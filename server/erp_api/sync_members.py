# -*- coding: utf-8 -*-
"""회원 시트 → 서버 PostgreSQL 미러 동기화 (읽기 전용 단방향) — 배 801 준비분 A.

sync_inquiries.py 와 같은 규칙이다. 원천은 화면들이 이미 쓰는 GAS 액션(member_active_list)을
그대로 부르고, 시트·GAS 는 절대 쓰지 않는다. 열쇠는 회원번호(M00001…) — 번호 없는 행은
미러에 넣지 않고 건수만 남긴다(전화·이름으로 사람을 찾던 구조로 되돌아가지 않기 위해).
정의서 = status/briefs/CPO-2026-09-03-회원미러-정의서.md

실행: python3 /srv/erp/api/sync_members.py   (cron 5분 · 시토 배치)
자체점검: python3 sync_members.py --selftest  (같은 DB 의 tenant 'selftest' · 네트워크 없음)
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, gas_get, load_env  # noqa: E402  — 같은 원천·같은 env·같은 DB

SCOPES = ["valid", "ended", "corp", "archive"]

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
    """한 scope 를 diff 삭제(이 배치에 없는 회원번호만) + upsert 로 갈아끼운다. 반환 = (넣은 건수, 회원번호 없어 뺀 건수).
    열쇠 = (회원번호, scope) — 같은 사람이 유효회원과 LOSS보관에 같은 번호로 함께 있는 것은 이력이라 다 싣는다.
    [2026-09-05 시토 · 배1039-A] 통째 DELETE→INSERT 였던 것을 upsert 로 바꿨다 — 회원 쓰기가 서버 원장에 먼저
    적히면(회원 원천 전환) 그 회원번호가 이번 GAS 배치에도 있는 한 사라지지 않는다.
    diff 삭제에 `synced_at <= now`(이 배치 시작 시각 · main() 이 gas_get 호출 전에 찍어 넘긴다) 조건을 더한다
    (배1054 검토⑤) — member_archive_restore(6단계)가 UPDATE 로 scope='archive'→'valid' 를 만드는 순간부터
    (synced_at=그 요청 시각) 이번 GAS 조회가 끝나기까지는 그 회원번호가 아직 이번 배치 목록에 없을 수 있다
    (GAS 쓰기는 서버 커밋 뒤에 도는 동기 호출이라 조회 시점이 딱 겹치면 못 실을 수 있다). 요청 시각이 항상
    이번 배치 시작보다 늦으므로(같은 사이클 안에서 만들어진 valid 행만 해당) synced_at 비교로 갈린다 —
    옛 행(진짜 사라져야 할 행)은 synced_at 이 이번 배치보다 훨씬 이전이라 그대로 지워진다."""
    recs, unnumbered = [], 0
    for r in rows:
        n = _norm_row(r)
        no = str(n.get("회원번호") or "").strip()
        if not re.fullmatch(r"M\d{5}", no):
            unnumbered += 1
            continue
        get = lambda k: (str(n.get(COLS[k]) or "").strip() or None)
        recs.append((
            db.TENANT, no, scope, get("name"), _phone(n.get(COLS["phone"])), get("kind"), get("kind2"),
            get("program"), get("reg_class"), get("reg_seq"), get("reg_date"), get("start_date"),
            get("end_date"), get("loss_date"), get("remain_days"), get("owner"),
            json.dumps(r, ensure_ascii=False), now,
        ))
    cols = ("name,phone,kind,kind2,program,reg_class,reg_seq,reg_date,start_date,end_date,"
            "loss_date,remain_days,owner,data,synced_at").split(",")
    member_nos = [r[1] for r in recs]
    with conn:
        if member_nos:
            conn.execute("DELETE FROM members WHERE tenant_id=%s AND scope=%s AND member_no <> ALL(%s) AND synced_at <= %s",
                        (db.TENANT, scope, member_nos, now))
        else:
            conn.execute("DELETE FROM members WHERE tenant_id=%s AND scope=%s AND synced_at <= %s", (db.TENANT, scope, now))
        conn.executemany(
            "INSERT INTO members (tenant_id,member_no,scope," + ",".join(cols) + ")"
            " VALUES (" + ",".join(["%s"] * (len(cols) + 3)) + ")"
            " ON CONFLICT (tenant_id,member_no,scope) DO UPDATE SET "
            + ", ".join("%s=EXCLUDED.%s" % (c, c) for c in cols), recs)
    return len(recs), unnumbered


def classify_overlaps(conn):
    """한 회원번호가 여러 scope 에 있는 경우를 가른다. 반환 = (충돌 건수, 같은 사람 이력 건수).
    충돌 = 같은 번호인데 이름+전화가 다른 사람(등기부 오류 — 시포가 재부여). 이력 = 같은 사람(정상)."""
    rows = conn.execute(
        "SELECT COUNT(DISTINCT COALESCE(name,'') || '|' || COALESCE(phone,'')) FROM members"
        " WHERE tenant_id=%s GROUP BY member_no HAVING COUNT(*) > 1", (db.TENANT,)).fetchall()
    collisions = sum(1 for (k,) in rows if k > 1)
    return collisions, len(rows) - collisions


OWNER_COLS = {   # api_members_write.FIELD_TO_COL 과 같은 5칸(역방향) + hold_status 1칸 — 늘리면 거기도 같이 고친다 (배1054)
    "owner_pt": "PT 담당자", "owner_golf": "골프 담당자", "owner_pl": "P.L 담당자",
    "owner_squash": "스쿼시 담당자", "owner_swim": "수영 담당자",
    "hold_status": "휴회접수상태",   # member_hold_approve·휴회복귀 등 아직 서버로 안 옮긴 GAS 경로가 계속 이 칸을 쓴다(배1054 검토①)
    # member_active_update(3단계) 신설 9칸 — api_members_write._ACTIVE_COL_MAP 뒤쪽 9개와 값이 같다(역방향).
    # replace_scope() COLS 목록에 없어(=매 sync 마다 손대지 않는 칸) owner_*·hold_status 와 같은 이유로
    # 여기서 data JSON 을 원천 삼아 되채워야 한다 — 안 넣으면 첫 백필(schema.sql) 이후 영원히 옛값으로 언다.
    "address": "주소", "note": "비고", "age": "나이",
    "reg_consult_date": "재등록상담 날짜", "reg_consult_time": "재등록상담 시간", "reg_consult_note": "재등록상담 내용",
    "reg_reservation": "재등록예약목록", "end_reason": "종료사유", "end_reason_memo": "종료사유메모",
    # member_hold_approve(4단계 · 배1054) 신설 5칸 — api_members_write.HOLD_APPROVE_COL_MAP 과 같은 값(역방향).
    # hold_status 는 위에서 이미 예외 처리(2단계) — 여기 5칸도 같은 규칙(서버가 쓴 (회원번호,칸)은 안 덮음).
    "hold_period": "휴회기간(휴회일수)", "hold_start_date": "휴회시작일", "hold_end_date": "휴회종료일",
    "hold_count": "휴회횟수", "hold_cum_days": "휴회누적일수",
}
_OWNER_SYNC_ACTIONS = ("member_owner_save", "member_hold_transition", "member_active_update", "member_hold_approve",
                       "member_archive_restore")


def sync_owner_cols(conn):
    """OWNER_COLS 의 실컬럼(owner_* 5칸·hold_status·member_active_update 신설 9칸)을 매 sync 마다 시트
    미러(data JSON)로 다시 채운다 — 서버가 아직 원천이 아닌 동안은 시트가 이긴다. schema.sql 의
    WHERE owner_* IS NULL 1회성 백필만으론 5분마다 갱신되는 data 와 실컬럼이 최초 배포 시점 스냅샷에
    얼어붙어 어긋난다(배1054 시포 실측: valid 991행 중 846행 불일치). 단 서버가 실제로 쓴 (회원번호,필드)는
    안 덮는다 — write_log 의 member_owner_save·member_hold_transition·member_active_update 성공행에서
    뽑는다(payload._member_no 는 애초에 대조용으로 넣어 둔 칸 · reconcile_dual_write.py 와 같은 재료).
    member_hold_transition 은 payload 에 'field' 키가 없다 — 액션 자체가 hold_status 칸을 가리키므로
    그 자리에 고정으로 채운다. member_active_update·member_hold_approve(4단계 · 승인만 — reject 는 회원
    원장을 안 건드려 member_no 자체가 없다)·member_archive_restore(6단계 경로B — 리셋한 17칸 라벨)는
    한 저장이 여러 칸을 동시에 바꿀 수 있어 'field' 한 칸이 아니라 payload._cols(실컬럼에 쓴 칸 이름
    목록 · api_members_write 가 넣어 둔다)를 본다. member_archive_restore 를 여기 넣는 이유 — GAS
    write-through 는 동기 호출이지만 그 직후 5분 배치가 도는 순간까지 짧은 창이 있고, 그 창에서 이
    행을 sync_owner_cols() 가 옛 archive data JSON(아직 안 갈렸다)으로 되채우면 방금 리셋한 값이
    되밀린다 — 예외로 빼면 다음 배치가 진짜 새 data 로 갈아낀 뒤에만 채워져 되밀림이 없다(배1054 검토②).
    반환 = 예외 아닌 행 중에도 남은 불일치 건수(0 이어야 정상 — 갱신 자체가 안 먹었다는 신호)."""
    field_to_col = {v: k for k, v in OWNER_COLS.items()}
    written = {col: set() for col in OWNER_COLS}
    for action, field, cols, member_no in conn.execute(
            "SELECT action, payload->>'field', payload->'_cols', payload->>'_member_no' FROM write_log"
            " WHERE tenant_id=%s AND action = ANY(%s) AND gas_status = 'ok'",
            (db.TENANT, list(_OWNER_SYNC_ACTIONS))):
        if not member_no:
            continue
        if action == "member_hold_transition":
            names = [OWNER_COLS["hold_status"]]
        elif action in ("member_active_update", "member_hold_approve", "member_archive_restore"):
            names = cols if isinstance(cols, list) else ([field] if field else [])
        else:
            names = [field] if field else []
        for nm in names:
            col = field_to_col.get(nm)
            if col:
                written[col].add(member_no)
    mismatch = 0
    with conn:
        for col, field in OWNER_COLS.items():
            skip = list(written[col])
            if skip:
                conn.execute(
                    ("UPDATE members SET {col}=data::jsonb->>%s WHERE tenant_id=%s AND scope='valid'"
                     " AND member_no <> ALL(%s)").format(col=col), (field, db.TENANT, skip))
                n = conn.execute(
                    ("SELECT COUNT(*) FROM members WHERE tenant_id=%s AND scope='valid' AND member_no <> ALL(%s)"
                     " AND COALESCE({col},'') <> COALESCE(data::jsonb->>%s,'')").format(col=col),
                    (db.TENANT, skip, field)).fetchone()[0]
            else:
                conn.execute(
                    "UPDATE members SET {col}=data::jsonb->>%s WHERE tenant_id=%s AND scope='valid'".format(col=col),
                    (field, db.TENANT))
                n = conn.execute(
                    ("SELECT COUNT(*) FROM members WHERE tenant_id=%s AND scope='valid'"
                     " AND COALESCE({col},'') <> COALESCE(data::jsonb->>%s,'')").format(col=col),
                    (db.TENANT, field)).fetchone()[0]
            mismatch += n
    return mismatch


def canon_drift(conn, hours=6):
    """서버가 쓴 수강반종목명이 GAS 가 쓴 것과 갈렸는지 센다(배1050 · 시토 제안 2026-09-09).

    member_registered_add 는 화면이 보낸 축약 종목명('플래티넘')을 정식명으로 펴서 저장한다. GAS 는
    유효회원 시트 열을 훑어 고르고(_memberProgramCanon_), 서버는 그 열의 거울을 훑어 고른다
    (api_members_write._program_canon) — 거울이 낡은 채로 계산하면 두 값이 갈릴 수 있다.

    ★'거울로 계산한 값 vs 서버 함수 값'을 맞춰 보는 대조는 두 쪽이 같은 재료라 늘 같게 나온다 —
    아무것도 못 잡는다. 그래서 여기서는 **서버가 그때 쓴 값**(member_change_log 의 등록 추가 이력)과
    **지금 막 시트에서 새로 뜬 거울 값**을 맞춘다. 이 함수는 replace_scope 직후에만 뜻이 있다.

    최근 %d시간 안의 등록 추가만 본다 — 그 뒤 다른 저장으로 종목이 정상적으로 바뀌었으면 갈린 것으로
    잘못 셀 수 있어 창을 짧게 잡는다(0 이 아니면 사람이 그 회원번호를 직접 본다)."""
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600 - hours * 3600))
    drift = []
    for r in conn.execute(
            "SELECT l.member_no, l.new_value, m.program FROM member_change_log l"
            " JOIN members m ON m.tenant_id=l.tenant_id AND m.member_no=l.member_no AND m.scope='valid'"
            " WHERE l.tenant_id=%s AND l.field='등록 추가' AND l.at>=%s", (db.TENANT, since)).fetchall():
        try:
            wrote = (json.loads(r["new_value"]) or {}).get("program")
        except Exception:
            continue
        if wrote and str(wrote).strip() != str(r["program"] or "").strip():
            drift.append(r["member_no"])
    return drift


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
    prev = db.meta_get(conn, "members_alert_fp") or ""
    if fp == prev:
        return None
    with conn:
        db.meta_set(conn, "members_alert_fp", fp)
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
    conn = db.connect()
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
    owner_mismatch = sync_owner_cols(conn)
    if owner_mismatch:
        _tell_gm("⚠️ 회원 실컬럼 정합 어긋남 — 시트 갱신 뒤에도 %d행 불일치(sync_members · 어긋난 칸=%s)"
                 % (owner_mismatch, ",".join(OWNER_COLS)))
    print("[parity] owner_* 불일치 %d행" % owner_mismatch)
    drift = canon_drift(conn)   # 서버가 편 종목명이 시트와 갈렸나(배1050) — 0 이면 조용하다
    print("[parity] 종목명 정규화 갈림 %d건%s" % (len(drift), (" · " + ",".join(drift[:5])) if drift else ""))
    collided, multi = classify_overlaps(conn)
    with conn:
        db.meta_set(conn, "members_canon_drift", ",".join(drift))
        db.meta_set(conn, "members_last_sync", now)
        db.meta_set(conn, "members_last_failed", ",".join(failed))
        db.meta_set(conn, "members_unnumbered", str(unnumbered))
        db.meta_set(conn, "members_collisions", str(collided))
        db.meta_set(conn, "members_multi_scope", str(multi))
    print("[done] %s · 갱신 %d건 · 번호 없음 %d · 번호 충돌 %d · 여러 scope 같은 사람 %d · 실패 %s"
          % (now, total, unnumbered, collided, multi, failed or "없음"))
    msg = alert_on_change(conn, failed, unnumbered, collided)
    if msg:
        print("[alert]", "보냄" if _tell_gm(msg) else "못 보냄(TG 키 없음)", "—", msg.splitlines()[0])
    conn.close()
    return 1 if failed else 0


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM members WHERE tenant_id=%s", (db.TENANT,))
        conn.execute("DELETE FROM sync_meta WHERE tenant_id=%s", (db.TENANT,))
    rows = [
        {"회원번호": "M00001", "회원명": "홍길동", "휴대폰 번호": "010-1234-5678", "등록\n일자": "2026-01-01"},
        {"회원번호": "M00002", "회원명": "김철수", "휴대폰 번호": "01098765432"},
        {"회원명": "번호없음", "휴대폰 번호": "010-0000-0000"},
    ]
    T = (db.TENANT,)
    try:
        assert replace_scope(conn, "valid", rows, "t0") == (2, 1), "회원번호 없는 행은 빼고 센다"
        assert conn.execute("SELECT phone FROM members WHERE tenant_id=%s AND member_no='M00001'", T).fetchone()[0] == "01012345678"
        assert conn.execute("SELECT reg_date FROM members WHERE tenant_id=%s AND member_no='M00001'", T).fetchone()[0] == "2026-01-01", \
            "줄바꿈 섞인 머리글도 같은 칸으로 읽는다"
        assert replace_scope(conn, "valid", rows[:1], "t1") == (1, 0), "같은 scope 는 통째로 교체"
        replace_scope(conn, "corp", rows[1:2], "t1")
        assert conn.execute("SELECT COUNT(*) FROM members WHERE tenant_id=%s", T).fetchone()[0] == 2, "다른 scope 가 남의 scope 를 지우면 안 된다"
        assert classify_overlaps(conn) == (0, 0)
        replace_scope(conn, "archive", [rows[0]], "t2")  # 같은 사람(이름+전화 동일)이 LOSS보관에도 = 이력
        assert conn.execute("SELECT COUNT(*) FROM members WHERE tenant_id=%s AND member_no='M00001'", T).fetchone()[0] == 2, "같은 사람 두 scope 는 다 싣는다"
        assert classify_overlaps(conn) == (0, 1), "같은 사람은 충돌이 아니라 이력"
        replace_scope(conn, "archive", [dict(rows[0], 회원명="다른사람")], "t3")  # 같은 번호 다른 사람 = 충돌
        assert classify_overlaps(conn) == (1, 0), "이름+전화가 다르면 충돌"
        # 경보 — 같은 상태는 한 번만, 바뀌면 다시, 정상 복귀는 한 줄
        assert alert_on_change(conn, [], 0, 0) is None, "처음부터 정상이면 조용"
        m1 = alert_on_change(conn, ["valid"], 2, 0); assert m1 and "조회 실패" in m1 and "2명" in m1
        assert alert_on_change(conn, ["valid"], 2, 0) is None, "같은 이상은 반복하지 않는다"
        assert "충돌 1건" in alert_on_change(conn, ["valid"], 2, 1), "이상 내용이 바뀌면 다시 보낸다"
        assert "복귀" in alert_on_change(conn, [], 0, 0)
        # owner_* 정합 — 시트가 이기되, 서버가 실제로 쓴 (회원번호,필드)는 안 덮는다(배1054)
        owner_rows = [
            {"회원번호": "M00003", "회원명": "황금성", "휴대폰 번호": "010-3333-3333", "PT 담당자": "최동오"},
            {"회원번호": "M00004", "회원명": "김보통", "휴대폰 번호": "010-4444-4444", "PT 담당자": "이보통"},
        ]
        replace_scope(conn, "valid", owner_rows, "t5")
        assert sync_owner_cols(conn) == 0, "갱신 직후엔 예외 없이 다 시트와 일치해야 한다"
        assert conn.execute("SELECT owner_pt FROM members WHERE tenant_id=%s AND member_no='M00003'", T).fetchone()[0] == "최동오"
        with conn:
            conn.execute("UPDATE members SET owner_pt=%s WHERE tenant_id=%s AND member_no='M00003'", ("이형진", db.TENANT))
            conn.execute(
                "INSERT INTO write_log (tenant_id,at,action,payload,user_email,gas_status) VALUES (%s,%s,'member_owner_save',%s,%s,'ok')",
                (db.TENANT, "t5", json.dumps({"field": "PT 담당자", "_member_no": "M00003"}, ensure_ascii=False), ""))
        assert sync_owner_cols(conn) == 0, "예외행 빼면 여전히 다 일치 — 예외행 자체는 안 세야 한다"
        assert conn.execute("SELECT owner_pt FROM members WHERE tenant_id=%s AND member_no='M00003'", T).fetchone()[0] == "이형진", \
            "서버가 쓴 행은 시트값(최동오)으로 안 덮인다"
        assert conn.execute("SELECT owner_pt FROM members WHERE tenant_id=%s AND member_no='M00004'", T).fetchone()[0] == "이보통", \
            "예외 아닌 행은 계속 시트를 따라간다"
        # hold_status 도 같은 예외 규칙 — member_hold_transition 행은 payload 에 field 키가 없다(배1054 검토①)
        hold_rows = [{"회원번호": "M00005", "회원명": "휴회테스트", "휴대폰 번호": "010-5555-5555", "휴회접수상태": "진행중"}]
        replace_scope(conn, "valid", owner_rows + hold_rows, "t6")
        assert sync_owner_cols(conn) == 0
        with conn:
            conn.execute("UPDATE members SET hold_status=%s WHERE tenant_id=%s AND member_no='M00005'", ("완료", db.TENANT))
            conn.execute(
                "INSERT INTO write_log (tenant_id,at,action,payload,user_email,gas_status) VALUES (%s,%s,'member_hold_transition',%s,%s,'ok')",
                (db.TENANT, "t6", json.dumps({"status": "완료", "_member_no": "M00005"}, ensure_ascii=False), ""))
        assert sync_owner_cols(conn) == 0, "hold_status 예외행도 빼면 여전히 일치"
        assert conn.execute("SELECT hold_status FROM members WHERE tenant_id=%s AND member_no='M00005'", T).fetchone()[0] == "완료", \
            "서버가 쓴 hold_status 는 시트값(진행중)으로 안 덮인다"
        # member_active_update(3단계 배1054) — 한 쓰기가 여러 신설 칸(주소·비고)을 동시에 바꾼다. payload
        # 에 'field' 한 칸이 아니라 '_cols'(목록)가 실려 온다(api_members_write._member_active_update_one).
        active_rows = [{"회원번호": "M00006", "회원명": "자유쓰기테스트", "휴대폰 번호": "010-6666-6666",
                        "주소": "서울시", "비고": "메모"}]
        replace_scope(conn, "valid", owner_rows + hold_rows + active_rows, "t7")
        assert sync_owner_cols(conn) == 0
        with conn:
            conn.execute("UPDATE members SET address=%s, note=%s WHERE tenant_id=%s AND member_no='M00006'",
                        ("부산시", "새메모", db.TENANT))
            conn.execute(
                "INSERT INTO write_log (tenant_id,at,action,payload,user_email,gas_status) VALUES (%s,%s,'member_active_update',%s,%s,'ok')",
                (db.TENANT, "t7", json.dumps({"_member_no": "M00006", "_cols": ["주소", "비고"]}, ensure_ascii=False), ""))
        assert sync_owner_cols(conn) == 0, "member_active_update 다건 예외도 나머지와 함께 일치해야 한다"
        an_row = conn.execute("SELECT address, note FROM members WHERE tenant_id=%s AND member_no='M00006'", T).fetchone()
        assert (an_row["address"], an_row["note"]) == ("부산시", "새메모"), \
            "서버가 쓴 신설 칸 다건은 시트값(서울시·메모)으로 안 덮인다"
        # member_hold_approve(4단계 배1054) — 승인 1건이 휴회 5칸(hold_status 포함 총 6칸 중 새 5칸)을 동시에
        # 바꾼다. member_active_update 와 같은 '_cols' 목록 규칙을 그대로 재사용(액션명만 다르다).
        hold_appr_rows = [{"회원번호": "M00007", "회원명": "휴회승인테스트", "휴대폰 번호": "010-7777-7777",
                           "휴회기간(휴회일수)": "2026-08-01 ~ 2026-08-30 (30일)", "휴회시작일": "2026-08-01",
                           "휴회종료일": "2026-08-30", "휴회횟수": "1", "휴회누적일수": "30"}]
        replace_scope(conn, "valid", owner_rows + hold_rows + active_rows + hold_appr_rows, "t8")
        assert sync_owner_cols(conn) == 0
        with conn:
            conn.execute(
                "UPDATE members SET hold_period=%s, hold_start_date=%s, hold_end_date=%s, hold_count=%s,"
                " hold_cum_days=%s WHERE tenant_id=%s AND member_no='M00007'",
                ("2026-08-05 ~ 2026-09-03 (30일)", "2026-08-05", "2026-09-03", "2", "60", db.TENANT))
            conn.execute(
                "INSERT INTO write_log (tenant_id,at,action,payload,user_email,gas_status) VALUES (%s,%s,'member_hold_approve',%s,%s,'ok')",
                (db.TENANT, "t8", json.dumps({"_member_no": "M00007", "_cols": [
                    "휴회기간(휴회일수)", "휴회시작일", "휴회종료일", "휴회횟수", "휴회누적일수"]}, ensure_ascii=False), ""))
        assert sync_owner_cols(conn) == 0, "member_hold_approve 다건 예외도 나머지와 함께 일치해야 한다"
        ah_row = conn.execute("SELECT hold_start_date, hold_count, hold_cum_days FROM members"
                              " WHERE tenant_id=%s AND member_no='M00007'", T).fetchone()
        assert (ah_row["hold_start_date"], ah_row["hold_count"], ah_row["hold_cum_days"]) == ("2026-08-05", "2", "60"), \
            "서버가 쓴 휴회 승인 5칸은 시트값(2026-08-01·1·30)으로 안 덮인다"
        # member_archive_restore(6단계 배1054) — 경로 B 가 리셋한 17칸(OWNER_COLS 교집합)도 같은 예외 규칙
        # (배1054 검토② — sync_owner_cols 되밀림 차단). 시트가 아직 옛 담당자·상태를 들고 있어도(짧은 창)
        # 서버가 방금 리셋한 빈값이 안 덮인다.
        arch_reset_rows = [{"회원번호": "M00008", "회원명": "복귀테스트", "휴대폰 번호": "010-8888-8888",
                            "PT 담당자": "옛담당자", "휴회접수상태": "완료"}]
        replace_scope(conn, "valid", owner_rows + hold_rows + active_rows + hold_appr_rows + arch_reset_rows, "t9")
        assert sync_owner_cols(conn) == 0, "예외 등록 전에는 시트값 그대로 일치해야 한다"
        with conn:
            conn.execute("UPDATE members SET owner_pt=%s, hold_status=%s WHERE tenant_id=%s AND member_no='M00008'",
                        ("", "", db.TENANT))
            conn.execute(
                "INSERT INTO write_log (tenant_id,at,action,payload,user_email,gas_status) VALUES (%s,%s,'member_archive_restore',%s,%s,'ok')",
                (db.TENANT, "t9", json.dumps({"_member_no": "M00008", "_cols": ["PT 담당자", "휴회접수상태"]}, ensure_ascii=False), ""))
        assert sync_owner_cols(conn) == 0, "member_archive_restore 리셋 예외도 나머지와 함께 일치해야 한다"
        row8 = conn.execute("SELECT owner_pt, hold_status FROM members WHERE tenant_id=%s AND member_no='M00008'", T).fetchone()
        assert (row8["owner_pt"], row8["hold_status"]) == ("", ""), \
            "서버가 리셋한 값은 시트에 남은 옛값(옛담당자·완료)으로 안 덮인다"
        # replace_scope diff-삭제 synced_at 가드(배1054 검토⑤) — 배치 시작(now) '뒤' 서버가 만든 valid 행은
        # 이번 배치 목록에 없어도 지우면 안 된다(member_archive_restore 가 scope='archive'→'valid' 로 만든
        # 새 valid 열쇠가 GAS write-through 완료 전에 sync 가 mid-fetch 로 겹치는 race 대비).
        with conn:
            conn.execute(
                "INSERT INTO members (tenant_id,member_no,scope,name,phone,data,synced_at) VALUES"
                " (%s,'M00777','valid','늦은복귀','01077777777','{}',%s)"
                " ON CONFLICT (tenant_id,member_no,scope) DO UPDATE SET synced_at=EXCLUDED.synced_at",
                (db.TENANT, "t9-late"))   # "t9-late" > "t9"(사전순) — 아래 배치 시작 시각보다 늦다
        replace_scope(conn, "valid", owner_rows + hold_rows + active_rows + hold_appr_rows + arch_reset_rows, "t9")
        assert conn.execute("SELECT COUNT(*) FROM members WHERE tenant_id=%s AND member_no='M00777'", T).fetchone()[0] == 1, \
            "배치 시작보다 늦게 서버가 만든 valid 행은 배치 목록에 없어도 지워지면 안 된다"
        # canon_drift(배1050) — 서버가 쓴 종목명이 방금 뜬 거울과 다르면 그 회원번호를 잡아낸다.
        now_kst = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
        with conn:
            conn.execute(
                "INSERT INTO members (tenant_id,member_no,scope,name,phone,program,data,synced_at) VALUES"
                " (%s,'M00888','valid','정규화','01088888888','플래티넘(정)6개월','{}',%s)"
                " ON CONFLICT (tenant_id,member_no,scope) DO UPDATE SET program=EXCLUDED.program",
                (db.TENANT, now_kst))
            conn.execute(
                "INSERT INTO member_change_log (tenant_id,at,staff,member_no,member_name,phone_masked,"
                " field,old_value,new_value,screen) VALUES (%s,%s,'자동','M00888','정규화','010-8888-****',"
                " '등록 추가','{}',%s,'멤버십')",
                (db.TENANT, now_kst, json.dumps({"program": "플래티넘(정)12개월"}, ensure_ascii=False)))
        assert canon_drift(conn) == ["M00888"], "서버가 쓴 종목명과 시트 거울이 다르면 잡아야 한다"
        with conn:
            conn.execute("UPDATE members SET program=%s WHERE tenant_id=%s AND member_no='M00888'",
                        ("플래티넘(정)12개월", db.TENANT))
        assert canon_drift(conn) == [], "같으면 조용해야 한다"
    finally:
        with conn:
            conn.execute("DELETE FROM members WHERE tenant_id=%s", T)
            conn.execute("DELETE FROM sync_meta WHERE tenant_id=%s", T)
            conn.execute("DELETE FROM write_log WHERE tenant_id=%s", T)
            conn.execute("DELETE FROM member_change_log WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
