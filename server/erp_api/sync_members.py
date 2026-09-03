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
  member_no   TEXT NOT NULL,
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
  synced_at   TEXT NOT NULL,
  PRIMARY KEY (member_no, scope)
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
    """한 scope 를 통째로 갈아끼운다. 반환 = (넣은 건수, 회원번호 없어 뺀 건수).
    열쇠 = (회원번호, scope) — 같은 사람이 유효회원과 LOSS보관에 같은 번호로 함께 있는 것은 이력이라 다 싣는다."""
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


def classify_overlaps(conn):
    """한 회원번호가 여러 scope 에 있는 경우를 가른다. 반환 = (충돌 건수, 같은 사람 이력 건수).
    충돌 = 같은 번호인데 이름+전화가 다른 사람(등기부 오류 — 시포가 재부여). 이력 = 같은 사람(정상)."""
    rows = conn.execute(
        "SELECT COUNT(DISTINCT name || '|' || COALESCE(phone,'')) FROM members"
        " GROUP BY member_no HAVING COUNT(*) > 1").fetchall()
    collisions = sum(1 for (k,) in rows if k > 1)
    return collisions, len(rows) - collisions


def _tell_gm(text):
    """문제가 생기면 업무보고방에 즉시 (GM 지시 2026-09-03). 키는 erp_auth.tell_gm 과 같은
    TG_BOT_TOKEN·TG_CHAT_ID — api.env 에 같은 두 줄을 넣어야 산다(시토 배치 항목)."""
    import urllib.request
    token, chat = os.environ.get("TG_BOT_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat:
        return False
    try:
        req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token,
                                     data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception:
        return False   # 알림 실패가 동기화를 막지 않는다


def alert_on_change(conn, failed, unnumbered, collided):
    """상태가 '나쁨'으로 바뀌거나 나쁨의 내용이 달라질 때만 보낸다. 5분마다 같은 말을 반복하지 않고,
    나쁨 → 정상으로 돌아오면 복구 한 줄. 지문은 sync_meta 에 남긴다. 반환 = 보낸 문구(없으면 None)."""
    fp = "f=%s|u=%d|c=%d" % (",".join(failed), unnumbered, collided)
    bad = bool(failed) or unnumbered > 0 or collided > 0
    prev = conn.execute("SELECT v FROM sync_meta WHERE k='members_alert_fp'").fetchone()
    prev = prev[0] if prev else ""
    if fp == prev:
        return None
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_alert_fp',?)", (fp,))
    if bad:
        lines = ["⚠ 회원 미러(AWS) 이상"]
        if failed:
            lines.append("   시트 조회 실패: %s — 옛 미러 유지 중" % ", ".join(failed))
        if unnumbered:
            lines.append("   회원번호 없는 회원 %d명 — 서버에서 빠짐(배941)" % unnumbered)
        if collided:
            lines.append("   회원번호 충돌 %d건 — 등기부 확인 필요" % collided)
        lines.append("   👉 시포 확인")
        return "\n".join(lines)
    return "✅ 회원 미러(AWS) 정상 복귀" if prev else None


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
    collided, multi = classify_overlaps(conn)
    with conn:
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_last_sync',?)", (now,))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_last_failed',?)", (",".join(failed),))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_unnumbered',?)", (str(unnumbered),))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_collisions',?)", (str(collided),))
        conn.execute("INSERT OR REPLACE INTO sync_meta VALUES ('members_multi_scope',?)", (str(multi),))
    print("[done] %s · 갱신 %d건 · 번호 없음 %d · 번호 충돌 %d · 여러 scope 같은 사람 %d · 실패 %s"
          % (now, total, unnumbered, collided, multi, failed or "없음"))
    msg = alert_on_change(conn, failed, unnumbered, collided)
    if msg:
        print("[alert]", "보냄" if _tell_gm(msg) else "못 보냄(TG 키 없음)", "—", msg.splitlines()[0])
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
    assert classify_overlaps(conn) == (0, 0)
    replace_scope(conn, "archive", [rows[0]], "t2")  # 같은 사람(이름+전화 동일)이 LOSS보관에도 = 이력
    assert conn.execute("SELECT COUNT(*) FROM members WHERE member_no='M00001'").fetchone()[0] == 2, "같은 사람 두 scope 는 다 싣는다"
    assert classify_overlaps(conn) == (0, 1), "같은 사람은 충돌이 아니라 이력"
    replace_scope(conn, "archive", [dict(rows[0], 회원명="다른사람")], "t3")  # 같은 번호 다른 사람 = 충돌
    assert classify_overlaps(conn) == (1, 0), "이름+전화가 다르면 충돌"
    # 경보 — 같은 상태는 한 번만, 바뀌면 다시, 정상 복귀는 한 줄
    assert alert_on_change(conn, [], 0, 0) is None, "처음부터 정상이면 조용"
    m1 = alert_on_change(conn, ["valid"], 2, 0); assert m1 and "조회 실패" in m1 and "2명" in m1
    assert alert_on_change(conn, ["valid"], 2, 0) is None, "같은 이상은 반복하지 않는다"
    assert "충돌 1건" in alert_on_change(conn, ["valid"], 2, 1), "이상 내용이 바뀌면 다시 보낸다"
    assert "복귀" in alert_on_change(conn, [], 0, 0)
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
