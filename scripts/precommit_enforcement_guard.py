#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_enforcement_guard.py — 화이트리스트 코드강제 pre-commit 가드 (AI 자율화 ③)

ssot/enforcement.py 엔진을 pre-commit 길목에 연결한다.
차단 대상 4종 중 pre-commit 으로 잡을 수 있는 3종을 감지:
  1) 공식값·약속 무단 변경 (canon_values.json·약속.json)
  2) 금지 경로·파일 변경    (결재 GAS·구버전 미끼 등 블랙리스트)
  3) 보안 차단 라이브 발효  (TOKEN_ENFORCE on 류 staged 변경)
  (4) 결제·지출 = 결재현황 게이트 재사용 — 신규 차단 없음)

【모드별 동작】
  - off   : 완전 무동작 → exit 0.
  - warn  : 위반 감지·로그(+선택 텔레그램)만 → 항상 exit 0(절대 비차단).
  - block : 위반 시 차단 → exit 1 (GM 명시 go 후에만).
  - GM 승인 우회([GM-approved] 토큰/플래그파일) → 위반이어도 통과(로그 BYPASS).

【안전 원칙】
  엔진/가드 내부 예외 = 전부 fail-open(exit 0). 가드 버그로 자동 커밋·푸시 마비 금지.
  이 레포는 watcher 가 5분마다 자동 커밋·푸시 → warn 이 막으면 대형사고.
"""
import sys
import io

try:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from pathlib import Path

# ssot/ 를 import 경로에 추가
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    try:
        from ssot import enforcement as E
    except Exception as exc:
        # 엔진 import 실패 = fail-open
        try:
            sys.stderr.write(f"[enforcement-guard][WARN] 엔진 로드 실패 — 통과: {exc!r}\n")
        except Exception:
            pass
        return 0

    try:
        mode = E.get_mode()
        if mode == E.ENFORCE_MODE_OFF:
            return 0  # 완전 무동작

        files = E.staged_files()
        if not files:
            return 0

        v_canon = E.check_canon_promise_change(files)
        v_path = E.check_forbidden_path_change(files)
        v_sec = E.check_security_live_activation(files)

        violations = []
        if v_canon:
            violations.append(("공식값·약속 무단 변경", v_canon))
        if v_path:
            violations.append(("금지 경로·파일 변경", v_path))
        if v_sec:
            violations.append(("보안 차단 라이브 발효", v_sec))

        if not violations:
            return 0  # 위반 없음

        # GM 승인 우회?
        if E.is_bypassed():
            for kind, items in violations:
                E.log_event(
                    "BYPASS",
                    f"{kind} 감지했으나 GM 승인 우회([GM-approved]/플래그) → 통과: {items[:3]}",
                )
            print("[enforcement-guard] ✅ GM 승인 우회 — 위반 통과(로그 기록)")
            return 0

        # 위반 출력 + 로그
        print("\n[enforcement-guard] ⚠️  화이트리스트 코드강제 위반 감지:")
        for kind, items in violations:
            shown = ", ".join(str(x) for x in items[:3])
            more = "..." if len(items) > 3 else ""
            print(f"  - {kind}: {shown}{more}")
            E.log_event("VIOLATION", f"{kind}: {items}")
            E.notify_warn(f"{kind}: {shown}{more}")

        if E.should_block(mode):
            print("  → mode=block: 커밋 차단. 정당 변경이면 커밋 메시지에 [GM-approved] 추가 후 재커밋.")
            return 1

        # warn(또는 알 수 없는 값=warn 폴백): 절대 비차단
        print("  → mode=warn: 감지·로그만, 커밋은 통과(차단하려면 GM go 후 enforcement_mode.json mode=block).")
        return 0

    except Exception as exc:
        # 전체 실패 → fail-open
        try:
            sys.stderr.write(f"[enforcement-guard][WARN] 내부 오류 — 통과(fail-open): {exc!r}\n")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
