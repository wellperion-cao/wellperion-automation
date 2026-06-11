# 260612 슬라이드 빌드 — 시간대별 운영현황 AI 자동 보고 (AI 시리즈 #12 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1~#11과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-12 AI CMO. "운영 현황을 쫓아다니지 마세요 — AI가 시간대별로 보고합니다." 현장 실전 how-to.
# 흐름: 1 표지 / 2 문제(공감) / 3 발상(전환) / 4 어떻게(실전 따라하기) / 5 결과(before→after) / 6 마무리 CTA
# 직전 #11(마케팅 업로드 자동화)와 차별화: #11=콘텐츠 1벌→5채널 분배. #12=운영현황을 사람이 확인하러 다니지 말고 AI가 시간대별로 폰에 보고(중복 금지).
# 톤: 개인계정 GM 1인칭 솔직. 한남동 하이엔드 스포츠클럽 대표 시점. '1인가게/혼자' 프레임 금지. 과장·비현실·설교 금지.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우(도달 유도형, #11부터 정본).
# 실행: .venv\Scripts\python instagram\260612_AI12_시간대별운영현황AI자동보고\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260612_AI12_시간대별운영현황AI자동보고"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-12-AI12-OPS-STATUS-AUTOREPORT"
QUEUE_TITLE = "AI #12편 — 시간대별 운영현황, AI가 알아서 보고한다(개인계정)"
QUEUE_CHANNEL = "인스타그램(namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []

CAPTION = (
    "운영 현황을 쫓아다니지 마세요. AI가 시간대별로 알아서 보고합니다.\n\n"
    "오픈 잘 됐나, 피크 땐 안 붐비나, 마감 매출은. 하루에도 몇 번씩 확인했어요.\n"
    "확인하러 가는 대신, 정해진 시간에 오게 만들면 됩니다.\n"
    "오픈·피크·마감마다 볼 항목 한 줄씩 정해 AI에 등록 → 텔레그램으로 자동 도착.\n"
    "지금은 폰만 열면 와 있어요. 확인은 AI, 결정은 저.\n\n"
    "📌 따라하려면 저장\n"
    "💬 어느 시간대부터 받고 싶으세요? 댓글로\n"
    "👀 이런 AI 활용기 더 보려면 팔로우\n\n"
    "#AI #AI활용 #스포츠클럽 #리더십 #조직운영 #운영자동화 #한남동 #웰페리온"
)

SLIDES = [
    dict(  # 1장 표지
        kor_title="운영 현황을\n쫓아다니지 마세요",
        eng_title="HOW MY CLUB REPORTS ITSELF",
    ),
    dict(  # 2장 문제 — 확인하러 다니는 하루
        kor_title="하루에도 몇 번씩\n괜찮나 확인했어요",
        body="오픈 잘 됐나, 피크 땐 안 붐비나,\n마감 매출은. 자꾸 확인하게 됐죠.",
    ),
    dict(  # 3장 발상 — 방향을 뒤집다
        kor_title="확인하러 가지 말고\n오게 만드세요",
        body="확인하러 다니는 대신\n정해진 시간에 오게 만들면 돼요.",
    ),
    dict(  # 4장 어떻게 — 실전 따라하기 3단계
        kor_title="오늘 바로\n따라하는 법",
        body="① 받을 시간 정하기(오픈·피크·마감)\n② 시간마다 볼 항목 한 줄\n③ AI 등록 → 텔레그램 자동 도착",
    ),
    dict(  # 5장 결과 — before→after
        kor_title="지금은 폰만 열면\n와 있어요",
        body="오픈·피크·마감이 알아서 도착해요.\n확인은 AI, 결정은 저.",
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
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, credit=True, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 편별 제목(실전 노선) + 저장·댓글·팔로우 CTA (2026-06-10 GM #11부터 정본 — DM/슬로건 폐기)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        credit=True,
        kor_title="시간만 정해두면\nAI가 보고합니다",
        body="따라하려면 저장\n어느 시간대부터 받고 싶은지 댓글로\n이런 AI 활용기 더 보려면 팔로우",
    )
    print(f"[OK] {last_out.name} - title/CTA card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 -> {montage}")

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260612_AI12_시간대별운영현황AI자동보고",
        montage_path=montage,
        caption=CAPTION,
        location=LOCATION,
        mentions=MENTIONS,
        account=ACCOUNT,
        slides=slides_rel,
        queue_id=QUEUE_ID,
        title=QUEUE_TITLE,
        channel=QUEUE_CHANNEL,
        send_card=True,  # 수동 경로 승인버튼 카드 자동 발송(자동생성기 무영향: 기본 False)
    )


if __name__ == "__main__":
    main()
