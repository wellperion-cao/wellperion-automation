# -*- coding: utf-8 -*-
"""브로제이 이관 누락 감시 (배908 · 시포 2026-09-09).

지금 실제 결제·승인은 스포피아에서 나고, 마감 때 사람이 그 내역을 브로제이로 손으로 옮긴다
(운영부 이경연 실장 확인 2026-09-09). 브로제이 실결제는 2026-10-01 부터다. 그래서 이 스크립트가 세는
차이는 **틀린 값이 아니라 「아직 안 옮긴 값」**이다 — 보고 문구를 그렇게 갈라야 재촉으로 읽히지 않는다.

무엇을 대조하나
  시트 쪽   보고 시트 일자탭(build_report 가 읽는 그 값 · api_report.build_report)
  브로제이  서버 적재분(brojay_records · sync_brojay 가 하루 3회 담는다)
  기준일    기본 = 어제(KST)

무엇을 세나
  ① 총액   시트 I4  vs  브로제이 결제 합
  ② 팀별   시트 칸(수영·P.T·골프·스쿼시·체조·P.L·뮤지컬·GXE) vs 브로제이 매출분류(sales_tag_name) 합
  칸↔분류 이름이 다르면 짝을 못 짓는다 — 못 지은 것은 지어내지 않고 'unmapped' 로 남긴다.

결과: /srv/erp/status/brojay_transfer_gap.json  (한 줄 요약 stdout)
실행: python3 /srv/erp/api/brojay_transfer_gap.py [YYYY-MM-DD]
자체점검: python3 brojay_transfer_gap.py --selftest   (네트워크·DB 없음 — 금액 파싱·판정만)
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
BASE = "http://127.0.0.1:8001"
OUT = os.environ.get("ERP_STATUS_DIR", "/srv/erp/status") + "/brojay_transfer_gap.json"

# 시트 칸 → 브로제이 매출분류(sales_tag_name). 실측으로 확인된 짝만 적는다(2026-09-08 대조).
# 회원권(I6)·옵션(I7)은 분류 하나에 대응하지 않는다(운영부 태그에 락커가 섞인다) — 총액으로만 본다.
CELL_TAG = {
    "I8": "수영", "I9": "PT", "I12": "체조&트램폴린", "I13": "필라테스",
}
CELL_LABEL = {"I4": "총 매출", "I6": "회원권", "I7": "옵션", "I8": "수영", "I9": "P.T", "I10": "골프",
              "I11": "스쿼시", "I12": "체조", "I13": "P.L", "I14": "뮤지컬", "I15": "GXE"}


def won(v):
    """시트 칸 문자열 → 정수 원. '- 130,000'(앞 대시 = 음수) · ' - '(빈칸) 을 가른다."""
    s = str(v if v is not None else "").strip()
    if not s or s in ("-", "–", "—"):
        return 0
    neg = s.startswith("-")
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        return 0
    return -int(digits) if neg else int(digits)


def _title_day(h2, want):
    """보고 제목(「📅 26년 9월 8일 매출 및 운영사항 보고」)에서 그 시트가 스스로 말하는 날짜를 읽는다.
    연도는 두 자리라 물어본 날짜의 세기를 빌려 쓴다. 못 읽으면 None — 못 읽은 것을 일치로 치지 않는다."""
    m = re.search(r"(\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일", str(h2 or ""))
    if not m:
        return None
    yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    century = int(str(want)[:2]) * 100 if len(str(want)) >= 4 else 2000
    try:
        return date(century + yy, mm, dd).isoformat()
    except ValueError:
        return None


def _get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=60).read().decode("utf-8"))


def check(day):
    rep = _get("/api/report/sales_report_cells?date=%s" % day) or {}
    # 일자탭이 아직 안 채워진 날을 부르면 렌더러가 어제 값을 그대로 돌려준다 — 그 값으로 대조하면
    # 남의 날 매출을 '안 옮긴 금액'으로 세게 된다(2026-09-09 실측).
    # ★ref_date 는 못 믿는다 — 물어본 날짜를 그대로 되돌려준다(09-09 를 물으면 ref_date 도 09-09 인데
    #   칸 내용은 09-08 이었다). 시트가 스스로 적은 제목(H2 「26년 9월 8일 …」)의 날짜가 진짜다.
    sheet_day = _title_day((rep.get("cells") or {}).get("H2"), day)
    if sheet_day != day:
        return {"date": day, "checked_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
                "skipped": "시트 일자탭이 아직 그 날짜가 아님(시트 제목 기준 %s)" % (sheet_day or "읽지 못함"),
                "sheet_total": None, "brojay_total": None, "total_diff": None,
                "rows": None, "by_tag": {}, "gaps": [], "unmapped_with_value": []}
    cells = rep.get("cells") or {}
    raw = (_get("/api/brojay/sales?date=%s" % day) or {}).get("data")
    rows = raw.get("data") if isinstance(raw, dict) else raw
    rows = [r for r in (rows or []) if isinstance(r, dict)]

    by_tag = {}
    for r in rows:
        t = str(r.get("sales_tag_name") or "(분류없음)")
        by_tag[t] = by_tag.get(t, 0) + int(r.get("total_payment_price") or 0)
    broj_total = sum(by_tag.values())
    sheet_total = won(cells.get("I4"))

    gaps = []
    for cell, tag in CELL_TAG.items():
        diff = won(cells.get(cell)) - by_tag.get(tag, 0)
        if diff:
            gaps.append({"cell": cell, "label": CELL_LABEL.get(cell, cell), "tag": tag,
                         "sheet": won(cells.get(cell)), "brojay": by_tag.get(tag, 0), "diff": diff})
    # 짝을 못 지은 시트 칸 중 값이 있는 것 — 브로제이에 그 분류 자체가 없다는 뜻일 수 있다
    unmapped = [{"cell": c, "label": CELL_LABEL.get(c, c), "sheet": won(cells.get(c))}
                for c in ("I10", "I11", "I14", "I15") if won(cells.get(c))]
    out = {
        "date": day, "checked_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "sheet_total": sheet_total, "brojay_total": broj_total, "total_diff": sheet_total - broj_total,
        "rows": len(rows), "by_tag": by_tag, "gaps": gaps, "unmapped_with_value": unmapped,
        "meaning": "차이는 '틀림'이 아니라 '아직 브로제이로 안 옮김' (실결제 원천=스포피아 · 브로제이 실결제 2026-10-01 시작)",
    }
    return out


def line(o):
    if o.get("skipped"):
        return "%s 대조 못 함 — %s" % (o["date"], o["skipped"])
    if o["total_diff"] == 0 and not o["gaps"] and not o["unmapped_with_value"]:
        return "%s 이관 누락 없음" % o["date"]
    names = [g["label"] for g in o["gaps"]] + [u["label"] for u in o["unmapped_with_value"]]
    return "%s 아직 브로제이에 안 넘어간 금액 %s원 — %s" % (
        o["date"], format(o["total_diff"], ","), " · ".join(names) or "분류 미상")


def selftest():
    assert won("  18,108,480 ") == 18108480
    assert won("- 130,000 ") == -130000        # 시트는 환불을 앞 대시로 적는다
    assert won(" - ") == 0 and won("") == 0 and won(None) == 0
    assert won("653,480") == 653480
    o = {"date": "2026-09-08", "total_diff": 0, "gaps": [], "unmapped_with_value": []}
    assert line(o).endswith("이관 누락 없음")
    o2 = {"date": "2026-09-08", "total_diff": 1208480, "gaps": [{"label": "체조"}],
          "unmapped_with_value": [{"label": "스쿼시"}]}
    assert "1,208,480원" in line(o2) and "체조 · 스쿼시" in line(o2)
    assert "대조 못 함" in line({"date": "2026-09-09", "skipped": "시트 일자탭이 아직 그 날짜가 아님(시트 제목 기준 2026-09-08)"})
    assert _title_day("📅 26년 9월 8일 매출 및 운영사항 보고", "2026-09-09") == "2026-09-08"
    assert _title_day("📅 26년 9월 9일 매출 및 운영사항 보고", "2026-09-09") == "2026-09-09"
    assert _title_day("", "2026-09-09") is None and _title_day("26년 13월 40일", "2026-09-09") is None
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    day = args[0] if args else (datetime.now(KST).date() - timedelta(days=1)).isoformat()
    result = check(day)
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("[warn] 결과 파일 못 씀: %s" % e)
    print(line(result))
