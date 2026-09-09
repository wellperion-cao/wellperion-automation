# -*- coding: utf-8 -*-
"""사람이 평범한 크롬에서 로그인하고, 그 세션만 받아 저장한다.

왜 있나 — 2026-09-09. 파트너(조재오 부장님) 계정을 붙이려고 playwright 가 띄운 창에서
로그인을 시도했더니 네이버가 자동입력 방지문자를 반복해서 띄우고 로그인 화면으로 되돌렸다.
자동화 표시를 끄고 진짜 크롬으로 바꿔도 같았다. 원인은 창을 자동화 도구가 띄웠다는 것 자체다.

그래서 순서를 뒤집는다.
  1) 크롬을 그냥 띄운다 — 자동화 도구가 관여하지 않는다. 사람이 평소처럼 로그인한다.
  2) 로그인이 끝난 뒤에야 붙어서 쿠키만 받아 저장한다.
로그인하는 동안에는 붙지 않으므로 사이트가 볼 자동화 흔적이 없다.

쓰는 법:
  python scripts/login_capture.py --site naver
  python scripts/login_capture.py --site instagram --tenant jo

--tenant 를 주면 그 계정 자리에 저장한다(scripts/tenant_profile.py 와 같은 규칙).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 9222

# site -> (로그인 주소, 프로필 이름, 로그인 성공을 알리는 쿠키)
SITES = {
    "naver": ("https://nid.naver.com/nidlogin.login", "naver-blog", ("naver.com", ("NID_AUT", "NID_SES"))),
    "cafe": ("https://nid.naver.com/nidlogin.login", "naver-cafe", ("naver.com", ("NID_AUT", "NID_SES"))),
    "instagram": ("https://www.instagram.com/accounts/login/", "instagram", ("instagram.com", ("sessionid",))),
    "danggn": ("https://www.daangn.com/", "danggn", ("daangn.com", ("_karrot_session", "sid"))),
}


def find_chrome() -> str | None:
    for p in (
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"),
    ):
        if p and Path(p).exists():
            return p
    return None


def _write_state(state_path: Path, cdp_cookies: list) -> None:
    """크롬이 준 쿠키를 playwright storage_state 형식으로 옮겨 적는다."""
    import json

    out = []
    for c in cdp_cookies:
        exp = c.get("expires", -1)
        out.append({
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "expires": float(exp) if exp and exp > 0 else -1,
            "httpOnly": bool(c.get("httpOnly")),
            "secure": bool(c.get("secure")),
            "sameSite": {"Strict": "Strict", "Lax": "Lax", "None": "None"}.get(c.get("sameSite"), "Lax"),
        })
    state_path.write_text(json.dumps({"cookies": out, "origins": []}, ensure_ascii=False),
                          encoding="utf-8")


async def capture(profile_dir: Path, state_path: Path, domain: str, names: tuple, wait_sec: int) -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = None
        for _ in range(20):                      # 크롬이 뜰 때까지만 짧게 기다린다
            try:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{PORT}")
                break
            except Exception:
                await asyncio.sleep(1)
        if browser is None:
            print("[ERROR] 크롬에 붙지 못했습니다. 창이 떠 있는지 확인하세요.")
            return 2
        # 붙은 크롬에서는 playwright 의 cookies()/storage_state() 가 오류를 낸다
        # (ValueError: list.remove(x): x not in list · 2026-09-09 실측). 크롬에 직접 묻는다.
        # 창(page)에 붙이면 로그인 중 화면이 넘어갈 때 함께 끊긴다 — 브라우저에 붙인다.
        cdp = await browser.new_browser_cdp_session()

        print(f"[INFO] 크롬에 붙었습니다. 로그인을 기다립니다 (최대 {wait_sec}초).")
        waited = 0
        while waited < wait_sec:
            cookies = (await cdp.send("Storage.getCookies")).get("cookies", [])
            if any(domain in (c.get("domain") or "") and c.get("name") in names and c.get("value")
                   for c in cookies):
                state_path.parent.mkdir(parents=True, exist_ok=True)
                _write_state(state_path, cookies)
                print(f"[OK] 로그인 확인 — 세션 저장 완료 → {state_path.name} (값은 화면에 찍지 않습니다)")
                return 0
            await asyncio.sleep(5)
            waited += 5
            if waited % 60 == 0:
                print(f"[INFO] 기다리는 중... ({waited}/{wait_sec}초)")
        print("[WARN] 시간 안에 로그인이 확인되지 않았습니다. 창을 닫지 말고 다시 실행하세요.")
        return 3


async def save_from_profile(profile_dir: Path, state_path: Path, domain: str, names: tuple) -> int:
    """사람이 로그인해 둔 크롬 프로필을 열어 세션만 꺼낸다. 크롬은 닫혀 있어야 한다."""
    from playwright.async_api import async_playwright

    if not profile_dir.exists():
        print(f"[ERROR] 그 자리가 없습니다: {profile_dir.name}")
        return 2
    async with async_playwright() as p:
        try:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), headless=True, channel="chrome",
            )
        except Exception as e:
            print(f"[ERROR] 프로필을 열지 못했습니다 — 크롬이 아직 떠 있는지 보세요. ({type(e).__name__})")
            return 2
        cookies = await ctx.cookies()
        hit = [c for c in cookies
               if domain in (c.get("domain") or "") and c.get("name") in names and c.get("value")]
        if not hit:
            got = sorted({c["name"] for c in cookies if domain in (c.get("domain") or "")})
            print(f"[WARN] 로그인 흔적이 없습니다. 그 사이트 쿠키 {len(got)}종이 있으나 "
                  f"인증 쿠키({'·'.join(names)})가 없습니다.")
            await ctx.close()
            return 3
        state_path.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(state_path))
        await ctx.close()
        print(f"[OK] 세션 저장 완료 → {state_path.name} (값은 화면에 찍지 않습니다)")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="평범한 크롬에서 로그인 → 세션만 저장")
    ap.add_argument("--site", required=True, choices=sorted(SITES))
    ap.add_argument("--tenant", default="", help="계정 자리 이름 (예: jo). 없으면 웰페리온")
    ap.add_argument("--wait", type=int, default=900, help="로그인 기다리는 초 (기본 900)")
    ap.add_argument("--no-launch", action="store_true", help="크롬을 새로 띄우지 않고 이미 뜬 창에 붙는다")
    ap.add_argument("--step", choices=["open", "save"], default="",
                    help="open: 감시 포트 없이 크롬만 띄운다(사람이 로그인) / "
                         "save: 그 크롬을 닫은 뒤 프로필에서 세션만 꺼내 저장한다")
    a = ap.parse_args()

    url, channel, (domain, names) = SITES[a.site]
    stem = f"{a.tenant}_{channel}" if a.tenant else channel
    profile_dir = ROOT / "profiles" / f"{stem}_login"      # 로그인 전용 자리 — 발행용 프로필과 섞지 않는다
    state_path = ROOT / "profiles" / f"{stem}_state.json"

    if a.step == "open":
        # 감시 포트조차 켜지 않는다 — 사이트가 볼 자동화 흔적이 하나도 없다.
        chrome = find_chrome()
        if not chrome:
            print("[ERROR] 크롬을 찾지 못했습니다.")
            return 2
        profile_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([chrome, f"--user-data-dir={profile_dir}", "--start-maximized", url])
        print(f"[INFO] 크롬을 띄웠습니다({a.site}). 로그인한 뒤 그 창을 닫아 주세요.")
        print("[INFO] 닫으신 뒤 --step save 로 세션을 꺼냅니다.")
        return 0

    if a.step == "save":
        return asyncio.run(save_from_profile(profile_dir, state_path, domain, names))

    if not a.no_launch:
        chrome = find_chrome()
        if not chrome:
            print("[ERROR] 크롬을 찾지 못했습니다. CHROME_PATH 로 경로를 알려주세요.")
            return 2
        profile_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([
            chrome,
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={PORT}",
            "--start-maximized",
            url,
        ])
        print(f"[INFO] 크롬 창을 띄웠습니다. 이 창에서 평소처럼 로그인하세요 ({a.site}).")
        time.sleep(3)

    return asyncio.run(capture(profile_dir, state_path, domain, names, a.wait))


if __name__ == "__main__":
    sys.exit(main())
