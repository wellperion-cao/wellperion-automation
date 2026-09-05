# -*- coding: utf-8 -*-
"""메모리 회수 훅 — GM 프롬프트 낱말과 메모리 frontmatter(name+description)를 대조해
상위 3건의 본문을 <system-reminder> 로 낸다 (배1016 · 웰리 설계 · GM 지시 2026-09-05).

경위: 부팅이 MEMORY.md 색인 377건을 통째로 미는데 그 순간 쓸 것은 몇 건뿐이다.
색인은 주제 지도로 얇게 하고(MEMORY.md), 필요한 순간 이 스크립트가 관련 3건 본문만
꺼낸다 — worklog.py 의 UserPromptSubmit 훅(--recall 인자)이 그 자리에서 부른다.

점수 = 프롬프트와 (name+description) 사이 한글 2-gram 겹침 개수(중복 가중).
coded: true 표시된 메모리(이미 코드·훅이 강제하는 규칙)는 점수를 절반으로 깎아
회수 후순위로 민다 — 굳이 다시 밀어넣지 않아도 코드가 대신 지키고 있어서다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MEMORY_DIR = Path(r"C:\Users\jjky0\.claude\projects\C--Users-jjky0-welperion-automation\memory")
TOP_N = 3
_HANGUL_RUN = re.compile(r"[가-힣]{2,}")
_FRONTMATTER = re.compile(r"^---\n(.*?\n)---\n(.*)$", re.S)
_SKIP_NAMES = ("MEMORY.md",)


def _bigrams(text: str) -> list[str]:
    grams: list[str] = []
    for run in _HANGUL_RUN.findall(text or ""):
        grams.extend(run[i:i + 2] for i in range(len(run) - 1))
    return grams


def _load_memories() -> list[tuple[str, str, bool, str]]:
    """(name, description, coded, body) 목록. 파싱 실패 파일은 건너뛴다 — 훅이 부팅을 막지 않는다."""
    out: list[tuple[str, str, bool, str]] = []
    if not MEMORY_DIR.is_dir():
        return out
    for path in MEMORY_DIR.glob("*.md"):
        if path.name in _SKIP_NAMES or path.name.startswith(("MEMORY.md.", "_MEMORY")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
            m = _FRONTMATTER.match(text)
            if not m:
                continue
            fm, body = m.group(1), m.group(2)
            name_m = re.search(r"^name:\s*(.+)$", fm, re.M)
            desc_m = re.search(r"^description:\s*(.+)$", fm, re.M)
            coded_m = re.search(r"^coded:\s*true\s*$", fm, re.M | re.I)
            name = (name_m.group(1).strip().strip('"') if name_m else path.stem)
            desc = (desc_m.group(1).strip().strip('"') if desc_m else "")
            out.append((name, desc, bool(coded_m), body.strip()))
        except Exception:
            continue
    return out


def recall(prompt: str, top_n: int = TOP_N) -> str:
    """상위 top_n 메모리 본문을 이어붙인 <system-reminder> 문자열. 못 찾으면 빈 문자열."""
    prompt_grams = set(_bigrams(prompt))
    if not prompt_grams:
        return ""
    scored = []
    for name, desc, coded, body in _load_memories():
        overlap = len(prompt_grams & set(_bigrams(name + " " + desc)))
        if overlap <= 0:
            continue
        scored.append((overlap * (0.5 if coded else 1.0), name, body))
    if not scored:
        return ""
    scored.sort(key=lambda x: -x[0])
    picked = scored[:top_n]
    parts = "\n\n".join(f"[{name}]\n{body}" for _, name, body in picked)
    return f"<system-reminder>\n관련 메모리 회수({len(picked)}건 · 배1016 memory_recall):\n\n{parts}\n</system-reminder>"


def _selftest() -> int:
    cases = [
        ("쿵짝표 보여줘", {"feedback_kungjjak_beats_summary_artifact"}),
        ("종합접수처 안 돼", {"feedback_reception_is_coo_only_cto_hands_off"}),
        ("결재 올려줘", {
            "feedback_gm_approval_drafts_owner_is_gm_line_gm_then_rep",
            "project_approval_final_approver_per_ssot",
            "feedback_check_approval_ssot_before_holding_a_ship",
        }),
    ]
    hit = 0
    for prompt, expected in cases:
        out = recall(prompt)
        names = set(re.findall(r"^\[(\S+)\]$", out, re.M))
        ok = bool(names & expected)
        hit += int(ok)
        print(f"[{'OK' if ok else 'FAIL'}] {prompt!r} → {names or '(없음)'}")
    print(f"[{'OK' if hit == len(cases) else 'FAIL'}] 회수 자가검사 {hit}/{len(cases)}")
    return 0 if hit == len(cases) else 1


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        return _selftest()
    try:
        data = json.loads(sys.stdin.read())
        prompt = str(data.get("prompt") or "")
    except Exception:
        prompt = ""
    out = recall(prompt)
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
