"""발레 런칭 슬라이드 합성 스크립트 (바레 SSOT import)
레퍼런스: scripts/compose_barre.py — 모든 스타일 함수를 import 재사용.
발레 고유: 사진 경로·텍스트·표지 top_crop_fill(인물 보정)·full_dark 분기.
스타일(좌표·폰트크기·색상·선굵기·칩정렬)은 바레 함수를 그대로 호출 — 추측 0.

캔버스: 1080x1080
구조:
  ig_01 표지   = 사진 상단 65%(듀오톤) + 검정 하단 35% 정보영역 (카운터 없음)
  ig_02~06 본문 = 전체 사진 fill + 하단 그라디언트 + 좌하단 텍스트 + 우상단 칩
  ig_07 가이드  = guideline_card.jpg 원본 복사

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
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

# 캐논 값 단일출처 직독 (ssot/canon_values.json)
sys.path.insert(0, str(Path(__file__).parent.parent))
from ssot.canon import canon_get
_INQUIRY_URL = "문의 :  " + canon_get("inquiry_path")

# ── 바레 SSOT import ─────────────────────────────────────────────────────────
# 스타일 상수·함수 전부 바레에서 가져온다. 발레 독자 정의 금지.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
# 색·폰트·경로 상수 = brand_constants SSOT (값 불변). 레이아웃 함수·W/H는 바레에서.
from brand_constants import (
    PROJECT_ROOT,
    BEIGE, BLACK_BG, WHITE, GRAY, CHIP_BEIGE, SEP_LINE,
    FONT_BOLD, FONT_SEMIBOLD, FONT_MEDIUM,
)
from compose_barre import (
    W, H,
    to_duotone,
    load_font,
    center_crop_fill,
    apply_bottom_gradient,
    paste_logo,
    draw_chip,
    draw_counter,
    compose_guide_card,
)
# ─────────────────────────────────────────────────────────────────────────────


def top_crop_fill(img_path: Path, w: int, h: int,
                  x_bias: float = 0.5, top_bias: float = 0.18,
                  zoom: float = 1.0) -> Image.Image:
    """표지용 — 상단(머리/얼굴)을 살리는 top-biased crop.
    x_bias: 가로 크롭 위치(인물이 좌/우로 치우친 사진 보정). zoom>1: 인물 확대."""
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


# ---------------------------------------------------------------------------
# 표지 (ig_01) — 바레 compose_cover 동일 구조
# 발레 고유: top_crop_fill(인물 보정 인자), 텍스트 내용
# ---------------------------------------------------------------------------
def compose_cover(
    photo_path: Path,
    title_eng: str,
    title_kor: str,
    date_location: str,
    output_path: Path,
    cover_x_bias: float = 0.5,
    cover_zoom: float = 1.0,
) -> None:
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    PHOTO_H = 700  # 바레 완성본 실측 동일
    photo = top_crop_fill(photo_path, W, PHOTO_H, x_bias=cover_x_bias, zoom=cover_zoom)
    photo = to_duotone(photo, normalize=True)  # 표지 톤 일관(정본 셋팅) — 밝은 표지도 로고·칩 대비 확보
    canvas.paste(photo, (0, 0))

    # 분리선 — 바레 완성본 실측: y=701~702, x=50~1030
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    # 우상단 칩 — 바레 완성본 동일 (chip_font 28, chip_w 240, chip_h 52)
    chip_font = load_font("bold", 24)
    chip_w, chip_h = 180, 48          # 바레 정본 측정
    chip_x = W - 50 - chip_w          # 우측끝 x=1030
    chip_y = 60
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 검정 정보영역 — 바레 완성본 y좌표 1:1
    # 영문 대제목 (베이지·큰·위) — 바레 정본 측정: 글자높이41, 중심 y786
    eng_font = load_font("bold", 58)
    draw.text((W // 2, 786), title_eng, font=eng_font, fill=BEIGE, anchor="mm")

    # 한글 부제 (흰색·작은·아래) — 바레 정본 중심 y=860
    kor_font = load_font("semibold", 38)
    draw.text((W // 2, 860), title_kor, font=kor_font, fill=WHITE, anchor="mm")

    sub_line_y = 920
    draw.rectangle(
        [(W // 2 - 30, sub_line_y), (W // 2 + 30, sub_line_y + 2)],
        fill=BEIGE,
    )

    date_font = load_font("medium", 26)
    draw.text((W // 2, 962), date_location, font=date_font, fill=(166, 151, 139), anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 스토리 슬라이드 — 바레 compose_story 동일 구조
# 발레 고유: full_dark 분기(어두운 사진용), 텍스트 내용
# 바레와 다른 점 없음(분리선 제거, 카운터 제거 상태 유지)
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
        canvas = center_crop_fill(photo_path, W, H)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.95)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=600)
    else:
        canvas = center_crop_fill(photo_path, W, H)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
        canvas = apply_bottom_gradient(canvas, gradient_start_y=555)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    # 우상단 칩 — 바레 완성본 동일
    chip_font = load_font("bold", 24)
    chip_w, chip_h = 180, 48          # 바레 정본 측정
    chip_x = W - 50 - chip_w          # 우측끝 x=1030
    chip_y = 60
    draw_chip(draw, chip_label, chip_font, chip_x, chip_y, chip_w, chip_h)

    # 카운터 없음 (GM 지시 2026-06-05)

    # 메타라인 위 연한 분리선 (바레 정본 — 옅게)
    draw.line([(40, 772), (W - 40, 772)], fill=(150, 138, 120), width=1)

    # 메타라인 — 바레 완성본 y=795
    meta_font = load_font("medium", 26)  # 1·3줄 글꼴 = medium
    draw.text((40, 795), meta_line, font=meta_font, fill=BEIGE)  # 1·3줄 색 = 베이지

    # 한글 대제목 — 바레 완성본 y=860
    title_font = load_font("bold", 64)
    draw.text((40, 860), title_kor, font=title_font, fill=WHITE)

    # 서브텍스트 — 바레 완성본 y=958
    sub_font = load_font("medium", 30)  # 1·3줄 글꼴 통일 = medium
    sub_lines = sub_text.split("\n")
    if len(sub_lines) == 1:
        draw.text((40, 958), sub_text, font=sub_font, fill=BEIGE)
    else:
        sy = 936
        for sl in sub_lines:
            draw.text((40, sy), sl, font=sub_font, fill=BEIGE)
            sy += 40

    # 풋터 — 바레 완성본 y=1026
    footer_font = load_font("bold", 26)  # 2·4줄 글꼴 = bold
    draw.text((40, 1026), footer_text, font=footer_font, fill=WHITE)  # 2·4줄 색 = 흰색

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{current:02d}/{total:02d}] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 발레 런칭 슬라이드 세트
#
# ig_01  표지        BALLET / 발레          카운터 없음
# ig_02  1:1 교정    02/07
# ig_03  바 그룹     03/07
# ig_04  팔 든 그룹  04/07
# ig_05  단독 포즈   05/07
# ig_06  파우더 점프 06/07  (full_dark)
# ig_07  GUIDE 카드  카운터 없음
# ---------------------------------------------------------------------------
SRC = PROJECT_ROOT / "instagram" / "260520_발레_런칭" / "output(인스타그램)" / "_src_gm"

COVER = SRC / "ig_01.jpg"
P02   = SRC / "ig_02.png"
P03   = SRC / "ig_03.png"
P04   = SRC / "ig_04.png"
P05   = SRC / "ig_05.png"
P06   = SRC / "ig_06.png"


def main():
    out_ig = PROJECT_ROOT / "instagram" / "260520_발레_런칭" / "output(인스타그램)"
    out_master = PROJECT_ROOT / "instagram" / "260520_발레_런칭" / "output"
    out_ig.mkdir(parents=True, exist_ok=True)
    out_master.mkdir(parents=True, exist_ok=True)

    for p in [COVER, P02, P03, P04, P05, P06]:
        if not p.exists():
            print(f"[ERROR] 소스 없음: {p}")
            sys.exit(1)

    TOTAL = 7  # 표지 + 본문5 + 가이드

    print("=== 발레 런칭 슬라이드 합성 (바레 SSOT import) ===")
    print(f"출력(인스타): {out_ig}")

    # ig_01 — 표지
    compose_cover(
        photo_path=COVER,
        title_eng="BALLET",
        title_kor="발레",
        date_location="2026.05 OPEN  ·  한남동 웰니스 스튜디오",
        output_path=out_ig / "ig_01.jpg",
        cover_x_bias=0.60,
        cover_zoom=1.28,
    )

    # ig_02~06 — 본문
    story_data = [
        (P02, "BALLET  ·  2026.05 OPEN", "전문가의 1:1 교정",   "이수지 BALLET INSTRUCTOR",      False),
        (P03, "BALLET  ·  2026.05 OPEN", "최대 8인 프라이빗",   "매주 금요일 오전 10시 / 11시",  False),
        (P04, "BALLET  ·  2026.05 OPEN", "클래식 발레의 정수",  "균형 · 자세 · 우아한 움직임",   False),
        (P05, "BALLET  ·  2026.05 OPEN", "함께 완성하는 자세",  "한남동 웰니스 스튜디오",         False),
        (P06, "BALLET  ·  2026.05 OPEN", "특별한 움직임의 여정", _INQUIRY_URL, True),
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

    # ig_07 — GUIDE 카드
    compose_guide_card(output_path=out_ig / "ig_07.jpg")

    # 마스터 폴더 동기화
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
