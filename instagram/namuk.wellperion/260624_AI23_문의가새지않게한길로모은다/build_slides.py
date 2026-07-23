# 260624 슬라이드 빌드 — 문의가 새지 않게, 한 길로 모은다 (AI 시리즈 #23 · SEASON 2 실전편 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카드(로드맵 §5.1): 문의가 전화·방문 제각각 → 한 길(홈 문의)로 모아 자동 기록 → 놓침 0·기록 남아 응대 빨라짐.
#  1 표지 / 2 문제(제각각·놓침) / 3 보완(한 길로 모음·자동기록) / 4 업그레이드①놓침0 / 5 업그레이드②기록·빠른응대 / 6 시그니처·CTA
# 톤: 개인계정 GM 1인칭 솔직. '정리해뒀다' 중심, 기술 과시·AI 티 금지. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 개정).
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260624_AI23_문의가새지않게한길로모은다"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-24-AI23-문의가새지않게한길로"
QUEUE_TITLE = "AI #23편 — 문의를 한 길로 모은다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "문의가 새지 않게, 한 길로 모았어요.\n\n"
    "예전엔 문의가 여기저기로 들어왔어요.\n"
    "전화로 한 건, 찾아와서 한 건, 또 다른 데로 한 건.\n"
    "그러다 보니 어떤 건 기록이 안 되고, 어떤 건 응대를 놓쳤어요.\n"
    "사람이 일일이 받아 적는 것도 한계가 있더라고요.\n\n"
    "그래서 문의가 들어오는 길을 하나로 모았어요.\n"
    "홈의 '문의하기' 한 곳으로요. 들어오면 자동으로 기록이 남아요.\n\n"
    "달라진 건 두 가지예요.\n"
    "하나, 놓치는 문의가 없어졌어요. 들어온 건 전부 한 곳에 남아요.\n"
    "둘, 누가 언제 무엇을 물었는지 남으니 응대가 빨라지고 빠짐이 없어요.\n\n"
    "길을 하나로 모으니, 문의 하나하나가 결국 사람으로 보이더라고요.\n"
    "이제 문의가 한 곳에 차곡차곡 쌓여요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 문의, 지금 몇 군데로 받고 있나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #일하는방식 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 문제(2) + 보완(3) + 업그레이드①(4) + 업그레이드②(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지 (eng_title 자리에 시즌2 라벨)
        kor_title="문의가 새지 않게,\n한 길로 모은다",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 문제 — 제각각 들어와 놓침
        kor_title="문의가 여기저기\n흩어졌어요",
        body="전화로 한 건,\n찾아와서 한 건, 또 다른 데로 한 건.\n어떤 건 기록이 안 되고\n어떤 건 응대를 놓쳤어요.\n받아 적는 것도 한계였어요.",
    ),
    dict(  # 3장 보완 — 한 길로 모으고 자동 기록
        kor_title="들어오는 길을\n하나로 모았어요",
        body="홈의 '문의하기' 한 곳으로요.\n들어오면 자동으로 기록이 남아요.\n흩어진 길을 하나로 모았어요.\n문의: wellperion.com/ko/inquiry",
    ),
    dict(  # 4장 업그레이드① — 놓침 0
        kor_title="이제 놓치는\n문의가 없어요",
        body="들어온 건 전부\n한 곳에 남아요.\n빠지는 게 없으니\n마음이 놓여요.",
    ),
    dict(  # 5장 업그레이드② — 기록 남아 빠른 응대 + 내일 다리
        kor_title="기록이 남으니\n응대가 빨라요",
        body="누가 언제 무엇을 물었는지\n그대로 남아 있어요.\n응대가 빨라지고 빠짐이 없어요.\n이제 문의가 한 곳에 쌓여요.",
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

    # 마지막 장 = 편별 마무리 제목 + 저장·댓글·팔로우 정본 CTA(2026-06-10 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="문의 하나하나가\n결국 사람이다",
        body="나중에 따라하려면 저장\n문의, 지금 몇 군데로 받고 있나요? 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260624_AI23_문의가새지않게한길로모은다",
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
