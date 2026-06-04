"""ENG 버튼 HTML 구조 + WPML 스위처 위젯 위치 분석"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

EVIDENCE = Path(r"C:\Users\jjky0\welperion-automation\scripts\poc-evidence")
EVIDENCE.mkdir(parents=True, exist_ok=True)

JS_ENG_BTN = """
() => {
    // ENG 텍스트를 가진 링크의 부모 구조 덤프
    var eng_links = Array.from(document.querySelectorAll("a")).filter(function(a) {
        return a.innerText.trim() === "ENG";
    });
    return eng_links.map(function(a) {
        var p1 = a.parentElement;
        var p2 = p1 ? p1.parentElement : null;
        var p3 = p2 ? p2.parentElement : null;
        return {
            href: a.href,
            a_class: a.className,
            parent1: p1 ? {tag: p1.tagName, cls: p1.className, html: p1.outerHTML.substring(0,500)} : null,
            parent2: p2 ? {tag: p2.tagName, cls: p2.className} : null,
            parent3: p3 ? {tag: p3.tagName, cls: p3.className} : null,
        };
    });
}
"""

JS_HEADER = """
() => {
    // 헤더 영역 전체에서 언어 관련 요소
    var header = document.querySelector("#header-outer, header, #masthead");
    if (!header) return "no-header";
    var lang_els = Array.from(header.querySelectorAll("[class*='lang'], [class*='wpml'], [id*='lang'], [id*='wpml']"));
    return lang_els.map(function(e) {
        return {tag: e.tagName, cls: e.className, id: e.id, html: e.outerHTML.substring(0,400)};
    });
}
"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
            locale="ko-KR",
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9"},
        )
        page = await ctx.new_page()
        await page.goto("http://wellperion.com/ko/inquiry/", wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(2000)

        print("=== ENG 버튼 구조 ===")
        eng = await page.evaluate(JS_ENG_BTN)
        for item in eng:
            print(f"  href: {item['href']}")
            print(f"  a.class: {item['a_class']}")
            if item.get('parent1'):
                print(f"  parent1: {item['parent1']['tag']}.{item['parent1']['cls']}")
                print(f"  parent1.html: {item['parent1']['html']}")
            if item.get('parent2'):
                print(f"  parent2: {item['parent2']['tag']}.{item['parent2']['cls']}")
            if item.get('parent3'):
                print(f"  parent3: {item['parent3']['tag']}.{item['parent3']['cls']}")

        print("\n=== 헤더 언어 요소 ===")
        header_lang = await page.evaluate(JS_HEADER)
        if isinstance(header_lang, list):
            for el in header_lang:
                print(f"  {el['tag']}#{el['id']}.{el['cls']}: {el['html'][:300]}")
        else:
            print(f"  {header_lang}")

        await browser.close()


asyncio.run(main())
