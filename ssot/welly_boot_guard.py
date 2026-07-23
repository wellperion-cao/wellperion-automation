#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""welly_boot_guard.py — 웰리 부팅 가드 (INC-006 차단조치).

웰리가 켜질 때 한 화면에서 먼저 확인할 두 가지를 모아 보여준다:
  ① origin 에 안 올라간(미푸시) 로컬 커밋 — 라이브가 stale 일 위험
  ② review_queue 의 '검수대기'·'발행검증대기' 건 — 웰리 손이 필요한 건

배경(INC-006): 자동 커밋 8건이 push 안 돼 라이브 M5 검수페이지가 ~2.5h stale →
AI17 검수요청 미반영. 부팅 시 미푸시·검수대기를 먼저 보면 같은 사고를 조기에 잡는다.

사용:
  python ssot/welly_boot_guard.py

반환코드: 미푸시 커밋이 있거나(우선) 대기 건이 있으면 1, 모두 깨끗하면 0.
(부팅 SOP 안내용 — 커밋/실행을 막지 않는 단순 리포터)
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from integration_health import check_bridges  # 연동 다리 자가점검 단일 정의
except Exception:  # 모듈 부재·import 실패 시에도 부팅 가드는 계속
    check_bridges = None
QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
WAIT_STATUSES = ("검수대기", "발행검증대기")
REMOTE = "origin"
BRANCH = "master"


def _unpushed() -> tuple[int, list[str]]:
    """origin/master..HEAD 커밋 수 + 한 줄 요약 목록. 실패 시 (-1, [])."""
    try:
        r = subprocess.run(
            ["git", "log", f"{REMOTE}/{BRANCH}..HEAD", "--oneline", "--no-color"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return -1, []
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        return len(lines), lines
    except Exception:
        return -1, []


def _waiting() -> dict[str, list[dict]]:
    """review_queue 에서 대기 상태별 항목 묶음."""
    out: dict[str, list[dict]] = {s: [] for s in WAIT_STATUSES}
    if not QUEUE_PATH.exists():
        return out
    try:
        queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return out
    for item in queue:
        st = item.get("status")
        if st in out:
            out[st].append(item)
    return out


def main() -> int:
    print("=" * 52)
    print("  🚦 웰리 부팅 가드 (INC-006 — 미푸시·검수대기 감지)")
    print("=" * 52)

    flagged = False

    # ── ① 미푸시 커밋 ──────────────────────────────────────────────
    n, lines = _unpushed()
    print("\n[1] origin 미동기화(미푸시) 커밋")
    if n < 0:
        print("    ℹ️  확인 불가(원격 ref 없음/네트워크) — 수동 `git fetch` 후 재확인.")
    elif n == 0:
        print("    ✅ 없음 — 로컬 = origin/master 동기화 상태.")
    else:
        # 자가복구 창: 동시 커밋 경합으로 push 가 잠깐 밀린 순간 상태는 정상(스위퍼/다음 push 가 드레인).
        # 창(10분) 안이면 알림하지 않고, 그 이상 묵으면만 stale 로 본다 — 부팅 노이즈 제거.
        import time as _t
        _oldest = None
        try:
            _ar = subprocess.run(
                ["git", "log", f"{REMOTE}/{BRANCH}..HEAD", "--reverse", "--format=%ct"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=30,
            )
            if _ar.returncode == 0 and _ar.stdout.strip():
                _oldest = int(_ar.stdout.strip().splitlines()[0])
        except Exception:
            _oldest = None
        _age = int(_t.time() - _oldest) if _oldest else None
        if _age is not None and _age < 600:
            print(f"    ✅ {n}건 동기화 진행 중({_age}s, 자가복구 창 내) — 정상(스위퍼가 드레인).")
        else:
            flagged = True
            _agetxt = f" {_age // 60}분+ 정체" if _age else ""
            print(f"    ⚠️  {n}건 안 올라감{_agetxt} — 라이브 stale 위험. 즉시 `git push` 필요:")
            for ln in lines[:15]:
                print(f"        · {ln}")
            if n > 15:
                print(f"        … 외 {n - 15}건")

    # ── ② 검수대기 / 발행검증대기 ──────────────────────────────────
    waiting = _waiting()
    for st in WAIT_STATUSES:
        items = waiting[st]
        print(f"\n[2] review_queue '{st}'")
        if not items:
            print("    ✅ 없음.")
            continue
        flagged = True
        print(f"    ⚠️  {len(items)}건 — 웰리 처리 필요:")
        for item in items:
            iid = item.get("id", "-")
            title = item.get("title", "(제목 없음)")
            channel = item.get("channel", "")
            tail = f" / {channel}" if channel else ""
            print(f"        [{iid}] {title}{tail}")

    # ── ③ 🔗 연동 다리 자가점검 ──────────────────────────────────────
    print("\n[3] 🔗 연동 다리 자가점검 (데이터 소스 간 다리 생존)")
    if check_bridges is None:
        print("    ℹ️  점검 모듈 로드 불가 — scripts/integration_health.py 확인.")
    else:
        rows = check_bridges()
        ok_n = sum(1 for _, ok, _ in rows if ok)
        for nm, ok, detail in rows:
            print(f"    {'✅' if ok else '⚠️'} {nm}: {detail}")
        if ok_n < len(rows):
            flagged = True
            print(f"    ⚠️  다리 {len(rows) - ok_n}개 끊김 — 위 사유부터 복구할 것.")
        else:
            print(f"    ✅ 다리 {ok_n}개 전부 정상.")

    print("\n" + "=" * 52)
    if flagged:
        print("  ⚠️  위 항목을 먼저 처리하고 부팅 마무리할 것.")
    else:
        print("  ✅ 미푸시·검수대기·연동 다리 모두 정상 — 깨끗.")
    print("=" * 52)
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
