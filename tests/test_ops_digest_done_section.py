# -*- coding: utf-8 -*-
"""send_ops_digest.build_done_section() 자체 점검 — 실 GAS 호출 없음(fake rows).

확인: ①운영부 아닌 담당자·미완료 건 제외 ②새로 완료된 건만 절에 실림
③지난 회차와 완료건이 같으면 절 없음(빈 문자열) ④id 로 dedup(업무명 바뀌어도 재알림 안 함)
⑤즉각 알림·아침 다이제스트가 같은 스냅샷을 공유하면 같은 건을 두 번 안 보냄(배431·GM 2026-08-06)
⑥하루 일과 정리(build_daily_done_section)는 날짜로만 거르고 중복억제가 없음
⑦조용한 시간(22:00~08:00) 판정.
실행: C:\\Python314\\python.exe tests/test_ops_digest_done_section.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from send_ops_digest import build_done_section, build_daily_done_section, in_ops_quiet_hours  # noqa: E402

ROWS = [
    {"id": "1", "업무명": "주차 라인 도색", "담당자": "최준용M", "상태": "완료"},
    {"id": "2", "업무명": "냉방기 점검", "담당자": "이경연 실장", "상태": "완료"},
    {"id": "3", "업무명": "예산안 검토", "담당자": "나우열M", "상태": "완료"},   # 운영부 아님 — 제외
    {"id": "4", "업무명": "락커 정리", "담당자": "윤병현AM", "상태": "진행중"},  # 미완료 — 제외
]

ROWS_WITH_DATE = [
    {"id": "10", "업무명": "누수 점검", "담당자": "최준용M", "상태": "완료", "수정일": "2026-08-06 09:10:00"},
    {"id": "11", "업무명": "락커 교체", "담당자": "이경연 실장", "상태": "완료", "수정일": "2026-08-05 18:00:00"},  # 어제 완료 — 제외
    {"id": "12", "업무명": "예산안 검토", "담당자": "나우열M", "상태": "완료", "수정일": "2026-08-06 10:00:00"},   # 운영부 아님 — 제외
]


def main() -> None:
    section, current = build_done_section(ROWS, prev_ids={})
    assert "✅ 완료된 일 2건" in section, section
    assert "주차 라인 도색 — 최준용M 완료" in section, section
    assert "냉방기 점검 — 이경연 실장 완료" in section, section
    assert "예산안 검토" not in section, "운영부 아닌 담당자가 새어나옴"
    assert "락커 정리" not in section, "미완료 건이 새어나옴"
    assert set(current.keys()) == {"1", "2"}

    # 지난 회차 스냅샷과 완료건이 같으면 절 없음
    section2, _ = build_done_section(ROWS, prev_ids=current)
    assert section2 == "", "변화 없는데 재알림"

    # 업무명이 바뀌어도 id 로 같은 건이면 재알림 안 함
    renamed = [dict(r) for r in ROWS]
    renamed[0]["업무명"] = "주차 라인 재도색(보완)"
    section3, _ = build_done_section(renamed, prev_ids=current)
    assert section3 == "", "id 는 그대로인데 업무명만 바뀌어 재알림"

    # ⑤즉각 알림이 먼저 스냅샷을 전진시키면(카톡 발송 성공 후 _save_done_state 호출을
    #   흉내) 아침 다이제스트가 같은 함수·같은 스냅샷으로 다시 불러도 그 건을 또 안 보낸다.
    section_immediate, snap_after_immediate = build_done_section(ROWS, prev_ids={})
    assert "완료된 일 2건" in section_immediate
    section_morning, _ = build_done_section(ROWS, prev_ids=snap_after_immediate)
    assert section_morning == "", "즉각 알림이 보낸 건을 아침 다이제스트가 중복 발송"

    # ⑥하루 일과 정리 — 날짜로만 거르고(어제 완료·타부서 제외) 중복억제 없음
    daily = build_daily_done_section(ROWS_WITH_DATE, "2026-08-06")
    assert "완료된 운영부 업무 1건" in daily, daily
    assert "누수 점검" in daily
    assert "락커 교체" not in daily, "어제 완료건이 오늘 정리에 새어나옴"
    assert "예산안 검토" not in daily, "운영부 아닌 담당자가 새어나옴"
    daily_again = build_daily_done_section(ROWS_WITH_DATE, "2026-08-06")
    assert daily_again == daily, "같은 날 재호출인데 결과가 달라짐(중복억제 로직이 끼면 안 된다)"
    assert build_daily_done_section(ROWS_WITH_DATE, "2026-08-07") == "", "빈 날짜엔 빈 절"

    # ⑦조용한 시간(22:00~08:00) 판정
    for h in (22, 23, 0, 7):
        assert in_ops_quiet_hours(h), f"{h}시는 조용한 시간이어야 함"
    for h in (8, 9, 21, 12):
        assert not in_ops_quiet_hours(h), f"{h}시는 조용한 시간이 아니어야 함"

    print("OK: build_done_section/build_daily_done_section/in_ops_quiet_hours — 필터·dedup·공유스냅샷·시간대 전부 통과")


if __name__ == "__main__":
    main()
