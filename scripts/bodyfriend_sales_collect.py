# -*- coding: utf-8 -*-
"""바디프렌드 라운지(안마의자) 매출 수집 — 매출 및 회원 현황 보고 1면 「그 밖의 매출」용.

GM 지시 2026-09-17: 「바디프렌드·주차·굿즈 매출도 잡아라 · 라운지 매출은 그대로 올려라(우리 몫 30% 는 알고 있다)」.

원천 = lounge.bodyfriend.co.kr 가맹점관리자 ▸ 매출집계(/owner/order/total · placeId 880 · 일별).
  그 화면은 날짜마다 「합계 ( YYYY-MM-DD ) = 12,345원」 줄을 찍는다 — 그 줄만 읽는다(표 칸 구조가 바뀌어도 버틴다).
계정 = 서버 파트너 계정함 한 곳(/api/partner-secrets/fetch · tenant=wellperion · channel=bodyfriend).
  열쇠는 이 PC 의 ~/.claude/token_push.key. 값은 메모리에만 두고 파일·로그에 남기지 않는다.
결과 = status/bodyfriend_sales.json  {"month","total_krw","days":{"YYYY-MM-DD":금액},"fetched_at"}
  보고 화면이 이 파일을 읽는다(erp 는 /repo/status/…, 공개 사본은 상대경로).

실행:  python scripts\\bodyfriend_sales_collect.py [YYYY-MM]      (기본 = 이번 달)
       python scripts\\bodyfriend_sales_collect.py --selftest      (네트워크 없음 · 파싱만)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "status" / "bodyfriend_sales.json"
KST = timezone(timedelta(hours=9))
SECRETS_URL = "https://erp.wellperion.com/api/partner-secrets/fetch?tenant=wellperion&channel=bodyfriend"
PLACE_ID = "880"          # 웰페리온 (라운지 화면의 placeId)
TOTAL_LINE = re.compile(r"합계\s*\(\s*(\d{4}-\d{2}-\d{2})\s*\)\s*=\s*([\d,]+)\s*원")


def parse_days(text: str) -> dict:
    """화면 글에서 날짜별 합계 줄만 뽑는다. 같은 날짜가 두 번 나오면 뒤엣것으로 덮지 않고 큰 값을 쓴다
    (화면이 소계·합계를 같이 찍는 날이 있어 작은 쪽이 소계다)."""
    out = {}
    for d, amt in TOTAL_LINE.findall(text):
        v = int(amt.replace(",", ""))
        out[d] = max(out.get(d, 0), v)
    return out


def month_range(ym: str):
    y, m = int(ym[:4]), int(ym[5:7])
    start = "%04d-%02d-01" % (y, m)
    nxt = datetime(y + (m == 12), (m % 12) + 1, 1)
    end = (nxt - timedelta(days=1)).strftime("%Y-%m-%d")
    return start, end


def fetch_secret():
    key = (Path.home() / ".claude" / "token_push.key").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(SECRETS_URL, headers={"X-Token-Push-Key": key})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    if not d.get("ok") or not d.get("id"):
        raise SystemExit("[fail] 계정이 아직 서버 보관함에 없다 — /erp/admin 파트너사 관리에서 넣는다")
    return d["id"], d["pw"]


def collect(ym: str) -> dict:
    from playwright.sync_api import sync_playwright
    start, end = month_range(ym)
    uid, pw = fetch_secret()
    url = ("https://lounge.bodyfriend.co.kr/owner/order/total?size=99999&page=0&placeId=%s&orderStatus="
           "&viewType=DAY&orderSearchStart=%s&orderSearchEnd=%s" % (PLACE_ID, start, end))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("https://lounge.bodyfriend.co.kr/", wait_until="networkidle", timeout=60000)
        pg.fill("#username", uid)
        pg.fill("#password", pw)
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(5000)
        pg.goto(url, wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(4000)
        text = pg.inner_text("body")
        b.close()
    if "가맹점관리자" not in text:
        raise SystemExit("[fail] 매출집계 화면이 안 열렸다(로그인·권한 확인) — 값 쓰지 않는다")
    days = parse_days(text)
    return {
        "month": ym,
        "total_krw": sum(days.values()),
        "days": dict(sorted(days.items())),
        "place_id": PLACE_ID,
        "source": "lounge.bodyfriend.co.kr /owner/order/total (일별 합계 줄)",
        "fetched_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }


def selftest():
    sample = ("소계 ( 웰페리온 스파 ) = 10,000원\n합계 ( 2026-09-04 ) = 10,000원\n"
              "소계 ( 웰페리온 스파 ) = 5,000원\n합계 ( 2026-09-05 ) = 15,000원\n")
    d = parse_days(sample)
    assert d == {"2026-09-04": 10000, "2026-09-05": 15000}, d
    assert sum(d.values()) == 25000
    assert month_range("2026-09") == ("2026-09-01", "2026-09-30")
    assert month_range("2026-12") == ("2026-12-01", "2026-12-31")
    assert parse_days("합계 ( 2026-09-04 ) = 3,000원\n합계 ( 2026-09-04 ) = 9,000원") == {"2026-09-04": 9000}
    print("selftest ok")


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--selftest"]
    if "--selftest" in sys.argv:
        selftest()
        return 0
    ym = args[0] if args else datetime.now(KST).strftime("%Y-%m")
    data = collect(ym)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("DONE: %s 매출 %s원 · 날짜 %d일 · %s" % (ym, format(data["total_krw"], ","), len(data["days"]), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
