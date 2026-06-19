# scripts/verify_live.py
# 전 C-Level 공용 자동 라이브 검수 도구 — 시크릿(clean) 컨텍스트 + 캡처
#
# 사용법:
#   python scripts/verify_live.py <URL> [--expect "텍스트"] [--out 경로] [--show] [--timeout 30]
#
# 예시:
#   python scripts/verify_live.py "https://wellperion-cao.github.io/wellperion-automation/" --expect "웰페리온"
#   python scripts/verify_live.py "https://wellperion-cao.github.io/..." --show --out my_shot.png
#
# 종료코드: 0=성공(+expect 통과), 1=실패(미도달·expect 불일치·오류)

import argparse
import asyncio
import sys
import unicodedata
import urllib.parse
from datetime import datetime
from pathlib import Path

# Windows stdout UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT / "status" / "verify"


def _nfc_url(url: str) -> str:
    """한글 경로 NFD→NFC 정규화 (GitHub Pages 가짜404 방지)"""
    parsed = urllib.parse.urlparse(url)
    # path 부분만 NFC 정규화 후 percent-encode
    path_decoded = urllib.parse.unquote(parsed.path)
    path_nfc = unicodedata.normalize("NFC", path_decoded)
    path_encoded = urllib.parse.quote(path_nfc, safe="/")
    return urllib.parse.urlunparse(parsed._replace(path=path_encoded))


def _bust_cache(url: str) -> str:
    """캐시버스트 쿼리 파라미터 추가"""
    ts = int(datetime.now().timestamp())
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={ts}"


def _default_out_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUT_DIR / f"verify_{ts}.png"


async def run_verify(url: str, expect: str | None, out: Path, show: bool, timeout_s: int) -> int:
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("❌ playwright 미설치 — pip install playwright && playwright install chromium")
        return 1

    url = _nfc_url(url)
    url_with_bust = _bust_cache(url)
    timeout_ms = timeout_s * 1000

    out.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=not show,
                args=["--start-maximized"] if show else [],
            )
        except Exception as e:
            print(f"❌ 브라우저 실행 실패: {e}")
            return 1

        # 시크릿(clean) 컨텍스트 — 쿠키·캐시·로그인 0
        ctx = await browser.new_context(
            ignore_https_errors=True,
            extra_http_headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            viewport={"width": 1400, "height": 900},
        )
        page = await ctx.new_page()

        http_status = None
        final_url = url_with_bust

        # 응답 상태 수집
        async def on_response(response):
            nonlocal http_status, final_url
            if response.url.split("?")[0] == url.split("?")[0]:
                http_status = response.status
                final_url = response.url

        page.on("response", on_response)

        # 페이지 이동
        try:
            await page.goto(url_with_bust, wait_until="networkidle", timeout=timeout_ms)
        except Exception:
            # networkidle 실패 시 load로 재시도
            try:
                await page.goto(url_with_bust, wait_until="load", timeout=timeout_ms)
            except Exception as e:
                print(f"❌ 페이지 도달 실패: {e}")
                await browser.close()
                return 1

        # 페이지 타이틀
        try:
            title = await page.title()
        except Exception:
            title = "(title 없음)"

        # 전체 페이지 스크린샷
        try:
            await page.screenshot(path=str(out), full_page=True)
            screenshot_ok = out.stat().st_size > 0
        except Exception as e:
            print(f"❌ 스크린샷 저장 실패: {e}")
            await browser.close()
            return 1

        # --expect 텍스트 검사
        expect_ok = None
        if expect:
            try:
                content = await page.inner_text("body")
            except Exception:
                content = ""
            expect_ok = expect in content

        await browser.close()

    # 결과 판정
    status_str = str(http_status) if http_status else "응답없음"
    reached = http_status is not None and http_status < 400

    if not reached:
        print(f"❌ 라이브 도달 실패 — HTTP {status_str} | {url}")
        return 1

    overall_ok = True
    if expect is not None and not expect_ok:
        overall_ok = False

    icon = "✅" if overall_ok else "❌"
    print(f"{icon} {url}")
    print(f"   HTTP {status_str} | 제목: {title}")
    if expect is not None:
        expect_icon = "✅" if expect_ok else "❌"
        print(f"   {expect_icon} 텍스트 확인: \"{expect}\"")
    if screenshot_ok:
        print(f"   📸 스크린샷: {out}")
    else:
        print(f"   ⚠️  스크린샷 파일 비어있음: {out}")

    return 0 if overall_ok else 1


def main():
    parser = argparse.ArgumentParser(description="라이브 페이지 자동 검수 (시크릿 크롬)")
    parser.add_argument("url", help="검수할 URL")
    parser.add_argument("--expect", default=None, help="페이지에 반드시 있어야 할 텍스트")
    parser.add_argument("--out", default=None, help="스크린샷 저장 경로 (기본: status/verify/verify_YYYYMMDD_HHMMSS.png)")
    parser.add_argument("--show", action="store_true", help="브라우저 화면 표시 (헤드풀 모드)")
    parser.add_argument("--timeout", type=int, default=30, help="페이지 타임아웃(초, 기본 30)")
    args = parser.parse_args()

    out = Path(args.out) if args.out else _default_out_path()
    code = asyncio.run(run_verify(args.url, args.expect, out, args.show, args.timeout))
    sys.exit(code)


if __name__ == "__main__":
    main()
