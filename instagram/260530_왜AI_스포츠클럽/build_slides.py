# 260530 슬라이드 빌드 — 왜 스포츠클럽 일에 AI를 쓰는가 (GM 개인 계정 namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 8장 모두 compose_text_slide 재사용. 회사 가이드 카드·litt.ly CTA 미포함(개인 톤).
# 발행 금지 — montage 미리보기까지만(GM 검수 게이트).
# 실행: .venv\Scripts\python instagram\260530_왜AI_스포츠클럽\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "260530_왜AI_스포츠클럽"
OUT = FOLDER / "output"

# 8장 카피 (기획_초안.md 기반) — "현장 문제 → AI 해결 → 사람이 더 중요해짐" 흐름
SLIDES = [
    dict(  # 1장 표지
        kor_title="스포츠클럽을 운영하며,\n나는 왜 AI를 쓰는가",
        eng_title="Why I Use AI",
    ),
    dict(  # 2장 솔직한 고백 (현장 문제)
        kor_title="현장은 늘\n사람이 부족했다",
        body="예약을 받고, 문의에 답하고,\n매출을 집계하고, 보고서를 쓰고.\n정작 회원의 얼굴을 볼\n시간이 줄었다.",
    ),
    dict(  # 3장 전환 선언
        kor_title="그래서 나는\nAI에게 일을 맡겼다",
        body="기술이 멋져서가 아니다.\n사람이 해야 할 일을\n지키기 위해서다.\n반복은 AI에게, 핵심은 나에게.",
    ),
    dict(  # 4장 근거 1 — 반복 자동화
        kor_title="예약·문의·보고는\n멈추지 않는다",
        body="새벽 문의도, 주말 예약도\nAI가 먼저 받는다.\n나는 더 이상 같은 답을\n백 번 쓰지 않는다.",
    ),
    dict(  # 5장 근거 2 — 일관성·24시간
        kor_title="누가 와도\n같은 경험",
        body="내가 자리에 없어도\n응대의 수준은 흔들리지 않는다.\n회원이 받는 인상이\n들쭉날쭉하지 않는 것, 그게 신뢰다.",
    ),
    dict(  # 6장 근거 3 — 데이터 기반 결정
        kor_title="감이 아니라\n숫자로 결정한다",
        body="어떤 수업이 붐비는지,\n어디서 회원이 떠나는지.\nAI가 정리해주면, 나는\n더 빨리·더 정확히 판단한다.",
    ),
    dict(  # 7장 오해 정정 — 대체가 아니라 집중
        kor_title="AI는 사람을\n대신하지 않는다",
        body="AI가 반복을 가져갈수록\n사람은 더 사람다운 일을 한다.\n눈을 맞추고, 관계를 쌓는 일.\n그건 끝까지 사람의 몫이다.",
    ),
    dict(  # 8장 마무리 — 나의 다짐 (개인 톤, 회사 가이드 카드 아님)
        kor_title="더 사람다운\n스포츠클럽을 위해",
        body="나는 AI를 도구로 쓴다.\n회원에게 더 집중하기 위해서.\n그게 내가 매일\nAI를 켜는 이유다.",
    ),
]


def build_montage(paths: list[Path], out_path: Path, cols: int = 4) -> None:
    """8장을 1장으로 합성한 검수 미리보기 (cols x rows 그리드)."""
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

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", **slide)
        paths.append(out)
        print(f"[OK] {out.name} — {r['layout']} ({r['size_kb']}KB)")

    montage = OUT / "_검수_미리보기_8장.png"
    build_montage(paths, montage)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
