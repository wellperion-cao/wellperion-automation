# -*- coding: utf-8 -*-
"""
배(2026-08-04, 대기→멤버십 자동전환) 드라이런 — 실제 쓰기 없이 라이브 유효회원 시트를 읽어
Survey.js의 member_wait_auto_release_()/_memberWaitReleaseCols_와 동일 판정을 재현한다.
GAS 배포·시트 쓰기 없음(clasp 인증 죽어있음) — gviz 공개 조회만(기존 _cto_member_phone_format_check.py
와 동일 패턴 재사용, 신규 인증경로 안 만듦).
판정: '분류' 든 칸 중 값이 정확히 '대기'이고 시작일자<=오늘이면 그 칸이 대상.
     시작일자 없음/파싱불가/미도래는 건드리지 않음(None).
실측 기준(GM 확인) 오늘 실행 시 대상 0건이 정답 — 12건 전부 시작일자가 미래(가장 이른 2026-08-10).
사용: python scripts/_cto_member_wait_auto_release_dryrun.py
"""
import re
import sys
import json
import urllib.parse
import urllib.request
from datetime import date

SS_ID = "12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U"
SHEET = "유효회원"


def _gviz(sheet_name):
    q = "tqx=out:json&headers=1&sheet=" + urllib.parse.quote(sheet_name)
    url = f"https://docs.google.com/spreadsheets/d/{SS_ID}/gviz/tq?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        txt = r.read().decode("utf-8", errors="replace")
    m = re.search(r"setResponse\((.*)\);?\s*$", txt, re.S)
    return json.loads(m.group(1))


def _strip(s):
    return re.sub(r"\s+", "", str(s or ""))


def _mi_to_iso(v):
    # Survey.js _miToISO_ 재현 — 느슨 파싱, 실패 시 ''.
    if v is None or v == "":
        return ""
    s = str(v).strip()
    m = re.match(r"(\d{4})[.\-/]?\s*(\d{1,2})[.\-/]?\s*(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s  # 파싱 실패해도 원문 반환(Survey.js와 동일) — 아래서 날짜형식 아니면 미도래 취급


def _looks_like_date(s):
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", s or ""))


def dryrun():
    data = _gviz(SHEET)
    cols = [c.get("label") or "" for c in data["table"]["cols"]]
    rows = data["table"]["rows"]
    today = date.today().isoformat()

    class_idx = [i for i, c in enumerate(cols) if "분류" in _strip(c)]
    start_idx = next((i for i, c in enumerate(cols) if "시작일자" in _strip(c)), -1)

    if not class_idx or start_idx < 0:
        print(f"[FAIL] '분류' 또는 '시작일자' 칸 미발견 (cols={cols})")
        sys.exit(1)

    checked = 0
    targets = []
    for ridx, r in enumerate(rows):
        c = r["c"]
        raw_start = c[start_idx]["v"] if start_idx < len(c) and c[start_idx] else None
        start_iso = _mi_to_iso(raw_start)
        if not start_iso or not _looks_like_date(start_iso) or start_iso > today:
            continue
        checked += 1
        for ci in class_idx:
            val = str(c[ci]["v"]).strip() if ci < len(c) and c[ci] and c[ci].get("v") is not None else ""
            if val == "대기":
                targets.append((ridx + 2, cols[ci], val))

    print(f"유효회원 {len(rows)}행 · 오늘={today}")
    print(f"시작일자 도래(<=오늘) 행: {checked}건")
    print(f"대기→비움 대상 칸: {len(targets)}건")
    for row, colname, val in targets:
        print(f"  - row={row} col={colname!r} before={val!r} -> ''")

    if checked == 0 and len(targets) == 0:
        print("[OK] 실측 기대치(0건)와 일치")
    elif len(targets) == 0:
        print("[OK] 대상 0건(도래 행은 있으나 '대기' 없음)")
    else:
        print("[INFO] 대상 존재 — 배포 후 실제 반영 시 위 칸들이 비워짐")


if __name__ == "__main__":
    dryrun()
