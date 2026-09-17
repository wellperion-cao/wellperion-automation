# -*- coding: utf-8 -*-
"""파트너 온보딩 질문·답 누적 → ERP 플랫폼관리 파트너사 패널 발행본 + 카톡 질문 통 생성.

왜 있나 — GM 지시 2026-09-15: 「질문 및 답변 내용 자료도 다음 파트너사를 위해서 정립해 놔야 해.
ERP 플랫폼관리 페이지에 데이터 가공 및 누적 신경 써 줘」 + 「html 로 하지 말고 카카오톡 질문에
번호 달아서, 번호로 답 받게」.

정본은 둘뿐이다(약속 L01 · 여기에 값을 복사하지 않는다):
  질문은행  server/counselbot/question_bank.json            — 업체 공통 질문(영역 A~L)
  업체별 답  server/counselbot/tenants/{tenant}_qa.json     — 그 업체에 물은 것·받은 답 누적
             (q_id = 영역-번호 · partner_no = 카톡에서 쓰는 번호 · answer null = 아직 못 받음)

이 스크립트가 만드는 것(발행본 · 언제든 다시 만든다):
  3. 웰페리온 가이드/erp/admin/data/partner_onboarding.json — 플랫폼관리 파트너사 패널이 읽는다
  --kakao {tenant}  → 답 없는 번호를 카톡 한 통 문안으로 찍는다(번호 + 질문 한 줄)

쓰는 법:
  C:/Python314/python.exe scripts/partner_onboarding_publish.py            # 발행본 갱신
  C:/Python314/python.exe scripts/partner_onboarding_publish.py --kakao jo  # 고척 카톡 질문 통
  C:/Python314/python.exe scripts/partner_onboarding_publish.py --self-test
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "server" / "counselbot" / "question_bank.json"
TENANTS = ROOT / "server" / "counselbot" / "tenants"
OUT = ROOT / "3. 웰페리온 가이드" / "erp" / "admin" / "data" / "partner_onboarding.json"

# 플랫폼관리 화면의 파트너 키(식별자 표와 같다) ↔ 상담봇 테넌트 폴더 이름
TENANT_KEYS = {"wellperion": "1_wellperion", "dc": "2_dietcamp", "jo": "3_gocheokgolf"}
TENANT_NAMES = {"wellperion": "1호 웰페리온", "dc": "2호 다이어트캠프", "jo": "3호 고척GDR QA 골프존"}
# 파트너 라인 폴더 — 초안 페이지 3장(소개서·브랜드가이드·운영전략)이 여기 있어야 설문을 보낸다(가이드라인 부록 B 2단계 · GM 2026-09-17).
TENANT_DIRS = {"dc": "dietcamp", "jo": "gocheokgolf"}
DRAFT_PAGES = (("회사소개서", "intro.html"), ("브랜드가이드", "brand.html"), ("운영전략", "strategy.html"))
ADMIN_DIR = ROOT / "3. 웰페리온 가이드" / "erp" / "admin"

def draft_page_lines(key: str) -> list[str]:
    """설문 머리에 붙일 초안 페이지 링크 — 파일이 없으면 링크 대신 경고 한 줄(페이지 먼저 만들라는 관문)."""
    d = TENANT_DIRS.get(key)
    if not d:
        return []
    out, missing = [], []
    for label, fn in DRAFT_PAGES:
        if (ADMIN_DIR / d / fn).exists():
            out.append(f"▪ {label} https://erp.wellperion.com/{d}/{fn}")
        else:
            missing.append(label)
    if missing:
        out.append("[경고] 초안 페이지가 아직 없음: " + " · ".join(missing) + " — 가이드라인 부록 B 2단계(페이지 먼저)를 지키지 않았다")
    return out


def load_json(p: Path):
    return json.loads(io.open(p, encoding="utf-8").read())


def bank_index(bank: dict) -> dict[str, dict]:
    """q_id(영역 첫 글자-번호) → 질문. 은행 순서가 번호다 — 중간에 끼워 넣지 않는다."""
    out, count = {}, {}
    for it in bank["questions"]:
        a = it["area"][0]
        count[a] = count.get(a, 0) + 1
        out[f"{a}-{count[a]}"] = it
    return out


def build(bank: dict, qa_by_key: dict[str, list]) -> dict:
    idx = bank_index(bank)
    tenants = {}
    for key, items in qa_by_key.items():
        rows = []
        for it in items:
            b = idx.get(it.get("q_id", ""), {})
            rows.append({
                "q_id": it.get("q_id"), "partner_no": it.get("partner_no"),
                "area": b.get("area") or it.get("area") or "",
                "q": it.get("q") or b.get("q") or "",
                "known": it.get("known"),            # 우리가 미리 아는 값(확인만 받을 때)
                "answer": it.get("answer"), "answered_on": it.get("answered_on"),
                "asked_on": it.get("asked_on"), "source": it.get("source"),
                "promoted_to": it.get("promoted_to"),
            })
        answered = sum(1 for r in rows if r["answer"])
        tenants[key] = {"name": TENANT_NAMES.get(key, key), "asked": len(rows), "answered": answered,
                        "pending": len(rows) - answered, "rows": rows}
    return {
        "_doc": "발행본 — scripts/partner_onboarding_publish.py 가 질문은행 + tenants/*_qa.json 에서 만든다. 손으로 고치지 않는다.",
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bank_count": len(bank["questions"]),
        "areas": sorted({it["area"] for it in bank["questions"]}),
        "tenants": tenants,
    }


def kakao_text(key: str, qa: list, bank: dict) -> str:
    """답 없는 번호만 — 번호 + 질문 한 줄. 미리 아는 값이 있으면 괄호로 붙여 확인만 받게."""
    idx = bank_index(bank)
    lines = []
    for it in qa:
        if it.get("answer") or not it.get("partner_no"):
            continue
        q = it.get("q") or idx.get(it["q_id"], {}).get("q", "")
        known = it.get("known")
        lines.append(f"{it['partner_no']}. {q}" + (f" (저희가 아는 것: {known})" if known else ""))
    head = draft_page_lines(key)
    if head:
        lines = ["[초안 페이지 — 답이 오는 번호부터 채워집니다]"] + head + lines
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kakao", choices=sorted(TENANT_KEYS), help="이 파트너의 답 없는 번호를 카톡 문안으로")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
        print("partner_onboarding_publish 자가점검 통과")
        return 0
    bank = load_json(BANK)
    qa_by_key = {}
    for key, folder in TENANT_KEYS.items():
        p = TENANTS / f"{folder}_qa.json"
        qa_by_key[key] = load_json(p) if p.exists() else []
    if args.kakao:
        print(kakao_text(args.kakao, qa_by_key[args.kakao], bank))
        return 0
    data = build(bank, qa_by_key)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(data, ensure_ascii=False, indent=1))
    for k, t in data["tenants"].items():
        print(f"{t['name']}: 물은 것 {t['asked']} · 답 {t['answered']} · 남음 {t['pending']}")
    print("→", OUT.relative_to(ROOT))
    return 0


def _self_test() -> None:
    bank = {"questions": [{"area": "A 기본", "q": "주소는?"}, {"area": "A 기본", "q": "시간은?"}, {"area": "B 말투", "q": "한 줄은?"}]}
    idx = bank_index(bank)
    assert list(idx) == ["A-1", "A-2", "B-1"], list(idx)
    qa = [{"q_id": "A-1", "partner_no": 1, "answer": "서울", "answered_on": "2026-09-01"},
          {"q_id": "B-1", "partner_no": 2, "known": "초안"}]
    d = build(bank, {"jo": qa})
    assert d["tenants"]["jo"]["answered"] == 1 and d["tenants"]["jo"]["pending"] == 1
    assert d["tenants"]["jo"]["rows"][1]["q"] == "한 줄은?"
    txt = kakao_text("jo", qa, bank)
    assert txt.splitlines()[-1] == "2. 한 줄은? (저희가 아는 것: 초안)", txt   # 마지막 줄 = 답 없는 번호 하나
    assert txt.startswith("[초안 페이지"), txt                                 # 머리 = 초안 페이지 링크(가이드라인 B-2 관문)
    assert "[경고]" not in txt or not (ADMIN_DIR / "gocheokgolf" / "intro.html").exists(), txt


if __name__ == "__main__":
    sys.exit(main())
