# 접수 백엔드 갈래 검사 — 분리 백엔드(.deploy-intake/Intake.js)의 intake_submit 이
# 원본(.deploy-funnel-v2/Survey.js)과 같은지 본다.
#
# 왜 있나: 2026-08-06 에 접수만 떼어 낸 작은 백엔드를 세웠는데(왕복 2.42초 → 1.49초),
#   그 다음 날 원본에 '오넛티 선물세트' 접수 유형이 새로 들어갔고 분리본에는 안 들어갔다.
#   그 상태로 화면 주소를 갈아끼웠으면 그 유형 접수가 통째로 죽는다 — 화면은 정상으로 보이고
#   고객만 접수가 안 된다. 갈래는 조용히 벌어지므로 기계가 본다.
#
# 실행: C:\Python314\python.exe scripts/tests/test_intake_parity.py
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".deploy-funnel-v2" / "Survey.js"
FORK = ROOT / ".deploy-intake" / "Intake.js"
START = "if (action === 'intake_submit')"
ENDS = ("if (action === 'staff_feedback_submit')", "return _json({ ok: false, error: '알 수 없는 action: '")


def block(path: Path) -> list[str]:
    s = path.read_text(encoding="utf-8")
    i = s.index(START)
    j = min([k for k in (s.find(e, i) for e in ENDS) if k > 0])
    return s[i:j].strip().splitlines()


def main() -> int:
    diff = list(difflib.unified_diff(block(SRC), block(FORK), "Survey.js(원본)", "Intake.js(분리본)", lineterm="", n=0))
    if not diff:
        print("접수 로직 일치 — 갈래 없음")
        return 0
    print(f"접수 로직이 갈렸습니다 — 차이 {len(diff)}줄")
    print("\n".join(diff[:60]))
    print("\n고치는 법: 원본의 intake_submit 블록을 분리본으로 그대로 옮기고, 새로 부르는 헬퍼가 있으면 같이 옮긴다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
