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


def resolve_today_edit_url() -> "tuple[str, str]":
    """오늘 날짜 기준 이달 시트의 edit URL을 만든다. G.resolve_sheet()를 재사용해 판정기와
    생성기가 같은 해석기를 보게 한다(약속 L01). 반환: (edit_url, 실패사유) — 그 달 시트가
    아직 없는 등 해석 자체가 실패하면 edit_url은 빈 문자열(로그인 문제가 아니므로 호출부는
    로그인 창을 띄우면 안 된다)."""
    sheet_id, gid, resolve_fail = G.resolve_sheet(datetime.now())
    if resolve_fail:
        return "", resolve_fail
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit", ""


def session_alive() -> "tuple[bool, str]":
    """09:30 이 실제로 하는 그 동작(PDF 내려받기)을 그대로 한 번 해 본다.

    ★2026-08-15 실사고로 바꿨다. 그 전에는 **시트 편집 페이지가 로그인으로 튕기는지만**
      보고 "가볍게" 판정했다. 그런데 구글은 편집 페이지는 열어 주면서 export 엔드포인트만
      401 로 막는 상태가 있다 — 실제로 그날 08:10 지킴이는 "세션 정상"을 찍었고, 같은
      세션으로 09:30 매출보고가 401 로 펑크났다(로그 실측). 판정이 실동작과 다르면 그
      판정은 매일 OK 만 찍는 장식이 된다.
    ▸그래서 판정을 생성기의 export_pdf() **그 함수 자체**로 한다 — 판정용 사본을 따로
      만들지 않는다(약속 L01). 받은 PDF 는 임시 파일이라 바로 지운다.
    """
    import tempfile  # noqa: PLC0415

    sheet_id, gid, resolve_fail = G.resolve_sheet(datetime.now())
    if resolve_fail:
        return True, f"판정 스킵(시트 해석 실패 — 로그인 문제 아님): {resolve_fail}"

    tmp = Path(tempfile.gettempdir()) / "wellperion_sales_session_probe.pdf"
    try:
        ok, fail = G.export_pdf(tmp, sheet_id, gid)
    except Exception as exc:  # noqa: BLE001
        # 판정 불가는 '만료'로 단정하지 않는다 — 괜히 로그인 창을 띄우면 프로필만 잠근다.
        return True, f"판정 불가(예외라 살아있는 것으로 간주): {type(exc).__name__}: {exc}"
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

    if ok:
        return True, "PDF 내려받기 성공"
    # export 가 막힌 것만 '만료'로 본다. 그 밖의 실패(네트워크·예외)는 살아있는 것으로 둔다.
    if "세션만료" in fail or "로그인" in fail:
        return False, fail
    return True, f"판정 불가(살아있는 것으로 간주): {fail}"


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

    edit_url, resolve_fail = resolve_today_edit_url()
    if resolve_fail:
        # 시트 해석 자체가 실패(그 달 시트가 아직 없음 등) — 로그인 문제가 아니므로
        # 로그인 창을 띄우지 않는다.
        G.log(f"세션 점검 스킵 — 시트 해석 실패(로그인 문제 아님): {resolve_fail}")
        print(f"SKIP: 시트 해석 실패(로그인 문제 아님) — {resolve_fail}")
        return 0

    alive, detail = session_alive()
    G.log(f"세션 판정: {'살아있음' if alive else '만료'} — {detail}")
    if alive:
        print("OK: 세션 정상")
        return 0
    if args.check_only:
        print("EXPIRED: 세션 만료(창 안 띄움 — --check-only)")
        return 1
    open_login_window(edit_url)
    print("EXPIRED: 세션 만료 — 로그인 창 표출")
    return 1


if __name__ == "__main__":
    sys.exit(main())
