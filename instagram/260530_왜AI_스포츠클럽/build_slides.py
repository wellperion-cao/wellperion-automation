# 260530 슬라이드 빌드 — 왜 스포츠클럽 일에 AI를 쓰는가 (GM 개인 계정 namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 5장: 1장 표지 + 2~4장 본문(실제 운영 방식 기반) + 5장 WELLPERION GUIDE 카드
# 미구현 기능(새벽 자동응대·회원이탈 숫자정리) 카피 전면 제거
# 실행: .venv\Scripts\python instagram\260530_왜AI_스포츠클럽\build_slides.py
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260530_왜AI_스포츠클럽"
OUT = FOLDER / "output"
GUIDE_CARD = ROOT / "instagram" / "_assets" / "guideline_card.jpg"

# 5장 카피 — SEED09 흐름 차용, 주제: 스포츠클럽 왜 AI인가
# 미구현 기능(자동 응대·회원이탈 숫자정리) 단정 표현 제거
# 실제로 하는 것(반복 AI·사람은 회원·관계·판단 집중)만 사실대로
SLIDES = [
    dict(  # 1장 표지
        kor_title="스포츠클럽을 운영하며,\n나는 왜 AI를 쓰는가",
        eng_title="Why I Use AI",
    ),
    dict(  # 2장 현장 문제 → 전환 선언
        kor_title="현장은 늘\n사람이 부족했다",
        body="예약을 받고, 문의에 답하고,\n매출을 집계하고, 보고서를 쓰다 보면\n정작 회원의 얼굴을 볼\n시간이 줄어든다.\n그래서 나는 AI에게 일을 맡겼다.",
    ),
    dict(  # 3장 반복은 AI에, 사람은 핵심에
        kor_title="반복은 AI에게,\n핵심은 사람에게",
        body="기술이 멋져서가 아니다.\n사람이 해야 할 일을 지키기 위해서다.\nAI = 집계·정리·보고\n사람 = 회원·관계·판단·결정",
    ),
    dict(  # 4장 사람다운 일에 집중
        kor_title="AI가 반복을 가져갈수록\n사람은 더 사람다운 일을 한다",
        body="현장에서 눈을 맞추고, 관계를 쌓는 일.\n그건 끝까지 사람의 몫이다.\n나는 AI를 도구로 쓴다.\n회원에게 더 집중하기 위해서.",
    ),
]


def build_montage(paths: list[Path], out_path: Path, cols: int = 3) -> None:
    """5장을 1장으로 합성한 검수 미리보기 (cols x rows 그리드)."""
    thumbs = [Image.open(p).convert("RGB") for p in paths]
    tw, th = thumbs[0].size
    scale = 0.5
    cw, chh = int(tw * scale), int(th * scale)
    gap = 18
    bg = (24, 22, 23)
    rows = (len(thumbs) + cols - 1) // cols
    canvas_w = cols * cw + (cols + 1) * gap
    canvas_h = rows * chh + (rows + 1) * gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = gap + c * (cw + gap)
        y = gap + r * (chh + gap)
        canvas.paste(t.resize((cw, chh), Image.LANCZOS), (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # 구 산출물 폐기 (버전업 시 이전 데이터 폐기 원칙)
    for old in OUT.glob("post_*"):
        old.unlink()
    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 5장 = 슬로건 카드 (GM 지시: GUIDE 카드 → 슬로건+DM CTA 교체, litt.ly 삭제)
    slogan_out = OUT / "post_5.jpg"
    r = compose_text_slide(
        output=slogan_out,
        brand_key="main",
        kor_title="AI를 다루는 대표가\n살아남는다",
        body="솔직히 저도 아직 부족하고, 배우는 중입니다.\n완벽하진 않아도 같이 성장하고 싶어요.\n\nAI 활용이 궁금한 운동시설 대표님,\n부담없이 DM 주세요",
    )
    print(f"[OK] post_5.jpg - slogan card ({r['size_kb']}KB)")
    paths.append(slogan_out)

    montage = OUT / "_검수_미리보기_5장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
