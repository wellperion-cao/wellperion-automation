# scripts/instagram_upload_playwright.py
# v1.1 — Playwright Persistent Context (Creator 계정) 인스타그램 자동 업로드
#         멀티계정(--account) + 영상(mp4) 캐러셀 + ig_NN 폴더 형식 지원
#
# 실행 전 사전 설치 (GM님 로컬 PC 1회):
#   cd C:\Users\jjky0\welperion-automation
#   .venv\Scripts\activate  (없으면: python -m venv .venv)
#   pip install playwright
#   playwright install chromium
#
# 실행 방법:
#   setup (최초 1회 · GM님 수동 로그인):
#     python scripts\instagram_upload_playwright.py --mode setup [--account wellperion]
#   dryrun (셀렉터 검증, 발행 없음):
#     python scripts\instagram_upload_playwright.py --mode dryrun [--account wellperion]
#   publish (3 post 묶음 실 발행 — 별건 결재 후):
#     python scripts\instagram_upload_playwright.py --mode publish ^
#         --content-folder instagram\260520_바레_런칭 [--account wellperion]
#
# 콘텐츠 폴더 v1.1 명세:
#   instagram/{YYMMDD_콘텐츠명}/
#     ├─ output/post_A_1.jpg, post_A_2.jpg, ..., post_B_*.jpg, post_C_*.jpg  (기존 형식)
#     ├─ output/ig_01.jpg, ig_02.jpg, ..., ig_07.mp4                          (ig_NN 형식 · 바레 등)
#     └─ 큐레이션_추천.md  ← 3 섹션 (## post A / ## post B / ## post C),
#                            각 섹션: ### 캡션 / ### 해시태그 / ### Collaborator / ### 종목
#
# 멀티계정 프로필 경로:
#   profiles/instagram/{account}/  (기본 account: namuk.wellperion)
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
# 콘솔 인코딩 하드닝 (수정 3) — Windows cp949 콘솔에서 대시(—)·이모지 print 시
# UnicodeEncodeError 로 스크립트가 중단되는 사고 재발방지.
# stdout/stderr 를 UTF-8(errors=replace)로 강제. reconfigure 미지원 환경은
# 안전 폴백(무시) — 어떤 경우에도 import 시 예외로 죽지 않게 한다.
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
            # 콘솔이 reconfigure 를 거부해도 발행 자체는 진행돼야 함
            pass


_harden_console_encoding()


# -----------------------------------------------------------------
# 상수
# -----------------------------------------------------------------
INSTAGRAM_HOME_URL = "https://www.instagram.com"

# Persistent Context 프로필 베이스 디렉터리 — 계정별 하위 폴더로 분리
# 실제 경로: PROFILE_BASE / {account}  (예: profiles/instagram/namuk.wellperion)
PROFILE_BASE = Path(r"C:\Users\jjky0\welperion-automation\profiles\instagram")

# 기본 계정 (--account 미지정 시)
DEFAULT_ACCOUNT = "namuk.wellperion"


def get_profile_dir(account: str) -> Path:
    """계정명 → Persistent Context 프로필 경로. 기존 단일 프로필과 호환."""
    return PROFILE_BASE / account

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

# 사진/영상 업로드 input[type="file"] 셀렉터 후보 (인스타 2026 데스크탑 기준)
# accept*="image" 셀렉터는 mp4 혼합 캐러셀 시 제한될 수 있으므로 범용 순위 상향
FILE_INPUT_SELECTORS = [
    'input[type="file"]',
    'input[type="file"][accept*="image"]',
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

# 위치 추가 UI 진입 셀렉터 후보 (캡션 화면 하단 "위치 추가" / "Add location")
LOCATION_TRIGGER_SELECTORS = [
    'div[role="button"]:has-text("위치 추가")',
    'span:has-text("위치 추가")',
    'div[role="button"]:has-text("Add location")',
    'span:has-text("Add location")',
    'button:has-text("위치 추가")',
]
LOCATION_INPUT_SELECTORS = [
    'input[placeholder*="위치"]',
    'input[placeholder*="검색"]',
    'input[aria-label*="위치"]',
    'input[type="text"][autocomplete="off"]',
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
try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

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

    def merged_caption(self, extra_mentions: list[str] | None = None) -> str:
        """캡션 + 해시태그 합성. extra_mentions 있으면 해시태그 줄 앞에 멘션 줄 삽입.
        caption 본문에 이미 @핸들이 있으면 중복 추가 금지."""
        body = self.caption.strip()
        hashtag_line = " ".join(self.hashtags) if self.hashtags else ""

        # 멘션 합성 — 이미 caption에 있는 핸들은 제외
        mention_line = ""
        if extra_mentions:
            existing = {m.lstrip("@").lower() for m in re.findall(r"@[\w.]+", body)}
            new_handles = [
                m if m.startswith("@") else "@" + m
                for m in extra_mentions
                if m.lstrip("@").lower() not in existing
            ]
            if new_handles:
                mention_line = " ".join(new_handles)

        parts: list[str] = []
        if body:
            parts.append(body)
        if mention_line:
            parts.append(mention_line)
        if hashtag_line:
            parts.append(hashtag_line)
        return "\n\n".join(parts)


def build_spec_from_caption(caption_text: str) -> dict[str, PostSpec]:
    """큐레이션_추천.md 없이 caption 문자열만으로 단일 슬롯(post A) 스펙 생성.

    AI 시리즈(개인계정) 단순화 — review_queue.json 의 caption 이 단일 출처가 된다.
    caption 본문 안에 #해시태그 줄이 포함돼 있으면 그대로 캡션에 둔다(merged_caption
    이 hashtags 를 별도 처리하지 않아도 본문에 이미 포함 → 중복 없음).
    이미지·종목·collaborator 는 호출부(run_publish)가 채운다.
    """
    spec = PostSpec("A")
    spec.caption = (caption_text or "").strip()
    # 해시태그는 caption 본문에 이미 포함되므로 별도 추출하지 않음(중복 방지).
    return {"A": spec}


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


def _scan_ig_pattern(search_dir: Path, allowed_exts: set, video_exts: set) -> list[Path]:
    """ig_NN 패턴 파일을 search_dir 에서 수집. 없으면 []."""
    ig_pattern = re.compile(r"^ig_?(\d+)", re.IGNORECASE)
    ig_images: list[tuple[int, Path]] = []
    ig_videos: list[tuple[int, Path]] = []
    for p in search_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in allowed_exts:
            continue
        m = ig_pattern.match(p.name)
        if m:
            idx = int(m.group(1))
            (ig_videos if p.suffix.lower() in video_exts else ig_images).append((idx, p))
    if ig_images or ig_videos:
        ig_images.sort(key=lambda t: t[0])
        ig_videos.sort(key=lambda t: t[0])
        return [p for _, p in ig_images] + [p for _, p in ig_videos]
    return []


def _scan_plain_pattern(search_dir: Path, allowed_exts: set, video_exts: set) -> list[Path]:
    """post_N 패턴(슬롯 글자 없음) 파일을 search_dir 에서 수집. 없으면 []."""
    plain_pattern = re.compile(r"^post_(\d+)", re.IGNORECASE)
    plain_images: list[tuple[int, Path]] = []
    plain_videos: list[tuple[int, Path]] = []
    for p in search_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in allowed_exts:
            continue
        m = plain_pattern.match(p.name)
        if m:
            idx = int(m.group(1))
            (plain_videos if p.suffix.lower() in video_exts else plain_images).append((idx, p))
    if plain_images or plain_videos:
        plain_images.sort(key=lambda t: t[0])
        plain_videos.sort(key=lambda t: t[0])
        return [p for _, p in plain_images] + [p for _, p in plain_videos]
    return []


def collect_post_images(content_folder: Path, slot: str) -> list[Path]:
    """슬롯에 해당하는 파일 목록을 반환.

    우선순위:
    1) output/ 존재 시 — post_{slot}_N 형식 (기존 표준, namuk 경로).
    2) output/ 존재 시 — ig_NN 형식 fallback (바레 등 output 하위 ig_NN).
    3) output/ 존재 시 — 평이름 post_N 형식 fallback (슬롯 글자 없음).
    4) (FIX2) output/ 없을 때 — 폴더 루트에서 ig_NN 탐색 (생크몽드 등 4채널형).
    5) (FIX2) output/ 없을 때 — 폴더 루트에서 post_N 탐색.
    영상(mp4)은 항상 마지막.
    """
    IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
    VIDEO_EXTS = {".mp4"}
    ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS

    output_dir = content_folder / "output"
    if output_dir.exists():
        # --- 1) post_{slot}_N 형식 (output/) ---
        pattern = re.compile(rf"^post_{re.escape(slot)}_(\d+)", re.IGNORECASE)
        images: list[tuple[int, Path]] = []
        videos: list[tuple[int, Path]] = []
        for p in output_dir.iterdir():
            if not p.is_file() or p.suffix.lower() not in ALLOWED_EXTS:
                continue
            m = pattern.match(p.name)
            if m:
                idx = int(m.group(1))
                (videos if p.suffix.lower() in VIDEO_EXTS else images).append((idx, p))
        if images or videos:
            images.sort(key=lambda t: t[0])
            videos.sort(key=lambda t: t[0])
            return [p for _, p in images] + [p for _, p in videos]

        # --- 2) ig_NN 형식 fallback (output/) ---
        result = _scan_ig_pattern(output_dir, ALLOWED_EXTS, VIDEO_EXTS)
        if result:
            return result

        # --- 3) (FIX1) 평이름 post_N 형식 fallback (output/) ---
        result = _scan_plain_pattern(output_dir, ALLOWED_EXTS, VIDEO_EXTS)
        if result:
            return result

    # --- 4) (FIX2) output/ 없음 — 폴더 루트 ig_NN 탐색 (생크몽드 등 4채널형) ---
    result = _scan_ig_pattern(content_folder, ALLOWED_EXTS, VIDEO_EXTS)
    if result:
        print(f"[INFO] 이미지 탐색: output/ 없음 → 폴더 루트 ig_NN 형식 사용 ({content_folder.name})")
        return result

    # --- 5) (FIX2) 폴더 루트 post_N 탐색 ---
    result = _scan_plain_pattern(content_folder, ALLOWED_EXTS, VIDEO_EXTS)
    if result:
        print(f"[INFO] 이미지 탐색: output/ 없음 → 폴더 루트 post_N 형식 사용 ({content_folder.name})")
        return result

    return []


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
        slot_label = spec.slot
        errors.append(
            f"post {slot_label}: 파일 미존재 "
            f"(output/post_{slot_label}_*.jpg/mp4 또는 ig_NN.jpg/mp4 또는 post_N.jpg/mp4)"
        )
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
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="instagram_upload_playwright.telegram_report", ok=ok, kind="sendMessage")
        print(f"[INFO] 텔레그램 보고 {'성공' if ok else '실패'} (chat={TELEGRAM_CHAT_ID})")
    except Exception:
        # 토큰 trace 노출 방지 — 예외 메시지 미출력
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="instagram_upload_playwright.telegram_report", ok=False, kind="sendMessage")
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
async def run_setup(account: str = DEFAULT_ACCOUNT) -> None:
    profile_dir = get_profile_dir(account)
    print("[INFO] === SETUP 모드 시작 ===")
    print(f"[INFO] 계정: {account}")
    print("[INFO] headful Chrome 창이 열립니다.")
    print("[INFO] 인스타그램에 로그인 후 Enter 키를 눌러 세션을 저장하세요.")
    print(f"[INFO] 프로필 저장 경로: {profile_dir}")

    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
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
    print(f"[INFO] 프로필 저장 위치: {profile_dir}")
    print("[INFO] 이후 --mode dryrun 실행 시 이 세션이 자동 사용됩니다.")


# -----------------------------------------------------------------
# setup-auto 모드 — 로그인을 자동 감지해 세션 저장 (Enter 불필요)
# 백그라운드 실행 가능: headful 창이 뜨면 GM이 로그인만 하면 자동 종료.
# -----------------------------------------------------------------
async def run_setup_auto(account: str = DEFAULT_ACCOUNT, max_wait_sec: int = 300) -> None:
    profile_dir = get_profile_dir(account)
    print("[INFO] === SETUP-AUTO 모드 시작 ===")
    print(f"[INFO] 계정: {account}")
    print(f"[INFO] headful Chrome 창이 열립니다. {account} 으로 로그인하세요.")
    print("[INFO] 로그인 감지 시 자동으로 세션 저장 후 종료합니다 (Enter 불필요).")
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
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
async def run_dryrun(account: str = DEFAULT_ACCOUNT) -> None:
    profile_dir = get_profile_dir(account)
    if not profile_dir.exists():
        print(f"[ERROR] 프로필 디렉터리 미존재 ({profile_dir}). 먼저 --mode setup --account {account} 실행 후 로그인해야 합니다.")
        sys.exit(3)

    print("[INFO] === DRYRUN 모드 시작 ===")
    print(f"[INFO] 계정: {account}")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = EVIDENCE_DIR / f"instagram-dryrun-{timestamp}.png"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
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
# review_queue.json 후처리 — 발행 완료 시 큐 항목 자동 갱신
# 수동 --mode publish 경로에서도 큐가 '발행완료'로 갱신되게 (누락 반복 방지).
# 예외는 광범위 try/except 로 포획 — 발행 자체를 절대 깨지 않음.
# -----------------------------------------------------------------
ROOT = Path(r"C:\Users\jjky0\welperion-automation")
_REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"


def update_review_queue(content_folder: Path, published: dict[str, str]) -> None:
    """큐에서 content_folder 와 매칭되는 항목을 발행완료로 갱신.

    매칭 기준: 큐 item["folder"] 문자열이 content_folder 경로 끝과 일치하거나
    폴더 이름(basename)이 같은 경우.
    갱신 필드: status="발행완료", post_url=첫 published url, published_at=ISO now.
    큐 파일 git commit 은 하지 않음(파일만 갱신).
    """
    try:
        import json as _json

        if not _REVIEW_QUEUE_PATH.exists():
            print(f"[INFO] review_queue.json 미존재 — 후처리 건너뜀 ({_REVIEW_QUEUE_PATH})")
            return

        queue: list[dict] = _json.loads(_REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
        folder_name = content_folder.name  # 예: "260529_AI직원효율_핵심집중"
        # content_folder 를 정방향 슬래시 상대경로로도 비교
        cf_str = content_folder.as_posix()

        first_url = next(iter(published.values()), "") if published else ""
        now_iso = datetime.now().isoformat(timespec="seconds")

        matched = False
        for item in queue:
            item_folder: str = item.get("folder", "")
            # 큐 folder 필드 예: "instagram/260529_AI직원효율_핵심집중"
            item_folder_name = item_folder.split("/")[-1].split("\\")[-1]
            if item_folder_name == folder_name or cf_str.endswith(item_folder.replace("\\", "/")):
                item["status"] = "발행완료"
                item["post_url"] = first_url
                item["published_at"] = now_iso
                matched = True
                print(f"[INFO] review_queue 갱신 완료 — id={item.get('id', '?')} → 발행완료 / {first_url}")

        if not matched:
            print(f"[INFO] review_queue 매칭 항목 없음 (folder={folder_name}) — 후처리 건너뜀")
            return

        _REVIEW_QUEUE_PATH.write_text(
            _json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[WARN] review_queue 후처리 예외 (발행 영향 없음): {exc}")


# -----------------------------------------------------------------
# publish 모드 — instagram/{콘텐츠}/output/post_{A|B|C}_*.jpg 3 post 묶음 발행
# 흐름: 큐레이션 파싱 → 검증(collab 강제) → post A → 1~3초 → post B → 1~3초 → post C
# 비가역 실 발행. 별건 결재 후만 호출.
# -----------------------------------------------------------------
async def run_publish(
    content_folder: Path,
    location: str = "",
    mentions: list[str] | None = None,
    account: str = DEFAULT_ACCOUNT,
    extra_collaborators: list[str] | None = None,
    caption_file: Path | None = None,
) -> dict[str, str]:
    profile_dir = get_profile_dir(account)
    if not profile_dir.exists():
        print(f"[ERROR] 프로필 디렉터리 미존재 ({profile_dir}). --mode setup --account {account} 우선 실행 필요.")
        sys.exit(3)
    if not content_folder.exists() or not content_folder.is_dir():
        print(f"[ERROR] 콘텐츠 폴더 미존재: {content_folder}")
        sys.exit(4)

    print(f"[INFO] === PUBLISH 모드 시작 === folder={content_folder} account={account}")

    # 1. 입력 소스 단일화 (2026-06-04 단순화) — 우선순위:
    #    (a) 큐레이션_추천.md 존재 → 기존 파싱(다중 슬롯 A/B/C 지원, 수동 경로 호환)
    #    (b) 없으면 caption_file(=review_queue.json caption) → 단일 슬롯 post A 합성
    #    → '큐레이션_추천.md 누락' FileNotFoundError 즉사 재발방지(오늘 3회 실패 원인 #1).
    #      review_queue 의 caption 이 항상 채워지므로(register_publish) 누락 불가.
    md_path = content_folder / "큐레이션_추천.md"
    if md_path.exists():
        posts = parse_curation_md(md_path)
        print(f"[INFO] 입력 소스: 큐레이션_추천.md ({md_path.name})")
    elif caption_file is not None and Path(caption_file).exists():
        caption_text = Path(caption_file).read_text(encoding="utf-8")
        posts = build_spec_from_caption(caption_text)
        print(f"[INFO] 입력 소스: caption_file 단일화 (큐레이션 md 부재 → 큐 caption 합성, {len(caption_text)} chars)")
    else:
        print(
            "[ERROR] 발행 입력 소스 없음 — 큐레이션_추천.md 도 caption_file 도 부재. "
            "(review_queue.json 의 caption 또는 폴더의 큐레이션_추천.md 중 하나 필수)"
        )
        telegram_report(
            f"⛔ AI CTO 인스타 publish 차단 — 입력 소스 부재\n"
            f"폴더: {content_folder.name}\n"
            f"사유: 큐레이션_추천.md·caption_file 모두 없음(누락 사전차단)"
        )
        sys.exit(5)
    # 발행 대상 = 존재하는 슬롯(A/B/C 순). 단일 포스트(post A만)도 허용 (2026-05-29 시드 #09).
    present_slots = [s for s in POST_SLOTS if s in posts]
    if not present_slots:
        print("[ERROR] 발행 대상 post 섹션 없음 (## post A/B/C 중 최소 1개 또는 caption 필요)")
        sys.exit(5)
    print(f"[INFO] 발행 대상 post: {present_slots}")

    all_errors: list[str] = []
    for slot in present_slots:
        spec = posts[slot]
        spec.image_paths = collect_post_images(content_folder, slot)
        enforce_subject_collaborators(spec)
        # --collaborators CLI 인자 병합 (중복 제거)
        if extra_collaborators:
            existing_lower = {c.lower() for c in spec.collaborators}
            for handle in extra_collaborators:
                if handle.lower() not in existing_lower:
                    spec.collaborators.append(handle)
                    existing_lower.add(handle.lower())
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
            user_data_dir=str(profile_dir),
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
                url, outcome = await _publish_single_post(page, spec, content_folder, location=location, mentions=mentions, account=account)
            except Exception as e:
                print(f"[ERROR] post {slot} 발행 예외: {e}")
                # 자동 재시도 1회 (지시 v1.0) — 예외(UI 크래시)에만 재시도.
                # (FIX2) '확인필요' 는 예외가 아니라 정상 반환이므로 여기로 오지 않음 = 중복 발행 안 됨.
                print(f"[INFO] post {slot} 자동 재시도 1회 시작")
                try:
                    url, outcome = await _publish_single_post(page, spec, content_folder, location=location, mentions=mentions, account=account)
                except Exception as e2:
                    print(f"[ERROR] post {slot} 재시도 실패: {e2}")
                    telegram_report(
                        f"⚠️ AI CTO 인스타 publish 실패 → 수동 진단 격상\npost: {slot}\n폴더: {content_folder.name}\n사유: {e2}"
                    )
                    await context.close()
                    sys.exit(7)

            if outcome == "확인필요":
                # (FIX2) 토스트 확인됐으나 신규 shortcode 미확정 → 발행됐을 가능성 높음.
                # '발행실패'로 단정·재시도 절대 금지(중복 발행 사고 방지). review_queue 도
                # '발행완료'로 갱신하지 않음(URL 없음). status='확인필요' 안내만.
                print(
                    f"[WARN] post {slot} 확인필요 — 성공 토스트는 떴으나 신규 shortcode 윈도우 내 미확정. "
                    f"발행됐을 가능성 높음 → URL 수동확인 필요. (재시도/발행실패 단정 안 함)"
                )
                telegram_report(
                    f"⚠️ AI CTO 인스타 publish 확인필요 — 발행됐을 가능성 높음\n"
                    f"post: {slot}\n폴더: {content_folder.name}\n"
                    f"조치: 성공 토스트 확인 / 신규 shortcode 윈도우 내 미회수 → "
                    f"프로필에서 게시물 URL 수동 확인 요망 (재발행 금지)"
                )
                await context.close()
                # exit 비0(미확정) 이되, '실패' 와 구분되는 코드(9)로 종료.
                sys.exit(9)

            if not url:
                # (수정 4) 신규 shortcode 미확인 + 토스트도 없음 = 게시 미확정(발행실패).
                # review_queue 발행완료 기록 절대 금지. exit 비0 + 텔레그램 실패 보고.
                print(
                    f"[ERROR] post {slot} 신규 게시물(shortcode)·성공 토스트 모두 미확인 → 게시 실패로 판정 "
                    f"(false-positive 사고 재발 방지 — exit 0/핀글 URL 단정 금지). review_queue 갱신 안 함."
                )
                telegram_report(
                    f"⛔ AI CTO 인스타 publish 실패 — 게시 미확정\n"
                    f"post: {slot}\n폴더: {content_folder.name}\n"
                    f"조치: 성공 토스트·신규 shortcode 모두 미등장 → 발행완료 미기록 (수동 확인 필요)"
                )
                await context.close()
                sys.exit(8)
            published[slot] = url
            print(f"[INFO] post {slot} 발행 성공(신규 shortcode 확인) — {url}")

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

    # 수동 발행 경로에서도 큐 자동 갱신 (ig_review_publish_watcher 와 동일 필드명)
    update_review_queue(content_folder, published)

    return published


async def _publish_single_post(
    page,
    spec: PostSpec,
    content_folder: Path,
    location: str = "",
    mentions: list[str] | None = None,
    account: str = DEFAULT_ACCOUNT,
) -> tuple[str | None, str]:
    """단일 post 발행. (게시 URL, outcome) 반환.

    outcome (FIX2 — 3분류):
      "발행완료"  — 신규 shortcode 확인(URL 회수 성공). url=실게시 URL.
      "확인필요"  — 성공 토스트는 떴으나 윈도우 내 신규 shortcode 미확정.
                    발행됐을 가능성 높음 → '발행실패'로 단정·재시도 금지(중복 발행 방지).
                    url=None, 상위에서 status='확인필요'로 기록 + 수동 URL 확인 안내.
      "발행실패"  — 토스트도 신규 shortcode 도 없음(게시 미확정 가능성). url=None.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_prefix = EVIDENCE_DIR / f"instagram-publish-{content_folder.name}-post{spec.slot}-{timestamp}"

    # (수정 1+2) 발행 직전 그리드 shortcode 집합 수집 — 핀 글 포함.
    # 발행 후 (current - before) 차집합으로 '신규' 게시물만 실게시로 인정한다.
    # 그리드 수집은 프로필로 이동하므로 반드시 업로드 시작 전에 수행한다.
    before_shortcodes = await _collect_grid_shortcodes(page, account)
    print(f"[INFO]   발행 전 그리드 shortcode {len(before_shortcodes)}개 수집 (신규 검증 기준선)")
    # 그리드로 이동했으므로 홈으로 복귀 후 새 게시물 흐름 진입
    await page.goto(INSTAGRAM_HOME_URL, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(2000)

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
    video_count = sum(1 for p in spec.image_paths if p.suffix.lower() == ".mp4")
    image_count = len(spec.image_paths) - video_count
    print(f"[INFO]   파일 업로드 시작 — 이미지 {image_count}장 + 영상 {video_count}개 (총 {len(spec.image_paths)})")
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
    final_caption = spec.merged_caption(extra_mentions=mentions)
    await page.keyboard.type(final_caption, delay=15)
    print(f"[INFO]   캡션 입력 완료 ({len(final_caption)} chars)")

    # 위치 태그 추가 (location 있을 때만, graceful — 실패해도 발행 차단 안 함)
    if location:
        await _add_location(page, location, evidence_prefix)

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

    # (수정 5) 발행 시도 시각(UTC) 기록 — 최신 게시물 시각 근접 판정(폴백)의 기준선.
    from datetime import timezone as _tz
    attempt_started_utc = datetime.now(_tz.utc)

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

    # (수정 1) 게시 완료 판정 — "공유하기 버튼 사라짐"을 완료로 간주하지 않는다.
    # 영상 캐러셀은 '공유 중' 스피너로 공유 버튼이 먼저 사라져 오탐 → 프로필 이동+context.close()로
    # 실제 업로드 중단 사고가 발생했다. 다음 둘 중 하나가 확인될 때까지 최대 180초 폴링하며
    # 절대 context.close() 하지 않는다(상위 run_publish 가 닫음 — 여기선 확정 전 이탈 금지):
    #   (a) 성공 토스트 ':text("게시물이 공유되었습니다")' / '회원님의 게시물이 공유', 또는
    #   (b) (가장 확실) 발행계정 그리드에 '발행 전엔 없던' 신규 shortcode 등장.
    # 토스트 폴링 단계에서는 프로필로 이동하지 않는다(업로드 진행 중 dialog 보존).
    MAX_WAIT_SEC = 180
    toast_confirmed = False
    waited = 0
    while waited < MAX_WAIT_SEC:
        await page.wait_for_timeout(2000)
        waited += 2
        try:
            done1 = await page.locator(':text("게시물이 공유되었습니다")').count()
            done2 = await page.locator(':text("회원님의 게시물이 공유")').count()
        except Exception:
            done1 = done2 = 0
        if done1 > 0 or done2 > 0:
            toast_confirmed = True
            print(f"[INFO]   게시 완료 토스트 확인 ({waited}s 경과)")
            break
        if waited % 20 == 0:
            print(f"[INFO]   게시 완료 대기 중... ({waited}/{MAX_WAIT_SEC}s)")
    if not toast_confirmed:
        print(
            f"[WARN]   성공 토스트 {MAX_WAIT_SEC}s 내 미확인 — 그리드 신규 shortcode 검증으로 최종 확정"
        )
    await page.screenshot(path=str(evidence_prefix.with_suffix(".post_share.png")))

    # (수정 1+2 · FIX2) 확정 검증: 발행계정 그리드에 '발행 전엔 없던' 신규 shortcode 등장 폴링.
    # 토스트가 확인됐어도 실게시 URL(신규 shortcode) 회수를 끝까지 시도한다.
    # FIX2: 캐시 지연 오탐 방지를 위해 폴링 윈도우 확대(총 대기 ~90s).
    #       각 폴 사이 ~5s 대기 × 18회 = 약 90s. (구: 6회×5s≈30s)
    #       _collect_grid_shortcodes 가 매 폴마다 캐시 우회 reload 하므로 캐시지연을 흡수.
    GRID_POLL_INTERVAL_MS = 5000
    grid_polls = 18 if toast_confirmed else max(1, (MAX_WAIT_SEC - waited) // 5)
    new_url: str | None = None
    for attempt in range(grid_polls):
        new_url = await _capture_new_post_url(page, account, before_shortcodes)
        if new_url:
            break
        if attempt < grid_polls - 1:
            await page.wait_for_timeout(GRID_POLL_INTERVAL_MS)
            print(f"[INFO]   신규 shortcode 미등장 — 재폴링 ({attempt + 1}/{grid_polls})")

    # (수정 5: 2026-06-02 false-negative 사고 재발방지)
    # 그리드 shortcode 스크랩이 0건/실패여도 '게시 실패'를 단정하지 않는다.
    # 오늘 사고: 그리드 a[href*="/p/"] 0건 회수 → 실게시를 실패로 오판(하마터면 중복 재발행).
    # 폴백: 그리드 차집합이 비었고(=before/after 모두 스크랩 실패 의심), 토스트가 떴다면,
    #       프로필 '최신 게시물 1건'을 직접 열어 게시 시각이 발행 시도 시각과 근접(±10분)하면
    #       그 게시물을 실게시로 인정한다. (false-positive·false-negative 양방향 가드)
    if new_url is None and toast_confirmed and not before_shortcodes:
        print(
            "[INFO]   그리드 차집합 비어 있고 토스트 확인됨 → 최신 게시물 직접 열람 폴백 검증 시작 "
            "(그리드 스크랩 false-negative 가드)"
        )
        new_url = await _verify_via_latest_post(page, account, attempt_started_utc)

    # (FIX2) outcome 3분류 — 신규 shortcode 미확정 시 '발행실패' 단정 금지.
    if new_url:
        return new_url, "발행완료"
    if toast_confirmed:
        # 성공 토스트는 떴는데 신규 shortcode 를 윈도우 내 못 잡음 = 캐시지연/스크랩 한계.
        # 발행됐을 가능성 높음 → '확인필요'(미확정). 재시도 트리거 금지(중복 발행 사고 방지).
        print(
            "[WARN]   성공 토스트 확인됐으나 신규 shortcode 윈도우 내 미회수 → "
            "'확인필요'(발행됐을 가능성 높음, URL 수동확인). 발행실패 단정·재시도 안 함."
        )
        return None, "확인필요"
    return None, "발행실패"


async def _add_location(page, location: str, evidence_prefix: Path) -> None:
    """캡션 화면에서 '위치 추가' UI 진입 → 검색어 입력 → 첫 결과 클릭.
    셀렉터 미발견 또는 예외 시 [WARN]+스크린샷으로 graceful 처리 (발행 차단 안 함)."""
    trigger = None
    for sel in LOCATION_TRIGGER_SELECTORS:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            trigger = loc
            print(f"[INFO]   위치 추가 진입 셀렉터: {sel!r}")
            break
    if trigger is None:
        print("[WARN]   위치 추가 진입 셀렉터 미발견 — UI 변경 가능성 (위치 태그 건너뜀)")
        warn_path = str(evidence_prefix.with_suffix(".warn_location_trigger.png"))
        await page.screenshot(path=warn_path)
        print(f"[WARN]   스크린샷: {warn_path}")
        return
    try:
        await trigger.click(timeout=5000)
    except Exception as e:
        print(f"[WARN]   위치 추가 진입 클릭 실패: {e} (위치 태그 건너뜀)")
        warn_path = str(evidence_prefix.with_suffix(".warn_location_click.png"))
        await page.screenshot(path=warn_path)
        return
    await page.wait_for_timeout(1500)

    inp = None
    for sel in LOCATION_INPUT_SELECTORS:
        loc = page.locator(sel).first
        if await loc.count() > 0:
            inp = loc
            print(f"[INFO]   위치 입력창 셀렉터: {sel!r}")
            break
    if inp is None:
        print("[WARN]   위치 입력창 미발견 — 위치 태그 건너뜀")
        warn_path = str(evidence_prefix.with_suffix(".warn_location_input.png"))
        await page.screenshot(path=warn_path)
        return

    try:
        await inp.fill("")
        await inp.type(location, delay=30)
        await page.wait_for_timeout(1500)
        # 첫 검색 결과 클릭
        first_result = page.locator('div[role="option"]').first
        if await first_result.count() == 0:
            # 후보 fallback
            first_result = page.locator('div[role="listbox"] div').first
        if await first_result.count() > 0:
            await first_result.click(timeout=4000)
            print(f"[INFO]   위치 태그 선택 완료: {location!r}")
        else:
            print(f"[WARN]   위치 검색 결과 없음: {location!r} (위치 태그 건너뜀)")
            warn_path = str(evidence_prefix.with_suffix(".warn_location_result.png"))
            await page.screenshot(path=warn_path)
    except Exception as e:
        print(f"[WARN]   위치 태그 추가 예외: {e} (발행 계속)")
        warn_path = str(evidence_prefix.with_suffix(".warn_location_exc.png"))
        await page.screenshot(path=warn_path)


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


async def _collect_grid_shortcodes(page, account: str) -> set[str]:
    """발행 계정 프로필 그리드에 현재 보이는 게시물 shortcode 집합을 수집.

    고정(핀) 게시물 포함 — 핀 글은 발행 전/후 모두 그리드에 있으므로
    before-set 에 그대로 들어가 (current - before) 차집합에서 자연 제외된다.
    URL 회수가 아니라 '집합' 만 수집 (수정 2: 핀 글 오회수 차단의 기반).
    """
    shortcodes: set[str] = set()
    try:
        # (FIX2) 캐시 우회 — 발행 후 그리드가 캐시된 옛 목록을 반환해
        # 신규 shortcode 가 안 보이는 false-negative(오늘 #4 사고) 방지.
        # 타임스탬프 쿼리로 URL 유니크화 + reload(no-cache 의도).
        cache_buster = int(datetime.now().timestamp() * 1000)
        profile_url = f"https://www.instagram.com/{account}/?__r={cache_buster}"
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=20_000)
        # 그리드 로딩 대기 (최대 10초 폴링)
        for _ in range(10):
            await page.wait_for_timeout(1000)
            if await page.locator('a[href*="/p/"]').count() > 0:
                break
        hrefs = await page.locator('a[href*="/p/"]').evaluate_all(
            "els => els.map(e => e.getAttribute('href'))"
        )
        for href in hrefs:
            if not href:
                continue
            full = href if href.startswith("http") else f"https://www.instagram.com{href}"
            m = POST_URL_PATTERN.search(full)
            if m:
                shortcodes.add(m.group(1))
    except Exception as e:
        print(f"[WARN]   그리드 shortcode 수집 예외: {e}")
    return shortcodes


def _is_today_kst(datetime_attr: str) -> bool:
    """time[datetime] ISO 문자열이 오늘(KST, UTC+9)인지 교차 확인 (보조 검증)."""
    try:
        from datetime import timedelta, timezone

        # 인스타 time datetime 은 보통 UTC ISO (Z 또는 +00:00). KST 로 환산해 날짜 비교.
        raw = datetime_attr.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        kst = timezone(timedelta(hours=9))
        today_kst = datetime.now(kst).date()
        return dt.astimezone(kst).date() == today_kst
    except Exception:
        return False


async def _capture_new_post_url(
    page, account: str, before_shortcodes: set[str]
) -> str | None:
    """게시 완료 후 (current - before) 신규 shortcode 를 실게시 URL 로 회수 (수정 2).

    - 발행 직전 그리드 shortcode 집합(before_shortcodes)을 받아, 발행 후 그리드와
      차집합을 계산해 '발행 전엔 없던' 신규 shortcode 만 게시 URL 로 회수한다.
    - 신규 shortcode 가 없으면 None 반환 (성공 단정 금지 — 핀 글 오회수 차단).
    - 신규가 여러 개면 time[datetime] 가 오늘(KST)인 것을 우선 채택.
    """
    try:
        current = await _collect_grid_shortcodes(page, account)
        new_codes = current - before_shortcodes
        if not new_codes:
            print(
                "[WARN]   신규 shortcode 없음 — 게시 미확정 (발행 전 그리드 대비 변화 없음). "
                "성공 단정 금지 → None 반환"
            )
            return None

        # 보조 교차검증: 신규 코드 중 time[datetime] 가 오늘(KST)인 것 우선
        chosen: str | None = None
        for code in new_codes:
            try:
                link = page.locator(f'a[href*="/p/{code}/"]').first
                if await link.count() == 0:
                    continue
                t = link.locator('time[datetime]').first
                if await t.count() > 0:
                    dt_attr = await t.get_attribute("datetime")
                    if dt_attr and _is_today_kst(dt_attr):
                        chosen = code
                        break
            except Exception:
                continue
        if chosen is None:
            # 오늘자 time 확인 실패해도 신규 shortcode 자체는 실게시 증거 → 첫 신규 채택
            chosen = sorted(new_codes)[0]
            print(
                f"[INFO]   신규 shortcode {len(new_codes)}개 감지 (오늘자 time 미확인 — 신규성으로 채택): {chosen}"
            )
        else:
            print(f"[INFO]   신규 shortcode 감지 + 오늘(KST) time 교차확인: {chosen}")
        return f"https://www.instagram.com/p/{chosen}/"
    except Exception as e:
        print(f"[WARN]   신규 게시 URL 회수 예외: {e}")
        return None


async def _verify_via_latest_post(
    page, account: str, attempt_started_utc, proximity_min: int = 10
) -> str | None:
    """(수정 5) 그리드 차집합 스크랩이 0건/실패일 때의 폴백 검증.

    프로필 '최신 게시물 1건'을 직접 열어, 그 게시 시각(time[datetime])이
    발행 시도 시각(attempt_started_utc)과 proximity_min 분 이내로 근접하면
    그 게시물을 '방금 올린 실게시'로 인정하고 URL 을 반환한다.

    오늘(2026-06-02) 사고: 그리드 a[href*="/p/"] 스크랩이 0건 → 실게시를
    '실패'로 오판(하마터면 중복 재발행). 이 폴백이 false-negative 를 막는다.
    시각 근접 조건으로 '이전 게시물 오인'(false-positive)도 동시에 차단한다.
    스크랩/파싱 실패 등 어떤 예외도 None 반환(성공 단정 절대 금지).
    """
    try:
        from datetime import timezone as _tz

        await page.goto(
            f"https://www.instagram.com/{account}/",
            wait_until="domcontentloaded",
            timeout=20_000,
        )
        # 최신 게시물 링크 등장 폴링 (그리드 로딩 지연 대비)
        first = None
        for _ in range(12):
            await page.wait_for_timeout(1500)
            cand = page.locator('main a[href*="/p/"]').first
            if await cand.count() > 0:
                first = cand
                break
        if first is None:
            print("[WARN]   폴백: 최신 게시물 링크 미등장 — 검증 보류(None)")
            return None

        href = await first.get_attribute("href")
        m = POST_URL_PATTERN.search(
            href if href and href.startswith("http") else f"https://www.instagram.com{href or ''}"
        )
        if not m:
            print("[WARN]   폴백: 최신 게시물 shortcode 파싱 실패 — None")
            return None
        shortcode = m.group(1)

        # 최신 게시물 상세 진입 → time[datetime] 시각 회수
        await first.click()
        await page.wait_for_timeout(3500)
        t = page.locator('time[datetime]').first
        if await t.count() == 0:
            print(f"[WARN]   폴백: 최신 게시물 시각(time) 미회수 — 근접판정 불가(None) [{shortcode}]")
            return None
        dt_attr = await t.get_attribute("datetime")
        raw = (dt_attr or "").strip().replace("Z", "+00:00")
        post_dt = datetime.fromisoformat(raw)
        if post_dt.tzinfo is None:
            post_dt = post_dt.replace(tzinfo=_tz.utc)

        delta_min = abs((post_dt - attempt_started_utc).total_seconds()) / 60.0
        if delta_min <= proximity_min:
            print(
                f"[INFO]   폴백 검증 성공 — 최신 게시물 시각이 발행 시도와 {delta_min:.1f}분 근접 "
                f"(≤{proximity_min}분) → 실게시 인정: {shortcode}"
            )
            return f"https://www.instagram.com/p/{shortcode}/"
        print(
            f"[WARN]   폴백: 최신 게시물 시각이 {delta_min:.1f}분 떨어짐(>{proximity_min}분) "
            f"— 이전 게시물 오인 차단(None) [{shortcode}]"
        )
        return None
    except Exception as e:
        print(f"[WARN]   폴백 검증 예외(성공 단정 금지 → None): {e}")
        return None


# -----------------------------------------------------------------
# 진입점
# -----------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="웰페리온 AI CTO — 인스타그램 Playwright v1.1 (Persistent Context · 멀티계정 · 영상 캐러셀)"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "setup-auto", "dryrun", "publish"],
        default="dryrun",
        help=(
            "setup: 최초 1회 GM님 수동 로그인 (Enter로 저장) / "
            "setup-auto: 로그인 자동 감지 저장 (Enter 불필요·백그라운드 가능) / "
            "dryrun: 세션 확인 + publish 흐름 셀렉터 후보군 전체 탐색 (기본·발행 없음) / "
            "publish: 콘텐츠 폴더 실 발행 (post_{A|B|C}_N 또는 ig_NN 형식 · 이미지+영상 혼합 캐러셀 · 비가역)"
        ),
    )
    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        help=(
            f"인스타그램 계정 식별자 (기본: {DEFAULT_ACCOUNT}). "
            "프로필 경로: profiles/instagram/{account}. "
            "예: --account wellperion"
        ),
    )
    parser.add_argument(
        "--content-folder",
        default=None,
        help=(
            "publish 모드 필수: 콘텐츠 폴더 경로 "
            "(예: instagram\\260520_바레_런칭 또는 instagram\\260426_WJO_스쿼시_대회)"
        ),
    )
    parser.add_argument(
        "--location",
        default="",
        help="위치 태그 문자열 (예: '서울 용산구 한남동'). 있을 때만 위치 추가 UI 진입.",
    )
    parser.add_argument(
        "--mentions",
        default="",
        help=(
            "캡션 멘션 핸들 목록, 콤마 구분 (예: 'namuk.wellperion,wellperion_squash'). "
            "caption 본문에 이미 있는 핸들은 중복 추가 안 함."
        ),
    )
    parser.add_argument(
        "--collaborators",
        default="",
        help=(
            "인스타 공동작업자 핸들 목록, 콤마 구분 (예: 'namuk.wellperion'). "
            "큐레이션 Collaborator/종목 매핑에 병합(중복 제거). "
            "watcher가 review_queue의 collaborators 필드를 전달할 때 사용."
        ),
    )
    parser.add_argument(
        "--caption-file",
        default=None,
        help=(
            "큐레이션_추천.md 부재 시 단일화 입력 — caption 텍스트 파일 경로. "
            "watcher/dispatcher가 review_queue.json 의 caption 을 임시파일로 전달. "
            "폴더에 큐레이션_추천.md 가 있으면 그쪽이 우선(이 인자 무시)."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "setup":
        asyncio.run(run_setup(account=args.account))
    elif args.mode == "setup-auto":
        asyncio.run(run_setup_auto(account=args.account))
    elif args.mode == "publish":
        if not args.content_folder:
            print("[ERROR] --mode publish 는 --content-folder 인자 필수")
            sys.exit(1)
        folder = Path(args.content_folder)
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        mentions_list = [m.strip() for m in args.mentions.split(",") if m.strip()] if args.mentions else []
        collab_list = [c.strip() for c in args.collaborators.split(",") if c.strip()] if args.collaborators else []
        caption_file_path = Path(args.caption_file) if args.caption_file else None
        asyncio.run(run_publish(folder, location=args.location, mentions=mentions_list, account=args.account, extra_collaborators=collab_list, caption_file=caption_file_path))
    else:
        asyncio.run(run_dryrun(account=args.account))
