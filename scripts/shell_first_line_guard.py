# -*- coding: utf-8 -*-
"""GM 셸 화면 첫 줄이 저장소 경로로 시작하는 것을 코드로 막는다.

경위 (약속 L02 — 정한 건 코드로 박는다):
    GM이 같은 지적을 다섯 번 하셨다(2026-08-11 · 08-13 · 08-15 · 08-24 · 08-25).
    GM 화면에서 `● main` 아래 줄은 AI가 친 명령 자체이고, 그 줄이 저장소 경로로 시작하면
    무슨 작업을 하는 중인지 전혀 안 보인다. 08-24에는 기억(메모리)에 규칙을 적어 두는 것으로
    끝냈는데, 그 다음 세션인 2026-08-25에 같은 위반이 또 났다 — 기억은 기계를 못 막는다.
    그래서 관문에 검사를 둔다.

무엇을 막나:
    1. Bash 명령이 `cd <저장소 루트> &&` 로 시작하는 것. 작업 디렉터리는 이미 저장소다.
    2. Bash 명령이 변수 대입(`f="긴/경로"`)이나 따옴표 경로로 시작하는 것.
    3. 서브에이전트 지시문(Agent/Task prompt)의 첫 줄이 저장소 경로로 시작하는 것.

무엇을 안 막나:
    다른 디렉터리로 가는 `cd`(하위 폴더·임시 폴더 등)는 정당하므로 통과시킨다.
    명령 안쪽·뒷부분에 경로가 들어가는 것도 통과 — 화면 첫머리만 문제다.

되돌리기: .claude/settings.local.json 의 PreToolUse 항목에서 이 스크립트 줄을 지운다.
"""
from __future__ import annotations

import json
import re
import sys

REPO_MARK = "welperion-automation"

# 명령 첫머리가 변수 대입 또는 따옴표 경로인 경우 (예: f="3. 웰페리온 가이드/…" · "C:/Users/…")
ASSIGN_HEAD = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\s*=\s*["\']')
QUOTED_PATH_HEAD = re.compile(r'^["\'][A-Za-z]:[/\\]')
CD_HEAD = re.compile(r'^cd\s+["\']?([^"\'&;|]+)')
# 경로가 시작하는 자리 — 윈도우 드라이브(C:\ · C:/) 또는 Git Bash 형(/c/)
PATH_START = re.compile(r'[A-Za-z]:[\\/]|/[a-z]/Users')

MSG = (
    "GM 화면 첫 줄이 저장소 경로가 된다 — 무슨 작업인지 안 보인다(GM 5회 지적).\n"
    "  고치는 법: 첫 줄을 '작업'으로 시작한다.\n"
    "   · cd 접두를 빼라 — 작업 디렉터리는 이미 저장소다.\n"
    "   · 명령을 동사로 시작하라: C:/Python314/python.exe … / git … / grep -c \"x\" \"긴/경로\"\n"
    "   · 긴 경로는 명령 뒤쪽이나 python -c 안으로 밀어 넣어라.\n"
    "   · 서브에이전트 지시문도 첫 줄에 '일 이름'을 먼저 쓰고 경로는 뒷줄로 내려라."
)


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _bash_violation(cmd: str) -> str:
    head = _first_line(cmd)
    if not head:
        return ""
    m = CD_HEAD.match(head)
    if m and REPO_MARK in m.group(1) and m.group(1).rstrip("/\\").endswith(REPO_MARK):
        return "명령이 `cd <저장소 루트>` 로 시작한다"
    if ASSIGN_HEAD.match(head):
        return "명령이 변수 대입(경로)으로 시작한다"
    if QUOTED_PATH_HEAD.match(head):
        return "명령이 따옴표 경로로 시작한다"
    return ""


def _agent_violation(prompt: str) -> str:
    head = _first_line(prompt)
    if head.startswith(("/", "C:", "c:", '"', "'")) or head.lower().startswith(REPO_MARK):
        return "지시문 첫 줄이 경로로 시작한다"
    # '웰페리온 저장소(C:\...)에서 …' 처럼 앞머리가 통째로 경로인 경우.
    # 앞에 놓인 글자가 12자도 안 되면 그 줄은 사실상 경로로 시작하는 것이다
    # (일 이름을 먼저 쓴 줄 — '배773 알림 점검. 저장소는 …' — 은 그보다 길어 통과한다).
    m = PATH_START.search(head)
    if m and m.start() < 12:
        return "지시문 첫 줄 앞머리가 저장소 경로다"
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 입력을 못 읽으면 통과 — 가드가 작업을 막아 세우지 않는다

    tool = payload.get("tool_name") or payload.get("toolName") or ""
    args = payload.get("tool_input") or payload.get("toolInput") or {}
    if not isinstance(args, dict):
        return 0

    if tool == "Bash":
        why = _bash_violation(str(args.get("command") or ""))
    elif tool in ("Agent", "Task"):
        why = _agent_violation(str(args.get("prompt") or ""))
    else:
        return 0

    if not why:
        return 0

    print(f"[셸 첫 줄 가드] {why}.\n{MSG}", file=sys.stderr)
    return 2  # 2 = 차단하고 stderr 를 모델에게 돌려준다


def _selfcheck() -> None:
    assert _bash_violation('cd "C:/Users/jjky0/welperion-automation" && git status')
    assert _bash_violation('f="3. 웰페리온 가이드/x.html"; grep -c a "$f"')
    assert _bash_violation('"C:/Python314/python.exe" -c "pass"')
    assert not _bash_violation('git status --porcelain')
    assert not _bash_violation('C:/Python314/python.exe scripts/x.py')
    assert not _bash_violation('cd scripts && ls')          # 하위 폴더 이동은 정당
    assert not _bash_violation('grep -c "x" "3. 웰페리온 가이드/x.html"')
    assert _agent_violation('웰페리온 저장소(C:\\Users\\jjky0\\welperion-automation)에서 점검한다.')
    assert _agent_violation('/c/Users/jjky0/welperion-automation 를 본다')
    assert not _agent_violation('배773 알림 점검. 저장소는 C:\\Users\\jjky0\\welperion-automation 이다.')
    assert not _agent_violation('알림 50개를 훑어 결함을 찾는다.')
    print("selfcheck OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
