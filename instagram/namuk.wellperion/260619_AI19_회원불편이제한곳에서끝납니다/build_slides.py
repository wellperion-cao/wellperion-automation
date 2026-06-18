# 260619 슬라이드 빌드 — 회원 불편, 이제 한 곳에서 끝납니다 (AI 시리즈 #19 · SEASON 2 실전편 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 주제(로드맵 §4.1·§5.1): 직원 없이도 회원이 직접 말하면 AI가 정확히 담당자에게 전달.
#  1 표지 / 2 왜(두 문제) / 3 어떻게1(AI와 설계) / 4 어떻게2(한 곳 완성) / 5 그래서(6가지 접수) / 6 마무리·CTA
# 톤: 개인계정 GM 1인칭 솔직. 광고 아님. 전문용어·내부 닉네임 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260619_AI19_회원불편이제한곳에서끝납니다\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260619_AI19_회원불편이제한곳에서끝납니다"
OUT = FOLDER / "output"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-19-AI19-회원불편이제한곳에서"
QUEUE_TITLE = "AI #19편 — 회원 불편 한 곳 접수(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 멘션 자동 삽입 금지

# 시즌2 라벨(표지 부제/eng_sub 자리)
SEASON2_LABEL = "SEASON 2 · 실전편"

CAPTION = (
    "회원 불편, 이제 한 곳에서 끝납니다.\n\n"
    "어제는 매일 아침 8시에 AI가 회사 안을 한 장으로 정리해주는 이야기였어요.\n"
    "오늘은 시선을 밖으로 돌렸어요. 바로 회원이에요.\n\n"
    "회원이 불편을 말하면, 그동안은 직원이 받아서 담당 부서로 옮겼어요.\n"
    "그런데 두 가지가 걸렸어요.\n"
    "하나는 그 일에 사람 손과 시간이 든다는 것.\n"
    "또 하나는 사람을 거치면서 회원 말이 흐려지거나 빠진다는 것.\n\n"
    "그래서 우리 AI에게 물었어요. \"이 두 가지, 한 번에 풀 방법이 있을까?\"\n"
    "AI가 방법을 분석해 제안했고, 같이 구조를 짰어요.\n\n"
    "승인하고 만들었어요. 회원이 직접 말하면 AI가 바로 담당 부서로 넘기는 한 곳.\n"
    "분실물, 시설 고장, 청결, 잠시 쉬기, 칭찬, 쓴소리 — 여섯 가지를 회원이 직접 접수해요.\n"
    "사람이 중간에서 받아 옮기는 단계가 없어요.\n\n"
    "문제는 한 곳으로 모여야 해결이 시작돼요.\n"
    "이제 어떻게 끝까지 처리되는지는 다음 편에서 이어갈게요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 당신 회사는 회원·고객 불편을 지금 어디서 받나요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 왜(2) + 어떻게1(3) + 어떻게2(4) + 그래서(5) + 마무리/CTA(6, main() 별도)
SLIDES = [
    dict(  # 1장 표지
        kor_title="회원 불편,\n이제 한 곳에서\n끝납니다",
        eng_title=SEASON2_LABEL,
        body="불편하다고 말했는데\n제대로 전달됐을까요?",
    ),
    dict(  # 2장 왜 — 두 가지 문제
        kor_title="두 가지가\n걸렸어요",
        body="회원 말을 직원이 받아\n담당 부서로 옮겼어요.\n하나는 그 일에 사람 손과 시간이 들고,\n또 하나는 사람을 거치며\n회원 말이 흐려지거나 빠졌어요.",
    ),
    dict(  # 3장 어떻게1 — AI와 설계
        kor_title="AI에게\n물어봤어요",
        body="\"이 두 가지,\n한 번에 풀 방법이 있을까?\"\nAI가 방법을 분석해 제안했어요.\n그렇게 같이 구조를 짰어요.",
    ),
    dict(  # 4장 어떻게2 — 한 곳 완성
        kor_title="그래서\n만들었어요",
        body="회원이 직접 말하면\nAI가 바로 담당 부서로 넘겨요.\n사람이 중간에서 받아\n옮기는 단계가 없어요.\n모든 불편이 한 곳으로 모여요.",
    ),
    dict(  # 5장 그래서 — 6가지 접수
        kor_title="이제\n이렇게 돼요",
        body="사람 손이 안 거치니 시간이 안 들고,\n회원 말이 그대로 담당자에게 가요.\n분실물·시설 고장·청결·잠시 쉬기·\n칭찬·쓴소리 — 여섯 가지를\n회원이 직접 접수해요.",
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

    # 개인계정(namuk.wellperion) = 'W' 심볼만 미니멀 로고. 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 6장 = 시그니처 마무리 제목(편별) + 저장·댓글·팔로우 정본 CTA(2026-06-10 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="문제는 한 곳으로 모여야\n해결이 시작된다",
        body="나중에 따라하려면 저장\n당신 회사는 회원·고객 불편을 지금 어디서 받나요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
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
        slug="260619_AI19_회원불편이제한곳에서끝납니다",
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
