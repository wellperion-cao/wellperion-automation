# 260617 슬라이드 빌드 — 사진 몇 장 올리면 AI가 블로그·인스타 글 초안을 써준다 (AI 시리즈 #17 · namuk.wellperion)
# 시즌2(실전편). 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지. 개인계정 = W 심볼만.
# 확정 주제(로드맵 §4.1): 촬영 후 AI에 사진 설명 세 줄 넣으면 채널별 초안이 나오는 실제 순서 공개.
# 직전 #16(직원에게 AI를 넘기다) 이어가기: 직원도 결국 이 순서로 쓴다 — 누구나 따라 하는 실전 how-to.
#  1 표지 / 2 막힘 공감 / 3 순서①사진+설명 세 줄 / 4 순서②채널별 초안 / 5 사람의 몫(다듬기) / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직. 실전 순서 공개. 광고 아님. 전문용어 금지. 초등학생 눈높이. 간결·핵심만.
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260617_AI17_사진몇장올리면AI가블로그인\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260617_AI17_사진몇장올리면AI가블로그인"
OUT = FOLDER / "output"

# 시즌2 라벨 (로드맵 §2.6 단일출처) — 표지 부제 자리에 텍스트만
SEASON2_LABEL = "SEASON 2 · 실전편"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-17-AI17-사진몇장올리면AI가"
QUEUE_TITLE = "AI #17편 — 사진 몇 장이면 AI가 채널별 글 초안(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

CAPTION = (
    "사진은 찍었는데 글이 막힌 적, 있으시죠? 저도 그랬어요.\n\n"
    "그래서 순서를 하나 만들었어요. 거창하지 않아요.\n\n"
    "① 찍은 사진 몇 장을 AI에 올려요.\n"
    "② 사진마다 설명을 딱 세 줄씩 적어줘요. 언제·어디서·뭘 했는지.\n"
    "③ \"블로그용으로, 인스타용으로\" 라고 말하면 채널별 초안이 따로 나와요.\n\n"
    "블로그는 길고 차분하게, 인스타는 짧고 가볍게 — 같은 사진인데 톤이 달라요.\n\n"
    "물론 초안은 초안이에요. 어색한 곳 고치고, 사실 맞는지 보는 건 제 몫이에요.\n"
    "그래도 빈 화면 앞에서 멈추던 시간이 확 줄었어요.\n"
    "이건 저만 쓰는 게 아니라, 직원도 같은 순서로 쓰고 있어요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 사진 찍고 글이 막힌 적 있나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #콘텐츠 #블로그 #인스타그램 #스포츠클럽 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 막힘공감(2) + 순서①(3) + 순서②(4) + 사람의몫(5) + 마무리/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지 (시즌2 라벨 = 부제)
        kor_title="사진 몇 장이면\nAI가 글을 써줘요",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 막힘 공감
        kor_title="사진은 찍었는데\n글이 막혀요",
        body="사진은 잔뜩 찍었는데\n막상 글은 한 줄도 안 써져요.\n빈 화면만 바라본 적,\n저도 참 많았어요.",
    ),
    dict(  # 3장 실제 순서 ① 사진 + 설명 세 줄
        kor_title="순서는\n생각보다 간단해요",
        body="① 찍은 사진을 AI에 올려요.\n② 사진마다 설명 세 줄.\n언제·어디서·뭘 했는지만.\n딱 그 정도면 충분해요.",
    ),
    dict(  # 4장 실제 순서 ② 채널별 초안
        kor_title="채널별 초안이\n따로 나와요",
        body="\"블로그용, 인스타용\"이라 하면\n둘이 따로 나와요.\n블로그는 길고 차분하게,\n인스타는 짧고 가볍게.",
    ),
    dict(  # 5장 사람의 몫 — #16 흐름 이어받기
        kor_title="다듬는 건\n제 몫이에요",
        body="초안은 어디까지나 초안이에요.\n어색한 곳 고치고,\n사실 맞는지 보는 건 사람 몫.\n이젠 직원도 같은 순서로 써요.",
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

    # 개인계정(namuk.wellperion) = 'W' 심볼만 미니멀 로고. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 이번 편 마무리 제목(#11+ 실전 노선) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="찍었으면\n반은 끝난 거예요",
        body="나중에 따라하려면 저장\n사진 찍고 글이 막힌 적 있나요? 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
    )
    print(f"[OK] {last_out.name} - signature/CTA card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260617_AI17_사진몇장올리면AI가블로그인",
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
