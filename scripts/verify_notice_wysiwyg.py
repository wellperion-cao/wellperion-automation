"""
v2.32 wysiwyg 검증
- contenteditable에 텍스트 입력 + ★ 클릭 시 마크다운 토큰("**") 안 보이고 style만 적용되는지
- 양쪽 캡처 (편집 영역 + 미리보기)
"""
import asyncio, time
from pathlib import Path
from playwright.async_api import async_playwright

URL = f"https://wellperion-cao.github.io/wellperion-automation/coo/notice/notice_template.html?v={int(time.time())}"
OUT = Path(__file__).resolve().parents[1] / ".verify_screenshots"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1700, "height": 1500})
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=30000)

        # 1. 3줄 입력 후 1번째 줄에만 크게 적용 (3번째 줄 무변경 검증)
        await page.click("#noticeBody")
        await page.keyboard.type("첫번째 줄")
        await page.keyboard.press("Enter")
        await page.keyboard.type("두번째 줄")
        await page.keyboard.press("Enter")
        await page.keyboard.type("세번째 줄")
        await page.wait_for_timeout(300)

        # 1번째 줄 어딘가에 커서 → 크게 클릭
        await page.evaluate("""() => {
            const ed = document.getElementById('noticeBody');
            const firstBlock = ed.children[0];  // 첫 <p>
            if(firstBlock){
                const range = document.createRange();
                range.setStart(firstBlock, 0);
                range.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }
        }""")
        await page.click("button:has-text('크')")
        await page.wait_for_timeout(300)

        # 그 상태에서 ★ 도 클릭
        await page.click("button:has-text('★')")
        await page.wait_for_timeout(300)

        # 편집기 innerHTML 확인 (마크다운 토큰이 보이면 안 됨)
        editor_html = await page.eval_on_selector("#noticeBody", "el => el.innerHTML")
        editor_text = await page.eval_on_selector("#noticeBody", "el => el.innerText")
        preview_html = await page.eval_on_selector("#noticePvBody", "el => el.innerHTML")
        print("=== EDITOR innerHTML ===")
        print(editor_html)
        print()
        print("=== EDITOR innerText (사용자가 실제 보는 텍스트) ===")
        print(editor_text)
        print()
        print("=== PREVIEW innerHTML ===")
        print(preview_html[:400])

        # 스크린샷 (form + preview 전체)
        await page.screenshot(path=str(OUT / "notice_wysiwyg_v232.png"), full_page=False)

        # 추가: B 굵게도 적용
        await page.click("#noticeBody")
        await page.keyboard.press("Control+End")
        await page.keyboard.press(" ")
        await page.keyboard.type("두번째 줄 굵게")
        # 두번째 줄 굵게 부분만 선택
        await page.evaluate("""() => {
            const ed = document.getElementById('noticeBody');
            const sel = window.getSelection();
            const range = document.createRange();
            const lastText = ed.lastChild;
            if(lastText && lastText.nodeType === 3){
                range.setStart(lastText, lastText.textContent.indexOf('두번째'));
                range.setEnd(lastText, lastText.textContent.length);
                sel.removeAllRanges();
                sel.addRange(range);
            }
        }""")
        await page.click("button:has-text('B'):not(:has-text('⮊'))")
        await page.wait_for_timeout(300)

        editor_html_2 = await page.eval_on_selector("#noticeBody", "el => el.innerHTML")
        print()
        print("=== AFTER bold ===")
        print(editor_html_2)

        await page.screenshot(path=str(OUT / "notice_wysiwyg_v232_after.png"), full_page=False)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
