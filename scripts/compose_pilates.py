"""필라테스 어깨 만들기 슬라이드 합성 스크립트 (바레 SSOT import)
레퍼런스: scripts/compose_barre.py / compose_ballet.py — 스타일 함수 전부 import 재사용.
필라테스 고유: 사진 경로·텍스트·프리셋(pilates). 스타일 추측 0.

캔버스: 1080x1080
구조:
  ig_01  표지   = 사진 상단 65%(듀오톤) + 검정 하단 35% 정보영역 (카운터 없음)
  ig_02~05 본문 = 전체 사진 fill + 하단 그라디언트 + 좌하단 텍스트 + 우상단 칩
  ig_06  가이드 = guideline_card.jpg 원본 복사

원본 폴더:
  instagram/Image/필라테스_최은지원장_어깨만들기(원본 이미지)/
    1. 머메이드.jpg
    2. 스완.jpg
    3. 암워크.jpg
    4. 가슴열기(회전근개운동).jpg
    5. 래터럴레이즈.jpg

출력:
  instagram/260610_필라테스_어깨만들기/output(인스타그램)/
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))

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


# ---------------------------------------------------------------------------
# 표지 (ig_01) — 바레·발레 compose_cover 동일 구조
# ---------------------------------------------------------------------------
def compose_cover(
    photo_path: Path,
    title_eng: str,
    title_kor: str,
    date_location: str,
    output_path: Path,
) -> None:
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    PHOTO_H = 700
    photo = center_crop_fill(photo_path, W, PHOTO_H)
    photo = to_duotone(photo, normalize=True)
    canvas.paste(photo, (0, 0))

    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    chip_font = load_font("bold", 24)
    chip_w, chip_h = 180, 48
    chip_x = W - 50 - chip_w
    chip_y = 60
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)

    # 영문 대제목 (베이지, 중앙)
    eng_font = load_font("bold", 58)
    draw.text((W // 2, 786), title_eng, font=eng_font, fill=BEIGE, anchor="mm")

    # 한글 부제 (흰색, 중앙) — 텍스트 너비에 따라 폰트 자동 축소
    KOR_MAX_W = W - 100  # 좌우 여백 50px
    kor_size = 38
    while kor_size > 20:
        kor_font = load_font("semibold", kor_size)
        _bb = draw.textbbox((0, 0), title_kor, font=kor_font)
        if (_bb[2] - _bb[0]) <= KOR_MAX_W:
            break
        kor_size -= 2
    draw.text((W // 2, 860), title_kor, font=kor_font, fill=WHITE, anchor="mm")

    # 베이지 얇은 분리선
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
# 스토리 슬라이드 — 바레·발레 compose_story 동일 구조
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
) -> None:
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=555)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)

    chip_font = load_font("bold", 24)
    chip_w, chip_h = 180, 48
    chip_x = W - 50 - chip_w
    chip_y = 60
    draw_chip(draw, chip_label, chip_font, chip_x, chip_y, chip_w, chip_h)

    # 메타라인 위 연한 분리선
    draw.line([(40, 772), (W - 40, 772)], fill=(150, 138, 120), width=1)

    meta_font = load_font("medium", 26)
    draw.text((40, 795), meta_line, font=meta_font, fill=BEIGE)

    title_font = load_font("bold", 64)
    draw.text((40, 860), title_kor, font=title_font, fill=WHITE)

    sub_font = load_font("medium", 30)
    sub_lines = sub_text.split("\n")
    if len(sub_lines) == 1:
        draw.text((40, 958), sub_text, font=sub_font, fill=BEIGE)
    else:
        sy = 936
        for sl in sub_lines:
            draw.text((40, sy), sl, font=sub_font, fill=BEIGE)
            sy += 40

    footer_font = load_font("bold", 26)
    draw.text((40, 1026), footer_text, font=footer_font, fill=WHITE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [{current:02d}/{total:02d}] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


# ---------------------------------------------------------------------------
# 슬라이드 세트
#
# ig_01  표지        PILATES / 어깨 만들기        카운터 없음
# ig_02  머메이드     02/06
# ig_03  스완         03/06
# ig_04  암워크       04/06
# ig_05  가슴열기     05/06
# ig_06  GUIDE 카드  카운터 없음
# (래터럴레이즈는 ig_05를 표지로 미사용 → 스토리 슬라이드 마지막으로 활용 가능하나
#  최은지원장 원본 5장 중 표지=머메이드 고정, 나머지 4장 모두 본문으로 사용)
# ---------------------------------------------------------------------------

SRC = PROJECT_ROOT / "instagram" / "Image" / "필라테스_최은지원장_어깨만들기(원본 이미지)"

COVER = SRC / "1. 머메이드.jpg"
P02   = SRC / "2. 스완.jpg"
P03   = SRC / "3. 암워크.jpg"
P04   = SRC / "4. 가슴열기(회전근개운동).jpg"
P05   = SRC / "5. 래터럴레이즈.jpg"


# ---------------------------------------------------------------------------
# 필라테스 전용 가이드 카드 — 공용 guideline_card.jpg 기반,
# "WELLNESS STUDIO / 웰니스 스튜디오" → "PILATES STUDIO / 필라테스 스튜디오" 명칭만 변경.
# 공용 SSOT(guideline_card.jpg) 원본은 절대 수정하지 않음.
# ---------------------------------------------------------------------------
def compose_guide_card_pilates(output_path: Path) -> None:
    """필라테스 포스트 전용 GUIDE 카드.
    공용 guideline_card.jpg를 베이스로:
      1) WELLNESS STUDIO 섹션 제목 → PILATES STUDIO 교체
      2) FOR MEMBERS 항목2 "웰니스 컨텐츠 최대 1:8 (Up to 8 per Class)"
         → "그룹 콘텐츠 최대 1:3 (Up to 3 per Class)" 교체
    나머지 항목·로고·CTA는 건드리지 않음.
    """
    guide_src = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card.jpg"
    if not guide_src.exists():
        raise FileNotFoundError(f"GUIDE 카드 없음: {guide_src}")

    img = Image.open(guide_src).convert("RGB")
    if img.size != (W, H):
        img = center_crop_fill(guide_src, W, H)

    draw = ImageDraw.Draw(img)

    # ── ① WELLNESS STUDIO 헤더 → PILATES STUDIO 교체 ──────────────────────
    # guideline_card.jpg 기준: WELLNESS STUDIO 제목 행 y ≈ 358~375, x ≈ 553~1035
    # 첫 항목(신발·외투 락커룸) 시작 y=388 — 패치 하단을 387로 제한해 잘림 방지
    bg_sample = img.getpixel((560, 355))
    ERASE_BOX = (553, 348, 1036, 387)
    draw.rectangle(ERASE_BOX, fill=bg_sample)

    font_section_eng = load_font("bold", 22)
    font_section_kor = load_font("medium", 22)
    ENG_COLOR = (183, 159, 138)   # BEIGE
    KOR_COLOR = (255, 255, 255)   # WHITE

    TEXT_Y = 357
    draw.text((553, TEXT_Y), "PILATES STUDIO", font=font_section_eng, fill=ENG_COLOR)
    eng_bbox = draw.textbbox((0, 0), "PILATES STUDIO", font=font_section_eng)
    eng_w = eng_bbox[2] - eng_bbox[0]
    kor_x = 553 + eng_w + 12
    draw.text((kor_x, TEXT_Y), "필라테스 스튜디오 시설 이용", font=font_section_kor, fill=KOR_COLOR)

    # ── ② FOR MEMBERS 항목2 교체 ──────────────────────────────────────────
    # 원본: "· 웰니스 컨텐츠 최대 1:8 (Up to 8 per Class)"  y≈413~425, x≈65~490
    # 교체: "· 그룹 콘텐츠 최대 1:3 (Up to 3 per Class)"
    # 형제 항목 측정값: x_min=65, color=(200,198,199), font=medium 18, draw_y=410
    ITEM2_BG = (33, 31, 32)          # 배경 단색 (측정값)
    # ITEM2_ERASE: draw_x=60 → JPEG 후 median first_x=80 (항목1 median=80 일치, 원샷 측정)
    ITEM2_ERASE = (55, 408, 500, 430)
    draw.rectangle(ITEM2_ERASE, fill=ITEM2_BG)

    font_item = load_font("medium", 18)
    ITEM_TEXT_COLOR = (200, 198, 199)  # 원본 항목 텍스트 색(측정값)
    draw.text((60, 410), "· 그룹 콘텐츠 최대 1:3 (Up to 3 per Class)", font=font_item, fill=ITEM_TEXT_COLOR)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [가이드-필라테스] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def main():
    out_ig = PROJECT_ROOT / "instagram" / "260610_[필라테스편]_민소매가_잘_어울리는_어깨만들기" / "output(인스타그램)"
    out_master = PROJECT_ROOT / "instagram" / "260610_[필라테스편]_민소매가_잘_어울리는_어깨만들기" / "output"
    out_ig.mkdir(parents=True, exist_ok=True)
    out_master.mkdir(parents=True, exist_ok=True)

    for p in [COVER, P02, P03, P04, P05]:
        if not p.exists():
            print(f"[ERROR] 소스 없음: {p}")
            sys.exit(1)

    # 총 파일: 표지1 + 본문4 + 가이드1 = 6
    TOTAL = 6

    print("=== 필라테스 어깨 만들기 슬라이드 합성 ===")
    print(f"출력(인스타): {out_ig}")

    # ig_01 — 표지
    compose_cover(
        photo_path=COVER,
        title_eng="PILATES",
        title_kor="민소매가 잘 어울리는 어깨만들기",
        date_location="최은지 원장  ·  한남동 웰페리온 스포츠클럽",
        output_path=out_ig / "ig_01.jpg",
    )

    # ig_02~05 — 동작 슬라이드
    story_data = [
        (P02, "PILATES  ·  어깨 만들기", "스완",         "등 뒤 라인을 탄탄하게"),
        (P03, "PILATES  ·  어깨 만들기", "암워크",        "팔 라인을 단단하게"),
        (P04, "PILATES  ·  어깨 만들기", "가슴 열기",     "라운드숄더 교정 · 거북목 예방"),
        (P05, "PILATES  ·  어깨 만들기", "래터럴 레이즈", "어깨 측면 라인을 또렷하게"),
    ]
    for idx, (photo, meta, title_kor, sub) in enumerate(story_data, start=2):
        compose_story(
            photo_path=photo,
            meta_line=meta,
            title_kor=title_kor,
            sub_text=sub,
            footer_text="WELLPERION  ·  PILATES",
            current=idx,
            total=TOTAL,
            output_path=out_ig / f"ig_{idx:02d}.jpg",
        )

    # ig_06 — GUIDE 카드 (필라테스 전용: WELLNESS STUDIO → PILATES STUDIO)
    compose_guide_card_pilates(output_path=out_ig / "ig_06.jpg")

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
