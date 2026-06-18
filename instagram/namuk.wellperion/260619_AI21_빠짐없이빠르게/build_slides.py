# 260619 슬라이드 빌드 — 빠짐없이, 빠르게: 회원 만족이 목표예요 (AI 시리즈 #21 · namuk.wellperion · SEASON 2 실전편)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카드: 로드맵 §5.1 — CS 챕터(#19~#21) 마무리 편. 직전 #20(한 건이 끝까지 가는 과정)을 잇는다.
#  1 표지 / 2 왜(현황 안 보이면 구멍) / 3 어떻게1(쌓여 보이고·현황·AI점검) / 4 어떻게2(빠른 응대·정직·챕터 마무리) / 5 그래서(놓치지 않는 응대=만족) / 6 시그니처·저장/댓글/팔로우
# 톤: 개인계정 GM 1인칭 진솔. 조직 이끄는 리더 화자. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260619_AI21_빠짐없이빠르게\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260619_AI21_빠짐없이빠르게"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-19-AI21-빠짐없이빠르게회원만"
QUEUE_TITLE = "AI #21편 — 빠짐없이 빠르게, 회원 만족이 목표(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

# 시즌2 라벨 (로드맵 §2.6 단일출처 — 표지 부제 자리)
SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "들어온 것과 해결된 것, 지금 몇 개인지 알고 있나요?\n\n"
    "회원이 남긴 말이 하나둘 쌓이면, 뭐가 들어왔고 뭐가 끝났는지 금세 헷갈려요.\n"
    "빠진 게 있어도 모르고 지나가요. 그게 바로 응대의 구멍이에요.\n\n"
    "그래서 이렇게 바꿨어요.\n"
    "· 들어온 것들이 한 화면에 모여요\n"
    "· 몇 개 들어오고 몇 개 해결됐는지 바로 보여요\n"
    "· 빠진 건 없는지 우리 AI가 한 번 더 훑어줘요\n\n"
    "핵심은 빠르게 응대하는 거예요.\n"
    "솔직히 만족도를 아직 숫자로 재진 못해요. 그래도 가는 방향은 분명해요.\n"
    "빠짐없이, 빠르게 — 놓치지 않는 응대가 회원 만족으로 이어진다고 믿어요.\n\n"
    "이렇게 회원이 말하면 AI가 받아 전달하고 끝까지 해결되는 이야기,\n"
    "여기까지가 한 챕터의 마무리예요. 다음엔 사람들이 먼저 찾아오게 만드는 이야기로 가볼게요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 CS 응대에서 가장 어려운 부분은 뭔가요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #회원관리 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 왜(2) + 어떻게1(3) + 어떻게2(4) + 그래서(5) + 시그니처(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지 — 후크로 스크롤 멈춤, 부제 자리에 시즌2 라벨
        kor_title="빠짐없이, 빠르게\n회원 만족이 목표예요",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 왜 — 현황이 안 보이면 구멍이 생긴다
        kor_title="현황이 안 보이면\n구멍이 생겨요",
        body="회원 말이 하나둘 쌓이면\n뭐가 들어왔고\n뭐가 끝났는지 헷갈려요.\n빠진 걸 모르고 지나가요.\n그게 응대의 구멍이에요.",
    ),
    dict(  # 3장 어떻게1 — 쌓여 보이고·현황·AI 점검
        kor_title="그래서 한눈에\n보이게 했어요",
        body="· 들어온 것들이 한 화면에 모여요\n· 몇 개 들어오고 몇 개 끝났는지 바로 보여요\n· 빠진 건 없는지 우리 AI가 한 번 더 훑어줘요",
    ),
    dict(  # 4장 어떻게2 — 빠른 응대·정직(미측정)·챕터 마무리
        kor_title="핵심은\n빠르게예요",
        body="빠르게 응대하는 게 제일 중요해요.\n솔직히 만족도를\n아직 숫자로 재진 못해요.\n그래도 우리가 가는 방향은\n분명해요.",
    ),
    dict(  # 5장 그래서 — 놓치지 않는 응대 = 만족
        kor_title="놓치지 않으면\n만족으로 가요",
        body="빠짐없이, 빠르게.\n회원이 말하면 AI가 받아\n담당자에게 전하고\n끝까지 해결돼요.\n그 흐름이 만족을 만들어요.",
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

    # 마지막 6장 = 시그니처(편별 마무리 제목 · #11+ 실전 노선) + 저장·댓글·팔로우 정본(2026-06-10 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="측정 못 해도 방향은 안다 —\n놓치지 않는 응대가 만족이다",
        body="나중에 따라하려면 저장\nCS 응대에서 가장 어려운 부분은 뭔가요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
    )
    print(f"[OK] {last_out.name} - signature/save-comment-follow card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260619_AI21_빠짐없이빠르게",
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
