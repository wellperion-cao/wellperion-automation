# -*- coding: utf-8 -*-
"""schedule_backfill_keys.py — 이미 올라가 있는 전사일정 항목에 열쇠 두 칸(todo_id·plan_id)을 소급해 채운다.

왜: 2026-09-14 부터 gm_handoff 로 **새로** 올리는 일정에는 todo_id·plan_id 가 들어가 화면 카드에
  「▸업무」·「▸GM업무」 링크가 뜬다(전사_일정.html renderList keyTxt). 그런데 그 전에 쌓인 242건에는
  그 칸이 없어 영영 링크가 안 뜬다. GM 승인 2026-09-14 「소급 진행」.

짝짓기 규칙 — 제목 정규화(꾸밈말 `[GM업무] `·`(GM 직접)` 과 괄호 꼬리(`(이후`)를 떼고
  공백·괄호·기호 제거) 뒤
  확신 ① 정규화 제목이 **완전히 같은** 후보가 딱 하나면 — 날짜를 안 본다. 이름이 같으면 같은 건이다.
  확신 ② 아니면 길이비 0.60 이상 · 날짜 차 90일 안 · (포함 또는 유사도 0.75 이상)인 후보가 딱 하나일 때.
  판정필요 — 위 둘 다 아닌데 닮은 후보는 있는 것(토막 제목·먼 날짜·후보 여럿 · 길이비 0.60 미만은 후보로도 안 침).
  없음     — 닮은 후보가 아예 없는 것(짧은 우산 행이 긴 제목의 토막으로만 걸리는 것 포함).
확신만 라이브에 쓴다. 판정필요는 stdout 에만 남긴다 — 파일로 안 남긴다(GM 2026-09-14 「보고서 파일 정리」).

길이비가 왜 필요한가(2026-09-14 2차 실측): 「종합접수처」라는 짧은 업무 행 하나가 「종합접수처 키오스크
  셋팅」·「연휴 전 종합접수처 미완료 소진」 두 일정에 동시에 걸렸다. 포함은 맞지만 후보가 제목의 토막일
  뿐이라 같은 건이라 할 수 없다(길이비 0.45·0.24). 0.60 문턱이 이런 우산 행을 걸러 낸다.

쓰는 법
  python scripts/schedule_backfill_keys.py            # 백업 + 짝짓기 + stdout 보고만 (라이브 쓰기 없음)
  python scripts/schedule_backfill_keys.py --apply    # 위에 더해 확신 건을 라이브에 저장하고 되읽어 확인

# ponytail: 한 번 쓰고 마는 소급 도구 — 일반화하지 않는다. 저장은 전사일정이 원래 쓰는 save_schedule 그대로.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PLAN_PATH = ROOT / "status" / "monthly_ops_plan.json"
GM_KEY = "1531"          # GM 행은 이 키 없이는 todo_list 에 안 나온다(gm_handoff 와 같은 값)
NEAR_DAYS = 90           # 날짜 차 상한. 일정은 행사 날, 업무·목표는 마감 달이라 한두 달 벌어지는 게 정상이다
SIM_SOFT = 0.72          # 「판정필요」로 올릴 최소 닮음
SIM_HARD = 0.75          # 포함이 아니어도 같은 이름으로 보는 닮음(실측 브로제이 0.947 · 바디프렌드 0.778)
LEN_MIN = 0.60           # 길이비 문턱 — 후보가 일정 제목의 토막일 뿐인 짝을 막는다
MIN_KEY = 4              # 정규화 제목이 이보다 짧으면 포함 판정을 믿지 않는다("교육" 같은 토막)


def backup_path() -> Path:
    """쓰기 직전 스냅샷 자리. 이미 있는 백업은 절대 덮지 않는다 — 회차마다 _2, _3 으로 새로 만든다."""
    base = ROOT / "status" / "backups"
    for n in range(1, 50):
        p = base / ("schedule_before_backfill_20260914%s.json" % ("" if n == 1 else "_%d" % n))
        if not p.exists():
            return p
    raise RuntimeError("백업 이름이 다 찼다 — 오래된 것을 치우고 다시 돌려라")


# ── 읽기 ──────────────────────────────────────────────────────────────────
def _open(req_or_url, tries: int = 3) -> dict:
    """GAS 한 번 호출 + 재시도. 2026-09-14 실측: /exec 의 302 목적지가 이따금 404 로 답한다
    (읽기 GET 조차 · 5초 뒤 같은 주소가 정상). 한 번 튕겼다고 소급을 멈추지 않는다.

    POST 재시도가 두 번 쓰는 사고를 내지 않는 이유: 저장은 baseRev 를 실어 보내고, 앞 POST 가
    실제로 들어갔다면 서버 rev 가 바뀌어 두 번째가 stale-rev 로 **거부**된다(그 답이 곧 신호다).
    """
    import time
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req_or_url, timeout=90) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            print("  … GAS 호출 실패 %d/%d: %s %s" % (i + 1, tries, type(e).__name__, e))
            if i < tries - 1:
                time.sleep(5 * (i + 1))
    raise last


def fetch_live() -> dict:
    from collectors.ops_shared import SCHEDULE_GAS_URL
    return _open(SCHEDULE_GAS_URL + "?action=load_schedule")


def fetch_todos() -> list:
    import ops_daily_digest as o
    res = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                     timeout=60, label="전사일정 소급 짝짓기").json()
    return res.get("data") or []


def load_objectives() -> list:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    out = []
    for mkey, mval in (plan.get("months") or {}).items():
        for ob in (mval.get("objectives") or []):
            if ob.get("id") and ob.get("title"):
                out.append({"id": ob["id"], "title": ob["title"], "month": mkey, "due": ob.get("due") or ""})
    return out


# ── 이름·날짜 ─────────────────────────────────────────────────────────────
# 도구가 붙인 꾸밈말 — 이름의 일부가 아니다. 떼고 나서 견준다.
#   `[GM업무] ` 접두 = 전사일정이 GM 카드에서 만들어질 때 붙는다.
#   `(GM 직접)` 접미 = 월간운영계획 목표 제목에 붙는다.
# 2026-09-14 실측: 이 둘 때문에 16건이 「포함 아님」으로 떨어졌다 — 날짜는 전부 0일차였다.
# 즉 1차에서 이 16건이 판정필요로 간 원인은 날짜 규칙이 아니라 여기였다.
_DECOR = re.compile(r"^\s*\[GM업무\]\s*|\s*\(GM\s*직접\)\s*$")
# 2차(2026-09-14): 괄호(꼬리) 이후는 부제·상세 설명이지 이름이 아니다.
#   예) 「제2회 웰림픽(WELLYMPIC) 개요서」→ 꼬리를 떼면 「제2회 웰림픽」= 일정 제목과 완전일치.
# 「—」는 여기서 안 뗀다 — 브로제이 SRS 건처럼 앞뒤 둘 다가 제목의 일부인 경우가 있다
# (「— 이후」를 통짜로 떼면 뒤쪽 문구가 사라져 유사도 매칭이 깨진다 · 실측으로 확인).
_TAIL = re.compile(r"\s*\(.*$")


def norm(s) -> str:
    """제목 정규화 — 꾸밈말을 떼고 공백·괄호·기호를 걷어낸 한글/영문/숫자만.
    포함·유사도(ratio) 비교에 쓴다 — 괄호 속 문구도 남겨 둬야 순서 다른 같은 이름을 잡는다."""
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", _DECOR.sub("", str(s or "")))


def norm_exact(s) -> str:
    """완전일치 전용 정규화 — 꾸밈말에 더해 괄호 꼬리(부제·상세 설명)까지 뗀다(2차 2026-09-14).
    ratio 비교에는 안 쓴다 — 거기 섞으면 곁가지 항목까지 문턱을 넘겨 엉뚱한 짝이 된다(실측 확인)."""
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", _TAIL.sub("", _DECOR.sub("", str(s or ""))))


def as_date(v):
    s = str(v or "")[:10]
    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


def month_span(mkey: str):
    """'2026-09' → (9/1, 9/30). due 가 없는 목표는 그 달 전체를 기간으로 본다."""
    try:
        y, m = (int(x) for x in mkey.split("-")[:2])
    except ValueError:
        return None
    first = _dt.date(y, m, 1)
    last = _dt.date(y + (m == 12), (m % 12) + 1, 1) - _dt.timedelta(days=1)
    return first, last


def gap_days(d, span):
    """일정 날짜와 상대 기간 사이의 거리(일). 기간 안이면 0. 잴 수 없으면 None."""
    if d is None or span is None:
        return None
    lo, hi = span
    if lo <= d <= hi:
        return 0
    return (lo - d).days if d < lo else (d - hi).days


# ── 짝짓기 ────────────────────────────────────────────────────────────────
def candidates(item_name: str, item_date, pool: list) -> list:
    """닮은 후보를 전부, 잰 값과 함께 돌려준다. pool 원소 = {"key","title","title_norm","span"}

    잰 값 셋 — 왜 셋이 다 필요한가:
      cont  포함    같은 이름인데 한쪽에 설명이 더 붙은 꼴
      ratio 닮음    낱말 순서만 다른 같은 이름(포함이 아니다 — 브로제이 SRS 0.947)
      lenr  길이비  후보가 일정 제목의 토막일 뿐인 짝을 거른다(「종합접수처」 0.45 · 「제2회 웰림픽」 0.33)
    """
    a, ae = norm(item_name), norm_exact(item_name)
    out = []
    if len(a) < MIN_KEY:
        return out
    for c in pool:
        b = c["title_norm"]
        if len(b) < MIN_KEY:
            continue
        exact = len(ae) >= MIN_KEY and ae == norm_exact(c["title"])
        cont = (a in b) or (b in a)
        ratio = SequenceMatcher(None, a, b).ratio()
        if not (cont or ratio >= SIM_SOFT or exact):
            continue
        lenr = min(len(a), len(b)) / max(len(a), len(b))
        if lenr < LEN_MIN and not exact:
            continue  # 후보가 제목의 토막일 뿐 — 판정필요로도 안 올린다(종합접수처류)
        out.append(dict(c, gap=gap_days(item_date, c["span"]), ratio=ratio, cont=cont,
                        exact=exact, lenr=lenr))
    return out


def pick(cands: list):
    """후보 목록에서 확신 짝 하나를 고른다 → (후보|None, 근거 문구).

    ① 제목 완전일치가 딱 하나면 날짜를 안 본다 — 이름이 같으면 같은 건이다.
       (후보가 둘이어도 완전일치가 하나뿐이면 헷갈릴 게 없다 — 「회원 서비스」 vs 「회원 서비스 개선 …」)
    ② 아니면 길이비·날짜를 통과한 후보가 딱 하나일 때만.
    둘 다 아니면 사람이 정한다.
    """
    exact = [c for c in cands if c["exact"]]
    if len(exact) == 1:
        return exact[0], "제목 완전일치"
    hits = [c for c in cands
            if c["lenr"] >= LEN_MIN and c["gap"] is not None and c["gap"] <= NEAR_DAYS
            and (c["cont"] or c["ratio"] >= SIM_HARD)]
    if len(hits) == 1:
        h = hits[0]
        how = "제목 포함" if h["cont"] else "제목 유사 %.2f" % h["ratio"]
        return h, "%s·%d일차" % (how, h["gap"])
    if len(exact) > 1 or len(hits) > 1:
        return None, "확신 후보 여럿"
    return None, "제목이 토막이거나 날짜가 멂"


def build_pools(todos: list, objectives: list):
    tpool = []
    for r in todos:
        s, e = as_date(r.get("시작일")), as_date(r.get("종료일"))
        have = [x for x in (s, e) if x]
        span = (min(have), max(have)) if have else None
        tpool.append({"key": r.get("id"), "title": r.get("업무명") or "",
                      "title_norm": norm(r.get("업무명")), "span": span})
    opool = []
    for ob in objectives:
        d = as_date(ob["due"])
        span = (d, d) if d else month_span(ob["month"])
        opool.append({"key": ob["id"], "title": ob["title"],
                      "title_norm": norm(ob["title"]), "span": span})
    return tpool, opool


def decide(item: dict, tpool: list, opool: list) -> dict:
    """한 일정 항목의 판정. verdict = sure | review | none"""
    name, d = item.get("name") or "", as_date(item.get("next_due"))
    tc, oc = candidates(name, d, tpool), candidates(name, d, opool)
    todo, twhy = pick(tc)
    plan, owhy = pick(oc)
    if todo or plan:
        return {"verdict": "sure", "todo": todo, "plan": plan,
                "why": " · ".join(x for x in [("업무 " + twhy) if todo else "",
                                              ("목표 " + owhy) if plan else ""] if x)}
    cands = [("업무", c) for c in tc] + [("목표", c) for c in oc]
    if cands:
        return {"verdict": "review", "cands": cands[:4],
                "why": twhy if tc else owhy}
    return {"verdict": "none", "why": "닮은 행·목표 없음"}


# ── 저장 ──────────────────────────────────────────────────────────────────
def save_live(cal: dict, base_rev: str) -> dict:
    """전사일정이 원래 쓰는 save_schedule 그대로. baseRev 를 실어 동시편집 충돌을 GAS 가 막게 둔다."""
    from collectors.ops_shared import SCHEDULE_GAS_URL
    body = json.dumps({"action": "save_schedule", "data": cal, "baseRev": base_rev}).encode("utf-8")
    req = urllib.request.Request(SCHEDULE_GAS_URL, data=body,
                                 headers={"Content-Type": "text/plain"}, method="POST")
    return _open(req)


# ── 보고 ──────────────────────────────────────────────────────────────────
# 2차(2026-09-14 GM 지시): 보고서 파일을 안 만든다 — stdout + 진행현황 한 줄(기존 단일 관문 재사용)로 낸다.
def cut(s, n=34) -> str:
    s = str(s or "").replace("|", "/").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def print_report(rows: list, counts: dict, applied: str, done_before: int = 0) -> None:
    total = sum(counts.values())
    print("\n남은 대상 %d건 · 확신 %d · 판정필요 %d · 없음 %d (앞선 회차에 이미 채운 %d건은 손대지 않는다)"
          % (total, counts["sure"], counts["review"], counts["none"], done_before))
    print("라이브 반영: " + applied)
    if counts["sure"]:
        print("\n[확신 — 반영]")
        for r in rows:
            if r["d"]["verdict"] != "sure":
                continue
            t, p = r["d"].get("todo") or {}, r["d"].get("plan") or {}
            print("  · %s (%s) → 업무=%s/%s 목표=%s · %s"
                  % (cut(r["it"].get("name")), r["it"].get("next_due") or "—",
                     t.get("key") or "—", cut(t.get("title"), 26), p.get("key") or "—", r["d"]["why"]))
    if counts["review"]:
        print("\n[판정 필요 — 안 씀, 사람이 정한다]")
        for r in rows:
            if r["d"]["verdict"] != "review":
                continue
            cands = " / ".join("%s:%s" % (k, cut(c["title"], 20)) for k, c in r["d"]["cands"])
            print("  · %s (%s) 후보 %s — %s"
                  % (cut(r["it"].get("name")), r["it"].get("next_due") or "—", cands, r["d"]["why"]))


def log_progress(counts: dict, done_before: int, applied: str) -> None:
    """진행현황 한 줄 — status/progress_report_log.jsonl 단일 관문(notify_gm_progress) 재사용.
    새 보고서 파일을 만들지 않는다(GM 2026-09-14)."""
    try:
        import notify_gm_progress as ng
    except Exception as exc:  # noqa: BLE001 — 진행보고 실패로 소급 자체를 멈추지 않는다
        print("[진행보고 생략] %s" % exc)
        return
    summary = ("전사일정 열쇠 소급 2차 — 확신 %d·판정필요 %d·없음 %d (%s)"
               % (counts["sure"], counts["review"], counts["none"], applied))
    res = ng.notify(summary[:ng.PLAIN_SUMMARY_MAX], ship="웰리", step="전사일정 열쇠 소급 2차", state="done")
    print("[진행보고] %s — %s" % (res.get("reason"), summary))


# ── 본체 ──────────────────────────────────────────────────────────────────
def main() -> int:
    apply = "--apply" in sys.argv

    live = fetch_live()
    if not (isinstance(live, dict) and live.get("ok") and isinstance((live.get("data") or {}).get("items"), list)):
        print("✖ 라이브 조회 실패 — 아무것도 하지 않는다:", str(live)[:200])
        return 1
    BACKUP = backup_path()
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
    cal, rev = live["data"], str(live.get("rev") or "")
    print("[백업] %s · %d bytes · 항목 %d건 · rev %s"
          % (BACKUP, BACKUP.stat().st_size, len(cal["items"]), rev or "(없음)"))

    tpool, opool = build_pools(fetch_todos(), load_objectives())
    print("[짝 후보] 업무 %d행 · 월간목표 %d개" % (len(tpool), len(opool)))

    rows, counts, done_before = [], {"sure": 0, "review": 0, "none": 0}, 0
    for it in cal["items"]:
        if not isinstance(it, dict):
            continue
        # 이미 채워진 항목은 건드리지 않는다(gm_handoff 로 새로 올린 건 · 앞선 회차에 채운 건).
        if it.get("todo_id") or it.get("plan_id"):
            done_before += 1
            continue
        d = decide(it, tpool, opool)
        counts[d["verdict"]] += 1
        rows.append({"it": it, "d": d})

    applied = "안 함(--apply 없음)"
    if apply and counts["sure"]:
        for r in rows:
            if r["d"]["verdict"] != "sure":
                continue
            t, p = r["d"].get("todo") or {}, r["d"].get("plan") or {}
            r["it"]["todo_id"] = t.get("key") or ""
            r["it"]["plan_id"] = p.get("key") or ""
        res = save_live(cal, rev)
        if not (isinstance(res, dict) and res.get("ok")):
            print("✖ 저장 거부 — 라이브 그대로:", str(res)[:300])
            applied = "저장 거부 — " + str(res)[:120]
            print_report(rows, counts, applied, done_before)
            log_progress(counts, done_before, applied)
            return 1
        back = fetch_live()
        items_back = (back.get("data") or {}).get("items") or []
        got = [x for x in items_back if isinstance(x, dict) and (x.get("todo_id") or x.get("plan_id"))]
        applied = "저장 ✔ · 되읽기에서 열쇠 있는 항목 %d건 (총 %d건)" % (len(got), len(items_back))
        print("[되읽기] 열쇠 살아 있는 항목 %d건 / 총 %d건" % (len(got), len(items_back)))
    elif apply:
        applied = "확신 0건 — 쓸 것이 없다"

    print_report(rows, counts, applied, done_before)
    log_progress(counts, done_before, applied)
    print("[판정] 확신 %d · 판정필요 %d · 없음 %d"
          % (counts["sure"], counts["review"], counts["none"]))
    return 0


def _demo() -> None:
    """자체 점검 — 짝짓기 규칙이 확신/판정필요/없음 셋을 제대로 가르는지."""
    pool = [{"key": "TODO-1", "title": "요가 프로그램 개편", "title_norm": norm("요가 프로그램 개편"),
             "span": (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))},
            {"key": "TODO-2", "title": "주차 요금 인상", "title_norm": norm("주차 요금 인상"),
             "span": (_dt.date(2026, 3, 1), _dt.date(2026, 3, 31))}]
    def hit(name, day=_dt.date(2026, 9, 15), p=None):
        c, why = pick(candidates(name, day, p if p is not None else pool))
        return ((c or {}).get("key"), why)

    # 이름이 같고 날짜가 그 달 안 → 확신
    assert hit("요가 프로그램 개편")[0] == "TODO-1"
    # 제목이 똑같으면 6개월 차이여도 고른다 — 이름이 같으면 같은 건이다(2차 규칙 ①)
    assert hit("주차 요금 인상") == ("TODO-2", "제목 완전일치")
    # 반대로 이름이 완전히 같지 않고 날짜까지 90일 넘게 벌어지면 못 고른다
    assert hit("주차 요금 인상 2차")[0] is None
    # 닮은 것 자체가 없다
    assert hit("승강기 정기점검") == (None, "닮은 행·목표 없음") or hit("승강기 정기점검")[0] is None
    # 꾸밈말([GM업무] 접두 · (GM 직접) 접미)을 떼면 완전일치 — 날짜를 안 본다(2026-09-14 2차)
    gm = [{"key": "OBJ-1", "title": "쓰쿠루 파트너 계약 해지 (GM 직접)",
           "title_norm": norm("쓰쿠루 파트너 계약 해지 (GM 직접)"),
           "span": (_dt.date(2026, 7, 1), _dt.date(2026, 7, 31))}]
    assert hit("[GM업무] 쓰쿠루 파트너 계약 해지", _dt.date(2026, 9, 30), gm) == ("OBJ-1", "제목 완전일치")
    # 후보가 둘이어도 완전일치가 하나면 그것으로 — 「회원 서비스」 vs 「회원 서비스 개선 …」
    two = gm + [{"key": "OBJ-2", "title": "쓰쿠루", "title_norm": norm("쓰쿠루"),
                 "span": (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))}]
    assert hit("[GM업무] 쓰쿠루 파트너 계약 해지", _dt.date(2026, 9, 30), two)[0] == "OBJ-1"
    # 후보가 일정 제목의 토막일 뿐이면 안 고른다 — 「종합접수처」(길이비 0.45)
    frag = [{"key": "TODO-9", "title": "종합접수처", "title_norm": norm("종합접수처"),
             "span": (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))}]
    assert hit("종합접수처 키오스크 셋팅", _dt.date(2026, 9, 15), frag)[0] is None
    # 꼬리(괄호 이후)를 떼면 완전일치 — 「제2회 웰림픽(WELLYMPIC) 개요서」(2차 2026-09-14)
    tail = [{"key": "TODO-11", "title": "제2회 웰림픽(WELLYMPIC) 개요서",
             "title_norm": norm("제2회 웰림픽(WELLYMPIC) 개요서"),
             "span": (_dt.date(2026, 11, 1), _dt.date(2026, 11, 30))}]
    assert hit("제 2회 웰림픽", _dt.date(2026, 11, 8), tail) == ("TODO-11", "제목 완전일치")
    # 포함이 아니어도 낱말 순서만 다르면 같은 이름 — 브로제이 SRS(실측 0.947)
    reord = [{"key": "TODO-8", "title": "브로제이 SRS 검토 — 조민규 대표님 피드백",
              "title_norm": norm("브로제이 SRS 검토 — 조민규 대표님 피드백"),
              "span": (_dt.date(2026, 9, 10), _dt.date(2026, 9, 13))}]
    assert hit("브로제이 SRS 검토 후 조민규 대표님께 피드백", _dt.date(2026, 9, 14), reord)[0] == "TODO-8"
    assert gap_days(_dt.date(2026, 9, 15), (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))) == 0
    assert gap_days(_dt.date(2026, 10, 5), (_dt.date(2026, 9, 1), _dt.date(2026, 9, 30))) == 5
    assert month_span("2026-02") == (_dt.date(2026, 2, 1), _dt.date(2026, 2, 28))
    assert month_span("2026-12") == (_dt.date(2026, 12, 1), _dt.date(2026, 12, 31))
    print("짝짓기 규칙 자체 점검 통과 ✓")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _demo()
        raise SystemExit(0)
    raise SystemExit(main())
