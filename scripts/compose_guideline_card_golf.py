"""골프 전용 가이드라인 카드 생성기 (v3 · 마스터 상속)

표준: instagram/_assets/업장_가이드_디자인_표준.md
황금 규칙 — 마스터 `guideline_card.jpg`를 베이스로, **가운데 3섹션 텍스트만** 골프용으로 교체.
프레임(로고·칩·제목블록·중앙 세로 구분선·OPERATIONS·문의·주소·여백)은 마스터 픽셀 그대로 둔다.
★from-scratch 재작성 금지(v2 사고: 제목46·항목20·헤더밑줄·배경변형·여백압축 드리프트).

본문 좌표·크기 = 마스터 실측 정본:
  섹션 헤더  Bold/Medium 22 (영문 베이지 / 국문 흰색), 상단 y=357 · 좌하 y=558
  항목       Medium 16, 연회색 (200,198,199), 줄간격 24px
  좌칼럼 x=52(헤더)/64(항목) · 우칼럼 x=550/562 · 중앙 구분선·프레임 보존

섹션:
  좌상 — FOR MEMBERS   회원님들
  좌하 — FOR PROS      프로님들
  우측 — GOLF FACILITY 골프장 시설 이용

출력: instagram/_assets/guideline_card_golf.jpg
실행: python scripts/compose_guideline_card_golf.py
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import PROJECT_ROOT, BEIGE, WHITE
from compose_barre import load_font, center_crop_fill

W, H = 1080, 1080
MASTER   = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card.jpg"
OUT_CARD = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card_golf.jpg"

# 본문 정본 (표준 §3 — 마스터 실측값)
ITEM_COLOR  = (200, 198, 199)   # 연회색(순백 아님)
ITEM_YS_TOP = [388, 412, 436, 460, 484]   # 상단 섹션 항목 Y (줄간격 24)
ITEM_YS_BOT = [588, 612, 636, 660, 684]   # 좌하 섹션 항목 Y
LX_H, LX_I  = 52, 64    # 좌칼럼 헤더/항목 x
RX_H, RX_I  = 550, 562  # 우칼럼 헤더/항목 x
HDR_Y_TOP   = 357
HDR_Y_BOT   = 558

MEMBERS = [
    "사전 예약 필수 (Reservation Required)",
    "골프화·칼라 복장 규정 준수 (Dress Code)",
    "빠른 진행·앞 팀과 간격 유지 (Keep Pace)",
    "휴대폰 무음·플레이 중 정숙 (Quiet & Silent)",
    "궁금하신 점은 언제든 문의해 주세요",
]
PROS = [
    "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
    "회원 동의 없는 촬영 금지 (No Photo)",
    "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
    "장비·시설 점검·정돈 (Check & Reset)",
    "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
]
FACILITY = [
    "스윙 시 주변 안전 거리 확보 (Keep Safe Distance)",
    "디봇 메우기 · 벙커 정리 (Repair & Rake)",
    "그린 볼마크 수리 (Fix Ball Marks)",
    "카트 · 코스 동선 준수 (Follow Cart Path)",
    "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
]


def compose_guideline_card_golf(output_path: Path = OUT_CARD) -> None:
    if not MASTER.exists():
        raise FileNotFoundError(f"마스터 가이드카드 없음: {MASTER} (instagram/_assets/guideline_card.jpg 복구 필요)")

    img = Image.open(MASTER).convert("RGB")
    if img.size != (W, H):
        img = center_crop_fill(MASTER, W, H)
    draw = ImageDraw.Draw(img)

    # 여백 빈 곳 배경색 샘플 → 단색 fill로 마스터 본문 텍스트만 지움(프레임·중앙구분선·OPERATIONS 보존)
    bg = img.getpixel((60, 760))
    draw.rectangle((44, 344, 516, 712), fill=bg)   # 좌칼럼 본문
    draw.rectangle((544, 344, 1036, 712), fill=bg)  # 우칼럼 본문 (중앙 구분선 x517~543 보존)

    f_h_eng = load_font("bold", 22)
    f_h_kor = load_font("medium", 22)
    f_item  = load_font("medium", 16)

    def header(x: int, y: int, eng: str, kor: str) -> None:
        draw.text((x, y), eng, font=f_h_eng, fill=BEIGE)
        ew = draw.textlength(eng, font=f_h_eng)
        draw.text((x + ew + 12, y), kor, font=f_h_kor, fill=WHITE)

    def items(x: int, ys: list[int], arr: list[str]) -> None:
        for yy, it in zip(ys, arr):
            draw.text((x, yy), f"·  {it}", font=f_item, fill=ITEM_COLOR)

    # 좌상 FOR MEMBERS / 좌하 FOR PROS / 우상 GOLF FACILITY
    header(LX_H, HDR_Y_TOP, "FOR MEMBERS", "회원님들")
    items(LX_I, ITEM_YS_TOP, MEMBERS)
    header(LX_H, HDR_Y_BOT, "FOR PROS", "프로님들")
    items(LX_I, ITEM_YS_BOT, PROS)
    header(RX_H, HDR_Y_TOP, "GOLF FACILITY", "골프장 시설 이용")
    items(RX_I, ITEM_YS_TOP, FACILITY)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=95, optimize=True)
    print(f"  [골프 가이드카드 v3·마스터상속] {output_path.name} ({output_path.stat().st_size // 1024}KB)")


def main() -> None:
    print("=== 골프 가이드라인 카드 생성 (v3 · 마스터 상속) ===")
    compose_guideline_card_golf(OUT_CARD)
    print(f"출력: {OUT_CARD}")


if __name__ == "__main__":
    main()
