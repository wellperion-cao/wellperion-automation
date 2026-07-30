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
        "repo": [("status/erp_status.json", "daily"),
                 ("status/gm_observation_ledger.jsonl", "daily"),
                 ("status/module_silence_snapshot.json", "daily")],
        "manual": ["status/module_registry.json", "status/notify_registry.json", "status/audit_registry.json"],
        "external": ["회원 이탈 GAS(cpo_churn_stats)"],
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
def _measure_root(page, root_sel: str) -> dict:
    """블록(section/.blk) 단위·칸(td/li 등) 단위 가시(innerText) 최대 글자수를 잰다.

    ★블록이 0개면 max_block_len 은 null 이다 — 페이지 전체 길이로 대신 채우지 않는다.
    (2026-07-30 실측: 5개 화면 중 3개가 section/.blk 마크업이 아예 없다. 옛 코드는 그때
    페이지 전체 글자수를 '블록 하나'로 착각해 블록 기준(5000자)과 견줬고, 그래서
    브로제이 업무분장을 '블록 6,239자 초과'로 잘못 신고했다 — 실제 그 화면의 최대 칸은
    146자였다. 없는 것은 없다고 적고, 못 잰 것은 못 쟀다고 적는다.)
    """
    return page.evaluate(
        """(sel) => {
            const root = document.querySelector(sel) || document.body;
            const blocks = Array.from(root.querySelectorAll('section, .blk'));
            const cells = Array.from(root.querySelectorAll('td, .r-title, .broj-list li, li'));
            const blockLens = blocks.map(b => (b.innerText||'').length).filter(n => n > 0);
            const cellLens = cells.map(c => (c.innerText||'').length).filter(n => n > 0);
            const wholeLen = (root.innerText||'').length;
            return {
                whole_len: wholeLen,
                max_block_len: blockLens.length ? Math.max(...blockLens) : null,
                max_cell_len: cellLens.length ? Math.max(...cellLens) : 0,
                block_count: blocks.length,
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
    findings.append({"kind": "fact_unmeasured", "items": unmeasured})
    return findings


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
                    m = _measure_root(page, root_sel)
                    page.close()

                    if m["whole_len"] == 0:
                        findings.append({"kind": "page_render_fail", "page": label,
                                          "detail": "렌더 후 가시 텍스트 0자 — 게이트·로드 실패 의심"})
                        ok = False
                        continue
                    if m["max_cell_len"] > GM_SURFACE_CELL_MAX:
                        findings.append({"kind": "cell_too_long", "page": label,
                                          "value": m["max_cell_len"], "limit": GM_SURFACE_CELL_MAX})
                    if m["max_block_len"] is None:
                        # 블록 마크업이 없는 화면 = 블록 기준으로 잴 수 없다. 통과로 위장하지 않고
                        # '못 쟀다'를 남긴다(칸 기준은 위에서 그대로 잰다).
                        findings.append({"kind": "block_unmeasurable", "page": label,
                                          "whole": m["whole_len"], "max_cell": m["max_cell_len"]})
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
            if kind == "cell_too_long":
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
            elif kind == "fact_check_fail":
                lines.append(f"- 🔧 사실인가 점검 실패: {f.get('detail','')}")
            else:
                lines.append(f"- {kind}: {f}")
    lines.append("")
    if unmeasured:
        detail = " · ".join(f"{f['page']}(전체 {f['whole']}자·최대 칸 {f['max_cell']}자)" for f in unmeasured)
        lines.append(f"*블록 기준으로 못 잰 화면: {detail} — 그 화면엔 블록 마크업(section/.blk)이 없어 칸 기준만 적용했다(위반 아님·측정 한계).*")
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
    args = parser.parse_args()
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
