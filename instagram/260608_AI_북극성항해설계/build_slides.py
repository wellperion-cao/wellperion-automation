# 260608 슬라이드 빌드 — 북극성 항해 설계: AI와 함께 방향을 잃지 않고 매일 나아간다 (AI 시리즈 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-08 AI CMO. 북극성=목적지(비전), 항해=여정, 항로=오늘 할 일, 배=미션/프로젝트.
# AI가 매일의 '항로'를 정리해줘서 큰 그림(북극성)을 잃지 않고 매일 한 걸음 나아간다.
# ⚠️ 공개 IG용 — 내부 전문용어(항로점·표류 등) 금지. 항해 '비유'로 방향성·리더십 쉽게 전달.
# 1 표지 / 2 리더의 고민(방향을 잃기 쉽다) / 3 북극성=목적지, 항해=여정 비유 / 4 AI가 오늘 항로를 정리해준다 / 5 매일 한 걸음, 방향을 잃지 않는다 / 6 시그니처 슬로건
# 톤: 개인계정 GM 1인칭 진솔. 조직을 이끄는 리더. '혼자/작은가게/1인기업/소상공인' 금지.
# 로고: W 심볼만(logo_style="symbol"). CTA: 복합 바이럴, litt.ly 미사용.
# 실행: .venv\Scripts\python instagram\260608_AI_북극성항해설계\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260608_AI_북극성항해설계"
OUT = FOLDER / "output"

QUEUE_ID = "CMO-2026-06-08-AI-북극성항해설계"
QUEUE_TITLE = "AI #8편 — 북극성 항해 설계(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []

CAPTION = (
    "북극성 항해 설계 — AI와 함께 방향을 잃지 않고 매일 나아가는 법.\n\n"
    "리더로 살다 보면 이런 날이 있어요.\n"
    "열심히 했는데, 어느 순간 '지금 어디로 가고 있지?' 싶은 날.\n"
    "바쁜 건 분명한데, 방향을 잃은 것 같은 느낌.\n\n"
    "저는 이걸 '항해'로 생각하게 됐어요.\n"
    "북극성 = 내가 가려는 목적지(우리 조직이 지향하는 비전).\n"
    "항해 = 그곳으로 가는 전체 여정.\n"
    "오늘 가는 뱃길 = 오늘 내가 실제로 움직일 일들.\n\n"
    "문제는 매일 파도가 치면 북극성을 잊기 쉽다는 거예요.\n"
    "긴급한 일에 치이다 보면 '오늘 어디로 가야 하지?'가 흐릿해져요.\n\n"
    "그래서 저는 AI한테 매일 아침 한 가지를 시켜요.\n"
    "\"오늘 북극성 방향으로 한 걸음, 가장 중요한 게 뭐야?\"\n"
    "AI가 지난 흐름을 보고 오늘 가야 할 뱃길을 정리해줘요.\n"
    "그걸 보면 오늘 하루가 선명해져요.\n\n"
    "방향이 있는 사람이 멀리 갑니다.\n"
    "AI는 그 방향을 매일 다시 잡아주는 나침반이에요.\n\n"
    "AI를 다루는 대표가 살아남습니다.\n"
    "도움이 됐다면 저장해두고 딱 하나만 따라 해보세요.\n"
    "혼자 고민 말고 DM 주세요 — 아는 선에서 같이 풀어드릴게요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "#AI #AI활용 #리더십 #방향성 #비전 #조직운영 #대표일상 #스포츠클럽 #한남동 #웰페리온"
)

SLIDES = [
    dict(  # 1장 표지
        kor_title="북극성\n항해 설계",
        eng_title="Navigate by the North Star",
    ),
    dict(  # 2장 리더의 고민 — 방향을 잃기 쉽다
        kor_title="열심히 했는데\n어디로 가고 있지?",
        body="바쁜 건 분명해요.\n그런데 어느 순간\n'지금 제대로 가고 있나?' 싶을 때\n리더라면 한 번쯤 느껴봤을 거예요.",
    ),
    dict(  # 3장 항해 비유 — 북극성=목적지, 항해=여정
        kor_title="저는 이걸\n항해로 생각해요",
        body="북극성 = 우리가 가려는 목적지.\n항해 = 그곳으로 가는 전체 여정.\n오늘 가는 뱃길 = 오늘 실제로\n움직일 일들이에요.",
    ),
    dict(  # 4장 AI가 오늘 항로를 정리해준다
        kor_title="AI가 매일 아침\n뱃길을 정리해줘요",
        body="\"오늘 북극성 방향으로\n가장 중요한 게 뭐야?\"\nAI가 흐름을 보고 오늘 할 일을\n정리해줘요. 하루가 선명해져요.",
    ),
    dict(  # 5장 매일 한 걸음, 방향을 잃지 않는다
        kor_title="매일 한 걸음\n방향을 잃지 않아요",
        body="긴급한 일에 치여도\n북극성은 안 잃어요.\nAI가 매일 아침 나침반처럼\n방향을 다시 잡아주니까요.",
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
        slug="260608_AI_북극성항해설계",
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
