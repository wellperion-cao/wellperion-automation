# -*- coding: utf-8 -*-
"""GM 금고 서버 문 (배 12843 · 2026-09-19 시토 · GM 직접 지시 「코드번호나 정말 계정이 아니라 GM만 들어갈 수 있었으면」).

문 = 두 가지를 다 가져야 열린다.
  ① 로그인한 세션이 cao@wellperion.com (nginx auth_request 가 X-Erp-User 에 싣는다 · 클라이언트 값은 nginx 가 덮어쓴다)
  ② 방금 받은 GM 패스키(WebAuthn) 확인 — userVerification required · 일회용 도전값(120초) · 서명 카운터 검사
  → 확인이 끝나면 5분짜리 잠금해제 표(X-Vault-Token)를 준다. 그 세션 쿠키(erp_session)에 묶여 다른 세션에선 안 통한다.
  코드(1531)만으로도, 로그인만으로도 값은 안 나온다.

칸 둘 = 같은 문 뒤.
  gm      GM 개인 금고(구글 시트에서 옮겨 오는 항목) — /srv/erp/vault/gm_items.json · 항목마다 AES-GCM 암호문
  partner 파트너사 채널 계정 — 기존 /srv/erp/partner_secrets.json(api_partner_secrets.py) · pw 칸만 암호문
          (id 는 평문 — 목록이 앞 2자 가림표를 거기서 만든다 · 발행 PC 열쇠 통로 /api/partner-secrets/fetch 는 그대로)

암호화 방식 = B(서버 봉투 암호화) — 지금 켜진 것.
  열쇠 = /srv/erp/vault.key(32바이트 · 600 · 저장소·PC 에 없음 · 배포 때 손으로 한 번 만든다 · 없으면 503).
  ⚠️ 정직하게: 파트너 칸의 서버 자동 첨부(secret_pw)·발행 PC 통로는 패스키 없이 복호화한다 — 그 칸의
     「패스키 뒤」는 사람 보기 경로의 코드 관문이지 암호학적 봉인이 아니다. 암호문 저장이 막는 것 = 파일만
     새어 나간 경우. GM 칸은 기계 경로가 없어 문을 지나야만 풀린다(그래도 열쇠는 같은 서버에 있다).
  A(WebAuthn PRF · 브라우저에서 열쇠를 만들어 서버가 평문을 못 봄)로 넘어갈 준비 = 등록 때 인증기가 PRF 를
     지원하는지(prf 칸)를 재서 적어 둔다. 지원이 확인되면 GM 칸만 A 로 옮길 수 있다(파트너 칸은 기계 경로 때문에 B 고정).

라우트(전부 /api/ 로그인 관문 뒤 · GM 이메일만):
  GET  /api/vault/status                 패스키 수·모드·잠금해제 여부(값 없음)
  POST /api/vault/register/options       {code?}  패스키 0개면 결재 GM 코드 필요(첫 등록 가로채기 막기) · 1개 이상이면 잠금해제 표 필요
  POST /api/vault/register/verify        {credential, label, prf}
  POST /api/vault/unlock/options
  POST /api/vault/unlock/verify          {credential} → {token, exp}
  GET  /api/vault/items?compartment=gm|partner      표 필요 · 제목·가림표만
  POST /api/vault/reveal                 {compartment, id}  표 필요 · 값
  POST /api/vault/import                 {text}  표 필요 · 붙여넣은 표(TSV/CSV) → gm 칸 · 건수만 돌려준다
기록 = /srv/erp/logs/vault_audit.jsonl (ts·email·action·item·ip · 값 없음).
"""
import base64
import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import secrets
import tempfile
import time

try:
    import fcntl
except ImportError:          # 윈도 자가점검용 — 서버는 리눅스라 늘 잠근다
    fcntl = None

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

VAULT_DIR = os.environ.get("VAULT_DIR", "/srv/erp/vault")
KEY_FILE = os.environ.get("VAULT_KEY_FILE", "/srv/erp/vault.key")
AUDIT_FILE = os.environ.get("VAULT_AUDIT_FILE", "/srv/erp/logs/vault_audit.jsonl")
RP_ID = os.environ.get("VAULT_RP_ID", "erp.wellperion.com")
ORIGIN = os.environ.get("VAULT_ORIGIN", "https://erp.wellperion.com")
GM = os.environ.get("VAULT_GM_EMAIL", "cao@wellperion.com").strip().lower()
MODE = "B-server-envelope"
CHALLENGE_TTL = 120
UNLOCK_TTL = 300
KST = dt.timezone(dt.timedelta(hours=9))


def b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── 열쇠·봉투 ───────────────────────────────────────────────────────────────
def _sub(label):
    with open(KEY_FILE, "rb") as f:
        k = f.read()
    if len(k) != 32:
        raise RuntimeError("vault key 길이 이상")
    return hmac.new(k, label, hashlib.sha256).digest()


def seal(plain, aad):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    n = os.urandom(12)
    return {"enc": "aesgcm-v1", "n": b64e(n), "ct": b64e(AESGCM(_sub(b"enc")).encrypt(n, plain.encode(), aad.encode()))}


def unseal(box, aad):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(_sub(b"enc")).decrypt(b64d(box["n"]), b64d(box["ct"]), aad.encode()).decode()


# ── 파일(두 워커가 같이 쓰므로 잠금 + 원자 교체) ─────────────────────────────
def _read(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".v-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _mutate(name, fn, default):
    """VAULT_DIR/name 을 잠금 안에서 읽고 fn(data) 로 고쳐 쓴다. fn 이 예외를 내면 안 쓴다."""
    os.makedirs(VAULT_DIR, mode=0o700, exist_ok=True)
    with open(os.path.join(VAULT_DIR, ".lock"), "a") as lf:
        if fcntl:
            fcntl.flock(lf, fcntl.LOCK_EX)
        path = os.path.join(VAULT_DIR, name)
        data = _read(path, default)
        out = fn(data)
        _write(path, data)
        return out


def _creds():
    return _read(os.path.join(VAULT_DIR, "state.json"), {"creds": [], "ch": {}})["creds"]


# ── 신원·표 ────────────────────────────────────────────────────────────────
def _who(request):
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _sess(request):
    c = request.cookies.get("erp_session") or ""
    return hashlib.sha256(c.encode()).hexdigest()[:32] if c else ""


def _sign(email, sess, exp):
    return hmac.new(_sub(b"unlock"), ("%s|%s|%d" % (email, sess, exp)).encode(), hashlib.sha256).hexdigest()


def _issue(request):
    exp = int(time.time()) + UNLOCK_TTL
    return "%d.%s" % (exp, _sign(_who(request), _sess(request), exp)), exp


def is_unlocked(request):
    who, sess = _who(request), _sess(request)
    tok = request.headers.get("x-vault-token") or ""
    exp, _, sig = tok.partition(".")
    if who != GM or not sess or not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(sig, _sign(who, sess, int(exp)))


def _deny(msg, code=403):
    return JSONResponse({"ok": False, "error": msg}, status_code=code)


def require_unlock(request):
    """None = 통과. 아니면 거절 응답. api_partner_secrets.reveal 도 이걸 쓴다."""
    if _who(request) != GM:
        return _deny("forbidden")
    if not os.path.exists(KEY_FILE):
        return _deny("vault key 없음", 503)
    if not is_unlocked(request):
        return _deny("금고 잠금 해제 필요(패스키)")
    return None


def audit(request, action, item=""):
    rec = {"ts": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "email": _who(request), "action": action,
           "item": item, "ip": (request.headers.get("x-forwarded-for") or (request.client.host if request.client else ""))}
    fd = os.open(AUDIT_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── 도전값(일회용) ─────────────────────────────────────────────────────────
def _new_challenge(request, purpose):
    ch = os.urandom(32)

    def fn(st):
        now = time.time()
        st["ch"] = {k: v for k, v in st.get("ch", {}).items() if v["exp"] > now}
        st["ch"][b64e(ch)] = {"p": purpose, "e": _who(request), "s": _sess(request), "exp": now + CHALLENGE_TTL}
    _mutate("state.json", fn, {"creds": [], "ch": {}})
    return ch


def _take_challenge(request, credential, purpose):
    """clientDataJSON 속 도전값을 꺼내 저장소에서 지운다(성공·실패 무관 한 번만). 맞으면 bytes, 아니면 None."""
    try:
        chal = json.loads(b64d(credential["response"]["clientDataJSON"]))["challenge"]
    except Exception:
        return None

    def fn(st):
        return st.get("ch", {}).pop(chal, None)
    rec = _mutate("state.json", fn, {"creds": [], "ch": {}})
    if not rec or rec["p"] != purpose or rec["e"] != _who(request) or rec["s"] != _sess(request) or rec["exp"] < time.time():
        return None
    return b64d(chal)


def _gm_only(request):
    if _who(request) != GM:
        return _deny("forbidden")
    if not os.path.exists(KEY_FILE):
        return _deny("vault key 없음", 503)
    if not _sess(request):
        return _deny("세션 없음")
    return None


# ── 라우트 ────────────────────────────────────────────────────────────────
@router.get("/api/vault/status")
def status(request: Request):
    if _who(request) != GM:
        return _deny("forbidden")
    creds = _creds()
    return {"ok": True, "mode": MODE, "passkeys": len(creds), "prf_supported": [bool(c.get("prf")) for c in creds],
            "unlocked": is_unlocked(request), "key_ready": os.path.exists(KEY_FILE)}


@router.post("/api/vault/register/options")
async def register_options(request: Request):
    bad = _gm_only(request)
    if bad:
        return bad
    body = await request.json()
    creds = _creds()
    if creds:
        if not is_unlocked(request):
            return _deny("새 패스키는 기존 패스키로 먼저 잠금 해제")
    else:
        import api_partner_secrets
        if not api_partner_secrets._code_ok(str(body.get("code") or "")):
            audit(request, "register-refused", "bootstrap-code")
            return _deny("첫 등록은 결재 GM 코드 필요")
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                          ResidentKeyRequirement, UserVerificationRequirement)
    opts = generate_registration_options(
        rp_id=RP_ID, rp_name="웰페리온 GM 금고", user_id=hashlib.sha256(GM.encode()).digest()[:16],
        user_name=GM, user_display_name="GM", challenge=_new_challenge(request, "reg"),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=b64d(c["id"])) for c in creds],
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.PREFERRED,
                                                               user_verification=UserVerificationRequirement.REQUIRED))
    return {"ok": True, "options": json.loads(options_to_json(opts))}


@router.post("/api/vault/register/verify")
async def register_verify(request: Request):
    bad = _gm_only(request)
    if bad:
        return bad
    body = await request.json()
    cred = body.get("credential") or {}
    chal = _take_challenge(request, cred, "reg")
    if not chal:
        return _deny("도전값 없음·만료·재사용")
    from webauthn import verify_registration_response
    try:
        v = verify_registration_response(credential=cred, expected_challenge=chal, expected_origin=ORIGIN,
                                         expected_rp_id=RP_ID, require_user_verification=True)
    except Exception as e:
        audit(request, "register-failed")
        return _deny("등록 검증 실패: %s" % type(e).__name__)
    row = {"id": b64e(v.credential_id), "pk": b64e(v.credential_public_key), "count": v.sign_count,
           "label": str(body.get("label") or "")[:40], "prf": bool(body.get("prf")),
           "created": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}

    def fn(st):
        if any(c["id"] == row["id"] for c in st["creds"]):
            return False
        st["creds"].append(row)
        return True
    _mutate("state.json", fn, {"creds": [], "ch": {}})
    audit(request, "register", row["id"][:8])
    return {"ok": True, "passkeys": len(_creds()), "prf": row["prf"]}


@router.post("/api/vault/unlock/options")
def unlock_options(request: Request):
    bad = _gm_only(request)
    if bad:
        return bad
    creds = _creds()
    if not creds:
        return _deny("등록된 패스키 없음", 409)
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    opts = generate_authentication_options(
        rp_id=RP_ID, challenge=_new_challenge(request, "auth"),
        allow_credentials=[PublicKeyCredentialDescriptor(id=b64d(c["id"])) for c in creds],
        user_verification=UserVerificationRequirement.REQUIRED)
    return {"ok": True, "options": json.loads(options_to_json(opts))}


@router.post("/api/vault/unlock/verify")
async def unlock_verify(request: Request):
    bad = _gm_only(request)
    if bad:
        return bad
    cred = (await request.json()).get("credential") or {}
    chal = _take_challenge(request, cred, "auth")
    if not chal:
        audit(request, "unlock-refused", "challenge")
        return _deny("도전값 없음·만료·재사용")
    row = next((c for c in _creds() if c["id"] == cred.get("rawId", cred.get("id"))), None)
    if not row:
        audit(request, "unlock-refused", "unknown-credential")
        return _deny("등록 안 된 패스키")
    from webauthn import verify_authentication_response
    try:
        v = verify_authentication_response(credential=cred, expected_challenge=chal, expected_rp_id=RP_ID,
                                           expected_origin=ORIGIN, credential_public_key=b64d(row["pk"]),
                                           credential_current_sign_count=row["count"], require_user_verification=True)
    except Exception as e:
        audit(request, "unlock-refused", type(e).__name__)
        return _deny("패스키 검증 실패: %s" % type(e).__name__)

    def fn(st):   # 카운터를 잠금 안에서 다시 본다(두 워커 동시 확인 대비)
        c = next(c for c in st["creds"] if c["id"] == row["id"])
        if (v.new_sign_count or c["count"]) and v.new_sign_count <= c["count"]:
            return False
        c["count"] = v.new_sign_count
        return True
    if not _mutate("state.json", fn, {"creds": [], "ch": {}}):
        audit(request, "unlock-refused", "sign-count")
        return _deny("서명 카운터 역행(복제 의심)")
    tok, exp = _issue(request)
    audit(request, "unlock", row["id"][:8])
    return {"ok": True, "token": tok, "exp": exp}


def _gm_items():
    return _read(os.path.join(VAULT_DIR, "gm_items.json"), {})


def _mask(v):
    v = str(v or "")
    return (v[:2] + "*" * max(3, len(v) - 2)) if v else ""


@router.get("/api/vault/items")
def items(request: Request, compartment: str = "gm"):
    bad = require_unlock(request)
    if bad:
        return bad
    if compartment == "partner":
        import api_partner_secrets as ps
        rows = ps.listing(ps._load())
        for r in rows:
            r["id"] = r["tenant"] + "/" + r["channel"]
        return {"ok": True, "compartment": "partner", "items": rows}
    out = []
    for iid, box in sorted(_gm_items().items(), key=lambda kv: kv[1].get("created", "")):
        d = json.loads(unseal(box, "gm/" + iid))
        out.append({"id": iid, "title": d.get("title", ""), "url": d.get("url", ""),
                    "user_masked": _mask(d.get("user")), "has_pw": bool(d.get("pw"))})
    return {"ok": True, "compartment": "gm", "items": out}


@router.post("/api/vault/reveal")
async def reveal(request: Request):
    bad = require_unlock(request)
    if bad:
        return bad
    body = await request.json()
    comp, iid = str(body.get("compartment") or ""), str(body.get("id") or "")
    if comp == "partner":
        import api_partner_secrets as ps
        v = ps._load().get(iid)
        if not v:
            return _deny("없음", 404)
        out = {"user": v.get("id", ""), "pw": v.get("pw", ""), "note": v.get("note", "")}
    elif comp == "gm":
        box = _gm_items().get(iid)
        if not box:
            return _deny("없음", 404)
        d = json.loads(unseal(box, "gm/" + iid))
        out = {"user": d.get("user", ""), "pw": d.get("pw", ""), "note": d.get("note", ""), "url": d.get("url", "")}
    else:
        return _deny("compartment", 400)
    audit(request, "reveal", comp + ":" + iid)
    return dict(out, ok=True)


_HEAD = {"title": ("title", "name", "site", "service", "이름", "사이트", "서비스", "항목", "구분"),
         "user": ("id", "user", "username", "login", "email", "아이디", "계정", "이메일"),
         "pw": ("pw", "password", "pass", "비밀번호", "비번", "패스워드"),
         "url": ("url", "link", "주소", "링크"),
         "note": ("note", "memo", "메모", "비고")}


def import_rows(text):
    """붙여넣은 표 → gm 칸. 머리행을 알아보면 그 순서, 아니면 제목·아이디·비번·주소·메모 순. 반환 = 건수만."""
    text = (text or "").strip("﻿\r\n ")
    if not text:
        return {"added": 0, "updated": 0, "skipped": 0}
    delim = "\t" if "\t" in text.splitlines()[0] else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    cols = ["title", "user", "pw", "url", "note"]
    head = [c.strip().lower() for c in rows[0]]
    hit = [next((k for k, ws in _HEAD.items() if h in ws), None) for h in head]
    if sum(1 for h in hit if h) >= 2:
        cols, rows = hit, rows[1:]
    fpkey = _sub(b"fp")
    added = updated = skipped = 0
    batch = []
    for r in rows:
        d = {k: r[i].strip() for i, k in enumerate(cols) if k and i < len(r)}
        if not d.get("title") and not d.get("pw"):
            skipped += 1
            continue
        fp = hmac.new(fpkey, ("%s|%s" % (d.get("title", ""), d.get("user", ""))).encode(), hashlib.sha256).hexdigest()
        batch.append((fp, d))

    def fn(store):
        nonlocal added, updated
        by_fp = {b.get("fp"): k for k, b in store.items()}
        for fp, d in batch:
            iid = by_fp.get(fp) or secrets.token_hex(6)
            if iid in store:
                updated += 1
            else:
                added += 1
            store[iid] = dict(seal(json.dumps(d, ensure_ascii=False), "gm/" + iid), fp=fp,
                              created=store.get(iid, {}).get("created") or dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"))
            by_fp[fp] = iid
    _mutate("gm_items.json", fn, {})
    return {"added": added, "updated": updated, "skipped": skipped}


@router.post("/api/vault/import")
async def import_paste(request: Request):
    bad = require_unlock(request)
    if bad:
        return bad
    body = await request.json()
    n = import_rows(str(body.get("text") or ""))
    audit(request, "import", "added=%d updated=%d skipped=%d" % (n["added"], n["updated"], n["skipped"]))
    return dict(n, ok=True)


# ── 자가점검(가짜값만 · 임시 폴더 · 라이브 파일 안 건드림) ─────────────────
def selftest():
    global VAULT_DIR, KEY_FILE, AUDIT_FILE
    import cbor2
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_partner_secrets as ps

    FAKE = "Xample1234!"
    with tempfile.TemporaryDirectory() as d:
        VAULT_DIR, KEY_FILE, AUDIT_FILE = os.path.join(d, "v"), os.path.join(d, "k"), os.path.join(d, "a.jsonl")
        ps.SECRETS_FILE = os.path.join(d, "ps.json")
        with open(KEY_FILE, "wb") as f:
            f.write(os.urandom(32))
        ps._code_ok = lambda c: c == "0000"      # 결재 코드 DB 대신(가짜)
        ps._save({"jo/naver-blog": {"id": "fake_id", "pw": FAKE, "note": ""}})
        assert FAKE.encode() not in open(ps.SECRETS_FILE, "rb").read(), "파트너 파일에 평문"
        assert ps.secret_pw("jo", "naver-blog") == FAKE, "서버 자동 첨부(기계 경로) 복호화"

        app = FastAPI()
        app.include_router(router)
        app.include_router(ps.router)
        c = TestClient(app, base_url=ORIGIN)
        c.cookies.set("erp_session", "sess-A")
        H = {"X-Erp-User": GM}

        # 문: 표 없이 / 남의 계정 / 코드만
        assert c.post("/api/vault/reveal", json={"compartment": "partner", "id": "jo/naver-blog"}, headers=H).status_code == 403
        assert c.get("/api/vault/items", headers={"X-Erp-User": "staff@wellperion.com"}).status_code == 403
        r = c.post("/api/admin/partner-secrets/reveal", json={"code": "0000", "tenant": "jo", "channel": "naver-blog"}, headers=H)
        assert r.status_code == 403 and FAKE not in r.text, "코드만으로 값이 나옴"
        assert c.post("/api/vault/register/options", json={"code": "9999"}, headers=H).status_code == 403, "첫 등록 코드 검사"
        assert c.post("/api/vault/register/options", json={"code": "0000"}, headers={"X-Erp-User": "x@y.com"}).status_code == 403

        # 가짜 인증기(P-256)로 등록 → 잠금 해제
        key = ec.generate_private_key(ec.SECP256R1())
        pn = key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: pn.x.to_bytes(32, "big"), -3: pn.y.to_bytes(32, "big")})
        cid, rph = os.urandom(16), hashlib.sha256(RP_ID.encode()).digest()

        def cdj(t, ch):
            return json.dumps({"type": t, "challenge": ch, "origin": ORIGIN}).encode()

        ch = c.post("/api/vault/register/options", json={"code": "0000"}, headers=H).json()["options"]["challenge"]
        ad = rph + bytes([0x45]) + (0).to_bytes(4, "big") + b"\0" * 16 + len(cid).to_bytes(2, "big") + cid + cose
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": ad})
        reg = {"id": b64e(cid), "rawId": b64e(cid), "type": "public-key",
               "response": {"clientDataJSON": b64e(cdj("webauthn.create", ch)), "attestationObject": b64e(att)}}
        r = c.post("/api/vault/register/verify", json={"credential": reg, "label": "test"}, headers=H)
        assert r.status_code == 200 and r.json()["passkeys"] == 1, r.text
        assert c.post("/api/vault/register/options", json={"code": "0000"}, headers=H).status_code == 403, "2번째 등록은 코드로 안 됨"

        def assertion(count):
            ch = c.post("/api/vault/unlock/options", headers=H).json()["options"]["challenge"]
            a = rph + bytes([0x05]) + count.to_bytes(4, "big")
            cd = cdj("webauthn.get", ch)
            sig = key.sign(a + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
            return {"id": b64e(cid), "rawId": b64e(cid), "type": "public-key",
                    "response": {"clientDataJSON": b64e(cd), "authenticatorData": b64e(a), "signature": b64e(sig)}}

        a1 = assertion(1)
        r = c.post("/api/vault/unlock/verify", json={"credential": a1}, headers=H)
        assert r.status_code == 200, r.text
        tok = r.json()["token"]
        assert c.post("/api/vault/unlock/verify", json={"credential": a1}, headers=H).status_code == 403, "도전값 재사용"
        assert c.post("/api/vault/unlock/verify", json={"credential": assertion(1)}, headers=H).status_code == 403, "카운터 역행"

        T = dict(H, **{"X-Vault-Token": tok})
        r = c.post("/api/vault/reveal", json={"compartment": "partner", "id": "jo/naver-blog"}, headers=T)
        assert r.status_code == 200 and r.json()["pw"] == FAKE
        r = c.post("/api/admin/partner-secrets/reveal", json={"tenant": "jo", "channel": "naver-blog"}, headers=T)
        assert r.status_code == 200 and r.json()["pw"] == FAKE, "옛 보기 경로도 표로는 열림"
        c.cookies.set("erp_session", "sess-B")
        assert c.post("/api/vault/reveal", json={"compartment": "partner", "id": "jo/naver-blog"}, headers=T).status_code == 403, "다른 세션"
        c.cookies.set("erp_session", "sess-A")

        # 붙여넣기 → 암호문만 저장
        r = c.post("/api/vault/import", json={"text": "사이트\t아이디\t비밀번호\n은행\tgm_fake\t%s\n\t\t\n" % FAKE}, headers=T)
        assert r.json()["added"] == 1 and r.json()["skipped"] == 0, r.text
        assert c.post("/api/vault/import", json={"text": "은행,gm_fake,Other999!"}, headers=T).json()["updated"] == 1
        raw = open(os.path.join(VAULT_DIR, "gm_items.json"), "rb").read()
        assert FAKE.encode() not in raw and b"gm_fake" not in raw and "은행".encode() not in raw, "gm 파일에 평문"
        its = c.get("/api/vault/items?compartment=gm", headers=T).json()["items"]
        assert len(its) == 1 and its[0]["title"] == "은행" and "Other999" not in json.dumps(its)
        assert c.post("/api/vault/reveal", json={"compartment": "gm", "id": its[0]["id"]}, headers=T).json()["pw"] == "Other999!"
        log = open(AUDIT_FILE, encoding="utf-8").read()
        assert FAKE not in log and "Other999" not in log and '"action": "reveal"' in log
    print("vault selftest ok")


if __name__ == "__main__":
    import api_vault   # __main__ 과 api_partner_secrets 가 부르는 api_vault 가 한 모듈이 되게
    api_vault.selftest()
