# -*- coding: utf-8 -*-
"""업체 FAQ 를 한 곳에서 재는 통합층 — 유형별 커버리지·빈칸·새 유형 후보.

왜 있나 — GM 지시 2026-09-10: 「시보의 역할은 각 센터 FAQ 를 채워서 그 FAQ 를 가공 및
통합시키는 역할까지. FAQ 를 통해서 마케팅 자동화 + 상담봇 + AX 에 활용할 수 있어야 한다.」

무엇을 하나
    업체마다 따로 쌓이는 FAQ(각 센터의 사실)를 공통 질문 유형 원장
    (server/counselbot/shared/question_types.json · 20유형)에 붙여 세 가지를 낸다.
      ① 커버리지 — 유형별로 몇 개 센터가 답을 갖고 있나. 전 센터가 비어 있는 유형이 상품의 구멍이다
      ② 빈칸 — 센터별로 답이 없는 유형. 그 센터에 물어볼 것이 되고 아침 질문 1통으로 나간다
      ③ 새 유형 후보 — 기존 20유형에 안 붙는 FAQ. 두 센터 이상에서 같은 것이 나오면 유형을 하나 늘린다

    쓰는 곳 셋 — 상담봇(빈칸이 곧 미답 원인) · 마케팅 자동화(커버리지 높은 유형이 콘텐츠 주제) ·
    센터 AX 제안(구멍이 그 센터에 팔 것).

새 원장을 만들지 않는다 (약속 L21)
    읽기 = tenants/*.json(프로필) + 각 프로필 faq_file(센터 FAQ) + shared/question_types.json
    쓰기 = status/faq_hub.json 한 장(재기록·언제든 재생성). 유형 추가는 사람이 판단해서 원장에 직접.

쓰는 법
  C:/Python314/python.exe scripts/faq_hub.py                 # 표로 출력
  C:/Python314/python.exe scripts/faq_hub.py --json          # 기계용
  C:/Python314/python.exe scripts/faq_hub.py --save          # status/faq_hub.json 갱신
  C:/Python314/python.exe scripts/faq_hub.py --tenant 3_gocheokgolf   # 한 센터만
  C:/Python314/python.exe scripts/faq_hub.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TENANT_DIR = ROOT / "server/counselbot/tenants"
TYPES = ROOT / "server/counselbot/shared/question_types.json"
OUT = ROOT / "status/faq_hub.json"

_WORD = re.compile(r"[가-힣A-Za-z]{2,}")
# 어느 질문에나 붙어 매칭을 망치는 말 — 세지 않는다
STOP = {"있어요", "되나요", "인가요", "어떻게", "얼마나", "무엇", "있나요", "하나요",
        "가능", "문의", "안내", "알려", "주세요", "괜찮", "해요", "그냥", "뭐가",
        # 시간·정도 부사는 어느 질문에나 붙는다. 유형의 뜻은 뒤에 오는 명사가 갖는다
        "오늘", "지금", "내일", "이번", "저도", "혹시", "정도", "그럼", "제가"}


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text or "") if w not in STOP}


def stem_set(text: str) -> set[str]:
    """어미가 달라도 붙게 앞 두 글자까지 함께 넣는다(운영시간/운영하나요 → '운영')."""
    out = set()
    for w in words(text):
        out.add(w)
        if len(w) > 2:
            out.add(w[:2])
    return out


def faq_of(profile: dict) -> tuple[list[dict], str]:
    """그 센터의 FAQ 목록과 읽은 경로. faq_file 칸에 설명이 붙어 있어도 앞쪽 경로만 쓴다."""
    raw = (profile.get("faq_file") or "").strip()
    if not raw:
        return [], ""
    path = raw.split(" (")[0].split(" · ")[0].strip()
    p = ROOT / path
    if not p.exists():
        return [], path
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return [], path
    return (d.get("faq") or []), path


def match_type(item: dict, types: list[dict]) -> str | None:
    """FAQ 한 문항이 어느 공통 유형에 붙나. 안 붙으면 None(= 새 유형 후보)."""
    bag = stem_set(item.get("q", "")) | {w for a in (item.get("alt") or []) for w in stem_set(a)}
    best, best_hits = None, 0
    for t in types:
        hits = 0
        for ex in t.get("examples") or []:
            hits += len(bag & stem_set(ex))
        if hits > best_hits:
            best, best_hits = t["type_id"], hits
    # 겹치는 낱말 하나로 붙인다 — 흔한 말(STOP)을 빼고 남은 낱말은 그 유형의 뜻을 담는다.
    # 임계 2로 두면 '운영시간이 어떻게 되나요' 처럼 핵심어가 하나뿐인 질문이 전부 새 유형 후보로 빠졌다.
    return best if best_hits >= 1 else None


def build(only: str = "") -> dict:
    types = json.loads(TYPES.read_text(encoding="utf-8"))["types"]
    type_ids = [t["type_id"] for t in types]
    centers: dict[str, dict] = {}
    for p in sorted(TENANT_DIR.glob("*.json")):
        if p.stem.endswith("_qa") or p.stem.endswith("_faq_seed"):
            continue
        if only and p.stem != only:
            continue
        prof = json.loads(p.read_text(encoding="utf-8"))
        faq, path = faq_of(prof)
        covered, unmatched = {}, []
        for item in faq:
            tid = match_type(item, types)
            if tid:
                covered.setdefault(tid, []).append(item.get("id") or item.get("q", "")[:20])
            else:
                unmatched.append(item.get("q", "")[:40])
        centers[p.stem] = {
            "name": (prof.get("tenant") or {}).get("name") or p.stem,
            "faq_path": path,
            "faq_count": len(faq),
            "covered": covered,
            "missing": [t for t in type_ids if t not in covered],
            "unmatched": unmatched,
        }
    coverage = {
        t: sorted(c for c, v in centers.items() if t in v["covered"]) for t in type_ids
    }
    holes = [t for t, cs in coverage.items() if not cs]
    return {
        "_about": "업체 FAQ 통합 계량 — scripts/faq_hub.py 가 만든다. 손으로 고치지 않는다(언제든 재생성).",
        "centers": centers,
        "coverage": coverage,
        "holes": holes,
        "type_count": len(type_ids),
    }


def render(d: dict) -> str:
    lines = [f"## FAQ 통합 — 공통 유형 {d['type_count']}개 · 센터 {len(d['centers'])}곳", ""]
    lines.append("| 센터 | FAQ | 덮은 유형 | 빈 유형 | 유형에 안 붙는 문항 |")
    lines.append("|---|---|---|---|---|")
    for cid, c in d["centers"].items():
        lines.append(f"| {c['name']} | {c['faq_count']}문 | {len(c['covered'])}개 "
                     f"| {len(c['missing'])}개 | {len(c['unmatched'])}개 |")
    lines.append("")
    if d["holes"]:
        lines.append(f"**전 센터가 비어 있는 유형 {len(d['holes'])}개** — 상품의 구멍이다:")
        lines.append("  " + " · ".join(d["holes"]))
    else:
        lines.append("전 센터가 비어 있는 유형은 없다.")
    lines.append("")
    for cid, c in d["centers"].items():
        if c["missing"]:
            lines.append(f"▪ {c['name']} 에 물어볼 것 {len(c['missing'])}개 — "
                         + " · ".join(c["missing"][:8])
                         + (" …" if len(c["missing"]) > 8 else ""))
    return "\n".join(lines)


def self_test() -> None:
    types = json.loads(TYPES.read_text(encoding="utf-8"))["types"]
    assert match_type({"q": "주차 되나요", "alt": ["주차장"]}, types) == "parking"
    assert match_type({"q": "운영시간이 어떻게 되나요", "alt": ["영업시간", "몇시"]}, types) == "hours_today"
    assert match_type({"q": "오늘 날씨 어때요"}, types) is None      # 안 붙는 것은 None
    assert "주차" in stem_set("주차 되나요")
    assert "되나요" not in words("주차 되나요")                       # 흔한 말은 안 센다
    d = build()
    assert d["centers"], "센터가 하나도 안 잡혔다"
    print("자체 검사 통과 — 센터", len(d["centers"]), "곳")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--tenant", default="")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
        return 0
    d = build(a.tenant)
    if a.save:
        OUT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {OUT.relative_to(ROOT)}")
    print(json.dumps(d, ensure_ascii=False, indent=2) if a.json else render(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
