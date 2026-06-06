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
GAS_URL           = "https://script.google.com/macros/s/AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec"
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
    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    try:
        import urllib.request
        req  = urllib.request.Request(url, data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("ok", False)
    except Exception as e:
        print(f"[ERROR] 텔레그램 발송 실패: {e}")
        return False


def send_message(text):
    notifier = _try_import_notifier()
    if notifier:
        result = notifier.send(text)
        return bool(result.get("ok", False))
    return _send_telegram_fallback(text)


# ── GAS 데이터 수집 ───────────────────────────────────────────────
def fetch_period_breakdown():
    """period_breakdown 액션 호출. 실패 시 None 반환."""
    try:
        data = _http_get(GAS_URL + "?action=period_breakdown", timeout=20)
        if not data.get("ok"):
            print(f"[WARN] period_breakdown ok=false: {data}")
            return None
        return data
    except Exception as e:
        print(f"[WARN] period_breakdown 수집 실패: {e}")
        return None


def fetch_funnel_conversion():
    """funnel_conversion 액션 호출. 실패 시 None 반환."""
    try:
        data = _http_get(GAS_URL + "?action=funnel_conversion", timeout=20)
        return data
    except Exception as e:
        print(f"[WARN] funnel_conversion 수집 실패: {e}")
        return None


# ── 숫자 포맷 ────────────────────────────────────────────────────
def _fmt(n, unit=""):
    if n is None:
        return "—"
    return f"{int(n):,}{unit}"


def _fmt_rate(r):
    if r is None:
        return "—"
    return f"{float(r):.1f}%"


# ── 월간 요약 텍스트 작성 ────────────────────────────────────────
def build_report_text(pb, fc):
    now      = datetime.datetime.now()
    month_ko = f"{now.year}년 {now.month}월"

    # period_breakdown 값 추출 (month 단위)
    clicks   = pb["clicks"]["month"]    if pb and "clicks"    in pb else None
    inq_m    = pb["inquiries"]["month"] if pb and "inquiries" in pb else None
    conv_cnt = None
    conv_rate = None
    if pb and "conversion" in pb and "month" in pb["conversion"]:
        conv_cnt  = pb["conversion"]["month"].get("converted")
        conv_rate = pb["conversion"]["month"].get("rate")

    # 이번 달 채널별 문의 (byChannelMonth — 월 단위, 월간 보고서 단위 일치)
    by_ch_month = {}
    if pb and "inquiries" in pb:
        by_ch_month = pb["inquiries"].get("byChannelMonth", {}) or {}
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

    # 유형별
    by_type = {}
    if pb and "inquiries" in pb:
        by_type = pb["inquiries"].get("byTypeMonth", {})
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
        f"  · 문의 페이지 클릭: {_fmt(clicks, '회')}",
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
        "📄 상세 보고서 → 웰페리온 ERP (M4 마케팅 현황 대시보드 → 월간 보고서)",
    ]

    return "\n".join(lines)


# ── 메인 ────────────────────────────────────────────────────────
def main():
    print("[INFO] 웰페리온 CMO 월간 마케팅 보고서 생성 시작")

    pb = fetch_period_breakdown()
    fc = fetch_funnel_conversion()

    if pb is None and fc is None:
        print("[WARN] GAS 데이터 전체 수집 실패 — 빈 보고서 발송")

    report_text = build_report_text(pb, fc)
    print("[INFO] 보고서 텍스트 생성 완료")
    print("─" * 60)
    print(report_text)
    print("─" * 60)

    ok = send_message(report_text)
    if ok:
        print("[INFO] 텔레그램 발송 완료")
    else:
        print("[ERROR] 텔레그램 발송 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
