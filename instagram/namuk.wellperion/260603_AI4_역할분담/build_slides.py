# 260603 슬라이드 빌드 — 뭘 맡기고, 뭘 내가 하나: WHAT I LET AI DO (AI 시리즈 #4 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1·#2·#3과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-03 GM 직접 확정. 역할 분담편 — 반복은 AI, 결정은 사람.
#  1 표지 / 2 헷갈림 공감 / 3 쉬운 기준 한 줄 / 4 AI가 하는 일 / 5 내가 하는 일 / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직 공유. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: DM 문의 + '함께 성장합시다'(litt.ly 미사용).
# 실행: .venv\Scripts\python instagram\260603_AI4_역할분담\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402  (FIX3 제작완료 자동 등록·알림)

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260603_AI4_역할분담"
OUT = FOLDER / "output"

# (FIX3) 제작완료 자동 등록용 메타 — 기존 M5 큐 엔트리와 id 일치(중복 아닌 갱신).
# 이미 '발행완료' 인 엔트리는 register_publish 내부에서 status 강등 안 됨(회귀 가드).
QUEUE_ID = "CMO-2026-06-03-AI4-역할분담"
QUEUE_TITLE = "AI #4편 — 역할 분담(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = ["dietcamp_pt", "na_daeng", "wellperion"]
# 캡션 SSOT = 큐레이션_추천.md / review_queue 와 동일 본문(개인계정 톤·DM CTA).
CAPTION = (
    "뭘 맡기고, 뭘 내가 하나 — AI와 역할 분담하는 제 방식.\n\n"
    "처음엔 정말 헷갈렸어요. AI를 켜놓고도 '이걸 시켜도 되나?' 한참 망설였거든요.\n"
    "그러다 찾은 기준이 하나예요. '어, 이거 또 하네?' 싶은 건 AI한테, "
    "'이건 내가 정해야지' 싶은 건 제가.\n반복은 AI, 결정은 저.\n\n"
    "AI한테 맡기는 것들: 인스타·블로그 글 초안, 매일 보고 취합·정리, "
    "매출·출결 집계, 검수 자료 정리.\n"
    "제가 하는 것들: 직원·회원과 직접 소통, 마지막 검수와 최종 결정, 요즘 트렌드 파악.\n\n"
    "AI한테 반복을 넘기면, 제 손엔 진짜 중요한 일만 남더라고요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "운동시설 대표님, 궁금하시면 DM 주세요. 아는 선에선 돕겠습니다.\n\n"
    "#AI #AI활용 #역할분담 #스포츠클럽 #일하는방식 #대표일상 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 헷갈림(2) + 기준(3) + AI가 하는 일(4) + 내가 하는 일(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 헷갈림 공감 → 쉬운 기준 → AI가 하는 일 → 내가 하는 일 → 마무리 (점층)
SLIDES = [
    dict(  # 1장 표지
        kor_title="뭘 맡기고,\n뭘 내가 하나",
        eng_title="What I Let AI Do",
    ),
    dict(  # 2장 헷갈림 공감
        kor_title="처음엔 헷갈렸어요\n뭘 맡겨야 하지?",
        body="AI를 켜놓고도\n한참 망설였어요.\n이건 시켜도 되나?\n이건 내가 해야 하나?\n경계가 잘 안 보이더라고요.",
    ),
    dict(  # 3장 쉬운 기준 한 줄
        kor_title="제 기준은\n딱 하나예요",
        body="'어, 이거 또 하네?'\n싶은 일은 AI한테.\n'이건 내가 정해야지'\n싶은 일은 제가.\n반복은 AI, 결정은 저예요.",
    ),
    dict(  # 4장 AI가 하는 일 — 구체 목록
        kor_title="이런 건\nAI가 해요",
        body="· 인스타·블로그 글 초안\n· 매일 보고 취합·정리\n· 매출·출결 숫자 집계\n· 검수 자료 정리\n손 많이 가는 반복 일이요.",
    ),
    dict(  # 5장 내가 하는 일 — 구체 목록
        kor_title="이런 건\n제가 해요",
        body="· 직원·회원과 직접 소통\n· 마지막 검수와 최종 결정\n· 요즘 트렌드 파악\n결국 사람 몫은 제가 해요.",
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
    # 기존 개인계정 발행분(왜AI·AI직원효율·입문편)과 동일 처리. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 슬로건 + 같이 성장 + DM 유도 (GM 사양)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="AI를 다루는 대표가\n살아남는다",
        body="AI한테 반복을 넘기면\n제 손엔 진짜 중요한 일만 남아요.\n완벽하진 않아도, 함께 성장합시다.\n\n운동시설 대표님, 궁금하시면\nDM 주세요. 아는 선에선 돕겠습니다.",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")

    # (FIX3) 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    # slides 는 ROOT 기준 정방향 슬래시 상대경로. 헬퍼가 어떤 단계 실패해도 빌드는 안 깨짐.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260603_AI4_역할분담",
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
