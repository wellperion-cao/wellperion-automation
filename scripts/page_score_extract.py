#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ERP 화면 완성도 채점표를 기계가 읽는 형태로 뽑는다 (배478 · GM 지시 2026-08-08).

왜 있나
  웰리가 배465(2026-08-10)로 79개 화면을 재채점했는데, 결과가 GM업무 화면 안에 표로만
  들어갔다. 사람은 볼 수 있지만 **기계는 못 읽는다.** 그래서 GM 이 이 배에 적어 둔 요구 —
  "아침 자가점검이 이 점수를 입력으로 쓰게 해서, 낮은 점수가 곧 그날의 배가 되게 한다.
  점수판이 장식이 되면 실패다" — 가 충족되지 않았다.

무엇을 하나
  GM업무.html 의 채점 섹션(#sec-erp-score)을 읽어 status/page_score.json 으로 낸다.
  화면이 원천이고 이 파일은 파생물이다 — 재채점하면 이 스크립트를 다시 돌린다.
  (데이터를 원천으로 뒤집는 게 구조상 맞지만 그 화면은 웰리 소유라 지금은 파싱으로 잇는다.)

쓰는 곳
  hangro_board.py 부팅 슬라이스가 이 파일을 읽어 저점 화면을 띄운다.

사용:  python scripts/page_score_extract.py [--check|--ping]
       --check 는 파일을 쓰지 않고 몇 건 잡히는지만 낸다.
       --ping  은 화면 열람 흔적을 걷어 status/page_ping.json 으로 낸다(매일 07:40 자동).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
PAGE = _REPO / "3. 웰페리온 가이드" / "coo" / "chairman" / "GM업무.html"
OUT = _REPO / "status" / "page_score.json"
SECTION_ID = 'id="sec-erp-score"'

# 평균 표기는 선택 — 1건짜리 그룹(CTO)은 평균을 안 적어서, 필수로 두면 그 그룹이 통째로
# 앞 그룹(CMO)에 붙어 버린다(2026-08-11 실측: 시모 13건 · 시토 0건으로 잘못 나왔다).
_GROUP = re.compile(r"<summary>[^<]{0,60}?([A-Z]{3})\(([^)]+)\)[^<]*?(\d+)건")
_ROW = re.compile(
    r"<tr><td>\d+</td>"
    r"<td>(?:<strong>)?([^<]+?)(?:</strong>)?</td>"
    r"<td>(?:<strong>)?(\d+)%(?:</strong>)?</td>"
    r"<td>([^<]*)</td>"
)


# ── 채점 대상이 아닌 화면 걸러내기 (2026-08-12 시토 · 배478 2단계) ──────────────
#   GM 결정 2026-08-11: "채점 대상 = 실무진이 실제로 쓰는 화면만". 그런데 채점표 49건 안에
#   **화면이 아닌 것**이 섞여 있었다 — 실측: 리다이렉트 스텁 5건(1.2~3.6KB, 본문 없이 다른
#   주소로 넘김) + 저장소에 파일 자체가 없는 것 1건. 이것들이 점수가 낮게 매겨져 부팅 화면
#   저점 목록의 윗자리를 차지했다(최저 30% '문의흐름지도' = 파일 없음). 없는 화면을 고치라고
#   매일 띄우는 셈이라, 점수판이 일감을 만드는 게 아니라 헛일감을 만들고 있었다.
#   ▸원천(GM업무.html)은 웰리 소유라 건드리지 않는다. 파생물인 이 JSON 에서만 갈라 담는다.
_GUIDE_ROOT = _REPO / "3. 웰페리온 가이드"
_STUB_MAX_BYTES = 4096
_REDIRECT_MARKS = ('http-equiv="refresh"', "location.replace", "location.href")


def _classify_page(name: str) -> tuple[str, str]:
    """(판정, 사유) — 판정은 'scored'(채점 대상) 또는 'excluded'(대상 아님)."""
    # 채점표 이름에 붙은 괄호 꼬리표는 사람 설명이다("GM업무 (이 화면 자체·GM 전용)") —
    # 떼고 찾지 않으면 실재하는 화면을 '파일 없음'으로 잘못 제외한다(2026-08-12 실측 2건).
    stem = re.sub(r"\s*\(.*$", "", name).strip()
    hits = list(_GUIDE_ROOT.rglob(f"{stem}.html"))
    if not hits:
        return "excluded", "저장소에 같은 이름의 화면 파일이 없다"
    path = hits[0]
    try:
        raw = path.read_bytes()
    except Exception:
        return "scored", ""
    if len(raw) <= _STUB_MAX_BYTES:
        text = raw.decode("utf-8", "ignore")
        if any(mark in text for mark in _REDIRECT_MARKS):
            return "excluded", f"리다이렉트 스텁({len(raw)}바이트) — 본문 없이 다른 주소로 넘긴다"
    return "scored", ""


def _section(html: str) -> str:
    """채점 섹션만 잘라 낸다. 끝 = 그 다음 최상위 섹션(<details class="sec") 또는 문서 끝."""
    i = html.find(SECTION_ID)
    if i < 0:
        return ""
    start = html.rfind("<details", 0, i)
    nxt = html.find('<details class="sec"', i + len(SECTION_ID))
    return html[start:nxt] if nxt > 0 else html[start:]


def extract() -> dict:
    html = PAGE.read_text(encoding="utf-8")
    seg = _section(html)
    if not seg:
        raise SystemExit("채점 섹션(#sec-erp-score)을 찾지 못했습니다 — 화면이 바뀌었는지 확인하세요.")

    # 그룹 헤더 위치로 행을 역할에 배정한다(표가 역할별 접힘 안에 있다).
    marks = [(m.start(), m.group(1).lower(), m.group(2)) for m in _GROUP.finditer(seg)]
    pages = []
    for m in _ROW.finditer(seg):
        pos = m.start()
        role, nick = "", ""
        for mp, r, n in marks:
            if mp < pos:
                role, nick = r, n
            else:
                break
        pages.append({
            "name": m.group(1).strip(),
            "score": int(m.group(2)),
            "note": m.group(3).strip(),
            "role": role,
            "owner_nick": nick,
        })
    scored, excluded = [], []
    for p in pages:
        verdict, why = _classify_page(p["name"])
        if verdict == "excluded":
            excluded.append({**p, "excluded_reason": why})
        else:
            scored.append(p)
    scored.sort(key=lambda p: p["score"])
    excluded.sort(key=lambda p: p["score"])
    return {
        "_doc": "ERP 화면 완성도 채점 — 생성물. 원천 = GM업무.html #sec-erp-score(웰리 배465 재채점). "
                "재채점하면 python scripts/page_score_extract.py 를 다시 돌린다. 손으로 고치지 않는다. "
                "pages = 채점 대상 / excluded = 화면이 아닌 것(리다이렉트 스텁·파일 부재)이라 점수를 "
                "일감으로 쓰지 않는다(2026-08-12 · GM 결정 '실무진이 실제로 쓰는 화면만').",
        "source": "3. 웰페리온 가이드/coo/chairman/GM업무.html #sec-erp-score",
        "count": len(scored),
        "excluded_count": len(excluded),
        "pages": scored,
        "excluded": excluded,
    }


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
    data = extract()
    if "--check" in sys.argv:
        print(f"{data['count']}건 · 최저 {data['pages'][0]['score']}% ({data['pages'][0]['name']})")
        return
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {OUT.relative_to(_REPO)} — {data['count']}건")


if __name__ == "__main__":
    main()
