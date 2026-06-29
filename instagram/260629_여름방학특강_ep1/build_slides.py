"""2026 여름 방학특강 Ep1 — 공간(시설)편 슬라이드 빌드

GM 지시 2차 결정 (2026-06-29 deep-interview 확정):
  1. 본문 post_2~6 = 65/35 + 베이지 중간선 + 다크 정보영역 (compose_story_banded)
  2. 우상단 WELLPERION 칩 미니멀 축소 (150×38, font 22, 전 슬라이드)
  3. 슬라이드 번호(카운터) 없음 유지
  4. 종목 제목/부제 가치+구체 강화 (일반지식 범위, 과장 금지)
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
OUT     = ROOT / "instagram" / "260629_여름방학특강_ep1" / "output(인스타그램)"
GUIDE   = ROOT / "3. 웰페리온 가이드"
REVIEW  = GUIDE / "cmo" / "review"
QUEUE_F = REVIEW / "review_queue.json"

TOTAL       = 7
CHIP_LABEL  = "WELLPERION"
FOOTER_TEXT = "WELLPERION  ·  스포츠클럽"
META_LINE   = "여름 방학특강  ·  한남동 웰페리온"

# 미니멀 칩 규격 (GM 지시: F1 수준)
CHIP_W_MINI    = 150
CHIP_H_MINI    = 38
CHIP_FONT_MINI = 22

CAPTION = """웰페리온 여름방학 특강이 시작되었습니다.

6월 29일 ~ 8월 14일
2019년 이전 출생 유소년 대상

먼저, 아이들이 머는 공간을 소개합니다.
실내 수영장, 체조룸, 트램폴린장, 스쿼시 코트, 실내 골프 연습실.
사계절 날씨 걱정 없이, 한 곳에서.

수영 · 체조 · 스쿼시 · 골프
1:6 소수정예 · 횟수 자율조정 · 주차 제공

궁금하신 점은 프로필 링크로 문의해 주세요.

#한남동수영 #한남동골프 #유소년스포츠 #주니어스포츠 #여름방학특강 #키즈스포츠 #수영 #체조 #스쿼시 #골프 #스포츠클럽 #웰페리온 #WELLPERION"""

REQUIRED_PHOTOS = [
    "수영장 메인.jpg",
    "3. 수영장.jpg",
    "체조룸(스프링매트 ).png",
    "트램폴린장.png",
    "스쿼시장.png",
    "골프룸.jpg",
]


def verify_sources() -> None:
    missing = [f for f in REQUIRED_PHOTOS if not (SRC / f).exists()]
    if missing:
        print(f"[ERROR] 원본 누락: {missing}")
        raise SystemExit(1)
    print(f"  원본 사진 {len(REQUIRED_PHOTOS)}장 확인 완료")


def _draw_chip_mini(draw: ImageDraw.ImageDraw) -> None:
    """미니멀 칩 — 전 슬라이드 공통 (GM 지시: F1 수준)."""
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
    """표지 — compose_cover 정본 구조 + 미니 칩 적용."""
    PHOTO_H = 700
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    photo = center_crop_fill(photo_path, W, PHOTO_H)
    photo = to_duotone(photo, normalize=True)
    canvas.paste(photo, (0, 0))

    # 베이지 분리선 (compose_cover 동일 규격)
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=115)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_mini(draw)

    # 정보영역 텍스트 — compose_cover 원본 좌표 유지
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
    """본문 슬라이드 65/35 + 베이지 중간선 + 다크 정보영역 (GM 지시 2차 확정).

    - 상단 65% (y=0~700): 컬러 사진 center_crop_fill
    - y≈701: 베이지 분리선 (SEP_LINE, compose_cover 동일)
    - 하단 35% (y=700~1080): BLACK_BG 정보영역
    - 텍스트: 메타라인 → 제목(흰색 bold) → 부제(베이지) → 풋터(베이지 작게)
    """
    PHOTO_H = 700
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    # 상단 65% 컬러 사진 (듀오톤 없음)
    photo = center_crop_fill(photo_path, W, PHOTO_H)
    canvas.paste(photo, (0, 0))

    # 베이지 분리선
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    canvas = paste_logo(canvas, logo_w=115)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_mini(draw)

    # 정보영역 텍스트 (y=700~1080, 좌측 40px 정렬)
    draw.text((40, 718),  META_LINE,   font=load_font("medium",   24), fill=GRAY)
    draw.text((40, 760),  title_kor,   font=load_font("bold",     54), fill=WHITE)
    draw.text((40, 840),  sub_text,    font=load_font("semibold", 27), fill=BEIGE)
    draw.text((40, 1040), FOOTER_TEXT, font=load_font("medium",   22), fill=BEIGE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [슬라이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def compose_closing_card(output_path: Path) -> None:
    """마무리 2×2 그리드 (4장 공간 사진). 칩 미니멀 적용."""
    HALF = W // 2  # 540

    grid_photos = [
        (SRC / "3. 수영장.jpg",  0,    0),
        (SRC / "트램폴린장.png", HALF, 0),
        (SRC / "스쿼시장.png",   0,    HALF),
        (SRC / "골프룸.jpg",     HALF, HALF),
    ]

    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    for src_path, x, y in grid_photos:
        tile = center_crop_fill(src_path, HALF, HALF)
        tile = ImageEnhance.Brightness(tile).enhance(0.85)
        canvas.paste(tile, (x, y))

    # 정중앙 반투명 띠 — 두 줄 텍스트 수용, 4장 모두 식별 가능
    band_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(band_overlay)
    band_draw.rectangle([(0, 448), (W, 632)], fill=(0, 0, 0, 150))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), band_overlay).convert("RGB")

    canvas = paste_logo(canvas, logo_w=115)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_mini(draw)

    draw.multiline_text(
        (W // 2, 502),
        "이 여름,\n네 가지 도전이 시작됩니다",
        font=load_font("bold", 54),
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=8,
    )
    draw.text(
        (W // 2, 593),
        "수영  ·  체조  ·  스쿼시  ·  골프",
        font=load_font("semibold", 36),
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

    # post_1 — 표지 (미니 칩 적용)
    p1 = OUT / "post_1.jpg"
    _compose_cover_local(
        photo_path=SRC / "수영장 메인.jpg",
        title_eng="SUMMER CAMP",
        title_kor="웰페리온 여름방학 특강이 시작되었습니다",
        date_location="6.29 ~ 8.14  ·  2019년 이전 출생 유소년",
        output_path=p1,
    )
    paths.append(p1)

    # post_2~6 — 65/35 종목 슬라이드 (가치+구체 강화, 일반지식 범위)
    stories = [
        ("3. 수영장.jpg",          "물과 친해지는 첫 영법",       "자유형·배영 기초부터 물 적응·체력까지"),
        ("체조룸(스프링매트 ).png",  "구르고 매달리며 키우는 균형감", "기본 동작·유연성, 그리고 자신감"),
        ("트램폴린장.png",           "뛰며 익히는 공중 감각",        "점프 균형과 순발력을 한 번에"),
        ("스쿼시장.png",            "랠리로 기르는 순발력",          "라켓·룰 기초부터 판단력·집중까지"),
        ("골프룸.jpg",              "스윙으로 배우는 집중과 매너",   "그립·스윙·퍼팅, 그리고 코트 예절"),
    ]
    for i, (photo, title, sub) in enumerate(stories, start=2):
        p = OUT / f"post_{i}.jpg"
        compose_story_banded(
            photo_path=SRC / photo,
            title_kor=title,
            sub_text=sub,
            output_path=p,
        )
        paths.append(p)

    # post_7 — 마무리 그리드 (칩 미니멀 적용)
    p7 = OUT / "post_7.jpg"
    compose_closing_card(output_path=p7)
    paths.append(p7)

    return paths


def build_montage(slide_paths: list[Path]) -> Path:
    """4×2 그리드 몽타주 (7장, 8번째 슬롯 빈칸)."""
    COLS = 4
    TW   = W // COLS
    TH   = W // COLS
    mont = Image.new("RGB", (TW * COLS, TH * 2), (20, 20, 20))
    for i, p in enumerate(slide_paths):
        if not p.exists():
            continue
        thumb = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
        row, col = divmod(i, COLS)
        mont.paste(thumb, (col * TW, row * TH))

    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    out = OUT / "_검수_미리보기_7장.png"
    mont.save(out, "PNG", optimize=True)
    print(f"  [몽타주] {out.name} ({out.stat().st_size // 1024}KB)")
    return out


def update_review_queue(montage: Path) -> str:
    """review_queue.json 의 CMO-2026-06-29-SUMMER-CAMP-EP1 항목 갱신.
    slides·preview 업데이트, status=검수대기 유지. 새 항목 추가 금지."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    prev_name = f"260629_여름방학특강_ep1_preview_{ts}.png"
    prev_dest = REVIEW / prev_name
    shutil.copy2(montage, prev_dest)
    print(f"  [preview] {prev_dest.name} 복사 완료")

    slides_list = [
        f"instagram/260629_여름방학특강_ep1/output(인스타그램)/post_{i}.jpg"
        for i in range(1, TOTAL + 1)
    ]
    prev_rel = f"cmo/review/{prev_name}"

    data = json.loads(QUEUE_F.read_text(encoding="utf-8"))
    updated = False
    for item in data:
        if item.get("id") == "CMO-2026-06-29-SUMMER-CAMP-EP1":
            item["title"]   = "2026 여름 방학특강 Ep1 공간(시설)편"
            item["slides"]  = slides_list
            item["caption"] = CAPTION
            item["preview"] = prev_rel
            item["status"]  = "검수대기"
            updated = True
            break
    if not updated:
        raise RuntimeError("review_queue.json에서 CMO-2026-06-29-SUMMER-CAMP-EP1 항목을 찾을 수 없습니다.")

    QUEUE_F.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  [queue] 업데이트 완료 — slides={len(slides_list)}, preview={prev_rel}")
    return prev_rel


def send_review_card() -> None:
    """이전 카드 삭제 후 수정본 검수 카드 재발송."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "send_review_card.py"),
            "--id", "CMO-2026-06-29-SUMMER-CAMP-EP1",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        print("  [텔레그램] 검수 카드 재발송 완료")
    else:
        print(f"  [텔레그램] 오류: {result.stderr.strip()}")


def main() -> None:
    print("=== Ep1 공간(시설)편 2차 재정합 (deep-interview 확정) ===")
    print(f"출력: {OUT}")
    print("변경: 65/35+중간선 본문 / 미니 칩 / 종목 내용 강화")

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
