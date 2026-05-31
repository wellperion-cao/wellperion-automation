# scripts/naver_blog_upload_playwright.py
# v1.0 — 네이버 블로그 SmartEditor ONE Playwright 업로더 (유실 소스 복원)
#
# 정책: 임시저장(draft)까지만 자동. 실 발행(publish)은 GM go 가드 — 명시 플래그 없으면 거부.
#       비밀번호 하드코딩 없음. Persistent Profile 세션 재사용. 토큰 stdout 노출 금지.
#
# 사전 설치 (GM 로컬 1회):
#   python -m venv .venv ; .venv\Scripts\activate
#   pip install playwright ; playwright install chromium
#
# 모드:
#   setup  : 최초 1회 GM 수동 로그인 → Persistent Profile 세션 저장 (Enter로 저장)
#   dryrun : 브라우저/로그인 없이 본문 조립·이미지 수집·셀렉터·모드 가드 점검만 (기본)
#   draft  : 글쓰기 진입 → 제목·본문·이미지(슬라이드) 입력 → 임시저장까지
#   publish: 실 발행 — GM go 가드(--i-am-sure 또는 WELLPERION_PUBLISH_GO=1) 없으면 거부
#
# 실행 예:
#   python scripts\naver_blog_upload_playwright.py --mode dryrun ^
#       --title "..." --body-file temp\body_blog.txt --image-dir instagram\xxx\output\blog
#   python scripts\naver_blog_upload_playwright.py --mode setup
#   python scripts\naver_blog_upload_playwright.py --mode draft --title "..." --body-file ... --image-dir ...
#
# 셀렉터 출처(evidence): scripts/poc-evidence/naver-blog-imgauto-v2-*, project_smarteditor_auto_attach 메모리
#   제목 .se-title-text / 본문 .se-text-paragraph / 사진버튼 button.se-image-toolbar-button
#   사진첨부방식 모달 .se-popup-image-type → 슬라이드 #image-type-slide
#   임시저장 button.save_btn__bzc5B ≡ button[data-click-area="tpb.save"]
#   ⚠ 임시저장 큐 0건일 때만 본문 lazy load 활성 (project_draft_queue_dependency)

import argparse
import os
import re
import sys
from datetime import datetime
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
PERSISTENT_PROFILE_DIR = ROOT / "profiles" / "naver"
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
# 블로그 글쓰기 진입 — 본인 블로그 ID 기준. 미지정 시 PostWriteForm 일반 진입.
BLOG_WRITE_URL_TEMPLATE = "https://blog.naver.com/{blog_id}/postwrite"
BLOG_WRITE_URL_GENERIC = "https://blog.naver.com/PostWriteForm.naver"

# 로그인 만료 시그널 (URL 기반)
LOGIN_REDIRECT_SIGNALS = ("nid.naver.com/nidlogin", "nid.naver.com/login")

# SmartEditor ONE 셀렉터 (2026-05-21 v3.0 실측 — project_smarteditor_auto_attach)
TITLE_SELECTORS = [
    ".se-title-text",
    "span.__se_placeholder.se-fs32",
    ".se-section-documentTitle .se-text-paragraph",
]
BODY_SELECTORS = [
    ".se-text-paragraph",
    "span.__se_placeholder.se-fs15",
    'div[contenteditable="true"].se-content',
]
IMAGE_TOOLBAR_BUTTON_SELECTORS = [
    "button.se-image-toolbar-button",
    'button[data-name="image"]',
    'button[data-log="image"]',
]
# 사진 첨부 방식 모달 → 슬라이드 옵션 (v3.0 핵심 단계)
IMAGE_TYPE_MODAL_SELECTORS = [".se-popup-image-type", '[data-group="popupLayer"] .se-popup-image-type']
IMAGE_TYPE_SLIDE_SELECTOR = "#image-type-slide"
IMAGE_TYPE_LIST_SELECTOR = "#image-type-list"
# 임시저장 버튼
SAVE_DRAFT_SELECTORS = [
    "button.save_btn__bzc5B",
    'button[data-click-area="tpb.save"]',
    'button:has-text("저장")',
]
# 발행 버튼 (publish 모드에서만 사용 — GM go 가드 통과 시)
PUBLISH_TRIGGER_SELECTORS = [
    'button[data-click-area="tpb.publish"]',
    'button.publish_btn__m9KHH',
    'button:has-text("발행")',
]
PUBLISH_CONFIRM_SELECTORS = [
    'button[data-click-area="tpb.publish"]',
    'div.layer_btn_area button.confirm_btn__WEaBq',
    'button.btn_check:has-text("발행")',
]

# popup killer (project_smarteditor_auto_attach v3.0)
POPUP_KILLER_SELECTORS = (
    ".se-popup-dim, .se-popup-alert, .se-popup-alert-confirm, "
    ".blog-se-alert, .se-help-panel, [data-group='popupLayer']"
)

# 임시저장 큐 카운트 버튼 (큐 누적 진단용 — project_draft_queue_dependency)
DRAFT_QUEUE_BUTTON_SELECTORS = [
    'button[data-click-area="tpb.draft"]',
    'button:has-text("저장")',
]

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot (CLAUDE.md §3-1)

# publish GM go 가드 (둘 중 하나 충족 시에만 실 발행 허용)
PUBLISH_GO_ENV_KEY = "WELLPERION_PUBLISH_GO"

IMAGE_EXTS = (".jpg", ".jpeg", ".png")


# -----------------------------------------------------------------
# 본문 조립 — body-file(가공완료 최종본) + 제목. (feedback_final_content_only_for_publish)
# -----------------------------------------------------------------
class BlogPost:
    __slots__ = ("title", "body", "image_paths")

    def __init__(self, title: str, body: str, image_paths: list[Path]) -> None:
        self.title = title
        self.body = body
        self.image_paths = image_paths


def load_body(body_file: Path | None, body_inline: str | None) -> str:
    if body_inline:
        return body_inline.strip()
    if body_file:
        if not body_file.exists():
            raise FileNotFoundError(f"본문 파일 부재: {body_file}")
        return body_file.read_text(encoding="utf-8").strip()
    return ""


def collect_images(image_dir: Path | None, image_glob: str) -> list[Path]:
    """image_dir 내 image_glob 패턴 파일을 정렬 수집. 한글 폴더 정규화 회피 위해 iterdir 사용."""
    if not image_dir or not image_dir.exists():
        return []
    pat = re.compile(_glob_to_regex(image_glob), re.IGNORECASE)
    found: list[Path] = []
    for p in sorted(image_dir.iterdir(), key=lambda x: x.name):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and pat.match(p.name):
            found.append(p)
    return found


def _glob_to_regex(glob: str) -> str:
    # 단순 glob(*,?) → regex. SmartEditor 이미지 파일명 매칭 전용.
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


def build_post(args: argparse.Namespace) -> BlogPost:
    title = (args.title or "").strip()
    body = load_body(Path(args.body_file) if args.body_file else None, args.body)
    image_dir = Path(args.image_dir) if args.image_dir else None
    if image_dir and not image_dir.is_absolute():
        image_dir = ROOT / image_dir
    images = collect_images(image_dir, args.image_glob)
    return BlogPost(title, body, images)


def validate_post(post: BlogPost, require_images: bool) -> list[str]:
    errs: list[str] = []
    if not post.title:
        errs.append("제목 비어 있음 (--title 필요)")
    if not post.body:
        errs.append("본문 비어 있음 (--body-file 또는 --body 필요)")
    if require_images and not post.image_paths:
        errs.append("이미지 0장 (--image-dir / --image-glob 확인)")
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
# 로그인 세션 판정
# -----------------------------------------------------------------
def is_login_required(current_url: str) -> bool:
    return any(sig in current_url for sig in LOGIN_REDIRECT_SIGNALS)


# -----------------------------------------------------------------
# dryrun — 브라우저/로그인 없이 본문 조립·이미지·셀렉터·가드 점검
# (playwright import 안 함 — 미설치 환경에서도 실행 가능)
# -----------------------------------------------------------------
def run_dryrun(args: argparse.Namespace) -> int:
    print("[INFO] === 네이버 블로그 DRYRUN (브라우저/로그인 없음) ===")
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
        print("[WARN] 본문 조립 경고:")
        for e in errs:
            print(f"        · {e}")
    else:
        print("[INFO] 본문 조립 검증 통과 (제목·본문 OK)")

    print("[INFO] --- 셀렉터 후보 (실측 evidence 기반) ---")
    print(f"        제목     : {TITLE_SELECTORS}")
    print(f"        본문     : {BODY_SELECTORS}")
    print(f"        사진버튼 : {IMAGE_TOOLBAR_BUTTON_SELECTORS}")
    print(f"        첨부모달 : {IMAGE_TYPE_MODAL_SELECTORS} → 슬라이드 {IMAGE_TYPE_SLIDE_SELECTOR}")
    print(f"        임시저장 : {SAVE_DRAFT_SELECTORS}")
    print(f"        발행     : {PUBLISH_TRIGGER_SELECTORS} (publish 모드·GM go 가드 전용)")
    print("[INFO] ⚠ 본문 lazy load는 임시저장 큐 0건일 때만 활성 (가동 전 임시저장함 비우기)")

    print("[INFO] --- 모드 가드 점검 ---")
    print(f"        publish GM go 가드: --i-am-sure 또는 {PUBLISH_GO_ENV_KEY}=1 필요")
    print(f"        현재 --i-am-sure={args.i_am_sure} / env {PUBLISH_GO_ENV_KEY}={os.environ.get(PUBLISH_GO_ENV_KEY, '(unset)')}")
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


async def _install_popup_killer(page) -> None:
    """SmartEditor 팝업 dim/alert 지속 제거 (force click 가능하게)."""
    try:
        await page.evaluate(
            """(sel) => {
                const kill = () => document.querySelectorAll(sel).forEach(el => { try { el.remove(); } catch (e) {} });
                kill();
                const mo = new MutationObserver(kill);
                mo.observe(document.documentElement, { childList: true, subtree: true });
                window.__wpKillTimer = setInterval(kill, 700);
            }""",
            POPUP_KILLER_SELECTORS,
        )
    except Exception as e:
        print(f"[WARN] popup killer 설치 실패(무시): {e}")


async def _first_locator(page, selectors: list[str]):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0:
                return loc, sel
        except Exception:
            continue
    return None, None


# -----------------------------------------------------------------
# setup — GM 수동 로그인 후 세션 저장 (비밀번호 하드코딩 없음)
# -----------------------------------------------------------------
async def run_setup() -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 네이버 블로그 SETUP — GM 수동 로그인 ===")
    print(f"[INFO] 프로필 저장: {PERSISTENT_PROFILE_DIR}")
    p, context = await _launch_context(async_playwright)
    page = await context.new_page()
    await page.goto(NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    print("[INFO] 브라우저에서 네이버 로그인 후 이 터미널에서 Enter 키를 누르세요.")
    await asyncio.get_event_loop().run_in_executor(None, input, "")
    cookies = await context.cookies()
    has_session = any(
        "naver.com" in c.get("domain", "") and c.get("name") in ("NID_AUT", "NID_SES") and c.get("value")
        for c in cookies
    )
    if has_session:
        print("[INFO] 네이버 세션 쿠키 확인 — 저장 완료 (값 비공개: ****)")
    else:
        print("[WARN] NID_AUT/NID_SES 쿠키 미감지 — 로그인 미완료 가능.")
    await context.close()
    await p.stop()
    print("[INFO] === SETUP 완료 ===")
    return 0


# -----------------------------------------------------------------
# 글쓰기 진입 + 제목·본문·이미지 입력 (draft·publish 공용 본체)
# -----------------------------------------------------------------
async def _enter_write_and_fill(page, post: BlogPost, blog_id: str | None) -> None:
    write_url = BLOG_WRITE_URL_TEMPLATE.format(blog_id=blog_id) if blog_id else BLOG_WRITE_URL_GENERIC
    print(f"[INFO] 글쓰기 진입: {write_url}")
    await page.goto(write_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(3000)
    await _install_popup_killer(page)

    if is_login_required(page.url):
        raise RuntimeError("로그인 필요 — --mode setup 으로 세션 재저장 필요")

    # SmartEditor는 iframe(mainFrame) 안에 있을 수 있음 → frame 우선 탐색
    target = page
    for fr in page.frames:
        try:
            if await fr.locator(".se-title-text, span.__se_placeholder").count() > 0:
                target = fr
                print(f"[INFO] SmartEditor frame 감지: {fr.name or fr.url}")
                break
        except Exception:
            continue

    # 제목
    title_loc, title_sel = await _first_locator(target, TITLE_SELECTORS)
    if title_loc is None:
        raise RuntimeError("제목 셀렉터 미발견 (SmartEditor 미로딩 또는 UI 변경)")
    await title_loc.click()
    await page.keyboard.type(post.title, delay=15)
    print(f"[INFO] 제목 입력 ({title_sel!r})")
    await page.wait_for_timeout(800)

    # 본문 (임시저장 큐 누적 시 lazy load 차단 — project_draft_queue_dependency)
    body_loc, body_sel = await _first_locator(target, BODY_SELECTORS)
    if body_loc is None:
        raise RuntimeError("본문 셀렉터 미발견 (임시저장 큐 누적 시 lazy load 차단 가능 — 큐 비우기)")
    await body_loc.click()
    await page.keyboard.type(post.body, delay=8)  # keyboard.type = 이모지 surrogate pair 대응
    print(f"[INFO] 본문 입력 ({body_sel!r}, {len(post.body)} chars)")
    await page.wait_for_timeout(800)

    # 본문 textContent 안전판 검증
    try:
        body_text = (await body_loc.inner_text()) or ""
        if len(body_text.strip()) < min(10, len(post.body)):
            raise RuntimeError(f"본문 입력 검증 실패 — textContent 길이 {len(body_text.strip())} (큐 누적 의심)")
    except RuntimeError:
        raise
    except Exception:
        pass

    # 이미지 첨부 (슬라이드 모달 단계 포함 — v3.0)
    if post.image_paths:
        await _attach_images(page, target, post.image_paths)


async def _attach_images(page, target, image_paths: list[Path]) -> None:
    btn_loc, btn_sel = await _first_locator(target, IMAGE_TOOLBAR_BUTTON_SELECTORS)
    if btn_loc is None:
        print("[WARN] 사진 추가 버튼 미발견 — 이미지 첨부 건너뜀")
        return
    # 본문 끝으로 caret 이동 (이미지가 본문 아래 들어가게)
    try:
        await page.keyboard.press("Control+End")
    except Exception:
        pass
    try:
        async with page.expect_file_chooser(timeout=8000) as fc_info:
            await btn_loc.click(force=True)
        fc = await fc_info.value
        await fc.set_files([str(p) for p in image_paths])
        print(f"[INFO] 이미지 {len(image_paths)}장 주입 (file_chooser)")
    except Exception as e:
        print(f"[WARN] file_chooser 경로 실패: {e}")
        return
    await page.wait_for_timeout(2000)
    # 사진 첨부 방식 모달 → 슬라이드 선택 (v3.0 핵심)
    modal_loc, _ = await _first_locator(page, IMAGE_TYPE_MODAL_SELECTORS)
    if modal_loc is not None:
        slide = page.locator(IMAGE_TYPE_SLIDE_SELECTOR).first
        try:
            if await slide.count() > 0:
                await slide.click(force=True)
                print("[INFO] 사진 첨부 방식 = 슬라이드 선택 (#image-type-slide)")
        except Exception as e:
            print(f"[WARN] 슬라이드 옵션 클릭 실패: {e}")
    await page.wait_for_timeout(3500)


# -----------------------------------------------------------------
# draft — 임시저장까지만
# -----------------------------------------------------------------
async def run_draft(args: argparse.Namespace) -> int:
    async_playwright = _import_playwright()
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    post = build_post(args)
    errs = validate_post(post, require_images=False)
    if errs:
        print("[ERROR] 본문 검증 실패 — draft 차단:")
        for e in errs:
            print(f"        · {e}")
        return 6

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot = EVIDENCE_DIR / f"naver-blog-draft-{ts}.png"

    print("[INFO] === 네이버 블로그 DRAFT (임시저장까지) ===")
    p, context = await _launch_context(async_playwright)
    page = await context.new_page()
    try:
        await _enter_write_and_fill(page, post, args.blog_id)
        # 임시저장
        save_loc, save_sel = await _first_locator(page, SAVE_DRAFT_SELECTORS)
        if save_loc is None:
            await page.screenshot(path=str(shot.with_suffix(".error_save.png")))
            raise RuntimeError("임시저장 버튼 미발견")
        await save_loc.click(force=True)
        print(f"[INFO] 임시저장 클릭 ({save_sel!r})")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(shot))
        print(f"[INFO] 임시저장 완료 — 스크린샷 {shot}")
    except Exception as e:
        await page.screenshot(path=str(shot.with_suffix(".error.png")))
        print(f"[ERROR] draft 실패: {e}")
        telegram_report(f"네이버 블로그 임시저장 실패\n사유: {e}")
        await context.close()
        await p.stop()
        return 7
    await context.close()
    await p.stop()
    telegram_report(f"네이버 블로그 임시저장 완료\n제목: {post.title}")
    print("[INFO] === DRAFT 완료 (발행 안 함 — 사람 검수 게이트) ===")
    return 0


# -----------------------------------------------------------------
# publish — 실 발행. GM go 가드 통과 시에만.
# -----------------------------------------------------------------
async def run_publish(args: argparse.Namespace) -> int:
    if not publish_guard_ok(args):
        print("[ERROR] publish 거부 — GM go 가드 미충족.")
        print(f"        실 발행하려면 --i-am-sure 플래그 또는 {PUBLISH_GO_ENV_KEY}=1 환경변수 필요.")
        return 9
    async_playwright = _import_playwright()
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    post = build_post(args)
    errs = validate_post(post, require_images=False)
    if errs:
        print("[ERROR] 본문 검증 실패 — publish 차단:")
        for e in errs:
            print(f"        · {e}")
        return 6

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot = EVIDENCE_DIR / f"naver-blog-published-{ts}.png"
    print("[INFO] === 네이버 블로그 PUBLISH (GM go 가드 통과) ===")
    p, context = await _launch_context(async_playwright)
    page = await context.new_page()
    try:
        await _enter_write_and_fill(page, post, args.blog_id)
        trig_loc, trig_sel = await _first_locator(page, PUBLISH_TRIGGER_SELECTORS)
        if trig_loc is None:
            raise RuntimeError("발행 버튼 미발견")
        await trig_loc.click(force=True)
        print(f"[INFO] 발행 패널 진입 ({trig_sel!r})")
        await page.wait_for_timeout(1500)
        conf_loc, conf_sel = await _first_locator(page, PUBLISH_CONFIRM_SELECTORS)
        if conf_loc is None:
            raise RuntimeError("발행 확인 버튼 미발견")
        await conf_loc.click(force=True)
        print(f"[INFO] 발행 확인 클릭 ({conf_sel!r})")
        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(shot))
        print(f"[INFO] 발행 완료 — 스크린샷 {shot}")
    except Exception as e:
        await page.screenshot(path=str(shot.with_suffix(".error.png")))
        print(f"[ERROR] publish 실패: {e}")
        telegram_report(f"네이버 블로그 발행 실패\n사유: {e}")
        await context.close()
        await p.stop()
        return 7
    await context.close()
    await p.stop()
    telegram_report(f"네이버 블로그 발행 완료\n제목: {post.title}")
    print("[INFO] === PUBLISH 완료 ===")
    return 0


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CMO — 네이버 블로그 SmartEditor 업로더 v1.0 (임시저장까지·발행 GM go 가드)"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "dryrun", "draft", "publish"],
        default="dryrun",
        help=(
            "setup: GM 수동 로그인 세션 저장 / "
            "dryrun: 브라우저 없이 본문 조립·이미지·셀렉터·가드 점검 (기본) / "
            "draft: 임시저장까지 / "
            "publish: 실 발행 (--i-am-sure 또는 WELLPERION_PUBLISH_GO=1 필요)"
        ),
    )
    parser.add_argument("--title", default=None, help="글 제목")
    parser.add_argument("--body-file", dest="body_file", default=None, help="본문 텍스트 파일(가공완료 최종본)")
    parser.add_argument("--body", default=None, help="본문 인라인 텍스트(테스트용)")
    parser.add_argument("--image-dir", dest="image_dir", default=None, help="이미지 폴더")
    parser.add_argument("--image-glob", dest="image_glob", default="blog_*.jpg", help="이미지 파일명 패턴")
    parser.add_argument("--blog-id", dest="blog_id", default=None, help="본인 블로그 ID (글쓰기 URL용)")
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
