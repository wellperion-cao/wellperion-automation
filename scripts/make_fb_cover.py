"""페이스북 페이지 커버 이미지를 브랜드 정본 값으로 합성한다 (배1118).

왜 있나
-------
페이스북 커버가 옛 정체성("Premium Lifestyle Club" · "프라이빗 스파 & 피트니스")을
그대로 달고 있었다. 텍스트 필드(소개·카테고리·주소)는 배999에서 정정했지만
그림 안의 글자는 남아 있었다. 문구를 다시 바꿀 때 손으로 그리지 않도록 합성을 코드로 둔다.

값의 출처
---------
- 문구 = ssot/canon_values.json (slogan_kr · slogan_en · official_one_liner_kr 계열)
- 색·폰트·로고 = scripts/brand_constants.py (원천 ssot/brand.json)
- 사진 = 실제 시설 사진만 쓴다 (브랜드 규칙 · 가상 렌더 금지)

쓰는 법
-------
    C:/Python314/python.exe scripts/make_fb_cover.py
    C:/Python314/python.exe scripts/make_fb_cover.py --photo 22-squash.jpg --out /tmp/x.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

import brand_constants as B
from slide_compositor import load_and_fit, load_font

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHOTO_DIR = PROJECT_ROOT / "3. 웰페리온 가이드" / "home" / "assets" / "profile"
CANON = PROJECT_ROOT / "ssot" / "canon_values.json"
DEFAULT_PHOTO = "20-pool.jpg"
DEFAULT_OUT = PROJECT_ROOT / "instagram" / "_assets" / "logo" / "fb_cover_1640.png"

# 페이스북 페이지 커버 권장 크기. 데스크톱·모바일이 각자 다르게 잘라 가므로
# 글자는 전부 가운데 안전대(가로 60% · 세로 55%) 안에만 둔다.
COVER_W, COVER_H = 1640, 856


def canon(key: str, fallback: str) -> str:
    """공식값 한 칸을 읽는다. 파일 구조가 바뀌어도 그림 합성이 멈추지는 않게 폴백을 둔다."""
    try:
        data = json.loads(CANON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    node = data.get(key) if isinstance(data, dict) else None
    if isinstance(node, dict):
        for field in ("value", "값", "text"):
            if isinstance(node.get(field), str):
                return node[field]
    return node if isinstance(node, str) else fallback


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy_center_y: tuple[int, int],
    text: str,
    font,
    fill,
    tracking: int,
) -> None:
    """자간을 준 한 줄을 가로 가운데에 그린다 (Pillow 는 자간 인자가 없다)."""
    center_x, y = xy_center_y
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * max(len(text) - 1, 0)
    x = center_x - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking


def build(photo: str, out: Path) -> Path:
    base = load_and_fit(PHOTO_DIR / photo, COVER_W, COVER_H).convert("RGBA")

    # 사진 위에 글자를 얹으므로 어둡게 깐다. 아래쪽을 더 눌러 로고가 앉을 자리를 만든다.
    scrim = Image.new("RGBA", (COVER_W, COVER_H), (*B.BLACK_BG, 120))
    base = Image.alpha_composite(base, scrim)
    gradient = Image.new("RGBA", (COVER_W, COVER_H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(gradient)
    for y in range(COVER_H):
        t = y / (COVER_H - 1)
        gdraw.line([(0, y), (COVER_W, y)], fill=(*B.BLACK_BG, int(125 * t * t)))
    base = Image.alpha_composite(base, gradient)

    draw = ImageDraw.Draw(base)
    cx = COVER_W // 2

    slogan_en = canon("slogan_en", "A Day, Well Completed.")
    slogan_kr = canon("slogan_kr", "하루의 완성, 웰페리온")
    positioning = canon("positioning_kr", "정원제 스포츠클럽")
    scale = canon("company_scale", "3,000평")
    subline = f"서울 한남동 약 {scale} {positioning}"

    f_en = load_font("medium", 34)
    f_kr = load_font("semibold", 82)
    f_sub = load_font("medium", 30)

    draw_tracked(draw, (cx, 250), slogan_en.upper(), f_en, (*B.BEIGE, 255), 6)

    kr_w = draw.textlength(slogan_kr, font=f_kr)
    draw.text((cx - kr_w / 2, 305), slogan_kr, font=f_kr, fill=(*B.WHITE, 255))

    draw.line([(cx - 90, 430), (cx + 90, 430)], fill=(*B.BEIGE, 210), width=2)

    draw_tracked(draw, (cx, 466), subline, f_sub, (255, 255, 255, 225), 2)

    logo = Image.open(B.LOGO_WHITE_ALPHA).convert("RGBA")
    logo_w = 240
    logo = logo.resize((logo_w, int(logo.height * logo_w / logo.width)), Image.LANCZOS)
    # 페이스북은 커버를 세로로 약 78%만 보여 준다(실측 2026-09-09 · 데스크톱 1440px).
    # 아래 여백을 넉넉히 둬야 로고가 잘리지 않는다.
    base.paste(logo, (cx - logo_w // 2, COVER_H - logo.height - 135), mask=logo)

    out.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out, "PNG")
    return out


def banned_words_in(text: str) -> list[str]:
    """브랜드 금지어. 커버 문구가 다시 옛 정체성으로 돌아가지 않게 여기서 막는다."""
    banned = ["프라이빗", "피트니스", "FITNESS", "Premium Lifestyle", "레슨", "현대하이페리온"]
    return [w for w in banned if w.lower() in text.lower()]


def demo() -> None:
    """자가 점검 — 합성이 실제로 나오고, 문구에 금지어가 없는지 본다."""
    text = " ".join(
        [
            canon("slogan_en", "A Day, Well Completed."),
            canon("slogan_kr", "하루의 완성, 웰페리온"),
            canon("positioning_kr", "정원제 스포츠클럽"),
        ]
    )
    assert not banned_words_in(text), f"커버 문구에 금지어: {banned_words_in(text)}"
    assert banned_words_in("프라이빗 스파 & 피트니스") == ["프라이빗", "피트니스"], "금지어 검출이 안 된다"
    img = Image.open(build(DEFAULT_PHOTO, DEFAULT_OUT))
    assert img.size == (COVER_W, COVER_H), img.size
    print("self-check OK", DEFAULT_OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", default=DEFAULT_PHOTO, help=f"{PHOTO_DIR} 안의 파일명")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        demo()
    else:
        print(build(a.photo, a.out))
