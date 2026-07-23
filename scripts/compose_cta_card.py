"""웰페리온 문의 CTA 카드 생성기 (1080x1080)

콘텐츠 슬라이드 끝(가이드 카드 옆)에 붙이는 표준 '문의·방문 예약' 카드.
- 디자인 톤 = guideline_card.jpg와 동일(차콜 배경 #221F20 + 베이지 #B79F8A + 베이지 로고).
- 색·폰트·로고 = brand_constants SSOT, 스타일 함수 = compose_barre 재사용(픽셀 일관·손 재추측 금지).
- 카피: 사전 예약제 + 공식 문의 링크(이미지라 클릭 불가 — 시각 강조용. 추적은 본문/프로필 링크가 담당).
- 금지어(피트니스·하이엔드프라이빗·사교) 회피 / 표준 문의 = wellperion.com/ko/inquiry.

출력: instagram/_assets/cta_card.jpg (CTA 카드 자산 SSOT)
실행: python scripts/compose_cta_card.py
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (  # noqa: E402
    PROJECT_ROOT, LOGO_BEIGE_ALPHA,
    BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE,
)
from compose_barre import draw_chip, load_font  # noqa: E402

W, H = 1080, 1080

# 공식값 (canon)
INQUIRY_URL = "wellperion.com/ko/inquiry"
PHONE = "02-6261-1200"
ADDRESS = "서울 용산구 서빙고로 413 · 한남동"


def _paste_beige_logo(canvas: Image.Image, logo_w: int = 150) -> Image.Image:
    """베이지 로고 PNG 좌상단 합성 (어두운 배경용 — 가이드 카드와 동일)."""
    logo = Image.open(LOGO_BEIGE_ALPHA).convert("RGBA")
    ow, oh = logo.size
    lh = int(oh * logo_w / ow)
    logo = logo.resize((logo_w, lh), Image.LANCZOS)
    base = canvas.convert("RGBA")
    base.paste(logo, (40, 40), mask=logo)
    return base.convert("RGB")


def _text_w(draw, text, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def compose_cta_card(output_path: Path) -> None:
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    # 로고(좌상단) + 칩(우상단)
    canvas = _paste_beige_logo(canvas, logo_w=150)
    draw = ImageDraw.Draw(canvas)
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    draw_chip(draw, "WELLPERION", chip_font, W - 40 - chip_w, 38, chip_w, chip_h)

    # ── 중앙 카피 블록 ──
    # 아이브로 (베이지)
    eyebrow_font = load_font("semibold", 30)
    draw.text((W // 2, 372), "한남동 프리미엄 라이프스타일 스포츠클럽",
              font=eyebrow_font, fill=BEIGE, anchor="mm")

    # 대제목 (흰색 bold)
    title_font = load_font("bold", 78)
    draw.text((W // 2, 462), "방문을 예약하세요", font=title_font, fill=WHITE, anchor="mm")

    # 베이지 분리선
    draw.rectangle([(W // 2 - 34, 536), (W // 2 + 34, 538)], fill=BEIGE)

    # 부제 (회색) — 예약제 안내 (GM 표준 문구)
    sub_font = load_font("medium", 31)
    draw.text((W // 2, 592), "모든 방문 · 상담은 사전 예약제로 운영됩니다",
              font=sub_font, fill=GRAY, anchor="mm")
    sub_en_font = load_font("medium", 24)
    draw.text((W // 2, 636), "Visits & consultations by appointment only",
              font=sub_en_font, fill=GRAY, anchor="mm")

    # ── 문의 링크 '버튼' (베이지 fill · 다크 텍스트) — 시각 강조(클릭 불가) ──
    btn_font = load_font("bold", 34)
    btn_label = f"문의 · 예약   →   {INQUIRY_URL}"
    tw = _text_w(draw, btn_label, btn_font)
    pad_x, pad_y = 46, 26
    btn_w = tw + pad_x * 2
    btn_h = 84
    btn_x = (W - btn_w) // 2
    btn_y = 716
    draw.rounded_rectangle([(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
                           radius=btn_h // 2, fill=BEIGE)
    draw.text((W // 2, btn_y + btn_h // 2 - 2), btn_label,
              font=btn_font, fill=BLACK_BG, anchor="mm")

    # ── 하단 풋터 (분리선 + 전화·주소) ──
    draw.rectangle([(80, 952), (W - 80, 953)], fill=SEP_LINE)
    foot_font = load_font("medium", 25)
    draw.text((W // 2, 1000), f"WELLPERION   ·   {PHONE}   ·   {ADDRESS}",
              font=foot_font, fill=GRAY, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [CTA] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def main():
    out = PROJECT_ROOT / "instagram" / "_assets" / "cta_card.jpg"
    print("=== 문의 CTA 카드 합성 ===")
    compose_cta_card(out)
    print(f"출력: {out}")


if __name__ == "__main__":
    main()
