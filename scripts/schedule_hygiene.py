# -*- coding: utf-8 -*-
"""전사일정 자동 정리 점검기 — 시우가 GM 말 없이 매일 스스로 정리한다 (GM 지시 2026-09-19).

GM 원문: 「이런건 시우가 좀 관리좀 해줘 자동으로 계속 이야길 해야하네」. 오늘 GM 이 손으로 짚은 것:
  ①같은 건 중복(미소시티 간판 2개) ②지난 대비 필러(추석 연휴대비) ③GM 일정 시간 빈칸
  ④휴관일에 걸린 GM 일정 ⑤지워 달라 했는데 동기화로 되살아날 위험.

★2026-09-19 (월요일 정리 배) — ⑥ 같은 todo_id 중복 추가: 같은 업무 SSOT 행(todo_id)에 전사일정
  항목이 2개 이상 걸리면 목록에 올린다(①의 이름-닮음 판정과 별개 — id 는 같은데 이름이 갈려도
  잡는다). 자동 병합은 안 한다 — 사람이 봐야 할 목록만.

원천 = schedule_ssot.pull_from_live()(GAS 라이브). 옛 JSON 만 보고 판정하지 않는다.
휴관일 판정은 coo_registry._closed_day 를 그대로 재사용한다.

★2026-09-19 웰리 수정 — ①중복 헛경보가 많았다(기존 재사용한 ops_daily_digest._schedule_is_dup 의
  이름-닮음(ratio)·부분포함 경로가 「진행」「직접」류 흔한 말 1개만 겹쳐도 잡았다). 이 체크만은
  자체 규칙으로 뗐다 — 핵심 낱말(추가 정지어로 더 거른 것) 3개 이상 겹칠 때만, 또는 같은
  타임스탬프 계열 id(evt-<13자리 숫자>-N 같은 자동생성 쌍)일 때만 중복으로 본다. 남/여 짝은
  이름·id 어느 쪽으로도 걸러 제외한다.

⑤ 되살아남 점검은 뺐다 — 시우가 지운 배의 삭제 이력을 남기는 원장이 저장소에 아직 없다
(만들면 새 SSOT 가 생긴다 · 약속 L21). 되면 그 원장을 여기서 읽기만 하면 된다.

사용법:
  python scripts/schedule_hygiene.py              # 목록만 출력(사람 말)
  python scripts/schedule_hygiene.py --apply       # ③ GM 시간 빈칸만 자동 채움 + push(①②④는 목록만)
  python scripts/schedule_hygiene.py --selfcheck   # 가짜 항목으로 판정 assert(네트워크 없음)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import schedule_ssot  # noqa: E402
from coo_registry import _closed_day  # noqa: E402

try:
    from worklog import log as worklog_log
except Exception:
    def worklog_log(*a, **k):
        return False


def _kst_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def _parse_date10(s) -> "date | None":
    """'YYYY-MM-DD' 만 date 로. 그 외(빈칸·'YYYY-MM'만)는 None — 지어내지 않는다."""
    s = str(s or "").strip()
    if len(s) != 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


# ═══════════════════════════════════════════
# ① 중복 — 핵심 낱말 3개 이상 겹침 또는 같은 타임스탬프 계열 id
# ═══════════════════════════════════════════
# ops_daily_digest._SCHEDULE_STOP_WORDS 에 이미 GM·회장님·대표님·완료·진행·보고·미팅 등이 있다.
# 여기서 더 거를 것 — 헛경보 실측(2026-09-19)으로 드러난 낱말만 얹는다(원본 목록은 안 건드린다 —
# ⑨닮은제목(gm_aide_scan) 등 다른 소비자가 이미 그 목록을 쓰고 있어 값을 바꾸면 거기도 흔들린다).
_DUP_EXTRA_STOP = frozenset(
    "GM 회장님 대표님 완료 휴관일 일정 진행 작업 보고 미팅 관리".split()
)
_DUP_MIN_WORDS = 3

# 같은 순간에 자동생성된 형제 항목 — id 끝이 "-<숫자>" 이고 그 앞에 13자리 안팎 타임스탬프가
# 박혀 있으면(예: evt-1784519651465-3 / -4) 이름이 달라도 같은 등록 배치라 중복으로 본다.
_ID_TS_SUFFIX_RE = re.compile(r"^(.*-\d{10,})-\d+$")
# 이름 끝(또는 id 끝)이 남/여·-m/-f 로만 다른 짝은 절대 중복이 아니다.
_GENDER_ID_SUFFIX_RE = re.compile(r"-(m|f)$", re.I)
# GM업무 카드 제목은 다 "[GM업무] " 로 시작한다 — 토큰화하면 "GM업무"가 모든 카드 쌍에
# 공통으로 잡혀 낱말 수를 부풀린다(실측 2026-09-19: 상가관리 카드 ↔ 전략로드맵 카드가
# "GM업무"+"관리"+"관리비⊃관리" 세 번으로 겹쳐 헛경보). 세기 전에 태그를 뗀다.
_GMWORK_TAG_RE = re.compile(r"\[GM업무\]")


def _dup_tokens(name: str) -> list:
    try:
        import ops_daily_digest as _o  # noqa: PLC0415 — 무거운 파일, 쓸 때만 임포트
    except Exception:
        return []
    clean = _GMWORK_TAG_RE.sub("", str(name or ""))
    return [t for t in _o._schedule_rare_tokens(clean) if t not in _DUP_EXTRA_STOP]


def _dup_shared_words(name_a: str, name_b: str) -> int:
    """두 이름이 공유하는 핵심 낱말 개수(가중치 없는 순수 개수 — 코드성 낱말도 1개로 센다)."""
    ta, tb = _dup_tokens(name_a), _dup_tokens(name_b)
    n = 0
    for tok_a in dict.fromkeys(ta):
        if any(tok_a == tok_b or tok_a in tok_b or tok_b in tok_a for tok_b in tb):
            n += 1
    return n


def _same_id_timestamp_family(id_a: str, id_b: str) -> bool:
    ma, mb = _ID_TS_SUFFIX_RE.match(id_a), _ID_TS_SUFFIX_RE.match(id_b)
    return bool(ma and mb and ma.group(1) == mb.group(1))


# GM업무 카드 짝(gmwork-*)은 이름이 "[GM업무] " + 원본 이벤트 이름 그대로다 — 핵심 낱말이
# 정지어(대청소 등 이미 원본 목록에서 뺀 흔한 말)뿐이면 낱말 개수로는 못 잡는다. 정규화한
# 전체 문자열이 서로 포함관계면(짧은 쪽 6자 이상) 그 자체로 같은 사실이다.
_CONTAINMENT_MIN_LEN = 6


def _norm_for_containment(name: str) -> str:
    s = _GMWORK_TAG_RE.sub("", str(name or ""))
    return re.sub(r"[\s·\-—()\[\]/,.]+", "", s)


def _is_containment_dup(name_a: str, name_b: str) -> bool:
    na, nb = _norm_for_containment(name_a), _norm_for_containment(name_b)
    if not na or not nb or min(len(na), len(nb)) < _CONTAINMENT_MIN_LEN:
        return False
    return na in nb or nb in na


def _is_gender_pair(a: dict, b: dict) -> bool:
    ida, idb = str(a.get("id") or ""), str(b.get("id") or "")
    ma, mb = _GENDER_ID_SUFFIX_RE.search(ida), _GENDER_ID_SUFFIX_RE.search(idb)
    if ma and mb and ma.group(1).lower() != mb.group(1).lower():
        if _GENDER_ID_SUFFIX_RE.sub("", ida) == _GENDER_ID_SUFFIX_RE.sub("", idb):
            return True
    na = (a.get("name") or "").replace("남", "").replace("여", "")
    nb = (b.get("name") or "").replace("남", "").replace("여", "")
    return na == nb and (a.get("name") or "") != (b.get("name") or "")


def check_duplicates(items: list) -> list:
    pairs, seen = [], set()
    for i, a in enumerate(items):
        due_a = _parse_date10(a.get("next_due"))
        if not due_a:
            continue
        ida = str(a.get("id") or "")
        for b in items[i + 1:]:
            due_b = _parse_date10(b.get("next_due"))
            if not due_b or abs((due_a - due_b).days) > 1:
                continue
            idb = str(b.get("id") or "")
            if _is_gender_pair(a, b):
                continue
            hit = (_dup_shared_words(a.get("name") or "", b.get("name") or "") >= _DUP_MIN_WORDS
                   or _same_id_timestamp_family(ida, idb)
                   or _is_containment_dup(a.get("name") or "", b.get("name") or ""))
            if not hit:
                continue
            key = tuple(sorted([ida, idb]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((a, b))
    return pairs


# ═══════════════════════════════════════════
# ② 지난 필러 — 「대비/준비」인데 기한이 지났고 반복(cycle)도 없는 것 (자동 처리 안 함 · 목록만)
# ═══════════════════════════════════════════
_FILLER_WORDS = ("대비", "준비")
_HOLIDAY_WORDS = ("추석", "설날", "연휴")


def check_stale_filler(items: list, today: date) -> list:
    out = []
    for it in items:
        name = it.get("name") or ""
        if not any(w in name for w in _FILLER_WORDS):
            continue
        due = _parse_date10(it.get("next_due"))
        if not due or due >= today:
            continue
        no_cycle = not str(it.get("cycle") or "").strip()
        has_holiday = any(w in name for w in _HOLIDAY_WORDS)
        if no_cycle or has_holiday:
            out.append(it)
    return out


# ═══════════════════════════════════════════
# ③ GM 시간 빈칸 — 다음 14일 안 GM 일정인데 time 이 빈 것
# ═══════════════════════════════════════════
def check_gm_time_blank(items: list, today: date) -> list:
    horizon = today + timedelta(days=14)
    out = []
    for it in items:
        assignee = it.get("assignee") or ""
        if "GM" not in assignee and "김남욱" not in assignee:
            continue
        due = _parse_date10(it.get("next_due"))
        if not due or not (today <= due <= horizon):
            continue
        if str(it.get("time") or "").strip():
            continue
        out.append(it)
    return out


# ③ --apply 전용 — 안전한 시간 채우기 규칙(회의·방문·실측류는 비워 둔다)
_SKIP_KEYWORDS = ("회의", "미팅", "면접", "면담", "방문", "내방", "상담", "오찬", "실측")
_SEND_KEYWORDS = ("발송", "연락", "전달", "컨택", "통보")
_DEADLINE_KEYWORDS = ("마감", "제출", "기한", "마무리")


def _classify_gm_time(name: str) -> "str | None":
    if any(k in name for k in _SKIP_KEYWORDS):
        return None  # 회의·방문·실측은 시간을 지어내지 않는다
    if any(k in name for k in _SEND_KEYWORDS):
        return "10:00"  # 외부 발송·연락
    if any(k in name for k in _DEADLINE_KEYWORDS):
        return "17:00"  # 마감형
    return "14:00"  # 내부 검토(기본)


def _bump_time(base: str, taken: set) -> str:
    t = datetime.strptime(base, "%H:%M")
    while t.strftime("%H:%M") in taken:
        t += timedelta(minutes=30)
    return t.strftime("%H:%M")


def apply_gm_time_fill(items: list, gm_blanks: list) -> int:
    """gm_blanks(items 안의 항목 참조)에 time 을 안전 규칙으로 채운다 — items 를 그 자리에서 수정.

    gmwork-* 는 뺀다 — gm_surfaces_sync.plan_event() 가 새로 세울 때 time="" 을 그대로 박고
    diff()의 fix 경로는 next_due·assignee 두 칸만 고쳐 time 은 안 건드린다(코드 확인 2026-09-19).
    즉 카드가 살아있는 한 우리가 채운 time 은 보존되지만, 그 시간을 카드 쪽에 되먹일 길이
    없다(plan_event 가 카드에서 time 을 읽어오지 않는다) — GM업무 카드가 진짜 정본인 채로
    여기 time만 얹으면 다음에 카드를 열어도 그 시간이 안 보여 혼란만 남긴다. 카드 쪽에
    time 입력 경로가 생기기 전엔 자동기입 대상에서 뺀다."""
    taken: dict[str, set] = {}
    for it in items:
        d = str(it.get("next_due") or "")
        t = str(it.get("time") or "").strip()
        if d and t:
            taken.setdefault(d, set()).add(t[:5])
    applied = 0
    for it in gm_blanks:
        if str(it.get("id") or "").startswith("gmwork-"):
            continue
        base = _classify_gm_time(it.get("name") or "")
        if base is None:
            continue
        d = str(it.get("next_due") or "")
        slot = _bump_time(base, taken.setdefault(d, set()))
        it["time"] = slot
        taken[d].add(slot)
        applied += 1
    return applied


# ═══════════════════════════════════════════
# ④ 휴관일 충돌 — coo_registry._closed_day 재사용. 시설부가 휴관일에 하는 정비 일은
#   충돌이 아니라 원래 그날 하는 일이다 — 사무 일이 실수로 휴관일에 걸린 것만 남긴다.
# ═══════════════════════════════════════════
_CLOSED_EXCLUDE_NAME_WORDS = ("휴관일", "대청소", "순찰", "공사", "클리닝", "보수", "양생", "대회", "웰림픽", "송년회")
_CLOSED_EXCLUDE_ASSIGNEE_WORDS = ("시설부", "지원부", "소장")


def check_closed_day_conflict(items: list, today: date) -> list:
    out = []
    for it in items:
        due = _parse_date10(it.get("next_due"))
        if not due or due < today:
            continue  # 지난 날은 지금 와서 손댈 수 없다 — 대상 아님
        name = it.get("name") or ""
        if any(w in name for w in _CLOSED_EXCLUDE_NAME_WORDS):
            continue  # 휴관일에 하기로 정한 정비·행사성 일 — 원래 그날 할 일이다
        assignee = it.get("assignee") or ""
        if any(w in assignee for w in _CLOSED_EXCLUDE_ASSIGNEE_WORDS):
            continue  # 시설부·지원부·소장 담당은 휴관일 근무가 정상 업무다
        if not assignee.strip():
            continue
        if _closed_day(str(it.get("next_due") or "").strip()):
            out.append(it)
    return out


# ═══════════════════════════════════════════
# ⑥ 같은 todo_id 중복 — 업무 SSOT 한 행에 전사일정 항목이 2개 이상 걸린 경우(자동 처리 없음 · 목록만)
# ═══════════════════════════════════════════
def check_same_todo_id(items: list) -> list:
    groups: dict[str, list] = {}
    for it in items:
        tid = str(it.get("todo_id") or "").strip()
        if not tid:
            continue
        groups.setdefault(tid, []).append(it)
    return [g for g in groups.values() if len(g) >= 2]


# ═══════════════════════════════════════════
# 보고
# ═══════════════════════════════════════════
def _line(it: dict, reason: str) -> str:
    return f"  - [{it.get('id')}] {(it.get('name') or '')[:40]} · {it.get('next_due')} · {reason}"


def run_report(items: list, today: date, source_note: str) -> dict:
    dups = check_duplicates(items)
    fillers = check_stale_filler(items, today)
    gm_blanks = check_gm_time_blank(items, today)
    closed = check_closed_day_conflict(items, today)
    same_todo = check_same_todo_id(items)

    print(f"[전사일정 자동 정리 점검] 원천={source_note} · 대상 {len(items)}건")

    print(f"① 중복 {len(dups)}쌍")
    for a, b in dups:
        print(f"  - [{a.get('id')}]↔[{b.get('id')}] {(a.get('name') or '')[:30]} · {a.get('next_due')}")

    print(f"② 지난 필러 {len(fillers)}건")
    for it in fillers:
        print(_line(it, f"cycle={it.get('cycle') or '없음'}"))

    print(f"③ GM 시간 빈칸 {len(gm_blanks)}건")
    for it in gm_blanks:
        print(_line(it, f"assignee={it.get('assignee')}"))

    print(f"④ 휴관일 충돌 {len(closed)}건")
    for it in closed:
        print(_line(it, f"assignee={it.get('assignee')}"))

    print("⑤ 되살아남 — 삭제 이력 원장 없음(점검 생략)")

    print(f"⑥ 같은 todo_id 중복 {len(same_todo)}건")
    for g in same_todo:
        ids = ", ".join(str(x.get("id")) for x in g)
        print(f"  - todo_id={g[0].get('todo_id')} · {ids}")

    if not (dups or fillers or gm_blanks or closed or same_todo):
        print("→ 진짜 0건" if "라이브" in source_note else "→ 0건이나 원천 못 읽어 판정 보류")

    return {"dups": dups, "fillers": fillers, "gm_blanks": gm_blanks, "closed": closed, "same_todo": same_todo}


# ═══════════════════════════════════════════
# --selfcheck (네트워크 없음) — 음성·양성 사례는 2026-09-19 실측(라이브) 값 그대로.
# ═══════════════════════════════════════════
def _selfcheck() -> None:
    today = _kst_today()
    fake_soon = (today + timedelta(days=3)).isoformat()
    fake_future_closed = "2026-09-24" if today <= date(2026, 9, 24) else (today + timedelta(days=5)).isoformat()

    items = [
        # ── ① 음성(중복 아님) — 실측 실제 항목 ──
        {"id": "evt-20260909-gm-CCTV93대계약미팅블루캅추정7대추가단가외부",
         "name": "CCTV 100대 계약 미팅 — 완료(월 80만원 + 공사비 100만원)",
         "next_due": "2026-09-10", "time": "16:00", "assignee": "김남욱 GM", "cycle": ""},
        {"id": "evt-20260911-대표님-골프팀장-면접요청",
         "name": "대표님 보고 — 골프팀장 면접 요청(박상민·김태엽) + CCTV 100대 계약",
         "next_due": "2026-09-11", "time": "10:00", "assignee": "김남욱 GM", "cycle": ""},
        {"id": "park-check-start-20260918", "name": "주차 일일점검 제출 시작 — 주차관리부",
         "next_due": "2026-09-18", "time": "", "assignee": "양상규 고문", "cycle": "1회"},
        {"id": "evt-20260917-yang-off",
         "name": "양상규 고문 휴무 — 울트라마라톤 참가 (주차부 점검 제출 = 운영부 대처)",
         "next_due": "2026-09-17", "time": "", "assignee": "양상규 고문", "cycle": ""},
        {"id": "sup-roller-m", "name": "남 사우나 돌돌이 청소", "next_due": "2026-10-02",
         "time": "", "assignee": "지원부(남) 반장(박남일 반장)", "cycle": "격주"},
        {"id": "sup-roller-f", "name": "여 사우나 돌돌이 청소", "next_due": "2026-10-02",
         "time": "", "assignee": "지원부(여) 반장(이연희 반장)", "cycle": "격주"},
        {"id": "evt-20261011-주차장-양생", "name": "주차장 바닥 보수 작업 — 오전 (휴관일)",
         "next_due": "2026-10-11", "time": "오전", "assignee": "김남욱 GM", "cycle": ""},
        {"id": "sup-closedday-work-monthly", "name": "둘째주 휴관일 작업 (구역별)",
         "next_due": "2026-10-11", "time": "", "assignee": "지원부 전체(구역별 배정)",
         "cycle": "매월 둘째주 휴관일"},
        {"id": "evt-20260927-gm-새홈페이지ERP로그인ERP구조진행남은일A3요",
         "name": "새 홈페이지 → ERP 로그인 → ERP — 구조·진행·남은 일 A3 요약 (GM 직접)",
         "next_due": "2026-09-27", "time": "14:00", "assignee": "김남욱GM", "cycle": ""},
        {"id": "evt-20260928-gm-보고알림자동화손입력없애고중복발신정리GM직접",
         "name": "보고·알림 자동화 — 손 입력 없애고 중복 발신 정리 (GM 직접)",
         "next_due": "2026-09-28", "time": "14:00", "assignee": "김남욱GM", "cycle": ""},
        # ── ① 양성(중복 잡혀야 함) — 실측 실제 항목 ──
        {"id": "evt-1784519651465-3", "name": "수영장 도보라인 녹조제거",
         "next_due": "2026-07-14", "time": None, "assignee": "수영팀", "cycle": ""},
        {"id": "evt-1784519651465-4", "name": "수영장 도보라인 청소",
         "next_due": "2026-07-13", "time": None, "assignee": "수영팀", "cycle": ""},
        {"id": "evt-swim-clean-1011", "name": "수영장 대청소 — 10/11(일) 둘째 주 휴관일",
         "next_due": "2026-10-11", "time": "", "assignee": "김남욱 GM", "cycle": ""},
        {"id": "gmwork-2026-09-36", "name": "[GM업무] 수영장 대청소 — 10/11(일) 둘째 주 휴관일",
         "next_due": "2026-10-11", "time": "", "assignee": "김남욱 GM", "cycle": ""},
        # ── ②③④ 나머지 판정용 ──
        {"id": "b1", "name": "추석 연휴대비", "next_due": (today - timedelta(days=3)).isoformat(),
         "cycle": "", "assignee": "시우"},
        {"id": "c1", "name": "매출 결산 보고", "next_due": fake_soon, "time": "", "assignee": "김남욱 GM"},
        {"id": "c2", "name": "임원 실측 방문", "next_due": fake_soon, "time": "", "assignee": "김남욱 GM"},
        {"id": "d1", "name": "세스코 방역 점검", "next_due": "2026-09-25", "assignee": "시설부", "cycle": "월 1회"},
        {"id": "d2", "name": "회장님 보고 자료 준비 시작", "next_due": fake_future_closed,
         "assignee": "김남욱 GM", "cycle": ""},
        {"id": "d3", "name": "지난 휴관일 사무 건", "next_due": (today - timedelta(days=10)).isoformat(),
         "assignee": "김남욱 GM", "cycle": ""},
        {"id": "e1", "name": "정상 일정", "next_due": fake_soon, "time": "10:00", "assignee": "박호균 과장"},
        # ── ⑥ 같은 todo_id 중복 판정용(time 채워서 ③ 대상에서 뺀다) ──
        {"id": "evt-f1", "name": "공조 민원 접수", "next_due": fake_soon, "time": "10:00",
         "assignee": "김남욱 GM", "todo_id": "TODO-DUPTEST"},
        {"id": "gmwork-f1", "name": "[GM업무] 공조 민원 접수", "next_due": fake_soon, "time": "10:00",
         "assignee": "김남욱 GM", "todo_id": "TODO-DUPTEST"},
        {"id": "evt-f2", "name": "다른 건", "next_due": fake_soon, "time": "10:00",
         "assignee": "김남욱 GM", "todo_id": "TODO-UNIQUE"},
    ]

    dups = check_duplicates(items)
    neg_pairs = [
        {"evt-20260909-gm-CCTV93대계약미팅블루캅추정7대추가단가외부", "evt-20260911-대표님-골프팀장-면접요청"},
        {"park-check-start-20260918", "evt-20260917-yang-off"},
        {"sup-roller-m", "sup-roller-f"},
        {"evt-20261011-주차장-양생", "sup-closedday-work-monthly"},
        {"evt-20260927-gm-새홈페이지ERP로그인ERP구조진행남은일A3요", "evt-20260928-gm-보고알림자동화손입력없애고중복발신정리GM직접"},
    ]
    got_pairs = [{a.get("id"), b.get("id")} for a, b in dups]
    for np in neg_pairs:
        assert np not in got_pairs, f"헛경보(중복 아닌데 잡음): {np}"
    assert {"evt-1784519651465-3", "evt-1784519651465-4"} in got_pairs, "타임스탬프 형제 못 잡음"
    assert {"evt-swim-clean-1011", "gmwork-2026-09-36"} in got_pairs, "GM업무 짝 중복 못 잡음"

    fillers = check_stale_filler(items, today)
    assert any(it["id"] == "b1" for it in fillers), f"지난 필러 못 잡음: {fillers}"
    assert not any(it["id"] == "e1" for it in fillers)

    gm_blanks = check_gm_time_blank(items, today)
    ids_blank = {it["id"] for it in gm_blanks}
    assert "c1" in ids_blank, f"GM 시간 빈칸 못 잡음: {gm_blanks}"
    assert "e1" not in ids_blank, "시간 있는 일정을 빈칸으로 오판"

    closed = check_closed_day_conflict(items, today)
    ids_closed = {it["id"] for it in closed}
    assert "d1" not in ids_closed, "시설부 담당 휴관일 정비를 충돌로 오판"
    assert "d2" in ids_closed, f"사무 일 휴관일 충돌 못 잡음: {closed}"
    assert "d3" not in ids_closed, "지난 날짜를 충돌로 오판"

    same_todo = check_same_todo_id(items)
    same_todo_ids = {tuple(sorted(str(x.get("id")) for x in g)) for g in same_todo}
    assert ("evt-f1", "gmwork-f1") in same_todo_ids, f"같은 todo_id 중복 못 잡음: {same_todo}"
    assert not any("evt-f2" in g for g in same_todo_ids), "혼자인 todo_id 를 중복으로 오판"

    applied = apply_gm_time_fill(items, gm_blanks)
    by_id = {it["id"]: it for it in items}
    assert by_id["c1"]["time"] == "14:00", by_id["c1"]  # 기본값 = 내부 검토
    assert by_id["c2"]["time"] == "", "실측(면담류)에 시간을 지어냄"
    assert by_id["d2"]["time"] == "14:00", by_id["d2"]
    assert applied == 2, f"채운 건수 어긋남(c1·d2 · 실측 c2 제외): {applied}"

    print("[selfcheck] schedule_hygiene 판정 OK")


# ═══════════════════════════════════════════
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="③ GM 시간 빈칸만 안전 규칙으로 채우고 push")
    ap.add_argument("--selfcheck", action="store_true", help="가짜 항목으로 판정 자체점검(네트워크 없음)")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return

    pull = schedule_ssot.pull_from_live()
    source_note = "라이브(GAS)" if pull.get("ok") else f"원천 못 읽음({pull.get('reason')}) · 캐시로 점검"

    cal = schedule_ssot.load()
    items = cal.get("items") or []
    today = _kst_today()

    result = run_report(items, today, source_note)

    if args.apply:
        before = len(items)
        applied = apply_gm_time_fill(items, result["gm_blanks"])
        assert len(items) == before, "건수가 바뀜 — push 중단"  # push 전 건수 assert
        if applied:
            cal["items"] = items
            cal["updated_at"] = today.isoformat()
            schedule_ssot.CAL_PATH.write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
            push = schedule_ssot.push_to_live(cal)
            print(f"[적용] ③ GM 시간 빈칸 {applied}건 채움(GM업무 카드 짝·실측류 제외) → push "
                  + ("성공" if push.get("ok") else f"실패: {push.get('reason')}"))
        else:
            print("[적용] 채울 항목 없음")

    counts = {k: len(v) for k, v in result.items()}
    worklog_log(
        "coo", "일정위생",
        f"전사일정 자동 정리 점검 — 중복{counts['dups']}·필러{counts['fillers']}"
        f"·GM빈칸{counts['gm_blanks']}·휴관충돌{counts['closed']}·todo_id중복{counts['same_todo']}",
        result="ok" if pull.get("ok") else "warn",
        detail=source_note,
        ref="schedule_hygiene",
    )


if __name__ == "__main__":
    main()
