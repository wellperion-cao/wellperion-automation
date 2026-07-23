#!/usr/bin/env python3
"""월간 운영 계획·보고 — 월초/월말 자동 카드 엔진 (monthly_ops_report.py)

헌법(장기 비전)과 G1 오늘의 항로(일일 배) 사이의 '월간 운영' 층을 GM이 "물어보고 챙기게"
하는 결정론적 카드 엔진. LLM 불필요(정본 데이터 → 고정 포맷).

정본·소스:
  - status/monthly_ops_plan.json (월별 objectives·status·metric)
  - 매출 실측 = home_kpi GAS ?action=home_kpi → sales.month (라이브)
  - 텔레그램 발송 = telegram_bot/.env (OWNER_ID/TELEGRAM_CHAT_ID · 토큰 단일출처)

카드 2종:
  · 월초(mode=start · 매월 1일 09:00): 전월 미완(이월 후보) + 이번달 시드 요약 + 계획 확정 CTA
  · 월말(mode=end · 매월 말일 21:00): 이번달 상태 요약 + 측정목표 실측(매출·ERP%) + 미완/이월 + 검토 CTA

사용법:
  python scripts/monthly_ops_report.py --mode start            # 드라이런(기본): 카드 콘솔 출력만
  python scripts/monthly_ops_report.py --mode end              # 드라이런
  python scripts/monthly_ops_report.py --mode start --send     # 라이브: 텔레그램 발송 + 로그
  python scripts/monthly_ops_report.py --mode end   --send     # 라이브 (말일 가드 적용)

예약(2단계 라이브):
  · Wellperion-MonthlyOps-Start-0900 = 매월 1일 09:00 → --mode start --send
  · Wellperion-MonthlyOps-End-2100   = 매월 말일 21:00 → --mode end --send
  런처: launchers/monthly_ops_report_hidden.vbs → scripts/monthly_ops_report.bat

정직 원칙(L05): 측정 안 되는 목표(metric 없음·current=null)는 상태만 표기, 가짜 달성% 금지.
"""
from __future__ import annotations

import argparse
import calendar
import html
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
PLAN_FILE = BASE_DIR / "status" / "monthly_ops_plan.json"
LOG_FILE = BASE_DIR / "status" / "monthly_ops_log.jsonl"
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"  # 토큰·챗ID 단일출처(INC-004)

# ── home_kpi GAS (매출 실측 sales.month) ──
HOME_KPI_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)

# ── 계획 페이지 (라이브 루트배포·가이드접두사 없음·ASCII) ──
PLAN_WEB_URL = "https://wellperion-cao.github.io/wellperion-automation/월간운영계획.html"

# ── 상태 배지 ──
STATUS_ICON = {"완료": "🏁", "진행": "🚢", "계획": "⚓", "이월": "🔄"}
CARRYOVER_STATUSES = ("진행", "계획", "이월")  # 완료 아닌 것 = 이월 후보


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════
#  입력 · 월 계산
# ═══════════════════════════════════════════
def load_plan() -> dict:
    try:
        return json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] 계획 로드 실패 {PLAN_FILE.name}: {type(e).__name__}: {e}")
        return {"months": {}}


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def prev_month_key(dt: datetime) -> str:
    y, m = dt.year, dt.month
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def month_label(key: str) -> str:
    """'2026-07' → '7월' (제목용)."""
    try:
        return f"{int(key.split('-')[1])}월"
    except Exception:
        return key


def is_last_day(dt: datetime) -> bool:
    return dt.day == calendar.monthrange(dt.year, dt.month)[1]


def objectives_of(plan: dict, key: str) -> list:
    return plan.get("months", {}).get(key, {}).get("objectives", []) or []


def owner_nick(plan: dict, o: dict) -> str:
    """objective owner(역할 id) → 닉네임. 매핑 없으면 owner 원문."""
    role = str(o.get("owner", ""))
    return str(plan.get("owner_nick", {}).get(role, role))


# ═══════════════════════════════════════════
#  매출 실측 (home_kpi sales.month)
# ═══════════════════════════════════════════
def fetch_sales_month() -> int | None:
    """home_kpi ?action=home_kpi → sales.month 실값(원). 실패·미연동 시 None(정직)."""
    try:
        req = urllib.request.Request(HOME_KPI_URL + "?action=home_kpi")
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"[WARN] home_kpi 조회 실패: {type(e).__name__}: {e}")
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        print("[WARN] home_kpi 응답 ok=False — 매출 미연동")
        return None
    sales = data.get("sales") or {}
    val = sales.get("month")
    if isinstance(val, (int, float)):
        return int(val)
    return None


def fmt_won(v: int | None) -> str:
    """원 → '6.5억' 가독 표기. None=미측정."""
    if v is None:
        return "미측정"
    eok = v / 100_000_000
    return f"{eok:.2f}억원"


# ═══════════════════════════════════════════
#  카드 빌더 — 월초
# ═══════════════════════════════════════════
def build_start_card(plan: dict, now: datetime) -> str:
    """월초 카드: 전월 미완(이월 후보) + 이번달 시드 요약 + 계획 확정 CTA."""
    e = html.escape
    cur_key = month_key(now)
    prev_key = prev_month_key(now)
    cur_lbl, prev_lbl = month_label(cur_key), month_label(prev_key)

    prev_objs = objectives_of(plan, prev_key)
    cur_objs = objectives_of(plan, cur_key)
    carry = [o for o in prev_objs if o.get("status") != "완료"]

    lines = [
        f"🗓️ <b>{e(cur_lbl)} 운영 계획 세울 시간입니다</b>",
        f"📅 {now.strftime('%Y-%m-%d')} · 헌법↔오늘의 항로 사이 '월간 운영' 층",
        "",
    ]

    # 전월 이월 후보
    lines.append(f"<b>🔄 {e(prev_lbl)} 이월 후보 (미완 {len(carry)}건)</b>")
    if carry:
        for o in carry:
            icon = STATUS_ICON.get(o.get("status", ""), "•")
            owner = e(owner_nick(plan, o))
            lines.append(f"  {icon} {e(str(o.get('title', '')))} <i>({owner}·{e(str(o.get('status', '')))})</i>")
    else:
        lines.append("  ✅ 전월 목표 전부 완료 — 이월 없음")
    lines.append("")

    # 이번달 시드 요약
    lines.append(f"<b>📋 {e(cur_lbl)} 기존 시드 목표 ({len(cur_objs)}건)</b>")
    if cur_objs:
        theme = plan.get("months", {}).get(cur_key, {}).get("theme", "")
        if theme:
            lines.append(f"  🎯 테마: {e(str(theme))}")
        for o in cur_objs:
            icon = STATUS_ICON.get(o.get("status", ""), "•")
            owner = e(owner_nick(plan, o))
            lines.append(f"  {icon} {e(str(o.get('title', '')))} <i>({owner})</i>")
    else:
        lines.append("  (아직 시드 목표 없음 — 새로 세우세요)")
    lines.append("")

    lines.append(f"👉 계획 페이지에서 {e(cur_lbl)} 목표를 확정하세요:")
    lines.append(f"📊 {PLAN_WEB_URL}")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  카드 빌더 — 월말
# ═══════════════════════════════════════════
def _measured_block(cur_objs: list, sales_month: int | None) -> list:
    """측정 목표 실측 블록. 매출=home_kpi 실값 vs target, ERP%=metric.current vs target.
    정직(L05): current 없으면 상태만, 가짜 달성% 금지."""
    e = html.escape
    out = ["<b>📈 측정 목표 실측</b>"]
    any_metric = False
    for o in cur_objs:
        metric = o.get("metric")
        if not isinstance(metric, dict):
            continue
        any_metric = True
        name = e(str(metric.get("name", "")))
        target = metric.get("target")
        unit = str(metric.get("unit", ""))

        # 매출은 home_kpi 라이브 실측으로 current 대체
        is_sales = unit == "원" or "매출" in str(metric.get("name", ""))
        current = sales_month if is_sales else metric.get("current")

        if isinstance(current, (int, float)) and isinstance(target, (int, float)) and target:
            rate = current / target * 100
            if unit == "원":
                cur_s, tgt_s = fmt_won(int(current)), fmt_won(int(target))
            else:
                cur_s, tgt_s = f"{current}{unit}", f"{target}{unit}"
            out.append(f"  • {name}: {cur_s} / 목표 {tgt_s} → <b>{rate:.0f}%</b>")
        else:
            # 측정 안 됨 — 상태만(정직)
            tgt_s = fmt_won(int(target)) if (unit == "원" and isinstance(target, (int, float))) \
                else (f"{target}{unit}" if target is not None else "미정")
            out.append(f"  • {name}: 목표 {tgt_s} · <i>실측 미연동(상태만)</i>")
    if not any_metric:
        out.append("  (측정 지표가 설정된 목표 없음)")
    return out


def build_end_card(plan: dict, now: datetime, sales_month: int | None) -> str:
    """월말 카드: 상태 요약 + 측정목표 실측 + 미완/이월 후보 + 검토 CTA."""
    e = html.escape
    cur_key = month_key(now)
    cur_lbl = month_label(cur_key)
    cur_objs = objectives_of(plan, cur_key)

    done = [o for o in cur_objs if o.get("status") == "완료"]
    prog = [o for o in cur_objs if o.get("status") == "진행"]
    plan_ = [o for o in cur_objs if o.get("status") in ("계획", "이월")]
    carry = [o for o in cur_objs if o.get("status") in CARRYOVER_STATUSES]

    lines = [
        f"📊 <b>{e(cur_lbl)} 운영 결과 보고 (초안)</b>",
        f"📅 {now.strftime('%Y-%m-%d')} · 전체 {len(cur_objs)}개 목표",
        "",
        f"<b>📌 상태 요약</b>  🏁 완료 {len(done)} · 🚢 진행 {len(prog)} · ⚓ 계획/미착수 {len(plan_)}",
        "",
    ]

    # 측정 목표 실측
    lines.extend(_measured_block(cur_objs, sales_month))
    lines.append("")

    # 미완/이월 후보
    lines.append(f"<b>🔄 미완·이월 후보 ({len(carry)}건)</b>")
    if carry:
        for o in carry:
            icon = STATUS_ICON.get(o.get("status", ""), "•")
            owner = e(owner_nick(plan, o))
            lines.append(f"  {icon} {e(str(o.get('title', '')))} <i>({owner}·{e(str(o.get('status', '')))})</i>")
    else:
        lines.append("  ✅ 미완 없음 — 이번달 목표 전부 완료")
    lines.append("")

    lines.append("👉 페이지에서 최종 검토·확정하세요:")
    lines.append(f"📊 {PLAN_WEB_URL}")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  텔레그램 발송 (.env 직독 · INC-004)
# ═══════════════════════════════════════════
def _env_val(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def send_card(text: str) -> bool:
    """카드를 GM(OWNER_ID, 폴백 TELEGRAM_CHAT_ID)에게 발송. 성공 True."""
    token = _env_val("TELEGRAM_BOT_TOKEN")
    chat_id = _env_val("OWNER_ID") or _env_val("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] 텔레그램 토큰/챗ID 미설정(.env) — 카드 발송 생략")
        return False
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
            print(f"[INFO] 월간 카드 발송 {'성공' if ok else '실패'}")
            return ok
    except Exception:
        print("[WARN] 카드 발송 실패 (토큰 trace 노출 방지로 상세 미출력)")
        return False


def log_event(event: str, **fields) -> None:
    """status/monthly_ops_log.jsonl 1행 append (발송·부작용 추적)."""
    rec = {"event": event, "logged_at": now_str(), **fields}
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 로그 기록 실패: {e}")


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(mode: str, send: bool = False) -> str:
    now = datetime.now()
    label = "라이브 발송(--send)" if send else "드라이런"
    print(f"[시작] 월간 운영 {mode} 카드 ({label}) — {now_str()}")

    # 말일 가드 — end + send 인데 말일 아니면 라이브 부작용 생략(오발송 방지). 드라이런은 통과.
    if mode == "end" and send and not is_last_day(now):
        print(f"[가드] 오늘({now.strftime('%Y-%m-%d')})은 말일 아님 — 월말 라이브 발송 생략")
        log_event("end_skipped", reason="not_last_day", date=now.strftime("%Y-%m-%d"))
        return ""

    plan = load_plan()

    # 매출 실측은 월말에만 필요(라이브 fetch)
    sales_month = None
    if mode == "end":
        print("[1/2] home_kpi 매출 실측 조회...")
        sales_month = fetch_sales_month()
        print(f"  → sales.month = {fmt_won(sales_month)}")
        card = build_end_card(plan, now, sales_month)
    else:
        card = build_start_card(plan, now)

    preview = card.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
    print(f"\n{'='*60}")
    print(html.unescape(preview))
    print(f"{'='*60}\n")

    if send:
        sent = send_card(card)
        log_event(
            f"{mode}_report",
            date=now.strftime("%Y-%m-%d"),
            sent=sent,
            sales_month=sales_month,
        )
        print(f"[2/2] 발송 완료 (텔레그램 {'발송' if sent else '미발송'}) — {now_str()}")
    else:
        print("  (드라이런 — 텔레그램 발송·로그는 --send)")
    return card


def main():
    parser = argparse.ArgumentParser(
        description="월간 운영 계획·보고 월초/월말 자동 카드 엔진",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", required=True, choices=["start", "end"],
                        help="start=월초 계획 카드(1일) / end=월말 결과 카드(말일)")
    parser.add_argument("--send", action="store_true",
                        help="라이브 발송 — 텔레그램 카드 + 로그 (예약 진입점)")
    parser.add_argument("--dry-run", action="store_true",
                        help="드라이런(기본 동작) — 카드 콘솔 출력만, 라이브 부작용 없음")
    args = parser.parse_args()
    run(mode=args.mode, send=args.send)


if __name__ == "__main__":
    main()
