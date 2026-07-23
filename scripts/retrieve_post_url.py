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
import unicodedata
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
LOGIN_SIGNALS_DANGGN = ("login", "signin", "sign-in", "auth", "accounts.daangn.com")

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


# ─── 키워드 대조 정규화 (2026-07-23 배9578) ────────────────────────────
# 실측한 미회수 24건의 원인은 '스크롤이 모자라서'가 아니라 표기 변형이었다:
#   · 띄어쓰기 차이   큐 '여름방학특강 Ep3'      ↔ 채널 '2026 여름방학 특강 Ep3 지도자편'
#   · 어미 차이       큐 '…한 곳에서 완성되다'    ↔ 채널 '…한 곳에서 완성됩니다'
#   · 제목 접두 표식  큐 '[필라테스편] 민소매가…' ↔ 채널 '민소매가 잘 어울리는 어깨…'
#   · 잘린 꼬리       큐 '운동과 회복이 한 곳에서 — ' (16자 컷 + em-dash 잔여)
# → 공백·특수문자를 지운 뒤 '앞부분 일치'로 본다. 느슨하게 푸는 게 아니라
#   변형에 안 흔들리는 부분만 비교하는 것 — 오탐을 늘리지 않도록 최소 길이를 강제한다.
_SQUASH_RE = re.compile(r"[^0-9a-z가-힣]")
KEYWORD_MIN_LEN = 8   # 이보다 짧은 키워드는 전체 일치를 요구(짧은 조각의 오탐 방지)
KEYWORD_PROBE = 12    # 긴 키워드는 앞 12자만 본다(어미·꼬리 변형 흡수)


def _squash(text: str) -> str:
    """공백·기호·대소문자를 지운 대조 키."""
    return _SQUASH_RE.sub("", unicodedata.normalize("NFKC", text or "").lower())


def _text_hit(keyword: str, text: str) -> bool:
    """keyword 가 text 안에 (표기 변형을 흡수해) 들어있는가."""
    k, t = _squash(keyword), _squash(text)
    if not k or not t:
        return False
    if len(k) < KEYWORD_MIN_LEN:
        return len(k) >= 4 and k in t
    return k[:KEYWORD_PROBE] in t


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

    async def _links_from_frame(frame) -> list[dict]:
        """
        프레임에서 블로그 포스트 링크 + 주변 텍스트 수집.
        두 URL 형식 모두 수용:
          - 구/단축형  https://blog.naver.com/{account}/{logNo}
          - PostView형 https://blog.naver.com/PostView.naver?blogId={account}&logNo={logNo}
        ★2026-07-23 배9578 실측: 목록 위젯 프레임 링크가 전부 PostView.naver?logNo=
        형식이라 옛 경로형 정규식만 쓰면 611개 중 매치 0건이었다(9건 전건 미회수 원인).
        """
        try:
            return await frame.evaluate(
                """(account) => {
                    const pathPat  = new RegExp('\\/' + account + '\\/(\\d{5,})', 'i');
                    const blogIdPat = new RegExp('[?&]blogId=' + account + '(?:&|$)', 'i');
                    const logNoPat  = /[?&]logNo=(\\d{5,})/i;
                    const out = [];
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = a.href;
                        let id = null;
                        const pm = pathPat.exec(href);
                        if (pm) {
                            id = pm[1];
                        } else if (blogIdPat.test(href)) {
                            const lm = logNoPat.exec(href);
                            if (lm) id = lm[1];
                        }
                        if (!id) continue;
                        out.push({
                            href, id,
                            text: (a.innerText || a.title || a.getAttribute('aria-label') || '').trim().substring(0, 300)
                        });
                    }
                    return out;
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

        # 중복 제거 (logNo 기준) — canonical 은 단축형으로 통일
        seen: set[str] = set()
        unique: list[dict] = []
        for lnk in all_links:
            log_no = lnk.get("id")
            if not log_no:
                continue
            canonical = f"https://blog.naver.com/{account}/{log_no}"
            if canonical in seen:
                continue
            seen.add(canonical)
            unique.append({"href": canonical, "text": lnk["text"]})

        if not unique and page_no == 1:
            return None, f"블로그 글 링크 미발견 (세션 또는 구조 변경 확인 필요) / URL={page.url}"

        for lnk in unique:
            if _text_hit(keyword, lnk["text"]):
                _log(f"  [MATCH] {lnk['href']} | text: {lnk['text'][:80]!r}")
                return lnk["href"], None

    return None, f"keyword '{keyword}' 일치 글 미발견 (블로그 {account}, 3페이지 탐색)"


# 카페 글 링크 — 구 형식(/ichon1dong/123, articleid=123)과 신 SPA 형식(.../articles/123) 모두 수용.
# ★2026-07-23 배9578 실측: 구 ArticleList.nhn/ArticleSearchList.nhn 은 이제
#   /f-e/cafes/{clubid}/menus/{menuid} 로 리다이렉트되고 링크가 .../articles/{id} 로 바뀌었다.
#   기존 정규식이 /ichon1dong/\d+ 만 봤기 때문에 목록에서 0건이 잡혔다 —
#   카페 7건 미회수의 진짜 원인은 키워드가 아니라 이 구조 변경이었다.
CAFE_ARTICLE_JS = r"""
() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const m = a.href.match(/\/articles\/(\d+)|articleid=(\d+)|\/ichon1dong\/(\d+)/i);
    if (!m) continue;
    const id = m[1] || m[2] || m[3];
    let node = a, best = (a.innerText || a.title || '').trim();
    for (let i = 0; i < 5 && node; i++) {
      const t = (node.innerText || '').trim();
      if (t.length > best.length && t.length < 400) best = t;
      node = node.parentElement;
    }
    out.push({ id, text: best.substring(0, 300) });
  }
  return out;
}
"""


async def _retrieve_cafe(page, keyword: str, account: str,
                         max_pages: int = 5) -> tuple[str | None, str]:
    """
    네이버 카페(ichon1dong) 게시판 목록에서 keyword 포함 글 URL 반환.
    신 SPA 목록(/f-e/cafes/{clubid}/menus/{menuid})을 페이지 단위로 훑는다.
    """
    scanned = 0
    for pno in range(1, max_pages + 1):
        list_url = (f"https://cafe.naver.com/f-e/cafes/{CAFE_CLUB_ID}"
                    f"/menus/{CAFE_MENU_ID}?viewType=L&page={pno}")
        try:
            await page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)
        except Exception as e:
            if pno == 1:
                return None, f"카페 목록 페이지 로드 실패: {e}"
            break

        if any(sig in page.url for sig in LOGIN_SIGNALS_NAVER):
            return None, "세션 만료 — 로그인 페이지로 리다이렉트"

        rows: list[dict] = []
        for frame in [page] + [f for f in page.frames if f is not page.main_frame]:
            try:
                rows.extend(await frame.evaluate(CAFE_ARTICLE_JS))
            except Exception:
                continue
        if not rows:
            if pno == 1:
                return None, f"카페 글 링크 미발견(구조 변경 확인 필요) / URL={page.url}"
            break
        scanned += len(rows)

        for lnk in rows:
            if _text_hit(keyword, lnk["text"]):
                canonical = f"https://cafe.naver.com/{CAFE_NAME}/{lnk['id']}"
                _log(f"  [MATCH] {canonical} | text: {lnk['text'][:80]!r}")
                return canonical, None

    return None, (f"keyword '{keyword}' 일치 글 미발견 "
                  f"(카페 {CAFE_NAME} · {max_pages}페이지 · 링크 {scanned}건 대조)")


# 카카오 관리자 '발행한 글' 목록 — 각 글의 postId + 발행일시 + 본문 미리보기.
# ★2026-07-23 배9578 실측: 공개 채널홈(pf.kakao.com/{ch})은 최신 5건 안팎만 렌더하고
#   스크롤해도 body.scrollHeight 가 자라지 않는다(과거 글 도달 불가) — 카카오 9건이
#   '스크롤 범위 밖'이었던 진짜 이유. 반면 관리자 목록은 전량(실측 140건) 나온다.
#   여기서 postId 를 얻고, 저장은 공개 permalink pf.kakao.com/{ch}/{postId} 로 한다
#   (읽기 전용 — goto·스크롤·DOM 읽기만. 발행·수정·삭제 호출 없음).
KAKAO_ADMIN_LIST_JS = r"""
() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const m = a.href.match(/\/posts\/(\d+)/);
    if (!m) continue;
    const pid = m[1];
    let node = a, best = '';
    for (let i = 0; i < 8 && node; i++) {
      const t = (node.innerText || '').trim();
      if (t.length > best.length) best = t;
      if (best.length > 120) break;
      node = node.parentElement;
    }
    if (seen.has(pid)) {
      const prev = out.find(o => o.pid === pid);
      if (prev && best.length > prev.text.length) prev.text = best.substring(0, 800);
      continue;
    }
    seen.add(pid);
    out.push({ pid, text: best.substring(0, 800) });
  }
  return out;
}
"""


async def _retrieve_kakao_admin(page, keyword: str, max_scrolls: int) -> tuple[str | None, str]:
    """관리자 발행글 목록에서 대조 → 공개 permalink 반환."""
    try:
        await page.goto(f"https://business.kakao.com/{KAKAO_CHANNEL_ID}/posts",
                        wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(6000)
    except Exception as e:
        return None, f"카카오 관리자 목록 로드 실패: {e}"
    if any(sig in page.url.lower() for sig in ("accounts.kakao.com", "/login")):
        return None, "카카오 관리자 세션 만료 — 로그인 필요"

    rows: list[dict] = []
    prev_n = -1
    for _ in range(max_scrolls):
        try:
            rows = await page.evaluate(KAKAO_ADMIN_LIST_JS)
        except Exception:
            rows = []
        if len(rows) == prev_n:
            break
        prev_n = len(rows)
        h = await page.evaluate("() => document.body.scrollHeight")
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2200)
        if await page.evaluate("() => document.body.scrollHeight") == h:
            await page.wait_for_timeout(2000)

    if not rows:
        return None, "카카오 관리자 목록에서 글 링크 미발견"
    for r in rows:
        if _text_hit(keyword, r["text"]):
            canonical = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}/{r['pid']}"
            _log(f"  [MATCH·admin] {canonical} | text: {r['text'][:80]!r}")
            return canonical, None
    return None, (f"keyword '{keyword}' 일치 글 미발견 "
                  f"(카카오 관리자 목록 {len(rows)}건 대조)")


async def _retrieve_kakao(page, keyword: str, account: str,
                          max_scrolls: int = 30) -> tuple[str | None, str]:
    """
    카카오 채널 글 URL 회수. 관리자 발행글 목록(전량)을 먼저 보고,
    실패 시 공개 채널홈(최신 몇 건만 렌더됨)으로 폴백한다.
    공개 URL 형식: pf.kakao.com/{channel_id}/{postId} (숫자 ID)
    """
    url, reason = await _retrieve_kakao_admin(page, keyword, max_scrolls)
    if url:
        return url, None
    _log(f"  [INFO] 관리자 목록 미회수({reason}) → 공개 채널홈 폴백")

    channel_url = f"https://pf.kakao.com/{KAKAO_CHANNEL_ID}"
    kw_lower    = keyword.lower()
    MAX_SCROLLS = max_scrolls

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
                const sq = s => (s||'').normalize('NFKC').toLowerCase()
                                  .replace(/[^0-9a-z가-힣]/g, '');
                const probe = sq(kw).substring(0, 12);
                const cards = [...document.querySelectorAll(cardSel)];
                for (const c of cards) {
                    const raw = (c.innerText || c.textContent || '');
                    const text = sq(raw);
                    if (text.length < 5 || probe.length < 4) continue;
                    if (!text.includes(probe)) continue;
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
                    t = await card.inner_text()
                    if _text_hit(keyword, t):
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


async def _retrieve_danggn(page, keyword: str, account: str,
                           max_scrolls: int = 30) -> tuple[str | None, str]:
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

    # 옛 글까지 닿도록 목록을 끝까지 스크롤(2026-07-23 배9578 — 종전엔 1화면만 봤다)
    for _ in range(max_scrolls):
        h = await page.evaluate("() => document.body.scrollHeight")
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1800)
        if await page.evaluate("() => document.body.scrollHeight") == h:
            break

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
        if _text_hit(keyword, item["text"]):
            m = re.search(r"daangn\.com.*?business-posts/([^/?#]+)", item["href"])
            if m:
                canonical = f"https://www.daangn.com/kr/business-posts/{m.group(1)}"
                _log(f"  [MATCH] {canonical} | text: {item['text'][:80]!r}")
                return canonical, None

    # 소식 카드 컨테이너에서 탐색
    result = await page.evaluate(
        """(kw) => {
            const sq = s => (s||'').normalize('NFKC').toLowerCase()
                              .replace(/[^0-9a-z가-힣]/g, '');
            const probe = sq(kw).substring(0, 12);
            const containers = [
                ...document.querySelectorAll(
                    '[class*="post"], [class*="Post"], article, li, [class*="item"]'
                )
            ];
            for (const c of containers) {
                const text = sq(c.innerText || c.textContent || '');
                if (probe.length >= 4 && text.includes(probe)) {
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
    max_pages: int = 5,
    max_scrolls: int = 30,
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
                url, reason = await _retrieve_cafe(page, keyword, account, max_pages)
            elif channel == "kakao":
                url, reason = await _retrieve_kakao(page, keyword, account, max_scrolls)
            elif channel == "danggn":
                url, reason = await _retrieve_danggn(page, keyword, account, max_scrolls)
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
    parser.add_argument("--max-pages", type=int, default=5,
                        help="카페 등 페이지 목록 탐색 상한(기본 5). 옛 글은 넉넉히")
    parser.add_argument("--max-scrolls", type=int, default=30,
                        help="카카오·당근 목록 스크롤 상한(기본 30)")
    args = parser.parse_args()

    url, reason = asyncio.run(
        _retrieve_url_async(args.channel, args.keyword, args.account, args.headful,
                            args.max_pages, args.max_scrolls)
    )

    if url:
        print(url)
        return 0
    else:
        print(f"NOT_FOUND:{reason}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
