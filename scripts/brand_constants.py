"""웰페리온 브랜드 상수 SSOT (디자인 표준 마스터 정본)

슬라이드 합성 엔진 3종이 공유하는 색·폰트·로고 경로·브랜드 프리셋의 단일 출처.
값은 기존 엔진 코드에서 그대로 이관(불변) — 새 값 도입 금지. 결과 이미지 1픽셀 불변 보장.

소비처:
  - compose_barre.py  (사진형 1080x1080)
  - compose_ballet.py (compose_barre 레이아웃 재사용)
  - slide_compositor.py (텍스트형 1080x1350 / BRAND_PRESETS)

문서 정본: 웰페리온 ERP M5(cmo-publish) "디자인 표준 마스터".
"""
from __future__ import annotations

from pathlib import Path

# -----------------------------------------------------------------
# 경로
# -----------------------------------------------------------------
PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")

# 폰트 위치 후보 (brand 통합 진행 중 — 실제 존재 경로 자동 선택)
_FONT_DIR_CANDIDATES = [
    PROJECT_ROOT / "brand" / "font",
    PROJECT_ROOT / "2. 브랜드_공식문서" / "font",
]
FONT_DIR = next((d for d in _FONT_DIR_CANDIDATES if d.exists()), _FONT_DIR_CANDIDATES[0])
FONT_BOLD = FONT_DIR / "Pretendard-Bold.otf"
FONT_SEMIBOLD = FONT_DIR / "Pretendard-SemiBold.otf"
FONT_MEDIUM = FONT_DIR / "Pretendard-Medium.otf"

# 공식 로고 PNG (instagram/_assets/logo/)
LOGO_DIR = PROJECT_ROOT / "instagram" / "_assets" / "logo"
# 사진 위(반투명 오버레이용): 흰색 알파
LOGO_WHITE_ALPHA = LOGO_DIR / "wellperion_white_alpha.png"
# 어두운 배경용: 베이지 알파
LOGO_BEIGE_ALPHA = LOGO_DIR / "wellperion_beige_alpha.png"

# -----------------------------------------------------------------
# 브랜드 색상 (사진형 엔진 — compose_barre / compose_ballet 공유)
# -----------------------------------------------------------------
BEIGE = (183, 159, 138)       # #B79F8A
BLACK_BG = (34, 31, 32)       # #221F20
WHITE = (255, 255, 255)
GRAY = (170, 160, 152)        # 날짜·메타 텍스트
HIGHLIGHT = (237, 91, 63)     # #ED5B3F 액센트 (텍스트형 main 프리셋)
CHIP_BEIGE = (186, 162, 140)  # 우상단 칩 배경
SEP_LINE = (171, 161, 151)    # 표지 분리선 (compose_cover y=701~702)

# 듀오톤 기본 hex (BLACK + BEIGE — 발레·스쿼시 완성본 표준)
DUOTONE_DARK = "#221F20"
DUOTONE_LIGHT = "#B79F8A"

# -----------------------------------------------------------------
# 브랜드 프리셋 (241030 가이드 — 텍스트형 slide_compositor)
# -----------------------------------------------------------------
BRAND_PRESETS = {
    "main": {
        "primary": (183, 159, 138),       # #B79F8A BEIGE
        "background": (34, 31, 32),       # #221F20 BLACK
        "accent": (237, 91, 63),          # #ED5B3F HIGHLIGHT
        "text": (255, 255, 255),
        "text_secondary": (183, 159, 138),
        "wordmark": "W  WELLPERION",
    },
    "sports_club": {
        "primary": (63, 113, 176),        # #3F71B0 LIGHT BLUE
        "background": (37, 59, 108),      # #253B6C DARK BLUE
        "accent": (183, 159, 138),        # #B79F8A 베이지 (메인 브랜드 액센트)
        "text": (255, 255, 255),
        "text_secondary": (210, 220, 240),
        "wordmark": "WELLPERION SPORTS CLUB",
    },
    "squash": {
        "primary": (210, 210, 210),       # #D2D2D2
        "background": (119, 150, 142),    # #77968E
        "accent": (183, 159, 138),
        "text": (255, 255, 255),
        "text_secondary": (220, 230, 225),
        "wordmark": "W  SQUASH",
    },
    "pt": {
        "primary": (181, 72, 64),
        "background": (81, 43, 50),
        "accent": (183, 159, 138),
        "text": (255, 255, 255),
        "text_secondary": (220, 200, 195),
        "wordmark": "W  PT",
    },
    "golf": {
        "primary": (51, 115, 66),
        "background": (19, 33, 23),
        "accent": (183, 159, 138),
        "text": (255, 255, 255),
        "text_secondary": (200, 215, 200),
        "wordmark": "W  GOLF",
    },
    "swimming": {
        "primary": (33, 87, 104),
        "background": (23, 44, 66),
        "accent": (183, 159, 138),
        "text": (255, 255, 255),
        "text_secondary": (200, 215, 225),
        "wordmark": "W  SWIMMING",
    },
    "pilates": {
        "primary": (196, 69, 88),
        "background": (130, 42, 55),
        "accent": (183, 159, 138),
        "text": (255, 255, 255),
        "text_secondary": (230, 200, 205),
        "wordmark": "W  PILATES",
    },
    "gymnastic": {
        "primary": (194, 186, 214),
        "background": (86, 58, 97),
        "accent": (183, 159, 138),
        "text": (255, 255, 255),
        "text_secondary": (220, 215, 230),
        "wordmark": "W  GYMNASTIC",
    },
}
