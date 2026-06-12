# 260612 슬라이드 빌드 — 회원 문의·예약 카톡, AI로 30초 만에 답변 초안 뽑기 (AI 시리즈 #12 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카피: 2026-06-12 AI CMO 초안. 실전 how-to편 — 카톡 답변 초안 30초.
#  1 표지 / 2 매일 반복되는 카톡 공감 / 3 핵심 방법(상황 한 줄) / 4 그대로 따라하기 / 5 효과·내 몫 / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직. 실전 따라하기 진솔 공유. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 함께 성장합시다 + DM 주세요(litt.ly 미사용).
# 실행: .venv\Scripts\python instagram\260612_AI12_회원문의예약카톡AI로30초\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260612_AI12_회원문의예약카톡AI로30초"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-12-AI12-회원문의예약카톡AI"
QUEUE_TITLE = "AI #12편 — 카톡 답변 초안 30초(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "회원 문의·예약 카톡, AI로 30초 만에 답변 초안 뽑기 — 그대로 따라 해보세요.\n\n"
    "우리는 하루에도 문의·예약 카톡이 열 건 넘게 와요.\n"
    "운영시간 묻고, 예약 바꾸고, 가격 궁금해하고.\n"
    "그때마다 답을 처음부터 새로 쓰면 시간이 훅 가더라고요.\n\n"
    "그래서 방법을 바꿨어요. 매번 새로 쓰지 않습니다.\n"
    "AI한테 상황을 딱 한 줄로 줘요.\n"
    "\"회원이 토요일 오전 예약을 일요일로 바꿔달라고 함. 정중하게 답장 써줘.\"\n"
    "그럼 30초 안에 답장 초안이 나와요.\n\n"
    "초안이 나오면 제가 두 가지만 손봐요.\n"
    "하나, 우리 말투로 다듬기.\n"
    "둘, 틀린 정보 없는지 확인하기.\n"
    "맨땅에서 쓰는 것과 초안을 고치는 건 속도가 완전 달라요.\n\n"
    "포인트는 딱 하나예요. 상황을 한 줄로 구체적으로 주는 것.\n"
    "누가, 뭘 원하고, 어떤 말투로 — 이 세 가지만 주면 초안 품질이 확 올라가요.\n\n"
    "AI를 다루는 대표가 살아남습니다.\n"
    "도움이 됐다면 저장해두고 딱 하나만 따라 해보세요.\n"
    "혼자 고민 말고 DM 주세요 — 아는 선에서 같이 풀어드릴게요.\n"
    "완벽하진 않아도, 함께 성장합시다.\n\n"
    "#AI #AI활용 #카톡답변 #고객응대 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 카톡공감(2) + 핵심방법(3) + 따라하기(4) + 효과·내몫(5) + 마무리/CTA(6, main() 별도)
# 흐름: 표지 → 매일 쌓이는 카톡 → 상황 한 줄 → 그대로 따라하기 → 두 가지만 손보기 → 마무리
SLIDES = [
    dict(  # 1장 표지
        kor_title="카톡 답변,\n30초면 끝나요",
        eng_title="30-Second Reply",
    ),
    dict(  # 2장 매일 반복되는 카톡 공감
        kor_title="매일 쌓이는\n문의 카톡",
        body="문의·예약 카톡이\n하루에도 열 건씩 와요.\n운영시간, 예약 변경, 가격…\n그때마다 답을 처음부터 쓰면\n시간이 훅 가더라고요.",
    ),
    dict(  # 3장 핵심 방법 — 상황 한 줄
        kor_title="상황을 한 줄로\n주면 돼요",
        body="이제 매번 새로 안 써요.\nAI한테 상황만 딱 한 줄.\n'누가, 뭘 원하고,\n어떤 말투로' 이 세 가지요.\n그럼 30초 만에 초안이 나와요.",
    ),
    dict(  # 4장 그대로 따라하기 예시
        kor_title="이렇게\n따라 해보세요",
        body="이렇게 입력해요 →\n\"회원이 토요일 예약을\n일요일로 바꿔달라고 함.\n정중하게 답장 써줘.\"\n끝. 답장 초안이 바로 떠요.",
    ),
    dict(  # 5장 효과 — 내가 손보는 두 가지
        kor_title="저는 두 가지만\n손봐요",
        body="하나, 우리 말투로 다듬기.\n둘, 틀린 정보 없는지 확인.\n맨땅에서 쓰는 거랑\n초안을 고치는 건\n속도가 완전 달라요.",
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
        slug="260612_AI12_회원문의예약카톡AI로30초",
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
