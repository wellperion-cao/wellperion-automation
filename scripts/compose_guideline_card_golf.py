"""골프 전용 가이드라인 카드 생성기
기존 guideline_card.jpg를 베이스로 우측 'WELLNESS STUDIO' 섹션만 교체.
좌측(FOR MEMBERS·FOR INSTRUCTORS)·하단(OPERATIONS·문의·로고·칩)은 원본 그대로 유지.

출력: instagram/_assets/guideline_card_golf.jpg
실행: python scripts/compose_guideline_card_golf.py
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import PROJECT_ROOT, BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE
from compose_barre import load_font

SRC_CARD = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card.jpg"
OUT_CARD = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card_golf.jpg"

# 우측 섹션 영역 좌표 (원본 실측)
# 구분선 x=540, 우측 텍스트 시작 x=556
# 제목 텍스트 y=360~372, 섹션 전체 y=340~760
SECTION_X0 = 548   # 구분선 오른쪽부터
SECTION_Y0 = 338   # 섹션 상단
SECTION_X1 = 1070  # 우측 끝
SECTION_Y1 = 762   # 섹션 하단

BG_COLOR = (32, 29, 28)  # 원본 배경색 실측


def compose_guideline_card_golf(output_path: Path = OUT_CARD) -> None:
    img = Image.open(SRC_CARD).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 우측 섹션 영역을 배경색으로 지움
    draw.rectangle(
        [(SECTION_X0, SECTION_Y0), (SECTION_X1, SECTION_Y1)],
        fill=BG_COLOR,
    )

    # ── 우측 섹션 제목 ──────────────────────────────────────────
    # 원본 "WELLNESS STUDIO  웰니스 스튜디오 시설 이용" 와 동일 y/x 좌표 사용
    title_eng_font = load_font("bold", 26)
    title_kor_font = load_font("semibold", 26)

    # "GOLF FACILITY" (베이지 bold)
    draw.text((556, 360), "GOLF FACILITY", font=title_eng_font, fill=BEIGE)

    # "골프장 시설 이용" (흰색 semibold) — 원본 동일 줄
    # 원본에서 영문 제목과 한글이 한 줄: "WELLNESS STUDIO  웰니스 스튜디오 시설 이용"
    # 영문 너비 측정 후 이어 쓰기
    eng_w = draw.textlength("GOLF FACILITY", font=title_eng_font)
    draw.text((556 + eng_w + 14, 360), "골프장 시설 이용", font=title_kor_font, fill=WHITE)

    # ── 구분선 (원본과 동일 — 제목 아래 가로선) ──────────────────
    draw.line([(556, 392), (1050, 393)], fill=SEP_LINE, width=1)

    # ── 항목 5개 ────────────────────────────────────────────────
    item_font = load_font("medium", 24)
    DOT = "· "
    items = [
        ("골프화·복장 규정 준수", "Dress Code"),
        ("스윙 시 안전 거리 유지", "Keep Safe Distance"),
        ("사용 후 정리·정돈", "Reset After Use"),
        ("플레이 중 정숙", "Quiet During Play"),
        ("시설 이슈 발생 시 리셉션 공유", "Notify Reception"),
    ]
    y = 406
    LINE_H = 47  # 원본 항목 간격 실측
    for kor, eng in items:
        draw.text((556, y), f"{DOT}{kor} ({eng})", font=item_font, fill=WHITE)
        y += LINE_H

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [골프 가이드카드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def main() -> None:
    print("=== 골프 전용 가이드라인 카드 생성 ===")
    compose_guideline_card_golf(OUT_CARD)
    print(f"출력: {OUT_CARD}")


if __name__ == "__main__":
    main()
