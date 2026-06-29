# 260629 슬라이드 빌드 — 시키지 않아도, 스스로 배운다 (AI 시리즈 #29 · namuk.wellperion · 시즌2 실전편)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카드(로드맵 §5.1): 자동화를 해놔도 새로 배운 건 매번 내가 알려줘야 했다 → AI가 주1회 스스로
#   한 주를 복기·정리해 자기 지식으로 쌓기 시작(진행형·표본 적음, 정직).
#  1 표지 / 2 문제 / 3 보완(주1회 스스로 복기) / 4 더나아진점① / 5 더나아진점②(정직한 한계) / 6 시그니처·CTA
# 톤: 개인계정 GM 1인칭 솔직. 초등 눈높이·짧은 문장. 내부 AI 닉네임 금지("우리 AI"). 전문용어 금지.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 개정).
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260629_AI29_시키지않아도스스로배운다"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-29-AI29-시키지않아도스스로배"
QUEUE_TITLE = "AI #29편 — 시키지 않아도 스스로 배운다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "시키지 않아도, 스스로 배운다.\n\n"
    "자동화를 아무리 해놔도, 새로 배운 건 결국 매번 내가 다시 알려줘야 했어요.\n"
    "같은 설명을 또 하는 것도 내 일이었죠.\n\n"
    "그래서 우리 AI가 한 주에 한 번,\n"
    "그 주에 있었던 일을 스스로 돌아보고 '이건 기억해두자'를 정리해두게 했어요.\n\n"
    "달라진 건 두 가지예요.\n"
    "· 같은 걸 두 번 설명하는 일이 줄었어요. 한 번 정리되면 다음부턴 알아서 챙겨요.\n"
    "· 아직 다 배운 건 아니에요. 스스로 쌓기 시작한 단계, 매주 조금씩 늘고 있어요.\n\n"
    "도구는 시키는 것, 동료는 스스로 배워요.\n"
    "이제 막 배우기 시작하니, 다음엔 먼저 말을 걸어오더라고요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 당신은 같은 걸 몇 번이나 다시 설명하고 있나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 문제(2) + 보완(3) + 더나아진점①(4) + 더나아진점②(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="시키지 않아도,\n스스로 배운다",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 문제 — 새로 배운 건 매번 내가 알려줘야 했다
        kor_title="결국 매번\n내가 시켰어요",
        body="자동화를 해놨는데도,\n새로 배운 건 매번\n내가 다시 알려줘야 했어요.\n같은 설명을 또 하는 것도\n결국 내 일이었어요.",
    ),
    dict(  # 3장 보완 — 주1회 스스로 복기·정리
        kor_title="그래서 스스로\n돌아보게 했어요",
        body="우리 AI가 한 주에 한 번,\n그 주에 있었던 일을\n스스로 돌아보게 했어요.\n'이건 기억해두자'를\n정리해 남겨두도록.",
    ),
    dict(  # 4장 더 나아진 점 ①
        kor_title="두 번 설명하는\n일이 줄었어요",
        body="한 번 정리된 건\n다음부터 알아서 챙겨요.\n같은 걸 또 설명하느라\n쓰던 시간이\n조금씩 줄어들었어요.",
    ),
    dict(  # 5장 더 나아진 점 ② — 정직한 한계
        kor_title="아직은 쌓기\n시작한 단계예요",
        body="솔직히 다 배운 건 아니에요.\n'완벽하게 안다'가 아니라\n'스스로 쌓기 시작한' 단계요.\n매주 조금씩\n늘어나는 중이에요.",
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

    # 마지막 6장 = 시그니처(편별 제목) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="도구는 시키는 것,\n동료는 스스로 배운다",
        body="나중에 따라하려면 저장\n같은 걸 몇 번이나 다시 설명하고 있나요? 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260629_AI29_시키지않아도스스로배운다",
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
