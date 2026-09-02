# -*- coding: utf-8 -*-
"""전사 일정 SSOT — 로더·검증·상태판정.
SSOT = status/schedule_ssot.json (반복 의무·이벤트, type으로 종류 구분·현재=정기점검).
정본은 JSON, 이 모듈은 소비자(읽기전용 — 항목 검증·상태(tbd/scheduled/due_soon/overdue)
판정·요약만 한다).

[2026-07-30 시토·웰리] 업무·결재 자동상신 서브기능(plan_workapproval()·gate.auto_workapproval
소비 및 그 키 자체)을 제거했다 — 실배선(이 함수를 실제로 호출해 업무·결재에 반영하는 코드)이
저장소 전체에 0곳이었다(자기 테스트 파일 제외 — 전수 grep 재확인, 화면·GAS 포함). 죽어 있는데
"켜면 뭔가 될 것 같은 스위치"로 남겨두면 나중에 배선을 만드는 사람이 GM 결정 없이 그냥 켤
위험이 있다(약속 L21 '꺼둔 것은 남기지 않는다'). 자동상신이 필요해지면 그때 GM 결정과 함께
다시 설계한다. status/schedule_ssot.json 의 gate 객체에서 auto_workapproval 키 자체도 제거했다
(같은 이유 — 값만 지우고 스위치 모양(키)을 남기면 되살릴 여지가 남는다). gate.lead_days·_note
와 3개 라이브 화면(전사_일정.html·시설부 체계.html·wellperion_guide(main).html)은 이 삭제와
무관 — 그대로 살아있다. 되돌리려면: gate 객체에 "auto_workapproval": false 한 줄을 다시 넣고
(git 이력의 삭제 전 커밋에서 복사 가능), plan_workapproval() 은 필요해질 때 새로 설계한다(그대로
되살리지 않는다 — 그때 상황에 맞게 다시 판단)."""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CAL_PATH = Path(__file__).resolve().parent.parent / "status" / "schedule_ssot.json"

_SCRIPTS_DIR_FOR_WORKLOG = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR_FOR_WORKLOG not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR_FOR_WORKLOG)

try:  # 작업 현황 로그(best-effort) — 임포트 실패해도 선별 흐름 무영향
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False

REQUIRED_ITEM_KEYS = ["id", "name", "category", "dept", "cycle", "cycle_confirmed",
                       "legal_basis", "last_done", "next_due"]
VALID_STATUS = {"scheduled", "due_soon", "overdue", "done", "tbd"}


def load(path=CAL_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _kst_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def validate(cal: dict) -> list:
    """구조 계약 검증 — 정본 무결성 가드. 오류 리스트(빈=통과)."""
    errors = []
    if not isinstance(cal.get("items"), list):
        return ["items 키가 리스트가 아님"]
    depts = set(cal.get("depts", []))
    cats = set(cal.get("categories", {}).keys())
    seen = set()
    for it in cal["items"]:
        iid = it.get("id")
        for k in REQUIRED_ITEM_KEYS:
            if k not in it:
                errors.append(f"[{iid}] 필수키 누락: {k}")
        if iid in seen:
            errors.append(f"중복 id: {iid}")
        seen.add(iid)
        # 빈 부서는 오류가 아니다 — GM 이 직접 넣은 일정처럼 담당 부서가 아직 없는 건은
        # 비었다고 보이게 두는 것이 규칙이다(약속 L23 · 빈칸을 지어 채우지 않는다).
        # 값이 들어 있는데 부서 목록에 없을 때만 잡는다(사람 이름을 부서 칸에 넣는 사고 방지).
        if it.get("dept") and it["dept"] not in depts:
            errors.append(f"[{iid}] 미등록 부서: {it.get('dept')}")
        if it.get("category") not in cats:
            errors.append(f"[{iid}] 미등록 분류: {it.get('category')}")
    return errors


def _parse_due(s):
    """next_due 문자열 → date. 빈칸/미확인/연월만 있으면 None(D-day 계산 불가)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d
        except ValueError:
            continue
    return None


def status_of(it: dict, today: date = None, lead_days: int = 30) -> dict:
    """항목 상태 판정 — 지어내지 않음: next_due 없으면 tbd."""
    today = today or _kst_today()
    due = _parse_due(it.get("next_due"))
    if due is None:
        return {"status": "tbd", "dday": None}
    dd = (due - today).days
    if dd < 0:
        st = "overdue"
    elif dd <= lead_days:
        st = "due_soon"
    else:
        st = "scheduled"
    return {"status": st, "dday": dd}


def _applies(it: dict) -> bool:
    """해당없음 항목은 달력·연동·집계에서 제외(설비 미보유 등)."""
    return it.get("applies") != "해당없음"


def due_items(cal: dict, today: date = None, lead_days: int = None) -> list:
    """기한 도래(임박·초과) 항목만 — 업무·결재 연동 후보. 해당없음 제외."""
    today = today or _kst_today()
    lead = cal.get("gate", {}).get("lead_days", 30) if lead_days is None else lead_days
    out = []
    for it in cal.get("items", []):
        if not _applies(it):
            continue
        s = status_of(it, today, lead)
        if s["status"] in ("due_soon", "overdue"):
            out.append({**it, **s})
    return out


def summarize(cal: dict, dept: str = None, today: date = None) -> dict:
    today = today or _kst_today()
    lead = cal.get("gate", {}).get("lead_days", 30)
    items = [it for it in cal.get("items", [])
             if (not dept or dept == "전체" or it.get("dept") == dept) and _applies(it)]
    c = {"overdue": 0, "due_soon": 0, "scheduled": 0, "tbd": 0, "total": len(items)}
    for it in items:
        c[status_of(it, today, lead)["status"]] += 1
    return c


def pull_from_live(path=CAL_PATH) -> dict:
    """전사일정 라이브(GAS) → 이 JSON 으로 **단방향** 내려받기 (배621·625 · 2026-08-14 시토).

    왜 필요한가: 사람이 쓰는 곳은 화면(GAS)인데, 기계가 읽는 곳은 이 파일이라 두 벌이 됐다.
      실사고 2026-08-13~14 — 이정헌 소장이 회신한 법정점검 실시일 4건(전기·승강기·정화조·가스)이
      화면에는 들어갔는데 이 파일은 빈칸 그대로였다. 그래서 다음날 아침 점검 보고가 "회신 0건
      지속"이라고 GM 께 잘못 보고했다. 놓침을 잡아야 할 쪽이 옛 데이터를 보고 있었다.
      (헌법 불변원리 1 — 한 진실 = 한 곳)

    방향은 GAS → 파일 한쪽뿐이다. 사람이 쓰는 곳이 화면이므로 화면이 원천이다.
    ★파일에만 있고 라이브에 없는 항목은 **지우지 않는다**(현재 0건이지만, 라이브 조회가
      반쪽만 성공했을 때 로컬을 비우는 사고를 막는다). 라이브를 못 읽으면 파일을 건드리지
      않고 그대로 둔다 — 못 읽은 것과 '없어진 것'은 다르다.
    새 스크립트·새 예약을 만들지 않는다(약속 L21): 이 파일을 소유한 모듈에 함수 하나만 얹고,
      매일 도는 monthly_ops_sync 끝에서 부른다.
    """
    import urllib.request  # noqa: PLC0415 — 읽기 경로에서만 쓴다
    try:
        from collectors.ops_shared import SCHEDULE_GAS_URL  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from collectors.ops_shared import SCHEDULE_GAS_URL  # noqa: PLC0415

    try:
        with urllib.request.urlopen(SCHEDULE_GAS_URL + "?action=load_schedule", timeout=25) as r:
            res = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"라이브 조회 실패({type(e).__name__}) — 파일 무변경"}
    live = res.get("data") if isinstance(res, dict) and res.get("ok") else None
    if not isinstance(live, dict) or not isinstance(live.get("items"), list):
        return {"ok": False, "reason": "라이브 응답이 비정상 — 파일 무변경"}

    cal = load(path)
    by_id = {it.get("id"): it for it in cal.get("items", []) if isinstance(it, dict)}
    added = changed = 0
    for it in live["items"]:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        cur = by_id.get(it["id"])
        if cur is None:
            by_id[it["id"]] = it
            added += 1
        elif cur != it:
            by_id[it["id"]] = it
            changed += 1
    if not (added or changed):
        return {"ok": True, "added": 0, "changed": 0, "total": len(by_id), "reason": "이미 같음"}

    cal["items"] = list(by_id.values())
    cal["updated_at"] = _kst_today().isoformat()
    path.write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "added": added, "changed": changed, "total": len(by_id)}


def push_to_live(cal: dict, force: bool = False) -> dict:
    """이 파일 내용을 전사일정 화면(GAS)에 밀어 넣는다 — 파일 → GAS 방향 (2026-08-21 시토 · 배743).

    왜 필요한가: 화면(전사_일정.html)은 GAS 를 원천으로 읽고, 이 JSON 은 폴백 씨앗일 뿐이다.
      그런데 add_event() 는 이 JSON 에만 썼다 — 스크립트로 넣은 일정이 화면에 **영영 안 떴다.**
      실사고 2026-08-21: GM 이 8/27 라이프피트니스 쇼룸 방문을 화면에서 못 찾으셨고,
      실측하니 로컬에만 있는 항목이 15건이었다(8/26 캡스 계약서·현장실사, 8/31 CCTV 계약 등
      GM 지시 건 포함). 아무 오류도 안 났기 때문에 아무도 몰랐다.

    pull_from_live() 와 짝이다 — 그쪽은 GAS → 파일, 이쪽은 파일 → GAS.
    새 GAS·새 액션을 만들지 않는다: 전사일정이 원래 쓰는 save_schedule 을 그대로 부른다(약속 L21).
    """
    import urllib.request  # noqa: PLC0415
    try:
        from collectors.ops_shared import SCHEDULE_GAS_URL  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from collectors.ops_shared import SCHEDULE_GAS_URL  # noqa: PLC0415
    try:
        # force — 항목이 줄어드는 저장은 GAS 가 기본으로 막는다(silent-drop 가드, 실수로 남의
        #   항목을 덮는 사고 방지). 일정을 **일부러 지우는** 호출만 force=True 로 그 가드를 넘는다.
        #   기본값은 False 라 종전 호출부 동작은 그대로다(회귀 0). 지워진 항목은 GAS 쪽
        #   삭제 로그(action=schedule_dropped)에 남으므로 되짚을 수 있다.
        payload = {"action": "save_schedule", "data": cal}
        if force:
            payload["force"] = True
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(SCHEDULE_GAS_URL, data=body,
                                     headers={"Content-Type": "text/plain"}, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            res = json.loads(r.read())
        if isinstance(res, dict) and res.get("ok"):
            return {"ok": True, "total": len(cal.get("items") or [])}
        return {"ok": False, "reason": f"GAS 응답 비정상: {str(res)[:120]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _dup_norm(s) -> str:
    """중복 판정용 정규화 — 공백·가운뎃점·괄호류를 지운 이름."""
    import re
    return re.sub(r"[\s·\-—()\[\]/,.]+", "", str(s or ""))


def find_duplicate(name: str, next_due: str, path=CAL_PATH) -> list:
    """같은 날 같은 일로 이미 등록된 항목을 돌려준다(빈 리스트 = 없음).

    2026-08-19 실사고: 웰리가 「외곽 인수인계 — 황용석 팀장 방문」을 이미 있는데 한 번 더
    만들어 전사일정에 같은 일이 두 줄로 떴다(GM 이 발견). 약속 L25 세 번째 대조("같은 게 이미
    있나")를 문서가 아니라 여기서 재게 한다 — 넣기 전에 이 함수를 부른다.

    판정: next_due 가 같고, 이름을 정규화했을 때 한쪽이 다른 쪽을 포함하거나 0.6 이상 닮으면 중복.
    (ops_daily_digest·send_ops_digest 의 _nudge_similar 과 같은 규칙 — 새 판정 로직을 만들지 않는다.)
    """
    from difflib import SequenceMatcher
    try:
        items = load(path).get("items") or []
    except Exception:
        return []
    na = _dup_norm(name)
    if not na:
        return []
    out = []
    for it in items:
        if str(it.get("next_due") or "") != str(next_due or ""):
            continue
        nb = _dup_norm(it.get("name"))
        if not nb:
            continue
        if na in nb or nb in na or SequenceMatcher(None, na, nb).ratio() >= 0.6:
            out.append(it)
    return out


def add_event(item: dict, path=CAL_PATH, force: bool = False) -> dict:
    """전사일정에 이벤트 1건 추가 — 같은 날 같은 일이 있으면 막는다(약속 L25).

    반환 {"ok":True,"added":1} / {"ok":False,"reason":"중복","dups":[...]}.
    정말 따로 세워야 하는 건이면 force=True 로 통과시키되, 그때는 note 에 왜 별건인지 적는다.
    """
    name = str(item.get("name") or "").strip()
    due = str(item.get("next_due") or "").strip()
    if not name or not due:
        return {"ok": False, "reason": "name·next_due 필수"}
    if not force:
        dups = find_duplicate(name, due, path)
        if dups:
            return {"ok": False, "reason": "중복",
                    "dups": [{"id": d.get("id"), "name": d.get("name"), "time": d.get("time")} for d in dups]}
    cal = load(path)
    items = cal.setdefault("items", [])
    if any(str(x.get("id")) == str(item.get("id")) for x in items):
        return {"ok": False, "reason": "같은 id 이미 있음"}
    items.append(item)
    cal["updated_at"] = _kst_today().isoformat()
    Path(path).write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    out = {"ok": True, "added": 1, "total": len(items)}
    # ★화면(GAS)에도 같이 쓴다 (2026-08-21 시토 · 배743). 여기까지 해야 사람이 볼 수 있다.
    #   실패하면 숨기지 않는다 — synced=False 와 이유를 함께 돌려주고 화면에 경고를 찍는다.
    #   조용히 성공으로 넘기면 이번 사고(로컬에만 15건)가 그대로 되풀이된다.
    if path == CAL_PATH:                       # 테스트용 임시 파일은 라이브로 밀지 않는다
        push = push_to_live(cal)
        out["synced"] = bool(push.get("ok"))
        if not push.get("ok"):
            out["sync_reason"] = push.get("reason")
            print(f"[경고] 파일엔 넣었지만 전사일정 화면에는 못 올렸습니다 — {push.get('reason')}\n"
                  f"       화면에 안 뜹니다. 다시 시도하거나 화면에서 직접 넣어 주세요.",
                  file=sys.stderr)
    return out


def _demo() -> None:
    """중복 가드 자체 점검 — 실제 원장을 건드리지 않는다."""
    import tempfile
    seed = {"_doc": "t", "items": [
        {"id": "a", "type": "이벤트", "name": "외곽 인수인계 — 황용석 팀장 방문", "next_due": "2026-08-20", "time": "오전"},
    ]}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cal.json"
        p.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
        # 같은 날 거의 같은 이름 → 막힌다
        r = add_event({"id": "b", "name": "외곽 인수인계 시작 — 황용석 팀장 방문", "next_due": "2026-08-20"}, p)
        assert r["ok"] is False and r["reason"] == "중복", r
        # 날짜가 다르면 통과
        r = add_event({"id": "c", "name": "외곽 인수인계 시작 — 황용석 팀장 방문", "next_due": "2026-09-20"}, p)
        assert r["ok"] is True, r
        # 아주 다른 일은 같은 날이어도 통과
        r = add_event({"id": "d", "name": "매트릭스 상무이사 미팅", "next_due": "2026-08-20"}, p)
        assert r["ok"] is True, r
        # force 면 중복이어도 들어간다
        r = add_event({"id": "e", "name": "외곽 인수인계 — 황용석 팀장 방문", "next_due": "2026-08-20"}, p, force=True)
        assert r["ok"] is True, r
    print("중복 가드 자체 점검 통과 ✓")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _demo()
        raise SystemExit(0)
    if "--pull" in sys.argv:
        print("[전사일정 내려받기]", pull_from_live())
        raise SystemExit(0)
    cal = load()
    errs = validate(cal)
    print("검증:", "통과 ✓" if not errs else errs)
    print("요약(전체):", summarize(cal))
    due = due_items(cal)
    print(f"기한 도래(임박·초과): {len(due)}건")
    for it in due:
        print("  →", it["name"], f"(D-{it['dday']})" if it["dday"] is not None else "")

    # 작업 현황 로그(best-effort) — 실행 1회당 선별 결과 요약 1줄
    worklog_log(
        "coo", "일정",
        f"전사 일정 기한 도래 선별 — 임박·초과 {len(due)}건 확인",
        result=("warn" if errs else "ok"),
        detail=("; ".join(errs[:3]) if errs else f"검증 통과 · 등록 {summarize(cal)['total']}건 대상"),
        ref="schedule_ssot",
    )
