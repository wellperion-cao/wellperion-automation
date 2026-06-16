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
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
PROFILE_BASE = ROOT / "profiles" / "instagram"
DEFAULT_ACCOUNT = "namuk.wellperion"
TARGET_STATUS = "발행검증대기"
LOGIN_SIGNALS = ("instagram.com/accounts/login", "instagram.com/accounts/onetap", "/challenge/")
POST_HREF_RE = re.compile(r"/(p|reel)/([A-Za-z0-9_-]+)/")


def _norm(t: str) -> str:
    """공백·개행 정규화(대조 비교용)."""
    return re.sub(r"\s+", " ", (t or "")).strip()


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


async def _read_caption_text(page) -> str:
    """현재 IG 게시물 페이지에서 캡션 텍스트 후보를 최대한 모아 반환."""
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
    return _norm(" ".join(chunks))


def _login_required(url: str) -> bool:
    return any(sig in (url or "") for sig in LOGIN_SIGNALS)


async def _verify_one(context, item: dict) -> tuple[str, str, str | None]:
    """단일 항목 대조. 반환 (verdict, reason, post_url).
    verdict ∈ {'match','nomatch','login','notfound','error'}"""
    account = (item.get("account") or DEFAULT_ACCOUNT).strip()
    caption = item.get("caption") or item.get("title") or ""
    snippets = _match_snippets(caption)
    if not snippets:
        return "error", "대조 스니펫 추출 실패(캡션 없음)", None

    def _hit(live: str) -> str | None:
        for sn in snippets:
            if sn and sn in live:
                return sn
            if len(sn) >= 14 and sn[:14] in live:
                return sn[:14]
        return None

    page = await context.new_page()
    try:
        # 대조 대상 게시물 URL 목록 — post_url 있으면 그것만, 없으면 프로필 앞쪽 N개
        # (공식 계정은 고정/핀 게시물이 맨 앞일 수 있어 최신 1개만 보면 놓친다)
        candidates: list[str] = []
        post_url = (item.get("post_url") or "").strip()
        if post_url:
            candidates = [post_url]
        else:
            await page.goto(f"https://www.instagram.com/{account}/",
                            wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            if _login_required(page.url):
                return "login", f"세션 만료/로그인 필요(account={account})", None
            try:
                hrefs = await page.locator(
                    'a[href*="/p/"], a[href*="/reel/"]').evaluate_all(
                    "els => els.map(e => e.getAttribute('href'))")
            except Exception:
                hrefs = []
            seen = set()
            for h in hrefs or []:
                m = POST_HREF_RE.search(h or "")
                if not m:
                    continue
                u = f"https://www.instagram.com/{m.group(1)}/{m.group(2)}/"
                if u not in seen:
                    seen.add(u)
                    candidates.append(u)
                if len(candidates) >= 6:
                    break
            if not candidates:
                return "notfound", "프로필에서 게시물 링크 미발견", None

        last_live_empty = True
        for url in candidates:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            if _login_required(page.url):
                return "login", f"세션 만료/로그인 필요(account={account})", None
            live = await _read_caption_text(page)
            if live:
                last_live_empty = False
            hit = _hit(live)
            if hit:
                return "match", f"대조 일치: '{hit}'", url
        if last_live_empty:
            return "notfound", "게시물 캡션 텍스트 미회수", (candidates[0] if candidates else None)
        return "nomatch", (f"앞쪽 {len(candidates)}개 게시물에서 스니펫 {snippets} 미검출"), None
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


async def run(target_id: str | None, dry_run: bool) -> int:
    queue: list[dict] = json.loads(QUEUE.read_text(encoding="utf-8"))
    targets = [
        it for it in queue
        if it.get("status") == TARGET_STATUS
        and "인스타그램" in (it.get("channel") or "")
        and (target_id is None or it.get("id") == target_id)
    ]
    if not targets:
        print("✅ 대조할 발행검증대기 인스타그램 항목 없음.")
        return 0

    # 계정별 그룹 — 계정 1개 세션으로 해당 계정 건 일괄 대조
    by_acct: dict[str, list[dict]] = {}
    for it in targets:
        by_acct.setdefault((it.get("account") or DEFAULT_ACCOUNT).strip(), []).append(it)

    stamped = 0
    changed = False
    for account, items in by_acct.items():
        if not _profile_dir(account).exists():
            print(f"[WARN] 프로필 미존재(account={account}) — 건너뜀 {len(items)}건")
            continue
        p = context = None
        try:
            p, context = await _launch(account)
            for it in items:
                verdict, reason, post_url = await _verify_one(context, it)
                tag = {"match": "✅", "nomatch": "⚠️", "login": "🔒",
                       "notfound": "❓", "error": "💥"}.get(verdict, "?")
                print(f"{tag} [{it.get('id')}] {verdict} — {reason}")
                if verdict == "match" and not dry_run:
                    it["status"] = "발행완료"
                    it["published_at"] = it.get("published_at") or datetime.now().isoformat(
                        timespec="seconds")
                    if post_url:
                        it["post_url"] = post_url
                    it["note"] = f"[자동대조 발행완료 {datetime.now():%Y-%m-%d}] {reason}"
                    stamped += 1
                    changed = True
        finally:
            try:
                if context:
                    await context.close()
                if p:
                    await p.stop()
            except Exception:
                pass

    if changed:
        QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ 대조 {len(targets)}건 / 발행완료 도장 {stamped}건"
          + (" (dry-run, 미반영)" if dry_run else ""))
    return stamped


def main() -> int:
    ap = argparse.ArgumentParser(description="IG 발행검증 자동 대조 → 발행완료 도장")
    ap.add_argument("--id", help="특정 항목 id만 대조")
    ap.add_argument("--dry-run", action="store_true", help="도장 없이 대조 결과만")
    ap.add_argument("--commit", action="store_true",
                    help="도장 후 review_queue 를 GitLock으로 커밋·푸시(스케줄러용)")
    args = ap.parse_args()
    stamped = asyncio.run(run(args.id, args.dry_run))
    if args.commit and not args.dry_run and stamped > 0:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from git_lock import git_commit_push
            git_commit_push(
                [str(QUEUE)],
                "auto(cmo): IG 발행검증 자동 대조 → 발행완료 도장",
                holder="ig_publish_verify",
            )
            print("[INFO] 변경 커밋·푸시 완료(GitLock)")
        except Exception as exc:
            print(f"[WARN] 커밋 실패(무해 — 다음 스윕 재시도): {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
