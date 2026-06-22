"""범용 업장 가이드 카드 생성기 (마스터 상속 · 글꼴·크기 100% 통일)

표준: instagram/_assets/업장_가이드_디자인_표준.md
모든 업장 카드를 동일 마스터 프레임 위에 본문 3섹션(회원/강사·프로/시설)만 교체해 렌더.
→ 프레임·폰트·크기·여백이 카드마다 자동 동일(드리프트 불가). 새 업장 = CARDS에 1개 추가.

출력: instagram/_assets/각 업장 가이드/{파일명}
실행:
  python scripts/compose_guideline_card.py            # 전체 렌더
  python scripts/compose_guideline_card.py 스쿼시      # 특정 업장만
"""
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from brand_constants import PROJECT_ROOT, BEIGE, WHITE
from compose_barre import load_font, center_crop_fill

W, H = 1080, 1080
MASTER = PROJECT_ROOT / "instagram" / "_assets" / "guideline_card.jpg"
OUT_DIR = PROJECT_ROOT / "instagram" / "_assets" / "각 업장 가이드"

# ── 본문 정본 좌표·크기 (표준 §3 — 마스터 실측, 전 카드 공통) ──────────────
ITEM_COLOR  = (200, 198, 199)
ITEM_YS_TOP = [388, 412, 436, 460, 484]
ITEM_YS_BOT = [588, 612, 636, 660, 684]
LX_H, LX_I  = 52, 64
RX_H, RX_I  = 550, 562
HDR_Y_TOP   = 357
HDR_Y_BOT   = 558

# ── 업장별 본문 내용 (★여기만 업장마다 다름 · 프레임/폰트/크기는 전부 공통) ──
# 각 카드: 파일명 + 좌상(회원) + 좌하(강사/프로/트레이너) + 우측(시설)
CARDS: dict[str, dict] = {
    "골프": {
        "file": "골프 가이드.jpg",
        "members": ("FOR MEMBERS", "회원님들", [
            "사전 예약 필수 (Reservation Required)",
            "타석 외 스윙 금지·출입 시 안전 확인 (Swing in Bay Only)",
            "만석 시 60분 에티켓 준수 (60-Min Courtesy When Full)",
            "소음·고성 자제 (Quiet Please)",
            "궁금하신 점은 언제든 문의해 주세요",
        ]),
        "left2": ("FOR PROS", "프로님들", [
            "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
            "소속 프로 외 레슨 금지 (Authorized Coaching Only)",
            "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
            "장비·타석 점검·정돈 (Check & Reset)",
            "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
        ]),
        "facility": ("GOLF RANGE", "골프 연습장 이용", [
            "타석 이동·취소는 키오스크에서 (Use Kiosk)",
            "10분 이상 이석 시 자동 종료 (10-Min Away = End)",
            "피팅존 회원 전용 (Fitting Zone · Members Only)",
            "동반·방문객은 라운지 이용 (Guests Wait in Lounge)",
            "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
        ]),
    },
    "스쿼시": {
        "file": "스쿼시 가이드.jpg",
        "members": ("FOR MEMBERS", "회원님들", [
            "사전 예약 필수 (Reservation Required)",
            "코트화·보호 고글 착용 (Court Shoes & Eyewear)",
            "예약 시간 준수·정시 교대 (Keep to Time)",
            "코트 내 음료는 물만 (Water Only)",
            "궁금하신 점은 언제든 문의해 주세요",
        ]),
        "left2": ("FOR INSTRUCTORS", "강사님들", [
            "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
            "회원 동의 없는 촬영 금지 (No Photo)",
            "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
            "장비·코트 점검·정돈 (Check & Reset)",
            "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
        ]),
        "facility": ("SQUASH COURT", "스쿼시 코트 이용", [
            "코트화 외 입장 금지 (Court Shoes Only)",
            "라켓·공은 지정 위치 보관 (Store Gear)",
            "벽·바닥 손상 주의 (Care for Court)",
            "종료 후 환기·정리 (Ventilate After)",
            "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
        ]),
    },
    "PT": {
        "file": "PT 가이드.jpg",
        "members": ("FOR MEMBERS", "회원님들", [
            "사전 예약 필수 (Reservation Required)",
            "실내 운동화 착용 (Indoor Shoes)",
            "기구 사용 후 소독·원위치 (Wipe & Reset)",
            "외부 음식 금지 · 생수만 (Water Only)",
            "궁금하신 점은 언제든 문의해 주세요",
        ]),
        "left2": ("FOR TRAINERS", "트레이너님들", [
            "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
            "회원 동의 없는 촬영 금지 (No Photo)",
            "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
            "기구·존 점검·정돈 (Check & Reset)",
            "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
        ]),
        "facility": ("PT STUDIO", "퍼스널 트레이닝 이용", [
            "지정 기구·존 사용 (Use Assigned Zone)",
            "중량·기구 정리·원위치 (Re-rack Weights)",
            "땀 닦기·소독 매너 (Wipe After Use)",
            "무리한 중량 주의·안전 우선 (Lift Safely)",
            "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
        ]),
    },
    "G.X": {
        "file": "G.X 가이드.jpg",
        "members": ("FOR MEMBERS", "회원님들", [
            "사전 예약 필수 (Reservation Required)",
            "실내 운동화·운동복 착용 (Workout Attire)",
            "수업 시작 후 입장 자제 (Be On Time)",
            "외부 음식 금지 · 생수만 (Water Only)",
            "궁금하신 점은 언제든 문의해 주세요",
        ]),
        "left2": ("FOR INSTRUCTORS", "강사님들", [
            "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
            "회원 동의 없는 촬영 금지 (No Photo)",
            "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
            "음향·기구 점검·정돈 (Check & Reset)",
            "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
        ]),
        "facility": ("G.X STUDIO", "그룹 운동 이용", [
            "도구·매트 사용 후 원위치 (Return Equipment)",
            "향수·강한 향 자제 (Light Scent Only)",
            "공간 배려·소음 자제 (Share & Quiet)",
            "부상·이상 시 즉시 알림 (Tell Instructor)",
            "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
        ]),
    },
    "수영장": {
        "file": "수영장 가이드.jpg",
        "members": ("FOR MEMBERS", "회원님들", [
            "사전 예약 필수 (Reservation Required)",
            "수영모 착용·입수 전 샤워 (Cap & Shower First)",
            "레인 순서·방향 준수 (Follow Lane Order)",
            "다이빙·뛰기 금지 (No Diving · No Running)",
            "궁금하신 점은 언제든 문의해 주세요",
        ]),
        "left2": ("FOR INSTRUCTORS", "강사님들", [
            "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
            "회원 동의 없는 촬영 금지 (No Photo)",
            "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
            "수질·장비 점검·정돈 (Check & Reset)",
            "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
        ]),
        "facility": ("SWIMMING POOL", "수영장 이용", [
            "입수 전 샤워 필수 (Shower Before Entry)",
            "음식물 반입 금지 (No Food)",
            "미끄럼 주의·뛰기 금지 (No Running)",
            "아동은 보호자 동반 (Kids with Guardian)",
            "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
        ]),
    },
    "체조": {
        "file": "체조 가이드.jpg",
        "members": ("FOR MEMBERS", "회원님들", [
            "사전 예약 필수 (Reservation Required)",
            "지정 실내화·운동복 착용 (Indoor Shoes & Attire)",
            "매트·기구 사용 후 원위치 (Return Equipment)",
            "안전 수칙 준수 (Follow Safety Rules)",
            "궁금하신 점은 언제든 문의해 주세요",
        ]),
        "left2": ("FOR INSTRUCTORS", "강사님들", [
            "시작 10분 전 도착·세팅 (Be Ready 10 Min)",
            "회원 동의 없는 촬영 금지 (No Photo)",
            "안전 1순위 · 즉시 리셉션 공유 (Safety First)",
            "매트·기구 점검·정돈 (Check & Reset)",
            "정중 · 절제 · 전문 (Respect · Restraint · Expertise)",
        ]),
        "facility": ("GYMNASTIC STUDIO", "체조 스튜디오 이용", [
            "맨발 또는 지정 실내화 (Bare Feet or Indoor Shoes)",
            "기구는 지도 하에 사용 (Use Under Guidance)",
            "매트 청결 유지 (Keep Mats Clean)",
            "부상·이상 시 즉시 알림 (Report Injury)",
            "시설 이슈 발생 시 리셉션 공유 (Notify Reception)",
        ]),
    },
}


def _section(draw, x_h: int, x_i: int, y_h: int, ys: list[int], hdr: tuple) -> None:
    eng, kor, items = hdr
    f_eng = load_font("bold", 22)
    f_kor = load_font("medium", 22)
    f_item = load_font("medium", 16)
    draw.text((x_h, y_h), eng, font=f_eng, fill=BEIGE)
    ew = draw.textlength(eng, font=f_eng)
    draw.text((x_h + ew + 12, y_h), kor, font=f_kor, fill=WHITE)
    for yy, it in zip(ys, items):
        draw.text((x_i, yy), f"·  {it}", font=f_item, fill=ITEM_COLOR)


def render_card(key: str) -> Path:
    cfg = CARDS[key]
    if not MASTER.exists():
        raise FileNotFoundError(f"마스터 가이드카드 없음: {MASTER}")
    img = Image.open(MASTER).convert("RGB")
    if img.size != (W, H):
        img = center_crop_fill(MASTER, W, H)
    draw = ImageDraw.Draw(img)

    bg = img.getpixel((60, 760))
    draw.rectangle((44, 344, 516, 712), fill=bg)
    draw.rectangle((544, 344, 1036, 712), fill=bg)

    _section(draw, LX_H, LX_I, HDR_Y_TOP, ITEM_YS_TOP, cfg["members"])   # 좌상 회원
    _section(draw, LX_H, LX_I, HDR_Y_BOT, ITEM_YS_BOT, cfg["left2"])     # 좌하 강사/프로
    _section(draw, RX_H, RX_I, HDR_Y_TOP, ITEM_YS_TOP, cfg["facility"])  # 우측 시설

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / cfg["file"]
    img.save(out, "JPEG", quality=95, optimize=True)
    print(f"  [{key}] {out.name} ({out.stat().st_size // 1024}KB)")
    return out


def main() -> None:
    keys = sys.argv[1:] or list(CARDS.keys())
    print("=== 업장 가이드 카드 생성 (마스터 상속 · 글꼴·크기 통일) ===")
    for k in keys:
        if k not in CARDS:
            print(f"  [건너뜀] 미정의 업장: {k} (CARDS에 추가 필요)")
            continue
        render_card(k)


if __name__ == "__main__":
    main()
