"""새 접수의 부서 → 카톡 방 라우팅이 11개 부서 체계에서 맞는지 검사한다.

배경(2026-08-17 시토): 부서 구분이 3개에서 11개로 늘면서 `_intake_room_for` 의 「강습」
문자열 판정이 죽었다 — 새 11개 값 중 「강습」을 품은 것이 하나도 없어, GM 이 2026-08-15 에
확정한 「강습·업장 = ★부서장 방」 라우팅이 통째로 기본 방으로 새고 있었다.

실행: C:/Python314/python.exe scripts/test_intake_room_routing.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_stream_2b_reception import (  # noqa: E402
    _INTAKE_ROOM_DEFAULT,
    _INTAKE_ROOM_LESSON,
    _intake_room_for,
)

# 종합접수처_현황.html DEPT_LIST 와 같은 11개 (GM 확정 2026-08-15)
TO_DEPT_HEAD = ["수영팀", "P.T팀", "골프팀", "스쿼시팀", "체조팀", "뮤지컬팀", "루프메소드팀"]
TO_DEFAULT = ["운영부", "시설부", "지원부(남)", "지원부(여)"]


def main() -> int:
    for d in TO_DEPT_HEAD:
        got = _intake_room_for(d)
        assert got == _INTAKE_ROOM_LESSON, f"{d} 는 부서장 방이어야 하는데 {got} 로 갔다"

    for d in TO_DEFAULT:
        got = _intake_room_for(d)
        assert got == _INTAKE_ROOM_DEFAULT, f"{d} 는 기본 방이어야 하는데 {got} 로 갔다"

    # 옛 값 호환 — 「강습」이 들어간 부서명은 계속 부서장 방
    assert _intake_room_for("강습") == _INTAKE_ROOM_LESSON
    assert _intake_room_for(" 수영팀 ") == _INTAKE_ROOM_LESSON  # 앞뒤 공백
    # 빈 값·미정은 기본 방(발신 자체가 끊기면 안 된다)
    assert _intake_room_for("") == _INTAKE_ROOM_DEFAULT
    assert _intake_room_for(None) == _INTAKE_ROOM_DEFAULT

    print(f"OK — 업장 {len(TO_DEPT_HEAD)}개는 {_INTAKE_ROOM_LESSON}, "
          f"나머지 {len(TO_DEFAULT)}개는 {_INTAKE_ROOM_DEFAULT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
