"""웰페리온 ERP 로그인 관문 (AWS 서버 · FastAPI · SQLite).

역할
    가입 신청 → GM(관리자) 승인 → 로그인 → 쿠키(JWT) → nginx 가 쿠키 없는 요청에 페이지를 주지 않는다.
    GitHub Pages 의 gate.js '커튼'(비밀번호가 소스에 노출)을 진짜 잠금으로 바꾸는 첫 조각이다(배101).

경로
    GET  /auth/login   /auth/signup   — 화면
    POST /auth/login   /auth/signup   /auth/logout
    GET  /auth/check                  — nginx auth_request 용 (200 통과 / 401 차단)
    GET  /auth/admin                  — 승인 대기 목록 (관리자만)
    POST /auth/admin/{uid}/{action}   — approve | block

환경변수(/srv/erp/auth.env · 서버 밖으로 안 나감)
    ERP_JWT_SECRET  서명 키        TG_BOT_TOKEN / TG_CHAT_ID  가입 신청 알림(업무보고방)
    ERP_ADMIN_EMAIL 첫 관리자     ERP_ADMIN_PW 첫 관리자 비밀번호(첫 기동 때만 씀)
"""
from __future__ import annotations

import hashlib
import json
import os
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
STYLE = ("<style>body{font-family:system-ui,'Malgun Gothic',sans-serif;background:#f6f7f9;margin:0;display:flex;"
         "min-height:100vh;align-items:center;justify-content:center}form,.box{background:#fff;padding:32px;"
         "border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.06);width:340px}h1{font-size:18px;margin:0 0 20px}"
         "input{width:100%;box-sizing:border-box;padding:10px;margin:6px 0 14px;border:1px solid #d5d8de;border-radius:8px}"
         "button{width:100%;padding:11px;border:0;border-radius:8px;background:#1f2937;color:#fff;font-weight:600}"
         "p{font-size:13px;color:#6b7280}a{color:#1f2937}.err{color:#b91c1c}table{width:100%;font-size:14px}"
         "td{padding:6px 4px;border-bottom:1px solid #eee}"
         ".g{display:block;text-align:center;padding:11px;margin:10px 0 0;border:1px solid #d5d8de;"
         "border-radius:8px;background:#fff;color:#1f2937;text-decoration:none;font-weight:600}</style>")


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{escape(title)}</title>{STYLE}{body}")


@app.get("/auth/login")
def login_page(next: str = "/", err: str = ""):
    return page("웰페리온 ERP 로그인", f"""<form method=post action=/auth/login>
<h1>웰페리온 ERP</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<input name=email type=email placeholder=이메일 required autofocus>
<input name=password type=password placeholder=비밀번호 required>
<input type=hidden name=next value="{escape(next)}"><button>로그인</button>
{'<a class=g href="/auth/google?next=' + escape(next) + '">회사 구글 계정으로 로그인</a>' if GOOGLE_ID else ''}
<p>계정이 없으면 <a href=/auth/signup>가입 신청</a> — GM 승인 후 사용할 수 있습니다.</p></form>""")


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
<h1>가입 신청</h1>{'<p>' + escape(msg) + '</p>' if msg else ''}
<input name=name placeholder="이름(직함 포함, 예: 홍길동 매니저)" required>
<input name=email type=email placeholder=회사이메일 required>
<input name=password type=password placeholder="비밀번호(8자 이상)" minlength=8 required>
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
def check(erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        raise HTTPException(401)
    return Response(status_code=200, headers={"X-Erp-User": u["email"], "X-Erp-Role": u["role"]})


@app.get("/auth/me")
def me(erp_session: Optional[str] = Cookie(default=None)):
    u = current(erp_session)
    if not u:
        raise HTTPException(401)
    return JSONResponse({"email": u["email"], "name": u["name"], "role": u["role"]})


@app.get("/auth/password")
def password_page(erp_session: Optional[str] = Cookie(default=None), msg: str = "", err: str = ""):
    if not current(erp_session):
        return RedirectResponse("/auth/login?next=/auth/password", status_code=303)
    return page("비밀번호 변경", f"""<form method=post action=/auth/password>
<h1>비밀번호 변경</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}{'<p>' + escape(msg) + '</p>' if msg else ''}
<input name=current_password type=password placeholder=현재 비밀번호 required>
<input name=new_password type=password placeholder="새 비밀번호(8자 이상)" minlength=8 required>
<button>변경</button><p><a href=/>ERP 로</a></p></form>""")


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
            approve_or_block = f"<form method=post action=/auth/admin/{r['id']}/block><button style=background:#9ca3af>차단</button></form>"
    role_btn = "" if r["id"] == me_id else (
        f"<form method=post action=/auth/admin/{r['id']}/toggle_role>"
        f"<button style=background:#6b7280>{'관리자로' if r['role'] != 'admin' else '일반으로'}</button></form>")
    return (f"<tr><td>{escape(r['name'])}<br><small>{escape(r['email'])}</small></td>"
            f"<td>{escape(r['role'])}</td><td>{escape(r['status'])}</td>"
            f"<td>{escape(r['created_at'])}</td><td>{escape(r['approved_at'] or '')}</td>"
            f"<td>{approve_or_block}{role_btn}</td></tr>")


@app.get("/auth/admin")
def admin(erp_session: Optional[str] = Cookie(default=None)):
    me = admin_only(erp_session)
    with db() as c:
        rows = c.execute("SELECT * FROM users ORDER BY status='pending' DESC, created_at DESC").fetchall()
    tr = "".join(_admin_row(r, me["id"]) for r in rows)
    return page("ERP 계정 관리", f"<div class=box style=width:680px><h1>계정 관리</h1><table>{tr}</table>"
                                 f"<p><a href=/>ERP 로</a> · <a href=/auth/password>비밀번호 변경</a> · <a href=/auth/logout>로그아웃</a></p></div>")


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
    print("self-check ok")
