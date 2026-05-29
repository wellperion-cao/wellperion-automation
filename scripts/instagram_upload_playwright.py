# scripts/instagram_upload_playwright.py
# v1.0 — Playwright Persistent Context (Creator 계정) 인스타그램 자동 업로드
#
# 실행 전 사전 설치 (GM님 로컬 PC 1회):
#   cd C:\Users\jjky0\welperion-automation
#   .venv\Scripts\activate  (없으면: python -m venv .venv)
#   pip install playwright
#   playwright install chromium
#
# 실행 방법:
#   setup (최초 1회 · GM님 수동 로그인):
#     python scripts\instagram_upload_playwright.py --mode setup
#   dryrun (셀렉터 검증, 발행 없음):
#     python scripts\instagram_upload_playwright.py --mode dryrun
#   publish (3 post 묶음 실 발행 — 별건 결재 후):
#     python scripts\instagram_upload_playwright.py --mode publish ^
#         --content-folder instagram\260426_WJO_스쿼시_대회
#
# 콘텐츠 폴더 v1.0 명세:
#   instagram/{YYMMDD_콘텐츠명}/
#     ├─ output/post_A_1.jpg, post_A_2.jpg, ..., post_B_*.jpg, post_C_*.jpg
#     └─ 큐레이션_추천.md  ← 3 섹션 (## post A / ## post B / ## post C),
#                            각 섹션: ### 캡션 / ### 해시태그 / ### Collaborator / ### 종목
#
# 결과 확인:
#   C:\Users\jjky0\welperion-automation\scripts\poc-evidence\instagram-{mode}-{timestamp}.png

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# -----------------------------------------------------------------
# 상수
# -----------------------------------------------------------------
INSTAGRAM_HOME_URL = "https://www.instagram.com"

# Persistent Context 프로필 디렉터리 — DPAPI 암호화 적용됨
PERSISTENT_PROFILE_DIR = Path(r"C:\Users\jjky0\welperion-automation\profiles\instagram")

EVIDENCE_DIR = Path(r"C:\Users\jjky0\welperion-automation\scripts\poc-evidence")

# headful 고정 UA (Mobile UA는 데스크탑 업로드 UI 비활성화 유발 — 데스크탑 UA 고정)
FIXED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 새 게시물(만들기) 진입 셀렉터 — 2026-05-29 실측: aria-label "새로운 게시물"
NEW_POST_SELECTORS = [
    'a:has(svg[aria-label="새로운 게시물"])',
    'div[role="button"]:has(svg[aria-label="새로운 게시물"])',
    'svg[aria-label="새로운 게시물"]',
    # legacy fallback
    'button[aria-label*="새 게시물"]',
    'svg[aria-label*="새 게시물"]',
]

# '만들기' 클릭 후 뜨는 하위메뉴의 '게시물' 항목 (없는 UI 버전도 있음 → 옵션)
CREATE_SUBMENU_SELECTORS = [
    'svg[aria-label="게시물"]',
    'div[role="dialog"] svg[aria-label="게시물"]',
    'div[role="menuitem"]:has-text("게시물")',
]

# 사진 업로드 input[type="file"] 셀렉터 후보 (인스타 2026 데스크탑 기준)
FILE_INPUT_SELECTORS = [
    'input[type="file"][accept*="image"]',
    'input[type="file"]',
    'form[role="presentation"] input[type="file"]',
]

# 캡션 입력 contenteditable 셀렉터 후보
CAPTION_SELECTORS = [
    'div[role="textbox"][aria-label*="캡션"]',
    'div[role="textbox"][aria-label*="문구"]',
    'div[contenteditable="true"][aria-label*="캡션"]',
    'div[contenteditable="true"]',
]

# "다음" 버튼 셀렉터 후보 (사진 → 자르기 → 필터 → 캡션 단계 진행)
NEXT_BUTTON_SELECTORS = [
    'button:has-text("다음")',
    'div[role="button"]:has-text("다음")',
    '[role="dialog"] button:has-text("다음")',
]

# "공유하기"/"게시" 최종 발행 버튼 — 2026-05-29 실측: div[role=button] "공유하기" (우상단)
SHARE_BUTTON_SELECTORS = [
    'div[role="button"]:text-is("공유하기")',
    'button:has-text("공유하기")',
    'div[role="button"]:has-text("공유하기")',
    'button:has-text("게시")',
]

# 협업자(Collaborator) 추가 UI 진입 셀렉터 후보
COLLABORATOR_TRIGGER_SELECTORS = [
    'div[role="button"]:has-text("사람 태그")',
    'div[role="button"]:has-text("협업자")',
    'span:has-text("협업자 추가")',
]
COLLABORATOR_INPUT_SELECTORS = [
    'input[placeholder*="검색"]',
    'input[aria-label*="검색"]',
    'input[type="text"][autocomplete="off"]',
]

# 게시 완료 URL 패턴 (게시물 상세) — /p/{shortcode}/
POST_URL_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com/p/([A-Za-z0-9_-]+)/?")

# 종목 → collaborator 강제 매핑 (메모리 feedback_ig_squash_collaborators 외 확장 슬롯)
SUBJECT_COLLABORATOR_MAP: dict[str, list[str]] = {
    "스쿼시": ["@namuk.wellperion", "@wellperion_squash", "@glass_court"],
    "squash": ["@namuk.wellperion", "@wellperion_squash", "@glass_court"],
}

# post 슬롯 식별자
POST_SLOTS = ("A", "B", "C")

# post 간 발행 간격 (초) — 지시 v1.0 명세 1~3초
POST_INTERVAL_SECONDS_MIN = 1.0
POST_INTERVAL_SECONDS_MAX = 3.0

# 텔레그램 봇 토큰 환경변수 키 (메모리 feedback_telegram_token_env_key)
TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot 보고 채널 (wellperion-agents/CLAUDE.md §3-1)


# -----------------------------------------------------------------
# 큐레이션 파서 — instagram/{folder}/큐레이션_추천.md 의 ## post A/B/C 섹션 추출
# v1.0 명세 (CMO 회신 시 조정 가능):
#   ## post A
#   ### 캡션
#   <본문 여러 줄>
#   ### 해시태그
#   #tag1 #tag2 ...
#   ### Collaborator
#   @handle1
#   @handle2
#   ### 종목
#   스쿼시            ← 미지정 시 SUBJECT_COLLABORATOR_MAP 자동 적용 안 됨
# -----------------------------------------------------------------
class PostSpec:
    __slots__ = ("slot", "caption", "hashtags", "collaborators", "subject", "image_paths")

    def __init__(self, slot: str) -> None:
        self.slot: str = slot
        self.caption: str = ""
        self.hashtags: list[str] = []
        self.collaborators: list[str] = []
        self.subject: str = ""
        self.image_paths: list[Path] = []

    def merged_caption(self) -> str:
        parts = [self.caption.strip()] if self.caption.strip() else []
        if self.hashtags:
            parts.append(" ".join(self.hashtags))
        return "\n\n".join(parts)


def parse_curation_md(md_path: Path) -> dict[str, PostSpec]:
    if not md_path.exists():
        raise FileNotFoundError(f"큐레이션 파일 부재: {md_path}")
    text = md_path.read_text(encoding="utf-8")
    posts: dict[str, PostSpec] = {}

    # ## post A / ## post B / ## post C 헤더로 분할
    section_re = re.compile(r"^##\s*post\s+([ABC])\s*$", re.IGNORECASE | re.MULTILINE)
    matches = list(section_re.finditer(text))
    if not matches:
        return posts

    for idx, m in enumerate(matches):
        slot = m.group(1).upper()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end]
        posts[slot] = _parse_post_section(slot, body)
    return posts


def _parse_post_section(slot: str, body: str) -> PostSpec:
    spec = PostSpec(slot)
    field_re = re.compile(r"^###\s*(캡션|해시태그|Collaborator|협업자|종목)\s*$", re.MULTILINE)
    fields = list(field_re.finditer(body))
    for idx, m in enumerate(fields):
        label = m.group(1)
        f_start = m.end()
        f_end = fields[idx + 1].start() if idx + 1 < len(fields) else len(body)
        chunk = body[f_start:f_end].strip()
        if label == "캡션":
            spec.caption = chunk
        elif label == "해시태그":
            spec.hashtags = re.findall(r"#[\w가-힣]+", chunk)
        elif label in ("Collaborator", "협업자"):
            spec.collaborators = [
                line.strip() for line in chunk.splitlines() if line.strip().startswith("@")
            ]
        elif label == "종목":
            spec.subject = chunk.splitlines()[0].strip() if chunk else ""
    return spec


def collect_post_images(content_folder: Path, slot: str) -> list[Path]:
    output_dir = content_folder / "output"
    if not output_dir.exists():
        return []
    pattern = re.compile(rf"^post_{slot}_(\d+)", re.IGNORECASE)
    candidates: list[tuple[int, Path]] = []
    for p in output_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        m = pattern.match(p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    candidates.sort(key=lambda t: t[0])
    return [p for _, p in candidates]


def enforce_subject_collaborators(spec: PostSpec) -> None:
    """종목 키워드에 매핑된 collaborator를 강제 합류 (메모리 feedback_ig_squash_collaborators)."""
    subject_key = spec.subject.strip().lower()
    forced = SUBJECT_COLLABORATOR_MAP.get(subject_key) or SUBJECT_COLLABORATOR_MAP.get(spec.subject.strip())
    if not forced:
        return
    existing = {c.lower() for c in spec.collaborators}
    for handle in forced:
        if handle.lower() not in existing:
            spec.collaborators.append(handle)
            existing.add(handle.lower())


def validate_post_spec(spec: PostSpec) -> list[str]:
    errors: list[str] = []
    if not spec.image_paths:
        errors.append(f"post {spec.slot}: 사진 파일 미존재 (output/post_{spec.slot}_*.jpg)")
    if not spec.caption.strip() and not spec.hashtags:
        errors.append(f"post {spec.slot}: 캡션·해시태그 모두 비어 있음")
    # 종목이 강제 매핑 대상이면 collaborator 누락 차단
    subj_key = spec.subject.strip().lower()
    if subj_key in {k.lower() for k in SUBJECT_COLLABORATOR_MAP}:
        required = {h.lower() for h in (SUBJECT_COLLABORATOR_MAP.get(subj_key) or SUBJECT_COLLABORATOR_MAP.get(spec.subject.strip()) or [])}
        actual = {c.lower() for c in spec.collaborators}
        missing = required - actual
        if missing:
            errors.append(
                f"post {spec.slot}: 종목={spec.subject!r} 필수 collaborator 누락 → {sorted(missing)}"
            )
    return errors


# -----------------------------------------------------------------
# 텔레그램 보고 — 토큰 stdout 노출 금지 (메모리 feedback_no_token_in_stdout)
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
        # 토큰 trace 노출 방지 — 예외 메시지 미출력
        print("[WARN] 텔레그램 보고 실패 (상세 미출력 — 토큰 trace 노출 방지)")


# -----------------------------------------------------------------
# 로그인 세션 유효성 확인
# 인스타그램은 미로그인 시 /accounts/login/ 또는 /challenge/ 로 리다이렉트
# -----------------------------------------------------------------
def is_session_expired(current_url: str) -> bool:
    expired_signals = [
        "instagram.com/accounts/login",
        "instagram.com/accounts/onetap",
        "instagram.com/challenge",
    ]
    return any(signal in current_url for signal in expired_signals)


async def detect_login_required(page) -> bool:
    """로그인 필요 여부를 화면 실측으로 판정.
    URL이 instagram.com/ 루트여도 로그아웃 랜딩(로그인 폼)이면 True.
    (URL만 보던 is_session_expired false-negative 보강 — 2026-05-29)"""
    if is_session_expired(page.url):
        return True
    try:
        if await page.locator('input[name="password"]').count() > 0:
            return True
        # 로그아웃 랜딩 고유 문구
        if await page.locator(':text("Instagram으로 로그인")').count() > 0:
            return True
    except Exception:
        pass
    return False


# -----------------------------------------------------------------
# setup 모드 — 최초 1회 대표님 수동 로그인으로 세션 확보
# headful(화면 표시) 모드로 실행 → 대표님이 직접 로그인 → 세션 자동 저장
# -----------------------------------------------------------------
async def run_setup() -> None:
    print("[INFO] === SETUP 모드 시작 ===")
    print("[INFO] headful Chrome 창이 열립니다.")
    print("[INFO] 인스타그램에 로그인 후 Enter 키를 눌러 세션을 저장하세요.")
    print(f"[INFO] 프로필 저장 경로: {PERSISTENT_PROFILE_DIR}")

    PERSISTENT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PERSISTENT_PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(INSTAGRAM_HOME_URL, wait_until="domcontentloaded", timeout=30_000)

        print("[INFO] 브라우저가 열렸습니다. 인스타그램에 로그인해 주세요.")
        print("[INFO] 로그인 완료 후 이 터미널에서 Enter 키를 누르세요.")

        # 대표님 로그인 대기 (비차단 입력 대기)
        await asyncio.get_event_loop().run_in_executor(None, input, "")

        # 세션 저장 확인 — 쿠키 값 stdout 노출 금지
        cookies = await context.cookies()
        ig_session_cookies = [
            c for c in cookies
            if "instagram.com" in c.get("domain", "") and c.get("name") in ("sessionid", "ds_user_id")
        ]
        if ig_session_cookies:
            print(f"[INFO] 인스타그램 세션 쿠키 확인 — {len(ig_session_cookies)}개 (sessionid/ds_user_id) 저장 완료 (값 비공개: ****)")
            for c in ig_session_cookies:
                exp = c.get("expires", -1)
                if exp > 0:
                    exp_dt = datetime.fromtimestamp(exp).strftime("%Y-%m-%d(%a) %H:%M")
                    print(f"[INFO] {c['name']} 만료 예정: {exp_dt} (값 비공개: ****)")
                else:
                    print(f"[INFO] {c['name']}: 세션 쿠키 (브라우저 종료 시 만료)")
        else:
            print("[WARN] sessionid / ds_user_id 쿠키 미감지 — 로그인이 완료되지 않았을 수 있습니다.")

        await context.close()

    print("[INFO] === SETUP 완료 ===")
    print(f"[INFO] 프로필 저장 위치: {PERSISTENT_PROFILE_DIR}")
    print("[INFO] 이후 --mode dryrun 실행 시 이 세션이 자동 사용됩니다.")


# -----------------------------------------------------------------
# setup-auto 모드 — 로그인을 자동 감지해 세션 저장 (Enter 불필요)
# 백그라운드 실행 가능: headful 창이 뜨면 GM이 로그인만 하면 자동 종료.
# -----------------------------------------------------------------
async def run_setup_auto(max_wait_sec: int = 300) -> None:
    print("[INFO] === SETUP-AUTO 모드 시작 ===")
    print("[INFO] headful Chrome 창이 열립니다. namuk.wellperion 으로 로그인하세요.")
    print("[INFO] 로그인 감지 시 자동으로 세션 저장 후 종료합니다 (Enter 불필요).")
    PERSISTENT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PERSISTENT_PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(INSTAGRAM_HOME_URL, wait_until="domcontentloaded", timeout=30_000)

        interval = 5
        waited = 0
        logged_in = False
        while waited < max_wait_sec:
            cookies = await context.cookies()
            has_sid = any(
                "instagram.com" in c.get("domain", "") and c.get("name") == "sessionid" and c.get("value")
                for c in cookies
            )
            if has_sid and not await detect_login_required(page):
                logged_in = True
                break
            await page.wait_for_timeout(interval * 1000)
            waited += interval
            print(f"[INFO] 로그인 대기 중... ({waited}/{max_wait_sec}s)")

        if logged_in:
            print("[INFO] 로그인 감지 — 세션 저장 완료 (값 비공개: ****)")
        else:
            print("[WARN] 제한시간 내 로그인 미감지 — 다시 시도하세요.")
        await context.close()

    print("[INFO] === SETUP-AUTO 완료 ===")
    return None


# -----------------------------------------------------------------
# dryrun 모드 — 로그인 세션 확인 + 새 게시물 버튼 셀렉터 탐색 (발행 안 함)
# -----------------------------------------------------------------
async def run_dryrun() -> None:
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 디렉터리 미존재. 먼저 --mode setup 실행 후 대표님이 로그인해야 합니다.")
        sys.exit(3)

    print("[INFO] === DRYRUN 모드 시작 ===")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = EVIDENCE_DIR / f"instagram-dryrun-{timestamp}.png"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PERSISTENT_PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            args=["--start-maximized"],
            no_viewport=True,
        )

        # 세션 쿠키 만료 체크 — 값 노출 금지
        cookies = await context.cookies()
        ig_cookies = [
            c for c in cookies
            if "instagram.com" in c.get("domain", "") and c.get("name") in ("sessionid", "ds_user_id")
        ]
        now_ts = datetime.now().timestamp()
        for c in ig_cookies:
            exp = c.get("expires", -1)
            if exp > 0:
                remaining_hours = (exp - now_ts) / 3600
                exp_dt = datetime.fromtimestamp(exp).strftime("%Y-%m-%d(%a) %H:%M")
                print(f"[INFO] {c['name']} 만료: {exp_dt} (잔여 {remaining_hours:.1f}h) (값 비공개: ****)")
                if remaining_hours < 24:
                    print(f"[WARN] {c['name']} 잔여 세션 24시간 미만 — 재로그인 필요")
            else:
                print(f"[INFO] {c['name']}: 세션 쿠키 타입 (만료 시각 없음)")

        page = await context.new_page()

        print(f"[INFO] 인스타그램 홈 이동 중... → {INSTAGRAM_HOME_URL}")
        await page.goto(INSTAGRAM_HOME_URL, wait_until="domcontentloaded", timeout=30_000)

        current_url = page.url
        print(f"[INFO] 현재 URL: {current_url}")

        if is_session_expired(current_url):
            print("[ERROR] 로그인 세션이 만료되었습니다. --mode setup 으로 재로그인 후 재실행하세요.")
            await context.close()
            sys.exit(2)

        print("[INFO] 로그인 세션 유효 확인 완료")

        # 홈 피드 로딩 대기
        await page.wait_for_timeout(3000)

        # 프로필 아바타 또는 새 게시물 버튼 탐색 (로그인 상태 2중 확인)
        login_confirmed = False
        try:
            avatar = page.locator('img[data-testid="user-avatar"], span[role="img"]').first
            if await avatar.count() > 0:
                print("[INFO] 프로필 아바타 감지 — 로그인 상태 확인")
                login_confirmed = True
        except Exception as e:
            print(f"[WARN] 프로필 아바타 셀렉터 탐색 실패: {e}")

        if not login_confirmed:
            print("[WARN] 프로필 아바타 미감지 — 로그인 상태 불확실")

        # 새 게시물 버튼 셀렉터 후보 3종 순차 탐색
        print("[INFO] 새 게시물 버튼 셀렉터 후보 3종 탐색 시작")
        found_selector = None
        for idx, selector in enumerate(NEW_POST_SELECTORS, start=1):
            try:
                el = page.locator(selector).first
                count = await el.count()
                status = "감지" if count > 0 else "미감지"
                print(f"[INFO] 후보 {idx}: {selector!r} → {status}")
                if count > 0 and found_selector is None:
                    found_selector = selector
            except Exception as e:
                print(f"[WARN] 후보 {idx} 탐색 오류: {e}")

        if found_selector:
            print(f"[INFO] 유효 셀렉터 확정 (새 게시물): {found_selector!r}")
        else:
            print("[WARN] 새 게시물 버튼 셀렉터 3종 모두 미감지 — 인스타그램 UI 변경 가능성. 스크린샷 확인 요망.")

        # publish 흐름 추가 셀렉터 후보군 탐색 — 클릭 없음 (count만 기록)
        await _probe_selector_group(page, "사진 업로드 input", FILE_INPUT_SELECTORS)
        await _probe_selector_group(page, "캡션 textbox", CAPTION_SELECTORS)
        await _probe_selector_group(page, "다음 버튼", NEXT_BUTTON_SELECTORS)
        await _probe_selector_group(page, "공유/게시 버튼", SHARE_BUTTON_SELECTORS)
        await _probe_selector_group(page, "Collaborator 진입", COLLABORATOR_TRIGGER_SELECTORS)

        # 스크린샷 저장 (Evidence)
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"[INFO] 스크린샷 저장 완료: {screenshot_path}")

        print("[INFO] dryrun 모드 — 발행 버튼 클릭 안 함 (PoC 원칙 준수)")

        await context.close()

    print("[INFO] === DRYRUN 완료 ===")
    print(f"[INFO] 증거 스크린샷 위치: {screenshot_path}")


async def _probe_selector_group(page, label: str, selectors: list[str]) -> str | None:
    """dryrun 전용: 셀렉터 후보들을 count만 검사 (클릭 없음). 첫 매치 반환."""
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
        print(f"[WARN] [{label}] 셀렉터 모두 미감지 — UI 변경 가능성")
    return matched


# -----------------------------------------------------------------
# publish 모드 — instagram/{콘텐츠}/output/post_{A|B|C}_*.jpg 3 post 묶음 발행
# 흐름: 큐레이션 파싱 → 검증(collab 강제) → post A → 1~3초 → post B → 1~3초 → post C
# 비가역 실 발행. 별건 결재 후만 호출.
# -----------------------------------------------------------------
async def run_publish(content_folder: Path) -> dict[str, str]:
    if not PERSISTENT_PROFILE_DIR.exists():
        print("[ERROR] 프로필 디렉터리 미존재. --mode setup 우선 실행 필요.")
        sys.exit(3)
    if not content_folder.exists() or not content_folder.is_dir():
        print(f"[ERROR] 콘텐츠 폴더 미존재: {content_folder}")
        sys.exit(4)

    print(f"[INFO] === PUBLISH 모드 시작 === folder={content_folder}")

    # 1. 큐레이션 파싱 + 사진 매핑 + 종목 collaborator 강제 + 검증
    md_path = content_folder / "큐레이션_추천.md"
    posts = parse_curation_md(md_path)
    # 발행 대상 = 존재하는 슬롯(A/B/C 순). 단일 포스트(post A만)도 허용 (2026-05-29 시드 #09).
    present_slots = [s for s in POST_SLOTS if s in posts]
    if not present_slots:
        print("[ERROR] 큐레이션에 post 섹션 없음 (## post A/B/C 중 최소 1개 필요)")
        sys.exit(5)
    print(f"[INFO] 발행 대상 post: {present_slots}")

    all_errors: list[str] = []
    for slot in present_slots:
        spec = posts[slot]
        spec.image_paths = collect_post_images(content_folder, slot)
        enforce_subject_collaborators(spec)
        all_errors.extend(validate_post_spec(spec))

    if all_errors:
        print("[ERROR] 사전 검증 실패 — publish 차단:")
        for err in all_errors:
            print(f"        · {err}")
        telegram_report(
            f"⛔ AI CTO 인스타 publish 차단\n폴더: {content_folder.name}\n사유: {len(all_errors)}건\n첫 항목: {all_errors[0]}"
        )
        sys.exit(6)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    published: dict[str, str] = {}

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PERSISTENT_PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(INSTAGRAM_HOME_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2500)
        if await detect_login_required(page):
            print("[ERROR] 로그인 필요 (화면 실측 — 로그인 페이지). --mode setup-auto 로 재로그인 필요.")
            await context.close()
            sys.exit(2)
        print("[INFO] 세션 유효 확인 완료 (로그인 화면 아님)")

        for idx, slot in enumerate(present_slots):
            spec = posts[slot]
            print(f"\n[INFO] ── post {slot} 발행 시작 ── images={len(spec.image_paths)} / collab={len(spec.collaborators)}")
            try:
                url = await _publish_single_post(page, spec, content_folder)
            except Exception as e:
                print(f"[ERROR] post {slot} 발행 예외: {e}")
                # 자동 재시도 1회 (지시 v1.0)
                print(f"[INFO] post {slot} 자동 재시도 1회 시작")
                try:
                    url = await _publish_single_post(page, spec, content_folder)
                except Exception as e2:
                    print(f"[ERROR] post {slot} 재시도 실패: {e2}")
                    telegram_report(
                        f"⚠️ AI CTO 인스타 publish 실패 → 수동 진단 격상\npost: {slot}\n폴더: {content_folder.name}\n사유: {e2}"
                    )
                    await context.close()
                    sys.exit(7)

            if not url:
                print(f"[ERROR] post {slot} 게시 URL 회수 실패 (스크립트 exit 0만으로 단정 금지 — 4.21 v1.19 사고 재발 방지)")
                telegram_report(
                    f"⚠️ AI CTO 인스타 publish — 게시 URL 미회수\npost: {slot}\n폴더: {content_folder.name}"
                )
                await context.close()
                sys.exit(8)
            published[slot] = url
            print(f"[INFO] post {slot} 발행 성공 — {url}")

            if idx < len(present_slots) - 1:
                import random
                gap = random.uniform(POST_INTERVAL_SECONDS_MIN, POST_INTERVAL_SECONDS_MAX)
                print(f"[INFO] post {slot} → 다음 post 간격 {gap:.2f}s 대기")
                await asyncio.sleep(gap)

        await context.close()

    # 2. 텔레그램 완료 보고
    summary_lines = [f"✅ 인스타 publish 성공 — {len(present_slots)} post"]
    summary_lines.append(f"폴더: {content_folder.name}")
    for slot in present_slots:
        summary_lines.append(f"  post {slot}: {published[slot]}")
    telegram_report("\n".join(summary_lines))

    print(f"\n[INFO] === PUBLISH 완료 — 게시 URL {len(present_slots)}개 ===")
    for slot in present_slots:
        print(f"  post {slot}: {published[slot]}")

    return published


async def _publish_single_post(page, spec: PostSpec, content_folder: Path) -> str | None:
    """단일 post 발행. 게시 URL 반환 (실패 시 None)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_prefix = EVIDENCE_DIR / f"instagram-publish-{content_folder.name}-post{spec.slot}-{timestamp}"

    # 새 게시물 버튼 클릭
    new_post_clicked = False
    for sel in NEW_POST_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=5000)
                new_post_clicked = True
                print(f"[INFO]   새 게시물 클릭: {sel!r}")
                break
        except Exception:
            continue
    if not new_post_clicked:
        await page.screenshot(path=str(evidence_prefix.with_suffix(".error_newpost.png")))
        raise RuntimeError("새 게시물 버튼 셀렉터 모두 실패")

    await page.wait_for_timeout(2000)

    # '만들기' → '게시물' 하위메뉴 클릭 (없는 UI 버전이면 건너뜀 — 옵션)
    for sel in CREATE_SUBMENU_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=3000)
                print(f"[INFO]   '게시물' 하위메뉴 클릭: {sel!r}")
                await page.wait_for_timeout(1500)
                break
        except Exception:
            continue

    # 사진 input[type=file] 다중 업로드
    file_input = None
    for sel in FILE_INPUT_SELECTORS:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            file_input = loc
            print(f"[INFO]   사진 input 발견: {sel!r}")
            break
    if file_input is None:
        await page.screenshot(path=str(evidence_prefix.with_suffix(".error_fileinput.png")))
        raise RuntimeError("사진 input[type=file] 미발견")

    await file_input.set_input_files([str(p) for p in spec.image_paths])
    print(f"[INFO]   사진 {len(spec.image_paths)}장 업로드 시작")
    await page.wait_for_timeout(3500)

    # "다음" 2회 클릭 (자르기 → 필터 → 캡션) — 인스타 데스크탑 표준 흐름
    for step in range(2):
        clicked = False
        for sel in NEXT_BUTTON_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=5000)
                    clicked = True
                    print(f"[INFO]   다음 버튼 step{step + 1} 클릭: {sel!r}")
                    break
            except Exception:
                continue
        if not clicked:
            await page.screenshot(path=str(evidence_prefix.with_suffix(f".error_next_step{step + 1}.png")))
            raise RuntimeError(f"다음 버튼 step{step + 1} 클릭 실패")
        await page.wait_for_timeout(1500)

    # 캡션 입력
    caption_box = None
    for sel in CAPTION_SELECTORS:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            caption_box = loc
            print(f"[INFO]   캡션 textbox: {sel!r}")
            break
    if caption_box is None:
        await page.screenshot(path=str(evidence_prefix.with_suffix(".error_caption.png")))
        raise RuntimeError("캡션 textbox 미발견")

    await caption_box.click()
    await page.keyboard.type(spec.merged_caption(), delay=15)
    print(f"[INFO]   캡션 입력 완료 ({len(spec.merged_caption())} chars)")

    # Collaborator 추가 (있는 경우만)
    if spec.collaborators:
        added = await _add_collaborators(page, spec.collaborators)
        print(f"[INFO]   Collaborator 추가 결과: {added}/{len(spec.collaborators)}")
        if added < len(spec.collaborators):
            await page.screenshot(path=str(evidence_prefix.with_suffix(".error_collab.png")))
            raise RuntimeError(
                f"Collaborator 일부 미추가 ({added}/{len(spec.collaborators)}) — 종목 강제 누락 시 publish 차단"
            )

    await page.screenshot(path=str(evidence_prefix.with_suffix(".pre_share.png")))

    # 공유하기 버튼 클릭 (실 게시)
    share_clicked = False
    for sel in SHARE_BUTTON_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=8000)
                share_clicked = True
                print(f"[INFO]   공유하기 클릭: {sel!r}")
                break
        except Exception:
            continue
    if not share_clicked:
        await page.screenshot(path=str(evidence_prefix.with_suffix(".error_share.png")))
        raise RuntimeError("공유하기 버튼 클릭 실패")

    # 게시 완료 대기 + URL 회수
    await page.wait_for_timeout(8000)
    await page.screenshot(path=str(evidence_prefix.with_suffix(".post_share.png")))

    # 프로필 이동 후 최신 게시물 URL 회수 (가장 안정적인 경로)
    return await _capture_latest_post_url(page)


async def _add_collaborators(page, handles: list[str]) -> int:
    """캡션 화면에서 Collaborator UI 진입 후 핸들 리스트 추가. 추가 성공 카운트 반환."""
    trigger = None
    for sel in COLLABORATOR_TRIGGER_SELECTORS:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            trigger = loc
            break
    if trigger is None:
        print("[WARN]   Collaborator 진입 셀렉터 미발견 — UI 변경 가능성")
        return 0
    try:
        await trigger.click(timeout=5000)
    except Exception as e:
        print(f"[WARN]   Collaborator 진입 클릭 실패: {e}")
        return 0
    await page.wait_for_timeout(1500)

    inp = None
    for sel in COLLABORATOR_INPUT_SELECTORS:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            inp = loc
            break
    if inp is None:
        return 0

    added = 0
    for handle in handles:
        clean = handle.lstrip("@")
        try:
            await inp.fill("")
            await inp.type(clean, delay=30)
            await page.wait_for_timeout(1200)
            # 첫 검색 결과 클릭 (가장 보수적)
            result = page.locator(f'div[role="dialog"] :text("{clean}")').first
            if await result.count() > 0:
                await result.click(timeout=4000)
                added += 1
                await page.wait_for_timeout(600)
            else:
                print(f"[WARN]   Collaborator 검색 결과 미발견: @{clean}")
        except Exception as e:
            print(f"[WARN]   Collaborator @{clean} 추가 예외: {e}")
    # 다이얼로그 닫기 (완료 버튼 후보)
    for sel in ['button:has-text("완료")', 'div[role="button"]:has-text("완료")']:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click(timeout=3000)
                break
        except Exception:
            continue
    return added


async def _capture_latest_post_url(page) -> str | None:
    try:
        # 인스타 본인 프로필로 이동 (페이지 자체 URL은 /username/)
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15_000)
        await page.wait_for_timeout(2000)
        # 프로필 아바타 → 내 프로필 진입
        for sel in ['a[href*="/namuk.wellperion/"]', 'img[alt*="프로필"]', 'img[data-testid="user-avatar"]']:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                try:
                    await loc.click(timeout=4000)
                    break
                except Exception:
                    continue
        await page.wait_for_timeout(2500)
        # 첫 게시물 링크 추출
        first_post = page.locator('a[href*="/p/"]').first
        if await first_post.count() > 0:
            href = await first_post.get_attribute("href")
            if href:
                full = href if href.startswith("http") else f"https://www.instagram.com{href}"
                m = POST_URL_PATTERN.search(full)
                if m:
                    return f"https://www.instagram.com/p/{m.group(1)}/"
                return full
        return None
    except Exception as e:
        print(f"[WARN]   게시 URL 회수 예외: {e}")
        return None


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CTO — 인스타그램 Playwright v1.0 (Persistent Context · 3 post 묶음)"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "setup-auto", "dryrun", "publish"],
        default="dryrun",
        help=(
            "setup: 최초 1회 GM님 수동 로그인 (Enter로 저장) / "
            "setup-auto: 로그인 자동 감지 저장 (Enter 불필요·백그라운드 가능) / "
            "dryrun: 세션 확인 + publish 흐름 셀렉터 후보군 전체 탐색 (기본·발행 없음) / "
            "publish: instagram/{콘텐츠}/output/post_{A|B|C}_*.jpg 실 발행 — 존재하는 슬롯만(단일 포스트 허용·비가역)"
        ),
    )
    parser.add_argument(
        "--content-folder",
        default=None,
        help="publish 모드 필수: 콘텐츠 폴더 경로 (예: instagram\\260426_WJO_스쿼시_대회)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "setup":
        asyncio.run(run_setup())
    elif args.mode == "setup-auto":
        asyncio.run(run_setup_auto())
    elif args.mode == "publish":
        if not args.content_folder:
            print("[ERROR] --mode publish 는 --content-folder 인자 필수")
            sys.exit(1)
        folder = Path(args.content_folder)
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        asyncio.run(run_publish(folder))
    else:
        asyncio.run(run_dryrun())
