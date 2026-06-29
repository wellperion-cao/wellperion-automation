"""2026 여름 방학특강 Ep1 — 공간(시설)편 슬라이드 빌드 (미니멀 재제작)

GM 피드백 반영 (2026-06-29):
  1. 슬라이드 번호(카운터) 완전 제거
  2. 글씨 축소·여백 강조 (제목 64→40, 부제 30→24, 메타라인 제거)
  3. 시설 사진 5장만 사용 (강습 사진 제외)
  4. 표지 = 한글 시작 문구 주연
  5. 총 7장 구성
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
    center_crop_fill,
    apply_bottom_gradient,
    paste_logo,
    draw_chip,
    load_font,
    to_duotone,
    W,
    H,
)
from brand_constants import BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE

ROOT    = Path(r"C:\Users\jjky0\welperion-automation")
SRC     = ROOT / "instagram" / "Image" / "방학특강(원본 이미지)"
OUT     = ROOT / "instagram" / "260629_여름방학특강_ep1" / "output(인스타그램)"
GUIDE   = ROOT / "3. 웰페리온 가이드"
REVIEW  = GUIDE / "cmo" / "review"
QUEUE_F = REVIEW / "review_queue.json"

TOTAL       = 7
CHIP_LABEL  = "WELLPERION"
FOOTER_TEXT = "WELLPERION  ·  스포츠클럽"

CAPTION = """웰페리온 여름방학 특강이 시작되었습니다.

6월 22일 ~ 8월 14일
2019년 이전 출생 유소년 대상

먼저, 아이들이 머무를 공간을 소개합니다.
실내 수영장, 체조룸, 트램폴린장, 스쿼시 코트, 실내 골프 연습실.
사계절 날씨 걱정 없이, 한 곳에서.

수영 · 체조 · 스쿼시 · 골프
1:6 소수정예 · 횟수 자율조정 · 주차 제공

궁금하신 점은 프로필 링크로 문의해 주세요.

#한남동수영 #한남동골프 #유소년스포츠 #주니어스포츠 #여름방학특강 #키즈스포츠 #수영 #체조 #스쿼시 #골프 #스포츠클럽 #웰페리온 #WELLPERION"""

# 슬라이드 스펙 — 시설 사진 5장만, 강습 사진 제외
SLIDES_SPEC = [
    {
        "type":     "cover",
        "photo":    "3. 수영장.jpg",
        "main_kor": "웰페리온 여름방학 특강이\n시작되었습니다",
        "label_eng": "2026 SUMMER CAMP",
        "date_line": "6.22 ~ 8.14  ·  유소년",
    },
    {
        "type":  "story",
        "photo": "3. 수영장.jpg",
        "title": "실내 수영장",
        "sub":   "물과 친해지는 넓은 레인",
    },
    {
        "type":  "story",
        "photo": "체조룸(스프링매트 ).png",
        "title": "체조룸",
        "sub":   "스프링 매트 위 안전한 움직임",
    },
    {
        "type":  "story",
        "photo": "트램폴린장.png",
        "title": "트램폴린장",
        "sub":   "뛰며 키우는 균형과 순발력",
    },
    {
        "type":  "story",
        "photo": "스쿼시장.png",
        "title": "스쿼시 코트",
        "sub":   "정식 규격 전용 코트",
    },
    {
        "type":  "story",
        "photo": "골프룸.jpg",
        "title": "실내 골프 연습실",
        "sub":   "사계절 날씨 걱정 없이",
    },
    {
        "type":  "closing",
        "photo": "골프룸.jpg",
        "title": "네 가지 공간이, 한 곳에",
        "sub":   "수영 · 체조 · 스쿼시 · 골프 · 1:6 소수정예",
    },
]

REQUIRED_PHOTOS = [
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
    print(f"  시설 사진 {len(REQUIRED_PHOTOS)}장 확인 완료 (강습 사진 제외)")


def _draw_chip_small(draw: ImageDraw.ImageDraw) -> None:
    """우상단 칩 (카운터 없음)."""
    chip_font = load_font("bold", 26)
    chip_w, chip_h = 220, 48
    chip_x = W - 40 - chip_w
    chip_y = 38
    draw_chip(draw, CHIP_LABEL, chip_font, chip_x, chip_y, chip_w, chip_h)


def compose_minimal_cover(
    photo_path: Path,
    main_kor: str,
    label_eng: str,
    date_line: str,
    output_path: Path,
) -> None:
    """미니멀 표지 — 한글 시작 문구 주연, 영문 소형 라벨, 카운터 없음."""
    canvas = Image.new("RGB", (W, H), BLACK_BG)

    # 상단 65% 사진 (듀오톤)
    photo = center_crop_fill(photo_path, W, 700)
    photo = to_duotone(photo, normalize=True)
    canvas.paste(photo, (0, 0))

    # 분리선
    draw_base = ImageDraw.Draw(canvas)
    draw_base.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)

    # 로고 좌상단
    canvas = paste_logo(canvas, logo_w=130)

    draw = ImageDraw.Draw(canvas)
    _draw_chip_small(draw)

    # 영문 소형 라벨 (베이지, 22px, 중앙)
    draw.text((W // 2, 742), label_eng,
              font=load_font("medium", 22), fill=BEIGE, anchor="mm")

    # 라벨·본문 분리선 (베이지, 25px 너비)
    draw.rectangle([(W // 2 - 20, 758), (W // 2 + 20, 760)], fill=BEIGE)

    # 한글 메인 문구 (흰색 bold, 44px, 중앙, 줄바꿈 지원)
    title_font = load_font("bold", 44)
    lines = main_kor.split("\n")
    y_start = 818
    line_gap = 62
    for i, line in enumerate(lines):
        draw.text((W // 2, y_start + i * line_gap), line,
                  font=title_font, fill=WHITE, anchor="mm")

    # 하단 날짜 (회색, 20px, 중앙)
    draw.text((W // 2, 960), date_line,
              font=load_font("medium", 20), fill=GRAY, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def compose_minimal_story(
    photo_path: Path,
    title_kor: str,
    sub_text: str,
    output_path: Path,
) -> None:
    """미니멀 스토리/닫음 — 카운터·메타라인 없음, 제목 40px, 부제 24px, 여백 충분."""
    canvas = center_crop_fill(photo_path, W, H)
    canvas = ImageEnhance.Brightness(canvas).enhance(0.88)
    canvas = apply_bottom_gradient(canvas, gradient_start_y=545)

    canvas = paste_logo(canvas, logo_w=130)
    draw = ImageDraw.Draw(canvas)
    _draw_chip_small(draw)

    # 제목 (흰색 bold 40px)
    draw.text((40, 846), title_kor,
              font=load_font("bold", 40), fill=WHITE)

    # 부제 (베이지 semibold 24px)
    draw.text((40, 908), sub_text,
              font=load_font("semibold", 24), fill=BEIGE)

    # 풋터 (베이지 medium 22px)
    draw.text((40, 1036), FOOTER_TEXT,
              font=load_font("medium", 22), fill=BEIGE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [슬라이드] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def build_slides() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    # 기존 슬라이드 정리
    for old in OUT.glob("post_*.jpg"):
        old.unlink()

    paths: list[Path] = []
    for idx, spec in enumerate(SLIDES_SPEC, start=1):
        out_path = OUT / f"post_{idx}.jpg"
        stype = spec["type"]

        if stype == "cover":
            compose_minimal_cover(
                photo_path=SRC / spec["photo"],
                main_kor=spec["main_kor"],
                label_eng=spec["label_eng"],
                date_line=spec["date_line"],
                output_path=out_path,
            )
        else:  # story or closing
            compose_minimal_story(
                photo_path=SRC / spec["photo"],
                title_kor=spec["title"],
                sub_text=spec["sub"],
                output_path=out_path,
            )
        paths.append(out_path)
    return paths


def build_montage(slide_paths: list[Path]) -> Path:
    """4×2 그리드 몽타주 (7장, 8번째 슬롯 블랙)."""
    COLS = 4
    TW   = W // COLS   # 270
    TH   = W // COLS   # 270
    ROWS = 2
    mont = Image.new("RGB", (TW * COLS, TH * ROWS), (20, 20, 20))
    for i, p in enumerate(slide_paths):
        if not p.exists():
            continue
        thumb = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
        row, col = divmod(i, COLS)
        mont.paste(thumb, (col * TW, row * TH))

    # 구 몽타주 파일 정리
    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    out = OUT / "_검수_미리보기_7장.png"
    mont.save(out, "PNG", optimize=True)
    print(f"  [몽타주] {out.name} ({out.stat().st_size // 1024}KB)")
    return out


def update_review_queue(montage: Path) -> str:
    """review_queue.json의 CMO-2026-06-29-SUMMER-CAMP-EP1 항목 업데이트.
    title·slides·caption·preview 갱신, status=검수대기 유지. 새 항목 추가 금지."""
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
    print(f"  [queue] 업데이트 완료 — title=Ep1 공간(시설)편, slides={len(slides_list)}, preview={prev_rel}")
    return prev_rel


def send_review_card() -> None:
    """이전 카드 삭제 후 수정본 검수 카드 재발송 (send_review_card.py 자동 처리)."""
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
    print("=== Ep1 공간(시설)편 미니멀 재제작 ===")
    print(f"출력: {OUT}")
    print("변경: 카운터 제거 / 폰트 축소(40/24) / 시설 5장 단일사진 / 7장 구성")

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
