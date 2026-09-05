#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/boot_pack.py — 부팅 SSOT 슬라이스 (배1014 · 2026-09-05 시토)

문제: 부팅 지시문이 "약속·incidents·canon·kpi 4종 직독"을 요구해 매 부팅 통째로 읽는다
(incidents.json 81K자 ≈ 48K tok 등 · 웰리 실측 배1013). kpi.json은 이미 hangro_board.py
--role의 _kpi_slice가 슬라이스하므로 여기서는 나머지 5벌(약속·incidents·canon·자율화규약·
CONSTITUTION·module_registry)을 역할별로 자른다.

원칙(hangro_board._kpi_slice와 동일): 파일은 한 벌 그대로 둔다(약속 L01 — 쪼개면 진실이
여러 벌이 된다). 여기서는 "읽는 순간"에만 필요한 부분만 뽑아 출력한다.

사용:
  python scripts/boot_pack.py --role cto
  python scripts/boot_pack.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent

PROMISE_PATH = _REPO / "ssot" / "약속.json"
INCIDENTS_PATH = _REPO / "ssot" / "incidents.json"
CANON_PATH = _REPO / "ssot" / "canon_values.json"
REGULATION_PATH = _REPO / "ssot" / "자율화규약.md"
CONSTITUTION_PATH = _REPO / "ssot" / "CONSTITUTION.md"
REGISTRY_PATH = _REPO / "status" / "module_registry.json"

if hasattr(sys.stdout, "buffer"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROLES = ["ceo", "cfo", "chro", "cmo", "coo", "cpo", "cto", "cbo"]
NICK = {"ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
        "coo": "시우", "cpo": "시포", "cto": "시토", "cbo": "시보"}

# ponytail: incidents.json엔 role 필드가 없다 — watch_globs 경로 문자열에 역할 도메인
# 힌트가 들어있는지 substring 매치로 근사한다(완벽한 귀속 아님·과대매칭 가능 → 아래서
# 최근 N건으로 캡). 새 힌트가 필요하면 이 표에 한 줄 추가.
ROLE_GLOB_HINTS: dict[str, list[str]] = {
    "ceo": ["wellperion_guide(main)", "자율현황", "coo/chairman", "hangro_board",
            "queue_dispatch", "start-ai", "boot_pack"],
    "cfo": [],
    "chro": [],
    "cmo": ["instagram/", "가이드/cmo/", "ig_series_producer", "compose_",
            "_verify_", "case_series_dispatch", "kpi_collector", "kpi_values.json"],
    "coo": ["가이드/coo/", ".deploy-check", ".deploy-reception", "ops_fill_board",
            "지원팀", "지원부"],
    "cpo": ["가이드/cpo/", ".deploy-funnel", ".deploy-voc", "verify_member_dup_delete"],
    "cto": ["scripts/", "telegram_bot/", ".git/hooks", "wellperion-agents/scripts",
            "module_registry.json", "module_silence_detector", "start-ai", "gas_",
            ".deploy-*", "safe_commit", "git_lock", "git_merge_queue"],
    "cbo": [],
}

_RE_ADDED_ID = re.compile(r'^\+(?!\+\+)\s*"id":\s*"(L\d+)"')


def _trunc(s: str, n: int) -> str:
    """ponytail: 5,000자 예산 안에 넣는 안전판 — 진짜 전문은 원본 파일에."""
    s = s or ""
    return s if len(s) <= n else s[:n].rstrip() + "…(전문은 원본 파일)"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] {path.name} 파싱 실패: {e}", file=sys.stderr)
        return None


def _promise_slice(role: str) -> str:
    """ssot/약속.json — L번호+제목 전부 + 최근 7일 내 바뀐 항목만 전문."""
    data = _load_json(PROMISE_PATH)
    lessons = (data or {}).get("lessons", [])
    if not lessons:
        return "## 📜 약속 — 파일 없음/파싱 실패\n"
    lines = ["## 📜 약속(ssot/약속.json) — 전체 목록"]
    lines += [f"  {it.get('id')}: {it.get('약속')}" for it in lessons]

    # 변경 감지: unified diff는 바뀐 "내용" 줄만 +/- 표시하고 "id" 줄은 근처 문맥으로만
    # 나온다(id 자체는 안 바뀌므로) — 그래서 hunk(각 "@@ ... @@" 블록) 단위로 잘라, 그
    # 블록 안에 나오는 첫 "id" 값을 그 hunk의 변경 대상으로 삼는다.
    changed_ids: list[str] = []
    try:
        out = subprocess.run(
            ["git", "log", "--since=7.days", "-p", "--", "ssot/약속.json"],
            cwd=_REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
        for hunk in re.split(r"^@@.*@@.*$", out, flags=re.M)[1:]:
            m = re.search(r'"id":\s*"(L\d+)"', hunk)
            if m and m.group(1) not in changed_ids:
                changed_ids.append(m.group(1))
    except Exception as e:
        print(f"[WARN] git log 실패(약속 변경분): {e}", file=sys.stderr)

    if changed_ids:
        by_id = {it.get("id"): it for it in lessons}
        lines.append(f"\n### 최근 7일 내 변경 — 전문({len(changed_ids)}건)")
        for lid in changed_ids[:3]:
            it = by_id.get(lid)
            if it:
                lines.append(f"  [{lid}] {it.get('약속')} — {_trunc(it.get('내용'), 250)}")
    return "\n".join(lines) + "\n"


def _incidents_slice(role: str) -> str:
    """ssot/incidents.json — 최근 5건 요약 한 줄씩 + 내 역할 watch_globs 걸리는 것 전문(최근 3건 캡)."""
    data = _load_json(INCIDENTS_PATH)
    if data is None:
        return "## 🚨 재발방지(incidents) — 파일 없음/파싱 실패\n"
    if "watch_globs" not in (data.get("_schema", {}).get("fields") or []):
        incs = data.get("incidents", [])
        recent = sorted(incs, key=lambda x: x.get("date", ""), reverse=True)[:5]
        lines = ["## 🚨 재발방지(incidents) — 역할 필드 없음 — 최근 5건만"]
        lines += [f"  {i['id']} {i.get('date')} {i.get('gate')} — {_trunc(i.get('요약'), 110)}" for i in recent]
        return "\n".join(lines) + "\n"

    incs = data.get("incidents", [])
    recent = sorted(incs, key=lambda x: x.get("date", ""), reverse=True)[:5]
    lines = ["## 🚨 재발방지(incidents) — 최근 5건"]
    lines += [f"  {i['id']} {i.get('date')} {i.get('gate')} — {_trunc(i.get('요약'), 110)}" for i in recent]

    # ponytail: "전문" 예산이 빠듯해 본질·차단조치는 90자로 캡(안전판) — 진짜 전문은
    # ssot/incidents.json 그 id를 직접 연다. 매칭 2건 캡으로 role별 총량도 막는다.
    hints = [h.lower() for h in ROLE_GLOB_HINTS.get(role, [])]
    if hints:
        matched = [
            i for i in incs
            if any(h in g.lower() for g in (i.get("watch_globs") or []) for h in hints)
        ]
        matched.sort(key=lambda x: x.get("date", ""), reverse=True)
        matched = matched[:2]
        if matched:
            lines.append(f"\n### 내 역할({role}) watch_globs 걸림 — 요약 전문(2건 캡)")
            for i in matched:
                lines.append(
                    f"  [{i['id']}] {_trunc(i.get('요약'), 90)} | 본질: {_trunc(i.get('본질'), 90)} | "
                    f"차단조치: {_trunc(i.get('차단조치'), 90)} | 상태: {i.get('상태')}"
                )
    return "\n".join(lines) + "\n"


def _canon_slice(role: str) -> str:
    """ssot/canon_values.json — key·이름·value만."""
    data = _load_json(CANON_PATH)
    values = (data or {}).get("values", [])
    if not values:
        return "## 🔒 공식값(canon) — 파일 없음/파싱 실패\n"
    lines = ["## 🔒 공식값(canon_values) — key·이름·value"]
    lines += [f"  {v.get('key')} ({v.get('이름')}) = {v.get('value')}" for v in values]
    return "\n".join(lines) + "\n"


def _regulation_slice(role: str) -> str:
    """ssot/자율화규약.md — 맨 위 발효 표기 + §1 편제 조직도(코드블록)만."""
    if not REGULATION_PATH.exists():
        return "## 📖 자율화규약 — 파일 없음\n"
    text = REGULATION_PATH.read_text(encoding="utf-8")
    lines_all = text.splitlines()
    effect_line = next((l for l in lines_all if "발효" in l), "").strip()
    m = re.search(r"```\nGM.*?```", text, re.S)
    chart = m.group(0) if m else ""
    return (
        "## 📖 자율화규약(ssot/자율화규약.md)\n"
        f"  {effect_line}\n"
        f"{chart}\n"
        "  ※ 편제 서술 전문은 파일 §1 자체를 연다.\n"
    )


def _constitution_slice(role: str) -> str:
    """ssot/CONSTITUTION.md — 불변원리 3 절만."""
    if not CONSTITUTION_PATH.exists():
        return "## ⚖️ CONSTITUTION — 파일 없음\n"
    text = CONSTITUTION_PATH.read_text(encoding="utf-8")
    m = re.search(r"## 불변 원리 3\n(.*?)(?=\n## )", text, re.S)
    body = m.group(1).strip() if m else ""
    return "## ⚖️ CONSTITUTION — 불변 원리 3\n" + body + "\n"


def _registry_slice(role: str) -> str:
    """status/module_registry.json — owner_role=내 것만 id·enabled·data_source."""
    data = _load_json(REGISTRY_PATH)
    mods = [m for m in (data or {}).get("modules", []) if m.get("owner_role") == role]
    if not mods:
        return f"## 🧩 모듈 등록부 — owner_role={role} 0건\n"
    lines = [f"## 🧩 모듈 등록부(module_registry) — owner_role={role} {len(mods)}건 (id/on-off/데이터원)"]
    for m in mods:
        ref = Path((m.get("data_source") or {}).get("ref", "")).name  # 경로 전체 대신 파일명만(공간 절약)
        on = "on" if m.get("enabled") else "off"
        lines.append(f"  {m['id']} {on} {ref}")
    return "\n".join(lines) + "\n"


def build_pack(role: str) -> str:
    role = role.strip().lower()
    nick = NICK.get(role, role)
    parts = [
        f"# 부팅 슬라이스(boot_pack) — {nick}({role})\n",
        _promise_slice(role),
        _incidents_slice(role),
        _canon_slice(role),
        _regulation_slice(role),
        _constitution_slice(role),
        _registry_slice(role),
    ]
    body = "\n".join(parts)
    n = len(body)
    body += f"\n📏 부팅 로드 {n}자(≤5,000 목표)\n"
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=ROLES, default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        ok = True
        for role in ["ceo", "cmo", "cpo", "cto"]:
            pack = build_pack(role)
            n = len(pack)
            status = "OK" if n <= 5000 else "FAIL(초과)"
            print(f"{role}: {n}자 — {status}")
            if n > 5000:
                ok = False
        print("SELFTEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    if not args.role:
        print("사용: python scripts/boot_pack.py --role {ceo|cfo|chro|cmo|coo|cpo|cto|cbo}", file=sys.stderr)
        return 1

    print(build_pack(args.role))
    return 0


if __name__ == "__main__":
    sys.exit(main())
