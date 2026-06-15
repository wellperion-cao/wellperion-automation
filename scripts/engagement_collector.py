# scripts/engagement_collector.py
# v1.1 — 채널별 engagement 수집기
#
# 로그인 없이 수집 가능한 채널:
#   당근(danggn) — 공개 비즈포스트 HTML에서 viewCount/bookmarkCount/commentCount 파싱
#   블로그(blog)  — RSS feed에서 신규 글 감지 (조회수는 로그인 필요 → 플래그)
#
# Persistent Profile 세션 사용 채널 (headful, GM 데스크톱 필요):
#   카페(cafe)   — profiles/naver-cafe/ 세션, iframe#cafe_main → span.count 파싱
#                  실측(2026-06-15): "조회 70" 형식
#   카카오(kakao) — profiles/kakao-channel/ 세션, span.num_g 파싱
#                  실측(2026-06-15): 좋아요수·댓글수 각 span.num_g
#
# 로그인 필요 채널 (FACEBOOK_ENABLED=OFF 정책):
#   인스타그램 — Meta Graph API 토큰 필요 → 수집 제외
#
# 사용법:
#   python scripts/engagement_collector.py            # 전체 수집 (danggn+blog, cafe/kakao 제외)
#   python scripts/engagement_collector.py --channel danggn
#   python scripts/engagement_collector.py --channel blog
#   python scripts/engagement_collector.py --channel cafe
#   python scripts/engagement_collector.py --channel kakao
#   python scripts/engagement_collector.py --channel desktop  # GM 데스크톱: danggn+blog+cafe+kakao 전부
#   python scripts/engagement_collector.py --dry-run  # 파일 저장 없이 결과만 출력
#
# 출력: 3. 웰페리온 가이드/cmo/funnel/engagement/engagement_feed.json (대시보드 소비)
#       3. 웰페리온 가이드/cmo/funnel/engagement/danggn_snapshot.json (당근 스냅샷)
#       3. 웰페리온 가이드/cmo/funnel/engagement/cafe_snapshot.json   (카페 스냅샷)
#       3. 웰페리온 가이드/cmo/funnel/engagement/kakao_snapshot.json  (카카오 스냅샷)

import argparse
import asyncio
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 경로 ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
ENGAGEMENT_DIR = ROOT / "3. 웰페리온 가이드" / "cmo" / "funnel" / "engagement"
FEED_PATH = ENGAGEMENT_DIR / "engagement_feed.json"
DANGGN_SNAP_PATH = ENGAGEMENT_DIR / "danggn_snapshot.json"
REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"

KST = timezone(timedelta(hours=9))


def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


# ── 공통 HTTP fetch ────────────────────────────────────
def _fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ── 스냅샷 로드/저장 ──────────────────────────────────
def _load_snap(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_snap(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── engagement_feed.json 로드/저장 ───────────────────
def _load_feed() -> dict:
    if FEED_PATH.exists():
        try:
            return json.loads(FEED_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated_at": "", "events": [], "note": "engagement_collector.py 자동 생성"}


def _save_feed(feed: dict) -> None:
    FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEED_PATH.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")


# ════════════════════════════════════════════════════
# 채널 1: 당근 (로그인 불필요 — 공개 포스트 HTML 파싱)
# ════════════════════════════════════════════════════
def _parse_danggn_post(url: str) -> dict | None:
    """
    공개 비즈포스트 URL에서 counter JSON 파싱.
    실측 확인 (2026-06-07): "counter":{"viewCount":N,"chatRoomCount":N,"bookmarkCount":N,"commentCount":N}
    """
    try:
        body = _fetch(url)
    except Exception as e:
        print(f"  [WARN] 당근 fetch 실패: {url} — {e}")
        return None

    m = re.search(r'"counter":\{([^}]+)\}', body)
    if not m:
        return None
    try:
        counter = json.loads("{" + m.group(1) + "}")
    except Exception:
        return None

    title_m = re.search(r'"headline":"([^"]+)"', body) or re.search(r'"name":"([^"]+)"', body)
    title = title_m.group(1) if title_m else url.rsplit("/", 1)[-1]

    return {
        "url": url,
        "title": title,
        "viewCount": counter.get("viewCount", 0),
        "bookmarkCount": counter.get("bookmarkCount", 0),
        "commentCount": counter.get("commentCount", 0),
        "chatRoomCount": counter.get("chatRoomCount", 0),
    }


def collect_danggn(dry_run: bool = False) -> list[dict]:
    """당근 발행완료 포스트 engagement 수집 → events 반환."""
    print("[당근] 수집 시작 (로그인 불필요)")

    # review_queue에서 당근 발행완료 포스트 URL 수집
    try:
        queue = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [ERROR] review_queue 로드 실패: {e}")
        return []

    posts = [
        it for it in queue
        if it.get("status") == "발행완료"
        and "당근" in it.get("channel", "")
        and it.get("post_url", "").startswith("http")
    ]
    if not posts:
        print("  [INFO] 당근 발행완료 포스트 없음")
        return []

    # 이전 스냅샷 로드
    prev_snap = _load_snap(DANGGN_SNAP_PATH)
    prev_posts = {p["url"]: p for p in prev_snap.get("posts", []) if "url" in p}

    new_snap_posts = []
    events = []
    ts = now_kst()

    for item in posts:
        url = item["post_url"]
        print(f"  → {item.get('title', '')[:30]} | {url}")
        current = _parse_danggn_post(url)
        if current is None:
            print(f"    [SKIP] 파싱 실패")
            continue

        prev = prev_posts.get(url, {})
        is_new = url not in prev_posts

        d_views = current["viewCount"] - prev.get("viewCount", 0)
        d_bookmark = current["bookmarkCount"] - prev.get("bookmarkCount", 0)
        d_comment = current["commentCount"] - prev.get("commentCount", 0)

        print(
            f"    viewCount={current['viewCount']} (+{d_views}) "
            f"bookmark={current['bookmarkCount']} (+{d_bookmark}) "
            f"comment={current['commentCount']} (+{d_comment})"
        )

        # 변동 있거나 신규인 경우만 event 생성
        if is_new or d_views != 0 or d_bookmark != 0 or d_comment != 0:
            events.append({
                "channel": "당근",
                "title": current["title"][:40],
                "url": url,
                "collected_at": ts,
                "isNew": is_new,
                "dViews": d_views if d_views > 0 else 0,
                "dInterest": d_bookmark if d_bookmark > 0 else 0,
                "dComments": d_comment if d_comment > 0 else 0,
                "totalViews": current["viewCount"],
                "totalBookmarks": current["bookmarkCount"],
            })

        new_snap_posts.append({
            "url": url,
            "title": current["title"],
            "viewCount": current["viewCount"],
            "bookmarkCount": current["bookmarkCount"],
            "commentCount": current["commentCount"],
            "collected_at": ts,
        })

    # 스냅샷 저장
    if not dry_run:
        new_snap = {
            "channel": "당근",
            "collected_at": ts,
            "count": len(new_snap_posts),
            "posts": new_snap_posts,
        }
        _save_snap(DANGGN_SNAP_PATH, new_snap)
        print(f"  [저장] danggn_snapshot.json ({len(new_snap_posts)}건)")

    print(f"  [완료] 이벤트 {len(events)}건")
    return events


# ════════════════════════════════════════════════════
# 채널 2: 네이버 블로그 (로그인 불필요 — RSS 신규 감지)
# ════════════════════════════════════════════════════
BLOG_RSS_URL = "https://rss.blog.naver.com/wellperion.xml"
BLOG_SNAP_PATH = ENGAGEMENT_DIR / "blog_snapshot.json"

# ── Playwright 프로필 경로 ─────────────────────────────
CAFE_PROFILE = ROOT / "profiles" / "naver-cafe"
KAKAO_PROFILE = ROOT / "profiles" / "kakao-channel"
CAFE_SNAP_PATH = ENGAGEMENT_DIR / "cafe_snapshot.json"
KAKAO_SNAP_PATH = ENGAGEMENT_DIR / "kakao_snapshot.json"

# 카카오 채널 ID
KAKAO_CHANNEL_ID = "_cgxiKj"
KAKAO_POSTS_URL = f"https://business.kakao.com/{KAKAO_CHANNEL_ID}/posts"


def collect_blog(dry_run: bool = False) -> list[dict]:
    """
    RSS feed에서 신규 포스트 감지 → events 반환.
    조회수는 로그인 없이 불가 (iframe 구조) → 신규 발행 감지만.
    """
    print("[블로그] 수집 시작 (RSS, 로그인 불필요 — 조회수 제외)")

    try:
        body = _fetch(BLOG_RSS_URL)
    except Exception as e:
        print(f"  [ERROR] RSS fetch 실패: {e}")
        return []

    raw_items = re.findall(r"<item>(.*?)</item>", body, re.S)
    current_posts = []
    for item in raw_items[:10]:
        title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]>", item)
        link_m = re.search(r"<link>\s*<!\[CDATA\[(.*?)\]\]>", item)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
        if not title_m:
            continue
        link = (link_m.group(1) if link_m else "").strip()
        # 포스트 ID 추출 (URL의 숫자 부분)
        pid_m = re.search(r"/wellperion/(\d+)", link)
        pid = pid_m.group(1) if pid_m else link
        current_posts.append({
            "id": pid,
            "title": title_m.group(1).strip(),
            "link": link,
            "date": (date_m.group(1) if date_m else "").strip(),
        })

    # 이전 스냅샷과 비교
    prev_snap = _load_snap(BLOG_SNAP_PATH)
    prev_ids = {p["id"] for p in prev_snap.get("posts", [])}
    is_first_run = len(prev_ids) == 0  # 초기 실행 — 이벤트 없이 스냅샷만 저장

    ts = now_kst()
    events = []
    new_count = 0

    for post in current_posts:
        if post["id"] not in prev_ids:
            if is_first_run:
                print(f"  [초기화] {post['title'][:40]}")
            else:
                print(f"  🆕 신규: {post['title'][:40]} ({post['date']})")
                events.append({
                    "channel": "블로그",
                    "title": post["title"][:40],
                    "url": post["link"],
                    "collected_at": ts,
                    "isNew": True,
                    "dViews": 0,  # RSS로는 조회수 불가 — 로그인 필요
                    "dInterest": 0,
                    "dComments": 0,
                    "note": "조회수: 로그인 필요 (GM 인터랙티브)",
                })
                new_count += 1
        else:
            print(f"  = 기존: {post['title'][:30]}")

    if is_first_run:
        print(f"  [초기 실행] 스냅샷만 저장 — 다음 실행부터 신규 감지")

    if not dry_run:
        _save_snap(BLOG_SNAP_PATH, {
            "channel": "블로그",
            "collected_at": ts,
            "count": len(current_posts),
            "posts": current_posts,
        })
        print(f"  [저장] blog_snapshot.json ({len(current_posts)}건)")

    print(f"  [완료] 신규 {new_count}건")
    return events


# ════════════════════════════════════════════════════
# 채널 3: 네이버 카페 (Persistent Profile 세션)
# 실측(2026-06-15): iframe#cafe_main → span.count → "조회 N" 형식
# ════════════════════════════════════════════════════
def _import_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        print("[ERROR] playwright 미설치 — 카페/카카오 수집 건너뜀")
        return None


def _parse_view_count(text: str) -> int:
    """'조회 70', '1,234' 등 다양한 형식에서 첫 번째 숫자 추출."""
    m = re.search(r"[\d,]+", text)
    if not m:
        return 0
    return int(m.group(0).replace(",", ""))


async def _collect_cafe_async(dry_run: bool) -> list[dict]:
    async_playwright = _import_playwright()
    if async_playwright is None:
        return []

    try:
        queue = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [ERROR] review_queue 로드 실패: {e}")
        return []

    posts = [
        it for it in queue
        if it.get("status") == "발행완료"
        and "카페" in it.get("channel", "")
        and it.get("post_url", "").startswith("https://cafe.naver.com")
    ]
    if not posts:
        print("  [INFO] 카페 발행완료 post_url 없음")
        return []

    prev_snap = _load_snap(CAFE_SNAP_PATH)
    prev_posts = {p["url"]: p for p in prev_snap.get("posts", []) if "url" in p}

    new_snap_posts = []
    events = []
    ts = now_kst()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(CAFE_PROFILE),
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        for item in posts:
            url = item["post_url"]
            title = item.get("title", url)
            print(f"  → {title[:30]} | {url}")

            view_count = 0
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)

                iframe_handle = await page.query_selector("iframe#cafe_main")
                if iframe_handle:
                    frame = await iframe_handle.content_frame()
                    await frame.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(1500)
                    # 실측 셀렉터: span.count → "조회 N"
                    el = await frame.query_selector("span.count")
                    if el:
                        txt = (await el.inner_text()).strip()
                        view_count = _parse_view_count(txt)
                        print(f"    span.count={txt!r} → viewCount={view_count}")
                    else:
                        # fallback: HTML regex
                        html = await frame.content()
                        m = re.search(r'조회\s*([\d,]+)', html)
                        if m:
                            view_count = int(m.group(1).replace(",", ""))
                            print(f"    [regex fallback] viewCount={view_count}")
                        else:
                            print("    [WARN] 조회수 요소 미발견")
                else:
                    print("    [WARN] iframe#cafe_main 없음")
            except Exception as e:
                print(f"    [ERROR] {e}")

            prev = prev_posts.get(url, {})
            is_new = url not in prev_posts
            d_views = view_count - prev.get("viewCount", 0)

            if is_new or d_views != 0:
                events.append({
                    "channel": "카페",
                    "title": title[:40],
                    "url": url,
                    "collected_at": ts,
                    "isNew": is_new,
                    "dViews": max(d_views, 0),
                    "dInterest": 0,
                    "dComments": 0,
                    "totalViews": view_count,
                })

            new_snap_posts.append({
                "url": url,
                "title": title,
                "viewCount": view_count,
                "collected_at": ts,
            })

        await context.close()

    if not dry_run:
        _save_snap(CAFE_SNAP_PATH, {
            "channel": "카페",
            "collected_at": ts,
            "count": len(new_snap_posts),
            "posts": new_snap_posts,
        })
        print(f"  [저장] cafe_snapshot.json ({len(new_snap_posts)}건)")

    print(f"  [완료] 이벤트 {len(events)}건")
    return events


def collect_cafe(dry_run: bool = False) -> list[dict]:
    """카페 발행완료 포스트 조회수 수집 (headful Playwright, GM 데스크톱)."""
    print("[카페] 수집 시작 (Persistent Profile 세션)")
    return asyncio.run(_collect_cafe_async(dry_run))


# ════════════════════════════════════════════════════
# 채널 4: 카카오 채널 (Persistent Profile 세션)
# 실측(2026-06-15): business.kakao.com posts → 글 페이지 →
#   span.icon.ico_like + span.num_g (좋아요), span.icon.ico_cmt + span.num_g (댓글)
# ════════════════════════════════════════════════════
async def _collect_kakao_async(dry_run: bool) -> list[dict]:
    async_playwright = _import_playwright()
    if async_playwright is None:
        return []

    # review_queue에서 카카오 발행완료 항목 — post_id → title 매핑
    kakao_title_map: dict[str, str] = {}
    try:
        queue = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
        for it in queue:
            if it.get("status") == "발행완료" and "카카오" in it.get("channel", ""):
                url = it.get("post_url", "")
                if url:
                    pid = url.rsplit("/", 1)[-1]
                    kakao_title_map[pid] = it.get("title", "")
    except Exception:
        pass

    prev_snap = _load_snap(KAKAO_SNAP_PATH)
    prev_posts = {p["url"]: p for p in prev_snap.get("posts", []) if "url" in p}

    new_snap_posts = []
    events = []
    ts = now_kst()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(KAKAO_PROFILE),
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # 소식 목록에서 글 링크 수집
        print(f"  → 소식 목록: {KAKAO_POSTS_URL}")
        try:
            await page.goto(KAKAO_POSTS_URL, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(4000)

            current_url = page.url
            if any(sig in current_url for sig in ("accounts.kakao.com", "/login", "logon")):
                print(f"  [BLOCKED] 세션 만료 — 로그인 리다이렉트: {current_url}")
                await context.close()
                return []

            post_links = await page.evaluate("""() => {
                return [...document.querySelectorAll('a[href]')]
                    .map(a => a.href)
                    .filter(h => h.includes('/posts/') && /\\/posts\\/\\d+$/.test(h))
                    .slice(0, 10);
            }""")
            print(f"  [글링크] {len(post_links)}건 발견")
        except Exception as e:
            print(f"  [ERROR] 목록 로드 실패: {e}")
            await context.close()
            return []

        # 페이지에서 og:title / title / heading을 한 번에 뽑는 JS 헬퍼
        _KAKAO_TITLE_JS = """() => {
            // 쓰레기 값 필터: 사이트 공통명·네비 메뉴만 있으면 버림
            const JUNK = ['전체 메뉴', '카카오', '카카오 채널', '카카오비즈니스', '카카오톡 채널'];
            function isJunk(s) {
                if (!s || s.trim() === '') return true;
                const t = s.trim();
                return JUNK.some(j => t === j || t.startsWith(j + ' ') || t.endsWith(' ' + j));
            }
            // ① og:title
            const og = document.querySelector('meta[property="og:title"]');
            if (og && !isJunk(og.getAttribute('content'))) return og.getAttribute('content').trim();
            // ② <title> 태그
            const tt = document.title;
            if (!isJunk(tt)) return tt.trim();
            // ③ 첫 heading
            for (const sel of ['h1', 'h2', 'h3']) {
                const el = document.querySelector(sel);
                if (el && !isJunk(el.innerText)) return el.innerText.trim();
            }
            return null;
        }"""

        # 페이지에서 좋아요·댓글·조회수를 폭넓게 긁는 JS 헬퍼
        _KAKAO_METRICS_JS = """() => {
            const LIKE_KW  = ['좋아요', '추천', '공감', 'like', 'ico_like'];
            const CMT_KW   = ['댓글', 'comment', 'ico_cmt', 'reply'];
            const VIEW_KW  = ['조회', '뷰', 'view', 'read', 'ico_view'];

            function parseNum(s) {
                if (!s) return 0;
                const m = s.replace(/,/g, '').match(/\\d+/);
                return m ? parseInt(m[0], 10) : 0;
            }
            function hasKw(el, kws) {
                const combined = [
                    el.className || '',
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('title') || '',
                    el.innerText || ''
                ].join(' ').toLowerCase();
                return kws.some(k => combined.includes(k.toLowerCase()));
            }

            let likes = 0, comments = 0, views = 0;

            // 전략 A: span.num_g 옆 형제·부모에서 키워드 매핑
            document.querySelectorAll(
                'span.num_g, [class*="num_"], [class*="_num"], [class*="count_"], [class*="_count"]'
            ).forEach(numEl => {
                const val = parseNum(numEl.innerText);
                if (!val) return;
                // 부모 또는 형제에서 키워드 확인
                const ctx = numEl.parentElement;
                if (!ctx) return;
                if (!likes  && hasKw(ctx, LIKE_KW))  likes    = val;
                if (!comments && hasKw(ctx, CMT_KW))  comments = val;
                if (!views  && hasKw(ctx, VIEW_KW))  views    = val;
            });

            // 전략 B: aria-label / data-* 속성 기반 스캔
            if (!likes || !comments || !views) {
                document.querySelectorAll('[aria-label], [data-count], [data-like], [data-comment]').forEach(el => {
                    const val = parseNum(el.getAttribute('aria-label') || el.getAttribute('data-count') || el.innerText);
                    if (!val) return;
                    if (!likes    && hasKw(el, LIKE_KW))  likes    = val;
                    if (!comments && hasKw(el, CMT_KW))   comments = val;
                    if (!views    && hasKw(el, VIEW_KW))  views    = val;
                });
            }

            // 전략 C: 숫자 직전/직후 텍스트 노드 기반 — 텍스트 전체 스캔
            if (!likes || !comments || !views) {
                document.querySelectorAll('span, em, strong, div').forEach(el => {
                    if (el.children.length > 3) return;  // 컨테이너 제외
                    const txt = (el.innerText || '').trim();
                    if (!/^[\\d,]+$/.test(txt)) return;  // 순수 숫자만
                    const val = parseNum(txt);
                    if (!val) return;
                    const sibling = el.previousElementSibling || el.parentElement;
                    if (sibling) {
                        if (!likes    && hasKw(sibling, LIKE_KW))  likes    = val;
                        if (!comments && hasKw(sibling, CMT_KW))   comments = val;
                        if (!views    && hasKw(sibling, VIEW_KW))  views    = val;
                    }
                });
            }

            return {likes, comments, views};
        }"""

        for post_url in post_links:
            like_count = 0
            comment_count = 0
            view_count = 0
            pid = post_url.rsplit("/", 1)[-1]

            try:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2500)

                # ─ 제목 추출 (우선순위 5단계) ─
                # ① review_queue 매핑
                title = kakao_title_map.get(pid)
                if not title:
                    # ②③④ og:title / <title> / heading을 JS로 한 번에 뽑기
                    title = await page.evaluate(_KAKAO_TITLE_JS)
                # ⑤ 최후 폴백
                if not title:
                    title = f"카카오소식_{pid}"

                # ─ 좋아요·댓글·조회수 수집 (다중 폴백) ─
                metrics = await page.evaluate(_KAKAO_METRICS_JS)
                like_count    = metrics.get("likes", 0)
                comment_count = metrics.get("comments", 0)
                view_count    = metrics.get("views", 0)

                # 전부 0이면 DOM 구조 변경 경고
                if like_count == 0 and comment_count == 0 and view_count == 0:
                    print(f"  [카카오 DEBUG] 수치 미감지 — 페이지 구조 확인 필요: {post_url}")

                print(f"    {title[:30]} → 좋아요={like_count} 댓글={comment_count} 조회={view_count}")

            except Exception as e:
                title = kakao_title_map.get(pid, f"카카오소식_{pid}")
                print(f"    [ERROR] {post_url}: {e}")

            prev = prev_posts.get(post_url, {})
            is_new = post_url not in prev_posts
            d_like    = like_count    - prev.get("likeCount", 0)
            d_comment = comment_count - prev.get("commentCount", 0)
            d_view    = view_count    - prev.get("viewCount", 0)

            if is_new or d_like != 0 or d_comment != 0 or d_view != 0:
                events.append({
                    "channel": "카카오",
                    "title": title,
                    "url": post_url,
                    "collected_at": ts,
                    "isNew": is_new,
                    "dViews": max(d_view, 0),
                    "dInterest": max(d_like, 0),
                    "dComments": max(d_comment, 0),
                    "totalViews": view_count,
                    "totalLikes": like_count,
                    "totalComments": comment_count,
                })

            new_snap_posts.append({
                "url": post_url,
                "title": title,
                "likeCount": like_count,
                "commentCount": comment_count,
                "viewCount": view_count,
                "collected_at": ts,
            })

        await context.close()

    if not dry_run:
        _save_snap(KAKAO_SNAP_PATH, {
            "channel": "카카오",
            "collected_at": ts,
            "count": len(new_snap_posts),
            "posts": new_snap_posts,
        })
        print(f"  [저장] kakao_snapshot.json ({len(new_snap_posts)}건)")

    print(f"  [완료] 이벤트 {len(events)}건")
    return events


def collect_kakao(dry_run: bool = False) -> list[dict]:
    """카카오 채널 소식 좋아요·댓글 수집 (headful Playwright, GM 데스크톱)."""
    print("[카카오] 수집 시작 (Persistent Profile 세션)")
    return asyncio.run(_collect_kakao_async(dry_run))


# ════════════════════════════════════════════════════
# 채널 5: 로그인 필요 플래그 (인스타그램만)
# ════════════════════════════════════════════════════
def flag_login_required() -> list[dict]:
    """로그인 필요 채널은 플래그 이벤트로 기록."""
    flags = [
        {"channel": "인스타그램", "reason": "Meta Graph API 토큰 필요 (FACEBOOK_ENABLED=OFF 정책 — GM 별도 결재)"},
    ]
    for f in flags:
        print(f"  [제외] {f['channel']}: {f['reason']}")
    return []  # 이벤트 생성 없음 — 플래그는 stdout만


# ════════════════════════════════════════════════════
# 메인 — 수집·피드 갱신
# ════════════════════════════════════════════════════
def main() -> int:
    parser = argparse.ArgumentParser(description="웰페리온 채널 engagement 수집기")
    parser.add_argument(
        "--channel",
        choices=["danggn", "blog", "cafe", "kakao", "all", "desktop"],
        default="all",
    )
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 없이 결과만 출력")
    args = parser.parse_args()

    print(f"=== 채널 engagement 수집 [{now_kst()}] ===")
    if args.dry_run:
        print("[DRY-RUN] 파일 저장 없음")

    events: list[dict] = []

    if args.channel in ("danggn", "all"):
        events.extend(collect_danggn(dry_run=args.dry_run))

    if args.channel in ("blog", "all"):
        events.extend(collect_blog(dry_run=args.dry_run))

    if args.channel in ("cafe", "desktop"):
        events.extend(collect_cafe(dry_run=args.dry_run))

    if args.channel in ("kakao", "desktop"):
        events.extend(collect_kakao(dry_run=args.dry_run))

    if args.channel == "all":
        print("\n[로그인 필요 채널 — FACEBOOK_ENABLED=OFF]")
        flag_login_required()
        print("\n[카페·카카오] headful 세션 필요 — --channel cafe / --channel kakao / --channel desktop 으로 실행")

    if args.channel == "desktop":
        print("\n[desktop 모드] danggn+blog+cafe+kakao 전체 수집 완료 (GM 데스크톱 세션 활성 전제)")

    # engagement_feed.json 갱신
    if not args.dry_run:
        feed = _load_feed()
        # 새 이벤트를 앞에 prepend, 최대 50건 유지
        feed["events"] = (events + feed.get("events", []))[:50]
        feed["updated_at"] = now_kst()
        feed["note"] = (
            "engagement_collector.py 자동 생성 — "
            "당근:공개HTML파싱 / 블로그:RSS신규감지 / "
            "카페:Playwright iframe#cafe_main span.count / "
            "카카오:Playwright 다중폴백(num_g/aria-label/텍스트노드) 좋아요·댓글·조회수"
        )
        _save_feed(feed)
        print(f"\n[저장] engagement_feed.json — 총 {len(feed['events'])}건")
    else:
        print(f"\n[DRY-RUN] 생성될 이벤트 {len(events)}건:")
        print(json.dumps(events, ensure_ascii=False, indent=2))

    print("=== 완료 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
