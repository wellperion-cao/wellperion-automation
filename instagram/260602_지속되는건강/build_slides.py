# 260602 슬라이드 빌드 — 지속되지 않으면 그건 건강이 아니다 (GM 개인 계정 namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 5장: 1장 표지 + 2~4장 본문 + 5장 슬로건/다짐 카드(문의 CTA)
# 톤: 1인칭 신념·생각 리더십 (회원 모집 마케팅 톤 금지)
# CTA: "문의: litt.ly/wellperion" 단일 (GM 지시)
# 실행: .venv\Scripts\python instagram\260602_지속되는건강\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260602_지속되는건강"
OUT = FOLDER / "output"
CTA = "문의: litt.ly/wellperion"

# 표지(1장) + 본문(2~4장) — compose_text_slide 분기:
#  eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body 본문)
SLIDES = [
    dict(  # 1장 표지
        kor_title="지속되지 않으면,\n그건 건강이 아니다",
        eng_title="Health That Lasts",
    ),
    dict(  # 2장 흔한 실패 — 공감
        kor_title="작심삼일은\n의지의 문제가 아니다",
        body="한 달 독하게 운동해서\n3kg을 뺀다.\n그리고 두 달 뒤,\n다시 제자리로 돌아온다.\n문제는 의지가 아니라,\n'지속될 수 없는 방식'이었다.",
    ),
    dict(  # 3장 통념 반박
        kor_title="빠르게 바뀐 몸은\n빠르게 돌아간다",
        body="단기 성과는 사진엔 남지만\n삶엔 남지 않는다.\n진짜 중요한 건\n'얼마나 뺐는가'가 아니라\n'얼마나 오래 유지되는가'다.",
    ),
    dict(  # 4장 진짜 정의 + 환경
        kor_title="지속되는 건강은\n환경에서 나온다",
        body="의지에 기대지 않는다.\n매일 가고 싶은 공간,\n무리 없이 쌓이는 습관,\n같이 가는 사람들.\n환경이 사람을 바꾼다.",
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

    # 5장 = 슬로건/다짐 카드 + 문의 CTA (GM 지시: 문의 litt.ly/wellperion 단일)
    slogan_out = OUT / "post_5.jpg"
    r = compose_text_slide(
        output=slogan_out,
        brand_key="main",
        kor_title="지속되지 않는 건강 문제를\n해결한다",
        body="그게 제가 이 일을 하는 이유입니다.\n반짝이 아니라, 10년 뒤에도\n유지되는 건강을 함께 만들고 싶어요.",
        footer_meta=CTA,
    )
    print(f"[OK] post_5.jpg - slogan card ({r['size_kb']}KB)")
    paths.append(slogan_out)

    montage = OUT / "_검수_미리보기_5장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
