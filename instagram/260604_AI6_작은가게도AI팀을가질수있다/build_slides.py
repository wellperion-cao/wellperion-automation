# 260604 슬라이드 빌드 — 작은 가게도 AI 팀을 가질 수 있다 (AI 시리즈 #6 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1·#2·#3·#4·#5와 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-04 AI CMO 초안. 규모의 벽이 무너진다 — 1명도 '팀'처럼 일한다.
#  1 표지 / 2 예전엔 사람이 곧 규모 / 3 지금은 1명이 팀처럼 / 4 내 가게 적용 예 / 5 그래서 달라진 것 / 6 마무리·CTA(시그니처)
# 톤: 개인계정 GM 1인칭 솔직 보이스. 생각 리더십. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 직전 #5(한계·오해)와 차별: #5=도구의 한계/시키는 법 / #6=규모의 벽 붕괴/작은 곳도 팀처럼. 표현 중복 금지.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 함께 성장합시다 + DM 주세요(litt.ly 미사용).
# 실행: .venv\Scripts\python instagram\260604_AI6_작은가게도AI팀을가질수있다\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260604_AI6_작은가게도AI팀을가질수있다"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-04-AI6-작은가게도AI팀을가"
QUEUE_TITLE = "AI #6편 — 작은 가게도 AI 팀을 가질 수 있다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = ["dietcamp_pt", "na_daeng", "wellperion"]

CAPTION = (
    "작은 가게도 'AI 팀'을 가질 수 있어요 — 제가 겪은 변화입니다.\n\n"
    "예전엔 일이 늘면 사람을 더 뽑아야 했어요.\n"
    "사람이 곧 규모였고, 작은 곳은 늘 손이 모자랐죠.\n\n"
    "그런데 지금은 달라요.\n"
    "기획을 거드는 손, 글을 다듬는 손, 숫자를 정리하는 손,\n"
    "이걸 AI가 동시에 거들어줘요.\n"
    "혼자여도 여러 명이 함께 일하는 것처럼요.\n\n"
    "큰 회사만 누리던 '팀'을, 이제 작은 가게도 가질 수 있어요.\n"
    "규모의 벽이 무너지고 있는 거예요.\n\n"
    "대신 방향을 정하고, 일을 나누고, 결과를 챙기는 건 여전히 사람 몫이에요.\n"
    "그 자리에 앉는 대표가 작아도 강해집니다.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "운동시설 대표님, DM 주세요. 아는 선에선 돕겠습니다.\n\n"
    "#AI #AI활용 #소상공인 #1인기업 #작은가게 #스포츠클럽 #일하는방식 #대표일상 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전엔사람이규모(2) + 지금은1명이팀처럼(3) + 내가게적용(4) + 달라진것(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 옛 방식(사람=규모) → 변화(1명이 팀처럼) → 구체 적용 → 그래서 달라진 것 → 마무리
SLIDES = [
    dict(  # 1장 표지
        kor_title="작은 가게도\nAI 팀을 가질 수 있다",
        eng_title="A Team of One",
    ),
    dict(  # 2장 예전엔 사람이 곧 규모
        kor_title="예전엔 사람이\n곧 규모였어요",
        body="일이 늘면\n사람을 더 뽑아야 했어요.\n작은 곳은 늘 손이 모자랐죠.\n큰 회사만 '팀'을 가졌어요.\n작은 가게는 늘 혼자 싸웠어요.",
    ),
    dict(  # 3장 지금은 1명이 팀처럼
        kor_title="지금은 1명도\n팀처럼 일해요",
        body="기획을 거드는 손,\n글을 다듬는 손,\n숫자를 정리하는 손.\nAI가 동시에 거들어줘요.\n혼자여도 여럿이 함께 일하듯이.",
    ),
    dict(  # 4장 내 가게 적용 예
        kor_title="제 가게엔\n이렇게 들어왔어요",
        body="· 안내문·공지는 같이 써요\n· 회원 응대 문구를 다듬어요\n· 매출·예약 숫자를 정리해요\n사람 여럿이 할 일을,\n혼자서도 돌릴 수 있게 됐어요.",
    ),
    dict(  # 5장 그래서 달라진 것 — 규모의 벽 붕괴 + 사람 몫
        kor_title="그래서\n무엇이 달라졌나",
        body="작아도 큰 곳처럼 일해요.\n규모의 벽이 무너지고 있어요.\n대신 방향을 정하고, 일을 나누고,\n결과를 챙기는 건 사람 몫이에요.\n그 자리에 앉는 대표가 강해져요.",
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
    # 기존 개인계정 발행분(왜AI·AI직원효율·입문편·역할분담·깨진환상)과 동일 처리. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 시그니처 슬로건 고정(2026-06-04 GM 지시 — 전 편 공통) + 함께 성장 + DM 유도
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="AI를 다루는 대표가\n살아남는다",
        body="규모가 작아도 괜찮아요.\nAI를 팀처럼 쓰면 작아도 강해져요.\n완벽하진 않아도, 함께 성장합시다.\n\n운동시설 대표님, 궁금하면\nDM 주세요. 아는 선에선 돕겠습니다.",
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
        slug="260604_AI6_작은가게도AI팀을가질수있다",
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
