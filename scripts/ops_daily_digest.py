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
  python scripts/ops_daily_digest.py --room-key mgr --bridge-dry-run   # 업무 장부에 무엇이 올라갈지만 보기
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
DEFAULT_ROOM = "★운영부"
ROOM_DIR_BASE = ROOT / "1. AI자료_아카이브" / "11_카카오톡"
# 아래 3개는 기본(★운영부) 값 — run(room=...)이 room 인자를 받으면 실행 시점에 이 전역을
# 해당 방 폴더로 재바인딩한다(배536 2026-08-11 — "ops_daily_digest 의 방 디렉터리만 갈아
# 끼우면 된다", send_ops_digest.py 주석 참조). --room 미지정 시 아래 값 그대로 = 회귀 없음.
KAKAO_ROOM_DIR = ROOM_DIR_BASE / "★운영부"
LEDGER_PATH = KAKAO_ROOM_DIR / "_digest_ledger.json"
PENDING_DIGEST_PATH = KAKAO_ROOM_DIR / "_pending_digest.json"

# ── 방 이름 ASCII 별칭 (2026-08-12 시토 · 실사고 수리) ─────────────────────────
#   왜: 예약 배치(scripts/ops_morning_digest.bat)는 CP949 로 읽히는 .bat 이라 파일 안에 적은
#   한글 인자가 깨진다. 실측 — `--room "★중간관리자"` 가 자식 프로세스에 '?낆쨷媛꾧?由ъ옄'
#   로 도착해 방을 못 찾고 매일 조용히 실패했다(2026-08-12 07:30 로그). 그래서 배치에는
#   ASCII 만 넘기고 실제 방 이름은 여기서 푼다.
#   ▸별칭 정본 = scripts/kakao_rooms.json 의 room_aliases (방 이름 SSOT 와 같은 파일).
#     파이썬 모듈에 두면 다른 스크립트가 그걸 import 하다가 stdout 이중 감싸기로 죽는다
#     (실측 — 두 모듈 다 import 시점에 sys.stdout 을 감싼다).
def _load_room_aliases() -> dict:
    try:
        data = json.loads((Path(__file__).resolve().parent / "kakao_rooms.json")
                          .read_text(encoding="utf-8"))
        aliases = data.get("room_aliases") or {}
        if aliases:
            return aliases
    except Exception:
        pass
    return {"ops": DEFAULT_ROOM, "mgr": "★중간관리자"}  # 파일을 못 읽어도 예약 실행은 멈추지 않는다


ROOM_KEYS = _load_room_aliases()

# ── 업무 장부 다리 (2026-08-12 GM 승인) ────────────────────────────────────────
#   GM: "다리를 놓고, 양방향으로 진행이 가능해? 이런 건들이 일정이 들어가서 놓치지 않게끔"
#   ①정방향 = 아침 정리가 뽑은 열린 이슈 중 **담당이 분명한 것**을 업무 SSOT(S3)에 등록한다.
#   ②역방향 = 그 건이 업무 SSOT에서 완료되면 다음 아침 정리에서 해결로 빠진다.
#   ③일정 = 등록할 때 기한을 함께 넣어 이미 도는 지연·임박 알림(09:30)이 잡게 한다.
#   ★담당이 비면 등록하지 않는다 — 주인 없는 일을 장부에 쌓지 않는 것이 약속 L23 의 순서다.
#   ★새 원장·새 스크립트를 만들지 않는다(L21). 이미 있는 _digest_ledger.json 의 이슈 항목에
#     todo_id 한 칸만 더 얹어 짝을 맞춘다.
_OWNER_CHOICES = ["이경연 실장", "최준용M", "윤병현AM", "임정은M", "백승화 사원",
                  "이정헌 소장", "나우열M"]
_CATEGORY_CHOICES = ["[1] 매출 및 영업", "[2] 인사", "[3] 파트너팀", "[4] 운영 정책",
                     "[5] 시설 및 환경", "[6] 회원·CS", "[7] IT·시스템·자동화",
                     "[8] 교육·조직문화", "[9] 회의"]
# 기한이 대화에 없을 때 넣는 임시 기한(일). 빈칸으로 두면 지연·임박 알림이 그 건을 영영
# 안 잡아 '놓치지 않게'라는 요구가 깨진다 — 대신 제목에 (기한 임시)를 붙여 지어낸 값이
# 아님을 사람이 바로 알게 한다.
_DEFAULT_DUE_DAYS = 7
_BRIDGE_CREATOR = "AI 아침정리"
_OWNER_LIST = " · ".join(_OWNER_CHOICES)
_CATEGORY_LIST = " · ".join(_CATEGORY_CHOICES)

# 지출품의 GAS(배97 · 매출/지출/구매물품 정본) — 매출지출현황.html PROC_API와 동일 배포본.
# 비밀번호는 telegram_bot/.env(저장소 밖)에서 읽는다(배328 — .js 소스 평문 노출 제거, 배326 과 같은 계열).
PROC_EXEC_URL = os.environ.get(
    "PROC_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbxUAQ3DefJt13z5Bsz5KlGw6BwS2lDeLgHDMeTHjifLYGuk1lNyEpARYQ20XcjJXNj5/exec",
)
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
        reception_elapsed_days as _reception_elapsed_days,
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
        reception_elapsed_days as _reception_elapsed_days,
        utc_iso_to_kst_date as _utc_iso_to_kst_date,
    )

MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")
DATE_SEP_RE = re.compile(r"^-{3,}.*?(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일.*-{3,}\s*$")
MSG_RE = re.compile(r"^\[(?P<name>.+?)\]\s*\[(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<m>\d{2})\]\s*(?P<msg>.*)$")
SYSTEM_LINE_RE = re.compile(r".*(들어왔습니다|나갔습니다|저장한 날짜)\.?\s*$")

# 자동 발신(봇 리포트) 판별 — 4개방 확장(2026-08-15 GM 지시)으로 새로 생기는 요약 잡음 대응.
# ★발신자명으로는 못 거른다(실측 2026-08-15 ★운영부·★중간관리자 8월 원문): 하루 일과 정리·
# HR/CFO 브리핑·주간보고 초안 전부 GM 개인 카톡계정("김남욱")이나 나우열M 계정으로 나가고
# 있어, 사람이 직접 쓴 말과 발신자가 같다. 대신 본문 첫 줄 고정 머리글/말미 서명으로 가른다.
AUTO_BROADCAST_HEADER_RE = re.compile(
    r"^("
    # ★2026-08-31 제목 통일에 맞춰 넓혔다 — 「🌅 하루의 시작」·「🌙 하루의 마무리」.
    #   옛 문구(🌅 …정리 · / 📊 [하루 일과 정리])도 그대로 둔다: 방에 이미 쌓인 지난 메시지가
    #   내일부터 갑자기 '사람이 쓴 말'로 잡혀 요약에 섞이면 안 된다.
    r"🌅 하루의 시작|"                                   # ops_daily_digest 자신의 아침 통(같은 방으로 되돌아온 것)
    r"🌙 하루의 마무리|"                                 # report_stream_1/2/2b/3 저녁 통
    r"🌅 .*정리 · |"                                    # (옛) ops_daily_digest 전날 정리
    r"📊 \[하루 일과 정리\]|"                             # (옛) report_stream_1/2/2b/3 통일 포맷
    r"📊 .*(아침 브리핑|회장님 매출보고)|"                  # module_reporter(CFO 등) · kakao_auto_daily_report
    r"📋 (.*아침 브리핑|운영부 주간 보고 초안\(자동 생성)|"  # module_reporter(HR) · send_ops_digest 주간보고
    r"🧭 .*(어제 정리 — 판단·배정 필요한 것만|아침 보고 ·)|"  # send_ops_digest · module_reporter
    r"(🧾 사람이 처리할 업무|📌 오늘 확인 부탁드릴 것) "      # send_ops_digest RELAY(업무 장부 전달 · 2026-08-18 문구 교체, 옛 문구도 계속 거른다)
    r")"
)
# 옛 문구도 계속 둔다 — 이미 방에 쌓인 지난 메시지가 다시 '사람 말'로 잡히면 안 된다.
# "AI 웰리 드림" = 2026-08-21 GM 확정 신규 서명(send_ops_digest.RELAY_SIGNOFF).
AUTO_BROADCAST_SIGNOFF = ("웰페리온 AI 총괄 담당 웰리 드림", "— AI 웰리", "AI 웰리 드림")


def _is_auto_broadcast(msg: str) -> bool:
    """카톡 메시지 1건이 AI 자동 리포트면 True(요약 대상에서 제외). 사람이 직접 쓴 말만
    남겨야 사람 대화가 봇 발신에 묻히지 않는다(GM 2026-08-15 — 4개방 확장 지시)."""
    body = msg.strip()
    if not body:
        return False
    first_line = body.splitlines()[0]
    if AUTO_BROADCAST_HEADER_RE.match(first_line):
        return True
    return any(sig in body for sig in AUTO_BROADCAST_SIGNOFF)

# 카톡 표시명 → 실명 (배536 후속 2026-08-11 — 발신 직전 웰리 손 치환 목격). 파싱 단계에서
# 바로잡아 두면 대화 원문·프롬프트·LLM 출력 전부 실명으로 나간다(후처리 문자열치환보다 안 깨짐).
# ★확신 있는 것만: ssot/kpi.json roles.cfo/chro.staff · ssot/ownership_map.json 리더/구성원 ·
# scripts/kakao_rooms.json members 전부 "나우열M"인데 카톡 표시명만 "라우열"로 어긋난다.
DISPLAY_NAME_ALIAS = {"라우열": "나우열M"}


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
        return _reception_elapsed_days(r, today_dt)

    unresolved = [r for r in rows if str(r.get("status", "")) not in _RESOLVED_STATUSES]
    if not unresolved:
        lines.append(" • 미해결 없음 👍")
        return "\n".join(lines)

    # 2주 넘게 방치된 건은 자동으로 '대기·보류'로 내려 매일 푸시에서 제외(에너지 절약, GM 2026-07-14).
    STALE_DAYS = 14
    active = sorted((r for r in unresolved if _elapsed_days(r) < STALE_DAYS), key=_elapsed_days, reverse=True)
    stale = sorted((r for r in unresolved if _elapsed_days(r) >= STALE_DAYS), key=_elapsed_days, reverse=True)

    # [2026-08-29 GM 지시 · 카톡 중복 정리] ★운영부 아침은 건수만 낸다 — 접수 원문 펼침은
    # 4부서방 아침 통(send_ops_digest._build_ovd_block) 한 곳뿐이다. 같은 건 원문이 아침에
    # 두 방(4부서방·★운영부)으로 겹쳐 나가던 것을 끊는다(오래된 순 3건·가장 오래된 건 전문
    # 나열 삭제 — 정보는 4부서방 통과 종합접수처 화면에 그대로 있다).
    oldest = max(unresolved, key=_elapsed_days)
    lines.append(
        f" • 미해결 {len(unresolved)}건 — 2주내 {len(active)} · 보류(2주+) {len(stale)}"
        f" · 최장 {_elapsed_days(oldest)}일"
    )
    lines.append("   (상세 목록은 아침 4부서방 통과 종합접수처 화면에 있습니다)")

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
    """지출품의 GAS 비밀번호 — 환경변수 우선, 없으면 telegram_bot/.env(저장소 밖) 한 줄.
    값은 저장소에 두지 않는다(배328 — .deploy-procurement/procurement.js 평문 노출이 문제였다)."""
    k = os.environ.get("PROC_PW", "").strip()
    if k:
        return k
    try:
        for line in (ROOT / "telegram_bot" / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("PROC_PW="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
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
            name = m.group("name").strip()
            name = DISPLAY_NAME_ALIAS.get(name, name)
            cur_msg = {"time": time_str, "name": name, "msg": m.group("msg")}
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
# ★2026-08-19 GM 결정(배698) — 못 나간 날은 다음날이 흡수한다. 종전 fallback("파일 내
#   가장 최근 완결일")의 문제: 그 완결일이 **이미 발송된 옛 날짜**일 수 있다 — 실측
#   2026-08-19, ★운영부가 08-18을 못 잡고 08-17(이미 어제 보낸 날)을 다시 골랐다. 마지막
#   발송일(하트비트)을 기준으로 "그 이후 아직 안 보낸 날"만 고르면 같은 날 재처리도,
#   못 보낸 날이 조용히 사라지는 것도 막힌다. 여러 날이 밀렸으면 한 통에 모아 흡수
#   (ABSORB_CAP_DAYS로 상한 — 안 그러면 한 통이 감당 못 하게 길어진다).
ABSORB_CAP_DAYS = 3
_LAST_SENT_HEARTBEAT = {"★운영부": "ops-digest-last-sent-ops", "★중간관리자": "ops-digest-last-sent-mgr"}


def _last_sent_date(room_dir_name: str) -> str | None:
    """그 방으로 마지막 발송 성공한 날짜 — send_ops_digest.py가 발송 성공 시에만 적는다.
    하트비트가 없으면(콜드스타트) None — 옛 단일일 로직으로 폴백."""
    hb_id = _LAST_SENT_HEARTBEAT.get(room_dir_name)
    if not hb_id:
        return None
    try:
        from module_heartbeat import last_heartbeat
        rec = last_heartbeat(hb_id)
    except Exception:
        return None
    if not rec:
        return None
    return str((rec.get("state") or {}).get("date") or "") or None


def pick_target_dates(by_date: dict[str, list[dict]], forced_date: str | None,
                      last_sent_date: str | None) -> tuple[list[str], str]:
    """대상일(들) 결정. forced_date 지정 시 그 하루만(수동·테스트 경로 — 흡수 없음).

    last_sent_date 가 있으면: 그 이후 ~ 어제까지 완결된 날을 전부 골라 흡수한다
    (ABSORB_CAP_DAYS 상한 — 넘으면 최근 것만 남기고 그 앞은 생략, 생략분은 이유에 남긴다).
    last_sent_date 가 없으면(콜드스타트) 종전 단일일 동작 그대로(어제 → 없으면 파일 내
    최근 완결일)."""
    today = datetime.now().date()
    if forced_date:
        if forced_date in by_date:
            return [forced_date], f"수동 지정({forced_date})"
        return [], f"수동 지정일({forced_date}) 대화 없음"

    yesterday = (today - timedelta(days=1)).isoformat()
    completed_dates = sorted(d for d in by_date if d < today.isoformat())

    if last_sent_date is None:
        if yesterday in by_date:
            return [yesterday], f"어제({yesterday})"
        if completed_dates:
            chosen = completed_dates[-1]
            return [chosen], f"어제({yesterday}) 분 없음 → 파일 내 가장 최근 완결일({chosen}) 대체 사용"
        return [], "완결된 하루(오늘 이전 날짜) 대화 없음 — 파일에 오늘자 또는 미완결 데이터만 존재"

    pending = [d for d in completed_dates if d > last_sent_date]
    if not pending:
        return [], f"마지막 발송({last_sent_date}) 이후 새 완결일 없음"
    if len(pending) > ABSORB_CAP_DAYS:
        skipped = pending[:-ABSORB_CAP_DAYS]
        pending = pending[-ABSORB_CAP_DAYS:]
        return pending, (f"{last_sent_date} 이후 {len(skipped) + len(pending)}일 밀림 → "
                         f"최근 {ABSORB_CAP_DAYS}일만 흡수(그 전 {len(skipped)}일 · "
                         f"{skipped[0]}~{skipped[-1]} 생략)")
    if len(pending) > 1:
        return pending, f"{last_sent_date} 이후 {len(pending)}일 밀림 → {pending[0]}~{pending[-1]} 흡수"
    return pending, f"어제({pending[0]})"


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
def build_prompt(target_date: str, conversation: str, past_issues_digest: str, room_dir_name: str = "★운영부") -> str:
    room_short = room_dir_name.replace("★", "")  # 헤더용 짧은 표기(예: "운영부"·"중간관리자")
    try:
        _d = datetime.strptime(target_date, "%Y-%m-%d")
        disp = f"{_d.month}/{_d.day}(" + "월화수목금토일"[_d.weekday()] + ")"
        # ★2026-08-31 — 아침 통 이름을 「하루의 시작」으로 통일한다(2026-08-29 확정안 · GM 승인).
        #   아침에 네 통이 각기 다른 제목으로 들어오면 실무진은 그때그때 무엇인지 다시 읽어야 한다.
        #   앞머리가 같으면 '아침에 오는 것'으로 한 덩어리로 잡히고, 뒤 부제로 어느 방 것인지 갈린다.
        #   ▸판별 목록(kakao_report_sender._ROUTINE_DIGEST_HEADS)에 「🌅 하루의 시작」을 먼저 넣어 뒀다 —
        #     안 넣고 제목만 바꾸면 실장 경유 가드가 아침 통을 통째로 막는다(2026-08-19~20 실사고).
        # 대상일이 '진짜 어제'면 날짜를 그대로, 아니면(휴관 폴백 등) 날짜만 — 오해 방지
        _yest = (datetime.now().date() - _d.date()).days == 1
        _when = f"어제 · {disp}" if _yest else disp
        header_label = f"하루의 시작 — {room_short} {_when}"
    except Exception:
        disp = target_date
        header_label = f"하루의 시작 — {room_short} {target_date}"
    return f"""당신은 웰페리온(프리미엄 스포츠클럽 멤버십 커뮤니티) AI COO '시우'입니다.
{room_dir_name} 카카오톡 방의 어제({target_date}) 하루 대화를 읽고, 오늘 아침 방에 바로 보낼 요약 메시지 1통을 작성합니다.

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

✅ 확인된 것 (해당할 때만 · 없으면 이 섹션 통째로 생략)
 • [확인자] 님이 [시각]에 확인 — 무엇이 확인·완료됐는지 한 줄. 최대 4줄.

⚠️ 오늘 챙길 것
 • 안 끝난(미해결) 건을 담당자 이름 붙여 한 줄씩 — 많으면 중요한 순으로 최대 5줄. 정말 없으면 '• 특이사항 없음'.

🔁 반복 (해당할 때만 · 없으면 이 섹션 통째로 생략)
 • 원장 이력과 비교해 며칠째 반복되는 문제만, 최대 2줄. 확실치 않으면 넣지 말 것.

💪 (★반드시 포함 — 매일 빠뜨리지 말 것) 그날 대화 분위기·요일·특이사항을 반영한 '그날만의' 따뜻한 격려·응원 한 줄. 매일 다르게, 판박이·복붙 금지. 감시 아닌 따뜻한 동료 톤. 메시지가 아무리 짧아도 이 격려 한 줄은 항상 남긴다.

★★짝맞춤 규칙 (GM 지적 2026-08-14 · 이 규칙을 어기면 실무진이 어제 답한 걸 오늘 또 답하게 된다):
대화는 위에서 아래로 흐른다. 앞쪽에서 나온 요청·질문에 **같은 날 뒤쪽에서 답·완료 보고가 붙은 경우가 많다.**
요청만 뽑고 그 답을 안 보면, 이미 닫힌 건이 다음날 '오늘 챙길 것'으로 다시 나간다. 실무진 입장에서는
답을 해도 소용없는 방이 되고, 그러면 답을 안 하게 된다.
- 한 항목을 '⚠️ 오늘 챙길 것'에 넣기 전에 **그 대화 뒤쪽 전체를 끝까지 훑어** 답·완료 보고가 있는지 본다.
- 답이 있으면 '⚠️ 오늘 챙길 것'에 넣지 않는다. 대신 '✅ 확인된 것'에 **누가·몇 시에 확인했는지와 함께** 적는다.
  예: ' • 최준용M 님이 21:29에 확인 — 8/12 기준 멤버십·준회원·유소년 이관 완료'
- 답이 '아직 안 됐습니다' 같은 부정 확인이어도 **확인 자체는 끝난 것**이다. ✅ 로 보내되 남은 일이 있으면
  그 남은 일만 ⚠️ 에 새로 적는다(확인을 또 요청하지 않는다).
- 답이 일부만 왔으면 받은 부분은 ✅, 아직 안 온 부분만 ⚠️ 로 쪼갠다.
- 확인자 이름·시각은 대화에 적힌 그대로만 쓴다. 시각을 모르면 시각을 빼고 이름만 적는다(지어내지 않는다).
- ★한 번 더 대조하고 낸다: '⚠️ 오늘 챙길 것'에 적은 줄을 **하나씩 다시 읽으면서** 그 건의 답이
  대화 어딘가에 있는지 본다. 있으면 그 줄을 ✅ 로 옮긴다. 이 대조를 건너뛰면 안 된다.
- ★이미 답을 받은 건에 '확인 필요'·'확인 요청'·'확인 바람' 이라고 쓰지 않는다. 확인은 끝났다.
  남은 것이 있으면 **남은 행동**을 쓴다(예: '확인 필요' ✗ → '비공개처리 적용' ○).
- 답을 준 사람이 있으면 '✅ 확인된 것'은 **비우지 않는다.** 그 사람이 어제 답한 것을 오늘 화면에서
  보지 못하면, 답해도 소용없는 방이 된다.

정직 규칙(중요):
- 대화에 실제로 있는 내용만. 지어내거나 과장 금지. 애매하면 '~인 것 같아요' 정도로.
- ★압박 표기 금지(GM 확정 2026-08-15): 'N일째'·'아직도'·'재요청' 같은 밀림 표기를 실무진 앞 문장에 쓰지 않는다. 밀린 건 우리 사정이다 — 남은 행동만 담백하게 적는다(예: '5일째 미해결' ✗ → '수리 일정 확인 필요' ○).
- 이름은 대화에 나온 그대로 사용. 사소한 잡담·인사는 굳이 항목화하지 않되 분위기는 반영.
- ★정체 정규화(위 규칙보다 우선 — 절대 예외 없음): 김남욱은 GM이다 → 반드시 'GM(김남욱)' 또는 'GM님'으로만 표기한다. 대화 원문에서 누가 김남욱을 '대표님'/'대표'라고 불렀어도 그 호칭을 그대로 쓰지 말고 GM으로 정규화한다. '대표님'/'대표'는 오직 전응준 대표를 지칭할 때만 쓴다. 차의주는 회장님.
- 대화가 짧거나 특이사항 없으면 억지로 항목을 만들지 말고 담백하게.

출력 형식(반드시 순수 JSON 하나만 — 코드블록·설명·머리말 없이):
{{
  "message": "위 구조 그대로 카카오톡에 보낼 아침 메시지 전문(한국어 · 글머리·이름별 정리)",
  "issues": [
    {{"issue": "이슈 한 줄 요약", "status": "open 또는 resolved", "note": "근거·짧은 메모",
      "owner": "담당자", "due": "YYYY-MM-DD", "category": "분류"}}
  ],
  "schedules": [
    {{"date": "YYYY-MM-DD", "title": "일정 한 줄 이름", "dept": "담당 부서 또는 사람", "note": "근거가 된 대화 내용 한 줄"}}
  ]
}}
issues는 대화에서 실제로 확인되는 미해결·해결 이슈만 담는다(없으면 빈 배열 []).

issues의 owner·due·category 규칙(이 세 칸은 업무 장부에 자동 등록될 때 쓰인다 — 틀리면 엉뚱한
사람에게 일이 배정된다):
- owner: 대화에서 그 일을 맡기로 한 사람이 분명할 때만 적는다. 아래 목록에 있는 이름만 쓴다.
  {_OWNER_LIST}
  분명하지 않거나 목록에 없는 사람(GM·회장님·대표님·외부 업체 등)이면 빈 문자열 "".
  ★추측 금지 — 애매하면 빈 문자열이 정답이다. 빈 문자열이면 장부에 안 올라가고 사람이 정한다.
- due: 대화에 기한·날짜가 나올 때만 YYYY-MM-DD 로. 없으면 빈 문자열 "".
- category: 아래 중 하나를 고른다(가장 가까운 것). 애매하면 빈 문자열 "".
  {_CATEGORY_LIST}

schedules 규칙(이 칸은 전사일정 화면에 자동 등록된다 — 없는 일정을 만들면 회사 달력이 거짓이 된다):
- 넣는 것: ①날짜가 대화에 분명히 나오고 ②앞으로 일어날 일이고 ③놓치면 회사에 영향이 있는 것.
  해당 예 — 외부 방문·정기검사·법정점검·업체 미팅·납품·계약/보고 마감·면접·교육.
- 넣지 않는 것: 부서 내부 청소 당번·일상 루틴·이미 지나간 일·날짜가 없거나 '다음 주쯤' 같은 어림.
  ★확신이 없으면 넣지 않는다. 빈 배열 [] 이 정답인 날이 대부분이다.
- date: 반드시 YYYY-MM-DD. '8/20', '다음 주 목요일' 같은 표현은 {target_date} 를 기준으로 실제 날짜로 바꿔 적는다.
- time: 대화에 시각이 나오면 24시간 HH:MM 으로. '오전 10시'→'10:00', '오후 2시'→'14:00', '2시반'→'14:30'.
  ★시각이 안 나오면 빈 문자열 "". 지어내지 않는다 — 화면에는 '시간 미정'으로 뜨고 그게 정직한 표시다.
- title: 사람이 달력에서 보고 바로 아는 짧은 이름(예: '승강기 정기검사'). 대화 문장을 그대로 옮기지 않는다.
- dept: 그 일을 맡는 부서·사람이 대화에 분명할 때만. 아니면 빈 문자열 "".
"""


def call_brain(prompt: str) -> tuple[str | None, str | None]:
    try:
        from model_router import run_claude
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_router import run_claude
    return run_claude(prompt, label="ops-daily-digest")


def parse_brain_json(raw: str) -> tuple[str, list[dict], list[dict], bool]:
    """claude 응답에서 {"message","issues","schedules"} JSON 파싱.
    실패 시 원문을 메시지로, issues·schedules=[] (정직 강등)."""
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
        schedules = data.get("schedules") or []
        if not isinstance(schedules, list):
            schedules = []
        if message:
            return message, issues, schedules, True
    except json.JSONDecodeError:
        pass
    return raw.strip(), [], [], False


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def _run_one_day(target_date: str, room_dir_name: str, by_date: dict,
                 export_path: Path, bridge_dry_run: bool) -> str | None:
    """하루치 정리 생성 — run()의 옛 몸통을 그대로(로직 변경 없음) 날짜 하나 단위로 뽑은 것
    (배698 · 2026-08-19). 여러 날을 흡수할 때 이 함수를 날짜마다 호출해 결과를 이어붙인다
    — 단일일 경로(절대다수)는 이 함수를 정확히 한 번만 불러 기존과 동일하게 동작한다."""
    day_messages = by_date[target_date]
    human_messages = [m for m in day_messages if not _is_auto_broadcast(m["msg"])]
    auto_n = len(day_messages) - len(human_messages)
    if auto_n:
        print(f"  → 자동 발신(봇 리포트) {auto_n}건 제외 — 사람 대화 {len(human_messages)}건만 요약 대상")
    conversation = format_conversation(human_messages)
    if not conversation.strip():
        print(f"[실패] {target_date} 사람 대화 0건(자동 발신 {auto_n}건 제외) — 요약 생성 안 함.")
        return None

    ledger = load_ledger()
    # 역방향 먼저 — 장부에서 닫힌 건을 원장에 반영하고 나서 프롬프트를 만든다. 순서가 바뀌면
    # 이미 끝난 일이 오늘 정리의 '반복·미해결'에 또 실린다.
    closed = pull_done_from_todo(ledger)
    if closed:
        save_ledger(ledger)
        print(f"  → 장부에서 완료된 건 {closed}건을 원장에 반영(양방향 회수)")
    past_digest = recent_issues_digest(ledger, before_date=target_date)

    print("[4/5] 두뇌(claude CLI · model_router 폴백) 호출...")
    prompt = build_prompt(target_date, conversation, past_digest, room_dir_name=room_dir_name)
    raw_out, used_model = call_brain(prompt)
    if raw_out is None:
        print("[실패] claude CLI 전 모델 실패 — 메시지 생성 불가(원장도 갱신 안 함). model_router 로그·텔레그램 경보 확인 요망.")
        return None

    message, issues, schedules, json_ok = parse_brain_json(raw_out)
    if not json_ok:
        print("  → 경고: JSON 파싱 실패 — 응답 원문을 메시지로 사용, 이번 회차 이슈 원장 갱신은 생략(정직 강등).")
    else:
        # 보내기 전 회신 대조(2026-08-15 GM 지시) — LLM 짝맞춤 지시만으론 안 새는 게
        # 8/14 실측으로 드러났다(08:05→08:24 보완 발송). 코드 대조로 한 겹 더 거른다.
        auto_resolved = mark_late_replied_resolved(issues, human_messages)
        if auto_resolved:
            print(f"  → 코드 대조: 대화 후반부 본인 확인 발언 감지 {len(auto_resolved)}건 자동 해결 처리(재요청 방지)")
            message = strip_confirmed_bullets(message, [i["issue"] for i in auto_resolved])
        ledger = upsert_ledger(ledger, target_date, issues, source_file=export_path.name)
        save_ledger(ledger)
        print(f"  → 원장 갱신: {LEDGER_PATH.relative_to(ROOT)} (이슈 {len(issues)}건, 날짜 {target_date})")

    # 전사일정 다리(배577) — 메시지를 조립하기 전에 등록한다. 등록 결과를 그 메시지에 한 줄로
    # 붙여 같이 내보내기 위해서다(새 발송 경로를 만들지 않는다 · 약속 L21).
    schedule_added = bridge_to_schedule(schedules, target_date, room_dir_name,
                                        dry_run=bridge_dry_run) if json_ok else []

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
    # 문의·예약 / 종합접수 / 💪 항상 맨끝.
    # 🏢 점검은 제외(22:30 밤 점검공유 스트림#2가 별도 담당).
    # 💰 매출·지출·구매(finance_block) · 🗂️ 업무 SSOT(work_block) 은 2026-08-05 GM 지시로
    # 이 07:32 메시지 본문에서 제외한다(카카오 간결화 — "실무진 혼란 최소화"). 정보 소실
    # 아님: 매출은 같은 방(★운영부)에 09:30~31 매출보고 이미지로, 업무 SSOT는 같은 방에
    # 09:30 「하루 일과 정리」 메시지(report_stream_3)로 그날 안에 더 상세히 나간다.
    # finance_block 은 원장 metrics 스냅샷(다음날 전일대비 계산용)을 위해 계속 계산만 한다.
    # 배536(2026-08-11 GM 확정) — 📩문의·등록/📣종합접수는 같은 GAS 원천이라 두 방에 그대로
    # 나가면 중복이다. ★운영부(공유 전용, 약속 L24)만 유지하고 ★중간관리자는 뺀다.
    # ⚠️오늘 챙길 것은 LLM 출력(llm_body) 안에 있고 두 방 다 그 방 대화가 달라 내용도 다르므로
    # 손대지 않는다(GM: "오늘 챙길 것은 두 방의 대화가 다르니 내용도 서로 다르다 — 중복 아니다").
    header, llm_body, warm = _split_llm(message)
    parts = [header, llm_body]
    # ★2026-08-18 GM 결정(배670) — 되묻는 문구("SSOT 에 올리실 건가요?"·"틀리면 한 줄
    #   주세요")는 ★운영부에 넣지 않는다. ★운영부는 공유 전용(약속 L24) — 답을 요구하지
    #   않는다. 두 문구 다 실질적으로 회신을 구하는 질문이라 ★중간관리자(소통 창구)로만.
    if room_dir_name != "★운영부":
        # 「🗂 업무 SSOT 에 올리실 건가요?」 되묻기 절은 GM 지시(2026-08-29)로 삭제 —
        # _bridge_ask_lines 함수째 지웠다(배589 되묻기 종료 · 등록은 여전히 사람이 한다).
        _sched_reply = _schedule_reply_lines(schedule_added)
        if _sched_reply:
            parts.append(_sched_reply)
    if room_dir_name == "★운영부":
        parts += [mid_block, reception_block]
    final_message = "\n\n".join(p.strip() for p in parts if p and p.strip())
    if warm:
        final_message += "\n\n" + warm.strip()

    print("\n" + "=" * 60)
    print(f"[대상일] {target_date}  |  [사용모델] {used_model}  |  [원장반영] {'예' if json_ok else '아니오(파싱실패)'}")
    print("=" * 60)
    print(final_message)
    print("=" * 60)

    bridge_to_todo(ledger, target_date, room_dir_name, dry_run=bridge_dry_run)
    return final_message


def run(forced_date: str | None = None, room: str = DEFAULT_ROOM,
        bridge_dry_run: bool = False) -> int:
    global KAKAO_ROOM_DIR, LEDGER_PATH, PENDING_DIGEST_PATH
    room_dir_name = room.replace(" ", "")
    KAKAO_ROOM_DIR = ROOM_DIR_BASE / room_dir_name
    LEDGER_PATH = KAKAO_ROOM_DIR / "_digest_ledger.json"
    PENDING_DIGEST_PATH = KAKAO_ROOM_DIR / "_pending_digest.json"

    print(f"[시작] {room_dir_name} 카톡 아침 요약 두뇌 — {now_str()}")

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

    last_sent = _last_sent_date(room_dir_name) if not forced_date else None
    target_dates, why = pick_target_dates(by_date, forced_date, last_sent)
    if not target_dates:
        print(f"[실패] 대상일 결정 불가 — {why}")
        return 1
    print(f"[3/5] 대상일 = {target_dates} ({why})")

    day_outputs: list[tuple[str, str]] = []
    for d in target_dates:
        msg = _run_one_day(d, room_dir_name, by_date, export_path, bridge_dry_run)
        if msg:
            day_outputs.append((d, msg))
        else:
            print(f"  → {d} 생성 실패 — 이 날짜는 흡수본에서 빠진다(다음 회차에 다시 시도됨)")
    if not day_outputs:
        print("[실패] 흡수 대상 날짜 전부 생성 실패")
        return 1

    if len(day_outputs) > 1:
        # 배698(2026-08-19 GM 결정) — 못 나간 날은 다음날이 흡수한다. 흡수 표시를 본문에
        # 남긴다(실무진이 '왜 이틀치가 오지' 하지 않게).
        note = (f"※ {day_outputs[0][0]}~{day_outputs[-1][0]} 카톡 정리가 밀려 "
               f"{len(day_outputs)}일치를 함께 보냅니다.")
        final_message = note + "\n\n" + ("\n\n" + "━" * 10 + "\n\n").join(m for _, m in day_outputs)
    else:
        final_message = day_outputs[0][1]
    final_date = day_outputs[-1][0]

    PENDING_DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"date": final_date, "generated_at": now_str(), "message": final_message, "sent": False}
    if len(day_outputs) > 1:
        payload["absorbed_dates"] = [d for d, _ in day_outputs]
    PENDING_DIGEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"  → 발송 대기 저장: {PENDING_DIGEST_PATH.relative_to(ROOT)} (발송은 범위 밖 — 게이트 대기)")
    return 0


# ═══════════════════════════════════════════
#  업무 장부 다리 — 정방향(등록) · 역방향(완료 회수)
#  GM 승인 2026-08-12. 위 상수 블록의 설명 참조.
# ═══════════════════════════════════════════
_BRIDGE_SWITCH = ROOT / "status" / "ops_digest_send.json"


def _bridge_enabled() -> bool:
    """킬스위치 — 기존 발송 스위치 파일에 키 하나만 얹는다(새 파일 금지 · 약속 L21).
    키가 없으면 꺼진 것으로 본다: 실무진 장부에 줄을 만드는 일이라 기본값은 '안 함'이다."""
    try:
        return bool(json.loads(_BRIDGE_SWITCH.read_text(encoding="utf-8")).get("todo_bridge_enabled"))
    except Exception:
        return False


def _todo_post(params: dict, timeout: int = 60) -> dict:
    """업무 SSOT GAS 쓰기. 화면(업무 현황 SSOT.html)이 쓰는 것과 같은 통로·같은 action."""
    import urllib.request
    req = urllib.request.Request(
        SSOT_API_URL, data=json.dumps(params, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _todo_status_by_id() -> dict:
    """업무 SSOT 전체를 {id: 상태} 로. 실패하면 빈 dict — 역방향은 조용히 건너뛴다
    (조회 실패를 '완료'로 읽으면 열린 일이 사라진다)."""
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list"}, timeout=40, label="다리 역방향")
    if resp is None:
        return {}
    try:
        data = resp.json()
        if not data.get("ok"):
            return {}
        return {str(r.get("id")): str(r.get("상태", "")) for r in data.get("data", []) if r.get("id")}
    except Exception:
        return {}


def pull_done_from_todo(ledger: list[dict]) -> int:
    """역방향 — 장부에서 완료된 건을 원장에서 해결로 바꾼다.

    이렇게 해야 다음 아침 정리의 '반복·미해결' 절에서 그 건이 저절로 빠진다(프롬프트가
    원장을 읽는다). 사람이 장부에서 닫으면 카톡 정리도 따라 닫히는 것이 GM 이 말한 양방향이다."""
    status_map = _todo_status_by_id()
    if not status_map:
        return 0
    changed = 0
    for entry in ledger:
        for issue in entry.get("issues") or []:
            tid = str(issue.get("todo_id") or "")
            if not tid or issue.get("status") == "resolved":
                continue
            if status_map.get(tid, "") in _TODO_DONE_STATUSES:
                issue["status"] = "resolved"
                issue["note"] = (issue.get("note") or "").strip()
                issue["note"] = (issue["note"] + " · " if issue["note"] else "") + "업무 장부에서 완료 처리됨"
                changed += 1
    return changed


# ═══════════════════════════════════════════
#  보내기 전 회신 대조 (GM 지시 2026-08-15 · 중복 알림 정리)
#  배경: build_prompt(위)의 '★★짝맞춤 규칙'을 2026-08-14 넣었는데도 같은 날 08:05 발송이
#  이미 답 준 항목을 다시 실었고, 08:24 에 사람이 「🔎 어제 정리 보완」을 따로 보내야 했다.
#  LLM 지시만으론 안 샌다는 게 그날 바로 실측됐다 — 코드 대조를 한 겹 더 얹는다.
#  낱말겹침 판정은 새로 만들지 않고 kungjjak_board.find_repeats 가 쓰는 것과 같은 기준
#  (_norm 재사용, 낱말 절반 이상 겹치면 같은 내용)을 그대로 쓴다(약속 L21).
# ═══════════════════════════════════════════
from kungjjak_board import _norm as _word_set  # noqa: E402

_LATE_REPLY_KEYWORDS = ("완료", "확인", "됐습니다", "됩니다", "끝났", "처리했", "전달했", "했습니다", "됨")


def _late_reply_texts_by_owner(messages: list[dict]) -> dict[str, list[str]]:
    """이름별로 해결·확인 신호가 담긴 문장만 모은다(오늘 대화 안 뒤쪽 자기 회신 탐지용)."""
    out: dict[str, list[str]] = {}
    for m in messages:
        msg = str(m.get("msg") or "")
        if any(k in msg for k in _LATE_REPLY_KEYWORDS):
            out.setdefault(str(m.get("name") or ""), []).append(msg)
    return out


def _overlaps(a: str, b: str) -> bool:
    """공통 낱말이 있으면 같은 내용으로 본다. ★kungjjak_board.find_repeats 는 '절반 이상'을
    쓰지만(같은 사람이 짧은 지시를 비슷한 말로 반복하는 경우), 여기는 3~6낱말짜리 이슈
    요약과 자연스러운 문장체 회신을 비교한다 — 실측(8/13 사례)해 보니 핵심 낱말 1개(예
    '이관')만 겹치고 나머지는 다 다른 표현이라 '절반 이상'을 쓰면 하나도 안 걸린다.
    같은 담당자·해결 키워드까지 이미 겹친 후보만 여기로 오므로(mark_late_replied_resolved),
    낱말 1개 겹침도 오탐보다 다시 안 물어보는 쪽이 낫다는 판단(2026-08-15 GM 지시)."""
    wa, wb = _word_set(a), _word_set(b)
    if len(wa) < 2 or len(wb) < 2:
        return False
    return bool(wa & wb)


def mark_late_replied_resolved(issues: list[dict], messages: list[dict]) -> list[dict]:
    """오늘 대화 뒤쪽에 담당자 본인이 남긴 확인·완료 발언과 낱말이 겹치는 open 이슈를
    resolved 로 자동 강등한다. 강등된 issue 목록을 반환(호출부가 메시지 본문 대조에도 쓴다).
    ledger 에 그대로 저장되므로 다음 날 '반복·미해결' 판정에도
    다시 안 뜬다 — 오늘 발송분만 고치는 게 아니라 내일 재발도 같이 막는다."""
    replies = _late_reply_texts_by_owner(messages)
    fixed: list[dict] = []
    for issue in issues:
        if issue.get("status") != "open":
            continue
        owner = str(issue.get("owner") or "").strip()
        title = str(issue.get("issue") or "").strip()
        if not owner or not title:
            continue
        cand = next((v for k, v in replies.items() if k and (owner in k or k in owner)), None)
        if not cand:
            continue
        if any(_overlaps(title, msg) for msg in cand):
            issue["status"] = "resolved"
            note = str(issue.get("note") or "").strip()
            issue["note"] = (note + " · " if note else "") + "대화 후반부 본인 확인 발언 자동대조로 해결 처리"
            fixed.append(issue)
    return fixed


def strip_confirmed_bullets(message: str, resolved_titles: list[str]) -> str:
    """⚠️ 오늘 챙길 것 섹션에서 자동대조로 이미 해결 처리된 이슈와 겹치는 글머리를 뺀다
    (보내기 전 대조 — 08:05 발송 뒤 08:24 보완 발송이 나갔던 사고 재발 방지). 섹션 표시
    자체는 남기고(형식 유지), 다 빠지면 '특이사항 없음' 한 줄만 남긴다."""
    if not resolved_titles:
        return message
    lines = message.split("\n")
    out: list[str] = []
    in_section = False
    section_marker_idx = None
    removed = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("⚠️"):
            in_section = True
            out.append(line)
            section_marker_idx = len(out) - 1
            continue
        if in_section and stripped[:1] in ("👤", "✅", "🔁", "💪"):
            in_section = False
        if in_section and stripped[:1] in ("•", "-", "·"):
            if any(_overlaps(line, t) for t in resolved_titles):
                removed = True
                continue
        out.append(line)
    if removed and section_marker_idx is not None:
        tail = out[section_marker_idx + 1:]
        if not any(t.strip()[:1] in ("•", "-", "·") for t in tail):
            out.insert(section_marker_idx + 1, " • 특이사항 없음(코드 대조로 자동 확인 처리)")
    return "\n".join(out)


# (_bridge_ask_lines 「🗂 업무 SSOT 에 올리실 건가요?」 되묻기는 2026-08-29 GM 지시로 삭제.)


def bridge_to_todo(ledger: list[dict], target_date: str, room_dir_name: str,
                   dry_run: bool = False) -> int:
    """정방향 — target_date 의 열린 이슈 중 담당이 분명한 것을 업무 SSOT 에 등록한다.

    등록 안 하는 것: 담당 빈칸(주인 없는 일은 장부에 안 쌓는다 · 약속 L23) · 이미 올린 것
    (todo_id 존재) · 해결된 것. 기한이 대화에 없으면 오늘+7일을 임시로 넣고 제목에 그렇게
    적는다 — 기한이 없으면 지연·임박 알림이 영영 안 잡아 '놓치지 않게'가 깨지기 때문이다."""
    # ★★자동 등록은 끝났다 (GM 지시 2026-08-12 · 배589). 코드로 막는다 — 스위치로 두지 않는다.
    #   GM 원문: "SSOT에 올린것들은 삭제해, 실무진들이 할 것 까지 다해버리면 어떻게해" /
    #   "실무진들에게 SSOT올려서 작업하는 현황 보고 받을 수 있도록 진행해야해 웰리가 거기까지 해주면 안되"
    #   무슨 일이었나: 2026-08-12 13:49 카톡 대화 정리에서 5건이 사람 담당으로 자동 등록됐고
    #   (나우열M 2·이경연 실장 2·윤병현AM 1) 4건은 기한이 대화에 없어 7일 뒤로 임의로 박혔다.
    #   왜 끄는가: 업무 SSOT 는 **실무진이 스스로 올리고 그 진행을 보고하는 판**이다. AI 가 대신
    #   올리면 그 사람의 일이 사라지고 우리는 진행 보고를 받을 수 없다.
    #   ▸스위치(todo_bridge_enabled)를 false 로만 두지 않는다 — 꺼둔 게이트는 죽은 코드가 되어
    #     나중에 누가 다시 켠다(약속 L21). 그래서 등록 경로 자체를 여기서 끊는다.
    #   ▸되묻기 절(_bridge_ask_lines)은 2026-08-29 GM 지시로 삭제 — 등록은 사람이 SSOT 화면에서 직접.
    #     등록은 사람이 한다.
    #   ▸구분: 전사일정 자동 등록(배577)은 그대로 간다 — 날짜는 놓치면 안 되고 GM 이 그 방식을 골랐다.
    if not dry_run:
        print("  → 업무 장부 자동 등록: 하지 않는다(GM 지시 2026-08-12 · 배589) — 방에 되묻기로 대체")
        return 0

    entry = next((e for e in ledger if e.get("date") == target_date), None)
    if not entry:
        return 0
    today = datetime.now()
    fallback_due = (today + timedelta(days=_DEFAULT_DUE_DAYS)).strftime("%Y-%m-%d")
    posted = 0
    for issue in entry.get("issues") or []:
        if issue.get("status") != "open" or issue.get("todo_id"):
            continue
        owner = str(issue.get("owner") or "").strip()
        if owner not in _OWNER_CHOICES:
            continue  # 담당 불명 — 사람이 정한다
        due = str(issue.get("due") or "").strip()
        temp_due = not due
        title = str(issue.get("issue") or "").strip()[:80]
        if not title:
            continue
        if temp_due:
            due = fallback_due
            title += " (기한 임시)"
        params = {
            "action": "todo_add",
            "title": title,
            "category": str(issue.get("category") or "").strip(),
            "owner": owner,
            "startDate": today.strftime("%Y-%m-%d"),
            "endDate": due,
            "content": (f"{issue.get('note') or ''}\n\n"
                        f"— {room_dir_name} {target_date} 카톡 대화 정리에서 자동 등록"
                        + ("\n— 기한은 대화에 없어 7일 뒤로 임시 지정했습니다. 담당자가 조정해 주세요."
                           if temp_due else "")).strip(),
            "link": "", "approval": "", "difficulty": "중",
            "creator": _BRIDGE_CREATOR,
        }
        if dry_run:
            print(f"  [다리·미리보기] {owner} ← {title} (기한 {due})")
            posted += 1
            continue
        try:
            res = _todo_post(params)
        except Exception as e:
            print(f"  [다리] 등록 실패({title}): {type(e).__name__}: {e}")
            continue
        new_id = str((res or {}).get("id") or (res or {}).get("data", {}).get("id") or "")
        if not (res or {}).get("ok") or not new_id:
            print(f"  [다리] 등록 거절({title}): {str(res)[:160]}")
            continue
        issue["todo_id"] = new_id
        posted += 1
        print(f"  [다리] 등록 — {owner} ← {title} (기한 {due} · id {new_id})")
    if posted and not dry_run:
        save_ledger(ledger)
    print(f"  → 업무 장부 다리: {posted}건 {'미리보기' if dry_run else '등록'}")
    return posted


# ═══════════════════════════════════════════
#  전사일정 다리 — 카톡 방 말 → 전사일정 자동 등록 (GM 결정 2026-08-12 · 배577)
# ═══════════════════════════════════════════
#  왜: 전사일정 입력칸이 8개라 현장에서 아무도 안 적는다. GM 원문 — "지금은 불편하니까 오히려
#  작성을 잘 안하는듯? 작업자분들이 나이가 있어서 반응이 좋지않음". 그래서 실무진에게 새 화면을
#  가르치는 대신, 이미 쓰는 카톡 방에 말한 것을 우리가 옮겨 적는다.
#  ▸업무 SSOT 다리(위 bridge_to_todo)와 다르다. 그건 **사람의 할 일**이라 AI 가 대신 올리면 안 되고
#    (배589), 이건 **날짜**라 놓치면 회사가 다친다. GM 이 이 방식을 골랐다.
#  ▸새 스크립트·새 GAS·새 발송기를 만들지 않는다(약속 L21). 판독은 이미 도는 같은 LLM 패스에
#    schedules 출력 하나를 얹었고, 등록은 전사일정이 원래 쓰는 save_schedule 을 그대로 부른다.
#  ▸회신도 새 발송이 아니다 — 이 아침 메시지 본문에 한 줄로 붙여 같이 나간다.
_SCHEDULE_SOURCE = "kakao_digest"
_SCHEDULE_MAX_PER_RUN = 3      # 하루에 이 이상 나오면 판독이 헛짚은 것이다 — 넣지 않고 사람에게 남긴다
_SCHEDULE_DUP_RATIO = 0.6      # 같은 날짜에 이 이상 닮은 이름이 있으면 같은 일로 본다


def _schedule_norm(name: str) -> str:
    """이름 비교용 정규화. 공백·괄호류를 없애고, **이름 안에 적힌 날짜·기간 표기도 뗀다.**

    ★2026-09-02 — 날짜를 안 떼서 같은 일이 두 줄로 살아 있었다(GM 지적). 실측:
      「오넛티 팝업 시작 (9/5~9/19)」 vs 「오넛티 추석 팝업 운영 시작」 = 닮음 0.538 로 기준(0.6) 미달.
      이름 뒤에 붙은 기간 표기가 닮음을 끌어내린 것이 원인이었다. 떼고 재면 0.778 로 걸린다.
    """
    s = str(name or "")
    s = re.sub(r"\d{1,2}\s*/\s*\d{1,2}", "", s)          # 9/5, 9 / 19
    s = re.sub(r"\d{1,2}\s*월\s*\d{1,2}\s*일?", "", s)    # 9월 5일
    s = re.sub(r"[~∼–]", "", s)                           # 기간 물결표
    return re.sub(r"[\s·\-—()\[\]]+", "", s)


# 아직 정해지지 않았다고 글쓴이가 스스로 적은 표현들 — 이게 보이면 자동 등록하지 않는다.
# 좁게 고른 이유: '예정'·'미정' 같은 흔한 말까지 넣으면 확정된 일정("9/4 공사 예정", "시간 미정")까지
# 막혀 오히려 일정이 안 올라간다. 사람이 "아직 아니다"라고 말한 표현만 담는다.
_UNCONFIRMED_MARKS = (
    "희망", "미확정", "확답", "확정 전", "확정전",
    "검토 중", "검토중", "가능할까", "가능하실까", "여쭤", "여쭙", "물어보고",
)


def _looks_unconfirmed(title: str, note: str) -> bool:
    """제목이나 메모에 '아직 확정 아님' 표현이 있으면 True (GM 지적 2026-09-02)."""
    blob = f"{title} {note}"
    return any(m in blob for m in _UNCONFIRMED_MARKS)


def _within_a_day(a: str, b: str) -> bool:
    """두 날짜(YYYY-MM-DD)가 같거나 하루 차이면 True. 형식이 아니면 문자열 일치로만 본다."""
    from datetime import date as _d
    try:
        pa = _d(*(int(x) for x in a.split("-")))
        pb = _d(*(int(x) for x in b.split("-")))
    except Exception:
        return a == b
    return abs((pa - pb).days) <= 1


def _selfcheck_schedule_dup() -> None:
    """GM 이 2026-09-02 에 잡아 준 실제 중복 두 건이 이제 걸리는지 — 네트워크 없이 돈다."""
    items = [
        {"name": "오넛티 팝업 시작 (9/5~9/19)", "next_due": "2026-09-05"},
        {"name": "회장님 요가 1:1 수업 미팅 — 나우열M · 김상식 팀장", "next_due": "2026-09-04"},
        {"name": "ADT캡스 공사 — 무인경비 2개소", "next_due": "2026-09-04"},
    ]
    assert _schedule_is_dup("오넛티 추석 팝업 운영 시작", "2026-09-05", items), "이름 속 기간 표기 때문에 못 잡던 건"
    assert _schedule_is_dup("회장님 요가 1:1 수업 미팅", "2026-09-05", items), "하루 어긋나 못 잡던 건"
    # 다른 일까지 같은 일로 묶으면 안 된다
    assert not _schedule_is_dup("세스코 방역 점검", "2026-09-05", items)
    assert not _schedule_is_dup("오넛티 추석 팝업 운영 시작", "2026-09-20", items), "사흘 넘게 떨어지면 남남"

    # 확정 아닌 건이 자동 등록되던 실사고(2026-09-02 GM 지적) — 그 원문으로 검사한다.
    assert _looks_unconfirmed("회장님 오찬 — 필라+골프팀",
                              "나우열M 19:02 강습부서 마지막 오찬으로 17일 14시 희망(회장님 보고 예정·희망 단계)")
    assert _looks_unconfirmed("스쿼시&체조 오찬", "회장님 확답 대기")
    # 확정된 일정까지 막으면 안 된다 — 흔한 말('예정'·'미정')은 통과해야 한다
    assert not _looks_unconfirmed("ADT캡스 공사 — 무인경비 설치", "9/4 10:00 공사 예정")
    assert not _looks_unconfirmed("파트너팀 오찬 — P.T팀 (회장님)", "13:00 확정. 참석=P.T팀 전원")
    assert not _looks_unconfirmed("오넛티 팝업 시작", "시간 미정")
    print("[selfcheck] schedule_dup·unconfirmed OK")


def _schedule_is_dup(title: str, due: str, items: list[dict]) -> str:
    """같은 날짜에 이미 같은 일이 있으면 그 이름을 돌려준다(없으면 빈 문자열).
    사람이 손으로 적은 것도 대상이다 — 같은 사실이 두 줄로 사는 것을 막는다(약속 L23)."""
    from difflib import SequenceMatcher
    a = _schedule_norm(title)
    if not a:
        return ""
    # ★2026-09-02 — 같은 날짜만 보던 것을 하루 앞뒤까지 넓혔다(GM 지적). 실측: 「회장님 요가 1:1 수업
    #   미팅」이 9/4(사람이 등록)와 9/5(카톡 자동 등록) 두 줄로 살아 있었다. 카톡 대화에서 날짜를
    #   읽을 때 하루 어긋나는 일이 흔해, 날짜가 같을 때만 보면 이 부류를 영영 못 잡는다.
    for it in items:
        if not _within_a_day(str(it.get("next_due") or "").strip(), due):
            continue
        b = _schedule_norm(it.get("name"))
        if not b:
            continue
        if a in b or b in a or SequenceMatcher(None, a, b).ratio() >= _SCHEDULE_DUP_RATIO:
            return str(it.get("name") or "")
    return ""


def bridge_to_schedule(schedules: list[dict], target_date: str, room_dir_name: str,
                       dry_run: bool = False) -> list[dict]:
    """일정 후보를 전사일정에 등록하고, 실제로 등록된 것만 돌려준다(회신 줄 만들 때 쓴다).

    거르는 것: 날짜 형식이 아닌 것 · 지난 날짜 · 이름 빈칸 · 같은 날짜에 이미 있는 일 ·
    한 번에 3건 초과. 실패해도 아침 메시지는 그대로 나간다(등록은 부가 기능이지 본업이 아니다).
    id 는 날짜+이름으로 고정이라 같은 날 다시 돌려도 덮어쓰기만 되고 줄이 늘지 않는다."""
    # 0건도 소리를 낸다 — 아무 줄도 안 찍히면 '후보가 없었다'와 '이 다리가 안 돌았다'가
    # 구분되지 않는다. 조용한 성공은 조용한 실패와 같은 얼굴이다.
    print(f"  [일정] 판독 후보 {len(schedules)}건")
    if not schedules:
        return []
    try:
        from collectors.ops_shared import SCHEDULE_GAS_URL
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from collectors.ops_shared import SCHEDULE_GAS_URL

    today = datetime.now().strftime("%Y-%m-%d")
    cands = []
    for s in schedules:
        if not isinstance(s, dict):
            continue
        due = str(s.get("date") or "").strip()
        title = str(s.get("title") or "").strip()[:80]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due) or not title:
            continue
        if due < today:
            print(f"  [일정] 건너뜀 — '{title}' ({due}) 이미 지난 날짜")
            continue
        # 시각은 화면이 이미 읽는 칸(전사_일정.html — it.time)인데 여태 아무도 쓰지 않아
        # 전부 '시간 미정'으로 떴다(GM 지적 2026-08-15 — 카톡엔 '8/19 오전10시'인데 달력은 미정).
        # 형식에 안 맞으면 빈칸으로 둔다 — 지어내지 않는다.
        tm = str(s.get("time") or "").strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", tm):
            tm = ""
        note = str(s.get("note") or "").strip()
        # ★2026-09-02 GM 지적 — 아직 확정 안 된 일이 자동으로 전사일정에 올라갔다.
        #   실사고: 「회장님 오찬 — 필라+골프팀」(9/17). 카톡 원문은 나우열M 이 "17일 14시 희망,
        #   회장님 보고 예정" 이라 한 것인데, 다리가 그대로 일정으로 등록했다. 전사일정은 GM 이
        #   '그 일이 실제로 잡혔나'를 보는 곳이라(약속 L23), 희망·제안 단계가 섞이면 화면이 거짓말을 한다.
        #   → 확정이 아니라고 스스로 적고 있는 후보는 등록하지 않는다. 사람이 확정한 뒤 넣는다.
        if _looks_unconfirmed(title, note):
            print(f"  [일정] 건너뜀 — '{title}' ({due}) 아직 확정 아님(희망·예정·검토 단계)")
            continue
        cands.append((due, title, str(s.get("dept") or "").strip(), note, tm))
    if not cands:
        return []
    if len(cands) > _SCHEDULE_MAX_PER_RUN:
        print(f"  [일정] 후보 {len(cands)}건 — 하루 상한 {_SCHEDULE_MAX_PER_RUN}건을 넘어 전부 건너뜀"
              f"(판독이 헛짚었을 가능성 · 사람이 보고 넣는다)")
        return []

    resp = _gas_get(SCHEDULE_GAS_URL, {"action": "load_schedule"}, timeout=20,
                    label="ops-digest 전사일정")
    try:
        cur = resp.json() if resp is not None else None
    except Exception:
        cur = None
    data = cur.get("data") if isinstance(cur, dict) and cur.get("ok") else None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        print("  [일정] 조회 실패 — 등록 생략(원본 무변경)")
        return []

    items = data["items"]
    by_id = {it.get("id"): it for it in items}
    added = []
    for due, title, dept, note, tm in cands:
        dup = _schedule_is_dup(title, due, items)
        if dup:
            print(f"  [일정] 건너뜀 — '{title}' ({due}) 같은 날짜에 이미 있음: {dup}")
            continue
        sid = f"kkd-{due}-{_schedule_norm(title)[:20]}"
        # dept 칸은 부서 이름만 받는다(시설부·운영부…). 판독이 주는 값은 사람 이름일 때가 많아
        # assignee 로 넣고 dept 는 비운다 — 부서를 지어내지 않는다(약속 L23 · 빈칸은 빈칸으로 둔다).
        # 2026-08-14 실사고: 첫 등록건이 dept="이경연 실장" 으로 들어가 전사일정 계약 검증에
        # '미등록 부서'로 걸렸다.
        item = {
            "id": sid, "type": "이벤트", "name": title, "category": "general",
            "dept": "", "cycle": "", "cycle_confirmed": False, "period_months": None,
            "legal_basis": "", "assignee": dept, "last_done": "", "next_due": due, "time": tm,
            "evidence": "", "applies": "있음",
            "note": f"{room_dir_name} {target_date} 카톡 대화에서 자동 등록"
                    + (f" — {note[:60]}" if note else ""),
            "vendor_id": "", "repeat": "", "source": _SCHEDULE_SOURCE,
        }
        if by_id.get(sid) == item:
            continue  # 같은 날 재실행 — 값이 같으면 아무 일도 하지 않는다
        by_id[sid] = item
        added.append(item)
        print(f"  [일정] 등록 — {due}{(' ' + tm) if tm else ''} {title}" + (f" · {dept}" if dept else ""))

    if not added:
        print("  → 전사일정 다리: 새로 넣을 일정 없음")
        return []
    if dry_run:
        print(f"  → 전사일정 다리: {len(added)}건 미리보기(등록 안 함)")
        return added
    try:
        import urllib.request
        body = json.dumps({"action": "save_schedule", "data": {**data, "items": list(by_id.values())}},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(SCHEDULE_GAS_URL, data=body,
                                     headers={"Content-Type": "text/plain"}, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            res = json.loads(r.read())
    except Exception as e:
        print(f"  [일정] 등록 실패({type(e).__name__}: {e}) — 아침 메시지는 그대로 나간다")
        return []
    if not (isinstance(res, dict) and res.get("ok")):
        print("  [일정] 등록 실패 — GAS 응답 오류")
        return []
    print(f"  → 전사일정 다리: {len(added)}건 등록 완료")
    return added


def _schedule_reply_lines(added: list[dict]) -> str:
    """등록한 일정을 방에 한 줄로 알린다. 틀렸을 때 되돌릴 길을 같이 준다 —
    말한 사람이 그 자리에서 아니라고 할 수 있어야 거짓 일정이 안 쌓인다."""
    if not added:
        return ""
    rows = []
    for it in added:
        try:
            d = datetime.strptime(it["next_due"], "%Y-%m-%d")
            when = f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})"
        except Exception:
            when = it.get("next_due", "")
        tm = str(it.get("time") or "").strip()
        rows.append("  · " + when + (f" {tm}" if tm else "") + " " + str(it.get("name") or "")
                    + (f" · {it['dept']}" if it.get("dept") else ""))
    return ("📅 전사일정에 넣었습니다\n" + "\n".join(rows) +
            "\n  (틀리면 한 줄만 주세요 — 바로 고칩니다)")


def main():
    parser = argparse.ArgumentParser(
        description="★운영부 카톡 대화 → AI 아침 요약 두뇌(v1) — 발송·txt 내보내기는 범위 밖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date", dest="date", default=None,
                        help="대상일 수동 지정(YYYY-MM-DD, 테스트·재실행용). 미지정 시 어제→최근 완결일 자동.")
    parser.add_argument("--room", dest="room", default=DEFAULT_ROOM,
                        help=f"카톡 방 제목(기본 '{DEFAULT_ROOM}') — 배536(2026-08-11), 예: '★ 중간관리자'")
    parser.add_argument("--room-key", dest="room_key", choices=sorted(ROOM_KEYS),
                        help="방 이름 ASCII 별칭(ops·mgr) — .bat 에서 부를 때 쓴다(한글 인자는 깨진다)")
    parser.add_argument("--bridge-dry-run", dest="bridge_dry_run", action="store_true",
                        help="업무 장부 다리를 실제로 등록하지 않고 무엇이 올라갈지만 보여준다")
    args = parser.parse_args()
    room = ROOM_KEYS[args.room_key] if args.room_key else args.room
    sys.exit(run(forced_date=args.date, room=room, bridge_dry_run=args.bridge_dry_run))


if __name__ == "__main__":
    main()
