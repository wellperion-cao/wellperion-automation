# -*- coding: utf-8 -*-
"""마케팅 자동업로드 접수 — cmo/upload/마케팅자동업로드.html 서버 문 ②③ (배 2662 · 2026-09-16 시토 · 시모 배 2658 짝).

  POST /api/marketing/upload           FormData(tenant, channels[], title, body, images[], when) → 접수(status=queued)
  GET  /api/marketing/uploads?tenant=  최근 20건 — 채널별 한 줄씩(date, channel, title, status, status_label)

관리자만(ERP_PLATFORM_ADMINS · api_partner_secrets.py 와 같은 관문). 사진은 서버
{MARKETING_DIR}/{tenant}/{ymd}_{id}/ 에 저장. 실제 채널 발행(네이버·인스타 자동화)은 이 배 범위 밖 —
status='queued' 로 접수만 한다.

발행 워커 1단계(배 12680 · 2026-09-16 시토) — 로그인 쿠키 없는 GM PC 워커가 부르는 문 2개(열쇠 헤더
X-Token-Push-Key = api_token_usage.py 와 같은 방식 · nginx 는 marketing-worker.nginx.conf 초안 참조):

  GET  /api/marketing/uploads/queue?tenant=  status=queued 행 전부(오래된 순)
  POST /api/marketing/uploads/status  {id, channel, status: drafted|failed|published, note}  → 채널별 상태 기록

채널별 상태는 channel_status(JSONB) 한 칸에 담는다 — {channel: {status, note, updated_at}}. 행 전체
status 는 _overall_status() 가 정한다: 하나라도 failed 면 재시도하도록 queued 유지, 접수된 채널
전부가 drafted/published 로 끝나면 그 값(전부 published 면 published, 아니면 drafted)으로 올린다.
"""
import datetime as dt
import hmac
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
STATUS_LABEL = {"queued": "접수됨", "ok": "발행됨", "fail": "실패",
                "drafted": "임시저장됨", "failed": "실패", "published": "발행됨"}
CHANNEL_STATUSES = ("drafted", "failed", "published")


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
            "SELECT channels, title, status, channel_status, created_at FROM marketing_uploads"
            " WHERE tenant_id=%s AND tenant=%s ORDER BY created_at DESC LIMIT 20",
            (db.TENANT, t)).fetchall()
    conn.close()
    items = []
    for r in rows:
        cs = r["channel_status"] or {}
        for c in (r["channels"] or [""]):
            st = (cs.get(c) or {}).get("status") or r["status"]
            items.append({"date": r["created_at"], "channel": c, "title": r["title"], "status": st,
                          "status_label": STATUS_LABEL.get(st, st)})
    return {"ok": True, "items": items}


def _check_key(request: Request) -> bool:
    """열쇠 헤더 확인 — 로그인 쿠키 없는 GM PC 워커 호출용(api_token_usage.py 와 같은 방식)."""
    want = os.environ.get("ERP_TOKEN_PUSH_KEY", "")
    got = request.headers.get("x-token-push-key", "")
    return bool(want) and hmac.compare_digest(got, want)


def _overall_status(channels, channel_status):
    """채널별 상태 → 행 전체 status. 순수 함수(라우트 밖) — _selfcheck 가 잰다."""
    if any((channel_status.get(c) or {}).get("status") == "failed" for c in channel_status):
        return "queued"
    if channels and all((channel_status.get(c) or {}).get("status") in ("drafted", "published") for c in channels):
        return "published" if all(channel_status[c]["status"] == "published" for c in channels) else "drafted"
    return "queued"


@router.get("/api/marketing/uploads/queue")
def uploads_queue(request: Request, tenant: str = ""):
    if not _check_key(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    t = (tenant or "").strip()
    conn = db.connect(readonly=True)
    with conn:
        if t:
            rows = conn.execute(
                "SELECT id, tenant, channels, title, body, files, channel_status, created_at FROM marketing_uploads"
                " WHERE tenant_id=%s AND tenant=%s AND status='queued' ORDER BY created_at ASC",
                (db.TENANT, t)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, tenant, channels, title, body, files, channel_status, created_at FROM marketing_uploads"
                " WHERE tenant_id=%s AND status='queued' ORDER BY created_at ASC",
                (db.TENANT,)).fetchall()
    conn.close()
    # channel_status 를 같이 준다(배 12752 #15) — 행이 queued 여도 이미 drafted/published 인 채널은 워커가
    # 건너뛰어야 한다(한 채널 남아 queued 유지 → 끝난 채널 재업로드 = 09-15 다캠 중복과 같은 꼴). 옛 행(NULL)은 {}.
    items = [{"id": r["id"], "tenant": r["tenant"], "channels": r["channels"], "title": r["title"],
              "body": r["body"], "files": r["files"], "channel_status": r["channel_status"] or {},
              "created_at": r["created_at"]} for r in rows]
    return {"ok": True, "items": items}


@router.post("/api/marketing/uploads/status")
async def uploads_status(request: Request):
    if not _check_key(request):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    payload = await request.json()
    uid = str(payload.get("id") or "").strip()
    channel = str(payload.get("channel") or "").strip()
    status = str(payload.get("status") or "").strip()
    note = str(payload.get("note") or "")
    if not uid or not channel or status not in CHANNEL_STATUSES:
        return JSONResponse({"ok": False, "error": "bad payload"}, status_code=400)
    conn = db.connect()
    with conn:
        row = conn.execute(
            "SELECT channels, channel_status FROM marketing_uploads WHERE tenant_id=%s AND id=%s",
            (db.TENANT, uid)).fetchone()
        if not row:
            conn.close()
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        cs = dict(row["channel_status"] or {})
        cs[channel] = {"status": status, "note": note, "updated_at": _now()}
        overall = _overall_status(row["channels"] or [], cs)
        conn.execute(
            "UPDATE marketing_uploads SET channel_status=%s::jsonb, status=%s WHERE tenant_id=%s AND id=%s",
            (json.dumps(cs, ensure_ascii=False), overall, db.TENANT, uid))
    conn.close()
    return {"ok": True, "status": overall}


def _selfcheck():
    """자체점검 3줄 — 가짜 tenant · 접수→목록에 보임 · 관리자 아니면 403 은 배포 뒤 실서버로 확인(README 참조).
    여기서는 순수 함수(라우트 밖) 판정만 — status 라벨·folder 경로 조립."""
    assert STATUS_LABEL["queued"] == "접수됨"
    tenant, uid = "selftest", "abc123def456"
    ymd = "20260916"
    saved = {"name": "x.jpg", "path": "/".join((tenant, "%s_%s" % (ymd, uid), "x.jpg"))}
    assert saved["path"] == "selftest/20260916_abc123def456/x.jpg"
    assert _overall_status(["naver-blog"], {"naver-blog": {"status": "drafted"}}) == "drafted"
    assert _overall_status(["naver-blog", "instagram"], {"naver-blog": {"status": "failed"}}) == "queued"
    assert _overall_status(["naver-blog"], {}) == "queued"
    assert _overall_status(["naver-blog"], {"naver-blog": {"status": "published"}}) == "published"
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
