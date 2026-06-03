# scripts/cafe_upload_playwright.py
# v1.0 — 동부이촌동커뮤니티 네이버 카페(ichon1dong) SmartEditor 업로더 (유실 소스 복원)
#
# 정책: 임시등록(draft)까지만 자동. 실 발행(publish)은 GM go 가드 — 명시 플래그 없으면 거부.
#       비밀번호 하드코딩 없음. Persistent Profile 세션 재사용. 토큰 stdout 노출 금지.
#       카페 본문 톤은 격조 있는 전문 톤 의무 (feedback_cafe_tone_elevated) — 본 스크립트는 게시만,
#       톤 격상은 상위 콘텐츠 가공 단계 책임. 게시 본문=가공완료 최종본만 가정.
#
# 모드:
#   setup  : GM 수동 로그인 → Persistent Profile 세션 저장
#   dryrun : 브라우저/로그인 없이 본문 조립·이미지·셀렉터·메뉴·가드 점검 (기본)
#   draft  : 글쓰기 진입 → 제목·본문·이미지(슬라이드) → 임시등록까지
#   publish: 실 발행 — GM go 가드(--i-am-sure 또는 WELLPERION_PUBLISH_GO=1) 없으면 거부
#
# 실행 예:
#   python scripts\cafe_upload_playwright.py --mode dryrun ^
#       --title "..." --body-file temp\body_cafe.txt --image-dir instagram\xxx\output\cafe
#   python scripts\cafe_upload_playwright.py --mode draft --menuid 659 --title "..." --body-file ... --image-dir ...
#
# 셀렉터 출처(evidence): scripts/poc-evidence/cafe-ichon1dong-*, project_smarteditor_auto_attach 메모리
#   제목 textarea.textarea_input / 본문 .__se_placeholder.se-fs15
#   사진버튼 button.se-image-toolbar-button / 첨부모달 .se-popup-image-type → 슬라이드 #image-type-slide
#   임시등록 button.btn_temp_save
# 카페 메뉴(evidence: cafe-ichon1dong-menus-*.json): club_id=11948735,
#   웰페리온 Spa&Fitness 게시판 menuid=659 (기본), 프로모션/이벤트 380, 제휴홍보업체 후기 689

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
PERSISTENT_PROFILE_DIR = ROOT / "profiles" / "naver-cafe"  # 실제 저장된 카페 로그인 세션
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"

# 동부이촌동커뮤니티 카페 (evidence: cafe-ichon1dong-menus-20260426_150706.json)
CAFE_NAME = "ichon1dong"
CAFE_CLUB_ID = 11948735
DEFAULT_MENU_ID = 659  # 웰페리온 Spa&Fitness 게시판
# 글쓰기 진입 URL (카페 글쓰기 폼). menuid 지정 시 해당 게시판 선택 상태로 진입.
CAFE_WRITE_URL_TEMPLATE = (
    "https://cafe.naver.com/ca-fe/cafes/{club_id}/articles/write?boardType=L&menuId={menu_id}"
)

LOGIN_REDIRECT_SIGNALS = ("nid.naver.com/nidlogin", "nid.naver.com/login")

# SmartEditor ONE 셀렉터 — 카페 (2026-05-21 v3.0 실측, project_smarteditor_auto_attach)
TITLE_SELECTORS = [
    "textarea.textarea_input",
    "input.textarea_input",
    ".se-title-text",
]
BODY_SELECTORS = [
    ".__se_placeholder.se-fs15",
    ".se-text-paragraph",
    'div[contenteditable="true"].se-content',
]
IMAGE_TOOLBAR_BUTTON_SELECTORS = [
    "button.se-image-toolbar-button",
    'button[data-name="image"]',
]
IMAGE_TYPE_MODAL_SELECTORS = [".se-popup-image-type", '[data-group="popupLayer"] .se-popup-image-type']
IMAGE_TYPE_SLIDE_SELECTOR = "#image-type-slide"
# 스티커 (2026-06-03 블로그 발행기에서 이식 — 동일 SmartEditor 툴바 구조).
# 툴바 '스티커' 버튼 클릭 → 우측 se-sidebar-container-sticker 패널 오픈.
# 패널 그리드의 각 스티커 = button.se-sidebar-element-sticker. 클릭 시 본문에
# se-component.se-sticker 컴포넌트가 삽입됨.
STICKER_TOOLBAR_BUTTON_SELECTORS = [
    'button[data-name="sticker"]',
    "button.se-sticker-toolbar-button",
    'button[data-log="dot.sticker"]',
]
# 카페는 GIF 스티커 버튼 클래스명이 블로그와 다름 (실측 2026-06-03).
# 블로그: button.se-sidebar-element-sticker (exact class)
# 카페:   button.se-sidebar-element-sticker-gif (class에 -gif 접미사 추가)
# attribute substring selector로 양쪽 모두 커버.
STICKER_ITEM_SELECTOR = 'button[class*="se-sidebar-element-sticker"]'
STICKER_COUNT_DEFAULT = 3  # 본문에 삽입할 기본 스티커 개수 (GM 검수 시 교체 전제)
# 카페 임시등록 버튼
SAVE_DRAFT_SELECTORS = [
    "button.btn_temp_save",
    'button:has-text("임시등록")',
    'button:has-text("임시저장")',
]
# 카페 등록(발행) 버튼 — publish 모드·GM go 가드 전용
PUBLISH_TRIGGER_SELECTORS = [
    "a.btn_register",
    "button.btn_register",
    'button:has-text("등록")',
]

POPUP_KILLER_SELECTORS = (
    ".se-popup-dim, .se-popup-alert, .se-popup-alert-confirm, "
    ".blog-se-alert, .se-help-panel, [data-group='popupLayer']"
)

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"

PUBLISH_GO_ENV_KEY = "WELLPERION_PUBLISH_GO"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


# -----------------------------------------------------------------
# 본문 조립
# -----------------------------------------------------------------
class CafePost:
    __slots__ = ("title", "body", "image_paths", "menu_id", "sticker_count")

    def __init__(self, title: str, body: str, image_paths: list[Path], menu_id: int, sticker_count: int = STICKER_COUNT_DEFAULT) -> None:
        self.title = title
        self.body = body
        self.image_paths = image_paths
        self.menu_id = menu_id
        self.sticker_count = sticker_count


def load_body(body_file: Path | None, body_inline: str | None) -> str:
    if body_inline:
        return body_inline.strip()
    if body_file:
        if not body_file.exists():
            raise FileNotFoundError(f"본문 파일 부재: {body_file}")
        return body_file.read_text(encoding="utf-8").strip()
    return ""


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


def collect_images(image_dir: Path | None, image_glob: str) -> list[Path]:
    if not image_dir or not image_dir.exists():
        return []
    pat = re.compile(_glob_to_regex(image_glob), re.IGNORECASE)
    found: list[Path] = []
    for p in sorted(image_dir.iterdir(), key=lambda x: x.name):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and pat.match(p.name):
            found.append(p)
    return found


def build_post(args: argparse.Namespace) -> CafePost:
    title = (args.title or "").strip()
    body = load_body(Path(args.body_file) if args.body_file else None, args.body)
    image_dir = Path(args.image_dir) if args.image_dir else None
    if image_dir and not image_dir.is_absolute():
        image_dir = ROOT / image_dir
    images = collect_images(image_dir, args.image_glob)
    sticker_count = getattr(args, "sticker_count", STICKER_COUNT_DEFAULT)
    return CafePost(title, body, images, args.menuid, sticker_count)


# 카페 톤 격상 룰 가드 (feedback_cafe_tone_elevated) — 게시 차단이 아닌 경고만.
FORBIDDEN_TONE_PHRASES = ["이웃 여러분", "동네 클럽", "동네 스포츠클럽", "이웃에게", "이웃분"]


def validate_post(post: CafePost, require_images: bool) -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    if not post.title:
        errs.append("제목 비어 있음 (--title 필요)")
    if not post.body:
        errs.append("본문 비어 있음 (--body-file 또는 --body 필요)")
    if require_images and not post.image_paths:
        errs.append("이미지 0장")
    for phrase in FORBIDDEN_TONE_PHRASES:
        if phrase in post.body:
            warns.append(f"톤 격하 표현 감지: {phrase!r} (feedback_cafe_tone_elevated — 전문 톤 권장)")
    return errs, warns


# -----------------------------------------------------------------
# 텔레그램 보고 (토큰 stdout 노출 금지)
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


def is_login_required(current_url: str) -> bool:
    return any(sig in current_url for sig in LOGIN_REDIRECT_SIGNALS)


def publish_guard_ok(args: argparse.Namespace) -> bool:
    if getattr(args, "i_am_sure", False):
        return True
    if os.environ.get(PUBLISH_GO_ENV_KEY, "").strip() == "1":
        return True
    return False


# -----------------------------------------------------------------
# dryrun — 브라우저/로그인 없이 점검
# -----------------------------------------------------------------
def run_dryrun(args: argparse.Namespace) -> int:
    print("[INFO] === 동부이촌동 카페 DRYRUN (브라우저/로그인 없음) ===")
    post = build_post(args)
    write_url = CAFE_WRITE_URL_TEMPLATE.format(club_id=CAFE_CLUB_ID, menu_id=post.menu_id)
    print(f"[INFO] 카페: {CAFE_NAME} (club_id={CAFE_CLUB_ID}) / 게시판 menuid={post.menu_id}")
    print(f"[INFO] 글쓰기 URL: {write_url}")
    print(f"[INFO] 제목: {post.title or '(비어 있음)'}")
    print(f"[INFO] 본문 길이: {len(post.body)} chars / 줄수: {post.body.count(chr(10)) + 1 if post.body else 0}")
    if post.body:
        print(f"[INFO] 본문 첫줄: {post.body.splitlines()[0][:60]}...")
    print(f"[INFO] 이미지 {len(post.image_paths)}장:")
    for p in post.image_paths[:10]:
        print(f"        · {p.name}")
    if len(post.image_paths) > 10:
        print(f"        · ... 외 {len(post.image_paths) - 10}장")

    errs, warns = validate_post(post, require_images=False)
    if errs:
        print("[WARN] 본문 조립 경고:")
        for e in errs:
            print(f"        · {e}")
    else:
        print("[INFO] 본문 조립 검증 통과 (제목·본문 OK)")
    for w in warns:
        print(f"[WARN] {w}")

    print("[INFO] --- 셀렉터 후보 (실측 evidence 기반) ---")
    print(f"        제목     : {TITLE_SELECTORS}")
    print(f"        본문     : {BODY_SELECTORS}")
    print(f"        사진버튼 : {IMAGE_TOOLBAR_BUTTON_SELECTORS}")
    print(f"        첨부모달 : {IMAGE_TYPE_MODAL_SELECTORS} → 슬라이드 {IMAGE_TYPE_SLIDE_SELECTOR}")
    print(f"        임시등록 : {SAVE_DRAFT_SELECTORS}")
    print(f"        등록(발행): {PUBLISH_TRIGGER_SELECTORS} (publish 모드·GM go 가드 전용)")

    print("[INFO] --- 모드 가드 점검 ---")
    print(f"        publish GM go 가드: --i-am-sure 또는 {PUBLISH_GO_ENV_KEY}=1 필요")
    print(f"        현재 --i-am-sure={args.i_am_sure} / env {PUBLISH_GO_ENV_KEY}={os.environ.get(PUBLISH_GO_ENV_KEY, '(unset)')}")
    print("[INFO] === DRYRUN 완료 (제출·발행 없음) ===")
    return 0


# -----------------------------------------------------------------
# 브라우저 공통 (playwright lazy import)
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
    try:
        await page.evaluate(
            """(sel) => {
                const kill = () => document.querySelectorAll(sel).forEach(el => { try { el.remove(); } catch (e) {} });
                kill();
                const mo = new MutationObserver(kill);
                mo.observe(document.documentElement, { childList: true, subtree: true });
                window.__wpKillObserver = mo;
                window.__wpKillTimer = setInterval(kill, 700);
            }""",
            POPUP_KILLER_SELECTORS,
        )
    except Exception as e:
        print(f"[WARN] popup killer 설치 실패(무시): {e}")


async def _stop_popup_killer(page) -> None:
    """팝업 킬러 일시 정지 — 스티커 모달처럼 '살려둬야 하는 팝업'을 열기 전 호출."""
    try:
        await page.evaluate(
            """() => {
                if (window.__wpKillTimer) { clearInterval(window.__wpKillTimer); window.__wpKillTimer = null; }
                if (window.__wpKillObserver) { try { window.__wpKillObserver.disconnect(); } catch (e) {} window.__wpKillObserver = null; }
            }"""
        )
    except Exception:
        pass


async def _first_locator(scope, selectors: list[str]):
    for sel in selectors:
        loc = scope.locator(sel).first
        try:
            if await loc.count() > 0:
                return loc, sel
        except Exception:
            continue
    return None, None


async def _resolve_editor_scope(page):
    """카페 SmartEditor는 iframe(cafe_main 등) 안에 있을 수 있음 → frame 우선 탐색."""
    for fr in page.frames:
        try:
            if await fr.locator("textarea.textarea_input, .__se_placeholder, .se-title-text").count() > 0:
                print(f"[INFO] SmartEditor frame 감지: {fr.name or fr.url}")
                return fr
        except Exception:
            continue
    return page


# -----------------------------------------------------------------
# setup
# -----------------------------------------------------------------
async def run_setup() -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 네이버 카페 SETUP — GM 수동 로그인 ===")
    print(f"[INFO] 프로필 저장: {PERSISTENT_PROFILE_DIR}")
    p, context = await _launch_context(async_playwright)
    # 기존(옛 계정) 세션 제거 — 새 로그인만 감지하도록 로그아웃 상태로 시작
    try:
        await context.clear_cookies()
        print("[INFO] 기존 세션 비움 — 새 계정으로 로그인하세요.")
    except Exception as e:
        print(f"[WARN] 기존 세션 비우기 실패(무시): {e}")
    page = await context.new_page()
    await page.goto(NAVER_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    print("[INFO] 브라우저에서 네이버 로그인을 완료하세요 — 로그인 감지 시 자동 저장됩니다.")
    print("[INFO] (Enter 불필요. 최대 5분 대기, 로그인 끝나면 자동 마무리)")

    def _has_naver_session(cookies):
        return any(
            "naver.com" in c.get("domain", "") and c.get("name") in ("NID_AUT", "NID_SES") and c.get("value")
            for c in cookies
        )

    has_session = False
    waited, deadline = 0, 300  # 초
    while waited < deadline:
        try:
            cookies = await context.cookies()
        except Exception:
            break  # 브라우저 창을 GM이 닫음
        if _has_naver_session(cookies):
            has_session = True
            break
        await asyncio.sleep(3)
        waited += 3
    if has_session:
        await asyncio.sleep(2)  # 쿠키가 디스크 프로필에 안착할 여유
        print("[INFO] 네이버 세션 쿠키 확인 — 저장 완료 (값 비공개: ****)")
    else:
        print("[WARN] 5분 내 NID_AUT/NID_SES 쿠키 미감지 — 로그인 미완료. 다시 실행하세요.")
    await context.close()
    await p.stop()
    print("[INFO] === SETUP 완료 ===")
    return 0


# -----------------------------------------------------------------
# 글쓰기 진입 + 제목·본문·이미지 입력 (draft·publish 공용)
# -----------------------------------------------------------------
async def _enter_write_and_fill(page, post: CafePost) -> None:
    write_url = CAFE_WRITE_URL_TEMPLATE.format(club_id=CAFE_CLUB_ID, menu_id=post.menu_id)
    print(f"[INFO] 카페 글쓰기 진입: {write_url}")
    await page.goto(write_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(3000)
    await _install_popup_killer(page)

    if is_login_required(page.url):
        raise RuntimeError("로그인 필요 — --mode setup 으로 세션 재저장 필요")

    scope = await _resolve_editor_scope(page)

    # 제목 (카페는 textarea)
    title_loc, title_sel = await _first_locator(scope, TITLE_SELECTORS)
    if title_loc is None:
        raise RuntimeError("제목 셀렉터 미발견 (카페 글쓰기 폼 미로딩 또는 UI 변경)")
    await title_loc.click()
    if title_sel and "textarea" in title_sel:
        await title_loc.fill(post.title)
    else:
        await page.keyboard.type(post.title, delay=15)
    print(f"[INFO] 제목 입력 ({title_sel!r})")
    await page.wait_for_timeout(800)

    # 본문
    body_loc, body_sel = await _first_locator(scope, BODY_SELECTORS)
    if body_loc is None:
        raise RuntimeError("본문 셀렉터 미발견 (SmartEditor 미로딩)")
    await body_loc.click()
    await page.keyboard.type(post.body, delay=8)
    print(f"[INFO] 본문 입력 ({body_sel!r}, {len(post.body)} chars)")
    await page.wait_for_timeout(800)

    try:
        body_text = (await body_loc.inner_text()) or ""
        if len(body_text.strip()) < min(10, len(post.body)):
            raise RuntimeError(f"본문 입력 검증 실패 — textContent 길이 {len(body_text.strip())}")
    except RuntimeError:
        raise
    except Exception:
        pass

    # 스티커 삽입 (블로그 발행기에서 이식 — 본문 입력 직후, 이미지 첨부 전).
    sticker_count = getattr(post, "sticker_count", STICKER_COUNT_DEFAULT)
    if sticker_count > 0:
        await _insert_stickers(page, scope, sticker_count)

    if post.image_paths:
        await _attach_images(page, scope, post.image_paths)


async def _insert_stickers(page, scope, count: int) -> int:
    """툴바 '스티커' 버튼 → 우측 패널 오픈 → 그리드에서 count개 클릭해 본문에 삽입.
    삽입된 se-component.se-sticker 컴포넌트 수를 반환. (블로그 발행기 이식 2026-06-03)"""
    # caret을 본문 끝으로 (스티커가 본문 아래 들어가게)
    try:
        await page.keyboard.press("Control+End")
    except Exception:
        pass
    # 팝업 킬러가 스티커 모달(팝업 레이어)을 삭제하므로 잠시 정지 (실측 2026-06-03)
    await _stop_popup_killer(page)
    btn_loc, btn_sel = await _first_locator(scope, STICKER_TOOLBAR_BUTTON_SELECTORS)
    if btn_loc is None:
        print("[WARN] 스티커 버튼 미발견 — 스티커 삽입 건너뜀")
        await _install_popup_killer(page)  # 킬러 복구
        return 0

    # 삽입 전 본문 내 스티커 컴포넌트 수
    sticker_count_js = "() => document.querySelectorAll('.se-component.se-sticker').length"
    try:
        before = await scope.evaluate(sticker_count_js)
    except Exception:
        before = 0

    # 카페 스티커는 중앙 팝업 모달이며 scope와 다른 프레임에 렌더됨(실측 2026-06-03) → 전 프레임 스캔
    async def _find_sticker_items():
        for ctx in [page] + list(page.frames):
            try:
                cand = ctx.locator(STICKER_ITEM_SELECTOR)
                if await cand.count() > 0:
                    return cand
            except Exception:
                continue
        return None

    # 스티커 하나 고르면 모달이 닫히므로 count만큼 패널을 재오픈하며 삽입
    clicked = 0
    for k in range(count):
        try:
            await btn_loc.click(force=True)  # 패널 열기
            await page.wait_for_timeout(1500)
        except Exception:
            break
        if k == 0:
            print(f"[INFO] 스티커 패널 오픈 ({btn_sel!r})")
        items = await _find_sticker_items()
        if items is None:
            await page.wait_for_timeout(2000)
            items = await _find_sticker_items()
        if items is None:
            print("[WARN] 스티커 그리드 항목 0개 (전 프레임)")
            break
        n = await items.count()
        idx = (k * 5) % n  # 매번 다른 스티커
        picked = False
        for off in range(n):
            it = items.nth((idx + off) % n)
            try:
                if await it.is_visible():
                    await it.click(force=True)
                    clicked += 1
                    picked = True
                    await page.wait_for_timeout(1000)  # 삽입·모달 닫힘 반영
                    break
            except Exception:
                continue
        if not picked:
            break
    print(f"[INFO] 스티커 {clicked}개 삽입 (요청 {count}개)")
    await _install_popup_killer(page)  # 킬러 복구 (이후 이미지 단계 보호)

    # 실측 검증 — 본문 내 스티커 컴포넌트 증가분 확인
    try:
        after = await scope.evaluate(sticker_count_js)
    except Exception:
        after = before
    inserted = after - before
    if inserted < clicked:
        print(f"[WARN] 스티커 삽입 검증 — 본문 스티커 {before}→{after} (클릭 {clicked}개 중 {inserted}개만 반영)")
    else:
        print(f"[INFO] 스티커 삽입 검증 OK — 본문 스티커 {before}→{after} ({inserted}개 추가)")
    return inserted


async def _attach_images(page, scope, image_paths: list[Path]) -> None:
    btn_loc, _ = await _first_locator(scope, IMAGE_TOOLBAR_BUTTON_SELECTORS)
    if btn_loc is None:
        print("[WARN] 사진 추가 버튼 미발견 — 이미지 첨부 건너뜀")
        return
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
# draft — 임시등록까지
# -----------------------------------------------------------------
async def run_draft(args: argparse.Namespace) -> int:
    async_playwright = _import_playwright()
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    post = build_post(args)
    errs, warns = validate_post(post, require_images=False)
    for w in warns:
        print(f"[WARN] {w}")
    if errs:
        print("[ERROR] 본문 검증 실패 — draft 차단:")
        for e in errs:
            print(f"        · {e}")
        return 6

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot = EVIDENCE_DIR / f"cafe-ichon1dong-draft-{ts}.png"
    print("[INFO] === 동부이촌동 카페 DRAFT (임시등록까지) ===")
    p, context = await _launch_context(async_playwright)
    page = await context.new_page()
    try:
        await _enter_write_and_fill(page, post)
        save_loc, save_sel = await _first_locator(page, SAVE_DRAFT_SELECTORS)
        if save_loc is None:
            await page.screenshot(path=str(shot.with_suffix(".error_save.png")))
            raise RuntimeError("임시등록 버튼 미발견")
        await save_loc.click(force=True)
        print(f"[INFO] 임시등록 클릭 ({save_sel!r})")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(shot))
        print(f"[INFO] 임시등록 완료 — 스크린샷 {shot}")
    except Exception as e:
        await page.screenshot(path=str(shot.with_suffix(".error.png")))
        print(f"[ERROR] draft 실패: {e}")
        telegram_report(f"동부이촌동 카페 임시등록 실패\n사유: {e}")
        await context.close()
        await p.stop()
        return 7
    await context.close()
    await p.stop()
    telegram_report(f"동부이촌동 카페 임시등록 완료\n제목: {post.title}")
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
    errs, warns = validate_post(post, require_images=False)
    for w in warns:
        print(f"[WARN] {w}")
    if errs:
        print("[ERROR] 본문 검증 실패 — publish 차단:")
        for e in errs:
            print(f"        · {e}")
        return 6

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot = EVIDENCE_DIR / f"cafe-ichon1dong-published-{ts}.png"
    print("[INFO] === 동부이촌동 카페 PUBLISH (GM go 가드 통과) ===")
    p, context = await _launch_context(async_playwright)
    page = await context.new_page()
    try:
        await _enter_write_and_fill(page, post)
        trig_loc, trig_sel = await _first_locator(page, PUBLISH_TRIGGER_SELECTORS)
        if trig_loc is None:
            raise RuntimeError("등록(발행) 버튼 미발견")
        await trig_loc.click(force=True)
        print(f"[INFO] 등록 클릭 ({trig_sel!r})")
        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(shot))
        print(f"[INFO] 등록 완료 — 스크린샷 {shot}")
        # 발행 후 현재 페이지 URL 회수 시도 (감시기 post_url 기록용)
        # 카페는 등록 후 게시물 상세 페이지로 이동하는 경우가 있어 현재 URL 확인.
        # URL 취득 불가 시에도 발행 성공 사실은 exit code 0 으로 전달.
        try:
            current_url = page.url
            if current_url and "cafe.naver.com" in current_url and "/articles/" in current_url:
                print(f"post A: {current_url}")
            else:
                print("post A: (naver-url-회수불가)")
        except Exception:
            print("post A: (naver-url-회수불가)")
    except Exception as e:
        await page.screenshot(path=str(shot.with_suffix(".error.png")))
        print(f"[ERROR] publish 실패: {e}")
        telegram_report(f"동부이촌동 카페 발행 실패\n사유: {e}")
        await context.close()
        await p.stop()
        return 7
    await context.close()
    await p.stop()
    telegram_report(f"동부이촌동 카페 발행 완료\n제목: {post.title}")
    print("[INFO] === PUBLISH 완료 ===")
    return 0


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CMO — 동부이촌동 카페 SmartEditor 업로더 v1.0 (임시등록까지·발행 GM go 가드)"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "dryrun", "draft", "publish"],
        default="dryrun",
        help=(
            "setup: GM 수동 로그인 세션 저장 / "
            "dryrun: 브라우저 없이 본문·이미지·셀렉터·메뉴·가드 점검 (기본) / "
            "draft: 임시등록까지 / "
            "publish: 실 발행 (--i-am-sure 또는 WELLPERION_PUBLISH_GO=1 필요)"
        ),
    )
    parser.add_argument("--title", default=None, help="글 제목")
    parser.add_argument("--body-file", dest="body_file", default=None, help="본문 텍스트 파일(가공완료 최종본)")
    parser.add_argument("--body", default=None, help="본문 인라인 텍스트(테스트용)")
    parser.add_argument("--image-dir", dest="image_dir", default=None, help="이미지 폴더")
    parser.add_argument("--image-glob", dest="image_glob", default="cafe_*.jpg", help="이미지 파일명 패턴")
    parser.add_argument("--menuid", type=int, default=DEFAULT_MENU_ID, help=f"카페 게시판 menuid (기본 {DEFAULT_MENU_ID}=웰페리온)")
    parser.add_argument(
        "--sticker-count", dest="sticker_count", type=int, default=STICKER_COUNT_DEFAULT,
        help=f"본문에 삽입할 스티커 개수 (기본 {STICKER_COUNT_DEFAULT}, 0이면 생략)",
    )
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
