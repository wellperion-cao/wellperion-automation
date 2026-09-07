#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매출보고서 서버 판 — 09:20 KST 업무보고방(8254867551) 병행 발송 (배1061 · 시토 · 2026-09-05).

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
import sales_report_render as render  # noqa: E402
from tg_outbound_log import send as tg_send  # noqa: E402

SWITCH_PATH = ROOT / "status" / "sales_report_server_switch.json"
OUT_PNG = ROOT / "qa_screenshots" / "sales_report_server_sample.png"


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
        render.load_env()
        write_cells(render.compute_narrative(render.datetime.now(render.KST).strftime("%Y-%m-%d")))
        return 0

    mode = _switch_mode()
    if mode != "parallel":
        print("[skip] switch mode=%s (parallel 아님 — 발송 안 함)" % mode)
        return 0

    report = render.build_report()                # 내부에서 load_env() 호출 → TG_BOT_TOKEN 등 os.environ 채워짐
    if not report:
        print("[fail] 시트 미러 없음 — sync_sales.py(deptrep/dump) 캐시 확인")
        return 1

    png = render.render_png(report, OUT_PNG)
    caption = "서버 판(병행) · 기준일 %s · 22칸 대조 %d/%d 일치" % (report["ref_date"], report["matched"], report["total"])
    if report["mismatches"]:
        caption += " · 불일치: " + ", ".join(report["mismatches"])

    # I20·I21(배1086) — 캡션 뒤에 붙인다. 텔레그램 sendPhoto 캡션 1024자 한도 넘으면 sendMessage 로 한 통 더.
    narrative = report.get("narrative") or {}
    i20, i21 = narrative.get("I20", ""), narrative.get("I21", "")
    narrative_text = ""
    if i20:
        narrative_text += "\n\n【I20 인사&파트너팀 진행 사항】\n" + i20
    if i21:
        narrative_text += "\n\n【I21 핵심 보고 및 진행 현황】\n" + i21
    full_caption = caption + narrative_text
    send_caption, extra_text = (full_caption, None) if len(full_caption) <= 1024 else (caption, narrative_text.strip())

    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        print("[fail] TG_BOT_TOKEN/TG_CHAT_ID 없음 (api.env 확인)")
        return 1

    resp = tg_send(token, chat, send_caption, source="sales_report_server_send", photo=png, full_response=True)
    ok = bool(isinstance(resp, dict) and resp.get("ok"))
    msg_id = (resp.get("result") or {}).get("message_id") if isinstance(resp, dict) else None
    if extra_text:
        tg_send(token, chat, extra_text, source="sales_report_server_send", full_response=True)

    print("DONE: ok=%s message_id=%s png=%s · %s" % (ok, msg_id, png, caption))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
