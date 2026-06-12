# 260606 슬라이드 빌드 — AI를 쓰고 바뀐 내 하루: 도입 전후 실제 장면 비교 (AI 시리즈 #7 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분 #1~#6과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-06 AI CMO 초안. 전후 비교편 — 집계·보고서에 치이던 하루 → 회원·결정에 쓰는 하루.
#  1 표지 / 2 예전 하루(집계·보고서에 치임) / 3 바뀐 지점(반복은 AI가) / 4 지금 하루(회원·결정) / 5 진짜 달라진 것(시간의 쓸모) / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직 고백. 실제 하루 장면으로 전후 비교. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# #6(작은 가게도 AI 팀)과 차별화 = '규모의 벽' 메시지 금지, 오직 '내 하루 시간의 쓸모'에 집중.
# 화자 = 조직(대표+직원+실무팀)을 이끄는 리더 1인칭. '혼자/작은가게/1인기업/소상공인' 프레임 금지.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 복합 바이럴(저장+DM+함께 성장), litt.ly 미사용.
# 실행: .venv\Scripts\python instagram\260606_AI7_AI를쓰고바뀐내하루\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "260606_AI7_AI를쓰고바뀐내하루"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-06-AI7-AI를쓰고바뀐내하루"
QUEUE_TITLE = "AI #7편 — AI를 쓰고 바뀐 내 하루(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "AI를 쓰고 바뀐 내 하루 — 솔직하게 보여드릴게요.\n\n"
    "예전 제 하루는 숫자랑 씨름하는 시간이었어요.\n"
    "아침에 출근하면 어제 무슨 일이 있었는지 집계부터 했어요.\n"
    "표 만들고, 보고서 정리하고, 같은 내용 채널마다 다시 옮기고.\n"
    "그러다 보면 정작 회원분들 얼굴 볼 시간이 없었어요.\n\n"
    "지금은 그 반복을 AI한테 넘겼어요.\n"
    "어제 일은 아침에 정리돼서 제 앞에 와 있어요.\n"
    "저는 그걸 보고 '오늘 뭘 할지' 결정만 하면 돼요.\n\n"
    "그래서 하루의 쓸모가 바뀌었어요.\n"
    "집계·보고서에 쓰던 시간을, 이제 회원분들과 결정에 써요.\n"
    "어떤 분이 요즘 안 오시는지, 무엇을 더 챙겨드릴지 들여다봐요.\n"
    "리더가 진짜 해야 할 일에 시간을 돌려받은 거예요.\n\n"
    "AI를 다루는 대표가 살아남습니다.\n"
    "도움이 됐다면 저장해두고 딱 하나만 따라 해보세요.\n"
    "혼자 고민 말고 DM 주세요 — 아는 선에서 같이 풀어드릴게요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "#AI #AI활용 #스포츠클럽 #리더십 #조직운영 #대표일상 #일하는방식 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 예전하루(2) + 바뀐지점(3) + 지금하루(4) + 시간의쓸모(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 숫자에 치이던 하루 → 반복을 AI에 넘김 → 회원·결정에 쓰는 하루 → 시간의 쓸모가 바뀜 → 마무리
SLIDES = [
    dict(  # 1장 표지
        kor_title="AI를 쓰고\n바뀐 내 하루",
        eng_title="My Day, Rewired",
    ),
    dict(  # 2장 예전 하루 — 집계·보고서에 치임
        kor_title="예전 제 하루는\n이랬어요",
        body="출근하면 숫자부터 모았어요.\n어제 무슨 일이 있었나,\n표 만들고 보고서 정리하고.\n그러다 보면 하루가 다 갔어요.\n정작 회원분 볼 시간이 없었죠.",
    ),
    dict(  # 3장 바뀐 지점 — 반복을 AI에 넘김
        kor_title="그 반복을\nAI한테 넘겼어요",
        body="매일 똑같이 하던 집계랑 정리,\n이젠 AI가 아침에 해둬요.\n제가 켜면 이미 끝나 있어요.\n저는 그걸 '읽기만' 하면 돼요.\n손이 아니라 머리를 쓰게 됐어요.",
    ),
    dict(  # 4장 지금 하루 — 회원·결정에 씀
        kor_title="지금 제 하루는\n이래요",
        body="정리된 걸 보고 결정만 해요.\n'오늘은 이걸 챙기자' 하고요.\n남는 시간엔 회원분을 봐요.\n요즘 누가 안 오시는지,\n무엇을 더 해드릴지 들여다봐요.",
    ),
    dict(  # 5장 진짜 달라진 것 — 시간의 쓸모
        kor_title="진짜 달라진 건\n시간의 쓸모",
        body="일하는 시간은 비슷해요.\n근데 그 시간을 어디 쓰냐가\n완전히 달라졌어요.\n숫자 옮기던 시간을,\n사람과 결정에 돌려받았어요.",
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
        slug="260606_AI7_AI를쓰고바뀐내하루",
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
