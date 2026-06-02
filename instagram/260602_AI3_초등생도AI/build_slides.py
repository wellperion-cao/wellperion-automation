# 260602 슬라이드 빌드 — 복잡한 건 빼고 핵심만: HOW I USE AI (AI 시리즈 #3 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1·#2와 통일 = 정확히 5장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 사양: .omc/specs/deep-interview-ai3-claude-intro.md (2026-06-02 GM deep-interview PASSED)
#  1 표지 / 2 ①범용가이드(Claude로 시작) / 3 ②웰페리온 사례(AI 직원) / 4 ③따라하기 / 5 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직 공유('내가 쓰는 도구' 프레임, 광고 아님). Claude 직접 명시 OK.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: DM 문의 + '함께 성장합시다'(litt.ly 미사용).
# 실행: .venv\Scripts\python instagram\260602_AI3_초등생도AI\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260602_AI3_초등생도AI"
OUT = FOLDER / "output"

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 5장 — 표지(1) + ①②③(2~4, 각 1장) + 마무리/CTA(5, main() 별도 처리)
SLIDES = [
    dict(  # 1장 표지
        kor_title="복잡한 건 빼고,\n핵심만",
        eng_title="How I Use AI",
    ),
    dict(  # 2장 ① 범용 가이드 — Claude로 시작 (가장 쉬운 첫 사용, 구체 사례)
        kor_title="AI 처음이면 Claude부터\n나는 이렇게 시작했다",
        body="거창하게 안 했어요.\n클로드(Claude)에 말 걸듯 적었죠.\n\"이 문자 정중하게 고쳐줘\"\n\"오늘 할 일 좀 정리해줘\"\n딱 이거 두 개부터였어요.",
    ),
    dict(  # 3장 ② 웰페리온 실제 사례 — AI 직원(C-Level) 만든 솔직 사례
        kor_title="우리는 AI 직원을\n만들었어요",
        body="익숙해지니 욕심이 생겼어요.\n그래서 'AI 직원'부터 만들었죠.\n문의 답변, 숫자 정리, 보고서를\n맡는 AI 담당자들이에요.\n사람은 결정에만 집중하면 되니까요.",
    ),
    dict(  # 4장 ③ 따라하기 — 실천 유도 (쉬운 버전, AI직원 셋업 강요 아님)
        kor_title="당신도 오늘\n이렇게 시작해보세요",
        body="AI 직원까지 안 만들어도 돼요.\n오늘 가장 귀찮았던 일 하나,\n클로드한테 말로 시켜보세요.\n\"이거 대신 정리해줘\"부터요.\n그거면 충분한 첫걸음이에요.",
    ),
]


def build_montage(paths: list[Path], out_path: Path, cols: int = 3) -> None:
    """전체 슬라이드를 1장으로 합성한 검수 미리보기 (cols x rows 그리드)."""
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

    # 개인계정(namuk.wellperion) = 'W' 심볼만 미니멀 로고 (2026-06-02 GM 결정)
    # 기존 개인계정 발행분(왜AI·AI직원효율)과 동일 처리. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 슬로건 + 같이 성장 + DM 유도 (GM 사양)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="AI를 다루는 대표가\n살아남는다",
        body="저도 아직 배우는 중입니다.\n완벽하진 않아도, 함께 성장합시다.\n\nAI 활용이 궁금한 운동시설 대표님,\nDM으로 문의 주세요.",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
