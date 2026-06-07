# 260607 슬라이드 빌드 — 대표의 일요일: AI가 당직 서는 동안, 나는 진짜 쉰다 (AI 시리즈 일요일 특별편 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1~#7과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-07(일) AI CMO. 쉬는 날에도 보고·콘텐츠·문의가 안 멈추는 건 AI가 당직을 서기 때문 →
#  대표가 죄책감 없이 충전한다 → AI 도입의 진짜 가치 = '시간·여백'. 일요일의 구체 장면 중심.
#  1 표지 / 2 일요일 늦잠(폰엔 AI 한 줄) / 3 AI가 당직 선다 / 4 그 사이 나는 가족·산책 / 5 진짜 가치=여백 / 6 마무리·CTA
# 차별화: #7(평일 하루 비포/애프터)·#8(피날레 '살아남는다')과 메시지 겹치지 않게 — 이번 편은 '쉬는 날·여백'에 집중.
# 화자 = 조직(대표+직원+실무팀)을 이끄는 리더 1인칭. '혼자/작은가게/1인기업/소상공인' 프레임 금지.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 복합 바이럴(저장+DM+함께 성장), litt.ly 미사용.
# 실행: .venv\Scripts\python instagram\260607_AI_대표의일요일\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260607_AI_대표의일요일"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-07-AI-대표의일요일"
QUEUE_TITLE = "AI 일요일 특별편 — 대표의 일요일(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "대표의 일요일 — AI가 당직 서는 동안, 저는 진짜 쉽니다.\n\n"
    "오늘은 일요일, 제가 쉬는 날이에요.\n"
    "예전엔 쉬는 날에도 마음이 안 놓였어요.\n"
    "보고는 누가 챙기지, 문의는 누가 답하지, 콘텐츠는 또 누가.\n"
    "결국 폰을 손에서 못 놨죠.\n\n"
    "지금은 달라요.\n"
    "제가 늦잠을 자도 어젯밤 일은 AI가 정리해 한 줄로 와 있고,\n"
    "주말 문의도 1차 안내는 끊기지 않아요.\n"
    "콘텐츠도 정해둔 대로 제 자리를 지켜요.\n\n"
    "그 사이 저는 진짜로 쉬어요.\n"
    "가족이랑 늦은 아침을 먹고, 동네 한 바퀴를 걷고,\n"
    "폰은 주머니에 그냥 둬요. 급하면 한 줄이 알려주니까요.\n\n"
    "그제야 알았어요.\n"
    "AI를 들인 진짜 이유는 '일을 더 하려고'가 아니라,\n"
    "마음 놓고 쉴 '여백'을 만들려고였다는 걸.\n"
    "쉬어야 멀리 갑니다. 그 여백을 AI가 지켜줘요.\n\n"
    "AI를 다루는 대표가 살아남습니다.\n"
    "도움이 됐다면 저장해두고 딱 하나만 따라 해보세요.\n"
    "혼자 고민 말고 DM 주세요 — 아는 선에서 같이 풀어드릴게요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "#AI #AI활용 #일요일 #쉼 #워라밸 #리더십 #조직운영 #대표일상 #스포츠클럽 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 일요일아침(2) + AI당직(3) + 그사이나는(4) + 진짜가치여백(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 쉬는 날인데 마음 못 놓던 나 → AI가 당직을 선다 → 그 사이 가족·산책·충전 → 진짜 가치는 '여백' → 마무리
SLIDES = [
    dict(  # 1장 표지
        kor_title="대표의\n일요일",
        eng_title="A Founder's Sunday",
    ),
    dict(  # 2장 예전엔 쉬는 날에도 마음을 못 놨다
        kor_title="쉬는 날에도\n마음이 안 놨어요",
        body="일요일에도 자꾸 폰을 봤어요.\n보고는 누가, 문의는 누가,\n콘텐츠는 또 누가 챙기지.\n쉬어도 쉰 것 같지 않았어요.",
    ),
    dict(  # 3장 지금은 AI가 당직을 선다
        kor_title="지금은 AI가\n당직을 서요",
        body="어젯밤 일은 한 줄로 정리돼 오고\n주말 문의 1차 안내도 안 끊겨요.\n콘텐츠는 정해둔 대로 제자리.\n제가 안 봐도 멈추지 않아요.",
    ),
    dict(  # 4장 그 사이 나는 진짜로 쉰다
        kor_title="그 사이\n저는 진짜 쉬어요",
        body="가족이랑 늦은 아침을 먹고\n동네 한 바퀴를 걸어요.\n폰은 주머니에 그냥 둬요.\n급하면 한 줄이 알려주니까요.",
    ),
    dict(  # 5장 깨달음 — 진짜 가치는 '여백'
        kor_title="진짜 가치는\n'여백'이었어요",
        body="AI를 들인 건 일을 더 하려고가\n아니라, 마음 놓고 쉴 여백을\n만들려고였어요.\n쉬어야 멀리 갑니다.",
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
        slug="260607_AI_대표의일요일",
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
