#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GM 프로필 생성기 (배237 · GM 보좌 자율화 체계 phase 1 · 구현①).

관찰 원장(gm_observation_ledger.jsonl)과 업무 큐(_queue*.json)를 읽어
'GM의 성향·습관·자주 놓치는 것·루틴 준수·핵심 수치지표'를 담은
사람이 읽는 서술 프로필 status/gm_profile.md 를 생성한다.

설계 정본:
  - 스펙 : .omc/specs/deep-interview-gm-aide-autonomy.md (①관찰·학습 = 수치+LLM 하이브리드, 일일 갱신)
  - 배   : status/_queue.json  CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237)

두뇌(하이브리드):
  - 1순위: claude CLI (scripts/model_router.run_claude · 폴백 체인) — LLM 서술 프로필
  - 2순위: 규칙기반 서술 폴백 — CLI 전멸 시에도 무중단(수치 카운터 기반 요약)

★ phase 1 안전 원칙 (라이브 부작용 0):
  - 파일 read + status/gm_profile.md write 만. 발송·삭제·외부전송·GAS·시트 변경 0.
  - 멱등: 같은 입력이면 수치 카운터 동일. gm_profile.md 는 매 실행 전체 덮어쓰기(일일 갱신).

사용법:
  python scripts/gm_profile_builder.py            # 프로필 생성(기본) — gm_profile.md 갱신
  python scripts/gm_profile_builder.py --stdout-only   # 파일 기록 없이 콘솔만(드라이)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
LEDGER = STATUS_DIR / "gm_observation_ledger.jsonl"
QUEUE_ACTIVE = STATUS_DIR / "_queue.json"
QUEUE_ARCHIVE = STATUS_DIR / "_queue_archive.json"
PROFILE_MD = STATUS_DIR / "gm_profile.md"

LONG_PENDING_DAYS = 30
TODAY = datetime.now().date()

# ── GM 표면 점검(2026-07-29 GM go · 웰리 제안) ──
# 배경: 2026-07-29 GM이 짚은 5건 중 4건(공개홈 글꼴 정본 이탈·핵심과제 칸 3,418자·브로제이 분리 필요·
# 보류 재부상 접기)을 아침 점검이 먼저 찾았어야 했는데 놓쳤다 — 점검이 "내 모듈이 도는가"만 보고
# "GM이 여는 화면이 읽히는가"를 안 봤기 때문. 새 스크립트·새 예약작업 0(약속 L21) — 이미 06:30에
# 도는 이 파일(gm_profile_builder.py)에 얹는다. 산출도 새 파일 0: JSON=기존 LEDGER에 append,
# 사람 요약=기존 PROFILE_MD에 새 섹션.
GM_SURFACE_CELL_MAX = 300     # 칸 하나 최대 가시 글자수 기준. 근거=2026-07-29 실측: 접힘 적용 후
                              # 정상 상태 최대 칸이 254자(핵심과제 title cell)였다 — 그 위에 여유를 둠.
GM_SURFACE_BLOCK_MAX = 5000   # 블록 하나 최대 가시 글자수 기준. 근거=2026-07-29 실측: 접힘 적용 후
                              # 정상 상태 최대 블록이 3,422자(월간운영계획 obj-board 전체)였다 —
                              # 접힘 전 옛 상태(13,293자)는 이 기준에 확실히 걸린다.
GM_SURFACE_STALE_DAYS = 2     # 값이 이 일수 이상 그대로면 "갱신 정지" 의심으로 본다.
GM_SURFACE_PUSH_STALE_HOURS = 6  # 올린 지 이 시간 이상 지났는데 올릴 것이 남아 있으면 "GM 화면 멈춤".

GM_SURFACE_PAGES = [
    # mode='plain' = 그 URL 자체가 화면 · mode='anchor' = wellperion_guide(main).html 안 탭
    {"label": "월간운영계획", "mode": "plain",
     "url": "https://wellperion-cao.github.io/wellperion-automation/%EC%9B%94%EA%B0%84%EC%9A%B4%EC%98%81%EA%B3%84%ED%9A%8D.html"},
    {"label": "브로제이 업무분장", "mode": "plain",
     "url": "https://wellperion-cao.github.io/wellperion-automation/coo/brojay/%EB%B8%8C%EB%A1%9C%EC%A0%9C%EC%9D%B4_%EC%97%85%EB%AC%B4%EB%B6%84%EC%9E%A5.html"},
    {"label": "자율현황", "mode": "plain",
     "url": "https://wellperion-cao.github.io/wellperion-automation/%EC%9E%90%EC%9C%A8%ED%98%84%ED%99%A9.html"},
    {"label": "G1 오늘의 항로", "mode": "anchor", "anchor": "G1",
     "url": "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html"},
    {"label": "업무·결재 SSOT", "mode": "anchor", "anchor": "S3",
     "url": "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html"},
    # 2026-08-01 추가 — AI C-Level 운영 한 장(AI운영한장.html)을 여기로 흡수하면서 같이 넣었다.
    # 그 페이지가 감시 목록 밖이라 조용히 굳어도 아무도 몰랐던 것이 폐지 사유 중 하나였으므로,
    # 옮긴 자리도 같은 사각이 되면 안 된다.
    {"label": "AI C-Level 운영 가이드", "mode": "anchor", "anchor": "S2",
     "url": "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html"},
]

# ── '사실인가' 원천 매핑(2026-07-31 · 배 10418 「GM 표면·G1 위생」 다음 과제 이행) ──
# 배경: 위 점검은 '읽히는가'(글자수)·'GM 일인가'(audience 비율) 둘만 재고, 3질문의 가운데인
# '사실인가'는 "화면별 원천 매핑이 필요"하다는 이유로 매일 범위 밖으로 남아 있었다.
# 그래서 화면 숫자가 며칠 굳어 있어도 점검은 매일 "기준 이내"를 냈다(2026-07-27 실측:
# GM 일일 요약이 7일째 옛 숫자였다 — 그때도 이 점검은 통과였다).
#
# 매핑 원칙 3가지:
#  1) 저장소 파일만 잰다. 화면 대부분은 GAS(구글 앱스스크립트)·시트에서 값을 받아오는데,
#     그건 이 스크립트가 못 본다 — 못 본 것은 `external` 로 적어 "측정 못 함"으로 낸다.
#     통과로 위장하지 않는다(0 위장 방지 · wellperion-boot §2-1 #7).
#  2) 신선도 기준은 파일 mtime 이 아니라 **git 커밋 시각**이다. 라이브 화면은 GitHub raw 를
#     읽으므로, 로컬에서 아무리 갱신돼도 커밋 안 됐으면 GM 화면은 옛 값이다(§2-1 #8 작업트리 고립).
#  3) 매일 갱신되는 것(`daily`)만 신선도를 따진다. 사람이 필요할 때만 고치는 것(`manual`)은
#     오래됐다고 문제가 아니다 — 그걸 경보로 내면 매일 거짓 경보가 뜬다.
GM_SURFACE_SOURCES = {
    "월간운영계획": {
        "repo": [("status/kpi_values.json", "daily")],           # kpi_collector.py 일 2회
        "manual": ["3. 웰페리온 가이드/coo/bootsetup_matrix.json"],  # GM 인라인 편집
        "external": ["점검 GAS(board·monthly_report·today_live)", "매출 GAS(home_kpi·sales_monthly·team_sales)"],
    },
    "자율현황": {
        # ★2026-07-31 시토 — 화면이 실제로 읽는 13개 중 3개만 재고 있었다. 오늘 GM 께서
        #   찾아내신 두 건이 정확히 그 사각에서 나왔다: ①"카톡 매출보고 239시간 멈춤"이라는
        #   거짓 빨간불(원천이 이틀째 저장소에 못 올라가 있었다) ②"코드↔등록부를 상시 대조
        #   중"이라는 거짓 안내(대조 결과가 8일째 굳어 있었다 — 이 파일은 아예 목록에 없었다).
        #   화면이 읽는데 아무도 신선도를 안 보는 파일이 있으면, 그 화면은 조용히 옛 값을
        #   사실처럼 말한다. **매일 갱신돼야 하는 것만** 아래에 넣는다(설정 파일은 manual 로
        #   그대로 둔다 — 안 바뀌는 게 정상인 것을 '멈췄다'고 부르면 그게 새 오탐이 된다).
        "repo": [("status/erp_status.json", "daily"),
                 ("status/gm_observation_ledger.jsonl", "daily"),
                 ("status/module_silence_snapshot.json", "daily"),
                 ("status/notify_drift.json", "daily"),      # 코드↔등록부 대조 결과
                 ("status/kakao_last_send.json", "daily")],  # 카톡 발신 기록(멈춤 판정 근거)
        "manual": ["status/module_registry.json", "status/notify_registry.json", "status/audit_registry.json",
                   "status/telegram_rooms.json"],
        "external": ["회원 LOSS GAS(cpo_churn_stats)"],
    },
    "G1 오늘의 항로": {
        # G1 은 발행 루트 안 미러를 읽는다(INC-007 이후 구조). 원천은 저장소 루트 큐다.
        "repo": [("3. 웰페리온 가이드/status/_queue.json", "daily")],
        "manual": [],
        "external": [],
        "parity": ("status/_queue.json", "3. 웰페리온 가이드/status/_queue.json"),
    },
    "업무·결재 SSOT": {
        "repo": [], "manual": [],
        "external": ["업무현황 GAS(todo_list)"],
    },
    "브로제이 업무분장": {
        "repo": [], "manual": [],
        "external": ["점검 GAS(board · 브로제이 저장키)"],
    },
}


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


def read_json_array(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


# ═══════════════════════════════════════════
#  수치 카운터 (결정적 · 항상 계산)
# ═══════════════════════════════════════════
def compute_counters(ledger: list, active: list, archive: list) -> dict:
    by_type = Counter(r.get("signal_type") for r in ledger)
    by_source = Counter(r.get("source") for r in ledger)

    # 근거 정직 표기용: GM이 세션에서 직접 남긴 신호(source에 "_session_" 포함,
    # 예 cmo_session_2026-07-25) vs 시스템이 자기 가동/큐 상태를 스스로 적은 미러링.
    session_sources = {s: n for s, n in by_source.items() if s and "_session_" in s}
    session_signal_total = sum(session_sources.values())
    machine_mirror_total = len(ledger) - session_signal_total

    # 경로가 '있다'와 '쓰인다'는 다르다 — 최근 7일 실제 사용량·사용 역할을 따로 센다(ship 10267).
    # 2026-07-29 발효한 흡수 경로(clevel_post_action.py --gm-signal)가 실제로 원장을 채우는지
    # 매 실행 재측정한다. 이 값이 안 오르면 경로가 있어도 학습기는 여전히 GM을 못 본다.
    session_recent_cut = TODAY - timedelta(days=7)
    session_recent = 0
    session_roles: set[str] = set()
    for r in ledger:
        src = r.get("source") or ""
        if "_session_" not in src:
            continue
        session_roles.add(src.split("_session_")[0])
        try:
            d = datetime.strptime(str(r.get("observed_at", ""))[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if d >= session_recent_cut:
            session_recent += 1

    # 활성 큐 상태 분포
    status_counter = Counter(x.get("status") for x in active)

    # 장기 대기(라이브 재계산)
    # ★정박 선언(next 가 ⚓ 로 시작)한 배는 세지 않는다 — 담당이 재개조건을 적어 의도적으로
    # 세워 둔 것이고, GM 결재도 이미 끝나 있다(예: AWS 가용 ≈2026-09 · PII D안 9월까지 현상유지).
    # 이걸 안 걸러서 프로필이 매일 "처분 판단이 미뤄져 있다"고 GM께 잘못 말해 왔다.
    # 판정은 복제하지 않고 gm_aide_scan._is_parked 단일 지점을 재사용한다(약속 L01·L21).
    try:
        from gm_aide_scan import _is_parked as _parked
    except Exception:
        _parked = None
    long_pending = 0
    parked_skipped = 0
    for x in active:
        if x.get("status") != "PENDING":
            continue
        if _parked is not None and _parked(x):
            parked_skipped += 1
            continue
        enq = x.get("enqueued_at")
        if not enq:
            continue
        try:
            d = datetime.strptime(enq, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (TODAY - d).days >= LONG_PENDING_DAYS:
            long_pending += 1

    # 표류(완료·terminal 인데 next 없음) — 활성 큐 기준
    drift = 0
    for x in active:
        if x.get("status") == "DONE" or x.get("terminal"):
            if not (x.get("next") or "").strip():
                drift += 1

    return {
        "observations_total": len(ledger),
        "observations_by_type": dict(by_type),
        "observations_by_source": dict(by_source),
        "session_signal_total": session_signal_total,
        "machine_mirror_total": machine_mirror_total,
        "session_signal_recent7": session_recent,
        "session_signal_roles": sorted(session_roles),
        "gm_decisions": by_type.get("decision", 0),
        "drift_events_ledger": by_type.get("repeat", 0),
        "queue_active_total": len(active),
        "queue_status": dict(status_counter),
        "queue_archive_total": len(archive),
        "long_pending_live": long_pending,
        "long_pending_parked_skipped": parked_skipped,
        "drift_live": drift,
    }


# ═══════════════════════════════════════════
#  두뇌 ① — claude CLI (model_router 폴백)
# ═══════════════════════════════════════════
def _ledger_digest(ledger: list, limit: int = 24) -> str:
    """원장에서 최근·대표 관찰 요약을 프롬프트용 다이제스트로."""
    lines = []
    for r in ledger[-limit:]:
        st = r.get("signal_type", "?")
        summ = (r.get("summary") or "").strip()[:110]
        hint = (r.get("pattern_hint") or "").strip()[:80]
        lines.append(f"- [{st}] {summ}" + (f" · 힌트:{hint}" if hint else ""))
    return "\n".join(lines)


def _build_prompt(counters: dict, ledger: list) -> str:
    digest = _ledger_digest(ledger)
    ct = counters
    return f"""당신은 웰페리온(하이엔드 스포츠클럽 멤버십 커뮤니티) AI CEO '웰리'입니다.
GM(대표)을 보좌하기 위해, 관찰 원장과 업무 큐 지표를 근거로 **GM의 성향·습관 프로필**을 작성합니다.
목적: GM이 놓친 것·다음 할 것을 웰리가 선제 포착할 수 있도록, GM의 일하는 패턴을 서술로 정리하는 것.

[수치 지표(관찰 원장·큐 집계)]
- 총 관찰 {ct['observations_total']}건 (유형별: {ct['observations_by_type']})
- GM 결정 이력 {ct['gm_decisions']}건
- 표류(완료 후 다음 미정) 관찰 {ct['drift_events_ledger']}건 / 라이브 표류 {ct['drift_live']}건
- 활성 큐 {ct['queue_active_total']}척 (상태: {ct['queue_status']}) · 장기 대기(30일+) {ct['long_pending_live']}척

[최근 관찰 다이제스트]
{digest}

위 지표와 관찰을 근거로, GM의 프로필을 **한국어 마크다운 서술**로 작성하세요.
반드시 아래 5개 소제목(## )을 그대로 사용하고, 각 항목은 3~5개의 불릿으로 근거와 함께 씁니다.
추정은 '추정' 라벨을 붙이고, 측정 못 한 것을 측정한 척하지 마세요(관측 정직).

## 선호
## 습관
## 자주 놓치는 것
## 루틴 준수
## 핵심 수치지표 해석

규칙:
- 순수 마크다운 본문만 출력(코드블록·머리말·맺음말 없이).
- 프라이버시: 민감 원문 대신 패턴·요약 위주.
- 각 불릿은 근거(어느 지표/관찰)에 연결되게."""


def brain_claude_cli(counters: dict, ledger: list) -> tuple[str | None, str | None]:
    prompt = _build_prompt(counters, ledger)
    try:
        from model_router import run_claude
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from model_router import run_claude
    raw, used_model = run_claude(prompt, label="gm-profile-builder")
    if raw is None:
        return None, None
    return raw.strip(), used_model


# ═══════════════════════════════════════════
#  두뇌 ② — 규칙기반 서술 폴백 (CLI 전멸 시 무중단)
# ═══════════════════════════════════════════
def brain_fallback(counters: dict) -> str:
    ct = counters
    q = ct["queue_status"]
    pending = q.get("PENDING", 0)
    inprog = q.get("IN_PROGRESS", 0)
    parts = []
    parts.append("## 선호")
    parts.append(f"- (추정) GM 결정 이력 {ct['gm_decisions']}건 — 큐 note에 결정을 직접 남기는 방식을 선호(원장 근거).")
    parts.append("- (추정) 라이브 파괴 위험 작업은 '다음 집중세션·신중' 지시로 미루는 경향(결정 관찰 패턴).")
    parts.append("")
    parts.append("## 습관")
    parts.append(f"- 활성 배 {ct['queue_active_total']}척 동시 진행(PENDING {pending}·IN_PROGRESS {inprog}) — 병렬 다발 진행 습관.")
    parts.append(f"- 완료 아카이브 {ct['queue_archive_total']}건 — 지속적으로 배를 완주·아카이브하는 흐름.")
    parts.append("")
    parts.append("## 자주 놓치는 것")
    parts.append(f"- 표류(완료 후 다음 미정) 라이브 {ct['drift_live']}건 — 완료 시 '다음 한 수' 지정을 빠뜨리는 경향.")
    parts.append(
        f"- 장기 대기(30일+) {ct['long_pending_live']}척 — 우선순위 낮은 배의 정리·폐기 판단을 미룸."
        + (f" (정박 선언 {ct.get('long_pending_parked_skipped', 0)}척은 제외했다 — 재개조건이 적혀 있고 GM 결재도 끝난 배)"
           if ct.get("long_pending_parked_skipped") else "")
    )
    parts.append("")
    parts.append("## 루틴 준수")
    parts.append("- (추정) 지시-실행-완료 사이클은 유지되나, 사후 '다음 정하기' 루틴은 느슨.")
    parts.append("")
    parts.append("## 핵심 수치지표 해석")
    parts.append(f"- 총 관찰 {ct['observations_total']}건 / 유형: {ct['observations_by_type']}")
    parts.append(f"- 활성 {ct['queue_active_total']}척 · 장기대기 {ct['long_pending_live']} · 표류 {ct['drift_live']}")
    parts.append("- 해석(추정): 개입 지점은 '완료 후 다음 정하기' + '장기대기 정리' 2곳.")
    return "\n".join(parts)


# ═══════════════════════════════════════════
#  md 렌더
# ═══════════════════════════════════════════
def render_counters_block(ct: dict) -> str:
    q = ct["queue_status"]
    lines = [
        "## 핵심 수치 카운터 (결정적 집계)",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| 총 관찰 | {ct['observations_total']}건 |",
        f"| GM 결정 이력 | {ct['gm_decisions']}건 |",
        f"| 표류(원장/라이브) | {ct['drift_events_ledger']} / {ct['drift_live']}건 |",
        f"| 활성 큐 | {ct['queue_active_total']}척 (PENDING {q.get('PENDING', 0)}·IN_PROGRESS {q.get('IN_PROGRESS', 0)}·DONE {q.get('DONE', 0)}) |",
        f"| 장기 대기(30일+) | {ct['long_pending_live']}척"
        + (f" (정박 선언 {ct.get('long_pending_parked_skipped', 0)}척은 제외 — 재개조건 대기·결재 완료)"
           if ct.get("long_pending_parked_skipped") else "")
        + " |",
        f"| 완료 아카이브 | {ct['queue_archive_total']}건 |",
        "",
        f"관찰 유형별: `{ct['observations_by_type']}`",
        "",
    ]
    return "\n".join(lines)


def render_source_honesty_block(ct: dict) -> str:
    """근거 정직 표기(결정적·계산 기반) — ship 10267.

    LLM 서술에 맡기지 않고 코드로 매일 강제 표기한다:
    관찰 원장이 실제로 무엇을 보고 있는지(세션에서 GM이 직접 남긴 신호 vs
    시스템이 자기 가동·큐 상태를 스스로 적은 미러링)를 매 실행 재계산해 밝힌다.
    """
    total = ct["observations_total"] or 1
    session_n = ct["session_signal_total"]
    machine_n = ct["machine_mirror_total"]
    pct = round(100 * session_n / total, 1)
    lines = [
        "## 근거 정직 표기 (기계 자기기록 vs GM 세션신호)",
        "",
        f"- 총 관찰 {ct['observations_total']}건 중 **GM이 세션에서 직접 남긴 신호는 {session_n}건({pct}%)** 뿐이다"
        f"(source에 `_session_` 포함 — 예 `cmo_session_2026-07-25`).",
        f"- 나머지 {machine_n}건은 시스템이 자기 가동(`gm_aide_auto_exec`)을 스스로 적거나,"
        " 큐 상태(`queue_active`/`queue_archive`)를 그대로 미러링한 기록이다 — GM 행동을 관찰한 것이 아니다.",
        "- **세션 교정을 원장에 남기는 경로는 있다**(2026-07-29 발효): 전 C-Level 이 작업 종료 직전 반드시"
        " 지나가는 관문 `clevel_post_action.py` 에 `--gm-signal \"<GM이 남긴 한 줄>\"` 을 붙이면 이 원장에"
        " 세션신호로 쌓인다(새 파일·새 감시기 0).",
        f"- 다만 **경로가 있다 ≠ 쓰인다.** 최근 7일 실제 사용 = **{ct.get('session_signal_recent7', 0)}건**,"
        f" 남긴 역할 = {', '.join(ct.get('session_signal_roles') or []) or '없음'}."
        " 붙이는 것이 아직 각 역할의 판단에 달려 있어, 안 붙인 세션의 교정은 대화에만 남아 사라진다(ship 10267).",
        "- 위 '선호·습관' 서술 중 이 정직 표기 이전 회차는 세션신호 비중이 낮았던 시점의 근거로 쓰였을 수 있다 — 날짜 표기 없는 해석은 재확인 전 잠정으로 읽는다.",
        "",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  GM 표면 점검 — 실제 렌더해서 3질문(읽히는가·사실인가·GM 일인가)을 잰다.
#  정적 grep이 아니라 Playwright 렌더를 쓴다 — 오늘 문제(핵심과제 칸 등)는 전부 JS 렌더 후에만
#  보였다(정적 HTML엔 안 보임). 저장소에 이미 설치된 Playwright 재사용(새 의존성 0).
# ═══════════════════════════════════════════
def _wait_until_rendered(page, root_sel: str, timeout_ms: int = 95000) -> bool:
    """화면이 '실제로 다 그려질 때까지' 기다린다. 다 그려졌다 = 「불러오는 중…」이 사라지고
    글자 수가 더 늘지 않는 상태.

    ★왜 필요한가(2026-08-01 시토 실측 · GM 지적 "내가 발견하는 게 아니라 시토가 찾아줘야").
      이 점검은 고정 3.5초만 기다린 뒤 쟀다. 그런데 GM 화면들은 저장소 파일을 여러 개
      받아 그리므로 데이터가 다 붙는 데 60~90초가 걸린다(자율현황 실측 — 사람이 렌더를
      기다려 재니 1,110자짜리 칸이 있었다). 그래서 점검은 아직 덜 그려진 화면을 쟀다.

    ★정정(2026-08-01 시토 · 같은 날 재측정).
      이 함수를 처음 넣을 때 근거로 'G1 최대 칸 2자 · 업무·결재 SSOT 최대 칸 0자'를 들며
      "탭 안쪽을 빈 화면으로 잰다"고 적었다. **틀렸다.** 실측하니 두 탭 다 정상으로 그려진다
      (G1 1,969자 · 업무·결재 SSOT 1,411자 · 클릭 후 2.5초면 완성, 75초까지 변화 0).
      0~2자는 `max_cell_len`(표의 td 최대 글자수)일 뿐이다 — G1 은 달력 칸이 1~2자라 2,
      업무·결재 SSOT 는 표가 아예 없고 div 피드라 0. **표 칸 글자수를 화면 생사 지표로
      읽은 것이 오독이었다.** 렌더 대기 자체는 그대로 값을 하지만(자율현황), 탭 화면이
      비어 있다는 진단은 취소한다.
      ↳ 그러면서 **진짜 결함은 못 잡고 있었다**: 업무·결재 SSOT 의 좌우 6개 피드 상자가
      라이브에서 통째로 비어 있다. 그래서 아래 `_empty_fill_slots()` 를 새로 넣었다.
    반환: True=다 그려짐 / False=시간 초과(그래도 잰다 — 대신 호출부가 판단할 수 있게 알린다).
    """
    prev, stable = -1, 0
    waited = 0
    while waited < timeout_ms:
        try:
            st = page.evaluate(
                """(sel) => {
                    const root = document.querySelector(sel) || document.body;
                    const t = root.innerText || '';
                    return { len: t.length, loading: (t.indexOf('불러오는 중') >= 0 || t.indexOf('집계 중') >= 0) };
                }""",
                root_sel,
            )
        except Exception:
            return False
        if st["len"] == prev and not st["loading"]:
            stable += 1
            if stable >= 2:          # 두 번 연속 그대로 = 다 그려졌다
                return True
        else:
            stable = 0
        prev = st["len"]
        page.wait_for_timeout(2500)
        waited += 2500
    return False


def _fill_slot_ids(url: str) -> list:
    """그 화면의 '채워질 예정' 칸 id 목록 — 원본 HTML 에서 「불러오는 중…」 자리표시자를 찾는다.

    자리표시자가 박혀 있다 = 만든 사람이 "여기는 데이터가 들어온다"고 선언한 곳이다.
    그러니 다 그려진 뒤에도 그 칸이 비어 있으면 **받아오기가 조용히 실패한 것**이다.
    (빈 div 를 전수로 훑지 않는 이유 = 여백용 빈 칸이 흔해 오탐 천지가 된다.)
    """
    import urllib.request, re as _re
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        return []
    out = []
    for m in _re.finditer(r'\bid="([A-Za-z0-9_\-]+)"', html):
        window = html[m.end():m.end() + 400]
        nxt = window.find(' id="')
        if nxt >= 0:
            window = window[:nxt]        # 다음 id 를 넘어가면 남의 칸이다
        if "불러오는 중" in window or "집계 중" in window:
            out.append(m.group(1))
    return out


def _empty_fill_slots(page, root_sel: str, slot_ids: list) -> list:
    """다 그려진 뒤에도 비어 있는 '채워질 예정' 칸 = 조용한 수집 실패.

    ★왜 있나(2026-08-01 시토 실측). 이 점검은 '글자가 너무 많은가'만 재고 **'있어야 할 것이
      아예 없는가'는 안 봤다.** 그래서 업무·결재 SSOT 의 좌우 6개 피드(업무 최근변동·마감임박·
      완료 / 결재 최근변동·대기·완료)가 라이브에서 통째로 빈 채 며칠을 지나도 매일 '기준 이내'가
      나왔다. 글자가 0 인 화면은 기준을 못 넘으니 영원히 통과한다 — 0 위장의 다른 얼굴이다.
    """
    if not slot_ids:
        return []
    return page.evaluate(
        """([sel, ids]) => {
            const root = document.querySelector(sel) || document.body;
            const out = [];
            for (const id of ids) {
                const el = document.getElementById(id);
                if (!el || !root.contains(el)) continue;   // 이 화면(탭) 밖은 안 본다
                if (el.offsetParent === null) continue;    // 숨은 칸은 뺀다
                if (el.closest('details:not([open])')) continue;  // 접어 둔 칸 = 안 보이는 게 정상
                if (((el.innerText || '').trim()).length === 0) out.push(id);
            }
            return out;
        }""",
        [root_sel, slot_ids],
    )


def _measure_table_balance(page, root_sel: str) -> list:
    """표의 칸 폭이 내용에 견줘 균형이 맞는지 잰다.

    ★왜 있나(2026-08-01 GM 지적): "이런 표에 대한 칸까지도 내가 다 짚는 건 아닌 것 같은데."
      맞다. 그날 GM 이 두 번 짚은 것이 둘 다 칸 폭이었다(상태칸이 좁아 줄이 길어짐 →
      '보내는 것'만 넓고 상태가 좁음). 사람 눈에는 바로 보이는데 점검기는 글자수만 재고
      **폭은 아예 안 봤다.** 그래서 매번 GM 이 감지기 노릇을 했다.

    판정: 칸마다 '글자밀도 = 평균 글자수 ÷ 렌더 폭(px)'을 낸다. 한 표 안에서 가장 빽빽한
      칸이 가장 헐거운 칸보다 _DENSITY_RATIO 배 넘게 빽빽하면 폭 배분이 틀어진 것으로 본다.
      폭 자체가 아니라 '내용 대비 폭'을 보므로 화면 크기와 무관하다.
    반환: [{table, dense_col, dense_ratio, sparse_col}] — 없으면 빈 목록.
    """
    try:
        return page.evaluate(
            """(sel) => {
                const root = document.querySelector(sel) || document.body;
                const RATIO = 3.0, MIN_ROWS = 3;
                const out = [];
                Array.from(root.querySelectorAll('table')).forEach((tb, ti) => {
                    const rows = Array.from(tb.rows).filter(r => r.cells.length > 1);
                    if (rows.length < MIN_ROWS) return;
                    const head = rows[0], body = rows.slice(1);
                    const n = head.cells.length;
                    const stat = [];
                    // 한 줄 높이 기준 = 그 표에서 가장 낮은 칸(=한 줄짜리)
                    let unit = Infinity;
                    body.forEach(r => Array.from(r.cells).forEach(c2 => {
                        const h = c2.getBoundingClientRect().height;
                        if (h > 8 && h < unit) unit = h;
                    }));
                    if (!isFinite(unit)) return;
                    for (let c = 0; c < n; c++) {
                        let chars = 0, cnt = 0, w = 0, hsum = 0;
                        body.forEach(r => {
                            const cell = r.cells[c];
                            if (!cell) return;
                            const rc = cell.getBoundingClientRect();
                            chars += (cell.innerText || '').length; cnt++;
                            hsum += rc.height;
                            w = Math.max(w, rc.width);
                        });
                        if (!cnt || w < 20) continue;
                        stat.push({ i: c, name: (head.cells[c] ? head.cells[c].innerText : '') .trim().slice(0, 14),
                                    density: (chars / cnt) / w, width: Math.round(w),
                                    lines: (hsum / cnt) / unit });
                    }
                    if (stat.length < 2) return;
                    stat.sort((a, b) => b.density - a.density);
                    const hi = stat[0], lo = stat[stat.length - 1];
                    /* 세 조건을 다 만족할 때만 잡는다 — 아무거나 잡으면 매일 헛경보가 뜨고
                       그러면 아무도 안 본다(2026-08-01 1차 가동에서 아이콘 칸 오탐 실측).
                        ①빽빽함 차이가 RATIO 배 넘고
                        ②빽빽한 칸이 실제로 **두 줄 이상 접히고**(안 접히면 좁아도 문제 아님)
                        ③그 칸이 그 표에서 **이미 가장 넓은 칸이 아니다**(제일 넓은데도 접힌다면
                          폭 배분이 아니라 내용을 줄이거나 접을 문제라 여기서 잡을 게 아니다).
                          ※처음엔 ③을 '가장 헐거운 칸과 비교'로 뒀다가 아이콘 칸(50px)이 기준이 돼
                            멀쩡한 표를 잡았다 — 비교 대상을 표의 최대 폭으로 바꿨다(2026-08-01 실측). */
                    const maxW = Math.max.apply(null, stat.map(s => s.width));
                    if (lo.density > 0 && hi.density / lo.density > RATIO
                        && hi.lines >= 1.8 && hi.width < maxW * 0.9) {
                        out.push({ table: ti, dense_col: hi.name, dense_w: hi.width,
                                   sparse_col: lo.name, sparse_w: lo.width,
                                   lines: Math.round(hi.lines * 10) / 10,
                                   ratio: Math.round((hi.density / lo.density) * 10) / 10 });
                    }
                });
                return out;
            }""",
            root_sel,
        )
    except Exception:
        return []


def _measure_root(page, root_sel: str) -> dict:
    """블록(section/.blk) 단위·칸(td/li 등) 단위 가시(innerText) 최대 글자수를 잰다.

    ★블록이 0개면 max_block_len 은 null 이다 — 페이지 전체 길이로 대신 채우지 않는다.
    (2026-07-30 실측: 5개 화면 중 3개가 section/.blk 마크업이 아예 없다. 옛 코드는 그때
    페이지 전체 글자수를 '블록 하나'로 착각해 블록 기준(5000자)과 견줬고, 그래서
    브로제이 업무분장을 '블록 6,239자 초과'로 잘못 신고했다 — 실제 그 화면의 최대 칸은
    146자였다. 없는 것은 없다고 적고, 못 잰 것은 못 쟀다고 적는다.)

    ★표 밖 글자도 잰다(2026-08-04 시토 · 배 280). 예전엔 `td, li` 계열만 칸으로 셌다.
    그런데 GM 화면 6개 중 둘(업무·결재 SSOT · 브로제이 업무분장)은 표가 아예 없고 인라인
    style 의 div 로만 그려져 **max_cell_len 이 늘 0** 이었고, 표가 있는 G1 도 달력 칸이
    1~2자라 사실상 같았다. 0 은 기준(300자)을 절대 못 넘으니 그 화면의 '읽히는가'는 매일
    자동 통과였다 — 잰 적이 없는데 통과로 보이는 0 위장이다. 블록도 마찬가지로 5개 화면이
    `section/.blk` 마크업이 없어 '못 잼'으로 매일 빠져 있었다.

    그래서 **'더 안 쪼개지는 글자 덩어리'**(자식 중 글자를 가진 요소가 없는 요소)를 같이 재되,
    줄바꿈 유무로 갈라 넣는다 — 한 줄짜리는 **칸**(300자 기준), 여러 줄짜리는 **블록**(5000자
    기준). 이 구분이 없으면 브로제이의 828자 안내문(골프장 운영 규정 · 줄바꿈으로 짜인 문서)이
    '칸 하나가 828자, 압축 필요'로 잘못 신고된다 — 2026-07-30 에 페이지 전체를 블록 하나로
    착각해 잘못 신고했던 것과 정확히 같은 부류의 오진이다.
    실측(2026-08-04 · 6개 화면): 칸 0→61(업무·결재 SSOT) · 2→96(G1) · 328→422(운영 가이드,
    이미 신고 중이던 건이 더 정확해짐) · 월간운영계획 240 불변. 새 오탐 0.
    """
    return page.evaluate(
        """(sel) => {
            const root = document.querySelector(sel) || document.body;
            const mx = (arr) => arr.length ? Math.max(...arr) : 0;
            const lenOf = (els) => els.map(c => (c.innerText || '').length).filter(n => n > 0);

            const tableMax = mx(lenOf(Array.from(root.querySelectorAll('td, .r-title, .broj-list li, li'))));

            // 더 안 쪼개지는 글자 덩어리 = 자식 중 글자를 가진 요소가 없는 요소(=겉 상자 제외)
            const leaves = Array.from(root.querySelectorAll('div, span, p, dd, figcaption')).filter(el => {
                if (!((el.innerText || '').trim())) return false;
                if (el.offsetParent === null) return false;              // 숨은 칸
                if (el.closest('details:not([open])')) return false;     // 접어 둔 칸
                if (el.closest('[role=dialog], .modal, .gdoc-modal')) return false;  // 눌러야 열리는 안내 상자
                return !Array.from(el.children).some(c => ((c.innerText || '').trim()));
            }).map(el => (el.innerText || '').trim());

            const leafCellMax  = mx(leaves.filter(t => t.indexOf('\\n') < 0).map(t => t.length));
            const leafBlockLens = leaves.filter(t => t.indexOf('\\n') >= 0).map(t => t.length);

            const blocks = Array.from(root.querySelectorAll('section, .blk'));
            const blockLens = lenOf(blocks).concat(leafBlockLens);

            const cellMax = Math.max(tableMax, leafCellMax);
            return {
                whole_len: (root.innerText||'').length,
                max_block_len: blockLens.length ? Math.max(...blockLens) : null,
                max_cell_len: cellMax,
                cell_basis: cellMax === 0 ? 'none' : (tableMax >= leafCellMax ? 'table' : 'leaf'),
                block_count: blocks.length + leafBlockLens.length,
            };
        }""",
        root_sel,
    )


def _git(*args: str, timeout: int = 30) -> str | None:
    import subprocess
    try:
        out = subprocess.run(["git", *args], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception:
        return None


def _git_commit_age_days(rel_path: str) -> int | None:
    """GM 화면이 읽는 값이 며칠째 그대로인가.

    ★기준은 로컬 HEAD 가 아니라 **origin/master** 다. 라이브 화면은 GitHub 에서 받아 가므로,
    로컬에서 아무리 갱신·커밋해도 올라가지 않았으면 GM 이 보는 값은 옛것이다. 2026-07-31 이 함수를
    처음 넣을 때 HEAD 로 쟀다가 바로 그 함정을 밟았다 — 그날 로컬은 전부 '어제 커밋'으로 신선했는데
    origin 은 8시간 넘게 멈춰 있었고, 점검은 '기준 이내'를 냈다. 못 재면 None(추측하지 않는다).
    """
    stamp = _git("log", "-1", "--format=%cI", "origin/master", "--", rel_path)
    if not stamp:
        return None
    try:
        return (TODAY - datetime.fromisoformat(stamp).date()).days
    except Exception:
        return None


def _push_gap() -> dict | None:
    """올리지 못한 것이 쌓여 GM 화면이 멈춰 있지 않은가(wellperion-boot §2-1 #8 작업트리 고립).

    읽기 전용만 한다 — fetch(원격 참조 갱신)까지이고 작업트리·브랜치는 건드리지 않는다.
    """
    _git("fetch", "origin", "master", timeout=90)  # best-effort · 실패해도 옛 참조로 잰다
    ahead = _git("rev-list", "--count", "origin/master..HEAD")
    behind = _git("rev-list", "--count", "HEAD..origin/master")
    stamp = _git("log", "-1", "--format=%cI", "origin/master")
    if not ahead or not ahead.isdigit() or not stamp:
        return None
    try:
        origin_age_h = (datetime.now().astimezone() - datetime.fromisoformat(stamp)).total_seconds() / 3600
    except Exception:
        return None
    if int(ahead) > 0 and origin_age_h >= GM_SURFACE_PUSH_STALE_HOURS:
        return {"kind": "push_stalled", "ahead": int(ahead),
                "behind": int(behind) if (behind or "").isdigit() else None,
                "origin_age_h": round(origin_age_h, 1),
                "limit_h": GM_SURFACE_PUSH_STALE_HOURS}
    return None


def _open_ship_count(rel_path: str) -> int | None:
    p = ROOT / rel_path
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    items = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    return sum(1 for it in items if isinstance(it, dict) and it.get("status") in ("PENDING", "IN_PROGRESS"))


GM_DUP_MIN_BYTES = 1024 * 1024      # 1MB 넘는 것만 본다(작은 파일은 중복이어도 무해·스캔만 느려진다)
GM_DUP_WARN_MB = 100                # 낭비가 이만큼 넘으면 표면화


def check_duplicate_assets() -> dict | None:
    """같은 내용을 두 벌 이상 들고 있는 큰 파일 — 쌓이는 것을 **쌓인 뒤에 찾지 않게** 매일 잰다.

    ★2026-07-31 시토(GM '불필요·중복된 데이터가 쌓이지 않도록') — 그날 실측에서 시설 사진이
      두 폴더에 통째로 두 벌(42개·574MB) 있었고, 아무도 몇 달째 몰랐다. 정리는 했지만 정리보다
      중요한 건 **다시 쌓이지 않는 것**이다. 새 감시기를 만들지 않고 이미 매일 06:30 도는
      이 점검에 얹는다(약속 L21).
    ▸판정은 sha256 완전일치만 — '비슷한 파일'은 사람이 판단할 일이라 건드리지 않는다.
    ▸1MB 이하는 세지 않는다(무해하고 스캔만 느려진다).
    ▸경보가 아니라 표면화다. 지우는 것은 사람·담당이 참조를 확인한 뒤에 한다.
    """
    import hashlib
    import subprocess
    try:
        r = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120)
        if r.returncode != 0:
            return None
        # ponytail(2026-08-05 시토·가벼움 작업): 진짜 중복이면 파일 크기도 같다 —
        # 크기부터 stat 로 묶고, 크기가 겹치는 후보만 sha256 read+hash 한다.
        # 실측(오늘 저장소): 1MB↑ 272개·1.3GB 전량 해시 → 크기충돌 85개·249MB 만 해시(바이트 기준 81%↓).
        # 결과는 100% 동일(크기가 다르면 내용도 다르므로 후보에서 뺄 근거가 확실함) — 회귀 0, 검증 스크립트로 대조 완료.
        by_size: dict[int, list[str]] = {}
        for rel in (r.stdout or "").splitlines():
            p = ROOT / rel
            try:
                if not p.is_file():
                    continue
                sz = p.stat().st_size
                if sz <= GM_DUP_MIN_BYTES:
                    continue
            except Exception:
                continue
            by_size.setdefault(sz, []).append(rel)
        seen: dict[str, list[str]] = {}
        waste = 0
        for sz, rels in by_size.items():
            if len(rels) < 2:
                continue
            for rel in rels:
                p = ROOT / rel
                try:
                    digest = hashlib.sha256(p.read_bytes()).hexdigest()
                except Exception:
                    continue
                if digest in seen:
                    waste += sz
                seen.setdefault(digest, []).append(rel)
        groups = [v for v in seen.values() if len(v) > 1]
        mb = round(waste / 1024 / 1024)
        if mb < GM_DUP_WARN_MB:
            return None
        top = sorted(groups, key=len, reverse=True)[:3]
        return {"kind": "duplicate_assets", "groups": len(groups), "waste_mb": mb,
                "examples": [v[0] for v in top]}
    except Exception:
        return None


def run_fact_check() -> list:
    """3질문 중 '사실인가' — 화면이 읽는 원천이 ①굳어 있지 않은가 ②사본끼리 어긋나지 않는가.

    두 가지만 잰다(잴 수 있는 것만):
      · source_stale  — 매일 갱신돼야 할 원천이 커밋 기준 GM_SURFACE_STALE_DAYS 일 이상 그대로
      · mirror_drift  — 화면이 읽는 사본과 원천의 열린 배 수가 다름(INC-007 부류)
    GAS·시트에서 오는 값은 여기서 못 본다 — fact_unmeasured 로 남겨 통과로 위장하지 않는다.
    """
    findings: list = []
    unmeasured: list = []
    gap = _push_gap()
    if gap:
        findings.append(gap)
    dup = check_duplicate_assets()
    if dup:
        findings.append(dup)
    for label, spec in GM_SURFACE_SOURCES.items():
        for rel, cadence in spec.get("repo", []):
            if cadence != "daily":
                continue
            age = _git_commit_age_days(rel)
            if age is None:
                unmeasured.append(f"{label}: {rel}(커밋 이력 못 읽음)")
            elif age >= GM_SURFACE_STALE_DAYS:
                findings.append({"kind": "source_stale", "page": label, "source": rel,
                                 "days": age, "limit": GM_SURFACE_STALE_DAYS})
        parity = spec.get("parity")
        if parity:
            src_n, mir_n = _open_ship_count(parity[0]), _open_ship_count(parity[1])
            if src_n is None or mir_n is None:
                unmeasured.append(f"{label}: 사본 대조 불가({parity[0]} 또는 {parity[1]} 못 읽음)")
            elif src_n != mir_n:
                findings.append({"kind": "mirror_drift", "page": label,
                                 "source": parity[0], "source_n": src_n,
                                 "mirror": parity[1], "mirror_n": mir_n})
        for ext in spec.get("external", []):
            unmeasured.append(f"{label}: {ext} — 저장소 밖(측정 못 함)")
    findings.extend(_dead_links())
    findings.extend(_stale_progress())
    findings.append({"kind": "fact_unmeasured", "items": unmeasured})
    return findings


# ── 실무진에게 보내는 링크가 살아 있는가 (2026-07-31 웰리) ──────────────────
# 2026-07-31, 밤 알림에 넣은 링크가 없는 페이지(404)였다 — 내가 파일명을 잘못 적었고,
# GM 이 "혼란만 가중된다"고 짚어서야 확인했다. 링크는 넣기 전에 열어보면 되는 일이고,
# 사람이 매번 기억할 일이 아니다. 하루 한 번 기계가 대신 연다.
# ▸대상 = 실무진·GM 에게 실제로 보내는 링크만(전수 크롤 아님 — 그건 소음이다).
# ▸새 스크립트·새 예약 0(약속 L21): 이미 06:30 에 도는 이 파일의 표면 점검에 얹는다.
GM_LINKS = [
    ("전사 일정(법정점검 회신)", "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%A0%84%EC%82%AC_%EC%9D%BC%EC%A0%95.html"),
    ("지원부 체계(점검 제출)", "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%A7%80%EC%9B%90%EB%B6%80%20%EC%B2%B4%EA%B3%84.html"),
    ("시설부 체계", "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%8B%9C%EC%84%A4%EB%B6%80%20%EC%B2%B4%EA%B3%84.html"),
    ("운영부 체계", "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%9A%B4%EC%98%81%EB%B6%80%20%EC%B2%B4%EA%B3%84.html"),
    ("주차관리부 체계", "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%A3%BC%EC%B0%A8%EA%B4%80%EB%A6%AC%EB%B6%80%20%EC%B2%B4%EA%B3%84.html"),
    ("종합접수처 현황", "https://wellperion-cao.github.io/wellperion-automation/coo/reception/%EC%A2%85%ED%95%A9%EC%A0%91%EC%88%98%EC%B2%98_%ED%98%84%ED%99%A9.html"),
    ("재등록 대시보드", "https://wellperion-cao.github.io/wellperion-automation/cpo/member/renewal.html"),
    ("멤버십 회원관리", "https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html"),
]


# ── 월간 진척이 굳어 있지 않은가 (2026-07-31 GM 지시) ──────────────────────
# GM: "시우가 할 수 있게 해줘. 그리고 그 부분을 웰리가 체크 관리할 수 있어야겠지?"
# 월간운영계획의 진척률(%)은 사람이 손으로 다시 세는 값이다. 다시 센 날짜는 각 항목의
# honesty.at 에 이미 남고 있다 — 그걸 읽어 **며칠째 안 세었는지**만 본다(새 필드 0).
# ▸왜 필요한가: 7월에 근거 없이 '80%'로 굳어 있다가 33%로 정정된 일이 있었다. 굳은 숫자는
#   틀린 숫자가 되고, 굳었다는 사실 자체가 아무 화면에도 안 보였다.
# ▸갱신은 시우(4부서 소관)가, 굳었는지 보는 것은 웰리가 — 역할이 갈린다.
MONTHLY_PLAN = STATUS_DIR / "monthly_ops_plan.json"
PROGRESS_STALE_DAYS = 7


def _stale_progress() -> list:
    try:
        data = json.loads(MONTHLY_PLAN.read_text(encoding="utf-8"))
    except Exception:
        return []
    key = TODAY.strftime("%Y-%m")
    month = (data.get("months") or {}).get(key)
    if not isinstance(month, dict):
        return []
    stale = []
    for o in month.get("objectives") or []:
        if not isinstance(o, dict):
            continue
        if str(o.get("status") or "") == "완료":
            continue                       # 끝난 것은 다시 셀 필요가 없다
        at = str(((o.get("honesty") or {}).get("at")) or "")[:10]
        try:
            days = (TODAY - datetime.fromisoformat(at).date()).days
        except Exception:
            days = None
        if days is None or days >= PROGRESS_STALE_DAYS:
            stale.append({"title": str(o.get("title") or "")[:40],
                          "owner": str(o.get("owner") or ""), "days": days})
    if not stale:
        return []
    stale.sort(key=lambda x: -(x["days"] or 999))
    return [{"kind": "stale_progress", "month": key, "count": len(stale),
             "worst": stale[0], "items": stale[:5]}]


def _dead_links() -> list:
    import urllib.request
    out = []
    for label, url in GM_LINKS:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=20) as r:
                code = r.status
        except Exception as e:
            code = getattr(e, "code", None) or 0
        if code != 200:
            out.append({"kind": "dead_link", "page": label, "url": url, "code": code})
    return out


def run_gm_surface_check() -> tuple[list, bool]:
    """GM 표면 3질문 점검 — ①읽히는가(칸·블록 글자수) ②사실인가(원천 갱신정지·사본 어긋남)
    ③GM 일인가(G1 audience 비율).
    반환: (findings 리스트, ok=점검 자체가 정상 수행됐는가).
    """
    findings: list = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return [{"kind": "check_unavailable", "detail": f"Playwright 임포트 실패: {e}"}], False

    ok = True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # gm1_auth=1 — G1(김남욱 GM 전용) 세션 게이트 사전 통과(비번 커튼, GM1_PW SSOT는
            # wellperion_guide(main).html 안·이 스크립트가 값을 복제하지 않는다 — 세션키만 심는다).
            ctx = browser.new_context()
            ctx.add_init_script("try{sessionStorage.setItem('gm1_auth','1')}catch(e){}")
            for spec in GM_SURFACE_PAGES:
                label = spec["label"]
                try:
                    page = ctx.new_page()
                    page.goto(spec["url"], wait_until="load", timeout=45000)
                    page.wait_for_timeout(2000)  # 비동기 fetch 렌더 대기(오늘 문제 전부 이 타이밍에만 보였음)
                    if spec["mode"] == "anchor":
                        page.evaluate(
                            "(id) => { const el = document.querySelector('[data-id=\"'+id+'\"]'); if(el) el.click(); }",
                            spec["anchor"],
                        )
                        page.wait_for_timeout(2000)
                        root_sel = "#" + spec["anchor"]
                    else:
                        page.wait_for_timeout(1500)
                        root_sel = "body"
                    # 다 안 그려진 채 시간이 끝나면 그것 자체가 결함이다(2026-08-01 실측:
                    # S2 매트릭스가 GAS 경합으로 30초 넘게 '불러오는 중'에 머물렀는데, 그 칸엔
                    # 글자가 있으니 빈칸 검사도 글자수 기준도 전부 통과했다 — 아무도 못 잡았다).
                    if not _wait_until_rendered(page, root_sel):
                        findings.append({"kind": "render_timeout", "page": label})
                    m = _measure_root(page, root_sel)
                    table_bal = _measure_table_balance(page, root_sel)   # 창 닫기 전에 잰다
                    empty_slots = _empty_fill_slots(page, root_sel, _fill_slot_ids(spec["url"]))
                    page.close()

                    if m["whole_len"] == 0:
                        findings.append({"kind": "page_render_fail", "page": label,
                                          "detail": "렌더 후 가시 텍스트 0자 — 게이트·로드 실패 의심"})
                        ok = False
                        continue
                    if empty_slots:
                        findings.append({
                            "kind": "empty_fill_slot", "page": label,
                            "slots": empty_slots,
                            "detail": (f"데이터가 들어와야 할 칸 {len(empty_slots)}개가 다 그려진 뒤에도 "
                                       f"비어 있다 — 받아오기가 조용히 실패한 것 ({', '.join(empty_slots[:6])})"),
                        })
                    if m["max_cell_len"] > GM_SURFACE_CELL_MAX:
                        findings.append({"kind": "cell_too_long", "page": label,
                                          "value": m["max_cell_len"], "limit": GM_SURFACE_CELL_MAX})
                    # 표 칸 폭 균형(2026-08-01 신설) — GM 이 두 번 짚은 것이 둘 다 칸 폭이었다.
                    for tb in table_bal:
                        findings.append({
                            "kind": "table_columns_unbalanced", "page": label,
                            "detail": (f"「{tb['dense_col']}」 칸이 평균 {tb.get('lines','?')}줄로 접힌다 — "
                                       f"「{tb['sparse_col']}」 보다 {tb['ratio']}배 빽빽한데 폭은 "
                                       f"{tb['dense_w']}px vs {tb['sparse_w']}px. 내용 많은 칸에 폭을 더 줄 것"),
                        })
                    if m["max_block_len"] is None:
                        # 블록 마크업이 없는 화면 = 블록 기준으로 잴 수 없다. 통과로 위장하지 않고
                        # '못 쟀다'를 남긴다(칸 기준은 위에서 그대로 잰다).
                        findings.append({"kind": "block_unmeasurable", "page": label,
                                          "whole": m["whole_len"], "max_cell": m["max_cell_len"],
                                          "cell_basis": m.get("cell_basis", "table")})
                    elif m["max_block_len"] > GM_SURFACE_BLOCK_MAX:
                        findings.append({"kind": "block_too_long", "page": label,
                                          "value": m["max_block_len"], "limit": GM_SURFACE_BLOCK_MAX})
                except Exception as e:
                    findings.append({"kind": "page_render_fail", "page": label, "detail": str(e)[:200]})
                    ok = False
            browser.close()
    except Exception as e:
        return [{"kind": "check_crash", "detail": str(e)[:200]}], False

    # ── "GM 일인가" — G1 항로가 AI 살림에 밀렸는지(렌더 아닌 큐 원천 직접 계산 — 더 정확) ──
    try:
        active = read_json_array(QUEUE_ACTIVE)
        open_items = [it for it in active if it.get("status") in ("PENDING", "IN_PROGRESS")]
        ai_n = sum(1 for it in open_items if it.get("audience") == "ai")
        office_n = sum(1 for it in open_items if it.get("audience") == "office")
        if ai_n > office_n:
            findings.append({"kind": "ai_over_office", "ai": ai_n, "office": office_n})
    except Exception as e:
        findings.append({"kind": "audience_check_fail", "detail": str(e)[:200]})

    # ── "사실인가" — 원천 갱신정지·사본 어긋남(2026-07-31 이행) ──
    try:
        findings.extend(run_fact_check())
    except Exception as e:
        findings.append({"kind": "fact_check_fail", "detail": str(e)[:200]})

    return findings, ok


# 위반이 아니라 '측정 한계'로 분류하는 종류 — 발견 건수에 넣지 않되 숨기지도 않는다.
NON_VIOLATION_KINDS = ("scope_note", "block_unmeasurable", "fact_unmeasured")


def log_surface_check(findings: list, ok: bool) -> dict:
    real_findings = [f for f in findings if f.get("kind") not in NON_VIOLATION_KINDS]
    if not ok:
        summary = "점검 실패(렌더 불가) — 별도 확인 필요"
    elif not real_findings:
        summary = "없음 — 점검한 화면 전부 기준 이내"
    else:
        summary = f"{len(real_findings)}건 발견"
    rec = {
        "observed_at": now_str(),
        "source": "gm_surface_scan",
        "signal_type": "surface_check",
        "summary": summary,
        "evidence": findings,
        "pattern_hint": "3질문: 읽히는가(칸·블록 글자수)·사실인가(원천 갱신정지·사본 어긋남)·GM 일인가(G1 audience 비율)",
        "dedup_key": f"surfacecheck|{today_str()}",
    }
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 표면점검 원장 기록 실패: {e}")
    return rec


def render_gm_surface_block(rec: dict) -> str:
    evidence = rec.get("evidence") or []
    findings = [f for f in evidence if f.get("kind") not in NON_VIOLATION_KINDS]
    unmeasured = [f for f in evidence if f.get("kind") == "block_unmeasurable"]
    lines = [
        "## 🔍 GM 표면 점검 (오늘 · 읽히는가 · 사실인가 · GM 일인가)",
        "",
        f"대상: {', '.join(s['label'] for s in GM_SURFACE_PAGES)}",
        "",
    ]
    if not findings:
        lines.append(f"**없음** — 점검한 화면 전부 기준 이내(칸 ≤{GM_SURFACE_CELL_MAX}자·블록 ≤{GM_SURFACE_BLOCK_MAX}자"
                     f"·원천 {GM_SURFACE_STALE_DAYS}일 내 갱신·화면 사본 일치·AI배<실무배).")
    else:
        for f in findings:
            kind = f.get("kind")
            if kind == "render_timeout":
                lines.append(f"- 🔴 **{f['page']}** 가 시간 안에 다 안 그려진다 — 아직 「불러오는 중」인 칸이 남아 있음(느린 받아오기)")
            elif kind == "empty_fill_slot":
                lines.append(f"- 🔴 **{f['page']}** {f.get('detail','')}")
            elif kind == "cell_too_long":
                lines.append(f"- ⚠️ **{f['page']}** 칸 하나가 {f['value']}자(기준 {f['limit']}자 초과) — 압축 필요")
            elif kind == "block_too_long":
                lines.append(f"- ⚠️ **{f['page']}** 블록이 {f['value']}자(기준 {f['limit']}자 초과) — 압축 필요")
            elif kind == "ai_over_office":
                lines.append(f"- ⚠️ G1 항로: AI배 {f['ai']}척 > 실무배 {f['office']}척 — GM 화면이 AI 살림에 밀림")
            elif kind == "page_render_fail":
                lines.append(f"- 🔧 **{f['page']}** 렌더 실패(점검 못함): {f.get('detail','')}")
            elif kind == "check_unavailable" or kind == "check_crash":
                lines.append(f"- 🔧 점검 자체 불가: {f.get('detail','')}")
            elif kind == "audience_check_fail":
                lines.append(f"- 🔧 GM 일인가 판정 실패: {f.get('detail','')}")
            elif kind == "source_stale":
                lines.append(f"- ⚠️ **{f['page']}** 가 읽는 값이 {f['days']}일째 그대로다"
                             f"(`{f['source']}` · 기준 {f['limit']}일) — 화면 숫자가 굳었을 수 있음")
            elif kind == "mirror_drift":
                lines.append(f"- ⚠️ **{f['page']}** 화면이 읽는 사본과 원천이 다르다 — "
                             f"원천 {f['source_n']}척 vs 화면 사본 {f['mirror_n']}척")
            elif kind == "push_stalled":
                behind = f" · 반대로 못 받은 것 {f['behind']}건" if f.get("behind") else ""
                lines.append(f"- ⚠️ **GM 화면이 멈춰 있다** — 올리지 못한 작업 {f['ahead']}건, "
                             f"마지막으로 올라간 지 {f['origin_age_h']}시간{behind}. "
                             f"라이브 페이지·G1 은 그 시점 값을 보여준다")
            elif kind == "stale_progress":
                w = f.get("worst") or {}
                d = w.get("days")
                lines.append(f"- ⚠️ **{f['month']} 월간계획 진척**이 {f['count']}건 오래 안 세어졌다"
                             f"(가장 오래된 것 {d if d is not None else '기록 없음'}일 · {w.get('title','')})"
                             " — 갱신=시우, 확인=웰리")
            elif kind == "dead_link":
                lines.append(f"- ⚠️ **{f['page']}** 링크가 열리지 않는다(응답 {f['code']}) — "
                             "실무진 알림에 이 주소가 들어간다")
            elif kind == "fact_check_fail":
                lines.append(f"- 🔧 사실인가 점검 실패: {f.get('detail','')}")
            else:
                lines.append(f"- {kind}: {f}")
    lines.append("")
    if unmeasured:
        _BASIS_KO = {"table": "표·목록 칸", "leaf": "글자 칸(표 없음)", "none": "칸 없음"}
        detail = " · ".join(
            f"{f['page']}(전체 {f['whole']}자·최대 {_BASIS_KO.get(f.get('cell_basis','table'),'칸')} {f['max_cell']}자)"
            for f in unmeasured
        )
        lines.append(f"*블록 기준으로 못 잰 화면: {detail} — 그 화면엔 여러 줄짜리 덩어리가 없어"
                     " 칸 기준만 적용했다(위반 아님·측정 한계). 칸은 표 칸과 한 줄짜리 글자 칸 중 큰 쪽이다.*")
    unmeasured_fact = next((f for f in evidence if f.get("kind") == "fact_unmeasured"), None)
    if unmeasured_fact and unmeasured_fact.get("items"):
        lines.append("<details><summary>'사실인가' — 못 잰 것 "
                     f"{len(unmeasured_fact['items'])}건 (대부분 저장소 밖 구글 시트·GAS 값)</summary>")
        lines.append("")
        for it in unmeasured_fact["items"]:
            lines.append(f"- {it}")
        lines.append("")
        lines.append("</details>")
    lines.append(f"*측정: {rec.get('observed_at')} · 근거 = `{LEDGER.name}` 최신 surface_check 항목*")
    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  북극성 지표 — "GM이 하루에 개입한 일 중 GM만 할 수 있었던 일의 비율"
#  자동집계는 원장의 GM 세션신호가 아직 얇아 불가(비율은 render 시점에 실측해 표기 — 하드코딩 금지).
#  이번 회차는 웰리가 하루 끝에 채워 넣는 "칸"까지만 만든다. 새 원장 0 — 기존 LEDGER 재사용.
# ═══════════════════════════════════════════
def record_northstar_ratio(total: int, gm_only: int, note: str = "") -> dict:
    """정직 조건: 분모를 숨기지 않는다 — GM이 그날 짚은 것은 전부 센다."""
    pct = round(gm_only / total * 100) if total else 0
    rec = {
        "observed_at": now_str(),
        "source": "welly_daily_northstar",
        "signal_type": "gm_only_ratio",
        "summary": f"GM 개입 {total}건 중 GM 전용 {gm_only}건 ({pct}%)" + (f" — {note}" if note else ""),
        "evidence": {"total": total, "gm_only": gm_only, "pct": pct, "note": note},
        "pattern_hint": "분모=그날 GM이 짚은 것 전부(숨김 금지) · 자동집계 전까지 웰리 수기 기록 · ship 10267과 연동",
        "dedup_key": f"northstar|{today_str()}",
    }
    try:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[북극성 기록] {rec['summary']}")
    except Exception as e:
        print(f"[WARN] 북극성 기록 실패: {e}")
    return rec


def render_northstar_block(ledger: list) -> str:
    entries = [r for r in ledger if r.get("source") == "welly_daily_northstar"]
    # 자동집계 가능 여부의 근거를 실측해 적는다(하드코딩된 옛 비율 금지).
    sess_n = sum(1 for r in ledger if "_session_" in str(r.get("source") or ""))
    sess_pct = round(100 * sess_n / len(ledger), 1) if ledger else 0.0
    header = "## 🌟 북극성 — GM 전용 개입 비율\n"
    cmd = ('다음 기록: `python scripts/gm_profile_builder.py --record-northstar '
           '<총건수> <GM전용건수> "<한줄메모>"`')
    if not entries:
        return (f"{header}\n**미기록** — 오늘 GM이 개입한 일 중 몇 건이 GM만 할 수 있었는지 적어 주세요.\n\n{cmd}\n")
    latest = entries[-1]
    is_today = str(latest.get("observed_at", "")).startswith(today_str())
    badge = "오늘" if is_today else f"최근({str(latest.get('observed_at',''))[:10]})"
    return (
        f"{header}\n**{badge}: {latest['summary']}**\n\n"
        "*정직 조건: 분모는 그날 GM이 짚은 것 전부(좋아 보이게 줄이지 않음). "
        f"자동집계는 아직 불가 — 원장의 GM 세션신호가 {sess_n}건({sess_pct}%)뿐이다(ship 10267 진행 중).*\n\n"
        f"{cmd}\n"
    )


def build_markdown(narrative: str, counters: dict, generated_by: str,
                    surface_rec: dict | None = None, ledger_with_surface: list | None = None) -> str:
    header = (
        "# GM 프로필 (웰리 학습 · GM 보좌 자율화 phase 1)\n\n"
        f"- 생성: {now_str()}\n"
        f"- 생성 두뇌: {generated_by}\n"
        f"- 근거: `status/gm_observation_ledger.jsonl` + `status/_queue*.json`\n"
        "- 성격: 사람이 읽는 서술 프로필(일일 갱신·멱등). 라이브 부작용 0.\n"
        "- 배: CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237) · 스펙: `.omc/specs/deep-interview-gm-aide-autonomy.md`\n\n"
        "---\n\n"
    )
    parts = [header, render_counters_block(counters), "\n---\n\n",
             render_source_honesty_block(counters), "\n---\n\n"]
    if surface_rec is not None:
        parts += [render_gm_surface_block(surface_rec), "\n---\n\n"]
    if ledger_with_surface is not None:
        parts += [render_northstar_block(ledger_with_surface), "\n---\n\n"]
    parts += [narrative.rstrip(), "\n"]
    return "".join(parts)


# ═══════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════
def run(stdout_only: bool = False, skip_surface_check: bool = False) -> str:
    print(f"[시작] GM 프로필 생성기 — {now_str()}")
    ledger = read_jsonl(LEDGER)
    active = read_json_array(QUEUE_ACTIVE)
    archive = read_json_array(QUEUE_ARCHIVE)
    print(f"[1/3] 입력 로드 — 관찰 {len(ledger)}건 · 활성큐 {len(active)}척 · 아카이브 {len(archive)}건")

    counters = compute_counters(ledger, active, archive)

    print("[1.5/3] GM 표면 점검(렌더 · 2026-07-29 GM go)...")
    if skip_surface_check:
        surface_rec = {"observed_at": now_str(), "summary": "생략(--skip-surface-check)", "evidence": []}
    else:
        findings, ok = run_gm_surface_check()
        surface_rec = log_surface_check(findings, ok)
        ledger = ledger + [surface_rec]  # 이번 실행분도 북극성 블록·다음 실행 근거에 즉시 반영
        print(f"  → {surface_rec['summary']}")

    print("[2/3] 웰리 두뇌(claude CLI · model_router 폴백) 호출...")
    narrative, used_model = brain_claude_cli(counters, ledger)
    if narrative is None:
        generated_by = "규칙폴백"
        narrative = brain_fallback(counters)
        print("  → 규칙기반 서술 폴백(claude CLI 미가용 — 정상 강등)")
    else:
        generated_by = f"ClaudeCLI({used_model})"
        print(f"  → ClaudeCLI 서술 생성(model={used_model}, {len(narrative)}자)")

    md = build_markdown(narrative, counters, generated_by, surface_rec, ledger)

    print(f"\n[요약] 수치 카운터")
    print(f"  · 총 관찰 {counters['observations_total']} · 결정 {counters['gm_decisions']}")
    print(f"  · 표류 라이브 {counters['drift_live']} · 장기대기 {counters['long_pending_live']} · 활성 {counters['queue_active_total']}")

    if stdout_only:
        print("\n[--stdout-only] 파일 기록 생략 (미리보기)\n")
        print(md[:800])
        return md

    PROFILE_MD.write_text(md, encoding="utf-8")
    print(f"\n[3/3] 기록 완료: {PROFILE_MD}")
    print(f"[완료] ({now_str()})")
    return md


def selftest_cells() -> int:
    """`_measure_root` 칸 기준 자체 점검 — 라이브 접속 없이 세 조각만 그려 확인한다.
    ①표 칸이 더 길면 표 칸을 낸다(회귀 0) ②표가 없으면 0 이 아니라 글자 칸을 낸다
    ③칸을 감싸는 겉 상자는 안 센다(가장 안쪽 글자 칸만 — 안 그러면 페이지 전체가 한 칸이 된다).
    """
    from playwright.sync_api import sync_playwright
    cases = [
        ("표 칸이 더 김", "<table><tr><td>가나다라마바사</td></tr></table><div>짧다</div>", "table", 7),
        ("표 없음(div 피드)",
         "<div><div><span>대기</span><span>업무제목이다</span></div></div>", "leaf", 6),
        ("겉 상자 제외", "<div><p>바깥이더길어보이는겉상자</p></div>", "leaf", 12),
    ]
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        for name, html, want_basis, want_max in cases:
            pg.set_content(f"<body>{html}</body>")
            m = _measure_root(pg, "body")
            if m["cell_basis"] != want_basis or m["max_cell_len"] != want_max:
                fails.append(f"{name}: basis={m['cell_basis']}(기대 {want_basis}) "
                             f"max_cell={m['max_cell_len']}(기대 {want_max})")
        b.close()
    for f in fails:
        print("  ❌", f)
    print("칸 기준 자체점검:", "통과" if not fails else f"실패 {len(fails)}건")
    return 1 if fails else 0


def main():
    parser = argparse.ArgumentParser(
        description="GM 프로필 생성기 phase1 — 관찰 원장+큐 → gm_profile.md(수치+LLM 서술 하이브리드)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--stdout-only", action="store_true", dest="stdout_only",
                        help="파일 기록 없이 콘솔 미리보기만(드라이)")
    parser.add_argument("--skip-surface-check", action="store_true", dest="skip_surface_check",
                        help="GM 표면 렌더 점검 생략(디버그·속도용 — 정식 실행은 기본대로 항상 켜둘 것)")
    parser.add_argument("--record-northstar", nargs="+", metavar=("TOTAL", "GM_ONLY"),
                        help="북극성 지표 수기 기록: <총건수> <GM전용건수> [\"한줄메모\"] — 그 자리에서 기록만 하고 종료")
    parser.add_argument("--selftest-cells", action="store_true", dest="selftest_cells",
                        help="칸 기준(표 있음/없음) 자체 점검만 하고 종료 — 라이브 접속 없음")
    args = parser.parse_args()
    if args.selftest_cells:
        raise SystemExit(selftest_cells())
    if args.record_northstar:
        vals = args.record_northstar
        if len(vals) < 2:
            parser.error("--record-northstar 는 최소 <총건수> <GM전용건수> 2개가 필요합니다")
        total, gm_only = int(vals[0]), int(vals[1])
        note = " ".join(vals[2:]) if len(vals) > 2 else ""
        record_northstar_ratio(total, gm_only, note)
        return
    run(stdout_only=args.stdout_only, skip_surface_check=args.skip_surface_check)


if __name__ == "__main__":
    main()
