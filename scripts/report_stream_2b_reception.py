# -*- coding: utf-8 -*-
"""[스트림 #2b] 종합접수 현황 + 미처리 적체 리마인드 — 프로덕션 (CTO 2026-07-22).

GM 2026-07-22 지시: 배9424(2026-07-21)의 '종합접수 현황 → 점검현황방 병합'을 되돌림.
종합접수(VOC 6종: 분실물·시설물고장·청결·칭찬·쓴소리·컴플레인)는 점검(시설·지원·주차)과
분리해 별도 종합접수방으로 단독 발송한다. 점검 현황은 scripts/report_stream_2_check.py 참조.

통일 포맷 [하루 일과 정리]:
  ① 오늘 신규 접수 요약
  ━━━━━━━━━━
  ② 미처리 적체 리마인드 — 카테고리별 SLA(apps_script_voc.js REG_CATEGORIES가 SSOT)를
     넘긴 미처리 건을 담당자별로 묶어 매일 밤 상기(GM 신설 지시). 방치된 접수건이
     하루하루 다이제스트에 묻히지 않도록 '오늘 신규'와 별개로 매번 재노출한다 — 의도적
     크로스데이 억제 없음(리마인드 목적상 반복 노출이 맞다). 칭찬(slaHours=null)은
     SLA 개념이 없어 적체 집계에서 제외.

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

from collectors.ops_shared import VOC_EXEC_URL, gas_get  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
from tg_outbound_log import send as tg_send  # noqa: E402

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_RECEPTION_CHAT_ID") or -5065206276)  # 종합접수방
DASHBOARD_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/reception/종합접수처_현황.html"
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
_DIVIDER = "━" * 10

# 카테고리(reg_list의 category=한글 라벨) → SLA 시간. SSOT=coo/reception/apps_script_reception.js
# REG_CATEGORIES(:38-43). 보드·다른 소비자에 하드코딩 복사 금지 원칙과 동일하게 이 표는
# GAS 응답 라벨 그대로를 키로 쓴다(코드 재구현 없이 라벨 정확일치). None=SLA 없음(집계 제외).
_SLA_HOURS: dict[str, int | None] = {
    "분실물 접수": 168,
    "시설물 고장 접수": 24,
    "청결 이슈 접수": 12,
    "직원·강사 칭찬합니다": None,
    "직원·강사 쓴소리합니다": 72,
    "컴플레인 접수": 48,
}


def _fetch_rows() -> list[dict] | None:
    resp = gas_get(VOC_EXEC_URL, {"action": "reg_list"}, timeout=20, label="stream2b-voc")
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


def _fmt_age(elapsed_h: float) -> str:
    days = elapsed_h / 24.0
    return f"{days:.1f}일" if days >= 1 else f"{elapsed_h:.1f}시간"


def _aging_block(rows: list[dict], now: datetime | None = None) -> str:
    """기한(SLA) 넘긴 미처리 건 — 담당자별 그룹(미배정 별도) + 오래된 순 상세."""
    now = now or datetime.now()
    undone = [r for r in rows if str(r.get("status", "")) != "완료"]

    overdue: list[dict] = []
    for r in undone:
        cat = str(r.get("category") or "").strip()
        sla = _SLA_HOURS.get(cat)
        if sla is None:  # 칭찬 등 SLA 없음 — 적체 집계 제외
            continue
        created = _parse_created(r.get("createdAt"))
        if created is None:
            continue
        elapsed_h = (now - created).total_seconds() / 3600.0
        if elapsed_h > sla:
            overdue.append({
                "regId": str(r.get("regId") or ""),
                "cat": cat,
                "assignee": str(r.get("assignee") or "").strip(),
                "content": " ".join(str(r.get("content") or "").split())[:28],  # 개행 제거 — 1건 1줄 유지
                "elapsed_h": elapsed_h,
                "sla": sla,
            })

    lines = ["⏰ 미처리 적체 리마인드", f"미처리 {len(undone)}건 · 기한초과 {len(overdue)}건"]
    if not overdue:
        lines.append("기한 초과 건 없음.")
        return "\n".join(lines)

    def _fmt_item(it: dict) -> str:
        ratio = it["elapsed_h"] / it["sla"] if it["sla"] else 0.0
        flag = "🔴" if ratio >= 3 else "⚠️"
        return f"  {flag} [{it['cat']}] {it['content']} — {_fmt_age(it['elapsed_h'])} 경과 ({it['regId']})"

    by_owner: dict[str, list[dict]] = {}
    for it in overdue:
        owner = it["assignee"] or "미배정"
        by_owner.setdefault(owner, []).append(it)

    # 미배정을 맨 위(별도 표기)로 두고, 이후 담당자는 최고령 건 기준 오래된 순.
    if "미배정" in by_owner:
        items = sorted(by_owner.pop("미배정"), key=lambda x: -x["elapsed_h"])
        lines.append(f"\n👤 미배정 ({len(items)}건)")
        for it in items:
            lines.append(_fmt_item(it))

    for owner in sorted(by_owner, key=lambda o: -max(i["elapsed_h"] for i in by_owner[o])):
        items = sorted(by_owner[owner], key=lambda x: -x["elapsed_h"])
        lines.append(f"\n👤 {owner} ({len(items)}건)")
        for it in items:
            lines.append(_fmt_item(it))

    lines.append(f"\n👉 상세: {DASHBOARD_URL}")
    return "\n".join(lines)


def build_digest(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    header = f"📊 [하루 일과 정리] {today}({weekday})\n📮 종합접수 현황"
    rows = _fetch_rows()
    if rows is None:
        return f"{header}\n\n조회 실패 (GAS 응답 없음)"
    return f"{header}\n\n{_today_section(rows, today)}\n\n{_DIVIDER}\n{_aging_block(rows)}"


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
    p = argparse.ArgumentParser(description="스트림 #2b 종합접수 현황+미처리 적체 리마인드 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    result = run(today=a.today, dry_run=not a.live)
    print("\n=== 렌더 ===")
    print(result)
