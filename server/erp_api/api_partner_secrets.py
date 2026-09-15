# -*- coding: utf-8 -*-
"""파트너사 마케팅 채널 계정(아이디·비밀번호) 서버 보관 (배 2652 · 2026-09-15 시토 · GM 확정 「개인 PC 말고 서버 플랫폼관리에 안 보이게 저장 · 보기는 코드 1531」).

정본 = 서버 비밀 파일 하나(/srv/erp/partner_secrets.json · 권한 600 · api.env 와 같은 취급). 다른 어디에도 값을 두지 않는다.
모양 = {"<tenant>/<channel>": {"id":…, "pw":…, "note":…, "received_at":…, "updated_by":…}}  · tenant = jo/dc/… · channel = naver-blog/naver-cafe/danggn/instagram/threads/google/kakao-channel

  GET  /api/admin/partner-secrets                 회사 관리자(ERP_PLATFORM_ADMINS)만 · 목록(아이디 앞 2자만 · 비밀번호는 있다/없다)
  POST /api/admin/partner-secrets/reveal          {"code","tenant","channel"} → 코드가 맞을 때만 {id, pw}
  POST /api/admin/partner-secrets                 {"code","tenant","channel","id","pw","note"} 저장 · {"code","tenant","channel","delete":true} 삭제
  GET  /api/partner-secrets/fetch?tenant=&channel=  발행 PC 자동화용 · 로그인 없이 열쇠 헤더(X-Token-Push-Key = ERP_TOKEN_PUSH_KEY)로만 · nginx partner-secrets.nginx.conf
코드 검사 = approval_pins 표의 APPROVAL_PIN_GM(결재 GM 코드와 같은 값) — approval_pin.judge 재사용 · 화면 JS 에 코드를 박지 않는다.
기록 = 누가·언제·어느 칸을 보거나 바꿨는지만(값은 절대 안 찍는다).
"""
import datetime as dt
import json
import os
import tempfile

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

SECRETS_FILE = os.environ.get("PARTNER_SECRETS_FILE", "/srv/erp/partner_secrets.json")
CHANNELS = ("naver-blog", "naver-cafe", "danggn", "instagram", "threads", "google", "kakao-channel")   # GM 2026-09-15 스레드·구글 추가 · 화면은 이 순서로 자리를 만든다


def _user(request):
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _admins():
    raw = os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _load():
    if not os.path.exists(SECRETS_FILE):
        return {}
    with open(SECRETS_FILE, encoding="utf-8") as f:
        return json.load(f) or {}


def _save(data):
    d = os.path.dirname(SECRETS_FILE) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ps-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, SECRETS_FILE)


def _code_ok(code):
    """결재 GM 코드와 대조 — approval_pins(APPROVAL_PIN_GM). 행이 없으면 거부(모르면 안 연다)."""
    import approval_pin
    from common import db
    with db.connect(readonly=True) as conn:
        stored = approval_pin.load(conn, approval_pin.GM_NAME)
    if stored is None:
        return False
    return approval_pin.judge(approval_pin.GM_NAME, stored, code) is None


def mask_id(v):
    v = str(v or "")
    return (v[:2] + "*" * max(3, len(v) - 2)) if v else ""


def _key(body):
    t = str(body.get("tenant") or "").strip().lower()
    c = str(body.get("channel") or "").strip().lower()
    if not t or c not in CHANNELS or "/" in t:
        return None
    return t + "/" + c


def listing(data):
    return [{"tenant": k.split("/")[0], "channel": k.split("/")[1], "id_masked": mask_id(v.get("id")),
             "has_pw": bool(v.get("pw")), "note": v.get("note", ""), "received_at": v.get("received_at", ""),
             "updated_by": v.get("updated_by", "")} for k, v in sorted(data.items())]


@router.get("/api/admin/partner-secrets")
def list_secrets(request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return {"ok": True, "items": listing(_load()), "channels": list(CHANNELS)}


@router.post("/api/admin/partner-secrets/reveal")
async def reveal(request: Request):
    who = _user(request)
    if who not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    key = _key(body)
    if not key:
        return JSONResponse({"ok": False, "error": "tenant/channel"}, status_code=400)
    if not _code_ok(str(body.get("code") or "")):
        print("[partner-secrets] %s 보기 거부(코드 불일치) %s" % (who, key), flush=True)
        return JSONResponse({"ok": False, "error": "코드가 맞지 않습니다"}, status_code=403)
    v = _load().get(key)
    if not v:
        return JSONResponse({"ok": False, "error": "없음"}, status_code=404)
    print("[partner-secrets] %s 보기 %s" % (who, key), flush=True)
    return {"ok": True, "id": v.get("id", ""), "pw": v.get("pw", ""), "note": v.get("note", "")}


@router.post("/api/admin/partner-secrets")
async def upsert(request: Request):
    who = _user(request)
    if who not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    key = _key(body)
    if not key:
        return JSONResponse({"ok": False, "error": "tenant/channel"}, status_code=400)
    if not _code_ok(str(body.get("code") or "")):
        print("[partner-secrets] %s 저장 거부(코드 불일치) %s" % (who, key), flush=True)
        return JSONResponse({"ok": False, "error": "코드가 맞지 않습니다"}, status_code=403)
    data = _load()
    if body.get("delete"):
        data.pop(key, None)
        _save(data)
        print("[partner-secrets] %s 삭제 %s" % (who, key), flush=True)
        return {"ok": True, "deleted": key}
    _id, pw = str(body.get("id") or "").strip(), str(body.get("pw") or "")
    if not _id or not pw:
        return JSONResponse({"ok": False, "error": "아이디·비밀번호 둘 다 필요"}, status_code=400)
    data[key] = {"id": _id, "pw": pw, "note": str(body.get("note") or "")[:200],
                 "received_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"), "updated_by": who}
    _save(data)
    print("[partner-secrets] %s 저장 %s" % (who, key), flush=True)
    return {"ok": True, "saved": key}


@router.get("/api/partner-secrets/fetch")
def fetch(request: Request, tenant: str = "", channel: str = ""):
    """발행 PC 자동화 — 열쇠 헤더로만. 값은 실행 때 환경변수로만 쓰고 디스크에 남기지 않는다(호출 쪽 규약)."""
    want = os.environ.get("ERP_TOKEN_PUSH_KEY", "")
    got = request.headers.get("x-token-push-key", "")
    if not want or got != want:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    key = _key({"tenant": tenant, "channel": channel})
    v = _load().get(key) if key else None
    if not v:
        return JSONResponse({"ok": False, "error": "없음"}, status_code=404)
    print("[partner-secrets] 자동화 읽기 %s" % key, flush=True)
    return {"ok": True, "id": v.get("id", ""), "pw": v.get("pw", "")}


def selftest():
    import stat
    global SECRETS_FILE
    with tempfile.TemporaryDirectory() as d:
        SECRETS_FILE = os.path.join(d, "s.json")
        assert _load() == {}
        _save({"jo/naver-blog": {"id": "gocheok_golf", "pw": "Xample1234!", "note": "", "received_at": "2026-09-15 13:40"}})
        assert stat.S_IMODE(os.stat(SECRETS_FILE).st_mode) == 0o600 or os.name == "nt"
        row = listing(_load())[0]
        assert row["id_masked"] == "go**********" and row["has_pw"] and "Xample" not in json.dumps(row)
    assert _key({"tenant": "jo", "channel": "instagram"}) == "jo/instagram"
    assert _key({"tenant": "jo", "channel": "tiktok"}) is None and _key({"tenant": "a/b", "channel": "instagram"}) is None
    assert mask_id("ab") == "ab***"
    print("selftest ok")


if __name__ == "__main__":
    selftest()
