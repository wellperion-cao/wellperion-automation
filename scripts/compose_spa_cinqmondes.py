"""생크몽드 스파 인스타그램 슬라이드 생성 (2026-06-11 GM 결재).

compose_barre 엔진 함수 재사용 + spa 프리셋 적용.
산출: instagram/260611_생크몽드스파/ (7장 사진 슬라이드 + 가이드카드 = 8p)

톤: 배경 크림 아이보리 #FAF7F2 / 포인트 와인 버건디 #8B1A2F / 보조 브러시드 골드 #C9A96E
서체: Light·Regular 위주, 헤드라인만 Medium (Pretendard)
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (
    PROJECT_ROOT,
    LOGO_WHITE_ALPHA,
    FONT_BOLD, FONT_SEMIBOLD, FONT_MEDIUM,
    BRAND_PRESETS,
)
from compose_barre import (
    center_crop_fill,
    compose_guide_card,
)

W, H = 1080, 1080

# spa 프리셋 색상
SPA = BRAND_PRESETS["spa"]
BG_IVORY   = SPA["background"]    # (250, 247, 242) #FAF7F2
BURGUNDY   = SPA["accent"]        # (139, 26, 47)   #8B1A2F
GOLD       = SPA["primary"]       # (201, 169, 110) #C9A96E
TEXT_DARK  = SPA["text"]          # (34, 31, 32)    #221F20
WHITE      = (255, 255, 255)


def _load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = {"bold": FONT_BOLD, "semibold": FONT_SEMIBOLD, "medium": FONT_MEDIUM}.get(weight, FONT_MEDIUM)
    if not path.exists():
        raise FileNotFoundError(f"Font not found: {path}")
    return ImageFont.truetype(str(path), size)


def _paste_logo_dark(canvas: Image.Image, logo_w: int = 130) -> Image.Image:
    """밝은 배경(표지) 위 로고: 버건디 tint 또는 다크 버전 사용.
    white_alpha 로고를 버건디 컬러로 tint해 아이보리 배경에서 가독성 확보."""
    logo = Image.open(LOGO_WHITE_ALPHA).convert("RGBA")
    orig_w, orig_h = logo.size
    logo_h = int(orig_h * logo_w / orig_w)
    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
    # 흰색 픽셀을 버건디로 tint
    r, g, b, a = logo.split()
    br, bg_, bb = BURGUNDY
    colored = Image.merge("RGBA", (
        r.point(lambda p: int(p * br / 255)),
        g.point(lambda p: int(p * bg_ / 255)),
        b.point(lambda p: int(p * bb / 255)),
        a,
    ))
    base = canvas.convert("RGBA")
    base.paste(colored, (40, 36), mask=a)
    return base.convert("RGB")


def _paste_logo_white(canvas: Image.Image, logo_w: int = 130) -> Image.Image:
    """어두운/사진 배경 위 흰색 로고."""
    logo = Image.open(LOGO_WHITE_ALPHA).convert("RGBA")
    orig_w, orig_h = logo.size
    logo_h = int(orig_h * logo_w / orig_w)
    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
    base = canvas.convert("RGBA")
    base.paste(logo, (40, 36), mask=logo)
    return base.convert("RGB")


def _apply_spa_gradient(img: Image.Image, start_y: int = 560) -> Image.Image:
    """하단 그라디언트 — 투명→버건디 다크(#1a0008 계열) 오버레이."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    dark = (26, 0, 12)  # 버건디 초다크
    for y in range(H):
        if y < start_y:
            alpha = 0
        else:
            t = (y - start_y) / (H - start_y)
            alpha = int(220 * (t ** 1.15))
            alpha = min(215, alpha)
        draw.line([(0, y), (W, y)], fill=(*dark, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _draw_chip_spa(draw: ImageDraw.ImageDraw, label: str,
                   font: ImageFont.FreeTypeFont,
                   chip_x: int, chip_y: int, chip_w: int, chip_h: int) -> None:
    """우상단 칩 — 버건디 fill, 골드 텍스트."""
    draw.rounded_rectangle(
        [(chip_x, chip_y), (chip_x + chip_w, chip_y + chip_h)],
        radius=chip_h // 2,
        fill=BURGUNDY,
    )
    bb = font.getbbox(label)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    tx = chip_x + (chip_w - tw) // 2
    ty = chip_y + (chip_h - th) // 2 - 1
    draw.text((tx, ty), label, font=font, fill=GOLD)


def compose_spa_cover(
    photo_path: Path,
    output_path: Path,
) -> None:
    """1p 표지 — 아이보리 배경 + 사진(상단 58%) + 버건디/골드 텍스트 영역.
    구조: 전체 아이보리 캔버스, 사진 상단 58%(y=0~630), 분리 골드선, 하단 정보영역."""
    canvas = Image.new("RGB", (W, H), BG_IVORY)

    # 사진 영역 (상단 58% ≈ 630px) — 컬러 원본 유지(밝기 살짝 보정)
    PHOTO_H = 630
    photo = center_crop_fill(photo_path, W, PHOTO_H)
    photo = ImageEnhance.Brightness(photo).enhance(0.92)
    canvas.paste(photo, (0, 0))

    # 골드 분리선 (y=631~633)
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(0, 631), (W, 633)], fill=GOLD)

    # 로고 (사진 위, 버건디 tint)
    canvas = _paste_logo_dark(canvas, logo_w=120)
    draw = ImageDraw.Draw(canvas)

    # 우상단 칩 — 버건디
    chip_font = _load_font("semibold", 26)
    chip_w, chip_h = 240, 50
    chip_x = W - 40 - chip_w
    chip_y = 38
    _draw_chip_spa(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 하단 아이보리 영역 텍스트
    # 서브라인 — 버건디 골드 작은 레터
    sub_font = _load_font("medium", 28)
    draw.text((W // 2, 680), "웰페리온 × Cinq Mondes", font=sub_font, fill=GOLD, anchor="mm")

    # 골드 얇은 장식선
    draw.rectangle([(W // 2 - 60, 712), (W // 2 + 60, 714)], fill=GOLD)

    # 메인 카피 — 버건디 Medium (헤드라인)
    main_font = _load_font("medium", 52)
    line1 = "땀을 흘린 자리에서,"
    line2 = "회복도 같은 곳에서."
    draw.text((W // 2, 770), line1, font=main_font, fill=BURGUNDY, anchor="mm")
    draw.text((W // 2, 836), line2, font=main_font, fill=BURGUNDY, anchor="mm")

    # 골드 얇은 장식선
    draw.rectangle([(W // 2 - 40, 878), (W // 2 + 40, 880)], fill=GOLD)

    # 태그라인 — 텍스트 다크
    tag_font = _load_font("medium", 24)
    draw.text((W // 2, 920), "운동도 스파도 웰페리온 한 곳에서", font=tag_font, fill=TEXT_DARK, anchor="mm")

    # CTA 하단
    cta_font = _load_font("medium", 22)
    draw.text((W // 2, 970), "문의: wellperion.com/ko/inquiry", font=cta_font, fill=GOLD, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def compose_spa_story(
    photo_path: Path,
    title_kor: str,
    sub_text: str,
    current: int,
    total: int,
    output_path: Path,
) -> None:
    """본문 슬라이드 — 풀 사진 + 하단 버건디 그라디언트 + 텍스트."""
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.88)
    canvas = _apply_spa_gradient(canvas, start_y=540)

    # 로고 (흰색 — 사진 위)
    canvas = _paste_logo_white(canvas, logo_w=120)
    draw = ImageDraw.Draw(canvas)

    # 우상단 칩
    chip_font = _load_font("semibold", 26)
    chip_w, chip_h = 240, 50
    chip_x = W - 40 - chip_w
    chip_y = 38
    _draw_chip_spa(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 카운터
    counter_font = _load_font("medium", 26)
    counter_text = f"{current:02d} / {total:02d}"
    bb = counter_font.getbbox(counter_text)
    tw = bb[2] - bb[0]
    chip_right = chip_x + chip_w
    draw.text((chip_right - tw, chip_y + chip_h + 8), counter_text,
              font=counter_font, fill=GOLD, stroke_width=1, stroke_fill=(26, 0, 12))

    # 골드 포인트 라인 (좌측 여백)
    draw.rectangle([(40, 840), (44, 910)], fill=GOLD)

    # 한글 대제목 (흰색 Medium — 헤드라인)
    title_font = _load_font("medium", 56)
    draw.text((60, 845), title_kor, font=title_font, fill=WHITE)

    # 서브텍스트 (골드)
    sub_font = _load_font("medium", 28)
    draw.text((60, 928), sub_text, font=sub_font, fill=GOLD)

    # 풋터
    footer_font = _load_font("medium", 24)
    draw.text((60, 1020), "WELLPERION  ·  Cinq Mondes", font=footer_font, fill=GOLD)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{current:02d}/{total:02d}] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def main():
    src = PROJECT_ROOT / "instagram" / "Image" / "생크몽드_소개(원본 이미지)"
    out_dir = PROJECT_ROOT / "instagram" / "260611_생크몽드스파"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 원본 7장 (GM 확정 순서)
    photos = [
        src / "3. DSC09483.jpg",    # 표지: 복도 + CINQ MONDES PARIS 사이니지
        src / "1-2. DSC09443.jpg",  # 2p: 리셉션 풀샷
        src / "1-1. DSC09492.jpg",  # 3p: 로고 라운지
        src / "4-1. DSC09470.jpg",  # 4p: 요가·명상 스튜디오
        src / "2-1. DSC09461.jpg",  # 5p: 페디큐어·풋배스 룸
        src / "5-1. DSC09535.jpg",  # 6p: 트리트먼트 시그니처 룸
        src / "7-1. DSC09439.jpg",  # 7p: 제품 풀 라인업 벽
    ]

    for p in photos:
        if not p.exists():
            print(f"[ERROR] 원본 없음: {p}")
            sys.exit(1)

    TOTAL = 8  # 7장 슬라이드 + 가이드카드

    print("=== 생크몽드 스파 슬라이드 합성 ===")
    print(f"출력: {out_dir}")

    # ig_01 — 표지
    compose_spa_cover(
        photo_path=photos[0],
        output_path=out_dir / "ig_01.jpg",
    )

    # ig_02~07 — 본문 슬라이드
    story_data = [
        (photos[1], "스파 전용 리셉션",          "클럽 안에 또 다른 세계가 있습니다"),
        (photos[2], "Cinq Mondes Paris",         "파리에서 온 프리미엄 스파 브랜드"),
        (photos[3], "운동 후, 같은 공간에서 바로",  "요가·명상 스튜디오"),
        (photos[4], "발끝부터 시작하는 회복",       "페디큐어 & 풋 배스 룸"),
        (photos[5], "프라이빗 트리트먼트 룸",       "온전히 나만을 위한 시간"),
        (photos[6], "Cinq Mondes 정식 파트너",    "전 라인업을 웰페리온에서"),
    ]

    for idx, (photo, title, sub) in enumerate(story_data, start=2):
        compose_spa_story(
            photo_path=photo,
            title_kor=title,
            sub_text=sub,
            current=idx,
            total=TOTAL,
            output_path=out_dir / f"ig_{idx:02d}.jpg",
        )

    # ig_08 — 가이드카드
    compose_guide_card(output_path=out_dir / "ig_08.jpg")

    print()
    print("=== 합성 완료 ===")
    total_files = list(sorted(out_dir.glob("ig_*.jpg")))
    for f in total_files:
        print(f"  {f.name}  {f.stat().st_size // 1024}KB")
    print(f"총 {len(total_files)}장 → {out_dir}")
    return out_dir, total_files


if __name__ == "__main__":
    main()
