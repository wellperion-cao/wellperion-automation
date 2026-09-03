"""웰페리온 ERP 로그인 관문 (AWS 서버 · FastAPI · SQLite).

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
    POST /auth/admin/{uid}/{action}   — approve | block | toggle_role

권한(users.perms · JSON · NULL 이면 modules.json 의 roles 규칙 그대로 = 종전 동작)
    {"groups":["시포","핵심"], "modules":["check"], "deny":["member"]}
    admin 역할은 전부 허용. 판정은 allowed() 한 곳 — /auth/check · /auth/me · 관리자 화면이 같이 쓴다.

환경변수(/srv/erp/auth.env · 서버 밖으로 안 나감)
    ERP_JWT_SECRET  서명 키        TG_BOT_TOKEN / TG_CHAT_ID  가입 신청 알림(업무보고방)
    ERP_ADMIN_EMAIL 첫 관리자     ERP_ADMIN_PW 첫 관리자 비밀번호(첫 기동 때만 씀)
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import secrets
import sqlite3
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

DB = os.environ.get("ERP_AUTH_DB", "/srv/erp/auth.db")
MODULES = os.environ.get("ERP_MODULES", "/srv/erp/www/erp/modules.json")   # 자동 생성본(GitHub 동기화) · 여기서 수정 안 함
GROUPS = ("핵심", "시포", "시모", "시우", "웰리", "시토", "시보", "시로", "시뽀", "GM")   # 핵심 = core:true 모듈 묶음
SECRET = os.environ["ERP_JWT_SECRET"]
COOKIE = "erp_session"
SESSION_DAYS = 30
KST = timezone(timedelta(hours=9))
LOCK_AFTER = 5                                 # 연속 실패 허용 횟수
LOCK_SECS = 600                                # 잠금 시간(10분)
GOOGLE_ID = os.environ.get("GOOGLE_CLIENT_ID", "")      # 없으면 구글 로그인 라우트가 안내만 낸다
GOOGLE_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_HD = "wellperion.com"                   # 회사 워크스페이스 도메인 — 개인 gmail 차단
FAILS: dict[str, tuple[int, float]] = {}       # email -> (연속실패수, 잠금해제시각) · ponytail: 서버 1대 메모리 락, 다중서버면 DB/redis로

app = FastAPI(docs_url=None, redoc_url=None)


# ── 저장 ────────────────────────────────────────────────────────────────
def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            salt TEXT NOT NULL, pw TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'staff',
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, approved_at TEXT)""")
        if "perms" not in [r[1] for r in c.execute("PRAGMA table_info(users)")]:
            c.execute("ALTER TABLE users ADD COLUMN perms TEXT")
        admin_email = os.environ.get("ERP_ADMIN_EMAIL")
        if admin_email and not c.execute("SELECT 1 FROM users WHERE email=?", (admin_email,)).fetchone():
            salt, h = hash_pw(os.environ["ERP_ADMIN_PW"])
            c.execute("INSERT INTO users(email,name,salt,pw,role,status,created_at,approved_at) VALUES(?,?,?,?,?,?,?,?)",
                      (admin_email, "GM", salt, h, "admin", "active", now(), now()))


def now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def hash_pw(pw: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1).hex()
    return salt, h


# ── 세션 ────────────────────────────────────────────────────────────────
def issue(user: sqlite3.Row) -> str:
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
        u = c.execute("SELECT * FROM users WHERE id=? AND status='active'", (claims["uid"],)).fetchone()
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


def module_at(uri: str) -> Optional[dict]:
    """nginx 가 넘긴 X-Original-URI → 모듈. 목록에 없는 경로(공용 자산·status 등)는 None."""
    modules()
    path = posixpath.normpath(urllib.parse.unquote(urllib.parse.urlsplit(uri).path) or "/")
    return _MODS[2].get(path)


def perms_of(user) -> Optional[dict]:
    raw = user["perms"] if "perms" in user.keys() else None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def allowed(user, module: dict) -> bool:
    """계정이 모듈을 볼 수 있나. admin=전부 · perms 없음=modules.json roles 규칙(종전) · 있으면 거부>허용."""
    if user["role"] == "admin":
        return True
    p = perms_of(user)
    if p is None:
        return "staff" in module.get("roles", [])
    if module["id"] in p.get("deny", []):
        return False
    groups = p.get("groups", [])
    return (module["id"] in p.get("modules", []) or module.get("group") in groups
            or ("핵심" in groups and bool(module.get("core"))))


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
    "</style>")

BRAND = "<a class=brand href=/erp/>WELLPERION<small>ERP</small></a>"


def page(title: str, body: str) -> HTMLResponse:
    brand = BRAND.replace("class=brand", "class='brand wide'") if "box wide" in body else BRAND
    return HTMLResponse(f"<!doctype html><html lang=ko><meta charset=utf-8><title>{escape(title)}</title>{STYLE}{brand}{body}")


@app.get("/auth/login")
def login_page(next: str = "/", err: str = ""):
    return page("웰페리온 ERP 로그인", f"""<form method=post action=/auth/login>
<h1>로그인</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<label>이메일<input name=email type=email autocomplete=username required autofocus></label>
<label>비밀번호<input name=password type=password autocomplete=current-password required></label>
<input type=hidden name=next value="{escape(next)}"><button>로그인</button>
{'<a class=g href="/auth/google?next=' + escape(next) + '">회사 구글 계정으로 로그인</a>' if GOOGLE_ID else ''}
<p>계정이 없으면 <a href=/auth/signup>가입 신청</a>. GM 승인 후 사용할 수 있습니다.</p></form>""")


@app.post("/auth/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    email = email.strip().lower()
    count, locked_until = FAILS.get(email, (0, 0.0))
    if locked_until > time.time():
        wait_min = max(1, int((locked_until - time.time()) // 60) + 1)
        return RedirectResponse(f"/auth/login?err=로그인 5회 실패로 잠겼습니다. {wait_min}분 후 다시 시도하세요&next={next}", status_code=303)
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
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
    return page("웰페리온 ERP 가입 신청", f"""<form method=post action=/auth/signup>
<h1>가입 신청</h1>{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<label>이름<input name=name placeholder="직함 포함, 예: 홍길동 매니저" autocomplete=name required></label>
<label>회사 이메일<input name=email type=email autocomplete=email required></label>
<label>비밀번호<input name=password type=password placeholder="8자 이상" minlength=8 autocomplete=new-password required></label>
<button>신청</button><p>GM 이 승인하면 로그인할 수 있습니다. <a href=/auth/login>로그인으로</a></p></form>""")


@app.post("/auth/signup")
def signup(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    salt, h = hash_pw(password)
    try:
        with db() as c:
            c.execute("INSERT INTO users(email,name,salt,pw,created_at) VALUES(?,?,?,?,?)", (email, name.strip(), salt, h, now()))
    except sqlite3.IntegrityError:
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
    return page("비밀번호 변경", f"""<form method=post action=/auth/password>
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
        c.execute("UPDATE users SET salt=?, pw=? WHERE id=?", (salt, h, u["id"]))
    return RedirectResponse("/auth/password?msg=변경됐습니다", status_code=303)


# ── 회사 구글 계정 로그인 ────────────────────────────────────────────────
# 회사 워크스페이스(@wellperion.com) 계정은 GM 승인 없이 바로 통과한다(GM 지시 2026-09-03).
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


@app.get("/auth/google")
def google_start(request: Request, next: str = "/"):
    if not GOOGLE_ID or not GOOGLE_SECRET:
        return page("회사 구글 로그인", "<div class=box><h1>아직 설정 전입니다</h1>"
                    "<p>구글 OAuth 클라이언트를 등록하고 서버 /srv/erp/auth.env 에 "
                    "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 을 넣으면 켜집니다.</p>"
                    "<p><a href=/auth/login>로그인 화면으로</a></p></div>")
    state = jwt.encode({"n": next if next.startswith("/") else "/", "exp": int(time.time()) + 600},
                       SECRET, algorithm="HS256")
    q = urllib.parse.urlencode({"client_id": GOOGLE_ID, "redirect_uri": _redirect_uri(request),
                                "response_type": "code", "scope": "openid email profile",
                                "hd": GOOGLE_HD, "state": state, "prompt": "select_account"})
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
    if not is_company_account(claims):
        return RedirectResponse("/auth/login?err=회사 구글 계정(@wellperion.com)만 로그인할 수 있습니다", status_code=303)
    email = claims["email"].strip().lower()
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and u["status"] == "blocked":
            return RedirectResponse("/auth/login?err=차단된 계정입니다. GM 에게 문의하세요", status_code=303)
        if not u:
            salt, h = hash_pw(secrets.token_urlsafe(32))    # 구글 전용 계정 — 비밀번호 로그인은 못 쓴다
            c.execute("INSERT INTO users(email,name,salt,pw,role,status,created_at,approved_at) VALUES(?,?,?,?,?,?,?,?)",
                      (email, (claims.get("name") or email.split("@")[0]).strip(), salt, h, "staff", "active", now(), now()))
        elif u["status"] != "active":
            c.execute("UPDATE users SET status='active', approved_at=? WHERE id=?", (now(), u["id"]))
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    r = RedirectResponse(nxt, status_code=303)
    https = request.headers.get("x-forwarded-proto") == "https"
    r.set_cookie(COOKIE, issue(u), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/", secure=https)
    return r


# ── 관리자 ──────────────────────────────────────────────────────────────
def admin_only(token: Optional[str]) -> sqlite3.Row:
    u = current(token)
    if not u or u["role"] != "admin":
        raise HTTPException(403, "관리자만")
    return u


def _admin_row(r: sqlite3.Row, me_id: int) -> str:
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
    role_ko = "관리자" if r["role"] == "admin" else "직원"
    pending = " on" if r["status"] == "pending" else ""
    perm_link = "" if r["role"] == "admin" else f"<a href=/auth/admin/{r['id']}/perms>권한</a> "
    return (f"<tr><td>{escape(r['name'])}<br><small>{escape(r['email'])}</small></td>"
            f"<td><span class=tag>{role_ko}</span></td><td><span class='tag{pending}'>{status_ko}</span></td>"
            f"<td>{escape(r['created_at'])}</td><td>{escape(r['approved_at'] or '')}</td>"
            f"<td>{perm_link}{approve_or_block}{role_btn}</td></tr>")


@app.get("/auth/admin")
def admin(erp_session: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session)
    with db() as c:
        rows = c.execute("SELECT * FROM users ORDER BY status='pending' DESC, created_at DESC").fetchall()
    tr = "".join(_admin_row(r, me["id"]) for r in rows)
    head = "<tr><th>이름</th><th>역할</th><th>상태</th><th>신청</th><th>승인</th><th></th></tr>"
    return page("ERP 계정 관리", f"<div class='box wide'><h1>계정 관리</h1><div class=tw><table>{head}{tr}</table></div>"
                                 f"<p class=nav><a href=/erp/>ERP 로 돌아가기</a><a href=/auth/password>비밀번호 변경</a><a href=/auth/logout>로그아웃</a></p></div>")


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
def perms_page(uid: int, erp_session: Optional[str] = Cookie(default=None), msg: str = ""):
    admin_only(erp_session)
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        raise HTTPException(404)
    p = perms_of(u)
    ms = modules()
    rows = "".join(_perms_row(g, [m for m in ms if (m.get("core") if g == "핵심" else m.get("group") == g)], u, p)
                   for g in GROUPS)
    mode = "관리자 — 전부 허용" if u["role"] == "admin" else ("개별 설정" if p else "기본 규칙(modules.json roles)")
    return page("계정 권한", f"""<div class='box wide'><h1>권한 — {escape(u['name'])} <small>{escape(u['email'])}</small></h1>
{'<p class=ok>' + escape(msg) + '</p>' if msg else ''}
<p>현재: <span class=tag>{mode}</span> · 허용 {len(allowed_ids(u))}/{len(ms)}개. 저장하면 개별 설정으로 바뀝니다(거부가 허용보다 우선).</p>
<form method=post action=/auth/admin/{uid}/perms style='max-width:none;padding:0;border:0;background:none'>
<div class=tw><table><tr><th>그룹</th><th>전체</th><th>모듈</th></tr>{rows}</table></div>
<button>저장</button><button class=sec name=reset value=1>기본 규칙으로 되돌리기</button></form>
<p class=nav><a href=/auth/admin>계정 관리로</a></p></div>""")


@app.post("/auth/admin/{uid}/perms")
async def perms_save(uid: int, request: Request, erp_session: Optional[str] = Cookie(default=None)):
    admin_only(erp_session)
    form = await request.form()
    ids = {m["id"] for m in modules()}
    perms = None if form.get("reset") else json.dumps({
        "groups": [g for g in form.getlist("g") if g in GROUPS],
        "modules": [m for m in form.getlist("m") if m in ids],
        "deny": [m for m in form.getlist("d") if m in ids]}, ensure_ascii=False)
    with db() as c:
        c.execute("UPDATE users SET perms=? WHERE id=?", (perms, uid))
    return RedirectResponse(f"/auth/admin/{uid}/perms?msg=저장됐습니다", status_code=303)


@app.post("/auth/admin/{uid}/{action}")
def admin_action(uid: int, action: str, erp_session: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session)
    if action not in ("approve", "block", "toggle_role"):
        raise HTTPException(400)
    if action == "toggle_role":
        if uid == me["id"]:
            raise HTTPException(400, "본인 역할은 바꿀 수 없습니다")
        with db() as c:
            row = c.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
            if row:
                c.execute("UPDATE users SET role=? WHERE id=?",
                          ("staff" if row["role"] == "admin" else "admin", uid))
        return RedirectResponse("/auth/admin", status_code=303)
    with db() as c:
        c.execute("UPDATE users SET status=?, approved_at=? WHERE id=? AND role!='admin'",
                  ("active" if action == "approve" else "blocked", now() if action == "approve" else None, uid))
    return RedirectResponse("/auth/admin", status_code=303)


init()


if __name__ == "__main__":                     # 회사 계정 판별 자가점검: python app.py
    ok = {"email": "cao@wellperion.com", "email_verified": True, "hd": "wellperion.com"}
    assert is_company_account(ok)
    assert not is_company_account({**ok, "hd": None})                        # 개인 gmail
    assert not is_company_account({**ok, "email": "x@gmail.com"})            # hd 만 위조된 경우
    assert not is_company_account({**ok, "email_verified": False})
    # 권한 판정 자가점검 — dict 가 sqlite3.Row 흉내(keys()·[] 둘 다 된다)
    core = {"id": "member", "group": "시포", "core": True, "roles": ["admin"]}
    plain = {"id": "check", "group": "시우", "roles": ["admin", "staff"]}
    assert allowed({"role": "admin", "perms": None}, core)
    assert not allowed({"role": "staff", "perms": None}, core) and allowed({"role": "staff", "perms": None}, plain)
    assert allowed({"role": "staff", "perms": '{"groups":["핵심"]}'}, core)
    assert not allowed({"role": "staff", "perms": '{"groups":["핵심"]}'}, plain)
    assert not allowed({"role": "staff", "perms": '{"groups":["시우"],"deny":["check"]}'}, plain)
    print("self-check ok")
