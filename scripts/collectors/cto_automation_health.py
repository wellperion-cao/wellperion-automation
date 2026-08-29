# -*- coding: utf-8 -*-
"""
cto_automation_health.py — 모듈 cto-automation-health 수집기(공유 SSOT 정합).
─────────────────────────────────────────────────────────────────────────────
등록부(module_registry.json)의 모듈 id `cto-automation-health` → id 규약으로
이 모듈명(collectors.cto_automation_health)이 해소된다.

1차 소스 = 모듈의 **선언된 data_source(status/erp_status.json)** 직독.
  erp_status.json 은 erp_status_publisher.py 가 30분 갱신하는 자동화 건강 현황
  (automation_health.summary/total/healthy/rate)을 담는다 → 실측 '측정' 꼬리표.

보강(fallback) = erp_status.json 에 필요한 값이 없을 때만:
  - integration_health.check_bridges()          → 연동 다리 [(name, ok, detail)]
  - learning_effect_meter.measure_all(dry_run=True) → 학습효과 측정 대상(무영속)
  (두 함수는 import·호출만 — 수정하지 않음. dry_run/check 는 side-effect 0.)

정직 꼬리표: 실측 = 측정 / 일부 = 부분 / 데이터 없음 = 미측정.

[2026-07-22 업그레이드·GM 지시(방4 승격) — 새 모듈/새 방/새 예약작업 생성 없이 기존
자산만 병합] 자동화현황방(방4)의 "전체 자동화 현황" 단일 다이제스트로 이 모듈을 daily
승격(등록부 notify_spec.daily=true 추가, 기존 weekly 유지)하며, 실제 운영중인 erp_status.json
(self_health_watchdog.ERP_STATUS_PATH와 동일 파일)을 읽을 때만 아래 3섹션을 병합한다:
  · 라이브·상주 프로세스   — erp_status.json systems 배열(일일 스케줄러·텔레그램 봇 등)
  · 스케줄·오늘 진행       — automation_health.items 오늘(KST) 실행분 성공/실패/대기
  · ERP 자가건강           — self_health_watchdog.build_digest() 재사용(재수집 금지).
    기존 self_health_watchdog 은 "정상=무발신"이라 GM 눈에 안 보였다 — 이 다이제스트는
    정상이어도 "이상 0건 ✅" 한 줄을 상시 노출한다(§자가건강 상시화, 배9420/9421 후속).
    13:00 telegram_health_check.bat 의 self_health_watchdog --live 별도발송은 이 병합으로
    중복이 되어 정리(주석 처리, 역롤백 표시)했다 — 소스 로직(self_health_watchdog.py)은
    수정 없이 그대로 재사용만 한다.
가짜/테스트 erp 경로(실제 운영 경로가 아님)로 collect() 를 호출하면 이 3섹션은 건드리지
않는다 — 기존 테스트(test_module_reporter.py)의 네트워크 0·결정론 계약을 보존하기 위함.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from collectors.base import make_payload  # noqa: E402
import self_health_watchdog as _self_health  # noqa: E402 — §자가건강 재사용(재수집 금지)

_LINK = "https://wellperion-cao.github.io/wellperion-automation/자율현황.html#health"
_DEFAULT_REF = "status/erp_status.json"
_KST = timezone(timedelta(hours=9))
_LIVE_OK_STATES = ("정상", "정상(건너뜀)")

# §주간 품질 회귀(delta) — 배10037 / 자기학습 승인건 prop_20260713_094621_6a0e52
_REPORT_LOG = os.path.join(_PROJECT_ROOT, "status", "module_report_log.jsonl")
_REGRESS_THRESHOLD = -0.10   # 전주 대비 성공률 하락 폭이 이 이하면 REGRESSED
_MIN_SAMPLE = 5              # 이번주 표본이 이 미만이면 판정 보류(N<5)
_TOP_N = 3                   # 텔레그램 1줄에 실을 상위 하락 모듈 수


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_ref(module):
    """모듈의 선언된 data_source.ref → 절대경로(없으면 기본 erp_status.json)."""
    ref = None
    if isinstance(module, dict):
        ds = module.get("data_source") or {}
        ref = ds.get("ref")
    ref = ref or _DEFAULT_REF
    return ref if os.path.isabs(ref) else os.path.join(_PROJECT_ROOT, ref)


def _from_erp_status(erp):
    """erp_status.json 의 automation_health 블록 → 표준 payload(없으면 None)."""
    if not isinstance(erp, dict):
        return None
    ah = erp.get("automation_health")
    if not isinstance(ah, dict) or not ah.get("total"):
        return None

    total = ah.get("total")
    healthy = ah.get("healthy")
    rate = ah.get("rate")

    metrics = [{"label": "자동화 가동", "value": f"{healthy}/{total}"}]
    if rate is not None:
        metrics.append({"label": "가동률", "value": f"{rate}%"})
    if isinstance(total, int) and isinstance(healthy, int):
        metrics.append({"label": "비정상", "value": total - healthy})

    summary = ah.get("summary") or f"자동화 {healthy}/{total} 정상"
    return make_payload(
        title="자율현황 자동화 건강",
        summary_line=summary,
        metrics=metrics,
        honesty_tag="측정",
        link=_LINK,
    )


def _from_functions():
    """보강 경로: check_bridges + measure_all(dry_run=True) 함수호출 흡수."""
    bridges = None
    bridge_err = None
    try:
        import integration_health  # noqa: PLC0415
        bridges = integration_health.check_bridges()  # list[(name, ok, detail)]
    except Exception as e:
        bridge_err = f"{type(e).__name__}: {str(e)[:80]}"

    learn_count = None
    try:
        import learning_effect_meter  # noqa: PLC0415
        # dry_run=True → learning_proposals.json 미영속(멱등·부작용 0)
        changed = learning_effect_meter.measure_all(dry_run=True)
        learn_count = len(changed) if isinstance(changed, list) else 0
    except Exception:
        learn_count = None

    metrics = []
    if bridges is not None:
        total = len(bridges)
        ok = sum(1 for b in bridges if len(b) >= 2 and b[1])
        fail = total - ok
        metrics.append({"label": "연동 다리 가동", "value": f"{ok}/{total}"})
        metrics.append({"label": "다리 실패", "value": fail})
        summary = f"연동 다리 {ok}/{total} 정상 · 실패 {fail}"
        honesty = "측정" if learn_count is not None else "부분"
    else:
        summary = f"연동 다리 점검 실패({bridge_err})"
        honesty = "미측정"

    if learn_count is not None:
        metrics.append({"label": "학습효과 측정대상", "value": learn_count})
        summary += f" · 학습효과 측정대상 {learn_count}건"

    return make_payload(
        title="자율현황 자동화 건강",
        summary_line=summary,
        metrics=metrics,
        honesty_tag=honesty,
        link=_LINK,
    )


def _is_live_erp_path(resolved_path):
    """resolved_path 가 self_health_watchdog 이 읽는 실제 운영 erp_status.json 과
    동일 파일인지(테스트용 임시경로가 아닌지) 확인 — 병합 3섹션은 이때만 붙인다."""
    try:
        return os.path.abspath(resolved_path) == os.path.abspath(str(_self_health.ERP_STATUS_PATH))
    except Exception:
        return False


# ── §라이브 상주 프로세스 (erp_status.json systems 배열) ─────────────────────
def _live_row(erp):
    systems = erp.get("systems")
    if not isinstance(systems, list) or not systems:
        return None
    total = len(systems)
    bad = [s for s in systems if isinstance(s, dict) and s.get("state") != "정상"]
    value = f"{total - len(bad)}/{total} 정상"
    if bad:
        value += " · 이상: " + ", ".join(
            f"{s.get('name', '?')}({s.get('state')})" for s in bad[:5])
    return {"label": "라이브·상주 프로세스", "value": value}


# ── §스케줄·오늘 진행 (automation_health.items 오늘(KST) 실행분) ─────────────
def _schedule_row(erp, now=None):
    ah = erp.get("automation_health")
    items = ah.get("items") if isinstance(ah, dict) else None
    if not isinstance(items, list) or not items:
        return None
    today = (now or datetime.now(_KST)).strftime("%Y-%m-%d")
    ran_today = [it for it in items
                 if isinstance(it, dict) and str(it.get("last_run") or "").startswith(today)]
    fail_today = [it for it in ran_today if it.get("state") not in _LIVE_OK_STATES]
    ok_today = len(ran_today) - len(fail_today)
    waiting = [it for it in items if isinstance(it, dict) and it.get("state") == "대기"]
    value = (f"오늘 실행 {len(ran_today)}건(성공 {ok_today} · 실패 {len(fail_today)}) "
             f"· 대기(주기 미도래) {len(waiting)}건")
    if fail_today:
        value += " · 실패: " + ", ".join(str(it.get("name", "?")) for it in fail_today[:5])
    return {"label": "스케줄·오늘 진행", "value": value}


# ── §ERP 자가건강 (self_health_watchdog.build_digest 재사용, 재수집 금지) ────
def _self_health_rows():
    """정상시에도 '이상 0건 ✅' 한 줄을 상시 노출(기존 watchdog은 정상시 무발신이라
    GM 눈에 안 보였음 — 이 다이제스트가 상시화한다).

    [2026-08-29 GM 승인] 이상 섹션을 첫 줄 요약 → 전체 줄로 넓혔다. 같은 방에 2분 뒤
    따라오던 09:12 별도 통(run_watchdog 단독 발신)을 이 09:10 다이제스트 한 통에 흡수
    — 내용은 그대로, 통 수만 줄인다(단독 발신은 module_reporter 가 notify=False 로 끈다)."""
    try:
        _, sections = _self_health.build_digest()
    except Exception as e:
        return [{"label": "ERP 이상 신호", "value": f"집계 실패({type(e).__name__}: {str(e)[:60]})"}]
    active = {k: v for k, v in sections.items() if v}
    if not active:
        return [{"label": "ERP 이상 신호", "value": "이상 0건 ✅"}]
    return [{"label": f"이상 신호·{name}", "value": "\n    ".join(lines)}
            for name, lines in active.items()]


# ── §주간 품질 회귀 delta (module_report_log.jsonl 재사용 — 새 리포트·새 모듈 없음) ──
def _week_key(dt):
    """ISO 주 키(연, 주). 주 경계 = 월요일(ISO 표준)."""
    y, w, _ = dt.isocalendar()
    return (y, w)


def _weekly_success_rates(log_path=None, now=None):
    """module_report_log.jsonl → {module: {week_key: (ok, total)}}.
    성공 = 그 주에 실제 발신된 보고 건수(sent=true) / 시도 총건수.
    로그 없음·손상 라인은 조용히 건너뛴다(집계 실패로 전체 다이제스트를 깨지 않는다).
    """
    path = log_path or _REPORT_LOG
    agg = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    mod = row["module"]
                    wk = _week_key(datetime.fromisoformat(row["ts"]))
                except Exception:
                    continue
                ok, total = agg.setdefault(mod, {}).get(wk, (0, 0))
                agg[mod][wk] = (ok + (1 if row.get("sent") else 0), total + 1)
    except Exception:
        return {}
    return agg


def _regression_row(log_path=None, now=None):
    """이번주 vs 지난주 모듈별 성공률 delta → 한 줄 metric(없으면 None).
    · delta ≤ -0.10 이고 이번주 표본 ≥5 인 모듈만 'REGRESSED' 플래그
    · 이번주 표본 <5 = 판정 보류(N<5) — 하락으로 단정하지 않고 건수만 정직 표기
    """
    agg = _weekly_success_rates(log_path, now)
    if not agg:
        return None
    ref = now or datetime.now(_KST)
    this_wk = _week_key(ref)
    last_wk = _week_key(ref - timedelta(days=7))

    regressed, held, compared = [], 0, 0
    for mod, weeks in agg.items():
        if this_wk not in weeks or last_wk not in weeks:
            continue
        t_ok, t_total = weeks[this_wk]
        l_ok, l_total = weeks[last_wk]
        if not t_total or not l_total:
            continue
        if t_total < _MIN_SAMPLE:
            held += 1
            continue
        compared += 1
        delta = (t_ok / t_total) - (l_ok / l_total)
        if delta <= _REGRESS_THRESHOLD:
            regressed.append((delta, mod, t_ok, t_total, l_ok, l_total))

    if not compared and not held:
        return {"label": "주간 품질 회귀(전주 대비)",
                "value": "판정 보류 — 전주와 이번주 둘 다 기록된 모듈 없음(비교 불가)"}

    hold_tail = f" · 표본부족 보류 {held}건(N<{_MIN_SAMPLE})" if held else ""
    if not regressed:
        return {"label": "주간 품질 회귀(전주 대비)",
                "value": f"하락 모듈 0건 ✅ (비교 {compared}건){hold_tail}"}

    regressed.sort()  # delta 오름차순 = 하락 폭 큰 순
    top = " · ".join(
        f"{mod} {delta * 100:+.0f}%p({t_ok}/{t_total}←{l_ok}/{l_total})"
        for delta, mod, t_ok, t_total, l_ok, l_total in regressed[:_TOP_N]
    )
    more = f" 외 {len(regressed) - _TOP_N}건" if len(regressed) > _TOP_N else ""
    return {"label": "주간 품질 회귀(전주 대비)",
            "value": f"⚠️ 하락 {len(regressed)}건 (비교 {compared}건){hold_tail} — {top}{more}"}


def _enrich_with_live_signals(payload, erp):
    """payload 를 in-place 로 병합(라이브+스케줄+자가건강) — 실제 운영 erp_status.json
    일 때만 호출된다(테스트/가짜 경로는 원본 payload 그대로 반환하는 기존 계약 보존)."""
    payload["title"] = "전체 자동화 현황"
    for row in (_live_row(erp), _schedule_row(erp), _regression_row()):
        if row:
            payload["metrics"].append(row)
    self_health_rows = _self_health_rows()
    payload["metrics"].extend(self_health_rows)
    sh_summary = self_health_rows[0]["value"] if len(self_health_rows) == 1 else \
        f"이상 {len(self_health_rows)}건"
    payload["summary_line"] = f"{payload['summary_line']} · 이상 신호 {sh_summary}"
    return payload


def collect(module=None) -> dict:
    """표준 payload 반환. 1차=선언된 data_source(erp_status.json), 보강=함수호출.
    실제 운영 erp_status.json 을 읽었을 때만 라이브·스케줄·자가건강 3섹션을 병합한다."""
    ref = _resolve_ref(module)
    erp = _load_json(ref)
    payload = _from_erp_status(erp)
    if payload is not None:
        if _is_live_erp_path(ref):
            _enrich_with_live_signals(payload, erp)
        return payload
    return _from_functions()


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
