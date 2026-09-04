# -*- coding: utf-8 -*-
"""계정 권한 파일 자가점검 — account_perms.json 의 모듈 id 가 실제 화면 목록과 맞나(배951).

  C:/Python314/python.exe server/erp_auth/account_perms_check.py

id 가 하나라도 어긋나면 그 화면은 조용히 열린다(deny 목록에서 빠지므로). 화면을 더하거나 이름을
바꾼 뒤 이 검사를 돌린다. accounts 가 비어 있으면 종전 동작이므로 통과시킨다.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PERMS = os.path.join(ROOT, "server", "erp_auth", "account_perms.json")
MODULES = os.path.join(ROOT, "3. 웰페리온 가이드", "erp", "modules.json")


def check(perms_file: str = PERMS, modules_file: str = MODULES) -> list:
    ids = {m["id"] for m in json.load(open(modules_file, encoding="utf-8"))["modules"]}
    accounts = json.load(open(perms_file, encoding="utf-8")).get("accounts") or {}
    bad = []
    for email, p in accounts.items():
        if not p.get("all") and not p.get("modules") and not p.get("groups"):
            bad.append(f"{email}: 아무것도 허용하지 않는다 — 이 계정은 화면을 못 연다")
        for key in ("modules", "deny"):
            for i in p.get(key, []):
                if i not in ids:
                    bad.append(f"{email}.{key}: 없는 id '{i}'")
    return bad


def main() -> int:
    bad = check()
    ids = {m["id"] for m in json.load(open(MODULES, encoding="utf-8"))["modules"]}
    accounts = json.load(open(PERMS, encoding="utf-8")).get("accounts") or {}
    for email, p in sorted(accounts.items()):
        n = len(ids) - len(set(p.get("deny", []))) if p.get("all") else len(set(p.get("modules", [])))
        print(f"  {email:26} 허용 {n}/{len(ids)}")
    for b in bad:
        print("  X", b)
    print("전체 화면", len(ids), "· 계정", len(accounts), "·", "이상 없음" if not bad else f"어긋남 {len(bad)}건")
    return 1 if bad else 0


def demo() -> None:
    """logic 자가점검 — 없는 id 를 넣으면 잡아내는가."""
    import tempfile
    ids = {"a", "b"}
    with tempfile.TemporaryDirectory() as d:
        mf, pf = os.path.join(d, "m.json"), os.path.join(d, "p.json")
        json.dump({"modules": [{"id": i} for i in ids]}, open(mf, "w", encoding="utf-8"))
        json.dump({"accounts": {"x@y.com": {"all": True, "deny": ["a", "없는것"]},
                                "z@y.com": {"modules": ["b"]},
                                "w@y.com": {}}}, open(pf, "w", encoding="utf-8"), ensure_ascii=False)
        bad = check(pf, mf)
    assert any("없는것" in b for b in bad), bad
    assert any("w@y.com" in b for b in bad), bad
    assert not any("z@y.com" in b for b in bad), bad
    assert len(bad) == 2, bad
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        sys.exit(main())
