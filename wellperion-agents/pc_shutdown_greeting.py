# pc_shutdown_greeting.py
# PC 종료/퇴근 인사 — AI CTO 복구본 (CTO-2026-06-01)
#
# 트리거 Wellperion-PC-Shutdown-Greeting-Live (매일 22:25경)가
#   C:\Python314\python.exe ...\wellperion-agents\pc_shutdown_greeting.py 실행.
#
# 기능: PC 종료/퇴근 시각에 GM 텔레그램(@namuki_report_bot, OWNER_ID)으로
#       시각대에 맞는 따뜻한 한국어 퇴근 인사 1줄 발송. 노션 무관, 순수 텔레그램.
#       문구는 날짜/요일 기반 index 선택(Math.random 금지) — 같은 날엔 항상 같은 문구.
#
# 사용법:
#   python pc_shutdown_greeting.py            # 실제 발송
#   python pc_shutdown_greeting.py --dry-run  # 발송 없이 문구만 print

import os
import sys
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import requests  # send_telegram 발송용

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

KST = timezone(timedelta(hours=9))

WEEKDAY_KO = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# 시각대별 퇴근 인사 문구 풀 (날짜 기반 index 선택, 랜덤 금지)
GREETINGS_EVENING = [
    "오늘도 고생 많으셨습니다, GM님. 편안한 저녁 보내세요.",
    "하루 마무리 잘 하셨습니다, GM님. 푹 쉬세요.",
    "오늘 하루도 수고하셨습니다, GM님. 내일도 응원하겠습니다.",
    "퇴근하시는 GM님, 오늘 하루 정말 고생 많으셨습니다.",
    "수고하셨습니다, GM님. 오늘은 충분히 쉬시고 재충전하세요.",
]

GREETINGS_LATE = [
    "늦은 시간까지 고생 많으셨습니다, GM님. 이제 푹 쉬세요.",
    "오늘도 밤늦게까지 수고하셨습니다, GM님. 무리 마시고 쉬세요.",
    "긴 하루 마무리하시는 GM님, 따뜻하게 쉬시길 바랍니다.",
]


def pick_greeting(now: datetime) -> str:
    """날짜/요일 기반 index로 시각대에 맞는 인사 1개 선택 (랜덤 금지)."""
    pool = GREETINGS_LATE if now.hour >= 23 or now.hour < 4 else GREETINGS_EVENING
    # 연중 일수(day-of-year)를 풀 크기로 나눈 나머지 → 같은 날 항상 같은 문구
    idx = now.timetuple().tm_yday % len(pool)
    return pool[idx]


def build_message(now: datetime) -> str:
    weekday = WEEKDAY_KO[now.weekday()]
    greeting = pick_greeting(now)
    return (
        f"[퇴근 인사] {now.strftime('%Y-%m-%d')} ({weekday}) "
        f"{now.strftime('%H:%M')}\n"
        f"{greeting}"
    )


def send_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not OWNER_ID:
        print("[ERROR] TELEGRAM_BOT_TOKEN/OWNER_ID 미설정 — 발송 생략")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": OWNER_ID, "text": msg},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR] 텔레그램 발송 실패: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    now = datetime.now(KST)
    msg = build_message(now)

    if dry_run:
        print("[DRY-RUN] 발송 생략 — 아래 문구만 표시")
        print(msg)
        return

    ok = send_telegram(msg)
    print(f"[발송 {'성공' if ok else '실패'}] {now.strftime('%H:%M')} 퇴근 인사")


if __name__ == "__main__":
    main()
