# scripts/wordpress_admin_playwright.py
# v0.1 — 워드프레스(wellperion.com) 관리자 반자동 편집기 스캐폴드
#         (네이버·카카오 패턴 차용: Playwright + Persistent Profile 1회 로그인 세션)
#
# 정책: 비밀번호 하드코딩/입력 없음 — GM이 브라우저에서 직접 로그인, 세션만 프로필에 저장.
#       wellperion.com 자체서명 인증서 → ignore_https_errors=True 로 우회.
#       종착지=초안(draft) 우선. 실제 발행(publish)은 GM go 가드.
#
# 모드:
#   setup  : 크롬 기동 → GM 수동 로그인 → wordpress_logged_in 쿠키 자동 감지·세션 저장 (Enter 불필요)
#   check  : 저장된 세션으로 wp-admin 접속해 로그인 유지 여부만 확인 (읽기 전용)
#
# 실행:
#   python scripts\wordpress_admin_playwright.py --mode setup
#   python scripts\wordpress_admin_playwright.py --mode check
#
# 페이지 신설/편집 자동화(draft/publish)는 GM 로그인 후 wp-admin DOM 실측하여 다음 단계 구현.

import argparse
import asyncio
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
PROFILE_DIR = ROOT / "profiles" / "wordpress"

# 주의: wellperion.com 은 HTTPS 미동작(SSL 연결 실패). HTTP 전용 사이트 → http:// 고정.
WP_ADMIN_URL = "http://wellperion.com/wp/wp-admin/"
WP_LOGIN_URL = "http://wellperion.com/wp/wp-login.php"
# 로그인 성공 = wordpress_logged_in_* 쿠키 존재 (워드프레스 표준 인증 쿠키)
AUTH_COOKIE_PREFIX = "wordpress_logged_in"


def _import_playwright():
    from playwright.async_api import async_playwright
    return async_playwright


async def _launch(async_playwright):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        ignore_https_errors=True,      # 자체서명 인증서 우회
        args=["--start-maximized"],
        no_viewport=True,
    )
    return p, ctx


def _has_wp_auth(cookies) -> bool:
    return any((c.get("name") or "").startswith(AUTH_COOKIE_PREFIX) for c in cookies)


async def run_setup() -> int:
    async_playwright = _import_playwright()
    print("[INFO] === 워드프레스 관리자 SETUP — GM 수동 로그인 ===")
    print(f"[INFO] 프로필 저장: {PROFILE_DIR}")
    p, ctx = await _launch(async_playwright)
    # 기존 세션 비움 — 원하는 계정으로 새로 로그인
    try:
        await ctx.clear_cookies()
        print("[INFO] 기존 세션 비움 — 관리자 계정으로 로그인하세요.")
    except Exception as e:
        print(f"[WARN] 기존 세션 비우기 실패(무시): {e}")
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await page.goto(WP_LOGIN_URL, wait_until="domcontentloaded", timeout=40_000)
    except Exception as e:
        print(f"[WARN] 로그인 페이지 진입 경고(무시 가능): {e}")
    print("[INFO] 브라우저에서 워드프레스 관리자 로그인을 완료하세요 — 로그인 감지 시 자동 저장됩니다.")
    print("[INFO] (Enter 불필요. 최대 10분 대기, 로그인 끝나면 자동 마무리)")

    has_session = False
    waited, deadline = 0, 600
    while waited < deadline:
        try:
            cookies = await ctx.cookies()
        except Exception:
            break  # GM이 창을 닫음
        if _has_wp_auth(cookies):
            has_session = True
            break
        await asyncio.sleep(3)
        waited += 3
    if has_session:
        await asyncio.sleep(2)
        print("[INFO] 워드프레스 세션 확인 — 저장 완료 (값 비공개: ****)")
    else:
        print("[WARN] 10분 내 로그인 미감지 — 다시 실행하거나 GM 확인 필요.")
    await ctx.close()
    await p.stop()
    print("[INFO] === SETUP 완료 ===")
    return 0 if has_session else 2


async def run_check() -> int:
    async_playwright = _import_playwright()
    print("[INFO] === 워드프레스 세션 CHECK (읽기 전용) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(WP_ADMIN_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(3000)
    url = page.url
    logged_in = "wp-login" not in url and _has_wp_auth(await ctx.cookies())
    print(f"[INFO] 최종 URL: {url}")
    print(f"[INFO] 로그인 유지: {logged_in}")
    await ctx.close()
    await p.stop()
    return 0 if logged_in else 2


INSPECT_DIR = ROOT / "scripts" / "poc-evidence"
PAGES_LIST_URL = "http://wellperion.com/wp/wp-admin/edit.php?post_type=page"
THEMES_URL = "http://wellperion.com/wp/wp-admin/themes.php"
PLUGINS_URL = "http://wellperion.com/wp/wp-admin/plugins.php"


async def run_inspect() -> int:
    """읽기 전용 실측 — 워드프레스 버전·테마·플러그인·페이지 목록·편집기 종류 파악.
    문의 페이지 신설/홈 편집 자동화 설계용. 어떤 변경도 가하지 않음."""
    async_playwright = _import_playwright()
    print("[INFO] === 워드프레스 관리자 INSPECT (읽기 전용·변경 없음) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # 1) 대시보드 — 로그인 유지 + 워드프레스 버전(우하단 #footer-thankyou / At a Glance)
    await page.goto(WP_ADMIN_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2
    ver = await page.evaluate(
        "() => { const f=document.querySelector('#footer-upgrade'); return f? f.innerText.trim() : (window.tinymce? 'tinymce-present':''); }"
    )
    print(f"[INFO] 워드프레스 버전 영역: {ver or '(미검출)'}")
    await page.screenshot(path=str(INSPECT_DIR / "wp_inspect_dashboard.png"))

    # 2) 테마
    await page.goto(THEMES_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(1500)
    active_theme = await page.evaluate(
        "() => { const a=document.querySelector('.theme.active .theme-name'); return a? a.innerText.trim():''; }"
    )
    print(f"[INFO] 활성 테마: {active_theme or '(미검출)'}")

    # 3) 플러그인 (페이지빌더·다국어 탐지)
    await page.goto(PLUGINS_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(1500)
    plugins = await page.evaluate(
        "() => Array.from(document.querySelectorAll('tr.active .plugin-title strong, tr[data-plugin].active .plugin-title strong')).map(e=>e.innerText.trim())"
    )
    print(f"[INFO] 활성 플러그인 {len(plugins)}개:")
    for pl in plugins:
        print(f"        · {pl}")

    # 4) 페이지 목록 (제목·ID·편집링크)
    await page.goto(PAGES_LIST_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(1500)
    pages = await page.evaluate(
        """() => Array.from(document.querySelectorAll('#the-list tr')).map(tr => {
            const a = tr.querySelector('a.row-title');
            const id = (tr.id||'').replace('post-','');
            return a ? {id, title: a.innerText.trim(), href: a.href} : null;
        }).filter(Boolean)"""
    )
    print(f"[INFO] 페이지 {len(pages)}개:")
    for pg in pages:
        print(f"        · [{pg['id']}] {pg['title']}")
    await page.screenshot(path=str(INSPECT_DIR / "wp_inspect_pages.png"))

    # 5) 결과 저장 (설계 입력용)
    import json
    out = {
        "wp_version_hint": ver,
        "active_theme": active_theme,
        "active_plugins": plugins,
        "pages": pages,
    }
    (INSPECT_DIR / "wp_inspect.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[INFO] 실측 결과 저장: {INSPECT_DIR / 'wp_inspect.json'}")
    print(f"[INFO] 스크린샷: wp_inspect_dashboard.png / wp_inspect_pages.png")
    await ctx.close()
    await p.stop()
    print("[INFO] === INSPECT 완료 (변경 없음) ===")
    return 0


NEW_PAGE_URL = "http://wellperion.com/wp/wp-admin/post-new.php?post_type=page"
INQUIRY_BLOCK_FILE = ROOT / "3. 웰페리온 가이드" / "cmo" / "survey" / "wp_inquiry_block.html"
INQUIRY_BLOCK_FILE_EN = ROOT / "3. 웰페리온 가이드" / "cmo" / "survey" / "wp_inquiry_block_en.html"
# 영문 자체 Survey 폼(구글폼 대체 컷오버, 배9674 시모 2026-07-22). draft-inquiry-en 은 이 파일을,
# rollback(draft-inquiry-en 기본)은 위 wp_inquiry_block_en.html(구글폼)을 주입 → 되돌리기 1스텝.
INQUIRY_FORM_FILE_EN = ROOT / "3. 웰페리온 가이드" / "cmo" / "survey" / "wp_inquiry_form_en.html"
INQUIRY_PAGE_TITLE = "문의"
INQUIRY_PAGE_TITLE_EN = "Inquiry"
KO_INQUIRY_POST_ID = "8394"  # 한국어 문의 페이지 고정 ID


def _wrap_vc_raw_html(html: str) -> str:
    """WPBakery [vc_raw_html] 형식으로 인코딩.
    렌더 시 WPBakery는 rawurldecode(base64_decode(content)) 순으로 푼다 →
    인코딩은 그 역순: base64_encode(rawurlencode(html)). (인라인 스타일 보존)"""
    import base64
    import urllib.parse
    enc = urllib.parse.quote(html, safe="")           # rawurlencode
    b64 = base64.b64encode(enc.encode("ascii")).decode("ascii")  # base64
    return f"[vc_raw_html]{b64}[/vc_raw_html]"


async def run_draft_inquiry(post_id_arg: "str | None" = None) -> int:
    """문의 페이지를 '비공개 초안'으로 생성/갱신 — 발행 안 함. GM 미리보기 검수용.
    본문 = wp_inquiry_block.html (4종 문의 폼 버튼)을 [vc_raw_html]로 주입.
    post_id_arg 지정 시 해당 페이지를 갱신(중복 생성 방지)."""
    async_playwright = _import_playwright()
    print("[INFO] === 워드프레스 문의 페이지 — 비공개 초안 생성/갱신 (발행 안 함) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    if not INQUIRY_BLOCK_FILE.exists():
        print(f"[ERROR] 문의 블록 HTML 부재: {INQUIRY_BLOCK_FILE}")
        return 4
    raw_html = INQUIRY_BLOCK_FILE.read_text(encoding="utf-8")
    html = _wrap_vc_raw_html(raw_html)  # WPBakery raw_html — sanitize 회피
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    target = (f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko"
              if post_id_arg else NEW_PAGE_URL)
    print(f"[INFO] 대상: {'갱신 post='+post_id_arg if post_id_arg else '신규 페이지'}")
    await page.goto(target, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    # 편집기 구조 감지
    probe = await page.evaluate(
        """() => ({
            title_classic: !!document.querySelector('#title'),
            title_gutenberg: !!document.querySelector('.editor-post-title__input, #post-title-0'),
            content_textarea: !!document.querySelector('#content'),
            text_tab: !!document.querySelector('#content-html'),
            wpbakery: !!document.querySelector('#wpb_visual_composer, .wpb_switch-to-composer, #wpb_switch'),
            save_draft_btn: !!document.querySelector('#save-post'),
        })"""
    )
    print(f"[INFO] 편집기 감지: {probe}")
    await page.screenshot(path=str(INSPECT_DIR / "wp_newpage_editor.png"))

    if not probe.get("title_classic") or not probe.get("content_textarea"):
        print("[ERROR] 고전(Classic) 편집기 구조 미검출 — 수동 확인 필요. 스크린샷: wp_newpage_editor.png")
        await ctx.close(); await p.stop(); return 5

    # 제목 입력 (신규일 때만 — 갱신 시 기존 제목 유지)
    cur_title = await page.evaluate("() => (document.querySelector('#title')||{}).value || ''")
    if not cur_title.strip():
        await page.fill("#title", INQUIRY_PAGE_TITLE)
        await page.wait_for_timeout(500)

    # Text(HTML) 모드 전환 후 본문 주입
    if probe.get("text_tab"):
        await page.click("#content-html")
        await page.wait_for_timeout(800)
    # textarea에 직접 세팅 + input 이벤트 (WP 제출 시 #content.value 사용)
    await page.evaluate(
        """(html) => { const ta = document.querySelector('#content');
            ta.value = html; ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true})); }""",
        html,
    )
    await page.wait_for_timeout(500)
    injected = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    ok_inject = "vc_raw_html" in injected and len(injected) > 200
    print(f"[INFO] 본문 주입 검증: {ok_inject} (길이 {len(injected)})")
    if not ok_inject:
        print("[ERROR] 본문 주입 실패 — 저장 중단. 스크린샷 확인 필요.")
        await ctx.close(); await p.stop(); return 6

    # 발행 상태면 업데이트(#publish)로 저장(발행 유지), 초안이면 임시저장(#save-post)
    pre_status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    is_published = ("공개" in pre_status) or ("발행" in pre_status) or ("published" in pre_status.lower())
    if is_published:
        print(f"[INFO] 이미 발행됨('{pre_status}') → 업데이트로 저장(발행 유지)")
        await page.click("#publish")
    else:
        await page.click("#save-post")
    # 저장 후 post.php?post=ID&action=edit 로 이동
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    cur = page.url
    import re as _re
    m = _re.search(r"[?&]post=(\d+)", cur)
    post_id = m.group(1) if m else None
    status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_inquiry_draft_saved.png"))
    print(f"[INFO] 저장 후 URL: {cur}")
    print(f"[INFO] 글 상태: {status or '(미검출)'}  /  page_id: {post_id or '(미검출)'}")
    if post_id:
        preview = f"http://wellperion.com/wp/?page_id={post_id}&preview=true"
        edit = f"http://wellperion.com/wp/wp-admin/post.php?post={post_id}&action=edit"
        print("[INFO] === GM 검수 링크 ===")
        print(f"        미리보기: {preview}")
        print(f"        편집화면: {edit}")
    print("[INFO] (※ 초안 상태 — 외부에 공개되지 않음. 발행은 GM 확인 후 별도 진행)")
    await ctx.close()
    await p.stop()
    print("[INFO] === 초안 생성 완료 (발행 안 함) ===")
    return 0 if post_id else 7


async def run_publish_inquiry(post_id_arg: str, slug: str = "inquiry") -> int:
    """초안 페이지를 슬러그 설정 후 '공개' 발행. (되돌리기: 편집화면에서 다시 임시글 전환 가능)"""
    async_playwright = _import_playwright()
    print(f"[INFO] === 워드프레스 문의 페이지 발행 (post={post_id_arg}, slug={slug}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    # 슬러그 설정 (퍼머링크 편집)
    try:
        if await page.query_selector("#edit-slug-buttons button.edit-slug"):
            await page.click("#edit-slug-buttons button.edit-slug")
            await page.wait_for_timeout(600)
            await page.fill("#new-post-slug", slug)
            await page.click("#edit-slug-buttons button.save")
            await page.wait_for_timeout(1200)
            print(f"[INFO] 슬러그 설정: {slug}")
    except Exception as e:
        print(f"[WARN] 슬러그 설정 경고(무시): {e}")

    # 발행 — #publish 버튼 (초안에서는 '공개')
    await page.click("#publish")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    status = await page.evaluate("() => (document.querySelector('#post-status-display')||{}).innerText || ''")
    permalink = await page.evaluate(
        "() => { const a=document.querySelector('#sample-permalink a, #sample-permalink'); return a? (a.href||a.innerText):''; }"
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_inquiry_published.png"))
    print(f"[INFO] 글 상태: {status or '(미검출)'}")
    print(f"[INFO] 공개 URL: {permalink or '(미검출)'}")
    await ctx.close(); await p.stop()
    published = "공개" in status or "published" in status.lower() or "발행" in status
    print(f"[INFO] === 발행 {'완료' if published else '확인 필요'} ===")
    return 0 if published else 8


async def run_wpml_create_en_translation() -> int:
    """WPML "+번역 추가" 자동 시도: 한국어 문의 페이지(8394) 편집화면에서
    WPML 메타박스의 영어 '+' 아이콘을 클릭해 영어 번역 페이지 생성.
    성공 시 생성된 영어 post_id를 출력. 실패 시 GM 수동 절차 안내."""
    async_playwright = _import_playwright()
    print("[INFO] === WPML 영어 번역 페이지 자동 생성 시도 (post=8394) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # 한국어 문의 편집화면 진입
    edit_url = f"http://wellperion.com/wp/wp-admin/post.php?post={KO_INQUIRY_POST_ID}&action=edit&lang=ko"
    await page.goto(edit_url, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(3000)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    await page.screenshot(path=str(INSPECT_DIR / "wpml_ko_edit_before.png"))

    # WPML 언어 메타박스에서 영어 '+' 아이콘 탐색
    # WPML은 .icl_lang_duplicate_links / .add_icl_post_link / a[href*="lang=en"] 등 다양한 셀렉터 사용
    wpml_probe = await page.evaluate("""() => {
        // '+' 번역 추가 링크 후보들
        const selectors = [
            'a.icl_post_link[data-lang="en"]',
            'a.add_icl_post_link',
            '.wpml-langmeta a[data-lang="en"]',
            '#icl_post_language_metabox a[data-lang="en"]',
            'a[href*="new_lang=en"]',
            'a[href*="lang=en"][href*="trid"]',
            '.wpml-translation-options a',
        ];
        for (const sel of selectors) {
            const els = document.querySelectorAll(sel);
            if (els.length) return {found: sel, count: els.length, href: els[0].href || ''};
        }
        // 전체 WPML 영역 HTML 덤프 (진단용)
        const box = document.querySelector('#icl_post_language_metabox, .wpml-post-language-metabox, #wpml-post-status-language');
        return {found: null, html: box ? box.innerHTML.substring(0,2000) : 'no-metabox'};
    }""")
    print(f"[INFO] WPML 메타박스 탐색: {wpml_probe}")
    await page.screenshot(path=str(INSPECT_DIR / "wpml_ko_edit_meta.png"))

    en_link = None
    if wpml_probe.get("found"):
        sel = wpml_probe["found"]
        try:
            en_link = await page.query_selector(sel)
        except Exception:
            pass

    # href 직접 추출 후 page.goto() 사용 (숨김 요소 클릭 실패 우회)
    en_href = None
    if wpml_probe.get("found") and wpml_probe.get("href"):
        en_href = wpml_probe["href"]
    if not en_href:
        # href에 new_lang=en 또는 lang=en+trid 포함 링크 전체 스캔
        hrefs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a')).map(a=>({text:a.innerText.trim(), href:a.href}))
                .filter(o=> o.href && (o.href.includes('new_lang=en') || (o.href.includes('lang=en') && o.href.includes('trid'))));
        }""")
        print(f"[INFO] href 스캔 결과: {hrefs}")
        if hrefs:
            en_href = hrefs[0]["href"]
    if en_href:
        print(f"[INFO] WPML 영어 '+' 링크: {en_href}")
        await page.goto(en_href, wait_until="domcontentloaded", timeout=40_000)
        await page.wait_for_timeout(3000)
    else:
        print("[WARN] WPML '+번역 추가' 링크 자동 탐색 실패.")
        print()
        print("=" * 60)
        print("  GM 수동 조치 필요 (1회)")
        print("=" * 60)
        print(f"  1. 브라우저에서 아래 URL 접속:")
        print(f"     {edit_url}")
        print(f"  2. 편집 화면 우측 'WPML Language' 메타박스 확인")
        print(f"  3. 영어(English) 행 옆 '+' 아이콘 클릭")
        print(f"  4. 제목: 'Inquiry', 슬러그: 'inquiry' 입력")
        print(f"  5. 임시글(Draft)로 저장 → URL의 post=XXXX 값을 메모")
        print(f"  6. 메모한 ID로: python scripts\\wordpress_admin_playwright.py")
        print(f"     --mode draft-inquiry-en --post-id <EN_ID>")
        print("=" * 60)
        await ctx.close(); await p.stop(); return 20

    # 현재 페이지가 영어 편집화면인지 확인
    cur_url = page.url
    print(f"[INFO] 이동 후 URL: {cur_url}")
    await page.screenshot(path=str(INSPECT_DIR / "wpml_en_edit_opened.png"))

    # WPML Translation Editor로 열렸으면 "Edit in WordPress" 클릭
    if "wpml-translation-editor" in cur_url or "WPML" in await page.title():
        wp_edit_btn = await page.query_selector("a.wpml-edit-in-wordpress, a[href*='action=edit']")
        if wp_edit_btn:
            await wp_edit_btn.click()
            await page.wait_for_timeout(3000)
            cur_url = page.url
            print(f"[INFO] Classic 편집기 전환 후 URL: {cur_url}")

    import re as _re
    m = _re.search(r"[?&]post=(\d+)", cur_url)
    en_post_id = m.group(1) if m else None

    # post-new.php 상태 = 아직 저장 전 → 제목 입력 후 임시저장해 post_id 획득
    if not en_post_id and "post-new.php" in cur_url:
        print("[INFO] 신규 페이지 편집화면 — 제목 입력 후 임시저장으로 post_id 획득")
        probe = await page.evaluate(
            "() => ({title: !!document.querySelector('#title'), save_draft: !!document.querySelector('#save-post')})"
        )
        print(f"[INFO] 편집기 감지: {probe}")
        if probe.get("title"):
            await page.fill("#title", INQUIRY_PAGE_TITLE_EN)
            await page.wait_for_timeout(500)
        if probe.get("save_draft"):
            await page.click("#save-post")
            try:
                await page.wait_for_url("**/post.php?post=*", timeout=30_000)
            except Exception:
                await page.wait_for_timeout(4000)
            await page.wait_for_timeout(1500)
            cur_url = page.url
            print(f"[INFO] 임시저장 후 URL: {cur_url}")
            m = _re.search(r"[?&]post=(\d+)", cur_url)
            en_post_id = m.group(1) if m else None
        await page.screenshot(path=str(INSPECT_DIR / "wpml_en_draft_saved.png"))

    if en_post_id and en_post_id != KO_INQUIRY_POST_ID:
        print(f"[INFO] 영어 페이지 ID 확인: {en_post_id}")
        print(f"[INFO] === WPML 영어 번역 페이지 자동 생성 성공 — translation pair 자동 등록됨 ===")
        print(f"[INFO] 다음 단계: python scripts\\wordpress_admin_playwright.py --mode draft-inquiry-en --post-id {en_post_id}")
    else:
        print(f"[WARN] 영어 post_id 추출 실패 (cur_url={cur_url}). URL에서 post= 값을 수동 확인.")

    await ctx.close(); await p.stop()
    return 0 if (en_post_id and en_post_id != KO_INQUIRY_POST_ID) else 21


async def run_draft_inquiry_en(post_id_arg: str, block_file: "Path | None" = None) -> int:
    """영어 문의 페이지 본문 갱신(발행 상태면 발행 유지 = 즉시 라이브 업데이트).
    block_file 미지정 = wp_inquiry_block_en.html(구글폼, rollback 자산) 주입.
    block_file = wp_inquiry_form_en.html(자체폼) → 컷오버. 둘 다 [vc_raw_html]·&lang=en 컨텍스트."""
    block_file = block_file or INQUIRY_BLOCK_FILE_EN
    async_playwright = _import_playwright()
    print(f"[INFO] === 워드프레스 영어 문의 페이지 본문 주입 (post={post_id_arg}, block={block_file.name}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    if not block_file.exists():
        print(f"[ERROR] 영어 문의 블록 HTML 부재: {block_file}")
        return 4
    raw_html = block_file.read_text(encoding="utf-8")
    html = _wrap_vc_raw_html(raw_html)
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    target = f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=en"
    print(f"[INFO] 대상: post={post_id_arg} (lang=en)")
    await page.goto(target, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    probe = await page.evaluate(
        """() => ({
            title_classic: !!document.querySelector('#title'),
            content_textarea: !!document.querySelector('#content'),
            text_tab: !!document.querySelector('#content-html'),
            save_draft_btn: !!document.querySelector('#save-post'),
        })"""
    )
    print(f"[INFO] 편집기 감지: {probe}")
    await page.screenshot(path=str(INSPECT_DIR / "wp_en_inquiry_editor.png"))

    if not probe.get("title_classic") or not probe.get("content_textarea"):
        print("[ERROR] Classic 편집기 미검출 — 스크린샷: wp_en_inquiry_editor.png")
        await ctx.close(); await p.stop(); return 5

    # 제목 설정 (비어있으면)
    cur_title = await page.evaluate("() => (document.querySelector('#title')||{}).value || ''")
    if not cur_title.strip():
        await page.fill("#title", INQUIRY_PAGE_TITLE_EN)
        await page.wait_for_timeout(500)

    # Text 모드 전환 후 본문 주입
    if probe.get("text_tab"):
        await page.click("#content-html")
        await page.wait_for_timeout(800)
    await page.evaluate(
        """(html) => { const ta = document.querySelector('#content');
            ta.value = html; ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true})); }""",
        html,
    )
    await page.wait_for_timeout(500)
    injected = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    ok_inject = "vc_raw_html" in injected and len(injected) > 200
    print(f"[INFO] 본문 주입 검증: {ok_inject} (길이 {len(injected)})")
    if not ok_inject:
        print("[ERROR] 본문 주입 실패 — 저장 중단.")
        await ctx.close(); await p.stop(); return 6

    # 발행 상태면 업데이트(발행 유지), 초안이면 임시저장
    pre_status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    is_published = ("공개" in pre_status) or ("발행" in pre_status) or ("published" in pre_status.lower())
    if is_published:
        print(f"[INFO] 이미 발행됨('{pre_status}') → 업데이트로 저장(발행 유지)")
        await page.click("#publish")
    else:
        await page.click("#save-post")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    cur = page.url
    import re as _re
    m = _re.search(r"[?&]post=(\d+)", cur)
    saved_post_id = m.group(1) if m else None
    status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_en_inquiry_draft_saved.png"))
    print(f"[INFO] 저장 후 URL: {cur}")
    print(f"[INFO] 글 상태: {status or '(미검출)'}  /  page_id: {saved_post_id or '(미검출)'}")
    if saved_post_id:
        preview = f"http://wellperion.com/wp/?page_id={saved_post_id}&preview=true"
        edit = f"http://wellperion.com/wp/wp-admin/post.php?post={saved_post_id}&action=edit&lang=en"
        print("[INFO] === GM 검수 링크 ===")
        print(f"        미리보기: {preview}")
        print(f"        편집화면: {edit}")
        print(f"[INFO] 발행 명령: python scripts\\wordpress_admin_playwright.py --mode publish-inquiry-en --post-id {saved_post_id}")
    print("[INFO] (※ 초안 상태 — 외부 미공개. 발행은 GM 확인 후 별도 진행)")
    await ctx.close(); await p.stop()
    print("[INFO] === 영어 초안 생성 완료 (발행 안 함) ===")
    return 0 if saved_post_id else 7


async def run_publish_inquiry_en(post_id_arg: str, slug: str = "inquiry") -> int:
    """영어 문의 초안을 슬러그 'inquiry' 설정 후 공개 발행.
    WPML /en/ prefix 적용 → 최종 URL: /en/inquiry/"""
    async_playwright = _import_playwright()
    print(f"[INFO] === 워드프레스 영어 문의 페이지 발행 (post={post_id_arg}, slug={slug}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=en",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    # 슬러그 설정
    try:
        if await page.query_selector("#edit-slug-buttons button.edit-slug"):
            await page.click("#edit-slug-buttons button.edit-slug")
            await page.wait_for_timeout(600)
            await page.fill("#new-post-slug", slug)
            await page.click("#edit-slug-buttons button.save")
            await page.wait_for_timeout(1200)
            print(f"[INFO] 슬러그 설정: {slug}")
    except Exception as e:
        print(f"[WARN] 슬러그 설정 경고(무시): {e}")

    await page.click("#publish")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    status = await page.evaluate("() => (document.querySelector('#post-status-display')||{}).innerText || ''")
    permalink = await page.evaluate(
        "() => { const a=document.querySelector('#sample-permalink a, #sample-permalink'); return a? (a.href||a.innerText):''; }"
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_en_inquiry_published.png"))
    print(f"[INFO] 글 상태: {status or '(미검출)'}")
    print(f"[INFO] 공개 URL: {permalink or '(미검출)'}")
    await ctx.close(); await p.stop()
    published = "공개" in status or "published" in status.lower() or "발행" in status
    print(f"[INFO] === 발행 {'완료' if published else '확인 필요'} ===")
    return 0 if published else 8


KOREAN_MENU_ID = "59"  # '한국어 메인 (Top Navigation Menu)' — 프론트 상단 메뉴


async def run_add_menu(post_id_arg: str, menu_id: str = KOREAN_MENU_ID) -> int:
    """한글 메인 메뉴(기본 id=59) '맨 끝'에 해당 페이지를 추가. (Add to Menu = 끝에 추가)"""
    async_playwright = _import_playwright()
    print(f"[INFO] === 상단 메뉴에 문의 페이지 추가 (post={post_id_arg}, menu={menu_id}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    # 한글 메인 메뉴를 직접 지정해 편집
    await page.goto(f"http://wellperion.com/wp/wp-admin/nav-menus.php?action=edit&menu={menu_id}&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    before = await page.evaluate("() => document.querySelectorAll('#menu-to-edit li.menu-item').length")
    menu_name = await page.evaluate("() => (document.querySelector('#menu-name')||{}).value || ''")
    print(f"[INFO] 편집 중 메뉴: '{menu_name}' / 현재 항목 {before}개")
    await page.screenshot(path=str(INSPECT_DIR / "wp_menu_before.png"))
    if "한국" not in menu_name and "Top" not in menu_name:
        print(f"[WARN] 한글 메인 메뉴가 아닐 수 있음('{menu_name}') — 계속 진행하되 결과 확인 필요.")

    # 이미 추가돼 있는지 확인(중복 방지)
    already = await page.evaluate(
        "(pid)=>[...document.querySelectorAll('#menu-to-edit input.menu-item-data-object-id')].some(i=>i.value===String(pid))",
        post_id_arg,
    )
    if already:
        print("[INFO] 이미 메뉴에 문의 페이지가 있음 — 중복 추가 안 함.")
        await ctx.close(); await p.stop(); return 0

    # Pages 메타박스 '검색' 탭 클릭 후 검색
    try:
        tab = await page.query_selector("a[href='#tabs-panel-posttype-page-search']")
        if tab:
            await tab.click()
            await page.wait_for_timeout(600)
        await page.fill("#quick-search-posttype-page", INQUIRY_PAGE_TITLE)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)
    except Exception as e:
        print(f"[WARN] 검색 경고(무시): {e}")

    # 검색 결과/전체에서 post-id 체크박스 선택
    checked = await page.evaluate(
        """(pid) => {
            let target=null;
            document.querySelectorAll('#add-page input[type=checkbox]').forEach(cb=>{
                if((cb.value||'')===String(pid)) target=cb;
            });
            if(target){ target.checked=true; target.dispatchEvent(new Event('change',{bubbles:true})); return true; }
            return false;
        }""",
        post_id_arg,
    )
    print(f"[INFO] 문의 페이지 체크박스 선택: {checked}")
    if not checked:
        await page.screenshot(path=str(INSPECT_DIR / "wp_menu_searchfail.png"))
        print("[ERROR] 페이지 체크박스 미발견 — 스크린샷(wp_menu_searchfail.png) 확인.")
        await ctx.close(); await p.stop(); return 9

    # 'Add to Menu' (페이지 post_type 전용 버튼)
    add_btn = await page.query_selector("#submit-posttype-page, .submit-add-to-menu")
    if add_btn:
        await add_btn.click()
        await page.wait_for_timeout(3000)
    after = await page.evaluate("() => document.querySelectorAll('#menu-to-edit li.menu-item').length")
    print(f"[INFO] 추가 후 항목 {after}개 (이전 {before})")
    if after <= before:
        await page.screenshot(path=str(INSPECT_DIR / "wp_menu_addfail.png"))
        print("[ERROR] 메뉴 항목이 늘지 않음 — 추가 실패. 스크린샷 확인.")
        await ctx.close(); await p.stop(); return 10

    # 메뉴 저장
    save_btn = await page.query_selector("#save_menu_footer, #save_menu_header")
    if save_btn:
        await save_btn.click()
        await page.wait_for_timeout(3500)
    await page.screenshot(path=str(INSPECT_DIR / "wp_menu_after.png"))
    print("[INFO] === 메뉴 저장 완료 (맨 끝에 추가) ===")
    await ctx.close(); await p.stop()
    return 0


async def run_remove_menu(object_ids: "list[str]", menu_id: str = KOREAN_MENU_ID,
                          disable_auto_add: bool = True) -> int:
    """전역 상단 메뉴(기본 id=59 한글메인)에서 지정 페이지(object-id)에 연결된 메뉴 항목을 제거.
    습득분실물/자체Survey 페이지가 테마 '자동 페이지 메뉴 추가'로 전역 nav에 편입된 것을 근본 정리.
    가드: object-id 로 정확 매칭된 항목만 제거 · 제거 수 == 매칭 수 검증 · 스크린샷 · 저장 전후 카운트 대조.
    disable_auto_add: '새 최상위 페이지 자동 추가' 체크박스가 켜져 있으면 끔(재발 방지 근본).
    되돌리기: Appearance→Menus 에서 다시 Add 하면 복원(가역)."""
    async_playwright = _import_playwright()
    print(f"[INFO] === 전역 메뉴에서 페이지 항목 제거 (menu={menu_id}, object_ids={object_ids}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/nav-menus.php?action=edit&menu={menu_id}&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    menu_name = await page.evaluate("() => (document.querySelector('#menu-name')||{}).value || ''")
    before = await page.evaluate("() => document.querySelectorAll('#menu-to-edit li.menu-item').length")
    print(f"[INFO] 편집 중 메뉴: '{menu_name}' / 현재 항목 {before}개")
    await page.screenshot(path=str(INSPECT_DIR / "wp_menu_remove_before.png"))
    if "한국" not in menu_name and "Top" not in menu_name:
        print(f"[WARN] 한글 메인 메뉴가 아닐 수 있음('{menu_name}') — 계속 진행하되 결과 확인 필요.")

    # object-id 로 매칭되는 메뉴 항목의 '제거(item-delete)' 링크를 클릭 (매칭 수 반환)
    matched = await page.evaluate(
        """(ids) => {
            const want = ids.map(String);
            let hits = [];
            document.querySelectorAll('#menu-to-edit li.menu-item').forEach(li => {
                const oid = li.querySelector('input.menu-item-data-object-id');
                if (oid && want.includes(String(oid.value))) {
                    const title = (li.querySelector('.menu-item-title')||{}).textContent || '';
                    const del = li.querySelector('a.item-delete');
                    hits.push({oid: oid.value, title: title.trim(), hasDelete: !!del});
                }
            });
            return hits;
        }""",
        object_ids,
    )
    print(f"[INFO] object-id 매칭 항목 {len(matched)}개: {matched}")
    if len(matched) == 0:
        print("[INFO] 매칭 항목 0 — 이미 제거됐거나 이 메뉴엔 없음. 저장 없이 종료(무손상).")
        await ctx.close(); await p.stop(); return 0

    # 실제 제거: 각 매칭 항목의 a.item-delete 클릭 (WP는 클릭 시 DOM에서 li 제거, 저장 시 확정)
    removed = await page.evaluate(
        """async (ids) => {
            const want = ids.map(String);
            let n = 0;
            const lis = Array.from(document.querySelectorAll('#menu-to-edit li.menu-item'));
            for (const li of lis) {
                const oid = li.querySelector('input.menu-item-data-object-id');
                if (oid && want.includes(String(oid.value))) {
                    const del = li.querySelector('a.item-delete');
                    if (del) { del.click(); n++; await new Promise(r=>setTimeout(r,400)); }
                }
            }
            return n;
        }""",
        object_ids,
    )
    await page.wait_for_timeout(1200)
    mid = await page.evaluate("() => document.querySelectorAll('#menu-to-edit li.menu-item').length")
    print(f"[INFO] 제거 클릭 {removed}건 → DOM 항목 {before}→{mid}")
    if mid != before - len(matched):
        await page.screenshot(path=str(INSPECT_DIR / "wp_menu_remove_mismatch.png"))
        print(f"[ABORT] 제거 후 카운트 불일치(기대 {before-len(matched)}, 실제 {mid}) — 저장 안 함(무손상).")
        await ctx.close(); await p.stop(); return 40

    # 재발 방지: '새 최상위 페이지 자동 추가' 체크 해제 (근본 원인)
    auto_state = "n/a"
    if disable_auto_add:
        auto_state = await page.evaluate(
            """() => { const c=document.querySelector('#auto-add-pages');
                if(!c) return 'no-checkbox';
                if(c.checked){ c.checked=false; c.dispatchEvent(new Event('change',{bubbles:true})); return 'unchecked'; }
                return 'already-off'; }"""
        )
        print(f"[INFO] '새 페이지 자동 메뉴 추가' 체크박스: {auto_state}")

    # 메뉴 저장
    save_btn = await page.query_selector("#save_menu_footer, #save_menu_header")
    if not save_btn:
        print("[ABORT] 저장 버튼 미검출 — 저장 안 함.")
        await ctx.close(); await p.stop(); return 41
    await save_btn.click()
    await page.wait_for_timeout(3500)
    after = await page.evaluate("() => document.querySelectorAll('#menu-to-edit li.menu-item').length")
    await page.screenshot(path=str(INSPECT_DIR / "wp_menu_remove_after.png"))
    print(f"[INFO] 저장 후 항목 {after}개 (제거 전 {before}, 매칭 {len(matched)})")
    ok = after == before - len(matched)
    print(f"[INFO] === 메뉴 항목 제거 {'완료' if ok else '확인 필요'} (auto-add: {auto_state}) ===")
    await ctx.close(); await p.stop()
    return 0 if ok else 42


async def run_swap_href(post_id_arg: str, find: str, repl: str) -> int:
    """외과적 치환: 지정 페이지 post_content에서 find→repl 단일 치환(count==1 가드).
    Classic 편집기 Text탭(#content)만 사용. 원본을 타임스탬프 백업 후, 정확히 1건일 때만 저장.
    나머지 본문(레이아웃·전체 버튼)은 일절 손대지 않음. 발행 상태 유지."""
    import datetime
    async_playwright = _import_playwright()
    print(f"[INFO] === 외과적 href 치환 (post={post_id_arg}) ===")
    print(f"[INFO] find: {find}")
    print(f"[INFO] repl: {repl}")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    probe = await page.evaluate(
        "() => ({classic: !!document.querySelector('#content'), text_tab: !!document.querySelector('#content-html')})"
    )
    if not probe.get("classic"):
        print("[ERROR] Classic 편집기 #content 미검출 — 중단(저장 안 함).")
        await ctx.close(); await p.stop(); return 5
    # Text(HTML) 탭 전환 — 백엔드 레이아웃이 길어 버튼이 뷰포트 밖일 수 있으므로
    # WP 네이티브 switchEditors API(JS)로 전환(클릭 액셔너빌리티 회피). 실패 시 force 클릭 폴백.
    switched = await page.evaluate(
        """() => { try {
            if (window.switchEditors && switchEditors.go) { switchEditors.go('content','html'); return 'api'; }
            const b=document.querySelector('#content-html'); if(b){ b.click(); return 'click'; }
            return 'none';
        } catch(e){ return 'err:'+e.message; } }"""
    )
    await page.wait_for_timeout(800)
    print(f"[INFO] Text탭 전환 방식: {switched}")
    if switched in ("none", "") or str(switched).startswith("err:"):
        try:
            await page.click("#content-html", force=True, timeout=8000)
            await page.wait_for_timeout(800)
        except Exception as e:
            print(f"[WARN] Text탭 클릭 폴백 경고: {e}")

    original = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    if not original or len(original) < 200:
        print(f"[ERROR] post_content 비정상(길이 {len(original)}) — 중단(저장 안 함).")
        await ctx.close(); await p.stop(); return 6

    # 원본 타임스탬프 백업 (필수 안전장치)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = INSPECT_DIR / f"home_page{post_id_arg}_content_backup_{ts}.txt"
    backup_path.write_text(original, encoding="utf-8")
    print(f"[INFO] 원본 백업: {backup_path} (길이 {len(original)})")

    # 단일 치환 가드: count != 1 이면 저장 말고 중단
    count = original.count(find)
    print(f"[INFO] find 출현 횟수: {count}")
    if count != 1:
        print(f"[ABORT] 치환 카운트 != 1 ({count}건) — 오인/중복 방지 위해 저장 안 함. 원본 무손상.")
        await page.screenshot(path=str(INSPECT_DIR / f"wp_swap_abort_{ts}.png"))
        await ctx.close(); await p.stop(); return 11
    repl_before = original.count(repl)  # 동일 URL이 이미 본문에 있을 수 있음(상대 검증용)
    print(f"[INFO] repl 사전 출현 횟수: {repl_before}")
    new_content = original.replace(find, repl)
    if new_content == original or new_content.count(repl) != repl_before + 1:
        print(f"[ABORT] 치환 후 repl 증가 != 1 (전 {repl_before} → 후 {new_content.count(repl)}) — 저장 안 함.")
        await ctx.close(); await p.stop(); return 12
    # 길이 변화는 (repl-find) 길이차 * 1 이어야 함 (그 외 변형 차단)
    expected_delta = len(repl) - len(find)
    if len(new_content) - len(original) != expected_delta:
        print(f"[ABORT] 길이 델타 불일치(기대 {expected_delta}, 실제 {len(new_content)-len(original)}) — 저장 안 함.")
        await ctx.close(); await p.stop(); return 13

    # TinyMCE(비주얼) 인스턴스가 살아 있으면 textarea를 재동기화해 우리 값을 덮어씀.
    # → 'content' 에디터를 detach 하여 #content textarea를 단일 진실원으로 만든 뒤 되쓰기.
    detached = await page.evaluate(
        """() => { try {
            if (window.tinymce && tinymce.get('content')) { tinymce.get('content').remove(); return 'removed'; }
            return 'no-tinymce';
        } catch(e){ return 'err:'+e.message; } }"""
    )
    await page.wait_for_timeout(400)
    print(f"[INFO] TinyMCE detach: {detached}")
    # textarea에 되쓰기 (WP 제출 시 #content.value 사용)
    await page.evaluate(
        """(html) => { const ta = document.querySelector('#content');
            ta.value = html; ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true})); }""",
        new_content,
    )
    await page.wait_for_timeout(500)
    verify = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    if verify.count(repl) != repl_before + 1 or find in verify:
        print(f"[ABORT] textarea 반영 검증 실패(repl {verify.count(repl)}건/기대 {repl_before+1}, find잔존 {find in verify}) — 저장 안 함.")
        await ctx.close(); await p.stop(); return 14
    print(f"[INFO] textarea 치환 반영 확인 (repl {verify.count(repl)}건, find 0건)")

    # 발행 상태 유지 → #publish(업데이트)로 저장
    pre_status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    print(f"[INFO] 저장 전 상태: {pre_status or '(미검출)'}")
    await page.click("#publish")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    saved = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    await page.screenshot(path=str(INSPECT_DIR / f"wp_swap_saved_{ts}.png"))
    print(f"[INFO] 저장 후 상태: {status or '(미검출)'}")
    print(f"[INFO] 저장 후 본문 내 find 잔존: {saved.count(find)}건 / repl: {saved.count(repl)}건(기대 {repl_before+1})")
    await ctx.close(); await p.stop()
    ok = saved.count(find) == 0 and saved.count(repl) == repl_before + 1
    print(f"[INFO] === 외과적 치환 {'완료' if ok else '확인 필요'} === (백업: {backup_path})")
    return 0 if ok else 15


RECEPTION_PAGE_TITLE = "종합접수처"
# ★ 근본구조 전환(2026-06-30): iframe('미리보기 창') 폐기 → 폼을 페이지 본문에 직접 인라인 주입.
#   문의 페이지(8394) wp_inquiry_block.html 직접주입과 완전히 동일한 방식.
#   주입 소스 = reception_block.html (폼·JS·토큰 단일 정본, .wlp-recept 스코프 적용).
#   ?loc 프리필은 폼 JS가 페이지 URL location.search 에서 직접 읽음(iframe 중계 JS 불필요).
RECEPTION_BLOCK_FILE = ROOT / "3. 웰페리온 가이드" / "coo" / "reception" / "reception_block.html"


async def run_draft_reception(post_id_arg: "str | None" = None) -> int:
    """종합접수처 페이지를 생성/갱신. VOC 모바일 폼을 페이지 본문에 직접 인라인 주입(iframe 폐기).
    주입 소스=reception_block.html. post_id 지정 시 기존 페이지 갱신. 발행 상태면 발행 유지."""
    async_playwright = _import_playwright()
    print("[INFO] === 워드프레스 종합접수처 페이지 — 비공개 초안 생성/갱신 (발행 안 함) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    if not RECEPTION_BLOCK_FILE.exists():
        print(f"[ERROR] 종합접수처 블록 HTML 부재: {RECEPTION_BLOCK_FILE}")
        return 4
    raw_html = RECEPTION_BLOCK_FILE.read_text(encoding="utf-8")
    html = _wrap_vc_raw_html(raw_html)   # 직접 인라인 주입(iframe 폐기)
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    target = (f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko"
              if post_id_arg else NEW_PAGE_URL)
    print(f"[INFO] 대상: {'갱신 post='+post_id_arg if post_id_arg else '신규 페이지'}")
    await page.goto(target, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    probe = await page.evaluate(
        """() => ({
            title_classic: !!document.querySelector('#title'),
            content_textarea: !!document.querySelector('#content'),
            text_tab: !!document.querySelector('#content-html'),
            save_draft_btn: !!document.querySelector('#save-post'),
        })"""
    )
    print(f"[INFO] 편집기 감지: {probe}")
    await page.screenshot(path=str(INSPECT_DIR / "wp_reception_editor.png"))

    if not probe.get("title_classic") or not probe.get("content_textarea"):
        print("[ERROR] Classic 편집기 미검출 — 스크린샷: wp_reception_editor.png")
        await ctx.close(); await p.stop(); return 5

    cur_title = await page.evaluate("() => (document.querySelector('#title')||{}).value || ''")
    if not cur_title.strip():
        await page.fill("#title", RECEPTION_PAGE_TITLE)
        await page.wait_for_timeout(500)

    if probe.get("text_tab"):
        await page.click("#content-html")
        await page.wait_for_timeout(800)
    await page.evaluate(
        """(html) => { const ta = document.querySelector('#content');
            ta.value = html; ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true})); }""",
        html,
    )
    await page.wait_for_timeout(500)
    injected = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    ok_inject = "vc_raw_html" in injected and len(injected) > 100
    print(f"[INFO] 본문 주입 검증: {ok_inject} (길이 {len(injected)})")
    if not ok_inject:
        print("[ERROR] 본문 주입 실패 — 저장 중단.")
        await ctx.close(); await p.stop(); return 6

    pre_status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    is_published = ("공개" in pre_status) or ("발행" in pre_status) or ("published" in pre_status.lower())
    if is_published:
        print(f"[INFO] 이미 발행됨('{pre_status}') → 업데이트로 저장(발행 유지)")
        await page.click("#publish")
    else:
        await page.click("#save-post")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    cur = page.url
    import re as _re
    m = _re.search(r"[?&]post=(\d+)", cur)
    post_id = m.group(1) if m else None
    status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_reception_draft_saved.png"))
    print(f"[INFO] 저장 후 URL: {cur}")
    print(f"[INFO] 글 상태: {status or '(미검출)'}  /  page_id: {post_id or '(미검출)'}")
    if post_id:
        preview = f"http://wellperion.com/wp/?page_id={post_id}&preview=true"
        edit = f"http://wellperion.com/wp/wp-admin/post.php?post={post_id}&action=edit"
        print("[INFO] === GM 검수 링크 ===")
        print(f"        미리보기: {preview}")
        print(f"        편집화면: {edit}")
        print(f"[INFO] 발행 명령: python scripts\\wordpress_admin_playwright.py --mode publish-reception --post-id {post_id}")
    print("[INFO] (※ 초안 상태 — 외부에 공개되지 않음. 발행은 GM 확인 후 별도 진행)")
    await ctx.close(); await p.stop()
    print("[INFO] === 종합접수처 초안 생성 완료 (발행 안 함) ===")
    return 0 if post_id else 7


async def run_publish_reception(post_id_arg: str, slug: str = "reception") -> int:
    """종합접수처 초안을 슬러그 'reception' 설정 후 공개 발행. 메뉴 미노출 유지."""
    async_playwright = _import_playwright()
    print(f"[INFO] === 워드프레스 종합접수처 페이지 발행 (post={post_id_arg}, slug={slug}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    try:
        if await page.query_selector("#edit-slug-buttons button.edit-slug"):
            await page.click("#edit-slug-buttons button.edit-slug")
            await page.wait_for_timeout(600)
            await page.fill("#new-post-slug", slug)
            await page.click("#edit-slug-buttons button.save")
            await page.wait_for_timeout(1200)
            print(f"[INFO] 슬러그 설정: {slug}")
    except Exception as e:
        print(f"[WARN] 슬러그 설정 경고(무시): {e}")

    await page.click("#publish")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    status = await page.evaluate("() => (document.querySelector('#post-status-display')||{}).innerText || ''")
    permalink = await page.evaluate(
        "() => { const a=document.querySelector('#sample-permalink a, #sample-permalink'); return a? (a.href||a.innerText):''; }"
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_reception_published.png"))
    print(f"[INFO] 글 상태: {status or '(미검출)'}")
    print(f"[INFO] 공개 URL: {permalink or '(미검출)'}")
    await ctx.close(); await p.stop()
    published = "공개" in status or "published" in status.lower() or "발행" in status
    print(f"[INFO] === 발행 {'완료' if published else '확인 필요'} ===")
    return 0 if published else 8


RECEPTION_POST_ID = "8434"  # 종합접수처 라이브 페이지 고정 ID (/ko/reception/)


def _decode_vc_raw_html(b64: str) -> str:
    """[vc_raw_html] payload 디코드: base64_decode → rawurldecode (인코딩의 정확한 역순)."""
    import base64
    import urllib.parse
    dec = base64.b64decode(b64.strip().encode("ascii")).decode("ascii")
    return urllib.parse.unquote(dec)


async def run_swap_reception_text(find: str, repl: str,
                                  post_id_arg: str = RECEPTION_POST_ID,
                                  dry_run: bool = False) -> int:
    """종합접수처 페이지 본문의 [vc_raw_html] base64 블록을 '디코드'해 find→repl **단일 문자열만** 교체.
    폼 동작·다른 마크업 무손상: 디코드된 HTML에서 find 가 정확히 1건일 때만 교체하고 재인코드해 되쓴다.
    - #content 는 base64 blob 이라 plain swap 불가 → 반드시 디코드 경로 사용.
    - 원본 #content 를 타임스탬프 백업. count!=1 이면 저장 없이 중단(라이브 무손상).
    - dry_run=True: 디코드·카운트만 보고하고 저장하지 않음(사전 검증용)."""
    import base64
    import urllib.parse
    import datetime
    import re as _re
    async_playwright = _import_playwright()
    print(f"[INFO] === 종합접수처 라벨 문자열 외과적 교체 (post={post_id_arg}, dry_run={dry_run}) ===")
    print(f"[INFO] find: {find}")
    print(f"[INFO] repl: {repl}")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    probe = await page.evaluate(
        "() => ({classic: !!document.querySelector('#content'), text_tab: !!document.querySelector('#content-html')})"
    )
    if not probe.get("classic"):
        print("[ERROR] Classic 편집기 #content 미검출 — 중단(저장 안 함).")
        await ctx.close(); await p.stop(); return 5
    # Text(HTML) 탭으로 전환 — WP 네이티브 switchEditors API 우선(액셔너빌리티 회피)
    switched = await page.evaluate(
        """() => { try {
            if (window.switchEditors && switchEditors.go) { switchEditors.go('content','html'); return 'api'; }
            const b=document.querySelector('#content-html'); if(b){ b.click(); return 'click'; }
            return 'none';
        } catch(e){ return 'err:'+e.message; } }"""
    )
    await page.wait_for_timeout(800)
    print(f"[INFO] Text탭 전환 방식: {switched}")
    if switched in ("none", "") or str(switched).startswith("err:"):
        try:
            await page.click("#content-html", force=True, timeout=8000)
            await page.wait_for_timeout(800)
        except Exception as e:
            print(f"[WARN] Text탭 클릭 폴백 경고: {e}")

    raw = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    if not raw or len(raw) < 200:
        print(f"[ERROR] post_content 비정상(길이 {len(raw)}) — 중단(저장 안 함).")
        await ctx.close(); await p.stop(); return 6

    # 원본 백업 (필수 안전장치)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = INSPECT_DIR / f"reception_page{post_id_arg}_content_backup_{ts}.txt"
    backup_path.write_text(raw, encoding="utf-8")
    print(f"[INFO] 원본 백업: {backup_path} (길이 {len(raw)})")

    # [vc_raw_html] 블록 전수 탐색 — 디코드해 find 총 출현 1건인 블록을 특정
    blocks = list(_re.finditer(r"\[vc_raw_html\](.*?)\[/vc_raw_html\]", raw, _re.S))
    print(f"[INFO] [vc_raw_html] 블록 수: {len(blocks)}")
    if not blocks:
        print("[ABORT] [vc_raw_html] 블록 미검출 — 예상 구조 아님. 저장 안 함(라이브 무손상).")
        await ctx.close(); await p.stop(); return 30

    target_idx, decoded_target, total_find = None, None, 0
    for i, b in enumerate(blocks):
        try:
            dec = _decode_vc_raw_html(b.group(1))
        except Exception as e:
            print(f"[WARN] 블록 {i} 디코드 실패(무시): {e}")
            continue
        c = dec.count(find)
        total_find += c
        if c > 0:
            target_idx, decoded_target = i, dec
    print(f"[INFO] find 총 출현(디코드 기준): {total_find}건")
    if total_find != 1:
        print(f"[ABORT] find 출현 != 1 ({total_find}건) — 오인/중복/이미교체 방지 위해 저장 안 함. 라이브 무손상.")
        # 참고: 이미 repl 이 라이브에 있으면(선반영) total_find==0 으로 여기서 안전 종료됨.
        await page.screenshot(path=str(INSPECT_DIR / f"wp_recept_swap_abort_{ts}.png"))
        await ctx.close(); await p.stop(); return 31

    repl_before = decoded_target.count(repl)
    decoded_new = decoded_target.replace(find, repl)
    # 디코드 레벨 무결성 가드: 정확히 1건만 바뀌고 그 외 완전 동일해야 함
    if decoded_new == decoded_target:
        print("[ABORT] 치환 후 변화 없음 — 저장 안 함.")
        await ctx.close(); await p.stop(); return 32
    if decoded_new.count(find) != 0 or decoded_new.count(repl) != repl_before + 1:
        print(f"[ABORT] 디코드 무결성 실패(find잔존 {decoded_new.count(find)}, repl {decoded_new.count(repl)}/기대 {repl_before+1}) — 저장 안 함.")
        await ctx.close(); await p.stop(); return 33
    if decoded_new.replace(repl, find, 1) != decoded_target:
        print("[ABORT] 역치환 대조 불일치 — find/repl 외 변경 위험. 저장 안 함.")
        await ctx.close(); await p.stop(); return 34

    # 재인코드(원 인코더와 동일 스킴: rawurlencode → base64) 후 해당 블록 payload만 교체
    new_b64 = base64.b64encode(urllib.parse.quote(decoded_new, safe="").encode("ascii")).decode("ascii")
    # 재인코드 라운드트립 검증 — 새 base64 디코드가 정확히 decoded_new 여야 함
    if _decode_vc_raw_html(new_b64) != decoded_new:
        print("[ABORT] 재인코드 라운드트립 실패 — 저장 안 함.")
        await ctx.close(); await p.stop(); return 35
    tb = blocks[target_idx]
    new_raw = raw[:tb.start(1)] + new_b64 + raw[tb.end(1):]
    # raw 레벨: 대상 블록 payload 외 나머지 텍스트 완전 동일 보장
    if raw[:tb.start(1)] != new_raw[:tb.start(1)] or raw[tb.end(1):] != new_raw[len(new_raw)-(len(raw)-tb.end(1)):]:
        print("[ABORT] raw 블록 외 영역 불일치 — 저장 안 함.")
        await ctx.close(); await p.stop(); return 36
    print(f"[INFO] 디코드 무결성 통과 · 블록[{target_idx}] payload만 교체 예정 (raw 길이 {len(raw)}→{len(new_raw)})")

    if dry_run:
        print("[INFO] === DRY-RUN — 저장하지 않음. 카운트·무결성만 검증 완료 ===")
        print(f"[INFO] 디코드 발췌(교체 지점): ...{decoded_new[max(0,decoded_new.find(repl)-30):decoded_new.find(repl)+len(repl)+30]}...")
        await ctx.close(); await p.stop(); return 0

    # TinyMCE 인스턴스 detach 후 textarea 를 단일 진실원으로 되쓰기
    detached = await page.evaluate(
        """() => { try {
            if (window.tinymce && tinymce.get('content')) { tinymce.get('content').remove(); return 'removed'; }
            return 'no-tinymce';
        } catch(e){ return 'err:'+e.message; } }"""
    )
    await page.wait_for_timeout(400)
    print(f"[INFO] TinyMCE detach: {detached}")
    await page.evaluate(
        """(html) => { const ta = document.querySelector('#content');
            ta.value = html; ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true})); }""",
        new_raw,
    )
    await page.wait_for_timeout(500)
    verify = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    if verify != new_raw:
        print("[ABORT] textarea 반영 검증 실패(값 불일치) — 저장 안 함.")
        await ctx.close(); await p.stop(); return 37
    print("[INFO] textarea 반영 확인 (new_raw 일치)")

    pre_status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    print(f"[INFO] 저장 전 상태: {pre_status or '(미검출)'}")
    await page.click("#publish")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    # 저장 후 재검증 — 디코드 기준 find=0, repl=baseline+1
    saved_raw = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    saved_ok = False
    try:
        sblocks = list(_re.finditer(r"\[vc_raw_html\](.*?)\[/vc_raw_html\]", saved_raw, _re.S))
        s_find = s_repl = 0
        for b in sblocks:
            d = _decode_vc_raw_html(b.group(1))
            s_find += d.count(find); s_repl += d.count(repl)
        saved_ok = (s_find == 0 and s_repl == repl_before + 1)
        print(f"[INFO] 저장 후 디코드 재검증: find {s_find}건 / repl {s_repl}건(기대 {repl_before+1})")
    except Exception as e:
        print(f"[WARN] 저장 후 재검증 경고: {e}")
    await page.screenshot(path=str(INSPECT_DIR / f"wp_recept_swap_saved_{ts}.png"))
    print(f"[INFO] 저장 후 상태: {status or '(미검출)'}")
    await ctx.close(); await p.stop()
    print(f"[INFO] === 종합접수처 문자열 교체 {'완료' if saved_ok else '확인 필요'} === (백업: {backup_path})")
    return 0 if saved_ok else 38


MEDIA_NEW_URL = "http://wellperion.com/wp/wp-admin/media-new.php"
MEDIA_LIBRARY_URL = "http://wellperion.com/wp/wp-admin/upload.php"


async def run_media_check() -> int:
    """읽기 전용 — media-new.php 에서 '최대 업로드 크기'만 확인. 변경 없음."""
    async_playwright = _import_playwright()
    print("[INFO] === 워드프레스 미디어 업로드 한도 확인 (읽기 전용) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(MEDIA_NEW_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2000)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2
    text = await page.evaluate(
        """() => { const body = document.body.innerText || '';
            const m = body.match(/[Mm]aximum upload file size[^\\n]*|최대\\s*업로드\\s*(?:파일\\s*)?크기[^\\n]*/);
            return m ? m[0].trim() : ''; }"""
    )
    await page.screenshot(path=str(INSPECT_DIR / "wp_media_check.png"))
    print(f"[INFO] 최대 업로드 크기 문구: {text or '(미검출 — 스크린샷 확인 필요)'}")
    await ctx.close()
    await p.stop()
    return 0


async def run_media_upload(file_path_arg: str) -> int:
    """media-new.php 로 파일 업로드. 완료 후 첨부 편집화면에서 File URL 확보."""
    async_playwright = _import_playwright()
    file_path = Path(file_path_arg)
    print(f"[INFO] === 워드프레스 미디어 업로드: {file_path} ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    if not file_path.exists():
        print(f"[ERROR] 업로드 파일 부재: {file_path}")
        return 4
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(MEDIA_NEW_URL, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2000)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    file_input = await page.query_selector("input[type=file]")
    if not file_input:
        print("[ERROR] 업로드 input[type=file] 미검출 — 스크린샷 확인 필요.")
        await page.screenshot(path=str(INSPECT_DIR / "wp_media_upload_noinput.png"))
        await ctx.close(); await p.stop(); return 5

    print("[INFO] 파일 선택 → 업로드 시작 (대용량, 시간 소요될 수 있음)...")
    await file_input.set_input_files(str(file_path))

    # 업로드 완료 판정: media-new.php 결과 그리드에 "편집" 링크(post.php?...action=edit)가 뜨면 완료.
    edit_href = None
    waited, deadline = 0, 900  # 최대 15분 대기 (160MB 대용량)
    while waited < deadline:
        edit_href = await page.evaluate(
            """() => { const a = document.querySelector('a[href*="post.php?post="][href*="action=edit"]');
                return a ? a.href : null; }"""
        )
        has_error = await page.evaluate(
            """() => !!document.querySelector('.upload-errors, .error, .media-item.error')"""
        )
        if has_error:
            err_text = await page.evaluate(
                "() => { const e=document.querySelector('.upload-errors, .error, .media-item.error'); return e? e.innerText.trim():''; }"
            )
            print(f"[ERROR] 업로드 오류 감지: {err_text}")
            await page.screenshot(path=str(INSPECT_DIR / "wp_media_upload_error.png"))
            await ctx.close(); await p.stop(); return 6
        if edit_href:
            break
        await asyncio.sleep(3)
        waited += 3
    await page.screenshot(path=str(INSPECT_DIR / "wp_media_upload_result.png"))
    if not edit_href:
        print(f"[ERROR] {deadline}초 내 업로드 완료 미확인 — 스크린샷(wp_media_upload_result.png) 확인 필요.")
        await ctx.close(); await p.stop(); return 7

    import re as _re
    m = _re.search(r"[?&]post=(\d+)", edit_href)
    attach_id = m.group(1) if m else None
    print(f"[INFO] 업로드 완료 — 첨부 ID: {attach_id or '(미검출)'}")

    file_url = None
    if attach_id:
        await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={attach_id}&action=edit",
                         wait_until="domcontentloaded", timeout=40_000)
        await page.wait_for_timeout(1500)
        file_url = await page.evaluate(
            """() => { const i=document.querySelector('#attachment_url'); return i? i.value : ''; }"""
        )
    print(f"[INFO] 첨부 파일 URL: {file_url or '(미검출 — 편집화면 확인 필요)'}")
    await ctx.close()
    await p.stop()
    return 0 if file_url else 8


# ═══════════════════════════════════════════════════════════════════
# 2026-07-15 시토 — 자체 Survey · 습득분실물(보기/접수) WP 자체 호스팅 신규 3페이지
#   GM 확정: 문의 자체 Survey·습득분실물 갤러리/등록을 wellperion.com WP 페이지로 호스팅
#   (github.io 아님). 방식 = reception/inquiry 와 100% 동일(Classic 편집기 Text탭 + [vc_raw_html]
#   직접 주입). 주입 소스(self-contained·SSOT, CSS 래퍼 스코프로 테마 오염 차단):
#     · 자체 Survey     → cmo/survey/wp_inquiry_form.html             (slug: inquiry-form         → /ko/inquiry-form/)
#     · 습득분실물 보기  → coo/reception/wp_lost_found_gallery_block.html (slug: lost-found        → /ko/lost-found/)
#     · 습득분실물 접수  → coo/reception/wp_lost_found_register_block.html(slug: lost-found-register → /ko/lost-found-register/)
#   ★ 신규 생성(post_id 미지정=post-new.php)은 GM 세션 필요(--mode setup 선행).
#     발행(공개) 전 draft 초안 미리보기(비공개)로 실측 권장 — 초안은 고객 미노출·삭제로 즉시 롤백.
SURVEY_BLOCK_FILE = ROOT / "3. 웰페리온 가이드" / "cmo" / "survey" / "wp_inquiry_form.html"
LF_GALLERY_BLOCK_FILE = ROOT / "3. 웰페리온 가이드" / "coo" / "reception" / "wp_lost_found_gallery_block.html"
LF_REGISTER_BLOCK_FILE = ROOT / "3. 웰페리온 가이드" / "coo" / "reception" / "wp_lost_found_register_block.html"

# key: (block_file, 신규생성 시 기본 제목, 발행 시 기본 slug)
_NEW_PAGE_SPECS = {
    "survey":      (SURVEY_BLOCK_FILE,      "문의하기",         "inquiry-form"),
    "lf-gallery":  (LF_GALLERY_BLOCK_FILE,  "습득 분실물 현황", "lost-found"),
    "lf-register": (LF_REGISTER_BLOCK_FILE, "습득물 등록",      "lost-found-register"),
}


async def run_draft_page(spec_key: str, post_id_arg: "str | None" = None) -> int:
    """자체 Survey / 습득분실물 갤러리·등록 페이지를 비공개 초안으로 생성/갱신 (발행 안 함).
    reception 패턴과 동일: Classic 편집기 Text탭에 [vc_raw_html]로 self-contained 블록 주입.
    post_id 미지정=신규 생성(post-new.php), 지정=기존 페이지 갱신(발행 상태면 발행 유지)."""
    block_file, title, _slug = _NEW_PAGE_SPECS[spec_key]
    async_playwright = _import_playwright()
    print(f"[INFO] === WP 페이지({spec_key}) — 비공개 초안 생성/갱신 (발행 안 함) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    if not block_file.exists():
        print(f"[ERROR] 주입 블록 HTML 부재: {block_file}")
        return 4
    raw_html = block_file.read_text(encoding="utf-8")
    html = _wrap_vc_raw_html(raw_html)
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    target = (f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko"
              if post_id_arg else NEW_PAGE_URL)
    print(f"[INFO] 대상: {'갱신 post='+post_id_arg if post_id_arg else '신규 페이지'}")
    await page.goto(target, wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    probe = await page.evaluate(
        """() => ({
            title_classic: !!document.querySelector('#title'),
            content_textarea: !!document.querySelector('#content'),
            text_tab: !!document.querySelector('#content-html'),
            save_draft_btn: !!document.querySelector('#save-post'),
        })"""
    )
    print(f"[INFO] 편집기 감지: {probe}")
    await page.screenshot(path=str(INSPECT_DIR / f"wp_{spec_key}_editor.png"))
    if not probe.get("title_classic") or not probe.get("content_textarea"):
        print(f"[ERROR] Classic 편집기 미검출 — 스크린샷: wp_{spec_key}_editor.png")
        await ctx.close(); await p.stop(); return 5

    cur_title = await page.evaluate("() => (document.querySelector('#title')||{}).value || ''")
    if not cur_title.strip():
        await page.fill("#title", title)
        await page.wait_for_timeout(500)

    if probe.get("text_tab"):
        await page.click("#content-html")
        await page.wait_for_timeout(800)
    await page.evaluate(
        """(html) => { const ta = document.querySelector('#content');
            ta.value = html; ta.dispatchEvent(new Event('input', {bubbles:true}));
            ta.dispatchEvent(new Event('change', {bubbles:true})); }""",
        html,
    )
    await page.wait_for_timeout(500)
    injected = await page.evaluate("() => (document.querySelector('#content')||{}).value || ''")
    ok_inject = "vc_raw_html" in injected and len(injected) > 100
    print(f"[INFO] 본문 주입 검증: {ok_inject} (길이 {len(injected)})")
    if not ok_inject:
        print("[ERROR] 본문 주입 실패 — 저장 중단.")
        await ctx.close(); await p.stop(); return 6

    pre_status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    is_published = ("공개" in pre_status) or ("발행" in pre_status) or ("published" in pre_status.lower())
    if is_published:
        print(f"[INFO] 이미 발행됨('{pre_status}') → 업데이트로 저장(발행 유지)")
        await page.click("#publish")
    else:
        await page.click("#save-post")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    cur = page.url
    import re as _re
    m = _re.search(r"[?&]post=(\d+)", cur)
    post_id = m.group(1) if m else None
    status = await page.evaluate(
        "() => (document.querySelector('#post-status-display')||{}).innerText || ''"
    )
    await page.screenshot(path=str(INSPECT_DIR / f"wp_{spec_key}_draft_saved.png"))
    print(f"[INFO] 저장 후 URL: {cur}")
    print(f"[INFO] 글 상태: {status or '(미검출)'}  /  page_id: {post_id or '(미검출)'}")
    if post_id:
        preview = f"http://wellperion.com/wp/?page_id={post_id}&preview=true"
        edit = f"http://wellperion.com/wp/wp-admin/post.php?post={post_id}&action=edit"
        print("[INFO] === GM 검수 링크 ===")
        print(f"        미리보기: {preview}")
        print(f"        편집화면: {edit}")
        print(f"[INFO] 발행 명령: python scripts\\wordpress_admin_playwright.py --mode publish-page --page {spec_key} --post-id {post_id}")
    print("[INFO] (※ 초안 상태 — 외부에 공개되지 않음. 발행은 GM 확인 후 별도 진행)")
    await ctx.close(); await p.stop()
    print(f"[INFO] === {spec_key} 초안 생성 완료 (발행 안 함) ===")
    return 0 if post_id else 7


async def run_publish_page(spec_key: str, post_id_arg: str, slug: "str | None" = None) -> int:
    """자체 Survey / 습득분실물 초안을 slug 설정 후 공개 발행. (되돌리기: 편집화면서 임시글 전환 가능)"""
    slug = slug or _NEW_PAGE_SPECS[spec_key][2]
    async_playwright = _import_playwright()
    print(f"[INFO] === WP 페이지({spec_key}) 발행 (post={post_id_arg}, slug={slug}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(f"http://wellperion.com/wp/wp-admin/post.php?post={post_id_arg}&action=edit&lang=ko",
                    wait_until="domcontentloaded", timeout=40_000)
    await page.wait_for_timeout(2500)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2
    try:
        if await page.query_selector("#edit-slug-buttons button.edit-slug"):
            await page.click("#edit-slug-buttons button.edit-slug")
            await page.wait_for_timeout(600)
            await page.fill("#new-post-slug", slug)
            await page.click("#edit-slug-buttons button.save")
            await page.wait_for_timeout(1200)
            print(f"[INFO] 슬러그 설정: {slug}")
    except Exception as e:
        print(f"[WARN] 슬러그 설정 경고(무시): {e}")
    await page.click("#publish")
    try:
        await page.wait_for_url("**/post.php?post=*", timeout=30_000)
    except Exception:
        await page.wait_for_timeout(4000)
    await page.wait_for_timeout(1500)
    status = await page.evaluate("() => (document.querySelector('#post-status-display')||{}).innerText || ''")
    permalink = await page.evaluate(
        "() => { const a=document.querySelector('#sample-permalink a, #sample-permalink'); return a? (a.href||a.innerText):''; }"
    )
    await page.screenshot(path=str(INSPECT_DIR / f"wp_{spec_key}_published.png"))
    print(f"[INFO] 글 상태: {status or '(미검출)'}")
    print(f"[INFO] 공개 URL: {permalink or '(미검출)'}")
    await ctx.close(); await p.stop()
    published = "공개" in status or "published" in status.lower() or "발행" in status
    print(f"[INFO] === 발행 {'완료' if published else '확인 필요'} ===")
    return 0 if published else 8


CUSTOMIZE_CSS_URL = "http://wellperion.com/wp/wp-admin/customize.php?autofocus%5Bsection%5D=custom_css"


async def run_swap_additional_css(find: str, repl: str, dry_run: bool = False) -> int:
    """WP 커스터마이저 '추가 CSS'(Additional CSS, <style id=wp-custom-css>)에서 find→repl 전역 치환.
    용도: @font-face url 의 옛 호스트(wellperion.cafe24.com/font/ = CORS 차단) → 동일 오리진(/font/) 교정.
    - CodeMirror DOM 대신 wp.customize JS API로 setting 값을 직접 읽고/쓴다(견고).
    - 원본 CSS 타임스탬프 백업 · find 출현 0건이면 이미 교정으로 보고 무손상 종료.
    - 무결성: 치환 후 find 잔존 0 · repl 증가분 == find 출현수 · 그 외 문자열 완전 동일(역치환 대조).
    - 저장 후 라이브 프론트(홈)에서 옛 호스트 참조 0건 재확인(진짜 결과 검증).
    - dry_run=True: 저장 없이 카운트·무결성만 보고."""
    import datetime
    async_playwright = _import_playwright()
    print(f"[INFO] === 추가 CSS 전역 치환 (dry_run={dry_run}) ===")
    print(f"[INFO] find: {find}")
    print(f"[INFO] repl: {repl}")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)
    p, ctx = await _launch(async_playwright)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(CUSTOMIZE_CSS_URL, wait_until="domcontentloaded", timeout=60_000)
    if "wp-login" in page.url:
        print("[ERROR] 세션 만료 — setup 재실행 필요.")
        await ctx.close(); await p.stop(); return 2

    # 커스터마이저·custom_css setting 준비 대기 (최대 ~30s)
    read = {"ready": False}
    for _ in range(30):
        read = await page.evaluate(
            """() => {
                if(!(window.wp && wp.customize && wp.customize.state)) return {ready:false};
                if(!wp.customize.state('activated')) { /* 아직 부팅중일 수 있음 */ }
                let id=null;
                wp.customize.each(function(s){ if(s.id.indexOf('custom_css')===0) id=s.id; });
                if(!id) return {ready:false};
                return {ready:true, id:id, value: wp.customize(id).get() || ''};
            }"""
        )
        if read.get("ready"):
            break
        await page.wait_for_timeout(1000)
    if not read.get("ready"):
        await page.screenshot(path=str(INSPECT_DIR / "wp_customize_css_notready.png"))
        print("[ERROR] 커스터마이저 custom_css setting 미준비 — 중단(무손상). 스샷: wp_customize_css_notready.png")
        await ctx.close(); await p.stop(); return 50
    setting_id = read["id"]
    original = read["value"] or ""
    print(f"[INFO] custom_css setting id: {setting_id} (길이 {len(original)})")
    if len(original) < 20:
        print(f"[ERROR] CSS 비정상(길이 {len(original)}) — 중단(저장 안 함).")
        await ctx.close(); await p.stop(); return 51

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = INSPECT_DIR / f"additional_css_backup_{ts}.txt"
    backup_path.write_text(original, encoding="utf-8")
    print(f"[INFO] 원본 백업: {backup_path}")

    count = original.count(find)
    print(f"[INFO] find 출현: {count}건")
    if count == 0:
        print("[INFO] find 0건 — 이미 교정됐거나 대상 없음. 저장 없이 종료(무손상).")
        await ctx.close(); await p.stop(); return 0
    new_css = original.replace(find, repl)
    # 무결성 가드 (repl 이 find 의 부분문자열이어도 안전 — 카운트 겹침 가정 없음)
    if new_css == original:
        print("[ABORT] 치환 후 변화 없음 — 저장 안 함."); await ctx.close(); await p.stop(); return 52
    if new_css.count(find) != 0:
        print(f"[ABORT] find 잔존 {new_css.count(find)} — 저장 안 함."); await ctx.close(); await p.stop(); return 53
    # 길이 델타 = count*(len(find)-len(repl)) 정확 일치 → 딱 count건만·그 외 무변경 증명
    expected_delta = count * (len(find) - len(repl))
    if len(original) - len(new_css) != expected_delta:
        print(f"[ABORT] 길이 델타 불일치(기대 {expected_delta}, 실제 {len(original)-len(new_css)}) — 저장 안 함.")
        await ctx.close(); await p.stop(); return 54
    print(f"[INFO] 무결성 통과 · {count}건 교체 예정 (CSS 길이 {len(original)}→{len(new_css)})")

    if dry_run:
        idx = new_css.find(repl)
        print(f"[INFO] 발췌(교체 지점): ...{new_css[max(0,idx-40):idx+len(repl)+30]}...")
        print("[INFO] === DRY-RUN — 저장하지 않음 ===")
        await ctx.close(); await p.stop(); return 0

    # wp.customize API로 setting 값 세팅(→ dirty) 후 저장(Save & Publish)
    setres = await page.evaluate(
        """({id, val}) => { try {
            wp.customize(id).set(val);
            return {ok: wp.customize(id).get() === val};
        } catch(e){ return {ok:false, err:String(e)}; } }""",
        {"id": setting_id, "val": new_css},
    )
    if not setres.get("ok"):
        print(f"[ABORT] setting 세팅 실패: {setres} — 저장 안 함."); await ctx.close(); await p.stop(); return 56
    await page.wait_for_timeout(500)
    # 저장 버튼 클릭 (#save) — 활성화될 때까지 잠깐 대기
    try:
        await page.click("#save", timeout=10_000)
    except Exception:
        await page.evaluate("() => { try{ wp.customize.previewer.save(); }catch(e){} }")
    # saved 상태 폴링
    saved = False
    for _ in range(30):
        saved = await page.evaluate(
            "() => !!(window.wp && wp.customize && wp.customize.state && wp.customize.state('saved') && wp.customize.state('saved').get())"
        )
        if saved:
            break
        await page.wait_for_timeout(1000)
    await page.screenshot(path=str(INSPECT_DIR / f"wp_customize_css_saved_{ts}.png"))
    print(f"[INFO] 커스터마이저 저장 상태: {'saved' if saved else '미확정'}")
    await ctx.close(); await p.stop()

    # 라이브 프론트 재검증 (별도 요청 — 캐시 없는 진짜 결과)
    import urllib.request
    live_ok = None
    try:
        req = urllib.request.Request("http://wellperion.com/", headers={"Cache-Control": "no-cache"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        old_host = "wellperion.cafe24.com/font"
        live_old = html.count(old_host)
        live_new = html.count("/font/FuturaPT")
        live_ok = (live_old == 0 and live_new > 0)
        print(f"[INFO] 라이브 재검증: 옛 호스트 {live_old}건(기대 0) · /font/FuturaPT {live_new}건(>0)")
    except Exception as e:
        print(f"[WARN] 라이브 재검증 경고: {e}")
    done = saved and (live_ok is not False)
    print(f"[INFO] === 추가 CSS 치환 {'완료' if done else '확인 필요'} === (백업: {backup_path})")
    return 0 if done else 57


def main() -> int:
    ap = argparse.ArgumentParser(description="워드프레스 관리자 반자동 (setup/check/inspect/draft-inquiry/publish-inquiry/add-menu/swap-href/wpml-create-en/draft-inquiry-en/publish-inquiry-en/draft-reception/publish-reception/draft-page/publish-page/media-check/media-upload/swap-additional-css)")
    ap.add_argument("--mode", choices=[
        "setup", "check", "inspect",
        "draft-inquiry", "publish-inquiry", "add-menu", "remove-menu", "swap-href",
        "wpml-create-en", "draft-inquiry-en", "publish-inquiry-en", "cutover-inquiry-en",
        "draft-reception", "publish-reception", "swap-reception-text",
        "draft-page", "publish-page",
        "media-check", "media-upload",
        "swap-additional-css",
    ], default="setup")
    ap.add_argument("--page", dest="page", default=None,
                    choices=["survey", "lf-gallery", "lf-register"],
                    help="draft-page/publish-page 대상: survey(자체Survey)/lf-gallery(습득분실물 보기)/lf-register(습득분실물 접수)")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="swap-reception-text: 저장 없이 카운트·무결성만 검증")
    ap.add_argument("--find", dest="find", default=None, help="swap-href 찾을 문자열")
    ap.add_argument("--repl", dest="repl", default=None, help="swap-href 바꿀 문자열")
    ap.add_argument("--slug", dest="slug", default=None, help="publish-* 슬러그 (미지정 시: inquiry 모드=inquiry, reception 모드=reception)")
    ap.add_argument("--menu-id", dest="menu_id", default=KOREAN_MENU_ID, help="add-menu/remove-menu 대상 메뉴 ID(기본 59=한글메인)")
    ap.add_argument("--object-ids", dest="object_ids", default=None,
                    help="remove-menu: 제거할 페이지 object-id 콤마목록(예: 8460,8462,8464)")
    ap.add_argument("--keep-auto-add", dest="keep_auto_add", action="store_true",
                    help="remove-menu: '새 페이지 자동 추가' 체크박스를 건드리지 않음(기본은 끔)")
    ap.add_argument("--post-id", dest="post_id", default=None,
                    help="draft/publish 갱신 대상 페이지 ID")
    ap.add_argument("--file", dest="file_path", default=None, help="media-upload 대상 파일 경로")
    args = ap.parse_args()
    if args.mode == "setup":
        return asyncio.run(run_setup())
    if args.mode == "inspect":
        return asyncio.run(run_inspect())
    if args.mode == "draft-inquiry":
        return asyncio.run(run_draft_inquiry(args.post_id))
    if args.mode == "publish-inquiry":
        if not args.post_id:
            print("[ERROR] --post-id 필요"); return 1
        return asyncio.run(run_publish_inquiry(args.post_id, args.slug or "inquiry"))
    if args.mode == "add-menu":
        if not args.post_id:
            print("[ERROR] --post-id 필요"); return 1
        return asyncio.run(run_add_menu(args.post_id, args.menu_id))
    if args.mode == "remove-menu":
        if not args.object_ids:
            print("[ERROR] remove-menu는 --object-ids 8460,8462,8464 필요"); return 1
        ids = [s.strip() for s in args.object_ids.split(",") if s.strip()]
        return asyncio.run(run_remove_menu(ids, args.menu_id, disable_auto_add=not args.keep_auto_add))
    if args.mode == "swap-href":
        if not args.post_id or not args.find or not args.repl:
            print("[ERROR] swap-href는 --post-id --find --repl 모두 필요"); return 1
        return asyncio.run(run_swap_href(args.post_id, args.find, args.repl))
    if args.mode == "wpml-create-en":
        return asyncio.run(run_wpml_create_en_translation())
    if args.mode == "draft-inquiry-en":
        if not args.post_id:
            print("[ERROR] --post-id 필요 (영어 페이지 ID)"); return 1
        return asyncio.run(run_draft_inquiry_en(args.post_id))
    if args.mode == "cutover-inquiry-en":
        # 영문 구글폼 → 자체폼 컷오버(배9674). 발행 유지 = 즉시 라이브. rollback = draft-inquiry-en(구글폼 재주입).
        if not args.post_id:
            print("[ERROR] --post-id 필요 (영어 페이지 ID, 예 8408)"); return 1
        return asyncio.run(run_draft_inquiry_en(args.post_id, INQUIRY_FORM_FILE_EN))
    if args.mode == "publish-inquiry-en":
        if not args.post_id:
            print("[ERROR] --post-id 필요 (영어 페이지 ID)"); return 1
        return asyncio.run(run_publish_inquiry_en(args.post_id, args.slug or "inquiry"))
    if args.mode == "draft-reception":
        return asyncio.run(run_draft_reception(args.post_id))
    if args.mode == "publish-reception":
        if not args.post_id:
            print("[ERROR] --post-id 필요"); return 1
        return asyncio.run(run_publish_reception(args.post_id, args.slug or "reception"))
    if args.mode == "swap-reception-text":
        if not args.find or not args.repl:
            print("[ERROR] swap-reception-text는 --find --repl 필요"); return 1
        return asyncio.run(run_swap_reception_text(
            args.find, args.repl, args.post_id or RECEPTION_POST_ID, args.dry_run))
    if args.mode == "draft-page":
        if not args.page:
            print("[ERROR] draft-page는 --page {survey|lf-gallery|lf-register} 필요"); return 1
        return asyncio.run(run_draft_page(args.page, args.post_id))
    if args.mode == "publish-page":
        if not args.page or not args.post_id:
            print("[ERROR] publish-page는 --page {survey|lf-gallery|lf-register} 와 --post-id 필요"); return 1
        return asyncio.run(run_publish_page(args.page, args.post_id, args.slug))
    if args.mode == "swap-additional-css":
        if not args.find or not args.repl:
            print("[ERROR] swap-additional-css는 --find --repl 필요"); return 1
        return asyncio.run(run_swap_additional_css(args.find, args.repl, args.dry_run))
    if args.mode == "media-check":
        return asyncio.run(run_media_check())
    if args.mode == "media-upload":
        if not args.file_path:
            print("[ERROR] --file 필요"); return 1
        return asyncio.run(run_media_upload(args.file_path))
    return asyncio.run(run_check())


if __name__ == "__main__":
    sys.exit(main())
