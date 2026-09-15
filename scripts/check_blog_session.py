# -*- coding: utf-8 -*-
"""파트너 블로그 네이버 로그인 세션이 얼마나 버틸지 본다.

왜 있나 — 2026-09-15. 조재오 지점장님 블로그가 09-12~15 나흘 연속 실패했고 다이어트캠프도
로그인한 다음 날 풀렸다. 쿠키를 재 보니 세 계정 모두 NID_AUT·NID_SES 가 **세션 쿠키**였다
(만료 시각이 없는 쿠키 = 브라우저를 닫으면 사라지고, 네이버도 하루 안쪽에 세션을 끊는다).
로그인 화면에서 「로그인 상태 유지」를 켜야 만료 시각이 있는 쿠키를 준다.

그래서 재로그인 직후 이 검사를 돌려 「이번 로그인이 내일까지 버티는가」를 그 자리에서 알린다.
안 그러면 다음 날 아침에야 실패로 알게 된다.

쓰는 법:
    python scripts/check_blog_session.py            # 세 계정 전부
    python scripts/check_blog_session.py --tenant dc
종료 코드: 0 = 그 계정 세션이 내일까지 버틴다 / 1 = 오늘 안에 풀린다(로그인 상태 유지 필요)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles"

# 계정 자리 이름 → 사람이 아는 이름. tenant_profile.ENV_KEY 와 같은 값을 쓴다.
TENANTS = {
    "": "웰페리온",
    "jo": "조재오 지점장님 · 고척골프",
    "dc": "이승기 대표님 · 다이어트캠프",
}
KEY_COOKIES = ("NID_AUT", "NID_SES")


def state_path(tenant: str) -> Path:
    stem = f"{tenant}_naver-blog" if tenant else "naver-blog"
    return PROFILES / f"{stem}_state.json"


def read_cookies(path: Path) -> dict:
    """{쿠키이름: 만료 epoch 또는 None(세션 쿠키)} — 파일이 없으면 빈 dict."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for c in data.get("cookies", []):
        if "naver" not in str(c.get("domain", "")):
            continue
        if c.get("name") in KEY_COOKIES:
            exp = c.get("expires")
            out[c["name"]] = None if exp in (None, -1) else float(exp)
    return out


def verdict(cookies: dict) -> tuple[bool, str]:
    """(내일까지 버티나, 사람이 읽을 한 줄)."""
    if not cookies:
        return False, "로그인 기록이 없다 — 한 번도 로그인하지 않았거나 파일이 지워졌다"
    missing = [n for n in KEY_COOKIES if n not in cookies]
    if missing:
        return False, "로그인 쿠키가 모자란다(%s 없음)" % ", ".join(missing)
    session_only = [n for n, e in cookies.items() if e is None]
    if session_only:
        return False, ("브라우저를 닫으면 사라지는 쿠키뿐이다 — 로그인할 때 "
                       "「로그인 상태 유지」를 켜지 않았다. 하루 안에 풀린다")
    soonest = min(cookies.values())
    when = datetime.fromtimestamp(soonest)
    if when < datetime.now() + timedelta(days=1):
        return False, "로그인이 %s 에 풀린다 — 내일 아침을 못 넘긴다" % when.strftime("%m-%d %H:%M")
    return True, "로그인이 %s 까지 살아 있다" % when.strftime("%Y-%m-%d %H:%M")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", choices=sorted(TENANTS), help="안 주면 세 계정 전부 본다")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        print("check_blog_session 자가점검 통과")
        return 0

    targets = [args.tenant] if args.tenant is not None else sorted(TENANTS)
    worst = 0
    for t in targets:
        ok, line = verdict(read_cookies(state_path(t)))
        print("%s %-22s %s" % ("[OK]  " if ok else "[주의]", TENANTS[t], line))
        if not ok:
            worst = 1
    if worst:
        print()
        print("→ 재로그인: ops\\relogin_blog.bat jo   (조재오 지점장님)")
        print("→ 재로그인: ops\\relogin_blog.bat dc   (이승기 대표님)")
        print("   ★로그인 창에서 「로그인 상태 유지」를 반드시 켜고 로그인하십시오.")
        print("    켜지 않으면 오늘 밤에 또 풀려 내일 아침 글이 안 올라갑니다.")
    return worst


def _self_test() -> None:
    now = datetime.now().timestamp()
    ok, _ = verdict({"NID_AUT": now + 86400 * 30, "NID_SES": now + 86400 * 30})
    assert ok
    ok, msg = verdict({"NID_AUT": None, "NID_SES": None})
    assert not ok and "로그인 상태 유지" in msg, msg
    ok, msg = verdict({"NID_AUT": now + 3600, "NID_SES": now + 86400 * 30})
    assert not ok and "못 넘긴다" in msg, msg          # 하나라도 곧 풀리면 주의
    ok, msg = verdict({"NID_AUT": now + 86400 * 30})
    assert not ok and "모자란다" in msg, msg
    ok, msg = verdict({})
    assert not ok and "로그인 기록이 없다" in msg, msg


if __name__ == "__main__":
    sys.exit(main())
