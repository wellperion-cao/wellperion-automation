#!/usr/bin/env python3
"""지원부 점검 월간 리포트 — 매월 1일 자동 요약 (monthly_check_report.py)

배208(지원부 점검 월간 분석 리포트 자동화) 3단계: 매월 1일 자동화.
전월 GAS monthly_report(dept=support) 집계를 점검관리방 텔레그램에 3~5줄 요약 +
페이지 링크로 발송한다. 콘텐츠·집계는 이미 라이브(GAS monthly_report action).
이 스크립트는 '매월 1일 자동 발송' 배선만 담당(monthly_ops_report.py 패턴 재사용).

정본·소스:
  - GAS ?action=monthly_report&dept=support&month=YYYY-MM (라이브·2026-07-03 배포)
  - 텔레그램 발송 = telegram_bot/.env (TELEGRAM_BOT_TOKEN·TELEGRAM_CHECK_CHAT_ID 단일출처)
  - 상세 페이지 = coo/check/지원부 체계.html#monthly (월간보고 탭)

사용법:
  python scripts/monthly_check_report.py                 # 드라이런(기본): 카드 콘솔 출력만
  python scripts/monthly_check_report.py --send           # 라이브: 텔레그램 발송 + 로그 (매월 1일 가드)
  python scripts/monthly_check_report.py --send --force    # 가드 무시(수동 테스트용)
  python scripts/monthly_check_report.py --month 2026-06  # 특정 월 강제 지정(테스트용, 드라이런 권장)

게이트(손대지 않음):
  - GAS 웹앱 재배포 = GM 액션
  - today_live 금요일 0 수리 = 시토 담당
  둘 다 이 스크립트와 무관 — monthly_report action은 이미 라이브 배포됨.

예약(활성화 절차 — GM 1회 확인 후 등록):
  Task Scheduler: Wellperion-MonthlyCheckReport-0900-D1 (매월 1일 09:00)
  등록 예시(관리자 PowerShell, GM 1회 실행):
    schtasks /create /tn "Wellperion-MonthlyCheckReport-0900-D1" ^
      /tr "wscript.exe C:\\Users\\jjky0\\welperion-automation\\launchers\\monthly_check_report_hidden.vbs" ^
      /sc MONTHLY /d 1 /st 09:00 /f
  런처: launchers\\monthly_check_report_hidden.vbs (숨김창) → scripts\\monthly_check_report.bat → 본 스크립트 --send.
  (reference_powershell_scheduledtasks_limitation 규칙 준수 — .bat ASCII 전용, 예약작업 검은창은 vbs 숨김런처로 우회)

첫 실발송: 8월 1일(7월 집계) — 6·7월은 분모 통일 직후 테스트 기간(handoff 문서 COO-2026-07-03-MONTHLY-REPORT-TELEGRAM-HANDOFF.md 참고).
"""
from __future__ import annotations

import argparse
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
LOG_FILE = BASE_DIR / "status" / "support_monthly_report_log.jsonl"
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"  # 토큰·챗ID 단일출처(INC-004)

# ── 지원부 점검 GAS(라이브 배포·2026-07-03 monthly_report action 포함) ──
GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"
)

# ── 상세 페이지(라이브 루트배포·월간보고 탭 앵커) ──
PAGE_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/check/지원부 체계.html#monthly"

# ── 점검관리방 chat_id 폴백(3분류 분리 완료·INC-011) ──
DEFAULT_CHECK_CHAT_ID = "-5136037543"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════
#  월 계산
# ═══════════════════════════════════════════
def prev_month_key(dt: datetime) -> str:
    y, m = dt.year, dt.month
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def month_label(key: str) -> str:
    """'2026-06' → '6월' (제목용)."""
    try:
        return f"{int(key.split('-')[1])}월"
    except Exception:
        return key


def prev_month_key_str(month_key: str) -> str:
    """'2026-07' → '2026-06' (전월 대비 조회용 — month 문자열 기준)."""
    try:
        y, m = (int(x) for x in month_key.split("-"))
    except Exception:
        return month_key
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


# ═══════════════════════════════════════════
#  신호등 판정 (결정론 — avgPct 기준)
# ═══════════════════════════════════════════
def signal(avg_pct) -> tuple[str, str]:
    """avgPct → (이모지, 판정어). >=90 양호 / 70~89 주의 / <70 위험 / None 미측정."""
    if not isinstance(avg_pct, (int, float)):
        return ("⚪", "미측정")
    if avg_pct >= 90:
        return ("🟢", "양호")
    if avg_pct >= 70:
        return ("🟡", "주의")
    return ("🔴", "위험")


def _fmt_num(n: float) -> str:
    """정수면 '2', 소수면 '2.5' (%g 스타일 — 불필요한 .0 제거)."""
    if float(n).is_integer():
        return str(int(n))
    return str(n)


# ═══════════════════════════════════════════
#  GAS 조회
# ═══════════════════════════════════════════
def fetch_monthly_report(month: str) -> dict | None:
    """?action=monthly_report&dept=support&month=YYYY-MM 호출. 실패 시 None(정직 — 지어내기 금지)."""
    url = GAS_URL + "?action=monthly_report&dept=support&month=" + urllib.parse.quote(month)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"[WARN] monthly_report 조회 실패: {type(e).__name__}: {e}")
        return None
    if not isinstance(data, dict) or not data.get("ok"):
        print(f"[WARN] monthly_report 응답 ok=false: {data}")
        return None
    return data


def max_issue_day(daily_series: list) -> tuple[str, int] | None:
    """dailySeries에서 issueCount 최다일 (M월DD일, count) 반환. 이슈 0건이면 None."""
    if not daily_series:
        return None
    best = max(daily_series, key=lambda d: d.get("issueCount", 0) or 0)
    if not best.get("issueCount"):
        return None
    parts = str(best.get("date", "")).split("-")
    if len(parts) != 3:
        return None
    label = f"{int(parts[1])}월 {int(parts[2])}일"
    return label, int(best["issueCount"])


# ═══════════════════════════════════════════
#  카드 빌더
# ═══════════════════════════════════════════
def build_card(data: dict, month_key: str, prev_data: dict | None = None) -> str:
    """4줄 한눈 판정형 카드 + 상세 링크. improvements·denomNote는 GAS 원문 그대로(가공·지어내기 금지).
    prev_data(전월 monthly_report 응답)가 있으면 전월 대비 화살표를 덧붙인다 — 없으면(조회 실패 포함) 화살표 생략(지어내기 금지)."""
    lbl = month_label(month_key)
    totals = data.get("monthTotals", {}) or {}
    avg_pct = totals.get("avgPct")
    issue_count = totals.get("issueCount", 0)

    denom_note = str(data.get("denomNote", ""))
    pct_state = "확정" if "확정" in denom_note else "잠정"
    pct_s = f"{avg_pct}%" if isinstance(avg_pct, (int, float)) else "미측정"
    prelim_tag = "(잠정)" if pct_state == "잠정" else ""

    sig_emoji, sig_word = signal(avg_pct)

    top_day = max_issue_day(data.get("dailySeries") or [])
    top_day_label = top_day[0] if top_day else None

    improvements = data.get("improvements") or []
    tip = improvements[0] if improvements else "특이사항 없음"

    # 전월 대비 델타(전월 없으면/조회 실패면 화살표 생략 — graceful)
    pct_delta_s = ""
    issue_delta_s = ""
    if prev_data:
        prev_totals = prev_data.get("monthTotals", {}) or {}
        prev_avg = prev_totals.get("avgPct")
        prev_issue = prev_totals.get("issueCount")
        if isinstance(avg_pct, (int, float)) and isinstance(prev_avg, (int, float)):
            d = round(avg_pct - prev_avg, 1)
            if d > 0:
                pct_delta_s = f"▲{_fmt_num(d)}%p"
            elif d < 0:
                pct_delta_s = f"▼{_fmt_num(abs(d))}%p"
            else:
                pct_delta_s = "—"
        if isinstance(issue_count, (int, float)) and isinstance(prev_issue, (int, float)):
            di = issue_count - prev_issue
            if di > 0:
                issue_delta_s = f"▲{_fmt_num(di)}"
            elif di < 0:
                issue_delta_s = f"▼{_fmt_num(abs(di))}"
            else:
                issue_delta_s = "—"

    comp_seg = f"완료율 {pct_s}{prelim_tag}"
    if pct_delta_s:
        comp_seg += f" {pct_delta_s}"
    issue_seg = f"이슈 {issue_count}건"
    if issue_delta_s:
        issue_seg += f" {issue_delta_s}"

    lines = [
        f"📊 <b>{lbl} 점검 월간 — {sig_emoji} {sig_word}</b>",
        f"{comp_seg} · {issue_seg} · 최다 {top_day_label or '없음'}",
        f"👉 {tip}",
        f"자세히 ▸ {PAGE_URL}",
    ]
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
    """카드를 점검관리방(TELEGRAM_CHECK_CHAT_ID, 폴백 -5136037543)에 발송. 성공 True."""
    token = _env_val("TELEGRAM_BOT_TOKEN")
    chat_id = _env_val("TELEGRAM_CHECK_CHAT_ID") or DEFAULT_CHECK_CHAT_ID
    if not token:
        print("[WARN] 텔레그램 토큰 미설정(.env) — 카드 발송 생략")
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
            print(f"[INFO] 점검 월간 카드 발송 {'성공' if ok else '실패'} (chat={chat_id})")
            return ok
    except Exception:
        print("[WARN] 카드 발송 실패 (토큰 trace 노출 방지로 상세 미출력)")
        return False


def log_event(event: str, **fields) -> None:
    """status/support_monthly_report_log.jsonl 1행 append (발송·부작용 추적). 신규 전용 로그 — 다른 status/*.json 무변경."""
    rec = {"event": event, "logged_at": now_str(), **fields}
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 로그 기록 실패: {e}")


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(send: bool = False, force: bool = False, month_override: str | None = None) -> str:
    now = datetime.now()
    label = "라이브 발송(--send)" if send else "드라이런"
    print(f"[시작] 지원부 점검 월간 리포트 ({label}) — {now_str()}")

    # 매월1일 가드 — send인데 1일 아니면 라이브 부작용 생략(오발송 방지). 드라이런·--force는 통과.
    if send and not force and now.day != 1:
        print(f"[가드] 오늘({now.strftime('%Y-%m-%d')})은 매월 1일 아님 — 라이브 발송 생략(--force로 무시 가능)")
        log_event("send_skipped", reason="not_day1", date=now.strftime("%Y-%m-%d"))
        return ""

    month = month_override or prev_month_key(now)
    print(f"[1/3] GAS monthly_report(dept=support, month={month}) 조회...")
    data = fetch_monthly_report(month)
    if data is None:
        print("[에러] 집계 조회 실패 — 카드 생성 중단(지어내기 금지)")
        log_event("fetch_failed", month=month)
        return ""

    prev_month = prev_month_key_str(month)
    print(f"[2/3] GAS monthly_report(dept=support, month={prev_month}) 전월대비 조회...")
    prev_data = fetch_monthly_report(prev_month)  # 실패/None이어도 graceful — 델타 생략, 본 리포트는 정상 진행

    card = build_card(data, month, prev_data)
    print(f"\n{'='*60}")
    print(card.replace("<b>", "").replace("</b>", ""))
    print(f"{'='*60}\n")

    if send:
        sent = send_card(card)
        log_event("monthly_check_report", month=month, sent=sent)
        print(f"[3/3] 발송 완료 (텔레그램 {'발송' if sent else '미발송'}) — {now_str()}")
    else:
        print("  (드라이런 — 텔레그램 발송·로그는 --send. 1일 가드는 --send 시만 적용)")
    return card


def main():
    parser = argparse.ArgumentParser(
        description="지원부 점검 월간 리포트 매월 1일 자동 요약 카드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--send", action="store_true",
                        help="라이브 발송 — 점검관리방 텔레그램 카드 + 로그 (예약 진입점)")
    parser.add_argument("--dry-run", action="store_true",
                        help="드라이런(기본 동작) — 카드 콘솔 출력만, 라이브 부작용 없음")
    parser.add_argument("--force", action="store_true",
                        help="매월 1일 가드 무시(수동 테스트용, --send와 함께 사용)")
    parser.add_argument("--month", default=None,
                        help="특정 월(YYYY-MM) 강제 지정 — 테스트용(드라이런 권장, 기본=전월 자동계산)")
    args = parser.parse_args()
    run(send=args.send, force=args.force, month_override=args.month)


if __name__ == "__main__":
    main()
