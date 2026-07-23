# scripts/ai_daily_series_card.py
# "폰 하나로 회사를 본다" 개인계정 시리즈 — 매일 아침 카드 1장 드립 (2026-07-21).
#
# review_queue.json 에 이미 status='검수대기' 로 선등록된 AIDAY01~10 중,
# 아직 카드 미발송(.review_card_msgids.json 에 없음)인 가장 낮은 회차 1건만
# 골라 send_review_card.send_card() 로 발송한다(그 모듈의 pace·락·dedup 재사용).
#
# 규칙:
#   - 평일(월~금)만 발송. 토·일은 조용히 종료.
#   - 하루 1장만(루프 금지).
#   - 후보 없음(전부 발송/소진)이면 조용히 종료.
#   - --dry-run: 고를 항목만 출력하고 실제 발송 안 함.
#   - 토큰 stdout 노출 금지 — send_review_card 모듈 재사용(텔레그램 직접 호출 재구현 금지).
#
# 실행:
#   .venv\Scripts\python.exe scripts\ai_daily_series_card.py
#   .venv\Scripts\python.exe scripts\ai_daily_series_card.py --dry-run
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"
SERIES_MARKER = "-AIDAY"

_SCRIPTS_DIR = ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _load_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[ERROR] review_queue 파싱 실패: {exc}")
        return []


def _sent_ids() -> set[str]:
    """이미 카드 발송된 id 집합 (.review_card_msgids.json 기준)."""
    if not MSGID_STORE.exists():
        return set()
    try:
        raw = json.loads(MSGID_STORE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(raw, dict):
        return set()
    return set(raw.keys())


def _episode_num(item_id: str) -> int:
    """id 에서 AIDAY 뒤 2자리 숫자 추출(정렬용). 파싱 실패 시 큰 값(뒤로 밀림)."""
    try:
        idx = item_id.index(SERIES_MARKER) + len(SERIES_MARKER)
        return int(item_id[idx : idx + 2])
    except Exception:
        return 99


def pick_next_candidate() -> dict | None:
    """review_queue 에서 status='검수대기' + id 에 -AIDAY 포함 + 카드 미발송 중 가장 낮은 회차 1건."""
    queue = _load_queue()
    sent = _sent_ids()
    candidates = [
        item
        for item in queue
        if item.get("status") == "검수대기"
        and SERIES_MARKER in str(item.get("id", ""))
        and item.get("id") not in sent
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda it: _episode_num(str(it.get("id", ""))))
    return candidates[0]


def _run_card_dispatch(args) -> int:
    today = datetime.now()
    if today.weekday() >= 5:  # 5=토, 6=일
        print(f"[INFO] 오늘({today.strftime('%Y-%m-%d')})은 주말 — 드립 생략, 조용히 종료.")
        return 0

    candidate = pick_next_candidate()
    if candidate is None:
        print("[INFO] 발송 대상 없음(전부 발송 완료 또는 대기 항목 없음) — 조용히 종료.")
        return 0

    print(f"[INFO] 오늘 고를 항목 = {candidate.get('id')} / {candidate.get('title')}")

    if args.dry_run:
        print("[DRY-RUN] 실제 발송 안 함.")
        return 0

    from send_review_card import send_card

    try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 카드 발송 무영향
        from worklog import log as worklog_log
    except Exception:
        def worklog_log(*a, **k):
            return False

    ok = send_card(candidate)
    if ok:
        print(f"[OK] 카드 발송 완료 — id={candidate.get('id')}")
        worklog_log("cmo", "검수", f"{candidate.get('title', candidate.get('id'))} 검수카드 GM 발송",
                    result="ok", ref=str(candidate.get("id", "")))
        return 0
    print(f"[ERROR] 카드 발송 실패 — id={candidate.get('id')}")
    return 1


def _run_worklog_gaps_scan_best_effort() -> None:
    """감지기 자동 실행(best-effort) — 기존 예약작업(07:30)에 편승, 신규 예약작업 미생성.
    실패해도 카드 발송 결과(반환코드)에 절대 영향 없음(2026-07-23, CMO-2026-07-23-WORKLOG-PANEL)."""
    try:
        import worklog_gaps
        result = worklog_gaps.scan()
        print(f"[INFO] worklog_gaps 스캔 — 빠진 것 {len(result.get('gaps', []))}건 "
              f"(status/worklog_gaps.json 갱신)")
    except Exception as exc:
        print(f"[WARN] worklog_gaps 스캔 예외(best-effort, 카드 발송 무영향): {exc}")


def main() -> int:
    p = argparse.ArgumentParser(description="AI 개인계정 시리즈 — 매일 아침 카드 1장 드립")
    p.add_argument("--dry-run", action="store_true", help="고를 항목만 출력, 실제 발송 안 함")
    args = p.parse_args()

    rc = _run_card_dispatch(args)
    _run_worklog_gaps_scan_best_effort()
    return rc


if __name__ == "__main__":
    sys.exit(main())
