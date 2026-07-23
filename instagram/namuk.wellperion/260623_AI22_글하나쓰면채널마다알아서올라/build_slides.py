# 260623 슬라이드 빌드 — 글 하나 쓰면, 채널마다 알아서 올라간다 (AI 시리즈 #22 · namuk.wellperion · SEASON 2 실전편)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카드(로드맵 §5.1): 1 표지 / 2 문제 / 3 보완 / 4 업그레이드① / 5 업그레이드② / 6 시그니처·CTA
# 톤: 개인계정 GM 1인칭 솔직. 운영이 바뀐 이야기 중심, AI는 조용한 도구. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 GM 개정).
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260623_AI22_글하나쓰면채널마다알아서올라"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-23-AI22-글하나쓰면채널마다알"
QUEUE_TITLE = "AI #22편 — 글 하나 쓰면 채널마다 알아서 올라간다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "글 하나 쓰면, 채널마다 알아서 올라간다.\n\n"
    "글은 다 썼는데, 올리는 게 또 한나절이었어요.\n"
    "인스타·블로그·카페… 채널이 늘수록 같은 내용을 형식 맞춰 따로 올리고,\n"
    "올리는 시간까지 신경 쓰는 게 매일 반복되는 잡일이었어요.\n\n"
    "그래서 한 번만 검수하면 채널별로 알아서 정리돼 올라가게 해뒀어요.\n"
    "올리는 데 들던 시간이 거의 사라졌고,\n"
    "빠뜨리는 채널·시간 실수도 없어졌어요. 늘 같은 품질로 빠짐없이 나가요.\n"
    "(채널에 따라 마지막 게시는 제가 직접 확인하고 누르기도 해요.)\n\n"
    "올리는 일에서 손을 떼니, 글 자체와 회원에게 쓸 시간이 생겼어요.\n"
    "이제 남은 시간을 어디에 쓸지가 다음 고민이에요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 당신은 콘텐츠를 채널마다 따로 올리는 데 시간을 얼마나 쓰나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #일하는방식 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 문제(2) + 보완(3) + 업그레이드①(4) + 업그레이드②(5) + 시그니처/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="글 하나 쓰면,\n채널마다\n알아서 올라간다",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 문제장 — 힘들었던 점 먼저
        kor_title="글은 다 썼는데,\n올리는 게 또 일",
        body="채널이 늘수록\n인스타·블로그·카페에\n같은 내용을 형식 맞춰\n따로 또 따로 올렸어요.\n매일 반복되는 잡일이었어요.",
    ),
    dict(  # 3장 보완장 — 조용히, 자동으로 정리되게
        kor_title="그래서 한 번만\n점검하게 했어요",
        body="이제 한 번 검수하면\n채널별로 알아서 정리돼\n올라가게 해뒀어요.\n손으로 채널마다\n붙여넣던 일이 없어요.",
    ),
    dict(  # 4장 업그레이드① — 시간
        kor_title="더 나아진 점 ①\n시간이 사라졌다",
        body="올리는 데 들던 시간이\n거의 사라졌어요.\n한나절 걸리던 일이\n검수 한 번으로 끝나요.\n그만큼 다른 일을 해요.",
    ),
    dict(  # 5장 업그레이드② — 실수 없음
        kor_title="더 나아진 점 ②\n빠뜨림이 없다",
        body="빠뜨리는 채널·시간\n실수가 없어졌어요.\n늘 같은 품질로\n빠짐없이 나가요.\n(마지막 게시는 직접 확인도 해요.)",
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

    # 개인계정(namuk.wellperion) = 'W' 심볼만 미니멀 로고 (2026-06-02 GM 결정). 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 6장 = 시그니처(편별 제목, #11+ 실전 노선) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="올리는 일을 내려놓으니,\n내용에 더 집중하게 됐다",
        body=(
            "나중에 따라하려면 저장\n"
            "당신은 콘텐츠를 채널마다 따로 올리는 데 시간을 얼마나 쓰나요? 댓글로 알려주세요\n"
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
        slug="260623_AI22_글하나쓰면채널마다알아서올라",
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
