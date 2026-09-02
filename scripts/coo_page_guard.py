# -*- coding: utf-8 -*-
"""시우(COO) 소유 화면 자동 점검 — 사람이 열어 봐야만 보이던 흠을 기계가 먼저 잡는다.

왜 있나
    2026-09-02 하루에 GM 이 직접 잡아 주신 것이 다섯 건이었다(키오스크 터치 스크롤·입력칸
    자동확대·습득물 이미지 크기·접수 조회 화면 오른쪽 잘림·월간운영계획 달 상태). 다섯 건 다
    "화면을 열어 봤으면 바로 보이는 것"이었고, 아침 자가점검이 '모듈이 도는가'만 봐서 전부
    통과시켰다. GM: "시우가 소유관리하는 페이지가 많은데, 이런 디테일한 것들은 스스로 챙겨야해."

무엇을 보나 (기계가 판정할 수 있는 것만)
    1. 가로 잘림     — 문서 폭이 창보다 넓다(좌우로 잘려 보인다)
    2. 폭 미달       — 본문이 창 폭의 90% 도 못 채운다(오른쪽에 빈 띠 = 잘린 것처럼 보인다)
    3. 자동확대 위험 — 글자 16px 미만인 입력칸이 있다(누르면 화면이 확대돼 안 돌아온다)
    4. 스크롤 막힘   — 내용이 창보다 긴데 문서가 스크롤되지 않는다

무엇을 안 보나
    디자인·문구·데이터 정확도. 그건 사람이 본다. 여기는 "열어 보면 바로 아는 흠"만 잡는다.

쓰는 법
    python scripts/coo_page_guard.py              # 전체 점검(표 출력 + status 저장)
    python scripts/coo_page_guard.py --only 접수  # 이름에 그 글자가 들어간 화면만
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "3. 웰페리온 가이드"
OUT = ROOT / "status" / "coo_page_guard.json"
PAGES_BASE = "https://wellperion-cao.github.io/wellperion-automation/"

# 워드프레스에 본문이 심어져 돌아가는 조각 — 저장소 파일이 아니라 라이브 주소로 봐야 한다.
WP_PAGES = [
    ("종합접수처", "http://wellperion.com/ko/reception/"),
    ("접수 조회", "http://wellperion.com/ko/lookup/"),
    ("습득물 보기", "http://wellperion.com/ko/lost-found/"),
    ("습득물 등록", "http://wellperion.com/ko/lost-found-register/"),
]

# 키오스크(세로 큰 화면)와 데스크톱(가로) 둘 다 본다 — 오늘 잘림은 가로에서만 났다.
VIEWPORTS = [("키오스크 세로", 1080, 1920), ("데스크톱 가로", 1920, 1080)]

PROBE = """() => {
  const de = document.documentElement, body = document.body;
  const small = [];
  document.querySelectorAll('input,select,textarea').forEach(el => {
    if (el.type === 'hidden' || !el.offsetParent) return;
    const fs = parseFloat(getComputedStyle(el).fontSize || '16');
    if (fs && fs < 16) small.push((el.tagName + '.' + (el.className || '')).slice(0, 40) + ' ' + fs + 'px');
  });
  let widest = 0;
  Array.from(body.children).forEach(el => { widest = Math.max(widest, el.getBoundingClientRect().width); });
  return {
    scrollW: de.scrollWidth, clientW: de.clientWidth,
    scrollH: de.scrollHeight, clientH: de.clientHeight,
    contentW: Math.round(widest),
    small: small.slice(0, 5)
  };
}"""

# 스크롤은 규칙을 읽어 짐작하지 않고 실제로 밀어 본다 — 넘침 값 조합은 브라우저가 다시 계산해서
# 눈으로 읽으면 틀린다(2026-09-02 첫 판에서 멀쩡한 화면을 '막힘'으로 잡았다).
SCROLL_TEST = """() => {
  const de = document.documentElement;
  if (de.scrollHeight <= de.clientHeight + 2) return {needed: false, moved: true};
  const before = window.scrollY;
  window.scrollTo(0, 400);
  const after = window.scrollY;
  window.scrollTo(0, before);
  return {needed: true, moved: after > before + 10};
}"""


def _findings(m: dict, w: int) -> list[str]:
    out = []
    if m["scrollW"] > m["clientW"] + 2:
        out.append(f"가로 잘림 — 문서 폭 {m['scrollW']} > 창 {m['clientW']}")
    if m["contentW"] and m["contentW"] < w * 0.9:
        out.append(f"폭 미달 — 본문 {m['contentW']} / 창 {w} (오른쪽 빈 띠)")
    if m["small"]:
        out.append("자동확대 위험 — 16px 미만 입력칸 " + ", ".join(m["small"]))
    if m.get("scrollBlocked"):
        out.append("스크롤 막힘 — 내용이 창보다 긴데 실제로 밀어도 안 내려간다")
    return out


def local_pages() -> list[tuple[str, str]]:
    """coo/ 아래 화면 + 월간운영계획. 워드프레스 조각(_block)과 템플릿은 뺀다."""
    items: list[tuple[str, str]] = []
    for p in sorted((GUIDE / "coo").rglob("*.html")):
        n = p.name
        if "_block" in n or "_template" in n or n.startswith("_"):
            continue
        rel = p.relative_to(GUIDE).as_posix()
        items.append((p.stem, PAGES_BASE + urllib.parse.quote(rel)))
    mop = GUIDE / "월간운영계획.html"
    if mop.exists():
        items.append(("월간운영계획", PAGES_BASE + urllib.parse.quote("월간운영계획.html")))
    return items


async def check(targets: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright  # noqa: PLC0415

    rows: list[dict] = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for name, url in targets:
            hits: list[str] = []
            for vp_name, w, h in VIEWPORTS:
                pg = await b.new_page(viewport={"width": w, "height": h})
                try:
                    await pg.goto(url, wait_until="load", timeout=45000)
                    await pg.wait_for_timeout(3500)
                    m = await pg.evaluate(PROBE)
                    sc = await pg.evaluate(SCROLL_TEST)
                    m["scrollBlocked"] = sc["needed"] and not sc["moved"]
                    hits += [f"[{vp_name}] {f}" for f in _findings(m, w)]
                except Exception as e:
                    hits.append(f"[{vp_name}] 못 열었다 — {str(e)[:60]}")
                finally:
                    await pg.close()
            rows.append({"name": name, "url": url, "findings": hits})
            print(("  OK  " if not hits else "  걸림 ") + name + (" — " + hits[0] if hits else ""))
        await b.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="시우 소유 화면 자동 점검")
    ap.add_argument("--only", default="", help="이름에 이 글자가 든 화면만")
    args = ap.parse_args()

    targets = WP_PAGES + local_pages()
    if args.only:
        targets = [t for t in targets if args.only in t[0]]
    print(f"[점검] 대상 {len(targets)}개 화면 × 화면크기 2종")

    rows = asyncio.run(check(targets))
    bad = [r for r in rows if r["findings"]]
    OUT.write_text(json.dumps({
        "generated_at_kst": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "checked": len(rows), "hit": len(bad), "rows": rows,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n걸린 화면 {len(bad)} / {len(rows)}")
    for r in bad:
        print(f"\n▪ {r['name']}  {r['url']}")
        for f in r["findings"]:
            print(f"   {f}")
    print(f"\n기록: {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
