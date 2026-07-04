# scripts/ig_engagement_poc.py
# PoC — @namuk.wellperion 최근 게시물 반응 수집 (댓글·좋아요·저장·팔로워)
# 기존 Playwright Persistent Context 세션 재활용 (신규 로그인 없음)
# 실행: python scripts\ig_engagement_poc.py

import asyncio
import json
import re
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

LEDGER_PATH = Path(r"C:\Users\jjky0\welperion-automation\status\ig_engagement_ledger.json")
REVIEW_QUEUE_PATH = Path(r"C:\Users\jjky0\welperion-automation\3. 웰페리온 가이드\cmo\review\review_queue.json")

VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm")


def _extract_shortcode(post_url):
    """IG post_url 두 형태(도메인 직후 /p/.. 또는 계정경유 /account/p/..) 모두에서
    고유 shortcode만 뽑아 episode_key로 정규화. 매칭 실패 시 None."""
    if not post_url:
        return None
    m = re.search(r"/p/([^/?]+)", post_url)
    return m.group(1) if m else None


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _detect_format(entry):
    """review_queue 매칭 항목의 channel 텍스트·folder 내 실제 파일 확장자로 포맷 판별.
    지금은 전부 carousel(영상편 없음) — 영상편 등장 시 이 로직이 자동으로 reel 잡아냄."""
    channel = (entry.get("channel") or "") if entry else ""
    if "릴스" in channel or "reel" in channel.lower():
        return "reel"
    folder = entry.get("folder") if entry else None
    if folder:
        folder_path = Path(r"C:\Users\jjky0\welperion-automation") / folder
        try:
            if folder_path.exists():
                for f in folder_path.rglob("*"):
                    if f.suffix.lower() in VIDEO_EXTS:
                        return "reel"
        except Exception:
            pass
    return "carousel"


def _match_review_queue_entry(shortcode):
    """namuk.wellperion 계정 발행 이력에서 post_url shortcode로 편(제목·포맷) 매칭."""
    if not shortcode:
        return None
    queue = _load_json(REVIEW_QUEUE_PATH, [])
    if not isinstance(queue, list):
        return None
    for entry in queue:
        if entry.get("account") != ACCOUNT:
            continue
        entry_code = _extract_shortcode(entry.get("post_url"))
        if entry_code and entry_code == shortcode:
            return entry
    return None


def update_ledger(result):
    """수집 결과를 status/ig_engagement_ledger.json 누적 원장에 반영.
    (a) follower_series: 날짜별 팔로워 — 같은 날 재실행 시 갱신(멱등, 중복행 없음).
    (b) episode_snapshots: 편별 반응 누적 스냅샷 — 같은 날 재실행 시 그날 스냅샷 갱신(멱등).
    발행·게시물 변경 없음 — 이 파일에만 읽기전용 수집치를 append/갱신."""
    ledger = _load_json(LEDGER_PATH, {"follower_series": [], "episode_snapshots": []})
    ledger.setdefault("follower_series", [])
    ledger.setdefault("episode_snapshots", [])

    today = datetime.now().strftime("%Y-%m-%d")

    # (a) follower_series — 날짜별 upsert
    follower_count = result.get("follower_count")
    if follower_count is not None:
        existing = next((f for f in ledger["follower_series"] if f.get("date") == today), None)
        if existing:
            existing["follower_count"] = follower_count
        else:
            ledger["follower_series"].append({"date": today, "follower_count": follower_count})

    # (b) episode_snapshots — 최신 게시물 1건 반영 (post_url 있을 때만)
    post_url = result.get("latest_post_url")
    shortcode = _extract_shortcode(post_url)
    if shortcode:
        episode = next(
            (e for e in ledger["episode_snapshots"] if e.get("episode_key") == shortcode), None
        )
        matched = _match_review_queue_entry(shortcode)
        title = matched.get("title") if matched else "unmapped"
        fmt = _detect_format(matched) if matched else "unmapped"

        if not episode:
            episode = {
                "episode_key": shortcode,
                "post_url": post_url,
                "title": title,
                "format": fmt,
                "first_seen": today,
                "snapshots": [],
            }
            ledger["episode_snapshots"].append(episode)
        else:
            # 매핑이 나중에 성공하면(예: review_queue 갱신 후) title/format 갱신
            if title != "unmapped":
                episode["title"] = title
            if fmt != "unmapped":
                episode["format"] = fmt

        metrics = result.get("metrics", {}) or {}
        likes = metrics.get("likes")
        comments = metrics.get("comments")
        saves_note = metrics.get("saves")

        snapshot = {
            "date": today,
            "comments": comments,
            "likes": likes,
            "views": None,
            "_note": "views/좋아요 다수 케이스는 IG 비공개 지표라 자동 수집 불가 — null 유지(지어내지 않음)",
        }
        if saves_note:
            snapshot["_saves_note"] = saves_note

        existing_snap = next((s for s in episode["snapshots"] if s.get("date") == today), None)
        if existing_snap:
            existing_snap.update(snapshot)
        else:
            episode["snapshots"].append(snapshot)

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    return ledger

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

    # 누적 원장 반영 (follower_series + episode_snapshots) — 기존 개별 JSON 저장과 별개, 가산만
    try:
        update_ledger(result)
        print(f"원장 갱신: {LEDGER_PATH}")
    except Exception as e:
        print(f"원장 갱신 실패(비치명적, 개별 JSON은 정상 저장됨): {e}")

    if result["status"] == "OK":
        print(f"\nDONE: 수집 성공 | 핀skip={result['pinned_posts_skipped']} | 최신={result['latest_post_url']} | 팔로워={result['follower_count']} | 좋아요={result['metrics'].get('likes')} | 댓글={result['metrics'].get('comments')} | 저장=비공개지표")
    else:
        print(f"\nBLOCKED: {result['blocked_reason']}")


if __name__ == "__main__":
    asyncio.run(main())
