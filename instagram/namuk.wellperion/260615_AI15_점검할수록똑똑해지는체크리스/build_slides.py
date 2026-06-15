# 260615 슬라이드 빌드 — 점검할수록 똑똑해지는 체크리스트 (AI 시리즈 #15 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-15 AI CMO 초안. 시즌2(실전편) — 폰 체크→자동 집계, 발견한 문제는 원클릭으로 점검항목 승격 → 다음 회차부터 자동 등장(같은 문제 두 번 안 놓치는 루프).
#  실재: 지원부 이슈→원클릭 점검항목 승격, coo/check/지원부 체계.html (2026-06-11 출시).
#  1 표지(SEASON2 라벨) / 2 예전 점검의 한계 / 3 지금=폰 체크·자동집계 / 4 발견한 문제=버튼 하나로 항목추가 / 5 다음 회차부터 자동 등장(루프) / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭, 조직을 이끄는 리더. how-to. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 GM 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260615_AI15_점검할수록똑똑해지는체크리스\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260615_AI15_점검할수록똑똑해지는체크리스"
OUT = FOLDER / "output"

# 시즌2(실전편) 공통 라벨 — 표지 eng_sub 자리 텍스트 (로드맵 §2.6 단일출처)
SEASON2_LABEL = "SEASON 2 · 실전편"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-15-AI15-점검할수록똑똑해지는"
QUEUE_TITLE = "AI #15편 — 점검할수록 똑똑해지는 체크리스트(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "AI를 왜·무엇에 쓰는지는 지난 10편(시즌1)에서 끝냈습니다. 이번 시즌2부터는 오늘 바로 따라하는 법만 답니다.\n\n"
    "오늘은 '점검 체크리스트' 이야기예요.\n\n"
    "예전엔 점검하다 문제를 발견해도 메모지에 적고 끝이었어요.\n"
    "다음 점검 때 같은 문제를 또 놓쳤죠.\n\n"
    "지금은 현장에서 폰으로 체크만 해요.\n"
    "결과는 자동으로 모이고, 어디가 됐는지 한눈에 정리돼요.\n\n"
    "점검 중 새 문제를 발견하면 버튼 하나로 점검표에 항목을 추가해요.\n"
    "그 항목은 다음 회차부터 저절로 떠요.\n"
    "그래서 같은 문제를 두 번 놓치지 않아요.\n\n"
    "점검할수록 체크리스트가 똑똑해지는 셈이죠.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 점검 중 같은 문제를 또 놓친 적 있나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지(영문/라벨 대제목 + 한글 부제), 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전한계(2) + 폰체크·자동집계(3) + 버튼하나로항목추가(4) + 다음회차자동등장(5) + 마무리/CTA(6, main() 별도)
# 표지 eng_title 자리에 SEASON2_LABEL 텍스트만(별도 그래픽 뱃지 합성 없음). 시즌2 전 편 공통.
SLIDES = [
    dict(  # 1장 표지 (시즌2 라벨 + 한글 제목)
        kor_title="점검할수록\n똑똑해지는 체크리스트",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 예전 점검의 한계
        kor_title="예전엔 점검이\n그냥 끝이었어요",
        body="종이에 체크하고 끝.\n문제를 발견해도\n메모지에 적으면 잊혀요.\n다음 점검 때\n같은 문제를 또 놓쳤어요.",
    ),
    dict(  # 3장 지금 = 폰 체크 · 자동 집계
        kor_title="지금은 폰으로\n체크만 해요",
        body="현장에서 폰으로 탁탁 체크.\n결과는 자동으로 모여요.\n어디가 됐고 안 됐는지\n한눈에 정리돼요.\n수기 집계가 사라졌어요.",
    ),
    dict(  # 4장 발견한 문제 = 버튼 하나로 항목 추가
        kor_title="문제를 찾으면\n버튼 하나",
        body="점검 중 새 문제를 발견하면\n버튼 하나로\n점검표에 항목을 더해요.\n따로 적어둘 필요가 없어요.",
    ),
    dict(  # 5장 다음 회차부터 자동 등장 (루프)
        kor_title="다음 점검부터\n자동으로 떠요",
        body="더한 항목이\n다음 회차부터 저절로 나와요.\n그래서 같은 문제를\n두 번 놓치지 않아요.\n점검할수록 똑똑해져요.",
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
        kor_title="놓친 문제는\n다음 항목이 된다",
        body="나중에 따라하려면 저장\n점검 중 같은 문제를 또 놓친 적 있나요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260615_AI15_점검할수록똑똑해지는체크리스",
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
