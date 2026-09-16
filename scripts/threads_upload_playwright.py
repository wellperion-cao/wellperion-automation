# scripts/threads_upload_playwright.py
# v1.0 — Playwright Persistent Context 스레드(Threads) 자동 발행
#         scripts/instagram_upload_playwright.py 구조 복제(시모 배 2694 ③ · GM 지시 2026-09-16)
#
# 실행 전 사전 설치: instagram_upload_playwright.py 와 동일(.venv + playwright install chromium)
#
# 실행 방법:
#   setup (최초 1회 · 사람 수동 로그인 — WP_BROWSER_SHOW=1 로 창 보이게):
#     set WP_BROWSER_SHOW=1 && python scripts\threads_upload_playwright.py --mode setup --account axlabs
#   dryrun (로그인 상태·작성 버튼 셀렉터 확인, 발행 없음):
#     python scripts\threads_upload_playwright.py --mode dryrun --account axlabs
#   publish (실 발행 — 비가역):
#     python scripts\threads_upload_playwright.py --mode publish --account axlabs --text "본문" [--image 경로 ...]
#   self-test (판정 함수만, 브라우저 안 엶):
#     python scripts\threads_upload_playwright.py --self-test
#
# 계정 자동 로그인은 아직 없다 — server/erp_api/sync_parking.py 가 쓰는
# GET /api/partner-secrets/fetch?tenant=ax&channel=threads 자동 로그인은 다음 판(계정 확보 후).
# setup 모드는 사람이 창에서 직접 로그인한다.
#
# 셀렉터(작성 버튼/입력창/게시 버튼)는 로그인 계정이 없어 dryrun 으로 실측하지 못했다 —
# ⚠️미검증 표시된 후보들은 계정 확보 뒤 --mode dryrun 실측으로 갱신 필요.
#
# 결과 확인:
#   %USERPROFILE%\welperion-automation\scripts\poc-evidence\threads-{mode}-{timestamp}.png

from browser_quiet import quiet_args  # 자동화 창은 화면 밖으로(2026-09-15 GM) — setup 도 WP_BROWSER_SHOW=1 로 보이게
import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


# -----------------------------------------------------------------
# 콘솔 인코딩 하드닝 — instagram_upload_playwright.py 와 동일(수정 3 재사용)
# -----------------------------------------------------------------
def _harden_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_harden_console_encoding()


# -----------------------------------------------------------------
# 상수
# -----------------------------------------------------------------
THREADS_HOME_URL = "https://www.threads.com"

PROFILE_BASE = Path.home() / r"welperion-automation\profiles\threads"
DEFAULT_ACCOUNT = "axlabs"
EVIDENCE_DIR = Path.home() / r"welperion-automation\scripts\poc-evidence"

FIXED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

MAX_TEXT_LEN = 500  # 스레드 게시글 한도
BANNED_NAME = "김남욱"  # GM 본명 — 게시문 금지(배 2694 규칙)
BANNED_SALES_PHRASES = ["문의하세요", "도입하세요", "가격", "할인", "지금 신청"]

# 작성(새 스레드) 진입 버튼 — ⚠️미검증(로그인 벽 안 — 계정 확보 뒤 dryrun 실측 필요)
COMPOSE_TRIGGER_SELECTORS = [
    'a[href="/create"]',
    'svg[aria-label="Create"]',
    'svg[aria-label="만들기"]',
    'div[role="button"]:has-text("새 스레드 작성")',
]

# 본문 입력 contenteditable — ⚠️미검증
TEXTBOX_SELECTORS = [
    'div[contenteditable="true"][aria-label*="스레드"]',
    'div[contenteditable="true"][aria-label*="thread" i]',
    'div[role="textbox"][contenteditable="true"]',
    'div[contenteditable="true"]',
]

# 이미지 첨부 input[type=file] — ⚠️미검증
FILE_INPUT_SELECTORS = [
    'input[type="file"]',
]

# "게시" 최종 발행 버튼 — ⚠️미검증
POST_BUTTON_SELECTORS = [
    'div[role="button"]:text-is("게시")',
    'button:text-is("게시")',
    'div[role="button"]:has-text("게시")',
    'button:has-text("Post")',
]

# 게시 완료 확인 문구 — ⚠️미검증
POST_SUCCESS_TEXT_SELECTORS = [
    ':text("스레드가 게시되었습니다")',
    ':text("게시되었습니다")',
    ':text("Your thread was posted")',
]


def get_profile_dir(account: str) -> Path:
    return PROFILE_BASE / account


# -----------------------------------------------------------------
# 판정 함수 — 본문 검사(길이·금지어). 브라우저 열기 전에 먼저 돈다.
# -----------------------------------------------------------------
def validate_text(text: str) -> str | None:
    """차단 사유 문자열 반환(통과면 None). 게시 자체를 막는 단일 관문."""
    if len(text) > MAX_TEXT_LEN:
        return f"본문 {len(text)}자 — 스레드 한도 {MAX_TEXT_LEN}자 초과"
    if BANNED_NAME in text:
        return f"금지 문구 포함: {BANNED_NAME}(GM 본명)"
    for phrase in BANNED_SALES_PHRASES:
        if phrase in text:
            return f"금지 영업 문구 포함: {phrase!r}"
    return None


def _selftest() -> None:
    assert validate_text("오늘 웰페리온 소식입니다") is None, "정상 본문이 차단됨"
    assert validate_text("김남욱 대표가 말한다") is not None, "GM 본명이 안 걸림"
    assert validate_text("지금 신청하세요") is not None, "영업 문구가 안 걸림"
    assert validate_text("가격 문의는 DM으로") is not None, "가격/문의하세요 문구가 안 걸림"
    assert validate_text("가" * MAX_TEXT_LEN) is None, "정확히 500자가 잘못 차단됨"
    assert validate_text("가" * (MAX_TEXT_LEN + 1)) is not None, "501자가 안 걸림"
    print("[OK] selftest 통과 — 길이 한도·GM본명·금지 영업문구 4종 판정 확인")


# -----------------------------------------------------------------
# 로그인 세션 유효성 확인
# -----------------------------------------------------------------
def is_session_expired(current_url: str) -> bool:
    expired_signals = ["threads.com/login", "threads.net/login", "accounts/login", "challenge"]
    return any(signal in current_url for signal in expired_signals)


async def detect_login_required(page) -> bool:
    """로그인 필요 여부 실측 판정. threads.com 은 로그아웃 상태에서도 리다이렉트·비밀번호
    입력창 없이 피드를 보여주고, 「Instagram으로 계속하기」 모달만 얹는다
    (2026-09-16 실측: profiles/threads/axlabs 신규 프로필 dryrun · scripts/poc-evidence/
    threads-dryrun-20260916_172556.png) — URL·password 필드만 보던 첫 판이 이걸 놓쳤다."""
    if is_session_expired(page.url):
        return True
    try:
        if await page.locator('input[name="password"]').count() > 0:
            return True
        if await page.locator(':text("Instagram으로 계속하기")').count() > 0:
            return True
        if await page.locator(':text("로그인 또는 가입하기")').count() > 0:
            return True
    except Exception:
        pass
    return False


# -----------------------------------------------------------------
# setup 모드 — 최초 1회 수동 로그인으로 세션 확보
# WP_BROWSER_SHOW=1 로 실행해야 창이 보인다(quiet_args 기본은 화면 밖 · 2026-09-15 GM 규칙).
# -----------------------------------------------------------------
async def run_setup(account: str = DEFAULT_ACCOUNT) -> None:
    profile_dir = get_profile_dir(account)
    print("[INFO] === SETUP 모드 시작 ===")
    print(f"[INFO] 계정: {account}")
    print(f"[INFO] 프로필 저장 경로: {profile_dir}")
    print("[INFO] 창이 안 보이면 WP_BROWSER_SHOW=1 로 재실행하세요(화면 밖 규칙 — 2026-09-15 GM).")
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            user_agent=FIXED_UA,
            args=[*quiet_args(), "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(THREADS_HOME_URL, wait_until="domcontentloaded", timeout=30_000)

        print("[INFO] 브라우저가 열렸습니다. 스레드에 로그인해 주세요.")
        print("[INFO] 로그인 완료 후 이 터미널에서 Enter 키를 누르세요.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")

        cookies = await context.cookies()
        session_cookies = [c for c in cookies if "threads" in c.get("domain", "") or "instagram" in c.get("domain", "")]
        if session_cookies:
            print(f"[INFO] 세션 쿠키 {len(session_cookies)}개 저장 완료 (값 비공개: ****)")
        else:
            print("[WARN] 세션 쿠키 미감지 — 로그인이 완료되지 않았을 수 있습니다.")

        await context.close()

    print("[INFO] === SETUP 완료 ===")
    print(f"[INFO] 프로필 저장 위치: {profile_dir}")


# -----------------------------------------------------------------
# dryrun 모드 — 로그인 세션 확인 + 작성 버튼 셀렉터 후보 탐색 (발행 안 함)
# -----------------------------------------------------------------
async def _probe_selector_group(page, label: str, selectors: list[str]) -> str | None:
    print(f"[INFO] [{label}] 셀렉터 후보 {len(selectors)}종 탐색")
    matched: str | None = None
    for idx, sel in enumerate(selectors, start=1):
        try:
            count = await page.locator(sel).count()
            status = f"감지 ({count}개)" if count > 0 else "미감지"
            print(f"[INFO]   후보 {idx}: {sel!r} → {status}")
            if count > 0 and matched is None:
                matched = sel
        except Exception as e:
            print(f"[WARN]   후보 {idx} 탐색 오류: {e}")
    if matched:
        print(f"[INFO] [{label}] 유효 셀렉터 확정: {matched!r}")
    else:
        print(f"[WARN] [{label}] 셀렉터 모두 미감지 — 로그인 벽 안이거나 UI 변경")
    return matched


async def run_dryrun(account: str = DEFAULT_ACCOUNT) -> None:
    profile_dir = get_profile_dir(account)
    if not profile_dir.exists():
        print(f"[ERROR] 프로필 디렉터리 미존재 ({profile_dir}). 먼저 --mode setup --account {account} 실행 필요.")
        sys.exit(3)

    print("[INFO] === DRYRUN 모드 시작 ===")
    print(f"[INFO] 계정: {account}")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = EVIDENCE_DIR / f"threads-dryrun-{timestamp}.png"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            user_agent=FIXED_UA,
            args=[*quiet_args(), "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            no_viewport=True,
        )
        page = await context.new_page()
        print(f"[INFO] 스레드 홈 이동 중... → {THREADS_HOME_URL}")
        await page.goto(THREADS_HOME_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2500)

        current_url = page.url
        print(f"[INFO] 현재 URL: {current_url}")

        if await detect_login_required(page):
            print("[WARN] 로그인 필요(화면 실측) — 계정 미확보 상태에서는 정상. --mode setup 필요.")
            await page.screenshot(path=str(screenshot_path), full_page=False)
            print(f"[INFO] 스크린샷 저장 완료: {screenshot_path}")
            await context.close()
            print("[INFO] === DRYRUN 완료(로그인 벽) ===")
            return

        print("[INFO] 로그인 세션 유효 확인 완료")
        await _probe_selector_group(page, "작성(새 스레드) 진입", COMPOSE_TRIGGER_SELECTORS)
        await _probe_selector_group(page, "본문 입력창", TEXTBOX_SELECTORS)
        await _probe_selector_group(page, "이미지 첨부 input", FILE_INPUT_SELECTORS)
        await _probe_selector_group(page, "게시 버튼", POST_BUTTON_SELECTORS)

        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"[INFO] 스크린샷 저장 완료: {screenshot_path}")
        print("[INFO] dryrun 모드 — 게시 버튼 클릭 안 함")
        await context.close()

    print("[INFO] === DRYRUN 완료 ===")


# -----------------------------------------------------------------
# publish 모드 — 텍스트(+이미지) 실 발행. 비가역.
# -----------------------------------------------------------------
async def run_publish(text: str, images: list[Path], account: str = DEFAULT_ACCOUNT) -> str:
    reason = validate_text(text)
    if reason:
        print(f"[BLOCKED] {reason}")
        sys.exit(1)

    profile_dir = get_profile_dir(account)
    if not profile_dir.exists():
        print(f"[ERROR] 프로필 디렉터리 미존재 ({profile_dir}). --mode setup --account {account} 우선 실행 필요.")
        sys.exit(3)

    print(f"[INFO] === PUBLISH 모드 시작 === account={account} images={len(images)}")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_prefix = EVIDENCE_DIR / f"threads-publish-{timestamp}"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            user_agent=FIXED_UA,
            args=[*quiet_args(), "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(THREADS_HOME_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2000)

        if await detect_login_required(page):
            print("[ERROR] 로그인 필요(화면 실측). --mode setup 으로 재로그인 필요.")
            await context.close()
            sys.exit(2)
        print("[INFO] 세션 유효 확인 완료")

        # 작성 진입
        clicked = False
        for sel in COMPOSE_TRIGGER_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=5000)
                    clicked = True
                    print(f"[INFO]   작성 진입 클릭: {sel!r}")
                    break
            except Exception:
                continue
        if not clicked:
            await page.screenshot(path=str(evidence_prefix.with_suffix(".error_compose.png")))
            raise RuntimeError("작성(새 스레드) 진입 셀렉터 모두 실패 — ⚠️미검증 후보, 계정 확보 뒤 실측 갱신 필요")
        await page.wait_for_timeout(1500)

        # 본문 입력
        textbox = None
        for sel in TEXTBOX_SELECTORS:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                textbox = loc
                print(f"[INFO]   본문 입력창: {sel!r}")
                break
        if textbox is None:
            await page.screenshot(path=str(evidence_prefix.with_suffix(".error_textbox.png")))
            raise RuntimeError("본문 입력창 미발견")
        await textbox.click()
        await page.keyboard.type(text, delay=15)
        print(f"[INFO]   본문 입력 완료 ({len(text)} chars)")

        # 이미지 첨부(있으면)
        if images:
            file_input = None
            for sel in FILE_INPUT_SELECTORS:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    file_input = loc
                    break
            if file_input is None:
                await page.screenshot(path=str(evidence_prefix.with_suffix(".error_fileinput.png")))
                raise RuntimeError("이미지 첨부 input[type=file] 미발견")
            await file_input.set_input_files([str(p) for p in images])
            print(f"[INFO]   이미지 첨부 완료 ({len(images)}장)")
            await page.wait_for_timeout(2000)

        await page.screenshot(path=str(evidence_prefix.with_suffix(".pre_post.png")))

        # 게시
        posted = False
        for sel in POST_BUTTON_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=8000)
                    posted = True
                    print(f"[INFO]   게시 클릭: {sel!r}")
                    break
            except Exception:
                continue
        if not posted:
            await page.screenshot(path=str(evidence_prefix.with_suffix(".error_post.png")))
            raise RuntimeError("게시 버튼 클릭 실패 — ⚠️미검증 후보, 계정 확보 뒤 실측 갱신 필요")

        # 완료 확인(최대 30초 폴링) — 못 잡아도 발행 자체는 진행된 것으로 보고, 미확정만 알림
        confirmed = False
        for _ in range(15):
            await page.wait_for_timeout(2000)
            for sel in POST_SUCCESS_TEXT_SELECTORS:
                try:
                    if await page.locator(sel).count() > 0:
                        confirmed = True
                        break
                except Exception:
                    continue
            if confirmed:
                break
        await page.screenshot(path=str(evidence_prefix.with_suffix(".post_share.png")))
        outcome = "발행완료" if confirmed else "확인필요(완료 문구 미확정 — 스크린샷 확인 요망)"
        print(f"[INFO]   결과: {outcome}")

        await context.close()

    print("[INFO] === PUBLISH 완료 ===")
    return outcome


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="웰페리온 AI CMO — 스레드(Threads) Playwright v1.0")
    parser.add_argument("--mode", choices=["setup", "dryrun", "publish"], default="dryrun")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--text", default=None, help="publish 모드 필수: 게시 본문")
    parser.add_argument("--image", action="append", default=[], help="첨부 이미지 경로(여러 번 지정 가능)")
    parser.add_argument("--self-test", action="store_true", help="판정 함수만 assert 로 자가점검(브라우저 안 엶)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.self_test:
        _selftest()
    elif args.mode == "setup":
        asyncio.run(run_setup(account=args.account))
    elif args.mode == "publish":
        if not args.text:
            print("[ERROR] --mode publish 는 --text 인자 필수")
            sys.exit(1)
        asyncio.run(run_publish(args.text, [Path(p) for p in args.image], account=args.account))
    else:
        asyncio.run(run_dryrun(account=args.account))
