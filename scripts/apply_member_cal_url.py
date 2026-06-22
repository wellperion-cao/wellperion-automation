"""
apply_member_cal_url.py
문의회원.html 내 __MEMBER_CAL_GAS_URL__ 자리표시자를 실제 GAS 배포 URL로 일괄 치환.

사용법:
    python scripts/apply_member_cal_url.py <GAS_EXEC_URL>

예시:
    python scripts/apply_member_cal_url.py "https://script.google.com/macros/s/AKf.../exec"

치환 후 자리표시자 잔여 개수를 출력. 0이면 완전 치환 성공.
"""

import sys
import re

TARGET = "3. 웰페리온 가이드/cpo/member/문의회원.html"
PLACEHOLDER = "__MEMBER_CAL_GAS_URL__"


def main():
    if len(sys.argv) < 2:
        print("오류: GAS 배포 URL을 인자로 전달하세요.")
        print("  사용법: python scripts/apply_member_cal_url.py <GAS_EXEC_URL>")
        sys.exit(1)

    gas_url = sys.argv[1].strip()
    if not gas_url.startswith("https://"):
        print(f"오류: URL이 https://로 시작하지 않습니다 — '{gas_url}'")
        sys.exit(1)

    with open(TARGET, encoding="utf-8") as f:
        content = f.read()

    before_count = content.count(PLACEHOLDER)
    if before_count == 0:
        print("자리표시자가 없습니다. 이미 치환된 상태이거나 파일을 확인하세요.")
        sys.exit(0)

    replaced = content.replace(PLACEHOLDER, gas_url)
    after_count = replaced.count(PLACEHOLDER)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(replaced)

    print(f"치환 완료: {before_count}곳 → 잔여 {after_count}곳")
    if after_count > 0:
        print(f"  경고: 자리표시자 {after_count}곳이 남아 있습니다. 파일을 수동 확인하세요.")
        sys.exit(1)
    else:
        print(f"  대상 파일: {TARGET}")
        print(f"  적용 URL: {gas_url}")
        print("ALL_PASS")


if __name__ == "__main__":
    main()
