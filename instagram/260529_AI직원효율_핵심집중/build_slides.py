# 시드 #09 슬라이드 빌드 — AI가 일하고 사람은 결정한다 (GM 개인 계정 namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 1~4장 = compose_text_slide 생성, 5장 = 기성 guideline_card.jpg 복사
# 실행: .venv\Scripts\python instagram\260529_AI직원효율_핵심집중\build_slides.py
import shutil
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260529_AI직원효율_핵심집중"
OUT = FOLDER / "output"
GUIDE_CARD = ROOT / "instagram" / "_assets" / "guideline_card.jpg"

# 1~4장 카피 (기획_초안.md 기반)
SLIDES = [
    dict(  # 1장 표지
        kor_title="AI가 일하고, 사람은 결정한다",
        eng_title="Let AI Work. You Decide.",
    ),
    dict(  # 2장 문제
        kor_title="하루의 80%가\n반복에 사라진다",
        body="집계하고, 정리하고, 보고하고,\n복사·붙여넣기.\n정작 '판단'할 시간이 남지 않는다.",
    ),
    dict(  # 3장 전환
        kor_title="반복은 AI에게,\n핵심은 사람에게",
        body="AI = 수집·집계·초안·보고\n사람 = 판단·결정·관계\n역할을 나누면, 사람은\n가장 중요한 일만 한다.",
    ),
    dict(  # 4장 실제 사례
        kor_title="웰페리온은\nAI 7명이 일한다",
        body="AI 임원 7명이 자동화·집계·보고를 맡는다.\n사람은 한눈에 파악하고, 결정만 내린다.\n이것이 우리가 매일 일하는 방식이다.",
    ),
    dict(  # 5장 마무리 — 1장과 짝이 되는 마무리(개인 톤, 회사 가이드 카드 아님)
        kor_title="핵심에 집중하는 하루",
        eng_title="A Day, Well Completed.",
    ),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # 구 산출물 폐기 (버전업 시 이전 데이터 폐기 원칙)
    for old in OUT.glob("post_A_*"):
        old.unlink()

    results = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_A_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", **slide)
        results.append(r)
        print(f"[OK] {out.name} — {r['layout']} ({r['size_kb']}KB)")

    # 5장 = 마무리 텍스트 슬라이드(개인 톤). 회사 WELLPERION GUIDE 카드는 개인 계정 제외.
    print(f"\n총 {len(results)}장 생성 완료 → {OUT}")


if __name__ == "__main__":
    main()
