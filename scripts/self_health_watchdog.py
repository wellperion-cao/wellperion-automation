# -*- coding: utf-8 -*-
"""
self_health_watchdog.py — 자가건강 감시 통합 하네스 (2026-07-21 CTO).
─────────────────────────────────────────────────────────────────────────────
문제: 자가건강 감시 모듈 4개(module_silence_detector·gas_version_monitor·
erp_status_publisher·weekly_page_hygiene)가 각자 흩어진 채널·흩어진 시각에
발신한다 — GM 입장에서는 같은 성격("시스템이 스스로를 얼마나 잘 지켜보고
있는가")의 알림이 여러 통으로 쪼개져 도착한다.

이 하네스는 read-only 애그리게이터다 — 4개 모듈의 기존 산출물/함수를
그대로 재사용해(재수집·복붙 금지) 하루 1통 "🩺 ERP 자가건강" 디제스트로
묶는다. 4개 소스 모듈의 동작은 전혀 건드리지 않는다.

2026-07-22(배9420 #5·웰리 제기 배9421) 이 하네스를 CTO 도메인 4종에서
**전사 무결성 감시 표준**으로 확장한다 — 등록부 전체에서 "정상=침묵, 이상만
지문 dedup 후 요약"의 동일 감시 패턴을 쓰는 타 도메인 모듈을 read-only로 편입해
GM이 하루 1통 전사 이상요약 한 판으로 보게 한다. 1차 편입 = 시포(CPO)
cpo-sheet-contract-check(매일 07:50). 소스 모듈은 존치·회귀 0(그 모듈은 자기
방·자기 시각에 그대로 가동, 하네스는 산출물만 읽는다).

2026-07-22(배9420 확장·GM 승인) §7·§8 추가 — 흩어진 텔레그램/연동 헬스체크를
함수 재사용으로 흡수(탐지 로직 삭제 없음, telegram_health_check.py·
integration_health.py 는 그대로 존치·13시 자기 알림도 불변). 이 하네스가 이미
cto-automation-health 의 §자가건강(build_digest 재사용)으로 09:10 하루 1통에
실리므로, §7·§8 추가만으로 그 1통 안에 텔레그램 채널·연동 다리 상태까지
자동 포함된다(추가 발신 배선 불필요). ★단 봇 폴링 하트비트 등 즉시성 중요한
경보는 telegram_health_check.py 자체의 13시 OWNER 즉시경보 경로를 그대로
남긴다(약화 금지) — §7 은 그 경로를 대체하지 않고 일일 요약 가시성만 더한다.

섹션 7개, 이상 있는 섹션만 노출(전부 정상이면 무발신):
  §1 🔇 침묵 모듈   — module_silence_detector.scan_registry() 재사용(등록부 전수)
  §2 📦 GAS 버전    — 삭제됨(2026-08-03). 게이트 OFF·예약 0건·하트비트 07-25 정지로
                      13일간 경보 0건이었다 — telegram_health_check._check_gas_versions
                      (예약 가동 중)로 원복하고 여기 사본은 지웠다(약속 L21).
  §3 🩹 자동화 건강 — status/erp_status.json 읽기 전용(재수집 금지).
                      systems/bridges state=="이상" + automation_health
                      items state in (실패·미실행·불명)만 요약.
  §4 🧹 페이지 위생 — 오늘자 status/page_hygiene_proposal_{date}.md 존재 시
                      미조치 항목 건수 한 줄(없으면 스킵).
  §5 🔐 시트 계약   — [전사 편입·CPO] cpo_sheet_contract 상태파일 읽기 전용.
                      미해소·미승인(accepted=false) 위반 + 연속조회실패(>=3일)만.
                      재점검·네트워크 호출 금지(07:50 소스 모듈이 이미 대조·기록).
                      accepted(시포가 승인해 침묵처리)는 재노출 안 함(계약 존중).
  §6 🔁 결정 정합   — decision_replay_log + ssot/decision_contracts.json 읽기
                      전용. 가드 우회 재발송(leaked)·미보증 모듈만 요약(surface-only).
  §7 📡 텔레그램 채널 — telegram_health_check.py 의 점검 함수 재사용(봇 생존·방
                      멤버십·발송 리컨실·GAS 진단·폴링 하트비트). 그 스크립트의
                      13시 OWNER 즉시경보는 그대로 유지(긴급 경로 보존).
  §8 🌉 연동 다리    — integration_health.check_bridges() 재사용(재점검 없음),
                      ok=False 인 다리만 요약.

★2026-07-31 GM 결정 — **이 스크립트의 단독 발신(--live)은 은퇴했다. 다시 켜지 마라.**
  2026-07-22 에 같은 내용이 cto-automation-health 의 09:10 다이제스트로 합쳐졌고
  (collectors/cto_automation_health.py 가 아래 build_digest() 를 그대로 재사용한다),
  13:00 단독 발신은 그때부터 같은 방에 하루 두 통을 보내는 중복이라 꺼졌다.
  그런데 '꺼둔 채' 두었더니 열흘 동안 "검증 끝나고 GM go 기다리는 기능"처럼 보였다 —
  기다리던 게 아니라 이미 대체된 것이었다. GM: "일주일 이상 작동이 안 된 거면 무의미·
  무분별·중복 셋 중 하나다. 혼란스럽지 않게 폐기해라."
  → 호출부(scripts/telegram_health_check.bat)의 주석 처리된 실행 줄을 지웠다.
  **살아 있는 것은 build_digest() 뿐이고, 그건 09:10 다이제스트가 쓴다.** 자가건강을 더
  드러내야 하면 새 발신을 만들지 말고 그 09:10 다이제스트를 고친다(약속 L21).

발신: notify.telegram_send.send() → 자동화현황방(기존 채널 재사용).
게이트: SELF_HEALTH_WATCHDOG_LIVE 환경변수(기본 OFF) — 위 은퇴로 상시 OFF. 수동 점검용 잔존.
멱등: 날짜 dedup(하루 최대 1통) — status/self_health_watchdog_log.jsonl.
자가증명: 매 실행(라이브) module_heartbeat.record_heartbeat("cto-self-health-watchdog", ...).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import module_silence_detector as _silence  # noqa: E402
from module_heartbeat import record_heartbeat  # noqa: E402
# [전사 무결성 표준 편입 2026-07-22] 시포 시트 계약 점검기(07:50)의 상태파일·임계·로더를
# 재사용해 STATE_PATH/threshold 드리프트 없이 읽기만 한다(재점검·네트워크 호출 없음).
from collectors import cpo_sheet_contract as _sheet  # noqa: E402
# [결정 정합 게이트 §6 편입 2026-07-22] 가드가 남긴 '옛것 재생 차단' 신호(공용 로그)만
# 읽는다 — 재점검·차단 없음(surface-only, §3 erp_status·§5 sheet_contract 와 동일 read-only).
import decision_replay_log as _replay  # noqa: E402
# [흩어진 헬스 흡수 §7·§8 2026-07-22 배9420 확장] 두 스크립트의 기존 점검 함수를
# import 만 해서 재사용한다 — 탐지 로직 복붙 금지, 소스 스크립트는 손대지 않음(그
# 스크립트들의 자체 실행·자체 발신 경로도 그대로 존치).
import telegram_health_check as _tghealth  # noqa: E402
import integration_health as _bridges  # noqa: E402

KST = timezone(timedelta(hours=9))  # 이 저장소 관행(module_silence_detector.py 상단 주석과 동일)

PROJECT_ROOT = Path(_PROJECT_ROOT)
STATUS_DIR = PROJECT_ROOT / "status"
ERP_STATUS_PATH = STATUS_DIR / "erp_status.json"
LOG_PATH = STATUS_DIR / "self_health_watchdog_log.jsonl"
DECISION_CONTRACTS_PATH = PROJECT_ROOT / "ssot" / "decision_contracts.json"
ROOMS_PATH = STATUS_DIR / "telegram_rooms.json"
BOT_ROOM = "자동화현황방"  # 기존 채널 재사용(새 봇·새 방 금지)
LINK = "https://wellperion-cao.github.io/wellperion-automation/자율현황.html#layer-automation"

MODULE_ID = "cto-self-health-watchdog"
# 2026-08-08 시토: SELF_HEALTH_WATCHDOG_LIVE 환경변수 게이트를 없앴다. 아무도 그 변수를
# 켜지 않아 이 감시기는 2026-07-21 수동 실행 1회 말고는 한 번도 발신한 적이 없고, 그 사이
# 침묵 모듈·시트 계약 위반이 매일 쌓여도 아무에게도 안 갔다. 게이트를 OFF로 남겨 두면
# 죽은 코드가 된다(약속 L21) — 실발신 여부는 호출부의 dry_run 인자 하나로만 정한다.

# automation_health.items 중 "이상"으로 간주할 상태(정상/대기/정상(건너뜀)=healthy — 소스 로직과 동일 기준)
_AUTOMATION_BAD_STATES = ("실패", "미실행", "불명")


def _now_utc(now=None):
    if now is not None:
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


# ── §1 🔇 침묵 모듈 (module_silence_detector 재사용) ─────────────────────────
def build_section_silence(now=None):
    """침묵 판정분만 → 라인 리스트. 없으면 None."""
    scan = _silence.scan_registry(root=PROJECT_ROOT, now=now)
    silent = _silence.silent_modules(scan)
    if not silent:
        return None
    lines = [f"🔇 침묵 모듈 {len(silent)}건(예상 주기 초과)"]
    for m in sorted(silent, key=lambda x: -(x.get("silence_hours") or 0)):
        days = (m.get("silence_hours") or 0) / 24
        lines.append(f"  · {m['id']} — {days:.1f}일째 조용함(허용 {m.get('cadence')}주기)")
    return lines


# ── §2 📦 GAS 버전 — 삭제됨(2026-08-03·CTO) ──────────────────────────────────
# 2026-07-21 에 telegram_health_check 의 GAS 버전경보를 "여기 일일 디제스트로 이관"했는데,
# 이 워치독은 게이트(SELF_HEALTH_WATCHDOG_LIVE) 상시 OFF · 예약작업 0건 · 하트비트 07-25 정지로
# **한 번도 라이브로 켜진 적이 없다.** 결과: 07-21~08-03 13일간 GAS 버전경보 0건, 그 사이
# funnel-v2 가 190→197(🔴)에 닿은 것을 아무도 몰랐다. 이관이 아니라 삭제였다.
# → 경보는 원래 자리(telegram_health_check._check_gas_versions, 예약 가동 중)로 원복하고
#   여기 사본은 지운다. 남겨두면 나중에 이 워치독을 켤 때 **경보가 두 곳에서 두 번 나간다**
#   (약속 L21 — 관문 하나 · 꺼둔 것은 남기지 않는다).


# ── §3 🩹 자동화 건강 (status/erp_status.json 읽기 전용) ─────────────────────
def build_section_erp_status(path: Path = ERP_STATUS_PATH):
    """erp_status.json 읽어 이상 항목만 → 라인 리스트. 파일 없음/파싱 실패/전부 정상 → None(fail-soft)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    issues = []
    for s in (data.get("systems") or []) + (data.get("bridges") or []):
        if isinstance(s, dict) and s.get("state") == "이상":
            issues.append(f"  · {s.get('name', '?')}: {s.get('detail', '')}")

    ah = data.get("automation_health") or {}
    for it in ah.get("items", []) or []:
        if isinstance(it, dict) and it.get("state") in _AUTOMATION_BAD_STATES:
            issues.append(f"  · {it.get('name', '?')} — {it.get('state')}")

    if not issues:
        return None

    lines = [f"🔧 자동화 이상 {len(issues)}건 (요약: {data.get('summary', '')})"]
    lines.extend(issues[:10])
    if len(issues) > 10:
        lines.append(f"  … 외 {len(issues) - 10}건")
    return lines


# ── §4 🧹 페이지 위생 (오늘자 제안서 존재 시만) ───────────────────────────────
_CATEGORY_ITEM_RE = re.compile(r"^- \[", re.MULTILINE)


def build_section_page_hygiene(now=None):
    """오늘자 status/page_hygiene_proposal_{date}.md 미조치 건수 한 줄. 파일 없으면 None."""
    now = _now_utc(now)
    date_str = now.astimezone(KST).strftime("%Y%m%d")
    path = STATUS_DIR / f"page_hygiene_proposal_{date_str}.md"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    n = len(_CATEGORY_ITEM_RE.findall(text))
    if n <= 0:
        return None
    return [f"🧹 페이지 위생 — 오늘자 제안서 미조치 {n}건 ({path.name})"]


# ── §5 🔐 시트 계약 무결성 (전사 편입·CPO cpo_sheet_contract 상태 읽기 전용) ──────
def build_section_sheet_contract():
    """시포 시트 칸 계약 점검기(매일 07:50)의 상태파일을 읽어 미해소·미승인 위반 + 연속
    조회실패만 → 라인 리스트. 전부 정상/파일 없음 → None(fail-soft).

    read-only 원칙: 소스 모듈(scripts/collectors/cpo_sheet_contract.py)이 이미 07:50에
    라이브 시트를 대조·기록한다. 여기서는 그 산출물(status/sheet_contract_state.json)만
    읽는다 — 재점검·네트워크 호출 금지(§3 erp_status·§4 page_hygiene 와 동일 패턴).
    accepted=true(시포가 승인해 침묵처리한 위반)는 재노출하지 않는다 — 소스 모듈의
    dedup·accept 계약을 그대로 존중(전사 표준의 핵심: 소유주가 끈 것은 다시 울리지 않음)."""
    try:
        state = _sheet.load_state()
    except Exception:
        return None
    if not isinstance(state, dict):
        return None

    fps = state.get("fingerprints") or {}
    unresolved = [rec for rec in fps.values()
                  if isinstance(rec, dict) and not rec.get("accepted")]
    streaks = state.get("network_fail_streak") or {}
    stuck = [(k, n) for k, n in streaks.items()
             if isinstance(n, int) and n >= _sheet._NETWORK_FAIL_ALERT_STREAK]

    if not unresolved and not stuck:
        return None

    lines = []
    if unresolved:
        lines.append(f"🔐 시트 계약 위반 {len(unresolved)}건(미해소·미승인 · 시포/07:50)")
        for rec in unresolved[:6]:
            lines.append(f"  · {rec.get('detail', '?')}")
        if len(unresolved) > 6:
            lines.append(f"  … 외 {len(unresolved) - 6}건")
    if stuck:
        thr = _sheet._NETWORK_FAIL_ALERT_STREAK
        lines.append(f"🔐 시트 조회 연속실패 {len(stuck)}건(>={thr}일)")
        for k, n in stuck:
            lines.append(f"  · {k} — {n}일 연속")
    return lines


# ── §6 🔁 결정 정합 (decision_replay_log + decision_contracts 읽기 전용) ────────
def _load_decision_contracts(path: Path = DECISION_CONTRACTS_PATH):
    """계약 파일 로드 → contracts 리스트. 파일 없음/파싱 실패 → [](fail-soft)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    contracts = data.get("contracts")
    return contracts if isinstance(contracts, list) else []


def build_section_decision_consistency(now=None):
    """결정 정합 이상만 → 라인 리스트. 전부 정상(차단 0·미보증 0) → None(무노출).

    스펙 §4·§6. surface-only — 실제 차단은 각 모듈 패턴 K/N 가드가 이미 최전단에서
    수행하고, 여기서는 그 신호(status/decision_replay_log.jsonl)와 계약(ssot/
    decision_contracts.json)만 읽는다(재점검·네트워크·차단 없음).
      (a) 오늘 '옛것 재생 차단' N건 — 가드가 실제로 막은 재선정/재발송(정상 작동 증거).
          그중 action='leaked'(가드 우회 재발송 흔적)는 별도 강조(회귀 대상, §6.3).
      (b) 미보증 모듈 M건 — 계약상 결정소멸형인데 status in (unguarded, proposed).
    """
    now = _now_utc(now)
    recs = _replay.read_today(now=now)
    blocked = [r for r in recs if r.get("action") == "blocked"]
    leaked = [r for r in recs if r.get("action") == "leaked"]

    contracts = _load_decision_contracts()
    unguarded = [c for c in contracts
                 if isinstance(c, dict) and c.get("status") in ("unguarded", "proposed")]

    if not blocked and not leaked and not unguarded:
        return None

    lines = []
    if leaked:
        lines.append(f"🔁 결정 정합 — ⚠️ 가드 우회 재발송(leaked) {len(leaked)}건 (회귀 대상)")
        for r in leaked[:6]:
            lines.append(f"  · {r.get('module_id', '?')} — {r.get('subject', '')}: {r.get('detail', '')}")
    if blocked:
        lines.append(f"🔁 옛것 재생 차단 {len(blocked)}건(가드 정상 작동 · 결정 미박제 흔적)")
        for r in blocked[:6]:
            lines.append(f"  · {r.get('module_id', '?')} — {r.get('subject', '')}: {r.get('detail', '')}")
        if len(blocked) > 6:
            lines.append(f"  … 외 {len(blocked) - 6}건")
    if unguarded:
        lines.append(f"🔁 결정소멸형 미보증 모듈 {len(unguarded)}건(계약상 가드 보류·로드맵 잔여)")
        for c in unguarded[:6]:
            lines.append(f"  · {c.get('module_id', '?')} — status={c.get('status')}"
                         + (f" · {c.get('domain_review')}" if c.get("domain_review") else ""))
    return lines


# ── §7 📡 텔레그램 채널 (telegram_health_check.py 점검 함수 재사용) ───────────────
def build_section_telegram():
    """telegram_health_check.py 의 기존 점검 함수(봇 생존·방 멤버십·발송 리컨실·
    GAS 진단·폴링 하트비트)를 그대로 호출(재수집 금지)해 문제만 → 라인 리스트.
    전부 정상 → None. read-only: 이 함수는 발신하지 않는다 — telegram_health_check.py
    자신의 13시 OWNER 즉시경보(★긴급 경로, 특히 폴링 하트비트 죽음)는 그대로
    별도 존치된다. 이 섹션은 그 즉시경보를 대체하지 않고 일일 요약 가시성만 더한다.
    네트워크 예외는 fail-soft(다른 섹션을 막지 않음)."""
    try:
        env = _tghealth._load_env(_tghealth._ENV_PATH)
        token = env.get('TELEGRAM_BOT_TOKEN', '')
        issues: list[str] = []
        bot_id = None
        if not token:
            issues.append("TELEGRAM_BOT_TOKEN 미설정")
        else:
            alive, bot_id, detail = _tghealth._get_bot_info(token)
            if not alive:
                issues.append(f"🔴 봇 생존 확인 실패: {detail}")
        if token and bot_id is not None:
            issues.extend(_tghealth._check_rooms(token, bot_id, _tghealth._default_rooms(env)))
        issues.extend(_tghealth._check_log_failures())
        issues.extend(_tghealth._check_gas_diag())
        issues.extend(_tghealth._check_heartbeat())  # now 생략 — 로컬 naive datetime 비교(원본과 동일)
    except Exception as e:
        return [f"📡 텔레그램 채널 점검 실패({type(e).__name__}: {str(e)[:80]})"]
    if not issues:
        return None
    lines = [f"📡 텔레그램 채널 이상 {len(issues)}건"
             f"(봇생존·방멤버십·발송리컨실·GAS진단·폴링 · telegram_health_check 재사용)"]
    lines.extend(f"  · {i}" for i in issues[:10])
    if len(issues) > 10:
        lines.append(f"  … 외 {len(issues) - 10}건")
    return lines


# ── §8 🌉 연동 다리 (integration_health.check_bridges() 재사용) ─────────────────
def build_section_bridges():
    """integration_health.check_bridges() 재사용(재점검 없음) — ok=False 인
    다리만 → 라인 리스트. 전부 정상 → None. check_bridges() 는 이미 fail-soft
    (개별 점검 예외로 전체가 죽지 않음) — 여기서도 호출 자체 예외만 추가 방어."""
    try:
        rows = _bridges.check_bridges()
    except Exception as e:
        return [f"🌉 연동 다리 점검 실패({type(e).__name__}: {str(e)[:80]})"]
    bad = [(name, detail) for name, ok, detail in rows if not ok]
    if not bad:
        return None
    lines = [f"🌉 연동 다리 이상 {len(bad)}/{len(rows)}건(integration_health 재사용)"]
    for name, detail in bad[:10]:
        lines.append(f"  · {name}: {detail}")
    if len(bad) > 10:
        lines.append(f"  … 외 {len(bad) - 10}건")
    return lines


# ── 조립·발신 ─────────────────────────────────────────────────────────────
def build_digest(now=None):
    """섹션 조립 → (text|None, sections:dict). 전부 정상이면 text=None."""
    now = _now_utc(now)
    sections = {
        "silence": build_section_silence(now=now),
        # gas_version 섹션 삭제(2026-08-03) — 경보 정본 = telegram_health_check (§2 주석 참조)
        "erp_status": build_section_erp_status(),
        "page_hygiene": build_section_page_hygiene(now=now),
        "sheet_contract": build_section_sheet_contract(),
        "decision_consistency": build_section_decision_consistency(now=now),
        "telegram": build_section_telegram(),
        "bridges": build_section_bridges(),
    }
    active = [v for v in sections.values() if v]
    if not active:
        return None, sections

    # 제목 문구는 GM 확정(2026-08-08) — '건강'은 회원 건강·시설 점검과 겹쳐 헷갈린다.
    # 이 알림은 이상이 있을 때만 오므로 제목이 그대로 뜻을 말하게 한다.
    lines = [f"🚨 ERP 이상 신호 — {now.astimezone(KST).strftime('%Y-%m-%d')}"]
    for sec in active:
        lines.append("")
        lines.extend(sec)
    lines.append("")
    lines.append(LINK)
    return "\n".join(lines), sections


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _already_sent_today(date_str, log_path=LOG_PATH):
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("date") == date_str and rec.get("sent") is True:
                    return True
    except Exception:
        return False
    return False


def _already_logged_today(date_str, log_path=LOG_PATH):
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if json.loads(line).get("date") == date_str:
                    return True
    except Exception:
        return False
    return False


def _append_log(record, log_path=LOG_PATH):
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def run_watchdog(*, dry_run=True, now=None, log_path=LOG_PATH, rooms_path=ROOMS_PATH,
                  sender=None, notify=True):
    """전체 조립 → 이상 있으면 하루 1통(멱등) 발송/드라이런. 반환: 결과 dict.

    notify=False — [2026-08-29 GM 승인] 이상 전문은 09:10 자동화 다이제스트
    (cto_automation_health._self_health_rows 전체 줄)가 싣는다. 같은 방에 2분 뒤
    두 번째 통을 보내지 않도록, 기록·자가증명(하트비트)만 남기고 발신은 건너뛴다."""
    now = _now_utc(now)
    date_str = now.astimezone(KST).strftime("%Y-%m-%d")

    text, sections = build_digest(now=now)

    if text is None:
        if not dry_run and not _already_logged_today(date_str, log_path=log_path):
            _append_log({"date": date_str, "sent": False, "reason": "no_op"}, log_path=log_path)
            record_heartbeat(MODULE_ID, detail="전부 정상 — 무발신")
        return {"date": date_str, "sections": sections, "action": "no_op",
                "reason": "전부 정상 — 발신 없음", "text": None}

    if dry_run:
        return {"date": date_str, "sections": sections, "action": "dry-run", "text": text}

    if not notify:
        if not _already_logged_today(date_str, log_path=log_path):
            _append_log({"date": date_str, "sent": False, "reason": "absorbed_0910_digest"},
                        log_path=log_path)
        record_heartbeat(MODULE_ID, detail="이상 있음 — 09:10 다이제스트에 흡수(단독 발신 안 함)")
        return {"date": date_str, "sections": sections, "action": "absorbed", "text": text}

    if _already_sent_today(date_str, log_path=log_path):
        return {"date": date_str, "sections": sections, "action": "skip",
                "reason": "dedup(오늘 이미 발송)", "text": text}

    rooms = _load_json(rooms_path, {})
    # 방 이름 해소는 정본 함수 하나만 쓴다(약속 L01·L21). 직접 rooms.get() 을 하면 2026-08-12
    # 방 개명("자동화현황방"→"AI관리") 뒤 _legacy_aliases 폴백을 못 타 조용히 안 나간다 —
    # 실제로 08-13·08-14 이틀 연속 room_unresolved 로 무발신이었다(2026-08-15 자가점검 실측).
    from module_reporter import resolve_chat_id  # noqa: PLC0415
    chat_id = resolve_chat_id(BOT_ROOM, rooms)
    if chat_id is None:
        _append_log({"date": date_str, "sent": False, "reason": "room_unresolved"}, log_path=log_path)
        return {"date": date_str, "sections": sections, "action": "skip",
                "reason": "room_unresolved", "text": text}

    if sender is None:
        from notify.telegram_send import send as sender  # noqa: PLC0415

    ok = bool(sender(chat_id, text))
    _append_log({"date": date_str, "sent": ok, "chat_id": chat_id}, log_path=log_path)
    if ok:
        record_heartbeat(MODULE_ID, detail="이상 감지 디제스트 발송")
    return {"date": date_str, "sections": sections,
            "action": "sent" if ok else "send_failed", "text": text}


def main(argv=None):
    ap = argparse.ArgumentParser(description="자가건강 감시 통합 하네스(2026-07-21)")
    ap.add_argument("--live", action="store_true",
                     help="실제 발송 시도(기본은 드라이런)")
    ap.add_argument("--dry-run", action="store_true",
                     help="발신 없이 디제스트 텍스트만 stdout 출력(기본값과 동일 — 명시용)")
    ap.add_argument("--scan-only", action="store_true",
                     help="4섹션 조립 결과만 표 형태로 출력, 발신 로직 미실행")
    args = ap.parse_args(argv)

    if args.scan_only:
        text, sections = build_digest()
        for name, sec in sections.items():
            status = "이상" if sec else "정상"
            print(f"[{name:>12}] {status}")
            if sec:
                for line in sec:
                    print(f"    {line}")
        return 0

    out = run_watchdog(dry_run=not args.live)
    print(f"[{out['action']}] date={out['date']}")
    if out.get("text"):
        print("--- 디제스트 미리보기 ---")
        print(out["text"])
    else:
        print("전부 정상 — 무발신")
    if out.get("reason"):
        print(f"사유: {out['reason']}")
    return 0


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
