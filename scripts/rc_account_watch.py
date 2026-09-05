# -*- coding: utf-8 -*-
"""로그인 계정이 바뀌면 원격제어(/rc)를 자동으로 다시 붙인다 (GM 지시 2026-09-05 · 시우).

배경: 원격제어 세션은 로그인 계정(claude.ai)에 묶인다. 세션 도중 /login 으로 계정을 바꾸면(cao↔info)
원격제어가 조용히 끊기고, 밖에서 같은 세션에 다시 붙이는 것(claude remote-control --session-id)은
"서버에서 세션을 찾을 수 없음"으로 실패한다(2026-09-05 실측). 되는 길은 하나 — 같은 대화를 새 창에서
이어받으며(--resume) 원격제어를 켜고 시작하는 것(--remote-control).

동작(UserPromptSubmit 훅 · 프롬프트마다 ~10ms): ~/.claude.json 의 oauthAccount.emailAddress 를 읽어
세션별 기록과 비교한다. 바뀌었으면 새 창(wt)에 `claude --resume <이 세션> --remote-control <역할>` 을 띄우고
알림 한 줄을 남긴다. 기존 창은 GM 이 닫는다(대화는 새 창이 이어받는다 · 새 세션 id 로 갈라지므로 기록 충돌 없음).

시험: echo '{"session_id":"test"}' | RC_WATCH_TEST_EMAIL=x@y python scripts/rc_account_watch.py --dry-run
"""
import json
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "rc_account_watch")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def current_email():
    if os.environ.get("RC_WATCH_TEST_EMAIL"):
        return os.environ["RC_WATCH_TEST_EMAIL"]
    try:
        with open(os.path.join(HOME, ".claude.json"), encoding="utf-8") as f:
            return (json.load(f).get("oauthAccount") or {}).get("emailAddress") or ""
    except Exception:
        return ""


def main():
    dry = "--dry-run" in sys.argv
    try:
        sid = (json.load(sys.stdin) or {}).get("session_id") or ""
    except Exception:
        sid = ""
    if not sid:
        return 0
    email = current_email()
    if not email:
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    sp = os.path.join(STATE_DIR, sid + ".json")
    prev = None
    try:
        with open(sp, encoding="utf-8") as f:
            prev = json.load(f).get("email")
    except Exception:
        pass
    if prev is None or prev == email:
        if prev is None:
            with open(sp, "w", encoding="utf-8") as f:
                json.dump({"email": email}, f)
        return 0
    # 계정이 바뀌었다 — 같은 대화를 새 창에서 이어받으며 원격제어를 켠다
    role = (os.environ.get("WELLPERION_ROLE") or "ai").upper()
    cmd = ["wt", "new-tab", "--title", role, "--suppressApplicationTitle", "-d", ROOT,
           "powershell", "-NoExit", "-Command",
           "claude --resume %s --fork-session --remote-control '%s'" % (sid, role)]
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"email": email, "prev": prev, "respawned": not dry}, f)
    if dry:
        print("[dry-run] " + " ".join(cmd))
        return 0
    try:
        subprocess.Popen(cmd, cwd=ROOT, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        print("[원격제어] 로그인 계정이 %s → %s 로 바뀌어 원격제어가 끊겼다. 새 창(%s)이 이 대화를 이어받으며 "
              "원격제어를 다시 켰다 — 이 창은 닫아도 된다." % (prev, email, role))
    except Exception as e:
        print("[원격제어] 계정 변경(%s → %s) 감지 — 새 창 자동 열기 실패(%s). 이 창에서 /rc 를 치면 된다." % (prev, email, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
