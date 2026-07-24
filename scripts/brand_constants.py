"""웰페리온 브랜드 상수 로더 (★정본 아님 — 원천은 ssot/brand.json)

슬라이드 합성 엔진 3종이 쓰는 색·폰트·로고 경로·브랜드 프리셋을 공급한다.
2026-07-24(배64) 이전에는 이 파일이 값의 정본이었으나, AI 가 브랜드 기준을 한 번에
학습할 수 있는 기계 원천이 필요해 원천을 ssot/brand.json 으로 옮겼다. 이 파일은
그걸 읽어 종전과 **같은 이름·같은 값**의 상수로 채우는 로더다(엔진 호환 유지·이미지 불변).

값의 원천 = ssot/brand.json (배64). 여기서 값을 고치지 말 것 — brand.json 을 고친 뒤
이 모듈을 다시 로드하면 반영된다. 이 파일은 brand.json 을 읽어 아래 동일한 이름·동일한 값의
상수로 채우는 로더다(공개 이름·값 불변 — 슬라이드 엔진 호환 유지).
JSON 로드 실패 시 조용히 죽지 않는다 — 하드코딩 폴백 값으로 채우고 stderr 에 [WARN] 을 남긴다
(콘텐츠 제작이 멈추면 안 된다).

소비처:
  - compose_barre.py  (사진형 1080x1080)
  - compose_ballet.py (compose_barre 레이아웃 재사용)
  - slide_compositor.py (텍스트형 1080x1350 / BRAND_PRESETS)

문서 정본: 웰페리온 ERP M1 "디자인 표준 마스터".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# -----------------------------------------------------------------
# 경로
# -----------------------------------------------------------------
PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")
_BRAND_JSON = PROJECT_ROOT / "ssot" / "brand.json"

# -----------------------------------------------------------------
# ─────────────────────────────────────────────────────────────────────────────
# 하드코딩 폴백 값 — ssot/brand.json 로드 실패 시에만 쓰인다.
# ★여기를 고쳐도 평소에는 아무 효과가 없다(정상 경로는 brand.json 을 읽는다).
#   값을 바꾸려면 ssot/brand.json 을 고쳐라. 여기만 고치면 원천과 갈라져,
#   '고쳤는데 왜 안 바뀌지' + 'JSON 이 깨진 날에만 옛 색이 나오는' 최악의 조합이 된다.
#   폴백을 바꿔야 할 유일한 이유 = brand.json 을 고친 뒤 둘을 같은 값으로 맞출 때.
# ─────────────────────────────────────────────────────────────────────────────
# -----------------------------------------------------------------
_FALLBACK_FONT_DIR = PROJECT_ROOT / "2. 브랜드_자료" / "02_로고&워터마크&FONT" / "font"
_FALLBACK_LOGO_DIR = PROJECT_ROOT / "instagram" / "_assets" / "logo"

_FALLBACK = {
    "FONT_DIR": _FALLBACK_FONT_DIR,
    "FONT_BOLD": _FALLBACK_FONT_DIR / "Pretendard-Bold.otf",
    "FONT_SEMIBOLD": _FALLBACK_FONT_DIR / "Pretendard-SemiBold.otf",
    "FONT_MEDIUM": _FALLBACK_FONT_DIR / "Pretendard-Medium.otf",
    "LOGO_DIR": _FALLBACK_LOGO_DIR,
    "LOGO_WHITE_ALPHA": _FALLBACK_LOGO_DIR / "wellperion_white_alpha.png",
    "LOGO_BEIGE_ALPHA": _FALLBACK_LOGO_DIR / "wellperion_beige_alpha.png",
    "BEIGE": (183, 159, 138),
    "BLACK_BG": (34, 31, 32),
    "WHITE": (255, 255, 255),
    "GRAY": (170, 160, 152),
    "HIGHLIGHT": (237, 91, 63),
    "CHIP_BEIGE": (186, 162, 140),
    "SEP_LINE": (171, 161, 151),
    "DUOTONE_DARK": "#221F20",
    "DUOTONE_LIGHT": "#B79F8A",
    "BRAND_PRESETS": {
        "main": {
            "primary": (183, 159, 138), "background": (34, 31, 32), "accent": (237, 91, 63),
            "text": (255, 255, 255), "text_secondary": (183, 159, 138), "wordmark": "W  WELLPERION",
        },
        "sports_club": {
            "primary": (63, 113, 176), "background": (37, 59, 108), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (210, 220, 240), "wordmark": "WELLPERION SPORTS CLUB",
        },
        "squash": {
            "primary": (210, 210, 210), "background": (119, 150, 142), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (220, 230, 225), "wordmark": "W  SQUASH",
        },
        "pt": {
            "primary": (181, 72, 64), "background": (81, 43, 50), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (220, 200, 195), "wordmark": "W  PT",
        },
        "golf": {
            "primary": (51, 115, 66), "background": (19, 33, 23), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (200, 215, 200), "wordmark": "W  GOLF",
        },
        "swimming": {
            "primary": (33, 87, 104), "background": (23, 44, 66), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (200, 215, 225), "wordmark": "W  SWIMMING",
        },
        "pilates": {
            "primary": (196, 69, 88), "background": (130, 42, 55), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (230, 200, 205), "wordmark": "W  PILATES",
        },
        "gymnastic": {
            "primary": (194, 186, 214), "background": (86, 58, 97), "accent": (183, 159, 138),
            "text": (255, 255, 255), "text_secondary": (220, 215, 230), "wordmark": "W  GYMNASTIC",
        },
        "spa": {
            "primary": (201, 169, 110), "background": (250, 247, 242), "accent": (139, 26, 47),
            "text": (34, 31, 32), "text_secondary": (139, 26, 47), "wordmark": "WELLPERION × Cinq Mondes",
        },
    },
}


def _load() -> dict:
    """ssot/brand.json 에서 값을 읽어 로더용 딕셔너리로 변환. 실패 시 폴백 + [WARN]."""
    try:
        with open(_BRAND_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)

        def rgb(hex_entry: dict) -> tuple:
            return tuple(hex_entry["rgb"])

        core = data["colors"]["core"]
        presets_raw = data["colors"]["department_presets"]
        presets = {}
        for key, preset in presets_raw.items():
            presets[key] = {
                "primary": rgb(preset["primary"]),
                "background": rgb(preset["background"]),
                "accent": rgb(preset["accent"]),
                "text": rgb(preset["text"]),
                "text_secondary": rgb(preset["text_secondary"]),
                "wordmark": preset["wordmark"],
            }

        fonts = data["fonts"]
        logo = data["logo"]

        return {
            "FONT_DIR": Path(fonts["FONT_DIR"]),
            "FONT_BOLD": Path(fonts["FONT_BOLD"]),
            "FONT_SEMIBOLD": Path(fonts["FONT_SEMIBOLD"]),
            "FONT_MEDIUM": Path(fonts["FONT_MEDIUM"]),
            "LOGO_DIR": Path(logo["LOGO_DIR"]),
            "LOGO_WHITE_ALPHA": Path(logo["LOGO_WHITE_ALPHA"]),
            "LOGO_BEIGE_ALPHA": Path(logo["LOGO_BEIGE_ALPHA"]),
            "BEIGE": rgb(core["BEIGE"]),
            "BLACK_BG": rgb(core["BLACK_BG"]),
            "WHITE": rgb(core["WHITE"]),
            "GRAY": rgb(core["GRAY"]),
            "HIGHLIGHT": rgb(core["HIGHLIGHT"]),
            "CHIP_BEIGE": rgb(core["CHIP_BEIGE"]),
            "SEP_LINE": rgb(core["SEP_LINE"]),
            "DUOTONE_DARK": core["DUOTONE_DARK"],
            "DUOTONE_LIGHT": core["DUOTONE_LIGHT"],
            "BRAND_PRESETS": presets,
        }
    except Exception as exc:  # noqa: BLE001 — 조용한 실패 금지, 폴백으로 계속 진행
        print(f"[WARN] ssot/brand.json 로드 실패({exc}) — brand_constants.py 하드코딩 폴백 값 사용", file=sys.stderr)
        return _FALLBACK


_values = _load()

FONT_DIR = _values["FONT_DIR"]
FONT_BOLD = _values["FONT_BOLD"]
FONT_SEMIBOLD = _values["FONT_SEMIBOLD"]
FONT_MEDIUM = _values["FONT_MEDIUM"]

LOGO_DIR = _values["LOGO_DIR"]
LOGO_WHITE_ALPHA = _values["LOGO_WHITE_ALPHA"]
LOGO_BEIGE_ALPHA = _values["LOGO_BEIGE_ALPHA"]

# -----------------------------------------------------------------
# 브랜드 색상 (사진형 엔진 — compose_barre / compose_ballet 공유)
# -----------------------------------------------------------------
BEIGE = _values["BEIGE"]              # #B79F8A
BLACK_BG = _values["BLACK_BG"]        # #221F20
WHITE = _values["WHITE"]
GRAY = _values["GRAY"]                # 날짜·메타 텍스트
HIGHLIGHT = _values["HIGHLIGHT"]      # #ED5B3F 액센트 (텍스트형 main 프리셋)
CHIP_BEIGE = _values["CHIP_BEIGE"]    # 우상단 칩 배경
SEP_LINE = _values["SEP_LINE"]        # 표지 분리선 (compose_cover y=701~702)

# 듀오톤 기본 hex (BLACK + BEIGE — 발레·스쿼시 완성본 표준)
DUOTONE_DARK = _values["DUOTONE_DARK"]
DUOTONE_LIGHT = _values["DUOTONE_LIGHT"]

# -----------------------------------------------------------------
# 브랜드 프리셋 (241030 가이드 — 텍스트형 slide_compositor)
# -----------------------------------------------------------------
BRAND_PRESETS = _values["BRAND_PRESETS"]
