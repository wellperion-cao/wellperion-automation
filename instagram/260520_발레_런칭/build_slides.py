# 260520 발레 신규 클래스 런칭 — IG 슬라이드 7장 빌드
# 바레(260520_바레_런칭) 최종 슬라이드 디자인 벤치마킹 — 동일 레이아웃 실제 합성
#   1p 표지   : 상단 2/3 세피아 인물 + 좌상단 풀로고 + 우상단 둥근 배지
#               하단 1/3 다크박스: BALLET / 발레 / 구분선 / 2026.05 OPEN · 한남동 웰니스 스튜디오
#   2~6p 내지 : 풀블리드 사진 + 하단 그라디언트 + 좌상단 로고 + 우상단 둥근 배지 + N/07 카운터
#               베이지 분리선 + 이벤트 라벨 + 한글 헤드라인 + 서브라인 + 좌하단 WELLPERION · BALLET
#   7p        : WELLPERION GUIDE 카드 (instagram/_assets/guideline_card.jpg 복사)
# 비용 언급 금지 / 정원 8인·강사 이수지·일정 금 10·11시·장소 한남동 웰니스 스튜디오
# 실행: .venv\Scripts\python instagram\260520_발레_런칭\build_slides.py
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import load_font, wrap_text  # noqa: E402

FOLDER = ROOT / "instagram" / "260520_발레_런칭"
SRC = ROOT / "instagram" / "Image" / "발레_런칭(원본 이미지)"
OUT_MASTER = FOLDER / "output"
OUT_IG = FOLDER / "output(인스타그램)"
GUIDE_CARD = ROOT / "instagram" / "_assets" / "guideline_card.jpg"

LOGO_DIR = ROOT / "instagram" / "_assets" / "logo"
LOGO_WHITE = LOGO_DIR / "wellperion_white_alpha.png"   # 사진 위 (밝은 오버레이)
LOGO_BEIGE = LOGO_DIR / "wellperion_beige_alpha.png"   # 다크 박스 위

# 브랜드 컬러 (241030 가이드)
BLACK = (34, 31, 32)        # #221F20
BEIGE = (183, 159, 138)     # #B79F8A
WHITE = (255, 255, 255)
GREY = (205, 205, 205)

SIZE = 1080                  # 정사각 1080²
COUNT = 7                    # 슬라이드 총 7장 (카운터 N/07)

# ----------------------------------------------------------------------
# 헬퍼
# ----------------------------------------------------------------------
def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fit_square(path: Path, w: int, h: int,
               x_bias: float = 0.5, y_bias: float = 0.5,
               zoom: float = 1.0) -> Image.Image:
    """원본을 crop + 리사이즈 (EXIF 보정).
    x_bias/y_bias: 0=좌/상단, 0.5=중앙(기본), 1=우/하단.
    zoom>1: 추가 확대(타이트 크롭) — 간섭요소(벽 사인 등)를 프레임 밖으로 밀어낼 때."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    sw, sh = img.size
    tr, sr = w / h, sw / sh
    if sr > tr:
        nw = int(sh * tr)
    else:
        nw = sw
    nh = int(nw / tr)
    if nh > sh:
        nh = sh
        nw = int(nh * tr)
    # zoom: 크롭 영역을 더 작게(= 확대)
    nw = int(nw / zoom)
    nh = int(nh / zoom)
    x0 = int((sw - nw) * x_bias)
    y0 = int((sh - nh) * y_bias)
    img = img.crop((x0, y0, x0 + nw, y0 + nh))
    return img.resize((w, h), Image.LANCZOS)


def sepia_duotone(img: Image.Image,
                  dark="#3A332C", light="#D8C3AC") -> Image.Image:
    """세피아 듀오톤 — 바레 표지 톤(따뜻한 세피아) 재현."""
    g = img.convert("L")
    dr, dg, db = _hex(dark)
    lr, lg, lb = _hex(light)
    r = [int(dr + (lr - dr) * (i / 255)) for i in range(256)]
    gg = [int(dg + (lg - dg) * (i / 255)) for i in range(256)]
    b = [int(db + (lb - db) * (i / 255)) for i in range(256)]
    return Image.merge("RGB", (g.point(r), g.point(gg), g.point(b)))


def bottom_gradient(img: Image.Image, start=0.40, max_alpha=248) -> Image.Image:
    """하단 그라디언트 (텍스트 가독성) — 바레 내지 톤."""
    w, h = img.size
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    gs = int(h * start)
    for y in range(h):
        if y < gs:
            a = 0
        else:
            t = (y - gs) / (h - gs)
            a = min(max_alpha, int(255 * (t ** 1.45)))
        d.line([(0, y), (w, y)], fill=(*BLACK, a))
    out = Image.alpha_composite(img.convert("RGBA"), ov)
    return ImageEnhance.Brightness(out.convert("RGB")).enhance(0.93)


def paste_logo(canvas: Image.Image, logo_path: Path, x: int, y: int,
               target_w: int, scrim: bool = False) -> Image.Image:
    """로고 PNG를 (x,y)에 합성. scrim=True면 로고 뒤 부드러운 다크 라디얼 스크림
    (배경의 WELLPERION 벽 사인 등과 충돌 방지 — 로고 가독성 확보)."""
    logo = Image.open(logo_path).convert("RGBA")
    ow, oh = logo.size
    th = int(oh * target_w / ow)
    logo = logo.resize((target_w, th), Image.LANCZOS)
    c = canvas.convert("RGBA")
    if scrim:
        # 상단 헤더 스크림 — 좌측 강 / 우측 약, 위 강 / 아래 소멸.
        # 배경 WELLPERION 벽 사인을 자연스럽게 흡수(프리미엄 헤더 비네트).
        band_h = y + th + int(SIZE * 0.06)
        W = c.size[0]
        scr = Image.new("L", (W, band_h), 0)
        spx = scr.load()
        peak = 175
        left_zone = x + target_w + int(SIZE * 0.05)  # 로고 영역까지 풀강도
        for yy in range(band_h):
            fy = 1.0 - (yy / band_h)
            ry = int(peak * (fy ** 1.25))
            for xx in range(W):
                if xx <= left_zone:
                    fx = 1.0
                else:
                    # 로고 우측 → 0.18까지 완만히 감쇠 (배지 영역엔 옅게)
                    t = (xx - left_zone) / (W - left_zone)
                    fx = max(0.0, (1.0 - t) ** 1.6) * 0.85 + 0.04
                spx[xx, yy] = int(ry * fx)
        ov = Image.new("RGBA", c.size, (*BLACK, 0))
        amask = Image.new("L", c.size, 0)
        amask.paste(scr, (0, 0))
        ov.putalpha(amask)
        c = Image.alpha_composite(c, ov)
    c.paste(logo, (x, y), mask=logo)
    return c.convert("RGB")


def logo_h(logo_path: Path, target_w: int) -> int:
    ow, oh = Image.open(logo_path).size
    return int(oh * target_w / ow)


def rounded_badge(draw: ImageDraw.ImageDraw, x_right: int, y: int,
                  text="WELLPERION", fill=BEIGE) -> None:
    """우상단 둥근 베이지 배지 (바레 동일)."""
    font = load_font("bold", int(SIZE * 0.026))
    bb = font.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad_x, pad_y = int(SIZE * 0.028), int(SIZE * 0.018)
    bw, bh = tw + 2 * pad_x, th + 2 * pad_y
    x0 = x_right - bw
    draw.rounded_rectangle([(x0, y), (x0 + bw, y + bh)],
                           radius=bh // 2, fill=fill)
    draw.text((x0 + pad_x, y + pad_y - bb[1]), text, font=font, fill=BLACK)
    return bh


def tracked_text(draw, text, font, x, y, fill, track_ratio=0.08):
    """자간(letter-spacing) 적용 텍스트. 끝 x 반환."""
    cx = x
    for ch in text:
        draw.text((cx, y), ch, font=font, fill=fill)
        bb = font.getbbox(ch)
        cx += (bb[2] - bb[0]) + int(font.size * track_ratio)
    return cx


def tracked_width(text, font, track_ratio=0.08) -> int:
    w = 0
    for ch in text:
        bb = font.getbbox(ch)
        w += (bb[2] - bb[0]) + int(font.size * track_ratio)
    return w - int(font.size * track_ratio) if text else 0


# ----------------------------------------------------------------------
# 1p — 표지 (상단 2/3 세피아 인물 + 하단 1/3 다크박스)
# ----------------------------------------------------------------------
def build_cover(src: Path, out: Path) -> None:
    canvas = Image.new("RGB", (SIZE, SIZE), BLACK)
    photo_h = int(SIZE * 0.66)
    photo = sepia_duotone(fit_square(src, SIZE, photo_h))
    canvas.paste(photo, (0, 0))

    margin = int(SIZE * 0.05)
    lw = int(SIZE * 0.26)
    canvas = paste_logo(canvas, LOGO_WHITE, margin, margin, lw, scrim=True)

    draw = ImageDraw.Draw(canvas)
    rounded_badge(draw, SIZE - margin, margin)

    # 하단 다크박스 영역
    box_y = photo_h
    # 상단 얇은 베이지 풀폭 라인
    rule_y = box_y + int((SIZE - box_y) * 0.10)
    draw.line([(margin, rule_y), (SIZE - margin, rule_y)], fill=BEIGE, width=2)

    # BALLET (대문자, 와이드 트래킹, 베이지) — 중앙
    eng_font = load_font("bold", int(SIZE * 0.092))
    eng = "BALLET"
    ew = tracked_width(eng, eng_font, 0.10)
    ey = rule_y + int((SIZE - box_y) * 0.16)
    tracked_text(draw, eng, eng_font, (SIZE - ew) // 2, ey, BEIGE, 0.10)

    # 발레 (한글, 화이트) — 중앙
    kor_font = load_font("semibold", int(SIZE * 0.046))
    kor = "발레"
    kb = kor_font.getbbox(kor)
    kw = kb[2] - kb[0]
    ky = ey + int(SIZE * 0.092 * 1.45)
    draw.text(((SIZE - kw) // 2, ky), kor, font=kor_font, fill=WHITE)

    # 짧은 중앙 구분선
    srule_y = ky + int(SIZE * 0.046 * 1.9)
    srule_w = int(SIZE * 0.05)
    draw.line([((SIZE - srule_w) // 2, srule_y),
               ((SIZE + srule_w) // 2, srule_y)], fill=BEIGE, width=2)

    # 일자·장소 — 중앙
    meta_font = load_font("medium", int(SIZE * 0.024))
    meta = "2026.05 OPEN  ·  한남동 웰니스 스튜디오"
    mb = meta_font.getbbox(meta)
    mw = mb[2] - mb[0]
    my = srule_y + int(SIZE * 0.04)
    draw.text(((SIZE - mw) // 2, my), meta, font=meta_font, fill=GREY)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=92, optimize=True)


# ----------------------------------------------------------------------
# 2~6p — 내지 (풀블리드 + 하단 그라디언트 + 카운터)
# ----------------------------------------------------------------------
def build_interior(src: Path, out: Path, page: int,
                   headline: str, subline: str,
                   x_bias: float = 0.5, y_bias: float = 0.5,
                   zoom: float = 1.0) -> None:
    canvas = bottom_gradient(
        fit_square(src, SIZE, SIZE, x_bias=x_bias, y_bias=y_bias, zoom=zoom))

    margin = int(SIZE * 0.05)
    lw = int(SIZE * 0.24)
    canvas = paste_logo(canvas, LOGO_WHITE, margin, margin, lw, scrim=True)

    draw = ImageDraw.Draw(canvas)
    bh = rounded_badge(draw, SIZE - margin, margin)

    # 카운터 N / 07 (배지 아래 우측) — 그림자 1px로 밝은 배경에서도 가독
    cnt_font = load_font("medium", int(SIZE * 0.024))
    cnt = f"{page:02d} / {COUNT:02d}"
    cb = cnt_font.getbbox(cnt)
    cnt_x = SIZE - margin - (cb[2] - cb[0])
    cnt_y = margin + bh + int(SIZE * 0.018)
    draw.text((cnt_x + 1, cnt_y + 1), cnt, font=cnt_font, fill=(0, 0, 0))
    draw.text((cnt_x, cnt_y), cnt, font=cnt_font, fill=BEIGE)

    # 하단 텍스트 블록
    # 베이지 풀폭 분리선
    head_font = load_font("bold", int(SIZE * 0.050))
    sub_font = load_font("semibold", int(SIZE * 0.030))
    label_font = load_font("medium", int(SIZE * 0.021))

    head_lines = wrap_text(headline, head_font, SIZE - 2 * margin)
    head_lh = int(SIZE * 0.050 * 1.30)
    sub_line_count = len(subline.split("\n"))
    sub_lh = int(SIZE * 0.030 * 1.45)
    block_h = (len(head_lines) * head_lh
               + sub_line_count * sub_lh        # subline (다중 줄 대응)
               + int(SIZE * 0.021 * 2.2))       # label
    # 워드마크 위 여백 확보
    wm_zone = int(SIZE * 0.075)
    block_top = SIZE - wm_zone - block_h - int(SIZE * 0.02)

    rule_y = block_top - int(SIZE * 0.03)
    draw.line([(margin, rule_y), (SIZE - margin, rule_y)], fill=BEIGE, width=2)

    # 이벤트 라벨 (중복 제거: 2026.05 한 번만)
    label = "BALLET  ·  2026.05 OPEN"
    draw.text((margin, block_top), label, font=label_font, fill=BEIGE)

    # 헤드라인
    hy = block_top + int(SIZE * 0.021 * 2.2)
    for ln in head_lines:
        draw.text((margin, hy), ln, font=head_font, fill=WHITE)
        hy += head_lh

    # 서브라인 (줄바꿈 \n 지원 — CTA 한/영 2줄 등)
    sub_lh = int(SIZE * 0.030 * 1.45)
    sy = hy + int(SIZE * 0.006)
    for sl in subline.split("\n"):
        draw.text((margin, sy), sl, font=sub_font, fill=BEIGE)
        sy += sub_lh

    # 좌하단 워드마크 WELLPERION · BALLET
    wm_font = load_font("bold", int(SIZE * 0.022))
    draw.text((margin, SIZE - margin - int(SIZE * 0.024)),
              "WELLPERION  ·  BALLET", font=wm_font, fill=WHITE)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=92, optimize=True)


# ----------------------------------------------------------------------
# 슬라이드 매핑 (비용 언급 금지)
# ----------------------------------------------------------------------
# 표지 = 파우더 점프 컷 (좌상단 깨끗·드라마틱·프리미엄 — 바레 ig_04 톤)
COVER_SRC = SRC / "KakaoTalk_20260512_142029503.png"

# 내지 매핑. dict로 크롭 파라미터 포함.
# 벽 사인이 좌상단 로고와 겹치는 컷(3·5)은 우측 바이어스 + 줌으로 사인을 프레임 밖/우측으로 밀어 충돌 제거.
INTERIORS = [
    dict(page=2, src=SRC / "KakaoTalk_20260512_142029503_02.jpg",
         headline="클래식 발레의 정수", subline="균형 · 자세 · 우아한 움직임",
         x_bias=0.5, y_bias=0.25),   # 상단 크롭 — 얼굴·상체 중심
    dict(page=3, src=SRC / "KakaoTalk_20260519_155452092.png",
         headline="전문가의 1:1 교정", subline="이수지 INSTRUCTOR",
         x_bias=1.0, y_bias=0.5, zoom=1.28),   # 우측으로 — 벽사인 좌측 탈락
    dict(page=4, src=SRC / "KakaoTalk_20260519_155452092_03.png",
         headline="최대 8인 프라이빗", subline="매주 금요일 오전 10시 · 11시",
         x_bias=0.5, y_bias=0.5),
    dict(page=5, src=SRC / "KakaoTalk_20260512_142029503_02.jpg",
         headline="특별한 움직임의 여정",
         subline="문의 (한) wellperion.com/ko/inquiry\n       (영) wellperion.com/en/inquiry",
         x_bias=0.5, y_bias=0.78),   # 하단 크롭 — 치마·발 중심, 2p와 다른 앵글
    dict(page=6, src=SRC / "KakaoTalk_20260519_155452092_04.png",
         headline="한남동 웰니스 스튜디오", subline="지금, 발레를 시작하세요",
         x_bias=0.5, y_bias=0.5),
]


def main():
    OUT_MASTER.mkdir(parents=True, exist_ok=True)
    OUT_IG.mkdir(parents=True, exist_ok=True)

    # 1p 표지
    build_cover(COVER_SRC, OUT_MASTER / "ig_01.jpg")

    # 2~6p 내지
    for it in INTERIORS:
        build_interior(it["src"], OUT_MASTER / f"ig_{it['page']:02d}.jpg",
                       it["page"], it["headline"], it["subline"],
                       x_bias=it.get("x_bias", 0.5),
                       y_bias=it.get("y_bias", 0.5),
                       zoom=it.get("zoom", 1.0))

    # 7p 가이드 카드
    shutil.copy(GUIDE_CARD, OUT_MASTER / "ig_07.jpg")

    # 인스타 채널 배치 (ig_01~07 동일 복사)
    for i in range(1, 8):
        shutil.copy(OUT_MASTER / f"ig_{i:02d}.jpg", OUT_IG / f"ig_{i:02d}.jpg")

    print("[OK] 발레 슬라이드 7장 생성 완료")
    for i in range(1, 8):
        p = OUT_MASTER / f"ig_{i:02d}.jpg"
        print(f"  ig_{i:02d}.jpg  {round(p.stat().st_size/1024,1)}KB")


if __name__ == "__main__":
    main()
