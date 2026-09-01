# -*- coding: utf-8 -*-
"""주간 페이지 위생 감사의 자동삭제 게이트 검사 (배507).

이 게이트가 틀리면 **실무진이 쓰는 기능이 조용히 지워진다.** 그래서 검사를 남긴다.
검사하는 것은 하나 — "지워도 되나"를 판정하는 verify_zero_consumers 가
① 살아 있는 함수를 죽었다고 하지 않는가 ② 못 찾은 것을 없다고 하지 않는가.

실행: C:/Python314/python.exe scripts/test_page_hygiene_gate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weekly_page_hygiene import verify_zero_consumers  # noqa: E402

LEAVE = "3. 웰페리온 가이드/chro/hub/leave.html"

# ① 살아 있는 함수 — 같은 파일에서 3곳이 부른다. 절대 자동삭제로 판정되면 안 된다.
live = verify_zero_consumers("usedAnnual2026", LEAVE)
assert live["zero"] is False, f"살아있는 함수를 죽은 코드로 판정했다: {live}"
assert live["match_count"] > 1, live

# ② 아예 없는 이름 — 선언조차 안 잡히면 '없다'가 아니라 '못 찾았다'로 본다(안전측).
#    ★이름을 실행 시점에 조립한다(2026-09-01 배871) — 리터럴로 적으면 이 테스트 파일
#    자체가 git grep 에 잡혀(추적 파일) match_count=1 이 되어 ②분기를 영영 못 탄다.
ghost = verify_zero_consumers("이름이없는함수_zzz_" + "존재하지않음", LEAVE)
assert ghost["zero"] is False, f"못 찾은 것을 자동삭제 가능으로 판정했다: {ghost}"
assert ghost["match_count"] == 0, ghost

# ③ 빈 이름 — 판정 자체를 거부한다.
empty = verify_zero_consumers("", LEAVE)
assert empty["zero"] is False, empty

print("OK — 페이지 위생 게이트 3개 검사 통과")
