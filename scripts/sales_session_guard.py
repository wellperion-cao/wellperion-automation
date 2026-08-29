# -*- coding: utf-8 -*-
"""매출보고 구글 세션 지킴이 — 만료를 아침에 미리 잡아 로그인 창만 띄운다 (배10021 · INC-033).

무엇을 하나
  09:30 매출보고 무인 발송보다 **앞서** 구글 세션이 살아있는지 한 번 확인하고,
  만료됐으면 **로그인 크롬 창만 조용히 띄운다.** 그게 전부다.

왜 이렇게 하나 (GM 2026-07-24 결정 = B안)
  구글 세션은 약 14일(passive=1209600) 주기로 반드시 만료된다. 그런데 지금까지는 그 사실을
  **09:30 발송하려는 순간에야** 알았고, 그때는 이미 회장님·관리부·운영부 보고가 펑크난 뒤였다
  (2026-07-24·2026-07-08 실사례). 탐지 시점이 복구 가능 시점보다 늦은 게 본질이다.

  ★알림은 한 통도 보내지 않는다. 배10011(GM 2026-07-24 '알림 신설 금지')과 부딪히지 않기 위해
  선택한 방식이다 — 텔레그램·카톡 대신 **화면에 뜬 로그인 창**이 신호다.

★함정 하나 (반드시 같이 봐야 함)
  profiles/danggn 로 크롬 창이 열려 있으면 프로필이 잠겨 09:30 무인 작업이 통째로 죽는다
  (2026-07-08 실사례). 이 지킴이는 로그인 창을 **일부러 띄우므로** 그 함정을 더 잘 밟게 만든다.
  그래서 짝으로 generate_sales_report_image.close_profile_chrome() 을 무인 작업 진입점에 박아,
  09:30 이 스스로 잠금을 풀고 들어가게 했다. 둘은 한 몸이라 따로 떼면 안 된다.

★이 파일은 generate_sales_report_image 의 시트 해석(resolve_sheet)에 의존한다 — 그쪽을
  고치면(예: 배277 SHEET_EDIT_URL 상수 제거) 여기도 함께 확인해야 한다. 판정기와 생성기가
  같은 edit URL 해석기를 보게 유지할 것(약속 L01, 배278 2026-08-01 시토).

사용:
  python scripts/sales_session_guard.py            # 점검 후 만료면 로그인 창 표출
  python scripts/sales_session_guard.py --check-only   # 점검만(창 안 띄움) — 진단·테스트용
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import generate_sales_report_image as G  # noqa: E402  (프로필·시트 주소 단일 출처)

CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def resolve_today() -> "tuple[str, str, str, str]":
    """오늘 날짜 기준 이달 시트를 한 번만 해석한다(약속 L01 — session_alive 가 다시
    resolve_sheet() 를 부르면 그 자체가 새 판정불가 지점이 된다 · 2026-08-26 실사고).
    반환: (sheet_id, gid, edit_url, 실패사유) — 해석 자체가 실패하면 나머지는 빈 문자열
    (로그인 문제가 아니므로 호출부는 로그인 창을 띄우면 안 된다)."""
    sheet_id, gid, resolve_fail = G.resolve_sheet(datetime.now())
    if resolve_fail:
        return "", "", "", resolve_fail
    return sheet_id, gid, f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit", ""


SESSION_ALIVE = "ALIVE"      # PDF 내려받기 성공 — 진짜 살아있음
SESSION_EXPIRED = "EXPIRED"  # export 가 로그인/세션만료로 막힘 — 진짜 만료
SESSION_UNKNOWN = "UNKNOWN"  # 재시도까지 다 했는데도 판정 자체를 못 함(로그인 문제 아닐 수 있음)

_PROBE_RETRIES = 3       # export_pdf 총 시도 횟수(판정불가일 때만 재시도)
_PROBE_RETRY_WAIT_SEC = 5


def session_alive(sheet_id: str, gid: str) -> "tuple[str, str]":
    """09:30 이 실제로 하는 그 동작(PDF 내려받기)을 그대로 해 본다. 반환 =
    (SESSION_ALIVE|SESSION_EXPIRED|SESSION_UNKNOWN, 상세).

    ★2026-08-15 실사고로 export_pdf() 그 함수 자체로 판정하게 바꿨다(편집 페이지는 열려도
      export 엔드포인트만 401 인 상태가 있었다 — 그날 08:10 은 "정상"을 찍고 09:30 이 펑크).
    ★2026-08-26 실사고 두 번째 구멍 — GAS 호출 일시 실패로 판정 자체가 안 될 때 이전 코드는
      **OK 와 똑같이** 취급해 "OK: 세션 정상"을 찍었다(만료도 판정불가도 결과가 안 갈림).
      이제 판정불가는 별도 상태(SESSION_UNKNOWN)로 반환하고, 그 자리에서 바로 포기하지
      않고 export_pdf 를 최대 _PROBE_RETRIES회까지 다시 시도한다 — 일시적인 GAS 실패로
      아침 점검을 통째로 건너뛰지 않기 위해서다. sheet_id/gid 는 호출부가 이미 해석해 준
      것을 그대로 받는다(약속 L01 — 여기서 다시 resolve_sheet() 를 부르면 그 두 번째
      호출 자체가 새로운 판정불가 지점이 된다).
    """
    import tempfile  # noqa: PLC0415
    import time  # noqa: PLC0415

    tmp = Path(tempfile.gettempdir()) / "wellperion_sales_session_probe.pdf"
    last_detail = ""
    for attempt in range(1, _PROBE_RETRIES + 1):
        try:
            ok, fail = G.export_pdf(tmp, sheet_id, gid)
        except Exception as exc:  # noqa: BLE001
            last_detail = f"판정불가(예외): {type(exc).__name__}: {exc}"
        else:
            if ok:
                return SESSION_ALIVE, "PDF 내려받기 성공" + (f" ({attempt}회차)" if attempt > 1 else "")
            if "세션만료" in fail or "로그인" in fail:
                # 진짜 만료 — 재시도해도 스스로 안 풀린다. 즉시 확정한다.
                return SESSION_EXPIRED, fail
            last_detail = f"판정불가: {fail}"
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        if attempt < _PROBE_RETRIES:
            G.log(f"[{attempt}/{_PROBE_RETRIES}] {last_detail} — {_PROBE_RETRY_WAIT_SEC}초 뒤 재시도")
            time.sleep(_PROBE_RETRY_WAIT_SEC)

    return SESSION_UNKNOWN, f"{_PROBE_RETRIES}회 재시도 후에도 판정 불가 — {last_detail}"


def open_login_window(edit_url: str) -> bool:
    """cao 로그인용 크롬 창을 띄운다. 메시지는 보내지 않는다."""
    chrome = next((c for c in CHROME_CANDIDATES if c.exists()), None)
    if chrome is None:
        G.log("[경고] chrome.exe 를 찾지 못해 로그인 창을 띄우지 못했습니다.")
        return False
    if G.profile_chrome_pids():
        G.log("이미 이 프로필 크롬 창이 열려 있습니다 — 중복으로 띄우지 않습니다.")
        return False
    subprocess.Popen([str(chrome), f"--user-data-dir={G.PERSISTENT_PROFILE_DIR}", edit_url])
    G.log("구글 세션 만료 — 로그인 창을 띄웠습니다(알림 발송 0통).")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="매출보고 구글 세션 지킴이(알림 없음)")
    ap.add_argument("--check-only", action="store_true", help="점검만 하고 로그인 창은 띄우지 않음")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("SKIP: Windows(cao 세션 프로필) 전용입니다.")
        return 0

    sheet_id, gid, edit_url, resolve_fail = resolve_today()
    if resolve_fail:
        # 시트 해석 자체가 실패(그 달 시트가 아직 없음 등) — 로그인 문제가 아니므로
        # 로그인 창을 띄우지 않는다.
        G.log(f"세션 점검 스킵 — 시트 해석 실패(로그인 문제 아님): {resolve_fail}")
        print(f"SKIP: 시트 해석 실패(로그인 문제 아님) — {resolve_fail}")
        return 0

    status, detail = session_alive(sheet_id, gid)
    label = {SESSION_ALIVE: "살아있음", SESSION_EXPIRED: "만료", SESSION_UNKNOWN: "판정불가"}[status]
    G.log(f"세션 판정: {label} — {detail}")

    if status == SESSION_ALIVE:
        print("OK: 세션 정상")
        return 0
    if status == SESSION_UNKNOWN:
        # ★재시도 다 했는데도 판정 못 함 — '만료'로 단정해 로그인 창을 띄우지도, 'OK'로
        # 뭉개지도 않는다. 로그·호출부(daily_scheduler)가 EXPIRED/OK 와 다른 결과로
        # 구분해야 그날 점검이 실제로 안 됐다는 사실이 남는다(배11025 실사고).
        print(f"UNKNOWN: 세션 판정 불가(재시도 {_PROBE_RETRIES}회 소진) — {detail}")
        return 2
    if args.check_only:
        print("EXPIRED: 세션 만료(창 안 띄움 — --check-only)")
        return 1
    open_login_window(edit_url)
    print("EXPIRED: 세션 만료 — 로그인 창 표출")
    return 1


if __name__ == "__main__":
    sys.exit(main())
