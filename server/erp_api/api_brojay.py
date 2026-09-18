# -*- coding: utf-8 -*-
"""브로제이 매출·입장 적재분 읽기 API (읽기 전용 · 배 959). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/brojay/sales?date=2026-09-03            그날 저장된 브로제이 응답 그대로
  GET /api/brojay/sales?from=&to=                  구간 — [{date, data}] 목록
  GET /api/brojay/entries?date= | ?from=&to=       입장(출입) 같은 모양
  GET /api/brojay/sessions?date= | ?from=&to= | ?month=YYYY-MM   강습 일정·출석 차감(브로제이 schedules 응답 그대로 · 배 2663)
  GET /api/brojay/members                          회원 명단 최신 스냅샷(member_id·name·phone_number… · 배 2664) · ?date= 로 특정 날
  GET /api/brojay/trainers                         강사 명단 최신 스냅샷(trainer_id→name · sessions 의 trainer_ids 해석용)
  GET /api/brojay/member_tickets?phones=010...,010...  전화별 회원권·수강권 기간(읽기 전용 · 배 12761) — 이름·주소는 안 준다
  GET /api/brojay/health                           kind 별 일수·최근 날짜·마지막 성공/실패

정본은 브로제이 — 응답마다 _source=brojay. 칸 이름은 브로제이가 준 그대로 두고 가공하지 않는다
(대조·집계는 화면 몫). nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

SOURCE = "brojay"
KINDS = ("sales", "entries", "sessions", "members", "trainers")
SNAPSHOT_KINDS = ("members", "trainers")          # 날짜 열쇠가 아니라 「받은 날」 열쇠 · 최신 한 벌만 있다(sync_brojay.prune_snapshots)
KST = timezone(timedelta(hours=9))
router = APIRouter(prefix="/api/brojay")


def _conn():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _range(kind, frm, to):
    conn = _conn()
    with conn:
        rows = conn.execute(
            "SELECT key, data, synced_at FROM brojay_records WHERE tenant_id=%s AND kind=%s AND key BETWEEN %s AND %s"
            " ORDER BY key", (db.TENANT, kind, frm, to)).fetchall()
    conn.close()
    return [{"date": r["key"], "synced_at": r["synced_at"], "data": json.loads(r["data"])} for r in rows]


def _month_range(month):
    """'YYYY-MM' → (첫날, 말일). 모양이 아니면 400."""
    try:
        y, m = int(month[:4]), int(month[5:7])
        assert len(month) == 7 and month[4] == "-" and 1 <= m <= 12
    except (ValueError, AssertionError):
        raise HTTPException(400, "month 는 YYYY-MM 모양: %r" % month)
    first = datetime(y, m, 1)
    last = (datetime(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


def _latest(kind, date):
    """스냅샷 kind — date 없으면 가장 최근 한 벌."""
    conn = _conn()
    with conn:
        if date:
            row = conn.execute("SELECT key, data, synced_at FROM brojay_records WHERE tenant_id=%s AND kind=%s AND key=%s",
                               (db.TENANT, kind, date)).fetchone()
        else:
            row = conn.execute("SELECT key, data, synced_at FROM brojay_records WHERE tenant_id=%s AND kind=%s ORDER BY key DESC LIMIT 1",
                               (db.TENANT, kind)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "적재된 %s 없음%s" % (kind, (": " + date) if date else " — sync_brojay 가 아직 한 번도 못 받음"))
    return {"date": row["key"], "synced_at": row["synced_at"], "data": json.loads(row["data"]), "_source": SOURCE}


def _serve(kind, date, frm, to):
    if date:
        got = _range(kind, date, date)
        if not got:
            raise HTTPException(404, "적재된 %s 없음: %s" % (kind, date))
        d = dict(got[0])
        d["_source"] = SOURCE
        return d
    today = datetime.now(KST).strftime("%Y-%m-%d")
    frm, to = frm or today, to or today
    got = _range(kind, frm, to)
    return {"from": frm, "to": to, "count": len(got), "days": got, "_source": SOURCE}


@router.get("/sales")
def sales(date: Optional[str] = None, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    return _serve("sales", date, frm, to)


@router.get("/entries")
def entries(date: Optional[str] = None, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    return _serve("entries", date, frm, to)


@router.get("/sessions")
def sessions(date: Optional[str] = None, frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
             month: Optional[str] = None):
    if month and not date:
        frm, to = _month_range(month)
    return _serve("sessions", date, frm, to)


_TICKET_FIELDS = {  # 화면에 주는 이름 → 브로제이 원본 칸 이름
    "member_start": "total_member_ticket_start_at", "member_end": "total_member_ticket_end_at",
    "lesson_start": "total_lesson_ticket_start_at", "lesson_end": "total_lesson_ticket_end_at",
    "status": "customer_status", "trainer": "trainer_name",
}
_ticket_index_cache = [None, None]   # [snapshot key, {정규화전화: {...}}] — members 스냅샷이 안 바뀌면 재사용(9,841건 매 요청 파싱 방지)


def _norm_phone(p):
    return "".join(c for c in str(p or "") if c.isdigit())


def _ticket_index():
    """members 최신 스냅샷을 전화→회원권 기간 dict 로 한 번만 만들어 캐시한다. 스냅샷 키(날짜)가 바뀌면 다시 만든다."""
    snap = _latest("members", None)
    key = snap["date"]
    if _ticket_index_cache[0] == key:
        return key, _ticket_index_cache[1]
    idx = {}
    for m in (snap["data"] or {}).get("data") or []:
        phone = _norm_phone(m.get("phone_number"))
        if not phone:
            continue
        rec = {out: m.get(src) for out, src in _TICKET_FIELDS.items()}
        last_visit = m.get("last_attendance_date")
        rec["last_visit"] = str(last_visit)[:10] if last_visit else None
        idx[phone] = rec
    _ticket_index_cache[0], _ticket_index_cache[1] = key, idx
    return key, idx


@router.get("/member_tickets")
def member_tickets(phones: str = ""):
    wanted = [_norm_phone(p) for p in phones.split(",") if _norm_phone(p)][:500]
    key, idx = _ticket_index()
    return {"snapshot": key, "items": {p: idx[p] for p in wanted if p in idx}, "_source": SOURCE}


@router.get("/members")
def members(date: Optional[str] = None):
    return _latest("members", date)


@router.get("/trainers")
def trainers(date: Optional[str] = None):
    return _latest("trainers", date)


def _selfcheck_month():
    assert _month_range("2026-09") == ("2026-09-01", "2026-09-30")
    assert _month_range("2026-12") == ("2026-12-01", "2026-12-31")
    assert _month_range("2028-02") == ("2028-02-01", "2028-02-29")
    for bad in ("2026-9", "2026-13", "202609", "abcd-ef"):
        try:
            _month_range(bad)
        except HTTPException as e:
            assert e.status_code == 400
        else:
            raise AssertionError("걸렀어야 한다: %r" % bad)
    print("selfcheck month ok")


@router.get("/health")
def health():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        rows = conn.execute(
            "SELECT kind, COUNT(*) c, MIN(key) a, MAX(key) b FROM brojay_records WHERE tenant_id=%s GROUP BY kind",
            (db.TENANT,)).fetchall()
        last, failed = db.meta_get(conn, "brojay_last_sync"), db.meta_get(conn, "brojay_last_failed")
    conn.close()
    by_kind = {r["kind"]: {"days": r["c"], "first": r["a"], "last": r["b"]} for r in rows}
    total = sum(v["days"] for v in by_kind.values())
    return {
        "ok": total > 0 and not failed,
        "days": total,
        "by_kind": {k: by_kind.get(k, {"days": 0, "first": None, "last": None}) for k in KINDS},
        "last_sync_kst": last or "",
        "last_failed_kst": failed or "",
        # 적재가 0이면 이유를 그대로 보여준다 — 화면이 '0건'을 '매출 0원'으로 읽지 않게.
        "detail": "" if total else (failed or "아직 한 번도 적재되지 않음 — 브로제이 API 사양·계정 미수령(배 908)"),
        "_source": SOURCE,
    }


if __name__ == "__main__":
    _selfcheck_month()
