# 260604 슬라이드 빌드 — AI를 쓰며 깨진 환상들: WHAT I GOT WRONG ABOUT AI (AI 시리즈 #5 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1·#2·#3·#4와 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-04 AI CMO 초안. 한계·오해 정정편 — 시키는 법이 실력이다.
#  1 표지 / 2 처음 기대·환상 공감 / 3 깨진 지점(시키는 법 모르면 멈춤) / 4 오해 사례 / 5 배운 것(사람의 몫) / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직 고백. 실패·오해 진솔 공유. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 함께 성장합시다 + DM 주세요(litt.ly 미사용).
# 실행: .venv\Scripts\python instagram\260604_AI5_깨진환상들\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260604_AI5_깨진환상들"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-04-AI5-깨진환상들"
QUEUE_TITLE = "AI #5편 — 깨진 환상들(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "AI를 쓰며 깨진 환상들 — 솔직하게 털어놓을게요.\n\n"
    "처음엔 AI를 켜면 뭐든 다 될 줄 알았어요. 말만 하면 알아서 척척 해줄 거라고.\n\n"
    "그 기대가 하나씩 깨졌어요.\n"
    "\"알아서 찾아줄 거야\" → 안 찾아요. 내가 줘야 찾아요.\n"
    "\"한 번에 완성될 거야\" → 여러 번 다듬어요.\n"
    "\"내 상황을 알겠지\" → 매번 설명해야 해요.\n\n"
    "깨닫고 보니, AI는 잘 시켜야 잘 움직이는 도구예요.\n"
    "막연하게 시키면 막연하게 답하고, 구체적으로 시키면 구체적으로 움직여요.\n"
    "맥락을 주고, 기준을 알려주고, 결과를 검수하는 건 결국 제 몫이더라고요.\n\n"
    "도구는 쓰는 사람을 닮아요.\n"
    "한계를 알아야 제대로 쓸 수 있어요. AI를 다루는 대표가 살아남습니다.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "운동시설 대표님, DM 주세요. 아는 선에선 돕겠습니다.\n\n"
    "#AI #AI활용 #AI한계 #AI오해 #스포츠클럽 #일하는방식 #대표일상 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 기대공감(2) + 깨진지점(3) + 오해사례(4) + 배운것(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 처음 기대 → 멈춘 순간 → 구체 오해 → 사람의 몫 → 마무리 (성찰)
SLIDES = [
    dict(  # 1장 표지
        kor_title="AI를 쓰며\n깨진 환상들",
        eng_title="What I Got Wrong",
    ),
    dict(  # 2장 처음 기대·환상 공감
        kor_title="처음엔 이렇게\n기대했어요",
        body="AI를 켜면\n뭐든 다 될 줄 알았어요.\n그냥 말만 하면,\n알아서 척척 해줄 거라고.\n그 기대가 조금씩 깨졌어요.",
    ),
    dict(  # 3장 깨진 지점 — 시키는 법 모르면 멈춤
        kor_title="근데 이렇게\n멈추더라고요",
        body="막연하게 시키면\nAI도 막연하게 답해요.\n'잘 해줘'가 아니라\n'이렇게 해줘'가 필요했어요.\n시키는 법이 실력이었어요.",
    ),
    dict(  # 4장 구체적 오해 사례 3가지
        kor_title="제가 틀렸던\n것들이에요",
        body="· \"알아서 찾아줄 거야\" → 안 찾아요\n· \"한 번에 완성될 거야\" → 여러 번 다듬어요\n· \"내 상황을 알겠지\" → 매번 설명해야 해요\n솔직히 꽤 당황했어요.",
    ),
    dict(  # 5장 그래서 배운 것 — 사람의 몫
        kor_title="그래서 배운\n사람의 몫",
        body="AI는 잘 시켜야 잘 움직여요.\n맥락을 주고, 기준을 알려주고,\n결과를 검수하는 건 제 몫이에요.\n도구는 쓰는 사람을 닮아요.",
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
    # 기존 개인계정 발행분(왜AI·AI직원효율·입문편·역할분담)과 동일 처리. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 시그니처 슬로건 고정(2026-06-04 GM 지시 — 전 편 공통) + 함께 성장 + DM 유도
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="AI를 다루는 대표가\n살아남는다",
        body="한계를 알아야 제대로 쓸 수 있어요.\n시키는 법이 곧 실력이에요.\n완벽하진 않아도, 함께 성장합시다.\n\n운동시설 대표님, 궁금하면\nDM 주세요. 아는 선에선 돕겠습니다.",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260604_AI5_깨진환상들",
        montage_path=montage,
        caption=CAPTION,
        location=LOCATION,
        mentions=MENTIONS,
        account=ACCOUNT,
        slides=slides_rel,
        queue_id=QUEUE_ID,
        title=QUEUE_TITLE,
        channel=QUEUE_CHANNEL,
    )


if __name__ == "__main__":
    main()
