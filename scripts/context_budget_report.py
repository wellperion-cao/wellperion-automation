#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
context_budget_report.py — 매 턴 로드되는 '상시 컨텍스트' 토큰 소비 측정기

배경 (2026-06-15 AI CTO · GM 지시 C):
  매 턴 자동으로 읽히는 것들(메모리·CLAUDE·에이전트 프롬프트·큐·캐시)이
  주중에 누적되면 토큰을 많이 먹는다. 일요일 주간 컨텍스트 정비(T2 CTX-CTO)에서
  이 측정값을 보고 '임계 초과 항목부터 슬림화' 한다. (측정 = 자동 / 삭제 = 사람 확인)

동작:
  알려진 무거운 파일들의 줄수·바이트·추정토큰을 재서 status/context_budget.json 에
  기록(직전 측정 대비 추세 포함). 읽기 전용 — 어떤 파일도 수정하지 않는다.

사용:
  python scripts/context_budget_report.py            # 측정 + JSON 기록 + 요약 출력
  python scripts/context_budget_report.py --notify   # + 텔레그램 1줄 추세(best-effort)

추정토큰: 한/영 혼합 러프 추정 = 문자수 / 3 (정확값 아님 — 주간 '추세' 판단용).
"""

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"C:\Users\jjky0\welperion-automation")
MEM_DIR = Path(r"C:\Users\jjky0\.claude\projects\C--Users-jjky0-welperion-automation\memory")
OUT = REPO / "status" / "context_budget.json"

# 측정 대상: (표시명, 경로 또는 glob, 종류)
TARGETS = [
    ("MEMORY.md 인덱스", MEM_DIR / "MEMORY.md", "file"),
    ("memory/*.md 전체", MEM_DIR, "memdir"),
    ("CLAUDE.md(프로젝트)", REPO / "CLAUDE.md", "file"),
    ("에이전트 프롬프트 ai-*.md", REPO / "wellperion-agents" / ".claude" / "agents", "agentdir"),
    ("status/_queue.json", REPO / "status" / "_queue.json", "json"),
    ("review_queue.json", REPO / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json", "json"),
]

# 임계(추정토큰) — 초과 시 일요일 정비에서 슬림화 우선 검토
THRESHOLDS = {
    "MEMORY.md 인덱스": 6000,
    "memory/*.md 전체": 120000,
    "CLAUDE.md(프로젝트)": 5000,
    "에이전트 프롬프트 ai-*.md": 20000,
    "status/_queue.json": 30000,
    "review_queue.json": 25000,
}


def measure_text(p: Path):
    try:
        b = p.read_bytes()
    except Exception:
        return None
    try:
        txt = b.decode("utf-8", "replace")
    except Exception:
        txt = ""
    return {"lines": len(txt.splitlines()), "bytes": len(b), "approx_tokens": round(len(txt) / 3)}


def measure_dir(d: Path, pattern="*.md"):
    files = sorted(d.glob(pattern)) if d.exists() else []
    lines = chars = nbytes = 0
    for f in files:
        try:
            b = f.read_bytes()
            t = b.decode("utf-8", "replace")
            lines += len(t.splitlines()); chars += len(t); nbytes += len(b)
        except Exception:
            continue
    return {"count": len(files), "lines": lines, "bytes": nbytes, "approx_tokens": round(chars / 3)}


def measure_json_array(p: Path):
    m = measure_text(p) or {"lines": 0, "bytes": 0, "approx_tokens": 0}
    try:
        d = json.loads(p.read_bytes().decode("utf-8", "replace"))
        if isinstance(d, list):
            m["items"] = len(d)
            m["active"] = sum(1 for t in d if isinstance(t, dict) and t.get("status") in ("PENDING", "IN_PROGRESS", "검수대기", "승인", "발행검증대기"))
    except Exception:
        pass
    return m


def main():
    prev = {}
    if OUT.exists():
        try:
            prev = {i["name"]: i for i in json.loads(OUT.read_text(encoding="utf-8")).get("items", [])}
        except Exception:
            prev = {}

    items = []
    total = 0
    for name, path, kind in TARGETS:
        if kind == "memdir":
            m = measure_dir(path, "*.md")
        elif kind == "agentdir":
            m = measure_dir(path, "ai-*.md")
        elif kind == "json":
            m = measure_json_array(path)
        else:
            m = measure_text(path)
        if m is None:
            m = {"lines": 0, "bytes": 0, "approx_tokens": 0, "missing": True}
        tok = m.get("approx_tokens", 0)
        total += tok
        prev_tok = prev.get(name, {}).get("approx_tokens")
        m["name"] = name
        m["prev_tokens"] = prev_tok
        m["delta"] = (tok - prev_tok) if isinstance(prev_tok, int) else None
        m["threshold"] = THRESHOLDS.get(name)
        m["over"] = bool(m["threshold"]) and tok > m["threshold"]
        items.append(m)

    # measured 날짜는 인자로 주입 가능(스크립트 내 시계 사용 금지 환경 대비) — 없으면 환경/파일 mtime 회피
    measured = os.environ.get("BUDGET_DATE", "")
    report = {"measured": measured, "total_approx_tokens": total, "items": items}
    try:
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print("[WARN] JSON 기록 실패:", e)

    print("=== 상시 컨텍스트 토큰 budget (추정) ===")
    for m in items:
        arrow = ""
        if isinstance(m["delta"], int):
            arrow = ("▲%d" % m["delta"]) if m["delta"] > 0 else ("▼%d" % -m["delta"]) if m["delta"] < 0 else "—"
        flag = " ⚠️임계초과" if m["over"] else ""
        print("  %-26s %6d tok  %s%s" % (m["name"], m.get("approx_tokens", 0), arrow, flag))
    print("  %-26s %6d tok (합계)" % ("TOTAL", total))

    overs = [m["name"] for m in items if m["over"]]
    if overs:
        print("\n  → 일요일 정비 슬림화 우선:", ", ".join(overs))

    if "--notify" in sys.argv:
        _notify(total, overs, items)
    return 0


def _notify(total, overs, items):
    """텔레그램 1줄 추세 (best-effort)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / "telegram_bot" / ".env")
        import requests
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = os.environ.get("OWNER_ID") or os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat:
            return
        msg = "🗜️ 상시 컨텍스트 budget: 합계 ~%d tok" % total
        if overs:
            msg += "\n임계초과: " + ", ".join(overs) + " → 일요일 정비 슬림화"
        requests.post("https://api.telegram.org/bot%s/sendMessage" % token,
                      data={"chat_id": chat, "text": msg}, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
