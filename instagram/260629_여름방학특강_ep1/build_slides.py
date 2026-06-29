"""2026 여름 방학특강 Ep1 — 공간(시설)편 슬라이드 빌드 (공식 매거진 룩)

정본 구조 = compose_barre.compose_cover / compose_story 그대로.
단, compose_story 카운터(draw_counter)만 제거 — 래퍼 함수로 처리.

GM 지시 반영 (2026-06-29 재작업):
  1. 표지 = 수영장 메인.jpg (post_1 교체)
  2. 마무리 = 단색 정보띠 사진 없음 (post_7, 골프룸 중복 금지)
  3. 제목 = 설명형 문구 (한 단어 제목 금지)
  4. 슬라이드 번호(카운터) 제거
  5. 메타라인·제목·부제·풋터·칩·로고 공식 복원
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
    compose_cover,
    center_crop_fill,
    apply_bottom_gradient,
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


def _draw_chip_official(draw: ImageDraw.ImageDraw) -> None:
    """웰상단 칩 (공식 규격: 240x52, bold 28px)."""
    chip_font = load_font("bold", 28)
    chip_w, chip_h = 240, 52
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, CHIP_LABEL, chip_font, chip_x, chip_y, chip_w, chip_h)


def compose_story_no_counter(
    photo_path: Path,
    title_kor: str,
    sub_text: str,
    output_path: Path,
) -> None:
    """공식 compose_story 구조 유지, 카운터(draw_counter)만 제거.
    메타라인 · 제목 · 부제 · 풋터 · 칩 · 로고는 정본 좌표 그대로 유지."""
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.90)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=555)
    canvas = paste_logo(canvas, logo_w=130)

    draw = ImageDraw.Draw(canvas)
    _draw_chip_official(draw)
    # draw_counter 호출 제거 (커운터 없음)

    # 메타라인 (y=795, GRAY, medium 26px)
    draw.text((40, 795), META_LINE, font=load_font("medium", 26), fill=GRAY)

    # 제목 (y=860, WHITE, bold 64px)
    draw.text((40, 860), title_kor, font=load_font("bold", 64), fill=WHITE)

    # 부제 (y=958, BEIGE, semibold 30px)
    draw.text((40, 958), sub_text, font=load_font("semibold", 30), fill=BEIGE)

    # 풋터 (y=1026, BEIGE, medium 26px)
    draw.text((40, 1026), FOOTER_TEXT, font=load_font("medium", 26), fill=BEIGE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [슬라이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def compose_closing_card(output_path: Path) -> None:
    """마무리 2×2 그리드 (4장 공간 사진, 사분면 각 540×540).
    GM 지시 (2026-06-29): 네 가지 공간을 한 번에 모아 보여주는 의도적 예외.
    post_1~6 단일사진 원칙은 유지, 이 장만 예외."""
    HALF = W // 2  # 540

    # 사분면: 좌상=수영, 우상=체조(트램폴린), 좌하=스쿼시, 우하=골프
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

    # 반투명 다크 스크림 — 텍스트 가독성 확보 (y=580 이하)
    scrim_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim_overlay)
    scrim_draw.rectangle([(0, 580), (W, H)], fill=(0, 0, 0, 168))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), scrim_overlay).convert("RGB")

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_official(draw)

    # 메인 (흰색 bold 64px, 중앙 y=780)
    draw.text(
        (W // 2, 780),
        "네 가지 공간이, 한 곳에",
        font=load_font("bold", 64),
        fill=WHITE,
        anchor="mm",
    )

    # 부제 (베이지 semibold 36px, 중앙 y=878)
    draw.text(
        (W // 2, 878),
        "수영  ·  체조  ·  스쿼시  ·  골프",
        font=load_font("semibold", 36),
        fill=BEIGE,
        anchor="mm",
    )

    # 소형 정보 (회색 medium 24px, 중앙 y=952)
    draw.text(
        (W // 2, 952),
        "1:6 소수정예  ·  횟수 자율조정  ·  주차 제공",
        font=load_font("medium", 24),
        fill=GRAY,
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

    # post_1 — 표지 (compose_cover 정본)
    p1 = OUT / "post_1.jpg"
    compose_cover(
        photo_path=SRC / "수영장 메인.jpg",
        title_eng="SUMMER CAMP",
        title_kor="웰페리온 여름방학 특강이 시작되었습니다",
        date_location="6.29 ~ 8.14  ·  2019년 이전 출생 유소년",
        output_path=p1,
    )
    paths.append(p1)

    # post_2~6 — 시설 스토리 (카운터 없는 래퍼)
    stories = [
        ("3. 수영장.jpg",         "물과 친해지는 실내 수영장", "넓은 레인에서 차근차근"),
        ("체조룸(스프링매트 ).png", "안전하게 구르는 체조룸",   "스프링 매트 전용 공간"),
        ("트램폴린장.png",          "뛰며 배우는 트램폴린장",   "균형과 순발력을 한 번에"),
        ("스쿼시장.png",           "집중을 배우는 스쿼시 코트", "정식 규격 전용 코트"),
        ("골프룸.jpg",             "사계절 즐기는 실내 골프",   "날씨 걱정 없는 골프 연습실"),
    ]
    for i, (photo, title, sub) in enumerate(stories, start=2):
        p = OUT / f"post_{i}.jpg"
        compose_story_no_counter(
            photo_path=SRC / photo,
            title_kor=title,
            sub_text=sub,
            output_path=p,
        )
        paths.append(p)

    # post_7 — 마무리 단색 정보띄 (사진 없음)
    p7 = OUT / "post_7.jpg"
    compose_closing_card(output_path=p7)
    paths.append(p7)

    return paths


def build_montage(slide_paths: list[Path]) -> Path:
    """4x2 그리드 몹타주 (7장, 8번째 슬롯 바낙)."""
    COLS = 4
    TW   = W // COLS
    TH   = W // COLS
    ROWS = 2
    mont = Image.new("RGB", (TW * COLS, TH * ROWS), (20, 20, 20))
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
    print(f"  [몹타주] {out.name} ({out.stat().st_size // 1024}KB)")
    return out


def update_review_queue(montage: Path) -> str:
    """review_queue.json의 CMO-2026-06-29-SUMMER-CAMP-EP1 항목 업데이트.
    slides · preview 갱신, status=검수대기 유지. 새 항목 추가 금지."""
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
    print("=== Ep1 공간(시설)편 공식 매거진 룩 재점합 ===")
    print(f"출력: {OUT}")
    print("변경: compose_cover/story 정본 복원 · 카운터 제거 · 표지=수영장메인 · post_7=단색정보띄")

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
