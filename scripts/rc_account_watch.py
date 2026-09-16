# -*- coding: utf-8 -*-
"""로그인 계정이 바뀌면 원격제어(/rc)를 자동으로 다시 붙인다 (GM 지시 2026-09-05 · 시우).

배경: 원격제어 세션은 로그인 계정(claude.ai)에 묶인다. 세션 도중 /login 으로 계정을 바꾸면(cao↔info)
원격제어가 조용히 끊기고, 밖에서 같은 세션에 다시 붙이는 것(claude remote-control --session-id)은
"서버에서 세션을 찾을 수 없음"으로 실패한다(2026-09-05 실측). 되는 길은 하나 — 같은 대화를 새 창에서
이어받으며(--resume) 원격제어를 켜고 시작하는 것(--remote-control).

동작(UserPromptSubmit 훅 · 프롬프트마다 ~10ms): ~/.claude.json 의 oauthAccount.emailAddress 를 읽어
세션별 기록과 비교한다. 바뀌었으면 **안내 한 줄만** 남긴다 — 「이 창에서 /rc 를 치면 원격제어가 다시 붙는다」.

★2026-09-15 GM 지시 「창을 안 켰으면 좋겠다, 한 줄만」 — 종전에는 새 창(wt)에 `claude --resume --fork-session
--remote-control` 을 자동으로 띄웠는데, 계정을 바꿀 때마다 살아 있는 세션 수만큼 창이 열려(하루 3번 · 15개) GM 이
매번 닫아야 했다. 계정 전환은 GM 이 PC 앞에서 하므로 그 자리에서 /rc 한 번이면 된다. 자동 창은 뺐다(코드 삭제).

시험: echo '{"session_id":"test"}' | RC_WATCH_TEST_EMAIL=x@y python scripts/rc_account_watch.py --dry-run
"""
import json
import os
import sys

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".claude", "rc_account_watch")
RC_ACCOUNT = "cao@wellperion.com"   # 원격제어를 붙이는 유일한 계정(GM 2026-09-16) — 다른 계정 전환은 조용히
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
    # 계정이 바뀌었다 — 기록만 갱신.
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"email": email, "prev": prev}, f)
    # ★2026-09-16 GM 「계정 변경될 때 /rc 안 해도 돼 · 그냥 cao 계정 rc 만 되어 있으면 돼」
    #   원격제어는 cao@ 계정 하나에만 붙인다. 다른 계정(info@·lessons@)으로 바뀐 때는 아무 말도 하지 않고,
    #   cao@ 로 돌아온 때만 한 줄 — 그때가 /rc 를 다시 붙일 자리다.
    if email.lower() == RC_ACCOUNT:
        print("[원격제어] cao 계정으로 돌아왔다 — 핸드폰에서 이어 보려면 이 창에서 /rc 한 줄.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
