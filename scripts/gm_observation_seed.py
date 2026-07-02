#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GM 관찰 원장 시드 스크립트 (배237 · GM 보좌 자율화 MVP · 첫걸음).

이미 존재하는 로그(northstar_log.jsonl, _queue.json, _queue_archive.json)를
스캔해 'GM 성향·습관' 관찰을 status/gm_observation_ledger.jsonl 에 append한다.

원칙:
- 순수 관찰·기록만. GM 행동을 바꾸거나 무언가를 자동 실행하지 않는다.
- 라이브 게이팅·발송·GAS 호출 없음. 파일 read + 원장 append만.
- 프라이버시: 민감정보 원문 대신 요약·패턴 위주로 저장.
- 멱등: dedup_key로 이미 적재된 관찰은 재실행해도 중복 append하지 않는다.
"""
import json
import re
from datetime import datetime, date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
NORTHSTAR_LOG = STATUS_DIR / "northstar_log.jsonl"
QUEUE_ACTIVE = STATUS_DIR / "_queue.json"
QUEUE_ARCHIVE = STATUS_DIR / "_queue_archive.json"
LEDGER = STATUS_DIR / "gm_observation_ledger.jsonl"

TODAY = datetime.now().date()
GM_NOTE_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2})\s*(GM[^\]]*)\]")
TRAILING_SNIPPET_LEN = 140
DECISION_LOOKBACK_DAYS = 14   # 최근 GM 결정만 (전체 이력 스캔은 과설계)
LONG_PENDING_DAYS = 30        # 이만큼 PENDING 유지되면 '장기 대기'


def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_json_array(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def load_existing_keys():
    keys = set()
    if not LEDGER.exists():
        return keys
    for row in read_jsonl(LEDGER):
        k = row.get("dedup_key")
        if k:
            keys.add(k)
    return keys


def make_row(source, signal_type, summary, evidence, pattern_hint, dedup_key):
    return {
        "observed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "signal_type": signal_type,
        "summary": summary,
        "evidence": evidence,
        "pattern_hint": pattern_hint,
        "dedup_key": dedup_key,
    }


def scan_northstar():
    """추천 카드 승인/보류/자동만료 패턴 관찰."""
    observations = []
    events = read_jsonl(NORTHSTAR_LOG)
    expired_events = [e for e in events if e.get("event") == "expired"]

    for e in expired_events:
        d = e.get("date", "unknown")
        key = f"northstar_log|missed|{d}"
        observations.append((key, make_row(
            source="northstar_log",
            signal_type="missed",
            summary=f"{d} 일일 북극성 추천 카드 GM 미응답 → 자동만료",
            evidence=f"date={d} candidate_count={e.get('candidate_count')} reason={e.get('reason')}",
            pattern_hint="GM이 06:30 추천 카드에 응답(승인/보류) 없이 자동만료 — 도달/노출 방식 재점검 또는 웰리 선제 리마인드 후보",
            dedup_key=key,
        )))

    if len(expired_events) >= 3:
        recent = expired_events[-3:]
        dates_str = "·".join(e.get("date", "?") for e in recent)
        key = f"northstar_log|approval_pattern|{dates_str}"
        observations.append((key, make_row(
            source="northstar_log",
            signal_type="approval_pattern",
            summary=f"최근 {len(recent)}일({dates_str}) 연속 추천 카드 승인·보류 응답 0건 — 전부 자동만료",
            evidence=f"expired_dates={[e.get('date') for e in recent]}",
            pattern_hint="GM이 06:30 추천 카드에 미응답·자동만료 반복 — 도달/노출 방식 재점검 또는 웰리 선제 리마인드 후보",
            dedup_key=key,
        )))
    return observations


def scan_queue_decisions(items, source_label):
    """note 필드의 '[YYYY-MM-DD GM ...]' 결정 이력 추출 (최근분만)."""
    observations = []
    cutoff = TODAY - timedelta(days=DECISION_LOOKBACK_DAYS)
    for item in items:
        note = item.get("note") or ""
        task_id = item.get("task_id") or item.get("id") or "unknown"
        for m in GM_NOTE_RE.finditer(note):
            d_str, body = m.group(1), m.group(2)
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < cutoff:
                continue
            # 대괄호 안(예: "GM")보다 대괄호 뒤에 이어지는 실제 결정 문구가 더 유의미
            trailing = note[m.end():m.end() + TRAILING_SNIPPET_LEN].strip()
            snippet = trailing if trailing else body.strip()
            if len(snippet) >= TRAILING_SNIPPET_LEN:
                snippet = snippet.rstrip() + "…"
            key = f"{source_label}|decision|{task_id}|{d_str}"
            observations.append((key, make_row(
                source=source_label,
                signal_type="decision",
                summary=f"[{task_id}] {d_str} GM 결정: {snippet}",
                evidence=f"task_id={task_id} note_date={d_str}",
                pattern_hint="GM 결정 이력 — 유사 안건 재상정 시 과거 결정 참고 후보",
                dedup_key=key,
            )))
    return observations


def scan_drift(items, source_label):
    """완료인데 '다음'이 비어있는 표류 관찰."""
    observations = []
    for item in items:
        if item.get("status") != "DONE" and not item.get("terminal"):
            continue
        next_field = (item.get("next") or "").strip()
        if next_field:
            continue
        task_id = item.get("task_id") or item.get("id") or "unknown"
        key = f"{source_label}|repeat|{task_id}|no_next"
        observations.append((key, make_row(
            source=source_label,
            signal_type="repeat",
            summary=f"[{task_id}] 완료됐지만 '다음' 없이 표류",
            evidence=f"task_id={task_id} status={item.get('status')}",
            pattern_hint="완료 후 다음 단계 미정 — 표류 방지 위해 후속 정하기 촉구 후보",
            dedup_key=key,
        )))
    return observations


def scan_long_pending(items, source_label):
    """PENDING 상태로 장기 대기 중인 배 관찰 (활성 큐만 — 아카이브는 이미 종료건)."""
    observations = []
    for item in items:
        if item.get("status") != "PENDING":
            continue
        enq = item.get("enqueued_at")
        if not enq:
            continue
        try:
            d = datetime.strptime(enq, "%Y-%m-%d").date()
        except ValueError:
            continue
        age = (TODAY - d).days
        if age < LONG_PENDING_DAYS:
            continue
        task_id = item.get("task_id") or item.get("id") or "unknown"
        key = f"{source_label}|routine|{task_id}|long_pending"
        observations.append((key, make_row(
            source=source_label,
            signal_type="routine",
            summary=f"[{task_id}] {age}일째 PENDING 대기 — 장기 미착수",
            evidence=f"task_id={task_id} enqueued_at={enq} priority={item.get('priority')}",
            pattern_hint="장기 대기 배 — GM 우선순위 재확인 또는 폐기 판단 후보",
            dedup_key=key,
        )))
    return observations


def main():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    existing_keys = load_existing_keys()

    active_items = read_json_array(QUEUE_ACTIVE)
    archive_items = read_json_array(QUEUE_ARCHIVE)

    all_observations = []
    all_observations += scan_northstar()
    all_observations += scan_queue_decisions(active_items, "queue_active")
    all_observations += scan_queue_decisions(archive_items, "queue_archive")
    all_observations += scan_drift(active_items, "queue_active")
    all_observations += scan_drift(archive_items, "queue_archive")
    all_observations += scan_long_pending(active_items, "queue_active")

    new_rows = []
    seen_this_run = set()
    for key, row in all_observations:
        if key in existing_keys or key in seen_this_run:
            continue
        seen_this_run.add(key)
        new_rows.append(row)

    if new_rows:
        with open(LEDGER, "a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[gm_observation_seed] 신규 적재 {len(new_rows)}건 (기존 {len(existing_keys)}건 스킵)")
    by_type = {}
    for row in new_rows:
        by_type.setdefault(row["signal_type"], 0)
        by_type[row["signal_type"]] += 1
    for t, c in by_type.items():
        print(f"  - {t}: {c}건")
    for row in new_rows[:8]:
        print(f"    · [{row['signal_type']}] {row['summary']}")
    if len(new_rows) > 8:
        print(f"    ... 외 {len(new_rows) - 8}건")


if __name__ == "__main__":
    main()
