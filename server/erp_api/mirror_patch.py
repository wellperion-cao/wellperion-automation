# -*- coding: utf-8 -*-
"""server 모드 업무·결재 쓰기를 서버 거울(todo_items·approvals)에 그 자리에서 반영 (2026-09-10 시토).

왜 필요한가 — api_write.write() 는 origin_switch 가 server 인 영역에서 서버 원장(write_log)에만 적고 즉시
답한다. 시트는 pushback.py(1분 cron)가 되밀고 그 뒤에야 sync_todo.py 가 거울을 다시 뜬다. 그 사이 최대
1분간 화면엔 저장 전 값이 그대로라, 실무진이 "저장이 안 됐네" 하고 다시 눌러 중복 행을 만든다.
그래서 접수처(api_reception.py)가 이미 쓰는 모양 그대로 — 서버가 쓰기를 받는 순간 서버 표를 직접 고친다.

★안전한 이유: 여기서 고치는 것은 **거울 한 곳뿐이고 시트에는 손대지 않는다.** 이 반영이 틀려도 1분 뒤
  sync_todo.py 가 GAS 판으로 전량을 덮어써 스스로 낫는다. 그래서 모르는 액션·못 찾는 행·관문 미통과는
  전부 조용히 False 다 — 예외를 밖으로 내지 않는다(거울 반영 실패가 저장을 막으면 안 된다).

칸 이름·부서 매핑·상태 기본값은 sync_todo 의 것을 그대로 쓴다(_row_tuples·status_of·dept_of·created_of).
각 액션이 어느 칸을 어떤 값으로 바꾸는지는 업무 GAS 원본 `.deploy-todo/업무&결재 현황.js` 의
_processTodoAction(2734줄~) 을 읽어 같은 뜻으로 옮긴 것이다 — 아래 각 함수 주석에 그 자리를 적어 둔다.

자체점검: python3 mirror_patch.py   (DB·서버 없이 가짜 conn 으로 액션별 칸 변화를 확인)
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402
import sync_todo  # noqa: E402  — 칸 뽑는 규칙 정본(_row_tuples·upsert_rows)

# GAS TODO_HEADERS(업무&결재 현황.js 54줄) — todo_update 가 훑는 칸 전수. JSON 이라 순서는 안 쓴다.
HEADERS = ("id", "업무명", "카테고리", "담당자", "시작일", "종료일", "내용", "상태", "결재요청", "링크",
           "파일URL", "생성자", "생성일", "수정일", "부서장싸인", "GM싸인", "대표싸인", "결재상태",
           "결재완료시각", "결과보고서URL", "난이도", "완료일", "결재의견", "보류사유", "재개조건", "규모점수")
# GAS _mapFields(2719줄) — 화면이 영문 키로 보내는 것을 한글 칸 이름으로. 한글 칸에 이미 값이 있으면 무시(같은 규칙).
FIELD_ALIAS = {"title": "업무명", "name": "업무명", "category": "카테고리", "owner": "담당자",
               "startDate": "시작일", "endDate": "종료일", "content": "내용", "status": "상태",
               "approval": "결재요청", "link": "링크", "fileUrl": "파일URL", "creator": "생성자",
               "difficulty": "난이도", "sizeScore": "규모점수"}
# 서버가 거울에 못 옮기는 쓰기 — 값을 지어내지 않고 1분 뒤 sync 에 맡긴다(api_write 자체점검이 이 표를 본다).
NO_MIRROR = {
    "approval_rep_sign_upload": "대표싸인 칸에 들어갈 값이 구글 드라이브 업로드 결과 주소다 — 서버는 그 주소를 모른다",
}
_SIGN_COL = {"부서장": "부서장싸인", "GM": "GM싸인"}
_MID = ("이경연 실장", "이정헌 소장", "나우열M")
# GAS _buildApprovalRoute(865줄) 의 예산 마커 — 결재요청이 비어도 이게 있으면 결재선이 선다.
_BUDGET_RE = re.compile(r"===BUDGET===\s*\n[^|]+\|\s*\d+")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))   # 서버는 UTC · 기록은 KST


def _s(v):
    return str(v if v is not None else "").strip()


def _mapped(payload):
    """GAS _mapFields 와 같은 뜻 — 영문 별칭을 한글 칸으로. 한글 칸에 이미 값이 있으면 덮지 않는다."""
    p = dict(payload or {})
    for en, ko in FIELD_ALIAS.items():
        if p.get(en) is not None and not p.get(ko):
            p[ko] = p[en]
    return p


def _ops(data):
    """결재의견 칸(JSON 배열) 파싱 — 깨져 있으면 빈 배열(GAS 도 try/catch 로 같은 판정)."""
    try:
        v = json.loads(_s(data.get("결재의견")) or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def approval_route(rec):
    """GAS _buildApprovalRoute(865줄) — (명시 체크한 부서장) → GM. 담당자가 김남욱GM 이면 부서장 단계 생략."""
    manual = [s.strip() for s in _s(rec.get("결재요청")).split(",") if s.strip()]
    if not manual and not _BUDGET_RE.search(str(rec.get("내용") or "")):
        return []
    mid = ([m for m in manual if m in _MID] or [""])[0]
    owners = [s.strip() for s in _s(rec.get("담당자")).split(",")]
    route = []
    if mid and "김남욱GM" not in owners:
        route.append("부서장")
    route.append("GM")
    return route


def next_approver(rec, route, role):
    """GAS _nextApprover(922줄) — 서명자가 결재선 마지막이면 앞 단계 미서명이 있어도 최종(None)."""
    if not route:
        return None
    if role and route[-1] == role:
        return None
    for r in route:
        if not _s(rec.get(_SIGN_COL[r])):
            return r
    return None


# ─── 액션별 칸 변경 — 각 함수는 data(거울 행 JSON)를 고친다. False 를 돌려주면 반영하지 않는다. ───
#     수정일 은 apply() 가 공통으로 찍는다(GAS 도 모든 쓰기에서 찍는다).

def _update(data, p, now):
    """GAS todo_update(2848줄) — 빈 문자열은 기존값 보존, 완료면 완료일 스탬프, 결재요청이 새로 바뀌면 결재상태 대기."""
    prev_appr = _s(data.get("결재요청"))
    appr_status = _s(data.get("결재상태"))
    for h in HEADERS:
        if h in ("id", "생성일", "생성자"):
            continue
        if p.get(h) is not None and p.get(h) != "":
            data[h] = p[h]
    if _s(data.get("상태")) == "완료" and not _s(data.get("완료일")):
        data["완료일"] = now[:10]
    # 결재요청이 실제로 바뀌었을 때만: 미설정·대기는 대기 유지, 반려는 대기로 되살린다(재상신 = 부서장부터).
    if _s(data.get("결재요청")) and _s(data.get("결재요청")) != prev_appr and (
            appr_status in ("", "대기") or "반려" in appr_status):
        data["결재상태"] = "대기"


def _done(data, p, now):
    """GAS todo_done(3118줄) — 상태 완료 + 완료일은 비어 있을 때만 스탬프."""
    data["상태"] = "완료"
    if not _s(data.get("완료일")):
        data["완료일"] = now[:10]


def _sign(data, p, now):
    """GAS todo_sign(2901줄) — 승인은 싸인 칸 + 다음 결재자 유무로 결재상태, 반려는 싸인·결재요청 초기화.
    ⚠️ PIN 검증은 여기서 하지 않는다(GAS 가 되밀기 때 검증한다) — 거울은 GAS 판정에 1분 뒤 맞춰진다."""
    role, decision = _s(p.get("role")), _s(p.get("decision"))
    signer = _s(p.get("signer")) or role
    col = _SIGN_COL.get(role)
    if not col or decision not in ("approve", "reject"):
        return False
    if decision == "reject":
        for k in ("부서장싸인", "GM싸인", "대표싸인", "결재완료시각", "결재요청"):
            data[k] = ""      # 결재요청을 비워 업무현황으로 복귀시킨다(결재선 잠금해제)
        data["결재상태"] = role + " 반려"
        reason = _s(p.get("reason"))
        if reason:
            prev = str(data.get("내용") or "")
            data["내용"] = prev + ("\n" if prev else "") + "===반려이력===\n[%s %s] %s" % (now[:10], role, reason)
        return
    data[col] = now + ((" (%s)" % signer) if signer and signer != role else "")
    if next_approver(data, approval_route(data), role):
        data["결재상태"] = role + " 완료"
    else:
        data["결재상태"] = "결재완료"
        data["결재완료시각"] = now
        data["상태"] = "완료"          # 최종 승인 = 업무도 완료 이관(GAS 와 같다)
        data["완료일"] = now[:10]


def _opinion(data, p, now):
    """GAS todo_opinion(3013줄) — 결재의견 JSON 배열에 append."""
    role, text = _s(p.get("role")), _s(p.get("text"))
    if not role or not text:
        return False
    ops = _ops(data)
    ops.append({"role": role, "name": _s(p.get("name")) or role, "time": now, "text": text})
    data["결재의견"] = json.dumps(ops, ensure_ascii=False)


def _opinion_delete(data, p, now):
    """GAS todo_opinion_delete(3055줄) — idx 하나 제거, 남는 게 없으면 빈 칸."""
    try:
        idx = int(_s(p.get("idx")))
    except ValueError:
        return False
    ops = _ops(data)
    if idx < 0 or idx >= len(ops):
        return False
    ops.pop(idx)
    data["결재의견"] = json.dumps(ops, ensure_ascii=False) if ops else ""


def _reset(data, p, now):
    """GAS todo_reset(3078줄) — 결재요청 전으로 복원(업무현황에서 수정 가능)."""
    for k in ("결재요청", "부서장싸인", "GM싸인", "대표싸인", "결재상태", "결재완료시각"):
        data[k] = ""


def _remove_file(data, p, now):
    """GAS todo_remove_file(3229줄) — 파일URL 줄 목록에서 그 주소만 뺀다(드라이브 원본은 GAS 가 지운다)."""
    url = _s(p.get("url"))
    if not url:
        return False
    lines = [u.strip() for u in str(data.get("파일URL") or "").split("\n")]
    data["파일URL"] = "\n".join([u for u in lines if u and u != url])


def _rep_escalate(data, p, now):
    """GAS approval_rep_escalate(3168줄) — GM 결재완료 건만, 이미 서명본(URL)이면 거부."""
    if _s(data.get("결재상태")) != "결재완료":
        return False
    if re.match(r"^https?://", _s(data.get("대표싸인"))):
        return False
    data["대표싸인"] = "PENDING"


def _rep_cancel(data, p, now):
    """GAS approval_rep_cancel(3210줄) — 대표 올림 취소."""
    data["대표싸인"] = ""


HANDLERS = {
    "todo_update": _update,
    "todo_done": _done,
    "todo_delete": None,          # 행 삭제 — apply() 가 직접 처리한다(고칠 data 가 없다)
    "todo_sign": _sign,
    "todo_opinion": _opinion,
    "todo_opinion_delete": _opinion_delete,
    "todo_reset": _reset,
    "todo_remove_file": _remove_file,
    "approval_rep_escalate": _rep_escalate,
    "approval_rep_cancel": _rep_cancel,
}
# todo_add 는 여기 없다 — 새 업무 id 를 GAS 가 매기므로 server 모드 자체에서 빠진다(api_write.NO_SERVER_ACTIONS).


def apply(conn, action, payload):
    """server 모드 쓰기를 서버 거울(todo_items)에 그 자리에서 반영. 반영했으면 True.
    모르는 액션·못 찾는 행은 그냥 False — 절대 예외를 밖으로 내지 않는다."""
    if action not in HANDLERS:
        return False
    tid = _s((payload or {}).get("id"))
    if not tid:
        return False
    if action == "todo_delete":
        with conn:
            conn.execute("DELETE FROM todo_items WHERE tenant_id=%s AND id=%s", (db.TENANT, tid))
            conn.execute("DELETE FROM approvals WHERE tenant_id=%s AND id=%s", (db.TENANT, tid))
        return True
    row = conn.execute("SELECT data FROM todo_items WHERE tenant_id=%s AND id=%s", (db.TENANT, tid)).fetchone()
    if not row:
        return False       # 거울에 없는 업무 — 지어내지 않는다(1분 뒤 sync 가 GAS 판으로 채운다)
    data = row["data"] if isinstance(row["data"], dict) else json.loads(row["data"])
    now = _now()
    if HANDLERS[action](data, _mapped(payload), now) is False:
        return False       # 관문 미통과 — GAS 도 거부할 요청이다. 거울을 건드리지 않는다.
    data["수정일"] = now
    sync_todo.upsert_rows(conn, [data], now)
    return True


if __name__ == "__main__":   # python3 mirror_patch.py — DB·서버 없이 액션별 칸 변화 자체점검
    class _Conn:
        """가짜 conn — todo_items·approvals 두 표를 dict 로 흉내(api_write.py 자체점검의 가짜 conn 과 같은 방식)."""

        def __init__(self, rows):
            self.todos = dict((r["id"], json.dumps(r, ensure_ascii=False)) for r in rows)
            self.appr = set(r["id"] for r in rows if _s(r.get("결재요청")))

        def execute(self, q, p=None):
            self._q, self._p = q, p
            if q.lstrip().startswith("DELETE"):
                ids = p[1] if isinstance(p[1], list) else [p[1]]
                for i in ids:
                    if "todo_items" in q:
                        self.todos.pop(i, None)
                    else:
                        self.appr.discard(i)
            return self

        def fetchone(self):
            return {"data": self.todos[self._p[1]]} if self._p[1] in self.todos else None

        def executemany(self, q, seq):
            for t in seq:
                if "todo_items" in q:
                    self.todos[t[1]] = t[13]
                else:
                    self.appr.add(t[1])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def row(self, tid):
            return json.loads(self.todos[tid])

    def _fresh(**over):
        r = dict((h, "") for h in HEADERS)   # GAS _readAll 은 늘 전 칸을 채워 준다 — 같은 모양으로 시작
        r.update({"id": "TODO-1", "업무명": "유리문 수리", "카테고리": "[5] 시설 및 환경", "담당자": "이정헌 소장",
                  "상태": "진행중", "생성일": "2026-09-01", "생성자": "이정헌 소장", "내용": "본문",
                  "시작일": "2026-09-01", "종료일": "2026-09-30", "파일URL": "u1\nu2"})
        r.update(over)
        return _Conn([r])

    # ① 모르는 액션·id 없음·거울에 없는 행 = 조용히 False (예외 없음)
    assert apply(_fresh(), "todo_add", {"id": "TODO-1"}) is False
    assert apply(_fresh(), "drop_table", {"id": "TODO-1"}) is False
    assert apply(_fresh(), "todo_done", {}) is False
    assert apply(_fresh(), "todo_done", {"id": "TODO-없음"}) is False

    # ② todo_update — 영문 별칭 매핑 · 빈 문자열은 기존값 보존 · id/생성자 불변
    c = _fresh()
    assert apply(c, "todo_update", {"id": "TODO-1", "status": "보류", "title": "", "creator": "남"}) is True
    r = c.row("TODO-1")
    assert r["상태"] == "보류" and r["업무명"] == "유리문 수리" and r["생성자"] == "이정헌 소장", r
    assert r["수정일"] == _now() and len(r["수정일"]) == 19, r["수정일"]   # 모든 쓰기가 수정일을 찍는다

    # ③ todo_update 로 완료 — 완료일 자동 스탬프. 이미 있으면 보존.
    c = _fresh()
    apply(c, "todo_update", {"id": "TODO-1", "status": "완료"})
    assert c.row("TODO-1")["완료일"] == _now()[:10]
    c = _fresh(완료일="2026-08-01")
    apply(c, "todo_update", {"id": "TODO-1", "status": "완료"})
    assert c.row("TODO-1")["완료일"] == "2026-08-01"

    # ④ todo_update 로 결재요청 신규 — 결재상태 대기 + approvals 표에 편입
    c = _fresh()
    assert "TODO-1" not in c.appr
    apply(c, "todo_update", {"id": "TODO-1", "approval": "이정헌 소장, 김남욱GM"})
    assert c.row("TODO-1")["결재상태"] == "대기" and "TODO-1" in c.appr
    # 반려 상태에서 결재요청을 바꾸면 다시 대기(재상신). 안 바뀌면 반려 흔적 보존.
    c = _fresh(결재요청="이정헌 소장", 결재상태="GM 반려")
    apply(c, "todo_update", {"id": "TODO-1", "내용": "고쳐 씀"})
    assert c.row("TODO-1")["결재상태"] == "GM 반려"
    apply(c, "todo_update", {"id": "TODO-1", "approval": "이정헌 소장, 김남욱GM"})
    assert c.row("TODO-1")["결재상태"] == "대기"

    # ⑤ todo_done
    c = _fresh()
    assert apply(c, "todo_done", {"id": "TODO-1"}) is True
    assert c.row("TODO-1")["상태"] == "완료" and c.row("TODO-1")["완료일"] == _now()[:10]

    # ⑥ todo_delete — 두 표에서 사라진다
    c = _fresh(결재요청="이정헌 소장")
    assert "TODO-1" in c.appr
    assert apply(c, "todo_delete", {"id": "TODO-1"}) is True
    assert c.todos == {} and c.appr == set()

    # ⑦ todo_sign 승인 — 부서장 싸인 뒤 GM 이 남으면 '부서장 완료', GM 이 서명하면 결재완료+업무완료
    c = _fresh(결재요청="이정헌 소장, 김남욱GM", 결재상태="대기")
    assert apply(c, "todo_sign", {"id": "TODO-1", "role": "부서장", "decision": "approve",
                                  "signer": "이정헌 소장"}) is True
    r = c.row("TODO-1")
    assert r["결재상태"] == "부서장 완료" and r["부서장싸인"].endswith("(이정헌 소장)"), r
    assert r["상태"] == "진행중" and not r["결재완료시각"]
    assert apply(c, "todo_sign", {"id": "TODO-1", "role": "GM", "decision": "approve"}) is True
    r = c.row("TODO-1")
    assert r["결재상태"] == "결재완료" and r["결재완료시각"] and r["상태"] == "완료"
    assert r["완료일"] == _now()[:10] and r["GM싸인"] and "(" not in r["GM싸인"]
    # 담당자가 GM 이면 부서장 단계 생략 — GM 한 번으로 결재완료
    c = _fresh(담당자="김남욱GM", 결재요청="이정헌 소장, 김남욱GM")
    apply(c, "todo_sign", {"id": "TODO-1", "role": "GM", "decision": "approve"})
    assert c.row("TODO-1")["결재상태"] == "결재완료"
    # 알 수 없는 결재자·결정은 거울을 안 건드린다
    assert apply(_fresh(), "todo_sign", {"id": "TODO-1", "role": "대표님", "decision": "approve"}) is False
    assert apply(_fresh(), "todo_sign", {"id": "TODO-1", "role": "GM", "decision": ""}) is False

    # ⑧ todo_sign 반려 — 싸인·결재요청 초기화 + 내용에 반려이력 append + approvals 에서 빠진다
    c = _fresh(결재요청="이정헌 소장, 김남욱GM", 결재상태="부서장 완료", 부서장싸인="2026-09-09 10:00:00")
    assert "TODO-1" in c.appr
    assert apply(c, "todo_sign", {"id": "TODO-1", "role": "GM", "decision": "reject", "reason": "예산 초과"}) is True
    r = c.row("TODO-1")
    assert r["결재상태"] == "GM 반려" and r["결재요청"] == "" and r["부서장싸인"] == ""
    assert r["상태"] == "진행중" and "===반려이력===" in r["내용"] and "예산 초과" in r["내용"]
    assert "TODO-1" not in c.appr, "결재요청이 비었으면 결재 표에서도 빠져야 한다"

    # ⑨ 결재의견 append·삭제
    c = _fresh()
    assert apply(c, "todo_opinion", {"id": "TODO-1", "role": "GM", "text": "확인함"}) is True
    ops = json.loads(c.row("TODO-1")["결재의견"])
    assert len(ops) == 1 and ops[0]["role"] == "GM" and ops[0]["name"] == "GM" and ops[0]["text"] == "확인함"
    assert apply(c, "todo_opinion", {"id": "TODO-1", "role": "부서장", "name": "이정헌 소장", "text": "동의"}) is True
    assert len(json.loads(c.row("TODO-1")["결재의견"])) == 2
    assert apply(c, "todo_opinion", {"id": "TODO-1", "role": "GM", "text": ""}) is False   # 빈 의견은 거부
    assert apply(c, "todo_opinion_delete", {"id": "TODO-1", "idx": 5}) is False            # 범위 밖
    assert apply(c, "todo_opinion_delete", {"id": "TODO-1", "idx": 0}) is True
    left = json.loads(c.row("TODO-1")["결재의견"])
    assert len(left) == 1 and left[0]["name"] == "이정헌 소장"
    assert apply(c, "todo_opinion_delete", {"id": "TODO-1", "idx": 0}) is True
    assert c.row("TODO-1")["결재의견"] == "", "마지막 의견을 지우면 빈 칸"

    # ⑩ todo_reset — 결재 흔적 전부 지움, 업무 상태는 그대로
    c = _fresh(결재요청="이정헌 소장", 결재상태="부서장 완료", 부서장싸인="2026-09-09 10:00:00", 상태="진행중")
    assert apply(c, "todo_reset", {"id": "TODO-1"}) is True
    r = c.row("TODO-1")
    assert r["결재요청"] == "" and r["결재상태"] == "" and r["부서장싸인"] == "" and r["상태"] == "진행중"
    assert "TODO-1" not in c.appr

    # ⑪ todo_remove_file — 그 주소만 빠지고 나머지 순서 유지
    c = _fresh()
    assert apply(c, "todo_remove_file", {"id": "TODO-1", "url": "u1"}) is True
    assert c.row("TODO-1")["파일URL"] == "u2"
    assert apply(c, "todo_remove_file", {"id": "TODO-1"}) is False    # url 없으면 안 건드린다

    # ⑫ 대표 결재 2단계 — 결재완료 건만 올릴 수 있고, 서명본(URL)이 이미 있으면 거부
    c = _fresh(결재상태="결재완료")
    assert apply(c, "approval_rep_escalate", {"id": "TODO-1"}) is True
    assert c.row("TODO-1")["대표싸인"] == "PENDING"
    assert apply(_fresh(결재상태="대기"), "approval_rep_escalate", {"id": "TODO-1"}) is False
    assert apply(_fresh(결재상태="결재완료", 대표싸인="https://drive.google.com/x"),
                 "approval_rep_escalate", {"id": "TODO-1"}) is False
    assert apply(c, "approval_rep_cancel", {"id": "TODO-1"}) is True
    assert c.row("TODO-1")["대표싸인"] == ""

    # ⑬ 서버가 값을 만들 수 없는 쓰기는 손대지 않는다(주소를 지어내지 않는다)
    assert "approval_rep_sign_upload" in NO_MIRROR and "approval_rep_sign_upload" not in HANDLERS

    # ⑭ 거울 행의 파생 칸(부서·상태·완료일)은 sync_todo 규칙 그대로 다시 뽑힌다 — 두 곳이 어긋나면 안 된다
    todos, apprs = sync_todo._row_tuples([_fresh().row("TODO-1")], "t")
    assert todos[0][4] == "시설부" and todos[0][6] == "진행중", todos[0]

    print("자체점검 통과")
