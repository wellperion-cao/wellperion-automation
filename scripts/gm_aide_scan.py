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
    ③ 크론-실행 가능한 가역 메타행위만: 현재=drift(next 없는 완료 표류) 배에 '다음 한 수' 후보 next 자동 보강.
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
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
LEDGER = STATUS_DIR / "gm_observation_ledger.jsonl"
QUEUE_ACTIVE = STATUS_DIR / "_queue.json"
QUEUE_ARCHIVE = STATUS_DIR / "_queue_archive.json"
NORTHSTAR_LOG = STATUS_DIR / "northstar_log.jsonl"
NORTHSTAR_PENDING = STATUS_DIR / "northstar_pending.json"
PROFILE_MD = STATUS_DIR / "gm_profile.md"
MATRIX_FILE = ROOT / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"
SCAN_LOG = STATUS_DIR / "gm_aide_scan_log.jsonl"

LONG_PENDING_DAYS = 30
UNAPPROVED_STREAK_GATE = 3     # 추천 미응답 연속 이만큼이면 '접근 재점검' 게이트 제안
MAX_PROPOSALS_PER_RUN = 5      # 하루 과다등록 방지 cap
PROPOSAL_TAG = "[GM보좌 제안]"

# ── phase2 가역 자율실행 레이어 스위치 (휴면 기본) ──
# 기본 OFF(dry-run). ON 은 GM go 후에만(feedback_security_live_activation_needs_gm_go).
# 라이브 발효 = 환경변수 GM_AIDE_AUTO_EXEC=1 (또는 --auto-exec 로컬 시뮬).
AUTO_EXEC_ENV = "GM_AIDE_AUTO_EXEC"
AUTO_EXEC_ON_VALUES = {"1", "true", "on", "yes"}
MAX_AUTO_ACTIONS_PER_RUN = 5   # 가역 자율실행 폭주 방지 cap

ROLE_NICK = {
    "ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
    "coo": "시우", "cpo": "시포", "cto": "시토",
}

TODAY = datetime.now().date()


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
        "type": ctype,                 # drift / long_pending / unapproved_recommendation / routine_missing
        "reversibility": reversibility,
        "target_role": target_role,
        "title": title,
        "reason": reason,
        "evidence": evidence,
        "remedy": remedy,              # 함의된 조치(가역=리마인드/촉구 / 비가역=GM 결정 필요)
        "dedup_key": dedup_key,
        "source_task_id": _ship_id(source_item) if source_item else "",
    }


def scan_drift(active: list) -> list:
    """완료·terminal 인데 next 없음 = 표류. 조치=후속 정하기 촉구(가역 리마인드)."""
    caps = []
    for x in active:
        if not (x.get("status") == "DONE" or x.get("terminal")):
            continue
        if (x.get("next") or "").strip():
            continue
        tid = _ship_id(x)
        role = (x.get("clevel") or "ceo").lower()
        caps.append(make_capture(
            ctype="drift",
            reversibility="가역",   # 촉구·리마인드는 되돌릴 수 있음 → phase1 제안대상 아님(표시만)
            target_role=role,
            title=f"[{tid}] 완료 후 '다음' 미정 표류",
            reason="완료·terminal 인데 next 필드가 비어 다음 한 수가 없음",
            evidence=f"status={x.get('status')} terminal={x.get('terminal')}",
            remedy="담당 C-Level에 '다음 한 수' 지정 리마인드(가역)",
            dedup_key=f"gmaide|drift|{tid}",
            source_item=x,
        ))
    return caps


def scan_long_pending(active: list) -> list:
    """PENDING 장기 대기 = 우선순위 재확인 또는 폐기 판단 필요. 폐기=삭제(비가역)·GM 결정 → 게이트 제안."""
    caps = []
    for x in active:
        if x.get("status") != "PENDING":
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


def scan_unapproved_recommendation(ns_log: list, ns_pending: dict) -> list:
    """북극성 추천 미응답. 최근 1회=가역 리마인드 / 연속 {GATE}일+=접근 재점검(게이트 제안)."""
    caps = []
    # 최근 연속 미응답(expired) streak
    streak = 0
    for e in reversed(ns_log):
        if e.get("event") == "expired":
            streak += 1
        elif e.get("event") == "proposed":
            continue
        else:
            break

    pending_status = str(ns_pending.get("status")) if isinstance(ns_pending, dict) else ""
    pending_date = ns_pending.get("date") if isinstance(ns_pending, dict) else None
    aging_unapproved = pending_status == "proposed" and pending_date != today_str()

    if streak >= UNAPPROVED_STREAK_GATE:
        caps.append(make_capture(
            ctype="unapproved_recommendation",
            reversibility="비가역",   # '도달/노출 방식 재점검' = 전략·프로세스 결정 게이트 → 제안
            target_role="ceo",
            title=f"06:30 북극성 추천 카드 {streak}일 연속 미응답",
            reason=f"추천 카드 {streak}일 연속 자동만료 — 도달/노출 방식 재점검이 필요한 구조 신호",
            evidence=f"missed_streak={streak} pending_status={pending_status}",
            remedy="GM 결정 필요: 추천 전달 방식·시점 재설계 여부(전략 게이트) → 제안만",
            # 안정 키(날짜·streak숫자 미포함, 2026-07-04 수정) — 이 유형 열린 카드가 있는 한
            # 매일 재등록되지 않도록 한다(구 키에 날짜가 껴 매일 새 카드 증식하던 버그 수정).
            dedup_key="gmaide|unapproved_streak",
        ))
    elif aging_unapproved:
        caps.append(make_capture(
            ctype="unapproved_recommendation",
            reversibility="가역",   # 단순 리마인드 → phase1 표시만
            target_role="ceo",
            title=f"미승인 추천 카드 대기({pending_date})",
            reason="직전 추천 카드가 아직 미승인(proposed) 상태로 대기",
            evidence=f"pending_date={pending_date} pending_status={pending_status}",
            remedy="GM에 추천 카드 응답 리마인드(가역)",
            dedup_key=f"gmaide|unapproved_pending|{pending_date}",
        ))
    return caps


def scan_routine_missing(ns_pending: dict) -> list:
    """루틴 누락 — 오늘 06:30 추천 카드가 아직 생성 안 됨(routine gap). 조치=리마인드(가역)."""
    caps = []
    pending_date = ns_pending.get("date") if isinstance(ns_pending, dict) else None
    if pending_date != today_str():
        caps.append(make_capture(
            ctype="routine_missing",
            reversibility="가역",
            target_role="ceo",
            title="오늘 북극성 추천 루틴 미생성",
            reason="오늘자 northstar_pending 이 아직 없음 — 06:30 추천 루틴 미가동 가능성",
            evidence=f"pending_date={pending_date} today={today_str()}",
            remedy="추천기(northstar_recommender --send) 가동 확인 리마인드(가역)",
            dedup_key=f"gmaide|routine_missing|{today_str()}",
        ))
    return caps


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
#  현재 지원 액션: next_augment — 표류(next 없는 완료) 배에 '다음 한 수' 후보를
#  자동 보강(가역: aide_auto_exec.old_next 로 원복). 멱등: next 이미 있으면 skip.
def auto_exec_enabled(cli_flag: bool = False) -> bool:
    """라이브 발효 여부. --auto-exec(로컬 시뮬) 또는 GM_AIDE_AUTO_EXEC=1 일 때만 ON."""
    if cli_flag:
        return True
    return os.environ.get(AUTO_EXEC_ENV, "").strip().lower() in AUTO_EXEC_ON_VALUES


def _augment_next_value(cap: dict) -> str:
    tid = cap.get("source_task_id") or "?"
    role = cap.get("target_role", "ceo")
    nick = ROLE_NICK.get(role, role.upper())
    return (f"👉 다음 정하세요(자동보강·gm_aide): [{tid}] 완료 후 다음 한 수 미정 표류 — "
            f"담당 {nick}가 후속 한 수 확정 필요. (가역·원복=next 를 빈 값으로)")


def build_auto_actions(rev_caps: list, active: list) -> list:
    """가역 포착 → 크론-실행 가능한 가역 메타행위 목록. 현재=drift→next_augment 만."""
    by_tid = {_ship_id(x): x for x in active}
    actions = []
    for c in rev_caps:
        if c.get("type") != "drift":
            continue  # drift 외 가역(리마인드형)은 새 알림 스트림 금지 → 여기서 실행 안 함
        tid = c.get("source_task_id")
        ship = by_tid.get(tid)
        if not ship:
            continue
        if (ship.get("next") or "").strip():
            continue  # 멱등: 이미 next 있으면 자율실행 대상 아님
        actions.append({
            "action_type": "next_augment",
            "target_task_id": tid,
            "reversibility": "가역",
            "new_next": _augment_next_value(c),
            "desc": f"next 보강 [{tid}] 표류 배에 '다음 한 수' 후보 자동 기입",
            "dedup_key": f"gmaide_autoexec|next_augment|{tid}",
        })
    return actions


def log_auto_exec(action_type: str, target: str, old_next: str, new_next: str) -> None:
    """자율실행 사후로그 — 관찰 원장에 auto_exec 신호 + 원상복구 근거(old_next)."""
    rec = {
        "observed_at": now_str(),
        "source": "gm_aide_auto_exec",
        "signal_type": "auto_exec",
        "summary": f"[{target}] 가역 자율실행: {action_type} (표류 배 next 자동보강)",
        "evidence": f"old_next={old_next!r} new_next_요약={new_next[:60]!r}",
        "pattern_hint": "가역 메타행위 자율실행 — 원복 가능(ship.aide_auto_exec.old_next)",
        "reversibility": "가역",
        "dedup_key": f"gmaide_autoexec|{action_type}|{target}",
    }
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] auto_exec 원장 기록 실패: {e}")


def apply_auto_actions(actions: list, archive: list) -> int:
    """라이브(ON) 전용: read-before-write 재로드 후 가역 메타행위 적용 + 사후로그.
    각 배에 aide_auto_exec(원복 근거) 기록. G1 입항 기록 = 원장 auto_exec 로그."""
    if not actions:
        return 0
    fresh = read_json(QUEUE_ACTIVE, [])
    by_tid = {_ship_id(x): x for x in fresh}
    applied = 0
    for a in actions[:MAX_AUTO_ACTIONS_PER_RUN]:
        ship = by_tid.get(a["target_task_id"])
        if not ship:
            continue
        if (ship.get("next") or "").strip():
            continue  # 재확인(동시성) — 이미 채워졌으면 skip
        old_next = ship.get("next", "")
        ship["next"] = a["new_next"]
        ship["aide_auto_exec"] = {
            "action": a["action_type"],
            "at": now_str(),
            "old_next": old_next,
            "restore": "next 를 old_next 값으로 되돌리면 원상복구(가역)",
        }
        log_auto_exec(a["action_type"], a["target_task_id"], old_next, a["new_next"])
        applied += 1
    if applied:
        QUEUE_ACTIVE.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(commit: bool = False, auto_exec_flag: bool = False) -> dict:
    mode = "라이브 제안등록(--commit)" if commit else "드라이런"
    print(f"[시작] GM 보좌 포착 스캔 ({mode}) — {now_str()}")

    active = read_json(QUEUE_ACTIVE, [])
    archive = read_json(QUEUE_ARCHIVE, [])
    ns_log = read_jsonl(NORTHSTAR_LOG)
    ns_pending = read_json(NORTHSTAR_PENDING, {})
    kpi = read_json(STATUS_DIR / "kpi_values.json", {})
    ns_map = load_northstar_map()
    profile_exists = PROFILE_MD.exists()
    profile_hints = load_profile_missed_hints()
    print(f"[1/3] 입력 로드 — 활성큐 {len(active)}척 · 프로필 {'있음' if profile_exists else '없음(먼저 gm_profile_builder 실행 권장)'}"
          f" · 프로필 근거(자주 놓치는 것) {len(profile_hints)}건 연동")

    # ── 포착 ──
    captures = []
    captures += scan_drift(active)
    captures += scan_long_pending(active)
    captures += scan_unapproved_recommendation(ns_log, ns_pending)
    captures += scan_routine_missing(ns_pending)

    rev = [c for c in captures if c["reversibility"] == "가역"]
    irr = [c for c in captures if c["reversibility"] == "비가역"]
    print(f"\n[2/3] 포착 {len(captures)}건 (가역 {len(rev)} · 비가역·게이트 {len(irr)})")
    for c in captures:
        mark = "🔒비가역" if c["reversibility"] == "비가역" else "↩️가역"
        print(f"  {mark} [{c['type']}] {c['title']}")
        print(f"      사유: {c['reason'][:90]}")

    # ── 제안 배 등록: 비가역·게이트만 · dedup · cap ──
    existing = existing_proposal_keys(active)
    candidates = [c for c in irr if c["dedup_key"] not in existing]
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
        overflow=[c["dedup_key"] for c in overflow],
        capture_keys=[c["dedup_key"] for c in captures],
        auto_exec_on=auto_on,
        auto_applied=auto_applied,
        profile_hints_used=profile_hints,
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
    main()
