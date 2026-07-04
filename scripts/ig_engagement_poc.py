# scripts/ig_engagement_poc.py
# PoC — @namuk.wellperion 최근 게시물 반응 수집 (댓글·좋아요·저장·팔로워)
# 기존 Playwright Persistent Context 세션 재활용 (신규 로그인 없음)
# 실행: python scripts\ig_engagement_poc.py

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

def _harden_console():
    for s in ("stdout", "stderr"):
        st = getattr(sys, s, None)
        if st and hasattr(st, "reconfigure"):
            try:
                st.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

_harden_console()

PROFILE_DIR = Path(r"C:\Users\jjky0\welperion-automation\profiles\instagram\namuk.wellperion")
EVIDENCE_DIR = Path(r"C:\Users\jjky0\welperion-automation\scripts\poc-evidence")
ACCOUNT = "namuk.wellperion"
IG_PROFILE_URL = f"https://www.instagram.com/{ACCOUNT}/"

FIXED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def collect_engagement():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = {
        "timestamp": ts,
        "account": ACCOUNT,
        "status": None,
        "blocked_reason": None,
        "latest_post_url": None,
        "pinned_posts_skipped": None,
        "metrics": {},
        "follower_count": None,
    }

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            user_agent=FIXED_UA,
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # 1단계: 프로필 페이지 접근
        print(f"[1] 프로필 페이지 이동: {IG_PROFILE_URL}")
        await page.goto(IG_PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 로그인 여부 확인
        login_check = await page.query_selector('input[name="username"]')
        if login_check:
            result["status"] = "BLOCKED"
            result["blocked_reason"] = "세션 만료 — 로그인 화면 표시됨. setup 모드로 재로그인 필요."
            await page.screenshot(path=str(EVIDENCE_DIR / f"ig_poc_{ts}_login_wall.png"))
            print(f"[BLOCKED] {result['blocked_reason']}")
            await ctx.close()
            return result

        # 세션 유효 확인 — 프로필 로드됐는지
        await page.screenshot(path=str(EVIDENCE_DIR / f"ig_poc_{ts}_profile.png"))
        print("[2] 프로필 페이지 스크린샷 저장")

        # 2단계: 팔로워 수 수집
        try:
            follower_el = await page.query_selector('a[href*="followers"] span, a[href$="/followers/"] span[title]')
            if not follower_el:
                # 대안: meta description 또는 텍스트 패턴
                follower_el = await page.query_selector('span[title]')
            if follower_el:
                follower_text = await follower_el.get_attribute("title") or await follower_el.inner_text()
                result["follower_count"] = follower_text.strip()
                print(f"[2] 팔로워: {result['follower_count']}")
            else:
                # JS evaluate로 시도
                follower_count = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        if (a.href && a.href.includes('followers')) {
                            const spans = a.querySelectorAll('span');
                            for (const s of spans) {
                                if (s.title) return s.title;
                                if (s.innerText && /[0-9]/.test(s.innerText)) return s.innerText;
                            }
                        }
                    }
                    return null;
                }""")
                result["follower_count"] = follower_count
                print(f"[2] 팔로워(JS): {follower_count}")
        except Exception as e:
            print(f"[2] 팔로워 수집 실패: {e}")

        # 3단계: 최신 게시물 링크 추출 (핀 게시물 skip)
        # IG 프로필 그리드에서 고정 게시물은 각 앵커 내부에 svg[aria-label="고정 게시물"]
        # (영문 로케일 "Pinned post")가 렌더됨. 실측 확인(2026-07-04): namuk.wellperion
        # 상위 3개 전부 이 마커 보유(6/17 수영장 사진 핀 3개), 4번째부터 실제 최신
        # 게시물(svg[aria-label="슬라이드"] = 여러 장 아이콘, 핀 아님)이 시작됨.
        print("[3] 최신 게시물 링크 추출 (핀 게시물 skip)")
        try:
            posts_info = await page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll('a[href*="/p/"]')).slice(0, 8);
                return anchors.map(a => {
                    const svgLabels = Array.from(a.querySelectorAll('svg'))
                        .map(s => s.getAttribute('aria-label') || '');
                    const isPinned = svgLabels.some(
                        l => l.includes('고정') || l.toLowerCase().includes('pinned')
                    );
                    return { href: a.getAttribute('href'), isPinned };
                });
            }""")

            if not posts_info:
                result["status"] = "BLOCKED"
                result["blocked_reason"] = "게시물 링크 없음 — 로그인 게이트 또는 DOM 변경"
                await page.screenshot(path=str(EVIDENCE_DIR / f"ig_poc_{ts}_no_posts.png"))
                await ctx.close()
                return result

            pinned_count = sum(1 for p in posts_info if p["isPinned"])
            latest_post = next((p for p in posts_info if not p["isPinned"]), None)
            if not latest_post:
                result["status"] = "BLOCKED"
                result["blocked_reason"] = "핀 게시물 제외 후 실제 최신 게시물 없음 — 그리드 상위가 전부 핀"
                await ctx.close()
                return result

            latest_href = latest_post["href"]
            latest_url = f"https://www.instagram.com{latest_href}"
            result["latest_post_url"] = latest_url
            result["pinned_posts_skipped"] = pinned_count
            print(f"[3] 핀 게시물 {pinned_count}개 skip / 최신 게시물: {latest_url}")
        except Exception as e:
            result["status"] = "BLOCKED"
            result["blocked_reason"] = f"게시물 링크 추출 예외: {e}"
            await ctx.close()
            return result

        # 4단계: 게시물 페이지 이동 → 반응 수집
        print(f"[4] 게시물 페이지 이동")
        await page.goto(latest_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(EVIDENCE_DIR / f"ig_poc_{ts}_post.png"))

        # DOM 덤프: 수치 포함 텍스트 전체 수집 → 실측 기반 파싱
        try:
            body_text = await page.evaluate("() => document.body.innerText")
        except Exception:
            body_text = ""

        # 좋아요 수 — IG DOM 실측 기반 3가지 패턴
        # 패턴1: "좋아요 N개" (숫자 노출 시)
        # 패턴2: "N명이 좋아합니다" / "N likes"
        # 패턴3: "X님 외 N명이 좋아합니다" (이름+숫자)
        # 패턴4: "여러 명이 좋아합니다" (소수 — 숫자 미노출, IG 정책)
        import re
        likes_val = None
        m = re.search(r'좋아요\s*([\d,만]+)개', body_text)
        if m:
            likes_val = m.group(1)
        if not likes_val:
            m = re.search(r'외\s*([\d,]+)명이\s*좋아합니다', body_text)
            if m:
                likes_val = m.group(1) + "+"
        if not likes_val:
            m = re.search(r'([\d,]+)명이\s*좋아합니다', body_text)
            if m:
                likes_val = m.group(1)
        if not likes_val:
            m = re.search(r'([\d,]+)\s*like', body_text, re.IGNORECASE)
            if m:
                likes_val = m.group(1)
        # 패턴4: 소수 좋아요 — "여러 명이 좋아합니다" or "X님이 좋아합니다"
        if not likes_val:
            m = re.search(r'(.+?(?:님|님 여러 명)이\s*좋아합니다)', body_text)
            if m:
                likes_val = f"소수({m.group(1).strip()})"
        result["metrics"]["likes"] = likes_val
        print(f"[4] 좋아요: {likes_val}")

        # 댓글 수 — DOM 실측: "아직 댓글이 없습니다" = 0, 숫자 패턴, DOM 카운트
        comments_val = None
        if "아직 댓글이 없습니다" in body_text:
            comments_val = "0"
        if not comments_val:
            m2 = re.search(r'댓글\s*([\d,]+)개', body_text)
            if m2:
                comments_val = m2.group(1)
        if not comments_val:
            m2 = re.search(r'([\d,]+)\s*comment', body_text, re.IGNORECASE)
            if m2:
                comments_val = m2.group(1)
        result["metrics"]["comments"] = comments_val
        print(f"[4] 댓글: {comments_val}")

        # 저장 수 (비공개 지표 — 수집 불가 여부 명시)
        result["metrics"]["saves"] = "수집불가(IG 비공개 지표 — 공개 DOM에 미노출)"

        # 디버그: 페이지 텍스트 일부 저장
        debug_path = EVIDENCE_DIR / f"ig_poc_{ts}_body_text.txt"
        debug_path.write_text(body_text[:3000], encoding="utf-8")

        result["status"] = "OK"
        await ctx.close()

    return result


async def main():
    print("=== IG 반응 수집 PoC 시작 ===")
    result = await collect_engagement()

    print("\n=== 결과 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # JSON 저장
    out_path = Path(r"C:\Users\jjky0\welperion-automation\scripts\poc-evidence") / f"ig_engagement_poc_{result['timestamp']}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")

    if result["status"] == "OK":
        print(f"\nDONE: 수집 성공 | 핀skip={result['pinned_posts_skipped']} | 최신={result['latest_post_url']} | 팔로워={result['follower_count']} | 좋아요={result['metrics'].get('likes')} | 댓글={result['metrics'].get('comments')} | 저장=비공개지표")
    else:
        print(f"\nBLOCKED: {result['blocked_reason']}")


if __name__ == "__main__":
    asyncio.run(main())
