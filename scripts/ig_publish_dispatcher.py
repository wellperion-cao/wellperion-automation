"""M5 승인 → 로컬 발행 디스패처 (인터랙티브 데스크톱 세션 전용, 2026-06-04 AI CTO)

배경(오늘 실패 원인 #2): IG 발행기는 headless=False(headful)라 데스크톱이 없는
백그라운드/세션0 에서 못 뜬다. 텔레그램 pub: 콜백이 백그라운드 subprocess 로 발행기를
띄우는 경로가 이래서 실패했다. → 발행은 '로그온 사용자 데스크톱 세션'에서만 성공한다.

해결: 이 디스패처를 Windows Task Scheduler 에 매일 07:30, '사용자 로그온 시에만 실행'
(숨김 vbs 금지 · 데스크톱 보이는 인터랙티브)으로 등록한다. 그러면 그 시점까지 GM 이
M5(웰페리온 ERP)에서 [승인]한 IG 개인계정 건이 일괄 발행된다.
(GM 검수·M5 승인은 아무때나 → 07:30 배치 발행)

설계: 발행 로직·중복발행 가드·URL false-negative 폴백·status 전이·텔레그램 보고는
ig_review_publish_watcher 가 이미 완비. 디스패처는 그 run_once 를 인터랙티브 세션
'포그라운드'로 1회 호출하는 얇은 래퍼다(가드 중복 구현 금지 = 단일 출처 유지).

실행:
  발행:        python scripts\\ig_publish_dispatcher.py
  로직만(테스트): python scripts\\ig_publish_dispatcher.py --dry-run

종료코드: 발행 성공 건수(>=0). 예외 시 1.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 콘솔 인코딩 하드닝 (cp949 콘솔에서 이모지/대시 print 시 죽지 않게)
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconf = getattr(_stream, "reconfigure", None) if _stream is not None else None
    if _reconf is not None:
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 같은 디렉터리의 watcher 모듈 재사용 (발행 로직 단일 출처)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ig_review_publish_watcher as watcher  # noqa: E402


def _warn_if_session0() -> None:
    """세션0/비대화 세션이면 경고 (headful 발행 실패 가능성 사전 안내).

    Windows 에서 GetProcessWindowStation/대화형 여부를 간이 판정. 실패해도 진행만 막지 않음
    (판정 자체가 불확실할 수 있어 발행을 차단하지 않고 경고만 — 오탐으로 발행 누락 방지).
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        # GetForegroundWindow 가 0 이고 데스크톱 핸들도 없으면 비대화형 의심
        hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_READOBJECTS
        if not hdesk:
            print(
                "[WARN] 입력 데스크톱 접근 불가 — 비대화형 세션(세션0/숨김) 의심. "
                "headful 발행이 실패할 수 있음(이 디스패처는 로그온 사용자 세션에서 실행해야 함)."
            )
        else:
            ctypes.windll.user32.CloseDesktop(hdesk)
            print("[INFO] 대화형 데스크톱 세션 확인 — headful 발행 가능 환경.")
        _ = user32  # silence linter
    except Exception:
        # 판정 실패는 치명적이지 않음 — 진행
        print("[INFO] 세션 유형 판정 생략(비치명) — 발행 계속.")


def main() -> int:
    p = argparse.ArgumentParser(
        description="M5 승인 → 로컬 발행 디스패처 (07:30 배치 · 인터랙티브 데스크톱 전용)"
    )
    p.add_argument("--dry-run", action="store_true", help="발행 없이 로직만 (승인 건 스캔만)")
    args = p.parse_args()

    print(f"[INFO] === IG 발행 디스패처 시작 === {datetime.now().isoformat(timespec='seconds')} (dry_run={args.dry_run})")
    if not args.dry_run:
        _warn_if_session0()

    try:
        published = watcher.run_once(args.dry_run)
    except Exception as exc:
        print(f"[ERROR] 디스패처 사이클 예외: {exc}")
        # 텔레그램 보고는 watcher 내부에서 처리. 여기선 비0 종료만.
        return 1

    print(f"[INFO] === IG 발행 디스패처 종료 === 발행 {published}건")
    return published if isinstance(published, int) else 0


if __name__ == "__main__":
    sys.exit(main())
