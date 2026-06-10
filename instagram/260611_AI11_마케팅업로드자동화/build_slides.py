# 260611 슬라이드 빌드 — 마케팅 업로드 자동화 (AI 시리즈 #11 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1~#10과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-11 AI CMO 초안. "콘텐츠 1벌 만들면 5채널 자동 발행" — 실질적 도움, 과장 금지.
# 흐름: 1 표지 / 2 문제 / 3 발상 / 4 어떻게 / 5 결과·팁 / 6 마무리 CTA
# 직전 #10(AI를 다루는 대표가 살아남는다)와 차별화: #10=대체vs강해짐·도구로 다루는 능력. #11=실제 업로드 자동화 구체 사례(중복 금지 점검 완료).
# 톤: 개인계정 GM 1인칭 솔직. 현실감이 참여를 만든다. 과장·비현실 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 복합 바이럴(저장+DM+함께 성장).
# 실행: .venv\Scripts\python instagram\260611_AI11_마케팅업로드자동화\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260611_AI11_마케팅업로드자동화"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-11-AI11-MKT-AUTOMATION"
QUEUE_TITLE = "AI #11편 — 마케팅 업로드 자동화(개인계정)"
QUEUE_CHANNEL = "인스타그램(namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []

CAPTION = (
    "콘텐츠 1벌 만들면 5채널 자동 발행 — 실제로 쓰는 제 방식이에요.\n\n"
    "예전엔 인스타에 올리고, 블로그 가서 다시 쓰고, 카페 가서 또 고치고.\n"
    "같은 내용을 채널마다 규격에 맞춰 붙여넣는 게 생각보다 오래 걸렸어요.\n"
    "시간보다 번거로움이 쌓이니까 나중엔 그냥 안 올리게 되더라고요.\n\n"
    "그래서 구조를 바꿨어요.\n"
    "이미지 세트 하나 만들면, AI가 채널별 규격에 맞게 문구를 다듬어줘요.\n"
    "인스타·블로그·카페·당근·카카오 — 다섯 채널 각각.\n\n"
    "중요한 건 제가 마지막에 확인하고 눌러야 발행돼요.\n"
    "자동이라고 내가 빠지는 게 아니에요.\n"
    "반복만 AI한테 넘기고, 판단은 제가 하는 거예요.\n\n"
    "실제로 채널 하나당 따로 쓰던 시간이 절반 이상 줄었어요.\n"
    "완벽하진 않고, 가끔 수정도 해요.\n"
    "그래도 안 올리는 것보단 낫고, 빨라진 건 확실해요.\n\n"
    "따라 해보고 싶으면 딱 하나만 — 글 하나 써두고 \"이거 블로그 버전으로 바꿔줘\" AI한테 시켜보세요. 그게 시작이에요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 어떤 채널부터 자동화하고 싶으세요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #마케팅자동화 #콘텐츠자동화 #SNS자동화 #스포츠클럽 #대표일상 #일하는방식 #한남동 #웰페리온"
)

SLIDES = [
    dict(  # 1장 표지
        kor_title="콘텐츠 1벌 만들면\n5채널 자동 발행",
        eng_title="One Set, Five Channels",
    ),
    dict(  # 2장 문제 — 수동 업로드의 현실
        kor_title="채널마다 다시 쓰는\n그 시간이 문제예요",
        body="인스타 올리고\n블로그 가서 또 쓰고\n카페 가서 다시 고치고.\n같은 내용인데 왜 이렇게\n손이 많이 가는 거지?",
    ),
    dict(  # 3장 발상 — 1벌 제작 → 자동 분배
        kor_title="구조를 바꾸면\n달라집니다",
        body="이미지 세트 1벌 만들면\nAI가 채널별로 다듬어줘요.\n인스타·블로그·카페·당근·카카오.\n반복 작업은 AI한테,\n판단은 제가.",
    ),
    dict(  # 4장 어떻게 — 검수 게이트 + 예약발행
        kor_title="자동이라도\n내가 확인해요",
        body="AI가 규격·문구 다듬고\n저한테 보여줘요.\n제가 보고 누르면 발행.\n자동이어도 빠지지 않아요.\n반복만 넘기고 판단은 제 몫.",
    ),
    dict(  # 5장 결과·팁 — 솔직하게
        kor_title="실제로 얼마나\n줄었냐면요",
        body="채널당 따로 쓰던 시간 절반 줄었어요.\n완벽하진 않고 가끔 수정해요.\n하지만 안 올리는 것보단 낫고\n꾸준히 올라가는 건 분명해요.\n딱 하나만: AI한테 채널 변환 시켜보세요.",
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

    # 마지막 장 = 저장·댓글·팔로우 유도형 CTA (2026-06-10 GM 결정 — DM/문의URL 제거)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="1벌 만들면\n5채널이 움직입니다",
        body="나중에 따라하려면 저장\n어떤 채널부터 자동화할지\n댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면\n팔로우",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 -> {montage}")

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260611_AI11_마케팅업로드자동화",
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
