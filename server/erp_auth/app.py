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
import urllib.request
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
         "td{padding:6px 4px;border-bottom:1px solid #eee}</style>")


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{escape(title)}</title>{STYLE}{body}")


@app.get("/auth/login")
def login_page(next: str = "/", err: str = ""):
    return page("웰페리온 ERP 로그인", f"""<form method=post action=/auth/login>
<h1>웰페리온 ERP</h1>{'<p class=err>' + escape(err) + '</p>' if err else ''}
<input name=email type=email placeholder=이메일 required autofocus>
<input name=password type=password placeholder=비밀번호 required>
<input type=hidden name=next value="{escape(next)}"><button>로그인</button>
<p>계정이 없으면 <a href=/auth/signup>가입 신청</a> — GM 승인 후 사용할 수 있습니다.</p></form>""")


@app.post("/auth/login")
def login(email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not u or hash_pw(password, u["salt"])[1] != u["pw"]:
        return RedirectResponse(f"/auth/login?err=이메일 또는 비밀번호가 맞지 않습니다&next={next}", status_code=303)
    if u["status"] != "active":
        return RedirectResponse("/auth/login?err=아직 승인 전입니다. GM 승인 후 로그인됩니다", status_code=303)
    r = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    r.set_cookie(COOKIE, issue(u), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/")
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


# ── 관리자 ──────────────────────────────────────────────────────────────
def admin_only(token: Optional[str]) -> sqlite3.Row:
    u = current(token)
    if not u or u["role"] != "admin":
        raise HTTPException(403, "관리자만")
    return u


@app.get("/auth/admin")
def admin(erp_session: Optional[str] = Cookie(default=None)):
    admin_only(erp_session)
    with db() as c:
        rows = c.execute("SELECT * FROM users ORDER BY status='pending' DESC, created_at DESC").fetchall()
    tr = "".join(
        f"<tr><td>{escape(r['name'])}<br><small>{escape(r['email'])}</small></td><td>{escape(r['status'])}</td>"
        f"<td>{'' if r['role'] == 'admin' else ('<form method=post action=/auth/admin/' + str(r['id']) + '/approve><button>승인</button></form>' if r['status'] != 'active' else '<form method=post action=/auth/admin/' + str(r['id']) + '/block><button style=background:#9ca3af>차단</button></form>')}</td></tr>"
        for r in rows)
    return page("ERP 계정 관리", f"<div class=box><h1>계정 관리</h1><table>{tr}</table><p><a href=/>ERP 로</a> · <a href=/auth/logout>로그아웃</a></p></div>")


@app.post("/auth/admin/{uid}/{action}")
def admin_action(uid: int, action: str, erp_session: Optional[str] = Cookie(default=None)):
    admin_only(erp_session)
    if action not in ("approve", "block"):
        raise HTTPException(400)
    with db() as c:
        c.execute("UPDATE users SET status=?, approved_at=? WHERE id=? AND role!='admin'",
                  ("active" if action == "approve" else "blocked", now() if action == "approve" else None, uid))
    return RedirectResponse("/auth/admin", status_code=303)


init()
