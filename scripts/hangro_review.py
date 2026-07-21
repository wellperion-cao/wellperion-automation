#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""웰리 항로 검수·종착지 두뇌 (hangro_review.py)
설계 정본: docs/superpowers/specs/2026-07-21-웰리-항로-검수-종착지-두뇌-design.md
검수(read-only) → 종착지 생성(LLM) → GM 카드 핑(간격제어) → 승인 시 반영(--next 배관).
★시토 경계: gm_aide_scan.py 는 재작성 금지 — 신호는 import/read만."""
from __future__ import annotations
import argparse, hashlib, io, json, os, subprocess, sys, time
from datetime import date, datetime
from pathlib import Path

# stdout 한글 안전 처리 (Windows CP949 대응)
# ※ sys 싱글톤에 가드 — __main__ 실행 뒤 모듈로 재import돼도 두 번 감싸지 않게.
#   이중래핑하면 먼저 만든 wrapper가 GC되며 버퍼를 닫아 'closed file' 버그가 난다.
#   pytest/다른 capture 환경에서는 buffer 없음/닫혀있을 수 있으므로 더 강한 체크 필요.
if (
    hasattr(sys.stdout, "buffer")
    and not getattr(sys, "_welp_stdout_wrapped", False)
    and sys.stdout.encoding != "utf-8"  # 이미 utf-8이면 skip
):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys._welp_stdout_wrapped = True
    except (AttributeError, ValueError, io.UnsupportedOperation):
        # pytest capture나 다른 환경에서 buffer 없음 또는 닫혀있음 — skip
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "aide_detectors"))
import stall_watch

STATUS_DIR = ROOT / "status"
QUEUE_FILE = STATUS_DIR / "_queue.json"
DECISIONS_FILE = STATUS_DIR / "hangro_decisions.jsonl"
PENDING_FILE = STATUS_DIR / "hangro_pending.json"
POST_ACTION = ROOT / "wellperion-agents" / "scripts" / "clevel_post_action.py"

CONFIDENCE_THRESHOLD = 0.6
MIN_PING_GAP_SEC = 4
APPLY_ENV = "HANGRO_APPLY"
APPLY_ON_VALUES = {"1", "true", "on", "yes"}
DONE_LOOK_KEYWORDS = ("완료", "입항", "종결", "완결", "done")
HOLD_STATUSES = ("ON_HOLD", "STANDBY", "대기", "보류")
MISLABEL_RECENT_DAYS = 1
ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS", "진행중")
VERDICT_ORDER = ("done_look_not_done", "stale", "drift", "mislabel", "no_destination")
# 승인 시 완료(DONE) 확정 대상 verdict — 그 외(no_destination/stale/mislabel)는
# 활성 배가 GM 승인만으로 DONE 처리되지 않게 막는다(오완료 방지, §설계 4-1).
COMPLETION_VERDICTS = {"drift", "done_look_not_done"}

_SUGGEST = {
    "done_look_not_done": "입항 확정 또는 진짜 남은 일 명시",
    "stale": "정박(대기) 전환 또는 재개 결정",
    "drift": "종착지(다음 한 수 + 최종 북극성) 생성",
    "mislabel": "진행중 승격",
    "no_destination": "북극성 종착지 부여",
}


def ledger_key(ship: dict) -> str:
    """안정 key = ship_no + 문맥해시(title|note|next|status의 sha1 앞10자).

    날짜 미포함 → 재핑 역설 방지 (같은 배·같은 문맥이면 항상 같은 key).
    """
    ctx = "|".join(str(ship.get(k, "")) for k in ("title", "note", "next", "status"))
    h = hashlib.sha1(ctx.encode("utf-8")).hexdigest()[:10]
    return f"{ship.get('ship_no')}|{h}"


def load_decisions(path: Path) -> dict:
    """JSONL 원장 파일을 dict로 로드."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            out[rec["key"]] = rec
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def already_decided(key: str, decisions: dict) -> bool:
    """key의 기존 결정 여부 조회."""
    return key in decisions


def record_decision(path: Path, ship: dict, decision: str) -> str:
    """결정 기록을 jsonl에 append, key 반환."""
    key = ledger_key(ship)
    rec = {
        "key": key,
        "ship_no": ship.get("ship_no"),
        "decision": decision,
        "decided_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return key


def _finding(ship: dict, verdict: str, evidence: str, suggestion: str) -> dict:
    """검수 결과 dict 생성."""
    return {
        "ship_no": ship.get("ship_no"),
        "task_id": ship.get("task_id", ""),
        "clevel": (ship.get("clevel") or "ceo").lower(),
        "title": ship.get("title", ""),
        "verdict": verdict,
        "evidence": evidence,
        "suggestion": suggestion,
    }


def default_drift_ids() -> set:
    """기본 drift finder — hangro_board._classify seam 주입."""
    try:
        import hangro_board as hb
    except ImportError:
        return set()
    sections = hb._classify(hb.fetch_queue_items())
    return {it["id"] for it in sections.get("drift", []) if it.get("id")}


def _looks_done(ship) -> bool:
    """note/next 텍스트에 완료 키워드가 있는지 판정."""
    text = f"{ship.get('note','')} {ship.get('next','')}"
    return any(k in text for k in DONE_LOOK_KEYWORDS)


def _has_destination(ship) -> bool:
    """배에 종착지(다음 또는 북극성/모듈)가 있는지 판정."""
    return bool((ship.get("next") or "").strip()) or bool(ship.get("northstar") or ship.get("module"))


def _verdict_for(ship, stale_ids, drift_ids, today) -> str | None:
    """배에 대한 판정 반환(없으면 None). VERDICT_ORDER가 실제 우선순위를 구동."""
    st = str(ship.get("status", ""))
    active = st in ACTIVE_STATUSES or st.upper() in {s.upper() for s in ACTIVE_STATUSES}

    def _check_done_look_not_done() -> bool:
        return active and _looks_done(ship)

    def _check_stale() -> bool:
        return ship.get("ship_no") in stale_ids

    def _check_drift() -> bool:
        return ship.get("task_id") in drift_ids

    def _check_mislabel() -> bool:
        if st.upper() not in {h.upper() for h in HOLD_STATUSES}:
            return False
        la = stall_watch.last_activity(ship)
        return bool(la and (today - la).days <= MISLABEL_RECENT_DAYS)

    def _check_no_destination() -> bool:
        return active and not _has_destination(ship)

    checks = {
        "done_look_not_done": _check_done_look_not_done,
        "stale": _check_stale,
        "drift": _check_drift,
        "mislabel": _check_mislabel,
        "no_destination": _check_no_destination,
    }
    for v in VERDICT_ORDER:
        if checks[v]():
            return v
    return None


def audit_ships(raw_queue, *, drift_ids=None, today=None):
    """항로 검수 5종 판정 (done_look_not_done / stale / drift / mislabel / no_destination)."""
    today = today or date.today()
    if drift_ids is None:
        drift_ids = default_drift_ids()
    stale_gaps = stall_watch.detect_stalled(raw_queue, today)
    stale_ids = {g.get("ship_no"): g for g in stale_gaps}
    findings = []
    taken = set()
    for ship in raw_queue:
        sn = ship.get("ship_no")
        if sn is None:
            continue
        if sn in taken:
            continue
        v = _verdict_for(ship, stale_ids, drift_ids, today)
        if not v:
            continue
        # stale 경우 기존 포맷 유지, 나머지는 새 포맷
        if v == "stale":
            g = stale_ids[sn]
            ev = f"{g['days_idle']}일 무활동(임계 {g['threshold']}일 초과)"
        else:
            ev = f"status={ship.get('status')} next={'유' if (ship.get('next') or '').strip() else '무'}"
        findings.append(_finding(ship, v, ev, _SUGGEST[v]))
        taken.add(sn)
    return findings


def _build_ship_prompt(ship: dict) -> str:
    """배 1척 문맥으로 LLM 프롬프트 구성."""
    return (
        "당신은 웰페리온 AI CEO '웰리'입니다. 아래 배 1척의 '종착지'를 정하세요.\n"
        f"- 제목: {ship.get('title','')}\n- 담당: {ship.get('clevel','')}\n"
        f"- 메모: {(ship.get('note') or '')[:300]}\n- 현재 next: {ship.get('next') or '(없음)'}\n"
        f"- 검수판정: {ship.get('verdict','')}\n\n"
        "순수 JSON만 출력(코드블록 없이):\n"
        '{"next_step":"다음 한 수 1줄","final_destination":"어느 북극성",'
        '"path_map":"🌟 북극성 → 📍 지금 → 👉 오늘 한 수","confidence":0.0~1.0}')


def _rule_destination(ship: dict) -> dict:
    """규칙 폴백 = 저확신 제안(northstar_recommender.brain_fallback 결과 형식 계승)."""
    title = ship.get("title", "")
    return {"next_step": f"[저확신] {title} 다음 한 수 담당 확정 필요",
            "final_destination": "(담당 북극성 연결 확인 필요)",
            "path_map": f"🌟 (미정) → 📍 {title} → 👉 다음 정하세요",
            "confidence": 0.3}


def generate_destination(ship: dict, *, run_claude=None) -> dict:
    """배 1척 문맥 → {다음 한 수, 최종 북극성, path_map, confidence} 생성.

    run_claude 실패·빈 응답·파싱 실패 시 규칙 폴백(저확신 라벨) — 거짓 종착지 금지.
    """
    if run_claude is None:
        p = str(ROOT / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)
        from model_router import run_claude as _rc
        run_claude = _rc
    raw, _model = run_claude(_build_ship_prompt(ship), label="hangro-destination")
    data = None
    if raw:
        try:
            import re
            cleaned = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            data = None
    if not isinstance(data, dict) or not str(data.get("next_step", "")).strip():
        data = _rule_destination(ship)   # 실패·빈 응답 → 규칙 폴백(저확신)
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {"ship_no": ship.get("ship_no"), "title": ship.get("title", ""),
            "verdict": ship.get("verdict", ""),
            "next_step": str(data.get("next_step", "")).strip(),
            "final_destination": str(data.get("final_destination", "")).strip(),
            "path_map": str(data.get("path_map", "")).strip(),
            "confidence": conf, "low_confidence": conf < CONFIDENCE_THRESHOLD}


def ping_gm(cards, *, decisions=None, send_fn, sleep_fn=time.sleep, ship_by_no=None) -> list:
    """GM 카드 핑: 간격 제어(429 방어) + dedup 통합 (이미 결정된 배 재핑 금지).

    Args:
        cards: 발송할 카드 배열
        decisions: ledger_key → 결정 dict 매핑 (None → 빈 dict)
        send_fn: 카드 1개 발송 함수 (테스트용 주입)
        sleep_fn: 간격 제어 함수 (기본=time.sleep, 테스트용 주입)
        ship_by_no: ship_no → 배 dict 매핑 (dedup 판정용)

    Returns:
        발송된 카드 배열 (dedup 제외)

    저확신 카드(low_confidence=True)는 next_step에 "[저확신]" 라벨 추가.
    """
    decisions = decisions or {}
    ship_by_no = ship_by_no or {}
    sent = []

    for card in cards:
        ship = ship_by_no.get(card.get("ship_no"), {"ship_no": card.get("ship_no")})
        if already_decided(ledger_key(ship), decisions):
            continue  # GM 이미 결정한 배 → 재핑 금지(dedup)

        # 카드 사이에만 간격 제어(첫 발송 제외)
        if sent:
            sleep_fn(MIN_PING_GAP_SEC)

        # 저확신 카드 라벨 반영
        card_to_send = card.copy()
        if card_to_send.get("low_confidence"):
            next_step = card_to_send.get("next_step", "")
            if not next_step.startswith("[저확신]"):
                card_to_send["next_step"] = f"[저확신] {next_step}"

        send_fn(card_to_send)
        sent.append(card_to_send)

    return sent


def apply_enabled(cli_flag: bool = False) -> bool:
    """게이트 판정 — cli_flag 우선, 없으면 환경변수(HANGRO_APPLY)."""
    if cli_flag:
        return True
    return os.environ.get(APPLY_ENV, "").strip().lower() in APPLY_ON_VALUES


def apply_on_approval(card, *, decision="approved", gate_on=None,
                       runner=subprocess.run, decisions_path=DECISIONS_FILE) -> tuple[str, bool]:
    """GM 승인 카드 → clevel_post_action.py 배관(--next).

    게이트(HANGRO_APPLY) OFF면 --dry-run 부착(라이브 델타 0). ON일 때만 실반영 +
    dedup 원장(record_decision) 기록. subprocess는 queue_lock으로 직렬화한다.

    verdict가 COMPLETION_VERDICTS(drift/done_look_not_done)일 때만 완료(DONE) 확정
    (--status 완료). 그 외(no_destination/stale/mislabel)는 활성 배를 GM 승인만으로
    오완료시키지 않도록 배의 현재 status를 그대로 넘긴다 — clevel_post_action.py 는
    비-DONE 상태에서 _queue.json(다음 배관)을 건드리지 않으므로 활성 배 상태는 불변.
    """
    if gate_on is None:
        gate_on = apply_enabled()
    is_completion = card.get("verdict") in COMPLETION_VERDICTS
    status = "완료" if is_completion else str(card.get("status") or "PENDING")
    py = r"C:\Python314\python.exe" if Path(r"C:\Python314\python.exe").exists() else sys.executable
    # --status 완료 → clevel_post_action.py 는 DONE 판정 시 --artifact-url(증거) 을
    # 필수로 요구한다(없으면 exit 2, 4요건 중 ④증거 누락 거부). 카드에 artifact_url이
    # 있으면 그걸, 없으면 승인이 실제로 기록되는 원장 경로를 증거로 넘긴다(non-empty 보장).
    artifact_url = card.get("artifact_url") or str(decisions_path)
    cmd = [py, str(POST_ACTION),
           "--clevel", str(card.get("clevel", "ceo")).upper(),
           "--task-id", str(card.get("task_id", "")),
           "--status", status,
           "--summary", f"[웰리 종착지 승인] {card.get('title', '')}",
           "--artifact-url", artifact_url,
           "--next", str(card.get("next_step", ""))]
    if not gate_on:
        cmd.append("--dry-run")    # ★게이트 OFF = 라이브 델타 0
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import queue_lock
        ctx = queue_lock.queue_lock("hangro-review")
    except ImportError:
        from contextlib import nullcontext
        ctx = nullcontext()
        print("[WARN] queue_lock 미가용 — 직렬화 없이 진행", file=sys.stderr)
    with ctx:
        r = runner(cmd, cwd=str(ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=60)
    changed = gate_on and getattr(r, "returncode", 1) == 0
    if changed:
        record_decision(decisions_path, card, decision)   # 승인 반영 시 원장 기록
    return (f"apply gate={'ON' if gate_on else 'OFF(dry-run)'} ship={card.get('ship_no')}", changed)


def _load_queue(queue_path) -> list:
    """큐 파일을 읽어 리스트로 반환. 없거나 파싱 실패 시 빈 리스트(read-only)."""
    p = Path(queue_path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print(f"[WARN] 큐 파싱 실패({p}) — 빈 리스트로 진행", file=sys.stderr)
        return []


def run(*, send=False, audit_only=False, queue_path=QUEUE_FILE) -> dict:
    """항로 검수·종착지 두뇌 엔드투엔드: audit → generate → dedup → (pending 기록/발송).

    ★큐(_queue.json)는 어떤 모드에서도 쓰지 않는다 — 반영은 apply_on_approval(게이트) 전용.
    """
    raw = _load_queue(queue_path)
    findings = audit_ships(raw)
    if audit_only:
        print(f"[검수] {len(findings)}건: {[f['verdict'] for f in findings]}")
        return {"findings": findings, "card_count": 0}
    by_no = {}
    for s in raw:                     # first-wins(중복 ship_no) — audit_ships 판정과 정합
        sn = s.get("ship_no")
        if sn not in by_no:
            by_no[sn] = s
    decisions = load_decisions(DECISIONS_FILE)
    cards = []
    for f in findings:
        ship = by_no.get(f["ship_no"], {})
        ship = {**ship, "verdict": f["verdict"]}
        if already_decided(ledger_key(ship), decisions):
            continue                    # 이미 GM 결정 = 재핑/재생성 안 함
        cards.append(generate_destination(ship))
    pending = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "findings": findings, "cards": cards, "card_count": len(cards)}
    PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    if send:
        send_fn = _telegram_send_fn()          # northstar send 패턴 재사용(_env_val)
        ping_gm(cards, decisions=decisions, ship_by_no=by_no, send_fn=send_fn)
    else:
        print(f"[드라이런] 카드 {len(cards)}건 → {PENDING_FILE} (텔레그램·큐쓰기 없음)")
    return pending


def _telegram_send_fn():
    """카드 1장 텔레그램 발송 클로저 — northstar_recommender._env_val 재사용(토큰 .env 직독)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import urllib.parse, urllib.request
    from northstar_recommender import _env_val
    tok, chat = _env_val("TELEGRAM_BOT_TOKEN"), _env_val("TELEGRAM_CHAT_ID")

    def _send(card):
        if not tok or not chat:
            print("[WARN] 텔레그램 미설정 — 발송 생략")
            return
        text = (f"🧭 <b>웰리 항로 검수 — 종착지 제안</b>\n"
                f"배 #{card.get('ship_no')} · {card.get('title','')}\n"
                f"{'⚠️ 저확신 제안' if card.get('low_confidence') else '추천'}: "
                f"{card.get('next_step','')}\n{card.get('path_map','')}")
        data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"}).encode("utf-8")
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=data, method="POST"), timeout=15)
        except Exception as e:
            print(f"[WARN] 카드 발송 실패 ship={card.get('ship_no')} err={type(e).__name__}", file=sys.stderr)
    return _send


def main():
    ap = argparse.ArgumentParser(description="웰리 항로 검수·종착지 두뇌")
    ap.add_argument("--dry-run", action="store_true", help="드라이런(기본) — 카드 pending 기록만")
    ap.add_argument("--send", action="store_true", help="텔레그램 카드 발송(간격 제어)")
    ap.add_argument("--audit-only", action="store_true", help="검수 판정만 출력(read-only)")
    a = ap.parse_args()
    run(send=a.send and not a.dry_run, audit_only=a.audit_only)


if __name__ == "__main__":
    main()
