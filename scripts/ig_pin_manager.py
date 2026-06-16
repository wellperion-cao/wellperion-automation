#!/usr/bin/env python3
"""인스타그램 프로필 고정(핀) 관리 — 계정별 세션으로 게시물 고정/해제.

IG는 프로필에 최대 3개 게시물 고정 가능. 본 도구로 기존 고정 해제 + 신규 고정을 자동화.

모드:
  inspect : 프로필 그리드 앞쪽 게시물 URL·고정여부 나열 + 스크린샷
  unpin   : --url 게시물 고정 해제
  pin     : --url 게시물 프로필에 고정
  (--account 기본 wellperion)

사용:
  python scripts/ig_pin_manager.py --mode inspect --account wellperion
  python scripts/ig_pin_manager.py --mode unpin --account wellperion --url https://www.instagram.com/p/XXXX/
  python scripts/ig_pin_manager.py --mode pin   --account wellperion --url https://www.instagram.com/p/XXXX/
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
PROFILE_BASE = ROOT / "profiles" / "instagram"
EVIDENCE = ROOT / "scripts" / "poc-evidence"
LOGIN_SIGNALS = ("accounts/login", "accounts/onetap", "/challenge/")

# 더보기(옵션) 버튼 — IG 게시물 우상단 "..."
MORE_SELECTORS = [
    'svg[aria-label="옵션 더 보기"]',
    'svg[aria-label="더 보기"]',
    'svg[aria-label="More options"]',
    '[aria-label="옵션 더 보기"]',
    '[aria-label="More options"]',
]
PIN_TEXTS = ("프로필에 고정", "Pin to your profile", "프로필에 고정하기")
UNPIN_TEXTS = ("고정 해제", "프로필에서 고정 해제", "Unpin from profile", "고정에서 해제")


def _profile_dir(account: str) -> Path:
    return PROFILE_BASE / account


def _login_required(url: str) -> bool:
    return any(s in (url or "") for s in LOGIN_SIGNALS)


async def _launch(account: str, headless: bool):
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=str(_profile_dir(account)),
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    return p, ctx


async def _click_more(page) -> bool:
    for sel in MORE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                # svg 자체보다 클릭 가능한 부모 버튼 클릭
                await loc.click(timeout=4000)
                await asyncio.sleep(1.2)
                return True
        except Exception:
            continue
    return False


async def _click_menu_text(page, texts) -> str | None:
    for t in texts:
        for sel in (f'button:has-text("{t}")', f'[role="button"]:has-text("{t}")',
                    f'div:has-text("{t}")'):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=3000)
                    await asyncio.sleep(1.5)
                    return t
            except Exception:
                continue
    return None


async def _confirm_dialog(page) -> None:
    """고정/해제 확인 다이얼로그가 뜨면 확인 버튼 클릭(있을 때만)."""
    for t in ("고정", "Pin", "확인", "고정 해제", "Unpin"):
        try:
            loc = page.locator(f'button:has-text("{t}")').last
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=2500)
                await asyncio.sleep(1.2)
                return
        except Exception:
            continue


async def inspect(account: str) -> int:
    p, ctx = await _launch(account, headless=True)
    try:
        page = await ctx.new_page()
        await page.goto(f"https://www.instagram.com/{account}/",
                        wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        if _login_required(page.url):
            print(f"[ERROR] 로그인 필요(account={account})")
            return 2
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        shot = EVIDENCE / f"ig_profile_{account}.png"
        await page.screenshot(path=str(shot))
        print(f"[INFO] 프로필 스크린샷: {shot}")
        # 그리드 앞쪽 게시물 + 고정 배지 여부
        rows = await page.evaluate(
            r"""() => {
              const out = [];
              const seen = new Set();
              const anchors = Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'));
              for (const a of anchors) {
                const m = a.getAttribute('href').match(/\/(p|reel)\/([A-Za-z0-9_-]+)/);
                if (!m) continue;
                const url = `https://www.instagram.com/${m[1]}/${m[2]}/`;
                if (seen.has(url)) continue;
                seen.add(url);
                const html = a.innerHTML || '';
                const pinned = /고정된 게시물|Pinned post|aria-label="고정/.test(html);
                out.push({url, pinned});
                if (out.length >= 9) break;
              }
              return out;
            }"""
        )
        print(f"[INFO] 프로필 앞쪽 게시물 {len(rows)}개:")
        for i, r in enumerate(rows):
            tag = "📌 고정" if r["pinned"] else "  일반"
            print(f"  {i+1}. {tag} | {r['url']}")
        return 0
    finally:
        try:
            await ctx.close(); await p.stop()
        except Exception:
            pass


async def set_pin(account: str, url: str, do_pin: bool) -> int:
    action = "고정" if do_pin else "고정 해제"
    p, ctx = await _launch(account, headless=False)  # 메뉴 상호작용은 headful이 안정적
    try:
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        if _login_required(page.url):
            print(f"[ERROR] 로그인 필요(account={account})")
            return 2
        if not await _click_more(page):
            print("[ERROR] 옵션 더보기(...) 버튼 미발견")
            await page.screenshot(path=str(EVIDENCE / f"ig_pin_more_fail_{account}.png"))
            return 3
        texts = PIN_TEXTS if do_pin else UNPIN_TEXTS
        clicked = await _click_menu_text(page, texts)
        if not clicked:
            # 반대 상태일 수 있음(이미 고정/이미 해제) — 메뉴 닫고 통과 보고
            print(f"[WARN] '{action}' 메뉴 항목 미발견 — 이미 {action} 상태이거나 메뉴 상이")
            await page.screenshot(path=str(EVIDENCE / f"ig_pin_menu_{account}.png"))
            return 4
        await _confirm_dialog(page)
        await asyncio.sleep(2)
        print(f"[INFO] {action} 클릭 완료: {url} (메뉴 '{clicked}')")
        await page.screenshot(path=str(EVIDENCE / f"ig_pin_done_{account}.png"))
        return 0
    finally:
        try:
            await ctx.close(); await p.stop()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="IG 프로필 고정(핀) 관리")
    ap.add_argument("--mode", choices=["inspect", "pin", "unpin"], required=True)
    ap.add_argument("--account", default="wellperion")
    ap.add_argument("--url", help="pin/unpin 대상 게시물 URL")
    args = ap.parse_args()
    if args.mode == "inspect":
        return asyncio.run(inspect(args.account))
    if not args.url:
        print("[ERROR] --url 필요")
        return 1
    return asyncio.run(set_pin(args.account, args.url, do_pin=(args.mode == "pin")))


if __name__ == "__main__":
    sys.exit(main())
