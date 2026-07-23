"""Insert Headers and Footers 플러그인으로
/ko/inquiry/ 및 /en/inquiry/ 페이지에서 lang-header ENG 버튼을 올바른 URL로 교체하는 JS 주입.

주입 JS 로직:
- /ko/inquiry/ → ENG 버튼 href = /en/inquiry/
- /en/inquiry/ → KOR 버튼이 없으면 추가 or href = /ko/inquiry/
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

EVIDENCE = Path(r"C:\Users\jjky0\welperion-automation\scripts\poc-evidence")
EVIDENCE.mkdir(parents=True, exist_ok=True)

# 주입할 JS — 문의 페이지에서만 lang-header href를 올바른 대응 URL로 교체
INJECT_JS = r"""<script>
(function() {
  var path = window.location.pathname;
  var a = document.querySelector('a.lang-header');
  if (!a) return;
  if (path.indexOf('/ko/inquiry') === 0 || path.indexOf('/ko/inquiry/') === 0) {
    a.href = '/en/inquiry/';
  } else if (path.indexOf('/en/inquiry') === 0 || path.indexOf('/en/inquiry/') === 0) {
    a.href = '/ko/inquiry/';
    a.textContent = 'KOR';
  }
})();
</script>"""

IHF_URL = "http://wellperion.com/wp/wp-admin/options-general.php?page=insert-headers-and-footers"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(Path(r"C:\Users\jjky0\welperion-automation\profiles\wordpress")),
            headless=False,
            ignore_https_errors=True,
            no_viewport=True,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        print("[INFO] Insert Headers and Footers 설정 페이지 접속...")
        await page.goto(IHF_URL, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(2500)
        if "wp-login" in page.url:
            print("[ERROR] 세션 만료 — setup 재실행 필요.")
            await browser.close()
            return

        print(f"[INFO] URL: {page.url}")
        await page.screenshot(path=str(EVIDENCE / "ihf_before.png"))

        # IHF 플러그인 구조 파악
        probe = await page.evaluate("""() => ({
            footer_textarea: !!document.querySelector('#ihf-footer, textarea[name*="footer"], textarea[id*="footer"]'),
            header_textarea: !!document.querySelector('#ihf-header, textarea[name*="header"], textarea[id*="header"]'),
            textareas: Array.from(document.querySelectorAll('textarea')).map(t => ({id: t.id, name: t.name, rows: t.rows, len: t.value.length})),
            submit: !!document.querySelector('#submit, input[type="submit"]'),
        })""")
        print(f"[INFO] IHF 구조: {probe}")

        # footer textarea에 JS 추가 (footer가 선호 — DOMContentLoaded 후 실행)
        footer_sel = None
        for sel in ["#ihf-footer", "textarea[name*='footer']", "textarea[id*='footer']"]:
            el = await page.query_selector(sel)
            if el:
                footer_sel = sel
                break
        if not footer_sel and probe.get("textareas"):
            # 두 번째 textarea가 보통 footer
            textareas = probe["textareas"]
            if len(textareas) >= 2:
                footer_sel = f"#{textareas[1]['id']}" if textareas[1].get('id') else f"textarea[name='{textareas[1]['name']}']"
            elif textareas:
                footer_sel = f"#{textareas[0]['id']}" if textareas[0].get('id') else "textarea"

        print(f"[INFO] footer textarea 셀렉터: {footer_sel}")
        if not footer_sel:
            print("[ERROR] IHF textarea 미발견 — 스크린샷 확인: ihf_before.png")
            await browser.close()
            return

        # 기존 값 읽기 — 셀렉터를 인자로 전달해 따옴표 충돌 방지
        existing = await page.evaluate(
            "(sel) => { var el = document.querySelector(sel); return el ? el.value : ''; }",
            footer_sel,
        )
        print(f"[INFO] 기존 footer 내용 (길이 {len(existing)}): {existing[:200]}")

        # 이미 주입됐으면 스킵
        if "lang-header" in existing and "inquiry" in existing:
            print("[INFO] 이미 lang-header 패치 JS 주입됨 — 스킵.")
            await browser.close()
            return

        # JS 추가 (기존 내용 보존 + 개행 후 추가)
        new_val = (existing.rstrip() + "\n" + INJECT_JS).strip()
        await page.evaluate(
            """(args) => {
                var ta = document.querySelector(args.sel);
                ta.value = args.val;
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                ta.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            {"sel": footer_sel, "val": new_val},
        )
        await page.wait_for_timeout(500)

        # 저장
        submit = await page.query_selector("#submit, input[type='submit']")
        if submit:
            await submit.click()
            await page.wait_for_timeout(3000)
            print("[INFO] IHF 저장 완료")
        await page.screenshot(path=str(EVIDENCE / "ihf_after.png"))

        # 저장 후 검증
        saved = await page.evaluate(
            "(sel) => { var el = document.querySelector(sel); return el ? el.value : ''; }",
            footer_sel,
        )
        ok = "lang-header" in saved and "inquiry" in saved
        print(f"[INFO] 저장 검증: {ok} (길이 {len(saved)})")
        print(f"[INFO] 저장 내용 (마지막 300자): {saved[-300:]}")

        await browser.close()
        print("[INFO] === IHF JS 주입 완료 ===")


asyncio.run(main())
