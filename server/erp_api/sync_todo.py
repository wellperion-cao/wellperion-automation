# -*- coding: utf-8 -*-
"""업무·결재 SSOT(todo_list 시트) → 서버 PostgreSQL 미러 동기화 (읽기 전용 단방향 · 배 922 레인 T).

원천 = 업무 현황 SSOT 화면이 부르는 GAS todo_list 그대로(include_gm=1 · GM 행 포함 — 결재 SSOT 와 같은 조회).
시트·GAS 는 절대 쓰지 않는다. 화면·GAS 는 나우열M 소유라 여기서는 읽기만 한다.
표 2개: todo_items(전 항목) · approvals(결재요청이 있는 항목). 열쇠 = 항목 id(TODO-…), 행번호 아님.

실행: python3 /srv/erp/api/sync_todo.py   (cron 5분 · /etc/cron.d/erp-todo-sync)
자체점검: python3 sync_todo.py --selftest  (tenant 'selftest' 로 교체·집계 로직만 확인, 네트워크 없음)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

ENV_FILE = os.environ.get("ERP_API_ENV", "/srv/erp/api.env")

# home 업무 카드(wellperion_guide(main).html loadHomeKpiOps STAFF)와 같은 실무진 목록 — 집계 정의 동일.
STAFF = ["이경연 실장", "나우열M", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "이정헌 소장"]
# 카테고리 번호 → 부서 (결재선 규칙: 운영부 [1][4] · 시설부 [5] · 파트너팀 [2][3] · 그 외는 부서장 생략)
# ponytail: 번호만 본다 — 카테고리 이름이 바뀌어도 번호는 유지된다는 전제. 어긋나면 이 표 한 줄만 고친다.
CAT_DEPT = {"1": "운영부", "4": "운영부", "5": "시설부", "2": "파트너팀", "3": "파트너팀"}


def load_env():
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def gas_todo_list(timeout=90):
    """todo_list 1회(GM 행 포함). 성공 시 행 리스트, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("TODO_GAS_URL", "")
    if not url:
        raise SystemExit("TODO_GAS_URL 없음 — %s 를 확인" % ENV_FILE)
    q = {"action": "todo_list", "include_gm": "1", "gmkey": os.environ.get("GM_TODO_KEY", "")}
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] todo_list 조회 실패: %s: %s" % (type(e).__name__, str(e)[:120]))
        return None
    if not data.get("ok") or not isinstance(data.get("data"), list):
        print("[warn] todo_list 응답 ok=false")
        return None
    return data["data"]


def _s(v):
    return str(v if v is not None else "").strip()


def status_of(r):
    return _s(r.get("상태")) or "진행중"          # 화면 getStatus 와 같다 — 빈칸은 진행중


def created_of(r):
    return _s(r.get("생성일"))[:10]              # 화면 getCreated 와 같다 — 앞 10자


def dept_of(r):
    m = re.match(r"\[(\d+)\]", _s(r.get("카테고리")))
    return CAT_DEPT.get(m.group(1), "") if m else ""


def is_staff(owner):
    return any(x.strip() in STAFF for x in _s(owner).split(","))


def replace_all(conn, rows, now):
    """두 표를 diff 삭제(이 배치에 없는 id 만) + upsert 로 갈아끼운다 — 시트가 정본이라 미러는 원천과 같아야 한다.
    호출부가 '조회 성공 + 행 있음'을 확인한 뒤에만 부른다(빈 값으로 지우지 않기 위해).
    [2026-09-05 시토 · 배1039-A] 통째 DELETE→INSERT 였던 것을 upsert 로 바꿨다 — 서버가 이 표에 직접 쓰면
    그 id 가 이번 배치에도 있는 한 사라지지 않는다."""
    todos, apprs = [], []
    for r in rows:
        key = _s(r.get("id"))
        if not key:
            continue
        data = json.dumps(r, ensure_ascii=False)
        todos.append((db.TENANT, key, _s(r.get("업무명")), _s(r.get("카테고리")), dept_of(r), _s(r.get("담당자")),
                      status_of(r), _s(r.get("생성자")), created_of(r), _s(r.get("수정일")),
                      _s(r.get("시작일"))[:10], _s(r.get("종료일"))[:10], _s(r.get("완료일"))[:10], data, now))
        if _s(r.get("결재요청")):
            apprs.append((db.TENANT, key, _s(r.get("업무명")), _s(r.get("담당자")), _s(r.get("결재요청")),
                          _s(r.get("결재상태")), _s(r.get("부서장싸인")), _s(r.get("GM싸인")), _s(r.get("대표싸인")),
                          _s(r.get("결재완료시각")), created_of(r), data, now))
    todo_ids = [t[1] for t in todos]
    appr_ids = [a[1] for a in apprs]
    with conn:
        if todo_ids:
            conn.execute("DELETE FROM todo_items WHERE tenant_id=%s AND id <> ALL(%s)", (db.TENANT, todo_ids))
        else:
            conn.execute("DELETE FROM todo_items WHERE tenant_id=%s", (db.TENANT,))
        if appr_ids:
            conn.execute("DELETE FROM approvals WHERE tenant_id=%s AND id <> ALL(%s)", (db.TENANT, appr_ids))
        else:
            conn.execute("DELETE FROM approvals WHERE tenant_id=%s", (db.TENANT,))
        conn.executemany(
            "INSERT INTO todo_items (tenant_id,id,title,category,dept,owner,status,creator,created,modified,"
            "start_date,end_date,done_date,data,synced_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id,id) DO UPDATE SET title=EXCLUDED.title, category=EXCLUDED.category,"
            " dept=EXCLUDED.dept, owner=EXCLUDED.owner, status=EXCLUDED.status, creator=EXCLUDED.creator,"
            " created=EXCLUDED.created, modified=EXCLUDED.modified, start_date=EXCLUDED.start_date,"
            " end_date=EXCLUDED.end_date, done_date=EXCLUDED.done_date, data=EXCLUDED.data,"
            " synced_at=EXCLUDED.synced_at", todos)
        conn.executemany(
            "INSERT INTO approvals (tenant_id,id,title,owner,approvers,appr_status,sign_head,sign_gm,sign_ceo,"
            "completed_at,created,data,synced_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id,id) DO UPDATE SET title=EXCLUDED.title, owner=EXCLUDED.owner,"
            " approvers=EXCLUDED.approvers, appr_status=EXCLUDED.appr_status, sign_head=EXCLUDED.sign_head,"
            " sign_gm=EXCLUDED.sign_gm, sign_ceo=EXCLUDED.sign_ceo, completed_at=EXCLUDED.completed_at,"
            " created=EXCLUDED.created, data=EXCLUDED.data, synced_at=EXCLUDED.synced_at", apprs)
    return len(todos), len(apprs)


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)                        # 멱등 — 새 표가 없으면 만든다
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))   # 서버는 UTC · 기록은 KST
    rows = gas_todo_list()
    ok = bool(rows)
    if ok:
        n, a = replace_all(conn, rows, now)
        print("[ok] 업무 %d건 · 결재 %d건" % (n, a))
    with conn:
        if ok:
            db.meta_set(conn, "todo_last_sync", now)
        db.meta_set(conn, "todo_last_failed", "" if ok else now)
    conn.close()
    print("[done] %s · %s" % (now, "정상" if ok else "실패 — 기존 미러 유지"))
    return 0 if ok else 1


def selftest():
    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    db.init_schema(conn)
    rows = [{"id": "TODO-1", "업무명": "a", "카테고리": "[5] 시설 및 환경", "담당자": "이정헌 소장",
             "생성일": "2026-09-01T00:00:00.000Z", "결재요청": "이정헌 소장, 김남욱GM"},
            {"id": "TODO-2", "업무명": "b", "카테고리": "[1] 매출 및 영업", "담당자": "김남욱GM, 이경연 실장", "상태": "완료",
             "생성일": "2026-08-01T00:00:00.000Z"},
            {"업무명": "id없음"}]
    T = (db.TENANT,)
    try:
        assert replace_all(conn, rows, "t0") == (2, 1), "id 없는 행은 버린다 · 결재요청 있는 행만 approvals"
        r = conn.execute("SELECT dept, status, created FROM todo_items WHERE tenant_id=%s AND id='TODO-1'", T).fetchone()
        assert (r["dept"], r["status"], r["created"]) == ("시설부", "진행중", "2026-09-01"), "부서 매핑·빈 상태=진행중·생성일 10자"
        assert is_staff("김남욱GM, 이경연 실장") and not is_staff("김남욱GM"), "쉼표 담당자 중 실무진 하나면 실무진"
        assert replace_all(conn, rows[:1], "t1") == (1, 1), "통째로 교체"
        assert conn.execute("SELECT COUNT(*) FROM todo_items WHERE tenant_id=%s", T).fetchone()[0] == 1
    finally:
        with conn:
            conn.execute("DELETE FROM todo_items WHERE tenant_id=%s", T)
            conn.execute("DELETE FROM approvals WHERE tenant_id=%s", T)
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
