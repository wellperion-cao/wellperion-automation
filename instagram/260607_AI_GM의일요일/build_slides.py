# 260607 슬라이드 빌드 — GM의 일요일: AI가 놓친 것들을 챙겨주는 일요일 아침 (AI 시리즈 일요일 특별편 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-07(일) AI CMO. 핵심 = AI가 평일에 내가 놓친 것들을 한눈에 모아준다 → 일요일 아침 차분히 따라잡는다 → 월요일이 가볍다.
# "AI가 대신 일한다/당직 선다" 금지. AI = 빠짐없이 챙겨주는 나만의 비서.
# 1 표지 / 2 평일엔 놓치는 게 쌓인다(공감) / 3 일요일 아침 AI가 한눈에 모아준다 / 4 우선순위 잡아 차분히 처리·위임 / 5 월요일이 가볍다 / 6 시그니처 슬로건
# 톤: 개인계정 GM 1인칭 진솔. 조직을 이끄는 리더. '혼자/작은가게/1인기업/소상공인' 금지.
# 로고: W 심볼만(logo_style="symbol"). CTA: 복합 바이럴, litt.ly 미사용.
# 실행: .venv\Scripts\python instagram\260607_AI_GM의일요일\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260607_AI_GM의일요일"
OUT = FOLDER / "output"

QUEUE_ID = "CMO-2026-06-07-AI-GM의일요일"
QUEUE_TITLE = "AI 일요일 특별편 — GM의 일요일(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []

CAPTION = (
    "GM의 일요일 — 일요일 아침, AI가 이번 주 놓친 것들을 챙겨줍니다.\n\n"
    "평일엔 바쁘다 보면 어쩔 수 없이 놓치는 게 생겨요.\n"
    "못 본 보고, 답 못한 메시지, 마음에 걸렸던 회원분,\n"
    "내일 해야지 미뤄둔 결정들.\n"
    "하나하나는 작은데, 쌓이면 머리가 무거워져요.\n\n"
    "그래서 저는 일요일 아침을 AI와 함께 시작해요.\n"
    "커피 한 잔 내려놓고 열면, AI가 이번 주 남은 것들을\n"
    "한 곳에 정리해서 보여줘요.\n"
    "빠짐없이, 우선순위 순서대로요.\n\n"
    "그걸 보면서 차분하게 정리해요.\n"
    "오늘 내가 직접 처리할 것, 팀에 넘길 것, 다음 주로 넘길 것.\n"
    "30분이면 머릿속이 한결 가벼워져요.\n\n"
    "그러면 월요일 아침이 달라요.\n"
    "쌓인 게 없으니까요.\n"
    "AI가 완벽한 비서처럼 놓친 것들을 챙겨준 덕분에요.\n\n"
    "AI를 다루는 대표가 살아남습니다.\n"
    "도움이 됐다면 저장해두고 딱 하나만 따라 해보세요.\n"
    "혼자 고민 말고 DM 주세요 — 아는 선에서 같이 풀어드릴게요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "#AI #AI활용 #일요일 #리더십 #조직운영 #대표일상 #시간관리 #스포츠클럽 #한남동 #웰페리온"
)

SLIDES = [
    dict(  # 1장 표지
        kor_title="GM의\n일요일",
        eng_title="GM's Sunday Ritual",
    ),
    dict(  # 2장 평일엔 놓치는 게 쌓인다
        kor_title="평일엔\n놓치는 게 쌓여요",
        body="바쁘다 보면 어쩔 수 없어요.\n못 본 보고, 답 못한 메시지,\n마음에 걸렸던 회원분,\n미뤄둔 결정들이 쌓여요.",
    ),
    dict(  # 3장 일요일 아침 AI가 한눈에 모아준다
        kor_title="AI가 한눈에\n모아줘요",
        body="일요일 아침, 커피 한 잔 들고 열면\nAI가 이번 주 남은 것들을\n빠짐없이 정리해서 보여줘요.\n우선순위 순서대로요.",
    ),
    dict(  # 4장 차분하게 처리·위임
        kor_title="차분하게\n정리합니다",
        body="오늘 내가 직접 할 것,\n팀에 넘길 것, 다음 주로 넘길 것.\n30분이면 머릿속이\n한결 가벼워져요.",
    ),
    dict(  # 5장 월요일이 달라진다
        kor_title="그러면\n월요일이 달라요",
        body="쌓인 게 없으니까요.\nAI가 빠짐없이 챙겨준 덕에\n월요일 아침을 무거움 없이\n시작할 수 있어요.",
    ),
]


def build_montage(paths: list[Path], out_path: Path, cols: int = 3) -> None:
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
    for old in OUT.glob("post_*"):
        old.unlink()
    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="AI를 다루는 대표가\n살아남는다",
        body="막막하면 일단 저장해두세요.\n딱 하나만 따라 해도 바뀝니다.\n혼자 고민 말고 DM 주세요.\n아는 선에서 같이 풀어드릴게요.",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")

    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260607_AI_GM의일요일",
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
