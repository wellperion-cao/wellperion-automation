# -*- coding: utf-8 -*-
"""회원 시트 → 서버 SQLite 미러 동기화 (읽기 전용 단방향) — 배 801 준비분 A.

sync_inquiries.py 와 같은 규칙이다. 원천은 화면들이 이미 쓰는 GAS 액션(member_active_list)을
그대로 부르고, 시트·GAS 는 절대 쓰지 않는다. 열쇠는 회원번호(M00001…) — 번호 없는 행은
미러에 넣지 않고 건수만 남긴다(전화·이름으로 사람을 찾던 구조로 되돌아가지 않기 위해).
정의서 = status/briefs/CPO-2026-09-03-회원미러-정의서.md

실행: python3 /srv/erp/api/sync_members.py   (cron 5분 · 시토 배치)
자체점검: python3 sync_members.py --selftest  (임시 DB · 네트워크 없음)
"""
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import DB_PATH, gas_get, load_env  # noqa: E402  — 같은 원천·같은 env

SCOPES = ["valid", "ended", "corp", "archive"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
  member_no   TEXT PRIMARY KEY,
  scope       TEXT NOT NULL,
  name        TEXT,
  phone       TEXT,
  kind        TEXT,
  kind2       TEXT,
  program     TEXT,
  reg_class   TEXT,
  reg_seq     TEXT,
  reg_date    TEXT,
  start_date  TEXT,
  end_date    TEXT,
  loss_date   TEXT,
  remain_days TEXT,
  owner       TEXT,
  data        TEXT NOT NULL,
  synced_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mem_scope_end ON members(scope, end_date);
CREATE INDEX IF NOT EXISTS ix_mem_phone ON members(phone);
CREATE INDEX IF NOT EXISTS ix_mem_name ON members(name);
CREATE TABLE IF NOT EXISTS sync_meta (k TEXT PRIMARY KEY, v TEXT);
"""

# 시트 머리글은 줄바꿈·공백이 섞여 있다("등록\\n일자"). 공백을 전부 지운 이름으로 맞춘다.
COLS = {
    "name": "회원명", "phone": "휴대폰번호", "kind": "회원구분", "kind2": "세부구분",
    "program": "수강반종목명", "reg_class": "등록분류", "reg_seq": "등록회차",
    "reg_date": "등록일자", "start_date": "시작일자", "end_date": "종료일자",
    "loss_date": "LOSS일자", "remain_days": "잔여일(일)", "owner": "담당자",
}


def _norm_row(r):
    return {re.sub(r"\s+", "", str(k)): v for k, v in r.items()}


def _phone(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d if len(d) in (10, 11) else (d or None)


def replace_scope(conn, scope, rows, now):
    """한 scope 를 통째로 갈아끼운다. 반환 = (넣은 건수, 회원번호 없어 뺀 건수)."""
    recs, unnumbered = [], 0
    for r in rows:
        n = _norm_row(r)
        no = str(n.get("회원번호") or "").strip()
        if not re.fullmatch(r"M\d{5}", no):
            unnumbered += 1
            continue
        get = lambda k: (str(n.get(COLS[k]) or "").strip() or None)
        recs.append((
            no, scope, get("name"), _phone(n.get(COLS["phone"])), get("kind"), get("kind2"),
            get("program"), get("reg_class"), get("reg_seq"), get("reg_date"), get("start_date"),
            get("end_date"), get("loss_date"), get("remain_days"), get("owner"),
            json.dumps(r, ensure_ascii=False), now,
        ))
    with conn:
        conn.execute("DELETE FROM members WHERE scope=?", (scope,))
        conn.executemany(
            "INSERT OR REPLACE INTO members (member_no,scope,name,phone,kind,kind2,program,"
            "reg_class,reg_seq,reg_date,start_date,end_date,loss_date,remain_days,owner,data,synced_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
    return len(recs), unnumbered


def main():
    load_env()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    total, unnumbered, failed = 0, 0, []
    for scope in SCOPES:
        data = gas_get("member_active_list", {"scope": scope}, timeout=90)
        rows = (data or {}).get("data")
        if not isinstance(rows, list) or not rows:
            failed.append(scope)  # 실패 — 기존 미러 유지(빈 값으로 덮지 않음)
            continue
        n, u = replace_scope(conn, scope, rows, now)
        total += n
        unnumbered += u
        print("[ok] %s %d건 (번호 없음 %d)" % (scope, n, u))
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_last_sync',?)", (now,))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_last_failed',?)", (",".join(failed),))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_unnumbered',?)", (str(unnumbered),))
    print("[done] %s · 갱신 %d건 · 번호 없음 %d · 실패 %s" % (now, total, unnumbered, failed or "없음"))
    return 1 if failed else 0


def selftest():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    rows = [
        {"회원번호": "M00001", "회원명": "홍길동", "휴대폰 번호": "010-1234-5678", "등록\n일자": "2026-01-01"},
        {"회원번호": "M00002", "회원명": "김철수", "휴대폰 번호": "01098765432"},
        {"회원명": "번호없음", "휴대폰 번호": "010-0000-0000"},
    ]
    assert replace_scope(conn, "valid", rows, "t0") == (2, 1), "회원번호 없는 행은 빼고 센다"
    assert conn.execute("SELECT phone FROM members WHERE member_no='M00001'").fetchone()[0] == "01012345678"
    assert conn.execute("SELECT reg_date FROM members WHERE member_no='M00001'").fetchone()[0] == "2026-01-01", \
        "줄바꿈 섞인 머리글도 같은 칸으로 읽는다"
    assert replace_scope(conn, "valid", rows[:1], "t1") == (1, 0), "같은 scope 는 통째로 교체"
    replace_scope(conn, "corp", rows[1:2], "t1")
    assert conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 2, "다른 scope 가 남의 scope 를 지우면 안 된다"
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
