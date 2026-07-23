# 260616 슬라이드 빌드 — 휴관·이벤트 공지문, AI로 채널별 버전을 한 번에 (AI 시리즈 #16 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-16 AI CMO 제작. 시즌2(실전편) — 공지 한 줄 넣으면 카톡·인스타·블로그·카페 4채널 톤에 맞게 4벌이 나오는 실제 프롬프트 공개.
#  실재: 4채널 표준 운영(IG·블로그·카페) + 카톡 안내. 같은 공지를 채널마다 다시 쓰던 일을 프롬프트 한 번으로 끝낸 실제 작업.
#  1 표지(SEASON2 라벨) / 2 예전=채널마다 다시 씀 / 3 깨달음=내용은 같고 톤만 다름 / 4 실제 프롬프트 공개 / 5 결과=4벌 동시·톤 자동 / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭, 조직을 이끄는 리더. how-to. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 GM 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260616_AI16_휴관이벤트공지문AI로채널별\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260616_AI16_휴관이벤트공지문AI로채널별"
OUT = FOLDER / "output"

# 시즌2(실전편) 공통 라벨 — 표지 eng_sub 자리 텍스트 (로드맵 §2.6 단일출처)
SEASON2_LABEL = "SEASON 2 · 실전편"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-16-AI16-휴관이벤트공지문AI"
QUEUE_TITLE = "AI #16편 — 공지문 채널별 4벌 한 번에 뽑기(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "오늘은 '공지문' 이야기예요.\n\n"
    "휴관이나 이벤트 공지를 올릴 때, 저는 예전에 같은 내용을 네 번 다시 썼어요.\n"
    "카톡 한 번, 인스타 한 번, 블로그 한 번, 카페 한 번.\n"
    "채널마다 말투가 달라야 하니까요.\n\n"
    "그런데 내용은 똑같잖아요. 톤만 다른 거예요.\n"
    "그래서 AI한테 이렇게 시켜봤어요.\n\n"
    "\"이 공지를 카톡·인스타·블로그·카페 톤에 맞게 각각 다시 써줘.\"\n\n"
    "공지 한 줄만 넣으면 4벌이 한 번에 나와요.\n"
    "카톡은 짧게, 인스타는 감성 한 스푼, 블로그는 자세히, 카페는 친근하게.\n"
    "네 번 쓰던 일이 한 번으로 줄었어요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 공지를 채널마다 다시 쓰느라 시간 버린 적 있나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지(영문/라벨 대제목 + 한글 부제), 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전·채널마다다시씀(2) + 깨달음·내용같고톤만다름(3) + 실제프롬프트(4) + 결과·4벌동시(5) + 마무리/CTA(6, main() 별도)
# 표지 eng_title 자리에 SEASON2_LABEL 텍스트만(별도 그래픽 뱃지 합성 없음). 시즌2 전 편 공통.
SLIDES = [
    dict(  # 1장 표지 (시즌2 라벨 + 한글 제목)
        kor_title="공지문, 채널별로\n한 번에 뽑는 법",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 예전 = 채널마다 다시 씀
        kor_title="예전엔 같은 공지를\n네 번 썼어요",
        body="휴관·이벤트 공지 하나에\n카톡 한 번,\n인스타 한 번,\n블로그 한 번, 카페 한 번.\n매번 다시 쓰니 한참 걸렸어요.",
    ),
    dict(  # 3장 깨달음 = 내용은 같고 톤만 다름
        kor_title="근데 내용은\n똑같더라고요",
        body="네 번 쓴 글,\n사실 내용은 다 같았어요.\n다른 건 말투뿐이었죠.\n그럼 톤만 바꾸면 되잖아요.\n그걸 AI한테 맡겼어요.",
    ),
    dict(  # 4장 실제 프롬프트 공개
        kor_title="제가 쓰는\n프롬프트예요",
        body="공지 한 줄을 주고 이렇게 시켜요.\n\"이 공지를\n카톡·인스타·블로그·카페\n톤에 맞게 각각 다시 써줘.\"\n그게 전부예요.",
    ),
    dict(  # 5장 결과 = 4벌 동시 · 톤 자동
        kor_title="4벌이 한 번에\n나와요",
        body="카톡은 짧고 간단하게.\n인스타는 감성 한 스푼.\n블로그는 자세하게.\n카페는 친근하게.\n네 채널 톤이 알아서 맞춰져요.",
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
        kor_title="한 번 쓰고\n네 곳에 맞춘다",
        body="나중에 따라하려면 저장\n공지를 채널마다 다시 쓰느라 시간 버린 적 있나요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260616_AI16_휴관이벤트공지문AI로채널별",
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
