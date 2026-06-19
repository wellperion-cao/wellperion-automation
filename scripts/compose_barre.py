"""웰페리온 슬라이드 디자인 — 사진형 정본 엔진 (compose_barre)

★ 디자인 정본 = 이 코드다 (2026-06-05 GM 결정 · 캔바(Canva) 의존 폐기).
  - 바레 '정본'은 원래 캔바 제작본이었고 코드는 그걸 모방했으나, 캔바 원본 확보가 불가하여
    영구 픽셀 불일치였다(GM 반복 미세수정의 근본 원인). → 캔바 추격 종료. 이 코드가 유일 SSOT(정본).
  - "캔바와 다르다"는 더 이상 결함이 아니다. 전 사진형 콘텐츠(바레·발레·WJO 등)는 이 엔진을 단일
    출처로 사용하고, compose_ballet 등은 이 모듈의 스타일 함수(draw_chip·paste_logo·to_duotone 등)를
    import 재사용한다 → 콘텐츠 간 픽셀 100% 일치.
  - 색·폰트·로고 상수 SSOT = scripts/brand_constants.py.

캔버스: 1080x1080
구조: 전체 사진 fill + 하단 그라디언트(y=600~) + 로고PNG 좌상단 + 우상단 칩 + 카운터
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter
import numpy as np

# 색·폰트·로고 상수 SSOT = scripts/brand_constants.py (값 불변 이관)
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (  # noqa: E402
    PROJECT_ROOT,
    LOGO_DIR, LOGO_WHITE_ALPHA,
    FONT_DIR, FONT_BOLD, FONT_SEMIBOLD, FONT_MEDIUM,
    BEIGE, BLACK_BG, WHITE, GRAY, CHIP_BEIGE,
    DUOTONE_DARK, DUOTONE_LIGHT,
)

W, H = 1080, 1080


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_duotone(img: Image.Image,
               dark_hex: str = DUOTONE_DARK,
               light_hex: str = DUOTONE_LIGHT,
               normalize: bool = False) -> Image.Image:
    """BLACK + BEIGE 듀오톤 변환 (정본 표준).
    normalize=True: autocontrast로 원본 밝기·대비를 정규화 → 밝은 흰배경 표지가 듀오톤 후
    흐려지고 로고·칩이 묻히는 문제 방지(콘텐츠 간 표지 톤 일관, 2026-06-05 정본 셋팅)."""
    gray = img.convert("L")
    if normalize:
        gray = ImageOps.autocontrast(gray, cutoff=1)
    dr, dg, db = _hex_to_rgb(dark_hex)
    lr, lg, lb = _hex_to_rgb(light_hex)
    r_lut = [int(dr + (lr - dr) * (i / 255)) for i in range(256)]
    g_lut = [int(dg + (lg - dg) * (i / 255)) for i in range(256)]
    b_lut = [int(db + (lb - db) * (i / 255)) for i in range(256)]
    return Image.merge("RGB", (
        gray.point(r_lut), gray.point(g_lut), gray.point(b_lut)))


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
    # 가독성: 배경박스 없이(GM 지시 준수) 다크 아웃라인으로 밝은 배경에서도 또렷하게
    draw.text((tx, ty), text, font=font, fill=WHITE,
              stroke_width=2, stroke_fill=BLACK_BG)


# ---------------------------------------------------------------------------
# 표지 (1p) — 발레 완성본 ig_01 1:1 정합 구조
# 사진 상단 65%(y=0~700, 듀오톤) + 분리선(y=701~702) + 검정 하단 35%(y=703~1080)
# 검정영역: 한글 부제(베이지) → 영문 대제목(흰색) → 베이지 얇은 선 → 날짜·장소(회색)
# ---------------------------------------------------------------------------
def compose_cover(
    photo_path: Path,
    title_eng: str,          # "BARRE"
    title_kor: str,          # "클래식 바레"
    date_location: str,      # "2026.05 OPEN  ·  한남동 웰니스 스튜디오"
    output_path: Path,
) -> None:
    # 1) 캔버스 — 순수 #221F20 검정 배경 (하단 35% 보장)
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    # 2) 사진 영역 — 상단 65% (y=0~700), 듀오톤 BLACK+BEIGE
    PHOTO_H = 700  # 1080 × 0.648 ≈ 700 (발레 완성본 실측 y=701 경계)
    photo = center_crop_fill(photo_path, W, PHOTO_H)
    photo = to_duotone(photo, normalize=True)  # 표지 톤 일관 — 밝은 표지도 로고·칩 대비 확보
    canvas.paste(photo, (0, 0))

    # 3) 분리선 (발레 완성본 실측: y=701~702, 전폭 x=50~1030, RGB≈171,161,151)
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=(171, 161, 151))

    # 4) 로고 PNG 좌상단 (사진 위, 박스 없이)
    canvas = paste_logo(canvas, logo_w=130)

    draw = ImageDraw.Draw(canvas)

    # 5) 우상단 칩 (발레 완성본: 베이지 둥근 칩, 흰색 "WELLPERION")
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 6) 검정 정보영역 텍스트 — 발레 완성본 y좌표 1:1
    # 한글 부제목 (베이지, 중앙, 발레 실측 y≈770~807 → anchor="mm" y=789)
    kor_font = load_font("semibold", 38)
    draw.text((W // 2, 789), title_kor, font=kor_font, fill=BEIGE, anchor="mm")

    # 영문 대제목 (흰색 bold, 중앙, 발레 실측 y≈849~868 → anchor="mm" y=859)
    eng_font = load_font("bold", 88)
    draw.text((W // 2, 859), title_eng, font=eng_font, fill=WHITE, anchor="mm")

    # 베이지 얇은 분리선 (발레 완성본 기준: y≈920, 중앙 60px)
    sub_line_y = 920
    draw.rectangle(
        [(W // 2 - 30, sub_line_y), (W // 2 + 30, sub_line_y + 2)],
        fill=BEIGE,
    )

    # 날짜·장소 (회색, 중앙, 발레 실측 y≈953~971 → anchor="mm" y=962)
    date_font = load_font("medium", 26)
    draw.text((W // 2, 962), date_location, font=date_font, fill=GRAY, anchor="mm")

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
# GUIDE 카드 슬라이드 — 원본 자체가 완성본, 합성 없이 1080x1080 리사이즈 복사
# (guideline_card.jpg에 이미 로고·칩·레이아웃 포함 — 이중 합성 금지)
# ---------------------------------------------------------------------------
def compose_guide_card(output_path: Path) -> None:
    """WELLPERION GUIDE 카드. 원본 그대로 1080x1080 복사."""
    guide_src = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card.jpg"
    if not guide_src.exists():
        raise FileNotFoundError(f"GUIDE 카드 없음: {guide_src}")

    img = Image.open(guide_src).convert("RGB")
    # 이미 1080x1080이면 그대로, 아니면 center-crop fit
    if img.size != (W, H):
        img = center_crop_fill(guide_src, W, H)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [가이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 바레 런칭 슬라이드 세트 실행 — 최종 구성
#
# ig_01  표지          검정 정보영역, 카운터 없음
# ig_02  바레1 수업컷  카운터 02/06
# ig_03  바레2 수업컷  카운터 03/06
# ig_04  바레3 수업컷  카운터 04/06
# ig_05  GUIDE 카드   카운터 없음
# ig_06  영상 mp4     카운터 없음
#
# 바레4 제외: 바레2(세 명 런지)와 동일 인물·동일 포즈 중복
# 카운터 분모 = 전체 파일 수 6 (발레 완성본 패턴과 동일)
# ---------------------------------------------------------------------------
def main():
    import shutil

    src = PROJECT_ROOT / "instagram" / "Image" / "바레_런칭(원본 이미지)"
    out_dir = PROJECT_ROOT / "instagram" / "260520_바레_런칭" / "output(인스타그램)"
    out_dir.mkdir(parents=True, exist_ok=True)

    main_photo = src / "main.jpg"
    video_src  = src / "바레 강습 공간.mp4"

    # 본문 사진: 바레1·2·3 (바레4는 바레2와 중복 → 제외)
    story_photos = [
        src / "바레1.png",
        src / "바레2.png",
        src / "바레3.png",
    ]

    for p in [main_photo] + story_photos:
        if not p.exists():
            print(f"[ERROR] 소스 없음: {p}")
            sys.exit(1)

    TOTAL = 6  # 전체 파일 수 (표지+본문3+가이드+영상)

    print("=== 바레 런칭 슬라이드 합성 (최종 구성) ===")
    print(f"출력: {out_dir}")
    print(f"구성: ig_01(표지) / ig_02~04(수업3컷) / ig_05(GUIDE) / ig_06(영상)")

    # ig_01 — 표지 (검정 정보영역 65/35 구조)
    compose_cover(
        photo_path=main_photo,
        title_eng="BARRE",
        title_kor="클래식 바레",
        date_location="2026.05 OPEN  ·  한남동 웰니스 스튜디오",
        output_path=out_dir / "ig_01.jpg",
    )

    # ig_02~04 — 수업 슬라이드 (카운터 02/06 ~ 04/06)
    story_data = [
        (story_photos[0], "BARRE 2026.05  ·  2026.05 OPEN", "움직임이 시작됩니다",  "근력 · 코어 · 균형 강화"),
        (story_photos[1], "BARRE 2026.05  ·  2026.05 OPEN", "정교한 동작의 반복",   "매주 화요일 오전 10시 / 11시"),
        (story_photos[2], "BARRE 2026.05  ·  2026.05 OPEN", "함께 완성하는 자세",   "박상아 BARRE INSTRUCTOR"),
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

    # ig_05 — WELLPERION GUIDE 카드 (카운터 없음)
    compose_guide_card(output_path=out_dir / "ig_05.jpg")

    # ig_06 — 영상 (카운터 없음, 단순 복사 — gitignore 대상)
    video_dst = out_dir / "ig_06.mp4"
    if video_src.exists():
        shutil.copy2(video_src, video_dst)
        print(f"  [영상] ig_06.mp4 복사 완료 ({video_dst.stat().st_size // 1024}KB)")
    else:
        print(f"  [경고] 영상 원본 없음: {video_src}")

    print()
    print("=== 합성 완료 ===")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name}  {f.stat().st_size // 1024}KB")
    print(f"출력 파일: {out_dir}")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name}  {f.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
