#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ERP 화면 완성도 채점표를 기계가 읽는 형태로 낸다 (배478 · GM 지시 2026-08-08 / 배641 원천 전환).

왜 있나
  웰리가 배465(2026-08-10)로 79개 화면을 재채점했는데, 결과가 GM업무 화면 안에 표로만
  들어갔다. 사람은 볼 수 있지만 **기계는 못 읽는다.** 그래서 GM 이 이 배에 적어 둔 요구 —
  "아침 자가점검이 이 점수를 입력으로 쓰게 해서, 낮은 점수가 곧 그날의 배가 되게 한다.
  점수판이 장식이 되면 실패다" — 가 충족되지 않았다.

무엇을 하나
  ★2026-08-16(배641) — 원천이 뒤집혔다. GM 지시(08-13)로 GM업무.html #sec-erp-score 가
  삭제되고 자율현황이 status/page_score.json 을 직접 렌더한다(웰리 처리). 이제 이 파일이
  **정본**이다 — HTML 을 파싱하지 않는다(파싱할 HTML 이 더는 없다). 재채점 = 이 JSON 을
  직접 고친다.

쓰는 곳
  hangro_board.py 부팅 슬라이스가 이 파일을 읽어 저점 화면을 띄운다.
  자율현황 화면이 이 파일을 직접 렌더한다(2026-08-13 이관).

사용:  python scripts/page_score_extract.py [--check|--ping]
       --check 는 지금 저장된 page_score.json 요약만 낸다(파일을 새로 안 만든다).
       --ping  은 화면 열람 흔적을 걷어 status/page_ping.json 으로 낸다(매일 07:40 자동,
                HTML 을 안 읽어 이번 전환과 무관).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
OUT = _REPO / "status" / "page_score.json"


# _ping_key 가 화면 파일 경로를 찾을 때 쓰는 뿌리(아래에서 계속 씀).
_GUIDE_ROOT = _REPO / "3. 웰페리온 가이드"


def load_current() -> dict:
    """정본(status/page_score.json)을 그대로 읽는다. 파일이 없으면 안내와 함께 SystemExit
    (예전처럼 HTML 을 파싱해 새로 만들지 않는다 — 2026-08-16 배641 원천 전환)."""
    if not OUT.exists():
        raise SystemExit(f"{OUT.relative_to(_REPO)} 이 없습니다 — 재채점은 이 JSON 을 직접 만듭니다.")
    return json.loads(OUT.read_text(encoding="utf-8"))


# ── 화면 열람 흔적 수집 (2026-08-12 · GM 승인) ────────────────────────────────
#   화면 쪽 짝 = 3. 웰페리온 가이드/_assets/page_ping.js (열릴 때 경로+시각만 남긴다).
#   여기서는 그 흔적을 하루 1회 걷어 status/page_ping.json 으로 낸다.
#   ★새 저장소를 만들지 않는다 — 이미 쓰는 점검 GAS 의 범용 보드 통로를 그대로 읽는다(L21).
PING_GAS = ("https://script.google.com/macros/s/"
            "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec")
PING_OUT = _REPO / "status" / "page_ping.json"
_PAGES_PREFIX = "/wellperion-automation/"  # 라이브 주소엔 '3. 웰페리온 가이드' 가 안 붙는다


def _ping_key(name: str) -> str | None:
    stem = re.sub(r"\s*\(.*$", "", name).strip()
    hits = list(_GUIDE_ROOT.rglob(f"{stem}.html"))
    if not hits:
        return None
    return "ping:" + _PAGES_PREFIX + hits[0].relative_to(_GUIDE_ROOT).as_posix()


def collect_pings() -> dict:
    """채점 대상 화면의 마지막 열람 시각을 모아 status/page_ping.json 으로."""
    import time
    import urllib.parse
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    scored = json.loads(OUT.read_text(encoding="utf-8"))["pages"]
    targets = [(p["name"], _ping_key(p["name"])) for p in scored]

    def fetch(item):
        name, key = item
        if not key:
            return name, None, "화면 파일을 못 찾음"
        url = f"{PING_GAS}?action=board&key={urllib.parse.quote(key, safe='')}"
        # GAS 는 동시 요청을 조이면 404 를 낸다(2026-08-12 실측: 8줄 병렬에서 43건 중 28건
        # 404, 같은 주소를 하나씩 부르면 전부 200). 그래서 줄을 좁히고 재시도를 둔다 —
        # 여기서 404 를 그냥 넘기면 '아무도 안 열었다'로 잘못 읽혀 멀쩡한 화면이 정리 후보가 된다.
        last_err = ""
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    body = json.loads(r.read().decode("utf-8"))
                return name, (body.get("board") or {}).get("last"), ""
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
        return name, None, f"조회 실패(3회): {last_err}"

    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, targets))

    pages = [{"name": n, "last_open": last, "note": note} for n, last, note in rows]
    opened = [p for p in pages if p["last_open"]]
    data = {
        "_doc": "화면 열람 흔적 — 생성물. 화면 쪽 짝 = _assets/page_ping.js. "
                "last_open 이 비어 있으면 '핑을 넣은 뒤로 아직 아무도 안 열었다'는 뜻이다 "
                "(핑을 못 넣은 화면은 note 에 사유가 적힌다). 갱신 = python scripts/page_score_extract.py --ping",
        "collected_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(pages),
        "opened_count": len(opened),
        "pages": sorted(pages, key=lambda p: (p["last_open"] or "")),
    }
    PING_OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> None:
    if "--ping" in sys.argv:
        d = collect_pings()
        print(f"[OK] {PING_OUT.relative_to(_REPO)} — {d['count']}건 중 열람 흔적 {d['opened_count']}건")
        return
    # ★HTML 파싱 없음(2026-08-16 배641) — page_score.json 이 정본이라 여기서는 읽기만 한다.
    #   재채점은 이 파일을 직접 고친다.
    data = load_current()
    pages = data.get("pages") or []
    if not pages:
        print(f"{OUT.relative_to(_REPO)} — pages 0건")
        return
    print(f"{len(pages)}건 · 최저 {pages[0]['score']}% ({pages[0]['name']})")


if __name__ == "__main__":
    main()
