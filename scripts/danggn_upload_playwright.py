# scripts/danggn_upload_playwright.py
# v0.1 — 당근 비즈프로필 반자동 업로더 스캐폴드
#         (네이버 발행기 패턴 차용: Playwright + Persistent Profile 1회 로그인 세션)
#
# 정책: 종착지=임시저장(draft). 현 단계 목표 = 로그인 세션 저장(setup) + 골격까지.
#       에디터 자동입력(draft/publish)은 GM 로그인 후 당근 비즈 글쓰기 DOM 실측 후 다음 단계 구현.
#       비밀번호 하드코딩 없음. Persistent Profile 세션 재사용. 토큰 stdout 노출 금지.
#
# 사전 설치 (GM 로컬 1회):
#   python -m venv .venv ; .venv\Scripts\activate
#   pip install playwright ; playwright install chromium
#
# 모드:
#   setup  : 최초 1회 GM 수동 로그인 → Persistent Profile 세션 저장 (Enter 불필요·자동 감지)
#   dryrun : 브라우저/로그인 없이 본문 조립·이미지 수집·경로·모드 가드 점검만 (기본)
#   draft  : [스텁] 글쓰기 → 임시저장 (에디터 자동입력 미구현 — DOM 실측 후 다음 단계)
#   publish: [스텁] 실 발행 — GM go 가드(--i-am-sure 또는 WELLPERION_PUBLISH_GO=1) 통과 전제
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

# 콘텐츠 소스 — instagram/{폴더}/output(당근)/ + danggn_copy.md
OUTPUT_SUBDIR_NAME = "output(당근)"
COPY_FILENAME = "danggn_copy.md"
DEFAULT_IMAGE_GLOB = "*.jpg"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot (CLAUDE.md §3-1)

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
        print(f"[INFO] 텔레그램 보고 {'성공' if ok else '실패'} (chat={TELEGRAM_CHAT_ID})")
    except Exception:
        print("[WARN] 텔레그램 보고 실패 (상세 미출력 — 토큰 trace 노출 방지)")


# -----------------------------------------------------------------
# 로그인 세션 판정 (URL 기반)
# -----------------------------------------------------------------
def is_login_required(current_url: str) -> bool:
    return any(sig in current_url for sig in LOGIN_REDIRECT_SIGNALS)


def is_session_landed(current_url: str) -> bool:
    return SESSION_LANDED_HOST in current_url and not is_login_required(current_url)


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
    print("[INFO] ⚠ draft/publish 에디터 자동입력은 스텁 — GM 로그인 후 당근 비즈 글쓰기 DOM 실측 필요")
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
# setup — GM 수동 로그인 후 세션 저장 (비밀번호 하드코딩 없음)
# 세션 시그널: URL이 biz.daangn.com 안착(로그인 페이지 이탈) + 쿠키 존재
# -----------------------------------------------------------------
async def run_setup() -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 당근 비즈 SETUP — GM 수동 로그인 ===")
    print(f"[INFO] 프로필 저장: {PERSISTENT_PROFILE_DIR}")
    p, context = await _launch_context(async_playwright)
    # 기존(옛 계정) 세션 제거 — 새 로그인만 감지하도록 로그아웃 상태로 시작
    try:
        await context.clear_cookies()
        print("[INFO] 기존 세션 비움 — 새 계정으로 로그인하세요.")
    except Exception as e:
        print(f"[WARN] 기존 세션 비우기 실패(무시): {e}")
    page = await context.new_page()
    await page.goto(DANGGN_BIZ_URL, wait_until="domcontentloaded", timeout=30_000)
    print("[INFO] 브라우저에서 당근 로그인을 완료하세요 — 로그인 감지 시 자동 저장됩니다.")
    print("[INFO] (Enter 불필요. 최대 10분 대기 — OAuth 로그인 시간 여유. 비즈프로필 홈 도달 시 자동 마무리)")

    has_session = False
    waited, deadline = 0, 600  # 초 (당근비즈 OAuth 로그인 여유 — 2026-06-03)
    while waited < deadline:
        try:
            current_url = page.url
            cookies = await context.cookies()
        except Exception:
            break  # 브라우저 창을 GM이 닫음
        # 로그인 페이지를 벗어나 비즈 홈에 안착 + 쿠키 보유 = 세션 성립
        if is_session_landed(current_url) and cookies:
            has_session = True
            break
        await asyncio.sleep(3)
        waited += 3
    if has_session:
        await asyncio.sleep(2)  # 쿠키가 디스크 프로필에 안착할 여유
        print("[INFO] 당근 비즈 세션 확인 — 저장 완료 (값 비공개: ****)")
    else:
        print("[WARN] 5분 내 로그인 미완료(비즈 홈 미안착) — 다시 실행하세요.")
    await context.close()
    await p.stop()
    print("[INFO] === SETUP 완료 ===")
    return 0


# -----------------------------------------------------------------
# draft — [스텁] 글쓰기 임시저장 (에디터 자동입력 미구현)
# 입력 인자(title/body/image)는 build_post로 배선만 해두고, 실제 DOM 자동입력은 다음 단계.
# -----------------------------------------------------------------
async def run_draft(args: argparse.Namespace) -> int:
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    post = build_post(args)
    print("[INFO] === 당근 비즈 DRAFT (스텁) ===")
    print(f"[INFO] 제목: {post.title or '(비어 있음)'} / 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")
    print("[TODO] 당근 비즈 글쓰기 에디터 자동입력 미구현 — GM 로그인(setup) 후 DOM 실측")
    return 0


# -----------------------------------------------------------------
# publish — [스텁] 실 발행. GM go 가드 통과 시에만.
# -----------------------------------------------------------------
async def run_publish(args: argparse.Namespace) -> int:
    if not publish_guard_ok(args):
        print("[ERROR] publish 거부 — GM go 가드 미충족.")
        print(f"        실 발행하려면 --i-am-sure 플래그 또는 {PUBLISH_GO_ENV_KEY}=1 환경변수 필요.")
        return 9
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    post = build_post(args)
    print("[INFO] === 당근 비즈 PUBLISH (스텁·GM go 가드 통과) ===")
    print(f"[INFO] 제목: {post.title or '(비어 있음)'} / 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")
    print("[TODO] 당근 비즈 글쓰기 에디터 자동입력 미구현 — GM 로그인(setup) 후 DOM 실측")
    return 0


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CMO — 당근 비즈프로필 반자동 업로더 v0.1 (setup·dryrun + draft/publish 스텁)"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "dryrun", "draft", "publish"],
        default="dryrun",
        help=(
            "setup: GM 수동 로그인 세션 저장 / "
            "dryrun: 브라우저 없이 본문·이미지·경로·가드 점검 (기본) / "
            "draft: 임시저장 [스텁] / "
            "publish: 실 발행 [스텁] (--i-am-sure 또는 WELLPERION_PUBLISH_GO=1 필요)"
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
    return parser.parse_args()


def main() -> int:
    import asyncio
    args = parse_args()
    if args.mode == "dryrun":
        return run_dryrun(args)
    if args.mode == "setup":
        return asyncio.run(run_setup())
    if args.mode == "draft":
        return asyncio.run(run_draft(args))
    if args.mode == "publish":
        return asyncio.run(run_publish(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
