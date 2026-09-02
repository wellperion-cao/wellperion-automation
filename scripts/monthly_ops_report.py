#!/usr/bin/env python3
"""월간 운영 계획·보고 — 월초/월말 자동 카드 엔진 (monthly_ops_report.py)

헌법(장기 비전)과 자율현황 🧭 항로(일일 배) 사이의 '월간 운영' 층을 GM이 "물어보고 챙기게"
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
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from honesty_gate import verdict as _honesty_verdict, summary_line as _honesty_summary_line
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from honesty_gate import verdict as _honesty_verdict, summary_line as _honesty_summary_line

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

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
HOME_KPI_SNAPSHOT_FILE = BASE_DIR / "status" / "home_kpi_snapshot.json"


def fetch_sales_month() -> tuple[int, bool] | None:
    """home_kpi ?action=home_kpi → sales.month 실값(원). 마감 전(null)이면 status/home_kpi_snapshot.json의
    monthInProgress(진행중 누적 · erp_status_publisher.py가 이미 발행 중 · 새 수집기 없음, 약속 L21)로 폴백한다.
    반환=(값, is_in_progress) — is_in_progress=True면 마감 전 진행중 누적(호출부가 반드시 라벨링).
    실패·미연동 시 None(정직). 2026-08-07 GM 지시 — 월간운영계획 매출 미연동 해결(08시 보고 건과 같은 방식)."""
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
        return int(val), False
    try:
        snap = json.loads(HOME_KPI_SNAPSHOT_FILE.read_text(encoding="utf-8"))
        mip = snap.get("data", {}).get("sales", {}).get("monthInProgress")
        if isinstance(mip, dict) and isinstance(mip.get("value"), (int, float)):
            return int(mip["value"]), True
    except Exception as e:
        print(f"[WARN] home_kpi_snapshot 진행중 누적 폴백 실패: {type(e).__name__}: {e}")
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
def _measured_block(cur_objs: list, sales_month: tuple[int, bool] | None) -> list:
    """측정 목표 실측 블록. 매출=home_kpi 실값 vs target, ERP%=metric.current vs target.
    정직(L05): current 없으면 상태만, 가짜 달성% 금지.
    정직 게이트(honesty_gate, GM 2단계 2026-07-24): objective.honesty.level 을 honesty_gate.verdict()
    로 판정해 비실측(manual/unmeasured) 수치 옆에 [미측정] 딱지를 붙인다(값 자체는 숨기지 않음).
    '실측 미연동(상태만)' 문구도 honesty_gate 배지로 일원화(흩어진 하드코딩 표기 제거)."""
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
        level = str((o.get("honesty") or {}).get("level", ""))
        v = _honesty_verdict(level)
        stamp_suffix = f" {v['stamp']}" if v["stamp"] else ""

        # 매출은 home_kpi 라이브 실측으로 current 대체 (마감 전엔 진행중 누적 — 반드시 라벨링)
        is_sales = unit == "원" or "매출" in str(metric.get("name", ""))
        in_progress = False
        if is_sales:
            current = sales_month[0] if sales_month else None
            in_progress = bool(sales_month and sales_month[1])
        else:
            current = metric.get("current")

        if isinstance(current, (int, float)) and isinstance(target, (int, float)) and target:
            rate = current / target * 100
            if unit == "원":
                cur_s, tgt_s = fmt_won(int(current)), fmt_won(int(target))
            else:
                cur_s, tgt_s = f"{current}{unit}", f"{target}{unit}"
            prog_tag = " <i>(마감 전 진행중 누적)</i>" if in_progress else ""
            out.append(f"  • {name}: {cur_s} / 목표 {tgt_s} → <b>{rate:.0f}%</b>{prog_tag}{stamp_suffix}")
        else:
            # 측정 안 됨 — 상태만(정직) · 배지는 honesty_gate 일원화
            tgt_s = fmt_won(int(target)) if (unit == "원" and isinstance(target, (int, float))) \
                else (f"{target}{unit}" if target is not None else "미정")
            out.append(f"  • {name}: 목표 {tgt_s} · <i>{v['badge']} 실측 미연동(상태만)</i>{stamp_suffix}")
    if not any_metric:
        out.append("  (측정 지표가 설정된 목표 없음)")
    return out


def build_end_card(plan: dict, now: datetime, sales_month: tuple[int, bool] | None) -> str:
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

    # 정직 게이트 요약(GM 2단계 2026-07-24): 이 카드에 실린 objective 전체의 실측/미측정 분포.
    lines.append("")
    lines.append(e(_honesty_summary_line(cur_objs)))
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
    try:
        ok = _tg_send(token, chat_id, text, source="monthly_ops_report.send_card",
                      extra={"parse_mode": "HTML", "disable_web_page_preview": "true"}, timeout=15)
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
def _snapshot_ledger(mode: str, now: datetime) -> None:
    """월간 보고 원장(status/monthly_report_ledger.json)을 그 달 값으로 채운다.

    실패해도 월간 카드 발송을 막지 않는다 — 원장은 A3 가 읽는 곳이고,
    카드는 텔레그램으로 나가는 별개 산출물이다.
    """
    if mode == "start":
        first = now.replace(day=1)
        target = (first - timedelta(days=1)).strftime("%Y-%m")
        extra = ["--close"]
        what = f"전월 {target} 마감 확정"
    else:
        target = now.strftime("%Y-%m")
        extra = []
        what = f"이번 달 {target} 재측정(마감 전)"
    cmd = [sys.executable,
           os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "monthly_report_snapshot.py"),
           "--month", target, "--write"] + extra
    print(f"[원장] {what}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", timeout=300)
        print("  → " + ((r.stdout or "").strip() or (r.stderr or "").strip() or "출력 없음"))
        if r.returncode != 0:
            log_event("ledger_snapshot_failed", mode=mode, month=target, rc=r.returncode)
    except Exception as exc:
        print(f"  [WARN] 원장 갱신 건너뜀: {type(exc).__name__}: {exc}")
        log_event("ledger_snapshot_failed", mode=mode, month=target, error=str(exc))


def _roll_month_status(now: datetime) -> None:
    """달이 바뀌면 월간운영계획의 달 상태를 오늘 기준으로 넘긴다(지난달=완료 / 이번달=진행 / 이후=계획).

    왜 여기냐: 이 값은 지금까지 아무 코드도 안 건드려 사람이 손으로 넘겨야 했고, 그래서
    2026-09-02 에 GM 이 "9월이 계획으로 되어 있다"고 직접 잡아 주셨다(8월이 진행중으로 남아
    있었다). 새 예약작업·새 파일을 만들지 않고(약속 L21) 이미 매월 1일 09:00 에 도는
    이 진입점에 흡수시킨다.

    라이브(--send)에서만 부른다 — 드라이런은 부작용 0 을 유지한다.
    """
    try:
        plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    except Exception as e:  # 원장을 못 읽으면 손대지 않는다
        print(f"[달상태] 원장을 못 읽어 건너뜀 — {e}")
        return
    cur = f"{now.year:04d}-{now.month:02d}"
    months = plan.get("months") or {}
    changed = []
    for key, body in months.items():
        if not isinstance(body, dict):
            continue
        want = "완료" if key < cur else ("진행" if key == cur else "계획")
        if body.get("month_status") != want:
            changed.append((key, body.get("month_status"), want))
            body["month_status"] = want
    if not changed:
        print("[달상태] 이미 최신 — 바꿀 것 없음")
        return
    PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    for key, old, new in changed:
        print(f"[달상태] {key} {old} → {new}")
    log_event("month_status_rolled", month=cur, changed=len(changed))


def run(mode: str, send: bool = False) -> str:
    now = datetime.now()
    label = "라이브 발송(--send)" if send else "드라이런"
    print(f"[시작] 월간 운영 {mode} 카드 ({label}) — {now_str()}")

    # 말일 가드 — end + send 인데 말일 아니면 라이브 부작용 생략(오발송 방지). 드라이런은 통과.
    if mode == "end" and send and not is_last_day(now):
        print(f"[가드] 오늘({now.strftime('%Y-%m-%d')})은 말일 아님 — 월말 라이브 발송 생략")
        log_event("end_skipped", reason="not_last_day", date=now.strftime("%Y-%m-%d"))
        return ""

    # 월간 보고 원장 갱신 — 회장님 A3 두 장이 이 원장을 직독한다(2026-08-29 시우).
    # 왜 여기냐: 원장을 채우는 monthly_report_snapshot 이 어떤 예약에도 안 걸려 있어
    #   사람이 손으로 실행해야 했다. 새 예약작업을 만들지 않고(약속 L21) 이미 매월
    #   두 번 도는 이 진입점에 흡수시킨다.
    #   · end(말일 21:00)  = 이번 달을 다시 세되 닫지 않는다(영업 마감 전이라 값이 더 는다)
    #   · start(1일 09:00) = 전월을 다시 세고 --close 로 확정한다(달이 완전히 끝난 뒤)
    # 라이브(--send)에서만 쓴다 — 드라이런은 부작용 0 을 유지한다.
    if send:
        _snapshot_ledger(mode, now)
        if mode == "start":
            _roll_month_status(now)

    plan = load_plan()

    # 매출 실측은 월말에만 필요(라이브 fetch)
    sales_month = None
    if mode == "end":
        print("[1/2] home_kpi 매출 실측 조회...")
        sales_month = fetch_sales_month()
        sm_val = sales_month[0] if sales_month else None
        sm_tag = " (마감 전 진행중 누적)" if sales_month and sales_month[1] else ""
        print(f"  → sales.month = {fmt_won(sm_val)}{sm_tag}")
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
            sales_month=(sales_month[0] if sales_month else None),
            sales_month_in_progress=bool(sales_month and sales_month[1]),
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
