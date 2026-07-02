"""2026 여름 방학특강 Ep3 — 강사·운영진 신뢰편 슬라이드 빌드 (A안 자격 카드형)

GM 결정 (2026-07-02):
  - Ep1=공간 / Ep2=강습(무엇을 배우나) → Ep3=강사·운영진 신뢰편(누가 가르치나).
  - ★얼굴 사진 부담 → 전면 제거. 'A안 자격 카드형'으로 대체(GM 선택 2026-07-02).
  - ① 표지: 얼굴 2×2 폐지 → 타이포 신뢰 커버(검증된 지도진 · 4종목 라인).
  - ② 개별 카드: 인물 사진 제거 → 종목·팀·팀장명(얼굴X) + 주요경력 + 보유자격 칩.
  - ③ 마지막장: 4종목 활동 그리드(강사 얼굴 아님·활동컷) 유지.
  - 기준=신뢰할 수 있는 강사·팀장. 부담=얼굴이므로 이름·자격은 유지(신뢰 근거·과장 금지).
  - 가격·시간표 비노출·프로필 문의 유도(Ep2 동일 정책). 자격은 카드 실재 항목만 인용.
엔진=compose_barre 계승(표지·마무리 톤 통일).
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

SCRIPTS = Path(r"C:\Users\jjky0\welperion-automation\scripts")
sys.path.insert(0, str(SCRIPTS))

from compose_barre import (
    to_duotone, center_crop_fill, paste_logo, draw_chip, load_font, W, H,
)
from brand_constants import BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE

ROOT     = Path(r"C:\Users\jjky0\welperion-automation")
SCENES   = ROOT / "instagram" / "Image" / "방학특강(원본 이미지)"
OUT      = ROOT / "instagram" / "260701_여름방학특강_ep3" / "output(인스타그램)"
GUIDE    = ROOT / "3. 웰페리온 가이드"
REVIEW   = GUIDE / "cmo" / "review"
QUEUE_F  = REVIEW / "review_queue.json"

REVIEW_ID = "CMO-2026-07-01-SUMMER-CAMP-EP3"
TITLE     = "2026 여름 방학특강 Ep3 강사·운영진 신뢰편"
TOTAL     = 6
DARK      = (38, 38, 40)
CRED_TXT  = (60, 50, 35)
LABEL_C   = (168, 148, 120)
BODY_TXT  = (70, 68, 66)

CHIP_LABEL, CHIP_W, CHIP_H, CHIP_F = "WELLPERION", 150, 38, 22
FOOTER    = "WELLPERION  ·  스포츠클럽"

# (종목KR, 종목EN, 이름KR, 팀, [주요경력3], [보유자격2])  ※ 얼굴 사진 없음
COACHES = [
    ("수영", "SWIMMING", "박민서", "수영팀",
     ["신구스포츠센터 성인 지도교사", "오션키즈 어린이 수영장 지도교사", "유소년·성인·실버반 지도 경력"],
     ["2급 생활스포츠지도사(수영)", "대한적십자 수상인명구조원"]),
    ("체조", "GYMNASTICS", "이형주", "체조팀",
     ["前 기계체조 국가대표 상비군", "전국체전 단체종합 우승 다수", "크로스핏 키즈 코치 역임"],
     ["유아체육 지도자 1급", "크로스핏 레벨1 트레이너"]),
    ("스쿼시", "SQUASH", "이상훈", "스쿼시팀",
     ["서울대 자유전공학부 학사", "전국체전 서울·경기 대표", "2014 Brown University Squash Team"],
     ["세계스쿼시연맹 WSC Foundation Coach", "PSA Squash Tour 프로"]),
    ("골프", "GOLF", "최현준", "골프팀",
     ["KPGA 프로 · JGTO 해외투어 활동", "이글 스포렉스 삼성동 소속프로", "충북 주니어선수권 1위"],
     ["한국프로골프협회 KPGA 프로", "유원대학교 골프전공"]),
]

# 마무리 4종목 활동 그리드 (활동컷 · 강사 얼굴 아님)
GRID_SCENES = [
    "방학 수영 레슨.png",
    "방학 유소년 체조 강습.png",
    "스쿼시 강습.jpg",
    "골프 강습.jpg",
]

CAPTION = """믿고 맡기는 이유 — 검증된 지도진.

이번 여름방학 특강은 종목별 전문 팀장과 코치진이 이끕니다.
자격을 갖춘 지도진이 아이 한 명 한 명을 챙깁니다.

· 수영팀 박민서 팀장 — 생활스포츠지도사·수상인명구조원
· 체조팀 이형주 팀장 — 유아체육 지도자 1급·前 기계체조 국가대표 상비군
· 스쿼시팀 이상훈 팀장 — 서울대 자유전공·WSC Foundation Coach
· 골프팀 최현준 팀장 — KPGA 프로·JGTO 해외투어

기초부터 차근차근, 1:6 소수정예로 한 명 한 명 눈을 맞춥니다.
처음이어도 안심하고 맡기셔도 좋습니다.

· 6월 29일 ~ 8월 14일 / 2019년 이전 출생 유소년
· 1:6 소수정예 · 횟수 자율조정 · 주차 제공

자세한 시간표·요금은 프로필 링크로 문의해 주세요.

#여름방학특강 #유소년스포츠 #한남동수영 #한남동골프 #키즈스포츠 #전문코치 #스포츠클럽 #웰페리온 #WELLPERION"""


def verify_sources() -> None:
    missing = [s for s in GRID_SCENES if not (SCENES / s).exists()]
    if missing:
        print(f"[ERROR] 원본 누락: {missing}")
        raise SystemExit(1)
    print("  활동 사진 4종 확인 완료 (인물 카드 = 얼굴 없음 · 텍스트 생성)")


def _chip(draw):
    draw_chip(draw, CHIP_LABEL, load_font("bold", CHIP_F), W - 40 - CHIP_W, 42, CHIP_W, CHIP_H)


def _cred_chip(d: ImageDraw.ImageDraw, text: str, x: int, y: int, font, h: int = 52) -> int:
    tw = d.textlength(text, font=font)
    pad = 22
    w = int(tw + pad * 2)
    d.rounded_rectangle([(x, y), (x + w, y + h)], radius=h // 2, fill=BEIGE)
    d.text((x + pad, y + h // 2), text, font=font, fill=CRED_TXT, anchor="lm")
    return h


def compose_cover(output_path: Path) -> None:
    """타이포 신뢰 커버 (얼굴 없음) — 검증된 지도진 + 4종목 라인."""
    canvas = Image.new("RGB", (W, H), BLACK_BG)
    canvas = paste_logo(canvas, logo_w=120)
    d = ImageDraw.Draw(canvas)
    _chip(d)

    # 은은한 상하 프레임 라인
    d.rectangle([(48, 48), (W - 48, 50)], fill=(70, 66, 60))
    d.rectangle([(48, H - 50), (W - 48, H - 48)], fill=(70, 66, 60))

    d.text((W // 2, 402), "믿고 맡기는 이유", font=load_font("semibold", 36), fill=BEIGE, anchor="mm")
    d.text((W // 2, 496), "검증된 지도진", font=load_font("bold", 82), fill=WHITE, anchor="mm")
    d.text((W // 2, 566), "QUALIFIED COACHES", font=load_font("semibold", 27), fill=BEIGE, anchor="mm")
    d.rectangle([(W // 2 - 34, 612), (W // 2 + 34, 614)], fill=BEIGE)
    d.text((W // 2, 648), "종목별 자격을 갖춘 전문 팀이 이끕니다",
           font=load_font("medium", 25), fill=(225, 220, 210), anchor="mm")

    d.text((W // 2, 892), "수영    ·    체조    ·    스쿼시    ·    골프",
           font=load_font("medium", 28), fill=(205, 196, 178), anchor="mm")
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [표지] {output_path.name}")


def compose_cred_card(jong_kr, jong_en, name_kr, team, careers, quals, output_path) -> None:
    """자격 카드 (얼굴 없음): 상단 다크 헤더(종목·팀·팀장) + 하단 화이트(경력·자격 칩)."""
    HEADER_H = 400
    canvas = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(canvas)

    # 상단 다크 헤더 + 종목 EN 워터마크
    d.rectangle([(0, 0), (W, HEADER_H)], fill=BLACK_BG)
    d.text((W - 34, HEADER_H - 26), jong_en, font=load_font("bold", 150),
           fill=(52, 52, 54), anchor="rs")
    d.rectangle([(0, HEADER_H - 4), (W, HEADER_H)], fill=BEIGE)

    canvas = paste_logo(canvas, logo_w=112)
    d = ImageDraw.Draw(canvas)
    _chip(d)

    tx = 48
    d.text((tx, 236), f"웰페리온 {team}", font=load_font("medium", 25), fill=(190, 180, 165))
    d.text((tx, 278), f"{jong_kr}  ·  {jong_en}", font=load_font("bold", 44), fill=BEIGE)

    # 팀장명 + '팀장' 태그 (얼굴 없이 신뢰 근거)
    nf = load_font("bold", 40)
    ny = 344
    d.text((tx, ny), name_kr, font=nf, fill=WHITE)
    nw = d.textlength(name_kr, font=nf)
    tag = "팀장"; tf = load_font("bold", 21)
    tw = d.textlength(tag, font=tf); pad = 15; th = 38
    tagx = tx + int(nw) + 16; tagy = ny + 2
    d.rounded_rectangle([(tagx, tagy), (tagx + int(tw) + pad * 2, tagy + th)], radius=19, fill=BEIGE)
    d.text((tagx + pad, tagy + th // 2), tag, font=tf, fill=CRED_TXT, anchor="lm")

    # 하단 화이트 본문: 주요 경력
    d.rectangle([(tx, 468), (tx + 60, 471)], fill=BEIGE)
    d.text((tx, 490), "주요 경력", font=load_font("semibold", 24), fill=LABEL_C)
    bf = load_font("medium", 26)
    for i, c in enumerate(careers):
        d.text((tx, 536 + i * 48), f"·  {c}", font=bf, fill=BODY_TXT)

    # 보유 자격 (칩 강조 = 주인공)
    qy = 536 + len(careers) * 48 + 34
    d.rectangle([(tx, qy - 22), (tx + 60, qy - 19)], fill=BEIGE)
    d.text((tx, qy), "보유 자격", font=load_font("semibold", 24), fill=LABEL_C)
    cf = load_font("semibold", 26)
    cy = qy + 48
    for q in quals:
        _cred_chip(d, q, tx, cy, cf)
        cy += 68

    d.text((tx, 1016), FOOTER, font=load_font("medium", 22), fill=(150, 140, 120))
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [자격카드] {output_path.name} ({team} {name_kr})")


def compose_closing(output_path: Path) -> None:
    """4종목 활동 2×2 그리드 + 1:6 안심 메시지 (활동컷 · 얼굴 주인공 아님)."""
    HALF = W // 2
    positions = [(0, 0), (HALF, 0), (0, HALF), (HALF, HALF)]
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    for scene, (x, y) in zip(GRID_SCENES, positions):
        tile = center_crop_fill(SCENES / scene, HALF, HALF)
        tile = ImageEnhance.Brightness(tile).enhance(0.85)
        canvas.paste(tile, (x, y))

    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle([(0, 430), (W, 650)], fill=(0, 0, 0, 155))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), band).convert("RGB")

    canvas = paste_logo(canvas, logo_w=115)
    d = ImageDraw.Draw(canvas)
    _chip(d)
    d.multiline_text((W // 2, 500), "자격을 갖춘 지도진이 이끄는\n1:6 소수정예, 안심하고 맡기세요",
                     font=load_font("bold", 46), fill=WHITE, anchor="mm", align="center", spacing=10)
    d.text((W // 2, 596), "문의는 프로필 링크로", font=load_font("semibold", 28), fill=BEIGE, anchor="mm")
    d.text((40, 1040), FOOTER, font=load_font("medium", 22), fill=BEIGE)
    canvas.convert("RGB").save(output_path, "JPEG", quality=93, optimize=True)
    print(f"  [마무리] {output_path.name}")


def build_slides() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("post_*.jpg"):
        old.unlink()
    paths = []
    p1 = OUT / "post_1.jpg"; compose_cover(p1); paths.append(p1)
    for i, (kr, en, nk, tm, careers, quals) in enumerate(COACHES, start=2):
        p = OUT / f"post_{i}.jpg"
        compose_cred_card(kr, en, nk, tm, careers, quals, p)
        paths.append(p)
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
    print("=== Ep3 강사·운영진 신뢰편 빌드 (A안 자격 카드형 · 얼굴 제거) ===")
    verify_sources()
    slides = build_slides()
    assert len(slides) == TOTAL
    montage = build_montage(slides)
    prev = update_review_queue(montage)
    print(f"\n=== 빌드 완료 === {TOTAL}장 / {prev}")
    print("※ 검수대기 상태 — 텔레그램 카드 미발송(GM 확인 후)")


if __name__ == "__main__":
    main()
