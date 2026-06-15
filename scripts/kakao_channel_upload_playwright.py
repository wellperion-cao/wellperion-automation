# scripts/kakao_channel_upload_playwright.py
# v0.2 — 카카오 채널(소식) 반자동 업로더
#         (네이버 발행기 패턴 차용: Playwright + Persistent Profile 1회 로그인 세션)
#
# 정책: 종착지=임시저장(draft). draft 모드 = '발행시간:임시저장' 선택 후 등록(=임시저장, 비공개).
#       publish 모드 = GM go 가드 통과 시에만 '발행시간:지금' 선택 후 등록(실 발행).
#       비밀번호 하드코딩 없음. Persistent Profile 세션 재사용. 토큰 stdout 노출 금지.
#
# 소식 작성 경로 (2026-06-03 DOM 실측):
#   center-pf.kakao.com → business.kakao.com 자동 리다이렉트 → /_{채널ID}/posts (소식 올리기)
#   페이지 상단 인라인 에디터. iframe 없음(단일 SPA).
#   - 제목: input.tf_g[placeholder='제목']
#   - 본문: textarea.textbox___...  (placeholder '...새 이야기를 들려주세요.')
#   - 이미지: input[type=file].uploadInput  (multiple, 직접 set_input_files)
#   - 발행시간 radio: input[name='status'] value=published(지금)/draft(임시저장)/scheduled(예약)
#   - 등록 버튼: button[type=submit] 텍스트 '등록' (입력 채워지면 활성화)
#
# 사전 설치 (GM 로컬 1회):
#   python -m venv .venv ; .venv\Scripts\activate
#   pip install playwright ; playwright install chromium
#
# 모드:
#   setup  : 최초 1회 GM 수동 로그인 → Persistent Profile 세션 저장 (Enter 불필요·자동 감지)
#   dryrun : 브라우저/로그인 없이 본문 조립·이미지 수집·경로·모드 가드 점검만 (기본)
#   draft  : [스텁] 소식 작성 → 임시저장 (에디터 자동입력 미구현 — DOM 실측 후 다음 단계)
#   publish: [스텁] 실 발행 — GM go 가드(--i-am-sure 또는 WELLPERION_PUBLISH_GO=1) 통과 전제
#
# 실행 예:
#   python scripts\kakao_channel_upload_playwright.py --mode setup
#   python scripts\kakao_channel_upload_playwright.py --mode dryrun ^
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
PERSISTENT_PROFILE_DIR = ROOT / "profiles" / "kakao-channel"  # 카카오 채널 관리자 로그인 세션
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"

# 카카오 채널 관리자 홈. 미로그인 시 accounts.kakao.com 으로 리다이렉트된다.
# 따라서 setup은 관리자 홈으로 goto 후 "로그인 페이지 이탈(center-pf 안착) + 쿠키 존재"를 세션 시그널로 본다.
KAKAO_CHANNEL_ADMIN_URL = "https://center-pf.kakao.com/"
# 로그인 페이지(미인증 상태) 시그널 — URL 기반
LOGIN_REDIRECT_SIGNALS = ("accounts.kakao.com", "/login", "logon")
# 로그인 성공 안착 시그널 — 관리자 홈 도메인으로 돌아옴
SESSION_LANDED_HOST = "center-pf.kakao.com"

# 웰페리온 채널 ID + 소식 작성(소식 올리기) 페이지 — center-pf → business.kakao.com 리다이렉트 (2026-06-03 실측)
KAKAO_CHANNEL_ID = "_cgxiKj"  # 웰페리온 채널
KAKAO_POSTS_URL = f"https://business.kakao.com/{KAKAO_CHANNEL_ID}/posts"

# 소식 에디터 DOM selector (2026-06-03 실측)
SEL_TITLE = "input.tf_g[placeholder='제목']"          # 제목 input
SEL_BODY = "textarea.textbox___1Ig6T"                # 본문 textarea
SEL_FILE = "input[type=file].uploadInput"            # 이미지 file input (multiple)
SEL_STATUS_DRAFT = "input[name='status'][value='draft']"        # 발행시간: 임시저장
SEL_STATUS_PUBLISH = "input[name='status'][value='published']"  # 발행시간: 지금
SEL_LABEL_DRAFT = "label:has-text('임시저장')"
SEL_LABEL_PUBLISH = "label:has-text('지금')"
SEL_SUBMIT = "button[type='submit']:has-text('등록')"  # 등록 버튼

# 콘텐츠 소스 — instagram/{폴더}/output(카카오 채널)/ + kakao_copy.md
OUTPUT_SUBDIR_NAME = "output(카카오 채널)"
COPY_FILENAME = "kakao_copy.md"
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
# 콘텐츠 조립 — kakao_copy.md (제목/본문 --- 구분) + output(카카오 채널)/ 이미지
# -----------------------------------------------------------------
class ChannelPost:
    __slots__ = ("title", "body", "image_paths")

    def __init__(self, title: str, body: str, image_paths: "list[Path]") -> None:
        self.title = title
        self.body = body
        self.image_paths = image_paths


def parse_copy_file(copy_file: Path) -> "tuple[str, str]":
    """kakao_copy.md 파싱. 첫 '---' 구분선 기준 위=제목 / 아래=본문.
    '---'가 없으면 첫 비어있지 않은 줄=제목, 나머지=본문."""
    text = copy_file.read_text(encoding="utf-8")
    # 제목 --- 본문 형식 (줄 단독 '---' 구분)
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
    """--content-dir(instagram/{폴더}) 기준 output(카카오 채널)/·kakao_copy.md 경로 산출.
    --image-dir/--body-file 명시 시 그 값을 우선한다."""
    content_dir = Path(args.content_dir) if args.content_dir else None
    if content_dir and not content_dir.is_absolute():
        content_dir = ROOT / content_dir

    # 이미지 폴더
    if args.image_dir:
        image_dir = Path(args.image_dir)
        if not image_dir.is_absolute():
            image_dir = ROOT / image_dir
    elif content_dir:
        image_dir = content_dir / OUTPUT_SUBDIR_NAME
    else:
        image_dir = None

    # 카피 파일
    if args.body_file:
        copy_file = Path(args.body_file)
        if not copy_file.is_absolute():
            copy_file = ROOT / copy_file
    elif content_dir:
        copy_file = content_dir / COPY_FILENAME
    else:
        copy_file = None

    return image_dir, copy_file


def build_post(args: argparse.Namespace) -> ChannelPost:
    image_dir, copy_file = _resolve_content_paths(args)
    title = (args.title or "").strip()
    body = ""
    if copy_file and copy_file.exists():
        parsed_title, parsed_body = parse_copy_file(copy_file)
        if not title:
            title = parsed_title
        body = parsed_body
    # 문의 CTA URL에 카카오 채널 utm_source 부착 (발행 직전 원본 미변경·중복 안전)
    body = apply_cta_utm(body, "kakao")
    images = collect_images(image_dir, args.image_glob)
    return ChannelPost(title, body, images)


def validate_post(post: ChannelPost, require_images: bool) -> "list[str]":
    errs: "list[str]" = []
    if not post.title:
        errs.append("제목 비어 있음 (kakao_copy.md 제목 또는 --title 필요)")
    if not post.body:
        errs.append("본문 비어 있음 (kakao_copy.md 본문 또는 --body-file 필요)")
    if require_images and not post.image_paths:
        errs.append("이미지 0장 (output(카카오 채널)/ 또는 --image-dir 확인)")
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
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="kakao_channel_upload_playwright.telegram_report", ok=ok, kind="sendMessage")
        print(f"[INFO] 텔레그램 보고 {'성공' if ok else '실패'} (chat={TELEGRAM_CHAT_ID})")
    except Exception:
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="kakao_channel_upload_playwright.telegram_report", ok=False, kind="sendMessage")
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
    print("[INFO] === 카카오 채널 DRYRUN (브라우저/로그인 없음) ===")
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
    print(f"        관리자 홈   : {KAKAO_CHANNEL_ADMIN_URL}")
    print(f"        로그인 시그널: {LOGIN_REDIRECT_SIGNALS}")
    print(f"        안착 시그널 : '{SESSION_LANDED_HOST}' 도메인 + 로그인 페이지 이탈")
    print("[INFO] --- 모드 가드 점검 ---")
    print(f"        publish GM go 가드: --i-am-sure 또는 {PUBLISH_GO_ENV_KEY}=1 필요")
    print(f"        현재 --i-am-sure={args.i_am_sure} / env {PUBLISH_GO_ENV_KEY}={os.environ.get(PUBLISH_GO_ENV_KEY, '(unset)')}")
    print(f"[INFO] 소식 작성 URL: {KAKAO_POSTS_URL}")
    print("[INFO] draft = 임시저장 / publish = 실 발행(GM go 가드 필요). 에디터 자동입력 구현됨(v0.2).")
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
# 세션 시그널: URL이 center-pf.kakao.com 안착(로그인 페이지 이탈) + 쿠키 존재
# -----------------------------------------------------------------
async def run_setup() -> int:
    import asyncio
    async_playwright = _import_playwright()
    print("[INFO] === 카카오 채널 SETUP — GM 수동 로그인 ===")
    print(f"[INFO] 프로필 저장: {PERSISTENT_PROFILE_DIR}")
    p, context = await _launch_context(async_playwright)
    # 기존(옛 계정) 세션 제거 — 새 로그인만 감지하도록 로그아웃 상태로 시작
    try:
        await context.clear_cookies()
        print("[INFO] 기존 세션 비움 — 새 계정으로 로그인하세요.")
    except Exception as e:
        print(f"[WARN] 기존 세션 비우기 실패(무시): {e}")
    page = await context.new_page()
    await page.goto(KAKAO_CHANNEL_ADMIN_URL, wait_until="domcontentloaded", timeout=30_000)
    print("[INFO] 브라우저에서 카카오 로그인을 완료하세요 — 로그인 감지 시 자동 저장됩니다.")
    print("[INFO] (Enter 불필요. 최대 5분 대기, 로그인 끝나면 자동 마무리)")

    has_session = False
    waited, deadline = 0, 300  # 초
    while waited < deadline:
        try:
            current_url = page.url
            cookies = await context.cookies()
        except Exception:
            break  # 브라우저 창을 GM이 닫음
        # 카카오 인증 쿠키(_kau/_kawlt 등) 보유 = 로그인 성립
        # (center-pf.kakao.com → business.kakao.com 리다이렉트라 URL 판정 대신 쿠키 판정, 실측 2026-06-03)
        if any(c.get("name") in ("_kau", "_kawlt", "_kawltea", "_karmt") for c in cookies):
            has_session = True
            break
        await asyncio.sleep(3)
        waited += 3
    if has_session:
        await asyncio.sleep(2)  # 쿠키가 디스크 프로필에 안착할 여유
        print("[INFO] 카카오 채널 세션 확인 — 저장 완료 (값 비공개: ****)")
    else:
        print("[WARN] 5분 내 로그인 미완료(관리자 홈 미안착) — 다시 실행하세요.")
    await context.close()
    await p.stop()
    print("[INFO] === SETUP 완료 ===")
    return 0


# -----------------------------------------------------------------
# 에디터 자동입력 공통 — 소식 작성 페이지(/posts) 인라인 에디터
#   제목 → 본문 → 이미지 첨부. 발행시간 radio 선택·등록 클릭은 호출부에서 결정.
#   (press_sequentially 사용 — React onChange 트리거 + 한글 IME 안전)
# -----------------------------------------------------------------
async def _fill_editor(page, post: ChannelPost) -> None:
    import asyncio
    # 소식 작성 페이지 진입 (center-pf → business.kakao.com 리다이렉트 흡수)
    await page.goto(KAKAO_POSTS_URL, wait_until="domcontentloaded", timeout=60_000)
    await asyncio.sleep(6)  # SPA 에디터 렌더 대기

    # 제목
    title_loc = page.locator(SEL_TITLE)
    await title_loc.first.click()
    await title_loc.first.fill("")
    await title_loc.first.press_sequentially(post.title, delay=15)
    print(f"[INFO] 제목 입력 완료 ({len(post.title)}자)")

    # 본문
    body_loc = page.locator(SEL_BODY)
    await body_loc.first.click()
    await body_loc.first.fill("")
    await body_loc.first.press_sequentially(post.body, delay=4)
    print(f"[INFO] 본문 입력 완료 ({len(post.body)}자)")

    # 이미지 첨부 (file input 직접 — 한 번에 multiple)
    if post.image_paths:
        file_loc = page.locator(SEL_FILE)
        await file_loc.first.set_input_files([str(p) for p in post.image_paths])
        # 업로드(썸네일 생성) 대기 — 장수에 비례
        await asyncio.sleep(3 + min(len(post.image_paths), 10))
        print(f"[INFO] 이미지 {len(post.image_paths)}장 첨부 완료")
    else:
        print("[WARN] 첨부 이미지 0장 — 텍스트만 입력")


async def _select_status(page, want_draft: bool) -> bool:
    """발행시간 radio 선택. want_draft=True → 임시저장, False → 지금(발행).
    선택 성공 여부 반환."""
    import asyncio
    label_sel = SEL_LABEL_DRAFT if want_draft else SEL_LABEL_PUBLISH
    radio_sel = SEL_STATUS_DRAFT if want_draft else SEL_STATUS_PUBLISH
    try:
        await page.locator(label_sel).first.click(timeout=5_000)
    except Exception as e:
        print(f"[WARN] 발행시간 라벨 클릭 실패: {e}")
    await asyncio.sleep(0.5)
    try:
        checked = await page.locator(radio_sel).first.is_checked()
    except Exception:
        checked = False
    return checked


# -----------------------------------------------------------------
# draft — 소식 임시저장. 제목·본문·이미지 입력 → '발행시간:임시저장' → 등록(임시저장, 비공개).
#         발행(공개) 절대 안 함.
# -----------------------------------------------------------------
async def run_draft(args: argparse.Namespace) -> int:
    import asyncio
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 미존재 — 먼저 --mode setup 실행 필요.")
        return 3
    post = build_post(args)
    print("[INFO] === 카카오 채널 DRAFT (임시저장) ===")
    print(f"[INFO] 제목: {post.title or '(비어 있음)'} / 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")
    errs = validate_post(post, require_images=False)
    if errs:
        print("[ERROR] 콘텐츠 검증 실패:")
        for e in errs:
            print(f"        · {e}")
        return 4

    async_playwright = _import_playwright()
    p, context = await _launch_context(async_playwright)
    page = context.pages[0] if context.pages else await context.new_page()
    rc = 0
    try:
        await _fill_editor(page, post)
        checked = await _select_status(page, want_draft=True)
        if not checked:
            print("[WARN] 임시저장 radio 미선택 — 안전상 등록 클릭 보류. 입력완료 상태로 정지.")
        else:
            print("[INFO] 발행시간 = 임시저장 선택 확인")
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        shot_before = EVIDENCE_DIR / "kakao_draft_filled.png"
        await page.screenshot(path=str(shot_before))
        print(f"[INFO] 입력완료 스크린샷: {shot_before}")

        if checked:
            # 임시저장 radio가 선택된 등록 = 임시저장(비공개). 발행 아님.
            await page.locator(SEL_SUBMIT).first.click(timeout=10_000)
            await asyncio.sleep(4)
            shot_after = EVIDENCE_DIR / "kakao_draft_saved.png"
            await page.screenshot(path=str(shot_after))
            print(f"[INFO] 임시저장 등록 클릭 완료 — 결과 스크린샷: {shot_after}")
        print("[INFO] === DRAFT 완료 (공개 발행 없음) ===")
    except Exception as e:
        print(f"[ERROR] draft 실패: {e}")
        try:
            await page.screenshot(path=str(EVIDENCE_DIR / "kakao_draft_error.png"))
        except Exception:
            pass
        rc = 5
    finally:
        await context.close()
        await p.stop()
    return rc


# -----------------------------------------------------------------
# publish — 실 발행. GM go 가드 통과 시에만 '발행시간:지금' → 등록(공개).
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
    print("[INFO] === 카카오 채널 PUBLISH (GM go 가드 통과) ===")
    print(f"[INFO] 제목: {post.title or '(비어 있음)'} / 본문 {len(post.body)} chars / 이미지 {len(post.image_paths)}장")
    errs = validate_post(post, require_images=True)
    if errs:
        print("[ERROR] 콘텐츠 검증 실패:")
        for e in errs:
            print(f"        · {e}")
        return 4

    async_playwright = _import_playwright()
    p, context = await _launch_context(async_playwright)
    page = context.pages[0] if context.pages else await context.new_page()
    rc = 0
    try:
        await _fill_editor(page, post)
        checked = await _select_status(page, want_draft=False)
        if not checked:
            print("[ERROR] 발행시간 '지금' 미선택 — 발행 중단(안전).")
            rc = 6
        else:
            print("[INFO] 발행시간 = 지금(발행) 선택 확인")
            EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(EVIDENCE_DIR / "kakao_publish_filled.png"))
            await page.locator(SEL_SUBMIT).first.click(timeout=10_000)
            await asyncio.sleep(5)
            await page.screenshot(path=str(EVIDENCE_DIR / "kakao_publish_done.png"))
            print("[INFO] === PUBLISH 완료 (실 발행) ===")
    except Exception as e:
        print(f"[ERROR] publish 실패: {e}")
        rc = 5
    finally:
        await context.close()
        await p.stop()
    return rc


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CMO — 카카오 채널(소식) 반자동 업로더 v0.1 (setup·dryrun + draft/publish 스텁)"
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
                        help="콘텐츠 폴더 (instagram/{폴더}) — output(카카오 채널)/·kakao_copy.md 자동 산출")
    parser.add_argument("--title", default=None, help="소식 제목 (미지정 시 kakao_copy.md 제목 사용)")
    parser.add_argument("--body-file", dest="body_file", default=None,
                        help="카피 파일 경로 (미지정 시 content-dir/kakao_copy.md)")
    parser.add_argument("--image-dir", dest="image_dir", default=None,
                        help="이미지 폴더 (미지정 시 content-dir/output(카카오 채널))")
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
