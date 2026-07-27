#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★운영부 카톡 대화 → AI 아침 요약 두뇌 (v1 · 요약 생성까지 — 발송·txt 내보내기는 범위 밖).

매일 아침, ★운영부 방의 전날(어제) 대화(카카오톡 PC '대화 내보내기' .txt)를 읽어
GM 승인용 아침 메시지 1통을 생성한다. 메시지 4요소:
  ① 어제 하루 요약(3~5줄) ② 미해결 이슈 추적 ③ 반복 문제 감지 ④ 격려·독려
한국어·카톡에 바로 보내기 좋은 톤·길이. 발송 기능은 이 스크립트 범위 아님(별도).

배97(GM 2026-07-25 "한 번의 현황보고에 모든 운영을 한눈에"): 전사 신호(매출·지출·구매물품)
3줄 블록 추가 + 전 섹션 3요소 압축(①오늘 숫자 ②전일 대비 방향 ③이상한 것만 펼침 —
정상은 한 줄로 접는다). 전일 대비 방향은 원장 metrics 스냅샷 비교(첫날은 방향 생략·날조 금지).

두뇌: scripts/model_router.run_claude (claude CLI · opus→sonnet→haiku 폴백 체인, 레포 표준 재사용).

★개인정보 원칙(필수):
  - 대화 원문·원장(이슈 이력)·생성 메시지는 직원 실명 등 개인정보를 포함한다.
  - git에 추적되는 경로(status/·docs/·3. 웰페리온 가이드/ 등)에는 절대 쓰지 않는다.
  - 입출력 전부 gitignore된 "1. AI자료_아카이브/11_카카오톡/★운영부/" 하위에만 저장.
  - 이 스크립트가 만든 산출물은 커밋하지 않는다(발행 전 GM 검수 전제).

입력: 1. AI자료_아카이브/11_카카오톡/★운영부/{YYYY-MM}/*.txt (최신 파일)
원장: 1. AI자료_아카이브/11_카카오톡/★운영부/_digest_ledger.json (날짜별 이슈 목록·해결여부 누적)

사용법:
  python scripts/ops_daily_digest.py                # 대상일=어제(없으면 최근 완결일) 자동
  python scripts/ops_daily_digest.py --date 2026-07-11   # 대상일 수동 지정(테스트·재실행용)
"""
from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 (gitignore된 아카이브 하위 전용 — 절대 status/·docs/ 등 추적경로 금지) ──
ROOT = Path(__file__).resolve().parent.parent
KAKAO_ROOM_DIR = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★운영부"
LEDGER_PATH = KAKAO_ROOM_DIR / "_digest_ledger.json"
PENDING_DIGEST_PATH = KAKAO_ROOM_DIR / "_pending_digest.json"

# 지출품의 GAS(배97 · 매출/지출/구매물품 정본) — 매출지출현황.html PROC_API와 동일 배포본.
# 비밀번호는 정본(.deploy-procurement/procurement.js)에서 직독(사본 하드코딩 금지).
PROC_EXEC_URL = os.environ.get(
    "PROC_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbxUAQ3DefJt13z5Bsz5KlGw6BwS2lDeLgHDMeTHjifLYGuk1lNyEpARYQ20XcjJXNj5/exec",
)
PROC_JS_PATH = ROOT / ".deploy-procurement" / "procurement.js"
SALES_TARGETS_PATH = ROOT / "status" / "sales_targets.json"  # 월 목표매출 정본(GM 결재 2026-07-03)

RECENT_LEDGER_DAYS = 5  # 반복감지·미해결추적용으로 프롬프트에 주입할 과거 원장 기간

# GAS URL 상수 3종(FUNNEL_EXEC_URL·RECEPTION_EXEC_URL·SSOT_API_URL)·_TODO_DONE_STATUSES는
# telegram_bot/daily_scheduler.py와의 중복 정의를 scripts/collectors/ops_shared.py 공용
# 수집층으로 수렴(2026-07-21 순수 리팩터 — 값·동작 무변경).
try:
    from collectors.ops_shared import (
        FUNNEL_EXEC_URL,
        RECEPTION_EXEC_URL,
        SSOT_API_URL,
        TODO_DONE_STATUSES as _TODO_DONE_STATUSES,
        gas_get as _gas_get,
        utc_iso_to_kst_date as _utc_iso_to_kst_date,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from collectors.ops_shared import (
        FUNNEL_EXEC_URL,
        RECEPTION_EXEC_URL,
        SSOT_API_URL,
        TODO_DONE_STATUSES as _TODO_DONE_STATUSES,
        gas_get as _gas_get,
        utc_iso_to_kst_date as _utc_iso_to_kst_date,
    )

MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")
DATE_SEP_RE = re.compile(r"^-{3,}.*?(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일.*-{3,}\s*$")
MSG_RE = re.compile(r"^\[(?P<name>.+?)\]\s*\[(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<m>\d{2})\]\s*(?P<msg>.*)$")
SYSTEM_LINE_RE = re.compile(r".*(들어왔습니다|나갔습니다|저장한 날짜)\.?\s*$")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════
#  0) 공용 GAS 조회 래퍼(재시도) — 문의·종합접수·예약·업무 블록 공용.
#     숫자는 LLM에 맡기지 않고 결정론적 실측만. 실패=호출부에서 "측정 불가" 정직 표기.
#     정의는 scripts/collectors/ops_shared.gas_get (위에서 _gas_get으로 import).
# ═══════════════════════════════════════════


def _split_llm(message: str) -> "tuple[str, str, str]":
    """LLM 메시지를 (🌅 헤더줄, 본문[💪 제외], 💪줄)로 분리 — 섹션 재배치·💪 맨끝 배치용."""
    lines = message.split("\n")
    hi = next((i for i, ln in enumerate(lines) if ln.strip().startswith("🌅")), None)
    header = lines[hi] if hi is not None else ""
    body_lines = lines[hi + 1:] if hi is not None else lines
    wi = next((i for i, ln in enumerate(body_lines) if ln.strip().startswith("💪")), None)
    if wi is not None:
        warm = "\n".join(body_lines[wi:]).strip()
        body = "\n".join(body_lines[:wi]).strip()
    else:
        warm, body = "", "\n".join(body_lines).strip()
    return header, body, warm


# ═══════════════════════════════════════════
#  0-b) 운영 현황 종합화 신규 4섹션(2026-07-14 GM 지시) — 점검 블록과 동일 원칙: 결정론적 실측,
#       숫자는 절대 추측 생성 금지. 소스 부재·date-scope 불명·응답 실패는 전부
#       "측정 불가 · 소스 배선 후속"으로 정직 표기. insert 지점만 확장(기존 로직 무접촉).
# ═══════════════════════════════════════════
_NO_SOURCE = "측정 불가 · 소스 배선 후속"
# _utc_iso_to_kst_date 정의는 scripts/collectors/ops_shared.utc_iso_to_kst_date (위에서 import).


def build_inquiry_block(target_date: str) -> str:
    """배97 압축: 문의(inquiry_list · KST 매칭 · 전일 대비 방향) + 등록(member_registered_list)을
    한 줄로 접는다. 소스는 기존과 동일(FUNNEL_EXEC_URL — 문의알림방 대시보드 정본).
    문의 0건은 이상 신호로 ⚠️ 표시(정상 아님 — 평일 기준 드묾)."""
    prev_date = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    inq_part = f"문의: {_NO_SOURCE}"
    resp = _gas_get(FUNNEL_EXEC_URL, {"action": "inquiry_list"}, timeout=40, label="ops-digest 문의")
    if resp is not None:
        try:
            data = resp.json()
            rows = data.get("data", []) if data.get("ok") else None
            if rows is not None:
                day_rows = [r for r in rows if _utc_iso_to_kst_date(r.get("시각", "")) == target_date]
                prev_n = sum(1 for r in rows if _utc_iso_to_kst_date(r.get("시각", "")) == prev_date)
                type_count: dict[str, int] = {}
                for r in day_rows:
                    t = r.get("문의유형", "기타") or "기타"
                    type_count[t] = type_count.get(t, 0) + 1
                detail = "·".join(f"{t}{c}" for t, c in sorted(type_count.items(), key=lambda x: -x[1]))
                arrow = "▲" if len(day_rows) > prev_n else ("▼" if len(day_rows) < prev_n else "=")
                mark = "⚠️ " if not day_rows else ""
                inq_part = f"{mark}문의 {len(day_rows)}건({(detail + ' · ') if detail else ''}전일 {prev_n} {arrow})"
        except Exception:
            pass

    reg_part = f"등록: {_NO_SOURCE}"
    resp2 = _gas_get(
        FUNNEL_EXEC_URL,
        {"action": "member_registered_list", "from": target_date, "to": target_date},
        timeout=40, label="ops-digest 등록",
    )
    if resp2 is not None:
        try:
            data2 = resp2.json()
            if data2.get("ok"):
                reg_part = f"등록 {data2.get('count', 0)}건"
        except Exception:
            pass

    return f"📩 문의·등록 · 오늘 예약\n • {inq_part} · {reg_part}"


def build_reception_block(target_date: str) -> str:
    """target_date(YYYY-MM-DD) 종합접수처 6종 통합 사실블록(RECEPTION_EXEC_URL reg_list).
    createdAt="YYYY-MM-DD HH:MM:SS"(KST) 접두 매칭 — daily_scheduler._build_digest_reception 동일 패턴.
    resolved={"완료"}만(나머지 접수·처리중 등 전부 미해결 — 동일 근거)·14일 초과=대기·보류 자동 이관.
    배97 압축: ①어제 접수 숫자+전일 대비 한 줄 ②미해결(2주내)만 오래된 순 3건 펼침(=이상 신호)
    ③보류(2주+)는 건수 한 줄로 접는다(항목 나열 제거 — 상세는 종합접수처 현황 페이지)."""
    lines = ["📣 종합접수 현황"]

    resp = _gas_get(RECEPTION_EXEC_URL, {"action": "reg_list"}, timeout=20, label="ops-digest 종합접수")
    if resp is None:
        lines.append(f" • {_NO_SOURCE}")
        return "\n".join(lines)
    try:
        data = resp.json()
        if not data.get("ok"):
            lines.append(f" • {_NO_SOURCE}")
            return "\n".join(lines)
        rows = data.get("data", [])
    except Exception:
        lines.append(f" • {_NO_SOURCE}")
        return "\n".join(lines)

    if not rows:
        lines.append(f" • {_NO_SOURCE}")
        return "\n".join(lines)

    _RESOLVED_STATUSES = {"완료"}

    def _short_cat(cat: str) -> str:
        cat = (cat or "기타").strip()
        return cat[:-3] if cat.endswith(" 접수") else cat

    def _day_match(r: dict, d: str) -> bool:
        return str(r.get("createdAt", "")).startswith(d) or str(r.get("occurredAt", "")).startswith(d)

    prev_date = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    day_rows = [r for r in rows if _day_match(r, target_date)]
    prev_n = sum(1 for r in rows if _day_match(r, prev_date))
    day_cat_count: dict[str, int] = {}
    for r in day_rows:
        c = _short_cat(r.get("category", ""))
        day_cat_count[c] = day_cat_count.get(c, 0) + 1
    cat_summary = "·".join(f"{c}{n}" for c, n in sorted(day_cat_count.items(), key=lambda x: -x[1]))
    arrow = "▲" if len(day_rows) > prev_n else ("▼" if len(day_rows) < prev_n else "=")
    lines.append(
        f" • 어제 접수 {len(day_rows)}건({(cat_summary + ' · ') if cat_summary else ''}전일 {prev_n} {arrow})"
    )

    today_dt = datetime.now()

    def _elapsed_days(r: dict) -> int:
        raw = str(r.get("occurredAt", "") or r.get("createdAt", ""))[:10]
        try:
            return (today_dt - datetime.strptime(raw, "%Y-%m-%d")).days
        except Exception:
            return 0

    unresolved = [r for r in rows if str(r.get("status", "")) not in _RESOLVED_STATUSES]
    if not unresolved:
        lines.append(" • 미해결 없음 👍")
        return "\n".join(lines)

    # 2주 넘게 방치된 건은 자동으로 '대기·보류'로 내려 매일 푸시에서 제외(에너지 절약, GM 2026-07-14).
    STALE_DAYS = 14
    active = sorted((r for r in unresolved if _elapsed_days(r) < STALE_DAYS), key=_elapsed_days, reverse=True)
    stale = sorted((r for r in unresolved if _elapsed_days(r) >= STALE_DAYS), key=_elapsed_days, reverse=True)

    _ICON = {"컴플레인": "🗣️", "분실물": "🔑", "시설물 고장": "🔧",
             "청결 이슈": "🧹", "직원·강사 칭찬합니다": "👏"}

    def _line(r: dict, cap: int, with_loc: bool = True) -> str:
        cat = _short_cat(r.get("category", ""))
        ico = _ICON.get(cat, "•")  # 유형별 이모지로 한눈에 구분(가시성)
        content = re.sub(r"\s+", " ", str(r.get("content", "") or "")).strip()
        if len(content) > cap:
            content = content[:cap] + "…"
        loc = r.get("loc", "") or ""
        tail = f" · {loc}" if (with_loc and loc) else ""
        return f"   {ico} [{cat}] {content}{tail} · {_elapsed_days(r)}일째"

    # 🔴 미해결(2주 이내) = 이상 신호 — 오래된 순 3건만 펼침(배97 압축: 5→3건·34→30자)
    if active:
        lines.append(f" • 🔴 미해결 {len(active)}건(2주내) — 오래된 순:")
        for r in active[:3]:
            lines.append(_line(r, 30))
        if len(active) > 3:
            lines.append(f"   · 외 {len(active) - 3}건")
    else:
        lines.append(" • 🔴 2주 이내 미해결 없음 👍")

    # ⏸️ 대기·보류(2주+ 자동 이관) = 정상 접힘 — 건수 한 줄만(항목 나열 제거)
    if stale:
        lines.append(f" • ⏸️ 보류 {len(stale)}건(2주+ 자동 이관 · 별도 검토)")

    return "\n".join(lines)


def build_reservation_block(today_date: str) -> str:
    """today_date(YYYY-MM-DD, 오늘) 투어·체험 예약(member_inquiry_list reservations[].date 매칭) 리마인드.
    강습 예약은 별도 리스트 GAS 미발견 — 정직하게 측정 불가 표기(날조 금지)."""
    lines = ["📅 오늘 예약·일정"]

    resp = _gas_get(FUNNEL_EXEC_URL, {"action": "member_inquiry_list"}, timeout=40, label="ops-digest 예약")
    if resp is None:
        lines.append(f" • 투어·체험 예약: {_NO_SOURCE}")
    else:
        try:
            data = resp.json()
            rows = data.get("data", []) if data.get("ok") else None
            if rows is None:
                lines.append(f" • 투어·체험 예약: {_NO_SOURCE}")
            else:
                today_events: list[tuple[str, str]] = []
                for r in rows:
                    name = r.get("name", "") or ""
                    for res in (r.get("reservations") or []):
                        if res.get("date") == today_date:
                            today_events.append((res.get("time") or "", name))
                if not today_events:
                    lines.append(" • 오늘 투어·체험 예약 없음")
                else:
                    today_events.sort(key=lambda x: x[0])
                    shown = today_events[:4]  # 배97 압축: 10→4건
                    detail = ", ".join(f"{t or '시간미정'} {n}" for t, n in shown)
                    over = len(today_events) - len(shown)
                    if over > 0:
                        detail += f" 외 {over}건"
                    lines.append(f" • 오늘 예약 {len(today_events)}건({detail})")
        except Exception:
            lines.append(f" • 투어·체험 예약: {_NO_SOURCE}")

    return "\n".join(lines)


def build_work_block(target_date: str) -> str:
    """target_date(YYYY-MM-DD) 실무진 업무현황(G1 항로 SSOT) 사실블록.
    소스: SSOT_API_URL?action=todo_list(telegram_bot/daily_scheduler.py와 동일 정본 GAS).
    어제 완료(상태∈_TODO_DONE_STATUSES · 수정일=target_date) + 진행/예정(그 외 상태) 각 최대 5개 제목."""
    lines = ["🗂️ 업무 (실무진 업무현황)"]

    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, timeout=40, label="ops-digest 업무현황")
    if resp is None:
        lines.append(f" • {_NO_SOURCE}")
        return "\n".join(lines)
    try:
        data = resp.json()
        if not data.get("ok"):
            lines.append(f" • {_NO_SOURCE}")
            return "\n".join(lines)
        items = data.get("data", [])
    except Exception:
        lines.append(f" • {_NO_SOURCE}")
        return "\n".join(lines)

    done_yesterday = [
        x for x in items
        if str(x.get("상태", "")) in _TODO_DONE_STATUSES
        and str(x.get("수정일", "") or "").startswith(target_date)
    ]
    active = [x for x in items if str(x.get("상태", "")) not in _TODO_DONE_STATUSES]

    def _title_summary(rows: list, n: int) -> str:
        titles = [str(r.get("업무명", "")).strip() for r in rows if str(r.get("업무명", "")).strip()]
        text = ", ".join(titles[:n])
        if len(titles) > n:
            text += f" 외 {len(titles) - n}건"
        return text

    # 배97 압축: 완료(=어제 실제 사건)만 제목 3건, 상시 목록인 진행/예정은 숫자+대표 1건으로 접는다.
    done_detail = _title_summary(done_yesterday, 3)
    active_detail = _title_summary(active, 1)
    seg_done = f"어제 완료 {len(done_yesterday)}건" + (f"({done_detail})" if done_detail else "")
    seg_active = f"진행/예정 {len(active)}건" + (f"({active_detail})" if active_detail else "")
    lines.append(f" • {seg_done} · {seg_active}")
    lines.append(" 📌 오늘 진행·완료 SSOT 업데이트 필수(인사평가 반영)")

    return "\n".join(lines)


# ═══════════════════════════════════════════
#  0-c) 전사 신호 — 매출·지출·구매물품 (배97 · GM 2026-07-25 "한 번의 현황보고에 모든 운영을")
#      소스 = 지출품의 GAS(PROC_EXEC_URL — 매출지출현황.html PROC_API와 동일 배포본):
#        sales_month(월별 매출보고 말일탭 Y70:Y80 — CFO 대시보드 1순위 "제일 정확한 매출")
#        proc_summary(지출품의 시트 월별 집행성 합계) · list(구매품의 행 — noimg 경량).
#      전일 대비 방향 = 원장(_digest_ledger.json) 각 날짜 entry의 metrics 스냅샷 비교.
#      같은 달 스냅샷이 없으면(첫날·월초) 방향을 생략한다 — 숫자 날조 금지.
# ═══════════════════════════════════════════
def _proc_password() -> str | None:
    """지출품의 GAS 비밀번호 — 정본(.deploy-procurement/procurement.js)에서 직독."""
    try:
        m = re.search(r'var PW = "([^"]+)"', PROC_JS_PATH.read_text(encoding="utf-8"))
        return m.group(1) if m else None
    except Exception:
        return None


def _fmt_won(v) -> str:
    """원화 압축 표기: 4.53억 / 411만 / 9,500원 (음수는 - 접두)."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return "?"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 100_000_000:
        return f"{sign}{a / 100_000_000:.2f}억"
    if a >= 10_000:
        return f"{sign}{a // 10_000:,}만"
    return f"{sign}{a:,}원"


def _prev_metrics(ledger: list[dict], before_date: str) -> dict:
    """before_date 이전 가장 최근 원장 entry의 metrics(전일 대비 방향용). 없으면 {}."""
    for e in sorted(ledger, key=lambda x: str(x.get("date", "")), reverse=True):
        if str(e.get("date", "")) < before_date and isinstance(e.get("metrics"), dict):
            return e["metrics"]
    return {}


def _date_num(s: str) -> int:
    """'2026. 7. 24'·'2026-07-24' 등 → 20260724 (지출품의 GAS dateNum과 동일 규약)."""
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(s or ""))
    return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3)) if m else 0


def build_finance_block(target_date: str, ledger: list[dict]) -> "tuple[str, dict]":
    """매출·지출·구매물품 3줄 사실블록 + 원장 저장용 metrics 스냅샷 반환.
    각 줄 = ①이번달 숫자 ②전일 대비 방향(스냅샷 있을 때만) ③실패는 측정 불가 정직 표기."""
    now = datetime.now()
    month_label = now.strftime("%Y-%m")
    mi = now.month - 1
    metrics: dict = {"month": month_label, "sales_cum": None, "expense_cum": None}
    lines = ["💰 매출·지출·구매 (전사)"]

    pw = _proc_password()
    if pw is None:
        lines.append(f" • 매출·지출·구매: {_NO_SOURCE}(지출품의 GAS 키 미발견)")
        return "\n".join(lines), metrics

    prev = _prev_metrics(ledger, target_date)
    prev_same_month = prev if prev.get("month") == month_label else {}

    def _delta_txt(cur: int, pv) -> str:
        if not isinstance(pv, int):
            return ""
        d = cur - pv
        body = "±0" if d == 0 else (("+" if d > 0 else "") + _fmt_won(d))
        return f" · 어제보다 {body}"

    # ① 매출 — 이번달 누적 · 목표 대비 %
    sales_line = f" • 매출: {_NO_SOURCE}"
    resp = _gas_get(PROC_EXEC_URL, {"action": "sales_month", "password": pw}, timeout=60, label="ops-digest 매출")
    if resp is not None:
        try:
            data = resp.json()
            total = (data.get("total") or [None] * 12)[mi] if data.get("ok") else None
            if total is not None:
                metrics["sales_cum"] = int(total)
                seg = f" • 매출({now.month}월 누적): {_fmt_won(total)}"
                try:
                    tgt = json.loads(SALES_TARGETS_PATH.read_text(encoding="utf-8"))["monthly_target_total"]
                    seg += f" — 목표 {_fmt_won(tgt)}의 {int(total) / tgt * 100:.0f}%"
                except Exception:
                    pass
                seg += _delta_txt(int(total), prev_same_month.get("sales_cum"))
                sales_line = seg
        except Exception:
            pass
    lines.append(sales_line)

    # ② 지출 — 이번달 구매품의 집행 누적 + 진행중 건수(품의·검토·정산)
    active_rows: list[dict] = []
    active_ok = False
    resp3 = _gas_get(
        PROC_EXEC_URL, {"action": "list", "mode": "active", "noimg": 1, "password": pw},
        timeout=60, label="ops-digest 구매진행",
    )
    if resp3 is not None:
        try:
            d3 = resp3.json()
            if d3.get("ok"):
                active_rows = d3.get("data", []) or []
                active_ok = True
        except Exception:
            pass

    exp_line = f" • 지출: {_NO_SOURCE}"
    resp2 = _gas_get(PROC_EXEC_URL, {"action": "proc_summary", "password": pw}, timeout=60, label="ops-digest 지출")
    if resp2 is not None:
        try:
            d2 = resp2.json()
            cum = (d2.get("months") or [None] * 12)[mi] if d2.get("ok") else None
            if cum is not None:
                metrics["expense_cum"] = int(cum)
                seg = f" • 지출({now.month}월 구매집행): {_fmt_won(cum)}"
                seg += _delta_txt(int(cum), prev_same_month.get("expense_cum"))
                if active_ok:
                    seg += f" · 품의 진행중 {len(active_rows)}건"
                exp_line = seg
        except Exception:
            pass
    lines.append(exp_line)

    # ③ 구매물품 — 어제 새로 올라온 구매요청(진행중 + 어제자 완료분)
    tnum = _date_num(target_date)
    yday_items = [r for r in active_rows if _date_num(r.get("날짜", "")) == tnum]
    done_ok = False
    resp4 = _gas_get(
        PROC_EXEC_URL,
        {"action": "list", "mode": "done", "from": target_date, "to": target_date, "noimg": 1, "password": pw},
        timeout=60, label="ops-digest 구매완료",
    )
    if resp4 is not None:
        try:
            d4 = resp4.json()
            if d4.get("ok"):
                done_ok = True
                yday_items += d4.get("data", []) or []
        except Exception:
            pass

    if not active_ok and not done_ok:
        lines.append(f" • 어제 구매요청: {_NO_SOURCE}")
    elif not yday_items:
        lines.append(" • 어제 구매요청 0건")
    else:
        names = []
        for r in yday_items[:3]:
            nm = re.sub(r"\s+", " ", str(r.get("물품", "") or "")).strip()
            names.append(nm[:14] + ("…" if len(nm) > 14 else ""))
        over = f" 외 {len(yday_items) - 3}건" if len(yday_items) > 3 else ""
        amt = 0
        for r in yday_items:
            try:
                amt += int(r.get("가격") or 0)
            except (TypeError, ValueError):
                pass
        lines.append(f" • 어제 구매요청 {len(yday_items)}건({_fmt_won(amt)}) — {', '.join(names)}{over}")

    return "\n".join(lines), metrics


# ═══════════════════════════════════════════
#  1) 최신 내보내기 txt 찾기
# ═══════════════════════════════════════════
def find_latest_export() -> Path | None:
    if not KAKAO_ROOM_DIR.exists():
        return None
    month_dirs = sorted(
        (d for d in KAKAO_ROOM_DIR.iterdir() if d.is_dir() and MONTH_DIR_RE.match(d.name)),
        key=lambda d: d.name,
        reverse=True,
    )
    for month_dir in month_dirs:
        txts = sorted(month_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if txts:
            return txts[0]
    return None


def read_text_robust(path: Path) -> str:
    """카카오톡 PC 내보내기는 보통 UTF-8(BOM 포함)이나 드물게 CP949 — 견고하게 시도."""
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


# ═══════════════════════════════════════════
#  2) 파싱 — 날짜 구분선 + [이름] [오전/오후 h:mm] 메시지 라인
# ═══════════════════════════════════════════
def parse_export(raw: str) -> dict[str, list[dict]]:
    """날짜(YYYY-MM-DD) → [{time, name, msg}] 딕셔너리. 여러 줄 메시지는 이어붙임."""
    by_date: dict[str, list[dict]] = {}
    cur_date: str | None = None
    cur_msg: dict | None = None

    for line in raw.splitlines():
        line = line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            continue

        sep = DATE_SEP_RE.match(stripped)
        if sep:
            y, mo, d = sep.groups()
            cur_date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            by_date.setdefault(cur_date, [])
            cur_msg = None
            continue

        m = MSG_RE.match(stripped)
        if m:
            if cur_date is None:
                # 날짜 구분선 이전 헤더 등 — 무시(완결된 날짜 컨텍스트 없이는 귀속 불가)
                continue
            h = int(m.group("h")) % 12
            if m.group("ampm") == "오후":
                h += 12
            time_str = f"{h:02d}:{int(m.group('m')):02d}"
            cur_msg = {"time": time_str, "name": m.group("name").strip(), "msg": m.group("msg")}
            by_date[cur_date].append(cur_msg)
            continue

        if SYSTEM_LINE_RE.match(stripped):
            # 입장/퇴장/저장일시 등 시스템 라인 — 대화 내용 아님, 건너뜀
            continue

        # 그 외 = 직전 메시지의 이어지는 줄(멀티라인 붙여넣기 등)
        if cur_msg is not None:
            cur_msg["msg"] = (cur_msg["msg"] + "\n" + stripped).strip()

    return by_date


# ═══════════════════════════════════════════
#  3) 대상일 결정 — 어제 우선, 없으면 파일 내 가장 최근 '완결된 하루'
# ═══════════════════════════════════════════
def pick_target_date(by_date: dict[str, list[dict]], forced_date: str | None) -> tuple[str | None, str]:
    today = datetime.now().date()
    if forced_date:
        if forced_date in by_date:
            return forced_date, f"수동 지정({forced_date})"
        return None, f"수동 지정일({forced_date}) 대화 없음"

    yesterday = (today - timedelta(days=1)).isoformat()
    if yesterday in by_date:
        return yesterday, f"어제({yesterday})"

    completed_dates = sorted(d for d in by_date if d < today.isoformat())
    if completed_dates:
        chosen = completed_dates[-1]
        return chosen, f"어제({yesterday}) 분 없음 → 파일 내 가장 최근 완결일({chosen}) 대체 사용"

    return None, "완결된 하루(오늘 이전 날짜) 대화 없음 — 파일에 오늘자 또는 미완결 데이터만 존재"


def format_conversation(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        if not m["msg"].strip():
            continue
        lines.append(f"{m['time']} {m['name']}: {m['msg']}")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  4) 원장(JSON) — 날짜별 이슈 목록·해결여부 누적
# ═══════════════════════════════════════════
def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def recent_issues_digest(ledger: list[dict], before_date: str, days: int = RECENT_LEDGER_DAYS) -> str:
    entries = sorted((e for e in ledger if e.get("date", "") < before_date), key=lambda e: e["date"], reverse=True)[:days]
    if not entries:
        return "(원장 이력 없음 — 첫 실행이거나 최근 이력 미존재)"
    lines = []
    for e in reversed(entries):
        issues = e.get("issues") or []
        if not issues:
            lines.append(f"- {e['date']}: (특이 이슈 없음)")
            continue
        for it in issues:
            lines.append(f"- {e['date']}: [{it.get('status', '?')}] {it.get('issue', '')}")
    return "\n".join(lines)


def upsert_ledger(ledger: list[dict], date: str, issues: list[dict], source_file: str) -> list[dict]:
    ledger = [e for e in ledger if e.get("date") != date]
    ledger.append({
        "date": date,
        "generated_at": now_str(),
        "source_file": source_file,
        "issues": issues,
    })
    ledger.sort(key=lambda e: e["date"])
    return ledger


def save_ledger(ledger: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════
#  5) 두뇌 — claude CLI (model_router 폴백 체인 재사용)
# ═══════════════════════════════════════════
def build_prompt(target_date: str, conversation: str, past_issues_digest: str) -> str:
    try:
        _d = datetime.strptime(target_date, "%Y-%m-%d")
        disp = f"{_d.month}/{_d.day}(" + "월화수목금토일"[_d.weekday()] + ")"
        # 대상일이 '진짜 어제'면 '어제 운영부 정리 · 날짜', 아니면(휴관 폴백 등) 날짜만 — 오해 방지
        _yest = (datetime.now().date() - _d.date()).days == 1
        header_label = f"어제 운영부 정리 · {disp}" if _yest else f"{disp} 운영부 정리"
    except Exception:
        disp = target_date
        header_label = f"{target_date} 운영부 정리"
    return f"""당신은 웰페리온(프리미엄 스포츠클럽 멤버십 커뮤니티) AI COO '시우'입니다.
★운영부 카카오톡 방의 어제({target_date}) 하루 대화를 읽고, 오늘 아침 방에 바로 보낼 요약 메시지 1통을 작성합니다.

[어제({target_date}) 대화 원문]
{conversation}

[최근 {RECENT_LEDGER_DAYS}일 이슈 원장(반복감지·미해결추적용 — 참고만)]
{past_issues_digest}

메시지는 '줄글'로 풀어쓰지 말고, 한눈에 들어오게 글머리(•)와 '이름별'로 딱딱 정리합니다.
★가시성: 대부분 항목은 글머리 '•'를 쓰고, '특히 눈에 띄어야 할 핵심 항목에만' 내용 맞는 이모지 1개를 글머리로 쓴다(강조용 소수만 — 매 줄 금지·남발 금지, 전체의 절반 이하). 특히 종목 단어가 들어가면 그 이모지 사용: 수영🏊·골프⛳·필라테스🧘·스쿼시🎾·라인댄스💃. 그 외 장비(키오스크💳·태블릿📱·복합기🖨️·라커🔑)·중요상황(환불💸·휴강🚫·미팅📅)은 정말 강조할 때만. 한 줄 최대 1개.
아래 구조를 그대로 따르세요(각 줄은 짧고 명확하게):

🌅 {header_label}

👤 [이름]
 • 그 사람의 핵심 업무·요청·미해결만 (★사람마다 최대 1줄 — 정말 중요한 사람만 2줄 · 지엽적 잡담·중복·군더더기 생략)
— 어제 대화에서 발언·보고·처리한 '사람마다' 이렇게 묶는다. 이름이 분명치 않은 방 공통 공지·일정은 맨 아래 '👥 공통'으로 묶는다. ★👤 파트 전체(공통 포함)는 이름줄 빼고 내용 12줄 이내 — 한눈에 스캔되도록, 중요도 낮은 건 과감히 뺀다(단 ⚠️ 오늘 챙길 것·💪는 반드시 유지).

⚠️ 오늘 챙길 것
 • 안 끝난(미해결) 건을 담당자 이름 붙여 한 줄씩 — 많으면 중요한 순으로 최대 5줄. 정말 없으면 '• 특이사항 없음'.

🔁 반복 (해당할 때만 · 없으면 이 섹션 통째로 생략)
 • 원장 이력과 비교해 며칠째 반복되는 문제만, 최대 2줄. 확실치 않으면 넣지 말 것.

💪 (★반드시 포함 — 매일 빠뜨리지 말 것) 그날 대화 분위기·요일·특이사항을 반영한 '그날만의' 따뜻한 격려·응원 한 줄. 매일 다르게, 판박이·복붙 금지. 감시 아닌 따뜻한 동료 톤. 메시지가 아무리 짧아도 이 격려 한 줄은 항상 남긴다.

정직 규칙(중요):
- 대화에 실제로 있는 내용만. 지어내거나 과장 금지. 애매하면 '~인 것 같아요' 정도로.
- 이름은 대화에 나온 그대로 사용. 사소한 잡담·인사는 굳이 항목화하지 않되 분위기는 반영.
- ★정체 정규화(위 규칙보다 우선 — 절대 예외 없음): 김남욱은 GM이다 → 반드시 'GM(김남욱)' 또는 'GM님'으로만 표기한다. 대화 원문에서 누가 김남욱을 '대표님'/'대표'라고 불렀어도 그 호칭을 그대로 쓰지 말고 GM으로 정규화한다. '대표님'/'대표'는 오직 전응준 대표를 지칭할 때만 쓴다. 차의주는 회장님.
- 대화가 짧거나 특이사항 없으면 억지로 항목을 만들지 말고 담백하게.

출력 형식(반드시 순수 JSON 하나만 — 코드블록·설명·머리말 없이):
{{
  "message": "위 구조 그대로 카카오톡에 보낼 아침 메시지 전문(한국어 · 글머리·이름별 정리)",
  "issues": [
    {{"issue": "이슈 한 줄 요약", "status": "open 또는 resolved", "note": "근거·짧은 메모"}}
  ]
}}
issues는 대화에서 실제로 확인되는 미해결·해결 이슈만 담는다(없으면 빈 배열 []).
"""


def call_brain(prompt: str) -> tuple[str | None, str | None]:
    try:
        from model_router import run_claude
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_router import run_claude
    return run_claude(prompt, label="ops-daily-digest")


def parse_brain_json(raw: str) -> tuple[str, list[dict], bool]:
    """claude 응답에서 {"message","issues"} JSON 파싱. 실패 시 원문을 메시지로, issues=[] (정직 강등)."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        message = str(data.get("message", "")).strip()
        issues = data.get("issues") or []
        if not isinstance(issues, list):
            issues = []
        if message:
            return message, issues, True
    except json.JSONDecodeError:
        pass
    return raw.strip(), [], False


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(forced_date: str | None = None) -> int:
    print(f"[시작] ★운영부 카톡 아침 요약 두뇌 — {now_str()}")

    export_path = find_latest_export()
    if export_path is None:
        print(f"[실패] 내보낸 txt 없음 — {KAKAO_ROOM_DIR} 하위에 카카오톡 '대화 내보내기' .txt 파일이 필요합니다.")
        return 1
    print(f"[1/5] 최신 내보내기 파일: {export_path.relative_to(ROOT)}")

    raw = read_text_robust(export_path)
    by_date = parse_export(raw)
    if not by_date:
        print("[실패] 파싱 결과 대화가 0건입니다 — 내보내기 포맷을 확인하세요(예상: [이름] [오전 9:03] 메시지 + 날짜 구분선).")
        return 1
    print(f"[2/5] 파싱 완료 — {len(by_date)}일치 대화 발견: {sorted(by_date.keys())}")

    target_date, why = pick_target_date(by_date, forced_date)
    if target_date is None:
        print(f"[실패] 대상일 결정 불가 — {why}")
        return 1
    print(f"[3/5] 대상일 = {target_date} ({why})")

    conversation = format_conversation(by_date[target_date])
    if not conversation.strip():
        print(f"[실패] {target_date} 대화 내용이 비어 있습니다(메시지 0건).")
        return 1

    ledger = load_ledger()
    past_digest = recent_issues_digest(ledger, before_date=target_date)

    print("[4/5] 두뇌(claude CLI · model_router 폴백) 호출...")
    prompt = build_prompt(target_date, conversation, past_digest)
    raw_out, used_model = call_brain(prompt)
    if raw_out is None:
        print("[실패] claude CLI 전 모델 실패 — 메시지 생성 불가(원장도 갱신 안 함). model_router 로그·텔레그램 경보 확인 요망.")
        return 1

    message, issues, json_ok = parse_brain_json(raw_out)
    if not json_ok:
        print("  → 경고: JSON 파싱 실패 — 응답 원문을 메시지로 사용, 이번 회차 이슈 원장 갱신은 생략(정직 강등).")
    else:
        ledger = upsert_ledger(ledger, target_date, issues, source_file=export_path.name)
        save_ledger(ledger)
        print(f"  → 원장 갱신: {LEDGER_PATH.relative_to(ROOT)} (이슈 {len(issues)}건, 날짜 {target_date})")

    print(f"[5/5] 생성 완료 (model={used_model})")

    inquiry_block = build_inquiry_block(target_date)
    today_str = datetime.now().strftime("%Y-%m-%d")
    reservation_block = build_reservation_block(today_str)
    reception_block = build_reception_block(target_date)
    work_block = build_work_block(target_date)
    finance_block, fin_metrics = build_finance_block(target_date, ledger)

    # 전일 대비 방향용 metrics 스냅샷을 원장 해당 날짜 entry에 부착(브레인 JSON 파싱 실패일에도 기록)
    for e in ledger:
        if e.get("date") == target_date:
            e["metrics"] = fin_metrics
            break
    else:
        ledger.append({
            "date": target_date, "generated_at": now_str(),
            "source_file": export_path.name, "issues": [], "metrics": fin_metrics,
        })
        ledger.sort(key=lambda x: x["date"])
    save_ledger(ledger)

    # 문의·등록 + 오늘 예약 = 한 섹션으로 합침(예약 헤더 떼고 문의 아래에)
    mid_block = inquiry_block
    _resv_body = "\n".join(reservation_block.split("\n")[1:]).rstrip()
    if _resv_body:
        mid_block += "\n" + _resv_body

    # 섹션 재배치(GM 2026-07-14 + 배97 2026-07-25): 상단=개별 카톡 대화·오늘 챙길 것 /
    # 💰 전사 신호(매출·지출·구매) / 업무 / 문의·예약 / 종합접수 / 💪 항상 맨끝.
    # 🏢 점검은 제외(22:30 밤 점검공유 스트림#2가 별도 담당).
    header, llm_body, warm = _split_llm(message)
    parts = [header, llm_body, finance_block, work_block, mid_block, reception_block]
    final_message = "\n\n".join(p.strip() for p in parts if p and p.strip())
    if warm:
        final_message += "\n\n" + warm.strip()

    print("\n" + "=" * 60)
    print(f"[대상일] {target_date}  |  [사용모델] {used_model}  |  [원장반영] {'예' if json_ok else '아니오(파싱실패)'}")
    print("=" * 60)
    print(final_message)
    print("=" * 60)

    PENDING_DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_DIGEST_PATH.write_text(
        json.dumps(
            {"date": target_date, "generated_at": now_str(), "message": final_message, "sent": False},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  → 발송 대기 저장: {PENDING_DIGEST_PATH.relative_to(ROOT)} (발송은 범위 밖 — 게이트 대기)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="★운영부 카톡 대화 → AI 아침 요약 두뇌(v1) — 발송·txt 내보내기는 범위 밖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date", dest="date", default=None,
                        help="대상일 수동 지정(YYYY-MM-DD, 테스트·재실행용). 미지정 시 어제→최근 완결일 자동.")
    args = parser.parse_args()
    sys.exit(run(forced_date=args.date))


if __name__ == "__main__":
    main()
