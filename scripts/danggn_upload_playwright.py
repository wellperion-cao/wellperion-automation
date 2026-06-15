# scripts/danggn_upload_playwright.py
# v0.1 — 당근 비즈프로필 반자동 업로더 스캐폴드
#         (네이버 발행기 패턴 차용: Playwright + Persistent Profile 1회 로그인 세션)
#
# 🔁 2026-06-03 재시도 — 쿠키 기반 세션 판정으로 개편 (GM 재시도 결재).
#    1차 실패 원인 추정: URL 안착만으로 세션 판정 → OAuth 경유 URL을 오판해 반쪽 세션 저장.
#    개편: setup이 '비즈홈 안착 + 실제 인증 쿠키 보유'까지 확인하고, 쿠키 이름(값 비공개) 덤프.
#    검증: --mode check 로 브라우저 재시작 후 세션 유지 여부 실측 → 유지 시 반자동, 미유지 시 B안(수동) 확정.
#
# 정책: setup(로그인 세션 저장) + draft(글쓰기·이미지·임시저장) + publish(다음→게시) 구현 완료.
#       에디터 자동입력(draft/publish)·이미지 첨부(file_chooser)·발행 = 2026-06-05 실측 검증.
#       비밀번호 하드코딩 없음. Persistent Profile 세션 재사용. 토큰 stdout 노출 금지.
#
# 사전 설치 (GM 로컬 1회):
#   python -m venv .venv ; .venv\Scripts\activate
#   pip install playwright ; playwright install chromium
#
# 모드:
#   setup  : 최초 1회 GM 수동 로그인 → Persistent Profile 세션 저장 (Enter 불필요·자동 감지)
#   dryrun : 브라우저/로그인 없이 본문 조립·이미지 수집·경로·모드 가드 점검만 (기본)
#   draft  : 글쓰기(제목·본문·이미지 자동입력) → 임시저장
#   publish: 실 발행(다음→게시) — GM go 가드(--i-am-sure 또는 WELLPERION_PUBLISH_GO=1) 통과 전제
#
# 실행 예:
#   python scripts\danggn_upload_playwright.py --mode setup
#   python scripts\danggn_upload_playwright.py --mode dryrun ^
#       --content-dir "instagram\260426_WJO_스쿼시_대회"

import argparse
import os
import re
import sys
from pathlib import Path

# UTM 딱지 헬퍼 — 본문 문의 CTA URL에 채널 출처 부착 (scripts/ 동일 디렉터리)
try:
    from cta_utm import apply_cta_utm
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from cta_utm import apply_cta_utm

# Windows 콘솔(cp949)에서 한글·em-dash 출력 깨짐 방지 — UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# -----------------------------------------------------------------
# 상수
# -----------------------------------------------------------------
ROOT = Path(r"C:\Users\jjky0\welperion-automation")
PERSISTENT_PROFILE_DIR = ROOT / "profiles" / "danggn"  # 당근 비즈 로그인 세션
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

# 당근 비즈프로필 관리 홈 (GM 제공 2026-06-03). 미로그인 시 로그인 페이지로 이동한다.
# setup은 이 URL로 goto 후 "로그인 페이지 이탈(bizprofile.daangn.com 안착) + 쿠키 존재"를 세션 시그널로 본다.
DANGGN_BIZ_ACCOUNT_ID = "2769927"  # 웰페리온 당근 비즈계정 ID
DANGGN_BIZ_URL = f"https://bizprofile.daangn.com/biz_accounts/{DANGGN_BIZ_ACCOUNT_ID}/manager/home/"
# 로그인 페이지(미인증 상태) 시그널 — URL 기반
LOGIN_REDIRECT_SIGNALS = ("/login", "accounts.daangn.com", "logon", "auth.daangn.com", "nid.daangn.com")
# 로그인 성공 안착 시그널 — 비즈프로필 도메인으로 돌아옴
SESSION_LANDED_HOST = "bizprofile.daangn.com"
# 인증 쿠키 후보 — 당근/카카오 OAuth 로그인 시 발급되는 영속 인증 쿠키 이름 조각.
# (URL 안착만으론 OAuth 경유 URL을 오판 → 실제 인증 쿠키 보유까지 확인)
AUTH_COOKIE_HINTS = ("session", "sid", "token", "auth", "_kau", "_kawlt", "access", "refresh")

# 콘텐츠 소스 — instagram/{폴더}/output(당근)/ + danggn_copy.md
OUTPUT_SUBDIR_NAME = "output(당근)"
COPY_FILENAME = "danggn_copy.md"
DEFAULT_IMAGE_GLOB = "*.jpg"

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"


def _load_env_val(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드 (python-dotenv 불필요)."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    env_file = ROOT / "telegram_bot" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


TELEGRAM_CHAT_ID: str = _load_env_val(TELEGRAM_CHAT_ID_ENV_KEY)  # telegram_bot/.env SSOT

# publish GM go 가드 (둘 중 하나 충족 시에만 실 발행 허용)
PUBLISH_GO_ENV_KEY = "WELLPERION_PUBLISH_GO"

IMAGE_EXTS = (".jpg", ".jpeg", ".png")


# -----------------------------------------------------------------
# 콘텐츠 조립 — danggn_copy.md (제목/본문 --- 구분) + output(당근)/ 이미지
# -----------------------------------------------------------------
class BizPost:
    __slots__ = ("title", "body", "image_paths")

    def __init__(self, title: str, body: str, image_paths: "list[Path]") -> None:
        self.title = title
        self.body = body
        self.image_paths = image_paths


def parse_copy_file(copy_file: Path) -> "tuple[str, str]":
    """danggn_copy.md 파싱. 첫 '---' 구분선 기준 위=제목 / 아래=본문.
    '---'가 없으면 첫 비어있지 않은 줄=제목, 나머지=본문."""
    text = copy_file.read_text(encoding="utf-8")
    m = re.split(r"(?m)^\s*-{3,}\s*$", text, maxsplit=1)
    if len(m) == 2:
        return m[0].strip(), m[1].strip()
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    title = lines[i].strip() if i < len(lines) else ""
    body = "\n".join(lines[i + 1:]).strip()
    return title, body


def _glob_to_regex(glob: str) -> str:
    out = ["^"]
    for ch in glob:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    out.append("$")
    return "".join(out)


def collect_images(image_dir: "Path | None", image_glob: str) -> "list[Path]":
    """image_dir 내 image_glob 패턴 파일을 정렬 수집. 한글 폴더 정규화 회피 위해 iterdir 사용."""
    if not image_dir or not image_dir.exists():
        return []
    pat = re.compile(_glob_to_regex(image_glob), re.IGNORECASE)
    found: "list[Path]" = []
    for p in sorted(image_dir.iterdir(), key=lambda x: x.name):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and pat.match(p.name):
            found.append(p)
    return found


def _resolve_content_paths(args: argparse.Namespace) -> "tuple[Path | None, Path | None]":
    """--content-dir(instagram/{폴더}) 기준 output(당근)/·danggn_copy.md 경로 산출.
    --image-dir/--body-file 명시 시 그 값을 우선한다."""
    content_dir = Path(args.content_dir) if args.content_dir else None
    if content_dir and not content_dir.is_absolute():
        content_dir = ROOT / content_dir

    if args.image_dir:
        image_dir = Path(args.image_dir)
        if not image_dir.is_absolute():
            image_dir = ROOT / image_dir
    elif content_dir:
        image_dir = content_dir / OUTPUT_SUBDIR_NAME
    else:
        image_dir = None

    if args.body_file:
        copy_file = Path(args.body_file)
        if not copy_file.is_absolute():
            copy_file = ROOT / copy_file
    elif content_dir:
        copy_file = content_dir / COPY_FILENAME
    else:
        copy_file = None

    return image_dir, copy_file


def build_post(args: argparse.Namespace) -> BizPost:
    image_dir, copy_file = _resolve_content_paths(args)
    title = (args.title or "").strip()
    body = ""
    if copy_file and copy_file.exists():
        parsed_title, parsed_body = parse_copy_file(copy_file)
        if not title:
            title = parsed_title
        body = parsed_body
    # 문의 CTA URL에 당근 채널 utm_source 부착 (발행 직전 원본 미변경·중복 안전)
    body = apply_cta_utm(body, "danggn")
    images = collect_images(image_dir, args.image_glob)
    return BizPost(title, body, images)


def validate_post(post: BizPost, require_images: bool) -> "list[str]":
    errs: "list[str]" = []
    if not post.title:
        errs.append("제목 비어 있음 (danggn_copy.md 제목 또는 --title 필요)")
    if not post.body:
        errs.append("본문 비어 있음 (danggn_copy.md 본문 또는 --body-file 필요)")
    if require_images and not post.image_paths:
        errs.append("이미지 0장 (output(당근)/ 또는 --image-dir 확인)")
    return errs


# -----------------------------------------------------------------
# 텔레그램 보고 (토큰 stdout 노출 금지 — feedback_no_token_in_stdout)
# -----------------------------------------------------------------
def telegram_report(message: str) -> None:
    token = os.environ.get(TELEGRAM_TOKEN_ENV_KEY, "").strip()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 보고 생략 (env: TELEGRAM_BOT_TOKEN)")
        return
    try:
        import urllib.parse
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="danggn_upload_playwright.telegram_report", ok=ok, kind="sendMessage")
        print(f"[INFO] 텔레그램 보고 {'성공' if ok else '실패'} (chat={TELEGRAM_CHAT_ID})")
    except Exception:
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="danggn_upload_playwright.telegram_report", ok=False, kind="sendMessage")
        print("[WARN] 텔레그램 보고 실패 (상세 미출력 — 토큰 trace 노출 방지)")


# -----------------------------------------------------------------
# 로그인 세션 판정 (URL 기반)
# -----------------------------------------------------------------
def is_login_required(current_url: str) -> bool:
    return any(sig in current_url for sig in LOGIN_REDIRECT_SIGNALS)


def is_session_landed(current_url: str) -> bool:
    return SESSION_LANDED_HOST in current_url and not is_login_required(current_url)


# -----------------------------------------------------------------
# Google OAuth 로그인 자동 클릭 (2026-06-10 보강)
#   문제: "Google 버튼 자동 클릭 실패" 로그 — 셀렉터 후보 부족.
#   1단계: 당근 로그인 화면의 Google 버튼 클릭.
#   2단계: Google 계정 선택 화면(accounts.google.com)에서
#          'cao@wellperion.com' 계정 + '계속/Continue' 확인 버튼 자동 클릭.
#   기존 '경영지원 계정으로 계속'(Chrome 저장 계정) 케이스도 함께 시도(무회귀).
# -----------------------------------------------------------------
GOOGLE_LOGIN_EMAIL = "cao@wellperion.com"

# 당근 로그인 화면의 'Google 로그인' 진입 버튼 후보
GOOGLE_LOGIN_BUTTON_SELECTORS = [
    'img[alt*="Google"]',
    'button:has-text("Google")',
    'a:has-text("Google")',
    '[aria-label*="Google"]',
    'img[src*="google"]',
    'button:has-text("구글")',
    'a:has-text("구글")',
    '[data-provider="google"]',
    'button[class*="google" i]',
    'a[href*="accounts.google.com"]',
    'a[href*="oauth"][href*="google" i]',
]


def _account_select_selectors() -> "list[str]":
    """Google 계정 선택/확인 화면 자동 클릭 후보(팝업·메인 공용).
    ① 당근측 Chrome 저장 계정 케이스 ② Google '계정 선택' 화면(이메일·이름 행)
    ③ Google '계속/Continue' 확인 버튼 ④ '다른 계정 사용' 회피용 직접 이메일 행."""
    email = GOOGLE_LOGIN_EMAIL
    return [
        # ① 당근/Chrome 저장 계정 케이스 (기존 동작 유지)
        "text=경영지원 계정으로 계속",
        'button:has-text("경영지원")',
        '[role="button"]:has-text("경영지원")',
        "text=계정으로 계속",
        # ② Google '계정 선택' 화면 — 이메일 텍스트가 박힌 행/버튼 직접 클릭
        f'div[role="link"]:has-text("{email}")',
        f'li:has-text("{email}")',
        f'[data-identifier="{email}"]',
        f'[data-email="{email}"]',
        f'div[data-authuser]:has-text("{email}")',
        f'text={email}',
        # ③ Google OAuth '계속'/'Continue' 동의·확인 버튼
        'button:has-text("계속")',
        'button:has-text("Continue")',
        '#submit_approve_access button',
        'button[jsname]:has-text("계속")',
        'div[role="button"]:has-text("계속")',
    ]


async def _click_google_login(page) -> bool:
    """당근 로그인 화면에서 Google 진입 버튼을 자동 클릭. 성공 시 True."""
    import asyncio
    for sel in GOOGLE_LOGIN_BUTTON_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                print(f"[INFO] Google 로그인 버튼 클릭: {sel}")
                await loc.click()
                await asyncio.sleep(4)
                return True
        except Exception:
            continue
    return False


async def _select_google_account(scopes) -> bool:
    """Google 계정 선택/확인 화면에서 cao@wellperion.com 행 또는 '계속' 버튼 자동 클릭.
    scopes = (page, popup) 등 검사 대상 프레임/페이지 목록. 한 곳이라도 클릭하면 True."""
    import asyncio
    for _scope in scopes:
        if _scope is None:
            continue
        for _acc_sel in _account_select_selectors():
            try:
                _loc = _scope.locator(_acc_sel).first
                if await _loc.count() > 0 and await _loc.is_visible():
                    await _loc.click()
                    print(f"[INFO] 계정 자동 선택 클릭: {_acc_sel!r}")
                    await asyncio.sleep(3)
                    return True
            except Exception:
                continue
    return False


def _auth_cookies(cookies) -> "list[str]":
    """인증 쿠키 후보(이름 조각 매칭) 목록 — 값은 절대 반환하지 않고 이름만."""
    names = []
    for c in cookies:
        n = (c.get("name") or "")
        if any(h in n.lower() for h in AUTH_COOKIE_HINTS):
            names.append(n)
    return names


def _dump_cookie_names(cookies) -> None:
    """진단용 — 보유 쿠키 '이름·도메인'만 출력(값 비공개). 인증 쿠키 식별에 사용."""
    if not cookies:
        print("        (쿠키 0개)")
        return
    seen = set()
    for c in cookies:
        key = (c.get("name") or "", c.get("domain") or "")
        if key in seen:
            continue
        seen.add(key)
        mark = " ★auth후보" if any(h in (c.get("name") or "").lower() for h in AUTH_COOKIE_HINTS) else ""
        print(f"        · {c.get('name')}  @{c.get('domain')}{mark}")


# -----------------------------------------------------------------
# dryrun — 브라우저/로그인 없이 본문 조립·이미지·경로·가드 점검
# (playwright import 안 함 — 미설치 환경에서도 실행 가능)
# -----------------------------------------------------------------
def run_dryrun(args: argparse.Namespace) -> int:
    print("[INFO] === 당근 비즈 DRYRUN (브라우저/로그인 없음) ===")
    image_dir, copy_file = _resolve_content_paths(args)
    print(f"[INFO] 카피 파일 : {copy_file or '(미지정)'}"
          + ("" if (copy_file and copy_file.exists()) else "  [부재]"))
    print(f"[INFO] 이미지 폴더: {image_dir or '(미지정)'}"
          + ("" if (image_dir and image_dir.exists()) else "  [부재]"))

    post = build_post(args)
    print(f"[INFO] 제목: {post.title or '(비어 있음)'}")
    print(f"[INFO] 본문 길이: {len(post.body)} chars / 줄수: {post.body.count(chr(10)) + 1 if post.body else 0}")
    if post.body:
        preview = post.body.splitlines()[0][:60]
        print(f"[INFO] 본문 첫줄: {preview}...")
    print(f"[INFO] 이미지 {len(post.image_paths)}장:")
    for p in post.image_paths[:10]:
        print(f"        · {p.name}")
    if len(post.image_paths) > 10:
        print(f"        · ... 외 {len(post.image_paths) - 10}장")

    errs = validate_post(post, require_images=False)
    if errs:
        print("[WARN] 콘텐츠 조립 경고:")
        for e in errs:
            print(f"        · {e}")
    else:
        print("[INFO] 콘텐츠 조립 검증 통과 (제목·본문 OK)")

    print("[INFO] --- 세션·URL 시그널 ---")
    print(f"        비즈 홈     : {DANGGN_BIZ_URL}")
    print(f"        로그인 시그널: {LOGIN_REDIRECT_SIGNALS}")
    print(f"        안착 시그널 : '{SESSION_LANDED_HOST}' 도메인 + 로그인 페이지 이탈")
    print("[INFO] --- 모드 가드 점검 ---")
    print(f"        publish GM go 가드: --i-am-sure 또는 {PUBLISH_GO_ENV_KEY}=1 필요")
    print(f"        현재 --i-am-sure={args.i_am_sure} / env {PUBLISH_GO_ENV_KEY}={os.environ.get(PUBLISH_GO_ENV_KEY, '(unset)')}")
    print("[INFO] draft/publish 자동입력·이미지 첨부·발행 구현됨 — 실행: --mode draft/publish 또는 --mode setup --then-draft/--then-publish")
    print("[INFO] === DRYRUN 완료 (제출·발행 없음) ===")
    return 0


# -----------------------------------------------------------------
# publish GM go 가드
# -----------------------------------------------------------------
def publish_guard_ok(args: argparse.Namespace) -> bool:
    if getattr(args, "i_am_sure", False):
        return True
    if os.environ.get(PUBLISH_GO_ENV_KEY, "").strip() == "1":
        return True
    return False


# -----------------------------------------------------------------
# 브라우저 공통 — playwright lazy import (setup/draft/publish 전용)
# -----------------------------------------------------------------
def _import_playwright():
    try:
        from playwright.async_api import async_playwright  # noqa
        return async_playwright
    except ImportError:
        print("[ERROR] playwright 미설치. .venv 활성화 후 'pip install playwright; playwright install chromium' 필요.")
        sys.exit(10)


async def _launch_context(async_playwright):
    PERSISTENT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(PERSISTENT_PROFILE_DIR),
        headless=False,
        args=["--start-maximized"],
        no_viewport=True,
    )
    return p, context


# -----------------------------------------------------------------
# setup — GM QR 로그인 후 세션 확립 (비밀번호 하드코딩 없음)
#
# 2026-06-04 개편: 당근 비즈 로그인 구조 실측 결과 반영
#   - 당근 비즈 = 모바일 앱 QR 스캔 전용 (business.daangn.com → 팝업 QR)
#   - bizprofile.daangn.com 직접 goto 시 sign-out 유발 → 세션 파괴
#   - 올바른 순서: business.daangn.com/login → 팝업 QR 스캔 → 설정하기 → 팝업 닫힘 → bizprofile 이동
#   - --then-draft 옵션: 로그인 완료 즉시 같은 context로 draft 진행 (세션 보존)
# -----------------------------------------------------------------
async def run_setup(args: "argparse.Namespace | None" = None) -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 당근 비즈 SETUP — Google 로그인 (cao@wellperion.com) ===")
    print(f"[INFO] 프로필 저장: {PERSISTENT_PROFILE_DIR}")
    p, context = await _launch_context(async_playwright)

    # bizprofile.daangn.com 로그인 페이지 직접 진입
    # (실측: business.daangn.com/login → QR전용. bizprofile 로그인 페이지 = Google/카카오/네이버 제공)
    BIZPROFILE_LOGIN = f"https://bizprofile.daangn.com/biz_accounts/{DANGGN_BIZ_ACCOUNT_ID}/manager/home/"
    page = context.pages[0] if context.pages else await context.new_page()

    popup_ref: "dict[str, object]" = {"pg": None}
    def _on_page(pg: object) -> None:
        popup_ref["pg"] = pg
    context.on("page", _on_page)

    await page.goto(BIZPROFILE_LOGIN, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3)

    cur_url = page.url
    print(f"[INFO] 현재 URL: {cur_url}")

    # 이미 로그인된 경우
    if "bizprofile.daangn.com" in cur_url and "/login" not in cur_url and "accounts.daangn.com" not in cur_url:
        print("[INFO] 이미 로그인 상태 — 세션 유효.")
        has_session = True
    else:
        # Google 로그인 버튼 클릭 (실측: 로그인 화면에 Google/카카오/네이버 버튼 존재)
        google_clicked = await _click_google_login(page)

        if not google_clicked:
            # 스크린샷 찍고 GM에게 수동 클릭 안내
            await _screenshot(page, "danggn_setup_login_page.png")
            print("[INFO] Google 버튼 자동 클릭 실패 — 브라우저에서 직접 Google 버튼을 클릭하세요.")
            print(f"[INFO] 스크린샷: {EVIDENCE_DIR / 'danggn_setup_login_page.png'}")
        else:
            print("[INFO] Google OAuth 팝업/리다이렉트 대기 중 — cao@wellperion.com 계정을 선택하세요.")

        print("[INFO] 로그인 완료 후 자동 감지합니다 (최대 10분 대기).")

        # 로그인 완료 대기 루프
        has_session = False
        waited, deadline = 0, 600
        while waited < deadline:
            # 새 팝업(Google OAuth 팝업) 자동 처리 불필요 — GM이 계정 선택
            try:
                cur = page.url
            except Exception:
                break

            # bizprofile 비즈 홈 안착 확인
            if "bizprofile.daangn.com" in cur and "/login" not in cur and "accounts.daangn.com" not in cur:
                has_session = True
                break

            # business.daangn.com 인증 후 bizprofile 이동 시도
            if "business.daangn.com" in cur and "/login" not in cur:
                await page.goto(DANGGN_BIZ_URL, wait_until="networkidle", timeout=20_000)
                await asyncio.sleep(2)
                if "bizprofile.daangn.com" in page.url and "/login" not in page.url:
                    has_session = True
                    break

            # 계정 선택 자동 클릭 — Google 계정 선택(cao@wellperion.com)·'계속' 확인
            # + '경영지원 계정으로 계속'(Chrome 저장 계정) 케이스. (2026-06-10 셀렉터 보강)
            # 못 찾으면 GM 수동 클릭 대기(기존 동작 유지·무회귀).
            # 미클릭 시 Google 버튼이 다시 보이면 재클릭(리다이렉트로 로그인 화면 재진입 케이스).
            if not await _select_google_account((page, popup_ref.get("pg"))):
                if is_login_required(page.url):
                    await _click_google_login(page)

            await asyncio.sleep(3)
            waited += 3
            if waited % 30 == 0:
                print(f"[INFO] 로그인 대기 중... {waited}초 경과 / 현재: {page.url[:80]}")

    if has_session:
        await asyncio.sleep(2)
        print(f"[INFO] 비즈 홈 안착: {page.url}")
        print("[INFO] 당근 비즈 세션 확립 완료")
        await _screenshot(page, "danggn_setup_success.png")
        print("[INFO] --- 보유 쿠키 진단 (이름·도메인만, 값 비공개) ---")
        try:
            _dump_cookie_names(await context.cookies())
        except Exception:
            pass

        # --then-publish: 로그인 직후 발행(게시)까지 (GM go 가드 필요 — 공개 발행)
        then_publish = getattr(args, "then_publish", False)
        if then_publish and args is not None:
            if not publish_guard_ok(args):
                print("[ERROR] publish 거부 — --i-am-sure 또는 WELLPERION_PUBLISH_GO=1 필요(공개 발행).")
                await context.close()
                await p.stop()
                return 9
            print("[INFO] --then-publish: 로그인 완료 즉시 발행(게시) 실행")
            rc = await _run_draft_with_context(page, context, args, publish=True)
            await context.close()
            await p.stop()
            return rc

        # --then-engagement: 로그인 직후 소식 목록 인게이지먼트 수집
        then_engagement = getattr(args, "then_engagement", False)
        if then_engagement and args is not None:
            print("[INFO] --then-engagement: 로그인 완료 즉시 소식 목록 수집")
            rc = await _run_engagement_with_context(page)
            await context.close()
            await p.stop()
            return rc

        # --then-draft: 로그인 성공 즉시 같은 context로 draft 실행
        then_draft = getattr(args, "then_draft", False)
        if then_draft and args is not None:
            print("[INFO] --then-draft: 로그인 완료 즉시 draft 실행")
            rc = await _run_draft_with_context(page, context, args)
            await context.close()
            await p.stop()
            return rc
    else:
        print("[WARN] 10분 내 로그인 미완료 — 다시 실행하세요.")

    await context.close()
    await p.stop()
    print("[INFO] === SETUP 완료 ===")
    if has_session:
        print("[INFO] ★ 원샷 실행(추천): python scripts\\danggn_upload_playwright.py "
              "--mode setup --then-draft --content-dir \"instagram\\260426_WJO_스쿼시_대회\"")
    return 0 if has_session else 2


# -----------------------------------------------------------------
# check — 저장된 세션으로 비즈 홈 접속해 로그인 유지 여부만 확인 (읽기 전용)
# 핵심 검증: 브라우저 재시작 후에도 세션이 살아있는지 = 반자동 가능 여부 판단
# -----------------------------------------------------------------
async def run_check() -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 당근 비즈 세션 CHECK (읽기 전용) ===")
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, context = await _launch_context(async_playwright)
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(DANGGN_BIZ_URL, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3)
    url = page.url
    cookies = await context.cookies()
    auth_names = _auth_cookies(cookies)
    logged_in = is_session_landed(url) and bool(auth_names)
    print(f"[INFO] 최종 URL: {url}")
    print(f"[INFO] 로그인 페이지 리다이렉트: {is_login_required(url)}")
    print(f"[INFO] 인증 쿠키 후보 {len(auth_names)}종 / 로그인 유지: {logged_in}")
    print("[INFO] --- 보유 쿠키 진단 (이름·도메인만) ---")
    _dump_cookie_names(cookies)
    await context.close()
    await p.stop()
    if logged_in:
        print("[INFO] ✅ 세션 유지됨 — 반자동(draft/publish) 진행 가능.")
    else:
        print("[WARN] ❌ 세션 미유지 — 당근은 영속 세션 불가 → 수동(B안) 확정.")
    return 0 if logged_in else 2


# -----------------------------------------------------------------
# draft — 글쓰기 임시저장
# 당근 비즈 소식 작성 페이지에 진입해 제목·본문·이미지를 자동 입력한다.
# 임시저장 버튼이 없으면 '뒤로가기' 시 자동 임시저장 동작을 활용한다.
#
# 세션 요건: --mode setup 실행 후 QR 로그인이 완료되어
#           bizprofile.daangn.com 세션 쿠키가 Persistent Profile에 저장된 상태.
#
# 진입 경로 (실측 2026-06-04):
#   bizprofile.daangn.com/biz_accounts/{ID}/manager/home/
#   → 사이드바 "소식 작성" 클릭
#   → bizprofile.daangn.com/biz_accounts/{ID}/manager/posts/new
#
# 당근 비즈 글쓰기 UI 구조 (사이드바 확인 + LevelDB remote-config 기반):
#   - 제목: 없음 (소식은 제목 없이 본문만 입력하는 SNS 형식)
#   - 본문: contenteditable div 또는 textarea
#   - 이미지: input[type=file] 또는 label 클릭
#   - 임시저장: 버튼 없음 → '나가기/닫기' 시 자동 임시저장 가능
#   ※ 실제 selector는 세션 확립 후 DOM 실측으로 확정 필요.
# -----------------------------------------------------------------

# 글쓰기 페이지 URL
DANGGN_WRITE_URL = (
    f"https://bizprofile.daangn.com/biz_accounts/{DANGGN_BIZ_ACCOUNT_ID}/manager/posts/new"
)

# 소식 작성 에디터 selector 후보 (실측 전 추론 — 세션 확립 후 재검증 필요)
# 당근 비즈 소식은 SNS 형식: 제목 없음, 본문=contenteditable, 이미지=file input
_BODY_SELECTORS = [
    '[contenteditable="true"]',
    '[role="textbox"]',
    'textarea',
    '[data-testid="post-body"]',
    '[data-testid="body"]',
    '[placeholder]',
]
_FILE_SELECTORS = [
    'input[type="file"]',
    'input[type="file"][accept*="image"]',
]
_SAVE_DRAFT_SELECTORS = [
    'button:has-text("임시저장")',
    'button:has-text("저장")',
    '[data-testid="save-draft"]',
    '[data-testid="draft"]',
]


async def _find_first(page, selectors: "list[str]"):
    """selector 목록을 순서대로 시도해 첫 번째로 count > 0인 Locator를 반환."""
    from playwright.async_api import Locator
    for sel in selectors:
        try:
            loc: Locator = page.locator(sel).first
            if await loc.count() > 0:
                return loc, sel
        except Exception:
            pass
    return None, None


async def _screenshot(page, name: str) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / name
    try:
        await page.screenshot(path=str(path), full_page=True)
        print(f"[INFO] 스크린샷: {path}")
    except Exception as e:
        print(f"[WARN] 스크린샷 실패: {e}")


async def _attach_images_via_file_chooser(page, image_paths: "list[Path]") -> bool:
    """이미지 추가 버튼을 클릭해 file chooser를 열고 이미지를 첨부한다.
    당근 비즈는 input[type=file]이 DOM에 노출되지 않으므로 expect_file_chooser() 방식 사용."""
    import asyncio

    # 이미지 추가 버튼 selector 후보
    # write_page.png 실측: 글쓰기 상단에 카메라 아이콘 + '사진' 라벨 버튼,
    # 하단 툴바에 이미지/갤러리 아이콘 버튼 존재 확인
    image_btn_selectors = [
        # 카메라 위젯 — '0/10' 카운터를 가진 버튼 (실측: 글쓰기 상단 카메라 아이콘 + 0/10)
        'button:has-text("/10")',
        'label:has-text("/10")',
        '[role="button"]:has-text("/10")',
        # 실측 확인: 카메라 아이콘 + '사진' 텍스트 버튼 (글쓰기 상단)
        'button:has-text("사진")',
        # 툴바 이미지 아이콘 버튼들 (하단 3-아이콘 툴바)
        'button[aria-label*="사진"]',
        'button[aria-label*="이미지"]',
        'button[aria-label*="photo"]',
        'button[aria-label*="image"]',
        # label for 패턴
        'label[for*="image"]',
        'label[for*="photo"]',
        'label[for*="file"]',
        # data-testid 패턴
        '[data-testid*="photo"]',
        '[data-testid*="image"]',
        '[data-testid*="media"]',
        # 텍스트 기반 폴백
        'button:has-text("이미지")',
        'button:has-text("갤러리")',
        # 마지막 폴백: DOM에 노출된 file input
        'input[type="file"]',
    ]

    # 버튼 전수 + '/10' 카운터 진단 (카메라 위젯 셀렉터 확보용 — 키워드 미매칭 대비)
    diag = await page.evaluate(r"""() => {
        const buttons = [];
        for (const el of document.querySelectorAll('button, label, [role="button"]')) {
            buttons.push({tag:el.tagName,
                text:(el.innerText||'').trim().substring(0,30),
                cls:(el.className||'').toString().substring(0,55),
                html: el.outerHTML.substring(0,130),
                visible: el.offsetParent !== null});
        }
        const counters = [];
        for (const el of document.querySelectorAll('*')) {
            if (el.childElementCount === 0) {
                const t = (el.innerText||'').trim();
                if (/\d+\s*\/\s*10/.test(t)) counters.push({text:t.substring(0,15),
                    tag:el.tagName, cls:(el.className||'').toString().substring(0,55),
                    parent:(el.parentElement?el.parentElement.outerHTML:'').substring(0,220)});
            }
        }
        return {buttons, counters};
    }""")
    print(f"[INFO] 버튼 {len(diag['buttons'])}개 / '/10' 카운터 {len(diag['counters'])}개:")
    for c in diag['counters']:
        print(f"  [counter] {c['text']!r} <{c['tag']} {c['cls']!r}> parent={c['parent']!r}")
    for b in diag['buttons'][:30]:
        print(f"  [{b['tag']}] text={b['text']!r} cls={b['cls']!r} vis={b['visible']} html={b['html']!r}")

    # input[type=file]이 직접 노출된 경우 set_input_files 우선 시도
    direct_file_inputs = await page.evaluate("""() =>
        Array.from(document.querySelectorAll('input[type=file]')).map(el=>({
            id:el.id||'',accept:el.accept||'',multiple:el.multiple,
            testid:el.getAttribute('data-testid')||'',visible:el.offsetParent!==null}))
    """)
    print(f"[INFO] input[type=file] {len(direct_file_inputs)}개:")
    for fi in direct_file_inputs:
        print(f"  id={fi['id']!r} accept={fi['accept']!r} multiple={fi['multiple']} visible={fi['visible']}")

    if direct_file_inputs:
        try:
            file_loc = page.locator('input[type="file"]').first
            await file_loc.set_input_files([str(img) for img in image_paths])
            print(f"[INFO] input[type=file] 직접 set_input_files {len(image_paths)}장")
            await asyncio.sleep(3)
            return True
        except Exception as e:
            print(f"[WARN] set_input_files 실패: {e}")

    # file chooser 방식: 후보 버튼을 클릭해 file chooser 이벤트를 캐치
    for sel in image_btn_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            print(f"[INFO] file chooser 시도: {sel}")
            async with page.expect_file_chooser(timeout=5_000) as fc_info:
                await loc.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files([str(img) for img in image_paths])
            print(f"[INFO] file chooser 이미지 {len(image_paths)}장 첨부 완료 (selector: {sel})")
            await asyncio.sleep(3)
            return True
        except Exception as e:
            print(f"[WARN] {sel} file chooser 실패: {e}")
            continue

    print("[WARN] 이미지 첨부 버튼 미발견 — 첨부 건너뜀.")
    return False


async def _publish_via_next(page) -> int:
    """발행: '다음' → 설정/확인 화면 → '게시/등록/발행' 클릭. 화면 진단 포함(첫 구현 실측용).
    버튼 못 찾으면 발행 안 하고 7 반환(안전 — 공개 오발행 방지)."""
    import asyncio

    async def _dump(tag):
        btns = await page.evaluate(r"""() => Array.from(document.querySelectorAll('button,[role="button"]'))
            .filter(el => el.offsetParent !== null)
            .map(el => (el.innerText || '').trim().substring(0, 24)).filter(t => t)""")
        print(f"[DIAG/{tag}] 보이는 버튼: " + " | ".join(repr(b) for b in btns))

    await _dump("작성후")
    next_loc, next_sel = await _find_first(page, [
        'button:has-text("다음")', '[role="button"]:has-text("다음")'])
    if not next_loc:
        print("[WARN] '다음' 버튼 미발견 — 발행 중단(안전).")
        await _screenshot(page, "danggn_publish_no_next.png")
        return 7
    print(f"[INFO] '다음' 클릭 ({next_sel})")
    await next_loc.click()
    await asyncio.sleep(3)
    await _screenshot(page, "danggn_publish_step2.png")
    await _dump("다음화면")

    pub_loc, pub_sel = await _find_first(page, [
        'button:has-text("게시하기")', 'button:has-text("등록하기")',
        'button:has-text("게시")', 'button:has-text("등록")',
        'button:has-text("발행")', 'button:has-text("완료")'])
    if not pub_loc:
        print("[WARN] 게시/발행 버튼 미발견 — 발행 미완(위 진단 참고). 안전상 중단.")
        return 7
    btxt = (await pub_loc.evaluate("el => el.innerText || ''")).strip()
    print(f"[INFO] 발행 버튼 클릭: {pub_sel} ({btxt!r})")
    await pub_loc.click()
    await asyncio.sleep(3)
    # 확인 다이얼로그 가능성 처리
    confirm_loc, _csel = await _find_first(page, [
        '[role="dialog"] button:has-text("게시")',
        '[role="dialog"] button:has-text("확인")',
        '[role="dialog"] button:has-text("등록")'])
    if confirm_loc:
        ct = (await confirm_loc.evaluate("el => el.innerText || ''")).strip()
        print(f"[INFO] 확인 다이얼로그 클릭: {ct!r}")
        await confirm_loc.click()
        await asyncio.sleep(3)
    await _screenshot(page, "danggn_publish_done.png")
    print("[INFO] === 발행(게시) 완료 ===")
    return 0


async def _run_draft_with_context(page, context, args: argparse.Namespace, publish: bool = False) -> int:
    """로그인된 page/context를 받아 글쓰기 자동입력 + 임시저장을 수행.
    setup --then-draft 와 run_draft 양쪽에서 재사용."""
    import asyncio

    post = build_post(args)
    print("[INFO] === 당근 비즈 DRAFT (글쓰기 시작) ===")
    print(f"[INFO] 제목: {post.title!r}")
    print(f"[INFO] 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")

    if not post.body:
        print("[ERROR] 본문 없음 — 진행 불가.")
        return 4

    # --- 소식 작성 페이지 진입 ---
    # 직접 URL 진입 (직전 실측에서 작동 확인됨)
    print(f"[INFO] 글쓰기 URL 직접 진입: {DANGGN_WRITE_URL}")
    await page.goto(DANGGN_WRITE_URL, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(3)
    write_page_url = page.url
    print(f"[INFO] 글쓰기 페이지 URL: {write_page_url}")

    if is_login_required(write_page_url):
        print("[ERROR] 글쓰기 페이지 세션 만료. --mode setup --then-draft 로 재실행 필요.")
        await _screenshot(page, "danggn_write_session_expired.png")
        return 5

    await _screenshot(page, "danggn_write_page.png")

    # "작성 중인 소식이 있어요" 다이얼로그 처리 → 새로 쓰기 선택
    await asyncio.sleep(1)
    for new_sel in [
        'button:has-text("새로 쓰기")',
        '[role="dialog"] button:has-text("새로")',
        'button:has-text("새로쓰기")',
    ]:
        loc = page.locator(new_sel).first
        if await loc.count() > 0:
            print(f"[INFO] 기존 임시저장 다이얼로그 → '새로 쓰기' 클릭 ({new_sel})")
            await loc.click()
            await asyncio.sleep(2)
            break

    # DOM 실측 출력 (진단용)
    inputs = await page.evaluate("""() => {
        const SELS=['input','textarea','[contenteditable="true"]','[contenteditable=""]','[role="textbox"]'];
        const seen=new Set(), result=[];
        for(const s of SELS) for(const el of document.querySelectorAll(s)){
            if(seen.has(el))continue; seen.add(el);
            result.push({tag:el.tagName,type:el.type||'',id:el.id||'',
                ph:(el.placeholder||el.getAttribute('placeholder')||'').substring(0,40),
                ce:el.contentEditable||'',role:el.getAttribute('role')||'',
                aria:(el.getAttribute('aria-label')||'').substring(0,40),
                testid:el.getAttribute('data-testid')||'',visible:el.offsetParent!==null});
        }
        return result;
    }""")
    print(f"[INFO] 입력 요소 {len(inputs)}개:")
    for el in inputs:
        print(f"  [{el['tag']}] id={el['id']!r} ph={el['ph']!r} ce={el['ce']!r} "
              f"role={el['role']!r} aria={el['aria']!r} testid={el['testid']!r} visible={el['visible']}")

    # ① 제목 입력 — id='title-input' (직전 실측 확인됨)
    title_input = False
    title_loc = page.locator("#title-input").first
    if await title_loc.count() > 0:
        await title_loc.click()
        await asyncio.sleep(0.3)
        await title_loc.fill(post.title)
        print(f"[INFO] 제목 입력 완료 (#title-input): {post.title!r}")
        title_input = True
        await asyncio.sleep(0.5)
    else:
        # placeholder 기반 폴백
        for ph_sel in ['[placeholder="소식 제목"]', 'input[placeholder*="제목"]', '#title']:
            loc = page.locator(ph_sel).first
            if await loc.count() > 0:
                await loc.fill(post.title)
                print(f"[INFO] 제목 입력 완료 ({ph_sel}): {post.title!r}")
                title_input = True
                await asyncio.sleep(0.5)
                break
        if not title_input:
            print("[WARN] 제목 입력 요소 미발견 — 제목 입력 건너뜀.")

    # ② 본문 입력 — contenteditable div (직전 실측 확인됨)
    body_loc, body_sel = await _find_first(page, _BODY_SELECTORS)
    if body_loc is None:
        print("[WARN] 본문 입력 요소 미발견 — DOM 덤프 저장.")
        html = await page.evaluate("() => document.body.innerHTML.substring(0,15000)")
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIR / "danggn_write_dom_nodraft.html").write_text(html, encoding="utf-8")
        print(f"[INFO] DOM 덤프: {EVIDENCE_DIR / 'danggn_write_dom_nodraft.html'}")
        return 6

    print(f"[INFO] 본문 입력 selector: {body_sel}")
    await body_loc.click()
    await asyncio.sleep(0.5)
    ce = await body_loc.evaluate("el => el.contentEditable")
    if ce == "true":
        await body_loc.evaluate("el => el.innerHTML = ''")
        await body_loc.type(post.body, delay=10)
    else:
        await body_loc.fill(post.body)
    print(f"[INFO] 본문 입력 완료 ({len(post.body)} chars)")
    await asyncio.sleep(1)

    await _screenshot(page, "danggn_after_body.png")

    # ③ 이미지 첨부 — file chooser 방식 (input[type=file] DOM 미노출)
    img_attached = False
    if post.image_paths:
        img_attached = await _attach_images_via_file_chooser(page, post.image_paths)
        await _screenshot(page, "danggn_after_image.png")
    else:
        print("[INFO] 이미지 없음 — 첨부 건너뜀.")

    await _screenshot(page, "danggn_after_input.png")

    # ④ 발행(publish=True) — '다음→게시' 흐름 / 아니면 임시저장
    if publish:
        return await _publish_via_next(page)

    # ④ 임시저장
    save_loc, save_sel = await _find_first(page, _SAVE_DRAFT_SELECTORS)
    if save_loc:
        print(f"[INFO] 임시저장 버튼 발견: {save_sel}")
        await save_loc.click()
        await asyncio.sleep(3)
        await _screenshot(page, "danggn_draft_result.png")
        print("[INFO] 임시저장 클릭 완료.")
        result_code = 0
    else:
        print("[INFO] 임시저장 버튼 미발견 — 뒤로가기 후 자동 임시저장 다이얼로그 확인.")
        await page.go_back()
        await asyncio.sleep(3)
        confirm_loc, confirm_sel = await _find_first(page, [
            'button:has-text("임시저장")',
            'button:has-text("저장하고 나가기")',
            'button:has-text("나가기")',
            'button:has-text("확인")',
            '[role="dialog"] button',
        ])
        if confirm_loc:
            print(f"[INFO] 나가기 다이얼로그 발견 ({confirm_sel})")
            await _screenshot(page, "danggn_draft_dialog.png")
            btn_text = await confirm_loc.evaluate("el => el.innerText || ''")
            print(f"[INFO] 다이얼로그 버튼: {btn_text!r}")
            if any(k in btn_text for k in ["임시저장", "저장"]):
                await confirm_loc.click()
                await asyncio.sleep(2)
                print("[INFO] 자동 임시저장 완료.")
                result_code = 0
            else:
                print("[INFO] 임시저장 아님 — 클릭 안 함.")
                result_code = 7
        else:
            print("[INFO] 나가기 다이얼로그 미발견 — 임시저장 미지원 또는 자동 처리.")
            result_code = 7
        await _screenshot(page, "danggn_draft_result.png")

    # ⑤ 저장 후 소식 목록 검증
    POSTS_LIST_URL = (
        f"https://bizprofile.daangn.com/biz_accounts/{DANGGN_BIZ_ACCOUNT_ID}/manager/posts"
    )
    print(f"[INFO] 소식 목록 이동: {POSTS_LIST_URL}")
    await page.goto(POSTS_LIST_URL, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(3)

    # 임시저장 탭/필터가 있으면 클릭 (당근 비즈는 발행됨/임시저장 탭 분리 가능)
    for tab_sel in [
        'button:has-text("임시저장")',
        'a:has-text("임시저장")',
        '[role="tab"]:has-text("임시저장")',
        'button:has-text("저장됨")',
    ]:
        tab_loc = page.locator(tab_sel).first
        if await tab_loc.count() > 0:
            print(f"[INFO] 임시저장 탭 발견 → 클릭: {tab_sel}")
            await tab_loc.click()
            await asyncio.sleep(2)
            break

    await _screenshot(page, "danggn_draft_list.png")

    # 목록에서 임시저장 글 존재 여부 확인 (제목·본문 앞부분·'임시저장' 키워드)
    list_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
    title_kw = post.title[:15] if post.title else ""
    body_kw = post.body[:15] if post.body else ""
    draft_found = any(kw and kw in list_text for kw in ["임시저장", title_kw, body_kw])
    print(f"[INFO] 소식 목록 URL: {page.url}")
    print(f"[INFO] 임시저장 글 목록 확인: {'발견' if draft_found else '미확인'}")
    print(f"[INFO] 탐색 키워드: {[title_kw, body_kw, '임시저장']}")
    print(f"[INFO] 목록 스크린샷: {EVIDENCE_DIR / 'danggn_draft_list.png'}")

    if result_code == 0:
        print("[INFO] DRAFT 완료.")
        msg = (
            f"[당근비즈] 소식 임시저장 완료\n"
            f"제목: {post.title[:30]}\n"
            f"본문: {post.body[:40]}...\n"
            f"이미지: {len(post.image_paths)}장 / 첨부: {'성공' if img_attached else '실패'}\n"
            f"목록 확인: {'발견' if draft_found else '미확인'}"
        )
        telegram_report(msg)
    elif result_code == 7:
        print("[WARN] 임시저장 미확인 — 당근 비즈 소식 에디터 임시저장 미지원 가능성 있음.")

    # 요약 보고
    print("\n[REPORT] ===== 당근 비즈 DRAFT 결과 =====")
    print(f"  ① 제목 입력   : {'성공' if title_input else '실패/건너뜀'} — {post.title!r}")
    print(f"  ② 이미지 첨부 : {'성공' if img_attached else '실패/건너뜀'} — {len(post.image_paths)}장")
    print(f"  ③ 임시저장    : {'완료' if result_code == 0 else '미확인(코드=' + str(result_code) + ')'}")
    print(f"  ④ 목록 검증   : {'발견' if draft_found else '미확인'}")
    print(f"  ⑤ 스크린샷    : {EVIDENCE_DIR}/danggn_draft_list.png")
    print("[REPORT] ===============================\n")

    return result_code


async def _try_auto_relogin(page, context) -> bool:
    """세션 만료 감지 시 '경영지원 계정으로 계속' 버튼 자동 클릭으로 무개입 재로그인 시도.
    성공(bizprofile 안착)이면 True, 실패이면 False 반환.
    headful(headless=False) 환경 전제 — headless에서는 Google 계정 선택 화면이 다를 수 있음.
    GM이 'cao@wellperion.com 경영지원' 계정을 Chrome에 기억해둔 상태 전제."""
    import asyncio

    print("[INFO] 세션 만료 감지 — '경영지원 계정으로 계속' 자동 클릭 시도")
    popup_ref: "dict[str, object]" = {"pg": None}

    def _on_page(pg: object) -> None:
        popup_ref["pg"] = pg
    context.on("page", _on_page)

    # 비즈 홈으로 이동하면 로그인 페이지로 리다이렉트됨 — 여기서 Google 버튼 자동 클릭
    await _click_google_login(page)

    # Google 계정 선택(cao@wellperion.com)·'계속' 확인 자동 클릭 (팝업·메인 양쪽, 셀렉터 보강 2026-06-10)
    deadline, waited = 60, 0
    while waited < deadline:
        await _select_google_account((page, popup_ref.get("pg")))
        # 로그인 화면으로 되돌아온 경우 Google 버튼 재클릭
        if is_login_required(page.url):
            await _click_google_login(page)

        cur = page.url
        if "bizprofile.daangn.com" in cur and "/login" not in cur and "accounts.daangn.com" not in cur:
            print(f"[INFO] 자동 재로그인 성공: {cur}")
            return True

        await asyncio.sleep(3)
        waited += 3

    print("[WARN] 자동 재로그인 60초 내 미완료 — QR 로그인(--mode setup) 필요.")
    return False


async def run_draft(args: argparse.Namespace) -> int:
    import asyncio

    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3

    post = build_post(args)
    errs = validate_post(post, require_images=False)
    print("[INFO] === 당근 비즈 DRAFT ===")
    print(f"[INFO] 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")
    if errs:
        for e in errs:
            print(f"[WARN] {e}")
        if not post.body:
            print("[ERROR] 본문 없음 — 진행 불가.")
            return 4

    async_playwright = _import_playwright()
    p, context = await _launch_context(async_playwright)
    page = context.pages[0] if context.pages else await context.new_page()

    # 비즈 홈 세션 확인
    print(f"[INFO] 비즈 홈 접속: {DANGGN_BIZ_URL}")
    await page.goto(DANGGN_BIZ_URL, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(3)
    home_url = page.url

    if is_login_required(home_url):
        print("[INFO] 세션 만료 — 자동 재로그인 시도 ('경영지원 계정으로 계속' 자동 클릭)")
        await _screenshot(page, "danggn_session_expired.png")
        relogin_ok = await _try_auto_relogin(page, context)
        if not relogin_ok:
            print("[ERROR] 자동 재로그인 실패 — --mode setup --then-draft 로 QR 로그인 필요.")
            await context.close()
            await p.stop()
            return 5
        home_url = page.url

    print(f"[INFO] 비즈 홈 안착: {home_url}")
    await _screenshot(page, "danggn_biz_home_draft.png")

    rc = await _run_draft_with_context(page, context, args)

    # --keep-open: 핸드오프 대기 — GM이 같은 브라우저에서 이미지 첨부 후 발행
    if getattr(args, "keep_open", False):
        _, copy_file = _resolve_content_paths(args)
        post_for_msg = build_post(args)
        # 이미지 경로 안내: output(당근)/ 폴더 기준
        image_dir, _ = _resolve_content_paths(args)
        img_hint = ""
        if image_dir and image_dir.exists():
            imgs = collect_images(image_dir, args.image_glob)
            if imgs:
                first_name = imgs[0].name
                last_name = imgs[-1].name
                count = len(imgs)
                img_hint = (
                    f"{image_dir / first_name} ~ {last_name} ({count}장)"
                )
        if not img_hint and image_dir:
            img_hint = str(image_dir)

        HANDOFF_WAIT_SEC = 900  # 15분
        print(
            "\n[HAND-OFF] 글·임시저장 완료. "
            "이제 이 브라우저에서 "
            f"① 이미지 5장({img_hint})을 끌어넣고 "
            "② 발행 버튼을 누르세요. "
            f"(완료까지 최대 {HANDOFF_WAIT_SEC // 60}분 브라우저 유지)\n"
        )
        await asyncio.sleep(HANDOFF_WAIT_SEC)
    else:
        await asyncio.sleep(2)

    await context.close()
    await p.stop()
    return rc


# -----------------------------------------------------------------
# publish — 실 발행(글쓰기·이미지·다음→게시). GM go 가드 통과 시에만.
# -----------------------------------------------------------------
async def run_publish(args: argparse.Namespace) -> int:
    import asyncio

    if not publish_guard_ok(args):
        print("[ERROR] publish 거부 — GM go 가드 미충족.")
        print(f"        실 발행하려면 --i-am-sure 플래그 또는 {PUBLISH_GO_ENV_KEY}=1 환경변수 필요.")
        return 9
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3

    post = build_post(args)
    errs = validate_post(post, require_images=False)
    print("[INFO] === 당근 비즈 PUBLISH (GM go 가드 통과) ===")
    print(f"[INFO] 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")
    if errs:
        for e in errs:
            print(f"[WARN] {e}")
        if not post.body:
            print("[ERROR] 본문 없음 — 진행 불가.")
            return 4

    async_playwright = _import_playwright()
    p, context = await _launch_context(async_playwright)
    page = context.pages[0] if context.pages else await context.new_page()

    print(f"[INFO] 비즈 홈 접속: {DANGGN_BIZ_URL}")
    await page.goto(DANGGN_BIZ_URL, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(3)
    home_url = page.url

    if is_login_required(home_url):
        print("[INFO] 세션 만료 — 자동 재로그인 시도 ('경영지원 계정으로 계속' 자동 클릭)")
        await _screenshot(page, "danggn_session_expired.png")
        relogin_ok = await _try_auto_relogin(page, context)
        if not relogin_ok:
            print("[ERROR] 자동 재로그인 실패 — --mode setup --then-publish 로 QR 로그인 필요.")
            await context.close()
            await p.stop()
            return 5
        home_url = page.url

    print(f"[INFO] 비즈 홈 안착: {home_url}")
    rc = await _run_draft_with_context(page, context, args, publish=True)

    await asyncio.sleep(2)
    await context.close()
    await p.stop()
    return rc


# -----------------------------------------------------------------
# engagement — 소식 목록 인게이지먼트(조회·관심·댓글) 수집 → JSON 스냅샷
# -----------------------------------------------------------------
async def run_engagement(args: "argparse.Namespace | None" = None) -> int:
    async_playwright = _import_playwright()
    print("[INFO] === 당근 인게이지먼트 수집 (소식 목록 조회·관심·댓글) ===")
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    p, context = await _launch_context(async_playwright)
    page = context.pages[0] if context.pages else await context.new_page()
    rc = await _run_engagement_with_context(page)
    await context.close()
    await p.stop()
    return rc


async def _run_engagement_with_context(page) -> int:
    """로그인된 page로 소식 목록 스크랩 → 스냅샷 JSON. setup --then-engagement 와 공용(닫기는 호출측)."""
    import asyncio
    import json
    import datetime
    posts_url = f"https://bizprofile.daangn.com/biz_accounts/{DANGGN_BIZ_ACCOUNT_ID}/manager/posts"
    print(f"[INFO] 소식 목록 접속: {posts_url}")
    await page.goto(posts_url, wait_until="networkidle", timeout=30_000)
    await asyncio.sleep(3)
    if is_login_required(page.url):
        print("[ERROR] 세션 만료 — setup --then-engagement 로 로그인 후 수집 필요.")
        await _screenshot(page, "danggn_engagement_session_expired.png")
        return 5
    await _screenshot(page, "danggn_engagement_list.png")

    # 소식 목록 행 추출 — 당근 글은 클릭 시 '모달'이라 앵커가 없음 → 날짜 패턴(YYYY.MM.DD HH:MM)을
    # 행 앵커로, 날짜 뒤 숫자 4개 = 조회/재밌/관심/댓글 (실측 스크린샷 2026-06-05 기준).
    rows = await page.evaluate(r"""() => {
        const dateRe = /\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}/;
        const numRe = /(?<!\d)\d[\d,]*(?!\d)/g;
        const leaves = Array.from(document.querySelectorAll('div,span,p,td,li'))
            .filter(el => el.children.length === 0 && dateRe.test(el.textContent || ''));
        const out = []; const seen = new Set();
        leaves.forEach(dl => {
            let row = dl;
            for (let i = 0; i < 7 && row.parentElement; i++) {
                row = row.parentElement;
                const tt = row.innerText || '';
                const dmx = tt.match(dateRe);
                const aft = dmx ? tt.slice(tt.indexOf(dmx[0]) + dmx[0].length) : '';
                if ((aft.match(numRe) || []).length >= 4) break;
            }
            if (seen.has(row)) return; seen.add(row);
            const t = (row.innerText || '').trim();
            const dm = t.match(dateRe);
            if (!dm) return;
            let title = '';
            t.split('\n').map(s => s.trim()).filter(Boolean).forEach(ln => {
                if (!dateRe.test(ln) && !/^\d[\d,]*$/.test(ln)
                    && !/^(광고하기|운영불가|잔액없음|광고|>)$/.test(ln)
                    && ln.length > title.length) title = ln;
            });
            const after = t.slice(t.indexOf(dm[0]) + dm[0].length);
            const m = (after.match(numRe) || []).map(s => parseInt(s.replace(/,/g, ''), 10));
            out.push({ title: title.substring(0, 80), date: dm[0],
                       views: m[0] || 0, fun: m[1] || 0, interest: m[2] || 0, comments: m[3] || 0,
                       rowText: t.replace(/\s+/g, ' ').substring(0, 160) });
        });
        return out;
    }""")
    print(f"[INFO] 추출 행 {len(rows)}개:")
    for r in rows[:12]:
        print(f"  · {r.get('title','')[:34]!r} 조회{r.get('views')} 관심{r.get('interest')} 댓글{r.get('comments')} ({r.get('date')})")

    eng_dir = ROOT / "3. 웰페리온 가이드" / "cmo" / "funnel" / "engagement"
    eng_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snap_path = eng_dir / "danggn_snapshot.json"
    feed_path = eng_dir / "engagement_feed.json"

    # 0건이면 셀렉터가 빗나간 것 → 본문 텍스트 덤프(다음 실행 확정용) 후 종료
    if not rows:
        dump = await page.evaluate("() => document.body.innerText.substring(0, 4000)")
        (eng_dir / "danggn_posts_dump.txt").write_text(dump, encoding="utf-8")
        print(f"[WARN] 0건 — 본문 덤프 저장(셀렉터 확정용): {eng_dir / 'danggn_posts_dump.txt'}")
        return 7

    # 이전 스냅샷 대비 delta → '최근 변동사항' 피드 이벤트
    prev = {}
    if snap_path.exists():
        try:
            for p_ in json.loads(snap_path.read_text(encoding="utf-8")).get("posts", []):
                prev[p_.get("title", "")] = p_
        except Exception:
            pass
    events = []
    for r in rows:
        o = prev.get(r["title"])
        dv = r["views"] - (o["views"] if o else 0)
        di = r["interest"] - (o["interest"] if o else 0)
        dc = r["comments"] - (o["comments"] if o else 0)
        if o is None or dv or di or dc:
            events.append({"collected_at": ts, "channel": "당근", "title": r["title"],
                           "views": r["views"], "interest": r["interest"], "comments": r["comments"],
                           "dViews": dv, "dInterest": di, "dComments": dc, "isNew": o is None})

    feed = []
    if feed_path.exists():
        try:
            feed = json.loads(feed_path.read_text(encoding="utf-8")).get("events", [])
        except Exception:
            feed = []
    feed = (events + feed)[:60]
    feed_path.write_text(json.dumps({"updated_at": ts, "events": feed}, ensure_ascii=False, indent=2), encoding="utf-8")

    snap = {"channel": "당근", "collected_at": ts, "count": len(rows), "posts": rows}
    snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 스냅샷 {len(rows)}건 / 변동 이벤트 {len(events)}건 → 피드 {len(feed)}건")
    return 0


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CMO — 당근 비즈프로필 반자동 업로더 v0.2 (setup·dryrun·draft·publish 구현)"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "check", "dryrun", "draft", "publish", "engagement"],
        default="dryrun",
        help=(
            "setup: GM 수동 로그인 세션 저장 / "
            "check: 저장 세션 유지 여부 검증(읽기 전용) / "
            "dryrun: 브라우저 없이 본문·이미지·경로·가드 점검 (기본) / "
            "draft: 글쓰기+이미지+임시저장 / "
            "publish: 실 발행(다음→게시) (--i-am-sure 또는 WELLPERION_PUBLISH_GO=1 필요)"
        ),
    )
    parser.add_argument("--content-dir", dest="content_dir", default=None,
                        help="콘텐츠 폴더 (instagram/{폴더}) — output(당근)/·danggn_copy.md 자동 산출")
    parser.add_argument("--title", default=None, help="글 제목 (미지정 시 danggn_copy.md 제목 사용)")
    parser.add_argument("--body-file", dest="body_file", default=None,
                        help="카피 파일 경로 (미지정 시 content-dir/danggn_copy.md)")
    parser.add_argument("--image-dir", dest="image_dir", default=None,
                        help="이미지 폴더 (미지정 시 content-dir/output(당근))")
    parser.add_argument("--image-glob", dest="image_glob", default=DEFAULT_IMAGE_GLOB, help="이미지 파일명 패턴")
    parser.add_argument(
        "--i-am-sure", dest="i_am_sure", action="store_true",
        help="publish 모드 GM go 가드 해제 플래그 (실 발행)",
    )
    parser.add_argument(
        "--then-draft", dest="then_draft", action="store_true",
        help="setup 완료 직후 같은 세션으로 draft 실행 (QR 로그인 + draft 원샷)",
    )
    parser.add_argument(
        "--then-publish", dest="then_publish", action="store_true",
        help="setup 완료 직후 같은 세션으로 발행(게시)까지 (로그인+발행 원샷, --i-am-sure 필요)",
    )
    parser.add_argument(
        "--then-engagement", dest="then_engagement", action="store_true",
        help="setup 완료 직후 같은 세션으로 소식 목록 인게이지먼트(조회·관심·댓글) 수집",
    )
    parser.add_argument(
        "--keep-open", dest="keep_open", action="store_true",
        help=(
            "draft 완료 후 브라우저를 닫지 않고 15분 유지. "
            "GM이 같은 창에서 이미지를 끌어넣고 발행할 수 있도록 핸드오프 대기. "
            "(백그라운드 실행 — stdin 없음, asyncio.sleep 방식)"
        ),
    )
    return parser.parse_args()


def main() -> int:
    import asyncio
    args = parse_args()
    if args.mode == "dryrun":
        return run_dryrun(args)
    if args.mode == "setup":
        return asyncio.run(run_setup(args))
    if args.mode == "check":
        return asyncio.run(run_check())
    if args.mode == "draft":
        return asyncio.run(run_draft(args))
    if args.mode == "publish":
        return asyncio.run(run_publish(args))
    if args.mode == "engagement":
        return asyncio.run(run_engagement(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
