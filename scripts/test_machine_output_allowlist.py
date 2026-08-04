"""_is_machine_output 허용목록 자가검사 (시토 2026-08-04).

이 검사가 지키는 것 = 5분 스위퍼가 **무엇을 자동 커밋해도 되는지**의 경계다.
경계를 잘못 넓히면 사람이 편집 중인 파일이 자동 커밋되고, 잘못 좁히면
브리프처럼 만들어만 지고 GM 화면까지 못 가는 파일이 다시 생긴다.

실행: C:/Python314/python.exe scripts/test_machine_output_allowlist.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_commit_push import _is_machine_output  # noqa: E402

ALLOWED = [
    "status/briefs/CMO-daily-feedback-20260803.md",   # 예약작업이 만드는 C-Level 브리프
    "status/morning_plans/2026-08-04.json",           # 아침 항로 근거
    "status/heartbeats/cpo-inquiry-snapshot.json",    # 기존 동작(회귀 방지)
    "status/erp_status.json",                         # 기존 개별 허용 항목
]
ALLOWED.append("status/_queue.json")  # 기존 항목 — 도구만 쓰는 배 원장(647~653줄 근거)

BLOCKED = [
    "scripts/post_commit_push.py",         # 코드
    "3. 웰페리온 가이드/wellperion_guide(main).html",  # 사람이 보는 화면
    "ssot/약속.json",                       # 공유 약속
    "status/briefs",                       # 폴더 자체(접두사 오탐 방지 — 슬래시 필요)
]

if __name__ == "__main__":
    for p in ALLOWED:
        assert _is_machine_output(p), f"허용돼야 하는데 막힘: {p}"
    for p in BLOCKED:
        assert not _is_machine_output(p), f"막혀야 하는데 통과: {p}"
    print(f"OK — 허용 {len(ALLOWED)}건 · 차단 {len(BLOCKED)}건 전부 기대대로")
