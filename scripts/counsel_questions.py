#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""counsel_questions.py — 상담봇에 손님이 던진 질문을 저장소 원장에 쌓고 가공한다.

GM 지시 2026-09-11: 「erp.wellperion.com/counsel/ 여기에 질문하는 것들 다 저장하고 가공해줘,
정말 중요한거야」.

왜 있나 — 질문은 서버 파일(/srv/erp/chat_log.jsonl) 한 벌에만 있고, 그마저 조회는
미답 50건에서 잘린다(2026-09-11 실측: stats 총 153건인데 목록으로 꺼낼 수 있는 것은 50건).
서버가 날아가거나 로그가 회전하면 손님이 무엇을 물었는지가 통째로 사라진다.
이 스크립트가 매일 긁어 저장소에 쌓으면 그 순간부터는 사라지지 않는다.

정본·수집 순서(가능한 통로부터 · 통로가 넓어지면 그 앞쪽만 쓴다):
  1) GET /api/chat/{tenant}/log      — 답한 것 포함 전량(시토 배2533② · 2026-09-11 열림 · 이쪽이 정본)
  2) GET /api/chat/{tenant}/unanswered?gaps=1 — ①이 막혔을 때만 쓰는 대비 통로(미답·50건에서 잘린다)
  3) GET /api/chat/{tenant}/stats    — 집계값(총계·답변율·많이 물은 미답)

쌓는 곳(둘 다 저장소 · 언제든 다시 만들 수 있는 것은 만들지 않는다):
  status/counsel_questions.jsonl        원장 — 질문 한 줄씩, 합집합으로만 더한다(삭제 0)
  status/counsel_questions_summary.json 가공 — 센터별 집계·유형별·많이 물은 것·날짜별

쓰는 법:
  C:/Python314/python.exe scripts/counsel_questions.py            # 수집 + 가공
  C:/Python314/python.exe scripts/counsel_questions.py --summary  # 이미 쌓인 것으로 가공만
  C:/Python314/python.exe scripts/counsel_questions.py --selftest # 자가점검(서버 접속 없음)
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "status" / "counsel_questions.jsonl"
SUMMARY = ROOT / "status" / "counsel_questions_summary.json"
TENANTS_FILE = ROOT / "3. 웰페리온 가이드" / "cbo" / "counsel_tenants.json"
KST = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def tenants() -> list[dict]:
    """업체 목록은 화면이 쓰는 그 파일 하나에서 읽는다(목록을 두 벌 두지 않는다)."""
    return json.loads(TENANTS_FILE.read_text(encoding="utf-8"))["tenants"]


def key_of(row: dict) -> str:
    """같은 질문인지 가르는 열쇠 — 시각·센터·질문이 같으면 같은 줄이다."""
    return "%s|%s|%s" % (row.get("ts", ""), row.get("tenant", ""), row.get("q", ""))


def load_ledger() -> dict:
    """원장을 열쇠→줄 로 읽는다. 깨진 줄은 건너뛰되 세어 둔다(조용히 삼키지 않는다)."""
    rows, broken = {}, 0
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                broken += 1
                continue
            rows[key_of(r)] = r
    if broken:
        print("[원장] 읽지 못한 줄 %d개 — 건너뜀" % broken, file=sys.stderr)
    return rows


def save_ledger(rows: dict) -> None:
    """시각순으로 다시 쓴다. 있던 줄은 지우지 않는다 — 이 함수는 합집합 결과만 받는다."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    out = sorted(rows.values(), key=lambda r: (r.get("ts") or "", r.get("tenant") or ""))
    LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
                      encoding="utf-8")


def fetch_rows(op, api, tenant: str, days: int) -> list[dict]:
    """그 센터의 질문을 지금 열려 있는 가장 넓은 통로로 받는다."""
    import erp_live_audit as e

    # ① 전량 통로(시토 배2533② · 2026-09-11 열림). offset 으로 끝까지 넘긴다 —
    #    next_offset 이 null 이면 끝이다. 한 장만 받고 마치면 건수가 늘었을 때 조용히 잘린다.
    out, offset, guard = [], 0, 0
    while True:
        st, body = e.fetch(op, "%s/log?days=%d&limit=500&offset=%d" % (api, days, offset))
        if st != 200:
            break
        try:
            d = json.loads(body)
        except json.JSONDecodeError:
            break
        out += [{**r, "tenant": tenant, "source": "log"} for r in (d.get("rows") or [])]
        offset = d.get("next_offset")
        guard += 1
        if offset is None or guard > 40:   # ponytail: 20,000줄이면 멈춘다 — 무한 고리 방지
            break
    if out:
        return out

    # ② 지금 열려 있는 통로 — 미답만·50건에서 잘린다(2026-09-11 실측). 반쪽인 것을 숨기지 않는다.
    st, body = e.fetch(op, "%s/unanswered?days=%d&gaps=1" % (api, days))
    if st != 200:
        print("[%s] 질문을 받지 못했다(HTTP %s)" % (tenant, st), file=sys.stderr)
        return []
    qs = json.loads(body).get("questions") or []
    return [{"ts": q.get("ts"), "q": q.get("q"), "a": "", "answered": bool(q.get("answered")),
             "needs_facts": q.get("needs_facts") or [], "type_id": q.get("type_id"),
             "tenant": tenant, "source": "unanswered"} for q in qs]


def collect(days: int = 365) -> dict:
    """서버에서 받아 원장에 더한다. 더하기만 한다 — 서버에서 사라진 줄도 원장에는 남는다."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import erp_live_audit as e

    op = e.login()
    rows = load_ledger()
    before = len(rows)
    stats = {}
    for t in tenants():
        api = "/api/chat/" + t["id"]
        for r in fetch_rows(op, api, t["id"], days):
            if r.get("q"):
                rows.setdefault(key_of(r), r)
        st, body = e.fetch(op, "%s/stats?days=%d" % (api, days))
        if st == 200:
            stats[t["id"]] = json.loads(body)
    save_ledger(rows)
    print("원장 %d줄 → %d줄 (새로 %d줄)" % (before, len(rows), len(rows) - before))
    return stats


def summarize(stats: dict | None = None) -> dict:
    """가공 — 쌓인 질문을 센터별·유형별·날짜별로 센다. 없는 값은 만들지 않는다."""
    rows = list(load_ledger().values())
    by_tenant: dict = {}
    names = {t["id"]: t["name"] for t in tenants()}
    for t_id, name in names.items():
        mine = [r for r in rows if r.get("tenant") == t_id]
        asked = collections.Counter(r["q"] for r in mine if r.get("q"))
        unans = collections.Counter(r["q"] for r in mine if r.get("q") and not r.get("answered"))
        days = collections.Counter((r.get("ts") or "")[:10] for r in mine if r.get("ts"))
        gaps = collections.Counter(f for r in mine for f in (r.get("needs_facts") or []))
        s = (stats or {}).get(t_id) or {}
        by_tenant[t_id] = {
            "name": name,
            "원장에_쌓인_질문": len(mine),
            "서버_집계": {"총_질문": s.get("total"), "답한_것": s.get("answered"),
                        "답변율": s.get("answer_ratio")},
            "많이_물은_것": asked.most_common(15),
            "많이_물었는데_못_답한_것": unans.most_common(15),
            "못_답한_이유_빈칸": gaps.most_common(10),
            "날짜별": sorted(days.items()),
        }
    out = {
        "_about": ("상담봇에 손님이 던진 질문 가공본 — scripts/counsel_questions.py 가 만든다. "
                   "손으로 고치지 않는다(언제든 재생성). 원장 = status/counsel_questions.jsonl"),
        "_caveat": ("전량 통로(GET /log)가 2026-09-11 19:51 에 열려 답한 질문까지 들어온다. "
                    "다만 답 본문(a)은 그 시각 이후 답부터 찍힌다 — 그 전 행은 질문만 있다(소급 불가). "
                    "원장 줄 수가 「서버_집계」보다 클 수 있다: 원장은 지우지 않으므로 서버 로그가 "
                    "회전·정리돼도 남는다."),
        "generated_at": _now(),
        "centers": by_tenant,
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def render(d: dict) -> str:
    lines = ["## 손님이 상담봇에 물은 것 — %s" % d["generated_at"][:16].replace("T", " "), ""]
    lines.append("| 센터 | 원장 | 서버 총계 | 답변율 | 많이 물었는데 못 답한 것 |")
    lines.append("|---|---|---|---|---|")
    for c in d["centers"].values():
        s = c["서버_집계"]
        top = " · ".join("%s(%d)" % (q, n) for q, n in c["많이_물었는데_못_답한_것"][:3]) or "없음"
        ratio = "%.0f%%" % (s["답변율"] * 100) if s.get("답변율") is not None else "—"
        lines.append("| %s | %d줄 | %s건 | %s | %s |"
                     % (c["name"], c["원장에_쌓인_질문"], s.get("총_질문") or "—", ratio, top[:60]))
    return "\n".join(lines)


def _selftest() -> None:
    """서버 없이 도는 자가점검 — 합집합·열쇠·가공이 깨지면 여기서 걸린다."""
    a = {"ts": "2026-09-11T10:00:00", "tenant": "1_wellperion", "q": "주차 되나요"}
    b = {"ts": "2026-09-11T10:00:00", "tenant": "1_wellperion", "q": "주차 되나요", "a": "됩니다"}
    assert key_of(a) == key_of(b), "같은 시각·센터·질문이면 같은 줄이어야 한다"
    c = {"ts": "2026-09-11T10:00:01", "tenant": "1_wellperion", "q": "주차 되나요"}
    assert key_of(a) != key_of(c), "시각이 다르면 다른 줄이다"

    rows = {key_of(a): a}
    rows.setdefault(key_of(b), b)          # 합집합 — 있던 줄을 덮지 않는다
    assert rows[key_of(a)] is a, "먼저 쌓인 줄이 남아야 한다"
    rows.setdefault(key_of(c), c)
    assert len(rows) == 2, rows
    print("[selfcheck] counsel_questions OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="상담봇 질문 수집·가공")
    ap.add_argument("--summary", action="store_true", help="수집 없이 가공만")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return 0
    stats = None if a.summary else collect(a.days)
    print(render(summarize(stats)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
