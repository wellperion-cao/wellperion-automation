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

# UTM 딱지 헬퍼 — 본문 문의 CTA URL에 채널 출처 부착 (scripts/ 동일 디렉터리)
try:
    from cta_utm import apply_cta_utm, append_cta_card, normalize_body, slugify_campaign
except ImportError:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from cta_utm import apply_cta_utm, append_cta_card, normalize_body, slugify_campaign

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
PERSISTENT_PROFILE_DIR = ROOT / "profiles" / "naver-blog"  # 실제 저장된 블로그 로그인 세션
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
# 블로그 글쓰기 진입 — 반드시 본인 블로그 ID 포함 URL 사용.
# PostWriteForm.naver(blog_id 없음)는 "유효하지 않은 요청 — 블로그 아이디가 없습니다" 에러 페이지로
# 빠져 SmartEditor가 로딩되지 않음(제목 셀렉터 미발견의 진짜 원인). 따라서 기본 blog_id를 강제한다.
BLOG_WRITE_URL_TEMPLATE = "https://blog.naver.com/{blog_id}/postwrite"
DEFAULT_BLOG_ID = "wellperion"  # 웰페리온 공식 블로그 ID (세션 실측 2026-06-03)

# 로그인 만료 시그널 (URL 기반)
LOGIN_REDIRECT_SIGNALS = ("nid.naver.com/nidlogin", "nid.naver.com/login")

# SmartEditor ONE 셀렉터 (2026-05-21 v3.0 실측 — project_smarteditor_auto_attach)
TITLE_SELECTORS = [
    ".se-title-text",
    "span.__se_placeholder.se-fs32",
    ".se-section-documentTitle .se-text-paragraph",
]
# ⚠ 제목 섹션(.se-section-documentTitle) 안에도 .se-text-paragraph 가 존재한다(2026-06-03 DOM 실측).
#   따라서 ".se-text-paragraph" 단독은 .first 가 제목 문단으로 resolve → 본문 입력이 제목칸으로 흘러드는
#   버그(제목+본문 연속 표기)의 root cause. 본문 컴포넌트(.se-component.se-text) 하위 문단으로 한정한다.
BODY_SELECTORS = [
    ".se-component.se-text .se-text-paragraph",
    ".se-component-content .se-text-paragraph",
    "span.__se_placeholder.se-fs15",
]
IMAGE_TOOLBAR_BUTTON_SELECTORS = [
    "button.se-image-toolbar-button",
    'button[data-name="image"]',
    'button[data-log="image"]',
]
# 사진 첨부 방식 모달 → 슬라이드 옵션 (v3.0 핵심 단계)
# ⚠ #image-type-slide 는 <input type=button> 인데 <label for=...>가 포인터 이벤트를 가로채
#   input 직접 클릭은 타임아웃. 반드시 label[for="image-type-slide"] 를 클릭한다(2026-06-03 실측).
IMAGE_TYPE_MODAL_SELECTORS = [".se-popup-image-type", '[data-group="popupLayer"] .se-popup-image-type']
IMAGE_TYPE_SLIDE_SELECTOR = 'label[for="image-type-slide"]'
IMAGE_TYPE_SLIDE_INPUT_SELECTOR = "#image-type-slide"
IMAGE_TYPE_LIST_SELECTOR = "#image-type-list"
# 본문에 실제 삽입된 이미지 검증용 — .se-content 영역 내 <img> 개수(슬라이드=N장 모두 img 태그).
INSERTED_IMAGE_SELECTOR = ".se-content img"

# 스티커 (2026-06-03 실측 — 사진 버튼과 동일한 툴바 구조).
# 툴바 '스티커' 버튼 클릭 → 우측 se-sidebar-container-sticker 패널 오픈.
# 패널 그리드의 각 스티커 = button.se-sidebar-element-sticker. 클릭 시 본문에
# se-component.se-sticker 컴포넌트가 삽입됨(실측 검증).
STICKER_TOOLBAR_BUTTON_SELECTORS = [
    'button[data-name="sticker"]',
    "button.se-sticker-toolbar-button",
    'button[data-log="dot.sticker"]',
]
STICKER_ITEM_SELECTOR = "button.se-sidebar-element-sticker"
STICKER_PANEL_CLOSE_SELECTORS = [
    ".se-sidebar-container-sticker button.se-sidebar-close-button",
    'button[data-name="sticker"]',  # 토글 — 다시 누르면 패널 닫힘
]
STICKER_COUNT_DEFAULT = 3  # 본문에 삽입할 기본 스티커 개수 (GM 검수 시 교체 전제)
# 링크 카드(oglink) 삽입 — URL 붙여넣기 자동 카드화 (PoC 실측 2026-06-24)
# 메커니즘: 본문 끝 빈 줄에 URL 타이핑 → Enter → SmartEditor 자동 og 링크 카드 생성
# og:image 로딩은 비동기(최대 5초 대기). 감지 셀렉터:
LINK_CARD_CTA_URL = "http://wellperion.com/ko/inquiry/"  # UTM 없는 깔끔한 URL — og:image 썸네일 우선
LINK_CARD_RESULT_SELECTORS = [
    ".se-component.se-oglink",
    ".se-module-oglink",
    ".se-oglink-thumbnail",
]

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

# "작성 중인 글이 있습니다 — 이어서 작성하시겠습니까?" (임시저장 큐 이어쓰기) 팝업.
# 취소(=새 글로 시작)를 눌러야 에디터가 깨끗한 상태로 열려 제목 입력이 가능.
DRAFT_RESUME_CANCEL_SELECTORS = [
    "button.se-popup-button-cancel",
    '.se-popup-alert-confirm button:has-text("취소")',
    '.blog-se-alert button:has-text("취소")',
]

# popup killer (project_smarteditor_auto_attach v3.0)
# ⚠ [data-group='popupLayer'] 제거: 사진 첨부 방식(se-popup-image-type) 모달이 이 그룹에 속해
#   killer가 모달을 즉시 삭제 → 슬라이드 선택 불가 → 이미지 미삽입(2026-06-03 실측 root cause).
#   resume 이어쓰기 팝업은 _dismiss_draft_resume_popup가 별도로 취소하므로 popupLayer 통삭제 불필요.
POPUP_KILLER_SELECTORS = (
    ".se-popup-dim, .se-popup-alert, .se-popup-alert-confirm, "
    ".blog-se-alert, .se-help-panel"
)

# 임시저장 큐 카운트 버튼 (큐 누적 진단용 — project_draft_queue_dependency)
DRAFT_QUEUE_BUTTON_SELECTORS = [
    'button[data-click-area="tpb.draft"]',
    'button:has-text("저장")',
]

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
# 본문 조립 — body-file(가공완료 최종본) + 제목. (feedback_final_content_only_for_publish)
# -----------------------------------------------------------------
class BlogPost:
    __slots__ = ("title", "body", "image_paths", "sticker_count", "link_card_url", "tags")

    def __init__(self, title: str, body: str, image_paths: list[Path], sticker_count: int = STICKER_COUNT_DEFAULT, link_card_url: str = "", tags: list[str] | None = None) -> None:
        self.title = title
        self.body = body
        self.image_paths = image_paths
        self.sticker_count = sticker_count
        self.link_card_url = link_card_url or LINK_CARD_CTA_URL
        self.tags = tags or []  # # 포함 형태(예: ['#한남동골프', '#WELLPERION'])


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


def _strip_leading_title(title: str, body: str) -> str:
    """본문 첫 비어있지 않은 줄이 제목과 같으면 제거 — 제목 연속 표기 버그 방지 (2026-06-03 GM)."""
    if not title or not body:
        return body
    lines = body.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip() == title.strip():
        del lines[i]
        while i < len(lines) and not lines[i].strip():
            del lines[i]
        return "\n".join(lines)
    return body


def build_post(args: argparse.Namespace) -> BlogPost:
    title = (args.title or "").strip()
    body = load_body(Path(args.body_file) if args.body_file else None, args.body)
    body = _strip_leading_title(title, body)
    # ① 소제목 구조 보장 ② 인라인 CTA 줄 제거 ③ 해시태그 정렬·치환
    body, _tags = normalize_body(body, for_cafe=False)
    # 링크카드 UTM URL 생성 (campaign 없으면 body_file 경로에서 자동 슬러그)
    _campaign = args.campaign or (slugify_campaign(args.body_file) if args.body_file else "")
    import urllib.parse as _up
    _lc_params = f"utm_source=naver_blog&utm_medium=blog" + (f"&utm_campaign={_up.quote(_campaign, safe='')}" if _campaign else "")
    _link_card_url = f"http://wellperion.com/ko/inquiry/?{_lc_params}"
    image_dir = Path(args.image_dir) if args.image_dir else None
    if image_dir and not image_dir.is_absolute():
        image_dir = ROOT / image_dir
    images = collect_images(image_dir, args.image_glob)
    images = append_cta_card(images)  # 4채널 마지막 이미지로 문의 CTA 카드(IG 제외)
    sticker_count = getattr(args, "sticker_count", STICKER_COUNT_DEFAULT)
    return BlogPost(title, body, images, sticker_count, _link_card_url, _tags)


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
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="naver_blog_upload_playwright.telegram_report", ok=ok, kind="sendMessage")
        print(f"[INFO] 텔레그램 보고 {'성공' if ok else '실패'} (chat={TELEGRAM_CHAT_ID})")
    except Exception:
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="naver_blog_upload_playwright.telegram_report", ok=False, kind="sendMessage")
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


async def _dismiss_draft_resume_popup(page) -> None:
    """글쓰기 진입 시 뜨는 '작성 중인 글 이어쓰기' 팝업을 취소(새 글)로 닫는다.
    팝업이 없으면 조용히 통과. (project_draft_queue_dependency)"""
    cancel_loc, sel = await _first_locator(page, DRAFT_RESUME_CANCEL_SELECTORS)
    if cancel_loc is None:
        return
    try:
        if await cancel_loc.is_visible():
            await cancel_loc.click(force=True)
            print(f"[INFO] 이어쓰기 팝업 취소 — 새 글로 시작 ({sel!r})")
            await page.wait_for_timeout(1000)
    except Exception as e:
        print(f"[WARN] 이어쓰기 팝업 취소 실패(무시): {e}")


# -----------------------------------------------------------------
# setup — GM 수동 로그인 후 세션 저장 (비밀번호 하드코딩 없음)
# -----------------------------------------------------------------
async def run_setup() -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 네이버 블로그 SETUP — GM 수동 로그인 ===")
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
# 글쓰기 진입 + 제목·본문·이미지 입력 (draft·publish 공용 본체)
# -----------------------------------------------------------------
async def _enter_write_and_fill(page, post: BlogPost, blog_id: str | None) -> None:
    write_url = BLOG_WRITE_URL_TEMPLATE.format(blog_id=blog_id or DEFAULT_BLOG_ID)
    print(f"[INFO] 글쓰기 진입: {write_url}")
    await page.goto(write_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(3000)

    if is_login_required(page.url):
        raise RuntimeError("로그인 필요 — --mode setup 으로 세션 재저장 필요")

    # "작성 중인 글이 있습니다 — 이어서?" 팝업 먼저 취소(새 글). 안 닫으면 제목 입력 불가.
    # popup killer로 dim만 지우면 에디터 상태가 모호해지므로 취소 버튼을 직접 클릭한다.
    await _dismiss_draft_resume_popup(page)
    await _install_popup_killer(page)

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

    # 명시적 caret 분리 — 제목 입력 직후 caret/selection 이 제목 섹션에 남아 있어
    # 본문 첫 글자가 제목칸으로 흘러드는 버그(제목+본문 연속 표기) 방지 (2026-06-03 DOM 실측).
    try:
        await target.evaluate(
            """() => {
                const ae = document.activeElement;
                if (ae && ae.blur) ae.blur();
                const sel = window.getSelection && window.getSelection();
                if (sel && sel.removeAllRanges) sel.removeAllRanges();
            }"""
        )
    except Exception:
        pass

    # 본문 (임시저장 큐 누적 시 lazy load 차단 — project_draft_queue_dependency)
    body_loc, body_sel = await _first_locator(target, BODY_SELECTORS)
    if body_loc is None:
        raise RuntimeError("본문 셀렉터 미발견 (임시저장 큐 누적 시 lazy load 차단 가능 — 큐 비우기)")
    await body_loc.click()
    await page.wait_for_timeout(300)
    # caret 가드 — 클릭 후에도 selection 이 제목 섹션이면 본문 첫 글자가 제목으로 새므로 1회 재클릭.
    try:
        anchor_in_title = await target.evaluate(
            """() => {
                const s = window.getSelection && window.getSelection();
                if (!s || !s.anchorNode) return null;
                const n = s.anchorNode;
                const el = n.nodeType === 1 ? n : n.parentElement;
                return el ? !!el.closest('.se-section-documentTitle') : null;
            }"""
        )
        if anchor_in_title:
            print("[WARN] caret 가 아직 제목 섹션 — 본문 재클릭으로 분리")
            await body_loc.click()
            await page.wait_for_timeout(300)
    except Exception:
        pass
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

    # 스티커 2개 위치 지정 삽입 (GM 지시 2026-06-03):
    #   ① 본문 맨 처음 1개  ② '문의 : http://wellperion.com/ko/inquiry/' 줄 다음 1개.
    #   순서: 시작 스티커 먼저 → '문의' 줄 재탐색 후 그 다음에 삽입(텍스트 매칭이라 caret 충돌 없음).
    #   이미지는 맨 마지막에 본문 끝(Ctrl+End)으로 삽입하므로 스티커와 caret 충돌 없음.
    sticker_count = getattr(post, "sticker_count", STICKER_COUNT_DEFAULT)
    if sticker_count > 0:
        await _place_caret_at_body_start(page, target)
        await _insert_one_sticker_at_caret(page, target, "본문 맨 처음")
        # ① 본문 맨 처음 스티커 가운데정렬 (삽입 직후 1회)
        await _center_align_first_sticker(page, target)
        await _place_caret_after_inquiry_line(page, target)
        await _insert_one_sticker_at_caret(page, target, "'문의' 줄 다음")

    # 링크 카드 삽입 — UTM 추적형 URL로 문의 CTA를 og:image 썸네일 포함 링크 카드로 삽입.
    # URL 타이핑 → Enter → SmartEditor 자동 카드화. 실패해도 draft 진행.
    await _insert_link_card(page, target, url=post.link_card_url)

    # 이미지 첨부 (슬라이드 모달 단계 포함). 본문 맨 아래에 삽입. 실패해도 draft 진행.
    if post.image_paths:
        await _attach_images(page, target, post.image_paths)


async def _insert_stickers(page, target, count: int) -> int:
    """툴바 '스티커' 버튼 → 우측 패널 오픈 → 그리드에서 count개 클릭해 본문에 삽입.
    삽입된 se-component.se-sticker 컴포넌트 수를 반환. (실측 검증 2026-06-03)"""
    # caret을 본문 끝으로 (스티커가 본문 아래 들어가게)
    try:
        await page.keyboard.press("Control+End")
    except Exception:
        pass
    btn_loc, btn_sel = await _first_locator(target, STICKER_TOOLBAR_BUTTON_SELECTORS)
    if btn_loc is None:
        print("[WARN] 스티커 버튼 미발견 — 스티커 삽입 건너뜀")
        return 0

    # 삽입 전 본문 내 스티커 컴포넌트 수
    sticker_count_js = "() => document.querySelectorAll('.se-component.se-sticker').length"
    try:
        before = await target.evaluate(sticker_count_js)
    except Exception:
        before = 0

    try:
        await btn_loc.click(force=True)
        await page.wait_for_timeout(2000)  # 패널 그리드 로딩
        print(f"[INFO] 스티커 패널 오픈 ({btn_sel!r})")
    except Exception as e:
        print(f"[WARN] 스티커 패널 오픈 실패: {e}")
        return 0

    items = target.locator(STICKER_ITEM_SELECTOR)
    try:
        n = await items.count()
    except Exception:
        n = 0
    if n == 0:
        print("[WARN] 스티커 그리드 항목 0개 — 삽입 불가")
        return 0

    clicked = 0
    for i in range(min(n, count + 10)):  # 일부 비가시 항목 건너뛸 여유
        if clicked >= count:
            break
        it = items.nth(i)
        try:
            if await it.is_visible():
                await it.click(force=True)
                clicked += 1
                await page.wait_for_timeout(900)  # 본문 삽입 반영 대기
        except Exception:
            continue
    print(f"[INFO] 스티커 {clicked}개 클릭 (요청 {count}개)")

    # 패널 닫기 (스티커 버튼 토글) — 이후 임시저장 버튼 클릭 방해 방지
    try:
        await btn_loc.click(force=True)
        await page.wait_for_timeout(600)
    except Exception:
        pass

    # 실측 검증 — 본문 내 스티커 컴포넌트 증가분 확인
    try:
        after = await target.evaluate(sticker_count_js)
    except Exception:
        after = before
    inserted = after - before
    if inserted < clicked:
        print(f"[WARN] 스티커 삽입 검증 — 본문 스티커 {before}→{after} (클릭 {clicked}개 중 {inserted}개만 반영)")
    else:
        print(f"[INFO] 스티커 삽입 검증 OK — 본문 스티커 {before}→{after} ({inserted}개 추가)")
    return inserted


async def _insert_one_sticker_at_caret(page, target, label: str) -> int:
    """현재 caret 위치에 스티커 1개만 삽입. (위치 지정은 호출 측 caret 이동 책임)
    툴바 스티커 버튼으로 패널 오픈 → 첫 가시 항목 1개 클릭 → 패널 닫기 → 삽입 검증.
    삽입 성공 시 1, 실패 시 0 반환. (위치 지정 스티커 — 2026-06-03 GM 지시)"""
    btn_loc, btn_sel = await _first_locator(target, STICKER_TOOLBAR_BUTTON_SELECTORS)
    if btn_loc is None:
        print(f"[WARN] 스티커 버튼 미발견 — {label} 스티커 건너뜀")
        return 0
    sticker_count_js = "() => document.querySelectorAll('.se-component.se-sticker').length"
    try:
        before = await target.evaluate(sticker_count_js)
    except Exception:
        before = 0
    try:
        await btn_loc.click(force=True)
        await page.wait_for_timeout(2000)  # 패널 그리드 로딩
    except Exception as e:
        print(f"[WARN] 스티커 패널 오픈 실패({label}): {e}")
        return 0
    items = target.locator(STICKER_ITEM_SELECTOR)
    try:
        n = await items.count()
    except Exception:
        n = 0
    clicked = 0
    for i in range(min(n, 11)):
        it = items.nth(i)
        try:
            if await it.is_visible():
                await it.click(force=True)
                clicked = 1
                await page.wait_for_timeout(900)
                break
        except Exception:
            continue
    # 패널 닫기 (토글)
    try:
        await btn_loc.click(force=True)
        await page.wait_for_timeout(600)
    except Exception:
        pass
    try:
        after = await target.evaluate(sticker_count_js)
    except Exception:
        after = before
    inserted = after - before
    if inserted >= 1:
        print(f"[INFO] 스티커 삽입 OK — {label} (본문 스티커 {before}→{after})")
    else:
        print(f"[WARN] 스티커 삽입 실패 — {label} (본문 스티커 {before}→{after}, 클릭 {clicked})")
    return inserted


async def _center_align_first_sticker(page, target) -> None:
    """본문 맨 처음 스티커 컴포넌트에 가운데정렬 적용 (삽입 직후 1회).
    근본 수정(2026-06-25): JS style.textAlign 직접 주입은 SmartEditor가 se-l-* 클래스로
    정렬을 관리하므로 즉시 덮어써짐 → 동작 안 함.
    올바른 방법: ① 스티커 컴포넌트 클릭해 선택 → ② 플로팅 툴바 가운데정렬 버튼 클릭.
    플로팅 툴바 실패 시 폴백: se-l-center 클래스 직접 토글 + se-l-default 제거.
    실패해도 발행은 막지 않는다."""
    try:
        # ① 첫 번째 스티커 컴포넌트를 클릭해 선택 상태로 만든다
        sticker_loc = target.locator('.se-component.se-sticker').first
        if await sticker_loc.count() == 0:
            print("[WARN] 스티커 가운데정렬 — se-sticker 컴포넌트 미발견, 건너뜀")
            return
        await sticker_loc.click()
        await page.wait_for_timeout(400)

        # ② 플로팅 툴바 가운데정렬 버튼 클릭 시도
        # SmartEditor 플로팅 툴바 정렬 버튼 셀렉터 (실측 클래스명)
        align_center_selectors = [
            'button[data-name="align_center"]',
            'button[data-log="align.center"]',
            '.se-toolbar-floating button[data-name="align_center"]',
            'button.se-align-button[data-value="center"]',
            '.se-component-toolbar button[title*="가운데"]',
            '.se-component-toolbar button[aria-label*="center"]',
        ]
        toolbar_clicked = False
        for sel in align_center_selectors:
            try:
                btn = target.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(300)
                    toolbar_clicked = True
                    print(f"[INFO] 스티커 가운데정렬 — 플로팅 툴바 버튼 클릭 ({sel})")
                    break
            except Exception:
                continue

        if not toolbar_clicked:
            # 폴백: se-l-center 클래스 토글 (SmartEditor 정렬 class 직접 조작)
            applied = await target.evaluate(
                """() => {
                    const sticker = document.querySelector('.se-component.se-sticker');
                    if (!sticker) return false;
                    sticker.classList.remove('se-l-default', 'se-l-left', 'se-l-right');
                    sticker.classList.add('se-l-center');
                    // section 내부도 동일하게
                    const section = sticker.querySelector('.se-section-sticker');
                    if (section) {
                        section.classList.remove('se-l-default', 'se-l-left', 'se-l-right');
                        section.classList.add('se-l-center');
                    }
                    return true;
                }"""
            )
            if applied:
                print("[INFO] 스티커 가운데정렬 — 폴백 se-l-center 클래스 적용")
            else:
                print("[WARN] 스티커 가운데정렬 폴백도 실패 (발행 계속)")
    except Exception as e:
        print(f"[WARN] 스티커 가운데정렬 실패(발행 계속): {e}")


async def _place_caret_at_body_start(page, target) -> None:
    """본문 첫 문단을 클릭하고 Ctrl+Home으로 caret을 본문 맨 처음으로 이동."""
    try:
        body_loc, _ = await _first_locator(target, BODY_SELECTORS)
        if body_loc is not None:
            await body_loc.click()
        await page.keyboard.press("Control+Home")
        await page.wait_for_timeout(300)
    except Exception as e:
        print(f"[WARN] 본문 시작 caret 이동 실패: {e}")


async def _place_caret_after_inquiry_line(page, target) -> bool:
    """본문에서 '문의' 텍스트가 있는 문단을 찾아 그 문단 끝으로 caret 이동.
    찾으면 True. 못 찾으면 본문 끝(Ctrl+End)으로 폴백하고 False 반환."""
    try:
        # SmartEditor 문단(span.se-text-paragraph 등)에서 '문의' 포함 노드를 찾아 클릭
        para = target.locator('p.se-text-paragraph:has-text("문의"), .se-text-paragraph:has-text("문의")').last
        if await para.count() > 0:
            await para.click()
            # 문단 끝으로 caret (End)
            await page.keyboard.press("End")
            await page.wait_for_timeout(300)
            print("[INFO] '문의' 줄 끝으로 caret 이동")
            return True
    except Exception as e:
        print(f"[WARN] '문의' 줄 탐색 실패: {e}")
    try:
        await page.keyboard.press("Control+End")
        await page.wait_for_timeout(200)
    except Exception:
        pass
    print("[WARN] '문의' 줄 미발견 — 본문 끝으로 폴백")
    return False


async def _insert_link_card(page, target, url: str = LINK_CARD_CTA_URL) -> bool:
    """본문 끝에 URL을 타이핑해 SmartEditor 자동 og 링크 카드를 삽입한다.
    메커니즘(PoC 실측 2026-06-24): 빈 줄에 URL 입력 → Enter → 에디터가 자동으로
    .se-component.se-oglink 컴포넌트를 생성 + og:image 썸네일 비동기 로딩(최대 5초).
    삽입 성공 시 True, 실패 시 False 반환."""
    try:
        # 본문 끝으로 caret 이동
        await page.keyboard.press("Control+End")
        await page.wait_for_timeout(300)
        # 빈 줄 확보
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)
        # URL 타이핑 (keyboard.type — clipboard 의존 없음)
        await page.keyboard.type(url, delay=10)
        await page.wait_for_timeout(300)
        # Enter — SmartEditor 링크 카드 변환 트리거
        await page.keyboard.press("Enter")
        print(f"[INFO] 링크 카드 URL 입력 완료: {url}")
        # og:image 비동기 로딩 대기 (최대 5초 폴링)
        detected = False
        for _ in range(10):
            await page.wait_for_timeout(500)
            for sel in LINK_CARD_RESULT_SELECTORS:
                try:
                    cnt = await target.evaluate(f"() => document.querySelectorAll('{sel}').length")
                    if cnt > 0:
                        detected = True
                        break
                except Exception:
                    pass
            if detected:
                break
        if detected:
            # og:image 썸네일 포함 여부
            thumb_cnt = await target.evaluate(
                "() => document.querySelectorAll('.se-oglink-thumbnail img, .se-module-oglink img').length"
            )
            print(f"[INFO] 링크 카드 삽입 성공 — og:image 썸네일: {'있음' if thumb_cnt > 0 else '로딩중/없음'} ({thumb_cnt}개)")
            # 근본 수정(2026-06-25 버그B): oglink 카드 변환 후에도 URL 텍스트 문단이 잔류함.
            # URL 입력 줄(se-text-paragraph 중 해당 URL 텍스트 포함 노드)을 찾아 삭제한다.
            url_domain = url.split("//")[-1].split("/")[0]  # e.g. 'wellperion.com'
            removed = await target.evaluate(
                """(domain) => {
                    let removed = 0;
                    // se-text-paragraph 중 URL 도메인 텍스트를 포함한 문단 제거
                    const paras = document.querySelectorAll('p.se-text-paragraph, .se-text-paragraph');
                    paras.forEach(p => {
                        const txt = p.textContent || '';
                        if (txt.includes(domain) && (txt.includes('http') || txt.includes('://') || txt.includes('inquiry'))) {
                            // 상위 se-component(텍스트 컴포넌트)까지 올라가 제거
                            let node = p;
                            while (node && node.parentElement) {
                                if (node.classList && node.classList.contains('se-component')) {
                                    node.parentElement.removeChild(node);
                                    removed++;
                                    return;
                                }
                                node = node.parentElement;
                            }
                            // se-component 못 찾으면 문단 자체 제거
                            p.parentElement && p.parentElement.removeChild(p);
                            removed++;
                        }
                    });
                    return removed;
                }""",
                url_domain
            )
            if removed > 0:
                print(f"[INFO] 링크 카드 URL 텍스트 잔류 제거 완료 ({removed}개 문단)")
            else:
                print("[INFO] 링크 카드 URL 텍스트 잔류 없음 (정상)")
        else:
            print("[WARN] 링크 카드 컴포넌트 미감지 (5초 대기 후) — 평문 URL로 폴백")
        return detected
    except Exception as e:
        print(f"[WARN] 링크 카드 삽입 실패(무시): {e}")
        return False


async def _attach_images(page, target, image_paths: list[Path]) -> int:
    """사진 버튼 클릭→file_chooser로 N장 주입→'사진 첨부 방식' 모달에서 슬라이드 선택→본문 맨 아래 삽입.
    실제 삽입된 <img> 개수를 반환. (2026-06-03 실측 root cause 반영)

    핵심 수정 2가지:
      1) popup killer가 image-type 모달(data-group=popupLayer)을 지우면 슬라이드 선택 불가 →
         POPUP_KILLER_SELECTORS 에서 popupLayer 제거 완료.
      2) #image-type-slide(input)는 label이 포인터를 가로채므로 label[for=...]를 클릭한다.
    """
    btn_loc, btn_sel = await _first_locator(target, IMAGE_TOOLBAR_BUTTON_SELECTORS)
    if btn_loc is None:
        print("[WARN] 사진 추가 버튼 미발견 — 이미지 첨부 건너뜀")
        return 0
    # 본문 끝으로 caret 이동 (이미지가 본문 아래 들어가게)
    try:
        await page.keyboard.press("Control+End")
    except Exception:
        pass

    # 삽입 전 본문 이미지 수 (검증 기준선)
    try:
        before = await page.evaluate("(sel)=>document.querySelectorAll(sel).length", INSERTED_IMAGE_SELECTOR)
    except Exception:
        before = 0

    # 사진 버튼 클릭 → 네이티브 file_chooser 가로채 N장 주입
    try:
        async with page.expect_file_chooser(timeout=8000) as fc_info:
            await btn_loc.click(force=True)
        fc = await fc_info.value
        await fc.set_files([str(p) for p in image_paths])
        print(f"[INFO] 이미지 {len(image_paths)}장 주입 (file_chooser)")
    except Exception as e:
        print(f"[WARN] file_chooser 경로 실패: {e}")
        return 0

    # '사진 첨부 방식' 모달 대기 → 슬라이드 라벨 클릭 (input은 label이 포인터 가로챔)
    slide = page.locator(IMAGE_TYPE_SLIDE_SELECTOR).first
    try:
        await slide.wait_for(state="visible", timeout=10000)
        await slide.click()
        print("[INFO] 사진 첨부 방식 = 슬라이드 선택 (label[for=image-type-slide])")
    except Exception as e:
        print(f"[WARN] 슬라이드 옵션 클릭 실패: {e}")
        # 폴백: input 강제 클릭
        try:
            await page.locator(IMAGE_TYPE_SLIDE_INPUT_SELECTOR).first.click(force=True)
            print("[INFO] 슬라이드 폴백 — input 강제 클릭")
        except Exception as e2:
            print(f"[WARN] 슬라이드 폴백도 실패: {e2}")
            return 0

    # 업로드+본문 삽입 대기 — <img> 개수가 before+len(image_paths) 도달할 때까지 폴링(최대 40초)
    target_count = before + len(image_paths)
    after = before
    for _ in range(40):
        await page.wait_for_timeout(1000)
        try:
            after = await page.evaluate("(sel)=>document.querySelectorAll(sel).length", INSERTED_IMAGE_SELECTOR)
        except Exception:
            after = before
        if after >= target_count:
            break
    inserted = after - before
    if inserted >= len(image_paths):
        print(f"[INFO] 이미지 삽입 검증 OK — 본문 <img> {before}→{after} ({inserted}장 슬라이드 삽입)")
    elif inserted > 0:
        print(f"[WARN] 이미지 일부 삽입 — 본문 <img> {before}→{after} (요청 {len(image_paths)}장 중 {inserted}장)")
    else:
        print(f"[WARN] 이미지 삽입 검증 실패 — 본문 <img> {before}→{after} (0장 삽입)")
    return inserted


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
        # 편집화면 상단 캡처 — 버그 수정 라이브 검증용 (2026-06-25)
        _verify_shot = EVIDENCE_DIR / "blog_fix_verify_top.png"
        try:
            # DOM 검증 — 버그A: 스티커 정렬 class / 버그B: URL 텍스트 잔류
            _sticker_class = await page.evaluate(
                "() => { const s = document.querySelector('.se-component.se-sticker'); return s ? s.className : 'NOT_FOUND'; }"
            )
            _url_remain = await page.evaluate(
                "() => { const paras = [...document.querySelectorAll('.se-text-paragraph')]; "
                "return paras.filter(p => p.textContent.includes('inquiry')).map(p => p.textContent.trim().slice(0,80)); }"
            )
            print(f"[VERIFY-A] 스티커 컴포넌트 class: {_sticker_class}")
            print(f"[VERIFY-B] 본문 내 'inquiry' 포함 문단: {_url_remain}")
            # 편집화면 iframe 내부 첫 스티커 컴포넌트를 뷰포트에 맞춰 스크롤 후 스크린샷
            await page.evaluate(
                "() => { const s = document.querySelector('.se-component.se-sticker'); if (s) s.scrollIntoView({block:'start'}); else window.scrollTo(0,0); }"
            )
            await page.wait_for_timeout(600)
            await page.screenshot(path=str(_verify_shot), full_page=False)
            print(f"[INFO] 편집화면 상단 스크린샷 저장 → {_verify_shot}")
        except Exception as _ve:
            print(f"[WARN] 검증 스크린샷 실패(무시): {_ve}")
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
        # ── 임시저장 직후 DOM 검증 (에디터 페이지 유지 상태) ──
        try:
            _ev_dir = EVIDENCE_DIR
            # 맨위 스크린샷
            await page.evaluate("window.scrollTo(0,0)")
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(_ev_dir / "reverify_blog_top.png"), full_page=False)
            print(f"[REVERIFY-SNAP] reverify_blog_top.png")
            # A) 본문 첫 300자
            _body300 = await page.evaluate("""
(function(){
    var paras = document.querySelectorAll('.se-text-paragraph');
    var out = '';
    for(var i=0;i<paras.length;i++){ out += (paras[i].innerText||'') + '\\n'; }
    return out.slice(0,300);
})()
""")
            print(f"[REVERIFY-A] 본문 첫 300자:\n{_body300}")
            # B) 소제목 다음 노드 인접 여부
            _sub_adj = await page.evaluate("""
(function(){
    var comps = Array.from(document.querySelectorAll('.se-component'));
    var res = [];
    comps.forEach(function(c,i){
        var t = c.innerText||'';
        if(t.indexOf('▍')!==-1){
            var nxt = comps[i+1];
            res.push({
                subtitle: t.trim().slice(0,60),
                nextText: nxt?(nxt.innerText||'').trim().slice(0,80):'(없음)',
                nextEmpty: nxt?((nxt.innerText||'').trim()===''):true
            });
        }
    });
    return res;
})()
""")
            import json as _json
            print(f"[REVERIFY-B] 소제목-내용 인접:\n{_json.dumps(_sub_adj, ensure_ascii=False, indent=2)}")
            # C) URL 텍스트 잔류
            _url_txt = await page.evaluate("""
(function(){
    var paras = document.querySelectorAll('.se-text-paragraph');
    var found = [];
    for(var i=0;i<paras.length;i++){
        var t = paras[i].innerText||'';
        if(t.indexOf('wellperion.com/ko/inquiry')!==-1){ found.push(t.trim().slice(0,120)); }
    }
    return found;
})()
""")
            print(f"[REVERIFY-C] URL 텍스트 잔류: {_url_txt}")
            # D) 스티커 class
            _stk_cls = await page.evaluate("""
(function(){
    var ss = document.querySelectorAll('.se-sticker');
    var out=[];
    for(var i=0;i<ss.length;i++){ out.push({idx:i,cls:ss[i].className}); }
    return out;
})()
""")
            print(f"[REVERIFY-D] 스티커 class: {_stk_cls}")
            # 임시저장 개수 배지
            _draft_badge = await page.evaluate("""
(function(){
    var els = document.querySelectorAll('[class*="save"] [class*="count"], [class*="draft"] [class*="count"], .save_count, .draft_count');
    var out=[];
    els.forEach(function(e){ out.push(e.innerText||e.textContent); });
    return out;
})()
""")
            print(f"[REVERIFY-DRAFT-COUNT] 배지: {_draft_badge}")
            # 중간 스크린샷
            await page.evaluate("window.scrollTo(0,700)")
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(_ev_dir / "reverify_blog_mid.png"), full_page=False)
            print(f"[REVERIFY-SNAP] reverify_blog_mid.png")
        except Exception as _re:
            print(f"[WARN] reverify DOM 추출 실패(무시): {_re}")
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
# 발행 레이어 태그 입력 (publish 모드 전용)
# -----------------------------------------------------------------
# 네이버 블로그 발행 설정 레이어(카테고리·공개설정·태그편집)에만 태그칸 존재.
# 태그 입력 필드 셀렉터 후보 (실측 PoC 2026-06-25):
PUBLISH_TAG_INPUT_SELECTORS = [
    "input#tag-input",
    ".tag_input input",
    "input[placeholder*='태그']",
    ".se_tag_area input",
    ".publish_layer input[type='text']",
    "div[class*='tag'] input",
    "input[class*='tag']",
]
# 공개설정 전체공개 셀렉터 (발행 레이어 내)
PUBLISH_PUBLIC_SELECTORS = [
    "input#open-type-all",
    "label[for='open-type-all']",
    "input[value='all']",
]


async def _fill_publish_tags(page, tags: list[str]) -> int:
    """발행 설정 레이어가 열린 상태에서 태그 입력칸을 찾아 tags 를 한 개씩 입력.
    태그는 # 없는 텍스트로 입력 후 Enter(네이버 방식). 입력된 태그 수 반환.
    실패해도 발행은 막지 않음(WARN 출력 후 0 반환)."""
    if not tags:
        return 0

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    # 발행 레이어 스크린샷 (태그칸 PoC 증거)
    try:
        await page.screenshot(path=str(EVIDENCE_DIR / "blog_publish_tag_field.png"))
        print(f"[INFO] 발행 레이어 스크린샷 저장 → {EVIDENCE_DIR / 'blog_publish_tag_field.png'}")
    except Exception:
        pass

    # 태그 입력 필드 탐색
    tag_input = None
    found_sel = None
    for sel in PUBLISH_TAG_INPUT_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                # 가시성 확인
                if await loc.is_visible():
                    tag_input = loc
                    found_sel = sel
                    print(f"[INFO] 태그 입력칸 발견: {sel!r}")
                    break
        except Exception:
            continue

    if tag_input is None:
        # 폴백: DOM 전체에서 input type=text 탐색 + 위치 기반 후보
        print("[WARN] 표준 태그 셀렉터 미발견 — DOM input 전수 탐색")
        try:
            # 발행 레이어 내부의 모든 text input 수집
            inputs_info = await page.evaluate("""
() => {
    const inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')];
    return inputs.map((inp, i) => ({
        idx: i,
        id: inp.id || '',
        name: inp.name || '',
        placeholder: inp.placeholder || '',
        className: inp.className || '',
        visible: inp.offsetParent !== null,
        rect: (() => { const r = inp.getBoundingClientRect(); return {top: Math.round(r.top), left: Math.round(r.left), w: Math.round(r.width)}; })()
    }));
}
""")
            print(f"[INFO] DOM input 후보:\n{inputs_info}")
        except Exception as e:
            print(f"[WARN] DOM input 탐색 실패: {e}")
        print("[WARN] 태그 입력칸 미발견 — 태그 입력 건너뜀 (발행 계속)")
        return 0

    # 공개설정 전체공개 확인
    for pub_sel in PUBLISH_PUBLIC_SELECTORS:
        try:
            pub_loc = page.locator(pub_sel).first
            if await pub_loc.count() > 0:
                await pub_loc.click(force=True)
                print(f"[INFO] 공개설정 전체공개 확인 ({pub_sel!r})")
                await page.wait_for_timeout(300)
                break
        except Exception:
            continue

    # 태그 # 제거 후 한 개씩 입력 + Enter
    inserted = 0
    for raw_tag in tags:
        tag_text = raw_tag.lstrip("#").strip()
        if not tag_text:
            continue
        try:
            await tag_input.click()
            await page.wait_for_timeout(200)
            await tag_input.fill("")  # 기존 내용 초기화
            await page.keyboard.type(tag_text, delay=30)
            await page.wait_for_timeout(300)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(400)
            inserted += 1
            print(f"[INFO] 태그 입력: #{tag_text}")
        except Exception as e:
            print(f"[WARN] 태그 입력 실패 (#{tag_text}): {e}")

    # 태그 입력 후 스크린샷 (증거)
    try:
        await page.screenshot(path=str(EVIDENCE_DIR / "blog_publish_tags_filled.png"))
        print(f"[INFO] 태그 입력 완료 스크린샷 → {EVIDENCE_DIR / 'blog_publish_tags_filled.png'}")
    except Exception:
        pass

    print(f"[INFO] 태그 입력 완료: {inserted}/{len(tags)}개 ({found_sel!r})")
    return inserted


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
        await page.wait_for_timeout(2000)  # 발행 레이어 완전 로딩 대기

        # ── 발행 설정 레이어 내 태그 입력 ──────────────────────────
        if post.tags:
            print(f"[INFO] 태그 {len(post.tags)}개 입력 시작: {post.tags}")
            await _fill_publish_tags(page, post.tags)
        else:
            print("[INFO] 태그 없음 — 태그 입력 건너뜀")

        # ── 발행 직전 스크린샷 (증거) ───────────────────────────────
        try:
            await page.screenshot(path=str(EVIDENCE_DIR / "blog_publish_before_confirm.png"))
            print(f"[INFO] 발행 직전 스크린샷 → {EVIDENCE_DIR / 'blog_publish_before_confirm.png'}")
        except Exception:
            pass

        # ── 최종 발행 확인 버튼 클릭 ────────────────────────────────
        # 태그 입력 후 발행 확인 버튼 재탐색 (레이어 구조상 동일 버튼이나 태그 입력 후 재확인)
        conf_loc, conf_sel = await _first_locator(page, PUBLISH_CONFIRM_SELECTORS)
        if conf_loc is None:
            raise RuntimeError("발행 확인 버튼 미발견")
        await conf_loc.click(force=True)
        print(f"[INFO] 발행 확인 클릭 ({conf_sel!r})")
        await page.wait_for_timeout(6000)  # 발행 완료 + 리다이렉트 대기

        # ── 발행 완료 스크린샷 ──────────────────────────────────────
        await page.screenshot(path=str(shot))
        print(f"[INFO] 발행 완료 — 스크린샷 {shot}")

        # ── 공개 글 URL 회수 ─────────────────────────────────────────
        # 네이버 블로그 발행 후 이동 패턴:
        #   - blog.naver.com/wellperion/{postNo}  (일반 뷰)
        #   - blog.naver.com/PostView.naver?...   (구형)
        #   - blog.naver.com/wellperion/postview/... (신형)
        # URL이 에디터 페이지에 머물면 history 탐색도 시도.
        post_url = ""
        try:
            current_url = page.url
            # 발행 후 에디터 URL에 머물러 있을 경우 — 잠시 더 대기
            if "postwrite" in current_url or "PostWriteForm" in current_url:
                await page.wait_for_timeout(3000)
                current_url = page.url
            if current_url and "blog.naver.com" in current_url and "postwrite" not in current_url:
                post_url = current_url
                print(f"[INFO] 공개 글 URL (자동 이동): {post_url}")
            else:
                # 직접 최신 게시물 URL 탐색: wellperion 블로그 목록 첫 번째 글 URL 추출
                print("[INFO] 자동 이동 없음 — 블로그 목록에서 최신 글 URL 탐색")
                await page.goto(
                    f"https://blog.naver.com/{args.blog_id or DEFAULT_BLOG_ID}",
                    wait_until="domcontentloaded", timeout=15000
                )
                await page.wait_for_timeout(2000)
                # 최신 글 링크 추출
                latest_url = await page.evaluate(r"""
() => {
    // 블로그 목록 최신 글 앵커 탐색 (다양한 레이아웃 대응)
    const candidates = [
        ...document.querySelectorAll('a[href*="/wellperion/"]'),
        ...document.querySelectorAll('a[href*="PostView"]'),
    ];
    for (const a of candidates) {
        const href = a.href || '';
        // 숫자 postNo 패턴: /wellperion/숫자
        if (/blog\.naver\.com\/wellperion\/\d+/.test(href)) return href;
        if (/blog\.naver\.com\/PostView/.test(href)) return href;
    }
    return '';
}
""")
                if latest_url and "blog.naver.com" in latest_url:
                    post_url = latest_url
                    print(f"[INFO] 공개 글 URL (목록 탐색): {post_url}")
                    await page.screenshot(path=str(EVIDENCE_DIR / "blog_publish_after_list.png"))
                else:
                    print("[WARN] 공개 글 URL 자동 회수 실패 — 블로그 관리자에서 직접 확인 필요")
        except Exception as _ue:
            print(f"[WARN] URL 회수 실패(무시): {_ue}")

        # stdout 에 단일 발행 URL 출력 (파싱 기준선)
        if post_url:
            print(f"post_url: {post_url}")
        else:
            print("post_url: (회수불가)")
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
    parser.add_argument("--campaign", default=None, help="UTM campaign 슬러그 (미지정 시 생략·하위호환)")
    parser.add_argument("--image-dir", dest="image_dir", default=None, help="이미지 폴더")
    parser.add_argument("--image-glob", dest="image_glob", default="blog_*.jpg", help="이미지 파일명 패턴")
    parser.add_argument("--blog-id", dest="blog_id", default=None, help="본인 블로그 ID (글쓰기 URL용)")
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
