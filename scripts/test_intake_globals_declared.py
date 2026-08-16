"""분리 백엔드(Intake.js)가 쓰는 전역 상수가 그 파일에 실제로 선언돼 있는지 검사한다.

배경(2026-08-17 시토): 원본(.deploy-funnel-v2/Survey.js)에서 오넛티 접수를 이식할 때
**함수만 옮기고 상수 셋(OHNUTTI_INTAKE_SHEET_NAME·OHNUTTI_INTAKE_HEADERS·OHNUTTI_CAP)을
빠뜨렸다.** 참조는 있고 선언이 없으니 그 유형 접수가 들어오는 순간 ReferenceError 가 나고
catch 에 잡혀 "서버 저장 오류"로 매번 실패한다 — 그런데 응답은 200 이라 아무 경보도 안 울린다.

기존 대조 검사(scripts/tests/test_intake_parity.py)는 intake_submit **함수 본문**만 비교해서
함수 밖 상수 누락을 구조적으로 못 잡는다. 이 검사가 그 사각지대를 메운다.

판정 범위를 좁혀 오탐을 없앤다: **원본에 `var X =` 로 선언된 이름**만 대상으로 본다.
Script Properties 키(`_prop('TELEGRAM_...')`)처럼 문자열로만 쓰이는 이름은 원본에도 선언이
없으므로 애초에 걸리지 않는다 — 정교한 JS 파서 없이 실제 사각지대만 정확히 덮는다.

실행: C:/Python314/python.exe scripts/test_intake_globals_declared.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTAKE = ROOT / ".deploy-intake" / "Intake.js"
ORIGIN = ROOT / ".deploy-funnel-v2" / "Survey.js"

# 최상위(들여쓰기 없는) 대문자 상수 선언만 본다 — 함수 안 지역변수는 대상이 아니다.
DECL = re.compile(r"^(?:var|let|const)\s+([A-Z][A-Z0-9_]{3,})\s*=", re.M)


def _strip_noise(src: str) -> str:
    """주석과 문자열 리터럴을 걷어낸다 — 거기 적힌 이름은 참조가 아니다."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"(?<!:)//[^\n]*", " ", src)       # URL 의 '://' 는 건드리지 않는다
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", src)
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)
    return src


def main() -> int:
    intake = INTAKE.read_text(encoding="utf-8")
    origin = ORIGIN.read_text(encoding="utf-8")

    origin_decl = set(DECL.findall(origin))
    intake_decl = set(DECL.findall(intake))
    intake_code = _strip_noise(intake)
    used = set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", intake_code))

    # 원본이 최상위 상수로 선언해 둔 이름 중, Intake.js 가 코드에서 쓰면서 선언은 안 한 것
    missing = sorted((origin_decl & used) - intake_decl)

    if missing:
        print("선언 없이 쓰이는 전역 — 그 경로는 실행 즉시 ReferenceError 로 죽는다:")
        for name in missing:
            line = next((i + 1 for i, ln in enumerate(intake.splitlines()) if name in ln), "?")
            print(f"  · {name}  (첫 사용 {INTAKE.name}:{line})")
        print(f"\n원본 {ORIGIN.name} 에서 같은 이름의 선언을 그대로 이식하세요.")
        return 1

    print(f"OK — 원본 선언 {len(origin_decl)}개 대비 누락 0 ({INTAKE.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
