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
    GET  /auth/admin                  — 승인 대기 목록 (관리자만)
    GET/POST /auth/admin/{uid}/perms  — 계정별 권한(그룹·모듈 허용/거부)
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


def dept_modules(dept: str) -> list:
    return DEPT_COMMON_MODULES + DEPT_ONLY_MODULES.get(dept, [])


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
SESSION_DAYS = 30
KST = timezone(timedelta(hours=9))
LOCK_AFTER = 5                                 # 연속 실패 허용 횟수
LOCK_SECS = 600                                # 잠금 시간(10분)
# 관리자 화면 별도 비밀번호(GM 2026-09-04 "관리자 사이트 비밀번호는 별도로") — 로그인 계정과 무관하게 한 번 더 묻는다.
# 값은 서버 /srv/erp/auth.env 에만 있다. 비어 있으면 종전대로(관리자 계정이면 바로 열림).
ADMIN_PW = os.environ.get("ERP_ADMIN_SITE_PW", "")
ADMIN_COOKIE = "erp_admin"
ADMIN_MIN = 30                                 # 관리자 비밀번호 한 번 넣으면 30분 유효
GOOGLE_ID = os.environ.get("GOOGLE_CLIENT_ID", "")      # 없으면 구글 로그인 라우트가 안내만 낸다
GOOGLE_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_HD = "wellperion.com"                   # 회사 워크스페이스 도메인 — 개인 gmail 차단
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
def issue(user) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    return jwt.encode({"uid": user["id"], "email": user["email"], "role": user["role"], "exp": exp}, SECRET, algorithm="HS256")


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
    path = "/" + posixpath.normpath(urllib.parse.unquote(urllib.parse.urlsplit(uri).path) or "/").lstrip("/")
    # 깔끔한 주소(.html 생략) 허용 — nginx try_files 가 $uri.html 로 파일을 찾으므로 권한 판정도 같은 파일로(GM 2026-09-05)
    return _MODS[2].get(path) or (_MODS[2].get(path + ".html") if not path.endswith(".html") else None)


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
    ".g{display:block;margin:12px 0 0;padding:11px;text-align:center;font-weight:700;color:var(--ink);text-decoration:none;"
    "border:1px solid var(--line-strong);border-radius:8px}.g:hover{background:var(--accent-soft);border-color:var(--accent)}"
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


@app.get("/auth/login")
def login_page(next: str = "/", err: str = "", msg: str = ""):
    dest = {"/auth/admin": "계정 관리", "/auth/password": "비밀번호 변경"}.get(next)
    hint = f"<p class=hint>로그인하면 <b>{escape(dest)}</b> 화면으로 이동합니다</p>" if dest else ""
    return page("웰페리온 ERP 로그인", head("직원용 업무 화면 · 구글 계정 또는 회사 이메일로 로그인") + f"""<form method=post action=/auth/login>
<h1>로그인</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}{hint}
<label>회사 이메일<input name=email type=email autocomplete=username placeholder="이름@wellperion.com" required autofocus></label>
<label>비밀번호<span class=pw><input name=password type=password autocomplete=current-password required>""" + TOGGLE + f"""</span></label>
<input type=hidden name=next value="{escape(next)}"><button>로그인</button>
{'<a class=g href="/auth/google?next=' + escape(next) + '">구글 계정으로 로그인</a>' if GOOGLE_ID else ''}
<div class=foot><p>구글 로그인이 처음이면 이름·부서만 알려주세요 — 승인은 GM 이 합니다.</p>
<p>계정이 없으면 <a href=/auth/signup>가입 신청</a> · 비밀번호를 잊으셨으면 GM 께 말씀해 주세요.</p></div></form>""")


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
    r = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"     # nginx 만 보냄 · http(IP접속)는 종전대로 secure 없음
    r.set_cookie(COOKIE, issue(u), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/", secure=https)
    return r


@app.get("/auth/signup")
def signup_page(msg: str = ""):
    return page("웰페리온 ERP 가입 신청", head("직원용 업무 화면 · 가입 신청") + f"""<form method=post action=/auth/signup>
<h1>가입 신청</h1>{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<label>이름<input name=name placeholder="직함 포함, 예: 홍길동 매니저" autocomplete=name required></label>
<label>회사 이메일 (@wellperion.com)<input name=email type=email autocomplete=email placeholder="이름@wellperion.com" required></label>
<label>비밀번호<input name=password type=password placeholder="8자 이상" minlength=8 autocomplete=new-password required></label>
<button>신청</button><div class=foot><p>신청하면 GM 께 알림이 가고, 승인되면 그 계정으로 로그인할 수 있습니다.</p>
<p>이미 계정이 있으면 <a href=/auth/login>로그인</a></p></div></form>""")


@app.post("/auth/signup")
def signup(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if not email.endswith("@" + GOOGLE_HD):
        return RedirectResponse("/auth/signup?msg=회사 계정(@wellperion.com)만 신청할 수 있습니다", status_code=303)
    salt, h = hash_pw(password)
    try:
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,created_at,perms) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                      (T, email, name.strip(), salt, h, now(), None))
    except _db.IntegrityError:
        return RedirectResponse("/auth/signup?msg=이미 신청된 이메일입니다", status_code=303)
    tell_gm(f"🔐 ERP 가입 신청 — {name.strip()} ({email})\n승인: http://15.164.151.105/auth/admin")
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


# ── 구글 계정 로그인 ────────────────────────────────────────────────────
# 회사 워크스페이스(@wellperion.com) 계정 = GM 승인 없이 바로 통과(GM 지시 2026-09-03).
# 개인 구글 계정 = 이름·부서 선택 후 GM 승인 대기(GM 지시 2026-09-05 · 역할별 회사계정 1개 방식 폐기).
# id_token 은 우리 클라이언트 시크릿으로 구글에서 직접(TLS) 받아오므로 서명 재검증 없이 payload 를 읽는다.
def _redirect_uri(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/auth/google/callback"


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
    state = jwt.encode({"n": next if next.startswith("/") else "/", "exp": int(time.time()) + 600},
                       SECRET, algorithm="HS256")
    # hd 파라미터 없음 = 계정 선택창에 개인 구글 계정도 뜬다(GM 2026-09-05). 회사 계정 여부는 콜백에서 판별.
    q = urllib.parse.urlencode({"client_id": GOOGLE_ID, "redirect_uri": _redirect_uri(request),
                                "response_type": "code", "scope": "openid email profile",
                                "state": state, "prompt": "select_account"})
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + q, status_code=302)


@app.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if not GOOGLE_ID or not GOOGLE_SECRET:
        return RedirectResponse("/auth/login?err=구글 로그인이 아직 설정되지 않았습니다", status_code=303)
    if error or not code:
        return RedirectResponse("/auth/login?err=구글 로그인이 취소됐습니다", status_code=303)
    try:
        nxt = jwt.decode(state, SECRET, algorithms=["HS256"])["n"]
    except jwt.PyJWTError:
        return RedirectResponse("/auth/login?err=로그인 요청이 만료됐습니다. 다시 시도하세요", status_code=303)
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


@app.get("/auth/google/finish")
def google_finish_page(t: str = "", next: str = "/", err: str = ""):
    """개인 구글 계정 첫 로그인 — 이름 확인 + 부서 선택. t 는 600초짜리 서명 토큰(이메일·구글이 준 이름)."""
    try:
        claims = jwt.decode(t, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return RedirectResponse("/auth/login?err=인증이 만료됐습니다. 처음부터 다시 로그인하세요", status_code=303)
    opts = "".join(f"<option value='{escape(d)}'>{escape(d)}</option>" for d in DEPTS)
    return page("가입 완료", head("구글 로그인 확인 · 이름과 부서만 알려주세요") + f"""<form method=post action=/auth/google/finish>
<h1>가입 완료</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<p class=hint>{escape(claims['e'])} 계정으로 계속합니다.</p>
<label>이름<input name=name value="{escape(claims['n'])}" placeholder="직함 포함, 예: 홍길동 매니저" required></label>
<label>부서<select name=dept required><option value=''>선택하세요</option>{opts}</select></label>
<input type=hidden name=t value="{escape(t)}"><input type=hidden name=next value="{escape(next)}">
<button>신청</button><div class=foot><p>신청하면 GM 께 알림이 가고, 승인되면 부서 화면으로 로그인할 수 있습니다.</p></div></form>""")


@app.post("/auth/google/finish")
def google_finish(name: str = Form(...), dept: str = Form(...), t: str = Form(...), next: str = Form("/")):
    try:
        claims = jwt.decode(t, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return RedirectResponse("/auth/login?err=인증이 만료됐습니다. 처음부터 다시 로그인하세요", status_code=303)
    if dept not in DEPTS:
        return RedirectResponse(f"/auth/google/finish?t={t}&next={urllib.parse.quote(next, safe='')}&err=부서를 선택하세요", status_code=303)
    email, salt_pw = claims["e"], secrets.token_urlsafe(32)     # 구글 전용 계정 — 비밀번호 로그인은 못 쓴다
    salt, h = hash_pw(salt_pw)
    perms = json.dumps({"dept": dept, "groups": [], "modules": dept_modules(dept), "deny": []}, ensure_ascii=False)
    try:
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,created_at,perms) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                      (T, email, name.strip(), salt, h, now(), perms))
    except _db.IntegrityError:
        pass                                    # 중복 제출 — 이미 신청돼 있으니 그대로 대기 안내만
    tell_gm(f"🔐 ERP 가입 신청 — {name.strip()} ({email} · {dept})\n승인: http://15.164.151.105/auth/admin")
    return RedirectResponse("/auth/login?msg=신청됐습니다. GM 승인 후 로그인할 수 있습니다", status_code=303)


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
<input type=hidden name=next value="{escape(next if next.startswith('/') else '/auth/admin')}"><button>확인</button>
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
    r = RedirectResponse(next if next.startswith("/") else "/auth/admin", status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(ADMIN_COOKIE, _admin_issue(u["id"]), max_age=ADMIN_MIN * 60, httponly=True, samesite="lax", path="/auth/admin", secure=https)
    return r


def _admin_row(r, me_id: int) -> str:
    approve_or_block = ""
    if r["role"] != "admin":
        if r["status"] != "active":
            approve_or_block = f"<form method=post action=/auth/admin/{r['id']}/approve><button>승인</button></form>"
        else:
            approve_or_block = f"<form method=post action=/auth/admin/{r['id']}/block><button class=sec>차단</button></form>"
    role_btn = "" if r["id"] == me_id else (
        f"<form method=post action=/auth/admin/{r['id']}/toggle_role>"
        f"<button class=sec>{'관리자로' if r['role'] != 'admin' else '일반으로'}</button></form>")
    status_ko = {"active": "사용 중", "pending": "승인 대기", "blocked": "차단"}.get(r["status"], r["status"])
    status_cls = {"active": " ok", "pending": " on", "blocked": " off"}.get(r["status"], "")
    role_ko = "관리자" if r["role"] == "admin" else "직원"
    perm_link = "" if r["role"] == "admin" else f"<a href=/auth/admin/{r['id']}/perms>권한</a>"
    # 삭제 = 사용 중이 아닌 직원 계정만(잘못 온 신청·시험 계정 정리 · GM 2026-09-04). 사용 중은 먼저 차단.
    delete = "" if (r["role"] == "admin" or r["status"] == "active" or r["id"] == me_id) else _delete_form(r)
    return (f"<tr{' class=pend' if r['status'] == 'pending' else ''}><td data-l=계정><b>{escape(r['name'])}</b>{_dept_badge(r)}<br><small>{escape(r['email'])}</small></td>"
            f"<td data-l=역할><span class=tag>{role_ko}</span></td><td data-l=상태><span class='tag{status_cls}'>{status_ko}</span></td>"
            f"<td data-l=신청><small>{short_dt(r['created_at'])}</small></td><td data-l=승인><small>{short_dt(r['approved_at'])}</small></td>"
            f"<td><div class=acts>{approve_or_block}{delete}{perm_link}{role_btn}</div></td></tr>")


def _dept_badge(r) -> str:
    """가입 폼에서 고른 부서(perms JSON 의 dept 키) — account_perms.json/관리자 화면 저장분엔 없어 조용히 빈칸."""
    try:
        p = json.loads(r["perms"]) if r["perms"] else None
    except ValueError:
        p = None
    d = (p or {}).get("dept")
    return f" <span class=tag>{escape(d)}</span>" if d else ""


def _delete_form(r) -> str:
    q = escape(r["name"]).replace("'", "")
    return (f"<form method=post action=/auth/admin/{r['id']}/delete onsubmit=\"return confirm('{q} 계정을 지웁니다. 되돌릴 수 없습니다.')\">"
            f"<button class=danger>삭제</button></form>")


def _row_perms(r) -> dict:
    try:
        return json.loads(r["perms"]) if r["perms"] else {}
    except ValueError:
        return {}


# ── 권한 매트릭스 (배1026 §4-2 · 2026-09-05) — 기존 /auth/admin 화면에 얹는다(새 페이지 아님) ──────
# 칸 = 그룹(회원·운영·점검·경영·문서함) 안에서 지금 열려 있는 화면 수. 세부(모듈 하나하나 허용/거부)는
# 이미 있는 /auth/admin/{uid}/perms 로 간다 — 사람×그룹 25칸을 전부 인라인 편집 가능하게 만들면
# (사람 수 × 5그룹 × 모듈수) 폼이라 페이지가 못 쓸 만큼 무거워진다. ponytail: 그룹 단위 요약 + 링크로 세부조정.
APPGROUPS = ("회원", "운영", "점검", "경영", "문서함")


def _matrix_row(r) -> str:
    p = _row_perms(r)
    dept = p.get("dept") or "미분류"
    ms = modules()
    cells = "".join(
        f"<td data-l='{escape(g)}'>{sum(1 for m in ms if m.get('appgroup', '문서함') == g and allowed(r, m))}"
        f"/{sum(1 for m in ms if m.get('appgroup', '문서함') == g)}</td>"
        for g in APPGROUPS)
    find = escape((r["name"] + " " + r["email"] + " " + dept).lower())
    lock_label = "잠금 해제" if p.get("locked") else "잠금"
    return (f"<tr data-find='{find}'><td data-l=이름><b>{escape(r['name'])}</b> <span class=tag>{escape(dept)}</span>"
            f"<br><small>{escape(r['email'])}</small></td>{cells}"
            f"<td data-l=관리><div class=acts><a href=/auth/admin/{r['id']}/perms>세부조정</a>"
            f"<form method=post action=/auth/admin/{r['id']}/lock><button class=sec>{lock_label}</button></form></div></td></tr>")


def _matrix_section() -> str:
    with db() as c:
        staff_rows = c.execute(
            "SELECT * FROM users WHERE tenant_id=%s AND role!='admin' AND status='active' ORDER BY name", (T,)).fetchall()
        hist = c.execute(
            "SELECT h.id, h.changed_by, h.changed_at, u.name FROM perms_history h "
            "LEFT JOIN users u ON u.tenant_id=h.tenant_id AND u.id=h.uid "
            "WHERE h.tenant_id=%s ORDER BY h.id DESC LIMIT 20", (T,)).fetchall()
    trs = "".join(_matrix_row(r) for r in staff_rows)
    th5 = "".join(f"<th>{escape(g)}</th>" for g in APPGROUPS)
    dept_btns = "".join(
        f"<form method=post action=/auth/admin/dept_apply/{urllib.parse.quote(d)}>"
        f"<button class=sec>{escape(d)} 기본 적용</button></form>" for d in DEPT_ONLY_MODULES)
    last = f"마지막 저장 {short_dt(hist[0]['changed_at'])} · {escape(hist[0]['changed_by'])}" if hist else "저장 이력 없음"
    hist_rows = "".join(
        f"<tr><td><small>{short_dt(h['changed_at'])}</small></td><td>{escape(h['name'] or ('#%s' % h['changed_by']))}</td>"
        f"<td><small>{escape(h['changed_by'])}</small></td>"
        f"<td><form method=post action=/auth/admin/undo/{h['id']}><button class=sec>되돌리기</button></form></td></tr>"
        for h in hist)
    return f"""<div class='box wide' id=matrix><h1>권한 매트릭스</h1>
<p class=muted>칸 = 그 그룹 안에서 지금 열려 있는 화면 수(허용/전체). 개인 예외 화면(월간운영계획·GM 업무·
인사·재무·채용·매출회원보고·자율현황·카톡전송관리)은 부서 기본에 없어 경영 칸은 대개 0 — 그 사람만 콕 집어
열려면 세부조정으로 간다. 읽기전용(보기만) 구분은 화면에 아직 없어 허용/차단 2단계만 있다.</p>
<input class=find id=mfind type=search placeholder="이름·계정·부서로 찾기" autocomplete=off>
<p class=acts>부서 기본 일괄 적용(잠금 걸린 사람은 건너뜀): {dept_btns}</p>
<div class=tw><table id=mtable><thead><tr><th>사람</th>{th5}<th>관리</th></tr></thead><tbody>{trs}</tbody></table></div>
<h2 style='font-size:15px;margin:24px 0 8px'>변경 이력(최근 20건) · {escape(last)}</h2>
<div class=tw><table><thead><tr><th>시각</th><th>대상</th><th>누가</th><th></th></tr></thead><tbody>{hist_rows}</tbody></table></div>
<script>document.getElementById('mfind').addEventListener('input',function(){{
var q=this.value.trim().toLowerCase();
document.querySelectorAll('#mtable tbody tr').forEach(function(tr){{tr.hidden=!!q&&tr.dataset.find.indexOf(q)<0;}});}});</script>
</div>"""


@app.get("/auth/admin")
def admin(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None), msg: str = ""):
    # 미로그인이면 로그인 화면으로 보낸다 — 새 창·시크릿에서 열면 {"detail":"관리자만"} 만 보였다(GM 2026-09-04).
    if not current(erp_session):
        return RedirectResponse("/auth/login?next=/auth/admin", status_code=303)
    me = admin_only(erp_session, erp_admin)
    with db() as c:
        rows = c.execute("SELECT * FROM users WHERE tenant_id=%s ORDER BY status='pending' DESC, created_at DESC", (T,)).fetchall()
    tr = "".join(_admin_row(r, me["id"]) for r in rows)
    th = "<thead><tr><th>계정</th><th>역할</th><th>상태</th><th>신청</th><th>승인</th><th>작업</th></tr></thead>"
    pend = [r for r in rows if r["status"] == "pending"]
    n_on = sum(1 for r in rows if r["status"] == "active")
    n_off = sum(1 for r in rows if r["status"] == "blocked")
    if pend:
        items = "".join(
            f"<div class=row><div><b>{escape(r['name'])}</b>{_dept_badge(r)} <small>{escape(r['email'])}</small><br><small>신청 {short_dt(r['created_at'])}</small></div>"
            f"<div class=act><form method=post action=/auth/admin/{r['id']}/approve><button>승인</button></form>{_delete_form(r)}</div></div>"
            for r in pend)
        card = f"<div class=card><h2>승인 대기 {len(pend)}건 — 지금 처리할 것</h2>{items}</div>"
    else:
        card = "<p class=muted>승인 대기 없음 — 새 가입 신청이 오면 여기 먼저 뜹니다.</p>"
    summary = f"<p class=muted>전체 {len(rows)} · 사용 중 {n_on} · 차단 {n_off}</p>"
    return page("ERP 계정 관리", head("관리자 · 누가 ERP 에 들어올 수 있는지 정하는 곳", wide=True) +
                f"<div class='box wide'><h1>계정 관리</h1>{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}"
                f"{card}{summary}<div class=tw><table>{th}<tbody>{tr}</tbody></table></div>"
                f"<p class=nav><a href=/erp/>ERP 로 돌아가기</a><a href=/auth/password>비밀번호 변경</a><a href=/auth/logout>로그아웃</a></p></div>"
                + _matrix_section())


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


# 권한 화면 — 아래 범용 POST /auth/admin/{uid}/{action} 보다 먼저 선언해야 perms POST 가 잡힌다
def _perms_row(group: str, ms: list, u, p: Optional[dict]) -> str:
    on = p is not None and group in p.get("groups", [])
    items = "".join(
        f"<div><label style='display:inline;margin-right:14px'>"
        f"<input type=checkbox name=m value='{m['id']}' style='display:inline;width:auto;margin:0 4px 0 0'"
        f"{' checked' if p is not None and m['id'] in p.get('modules', []) else ''}>허용</label>"
        f"<label style='display:inline;margin-right:14px'>"
        f"<input type=checkbox name=d value='{m['id']}' style='display:inline;width:auto;margin:0 4px 0 0'"
        f"{' checked' if p is not None and m['id'] in p.get('deny', []) else ''}>거부</label>"
        f"{escape(m['name'])} <small>{'· 지금 ' + ('보임' if allowed(u, m) else '안 보임')}</small></div>"
        for m in ms)
    return (f"<tr><td><b>{escape(group)}</b><br><small>{len(ms)}개</small></td>"
            f"<td><label style='display:inline'><input type=checkbox name=g value='{escape(group)}'"
            f" style='display:inline;width:auto;margin:0 4px 0 0'{' checked' if on else ''}>그룹 전체 허용</label></td>"
            f"<td><details><summary>모듈별</summary>{items}</details></td></tr>")


@app.get("/auth/admin/{uid}/perms")
def perms_page(uid: int, erp_session: Optional[str] = Cookie(default=None), msg: str = "",
               erp_admin: Optional[str] = Cookie(default=None)):
    admin_only(erp_session, erp_admin, f"/auth/admin/{uid}/perms")
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
    if not u:
        raise HTTPException(404)
    p = perms_of(u)
    ms = modules()
    rows = "".join(_perms_row(g, [m for m in ms if (m.get("core") if g == "핵심" else m.get("group") == g)], u, p)
                   for g in GROUPS)
    fixed = (u["email"] or "").lower() in accounts()
    mode = ("관리자 — 전부 허용" if u["role"] == "admin"
            else "계정 권한 파일(account_perms.json)" if fixed else ("개별 설정" if p else "기본 = 핵심 화면만"))
    return page("계정 권한", f"""<div class='box wide'><h1>권한 — {escape(u['name'])} <small>{escape(u['email'])}</small></h1>
{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<p>현재: <span class=tag>{mode}</span> · 허용 {len(allowed_ids(u))}/{len(ms)}개. 저장하면 개별 설정으로 바뀝니다(거부가 허용보다 우선).</p>
{'<p class=err>이 계정은 <b>account_perms.json</b> 이 정본입니다 — 여기서 저장해도 반영되지 않습니다. 저장소 파일을 고치고 배포하세요.</p>' if fixed else ''}
<form method=post action=/auth/admin/{uid}/perms style='max-width:none;padding:0;border:0;background:none'>
<p>부서 기본(모듈 정본): {' '.join(f"<button class=sec name=preset value='{escape(k)}'>{escape(k)}</button>" for k in DEPT_ONLY_MODULES)}</p>
<p class=hint>개인 예외 화면(월간운영계획·GM 업무·인사·재무·채용·매출회원보고·자율현황·카톡전송관리)은 부서 기본에 없다 — 아래 그룹 표에서 그 모듈만 콕 집어 허용에 체크한다.</p>
<div class=tw><table><tr><th>그룹</th><th>전체</th><th>모듈</th></tr>{rows}</table></div>
<button>저장</button><button class=sec name=reset value=1>기본(핵심만)으로 되돌리기</button></form>
<p class=nav><a href=/auth/admin>계정 관리로</a></p></div>""")


@app.post("/auth/admin/{uid}/perms")
async def perms_save(uid: int, request: Request, erp_session: Optional[str] = Cookie(default=None),
                     erp_admin: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session, erp_admin, f"/auth/admin/{uid}/perms")
    form = await request.form()
    ids = {m["id"] for m in modules()}
    if form.get("preset") in DEPT_ONLY_MODULES:
        dept = form["preset"]
        _set_perms(uid, {"dept": dept, "groups": [], "modules": dept_modules(dept), "deny": []}, me["email"])
        return RedirectResponse(f"/auth/admin/{uid}/perms?msg={dept} 부서 기본을 넣었습니다", status_code=303)
    perms = None if form.get("reset") else {
        "groups": [g for g in form.getlist("g") if g in GROUPS],
        "modules": [m for m in form.getlist("m") if m in ids],
        "deny": [m for m in form.getlist("d") if m in ids]}
    _set_perms(uid, perms, me["email"])
    return RedirectResponse(f"/auth/admin/{uid}/perms?msg=저장됐습니다", status_code=303)


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
    print("self-check ok")
