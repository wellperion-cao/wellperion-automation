# -*- coding: utf-8 -*-
"""
배276 회귀 점검 — 유효회원 탭 '휴대폰 번호' 칸에 앞자리 0 소실(숫자 자동변환) 행이 있는지 확인.
2026-08-01 시토: _memberActiveUpsert_ 신설 직후 appendRow가 "01063165386"을 숫자로 바꿔
앞자리 0을 지운 사고(정지원·최기원·박지윤 3건) 재발방지용 1회성 assert 체크.
휴대폰 010 번호는 정규화하면 항상 11자리 '010...'이어야 한다 — 10자리(0 소실)면 실패.
사용: python scripts/_cto_member_phone_format_check.py
"""
import re
import sys
import urllib.parse
import urllib.request
import json

SS_ID = "12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U"


def _gviz(sheet_name):
    q = "tqx=out:json&headers=1&sheet=" + urllib.parse.quote(sheet_name)
    url = f"https://docs.google.com/spreadsheets/d/{SS_ID}/gviz/tq?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        txt = r.read().decode("utf-8", errors="replace")
    m = re.search(r"setResponse\((.*)\);?\s*$", txt, re.S)
    return json.loads(m.group(1))


def check():
    data = _gviz("유효회원")
    rows = data["table"]["rows"]
    cols = [c.get("label") for c in data["table"]["cols"]]
    ph_i = cols.index("휴대폰 번호")
    nm_i = cols.index("회원명")
    bad = []
    for r in rows:
        c = r["c"]
        nm = c[nm_i]["v"] if nm_i < len(c) and c[nm_i] else ""
        raw = c[ph_i]["v"] if ph_i < len(c) and c[ph_i] else ""
        digits = re.sub(r"\D", "", str(raw or ""))
        # 010으로 시작하는 휴대폰은 정규화 시 항상 11자리. 10자리이면서 '1'로 시작하면
        # (010→10으로 변한 흔적) 앞자리 0 소실 의심 — 오탐 억제: 완전 공란·구내전화 등은 skip.
        if digits and len(digits) == 10 and digits.startswith("1"):
            bad.append((nm, raw))
    if bad:
        print(f"[FAIL] 앞자리 0 소실 의심 {len(bad)}건:")
        for nm, raw in bad:
            print(" -", nm, raw)
        sys.exit(1)
    print(f"[OK] 유효회원 {len(rows)}행 — 휴대폰 앞자리 0 소실 없음")


if __name__ == "__main__":
    check()
