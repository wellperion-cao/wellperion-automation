# -*- coding: utf-8 -*-
"""문자(SMS/LMS) 관리 API — 문구 저장소 CRUD·시험 발송·발송 로그·화면 버튼 발송 (배 2714 · 2026-09-17 시토).

실제 딜라이브 발송은 dlive_sms.py 한 곳(약속 L21) — 이 파일은 그 위의 얇은 라우터뿐.
관리자 판정 = api_partner_secrets.py 와 같은 방식(ERP_PLATFORM_ADMINS · x-erp-user 헤더) 재사용.

  GET  /api/admin/sms/templates              관리자만 · 문구 목록(렌더 미리보기·글자수 포함)
  PUT  /api/admin/sms/templates/{id}          관리자만 · body/name/sample/state 등 patch
  POST /api/admin/sms/test                    관리자만 · {rcpt,template_id,vars} · 하루 10건 상한 · 발효 아니어도 시험 가능
  GET  /api/admin/sms/log                     관리자만 · 최근 발송 로그
  GET  /api/admin/sms/counts                  관리자만 · 오늘/이달 발송 건수 · 문구별 오늘 건수(GM 지시 2026-09-17)
  POST /api/sms/send                          로그인 직원 · {template_id,rcpt,vars,origin_key} · 화면 버튼용(발효 문구만)

2026-09-17 실측 — 시험 클라이언트가 cp949 로 본문을 보내자 request.json() 이 UnicodeDecodeError 로 500 을 냈다(api_sms.py:91).
그래서 POST/PUT 본문은 전부 _read_json() 을 거친다 — utf-8 로만 파싱하고, 아니면 400 으로 답한다(500 금지).
"""
import json
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


async def _read_json(request):
    """request.json() 대신 — 본문이 UTF-8 이 아니거나 JSON 이 아니면 500 대신 400 을 낸다."""
    raw = await request.body()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, JSONResponse({"ok": False, "error": "본문 인코딩이 UTF-8 이 아닙니다"}, status_code=400)
    try:
        return (json.loads(text) if text else {}), None
    except ValueError:
        return None, JSONResponse({"ok": False, "error": "JSON 형식이 아닙니다"}, status_code=400)


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
    body, err = await _read_json(request)
    if err:
        return err
    row = dlive_sms.save_template(template_id, body, who)
    return {"ok": True, "item": row}


@router.post("/api/admin/sms/test")
async def test_send(request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body, err = await _read_json(request)
    if err:
        return err
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


@router.get("/api/admin/sms/counts")
def sms_counts(request: Request):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return dict(dlive_sms.counts(), ok=True)


@router.post("/api/sms/send")
async def send_endpoint(request: Request):
    if not _user(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    body, err = await _read_json(request)
    if err:
        return err
    rcpt = _digits(body.get("rcpt"))
    if not PHONE_RE.match(rcpt):
        return JSONResponse({"ok": False, "error": "번호 형식이 아닙니다"}, status_code=400)
    result = dlive_sms.send(body.get("template_id"), rcpt, body.get("vars") or {},
                             origin_key=str(body.get("origin_key") or ""))
    c = dlive_sms.counts()
    result["today_sent"] = c["today_sent"]
    result["limit"] = c["today_limit"]
    return result
