#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
queue_archive.py — 끝난 일 자동 정리 장치 (일의 브릿지 보조)

목적
    status/_queue.json(중앙 큐 = 열린 일 + 막 끝난 일)이 완료 항목으로 비대해지는 것을 막는다.
    "완료된 지 N일 지난" DONE 항목만 status/_archive.json(끝난 일 보관소)으로 옮겨,
    큐에는 '지금 열린 일 + 최근 완료(보고용)'만 남게 한다.

왜 N일 보존(기본 2일)인가
    ceo_morning_pipeline.py / ceo_evening_wrap.py 는 _queue.json 에서
    'processed_at=어제/오늘인 DONE' 을 읽어 '마무리 건수'를 집계한다.
    완료 즉시 다 치우면 그 보고가 깨지므로, 어제·오늘 완료는 큐에 남긴다.
    daily_scheduler(status!=DONE) · bot(PENDING) 은 애초에 DONE 을 안 읽어 영향 없음.

날짜 판정
    완료일 = processed_at → completed_at → updated_at → enqueued_at 순으로 처음 존재하는 값의
    앞 10자(YYYY-MM-DD). 어느 것도 없으면 '아주 오래된 것'으로 간주해 보관 대상.
    cutoff = today - retain_days. 완료일 < cutoff 이면 보관(이동).

원자적 쓰기
    .tmp 작성 후 os.replace 로 교체(부분 기록 방지). 기존 브릿지와 동일 패턴.

CLI
    python queue_archive.py --sweep [--retain-days 2] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATUS_DIR = _REPO_ROOT / "status"
_QUEUE_PATH = _STATUS_DIR / "_queue.json"
_ARCHIVE_PATH = _STATUS_DIR / "_archive.json"

DEFAULT_RETAIN_DAYS = 2
_DATE_FIELDS = ("processed_at", "completed_at", "updated_at", "enqueued_at")


def _load_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] {path.name} 로드 실패: {e}", file=sys.stderr)
        return []


def _atomic_write(path: Path, items: list) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(path))


def _completion_date(item: dict) -> date | None:
    """완료일 추출(YYYY-MM-DD). 후보 필드가 전부 없으면 None(=아주 오래됨 취급)."""
    for f in _DATE_FIELDS:
        v = item.get(f)
        if isinstance(v, str) and len(v) >= 10:
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    return None


def sweep_old_done(
    retain_days: int = DEFAULT_RETAIN_DAYS,
    today: date | None = None,
    dry_run: bool = False,
    queue_path: Path | None = None,
    archive_path: Path | None = None,
) -> tuple[int, int]:
    """
    _queue.json 에서 '완료된 지 retain_days 일 지난' DONE 항목을 _archive.json 으로 이동.

    반환: (kept_open_or_recent, archived_count)
    """
    qpath = queue_path or _QUEUE_PATH
    apath = archive_path or _ARCHIVE_PATH
    today = today or datetime.now(timezone.utc).astimezone().date()
    cutoff = today - timedelta(days=retain_days)

    queue = _load_list(qpath)
    keep: list = []
    to_archive: list = []

    for item in queue:
        if not isinstance(item, dict):
            keep.append(item)
            continue
        status = str(item.get("status", "")).upper()
        if status != "DONE":
            keep.append(item)            # 열린 일은 무조건 잔류
            continue
        cdate = _completion_date(item)
        # 완료일을 못 구하면(undated) 오래된 것으로 보고 보관. 구하면 cutoff 비교.
        if cdate is None or cdate < cutoff:
            item.setdefault("archived_at", today.isoformat())
            to_archive.append(item)
        else:
            keep.append(item)            # 최근 완료(보고용)는 잔류

    if not to_archive:
        return (len(keep), 0)

    if dry_run:
        ids = ", ".join(str(x.get("task_id")) for x in to_archive)
        print(f"[DRY-RUN] 보관 예정 {len(to_archive)}건: {ids}")
        return (len(keep), len(to_archive))

    archive = _load_list(apath)
    existing = {x.get("task_id") for x in archive if isinstance(x, dict)}
    for x in to_archive:
        if x.get("task_id") not in existing:   # 중복 보관 방지(멱등)
            archive.append(x)

    _atomic_write(apath, archive)
    _atomic_write(qpath, keep)
    print(f"[Archive] 끝난 일 {len(to_archive)}건 보관 → 큐 잔류 {len(keep)}건")
    return (len(keep), len(to_archive))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="끝난 일 자동 정리(_queue.json → _archive.json)")
    ap.add_argument("--sweep", action="store_true", help="완료 N일 경과 항목 보관 실행")
    ap.add_argument("--retain-days", type=int, default=DEFAULT_RETAIN_DAYS,
                    help=f"큐에 남길 완료 보존 일수(기본 {DEFAULT_RETAIN_DAYS})")
    ap.add_argument("--dry-run", action="store_true", help="이동 없이 대상만 출력")
    args = ap.parse_args(argv)

    if not args.sweep:
        ap.print_help()
        return 0

    kept, archived = sweep_old_done(retain_days=args.retain_days, dry_run=args.dry_run)
    print(f"완료. 큐 {kept}건 / 보관 {archived}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
