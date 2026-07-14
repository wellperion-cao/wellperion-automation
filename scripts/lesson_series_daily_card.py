#!/usr/bin/env python3
"""L시리즈(성인강습 6편) 예약 카드 자동발송기 (2026-07-14).

review_queue.json 에 scheduled_date 로 등록된 L시리즈 편 중 '오늘' 발행 예정인
건을 찾아 기존 send_review_card.py 카드 발송 로직을 그대로 호출한다.

★ 안전 원칙 (반드시 지킬 것):
  - 이 스크립트는 검수 카드를 "보내기만" 한다. 승인(approved)·발행(publish) 절대 금지.
  - status 를 '검수대기'→'승인' 등으로 변경하지 않는다 (bot.py 콜백 몫).
  - ig_review_publish_watcher 등 발행 엔진을 호출하지 않는다.
  - 발행은 100% GM 의 텔레그램 [✅ 승인] 탭으로만 이뤄진다(게이트 불변).

멱등성: 오늘 이미 카드를 보낸 id 는 상태 파일(SENT_STATE)에 기록해두고,
같은 날 재실행돼도 다시 보내지 않는다(날짜가 바뀌면 자동 리셋).

사용법:
  python scripts\\lesson_series_daily_card.py             # 실발송(오늘 날짜 기준)
  python scripts\\lesson_series_daily_card.py --dry-run    # 발송 시뮬레이션만(전송 없음)
  python scripts\\lesson_series_daily_card.py --dry-run --as-of 2026-07-15  # 특정 날짜로 시뮬레이션

Task Scheduler: launchers\\lesson_series_daily_card_hidden.vbs (매일 08:45, 조용한 아침 슬롯)
되돌리기: schtasks /delete /tn "Wellperion-LSeries-Daily-Card-0845" /f 후 스크립트 삭제.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
SENT_STATE = ROOT / "status" / "lesson_series_daily_card_sent.json"

# L시리즈 판별: id 접두사 + 계정. review_queue.json 등록 규칙(CMO-2026-07-14-LSERIES-*) 고정.
LSERIES_ID_PREFIX = "CMO-2026-07-14-LSERIES-"
LSERIES_ACCOUNT = "wellperion"


def load_queue() -> list:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] 큐 파싱 실패: {e}")
        return []


def _load_sent_state() -> dict:
    """{"date": "YYYY-MM-DD", "ids": ["...", ...]} — 날짜 바뀌면 자동 리셋."""
    try:
        if SENT_STATE.exists():
            return json.loads(SENT_STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _mark_sent(today_str: str, item_id: str) -> None:
    state = _load_sent_state()
    if state.get("date") != today_str:
        state = {"date": today_str, "ids": []}
    ids = state.get("ids", [])
    if item_id not in ids:
        ids.append(item_id)
    state["ids"] = ids
    state["date"] = today_str
    try:
        SENT_STATE.parent.mkdir(parents=True, exist_ok=True)
        SENT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 발송 상태 저장 실패(무해 - 다음 실행에 재시도됨): {e}")


def _already_sent_today(today_str: str, item_id: str) -> bool:
    state = _load_sent_state()
    return state.get("date") == today_str and item_id in state.get("ids", [])


def find_today_item(items: list, today_str: str) -> dict | None:
    """L시리즈 · 검수대기 · scheduled_date == today_str 인 단일 항목을 찾는다."""
    for it in items:
        if not str(it.get("id", "")).startswith(LSERIES_ID_PREFIX):
            continue
        if it.get("account") != LSERIES_ACCOUNT:
            continue
        if it.get("status") != "검수대기":
            continue
        if it.get("scheduled_date") != today_str:
            continue
        return it
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="L시리즈 예약 카드 자동발송(당일분, 카드 발송 전용 — 승인/발행 금지)")
    p.add_argument("--dry-run", action="store_true", help="실제 전송 없이 시뮬레이션만(검증용)")
    p.add_argument("--as-of", help="시뮬레이션 기준 날짜 YYYY-MM-DD (--dry-run 전용, 미지정 시 오늘)")
    args = p.parse_args()

    if args.as_of and not args.dry_run:
        print("[ERROR] --as-of 는 --dry-run 과 함께만 사용 가능(실발송은 항상 실제 오늘 기준).")
        sys.exit(1)

    today_str = args.as_of if (args.dry_run and args.as_of) else date.today().isoformat()

    items = load_queue()
    target = find_today_item(items, today_str)

    if target is None:
        print(f"[INFO] {today_str} 예정 L시리즈 검수대기 항목 없음 — no-op.")
        return

    item_id = target.get("id", "")
    title = target.get("title", item_id)

    if _already_sent_today(today_str, item_id):
        print(f"[INFO] 오늘({today_str}) 이미 카드 발송 완료(멱등 가드) — 재발송 생략: {item_id}")
        return

    if args.dry_run:
        print(f"[DRY-RUN] {today_str} 대상 식별: {item_id} ({title})")
        print("[DRY-RUN] send_review_card.send_card() 호출 예정이었음 — 실제 전송/승인/발행 없음.")
        return

    # 실발송: 기존 send_review_card.py 로직 재사용(카드 발송만 — 승인/발행 절대 호출하지 않음)
    sys.path.insert(0, str(ROOT / "scripts"))
    import send_review_card  # noqa: E402  (기존 검수카드 발송기 — 승인/발행 로직 없음)

    ok = send_review_card.send_card(target)
    if ok:
        _mark_sent(today_str, item_id)
        print(f"[INFO] L시리즈 예약 카드 발송 완료: {item_id} ({title})")
    else:
        print(f"[WARN] L시리즈 예약 카드 발송 실패: {item_id} — 다음 실행에서 재시도됨(상태 미기록).")


if __name__ == "__main__":
    main()
