# -*- coding: utf-8 -*-
"""coo_north_star.py — 시우(COO) 궁극 목표 「무인 운영 시스템 완성」 진척률 (GM 결정 2026-09-19 13:4x).

100% 기준 = ①4축 자동화 ②GM 개입 0 ③현장 KPI 달성 — 셋을 통합(단순 평균, 0~100 정수).
범위 = 웰페리온만. 새 원장 파일을 만들지 않는다 — 기존 산출물(module_registry·worklog·
check_incomplete_ledger·reception_watch·업무&결재 SSOT)만 읽는다.

① 자동화(4축) — 점검·결재·접수 3축은 module_registry.json 의 coo 모듈이 enabled 이고
   status/heartbeats/<id>.json 이 26시간 안에 갱신됐으면 그 축 1. SOP 축은 담당 모듈이
   등록부에 없어(2026-09-19 실측) 항상 0 — 사유를 같이 낸다. 점수 = 살아있는 축/4×100.
② GM 개입 — worklog.jsonl 에서 어제(KST) role=coo · area∈GM_AREAS · result=warn 줄 수
   (hangro_board._gm_answered_yesterday 와 같은 판정에 role 필터만 더함 — 그 함수엔
   role 인자가 없어 그대로 재사용할 수 없었다). 기준선 = 같은 판정으로 2026-09-15 를
   재도 0건(실측) — 기준선을 못 세워 고정값 20 을 쓴다(주석 · 실측되면 이 상수를 지운다).
   점수 = max(0, 1 - 어제/기준선)×100.
③ 현장 KPI 세 항목 평균(못 읽은 항목은 평균에서 빼고 "못읽음" — 0 위장 금지):
   - 지원부 점검 제출률(최근 7일 · ssot/closed_days.json 휴관일 제외) — 원천 =
     status/check_incomplete_ledger.json 의 detail(성별×회차 슬롯 t>0 이 "예정",
     sub 비어있지 않음이 "제출" — support_check_summary.record_check_detail 이 쓰는
     그 필드를 그대로 읽는다). recurring_check_causes(window=7) 과 같은 7일 창 · 같은
     closed_day 배제(coo_registry._closed_day)를 재사용.
   - 종합접수처 3일 넘은 미처리 — status/reception_watch.json["overdue_3d"](이미 계산돼
     있음 · 실제 산식은 report_stream_2b_reception.py:_write_reception_watch — GM 지시문이
     send_ops_digest.py 를 가리켰지만 그 파일엔 이 판정이 없다, 계산이 사는 곳을 그대로 읽는다).
   - 결재 대기 3일 넘은 건수 — rep_approval_relay.py 에는 결재대기 "나이" 판정이 없다
     (그 파일은 알림·중복방지만 한다). pending 판정은 coo_registry.fetch_workapproval_status
     의 필터(결재상태/결재요청 있음·결재완료 아님·반려 아님)를 그대로 쓰고, 나이는 각 행의
     "생성일"(KST)로 잰다 — 결재요청일 칸이 시트에 따로 없어 생성일을 대리 지표로 쓴다
     (주석으로 남김 · 더 정확한 칸이 생기면 교체).

출력: 기본 = 한 줄. --json = 세부값 전부. --selfcheck = 공식·못읽음 처리 오프라인 검증.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

KST = timezone(timedelta(hours=9))
UTC = timezone.utc

MODULE_REGISTRY_PATH = REPO_ROOT / "status" / "module_registry.json"
WORKLOG_PATH = REPO_ROOT / "status" / "worklog.jsonl"
CHECK_LEDGER_PATH = REPO_ROOT / "status" / "check_incomplete_ledger.json"
RECEPTION_WATCH_PATH = REPO_ROOT / "status" / "reception_watch.json"

# 2026-09-15 실측 0건이라 기준선을 못 세웠다(coo 가 그날 GM 접수 줄이 없었음) — 실측이
# 쌓여 0 아닌 기준선이 나오면 이 고정값을 지우고 실측값을 쓴다.
GM_INTERVENTION_FIXED_BASELINE = 20
HEARTBEAT_FRESH_HOURS = 26

AUTOMATION_AXES = {"점검": "coo-check-status", "결재": "coo-work-approval", "접수": "coo-reception"}
SOP_REASON = "SOP 자동화 모듈 없음"


# ── 공통 소스 로더 (실패=None, 재사용 우선순위: 있는 로더를 부르고 없으면 파일 직독) ──

def _load_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _kst_today_str(now: datetime | None = None) -> str:
    return (now or datetime.now(KST)).astimezone(KST).strftime("%Y-%m-%d")


def load_module_registry() -> dict:
    try:
        import module_registry  # noqa: PLC0415
        return module_registry.load_registry()
    except Exception:
        return _load_json(MODULE_REGISTRY_PATH) or {"modules": []}


def load_heartbeat(module_id: str) -> dict | None:
    try:
        import module_heartbeat  # noqa: PLC0415
        return module_heartbeat.last_heartbeat(module_id)
    except Exception:
        return None


# ── ① 자동화 4축 ──

def _heartbeat_fresh(hb: dict | None, now: datetime, max_hours: int = HEARTBEAT_FRESH_HOURS) -> bool:
    if not hb or not hb.get("generated_at"):
        return False
    try:
        ts = datetime.strptime(hb["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except Exception:
        return False
    return (now.astimezone(UTC) - ts) <= timedelta(hours=max_hours)


def automation_score(modules_by_id: dict, heartbeats: dict, now: datetime | None = None) -> dict:
    """modules_by_id={id: module dict}, heartbeats={id: last_heartbeat dict|None}."""
    now = now or datetime.now(UTC)
    detail = {}
    alive = 0
    for name, mid in AUTOMATION_AXES.items():
        mod = modules_by_id.get(mid)
        ok = bool(mod and mod.get("enabled")) and _heartbeat_fresh(heartbeats.get(mid), now)
        detail[name] = ok
        alive += int(ok)
    detail["SOP"] = False
    return {"score": round(alive / 4 * 100), "alive": alive, "detail": detail, "sop_reason": SOP_REASON}


# ── ② GM 개입 ──

def _iter_worklog_rows(path: Path = WORKLOG_PATH):
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if '"result": "warn"' not in line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return


def coo_gm_answered(day: str, rows=None) -> int:
    """어제(day) role=coo 인 GM 접수(warn) 줄 수 — hangro_board._gm_answered_yesterday 판정에
    role 필터만 더한 것(그 함수는 role 인자가 없어 그대로 재사용 불가)."""
    try:
        from worklog import GM_AREAS  # noqa: PLC0415 — 정본=worklog.py(값 복사 금지)
    except Exception:
        GM_AREAS = ("GM요청", "GM지시")
    rows = rows if rows is not None else _iter_worklog_rows()
    n = 0
    for d in rows:
        if d.get("area") not in GM_AREAS:
            continue
        if d.get("role") != "coo":
            continue
        if str(d.get("ts") or "")[:10] != day:
            continue
        n += 1
    return n


def gm_intervention_score(yesterday_n: int, baseline_n: int) -> dict:
    baseline = baseline_n if baseline_n > 0 else GM_INTERVENTION_FIXED_BASELINE
    score = round(max(0, 1 - yesterday_n / baseline) * 100)
    return {"score": score, "yesterday": yesterday_n, "baseline": baseline,
            "baseline_measured": baseline_n > 0}


# ── ③ 현장 KPI ──

def _default_closed_day(day: str) -> bool:
    try:
        from coo_registry import _closed_day  # noqa: PLC0415
        return bool(_closed_day(day))
    except Exception:
        return False


def support_submit_rate_7d(ledger: dict, today: str, closed_fn=None) -> float | None:
    """지원부 점검 제출률(%, 0~100) 최근 7일 — status/check_incomplete_ledger.json 의
    detail(t>0=예정 슬롯, sub 비어있지 않음=제출)을 읽는다. 원천에 그 날 detail 이 하나도
    없으면(예정 슬롯 0건) None(못읽음) — 0%로 위장하지 않는다."""
    closed_fn = closed_fn or _default_closed_day
    base = datetime.strptime(today, "%Y-%m-%d")
    days = [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 8)]
    days = [d for d in days if not closed_fn(d)]
    submitted = total = 0
    for d in days:
        det = (ledger.get(d) or {}).get("detail") or {}
        for g in ("m", "f"):
            for _sh, cell in (det.get(g) or {}).items():
                if not isinstance(cell, dict) or (cell.get("t") or 0) <= 0:
                    continue
                total += 1
                if str(cell.get("sub") or "").strip():
                    submitted += 1
    if total == 0:
        return None
    return round(submitted / total * 100, 1)


def reception_overdue_3d(watch: dict | None) -> int | None:
    if not isinstance(watch, dict):
        return None
    v = watch.get("overdue_3d")
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def approval_overdue_3d(rows: list | None, today: str) -> int | None:
    """rows=None → 조회 실패(못읽음). rows=[] → 실제로 0건(실측). pending 필터는
    coo_registry.fetch_workapproval_status 와 동일 — 나이는 「생성일」(결재요청일 칸이
    없어 대리 지표로 씀)."""
    if rows is None:
        return None
    try:
        from rep_approval_relay import _kst_day  # noqa: PLC0415
    except Exception:
        def _kst_day(v):
            return str(v or "")[:10]
    n = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        status = r.get("결재상태") or ""
        if "반려" in status or status == "결재완료":
            continue
        if not (r.get("결재상태") or r.get("결재요청")):
            continue
        created = _kst_day(r.get("생성일"))
        if not created:
            continue
        try:
            age = (date.fromisoformat(today) - date.fromisoformat(created)).days
        except Exception:
            continue
        if age >= 3:
            n += 1
    return n


def _rate_to_score(pct: float | None, target: float = 90.0) -> float | None:
    if pct is None:
        return None
    return min(100.0, pct / target * 100.0)


def _overdue_to_score(n: int | None) -> float | None:
    if n is None:
        return None
    return max(0.0, 100.0 - 10.0 * n)


def field_score(support_pct: float | None, reception_n: int | None, approval_n: int | None) -> dict:
    sub = {
        "지원부_제출률_7일": support_pct,
        "종합접수처_3일초과": reception_n,
        "결재대기_3일초과": approval_n,
    }
    scores = {
        "지원부_제출률_7일": _rate_to_score(support_pct),
        "종합접수처_3일초과": _overdue_to_score(reception_n),
        "결재대기_3일초과": _overdue_to_score(approval_n),
    }
    vals = [v for v in scores.values() if v is not None]
    avg = round(sum(vals) / len(vals), 1) if vals else None
    return {"score": avg, "raw": sub, "sub_scores": scores}


# ── 통합 ──

def composite(auto_score: float | None, gm_score: float | None, field_score_v: float | None) -> int | None:
    vals = [v for v in (auto_score, gm_score, field_score_v) if v is not None]
    return round(sum(vals) / len(vals)) if vals else None


def _fmt(v) -> str:
    return "못읽음" if v is None else f"{round(v)}%"


def compute(now: datetime | None = None) -> dict:
    """실측 조회 — 각 원천이 못 읽히면 그 항목만 못읽음으로 빠진다(전체는 안 죽음)."""
    now_kst = now or datetime.now(KST)
    today = _kst_today_str(now_kst)
    yday = (now_kst.date() - timedelta(days=1)).isoformat()
    base15 = "2026-09-15"

    registry = load_module_registry()
    modules_by_id = {m.get("id"): m for m in registry.get("modules", []) if isinstance(m, dict)}
    heartbeats = {mid: load_heartbeat(mid) for mid in AUTOMATION_AXES.values()}
    auto = automation_score(modules_by_id, heartbeats, now_kst)

    yday_n = coo_gm_answered(yday)
    base_n = coo_gm_answered(base15)
    gm = gm_intervention_score(yday_n, base_n)

    ledger = _load_json(CHECK_LEDGER_PATH) or {}
    support_pct = support_submit_rate_7d(ledger, today)

    watch = _load_json(RECEPTION_WATCH_PATH)
    reception_n = reception_overdue_3d(watch)

    try:
        from rep_approval_relay import fetch_rows  # noqa: PLC0415
        approval_rows = fetch_rows()
    except Exception:
        approval_rows = None
    approval_n = approval_overdue_3d(approval_rows, today)

    field = field_score(support_pct, reception_n, approval_n)
    total = composite(auto["score"], gm["score"], field["score"])

    return {"total": total, "automation": auto, "gm_intervention": gm, "field": field,
            "today": today, "yesterday": yday}


def line(result: dict | None = None) -> str:
    r = result or compute()
    return (f"🧭 시우 궁극 목표 진척 {_fmt(r['total'])} "
            f"(자동화 {_fmt(r['automation']['score'])} · "
            f"GM 개입 {_fmt(r['gm_intervention']['score'])} · "
            f"현장 {_fmt(r['field']['score'])})")


# ── --selfcheck ──

def _selfcheck() -> None:
    now = datetime(2026, 9, 19, 1, 0, tzinfo=UTC)  # KST 10:00

    # ① 자동화 — 3축 중 2축만 살아있음(하나는 heartbeat 낡음) + SOP 는 항상 0/사유 있음
    modules = {"coo-check-status": {"enabled": True}, "coo-work-approval": {"enabled": True},
               "coo-reception": {"enabled": False}}
    heartbeats = {
        "coo-check-status": {"generated_at": "2026-09-19T00:00:00Z"},   # 1시간 전 — 신선
        "coo-work-approval": {"generated_at": "2026-09-16T00:00:00Z"},  # 3일 전 — 낡음
        "coo-reception": {"generated_at": "2026-09-19T00:00:00Z"},      # enabled=False 라 무효
    }
    auto = automation_score(modules, heartbeats, now)
    assert auto["alive"] == 1, auto           # check-status 만 살아있음
    assert auto["score"] == 25, auto          # 1/4*100
    assert auto["detail"]["SOP"] is False and auto["sop_reason"] == SOP_REASON, auto

    # ② GM 개입 — 기준선 미실측(0) → 고정값 20, 어제 4건 → 80%
    gm = gm_intervention_score(4, 0)
    assert gm["baseline"] == GM_INTERVENTION_FIXED_BASELINE and not gm["baseline_measured"], gm
    assert gm["score"] == 80, gm              # (1-4/20)*100
    gm0 = gm_intervention_score(0, 20)
    assert gm0["score"] == 100, gm0

    # ③ 현장 — 못읽음(None) 하나는 평균에서 빠지고, 0 은 100점으로 정직히 반영(0 위장 금지 대칭성)
    f_missing = field_score(None, 0, 2)
    assert f_missing["sub_scores"]["지원부_제출률_7일"] is None, f_missing
    assert f_missing["score"] == round((100 + 80) / 2, 1), f_missing   # 0건=100 · 2건=80 평균
    f_all_missing = field_score(None, None, None)
    assert f_all_missing["score"] is None, f_all_missing

    # support_submit_rate_7d — 예정 슬롯 0건인 날은 못읽음(총 0), 있으면 제출/예정
    ledger = {
        "2026-09-18": {"detail": {"m": {"am": {"t": 26, "sub": ""}, "pm": {"t": 14, "sub": "박남일"}}, "f": {}}},
    }
    rate = support_submit_rate_7d(ledger, "2026-09-19", closed_fn=lambda d: d != "2026-09-18")
    assert rate == 50.0, rate   # 2 슬롯 중 1 제출
    rate_none = support_submit_rate_7d({}, "2026-09-19", closed_fn=lambda d: True)  # 전부 휴관 처리
    assert rate_none is None, rate_none

    # reception_overdue_3d / approval_overdue_3d
    assert reception_overdue_3d({"overdue_3d": 7}) == 7
    assert reception_overdue_3d(None) is None
    assert reception_overdue_3d({"overdue_3d": "x"}) is None
    today = "2026-09-19"
    rows = [
        {"결재상태": "", "결재요청": "GM", "생성일": "2026-09-15T00:00:00Z"},   # 4일 — 초과
        {"결재상태": "", "결재요청": "GM", "생성일": "2026-09-18T00:00:00Z"},   # 1일 — 아직
        {"결재상태": "반려", "결재요청": "GM", "생성일": "2026-09-01T00:00:00Z"},  # 반려 제외
        {"결재상태": "결재완료", "결재요청": "GM", "생성일": "2026-09-01T00:00:00Z"},  # 완료 제외
    ]
    assert approval_overdue_3d(rows, today) == 1, approval_overdue_3d(rows, today)
    assert approval_overdue_3d(None, today) is None

    # 통합 평균 + 못읽음 표시
    assert composite(50, 80, None) == 65
    assert composite(None, None, None) is None
    r = {"total": 65, "automation": {"score": 50}, "gm_intervention": {"score": 80},
         "field": {"score": None}}
    assert line(r) == "🧭 시우 궁극 목표 진척 65% (자동화 50% · GM 개입 80% · 현장 못읽음)", line(r)

    print("[selfcheck] coo_north_star OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return 0
    result = compute()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(line(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
