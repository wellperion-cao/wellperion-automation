# 260602 슬라이드 빌드 — 초등학생도 따라 하는 AI 활용 A→Z (AI 시리즈 #3 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# "왜AI"(260530) 5장 양식과 일관 — compose_text_slide(main) 그대로 사용, 디자인 코드 재발명 금지
# GM 사양: 초등학생 눈높이 · 3단 구조(범용 가이드→웰페리온 사례→따라하기) · 매수 많아도 됨
# CTA: DM 유도(개인계정 톤, litt.ly 강제 없음) · 마지막 장 슬로건+같이성장+DM
# 실행: .venv\Scripts\python instagram\260602_AI3_초등생도AI\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260602_AI3_초등생도AI"
OUT = FOLDER / "output"

# compose_text_slide 분기: eng_title 있으면 표지, 없으면 본문(kor_title 헤딩 + body)
# 3단 구조는 헤딩 번호(①②③)와 montage 그룹으로 표현 (compositor 파라미터 재발명 금지)
SLIDES = [
    dict(  # 1장 표지
        kor_title="초등학생도 따라 하는\nAI 활용법",
        eng_title="How I Use AI",
    ),
    dict(  # 2장 도입 — 눈높이 낮추기
        kor_title="AI, 어렵게 생각 마세요",
        body="AI는 복잡한 기계가 아니에요.\n말을 알아듣는 '똑똑한 막내 직원'\n한 명이 생겼다고 보면 돼요.\n시키면 해요. 말로요.",
    ),
    # --- ① 범용 AI 활용 가이드 (누구나 따라 하는 기본) ---
    dict(  # 3장
        kor_title="누구나 쓰는 법 ①\n그냥 '말'로 시키면 돼요",
        body="휴대폰에 AI 앱을 깔고,\n친구한테 부탁하듯 적으면 끝이에요.\n\"내일 날씨 알려줘\"\n\"이 문장 더 정중하게 고쳐줘\"\n이게 전부예요.",
    ),
    dict(  # 4장
        kor_title="누구나 쓰는 법 ②\n자세히 말할수록 잘해요",
        body="막내한테도 \"대충 해줘\"보다\n\"누구에게, 어떤 느낌으로\"\n알려주면 더 잘하죠?\nAI도 똑같아요.\n상황을 같이 적어주세요.",
    ),
    dict(  # 5장
        kor_title="누구나 쓰는 법 ③\n틀려도 괜찮아요",
        body="처음부터 잘하는 사람 없어요.\n마음에 안 들면\n\"다시, 이렇게 바꿔줘\" 하면 돼요.\n혼나지 않는 막내라서\n몇 번이고 시켜도 돼요.",
    ),
    # --- ② 웰페리온 실제 사례 (우리가 이렇게 쓴다) ---
    dict(  # 6장
        kor_title="웰페리온은 이렇게 ①\n문의 답변을 도와줘요",
        body="회원님 질문에 답할 때,\nAI가 먼저 친절한 초안을 써줘요.\n저는 읽고 다듬기만 하면 되니\n답이 빨라지고, 놓치는 게 줄어요.",
    ),
    dict(  # 7장
        kor_title="웰페리온은 이렇게 ②\n숫자 정리를 맡겨요",
        body="이번 달 수업이 얼마나 찼는지,\n뭐가 인기인지 표로 정리하는 일.\n예전엔 한참 걸렸는데\n지금은 AI가 몇 초면 끝내요.",
    ),
    dict(  # 8장
        kor_title="웰페리온은 이렇게 ③\n보고서 초안을 써줘요",
        body="하루 일을 몇 줄 적어주면\nAI가 깔끔한 보고서로 만들어줘요.\n덕분에 저는 '쓰는 일' 말고\n'결정하는 일'에 시간을 써요.",
    ),
    # --- ③ 당신도 이렇게 따라 해보세요 (실천 유도) ---
    dict(  # 9장
        kor_title="따라 해보세요 ①\n오늘 딱 하나만",
        body="거창하게 시작하지 마세요.\n오늘 가장 귀찮았던 일 하나,\n그걸 AI에게 말로 시켜보세요.\n\"이거 대신 정리해줘\"부터요.",
    ),
    dict(  # 10장
        kor_title="따라 해보세요 ②\n매일 한 번씩",
        body="하루 한 번만 써보면\n일주일 뒤엔 손에 익어요.\n어렵게 배우는 게 아니라\n그냥 '자주 시켜보는' 거예요.",
    ),
    dict(  # 11장
        kor_title="따라 해보세요 ③\n익숙해지면 넓혀요",
        body="답장 → 정리 → 기획까지\n조금씩 맡기는 일을 늘려보세요.\n어느새 막내 직원 한 명 몫을\nAI가 해주고 있을 거예요.",
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
    # 기존 개인계정 발행분(왜AI·AI직원효율)과 동일 처리. 풀 로고 금지.
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
        body="솔직히 저도 아직 부족하고, 배우는 중이에요.\n완벽하진 않아도 같이 성장하고 싶어요.\n\nAI 활용이 궁금한 운동시설 대표님,\n부담 없이 DM 주세요.",
    )
    print(f"[OK] {last_out.name} - slogan/DM card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
