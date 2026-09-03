#!/usr/bin/env python3
"""cafe24 호스팅 관리 화면 자동화 (DNS 등) — GM 이 로그인만 하고 나머지는 시토가 한다.

프로필 profiles/cafe24 에 로그인 상태가 남는다(당근·워드프레스 업로더와 같은 방식). 비밀번호는 저장소·로그에 남지 않는다.

    C:/Python314/python.exe scripts/cafe24_browser.py login      # 창을 띄우고 GM 로그인을 기다린다(최대 10분)
    C:/Python314/python.exe scripts/cafe24_browser.py dns        # 로그인된 프로필로 DNS 관리 화면까지 가서 캡처·링크 덤프
    C:/Python314/python.exe scripts/cafe24_browser.py goto <url> # 임의 화면 캡처·링크 덤프(탐색용)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "profiles" / "cafe24"
OUT = REPO / "status" / "cafe24"
LOGIN_URL = "https://hosting.cafe24.com/?controller=new_member&method=login&sec=on"
MYSERVICE_URL = "https://hosting.cafe24.com/?controller=myservice_hosting_main"
sys.stdout.reconfigure(encoding="utf-8")


def _ctx(p, headed: bool):
    PROFILE.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(str(PROFILE), headless=not headed, channel="chrome",
                                               viewport={"width": 1400, "height": 1000}, locale="ko-KR")


def logged_in(page) -> bool:
    # 로그인 뒤에는 상단에 '로그아웃' 링크가 생기고 '로그인' 링크(new_member&method=login)가 사라진다(2026-09-03 실측)
    try:
        return page.locator("a:has-text('로그아웃')").count() > 0             and page.locator("a[href*='method=login']").count() == 0
    except Exception:
        return False


def dump(page, tag: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{tag}.png"), full_page=True)
    links = page.evaluate("""() => Array.from(document.querySelectorAll('a,button')).map(e => ({
        t:(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,60), h:e.getAttribute('href')||'', oc:(e.getAttribute('onclick')||'').slice(0,80)}))
        .filter(x => x.t)""")
    (OUT / f"{tag}.links.txt").write_text("\n".join(f"{l['t']} | {l['h']} | {l['oc']}" for l in links), encoding="utf-8")
    print(f"[{tag}] url={page.url}\n  캡처 {OUT / (tag + '.png')} · 링크 {len(links)}개 → {OUT / (tag + '.links.txt')}")


def cmd_login() -> int:
    with sync_playwright() as p:
        ctx = _ctx(p, headed=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("cafe24 창을 띄웠다 — GM 로그인 대기(최대 10분)")
        for _ in range(120):
            time.sleep(5)
            if logged_in(page):
                print("로그인 감지 — 프로필에 저장됨")
                dump(page, "after_login")
                ctx.close()
                return 0
        print("10분 안에 로그인 안 됨")
        ctx.close()
        return 1


def cmd_goto(url: str, tag: str = "goto") -> int:
    with sync_playwright() as p:
        ctx = _ctx(p, headed=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        if not logged_in(page):
            print("로그인 상태 아님 — 먼저 login 을 돌려라")
            dump(page, "not_logged_in")
            ctx.close()
            return 2
        dump(page, tag)
        ctx.close()
        return 0


if __name__ == "__main__":
    a = sys.argv[1:] or ["login"]
    if a[0] == "login":
        raise SystemExit(cmd_login())
    if a[0] == "dns":
        raise SystemExit(cmd_goto(MYSERVICE_URL, "myservice"))
    if a[0] == "goto":
        raise SystemExit(cmd_goto(a[1], a[2] if len(a) > 2 else "goto"))
    raise SystemExit("사용법: login | dns | goto <url> [tag]")
