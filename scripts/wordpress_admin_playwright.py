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


def main() -> int:
    ap = argparse.ArgumentParser(description="워드프레스 관리자 반자동 (setup/check)")
    ap.add_argument("--mode", choices=["setup", "check"], default="setup")
    args = ap.parse_args()
    if args.mode == "setup":
        return asyncio.run(run_setup())
    return asyncio.run(run_check())


if __name__ == "__main__":
    sys.exit(main())
