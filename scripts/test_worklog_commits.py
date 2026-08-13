# -*- coding: utf-8 -*-
"""worklog._commits_between 검사 — 자동종결이 「한 것」 칸을 채우는 근거가 되는 함수.

왜 검사가 필요한가: 이 저장소는 세션 5개가 같은 시각에 커밋한다. 시각만으로 자르면 남의
커밋이 내 칸에 붙는다 — 빈칸보다 나쁘다(GM 이 남의 일을 내 일로 읽는다). 역할 태그 필터와
기계 발행 커밋 제외가 살아 있는지만 본다.

실행: C:/Python314/python.exe scripts/test_worklog_commits.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import worklog as w  # noqa: E402

# 역할을 안 주면 아무것도 돌려주지 않는다 — 남의 커밋을 붙이느니 빈칸이 낫다.
assert w._commits_between("2026-08-13T00:00:00+09:00", "", "") == ""
assert w._commits_between("", "", "cto") == ""

# 미래 구간은 커밋이 없다.
assert w._commits_between("2099-01-01T00:00:00+09:00", "", "cto") == ""

# 같은 구간이라도 역할이 다르면 결과가 달라야 한다(태그 필터가 살아 있다는 뜻).
lo, hi = "2026-08-13T00:00:00+09:00", "2026-08-14T00:00:00+09:00"
a, b = w._commits_between(lo, hi, "cto"), w._commits_between(lo, hi, "cpo")
assert a and b and a != b, (a, b)

# 기계가 주기적으로 내는 발행 커밋은 「한 것」이 아니다.
assert "자동 발행" not in a and "자동 발행" not in b

# 같은 제목이 두 번 나오지 않는다.
for out in (a, b):
    parts = [p.strip() for p in out.split(" · ")]
    assert len(parts) == len(set(parts)), out

print("OK — worklog._commits_between 5개 검사 통과")
