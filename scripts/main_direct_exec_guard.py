#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""메인 창이 서브에이전트 없이 코드·화면을 직접 고치거나 발신 도구를 직접 부르면 막는다 (GM 지시 2026-09-18 · 배 12745).

왜: 메인 창은 판단·조율 자리이고 실행은 executor(Sonnet) 서브에이전트 몫인데(CLAUDE.md 위임 규칙),
    실측하니 메인 세션이 Edit·Write·Bash 로 코드를 직접 고치고 발신 도구를 직접 돌렸다(위임 비율
    한 자릿수). 규칙은 문서에 있었지만 지켜지지 않았다 — 문서로 안 지켜지는 항목은 코드로 옮긴다
    (약속 L02). agent_model_guard 와 같은 PreToolUse 자리에 붙인다(약속 L21).

무엇을: 메인 세션(훅 stdin 에 agent_id 가 없는 호출 · 2026-09-18 실측 — 서브에이전트 호출은
    agent_id·agent_type 이 실리고 메인 호출엔 없다 · 환경변수로는 구분 안 됨)에서
      (a) Edit/Write 대상이 코드·화면 파일(.py .html .js .css .json)이거나
      (b) Bash 명령이 발신 도구(SENDERS)를 부르거나, 파이썬 인라인·스크래치 패치(쓰기 낱말 포함)나
          sed -i 로 파일을 고치면
    차단(exit 2)하고 「executor 서브에이전트에 위임하라」를 stderr 로 돌려준다.

안 막는 것:
  - 서브에이전트 호출(agent_id 있음)
  - 도구 입력이나 명령 안에 『직접실행: 이유』 마커가 있는 것(사람이 뜻을 밝힌 것)
  - 상태·데이터 파일(status/** · ssot/** · logs/**) · 스크래치 폴더 · 저장소 밖 · .claude/ .omc/ 설정
  - 문서(.md 등 코드·화면 확장자가 아닌 것)
  - 저장소에 있는 스크립트를 그냥 실행하는 것(scripts/*.py 등 — 패치가 아니라 도구다)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARK = "직접실행:"
CODE_EXT = (".py", ".html", ".js", ".css", ".json")
PASS_DIRS = ("/status/", "/ssot/", "/logs/", "/.claude/", "/.omc/", "/scratchpad/", "/temp/claude/")
SENDERS = ("kakao_report_sender.py", "telegram_send.py", "telegram_user_send.py", "notify_gm_progress.py")
PY_RUN = re.compile(r"(?:^|[\s;&|(])(?:[\w./:\\-]*python[\d.]*(?:\.exe)?|py)\s", re.I)
PY_INLINE = re.compile(r"\s-c\s|<<\s*['\"]?\w+['\"]?|python[\w.]*\s+-\s")
WRITE_WORDS = re.compile(r"open\([^)]*['\"][wa]\+?['\"]|write_text\(|os\.replace\(|\.write\(|json\.dump\(")
SED_INPLACE = re.compile(r"\bsed\s+(?:-[a-zA-Z]*i|--in-place)")
HINT = (
    "executor(Sonnet) 서브에이전트에 위임하세요 — 메인 창은 판단·조율만 한다.\n"
    f"  예외 = 도구 입력이나 명령 안에 『{MARK} 이유』 마커를 넣는다."
)


def _pass_path(p: str) -> bool:
    s = p.replace("\\", "/").lower()
    if not s.endswith(CODE_EXT):
        return True
    try:
        if not Path(p).resolve().is_relative_to(ROOT):
            return True
    except Exception:
        pass
    return any(d in s for d in PASS_DIRS)


def _scratch_text(cmd: str) -> str:
    """명령이 스크래치·임시 폴더의 .py 를 부르면 그 파일 본문(쓰기 낱말 검사용)."""
    out = []
    for m in re.finditer(r"[\w:./\\-]*(?:scratchpad|temp/claude)[\w./\\-]*\.py", cmd, re.I):
        try:
            out.append(Path(m.group(0)).read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    return "\n".join(out)


def verdict(tool: str, args: dict, is_sub: bool) -> str | None:
    """막아야 하면 사유 문자열, 아니면 None."""
    if is_sub:
        return None
    if MARK in json.dumps(args, ensure_ascii=False):
        return None
    if tool in ("Edit", "Write", "MultiEdit"):
        p = str(args.get("file_path") or "")
        if p and not _pass_path(p):
            return f"메인 창이 코드·화면 파일을 직접 고친다: {p}"
        return None
    if tool == "Bash":
        cmd = str(args.get("command") or "")
        low = cmd.lower()
        hit = [s for s in SENDERS if s in low]
        if hit:
            return f"메인 창이 발신 도구를 직접 부른다: {hit[0]}"
        if SED_INPLACE.search(cmd):
            return "메인 창이 sed -i 로 파일을 직접 고친다"
        if PY_RUN.search(cmd):
            body = cmd if PY_INLINE.search(cmd) else _scratch_text(cmd)
            if body and WRITE_WORDS.search(body):
                return "메인 창이 파이썬 패치 스크립트로 파일을 직접 고친다"
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip().startswith("{") else {}
    except Exception:
        return 0
    why = verdict(str(payload.get("tool_name") or ""), payload.get("tool_input") or {},
                  bool(payload.get("agent_id")))
    if not why:
        return 0
    print(f"[메인 창 직접 실행 관문] {why}\n{HINT}", file=sys.stderr)
    return 2  # 2 = 차단하고 stderr 를 모델에게 돌려준다


def _selftest() -> None:
    py = "C:/Python314/python.exe"
    # 차단 3
    assert verdict("Edit", {"file_path": str(ROOT / "scripts" / "x.py"), "new_string": "a"}, False), "코드 Edit 은 막아야 한다"
    assert verdict("Bash", {"command": f"{py} scripts/kakao_report_sender.py --room x"}, False), "발신 도구는 막아야 한다"
    assert verdict("Bash", {"command": f"{py} - <<'EOF'\nopen('a.py','w').write('x')\nEOF"}, False), "인라인 패치는 막아야 한다"
    # 통과 4
    assert verdict("Edit", {"file_path": str(ROOT / "scripts" / "x.py")}, True) is None, "서브에이전트는 막지 않는다"
    assert verdict("Write", {"file_path": str(ROOT / "3. 웰페리온 가이드" / "status" / "_queue.json")}, False) is None, "상태 파일은 막지 않는다"
    assert verdict("Edit", {"file_path": str(ROOT / "scripts" / "x.py"), "new_string": f"# {MARK} 한 줄 핫픽스"}, False) is None, "마커는 통과"
    assert verdict("Bash", {"command": f"{py} scripts/hangro_board.py --role cto && git status"}, False) is None, "저장소 스크립트 실행·git 은 막지 않는다"
    assert verdict("Write", {"file_path": str(ROOT / "docs" / "a.md")}, False) is None, "문서는 막지 않는다"
    print("main_direct_exec_guard selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv or "--selfcheck" in sys.argv:
        _selftest()
    else:
        try:
            sys.exit(main())
        except Exception:
            sys.exit(0)  # 가드가 죽어서 일을 막으면 안 된다
