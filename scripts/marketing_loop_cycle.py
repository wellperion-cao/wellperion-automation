#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""marketing_loop_cycle.py — 시모 마케팅 폐루프 오케스트레이션 v1 (배관만 · dry 기본 · 휴면).

담당: 웰리(AI CEO) 총괄 오케스트레이션(단계 완료→다음 촉발) + 시모(AI CMO) 단계 실행.
스펙: .omc/specs/deep-interview-cmo-loop-autonomy.md (deep-interview 확정 · 모호도 9%)
정직 원칙(약속 L05): 실제로 실행한 단계만 '실행'으로 표시. 안 한 단계는 '(dry — 미실행)'.
빈 슬롯을 지어내지 않는다 — ⑤ 제안이 없으면 "제안 없음(대기)" 그대로 출력.

한 사이클 = ⑤평가(weekly_marketing_feedback.py) → 제안 읽기(참고) → ①제작 참고 전달(휴면).
②발행 GM 승인 게이트는 이 오케스트레이터가 절대 건드리지 않는다(상시 유지 — 관여 없음).

──────────────────────────────────────────────────────────
발효 플래그 + 역롤백 (v1 — 라이브 발효는 GM go 1회 필요)
──────────────────────────────────────────────────────────
- CMO_LOOP_FEEDBACK (기본 OFF/미설정): ON 이면 ①제작(ig_series_producer.py)이 ⑤ 최신 제안
  슬롯을 선정 로그에 '참고'로 출력(선정 자체는 불변 — 시모 확정 필요). 자세한 내용은
  scripts/ig_series_producer.py 모듈 docstring '⑤→① 되먹임 참고' 절 참조.
- 역롤백: 환경변수 CMO_LOOP_FEEDBACK 을 언셋(또는 0/false)하면 즉시 이전 동작으로 복귀.
- 주간 cron(⑤ 자동 실행)은 **아직 미등록**. 등록 커맨드 SSOT = weekly_marketing_feedback.py
  모듈 docstring 상단(schtasks /create ... Wellperion-CMO-Weekly-Marketing-Feedback) —
  여기서 재타이핑하지 않는다(중복 방지). GM 승인 후 관리자 권한 콘솔에서 그 명령 1회 실행.
- 이 오케스트레이터 자신도 cron 미등록 — GM go 전엔 수동 실행(--dry-run)만 안전.

실행:
  python scripts/marketing_loop_cycle.py               (기본 = --dry-run 과 동일, 아무것도 실행 안 함)
  python scripts/marketing_loop_cycle.py --dry-run      (동일 · 명시 — 단계만 출력)
  python scripts/marketing_loop_cycle.py --run          (⑤ weekly_marketing_feedback.py 실제 실행.
                                                           나머지 단계는 여전히 참고/보고만 — 자동 촉발 없음)

v2 훅: 사이클 완료 후 자동으로 다음 사이클을 스케줄링하거나, 제안 채택률을 학습해
       producer 가중치를 자동 조정하는 로직은 데이터(UTM 표본) 축적 후 추가한다
       (현재 미구현 — sparse 과적합 방지, 시모 확정 유지).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서도 한글 print 안 깨지도록.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconf = getattr(_stream, "reconfigure", None) if _stream is not None else None
    if _reconf is not None:
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = _SCRIPT_DIR.parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
WEEKLY_FEEDBACK_SCRIPT = _SCRIPT_DIR / "weekly_marketing_feedback.py"

CMO_LOOP_FEEDBACK_ENV = "CMO_LOOP_FEEDBACK"

# ig_series_producer.py 의 read_latest_marketing_proposal() 을 재사용(파싱 로직 중복 금지 —
# ⑤ 슬롯 판정 기준(플레이스홀더 문자열)이 두 곳에서 다르게 어긋나는 사고 방지).
sys.path.insert(0, str(_SCRIPT_DIR))


def _loop_feedback_flag_state() -> str:
    val = os.environ.get(CMO_LOOP_FEEDBACK_ENV, "").strip().lower()
    return "ON" if val in ("1", "true", "on", "yes") else "OFF(기본)"


def step_run_weekly_feedback(execute: bool) -> bool:
    """⑤ 평가 환류 단계. execute=False(dry) 면 실제 실행 안 하고 안내만 출력."""
    print("── [1/3] ⑤ 평가 환류 (weekly_marketing_feedback.py) ──")
    if not execute:
        print("  (dry — 미실행) --run 플래그로 실제 실행 가능. SSOT: " + str(WEEKLY_FEEDBACK_SCRIPT))
        return False
    if not WEEKLY_FEEDBACK_SCRIPT.exists():
        print(f"  [WARN] 스크립트 부재 — 실행 불가: {WEEKLY_FEEDBACK_SCRIPT}")
        return False
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(
            [str(PY), str(WEEKLY_FEEDBACK_SCRIPT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )
        print(proc.stdout or "")
        if proc.stderr:
            print(proc.stderr)
        ok = proc.returncode == 0
        print(f"  [{'OK' if ok else 'WARN'}] weekly_marketing_feedback.py 실행 {'완료' if ok else '실패'} (exit={proc.returncode})")
        return ok
    except Exception as exc:
        print(f"  [WARN] weekly_marketing_feedback.py 실행 예외: {exc}")
        return False


def step_read_proposal() -> str | None:
    """제안 읽기(참고 전용) — ig_series_producer.read_latest_marketing_proposal() 재사용."""
    print("── [2/3] 제안 읽기 (⑤ 최신 정리 보고 → '다음 편 제안' 슬롯, 참고 전용) ──")
    try:
        import ig_series_producer as _producer

        proposal = _producer.read_latest_marketing_proposal()
    except Exception as exc:
        print(f"  [WARN] 제안 읽기 예외(정직 폴백 — 제안 없음 취급): {exc}")
        return None
    if proposal:
        print(f"  [참고] 제안 발견:\n{proposal}")
    else:
        print("  제안 없음(대기) — 시모가 아직 ⑤ 보고의 '다음 편 제안' 슬롯을 채우지 않음.")
    return proposal


def step_hand_to_producer(proposal: str | None) -> None:
    """①제작 참고 전달 — 휴면(dormant). 실제 producer 호출은 절대 하지 않는다(v1 배관만).

    CMO_LOOP_FEEDBACK 플래그가 실제로 ON 이어야 ①제작(ig_series_producer.py) 이 이 제안을
    선정 로그에 참고 출력한다(이 오케스트레이터가 대신 켜거나 호출하지 않음 — 자율 발효 없음).
    """
    print("── [3/3] ①제작 참고 전달 (휴면 — producer 자동 호출 없음) ──")
    flag_state = _loop_feedback_flag_state()
    print(f"  CMO_LOOP_FEEDBACK = {flag_state}")
    if flag_state.startswith("ON"):
        print("  → 다음 ①제작(ig_series_producer.py) 가동 시 위 제안을 선정 로그에 참고 출력(선정 자체는 불변).")
    else:
        print("  → 플래그 OFF — ①제작은 이 제안을 전혀 읽지 않음(기존 동작과 100% 동일). 발효 = GM go.")
    print("  ②발행 GM 승인 게이트: 이 오케스트레이터는 관여하지 않음(상시 유지).")


def run_cycle(execute: bool) -> int:
    print(
        f"[INFO] === 시모 마케팅 폐루프 사이클 (오케스트레이션 v1, 웰리 총괄) === "
        f"execute={execute} (dry={'아니오' if execute else '예'})"
    )
    step_run_weekly_feedback(execute)
    proposal = step_read_proposal()
    step_hand_to_producer(proposal)
    print("[OK] 사이클 단계 출력 완료 — 자동 촉발(cron) 없음, 수동/GM go 대기.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="시모 마케팅 폐루프 주간 사이클 오케스트레이션 (v1 배관 · 기본 dry-run)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="기본값과 동일 — 아무것도 실행하지 않고 단계만 출력"
    )
    ap.add_argument(
        "--run", action="store_true", help="⑤ weekly_marketing_feedback.py 실제 실행(그 외 단계는 여전히 참고/보고만)"
    )
    args = ap.parse_args()
    execute = bool(args.run) and not args.dry_run
    return run_cycle(execute=execute)


if __name__ == "__main__":
    sys.exit(main())
