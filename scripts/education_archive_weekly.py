# education_archive_weekly.py
# AI 교육자료 주간 자동 정리(이관) — AI CTO 복구본 (CTO-2026-06-01)
#
# 트리거 Wellperion-Education-Archive-Weekly (매주 월 09:00)가
#   C:\Python314\python.exe ...\scripts\education_archive_weekly.py 실행.
#
# 기능 (메모리 project_education_archive_policy 정합):
#   Desktop·Downloads 최상위(top-level, 재귀 X)의 AI 학습자료를 매주
#   Desktop\_정리완료\03_교육\YYYY-MM\ 로 이관(이동, 복사 금지).
#   대상 폴더 없으면 생성. 7일+ 미수정 파일만(편집 중 보호). 충돌 시 _1, _2 suffix.
#   이관 후 텔레그램 1줄 보고(이관 N건 + 상위 5개 파일명). 노션 무관.
#
#   ai_education_auto_learner.py 와 상호 보완:
#     - learner = 수집·요약·발송 + scan(읽기 전용, ARCHIVE_DIR/Desktop/Downloads top-level 스캔)
#     - 본 스크립트 = 실제 이동(Desktop/Downloads top-level → ARCHIVE_DIR\YYYY-MM\ 하위)
#   이동 목적지가 ARCHIVE_DIR 의 월별 하위폴더이므로 learner 의 non-recursive
#   iterdir() 스캔과 충돌(중복 집계) 없음. 키워드·확장자 집합은 learner 와 동일하게 정합.
#
# 사용법:
#   python education_archive_weekly.py            # 실제 이관 + 텔레그램 보고
#   python education_archive_weekly.py --dry-run  # 이동 없이 대상 목록만 출력

import os
import sys
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

# .env 위치: 레포 telegram_bot/.env (TELEGRAM_BOT_TOKEN/OWNER_ID SSOT)
_BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
load_dotenv(_BASE_DIR / "telegram_bot" / ".env")

import requests  # send_telegram 발송용

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

KST = timezone(timedelta(hours=9))

# 이관 목적지 루트 (ai_education_auto_learner.ARCHIVE_DIR 와 동일 경로)
ARCHIVE_ROOT = Path.home() / "Desktop" / "_정리완료" / "03_교육"

# 정리 대상 위치 — Desktop/Downloads 최상위만 (재귀 X — 작업 폴더 침범 차단)
SOURCE_DIRS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
]

# learner 와 동일 확장자/키워드 집합 (정합)
EXTENSIONS = {".pdf", ".docx", ".md", ".txt", ".html", ".epub"}
KEYWORDS = [
    "claude", "gpt", "llm", "anthropic", "gemini",
    "prompt", "ai", "에이전트", "튜토리얼",
]

# 편집 중 파일 보호 — 7일+ 미수정 파일만 이관
PROTECT_DAYS = 7


def collect_targets():
    """Desktop/Downloads 최상위에서 이관 대상 파일 목록 수집."""
    targets = []
    cutoff = time.time() - PROTECT_DAYS * 86400
    for src in SOURCE_DIRS:
        if not src.exists():
            continue
        for f in src.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in EXTENSIONS:
                continue
            name_lower = f.name.lower()
            if not any(kw in name_lower for kw in KEYWORDS):
                continue
            if f.stat().st_mtime > cutoff:
                continue  # 7일 내 미수정 — 작업 중 보호
            targets.append(f)
    return targets


def unique_dest(dest_dir: Path, filename: str) -> Path:
    """충돌 시 _1, _2 suffix 부여한 목적지 경로 반환."""
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    i = 1
    while True:
        cand = dest_dir / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


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
        log_outbound(msg, chat_id=OWNER_ID, source="education_archive_weekly.send_telegram", ok=(resp.status_code == 200), kind="sendMessage")
        return resp.status_code == 200
    except Exception as e:
        log_outbound(msg, chat_id=OWNER_ID, source="education_archive_weekly.send_telegram", ok=False, kind="sendMessage")
        print(f"[ERROR] 텔레그램 발송 실패: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    now = datetime.now(KST)
    month_folder = ARCHIVE_ROOT / now.strftime("%Y-%m")

    targets = collect_targets()

    if dry_run:
        print(f"[DRY-RUN] 이관 대상 {len(targets)}건 — 실제 이동 없음")
        print(f"[DRY-RUN] 목적지: {month_folder}")
        for f in targets:
            print(f"  - {f.name}  ({f})")
        return

    if not targets:
        msg = f"[교육자료 주간 정리] {now.strftime('%Y-%m-%d')} 이관 0건 — 대상 없음"
        send_telegram(msg)
        print(msg)
        return

    month_folder.mkdir(parents=True, exist_ok=True)

    moved = []
    for f in targets:
        dest = unique_dest(month_folder, f.name)
        try:
            shutil.move(str(f), str(dest))
            moved.append(dest.name)
        except Exception as e:
            print(f"[ERROR] 이동 실패 {f.name}: {e}")

    top5 = ", ".join(moved[:5])
    msg = (
        f"[교육자료 주간 정리] {now.strftime('%Y-%m-%d')} "
        f"이관 {len(moved)}건 → {now.strftime('%Y-%m')}\n"
        f"{top5}"
    )
    ok = send_telegram(msg)
    print(f"[발송 {'성공' if ok else '실패'}] {msg}")


if __name__ == "__main__":
    main()
