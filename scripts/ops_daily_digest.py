#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★운영부 카톡 대화 → AI 아침 요약 두뇌 (v1 · 요약 생성까지 — 발송·txt 내보내기는 범위 밖).

매일 아침, ★운영부 방의 전날(어제) 대화(카카오톡 PC '대화 내보내기' .txt)를 읽어
GM 승인용 아침 메시지 1통을 생성한다. 메시지 4요소:
  ① 어제 하루 요약(3~5줄) ② 미해결 이슈 추적 ③ 반복 문제 감지 ④ 격려·독려
한국어·카톡에 바로 보내기 좋은 톤·길이. 발송 기능은 이 스크립트 범위 아님(별도).

두뇌: scripts/model_router.run_claude (claude CLI · opus→sonnet→haiku 폴백 체인, 레포 표준 재사용).

★개인정보 원칙(필수):
  - 대화 원문·원장(이슈 이력)·생성 메시지는 직원 실명 등 개인정보를 포함한다.
  - git에 추적되는 경로(status/·docs/·3. 웰페리온 가이드/ 등)에는 절대 쓰지 않는다.
  - 입출력 전부 gitignore된 "1. AI학습자료_아카이브/11_카카오톡/★운영부/" 하위에만 저장.
  - 이 스크립트가 만든 산출물은 커밋하지 않는다(발행 전 GM 검수 전제).

입력: 1. AI학습자료_아카이브/11_카카오톡/★운영부/{YYYY-MM}/*.txt (최신 파일)
원장: 1. AI학습자료_아카이브/11_카카오톡/★운영부/_digest_ledger.json (날짜별 이슈 목록·해결여부 누적)

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 (gitignore된 아카이브 하위 전용 — 절대 status/·docs/ 등 추적경로 금지) ──
ROOT = Path(__file__).resolve().parent.parent
KAKAO_ROOM_DIR = ROOT / "1. AI학습자료_아카이브" / "11_카카오톡" / "★운영부"
LEDGER_PATH = KAKAO_ROOM_DIR / "_digest_ledger.json"
PENDING_DIGEST_PATH = KAKAO_ROOM_DIR / "_pending_digest.json"
KPI_VALUES_PATH = ROOT / "status" / "kpi_values.json"

RECENT_LEDGER_DAYS = 5  # 반복감지·미해결추적용으로 프롬프트에 주입할 과거 원장 기간

# 문의·등록 GAS(.deploy-funnel/Survey.js 배포본) — kpi_collector.py _CPO_GAS·telegram_bot/daily_scheduler.py
# FUNNEL_EXEC_URL과 동일 정본(inquiry_list=문의알림방 대시보드 소스). import는 하지 않는다(사이드이펙트 회피),
# env로 오버라이드 가능한 상수만 최소 복사.
FUNNEL_EXEC_URL = os.environ.get(
    "FUNNEL_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec",
)
# VOC·종합접수처 GAS(.deploy-voc/VOC_배포.js) — telegram_bot/daily_scheduler.py VOC_EXEC_URL과 동일 정본
# (reg_list=6종 접수 카테고리: 분실물/시설물고장/청결/칭찬/쓴소리/컴플레인 통합).
VOC_EXEC_URL = os.environ.get(
    "VOC_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec",
)
# 실무진 업무현황(G1 항로 SSOT·S3) GAS — telegram_bot/daily_scheduler.py SSOT_API_URL(action=todo_list)과
# 동일 정본. import는 하지 않는다(봇 사이드이펙트 회피), env로 오버라이드 가능한 상수만 최소 복사.
SSOT_API_URL = os.environ.get(
    "SSOT_API_URL",
    "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec",
)
# telegram_bot/daily_scheduler.py _TODO_DONE_STATUSES와 동일(todo_list '상태' 완료 판정 기준).
_TODO_DONE_STATUSES = {"완료", "폐기", "DONE", "완료됨"}

MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")
DATE_SEP_RE = re.compile(r"^-{3,}.*?(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일.*-{3,}\s*$")
MSG_RE = re.compile(r"^\[(?P<name>.+?)\]\s*\[(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<m>\d{2})\]\s*(?P<msg>.*)$")
SYSTEM_LINE_RE = re.compile(r".*(들어왔습니다|나갔습니다|저장한 날짜)\.?\s*$")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═══════════════════════════════════════════
#  0) 공용 GAS 조회 래퍼(재시도) — 문의·VOC(종합접수)·예약·업무 블록 공용.
#     숫자는 LLM에 맡기지 않고 결정론적 실측만. 실패=호출부에서 "측정 불가" 정직 표기.
# ═══════════════════════════════════════════
def _gas_get(url: str, params: dict | None = None, *, timeout: int = 40, attempts: int = 3, label: str = "GAS") -> object | None:
    """GAS(script.google.com) GET 재시도 래퍼. 성공(HTTP 200) 시 Response, 전량 실패 시 None."""
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp
        except Exception:
            pass
    return None


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


def _utc_iso_to_kst_date(iso_str: str) -> str:
    """UTC ISO 8601 문자열(Z suffix) → KST YYYY-MM-DD.
    telegram_bot/daily_scheduler.py _utc_iso_to_kst_date와 동일 로직 최소 복사(import 회피)."""
    try:
        s = str(iso_str).rstrip("Z").replace("T", " ")
        dt_utc = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return (dt_utc + timedelta(hours=9)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def build_inquiry_block(target_date: str) -> str:
    """target_date(YYYY-MM-DD) 신규 문의(inquiry_list · 시각 KST 매칭) + 등록(member_registered_list ·
    회원 DB 등록일자 실측) 사실블록. 두 액션 모두 FUNNEL_EXEC_URL(문의알림방 대시보드와 동일 정본)."""
    lines = ["📩 문의·상담·등록"]

    resp = _gas_get(FUNNEL_EXEC_URL, {"action": "inquiry_list"}, timeout=40, label="ops-digest 문의")
    if resp is None:
        lines.append(f" • 신규 문의: {_NO_SOURCE}")
    else:
        try:
            data = resp.json()
            rows = data.get("data", []) if data.get("ok") else None
            if rows is None:
                lines.append(f" • 신규 문의: {_NO_SOURCE}")
            else:
                day_rows = [r for r in rows if _utc_iso_to_kst_date(r.get("시각", "")) == target_date]
                if not day_rows:
                    lines.append(" • 신규 문의: 0건")
                else:
                    type_count: dict[str, int] = {}
                    for r in day_rows:
                        t = r.get("문의유형", "기타") or "기타"
                        type_count[t] = type_count.get(t, 0) + 1
                    detail = " · ".join(f"{t} {c}건" for t, c in sorted(type_count.items(), key=lambda x: -x[1]))
                    lines.append(f" • 신규 문의: {len(day_rows)}건 ({detail})")
        except Exception:
            lines.append(f" • 신규 문의: {_NO_SOURCE}")

    resp2 = _gas_get(
        FUNNEL_EXEC_URL,
        {"action": "member_registered_list", "from": target_date, "to": target_date},
        timeout=40, label="ops-digest 등록",
    )
    if resp2 is None:
        lines.append(f" • 등록: {_NO_SOURCE}")
    else:
        try:
            data2 = resp2.json()
            if not data2.get("ok"):
                lines.append(f" • 등록: {_NO_SOURCE}")
            else:
                lines.append(f" • 등록: {data2.get('count', 0)}건 (회원 DB 등록일자 실측)")
        except Exception:
            lines.append(f" • 등록: {_NO_SOURCE}")

    return "\n".join(lines)


def build_reception_block(target_date: str) -> str:
    """target_date(YYYY-MM-DD) 종합접수처 6종 통합 사실블록(VOC_EXEC_URL reg_list).
    createdAt="YYYY-MM-DD HH:MM:SS"(KST) 접두 매칭 — daily_scheduler._build_digest_reception 동일 패턴.
    status 실측 분포(2026-07-14, 34건): 완료16·접수13·처리중5 → resolved={"완료"}만, 나머지(접수·처리중 등)는
    전부 미해결로 간주(daily_scheduler._build_digest_reception의 `!= "완료"` 판정과 동일 근거).
    미해결은 경과일(오늘 - occurredAt(없으면 createdAt) 날짜) 큰 순으로 정렬해 방치 건을 위로 올려 매일 강조."""
    lines = ["📣 종합접수 현황"]

    resp = _gas_get(VOC_EXEC_URL, {"action": "reg_list"}, timeout=20, label="ops-digest 종합접수")
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

    day_rows = [
        r for r in rows
        if str(r.get("createdAt", "")).startswith(target_date)
        or str(r.get("occurredAt", "")).startswith(target_date)
    ]
    day_cat_count: dict[str, int] = {}
    for r in day_rows:
        c = _short_cat(r.get("category", ""))
        day_cat_count[c] = day_cat_count.get(c, 0) + 1
    cat_summary = ", ".join(f"{c} {n}" for c, n in sorted(day_cat_count.items(), key=lambda x: -x[1]))
    lines.append(f" • 어제 접수: {len(day_rows)}건" + (f" ({cat_summary})" if cat_summary else ""))

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

    def _line(r: dict, cap: int, with_loc: bool = True) -> str:
        cat = _short_cat(r.get("category", ""))
        content = re.sub(r"\s+", " ", str(r.get("content", "") or "")).strip()
        if len(content) > cap:
            content = content[:cap] + "…"
        loc = r.get("loc", "") or ""
        tail = f" · {loc}" if (with_loc and loc) else ""
        return f"   · [{cat}] {content}{tail} · {_elapsed_days(r)}일째"

    # 🔴 계속 챙길 것 (2주 이내) — 활성 푸시
    if active:
        lines.append(f" • 🔴 계속 챙길 것 {len(active)}건 (2주 이내):")
        for r in active[:5]:
            lines.append(_line(r, 34))
        if len(active) > 5:
            lines.append(f"   · 외 {len(active) - 5}건")
    else:
        lines.append(" • 🔴 계속 챙길 것: 2주 이내 미해결 없음 👍")

    # ⏸️ 대기·보류 (2주+) — 자동 이관, 매일 재촉 안 함
    if stale:
        lines.append(f" • ⏸️ 대기·보류 {len(stale)}건 (2주+ 자동 이관 · 별도 검토):")
        for r in stale[:3]:
            lines.append(_line(r, 22, with_loc=False))
        if len(stale) > 3:
            lines.append(f"   · 외 {len(stale) - 3}건")

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
                    lines.append(" • 투어·체험 예약: 오늘 예약 없음")
                else:
                    today_events.sort(key=lambda x: x[0])
                    shown = today_events[:10]
                    detail = ", ".join(f"{t or '시간미정'} {n}" for t, n in shown)
                    over = len(today_events) - len(shown)
                    if over > 0:
                        detail += f" 외 {over}건"
                    lines.append(f" • 투어·체험 예약: {len(today_events)}건 ({detail})")
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

    def _title_summary(rows: list, n: int = 5) -> str:
        titles = [str(r.get("업무명", "")).strip() for r in rows if str(r.get("업무명", "")).strip()]
        shown = titles[:n]
        text = ", ".join(shown)
        if len(titles) > n:
            text += f" 외 {len(titles) - n}건"
        return text

    done_detail = _title_summary(done_yesterday)
    lines.append(f" • 어제 완료: {len(done_yesterday)}건" + (f" — {done_detail}" if done_detail else ""))
    active_detail = _title_summary(active)
    lines.append(f" • 진행/예정: {len(active)}건" + (f" — {active_detail}" if active_detail else ""))
    lines.append(" 📌 업무 SSOT 기록은 인사평가에 반영됩니다 — 각자 오늘 진행/완료를 꼭 업데이트하세요.")

    return "\n".join(lines)


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
아래 구조를 그대로 따르세요(각 줄은 짧고 명확하게):

🌅 {header_label}

👤 [이름]
 • 그 사람의 핵심 업무·요청·미해결만 (사람마다 최대 2줄 · 지엽적 잡담·중복·군더더기 생략)
— 어제 대화에서 발언·보고·처리한 '사람마다' 이렇게 묶는다. 이름이 분명치 않은 방 공통 공지·일정은 맨 아래 '👥 공통'으로 묶는다. ★전체가 너무 길지 않게 한눈에 스캔되도록 짧게 — 중요도 낮은 건 과감히 뺀다(단 ⚠️ 오늘 챙길 것·💪는 반드시 유지).

⚠️ 오늘 챙길 것
 • 안 끝난(미해결) 건을 담당자 이름 붙여 한 줄씩. 정말 없으면 '• 특이사항 없음'.

🔁 반복 (해당할 때만 · 없으면 이 섹션 통째로 생략)
 • 원장 이력과 비교해 며칠째 반복되는 문제만. 확실치 않으면 넣지 말 것.

💪 (★반드시 포함 — 매일 빠뜨리지 말 것) 그날 대화 분위기·요일·특이사항을 반영한 '그날만의' 따뜻한 격려·응원 한 줄. 매일 다르게, 판박이·복붙 금지. 감시 아닌 따뜻한 동료 톤. 메시지가 아무리 짧아도 이 격려 한 줄은 항상 남긴다.

정직 규칙(중요):
- 대화에 실제로 있는 내용만. 지어내거나 과장 금지. 애매하면 '~인 것 같아요' 정도로.
- 이름은 대화에 나온 그대로 사용. 사소한 잡담·인사는 굳이 항목화하지 않되 분위기는 반영.
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

    # 문의·등록 + 오늘 예약 = 한 섹션으로 합침(예약 헤더 떼고 문의 아래에)
    mid_block = "📩 문의·등록 · 오늘 예약\n" + "\n".join(inquiry_block.split("\n")[1:]).rstrip()
    _resv_body = "\n".join(reservation_block.split("\n")[1:]).rstrip()
    if _resv_body:
        mid_block += "\n" + _resv_body

    # 섹션 재배치(GM 2026-07-14): 상단=개별 카톡 대화·오늘 챙길 것·업무 / 중간=문의·예약 /
    # 그 바로 아래=종합접수 / 💪 항상 맨끝. 🏢 점검은 제외(23시 밤 점검공유가 별도 담당).
    header, llm_body, warm = _split_llm(message)
    parts = [header, llm_body, work_block, mid_block, reception_block]
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
