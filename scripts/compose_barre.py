"""바레 런칭 슬라이드 합성 스크립트
레퍼런스: instagram/260520_발레_런칭/output(인스타그램)/ (발레 완성본)
           instagram/260426_WJO_스쿼시_대회/output(인스타그램)/ (스쿼시 완성본)
완성본 1:1 구현 — Canva 완성본 픽셀 실측 기반.

캔버스: 1080x1080
구조: 전체 사진 fill + 하단 그라디언트(y=600~) + 로고PNG 좌상단 + 우상단 칩 + 카운터
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter
import numpy as np

PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")
LOGO_DIR = PROJECT_ROOT / "instagram" / "_assets" / "logo"
LOGO_WHITE_ALPHA = LOGO_DIR / "wellperion_white_alpha.png"

_FONT_DIR_CANDIDATES = [
    PROJECT_ROOT / "brand" / "font",
    PROJECT_ROOT / "2. 브랜드_공식문서" / "font",
]
FONT_DIR = next((d for d in _FONT_DIR_CANDIDATES if d.exists()), _FONT_DIR_CANDIDATES[0])
FONT_BOLD = FONT_DIR / "Pretendard-Bold.otf"
FONT_SEMIBOLD = FONT_DIR / "Pretendard-SemiBold.otf"
FONT_MEDIUM = FONT_DIR / "Pretendard-Medium.otf"

# 브랜드 색상
BEIGE = (183, 159, 138)       # #B79F8A
BLACK_BG = (34, 31, 32)       # #221F20
WHITE = (255, 255, 255)
GRAY = (170, 160, 152)        # 날짜·메타 텍스트
CHIP_BEIGE = (186, 162, 140)  # 우상단 칩 배경

W, H = 1080, 1080


def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = {"bold": FONT_BOLD, "semibold": FONT_SEMIBOLD, "medium": FONT_MEDIUM}.get(weight, FONT_BOLD)
    if not path.exists():
        raise FileNotFoundError(f"Font not found: {path}")
    return ImageFont.truetype(str(path), size)


def center_crop_fill(img_path: Path, w: int, h: int) -> Image.Image:
    """원본 이미지를 center-crop으로 w×h에 fill."""
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    sw, sh = img.size
    target_ratio = w / h
    src_ratio = sw / sh
    if src_ratio > target_ratio:
        nw = int(sh * target_ratio)
        x0 = (sw - nw) // 2
        img = img.crop((x0, 0, x0 + nw, sh))
    else:
        nh = int(sw / target_ratio)
        y0 = (sh - nh) // 2
        img = img.crop((0, y0, sw, y0 + nh))
    return img.resize((w, h), Image.LANCZOS)


def apply_bottom_gradient(img: Image.Image, gradient_start_y: int = 580) -> Image.Image:
    """하단 그라디언트 오버레이 — 완성본 실측 기반."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(H):
        if y < gradient_start_y:
            alpha = 0
        else:
            t = (y - gradient_start_y) / (H - gradient_start_y)
            # 완성본 곡선: 중간은 완만, 하단은 짙게
            alpha = int(255 * (t ** 1.2))
            alpha = min(230, alpha)
        draw.line([(0, y), (W, y)], fill=(*BLACK_BG, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def paste_logo(canvas: Image.Image, logo_w: int = 130) -> Image.Image:
    """공식 로고 PNG 좌상단 합성 — 박스 없이 직접 올림 (완성본 기준)."""
    logo = Image.open(LOGO_WHITE_ALPHA).convert("RGBA")
    orig_w, orig_h = logo.size
    logo_h = int(orig_h * logo_w / orig_w)
    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
    x, y = 40, 36
    base = canvas.convert("RGBA")
    base.paste(logo, (x, y), mask=logo)
    return base.convert("RGB")


def draw_chip(draw: ImageDraw.ImageDraw, label: str, font: ImageFont.FreeTypeFont,
              chip_x: int, chip_y: int, chip_w: int, chip_h: int) -> None:
    """우상단 둥근 칩 — 완성본: 베이지 fill, 흰색 텍스트."""
    draw.rounded_rectangle(
        [(chip_x, chip_y), (chip_x + chip_w, chip_y + chip_h)],
        radius=chip_h // 2,
        fill=CHIP_BEIGE,
    )
    bb = font.getbbox(label)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    tx = chip_x + (chip_w - tw) // 2
    ty = chip_y + (chip_h - th) // 2 - 1
    draw.text((tx, ty), label, font=font, fill=WHITE)


def draw_counter(draw: ImageDraw.ImageDraw, current: int, total: int,
                 font: ImageFont.FreeTypeFont, chip_x: int, chip_y: int, chip_h: int) -> None:
    """카운터 — 배경 없이 텍스트만, 칩 아래 우측 정렬 (완성본 기준)."""
    text = f"{current:02d} / {total:02d}"
    bb = font.getbbox(text)
    tw = bb[2] - bb[0]
    # 우측 정렬: 칩 우측 끝 기준
    chip_right = chip_x + 240  # 칩 오른쪽 끝
    tx = chip_right - tw
    ty = chip_y + chip_h + 8
    draw.text((tx, ty), text, font=font, fill=WHITE)


# ---------------------------------------------------------------------------
# 표지 (1p) — 완성본 발레 ig_01 기준
# ---------------------------------------------------------------------------
def compose_cover(
    photo_path: Path,
    title_eng: str,          # "BARRE"
    title_kor: str,          # "클래식 바레"
    date_location: str,      # "2026.05 OPEN  ·  한남동 웰니스 스튜디오"
    output_path: Path,
) -> None:
    canvas = center_crop_fill(photo_path, W, H)

    # 밝기 약간 어둡게 (완성본 분위기)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.88)

    # 하단 그라디언트
    canvas = apply_bottom_gradient(canvas, gradient_start_y=570)

    # 로고 PNG
    canvas = paste_logo(canvas, logo_w=130)

    draw = ImageDraw.Draw(canvas)

    # 우상단 칩
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 분리선 — 전폭 얇은 선 (완성본: y=701, x=50~1030)
    line_y = 700
    draw.rectangle([(50, line_y), (1030, line_y + 2)], fill=(120, 105, 92))

    # 한글 부제목 — 베이지, 분리선 아래 (완성본: y≈800)
    kor_font = load_font("semibold", 38)
    draw.text((W // 2, 790), title_kor,
              font=kor_font, fill=BEIGE, anchor="mm")

    # 영문 대제목 — 흰색 bold large (완성본: y≈847)
    eng_font = load_font("bold", 88)
    draw.text((W // 2, 848), title_eng,
              font=eng_font, fill=WHITE, anchor="mm")

    # 얇은 분리선 (한글 아래) — 완성본 ig_01 기준
    sub_line_y = 920
    sub_line_w = 60
    draw.rectangle(
        [(W // 2 - sub_line_w // 2, sub_line_y),
         (W // 2 + sub_line_w // 2, sub_line_y + 2)],
        fill=BEIGE,
    )

    # 일자·장소 — 회색 (완성본: y≈953)
    date_font = load_font("medium", 26)
    draw.text((W // 2, 960), date_location,
              font=date_font, fill=GRAY, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 스토리 슬라이드 — 완성본 발레 ig_02~06 기준
# ---------------------------------------------------------------------------
def compose_story(
    photo_path: Path,
    meta_line: str,           # "BARRE 2026.05  ·  2026.05 OPEN"
    title_kor: str,           # "클래식의 우아함"
    sub_text: str,            # "박상아 BARRE INSTRUCTOR"
    footer_text: str,         # "WELLPERION  ·  BARRE"
    current: int,             # 슬라이드 번호
    total: int,               # 전체 슬라이드 수 (영상 포함)
    output_path: Path,
    chip_label: str = "WELLPERION",
) -> None:
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=555)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    # 우상단 칩
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, chip_label, chip_font, chip_x, chip_y, chip_w, chip_h)

    # 카운터 — 칩 아래, 배경 없음
    counter_font = load_font("medium", 28)
    draw_counter(draw, current, total, counter_font, chip_x, chip_y, chip_h)

    # 메타라인 (완성본: y≈800, 베이지/회색 작은 텍스트)
    meta_font = load_font("medium", 26)
    draw.text((40, 795), meta_line, font=meta_font, fill=GRAY)

    # 한글 대제목 (완성본: y≈886, 흰색 bold)
    title_font = load_font("bold", 64)
    draw.text((40, 860), title_kor, font=title_font, fill=WHITE)

    # 서브텍스트 (완성본: y≈962, 베이지)
    sub_font = load_font("semibold", 30)
    draw.text((40, 958), sub_text, font=sub_font, fill=BEIGE)

    # 풋터 (완성본: y≈1026~1039)
    footer_font = load_font("medium", 26)
    draw.text((40, 1026), footer_text, font=footer_font, fill=BEIGE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{current:02d}/{total:02d}] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 바레 런칭 슬라이드 세트 실행
# ---------------------------------------------------------------------------
def main():
    src = PROJECT_ROOT / "instagram" / "Image" / "바레_런칭(원본 이미지)"
    out_dir = PROJECT_ROOT / "instagram" / "260520_바레_런칭" / "output(인스타그램)"

    # 소스 이미지 확인
    main_photo = src / "main.jpg"
    photos = [
        src / "바레1.png",
        src / "바레2.png",
        src / "바레3.png",
        src / "바레4.png",
    ]
    video_src = src / "바레 강습 공간.mp4"

    for p in [main_photo] + photos:
        if not p.exists():
            print(f"[ERROR] 소스 없음: {p}")
            sys.exit(1)

    TOTAL = 6   # 사진5 + 영상1

    print("=== 바레 런칭 슬라이드 합성 시작 ===")
    print(f"출력 폴더: {out_dir}")

    # ig_01 — 표지
    compose_cover(
        photo_path=main_photo,
        title_eng="BARRE",
        title_kor="클래식 바레",
        date_location="2026.05 OPEN  ·  한남동 웰니스 스튜디오",
        output_path=out_dir / "ig_01.jpg",
    )

    # ig_02~05 — 수업 슬라이드
    story_data = [
        (photos[0], "BARRE 2026.05  ·  2026.05 OPEN", "움직임이 시작됩니다", "근력 · 코어 · 균형 강화"),
        (photos[1], "BARRE 2026.05  ·  2026.05 OPEN", "정교한 동작의 반복", "매주 화요일 오전 10시 / 11시"),
        (photos[2], "BARRE 2026.05  ·  2026.05 OPEN", "함께 완성하는 자세", "박상아 BARRE INSTRUCTOR"),
        (photos[3], "BARRE 2026.05  ·  2026.05 OPEN", "특별한 움직임의 여정", "WELLPERION SPA&FITNESS"),
    ]
    for idx, (photo, meta, title_kor, sub) in enumerate(story_data, start=2):
        compose_story(
            photo_path=photo,
            meta_line=meta,
            title_kor=title_kor,
            sub_text=sub,
            footer_text="WELLPERION  ·  BARRE",
            current=idx,
            total=TOTAL,
            output_path=out_dir / f"ig_{idx:02d}.jpg",
        )

    # ig_06 — 영상 (복사)
    import shutil
    video_dst = out_dir / "ig_06.mp4"
    if video_src.exists():
        shutil.copy2(video_src, video_dst)
        print(f"  [영상] ig_06.mp4 복사 완료 ({video_dst.stat().st_size // 1024}KB)")
    else:
        print(f"  [경고] 영상 원본 없음: {video_src}")

    print("=== 합성 완료 ===")
    print(f"출력 파일: {out_dir}")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name}  {f.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
