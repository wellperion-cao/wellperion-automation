# -*- coding: utf-8 -*-
"""서버 캐시·백업 버전 정리 (배1040). 실행: python3 /srv/erp/api/prune_versions.py [--apply] (cron 03:30 KST 일일).

실측(2026-09-05, 시토): sales_cache·funnel_cache·misc_cache·board_cache 4표는 PRIMARY KEY 가
집계 키 자체라 sync_*.py 가 전부 INSERT..ON CONFLICT DO UPDATE(업서트)로 쓴다 — 키당 항상 1행,
DB 제약상 "이력 행"이 애초에 생길 수 없다. 그래서 이 스크립트는 그 4표를 건드리지 않는다
(존재하지 않는 문제를 치우는 코드는 안 만든다).
실제로 버전이 쌓이는 곳은 /srv/erp/backup 뿐(ad-hoc 덤프 파일) — 파일명 접두사(타임스탬프 앞부분)
별로 최신 KEEP개만 남기고 나머지는 지우기 전 prune_<시각>.json 에 통째로 백업한다.
write_log·intake_log 는 삭제하지 않는다(약속) — 90일 초과 행 수만 세어 로그에 남긴다.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

BACKUP_DIR = "/srv/erp/backup"
KEEP = 2
RETAIN_DAYS = 90
KST = timezone(timedelta(hours=9))
_TS_SUFFIX = re.compile(r"_\d{8}_\d{6}(?=\.[^.]+$|$)")


def _prefix(fname):
    """파일명에서 뒤 타임스탬프(_YYYYMMDD_HHMMSS)를 뗀 나머지 = 같은 종류 판정 키."""
    return _TS_SUFFIX.sub("", fname)


def scan_backup_dir():
    """접두사별 파일 목록(최신순). {prefix: [(mtime, path, size), ...]}"""
    groups = {}
    if not os.path.isdir(BACKUP_DIR):
        return groups
    for fname in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, fname)
        if not os.path.isfile(path):
            continue
        st = os.stat(path)
        groups.setdefault(_prefix(fname), []).append((st.st_mtime, path, st.st_size))
    for g in groups.values():
        g.sort(key=lambda x: x[0], reverse=True)
    return groups


def prune_backup_dir(apply):
    groups = scan_backup_dir()
    to_delete = []
    for prefix, files in groups.items():
        to_delete.extend(files[KEEP:])
    dump_path = None
    if to_delete and apply:
        dump = []
        for mtime, path, size in to_delete:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError):
                content = None  # 텍스트가 아니면 이름·크기만 기록
            dump.append({"path": path, "mtime": mtime, "size": size, "content": content})
        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        dump_path = os.path.join(BACKUP_DIR, f"prune_{ts}.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False)
        for _, path, _ in to_delete:
            os.remove(path)
    return groups, to_delete, dump_path


def count_old_logs(conn):
    cutoff = (datetime.now(KST) - timedelta(days=RETAIN_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    wl = conn.execute("SELECT count(*) FROM write_log WHERE at < %s", (cutoff,)).fetchone()[0]
    il = conn.execute("SELECT count(*) FROM intake_log WHERE received_at < %s", (cutoff,)).fetchone()[0]
    return wl, il


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 삭제(기본은 dry-run)")
    args = ap.parse_args()

    groups, to_delete, dump_path = prune_backup_dir(args.apply)
    print(f"backup dir: {len(groups)}종 · 삭제대상 {len(to_delete)}개" + (f" apply" if args.apply else " dry-run"))
    for _, path, size in to_delete:
        print(" -", path, size, "B")
    if dump_path:
        print("dump:", dump_path)

    conn = db.connect()
    wl, il = count_old_logs(conn)
    conn.close()
    print(f"write_log {RETAIN_DAYS}일초과 {wl}행(삭제안함) · intake_log {RETAIN_DAYS}일초과 {il}행(삭제안함)")


if __name__ == "__main__":
    main()
