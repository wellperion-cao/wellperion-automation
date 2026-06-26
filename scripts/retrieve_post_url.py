# scripts/retrieve_post_url.py
# 채널 글 목록 URL 회수 엔진 (읽기 전용)
#
# 정책:
#   - 읽기·탐색 전용. 발행·수정·삭제 일체 금지.
#   - 긍정 일치(keyword가 실제 글에서 발견됨)일 때만 URL 반환.
#   - 못 찾으면 None 반환, 추측 URL 절대 생성 금지.
#
# 공개 API:
#   retrieve_url(channel, keyword, account='wellperion', headful=False) -> str | None
#   channel: blog | cafe | kakao | danggn
#
# CLI:
#   python scripts/retrieve_post_url.py --channel blog --keyword "발레 신규" [--account wellperion] [--headful]
#   출력: URL 또는 NOT_FOUND:<사유>
#
# 세션 경로 (기존 upload 스크립트와 동일):
#   blog   → profiles/naver-blog/
#   cafe   → profiles/naver-cafe/
#   kakao  → profiles/kakao-channel/
#   danggn → profiles/danggn/

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import urllib.parse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")

# 채널별 세션 프로파일 경로 (기존 upload 스크립트 PERSISTENT_PROFILE_DIR 재사용)
BLOG_PROFILE   = ROOT / "profiles" / "naver-blog"
CAFE_PROFILE   = ROOT / "profiles" / "naver-cafe"
KAKAO_PROFILE  = ROOT / "profiles" / "kakao-channel"
DANGGN_PROFILE = ROOT / "profiles" / "danggn"

# 채널 상수
DEFAULT_BLOG_ACCOUNT  = "wellperion"
CAFE_CLUB_ID          = 11948735   # 동부이촌동 커뮤니티 (cafe_upload_playwright.py 실측)
CAFE_MENU_ID          = 659        # 웰페리온 Spa&Fitness 게시판
CAFE_NAME             = "ichon1dong"
KAKAO_CHANNEL_ID      = "_cgxiKj"  # 웰페리온 카카오 채널 (engagement_probe_cafe_kakao.py 실측)
DANGGN_BIZ_ACCOUNT_ID = "2769927"  # danggn_upload_playwright.py 실측

LOGIN_SIGNALS_NAVER  = ("nid.naver.com/nidlogin", "nid.naver.com/login")
LOGIN_SIGNALS_KAKAO  = ("accounts.kakao.com", "/login", "logon")
LOGIN_SIGNALS_DANGGN = ("login", "signin", "auth")

VALID_CHANNELS = {"blog", "cafe", "kakao", "danggn"}


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _import_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        print(
            "[ERROR] playwright 미설치. .venv 활성화 후 "
            "'pip install playwright; playwright install chromium' 실행 필요.",
            file=sys.stderr,
        )
        sys.exit(10)


def _profile_for(channel: str) -> Path:
    return {
        "blog":   BLOG_PROFILE,
        "cafe":   CAFE_PROFILE,
        "kakao":  KAKAO_PROFILE,
        "danggn": DANGGN_PROFILE,
    }[channel]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ─────────────────────────────────────────────
# 채널별 탐색 함수
# ─────────────────────────────────────────────

async def _retrieve_blog(page, keyword: str, account: str) -> tuple[str | None, str]:
    """
    네이버 블로그 글 목록에서 keyword 포함 글 URL 반환.
    blog.naver.com/{account} 주 프레임 + 서브프레임에서 글 링크 탐색.
    최대 3페이지 탐색.
    """
    blog_main = f"https://blog.naver.com/{account}"
    kw_lower  = keyword.lower()
    # 블로그 포스트 URL 패턴: /{account}/숫자(logNo)
    post_re = re.compile(rf"/{re.escape(account)}/(\d{{5,}})", re.IGNORECASE)

    async def _links_from_frame(frame) -> list[dict]:
        """프레임에서 블로그 포스트 링크 + 주변 텍스트 수집."""
        try:
            return await frame.evaluate(
                """(account) => {
                    const pat = new RegExp('\\/' + account + '\\/(\\d{5,})', 'i');
                    return [...document.querySelectorAll('a[href]')]
                        .filter(a => pat.test(a.href))
                        .map(a => ({
                            href: a.href,
                            text: (a.innerText || a.title || a.getAttribute('aria-label') || '').trim().substring(0, 300)
                        }));
                }""",
                account,
            )
        except Exception:
            return []

    for page_no in range(1, 4):
        if page_no == 1:
            try:
                await page.goto(blog_main, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(3000)
            except Exception as e:
                return None, f"블로그 메인 페이지 로드 실패: {e}"
        else:
            # 블로그 글 목록 직접 이동 (페이지네이션)
            list_url = f"https://blog.naver.com/{account}/PostList.naver?currentPage={page_no}"
            try:
                await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2500)
            except Exception:
                break

        # 로그인 상태 확인
        if any(sig in page.url for sig in LOGIN_SIGNALS_NAVER):
            return None, "세션 만료 — 로그인 페이지로 리다이렉트"

        # 메인 프레임 + 모든 서브프레임 수집
        all_links: list[dict] = []
        all_links.extend(await _links_from_frame(page))
        for frame in page.frames:
            if frame is page.main_frame:
                continue
            all_links.extend(await _links_from_frame(frame))

        # 중복 제거 (logNo 기준)
        seen: set[str] = set()
        unique: list[dict] = []
        for lnk in all_links:
            m = post_re.search(lnk["href"])
            if not m:
                continue
            canonical = f"https://blog.naver.com/{account}/{m.group(1)}"
            if canonical in seen:
                continue
            seen.add(canonical)
            unique.append({"href": canonical, "text": lnk["text"]})

        if not unique and page_no == 1:
            return None, f"블로그 글 링크 미발견 (세션 또는 구조 변경 확인 필요) / URL={page.url}"

        for lnk in unique:
            if kw_lower in lnk["text"].lower():
                _log(f"  [MATCH] {lnk['href']} | text: {lnk['text'][:80]!r}")
                return lnk["href"], None

    return None, f"keyword '{keyword}' 일치 글 미발견 (블로그 {account}, 3페이지 탐색)"


async def _retrieve_cafe(page, keyword: str, account: str) -> tuple[str | None, str]:
    """
    네이버 카페(ichon1dong) ArticleSearchList 에서 keyword 포함 글 URL 반환.
    iframe#cafe_main 내부에서 탐색.
    """
    kw_encoded = urllib.parse.quote(keyword)
    search_url = (
        f"https://cafe.naver.com/ArticleSearchList.nhn"
        f"?search.clubid={CAFE_CLUB_ID}"
        f"&search.searchBy=0"
        f"&search.query={kw_encoded}"
        f"&search.menuid={CAFE_MENU_ID}"
    )
    kw_lower = keyword.lower()
    article_re = re.compile(rf"/{re.escape(CAFE_NAME)}/(\d+)")

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        return None, f"카페 검색 페이지 로드 실패: {e}"

    if any(sig in page.url for sig in LOGIN_SIGNALS_NAVER):
        return None, "세션 만료 — 로그인 페이지로 리다이렉트"

    async def _search_frame(frame) -> str | None:
        try:
            links = await frame.evaluate(
                """(cafeName) => {
                    const pat = new RegExp('\\/' + cafeName + '\\/(\\d+)', 'i');
                    return [...document.querySelectorAll('a[href]')]
                        .filter(a => pat.test(a.href))
                        .map(a => ({
                            href: a.href,
                            text: (a.innerText || a.title || '').trim().substring(0, 300)
                        }));
                }""",
                CAFE_NAME,
            )
            for lnk in links:
                if kw_lower in lnk["text"].lower():
                    m = article_re.search(lnk["href"])
                    if m:
                        canonical = f"https://cafe.naver.com/{CAFE_NAME}/{m.group(1)}"
                        _log(f"  [MATCH] {canonical} | text: {lnk['text'][:80]!r}")
                        return canonical
        except Exception:
            pass
        return None

    # 메인 프레임 시도
    result = await _search_frame(page)
    if result:
        return result, None

    # iframe#cafe_main 시도 (카페는 iframe 구조 사용)
    iframe_handle = await page.query_selector("iframe#cafe_main")
    if iframe_handle:
        frame = await iframe_handle.content_frame()
        if frame:
            await frame.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)
            result = await _search_frame(frame)
            if result:
                return result, None

    return None, f"keyword '{keyword}' 일치 글 미발견 (카페 {CAFE_NAME} 검색)"


async def _retrieve_kakao(page, keyword: str, account: str) -> tuple[str | None, str]:
    """
    카카오 채널 공개 페이지(pf.kakao.com/_cgxiKj)를 무로그인으로 탐색.
    글 목록을 끝까지 스크롤해 keyword 포함 포스트를 찾아 URL 반환.
    공개 URL 형식: pf.kakao.com/{channel_id}/{postId} (숫자 ID)

    오늘 실증 경로(2026-06-26):
      '진짜 대회'→113739016, '시상대에 올랐'→113752558, '그 뒤엔, 한 사람'→113761120
    """
    channel_url = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}"
    kw_lower    = MAX_SCROLLS = None  # 타입 힌트용
    kw_lower    = keyword.lower()
    MAX_SCROLLS = 20  # 글이 많지 않으므로 20회 스크롤로 충분

    try:
        await page.goto(channel_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        return None, f"카카오 공개 채널 페이지 로드 실패: {e}"

    # pf.kakao.com 포스트 선택자 후보 (카드/리스트 형태)
    CARD_SEL = (
        "li, article, "
        "[class*='post'], [class*='Post'], "
        "[class*='story'], [class*='Story'], "
        "[class*='item'], [class*='Item'], "
        "[class*='card'], [class*='Card']"
    )

    for scroll_idx in range(MAX_SCROLLS):
        # 현재 화면 포스트에서 keyword 탐색
        matched = await page.evaluate(
            """([kw, cardSel]) => {
                const kw_lower = kw.toLowerCase();
                const cards = [...document.querySelectorAll(cardSel)];
                for (const c of cards) {
                    const text = (c.innerText || c.textContent || '').toLowerCase();
                    if (text.length < 5) continue;
                    if (!text.includes(kw_lower)) continue;
                    // 해당 카드의 링크(pf.kakao.com/{id} 또는 /{숫자}) 추출
                    const anchors = [c, ...c.querySelectorAll('a[href]')];
                    for (const a of anchors) {
                        const href = a.tagName === 'A' ? a.href : '';
                        if (href && (href.includes('pf.kakao.com') || /\\/\\d{6,}/.test(href))) {
                            return { href, text: c.innerText.trim().substring(0, 200) };
                        }
                    }
                    // 링크 없는 클릭 가능 카드
                    return { href: null, text: c.innerText.trim().substring(0, 200) };
                }
                return null;
            }""",
            [keyword, CARD_SEL],
        )

        if matched:
            text = matched.get("text", "")
            href = matched.get("href")
            _log(f"  [MATCH] text={text[:80]!r}")

            if href:
                # href에서 직접 postId 추출
                m = re.search(r"pf\.kakao\.com/[^/?#]+/(\d+)", href)
                if m:
                    canonical = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}/{m.group(1)}"
                    _log(f"  [URL 직접] {canonical}")
                    return canonical, None
                # 상대 경로 숫자 패턴
                m2 = re.search(r"/(\d{6,})", href)
                if m2:
                    canonical = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}/{m2.group(1)}"
                    _log(f"  [URL 상대→정규화] {canonical}")
                    return canonical, None
                # 절대 이동 후 URL 수거
                try:
                    await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1500)
                    final = page.url
                    m3 = re.search(r"pf\.kakao\.com/[^/?#]+/(\d+)", final)
                    if m3:
                        canonical = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}/{m3.group(1)}"
                        _log(f"  [URL 이동 회수] {canonical}")
                        return canonical, None
                except Exception:
                    pass

            # href 없음 → 해당 카드 클릭 후 주소창 URL 수거
            try:
                cards = await page.query_selector_all(CARD_SEL)
                for card in cards:
                    t = (await card.inner_text()).lower()
                    if kw_lower in t:
                        async with page.expect_navigation(timeout=15000):
                            await card.click()
                        final = page.url
                        m4 = re.search(r"pf\.kakao\.com/[^/?#]+/(\d+)", final)
                        if m4:
                            canonical = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}/{m4.group(1)}"
                            _log(f"  [클릭 URL 회수] {canonical}")
                            return canonical, None
                        break
            except Exception as e:
                _log(f"  [WARN] 클릭 탐색 실패: {e}")

        # 스크롤 후 새 콘텐츠 대기
        prev_h = await page.evaluate("() => document.body.scrollHeight")
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1800)
        new_h = await page.evaluate("() => document.body.scrollHeight")
        if new_h == prev_h:
            break  # 더 이상 로드할 콘텐츠 없음

    return None, (
        f"keyword '{keyword}' 일치 글 미발견 "
        f"(공개 채널 pf.kakao.com/{KAKAO_CHANNEL_ID}, {scroll_idx + 1}회 스크롤)"
    )


async def _retrieve_danggn(page, keyword: str, account: str) -> tuple[str | None, str]:
    """
    당근 비즈프로필 게시 목록에서 keyword 포함 글 URL 반환.
    세션 만료 시 NOT_FOUND 반환 (추측 URL 생성 금지).
    공개 URL 형식: daangn.com/kr/business-posts/{id}
    """
    posts_url = (
        f"https://bizprofile.daangn.com/biz_accounts/{DANGGN_BIZ_ACCOUNT_ID}/manager/posts/"
    )
    kw_lower = keyword.lower()

    try:
        await page.goto(posts_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(3500)
    except Exception as e:
        return None, f"당근 게시 목록 로드 실패: {e}"

    # 세션 만료 확인 (당근 세션 TTL ≈ 8-9h — danggn_upload_playwright.py 주석)
    current_url = page.url
    if any(sig in current_url.lower() for sig in LOGIN_SIGNALS_DANGGN):
        return None, "세션 만료 — 당근 로그인 페이지로 리다이렉트"

    # daangn.com business-posts URL 패턴으로 글 링크 수집
    post_items = await page.evaluate(
        """() => {
            return [...document.querySelectorAll('a[href]')]
                .filter(a => a.href.includes('daangn.com'))
                .map(a => ({
                    href: a.href,
                    text: (a.innerText || a.textContent || '').trim().substring(0, 300)
                }));
        }"""
    )
    for item in post_items:
        if kw_lower in item["text"].lower():
            m = re.search(r"daangn\.com.*?business-posts/([^/?#]+)", item["href"])
            if m:
                canonical = f"https://www.daangn.com/kr/business-posts/{m.group(1)}"
                _log(f"  [MATCH] {canonical} | text: {item['text'][:80]!r}")
                return canonical, None

    # 소식 카드 컨테이너에서 탐색
    result = await page.evaluate(
        """(kw) => {
            const kw_lower = kw.toLowerCase();
            const containers = [
                ...document.querySelectorAll(
                    '[class*="post"], [class*="Post"], article, li, [class*="item"]'
                )
            ];
            for (const c of containers) {
                const text = (c.innerText || c.textContent || '').toLowerCase();
                if (text.includes(kw_lower)) {
                    const a = c.querySelector('a[href]');
                    if (a && a.href.includes('daangn.com')) {
                        return { href: a.href, text: c.innerText.trim().substring(0, 200) };
                    }
                }
            }
            return null;
        }""",
        keyword,
    )
    if result:
        m = re.search(r"daangn\.com.*?business-posts/([^/?#]+)", result["href"])
        if m:
            canonical = f"https://www.daangn.com/kr/business-posts/{m.group(1)}"
            _log(f"  [MATCH] {canonical} | text: {result['text'][:80]!r}")
            return canonical, None

    return None, f"keyword '{keyword}' 일치 글 미발견 (당근 계정 {DANGGN_BIZ_ACCOUNT_ID})"


# ─────────────────────────────────────────────
# 브라우저 컨텍스트 공통 런처
# ─────────────────────────────────────────────

async def _retrieve_url_async(
    channel: str,
    keyword: str,
    account: str,
    headful: bool,
) -> tuple[str | None, str]:
    """내부 비동기 구현. 브라우저 기동→탐색→종료."""
    profile_dir = _profile_for(channel)

    if not profile_dir.exists():
        return (
            None,
            f"세션 프로파일 없음: {profile_dir} "
            f"(해당 upload 스크립트 --mode setup 먼저 실행 필요)",
        )

    async_playwright = _import_playwright()

    async with async_playwright() as p:
        launch_kwargs: dict = {
            "user_data_dir": str(profile_dir),
            "headless": not headful,
        }
        if headful:
            launch_kwargs["args"] = ["--start-maximized"]
            launch_kwargs["no_viewport"] = True
        else:
            launch_kwargs["viewport"] = {"width": 1280, "height": 900}

        context = await p.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            if channel == "blog":
                url, reason = await _retrieve_blog(page, keyword, account)
            elif channel == "cafe":
                url, reason = await _retrieve_cafe(page, keyword, account)
            elif channel == "kakao":
                url, reason = await _retrieve_kakao(page, keyword, account)
            elif channel == "danggn":
                url, reason = await _retrieve_danggn(page, keyword, account)
            else:
                url, reason = None, f"지원하지 않는 채널: {channel!r}"
        except Exception as e:
            url, reason = None, f"예외 발생: {e}"
        finally:
            await context.close()

    return url, reason


# ─────────────────────────────────────────────
# 공개 동기 API
# ─────────────────────────────────────────────

def retrieve_url(
    channel: str,
    keyword: str,
    account: str = "wellperion",
    headful: bool = False,
) -> str | None:
    """
    채널 글 목록에서 keyword 포함 글을 찾아 URL 반환. 못 찾으면 None.

    channel: blog | cafe | kakao | danggn
    keyword: 글 식별용 제목/본문 핵심 구절
    account: 네이버 블로그 ID 등 (기본: wellperion)
    headful: True이면 브라우저 창 표시

    정책: 긍정 일치 시에만 반환. 추측 URL 절대 생성 금지.
    """
    if channel not in VALID_CHANNELS:
        raise ValueError(f"지원 채널: {VALID_CHANNELS} / 입력: {channel!r}")
    url, _reason = asyncio.run(_retrieve_url_async(channel, keyword, account, headful))
    return url


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="채널 글 목록에서 keyword 포함 글 URL 회수 (읽기 전용)"
    )
    parser.add_argument(
        "--channel", required=True, choices=list(VALID_CHANNELS),
        help="채널 종류: blog | cafe | kakao | danggn",
    )
    parser.add_argument("--keyword", required=True, help="글 식별용 핵심 구절")
    parser.add_argument("--account", default="wellperion", help="계정 ID (기본: wellperion)")
    parser.add_argument("--headful", action="store_true", help="브라우저 창 표시 (디버그)")
    args = parser.parse_args()

    url, reason = asyncio.run(
        _retrieve_url_async(args.channel, args.keyword, args.account, args.headful)
    )

    if url:
        print(url)
        return 0
    else:
        print(f"NOT_FOUND:{reason}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
