"""생크몽드(Cinq Mondes) IG 3편(Episode) 슬라이드 생성 (2026-06-11 GM 결재 · 보강).

생크몽드 팀 공유용 — 외부 파트너 스파 소개를 3편 에피소드로 전량 제작.
엔진 = compose_spa_cinqmondes / compose_barre 헬퍼 재사용(새 엔진 손코딩 금지).

편당 디자인(2026-06-11 GM 피드백 반영 — 편당 6장):
  - ig_01 = 표지(커버) — 웰페리온 1p 정본 65/35 구조(compose_barre.compose_cover 구조 차용),
    SPA 톤(크림 정보영역·버건디 영문대제목·골드 분리선) 적용
  - ig_02~05 = 본문 사진 + 하단 그라디언트 + 카피
  - ig_06 = 임팩트 클로징 — 강한 타이포 + 공동 로고 + CTA
  - 전 슬라이드: 좌상단 = 웰페리온 로고 / 우상단 = 생크몽드 로고 (공동 브랜딩)
  - 페이지 카운트 없음
  - 톤: 크림 #FAF7F2 / 버건디 #8B1A2F / 골드 #C9A96E

산출: instagram/260611_생크몽드_ep1|ep2|ep3/ (각 6장, ig_01~06)
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (
    PROJECT_ROOT,
    LOGO_WHITE_ALPHA,
    FONT_BOLD, FONT_SEMIBOLD, FONT_MEDIUM,
    BRAND_PRESETS,
)
from compose_barre import center_crop_fill

W, H = 1080, 1080

SPA = BRAND_PRESETS["spa"]
BG_IVORY = SPA["background"]
BURGUNDY = SPA["accent"]
GOLD = SPA["primary"]
TEXT_DARK = SPA["text"]
WHITE = (255, 255, 255)

CINQ_LOGO = PROJECT_ROOT / "_assets" / "logo" / "cinq_mondes_logo_a.png"


def _load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = {"bold": FONT_BOLD, "semibold": FONT_SEMIBOLD, "medium": FONT_MEDIUM}.get(weight, FONT_MEDIUM)
    if not path.exists():
        raise FileNotFoundError(f"Font not found: {path}")
    return ImageFont.truetype(str(path), size)


def _tint_logo(logo: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """알파 로고를 단색(rgb)으로 tint. 알파 채널은 보존."""
    r, g, b, a = logo.split()
    tr, tg, tb = rgb
    return Image.merge("RGBA", (
        r.point(lambda p: tr),
        g.point(lambda p: tg),
        b.point(lambda p: tb),
        a,
    ))


def _spa_duotone(img: Image.Image) -> Image.Image:
    """표지 사진을 SPA 톤 듀오톤으로 변환 — dark=딥버건디 / light=크림.
    autocontrast로 톤 정규화(밝은 표지도 로고·텍스트 대비 확보, 편별 표지 일관)."""
    from PIL import ImageOps
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    dr, dg, db = (74, 14, 25)        # 딥 버건디(버건디 #8B1A2F 보다 어둡게 — 그림자)
    lr, lg, lb = BG_IVORY            # 크림 #FAF7F2
    r_lut = [int(dr + (lr - dr) * (i / 255)) for i in range(256)]
    g_lut = [int(dg + (lg - dg) * (i / 255)) for i in range(256)]
    b_lut = [int(db + (lb - db) * (i / 255)) for i in range(256)]
    return Image.merge("RGB", (gray.point(r_lut), gray.point(g_lut), gray.point(b_lut)))


def _paste_cinq_topright(canvas: Image.Image, logo_w: int = 150,
                         tint: tuple[int, int, int] | None = None) -> Image.Image:
    """생크몽드 로고를 우측 상단에 배치. tint 지정 시 단색 적용(사진 위 가독성)."""
    logo = Image.open(CINQ_LOGO).convert("RGBA")
    ow, oh = logo.size
    lh = int(oh * logo_w / ow)
    logo = logo.resize((logo_w, lh), Image.LANCZOS)
    if tint is not None:
        logo = _tint_logo(logo, tint)
    base = canvas.convert("RGBA")
    x = W - 40 - logo_w
    base.paste(logo, (x, 40), mask=logo.split()[3])
    return base.convert("RGB")


def _paste_wellperion_topleft(canvas: Image.Image, logo_w: int = 130,
                              tint: tuple[int, int, int] | None = None,
                              x: int = 40, y: int = 40) -> Image.Image:
    """웰페리온 로고를 좌측 상단에 배치(공동 브랜딩). tint 지정 시 단색 적용.
    (2026-06-11 GM 피드백: 좌하단→좌상단 이동 — 좌상단 웰페리온/우상단 생크몽드 공동 브랜딩.)"""
    logo = Image.open(LOGO_WHITE_ALPHA).convert("RGBA")
    ow, oh = logo.size
    lh = int(oh * logo_w / ow)
    logo = logo.resize((logo_w, lh), Image.LANCZOS)
    if tint is not None:
        logo = _tint_logo(logo, tint)
    base = canvas.convert("RGBA")
    base.paste(logo, (x, y), mask=logo.split()[3])
    return base.convert("RGB")


def _apply_gradient(img: Image.Image, start_y: int = 540) -> Image.Image:
    """하단 그라디언트 — 투명→버건디 초다크 오버레이(텍스트 가독성)."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    dark = (24, 0, 11)
    full_y = 770  # 카피·풋터 밴드는 이 지점부터 최대 농도 유지(밝은 사진서도 흰 카피 가독 보장)
    for y in range(H):
        if y <= start_y:
            alpha = 0
        else:
            t = min(1.0, (y - start_y) / (full_y - start_y))
            alpha = int(244 * (t ** 0.9))
        draw.line([(0, y), (W, y)], fill=(*dark, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _wrap_text(draw: ImageDraw.ImageDraw, text: str,
               font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """공백 기준 줄바꿈 — max_w 픽셀 폭을 넘지 않게 단어 단위 래핑."""
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        bb = draw.textbbox((0, 0), trial, font=font)
        if bb[2] - bb[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def compose_slide(photo_path: Path, caption: str, output_path: Path,
                  brightness: float = 0.88) -> None:
    """본문 슬라이드 — 풀 사진 + 하단 버건디 그라디언트 + 카피.
    페이지 카운트 없음 / 웰페리온 로고(좌상단) / 생크몽드 로고(우상단) 공동 브랜딩."""
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(brightness)
    canvas = _apply_gradient(canvas, start_y=480)

    # 상단 공동 브랜딩 — 좌상단 웰페리온 / 우상단 생크몽드 (둘 다 크림 tint, 사진 위 가독성)
    canvas = _paste_wellperion_topleft(canvas, logo_w=132, tint=(250, 247, 242), x=44, y=40)
    canvas = _paste_cinq_topright(canvas, logo_w=150, tint=(250, 247, 242))
    draw = ImageDraw.Draw(canvas)

    # 카피 블록 — 하단 그라디언트 밴드 위. 골드 좌측 바 + 흰색 bold + 외곽선(가독성 정본 유지).
    body_font = _load_font("bold", 45)
    line_h = 58
    lines = _wrap_text(draw, caption, body_font, max_w=W - 96 - 40)
    n = len(lines)
    last_line_top = 936            # 마지막 줄 상단 — 하단 여백 확보(풋터 제거로 하향)
    start_y = last_line_top - (n - 1) * line_h
    bar_top = start_y - 2
    bar_bottom = last_line_top + 46
    draw.rectangle([(60, bar_top), (64, bar_bottom)], fill=GOLD)
    for i, ln in enumerate(lines):
        draw.text((96, start_y + i * line_h), ln, font=body_font, fill=WHITE,
                  stroke_width=2, stroke_fill=(24, 0, 11))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{output_path.parent.name}/{output_path.name}] {output_path.stat().st_size // 1024}KB")


def compose_cover(photo_path: Path, title_eng: str, title_kor: str,
                  date_location: str, output_path: Path) -> None:
    """표지(ig_01) — 웰페리온 1p 정본 65/35 구조(compose_barre.compose_cover 차용),
    SPA 톤 적용. 사진 상단 65%(듀오톤 크림×버건디) + 골드 분리선 + 크림 정보영역.
    정보영역: 한글 부제(버건디) → 영문 대제목(버건디 bold) → 골드 짧은 선 → 날짜·장소(골드).
    상단 공동 브랜딩: 좌상단 웰페리온 / 우상단 생크몽드."""
    PHOTO_H = 700  # 1080 × 0.648 ≈ 700 (정본 65/35 경계)

    # 1) 캔버스 — 크림 아이보리 정보영역(하단 35%)
    canvas = Image.new("RGB", (W, H), BG_IVORY)

    # 2) 사진 영역(상단 65%) — 버건디×크림 듀오톤(SPA 톤, 표지 일관)
    photo = center_crop_fill(photo_path, W, PHOTO_H)
    photo = _spa_duotone(photo)
    canvas.paste(photo, (0, 0))

    # 3) 골드 분리선 (사진/정보영역 경계)
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, PHOTO_H), (1030, PHOTO_H + 2)], fill=GOLD)

    # 4) 상단 공동 브랜딩 — 좌상단 웰페리온(크림) / 우상단 생크몽드(크림)
    canvas = _paste_wellperion_topleft(canvas, logo_w=132, tint=(250, 247, 242), x=44, y=40)
    canvas = _paste_cinq_topright(canvas, logo_w=150, tint=(250, 247, 242))
    draw = ImageDraw.Draw(canvas)

    # 5) 정보영역 텍스트 (크림 배경 위 — 버건디/골드)
    # 한글 부제목 (버건디, 중앙)
    kor_font = _load_font("semibold", 38)
    draw.text((W // 2, 789), title_kor, font=kor_font, fill=BURGUNDY, anchor="mm")
    # 영문 대제목 (버건디 bold, 중앙)
    eng_font = _load_font("bold", 76)
    draw.text((W // 2, 859), title_eng, font=eng_font, fill=BURGUNDY, anchor="mm")
    # 골드 짧은 분리선 (중앙)
    draw.rectangle([(W // 2 - 30, 920), (W // 2 + 30, 922)], fill=GOLD)
    # 날짜·장소 (골드, 중앙)
    date_font = _load_font("medium", 26)
    draw.text((W // 2, 962), date_location, font=date_font, fill=GOLD, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지 {output_path.parent.name}/{output_path.name}] {output_path.stat().st_size // 1024}KB")


def compose_closing(headline: list[str], cta: str, output_path: Path) -> None:
    """임팩트 클로징(ig_06) — 버건디 풀배경 + 강한 타이포 + 공동 로고 + CTA.
    가이드 카드 대체. 카피 = 운동/회복 공동 메시지(편별 다름)."""
    # 1) 버건디 풀배경 + 미묘한 골드 비네팅 텍스처
    canvas = Image.new("RGB", (W, H), BURGUNDY)
    draw = ImageDraw.Draw(canvas)

    # 2) 상단 공동 브랜딩 — 좌상단 웰페리온(크림) / 우상단 생크몽드(크림)
    canvas = _paste_wellperion_topleft(canvas, logo_w=140, tint=(250, 247, 242), x=44, y=48)
    canvas = _paste_cinq_topright(canvas, logo_w=160, tint=(250, 247, 242))
    draw = ImageDraw.Draw(canvas)

    # 3) 골드 짧은 상단 악센트 선 (헤드라인 위)
    draw.rectangle([(W // 2 - 40, 372), (W // 2 + 40, 376)], fill=GOLD)

    # 4) 헤드라인 — 강한 타이포(크림, bold, 중앙). 줄별 리스트로 정확 제어.
    head_font = _load_font("bold", 62)
    line_h = 86
    total_h = len(headline) * line_h
    y0 = H // 2 - total_h // 2 - 30
    for i, ln in enumerate(headline):
        draw.text((W // 2, y0 + i * line_h + line_h // 2), ln,
                  font=head_font, fill=(250, 247, 242), anchor="mm")

    # 5) 골드 짧은 하단 악센트 선 (CTA 위)
    cta_line_y = y0 + total_h + 44
    draw.rectangle([(W // 2 - 40, cta_line_y), (W // 2 + 40, cta_line_y + 4)], fill=GOLD)

    # 6) CTA (골드, medium, 중앙)
    cta_font = _load_font("semibold", 34)
    draw.text((W // 2, cta_line_y + 56), cta, font=cta_font, fill=GOLD, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [클로징 {output_path.parent.name}/{output_path.name}] {output_path.stat().st_size // 1024}KB")


# ---------------------------------------------------------------------------
SRC = PROJECT_ROOT / "instagram" / "Image" / "생크몽드_소개(원본 이미지)"

# 파일명 매핑(번호 → 실제 파일)
IMG = {
    "1-1": "1-1. DSC09492.jpg",
    "1-2": "1-2. DSC09443.jpg",
    "1-3": "1-3. DSC09485.jpg",
    "1-4": "1-4. DSC09488.jpg",
    "2-1": "2-1. DSC09461.jpg",
    "2-2": "2-2. DSC09463.jpg",
    "3":   "3. DSC09483.jpg",
    "4-1": "4-1. DSC09470.jpg",
    "4-2": "4-2. DSC09473.jpg",
    "5-1": "5-1. DSC09535.jpg",
    "5-2": "5-2. DSC09545.jpg",
    "6":   "6. DSC09496.jpg",
    "7-1": "7-1. DSC09439.jpg",
    "7-2": "7-2. DSC09441.jpg",
    "7-3": "7-3. DSC09442.jpg",
}

# 편당 6장 구성(2026-06-11 GM 피드백 보강):
#   cover  = ig_01 표지(정본 65/35) — (photo_key, title_eng, title_kor, date_location)
#   body   = ig_02~05 본문 4장 — (key, caption, brightness)
#   closing= ig_06 임팩트 클로징 — (headline_lines, cta)
DATE_LOCATION = "한남동 웰페리온 × Cinq Mondes"

EPISODES = {
    "ep1": {
        "cover": ("1-2", "PARIS, ARRIVED", "파리의 회복 의식이 한남동에", DATE_LOCATION),
        "body": [
            ("1-1", "Cinq Mondes — 5개 대륙의 뷰티 리추얼이 머무는 자리", 0.88),
            ("1-3", "서두름을 내려놓는 공간, 회복은 앉는 순간부터", 0.88),
            ("1-4", "정직한 식물성 포뮬러, 피부에 꼭 필요한 것만", 0.88),
            ("2-1", "발끝을 씻어내며 여는 환대 — 리추얼의 첫 인사", 0.88),
        ],
        "closing": (["운동은 웰페리온,", "회복은 Cinq Mondes —", "한 곳에서."],
                    "문의: wellperion.com/ko/inquiry"),
    },
    "ep2": {
        "cover": ("2-2", "SLOW DOWN", "감각이 깨어나는 회복의 시간", DATE_LOCATION),
        "body": [
            ("4-1", "멈춤도 회복입니다 — 호흡과 명상의 자리", 0.88),
            ("4-2", "소리가 긴장을 풀어내는 동양의 회복 리추얼", 0.88),
            ("6",   "머리끝부터 — 두피와 어깨의 피로를 덜어내는 손길", 0.88),
            ("3",   "한 걸음마다 깊어지는 몰입, 파리의 결을 따라", 0.88),
        ],
        "closing": (["운동은 웰페리온,", "회복은 Cinq Mondes —", "한 곳에서."],
                    "문의: wellperion.com/ko/inquiry"),
    },
    "ep3": {
        "cover": ("5-1", "THE RITUAL", "회복이 완성되는 자리", DATE_LOCATION),
        "body": [
            ("7-1", "5개 세계의 식물이 한 벽에, 회복의 모든 단계", 0.88),
            ("7-3", "고농축 식물 오일, 피부가 시간이 갈수록 건강해지도록", 0.88),
            ("7-2", "향으로 마무리하는 리추얼, 회복의 여운을 가지고 돌아갑니다", 0.88),
            ("5-2", "시그니처 리추얼 — 깊은 회복의 정점", 0.62),
        ],
        "closing": (["운동은 웰페리온,", "회복은 Cinq Mondes —", "한 곳에서 완성됩니다."],
                    "문의: wellperion.com/ko/inquiry"),
    },
}


def main():
    print("=== 생크몽드 IG 3편 합성 (편당 6장: 표지+본문4+클로징) ===")
    for ep, spec in EPISODES.items():
        out_dir = PROJECT_ROOT / "instagram" / f"260611_생크몽드_{ep}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[{ep}] → {out_dir}")

        # ig_01 — 표지(커버, 정본 65/35)
        ckey, title_eng, title_kor, date_loc = spec["cover"]
        cover_photo = SRC / IMG[ckey]
        if not cover_photo.exists():
            print(f"[ERROR] 표지 원본 없음: {cover_photo}")
            sys.exit(1)
        compose_cover(cover_photo, title_eng, title_kor, date_loc, out_dir / "ig_01.jpg")

        # ig_02~05 — 본문 4장
        for idx, (key, caption, bright) in enumerate(spec["body"], start=2):
            photo = SRC / IMG[key]
            if not photo.exists():
                print(f"[ERROR] 원본 없음: {photo}")
                sys.exit(1)
            compose_slide(photo, caption, out_dir / f"ig_{idx:02d}.jpg", brightness=bright)

        # ig_06 — 임팩트 클로징
        headline, cta = spec["closing"]
        compose_closing(headline, cta, out_dir / "ig_06.jpg")

    print("\n=== 합성 완료 (편당 6장) ===")


if __name__ == "__main__":
    main()
