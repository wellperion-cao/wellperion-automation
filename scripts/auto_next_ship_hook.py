#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""턴이 끝나면 스스로 다음 배로 (GM 결정 2026-07-28 · A안).

왜 있나
  실측(2026-07-28): 각 세션이 하루에 GM 입력을 기다리며 서 있던 시간 — 웰리 428분·시모 236분·
  시우 193분·시포 165분·시토 69분. 배가 없어서가 아니라 **한 턴을 끝내면 다음으로 스스로
  넘어가지 않아서**였다. GM: "AI할게 많을텐데 … statusline엔 계속 대기로만 남는데" → A안 선택.

무엇을 하나
  세션이 턴을 끝내려는 순간(Stop 훅) **이미 있는 선별 관문**에 물어본다:
      python scripts/welly_auto_runner.py --boot-candidate --clevel <role>
  '✅ 착수' 판정이 나오면 멈추지 않고 그 배를 이어서 진행하게 한다.
  판정이 모호·후보 0건이면 그냥 멈춘다(평소와 같음).

무엇을 하지 않나 (★새 선별 로직을 만들지 않는다 — 헌법 불변원리 1·약속 L21)
  어떤 배를 집을지는 **전적으로 위 관문이 정한다.** 이 훅은 '물어보고 이어붙이는' 배선일 뿐이다.
  가역(reversible)·모호성·쿨다운·금지 5종 판정은 전부 관문 안에 이미 있다.

멈추는 조건(안전장치) — 하나라도 걸리면 평소처럼 멈춘다
  ① 이 훅 때문에 이미 이어붙인 턴이다(stop_hook_active) — 무한루프 차단
  ② 역할을 모른다 / 시로·시뽀다(나우열M 관할 · queue_dispatch.EXCLUDED_ROLES)
  ③ 끄기 스위치 파일이 있다(status/auto_continue.OFF) 또는 WELLPERION_AUTO_NEXT=0
  ④ 마지막 턴에서 GM께 **선택 카드를 냈다**(AskUserQuestion·ExitPlanMode) — 답을 기다려야 한다
  ⑤ GM 입력 없이 이어붙인 횟수가 상한(기본 6)에 닿았다 — GM이 끼어들 자리를 반드시 남긴다
  ⑥ 관문이 '착수'라고 하지 않았다

되돌리기: `.claude/settings.local.json` 의 Stop 훅 한 줄을 지우거나,
          `status/auto_continue.OFF` 파일을 만들면 즉시 멈춘다(코드 수정 불필요).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_HERE))

try:
    from queue_dispatch import EXCLUDED_ROLES  # 배제 역할 단일 정본(복사 금지)
except Exception:  # noqa: BLE001
    EXCLUDED_ROLES = {"chro", "cfo"}

MAX_CHAIN = 6                       # GM 입력 없이 이어붙일 수 있는 최대 턴 수
STATE = _REPO / "tmp" / "auto_next_ship_state.json"
OFF_SWITCH = _REPO / "status" / "auto_continue.OFF"
ROLE_CACHE = _REPO / "tmp" / "hud_role_cache.json"   # 상태줄이 이미 적어둔 역할 기억함(재사용)
TAIL_BYTES = 400_000
NICK = {"ceo": "웰리", "cmo": "시모", "coo": "시우", "cpo": "시포", "cto": "시토", "cbo": "시보"}
# 마지막 턴이 GM 답을 기다리는 도구로 끝났는지 — 이때는 이어붙이면 안 된다.
# 공백 유무에 흔들리지 않게 정규식으로 본다("name":"X" / "name": "X" 둘 다).
ASK_TOOLS = re.compile(r'"name"\s*:\s*"(AskUserQuestion|ExitPlanMode)"')
HUMAN_TURN = re.compile(r'"promptSource"')
STAMP = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')


def allow_stop(why: str = "") -> None:
    """평소처럼 멈춘다."""
    if why:
        print(why, file=sys.stderr)
    print(json.dumps({"continue": True}, ensure_ascii=False))
    sys.exit(0)


def keep_going(reason: str) -> None:
    """멈추지 않고 이어서 진행하게 한다."""
    print(json.dumps({"continue": False, "decision": "block", "reason": reason},
                     ensure_ascii=False))
    sys.exit(0)


def read_tail(path: str) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
            raw = f.read()
        return raw.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def resolve_role(transcript: str) -> str | None:
    """역할 — 상태줄이 적어둔 기억함을 먼저 본다(같은 판정을 두 번 하지 않는다).
    기억함이 없으면 부팅 프롬프트에서 직접 찾는다(상태줄 roleOf 와 같은 표식)."""
    key = str(transcript).replace("\\", "/").lower()
    try:
        cache = json.loads(ROLE_CACHE.read_text(encoding="utf-8"))
        if isinstance(cache, dict) and cache.get(key):
            return cache[key]
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(transcript, "rb") as f:
            head = f.read(60000).decode("utf-8", "replace")
        m = re.search(r"ai-(ceo|cfo|chro|cmo|coo|cpo|cto)\.md", head)
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


def last_human_stamp(tail: str) -> str:
    """마지막으로 사람이 실제로 친 프롬프트의 시각 — 이어붙인 횟수를 세는 기준점."""
    best = ""
    for line in tail.splitlines():
        if not HUMAN_TURN.search(line):
            continue
        m = STAMP.search(line)
        if m:
            best = m.group(1)
    return best


def waiting_on_gm(tail: str) -> bool:
    """마지막 턴이 GM 선택 카드로 끝났나 — 그러면 답을 기다려야 한다.
    뒤에서부터 훑다가 사람이 말한 지점을 만나면 거기서 끊는다(그 뒤엔 대기가 아니다)."""
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    for ln in reversed(lines[-60:]):
        if ASK_TOOLS.search(ln):
            return True
        if HUMAN_TURN.search(ln):      # 그 사이 사람이 다시 말했으면 대기 아님
            return False
    return False


def bump_chain(session_id: str, human_stamp: str) -> int:
    """GM 입력 이후 몇 번째 이어붙임인가. GM이 말하면 0으로 돌아간다."""
    state = {}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except Exception:  # noqa: BLE001
        state = {}
    cur = state.get(session_id) or {}
    n = 0 if cur.get("human") != human_stamp else int(cur.get("n") or 0)
    n += 1
    state[session_id] = {"human": human_stamp, "n": n}
    if len(state) > 50:                       # 오래된 세션부터 버린다
        for k in list(state.keys())[:len(state) - 50]:
            del state[k]
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return n


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:  # noqa: BLE001
        allow_stop("입력을 못 읽음")

    if data.get("stop_hook_active"):
        allow_stop("이미 이어붙인 턴")
    if OFF_SWITCH.exists() or os.environ.get("WELLPERION_AUTO_NEXT") == "0":
        allow_stop("끄기 스위치 켜져 있음")

    transcript = data.get("transcript_path") or ""
    if not transcript or not os.path.exists(transcript):
        allow_stop("세션 기록 없음")

    role = resolve_role(transcript)
    if not role or role in EXCLUDED_ROLES:
        allow_stop("역할 없음/배제 역할: %s" % role)

    # 쿵짝 완료 짝 — 접수는 UserPromptSubmit 훅이 기계로 남기는데 완료는 손으로 남기던 탓에
    # 답을 다 한 물음이 "미완"으로 쌓였다(2026-08-11 실측 91건). 턴이 끝나는 이 자리에서 닫는다.
    # 새 훅·새 파일을 만들지 않고 이미 모든 턴이 지나가는 관문에 얹는다(약속 L21).
    try:
        import worklog
        closed = worklog.close_gm_refs(role)
        if closed:
            print("[auto-next] GM지시 완료 짝 %d건 자동 기록" % closed, file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print("[auto-next] 완료 짝 기록 실패(무시): %s" % e, file=sys.stderr)

    tail = read_tail(transcript)
    if waiting_on_gm(tail):
        allow_stop("GM 선택 카드 대기 중")

    stamp = last_human_stamp(tail)
    n = bump_chain(str(data.get("session_id") or transcript), stamp)
    print("[auto-next] role=%s 기준시각=%s 연속=%d" % (role, stamp or "(없음)", n), file=sys.stderr)
    if n > MAX_CHAIN:
        allow_stop("연속 %d회 — GM이 끼어들 자리를 남긴다" % (n - 1))

    try:
        r = subprocess.run(
            [sys.executable, str(_HERE / "welly_auto_runner.py"),
             "--boot-candidate", "--clevel", role],
            capture_output=True, text=True, encoding="utf-8", timeout=25)
        out = (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        allow_stop("선별 관문 호출 실패: %s" % e)

    if "✅ 착수" not in out:
        allow_stop("착수 후보 없음")

    nick = NICK.get(role, role)
    keep_going(
        "[자동 이어가기 %d/%d · GM 결정 2026-07-28 A안]\n"
        "턴이 끝났지만 멈추지 않는다 — 선별 관문이 다음 배를 '착수'로 판정했다.\n"
        "아래가 관문의 판정 결과다. **되묻지 말고 그 배를 이어서 진행한다.**\n\n"
        "%s\n"
        "지킬 것:\n"
        "- 이 배가 막히면(외부 응답·GM 결정 대기) 멈추지 말고 큐의 다른 **가역** 배로 넘어간다.\n"
        "- 비가역(💰결제·🔒보안·🚫금지·📐전략·🏷️공식값·발행·배포·삭제·외부전송)은 손대지 않는다.\n"
        "- 끝난 것·다음 것은 셸이 아니라 AI 진행현황방으로 보낸다"
        "(scripts/notify_gm_progress.py · wellperion-gm-report §4-2-1).\n"
        "- 셸에는 GM이 정해야 하는 것만 남긴다. 진행 중계·완료 보고를 길게 쓰지 않는다.\n"
        "- 증거 없는 완료 금지 — 실제 결과물로 확인한 뒤에만 배를 닫는다.\n"
        "- 이어붙이기는 GM 입력 없이 최대 %d회다. 그 뒤엔 자동으로 멈춘다.\n"
        % (n, MAX_CHAIN, out.strip(), MAX_CHAIN)
    )


if __name__ == "__main__":
    main()
