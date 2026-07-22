#!/usr/bin/env python3
"""월간운영계획 내부내용 자동반영 엔진 (monthly_ops_sync.py · 배9678)

목표: objective마다 연결된 '실무·업무 SSOT' 소스에서 진척을 자동으로 당겨 갱신.
정본=status/monthly_ops_plan.json · 페이지=월간운영계획.html(렌더만).
설계=docs/superpowers/specs/2026-07-22-monthly-ops-ssot-sync-design.md

소스(objective.sync.source):
  · metric_live : home_kpi GAS 실시간 지표(매출 등) → metric.current
  · queue       : status/_queue.json 배 → rule(avg_progress·status_map·count_done)
  · todo_ssot   : 업무현황 SSOT(GAS todo_list) 실무 항목 → (미연동·정직 표기)
  · manual/없음 : 손 안 댐(현행 수동 값 보존)

정직(L05): 소스 없음/조회 실패 = 값 무변경 + '미연동' 표기. 가짜 % 금지.
게이트: 환경변수 MONTHLY_SYNC_APPLY=1 이고 --apply 일 때만 실제 쓰기·커밋.
기본 = 드라이런(무엇이 바뀔지 표만 출력, 파일 무변경).

사용법:
  python scripts/monthly_ops_sync.py                 # 드라이런(당월)
  python scripts/monthly_ops_sync.py --month 2026-07 # 특정월 드라이런
  MONTHLY_SYNC_APPLY=1 python scripts/monthly_ops_sync.py --apply   # 라이브(게이트)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
PLAN_FILE = BASE_DIR / "status" / "monthly_ops_plan.json"
QUEUE_FILE = BASE_DIR / "status" / "_queue.json"

HOME_KPI_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)

GATE = os.environ.get("MONTHLY_SYNC_APPLY", "0").strip() == "1"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


# ── 소스 로더 ──────────────────────────────
def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def fetch_home_kpi() -> dict | None:
    try:
        req = urllib.request.Request(HOME_KPI_URL + "?action=home_kpi")
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data if isinstance(data, dict) and data.get("ok") else None
    except Exception as e:
        print(f"[WARN] home_kpi 조회 실패: {type(e).__name__}: {e}")
        return None


def dig(d: dict, dotted: str):
    """'sales.month' → d['sales']['month']. 없으면 None."""
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def queue_ships_by_ref(refs: list) -> list:
    """_queue.json에서 task_id 또는 ship_no가 refs에 든 배들."""
    try:
        q = load_json(QUEUE_FILE)
    except Exception:
        return []
    rset = {str(r) for r in refs}
    out = []
    for s in q if isinstance(q, list) else []:
        if str(s.get("task_id")) in rset or str(s.get("ship_no")) in rset:
            out.append(s)
    return out


# ── 업무현황 SSOT(todo_list · GAS 공용 웹앱) ──
TODO_URL = HOME_KPI_URL  # todo_list·home_kpi 동일 GAS 웹앱
_TODO_CACHE: list | None = None


def fetch_todo() -> list:
    """업무현황 SSOT 항목(진행중·완료 등). 실패 시 빈 리스트(정직)."""
    global _TODO_CACHE
    if _TODO_CACHE is not None:
        return _TODO_CACHE
    try:
        req = urllib.request.Request(TODO_URL + "?action=todo_list")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        _TODO_CACHE = data.get("data", []) if isinstance(data, dict) else []
    except Exception as e:
        print(f"[WARN] todo_list 조회 실패: {type(e).__name__}: {e}")
        _TODO_CACHE = []
    return _TODO_CACHE


def todo_by_ref(refs: list) -> list:
    rset = {str(r) for r in refs}
    return [t for t in fetch_todo() if str(t.get("id")) in rset]


# ── 채용 공고 상태(인사허브 GAS · public-job-status) ──
RECRUIT_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyyXrdM7nSXKPG3Dy8wI6_3AI1spZs24d-uHTzQZlsqzoRXKkFbSFnX-hr42D3ScQSSHQ/exec"
)
_JOBS_CACHE: list | None = None


def fetch_jobs() -> list:
    """라이브 채용 공고(공개 상태 open/closed). 실패 시 빈 리스트(정직)."""
    global _JOBS_CACHE
    if _JOBS_CACHE is not None:
        return _JOBS_CACHE
    try:
        body = json.dumps({"action": "public-job-status"}).encode("utf-8")
        req = urllib.request.Request(
            RECRUIT_URL, data=body,
            headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        _JOBS_CACHE = data.get("jobs", []) if isinstance(data, dict) and data.get("ok") else []
    except Exception as e:
        print(f"[WARN] 채용 상태 조회 실패: {type(e).__name__}: {e}")
        _JOBS_CACHE = []
    return _JOBS_CACHE


def jobs_by_ref(refs: list) -> list:
    """공고 position에 ref 문자열이 든 공고 → {상태: 완료/진행중}로 정규화(closed→완료)."""
    out = []
    for j in fetch_jobs():
        pos = str(j.get("position", ""))
        if any(str(rf) in pos for rf in refs):
            out.append({"상태": "완료" if j.get("closed") else "진행중",
                        "position": pos, "closed": bool(j.get("closed"))})
    return out


# ── 규칙 계산 ──────────────────────────────
_STATUS_MAP = {
    "DONE": 100, "IN_PROGRESS": 50, "PENDING": 0, "STANDBY": 0,
    "완료": 100, "진행중": 50, "이월": 50, "보류": 0, "계획": 0,
}


def _stat(item: dict) -> str:
    """배(status) 또는 실무항목(상태) 공통 상태 읽기."""
    return str(item.get("status") or item.get("상태") or "")


def apply_rule(rule: str, items: list) -> int | None:
    if not items:
        return None
    if rule == "count_done":
        done = sum(1 for s in items if _stat(s) in ("DONE", "완료"))
        return round(done / len(items) * 100)
    if rule == "status_map":
        vals = [_STATUS_MAP.get(_stat(s), 0) for s in items]
        return round(sum(vals) / len(vals))
    if rule == "avg_progress":
        vals = [s["progress"] for s in items if isinstance(s.get("progress"), (int, float))]
        return round(sum(vals) / len(vals)) if vals else None
    return None


# ── 엔진 ──────────────────────────────────
def resolve(obj: dict, kpi: dict | None) -> dict:
    """objective 하나에 대해 자동값을 계산. 반환=판정 dict(쓰지는 않음)."""
    sync = obj.get("sync")
    title = str(obj.get("title", ""))[:34]
    if not isinstance(sync, dict) or sync.get("source") in (None, "manual"):
        return {"title": title, "verdict": "MANUAL", "detail": "수동 유지(소스 없음)"}

    src = sync.get("source")
    if src == "metric_live":
        if kpi is None:
            return {"title": title, "verdict": "미연동", "detail": "home_kpi 조회 실패"}
        val = dig(kpi, str(sync.get("ref", "")))
        if not isinstance(val, (int, float)):
            return {"title": title, "verdict": "미연동", "detail": f"지표 없음({sync.get('ref')})"}
        cur = (obj.get("metric") or {}).get("current")
        return {"title": title, "verdict": "AUTO", "field": "metric.current",
                "old": cur, "new": int(val), "src": f"metric_live:{sync.get('ref')}"}

    if src == "queue":
        refs = sync.get("ref") or []
        ships = queue_ships_by_ref(refs if isinstance(refs, list) else [refs])
        val = apply_rule(str(sync.get("rule", "avg_progress")), ships)
        if val is None:
            return {"title": title, "verdict": "미연동", "detail": f"연결 배 없음({refs})"}
        return {"title": title, "verdict": "AUTO", "field": "progress",
                "old": obj.get("progress"), "new": val,
                "src": f"queue:{sync.get('rule')}({len(ships)}배)"}

    if src == "todo_ssot":
        refs = sync.get("ref") or []
        items = todo_by_ref(refs if isinstance(refs, list) else [refs])
        val = apply_rule(str(sync.get("rule", "count_done")), items)
        if val is None:
            return {"title": title, "verdict": "미연동", "detail": f"연결 실무항목 없음({refs})"}
        return {"title": title, "verdict": "AUTO", "field": "progress",
                "old": obj.get("progress"), "new": val,
                "src": f"todo_ssot:{sync.get('rule')}({len(items)}건)"}

    if src == "job_status":
        refs = sync.get("ref") or []
        jobs = jobs_by_ref(refs if isinstance(refs, list) else [refs])
        val = apply_rule(str(sync.get("rule", "status_map")), jobs)
        if val is None:
            return {"title": title, "verdict": "미연동", "detail": f"연결 공고 없음({refs})"}
        closed = sum(1 for j in jobs if j["closed"])
        return {"title": title, "verdict": "AUTO", "field": "progress",
                "old": obj.get("progress"), "new": val,
                "src": f"job_status:{closed}/{len(jobs)}마감"}

    return {"title": title, "verdict": "미연동", "detail": f"알 수 없는 source={src}"}


def write_back(obj: dict, v: dict) -> None:
    """게이트 ON일 때만 반영 — ★자문(advisory) 전용: progress(사람 소유) 미변경.
    자동값은 sync.auto_value·last_auto 에만 기록 → 페이지가 '🔄 자동 N%' 배지로 병기.
    수기 진실 보존 최우선·드리프트 0(GM 2026-07-22): 자동이 사람 PIN 편집값을 덮지 않는다.
    (구현 이전 버전이 status_map 평탄값 50으로 '계획 0%' 목표를 '50%'로 덮어 상태 모순
     발생 → 자문 전용으로 정정. 사람 progress ↔ 자동 auto_value 를 페이지가 나란히 노출.)
    ★INC-001: 매출·지출 등 지표값(metric.current·metric_live)은 이 파일에 저장 금지."""
    if v.get("field") != "progress":
        return  # metric_live(매출 등)는 미저장·라이브 표시 전용(INC-001)
    s = obj.setdefault("sync", {})
    s["last_auto"] = now_iso()
    s["auto_value"] = v["new"]
    # obj["progress"] 는 사람(시우 PIN 검수) 소유 — 자동 미개입. 페이지 배지로 auto_value 병기.


def run(month: str | None, apply: bool) -> None:
    plan = load_json(PLAN_FILE)
    if not month:
        month = datetime.now().strftime("%Y-%m")
    objs = plan.get("months", {}).get(month, {}).get("objectives", []) or []

    live = apply and GATE
    print(f"[월간 자동반영] {month} · 목표 {len(objs)}건 · "
          f"{'라이브 반영(게이트 ON)' if live else '드라이런(값 무변경)'}")
    if apply and not GATE:
        print("[가드] --apply 지만 MONTHLY_SYNC_APPLY=1 아님 → 드라이런으로 강등")

    kpi = fetch_home_kpi() if any(
        isinstance(o.get("sync"), dict) and o["sync"].get("source") == "metric_live" for o in objs
    ) else None

    n_auto = n_manual = n_gap = changed = 0
    print(f"\n{'상태':<6} {'목표':<36} 내용")
    print("─" * 72)
    for o in objs:
        v = resolve(o, kpi)
        vd = v["verdict"]
        if vd == "AUTO":
            n_auto += 1
            prior_av = (o.get("sync") or {}).get("auto_value")
            delta = f"{v['field']} 수기 {v['old']} · 자동 {v['new']}  [{v['src']}]"
            mark = "🔄자동"
            # 저장 트리거 = 자동값이 직전 기록과 달라졌을 때만(사람 progress 덮지 않음).
            if v.get("field") == "progress" and prior_av != v["new"]:
                changed += 1
            if live:
                write_back(o, v)
            print(f"{mark:<6} {v['title']:<36} {delta}")
        elif vd == "MANUAL":
            n_manual += 1
            print(f"{'✋수동':<6} {v['title']:<36} {v['detail']}")
        else:
            n_gap += 1
            print(f"{'⚠️미연동':<6} {v['title']:<36} {v['detail']}")
    print("─" * 72)
    print(f"요약: 🔄자동 {n_auto}(변경 {changed}) · ✋수동 {n_manual} · ⚠️미연동 {n_gap}")

    if live and changed:
        PLAN_FILE.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[반영] {PLAN_FILE.name} 저장 완료 — 커밋은 호출측/워처.")
    elif live:
        print("[반영] 변경 없음 — 저장 생략.")
    else:
        print("[드라이런] 파일 무변경. 라이브=MONTHLY_SYNC_APPLY=1 + --apply")


def main() -> None:
    ap = argparse.ArgumentParser(description="월간운영계획 자동반영 엔진")
    ap.add_argument("--month", help="YYYY-MM (기본=당월)")
    ap.add_argument("--apply", action="store_true", help="라이브 반영(게이트 동반 필요)")
    a = ap.parse_args()
    run(a.month, a.apply)


if __name__ == "__main__":
    main()
