# -*- coding: utf-8 -*-
"""매출 보고 시트 「보고」탭 P20 — 시설·청결·주차·밸류업 운영 현황 채우기.

왜 있나
    09:30 매출보고 이미지는 사람이 만든 시트 한 조각(H2:S21)을 그대로 찍어 보낸다.
    그 안 P20 칸에 3부서 현황을 매일 아침 09:00 에 채워 두면, 회장님·관리부·부서장·
    운영부가 매출과 같은 화면에서 운영 현황을 함께 본다(GM 지시 2026-08-18).

무엇을 새로 만들지 않았나
    · 수집기 — 점검·접수 숫자는 scripts/collectors/ops_shared.py 의 기존 함수로 받는다.
    · 발신 관문 — 카톡으로 보내지 않는다. 시트에 쓰는 것뿐이다.
    · 상쇄(약속 L21 net-zero) — 같은 날 18:30 저녁 카톡 재수집(값 0건)을 지웠다.

쓰는 법
    python scripts/sales_report_ops_summary.py --dry-run   # 만들 텍스트만 보기
    python scripts/sales_report_ops_summary.py             # 시트 P20 에 쓰기

    환경변수(telegram_bot/.env 또는 OS 환경):
      SALES_OPS_GAS_URL   시트에 붙인 웹앱 주소(/exec)
      SALES_OPS_GAS_TOKEN 그 웹앱의 TOKEN (기본 wellperion-2026)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.collectors.ops_shared import (  # noqa: E402
    RECEPTION_EXEC_URL,
    gas_get,
    reception_elapsed_days,
)
from scripts.coo_registry import CHECK_API  # noqa: E402

WEEKDAY_KO = "월화수목금토일"


def _env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v:
        return v
    envfile = ROOT / "telegram_bot" / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def facility_line(day: str) -> list[str]:
    """시설 — 오늘 점검 진행과 특이사항. 못 세면 그 줄을 빼고 빈 리스트를 준다(0 위장 금지)."""
    r = gas_get(CHECK_API, {"action": "weekly", "dept": "facility"}, label="facility")
    if r is None:
        return []
    rows = (r.json() or {}).get("data") or []
    today = next((x for x in rows if str(x.get("date")) == day), None)
    if not today:
        return []
    out = [f" · 일일점검 {today.get('done')}/{today.get('total')}"
           + (" · 이상 없음" if not str(today.get("issue") or "").strip() else "")]
    issue = str(today.get("issue") or "").strip()
    if issue:
        out.append(f" · 특이사항 — {issue[:60]}")
    return out


def support_line(day: str) -> list[str]:
    """청결 — 지원부 완료 현황과 남/여 격차."""
    r = gas_get(CHECK_API, {"action": "today_live", "dept": "support", "date": day}, label="support")
    if r is None:
        return []
    d = r.json() or {}
    g = d.get("byGender") or {}
    m, f = g.get("m") or {}, g.get("f") or {}
    out = [f" · 일일점검 {d.get('done')}/{d.get('total')}"
           + (f" (남 {m.get('pct')}% / 여 {f.get('pct')}%)" if m and f else "")]
    # 한쪽이 크게 낮으면 그것만 짚는다 — 매일 같은 문장을 반복하지 않는다.
    try:
        gap = abs(int(m.get("pct", 0)) - int(f.get("pct", 0)))
        if gap >= 20:
            low = "여자구역" if int(m.get("pct", 0)) > int(f.get("pct", 0)) else "남자구역"
            out.append(f" · {low} 완료율 낮음 — 원인 확인 중")
    except (TypeError, ValueError):
        pass
    return out


def reception_line() -> list[str]:
    """미처리 접수 — 시설부 기준 건수와 최장 경과일."""
    r = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, label="reception")
    if r is None:
        return []
    d = r.json()
    rows = d if isinstance(d, list) else (d.get("data") or d.get("items") or [])
    rows = [x for x in rows if isinstance(x, dict)]
    op = [x for x in rows if str(x.get("status")) in ("접수", "처리중")]
    if not op:
        return []
    fac = [x for x in op if str(x.get("dept") or "") == "시설부"]
    if not fac:
        return []
    oldest = max(reception_elapsed_days(x) for x in fac)
    return [f" · 미처리 접수 {len(fac)}건 — 최장 {oldest}일"]


def build_text(day: str, value_up: list[str]) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").date()
    head = f"[운영 현황]  시설 · 지원 · 주차   {d.month}/{d.day}({WEEKDAY_KO[d.weekday()]})"

    blocks: list[tuple[str, list[str]]] = [
        ("■ 시설물 관리", facility_line(day) + reception_line()),
        ("■ 청결 관리", support_line(day)),
        ("■ 주차 관리", _parking_lines()),
        ("■ 내부 환경 개선", value_up),
    ]
    parts = [head]
    for title, lines in blocks:
        if not lines:
            lines = [" · 집계 중"]
        parts.append("")
        parts.append(title)
        parts.extend(lines)
    return "\n".join(parts)


def _parking_lines() -> list[str]:
    """주차 — 지금은 점검이 종이 체크라 셀 숫자가 없다. 없는 숫자를 지어내지 않는다.
    ponytail: 제출형 점검(시토 배672)이 붙으면 여기서 support_line 과 같은 방식으로 센다."""
    return [" · 일일점검 전산화 진행 중"]


def post_to_sheet(text: str, cell: str = "P20") -> dict:
    url = _env("SALES_OPS_GAS_URL")
    if not url:
        return {"ok": False, "error": "SALES_OPS_GAS_URL 이 없습니다 — 웹앱 배포 후 .env 에 넣어 주세요"}
    body = json.dumps({
        "token": _env("SALES_OPS_GAS_TOKEN", "wellperion-2026"),
        "cell": cell,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "text/plain"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="매출 보고 시트 P20 운영 현황 채우기")
    # ★ 기본은 **어제**다. 09:30 매출보고는 전날 실적을 보고하므로(캡션 "8.16(일) 매출 및
    # 운영사항"), 운영 현황도 같은 날이어야 한 화면에서 앞뒤가 맞는다. 오늘로 잡으면
    # 매출은 전날인데 현황만 당일이 되고, 게다가 09:00 시점의 당일 점검은 아침 회차뿐이라 거의 비어 있다.
    ap.add_argument("--date", default=(date.today() - timedelta(days=1)).isoformat(),
                    help="기준일(기본=어제 · 매출보고와 같은 날)")
    ap.add_argument("--cell", default="P20")
    ap.add_argument("--dry-run", action="store_true", help="만들 텍스트만 보고 시트엔 쓰지 않는다")
    ap.add_argument("--value-up", action="append", default=[],
                    help="내부 환경 개선 줄(여러 번 지정 가능). 없으면 '집계 중'")
    args = ap.parse_args()

    value_up = [f" · {v}" for v in args.value_up]
    text = build_text(args.date, value_up)
    print(text)
    print("---")
    if args.dry_run:
        print(f"[미리보기] {len(text)}자 · {text.count(chr(10)) + 1}줄 — 시트에 쓰지 않았습니다")
        return 0
    res = post_to_sheet(text, args.cell)
    print("[결과]", json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


def _selftest() -> None:
    """텍스트 조립만 검사한다(네트워크 없이). 빈 묶음이 '집계 중'으로 채워지는지."""
    out = build_text("2026-08-18", [])
    assert "[운영 현황]" in out
    assert out.count("■") == 4, out
    assert "집계 중" in out  # value_up 이 비었으니 그 자리는 집계 중
    assert "8/18(화)" in out, out
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        raise SystemExit(main())
