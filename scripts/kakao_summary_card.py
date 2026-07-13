#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/kakao_summary_card.py — 카카오톡 아침 요약 카드 이미지 생성기

배경(2026-07-13 GM 승인): 매출 상세표(generate_sales_report_image.py)와 별개로,
매출·점검·전환·주차 4지표를 한 장에 담는 세로형 "아침 요약 카드"를 생성한다.
데이터는 전부 이미 라이브 집계된 SSOT를 읽기만 한다(신규 수집 금지):
  - status/kpi_values.json  → roles.cfo(매출) / roles.coo(점검) / roles.cpo(전환)
  - status/parking_revenue.json → 주차 매출(일별 포함)

정직 원칙(절대): 소스 json에 값이 없거나 null이면 숫자를 지어내지 않고 "측정 불가"로
표기한다. 매출은 최근 마감월 실적이므로 라벨에 "N월 마감"을 반드시 밝힌다.

경보 엔진(오탐 금지 — 확실한 것만):
  - 지원부 점검 완료율 < 95% → ⚠️ 경보
  - 매출 달성률 < 90% → ⚠️ 경보
  - 경보 0건이면 🟢 "오늘 특이사항 없음" 배너
  - 주차 급락 경보는 이번 배치에서 보류(0원=미수집일 오탐 위험)

렌더링: 코드로 그리지 않고 HTML 템플릿을 채워 Playwright로 스크린샷한다.
브라우저 실행은 generate_sales_report_image.py의 _launch_context(p)를 그대로
재사용한다(profiles/danggn 퍼시스턴트 크롬 프로필, channel=chrome→chromium 폴백).

**중요: 이 스크립트는 이미지 생성까지만 담당한다. 카카오톡 발송에는 일절 관여하지
않는다.** kakao_auto_daily_report.py·kakao_report_sender.py 등 발송 파이프라인은
이 스크립트가 존재해도 자동으로 바뀌지 않는다(발송 통합은 GM 승인 후 별도 작업).

사용:
    python scripts/kakao_summary_card.py                     # 오늘 날짜 기준
    python scripts/kakao_summary_card.py --date 20260713      # 특정 날짜로 저장
    python scripts/kakao_summary_card.py --out C:\\...\\x.png   # 추가 저장

출력: 성공 시 stdout에 `IMAGE: <절대경로>` + exit 0. 실패 시 `FAILED: <이유>` + exit 1.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_sales_report_image as sales_img  # noqa: E402  _launch_context(p) 재사용

KPI_PATH = ROOT / "status" / "kpi_values.json"
PARKING_PATH = ROOT / "status" / "parking_revenue.json"
OUT_DIR = ROOT / "tmp" / "kakao_summary_card"
FILENAME_FMT = "웰페리온_아침요약_%Y%m%d.png"

WEEKDAY_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
MISSING = "측정 불가"

# ══════════════════════════════════════════════════════════════════════════
# 디자인 시안(kakao_summary_card.html) CSS 원본 그대로 — 룩 재현. legend/frame-label/
# script 데모 요소는 뺀다(그건 GM 설명용이었음). .banner.ok 만 경보-0건 상태용으로 추가.
# ══════════════════════════════════════════════════════════════════════════
STYLE_CSS = """
:root{
  --bg:#EEF1F5; --card:#FBFCFD; --ink:#1A2230; --dim:#5C6675; --line:#DCE2EA;
  --tile:#F4F6F9; --gold:#B8892E; --goldbg:#F7EEDA; --blue:#35618E;
  --good:#2E8F63; --goodbg:#E4F2EA; --warn:#C77A1E; --warnbg:#FBEEDA;
  --crit:#C4472F; --shadow:0 10px 34px rgba(26,34,48,.12);
}
:root[data-theme="light"]{
  --bg:#EEF1F5; --card:#FBFCFD; --ink:#1A2230; --dim:#5C6675; --line:#DCE2EA;
  --tile:#F4F6F9; --gold:#B8892E; --goldbg:#F7EEDA; --blue:#35618E;
  --good:#2E8F63; --goodbg:#E4F2EA; --warn:#C77A1E; --warnbg:#FBEEDA;
  --crit:#C4472F; --shadow:0 10px 34px rgba(26,34,48,.12);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased; line-height:1.45;
}
.card{
  width:100%; max-width:430px; background:var(--card); border:1px solid var(--line);
  border-radius:20px; box-shadow:var(--shadow); overflow:hidden;
}
.pad{padding:20px 20px 22px}

header.top{display:flex; align-items:center; justify-content:space-between; padding:18px 20px 14px}
.brand{display:flex; align-items:center; gap:9px}
.mark{width:30px; height:30px; border-radius:8px; background:linear-gradient(135deg,#3B6EA5,#2C4E74);
  display:grid; place-items:center; color:#fff; font-weight:800; font-size:15px; letter-spacing:-.03em}
.brand .t1{font-weight:800; font-size:15px; letter-spacing:-.01em}
.brand .t2{font-size:11.5px; color:var(--dim); margin-top:1px}
.date{text-align:right}
.date .d1{font-weight:800; font-size:15px; font-variant-numeric:tabular-nums}
.date .d2{font-size:11px; color:var(--dim)}

.banner{display:flex; align-items:flex-start; gap:10px; margin:0 20px; padding:12px 14px;
  border-radius:13px; background:var(--warnbg); border:1px solid color-mix(in srgb,var(--warn) 32%,transparent)}
.banner.ok{background:var(--goodbg); border-color:color-mix(in srgb,var(--good) 32%,transparent)}
.banner .ic{font-size:17px; line-height:1.2}
.banner .b1{font-weight:800; font-size:13.5px; color:var(--warn)}
.banner.ok .b1{color:var(--good)}
.banner .b2{font-size:12.5px; color:var(--ink); margin-top:2px}
.banner .b2 b{font-variant-numeric:tabular-nums}

.grid{display:grid; grid-template-columns:1fr 1fr; gap:11px; margin-top:16px}
.tile{background:var(--tile); border:1px solid var(--line); border-radius:14px; padding:13px 14px}
.tile .lab{font-size:11.5px; color:var(--dim); font-weight:700; letter-spacing:.01em; display:flex; align-items:center; gap:5px}
.tile .big{font-size:23px; font-weight:800; letter-spacing:-.02em; margin-top:5px; font-variant-numeric:tabular-nums}
.tile .sub{font-size:11.5px; color:var(--dim); margin-top:2px; font-variant-numeric:tabular-nums}
.dot{width:7px; height:7px; border-radius:50%; display:inline-block; background:var(--dim)}
.dot.good{background:var(--good)} .dot.warn{background:var(--warn)}
.pill{font-size:10.5px; font-weight:800; padding:1px 7px; border-radius:999px}
.pill.good{color:var(--good); background:var(--goodbg)}
.pill.warn{color:var(--warn); background:var(--warnbg)}
.tile.sales .big{color:var(--gold)}
.tile.sales{background:var(--goldbg); border-color:color-mix(in srgb,var(--gold) 30%,transparent)}
.gauge{height:6px; border-radius:999px; background:color-mix(in srgb,var(--gold) 22%,transparent); margin-top:9px; overflow:hidden}
.gauge > i{display:block; height:100%; background:var(--gold); border-radius:999px}
.arrow{font-weight:800}
.arrow.up{color:var(--good)} .arrow.down{color:var(--crit)}

.chart-wrap{margin-top:15px; background:var(--tile); border:1px solid var(--line); border-radius:14px; padding:13px 14px 11px}
.chart-head{display:flex; align-items:baseline; justify-content:space-between}
.chart-head .ct{font-size:11.5px; font-weight:700; color:var(--dim)}
.chart-head .cv{font-size:12px; font-weight:800; font-variant-numeric:tabular-nums}
.bars{display:flex; align-items:flex-end; gap:4px; height:56px; margin-top:11px}
.bars .col{flex:1; display:flex; flex-direction:column; justify-content:flex-end; gap:4px; height:100%}
.bars .bar{width:100%; border-radius:3px 3px 2px 2px; background:var(--blue); opacity:.55}
.bars .bar.max{opacity:1}
.bars .bar.zero{background:var(--line); height:2px !important; opacity:1}
.bars .lbl{font-size:8.5px; color:var(--dim); text-align:center; font-variant-numeric:tabular-nums}

footer.foot{padding:13px 20px 18px; border-top:1px solid var(--line); margin-top:16px}
.foot .frow{display:flex; align-items:center; gap:7px; font-size:10.8px; color:var(--dim)}
.foot .frow + .frow{margin-top:4px}
.foot b{color:var(--ink)}
.tag{font-size:9.5px; font-weight:800; letter-spacing:.03em; color:var(--blue);
  border:1px solid color-mix(in srgb,var(--blue) 40%,transparent); padding:1px 6px; border-radius:6px}
"""

PAGE_TEMPLATE = """<!doctype html>
<html data-theme="light">
<head>
<meta charset="utf-8">
<title>웰페리온 아침 요약 카드</title>
<style>
{style}
</style>
</head>
<body style="display:flex; justify-content:center; padding:24px 16px;">
{card}
</body>
</html>"""


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_json(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"{path.name} 없음({path})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{path.name} 읽기 실패: {exc}")


def dround(value: float, ndigits: int) -> Decimal:
    """소스 float를 절사 없이 정직 반올림(ROUND_HALF_UP, Decimal 기반)."""
    q = Decimal(1).scaleb(-ndigits)
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def fmt_eok(value) -> str:
    return f"{dround(value / 1e8, 2)}억"


def fmt_man(value) -> str:
    return f"{dround(value / 10000, 1)}만"


def fmt_num(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def fmt_comma(value) -> str:
    return f"{value:,}" if isinstance(value, (int, float)) else MISSING


def extract_month(label: str) -> "int | None":
    m = re.match(r"(\d{4})-(\d{2})", label or "")
    return int(m.group(2)) if m else None


# ══════════════════════════════════════════════════════════════════════════
# 경보 엔진
# ══════════════════════════════════════════════════════════════════════════
def compute_alerts(kpi: dict) -> list:
    alerts = []
    roles = kpi.get("roles", {})
    coo = roles.get("coo", {})
    cfo = roles.get("cfo", {})

    insp_rate = coo.get("지원부_점검완료율")
    if isinstance(insp_rate, (int, float)) and insp_rate < 0.95:
        pct = dround(insp_rate * 100, 0)
        month = extract_month(coo.get("지원부_점검완료율_기준", ""))
        month_label = f"{month}월 누적" if month else "이번달 누적"
        alerts.append(f"지원부 점검 완료율 {pct}% — 목표 95% 미달 ({month_label})")

    sales = cfo.get("sales_month")
    target = cfo.get("sales_month_target")
    if isinstance(sales, (int, float)) and isinstance(target, (int, float)) and target:
        rate = sales / target * 100
        if rate < 90:
            alerts.append(f"매출 달성률 {dround(rate, 0)}% (목표 미달)")

    return alerts


def build_banner(alerts: list) -> str:
    if not alerts:
        return (
            '<div class="banner ok">'
            '<div class="ic">🟢</div>'
            '<div><div class="b1">오늘 특이사항 없음</div></div>'
            '</div>'
        )
    head = "오늘 주의 1건" if len(alerts) == 1 else f"오늘 주의 {len(alerts)}건"
    extra = "".join(f'<div class="b2">{html_mod.escape(a)}</div>' for a in alerts[1:])
    return (
        '<div class="banner">'
        '<div class="ic">⚠️</div>'
        '<div>'
        f'<div class="b1">{html_mod.escape(head)}</div>'
        f'<div class="b2">{html_mod.escape(alerts[0])}</div>'
        f'{extra}'
        '</div>'
        '</div>'
    )


# ══════════════════════════════════════════════════════════════════════════
# 지표 타일
# ══════════════════════════════════════════════════════════════════════════
def tile_sales(cfo: dict) -> str:
    sales = cfo.get("sales_month")
    target = cfo.get("sales_month_target")
    month = extract_month(cfo.get("sales_month_label", ""))
    month_txt = f"{month}월 마감" if month else "마감월 불명"

    if not isinstance(sales, (int, float)) or not isinstance(target, (int, float)) or not target:
        return (
            '<div class="tile sales">'
            '<div class="lab">💰 매출</div>'
            f'<div class="big">{MISSING}</div>'
            f'<div class="sub">{month_txt}</div>'
            '</div>'
        )

    rate = sales / target * 100
    rate_i = dround(rate, 0)
    pill_cls = "good" if rate_i >= 100 else "warn"
    gauge_w = min(100, max(0, int(rate_i)))
    return (
        '<div class="tile sales">'
        f'<div class="lab">💰 매출 <span class="pill {pill_cls}">{rate_i}%</span></div>'
        f'<div class="big">{fmt_eok(sales)}</div>'
        f'<div class="sub">목표 {fmt_eok(target)} · {month_txt}</div>'
        f'<div class="gauge"><i style="width:{gauge_w}%"></i></div>'
        '</div>'
    )


def tile_inspection(coo: dict) -> str:
    rate = coo.get("지원부_점검완료율")
    done = coo.get("지원부_완료")
    total = coo.get("지원부_전체")

    if not isinstance(rate, (int, float)):
        return (
            '<div class="tile">'
            '<div class="lab"><span class="dot"></span> 점검 완료율</div>'
            f'<div class="big">{MISSING}</div>'
            '<div class="sub">데이터 없음</div>'
            '</div>'
        )

    pct = dround(rate * 100, 0)
    warn = rate < 0.95
    dot_cls = "warn" if warn else "good"
    arrow = '<span class="arrow down" style="font-size:14px"> ▼</span>' if warn else ""
    return (
        '<div class="tile">'
        f'<div class="lab"><span class="dot {dot_cls}"></span> 점검 완료율</div>'
        f'<div class="big">{pct}%{arrow}</div>'
        f'<div class="sub">완료 {fmt_comma(done)} / 전체 {fmt_comma(total)} · 목표 95%</div>'
        '</div>'
    )


def tile_conversion(cpo: dict) -> str:
    rate = cpo.get("이번달_전환율")
    inquiries = cpo.get("이번달_전환_문의수")
    signups = cpo.get("이번달_전환_가입수")

    if not isinstance(rate, (int, float)):
        return (
            '<div class="tile">'
            '<div class="lab"><span class="dot"></span> 이번 달 전환</div>'
            f'<div class="big">{MISSING}</div>'
            '<div class="sub">데이터 없음</div>'
            '</div>'
        )

    return (
        '<div class="tile">'
        '<div class="lab"><span class="dot good"></span> 이번 달 전환</div>'
        f'<div class="big">{fmt_num(rate)}%</div>'
        f'<div class="sub">문의 {fmt_comma(inquiries)} → 가입 {fmt_comma(signups)}</div>'
        '</div>'
    )


def tile_parking(parking: dict) -> str:
    amount = parking.get("매출금액")
    count = parking.get("결제건수")

    if not isinstance(amount, (int, float)):
        return (
            '<div class="tile">'
            '<div class="lab">🅿️ 주차 매출</div>'
            f'<div class="big">{MISSING}</div>'
            '<div class="sub">데이터 없음</div>'
            '</div>'
        )

    return (
        '<div class="tile">'
        '<div class="lab">🅿️ 주차 매출</div>'
        f'<div class="big">{fmt_man(amount)}</div>'
        f'<div class="sub">이번 달 · 결제 {fmt_comma(count)}건</div>'
        '</div>'
    )


# ══════════════════════════════════════════════════════════════════════════
# 주차 일별 미니 막대그래프 — 매출금액 0(미수집/당일)은 회색 빈 막대
# ══════════════════════════════════════════════════════════════════════════
def _md(date_str: str) -> str:
    parts = (date_str or "").split("-")
    return f"{int(parts[1])}/{int(parts[2])}" if len(parts) == 3 else (date_str or "?")


def build_bars_html(daily: list) -> "tuple[str, str, str]":
    rows = []
    for d in daily:
        date_str = d.get("날짜", "")
        val = d.get("매출금액")
        val = val if isinstance(val, (int, float)) else 0
        rows.append((date_str, val))

    max_val = max((v for _, v in rows), default=0)
    max_date_label = ""
    cols = []
    for date_str, val in rows:
        try:
            day_num = str(int(date_str.split("-")[-1]))
        except Exception:
            day_num = "?"
        if val <= 0:
            bar_html = '<div class="bar zero"></div>'
        else:
            height = max(6, round(val / max_val * 48)) if max_val else 6
            cls = "bar max" if val == max_val else "bar"
            bar_html = f'<div class="{cls}" style="height:{height}px"></div>'
            if val == max_val and not max_date_label:
                max_date_label = _md(date_str)
        cols.append(f'<div class="col">{bar_html}<div class="lbl">{day_num}</div></div>')

    range_label = f"{_md(rows[0][0])}~{_md(rows[-1][0])}" if rows else ""
    max_label = f"최고 {fmt_man(max_val)} · {max_date_label}" if max_val else "최고 데이터 없음"
    return "".join(cols), range_label, max_label


def chart_wrap(parking: dict) -> str:
    daily = parking.get("일별")
    if not daily:
        return (
            '<div class="chart-wrap">'
            '<div class="chart-head"><span class="ct">주차 매출 · 일별 추이</span>'
            f'<span class="cv">{MISSING}</span></div>'
            '</div>'
        )
    bars_html, range_label, max_label = build_bars_html(daily)
    return (
        '<div class="chart-wrap">'
        '<div class="chart-head">'
        f'<span class="ct">주차 매출 · 일별 추이 ({range_label})</span>'
        f'<span class="cv">{max_label}</span>'
        '</div>'
        f'<div class="bars">{bars_html}</div>'
        '</div>'
    )


def build_footer(cfo: dict) -> str:
    month = extract_month(cfo.get("sales_month_label", ""))
    month_txt = f"{month}월" if month else "마감월 불명"
    return (
        '<footer class="foot">'
        '<div class="frow"><span class="tag">정직</span> '
        f'<span>매출=최근 마감월({month_txt}) 실적 · 그 외 전부 이번 달 라이브 값</span></div>'
        '<div class="frow"><b>출처</b> <span>매출 시트 · 점검 GAS · 회원 전환 · 주차 시스템 — 전부 자동 집계</span></div>'
        '</footer>'
    )


def build_page_html(kpi: dict, parking: dict, target_date: datetime) -> str:
    roles = kpi.get("roles", {})
    cfo = roles.get("cfo", {})
    coo = roles.get("coo", {})
    cpo = roles.get("cpo", {})

    alerts = compute_alerts(kpi)
    d1 = f"{target_date.month}.{target_date.day}"
    d2 = WEEKDAY_KR[target_date.weekday()]

    card = (
        '<div class="card" id="card" style="zoom:3">'
        '<header class="top">'
        '<div class="brand">'
        '<div class="mark">W</div>'
        '<div>'
        '<div class="t1">웰페리온 아침 요약</div>'
        '<div class="t2">매일 09:30 자동 · 회장님 · 관리부 · 운영부</div>'
        '</div>'
        '</div>'
        '<div class="date">'
        f'<div class="d1">{d1}</div>'
        f'<div class="d2">{d2}</div>'
        '</div>'
        '</header>'
        f'{build_banner(alerts)}'
        '<div class="pad" style="padding-top:0">'
        '<div class="grid">'
        f'{tile_sales(cfo)}'
        f'{tile_inspection(coo)}'
        f'{tile_conversion(cpo)}'
        f'{tile_parking(parking)}'
        '</div>'
        f'{chart_wrap(parking)}'
        '</div>'
        f'{build_footer(cfo)}'
        '</div>'
    )

    return PAGE_TEMPLATE.format(style=STYLE_CSS, card=card)


def render_card_png(html_content: str, out_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = sales_img._launch_context(p)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_content(html_content, wait_until="load")
            page.wait_for_timeout(300)
            el = page.query_selector("#card")
            if el is None:
                raise RuntimeError("#card 요소를 찾지 못함(렌더 실패)")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            el.screenshot(path=str(out_path))
        finally:
            try:
                context.close()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="카카오톡 아침 요약 카드 이미지 생성(HTML→PNG, 발송 없음)")
    ap.add_argument("--out", default=None, help="지정 시 이 경로에도 추가 저장")
    ap.add_argument("--date", default=None, help="카드 날짜 YYYYMMDD(기본 오늘)")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("FAILED: 이 스크립트는 Windows(Playwright+cao 프로필) 전용입니다.")
        return 1

    target_date = datetime.now()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            print(f"FAILED: --date 형식 오류({args.date}, YYYYMMDD 필요)")
            return 1

    try:
        kpi = load_json(KPI_PATH)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    try:
        parking = load_json(PARKING_PATH)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    try:
        html_content = build_page_html(kpi, parking, target_date)
    except Exception as exc:
        print(f"FAILED: 카드 HTML 생성 오류 — {exc}")
        return 1

    out_dir = OUT_DIR / target_date.strftime("%Y-%m")
    png_path = out_dir / target_date.strftime(FILENAME_FMT)

    try:
        render_card_png(html_content, png_path)
    except Exception as exc:
        print(f"FAILED: 카드 렌더링 오류 — {exc}")
        return 1

    if not png_path.exists() or png_path.stat().st_size == 0:
        print("FAILED: PNG 저장 실패(파일 없음/빈 파일)")
        return 1

    if args.out:
        try:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(png_path.read_bytes())
            log(f"추가 저장: {out_path}")
        except Exception as exc:
            log(f"[경고] --out 추가 저장 실패(무시, 기본 저장 자체는 성공): {exc}")

    print(f"IMAGE: {png_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
