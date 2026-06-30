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


async def run_draft_inquiry_en(post_id_arg: str) -> int:
    """영어 문의 페이지를 비공개 초안으로 생성/갱신.
    wp_inquiry_block_en.html을 [vc_raw_html]로 주입. &lang=en 컨텍스트 사용."""
    async_playwright = _import_playwright()
    print(f"[INFO] === 워드프레스 영어 문의 페이지 — 비공개 초안 생성/갱신 (post={post_id_arg}) ===")
    if not PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    if not INQUIRY_BLOCK_FILE_EN.exists():
        print(f"[ERROR] 영어 문의 블록 HTML 부재: {INQUIRY_BLOCK_FILE_EN}")
        return 4
    raw_html = INQUIRY_BLOCK_FILE_EN.read_text(encoding="utf-8")
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


def main() -> int:
    ap = argparse.ArgumentParser(description="워드프레스 관리자 반자동 (setup/check/inspect/draft-inquiry/publish-inquiry/add-menu/swap-href/wpml-create-en/draft-inquiry-en/publish-inquiry-en/draft-reception/publish-reception)")
    ap.add_argument("--mode", choices=[
        "setup", "check", "inspect",
        "draft-inquiry", "publish-inquiry", "add-menu", "swap-href",
        "wpml-create-en", "draft-inquiry-en", "publish-inquiry-en",
        "draft-reception", "publish-reception",
    ], default="setup")
    ap.add_argument("--find", dest="find", default=None, help="swap-href 찾을 문자열")
    ap.add_argument("--repl", dest="repl", default=None, help="swap-href 바꿀 문자열")
    ap.add_argument("--slug", dest="slug", default=None, help="publish-* 슬러그 (미지정 시: inquiry 모드=inquiry, reception 모드=reception)")
    ap.add_argument("--menu-id", dest="menu_id", default=KOREAN_MENU_ID, help="add-menu 대상 메뉴 ID(기본 59=한글메인)")
    ap.add_argument("--post-id", dest="post_id", default=None,
                    help="draft/publish 갱신 대상 페이지 ID")
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
    return asyncio.run(run_check())


if __name__ == "__main__":
    sys.exit(main())
