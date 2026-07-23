# 260619 슬라이드 빌드 — 접수부터 해결까지, 한 건이 끝까지 가는 과정 (AI 시리즈 #20 · 시즌2 실전편 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카드(로드맵 §5.1): 한 건이 접수→자동전달→조치→완료알림까지 끝까지 가는 전체 흐름.
#  1 표지 / 2 왜(빈칸이 답답) / 3 어떻게1(접수·자동전달·바로뜸) / 4 어떻게2(조치·완료알림·사람중간연결없음) / 5 그래서(끝까지 보인다) / 6 시그니처·CTA
# 톤: 개인계정 GM 1인칭. 조직을 이끄는 리더 시점. 광고 아님. 전문용어·내부 닉네임 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260619_AI20_접수부터해결까지한건이끝까지\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260619_AI20_접수부터해결까지한건이끝까지"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-19-AI20-접수부터해결까지한건"
QUEUE_TITLE = "AI #20편 — 접수부터 해결까지 한 건이 끝까지(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "접수부터 해결까지, 한 건이 끝까지 가는 과정\n\n"
    "회원이 불편을 말하면, 그게 어떻게 됐는지 끝까지 본 적 있나요?\n"
    "예전엔 접수하고 나면 처리됐는지 알 수가 없었어요. 그 빈칸이 제일 답답했죠.\n\n"
    "지금은 이렇게 흘러가요.\n"
    "회원이 직접 불편을 고르고 적어요.\n"
    "우리 AI가 읽고 맞는 담당자에게 바로 전달해요.\n"
    "담당자가 조치하고 기록하면, 회원에게 완료 알림이 가요.\n\n"
    "접수 → 전달 → 조치 → 완료. 그 사이에 사람이 중간에서 끌고 다닐 일이 없어요.\n"
    "회원도, 담당자도 지금 어디까지 됐는지 알아요. 한 건이 빠짐없이 끝까지 갑니다.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 가장 자주 들어오는 불편은 어떤 종류인가요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 왜(2) + 어떻게1(3) + 어떻게2(4) + 그래서(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="접수부터 해결까지,\n한 건이 끝까지\n가는 과정",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 왜 — 빈칸이 답답했다
        kor_title="처리됐는지\n모르는 게\n더 답답했어요",
        body="불편을 말해도\n그게 어떻게 됐는지\n알 수가 없었어요.\n접수·전달·처리·완료 사이에\n빈칸이 너무 많았어요.",
    ),
    dict(  # 3장 어떻게1 — 접수·자동전달·바로 뜸
        kor_title="먼저 이렇게\n시작돼요",
        body="① 회원이 직접 고르고 적어요\n② 우리 AI가 읽고\n   맞는 담당자에게 바로 보내요\n③ 담당자 화면에 바로 떠요\n따로 연락하고 기다릴 일 없어요.",
    ),
    dict(  # 4장 어떻게2 — 조치·완료알림·사람 중간연결 없음
        kor_title="그다음은\n이렇게 끝나요",
        body="④ 담당자가 조치하고 적어요\n⑤ 끝나면 회원에게 알림이 가요\n⑥ 접수→전달→조치→완료\n그 사이에 사람이\n중간에서 끌고 다닐 일이 없어요.",
    ),
    dict(  # 5장 그래서 — 끝까지 보인다
        kor_title="한 건이\n끝까지 가는 게\n보여요",
        body="한 건이 끝까지 간다는 게\n이렇게 눈에 보여요.\n회원도, 담당자도\n지금 어디까지 됐는지 알아요.",
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
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 6장 = 시그니처(편별 마무리 제목, #11+ 실전 노선) + 저장·댓글·팔로우 CTA(2026-06-10 정본)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="빠짐없이, 빠르게 —\n그게 신뢰가 되는 응대다",
        body="나중에 따라하려면 저장\n가장 자주 들어오는 불편은 어떤 종류인가요? 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260619_AI20_접수부터해결까지한건이끝까지",
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
