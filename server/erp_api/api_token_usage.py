# -*- coding: utf-8 -*-
"""원격 PC 토큰 사용량 수집 통로 (GM 지시 2026-09-14).

다른 계정 PC(info@·lessons@)가 scripts/token_usage_push.py 로 이 PC의 클로드 사용량을 올리면
여기 파일로 저장하고, GM PC 의 scripts/token_usage.py 가 GET /remote 로 읽어 AI 토큰 현황에 합친다.
로그인 쿠키가 없는 통로라(nginx auth_request 없음) 열쇠 헤더(X-Token-Push-Key)로 대신 막는다 —
열쇠 = /srv/erp/api.env 의 ERP_TOKEN_PUSH_KEY. app.py 가 같은 폴더의 api_*.py 를 자동 등록한다
(app.py 본문은 건드리지 않는다).

  POST /api/token_usage/push    본문 = token_usage_push.py 가 만든 계정 하나짜리 요약(JSON)
  GET  /api/token_usage/remote  저장된 파일 전부 — {"<account>__<host>": payload, ...}
"""
import glob
import json
import os
import re

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/token_usage")

STORE_DIR = os.path.join(os.environ.get("ERP_STATUS_DIR", "/srv/erp/status"), "token_usage_remote")
MAX_BODY = 4 * 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9@._-]+$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+$")


def _check_key(request: Request):
    want = os.environ.get("ERP_TOKEN_PUSH_KEY")
    got = request.headers.get("x-token-push-key", "")
    if not want or got != want:
        raise HTTPException(403, "열쇠 불일치")


@router.post("/push")
def push(request: Request, payload: dict):
    _check_key(request)
    account = str(payload.get("account") or "")
    host = str(payload.get("host") or "")
    if not EMAIL_RE.match(account):
        raise HTTPException(400, "account 형식 오류")
    fname = "%s__%s.json" % (account, host)
    if not SAFE_NAME.match(fname) or ".." in fname:
        raise HTTPException(400, "host 형식 오류")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_BODY:
        raise HTTPException(403, "본문 4MB 초과")
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(os.path.join(STORE_DIR, fname), "wb") as f:
        f.write(body)
    return {"ok": True}


@router.get("/remote")
def remote(request: Request):
    _check_key(request)
    out = {}
    for path in glob.glob(os.path.join(STORE_DIR, "*.json")):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, encoding="utf-8") as f:
                out[name] = json.load(f)
        except Exception:
            continue
    return out
