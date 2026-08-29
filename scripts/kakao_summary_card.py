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
  - 지원부 점검 제출률 < 90% → ⚠️ 경보 (GM 확정 2026-08-29 · 제출률을 못 받으면 완료율 95% 로 폴백)
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

    # 게이트는 '제출률 90%'다(GM 확정 2026-08-29). 종전엔 완료율 95% 였는데, 완료율은
    # 제출률 × 제출분 충실도의 곱이라 무엇이 모자란지 가리키지 못했다. 실측상 항목 체크는
    # 93% 로 충실하고 모자란 것은 제출(48%)이라, 사람이 실제로 움직여야 하는 숫자에 건다.
    insp_rate = coo.get("지원부_점검완료율")
    submit_rate = coo.get("지원부_제출률")
    fill_rate = coo.get("지원부_제출분충실도")
    if isinstance(submit_rate, (int, float)):
        gated, gate, gate_label = submit_rate, 0.90, "제출 목표 90%"
    else:  # 제출률을 못 받았을 때만 종전 기준으로 돌아간다(fail-soft)
        gated, gate, gate_label = insp_rate, 0.95, "목표 95%"
    if isinstance(gated, (int, float)) and gated < gate:
        month = extract_month(coo.get("지원부_점검완료율_기준", ""))
        month_label = f"{month}월 누적" if month else "이번달 누적"
        # 병기: 45% 한 줄만 보면 체크 태만으로 오독한다 — 제출률·제출분충실도로 원인을 가른다(값 없으면 종전 표기 유지).
        if isinstance(submit_rate, (int, float)) and isinstance(fill_rate, (int, float)):
            detail = f"제출률 {dround(submit_rate * 100, 0)}% · 제출분 충실도 {dround(fill_rate * 100, 0)}%"
        else:
            detail = f"완료율 {dround(insp_rate * 100, 0)}%"
        alerts.append(f"지원부 점검 — {detail} — {gate_label} 미달 ({month_label})")

    sales = cfo.get("sales_month")
    target = cfo.get("sales_month_target")
    if isinstance(sales, (int, float)) and isinstance(target, (int, float)) and target:
        rate = sales / target * 100
        if rate < 90:
            alerts.append(f"매출 달성률 {dround(rate, 0)}% (목표 미달)")

    return alerts


def build_banner(alerts: list, head_word: str = "오늘") -> str:
    """경보 배너. head_word = '오늘'(매일 카드) / '이번 주'(주간 카드) 등 — 주기에 맞는 말을 쓴다.

    2026-08-08: 주간 카드에 '오늘 주의'라고 떠서 말이 안 맞았다(매일 카드용 문구를 그대로 씀).
    """
    if not alerts:
        return (
            '<div class="banner ok">'
            '<div class="ic">🟢</div>'
            f'<div><div class="b1">{html_mod.escape(head_word)} 특이사항 없음</div></div>'
            '</div>'
        )
    head = f"{head_word} 주의 {len(alerts)}건"
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
def _in_progress_line() -> str:
    """이달 진행중 누적 한 줄 — 큰 숫자는 마감 실적 그대로 두고, 오늘 값을 밑에 덧붙인다.

    ★2026-08-08 GM 지시("아침 요약 이거 내용 너무 좋은데?" — 살리기로 하며 기준 정정).
    큰 숫자를 진행중으로 바꾸지 않는 이유: 목표(sales_month_target)가 마감월 목표라,
    이달 누적을 지난달 목표로 나누면 달성률이 거짓이 된다. 숫자를 바꾸는 대신 한 줄을 더한다.
    판정·표기는 erp_status_publisher 한 곳이 한다(약속 L01 — 08시 보고·09시·09:30과 같은 값).
    """
    try:
        from erp_status_publisher import read_sales_month_display
        text, in_progress = read_sales_month_display()
    except Exception:
        return ""
    if not in_progress or text == "—":
        return ""
    # 한 줄에 들어가는 길이로 유지한다 — '· 마감 전'을 붙였더니 '마 / 감 전'으로 잘렸다(2026-08-08).
    # '진행중'이라는 말이 이미 마감 전이라는 뜻을 담고, 바로 윗줄에 'N월 마감'이 있어 대비도 된다.
    return f'<div class="sub">이달 진행중 {text}</div>'


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
        + _in_progress_line() +
        f'<div class="gauge"><i style="width:{gauge_w}%"></i></div>'
        '</div>'
    )


def tile_inspection(coo: dict) -> str:
    rate = coo.get("지원부_점검완료율")
    done = coo.get("지원부_완료")
    total = coo.get("지원부_전체")
    submit_rate = coo.get("지원부_제출률")
    fill_rate = coo.get("지원부_제출분충실도")

    if not isinstance(rate, (int, float)):
        return (
            '<div class="tile">'
            '<div class="lab"><span class="dot"></span> 지원부 점검 완료율</div>'
            f'<div class="big">{MISSING}</div>'
            '<div class="sub">데이터 없음</div>'
            '</div>'
        )

    pct = dround(rate * 100, 0)
    # 경보와 같은 게이트를 쓴다 — 카드와 경보가 서로 다른 기준을 말하면 안 된다(약속 L01).
    warn = (submit_rate < 0.90) if isinstance(submit_rate, (int, float)) else (rate < 0.95)
    dot_cls = "warn" if warn else "good"
    arrow = '<span class="arrow down" style="font-size:14px"> ▼</span>' if warn else ""
    # 병기: 완료율 한 숫자만 보면 4부서 값처럼 읽힌다(지원부 한정) + 낮은 원인(제출 누락 vs 체크 태만)이 안 보인다.
    # 값 없으면 종전 표기(완료/전체) 그대로 유지(fail-soft).
    if isinstance(submit_rate, (int, float)) and isinstance(fill_rate, (int, float)):
        sub = (f'제출률 {dround(submit_rate * 100, 0)}% · 제출분 충실도 '
               f'{dround(fill_rate * 100, 0)}% · 제출 목표 90%')
    else:
        sub = f'완료 {fmt_comma(done)} / 전체 {fmt_comma(total)} · 목표 95%'
    return (
        '<div class="tile">'
        f'<div class="lab"><span class="dot {dot_cls}"></span> 지원부 점검 완료율</div>'
        f'<div class="big">{pct}%{arrow}</div>'
        f'<div class="sub">{sub}</div>'
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
        '<div class="t2">💬 매일 07:30 자동 · ★운영부</div>'
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


# ══════════════════════════════════════════════════════════════════════════
# 방별 카드 — ★중간관리자 「멈춘 업무 정리」 (2026-08-08 GM 지시)
#   GM: "지금은 글로 다 정리가 되니까 잘 읽지도 않고 반영도 안되는 것 같아."
#       "진행이 안되는 건에 대해선 명확히 담당 팀 리더에게 전달을 해서 작업을 할 수 있게."
#   ★실측이 설계를 바꿨다(2026-08-08): 지연 12건 전부 담당자가 이미 있다(담당 미정 0건).
#     문제는 '누구 건지 몰라서'가 아니라 '알고도 두 달째 안 움직인다'다. 그래서 이름보다
#     **며칠째인지**를 크게 세운다 — D+63 이라는 숫자가 이름보다 사람을 움직인다.
#   겉모습·렌더·발송은 위 아침 요약 카드 것을 그대로 쓴다(새 엔진·새 발송 경로 없음 · 약속 L21).
# ══════════════════════════════════════════════════════════════════════════
STALLED_ROOM = "★중간관리자"
STALLED_STATE_ID = "stalled-weekly-snapshot"   # 지난 회차 목록 = 상설 하트비트 1파일(새 파일 안 만든다)
ESCALATE_WEEKS = 3     # 이 주차 이상 같은 건이 사유도 없이 남으면 GM 께 올린다


def _stalled_state() -> dict:
    """지난 회차 스냅샷 {업무id: 그때 주차}. send_ops_digest 의 릴레이 스냅샷과 같은 방식."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from module_heartbeat import last_heartbeat
    rec = last_heartbeat(STALLED_STATE_ID) or {}
    st = rec.get("state")
    return dict(st) if isinstance(st, dict) else {}


def _save_stalled_state(state: dict) -> None:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from module_heartbeat import record_heartbeat
    record_heartbeat(STALLED_STATE_ID,
                     detail=f"멈춘 업무 주간 회차 기록 — {len(state)}건",
                     extra={"state": state})


def collect_stalled(record: bool = False) -> dict:
    """업무 시트(S3)에서 마감이 지난 채 살아 있는 건을 담당자별로 모은다.

    판정은 report_stream_3_impl 의 것을 그대로 쓴다 — 같은 '지연'을 두 벌로 계산하지 않는다
    (약속 L01). 조회 실패는 예외를 올린다(빈 카드를 정상처럼 내보내지 않는다).

    ★고리를 닫는 부분 (GM 2026-08-08 세 번 지시 — "진행이 안된건에 대해서는 명확히 체크해서
      진행이 되게끔 구조를 만들어줘"):
      카드로 알리기만 하면 다음 주에 같은 이름이 또 뜨고, 반복되면 다시 안 읽힌다.
      그래서 세 가지를 같이 센다.
      ① **몇 주째인가** — 회차마다 목록을 남겨 다음 회차와 대조한다. 주차가 늘면 그 건은
         '알렸는데도 안 움직인 건'이다.
      ② **막힌 이유가 적혀 있나** — 시트에 「보류사유」·「재개조건」 칸이 이미 있다(새 칸 안 만든다).
         2026-08-08 실측: 지연 12건 전부 두 칸이 비어 있었다. 칸은 있는데 아무도 안 쓴다 —
         구조의 빈 곳이 여기다. 비어 있으면 카드가 그 사실 자체를 요청으로 띄운다.
      ③ **그래도 안 되면 올린다** — 3주째인데 사유도 없는 건은 담당이 못 푸는 건이다.
         그건 GM 이 풀 일이므로 카드 맨 위와 GM 보고로 분리해 올린다(사람을 탓하지 않고 막힌 곳을 연다).
    record=True 일 때만 회차 기록을 갱신한다 — 미리보기로 주차가 올라가면 안 된다.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report_stream_3_impl import (_fetch_todo, _is_overdue, _due_date10,
                                      TODO_DONE_STATUSES)
    today = datetime.now().strftime("%Y-%m-%d")
    items = _fetch_todo()
    if not items:
        raise RuntimeError("업무 시트 응답 없음 — 카드를 만들지 않는다(빈 값을 0으로 내보내지 않음)")
    active = [x for x in items if str(x.get("상태", "")).strip() not in TODO_DONE_STATUSES]
    overdue = [x for x in active if _is_overdue(x, today)]

    def days_over(x) -> int:
        d = _due_date10(x)
        try:
            due = datetime.strptime(d[:10], "%Y-%m-%d")
            return (datetime.now() - due).days
        except Exception:
            return 0

    prev = _stalled_state()
    raw = [{"key": str(x.get("id") or x.get("업무명") or ""),
            "who": (str(x.get("담당자", "")).strip() or "담당 미정"),
            "title": str(x.get("업무명", "")).strip(),
            "days": days_over(x),
            "reason": str(x.get("보류사유", "")).strip(),
            "resume": str(x.get("재개조건", "")).strip()} for x in overdue]
    folded = fold_stalled(raw, prev)

    if record:
        _save_stalled_state(folded["state"])

    folded["active"] = len(active)
    folded["overdue"] = len(overdue)
    return folded


def fold_stalled(raw: list, prev: dict) -> dict:
    """지연 목록 + 지난 회차 기록 → 카드가 쓸 값. 파일·시트를 안 건드리는 순수 함수.

    자기검사 = scripts/test_stalled_card.py (주차 세기와 에스컬레이션 경계가 유일한 위험).
    """
    rows, state = [], {}
    for r in raw:
        weeks = int(prev.get(r["key"], 0)) + 1     # 이번 회차 포함 몇 번째로 뜨는가
        row = dict(r, weeks=weeks)
        rows.append(row)
        state[r["key"]] = weeks
    rows.sort(key=lambda r: -r["days"])

    # ★부서 단위로 센다(GM 확정 2026-08-08) — 개인 이름으로 부르면 방어부터 하게 된다.
    by_dept: dict = {}
    for r in rows:
        r["dept"] = dept_of(r["who"])
        by_dept[r["dept"]] = by_dept.get(r["dept"], 0) + 1

    # 담당이 못 푸는 것 = 여러 회차째인데 막힌 이유조차 안 적힌 건. 이건 GM 이 풀 일이다.
    return {"rows": rows, "state": state,
            "by_who": sorted(by_dept.items(), key=lambda kv: -kv[1]),
            "escalate": [r for r in rows if r["weeks"] >= ESCALATE_WEEKS and not r["reason"]],
            "no_reason": [r for r in rows if not r["reason"]],
            "first_round": not prev}


def dept_of(name: str) -> str:
    """사람 이름 → 부서. 못 찾으면 '미분류'(지어내지 않는다).

    ★GM 확정 2026-08-08 — "사람단위로 하지말고 부서단위로 정리하는게 좋지않아?
      사람이 직접적으로 안된건에 대해서 이야기하면 괴로울 것 같은데?"
      멈춘 일을 개인 이름으로 부르면 방어부터 하게 된다. 부서로 말하면 그 부서 리더가
      안에서 나눈다(약속 L24 — 지시·보고는 리더 한 곳을 거친다).
    정본 = ssot/ownership_map.json 의 부서_리더. 여기 표를 새로 만들지 않는다(약속 L01).
    """
    nm = str(name or "").strip()
    for d in _dept_table():
        if nm in d.get("구성원", []):
            return d["이름"]
    return "미분류"


def dept_leader(dept: str) -> str:
    for d in _dept_table():
        if d["이름"] == dept:
            return d.get("리더", "")
    return ""


def _dept_table() -> list:
    global _DEPT_CACHE
    if _DEPT_CACHE is None:
        try:
            m = json.loads((ROOT / "ssot" / "ownership_map.json").read_text(encoding="utf-8"))
            _DEPT_CACHE = (m.get("부서_리더") or {}).get("부서") or []
        except Exception:
            _DEPT_CACHE = []
    return _DEPT_CACHE


_DEPT_CACHE = None


def _stalled_tile(label: str, big: str, sub: str, tone: str = "") -> str:
    return (f'<div class="tile{(" " + tone) if tone else ""}">'
            f'<div class="lab">{label}</div>'
            f'<div class="big">{big}</div>'
            f'<div class="sub">{sub}</div></div>')


def build_stalled_card_html(S: dict, target_date: datetime) -> str:
    """★중간관리자 「멈춘 업무 정리」 카드 HTML."""
    d1 = f"{target_date.month}.{target_date.day}"
    d2 = WEEKDAY_KR[target_date.weekday()]
    rows, by_who = S["rows"], S["by_who"]

    # 경보 = 가장 오래 멈춘 것 하나. 없으면 '특이사항 없음'(엔진의 기존 배너 규칙 재사용).
    alerts = ([f'{rows[0]["title"]} — {rows[0]["days"]}일째 · {rows[0].get("dept") or "미분류"}'] if rows else [])

    who_lines = "".join(
        f'<div class="who"><span class="wn">{w}</span>'
        f'<span class="wc">{n}건</span></div>' for w, n in by_who) or \
        '<div class="sub">멈춘 업무 없음</div>'

    # 오래된 순 5건까지. 12건을 다 실으면 카드가 다시 '긴 글'이 된다.
    SHOW = 5

    # 전부 비어 있으면 줄마다 '안 적힘'을 반복하지 않는다 — 같은 말이 5번 이어지면 그게 곧
    # 안 읽히는 벽글이다(맨 아래 부탁이 한 번만 말한다). 일부라도 적히기 시작하면 그때부터
    # 안 적힌 줄을 표시해 대비를 만든다.
    all_empty = len(S.get("no_reason") or []) == len(rows)

    def _row_html(r) -> str:
        # 주차 꼬리표 — 이미 알렸는데 또 뜬 건임을 드러낸다(1주째는 안 붙인다·소음).
        wk = (f'<span class="wk">{r["weeks"]}주째</span>' if r["weeks"] >= 2 else "")
        # 막힌 이유가 적혀 있으면 그걸 보여 준다. 그게 GM 이 풀 수 있는 실마리다.
        if r["reason"]:
            why = f'<div class="why">막힌 곳 — {html_mod.escape(r["reason"][:34])}</div>'
        elif all_empty:
            why = ""
        else:
            why = '<div class="why nofill">막힌 이유 아직 안 적힘</div>'
        return ('<div class="sblock">'
                f'<div class="srow"><span class="sd">{r["days"]}일</span>'
                f'<span class="st">{html_mod.escape(r["title"][:30])}</span>'
                f'<span class="sw">{html_mod.escape(r.get("dept") or "미분류")}{wk}</span></div>'
                f'{why}</div>')

    top = "".join(_row_html(r) for r in rows[:SHOW])
    more = (f'<div class="sub" style="margin-top:6px;">외 {len(rows) - SHOW}건 — '
            f'업무 현황 화면에서 전부 봅니다</div>') if len(rows) > SHOW else ""

    # 담당이 못 푸는 것 — 사람을 탓하는 칸이 아니라 GM 이 열어 줄 문을 가리키는 칸이다.
    esc = S.get("escalate") or []
    esc_html = ""
    if esc:
        esc_lines = "".join(
            f'<div class="srow"><span class="sd">{r["weeks"]}주</span>'
            f'<span class="st">{html_mod.escape(r["title"][:30])}</span>'
            f'<span class="sw">{html_mod.escape(r.get("dept") or "미분류")}</span></div>' for r in esc[:3])
        esc_html = ('<div class="whowrap esc"><div class="lab">🔴 담당이 못 푸는 것 — GM 께 올립니다</div>'
                    f'{esc_lines}'
                    '<div class="sub" style="margin-top:6px;">여러 주째 그대로인데 막힌 이유도 안 적혔습니다. '
                    '담당 힘으로 안 되는 건으로 봅니다.</div></div>')

    nr = len(S.get("no_reason") or [])
    nr_line = (f'<b>{nr}건</b>은 막힌 이유가 아직 비어 있습니다. ' if nr else "")
    # 부서 리더는 '탓할 사람'이 아니라 '안에서 나눌 사람'이다 — 숫자 옆이 아니라 여기에만 적는다.
    leads = [f'{d} {dept_leader(d)}' for d, _n in by_who if dept_leader(d)]
    lead_line = (f'{" · ".join(leads)}께 드립니다. ' if leads else "")

    card = (
        '<div class="card" id="card" style="zoom:3">'
        '<header class="top">'
        '<div class="brand"><div class="mark">W</div><div>'
        '<div class="t1">멈춘 업무 정리</div>'
        f'<div class="t2">💬 매주 금 17:00 자동 · {STALLED_ROOM}</div>'
        '</div></div>'
        f'<div class="date"><div class="d1">{d1}</div><div class="d2">{d2}</div></div>'
        '</header>'
        f'{build_banner(alerts, "이번 주")}'
        '<div class="pad" style="padding-top:0">'
        '<div class="grid">'
        f'{_stalled_tile("🗂 진행 중", fmt_comma(S["active"]) + "건", "마감 안 지난 것")}'
        f'{_stalled_tile("⏰ 마감 지남", fmt_comma(S["overdue"]) + "건", "부서별로 아래에", "sales")}'
        '</div>'
        '<div class="whowrap"><div class="lab">부서별 밀린 건수</div>'
        f'{who_lines}</div>'
        '<div class="whowrap"><div class="lab">가장 오래 멈춘 것</div>'
        f'{top}{more}</div>'
        f'{esc_html}'
        '</div>'
        '<div class="foot"><div class="fl">'
        f'<b>부탁</b> {lead_line}{nr_line}업무 시트의 <b>「보류사유」·「재개조건」</b> 두 칸에 한 줄만 적어 주세요. '
        '적히면 다음 주 카드에 그 내용이 뜨고, 막힌 곳은 저희가 풉니다. '
        '끝났거나 접을 건이면 상태만 바꿔 주셔도 목록에서 빠집니다.'
        '</div></div>'
        '</div>'
    )
    return PAGE_TEMPLATE.format(style=STYLE_CSS + STALLED_CSS, card=card)


STALLED_CSS = """
.whowrap{margin-top:14px;padding:14px 16px;background:var(--tile);border:1px solid var(--line);border-radius:14px}
.whowrap .lab{font-size:13px;font-weight:800;color:var(--dim);margin-bottom:8px}
.who{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)}
.who:last-child{border-bottom:none}
.wn{font-size:15px;font-weight:700;color:var(--ink)}
.wc{font-size:15px;font-weight:800;color:var(--gold)}
.lead{font-size:12px;font-weight:600;color:var(--dim);margin-left:6px}
.srow{display:flex;align-items:baseline;gap:10px;padding:5px 0;border-bottom:1px solid var(--line)}
.srow:last-child{border-bottom:none}
.sd{flex:0 0 auto;min-width:52px;font-size:16px;font-weight:800;color:var(--crit)}
.st{flex:1 1 auto;font-size:14px;color:var(--ink);line-height:1.45}
.sw{flex:0 0 auto;font-size:13px;font-weight:700;color:var(--dim);text-align:right}
.sblock{padding:6px 0;border-bottom:1px solid var(--line)}
.sblock:last-child{border-bottom:none}
.sblock .srow{border-bottom:none;padding:0}
.wk{display:block;font-size:11px;font-weight:800;color:var(--crit);margin-top:2px}
.why{margin:3px 0 0 62px;font-size:12.5px;color:var(--dim);line-height:1.4}
.why.nofill{color:var(--crit);font-weight:700}
.whowrap.esc{border-color:var(--crit);background:#FCECE8}
.whowrap.esc .lab{color:var(--crit)}
"""


# ══════════════════════════════════════════════════════════════════════════
# 방별 카드 2호 — ★운영+시설+지원+주차 「오늘 점검 마감」 (2026-08-08 GM 지시)
#   이 방이 받는 밤 22:30 글이 47줄 + 42줄 두 통으로 가장 긴 벽글이다. 시설부 회차 일지·
#   측정값 20여 줄이 이상 없어도 매일 전문으로 나가고, 정작 행동이 필요한 '0% 조'는
#   중간에 묻힌다. 카드는 **오늘 안 채운 곳**을 맨 위로 올리는 것이 전부다.
#   원본 글을 다시 만들지 않는다 — 이미 조립된 본문을 읽어 숫자만 뽑는다(약속 L01).
# ══════════════════════════════════════════════════════════════════════════
CHECK_ROOM = "★운영+시설+지원+주차"


def collect_check(section_text: str) -> dict:
    """점검 본문에서 카드가 쓸 숫자만 뽑는다. 파일·시트를 안 건드리는 순수 함수.

    자기검사 = scripts/test_check_card.py
    """
    import re as _re
    S: dict = {"facility": None, "support": None, "parking": None,
               "zero_groups": [], "full_groups": [], "issues": []}

    m = _re.search(r"🏗 시설부 현황\s*(\d+)회차\s*·\s*(\S+[^\n]*)", section_text)
    if m:
        S["facility"] = {"rounds": int(m.group(1)), "state": m.group(2).strip()}

    m = _re.search(r"🛠 지원부 현황\s*(\d+)/(\d+)\((\d+)%\)", section_text)
    if m:
        S["support"] = {"done": int(m.group(1)), "total": int(m.group(2)), "pct": int(m.group(3))}

    for zone, _d, _t, _p, groups in _re.findall(
            r"(남성구역|여성구역) (\d+)/(\d+)\((\d+)%\) — (.+)", section_text):
        for gname, gd, gt in _re.findall(r"(\S+조)\s*(\d+)/(\d+)", groups):
            gd, gt = int(gd), int(gt)
            if gt <= 0:
                continue
            if gd == 0:
                S["zero_groups"].append({"name": f"{zone} {gname}", "total": gt})
            elif gd == gt:
                S["full_groups"].append({"name": f"{zone} {gname}", "total": gt})

    m = _re.search(r"🅿 주차부 이슈사항:\s*([^\n]+)", section_text)
    if m:
        S["parking"] = m.group(1).strip()

    for line in _re.findall(r"·\s*\[([^\]]+)\]\s*([^\n(]+)", section_text):
        S["issues"].append({"where": line[0].strip(), "what": line[1].strip()})
    return S


def build_check_card_html(S: dict, target_date: datetime) -> str:
    """★운영+시설+지원+주차 「오늘 점검 마감」 카드 HTML."""
    d1 = f"{target_date.month}.{target_date.day}"
    d2 = WEEKDAY_KR[target_date.weekday()]
    fac, sup, park = S.get("facility"), S.get("support"), S.get("parking")
    zeros, fulls = S.get("zero_groups") or [], S.get("full_groups") or []

    # 경보 = 아직 한 건도 안 들어온 조. 이게 오늘 이 방이 움직여야 할 유일한 이유다.
    alerts = [f'{z["name"]} — {z["total"]}건 중 아직 0건' for z in zeros[:3]]

    fac_big = f'{fac["rounds"]}회차' if fac else MISSING
    fac_sub = (fac["state"] if fac else "값 없음")
    sup_big = (f'{sup["pct"]}%' if sup else MISSING)
    sup_sub = (f'{sup["done"]}/{sup["total"]}건 완료' if sup else "값 없음")
    park_sub = park or "값 없음"

    tiles = (
        _stalled_tile("🏗 시설부", fac_big, fac_sub) +
        _stalled_tile("🛠 지원부", sup_big, sup_sub,
                      "sales" if (sup and sup["pct"] < 90) else "") +
        _stalled_tile("🅿 주차부", "이슈 없음" if park and park.startswith("없음") else "확인",
                      park_sub)
    )

    zero_html = ""
    if zeros:
        rows = "".join(
            f'<div class="srow"><span class="sd">0건</span>'
            f'<span class="st">{html_mod.escape(z["name"])}</span>'
            f'<span class="sw">{z["total"]}건 예정</span></div>' for z in zeros)
        zero_html = ('<div class="whowrap esc"><div class="lab">🔴 아직 안 들어온 조</div>'
                     f'{rows}<div class="sub" style="margin-top:6px;">'
                     '하셨는데 입력만 못 하신 것일 수 있습니다 — 확인 부탁드립니다.</div></div>')

    full_html = ""
    if fulls:
        rows = "".join(
            f'<div class="who"><span class="wn">{html_mod.escape(f["name"])}</span>'
            f'<span class="wc">{f["total"]}건 완료</span></div>' for f in fulls[:3])
        full_html = ('<div class="whowrap"><div class="lab">🏆 오늘 다 채운 곳</div>'
                     f'{rows}</div>')

    issues = S.get("issues") or []
    issue_html = ""
    if issues:
        rows = "".join(
            f'<div class="srow"><span class="st">{html_mod.escape(i["what"][:34])}</span>'
            f'<span class="sw">{html_mod.escape(i["where"])}</span></div>' for i in issues[:3])
        issue_html = ('<div class="whowrap"><div class="lab">🛠 오늘 올라온 이슈</div>'
                      f'{rows}</div>')

    card = (
        '<div class="card" id="card" style="zoom:3">'
        '<header class="top">'
        '<div class="brand"><div class="mark">W</div><div>'
        '<div class="t1">오늘 점검 마감</div>'
        f'<div class="t2">💬 매일 밤 자동 · {CHECK_ROOM}</div>'
        '</div></div>'
        f'<div class="date"><div class="d1">{d1}</div><div class="d2">{d2}</div></div>'
        '</header>'
        f'{build_banner(alerts)}'
        '<div class="pad" style="padding-top:0">'
        f'<div class="grid">{tiles}</div>'
        f'{zero_html}{full_html}{issue_html}'
        '</div>'
        '<div class="foot"><div class="fl">'
        '<b>부탁</b> 빈 칸으로 남은 조는 <b>내일 아침 제출</b> 부탁드립니다. '
        '회차별 일지와 측정값 전체는 점검 화면에서 그대로 보실 수 있습니다.'
        '</div></div>'
        '</div>'
    )
    return PAGE_TEMPLATE.format(style=STYLE_CSS + STALLED_CSS, card=card)


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
    ap.add_argument("--card", default="morning", choices=["morning", "stalled", "check"],
                    help="morning=아침 요약(기본) · stalled=★중간관리자 멈춘 업무 정리 · "
                         "check=★운영+시설+지원+주차 오늘 점검 마감")
    ap.add_argument("--record", action="store_true",
                    help="stalled 전용 — 이번 회차를 기록해 '몇 주째'를 올린다. "
                         "실제 발송 회차에서만 켠다(미리보기로 주차가 오르면 안 된다)")
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

    if args.card == "check":
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            from report_stream_2_check import _check_section
            section = _check_section(target_date.strftime("%Y-%m-%d"))
            if not section.strip():
                raise RuntimeError("점검 본문이 비었다 — 카드를 만들지 않는다")
            html_content = build_check_card_html(collect_check(section), target_date)
        except Exception as exc:
            print(f"FAILED: 점검 마감 카드 — {exc}")
            return 1
        out_dir = OUT_DIR / target_date.strftime("%Y-%m")
        png_path = out_dir / target_date.strftime("웰페리온_점검마감_%Y%m%d.png")
        try:
            render_card_png(html_content, png_path)
        except Exception as exc:
            print(f"FAILED: 카드 렌더 오류 — {exc}")
            return 1
        if args.out:
            extra = Path(args.out)
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(png_path.read_bytes())
        print(f"IMAGE: {png_path}")
        return 0

    if args.card == "stalled":
        try:
            S = collect_stalled(record=args.record)
            html_content = build_stalled_card_html(S, target_date)
        except Exception as exc:
            print(f"FAILED: 멈춘 업무 카드 — {exc}")
            return 1
        out_dir = OUT_DIR / target_date.strftime("%Y-%m")
        png_path = out_dir / target_date.strftime("웰페리온_멈춘업무_%Y%m%d.png")
        try:
            render_card_png(html_content, png_path)
        except Exception as exc:
            print(f"FAILED: 카드 렌더 오류 — {exc}")
            return 1
        if args.out:
            extra = Path(args.out)
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(png_path.read_bytes())
        print(f"IMAGE: {png_path}")
        return 0

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
