# -*- coding: utf-8 -*-
"""전사 일정 SSOT — 로더·검증·업무결재 연동(예행).
SSOT = status/schedule_ssot.json (반복 의무·이벤트, type으로 종류 구분·현재=정기점검).
정본은 JSON, 이 모듈은 소비자. gate.auto_workapproval=False(기본)면 '무엇을 만들지'만
반환/로그하고 업무·결재를 건드리지 않는다."""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CAL_PATH = Path(__file__).resolve().parent.parent / "status" / "schedule_ssot.json"

_SCRIPTS_DIR_FOR_WORKLOG = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR_FOR_WORKLOG not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR_FOR_WORKLOG)

try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 선별 흐름 무영향
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False

REQUIRED_ITEM_KEYS = ["id", "name", "category", "dept", "cycle", "cycle_confirmed",
                       "legal_basis", "last_done", "next_due"]
VALID_STATUS = {"scheduled", "due_soon", "overdue", "done", "tbd"}


def load(path=CAL_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _kst_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def validate(cal: dict) -> list:
    """구조 계약 검증 — 정본 무결성 가드. 오류 리스트(빈=통과)."""
    errors = []
    if not isinstance(cal.get("items"), list):
        return ["items 키가 리스트가 아님"]
    depts = set(cal.get("depts", []))
    cats = set(cal.get("categories", {}).keys())
    seen = set()
    for it in cal["items"]:
        iid = it.get("id")
        for k in REQUIRED_ITEM_KEYS:
            if k not in it:
                errors.append(f"[{iid}] 필수키 누락: {k}")
        if iid in seen:
            errors.append(f"중복 id: {iid}")
        seen.add(iid)
        if it.get("dept") not in depts:
            errors.append(f"[{iid}] 미등록 부서: {it.get('dept')}")
        if it.get("category") not in cats:
            errors.append(f"[{iid}] 미등록 분류: {it.get('category')}")
    if "gate" not in cal or "auto_workapproval" not in cal.get("gate", {}):
        errors.append("gate.auto_workapproval 누락")
    return errors


def _parse_due(s):
    """next_due 문자열 → date. 빈칸/미확인/연월만 있으면 None(D-day 계산 불가)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d
        except ValueError:
            continue
    return None


def status_of(it: dict, today: date = None, lead_days: int = 30) -> dict:
    """항목 상태 판정 — 지어내지 않음: next_due 없으면 tbd."""
    today = today or _kst_today()
    due = _parse_due(it.get("next_due"))
    if due is None:
        return {"status": "tbd", "dday": None}
    dd = (due - today).days
    if dd < 0:
        st = "overdue"
    elif dd <= lead_days:
        st = "due_soon"
    else:
        st = "scheduled"
    return {"status": st, "dday": dd}


def _applies(it: dict) -> bool:
    """해당없음 항목은 달력·연동·집계에서 제외(설비 미보유 등)."""
    return it.get("applies") != "해당없음"


def due_items(cal: dict, today: date = None, lead_days: int = None) -> list:
    """기한 도래(임박·초과) 항목만 — 업무·결재 연동 후보. 해당없음 제외."""
    today = today or _kst_today()
    lead = cal.get("gate", {}).get("lead_days", 30) if lead_days is None else lead_days
    out = []
    for it in cal.get("items", []):
        if not _applies(it):
            continue
        s = status_of(it, today, lead)
        if s["status"] in ("due_soon", "overdue"):
            out.append({**it, **s})
    return out


def plan_workapproval(cal: dict, today: date = None) -> dict:
    """기한 도래분 → 업무·결재 배 생성 '계획' 산출.
    gate.auto_workapproval=False면 dry_run=True로 계획만 반환(SSOT 무변경)."""
    gate = cal.get("gate", {})
    live = bool(gate.get("auto_workapproval"))
    cands = due_items(cal, today)
    proposals = [{
        "title": f"[정기점검] {it['name']} — {it['dept']} · {it['cycle']}",
        "dept": it["dept"], "next_due": it.get("next_due", ""),
        "dday": it["dday"], "legal_basis": it.get("legal_basis", ""),
        "source": "schedule_ssot", "item_id": it["id"],
    } for it in cands]
    return {"dry_run": not live, "count": len(proposals), "proposals": proposals}


def summarize(cal: dict, dept: str = None, today: date = None) -> dict:
    today = today or _kst_today()
    lead = cal.get("gate", {}).get("lead_days", 30)
    items = [it for it in cal.get("items", [])
             if (not dept or dept == "전체" or it.get("dept") == dept) and _applies(it)]
    c = {"overdue": 0, "due_soon": 0, "scheduled": 0, "tbd": 0, "total": len(items)}
    for it in items:
        c[status_of(it, today, lead)["status"]] += 1
    return c


if __name__ == "__main__":
    cal = load()
    errs = validate(cal)
    print("검증:", "통과 ✓" if not errs else errs)
    print("요약(전체):", summarize(cal))
    plan = plan_workapproval(cal)
    print(f"업무·결재 연동: dry_run={plan['dry_run']} · 도래 {plan['count']}건 "
          f"(gate.auto_workapproval={cal['gate']['auto_workapproval']})")
    for p in plan["proposals"]:
        print("  →", p["title"], f"(D-{p['dday']})" if p["dday"] is not None else "")

    # 작업 현황 로그(best-effort) — 실행 1회당 선별 결과 요약 1줄
    worklog_log(
        "coo", "일정",
        f"전사 일정 기한 도래 선별 — 임박·초과 {plan['count']}건 확인",
        result=("warn" if errs else "ok"),
        detail=("; ".join(errs[:3]) if errs else f"검증 통과 · 등록 {summarize(cal)['total']}건 대상"),
        ref="schedule_ssot",
    )
