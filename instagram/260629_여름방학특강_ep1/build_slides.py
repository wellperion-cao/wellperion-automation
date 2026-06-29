"""2026 여름 방학특강 Ep1 — 슬라이드 빌드 스크립트
compose_barre 엔진(사진형 정본) 재사용.
7장 구성 / 원본 사진 9장 전부 배치.
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance

SCRIPTS = Path(r"C:\Users\jjky0\welperion-automation\scripts")
sys.path.insert(0, str(SCRIPTS))

from compose_barre import (
    center_crop_fill,
    apply_bottom_gradient,
    paste_logo,
    draw_chip,
    draw_counter,
    to_duotone,
    load_font,
    W, H,
)
from brand_constants import WHITE, BEIGE, GRAY, BLACK_BG

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
SRC  = ROOT / "instagram" / "Image" / "방학특강(원본 이미지)"
OUT  = ROOT / "instagram" / "260629_여름방학특강_ep1" / "output(인스타그램)"
OUT.mkdir(parents=True, exist_ok=True)

TOTAL      = 7
CHIP_LABEL = "WELLPERION"
FOOTER_TXT = "WELLPERION  ·  스포츠클럽"


# ── 공통 헬퍼 ────────────────────────────────────────────────────
def _attach_brand(canvas: Image.Image, current: int) -> ImageDraw.ImageDraw:
    """로고 + 칩 + 카운터 부착 후 draw 반환."""
    canvas_ref = paste_logo(canvas, logo_w=130)
    # paste_logo 는 canvas 를 RGB 로 변환해 새 이미지 반환하지 않음
    # — 실제로 convert+paste 후 반환값이 있으므로 덮어씌운다
    canvas.__dict__.update(canvas_ref.__dict__)
    canvas._size    = canvas_ref._size
    canvas.im       = canvas_ref.im
    canvas.mode     = canvas_ref.mode
    draw = ImageDraw.Draw(canvas)
    cw, ch = 240, 52
    cx = W - 40 - cw
    cy = 38
    draw_chip(draw, CHIP_LABEL, load_font("bold", 28), cx, cy, cw, ch)
    if current > 0:
        draw_counter(draw, current, TOTAL, load_font("medium", 28), cx, cy, ch)
    return draw


def _brand_overlay(canvas: Image.Image, current: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """로고+칩+카운터 합성 후 (canvas, draw) 반환."""
    canvas = paste_logo(canvas, logo_w=130)
    draw   = ImageDraw.Draw(canvas)
    cw, ch = 240, 52
    cx = W - 40 - cw
    cy = 38
    draw_chip(draw, CHIP_LABEL, load_font("bold", 28), cx, cy, cw, ch)
    if current > 0:
        draw_counter(draw, current, TOTAL, load_font("medium", 28), cx, cy, ch)
    return canvas, draw


def _save(canvas: Image.Image, num: int) -> Path:
    p = OUT / f"post_{num}.jpg"
    canvas.convert("RGB").save(p, "JPEG", quality=93, optimize=True)
    print(f"  [{num:02d}/{TOTAL:02d}] post_{num}.jpg ({p.stat().st_size // 1024} KB)")
    return p


# ── post_1: 표지 ─────────────────────────────────────────────────
def make_cover() -> Path:
    canvas = Image.new("RGB", (W, H), BLACK_BG)
    PHOTO_H = 700
    photo = center_crop_fill(SRC / "3. 수영장.jpg", W, PHOTO_H)
    photo = to_duotone(photo, normalize=True)
    canvas.paste(photo, (0, 0))

    d0 = ImageDraw.Draw(canvas)
    d0.rectangle([(50, 701), (1030, 702)], fill=(171, 161, 151))  # 분리선

    canvas, draw = _brand_overlay(canvas, current=0)  # 표지=카운터 없음

    # 메인 타이틀 (white bold)
    draw.text((W // 2, 790),
              "2026 여름 방학특강",
              font=load_font("bold", 66), fill=WHITE, anchor="mm")

    # 베이지 얇은 구분선
    draw.rectangle([(W // 2 - 30, 841), (W // 2 + 30, 843)], fill=BEIGE)

    # 서브타이틀 (beige)
    draw.text((W // 2, 885),
              "아이의 여름을 채우는 네 가지 운동",
              font=load_font("semibold", 30), fill=BEIGE, anchor="mm")

    # 날짜·대상 (gray)
    draw.text((W // 2, 952),
              "6.22 ~ 8.14  ·  유소년",
              font=load_font("medium", 26), fill=GRAY, anchor="mm")

    return _save(canvas, 1)


# ── post_N: 단일 사진 스토리 슬라이드 ────────────────────────────
def make_story(photo_name: str, meta: str, title: str, sub: str, num: int) -> Path:
    canvas = center_crop_fill(SRC / photo_name, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.88)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=555)
    canvas, draw = _brand_overlay(canvas, current=num)

    draw.text((40, 795), meta,  font=load_font("medium", 26), fill=GRAY)
    draw.text((40, 860), title, font=load_font("bold",   60), fill=WHITE)
    draw.text((40, 952), sub,   font=load_font("semibold", 28), fill=BEIGE)
    draw.text((40, 1026), FOOTER_TXT, font=load_font("medium", 26), fill=BEIGE)

    return _save(canvas, num)


# ── post_N: 2분할 사진 슬라이드 ──────────────────────────────────
def make_dual(photo_a: str, photo_b: str, title: str, num: int) -> Path:
    pw = W // 2  # 540
    left  = center_crop_fill(SRC / photo_a, pw,      H)
    right = center_crop_fill(SRC / photo_b, W - pw,  H)
    left  = ImageEnhance.Brightness(left).enhance(0.85)
    right = ImageEnhance.Brightness(right).enhance(0.85)

    canvas = Image.new("RGB", (W, H), BLACK_BG)
    canvas.paste(left,  (0,   0))
    canvas.paste(right, (pw,  0))

    canvas = apply_bottom_gradient(canvas, gradient_start_y=570)
    canvas, draw = _brand_overlay(canvas, current=num)

    draw.text((40, 855), title,      font=load_font("bold",   56), fill=WHITE)
    draw.text((40, 930), FOOTER_TXT, font=load_font("medium", 26), fill=BEIGE)

    return _save(canvas, num)


# ── post_N: 3분할 사진 슬라이드 ──────────────────────────────────
def make_triple(photo_a: str, photo_b: str, photo_c: str, title: str, num: int) -> Path:
    pw = W // 3  # 360
    panels = [
        center_crop_fill(SRC / photo_a, pw,          H),
        center_crop_fill(SRC / photo_b, pw,          H),
        center_crop_fill(SRC / photo_c, W - pw * 2,  H),
    ]
    canvas = Image.new("RGB", (W, H), BLACK_BG)
    offsets = [0, pw, pw * 2]
    for panel, ox in zip(panels, offsets):
        panel = ImageEnhance.Brightness(panel).enhance(0.85)
        canvas.paste(panel, (ox, 0))

    canvas = apply_bottom_gradient(canvas, gradient_start_y=570)
    canvas, draw = _brand_overlay(canvas, current=num)

    draw.text((40, 855), title,      font=load_font("bold",   56), fill=WHITE)
    draw.text((40, 930), FOOTER_TXT, font=load_font("medium", 26), fill=BEIGE)

    return _save(canvas, num)


# ── 몽타주 (검수 미리보기) ────────────────────────────────────────
def make_montage() -> Path:
    slides = [OUT / f"post_{i}.jpg" for i in range(1, TOTAL + 1)]
    # 4+3 배치: 첫 줄 4장, 둘째 줄 3장 (가운데 정렬)
    COLS = 4
    TW   = W // COLS    # 270
    TH   = H // COLS    # 270
    MONT_W = TW * COLS  # 1080
    MONT_H = TH * 2     # 540
    mont = Image.new("RGB", (MONT_W, MONT_H), (20, 20, 20))

    for i, p in enumerate(slides):
        if not p.exists():
            continue
        thumb = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
        row, col = divmod(i, COLS)
        # 둘째 줄(row=1) 3장 가운데 정렬: x_offset = (1080 - 3*270)//2 = 135
        if row == 1:
            x_base = (MONT_W - 3 * TW) // 2
            ox = x_base + col * TW
        else:
            ox = col * TW
        mont.paste(thumb, (ox, row * TH))

    out = OUT / "_검수_미리보기_7장.png"
    mont.save(out, "PNG", optimize=True)
    print(f"  [몽타주] {out.name} ({out.stat().st_size // 1024} KB)")
    return out


# ── 메인 ────────────────────────────────────────────────────────
def main() -> Path:
    print("=== 2026 여름 방학특강 Ep1 슬라이드 빌드 ===")
    print(f"출력 폴더: {OUT}")

    # 사진 존재 확인
    required = [
        "3. 수영장.jpg", "방학 수영 레슨.png",
        "체조룸(스프링매트 ).png", "방학 유소년 체조 강습.png", "트램폴린장.png",
        "스쿼시 강습.jpg", "스쿼시장.png",
        "골프 강습.jpg", "골프룸.jpg",
    ]
    missing = [f for f in required if not (SRC / f).exists()]
    if missing:
        print(f"[ERROR] 소스 이미지 누락: {missing}")
        raise SystemExit(1)
    print(f"  원본 9장 확인 완료")

    make_cover()                                                          # post_1: 표지 (수영장)

    make_story(                                                           # post_2: 개요 (골프룸)
        "골프룸.jpg",
        "수영 · 체조 · 스쿼시 · 골프",
        "한 곳에서, 1:6 소수정예로",
        "대상: 2019년 이전 출생 유소년",
        num=2,
    )

    make_dual(                                                            # post_3: 수영
        "3. 수영장.jpg", "방학 수영 레슨.png",
        "수영 — 물과 친해지는 여름", num=3,
    )

    make_triple(                                                          # post_4: 체조
        "체조룸(스프링매트 ).png",
        "방학 유소년 체조 강습.png",
        "트램폴린장.png",
        "체조 — 균형과 자신감", num=4,
    )

    make_dual(                                                            # post_5: 스쿼시
        "스쿼시 강습.jpg", "스쿼시장.png",
        "스쿼시 — 순발력과 집중", num=5,
    )

    make_dual(                                                            # post_6: 골프
        "골프 강습.jpg", "골프룸.jpg",
        "골프 — 집중력과 매너", num=6,
    )

    make_story(                                                           # post_7: CTA
        "방학 수영 레슨.png",
        "1:6 소수정예  ·  횟수 자율조정  ·  주차 제공",
        "전문 지도진이 함께합니다",
        "문의·예약 → wellperion.com/ko/inquiry",
        num=7,
    )

    montage = make_montage()

    print("\n=== 빌드 완료 ===")
    total_kb = sum(f.stat().st_size for f in OUT.iterdir()) // 1024
    print(f"  출력 파일 {sum(1 for _ in OUT.iterdir())}개 / 총 {total_kb} KB")
    return montage


if __name__ == "__main__":
    main()
