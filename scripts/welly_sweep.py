#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/welly_sweep.py — 자율 웰리(Autonomous Welly) 스윕 오케스트레이터 (2026-06-26)

★현 단계 = 1관문 + MVP(dry-run 관찰 전용). 자율 실행(ON-A/ON-B)은 OFF.

흐름(스윕 1회):
  1. 항목 로드
       - 표류 입력 = build_board와 동일: fetch_gas_items() + fetch_queue_items()
       - dedup/ship_no 입력 = 원시 status/_queue.json 직독(ship_no=int 필드)
  2. 감지·집합 분리
       - dedup / ship_no 충돌 = 원시 _queue.json 활성(PENDING/IN_PROGRESS)
       - 표류(drift) = hangro_board._classify(...)["drift"] 직독(부분 술어 재구현 금지)
  3. 분류 = welly_sweep_classifier.classify(item, drift_ids)
  4. 디스패치 — dry-run에선 실제 변경/커밋 안 함(분기만)
  5. 보고 = 텔레그램 1줄(키 있을 때만) + 콘솔 + 자율로그 jsonl

계획: .omc/plans/autonomous-welly-loop.md (T3·MVP)
안전: dry-run 기본 · 결재영역 하드 게이트 · fail-open · 실제 큐 변경 없음.

사용:
  python scripts/welly_sweep.py            # dry-run(기본)
  python scripts/welly_sweep.py --json     # 분류 결과 JSON도 출력
  # --execute 는 분기만 존재 — 1관문 미통과로 이번 단계 미사용(차단).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 경로 ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent           # scripts/
_REPO = _HERE.parent                              # welperion-automation/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

QUEUE_PATH = _REPO / "status" / "_queue.json"
LOG_DIR = _REPO / ".omc" / "logs" / "welly_sweep"

# stdout 한글 안전(Windows cp949).
#   ※ hangro_board.py와 동일 가드 플래그(_welp_stdout_wrapped)를 공유 — import 시 이중래핑되면
#     먼저 만든 wrapper가 GC되며 버퍼를 닫아 'closed file' 버그가 난다(hangro_board 주석 참조).
if hasattr(sys.stdout, "buffer") and not getattr(sys, "_welp_stdout_wrapped", False):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys._welp_stdout_wrapped = True

import welly_sweep_classifier as wsc  # noqa: E402

_ACTIVE = {"PENDING", "IN_PROGRESS", "진행중", "대기"}


def _kst_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=9)


def _load_raw_queue() -> list[dict]:
    """원시 status/_queue.json 직독(ship_no=int 보존). fail-open=[]."""
    try:
        rows = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except Exception as e:
        print(f"[WARN] _queue.json 읽기 실패: {e}", file=sys.stderr)
        return []


def _norm_title(t: str) -> str:
    import re
    return re.sub(r"\s+", " ", str(t or "").strip()).lower()


def detect_dedup_and_ship_conflicts(raw: list[dict]) -> tuple[set[str], set[str]]:
    """원시 큐 활성 항목에서 ⓐ완전중복(task_id/정규화 title) ⓑclevel 내 ship_no 충돌 감지.

    반환: (dup_task_ids, ship_conflict_task_ids).
    중복은 '2번째 이후' 출현분을 후보로 표기(첫 출현은 보존). 파괴는 안 한다(감지만).
    """
    active = [r for r in raw if str(r.get("status", "")).upper() in
              {"PENDING", "IN_PROGRESS"} or str(r.get("status", "")) in _ACTIVE]

    dup_ids: set[str] = set()
    seen_tid: set[str] = set()
    seen_title: set[str] = set()
    for r in active:
        tid = str(r.get("task_id", "") or "")
        tkey = _norm_title(r.get("title", ""))
        is_dup = False
        if tid and tid in seen_tid:
            is_dup = True
        if tkey and tkey in seen_title:
            is_dup = True
        if is_dup:
            dup_ids.add(tid)
        if tid:
            seen_tid.add(tid)
        if tkey:
            seen_title.add(tkey)

    # ship_no 충돌 = 같은 clevel 내 동일 ship_no(int)를 가진 항목이 2건 이상.
    by_clevel: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in active:
        sn = r.get("ship_no")
        if not isinstance(sn, int):
            continue
        clv = str(r.get("clevel", "") or "").lower()
        by_clevel[clv][sn].append(str(r.get("task_id", "") or ""))
    ship_conflict_ids: set[str] = set()
    for clv, sns in by_clevel.items():
        for sn, tids in sns.items():
            if len(tids) > 1:
                ship_conflict_ids.update(t for t in tids if t)
    return dup_ids, ship_conflict_ids


def fetch_drift_ids() -> set[str]:
    """표류 집합 단일출처 — hangro_board._classify(build_board와 동일 입력)["drift"].

    부분 술어 재구현·import 금지(§0.1 원칙4). gas fetch 실패/게이트 시 빈 gas로 degrade
    (welly 런타임 GAS 가용성은 open-question — fail-open).
    """
    try:
        from hangro_board import fetch_gas_items, fetch_queue_items, _classify
        try:
            gas_items = fetch_gas_items()
        except Exception as e:
            print(f"[WARN] fetch_gas_items 실패(빈 gas degrade): {e}", file=sys.stderr)
            gas_items = []
        queue_items = fetch_queue_items()
        secs = _classify(gas_items + queue_items)
        return {str(it.get("id", "")) for it in secs.get("drift", [])}
    except Exception as e:
        print(f"[WARN] 표류 단일출처 호출 실패(fail-open): {e}", file=sys.stderr)
        return set()


def build_items(raw: list[dict], dup_ids: set[str], ship_ids: set[str]) -> list[dict]:
    """분류기 입력 dict 리스트 — fetch_queue_items 정규화 + 기계적 보조키(_dup·_ship_conflict)."""
    items = []
    for r in raw:
        st = str(r.get("status", "") or "")
        if "폐기" in st:
            continue
        tid = str(r.get("task_id", "") or "")
        items.append({
            "id": tid,
            "title": str(r.get("title", "") or ""),
            "owner": str(r.get("clevel", "") or "").upper(),
            "status": st,
            "next": str(r.get("next") or "").strip(),
            "terminal": bool(r.get("terminal", False)),
            "ship_no": r.get("ship_no"),
            "_raw_summary": str(r.get("note") or r.get("summary") or "").strip(),
            "_dup": tid in dup_ids,
            "_ship_conflict": tid in ship_ids,
        })
    return items


def run_sweep(execute: bool = False, max_n: int = 3) -> dict:
    """스윕 1회. dry-run 기본(execute=False)에선 실제 변경/커밋 0.

    반환: 카운트·분류결과 요약 dict.
    """
    raw = _load_raw_queue()
    dup_ids, ship_ids = detect_dedup_and_ship_conflicts(raw)
    drift_ids = fetch_drift_ids()
    items = build_items(raw, dup_ids, ship_ids)

    counts = {"AUTO_EXEC": 0, "GM_GATE": 0, "GM_INTERVIEW": 0, "HOLD": 0, "GUARD_BLOCK": 0}
    results = []
    for it in items:
        v = wsc.classify(it, drift_ids)
        counts[v.verdict] = counts.get(v.verdict, 0) + 1
        results.append({
            "task_id": it["id"],
            "verdict": v.verdict,
            "reason": v.reason,
            "evidence": v.evidence,
        })

    # ── 디스패치(분기만) — dry-run에선 실제 실행/커밋 없음. ─────────────────
    #   --execute 는 1관문 미통과로 이번 단계 차단(아래 main에서 거부).
    #   ON-A 활성화 전까지 AUTO_EXEC도 dry-run 보고만.
    auto_n = counts["AUTO_EXEC"]

    summary = {
        "ts": _kst_now().isoformat(),
        "dry_run": not execute,
        "drift_count": len(drift_ids),
        "dedup_count": len(dup_ids),
        "ship_conflict_count": len(ship_ids),
        "counts": counts,
        "results": results,
    }

    _write_log(summary)
    _report(summary)
    return summary


def _write_log(summary: dict) -> None:
    """자율로그 jsonl append — 줄당 1판정 + 1요약줄. fail-open."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = _kst_now().strftime("%Y-%m-%d")
        path = LOG_DIR / f"{day}.jsonl"
        lines = []
        ts = summary["ts"]
        for r in summary["results"]:
            lines.append(json.dumps({
                "ts": ts,
                "task_id": r["task_id"],
                "verdict": r["verdict"],
                "reason": r["reason"],
                "dry_run": summary["dry_run"],
            }, ensure_ascii=False))
        lines.append(json.dumps({
            "ts": ts,
            "kind": "sweep_summary",
            "dry_run": summary["dry_run"],
            "counts": summary["counts"],
            "drift_count": summary["drift_count"],
            "dedup_count": summary["dedup_count"],
            "ship_conflict_count": summary["ship_conflict_count"],
        }, ensure_ascii=False))
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        print(f"[WARN] 자율로그 기록 실패(fail-open): {e}", file=sys.stderr)


def _one_line(summary: dict) -> str:
    c = summary["counts"]
    tag = "dry-run" if summary["dry_run"] else "execute"
    return (
        f"🔍 웰리 스윕 {tag}: 자율후보 {c['AUTO_EXEC']}"
        f"·게이트 {c['GM_GATE']}·모호 {c['GM_INTERVIEW']}·보류 {c['HOLD']}"
        f"·가드차단 {c['GUARD_BLOCK']} "
        f"(표류 {summary['drift_count']}·중복 {summary['dedup_count']}"
        f"·배번호충돌 {summary['ship_conflict_count']})"
    )


def _report(summary: dict) -> None:
    """텔레그램 1줄 — dry-run에선 콘솔+로그로 충분, 키 있을 때만 실발송(open-question)."""
    line = _one_line(summary)
    print(line)
    # 텔레그램 실발송은 키 있을 때만(clevel_post_action send 패턴 재사용).
    try:
        import os
        if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
            print("[INFO] 텔레그램 키 없음 — 콘솔+로그만(dry-run 충분).")
            return
        _pkg = _REPO / "wellperion-agents"
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        from telegram_notifier import TelegramNotifier
        TelegramNotifier().send(line)
    except Exception as e:
        print(f"[WARN] 텔레그램 발송 실패(fail-open): {e}", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description="자율 웰리 스윕(현 단계=dry-run 관찰 전용)")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="감지·분류·보고만(기본·이번 단계 강제)")
    p.add_argument("--execute", action="store_true",
                   help="[차단] 자율 실행 — 1관문 미통과로 이번 단계 미사용")
    p.add_argument("--max", type=int, default=3, help="1스윕 최대 자율 실행 건수(ON 단계용)")
    p.add_argument("--mode", choices=["A", "B"], default="A",
                   help="A=기계적 2종(dedup+ship_no) / B=보류(안전기제 선행)")
    p.add_argument("--json", action="store_true", help="분류 결과 JSON도 출력")
    args = p.parse_args()

    if args.execute:
        # 안전장치: 1관문(게이트0+롤백+디스패치+인증 실증) 미통과 → execute 영구 차단.
        print("[BLOCKED] --execute 는 1관문 미통과로 비활성(이번 단계=dry-run 관찰 전용). "
              "자율 실행 OFF.", file=sys.stderr)
        sys.exit(2)

    summary = run_sweep(execute=False, max_n=args.max)
    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
