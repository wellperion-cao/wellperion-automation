#!/usr/bin/env python3
"""일일 점검 현황 공유 — 매일 23:00 카톡 '웰페리온 운영+시설+지원' 방 자동 발송 (kakao_daily_check_share.py)

GM 지시(2026-07-09, 오늘 23시 발효). 하루 점검 현황을 실데이터로 정리해
'개선을 유도'하는 톤으로 공유한다 — 미흡/미체크/이슈/기준이탈을 앞쪽에 짚고
마무리에 수고·감사 문구. '최종 정리'가 아니라 '현황 공유'가 제목·목적.

데이터 소스(점검 GAS · CHECK_API · 실측·지어내기 0):
  - 지원부: ?action=today_live&dept=support
      → done/total/pct · uncheckedByShift(미체크 회차×성별 항목명) · allIssues(이슈)
  - 시설부 회수·시각: ?action=board&key=FACILITY_CHECK_YYYY-MM-DD
      → board.store.submissions(리스트) = 실제 제출 회수(페이지 'N회 완료'와 일치·오늘 키라 stale 아님).
      각 submission의 seq·startHHMM·endHHMM·inspector로 회수·시각·점검자를 표출한다.
      (monthly의 sessionCount는 '라운드종류=1 고정'이라 항상 1 → 회수로 쓰지 않는다, GM 2026-07-15)
  - 시설부 기준이탈: ?action=monthly_report&dept=facility&month=YYYY-MM
      → outOfRange.list에서 오늘 날짜 항목(name/value/min/max)만 필터.
      작업사항/지시사항: facility today_live 응답에 있으면 포함, 없으면 정직히 생략.
  - 주차: weekly/monthly 데이터 있으면 포함, 없으면 '자체점검 준비 중' 정직 표기.
  값이 없으면 그 줄을 생략(지어내기 금지).

카톡 발송(재사용):
  scripts/kakao_report_sender.py 의 텍스트 전송을 subprocess로 호출:
    python scripts/kakao_report_sender.py --message "<본문>" --only-room "웰페리온 운영+시설+지원"
  --dry-run 시 렌더 본문만 출력하고 발송 스크립트를 호출하지 않는다.

절대 제약:
  - 발송 대상 방 = '웰페리온 운영+시설+지원' 하나뿐(--only-room 고정). 다른 방·회장님방 금지.
  - GAS 조회 실패해도 크래시 금지(부분 정보라도 발송 or 정직 안내).

사용법:
  python scripts/kakao_daily_check_share.py --dry-run   # 본문 렌더만(카톡 미발송)
  python scripts/kakao_daily_check_share.py             # 실발송(23:00 예약 진입점)
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SENDER = ROOT / "scripts" / "kakao_report_sender.py"

# 3섹션 핵심요약 렌더 = 공용 모듈(텔레그램 점검관리방과 단일 진실). scripts/ 동일 폴더.
import support_check_summary  # noqa: E402

# 발송 대상 방(단일·고정 — 절대 다른 방 금지)
TARGET_ROOM = "★운영+시설+지원+주차"

_DOW_KO = ["월", "화", "수", "목", "금", "토", "일"]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════
#  본문 조립 — 3섹션 핵심요약은 공용 모듈(support_check_summary)이 렌더(단일 진실).
#  텔레그램 점검관리방과 동일 포맷 보장 + 회차분해 요일반영(주말 2회차). GM 2026-07-19.
# ══════════════════════════════════════════════════════════════════════════
def build_body(now: datetime | None = None) -> tuple[str, dict]:
    now = now or datetime.now()
    title_date = f"{now.strftime('%m-%d')}({_DOW_KO[now.weekday()]})"
    bar = "━" * 12

    summary_lines, filled = support_check_summary.build_summary_lines(now=now)

    body_lines = [f"📋 일일 점검 현황 공유 — {title_date}", bar]
    body_lines += summary_lines
    body_lines += [bar, "오늘도 수고 많으셨습니다. 감사합니다 🙏"]

    return ("\n".join(body_lines), filled)


# ══════════════════════════════════════════════════════════════════════════
#  발송(kakao_report_sender.py 텍스트 전송 재사용)
# ══════════════════════════════════════════════════════════════════════════
# 카톡 실행파일(무인 발송 신뢰성 — env로 오버라이드 가능)
KAKAO_EXE = os.environ.get(
    "KAKAOTALK_EXE", r"C:\Program Files (x86)\Kakao\KakaoTalk\KakaoTalk.exe"
)


def ensure_kakao_foreground(wait: float = 6.0) -> None:
    """무인 발송 전 카톡 메인창 띄우기 — 2026-07-13 밤 실패 원인(앱이 트레이로 내려가
    'kakao 메인창 못 찾음') 방지. KakaoTalk은 단일 인스턴스라 exe를 다시 실행하면 이미
    떠 있는 인스턴스의 메인창이 앞으로 나온다. 실패해도 발송은 계속(비치명)."""
    try:
        if not os.path.exists(KAKAO_EXE):
            log(f"[kakao] 실행파일 없음({KAKAO_EXE}) — 자동 띄우기 생략(설치경로 확인 필요)")
            return
        subprocess.Popen([KAKAO_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log(f"[kakao] 메인창 자동 띄우기 시도(무인 신뢰성) — {wait:.0f}s 대기")
        time.sleep(wait)
    except Exception as e:
        log(f"[kakao] 자동 띄우기 실패(무시하고 발송 시도): {type(e).__name__}: {e}")


def send_via_kakao(body: str, dry_run: bool) -> int:
    """kakao_report_sender.py --message ... --only-room TARGET_ROOM 호출(단일 방 고정)."""
    if not dry_run:
        ensure_kakao_foreground()  # 무인 발송 신뢰성 — 발송 직전 카톡 메인창 확보
    cmd = [
        sys.executable, str(SENDER),
        "--message", body,
        "--only-room", TARGET_ROOM,
    ]
    if dry_run:
        cmd.append("--dry-run")
    log(f"[send] 호출: {sys.executable} {SENDER.name} --message <본문> --only-room {TARGET_ROOM!r}"
        f"{' --dry-run' if dry_run else ''}")
    try:
        proc = subprocess.run(cmd, timeout=300)
        return proc.returncode
    except Exception as e:
        log(f"[send] 발송 스크립트 호출 실패: {type(e).__name__}: {e}")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="일일 점검 현황 공유 — 카톡 '웰페리온 운영+시설+지원' 방 자동 발송")
    ap.add_argument("--dry-run", action="store_true",
                    help="본문 렌더만 출력(카톡 미발송·발송 스크립트 미호출)")
    args = ap.parse_args()

    log("일일 점검 현황 공유 시작 — GAS 조회...")
    body, filled = build_body()

    print("\n" + "=" * 60)
    print(body)
    print("=" * 60 + "\n")
    log(f"[데이터] 채워진 필드: {filled}")

    if args.dry_run:
        log("DRY-RUN: 본문 렌더만 완료 — 카톡 미발송(발송 스크립트 미호출).")
        print("DONE: DRY-RUN 렌더 완료(카톡 미발송)")
        return 0

    rc = send_via_kakao(body, dry_run=False)
    if rc == 0:
        print(f"DONE: 카톡 '{TARGET_ROOM}' 방 발송 완료")
        return 0
    print(f"BLOCKED: 카톡 발송 실패(rc={rc}) — 본문은 위에 렌더됨")
    return 1


if __name__ == "__main__":
    sys.exit(main())
