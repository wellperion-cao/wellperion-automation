# 260705 슬라이드 빌드 — GM의 일요일 4: 다른 클럽에 AI를 심는다 (AI 시리즈 #38 · namuk.wellperion)
# 시즌2(실전편) · 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지. 로고=W 심볼만.
# 확정 카드(로드맵 §5.1): 가벼워진 일요일, 그 여유로 다른 클럽·가게에 AI를 셋업해준다 — 팔려고가 아니라 너무 좋아서.
#  1 표지 / 2 예전(비어버린 일요일) / 3 지금(남의 가게 셋업) / 4 왜(좋아서 나눈다) / 5 깨달음(남의 하루도 돌려준다) / 6 시그니처·CTA
# 톤: 개인계정 GM 1인칭 잔잔한 인터루드. 영업·판매 톤 금지, 진행형(이제 막 심어보는 중). 전문용어·닉네임 금지.
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260705_AI38_GM의일요일4\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260705_AI38_GM의일요일4"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-07-05-AI38-GM의일요일4다른클"
QUEUE_TITLE = "AI #38편 — GM의 일요일 4: 다른 클럽에 AI를 심는다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

# 시즌2 라벨 (표지 부제/eng_sub 자리)
SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "요즘 내 일요일은, 남의 가게 일을 한다.\n\n"
    "한때 일요일은 밀린 걸 따라잡고 다음 주를 미리 그리던 날이었어요.\n"
    "그런데 일이 알아서 돌아가게 자리를 잡으니, 일요일에 시간이 비더라고요.\n\n"
    "그 빈 시간에 요즘은 다른 클럽이나 가게에 AI를 셋업해줍니다.\n"
    "우리한테 이렇게 편했던 걸, 이제 막 다른 곳에도 심어보는 중이에요.\n\n"
    "팔려고가 아니에요. 그냥 너무 좋아서 — 나만 아는 게 아까워서요.\n"
    "내 하루를 돌려준 도구가 이제 남의 하루도 돌려줘요.\n"
    "그래서 쉬는 날인데도, 이건 일 같지가 않아요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 너무 좋아서 남들도 알았으면 한 것? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #대표일상 #일요일 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전(2) + 지금(3) + 왜(4) + 깨달음(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="GM의 일요일 4",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 예전 — 비어버린 일요일
        kor_title="일요일이\n비었어요",
        body="한때 일요일은\n밀린 걸 따라잡고\n다음 주를 미리 그리던 날.\n일이 알아서 돌아가니,\n일요일에 시간이 비더라고요.",
    ),
    dict(  # 3장 지금 — 남의 가게에 AI를 심는다
        kor_title="요즘은\n남의 일을 해요",
        body="그 빈 시간에\n다른 클럽이나 가게에\nAI를 셋업해줍니다.\n우리한테 이렇게 편했던 걸,\n그들 손에도 쥐여주는 일이에요.",
    ),
    dict(  # 4장 왜 — 팔려고가 아니라 좋아서
        kor_title="팔려고가\n아니에요",
        body="그냥 너무 좋아서예요.\n이 편함을 나만 아는 게\n아까워서요.\n좋은 건 결국\n나누고 싶어지더라고요.",
    ),
    dict(  # 5장 깨달음 — 남의 하루도 돌려준다
        kor_title="남의 하루도\n돌려줘요",
        body="내 하루를 돌려준 도구가\n이제 남의 하루도 돌려줘요.\n그래서 쉬는 날인데도,\n이건 일 같지가 않아요.",
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

    # 개인계정(namuk.wellperion) = 'W' 심볼만 미니멀 로고
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 6장 = 시그니처 제목(편별 마무리) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="좋은 건,\n나누고 싶어진다",
        body="나중에 따라하려면 저장\n너무 좋아서 남들도 알았으면 한 것, 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260705_AI38_GM의일요일4",
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
