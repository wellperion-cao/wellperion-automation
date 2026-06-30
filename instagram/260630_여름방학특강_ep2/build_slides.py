"""2026 여름 방학특강 Ep2 — 강습(무엇을 배우나)편 슬라이드 빌드

GM 결정 (2026-06-30):
  - Ep1=공간(시설)편 → Ep2='무엇을 배우나' 종목별 강습 매력 심화편
  - 소스 = 실제 강습 사진 4종(수영·체조·스쿼시·골프 강습)
  - 가격(회당 52,250원)·정확한 시간표 = 비노출 → '프로필 링크 문의' 유도
엔진·룩 = Ep1 정본 계승: 사진형(compose_barre) · 본문 65/35+베이지 중간선 · 미니멀 칩.
종목 제목/부제 = 가치+구체(일반지식 범위, 과장 금지).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

SCRIPTS = Path(r"C:\Users\jjky0\welperion-automation\scripts")
sys.path.insert(0, str(SCRIPTS))

from compose_barre import (
    to_duotone,
    center_crop_fill,
    paste_logo,
    draw_chip,
    load_font,
    W,
    H,
)
from brand_constants import BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE, CHIP_BEIGE

ROOT    = Path(r"C:\Users\jjky0\welperion-automation")
SRC     = ROOT / "instagram" / "Image" / "방학특강(원본 이미지)"
OUT     = ROOT / "instagram" / "260630_여름방학특강_ep2" / "output(인스타그램)"
GUIDE   = ROOT / "3. 웰페리온 가이드"
REVIEW  = GUIDE / "cmo" / "review"
QUEUE_F = REVIEW / "review_queue.json"

REVIEW_ID = "CMO-2026-06-30-SUMMER-CAMP-EP2"
TITLE     = "2026 여름 방학특강 Ep2 강습(무엇을 배우나)편"

TOTAL       = 6
CHIP_LABEL  = "WELLPERION"
FOOTER_TEXT = "WELLPERION  ·  스포츠클럽"
META_LINE   = "여름 방학특강  ·  한남동 웰페리온"

# 미니멀 칩 규격 (Ep1 동일)
CHIP_W_MINI    = 150
CHIP_H_MINI    = 38
CHIP_FONT_MINI = 22

CAPTION = """이번 여름, 아이는 무엇을 배울까요.

6월 29일 ~ 8월 14일
2019년 이전 출생 유소년

수영, 체조, 스쿼시, 골프.
물과 친해지고, 구르고 매달리고, 랠리를 주고받고, 스윙을 배웁니다.
종목마다 기초부터 차근차근, 1:6 소수정예로.

· 1:6 소수정예 코칭
· 횟수 자율조정 · 주차 제공

자세한 시간표·요금은 프로필 링크로 문의해 주세요.

#한남동수영 #한남동골프 #유소년스포츠 #주니어스포츠 #여름방학특강 #키즈스포츠 #수영 #체조 #스쿼시 #골프 #스포츠클럽 #웰페리온 #WELLPERION"""

# (파일명, 제목, 부제) — 실제 강습 사진 4종
STORIES = [
    ("방학 수영 레슨.png",        "물과 친해지는 강습",        "자유형·배영 기초와 물 적응을 단계별로"),
    ("방학 유소년 체조 강습.png",  "구르고 매달리는 기본기",     "유연성·균형감, 그리고 해냈다는 자신감"),
    ("스쿼시 강습.jpg",          "랠리로 키우는 순발력",       "라켓·룰 기초부터 판단력·집중까지"),
    ("골프 강습.jpg",            "스윙으로 배우는 집중과 매너",  "그립·스윙·퍼팅, 그리고 기본 매너"),
]

COVER_PHOTO = "방학 수영 레슨.png"

REQUIRED_PHOTOS = [COVER_PHOTO] + [s[0] for s in STORIES]


def verify_sources() -> None:
    missing = [f for f in REQUIRED_PHOTOS if not (SRC / f).exists()]
    if missing:
        print(f"[ERROR] 원본 누락: {missing}")
        raise SystemExit(1)
    print(f"  원본 강습 사진 확인 완료 ({len(set(REQUIRED_PHOTOS))}종)")


def _draw_chip_mini(draw: ImageDraw.ImageDraw) -> None:
    chip_font = load_font("bold", CHIP_FONT_MINI)
    chip_x = W - 40 - CHIP_W_MINI
    chip_y = 42
    draw_chip(draw, CHIP_LABEL, chip_font, chip_x, chip_y, CHIP_W_MINI, CHIP_H_MINI)


def _compose_cover_local(
    photo_path: Path,
    title_eng: str,
    title_kor: str,
    date_location: str,
    output_path: Path,
) -> None:
    """표지 — Ep1 정본 구조 + 미니 칩."""
    PHOTO_H = 700
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    photo = center_crop_fill(photo_path, W, PHOTO_H)
    photo = to_duotone(photo, normalize=True)
    canvas.paste(photo, (0, 0))

    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=115)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_mini(draw)

    draw.text((W // 2, 789), title_kor,     font=load_font("semibold", 38), fill=BEIGE, anchor="mm")
    draw.text((W // 2, 859), title_eng,     font=load_font("bold",     88), fill=WHITE, anchor="mm")
    sub_line_y = 920
    draw.rectangle([(W // 2 - 30, sub_line_y), (W // 2 + 30, sub_line_y + 2)], fill=BEIGE)
    draw.text((W // 2, 962), date_location, font=load_font("medium",   26), fill=GRAY,  anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def compose_story_banded(
    photo_path: Path,
    title_kor: str,
    sub_text: str,
    output_path: Path,
) -> None:
    """본문 65/35 + 베이지 중간선 + 다크 정보영역 (Ep1 정본)."""
    PHOTO_H = 700
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    photo = center_crop_fill(photo_path, W, PHOTO_H)
    canvas.paste(photo, (0, 0))

    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=115)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_mini(draw)

    draw.text((40, 718),  META_LINE,   font=load_font("medium",   24), fill=GRAY)
    draw.text((40, 760),  title_kor,   font=load_font("bold",     54), fill=WHITE)
    draw.text((40, 840),  sub_text,    font=load_font("semibold", 27), fill=BEIGE)
    draw.text((40, 1040), FOOTER_TEXT, font=load_font("medium",   22), fill=BEIGE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [슬라이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def compose_closing_card(output_path: Path) -> None:
    """마무리 2×2 그리드 (4 강습 사진) + 1:6 코칭·문의 유도. 칩 미니멀."""
    HALF = W // 2

    grid_photos = [
        (SRC / "방학 수영 레슨.png",        0,    0),
        (SRC / "방학 유소년 체조 강습.png",  HALF, 0),
        (SRC / "스쿼시 강습.jpg",          0,    HALF),
        (SRC / "골프 강습.jpg",            HALF, HALF),
    ]

    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    for src_path, x, y in grid_photos:
        tile = center_crop_fill(src_path, HALF, HALF)
        tile = ImageEnhance.Brightness(tile).enhance(0.85)
        canvas.paste(tile, (x, y))

    band_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(band_overlay)
    band_draw.rectangle([(0, 448), (W, 632)], fill=(0, 0, 0, 150))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), band_overlay).convert("RGB")

    canvas = paste_logo(canvas, logo_w=115)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_mini(draw)

    draw.multiline_text(
        (W // 2, 502),
        "한 명 한 명,\n눈을 맞추는 1:6 코칭",
        font=load_font("bold", 54),
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=8,
    )
    draw.text(
        (W // 2, 593),
        "자세한 안내는 프로필 링크로 문의",
        font=load_font("semibold", 30),
        fill=BEIGE,
        anchor="mm",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [마무리] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def build_slides() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("post_*.jpg"):
        old.unlink()

    paths: list[Path] = []

    # post_1 — 표지
    p1 = OUT / "post_1.jpg"
    _compose_cover_local(
        photo_path=SRC / COVER_PHOTO,
        title_eng="SUMMER CAMP",
        title_kor="이 여름, 무엇을 배우나",
        date_location="6.29 ~ 8.14  ·  2019년 이전 출생 유소년",
        output_path=p1,
    )
    paths.append(p1)

    # post_2~5 — 종목별 강습 (65/35)
    for i, (photo, title, sub) in enumerate(STORIES, start=2):
        p = OUT / f"post_{i}.jpg"
        compose_story_banded(
            photo_path=SRC / photo,
            title_kor=title,
            sub_text=sub,
            output_path=p,
        )
        paths.append(p)

    # post_6 — 마무리 그리드
    p6 = OUT / f"post_{TOTAL}.jpg"
    compose_closing_card(output_path=p6)
    paths.append(p6)

    return paths


def build_montage(slide_paths: list[Path]) -> Path:
    """3×2 그리드 몽타주 (6장)."""
    COLS = 3
    TW   = W // COLS
    TH   = W // COLS
    rows = (len(slide_paths) + COLS - 1) // COLS
    mont = Image.new("RGB", (TW * COLS, TH * rows), (20, 20, 20))
    for i, p in enumerate(slide_paths):
        if not p.exists():
            continue
        thumb = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
        row, col = divmod(i, COLS)
        mont.paste(thumb, (col * TW, row * TH))

    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    out = OUT / f"_검수_미리보기_{TOTAL}장.png"
    mont.save(out, "PNG", optimize=True)
    print(f"  [몽타주] {out.name} ({out.stat().st_size // 1024}KB)")
    return out


def update_review_queue(montage: Path) -> str:
    """review_queue.json EP2 항목 insert-or-update. status=검수대기. 발행완료 금지."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    prev_name = f"260630_여름방학특강_ep2_preview_{ts}.png"
    prev_dest = REVIEW / prev_name
    shutil.copy2(montage, prev_dest)
    print(f"  [preview] {prev_dest.name} 복사 완료")

    slides_list = [
        f"instagram/260630_여름방학특강_ep2/output(인스타그램)/post_{i}.jpg"
        for i in range(1, TOTAL + 1)
    ]
    prev_rel = f"cmo/review/{prev_name}"

    data = json.loads(QUEUE_F.read_text(encoding="utf-8"))
    entry = {
        "id":       REVIEW_ID,
        "title":    TITLE,
        "channel":  "인스타그램 (wellperion 공식)",
        "account":  "wellperion",
        "folder":   "instagram/260630_여름방학특강_ep2",
        "slides":   slides_list,
        "caption":  CAPTION,
        "location": "웰페리온 스포츠클럽",
        "status":   "검수대기",
        "preview":  prev_rel,
    }

    found = False
    for item in data:
        if item.get("id") == REVIEW_ID:
            item.update(entry)
            found = True
            break
    if not found:
        data.insert(0, entry)

    QUEUE_F.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  [queue] {'갱신' if found else '신규추가'} — slides={len(slides_list)}, preview={prev_rel}")
    return prev_rel


def send_review_card() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "send_review_card.py"), "--id", REVIEW_ID],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        print("  [텔레그램] 검수 카드 발송 완료")
    else:
        print(f"  [텔레그램] 오류: {result.stderr.strip()}")


def main() -> None:
    print("=== Ep2 강습(무엇을 배우나)편 빌드 ===")
    print(f"출력: {OUT}")

    verify_sources()
    slides = build_slides()
    assert len(slides) == TOTAL, f"슬라이드 수 불일치: {len(slides)}"

    montage = build_montage(slides)
    preview_rel = update_review_queue(montage)
    send_review_card()

    print(f"\n=== 빌드 완료 ===")
    print(f"  슬라이드 {TOTAL}장 / 미리보기: {preview_rel}")


if __name__ == "__main__":
    main()
