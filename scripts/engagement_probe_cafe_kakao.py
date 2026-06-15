# scripts/engagement_probe_cafe_kakao.py
# STEP 1 PROBE — 카페/카카오 조회수 DOM 실측
#
# 목적: 기존 발행 세션(profiles/naver-cafe, profiles/kakao-channel)으로
#       조회수·좋아요·댓글 DOM 요소가 실제로 보이는지 확인 + 스크린샷 저장.
#       셀렉터 확정 후 engagement_collector.py 수집 함수 추가에 활용.
#
# 사용법:
#   python scripts\engagement_probe_cafe_kakao.py --channel cafe
#   python scripts\engagement_probe_cafe_kakao.py --channel kakao
#   python scripts\engagement_probe_cafe_kakao.py  (기본: 둘 다)
#
# 출력: scripts/poc-evidence/engagement_probe_cafe_*.png
#        scripts/poc-evidence/engagement_probe_kakao_*.png
#        stdout — 발견된 셀렉터 + 수치

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
EVIDENCE_DIR = ROOT / "scripts" / "poc-evidence"
REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"

CAFE_PROFILE = ROOT / "profiles" / "naver-cafe"
KAKAO_PROFILE = ROOT / "profiles" / "kakao-channel"

CAFE_TEST_URL = "https://cafe.naver.com/ichon1dong/362833"

KAKAO_CHANNEL_ID = "_cgxiKj"
KAKAO_POSTS_URL = f"https://business.kakao.com/{KAKAO_CHANNEL_ID}/posts"

KAKAO_POST_LINK_CANDIDATES = [
    "a[href*='/posts/']",
    ".post_item a",
    "article a",
    "[class*='post'] a[href]",
]


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _import_playwright():
    try:
        from playwright.async_api import async_playwright
        return async_playwright
    except ImportError:
        print("[ERROR] playwright 미설치. .venv 활성화 후 'pip install playwright; playwright install chromium' 실행 필요.")
        sys.exit(10)


def _load_cafe_urls() -> list[str]:
    """review_queue에서 카페 발행완료 post_url 수집."""
    try:
        queue = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] review_queue 로드 실패: {e}")
        return [CAFE_TEST_URL]

    urls = [
        it["post_url"]
        for it in queue
        if it.get("status") == "발행완료"
        and "카페" in it.get("channel", "")
        and it.get("post_url", "").startswith("https://cafe.naver.com")
    ]
    return urls if urls else [CAFE_TEST_URL]


# ─────────────────────────────────────────────
# PROBE 1: 네이버 카페
# ─────────────────────────────────────────────
async def probe_cafe() -> dict:
    """
    카페 발행글을 persistent 세션으로 열고 iframe 내부 HTML 전체 덤프
    + 조회수 셀렉터 탐색.
    """
    async_playwright = _import_playwright()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    urls = _load_cafe_urls()
    results = []

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(CAFE_PROFILE),
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        for url in urls[:1]:  # probe: 1건만
            print(f"\n[카페] {url}")
            result = {"url": url, "found": False, "selector": None, "value": None, "note": ""}

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)

                ts = _ts()
                shot_path = EVIDENCE_DIR / f"engagement_probe_cafe_{ts}_outer.png"
                await page.screenshot(path=str(shot_path), full_page=False)
                print(f"  [스크린샷] {shot_path.name}")

                iframe_handle = await page.query_selector("iframe#cafe_main")
                if iframe_handle:
                    frame = await iframe_handle.content_frame()
                    print("  [INFO] iframe#cafe_main 발견")
                    await frame.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(2500)

                    shot_inner = EVIDENCE_DIR / f"engagement_probe_cafe_{ts}_inner.png"
                    await page.screenshot(path=str(shot_inner), full_page=False)
                    print(f"  [스크린샷] {shot_inner.name}")

                    # iframe 내 HTML 덤프 — 조회수 관련 키워드 추출
                    html = await frame.content()
                    # 조회수 관련 키워드 주변 컨텍스트
                    for kw in ["조회", "view", "readCount", "viewCount", "hit", "count"]:
                        matches = [m.start() for m in re.finditer(kw, html, re.IGNORECASE)]
                        if matches:
                            # 첫 번째 매치 주변 120자
                            idx = matches[0]
                            snippet = html[max(0, idx-30):idx+90].replace("\n", " ")
                            print(f"  [HTML키워드:{kw}] ...{snippet}...")
                            break

                    # 조회수 셀렉터 후보 — 숫자만 포함된 요소 찾기
                    view_candidates = [
                        ".count_view",
                        "em.count_view",
                        "#viewCount",
                        ".article_read_count",
                        "[class*='view_count']",
                        "[class*='readCount']",
                        "[class*='hitCount']",
                        ".article_info .num",
                        ".read_count",
                        ".cnt_view",
                        "span.count",
                        ".article_view_count",
                        # 조회 텍스트 인접 숫자
                        ".ArticleViewInfo em",
                        ".ArticleViewInfo strong",
                        ".view_info em",
                        ".view_info strong",
                    ]
                    for sel in view_candidates:
                        el = await frame.query_selector(sel)
                        if el:
                            txt = (await el.inner_text()).strip()
                            print(f"  [CAND] sel={sel!r}  val={txt!r}")
                            # 숫자가 포함된 경우만 HIT
                            if any(c.isdigit() for c in txt):
                                print(f"  [HIT] 조회수 셀렉터={sel!r}  값={txt!r}")
                                result.update({"found": True, "selector": f"iframe#{sel}", "value": txt})
                                break

                    if not result["found"]:
                        # JSON/JS 변수에서 조회수 추출 시도
                        m = re.search(r'readCount["\']?\s*[:=]\s*(\d+)', html, re.IGNORECASE)
                        if not m:
                            m = re.search(r'viewCount["\']?\s*[:=]\s*(\d+)', html, re.IGNORECASE)
                        if not m:
                            m = re.search(r'hitCount["\']?\s*[:=]\s*(\d+)', html, re.IGNORECASE)
                        if m:
                            print(f"  [HIT] HTML regex viewCount={m.group(1)}")
                            result.update({"found": True, "selector": "iframe_html_regex", "value": m.group(1)})
                        else:
                            # 모든 em/strong 요소 나열 (숫자 포함)
                            all_nums = await frame.evaluate("""() => {
                                const els = [...document.querySelectorAll('em, strong, span')];
                                return els
                                    .map(el => ({ tag: el.tagName, cls: el.className, txt: el.innerText.trim() }))
                                    .filter(x => x.txt && /^[\\d,]+$/.test(x.txt) && parseInt(x.txt.replace(/,/g,'')) > 0)
                                    .slice(0, 15);
                            }""")
                            print(f"  [숫자요소목록] {json.dumps(all_nums, ensure_ascii=False)}")
                            result["note"] = f"iframe 조회수 셀렉터 미확정 — 숫자요소: {all_nums[:5]}"

                else:
                    print("  [INFO] iframe#cafe_main 없음 — 외부 직접 탐색")
                    page_html = await page.content()
                    m = re.search(r'viewCount["\']?\s*[:=]\s*(\d+)', page_html, re.IGNORECASE)
                    if m:
                        print(f"  [HIT] 외부 HTML viewCount={m.group(1)}")
                        result.update({"found": True, "selector": "page_html_viewCount", "value": m.group(1)})
                    else:
                        result["note"] = "iframe 없음 + 외부 viewCount 없음"

            except Exception as e:
                result["note"] = f"오류: {e}"
                print(f"  [ERROR] {e}")
                try:
                    await page.screenshot(path=str(EVIDENCE_DIR / f"engagement_probe_cafe_{_ts()}_error.png"))
                except Exception:
                    pass

            results.append(result)

        await context.close()

    return {"channel": "cafe", "results": results}


# ─────────────────────────────────────────────
# PROBE 2: 카카오 채널
# ─────────────────────────────────────────────
async def probe_kakao() -> dict:
    """
    카카오 채널 소식 목록 → 첫 글 → 조회수/좋아요/댓글 DOM 탐색.
    """
    async_playwright = _import_playwright()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    result = {"url": KAKAO_POSTS_URL, "found": False, "selector": None, "value": None, "note": ""}

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(KAKAO_PROFILE),
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            print(f"\n[카카오] {KAKAO_POSTS_URL}")
            await page.goto(KAKAO_POSTS_URL, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(4000)

            ts = _ts()
            shot1 = EVIDENCE_DIR / f"engagement_probe_kakao_{ts}_list.png"
            await page.screenshot(path=str(shot1), full_page=False)
            print(f"  [스크린샷] {shot1.name}")

            current_url = page.url
            print(f"  [URL] {current_url}")

            if any(sig in current_url for sig in ("accounts.kakao.com", "/login", "logon")):
                result["note"] = "세션 만료 — 로그인 페이지로 리다이렉트됨"
                print(f"  [BLOCKED] 세션 만료: {current_url}")
                await context.close()
                return {"channel": "kakao", "results": [result]}

            # HTML 덤프에서 조회수 키워드 탐색
            html = await page.content()
            for kw in ["viewCount", "readCount", "likeCount", "commentCount", "조회", "좋아요"]:
                m = re.search(kw, html, re.IGNORECASE)
                if m:
                    idx = m.start()
                    snippet = html[max(0, idx-20):idx+80].replace("\n", " ")
                    print(f"  [HTML키워드:{kw}] ...{snippet}...")

            # 소식 목록 테이블/카드 — 숫자 포함 요소 나열
            num_els = await page.evaluate("""() => {
                const els = [...document.querySelectorAll('td, [class*="count"], [class*="Count"], [class*="stat"], [class*="Stat"]')];
                return els
                    .map(el => ({ tag: el.tagName, cls: el.className.substring(0,60), txt: el.innerText.trim().substring(0,30) }))
                    .filter(x => x.txt && /\\d/.test(x.txt))
                    .slice(0, 20);
            }""")
            print(f"  [숫자요소목록] {json.dumps(num_els, ensure_ascii=False)}")

            # 소식 목록에서 글 링크 탐색
            post_url = None
            all_links = await page.evaluate("""() => {
                return [...document.querySelectorAll('a[href]')]
                    .map(a => a.href)
                    .filter(h => h.includes('/posts/') || h.includes('/post/'))
                    .slice(0, 5);
            }""")
            print(f"  [글링크후보] {all_links}")

            if all_links:
                post_url = all_links[0]
                print(f"  [글링크] {post_url}")
                await page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                shot2 = EVIDENCE_DIR / f"engagement_probe_kakao_{ts}_post.png"
                await page.screenshot(path=str(shot2), full_page=False)
                print(f"  [스크린샷] {shot2.name}")

                post_html = await page.content()
                for kw in ["viewCount", "likeCount", "commentCount", "조회", "좋아요", "댓글"]:
                    m_kw = re.search(kw, post_html, re.IGNORECASE)
                    if m_kw:
                        idx = m_kw.start()
                        snippet = post_html[max(0, idx-20):idx+80].replace("\n", " ")
                        print(f"  [글HTML:{kw}] ...{snippet}...")

                num_els2 = await page.evaluate("""() => {
                    const els = [...document.querySelectorAll('[class*="count"], [class*="Count"], [class*="like"], [class*="Like"], [class*="stat"], button span')];
                    return els
                        .map(el => ({ cls: el.className.substring(0,60), txt: el.innerText.trim().substring(0,20) }))
                        .filter(x => x.txt && /\\d/.test(x.txt))
                        .slice(0, 15);
                }""")
                print(f"  [글숫자요소] {json.dumps(num_els2, ensure_ascii=False)}")

                if num_els2:
                    first = num_els2[0]
                    result.update({"found": True, "selector": f"[class*='{first['cls'][:20]}']", "value": first["txt"], "url": post_url})
            else:
                result["note"] = "소식 목록 글 링크 미발견"
                print("  [MISS] 글 링크 미발견")

        except Exception as e:
            result["note"] = f"오류: {e}"
            print(f"  [ERROR] {e}")
            try:
                await page.screenshot(path=str(EVIDENCE_DIR / f"engagement_probe_kakao_{_ts()}_error.png"))
            except Exception:
                pass

        await context.close()

    return {"channel": "kakao", "results": [result]}


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="카페/카카오 engagement DOM probe")
    parser.add_argument("--channel", choices=["cafe", "kakao", "all"], default="all")
    args = parser.parse_args()

    probe_results = {}

    if args.channel in ("cafe", "all"):
        probe_results["cafe"] = asyncio.run(probe_cafe())

    if args.channel in ("kakao", "all"):
        probe_results["kakao"] = asyncio.run(probe_kakao())

    print("\n=== PROBE 결과 요약 ===")
    for ch, res in probe_results.items():
        for r in res.get("results", []):
            status = "HIT" if r["found"] else "MISS"
            print(f"  [{ch}] {status} | sel={r['selector']} | val={r['value']} | note={r['note']}")

    print(f"\n[스크린샷] {EVIDENCE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
