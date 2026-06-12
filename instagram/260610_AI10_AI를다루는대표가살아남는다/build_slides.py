# 260610 슬라이드 빌드 — AI를 다루는 대표가 살아남는다 (AI 시리즈 #10 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1~#9와 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-10 AI CMO 초안. 대체될 사람 vs 더 강해질 사람 — 가르는 건 'AI를 도구로 쓰는 능력'.
#  1 표지 / 2 다들 품는 불안 / 3 둘을 가르는 한 끗 / 4 도구로 쓴다는 게 뭔지 / 5 리더의 몫 / 6 마무리·CTA
# 직전 #9(북극성 항해 설계)와 차별화: #9=방향·나침반·여정. #10=대체 vs 강해짐·도구로 다루는 능력(중복 금지 점검 완료).
# 톤: 개인계정 GM 1인칭 솔직. 조직을 이끄는 리더 시점. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 복합 바이럴(저장+DM+함께 성장), litt.ly 미사용.
# 실행: .venv\Scripts\python instagram\260610_AI10_AI를다루는대표가살아남는다\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260610_AI10_AI를다루는대표가살아남는다"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-10-AI10-AI를다루는대표가살"
QUEUE_TITLE = "AI #10편 — AI를 다루는 대표가 살아남는다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "AI를 다루는 대표가 살아남는다 — 요즘 제가 가장 자주 하는 생각이에요.\n\n"
    "한동안 'AI가 내 일을 대신하면 어쩌지' 걱정했어요.\n"
    "근데 일을 시켜보니 알겠더라고요. AI는 자리를 뺏는 게 아니라, 쓰는 사람을 가른다는 걸요.\n\n"
    "대체될 사람과 더 강해질 사람을 가르는 건 딱 하나였어요.\n"
    "AI를 무서워하며 멀리 두느냐, 도구로 끌어다 쓰느냐.\n\n"
    "도구로 쓴다는 건 거창한 게 아니에요.\n"
    "막막한 일을 AI한테 먼저 꺼내 보고, 초안을 받아 제 손으로 다듬고, 맞는지 제가 확인하는 거예요.\n"
    "그러면 혼자 끙끙대던 일이 반나절 만에 끝나요. 저는 그만큼 더 중요한 결정에 시간을 써요.\n\n"
    "기계가 사람을 이기는 게 아니라, AI를 쓰는 사람이 안 쓰는 사람보다 멀리 가는 거예요.\n"
    "그래서 저는 직원들에게도 'AI를 무서워하지 말고 일단 시켜보라'고 말해요.\n\n"
    "AI를 다루는 대표가 살아남습니다.\n"
    "도움이 됐다면 저장해두고 딱 하나만 따라 해보세요.\n"
    "혼자 고민 말고 DM 주세요 — 아는 선에서 같이 풀어드릴게요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "#AI #AI활용 #리더십 #조직운영 #일하는방식 #대표일상 #스포츠클럽 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 불안 공감(2) + 한 끗 차이(3) + 도구로 쓴다는 것(4) + 리더의 몫(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 다들 품는 불안 → 둘을 가르는 한 끗 → 도구로 쓴다는 게 뭔지 → 리더의 몫 → 마무리
SLIDES = [
    dict(  # 1장 표지
        kor_title="AI를 다루는\n대표가 산다",
        eng_title="Use It, Don't Fear It",
    ),
    dict(  # 2장 다들 품는 불안 공감
        kor_title="다들 속으론\n불안해해요",
        body="\"AI가 내 일을\n대신하면 어쩌지.\"\n저도 한참 그 생각이었어요.\n근데 막상 시켜보니\n걱정의 방향이 틀렸더라고요.",
    ),
    dict(  # 3장 둘을 가르는 한 끗 — 대체 vs 강해짐
        kor_title="둘을 가르는\n건 한 끗이에요",
        body="AI는 자리를 뺏는 게 아니라\n쓰는 사람을 갈라요.\n무서워서 멀리 두는 사람과\n도구로 끌어다 쓰는 사람.\n나뉘는 지점은 딱 거기예요.",
    ),
    dict(  # 4장 '도구로 쓴다'는 게 뭔지
        kor_title="도구로 쓴다는\n게 뭐냐면요",
        body="거창한 거 아니에요.\n막막한 일을 먼저 꺼내 보고,\n초안을 받아 손으로 다듬고,\n맞는지 내가 확인하는 거예요.\n반나절이면 끝나더라고요.",
    ),
    dict(  # 5장 리더의 몫
        kor_title="그게 리더의\n몫이더라고요",
        body="기계가 사람을 이기는 게 아니라\n쓰는 사람이 더 멀리 가요.\n그래서 직원들에게도 말해요.\n무서워 말고 일단 시켜보라고.\n같이 강해지자고요.",
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
    # 기존 개인계정 발행분과 동일 처리. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 시그니처 슬로건 고정(2026-06-04 GM 지시 — 전 편 공통) + 복합 바이럴 CTA(2026-06-05 GM 결정)
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

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260610_AI10_AI를다루는대표가살아남는다",
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
