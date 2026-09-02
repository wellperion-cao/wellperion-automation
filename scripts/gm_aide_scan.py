#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""06:30 GM 보좌 포착 스캔 (배237 · GM 보좌 자율화 체계 phase 1 · 구현②③).

관찰 원장 + 업무 큐 + GM 프로필을 읽어 'GM이 놓친 것·다음 할 것'을
**포착 이벤트**로 생성하고(②), 그 중 **비가역·게이트 건**을
status/_queue.json 에 '[GM보좌 제안]' PENDING 배로 자동등록한다(③, 가역 자율의 첫 실동작).

설계 정본:
  - 스펙 : .omc/specs/deep-interview-gm-aide-autonomy.md
          (②포착 범위 = 확정신호 + 지시함의, 예측형 제외 / ③가역=자율·비가역=제안)
  - 배   : status/_queue.json  CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237)

★ phase 1 경계 (절대 준수 · GM '가역 자율부터' 지시):
  - 포착·프로필·제안등록까지만. 실제 도메인 작업의 C-Level 위임 자율실행은 phase2(제외).
  - 라이브 파괴·비가역 동작 0: 발행·삭제·외부전송·GAS·시트 변경 절대 없음.
  - '제안 배 등록'은 가역(보류·삭제 가능)이므로 phase1 자율 OK. 등록까지가 끝.

안전장치:
  - 각 포착에 가역/비가역 분류. 비가역·게이트 포착만 제안 배로 등록.
  - read-before-write · ship_no=max+1 · dedup(aide_proposal_key) · 하루 과다등록 방지(cap {MAX_PROPOSALS_PER_RUN}).
  - 각 제안 배 note = 사유 + 'KPI→북극성 경로' 한 줄 필수(메모리 feedback_gm_decides_by_seeing_kpi_path 정합).

프로필 연동(2026-07-04 추가 · load_profile_missed_hints):
  - gm_aide_scan.bat 이 06:30 실행 시 먼저 gm_profile_builder.py 로 gm_profile.md 를 갱신(스펙 '①일일 갱신' 배선 —
    이전엔 프로필이 2026-07-02 이후 정체돼 있었음). 그 다음 이 스크립트가 갱신된 프로필의
    '## 자주 놓치는 것' 섹션을 읽어 제안 배 note 에 'GM프로필 근거' 한 줄로 인용한다(①→② 배선 연결).

06:30 스케줄 등록(이번엔 만들지 않음 — GM 확인 후):
  기존 northstar_recommender(06:30)와 충돌 없이 별도 스크립트. 같은 06:30에 붙이려면:
    launchers/gm_aide_scan.vbs(숨김런처) → scripts/gm_aide_scan.bat → python ... --commit
  를 만들어 Task Scheduler 'Wellperion-GM-Aide-Scan-0630' 에 등록.
  (.bat=영문전용·PYTHONIOENCODING=utf-8 / 참고: reference_powershell_scheduledtasks_limitation)

★ phase 2 = 가역 자율실행 레이어 (휴면 기본 · 이 파일에 추가):
  - phase1은 '제안'까지. phase2 = 가역 포착 건을 실제 처리(자율실행)하되 **안전경계 엄수**:
    ① 휴면 기본: GM_AIDE_AUTO_EXEC(기본 OFF·dry-run). OFF면 '무엇을 자율실행할지' 로그만(변경 0). 라이브(ON)=GM go 후.
    ② 가역만: 비가역(발행·삭제·외부전송·시트·결제·보안·금지·전략·공식값)은 절대 자율실행 X → phase1대로 제안배.
    ③ 크론-실행 가능한 가역 메타행위만: 정비 액션 5종(미러 동기·현황 재발행·KPI 재집계 등).
       도메인 실무(콘텐츠·GAS 변경 등)는 C-Level 세션 몫 → 여기서 실행 금지(제안/위임 대기로만).
    ④ ON 시 G1 기록 + 사후보고: ship.aide_auto_exec(원복 근거) + gm_observation_ledger.jsonl auto_exec 로그.
    ⑤ 웰리 직접실행 금지 원칙 유지: 스크립트는 '가역 메타행위'까지만, 도메인 실행은 담당 C-Level 경유.

사용법:
  python scripts/gm_aide_scan.py                 # 드라이런(기본) — 포착 콘솔 출력 + phase2 휴면(자율실행 예정만 표시)
  python scripts/gm_aide_scan.py --commit        # 제안 배 실제 등록(_queue.json 갱신) + 스캔 로그
  GM_AIDE_AUTO_EXEC=1 python scripts/gm_aide_scan.py   # phase2 라이브 발효(GM go 후에만) — 가역 메타행위 실제 적용
  python scripts/gm_aide_scan.py --auto-exec     # 로컬 시뮬(라이브 발효 강제 · 검증용)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 경로 상수 ──
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
LEDGER = STATUS_DIR / "gm_observation_ledger.jsonl"
QUEUE_ACTIVE = STATUS_DIR / "_queue.json"
QUEUE_ARCHIVE = STATUS_DIR / "_queue_archive.json"
PROFILE_MD = STATUS_DIR / "gm_profile.md"
MATRIX_FILE = ROOT / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
SCAN_LOG = STATUS_DIR / "gm_aide_scan_log.jsonl"

# ── 기한 위생 점검(배732 · 약속 L26⑤ · GM 확정 2026-08-21) ──
# "놓치는 것은 웰리가 찾아 알린다 — 전사일정 + 월간운영계획 + 결재 SSOT 세 곳을 이어서 보고,
#  기간(기한)은 항상 채워져 있어야 하며 ... 보고를 마치면 목록에서 내려간다."
# 결재 SSOT 다리는 scan_stale_approval(기존)이 이미 담당 — 여기선 나머지 두 다리(전사일정·월간운영계획)
# + 보고완료 미이관(회장님 목록 vs chairman_reported.json)까지 한 표로 묶는다.
MONTHLY_PLAN_FILE = STATUS_DIR / "monthly_ops_plan.json"
SCHEDULE_SSOT_FILE = STATUS_DIR / "schedule_ssot.json"
CHAIRMAN_ITEMS_JS = ROOT / "3. 웰페리온 가이드" / "coo" / "chairman" / "_chairman_items.js"
CHAIRMAN_REPORTED_JSON = ROOT / "3. 웰페리온 가이드" / "coo" / "chairman" / "chairman_reported.json"
# ★2026-09-02 실측으로 넓혔다. 종전 r"^[□✅]\s*\d+\)" 는 「□ 1) 내용」만 잡았는데,
#   원장의 체크 줄 561개 중 그 형식은 0개였다 — 사람은 「□ 내용」·「□ 1️⃣ 내용」으로 쓴다.
#   그래서 9월 GM업무 체크 항목이 기한 경보에서 통째로 빠져 있었다(GM 지시로 5단 루프 착수 중 발견).
#   사람에게 형식을 맞추라고 하는 대신 기계가 사람 글을 읽게 한다(안내문 아니라 코드로 · 약속 L02).
# ★★2026-09-02 두 번째 수정 — 완료 표시 ☑(U+2611)를 빠뜨리고 있었다.
#   GM업무 화면은 □(U+25A1)/☑(U+2611) 두 글자만 체크 줄로 읽고, GM 이 화면에서 체크하면
#   원장에도 ☑ 로 남는다. 그런데 이 정규식에 ☑ 가 없어서 **이미 끝낸 줄을 아예 못 세고 있었다**
#   — "체크 178줄 중 닫힌 게 0개"라는 오판이 여기서 나왔다(GM 지적 2026-09-02).
#   ✅ 는 사람이 손으로 적을 수 있어 함께 읽되, 원장에 새로 쓸 때는 ☑ 를 쓴다(화면이 못 읽는다).
CHECKLIST_ITEM = re.compile(r"^[□☑✅⬜]\s*\S")
# 끝난 줄 판정 — 이 글자로 시작하면 완료다(정본 = GM업무 화면 extractTodos 의 U+2611).
CHECK_DONE_MARKS = ("☑", "✅")
# 체크 줄 끝의 담당 태그 — 「[담당: 이경연 실장 (회신 9/5)]」. 없으면 담당 미정이다(빈 태그를 미리 붙이지 않는다).
OWNER_MARK = re.compile(r"\[담당:\s*([^\]]+?)\s*\]")
DUE_MARK = re.compile(r"\(~\s*(\d{1,2})/(\d{1,2})\s*\)")  # 체크 항목 완료예정일 표기(GM 확정 2026-08-24) — "(~9/5)" "(~09/05)"

LONG_PENDING_DAYS = 30

# ── 결재 장기 무처리 규칙(배69 · GM 07-24 지시 — 58일 적체 5건 재발 차단) ──
# 임계값 근거(2026-07-24 실측): 결재완료 17건의 생성→완료 소요일 중앙값 2일 · 대부분 6일 내 종결,
#   가장 느린 정상 케이스가 13~14일(2건) · 그 다음은 52일 이상치 1건뿐. 14일 = "느리지만 정상"과
#   "방치"의 실측 경계값. 7일로 잡으면 정상 지연건까지 섞여 벽이 되고, 30일은 첫 적발까지 너무 늦다.
STALE_APPROVAL_DAYS = 14
SSOT_TODO_URL = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
MAX_PROPOSALS_PER_RUN = 5      # 하루 과다등록 방지 cap
PROPOSAL_TAG = "[GM보좌 제안]"

# ── phase2 가역 자율실행 레이어 스위치 (휴면 기본) ──
# 기본 OFF(dry-run). ON 은 GM go 후에만(feedback_security_live_activation_needs_gm_go).
# 라이브 발효 = 환경변수 GM_AIDE_AUTO_EXEC=1 (또는 --auto-exec 로컬 시뮬).
AUTO_EXEC_ENV = "GM_AIDE_AUTO_EXEC"
AUTO_EXEC_ON_VALUES = {"1", "true", "on", "yes"}
MAX_AUTO_ACTIONS_PER_RUN = 5   # 가역 자율실행 폭주 방지 cap

# ── 자율 틈 감지기(배237(b)) 재개가능 auto 전용 게이트 (독립·기본 OFF) ──
# ★반반 구성(GM 결정 2026-07-08): 이 게이트는 '재개가능'(resumable) auto 레인만 제어.
#   '정체'(stalled)는 surface-only(자율 write 0) → 어떤 게이트로도 실행 안 됨. .bat 에는 이 게이트만 추가.
# ★안전: 기존 GM_AIDE_AUTO_EXEC 와 절대 공유 금지 — 별도 env 별도 체크(라이브 발효=별도 GM go).
RESUMABLE_APPLY_ENV = "AIDE_RESUMABLE_APPLY"

# ── 자동 검증-완결 핸들러 게이트 (독립·기본 OFF · 자율 실행 루프 첫 닫힘) ──
# ★재개가능 auto 레인 처리 뒤에서만 동작. OFF=드라이런(무엇을 닫을지 로그만·_queue 델타 0).
#   ON(=AIDE_VERIFY_APPLY=1)+PASS 일 때만 라이브 완결. FAIL·불명은 절대 완결 안 함(거짓완료 0).
#   ★안전: 기존 게이트들과 절대 공유 금지 — 별도 env 별도 체크(라이브 발효=별도 GM go).
VERIFY_APPLY_ENV = "AIDE_VERIFY_APPLY"

# ── 정비 액션 5종(2026-07-04 추가) 조건 임계값 — 전부 '실제 문제 있을 때만' 게이트 ──
STALE_HOURS_ERP = 6   # erp_status.json generated_at 이 이만큼 지나면 재발행 대상
STALE_HOURS_KPI = 6   # kpi_values.json generated_at 이 이만큼 지나면 재집계 대상
WORKTREES_DIR = ROOT / ".claude" / "worktrees"

ROLE_NICK = {
    "ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
    "coo": "시우", "cpo": "시포", "cto": "시토", "cbo": "시보",
}

TODAY = datetime.now().date()

# ── 자율 틈 감지기 모듈(배237(b)) — scripts/aide_detectors/ ──
sys.path.insert(0, str(ROOT / "scripts" / "aide_detectors"))
import stall_watch      # type: ignore  # noqa: E402
import reversibility    # type: ignore  # noqa: E402
import auto_actions     # type: ignore  # noqa: E402
import verify_complete  # type: ignore  # noqa: E402

try:  # 크로스프로세스 _queue.json 락 (P2, 2026-07-10) — 같은 scripts/ 디렉토리
    import queue_lock
except Exception:
    queue_lock = None
from contextlib import nullcontext  # noqa: E402


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ═══════════════════════════════════════════
#  입력 로드
# ═══════════════════════════════════════════
def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def load_northstar_map() -> dict:
    """역할별 북극성(matrix dims[0]) — KPI→북극성 경로 한 줄 조립용."""
    m = read_json(MATRIX_FILE, {"roles": []})
    out = {}
    for r in m.get("roles", []):
        dims = r.get("dims", []) if isinstance(r, dict) else []
        out[r.get("id")] = (dims[0] if dims else "").strip()
    return out


def load_profile_missed_hints(limit: int = 3) -> list:
    """gm_profile.md '## 자주 놓치는 것' 섹션 불릿을 포착 근거로 연동(①관찰·학습 → ②포착 배선).
    프로필 없거나 섹션 없으면 빈 리스트(휴먼: profile builder 미실행 시에도 스캔은 무중단)."""
    if not PROFILE_MD.exists():
        return []
    try:
        text = PROFILE_MD.read_text(encoding="utf-8")
    except Exception:
        return []
    m = re.search(r"## 자주 놓치는 것\s*\n(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return []
    hints = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("-"):
            hints.append(line.lstrip("- ").strip())
    return hints[:limit]


# ═══════════════════════════════════════════
#  포착 이벤트 생성 (②)
# ═══════════════════════════════════════════
def _ship_id(item: dict) -> str:
    return item.get("task_id") or item.get("id") or "unknown"


def make_capture(ctype, reversibility, target_role, title, reason, evidence, remedy,
                 dedup_key, source_item=None):
    """포착 이벤트 1건. reversibility = '가역' | '비가역'."""
    return {
        "captured_at": now_str(),
        "type": ctype,                 # long_pending / unapproved_recommendation / routine_missing
        "reversibility": reversibility,
        "target_role": target_role,
        "title": title,
        "reason": reason,
        "evidence": evidence,
        "remedy": remedy,              # 함의된 조치(가역=리마인드/촉구 / 비가역=GM 결정 필요)
        "dedup_key": dedup_key,
        "source_task_id": _ship_id(source_item) if source_item else "",
    }


#  ★정박 선언 = ⚓ (약속 L16 아이콘 표준 · '대기/정박'). next 가 이 표식으로 시작하면
#  담당이 **의도적으로 세워 둔 배**다(재개조건이 붙어 있다). 그런 배까지 매일 '장기 미착수'로
#  다시 잡으면 자율 스캔이 헛돈다 — 2026-07-29 실측: 최근 5회 포착이 전부 같은 2건
#  (배101 AWS 9월 대기 · 배21 그 후속)이었고 자율 처리는 0건이었다. 포착은 매일 2건인데
#  아무 일도 안 일어나니 자율현황 화면엔 '포착 2 · 처리 0'만 반복됐다.
#  ▸낱말로 판정하지 않는다(설명글에 '대기'가 들어갔다고 걸면 오탐 — 같은 뿌리의 실패가
#    자율 착수 선별기에서 이미 있었다). 사람이 일부러 붙이는 **표식 하나**만 본다.
#  ▸숨기지 않는다: 건너뛴 수는 parked_skipped 로 로그에 남겨 '몇 척이 정박 중인지' 보이게 한다.
_PARKED = re.compile(r"^[\s·]*⚓")


def _is_parked(item: dict) -> bool:
    return bool(_PARKED.match(str(item.get("next") or "")))


def scan_long_pending(active: list, parked_out: list | None = None) -> list:
    """PENDING 장기 대기 = 우선순위 재확인 또는 폐기 판단 필요. 폐기=삭제(비가역)·GM 결정 → 게이트 제안.
    ★next 가 ⚓ 로 시작하는 배(정박 선언)는 건너뛴다 — 담당이 재개조건을 적어 세워 둔 것이라
    매일 다시 잡을 이유가 없다. 건너뛴 배 id 는 parked_out 에 담아 로그에 남긴다."""
    caps = []
    for x in active:
        if x.get("status") != "PENDING":
            continue
        if _is_parked(x):
            if parked_out is not None:
                parked_out.append(_ship_id(x))
            continue
        enq = x.get("enqueued_at")
        if not enq:
            continue
        try:
            d = datetime.strptime(enq, "%Y-%m-%d").date()
        except ValueError:
            continue
        age = (TODAY - d).days
        if age < LONG_PENDING_DAYS:
            continue
        tid = _ship_id(x)
        role = (x.get("clevel") or "ceo").lower()
        caps.append(make_capture(
            ctype="long_pending",
            reversibility="비가역",   # 폐기(삭제)·우선순위 재확정 = GM 결정 게이트 → 제안 배
            target_role=role,
            title=f"[{tid}] {age}일째 PENDING 장기 미착수",
            reason=f"{age}일 대기 — 우선순위 재확인 또는 폐기(삭제) 판단 필요(GM 결정 게이트)",
            evidence=f"enqueued_at={enq} priority={x.get('priority')} title={(x.get('title') or '')[:50]}",
            remedy="GM 결정 필요(착수/우선순위 하향/폐기) — 비가역(폐기) 포함 → 제안만",
            dedup_key=f"gmaide|long_pending|{tid}",
            source_item=x,
        ))
    return caps


def fetch_todo_list_readonly() -> list:
    """업무&결재 SSOT(ERP S3) 원본 읽기 전용 GET(action=todo_list). 쓰기 호출 없음.
    실패(네트워크·타임아웃·파싱 오류)해도 예외를 밖으로 던지지 않고 빈 리스트 반환 —
    이 스캔이 06:30 예약 전체를 죽이면 안 된다(기존 함수들의 방어적 실패 패턴과 동일)."""
    try:
        req = urllib.request.Request(
            SSOT_TODO_URL + "?action=todo_list",
            headers={"User-Agent": "gm_aide_scan/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = data.get("data") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []
    except Exception as e:
        print(f"  [WARN] 업무&결재 SSOT 읽기 실패(스킵·스캔은 계속): {e}")
        return []


def scan_stale_approval(todo_rows: list) -> list:
    """결재요청 후 STALE_APPROVAL_DAYS일 이상 무처리(결재상태=대기)인 건 포착(배69 · GM 07-24).
    ★오탐 방지: 결재선을 탄 건만(결재요청 비어있는 순수 업무기록 제외) · 결재상태가 정확히
    '대기'인 것만(결재완료·GM반려 등 종결건은 절대 재부상 안 함) · 생성일 파싱 실패는 스킵(정직)."""
    caps = []
    for r in todo_rows or []:
        appr_req = (r.get("결재요청") or "").strip()
        if not appr_req:
            continue  # 결재선 없는 순수 업무기록 — 대상 아님(오탐 방지)
        if (r.get("결재상태") or "").strip() != "대기":
            continue  # 완료·반려 등 종결건은 재부상 금지
        created = _parse_date_loose(r.get("생성일"))
        if created is None:
            continue
        age = (TODAY - created).days
        if age < STALE_APPROVAL_DAYS:
            continue
        tid = r.get("id") or "unknown"
        title = (r.get("업무명") or "").strip()
        owner = (r.get("담당자") or "").strip()
        caps.append(make_capture(
            ctype="stale_approval",
            reversibility="비가역",   # 승인/반려 = GM 결정 게이트 → 제안 배(기존 long_pending과 동일 경로)
            target_role="ceo",        # 결재요청 대상이 실무 C-Level이 아니라 GM 본인이라 웰리가 대신 표면화
            title=f"[{tid}] 결재 {age}일째 무처리 — {title[:35]}",
            reason=f"결재요청({appr_req}) 후 {age}일째 미처리(결재상태=대기) — 정상 승인 소요(중앙값 2일·최대 14일) 대비 장기 방치",
            evidence=f"생성일={r.get('생성일')} 결재요청={appr_req} 담당자={owner} 업무명={title[:60]}",
            remedy="GM 결정 필요(승인/반려) — 방치될수록 맥락 소실(58일 적체 실측 사례)",
            dedup_key=f"gmaide|stale_approval|{tid}",
        ))
    return caps


def _parse_date_loose(s) -> "datetime.date | None":
    """'YYYY-MM-DD' 또는 'YYYY-MM-DDTHH:MM:SSZ' 형태를 느슨하게 date로 파싱. 실패 시 None(정직 미상)."""
    if not s:
        return None
    s = str(s).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def scan_due_hygiene() -> list:
    """기한 위생 점검(배732 · 약속 L26⑤). 전사일정(schedule_ssot)·월간운영계획(monthly_ops_plan)·
    회장님 보고 목록 3곳을 읽어 ①기한없음 ②기한넘김 ③체크리스트100%인데 미이관 ④전사일정 담당빈칸
    ⑤보고완료인데 목록에 남음 ⑥체크 항목에 완료예정일(~M/D) 표기 없음 ⑦표기된 완료예정일이 지남
    — 7종을 찾는다. 항목마다 배를 만들면 board 가 넘친다(long_pending과 같은 함정) → 하루 1건짜리
    표 한 장(캡처 1건)으로 묶는다. 지어낸 기한·담당 없음 — 원본 필드만 그대로."""
    rows = []  # (구분, 항목, 담당, 사유)

    plan = read_json(MONTHLY_PLAN_FILE, {})
    months = plan.get("months", {}) if isinstance(plan, dict) else {}
    cur = months.get(TODAY.strftime("%Y-%m"), {})
    for o in cur.get("objectives", []):
        if o.get("status") in ("진행", "계획") and not (o.get("due") or "").strip():
            rows.append(("①기한없음", f"[{o.get('id')}] {(o.get('title') or '')[:30]}",
                         o.get("owner") or "", "월간운영계획 due 미기재"))

    all_objs = [o for m in months.values() for o in m.get("objectives", [])]
    cur_ids = {o.get("id") for o in cur.get("objectives", [])}
    for o in all_objs:
        due = _parse_date_loose(o.get("due"))
        if due and due < TODAY and o.get("status") != "완료":
            rows.append(("②기한넘김", f"[{o.get('id')}] {(o.get('title') or '')[:30]}",
                         o.get("owner") or "", f"due={o.get('due')} 경과(status={o.get('status')})"))
        if o.get("status") == "완료":
            continue
        items = [l.strip() for l in (o.get("progress_note") or "").splitlines() if CHECKLIST_ITEM.match(l.strip())]
        # 체크 줄 판정(⑥⑦⑧)은 **이번 달 목표만** 본다. 지난달 카드까지 훑으면 아침 표가
        # 수백 줄로 불어 아무도 안 읽는다(GM: 줄이 아니라 건수를 줄여라).
        if o.get("id") not in cur_ids:
            continue
        if len(items) >= 2 and all(l.startswith(CHECK_DONE_MARKS) for l in items):
            rows.append(("③체크리스트100%", f"[{o.get('id')}] {(o.get('title') or '')[:30]}",
                         o.get("owner") or "", "전항 완료·완료건 정리로 이관 안 됨"))
        for l in items:
            if l.startswith(CHECK_DONE_MARKS):
                continue  # 끝난 항목엔 예정일을 요구 안 함
            m = DUE_MARK.search(l)
            if not m:
                rows.append(("⑥완료예정일없음", f"[{o.get('id')}] {l[:40]}",
                             o.get("owner") or "", "체크 항목에 (~M/D) 표기 없음"))
                continue
            try:
                due_date = datetime(TODAY.year, int(m.group(1)), int(m.group(2))).date()
            except ValueError:
                continue  # 잘못된 날짜 표기 — 지어내지 않고 판정 보류
            if due_date < TODAY:
                rows.append(("⑦완료예정일지남", f"[{o.get('id')}] {l[:40]}",
                             o.get("owner") or "", f"due=~{m.group(1)}/{m.group(2)} 경과"))
        # ⑧ 담당 없음 — GM 이 직접 관장하는 건의 체크 항목에 담당이 안 붙어 있으면,
        #    중간관리자 방으로 "누가 맡을지"를 물어야 한다(GM 확정 2026-09-02 · 5단 루프 1단계).
        #    웰리가 담당을 지어 배정하지 않는다 — 실장·소장·나우열M 이 나눈다.
        if "(GM 직접)" in (o.get("title") or ""):
            for l in items:
                if l.startswith(CHECK_DONE_MARKS) or OWNER_MARK.search(l):
                    continue
                rows.append(("⑧담당없음", f"[{o.get('id')}] {l[:40]}",
                             o.get("owner") or "", "체크 항목에 [담당: …] 표기 없음"))

    sched = read_json(SCHEDULE_SSOT_FILE, {})
    for it in (sched.get("items") or []):
        if not (it.get("assignee") or "").strip():
            rows.append(("④전사일정담당빈칸", f"[{it.get('id')}] {(it.get('name') or '')[:30]}",
                         it.get("dept") or "", "assignee 미기재"))

    reported = read_json(CHAIRMAN_REPORTED_JSON, {})
    try:
        listed_ids = re.findall(r'id:\s*"(d\d+)"', CHAIRMAN_ITEMS_JS.read_text(encoding="utf-8"))
    except Exception:
        listed_ids = []
    for i in listed_ids:
        if i in reported:
            rows.append(("⑤보고완료미이관", f"[{i}]", "회장님보고목록",
                         f"chairman_reported.json {reported.get(i)} 보고완료 찍혔는데 목록에 남음"))

    if not rows:
        return []

    counts = {}
    for r in rows:
        counts[r[0]] = counts.get(r[0], 0) + 1
    summary = " · ".join(f"{k} {v}건" for k, v in sorted(counts.items()))
    table = "| 구분 | 항목 | 담당 | 사유 |\n|---|---|---|---|\n" + "\n".join(
        f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows[:40])
    if len(rows) > 40:
        table += f"\n(외 {len(rows) - 40}건 더 — 스캔로그 참고)"

    cap = make_capture(
        ctype="due_hygiene",
        reversibility="비가역",
        target_role="ceo",
        title=f"⏰ 기한 빈칸·넘김 — {summary}",
        reason=f"약속 L26⑤ 기한 위생 점검 — {summary}",
        evidence=table,
        remedy="각 항목 기한 채우기/완료 이관/담당 지정/보고목록 정리 — GM 결정 필요",
        dedup_key="gmaide|due_hygiene|daily",
    )
    cap["counts"] = counts  # hangro_board._due_hygiene_alert 가 판정 재구현 없이 그대로 씀(약속 L01)
    return [cap]


# ═══════════════════════════════════════════
#  KPI → 북극성 경로 한 줄 (제안 배 note 필수)
# ═══════════════════════════════════════════
def build_kpi_path(role: str, kpi: dict, ns_map: dict) -> str:
    ns = ns_map.get(role, "").strip()
    ns_short = (ns.splitlines()[0] if ns else "")[:60] or "(북극성 미정)"
    kv = kpi.get("roles", {}).get(role, {}) if isinstance(kpi, dict) else {}
    kv_str = ", ".join(f"{k}={v}" for k, v in kv.items() if not str(k).startswith("_")) or "집계없음"
    nick = ROLE_NICK.get(role, role.upper())
    return f"KPI→북극성: [{role}·{nick}] 현재 KPI({kv_str}) → 북극성 '{ns_short}' 로 잇는 결정 게이트"


# ═══════════════════════════════════════════
#  제안 배 등록 (③ · 비가역·게이트 포착만)
# ═══════════════════════════════════════════
def existing_proposal_keys(active: list) -> set:
    keys = set()
    for x in active:
        k = x.get("aide_proposal_key")
        if k:
            keys.add(k)
    return keys


def make_proposal_ship(cap: dict, ship_no: int, kpi: dict, ns_map: dict, profile_hints: list | None = None) -> dict:
    role = cap.get("target_role", "ceo")
    kpi_path = build_kpi_path(role, kpi, ns_map)
    ctype = cap["type"].upper().replace("_", "-")
    tid = f"AIDE-{today_str()}-{ctype}-{ship_no}"
    profile_ref = (
        f" GM프로필 근거(자주 놓치는 것): {profile_hints[0]}"
        if profile_hints else ""
    )
    note = (
        f"[{today_str()} GM보좌 제안·웰리 포착] {cap['reason']} "
        f"(포착유형={cap['type']} · 가역성={cap['reversibility']} · 근거={cap['evidence']}). "
        f"조치안: {cap['remedy']}. {kpi_path}.{profile_ref} "
        f"※ phase1=제안(대기)까지만 — 실제 도메인 작업은 GM 결정 후."
    )
    return {
        "task_id": tid,
        "clevel": role,
        "title": f"{PROPOSAL_TAG} {cap['title']}",
        "status": "PENDING",
        "priority": "⛵돛단배",
        "enqueued_at": today_str(),
        "ship_no": ship_no,
        "note": note,
        "next": "",
        "depends_on": "",
        "source": "gm_aide_scan",
        "reversibility": cap["reversibility"],
        "aide_proposal_key": cap["dedup_key"],
    }


def max_ship_no(active: list, archive: list) -> int:
    nums = [x.get("ship_no") for x in (active + archive) if isinstance(x.get("ship_no"), int)]
    return max(nums) if nums else 0


def log_scan(event: str, **fields) -> None:
    rec = {"event": event, "logged_at": now_str(), **fields}
    try:
        with open(SCAN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 스캔 로그 기록 실패: {e}")


# ═══════════════════════════════════════════
#  phase2 · 가역 자율실행 레이어 (휴면 기본)
# ═══════════════════════════════════════════
#  ★경계: 가역(phase1 분류) 포착만 · 크론-실행 가능한 안전 '메타행위'만.
#  도메인 실무(콘텐츠 제작·GAS 변경 등)는 담당 C-Level 세션 몫 → 여기서 실행 금지.
#  지원 액션:
#   - 정비 액션 5종(2026-07-04 추가 · plan_maintenance_actions) — 전부 조건부(실제
#     문제 있을 때만 등재 · 억지 발동 금지) · 가역 · 기존 스크립트 재사용:
#       mirror_sync                — 라이브↔미러 드리프트 시 sync_queue_mirror.py 재동기
#       stale_republish            — 현황 오래됨/죽은작업 잔존 시 erp_status_publisher.py 재발행
#       kpi_refresh                — KPI 오래됨 시 kpi_collector.py(+northstar_reach.py) 재집계
#       dead_artifact_prune        — clean·비활성·비메인 워크트리만 git worktree remove(+prune)
#       sunday_context_maintenance — 일요일 한정, context_budget_report.py 금주분 미갱신 시 재측정
def auto_exec_enabled(cli_flag: bool = False) -> bool:
    """라이브 발효 여부. --auto-exec(로컬 시뮬) 또는 GM_AIDE_AUTO_EXEC=1 일 때만 ON."""
    if cli_flag:
        return True
    return os.environ.get(AUTO_EXEC_ENV, "").strip().lower() in AUTO_EXEC_ON_VALUES


# ── 정비 액션 5종 · 탐지(detector) — 전부 '실제 문제 있을 때만' 조건부(억지 발동 금지) ──
def _detect_mirror_sync() -> list:
    """라이브↔미러 드리프트 감지(sync_queue_mirror.SYNC_PAIRS 그대로 재사용).
    드리프트 없으면 빈 리스트(정직 skip)."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import sync_queue_mirror as sq  # type: ignore
    except Exception:
        return []
    drifted = []
    for src_rel, dst_rel in sq.SYNC_PAIRS:
        src_bytes = sq.read_bytes(str(ROOT / src_rel))
        if src_bytes is None:
            continue  # 원본 없음 → 대상 아님
        dst_bytes = sq.read_bytes(str(ROOT / Path(*dst_rel.split("/"))))
        if src_bytes != dst_bytes:
            drifted.append(dst_rel)
    if not drifted:
        return []
    return [{
        "action_type": "mirror_sync",
        "target_task_id": "mirror_sync",
        "reversibility": "가역",
        "desc": f"라이브↔미러 드리프트 감지({len(drifted)}건: {', '.join(drifted)}) → sync_queue_mirror.py 재동기",
        "dedup_key": "gmaide_autoexec|mirror_sync|mirror_sync",
        "drifted": drifted,
    }]


def _detect_stale_republish() -> list:
    """erp_status.json 오래됨(>{STALE_HOURS_ERP}h) 또는 automation_health 에
    Task Scheduler 실측에 이미 없는 죽은 작업명 존재 시 재발행 대상."""
    data = read_json(STATUS_DIR / "erp_status.json", {})
    reasons = []
    gen_at = data.get("generated_at")
    if gen_at:
        try:
            gen_dt = datetime.strptime(gen_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
            if age_hours > STALE_HOURS_ERP:
                reasons.append(f"generated_at {age_hours:.1f}h 경과(>{STALE_HOURS_ERP}h)")
        except Exception:
            pass
    dead = []
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import erp_status_publisher as esp  # type: ignore
        live_names = {i.get("name") for i in esp.collect_automation_health().get("items", [])}
        recorded_names = {i.get("name") for i in (data.get("automation_health") or {}).get("items", [])}
        dead = sorted(n for n in (recorded_names - live_names) if n)
        if dead:
            reasons.append(f"죽은작업 잔존: {', '.join(dead)}")
    except Exception:
        pass
    if not reasons:
        return []
    return [{
        "action_type": "stale_republish",
        "target_task_id": "erp_status",
        "reversibility": "가역",
        "desc": f"erp_status.json 재발행 필요({' / '.join(reasons)}) → erp_status_publisher.py 재실행",
        "dedup_key": "gmaide_autoexec|stale_republish|erp_status",
        "reasons": reasons,
    }]


def _detect_kpi_refresh() -> list:
    """kpi_values.json 오래됨(>{STALE_HOURS_KPI}h) 시 재집계 대상."""
    data = read_json(STATUS_DIR / "kpi_values.json", {})
    gen_at = data.get("generated_at")
    if not gen_at:
        return []
    try:
        gen_dt = datetime.strptime(gen_at, "%Y-%m-%dT%H:%M:%S%z")
        age_hours = (datetime.now(timezone.utc) - gen_dt.astimezone(timezone.utc)).total_seconds() / 3600
    except Exception:
        return []
    if age_hours <= STALE_HOURS_KPI:
        return []
    return [{
        "action_type": "kpi_refresh",
        "target_task_id": "kpi_values",
        "reversibility": "가역",
        "desc": f"KPI 측정치 {age_hours:.1f}h 경과(>{STALE_HOURS_KPI}h) → kpi_collector.py 재실행",
        "dedup_key": "gmaide_autoexec|kpi_refresh|kpi_values",
        "age_hours": age_hours,
    }]


def _git_worktree_list_porcelain() -> list:
    """`git worktree list --porcelain` 파싱 → [{"path":, "locked": bool}, ...] (메인 포함)."""
    try:
        r = subprocess.run(["git", "worktree", "list", "--porcelain"],
                            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if r.returncode != 0:
            return []
    except Exception:
        return []
    entries, cur = [], {}
    for line in r.stdout.splitlines():
        if not line.strip():
            if cur:
                entries.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            if cur:
                entries.append(cur)
            cur = {"path": line[len("worktree "):].strip(), "locked": False}
        elif line.startswith("locked"):
            cur["locked"] = True
    if cur:
        entries.append(cur)
    return entries


def _detect_dead_artifact_prune() -> list:
    """죽은 워크트리(clean·비활성잠금·비메인·.claude/worktrees 하위)만 정리 대상.
    dirty·잠금·메인은 절대 제외(안전 우선 · reference_prune_dead_subagent_worktrees 준수)."""
    entries = _git_worktree_list_porcelain()
    if not entries:
        return []
    root_resolved = str(ROOT.resolve()).replace("\\", "/")
    scope_resolved = str(WORKTREES_DIR.resolve()).replace("\\", "/")
    candidates = []
    for e in entries:
        p = e.get("path", "")
        if not p:
            continue
        try:
            p_resolved = str(Path(p).resolve()).replace("\\", "/")
        except Exception:
            continue
        if p_resolved == root_resolved:
            continue  # 메인 워킹트리 절대 제외
        if not p_resolved.startswith(scope_resolved):
            continue  # .claude/worktrees 하위만 대상(안전 스코프)
        if e.get("locked"):
            continue  # 활성 잠금 제외
        try:
            st = subprocess.run(["git", "-C", p, "status", "--porcelain"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        except Exception:
            continue
        if st.returncode != 0 or st.stdout.strip():
            continue  # 조회 실패/dirty(미커밋 있음) 제외
        candidates.append(p)
    if not candidates:
        return []
    return [{
        "action_type": "dead_artifact_prune",
        "target_task_id": p,
        "reversibility": "가역",
        "desc": f"죽은 워크트리(clean·비활성) 정리: {p}",
        "dedup_key": f"gmaide_autoexec|dead_artifact_prune|{p}",
    } for p in candidates]


def _detect_sunday_context_maintenance() -> list:
    """일요일 한정. context_budget_report.py(기존 · 읽기전용 측정 스크립트) 금주분
    미갱신 시만 재측정 대상. 일요일 아니면 억지로 만들지 않음(정직 skip)."""
    if TODAY.weekday() != 6:  # 월=0 … 일=6
        return []
    script = ROOT / "scripts" / "context_budget_report.py"
    if not script.exists():
        return []
    out = STATUS_DIR / "context_budget.json"
    stale = True
    if out.exists():
        try:
            stale = datetime.fromtimestamp(out.stat().st_mtime).date() != TODAY
        except Exception:
            stale = True
    if not stale:
        return []
    return [{
        "action_type": "sunday_context_maintenance",
        "target_task_id": "context_budget",
        "reversibility": "가역",
        "desc": "일요일 컨텍스트 정비 — context_budget_report.py 금주분 미갱신 → 재측정",
        "dedup_key": "gmaide_autoexec|sunday_context_maintenance|context_budget",
    }]


def plan_maintenance_actions() -> list:
    """가역 정비 액션 5종 탐지 레이어(2026-07-04 추가). 각 액션 = 실제 조건 충족 시만
    등재(억지 발동 금지) · 하나 실패해도 나머지 탐지는 계속(개별 try/except)."""
    actions = []
    for detect_fn in (
        _detect_mirror_sync,
        _detect_stale_republish,
        _detect_kpi_refresh,
        _detect_dead_artifact_prune,
        _detect_sunday_context_maintenance,
    ):
        try:
            actions += detect_fn()
        except Exception as e:
            print(f"  [WARN] 정비 액션 탐지 실패({detect_fn.__name__}): {e}")
    return actions


def build_auto_actions(rev_caps: list, active: list) -> list:
    """가역 포착 → 크론-실행 가능한 가역 메타행위 목록.
    = 정비 액션 5종(plan_maintenance_actions)."""
    return plan_maintenance_actions()


def log_auto_exec(action_type: str, target: str, before: str, after: str,
                   restore_hint: str | None = None) -> None:
    """자율실행 사후로그 — 관찰 원장에 auto_exec 신호 + 원상복구 근거.
    before/after 일반 표기(restore_hint 로 원복법 명시)."""
    summary = f"[{target}] 가역 자율실행: {action_type} — {after}"
    evidence = f"before={before!r} after={after!r}"
    pattern_hint = restore_hint or "가역 메타행위 자율실행 — 원복 가능"
    rec = {
        "observed_at": now_str(),
        "source": "gm_aide_auto_exec",
        "signal_type": "auto_exec",
        "summary": summary,
        "evidence": evidence,
        "pattern_hint": pattern_hint,
        "reversibility": "가역",
        "dedup_key": f"gmaide_autoexec|{action_type}|{target}",
    }
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] auto_exec 원장 기록 실패: {e}")


# ── 정비 액션 5종 · 적용(executor) — 라이브(ON) 전용, 전부 기존 스크립트 재사용·가역 ──
def _apply_mirror_sync(a: dict) -> bool:
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_queue_mirror as sq  # type: ignore
    before = f"드리프트 {len(a['drifted'])}건: {', '.join(a['drifted'])}"
    sq.main()  # 단방향 동기화(멱등) — 원본 무변경, 미러만 갱신(+git add, 커밋은 안 함)
    log_auto_exec(a["action_type"], a["target_task_id"], before, "미러 재동기 완료(원본 무변경)",
                  restore_hint="원복=미러 파일을 이전 git 커밋 상태로 되돌리면 됨(원본=SSOT는 항상 그대로)")
    return True


def _apply_stale_republish(a: dict) -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "erp_status_publisher.py")],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"erp_status_publisher 실패: {(r.stderr or '')[:200]}")
    log_auto_exec(a["action_type"], a["target_task_id"], " / ".join(a["reasons"]),
                  "재발행 완료(erp_status_publisher.py 재실행)",
                  restore_hint="원복=이전 erp_status.json git 커밋 상태로 되돌리면 됨(순수 재생성 산출물)")
    return True


def _apply_kpi_refresh(a: dict) -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "kpi_collector.py")],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    if r.returncode != 0:
        raise RuntimeError(f"kpi_collector 실패: {(r.stderr or '')[:200]}")
    log_auto_exec(a["action_type"], a["target_task_id"], f"{a['age_hours']:.1f}h 경과",
                  "갱신 완료(kpi_collector.py+northstar_reach.py 재실행)",
                  restore_hint="원복=이전 kpi_values.json git 커밋 상태로 되돌리면 됨(순수 재집계 산출물)")
    return True


def _apply_dead_artifact_prune(a: dict) -> bool:
    p = a["target_task_id"]
    st = subprocess.run(["git", "-C", p, "status", "--porcelain"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    if st.returncode != 0 or st.stdout.strip():
        return False  # 재확인(동시성) — 사이 dirty 됐으면 skip(안전)
    r = subprocess.run(["git", "worktree", "remove", p],
                        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"worktree remove 실패({p}): {(r.stderr or '')[:200]}")
    subprocess.run(["git", "worktree", "prune"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    log_auto_exec(a["action_type"], p, "clean 워크트리 존재", "제거 완료(git worktree remove + prune)",
                  restore_hint="손실 없음(clean=미커밋 변경 0) — 재필요시 EnterWorktree로 재생성")
    return True


def _apply_sunday_context_maintenance(a: dict) -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "context_budget_report.py")],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"context_budget_report 실패: {(r.stderr or '')[:200]}")
    log_auto_exec(a["action_type"], a["target_task_id"], "금주 미갱신",
                  "측정 갱신 완료(context_budget_report.py 재실행 · 읽기전용 측정)",
                  restore_hint="원복 불요(순수 측정 산출물 · 삭제 판단은 사람 확인 몫)")
    return True


_MAINTENANCE_APPLIERS = {
    "mirror_sync": _apply_mirror_sync,
    "stale_republish": _apply_stale_republish,
    "kpi_refresh": _apply_kpi_refresh,
    "dead_artifact_prune": _apply_dead_artifact_prune,
    "sunday_context_maintenance": _apply_sunday_context_maintenance,
}


def apply_auto_actions(actions: list, archive: list) -> int:
    """라이브(ON) 전용: read-before-write 재로드 후 가역 메타행위 적용 + 사후로그.
    각 액션 실행은 독립 try/except — 하나 실패해도 나머지는 계속 진행.
    정비 액션 5종은 각자 자기 산출물 파일만 건드리는 독립 실행(기존 스크립트 재사용)."""
    if not actions:
        return 0
    applied = 0
    fresh_queue = None
    queue_dirty = False
    with (queue_lock.queue_lock("gm-aide") if queue_lock else nullcontext()):
        for a in actions[:MAX_AUTO_ACTIONS_PER_RUN]:
            atype = a.get("action_type")
            try:
                applier = _MAINTENANCE_APPLIERS.get(atype)
                ok = applier(a) if applier else False
            except Exception as e:
                print(f"  [WARN] 자율실행 실패({atype}·{a.get('target_task_id', '')}): {e}")
                ok = False
            if ok:
                applied += 1
        if queue_dirty and fresh_queue is not None:
            QUEUE_ACTIVE.write_text(json.dumps(fresh_queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


# ═══════════════════════════════════════════
#  자율 틈 감지기(배237(b)) 반반 레인 (US-004 · GM 결정 2026-07-08)
#  ★재개가능(resumable) 자율 write = 독립 게이트 AIDE_RESUMABLE_APPLY 뒤에서만.
#  ★정체(stalled) = surface-only — 자율 write 0(태그·nudge·의존해소·제안 배 전부 금지). 정보 표시만.
#   기존 GM_AIDE_AUTO_EXEC 와 무관(별도 env·별도 체크). 캡 MAX_AUTO_ACTIONS_PER_RUN 공유.
# ═══════════════════════════════════════════
def resumable_apply_enabled() -> bool:
    """재개가능 auto 레인 라이브 여부. AIDE_RESUMABLE_APPLY=1 일 때만 ON(기본 OFF)."""
    return os.environ.get(RESUMABLE_APPLY_ENV, "").strip().lower() in AUTO_EXEC_ON_VALUES


def _gap_to_capture(gap: dict) -> dict:
    """propose 폴백용 — gap → 기존 capture 스키마(make_proposal_ship 재사용)."""
    kind = gap.get("kind", "gap")
    tid = gap.get("task_id") or str(gap.get("ship_no") or "?")
    return make_capture(
        ctype=f"aide_{kind}",
        reversibility="비가역",   # propose 경로 = 가역 확신 못한 건 → 게이트 제안
        target_role=gap.get("clevel", "ceo"),
        title=f"[{tid}] {'정체' if kind == 'stalled' else '재개가능'} 감지",
        reason=gap.get("reason", ""),
        evidence=f"kind={kind} ship_no={gap.get('ship_no')} "
                 f"revert_ok={gap.get('revert_ok')} external={gap.get('external')} data_loss={gap.get('data_loss')}",
        remedy="GM 결정 필요(가역 확신 못함) → 제안만",
        dedup_key=f"gmaide|aide_{kind}|{tid}",
    )


def _apply_gap_auto(resumable_gaps: list) -> int:
    """AIDE_RESUMABLE_APPLY ON 전용 · 재개가능(resumable) gap 만: read-before-write 재로드 후
    가역 태그(resumable)+담당 재촉(nudge)+구조적 의존 해소 적용(GM 결정 2026-07-08).
    ★정체(stalled)는 이 함수에 절대 도달 안 함(split_lanes 하드 분리) — 방어적으로 kind 확인.
    각 조치를 log_auto_exec → gm_observation_ledger auto_exec 채널로 사유+되돌리기근거 적재.
    캡 MAX_AUTO_ACTIONS_PER_RUN(기존 자율레인과 공유). 멱등."""
    with (queue_lock.queue_lock("gm-aide") if queue_lock else nullcontext()):
        fresh = read_json(QUEUE_ACTIVE, [])
        by_tid = {_ship_id(x): x for x in fresh}
        by_sn = {x.get("ship_no"): x for x in fresh if isinstance(x.get("ship_no"), int)}
        applied = 0
        dirty = False
        for g in resumable_gaps[:MAX_AUTO_ACTIONS_PER_RUN]:
            if g.get("kind") != "resumable":
                continue  # 방어 — 정체(stalled) surface-only 는 여기서 절대 write 안 함
            ship = by_tid.get(g.get("task_id")) or by_sn.get(g.get("ship_no"))
            if not ship:
                continue
            target = g.get("task_id") or str(g.get("ship_no") or "?")
            did = False
            if auto_actions.apply_tag(ship, "resumable"):
                log_auto_exec("resumable_tag", target, "aide_flags:no-resumable", "aide_flags+=resumable",
                              restore_hint=f"원복=ship['aide_flags']에서 'resumable' 제거 · 사유={g['reason']}")
                did = True
            if auto_actions.set_nudge(ship, g["clevel"]):
                log_auto_exec("nudge", target, "aide_nudge:none", f"aide_nudge={g['clevel']}",
                              restore_hint=f"원복=ship['aide_nudge'] 삭제 · 담당 {g['clevel']} 재촉(재개 가능)")
                did = True
            old_dep = ship.get("depends_on")
            if auto_actions.resolve_structural_depends(ship):
                log_auto_exec("depends_resolved", target, f"depends_on={old_dep!r}",
                              "depends_on→depends_on_resolved 이전(원문 보존)",
                              restore_hint="원복=depends_on_resolved 값을 depends_on 으로 되돌림")
                did = True
            if did:
                applied += 1
                dirty = True
        if dirty:
            QUEUE_ACTIVE.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


def _register_gap_proposals(propose_gaps: list, kpi: dict, ns_map: dict,
                            profile_hints: list, archive: list) -> int:
    """propose 폴백 — 기존 make_proposal_ship 경로 재사용(새 제안타입 없음·dedup·캡 상속)."""
    with (queue_lock.queue_lock("gm-aide") if queue_lock else nullcontext()):
        fresh = read_json(QUEUE_ACTIVE, [])
        existing = existing_proposal_keys(fresh)
        fresh_max = max_ship_no(fresh, archive)
        added = 0
        for g in propose_gaps[:MAX_PROPOSALS_PER_RUN]:
            cap = _gap_to_capture(g)
            if cap["dedup_key"] in existing:
                continue
            fresh_max += 1
            fresh.append(make_proposal_ship(cap, fresh_max, kpi, ns_map, profile_hints))
            existing.add(cap["dedup_key"])
            added += 1
        if added:
            QUEUE_ACTIVE.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def _stall_surface_item(g: dict) -> dict:
    """정체 surface-only 정보 항목(보드/스캔로그용 · 자율 write 아님)."""
    return {
        "ship_no": g.get("ship_no"),
        "task_id": g.get("task_id"),
        "clevel": g.get("clevel"),
        "priority": g.get("priority"),
        "days_idle": g.get("days_idle"),
        "threshold": g.get("threshold"),
        "last_activity": g.get("last_activity"),
        "reason": g.get("reason"),
    }


def run_gap_detector(active: list, commit: bool, kpi: dict, ns_map: dict,
                     profile_hints: list, archive: list) -> dict:
    """자율 틈 감지기(배237(b)) 반반 라우팅(GM 결정 2026-07-08):
      - 재개가능(resumable) → auto 레인(AIDE_RESUMABLE_APPLY 게이트 뒤 · 태그+nudge+의존해소).
      - 정체(stalled)      → surface-only: 자율 write 0. 감지 목록만 산출(스캔로그/보드 정보 표시용).
      - 그 외              → propose(제안 배 폴백)."""
    gaps = stall_watch.detect_stalled(active, TODAY) + stall_watch.detect_resumable(active)
    resumable_auto, stall_surface, propose_gaps = reversibility.split_lanes(gaps)
    apply_on = resumable_apply_enabled()
    switch = "🟢 라이브(ON)" if apply_on else "🌙 휴면(OFF·dry-run)"
    print(f"\n[gap] 자율 틈 감지기(배237(b) 반반) — 재개가능 auto {switch} · 틈 {len(gaps)}건 "
          f"(재개가능 {len(resumable_auto)} · 정체 surface {len(stall_surface)} · 제안 {len(propose_gaps)})")
    for g in gaps:
        print(f"  [{g['kind']}] #{g.get('ship_no')} {g.get('task_id')} — {g['reason'][:70]}")

    stall_list = [_stall_surface_item(g) for g in stall_surface]
    result = {"gap_detected": len(gaps), "gap_auto": len(resumable_auto),
              "gap_stall": len(stall_surface), "gap_propose": len(propose_gaps),
              "resumable_apply_on": apply_on,
              "gap_auto_applied": 0, "gap_proposed": 0,
              "gap_stall_list": stall_list}

    if resumable_auto and apply_on:
        result["gap_auto_applied"] = _apply_gap_auto(resumable_auto)
        print(f"  ✅ 재개가능 자율 조치 {result['gap_auto_applied']}건 적용(태그·nudge·의존해소 + 원장 auto_exec).")
    elif resumable_auto:
        for g in resumable_auto[:MAX_AUTO_ACTIONS_PER_RUN]:
            print(f"  [dry-run] 재개가능 자율 조치 예정: #{g.get('ship_no')} ({RESUMABLE_APPLY_ENV} OFF·변경 0)")

    if stall_surface:
        print(f"  ⏳ 정체 의심 {len(stall_surface)}건 — surface-only(자율 write 0·자율현황/보드 정보 표시만·오탐 소지).")

    if propose_gaps and commit:
        result["gap_proposed"] = _register_gap_proposals(propose_gaps, kpi, ns_map, profile_hints, archive)
        if result["gap_proposed"]:
            print(f"  + 제안 배 {result['gap_proposed']}건 등록(propose 폴백·make_proposal_ship 재사용).")
    return result


# ═══════════════════════════════════════════
#  자동 검증-완결 핸들러 (자율 실행 루프 첫 닫힘 · 게이트 AIDE_VERIFY_APPLY 기본 OFF)
#  ★재개가능 auto 레인 뒤 · 명시적 verify 스펙 가진 배만 · PASS만 완결(거짓완료 0).
#   OFF=드라이런(_queue 미변경·스캔로그 요약만) / ON+closed 시에만 _queue 저장 + 원장 기록.
# ═══════════════════════════════════════════
def verify_apply_enabled() -> bool:
    """자동 검증-완결 라이브 여부. AIDE_VERIFY_APPLY=1 일 때만 ON(기본 OFF)."""
    return os.environ.get(VERIFY_APPLY_ENV, "0").strip() == "1"


def run_verify_complete(active: list) -> dict:
    """재개가능 auto 레인 뒤 검증형 배 자동 완결. verify_complete.handle 순수결과를
    받아 게이트 OFF=드라이런(변경 0)·ON=read-before-write 재로드 후 close 저장 + 원장 기록."""
    gate_on = verify_apply_enabled()
    switch = "🟢 라이브(ON)" if gate_on else "🌙 휴면(OFF·dry-run)"

    # 드라이런 패스: 인메모리 active 로 '무엇을 닫을지' 파악(gate_on=False → 배 뮤테이션 0).
    preview = verify_complete.handle(active, gate_on=False, today=today_str())
    pc = preview["counts"]
    print(f"\n[verify] 자동 검증-완결 핸들러 — {switch} · 검증대상 {pc['targets']}척 "
          f"(완결가능 {pc['dryrun_would_close']} · surface {pc['surface']} · terminal skip {pc['skipped_terminal']})")
    for r in preview["results"]:
        print(f"  [{r['outcome']}] {r['task_id']} — {str(r.get('evidence') or '')[:80]}")

    out = {
        "verify_gate_on": gate_on,
        "verify_targets": pc["targets"],
        "verify_would_close": pc["dryrun_would_close"],
        "verify_surface": pc["surface"],
        "verify_skipped_terminal": pc["skipped_terminal"],
        "verify_closed": 0,
    }

    if not gate_on:
        # 게이트 OFF: 드라이런 — 배·_queue 미변경. 스캔로그에 요약만(델타 0 보장).
        if pc["dryrun_would_close"]:
            print(f"  (휴면 — {VERIFY_APPLY_ENV} OFF. 완결 0. 라이브 발효=GM go 후 ON)")
        log_scan("verify_complete_dryrun", **out)
        return out

    # 게이트 ON: read-before-write 재로드 후 라이브 완결(gm_aide_scan 기존 저장 패턴 재사용).
    fresh = read_json(QUEUE_ACTIVE, [])
    live = verify_complete.handle(fresh, gate_on=True, today=today_str())
    closed = live["counts"]["closed"]
    if closed:
        QUEUE_ACTIVE.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        for r in live["results"]:
            if r["outcome"] == "closed":
                log_auto_exec("verify_complete", r["task_id"], "status:재개가능(검증대기)", r["evidence"],
                              restore_hint="원복=git revert(상태·메타만 변경·외부·파괴·전송 0)")
        print(f"\n  ✅ 자동 검증-완결 {closed}척 입항(_queue 저장 + 원장 auto_exec 기록).")
    out["verify_closed"] = closed
    log_scan("verify_complete", **out)
    return out


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(commit: bool = False, auto_exec_flag: bool = False) -> dict:
    mode = "라이브 제안등록(--commit)" if commit else "드라이런"
    print(f"[시작] GM 보좌 포착 스캔 ({mode}) — {now_str()}")

    active = read_json(QUEUE_ACTIVE, [])
    archive = read_json(QUEUE_ARCHIVE, [])
    kpi = read_json(STATUS_DIR / "kpi_values.json", {})
    ns_map = load_northstar_map()
    profile_exists = PROFILE_MD.exists()
    profile_hints = load_profile_missed_hints()
    todo_rows = fetch_todo_list_readonly()  # 업무&결재 SSOT 읽기 전용(배69) — 실패해도 빈 리스트, 스캔 계속
    print(f"[1/3] 입력 로드 — 활성큐 {len(active)}척 · 프로필 {'있음' if profile_exists else '없음(먼저 gm_profile_builder 실행 권장)'}"
          f" · 프로필 근거(자주 놓치는 것) {len(profile_hints)}건 연동 · 업무&결재 SSOT {len(todo_rows)}건 읽음")

    # ── 포착 ──
    captures = []
    parked_ids: list[str] = []          # ⚓ 정박 선언으로 건너뛴 배 — 숨기지 않고 로그에 남긴다
    captures += scan_long_pending(active, parked_out=parked_ids)
    captures += scan_stale_approval(todo_rows)
    # ★due_hygiene 은 여기 안 얹는다(약속 L20 · GM 확정 2026-08-19 "자가점검으로 배를 만들지 말고
    #   전체 정리를 표로만 내라"). scripts/hangro_board.py 가 scan_due_hygiene() 을 직접 import 해
    #   --role ceo 부팅 화면에 표로만 낸다 — captures/make_proposal_ship 경로 태우지 않는다.
    if parked_ids:
        print(f"  ⚓ 정박 선언(next 가 ⚓ 로 시작) {len(parked_ids)}척은 장기미착수 포착에서 제외 — {', '.join(parked_ids[:5])}")

    rev = [c for c in captures if c["reversibility"] == "가역"]
    irr = [c for c in captures if c["reversibility"] == "비가역"]
    print(f"\n[2/3] 포착 {len(captures)}건 (가역 {len(rev)} · 비가역·게이트 {len(irr)})")
    for c in captures:
        mark = "🔒비가역" if c["reversibility"] == "비가역" else "↩️가역"
        print(f"  {mark} [{c['type']}] {c['title']}")
        print(f"      사유: {c['reason'][:90]}")

    # ── 제안 배 등록: 비가역·게이트만 · dedup · cap ──
    # ★long_pending 은 배를 만들지 않는다 (GM 지시 2026-07-27 "내가 다 확인해서 수동으로 정리해야 하나?").
    #   기존 동작: 오래 멈춘 배마다 '[GM보좌 제안] N일째 미착수' 배를 **하나 더** 만들었다 →
    #   목록이 두 배가 되고, 원본과 제안이 나란히 떠서 GM 이 둘을 대조해 골라내야 했다.
    #   실측(2026-07-27): 열린 배 90척 중 진짜 정리 대상은 이 자동 생성분뿐이었다 —
    #   즉 '정리할 쓰레기'를 만들어낸 게 이 줄이다. 포착 자체는 로그에 그대로 남기고(신호 유지),
    #   화면에는 원본 배가 '오래 멈춤'으로 보이게 한다(자율현황 필터) — 배는 늘리지 않는다.
    #   약속 L21(장치를 늘리지 않는다) · 기억 '배 중복생성 금지 — 하위단계는 기존 배에 append'.
    NO_SHIP_TYPES = {"long_pending"}
    existing = existing_proposal_keys(active)
    candidates = [c for c in irr
                  if c["dedup_key"] not in existing and c["type"] not in NO_SHIP_TYPES]
    skipped_dedup = len(irr) - len(candidates)

    to_register = candidates[:MAX_PROPOSALS_PER_RUN]
    overflow = candidates[MAX_PROPOSALS_PER_RUN:]

    print(f"\n[3/3] 제안 배 등록 대상 {len(candidates)}건 "
          f"(중복 스킵 {skipped_dedup} · cap {MAX_PROPOSALS_PER_RUN} 초과 보류 {len(overflow)})")

    registered = []
    if to_register:
        base = max_ship_no(active, archive)
        for i, cap in enumerate(to_register, 1):
            ship = make_proposal_ship(cap, base + i, kpi, ns_map, profile_hints)
            registered.append(ship)
            print(f"  + #{ship['ship_no']} {ship['title']}  (clevel={ship['clevel']})")

    # ── phase2: 가역 자율실행 레이어 (휴면 기본 · GM go 후에만 ON) ──
    auto_on = auto_exec_enabled(auto_exec_flag)
    auto_actions = build_auto_actions(rev, active)
    switch = "🟢 라이브(ON)" if auto_on else "🌙 휴면(OFF·dry-run)"
    print(f"\n[phase2] 가역 자율실행 레이어 — {switch} · 대상 {len(auto_actions)}건 (가역 메타행위만)")
    auto_applied = 0
    if not auto_actions:
        print("  (자율실행할 가역 메타행위 없음)")
    elif not auto_on:
        for a in auto_actions[:MAX_AUTO_ACTIONS_PER_RUN]:
            print(f"  [dry-run] 자율실행 예정: {a['desc']}")
        print(f"  (휴면 — {AUTO_EXEC_ENV} OFF. 실제 변경 0. 라이브 발효=GM go 후 ON)")
    else:
        auto_applied = apply_auto_actions(auto_actions, archive)
        print(f"  ✅ 가역 자율실행 {auto_applied}건 적용 + 사후로그(원장 auto_exec·원복근거 기록).")

    # ── 자율 틈 감지기(배237(b) 반반) — 재개가능=auto(게이트 AIDE_RESUMABLE_APPLY 뒤)·정체=surface-only ──
    gap_result = run_gap_detector(active, commit, kpi, ns_map, profile_hints, archive)

    # ── 자동 검증-완결 핸들러(재개가능 auto 레인 뒤 · 게이트 AIDE_VERIFY_APPLY 기본 OFF) ──
    verify_result = run_verify_complete(active)

    result = {
        "captured": len(captures),
        "reversible": len(rev),
        "irreversible": len(irr),
        "registered": len(registered),
        "skipped_dedup": skipped_dedup,
        "overflow": len(overflow),
        "auto_exec_on": auto_on,
        "auto_actions": len(auto_actions),
        "auto_applied": auto_applied,
        **gap_result,
        **verify_result,
    }

    if not commit:
        print("\n  (드라이런 — 제안 배 큐 변경 없음. 실제 등록은 --commit)")
        if overflow:
            print(f"  ※ cap 초과 {len(overflow)}건은 --commit 시 스캔 로그에 기록되고 이번엔 미등록.")
        return result

    # ── 라이브: read-before-write 재로드 후 append (동시성 최소화) ──
    if registered:
        fresh = read_json(QUEUE_ACTIVE, [])
        fresh_keys = existing_proposal_keys(fresh)
        fresh_max = max_ship_no(fresh, archive)
        appended = 0
        for cap in to_register:
            if cap["dedup_key"] in fresh_keys:
                continue
            fresh_max += 1
            fresh.append(make_proposal_ship(cap, fresh_max, kpi, ns_map, profile_hints))
            fresh_keys.add(cap["dedup_key"])
            appended += 1
        QUEUE_ACTIVE.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        result["registered"] = appended
        print(f"\n  ✅ _queue.json 에 제안 배 {appended}건 등록(재로드 후 append).")

    log_scan(
        "scan",
        captured=result["captured"],
        reversible=result["reversible"],
        irreversible=result["irreversible"],
        registered=result["registered"],
        skipped_dedup=skipped_dedup,
        parked_skipped=len(parked_ids),      # ⚓ 정박 선언으로 제외한 배 수(숨기지 않고 기록)
        parked_ids=parked_ids,
        overflow=[c["dedup_key"] for c in overflow],
        capture_keys=[c["dedup_key"] for c in captures],
        auto_exec_on=auto_on,
        auto_applied=auto_applied,
        profile_hints_used=profile_hints,
        # 자율 틈 감지기(배237(b) 반반) — 자율현황 집계·정체 정보패널 배선.
        gap_auto=gap_result["gap_auto"],
        gap_stall=gap_result["gap_stall"],
        gap_propose=gap_result["gap_propose"],
        gap_auto_applied=gap_result["gap_auto_applied"],
        gap_proposed=gap_result["gap_proposed"],
        resumable_apply_on=gap_result["resumable_apply_on"],
        gap_stall_list=gap_result["gap_stall_list"],  # 정체 surface-only 목록(보드 정보 표시용)
    )
    print(f"[완료] ({now_str()}) — 스캔 로그: {SCAN_LOG.name}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="GM 보좌 포착 스캔 phase1 — 포착 이벤트 생성 + 비가역·게이트 건 G1 제안 배 등록",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--commit", action="store_true",
                        help="제안 배 실제 등록(_queue.json 갱신 + 스캔 로그). 미지정 시 드라이런")
    parser.add_argument("--auto-exec", action="store_true",
                        help=f"phase2 가역 자율실행 라이브 발효(로컬 시뮬용). "
                             f"기본 휴면 · 상시 스위치=환경변수 {AUTO_EXEC_ENV}=1 (GM go 후에만)")
    args = parser.parse_args()
    run(commit=args.commit, auto_exec_flag=args.auto_exec)


if __name__ == "__main__":
    # 콘솔 한글 깨짐 방지(Windows cp949) — 스탠드얼론 실행 시에만(import 경로에선 전역 스트림 불건드림).
    # 선례: support_check_summary.py main(), self_health_watchdog.py / module_silence_detector.py 하단 가드.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
