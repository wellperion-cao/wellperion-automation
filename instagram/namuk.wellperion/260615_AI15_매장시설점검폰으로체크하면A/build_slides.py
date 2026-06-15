# 260615 슬라이드 빌드 — 매장·시설 점검을 폰으로 체크하면 AI가 자동 집계·이상치까지 (AI 시리즈 #15 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-15 AI CMO 초안. 시즌2(실전편) 도입 첫 편 — 종이·기억 → 폰 체크리스트 → AI 자동집계·이상치.
# 근거: 지원부 점검 시스템 실제 가동(폰 체크 → 자동 집계 → 빠진 항목·이상치 알림).
#  1 표지 / 2 예전엔 종이·기억 / 3 지금은 폰 체크 / 4 AI 자동 집계·빠진 항목 / 5 이상치 알림 / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭, 실전 how-to. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 GM 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260615_AI15_매장시설점검폰으로체크하면A\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260615_AI15_매장시설점검폰으로체크하면A"
OUT = FOLDER / "output"

# 시즌2(실전편) 라벨 — 표지 부제(eng_title) 자리에 텍스트 한 줄. 로드맵 §2.6 단일출처.
SEASON2_LABEL = "SEASON 2 · 실전편"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-15-AI15-매장시설점검폰으로체"
QUEUE_TITLE = "AI #15편 — 시설 점검 폰 체크→AI 자동집계·이상치(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "AI를 왜·무엇에 쓰는지는 지난 10편(시즌1)에서 끝냈습니다. 이번 시즌2부터는 오늘 바로 따라하는 법만 답니다.\n\n"
    "오늘은 매장·시설 점검 이야기예요.\n\n"
    "예전엔 점검을 종이에 적거나 그냥 머리로 기억했어요.\n"
    "빠뜨려도 몰랐고, 모아 보려면 일일이 다시 세야 했어요.\n\n"
    "지금은 폰으로 항목을 하나씩 눌러 체크해요.\n"
    "적는 게 아니라 누르는 거라 현장에서 바로 끝나요.\n\n"
    "체크가 끝나면 AI가 결과를 자동으로 모아요.\n"
    "빠진 항목이 있으면 '여기 안 했어요' 하고 바로 짚어줘요.\n\n"
    "늘 보던 값이랑 크게 다른 게 나오면\n"
    "AI가 '이거 좀 이상해요' 하고 표시해줘요.\n"
    "눈으로 놓칠 걸 잡아주는 거예요.\n\n"
    "점검은 폰이 받아 적고, 이상한 건 AI가 걸러주고,\n"
    "판단은 제가 해요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 점검, 아직 종이로 하세요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전엔종이·기억(2) + 지금은폰체크(3) + AI자동집계·빠진항목(4) + 이상치알림(5) + 마무리/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지 (eng_title 자리 = 시즌2 라벨 텍스트)
        kor_title="시설 점검을\n폰으로 바꿨더니",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 예전엔 종이·기억
        kor_title="예전엔 종이랑\n기억에 맡겼어요",
        body="점검을 종이에 적거나\n그냥 머리로 기억했어요.\n빠뜨려도 몰랐고,\n모아 보려면\n일일이 다시 세야 했어요.",
    ),
    dict(  # 3장 지금은 폰 체크
        kor_title="지금은 폰으로\n체크만 해요",
        body="항목을 폰에서\n하나씩 눌러 체크해요.\n적는 게 아니라\n누르는 거라\n현장에서 바로 끝나요.",
    ),
    dict(  # 4장 AI 자동 집계 + 빠진 항목
        kor_title="AI가 알아서\n모아줘요",
        body="체크가 끝나면\nAI가 결과를 자동으로 모아요.\n빠진 항목이 있으면\n'여기 안 했어요' 하고\n바로 짚어줘요.",
    ),
    dict(  # 5장 이상치 알림
        kor_title="평소랑 다르면\n알려줘요",
        body="늘 보던 값이랑\n크게 다른 게 나오면\nAI가 '이거 좀 이상해요' 하고\n표시해줘요.\n눈으로 놓칠 걸 잡아줘요.",
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
        kor_title="점검은 폰이,\n판단은 사람이",
        body="나중에 따라하려면 저장\n점검 아직 종이로 하세요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260615_AI15_매장시설점검폰으로체크하면A",
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
