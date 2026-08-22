# -*- coding: utf-8 -*-
"""배724 화면 클릭 재현 — PIN 통과 후 LOSS 관리 모달에서 미등록사유 셀 클릭까지."""
import sys, asyncio
sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

URL  = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html"
PIN  = "1200"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        errs = []
        page.on("console", lambda m: errs.append(m) if m.type == "error" else None)

        print(f"→ {URL}")
        resp = await page.goto(URL, timeout=45000, wait_until="domcontentloaded")
        print(f"  HTTP {resp.status}")
        if resp.status != 200:
            print("FAIL: 200 아님")
            await browser.close(); return 1

        # PIN 게이트
        gate = page.locator("#miGate")
        if await gate.count() > 0:
            await page.fill("#miGate input[type=password], #miGate input[type=text]", PIN)
            await page.click("#miGate button")
            await page.wait_for_selector("#miGate", state="hidden", timeout=5000)
            print("  PIN 통과")

        # LOSS 관리 버튼
        btn = page.locator("button.action-btn", has_text="LOSS 관리")
        if await btn.count() == 0:
            print("FAIL: LOSS 관리 버튼 없음")
            await browser.close(); return 1
        await btn.first.click()
        print("  LOSS 관리 버튼 클릭")

        # 모달 내 "종료회원 목록 보기" 버튼 → closeGdoc + jumpToEndedMembers
        ended_btn = page.locator("button.btn-refresh", has_text="종료회원 목록")
        await ended_btn.first.wait_for(timeout=10000)
        await ended_btn.first.click()
        print("  종료회원 목록 보기 클릭")

        # scope=ended GAS fetch 대기 (최대 45초)
        await page.wait_for_selector("td.churn-reason-cell", state="attached", timeout=45000)
        cells = page.locator("td.churn-reason-cell")
        n = await cells.count()
        print(f"  churn-reason-cell 개수: {n}")
        if n == 0:
            print("FAIL: churn-reason-cell 없음")
            await browser.close(); return 1

        # 미등록사유 셀 중 첫 번째 rowIndex 추출 후 JS로 모달 직접 호출
        unreg = page.locator("td.churn-reason-cell[data-unregreason]")
        nu = await unreg.count()
        print(f"  미등록사유 셀(data-unregreason): {nu}개")
        # 첫 번째 셀의 rowIndex 읽기
        first_ri = await page.evaluate(
            "() => { var el = document.querySelector('td.churn-reason-cell[data-unregreason]');"
            " return el ? el.getAttribute('data-unregreason') : null; }"
        )
        print(f"  첫 번째 data-unregreason: {first_ri}")
        if not first_ri:
            print("FAIL: unregreason rowIndex 없음"); await browser.close(); return 1

        # JS로 모달 함수 직접 트리거 (visibility 우회)
        await page.evaluate(f"() => openUnregReasonModal({first_ri})")
        print(f"  openUnregReasonModal({first_ri}) 호출")

        # 모달 열림 확인
        await page.wait_for_timeout(2000)
        visible_modals = await page.evaluate(
            "() => [...document.querySelectorAll('[id*=Modal],[id*=modal],[class*=modal],[class*=overlay]')]"
            ".filter(el=>el.offsetParent!==null&&el.style.display!=='none'&&!el.classList.contains('hidden'))"
            ".map(el=>el.id||el.className.split(' ')[0]).filter(Boolean).join('|')"
        )
        print(f"  가시 모달: {visible_modals or '없음'}")
        result = "OK" if visible_modals else "WARN"

        js_errs = [m.text for m in errs]
        print(f"  콘솔 에러: {len(js_errs)}건")
        for e in js_errs[:5]:
            print(f"    {e}")

        await browser.close()
        print(f"\n=== 결과: {result} | churn-cell={n} | JS에러={len(js_errs)} ===")
        return 0 if result == "OK" else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
