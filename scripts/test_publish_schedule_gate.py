"""예약 발행 게이트 자체검사 (배401 · 2026-08-05)

지키는 것 = ig_review_publish_watcher 의 '언제 나가느냐' 판정 한 곳.
  · publish_at 없음        → 지금까지와 동일(승인 즉시 발행) — 회귀 0 보증
  · publish_at 지남        → 발행
  · publish_at 미래        → 보류. ★events 를 늘리지 않는다(events 는 텔레그램 요약으로
                              나가므로, 며칠 뒤 예약 1건이 매 회차 알림을 쏘면 발신 폭주)
  · publish_at 형식 깨짐   → 보류 + 알림 1건(조기 발행은 비가역이라 예약 누락보다 나쁘다)
  · 승인 상태 아님          → 시각과 무관하게 차단

실행: C:/Python314/python.exe scripts/test_publish_schedule_gate.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ig_review_publish_watcher as w  # noqa: E402

PAST = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
FUTURE = (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M")


def main() -> int:
    ev: list[str] = []

    assert w._publish_time_reached({"id": "a"}, ev) is True, "예약 없으면 즉시 발행이어야 한다"
    assert w._publish_time_reached({"id": "b", "publish_at": PAST}, ev) is True, "시각이 지나면 발행"
    assert not ev, "여기까지는 알림이 없어야 한다"

    assert w._publish_time_reached({"id": "c", "publish_at": FUTURE}, ev) is False, "미래 예약은 보류"
    assert not ev, "예약 대기는 텔레그램 알림을 만들면 안 된다(발신 폭주 방지)"

    assert w._publish_time_reached({"id": "d", "publish_at": "2026-08-09 아침"}, ev) is False, \
        "형식이 깨지면 조기 발행하지 말고 보류"
    assert len(ev) == 1, "형식 오류는 사람이 볼 수 있게 알림 1건"

    assert w._assert_publish_authorized({"id": "e", "status": "검수대기"}, ev) is False, "미승인 차단"
    assert w._assert_publish_authorized({"id": "f", "status": "승인", "publish_at": FUTURE}, ev) is False, \
        "승인됐어도 예약 시각 전이면 차단"
    assert w._assert_publish_authorized({"id": "g", "status": "승인"}, ev) is True, \
        "승인 + 예약 없음 = 즉시 발행(기존 동작)"

    print("OK — 예약 발행 게이트 8항목 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
