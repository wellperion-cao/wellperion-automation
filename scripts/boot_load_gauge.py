# -*- coding: utf-8 -*-
"""부팅 로드 게이지 — 역할별 부팅 시 밀어넣는 글자 수를 재서 status/boot_load.json 에
날짜별로 쌓는다(배1016 · 웰리 설계 2026-09-05). 다시 불어나면(약속 L20) 숫자로 보이게.

재는 것: 에이전트 md 1개 + 부팅 시 항상 같이 로드하는 스킬 2개(wellperion-boot ·
wellperion-gm-report) + 메모리 색인(MEMORY.md) + (있으면) boot_pack 슬라이스 출력.
프론트(자율현황 카드에 한 줄)는 이 배 범위 밖 — JSON 만 내고 웰리에게 배로 넘긴다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
MEMORY_INDEX = Path(r"C:\Users\jjky0\.claude\projects\C--Users-jjky0-welperion-automation\memory\MEMORY.md")
BOOT_SKILL = ROOT / ".claude" / "skills" / "wellperion-boot" / "SKILL.md"
REPORT_SKILL = ROOT / ".claude" / "skills" / "wellperion-gm-report" / "SKILL.md"
AGENTS_DIR = ROOT / "wellperion-agents" / ".claude" / "agents"
OUT_PATH = ROOT / "status" / "boot_load.json"
KST = timezone(timedelta(hours=9))

ROLES = ["ceo", "cfo", "chro", "cmo", "coo", "cpo", "cto", "cbo"]


def _len(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8"))
    except Exception:
        return 0


def _boot_pack_len(role: str) -> int:
    """배1014 가 만드는 중인 boot_pack — 있으면 잰다, 없거나 깨졌으면 0(부팅을 막지 않는다)."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import boot_pack  # type: ignore
        return len(boot_pack.build_pack(role))
    except Exception:
        return 0


def measure(role: str) -> dict:
    agent_md = _len(AGENTS_DIR / f"ai-{role}.md")
    boot_skill = _len(BOOT_SKILL)
    gm_report_skill = _len(REPORT_SKILL)
    memory_index = _len(MEMORY_INDEX)
    boot_pack_out = _boot_pack_len(role)
    total = agent_md + boot_skill + gm_report_skill + memory_index + boot_pack_out
    return {
        "agent_md": agent_md,
        "boot_skill": boot_skill,
        "gm_report_skill": gm_report_skill,
        "memory_index": memory_index,
        "boot_pack": boot_pack_out,
        "total_chars": total,
    }


def record(role: str) -> dict:
    data = {}
    if OUT_PATH.exists():
        try:
            data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    day = datetime.now(tz=KST).strftime("%Y-%m-%d")
    entry = measure(role)
    entry["date"] = day
    role_hist = data.setdefault(role, {"history": []})
    role_hist["history"] = [h for h in role_hist.get("history", []) if h.get("date") != day]
    role_hist["history"].append(entry)
    role_hist["latest"] = entry
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=ROLES, default="")
    args = ap.parse_args()
    targets = [args.role] if args.role else ROLES
    for role in targets:
        entry = record(role)
        print(f"[OK] {role} 부팅 로드 = {entry['total_chars']:,}자 "
              f"(agent {entry['agent_md']:,} · boot스킬 {entry['boot_skill']:,} · "
              f"gm-report스킬 {entry['gm_report_skill']:,} · 메모리색인 {entry['memory_index']:,} · "
              f"boot_pack {entry['boot_pack']:,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
