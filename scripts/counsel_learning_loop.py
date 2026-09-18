#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""counsel_learning_loop.py — 상담봇 학습 루프 한 관문 (GM 지시 2026-09-17 「정말 중요」).

손님 질문 → 유형 → 3업체 전파 → 빈칸을 번호 질문으로(중복 0) → 답 접수 → 정본 → 누적 지표.
모델 0 · 규칙만 · 언제든 재실행(멱등). 카톡 발송·서버 배포는 이 스크립트가 하지 않는다.

흐름
  ① 수집·가공  status/_private/counsel_questions.jsonl(원장 · counsel_questions.py 가 서버 /log·/unanswered 를 합쳐
              쌓은 것 · 예약작업에서 이 스크립트 바로 앞에 돈다 — 서버를 다시 부르지 않는다) 의 질문을
              question_types 에 붙인다(faq_hub.match_type 재사용). 어느 유형에도 안 붙고 2회 이상 나온 질문은
              새 유형 후보로 server/counselbot/shared/question_candidates.json 에 누적한다(정규화 문장·횟수·센터수·첫날 —
              공통 학습층이라 손님 원문·센터 id 는 싣지 않는다 · 설계 §12 ② · 배 12763).
              ★후보는 자동 승격하지 않는다 — 시보가 유형(answer_skeleton·needs_facts)을 정해 question_types 에
              넣으면 그 순간 전 업체에 전파된다(②가 매일 전 업체를 대조하므로).
  ② 전파      유형마다 needs_facts 를 3업체 전부에 대조 — api_chat._fact_present 와 같은 규칙(아래 fact_present ·
              --self-test 가 두 함수의 결과가 같음을 보인다). 있으면 즉시 답 가능, 없으면 빈칸.
  ③ 번호 질문  빈칸 경로 → question_bank 의 fills(경로 목록) 로 질문 하나에 매핑 → 그 업체 qa 파일에 q_id 가 없을 때만
              다음 partner_no 로 추가(asked_on 비움 = 아직 안 물음). 이미 있으면(답 있든 없든) 절대 다시 넣지 않는다.
              규칙으로 판정할 수 없는 경로 표기(offerings[trial]·channels.* 등 · judgeable()=False)는 질문을 만들지
              않고 지표 파일 「판정불가_경로」에 적는다 — 이미 아는 것을 다시 묻지 않기 위해서다.
  ④ 물을 묶음  업체별 「아직 안 물은 번호」 → status/counsel_ask_pending.json. 발송은 partner_onboarding_publish
              --kakao {키} 로 시보가 사흘에 한 번 묶음으로 · 보낸 뒤 --mark-asked {키}.
  ⑤ 답 접수    --answer {키} {번호} "답" → qa answer/answered_on + fills 경로에 값(빈 단순 경로만 자동 ·
              policies[topic=X] 는 {topic,text} 추가 · 구조 칸·이미 값 있는 칸은 tenants 파일 _pending_manual 에) →
              client_counselbot_check → 「deploy_chat.sh 로 배포」 안내(배포는 시보/시토 손).
  ⑥ 누적 지표  status/counsel_learning.json — 업체별 6칸 + 전체 + 30일 추이. 랩스 관리자 판 index.html 이 읽는다.

쓰는 법
  C:/Python314/python.exe scripts/counsel_learning_loop.py                 # ①~④·⑥ 한 바퀴
  C:/Python314/python.exe scripts/counsel_learning_loop.py --mark-asked jo  # 고척에 pending 번호를 보낸 뒤
  C:/Python314/python.exe scripts/counsel_learning_loop.py --answer jo 51 "답 문장"
  C:/Python314/python.exe scripts/counsel_learning_loop.py --self-test     # 가짜 업체 데이터 · 실값 0
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from faq_hub import match_type, build as faq_build          # noqa: E402
from partner_onboarding_publish import bank_index, TENANT_KEYS  # noqa: E402
from counsel_questions import load_ledger                    # noqa: E402

CB = ROOT / "server" / "counselbot"
BANK = CB / "question_bank.json"
TYPES = CB / "shared" / "question_types.json"
CANDIDATES = CB / "shared" / "question_candidates.json"
TENANTS = CB / "tenants"
PENDING = ROOT / "status" / "counsel_ask_pending.json"
LEARNING = ROOT / "status" / "counsel_learning.json"
KST = timezone(timedelta(hours=9))
_PHONE = re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
EMPTY = (None, "", "미수령")


def today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p: Path, d) -> None:
    """있는 파일은 그 들여쓰기(qa 2 · 은행 1)를 지켜 diff 가 내 줄만 나오게 한다."""
    p.parent.mkdir(parents=True, exist_ok=True)
    indent = 1
    if p.exists():
        lines = p.read_text(encoding="utf-8").split(chr(10))
        for line in lines[1:]:            # 둘째 줄부터 첫 들여쓰기 한 줄을 본다
            m = re.match(r"( +)\S", line)
            if m:
                indent = len(m.group(1))
                break
    io.open(p, "w", encoding="utf-8", newline=chr(10)).write(json.dumps(d, ensure_ascii=False, indent=indent) + chr(10))


def mask(q: str) -> str:
    return _EMAIL.sub("[이메일]", _PHONE.sub("[전화번호]", q or ""))


_TAIL_PUNCT = "?？!！.。~ "


def norm_q(q: str) -> str:
    """후보 열쇠 = 마스킹 + 공백 정리 + 끝 문장부호 제거(「지금 영업해요?」·「지금 영업해요」 = 한 후보). 원문은 원장에만."""
    return " ".join(mask(q or "").split()).rstrip(_TAIL_PUNCT)


def _migrate_candidates(items: dict) -> dict:
    """옛 규격(원문 열쇠 · 업체 목록) → 새 규격(정규화 열쇠 · 센터수). 한 번 지나면 그대로."""
    out: dict = {}
    for q, c in items.items():
        k = norm_q(q)
        n = c.get("센터수") or len(c.get("업체") or [])
        cur = out.get(k) or {"질문": k, "횟수": 0, "센터수": 0, "첫날": c.get("첫날") or ""}
        cur["횟수"] = max(cur["횟수"], c.get("횟수") or 0)
        cur["센터수"] = max(cur["센터수"], n)
        cur["첫날"] = min(cur["첫날"] or c.get("첫날") or "", c.get("첫날") or cur["첫날"])
        out[k] = cur
    return out


# ── ② api_chat._fact_present 와 같은 규칙(서버 코드는 import 하지 않는다 · --self-test 가 동일함을 보인다) ──
def fact_present(prof: dict, path: str) -> bool:
    if "[topic=" in path:
        base, rest = path.split("[topic=", 1)
        topic = rest.rstrip("]")
        items = (prof or {}).get(base) or []
        return any(topic in (it.get("topic") or "") for it in items if isinstance(it, dict))
    if "[]" in path:
        return bool((prof or {}).get(path.split("[", 1)[0]) or [])
    node = prof or {}
    for part in path.split("."):
        if not isinstance(node, dict):
            return False
        node = node.get(part)
    if isinstance(node, dict):
        return any(v not in (None, "", "미수령", []) for k, v in node.items() if not k.startswith("_"))
    return node not in EMPTY


def judgeable(path: str) -> bool:
    """규칙이 값을 볼 수 있는 표기인가. offerings[trial]·channels.* 는 위 규칙이 언제나 False 라 물어도 소용없다."""
    if "*" in path:
        return False
    return "[" not in path or "[]" in path or "[topic=" in path


def missing_by_tenant(types: list, profiles: dict) -> dict:
    """업체 → {경로: [유형…]} (빈칸만)."""
    out = {t: {} for t in profiles}
    for ty in types:
        for t, prof in profiles.items():
            for p in ty.get("needs_facts") or []:
                if not fact_present(prof, p):
                    out[t].setdefault(p, []).append(ty["type_id"])
    return out


# ── ① 후보 누적 ──
def collect_candidates(rows: list, types: list, cands: dict) -> tuple[dict, dict]:
    """유형에 안 붙는 질문(2회 이상)을 후보에 누적. 돌려주는 둘째 값 = 업체별 유형 붙은 수."""
    seen: dict = {}
    typed: dict = {}
    for r in rows:
        if r.get("is_test") or not r.get("q"):
            continue
        q = norm_q(r["q"])
        tid = r.get("type_id") or match_type({"q": q}, types)
        if tid:
            typed.setdefault(r["tenant"], set()).add(tid)
            continue
        c = seen.setdefault(q, {"질문": q, "업체": set(), "횟수": 0, "첫날": (r.get("ts") or "")[:10]})
        c["업체"].add(r["tenant"])
        c["횟수"] += 1
        c["첫날"] = min(c["첫날"], (r.get("ts") or "")[:10]) or c["첫날"]
    items = cands["candidates"] = _migrate_candidates(cands.get("candidates") or {})
    for q, c in seen.items():
        if c["횟수"] < 2:
            continue
        cur = items.get(q) or {"질문": q, "횟수": 0, "센터수": 0, "첫날": c["첫날"]}
        cur["센터수"] = max(cur["센터수"], len(c["업체"]))   # 어느 센터인지는 원장에서 되짚는다(공통층에 센터 id 금지)
        cur["횟수"] = max(cur["횟수"], c["횟수"])   # 원장은 누적이라 같은 줄을 다시 센다 — 큰 쪽이 진짜
        cur["첫날"] = min(cur["첫날"], c["첫날"])
        items[q] = cur
    cands["_rule"] = ("후보는 자동 승격하지 않는다. 시보가 유형(answer_skeleton·needs_facts)을 정해 "
                      "question_types.json 에 넣으면 그 순간 전 업체에 전파된다. 정규화 문장·횟수·센터수만 — 손님 원문·센터 id 는 여기 없다(설계 §12 ②).")
    cands["updated"] = today()
    return cands, typed


# ── ③ 빈칸 → 번호 질문 ──
def path_to_qid(bank: dict) -> dict:
    out = {}
    for qid, q in bank_index(bank).items():
        for p in q.get("fills") or []:
            out.setdefault(p, qid)
    return out


# 업체별 번호 바닥 — 카톡으로 이미 나간 번호 대역과 겹치지 않게 한다(GM 2026-09-17 「반복 중복 질문 절대 금지」).
#   dc = _받을것.md 1~19 를 9/17 설문으로 보냈다 → 20 부터 · jo = 19~48 을 9/17 설문으로 보냈다 → 49 부터
#   wellperion = 파트너가 아니라 우리 것(카톡 설문 없음) → 1 부터
NUMBER_FLOOR = {"dc": 20, "jo": 49, "wellperion": 1}


def add_pending_questions(qa: list, missing: dict, bank: dict, p2q: dict, key: str = "") -> list:
    """qa 에 없는 q_id 만 다음 partner_no 로 추가 — 돌려주는 값 = 새로 넣은 행."""
    idx = bank_index(bank)
    have = {r.get("q_id") for r in qa}
    nxt = max([r.get("partner_no") or 0 for r in qa] + [NUMBER_FLOOR.get(key, 1) - 1]) + 1
    added = []
    for path in sorted(missing):
        if not judgeable(path):
            continue
        qid = p2q.get(path)
        if not qid or qid in have:
            continue
        row = {"q_id": qid, "partner_no": nxt, "q": idx[qid]["q"], "answer": None, "asked_on": None,
               "why": "상담봇 빈칸 " + " · ".join(sorted({p for p in missing if p2q.get(p) == qid}))}
        qa.append(row)
        added.append(row)
        have.add(qid)
        nxt += 1
    return added


def pending_of(qa: list) -> list:
    return [{"partner_no": r["partner_no"], "q_id": r.get("q_id"), "q": r.get("q")}
            for r in qa if r.get("partner_no") and not r.get("answer") and not r.get("asked_on")]


# ── ⑤ 답 → 정본 ──
def apply_answer(prof: dict, path: str, answer: str, src: str) -> str:
    """빈 단순 경로·없는 topic 만 자동. 나머지는 _pending_manual. 돌려주는 값 = 어떻게 처리했나."""
    if "[topic=" in path:
        base, topic = path.split("[topic=", 1)
        topic = topic.rstrip("]")
        items = prof.setdefault(base, [])
        if any(topic in (it.get("topic") or "") for it in items if isinstance(it, dict)):
            return _manual(prof, path, answer, "같은 topic 이 이미 있다")
        items.append({"topic": topic, "text": answer, "source": src})
        return "추가"
    if not judgeable(path) or "[]" in path:
        return _manual(prof, path, answer, "구조 칸")
    parts = path.split(".")
    node = prof
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            if node.get(part) not in EMPTY:
                return _manual(prof, path, answer, "중간 칸이 dict 가 아니다")
            node[part] = {}
        node = node[part]
    cur = node.get(parts[-1])
    if isinstance(cur, (dict, list)) or cur not in EMPTY:
        return _manual(prof, path, answer, "이미 값이 있다")
    node[parts[-1]] = answer
    node[parts[-1] + "_source"] = src
    return "자동"


def _manual(prof: dict, path: str, answer: str, why: str) -> str:
    prof.setdefault("_pending_manual", []).append({"path": path, "answer": answer, "why": why, "on": today()})
    return "수동(_pending_manual)"


def do_answer(key: str, no: int, answer: str) -> int:
    folder = TENANT_KEYS[key]
    qa_p, prof_p = TENANTS / f"{folder}_qa.json", TENANTS / f"{folder}.json"
    qa, prof, bank = load(qa_p, []), load(prof_p, {}), load(BANK, {})
    row = next((r for r in qa if r.get("partner_no") == no), None)
    if not row:
        print(f"[{key}] 번호 {no} 가 qa 파일에 없다"); return 1
    row["answer"], row["answered_on"] = answer, today()
    row.setdefault("source", f"카톡 {today()}")
    fills = (bank_index(bank).get(row.get("q_id"), {}).get("fills")) or []
    done = {p: apply_answer(prof, p, answer, f"{key} 번호 {no} 답 · {today()}") for p in fills}
    if any(v in ("자동", "추가") for v in done.values()):
        row["promoted_to"] = " · ".join(p for p, v in done.items() if v in ("자동", "추가"))
    save(qa_p, qa)
    if fills:
        save(prof_p, prof)
    for p, v in done.items():
        print(f"  {p}: {v}")
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "scripts" / "client_counselbot_check.py"), folder])
    print(f"→ 정본이 바뀌었다. 배포 = bash server/deploy_chat.sh (시보/시토 손) · 수동 칸은 {prof_p.name} _pending_manual")
    return 0


def do_mark_asked(key: str) -> int:
    qa_p = TENANTS / f"{TENANT_KEYS[key]}_qa.json"
    qa = load(qa_p, [])
    n = 0
    for r in qa:
        if r.get("partner_no") and not r.get("answer") and not r.get("asked_on"):
            r["asked_on"] = today(); n += 1
    save(qa_p, qa)
    print(f"[{key}] asked_on 찍음 {n}건")
    return 0


# ── 한 바퀴(①~④·⑥) ──
def run(rows: list, types: list, bank: dict, profiles: dict, qa_by: dict, cands: dict,
        learning: dict, faq_centers: dict) -> tuple[dict, dict, dict, dict]:
    cands, typed = collect_candidates(rows, types, cands)
    missing = missing_by_tenant(types, profiles)
    p2q = path_to_qid(bank)
    pending, per = {}, {}
    new_total = 0
    for t, prof in profiles.items():
        qa = qa_by[t]
        key = next((k for k, f in TENANT_KEYS.items() if f == t), t)
        added = add_pending_questions(qa, missing[t], bank, p2q, key)
        new_total += len(added)
        pending[key] = pending_of(qa)
        mine = [r for r in rows if r.get("tenant") == t and not r.get("is_test") and r.get("q")]
        ans = sum(1 for r in mine if r.get("answered"))
        per[t] = {
            "name": (prof.get("tenant") or {}).get("name") or t,
            "총_질문": len(mine), "답한_것": ans, "답변율": round(ans / len(mine), 3) if mine else None,
            "유형_커버리지": f"{len(faq_centers.get(t, {}).get('covered') or {})}/{len(types)}",
            "빈칸_수": sum(1 for p in missing[t] if judgeable(p)),
            "빈칸": sorted(p for p in missing[t] if judgeable(p)),
            "판정불가_경로": sorted(p for p in missing[t] if not judgeable(p)),
            "안_물은_번호_수": len(pending[key]),
            "답_온_번호_수": sum(1 for r in qa if r.get("partner_no") and r.get("answer")),
            "오늘_새_번호": [r["partner_no"] for r in added],
        }
    day = today()
    hist = [h for h in learning.get("추이", []) if h.get("날짜") != day]
    hist.append({"날짜": day, **{t: [v["총_질문"], v["답한_것"], v["빈칸_수"], v["안_물은_번호_수"], v["답_온_번호_수"]]
                              for t, v in per.items()}})
    learning = {
        "_about": "상담봇 학습 루프 누적 지표 — scripts/counsel_learning_loop.py 가 만든다. 손으로 고치지 않는다.",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "centers": per,
        "all": {"유형_수": len(types), "후보_수": len(cands.get("candidates", {})),
                "오늘_새로_전파된_빈칸_수": new_total},
        "추이": hist[-30:],
        "추이_칸": "[총_질문, 답한_것, 빈칸_수, 안_물은_번호_수, 답_온_번호_수]",
    }
    pend = {"_about": "아직 안 물은 번호(업체 키별) — 발송은 partner_onboarding_publish --kakao {키} · 보낸 뒤 "
                      "counsel_learning_loop --mark-asked {키}", "generated_at": learning["generated_at"], "tenants": pending}
    return cands, pend, learning, qa_by


def main_run() -> int:
    types = load(TYPES, {})["types"]
    bank = load(BANK, {})
    rows = list(load_ledger().values())
    profiles = {f: load(TENANTS / f"{f}.json", {}) for f in TENANT_KEYS.values()}
    qa_by = {f: load(TENANTS / f"{f}_qa.json", []) for f in TENANT_KEYS.values()}
    cands, pend, learning, qa_by = run(rows, types, bank, profiles, qa_by, load(CANDIDATES, {}),
                                       load(LEARNING, {}), faq_build().get("centers", {}))
    save(CANDIDATES, cands); save(PENDING, pend); save(LEARNING, learning)
    for f, qa in qa_by.items():
        save(TENANTS / f"{f}_qa.json", qa)
    for t, v in learning["centers"].items():
        print(f"{v['name']}: 질문 {v['총_질문']} · 답변율 {v['답변율']} · 커버리지 {v['유형_커버리지']} · "
              f"빈칸 {v['빈칸_수']} · 안 물은 번호 {v['안_물은_번호_수']} · 오늘 새 번호 {v['오늘_새_번호']}")
    print(f"후보 유형 {learning['all']['후보_수']} · 판정불가 경로 = 지표 파일 참조 → {LEARNING.relative_to(ROOT)}")
    return 0


def self_test() -> None:
    # ② 같은 규칙인지 — 서버 함수를 부를 수 있으면 같은 입력으로 대조, 못 부르면 서버 selfcheck 의 고정 표로.
    cases = [({"facts": {"hours": {"weekday": "06:00"}}}, "facts.hours", True),
             ({"facts": {"hours": None}}, "facts.hours", False),
             ({"facts": {"parking": None, "_note": "미수령"}}, "facts.parking", False),
             ({"facts": {"parking": "무료"}}, "facts.parking", True),
             ({"policies": [{"topic": "환불 규정"}]}, "policies[topic=환불]", True),
             ({"policies": []}, "policies[topic=환불]", False),
             ({"offerings": [{"name": "x"}]}, "offerings[].who", True),
             ({}, "offerings[trial]", False), ({"channels": {"kakao": "y"}}, "channels.*", False)]
    try:
        sys.path.insert(0, str(ROOT / "server" / "erp_api"))
        import api_chat  # noqa
        ref = api_chat._fact_present
        print("  api_chat._fact_present 직접 대조")
    except Exception:
        ref = lambda prof, path: next(e for p, pa, e in cases if p is prof and pa == path)  # noqa: E731
        print("  (api_chat import 불가 — 고정 표로 대조)")
    for prof, path, exp in cases:
        assert fact_present(prof, path) == ref(prof, path) == exp, (path, prof)
    assert judgeable("facts.parking") and judgeable("policies[topic=환불]") and judgeable("offerings[].who")
    assert not judgeable("offerings[trial]") and not judgeable("channels.*")

    # ①·③·④·⑥ 가짜 업체 둘 · 실값 0
    types = [{"type_id": "parking", "examples": ["주차 되나요"], "needs_facts": ["facts.parking"]},
             {"type_id": "refund", "examples": ["환불 되나요"], "needs_facts": ["policies[topic=환불]", "offerings[trial]"]}]
    bank = {"questions": [{"area": "A 기본", "q": "주차는?", "fills": ["facts.parking"]},
                          {"area": "E 규정", "q": "환불은?", "fills": ["policies[topic=환불]"]}]}
    rows = [{"tenant": "t1", "q": "주차 되나요", "answered": True, "ts": "2026-09-01T10:00"},
            {"tenant": "t1", "q": "달나라 가나요", "answered": False, "ts": "2026-09-02T10:00"},
            {"tenant": "t2", "q": "달나라 가나요", "answered": False, "ts": "2026-09-01T09:00"},
            {"tenant": "t2", "q": "혼자 온 질문", "answered": False, "ts": "2026-09-01T09:00"},
            {"tenant": "t2", "q": "테스트 010-1234-5678", "answered": False, "is_test": True, "ts": "2026-09-01"}]
    profiles = {"t1": {"tenant": {"name": "가"}, "facts": {"parking": "있음"}, "policies": []},
                "t2": {"tenant": {"name": "나"}, "facts": {}, "policies": [{"topic": "환불", "text": "x"}]}}
    qa_by = {"t1": [{"q_id": "E-1", "partner_no": 3, "answer": None, "asked_on": "2026-09-10"}], "t2": []}
    cands, pend, learn, qa_by = run(rows, types, bank, profiles, qa_by, {}, {}, {"t1": {"covered": {"parking": ["f1"]}}})
    assert list(cands["candidates"]) == ["달나라 가나요"], cands           # 2회·두 업체 → 후보 · 1회짜리는 아님
    assert cands["candidates"]["달나라 가나요"]["센터수"] == 2 and "업체" not in cands["candidates"]["달나라 가나요"]
    assert norm_q("지금 영업해요?  ") == "지금 영업해요" and norm_q("010-1234-5678 로요") == "[전화번호] 로요"
    old = {"영업해요?": {"질문": "영업해요?", "업체": ["a", "b"], "횟수": 3, "첫날": "2026-09-05"}}
    assert _migrate_candidates(old) == {"영업해요": {"질문": "영업해요", "횟수": 3, "센터수": 2, "첫날": "2026-09-05"}}
    assert cands["candidates"]["달나라 가나요"]["첫날"] == "2026-09-01"
    assert [r["q_id"] for r in qa_by["t1"]] == ["E-1"], qa_by["t1"]         # 이미 있는 번호는 다시 안 넣는다(답 없어도)
    assert [r["q_id"] for r in qa_by["t2"]] == ["A-1"] and qa_by["t2"][0]["partner_no"] == 1
    assert learn["centers"]["t2"]["판정불가_경로"] == ["offerings[trial]"]  # 규칙이 못 보는 표기는 질문 안 만든다
    assert learn["centers"]["t1"]["유형_커버리지"] == "1/2" and learn["centers"]["t1"]["답변율"] == 0.5
    assert pend["tenants"]["t2"] == [{"partner_no": 1, "q_id": "A-1", "q": "주차는?"}] and pend["tenants"]["t1"] == []
    assert learn["all"]["오늘_새로_전파된_빈칸_수"] == 1 and len(learn["추이"]) == 1
    # 멱등 — 한 번 더 돌려도 번호가 안 는다
    _, _, learn2, qa_by2 = run(rows, types, bank, profiles, qa_by, cands, learn, {})
    assert len(qa_by2["t2"]) == 1 and learn2["all"]["오늘_새로_전파된_빈칸_수"] == 0 and len(learn2["추이"]) == 1

    # ⑤ 답 → 정본
    prof = {"facts": {"parking": None}, "policies": [{"topic": "환불", "text": "x"}], "staff": None}
    assert apply_answer(prof, "facts.parking", "무료 10대", "s") == "자동" and prof["facts"]["parking"] == "무료 10대"
    assert apply_answer(prof, "facts.parking", "덮어쓰기", "s").startswith("수동") and prof["facts"]["parking"] == "무료 10대"
    assert apply_answer(prof, "policies[topic=연기]", "1회", "s") == "추가" and prof["policies"][-1]["topic"] == "연기"
    assert apply_answer(prof, "policies[topic=환불]", "y", "s").startswith("수동")
    assert apply_answer(prof, "staff.contact_hours", "10~18시", "s") == "자동" and prof["staff"]["contact_hours"] == "10~18시"
    assert apply_answer(prof, "offerings[].who", "z", "s").startswith("수동") and len(prof["_pending_manual"]) == 3
    assert mask("010-1234-5678 로 a@b.co") == "[전화번호] 로 [이메일]"
    print("counsel_learning_loop 자가점검 통과")


def main() -> int:
    ap = argparse.ArgumentParser(description="상담봇 학습 루프 한 관문")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--mark-asked", choices=sorted(TENANT_KEYS), metavar="키")
    ap.add_argument("--answer", nargs=3, metavar=("키", "번호", "답"))
    a = ap.parse_args()
    if a.self_test:
        self_test(); return 0
    if a.mark_asked:
        return do_mark_asked(a.mark_asked)
    if a.answer:
        key, no, ans = a.answer
        if key not in TENANT_KEYS:
            print("키 = " + " · ".join(sorted(TENANT_KEYS))); return 1
        return do_answer(key, int(no), ans)
    return main_run()


if __name__ == "__main__":
    sys.exit(main())
