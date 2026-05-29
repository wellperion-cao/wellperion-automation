"""웰페리온 슬라이드 자동 합성 모듈 v1.0
브랜드 가이드(241030) 기반 사진+카피 슬라이드 JPG 생성

CMO-001 자동 업로드 파이프라인의 시각 자료 생성 단계.
Pillow로 베이스 사진 위에 다크 오버레이 + 카피 + 액센트 + 워드마크 합성.

CLI 사용:
    python slide_compositor.py \
        --base-image <원본 사진> \
        --copy-text "<슬라이드 카피>" \
        --output <출력 경로> \
        --aspect 1080x1350 \
        --brand sports_club \
        --layout bottom

브랜드 프리셋: main / sports_club / squash / pt / golf / swimming / pilates / gymnastic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps

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

# -----------------------------------------------------------------
# 브랜드 프리셋 (241030 가이드)
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

# -----------------------------------------------------------------
# 비율 프리셋
# -----------------------------------------------------------------
ASPECT_PRESETS = {
    "1080x1350": (1080, 1350),  # 인스타 세로
    "1080x1080": (1080, 1080),  # 정방형 (카페·인스타 정방형)
    "1200x900": (1200, 900),    # 블로그 가로
    "1200x630": (1200, 630),    # 블로그 OG / 페이스북
}


# -----------------------------------------------------------------
# 이미지 헬퍼
# -----------------------------------------------------------------
def load_and_fit(image_path: Path, target_w: int, target_h: int) -> Image.Image:
    """원본 이미지를 타겟 비율로 center-crop + 리사이즈. EXIF orientation 자동 보정."""
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # 원본이 더 가로형 → 가로 자름
        new_w = int(src_h * target_ratio)
        x0 = (src_w - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, src_h))
    else:
        # 원본이 더 세로형 → 세로 자름
        new_h = int(src_w / target_ratio)
        y0 = (src_h - new_h) // 2
        img = img.crop((0, y0, src_w, y0 + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_duotone(img: Image.Image,
               dark_hex: str = "#221F20",
               light_hex: str = "#B79F8A") -> Image.Image:
    """BLACK + BEIGE 듀오톤 변환 (메인 페이지 영구 템플릿 v1 표준).
    어떤 사진이든 동일 브랜드 톤 유지 → 럭셔리 매거진 무드."""
    gray = img.convert("L")
    dr, dg, db = _hex_to_rgb(dark_hex)
    lr, lg, lb = _hex_to_rgb(light_hex)
    r_lut = [int(dr + (lr - dr) * (i / 255)) for i in range(256)]
    g_lut = [int(dg + (lg - dg) * (i / 255)) for i in range(256)]
    b_lut = [int(db + (lb - db) * (i / 255)) for i in range(256)]
    return Image.merge("RGB", (
        gray.point(r_lut), gray.point(g_lut), gray.point(b_lut)))


def apply_dark_gradient(img: Image.Image, brand: dict, layout: str) -> Image.Image:
    """프리미엄 다크 그라디언트 오버레이 (텍스트 영역 가독성 확보)."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bg = brand["background"]

    if layout == "center":
        # 전체 50% 다크 오버레이 (중앙 배치 강조)
        for y in range(h):
            alpha = 130
            ImageDraw.Draw(overlay).line([(0, y), (w, y)], fill=(*bg, alpha))
    elif layout == "top":
        # 상단 그라디언트
        for y in range(h):
            t = max(0.0, 1.0 - (y / (h * 0.5)))
            alpha = int(220 * t)
            ImageDraw.Draw(overlay).line([(0, y), (w, y)], fill=(*bg, alpha))
    else:  # bottom (default)
        # 하단 60% 그라디언트 (가이드 적용 — 사진 상부는 살리고 하부는 텍스트 영역)
        gradient_start = int(h * 0.40)
        for y in range(h):
            if y < gradient_start:
                alpha = 0
            else:
                t = (y - gradient_start) / (h - gradient_start)
                alpha = int(255 * (t ** 1.4))
                alpha = min(245, alpha)
            ImageDraw.Draw(overlay).line([(0, y), (w, y)], fill=(*bg, alpha))

    base = img.convert("RGBA")
    composed = Image.alpha_composite(base, overlay)

    # 사진 자체도 약간 어둡게 (프리미엄 톤)
    enhancer = ImageEnhance.Brightness(composed.convert("RGB"))
    return enhancer.enhance(0.92)


# -----------------------------------------------------------------
# 폰트·텍스트 헬퍼
# -----------------------------------------------------------------
def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = {
        "bold": FONT_BOLD,
        "semibold": FONT_SEMIBOLD,
        "medium": FONT_MEDIUM,
    }.get(weight, FONT_BOLD)
    if not path.exists():
        raise FileNotFoundError(f"Font not found: {path}")
    return ImageFont.truetype(str(path), size)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """원본 줄바꿈은 보존, 너무 긴 줄은 max_width 기준 자동 줄바꿈."""
    out_lines: list[str] = []
    for orig_line in text.split("\n"):
        if not orig_line.strip():
            out_lines.append("")
            continue
        words = orig_line.split(" ")
        current = ""
        for w in words:
            candidate = (current + " " + w).strip() if current else w
            bbox = font.getbbox(candidate)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                if current:
                    out_lines.append(current)
                current = w
        if current:
            out_lines.append(current)
    return out_lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    color: tuple,
    x: int,
    y: int,
    line_spacing: float = 1.35,
) -> int:
    """여러 줄 텍스트 그리기. 마지막 줄의 y_end 반환."""
    line_h = int(font.size * line_spacing)
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=color)
        cy += line_h
    return cy


# -----------------------------------------------------------------
# 슬라이드 합성 메인
# -----------------------------------------------------------------
def compose_slide(
    base_image: Path,
    copy_text: str,
    output: Path,
    aspect: str = "1080x1350",
    brand_key: str = "sports_club",
    layout: str = "bottom",
    title_size: int | None = None,
    show_wordmark: bool = True,
) -> dict:
    """슬라이드 1장 합성. 결과 dict 반환."""
    if aspect not in ASPECT_PRESETS:
        raise ValueError(f"Unknown aspect: {aspect}")
    if brand_key not in BRAND_PRESETS:
        raise ValueError(f"Unknown brand: {brand_key}")

    target_w, target_h = ASPECT_PRESETS[aspect]
    brand = BRAND_PRESETS[brand_key]

    # 1) 베이스 이미지 fit
    img = load_and_fit(base_image, target_w, target_h)

    # 2) 다크 그라디언트 오버레이
    img = apply_dark_gradient(img, brand, layout)

    # 3) 텍스트 합성
    draw = ImageDraw.Draw(img)
    margin_x = int(target_w * 0.07)
    text_max_width = target_w - 2 * margin_x

    # 자동 폰트 사이즈 (비율 적응)
    if title_size is None:
        title_size = int(target_w * 0.062)  # 1080 → 67, 1200 → 74
    title_font = load_font("bold", title_size)
    body_font = load_font("semibold", int(title_size * 0.62))

    # 카피 줄바꿈
    lines = wrap_text(copy_text, title_font, text_max_width)

    # 텍스트 위치 — 하단 그라디언트 영역 안 (layout=bottom 기준)
    line_h = int(title_size * 1.35)
    total_text_h = len(lines) * line_h
    if layout == "bottom":
        text_y = target_h - total_text_h - int(target_h * 0.18)
    elif layout == "center":
        text_y = (target_h - total_text_h) // 2
    elif layout == "top":
        text_y = int(target_h * 0.10)
    else:
        text_y = target_h - total_text_h - int(target_h * 0.15)

    # 액센트 바 (텍스트 위 — 가이드 베이지 #B79F8A 또는 라이트블루)
    bar_y = text_y - int(title_size * 0.55)
    bar_w = int(target_w * 0.08)
    draw.rectangle(
        [(margin_x, bar_y), (margin_x + bar_w, bar_y + 5)],
        fill=brand["accent"],
    )

    # 카피 본문
    draw_text_block(
        draw,
        lines,
        title_font,
        brand["text"],
        margin_x,
        text_y,
    )

    # 4) 워드마크 (하단 우측 또는 좌측)
    if show_wordmark:
        wm_size = int(target_w * 0.022)
        wm_font = load_font("medium", wm_size)
        wm_text = brand["wordmark"]
        wm_bbox = wm_font.getbbox(wm_text)
        wm_w = wm_bbox[2] - wm_bbox[0]
        wm_x = target_w - margin_x - wm_w
        wm_y = target_h - int(target_h * 0.055)
        draw.text((wm_x, wm_y), wm_text, font=wm_font, fill=brand["text_secondary"])

        # 좌측 하단 — 회사 정보
        info_size = int(target_w * 0.018)
        info_font = load_font("medium", info_size)
        info_text = "한남동 현대하이페리온"
        draw.text(
            (margin_x, wm_y + int(wm_size * 0.15)),
            info_text,
            font=info_font,
            fill=brand["text_secondary"],
        )

    # 5) 저장
    output.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(output, "JPEG", quality=92, optimize=True)

    return {
        "output": str(output),
        "aspect": aspect,
        "brand": brand_key,
        "layout": layout,
        "lines": len(lines),
        "size_kb": round(output.stat().st_size / 1024, 1),
    }


# -----------------------------------------------------------------
# 메인 페이지 영구 템플릿 (대표님 2026-05-06 큐레이션 가이드 v1.0)
# 모든 콘텐츠 인스타 1p가 이 템플릿을 따른다.
# 65% 사진 + 35% 정보 영역. 상단좌 W로고 + 상단우 사업부 컬러칩.
# 하단: 영문 대제목 + 한글 부제목 + 일자·장소 + 풋터 워드마크.
# -----------------------------------------------------------------
def compose_main_slide(
    base_image: Path,
    title_eng: str,
    title_kor: str,
    date_location: str,
    output: Path,
    aspect: str = "1080x1350",
    brand_key: str = "sports_club",
) -> dict:
    if aspect not in ASPECT_PRESETS:
        raise ValueError(f"Unknown aspect: {aspect}")
    if brand_key not in BRAND_PRESETS:
        raise ValueError(f"Unknown brand: {brand_key}")

    target_w, target_h = ASPECT_PRESETS[aspect]
    brand = BRAND_PRESETS[brand_key]

    # 캔버스 (배경 = 메인 브랜드 BLACK #221F20)
    canvas_bg = (34, 31, 32)
    canvas = Image.new("RGB", (target_w, target_h), canvas_bg)

    # 1) 사진 영역 — 상단 65% (BLACK + BEIGE 듀오톤 변환)
    photo_h = int(target_h * 0.65)
    photo = load_and_fit(base_image, target_w, photo_h)
    photo = to_duotone(photo)
    canvas.paste(photo, (0, 0))

    draw = ImageDraw.Draw(canvas)

    # 2) 상단 좌측 W 로고 (텍스트, 사진 위 오버레이)
    margin = int(target_w * 0.05)
    logo_size = int(target_w * 0.07)
    logo_font = load_font("bold", logo_size)
    # 로고 가독성을 위해 어두운 반투명 박스 깔기
    box_pad = int(logo_size * 0.3)
    logo_text = "W"
    lb = logo_font.getbbox(logo_text)
    lw = lb[2] - lb[0]
    lh = lb[3] - lb[1]
    box_overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_overlay)
    box_draw.rectangle(
        [(margin - box_pad, margin - box_pad // 2),
         (margin + lw + box_pad, margin + lh + box_pad)],
        fill=(34, 31, 32, 180),
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), box_overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin), logo_text, font=logo_font, fill=brand["primary"])

    # 3) 상단 우측 사업부 컬러 칩 (사각 + 사업부명)
    chip_w = int(target_w * 0.20)
    chip_h = int(target_h * 0.030)
    chip_x0 = target_w - margin - chip_w
    chip_y0 = margin
    draw.rectangle(
        [(chip_x0, chip_y0), (chip_x0 + chip_w, chip_y0 + chip_h)],
        fill=brand["primary"],
    )
    chip_label_size = int(target_h * 0.018)
    chip_font = load_font("medium", chip_label_size)
    chip_label = brand["wordmark"].split("  ", 1)[-1] if "  " in brand["wordmark"] else brand["wordmark"]
    cb = chip_font.getbbox(chip_label)
    cw = cb[2] - cb[0]
    ch = cb[3] - cb[1]
    draw.text(
        (chip_x0 + (chip_w - cw) // 2, chip_y0 + (chip_h - ch) // 2 - 2),
        chip_label,
        font=chip_font,
        fill=(255, 255, 255),
    )

    # 4) 하단 정보 영역 (사진 영역 아래 35%)
    info_y0 = photo_h
    info_h = target_h - photo_h

    # 베이지 가는 분리선 (사진/정보 영역 경계)
    line_y = info_y0 + int(info_h * 0.05)
    line_w = int(target_w * 0.10)
    draw.rectangle(
        [(margin, line_y), (margin + line_w, line_y + 4)],
        fill=brand["primary"],
    )

    # 영문 대제목 (대문자, Pretendard Bold)
    eng_size = int(target_w * 0.046)
    eng_font = load_font("bold", eng_size)
    eng_y = line_y + int(info_h * 0.10)
    eng_text = title_eng.upper()
    # 자간 효과 = 글자 단위로 그리기
    cx = margin
    for ch in eng_text:
        draw.text((cx, eng_y), ch, font=eng_font, fill=(255, 255, 255))
        bb = eng_font.getbbox(ch)
        cx += (bb[2] - bb[0]) + int(eng_size * 0.08)

    # 한글 부제목 (Pretendard SemiBold)
    kor_size = int(target_w * 0.028)
    kor_font = load_font("semibold", kor_size)
    kor_y = eng_y + int(eng_size * 1.6)
    draw.text((margin, kor_y), title_kor, font=kor_font, fill=brand["primary"])

    # 일자·장소
    date_size = int(target_w * 0.020)
    date_font = load_font("medium", date_size)
    date_y = kor_y + int(kor_size * 1.8)
    draw.text((margin, date_y), date_location, font=date_font, fill=(200, 200, 200))

    # 풋터 워드마크 — 하단 중앙 WELLPERION
    footer_size = int(target_w * 0.025)
    footer_font = load_font("medium", footer_size)
    footer_text = "WELLPERION"
    fb = footer_font.getbbox(footer_text)
    fw = fb[2] - fb[0]
    fh = fb[3] - fb[1]
    footer_y = target_h - margin - fh
    draw.text(
        ((target_w - fw) // 2, footer_y),
        footer_text,
        font=footer_font,
        fill=brand["primary"],
    )

    # 저장
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=92, optimize=True)
    return {
        "output": str(output),
        "aspect": aspect,
        "brand": brand_key,
        "layout": "main_template",
        "size_kb": round(output.stat().st_size / 1024, 1),
    }


# -----------------------------------------------------------------
# 통일 양식 스토리 슬라이드 (2026-05-20 GM님 결정)
# 메인 페이지 영구 템플릿 v1 기반 — 모든 슬라이드(1p~Np) 동일 양식
# 65% 사진(듀오톤) + 35% 정보 영역 + 헤더(W로고+칩) + 풋터
# -----------------------------------------------------------------
def compose_unified_slide(
    base_image: Path,
    label_eng: str,
    body_text: str,
    output: Path,
    aspect: str = "1080x1350",
    brand_key: str = "main",
    footer_meta: str | None = None,
) -> dict:
    """통일 양식 스토리 슬라이드. 사진과 텍스트 영역 완전 분리.

    Args:
        label_eng: 영문 라벨 (정보 영역 상단, 대문자, 작게)
        body_text: 한글 본문 (줄바꿈 \\n 구분 다중 줄)
        footer_meta: 풋터 라인 (예: "litt.ly/wellperion") — 옵션
    """
    if aspect not in ASPECT_PRESETS:
        raise ValueError(f"Unknown aspect: {aspect}")
    if brand_key not in BRAND_PRESETS:
        raise ValueError(f"Unknown brand: {brand_key}")

    target_w, target_h = ASPECT_PRESETS[aspect]
    brand = BRAND_PRESETS[brand_key]

    canvas_bg = (34, 31, 32)
    canvas = Image.new("RGB", (target_w, target_h), canvas_bg)

    # 1) 사진 영역 — 상단 65% (BLACK + BEIGE 듀오톤)
    photo_h = int(target_h * 0.65)
    photo = load_and_fit(base_image, target_w, photo_h)
    photo = to_duotone(photo)
    canvas.paste(photo, (0, 0))

    draw = ImageDraw.Draw(canvas)
    margin = int(target_w * 0.05)

    # 2) 상단 좌측 W 로고 (반투명 박스)
    logo_size = int(target_w * 0.07)
    logo_font = load_font("bold", logo_size)
    box_pad = int(logo_size * 0.3)
    logo_text = "W"
    lb = logo_font.getbbox(logo_text)
    lw = lb[2] - lb[0]
    lh = lb[3] - lb[1]
    box_overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_overlay)
    box_draw.rectangle(
        [(margin - box_pad, margin - box_pad // 2),
         (margin + lw + box_pad, margin + lh + box_pad)],
        fill=(34, 31, 32, 180),
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), box_overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin), logo_text, font=logo_font, fill=brand["primary"])

    # 3) 상단 우측 사업부 칩
    chip_w = int(target_w * 0.20)
    chip_h = int(target_h * 0.030)
    chip_x0 = target_w - margin - chip_w
    chip_y0 = margin
    draw.rectangle(
        [(chip_x0, chip_y0), (chip_x0 + chip_w, chip_y0 + chip_h)],
        fill=brand["primary"],
    )
    chip_label_size = int(target_h * 0.018)
    chip_font = load_font("medium", chip_label_size)
    chip_label = brand["wordmark"].split("  ", 1)[-1] if "  " in brand["wordmark"] else brand["wordmark"]
    cb = chip_font.getbbox(chip_label)
    cw = cb[2] - cb[0]
    ch_h = cb[3] - cb[1]
    draw.text(
        (chip_x0 + (chip_w - cw) // 2, chip_y0 + (chip_h - ch_h) // 2 - 2),
        chip_label,
        font=chip_font,
        fill=(255, 255, 255),
    )

    # 4) 하단 정보 영역
    info_y0 = photo_h
    info_h = target_h - photo_h

    # 베이지 분리선 (사진/정보 영역 경계)
    line_y = info_y0 + int(info_h * 0.05)
    line_w = int(target_w * 0.10)
    draw.rectangle(
        [(margin, line_y), (margin + line_w, line_y + 4)],
        fill=brand["primary"],
    )

    # 영문 라벨 (작게)
    label_size = int(target_w * 0.026)
    label_font = load_font("bold", label_size)
    label_y = line_y + int(info_h * 0.07)
    label_text = label_eng.upper() if label_eng else ""
    cx = margin
    for ch_ in label_text:
        draw.text((cx, label_y), ch_, font=label_font, fill=brand["primary"])
        bb = label_font.getbbox(ch_)
        cx += (bb[2] - bb[0]) + int(label_size * 0.08)

    # 한글 본문 (다중 줄)
    body_size = int(target_w * 0.029)
    body_font = load_font("semibold", body_size)
    body_y = label_y + int(label_size * 2.0) if label_text else label_y
    body_line_h = int(body_size * 1.55)
    for line in body_text.split("\n"):
        draw.text((margin, body_y), line, font=body_font, fill=(255, 255, 255))
        body_y += body_line_h

    # 풋터 메타 (옵션)
    if footer_meta:
        meta_size = int(target_w * 0.020)
        meta_font = load_font("medium", meta_size)
        meta_y = target_h - margin - int(meta_size * 2.6)
        draw.text((margin, meta_y), footer_meta, font=meta_font, fill=brand["primary"])

    # 풋터 워드마크 — 하단 중앙 WELLPERION
    footer_size = int(target_w * 0.022)
    footer_font = load_font("medium", footer_size)
    footer_text = "WELLPERION"
    fb = footer_font.getbbox(footer_text)
    fw = fb[2] - fb[0]
    fh = fb[3] - fb[1]
    footer_y = target_h - margin - fh
    draw.text(
        ((target_w - fw) // 2, footer_y),
        footer_text,
        font=footer_font,
        fill=brand["primary"],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=92, optimize=True)
    return {
        "output": str(output),
        "aspect": aspect,
        "brand": brand_key,
        "layout": "unified_template",
        "size_kb": round(output.stat().st_size / 1024, 1),
    }


# -----------------------------------------------------------------
# 텍스트 중심 슬라이드 (2026-05-29 시드 #09 — GM 개인 계정 생각 리더십)
# 사진 없이 브랜드 BLACK 배경 + 베이지/화이트 타이포만.
# eng_title 있으면 표지(영문 대제목+한글 부제목), 없으면 본문(헤딩+본문).
# -----------------------------------------------------------------
def compose_text_slide(
    output: Path,
    kor_title: str,
    eng_title: str | None = None,
    body: str | None = None,
    footer_meta: str | None = None,
    brand_key: str = "main",
    aspect: str = "1080x1350",
) -> dict:
    """사진 없는 텍스트 중심 슬라이드. 럭셔리 매거진 무드의 여백 중심 레이아웃."""
    if aspect not in ASPECT_PRESETS:
        raise ValueError(f"Unknown aspect: {aspect}")
    if brand_key not in BRAND_PRESETS:
        raise ValueError(f"Unknown brand: {brand_key}")

    target_w, target_h = ASPECT_PRESETS[aspect]
    brand = BRAND_PRESETS[brand_key]

    canvas = Image.new("RGB", (target_w, target_h), brand["background"])
    draw = ImageDraw.Draw(canvas)
    margin = int(target_w * 0.085)
    text_max_width = target_w - 2 * margin

    # 1) 헤더 — 좌측 W 로고 + 우측 워드마크
    logo_size = int(target_w * 0.055)
    logo_font = load_font("bold", logo_size)
    draw.text((margin, margin), "W", font=logo_font, fill=brand["primary"])
    wm_size = int(target_w * 0.020)
    wm_font = load_font("medium", wm_size)
    wm_text = "WELLPERION"
    wb = wm_font.getbbox(wm_text)
    draw.text(
        (target_w - margin - (wb[2] - wb[0]), margin + int(logo_size * 0.30)),
        wm_text, font=wm_font, fill=brand["text_secondary"],
    )

    # 2) 본문 블록 — 표지/본문 분기
    is_cover = eng_title is not None
    if is_cover:
        eng_size = int(target_w * 0.072)
        eng_font = load_font("bold", eng_size)
        kor_size = int(target_w * 0.040)
        kor_font = load_font("semibold", kor_size)
    else:
        eng_size = 0
        kor_size = int(target_w * 0.052)
        kor_font = load_font("bold", kor_size)
    body_size = int(target_w * 0.032)
    body_font = load_font("semibold", body_size)

    # 줄 구성 계산 (수직 중앙 정렬을 위해 총 높이 선계산)
    blocks: list[tuple] = []  # (font, color, lines, line_h, gap_after)
    if is_cover:
        eng_lines = wrap_text(eng_title.upper(), eng_font, text_max_width)
        blocks.append((eng_font, brand["text"], eng_lines,
                       int(eng_size * 1.18), int(eng_size * 0.55)))
        kor_lines = wrap_text(kor_title, kor_font, text_max_width)
        blocks.append((kor_font, brand["primary"], kor_lines,
                       int(kor_size * 1.45), 0))
    else:
        kor_lines = wrap_text(kor_title, kor_font, text_max_width)
        blocks.append((kor_font, brand["text"], kor_lines,
                       int(kor_size * 1.30), int(kor_size * 0.70)))
        if body:
            body_lines = wrap_text(body, body_font, text_max_width)
            blocks.append((body_font, brand["text_secondary"], body_lines,
                           int(body_size * 1.55), 0))

    bar_h = int(target_h * 0.012)
    bar_gap = int(target_h * 0.045)
    total_h = bar_h + bar_gap + sum(
        len(lines) * lh + gap for _, _, lines, lh, gap in blocks)
    start_y = (target_h - total_h) // 2

    # 액센트 바 (하이라이트 #ED5B3F)
    bar_w = int(target_w * 0.11)
    draw.rectangle(
        [(margin, start_y), (margin + bar_w, start_y + bar_h)],
        fill=brand["accent"],
    )
    cy = start_y + bar_h + bar_gap
    for font, color, lines, line_h, gap in blocks:
        for line in lines:
            draw.text((margin, cy), line, font=font, fill=color)
            cy += line_h
        cy += gap

    # 3) 풋터 — 옵션 메타 + 중앙 워드마크
    if footer_meta:
        fm_size = int(target_w * 0.021)
        fm_font = load_font("medium", fm_size)
        draw.text((margin, target_h - margin - int(fm_size * 2.7)),
                  footer_meta, font=fm_font, fill=brand["primary"])
    footer_size = int(target_w * 0.023)
    footer_font = load_font("medium", footer_size)
    ftext = "WELLPERION"
    fb = footer_font.getbbox(ftext)
    draw.text(((target_w - (fb[2] - fb[0])) // 2,
               target_h - margin - (fb[3] - fb[1])),
              ftext, font=footer_font, fill=brand["primary"])

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=92, optimize=True)
    return {
        "output": str(output),
        "aspect": aspect,
        "brand": brand_key,
        "layout": "text_cover" if is_cover else "text_body",
        "size_kb": round(output.stat().st_size / 1024, 1),
    }


# -----------------------------------------------------------------
# CLI
# -----------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="웰페리온 슬라이드 자동 합성 v1.0")
    p.add_argument("--base-image", required=True, type=Path)
    p.add_argument("--copy-text", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--aspect", default="1080x1350", choices=ASPECT_PRESETS.keys())
    p.add_argument("--brand", default="sports_club", choices=BRAND_PRESETS.keys())
    p.add_argument("--layout", default="bottom", choices=["bottom", "center", "top"])
    p.add_argument("--title-size", type=int, default=None)
    p.add_argument("--no-wordmark", action="store_true")
    args = p.parse_args()

    if not args.base_image.exists():
        print(f"[ERROR] base image not found: {args.base_image}")
        sys.exit(2)

    result = compose_slide(
        base_image=args.base_image,
        copy_text=args.copy_text,
        output=args.output,
        aspect=args.aspect,
        brand_key=args.brand,
        layout=args.layout,
        title_size=args.title_size,
        show_wordmark=not args.no_wordmark,
    )
    print(f"[OK] {result['output']} ({result['size_kb']}KB, {result['lines']} lines)")


if __name__ == "__main__":
    main()
