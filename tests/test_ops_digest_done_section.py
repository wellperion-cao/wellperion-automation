# -*- coding: utf-8 -*-
"""send_ops_digest.build_done_section() 자체 점검 — 실 GAS 호출 없음(fake rows).

확인: ①운영부 아닌 담당자·미완료 건 제외 ②새로 완료된 건만 절에 실림
③지난 회차와 완료건이 같으면 절 없음(빈 문자열) ④id 로 dedup(업무명 바뀌어도 재알림 안 함)
⑤즉각 알림·아침 다이제스트가 같은 스냅샷을 공유하면 같은 건을 두 번 안 보냄(배431·GM 2026-08-06)
⑥하루 일과 정리(build_daily_done_section)는 날짜로만 거르고 중복억제가 없음
⑦조용한 시간(22:00~08:00) 판정.
⑧주간 보고 초안(build_weekly_report_draft) — ②진행중·③멈춤(기한초과/무갱신)·✅이번주완료
분류 및 보류·타부서 제외(배431 후속, GM 2026-08-06).
실행: C:\\Python314\\python.exe tests/test_ops_digest_done_section.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from send_ops_digest import (  # noqa: E402
    build_done_section, build_daily_done_section, in_ops_quiet_hours,
    build_weekly_report_draft,
)

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


WEEKLY_ROWS = [
    # ②진행 중 — 상태=진행중·기한 안 지남(2026-08-10)·최근 갱신(1일전)
    {"id": "20", "업무명": "락커 유지보수", "담당자": "최준용M", "상태": "진행중",
     "종료일": "2026-08-10", "수정일": "2026-08-05"},
    # ③멈춤(기한 초과) — 종료일이 오늘(2026-08-06)보다 과거
    {"id": "21", "업무명": "주차 라인 재도색", "담당자": "이경연 실장", "상태": "진행중",
     "종료일": "2026-08-01", "수정일": "2026-08-05"},
    # ③멈춤(무갱신 7일+) — 기한은 안 지났지만 수정일이 17일 전
    {"id": "22", "업무명": "냉방기 부품 발주", "담당자": "윤병현AM", "상태": "진행중",
     "종료일": "2026-08-20", "수정일": "2026-07-20"},
    # ③멈춤(수정일 없음) — 무갱신 취급
    {"id": "23", "업무명": "누수 재점검", "담당자": "최준용M", "상태": "진행중", "종료일": "2026-08-15"},
    # 보류 — ②③ 어디에도 안 실림
    {"id": "24", "업무명": "예산 보류 건", "담당자": "이경연 실장", "상태": "보류",
     "종료일": "2026-07-01", "수정일": "2026-07-01"},
    # 타부서 담당 — 제외
    {"id": "25", "업무명": "예산안 검토", "담당자": "나우열M", "상태": "진행중",
     "종료일": "2026-08-10", "수정일": "2026-08-05"},
    # ✅이번 주 완료(주 시작=2026-08-03 월요일, 08-04는 이번 주)
    {"id": "26", "업무명": "누수 점검", "담당자": "최준용M", "상태": "완료", "수정일": "2026-08-04"},
    # 완료지만 지난주 — 이번 주 절에서 제외
    {"id": "27", "업무명": "락커 교체", "담당자": "이경연 실장", "상태": "완료", "수정일": "2026-07-30"},
]


def test_build_weekly_report_draft() -> None:
    draft = build_weekly_report_draft(WEEKLY_ROWS, "2026-08-06")

    assert "② 진행 중 1건" in draft, draft
    assert "락커 유지보수 / 최준용M / 2026-08-10" in draft, draft

    assert "③ 멈춰 있는 것 3건" in draft, draft
    assert "주차 라인 재도색 / 이경연 실장 / 기한 5일 초과" in draft, draft
    assert "냉방기 부품 발주 / 윤병현AM / 17일째 무갱신" in draft, draft
    assert "누수 재점검 / 최준용M / 갱신기록 없음" in draft, draft

    assert "✅ 이번 주 끝난 것 1건" in draft, draft
    assert "누수 점검 — 최준용M" in draft, draft
    assert "락커 교체" not in draft, "지난주 완료건이 이번 주 절에 새어나옴"

    assert "예산 보류 건" not in draft, "보류 건이 ②③에 새어나옴"
    assert "예산안 검토" not in draft, "타부서 담당자가 새어나옴"
    assert "👉 멈춘 건은" in draft, "멈춤 정리 안내 누락"

    assert build_weekly_report_draft([], "2026-08-06") == "", "빈 입력인데 초안이 생성됨"

    print("OK: build_weekly_report_draft — ②③✅ 분류·보류/타부서 제외·이번 주 필터 전부 통과")


if __name__ == "__main__":
    main()
    test_build_weekly_report_draft()
