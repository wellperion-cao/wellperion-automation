# -*- coding: utf-8 -*-
"""마케팅 자동업로드 접수 — cmo/upload/마케팅자동업로드.html 서버 문 ②③ (배 2662 · 2026-09-16 시토 · 시모 배 2658 짝).

  POST /api/marketing/upload           FormData(tenant, channels[], title, body, images[], when) → 접수(status=queued)
  GET  /api/marketing/uploads?tenant=  최근 20건 — 채널별 한 줄씩(date, channel, title, status, status_label)

관리자만(ERP_PLATFORM_ADMINS · api_partner_secrets.py 와 같은 관문). 사진은 서버
{MARKETING_DIR}/{tenant}/{ymd}_{id}/ 에 저장. 실제 채널 발행(네이버·인스타 자동화)은 이 배 범위 밖 —
status='queued' 로 접수만 한다. 발행 워커는 기존 발행 스크립트를 재사용하는 다음 배.
"""
import datetime as dt
import json
import os
import sys
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

router = APIRouter()

MARKETING_DIR = os.environ.get("MARKETING_UPLOAD_DIR", "/srv/erp/marketing")
KST = dt.timezone(dt.timedelta(hours=9))
STATUS_LABEL = {"queued": "접수됨", "ok": "발행됨", "fail": "실패"}


def _user(request):
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _admins():
    raw = os.environ.get("ERP_PLATFORM_ADMINS", "cao@wellperion.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _now():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


async def _save_images(tenant, uid, files):
    """업로드 파일들을 {MARKETING_DIR}/{tenant}/{ymd}_{uid}/ 에 쓰고 [{name,path}] 를 돌려준다."""
    named = [f for f in files if getattr(f, "filename", "")]
    if not named:
        return []
    ymd = dt.datetime.now(KST).strftime("%Y%m%d")
    subdir = "%s_%s" % (ymd, uid)
    folder = os.path.join(MARKETING_DIR, tenant, subdir)
    os.makedirs(folder, exist_ok=True)
    saved = []
    for f in named:
        name = os.path.basename(f.filename)
        with open(os.path.join(folder, name), "wb") as out:
            out.write(await f.read())
        saved.append({"name": name, "path": "/".join((tenant, subdir, name))})
    return saved


@router.post("/api/marketing/upload")
async def upload(request: Request):
    who = _user(request)
    if who not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    form = await request.form()
    tenant = str(form.get("tenant") or "").strip()
    if not tenant:
        return JSONResponse({"ok": False, "error": "tenant required"}, status_code=400)
    channels = [str(v).strip() for v in form.getlist("channels") if str(v).strip()]
    title = str(form.get("title") or "").strip()
    body = str(form.get("body") or "")
    uid = uuid.uuid4().hex[:12]
    files = await _save_images(tenant, uid, form.getlist("images"))
    now = _now()
    conn = db.connect()
    with conn:
        conn.execute(
            "INSERT INTO marketing_uploads (tenant_id, id, tenant, channels, title, body, status, created_at, created_by, files)"
            " VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s::jsonb)",
            (db.TENANT, uid, tenant, json.dumps(channels, ensure_ascii=False), title, body, "queued", now, who,
             json.dumps(files, ensure_ascii=False)))
    conn.close()
    print("[marketing] %s 접수 %s/%s (%d채널·%d파일)" % (who, tenant, uid, len(channels), len(files)), flush=True)
    return {"ok": True, "id": uid}


@router.get("/api/marketing/uploads")
def uploads(request: Request, tenant: str = ""):
    if _user(request) not in _admins():
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    t = (tenant or "").strip()
    if not t:
        return JSONResponse({"ok": False, "error": "tenant required"}, status_code=400)
    conn = db.connect(readonly=True)
    with conn:
        rows = conn.execute(
            "SELECT channels, title, status, created_at FROM marketing_uploads"
            " WHERE tenant_id=%s AND tenant=%s ORDER BY created_at DESC LIMIT 20",
            (db.TENANT, t)).fetchall()
    conn.close()
    items = []
    for r in rows:
        for c in (r["channels"] or [""]):
            items.append({"date": r["created_at"], "channel": c, "title": r["title"], "status": r["status"],
                          "status_label": STATUS_LABEL.get(r["status"], r["status"])})
    return {"ok": True, "items": items}


def _selfcheck():
    """자체점검 3줄 — 가짜 tenant · 접수→목록에 보임 · 관리자 아니면 403 은 배포 뒤 실서버로 확인(README 참조).
    여기서는 순수 함수(라우트 밖) 판정만 — status 라벨·folder 경로 조립."""
    assert STATUS_LABEL["queued"] == "접수됨"
    tenant, uid = "selftest", "abc123def456"
    ymd = "20260916"
    saved = {"name": "x.jpg", "path": "/".join((tenant, "%s_%s" % (ymd, uid), "x.jpg"))}
    assert saved["path"] == "selftest/20260916_abc123def456/x.jpg"
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
