# -*- coding: utf-8 -*-
"""send_ops_digest.build_done_section() 자체 점검 — 실 GAS 호출 없음(fake rows).

확인: ①운영부 아닌 담당자·미완료 건 제외 ②새로 완료된 건만 절에 실림
③지난 회차와 완료건이 같으면 절 없음(빈 문자열) ④id 로 dedup(업무명 바뀌어도 재알림 안 함).
실행: C:\\Python314\\python.exe tests/test_ops_digest_done_section.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from send_ops_digest import build_done_section  # noqa: E402

ROWS = [
    {"id": "1", "업무명": "주차 라인 도색", "담당자": "최준용M", "상태": "완료"},
    {"id": "2", "업무명": "냉방기 점검", "담당자": "이경연 실장", "상태": "완료"},
    {"id": "3", "업무명": "예산안 검토", "담당자": "나우열M", "상태": "완료"},   # 운영부 아님 — 제외
    {"id": "4", "업무명": "락커 정리", "담당자": "윤병현AM", "상태": "진행중"},  # 미완료 — 제외
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

    print("OK: build_done_section — 필터·dedup·재알림 억제 전부 통과")


if __name__ == "__main__":
    main()
