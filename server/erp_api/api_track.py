# -*- coding: utf-8 -*-
"""전환 퍼널 첫 단 측정 — 홈·문의 페이지 조회/문의버튼 클릭 기록 (배1034 · 시모 요청 · 2026-09-05 시토).

POST /api/track            공개(무로그인) — view/click 1건 기록. 개인정보 저장 0(IP 미저장·User-Agent 원문 미저장,
                            bot 판정 결과만 남는다). 본문 2KB 상한.
GET  /api/track/summary     로그인 뒤 — 기간·그룹별 집계(views/clicks/sessions). bot 행 제외.
channel_code 는 sync_inquiries.channel_code_of 재사용(utm_source 텍스트 → 6종, CHANNEL_CUTOVER 이전은 unknown —
새 파이프라인이라 사실상 항상 판정됨).
nginx: POST 는 track.nginx.conf 의 `location = /api/track`(exact match)이 intake 존을 재사용해
       /api/ 관문(로그인 auth_request)보다 먼저 잡는다. GET .../summary 는 이 exact match 에 안 걸려
       그대로 /api/ 관문(로그인)을 탄다.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402
from sync_inquiries import channel_code_of  # noqa: E402  — utm_source 텍스트 → channel_code 6종 재사용

MAX_BODY = 2 * 1024
EVENTS = {"view", "click"}
_BOT_RE = re.compile(r"bot|crawl|spider|slurp|facebookexternalhit|whatsapp|telegram|curl|"
                      r"python-requests|python-urllib|headless|preview", re.I)
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"}   # 화면은 wellperion.com(다른 origin) 에서 fetch 로 보낸다
_GROUP_COLS = {"day": "left(ts,10)", "channel_code": "channel_code", "post_id": "post_id", "page": "page"}
router = APIRouter(prefix="/api/track")


def _kst_now():
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")


def _s(v, n):
    return str(v or "")[:n]


@router.options("")
@router.options("/")
def preflight():
    return Response(status_code=204, headers=CORS)


@router.post("")
@router.post("/")
async def track(request: Request):
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "본문 2KB 초과")
    try:
        p = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        p = {}
    if not isinstance(p, dict) or p.get("event") not in EVENTS:
        return Response(json.dumps({"ok": False, "error": "event 없음(view|click)"}, ensure_ascii=False),
                        status_code=400, media_type="application/json; charset=utf-8", headers=CORS)
    ts = _kst_now()
    is_bot = bool(_BOT_RE.search(request.headers.get("user-agent", "")))
    conn = db.connect()
    with conn:
        conn.execute(
            "INSERT INTO track_events (tenant_id, ts, event, page, target, channel_code, post_id,"
            " utm_source, utm_medium, utm_campaign, utm_content, ref_host, sid, is_bot)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (db.TENANT, ts, p["event"], _s(p.get("page"), 300), _s(p.get("target"), 100),
             channel_code_of(p.get("utm_source"), ts), _s(p.get("post_id"), 100),
             _s(p.get("utm_source"), 100), _s(p.get("utm_medium"), 100),
             _s(p.get("utm_campaign"), 100), _s(p.get("utm_content"), 100),
             _s(p.get("ref"), 200), _s(p.get("sid"), 64), is_bot))
    conn.close()
    return Response(json.dumps({"ok": True}, ensure_ascii=False),
                    media_type="application/json; charset=utf-8", headers=CORS)


@router.get("/summary")
def summary(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
            group: str = "day"):
    if group not in _GROUP_COLS:
        raise HTTPException(400, "group 은 day|channel_code|post_id|page")
    col = _GROUP_COLS[group]
    where, args = ["tenant_id=%s", "NOT is_bot"], [db.TENANT]
    if from_:
        where.append("ts >= %s"); args.append(from_ + " 00:00:00")
    if to:
        where.append("ts <= %s"); args.append(to + " 23:59:59")
    conn = db.connect(readonly=True)
    rows = conn.execute(
        "SELECT %s AS key,"
        " count(*) FILTER (WHERE event='view') AS views,"
        " count(*) FILTER (WHERE event='click') AS clicks,"
        " count(DISTINCT sid) FILTER (WHERE sid<>'') AS sessions"
        " FROM track_events WHERE %s GROUP BY 1 ORDER BY 1" % (col, " AND ".join(where)), args).fetchall()
    conn.close()
    return {"ok": True, "rows": [dict(r) for r in rows]}


if __name__ == "__main__":
    assert bool(_BOT_RE.search("Mozilla/5.0 (compatible; Googlebot/2.1)"))
    assert not _BOT_RE.search("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    print("selftest ok")
