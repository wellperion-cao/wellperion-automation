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

사용:  python scripts/page_score_extract.py [--check]
       --check 는 파일을 쓰지 않고 몇 건 잡히는지만 낸다.
"""
from __future__ import annotations

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
    pages.sort(key=lambda p: p["score"])
    return {
        "_doc": "ERP 화면 완성도 채점 — 생성물. 원천 = GM업무.html #sec-erp-score(웰리 배465 재채점). "
                "재채점하면 python scripts/page_score_extract.py 를 다시 돌린다. 손으로 고치지 않는다.",
        "source": "3. 웰페리온 가이드/coo/chairman/GM업무.html #sec-erp-score",
        "count": len(pages),
        "pages": pages,
    }


def main() -> None:
    data = extract()
    if "--check" in sys.argv:
        print(f"{data['count']}건 · 최저 {data['pages'][0]['score']}% ({data['pages'][0]['name']})")
        return
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] {OUT.relative_to(_REPO)} — {data['count']}건")


if __name__ == "__main__":
    main()
