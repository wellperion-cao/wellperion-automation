"""
G1 라이브 보드 스크린샷 검증 (Playwright headless)
- G1 탭 진입 → 항로 섹션 스크린샷
- 콘솔 에러 수집
"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

G1_URL = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html"
OUT_DIR = Path(r"C:\Users\jjky0\welperion-automation\qa_screenshots")
OUT_DIR.mkdir(exist_ok=True)

async def run():
    console_errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        # 콘솔 에러 수집
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error","warning") else None)

        print(f"[1] 페이지 로드: {G1_URL}")
        await page.goto(G1_URL, wait_until="networkidle", timeout=30000)

        # G1 탭 클릭 (홈 = 기본 활성화여서 바로 항로 섹션 확인)
        # G1 nav 링크 찾기
        g1_link = page.locator("a[data-doc='home'], a[data-id='G1'], a:has-text('오늘의 항로'), a[href*='home']").first
        try:
            await g1_link.click(timeout=5000)
            await page.wait_for_timeout(1500)
        except Exception:
            print("  G1 nav 클릭 불필요 (이미 홈)")

        # 항로 섹션 대기
        await page.wait_for_selector("#today-task-list, #gm1-todo-section", timeout=10000)
        await page.wait_for_timeout(3000)  # SSOT fetch 완료 대기

        # 스크린샷 1: 항로 전체
        ss1 = OUT_DIR / "g1_hangro_loaded.png"
        await page.screenshot(path=str(ss1), full_page=False)
        print(f"[2] 스크린샷 저장: {ss1}")

        # 항로 섹션만 클립
        todo_section = page.locator("#gm1-todo-section").first
        if await todo_section.count() > 0:
            ss2 = OUT_DIR / "g1_hangro_section.png"
            await todo_section.screenshot(path=str(ss2))
            print(f"[3] 항로 섹션 스크린샷: {ss2}")

        # 콘솔 에러 보고
        print(f"\n[4] 콘솔 에러/경고 ({len(console_errors)}건):")
        errs = [e for e in console_errors if "[error]" in e.lower()]
        warns = [e for e in console_errors if "[warning]" in e.lower()]
        if errs:
            for e in errs[:10]:
                print(f"  ERROR: {e}")
        if warns:
            print(f"  (경고 {len(warns)}건 — 아래 최대 5건)")
            for w in warns[:5]:
                print(f"  WARN: {w}")
        if not console_errors:
            print("  없음 (정상)")

        # 페이지 내 task 카드 수 확인
        cards = await page.locator(".task-card").count()
        print(f"\n[5] 항로 카드 수: {cards}개")

        await browser.close()

    print("\n스크린샷 경로:")
    for f in sorted(OUT_DIR.glob("g1_hangro*.png")):
        print(f"  {f}")

    # 에러 없으면 성공
    fatal_errs = [e for e in console_errors if "[error]" in e.lower() and "favicon" not in e.lower()]
    if fatal_errs:
        print(f"\n콘솔 에러 감지 ({len(fatal_errs)}건) — 검토 필요")
        return 1
    print("\n콘솔 에러 없음 — PASS")
    return 0

if __name__ == "__main__":
    rc = asyncio.run(run())
    sys.exit(rc)
