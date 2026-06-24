# 260614 슬라이드 빌드 — GM의 일요일 2: 다음 주 항로를 미리 그린다 (AI 시리즈 #14 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-14 AI CMO 초안. #8「GM의 일요일」속편 — 따라잡기 → 선제(미리 항로 그리기).
#  1 표지 / 2 지난주 회고(놓친 것 줍기)→이번주 한 발 더 / 3 일요일 아침에 하는 일 / 4 어떻게(항로 보드) / 5 그래서 월요일이 달라졌다 / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭, 차분한 일요일. how-to. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 GM 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260614_AI14_GM의일요일2\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260614_AI14_GM의일요일2"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-14-AI14-GM의일요일2다음주"
QUEUE_TITLE = "AI #14편 — GM의 일요일2: 다음 주 항로를 미리 그린다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "지난번 일요일 글에선, AI가 평일에 놓친 걸 일요일 아침에 주워준다고 했어요.\n\n"
    "이번 주엔 한 발 더 나가봤어요.\n"
    "일요일 아침, AI와 '다음 주에 갈 길'을 미리 그려둡니다.\n\n"
    "평일엔 매일 아침 AI와 '오늘 갈 길'을 정해요.\n"
    "그걸 일요일에 한 주 단위로 미리 해두는 거예요.\n\n"
    "AI가 지난주에 끝난 일, 아직 남은 일, 다음에 이어질 일을\n"
    "한 판에 모아 보여줘요.\n"
    "저는 거기서 다음 주 순서만 잡아요.\n\n"
    "그러면 월요일이 출발선이 아니에요.\n"
    "이미 방향이 정해진 채로 달리기 시작하는 거예요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 당신은 일요일에 다음 주를 미리 그려보나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #스포츠클럽 #리더십 #조직운영 #일하는방식 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 지난주회고/한발더(2) + 일요일아침에하는일(3) + 어떻게(4) + 월요일이달라짐(5) + 마무리/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="GM의 일요일 2\n다음 주를 미리 그린다",
        eng_title="Sunday, One Step Ahead",
    ),
    dict(  # 2장 지난주 회고 → 이번주 한 발 더
        kor_title="지난번엔\n따라잡기였어요",
        body="평일에 놓친 걸\n일요일 아침 AI가 주워줬어요.\n이번 주엔 한 발 더 나가봤어요.\n놓친 걸 줍는 대신,\n다음 주를 미리 그려둡니다.",
    ),
    dict(  # 3장 일요일 아침에 하는 일
        kor_title="일요일 아침에\n하는 일",
        body="평일엔 매일 아침\nAI와 '오늘 갈 길'을 정해요.\n그걸 일요일에\n한 주 단위로 미리 해둬요.\n주간판 길잡이인 셈이죠.",
    ),
    dict(  # 4장 어떻게 — 항로 보드
        kor_title="AI가 한 판에\n모아줘요",
        body="지난주에 끝난 일,\n아직 남은 일,\n다음에 이어질 일.\nAI가 한 화면에 모아주면\n저는 다음 주 순서만 잡아요.",
    ),
    dict(  # 5장 그래서 월요일이 달라졌다
        kor_title="그래서 월요일이\n달라졌어요",
        body="월요일이 출발선이 아니에요.\n이미 방향이 정해진 채로\n달리기 시작해요.\n뭐부터 할지 고민하는 시간이\n사라졌어요.",
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
    # 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 편별 마무리 제목(#11+ 실전 노선) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="일요일 30분이\n월요일을 바꾼다",
        body="나중에 따라하려면 저장\n당신은 일요일에 다음 주를 미리 그려보나요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260614_AI14_GM의일요일2",
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
