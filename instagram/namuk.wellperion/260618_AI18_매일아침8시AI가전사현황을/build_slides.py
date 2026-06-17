# 260618 슬라이드 빌드 — 매일 아침 8시, AI가 전사 현황을 한 장으로 보고한다 (AI 시리즈 #18 · namuk.wellperion)
# 시즌2(실전편). 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지. 개인계정 = W 심볼만.
# 확정 주제(로드맵 §4.1): 6명 담당 보고·할일·미결을 사람이 취합 않고 AI가 매일 08:00 자동 수집·정리해 폰으로 한 장(ceo_morning_pipeline.py 예약작업 실제 근거).
# 직전 #17(사진→채널별 글 초안) 이어가기: 글만 AI가 돕는 게 아니라, 아침 보고 취합까지 AI가 한다 — 한 걸음 더.
#  1 표지 / 2 아침마다 보고 모으던 고생 공감 / 3 작동①각자 올리면 / 4 작동②8시 한 장으로 폰에 / 5 사람의 몫(읽고 결정) / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직. 실제 한 일 공개. 광고 아님. 전문용어 금지. 초등학생 눈높이. 간결·핵심만.
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260618_AI18_매일아침8시AI가전사현황을\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260618_AI18_매일아침8시AI가전사현황을"
OUT = FOLDER / "output"

# 시즌2 라벨 (로드맵 §2.6 단일출처) — 표지 부제 자리에 텍스트만
SEASON2_LABEL = "SEASON 2 · 실전편"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-18-AI18-매일아침8시AI가전"
QUEUE_TITLE = "AI #18편 — 매일 아침 8시 AI가 전사 현황 한 장 보고(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

CAPTION = (
    "아침마다 여기저기 흩어진 보고를 모으느라 바빴어요. 저도 그랬어요.\n\n"
    "담당마다 한 일, 할 일, 막힌 일이 다 다른 곳에 적혀 있으니까요.\n\n"
    "그래서 이걸 AI한테 맡겼어요.\n"
    "① 각 담당이 자기 자리에서 한 일·할 일·막힌 일을 올려요.\n"
    "② AI가 매일 아침 8시에 그걸 알아서 모아요.\n"
    "③ 정리해서 한 장으로 제 폰에 보내줘요.\n\n"
    "이제 아침에 폰만 열면 전사 현황이 한눈에 들어와요. 제가 모을 필요가 없어요.\n\n"
    "대신 그 한 장을 읽고, 오늘 뭐부터 할지 정하는 건 제 몫이에요.\n"
    "모으는 건 AI가, 결정하는 건 사람이 — 딱 그렇게 나눴어요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 아침마다 보고 모으는 데 시간 쓰시나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #조직운영 #리더십 #업무자동화 #스포츠클럽 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 고생공감(2) + 작동①(3) + 작동②(4) + 사람의몫(5) + 마무리/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지 (시즌2 라벨 = 부제)
        kor_title="매일 아침 8시\nAI가 한 장으로 보고",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 아침마다 보고 모으던 고생 공감
        kor_title="아침마다\n보고를 모았어요",
        body="담당마다 한 일도, 할 일도,\n막힌 일도 다 다른 곳에.\n그걸 하나씩 모으는 게\n매일 아침 제 일이었어요.",
    ),
    dict(  # 3장 실제 작동 ① 각자 올리면
        kor_title="이제는\n각자 올리기만 해요",
        body="담당이 자기 자리에서\n한 일·할 일·막힌 일을 올려요.\n따로 취합 회의도,\n제가 닦달할 일도 없어요.",
    ),
    dict(  # 4장 실제 작동 ② 8시 한 장으로 폰에
        kor_title="8시에 한 장으로\n폰에 와요",
        body="AI가 매일 아침 8시에\n그걸 알아서 모아요.\n정리해서 딱 한 장으로\n제 폰에 보내줘요.",
    ),
    dict(  # 5장 사람의 몫 — 읽고 결정
        kor_title="결정하는 건\n제 몫이에요",
        body="모으는 건 AI가 해줘도\n그 한 장을 읽고\n오늘 뭐부터 할지 정하는 건\n사람 몫이에요.",
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
        kor_title="모으는 건 AI\n정하는 건 나",
        body="나중에 따라하려면 저장\n아침마다 보고 모으는 데 시간 쓰시나요? 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260618_AI18_매일아침8시AI가전사현황을",
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
