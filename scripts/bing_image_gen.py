# scripts/bing_image_gen.py
# v1.0 — Bing Image Creator (무료 AI 그림 생성) 자동화
#         Playwright Persistent Context + headful 패턴 재사용
#         (instagram_upload_playwright.py 의 setup-auto·영속 프로필 패턴 동일)
#
# 무엇을 하나:
#   GM이 한 번 마이크로소프트 계정으로 로그인(setup) → 세션을 profiles/bing/ 에 저장.
#   이후 프롬프트만 넣으면(gen) Bing Image Creator 가 무료로 AI 그림 4장을 만들고,
#   완성 이미지를 instagram/Image/welly_concept/<name>_1..N.png 로 자동 다운로드한다.
#   → 시디(AI CTO)가 무료 AI 그림 생성을 자동화할 수 있다.
#
# 실행 전 사전 설치 (GM님 로컬 PC 1회):
#   cd C:\Users\jjky0\welperion-automation
#   .venv\Scripts\activate  (없으면: python -m venv .venv)
#   pip install playwright
#   playwright install chromium
#
# 실행 방법:
#   1) setup (최초 1회 · GM님 마이크로소프트 로그인):
#        python scripts\bing_image_gen.py --mode setup
#      → headful 창이 열림 → 마이크로소프트 계정 로그인 → 로그인 감지 시 자동 저장·종료 (Enter 불필요)
#
#   2) gen (그림 생성 + 다운로드):
#        python scripts\bing_image_gen.py --mode gen --prompt "고양이가 우주를 나는 수채화" --out welly_cat [--count 4]
#      → 결과: instagram/Image/welly_concept/welly_cat_1.png .. welly_cat_4.png
#
# 보안:
#   세션 쿠키 값은 stdout 에 절대 노출하지 않음. profiles/bing/ 은 .gitignore 로 커밋 제외.

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


# -----------------------------------------------------------------
# 콘솔 인코딩 하드닝 — Windows cp949 콘솔에서 대시(—)·이모지 print 시
# UnicodeEncodeError 로 스크립트가 중단되는 사고 방지.
# (instagram_upload_playwright.py 와 동일 패턴)
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
ROOT = Path(r"C:\Users\jjky0\welperion-automation")
BING_CREATE_URL = "https://www.bing.com/images/create"

# Persistent Context 프로필 (Bing 전용) — 인스타 멀티계정 프로필 패턴 동일.
PROFILE_DIR = ROOT / "profiles" / "bing"

# 결과 이미지 저장 경로 (지시 명세)
OUTPUT_DIR = ROOT / "instagram" / "Image" / "welly_concept"

# 증거 스크린샷 (인스타 모듈과 동일 폴더 재사용)
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

# headful 고정 데스크탑 UA (모바일 UA 는 Bing Create UI 비활성 유발 가능 → 데스크탑 고정)
FIXED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 그림 생성 완료까지 최대 대기 (boost 소진 시 느린 생성 대비 — 넉넉히 180s)
GEN_MAX_WAIT_SEC = 180

# 기본 생성 장수 (Bing 은 1회 4장 생성)
DEFAULT_COUNT = 4

# -----------------------------------------------------------------
# 셀렉터 폴백 — Bing Create UI 는 자주 바뀐다 → 후보 여러 개 + 실측 폴백.
# -----------------------------------------------------------------
# 프롬프트 입력칸 후보
PROMPT_INPUT_SELECTORS = [
    "textarea#sb_form_q",
    "input#sb_form_q",
    "#sb_form_q",
    "textarea[name='q']",
    "input[name='q']",
    "textarea[aria-label*='prompt' i]",
    "textarea[placeholder*='prompt' i]",
    "textarea",
]

# "만들기 / Create" 생성 버튼 후보
CREATE_BUTTON_SELECTORS = [
    "a#create_btn_c",
    "#create_btn_c",
    "a#create_btn",
    "#create_btn",
    "button#create_btn",
    "label[for='sb_form_go']",
    "input#sb_form_go",
    "#sb_form_go",
    "button:has-text('만들기')",
    "a:has-text('만들기')",
    "button:has-text('Create')",
    "a:has-text('Create')",
]

# 생성 결과 썸네일(앵커) 후보 — 클릭 시 상세/원본으로 이동
RESULT_LINK_SELECTORS = [
    "a.iusc",
    "div.imgpt a.iusc",
    "div.girr a",
    "div.mimg a",
    "a.single-img-link",
    "a[href*='/images/create/']",
]

# 결과 영역의 이미지 태그 후보 (URL 직접 회수용 폴백)
RESULT_IMG_SELECTORS = [
    "img.mimg",
    "div.imgpt img",
    "div.girr img",
    "img.gir_mmimg",
]

# 미로그인 신호 — 로그인 페이지로 리다이렉트 / 로그인 버튼.
LOGIN_REQUIRED_URL_SIGNALS = [
    "login.live.com",
    "login.microsoftonline.com",
    "account.microsoft.com/auth",
    "/fd/auth/signin",
]
LOGIN_REQUIRED_SELECTORS = [
    "a#id_l",            # Bing 우상단 'Sign in'
    "a[href*='login.live.com']",
    "input[name='loginfmt']",  # MS 로그인 폼 이메일칸
    "#i0116",                  # MS 로그인 이메일 input id
]


# -----------------------------------------------------------------
# 미로그인 판정 — URL 신호 + 화면 셀렉터 실측 (false-negative 보강).
# -----------------------------------------------------------------
def _url_is_login(current_url: str) -> bool:
    return any(sig in current_url for sig in LOGIN_REQUIRED_URL_SIGNALS)


async def detect_login_required(page) -> bool:
    if _url_is_login(page.url):
        return True
    try:
        for sel in LOGIN_REQUIRED_SELECTORS:
            if await page.locator(sel).count() > 0:
                return True
    except Exception:
        pass
    return False


# -----------------------------------------------------------------
# setup 모드 — 최초 1회 GM 마이크로소프트 로그인으로 세션 확보.
# 로그인을 자동 감지해 세션 저장 (Enter 불필요) — instagram setup-auto 패턴 동일.
# -----------------------------------------------------------------
async def run_setup(max_wait_sec: int = 300) -> None:
    print("[INFO] === SETUP 모드 시작 (Bing Image Creator) ===")
    print("[INFO] headful Chrome 창이 열립니다. 마이크로소프트 계정으로 로그인하세요.")
    print("[INFO] 로그인 감지 시 자동으로 세션을 저장하고 종료합니다 (Enter 불필요).")
    print(f"[INFO] 프로필 저장 경로: {PROFILE_DIR}")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(BING_CREATE_URL, wait_until="domcontentloaded", timeout=30_000)

        interval = 5
        waited = 0
        logged_in = False
        while waited < max_wait_sec:
            # 로그인 성공 신호:
            #   (a) create 페이지에서 로그인 요구 셀렉터/URL 이 사라지고
            #   (b) 마이크로소프트 인증 쿠키가 존재.
            cookies = await context.cookies()
            has_auth = any(
                c.get("name") in ("_U", "MUID", "WLSSC", "MSPAuth", "ESTSAUTH", "ESTSAUTHPERSISTENT")
                and c.get("value")
                for c in cookies
            )
            on_create = "bing.com/images/create" in page.url
            if has_auth and on_create and not await detect_login_required(page):
                logged_in = True
                break
            await page.wait_for_timeout(interval * 1000)
            waited += interval
            print(f"[INFO] 로그인 대기 중... ({waited}/{max_wait_sec}s)")

        if logged_in:
            print("[INFO] 로그인 감지 — 세션 저장 완료 (쿠키 값 비공개: ****)")
        else:
            print("[WARN] 제한시간 내 로그인 미감지 — 다시 시도하세요 (--mode setup).")
        await context.close()

    print("[INFO] === SETUP 완료 ===")
    print(f"[INFO] 프로필 저장 위치: {PROFILE_DIR}")
    print("[INFO] 이후 --mode gen 실행 시 이 세션이 자동 사용됩니다.")


# -----------------------------------------------------------------
# 셀렉터 폴백 헬퍼 — 후보 목록 중 첫 매치 locator 반환 (없으면 None).
# -----------------------------------------------------------------
async def _first_match(page, selectors: list[str], label: str):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                print(f"[INFO]   [{label}] 셀렉터 매치: {sel!r}")
                return loc
        except Exception:
            continue
    return None


# -----------------------------------------------------------------
# 결과 이미지 원본 URL 회수 — 썸네일 말고 큰 해상도 우선.
# Bing 결과 이미지 URL 에는 보통 &w=&h=&c= 등 리사이즈 파라미터가 붙는다.
# 이를 제거하면 원본에 가까운 해상도를 받을 수 있다(가능한 경우).
# -----------------------------------------------------------------
def _upgrade_image_url(url: str) -> str:
    if not url:
        return url
    # th?id=... 썸네일 프록시면 리사이즈 파라미터(w/h/c/rs/qlt/pid) 제거 시도.
    import re as _re
    upgraded = url
    for param in ("w", "h", "c", "rs", "qlt", "pid", "p"):
        upgraded = _re.sub(rf"([?&]){param}=[^&]*", r"\1", upgraded)
    # 정리: 중복/꼬리 & 정돈
    upgraded = _re.sub(r"[?&]{2,}", "&", upgraded)
    upgraded = upgraded.replace("?&", "?").rstrip("?&")
    return upgraded


async def _collect_result_image_urls(page, count: int) -> list[str]:
    """결과 영역에서 이미지 URL 후보를 회수한다.

    우선순위:
      1) 결과 앵커(a.iusc 등) 의 m 속성(JSON) 안 murl(원본 미디어 URL).
      2) 결과 img 태그의 src/data-src (썸네일 — 원본 업그레이드 시도).
    """
    import json as _json

    urls: list[str] = []

    # 1) a.iusc 류 — m 속성에 {"murl": "<원본>", "turl": "<썸네일>"} JSON.
    for sel in RESULT_LINK_SELECTORS:
        try:
            anchors = page.locator(sel)
            n = await anchors.count()
        except Exception:
            continue
        if n == 0:
            continue
        for i in range(n):
            a = anchors.nth(i)
            murl = None
            try:
                m_attr = await a.get_attribute("m")
                if m_attr:
                    data = _json.loads(m_attr)
                    murl = data.get("murl") or data.get("turl")
            except Exception:
                murl = None
            if not murl:
                # href 폴백
                try:
                    murl = await a.get_attribute("href")
                except Exception:
                    murl = None
            if murl and murl.startswith("http") and murl not in urls:
                urls.append(murl)
        if urls:
            break

    # 2) img 태그 폴백 (앵커에서 못 건졌을 때)
    if not urls:
        for sel in RESULT_IMG_SELECTORS:
            try:
                imgs = page.locator(sel)
                n = await imgs.count()
            except Exception:
                continue
            if n == 0:
                continue
            for i in range(n):
                img = imgs.nth(i)
                src = None
                for attr in ("src", "data-src"):
                    try:
                        v = await img.get_attribute(attr)
                    except Exception:
                        v = None
                    if v and v.startswith("http"):
                        src = v
                        break
                if src:
                    up = _upgrade_image_url(src)
                    if up not in urls:
                        urls.append(up)
            if urls:
                break

    return urls[:count]


# -----------------------------------------------------------------
# gen 모드 — 프롬프트로 그림 생성 + 다운로드.
# -----------------------------------------------------------------
async def run_gen(prompt: str, out_name: str, count: int = DEFAULT_COUNT) -> None:
    if not PROFILE_DIR.exists():
        print(f"[ERROR] 프로필 디렉터리 미존재 ({PROFILE_DIR}). 먼저 --mode setup 으로 로그인하세요.")
        sys.exit(3)

    print("[INFO] === GEN 모드 시작 (Bing Image Creator) ===")
    print(f"[INFO] 프롬프트: {prompt}")
    print(f"[INFO] 출력 이름: {out_name} (최대 {count}장)")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_prefix = EVIDENCE_DIR / f"bing-gen-{out_name}-{timestamp}"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(BING_CREATE_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2500)

        # 미로그인 감지 — 추정 말고 'setup 먼저 필요' 보고.
        if await detect_login_required(page):
            await page.screenshot(path=str(evidence_prefix.with_suffix(".login_required.png")))
            print(
                "[ERROR] 로그인 필요 (화면 실측 — 마이크로소프트 로그인 페이지/버튼 감지). "
                "먼저 'python scripts\\bing_image_gen.py --mode setup' 으로 로그인하세요."
            )
            await context.close()
            sys.exit(2)
        print("[INFO] 세션 유효 확인 완료 (로그인 화면 아님)")

        # 1) 프롬프트 입력칸 채우기
        prompt_box = await _first_match(page, PROMPT_INPUT_SELECTORS, "프롬프트 입력칸")
        if prompt_box is None:
            await page.screenshot(path=str(evidence_prefix.with_suffix(".error_prompt_input.png")))
            print("[ERROR] 프롬프트 입력칸 미발견 — Bing Create UI 변경 가능성 (스크린샷 확인).")
            await context.close()
            sys.exit(4)
        await prompt_box.click()
        await prompt_box.fill("")
        await prompt_box.type(prompt, delay=10)
        print(f"[INFO] 프롬프트 입력 완료 ({len(prompt)} chars)")

        # 2) "만들기 / Create" 클릭
        create_btn = await _first_match(page, CREATE_BUTTON_SELECTORS, "만들기 버튼")
        if create_btn is None:
            # Enter 키 폴백 (입력칸이 form 이면 제출될 수 있음)
            print("[WARN] 만들기 버튼 미발견 — Enter 키 제출 폴백 시도")
            await prompt_box.press("Enter")
        else:
            try:
                await create_btn.click(timeout=8000)
                print("[INFO] 만들기 버튼 클릭")
            except Exception as e:
                print(f"[WARN] 만들기 버튼 클릭 실패({e}) — Enter 키 폴백 시도")
                await prompt_box.press("Enter")

        # 3) 생성 완료까지 대기 — 결과 썸네일 등장 폴링 (boost 소진 시 느림 → 넉넉히).
        print(f"[INFO] 생성 완료 대기 (최대 {GEN_MAX_WAIT_SEC}s) — boost 소진 시 느릴 수 있음")
        result_urls: list[str] = []
        waited = 0
        interval = 3
        while waited < GEN_MAX_WAIT_SEC:
            await page.wait_for_timeout(interval * 1000)
            waited += interval

            # 진행 중 미로그인으로 튕긴 경우(세션 만료) 감지.
            if await detect_login_required(page):
                await page.screenshot(path=str(evidence_prefix.with_suffix(".login_lost.png")))
                print("[ERROR] 생성 중 로그인 페이지로 이탈 — 세션 만료 가능. --mode setup 재실행 필요.")
                await context.close()
                sys.exit(2)

            result_urls = await _collect_result_image_urls(page, count)
            if len(result_urls) >= 1:
                # 4장이 한꺼번에 안 뜰 수 있으니 1회 더 짧게 안정화 대기 후 재수집.
                await page.wait_for_timeout(2500)
                result_urls = await _collect_result_image_urls(page, count)
                print(f"[INFO] 결과 썸네일 감지 — {len(result_urls)}장 (대기 {waited}s)")
                break
            print(f"[INFO] 생성 대기 중... ({waited}/{GEN_MAX_WAIT_SEC}s)")

        await page.screenshot(path=str(evidence_prefix.with_suffix(".result.png")))

        if not result_urls:
            print(
                "[ERROR] 제한시간 내 결과 이미지 미감지 — UI 변경 / boost 초과 지연 / 콘텐츠 차단 가능. "
                "스크린샷 확인 요망."
            )
            await context.close()
            sys.exit(5)

        # 4) 결과 이미지 다운로드 — 브라우저 컨텍스트(세션 쿠키 포함)로 요청.
        saved = await _download_images(context, result_urls, out_name, count)
        await context.close()

    if saved:
        print(f"\n[INFO] === GEN 완료 — {len(saved)}장 저장 ===")
        for path in saved:
            print(f"  {path}")
    else:
        print("[ERROR] 이미지 다운로드 0건 — URL 회수는 됐으나 저장 실패 (스크린샷·로그 확인).")
        sys.exit(6)


async def _download_images(context, urls: list[str], out_name: str, count: int) -> list[Path]:
    """결과 URL 들을 브라우저 request 컨텍스트(세션 쿠키 포함)로 다운로드.

    저장: OUTPUT_DIR/<out_name>_1.png .. _N.png
    Bing 이미지는 jpeg 일 수 있으나 인스타 파이프 호환을 위해 확장자 .png 로 통일 저장
    (지시 명세 — <name>_1..N.png). 바이트는 원본 그대로 기록.
    """
    saved: list[Path] = []
    api_request = context.request
    for idx, url in enumerate(urls[:count], start=1):
        # 썸네일이면 원본 업그레이드 1회 더 시도(이미 murl 이면 변화 없음).
        target_url = url
        try:
            resp = await api_request.get(target_url, timeout=30_000)
            if not resp.ok:
                # 업그레이드 URL 이 깨졌으면 원본 url 재시도
                if target_url != url:
                    resp = await api_request.get(url, timeout=30_000)
            if not resp.ok:
                print(f"[WARN]   이미지 {idx} 다운로드 실패 (HTTP {resp.status})")
                continue
            body = await resp.body()
        except Exception as e:
            print(f"[WARN]   이미지 {idx} 다운로드 예외: {e}")
            continue
        if not body:
            print(f"[WARN]   이미지 {idx} 본문 비어 있음 — 건너뜀")
            continue
        out_path = OUTPUT_DIR / f"{out_name}_{idx}.png"
        try:
            out_path.write_bytes(body)
            saved.append(out_path)
            print(f"[INFO]   이미지 {idx} 저장: {out_path} ({len(body)} bytes)")
        except Exception as e:
            print(f"[WARN]   이미지 {idx} 저장 실패: {e}")
    return saved


# -----------------------------------------------------------------
# 엔트리포인트
# -----------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bing Image Creator (무료 AI 그림 생성) 자동화 — Playwright 영속 프로필"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["setup", "gen"],
        help="setup: 마이크로소프트 로그인(최초 1회) / gen: 프롬프트로 그림 생성·다운로드",
    )
    parser.add_argument("--prompt", default="", help="gen 모드 그림 생성 프롬프트(한국어 가능)")
    parser.add_argument("--out", default="", help="gen 모드 출력 파일 이름 접두어 (예: welly_cat)")
    parser.add_argument(
        "--count", type=int, default=DEFAULT_COUNT, help=f"gen 모드 저장 장수 (기본 {DEFAULT_COUNT})"
    )
    args = parser.parse_args()

    if args.mode == "setup":
        asyncio.run(run_setup())
        return

    # gen
    if not args.prompt.strip():
        print("[ERROR] --prompt 가 필요합니다 (gen 모드).")
        sys.exit(1)
    if not args.out.strip():
        print("[ERROR] --out (출력 이름 접두어) 가 필요합니다 (gen 모드).")
        sys.exit(1)
    count = max(1, min(args.count, 4))  # Bing 1회 최대 4장
    asyncio.run(run_gen(args.prompt.strip(), args.out.strip(), count))


if __name__ == "__main__":
    main()
