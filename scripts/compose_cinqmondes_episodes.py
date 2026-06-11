"""생크몽드(Cinq Mondes) IG 3편(Episode) 슬라이드 생성 (2026-06-11 GM 결재).

생크몽드 팀 공유용 — 외부 파트너 스파 소개를 3편 에피소드로 전량 제작.
엔진 = compose_spa_cinqmondes / compose_barre 헬퍼 재사용(새 엔진 손코딩 금지).

편당 디자인(전 슬라이드 공통):
  - 마지막 가이드라인 카드 제외
  - 페이지 카운트 없음
  - 우측 상단 로고 = 생크몽드 로고(_assets/logo/cinq_mondes_logo_a.png)
  - 웰페리온 로고 = 좌측 하단(공동 브랜딩)
  - 톤: 크림 #FAF7F2 / 버건디 #8B1A2F / 골드 #C9A96E

산출: instagram/260611_생크몽드_ep1|ep2|ep3/ (각 5장, ig_01~05)
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


def _paste_wellperion_bottomleft(canvas: Image.Image, logo_w: int = 130,
                                 tint: tuple[int, int, int] | None = None) -> Image.Image:
    """웰페리온 로고를 좌측 하단에 배치(공동 브랜딩). tint 지정 시 단색 적용."""
    logo = Image.open(LOGO_WHITE_ALPHA).convert("RGBA")
    ow, oh = logo.size
    lh = int(oh * logo_w / ow)
    logo = logo.resize((logo_w, lh), Image.LANCZOS)
    if tint is not None:
        logo = _tint_logo(logo, tint)
    base = canvas.convert("RGBA")
    base.paste(logo, (44, H - 40 - lh), mask=logo.split()[3])
    return base.convert("RGB")


def _apply_gradient(img: Image.Image, start_y: int = 540) -> Image.Image:
    """하단 그라디언트 — 투명→버건디 초다크 오버레이(텍스트 가독성)."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    dark = (26, 0, 12)
    for y in range(H):
        if y < start_y:
            alpha = 0
        else:
            t = (y - start_y) / (H - start_y)
            alpha = min(215, int(220 * (t ** 1.15)))
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
    페이지 카운트 없음 / 생크몽드 로고(우상단) / 웰페리온 로고(좌하단)."""
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(brightness)
    canvas = _apply_gradient(canvas, start_y=480)

    # 생크몽드 로고(우상단, 크림 tint)
    canvas = _paste_cinq_topright(canvas, logo_w=150, tint=(250, 247, 242))
    draw = ImageDraw.Draw(canvas)

    # 레이아웃 밴드(겹침 방지):
    #   풋터(로고+브랜드라인)  : y = 1000 baseline, 높이 ~36 → 상단 ~964
    #   카피 블록              : 마지막 줄 baseline 이 풋터 위(y<=905)에서 끝나도록 위로 쌓음
    LOGO_W = 104
    FOOT_BASELINE = 1004
    body_font = _load_font("medium", 44)
    line_h = 58
    lines = _wrap_text(draw, caption, body_font, max_w=W - 96 - 40)
    n = len(lines)
    last_line_top = 858            # 마지막 줄 상단 — 풋터(964~)와 안전 간격 확보
    start_y = last_line_top - (n - 1) * line_h
    bar_top = start_y - 2
    bar_bottom = last_line_top + 46
    draw.rectangle([(60, bar_top), (64, bar_bottom)], fill=GOLD)
    for i, ln in enumerate(lines):
        draw.text((96, start_y + i * line_h), ln, font=body_font, fill=WHITE)

    # 웰페리온 로고(좌하단, 크림 tint) — 풋터 밴드
    logo = Image.open(LOGO_WHITE_ALPHA).convert("RGBA")
    ow, oh = logo.size
    lh = int(oh * LOGO_W / ow)
    logo = logo.resize((LOGO_W, lh), Image.LANCZOS)
    logo = _tint_logo(logo, (250, 247, 242))
    base = canvas.convert("RGBA")
    base.paste(logo, (60, FOOT_BASELINE - lh), mask=logo.split()[3])
    canvas = base.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 풋터 — 로고 우측에 브랜드 라인(작게), 로고와 수직 중앙 정렬
    foot_font = _load_font("medium", 22)
    fb = foot_font.getbbox("× Cinq Mondes")
    foot_top = FOOT_BASELINE - lh + (lh - (fb[3] - fb[1])) // 2 - fb[1]
    draw.text((60 + LOGO_W + 18, foot_top), "× Cinq Mondes", font=foot_font, fill=GOLD)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{output_path.parent.name}/{output_path.name}] {output_path.stat().st_size // 1024}KB")


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

# (key, caption, brightness)  — 5-2는 과노출 → 밝기 0.62로 강하게 보정
EPISODES = {
    "ep1": [
        ("1-2", "운동 다음의 시간, 파리의 회복 의식이 한남동에서 시작됩니다", 0.88),
        ("1-1", "Cinq Mondes — 5개 대륙의 뷰티 리추얼이 머무는 자리", 0.88),
        ("1-3", "서두름을 내려놓는 공간, 회복은 앉는 순간부터", 0.88),
        ("1-4", "정직한 식물성 포뮬러, 피부에 꼭 필요한 것만", 0.88),
        ("2-1", "발끝을 씻어내며 여는 환대 — 리추얼의 첫 인사", 0.88),
    ],
    "ep2": [
        ("2-2", "차 한 모금으로 호흡을 늦추고, 몸의 속도를 바꿉니다", 0.88),
        ("4-1", "멈춤도 회복입니다 — 호흡과 명상의 자리", 0.88),
        ("4-2", "소리가 긴장을 풀어내는 동양의 회복 리추얼", 0.88),
        ("6",   "머리끝부터 — 두피와 어깨의 피로를 덜어내는 손길", 0.88),
        ("3",   "한 걸음마다 깊어지는 몰입, 파리의 결을 따라", 0.88),
    ],
    "ep3": [
        ("5-1", "시그니처 리추얼 — 아유르베다부터 코비도까지, 깊은 회복의 정점", 0.88),
        ("7-1", "5개 세계의 식물이 한 벽에, 회복의 모든 단계", 0.88),
        ("7-3", "고농축 식물 오일, 피부가 시간이 갈수록 건강해지도록", 0.88),
        ("7-2", "향으로 마무리하는 리추얼, 회복의 여운을 가지고 돌아갑니다", 0.88),
        ("5-2", "운동은 웰페리온에서, 회복은 Cinq Mondes에서 — 한 곳에서 완성됩니다 / 문의: wellperion.com/ko/inquiry", 0.62),
    ],
}


def main():
    print("=== 생크몽드 IG 3편 합성 ===")
    for ep, slides in EPISODES.items():
        out_dir = PROJECT_ROOT / "instagram" / f"260611_생크몽드_{ep}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[{ep}] → {out_dir}")
        for idx, (key, caption, bright) in enumerate(slides, start=1):
            photo = SRC / IMG[key]
            if not photo.exists():
                print(f"[ERROR] 원본 없음: {photo}")
                sys.exit(1)
            compose_slide(photo, caption, out_dir / f"ig_{idx:02d}.jpg", brightness=bright)
    print("\n=== 합성 완료 ===")


if __name__ == "__main__":
    main()
