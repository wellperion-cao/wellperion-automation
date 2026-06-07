# scripts/engagement_collector.py
# v1.0 — 채널별 engagement 수집기
#
# 로그인 없이 수집 가능한 채널:
#   당근(danggn) — 공개 비즈포스트 HTML에서 viewCount/bookmarkCount/commentCount 파싱
#   블로그(blog)  — RSS feed에서 신규 글 감지 (조회수는 로그인 필요 → 플래그)
#
# 로그인 필요 채널 (GM 인터랙티브 세션 필요):
#   인스타그램 — Meta Graph API 토큰 필요 (FACEBOOK_ENABLED=OFF 정책)
#   카페        — 로그인 필요 (noindex 리다이렉트 확인)
#   카카오      — 파트너센터 로그인 필요
#
# 사용법:
#   python scripts/engagement_collector.py            # 전체 수집
#   python scripts/engagement_collector.py --channel danggn
#   python scripts/engagement_collector.py --channel blog
#   python scripts/engagement_collector.py --dry-run  # 파일 저장 없이 결과만 출력
#
# 출력: 3. 웰페리온 가이드/cmo/funnel/engagement/engagement_feed.json (대시보드 소비)
#       3. 웰페리온 가이드/cmo/funnel/engagement/danggn_snapshot.json (당근 스냅샷)

import argparse
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
# 채널 3~5: 로그인 필요 플래그
# ════════════════════════════════════════════════════
def flag_login_required() -> list[dict]:
    """로그인 필요 채널은 플래그 이벤트로 기록."""
    flags = [
        {"channel": "인스타그램", "reason": "Meta Graph API 토큰 필요 (FACEBOOK_ENABLED=OFF 정책 — GM 별도 결재)"},
        {"channel": "카페", "reason": "네이버 카페 로그인 필요 (noindex 리다이렉트 확인됨) — GM cao SSO 인터랙티브"},
        {"channel": "카카오", "reason": "파트너센터 로그인 필요 — GM cao SSO 인터랙티브"},
    ]
    for f in flags:
        print(f"  ⚠️  {f['channel']}: {f['reason']}")
    return []  # 이벤트 생성 없음 — 플래그는 stdout만


# ════════════════════════════════════════════════════
# 메인 — 수집·피드 갱신
# ════════════════════════════════════════════════════
def main() -> int:
    parser = argparse.ArgumentParser(description="웰페리온 채널 engagement 수집기")
    parser.add_argument("--channel", choices=["danggn", "blog", "all"], default="all")
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

    if args.channel == "all":
        print("\n[로그인 필요 채널 — GM 인터랙티브 필요]")
        flag_login_required()

    # engagement_feed.json 갱신
    if not args.dry_run:
        feed = _load_feed()
        # 새 이벤트를 앞에 prepend, 최대 50건 유지
        feed["events"] = (events + feed.get("events", []))[:50]
        feed["updated_at"] = now_kst()
        feed["note"] = "engagement_collector.py 자동 생성 — 당근:공개HTML파싱 / 블로그:RSS신규감지"
        _save_feed(feed)
        print(f"\n[저장] engagement_feed.json — 총 {len(feed['events'])}건")
    else:
        print(f"\n[DRY-RUN] 생성될 이벤트 {len(events)}건:")
        print(json.dumps(events, ensure_ascii=False, indent=2))

    print("=== 완료 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
