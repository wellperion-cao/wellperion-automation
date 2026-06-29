# 260628 슬라이드 빌드 — GM의 일요일 3: 일요일을, 진짜 일요일로 (AI 시리즈 #28 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 시즌2(실전편) · C안 확정(2026-06-28 GM) — A안(260627_AI27) 대체.
#  1 표지 / 2 예전(일이 걸쳐있던 일요일) / 3 달라진점(시스템이 돌아감) / 4 그래서오늘(일을 안 했다) / 5 깨달음(진짜 선물) / 6 시그니처·CTA
# 톤: 차분한 일요일 1인칭. 광고·모집 톤 금지. AI 티 금지(내부 닉네임 금지·'시스템' 정도). 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본.
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260628_AI28_GM의일요일3"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-28-AI28-GM의일요일3진짜"
QUEUE_TITLE = "AI #28편 — GM의 일요일 3: 일요일을, 진짜 일요일로(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음

SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "GM의 일요일 3 — 일요일을, 진짜 일요일로.\n\n"
    "예전 제 일요일엔 늘 일이 한 자락 걸쳐 있었어요.\n"
    "평일에 놓친 걸 주워보고, 다음 주 갈 길을 미리 그리고.\n"
    "쉬는 날인데도 머릿속 한쪽은 계속 일에 가 있었죠.\n\n"
    "그런데 요즘은 좀 달라졌어요.\n"
    "글 올리고, 문의 받고, 현황 챙기는 일들이\n"
    "이제 시스템에서 알아서 돌아가요.\n"
    "일요일에 제가 붙잡고 있을 일이 줄었어요.\n\n"
    "그래서 오늘은 그냥, 일을 안 했어요.\n"
    "늦잠을 자고, 천천히 걷고, 가까운 사람과 시간을 보냈어요.\n"
    "일은 하루의 한 토막이면 충분하더라고요.\n\n"
    "자동화가 정말 좋은 건 일을 빨리 끝내줘서가 아니라,\n"
    "일요일을 진짜 일요일로 돌려줘서예요.\n"
    "일을 덜어낸 자리에, 삶이 들어옵니다.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 당신의 일요일은 진짜 쉬는 날인가요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #일하는방식 #대표일상 #워라밸 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전(2) + 달라진점(3) + 그래서오늘(4) + 깨달음(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="GM의 일요일 ③",
        eng_title=SEASON2_LABEL,
        body="일요일을,\n진짜 일요일로.",
    ),
    dict(  # 2장 예전 — 일이 걸쳐 있던 일요일
        kor_title="예전엔 늘\n일이 걸쳐 있었어요",
        body="1편에선 놓친 걸 주워봤고,\n2편에선 다음 주를 미리 그렸죠.\n쉬는 날인데도 머릿속 한쪽은\n계속 일에 가 있었어요.",
    ),
    dict(  # 3장 달라진 점 — 시스템이 돌아감
        kor_title="이제는\n시스템이 돌아요",
        body="글 올리고, 문의 받고,\n현황 챙기는 일들이\n이제 알아서 돌아가요.\n일요일에 붙잡을 일이 줄었어요.",
    ),
    dict(  # 4장 그래서 오늘 — 일을 안 했다
        kor_title="그래서 오늘은,\n일을 안 했어요",
        body="늦잠을 자고,\n천천히 걷고,\n가까운 사람과 시간을 보냈어요.\n일은 하루의 한 토막이면 충분해요.",
    ),
    dict(  # 5장 깨달음 — 자동화의 진짜 선물
        kor_title="자동화의\n진짜 선물",
        body="일을 빨리 끝내줘서가 아니라,\n일요일을 진짜 일요일로\n돌려줘서예요.\n일을 덜어낸 자리에, 삶이 들어옵니다.",
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
        kor_title="일을 덜어낸 자리에,\n삶이 들어온다",
        body=(
            "나중에 따라하려면 저장\n"
            "당신의 일요일은 진짜 쉬는 날인가요? 댓글로 알려주세요\n"
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
        slug="260628_AI28_GM의일요일3",
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
