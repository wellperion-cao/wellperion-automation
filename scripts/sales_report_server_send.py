#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매출 및 회원 현황 보고 서버판 — 매일 09:00 업무보고방(8254867551)에 1~3면 사진으로 (배1061 · 시토 · 2026-09-05 → GM 지시 2026-09-14 개편).

★2026-09-14 GM 지시(15:5x): 「서버판은 매일 아침 09:00(기존 09:30 카톡 30분 전) 업무보고방에 · 09:30 은 원래대로 ·
9월 말까지 신뢰되면 10/1 부터 서버판으로 전환 · 숫자만 나오는 요약표(Pillow 폴백)는 삭제·금지 · 무조건 1~3면
(매출 및 회원 현황 보고 / 문의 등록 상세 / 운영 현황)으로」.
  · 그림은 GM PC 에서만 찍을 수 있다(playwright·크롬) — 서버엔 브라우저가 없다(rc=127 실측). 그래서 발송 주체가 갈린다:
      GM PC 예약작업 Wellperion-SalesReport-Server-0900 (09:00) → 1~3면 사진 3장 (switch mode=gmpc_0900)
      서버 cron 09:02 → 22칸 대조 한 줄(글)만 — 대조는 서버 DB(sales_cache)에서만 셀 수 있다(--check-line)
  · 캡처 실패 = 사진 대신 「실패 사유 한 줄」을 같은 방에 보낸다. 요약표 폴백(render.render_png)은 더 이상 안 쓴다.
  · 캡처 주소·3면 규약 = scripts/report_page_capture.py(PAGES3).


★정본 병합(GM 지시 2026-09-10) — 정본은 「매출 및 회원 현황보고」 화면(erp.wellperion.com/coo/
report/매출회원현황보고.html)이다. 여기서 보내는 사진은 그 화면과 같은 계산(sales_report_render.
build_report — 화면도 /api/report/sales_report_cells 로 같은 함수를 부른다)의 요약본이지, 별도
"서버 판"이 아니다. 캡션에 화면 링크를 달아 어느 쪽이 정본인지 항상 밝힌다.

원칙 = 기존 경로(시트 → GAS → 09:00 텔레그램 · 09:30 카톡 3방 · generate_sales_report_image.py)
무접촉. 이 스크립트 하나만 sales_report_render 가 그린 표를 업무보고방 한 곳에만 sendPhoto +
22칸 대조 한 줄 캡션으로 보낸다. 킬스위치 status/sales_report_server_switch.json {"mode": ...}
— "parallel" 일 때만 발송(그 외는 조용히 스킵). "live"(3방 전환)는 3일 무결 확인 뒤 별도 구현.

실행: cd /srv/erp/repo && python3 scripts/sales_report_server_send.py
cron(서버 · KST): 20 9 * * * cd /srv/erp/repo && python3 scripts/sales_report_server_send.py >> logs/sales_report_server_send.log 2>&1
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 서버 배포 표준 경로(/srv/erp/api — 다른 api_*.py 와 같은 자리 · scp 배포)를 먼저 찾고,
# 없으면 이 저장소의 server/erp_api 를 쓴다(로컬 실행 · repo 클론이 server/ 를 sparse-checkout
# 밖에 둘 수 있어 실서버 cron 에서는 항상 앞쪽이 잡힌다).
_DEPLOYED = Path("/srv/erp/api")
ERP_API_DIR = _DEPLOYED if _DEPLOYED.is_dir() else (ROOT / "server" / "erp_api")
sys.path.insert(0, str(ERP_API_DIR))
sys.path.insert(0, str(ROOT / "scripts"))


def _render():
    """서버 전용 계산기(sales_report_render → sync_sales → DB) — GM PC 엔 DB 드라이버가 없어 필요할 때만 읽는다."""
    import sales_report_render as render  # noqa: WPS433
    return render


from tg_outbound_log import send as tg_send  # noqa: E402

SWITCH_PATH = ROOT / "status" / "sales_report_server_switch.json"
REPORT_ROOM = "8254867551"        # 업무보고방(@namuki_report_bot) — CLAUDE.md 0장
SCREEN_URL = "https://erp.wellperion.com/coo/report/매출회원현황보고.html"
PAGE_TITLES = ("매출 및 회원 현황 보고", "문의 등록 상세", "운영 현황")
ON_SERVER = _DEPLOYED.is_dir()


def _gm_pc_env():
    """GM PC 실행 — 봇 토큰은 telegram_bot/.env(TELEGRAM_BOT_TOKEN · notify_gm_progress 와 같은 열쇠)."""
    env = {}
    try:
        for line in (ROOT / "telegram_bot" / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env.get("TELEGRAM_BOT_TOKEN", ""), REPORT_ROOM


def _ref_date():
    """보고 기준일 = 어제(KST) — 09:30 카톡 보고와 같은 기준."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=1)).strftime("%Y-%m-%d")


def send_three_pages(token, chat, paths, ref_date, note, dry_run=False):
    """1~3면 사진 3장 — 1면 캡션에 제목·기준일·판 안내, 2·3면은 면 이름만."""
    head = ("매출 및 회원 현황 보고 · 기준일 %s · 서버판 09:00(병행 · 10/1 전환 예정) · 정본 %s"
            % (ref_date, SCREEN_URL))
    caps = ["%s\n1/3 %s%s" % (head, PAGE_TITLES[0], note),
            "2/3 %s · 기준일 %s" % (PAGE_TITLES[1], ref_date),
            "3/3 %s · 기준일 %s" % (PAGE_TITLES[2], ref_date)]
    ok_all, ids = True, []
    for png, cap in zip(paths, caps):
        if dry_run:
            print("[dry-run] %s ← %s" % (cap.replace("\n", " / "), png))
            continue
        resp = tg_send(token, chat, cap, source="sales_report_server_send", photo=png, full_response=True)
        ok = bool(isinstance(resp, dict) and resp.get("ok"))
        ok_all = ok_all and ok
        ids.append((resp.get("result") or {}).get("message_id") if isinstance(resp, dict) else None)
    return ok_all, ids


def server_check_note():
    """GM PC 09:00 캡션에 붙는 서버 원천 대조 한 줄 (GM 지시 2026-09-15 「시트 보고는 그대로 두고
    ERP 매출·회원현황보고만 서버에서 가져와 체크」). 서버 렌더러가 이미 22칸을 계산해 두므로
    (/api/report/sales_report_cells · build_report 재사용) 그 결과만 받아 적는다 — 새 계산·새 경로 없음.
    로그인 쿠키는 기존 ERP_SESSION_TOKEN 하나(telegram_bot/.env). 못 받으면 빈 문자열이라 발송은 안 막는다."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import requests
        from collectors.ops_shared import _env_line, ERP_API_BASE
        tok = _env_line("ERP_SESSION_TOKEN")
        if not tok:
            return ""
        r = requests.get(ERP_API_BASE + "/api/report/sales_report_cells",
                         headers={"Cookie": "erp_session=" + tok}, timeout=40)
        if r.status_code != 200:
            return " · 서버 원천 대조 못함(권한·응답 %s)" % r.status_code
        d = r.json()
        if not isinstance(d.get("total"), int):
            return " · 서버 원천 대조 못함(응답 모양 다름)"
        note = " · 서버 원천 대조 %d/%d 일치" % (d["matched"], d["total"])
        if d.get("mismatches"):
            note += " · 다른 칸: " + ", ".join(d["mismatches"])
        if str(d.get("ref_date") or "") != _ref_date():
            note += " · ⚠️서버 기준일 %s" % d.get("ref_date")
        return note
    except Exception as e:
        return " · 서버 원천 대조 못함(%s)" % type(e).__name__


def _capture_pages(n):
    """n면 캡처 — 실패는 (None, 사유). 요약표 폴백은 없다(GM 지시 2026-09-14)."""
    try:
        import report_page_capture as cap
        code, msg = cap.capture(pages=cap.PAGES3 if n == 3 else ("sheet",))
    except ImportError:
        return None, "playwright 미설치"
    except Exception as e:  # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, str(e)[:160])
    if code:
        return None, msg
    return msg.split("|"), ""


def _switch_mode():
    try:
        return json.loads(SWITCH_PATH.read_text(encoding="utf-8")).get("mode", "parallel")
    except Exception:
        return "parallel"                        # 파일 없으면 안전 기본값(병행만·3방 절대 아님)


def write_cells(narrative):
    """I20·I21 시트 기입(배1086 · GM 결재 2026-09-07 「켠다」). 쓰기 관문은 기존 post_to_sheet 하나
    (GAS 웹앱 허용 칸 I20·I21 · 같은 날 사람이 고친 칸은 덮지 않는 가드 그대로).
    배1097(GM 2026-09-07): 기입 시각을 I16·I18(08:00)에 맞춰 08:05 --write-cells 로 따로 돌린다 —
    09:20 발송은 캡션 표시만."""
    from sales_report_ops_summary import post_to_sheet, _alert_if_bad
    for cell in ("I20", "I21"):
        text = (narrative or {}).get(cell, "")
        if not text:
            print("[I20·I21] %s 원천 비어 있음 — 기입 안 함" % cell)
            continue
        res = post_to_sheet(text, cell)
        _alert_if_bad(cell, res)
        print("[I20·I21] %s 기입 %s" % (cell, "ok" if res.get("ok") else res))




def main():
    if "--write-cells" in sys.argv:            # 08:05 cron — 발송 없이 I20·I21 시트 기입만
        render = _render()
        render.load_env()
        write_cells(render.compute_narrative(render.datetime.now(render.KST).strftime("%Y-%m-%d")))
        return 0
    dry_run = "--dry-run" in sys.argv

    mode = _switch_mode()
    # "live"(3방 전환 · 배1061 · 10/1) 도 09:00 업무보고방 사진·09:02 대조 줄은 그대로 간다 — 3방 원천만 바뀐다(generate_sales_report_image.live_mode).
    if mode in ("gmpc_0900", "live") and not ON_SERVER:
        return gm_pc_0900(dry_run)
    if mode in ("gmpc_0900", "live") and ON_SERVER:
        return server_check_line(dry_run)
    if mode != "parallel":
        print("[skip] switch mode=%s (parallel·gmpc_0900 아님 — 발송 안 함)" % mode)
        return 0
    return legacy_parallel(dry_run)


def gm_pc_0900(dry_run):
    """GM PC 09:00 — 1~3면 사진 3장. 캡처가 안 되면 사진 대신 사유 한 줄."""
    token, chat = _gm_pc_env()
    if not token:
        print("[fail] telegram_bot/.env TELEGRAM_BOT_TOKEN 없음")
        return 1
    paths, why = _capture_pages(3)
    ref_date = _ref_date()
    if not paths:
        text = "매출 및 회원 현황 보고 서버판(09:00) — 오늘은 그림을 못 만들었습니다: %s · 09:30 카톡 보고는 그대로 나갑니다" % why
        print("[fail] " + text)
        if not dry_run:
            tg_send(token, chat, text, source="sales_report_server_send", full_response=True)
        return 1
    ok, ids = send_three_pages(token, chat, paths, ref_date, server_check_note(), dry_run=dry_run)
    print("DONE: ok=%s ids=%s pages=%s" % (ok, ids, paths))
    return 0 if ok else 1


def server_check_line(dry_run):
    """서버 09:02 — 22칸 대조 결과 한 줄(글). 사진은 GM PC 가 09:00 에 보냈다."""
    report = _render().build_report()
    if not report:
        print("[fail] 시트 미러 없음 — sync_sales.py(deptrep/dump) 캐시 확인")
        return 1
    text = "↳ 서버판 22칸 대조 · 기준일 %s · %d/%d 일치" % (report["ref_date"], report["matched"], report["total"])
    if report["mismatches"]:
        text += " · 불일치: " + ", ".join(report["mismatches"])
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if dry_run:
        print("[dry-run] " + text)
        return 0
    if not token or not chat:
        print("[fail] TG_BOT_TOKEN/TG_CHAT_ID 없음 (api.env 확인)")
        return 1
    resp = tg_send(token, chat, text, source="sales_report_server_send", full_response=True)
    ok = bool(isinstance(resp, dict) and resp.get("ok"))
    print("DONE: ok=%s · %s" % (ok, text))
    return 0 if ok else 1


def legacy_parallel(dry_run):
    """종전 parallel 모드(한 곳에서 사진+대조) — 브라우저 있는 곳에서만 뜻이 있다. 요약표 폴백은 없앴다."""
    report = _render().build_report()                # 내부에서 load_env() 호출 → TG_BOT_TOKEN 등 os.environ 채워짐
    if not report:
        print("[fail] 시트 미러 없음 — sync_sales.py(deptrep/dump) 캐시 확인")
        return 1
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        print("[fail] TG_BOT_TOKEN/TG_CHAT_ID 없음 (api.env 확인)")
        return 1
    paths, why = _capture_pages(3)
    note = " · 22칸 대조 %d/%d 일치" % (report["matched"], report["total"])
    if report["mismatches"]:
        note += " · 불일치: " + ", ".join(report["mismatches"])
    if not paths:
        text = "매출 및 회원 현황 보고 서버판 — 그림을 못 만들었습니다: %s%s" % (why, note)
        print("[fail] " + text)
        if not dry_run:
            tg_send(token, chat, text, source="sales_report_server_send", full_response=True)
        return 1
    ok, ids = send_three_pages(token, chat, paths, report["ref_date"], note, dry_run=dry_run)
    print("DONE: ok=%s ids=%s pages=%s" % (ok, ids, paths))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
