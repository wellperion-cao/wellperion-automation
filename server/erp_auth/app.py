"""웰페리온 ERP 로그인 관문 (AWS 서버 · FastAPI · PostgreSQL).

역할
    가입 신청 → GM(관리자) 승인 → 로그인 → 쿠키(JWT) → nginx 가 쿠키 없는 요청에 페이지를 주지 않는다.
    GitHub Pages 의 gate.js '커튼'(비밀번호가 소스에 노출)을 진짜 잠금으로 바꾸는 첫 조각이다(배101).

경로
    GET  /auth/login   /auth/signup   — 화면
    POST /auth/login   /auth/signup   /auth/logout
    GET  /auth/check                  — nginx auth_request 용 (200 통과 / 401 로그인 필요 / 403 권한 없음)
    GET  /auth/me                     — 로그인 사용자 + allowed_ids(허용 모듈 id · 앱 셸이 카드 표시에 씀)
    GET  /auth/forbidden              — 권한 없음 화면(nginx 내부 재작성 전용 · 밖에서는 404)
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


# ── 직급 → 권한 층 (GM 지시 2026-09-11 「팀장과 팀원의 권한은 차별을 둬야해, 그래서 직급도 받아야해」) ──
# 정본 = ssot/ranks.json 한 곳. 화면·코드에 직급 이름을 박지 않는다(약속 L01).
# 서버는 /srv/erp/repo(매분 내려받는 저장소 체크아웃)를, 로컬은 이 저장소를 본다.
_RANKS_PATHS = ("/srv/erp/repo/ssot/ranks.json",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "ssot", "ranks.json"))
_RANKS: tuple = (None, None)


def ranks_raw() -> dict:
    """ranks.json 그대로. 못 읽으면 빈 dict — 직급 칸이 비어도 가입 자체는 막지 않는다."""
    global _RANKS
    for p in _RANKS_PATHS:
        try:
            mt = os.stat(p).st_mtime
        except OSError:
            continue
        if _RANKS[0] != (p, mt):
            with open(p, encoding="utf-8") as f:
                _RANKS = ((p, mt), json.load(f))
        return _RANKS[1] or {}
    return {}


def rank_names() -> list:
    return [str(r.get("name") or "").strip() for r in (ranks_raw().get("ranks") or []) if r.get("name")]


# 파트너팀 안의 팀(P.T팀·골프팀·스쿼시팀 …) — GM 2026-09-18 「파트너팀으로만 묶이면 안 보인다」.
# 정본 = ssot/kpi.json _팀리더_2026_08_25.teams(종목별 팀 리더 단일 출처) — 이름을 여기 복제하지 않는다.
TEAM_DEPT = "파트너팀"
_KPI_PATHS = ("/srv/erp/repo/ssot/kpi.json",
              os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "ssot", "kpi.json"))


def team_names() -> list:
    for p in _KPI_PATHS:
        try:
            with open(p, encoding="utf-8") as f:
                teams = (json.load(f).get("_팀리더_2026_08_25") or {}).get("teams") or {}
            return [str(k).strip() for k in teams if str(k).strip()]
        except (OSError, ValueError):
            continue
    return []


def rank_tier(rank: str) -> str:
    """그 직급이 리더급인가 팀원급인가. 모르는 값이면 member(좁은 쪽) — 안전한 쪽으로 떨어뜨린다."""
    key = str(rank or "").strip()
    for r in (ranks_raw().get("ranks") or []):
        if str(r.get("name") or "").strip() == key:
            return "leader" if r.get("tier") == "leader" else "member"
    return "member"


def tier_deny(tier: str) -> list:
    """팀원급에서 빼는 화면 — 층에 한 번만 적고 부서마다 복제하지 않는다."""
    return [] if tier == "leader" else list(ranks_raw().get("member_deny") or [])


def tier_extra(dept: str, tier: str) -> list:
    """리더급에게 부서 기본 위에 더 얹는 화면 — ranks.json leader_extra[부서](GM 2026-09-17 「강습부 팀장은 박민서 팀장처럼 권한 같게」).
    팀원급은 빈 목록. 강습 팀장 = 파트너팀 기본(강습 회원)에 회원·문의 화면이 더 붙는다."""
    if tier != "leader":
        return []
    return list((ranks_raw().get("leader_extra") or {}).get(dept) or [])


def dept_modules_for(dept: str, tier: str) -> list:
    """부서 기본 + 리더급 추가 — 가입·소셜 승인·부서 일괄 적용이 전부 이 하나를 쓴다(중복 없이 순서 유지)."""
    mods = list(dept_modules(dept))
    return mods + [m for m in tier_extra(dept, tier) if m not in mods]


# 개인 예외 3건(GM 확정 2026-09-05 §3) — 부서 템플릿·groups·all 매칭으로는 절대 안 열린다.
# GM 이 관리자 화면에서 그 사람에게만 modules 로 콕 집어 켜야 보인다(월간운영계획=이경연 실장·GM업무=김남욱 GM·
# 인사재무/채용=나우열M). 매출회원보고·자율현황·카톡전송관리도 경영진 전용이라 같은 방식으로 묶는다.
EXCEPTION_ONLY_IDS = frozenset({
    "gm-월간운영계획", "coo-chairman-gm업무",
    "cfo-finance-매출현황", "cfo-finance-지출현황", "cfo-finance-매출지출현황",
    "chro-hub-index", "chro-recruiting-index",
    "coo-report-매출회원현황보고", "cto-자율현황", "cto-automation-카톡전송관리",
    # 2026-09-17 시토: 관리자 판을 「사람 × 업무영역 6칸 체크」로 단순화(GM 10:44)하면서 화면 UI 관례(MGMT_ONLY)로만
    #   가려지던 경영 문서 5장이 영역 체크 한 번에 같이 켜지게 됐다 — 서버 규칙으로 개인 예외 전용에 넣는다.
    "ceo-wellperion-guide-main", "cmo-funnel-월간마케팅보고서",
    "coo-chairman-대표님-지시사항", "coo-chairman-회장님-지시사항", "cfo-finance-지출품의",
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
# 사무실 PC 자동 로그인(배1134)은 2026-09-17 GM 지시로 폐지했다 — 「다들 info 계정을 쓰다 보니 크롬에서 erp 를 열면
# info 로 자동 로그인 · 인포 계정을 삭제하고 개인 계정으로」. 함수 office_auto_login 과 OFFICE_AUTO_LOGIN_IP 환경값을
# 지웠고 info@ 계정은 status=disabled(모든 info 세션이 그 순간 401 → 로그인 화면). 아래 상수·auto 토큰 차단은
# 아직 살아 있는 옛 auto 토큰 방어용으로만 남긴다(경위는 저장 이력).
OFFICE_AUTO_LOGIN_ACCOUNT = os.environ.get("OFFICE_AUTO_LOGIN_ACCOUNT", "info@wellperion.com")
# 직원 홈 주소 — 로그인만 되면 누구나(카드·폴더 판정 밖). nginx guide-alias 가 /home·/guide 를 정본 파일로 되쓴다.
STAFF_HOME_PATHS = frozenset({"/home", "/guide", "/wellperion_guide(main).html"})
STAFF_HOME_MODULE = "ceo-wellperion-guide-main"   # 그 파일의 카드 id(modules.json) — 카드 판정에서도 전원 허용
# 로그인한 계정 전원에게 열리는 카드 — 직원 홈 + 업무 시스템(GM 2026-09-17 「GM·실장·소장·나우열M·실무진 7명이 각자 ?who= 로 본다」).
# 카드 표(erp_modules_build CORE)에 올려도 perms 가 있는 계정은 modules 목록에 없으면 403 이라(실측 09-17 16:07 직원 9계정 전부) 여기서 연다.
STAFF_OPEN_MODULES = frozenset({STAFF_HOME_MODULE, "coo-chairman-업무시스템"})
# 자동 로그인 세션이 못 여는 개인정보 카드(배 2574). chro-* 는 접두로 따로 막는다.
AUTO_LOGIN_DENY_IDS = frozenset({"member", "inquiry", "cpo-member-lesson", "cpo-member-renewal",
                                 "cpo-member-오넛티-접수현황"})
# 자동 로그인 세션에 여는 유일한 쓰기 = 실무진 피드백(GM 2026-09-16 「인포 계정 실무진 피드백 권한도 열어줘야 해」).
#   쓰기 관문(/api/write)만 통과시키고, 액션은 api_write.AUTO_LOGIN_ACTIONS(staff_feedback_*)가 다시 가른다 — 표식은
#   X-Erp-Allowed 맨 앞 "auto-login"(모듈 id 모양이 아닌 낱말이라 다른 카드와 안 섞인다). 피드백 카드 자체도 연다.
AUTO_LOGIN_ALLOWED_HEADER = "auto-login," + urllib.parse.quote("cpo-member-실무진피드백", safe="")
# 자동 로그인 세션이 쓰기(POST)를 보낼 수 있는 경로 — /api/write(실무진 피드백만 · 위) + 종합접수처 처리
#   (GM 2026-09-16 13:2x 「종합접수처 현황 info 계정 권한 열어줘」 — 사무실 PC 에서 접수 처리·보류·습득물 인계).
AUTO_LOGIN_WRITE_PREFIXES = ("/api/write", "/api/reception/")
# 그 카드들이 쓰는 읽기 API 도 같이 막는다 — 화면만 막고 API 를 열어 두면 주소로 자료를 그대로 받는다.
AUTO_LOGIN_DENY_API = ("/api/members", "/api/inquiries", "/api/lesson/", "/api/hr/")
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


# ── 모듈 배치(ERP관리 층 · GM 구조 2026-09-14: 플랫폼=셋업 → 관리=배치 → 홈=사용) ─────────────────
# 이 회사에서 끈 모듈 id 목록. 파일 하나(account_perms.json 과 같은 mtime 재읽기 · 저장 즉시 반영).
# 꺼진 모듈 = 직원에게 카드도 안 보이고 관문(check)도 막는다 · 관리자는 그대로 본다(다시 켜야 하니까).
MODULE_SWITCH = os.environ.get("ERP_MODULE_SWITCH",
                               os.path.join(os.path.dirname(os.path.abspath(__file__)), "module_switch.json"))
_SWITCH: tuple = (None, frozenset())

# ── 평가 KPI 설정(ERP 관리자 「평가」 · GM 지시 2026-09-18) ──────────────────────────────────
# 원장 = 이 파일 하나(company·manager·partner 세 절). 없으면 저장소 씨앗(status/eval_kpi.json)을 한 번 읽는다.
# 저장은 관리자 등급 + 관리자 비밀번호 문 뒤(POST /auth/admin/api/eval_kpi). 실측값은 여기 두지 않는다(화면이 원장에서 읽는다).
EVAL_KPI = os.environ.get("ERP_EVAL_KPI", os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_kpi.json"))
_EVAL_KPI_SEEDS = ("/srv/erp/repo/status/eval_kpi.json",
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "status", "eval_kpi.json"))
_EVAL_KPI_SECTIONS = ("company", "manager", "partner")


def eval_kpi_load() -> dict:
    """서버 원장 → 없으면 씨앗 → 그것도 없으면 빈 세 절. 모양은 항상 세 절 리스트로 맞춘다."""
    for p in (EVAL_KPI,) + _EVAL_KPI_SEEDS:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            break
        except (OSError, ValueError):
            continue
    else:
        d = {}
    out = {k: v for k, v in d.items() if not k.startswith("_")}
    for sec in _EVAL_KPI_SECTIONS:
        out[sec] = [x for x in (out.get(sec) or []) if isinstance(x, dict)]
    return out


def eval_kpi_clean(body: dict) -> dict:
    """화면이 보낸 본문에서 세 절만, 문자열 칸만 남긴다(모르는 칸·긴 값은 버린다)."""
    keep = {"company": ("key", "name", "target", "unit", "source", "measure"),
            "manager": ("person", "item", "target"), "partner": ("key", "name", "target")}
    out = {}
    for sec in _EVAL_KPI_SECTIONS:
        rows = []
        for x in (body.get(sec) or [])[:200]:
            if not isinstance(x, dict):
                continue
            row = {k: str(x.get(k) or "")[:300] for k in keep[sec]}
            if row.get("name") or row.get("item"):
                rows.append(row)
        out[sec] = rows
    return out


def eval_kpi_save(body: dict, by: str) -> dict:
    d = eval_kpi_clean(body)
    d["updated_at"] = now()
    d["updated_by"] = by
    tmp = EVAL_KPI + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, EVAL_KPI)
    return d


def modules_off() -> frozenset:
    global _SWITCH
    try:
        mt = os.stat(MODULE_SWITCH).st_mtime
    except OSError:
        return frozenset()
    if mt != _SWITCH[0]:
        with open(MODULE_SWITCH, encoding="utf-8") as f:
            _SWITCH = (mt, frozenset(json.load(f).get("off") or []))
    return _SWITCH[1]


def _save_modules_off(ids: list, by: str) -> None:
    tmp = MODULE_SWITCH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"off": sorted(set(ids)), "_updated": {"by": by, "at": now()}}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MODULE_SWITCH)
    global _SWITCH
    _SWITCH = (None, frozenset())


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
    """이름만 본다 — 명부에 그 이름이 있고 재직이면 통과(GM 지시 2026-09-11 「이름만 대조해줘, 이름만 맞으면되」).

    ▸경위: 2026-09-07 GM 「인사정보랑 크로스체크」로 시작할 때는 이름+연락처 둘 다 맞아야 했다.
      2026-09-11 GM 이 이름만으로 좁혔다 — 다음에 「왜 연락처를 안 보나」 하지 않게 여기 적어 둔다.
      phone 인자는 그대로 받는다(승인 화면에서 GM 이 보실 값이라 계속 저장한다) — 통과 여부만 안 가린다.
    ▸비교: 양쪽 공백을 다 턴 뒤, 명부 이름이 신청 이름 안에 들어 있으면 통과한다 —
      신청은 「홍길동 매니저」처럼 직함이 붙어 오는데 명부는 「홍길동」이라 완전일치로는 못 잡는다.
      단 명부 이름이 두 글자 이상일 때만 그렇게 본다(한 글자가 아무 이름에나 들어맞는 것 차단).
    ▸퇴직·퇴사는 종전대로 불일치. 순수 함수 — 자가점검에서 가짜 명부를 넣어 검증한다.
    """
    name_key = "".join(str(name or "").split())
    if not name_key:
        return False
    for row in roster:
        row_name = "".join(str(row.get("성명") or row.get("이름") or "").split())
        if not row_name:
            continue
        if row_name != name_key and not (len(row_name) >= 2 and row_name in name_key):
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
    # ★거절을 빈 명부로 삼키지 않는다(2026-09-11 실사고). 비밀번호가 틀리면 인사 허브는 HTTP 200 에
    #   {"ok":false,"error":"unauthorized"} 를 담아 준다. 종전에는 results 가 없으니 [] 가 돼
    #   "명부 0명" 이 되고, 가입 신청은 전부 「이름이 명부에 없습니다」로 막혔다 — 비밀번호가 틀렸다는
    #   말은 어디에도 안 나왔다. GM 이 값을 넣고도 계속 막힌 것이 이 자리다.
    if isinstance(data, dict) and data.get("ok") is False:
        raise RuntimeError(str(data.get("message") or data.get("error") or "인사 허브가 거절했습니다"))
    rows = data.get("results") if isinstance(data, dict) else data
    if not rows:
        raise RuntimeError("인사 허브가 명부를 0명으로 돌려줬습니다 — 비밀번호나 응답 형식을 확인해 주세요")
    return rows


def _hr_roster_db() -> list:
    """서버 인사 표(hr.employee · 나우열M 라인 적재분)를 hr_match 가 읽는 모양({"성명","재직 상태"})으로 — 읽기만 한다.
    2026-09-17 인사 허브 GAS 가 비밀번호 거절로 명부를 안 줘 가입 신청이 전부 막혔다. 서버 표(재직 71명)가 정본이라 여기부터 본다."""
    with db() as c:
        rows = c.execute("SELECT person_name_raw, roster_display_name, status FROM hr.employee").fetchall()
    return [{"성명": r["roster_display_name"] or r["person_name_raw"], "재직 상태": r["status"] or ""} for r in rows]


def hr_roster() -> list:
    """5분 메모리 캐시(성공한 결과만 캐시 — 실패는 다음 호출에서 바로 재시도). 서버 인사 표 → 비었을 때만 인사 허브 GAS."""
    global _HR_ROSTER
    ts, rows = _HR_ROSTER
    if rows is not None and time.time() - ts < 300:
        return rows
    try:
        rows = _hr_roster_db()
    except Exception:
        rows = []
    if not rows:
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
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TEXT")   # 사용 현황(ERP관리 층 · 2026-09-14)
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_ver INTEGER NOT NULL DEFAULT 0")   # 세션 세대(배 12752 P1 #10)
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
def touch_login(uid: int) -> None:
    """마지막 로그인 시각 — 사용 현황(ERP관리 층)이 읽는다. 로그인 성공 자리 3곳(아이디·구글·네이버/카카오)에서 부른다."""
    try:
        with db() as c:
            c.execute("UPDATE users SET last_login=%s WHERE tenant_id=%s AND id=%s", (now(), T, uid))
    except Exception:
        pass                                       # 기록 실패가 로그인을 막지 않는다


def session_ver(user) -> int:
    """세션 세대(배 12752 P1 #10) — 비밀번호 변경·전체 기기 로그아웃·차단 때 +1 하면 그 전에 발급된 토큰은 current() 가 거부한다.
    세션은 90일 무상태라 종전엔 비밀번호를 바꿔도 분실 폰·공용 PC 세션이 그대로 살았다. 열이 없는 옛 행·자가점검 가짜 user = 0세대."""
    try:
        return int(user["session_ver"] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return 0


def _bump_session_ver(uid: int) -> None:
    with db() as c:
        c.execute("UPDATE users SET session_ver=session_ver+1 WHERE tenant_id=%s AND id=%s", (T, uid))


def issue(user, auto: bool = False) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    claims = {"uid": user["id"], "email": user["email"], "role": user["role"], "exp": exp, "ver": session_ver(user)}
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
    if u is not None and int(claims.get("ver") or 0) != session_ver(u):
        return None                                # 세대가 다르다 = 비밀번호 변경·전체 로그아웃·차단 뒤 남은 옛 토큰(ver 없는 옛 토큰은 0세대)
    return u


# ── 권한 ────────────────────────────────────────────────────────────────
_MODS: tuple = (None, [], {})                  # (mtime, 모듈 목록, 경로→모듈) · mtime 바뀌면 다시 읽는다
_DOCS: tuple = (None, [], {})                  # (mtime, 문서 목록, 경로→문서) — 같은 modules.json 의 documents 키(배 12666)


def _by_path(items: list) -> dict:
    # path 는 /erp/ 기준 상대경로("../cpo/x.html") → 사이트 절대경로("/cpo/x.html")
    return {posixpath.normpath(urllib.parse.urljoin("/erp/", m["path"])): m for m in items}


def modules() -> list:
    global _MODS, _DOCS
    try:
        mt = os.stat(MODULES).st_mtime
    except OSError:
        return _MODS[1]
    if mt != _MODS[0]:
        with open(MODULES, encoding="utf-8") as f:
            raw = json.load(f)
        ms = raw["modules"]
        _MODS = (mt, ms, _by_path(ms))
        ds = raw.get("documents") or []            # 보고 문서(kind=doc) — 모듈이 아니다(배 12666)
        _DOCS = (mt, ds, _by_path(ds))
    return _MODS[1]


def documents() -> list:
    modules()                                      # 같은 파일·같은 mtime 로 같이 읽는다
    return _DOCS[1]


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


GUIDE_ALIASES = {"/home": "/wellperion_guide(main).html", "/guide": "/wellperion_guide(main).html"}   # = guide-alias.nginx.conf rewrite


def uri_path(uri: str) -> str:
    """X-Original-URI → 정규화한 경로('/'로 시작 · 쿼리 없음 · 퍼센트 해제 · '..' 정리). module_at·path_allowed 가 같이 쓴다."""
    # 선행 슬래시를 1개로 강제 — posixpath.normpath 는 '//x' 를 보존해 '//cpo/…' 요청이 모듈 조회를 빗나가게 했다
    # (권한 판정 우회 · 2026-09-05 검수 C4). nginx 는 merge_slashes 로 파일은 정상으로 내주므로 여기서 맞춘다.
    # urlsplit 을 쓰지 않는다 — '//cpo/x' 는 urlsplit 이 '//cpo' 를 호스트로 먹어 path 가 '/x' 가 된다(실측 2026-09-05).
    raw = uri.split("?", 1)[0].split("#", 1)[0]
    path = "/" + posixpath.normpath(urllib.parse.unquote(raw) or "/").lstrip("/")
    # 짧은 주소(guide-alias.nginx.conf 의 rewrite /home·/guide → 가이드 화면)는 nginx 안에서만 바뀌고
    # X-Original-URI 엔 '/home' 그대로 온다. 그러면 카드 조회가 빗나가 직원 계정이 전부 403 이었다
    # (GM 2026-09-16 「/auth/forbidden?next=/home 이거 어디길래」 — 사무실 자동 로그인(info@)으로 열려 있던 창).
    # nginx 가 재작성하는 것과 같은 규칙으로 여기서도 맞춘다 — 관리자는 원래 열렸고 직원은 카드 권한대로 열린다.
    return GUIDE_ALIASES.get(path, path)


def _lookup(path: str, by_path: dict) -> Optional[dict]:
    """정확 경로 → 없으면 .html 생략 보정 → 없으면 폴더 index.html. module_at·doc_at 공용."""
    if path in by_path:
        return by_path[path]
    if path.endswith(".html"):
        return None
    # 깔끔한 주소(.html 생략) 허용 — nginx try_files 가 $uri.html 로 파일을 찾으므로 권한 판정도 같은 파일로(GM 2026-09-05)
    m = by_path.get(path + ".html")
    if m:
        return m
    # 폴더 index.html(/chro/hub/ 등) — nginx try_files 가 $uri/index.html 로 찾는 것과 맞춘다(2026-09-05 검수 H2)
    return by_path.get(path.rstrip("/") + "/index.html")


def module_at(uri: str) -> Optional[dict]:
    """nginx 가 넘긴 X-Original-URI → 모듈. 목록에 없는 경로(공용 자산·status 등)는 None."""
    modules()
    return _lookup(uri_path(uri), _MODS[2])


def doc_at(path: str) -> Optional[dict]:
    """카드 밖 보고 문서(kind=doc) 찾기 — module_at 과 같은 매칭 규칙(배 12666).
    path_allowed 가 이미 uri_path 로 정규화한 path 를 그대로 받는다(재정규화 안 함)."""
    modules()
    return _lookup(path, _DOCS[2])


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
    if module["id"] in STAFF_OPEN_MODULES:         # 직원 홈(/home)·업무 시스템 — 로그인한 계정 전원(GM 2026-09-17)
        return True
    if module["id"] in modules_off():              # 이 회사에서 끈 모듈(모듈 배치) — 직원은 못 본다
        return False
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
    return [m["id"] for m in modules() if allowed(user, m)] + \
           [d["id"] for d in documents() if doc_allowed(user, d)]


def doc_allowed(user, doc: dict) -> bool:
    """보고 문서(kind=doc) 권한 — 카드 밖 폴더 대체판정을 건너뛰고 개인 예외로만 연다(배 12666).
    관리자=전부. 그 외는 account_perms 의 deny 를 먼저, 그다음 modules(개인 지정)만 본다 —
    groups·all 은 안 본다(문서는 부서 권한이 아니라 사람을 콕 집어 여는 것이다)."""
    if user["role"] == "admin":
        return True
    p = perms_of(user)
    if p is None:
        return False
    if doc["id"] in p.get("deny", []):
        return False
    return doc["id"] in p.get("modules", [])


# ── 카드 목록(modules.json) 밖 경로의 권한 (2026-09-14 배포 전 점검 · 치명 2·3번) ─────────────────
# 종전 check() 는 module_at() 이 None 이면 로그인만 보고 200 을 냈다. 그래서 카드에 안 실은 것 — /api/ 전부,
# /repo/(저장소 통째), /reports/(실명 인사평가 A3), /erp/admin/(회사 관리자 콘솔), /회사문서/, 회원·문의 스냅샷 —
# 이 로그인한 아무 계정(파트너사 포함)에게 다 열렸다. 「카드에 안 싣는다」가 「권한을 안 본다」가 돼 있던 자리.
ADMIN_ONLY_PREFIXES = ("/reports/", "/회사문서/", "/erp/admin/", "/1. AI자료_아카이브/", "/gm/",
                       "/wellperion-agents/", "/scripts/", "/logs/", "/ops/", "/telegram_bot/", "/qa_screenshots/", "/ig/",
                       "/coo/chairman/")   # 보고 문서(kind=doc, 배 12666) — 카드 밖으로 떨어져도 관리자만(카드 4장은 카드 권한이 먼저)
# /repo/ = 저장소 통째(repo-data.nginx.conf alias). 화면 17장이 /repo/status/*.json·/repo/ssot/*.json 을 읽으므로(배1193)
# 통째로 막지 않고 안쪽 경로에 같은 규칙을 적용한다 — status·ssot·가이드 폴더만 열고 나머지(scripts·logs·아카이브…)는 관리자만.
REPO_OPEN_PREFIXES = ("/status/", "/ssot/")
GUIDE_DIR = "/3. 웰페리온 가이드"
# ERP 플랫폼관리(/erp/admin/ · 플랫폼을 파는 우리 자리)는 관리자 등급이어도 회사 계정 관리자만 연다(GM 결정 2026-09-14 —
# 개인 아이디 namuk87·jjky0123 은 관리자 등급이라 열렸다). 회사 관리자 콘솔(/auth/admin)은 종전대로 관리자 등급 전부.
PLATFORM_ADMINS = frozenset(e.strip().lower() for e in os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com").split(",") if e.strip())
PLATFORM_PREFIX = "/erp/admin/"
# 회사 관리자 도구 — 파일은 랩스 폴더에 있지만 웰페리온 ERP 관리 메뉴(/erp/ 「관리」) 안에서 여는 회사 것.
# 플랫폼 판정(회사 계정만)에서 빼고 관리자 전용(ADMIN_ONLY_PREFIXES)만 건다 — 개인 아이디 관리자도 연다(GM 2026-09-18 「평가는 ERP 관리자로」).
COMPANY_ADMIN_SCREENS = ("/erp/admin/screens.html", "/erp/admin/eval.html")
# 플랫폼(파는 쪽) 화면인데 아직 파트너사 경로에 남아 있는 것 — 회사 계정 관리자만 연다(배 2633 · 웰리 실측 2026-09-15).
# 파일을 먼저 옮기면 기존 즐겨찾기가 깨지므로(2026-09-07 파트너팀 404) 자리 이동 전에 권한으로 먼저 막는다.
# 회사 관리자 콘솔(/erp/admin/)이 이 경로들을 그대로 가리키므로 회사 계정에서는 링크가 그대로 산다.
PLATFORM_PATHS = ("/자율현황.html", "/cto/automation/카톡전송관리.html", "/cto/aws_migration.html",
                  "/cto/env_status.html", "/cto/AWS_ERP_운영가이드.html", "/cbo/counsel_admin.html")
PLATFORM_PATH_PREFIXES = ("/cbo/model/", "/cbo/dietcamp/", "/cbo/gocheokgolf/")
# 회원·문의 개인정보가 든 status 파일 = 회원 관리(member) 카드가 있어야 읽는다.
MEMBER_DATA_RE = re.compile(r"^/status/(member_|inquiry_snapshot|counsel_questions|cpo_member_)")
# 읽기 API 접두 → 그 자료를 그리는 카드들. 그중 하나라도 허용돼야 API 도 열린다(2026-09-14 화면 전수 grep 으로 만든 표).
# /api/write·/api/members/write 는 본문의 action 으로 갈리므로 상류(api_write.write_allowed)가 X-Erp-Allowed 헤더로 판정한다.
# /api/board 는 페이지 공용 보드(로그인 전용 그대로).
# ⚠️ 홈 모듈(ceo-wellperion-guide-main)은 STAFF_OPEN_MODULES 로 로그인 직원 전원에게 열린다 — 이 표에 넣는 순간
#   그 접두는 전원 공개다. 홈(wellperion_guide(main).html)이 실제로 fetch 하는 접두에만 넣는다(2026-09-18 · 홈은
#   /api/members 를 안 부르는데 넣어 뒀다가 회원 API 가 전 직원에게 뚫려 있었다 — 문서 표 안 <code> 언급과 실제
#   fetch 호출을 혼동하지 말 것). /api/lesson/ 은 개인정보(등록회원·명단)라 좁게, 홈이 쓰는 집계는 /api/lesson/stats 로 따로 연다.
API_MODULES = {
    "/api/members": {"member", "cpo-member-renewal"},
    "/api/inquiries": {"member", "inquiry", "ceo-wellperion-guide-main"},
    "/api/report/": {"member", "coo-report-매출회원현황보고"},
    "/api/lesson/stats": {"member", "cpo-member-lesson", "ceo-wellperion-guide-main"},  # 홈 KPI 타일(집계만·개인정보 없음)
    "/api/lesson/": {"member", "cpo-member-lesson"},          # /members·/roster·/registry = 강습 등록 회원 개인정보
    "/api/hr/": {"chro-hub-index", "chro-recruiting-index"},
    "/api/todo": {"coo-todo-업무-현황-ssot", "coo-todo-결재-현황-ssot", "coo-chairman-gm업무", "coo-check-파트너팀-체계",
                  "ceo-wellperion-guide-main", "gm-월간운영계획"},
    "/api/proc/": {"cfo-finance-매출지출현황", "cfo-finance-지출품의"},
    "/api/sales/": {"cfo-finance-매출지출현황", "cfo-finance-매출현황", "cfo-finance-지출현황", "coo-check-파트너팀-체계",
                    "coo-report-매출회원현황보고", "gm-월간운영계획"},
    "/api/check/": {"check", "coo-check-운영부-체계", "coo-check-지원부-체계", "coo-check-주차관리부-체계",
                    "coo-check-파트너팀-체계", "ceo-wellperion-guide-main", "gm-월간운영계획"},
    "/api/reception/": {"coo-reception-종합접수처-현황", "coo-reception-lost-found-register",
                        "coo-reception-lost-found-disposal", "coo-reception-lost-found-gallery",
                        "ceo-wellperion-guide-main", "gm-월간운영계획"},
    "/api/reception-ops": {"coo-리셉션-업무-index", "coo-리셉션-업무-라커관리-index"},
    "/api/brojay/": {"coo-report-매출회원현황보고"},
    "/api/visitors": {"coo-report-매출회원현황보고"},
    "/api/chat/": set(),            # 상담봇 관리 API(log·unanswered·faq·stats) = 관리자만(빈 집합 = 아무 카드도 안 연다)
    "/api/track/": {"cmo-funnel-콘텐츠문의현황"},
}


def _api_need(path: str) -> Optional[set]:
    """가장 긴 접두로 매칭. 표에 없으면 None(로그인 전용)."""
    best = None
    for prefix, need in API_MODULES.items():
        if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, need)
    return best[1] if best else None


def _auto_denies_api(path: str) -> bool:
    """자동 로그인 세션이 못 부르는 읽기 API 인가(배 2574 · 순수함수·테스트용)."""
    return path.startswith(AUTO_LOGIN_DENY_API)


def is_platform_path(path: str) -> bool:
    """플랫폼(파는 쪽) 자리인가 — 회사 계정 관리자만 여는 경로.

    카드(모듈)가 붙어 있는 화면은 check() 가 path_allowed 를 아예 안 부르므로(카드 권한으로만 판정)
    이 판정을 따로 떼어 카드 검사보다 먼저 건다. 저장소 경로(/repo/3. 웰페리온 가이드/…)로 우회해도
    같은 자리에 걸리게 접두를 먼저 벗긴다."""
    p = path
    if p.startswith("/repo/") or p == "/repo":
        p = p[len("/repo"):] or "/"
    if p.startswith(GUIDE_DIR + "/"):
        p = p[len(GUIDE_DIR):]
    if p in COMPANY_ADMIN_SCREENS:
        return False          # 회사 관리자 도구 — 랩스 폴더에 있지만 /erp/ 관리 메뉴 안에서 여는 회사 것(관리자 전용은 ADMIN_ONLY_PREFIXES 가 그대로 건다)
    return (p.startswith(PLATFORM_PREFIX) or p == PLATFORM_PREFIX.rstrip("/")
            or p in PLATFORM_PATHS or p.startswith(PLATFORM_PATH_PREFIXES))


def path_allowed(user, path: str) -> bool:
    """카드 목록 밖 경로를 이 계정이 열어도 되나. 관리자=전부(플랫폼관리만 예외). 판정 순서 = 플랫폼관리 → 관리자 전용 접두 → 회원 자료 → API → 화면 → 자산."""
    if is_platform_path(path):
        return (user["email"] or "").lower() in PLATFORM_ADMINS
    if user["role"] == "admin":
        return True
    # 직원 홈(GM 2026-09-17 「직원 화면 = /home」 · nginx 가 /home·/guide 를 wellperion_guide(main).html 로 되쓴다) —
    # 루트 낱장이라 아래 「폴더 = 부서 도메인」 판정에 걸려 로그인한 실무진 전원이 403 을 받았다(이경연 실장 14:13 실측).
    if path in STAFF_HOME_PATHS:
        return True
    if path == "/repo" or path.startswith("/repo/"):
        inner = path[len("/repo"):] or "/"
        if inner.startswith(GUIDE_DIR + "/"):                    # 저장소 안의 화면 폴더 = 서빙 경로와 같은 규칙
            inner = inner[len(GUIDE_DIR):]
            modules()
            m = _MODS[2].get(inner)
            return allowed(user, m) if m else path_allowed(user, inner)
        if inner.startswith(REPO_OPEN_PREFIXES):
            return path_allowed(user, inner)                     # 회원 자료(MEMBER_DATA_RE) 규칙이 그대로 걸린다
        return False
    # uri_path 의 normpath 가 끝 슬래시를 떼므로('/erp/admin/'→'/erp/admin') 폴더 자체 요청도 접두에 걸리게 한 번 더 붙여 본다
    if path.startswith(ADMIN_ONLY_PREFIXES) or (path + "/").startswith(ADMIN_ONLY_PREFIXES):
        return False
    if MEMBER_DATA_RE.match(path):
        return "member" in allowed_ids(user)
    if path.startswith("/api/"):
        need = _api_need(path)
        return True if need is None else bool(need & set(allowed_ids(user)))
    last = path.rsplit("/", 1)[-1]
    if path.endswith(".html") or "." not in last:                # 화면 또는 폴더(index.html) — 확장자 없는 경로는 페이지로 본다
        doc = doc_at(path)
        if doc is not None:            # 보고 문서(kind=doc) — 개인 예외로만(배 12666). 폴더 대체판정을 건너뛴다
            return doc_allowed(user, doc)
        # 카드에 없는 화면 — 같은 최상위 폴더에 허용된 카드가 하나라도 있어야 열린다(폴더 = 부서 도메인).
        # 루트 낱장(자율현황·항해지도 등)은 폴더가 없어 관리자만.
        top = "/" + path.strip("/").split("/")[0] + "/"
        if top == "/erp/" or path == "/":
            return True                                    # 모듈 홈(erp/index.html) — /erp/admin/ 은 위에서 이미 막혔다
        modules()
        folder = [m for p, m in _MODS[2].items() if p.startswith(top)]
        return any(allowed(user, m) for m in folder)
    return True                                            # css·js·이미지·페이지가 읽는 데이터 파일


def allowed_header(user) -> str:
    """상류 API 에 넘기는 X-Erp-Allowed 값 — 관리자 '*', 아니면 허용 모듈 id 를 퍼센트 인코딩해 쉼표로(헤더는 latin-1 만 받는다)."""
    if user["role"] == "admin":
        return "*"
    return ",".join(urllib.parse.quote(i, safe="") for i in allowed_ids(user))


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
    ".brand{display:flex;align-items:center;min-height:44px}.brand svg{height:15px;width:auto;display:block}"
    ".brand small{margin-left:8px;font-size:12px;font-weight:600;letter-spacing:.06em;color:var(--ink-soft)}"
    "form,.box{width:100%;max-width:400px;margin:0 auto;padding:28px;background:var(--paper);border:1px solid var(--line);border-radius:8px}"
    ".box.wide{max-width:860px}"
    "h1{margin:0 0 18px;font-size:20px;font-weight:700;letter-spacing:-.01em}"
    "label{display:block;margin:0 0 14px;font-size:13px;font-weight:600;color:var(--ink-soft)}"
    # 「로그인 상태 유지」 — 체크칸은 한 줄로 눕힌다(다른 칸처럼 위아래로 벌어지면 입력칸처럼 보인다)
    "label.keep{display:flex;align-items:center;gap:8px;margin:-4px 0 10px;cursor:pointer}"
    "label.keep input{width:auto;margin:0;accent-color:var(--accent)}"
    "input,select{display:block;width:100%;margin-top:6px;padding:11px 12px;font:inherit;color:var(--ink);background:var(--paper);"
    "border:1px solid var(--line-strong);border-radius:8px}"
    "input::placeholder{color:var(--ink-soft);opacity:.7}"
    # 부서 고르는 칸을 위 입력칸들과 같은 모양으로 (GM 지적 2026-09-11) — 브라우저 기본 모양이면
    # 높이·테두리·글꼴이 혼자 다르다. 기본 화살표를 끄고 같은 자리에 우리 화살표를 그린다.
    "select{appearance:none;-webkit-appearance:none;padding-right:34px;cursor:pointer;"
    "background-image:url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236E655C' stroke-width='2.2' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\");"
    "background-repeat:no-repeat;background-position:right 11px center;background-size:16px}"
    "select:invalid{color:var(--ink-soft)}"
    ":focus-visible{outline:2px solid var(--focus);outline-offset:2px}"
    "input:focus,select:focus{outline:2px solid var(--focus);outline-offset:0;border-color:transparent}"
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
    "p{margin:16px 0 0;font-size:13.5px;color:var(--ink-soft)}p a{display:inline-block;padding:12px 0;color:var(--ink);text-decoration:underline;text-underline-offset:3px;white-space:nowrap}"
    ".err,.ok{margin:0 0 16px;padding:8px 12px;font-size:13.5px;color:var(--ink);border-left:3px solid var(--accent);background:var(--accent-soft)}"
    ".err{border-left-color:#ED5B3F}"
    ".tw{overflow-x:auto}table{width:100%;min-width:640px;font-size:14px;border-collapse:collapse}"
    "th{padding:6px 8px;text-align:left;font-size:12px;font-weight:700;color:var(--ink-soft);border-bottom:1px solid var(--line-strong)}"
    "td{padding:10px 8px;vertical-align:top;border-bottom:1px solid var(--line)}td small{color:var(--ink-soft)}"
    "td form{display:inline;padding:0;border:0;width:auto;max-width:none;background:none}"
    "td button{width:auto;margin:0 6px 4px 0;padding:6px 10px;font-size:13px}"
    ".tag{display:inline-block;white-space:nowrap;padding:1px 8px;font-size:12px;font-weight:700;border-radius:8px;border:1px solid var(--line-strong)}"
    ".tag.on{background:var(--accent);color:#221F20;border-color:transparent}"
    ".nav{margin-top:18px;font-size:13.5px;color:var(--ink-soft)}.nav a{display:inline-block;padding:6px 0;color:var(--ink);text-decoration:underline;text-underline-offset:3px;margin-right:14px}"
    # ── 2026-09-04 시포(GM "UI/UX 신경써서") — 머리글·상태색·대기 카드·비밀번호 표시·모바일 카드형 ──
    ".hd{max-width:400px;margin:0 auto 18px}.hd.wide{max-width:860px}.hd .brand{margin:0}.hd .sub{margin:4px 0 0;font-size:13px;color:var(--ink-soft)}"
    ".hint{margin:-6px 0 16px;padding:8px 12px;font-size:13px;color:var(--ink);background:var(--accent-soft);border-radius:6px}"
    ".pw{position:relative;display:block}.pw button{position:absolute;right:1px;bottom:1px;width:auto;margin:0;padding:0 12px;min-height:44px;font-size:12px;font-weight:600;"
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
    # 시모 검수 2026-09-17(design_audit) — 폰 본문 16px · 움직임 줄이기 · 인라인 버튼을 클래스로
    "@media(max-width:480px){body{font-size:16px}}"
    "@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}button:active{transform:none}}"
    ".btn{display:inline-block;padding:11px 20px;border-radius:8px;background:var(--accent);color:#221F20;font-weight:700;text-decoration:none;min-height:44px;box-sizing:border-box}"
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
    """로그인 뒤 돌아갈 주소 검증 — '/' 로 시작하되 '//도메인' 오픈 리다이렉트는 막는다(2026-09-05 검수 M2).
    역슬래시도 막는다(2026-09-14 점검) — 브라우저는 '/\\evil.com' 의 '\\' 를 '/' 로 읽어 밖으로 튄다."""
    return next if next.startswith("/") and not next.startswith("//") and "\\" not in next else default


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


def _keep_max_age(keep) -> Optional[int]:
    """「로그인 상태 유지」 = 90일 쿠키 / 끄면 max_age 없음(브라우저 닫으면 로그아웃).

    GM 지시 2026-09-11 「로그인화면에서 자동로그인 기능 넣어줘」. 쿠키는 이미 90일이었는데
    화면에 그렇게 적힌 데가 없어 없는 기능으로 보였다 — 체크칸으로 보이게 하고, 끌 수도 있게 했다.
    ⚠️ 배1134(사무실 IP 무인 자동 로그인)와 다른 것이다. 그건 로그인 없이 들어가는 것이고
    회원 와이파이 확인 전엔 안 켠다. 이건 사람이 한 번 로그인한 뒤 오래 유지되는 것뿐이다.
    """
    return SESSION_DAYS * 86400 if str(keep or "").strip() else None


LOGIN_JS = r"""
<script>
(function(){
  var keep = document.getElementById('keep'), id = document.querySelector('input[name=email]');
  var hint = document.getElementById('keephint');
  /* 아이디만 기억한다 — 비밀번호는 우리가 저장하지 않고 브라우저에 맡긴다. */
  try {
    var last = localStorage.getItem('erp_last_id');
    if (id && last && !id.value) { id.value = last; }
    var k = localStorage.getItem('erp_keep');
    if (keep && k === '0') keep.checked = false;
  } catch (e) {}
  function sync(){
    if (!keep) return;
    try { localStorage.setItem('erp_keep', keep.checked ? '1' : '0'); } catch (e) {}
    /* 구글·네이버·카카오도 같은 값을 따르게 — 콜백이 이 쿠키를 본다. */
    document.cookie = 'erp_keep=' + (keep.checked ? '1' : '0') + '; path=/auth; max-age=600; samesite=lax';
    if (hint) hint.textContent = keep.checked
      ? '이 브라우저에서 90일 동안 로그인 상태로 둡니다'
      : '브라우저를 닫으면 로그아웃됩니다';
  }
  if (keep) { keep.addEventListener('change', sync); sync(); }
  var form = id && id.form;
  if (form) form.addEventListener('submit', function(){
    try { localStorage.setItem('erp_last_id', (id.value || '').trim()); } catch (e) {}
  });
})();
</script>
"""


@app.get("/auth/login")
def login_page(request: Request, next: str = "/", err: str = "", msg: str = ""):
    dest = {"/auth/admin": "계정 관리", "/auth/password": "비밀번호 변경"}.get(next)
    hint = f"<p class=hint>로그인하면 <b>{escape(dest)}</b> 화면으로 이동합니다</p>" if dest else ""
    # 머리글에 개인 계정을 적어 둔다(GM 지시 2026-09-11 "개인계정 가입하는 것도 열어놔줘").
    # 흐름은 2026-09-05 부터 이미 열려 있었는데(개인 구글 = 이름·부서 확인 → GM 승인),
    # 화면 문구가 「아이디 또는 회사 이메일」 이라 닫힌 것처럼 읽혔다.
    return page("웰페리온 ERP 로그인", head("직원용 업무 화면 · 아이디 · 회사 이메일 · 개인 구글 계정으로 로그인") + f"""<form method=post action=/auth/login>
<h1>로그인</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}{hint}
<label>아이디 또는 이메일<input name=email type=text autocomplete=username placeholder="아이디 또는 이름@wellperion.com" required autofocus></label>
<label>비밀번호<span class=pw><input name=password type=password autocomplete=current-password required>""" + TOGGLE + f"""</span></label>
<label class=keep><input type=checkbox id=keep name=keep value=1 checked> 로그인 상태 유지</label>
<p class=hint id=keephint>이 브라우저에서 {SESSION_DAYS}일 동안 로그인 상태로 둡니다</p>
<input type=hidden name=next value="{escape(next)}"><button>로그인</button>
{_social_login_buttons(next)}
<div class=foot><p><b>개인 구글 계정(gmail 등)으로도 됩니다.</b> 처음이면 이름·부서만 알려주세요 — 승인은 GM 이 합니다.</p>
<p>구글 계정이 없으면 <a href=/auth/signup>아이디로 가입 신청</a> · 비밀번호를 잊으셨으면 GM 께 말씀해 주세요.</p></div></form>""" + LOGIN_JS)


@app.post("/auth/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/"),
          keep: str = Form("")):
    email = email.strip().lower()
    if len(FAILS) > 2000:                                   # 무작위 아이디로 채워 메모리가 늘지 않게 — 만료된 잠금·오래된 실패부터 턴다
        cut = time.time() - LOCK_SECS
        for k in [k for k, (_, until) in FAILS.items() if until < cut]:
            FAILS.pop(k, None)
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
    touch_login(u["id"])
    r = RedirectResponse(safe_next(next), status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"     # nginx 만 보냄 · http(IP접속)는 종전대로 secure 없음
    r.set_cookie(COOKIE, issue(u), max_age=_keep_max_age(keep), httponly=True, samesite="lax", path="/", secure=https)
    return r


SIGNUP_JS = r"""
<script>
/* 아이디 칸 — 서버가 이미 하는 정리(공백 제거·소문자)를 화면에서도 한다(GM 막힘 2026-09-11).
   종전에는 pattern 으로만 막아서, 자동완성이 넣은 앞뒤 공백·대문자·폭 없는 공백 하나에
   브라우저가 「요청한 형식과 일치시키세요」를 띄웠다 — 무엇을 고쳐야 하는지 알 수 없는 문구다.
   회사 이메일(@wellperion.com)도 서버는 받아 주는데 옛 pattern 이 @ 를 막고 있었다. */
(function(){
  var el = document.getElementById('uid');
  if (!el) return;
  var ID = /^[a-z0-9._]{4,20}$/, MAIL = /^[a-z0-9._%+-]+@wellperion[.]com$/;
  var JUNK = /[\s\u200b-\u200d\ufeff]/g;   // 눈에 안 보이는 공백까지 턴다(정규식 그대로 — 문자열로 쓰면 역슬래시가 한 겹 벗겨진다)
  function clean(v){
    return String(v || '').replace(JUNK, '').toLowerCase();
  }
  function check(){
    var v = clean(el.value);
    if (el.value !== v) el.value = v;                 // 붙여넣기·자동완성 값도 그 자리에서 정리
    if (!v) { el.setCustomValidity('아이디를 입력해 주세요'); return; }
    if (ID.test(v) || MAIL.test(v)) { el.setCustomValidity(''); return; }
    if (v.length < 4) { el.setCustomValidity('아이디가 짧습니다 — 4자 이상으로 적어 주세요'); return; }
    if (v.length > 20) { el.setCustomValidity('아이디가 깁니다 — 20자 안으로 적어 주세요'); return; }
    var bad = v.replace(/[a-z0-9._]/g, '');
    el.setCustomValidity(bad
      ? '아이디에 쓸 수 없는 글자가 있습니다: ' + bad.split('').join(' ') + ' — 영문 소문자·숫자·마침표·밑줄만 됩니다'
      : '아이디 형식을 확인해 주세요');
  }
  el.addEventListener('input', check);
  el.addEventListener('blur', check);
  el.form.addEventListener('submit', check);
  check();
})();
</script>
"""


@app.get("/auth/signup")
def signup_page(msg: str = ""):
    dept_opts = "".join(f"<option value='{escape(d)}'>{escape(d)}</option>" for d in DEPTS)
    # 직급 목록은 ssot/ranks.json 에서 읽는다 — 화면에 이름을 박지 않는다.
    rank_opts = "".join(f"<option value='{escape(r)}'>{escape(r)}</option>" for r in rank_names())
    return page("웰페리온 ERP 가입 신청", head("직원용 업무 화면 · 가입 신청") + f"""<form method=post action=/auth/signup>
<h1>가입 신청</h1>{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<label>아이디<input id=uid name=username autocomplete=username maxlength=40
placeholder="영문 소문자·숫자·.·_ 4~20자" required></label>
<label>비밀번호<input name=password type=password placeholder="8자 이상" minlength=8 autocomplete=new-password required></label>
<label>이름<input name=name placeholder="직함 포함, 예: 홍길동 매니저" autocomplete=name required></label>
<label>연락처<input name=phone type=tel autocomplete=tel placeholder="010-0000-0000" required></label>
<label>부서<select name=dept required><option value="">선택</option>{dept_opts}</select></label>
<label>직급<select name=rank required><option value="">선택</option>{rank_opts}</select></label>
<button>신청</button><div class=foot><p>신청하면 GM 께 알림이 갑니다. <b>GM 이 승인해야</b> 그 계정으로 로그인할 수 있습니다. 이름·연락처·부서는 GM 이 보고 판단하는 값이니 정확히 적어 주세요.</p>
<p>이미 계정이 있으면 <a href=/auth/login>로그인</a></p></div></form>
""" + SIGNUP_JS + """""")


@app.post("/auth/signup")
def signup(name: str = Form(...), username: str = Form(...), password: str = Form(...),
           phone: str = Form(...), dept: str = Form(...), rank: str = Form("")):
    name = name.strip()
    uid = "".join(username.split()).lower()
    if dept not in DEPTS:
        return RedirectResponse("/auth/signup?msg=부서를 선택해 주세요", status_code=303)
    # ★회사 이메일 형태(x@wellperion.com)로 자동 활성하던 갈래를 없앴다(2026-09-14 배포 전 점검 · 치명 1번).
    #   메일함 소유를 한 단계도 확인하지 않아 인터넷의 누구나 회사 주소를 적고 즉시 활성 계정을 얻었고,
    #   아직 구글로 안 들어온 직원 주소를 선점할 수도 있었다. 회사 계정은 구글 로그인(소유가 증명됨)으로만.
    if not valid_username(uid):
        return RedirectResponse("/auth/signup?msg=아이디는 영문 소문자·숫자·.·_ 4~20자로 입력해 주세요 "
                                "(회사 이메일은 로그인 화면의 구글 로그인을 쓰세요)", status_code=303)
    if len(password) < 8:
        return RedirectResponse("/auth/signup?msg=비밀번호는 8자 이상이어야 합니다", status_code=303)
    # ★가입에서 인사 명부 대조를 뺀다 (GM 지시 2026-09-11 「그냥 내가 승인하냐 안하냐로
    #   구분해줘 명부 체크하는것 하지말고」). 누구나 신청할 수 있고, 계정이 사는 것은 GM 승인
    #   하나로만 정해진다. 「명부 확인 안 됨」 같은 표시도 안 붙인다 — 표시가 있으면 GM 이 그걸
    #   판단 근거로 오해한다. 승인 화면이 보여 주는 이름·연락처·부서가 이제 유일한 판단 근거다.
    #   ▸경위: 09-07 「인사정보 크로스체크」로 시작 → 09-11 오전 이름만 → 09-11 낮 대조 폐지.
    #   ▸hr_check 화면·hr_match·hr_roster 는 남겨 둔다(가입 경로에서만 안 쓴다).
    salt, h = hash_pw(password)
    status, approved_at = "pending", None
    # 부서 화면에서 팀원급이 못 보는 것을 뺀다(GM 지시 2026-09-11) — 빼는 목록은 층에 한 번만 적혀 있다.
    tier = rank_tier(rank)
    perms = {"dept": dept, "rank": rank.strip(), "tier": tier, "phone": _digits(phone),
             "groups": [], "modules": dept_modules_for(dept, tier), "deny": tier_deny(tier)}
    try:
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,role,status,created_at,approved_at,perms) "
                      "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (T, uid, name, salt, h, "staff", status, now(), approved_at, json.dumps(perms, ensure_ascii=False)))
    except _db.IntegrityError:
        return RedirectResponse("/auth/signup?msg=이미 있는 아이디입니다", status_code=303)
    tell_gm(f"🔐 ERP 가입 신청 — {name} ({uid})\n"
            f"{dept} · {rank.strip() or '직급 미기재'} ({'리더급' if tier == 'leader' else '팀원급'})\n"
            f"연락처 {phone.strip()}\n"
            "승인하시면 그때부터 로그인됩니다: https://erp.wellperion.com/auth/admin")
    return RedirectResponse("/auth/signup?msg=접수됐습니다 · GM 승인 뒤 로그인하실 수 있습니다", status_code=303)


@app.post("/auth/logout")
@app.get("/auth/logout")
def logout(next: str = "/", everywhere: str = "", erp_session: Optional[str] = Cookie(default=None)):
    if everywhere:                                 # 모든 기기에서 로그아웃(배 12752 P1 #10) — 세대 +1 로 다른 기기 토큰까지 죽인다
        u = current(erp_session)
        if u:
            _bump_session_ver(u["id"])
    dest = safe_next(next)
    r = RedirectResponse("/auth/login" + (("?next=" + urllib.parse.quote(dest, safe="/?=&")) if dest != "/" else ""), status_code=303)
    r.delete_cookie(COOKIE, path="/")
    return r


@app.get("/auth/check")
def check(request: Request, erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        raise HTTPException(401)
    uri = request.headers.get("x-original-uri", "")             # nginx 가 붙인다(erp.nginx.conf)
    m = module_at(uri)
    path = uri_path(uri)
    # 플랫폼 자리(배 2633)는 카드 검사보다 먼저 — 카드가 붙은 화면은 아래 path_allowed 를 안 타므로
    # 여기서 막지 않으면 파트너사 관리자 등급 계정이 카드 권한만으로 열린다.
    if is_platform_path(path) and (u["email"] or "").lower() not in PLATFORM_ADMINS:
        raise HTTPException(403)
    if m and not allowed(u, m):
        raise HTTPException(403)
    if not m and not path_allowed(u, path):                       # 카드 밖 경로(API·/repo/·보고서·관리자 콘솔…)
        raise HTTPException(403)
    if is_auto_token(erp_session):
        # 사무실 자동 로그인 세션(배1134) — 계정 perms 와 별개로 조회만 허용. 쓰기(GET/HEAD 아닌 요청)와
        # 인사 폴더(chro-*)는 이 세션으로 못 연다 — account_perms.json 이 나중에 바뀌어도 여기서 다시 막는다.
        if ((request.headers.get("x-original-method") or "GET").upper() not in ("GET", "HEAD")
                and not path.startswith(AUTO_LOGIN_WRITE_PREFIXES)):
            raise HTTPException(403)          # 쓰기는 AUTO_LOGIN_WRITE_PREFIXES(피드백 · 종합접수처 처리)뿐
        if m and m["id"].startswith("chro-"):
            raise HTTPException(403)
        # 개인정보 화면·자료도 이 세션으로는 안 연다(배 2574 · 2026-09-15). 사무실 회선과 손님용 와이파이의
        # 공인 IP 가 같다는 소장 회신(2026-09-11) 때문이다 — IP 만으로 여는 세션은 손님 단말에도 열린다.
        # 그 자료를 보려면 평소대로 로그인한다(자동 세션이 아니면 이 블록을 안 탄다).
        if (m and m["id"] in AUTO_LOGIN_DENY_IDS) or MEMBER_DATA_RE.match(path) or _auto_denies_api(path):
            raise HTTPException(403)
    headers = {"X-Erp-User": u["email"], "X-Erp-Role": u["role"]}
    if path.startswith("/api/"):
        headers["X-Erp-Allowed"] = allowed_header(u)              # 쓰기 관문(api_write)이 action 별 카드 권한을 이걸로 판정
        if is_auto_token(erp_session):
            headers["X-Erp-Allowed"] = AUTO_LOGIN_ALLOWED_HEADER   # 자동 세션은 계정 권한과 무관하게 실무진 피드백만
    return Response(status_code=200, headers=headers)


ROLE_LABEL = {"admin": "관리자", "staff": "직원"}   # 화면엔 영문 role 을 그대로 내지 않는다(GM 2026-09-17 「admin 이 뭐야」)
TIER_LABEL = {"leader": "팀 리더", "member": "팀원"}   # 직원 계정은 직급 층으로 부른다(ssot/ranks.json tiers)


def _profile(u) -> dict:
    """계정 화면·/auth/me 가 같이 쓰는 내 정보 — perms 의 dept·rank 는 관리자 콘솔이 적은 값(없으면 빈칸)."""
    p = perms_of(u) or {}
    # 역할 칸 = 시스템 role(admin/staff)이 아니라 직급 층(ranks.json tiers) — 실장·팀장은 「팀 리더」(GM 2026-09-17 「실장인데 왜 직원이야」)
    tier = p.get("tier") or rank_tier(p.get("rank") or "")
    role_label = ROLE_LABEL["admin"] if u["role"] == "admin" else TIER_LABEL.get(tier, ROLE_LABEL["staff"])
    return {"email": u["email"], "name": u["name"], "role": u["role"], "role_label": role_label,
            "dept": p.get("dept") or "", "rank": p.get("rank") or "", "phone": p.get("phone") or "",
            "last_login": str(u["last_login"] or "") if "last_login" in u.keys() else "",
            "social": bool(u["pw"]) is False}


@app.get("/auth/me")
def me(erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        raise HTTPException(401)
    d = _profile(u); d["allowed_ids"] = allowed_ids(u)
    return JSONResponse(d)


@app.get("/auth/account")
def account_page(erp_session: Optional[str] = Cookie(default=None), msg: str = "", err: str = ""):
    """내 계정 — 이름·아이디·부서·직급·역할·최근 로그인·열린 화면 수 + 비밀번호 변경 한 화면(GM 2026-09-17)."""
    u = current(erp_session)
    if not u:
        return RedirectResponse("/auth/login?next=/auth/account", status_code=303)
    d = _profile(u)
    n_allowed = len(allowed_ids(u)) if u["role"] != "admin" else len(modules()) + len(documents())
    rows = [("이름", d["name"] or "—"), ("아이디", d["email"]), ("부서", d["dept"] or "—"), ("직급", d["rank"] or "—"),
            ("역할", d["role_label"]), ("최근 로그인", short_dt(d["last_login"]) or "—"), ("열린 화면", "%d개" % n_allowed)]
    info = "".join(f"<div class=row><span class=k>{escape(k)}</span><b>{escape(str(v))}</b></div>" for k, v in rows)
    pw_form = ("<p class=muted>구글·네이버·카카오로 로그인하는 계정은 비밀번호가 그 서비스에 있습니다.</p>" if d["social"] else f"""
<form method=post action=/auth/password>
<label>현재 비밀번호<input name=current_password type=password autocomplete=current-password required></label>
<label>새 비밀번호<input name=new_password type=password placeholder="8자 이상" minlength=8 autocomplete=new-password required></label>
<button>비밀번호 변경</button></form>""")
    return page("내 계정", head("내 계정 · 정보 확인과 비밀번호 변경") + f"""<div class=box>
<style>.box .row{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);margin:0}}.box .row:last-of-type{{border-bottom:0}}
.box .row .k{{color:var(--ink-soft);font-size:13px}}.box h2{{margin:22px 0 10px;font-size:15px}}
.box form{{padding:0;border:0;background:none;max-width:none;margin:0}}.box .hint{{margin:16px 0 0}}</style>
<h1>내 계정</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
{info}
<h2>비밀번호 변경</h2>{pw_form}
<p class=hint>부서·직급·권한이 다르면 GM 께 한 줄로 알려 주세요 — 관리자 화면에서 고칩니다.</p>
<p class=nav><a href=/home>← 직원 홈</a> · <a href=/auth/logout>로그아웃</a> · <a href="/auth/logout?everywhere=1">모든 기기에서 로그아웃</a></p></div>""")


@app.get("/auth/forbidden")
def forbidden_page(next: str = "/"):
    # nginx @forbidden 의 내부 재작성으로만 도달한다(erp.nginx.conf `location = /auth/forbidden { internal; }`) —
    # 밖에서 이 주소를 직접 열면 404. 옛 주소(/auth/forbidden?next=…)를 받아 주던 처리는 GM 2026-09-16 지시로 지웠다
    # (「다 삭제하고 기록으로만」) — 경위는 저장 이력 c2733fc03·14ece03d4.
    return page("권한 없음", f"""<div class=box><h1>권한 없음</h1>
<p class=err>이 화면은 지금 계정에 허용되지 않았습니다.<br><small>{escape(next)}</small></p>
<p><a href="/auth/logout?next={escape(next)}" class=btn>로그인하기</a></p>
<p class=hint>지금 계정(공용 계정일 수 있습니다)을 내리고 <b>개인 계정</b>으로 다시 로그인합니다 — 구글 로그인은 계정 선택창이 뜹니다.<br>그래도 안 열리면 GM 에게 권한을 요청하세요.</p></div>""")


@app.get("/auth/password")
def password_page(erp_session: Optional[str] = Cookie(default=None), msg: str = "", err: str = ""):
    # 비밀번호 변경은 내 계정 화면 안으로 합쳤다(GM 2026-09-17) — 옛 주소는 그리로 보낸다.
    q = ("?err=" + urllib.parse.quote(err)) if err else (("?msg=" + urllib.parse.quote(msg)) if msg else "")
    return RedirectResponse("/auth/account" + q, status_code=303)


@app.post("/auth/password")
def password_change(request: Request, current_password: str = Form(...), new_password: str = Form(...),
                     erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        return RedirectResponse("/auth/login?next=/auth/account", status_code=303)
    if not u["pw"] or hash_pw(current_password, u["salt"])[1] != u["pw"]:
        return RedirectResponse("/auth/account?err=현재 비밀번호가 맞지 않습니다", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse("/auth/account?err=새 비밀번호는 8자 이상이어야 합니다", status_code=303)
    salt, h = hash_pw(new_password)
    with db() as c:
        # 세대 +1 = 다른 기기·분실 폰의 옛 토큰이 전부 죽는다(배 12752 P1 #10). 이 브라우저는 새 세대 토큰을 다시 받는다.
        c.execute("UPDATE users SET salt=%s, pw=%s, session_ver=session_ver+1 WHERE tenant_id=%s AND id=%s", (salt, h, T, u["id"]))
        u = c.execute("SELECT * FROM users WHERE tenant_id=%s AND id=%s", (T, u["id"])).fetchone()
    r = RedirectResponse("/auth/account?msg=비밀번호가 바뀌었습니다 · 다른 기기는 모두 로그아웃됐습니다", status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(COOKIE, issue(u), max_age=_keep_max_age(request.cookies.get("erp_keep", "1")), httponly=True, samesite="lax", path="/", secure=https)
    return r


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
    touch_login(u["id"])
    r = RedirectResponse(nxt, status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(COOKIE, issue(u), max_age=_keep_max_age(request.cookies.get("erp_keep", "1")), httponly=True, samesite="lax", path="/", secure=https)
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
    rank_opts = "".join(f"<option value='{escape(r)}'>{escape(r)}</option>" for r in rank_names())
    # 직급도 받는다(2026-09-14 점검 높음 12번) — 아이디 가입(signup)과 같은 층(팀장/팀원) 규칙이 소셜 가입에도 걸리게.
    return page("가입 완료", head(f"{label} 로그인 확인 · 이름·부서·직급만 알려주세요") + f"""<form method=post action={action}>
<h1>가입 완료</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<p class=hint>{escape(claims.get('m') or claims['e'])} 계정으로 계속합니다.</p>
<label>이름<input name=name value="{escape(claims['n'])}" placeholder="직함 포함, 예: 홍길동 매니저" required></label>
<label>부서<select name=dept required><option value=''>선택하세요</option>{opts}</select></label>
<label>직급<select name=rank required><option value=''>선택하세요</option>{rank_opts}</select></label>
<input type=hidden name=t value="{escape(t)}"><input type=hidden name=next value="{escape(next)}">
<button>신청</button><div class=foot><p>신청하면 GM 께 알림이 가고, 승인되면 부서 화면으로 로그인할 수 있습니다.</p></div></form>""")


def _finish_submit(name: str, dept: str, t: str, next: str, action: str, rank: str = "") -> Response:
    try:
        claims = _finish_claims(t)
    except ValueError as e:
        return RedirectResponse(f"/auth/login?err={e}", status_code=303)
    if dept not in DEPTS:
        return RedirectResponse(f"{action}?t={t}&next={urllib.parse.quote(next, safe='')}&err=부서를 선택하세요", status_code=303)
    email, salt_pw = claims["e"], secrets.token_urlsafe(32)     # 소셜 전용 계정 — 비밀번호 로그인은 못 쓴다
    salt, h = hash_pw(salt_pw)
    tier = rank_tier(rank)                                      # 모르는 값·빈 값 = 팀원급(좁은 쪽) — signup 과 같은 규칙
    perms = json.dumps({"dept": dept, "rank": rank.strip(), "tier": tier, "groups": [],
                        "modules": dept_modules_for(dept, tier), "deny": tier_deny(tier)}, ensure_ascii=False)
    try:
        with db() as c:
            c.execute("INSERT INTO users(tenant_id,email,name,salt,pw,created_at,perms) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                      (T, email, name.strip(), salt, h, now(), perms))
    except _db.IntegrityError:
        pass                                    # 중복 제출 — 이미 신청돼 있으니 그대로 대기 안내만
    provider = claims.get("p")                  # 구글(기본 흐름)은 문구 그대로, 네이버·카카오만 계정 종류를 덧붙인다
    suffix = f" · {SOCIAL[provider]['label']} 계정" if provider else ""
    if claims.get("m"):                          # 소셜 키(kakao_123@kakao.login)만으론 GM 이 누군지 모른다 — 이메일을 덧붙인다
        suffix += f" · 이메일 {claims['m']}"
    tell_gm(f"🔐 ERP 가입 신청 — {name.strip()} ({email} · {dept}{suffix})\n승인: https://erp.wellperion.com/auth/admin")
    return RedirectResponse("/auth/login?msg=신청됐습니다. GM 승인 후 로그인할 수 있습니다", status_code=303)


@app.get("/auth/google/finish")
def google_finish_page(t: str = "", next: str = "/", err: str = ""):
    return _finish_page(t, next, err, "/auth/google/finish")


@app.post("/auth/google/finish")
def google_finish(name: str = Form(...), dept: str = Form(...), t: str = Form(...), next: str = Form("/"), rank: str = Form("")):
    return _finish_submit(name, dept, t, next, "/auth/google/finish", rank)


@app.get("/auth/social/finish")
def social_finish_page(t: str = "", next: str = "/", err: str = ""):
    return _finish_page(t, next, err, "/auth/social/finish")


@app.post("/auth/social/finish")
def social_finish(name: str = Form(...), dept: str = Form(...), t: str = Form(...), next: str = Form("/"), rank: str = Form("")):
    return _finish_submit(name, dept, t, next, "/auth/social/finish", rank)


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
    """(계정 키, 표시 이름, 이메일). 계정 키 = {provider}_{id}@{provider}.login — 공급자 안의 고유 id 로만 맞춘다.
    이메일은 화면·GM 알림용이지 키가 아니다(배 12750 P0 #1 · 2026-09-18): 카카오 대표 이메일은 본인 확인 없이
    아무 주소나 적을 수 있어(is_email_verified=false) 이메일을 키로 쓰면 그 주소의 기존 계정(관리자 포함)에 그대로
    붙는다. 검증된 이메일이라도 아이디·구글로 만든 기존 계정과 자동 결합하지 않는다 — 소셜 키로는 그 행을 못 찾으니
    새 신청(승인 대기)으로 흘러 GM 이 /auth/admin 에서 결정한다. 카카오 이메일은 검증된 것만 넘긴다."""
    if provider == "naver":
        r = profile.get("response") or {}
        email = (r.get("email") or "").strip().lower()
        if not email:
            raise ValueError("네이버 계정에 이메일 제공 동의가 필요합니다")
        return f"naver_{r['id']}@naver.login", (r.get("name") or email.split("@")[0]).strip(), email
    acct = profile.get("kakao_account") or {}
    email = (acct.get("email") or "").strip().lower() if acct.get("is_email_verified") else ""
    key = f"kakao_{profile['id']}@kakao.login"
    name = ((acct.get("profile") or {}).get("nickname") or (email or key).split("@")[0]).strip()
    return key, name, email


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
        email, name, mail = _social_identity(provider, profile)   # email = 계정 키(공급자 id) · mail = 표시·알림용
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
        touch_login(u["id"])
        r = RedirectResponse(nxt, status_code=303)
        https = request.headers.get("x-forwarded-proto") == "https"
        r.set_cookie(COOKIE, issue(u), max_age=_keep_max_age(request.cookies.get("erp_keep", "1")), httponly=True, samesite="lax", path="/", secure=https)
        return r
    reg = jwt.encode({"e": email, "n": name, "p": provider, "m": mail, "exp": int(time.time()) + 600}, SECRET, algorithm="HS256")
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
        "ranks": rank_names(),                 # 승인 화면 직급 드롭다운(배2539) — 정본은 ssot/ranks.json 하나
        "teams": {TEAM_DEPT: team_names()},    # 파트너팀 안 팀 목록(GM 2026-09-18) — 정본은 ssot/kpi.json 팀 리더 표
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
        keep = {k: p[k] for k in ("rank", "tier", "phone") if p.get(k)}      # 직급·층·연락처는 그대로(부서 일괄이 지우지 않는다)
        _set_perms(r["id"], {"dept": dept, **keep, "groups": [], "modules": dept_modules_for(dept, p.get("tier") or "member"), "deny": p.get("deny", [])}, me["email"])
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


# ── ERP관리 층 API (GM 구조 2026-09-14: 플랫폼=셋업 → 관리=배치 → 홈=사용) — erp/index.html 관리자 층이 부른다 ──
def _admin_json_gate(erp_session, erp_admin):
    """관리자 + 관리자 비밀번호 창 안이면 사용자 행, 아니면 401 JSON(화면이 unlock 으로 보낸다)."""
    u = current(erp_session)
    if not u or u["role"] != "admin" or (ADMIN_PW and not _admin_unlocked(erp_admin, u["id"])):
        raise HTTPException(401, "관리자 확인 필요")
    return u


@app.get("/auth/admin/api/modules")
def admin_api_modules(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    """모듈 배치 — 플랫폼에 셋업된 모듈 전부 + 이 회사에서 끈 것."""
    _admin_json_gate(erp_session, erp_admin)
    off = modules_off()
    return JSONResponse({"modules": [{"id": m["id"], "name": m.get("name") or m["id"], "group": m.get("group") or "",
                                      "appgroup": m.get("appgroup") or "", "staff": m.get("staff") or "",
                                      "core": bool(m.get("core")), "off": m["id"] in off} for m in modules()
                                     if m.get("kind") != "doc"],   # 보고 문서는 모듈이 아니다(GM 09-15 · 배 12666) — 배치 목록에서 뺀다
                         "off": sorted(off)})


@app.post("/auth/admin/api/modules")
async def admin_api_modules_save(request: Request, erp_session: Optional[str] = Cookie(default=None),
                                 erp_admin: Optional[str] = Cookie(default=None)):
    """끌 모듈 목록 저장(form off=id 여러 개) — 모르는 id 는 버린다. 저장 즉시 직원 카드·관문에 반영."""
    me = _admin_json_gate(erp_session, erp_admin)
    form = await request.form()
    ids = {m["id"] for m in modules()}
    off = [v for v in form.getlist("off") if v in ids]
    _save_modules_off(off, me["email"])
    return JSONResponse({"ok": True, "off": sorted(set(off))})


@app.get("/auth/admin/api/eval_kpi")
def admin_api_eval_kpi(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    """평가 KPI 설정 원장(회사·관리자·파트너 세 절) — ERP 관리자 「평가」·랩스 「파트너사 평가」가 읽는다."""
    _admin_json_gate(erp_session, erp_admin)
    return JSONResponse(eval_kpi_load())


@app.post("/auth/admin/api/eval_kpi")
async def admin_api_eval_kpi_save(request: Request, erp_session: Optional[str] = Cookie(default=None),
                                  erp_admin: Optional[str] = Cookie(default=None)):
    """KPI 설정 저장(JSON 본문 {company,manager,partner}) — 세 절·정해진 칸만 남기고 통째로 교체."""
    me = _admin_json_gate(erp_session, erp_admin)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "JSON 본문이 아닙니다")
    if not isinstance(body, dict):
        raise HTTPException(400, "본문은 객체여야 합니다")
    return JSONResponse({"ok": True, "kpi": eval_kpi_save(body, me["email"])})


_USAGE_AREAS = (("reg_", "접수"), ("lf_", "접수"), ("voc_", "접수"), ("hold_complete", "접수"),
                ("todo_", "업무"), ("approval_", "업무"), ("member_inquiry", "문의"), ("lesson_inquiry", "문의"),
                ("member_", "회원"), ("save_schedule", "일정"), ("snapshot_append", "점검"), ("save", "점검"),
                ("unlock_round", "점검"), ("asset_", "구매"), ("proc", "구매"), ("add", "구매"))


def usage_area(action: str) -> str:
    """write_log 의 action → 사람이 읽는 영역 이름(접두 표 · 순서가 우선순위)."""
    a = str(action or "")
    for prefix, area in _USAGE_AREAS:
        if a.startswith(prefix):
            return area
    return "기타"


@app.get("/auth/admin/api/usage")
def admin_api_usage(erp_session: Optional[str] = Cookie(default=None), erp_admin: Optional[str] = Cookie(default=None)):
    """사용 현황 — 계정별 마지막 로그인·30일 저장 횟수·많이 쓴 영역 / 영역별 저장·쓴 사람·마지막 저장(서버 원장 write_log)."""
    _admin_json_gate(erp_session, erp_admin)
    since = (datetime.now(KST) - timedelta(days=30)).strftime("%Y-%m-%d")
    with db() as c:
        users = c.execute("SELECT id, email, name, role, status, last_login FROM users WHERE tenant_id=%s ORDER BY id", (T,)).fetchall()
        rows = c.execute("SELECT user_email, action, MAX(at) last_at, COUNT(*) n FROM write_log "
                         "WHERE tenant_id=%s AND at >= %s AND gas_status <> 'test' GROUP BY user_email, action", (T, since)).fetchall()
    per_user: dict = {}
    per_area: dict = {}
    for r in rows:
        email, area = (r["user_email"] or "").lower(), usage_area(r["action"])
        u = per_user.setdefault(email, {"writes": 0, "last": "", "areas": {}})
        u["writes"] += r["n"]; u["last"] = max(u["last"], r["last_at"] or "")
        u["areas"][area] = u["areas"].get(area, 0) + r["n"]
        a = per_area.setdefault(area, {"writes": 0, "last": "", "users": set()})
        a["writes"] += r["n"]; a["last"] = max(a["last"], r["last_at"] or "")
        if email:
            a["users"].add(email)
    out_users = []
    for x in users:
        u = per_user.get((x["email"] or "").lower(), {"writes": 0, "last": "", "areas": {}})
        top = sorted(u["areas"].items(), key=lambda kv: -kv[1])[:3]
        out_users.append({"email": x["email"], "name": x["name"], "role": x["role"], "status": x["status"],
                          "last_login": x["last_login"] or "", "writes_30d": u["writes"], "last_write": u["last"],
                          "areas": [{"area": k, "n": n} for k, n in top]})
    out_areas = [{"area": k, "writes_30d": v["writes"], "users": len(v["users"]), "last_write": v["last"]}
                 for k, v in sorted(per_area.items(), key=lambda kv: -kv[1]["writes"])]
    return JSONResponse({"users": out_users, "areas": out_areas, "since": since})


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
    # 2026-09-11 GM 지시로 가입 경로에서는 명부를 안 본다 — 이 값이 비어도 가입은 안 막힌다.
    state = "설정됨" if hr_hub_pw() else "비어 있음 (가입 신청과는 무관 — 명부를 쓰는 다른 자리용)"
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
    # ★가입 때 적힌 부서·직급·층·연락처·잠금은 남긴다(2026-09-14 점검 높음 11번) — 종전엔 세 칸짜리 새 dict 로
    #   통째 덮어써 저장 한 번에 부서가 「미분류」가 되고 「부서 기본 한 번에」에서 영영 빠지고 잠금도 풀렸다.
    with db() as c:
        row = c.execute("SELECT perms FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
    keep = {k: v for k, v in _row_perms(row).items() if k in ("dept", "rank", "tier", "phone", "locked", "team")} if row else {}
    if form.get("reset"):
        # 「기본(핵심만)」 = 매일 쓰는 화면만. perms 가 None 이면 allowed() 가 core 만 여는데, 신원 칸을 남기려면
        # dict 여야 하므로 같은 뜻인 groups=["핵심"] 로 적는다(allowed(): 핵심 그룹 = core 모듈 전부).
        perms = {**keep, "groups": ["핵심"], "modules": [], "deny": []} if keep else None
    else:
        perms = {**keep,
                 "groups": [g for g in form.getlist("g") if g in GROUPS],
                 "modules": [m for m in form.getlist("m") if m in ids],
                 "deny": [m for m in form.getlist("d") if m in ids]}
    _set_perms(uid, perms, me["email"])
    return RedirectResponse("/auth/admin?msg=저장됐습니다", status_code=303)


@app.post("/auth/admin/{uid}/team")
async def team_save(uid: int, request: Request, erp_session: Optional[str] = Cookie(default=None),
                    erp_admin: Optional[str] = Cookie(default=None)):
    """파트너팀 계정의 팀(P.T팀·골프팀 …)만 적는다 — 권한(modules·deny)은 안 건드린다(GM 2026-09-18 구분용).
    빈 값 = 팀 미지정. 목록 밖 값은 400."""
    me = admin_only(erp_session, erp_admin)
    team = str((await request.form()).get("team") or "").strip()
    if team and team not in team_names():
        raise HTTPException(400, "모르는 팀")
    with db() as c:
        row = c.execute("SELECT perms FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
    if not row:
        raise HTTPException(404)
    p = _row_perms(row)
    if p.get("dept") != TEAM_DEPT:
        raise HTTPException(400, f"{TEAM_DEPT} 계정만 팀을 둔다")
    if (p.get("team") or "") == team:
        return JSONResponse({"ok": True, "team": team})
    p["team"] = team
    _set_perms(uid, p, me["email"])
    return JSONResponse({"ok": True, "team": team})


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
async def admin_action(uid: int, action: str, request: Request, erp_session: Optional[str] = Cookie(default=None),
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
    if action == "approve":
        # 승인자가 직급을 마지막으로 고친다(배2539 · GM 2026-09-11). 신청자가 고른 값은 자기 신고일 뿐이고,
        # 리더급/팀원급으로 보이는 화면이 갈리므로 교정 지점이 승인자여야 한다. 안 고르면 신청 값 그대로 간다.
        _approve_rank(uid, await _body_rank(request), me["email"])
    with db() as c:
        c.execute("UPDATE users SET status=%s, approved_at=%s WHERE tenant_id=%s AND id=%s AND role!='admin'",
                  ("active" if action == "approve" else "blocked", now() if action == "approve" else None, T, uid))
        if action == "block":                      # 차단 해제 뒤에도 옛 토큰이 되살아나지 않게 세대 +1(배 12752 P1 #10)
            c.execute("UPDATE users SET session_ver=session_ver+1 WHERE tenant_id=%s AND id=%s AND role!='admin'", (T, uid))
    return RedirectResponse("/auth/admin", status_code=303)


async def _body_rank(request: Request) -> str:
    """요청 본문의 rank 값. 화면은 폼(urlencoded)으로 보낸다 — 다른 동작(차단·삭제)은 본문 없이 오므로 빈 문자열."""
    try:
        return str((await request.form()).get("rank") or "").strip()
    except Exception:
        return ""


def rank_modules(dept: str, old_tier: str, new_tier: str, mods: list) -> list:
    """직급 층이 바뀔 때의 modules(배 12752 P1 #12) — 새 층의 부서 기본(leader_extra 포함) + 옛 층 부서 기본에 없던 것(개인 예외로 켠 것)은 그대로.
    종전엔 승인 화면에서 사원→팀장으로 고쳐도 tier 만 바뀌고 modules 가 가입 때 값이라 회원·문의 화면이 안 열렸다(반대도)."""
    base_old = set(dept_modules_for(dept, old_tier))
    new = dept_modules_for(dept, new_tier)
    return new + [m for m in (mods or []) if m not in base_old and m not in new]


def _approve_rank(uid: int, rank: str, by: str) -> None:
    """직급을 바꾸면 층(tier)·팀원급 제외 화면(deny)·부서 모듈(modules)도 같이 따라간다 — 네 값을 따로 고치면 어긋난다. 부서가 없으면 modules 는 그대로."""
    if not rank or rank not in rank_names():
        return
    with db() as c:
        row = c.execute("SELECT perms FROM users WHERE tenant_id=%s AND id=%s", (T, uid)).fetchone()
    if not row:
        return
    try:
        p = json.loads(row["perms"]) if row["perms"] else {}
    except ValueError:
        p = {}
    if not isinstance(p, dict):
        p = {}
    if p.get("rank") == rank:
        return
    tier = rank_tier(rank)
    old_tier = p.get("tier") or rank_tier(p.get("rank") or "")
    p["rank"], p["tier"], p["deny"] = rank, tier, tier_deny(tier)
    if p.get("dept"):
        p["modules"] = rank_modules(p["dept"], old_tier, tier, p.get("modules"))
    _set_perms(uid, p, by)


init()


if __name__ == "__main__":                     # 회사 계정 판별 자가점검: python app.py
    # 오픈 리다이렉트 차단(2026-09-05 검수 M2)
    assert safe_next("/erp/") == "/erp/"
    assert safe_next("//evil.example") == "/"                 # '/' 로 시작하지만 '//' 는 외부 도메인으로 튄다
    assert safe_next("evil.example") == "/"                    # '/' 로 시작 안 함
    assert safe_next("//evil.example", "/auth/admin") == "/auth/admin"
    assert safe_next("/\\evil.example") == "/"                # 브라우저는 '\' 를 '/' 로 읽는다(2026-09-14 점검)
    # 카드 밖 경로 권한(2026-09-14 점검 · 치명 2·3번) — 관리자 전용 접두·회원 자료·API·폴더 화면
    _adm = {"role": "admin", "email": "a@x", "perms": None}
    _stf = {"role": "staff", "email": "s@x", "perms": json.dumps({"modules": ["cpo-member-lesson"], "groups": [], "deny": []})}
    assert path_allowed(_adm, "/repo/scripts/x.py") and not path_allowed(_stf, "/repo/scripts/x.py")
    # 짧은 주소 /home·/guide 는 가이드 화면과 같은 경로로 판정된다(2026-09-16 · 직원 계정 403 사고)
    assert uri_path("/home") == "/wellperion_guide(main).html" == uri_path("/guide?x=1") == uri_path("/wellperion_guide(main).html#S3")
    # 플랫폼관리 = 회사 계정 관리자만(GM 2026-09-14) — 관리자 등급이라도 개인 아이디는 못 연다
    # 표본 이메일은 실제 PLATFORM_ADMINS 와 절대 겹치면 안 된다 — 겹치면(예: 서버 env 에 GM 개인 계정이
    # 들어간 경우) 아래 assert 들이 전부 실패해 자가점검이 죽는다(2026-09-18 서버 AssertionError 원인).
    assert "personal-admin@example.test" not in PLATFORM_ADMINS
    _adm_personal = {"role": "admin", "email": "personal-admin@example.test", "perms": None}
    _adm_company = {"role": "admin", "email": "cao@wellperion.com", "perms": None}
    assert path_allowed(_adm_company, uri_path("/erp/admin/")) and path_allowed(_adm_company, "/erp/admin/index.html")
    assert not path_allowed(_adm_personal, uri_path("/erp/admin/")) and not path_allowed(_adm_personal, "/erp/admin/clevel-guide.html")
    assert path_allowed(_adm_personal, "/repo/scripts/x.py")      # 그 밖은 관리자 등급 그대로
    # 파트너사 경로에 남아 있는 플랫폼 화면(배 2633) — 회사 계정만. 자리 이동 전에 권한으로 먼저 막는다.
    for _p in ("/자율현황.html", "/cto/aws_migration.html", "/cbo/counsel_admin.html",
               "/cbo/dietcamp/index.html", "/cbo/gocheokgolf/admin.html", "/cbo/model/x.html"):
        assert path_allowed(_adm_company, _p), _p
        assert not path_allowed(_adm_personal, _p), _p
        assert not path_allowed(_stf, _p), _p
    assert path_allowed(_adm_personal, "/cto/automation/index.html")   # 같은 폴더의 다른 화면은 그대로 열린다
    # 카드가 붙은 화면도 걸러야 한다 — check() 가 카드 검사 전에 이 판정을 건다.
    assert is_platform_path("/자율현황.html") and is_platform_path("/repo/3. 웰페리온 가이드/자율현황.html")
    assert is_platform_path("/cbo/dietcamp/") and is_platform_path(uri_path("/erp/admin/"))
    assert not is_platform_path("/cpo/member/membership.html") and not is_platform_path("/cto/automation/index.html")
    # 자동 로그인 세션이 못 여는 자리(배 2574) — 손님용 와이파이가 사무실과 같은 공인 IP 라서.
    assert _auto_denies_api("/api/members") and _auto_denies_api("/api/inquiries/list") and _auto_denies_api("/api/hr/x")
    assert not _auto_denies_api("/api/check/list") and not _auto_denies_api("/api/todo")
    assert "member" in AUTO_LOGIN_DENY_IDS and "inquiry" in AUTO_LOGIN_DENY_IDS
    assert "cpo-member-실무진피드백" not in AUTO_LOGIN_DENY_IDS and AUTO_LOGIN_ALLOWED_HEADER.startswith("auto-login,")   # GM 2026-09-16
    assert "/api/reception/update".startswith(AUTO_LOGIN_WRITE_PREFIXES) and not "/api/members/write".startswith(AUTO_LOGIN_WRITE_PREFIXES)
    assert MEMBER_DATA_RE.match("/status/member_active_snapshot.json")
    assert path_allowed(_stf, "/repo/status/monthly_ops_plan.json") and path_allowed(_stf, "/repo/ssot/kpi.json")   # 화면이 읽는 데이터
    assert not path_allowed(_stf, "/repo/status/member_active_snapshot.json") and not path_allowed(_stf, "/repo/logs/a.log")
    assert path_allowed(_stf, "/repo/3. 웰페리온 가이드/coo/bootsetup_matrix.json") and not path_allowed(_stf, "/repo/3. 웰페리온 가이드/reports/x.html")
    assert not path_allowed(_stf, "/reports/x.html") and not path_allowed(_stf, "/erp/admin/") and not path_allowed(_stf, "/api/members")
    # 홈 모듈만 가진 직원(카드 없음) — 회원·강습 개인정보 API 는 못 열고, 홈이 실제로 fetch 하는 접두만 연다(2026-09-18 구멍 수리).
    _stf_home = {"role": "staff", "email": "home@x", "perms": json.dumps({"modules": [], "groups": [], "deny": []})}
    assert not path_allowed(_stf_home, "/api/members") and not path_allowed(_stf_home, "/api/lesson/members")
    assert path_allowed(_stf_home, "/api/inquiries") and path_allowed(_stf_home, "/api/lesson/stats")
    # 보고 문서(kind=doc, 배 12666) — 카드 밖으로 떨어져도 직원은 못 연다 · 관리자는 그대로
    assert not path_allowed(_stf, "/coo/chairman/x.html") and path_allowed(_adm, "/coo/chairman/x.html")
    assert not path_allowed(_stf, uri_path("/erp/admin/")) and not path_allowed(_stf, uri_path("/repo/"))   # 폴더 요청(끝 슬래시 떼임)
    assert not path_allowed(_stf, uri_path("/chro/hub/")) and path_allowed(_stf, uri_path("/cpo/member/"))  # 폴더 = 같은 폴더 카드로
    assert path_allowed(_stf, "/api/lesson/members") and path_allowed(_stf, "/api/write") and path_allowed(_stf, "/erp/")
    assert not path_allowed(_stf, "/status/member_active_snapshot.json") and path_allowed(_stf, "/status/monthly_ops_plan.json")
    assert allowed_header(_adm) == "*" and "cpo-member-lesson" in allowed_header(_stf)
    # 모듈 배치(2026-09-14) — 끈 모듈은 직원에게 안 열리고 관리자는 그대로 · 영역 이름 표
    import tempfile
    _real_switch = MODULE_SWITCH
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as _tf:
        json.dump({"off": ["check"]}, _tf)
    MODULE_SWITCH, _SWITCH = _tf.name, (None, frozenset())
    _chk = {"id": "check", "group": "시우", "core": False}
    assert not allowed({"role": "staff", "email": "s@x", "perms": '{"groups":["시우"]}'}, _chk)
    assert allowed({"role": "admin", "email": "cao@wellperion.com", "perms": None}, _chk)
    MODULE_SWITCH, _SWITCH = _real_switch, (None, frozenset())
    os.unlink(_tf.name)
    assert usage_area("todo_add") == "업무" and usage_area("reg_update") == "접수" and usage_area("member_inquiry_add") == "문의"
    assert usage_area("member_owner_save") == "회원" and usage_area("saveBoard") == "점검" and usage_area("zzz") == "기타"
    assert not valid_username("x@wellperion.com")               # 회사 이메일 형태 자동 활성 갈래는 없앴다(치명 1번)
    # 폴더 index.html 모듈 권한 판정(2026-09-05 검수 H2) — /chro/hub 든 /chro/hub/ 든 같은 모듈로 잡혀야 한다.
    # MODULES 를 없는 경로로 돌려 modules()의 os.stat 이 항상 실패하게 만든다 — 그래야 실제
    # /srv/erp/www/erp/modules.json 이 있는 서버에서도 이 임시 _MODS 가 재로딩으로 덮이지 않는다.
    _real_modules_path, MODULES = MODULES, "/__selftest_no_such_modules_json__"
    _MODS = (None, [], {"/chro/hub/index.html": {"id": "chro-hub-index"}, "/check.html": {"id": "check"},
                        "/cpo/member/membership.html": {"id": "member", "group": "시포", "core": True}})
    assert module_at("/chro/hub/")["id"] == "chro-hub-index"
    assert module_at("/chro/hub")["id"] == "chro-hub-index"
    assert module_at("/check")["id"] == "check"                # 기존 .html 생략 보정은 그대로
    assert module_at("/check.html")["id"] == "check"
    assert module_at("/없는경로/") is None
    # 문서(kind=doc, 배 12666 남은 절반) — modules 배열 밖(documents)으로 빠지면 module_at 은 못 찾고 doc_at 이 찾는다.
    # path_allowed 는 doc_at 을 먼저 본다 — 같은 폴더에 열린 카드(member)가 있어도 문서는 개인 예외로만 연다.
    # 이 assert 가 없으면 「빼면 폴더 대체판정이 더 연다」(오전 배 12666 note)는 회귀를 못 잡는다.
    _DOCS = (None, [], {"/cpo/member/실무진피드백.html": {"id": "cpo-member-실무진피드백"}})
    assert doc_at("/cpo/member/실무진피드백.html")["id"] == "cpo-member-실무진피드백"
    assert doc_at("/cpo/member/실무진피드백")["id"] == "cpo-member-실무진피드백"    # .html 생략도 module_at 과 같이
    assert doc_at("/없는문서") is None
    _stf2 = {"role": "staff", "email": "s2@x", "perms": json.dumps({"modules": ["member"], "groups": [], "deny": []})}
    _exc = {"role": "staff", "email": "exc@x",
            "perms": json.dumps({"modules": ["member", "cpo-member-실무진피드백"], "groups": [], "deny": []})}
    assert path_allowed(_stf2, "/cpo/member/membership.html")         # 카드는 그대로 열린다(비교군)
    assert not path_allowed(_stf2, "/cpo/member/실무진피드백.html")    # 같은 폴더 카드가 있어도 문서는 개인 예외 없인 막힘
    assert path_allowed(_exc, "/cpo/member/실무진피드백.html")         # modules 로 콕 집으면(개인 예외) 열린다
    assert path_allowed(_adm, "/cpo/member/실무진피드백.html")         # 관리자는 그대로
    MODULES = _real_modules_path
    _MODS = (None, [], {})                                     # 다음 modules() 호출이 실제 파일에서 다시 읽도록 리셋
    _DOCS = (None, [], {})

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
    # 네이버·카카오(배1108 → 배 12750 P0 #1) — 계정 키 = {provider}_{id}@{provider}.login 하나. 이메일은 셋째 값(표시·알림).
    # _social_callback 은 이 키로만 users 를 찾는다 → 이메일 칸으로 만든 기존 계정(관리자 포함)은 소셜 로그인으로 못 연다.
    assert _social_identity("naver", {"response": {"id": "n1", "email": "A@Test.com", "name": "홍길동"}}) == ("naver_n1@naver.login", "홍길동", "a@test.com")
    try:
        _social_identity("naver", {"response": {"id": "n1"}})
        assert False, "네이버 이메일 없으면 ValueError 여야 한다"
    except ValueError:
        pass
    assert _social_identity("kakao", {"id": 123, "kakao_account": {}}) == ("kakao_123@kakao.login", "kakao_123", "")
    admin_mail = "cao@wellperion.com"
    # 케이스 1 · 미검증 이메일(누구나 적을 수 있는 카카오 대표 이메일)을 관리자 주소로 적고 들어와도 키가 되지 않는다 → 결합 안 됨
    k1 = _social_identity("kakao", {"id": 123, "kakao_account": {"email": admin_mail, "is_email_verified": False,
                                                                 "profile": {"nickname": "닉네임"}}})
    assert k1 == ("kakao_123@kakao.login", "닉네임", ""), k1           # 미검증 이메일은 알림에도 안 실린다
    # 케이스 2 · 검증된 이메일이 기존 계정과 같아도 키는 여전히 카카오 id → 기존 행과 안 맞아 가입 신청(승인 대기)으로 흐른다
    k2 = _social_identity("kakao", {"id": 123, "kakao_account": {"email": admin_mail, "is_email_verified": True,
                                                                 "profile": {"nickname": "닉네임"}}})
    assert k2 == ("kakao_123@kakao.login", "닉네임", admin_mail), k2   # 이메일은 GM 알림용으로만 셋째 값에
    assert k1[0] != admin_mail and k2[0] != admin_mail                  # 어느 경우도 이메일이 계정 키가 아니다
    reg = jwt.encode({"e": k2[0], "n": k2[1], "p": "kakao", "m": k2[2], "exp": int(time.time()) + 60}, SECRET, algorithm="HS256")
    assert _finish_claims(reg)["m"] == admin_mail                        # 가입 토큰이 이메일을 GM 알림까지 나른다
    assert set(SOCIAL) == {"naver", "kakao"}
    # 승인 화면 직급 교정(배2539) — 직급을 고치면 층·제외 화면이 함께 따라와야 한다.
    # 세 값이 갈라지면 팀원급이 리더급 화면을 보게 된다.
    assert "팀장" in rank_names() and rank_tier("팀장") == "leader"
    assert tier_deny(rank_tier("팀장")) == []
    assert rank_tier("사원") == "member"
    assert tier_deny(rank_tier("사원")) == list(ranks_raw().get("member_deny") or [])
    assert rank_tier("없는직급") == "member"      # 모르는 값은 좁은 쪽으로
    # 승인 때 직급 층이 바뀌면 modules 도 재계산(배 12752 P1 #12) — 파트너팀 leader_extra(member·inquiry)가 붙고 떨어진다 · 개인 예외는 유지
    _pt_member, _pt_leader = dept_modules_for("파트너팀", "member"), dept_modules_for("파트너팀", "leader")
    assert set(_pt_leader) - set(_pt_member) == set(ranks_raw()["leader_extra"]["파트너팀"])
    _up = rank_modules("파트너팀", "member", "leader", _pt_member + ["coo-chairman-gm업무"])
    assert set(_up) == set(_pt_leader) | {"coo-chairman-gm업무"} and len(_up) == len(set(_up))          # 사원→팀장: extra 붙고 개인 예외 유지
    _down = rank_modules("파트너팀", "leader", "member", _pt_leader + ["coo-chairman-gm업무"])
    assert set(_down) == set(_pt_member) | {"coo-chairman-gm업무"}                                        # 팀장→사원: extra 떨어지고 개인 예외 유지
    assert rank_modules("파트너팀", "member", "member", _pt_member) == _pt_member                         # 같은 층 = 그대로
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
    assert hr_match("홍길동", "010-1234-5678", roster)          # 이름 공백 무시하고 일치
    assert hr_match("홍길동", "", roster)                        # ★이름만 맞으면 통과(GM 2026-09-11)
    assert hr_match("홍길동 매니저", "", roster)                 # 직함이 붙어 와도 통과
    assert hr_match("홍길동", "010-9999-9999", roster)          # 전화가 달라도 이름이 맞으면 통과
    assert not hr_match("김철수", "010-9999-8888", roster)      # 재직상태=퇴직이면 불일치
    assert not hr_match("없는사람", "010-0000-0000", roster)    # ★이름이 명부에 없으면 막힌다
    assert not hr_match("", "", roster)
    # 한 글자 이름이 남의 이름 안에 들어맞아 통과하는 것 차단
    assert not hr_match("홍길동", "", [{"성명": "홍", "재직 상태": "재직"}])
    # 사무실 자동 로그인 세션 표시(배1134) — 일반 로그인은 claim 이 없고, 자동 로그인만 auto=true.
    fake_user = {"id": 1, "email": OFFICE_AUTO_LOGIN_ACCOUNT, "role": "staff"}
    assert not is_auto_token(issue(fake_user))
    assert is_auto_token(issue(fake_user, auto=True))
    assert not is_auto_token(None)
    assert not is_auto_token("깨진토큰")
    # 세션 세대(배 12752 P1 #10) — 토큰의 ver 는 발급 때 user 행의 session_ver · 열이 없는 옛 행·ver 없는 옛 토큰은 0세대로 읽는다.
    assert session_ver(fake_user) == 0 and session_ver({**fake_user, "session_ver": 3}) == 3 and session_ver({**fake_user, "session_ver": None}) == 0
    assert jwt.decode(issue(fake_user), SECRET, algorithms=["HS256"])["ver"] == 0
    assert jwt.decode(issue({**fake_user, "session_ver": 2}), SECRET, algorithms=["HS256"])["ver"] == 2
    _old_tok = jwt.encode({"uid": 1, "email": "x", "role": "staff", "exp": int(time.time()) + 60}, SECRET, algorithm="HS256")
    assert "ver" not in jwt.decode(_old_tok, SECRET, algorithms=["HS256"])           # 배포 전 토큰 = ver 없음 → current() 가 0세대와 같다고 본다
    print("self-check ok")
