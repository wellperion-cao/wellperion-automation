"""발레 런칭 슬라이드 합성 스크립트 (바레 벤치마킹 1:1)
레퍼런스: scripts/compose_barre.py (바레 완성본 generator) — 동일 레이아웃·톤·폰트·좌표.
완성본 정합 목표: 바레 ig_01~05 와 톤·구성·타이포 100% 통일.

캔버스: 1080x1080
구조:
  ig_01 표지   = 사진 상단 65%(듀오톤) + 검정 하단 35% 정보영역 (카운터 없음)
  ig_02~04 본문 = 전체 사진 fill + 하단 그라디언트 + 좌하단 텍스트 + 우상단 칩 + 카운터
  ig_05 가이드  = guideline_card.jpg 원본 복사 (카운터 없음)

캡션 정본(큐레이션_추천.md) 기준 텍스트:
  - 일정: 매주 금요일 오전 10시 / 11시
  - 강사: 이수지 인스트럭터 (현 포시즌스·국제갤러리·여의도 브라이튼)
  - 정원: 최대 8인 (프라이빗 소그룹)
  - 장소: 한남동 웰페리온 웰니스 스튜디오
  - ※ 비용 언급 금지 (캡션에 없음)
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps

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

# 브랜드 색상 (바레 완성본과 동일)
BEIGE = (183, 159, 138)       # #B79F8A
BLACK_BG = (34, 31, 32)       # #221F20
WHITE = (255, 255, 255)
GRAY = (170, 160, 152)        # 날짜·메타 텍스트
CHIP_BEIGE = (186, 162, 140)  # 우상단 칩 배경

W, H = 1080, 1080


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_duotone(img: Image.Image,
               dark_hex: str = "#221F20",
               light_hex: str = "#B79F8A") -> Image.Image:
    """BLACK + BEIGE 듀오톤 변환 (바레·발레 완성본 표준)."""
    gray = img.convert("L")
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


def top_crop_fill(img_path: Path, w: int, h: int,
                  x_bias: float = 0.5, top_bias: float = 0.18,
                  zoom: float = 1.0) -> Image.Image:
    """표지용 — 상단(머리/얼굴)을 살리는 top-biased crop.
    x_bias: 가로 크롭 위치(인물이 좌/우로 치우친 사진 보정). zoom>1: 인물 확대(빈 배경 축소)."""
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    sw, sh = img.size
    tr = w / h
    sr = sw / sh
    if sr > tr:
        nw, nh = int(sh * tr), sh
    else:
        nw, nh = sw, int(sw / tr)
    nw = int(nw / zoom)
    nh = int(nh / zoom)
    x0 = int((sw - nw) * x_bias)
    y0 = int((sh - nh) * top_bias)
    img = img.crop((x0, y0, x0 + nw, y0 + nh))
    return img.resize((w, h), Image.LANCZOS)


def apply_bottom_gradient(img: Image.Image, gradient_start_y: int = 555) -> Image.Image:
    """하단 그라디언트 오버레이 — 바레 완성본 실측 기반."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(H):
        if y < gradient_start_y:
            alpha = 0
        else:
            t = (y - gradient_start_y) / (H - gradient_start_y)
            alpha = int(255 * (t ** 1.2))
            alpha = min(230, alpha)
        draw.line([(0, y), (W, y)], fill=(*BLACK_BG, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def paste_logo(canvas: Image.Image, logo_w: int = 130) -> Image.Image:
    """공식 로고 PNG 좌상단 합성 — 박스 없이 직접 (바레 완성본 기준)."""
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
    """우상단 둥근 칩 — 베이지 fill, 흰색 텍스트."""
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
    """카운터 — 배경 없이 텍스트만, 칩 아래 우측 정렬 (바레 완성본 기준)."""
    text = f"{current:02d} / {total:02d}"
    bb = font.getbbox(text)
    tw = bb[2] - bb[0]
    chip_right = chip_x + 240
    tx = chip_right - tw
    ty = chip_y + chip_h + 8
    draw.text((tx, ty), text, font=font, fill=WHITE,
              stroke_width=2, stroke_fill=BLACK_BG)


# ---------------------------------------------------------------------------
# 표지 (ig_01) — 바레 완성본 ig_01 1:1 정합 구조
# ---------------------------------------------------------------------------
def compose_cover(
    photo_path: Path,
    title_eng: str,          # "BALLET"
    title_kor: str,          # "발레"
    date_location: str,      # "2026.05 OPEN  ·  한남동 웰니스 스튜디오"
    output_path: Path,
    cover_x_bias: float = 0.5,
    cover_zoom: float = 1.0,
) -> None:
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    PHOTO_H = 700  # 바레 완성본 실측 경계 (y=701)
    photo = top_crop_fill(photo_path, W, PHOTO_H, x_bias=cover_x_bias, zoom=cover_zoom)
    photo = to_duotone(photo)
    canvas.paste(photo, (0, 0))

    # 분리선 (바레 완성본 실측: y=701~702, x=50~1030)
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=(171, 161, 151))

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    # 우상단 칩
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 검정 정보영역 텍스트 — 바레 완성본 y좌표 1:1
    kor_font = load_font("semibold", 38)
    draw.text((W // 2, 789), title_kor, font=kor_font, fill=BEIGE, anchor="mm")

    eng_font = load_font("bold", 88)
    draw.text((W // 2, 859), title_eng, font=eng_font, fill=WHITE, anchor="mm")

    sub_line_y = 920
    draw.rectangle(
        [(W // 2 - 30, sub_line_y), (W // 2 + 30, sub_line_y + 2)],
        fill=BEIGE,
    )

    date_font = load_font("medium", 26)
    draw.text((W // 2, 962), date_location, font=date_font, fill=GRAY, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 스토리 슬라이드 — 바레 완성본 ig_02~04 기준
# ---------------------------------------------------------------------------
def compose_story(
    photo_path: Path,
    meta_line: str,
    title_kor: str,
    sub_text: str,
    footer_text: str,
    current: int,
    total: int,
    output_path: Path,
    chip_label: str = "WELLPERION",
    full_dark: bool = False,
) -> None:
    if full_dark:
        # 다크 히어로(바레 ig_04 동등) — 듀오톤/그라디언트 대신 원본 어두운 톤 유지
        canvas = center_crop_fill(photo_path, W, H)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.95)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=600)
    else:
        canvas = center_crop_fill(photo_path, W, H)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=555)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, chip_label, chip_font, chip_x, chip_y, chip_w, chip_h)

    counter_font = load_font("medium", 28)
    draw_counter(draw, current, total, counter_font, chip_x, chip_y, chip_h)

    meta_font = load_font("medium", 26)
    draw.text((40, 795), meta_line, font=meta_font, fill=GRAY)

    title_font = load_font("bold", 64)
    draw.text((40, 860), title_kor, font=title_font, fill=WHITE)

    sub_font = load_font("semibold", 30)
    sub_lines = sub_text.split("\n")
    if len(sub_lines) == 1:
        draw.text((40, 958), sub_text, font=sub_font, fill=BEIGE)
    else:
        # CTA 한/영 2줄 — 좌표·폰트·색은 바레 동일, 시작만 살짝 올려 풋터와 간격 확보
        sy = 936
        for sl in sub_lines:
            draw.text((40, sy), sl, font=sub_font, fill=BEIGE)
            sy += 40

    footer_font = load_font("medium", 26)
    draw.text((40, 1026), footer_text, font=footer_font, fill=BEIGE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{current:02d}/{total:02d}] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# GUIDE 카드 — 원본 자체가 완성본, 합성 없이 복사 (바레 완성본 동일)
# ---------------------------------------------------------------------------
def compose_guide_card(output_path: Path) -> None:
    guide_src = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card.jpg"
    if not guide_src.exists():
        raise FileNotFoundError(f"GUIDE 카드 없음: {guide_src}")
    img = Image.open(guide_src).convert("RGB")
    if img.size != (W, H):
        img = center_crop_fill(guide_src, W, H)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [가이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 발레 런칭 슬라이드 세트 — 바레 구성 그대로
#
# ig_01  표지        BALLET / 발레          카운터 없음
# ig_02  그룹 수업컷  02/05
# ig_03  지도 수업컷  03/05
# ig_04  다크 히어로  04/05
# ig_05  GUIDE 카드   카운터 없음 (마지막)
# ---------------------------------------------------------------------------
# GM이 직접 고른 새 사진 6장 (output(인스타그램)/_src_gm) — 2026-06-05
SRC = PROJECT_ROOT / "instagram" / "260520_발레_런칭" / "output(인스타그램)" / "_src_gm"

COVER = SRC / "ig_01.jpg"   # 발레복 전신(표지)
P02   = SRC / "ig_02.png"   # 1:1 자세 교정
P03   = SRC / "ig_03.png"   # 바 그룹 4인(정원)
P04   = SRC / "ig_04.png"   # 팔 든 그룹(자세)
P05   = SRC / "ig_05.png"   # 단독 우아한 포즈
P06   = SRC / "ig_06.png"   # 파우더 점프 흑백(CTA·드라마틱)


def main():
    out_master = PROJECT_ROOT / "instagram" / "260520_발레_런칭" / "output"
    out_ig = PROJECT_ROOT / "instagram" / "260520_발레_런칭" / "output(인스타그램)"
    out_master.mkdir(parents=True, exist_ok=True)
    out_ig.mkdir(parents=True, exist_ok=True)

    for p in [COVER, P02, P03, P04, P05, P06]:
        if not p.exists():
            print(f"[ERROR] 소스 없음: {p}")
            sys.exit(1)

    TOTAL = 7  # 표지 + 본문5 + 가이드

    print("=== 발레 런칭 슬라이드 합성 (바레 벤치마킹) ===")
    print(f"출력(인스타): {out_ig}")

    # ig_01 — 표지
    compose_cover(
        photo_path=COVER,
        title_eng="BALLET",
        title_kor="발레",
        date_location="2026.05 OPEN  ·  한남동 웰니스 스튜디오",
        output_path=out_ig / "ig_01.jpg",
        cover_x_bias=0.60,   # 인물이 원본 우측 → 가로 크롭으로 중앙 정렬
        cover_zoom=1.28,     # 인물 확대(빈 배경 축소)
    )

    # ig_02~06 — 본문 (큐레이션 정본 텍스트 / CTA는 마지막 본문)
    story_data = [
        (P02, "BALLET 2026.05  ·  2026.05 OPEN", "전문가의 1:1 교정", "이수지 BALLET INSTRUCTOR", False),
        (P03, "BALLET 2026.05  ·  2026.05 OPEN", "최대 8인 프라이빗", "매주 금요일 오전 10시 / 11시", False),
        (P04, "BALLET 2026.05  ·  2026.05 OPEN", "클래식 발레의 정수", "균형 · 자세 · 우아한 움직임", False),
        (P05, "BALLET 2026.05  ·  2026.05 OPEN", "함께 완성하는 자세", "한남동 웰니스 스튜디오", False),
        (P06, "BALLET 2026.05  ·  2026.05 OPEN", "특별한 움직임의 여정", "문의 wellperion.com/ko/inquiry", True),
    ]
    for idx, (photo, meta, title_kor, sub, full_dark) in enumerate(story_data, start=2):
        compose_story(
            photo_path=photo,
            meta_line=meta,
            title_kor=title_kor,
            sub_text=sub,
            footer_text="WELLPERION  ·  BALLET",
            current=idx,
            total=TOTAL,
            output_path=out_ig / f"ig_{idx:02d}.jpg",
            full_dark=full_dark,
        )

    # ig_07 — GUIDE 카드 (마지막)
    compose_guide_card(output_path=out_ig / "ig_07.jpg")

    # 마스터(output) 폴더에도 동일 배치
    print(f"\n출력(마스터): {out_master}")
    for f in sorted(out_ig.glob("ig_*.jpg")):
        shutil.copy2(f, out_master / f.name)
        print(f"  [마스터] {f.name}")

    print("\n=== 합성 완료 ===")
    for f in sorted(out_ig.iterdir()):
        if f.is_file():
            print(f"  {f.name}  {f.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
