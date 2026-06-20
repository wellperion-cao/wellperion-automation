"""골프 전용 가이드라인 카드 생성기 (전면 재설계 v2)
레이아웃·톤(차콜배경·베이지·로고·칩·구분선·OPERATIONS·문의·주소)은 기존 표준 그대로.
가운데 3개 섹션 텍스트만 골프 전용으로 전면 교체.

섹션:
  좌상 — FOR MEMBERS  회원님들
  좌하 — FOR PROS  프로님들  (기존 FOR INSTRUCTORS 자리)
  우측 — GOLF FACILITY  골프장 시설 이용

출력: instagram/_assets/guideline_card_golf.jpg
실행: python scripts/compose_guideline_card_golf.py
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import (
    PROJECT_ROOT, LOGO_BEIGE_ALPHA,
    BEIGE, BLACK_BG, WHITE, GRAY, SEP_LINE,
)
from compose_barre import load_font, draw_chip

W, H = 1080, 1080
OUT_CARD = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card_golf.jpg"

BG       = (32, 29, 28)   # 원본 배경 실측
LINE_COL = (80, 74, 70)   # 중앙 세로 구분선
DOT      = "· "
LINE_H   = 36             # 항목 줄 간격


def _paste_logo(canvas: Image.Image, logo_w: int = 130) -> Image.Image:
    logo = Image.open(LOGO_BEIGE_ALPHA).convert("RGBA")
    ow, oh = logo.size
    lh = int(oh * logo_w / ow)
    logo = logo.resize((logo_w, lh), Image.LANCZOS)
    base = canvas.convert("RGBA")
    base.paste(logo, (40, 40), mask=logo)
    return base.convert("RGB")


def compose_guideline_card_golf(output_path: Path = OUT_CARD) -> None:
    canvas = Image.new("RGB", (W, H), BG)
    canvas = _paste_logo(canvas, logo_w=130)
    draw   = ImageDraw.Draw(canvas)

    # ── 우상단 칩 ─────────────────────────────────────────────────
    chip_font = load_font("bold", 24)
    draw_chip(draw, "WELLPERION", chip_font, W - 50 - 180, 40, 180, 48)

    # ── 상단 제목 블록 ────────────────────────────────────────────
    draw.text((W // 2, 160), "WELLPERION GUIDE",
              font=load_font("bold", 46), fill=BEIGE, anchor="mm")
    draw.text((W // 2, 212), "A Day, Well Completed.",
              font=load_font("semibold", 30), fill=WHITE, anchor="mm")
    draw.text((W // 2, 248), "하루의 완성",
              font=load_font("medium", 26), fill=WHITE, anchor="mm")
    draw.text((W // 2, 280), "정성스러운 하루가 모여, 더 나은 일상을 만듭니다",
              font=load_font("medium", 22), fill=GRAY, anchor="mm")

    # 상단 / 섹션 구분 가로선
    draw.line([(50, 308), (W - 50, 309)], fill=SEP_LINE, width=1)

    # ── 중앙 세로 구분선 ──────────────────────────────────────────
    MID_X = 530
    draw.line([(MID_X, 318), (MID_X, 762)], fill=LINE_COL, width=1)

    # 섹션 공통 폰트
    f_sec_eng  = load_font("bold",     22)
    f_sec_kor  = load_font("semibold", 22)
    f_item     = load_font("medium",   20)

    def _section_header(x: int, y: int, eng: str, kor: str,
                        x_end: int) -> int:
        """섹션 제목 + 하단 구분선 그리기. 다음 y 반환."""
        ew = draw.textlength(eng, font=f_sec_eng)
        draw.text((x, y), eng, font=f_sec_eng, fill=BEIGE)
        draw.text((x + ew + 12, y), kor, font=f_sec_kor, fill=WHITE)
        y += 30
        draw.line([(x, y), (x_end, y + 1)], fill=SEP_LINE, width=1)
        return y + 10

    def _items(x: int, y: int, items: list[str]) -> int:
        for item in items:
            draw.text((x, y), f"{DOT}{item}", font=f_item, fill=WHITE)
            y += LINE_H
        return y

    # ── 좌상: FOR MEMBERS  회원님들 ──────────────────────────────
    Lx = 52
    y  = 326
    y = _section_header(Lx, y, "FOR MEMBERS", "회원님들", MID_X - 20)
    y = _items(Lx, y, [
        "사전 예약 필수 (Reservation Required)",
        "골프화·칼라 복장 규정 준수 (Dress Code)",
        "빠른 진행·앞 팀과 간격 유지 (Keep Pace)",
        "휴대폰 무음·플레이 중 정숙 (Quiet & Silent)",
        "궁금하신 점은 언제든 문의해 주세요",
    ])

    # ── 좌하: FOR PROS  프로님들 ─────────────────────────────────
    y += 18
    y = _section_header(Lx, y, "FOR PROS", "프로님들", MID_X - 20)
    _items(Lx, y, [
        "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
        "회원 동의 없는 촬영 금지 (No Photo)",
        "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
        "장비·시설 점검·정돈 (Check & Reset)",
        "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
    ])

    # ── 우측: GOLF FACILITY  골프장 시설 이용 ────────────────────
    Rx = MID_X + 20
    ry = 326
    ry = _section_header(Rx, ry, "GOLF FACILITY", "골프장 시설 이용", W - 50)
    _items(Rx, ry, [
        "스윙 시 주변 안전 거리 확보 (Keep Safe Distance)",
        "디봇 메우기 · 벙커 정리 (Repair & Rake)",
        "그린 볼마크 수리 (Fix Ball Marks)",
        "카트 · 코스 동선 준수 (Follow Cart Path)",
        "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
    ])

    # ── OPERATIONS 운영 안내 ──────────────────────────────────────
    ops_y = 780
    draw.line([(50, ops_y), (W - 50, ops_y + 1)], fill=SEP_LINE, width=1)
    ops_y += 18
    draw.text((52, ops_y), "OPERATIONS · 운영 안내",
              font=load_font("bold", 22), fill=BEIGE)
    ops_y += 32
    draw.text((52, ops_y),
              "· 운영시간 (Hours)  ·  평일 06:00 — 22:30 / 주말·공휴일 08:00 — 20:00",
              font=load_font("medium", 20), fill=WHITE)
    ops_y += LINE_H
    draw.text((52, ops_y),
              "· 휴관 (Closed)  ·  신정·명절·매월 둘째·넷째 일요일",
              font=load_font("medium", 20), fill=WHITE)

    # ── 하단 문의·주소 ────────────────────────────────────────────
    draw.line([(50, 918), (W - 50, 919)], fill=SEP_LINE, width=1)
    draw.text((W // 2, 952),
              "문의 (Inquiry) :  http://wellperion.com/ko/inquiry/",
              font=load_font("semibold", 26), fill=WHITE, anchor="mm")
    draw.text((W // 2, 992),
              "WELLPERION  ·  한남동  ·  서울 용산구 서빙고로 413",
              font=load_font("medium", 20), fill=GRAY, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [골프 가이드카드 v2] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def main() -> None:
    print("=== 골프 전용 가이드라인 카드 생성 (전면 재설계 v2) ===")
    compose_guideline_card_golf(OUT_CARD)
    print(f"출력: {OUT_CARD}")


if __name__ == "__main__":
    main()
