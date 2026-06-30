"""2026 여름 방학특강 Ep3 — 강사·운영진 신뢰편 슬라이드 빌드

GM 결정 (2026-06-30): Ep1=공간 / Ep2=강습(무엇을 배우나) → Ep3=강사·운영진 신뢰편.
준비된 강사 프로필월(완성 카드) 활용 — 방학특강 4종목 팀장(수영·체조·스쿼시·골프).
'누가 가르치나'로 학부모 안심→문의. 가격·시간표 비노출·프로필 문의 유도(Ep2 동일 정책).
엔진=Ep2 계승(표지·마무리=compose_barre / 강사 슬라이드=완성카드 흰 캔버스 피팅).
사실성: 카드에 실재하는 자격만 캡션에 인용(과장 금지).
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(r"C:\Users\jjky0\welperion-automation\scripts")
sys.path.insert(0, str(SCRIPTS))

from compose_barre import (
    to_duotone, center_crop_fill, paste_logo, draw_chip, load_font, W, H,
)
from brand_constants import BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE

ROOT     = Path(r"C:\Users\jjky0\welperion-automation")
CARDS    = ROOT / "2. 브랜드_공식문서" / "03_파트너강사 프로필월"
SCENES   = ROOT / "instagram" / "Image" / "방학특강(원본 이미지)"
OUT      = ROOT / "instagram" / "260701_여름방학특강_ep3" / "output(인스타그램)"
GUIDE    = ROOT / "3. 웰페리온 가이드"
REVIEW   = GUIDE / "cmo" / "review"
QUEUE_F  = REVIEW / "review_queue.json"

REVIEW_ID = "CMO-2026-07-01-SUMMER-CAMP-EP3"
TITLE     = "2026 여름 방학특강 Ep3 강사·운영진 신뢰편"
TOTAL     = 6
DARK      = (38, 38, 40)

CHIP_LABEL, CHIP_W, CHIP_H, CHIP_F = "WELLPERION", 150, 38, 22
META_LINE = "여름 방학특강  ·  한남동 웰페리온"
FOOTER    = "WELLPERION  ·  스포츠클럽"

# (카드파일, 종목 국문, 종목 영문)
COACHES = [
    ("수영 박민서 팀장 프로필.jpg", "수영", "SWIMMING"),
    ("체조 이형주 팀장 프로필.jpg", "체조", "GYMNASTICS"),
    ("스쿼시 이상훈 팀장 프로필.png", "스쿼시", "SQUASH"),
    ("골프 최현준 팀장.png", "골프", "GOLF"),
]
COVER_SCENE = "방학 수영 레슨.png"

CAPTION = """믿고 맡기는 이유 — 누가 가르치나.

이번 여름방학 특강을 이끄는 종목별 전문 코치진을 소개합니다.

· 수영 박민서 팀장 — 생활스포츠지도사·수상인명구조원
· 체조 이형주 팀장
· 스쿼시 이상훈 팀장
· 골프 최현준 팀장 — KPGA 프로

기초부터 차근차근, 1:6 소수정예로 한 명 한 명 눈을 맞춥니다.
처음이어도 안심하고 맡기셔도 좋습니다.

· 6월 29일 ~ 8월 14일 / 2019년 이전 출생 유소년
· 1:6 소수정예 · 횟수 자율조정 · 주차 제공

자세한 시간표·요금은 프로필 링크로 문의해 주세요.

#여름방학특강 #유소년스포츠 #한남동수영 #한남동골프 #키즈스포츠 #전문코치 #스포츠클럽 #웰페리온 #WELLPERION"""


def verify_sources() -> None:
    missing = [c[0] for c in COACHES if not (CARDS / c[0]).exists()]
    if not (SCENES / COVER_SCENE).exists():
        missing.append(COVER_SCENE)
    if missing:
        print(f"[ERROR] 원본 누락: {missing}")
        raise SystemExit(1)
    print(f"  강사 카드 4종 + 표지 사진 확인 완료")


def _chip(draw):
    draw_chip(draw, CHIP_LABEL, load_font("bold", CHIP_F), W - 40 - CHIP_W, 42, CHIP_W, CHIP_H)


def compose_cover(output_path: Path) -> None:
    PHOTO_H = 700
    canvas = Image.new("RGB", (W, H), BLACK_BG)
    photo = to_duotone(center_crop_fill(SCENES / COVER_SCENE, W, PHOTO_H), normalize=True)
    canvas.paste(photo, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)
    canvas = paste_logo(canvas, logo_w=115)
    d = ImageDraw.Draw(canvas)
    _chip(d)
    d.text((W // 2, 789), "누가 가르치나요", font=load_font("semibold", 38), fill=BEIGE, anchor="mm")
    d.text((W // 2, 859), "OUR COACHES", font=load_font("bold", 74), fill=WHITE, anchor="mm")
    d.rectangle([(W // 2 - 30, 920), (W // 2 + 30, 922)], fill=BEIGE)
    d.text((W // 2, 962), "여름 방학특강 운영 강사  ·  한남동 웰페리온", font=load_font("medium", 24), fill=GRAY, anchor="mm")
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name}")


def compose_coach(card_file: str, jong_kr: str, jong_en: str, output_path: Path) -> None:
    """완성 강사 카드를 흰 캔버스에 contain 피팅 + 상단 종목 라벨 + 풋터."""
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    card = Image.open(CARDS / card_file).convert("RGB")
    area_w, area_h = W - 110, H - 320
    scale = min(area_w / card.width, area_h / card.height)
    nw, nh = int(card.width * scale), int(card.height * scale)
    card = card.resize((nw, nh), Image.LANCZOS)
    cx = (W - nw) // 2
    cy = 215 + (area_h - nh) // 2
    canvas.paste(card, (cx, cy))
    d = ImageDraw.Draw(canvas)
    d.text((54, 78), "여름 방학특강 운영 강사", font=load_font("medium", 26), fill=GRAY)
    d.text((54, 120), f"{jong_kr}  ·  {jong_en}", font=load_font("bold", 50), fill=DARK)
    d.rectangle([(56, 188), (150, 191)], fill=BEIGE)
    d.text((54, H - 56), FOOTER, font=load_font("medium", 22), fill=(150, 140, 120))
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [강사] {output_path.name} ({jong_kr})")


def compose_closing(output_path: Path) -> None:
    PHOTO_H = 700
    canvas = Image.new("RGB", (W, H), BLACK_BG)
    photo = center_crop_fill(SCENES / "스쿼시 강습.jpg", W, PHOTO_H)
    canvas.paste(photo, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([(50, 701), (1030, 702)], fill=SEP_LINE)
    canvas = paste_logo(canvas, logo_w=115)
    d = ImageDraw.Draw(canvas)
    _chip(d)
    d.text((40, 718), META_LINE, font=load_font("medium", 24), fill=GRAY)
    d.multiline_text((40, 772), "전문 코치진과 1:6 소수정예,\n안심하고 맡기세요", font=load_font("bold", 50), fill=WHITE, spacing=10)
    d.text((40, 920), "문의는 프로필 링크로", font=load_font("semibold", 28), fill=BEIGE)
    d.text((40, 1040), FOOTER, font=load_font("medium", 22), fill=BEIGE)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [마무리] {output_path.name}")


def build_slides() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("post_*.jpg"):
        old.unlink()
    paths = []
    p1 = OUT / "post_1.jpg"; compose_cover(p1); paths.append(p1)
    for i, (cf, kr, en) in enumerate(COACHES, start=2):
        p = OUT / f"post_{i}.jpg"; compose_coach(cf, kr, en, p); paths.append(p)
    p6 = OUT / f"post_{TOTAL}.jpg"; compose_closing(p6); paths.append(p6)
    return paths


def build_montage(paths: list[Path]) -> Path:
    COLS = 3
    TW = TH = W // COLS
    rows = (len(paths) + COLS - 1) // COLS
    mont = Image.new("RGB", (TW * COLS, TH * rows), (20, 20, 20))
    for i, p in enumerate(paths):
        thumb = Image.open(p).convert("RGB").resize((TW, TH), Image.LANCZOS)
        r, c = divmod(i, COLS)
        mont.paste(thumb, (c * TW, r * TH))
    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()
    out = OUT / f"_검수_미리보기_{TOTAL}장.png"
    mont.save(out, "PNG", optimize=True)
    print(f"  [몽타주] {out.name}")
    return out


def update_review_queue(montage: Path) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    prev_name = f"260701_여름방학특강_ep3_preview_{ts}.png"
    shutil.copy2(montage, REVIEW / prev_name)
    slides = [f"instagram/260701_여름방학특강_ep3/output(인스타그램)/post_{i}.jpg" for i in range(1, TOTAL + 1)]
    prev_rel = f"cmo/review/{prev_name}"
    data = json.loads(QUEUE_F.read_text(encoding="utf-8-sig"))
    entry = {
        "id": REVIEW_ID, "title": TITLE, "channel": "인스타그램 (wellperion 공식)",
        "account": "wellperion", "folder": "instagram/260701_여름방학특강_ep3",
        "slides": slides, "caption": CAPTION, "location": "웰페리온 스포츠클럽",
        "status": "검수대기", "preview": prev_rel,
    }
    found = False
    for item in data:
        if item.get("id") == REVIEW_ID:
            item.update(entry); found = True; break
    if not found:
        data.insert(0, entry)
    QUEUE_F.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [queue] {'갱신' if found else '신규추가'} — {prev_rel}")
    return prev_rel


def main() -> None:
    print("=== Ep3 강사·운영진 신뢰편 빌드 ===")
    verify_sources()
    slides = build_slides()
    assert len(slides) == TOTAL
    montage = build_montage(slides)
    prev = update_review_queue(montage)
    print(f"\n=== 빌드 완료 === {TOTAL}장 / {prev}")
    print("※ 검수카드는 내일 10시 예약 발송(여기서 미발송)")


if __name__ == "__main__":
    main()
