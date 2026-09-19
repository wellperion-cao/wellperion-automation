# -*- coding: utf-8 -*-
"""강습 회원관리 미러 API (읽기 전용 · 배 922 레인 W + 배946 #6). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/lesson/stats?type=성인강습&scope=year|all   lesson_stats 응답 그대로
  GET /api/lesson/roster?type=성인강습                 lesson_registered_roster 응답 그대로
  GET /api/lesson/registry?type=성인강습&from=&to=     lesson_registry_list 응답 모양 — 등록일 from~to(기본 오늘 KST) 로 자른 data·count
  GET /api/lesson/members?type=성인강습&from=&to=      강습 등록 회원 — inquiries 표에서 직접(신설 · 배946 #6)
  GET /api/lesson/health                              미러 건수 · 마지막 동기화
  POST /api/lesson/refresh?type=성인강습                roster 즉시 재동기화(로그인 필요 · 같은 사람 30초 쿨다운 ·
                                                       sync_lesson.gas_get·upsert 재사용 — 새 동기화 로직 0 · 배2859 후속)

위 4개(stats·roster·registry·health)는 lesson_records 미러(GAS lesson_registry_list 등이 원천) 그대로다.
그 원천 시트(등록원장)는 2026-07-20 이후 갱신이 멈췄다(CPO 정의서 CPO-2026-09-03-AWS이관-시포도메인-문제점-보완.md #6).
새 members 라우트는 그 시트를 거치지 않고 이미 동기화되는 inquiries 미러(sync_inquiries.py)를 status=SUC/단기SUC 로 직접
읽는다 — 새 표를 만들지 않는다(정의서 지침). 등록일 우선순위는 화면 헬퍼 _lessonRegDateStr(membership.html)와 같다:
등록일(regDate) 없으면 접수일(timestamp) 폴백.
정본은 시트 — 응답마다 _source=sheet-mirror. nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_lesson  # noqa: E402 — /refresh 가 재사용하는 기존 동기화 함수(gas_get·upsert). 새 로직 안 만든다.

SOURCE = "sheet-mirror"
KST = timezone(timedelta(hours=9))
router = APIRouter(prefix="/api/lesson")
REFRESH_COOLDOWN_SEC = 30


def _get(kind, key):
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        r = conn.execute("SELECT data, synced_at FROM lesson_records WHERE tenant_id=%s AND kind=%s AND key=%s",
                         (db.TENANT, kind, key)).fetchone()
    conn.close()
    if r is None:
        raise HTTPException(404, "미러에 없음: %s %s" % (kind, key))
    d = json.loads(r["data"])
    d["_synced_at"] = r["synced_at"]
    d["_source"] = SOURCE
    return d


@router.get("/stats")
def stats(type: str = "성인강습", scope: str = "year"):
    return _get("stats", type + "|" + ("all" if scope == "all" else "year"))


@router.get("/roster")
def roster(type: str = "성인강습"):
    return _get("roster", type)


def _cooldown_remaining(last_ts, now_ts, window=REFRESH_COOLDOWN_SEC):
    """마지막 새로고침(last_ts, epoch 초 문자열)과 지금(now_ts) 차이가 window 안이면 남은 초, 아니면 0."""
    if not last_ts:
        return 0
    try:
        elapsed = now_ts - float(last_ts)
    except (TypeError, ValueError):
        return 0
    return max(0, int(window - elapsed)) if elapsed < window else 0


@router.post("/refresh")
def refresh(type: str = "성인강습", request: Request = None):
    """roster 즉시 재동기화 — 화면 새로고침(force=1)이 GAS 로 직행하던 것을 대체할 서버 문(배2859 후속).
    sync_lesson.gas_get·upsert 를 그대로 재사용(새 동기화 로직 0). 로그인 필요 · 같은 사람·종목 30초 쿨다운."""
    who = (request.headers.get("x-erp-user") or "").strip().lower() if request else ""
    if not who:
        raise HTTPException(403, "로그인한 계정만 새로고침할 수 있습니다")
    try:
        conn = db.connect()
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    cd_key = "lesson_refresh_cd:%s:%s" % (who, type)
    now_ts = time.time()
    with conn:
        remain = _cooldown_remaining(db.meta_get(conn, cd_key), now_ts)
    if remain:
        conn.close()
        raise HTTPException(429, "%d초 뒤 다시 시도하세요" % remain)
    sync_lesson.load_env()
    d = sync_lesson.gas_get("lesson_registered_roster", {"type": type, "fresh": "1"}, timeout=180)
    if not d:
        conn.close()
        raise HTTPException(502, "동기화 실패 — GAS 응답 없음")
    synced_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now_ts + 9 * 3600))
    sync_lesson.upsert(conn, [("roster", type, d)], synced_at)
    with conn:
        db.meta_set(conn, cd_key, str(now_ts))
    conn.close()
    return {"ok": True, "type": type, "synced_at": synced_at, "_source": SOURCE}


def slice_registry(d, frm, to):
    """GAS 와 같은 규칙 — 등록일 앞 10자가 from~to 안이면 남긴다. count 도 다시 센다."""
    rows = [r for r in d.get("data") or [] if frm <= str(r.get("등록일") or "")[:10] <= to]
    d.update({"from": frm, "to": to, "count": len(rows), "data": rows})
    return d


@router.get("/registry")
def registry(type: str = "성인강습", frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    return slice_registry(_get("registry", type), frm or today, to or today)


LESSON_SUC = ("SUC", "단기SUC")


def _lesson_reg_date(d):
    """화면 헬퍼 _lessonRegDateStr(membership.html)와 같은 우선순위 — 등록일 없으면 접수일 폴백."""
    return str(d.get("regDate") or d.get("timestamp") or "")[:10]


@router.get("/members")
def lesson_members(type: str = "성인강습", frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    """강습 등록 회원 — inquiries 미러에서 직접(구 lesson_registry 시트 우회 · 배946 #6).
    status IN (SUC,단기SUC)만. from~to 는 등록일(폴백 포함) 기준 — 기본은 전체."""
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)
    with conn:
        rows = conn.execute("SELECT data FROM inquiries WHERE tenant_id=%s AND type=%s", (db.TENANT, type)).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["data"])
        if d.get("status") not in LESSON_SUC:
            continue
        reg = _lesson_reg_date(d)
        if frm and reg < frm:
            continue
        if to and reg > to:
            continue
        out.append({"name": d.get("name"), "phone": d.get("phone"),
                    "program": d.get("regProgram") or d.get("sport"), "regDate": reg,
                    "status": d.get("status"), "rowKey": d.get("rowKey")})
    out.sort(key=lambda x: x["regDate"], reverse=True)
    return {"ok": True, "type": type, "from": frm, "to": to, "count": len(out), "data": out, "_source": SOURCE}


@router.get("/health")
def health():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = conn.execute("SELECT kind, key, data FROM lesson_records WHERE tenant_id=%s ORDER BY kind, key", (db.TENANT,)).fetchall()
        last, failed = db.meta_get(conn, "lesson_last_sync"), db.meta_get(conn, "lesson_last_failed")
    conn.close()
    counts = {}
    for r in rows:
        d = json.loads(r["data"])
        counts[r["kind"] + ":" + r["key"]] = d.get("total") if r["kind"] != "registry" else d.get("count")
    return {"ok": len(rows) == 8, "records": len(rows), "counts": counts, "last_sync_kst": last, "last_failed_kst": failed or "", "_source": SOURCE}


if __name__ == "__main__" and "--selftest" in sys.argv:
    d = slice_registry({"data": [{"등록일": "2026-09-01"}, {"등록일": "2026-09-03T10:00"}, {}]}, "2026-09-03", "2026-09-03")
    assert d["count"] == 1 and d["data"][0]["등록일"].startswith("2026-09-03"), d
    assert _lesson_reg_date({"regDate": "2026-09-01", "timestamp": "2026-08-01 10:00:00"}) == "2026-09-01", "등록일 우선"
    assert _lesson_reg_date({"regDate": "", "timestamp": "2026-08-01 10:00:00"}) == "2026-08-01", "등록일 없으면 접수일 폴백"
    assert _lesson_reg_date({}) == "", "둘 다 없으면 빈값"
    assert _cooldown_remaining(None, 1000) == 0, "이전 기록 없으면 즉시 허용"
    assert _cooldown_remaining("990", 1000) == 20, "10초 지남 → 남은 20초(30초 창)"
    assert _cooldown_remaining("960", 1000) == 0, "40초 지남 → 쿨다운 끝"
    assert _cooldown_remaining("bad", 1000) == 0, "깨진 값은 막지 않는다(정직 실패보다 통과)"
    print("selftest ok")
