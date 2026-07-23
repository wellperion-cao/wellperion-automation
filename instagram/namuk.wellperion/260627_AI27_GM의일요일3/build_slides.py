# 260627 슬라이드 빌드 — GM의 일요일 3: 일을 쫓던 일요일에서, 사람을 보는 일요일로 (AI 시리즈 #27 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 시즌2(실전편) · 확정 카드(로드맵 §5.1) 비트대로 제작만 함.
#  1 표지 / 2 예전(따라잡는 일요일) / 3 달라진점(손이 덜 가게 자리잡음) / 4 그래서오늘(사람을 본다) / 5 깨달음 / 6 시그니처·CTA
# 톤: 차분한 일요일 1인칭. 광고·모집 톤 금지. AI 티 금지(내부 닉네임 금지·'우리 시스템' 정도). 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본.
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260627_AI27_GM의일요일3"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-27-AI27-GM의일요일3일을쫓"
QUEUE_TITLE = "AI #27편 — GM의 일요일 3: 일 대신 사람을 보는 일요일(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음

SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "GM의 일요일 3 — 일을 쫓던 일요일에서, 사람을 보는 일요일로.\n\n"
    "한동안 제 일요일은 '따라잡는 날'이었어요.\n"
    "평일에 놓친 걸 모아 보고, 다음 주 할 일을 미리 그렸죠.\n"
    "쉬는 날인데 늘 일이 한 자락 걸쳐 있었어요.\n\n"
    "이번 주는 달랐어요.\n"
    "글 올리고, 문의 받고, 현황 챙기던 일들이\n"
    "이제 우리 시스템에서 알아서 돌아가게 자리잡는 중이에요.\n"
    "그래서 일요일에 따라잡을 것도, 급히 그릴 것도 줄었어요.\n\n"
    "빈 시간에 숫자나 할 일 대신,\n"
    "한 주 동안 들어온 문의와 회원을 천천히 들여다봤어요.\n"
    "누가 왜 왔고, 무엇을 궁금해했는지.\n"
    "일이 아니라 사람이 보이더라고요.\n\n"
    "자동화가 좋은 건 빨라서가 아니라,\n"
    "사람을 볼 여유를 돌려줘서예요.\n"
    "일을 덜어낸 자리에, 사람이 들어옵니다.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 당신의 일요일은 무엇을 따라잡는 날인가요, 아니면 비우는 날인가요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #일하는방식 #대표일상 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전(2) + 달라진점(3) + 그래서오늘(4) + 깨달음(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="GM의 일요일 3",
        eng_title=SEASON2_LABEL,
        body="일요일 아침,\n예전엔 밀린 일부터 폈어요.\n오늘은 그러지 않았어요.",
    ),
    dict(  # 2장 예전 — 따라잡는 일요일
        kor_title="따라잡는\n일요일이었어요",
        body="한동안 제 일요일은\n'따라잡는 날'이었어요.\n놓친 걸 모아 보고,\n다음 주 할 일을 미리 그렸죠.\n쉬는 날인데 늘 일이 걸쳐 있었어요.",
    ),
    dict(  # 3장 달라진 점 — 손이 덜 가게 자리잡음
        kor_title="이번 주는\n달랐어요",
        body="글 올리고, 문의 받고,\n현황 챙기던 일들이\n이제 알아서 돌아가게 자리잡는 중이에요.\n그래서 따라잡을 것도,\n급히 그릴 것도 줄었어요.",
    ),
    dict(  # 4장 그래서 오늘 — 사람을 본다
        kor_title="그래서 오늘은\n사람을 봤어요",
        body="빈 시간에 숫자나 할 일 대신,\n한 주 들어온 문의와 회원을\n천천히 들여다봤어요.\n누가 왜 왔고, 뭘 궁금해했는지.\n일이 아니라 사람이 보였어요.",
    ),
    dict(  # 5장 깨달음
        kor_title="자동화가\n돌려준 것",
        body="좋은 건 빨라서가 아니에요.\n사람을 볼 여유를\n돌려줘서예요.\n일을 쫓던 일요일에서,\n사람을 떠올리는 일요일로.",
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

    # 마지막 6장 = 시그니처(편별 제목) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="일을 덜어낸 자리에,\n사람이 들어온다",
        body=(
            "나중에 따라하려면 저장\n"
            "당신의 일요일은 따라잡는 날인가요, 비우는 날인가요? 댓글로 알려주세요\n"
            "이런 AI 활용기 계속 보고 싶으면 팔로우"
        ),
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
        slug="260627_AI27_GM의일요일3",
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
