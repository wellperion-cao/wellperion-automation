"""웰페리온 ERP 로그인 관문 (AWS 서버 · FastAPI · PostgreSQL).

역할
    가입 신청 → GM(관리자) 승인 → 로그인 → 쿠키(JWT) → nginx 가 쿠키 없는 요청에 페이지를 주지 않는다.
    GitHub Pages 의 gate.js '커튼'(비밀번호가 소스에 노출)을 진짜 잠금으로 바꾸는 첫 조각이다(배101).

경로
    GET  /auth/login   /auth/signup   — 화면
    POST /auth/login   /auth/signup   /auth/logout
    GET  /auth/check                  — nginx auth_request 용 (200 통과 / 401 로그인 필요 / 403 권한 없음)
    GET  /auth/me                     — 로그인 사용자 + allowed_ids(허용 모듈 id · 앱 셸이 카드 표시에 씀)
    GET  /auth/forbidden              — 403 안내 화면
    GET  /auth/admin                  — 관리자 콘솔(admin.html, SPA 하나가 아래 API로 전부 그린다)
    GET  /auth/admin/api/state        — 콘솔 데이터(관리자 아니거나 비밀번호 미입력=401)
    GET  /auth/admin/push_approvals   — 🔒 커밋·푸시 승인 현황(읽기 전용 · 배1098 2단계) · 결정은 GM 봇방 카드만
    POST /auth/admin/{uid}/perms      — 계정별 권한 저장(그룹·모듈 허용/거부)
    POST /auth/admin/{uid}/{action}   — approve | block | toggle_role | delete
    GET/POST /auth/admin/unlock       — 관리자 전용 비밀번호(ERP_ADMIN_SITE_PW · 30분 쿠키) — 관리자 화면 전부가 이 문을 지난다

권한 — 판정은 allowed() 한 곳(/auth/check · /auth/me · 관리자 화면이 같이 쓴다). 순서:
    ① role=admin            전부 허용
    ② account_perms.json    회사 계정 7개의 정본(GM 확정 2026-09-03 · 배951). DB perms 보다 우선한다.
    ③ users.perms (JSON)    관리자 화면에서 계정마다 준 권한
    ④ 아무것도 없으면       매일 쓰는 화면(core)만
    권한 JSON = {"all":true, "groups":["시포","핵심"], "modules":["check"], "deny":["member"]}
    all=전체 허용 · deny 가 언제나 우선. 되돌리기 = account_perms.json 의 accounts 를 비운다(종전 동작).

환경변수(/srv/erp/auth.env · 서버 밖으로 안 나감 · DB 접속은 /srv/erp/db.env 의 ERP_DB_URL — common/db.py 가 읽는다)
    ERP_JWT_SECRET  서명 키        TG_BOT_TOKEN / TG_CHAT_ID  가입 신청 알림(업무보고방)
    ERP_ADMIN_EMAIL 첫 관리자     ERP_ADMIN_PW 첫 관리자 비밀번호(첫 기동 때만 씀)
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional

import jwt
from fastapi import Cookie, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db as _db   # noqa: E402  — DB 를 여는 유일한 자리 · 모든 표는 tenant_id 로 거른다

T = _db.TENANT
MODULES = os.environ.get("ERP_MODULES", "/srv/erp/www/erp/modules.json")   # 자동 생성본(GitHub 동기화) · 여기서 수정 안 함
# 🔒 커밋·푸시 승인 원장(배1098) — 정본은 GM PC 저장소 status/push_approvals.json, 결정도 거기서만 난다
# (텔레그램 plk: 카드 → scripts/push_lock.decide()). 서버는 /srv/erp/www 5분 git 동기화를 그대로 읽기만 한다
# (close_days.json·modules.json 과 동일 패턴) — 여기서 쓰지 않는다, 관문을 두 곳으로 늘리지 않는다(약속 L21).
PUSH_APPROVALS = os.environ.get(
    "ERP_PUSH_APPROVALS",
    "/srv/erp/www/status/push_approvals.json" if os.path.isdir("/srv/erp/www") else
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "status", "push_approvals.json"))
GROUPS = ("핵심", "시포", "시모", "시우", "웰리", "시토", "시보", "시로", "시뽀", "GM")   # 핵심 = core:true 모듈 묶음(수동 개별조정용 — 아래 참고)
# 가입 폼 부서 선택지(GM 2026-09-05 지정 6부서).
DEPTS = ("운영부", "시설부", "지원부", "주차관리부", "경영지원", "파트너팀")

# ── 부서 기본 모듈(ERP 권한 정리 · 배1026 · GM 확정 2026-09-05 설계 §2③ 매트릭스) ──────────────
# 사람마다 다시 적지 않도록 이 표 하나가 정본이다(가입 승인·관리자 화면 "부서로 한 번에"·매트릭스
# "부서 기본 적용" 버튼이 전부 여기서 만든다 — 벌 두 개 금지). 전 부서 공통 + 부서 전용을 합쳐 쓴다.
DEPT_COMMON_MODULES = [
    "coo-reception-종합접수처-현황", "coo-reception-lost-found-register", "coo-reception-lost-found-gallery",
    "coo-reception-lost-found-disposal", "cpo-member-실무진피드백", "coo-todo-업무-현황-ssot",
    "coo-todo-결재-현황-ssot", "coo-check-전사-일정", "coo-check-전사-거래업체",
    "coo-check-주차장-이용안내-공지문", "chro-hub-schedule", "chro-hub-schedule-mobile", "chro-hub-leave",
]
# ponytail: 결재현황은 매트릭스가 원래 운영부=○·나머지=△(보기만)로 나눴지만, 화면에 읽기전용 모드가
# 없어(2-state 관문 구조) 전 부서 ○로 연다 — 진짜 보기전용이 필요해지면 그때 화면별로 넣는다.
DEPT_ONLY_MODULES = {
    "운영부":     ["member", "inquiry", "cpo-member-renewal", "cpo-member-오넛티-접수현황", "cpo-member-lesson",
                 "check", "coo-check-운영부-체계", "coo-리셉션-업무-라커관리-index", "coo-리셉션-업무-index",
                 "coo-brojay-브로제이-업무분장", "coo-brojay-브로제이-확인목록", "coo-notice-게시물-프로필월",
                 "cmo-intake-instructor-intake", "cmo-funnel-콘텐츠문의현황"],
    "시설부":     ["check"],                                        # 부서체계 = check 자기 자신(시설부 체계.html)
    "지원부":     ["check", "coo-check-지원부-체계"],
    "주차관리부": ["check", "coo-check-주차관리부-체계"],
    "파트너팀":   ["cpo-member-lesson", "coo-check-파트너팀-체계"],   # 점검(check)은 파트너팀 몫 아님(매트릭스 §2③)
    "경영지원":   [],                                                # 나우열M — 인사·재무는 개인 예외로 따로(§3, EXCEPTION_ONLY_IDS)
}


# 코드 표(위 두 상수) = 부서 기본의 "초안"일 뿐 — 서버 데이터 파일이 있으면 그게 정본이다(GM 이
# 권한 콘솔 「부서 기본 권한」 탭에서 직접 고친다 · GM 지시 2026-09-07 "일단 초안 셋팅해 주고 내가 수정할 수 있게").
# account_perms.json 과 같은 mtime 재읽기 패턴 — 재기동 없이 저장 즉시 반영.
_DEPT_DRAFT = {d: DEPT_COMMON_MODULES + DEPT_ONLY_MODULES.get(d, []) for d in DEPTS}
DEPT_PRESETS = os.environ.get("ERP_DEPT_PRESETS",
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "dept_presets.json"))
_PRESETS: tuple = (None, None)                 # (mtime, 파일 원본 dict) · 파일 없음/못 읽음 = None


def _presets_raw() -> Optional[dict]:
    global _PRESETS
    try:
        mt = os.stat(DEPT_PRESETS).st_mtime
    except OSError:
        _PRESETS = (None, None)
        return None
    if mt != _PRESETS[0]:
        with open(DEPT_PRESETS, encoding="utf-8") as f:
            _PRESETS = (mt, json.load(f))
    return _PRESETS[1]


def dept_presets() -> dict:
    """부서 → 모듈id 목록. 파일에 없는 부서는 코드 초안으로 메운다(부분 파일도 안전)."""
    raw = _presets_raw() or {}
    return {d: raw.get(d, _DEPT_DRAFT[d]) for d in DEPTS}


def dept_modules(dept: str) -> list:
    return dept_presets().get(dept, [])


# 개인 예외 3건(GM 확정 2026-09-05 §3) — 부서 템플릿·groups·all 매칭으로는 절대 안 열린다.
# GM 이 관리자 화면에서 그 사람에게만 modules 로 콕 집어 켜야 보인다(월간운영계획=이경연 실장·GM업무=김남욱 GM·
# 인사재무/채용=나우열M). 매출회원보고·자율현황·카톡전송관리도 경영진 전용이라 같은 방식으로 묶는다.
EXCEPTION_ONLY_IDS = frozenset({
    "gm-월간운영계획", "coo-chairman-gm업무",
    "cfo-finance-매출현황", "cfo-finance-지출현황", "cfo-finance-매출지출현황",
    "chro-hub-index", "chro-recruiting-index",
    "coo-report-매출회원현황보고", "cto-자율현황", "cto-automation-카톡전송관리",
})
# 계정별 권한 정본(GM 확정 2026-09-03 · 배951). 여기 적힌 계정은 이 파일이 DB perms 를 이긴다.
# accounts 를 비우거나 파일을 지우면 종전 동작(DB perms · 없으면 핵심 화면만)으로 그대로 돌아간다.
ACCOUNTS = os.environ.get("ERP_ACCOUNT_PERMS",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "account_perms.json"))
SECRET = os.environ["ERP_JWT_SECRET"]
COOKIE = "erp_session"
SESSION_DAYS = 90                              # 30→90 (배1134 · GM 「해보자」 2026-09-08)
KST = timezone(timedelta(hours=9))
LOCK_AFTER = 5                                 # 연속 실패 허용 횟수
LOCK_SECS = 600                                # 잠금 시간(10분)
# 사무실 PC 자동 로그인(배1134 · 기본 꺼짐 — OFFICE_AUTO_LOGIN_IP 가 비어 있으면 이 기능은 통째로 안 돈다).
# 켜기: /srv/erp/auth.env 에 OFFICE_AUTO_LOGIN_IP=114.207.50.85 (콤마로 여러 개) 추가 → systemctl restart erp-auth.
# 끄기: 그 줄을 지우거나 비우고 재기동 — 그 순간부터 그 IP 도 다시 로그인 화면을 본다(원래 동작).
OFFICE_AUTO_LOGIN_IPS = frozenset(ip.strip() for ip in os.environ.get("OFFICE_AUTO_LOGIN_IP", "").split(",") if ip.strip())
OFFICE_AUTO_LOGIN_ACCOUNT = os.environ.get("OFFICE_AUTO_LOGIN_ACCOUNT", "info@wellperion.com")
# 관리자 화면 별도 비밀번호(GM 2026-09-04 "관리자 사이트 비밀번호는 별도로") — 로그인 계정과 무관하게 한 번 더 묻는다.
# 값은 서버 /srv/erp/auth.env 에만 있다. 비어 있으면 종전대로(관리자 계정이면 바로 열림).
ADMIN_PW = os.environ.get("ERP_ADMIN_SITE_PW", "")
ADMIN_COOKIE = "erp_admin"
ADMIN_MIN = 30                                 # 관리자 비밀번호 한 번 넣으면 30분 유효
GOOGLE_ID = os.environ.get("GOOGLE_CLIENT_ID", "")      # 없으면 구글 로그인 라우트가 안내만 낸다
GOOGLE_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_HD = "wellperion.com"                   # 회사 워크스페이스 도메인 — 개인 gmail 차단
# 네이버·카카오(배1108 · GM 2026-09-07) — 구글과 같은 가입 신청·승인 흐름을 표 하나로 공유한다.
SOCIAL = {
    "naver": {"label": "네이버", "color": "#03C75A", "fg": "#fff",
              "auth_url": "https://nid.naver.com/oauth2.0/authorize",
              "token_url": "https://nid.naver.com/oauth2.0/token",
              "profile_url": "https://openapi.naver.com/v1/nid/me",
              "id_env": "NAVER_CLIENT_ID", "secret_env": "NAVER_CLIENT_SECRET"},
    "kakao": {"label": "카카오", "color": "#FEE500", "fg": "#221F20",
              "auth_url": "https://kauth.kakao.com/oauth/authorize",
              "token_url": "https://kauth.kakao.com/oauth/token",
              "profile_url": "https://kapi.kakao.com/v2/user/me",
              "id_env": "KAKAO_REST_API_KEY", "secret_env": "KAKAO_CLIENT_SECRET"},
}
# 키 출처 = 환경변수 또는 관리자 콘솔이 쓰는 social_keys.json(파일 있으면 파일 우선 · account_perms.json 과 같은 mtime 재읽기 패턴)
SOCIAL_KEYS_FILE = os.environ.get("ERP_SOCIAL_KEYS",
                                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "social_keys.json"))
_SOCIAL_KEYS: tuple = (None, {})


def _social_keys_raw() -> dict:
    global _SOCIAL_KEYS
    try:
        mt = os.stat(SOCIAL_KEYS_FILE).st_mtime
    except OSError:
        return {}
    if mt != _SOCIAL_KEYS[0]:
        with open(SOCIAL_KEYS_FILE, encoding="utf-8") as f:
            _SOCIAL_KEYS = (mt, json.load(f))
    return _SOCIAL_KEYS[1]


def social_creds(provider: str) -> tuple:
    """(client_id, client_secret) — social_keys.json 이 있으면 그 값이 환경변수보다 우선."""
    file_kv = _social_keys_raw().get(provider) or {}
    cfg = SOCIAL[provider]
    cid = file_kv.get("id") or os.environ.get(cfg["id_env"], "")
    secret = file_kv.get("secret") or os.environ.get(cfg["secret_env"], "")
    return cid, secret


# ── 아이디 가입 · 인사 명부 대조 (배1108 후속 · GM 2026-09-07 "원하는 아이디로, 대신 인사정보 크로스체크") ─
# 회사 이메일(@wellperion.com) 대신 아이디+비밀번호로 가입 신청할 수 있다. 단, 이름·연락처가
# 인사 허브 명부와 맞아야 신청이 접수된다(동명이인 방지용 전화 대조 포함) — GAS 는 인사 허브가
# 이미 쓰는 것 하나를 그대로 재사용한다(관문 두 곳 금지 · 약속 L21).
UID_RE = re.compile(r"^[a-z0-9._]{4,20}$")
HR_HUB_URL = "https://script.google.com/macros/s/AKfycbyyXrdM7nSXKPG3Dy8wI6_3AI1spZs24d-uHTzQZlsqzoRXKkFbSFnX-hr42D3ScQSSHQ/exec"
_HR_ROSTER: tuple = (0.0, None)                # (읽은시각, 명부 list) · 5분 캐시(성공했을 때만 채운다)


def valid_username(uid: str) -> bool:
    return bool(UID_RE.match(uid))


def hr_hub_pw() -> str:
    """social_keys.json 의 hr_hub_pw(관리자 콘솔 저장) 우선, 없으면 환경변수 HR_HUB_PW."""
    return (_social_keys_raw().get("hr_hub_pw") or "").strip() or os.environ.get("HR_HUB_PW", "")


def _digits(s) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def hr_match(name: str, phone: str, roster: list) -> bool:
    """이름 공백제거 완전일치 + 연락처 숫자만 완전일치 — 인사 허브 index.html isAlreadyHiredEmpByPhone_ 과 같은 원칙.
    이름만 맞고 전화가 다르면 불일치(동명이인 보호), 재직 상태가 퇴직·퇴사면 불일치. 순수 함수 —
    명부(roster)를 인자로 받으므로 자가점검에서 가짜 리스트를 넣어 테스트할 수 있다."""
    name_key, phone_key = "".join(str(name or "").split()), _digits(phone)
    if not name_key or not phone_key:
        return False
    for row in roster:
        row_name = row.get("성명") or row.get("이름") or ""
        if "".join(str(row_name).split()) != name_key:
            continue
        if _digits(row.get("연락처")) != phone_key:
            continue
        status = row.get("재직 상태") or row.get("재직상태") or ""
        if "퇴직" in status or "퇴사" in status:
            continue
        return True
    return False


def _hr_roster_fetch() -> list:
    """인사 허브 GAS 명부를 새로 읽는다. 실패하면 예외를 그대로 던진다(호출부가 사용자 문구로 번역)."""
    pw = hr_hub_pw()
    if not pw:
        raise RuntimeError("hr_hub_pw 미설정")
    body = json.dumps({"db": "emp", "password": pw}).encode("utf-8")
    req = urllib.request.Request(HR_HUB_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    rows = data.get("results") if isinstance(data, dict) else data
    return rows or []


def hr_roster() -> list:
    """5분 메모리 캐시(성공한 결과만 캐시 — 실패는 다음 호출에서 바로 재시도)."""
    global _HR_ROSTER
    ts, rows = _HR_ROSTER
    if rows is not None and time.time() - ts < 300:
        return rows
    rows = _hr_roster_fetch()
    _HR_ROSTER = (time.time(), rows)
    return rows


FAILS: dict[str, tuple[int, float]] = {}       # email -> (연속실패수, 잠금해제시각) · ponytail: 서버 1대 메모리 락, 다중서버면 DB/redis로

app = FastAPI(docs_url=None, redoc_url=None)


# ── 저장 ────────────────────────────────────────────────────────────────
def db() -> _db.Conn:
    return _db.connect()


def init() -> None:
    """표는 common/schema.sql(deploy_db.sh) 이 만든다 — 여기선 첫 관리자만 심는다."""
    with db() as c:
        admin_email = os.environ.get("ERP_ADMIN_EMAIL")
        if admin_email and not c.execute("SELECT 1 FROM users WHERE tenant_id=%s AND email=%s", (T, admin_email)).fetchone():
            salt, h = hash_pw(os.environ["ERP_ADMIN_PW"])
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,role,status,created_at,approved_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (T, admin_email, "GM", salt, h, "admin", "active", now(), now()))


def now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


# ── 권한 변경 이력(배1026 · 2026-09-05) — 매트릭스 "되돌리기" 20건이 여기서 읽는다. ────────────
def _perms_log(uid: int, before: Optional[str], after: Optional[str], by: str) -> None:
    with db() as c:
        c.execute("INSERT INTO perms_history(tenant_id,uid,before,after,changed_by,changed_at) VALUES(%s,%s,%s,%s,%s,%s)",
                  (T, uid, before, after, by, now()))


def _set_perms(uid: int, perms_dict: Optional[dict], by: str) -> None:
    """perms 를 갱신하고 이력 한 줄을 남긴다 — 저장 경로는 이 함수 하나로(관리자 화면·매트릭스·부서 일괄 전부)."""
    after = json.dumps(perms_dict, ensure_ascii=False) if perms_dict is not None else None
    with db() as c:
        row = c.execute("SELECT perms FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
        before = row["perms"] if row else None
        c.execute("UPDATE users SET perms=%s WHERE tenant_id=%s AND id=%s", (after, T, uid))
    if before != after:
        _perms_log(uid, before, after, by)


def hash_pw(pw: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1).hex()
    return salt, h


# ── 세션 ────────────────────────────────────────────────────────────────
def issue(user, auto: bool = False) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    claims = {"uid": user["id"], "email": user["email"], "role": user["role"], "exp": exp}
    if auto:
        claims["auto"] = True    # 사무실 자동 로그인 세션 표시(배1134) — check() 가 이 claim 으로 쓰기·인사 폴더를 막는다
    return jwt.encode(claims, SECRET, algorithm="HS256")


def is_auto_token(token: Optional[str]) -> bool:
    """세션이 사무실 자동 로그인으로 발급됐나 — current() 의 11개 호출부를 안 건드리려고 토큰을 따로 한 번 더 본다."""
    if not token:
        return False
    try:
        return bool(jwt.decode(token, SECRET, algorithms=["HS256"]).get("auto"))
    except jwt.PyJWTError:
        return False


def current(token: Optional[str]):
    if not token:
        return None
    try:
        claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND id=%s AND status='active'", (T, claims["uid"])).fetchone()
    return u


# ── 권한 ────────────────────────────────────────────────────────────────
_MODS: tuple = (None, [], {})                  # (mtime, 모듈 목록, 경로→모듈) · mtime 바뀌면 다시 읽는다


def modules() -> list:
    global _MODS
    try:
        mt = os.stat(MODULES).st_mtime
    except OSError:
        return _MODS[1]
    if mt != _MODS[0]:
        with open(MODULES, encoding="utf-8") as f:
            ms = json.load(f)["modules"]
        # path 는 /erp/ 기준 상대경로("../cpo/x.html") → 사이트 절대경로("/cpo/x.html")
        by_path = {posixpath.normpath(urllib.parse.urljoin("/erp/", m["path"])): m for m in ms}
        _MODS = (mt, ms, by_path)
    return _MODS[1]


_ACCTS: tuple = (None, {})                     # (mtime, 이메일→권한) · 파일이 바뀌면 다시 읽는다(재기동 불필요)


def accounts() -> dict:
    global _ACCTS
    try:
        mt = os.stat(ACCOUNTS).st_mtime
    except OSError:
        return {}                              # 파일 없음 = 종전 동작
    if mt != _ACCTS[0]:
        with open(ACCOUNTS, encoding="utf-8") as f:
            _ACCTS = (mt, {k.lower(): v for k, v in (json.load(f).get("accounts") or {}).items()})
    return _ACCTS[1]


def module_at(uri: str) -> Optional[dict]:
    """nginx 가 넘긴 X-Original-URI → 모듈. 목록에 없는 경로(공용 자산·status 등)는 None."""
    modules()
    # 선행 슬래시를 1개로 강제 — posixpath.normpath 는 '//x' 를 보존해 '//cpo/…' 요청이 모듈 조회를 빗나가게 했다
    # (권한 판정 우회 · 2026-09-05 검수 C4). nginx 는 merge_slashes 로 파일은 정상으로 내주므로 여기서 맞춘다.
    # urlsplit 을 쓰지 않는다 — '//cpo/x' 는 urlsplit 이 '//cpo' 를 호스트로 먹어 path 가 '/x' 가 된다(실측 2026-09-05).
    raw = uri.split("?", 1)[0].split("#", 1)[0]
    path = "/" + posixpath.normpath(urllib.parse.unquote(raw) or "/").lstrip("/")
    if path in _MODS[2]:
        return _MODS[2][path]
    if path.endswith(".html"):
        return None
    # 깔끔한 주소(.html 생략) 허용 — nginx try_files 가 $uri.html 로 파일을 찾으므로 권한 판정도 같은 파일로(GM 2026-09-05)
    m = _MODS[2].get(path + ".html")
    if m:
        return m
    # 폴더 index.html 모듈(/chro/hub/ 등 6개) — nginx try_files 가 $uri/index.html 로 찾는 것과 맞춘다(2026-09-05 검수 H2)
    return _MODS[2].get(path.rstrip("/") + "/index.html")


def perms_of(user) -> Optional[dict]:
    """계정 권한. account_perms.json 에 적힌 계정은 그 파일이 정본(관리자 화면 저장분보다 우선)."""
    fixed = accounts().get((user["email"] or "").lower())
    if fixed is not None:
        return fixed
    raw = user["perms"] if "perms" in user.keys() else None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def allowed(user, module: dict) -> bool:
    """계정이 모듈을 볼 수 있나. admin=전부 · perms 없음=핵심 화면만 · 있으면 거부>개인예외>허용.
    개인 예외(EXCEPTION_ONLY_IDS)는 groups/all 매칭을 건너뛴다 — modules 로 콕 집어야만 켜진다(배1026 §3)."""
    if user["role"] == "admin":
        return True
    p = perms_of(user)
    if p is None:                                  # 권한을 아직 안 준 계정 = 매일 쓰는 화면(핵심)만
        return bool(module.get("core"))
    if module["id"] in p.get("deny", []):
        return False
    if module["id"] in p.get("modules", []):
        return True
    if module["id"] in EXCEPTION_ONLY_IDS:
        return False                               # modules 에 없으면 groups·all 이 뭐든 여기서 끝 — 개인 예외 전용
    if p.get("all"):                               # 전체 허용 — deny 뺀 나머지 전부
        return True
    groups = p.get("groups", [])
    return module.get("group") in groups or ("핵심" in groups and bool(module.get("core")))


def allowed_ids(user) -> list:
    return [m["id"] for m in modules() if allowed(user, m)]


def tell_gm(text: str) -> None:
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        return
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass                                   # 알림 실패가 가입을 막지 않는다


# ── 화면 ────────────────────────────────────────────────────────────────
STYLE = (
    # 색·서체 = 브랜드가이드.html 정본(paper/ink/beige). 베이지는 라이트에서 글자 대비 미달이라 버튼 배경·선에만 쓴다.
    # 다크는 prefers-color-scheme 로 색만 뒤집는다. erp/index.html 과 같은 토큰(2026-09-03).
    "<meta name=viewport content='width=device-width,initial-scale=1'><style>"
    ":root{--bg:#F4F0EB;--paper:#fff;--ink:#221F20;--ink-soft:#6E655C;--line:rgba(34,31,32,.12);"
    "--line-strong:rgba(34,31,32,.28);--accent:#B79F8A;--accent-soft:rgba(183,159,138,.18);--focus:#221F20}"
    "@media(prefers-color-scheme:dark){:root{--bg:#221F20;--paper:#2a2725;--ink:#F4F0EB;--ink-soft:#AAA098;"
    "--line:rgba(255,255,255,.1);--line-strong:rgba(255,255,255,.24);--focus:#B79F8A}}"
    "*{box-sizing:border-box}html{color-scheme:light dark}"
    "body{margin:0;padding:10vh 16px 48px;font:15px/1.6 'Pretendard Variable',Pretendard,'Apple SD Gothic Neo',"
    "'Malgun Gothic',-apple-system,system-ui,sans-serif;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}"
    ".brand{display:block;width:100%;max-width:400px;margin:0 auto 20px;font-size:14px;font-weight:700;letter-spacing:.18em;"
    "color:var(--ink);text-decoration:none}.brand.wide{max-width:860px}"
    ".brand{display:flex;align-items:center}.brand svg{height:15px;width:auto;display:block}"
    ".brand small{margin-left:8px;font-size:12px;font-weight:600;letter-spacing:.06em;color:var(--ink-soft)}"
    "form,.box{width:100%;max-width:400px;margin:0 auto;padding:28px;background:var(--paper);border:1px solid var(--line);border-radius:8px}"
    ".box.wide{max-width:860px}"
    "h1{margin:0 0 18px;font-size:20px;font-weight:700;letter-spacing:-.01em}"
    "label{display:block;margin:0 0 14px;font-size:13px;font-weight:600;color:var(--ink-soft)}"
    "input{display:block;width:100%;margin-top:6px;padding:11px 12px;font:inherit;color:var(--ink);background:var(--paper);"
    "border:1px solid var(--line-strong);border-radius:8px}"
    "input::placeholder{color:var(--ink-soft);opacity:.7}"
    ":focus-visible{outline:2px solid var(--focus);outline-offset:2px}"
    "input:focus{outline:2px solid var(--focus);outline-offset:0;border-color:transparent}"
    "button{width:100%;margin-top:6px;padding:12px;font:inherit;font-weight:700;color:#221F20;background:var(--accent);"
    "border:0;border-radius:8px;cursor:pointer}button:hover{filter:brightness(1.06)}button:active{transform:translateY(1px)}"
    "button.sec{background:transparent;color:var(--ink);border:1px solid var(--line-strong)}"
    # 소셜 로그인 = 세로 박스 대신 가로 한 줄 원형 아이콘(GM 2026-09-07 "네모박스는 칸만 먹는다").
    ".soc{margin-top:16px}.soc-div{position:relative;margin:0 0 14px;text-align:center}"
    ".soc-div::before{content:'';position:absolute;left:0;right:0;top:50%;border-top:1px solid var(--line)}"
    ".soc-div span{position:relative;padding:0 10px;background:var(--paper);font-size:12px;color:var(--ink-soft)}"
    ".soc-row{display:flex;justify-content:center;align-items:center;gap:14px}"
    ".soc-row a,.soc-row span{display:flex;width:44px;height:44px;border-radius:50%;align-items:center;justify-content:center}"
    ".soc-row a{text-decoration:none;border:1px solid transparent}.soc-row a:hover{filter:brightness(1.06)}"
    ".soc-row span.off{opacity:.35;cursor:default;background:var(--accent-soft)}"
    "p{margin:16px 0 0;font-size:13.5px;color:var(--ink-soft)}p a{color:var(--ink);text-decoration:underline;text-underline-offset:3px;white-space:nowrap}"
    ".err,.ok{margin:0 0 16px;padding:8px 12px;font-size:13.5px;color:var(--ink);border-left:3px solid var(--accent);background:var(--accent-soft)}"
    ".err{border-left-color:#ED5B3F}"
    ".tw{overflow-x:auto}table{width:100%;min-width:640px;font-size:14px;border-collapse:collapse}"
    "th{padding:6px 8px;text-align:left;font-size:12px;font-weight:700;color:var(--ink-soft);border-bottom:1px solid var(--line-strong)}"
    "td{padding:10px 8px;vertical-align:top;border-bottom:1px solid var(--line)}td small{color:var(--ink-soft)}"
    "td form{display:inline;padding:0;border:0;width:auto;max-width:none;background:none}"
    "td button{width:auto;margin:0 6px 4px 0;padding:6px 10px;font-size:13px}"
    ".tag{display:inline-block;white-space:nowrap;padding:1px 8px;font-size:12px;font-weight:700;border-radius:8px;border:1px solid var(--line-strong)}"
    ".tag.on{background:var(--accent);color:#221F20;border-color:transparent}"
    ".nav{margin-top:18px;font-size:13.5px;color:var(--ink-soft)}.nav a{color:var(--ink);text-decoration:underline;text-underline-offset:3px;margin-right:14px}"
    # ── 2026-09-04 시포(GM "UI/UX 신경써서") — 머리글·상태색·대기 카드·비밀번호 표시·모바일 카드형 ──
    ".hd{max-width:400px;margin:0 auto 18px}.hd.wide{max-width:860px}.hd .brand{margin:0}.hd .sub{margin:4px 0 0;font-size:13px;color:var(--ink-soft)}"
    ".hint{margin:-6px 0 16px;padding:8px 12px;font-size:13px;color:var(--ink-soft);background:var(--accent-soft);border-radius:6px}"
    ".pw{position:relative;display:block}.pw button{position:absolute;right:6px;bottom:6px;width:auto;margin:0;padding:5px 9px;font-size:12px;font-weight:600;"
    "color:var(--ink-soft);background:transparent;border:0}.pw button:hover{color:var(--ink);filter:none}"
    ".foot{margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}.foot p{margin:6px 0 0}"
    ".tag.ok{color:#2E6B3A;background:rgba(46,107,58,.12);border-color:transparent}.tag.off{color:var(--ink-soft);background:transparent}"
    "@media(prefers-color-scheme:dark){.tag.ok{color:#9BD3A8;background:rgba(155,211,168,.14)}}"
    ".card{margin:0 0 20px;padding:14px 16px;border:1px solid var(--accent);border-radius:8px;background:var(--accent-soft)}"
    ".card h2{margin:0 0 6px;font-size:15px}.card .row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;padding:10px 0 4px;border-top:1px solid var(--line)}"
    ".card .row b{font-size:14.5px}.card .row small{color:var(--ink-soft)}.card .row .act{margin-left:auto;display:flex;gap:6px}"
    ".card .row form{display:inline;padding:0;border:0;width:auto;max-width:none;background:none}.card .row button{width:auto;margin:0;padding:7px 14px;font-size:13px}"
    ".muted{margin:0 0 18px;font-size:13.5px;color:var(--ink-soft)}"
    ".acts{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.acts a{font-size:13px;color:var(--ink);text-decoration:underline;text-underline-offset:3px;margin-right:4px}"
    "button.danger{background:transparent;color:#B3402B;border:1px solid rgba(179,64,43,.5)}button.danger:hover{background:rgba(179,64,43,.08)}"
    "tr.pend td{background:var(--accent-soft)}"
    "@media(max-width:640px){table{min-width:0}thead{display:none}tr,td{display:block}tr{padding:12px 0;border-bottom:1px solid var(--line)}"
    "td{padding:3px 0;border:0}td[data-l]::before{content:attr(data-l);display:inline-block;min-width:38px;margin-right:6px;font-size:12px;color:var(--ink-soft)}"
    ".acts{padding-top:6px}.card .row .act{margin-left:0;width:100%}}"
    # 권한 매트릭스 A3 가로 인쇄(배1026 §4-2 · 2026-09-05) — 화면 요소는 숨기고 표만 최대한 넓게.
    "@media print{@page{size:A3 landscape;margin:10mm}.hd,.nav,.find,#mfind,form button,.acts form"
    "{display:none!important}table{font-size:11px}#matrix{max-width:none}}"
    "</style>")

# 워드마크 = erp/brand/wellperion-wordmark.svg 원본 벡터(배932·952) · fill=currentColor 라 라이트/다크 --ink 상속
BRAND = "<a class=brand href=/erp/ aria-label='웰페리온 ERP'>" + """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108.7954 17.5240" height="20" role="img" aria-hidden="true"><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,96.8257,43.6787)" d="M0 0-3.093 5.825 .208 12.412H-1.778L-4.214 7.871-6.597 12.412H-8.731L-5.319 5.821-8.288-.041-14.694 12.412H-16.902L-8.271-3.912-4.197 3.954-.035-3.89 8.62 12.412H6.316Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,117.7407,42.6162)" d="M0 0-2.349 7.471H-3.277L-5.625 .004-8.025 7.47-9.046 7.471-6.261-1.094-4.967-1.096-2.813 5.929-.672-1.096 .621-1.094 3.419 7.471 2.399 7.47Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,122.3008,43.71)" d="M0 0H5.357V.776H.981V3.928H5.211V4.705H.981V7.788H5.357V8.563H0Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,130.3896,35.1455)" d="M0 0H-.981V-8.564H4.059V-7.788H0Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,136.5166,35.1455)" d="M0 0H-.981V-8.564H4.058V-7.788H0Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,147.4697,38.5273)" d="M0 0C-.151-.258-.361-.46-.635-.607-.857-.722-1.104-.81-1.378-.867-1.653-.925-2.063-.954-2.611-.954H-4.296V2.605H-3.036-2.718-2.399C-2.108 2.605-1.855 2.591-1.643 2.564-1.431 2.537-1.214 2.486-.993 2.409-.18 2.115 .224 1.584 .224 .814 .224 .529 .15 .257 0 0M-.078 2.917C-.45 3.126-.826 3.255-1.206 3.306-1.587 3.355-2.086 3.382-2.705 3.382H-5.277V-5.185H-4.296V-1.73H-2.452C-1.895-1.73-1.45-1.699-1.112-1.637-.652-1.552-.252-1.398 .094-1.173 .835-.695 1.207-.034 1.207 .808 1.207 1.743 .779 2.446-.078 2.917" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,150.0439,43.71)" d="M0 0H5.356V.776H.979V3.928H5.21V4.705H.979V7.788H5.356V8.563H0Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,163.793,37.938)" d="M0 0C0 .517-.129 .981-.39 1.391-.65 1.8-1.027 2.128-1.523 2.375-1.912 2.568-2.305 2.685-2.704 2.728-3.103 2.77-3.637 2.793-4.309 2.793H-6.643V-5.772H-5.66V2.016H-4.109C-3.632 2.016-3.215 1.991-2.855 1.946-2.498 1.899-2.178 1.79-1.895 1.616-1.611 1.442-1.389 1.217-1.225 .943-1.062 .669-.98 .381-.98 .081-.98-.314-1.09-.662-1.311-.963-1.532-1.265-1.846-1.496-2.253-1.659-2.536-1.767-2.8-1.832-3.05-1.856-3.296-1.878-3.654-1.891-4.122-1.891H-4.388-4.679L-1.353-5.772-.127-5.771-2.886-2.572C-2.092-2.572-1.411-2.316-.846-1.807-.281-1.298 0-.696 0 0" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,0,80)" d="M165.201 36.29H166.181V44.854H165.201Z" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,175.9219,41.9678)" d="M0 0C-.818-.707-1.806-1.061-2.964-1.061-4.096-1.061-5.079-.71-5.914-.012-6.751 .686-7.168 1.524-7.168 2.504-7.168 3.515-6.759 4.374-5.939 5.079-5.123 5.785-4.131 6.138-2.964 6.138-1.831 6.138-.85 5.791-.02 5.096 .812 4.401 1.227 3.561 1.227 2.573 1.227 1.564 .819 .704 0 0M.663 5.682C-.366 6.534-1.58 6.961-2.977 6.961-4.409 6.961-5.629 6.529-6.638 5.665-7.646 4.8-8.149 3.746-8.149 2.504-8.149 1.285-7.634 .249-6.604-.604-5.573-1.456-4.364-1.883-2.977-1.883-1.544-1.883-.321-1.448 .69-.579 1.7 .287 2.208 1.339 2.208 2.573 2.208 3.794 1.692 4.829 .663 5.682" fill="currentColor"/><path transform="translate(-79.3237,-30.6667) matrix(1,0,0,-1,186.5371,35.1455)" d="M0 0V-7.119L-5.494-.004-6.816 0V-8.564H-5.836V-1.033L0-8.564H.982V0Z" fill="currentColor"/></svg>""" + "<small>ERP</small></a>"
TOGGLE = ('<button type=button onclick="var i=this.previousElementSibling;i.type=i.type==\'password\'?\'text\':\'password\';'
          'this.textContent=i.type==\'password\'?\'표시\':\'숨김\'">표시</button>')


def head(sub: str, wide: bool = False) -> str:
    """머리글 — 워드마크 + 이 화면이 무엇인지 한 줄. 화면마다 그 한 줄만 바뀐다."""
    return f"<div class='hd{' wide' if wide else ''}'>{BRAND}<p class=sub>{escape(sub)}</p></div>"


def short_dt(v) -> str:
    """'2026-09-03 21:42:10' → '09-03 21:42' (올해면 연도 생략) — 표에서 날짜가 자리를 다 먹지 않게."""
    t = str(v or "")
    if not t:
        return ""
    if t[:4] == datetime.now().strftime("%Y"):
        t = t[5:]
    return t[:11]


def page(title: str, body: str) -> HTMLResponse:
    # 본문이 머리글(head())을 직접 가지면 그대로, 아니면 워드마크만 얹는다(종전 화면 호환).
    if "class='hd" not in body:
        body = (BRAND.replace("class=brand", "class='brand wide'") if "box wide" in body else BRAND) + body
    return HTMLResponse(f"<!doctype html><html lang=ko><meta charset=utf-8><title>{escape(title)}</title>{STYLE}{body}")


def safe_next(next: str, default: str = "/") -> str:
    """로그인 뒤 돌아갈 주소 검증 — '/' 로 시작하되 '//도메인' 오픈 리다이렉트는 막는다(2026-09-05 검수 M2)."""
    return next if next.startswith("/") and not next.startswith("//") else default


# 인라인 SVG 로고(외부 이미지 금지 · GM 2026-09-07) — 44px 원형 아이콘 안에 넣는다.
_ICON_GOOGLE = (
    "<svg viewBox='0 0 48 48' width=22 height=22 aria-hidden=true>"
    "<path fill='#FFC107' d='M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12"
    "c0-6.627,5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24"
    "c0,11.045,8.955,20,20,20c11.045,0,20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z'/>"
    "<path fill='#FF3D00' d='M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039"
    "l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z'/>"
    "<path fill='#4CAF50' d='M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36"
    "c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z'/>"
    "<path fill='#1976D2' d='M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571"
    "c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z'/></svg>")
_ICON_NAVER = ("<svg viewBox='0 0 24 24' width=17 height=17 aria-hidden=true>"
              "<path fill='#fff' d='M16.273 12.845 7.376 0H0v24h7.727V11.156L16.624 24H24V0h-7.727z'/></svg>")
_ICON_KAKAO = ("<svg viewBox='0 0 24 24' width=20 height=20 aria-hidden=true>"
              "<path fill='#391B1B' d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/></svg>")


def _social_login_buttons(next: str) -> str:
    """구글·네이버·카카오 — 가로 한 줄 원형 아이콘(GM 2026-09-07 "네모박스는 칸만 먹는다").
    키 없는 공급자는 회색 비활성 + title「준비 중」(클릭 안 됨 = span)."""
    provs = [
        ("google", "구글", GOOGLE_ID, "#fff", "#221F20", _ICON_GOOGLE, "border-color:var(--line-strong)"),
        ("naver", "네이버", social_creds("naver")[0], SOCIAL["naver"]["color"], SOCIAL["naver"]["fg"], _ICON_NAVER, ""),
        ("kakao", "카카오", social_creds("kakao")[0], SOCIAL["kakao"]["color"], SOCIAL["kakao"]["fg"], _ICON_KAKAO, ""),
    ]
    out = []
    for pid, label, cid, bg, fg, icon, extra in provs:
        title = f"{label} 계정으로 로그인"
        if cid:
            out.append(f'<a href="/auth/{pid}?next={escape(next)}" style="background:{bg};color:{fg};{extra}" '
                       f'aria-label="{title}" title="{title}">{icon}</a>')
        else:
            out.append(f'<span class=off title="{label} · 준비 중" aria-label="{label} · 준비 중">{icon}</span>')
    return f"""<div class=soc><div class=soc-div><span>또는 소셜 계정으로 로그인</span></div>
<div class=soc-row>{''.join(out)}</div></div>"""


def office_auto_login(request: Request, next: str) -> Optional[Response]:
    """사무실 고정 IP 자동 로그인(배1134 · OFFICE_AUTO_LOGIN_IP 비어 있으면 항상 None = 기능 꺼짐).
    조건: 클라이언트 IP 가 그 목록에 있고, 부서 계정이 살아 있고, 가려던 화면이 인사 폴더가 아니고
    그 계정이 볼 수 있는 화면일 때만 — 하나라도 아니면 평소대로 로그인 화면을 보여준다(안전한 쪽으로 폴백)."""
    if not OFFICE_AUTO_LOGIN_IPS:
        return None
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()   # erp.nginx.conf 가 $remote_addr 로 채운다
    if ip not in OFFICE_AUTO_LOGIN_IPS:
        return None
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND email=%s AND status='active'",
                      (T, OFFICE_AUTO_LOGIN_ACCOUNT)).fetchone()
    if not u:
        return None
    dest = safe_next(next)
    m = module_at(dest)
    if m and (m["id"].startswith("chro-") or not allowed(u, m)):
        return None
    r = RedirectResponse(dest, status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(COOKIE, issue(u, auto=True), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/", secure=https)
    return r


@app.get("/auth/login")
def login_page(request: Request, next: str = "/", err: str = "", msg: str = ""):
    if not err:
        auto = office_auto_login(request, next)
        if auto:
            return auto
    dest = {"/auth/admin": "계정 관리", "/auth/password": "비밀번호 변경"}.get(next)
    hint = f"<p class=hint>로그인하면 <b>{escape(dest)}</b> 화면으로 이동합니다</p>" if dest else ""
    # 머리글에 개인 계정을 적어 둔다(GM 지시 2026-09-11 "개인계정 가입하는 것도 열어놔줘").
    # 흐름은 2026-09-05 부터 이미 열려 있었는데(개인 구글 = 이름·부서 확인 → GM 승인),
    # 화면 문구가 「아이디 또는 회사 이메일」 이라 닫힌 것처럼 읽혔다.
    return page("웰페리온 ERP 로그인", head("직원용 업무 화면 · 아이디 · 회사 이메일 · 개인 구글 계정으로 로그인") + f"""<form method=post action=/auth/login>
<h1>로그인</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}{hint}
<label>아이디 또는 이메일<input name=email type=text autocomplete=username placeholder="아이디 또는 이름@wellperion.com" required autofocus></label>
<label>비밀번호<span class=pw><input name=password type=password autocomplete=current-password required>""" + TOGGLE + f"""</span></label>
<input type=hidden name=next value="{escape(next)}"><button>로그인</button>
{_social_login_buttons(next)}
<div class=foot><p><b>개인 구글 계정(gmail 등)으로도 됩니다.</b> 처음이면 이름·부서만 알려주세요 — 승인은 GM 이 합니다.</p>
<p>구글 계정이 없으면 <a href=/auth/signup>아이디로 가입 신청</a> · 비밀번호를 잊으셨으면 GM 께 말씀해 주세요.</p></div></form>""")


@app.post("/auth/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    email = email.strip().lower()
    count, locked_until = FAILS.get(email, (0, 0.0))
    if locked_until > time.time():
        wait_min = max(1, int((locked_until - time.time()) // 60) + 1)
        return RedirectResponse(f"/auth/login?err=로그인 5회 실패로 잠겼습니다. {wait_min}분 후 다시 시도하세요&next={next}", status_code=303)
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND email=%s", (T, email)).fetchone()
    if not u or hash_pw(password, u["salt"])[1] != u["pw"]:
        count += 1
        FAILS[email] = (0, time.time() + LOCK_SECS) if count >= LOCK_AFTER else (count, 0.0)
        return RedirectResponse(f"/auth/login?err=이메일 또는 비밀번호가 맞지 않습니다&next={next}", status_code=303)
    FAILS.pop(email, None)
    if u["status"] != "active":
        return RedirectResponse("/auth/login?err=아직 승인 전입니다. GM 승인 후 로그인됩니다", status_code=303)
    r = RedirectResponse(safe_next(next), status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"     # nginx 만 보냄 · http(IP접속)는 종전대로 secure 없음
    r.set_cookie(COOKIE, issue(u), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/", secure=https)
    return r


@app.get("/auth/signup")
def signup_page(msg: str = ""):
    dept_opts = "".join(f"<option value='{escape(d)}'>{escape(d)}</option>" for d in DEPTS)
    return page("웰페리온 ERP 가입 신청", head("직원용 업무 화면 · 가입 신청") + f"""<form method=post action=/auth/signup>
<h1>가입 신청</h1>{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<label>아이디<input name=username autocomplete=username minlength=4 maxlength=20 pattern="[a-z0-9._]{{4,20}}"
title="영문 소문자·숫자·.·_ 4~20자" placeholder="영문 소문자·숫자·.·_ 4~20자" required></label>
<label>비밀번호<input name=password type=password placeholder="8자 이상" minlength=8 autocomplete=new-password required></label>
<label>이름<input name=name placeholder="직함 포함, 예: 홍길동 매니저" autocomplete=name required></label>
<label>연락처<input name=phone type=tel autocomplete=tel placeholder="010-0000-0000" required></label>
<label>부서<select name=dept required><option value="">선택</option>{dept_opts}</select></label>
<button>신청</button><div class=foot><p>이름·연락처는 인사 등록 정보와 대조됩니다. 신청하면 GM 께 알림이 가고, 승인되면 그 계정으로 로그인할 수 있습니다.</p>
<p>이미 계정이 있으면 <a href=/auth/login>로그인</a></p></div></form>""")


@app.post("/auth/signup")
def signup(name: str = Form(...), username: str = Form(...), password: str = Form(...),
           phone: str = Form(...), dept: str = Form(...)):
    name = name.strip()
    uid = "".join(username.split()).lower()
    is_company = uid.endswith("@" + GOOGLE_HD)             # 이메일 형태로 넣으면 종전 구글 회사계정과 같이 자동 활성
    if dept not in DEPTS:
        return RedirectResponse("/auth/signup?msg=부서를 선택해 주세요", status_code=303)
    if not is_company and not valid_username(uid):
        return RedirectResponse("/auth/signup?msg=아이디는 영문 소문자·숫자·.·_ 4~20자로 입력해 주세요", status_code=303)
    mark = "회사 계정"
    if not is_company:
        if not hr_hub_pw():
            return RedirectResponse("/auth/signup?msg=가입 신청 대조 준비 중 — 경영지원에 문의", status_code=303)
        try:
            roster = hr_roster()
        except Exception:
            return RedirectResponse("/auth/signup?msg=인사 정보 확인이 잠시 안 됩니다. 잠시 뒤 다시", status_code=303)
        if not hr_match(name, phone, roster):
            return RedirectResponse(
                "/auth/signup?msg=인사 정보와 이름·연락처가 일치하지 않습니다. 인사 등록된 이름·휴대폰 번호 그대로 입력해 주세요",
                status_code=303)
        mark = "인사 대조 ✅"
    salt, h = hash_pw(password)
    status, approved_at = ("active", now()) if is_company else ("pending", None)
    perms = {"dept": dept, "phone": _digits(phone), "groups": [], "modules": dept_modules(dept), "deny": []}
    try:
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,role,status,created_at,approved_at,perms) "
                      "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (T, uid, name, salt, h, "staff", status, now(), approved_at, json.dumps(perms, ensure_ascii=False)))
    except _db.IntegrityError:
        return RedirectResponse("/auth/signup?msg=이미 있는 아이디입니다", status_code=303)
    if is_company:
        tell_gm(f"🔐 ERP 가입 — {name} ({uid} · {dept} · {mark} · 자동 활성)")
        return RedirectResponse("/auth/signup?msg=가입됐습니다. 바로 로그인할 수 있습니다", status_code=303)
    tell_gm(f"🔐 ERP 가입 신청 — {name} ({uid} · {dept} · {mark})\n승인: https://erp.wellperion.com/auth/admin")
    return RedirectResponse("/auth/signup?msg=신청됐습니다. GM 승인 후 로그인할 수 있습니다", status_code=303)


@app.post("/auth/logout")
@app.get("/auth/logout")
def logout():
    r = RedirectResponse("/auth/login", status_code=303)
    r.delete_cookie(COOKIE, path="/")
    return r


@app.get("/auth/check")
def check(request: Request, erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        raise HTTPException(401)
    m = module_at(request.headers.get("x-original-uri", ""))    # nginx 가 붙인다(erp.nginx.conf) · 없으면 로그인만 본다
    if m and not allowed(u, m):
        raise HTTPException(403)
    if is_auto_token(erp_session):
        # 사무실 자동 로그인 세션(배1134) — 계정 perms 와 별개로 조회만 허용. 쓰기(GET/HEAD 아닌 요청)와
        # 인사 폴더(chro-*)는 이 세션으로 못 연다 — account_perms.json 이 나중에 바뀌어도 여기서 다시 막는다.
        if (request.headers.get("x-original-method") or "GET").upper() not in ("GET", "HEAD"):
            raise HTTPException(403)
        if m and m["id"].startswith("chro-"):
            raise HTTPException(403)
    return Response(status_code=200, headers={"X-Erp-User": u["email"], "X-Erp-Role": u["role"]})


@app.get("/auth/me")
def me(erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        raise HTTPException(401)
    return JSONResponse({"email": u["email"], "name": u["name"], "role": u["role"], "allowed_ids": allowed_ids(u)})


@app.get("/auth/forbidden")
def forbidden_page(next: str = "/"):
    return page("권한 없음", f"""<div class=box><h1>권한 없음</h1>
<p class=err>이 화면은 지금 계정에 허용되지 않았습니다.<br><small>{escape(next)}</small></p>
<p>필요하면 GM 에게 권한을 요청하세요. <a href=/erp/>ERP 홈으로</a></p></div>""")


@app.get("/auth/password")
def password_page(erp_session: Optional[str] = Cookie(default=None), msg: str = "", err: str = ""):
    if not current(erp_session):
        return RedirectResponse("/auth/login?next=/auth/password", status_code=303)
    return page("비밀번호 변경", head("내 계정 · 비밀번호 변경") + f"""<form method=post action=/auth/password>
<h1>비밀번호 변경</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<label>현재 비밀번호<input name=current_password type=password autocomplete=current-password required></label>
<label>새 비밀번호<input name=new_password type=password placeholder="8자 이상" minlength=8 autocomplete=new-password required></label>
<button>변경</button><p><a href=/erp/>ERP 로 돌아가기</a></p></form>""")


@app.post("/auth/password")
def password_change(current_password: str = Form(...), new_password: str = Form(...),
                     erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        return RedirectResponse("/auth/login?next=/auth/password", status_code=303)
    if hash_pw(current_password, u["salt"])[1] != u["pw"]:
        return RedirectResponse("/auth/password?err=현재 비밀번호가 맞지 않습니다", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse("/auth/password?err=새 비밀번호는 8자 이상이어야 합니다", status_code=303)
    salt, h = hash_pw(new_password)
    with db() as c:
        c.execute("UPDATE users SET salt=%s, pw=%s WHERE tenant_id=%s AND id=%s", (salt, h, T, u["id"]))
    return RedirectResponse("/auth/password?msg=변경됐습니다", status_code=303)


# ── 소셜 로그인 공용 — state(jwt+브라우저 nonce 쿠키) 구글·네이버·카카오가 같이 쓴다 ──────────
# 브라우저 결속 난수(2026-09-05 검수 M1) — state 서명만으로는 공격자가 자기 로그인 흐름을 시작해 얻은
# 콜백 URL 을 직원에게 열게 하는 로그인 CSRF 를 못 막는다. 이 요청을 시작한 브라우저만 아는 값을
# 쿠키+state 둘 다에 넣고 콜백에서 대조한다.
def _oauth_redirect_uri(request: Request, provider: str) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/auth/{provider}/callback"


def _oauth_state_new(next: str) -> tuple:
    """(state, nonce) — nonce 는 쿠키에도 심어 콜백에서 대조한다."""
    nonce = secrets.token_urlsafe(16)
    state = jwt.encode({"n": safe_next(next), "b": nonce, "exp": int(time.time()) + 600}, SECRET, algorithm="HS256")
    return state, nonce


def _oauth_state_verify(state: str, cookie_nonce: Optional[str]) -> str:
    """반환 = next 경로. 실패하면 ValueError(그대로 err= 뒤에 붙일 한글 문구)."""
    try:
        claims = jwt.decode(state, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ValueError("로그인 요청이 만료됐습니다. 다시 시도하세요")
    if not cookie_nonce or not secrets.compare_digest(cookie_nonce, claims.get("b", "")):
        raise ValueError("로그인 요청이 이 브라우저에서 시작되지 않았습니다. 다시 시도하세요")
    return claims["n"]


# ── 구글 계정 로그인 ────────────────────────────────────────────────────
# 회사 워크스페이스(@wellperion.com) 계정 = GM 승인 없이 바로 통과(GM 지시 2026-09-03).
# 개인 구글 계정 = 이름·부서 선택 후 GM 승인 대기(GM 지시 2026-09-05 · 역할별 회사계정 1개 방식 폐기).
# id_token 은 우리 클라이언트 시크릿으로 구글에서 직접(TLS) 받아오므로 서명 재검증 없이 payload 를 읽는다.
def _redirect_uri(request: Request) -> str:
    return _oauth_redirect_uri(request, "google")


def _google_token(code: str, redirect_uri: str) -> dict:
    body = urllib.parse.urlencode({"code": code, "client_id": GOOGLE_ID, "client_secret": GOOGLE_SECRET,
                                   "redirect_uri": redirect_uri, "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _id_claims(id_token: str) -> dict:
    payload = id_token.split(".")[1]
    return json.loads(urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def is_company_account(claims: dict) -> bool:
    email = (claims.get("email") or "").strip().lower()
    return bool(claims.get("hd") == GOOGLE_HD and claims.get("email_verified")
                and email.endswith("@" + GOOGLE_HD))


def is_valid_google_account(claims: dict) -> bool:
    """개인 계정도 통과 — 구글이 이메일을 확인해줬으면 충분하다(가입 승인은 GM 이 뒤에서 한다)."""
    return bool(claims.get("email_verified") and claims.get("email"))


@app.get("/auth/google")
def google_start(request: Request, next: str = "/"):
    if not GOOGLE_ID or not GOOGLE_SECRET:
        return page("회사 구글 로그인", "<div class=box><h1>아직 설정 전입니다</h1>"
                    "<p>구글 OAuth 클라이언트를 등록하고 서버 /srv/erp/auth.env 에 "
                    "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 을 넣으면 켜집니다.</p>"
                    "<p><a href=/auth/login>로그인 화면으로</a></p></div>")
    state, nonce = _oauth_state_new(next)
    # hd 파라미터 없음 = 계정 선택창에 개인 구글 계정도 뜬다(GM 2026-09-05). 회사 계정 여부는 콜백에서 판별.
    q = urllib.parse.urlencode({"client_id": GOOGLE_ID, "redirect_uri": _redirect_uri(request),
                                "response_type": "code", "scope": "openid email profile",
                                "state": state, "prompt": "select_account"})
    r = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + q, status_code=302)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie("erp_oauth_n", nonce, max_age=600, httponly=True, samesite="lax", path="/auth/google", secure=https)
    return r


@app.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "",
                     erp_oauth_n: Optional[str] = Cookie(default=None)):
    if not GOOGLE_ID or not GOOGLE_SECRET:
        return RedirectResponse("/auth/login?err=구글 로그인이 아직 설정되지 않았습니다", status_code=303)
    if error or not code:
        return RedirectResponse("/auth/login?err=구글 로그인이 취소됐습니다", status_code=303)
    try:
        nxt = _oauth_state_verify(state, erp_oauth_n)
    except ValueError as e:
        return RedirectResponse(f"/auth/login?err={e}", status_code=303)
    try:
        claims = _id_claims(_google_token(code, _redirect_uri(request))["id_token"])
    except Exception:
        return RedirectResponse("/auth/login?err=구글 인증에 실패했습니다", status_code=303)
    if not is_valid_google_account(claims):
        return RedirectResponse("/auth/login?err=구글 인증에 실패했습니다", status_code=303)
    email = claims["email"].strip().lower()
    name = (claims.get("name") or email.split("@")[0]).strip()
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND email=%s", (T, email)).fetchone()
    if u:
        # 이미 있는 계정 — 회사 계정이든 개인 계정이든 상태 그대로 따른다(승인 우회 없음).
        if u["status"] == "blocked":
            return RedirectResponse("/auth/login?err=차단된 계정입니다. GM 에게 문의하세요", status_code=303)
        if u["status"] != "active":
            return RedirectResponse("/auth/login?err=아직 승인 전입니다. GM 승인 후 로그인됩니다", status_code=303)
    elif is_company_account(claims):
        # 회사 워크스페이스 계정 — GM 승인 없이 바로 활성(GM 2026-09-03 · 종전 동작 유지).
        salt, h = hash_pw(secrets.token_urlsafe(32))        # 구글 전용 계정 — 비밀번호 로그인은 못 쓴다
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,role,status,created_at,approved_at,perms) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (T, email, name, salt, h, "staff", "active", now(), now(), None))
            u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND email=%s", (T, email)).fetchone()
    else:
        # 개인 구글 계정, 첫 로그인 — 이름·부서 확인 후 승인 대기로 넘긴다(GM 2026-09-05).
        reg = jwt.encode({"e": email, "n": name, "exp": int(time.time()) + 600}, SECRET, algorithm="HS256")
        return RedirectResponse(f"/auth/google/finish?t={reg}&next={urllib.parse.quote(nxt, safe='')}", status_code=303)
    r = RedirectResponse(nxt, status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(COOKIE, issue(u), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/", secure=https)
    return r


# 이름·부서 확인 화면 — 구글 개인계정과 네이버·카카오(항상 개인 취급) 가 공유한다. t 토큰의 "p"(공급자)로
# 화면 문구·알림만 갈리고, 절차(부서 선택 → perms 초안 → GM 승인 대기)는 하나다(약속 L21 · 관문 늘리지 않는다).
def _finish_claims(t: str) -> dict:
    try:
        return jwt.decode(t, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise ValueError("인증이 만료됐습니다. 처음부터 다시 로그인하세요")


def _finish_page(t: str, next: str, err: str, action: str) -> Response:
    """개인 계정 첫 로그인 — 이름 확인 + 부서 선택. t 는 600초짜리 서명 토큰(이메일·표시이름·공급자)."""
    try:
        claims = _finish_claims(t)
    except ValueError as e:
        return RedirectResponse(f"/auth/login?err={e}", status_code=303)
    label = SOCIAL.get(claims.get("p", "google"), {}).get("label", "구글")
    opts = "".join(f"<option value='{escape(d)}'>{escape(d)}</option>" for d in DEPTS)
    return page("가입 완료", head(f"{label} 로그인 확인 · 이름과 부서만 알려주세요") + f"""<form method=post action={action}>
<h1>가입 완료</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<p class=hint>{escape(claims['e'])} 계정으로 계속합니다.</p>
<label>이름<input name=name value="{escape(claims['n'])}" placeholder="직함 포함, 예: 홍길동 매니저" required></label>
<label>부서<select name=dept required><option value=''>선택하세요</option>{opts}</select></label>
<input type=hidden name=t value="{escape(t)}"><input type=hidden name=next value="{escape(next)}">
<button>신청</button><div class=foot><p>신청하면 GM 께 알림이 가고, 승인되면 부서 화면으로 로그인할 수 있습니다.</p></div></form>""")


def _finish_submit(name: str, dept: str, t: str, next: str, action: str) -> Response:
    try:
        claims = _finish_claims(t)
    except ValueError as e:
        return RedirectResponse(f"/auth/login?err={e}", status_code=303)
    if dept not in DEPTS:
        return RedirectResponse(f"{action}?t={t}&next={urllib.parse.quote(next, safe='')}&err=부서를 선택하세요", status_code=303)
    email, salt_pw = claims["e"], secrets.token_urlsafe(32)     # 소셜 전용 계정 — 비밀번호 로그인은 못 쓴다
    salt, h = hash_pw(salt_pw)
    perms = json.dumps({"dept": dept, "groups": [], "modules": dept_modules(dept), "deny": []}, ensure_ascii=False)
    try:
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,created_at,perms) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                      (T, email, name.strip(), salt, h, now(), perms))
    except _db.IntegrityError:
        pass                                    # 중복 제출 — 이미 신청돼 있으니 그대로 대기 안내만
    provider = claims.get("p")                  # 구글(기본 흐름)은 문구 그대로, 네이버·카카오만 계정 종류를 덧붙인다
    suffix = f" · {SOCIAL[provider]['label']} 계정" if provider else ""
    tell_gm(f"🔐 ERP 가입 신청 — {name.strip()} ({email} · {dept}{suffix})\n승인: https://erp.wellperion.com/auth/admin")
    return RedirectResponse("/auth/login?msg=신청됐습니다. GM 승인 후 로그인할 수 있습니다", status_code=303)


@app.get("/auth/google/finish")
def google_finish_page(t: str = "", next: str = "/", err: str = ""):
    return _finish_page(t, next, err, "/auth/google/finish")


@app.post("/auth/google/finish")
def google_finish(name: str = Form(...), dept: str = Form(...), t: str = Form(...), next: str = Form("/")):
    return _finish_submit(name, dept, t, next, "/auth/google/finish")


@app.get("/auth/social/finish")
def social_finish_page(t: str = "", next: str = "/", err: str = ""):
    return _finish_page(t, next, err, "/auth/social/finish")


@app.post("/auth/social/finish")
def social_finish(name: str = Form(...), dept: str = Form(...), t: str = Form(...), next: str = Form("/")):
    return _finish_submit(name, dept, t, next, "/auth/social/finish")


# ── 네이버·카카오 로그인 ────────────────────────────────────────────────
# 구글과 달리 회사 계정 개념이 없다 — 로그인하면 무조건 개인 취급, 기존 계정이면 상태만 따르고
# 신규면 위 _finish_page/_finish_submit(이름·부서 확인 → GM 승인 대기)로 넘긴다.
def _social_token(provider: str, code: str, redirect_uri: str, client_id: str, client_secret: str, state: str) -> dict:
    cfg = SOCIAL[provider]
    data = {"grant_type": "authorization_code", "client_id": client_id, "code": code, "redirect_uri": redirect_uri}
    if provider == "naver":
        data["state"] = state
    if client_secret:
        data["client_secret"] = client_secret
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(cfg["token_url"], data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _social_profile(provider: str, access_token: str) -> dict:
    req = urllib.request.Request(SOCIAL[provider]["profile_url"], headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _social_identity(provider: str, profile: dict) -> tuple:
    """(계정 키로 쓸 이메일, 표시 이름). 카카오가 이메일 미동의면 kakao_{id}@kakao.login 로 대체
    (발송용 아님 — users.email 칸을 채우는 로그인 식별자일 뿐, 화면엔 「카카오 계정」으로 보인다)."""
    if provider == "naver":
        r = profile.get("response") or {}
        email = (r.get("email") or "").strip().lower()
        if not email:
            raise ValueError("네이버 계정에 이메일 제공 동의가 필요합니다")
        return email, (r.get("name") or email.split("@")[0]).strip()
    acct = profile.get("kakao_account") or {}
    email = (acct.get("email") or "").strip().lower()
    if not email:
        email = f"kakao_{profile['id']}@kakao.login"
    name = ((acct.get("profile") or {}).get("nickname") or email.split("@")[0]).strip()
    return email, name


def _social_start(request: Request, provider: str, next: str) -> Response:
    cfg = SOCIAL[provider]
    cid, _ = social_creds(provider)
    if not cid:
        return page(f"{cfg['label']} 계정 로그인", f"<div class=box><h1>아직 설정 전입니다</h1>"
                    f"<p>관리자 콘솔(소셜 로그인 키)에서 {cfg['label']} 키를 넣으면 켜집니다.</p>"
                    "<p><a href=/auth/login>로그인 화면으로</a></p></div>")
    state, nonce = _oauth_state_new(next)
    q = urllib.parse.urlencode({"client_id": cid, "redirect_uri": _oauth_redirect_uri(request, provider),
                                "response_type": "code", "state": state})
    r = RedirectResponse(cfg["auth_url"] + "?" + q, status_code=302)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie("erp_oauth_n", nonce, max_age=600, httponly=True, samesite="lax", path=f"/auth/{provider}", secure=https)
    return r


def _social_callback(request: Request, provider: str, code: str, state: str, error: str,
                      erp_oauth_n: Optional[str]) -> Response:
    cfg = SOCIAL[provider]
    cid, secret = social_creds(provider)
    if not cid:
        return RedirectResponse(f"/auth/login?err={cfg['label']} 로그인이 아직 설정되지 않았습니다", status_code=303)
    if error or not code:
        return RedirectResponse(f"/auth/login?err={cfg['label']} 로그인이 취소됐습니다", status_code=303)
    try:
        nxt = _oauth_state_verify(state, erp_oauth_n)
    except ValueError as e:
        return RedirectResponse(f"/auth/login?err={e}", status_code=303)
    try:
        redirect_uri = _oauth_redirect_uri(request, provider)
        tok = _social_token(provider, code, redirect_uri, cid, secret, state)
        profile = _social_profile(provider, tok["access_token"])
        email, name = _social_identity(provider, profile)
    except ValueError as e:
        return RedirectResponse(f"/auth/login?err={e}", status_code=303)
    except Exception:
        return RedirectResponse(f"/auth/login?err={cfg['label']} 인증에 실패했습니다", status_code=303)
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND email=%s", (T, email)).fetchone()
    if u:
        if u["status"] == "blocked":
            return RedirectResponse("/auth/login?err=차단된 계정입니다. GM 에게 문의하세요", status_code=303)
        if u["status"] != "active":
            return RedirectResponse("/auth/login?err=아직 승인 전입니다. GM 승인 후 로그인됩니다", status_code=303)
        r = RedirectResponse(nxt, status_code=303)
        https = request.headers.get("x-forwarded-proto") == "https"
        r.set_cookie(COOKIE, issue(u), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/", secure=https)
        return r
    reg = jwt.encode({"e": email, "n": name, "p": provider, "exp": int(time.time()) + 600}, SECRET, algorithm="HS256")
    return RedirectResponse(f"/auth/social/finish?t={reg}&next={urllib.parse.quote(nxt, safe='')}", status_code=303)


@app.get("/auth/naver")
def naver_start(request: Request, next: str = "/"):
    return _social_start(request, "naver", next)


@app.get("/auth/naver/callback")
def naver_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    erp_oauth_n: Optional[str] = Cookie(default=None)):
    return _social_callback(request, "naver", code, state, error, erp_oauth_n)


@app.get("/auth/kakao")
def kakao_start(request: Request, next: str = "/"):
    return _social_start(request, "kakao", next)


@app.get("/auth/kakao/callback")
def kakao_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    erp_oauth_n: Optional[str] = Cookie(default=None)):
    return _social_callback(request, "kakao", code, state, error, erp_oauth_n)


# ── 관리자 ──────────────────────────────────────────────────────────────
def admin_only(token: Optional[str], admin_token: Optional[str] = None, next: str = "/auth/admin"):
    u = current(token)
    if not u or u["role"] != "admin":
        raise HTTPException(403, "관리자만")
    if ADMIN_PW and not _admin_unlocked(admin_token, u["id"]):
        # 관리자 비밀번호를 아직 안 넣었다 — 입력 화면으로(303). 라우트마다 분기하지 않고 여기 한 곳에서.
        raise HTTPException(303, headers={"Location": "/auth/admin/unlock?next=" + urllib.parse.quote(next, safe="/")})
    return u


def _admin_unlocked(admin_token: Optional[str], uid: int) -> bool:
    if not admin_token:
        return False
    try:
        c = jwt.decode(admin_token, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return False
    return c.get("p") == "admin" and c.get("uid") == uid


def _admin_issue(uid: int) -> str:
    return jwt.encode({"p": "admin", "uid": uid, "exp": int(time.time()) + ADMIN_MIN * 60}, SECRET, algorithm="HS256")


@app.get("/auth/admin/unlock")
def admin_unlock_page(next: str = "/auth/admin", err: str = "", erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u or u["role"] != "admin":
        return RedirectResponse("/auth/login?next=" + urllib.parse.quote(next, safe="/"), status_code=303)
    return page("관리자 확인", head("관리자 화면 · 비밀번호 한 번 더") + f"""<form method=post action=/auth/admin/unlock>
<h1>관리자 비밀번호</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<p class=hint>로그인 계정과 별개인 관리자 전용 비밀번호입니다. 넣으면 {ADMIN_MIN}분 동안 다시 묻지 않습니다.</p>
<label>관리자 비밀번호<span class=pw><input name=password type=password autocomplete=off required autofocus>""" + TOGGLE + f"""</span></label>
<input type=hidden name=next value="{escape(safe_next(next, '/auth/admin'))}"><button>확인</button>
<div class=foot><p><a href=/erp/>ERP 로 돌아가기</a></p></div></form>""")


@app.post("/auth/admin/unlock")
def admin_unlock(request: Request, password: str = Form(...), next: str = Form("/auth/admin"),
                 erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u or u["role"] != "admin":
        raise HTTPException(403, "관리자만")
    key = "admin:" + u["email"]
    count, locked_until = FAILS.get(key, (0, 0.0))
    if locked_until > time.time():
        wait_min = max(1, int((locked_until - time.time()) // 60) + 1)
        return RedirectResponse(f"/auth/admin/unlock?err=5회 틀려 잠겼습니다. {wait_min}분 후 다시&next={next}", status_code=303)
    if not ADMIN_PW or not secrets.compare_digest(password, ADMIN_PW):
        count += 1
        FAILS[key] = (0, time.time() + LOCK_SECS) if count >= LOCK_AFTER else (count, 0.0)
        return RedirectResponse(f"/auth/admin/unlock?err=관리자 비밀번호가 맞지 않습니다&next={next}", status_code=303)
    FAILS.pop(key, None)
    r = RedirectResponse(safe_next(next, "/auth/admin"), status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(ADMIN_COOKIE, _admin_issue(u["id"]), max_age=ADMIN_MIN * 60, httponly=True, samesite="lax", path="/auth/admin", secure=https)
    return r


def _row_perms(r) -> dict:
    try:
        return json.loads(r["perms"]) if r["perms"] else {}
    except ValueError:
        return {}


_ADMIN_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin.html")


@app.get("/auth/admin")
def admin(erp_session: Optional[str] = Cookie(default=None)):
    # 미로그인이면 로그인 화면으로 보낸다 — 새 창·시크릿에서 열면 {"detail":"관리자만"} 만 보였다(GM 2026-09-04).
    # 로그인은 됐지만 관리자가 아니거나 관리자 비밀번호가 없는 경우는 화면을 그대로 내고, 화면이 뜬 뒤
    # api/state 가 401 을 주면 admin.html 이 안내 화면으로 바꾼다(배1076 · 시모 admin.html 마운트).
    if not current(erp_session):
        return RedirectResponse("/auth/login?next=/auth/admin", status_code=303)
    with open(_ADMIN_HTML, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/auth/admin/api/state")
def admin_api_state(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u or u["role"] != "admin" or (ADMIN_PW and not _admin_unlocked(erp_admin, u["id"])):
        raise HTTPException(401, "관리자 확인 필요")
    accts = accounts()
    with db() as c:
        rows = c.execute("SELECT * FROM users WHERE tenant_id=%s ORDER BY status='pending' DESC, created_at DESC", (T,)).fetchall()
        hist = c.execute(
            "SELECT h.id, h.uid, h.before, h.after, h.changed_by, h.changed_at, usr.name FROM perms_history h "
            "LEFT JOIN users usr ON usr.tenant_id=h.tenant_id AND usr.id=h.uid "
            "WHERE h.tenant_id=%s ORDER BY h.id DESC LIMIT 20", (T,)).fetchall()

    def _perms(r):
        try:
            return json.loads(r["perms"]) if r["perms"] else None
        except ValueError:
            return None

    return JSONResponse({
        "me": {"id": u["id"], "name": u["name"], "email": u["email"]},
        "users": [{
            "id": r["id"], "name": r["name"], "email": r["email"], "role": r["role"], "status": r["status"],
            "created_at": r["created_at"], "approved_at": r["approved_at"],
            "google": False,   # ponytail: users 표에 구글 전용 여부 열이 없다 — 배지만 안 뜬다, 필요해지면 스키마에 열 추가
            "perms": _perms(r), "fixed_perms": accts.get((r["email"] or "").lower()),
        } for r in rows],
        "modules": modules(),
        "dept_modules": dept_presets(),          # 부서 → 모듈id 전체 목록(공통+전용 이미 합침) · 데이터 파일 있으면 그게 정본
        "common_modules": [],                    # ponytail: 공통/전용 구분은 이제 dept_presets 안에 이미 합쳐 들어간다(배1026)
        "exception_ids": list(EXCEPTION_ONLY_IDS),
        "social": {p: bool(social_creds(p)[0]) for p in SOCIAL},   # 값은 안 준다 — 설정됨/비어있음만(키 유출 방지)
        "history": [{
            "id": h["id"], "uid": h["uid"], "name": h["name"], "changed_by": h["changed_by"],
            "changed_at": h["changed_at"], "before": h["before"], "after": h["after"],
        } for h in hist],
    })


@app.get("/auth/admin/push_approvals")
def admin_push_approvals(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    """🔒 커밋·푸시 승인 현황(읽기 전용 · 배1098 2단계). 결정은 여기서 안 받는다 — GM 개인 봇방
    [승인]/[반려] 카드가 유일한 결정 경로(scripts/push_lock.decide()). 이유 = 관문을 하나로 유지
    (약속 L21) — 서버에 쓰기 API를 두면 결정이 두 곳(카드/화면)으로 갈라져 어긋난다."""
    u = current(erp_session)
    if not u or u["role"] != "admin" or (ADMIN_PW and not _admin_unlocked(erp_admin, u["id"])):
        raise HTTPException(401, "관리자 확인 필요")
    try:
        with open(PUSH_APPROVALS, encoding="utf-8") as f:
            reqs = (json.load(f) or {}).get("requests") or []
    except Exception:
        reqs = []
    reqs = sorted(reqs, key=lambda r: r.get("created_at", ""), reverse=True)
    reqs = sorted(reqs, key=lambda r: r.get("status") != "pending")   # pending 먼저, 나머지는 최신순 유지(stable)
    return JSONResponse({"requests": reqs})


@app.post("/auth/admin/dept_apply/{dept}")
def dept_apply(dept: str, erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin)
    if dept not in DEPT_ONLY_MODULES:
        raise HTTPException(400, "모르는 부서")
    mods = dept_modules(dept)
    with db() as c:
        targets = c.execute("SELECT id, perms FROM users WHERE tenant_id=%s AND role!='admin' AND status='active'", (T,)).fetchall()
    n = 0
    for r in targets:
        p = _row_perms(r)
        if p.get("dept") != dept or p.get("locked"):
            continue
        _set_perms(r["id"], {"dept": dept, "groups": [], "modules": mods, "deny": p.get("deny", [])}, me["email"])
        n += 1
    return RedirectResponse(f"/auth/admin?msg={urllib.parse.quote(dept)} 부서 기본을 {n}명에 적용했습니다#matrix", status_code=303)


# 부서 기본 모듈 표 — GM 콘솔에서 직접 편집(배1026 · GM 2026-09-07). 저장 즉시 dept_modules() 가
# 이 값을 쓴다(가입 승인 프리셋·「부서 기본 한 번에」 버튼 전부 여기 하나로 수렴 — 벌 두 개 금지).
@app.get("/auth/admin/dept_presets")
def admin_dept_presets_get(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u or u["role"] != "admin" or (ADMIN_PW and not _admin_unlocked(erp_admin, u["id"])):
        raise HTTPException(401, "관리자 확인 필요")
    return JSONResponse({
        "presets": dept_presets(), "code_draft": _DEPT_DRAFT,
        "updated": (_presets_raw() or {}).get("_updated"), "modules": modules(),
    })


@app.post("/auth/admin/dept_presets")
async def admin_dept_presets_save(request: Request, erp_session: Optional[str] = Cookie(default=None),
                                  erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin, "/auth/admin")
    form = await request.form()
    ids = {m["id"] for m in modules()}
    out = {d: [v for v in form.getlist(d) if v in ids] for d in DEPTS}   # 모르는 모듈id 는 조용히 버린다(악의 없는 UI만 호출)
    out["_updated"] = {"by": me["email"], "at": now()}
    tmp = DEPT_PRESETS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DEPT_PRESETS)
    global _PRESETS
    _PRESETS = (None, None)                     # 강제 재읽기 — 같은 초 안에 두 번 저장돼도 mtime 비교를 건너뛴다
    return RedirectResponse("/auth/admin?msg=부서 기본 표를 저장했습니다#depts", status_code=303)


# 소셜 로그인 키(배1108) — 관리자 콘솔 저장. 값은 GET(api/state)으로 절대 안 돌려준다(설정됨/비어있음만).
@app.post("/auth/admin/social_keys")
async def admin_social_keys_save(request: Request, erp_session: Optional[str] = Cookie(default=None),
                                 erp_admin: Optional[str] = Cookie(default=None)):
    admin_only(erp_session, erp_admin, "/auth/admin")
    form = await request.form()
    cur = _social_keys_raw()   # 빈 칸("새 값이 있을 때만 입력")은 기존 값을 유지 — 제출분만 덮어쓴다
    out = dict(cur)            # hr_hub_pw 등 provider 아닌 다른 키(예: 인사 허브 비밀번호)는 그대로 보존
    for p in SOCIAL:
        prev = cur.get(p) or {}
        pid = (form.get(f"{p}_id") or "").strip()
        secret = (form.get(f"{p}_secret") or "").strip()
        out[p] = {"id": pid or prev.get("id", ""), "secret": secret or prev.get("secret", "")}
    _save_social_keys(out)
    return RedirectResponse("/auth/admin?msg=소셜 로그인 키를 저장했습니다#screens", status_code=303)


def _save_social_keys(out: dict) -> None:
    """social_keys.json 저장 — provider 키·hr_hub_pw 가 같이 쓰는 파일 하나(관문 두 곳 금지)."""
    tmp = SOCIAL_KEYS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SOCIAL_KEYS_FILE)
    try:
        os.chmod(SOCIAL_KEYS_FILE, 0o600)
    except OSError:
        pass
    global _SOCIAL_KEYS
    _SOCIAL_KEYS = (None, {})                    # 강제 재읽기


# 인사 허브 대조 비밀번호 — 관리자 미니 화면(admin.html 콘솔에는 시토가 나중에 링크만 붙인다).
@app.get("/auth/admin/hr_check")
def admin_hr_check_page(msg: str = "", err: str = "", erp_session: Optional[str] = Cookie(default=None),
                        erp_admin: Optional[str] = Cookie(default=None)):
    admin_only(erp_session, erp_admin, "/auth/admin/hr_check")
    state = "설정됨" if hr_hub_pw() else "비어 있음 — 아이디 가입 신청이 전부 막힙니다"
    return page("인사 허브 대조", head("가입 신청 이름·연락처 대조 · 관리자 전용") + f"""
{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<form method=post action=/auth/admin/hr_check>
<h1>인사 허브 대조 비밀번호</h1>
<p class=hint>현재 상태: {state}</p>
<input type=hidden name=action value=save>
<label>인사 허브 비밀번호<span class=pw><input name=password type=password autocomplete=off placeholder="새 값이 있을 때만 입력">""" + TOGGLE + f"""</span></label>
<button>저장</button></form>
<form method=post action=/auth/admin/hr_check style="margin-top:14px">
<input type=hidden name=action value=test><button class=sec>대조 테스트(명부만 읽어본다 · 이름·전화 표시 안 함)</button></form>
<div class=foot><p><a href=/auth/admin>관리자 화면으로</a></p></div>""")


@app.post("/auth/admin/hr_check")
async def admin_hr_check_save(request: Request, erp_session: Optional[str] = Cookie(default=None),
                              erp_admin: Optional[str] = Cookie(default=None)):
    admin_only(erp_session, erp_admin, "/auth/admin/hr_check")
    form = await request.form()
    if form.get("action") == "test":
        global _HR_ROSTER
        _HR_ROSTER = (0.0, None)                # 강제 재조회
        try:
            roster = hr_roster()
        except Exception as e:
            return RedirectResponse(f"/auth/admin/hr_check?err=대조 테스트 실패: {urllib.parse.quote(str(e)[:80])}", status_code=303)
        fields = sorted({k for row in roster[:5] for k in row.keys()})
        return RedirectResponse(
            f"/auth/admin/hr_check?msg={urllib.parse.quote(f'명부 {len(roster)}명 읽힘 · 필드: ' + (', '.join(fields) or '없음'))}",
            status_code=303)
    pw = (form.get("password") or "").strip()
    if pw:
        _save_social_keys({**_social_keys_raw(), "hr_hub_pw": pw})
    return RedirectResponse("/auth/admin/hr_check?msg=저장했습니다", status_code=303)


@app.post("/auth/admin/undo/{hid}")
def undo_perms(hid: int, erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin)
    with db() as c:
        h = c.execute("SELECT * FROM perms_history WHERE tenant_id=%s AND id=%s", (T, hid)).fetchone()
    if not h:
        raise HTTPException(404)
    with db() as c:
        c.execute("UPDATE users SET perms=%s WHERE tenant_id=%s AND id=%s", (h["before"], T, h["uid"]))
    _perms_log(h["uid"], h["after"], h["before"], me["email"] + "(되돌리기)")
    return RedirectResponse("/auth/admin?msg=되돌렸습니다#matrix", status_code=303)


# 권한 저장 — 화면(admin.html)은 콘솔 안 서랍에서 이 하나만 호출한다. 개별 GET 화면은 배1076 에서 admin.html 로 흡수.
@app.post("/auth/admin/{uid}/perms")
async def perms_save(uid: int, request: Request, erp_session: Optional[str] = Cookie(default=None),
                     erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin, "/auth/admin")
    form = await request.form()
    ids = {m["id"] for m in modules()}
    if form.get("preset") in DEPT_ONLY_MODULES:
        dept = form["preset"]
        _set_perms(uid, {"dept": dept, "groups": [], "modules": dept_modules(dept), "deny": []}, me["email"])
        return RedirectResponse(f"/auth/admin?msg={dept} 부서 기본을 넣었습니다", status_code=303)
    perms = None if form.get("reset") else {
        "groups": [g for g in form.getlist("g") if g in GROUPS],
        "modules": [m for m in form.getlist("m") if m in ids],
        "deny": [m for m in form.getlist("d") if m in ids]}
    _set_perms(uid, perms, me["email"])
    return RedirectResponse("/auth/admin?msg=저장됐습니다", status_code=303)


# /auth/admin/{uid}/{action} 범용 라우트보다 먼저 선언해야 "lock" 이 그 400 처리로 안 빠진다.
@app.post("/auth/admin/{uid}/lock")
def toggle_lock(uid: int, erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin)
    with db() as c:
        row = c.execute("SELECT perms FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
    if not row:
        raise HTTPException(404)
    try:
        p = json.loads(row["perms"]) if row["perms"] else {}
    except ValueError:
        p = {}
    p["locked"] = not p.get("locked")
    _set_perms(uid, p, me["email"])
    return RedirectResponse("/auth/admin?msg=잠금 상태를 바꿨습니다#matrix", status_code=303)


@app.post("/auth/admin/{uid}/{action}")
def admin_action(uid: int, action: str, erp_session: Optional[str] = Cookie(default=None),
                 erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin)
    if action not in ("approve", "block", "toggle_role", "delete"):
        raise HTTPException(400)
    if action == "delete":
        # 사용 중·관리자·본인은 못 지운다 — 잘못 온 신청·차단 계정 정리 전용(GM 2026-09-04).
        with db() as c:
            c.execute("DELETE FROM users WHERE tenant_id=%s AND id=%s AND role!='admin' AND status!='active' AND id!=%s",
                      (T, uid, me["id"]))
        return RedirectResponse("/auth/admin", status_code=303)
    if action == "toggle_role":
        if uid == me["id"]:
            raise HTTPException(400, "본인 역할은 바꿀 수 없습니다")
        with db() as c:
            row = c.execute("SELECT role FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
            if row:
                c.execute("UPDATE users SET role=%s WHERE tenant_id=%s AND id=%s",
                          ("staff" if row["role"] == "admin" else "admin", T, uid))
        return RedirectResponse("/auth/admin", status_code=303)
    with db() as c:
        c.execute("UPDATE users SET status=%s, approved_at=%s WHERE tenant_id=%s AND id=%s AND role!='admin'",
                  ("active" if action == "approve" else "blocked", now() if action == "approve" else None, T, uid))
    return RedirectResponse("/auth/admin", status_code=303)


init()


if __name__ == "__main__":                     # 회사 계정 판별 자가점검: python app.py
    # 오픈 리다이렉트 차단(2026-09-05 검수 M2)
    assert safe_next("/erp/") == "/erp/"
    assert safe_next("//evil.example") == "/"                 # '/' 로 시작하지만 '//' 는 외부 도메인으로 튄다
    assert safe_next("evil.example") == "/"                    # '/' 로 시작 안 함
    assert safe_next("//evil.example", "/auth/admin") == "/auth/admin"
    # 폴더 index.html 모듈 권한 판정(2026-09-05 검수 H2) — /chro/hub 든 /chro/hub/ 든 같은 모듈로 잡혀야 한다.
    # MODULES 를 없는 경로로 돌려 modules()의 os.stat 이 항상 실패하게 만든다 — 그래야 실제
    # /srv/erp/www/erp/modules.json 이 있는 서버에서도 이 임시 _MODS 가 재로딩으로 덮이지 않는다.
    _real_modules_path, MODULES = MODULES, "/__selftest_no_such_modules_json__"
    _MODS = (None, [], {"/chro/hub/index.html": {"id": "chro-hub-index"}, "/check.html": {"id": "check"}})
    assert module_at("/chro/hub/")["id"] == "chro-hub-index"
    assert module_at("/chro/hub")["id"] == "chro-hub-index"
    assert module_at("/check")["id"] == "check"                # 기존 .html 생략 보정은 그대로
    assert module_at("/check.html")["id"] == "check"
    assert module_at("/없는경로/") is None
    MODULES = _real_modules_path
    _MODS = (None, [], {})                                     # 다음 modules() 호출이 실제 파일에서 다시 읽도록 리셋

    ok = {"email": "cao@wellperion.com", "email_verified": True, "hd": "wellperion.com"}
    assert is_company_account(ok)
    assert not is_company_account({**ok, "hd": None})                        # 개인 gmail
    assert not is_company_account({**ok, "email": "x@gmail.com"})            # hd 만 위조된 경우
    assert not is_company_account({**ok, "email_verified": False})
    # 개인 구글 계정 — hd 없이도 통과해야 가입 폼으로 넘어간다(GM 2026-09-05)
    personal = {"email": "someone@gmail.com", "email_verified": True}
    assert is_valid_google_account(personal) and not is_company_account(personal)
    assert not is_valid_google_account({"email": "x@gmail.com", "email_verified": False})
    # 권한 판정 자가점검 — dict 가 DictRow 흉내(keys()·[] 둘 다 된다). user 는 email 이 있어야 perms_of() 가 안 죽는다.
    admin_u = {"role": "admin", "email": "cao@wellperion.com", "perms": None}
    staff_u = {"role": "staff", "email": "staff@example.invalid", "perms": None}
    member_mod = {"id": "member", "group": "시포", "core": True}                 # 핵심 모듈(roles 칸 삭제 · 배1026)
    dept_module = {"id": "check", "group": "시우", "core": False}                # 일반 부서 모듈(core 아님)
    assert allowed(admin_u, member_mod)                     # admin=항상 전부
    assert allowed(staff_u, member_mod)                     # 기본(perms 없음)이라도 core 모듈은 전 직원에게 보인다(배978)
    assert not allowed(staff_u, dept_module)                # 기본(perms 없음) = core 모듈만, 부서 모듈은 안 보임
    perms_core = {**staff_u, "perms": '{"groups":["핵심"]}'}
    assert allowed(perms_core, member_mod)                  # 핵심 그룹 = core 모듈 전부 허용
    assert not allowed(perms_core, dept_module)             # 부서 전용 모듈은 그룹이 안 맞으면 그대로 막힘
    perms_deny = {**staff_u, "perms": '{"groups":["시우"],"deny":["check"]}'}
    assert not allowed(perms_deny, dept_module)             # deny 가 groups 매칭보다 우선
    # 부서 가입 perms(dept 키 포함) — allowed() 는 groups/modules/deny/all 만 보므로 dept 는 무해해야 한다
    dept_perms = {**staff_u, "perms": json.dumps({"dept": "운영부", "groups": [], "modules": dept_modules("운영부"), "deny": []})}
    assert allowed(dept_perms, member_mod) and allowed(dept_perms, dept_module)
    assert all(d in DEPT_ONLY_MODULES for d in DEPTS)                            # 가입 폼 선택지 = 부서 템플릿 정의됨
    # 개인 예외(배1026 §3) — 부서 기본에 들어 있어도 EXCEPTION_ONLY_IDS 는 groups/all 매칭을 건너뛴다.
    gm_work = {"id": "coo-chairman-gm업무", "group": "시우", "core": False}       # 폴더는 coo 지만 GM 전용
    assert gm_work["id"] in EXCEPTION_ONLY_IDS
    assert not allowed(dept_perms, gm_work)                 # 운영부 부서기본(시우 그룹 매칭)로는 GM 업무가 안 열린다
    exception_granted = {**staff_u, "perms": json.dumps({"groups": [], "modules": [gm_work["id"]], "deny": []})}
    assert allowed(exception_granted, gm_work)              # modules 로 콕 집으면(개인 예외 부여) 열린다
    all_true = {**staff_u, "perms": json.dumps({"all": True, "deny": []})}
    assert not allowed(all_true, gm_work)                   # all:true(부서 메인 계정)로도 개인 예외는 안 열린다
    # 네이버·카카오(배1108) — 계정 키 규칙: 카카오 이메일 없으면 kakao_{id}@kakao.login, 네이버는 이메일 필수.
    assert _social_identity("naver", {"response": {"email": "A@Test.com", "name": "홍길동"}}) == ("a@test.com", "홍길동")
    try:
        _social_identity("naver", {"response": {}})
        assert False, "네이버 이메일 없으면 ValueError 여야 한다"
    except ValueError:
        pass
    assert _social_identity("kakao", {"id": 123, "kakao_account": {}}) == ("kakao_123@kakao.login", "kakao_123")
    assert _social_identity("kakao", {"id": 123, "kakao_account": {"email": "B@Test.com",
                             "profile": {"nickname": "닉네임"}}}) == ("b@test.com", "닉네임")
    assert set(SOCIAL) == {"naver", "kakao"}
    # 아이디 가입 규칙(배1108 후속) — 영문 소문자·숫자·.·_ 4~20자.
    assert valid_username("hong.gd01")
    assert not valid_username("Hong.GD")            # 대문자 금지
    assert not valid_username("abc")                # 4자 미만
    assert not valid_username("a" * 21)              # 20자 초과
    assert not valid_username("hong gd")             # 공백 금지
    # 인사 명부 대조(순수 함수 — 가짜 리스트로 검증) — 이름 공백무시 완전일치 + 전화 숫자만 완전일치.
    roster = [
        {"성명": "홍 길동", "연락처": "010-1234-5678", "재직 상태": "재직"},
        {"이름": "김철수", "연락처": "01099998888", "재직상태": "퇴직"},
        {"성명": "이영희", "연락처": "010-0000-1111", "재직 상태": "재직"},
    ]
    assert hr_match("홍길동", "010-1234-5678", roster)          # 공백·하이픈 무시하고 일치
    assert not hr_match("홍길동", "010-9999-9999", roster)      # 이름 맞아도 전화 다르면 불일치(동명이인 보호)
    assert not hr_match("김철수", "010-9999-8888", roster)      # 재직상태=퇴직이면 불일치
    assert not hr_match("없는사람", "010-0000-0000", roster)    # 명부에 없음
    assert not hr_match("", "", roster)
    # 사무실 자동 로그인 세션 표시(배1134) — 일반 로그인은 claim 이 없고, 자동 로그인만 auto=true.
    fake_user = {"id": 1, "email": OFFICE_AUTO_LOGIN_ACCOUNT, "role": "staff"}
    assert not is_auto_token(issue(fake_user))
    assert is_auto_token(issue(fake_user, auto=True))
    assert not is_auto_token(None)
    assert not is_auto_token("깨진토큰")
    print("self-check ok")
