# -*- coding: utf-8 -*-
"""지난달 확정 매출(2026-01~07)을 월간 보고 원장(status/monthly_report_ledger.json)에 굳힌다 — 배 12523 2단계.

왜 있나
    화면(매출회원현황보고.html)이 지난달 값을 볼 때마다 시트를 다시 읽는다. 이미 끝난 달은 안 변하니
    원장에 한 번 박아 두면 그 읽기를 끊을 수 있다. 이 스크립트는 그 값을 원장에 채우는 1회성 도구다.

원천 판정(추측 금지)
    화면이 지난달 값을 읽을 때 쓰는 것과 같은 경로 — 그 달 「매출 보고」 파일(daily_report_sheet 로
    fileId 를 찾음) 안의 sheet="31" 탭 J4(월 마감 누적). "31" 은 날짜(말일)가 아니라 파일마다 고정된
    탭 이름이다 — 화면 코드(fixPastMonths)도 모든 달에 sheet=31 을 그대로 쓰고, 30일짜리 달도 정상
    응답한다(2026-09-18 실측 확인).
    8월은 이미 닫혀 있다(원장 2026-08.sales.month=627,869,695 · GM 확정 2026-08-28). 이 경로로 8월
    J4 를 다시 읽어 원장 값과 1% 이내로 맞으면 "같은 정의"로 보고 1~7월을 옮긴다. 1% 를 넘으면
    BLOCKED. ★8월은 실측상 정확히는 안 맞는다(2026-09-18: 625,385,695 vs 627,869,695 · 차 0.4%) —
    원장 8월 값은 GM 확정(8/31 22:56) 스냅샷이고 보고 파일은 그 뒤 정정 입력이 몇 건 더 들어갈 수
    있어서다(team-lead 판정 2026-09-18). 그래서 정확히 같지 않고 "1% 이내"를 기준으로 둔다 — 8월
    자체는 GM 확정값이라 이 스크립트가 덮지 않는다(대조용 키 하나만 얹는다).

쓰는 법
    python scripts/seed_monthly_sales_ledger.py           # 원천 대조 → 1% 이내면 원장에 씀(idempotent)
    python scripts/seed_monthly_sales_ledger.py --selftest
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

LEDGER = os.path.join(REPO, "status", "monthly_report_ledger.json")
ERP_URL = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
GAS_URL = "https://script.google.com/macros/s/AKfycbznAmvB-2cWfZVVcTud7ZWwKej9JtiUCl7RF8rrID0L0ldAKSO7nI5wHdUEZPIQQwM/exec"
TOKEN = "wellperion-2026"
ANCHOR_MONTH = "2026-08"      # 이미 닫힌 달 — 원천 판정의 대조 기준
ANCHOR_TOLERANCE_PCT = 1.0    # 이 안이면 같은 정의로 본다(위 원천 판정 주석 참고)
SOURCE_NOTE = "보고 파일 sheet=31 J4 → 원장 굳힘 2026-09-18 시포 (시트 읽기 종료) · 정의 = 보고 파일 sheet=31 J4"
KST = timezone(timedelta(hours=9))


def _parse_krw(cell) -> int | None:
    if cell is None:
        return None
    digits = re.sub(r"[^0-9-]", "", str(cell))
    return int(digits) if digits not in ("", "-") else None


def fetch_month_j4(year: int, month: int) -> int | None:
    """그 달 보고 파일을 찾아 sheet=31 J4 를 읽는다. 파일·탭이 없으면 None(지어내지 않음)."""
    try:
        f_url = ERP_URL + f"?action=daily_report_sheet&year={year}&month={month}&cb=1"
        with urllib.request.urlopen(urllib.request.Request(f_url, headers={"User-Agent": "wellperion-seed-sales"}), timeout=40) as r:
            f = json.loads(r.read().decode("utf-8"))
        if not f.get("ok") or not f.get("fileId"):
            print(f"[경고] {year}-{month:02d} 보고 파일 없음 — {f.get('error')}")
            return None
        j_url = (GAS_URL + "?token=" + urllib.parse.quote(TOKEN) +
                 "&dump=1&sheet=31&range=J4:J4&file=" + urllib.parse.quote(f["fileId"]) + "&cb=1")
        with urllib.request.urlopen(urllib.request.Request(j_url, headers={"User-Agent": "wellperion-seed-sales"}), timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
        if not d.get("ok"):
            print(f"[경고] {year}-{month:02d} J4 읽기 실패 — {d.get('error')}")
            return None
        return _parse_krw((d.get("cells") or {}).get("J4"))
    except Exception as e:
        print(f"[경고] {year}-{month:02d} 조회 예외 — {e}")
        return None


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def seed(ledger_path: str = LEDGER) -> int:
    ledger = _load(ledger_path)
    months = ledger.get("months", {})
    anchor = ((months.get(ANCHOR_MONTH) or {}).get("sales") or {}).get("month")
    anchor_j4 = fetch_month_j4(2026, 8)

    if anchor is None or anchor_j4 is None:
        print(f"BLOCKED: 8월 대조값을 못 얻었다 — 원장={anchor} 보고파일 J4={anchor_j4}")
        return 1
    diff_pct = abs(anchor_j4 - anchor) / anchor * 100
    if diff_pct > ANCHOR_TOLERANCE_PCT:
        print(f"BLOCKED: 8월 차이가 {ANCHOR_TOLERANCE_PCT}% 를 넘는다 — "
              f"원장 {ANCHOR_MONTH}.sales.month={anchor} vs 보고파일 J4={anchor_j4} (차 {diff_pct:.2f}%)")
        return 1
    print(f"[대조 통과] 8월 원장={anchor} vs 보고파일 J4={anchor_j4} (차 {diff_pct:.2f}% ≤ {ANCHOR_TOLERANCE_PCT}%)")

    try:
        from safe_commit import refuse_if_older_than_head
        if not refuse_if_older_than_head(ledger_path):
            print("BLOCKED: 낡은 판정 — 원장 사본이 HEAD 보다 뒤처져 있다")
            return 1
    except Exception as e:
        print(f"[경고] 낡은판 검사 불가({e}) — 계속 진행")

    added, skipped = [], []
    for m in range(1, 8):
        label = f"2026-{m:02d}"
        cur = months.get(label)
        if cur is not None:
            skipped.append(label)
            continue
        value = fetch_month_j4(2026, m)
        if value is None:
            print(f"[경고] {label} 값을 못 읽었다 — 이 달은 건너뛴다(0으로 채우지 않음)", file=sys.stderr)
            continue
        months[label] = {"closed": True, "sales": {"month": value}, "source": SOURCE_NOTE}
        added.append(label)

    # 8월은 GM 확정값 — 덮지 않고 대조용 키 하나만 얹는다(이미 있으면 다시 안 씀).
    key = "sheet_j4_" + datetime.now(KST).strftime("%Y_%m_%d")
    aug = months.setdefault(ANCHOR_MONTH, {})
    if key not in aug:
        aug[key] = anchor_j4
        added.append(f"{ANCHOR_MONTH}.{key}")
    elif aug[key] != anchor_j4:
        print(f"[경고] {ANCHOR_MONTH}.{key} 이미 있는데 값이 다르다({aug[key]} vs {anchor_j4}) — 덮지 않음", file=sys.stderr)

    if added:
        ledger["months"] = months
        _write(ledger_path, ledger)
    print(f"DONE: 추가={added} 건너뜀(이미 있음)={skipped}")
    return 0


def _selftest():
    import tempfile
    assert _parse_krw(" ₩ 625,385,695 ") == 625385695
    assert _parse_krw(None) is None
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ledger.json")
        _write(p, {"months": {"2026-08": {"sales": {"month": 100}}}})
        d = _load(p)
        assert d["months"]["2026-08"]["sales"]["month"] == 100
    print("[selftest] OK — 금액 파싱·임시파일 쓰기·읽기 정상")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    sys.exit(seed())
