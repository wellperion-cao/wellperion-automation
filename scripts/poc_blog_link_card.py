# scripts/poc_blog_link_card.py
# PoC — SmartEditor ONE 링크 카드(링크 컴포넌트) 삽입 실측
#
# 목표: 네이버 블로그 SmartEditor에서 '링크' 툴바 버튼으로 URL을 입력해
#       og:image 포함 링크 카드가 본문에 생성되는지 검증한다.
#
# 실행:
#   python scripts\poc_blog_link_card.py --mode blog
#   python scripts\poc_blog_link_card.py --mode cafe
#   python scripts\poc_blog_link_card.py --mode blog --url "https://wellperion.com/ko/inquiry/"
#
# 결과물: scripts/poc-evidence/link-card-{mode}-{ts}.png
#         임시저장까지만. 발행 없음.

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

# 삽입할 기본 CTA URL (깔끔한 형태 — UTM 없이 og:image 노출 우선)
DEFAULT_CTA_URL = "http://wellperion.com/ko/inquiry/"

# 블로그 설정
BLOG_PROFILE_DIR = ROOT / "profiles" / "naver-blog"
BLOG_WRITE_URL = "https://blog.naver.com/wellperion/postwrite"

# 카페 설정
CAFE_PROFILE_DIR = ROOT / "profiles" / "naver-cafe"
CAFE_WRITE_URL = "https://cafe.naver.com/ca-fe/cafes/11948735/articles/write?boardType=L&menuId=659"

# SmartEditor 링크 툴바 버튼 셀렉터 후보
# 네이버 SmartEditor ONE 실측 — '링크' 버튼: data-name="oglink" 또는 data-name="link"
LINK_TOOLBAR_SELECTORS = [
    'button[data-name="oglink"]',       # og 링크 카드 전용 버튼 (블로그 실측 유력)
    'button[data-name="link"]',         # 일반 하이퍼링크 버튼
    'button[data-log="link"]',
    'button[data-log="dot.oglink"]',
    'button[title*="링크"]',
    'button[aria-label*="링크"]',
    '.se-toolbar button[class*="link"]',
]

# 링크 입력 팝업 내 URL 입력창 셀렉터 후보
LINK_INPUT_SELECTORS = [
    'input[placeholder*="URL"]',
    'input[placeholder*="url"]',
    'input[placeholder*="주소"]',
    'input[placeholder*="링크"]',
    '.se-popup input[type="text"]',
    '.se-popup input[type="url"]',
    'input.se-input-url',
    'input[name="url"]',
]

# 팝업 내 확인/삽입 버튼
LINK_CONFIRM_SELECTORS = [
    '.se-popup button.se-popup-button-confirm',
    '.se-popup button:has-text("확인")',
    '.se-popup button:has-text("등록")',
    '.se-popup button:has-text("삽입")',
    '.se-popup button[type="submit"]',
]

# 삽입 결과 — og 링크 카드 컴포넌트 셀렉터
LINK_CARD_RESULT_SELECTORS = [
    '.se-component.se-oglink',     # SmartEditor ONE og 링크 카드 컴포넌트
    '.se-module-oglink',           # og 링크 모듈
    '.se-oglink-thumbnail',        # 썸네일(이미지) 포함 여부 확인용
    '.se-component-oglink',
]

# 드래프트 팝업 취소 (블로그 — 이어쓰기 팝업)
DRAFT_RESUME_CANCEL_SELECTORS = [
    "button.se-popup-button-cancel",
    '.se-popup-alert-confirm button:has-text("취소")',
]

POPUP_KILLER_SELECTORS = (
    ".se-popup-dim, .se-popup-alert, .se-popup-alert-confirm, "
    ".blog-se-alert, .se-help-panel"
)

# Windows 콘솔 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _import_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        print("[ERROR] playwright 미설치. .venv 활성화 후 'pip install playwright; playwright install chromium' 필요.")
        sys.exit(10)


async def _launch_context(async_playwright, profile_dir: Path):
    profile_dir.mkdir(parents=True, exist_ok=True)
    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        args=["--start-maximized"],
        no_viewport=True,
    )
    return p, context


async def _first_locator(scope, selectors: list[str]):
    for sel in selectors:
        loc = scope.locator(sel).first
        try:
            if await loc.count() > 0:
                return loc, sel
        except Exception:
            continue
    return None, None


async def _install_popup_killer(page) -> None:
    try:
        await page.evaluate(
            """(sel) => {
                const kill = () => document.querySelectorAll(sel).forEach(el => { try { el.remove(); } catch(e){} });
                kill();
                const mo = new MutationObserver(kill);
                mo.observe(document.documentElement, { childList: true, subtree: true });
                window.__wpKillTimer = setInterval(kill, 700);
            }""",
            POPUP_KILLER_SELECTORS,
        )
    except Exception as e:
        print(f"[WARN] popup killer 설치 실패(무시): {e}")


async def _stop_popup_killer(page) -> None:
    """링크 팝업 모달 열기 전 popup killer 일시 정지."""
    try:
        await page.evaluate(
            """() => {
                if (window.__wpKillTimer) { clearInterval(window.__wpKillTimer); window.__wpKillTimer = null; }
                if (window.__wpKillObserver) { try { window.__wpKillObserver.disconnect(); } catch(e){} window.__wpKillObserver = null; }
            }"""
        )
    except Exception:
        pass


async def _resolve_editor_scope(page):
    """SmartEditor가 iframe 안에 있을 수 있음 → frame 우선 탐색."""
    for fr in page.frames:
        try:
            if await fr.locator(".se-title-text, textarea.textarea_input, .__se_placeholder").count() > 0:
                print(f"[INFO] SmartEditor frame 감지: {fr.name or fr.url[:80]}")
                return fr
        except Exception:
            continue
    return page


async def _dismiss_draft_resume_popup(page) -> None:
    """블로그 이어쓰기 팝업 취소(새 글)."""
    for sel in DRAFT_RESUME_CANCEL_SELECTORS:
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(force=True)
                print(f"[INFO] 이어쓰기 팝업 취소 ({sel!r})")
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue


async def _dump_toolbar_buttons(scope) -> None:
    """SmartEditor 툴바 버튼 전체 목록을 출력 — 링크 관련 버튼 탐색용."""
    try:
        btns = await scope.evaluate("""() => {
            const results = [];
            document.querySelectorAll('.se-toolbar button, .se-toolbar-group button').forEach(btn => {
                results.push({
                    tag: btn.tagName,
                    dataName: btn.getAttribute('data-name'),
                    dataLog: btn.getAttribute('data-log'),
                    title: btn.getAttribute('title'),
                    ariaLabel: btn.getAttribute('aria-label'),
                    className: btn.className.substring(0, 60),
                    text: (btn.innerText || '').trim().substring(0, 20),
                });
            });
            return results;
        }""")
        link_related = [b for b in btns if any(
            kw in str(b.get(k, '')).lower()
            for k in ('dataName', 'dataLog', 'title', 'ariaLabel', 'text', 'className')
            for kw in ('link', '링크', 'oglink', 'og')
        )]
        print(f"[INFO] 툴바 버튼 전체 {len(btns)}개 — 링크 관련 {len(link_related)}개:")
        for b in link_related:
            print(f"        data-name={b.get('dataName')!r:20} data-log={b.get('dataLog')!r:25} title={b.get('title')!r} aria={b.get('ariaLabel')!r} cls={b.get('className')!r}")
        if not link_related:
            print("[WARN] 링크 관련 버튼 미발견. 전체 버튼 목록:")
            for b in btns[:30]:
                print(f"        data-name={b.get('dataName')!r:20} data-log={b.get('dataLog')!r:25} text={b.get('text')!r}")
    except Exception as e:
        print(f"[WARN] 툴바 버튼 덤프 실패: {e}")


async def _try_paste_url_in_body(page, scope, cta_url: str) -> bool:
    """방법 B: 본문 빈 줄에 URL만 붙여넣기 → 에디터가 자동 링크 카드화하는지 시도."""
    print("[INFO] 방법 B: 본문 URL 붙여넣기 → 자동 링크 카드화 시도")
    try:
        # 본문 포커스
        body_loc = scope.locator(".se-component.se-text .se-text-paragraph, .__se_placeholder.se-fs15").first
        if await body_loc.count() > 0:
            await body_loc.click()
        else:
            await page.keyboard.press("Control+End")
        await page.wait_for_timeout(500)
        # 빈 줄 추가
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)
        # URL 클립보드 붙여넣기 (clipboard API 없는 환경 → keyboard.type)
        await page.keyboard.type(cta_url, delay=10)
        await page.wait_for_timeout(500)
        # Enter — 에디터가 URL 변환 트리거를 Enter로 실행하는지
        await page.keyboard.press("Enter")
        # og:image 비동기 로딩 대기 — 최대 8초 폴링 (PoC 1차 실측: 3초로 짧아 미감지)
        for _ in range(16):
            await page.wait_for_timeout(500)
            for sel in LINK_CARD_RESULT_SELECTORS:
                for frame in [scope] + list(page.frames):
                    try:
                        cnt = await frame.evaluate(f"() => document.querySelectorAll('{sel}').length")
                        if cnt > 0:
                            print(f"[INFO] 방법 B 성공 — 자동 링크 카드 감지 ({sel}: {cnt}개, frame)")
                            return True
                    except Exception:
                        pass
        print("[INFO] 방법 B — 자동 링크 카드화 없음 (8초 대기 후 미감지)")
        return False
    except Exception as e:
        print(f"[WARN] 방법 B 실패: {e}")
        return False


async def run_poc(mode: str, cta_url: str) -> int:
    async_playwright = _import_playwright()

    profile_dir = BLOG_PROFILE_DIR if mode == "blog" else CAFE_PROFILE_DIR
    write_url = BLOG_WRITE_URL if mode == "blog" else CAFE_WRITE_URL

    if not profile_dir.exists():
        print(f"[ERROR] 프로필 미존재({profile_dir}) — 먼저 --mode setup 으로 세션 저장 필요.")
        return 3

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_base = EVIDENCE_DIR / f"link-card-{mode}-{ts}"

    print(f"[INFO] === SmartEditor 링크 카드 PoC ({mode}) ===")
    print(f"[INFO] 삽입 URL: {cta_url}")

    p, context = await _launch_context(async_playwright, profile_dir)
    page = await context.new_page()

    try:
        print(f"[INFO] 글쓰기 진입: {write_url}")
        await page.goto(write_url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3500)

        # 블로그: 이어쓰기 팝업 취소
        if mode == "blog":
            await _dismiss_draft_resume_popup(page)

        await _install_popup_killer(page)
        await page.wait_for_timeout(1000)

        scope = await _resolve_editor_scope(page)

        # 더미 제목 + 짧은 본문 입력 (SmartEditor 활성화)
        if mode == "blog":
            title_loc = scope.locator(".se-title-text").first
        else:
            title_loc = scope.locator("textarea.textarea_input, .se-title-text").first

        if await title_loc.count() > 0:
            await title_loc.click()
            await page.keyboard.type("링크 카드 PoC 테스트", delay=15)
            await page.wait_for_timeout(500)
        else:
            print("[WARN] 제목 입력란 미발견 — 계속 진행")

        # 본문 포커스
        body_loc = scope.locator(
            ".se-component.se-text .se-text-paragraph, .__se_placeholder.se-fs15, .se-text-paragraph"
        ).first
        if await body_loc.count() > 0:
            await body_loc.click()
            await page.wait_for_timeout(300)
        await page.keyboard.type("웰페리온 문의 링크 카드 테스트입니다.", delay=10)
        await page.wait_for_timeout(500)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)

        # 툴바 버튼 전체 덤프 — 링크 관련 버튼 탐색
        await _dump_toolbar_buttons(scope)
        await page.screenshot(path=str(shot_base) + "_01_before_link.png")
        print(f"[INFO] 스크린샷 저장: {shot_base}_01_before_link.png")

        # ─────────────────────────────────────────────
        # 방법 A: 툴바 링크 버튼 클릭 → URL 입력 팝업
        # ─────────────────────────────────────────────
        print("[INFO] 방법 A: 툴바 링크 버튼 → URL 입력 팝업 시도")
        await _stop_popup_killer(page)

        link_btn, link_sel = await _first_locator(scope, LINK_TOOLBAR_SELECTORS)
        method_a_success = False
        method_b_success = False

        if link_btn is not None:
            print(f"[INFO] 링크 버튼 발견: {link_sel!r}")
            try:
                await link_btn.click(force=True)
                await page.wait_for_timeout(2000)
                await page.screenshot(path=str(shot_base) + "_02_link_popup.png")
                print(f"[INFO] 스크린샷 저장: {shot_base}_02_link_popup.png")

                # URL 입력란 탐색 (팝업이 iframe 안에 있을 수 있음 → 전 프레임 스캔)
                input_loc = None
                input_sel_found = None
                for frame in [page] + list(page.frames):
                    try:
                        for sel in LINK_INPUT_SELECTORS:
                            loc = frame.locator(sel).first
                            if await loc.count() > 0 and await loc.is_visible():
                                input_loc = loc
                                input_sel_found = sel
                                break
                        if input_loc:
                            break
                    except Exception:
                        continue

                if input_loc is not None:
                    print(f"[INFO] URL 입력란 발견: {input_sel_found!r}")
                    await input_loc.fill(cta_url)
                    await page.wait_for_timeout(1000)
                    await page.screenshot(path=str(shot_base) + "_03_url_typed.png")
                    print(f"[INFO] 스크린샷 저장: {shot_base}_03_url_typed.png")

                    # 확인 버튼 클릭
                    confirm_loc = None
                    for frame in [page] + list(page.frames):
                        try:
                            for sel in LINK_CONFIRM_SELECTORS:
                                loc = frame.locator(sel).first
                                if await loc.count() > 0 and await loc.is_visible():
                                    confirm_loc = loc
                                    break
                            if confirm_loc:
                                break
                        except Exception:
                            continue

                    if confirm_loc is not None:
                        await confirm_loc.click(force=True)
                        print("[INFO] 확인 버튼 클릭")
                        await page.wait_for_timeout(4000)  # og 썸네일 로딩 대기
                    else:
                        # 확인 버튼 없으면 Enter로 시도
                        await page.keyboard.press("Enter")
                        print("[INFO] 확인 버튼 미발견 — Enter로 대체")
                        await page.wait_for_timeout(4000)

                    await page.screenshot(path=str(shot_base) + "_04_after_insert.png")
                    print(f"[INFO] 스크린샷 저장: {shot_base}_04_after_insert.png")

                    # 링크 카드 컴포넌트 삽입 확인
                    for sel in LINK_CARD_RESULT_SELECTORS:
                        cnt = await scope.evaluate(f"() => document.querySelectorAll('{sel}').length")
                        if cnt > 0:
                            print(f"[INFO] 방법 A 성공 — 링크 카드 컴포넌트 감지 ({sel}: {cnt}개)")
                            method_a_success = True
                            break

                    # og:image 썸네일 포함 여부 추가 확인
                    if method_a_success:
                        thumb_cnt = await scope.evaluate(
                            "() => document.querySelectorAll('.se-oglink-thumbnail img, .se-module-oglink img').length"
                        )
                        has_thumbnail = thumb_cnt > 0
                        print(f"[INFO] og:image 썸네일: {'있음' if has_thumbnail else '없음'} ({thumb_cnt}개 img)")

                    if not method_a_success:
                        print("[WARN] 방법 A — 링크 카드 컴포넌트 미감지")
                else:
                    print("[WARN] URL 입력란 미발견 — 방법 A 실패")
            except Exception as e:
                print(f"[WARN] 방법 A 팝업 처리 실패: {e}")
        else:
            print("[WARN] 툴바 링크 버튼 미발견 — 방법 A 건너뜀")

        await _install_popup_killer(page)

        # ─────────────────────────────────────────────
        # 방법 B: 본문 URL 직접 붙여넣기 → 자동 카드화
        # ─────────────────────────────────────────────
        if not method_a_success:
            method_b_success = await _try_paste_url_in_body(page, scope, cta_url)
            await page.screenshot(path=str(shot_base) + "_05_paste_result.png")
            print(f"[INFO] 스크린샷 저장: {shot_base}_05_paste_result.png")

        # 최종 본문 상태 스크린샷
        await page.screenshot(path=str(shot_base) + "_final.png")
        print(f"[INFO] 최종 스크린샷: {shot_base}_final.png")

        # 임시저장 (발행 없음)
        if mode == "blog":
            save_selectors = ["button.save_btn__bzc5B", 'button[data-click-area="tpb.save"]', 'button:has-text("저장")']
        else:
            save_selectors = ["button.btn_temp_save", 'button:has-text("임시등록")', 'button:has-text("임시저장")']

        save_loc = None
        for sel in save_selectors:
            loc = page.locator(sel).first
            try:
                if await loc.count() > 0:
                    save_loc = loc
                    break
            except Exception:
                continue

        if save_loc:
            await save_loc.click(force=True)
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(shot_base) + "_saved.png")
            print(f"[INFO] 임시저장 완료 — 스크린샷: {shot_base}_saved.png")
        else:
            print("[WARN] 임시저장 버튼 미발견 — 저장 생략")

        # ─────────────────────────────────────────────
        # PoC 결과 요약
        # ─────────────────────────────────────────────
        print()
        print("=" * 60)
        print("[PoC 결과 요약]")
        print(f"  모드:         {mode}")
        print(f"  삽입 URL:     {cta_url}")
        print(f"  방법 A (툴바 링크 버튼): {'성공' if method_a_success else '실패'}")
        print(f"  방법 B (URL 붙여넣기):   {'성공' if method_b_success else '실패'}")
        if method_a_success or method_b_success:
            thumb_cnt = await scope.evaluate(
                "() => document.querySelectorAll('.se-oglink-thumbnail img, .se-module-oglink img').length"
            )
            print(f"  og:image 썸네일 img:   {'있음' if thumb_cnt > 0 else '없음'} ({thumb_cnt}개)")
        print(f"  스크린샷 위치: {EVIDENCE_DIR}")
        print("=" * 60)

        return 0

    except Exception as e:
        await page.screenshot(path=str(shot_base) + "_error.png")
        print(f"[ERROR] PoC 실패: {e}")
        return 7
    finally:
        await context.close()
        await p.stop()


def parse_args():
    parser = argparse.ArgumentParser(description="SmartEditor 링크 카드 삽입 PoC")
    parser.add_argument("--mode", choices=["blog", "cafe"], default="blog", help="블로그 또는 카페")
    parser.add_argument("--url", default=DEFAULT_CTA_URL, help=f"삽입할 CTA URL (기본: {DEFAULT_CTA_URL})")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(run_poc(args.mode, args.url)))
