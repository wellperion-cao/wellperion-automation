# -*- coding: utf-8 -*-
"""[스트림 #2b] 종합접수 현황 — 프로덕션 (CTO 2026-07-22, SLA 리마인드 제거 2026-07-27 시우).

GM 2026-07-22 지시: 배9424(2026-07-21)의 '종합접수 현황 → 점검현황방 병합'을 되돌림.
종합접수(VOC 6종: 분실물·시설물고장·청결·칭찬·쓴소리·컴플레인)는 점검(시설·지원·주차)과
분리해 별도 종합접수방으로 단독 발송한다. 점검 현황은 scripts/report_stream_2_check.py 참조.

통일 포맷 [하루 일과 정리]:
  ① 오늘 신규 접수 요약 (유일 섹션)

  ※ 2026-07-27 웰리 결정(배163): 'SLA 초과 미처리 적체 리마인드' 섹션은 이 22:30
     다이제스트에서 제거했다. 같은 성격의 알림이 GAS reg_sla_check(전환 즉시 통지)로
     이관되어 실무진이 그날 안에 대응할 수 있게 됐고, 이미 퇴근한 뒤인 22:30에 같은
     내용을 또 보내면 방 신뢰만 깎인다(관문 하나 원칙). 관련 로직(_SLA_HOURS/_fmt_age/
     _aging_block)은 이 파일에서 제거 — SSOT는 apps_script_reception.js reg_sla_check.

텔레그램: 종합접수방(TELEGRAM_RECEPTION_CHAT_ID, -5065206276) 단일 발송.
발사 시각: 매일 22:30 (daily_scheduler.py run_daily_digest 경유) / 독립 실행 가능.
카카오톡: 이 모듈 자체는 텔레그램만 다룬다(build_digest만 노출). ★운영+시설+지원+주차 방
발송은 daily_scheduler.py run_daily_digest()가 이 모듈의 build_digest() 결과를 그대로
재사용해 처리한다(점검현황과 별도 메시지로 분리 — GM 2026-07-22 go, KAKAO_GO_STREAM2 게이트).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import RECEPTION_EXEC_URL, gas_get  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
from tg_outbound_log import send as tg_send  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_RECEPTION_CHAT_ID") or -5065206276)  # 종합접수방
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]


def _fetch_rows() -> list[dict] | None:
    resp = gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, timeout=20, label="stream2b-reception")
    if resp is None:
        return None
    try:
        data = resp.json()
        return data.get("data", []) if data.get("ok") else None
    except Exception:
        return None


def _parse_created(s) -> datetime | None:
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _today_section(rows: list[dict], today: str) -> str:
    """오늘 신규 접수 요약(카테고리별 건수 + 미처리)."""
    today_rows = [r for r in rows if str(r.get("createdAt", "")).startswith(today)]
    if not today_rows:
        return "📮 오늘 신규 접수 없음."
    cat_cnt: dict[str, int] = {}
    undone_today = 0
    for r in today_rows:
        cat = str(r.get("category") or "기타").strip()
        cat_cnt[cat] = cat_cnt.get(cat, 0) + 1
        if str(r.get("status", "")) != "완료":
            undone_today += 1
    cat_str = " · ".join(f"{c}:{n}" for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1]))
    return f"📮 오늘 신규 접수 {len(today_rows)}건 (미처리 {undone_today}건)  {cat_str}"


def build_digest(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    header = f"📊 [하루 일과 정리] {today}({weekday})\n📮 종합접수 현황"
    rows = _fetch_rows()
    if rows is None:
        return f"{header}\n\n조회 실패 (GAS 응답 없음)"
    return f"{header}\n\n{_today_section(rows, today)}"


def run(today: str | None = None, dry_run: bool = True) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = build_digest(today)
    if dry_run:
        print(f"[stream2b] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        return text
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream2b] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return text
    # 전역 페이싱·429 재시도·로깅 = tg_outbound_log.send() 경유(플러드 방어, 개별 requests 금지).
    ok = tg_send(token, TELEGRAM_CHAT_ID, text, source="report_stream_2b_reception")
    print(f"[stream2b] 텔레그램 {'완료' if ok else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    return text


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #2b 종합접수 현황 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    result = run(today=a.today, dry_run=not a.live)
    print("\n=== 렌더 ===")
    print(result)
