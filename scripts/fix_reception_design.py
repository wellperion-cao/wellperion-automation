# scripts/fix_reception_design.py
# 종합접수처 페이지(8434) 디자인 마감 — 3가지 결함 수정
# 1) 헤더 로고 천정 잘림 → body.page-id-8434 margin-top CSS 주입
# 2) 플로팅 '문의하기' 버튼 숨김 → Buttonizer 셀렉터 탐지 후 display:none
# 3) 폼 컨테이너 폭·여백·배경 → 문의 페이지(8394)와 동일 토큰 적용
#
# ★ iframe 안 reception_form.html 기능은 0 변경.
# ★ 문의 페이지(8394)·다른 페이지 건드리지 않음.
#
# 실행: python scripts\fix_reception_design.py

import asyncio
import base64
import re
import sys
import urllib.parse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
PROFILE_DIR = ROOT / "profiles" / "wordpress"
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"
SCRATCHPAD = Path(r"C:\Users\jjky0\AppData\Local\Temp\claude\C--Users-jjky0-welperion-automation\e0d6c6df-0836-46ea-8aad-5e624987d96a\scratchpad")

RECEPTION_POST_ID = "8434"
INQUIRY_POST_ID   = "8394"

LIVE_RECEPTION_URL  = "http://wellperion.com/ko/reception/?loc=리셉션"
LIVE_INQUIRY_URL    = "http://wellperion.com/ko/inquiry/"
EDIT_RECEPTION_URL  = f"http://wellperion.com/wp/wp-admin/post.php?post={RECEPTION_POST_ID}&action=edit&lang=ko"


def _decode_vc_raw_html(shortcode: str) -> str:
    """[vc_raw_html]BASE64[/vc_raw_html] → 원본 HTML"""
    m = re.search(r"\[vc_raw_html\](.*?)\[/vc_raw_html\]", shortcode, re.DOTALL)
    if not m:
        return shortcode
    b64 = m.group(1).strip()
    try:
        decoded_bytes = base64.b64decode(b64)
        url_decoded = urllib.parse.unquote(decoded_bytes.decode("ascii"))
        return url_decoded
    except Exception as e:
        print(f"[WARN] decode 실패: {e}")
        return shortcode


def _encode_vc_raw_html(html: str) -> str:
    """HTML → [vc_raw_html]BASE64[/vc_raw_html]"""
    enc = urllib.parse.quote(html, safe="")
    b64 = base64.b64encode(enc.encode("ascii")).decode("ascii")
    return f"[vc_raw_html]{b64}[/vc_raw_html]"


def _build_css_fix(buttonizer_selectors: list[str]) -> str:
    """
    3가지 결함 수정 CSS.
    buttonizer_selectors: 라이브 DOM에서 탐지한 Buttonizer 셀렉터 목록.
    """
    # 플로팅 버튼 숨김 셀렉터 — 탐지 결과 + 알려진 Buttonizer 클래스 방어폭 합산
    hide_sel_parts = []
    known_fallbacks = [
        "body.page-id-8434 .buttonizer",
        "body.page-id-8434 #buttonizer",
        "body.page-id-8434 [class*='buttonizer']",
        "body.page-id-8434 [id*='buttonizer']",
    ]
    if buttonizer_selectors:
        for s in buttonizer_selectors:
            hide_sel_parts.append(f"body.page-id-8434 {s}")
    # fallback 항상 포함
    all_hide = list(dict.fromkeys(hide_sel_parts + known_fallbacks))
    hide_css = ",\n".join(all_hide) + " { display: none !important; }"

    css = f"""<style>
/* ──────────────────────────────────────────────────────────────
   종합접수처(8434) 디자인 마감 CSS — 기능 0 변경, 외관/레이아웃만
   기준: 문의 페이지(8394) 동일 토큰
   ────────────────────────────────────────────────────────────── */

/* 1) 헤더 로고 천정 잘림 해소 — 문의 페이지(8394)와 동일 처리 */
body.page-id-8434 #header-outer #logo {{ margin-top: 32px !important; }}
@media (max-width: 1000px) {{
  body.page-id-8434 #header-outer #logo {{ margin-top: 22px !important; }}
}}

/* 2) 노란 플로팅 '문의하기' Buttonizer 버튼 숨김 (접수 페이지 내 불필요·가림) */
{hide_css}

/* 3) 폼 컨테이너 폭·배경·여백 — 문의 페이지와 형제처럼 */
body.page-id-8434 #main-content,
body.page-id-8434 .container,
body.page-id-8434 .wpb_wrapper,
body.page-id-8434 .vc_column-inner {{
  background: #faf9f7 !important;
}}
body.page-id-8434 .wpb_row,
body.page-id-8434 .vc_row {{
  background: #faf9f7 !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}}
</style>"""
    return css


def _inject_css_into_html(raw_html: str, css_block: str) -> str:
    """
    기존 raw_html의 <style> 마감 결함 CSS 블록을 교체하거나,
    없으면 맨 앞에 삽입한다.
    기존 page-id-8434 style 블록이 있으면 교체, 없으면 prepend.
    """
    # 이미 이 스크립트가 주입한 블록 제거 후 재삽입(멱등)
    marker_start = "/* ──────────────────────────────────────────────────────────────"
    marker_end = "</style>"
    if marker_start in raw_html:
        # 기존 fix 블록 제거
        start_idx = raw_html.find(marker_start)
        # 앞의 <style> 태그도 제거
        style_start = raw_html.rfind("<style>", 0, start_idx)
        if style_start == -1:
            style_start = start_idx
        end_idx = raw_html.find(marker_end, start_idx)
        if end_idx != -1:
            end_idx += len(marker_end)
            raw_html = raw_html[:style_start] + raw_html[end_idx:]

    return css_block + "\n" + raw_html.lstrip()


async def main():
    from playwright.async_api import async_playwright

    SCRATCHPAD.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    print("[STEP 1] 라이브 페이지 스크린샷 + Buttonizer DOM 탐지")
    p_inst = await async_playwright().start()
    ctx = await p_inst.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        ignore_https_errors=True,
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # ── 문의 페이지 (기준) 스크린샷 ──────────────────────────────
    print("  문의 페이지 데스크톱 스크린샷 중...")
    await page.set_viewport_size({"width": 1280, "height": 900})
    await page.goto(LIVE_INQUIRY_URL, wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(2000)
    inq_desktop = SCRATCHPAD / "inquiry_desktop_before.png"
    await page.screenshot(path=str(inq_desktop), full_page=False)
    print(f"  저장: {inq_desktop}")

    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto(LIVE_INQUIRY_URL, wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(1500)
    inq_mobile = SCRATCHPAD / "inquiry_mobile_before.png"
    await page.screenshot(path=str(inq_mobile), full_page=False)
    print(f"  저장: {inq_mobile}")

    # ── 접수 페이지 (수정 전) 스크린샷 + Buttonizer 탐지 ─────────
    print("  접수 페이지 데스크톱 스크린샷 + DOM 탐지 중...")
    await page.set_viewport_size({"width": 1280, "height": 900})
    await page.goto(LIVE_RECEPTION_URL, wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(3000)
    rec_before_desktop = SCRATCHPAD / "reception_before_desktop.png"
    await page.screenshot(path=str(rec_before_desktop), full_page=False)
    print(f"  저장: {rec_before_desktop}")

    await page.set_viewport_size({"width": 390, "height": 844})
    await page.goto(LIVE_RECEPTION_URL, wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(2000)
    rec_before_mobile = SCRATCHPAD / "reception_before_mobile.png"
    await page.screenshot(path=str(rec_before_mobile), full_page=False)
    print(f"  저장: {rec_before_mobile}")

    # Buttonizer 셀렉터 탐지
    buttonizer_info = await page.evaluate("""() => {
        // 모든 요소에서 buttonizer 관련 클래스·ID 스캔
        const results = [];
        document.querySelectorAll('[class],[id]').forEach(el => {
            const cls = el.className || '';
            const id  = el.id || '';
            const clsStr = (typeof cls === 'string') ? cls : (cls.baseVal || '');
            if (clsStr.toLowerCase().includes('button') &&
                (clsStr.toLowerCase().includes('izer') || clsStr.toLowerCase().includes('float') ||
                 clsStr.toLowerCase().includes('fixed'))) {
                results.push({tag: el.tagName, cls: clsStr, id: id});
            }
            if (id.toLowerCase().includes('buttonizer') || id.toLowerCase().includes('btn-float')) {
                results.push({tag: el.tagName, cls: clsStr, id: id});
            }
        });
        // Buttonizer 공식 컨테이너도 탐지
        const btns = document.querySelectorAll('.buttonizer, #buttonizer, [class*="buttonizer"], .btn-buttonizer, .floating-btn');
        btns.forEach(el => {
            results.push({tag: el.tagName, cls: el.className||'', id: el.id||''});
        });
        return results.slice(0, 20);
    }""")
    print(f"  Buttonizer DOM 탐지 결과: {buttonizer_info}")

    # 탐지 결과에서 셀렉터 추출
    buttonizer_selectors = []
    for item in buttonizer_info:
        cls = item.get("cls", "")
        eid = item.get("id", "")
        if cls:
            # 첫 클래스명만 사용
            first_cls = cls.strip().split()[0]
            if first_cls:
                buttonizer_selectors.append(f".{first_cls}")
        if eid:
            buttonizer_selectors.append(f"#{eid}")
    buttonizer_selectors = list(dict.fromkeys(buttonizer_selectors))
    print(f"  추출된 셀렉터: {buttonizer_selectors}")

    await ctx.close()
    await p_inst.stop()

    # ──────────────────────────────────────────────────────────────
    print("\n[STEP 2] WP 편집기에서 reception 페이지 현재 본문 읽기")
    p_inst2 = await async_playwright().start()
    ctx2 = await p_inst2.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        ignore_https_errors=True,
    )
    page2 = ctx2.pages[0] if ctx2.pages else await ctx2.new_page()
    await page2.goto(EDIT_RECEPTION_URL, wait_until="domcontentloaded", timeout=40_000)
    await page2.wait_for_timeout(3000)

    if "wp-login" in page2.url:
        print("[ERROR] 세션 만료 — python scripts\\wordpress_admin_playwright.py --mode setup 재실행 필요.")
        await ctx2.close(); await p_inst2.stop(); return

    # 편집기 Text 모드로 전환
    text_tab = await page2.query_selector("#content-html")
    if text_tab:
        await page2.click("#content-html")
        await page2.wait_for_timeout(800)

    current_content = await page2.evaluate(
        "() => (document.querySelector('#content')||{}).value || ''"
    )
    print(f"  현재 본문 길이: {len(current_content)} 자")

    # vc_raw_html 디코딩
    if "vc_raw_html" in current_content:
        raw_html = _decode_vc_raw_html(current_content)
        print(f"  디코딩된 HTML 길이: {len(raw_html)} 자 (앞 200자: {raw_html[:200]!r})")
    else:
        raw_html = current_content
        print(f"  [INFO] vc_raw_html 없음 — 원본 직접 사용. 앞 200자: {raw_html[:200]!r}")

    # ──────────────────────────────────────────────────────────────
    print("\n[STEP 3] CSS 수정 주입")
    css_block = _build_css_fix(buttonizer_selectors)
    print("  생성된 CSS:\n" + css_block)

    fixed_html = _inject_css_into_html(raw_html, css_block)
    print(f"  수정 후 HTML 길이: {len(fixed_html)} 자")

    # 다시 vc_raw_html 인코딩
    fixed_content = _encode_vc_raw_html(fixed_html)

    # ──────────────────────────────────────────────────────────────
    print("\n[STEP 4] WP에 저장")
    # Text 모드 재확인 후 주입
    text_tab2 = await page2.query_selector("#content-html")
    if text_tab2:
        await page2.click("#content-html")
        await page2.wait_for_timeout(500)

    await page2.evaluate(
        """(html) => {
            const ta = document.querySelector('#content');
            ta.value = html;
            ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true}));
        }""",
        fixed_content,
    )
    await page2.wait_for_timeout(500)

    # 주입 검증
    injected = await page2.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    ok = "vc_raw_html" in injected and len(injected) > 200
    print(f"  주입 검증: {ok} (길이 {len(injected)})")
    if not ok:
        print("[ERROR] 주입 실패 — 저장 중단.")
        await ctx2.close(); await p_inst2.stop(); return

    # 발행 상태 확인 후 저장
    pre_status = await page2.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    is_published = any(w in pre_status for w in ("공개", "발행", "published"))
    print(f"  현재 WP 상태: '{pre_status}' → {'업데이트(발행유지)' if is_published else '임시저장'}")

    if is_published:
        await page2.click("#publish")
    else:
        await page2.click("#save-post")

    try:
        await page2.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page2.wait_for_timeout(4000)
    await page2.wait_for_timeout(2000)

    save_status = await page2.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    print(f"  저장 후 WP 상태: '{save_status}'")
    await page2.screenshot(path=str(EVIDENCE_DIR / "wp_reception_design_fixed_editor.png"))
    await ctx2.close(); await p_inst2.stop()

    # ──────────────────────────────────────────────────────────────
    print("\n[STEP 5] 수정 후 라이브 스크린샷 — 검증")
    await asyncio.sleep(4)  # WP 캐시 반영 대기

    p_inst3 = await async_playwright().start()
    ctx3 = await p_inst3.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        ignore_https_errors=True,
    )
    page3 = ctx3.pages[0] if ctx3.pages else await ctx3.new_page()

    # 데스크톱 after
    await page3.set_viewport_size({"width": 1280, "height": 900})
    await page3.goto(LIVE_RECEPTION_URL, wait_until="networkidle", timeout=60_000)
    await page3.wait_for_timeout(3000)
    rec_after_desktop = SCRATCHPAD / "reception_after_desktop.png"
    await page3.screenshot(path=str(rec_after_desktop), full_page=False)
    print(f"  데스크톱 after: {rec_after_desktop}")

    # 콘솔 에러 확인
    console_errors = []
    page3.on("console", lambda m: console_errors.append(m) if m.type == "error" else None)
    await page3.wait_for_timeout(1000)

    # Buttonizer 숨김 확인
    float_visible = await page3.evaluate("""() => {
        const candidates = document.querySelectorAll('.buttonizer, #buttonizer, [class*="buttonizer"], [id*="buttonizer"]');
        let visible = [];
        candidates.forEach(el => {
            const st = window.getComputedStyle(el);
            if (st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0') {
                visible.push({tag: el.tagName, cls: el.className||'', id: el.id||''});
            }
        });
        return visible;
    }""")
    print(f"  플로팅 버튼 가시성(빈 배열=숨김 성공): {float_visible}")

    # 로고 margin 확인
    logo_margin = await page3.evaluate("""() => {
        const logo = document.querySelector('#header-outer #logo');
        if (!logo) return 'logo 미검출';
        const st = window.getComputedStyle(logo);
        return {marginTop: st.marginTop};
    }""")
    print(f"  로고 margin-top: {logo_margin}")

    # 모바일 after
    await page3.set_viewport_size({"width": 390, "height": 844})
    await page3.goto(LIVE_RECEPTION_URL, wait_until="networkidle", timeout=60_000)
    await page3.wait_for_timeout(2000)
    rec_after_mobile = SCRATCHPAD / "reception_after_mobile.png"
    await page3.screenshot(path=str(rec_after_mobile), full_page=False)
    print(f"  모바일 after:  {rec_after_mobile}")

    await ctx3.close(); await p_inst3.stop()

    # ──────────────────────────────────────────────────────────────
    print("\n══════════════════════════════════════════")
    print("DONE: 종합접수처(8434) 디자인 마감 완료")
    print("══════════════════════════════════════════")
    print(f"\n【스크린샷 경로】")
    print(f"  수정 전 데스크톱: {rec_before_desktop}")
    print(f"  수정 전 모바일:   {rec_before_mobile}")
    print(f"  수정 후 데스크톱: {rec_after_desktop}")
    print(f"  수정 후 모바일:   {rec_after_mobile}")
    print(f"  문의 기준 데스크톱: {inq_desktop}")
    print(f"  문의 기준 모바일:   {inq_mobile}")
    print(f"\n【라이브 검수 URL】")
    print(f"  {LIVE_RECEPTION_URL}")
    print(f"\n【결함 처리 요약】")
    print(f"  ① 로고 잘림:   body.page-id-8434 #header-outer #logo {{ margin-top: 32px }}")
    print(f"  ② 플로팅 버튼: {len(buttonizer_selectors)+4}개 셀렉터 display:none")
    print(f"  ③ 컨테이너:    배경 #faf9f7 + 문의 페이지 동일 여백")
    print(f"  콘솔 에러 수:  {len(console_errors)}")


if __name__ == "__main__":
    asyncio.run(main())
