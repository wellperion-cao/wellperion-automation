#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GM 프로필 생성기 (배237 · GM 보좌 자율화 체계 phase 1 · 구현①).

관찰 원장(gm_observation_ledger.jsonl)과 업무 큐(_queue*.json)를 읽어
'GM의 성향·습관·자주 놓치는 것·루틴 준수·핵심 수치지표'를 담은
사람이 읽는 서술 프로필 status/gm_profile.md 를 생성한다.

설계 정본:
  - 스펙 : .omc/specs/deep-interview-gm-aide-autonomy.md (①관찰·학습 = 수치+LLM 하이브리드, 일일 갱신)
  - 배   : status/_queue.json  CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237)

두뇌(하이브리드):
  - 1순위: claude CLI (scripts/model_router.run_claude · 폴백 체인) — LLM 서술 프로필
  - 2순위: 규칙기반 서술 폴백 — CLI 전멸 시에도 무중단(수치 카운터 기반 요약)

★ phase 1 안전 원칙 (라이브 부작용 0):
  - 파일 read + status/gm_profile.md write 만. 발송·삭제·외부전송·GAS·시트 변경 0.
  - 멱등: 같은 입력이면 수치 카운터 동일. gm_profile.md 는 매 실행 전체 덮어쓰기(일일 갱신).

사용법:
  python scripts/gm_profile_builder.py            # 프로필 생성(기본) — gm_profile.md 갱신
  python scripts/gm_profile_builder.py --stdout-only   # 파일 기록 없이 콘솔만(드라이)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
LEDGER = STATUS_DIR / "gm_observation_ledger.jsonl"
QUEUE_ACTIVE = STATUS_DIR / "_queue.json"
QUEUE_ARCHIVE = STATUS_DIR / "_queue_archive.json"
NORTHSTAR_LOG = STATUS_DIR / "northstar_log.jsonl"
PROFILE_MD = STATUS_DIR / "gm_profile.md"

LONG_PENDING_DAYS = 30
TODAY = datetime.now().date()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ═══════════════════════════════════════════
#  입력 로드
# ═══════════════════════════════════════════
def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_json_array(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


# ═══════════════════════════════════════════
#  수치 카운터 (결정적 · 항상 계산)
# ═══════════════════════════════════════════
def compute_counters(ledger: list, active: list, archive: list, ns_log: list) -> dict:
    by_type = Counter(r.get("signal_type") for r in ledger)
    by_source = Counter(r.get("source") for r in ledger)

    # 활성 큐 상태 분포
    status_counter = Counter(x.get("status") for x in active)

    # 장기 대기(라이브 재계산)
    long_pending = 0
    for x in active:
        if x.get("status") != "PENDING":
            continue
        enq = x.get("enqueued_at")
        if not enq:
            continue
        try:
            d = datetime.strptime(enq, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (TODAY - d).days >= LONG_PENDING_DAYS:
            long_pending += 1

    # 표류(완료·terminal 인데 next 없음) — 활성 큐 기준
    drift = 0
    for x in active:
        if x.get("status") == "DONE" or x.get("terminal"):
            if not (x.get("next") or "").strip():
                drift += 1

    # 북극성 추천 미응답 연속 streak(최근 expired 연속)
    missed_streak = 0
    for e in reversed(ns_log):
        if e.get("event") == "expired":
            missed_streak += 1
        elif e.get("event") == "proposed":
            # proposed 이후 approved 없이 다음 expired 로만 이어지면 미응답 지속
            continue
        else:
            break

    return {
        "observations_total": len(ledger),
        "observations_by_type": dict(by_type),
        "observations_by_source": dict(by_source),
        "gm_decisions": by_type.get("decision", 0),
        "missed_recommendations": by_type.get("missed", 0),
        "drift_events_ledger": by_type.get("repeat", 0),
        "queue_active_total": len(active),
        "queue_status": dict(status_counter),
        "queue_archive_total": len(archive),
        "long_pending_live": long_pending,
        "drift_live": drift,
        "northstar_missed_streak": missed_streak,
    }


# ═══════════════════════════════════════════
#  두뇌 ① — claude CLI (model_router 폴백)
# ═══════════════════════════════════════════
def _ledger_digest(ledger: list, limit: int = 24) -> str:
    """원장에서 최근·대표 관찰 요약을 프롬프트용 다이제스트로."""
    lines = []
    for r in ledger[-limit:]:
        st = r.get("signal_type", "?")
        summ = (r.get("summary") or "").strip()[:110]
        hint = (r.get("pattern_hint") or "").strip()[:80]
        lines.append(f"- [{st}] {summ}" + (f" · 힌트:{hint}" if hint else ""))
    return "\n".join(lines)


def _build_prompt(counters: dict, ledger: list) -> str:
    digest = _ledger_digest(ledger)
    ct = counters
    return f"""당신은 웰페리온(하이엔드 스포츠클럽 멤버십 커뮤니티) AI CEO '웰리'입니다.
GM(대표)을 보좌하기 위해, 관찰 원장과 업무 큐 지표를 근거로 **GM의 성향·습관 프로필**을 작성합니다.
목적: GM이 놓친 것·다음 할 것을 웰리가 선제 포착할 수 있도록, GM의 일하는 패턴을 서술로 정리하는 것.

[수치 지표(관찰 원장·큐 집계)]
- 총 관찰 {ct['observations_total']}건 (유형별: {ct['observations_by_type']})
- GM 결정 이력 {ct['gm_decisions']}건 / 추천 카드 미응답 {ct['missed_recommendations']}건 (최근 연속 미응답 {ct['northstar_missed_streak']}일)
- 표류(완료 후 다음 미정) 관찰 {ct['drift_events_ledger']}건 / 라이브 표류 {ct['drift_live']}건
- 활성 큐 {ct['queue_active_total']}척 (상태: {ct['queue_status']}) · 장기 대기(30일+) {ct['long_pending_live']}척

[최근 관찰 다이제스트]
{digest}

위 지표와 관찰을 근거로, GM의 프로필을 **한국어 마크다운 서술**로 작성하세요.
반드시 아래 5개 소제목(## )을 그대로 사용하고, 각 항목은 3~5개의 불릿으로 근거와 함께 씁니다.
추정은 '추정' 라벨을 붙이고, 측정 못 한 것을 측정한 척하지 마세요(관측 정직).

## 선호
## 습관
## 자주 놓치는 것
## 루틴 준수
## 핵심 수치지표 해석

규칙:
- 순수 마크다운 본문만 출력(코드블록·머리말·맺음말 없이).
- 프라이버시: 민감 원문 대신 패턴·요약 위주.
- 각 불릿은 근거(어느 지표/관찰)에 연결되게."""


def brain_claude_cli(counters: dict, ledger: list) -> tuple[str | None, str | None]:
    prompt = _build_prompt(counters, ledger)
    try:
        from model_router import run_claude
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_router import run_claude
    raw, used_model = run_claude(prompt, label="gm-profile-builder")
    if raw is None:
        return None, None
    return raw.strip(), used_model


# ═══════════════════════════════════════════
#  두뇌 ② — 규칙기반 서술 폴백 (CLI 전멸 시 무중단)
# ═══════════════════════════════════════════
def brain_fallback(counters: dict) -> str:
    ct = counters
    streak = ct["northstar_missed_streak"]
    q = ct["queue_status"]
    pending = q.get("PENDING", 0)
    inprog = q.get("IN_PROGRESS", 0)
    parts = []
    parts.append("## 선호")
    parts.append(f"- (추정) GM 결정 이력 {ct['gm_decisions']}건 — 큐 note에 결정을 직접 남기는 방식을 선호(원장 근거).")
    parts.append("- (추정) 라이브 파괴 위험 작업은 '다음 집중세션·신중' 지시로 미루는 경향(결정 관찰 패턴).")
    parts.append("")
    parts.append("## 습관")
    parts.append(f"- 활성 배 {ct['queue_active_total']}척 동시 진행(PENDING {pending}·IN_PROGRESS {inprog}) — 병렬 다발 진행 습관.")
    parts.append(f"- 완료 아카이브 {ct['queue_archive_total']}건 — 지속적으로 배를 완주·아카이브하는 흐름.")
    parts.append("")
    parts.append("## 자주 놓치는 것")
    if streak >= 1:
        parts.append(f"- 06:30 북극성 추천 카드 최근 {streak}일 연속 미응답 — 아침 카드 응답을 자주 놓침(로그 근거).")
    parts.append(f"- 표류(완료 후 다음 미정) 라이브 {ct['drift_live']}건 — 완료 시 '다음 한 수' 지정을 빠뜨리는 경향.")
    parts.append(f"- 장기 대기(30일+) {ct['long_pending_live']}척 — 우선순위 낮은 배의 정리·폐기 판단을 미룸.")
    parts.append("")
    parts.append("## 루틴 준수")
    parts.append(f"- 추천 카드 미응답 {ct['missed_recommendations']}건 — 일일 추천 루틴 응답률 낮음(개선 여지).")
    parts.append("- (추정) 지시-실행-완료 사이클은 유지되나, 사후 '다음 정하기' 루틴은 느슨.")
    parts.append("")
    parts.append("## 핵심 수치지표 해석")
    parts.append(f"- 총 관찰 {ct['observations_total']}건 / 유형: {ct['observations_by_type']}")
    parts.append(f"- 활성 {ct['queue_active_total']}척 · 장기대기 {ct['long_pending_live']} · 표류 {ct['drift_live']} · 미응답 연속 {streak}일")
    parts.append("- 해석(추정): 개입 지점은 '완료 후 다음 정하기' + '아침 추천 응답' + '장기대기 정리' 3곳.")
    return "\n".join(parts)


# ═══════════════════════════════════════════
#  md 렌더
# ═══════════════════════════════════════════
def render_counters_block(ct: dict) -> str:
    q = ct["queue_status"]
    lines = [
        "## 핵심 수치 카운터 (결정적 집계)",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| 총 관찰 | {ct['observations_total']}건 |",
        f"| GM 결정 이력 | {ct['gm_decisions']}건 |",
        f"| 추천 카드 미응답 | {ct['missed_recommendations']}건 |",
        f"| 추천 미응답 연속 | {ct['northstar_missed_streak']}일 |",
        f"| 표류(원장/라이브) | {ct['drift_events_ledger']} / {ct['drift_live']}건 |",
        f"| 활성 큐 | {ct['queue_active_total']}척 (PENDING {q.get('PENDING', 0)}·IN_PROGRESS {q.get('IN_PROGRESS', 0)}·DONE {q.get('DONE', 0)}) |",
        f"| 장기 대기(30일+) | {ct['long_pending_live']}척 |",
        f"| 완료 아카이브 | {ct['queue_archive_total']}건 |",
        "",
        f"관찰 유형별: `{ct['observations_by_type']}`",
        "",
    ]
    return "\n".join(lines)


def build_markdown(narrative: str, counters: dict, generated_by: str) -> str:
    header = (
        "# GM 프로필 (웰리 학습 · GM 보좌 자율화 phase 1)\n\n"
        f"- 생성: {now_str()}\n"
        f"- 생성 두뇌: {generated_by}\n"
        f"- 근거: `status/gm_observation_ledger.jsonl` + `status/_queue*.json` + `status/northstar_log.jsonl`\n"
        "- 성격: 사람이 읽는 서술 프로필(일일 갱신·멱등). 라이브 부작용 0.\n"
        "- 배: CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237) · 스펙: `.omc/specs/deep-interview-gm-aide-autonomy.md`\n\n"
        "---\n\n"
    )
    return header + render_counters_block(counters) + "\n---\n\n" + narrative.rstrip() + "\n"


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(stdout_only: bool = False) -> str:
    print(f"[시작] GM 프로필 생성기 — {now_str()}")
    ledger = read_jsonl(LEDGER)
    active = read_json_array(QUEUE_ACTIVE)
    archive = read_json_array(QUEUE_ARCHIVE)
    ns_log = read_jsonl(NORTHSTAR_LOG)
    print(f"[1/3] 입력 로드 — 관찰 {len(ledger)}건 · 활성큐 {len(active)}척 · 아카이브 {len(archive)}건")

    counters = compute_counters(ledger, active, archive, ns_log)

    print("[2/3] 웰리 두뇌(claude CLI · model_router 폴백) 호출...")
    narrative, used_model = brain_claude_cli(counters, ledger)
    if narrative is None:
        generated_by = "규칙폴백"
        narrative = brain_fallback(counters)
        print("  → 규칙기반 서술 폴백(claude CLI 미가용 — 정상 강등)")
    else:
        generated_by = f"ClaudeCLI({used_model})"
        print(f"  → ClaudeCLI 서술 생성(model={used_model}, {len(narrative)}자)")

    md = build_markdown(narrative, counters, generated_by)

    print(f"\n[요약] 수치 카운터")
    print(f"  · 총 관찰 {counters['observations_total']} · 결정 {counters['gm_decisions']} · 미응답 {counters['missed_recommendations']}(연속 {counters['northstar_missed_streak']}일)")
    print(f"  · 표류 라이브 {counters['drift_live']} · 장기대기 {counters['long_pending_live']} · 활성 {counters['queue_active_total']}")

    if stdout_only:
        print("\n[--stdout-only] 파일 기록 생략 (미리보기)\n")
        print(md[:800])
        return md

    PROFILE_MD.write_text(md, encoding="utf-8")
    print(f"\n[3/3] 기록 완료: {PROFILE_MD}")
    print(f"[완료] ({now_str()})")
    return md


def main():
    parser = argparse.ArgumentParser(
        description="GM 프로필 생성기 phase1 — 관찰 원장+큐 → gm_profile.md(수치+LLM 서술 하이브리드)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--stdout-only", action="store_true", dest="stdout_only",
                        help="파일 기록 없이 콘솔 미리보기만(드라이)")
    args = parser.parse_args()
    run(stdout_only=args.stdout_only)


if __name__ == "__main__":
    main()
