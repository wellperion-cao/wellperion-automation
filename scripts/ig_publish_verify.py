#!/usr/bin/env python3
"""IG 발행검증 자동 대조 — 발행검증대기 → 발행완료 자동 도장 (INC-003 자동화).

review_queue.json 의 status='발행검증대기' 인스타그램 항목을, 계정별 IG 세션으로
실제 게시물 캡션을 읽어 M5 캡션과 대조한다.
  · 일치 → '발행완료' 도장 (+ post_url 백필 + 대조 증거 note)
  · 불일치 / 로그인필요 / 게시물 미발견 → 발행검증대기 유지(거짓 도장 금지 = INC-003 안전)

발행≠완료(L04). '됐다'는 상태값이 아니라 실제 게시물로 확인(L03). 이 검증을 자동화해
웰리 수동 대조가 안 돌아 적체되던 마지막 단계를 메운다(GM 2026-06-16 결정: 자동 대조→자동 도장).

사용:
  python scripts/ig_publish_verify.py               # 전체 발행검증대기 IG 대조
  python scripts/ig_publish_verify.py --id <ID>     # 특정 건만
  python scripts/ig_publish_verify.py --dry-run     # 도장 없이 대조 결과만
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
# review_queue.json 쓰기 단일 관문(락 직렬화 · 2026-07-23 · 07-21 AI하루 10편 소실 재발방지)
from review_queue_util import merge_save_review_queue  # noqa: E402

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
PROFILE_BASE = ROOT / "profiles" / "instagram"
DEFAULT_ACCOUNT = "namuk.wellperion"
TARGET_STATUS = "발행검증대기"
# 주소 회수 대상 확대(2026-07-23 배9578): '발행완료'로 이미 굳었지만 url·post_url 이 빈 건도
# 대조 대상에 넣는다. 기존엔 TARGET_STATUS 하드코딩이라 한번 발행완료가 되면 영구히 대상 밖이었고,
# 그래서 인스타 14건이 주소 없이 방치됐다.
# ★재발행 위험 0 근거: 이 스크립트는 페이지 이동(page.goto)과 텍스트 읽기(inner_text·
#   get_attribute)만 한다 — click·fill·set_input_files·업로드 호출이 한 줄도 없다.
#   쓰기는 review_queue.json 의 status·post_url·note 뿐(발행 경로 미접촉).
URL_BACKFILL_STATUS = "발행완료"
LOGIN_SIGNALS = ("instagram.com/accounts/login", "instagram.com/accounts/onetap", "/challenge/")
POST_HREF_RE = re.compile(r"/(p|reel)/([A-Za-z0-9_-]+)/")

KST = timezone(timedelta(hours=9))
# 그리드 썸네일 alt 의 게시일("Photo by ... on June 04, 2026"). ★UTC 기준이라 KST 와 하루
# 어긋날 수 있다(실측: alt 'June 03' = 게시물 time 2026-06-03T23:55Z = KST 06-04 08:55).
# 그래서 alt 날짜는 '후보 좁히기'에만 쓰고, 최종 날짜 근거는 게시물 time[datetime] 로 판정한다.
ALT_DATE_RE = re.compile(r"\bon ([A-Z][a-z]+) (\d{1,2}), (\d{4})")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
# 제목 꼬리의 채널 표식 — 핵심어 추출 전에 떼어낸다.
TITLE_CHANNEL_TAIL_RE = re.compile(
    r"\s*[—\-]?\s*\((?:개인계정|공식|공식계정)\)\s*$|"
    r"\s*[—\-]\s*(?:인스타그램|네이버\s*블로그|네이버\s*카페|카카오|당근)[^—]*$")
TIME_IN_TEXT_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
DATE_IN_TEXT_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
TIME_TOLERANCE_SEC = 900  # ±15분 — 발행 콜백 기록 시각과 실제 게시 시각의 관측 편차(실측 ≤2분)


def _norm(t: str) -> str:
    """공백·개행 정규화(대조 비교용)."""
    return re.sub(r"\s+", " ", (t or "")).strip()


def _squash(t: str) -> str:
    """공백·특수문자·따옴표 제거 + 소문자 — 표기 변형에 강한 대조 키."""
    return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFKC", t or "").lower())


def _alt_date(alt: str) -> str | None:
    m = ALT_DATE_RE.search(alt or "")
    if not m or m.group(1) not in MONTHS:
        return None
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def _item_dates(item: dict) -> set[str]:
    """항목이 주장하는 게시일(KST) 후보 — published_at · id · folder 접두 · note 안 날짜."""
    out: set[str] = set()
    pub = (item.get("published_at") or "").strip()
    if len(pub) >= 10:
        out.add(pub[:10])
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", item.get("id") or "")
    if m:
        out.add(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    m = re.search(r"(?:^|/)(\d{2})(\d{2})(\d{2})_", (item.get("folder") or "") + "_")
    if m:
        out.add(f"20{m.group(1)}-{m.group(2)}-{m.group(3)}")
    for d in DATE_IN_TEXT_RE.finditer(item.get("note") or ""):
        out.add(f"{d.group(1)}-{d.group(2)}-{d.group(3)}")
    return out


def _item_times(item: dict) -> list[datetime]:
    """항목이 주장하는 게시 시각(KST) 후보 — published_at 의 시각 + note 안 HH:MM × 날짜후보."""
    out: list[datetime] = []
    pub = (item.get("published_at") or "").strip()
    if "T" in pub:
        try:
            out.append(datetime.fromisoformat(pub).replace(tzinfo=KST))
        except ValueError:
            pass
    dates = _item_dates(item)
    for tm in TIME_IN_TEXT_RE.finditer(item.get("note") or ""):
        for d in dates:
            try:
                out.append(datetime.fromisoformat(
                    f"{d}T{int(tm.group(1)):02d}:{tm.group(2)}:00").replace(tzinfo=KST))
            except ValueError:
                continue
    return out


def _title_core(item: dict) -> str:
    """제목에서 채널 표식·시리즈 번호를 떼어낸 핵심 구절(대조용).
    'AI #8편 (일요일 특별편) — GM의 일요일(개인계정)' → 'GM의 일요일'.
    '[필라테스편] 민소매가 잘 어울리는 어깨만들기 — 인스타그램(공식)' → '민소매가 잘 어울리는 어깨만들기'
    (앞머리 대괄호는 시리즈 표식이라 실제 게시 캡션엔 안 들어간다 — 떼지 않으면 대조가 통째로 빗나간다)."""
    title = (item.get("title") or "").strip()
    prev = None
    while prev != title:
        prev = title
        title = TITLE_CHANNEL_TAIL_RE.sub("", title).strip()
    title = re.sub(r"^(?:\s*\[[^\]]*\])+\s*", "", title).strip()
    parts = [p.strip() for p in re.split(r"\s+—\s+", title) if p.strip()]
    return parts[-1] if parts else title


def _profile_dir(account: str) -> Path:
    return PROFILE_BASE / (account or DEFAULT_ACCOUNT)


def _match_snippets(caption: str) -> list[str]:
    """M5 캡션에서 대조 스니펫 후보들을 뽑는다(여러 개 — 하나라도 일치하면 매치).
    CTA·해시태그·전화번호 줄 제외. 게시물 캡션 앞부분이 잘리는 경우(og:description)에
    강건하도록 '첫 변별 줄'과 '가장 긴 줄'을 모두 후보로 쓴다."""
    lines = [ln.strip() for ln in (caption or "").splitlines() if ln.strip()]
    cand = []
    for ln in lines:
        if ln.startswith("#") or "wellperion.com" in ln or ln.startswith("문의"):
            continue
        if re.match(r"^[0-9\-\s]+$", ln):  # 전화번호 등
            continue
        if len(_norm(ln)) < 8:
            continue
        cand.append(_norm(ln))
    if not cand:
        cand = [_norm(ln) for ln in lines if len(_norm(ln)) >= 8]
    if not cand:
        return []
    picks = []
    picks.append(cand[0])             # 첫 변별 줄(보통 캡션 앞부분 — 잘림에 강함)
    longest = max(cand, key=len)
    if longest not in picks:
        picks.append(longest)
    if len(cand) > 1 and cand[1] not in picks:
        picks.append(cand[1])
    # 각 후보 앞 30자로 정규화
    return [p[:30] for p in picks if p][:3]


async def _read_post(page) -> tuple[str, datetime | None]:
    """현재 IG 게시물 페이지에서 (캡션 텍스트, 게시일시 KST) 반환."""
    chunks: list[str] = []
    try:
        meta = await page.locator('meta[property="og:description"]').first.get_attribute(
            "content", timeout=4000)
        if meta:
            chunks.append(meta)
    except Exception:
        pass
    for sel in ('article', 'main', 'h1'):
        try:
            txt = await page.locator(sel).first.inner_text(timeout=3000)
            if txt:
                chunks.append(txt)
        except Exception:
            continue
    posted = None
    try:
        raw = await page.locator('time[datetime]').first.get_attribute("datetime", timeout=3000)
        if raw:
            posted = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(KST)
    except Exception:
        posted = None
    return _norm(" ".join(chunks)), posted


async def _collect_grid(page, account: str, scrolls: int, max_posts: int) -> list[dict]:
    """프로필 그리드를 스크롤하며 게시물 URL + 썸네일 alt(게시일 포함) 수집.
    ★읽기 전용 — goto·evaluate(스크롤/DOM 읽기)만. 클릭·입력·업로드 호출 없음."""
    order: list[str] = []
    alts: dict[str, str] = {}
    for _ in range(max(1, scrolls)):
        try:
            rows = await page.evaluate(
                """() => [...document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')]
                     .map(a => ({href: a.getAttribute('href'),
                                 alt: (a.querySelector('img')?.getAttribute('alt') || '')}))"""
            )
        except Exception:
            rows = []
        for r in rows or []:
            m = POST_HREF_RE.search(r.get("href") or "")
            if not m:
                continue
            u = f"https://www.instagram.com/{m.group(1)}/{m.group(2)}/"
            if u not in alts:
                order.append(u)
                alts[u] = r.get("alt") or ""
            elif r.get("alt") and not alts[u]:
                alts[u] = r.get("alt")
        if len(order) >= max_posts:
            break
        prev = await page.evaluate("() => document.body.scrollHeight")
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2.5)
        if await page.evaluate("() => document.body.scrollHeight") == prev:
            await asyncio.sleep(2.5)
            if await page.evaluate("() => document.body.scrollHeight") == prev:
                break
    grid = [{"url": u, "alt": alts[u], "alt_date": _alt_date(alts[u])} for u in order[:max_posts]]
    per_date: dict[str, int] = {}
    for g in grid:
        if g["alt_date"]:
            per_date[g["alt_date"]] = per_date.get(g["alt_date"], 0) + 1
    for g in grid:
        g["date_unique"] = per_date.get(g["alt_date"] or "", 0) == 1
    return grid


def _login_required(url: str) -> bool:
    return any(sig in (url or "") for sig in LOGIN_SIGNALS)


def _evidence(item: dict, live: str, posted: datetime | None, date_unique: bool,
              snippets: list[str]) -> list[str]:
    """근거 목록 — ①캡션 스니펫 ②게시일 ③게시시각 ④제목 핵심어. 최소 2개 일치해야 채택.
    ★근거 없이 느슨하게 하지 않는다 — 틀린 주소를 붙이는 게 빈 칸보다 나쁘다(배9578)."""
    ev: list[str] = []
    for sn in snippets:
        if sn and (sn in live or (len(sn) >= 14 and sn[:14] in live)):
            ev.append(f"캡션 '{sn[:20]}'")
            break
    if posted:
        if posted.strftime("%Y-%m-%d") in _item_dates(item):
            ev.append(f"게시일 {posted:%Y-%m-%d}" + ("(당일 유일)" if date_unique else ""))
        for t in _item_times(item):
            gap = abs((posted - t).total_seconds())
            if gap <= TIME_TOLERANCE_SEC:
                ev.append(f"게시시각 {posted:%H:%M} (기록 {t:%H:%M}, {int(gap)}초 차)")
                break
    core = _squash(_title_core(item))
    if len(core) >= 5 and core[:12] in _squash(live):
        ev.append(f"제목 핵심어 '{_title_core(item)[:20]}'")
    return ev


async def _verify_one(context, item: dict, grid: list[dict],
                      used_urls: set[str]) -> tuple[str, str, str | None]:
    """단일 항목 대조. 반환 (verdict, reason, post_url).
    verdict ∈ {'match','nomatch','login','notfound','error'}"""
    account = (item.get("account") or DEFAULT_ACCOUNT).strip()
    snippets = _match_snippets(item.get("caption") or "")

    post_url = (item.get("post_url") or "").strip()
    if post_url:
        candidates = [{"url": post_url, "alt_date": None, "date_unique": False}]
    else:
        if not grid:
            return "notfound", "프로필에서 게시물 링크 미발견", None
        # 날짜로 후보를 좁힌다 — alt 날짜는 UTC 기준이라 ±1일 여유를 둔다.
        want = _item_dates(item)
        wide: set[str] = set()
        for d in want:
            try:
                base = datetime.fromisoformat(d)
            except ValueError:
                continue
            for off in (-1, 0, 1):
                wide.add((base + timedelta(days=off)).strftime("%Y-%m-%d"))
        candidates = [g for g in grid if g["alt_date"] and g["alt_date"] in wide]
        if not candidates:
            # 날짜 근거가 없거나 그리드에 해당 날짜가 없으면 최신 앞쪽만 훑는다(종전 동작).
            candidates = grid[:6]
        candidates = [g for g in candidates if g["url"] not in used_urls]
        if not candidates:
            return "nomatch", "날짜 후보 게시물이 모두 다른 항목에 이미 배정됨", None

    page = await context.new_page()
    try:
        best: tuple[list[str], str] | None = None
        live_seen = False
        for cand in candidates:
            await page.goto(cand["url"], wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            if _login_required(page.url):
                return "login", f"세션 만료/로그인 필요(account={account})", None
            live, posted = await _read_post(page)
            if live:
                live_seen = True
            ev = _evidence(item, live, posted, cand.get("date_unique", False), snippets)
            if len(ev) >= 2 and (best is None or len(ev) > len(best[0])):
                best = (ev, cand["url"])
                if len(ev) >= 3:
                    break
        if best:
            return "match", "근거 " + str(len(best[0])) + "개 — " + " · ".join(best[0]), best[1]
        if not live_seen:
            return "notfound", "게시물 캡션 텍스트 미회수", None
        return "nomatch", (f"후보 {len(candidates)}건 대조했으나 근거 2개 미달"
                           f"(날짜후보={sorted(_item_dates(item))})"), None
    except Exception as exc:
        return "error", f"대조 예외: {type(exc).__name__}: {exc}", None
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _launch(account: str):
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        user_data_dir=str(_profile_dir(account)),
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    return p, context


def _is_target(it: dict) -> bool:
    """대조 대상 판정 — ① 발행검증대기(도장 대상) ② 발행완료인데 주소 빈 건(주소 백필 대상).
    이미 주소가 있는 발행완료 건은 제외(불필요한 크롤 방지)."""
    if "인스타그램" not in (it.get("channel") or ""):
        return False
    status = it.get("status")
    if status == TARGET_STATUS:
        return True
    if status == URL_BACKFILL_STATUS:
        return not (it.get("url") or it.get("post_url") or "").strip()
    return False


async def run(target_id: str | None, dry_run: bool,
              scrolls: int = 3, max_posts: int = 18) -> int:
    queue: list[dict] = json.loads(QUEUE.read_text(encoding="utf-8"))
    # 이미 다른 항목이 쓰고 있는 주소는 재배정 금지(중복 배정 방지).
    used_urls = {(it.get("post_url") or "").strip() for it in queue
                 if (it.get("post_url") or "").strip()}
    targets = [
        it for it in queue
        if _is_target(it) and (target_id is None or it.get("id") == target_id)
    ]
    if not targets:
        print("✅ 대조할 인스타그램 항목 없음(발행검증대기 0건 · 주소 빈 발행완료 0건).")
        return 0

    # 계정별 그룹 — 계정 1개 세션으로 해당 계정 건 일괄 대조
    by_acct: dict[str, list[dict]] = {}
    for it in targets:
        by_acct.setdefault((it.get("account") or DEFAULT_ACCOUNT).strip(), []).append(it)

    stamped = 0
    # ★저장은 '이번에 실제로 바꾼 항목'만 넘긴다(2026-07-23 배9578 실측 사고).
    #   큐 전체를 넘기면 merge_save_review_queue 가 id 마다 이 프로세스의 스테일 사본으로
    #   덮어써, 대조가 도는 몇 분 사이 다른 프로세스가 채운 값이 지워진다
    #   (실측: 13:28 회수기가 채운 카카오 post_url 을 13:30 이 스윕이 되돌림).
    changed_items: list[dict] = []
    for account, items in by_acct.items():
        if not _profile_dir(account).exists():
            print(f"[WARN] 프로필 미존재(account={account}) — 건너뜀 {len(items)}건")
            continue
        p = context = None
        try:
            p, context = await _launch(account)
            # 계정당 그리드 1회만 수집해 항목들이 공유한다(항목마다 재수집하면 크롤이 N배).
            grid: list[dict] = []
            gpage = await context.new_page()
            try:
                await gpage.goto(f"https://www.instagram.com/{account}/",
                                 wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)
                if _login_required(gpage.url):
                    print(f"🔒 [{account}] 세션 만료/로그인 필요 — {len(items)}건 건너뜀")
                    continue
                grid = await _collect_grid(gpage, account, scrolls, max_posts)
                print(f"[grid] {account}: 게시물 {len(grid)}건 수집"
                      f"(스크롤 {scrolls} · 상한 {max_posts})")
            finally:
                try:
                    await gpage.close()
                except Exception:
                    pass
            for it in items:
                verdict, reason, post_url = await _verify_one(context, it, grid, used_urls)
                tag = {"match": "✅", "nomatch": "⚠️", "login": "🔒",
                       "notfound": "❓", "error": "💥"}.get(verdict, "?")
                print(f"{tag} [{it.get('id')}] {verdict} — {reason}")
                if verdict == "match" and post_url:
                    used_urls.add(post_url)
                if verdict == "match" and not dry_run:
                    was_backfill = it.get("status") == URL_BACKFILL_STATUS
                    it["status"] = "발행완료"
                    it["published_at"] = it.get("published_at") or datetime.now().isoformat(
                        timespec="seconds")
                    if post_url:
                        it["post_url"] = post_url
                    # note 는 덮어쓰지 않고 뒤에 붙인다 — 이미 발행완료로 굳은 건(주소 백필 대상)의
                    # 기존 이력을 지우지 않기 위함(2026-07-23 배9578).
                    label = "주소 회수" if was_backfill else "발행완료"
                    stamp = f"[자동대조 {label} {datetime.now():%Y-%m-%d}] {reason}"
                    prev = (it.get("note") or "").strip()
                    it["note"] = (prev + " | " + stamp) if prev else stamp
                    stamped += 1
                    changed_items.append(it)
        finally:
            try:
                if context:
                    await context.close()
                if p:
                    await p.stop()
            except Exception:
                pass

    if changed_items:
        # 락 안에서 최신본 재로드 후 id 병합 저장 — 대조(수 분) 사이 추가된 신규 항목 보존.
        # id 없는 항목은 id 병합이 불가하므로 그때만 종전처럼 큐 전체를 넘긴다(변경 유실 방지).
        payload = changed_items if all(it.get("id") for it in changed_items) else queue
        merge_save_review_queue(payload, holder="ig_publish_verify")
    print(f"\n→ 대조 {len(targets)}건 / 발행완료 도장 {stamped}건"
          + (" (dry-run, 미반영)" if dry_run else ""))
    return stamped


def main() -> int:
    ap = argparse.ArgumentParser(description="IG 발행검증 자동 대조 → 발행완료 도장")
    ap.add_argument("--id", help="특정 항목 id만 대조")
    ap.add_argument("--dry-run", action="store_true", help="도장 없이 대조 결과만")
    ap.add_argument("--commit", action="store_true",
                    help="도장 후 review_queue 를 GitLock으로 커밋·푸시(스케줄러용)")
    ap.add_argument("--scrolls", type=int, default=3,
                    help="프로필 그리드 스크롤 횟수(기본 3 ≈ 최근 36건). 옛 게시물 회수 시 늘린다")
    ap.add_argument("--max-posts", type=int, default=18,
                    help="그리드에서 수집할 게시물 상한(기본 18)")
    args = ap.parse_args()
    stamped = asyncio.run(run(args.id, args.dry_run, args.scrolls, args.max_posts))
    # [2026-07-27 시모] stamped > 0 조건 삭제. 옛 코드는 "이번 실행에서 도장을 찍었을 때만"
    # 커밋했다 — 도장은 찍혔는데 그 순간 커밋이 실패하면(락 경합 등) 변경이 작업트리에 고립되고,
    # 다음 스윕은 로컬을 읽어 "발행검증대기 0건"이라 판단해 stamped=0 → 커밋 블록을 통째로
    # 건너뛴다. "다음 스윕 재시도"라는 주석은 실제로는 지켜지지 않았다.
    # 실측: AI하루 03(2026-07-27) 이 로컬만 발행완료·저장소는 발행검증대기로 남아 M1(GM 화면)이
    # 하루 종일 옛 상태를 보였다. safe_commit 은 변경 없으면 무해 통과(committed=False)라
    # 매번 호출해도 안전하다 → 조건을 없애는 쪽이 옳다(장치 추가 아님·조건 제거).
    if args.commit and not args.dry_run:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            # 안전 커밋터(2026-07-23 배9820) — 임시 인덱스(read-tree HEAD) + 커밋 직전 HEAD
            # 재검증 + update-ref CAS. 공용 작업트리에서 남의 미커밋 변경분을 쓸어담거나
            # 그 사이 들어온 파일을 '삭제'로 기록하는 스테일 트리 레이스를 구조적으로 차단.
            from safe_commit import safe_commit
            res = safe_commit(
                [str(QUEUE)],
                "auto(cmo): IG 발행검증 자동 대조 → 발행완료 도장",
                holder="ig_publish_verify",
            )
            print(f"[{'INFO' if res['ok'] else 'WARN'}] 커밋: {res['reason']}"
                  + (f" · 혼입 {res['foreign']}" if res["foreign"] else ""))
        except Exception as exc:
            print(f"[WARN] 커밋 실패(무해 — 다음 스윕 재시도): {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
