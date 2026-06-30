"""공식 @wellperion 시설 종합 F1 — 사진형 슬라이드 6장 (GM 피드백 재정리).

디자인 정본 = compose_barre 의 스타일 프리미티브(center_crop_fill·apply_bottom_gradient·
paste_logo·draw_chip·draw_counter·load_font)를 그대로 import 재사용한다. 손 디자인 추측 금지
(메모리: feedback_visual_reuse_reference_generator · project_ballet_design_canonical).

전 슬라이드 = 풀사진 + 하단 그라디언트 + 좌상단 풀로고 + 우상단 WELLPERION 칩 (회사 공식계정).
구성: 표지(라운지) + 5대 시설(수영·헬스·골프·스쿼시·사우나) = 6장.
출력: instagram/260629_공식_시설_F1종합/output(인스타그램)/post_1..6.jpg + _검수_미리보기_6장.png

실행:
  python scripts\\compose_official_facility_f1.py            # 제작 + M5 등록
  python scripts\\compose_official_facility_f1.py --no-register   # 제작만(룩 확인용)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

sys.path.insert(0, str(Path(__file__).parent))
from compose_barre import (  # noqa: E402
    W, H, center_crop_fill, apply_bottom_gradient,
    paste_logo, draw_chip, draw_counter, load_font,
)
from brand_constants import BEIGE, WHITE, GRAY, PROJECT_ROOT  # noqa: E402

PHOTO_DIR = PROJECT_ROOT / "2. 브랜드_공식문서" / "시설 사진" / "web_10mb아래"
OUT_DIR = PROJECT_ROOT / "instagram" / "260629_공식_시설_F1종합" / "output(인스타그램)"
TOTAL = 6

CAPTION = (
    "한 곳에서 하루가 완성되는 곳, 웰페리온.\n\n"
    "한남동 3,000평 종합 스포츠클럽.\n"
    "25m 정규 수영장, 스쿼시 코트, 테크노짐 헬스존,\n"
    "GDR·QED 15타석 오토티업 + 골프강습룸 1타석, 사우나·스파까지.\n"
    "운동의 시작과 회복을 한 공간에서 누리세요.\n\n"
    "문의: wellperion.com/ko/inquiry\n\n"
    "#웰페리온 #한남동 #스포츠클럽 #프리미엄 #수영 #골프 #스쿼시 "
    "#헬스 #사우나 #테크노짐"
)


def _base(photo_path: Path) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=505)
    canvas = paste_logo(canvas, logo_w=130)  # LOGO_WHITE_ALPHA = 회사 풀로고
    draw = ImageDraw.Draw(canvas)
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, "WELLPERION", chip_font, chip_x, chip_y, chip_w, chip_h)
    return canvas, draw


def _save(canvas: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "JPEG", quality=93, optimize=True)
    print(f"  {out_path.name}  {out_path.stat().st_size // 1024}KB")


def compose_hero(photo_path: Path, title_lines: str, sub: str, footer: str,
                 cta: str, out_path: Path, title_size: int = 70) -> None:
    """표지/마무리 — 2줄 대제목 + 베이지 서브/CTA (카운터 없음)."""
    canvas, draw = _base(photo_path)
    title_font = load_font("bold", title_size)
    draw.multiline_text((40, 718), title_lines, font=title_font, fill=WHITE, spacing=16)
    sub_font = load_font("semibold", 30)
    draw.text((40, 928), sub, font=sub_font, fill=BEIGE)
    if cta:
        cta_font = load_font("semibold", 30)
        draw.text((40, 928), cta, font=cta_font, fill=BEIGE)
    foot_font = load_font("medium", 26)
    draw.text((40, 1000), footer, font=foot_font, fill=BEIGE)
    _save(canvas, out_path)


def compose_feature(photo_path: Path, meta: str, title: str, sub: str,
                    footer: str, current: int, out_path: Path) -> None:
    """종목 소개 슬라이드 — 메타 + 대제목 + 서브 + 풋터 + 카운터."""
    canvas, draw = _base(photo_path)
    chip_x = W - 40 - 240
    counter_font = load_font("medium", 28)
    draw_counter(draw, current, TOTAL, counter_font, chip_x, 38, 52)
    meta_font = load_font("medium", 26)
    draw.text((40, 795), meta, font=meta_font, fill=GRAY)
    title_font = load_font("bold", 64)
    draw.text((40, 858), title, font=title_font, fill=WHITE)
    sub_font = load_font("semibold", 30)
    draw.text((40, 958), sub, font=sub_font, fill=BEIGE)
    foot_font = load_font("medium", 26)
    draw.text((40, 1026), footer, font=foot_font, fill=BEIGE)
    _save(canvas, out_path)


def build_montage(slide_paths: list[Path], dest: Path,
                  cols: int = 3, cell: int = 360) -> None:
    imgs = [Image.open(p).convert("RGB") for p in slide_paths if p.exists()]
    rows = (len(imgs) + cols - 1) // cols
    gap, bg = 12, (28, 26, 24)
    mw = cols * cell + (cols + 1) * gap
    mh = rows * cell + (rows + 1) * gap
    canvas = Image.new("RGB", (mw, mh), bg)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        thumb = im.copy()
        thumb.thumbnail((cell, cell))
        x = gap + c * (cell + gap) + (cell - thumb.width) // 2
        y = gap + r * (cell + gap) + (cell - thumb.height) // 2
        canvas.paste(thumb, (x, y))
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, quality=90)
    print(f"  montage → {dest.name}")


def main() -> None:
    register = "--no-register" not in sys.argv
    photos = {
        1: PHOTO_DIR / "094A0032.jpg",  # 라운지·갤러리 — 표지
        2: PHOTO_DIR / "094A9901.jpg",  # 수영장
        3: PHOTO_DIR / "094A9977.jpg",  # 헬스장
        4: PHOTO_DIR / "094A0008.jpg",  # 골프장
        5: PHOTO_DIR / "094A9943.jpg",  # 스쿼시장
        6: PHOTO_DIR / "094A9949.jpg",  # 사우나
    }
    for n, p in photos.items():
        if not p.exists():
            print(f"[ERROR] 소스 사진 없음: {p}")
            sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=== 공식 시설 F1 종합 — 6장 합성 ===")

    META = "한남동 3,000평 종합 스포츠클럽"
    FOOT = "WELLPERION  ·  FACILITY"

    # post_1 — 표지 (라운지·갤러리)
    compose_hero(
        photos[1],
        "한 곳에서,\n하루가 완성된다",
        sub="한남동 3,000평 종합 스포츠클럽",
        footer="WELLPERION",
        cta="",
        out_path=OUT_DIR / "post_1.jpg",
        title_size=70,
    )
    # post_2~5 — 5대 시설 (수영·헬스·골프·스쿼시)
    compose_feature(photos[2], META, "수영", "25m 정규 레인",
                    FOOT, 2, OUT_DIR / "post_2.jpg")
    compose_feature(photos[3], META, "헬스", "테크노짐 프리미엄 존",
                    FOOT, 3, OUT_DIR / "post_3.jpg")
    compose_feature(photos[4], META, "골프", "GDR·QED 15타석 오토티업",
                    FOOT, 4, OUT_DIR / "post_4.jpg")
    compose_feature(photos[5], META, "스쿼시", "정식 코트",
                    FOOT, 5, OUT_DIR / "post_5.jpg")
    # post_6 — 마무리 (사우나) + CTA
    compose_hero(
        photos[6],
        "스파 · 사우나\n운동 뒤 회복까지",
        sub="",
        footer=FOOT,
        cta="문의 · wellperion.com/ko/inquiry",
        out_path=OUT_DIR / "post_6.jpg",
        title_size=60,
    )

    slides = [OUT_DIR / f"post_{i}.jpg" for i in range(1, 7)]
    montage = OUT_DIR / "_검수_미리보기_6장.png"
    build_montage(slides, montage)
    print("=== 합성 완료 ===")

    if not register:
        print("[INFO] --no-register: 등록 생략(룩 확인용).")
        return

    from publish_register import register_publish
    content_folder = PROJECT_ROOT / "instagram" / "260629_공식_시설_F1종합"
    register_publish(
        content_folder=content_folder,
        slug="260629_공식_시설_F1종합",
        montage_path=montage,
        caption=CAPTION,
        location="웰페리온 스포츠클럽",
        mentions=[],
        account="wellperion",
        slides=[p.relative_to(PROJECT_ROOT).as_posix() for p in slides],
        queue_id="CMO-2026-06-29-OFFICIAL-F1-시설종합",
        title="공식 #F1 — 시설 종합: 한 곳에서, 하루가 완성된다",
        channel="인스타그램 (wellperion)",
        send_card=False,  # 재정리본 — 텔레그램 검수카드 재발송 금지(콘텐츠당 1회 원칙)
    )


if __name__ == "__main__":
    main()
