# -*- coding: utf-8 -*-
"""배724 사후 검증 — 미등록사유 5건 현재값 재실측 (읽기 전용)."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpo_report as C

TARGETS = {
    187: ("정민정",   "휴회불만"),
    191: ("염현경",   "바쁜일정"),
    194: ("유지훈",   "시설불만"),
    195: ("박보경",   "휴회불만"),
    201: ("김현수1",  "시설불만"),
}

def col(r, *names):
    for n in names:
        if n in r: return r[n]
    return ""

rows = C.fetch_active_members("ended") or []
idx = {int(col(r,"rowIndex")): r for r in rows if col(r,"rowIndex")}

ok, fail = 0, 0
for rowno, (name, expected) in sorted(TARGETS.items()):
    r = idx.get(rowno)
    if r is None:
        print(f"  ❌ row{rowno} {name}: 행 없음")
        fail += 1
        continue
    actual = str(col(r,"미등록사유") or "").strip()
    match = (actual == expected)
    ok   += match
    fail += not match
    mark = "✅" if match else "❌"
    print(f"  {mark} row{rowno} {name}: 기대={expected!r} 실제={actual!r}")

print(f"\n결과: {ok}/5 정상 · {fail}건 불일치")
sys.exit(0 if fail == 0 else 1)
