# -*- coding: utf-8 -*-
"""
2026-08-08 일괄 LOSS 처리된 문의 34건 되살리기 스크립트 (1회성 · 보관용)

근거 배: CPO-2026-08-08-장기-미컨택-문의-28건-이탈종결-일괄-정리-되살리
실행 시점: 실무진이 '되살려 달라'고 요청한 특정 건, 또는 전건을 원상복구할 때.

GM 확인사항(2026-08-08):
  - '이번에만' — 이 정리는 1회성. 자동화 규칙으로 만들지 않음.
  - '이탈' 낱말 금지 → LOSS 로 통일(이미 반영됨).

사용:
  python scripts\\cpo_loss_restore_20260808.py --all          # 전건 복원
  python scripts\\cpo_loss_restore_20260808.py --row 223      # 특정 rowIndex만
  python scripts\\cpo_loss_restore_20260808.py --row 223 459  # 복수 지정
  python scripts\\cpo_loss_restore_20260808.py --dry-run      # 실제 쓰기 없이 대상 목록만 출력
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)

# 되돌리기 원본 테이블 — rowIndex|이름|원래 상태
# 90일+ 기준 28건 (2026-08-08 1차 처리)
_RESTORE_90D = [
    (223, "최정욱",            "가망"),
    (243, "이정하",            "컨택중"),
    (244, "김애리",            "컨택중"),
    (254, "최용호",            "가망"),
    (255, "유창원",            "컨택중"),
    (257, "윤채민",            "컨택중"),
    (258, "김단우·김영진 엄마번호", "컨택중"),
    (259, "강윤희",            "가망"),
    (260, "익명여(3/9)",       "컨택중"),
    (268, "장서윤",            "컨택중"),
    (272, "denara",            "컨택중"),
    (287, "이경숙",            "컨택중"),
    (294, "안형근님 와이프",   "가망"),
    (295, "이승엽",            "컨택중"),
    (301, "조우형",            "가망"),
    (315, "Aysia Touchett",    "컨택중"),
    (320, "이한서",            "컨택중"),
    (321, "허나래",            "컨택중"),
    (331, "유소년 학부모",     "컨택중"),
    (337, "이문수님 동생(더클레식)", "가망"),
    (343, "익명여(4/1)",       "컨택중"),
    (357, "박현비",            "컨택중"),
    (358, "이경민",            "컨택중"),
    (373, "이희정",            "가망"),
    (376, "배주영",            "컨택중"),
    (409, "김애남",            "컨택중"),
    (418, "박진숙",            "가망"),
    (422, "로렌조",            "컨택중"),
]

# 30일+ 기준 6건 추가 (2026-08-08 2차 처리, GM 기준 변경)
_RESTORE_30D = [
    (459, "박현미",  "컨택중"),
    (494, "고주현",  "컨택중"),
    (499, "박은숙",  "컨택중"),
    (534, "김문",    "컨택중"),
    (554, "김주영1", "가망"),
    (587, "채우리",  "컨택중"),
]

ALL_CASES: list[tuple[int, str, str]] = _RESTORE_90D + _RESTORE_30D  # 총 34건


def _gas_call(row_index: int, orig_status: str, dry_run: bool) -> bool:
    """GAS member_inquiry_update 로 진행상태 원상복구 + lossReason 클리어."""
    params = {
        "action": "member_inquiry_update",
        "rowIndex": str(row_index),
        "status": orig_status,
        "lossReason": "",   # 일괄 정리 사유 제거
    }
    if dry_run:
        print(f"  [DRY] row={row_index} status={orig_status}")
        return True
    try:
        r = requests.get(FUNNEL_EXEC_URL, params=params, timeout=40, allow_redirects=True)
        r.encoding = "utf-8"
        data = r.json()
        ok = data.get("ok") is True
        print(f"  row={row_index} {'OK' if ok else 'FAIL'} — {data.get('error') or orig_status}")
        return ok
    except Exception as e:
        print(f"  row={row_index} ERROR — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="2026-08-08 LOSS 일괄처리 되살리기")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="34건 전건 복원")
    group.add_argument("--row", nargs="+", type=int, metavar="ROW_INDEX", help="특정 rowIndex 지정")
    parser.add_argument("--dry-run", action="store_true", help="실제 쓰기 없이 대상 목록만 출력")
    args = parser.parse_args()

    lookup = {row: (name, status) for row, name, status in ALL_CASES}

    if args.all:
        targets = ALL_CASES
    else:
        targets = []
        for ri in args.row:
            if ri not in lookup:
                print(f"[WARN] row={ri} 는 이 스크립트의 되살리기 목록에 없음 — 건너뜀")
                continue
            name, status = lookup[ri]
            targets.append((ri, name, status))

    print(f"복원 대상 {len(targets)}건 {'[DRY-RUN]' if args.dry_run else ''}")
    print("-" * 50)

    ok_count = fail_count = 0
    for row, name, status in targets:
        print(f"  {row} {name} → {status}")
        success = _gas_call(row, status, args.dry_run)
        if success:
            ok_count += 1
        else:
            fail_count += 1
        if not args.dry_run:
            time.sleep(0.5)  # GAS 부하 방지

    print("-" * 50)
    print(f"완료: 성공 {ok_count} / 실패 {fail_count} / 전체 {len(targets)}")
    if fail_count > 0:
        print("[주의] 실패 건은 membership.html 에서 직접 수동 변경 필요")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
