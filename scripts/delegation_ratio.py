#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""역할별 위임 비율 — 메인 창이 직접 실행한 것 대비 서브에이전트에 넘긴 비율 (배 12745 · GM 2026-09-18).

왜: 메인 창이 실행까지 직접 하면 비싼 모델이 루틴을 먹고 GM 화면이 과정 중계로 찬다.
    「위임하라」는 규칙은 숫자로 재야 지켜진다 — 아침 표 한 줄로 스스로 잰다.

무엇을: ~/.claude/projects/<이 저장소>/*.jsonl(메인 세션 기록 · 서브에이전트 기록은 하위 폴더라
    저절로 빠진다)에서 최근 7일 안에 도구호출 100회 이상인 세션을 골라
    역할별로 (Agent 호출 수) / (Edit+Write+Bash 호출 수) 를 낸다.
    역할 = 첫 사용자 메시지(부팅 지시문)의 ai-xxx.md 파일명 → 없으면 닉네임 낱말 → 못 잡으면 「미상」.

출력: 「🤝 위임 비율 — 시토 12% · 웰리 3% · …(7일 · 세션 N개)」 한 줄. --json 은 원자료.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# C:\Users\jjky0\welperion-automation → C--Users-jjky0-welperion-automation (Claude Code 가 쓰는 폴더 이름 규칙)
SESS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9-]", "-", ROOT))
DAYS = 7
MIN_CALLS = 100
DIRECT = ("Edit", "Write", "MultiEdit", "Bash")
DELEGATE = ("Agent", "Task")
NICK = {"ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모", "coo": "시우",
        "cpo": "시포", "cto": "시토", "cbo": "시보"}
ROLE_FILE = re.compile(r"ai-(ceo|cfo|chro|cmo|coo|cpo|cto|cbo)\.md")
NICK_WORD = re.compile("|".join(NICK.values()))


def _role(first_user_text: str) -> str:
    m = ROLE_FILE.search(first_user_text)
    if m:
        return NICK[m.group(1)]
    m = NICK_WORD.search(first_user_text)
    return m.group(0) if m else "미상"


def _scan(path: str) -> dict | None:
    """세션 하나 → {'role','direct','delegate','calls'} · 100회 미만이면 None."""
    first = None
    direct = delegate = calls = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = r.get("type")
            c = (r.get("message") or {}).get("content")
            if t == "user" and first is None:
                first = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            elif t == "assistant" and isinstance(c, list):
                for b in c:
                    if b.get("type") != "tool_use":
                        continue
                    calls += 1
                    n = b.get("name")
                    if n in DIRECT:
                        direct += 1
                    elif n in DELEGATE:
                        delegate += 1
    if calls < MIN_CALLS:
        return None
    return {"role": _role(first or ""), "direct": direct, "delegate": delegate, "calls": calls}


def measure(days: int = DAYS) -> dict:
    cut = dt.datetime.now().timestamp() - days * 86400
    per: dict[str, dict] = {}
    n = 0
    for p in glob.glob(os.path.join(SESS_DIR, "*.jsonl")):
        if os.path.getmtime(p) < cut:
            continue
        s = _scan(p)
        if not s:
            continue
        n += 1
        d = per.setdefault(s["role"], {"direct": 0, "delegate": 0, "sessions": 0})
        d["direct"] += s["direct"]
        d["delegate"] += s["delegate"]
        d["sessions"] += 1
    for d in per.values():
        d["ratio_pct"] = round(100 * d["delegate"] / d["direct"]) if d["direct"] else (100 if d["delegate"] else 0)
    return {"days": days, "sessions": n, "roles": per}


def line(m: dict | None = None) -> str:
    m = m or measure()
    parts = [f"{r} {d['ratio_pct']}%" for r, d in
             sorted(m["roles"].items(), key=lambda kv: -kv[1]["ratio_pct"])]
    body = " · ".join(parts) if parts else "측정 안 됨(100회 이상 세션 없음)"
    return f"🤝 위임 비율 — {body}({m['days']}일 · 세션 {m['sessions']}개)"


def _selftest() -> None:
    assert _role("… wellperion-agents\\.claude\\agents\\ai-cto.md 읽고 …") == "시토"
    assert _role("웰리·시토 두 창이 같이 뜬다") == "웰리", "파일명 없으면 첫 닉네임"
    assert _role("아무 표식 없음") == "미상"
    fake = {"days": 7, "sessions": 2, "roles": {"시토": {"ratio_pct": 12}, "웰리": {"ratio_pct": 30}}}
    assert line(fake) == "🤝 위임 비율 — 웰리 30% · 시토 12%(7일 · 세션 2개)", line(fake)
    assert line({"days": 7, "sessions": 0, "roles": {}}).startswith("🤝 위임 비율 — 측정 안 됨")
    assert os.path.isdir(SESS_DIR), f"세션 폴더가 없다: {SESS_DIR}"
    print("delegation_ratio selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--json" in sys.argv:
        print(json.dumps(measure(), ensure_ascii=False, indent=1))
    else:
        print(line())
