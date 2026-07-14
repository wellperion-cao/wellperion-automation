"""성인 강습 신규 시리즈(L 시리즈) 표지 — 사진형 시안 렌더 (GM 확정용).

GM 2026-07-13 지시: compose_official_facility_series.py의 표지(hero) 렌더 구조를
강습 톤으로 미러링. 카운터(draw_counter)는 호출하지 않음(우상단 페이지번호 제거).
디자인 정본 프리미티브 = compose_barre(center_crop_fill·apply_bottom_gradient·
paste_logo·draw_chip·load_font) 재사용, 색·폰트·로고 상수 SSOT = brand_constants.

⚠ 캔버스가 1080×1350(F 시리즈는 1080×1080)이므로 compose_barre.apply_bottom_gradient는
그대로 쓸 수 없다(모듈 전역 W,H=1080,1080에 고정된 오버레이라 세로 1350 캔버스와 크기가
안 맞아 alpha_composite에서 깨짐) → 동일 알고리즘을 실제 이미지 크기로 파라미터화해
로컬로 재구현(_bottom_gradient). 그 외 프리미티브는 캔버스 크기에 의존하지 않아 그대로 재사용.

이 스크립트는 시안 렌더 전용 — 발행·M5 등록·레포 instagram 폴더 기록 없음.
출력은 호출부에서 지정한 out_dir에 저장.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

sys.path.insert(0, str(Path(__file__).parent))
from compose_barre import (  # noqa: E402
    center_crop_fill, paste_logo, draw_chip, load_font,
)
from brand_constants import BEIGE, BLACK_BG, WHITE, HIGHLIGHT, PROJECT_ROOT  # noqa: E402

W, H = 1080, 1350

FAC = PROJECT_ROOT / "2. 브랜드_공식문서" / "01_시설_사진"
PRO = FAC / "web_10mb아래"      # 094A* 프로컷
KAKAO = FAC / "시설 사진"        # 수영장·골프장 등

FOOTER = "WELLPERION  ·  LESSON"
LABEL = "성인 강습"


def _bottom_gradient(img: Image.Image, gradient_start_y: int) -> Image.Image:
    """compose_barre.apply_bottom_gradient과 동일 알고리즘 — 실제 이미지 크기로 파라미터화
    (F 시리즈처럼 1080x1080 고정이 아니라 1080x1350 세로 캔버스라 로컬 재구현 필요)."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(h):
        if y < gradient_start_y:
            alpha = 0
        else:
            t = (y - gradient_start_y) / (h - gradient_start_y)
            alpha = int(255 * (t ** 1.2))
            alpha = min(230, alpha)
        draw.line([(0, y), (w, y)], fill=(*BLACK_BG, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _base(photo_path: Path):
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.88)
    canvas = _bottom_gradient(canvas, gradient_start_y=480)
    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)
    chip_font = load_font("bold", 28)
    draw_chip(draw, "WELLPERION", chip_font, W - 40 - 240, 38, 240, 52)
    return canvas, draw


def _save(canvas: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "JPEG", quality=93, optimize=True)
    print(f"  {out_path.name}  {out_path.stat().st_size // 1024}KB")


def compose_lesson_cover(photo_path: Path, title: str, subtitle: str, out_path: Path,
                         title_size: int = 110) -> None:
    """L 시리즈 공통 표지 템플릿.
    라벨(성인 강습) → 종목명 대제목 → 코랄 언더라인 → 부제(배움 메시지) → 하단 시리즈 태그.
    """
    canvas, draw = _base(photo_path)

    label_font = load_font("medium", 30)
    draw.text((40, 850), LABEL, font=label_font, fill=BEIGE)

    title_font = load_font("bold", title_size)
    title_y = 895
    draw.text((40, title_y), title, font=title_font, fill=WHITE)
    title_bbox = draw.textbbox((40, title_y), title, font=title_font)

    underline_y = title_bbox[3] + 20
    draw.rectangle([(40, underline_y), (40 + 120, underline_y + 6)], fill=HIGHLIGHT)

    sub_font = load_font("semibold", 40)
    sub_y = underline_y + 6 + 35
    draw.multiline_text((40, sub_y), subtitle, font=sub_font, fill=BEIGE, spacing=14)

    footer_font = load_font("medium", 26)
    draw.text((40, 1290), FOOTER, font=footer_font, fill=BEIGE)

    _save(canvas, out_path)


# ── 배치1 3종목 ──────────────────────────────────────────────────────
EPISODES = [
    {
        "out": "L1_수영.jpg",
        "photo": KAKAO / "수영장.jpg",
        "title": "수영,",
        "sub": "물이 무서운 어른도\n0에서 시작합니다",
    },
    {
        "out": "L3_골프.jpg",
        "photo": KAKAO / "골프장.jpg",
        "title": "골프,",
        "sub": "실내에서, 눈치 안 보고\n제대로 배웁니다",
    },
    {
        "out": "L2_PT.jpg",
        # 094A9961.jpg = TechnoGym 웨이트(레그 익스텐션 등) 트레이닝존 실사 확인됨
        # (094A9977=트레드밀 유산소존은 F1 '헬스'에 이미 사용 — 저항운동 기구가 있는
        #  9961을 퍼스널 트레이닝 톤에 더 부합해 채택)
        "photo": PRO / "094A9961.jpg",
        "title": "퍼스널,",
        "sub": "혼자 안 되던 게\n옆에서 잡아주니 됩니다",
    },
]


def main(out_dir: Path):
    for ep in EPISODES:
        if not ep["photo"].exists():
            print(f"[ERROR] 소스 사진 없음: {ep['photo']}")
            continue
        compose_lesson_cover(ep["photo"], ep["title"], ep["sub"], out_dir / ep["out"])
    print("=== L 시리즈 표지 시안 렌더 완료 ===")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "_lesson_covers_preview"
    main(target)
