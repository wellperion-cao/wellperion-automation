# -*- coding: utf-8 -*-
"""track_events 90일 보관 상한 (배1034). 실행: python3 /srv/erp/api/prune_track.py  (cron 03:20 KST 일일)."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

RETAIN_DAYS = 90


def cutoff():
    return (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=RETAIN_DAYS)).strftime("%Y-%m-%d %H:%M:%S")


def main():
    conn = db.connect()
    with conn:
        n = conn.execute("DELETE FROM track_events WHERE ts < %s", (cutoff(),)).rowcount
    conn.close()
    print("pruned", n, "rows older than", RETAIN_DAYS, "days")


if __name__ == "__main__":
    assert cutoff() < datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")
    main()
