# -*- coding: utf-8 -*-
"""문자(SMS/LMS) 관리 API — 문구 저장소 CRUD·시험 발송·발송 로그·화면 버튼 발송 (배 2714 · 2026-09-17 시토).

실제 딜라이브 발송은 dlive_sms.py 한 곳(약속 L21) — 이 파일은 그 위의 얇은 라우터뿐.
관리자 판정 = api_partner_secrets.py 와 같은 방식(ERP_PLATFORM_ADMINS · x-erp-user 헤더) 재사용.

  GET  /api/admin/sms/templates              관리자만 · 문구 목록(렌더 미리보기·글자수 포함)
  PUT  /api/admin/sms/templates/{id}          관리자만 · body/name/sample/state 등 patch
  POST /api/admin/sms/test                    관리자만 · {rcpt,template_id,vars} · 하루 10건 상한 · 발효 아니어도 시험 가능
  GET  /api/admin/sms/log                     관리자만 · 최근 발송 로그
  POST /api/sms/send                          로그인 직원 · {template_id,rcpt,vars,origin_key} · 화면 버튼용(발효 문구만)
"""
import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import dlive_sms

router = APIRouter()

PHONE_RE = re.compile(r"^01[0-9]{8,9}$")
DAILY_TEST_LIMIT = 10


def _user(request):
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _admins():
    raw = os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _digits(v):
    return "".join(ch for ch in str(v or "") if ch.isdigit())


@router.get("/api/admin/sms/templates")
def list_templates(request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    data = dlive_sms.load_templates()
    items = []
    for tid, row in sorted(data.items()):
        text = dlive_sms.render(row.get("body", ""), row.get("sample") or {})
        items.append(dict(row, id=tid, rendered=text, len=len(text), msg_type=dlive_sms.msg_type_for(text)))
    return {"ok": True, "items": items}


@router.put("/api/admin/sms/templates/{template_id}")
async def update_template(template_id: str, request: Request):
    who = _user(request)
    if who not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    row = dlive_sms.save_template(template_id, body, who)
    return {"ok": True, "item": row}


@router.post("/api/admin/sms/test")
async def test_send(request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    rcpt = _digits(body.get("rcpt"))
    if not PHONE_RE.match(rcpt):
        return JSONResponse({"ok": False, "error": "번호 형식이 아닙니다"}, status_code=400)
    prefix = dlive_sms.today_str()
    today_tests = [r for r in dlive_sms.recent_log(500) if r.get("tag") == "test" and r.get("at", "").startswith(prefix)]
    if len(today_tests) >= DAILY_TEST_LIMIT:
        return JSONResponse({"ok": False, "error": "하루 시험 발송 %d건 상한" % DAILY_TEST_LIMIT}, status_code=429)
    result = dlive_sms.send(body.get("template_id"), rcpt, body.get("vars") or {},
                             origin_key="test-%d" % int(time.time()), force=True, tag="test", require_active=False)
    return result


@router.get("/api/admin/sms/log")
def sms_log(request: Request, limit: int = 50):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return {"ok": True, "items": dlive_sms.recent_log(limit)}


@router.post("/api/sms/send")
async def send_endpoint(request: Request):
    if not _user(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body = await request.json()
    rcpt = _digits(body.get("rcpt"))
    if not PHONE_RE.match(rcpt):
        return JSONResponse({"ok": False, "error": "번호 형식이 아닙니다"}, status_code=400)
    result = dlive_sms.send(body.get("template_id"), rcpt, body.get("vars") or {},
                             origin_key=str(body.get("origin_key") or ""))
    return result
