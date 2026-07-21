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

섹션 5개, 이상 있는 섹션만 노출(전부 정상이면 무발신):
  §1 🔇 침묵 모듈   — module_silence_detector.scan_registry() 재사용(등록부 전수)
  §2 📦 GAS 버전    — gas_version_monitor.collect() 재사용, 임계(>=180)만
  §3 🩹 자동화 건강 — status/erp_status.json 읽기 전용(재수집 금지).
                      systems/bridges state=="이상" + automation_health
                      items state in (실패·미실행·불명)만 요약.
  §4 🧹 페이지 위생 — 오늘자 status/page_hygiene_proposal_{date}.md 존재 시
                      미조치 항목 건수 한 줄(없으면 스킵).
  §5 🔐 시트 계약   — [전사 편입·CPO] cpo_sheet_contract 상태파일 읽기 전용.
                      미해소·미승인(accepted=false) 위반 + 연속조회실패(>=3일)만.
                      재점검·네트워크 호출 금지(07:50 소스 모듈이 이미 대조·기록).
                      accepted(시포가 승인해 침묵처리)는 재노출 안 함(계약 존중).

발신: notify.telegram_send.send() → 자동화현황방(기존 채널 재사용).
게이트: SELF_HEALTH_WATCHDOG_LIVE 환경변수(기본 OFF)일 때만 --live 가 실발신.
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
import gas_version_monitor as _gasmon  # noqa: E402
from module_heartbeat import record_heartbeat  # noqa: E402
# [전사 무결성 표준 편입 2026-07-22] 시포 시트 계약 점검기(07:50)의 상태파일·임계·로더를
# 재사용해 STATE_PATH/threshold 드리프트 없이 읽기만 한다(재점검·네트워크 호출 없음).
from collectors import cpo_sheet_contract as _sheet  # noqa: E402

KST = timezone(timedelta(hours=9))  # 이 저장소 관행(module_silence_detector.py 상단 주석과 동일)

PROJECT_ROOT = Path(_PROJECT_ROOT)
STATUS_DIR = PROJECT_ROOT / "status"
ERP_STATUS_PATH = STATUS_DIR / "erp_status.json"
LOG_PATH = STATUS_DIR / "self_health_watchdog_log.jsonl"
ROOMS_PATH = STATUS_DIR / "telegram_rooms.json"
BOT_ROOM = "자동화현황방"  # 기존 채널 재사용(새 봇·새 방 금지)
LINK = "https://wellperion-cao.github.io/wellperion-automation/자율현황.html#layer-automation"

MODULE_ID = "cto-self-health-watchdog"
LIVE_ENV_VAR = "SELF_HEALTH_WATCHDOG_LIVE"

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


# ── §2 📦 GAS 버전 (gas_version_monitor 재사용) ──────────────────────────────
def build_section_gas_version():
    """임계(>=180) 프로젝트만 → 라인 리스트. 없으면 None."""
    results = _gasmon.collect()
    alerts = [r for r in results
              if r.get("version_count") is not None
              and r["version_count"] >= _gasmon._ALERT_THRESHOLD]
    if not alerts:
        return None
    lines = [f"📦 GAS 버전 임박 {len(alerts)}건(하드리밋 {_gasmon._HARD_LIMIT})"]
    for r in alerts:
        lines.append(f"  · {r['project']} {r['version_count']}/{_gasmon._HARD_LIMIT}")
    return lines


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

    lines = [f"🩹 자동화 건강 이상 {len(issues)}건 (요약: {data.get('summary', '')})"]
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


# ── 조립·발신 ─────────────────────────────────────────────────────────────
def build_digest(now=None):
    """4섹션 조립 → (text|None, sections:dict). 전부 정상이면 text=None."""
    now = _now_utc(now)
    sections = {
        "silence": build_section_silence(now=now),
        "gas_version": build_section_gas_version(),
        "erp_status": build_section_erp_status(),
        "page_hygiene": build_section_page_hygiene(now=now),
        "sheet_contract": build_section_sheet_contract(),
    }
    active = [v for v in sections.values() if v]
    if not active:
        return None, sections

    lines = [f"🩺 ERP 자가건강 — {now.astimezone(KST).strftime('%Y-%m-%d')}"]
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


def _live_gate_open() -> bool:
    """SELF_HEALTH_WATCHDOG_LIVE 환경변수 게이트(기본 OFF)."""
    return os.environ.get(LIVE_ENV_VAR, "").strip().lower() in ("1", "true", "on", "yes")


def run_watchdog(*, dry_run=True, now=None, log_path=LOG_PATH, rooms_path=ROOMS_PATH,
                  sender=None):
    """전체 조립 → 이상 있으면 하루 1통(멱등) 발송/드라이런. 반환: 결과 dict."""
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

    if not _live_gate_open():
        _append_log({"date": date_str, "sent": False, "reason": "live_gate_closed"}, log_path=log_path)
        record_heartbeat(MODULE_ID, detail="이상 감지했으나 LIVE 게이트 OFF — 발신 생략")
        return {"date": date_str, "sections": sections, "action": "skip",
                "reason": f"{LIVE_ENV_VAR} 미설정 — 실발신 게이트 닫힘", "text": text}

    if _already_sent_today(date_str, log_path=log_path):
        return {"date": date_str, "sections": sections, "action": "skip",
                "reason": "dedup(오늘 이미 발송)", "text": text}

    rooms = _load_json(rooms_path, {})
    chat_id = rooms.get(BOT_ROOM)
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
                     help=f"실제 발송 시도(기본은 드라이런). {LIVE_ENV_VAR} 환경변수도 켜져 있어야 실발신")
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
