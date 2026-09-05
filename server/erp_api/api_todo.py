# -*- coding: utf-8 -*-
"""업무·결재 SSOT 미러 API (읽기 전용 · 배 922 레인 T). app.py 가 api_*.py 를 자동 등록한다.

  GET /api/todo?status=&dept=&owner=&limit=&offset=   목록 (todo_items)
  GET /api/todo/summary    home 업무 카드와 같은 정의(실무진 담당 행 · 전체/이번달/오늘 × 진행/완료/보류) + 결재 대기/완료/반려
  GET /api/todo/health     미러 건수 · 마지막 동기화
  GET /api/todo/{id}       항목 하나(결재 정보 포함)
정본은 시트 — 응답마다 _source=sheet-mirror. nginx auth_request 뒤에서만 열린다(무쿠키 401).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402
from sync_todo import STAFF, is_staff  # noqa: E402  — 집계 정의는 동기화 쪽 한 곳

SOURCE = "sheet-mirror"
KST = timezone(timedelta(hours=9))
router = APIRouter(prefix="/api/todo")


def _open():
    try:
        return db.connect(readonly=True)
    except db.Error as e:
        raise HTTPException(503, "DB 열기 실패: %s" % e)


def _row(r, appr=None):
    d = json.loads(r["data"])
    d["_id"] = r["id"]
    d["_dept"] = r["dept"]
    d["_status"] = r["status"]
    d["_synced_at"] = r["synced_at"]
    d["_source"] = SOURCE
    if appr is not None:
        d["_approval"] = {"approvers": appr["approvers"], "status": appr["appr_status"], "sign_head": appr["sign_head"],
                          "sign_gm": appr["sign_gm"], "sign_ceo": appr["sign_ceo"], "completed_at": appr["completed_at"]}
    return d


def work_stats(rows):
    """home workStats 와 같다: 진행 = 완료·보류 아닌 것."""
    done = sum(1 for r in rows if r["status"] == "완료")
    hold = sum(1 for r in rows if r["status"] == "보류")
    t = len(rows)
    return {"total": t, "active": t - done - hold, "done": done, "hold": hold, "rate": round(done / t * 100) if t else 0}


def summarize(conn, today):
    """실무진 담당 행(쉼표 담당자 중 하나라도 실무진) — home 카드 workAllArr 와 동일. 이번달·오늘 = 생성일 앞자리."""
    rows = [r for r in conn.execute("SELECT owner, status, created FROM todo_items WHERE tenant_id=%s", (db.TENANT,)).fetchall()
            if is_staff(r["owner"])]
    ym = today[:7]
    apprs = conn.execute("SELECT appr_status FROM approvals WHERE tenant_id=%s", (db.TENANT,)).fetchall()
    a_done = sum(1 for a in apprs if a["appr_status"] == "결재완료")
    a_rej = sum(1 for a in apprs if "반려" in (a["appr_status"] or ""))
    return {
        "work": {"all": work_stats(rows),
                 "month": work_stats([r for r in rows if r["created"][:7] == ym]),
                 "today": work_stats([r for r in rows if r["created"] == today])},
        "approval": {"total": len(apprs), "pending": len(apprs) - a_done - a_rej, "done": a_done, "reject": a_rej},
        "month": ym, "today": today, "staff": STAFF,
    }


@router.get("/summary")
def summary():
    conn = _open()
    with conn:
        out = summarize(conn, datetime.now(KST).strftime("%Y-%m-%d"))
        out["last_sync_kst"] = db.meta_get(conn, "todo_last_sync")
    out["_source"] = SOURCE
    return out


@router.get("/health")
def health():
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:
        return {"ok": False, "detail": "DB 열기 실패: %s" % e, "_source": SOURCE}
    with conn:
        n = conn.execute("SELECT COUNT(*) FROM todo_items WHERE tenant_id=%s", (db.TENANT,)).fetchone()[0]
        a = conn.execute("SELECT COUNT(*) FROM approvals WHERE tenant_id=%s", (db.TENANT,)).fetchone()[0]
        last, failed = db.meta_get(conn, "todo_last_sync"), db.meta_get(conn, "todo_last_failed")
    return {"ok": n > 0, "rows": n, "approvals": a, "last_sync_kst": last, "last_failed_kst": failed or "", "_source": SOURCE}


def _gm_ok(include_gm, gmkey, key_env=None):
    """GAS `_gmKeyOk_` 와 같은 판정 — 김남욱GM 행 통로 열쇠(배326). 값은 서버 env GM_TODO_KEY 한 곳에만."""
    k = (key_env if key_env is not None else os.environ.get("GM_TODO_KEY", "")).strip()
    return include_gm == 1 and bool(k) and gmkey.strip() == k


@router.get("")
def todo_list(
    status: Optional[str] = None,     # 진행중 · 완료 · 보류 (시트 상태값 그대로)
    dept: Optional[str] = None,       # 운영부 · 시설부 · 파트너팀
    owner: Optional[str] = None,      # 담당자 부분일치
    include_gm: int = Query(0, ge=0, le=1),   # GAS todo_list 와 같은 이름
    gmkey: str = Query(""),                   # GAS _gmKeyOk_ 와 같은 열쇠(env GM_TODO_KEY)
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    where, args = ["tenant_id = %s"], [db.TENANT]
    if not _gm_ok(include_gm, gmkey):
        # GAS 와 같은 기준 칸(담당자) · 부분일치 — todo_list 필터 e.parameter.owner 와는 별개(배326 보호)
        # 띄어쓰기 무시 — 전사일정 정본 표기가 「김남욱 GM」(2026-09-03 통일)이라 GAS 의 '김남욱GM' 부분일치는
        # 그 행들을 못 거른다(2026-09-05 실측: 기본 응답 100건 중 GM 담당 10건 노출). 서버는 공백을 지우고 비교한다.
        # 직함 없는 '김남욱' 표기도 1건 있어(AI 가 적은 행) 이름만으로 거른다 — 같은 이름의 실무진은 없다.
        # COALESCE — NULL NOT LIKE 는 NULL(참 아님)이라 담당자 빈 행이 통째로 빠지던 버그 수리(검수 M6).
        # creator 도 같은 조건으로 AND — 담당자는 실무진인데 생성자가 GM 인 개인 행까지 같이 가린다.
        where.append("COALESCE(REPLACE(owner, ' ', ''), '') NOT LIKE %s"); args.append("%김남욱%")
        where.append("COALESCE(REPLACE(creator, ' ', ''), '') NOT LIKE %s"); args.append("%김남욱%")
    if status:
        where.append("status = %s"); args.append(status)
    if dept:
        where.append("dept = %s"); args.append(dept)
    if owner:
        where.append("owner LIKE %s"); args.append("%" + owner.strip() + "%")
    w = " AND ".join(where)
    conn = _open()
    with conn:
        total = conn.execute("SELECT COUNT(*) FROM todo_items WHERE " + w, args).fetchone()[0]
        rows = conn.execute("SELECT * FROM todo_items WHERE " + w + " ORDER BY created DESC, id LIMIT %s OFFSET %s",
                            args + [limit, offset]).fetchall()
    data = [_row(r) for r in rows]
    return {"ok": True, "data": data,       # GAS 봉투 그대로 — 화면 어댑터 제거용
            "total": total, "count": len(rows), "limit": limit, "offset": offset, "rows": data, "_source": SOURCE}


@router.get("/{item_id}")
def todo_item(
    item_id: str,
    include_gm: int = Query(0, ge=0, le=1),   # 목록(todo_list)과 같은 GM 행 게이트(검수 H5 — 단건 조회는 안 걸렸었다)
    gmkey: str = Query(""),
):
    where, args = ["tenant_id=%s", "id=%s"], [db.TENANT, item_id]
    if not _gm_ok(include_gm, gmkey):
        where.append("COALESCE(REPLACE(owner, ' ', ''), '') NOT LIKE %s"); args.append("%김남욱%")
        where.append("COALESCE(REPLACE(creator, ' ', ''), '') NOT LIKE %s"); args.append("%김남욱%")
    conn = _open()
    with conn:
        r = conn.execute("SELECT * FROM todo_items WHERE " + " AND ".join(where), args).fetchone()
        if r is None:
            raise HTTPException(404, "없는 업무 id")
        a = conn.execute("SELECT * FROM approvals WHERE tenant_id=%s AND id=%s", (db.TENANT, item_id)).fetchone()
    return _row(r, a)


if __name__ == "__main__" and "--selftest" in sys.argv:
    # 집계 정의 자체점검 — DB 없이 work_stats 만(진행 = 전체 - 완료 - 보류).
    s = work_stats([{"status": "진행중"}, {"status": "완료"}, {"status": "보류"}, {"status": ""}])
    assert (s["total"], s["active"], s["done"], s["hold"], s["rate"]) == (4, 2, 1, 1, 25), s
    # GM 행 게이트 — include_gm=1 + 맞는 열쇠일 때만 통과(GAS _gmKeyOk_ 와 동치, DB 없이).
    assert _gm_ok(1, "abc", "abc") and not _gm_ok(1, "abc", "xyz")
    assert not _gm_ok(0, "abc", "abc"), "include_gm 없으면 항상 false"
    assert not _gm_ok(1, "abc", ""), "서버 열쇠 비어 있으면 항상 false(안전 기본)"
    assert _gm_ok(1, " abc ", "abc"), "양쪽 trim 뒤 비교(GAS _gmKeyOk_ 와 동치)"
    print("selftest ok")
