#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ceo_evening_wrap.py - AI CEO 하루 마감 루틴 (세션 종료 대칭)
v1.0 (2026-05-30)

GM 아이디어(2026-05-30): "CLI 가동 on/off마다 하는 것도 좋겠다."
  on(세션시작) = ceo_morning_pipeline.py (아침 할일 수집·정리·배정) — 이미 구현.
  off(세션종료) = 본 스크립트 (하루 마감 보고).

하는 일(3가지를 모아 텔레그램 일상어로 보고):
  ① 오늘 한 일   : 오늘자 git 커밋(완료 표시) + 오늘 종결된(processed) 큐 항목
  ② 내일/남은 할일: 미완·대기 큐(status/_queue.json + status/{cl}.json active) 리스트
  ③ 미완 이슈 요약: 위 미완 중 'GM 답 필요(모호)' 신호가 있는 것만 별도로

수집 로직은 새로 만들지 않고 ceo_morning_pipeline 의 함수를 그대로 재사용한다
(stage1_collect_classify / today_kr / CLEVEL_OWNER 등). 신규 코드 최소화.

실행:
  python ceo_evening_wrap.py --dry-run          # 텔레그램 발송·마커 생성 없이 로그만
  python ceo_evening_wrap.py                     # 실제 발송 + 마커 기록
  python ceo_evening_wrap.py --once-per-day      # 오늘 이미 돌았으면 즉시 스킵(세션종료 훅용)

하루 1회 가드(--once-per-day):
  오늘자 마커 status/evening_wraps/YYYY-MM-DD.json 이 이미 있으면 즉시 스킵(exit 0).
  같은 날 CLI 세션을 여러 번 껐다 켜도 마감 보고는 1회만 실가동.
  (dry-run 은 마커를 만들지 않으므로 가드를 소모하지 않는다.)

보안: PIN/토큰 등 하드코딩 금지. .env / 환경변수만 참조(telegram_notifier 경유).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 한글 안전 출력
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 경로 ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent          # wellperion-agents/scripts
PACKAGE_ROOT = BASE.parent                       # wellperion-agents
REPO = PACKAGE_ROOT.parent                       # welperion-automation (repo root)
STATUS_DIR = REPO / "status"
QUEUE_PATH = STATUS_DIR / "_queue.json"
WRAP_DIR = STATUS_DIR / "evening_wraps"          # 마커: 일자별 마감 요약 JSON

# telegram_notifier + ceo_morning_pipeline import 경로
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# 아침 파이프라인 수집·분류 로직 재사용 (신규 최소화)
from ceo_morning_pipeline import (  # noqa: E402
    stage1_collect_classify,
    today_kr,
    CLEVEL_OWNER,
    CLEVEL_ORDER,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_marker() -> Path:
    """오늘자 마감 요약 파일 경로 = 하루 1회 가드 마커."""
    return WRAP_DIR / (datetime.now().strftime("%Y-%m-%d") + ".json")


def already_ran_today() -> bool:
    return today_marker().exists()


# ── ① 오늘 한 일 ─────────────────────────────────────────────────────────────

def today_commits() -> list[str]:
    """오늘자(로컬 날짜) git 커밋 제목 목록. 자동 changelog 커밋은 제외(노이즈)."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "log",
             f"--since={today} 00:00:00", f"--until={today} 23:59:59",
             "--format=%s"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
    except Exception:
        return []
    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # 자동 changelog 갱신 커밋은 사람 작업이 아니므로 제외
        if line.startswith("auto(changelog)"):
            continue
        out.append(line)
    return out


def today_done_queue() -> list[dict]:
    """오늘 종결(processed_at 이 오늘) 처리된 큐 항목."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for q in data if isinstance(data, list) else []:
        st = (q.get("status") or "").upper()
        proc_at = str(q.get("processed_at") or "")
        if st == "DONE" and proc_at.startswith(today):
            out.append({
                "task_id": q.get("task_id", ""),
                "clevel": (q.get("clevel") or "").upper(),
                "title": q.get("title", ""),
            })
    return out


# ── 마감 보고 빌드 ───────────────────────────────────────────────────────────

def build_evening_report(commits: list[str], done_q: list[dict],
                         remaining: list[dict], issues: list[dict]) -> str:
    """GM 일상어 마감 보고."""
    lines = []
    lines.append(f"🌙 AI CEO 하루 마감 — {today_kr()}")
    lines.append("━" * 22)

    # ① 오늘 한 일
    lines.append(f"〈오늘 한 일〉 마무리 {len(commits)}건 + 끝낸 업무 {len(done_q)}건")
    if commits:
        for c in commits[:8]:
            lines.append(f"· {c[:50]}")
        if len(commits) > 8:
            lines.append(f"· … 외 {len(commits) - 8}건 더")
    if done_q:
        for d in done_q:
            title = (d.get("title") or "")[:42]
            lines.append(f"✓ [{d.get('clevel','?')}] {title}")
    if not commits and not done_q:
        lines.append("· (오늘 기록된 마무리·완료 업무 없음)")
    lines.append("")

    # ② 내일/남은 할일
    lines.append(f"〈내일·남은 할일〉 {len(remaining)}건")
    if remaining:
        for it in remaining:
            cl = it.get("clevel") or "?"
            owner = CLEVEL_OWNER.get(cl, "?")
            title = (it.get("title") or "")[:40]
            lines.append(f"· [{cl}/{owner}] {title}")
    else:
        lines.append("· 남은 할일 없음 — 깔끔하게 마감!")
    lines.append("")

    # ③ 미완 이슈 (GM 답 필요한 것만)
    if issues:
        lines.append(f"〈❓ GM 결정이 필요해 멈춰둔 것〉 {len(issues)}건")
        for i, a in enumerate(issues, 1):
            title = (a.get("title") or "")[:38]
            lines.append(f"{i}. {title}")
            lines.append(f"   → 왜: {a.get('ambiguous_reason','')}")
        lines.append("")

    lines.append("〈기록 위치〉 오늘 마감 요약은 status/evening_wraps/ 에 저장돼요.")
    lines.append("내일 아침 CLI를 켜면 남은 할일이 다시 정리돼 올라와요.")
    return "\n".join(lines)


def save_marker(commits: list[str], done_q: list[dict],
                remaining: list[dict], issues: list[dict], dry_run: bool) -> Path:
    marker = {
        "generated_at": now_iso(),
        "date": today_kr(),
        "today_done": {
            "commits": commits,
            "queue_done": [{"task_id": d.get("task_id"), "clevel": d.get("clevel"),
                            "title": d.get("title")} for d in done_q],
        },
        "remaining": [
            {"task_id": it.get("task_id"), "clevel": it.get("clevel"),
             "status": it.get("status"), "title": it.get("title"),
             "source": it.get("source")}
            for it in remaining
        ],
        "issues_need_gm": [
            {"task_id": a.get("task_id"), "title": a.get("title"),
             "reason": a.get("ambiguous_reason")}
            for a in issues
        ],
    }
    out = today_marker()
    text = json.dumps(marker, ensure_ascii=False, indent=2)
    if dry_run:
        print(f"[DRY-RUN] 마감 마커 저장 예정 → {out} ({len(text)} bytes, 기록 안 함)")
    else:
        WRAP_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"[OK] 마감 마커 저장 → {out}")
    return out


def send_report(report: str, dry_run: bool) -> bool:
    if dry_run:
        print("\n========== [DRY-RUN] 텔레그램 마감 보고 (발송 안 함) ==========")
        print(report)
        print("========== [DRY-RUN] 끝 ==========\n")
        return True
    try:
        from telegram_notifier import TelegramNotifier
        tg = TelegramNotifier()
        r = tg.send(report)
        ok = bool(r.get("ok")) if isinstance(r, dict) else False
        print(f"[OK] 텔레그램 마감 보고 발송 — ok={ok}")
        return ok
    except Exception as exc:
        print(f"[FAIL] 텔레그램 발송 실패: {exc}", file=sys.stderr)
        return False


# ── 메인 ─────────────────────────────────────────────────────────────────────

def run_wrap(dry_run: bool, once_per_day: bool = False) -> int:
    # 하루 1회 가드: 오늘 이미 마감했으면 즉시 스킵. dry-run 은 마커를 안 만들어 가드 미소모.
    if once_per_day and not dry_run and already_ran_today():
        print(f"[SKIP] 오늘({datetime.now().strftime('%Y-%m-%d')}) 마감 루틴 이미 실행됨 "
              f"→ {today_marker()} (스킵)")
        return 0

    print(f"=== CEO 하루 마감 루틴 시작 (dry_run={dry_run}, once_per_day={once_per_day}) ===")

    # ① 오늘 한 일
    commits = today_commits()
    done_q = today_done_queue()
    print(f"[① 오늘 한 일] 커밋 {len(commits)}건 + 완료 큐 {len(done_q)}건")

    # ②③ 남은 할일 + 미완 이슈 — 아침 파이프라인 수집·분류 재사용
    s1 = stage1_collect_classify()
    remaining = s1["clear"] + s1["ambiguous"]      # 미결 전체(명확+모호)
    issues = s1["ambiguous"]                         # GM 답 필요한 것만
    print(f"[② 남은 할일] {len(remaining)}건 (그중 미완 이슈 {len(issues)}건)")

    # 보고 빌드 + 발송 + 마커
    report = build_evening_report(commits, done_q, remaining, issues)
    sent = send_report(report, dry_run)
    save_marker(commits, done_q, remaining, issues, dry_run)
    print(f"[보고] {'(dry-run 출력)' if dry_run else '발송'} — {'OK' if sent else 'FAIL'}")

    print(f"=== 마감 루틴 종료 — {'성공' if sent else '실패'} ===")
    return 0 if sent else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="AI CEO 하루 마감 루틴 (세션 종료)")
    ap.add_argument("--dry-run", action="store_true",
                    help="텔레그램 발송·마커 기록을 막고 로그만 출력")
    ap.add_argument("--once-per-day", action="store_true",
                    help="오늘자 마커가 이미 있으면 즉시 스킵 (세션 종료 훅용 가드)")
    args = ap.parse_args()
    return run_wrap(dry_run=args.dry_run, once_per_day=args.once_per_day)


if __name__ == "__main__":
    sys.exit(main())
