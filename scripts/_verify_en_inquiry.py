"""비로그인 검증: /ko/inquiry/ 언어 스위처 + /en/inquiry/ 라이브 확인"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

EVIDENCE = Path(r"C:\Users\jjky0\welperion-automation\scripts\poc-evidence")
EVIDENCE.mkdir(parents=True, exist_ok=True)

JS_SWITCHER = """
() => {
    const sels = [
        ".wpml-ls-statics-shortcode_actions",
        ".wpml-ls-menu-item",
        ".icl_lang_sel_widget",
        ".wpml-ls",
        ".lang-sel",
        "#lang_sel",
        ".language-switcher"
    ];
    const results = {};
    for (const s of sels) {
        const els = document.querySelectorAll(s);
        if (els.length) {
            results[s] = Array.from(els).map(function(e) {
                return {html: e.outerHTML.substring(0, 300), href: (e.href || "")};
            });
        }
    }
    results["all_en_links"] = Array.from(document.querySelectorAll("a")).filter(function(a) {
        return a.href && a.href.indexOf("/en") !== -1;
    }).map(function(a) {
        return {t: a.innerText.trim().substring(0, 30), h: a.href};
    });
    return results;
}
"""

JS_H2 = "() => { var h = document.querySelector('h2'); return h ? h.innerText.trim() : 'none'; }"
JS_BODY = "() => document.body.className"
JS_LOGO = "() => { var l = document.querySelector('#header-outer #logo'); return l ? window.getComputedStyle(l).marginTop : 'not-found'; }"


async def main():
    async with async_playwright() as p:
        # --- /ko/inquiry/ 언어 스위처 분석 ---
        browser = await p.chromium.launch(headless=True)
        ctx_ko = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
            locale="ko-KR",
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
        )
        page_ko = await ctx_ko.new_page()
        await page_ko.goto("http://wellperion.com/ko/inquiry/", wait_until="networkidle", timeout=40000)
        await page_ko.wait_for_timeout(2000)

        switcher = await page_ko.evaluate(JS_SWITCHER)
        print("=== /ko/inquiry/ 언어 스위처 ===")
        for k, v in switcher.items():
            print(f"  [{k}]: {str(v)[:400]}")

        await page_ko.screenshot(path=str(EVIDENCE / "wp_inquiry_ko_eng_btn.png"))
        print("screenshot: wp_inquiry_ko_eng_btn.png")

        # --- /en/inquiry/ 라이브 확인 ---
        ctx_en = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page_en = await ctx_en.new_page()
        await page_en.goto("http://wellperion.com/en/inquiry/", wait_until="networkidle", timeout=40000)
        await page_en.wait_for_timeout(2000)

        print("\n=== /en/inquiry/ 라이브 ===")
        print(f"  FINAL_URL  : {page_en.url}")
        print(f"  BODY_CLASS : {(await page_en.evaluate(JS_BODY))[:120]}")
        print(f"  H2         : {await page_en.evaluate(JS_H2)}")
        print(f"  LOGO_MT    : {await page_en.evaluate(JS_LOGO)}")

        await page_en.screenshot(path=str(EVIDENCE / "wp_inquiry_en_LIVE.png"))
        print("screenshot: wp_inquiry_en_LIVE.png")

        await browser.close()


asyncio.run(main())
