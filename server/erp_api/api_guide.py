# -*- coding: utf-8 -*-
"""AI 운영 가이드 화면(clevel-guide.html) 저장 통로 — 구글(Apps Script commit_file)에서 서버로
(GM 지시 2026-09-14 「AWS 이관 오늘 마무리」 · 지시자 시토).

서버엔 깃허브 쓰기 열쇠가 없다(GM 토큰 발급 전) — 그래서 저장은 2단계다:
  1) 화면이 POST /api/guide/commit 으로 보내면 여기서 대기 파일(pending/)에 받아 둔다.
  2) GM PC 의 scripts/guide_edits_apply.py 가 GET /api/guide/pending 으로 가져가
     실제로 저장소 파일에 쓰고 커밋한 뒤 POST /api/guide/applied 로 치운다(pending→applied).

pending/applied 두 경로는 로그인 쿠키 없이 열쇠(X-Token-Push-Key)로만 여는 통로다
(api_token_usage.py 와 같은 열쇠 — server/erp_api/guide.nginx.conf 가 auth_request 를 뺀다).
commit 경로는 그대로 /api/ 기본 관문(로그인+역할)을 지난다.

⚠️ 역할 헤더(X-Erp-Role)는 아직 신뢰 대상이 아니다(api_hr.py 참고 — 관문이 그 헤더를 덮어쓰는
배포가 아직 안 끝났다). 그래서 관리자 판정은 로그인 이메일(X-Erp-User, 관문이 항상 덮어씀)을
erp_auth/app.py 의 PLATFORM_ADMINS 와 같은 환경변수(ERP_PLATFORM_ADMINS)로 재는 방식을 그대로 쓴다.
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request

from api_token_usage import _check_key  # 열쇠 검사 재사용(중복 구현 금지)

router = APIRouter(prefix="/api/guide")

KST = timezone(timedelta(hours=9))
STORE_DIR = os.path.join(os.environ.get("ERP_STATUS_DIR", "/srv/erp/status"), "guide_edits")
PENDING_DIR = os.path.join(STORE_DIR, "pending")
APPLIED_DIR = os.path.join(STORE_DIR, "applied")
MAX_BODY = 2 * 1024 * 1024

# 저장 허용 경로 — 하나뿐(2026-09-14). 화면이 늘면 여기만 넓힌다.
ALLOWED_PATHS = frozenset([
    "3. 웰페리온 가이드/coo/bootsetup_matrix.json",
])

ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}$")


def _admins():
    raw = os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def _is_admin(request):
    email = (request.headers.get("x-erp-user") or "").strip().lower()
    return bool(email) and email in _admins()


@router.post("/commit")
async def commit(request: Request):
    if not _is_admin(request):
        raise HTTPException(403, "관리자만 저장할 수 있습니다")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(403, "본문 2MB 초과")
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "본문이 JSON 이 아닙니다")
    path = str(payload.get("path") or "")
    content = payload.get("content")
    message = str(payload.get("message") or "")
    if path not in ALLOWED_PATHS:
        raise HTTPException(400, "허용되지 않은 경로: %s" % path)
    if not isinstance(content, str):
        raise HTTPException(400, "content 는 문자열(JSON 원문)이어야 합니다")
    try:
        json.loads(content)
    except Exception:
        raise HTTPException(400, "content 가 JSON 으로 파싱되지 않습니다")

    os.makedirs(PENDING_DIR, exist_ok=True)
    now = datetime.now(KST)
    edit_id = now.strftime("%Y%m%dT%H%M%S")
    fname = os.path.join(PENDING_DIR, edit_id + ".json")
    if os.path.exists(fname):
        edit_id = edit_id + "-" + str(os.getpid())
        fname = os.path.join(PENDING_DIR, edit_id + ".json")
    record = {
        "id": edit_id, "path": path, "content": content, "message": message,
        "by": (request.headers.get("x-erp-user") or "").strip().lower(),
        "at": now.isoformat(),
    }
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return {"ok": True, "queued": True, "id": edit_id}


@router.get("/pending")
def pending(request: Request):
    _check_key(request)
    items = []
    if os.path.isdir(PENDING_DIR):
        for name in sorted(os.listdir(PENDING_DIR)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(PENDING_DIR, name), encoding="utf-8") as f:
                    items.append(json.load(f))
            except Exception:
                continue
    return {"items": items}


@router.post("/applied")
async def applied(request: Request):
    _check_key(request)
    payload = await request.json()
    ids = payload.get("ids") or []
    os.makedirs(APPLIED_DIR, exist_ok=True)
    moved = []
    for edit_id in ids:
        edit_id = str(edit_id)
        if not ID_RE.match(edit_id.split("-")[0]):
            continue
        src = os.path.join(PENDING_DIR, edit_id + ".json")
        if os.path.exists(src):
            os.replace(src, os.path.join(APPLIED_DIR, edit_id + ".json"))
            moved.append(edit_id)
    return {"ok": True, "moved": moved}


def selftest():
    class _Req:
        def __init__(self, headers, body=b""):
            self.headers = headers
            self._body = body

        async def body(self):
            return self._body

        async def json(self):
            return json.loads(self._body.decode("utf-8"))

    assert not _is_admin(_Req({}))
    assert not _is_admin(_Req({"x-erp-user": "someone@gmail.com"}))
    assert _is_admin(_Req({"x-erp-user": " CAO@wellperion.com "}))

    # 403 — 관리자 아님
    import asyncio
    try:
        asyncio.run(commit(_Req({"x-erp-user": "staff@wellperion.com"},
                                 json.dumps({"path": "x", "content": "{}"}).encode())))
        raise AssertionError("403 이 안 났다")
    except HTTPException as e:
        assert e.status_code == 403

    # 400 — 허용 경로 밖
    try:
        asyncio.run(commit(_Req({"x-erp-user": "cao@wellperion.com"},
                                 json.dumps({"path": "아무거나", "content": "{}"}).encode())))
        raise AssertionError("400 이 안 났다")
    except HTTPException as e:
        assert e.status_code == 400

    # 정상 — 대기열에 쌓인다
    res = asyncio.run(commit(_Req({"x-erp-user": "cao@wellperion.com"},
                                   json.dumps({"path": list(ALLOWED_PATHS)[0],
                                               "content": json.dumps({"a": 1}),
                                               "message": "테스트"}).encode())))
    assert res["ok"] and res["queued"] and res["id"]
    fname = os.path.join(PENDING_DIR, res["id"] + ".json")
    assert os.path.exists(fname)
    os.remove(fname)
    print("selftest ok")


if __name__ == "__main__":
    selftest()
