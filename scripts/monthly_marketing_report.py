"""
웰페리온 CMO — 월간 마케팅 보고서 자동 생성 및 텔레그램 발송 스크립트

담당: AI CMO 시모 | 실무진: 김남욱 GM
버전: 1.0 (2026-06-06)

개인정보(이름·연락처) 절대 미포함 — 집계 카운트만 처리합니다.

──────────────────────────────────────────────────────────
Task Scheduler 등록 명령 (매월 1일 09:00, 관리자 권한으로 실행 필요)
──────────────────────────────────────────────────────────
schtasks /create ^
  /tn "Wellperion-CMO-Monthly-Report" ^
  /tr "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NonInteractive -WindowStyle Hidden -Command \"python 'C:\\Users\\jjky0\\welperion-automation\\scripts\\monthly_marketing_report.py'\"" ^
  /sc MONTHLY /d 1 /st 09:00 ^
  /ru SYSTEM /f

* /ru SYSTEM 대신 관리자 계정명을 지정해도 됩니다.
* 예약작업 등록은 GM이 관리자 권한으로 1회 수동 실행합니다.
──────────────────────────────────────────────────────────
"""

import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

# Windows 콘솔(cp949)·예약작업 환경에서도 이모지·한글 print가 깨지거나 죽지 않도록
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# requests 없으면 urllib 폴백
try:
    import requests as _requests

    def _http_get(url, timeout=15):
        resp = _requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

except ImportError:
    import urllib.request
    import urllib.error

    def _http_get(url, timeout=15):
        req = urllib.request.Request(url, headers={"User-Agent": "WellperionCMO/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


# ── 경로 설정 (telegram_notifier 재사용) ──────────────────────────
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_AGENTS_DIR   = os.path.join(_SCRIPT_DIR, "..", "wellperion-agents")
_DOTENV_PATH  = os.path.join(_SCRIPT_DIR, ".env")

# dotenv 수동 로드 (python-dotenv 없는 환경 대비)
def _load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv(_DOTENV_PATH)
_load_dotenv(os.path.join(_AGENTS_DIR, ".env"))

# ── 환경변수 ─────────────────────────────────────────────────────
GAS_URL           = "https://script.google.com/macros/s/AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
# 서버 API 거울(cmo/_api.js wpCmoRead 와 동일 규격) — 우선 조회, 실패 시 GAS 폴백.
SERVER_API_BASE    = "https://erp.wellperion.com/api/funnel"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


# ── TelegramNotifier 재사용 시도, 실패 시 인라인 fallback ──────────
def _try_import_notifier():
    """wellperion-agents/telegram_notifier.py 재사용."""
    _agents = os.path.abspath(_AGENTS_DIR)
    if _agents not in sys.path:
        sys.path.insert(0, _agents)
    try:
        from telegram_notifier import TelegramNotifier
        return TelegramNotifier()
    except Exception:
        return None


def _send_telegram_fallback(text):
    """telegram_notifier import 실패 시 urllib 직접 발송."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — 텔레그램 발송 생략")
        return False
    try:
        return _tg_send(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text,
                         source="monthly_marketing_report._send_telegram_fallback",
                         extra={"parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print(f"[ERROR] 텔레그램 발송 실패: {e}")
        return False


def send_message(text):
    notifier = _try_import_notifier()
    if notifier:
        result = notifier.send(text)
        return bool(result.get("ok", False))
    return _send_telegram_fallback(text)


# ── 데이터 수집 (서버 API 우선 → GAS 폴백) ─────────────────────────
def _fetch_action(action, params=None):
    """서버 API(erp.wellperion.com/api/funnel) 우선 조회, 실패(비로그인 401/302·다운) 시
    같은 파라미터로 GAS 웹앱에 폴백. 둘 다 실패하면 None."""
    qs = "action=" + action
    for k, v in (params or {}).items():
        qs += f"&{k}={v}"
    try:
        data = _http_get(SERVER_API_BASE + "?" + qs, timeout=10)
        if isinstance(data, dict) and data.get("ok") is not False:
            return data
        print(f"[WARN] 서버 API {action} 비정상 응답 — GAS 폴백")
    except Exception as e:
        print(f"[WARN] 서버 API {action} 실패({e}) — GAS 폴백")
    try:
        data = _http_get(GAS_URL + "?" + qs, timeout=20)
        if not data.get("ok"):
            print(f"[WARN] GAS {action} ok=false: {data}")
            return None
        return data
    except Exception as e:
        print(f"[WARN] GAS {action} 수집 실패: {e}")
        return None


def fetch_period_breakdown(from_d, to_d):
    """period_breakdown 액션 — from/to(YYYY-MM-DD)로 대상월 custom 집계를 받는다."""
    return _fetch_action("period_breakdown", {"from": from_d, "to": to_d})


def fetch_type_channel_breakdown(from_d, to_d):
    """type_channel_breakdown 액션 — period_breakdown과 별도 집계 루틴(원장 재수집·전화+유형 dedup).
    문의 접수 수 대조(교차검증)용 — 같은 원천을 다른 경로로 한 번 더 센다."""
    return _fetch_action("type_channel_breakdown", {"from": from_d, "to": to_d})


def fetch_funnel_conversion():
    """funnel_conversion 액션 — 참고용 전체 누적(월 무관, 종전 동작 그대로)."""
    return _fetch_action("funnel_conversion")


# ── 숫자 포맷 ────────────────────────────────────────────────────
def _fmt(n, unit=""):
    if n is None:
        return "—"
    return f"{int(n):,}{unit}"


def _fmt_rate(r):
    if r is None:
        return "—"
    return f"{float(r):.1f}%"


# ── 대상월 계산 (기본 = 실행일 기준 전월) ──────────────────────────
def _prev_month_str(dt):
    y, m = dt.year, dt.month
    return f"{y-1}-12" if m == 1 else f"{y}-{m-1:02d}"


def _month_bounds(month_str):
    """'YYYY-MM' → (from_d, to_d, month_ko) — 그 달 1일~말일, GAS from/to(YYYY-MM-DD)용."""
    y, m = (int(x) for x in month_str.split("-"))
    from_d = f"{y}-{m:02d}-01"
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last_day = (datetime.date(ny, nm, 1) - datetime.timedelta(days=1)).day
    to_d = f"{y}-{m:02d}-{last_day:02d}"
    return from_d, to_d, f"{y}년 {m}월"


# ── 월간 요약 텍스트 작성 ────────────────────────────────────────
def build_report_text(pb, tc, fc, month_ko):
    # pb.custom = period_breakdown(from/to) 응답 — 대상월(전월) 기준 실측치
    custom = (pb or {}).get("custom") or {}

    # 문의 페이지 클릭 — GAS 어떤 액션에도 클릭 집계 자체가 없음(2026-09 확인).
    # 값이 생기면 그대로 쓰고, 없으면 0으로 위장하지 않고 정직하게 「미측정」 표기.
    clicks = None
    if isinstance((pb or {}).get("clicks"), dict):
        clicks = pb["clicks"].get("month")
    clicks_str = _fmt(clicks, "회") if clicks is not None else "미측정"

    inq_m    = custom.get("inquiries")
    conv_cnt  = (custom.get("conversion") or {}).get("converted")
    conv_rate = (custom.get("conversion") or {}).get("rate")

    # 문의 접수 수 대조 — type_channel_breakdown(별도 수집 루틴)으로 같은 기간을 한 번 더 세어 비교.
    # 요약줄을 그대로 옮기지 않고, 다른 경로로 나온 원장 카운트끼리 맞춰본다.
    tc_total = ((tc or {}).get("overall") or {}).get("total")
    if inq_m is not None and tc_total is not None and inq_m != tc_total:
        print(f"[WARN] 문의 접수 수 불일치 — period_breakdown={inq_m}건 vs type_channel_breakdown={tc_total}건 (표기는 period_breakdown 값)")

    # 대상월 채널별 문의 (period_breakdown custom.byChannel — 지정 기간 단위)
    by_ch_month = custom.get("byChannel") or {}
    ch_month_lines = ""
    if by_ch_month:
        sorted_chm = sorted(by_ch_month.items(), key=lambda x: x[1], reverse=True)[:5]
        ch_month_lines = "\n".join(f"  · {ch}: {_fmt(cnt, '건')}" for ch, cnt in sorted_chm)

    # 참고: 전체 누적 채널별 전환율 (funnel_conversion — 월 구분 없음, 누적값임을 명시)
    ch_list = (fc.get("byChannel") if fc else None) or []
    cum_lines = ""
    if isinstance(ch_list, list) and ch_list:
        top3 = sorted(ch_list, key=lambda d: d.get("inquiries", 0), reverse=True)[:3]
        cum_lines = "\n".join(
            f"  · {d.get('channel', '기타')}: 누적 {_fmt(d.get('inquiries', 0), '건')}"
            f" · 전환율 {_fmt_rate(d.get('rate'))}"
            for d in top3
        )

    # 대상월 문의 유형별 (period_breakdown custom.byType)
    by_type = custom.get("byType") or {}
    type_lines = ""
    if by_type:
        sorted_tp = sorted(by_type.items(), key=lambda x: x[1], reverse=True)
        type_lines = "\n".join(
            f"  · {tp}: {_fmt(cnt, '건')}"
            for tp, cnt in sorted_tp
        )

    # 전환율 평가
    rate_comment = ""
    if conv_rate is not None:
        r = float(conv_rate)
        if r >= 15:
            rate_comment = "양호 — 노출 확대 집중 권장"
        elif r >= 5:
            rate_comment = "개선 여지 — 응대 속도·CTA 강화 검토"
        else:
            rate_comment = "저조 — 문의→상담 연결 프로세스 점검 필요"

    lines = [
        f"📣 <b>[CMO] 웰페리온 마케팅 월간 보고 — {month_ko}</b>",
        "",
        "📊 <b>실데이터 3종 집계</b>",
        f"  · 문의 페이지 클릭: {clicks_str}",
        f"  · 문의 접수: {_fmt(inq_m, '건')}",
        f"  · 회원 전환: {_fmt(conv_cnt, '명')}",
        f"  · 전환율: {_fmt_rate(conv_rate)}" + (f" ({rate_comment})" if rate_comment else ""),
    ]

    if ch_month_lines:
        lines += ["", "📍 <b>이번 달 채널별 문의</b>", ch_month_lines]

    if type_lines:
        lines += ["", "🗂 <b>이번 달 문의 유형별</b>", type_lines]

    if cum_lines:
        lines += ["", "📈 <b>참고 · 전체 누적 채널별 전환율</b>", cum_lines]

    lines += [
        "",
        "📌 노출·인지·관심 지표는 외부 플랫폼 수기 입력 — 보고서 페이지에서 추가 확인 요망.",
        "",
        "📄 상세 보고서 → 웰페리온 ERP (M2 마케팅 현황 대시보드 → 월간 보고서)",
    ]

    return "\n".join(lines)


# ── 메인 ────────────────────────────────────────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="텔레그램 실제 발송 생략 — 보고서 텍스트만 stdout 출력 (배944 서버 병행검증용)")
    ap.add_argument("--month", default=None,
                     help="집계 대상월 'YYYY-MM' (미지정 시 실행일 기준 전월)")
    args = ap.parse_args()

    month_str = args.month or _prev_month_str(datetime.datetime.now())
    from_d, to_d, month_ko = _month_bounds(month_str)

    print(f"[INFO] 웰페리온 CMO 월간 마케팅 보고서 생성 시작 — 대상월 {month_ko} ({from_d}~{to_d})")

    pb = fetch_period_breakdown(from_d, to_d)
    tc = fetch_type_channel_breakdown(from_d, to_d)
    fc = fetch_funnel_conversion()

    if pb is None and fc is None:
        print("[WARN] 데이터 전체 수집 실패 — 빈 보고서 발송")

    report_text = build_report_text(pb, tc, fc, month_ko)
    print("[INFO] 보고서 텍스트 생성 완료")
    print("─" * 60)
    print(report_text)
    print("─" * 60)

    if args.dry_run:
        print("[INFO] --dry-run: 텔레그램 실제 발송 생략")
        return

    ok = send_message(report_text)
    if ok:
        print("[INFO] 텔레그램 발송 완료")
    else:
        print("[ERROR] 텔레그램 발송 실패")
        sys.exit(1)


def _selfcheck():
    """월 경계 계산 로직 최소 검증 — 실행: python monthly_marketing_report.py --selfcheck"""
    assert _prev_month_str(datetime.datetime(2026, 9, 5)) == "2026-08"
    assert _prev_month_str(datetime.datetime(2026, 1, 15)) == "2025-12"
    assert _month_bounds("2026-08") == ("2026-08-01", "2026-08-31", "2026년 8월")
    assert _month_bounds("2026-02") == ("2026-02-01", "2026-02-28", "2026년 2월")  # 평년
    assert _month_bounds("2028-02") == ("2028-02-01", "2028-02-29", "2028년 2월")  # 윤년
    print("[OK] selfcheck 통과")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
        sys.exit(0)
    main()
