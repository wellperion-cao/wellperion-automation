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

rule=status_map 은 진척률(progress)을 절대 쓰지 않는다(GM 확정 2026-07-24) — '진행중'류
상태를 숫자 하나로 평균 내면 실무 실제와 무관하게 평탄값(예 50)이 나와, 사람이 실측하고
넣은 진척률(예 70·45·40·15)을 통째로 지워버린다. 대신 관찰한 상태 분포만
objective.sync_observed 에 사실대로 기록한다. count_done·avg_progress 등 실측 규칙은
그대로 progress 를 갱신(자문 auto_value 기록)한다 — 실제 데이터라 덮어써도 의미가 있다.

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
import time
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

_SCRIPTS_DIR_FOR_WORKLOG = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR_FOR_WORKLOG not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR_FOR_WORKLOG)

try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 반영 흐름 무영향
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False

try:  # 안전 커밋터(배9820) — 임시 인덱스+CAS. 커밋은 반드시 이 경유(맨손 git 금지, 저장소 규칙)
    from safe_commit import safe_commit as _safe_commit
except Exception:
    _safe_commit = None

INDEX_LOCK_FILE = BASE_DIR / ".git" / "index.lock"
_COMMIT_LOCK_RETRY_SEC = 5
_COMMIT_LOCK_RETRIES = 12  # 5초 × 12 ≈ 1분(GM 확정 2026-07-24)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


# ── 소스 로더 ──────────────────────────────
def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _get_json_retry(url: str, timeout: int, retries: int = 2) -> dict | None:
    """GET → JSON. GAS 콜드스타트 등 일시 타임아웃은 백오프(2s·4s) 재시도
    (scripts/kpi_collector.py._http_get_json 과 동일 패턴 — 07:00 예약 실행 1회
    타임아웃으로 그날치 실측이 통째로 '측정실패'로 떨어지는 것 방지)."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    print(f"[WARN] {url.split('?')[0]} 조회 실패({retries + 1}회 시도): "
          f"{type(last_exc).__name__}: {last_exc}")
    return None


def fetch_home_kpi() -> dict | None:
    data = _get_json_retry(HOME_KPI_URL + "?action=home_kpi", timeout=15)
    return data if isinstance(data, dict) and data.get("ok") else None


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
    data = _get_json_retry(TODO_URL + "?action=todo_list", timeout=30)
    _TODO_CACHE = data.get("data", []) if isinstance(data, dict) else []
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
    "완료": 100, "진행중": 50, "이월": 30, "보류": 0, "계획": 0,
}

# status_map 관찰 기록용 — 배(영문 enum)·실무항목(한글 상태) 어느 쪽이든 4상태로 묶어
# '사실'만 기록한다(GM 확정 2026-07-24). _STATUS_MAP 의 평탄 숫자와 달리 진척률에는 쓰지 않음.
_STATUS_LABEL = {
    "DONE": "완료", "완료": "완료",
    "IN_PROGRESS": "진행중", "진행중": "진행중", "이월": "진행중",
    "PENDING": "보류", "STANDBY": "보류", "BLOCKED": "보류", "보류": "보류",
    "계획": "계획",
}
_STATUS_LABEL_ORDER = ["진행중", "완료", "보류", "계획"]


def _stat(item: dict) -> str:
    """배(status) 또는 실무항목(상태) 공통 상태 읽기."""
    return str(item.get("status") or item.get("상태") or "")


def observed_state(items: list) -> dict:
    """status_map 소스의 실측 상태 분포(정직 기록 — 지어내기 금지). 0건 상태는 생략."""
    counts: dict[str, int] = {}
    for it in items:
        raw = _stat(it)
        label = _STATUS_LABEL.get(raw, raw or "미상")
        counts[label] = counts.get(label, 0) + 1
    out = dict(counts)
    out["총"] = len(items)
    out["at"] = datetime.now().strftime("%Y-%m-%d")
    return out


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
def _observe_verdict(title: str, obj: dict, items: list, avg_val: int, src_label: str) -> dict:
    """status_map 전용 판정(GM 확정 2026-07-24) — progress 는 절대 안 쓰고 관찰 상태만 기록.
    avg_val=_STATUS_MAP 평탄 평균(참고용 sync.auto_value 에만 보존 — progress 미반영)."""
    observed = observed_state(items)
    old = obj.get("progress")
    ordered = [f"{k} {observed[k]}" for k in _STATUS_LABEL_ORDER if k in observed]
    extra = [f"{k} {v}" for k, v in observed.items()
             if k not in _STATUS_LABEL_ORDER and k not in ("총", "at")]
    old_disp = old if old is not None else "미설정"
    detail = f"{' · '.join(ordered + extra)} (진척률은 사람 값 {old_disp} 유지)"
    return {"title": title, "verdict": "OBSERVE", "old": old, "new": avg_val,
            "observed": observed, "src": src_label, "detail": detail}


# ── 정직 딱지(honesty) ─────────────────────
# GM 지시 2026-07-24: "숫자마다 정직 딱지를 붙인다" — 딱지는 resolve() 판정 결과에서
# 그대로 도출한다(손으로 달지 않음 · 약속 L01·L05 — 손으로 달면 그게 또 거짓말이 된다).
_SRC_KIND = {
    "metric_live": "home_kpi 실시간 지표",
    "queue": "업무현황 배",
    "todo_ssot": "업무현황 SSOT",
    "job_status": "채용 공고",
}


def _src_kind(src: str) -> str:
    """sync 판정 src 라벨(예 'queue:status_map(2배)')에서 소스 종류만 한국어로."""
    key = str(src or "").split(":", 1)[0]
    return _SRC_KIND.get(key, key)


def honesty_from_verdict(v: dict) -> dict:
    """resolve() 판정 결과 v 하나에서 정직 딱지를 도출한다.
    · AUTO(metric_live·count_done·avg_progress 로 실제 값 갱신) → measured(✅ 실측)
    · OBSERVE(status_map — 상태만 관찰, 진척률은 사람 값 유지) → observed(👀 상태만)
    · MANUAL(연결 소스 없음) → manual(📝 사람값)
    · 그 외(소스는 있는데 조회 실패/연결 대상 없음 = verdict '미연동') → unmeasured(🔧 측정 실패)
    honesty_summary.자동화율 정의 = 실측(measured) ÷ 총. '상태만'(observed)은 숫자 자체는
    사람이 넣은 값이라 실측에 포함하지 않는다(부풀리기 금지 — GM 과대보고 지적 2026-07-24)."""
    verdict = v.get("verdict")
    at = datetime.now().strftime("%Y-%m-%d")
    if verdict == "AUTO":
        src = v.get("src", "")
        basis = f"{_src_kind(src)} · {src}" if src else _src_kind(src)
        return {"level": "measured", "label": "✅ 실측", "basis": basis, "at": at}
    if verdict == "OBSERVE":
        observed = v.get("observed") or {}
        parts = [f"{k} {observed[k]}건" for k in _STATUS_LABEL_ORDER if k in observed]
        basis = f"{_src_kind(v.get('src', ''))} " + (" · ".join(parts) if parts else "관찰 없음")
        return {"level": "observed", "label": "👀 상태만", "basis": basis.strip(), "at": at}
    if verdict == "MANUAL":
        return {"level": "manual", "label": "📝 사람값", "basis": "연결된 소스 없음", "at": at}
    # verdict == "미연동" — 소스는 연결돼 있는데 조회 실패/연결 대상 없음 → 조용히 감추지 않고 표기.
    return {"level": "unmeasured", "label": "🔧 측정 실패", "basis": v.get("detail", ""), "at": at}


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
        rule = str(sync.get("rule", "avg_progress"))
        val = apply_rule(rule, ships)
        if val is None:
            return {"title": title, "verdict": "미연동", "detail": f"연결 배 없음({refs})"}
        src_label = f"queue:{rule}({len(ships)}배)"
        if rule == "status_map":
            return _observe_verdict(title, obj, ships, val, src_label)
        return {"title": title, "verdict": "AUTO", "field": "progress",
                "old": obj.get("progress"), "new": val, "src": src_label}

    if src == "todo_ssot":
        refs = sync.get("ref") or []
        items = todo_by_ref(refs if isinstance(refs, list) else [refs])
        rule = str(sync.get("rule", "count_done"))
        val = apply_rule(rule, items)
        if val is None:
            return {"title": title, "verdict": "미연동", "detail": f"연결 실무항목 없음({refs})"}
        src_label = f"todo_ssot:{rule}({len(items)}건)"
        if rule == "status_map":
            return _observe_verdict(title, obj, items, val, src_label)
        return {"title": title, "verdict": "AUTO", "field": "progress",
                "old": obj.get("progress"), "new": val, "src": src_label}

    if src == "job_status":
        refs = sync.get("ref") or []
        jobs = jobs_by_ref(refs if isinstance(refs, list) else [refs])
        rule = str(sync.get("rule", "status_map"))
        val = apply_rule(rule, jobs)
        if val is None:
            return {"title": title, "verdict": "미연동", "detail": f"연결 공고 없음({refs})"}
        closed = sum(1 for j in jobs if j["closed"])
        src_label = f"job_status:{closed}/{len(jobs)}마감"
        if rule == "status_map":
            return _observe_verdict(title, obj, jobs, val, src_label)
        return {"title": title, "verdict": "AUTO", "field": "progress",
                "old": obj.get("progress"), "new": val, "src": src_label}

    return {"title": title, "verdict": "미연동", "detail": f"알 수 없는 source={src}"}


def write_back(obj: dict, v: dict) -> None:
    """게이트 ON일 때만 반영.
    ★status_map(OBSERVE 판정)은 progress(사람 소유)를 절대 안 쓴다(GM 확정 2026-07-24) —
    '진행중'류를 숫자 하나로 평균 내면 실무 실제와 무관한 평탄값이 나와 사람이 실측해
    넣은 진척률을 지워버린다. 대신 관찰한 상태 분포를 objective.sync_observed 에 사실대로
    기록한다(추정 금지). sync.auto_value·last_auto 는 참고용으로만 계속 병기(페이지 배지).
    나머지 규칙(count_done·avg_progress 등)은 기존 자문(advisory) 동작 그대로 —
    auto_value·last_auto 에만 기록하고 progress 는 미변경(2026-07-22 자문 전환 유지).
    ★INC-001: 매출·지출 등 지표값(metric.current·metric_live)은 이 파일에 저장 금지."""
    s = obj.setdefault("sync", {})
    if v.get("verdict") == "OBSERVE":
        s["last_auto"] = now_iso()
        s["auto_value"] = v["new"]  # 참고용(페이지 배지)일 뿐 progress 아님
        obj["sync_observed"] = v["observed"]
        return
    if v.get("field") != "progress":
        return  # metric_live(매출 등)는 미저장·라이브 표시 전용(INC-001)
    s["last_auto"] = now_iso()
    s["auto_value"] = v["new"]
    # obj["progress"] 는 사람(시우 PIN 검수) 소유 — 자동 미개입. 페이지 배지로 auto_value 병기.


def commit_plan(month: str, changed: int, n_observe_changed: int) -> None:
    """status/monthly_ops_plan.json 반영분을 safe_commit 경유로 커밋한다(저장소 규칙 —
    맨손 git add/commit 금지). .git/index.lock 이 있으면 지우지 않고 5초 간격 최대 12회
    (약 1분) 대기 후 재시도한다 — 다른 세션이 실제 커밋 중일 수 있어서다. 그래도 안 풀리면
    조용히 넘기지 않고 로그에 눈에 띄게 남긴다(GM 2026-07-24: 07:00 실행이 락 때문에 커밋을
    건너뛰고 그날 반영분이 사라졌다 — 이전엔 [SKIP] 한 줄뿐이라 아무도 몰랐다)."""
    if _safe_commit is None:
        print("[FAIL] 커밋 실패 — 반영분이 커밋되지 않았습니다. safe_commit 모듈 로드 실패")
        return
    for attempt in range(1, _COMMIT_LOCK_RETRIES + 1):
        if not INDEX_LOCK_FILE.exists():
            break
        print(f"[대기] .git/index.lock 존재 — 커밋 보류·재시도 {attempt}/{_COMMIT_LOCK_RETRIES}"
              f"(락 파일은 지우지 않음 — 다른 세션이 커밋 중일 수 있음)")
        time.sleep(_COMMIT_LOCK_RETRY_SEC)
    else:
        print("[FAIL] 커밋 실패 — 반영분이 커밋되지 않았습니다. 잠금 지속"
              f"(.git/index.lock 이 {_COMMIT_LOCK_RETRIES * _COMMIT_LOCK_RETRY_SEC}초 대기 후에도 존재)")
        return

    message = (f"chore(coo): 월간계획 자동반영 — {month} 진척갱신 {changed}건·"
               f"상태관찰갱신 {n_observe_changed}건 (ship9678)")
    try:
        res = _safe_commit([str(PLAN_FILE)], message, holder="monthly_ops_sync")
    except Exception as exc:
        print(f"[FAIL] 커밋 실패 — 반영분이 커밋되지 않았습니다. safe_commit 예외: "
              f"{type(exc).__name__}: {exc}")
        return
    if res.get("ok") and res.get("committed"):
        print(f"[커밋] {PLAN_FILE.name} 커밋 완료 sha={res['sha'][:9]}")
    elif res.get("ok"):
        print(f"[커밋] 변경 없음 — {res.get('reason')}")
    else:
        print(f"[FAIL] 커밋 실패 — 반영분이 커밋되지 않았습니다. {res.get('reason')}")


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

    n_auto = n_observe = n_manual = n_gap = changed = obs_changed = honesty_changed = 0
    print(f"\n{'상태':<6} {'목표':<36} 내용")
    print("─" * 72)
    for o in objs:
        v = resolve(o, kpi)
        vd = v["verdict"]
        # 정직 딱지 — verdict 와 무관하게 모든 objective 에 매긴다(honesty 없는 옛 항목도 포함).
        # 'at' 는 비교에서 제외(당일 재실행은 무변경으로 취급 · sync_observed 비교와 동일 관례).
        honesty = honesty_from_verdict(v)
        prior_honesty = {k: val for k, val in (o.get("honesty") or {}).items() if k != "at"}
        new_honesty_cmp = {k: val for k, val in honesty.items() if k != "at"}
        if prior_honesty != new_honesty_cmp:
            honesty_changed += 1
        if live:
            o["honesty"] = honesty
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
        elif vd == "OBSERVE":
            n_observe += 1
            # 관찰 상태가 직전 기록과 달라졌을 때만 '변경'으로 카운트('at' 타임스탬프는 제외).
            prior_observed = {k: val for k, val in (o.get("sync_observed") or {}).items()
                               if k != "at"}
            new_observed = {k: val for k, val in v["observed"].items() if k != "at"}
            if new_observed != prior_observed:
                obs_changed += 1
            if live:
                write_back(o, v)
            print(f"{'👀상태만':<6} {v['title']:<36} {v['detail']}  [{v['src']}]")
        elif vd == "MANUAL":
            n_manual += 1
            print(f"{'✋수동':<6} {v['title']:<36} {v['detail']}")
        else:
            n_gap += 1
            print(f"{'⚠️미연동':<6} {v['title']:<36} {v['detail']}")
    print("─" * 72)
    print(f"요약: 🔄자동 {n_auto}(변경 {changed}) · 👀상태만 {n_observe} · "
          f"✋수동 {n_manual} · ⚠️미연동 {n_gap}")

    total = len(objs)
    # 자동화율 정의(honesty_summary.자동화율) = 실측(measured=AUTO) ÷ 총. status_map 관찰(observed)은
    # 숫자는 사람 값 그대로라 분자에서 뺀다 — 부풀리기 금지(GM 과대보고 지적 2026-07-24).
    auto_rate = round(n_auto / total, 4) if total else 0.0

    if live and (changed or obs_changed or honesty_changed):
        plan["honesty_summary"] = {
            "총": total, "실측": n_auto, "상태만": n_observe,
            "사람값": n_manual, "측정실패": n_gap,
            "자동화율": auto_rate, "at": datetime.now().strftime("%Y-%m-%d"),
        }
        PLAN_FILE.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[반영] {PLAN_FILE.name} 저장 완료 — safe_commit 경유 커밋 시도.")
        commit_plan(month, changed, obs_changed)
        # 작업 현황 로그(best-effort) — dry-run 시엔 남기지 않음(실행 1회당 1줄)
        worklog_log(
            "coo", "월간계획",
            f"월간 운영계획 진척 자동 반영 — {changed}개 목표 갱신·상태관찰 {obs_changed}건 갱신·"
            f"정직딱지 {honesty_changed}건 갱신",
            result="ok",
            detail=f"{month} · 자동판정 {n_auto}건 중 변경 {changed}건 · "
                   f"상태만판정 {n_observe}건 중 관찰갱신 {obs_changed}건 · "
                   f"정직딱지 갱신 {honesty_changed}건 · 자동화율 {round(auto_rate * 100)}%",
            ref=month,
        )
    elif live:
        print("[반영] 변경 없음 — 저장 생략.")
        worklog_log(
            "coo", "월간계획", "월간 운영계획 자동 반영 실행 — 갱신된 목표 없음",
            result="warn", detail=f"{month} · 자동판정 {n_auto}건 모두 기존값과 동일", ref=month,
        )
    else:
        print("[드라이런] 파일 무변경. 라이브=MONTHLY_SYNC_APPLY=1 + --apply")

    # 정직 요약 — 드라이런·라이브 어느 쪽이든 항상 콘솔 맨 아래에 출력(GM 1단계 2026-07-24).
    print(f"정직: ✅실측 {n_auto} · 👀상태만 {n_observe} · 📝사람값 {n_manual} · "
          f"🔧측정실패 {n_gap} → 자동화율 {round(auto_rate * 100)}%")

    warn_unbacked_approvals(objs)


# ── 근거 없는 '승인' 기록 적발 (2026-07-27 GM 정정 3건 후속) ──────────────────
# 왜 있나: 2026-07-25 에 AI(시우)가 목표 3건의 note 에 "GM 결재 확정 반영 — 2026-07-24 GM 승인"
#   이라고 적었는데, 2026-07-27 GM 확인 결과 셋 다 승인 난 적이 없었다. 같은 시기 결재 브리프는
#   "아직 미결정"이라고 정확히 적고 있었는데도 이틀간 어긋난 채 남아 GM이 직접 잡아냈다.
#   승인 여부는 GM 발화가 유일한 근거인데, 그걸 확인했다는 표시가 기록에 없어 사후 구별이 불가능했다.
# 무엇을 하나: 승인을 단정하는 문구가 있는데 근거 필드(approval_evidence)가 없으면 실행할 때마다
#   경고로 띄운다. 막지는 않는다 — 사람이 손으로 쓰는 칸이라 차단하면 기록 자체를 못 남긴다.
#   대신 조용히 지나가지 못하게 한다(약속 L05·헌법 구조2 — 문서가 아니라 돌아가는 코드에 박는다).
# 근거를 남기는 법: 해당 objective 에 "approval_evidence": "2026-07-24 GM 발화 …" 를 같이 적는다.
_APPROVAL_CLAIM_WORDS = ("GM 승인", "결재 확정", "결재 종결", "GM 확정 승인")


def warn_unbacked_approvals(objs: list) -> None:
    flagged = []
    for o in objs:
        if not isinstance(o, dict):
            continue
        note = str(o.get("progress_note") or "")
        if o.get("approval_evidence"):
            continue
        # 이미 '사실 아님'으로 정정된 기록은 다시 세지 않는다(정정이 곧 처리 완료).
        hits = [w for w in _APPROVAL_CLAIM_WORDS if w in note]
        if hits and "사실 아님" not in note:
            flagged.append((str(o.get("title") or "")[:38], hits[0]))
    if not flagged:
        print("승인근거: ✅ 근거 없는 승인 기록 없음")
        return
    print(f"\n⚠️ 승인근거 없음 {len(flagged)}건 — GM 발화 확인 없이 승인을 단정한 기록일 수 있습니다.")
    for title, word in flagged:
        print(f"   · {title:<38} ('{word}')")
    print("   → 근거가 있으면 해당 목표에 approval_evidence 를 적고, 없으면 '미결정'으로 되돌리세요.")


def main() -> None:
    ap = argparse.ArgumentParser(description="월간운영계획 자동반영 엔진")
    ap.add_argument("--month", help="YYYY-MM (기본=당월)")
    ap.add_argument("--apply", action="store_true", help="라이브 반영(게이트 동반 필요)")
    a = ap.parse_args()
    run(a.month, a.apply)


if __name__ == "__main__":
    main()
