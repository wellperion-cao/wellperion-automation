# 260603 슬라이드 빌드 — 뭘 맡기고, 뭘 내가 하나: WHAT I LET AI DO (AI 시리즈 #4 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1·#2·#3과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-03 GM 직접 확정. 역할 분담편 — 반복은 AI, 결정은 사람.
#  1 표지 / 2 헷갈림 공감 / 3 쉬운 기준 한 줄 / 4 AI가 하는 일 / 5 내가 하는 일 / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직 공유. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: DM 문의 + '함께 성장합시다'(litt.ly 미사용).
# 실행: .venv\Scripts\python instagram\260603_AI4_역할분담\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260603_AI4_역할분담"
OUT = FOLDER / "output"

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 헷갈림(2) + 기준(3) + AI가 하는 일(4) + 내가 하는 일(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 헷갈림 공감 → 쉬운 기준 → AI가 하는 일 → 내가 하는 일 → 마무리 (점층)
SLIDES = [
    dict(  # 1장 표지
        kor_title="뭘 맡기고,\n뭘 내가 하나",
        eng_title="What I Let AI Do",
    ),
    dict(  # 2장 헷갈림 공감
        kor_title="처음엔 헷갈렸어요\n뭘 맡겨야 하지?",
        body="AI를 켜놓고도\n한참 망설였어요.\n이건 시켜도 되나?\n이건 내가 해야 하나?\n경계가 잘 안 보이더라고요.",
    ),
    dict(  # 3장 쉬운 기준 한 줄
        kor_title="제 기준은\n딱 하나예요",
        body="'어, 이거 또 하네?'\n싶은 일은 AI한테.\n'이건 내가 정해야지'\n싶은 일은 제가.\n반복은 AI, 결정은 저예요.",
    ),
    dict(  # 4장 AI가 하는 일 — 구체 목록
        kor_title="이런 건\nAI가 해요",
        body="· 예약 문자 초안 쓰기\n· 문의에 1차로 답하기\n· 매출 숫자 정리하기\n· 보고서 밑그림 만들기\n매일 똑같이 반복되는 일들이요.",
    ),
    dict(  # 5장 내가 하는 일 — 구체 목록
        kor_title="이런 건\n제가 해요",
        body="· 회원 얼굴·표정 살피기\n· 가격과 방향 정하기\n· 사람과의 관계 쌓기\n· 마지막으로 한 번 확인하기\n결국 '결정'은 사람 몫이니까요.",
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
    # 기존 개인계정 발행분(왜AI·AI직원효율·입문편)과 동일 처리. 풀 로고 금지.
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
        kor_title="맡길수록\n더 중요한 일만 남아요",
        body="AI한테 반복을 넘기면\n제 손엔 진짜 중요한 일만 남아요.\n완벽하진 않아도, 함께 성장합시다.\n\n운동시설 대표님, 궁금하시면\nDM 주세요. 아는 선에선 돕겠습니다.",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
