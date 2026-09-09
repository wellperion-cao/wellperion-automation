# -*- coding: utf-8 -*-
"""GM업무 화면 체크 키 재현 검사 (2026-09-09 · GM 지시 "지시한 내용들도 놓치지않게 체크").

gm_aide_scan._check_hash 는 GM업무.html 의 chkKey() 해시를 파이썬으로 옮긴 것이다.
둘이 어긋나면 아침 표 ⑫지시미체크가 GM 이 이미 끈 줄을 매일 다시 올린다 —
조용히 틀리는 자리라 실제 보드에 살아 있는 키 두 개를 고정해 둔다.
값의 출처 = 2026-09-09 GM_TASK_CHECKS 보드 실측(화면에서 GM 이 직접 누른 항목).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gm_aide_scan import _check_hash  # noqa: E402


def test_hash_matches_screen_keys():
    assert _check_hash("일일 입장객 보고 — 8/12부 중단, 9/1 재개 (d13)") == "1ecb5kw"
    assert _check_hash("결제 시스템·매출 보고 9/1 브로제이 전환 (d15)") == "1e4bq0d"


def test_whitespace_normalized():
    # 들여쓰기·연속 공백이 달라도 같은 줄이면 같은 키(화면 chkKey 와 같은 정규화).
    assert _check_hash("  일일 입장객 보고 — 8/12부  중단, 9/1 재개 (d13) ") == \
        _check_hash("일일 입장객 보고 — 8/12부 중단, 9/1 재개 (d13)")


if __name__ == "__main__":
    test_hash_matches_screen_keys()
    test_whitespace_normalized()
    print("OK")
