# -*- coding: utf-8 -*-
"""
주차 매출 크롤러 (parking_revenue_crawler)
─────────────────────────────────────────────
웰페리온 주차관리시스템(THEHAM)에 자동 로그인 → 이번달 매출(결제금액)을
매일 수집해 status/parking_revenue.json 으로 발행한다.
GM은 주차 시스템을 매번 열지 않아도, 이 한 파일이 매출 보고·KPI의 데이터 소스가 된다.

데이터 출처 (라이브 실측 2026-06-19):
  - 로그인:  POST {BASE}/login.htm  (loginId/loginPw 평문 폼, 세션쿠키 JSESSIONID_ADMIN)
  - 정산:    POST {BASE}/report/getParkCloseList  (application/json)
             body = {searchParkId, searchType:"start", searchStartDt, searchEndDt(YYYYMMDD), searchDcSellYn:0}
             응답 result.data[] 각 행: stdDtStr, payCnt, payAmt(실결제), dcAmt(할인감면),
                                       cancelPayCnt, cancelPayAmt, inCnt, outCnt ...
  - "매출금액" = payAmt 합(실결제 현금). 할인감면(dcAmt)은 참고로 함께 발행.

사용:
  python scripts/parking_revenue_crawler.py            # 이번달 수집 → status/parking_revenue.json
  python scripts/parking_revenue_crawler.py --push     # 수집 + git 커밋·푸시 (ERP/보고 반영)
  python scripts/parking_revenue_crawler.py --month 2026-05   # 특정 월

설계 원칙: 모든 단계는 실패해도 예외로 죽지 않고 status='이상'으로 떨어진다(fail-safe).
자격증명은 telegram_bot/.env 단일출처(PARKING_*)에서만 읽는다 — 코드 하드코딩 금지.
값은 사람이 바로 읽는 한국어 plain text로 채운다(약속 L10/L12).
"""
import json
import sys
try:  # Windows cp949 콘솔에서도 한글/기호 출력이 죽지 않게 (예약작업 안전)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
OUT = STATUS_DIR / "parking_revenue.json"
ENV_PATH = ROOT / "telegram_bot" / ".env"

DEFAULTS = {
    "PARKING_BASE_URL": "http://ppark-wall.iptime.org:8280",
    "PARKING_PARK_ID": "1057",
    "PARKING_LOGIN_ID": "",
    "PARKING_LOGIN_PW": "",
}


def _now_kst():
    return datetime.now(KST)


def _read_env():
    """telegram_bot/.env 직독 → PARKING_* 설정. 누락은 DEFAULTS로."""
    vals = dict(DEFAULTS)
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in DEFAULTS:
                vals[k] = v.strip()
    except Exception:
        pass
    return vals


def _month_range(month_str=None):
    """('YYYYMMDD' 시작, 'YYYYMMDD' 끝, 'YYYY-MM' 라벨). month_str=None이면 이번달 1일~오늘(KST)."""
    now = _now_kst()
    if month_str:
        y, m = (int(x) for x in month_str.split("-"))
        start = datetime(y, m, 1, tzinfo=KST)
        # 해당 월 말일 또는 오늘 중 이른 쪽
        nm = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=KST)
        last = nm - timedelta(days=1)
        end = min(last, now) if (y == now.year and m == now.month) else last
    else:
        start = now.replace(day=1)
        end = now
        y, m = now.year, now.month
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), f"{y:04d}-{m:02d}"


def _build_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj)), cj


def _login(opener, base, login_id, login_pw, timeout=20):
    """폼 로그인. 성공(로그인페이지로 재튕기지 않음) 시 True."""
    data = urllib.parse.urlencode({"loginId": login_id, "loginPw": login_pw}).encode()
    req = urllib.request.Request(f"{base}/login.htm", data=data)
    with opener.open(req, timeout=timeout) as r:
        final = r.geturl()
    # 인증 실패 시 /login.htm 으로 되돌아옴
    return "/login.htm" not in final


def _fetch_close_list(opener, base, park_id, start_dt, end_dt, timeout=30):
    body = json.dumps({
        "searchParkId": str(park_id),
        "searchType": "start",
        "searchStartDt": start_dt,
        "searchEndDt": end_dt,
        "searchDcSellYn": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/report/getParkCloseList", data=body,
        headers={"Content-Type": "application/json;charset=utf-8"},
    )
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def collect(month_str=None):
    """이번달(또는 지정월) 주차 매출 집계. 항상 dict 반환(실패해도 status='이상')."""
    env = _read_env()
    base = env["PARKING_BASE_URL"].rstrip("/")
    park_id = env["PARKING_PARK_ID"]
    start_dt, end_dt, label = _month_range(month_str)
    out = {
        "갱신시각": _now_kst().strftime("%Y-%m-%d %H:%M"),
        "월": label,
        "기간": f"{start_dt}~{end_dt}",
        "주차장": "웰페리온",
        "status": "이상",
        "메시지": "",
        "매출금액": 0,          # payAmt 합 = 실결제 현금 매출
        "결제건수": 0,
        "할인감면액": 0,        # dcAmt 합 = 회원 무료/감면(참고)
        "취소금액": 0,
        "수집일수": 0,
    }
    if not env["PARKING_LOGIN_ID"] or not env["PARKING_LOGIN_PW"]:
        out["메시지"] = "자격증명 없음(telegram_bot/.env PARKING_LOGIN_ID/PW 확인)"
        return out
    try:
        opener, _ = _build_opener()
        if not _login(opener, base, env["PARKING_LOGIN_ID"], env["PARKING_LOGIN_PW"]):
            out["메시지"] = "로그인 실패(ID/PW 또는 권한 확인)"
            return out
        res = _fetch_close_list(opener, base, park_id, start_dt, end_dt)
        rows = res.get("data")
        if not isinstance(rows, list):
            out["메시지"] = f"데이터 없음/오류: {str(res)[:120]}"
            return out
        out["매출금액"] = sum(int(r.get("payAmt") or 0) for r in rows)
        out["결제건수"] = sum(int(r.get("payCnt") or 0) for r in rows)
        out["할인감면액"] = sum(int(r.get("dcAmt") or 0) for r in rows)
        out["취소금액"] = sum(int(r.get("cancelPayAmt") or 0) for r in rows)
        out["수집일수"] = len(rows)
        out["status"] = "정상"
        out["메시지"] = f"{label} 실결제 매출 {out['매출금액']:,}원 / {out['결제건수']:,}건"
    except Exception as e:
        out["메시지"] = f"수집 예외: {type(e).__name__}: {str(e)[:120]}"
    return out


def _git_push():
    import subprocess
    try:
        subprocess.run(["git", "add", str(OUT)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore(parking): 주차 매출 현황 자동 발행 (parking_revenue.json)"],
            cwd=ROOT, check=True,
        )
        subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "master"], cwd=ROOT, check=False)
        subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=False)
    except subprocess.CalledProcessError:
        pass  # 변경 없음 등은 무해


def main():
    month = None
    if "--month" in sys.argv:
        i = sys.argv.index("--month")
        if i + 1 < len(sys.argv):
            month = sys.argv[i + 1]
    data = collect(month)
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parking_revenue] {data['status']} — {data['메시지']}")
    if "--push" in sys.argv:
        _git_push()


if __name__ == "__main__":
    main()
