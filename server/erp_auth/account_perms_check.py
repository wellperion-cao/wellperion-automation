# -*- coding: utf-8 -*-
"""계정 권한 파일 자가점검 — account_perms.json 의 모듈 id 가 실제 화면 목록과 맞나(배951).

  C:/Python314/python.exe server/erp_auth/account_perms_check.py

id 가 하나라도 어긋나면 그 화면은 조용히 열린다(deny 목록에서 빠지므로). 화면을 더하거나 이름을
바꾼 뒤 이 검사를 돌린다. accounts 가 비어 있으면 종전 동작이므로 통과시킨다.
"""
import json
import os
import re
import sys

# location.replace('membership.html?manage=lesson') · <meta http-equiv=refresh url=…>
REDIRECT_RE = re.compile(r"""location\.replace\(\s*['"]([^'"]+)|url=([^'">\s]+)""")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PERMS = os.path.join(ROOT, "server", "erp_auth", "account_perms.json")
MODULES = os.path.join(ROOT, "3. 웰페리온 가이드", "erp", "modules.json")


def _redirect_pairs(modules: list) -> list:
    """화면 A 가 화면 B 로 넘기면 (A id, B id, B 이름). 넘어간 화면이 다른 모듈이면 권한도 따라가야 한다.

    2026-09-07 실사고: 강습 계정에 'cpo-member-lesson'(lesson.html)만 줬는데 그 화면이
    membership.html(모듈 'member')로 넘어가 「권한 없음」이 떴다. 사람이 열어 보기 전에 여기서 잡는다."""
    by_path, pairs = {}, []
    for m in modules:
        p = os.path.normpath(os.path.join(os.path.dirname(MODULES), m.get("path", "")))
        by_path[p] = m
    for m in modules:
        src = os.path.normpath(os.path.join(os.path.dirname(MODULES), m.get("path", "")))
        if not os.path.isfile(src):
            continue
        with open(src, encoding="utf-8", errors="ignore") as f:
            head = f.read(6000)
        hit = REDIRECT_RE.search(head)
        if not hit:
            continue
        target = (hit.group(1) or hit.group(2) or "").split("?")[0].split("#")[0]
        if not target or target.startswith(("http", "//", "mailto:")):
            continue
        tgt = os.path.normpath(os.path.join(os.path.dirname(src), target))
        dest = by_path.get(tgt)
        if dest and dest["id"] != m["id"]:
            pairs.append((m["id"], dest["id"], dest.get("name", "")))
    return pairs


def check(perms_file: str = PERMS, modules_file: str = MODULES) -> tuple:
    """(막아야 할 것, 알리기만 할 것). 앞쪽이 하나라도 있으면 배포를 멈춘다."""
    mods = json.load(open(modules_file, encoding="utf-8"))["modules"]
    ids = {m["id"] for m in mods}
    accounts = json.load(open(perms_file, encoding="utf-8")).get("accounts") or {}
    bad, soft = [], []
    for email, p in accounts.items():
        if not p.get("all") and not p.get("modules") and not p.get("groups"):
            bad.append(f"{email}: 아무것도 허용하지 않는다 — 이 계정은 화면을 못 연다")
        for i in p.get("modules", []):
            if i not in ids:
                bad.append(f"{email}.modules: 없는 id '{i}'")
        # deny 에 없는 id 가 남은 것은 못 여는 쪽이라 사고가 아니다 — 그 화면이 등록에서 빠졌을 뿐이다.
        # 그래서 배포를 막지 않고 알리기만 한다(2026-09-11: 없어진 cbo 문서 3개가 배포를 통째로 막았다).
        # 줄은 지우지 않는다 — 그 화면이 다시 등록되면 이 deny 가 그대로 살아야 한다.
        for i in p.get("deny", []):
            if i not in ids:
                soft.append(f"{email}.deny: 등록에 없는 id '{i}' — 막는 쪽이라 그대로 둔다")
    for src_id, dest_id, dest_name in _redirect_pairs(mods):
        for email, p in accounts.items():
            allow, deny = p.get("modules", []), p.get("deny", [])
            if src_id in allow and dest_id not in allow:
                bad.append(f"{email}: '{src_id}' 를 열면 '{dest_id}'({dest_name}) 로 넘어가는데 그건 안 열린다 — 권한 없음이 뜬다")
            elif p.get("all") and dest_id in deny and src_id not in deny:
                bad.append(f"{email}: '{src_id}' 를 열면 막아 둔 '{dest_id}'({dest_name}) 로 넘어간다")
    return bad, soft


def main() -> int:
    bad, soft = check()
    ids = {m["id"] for m in json.load(open(MODULES, encoding="utf-8"))["modules"]}
    accounts = json.load(open(PERMS, encoding="utf-8")).get("accounts") or {}
    for email, p in sorted(accounts.items()):
        n = len(ids) - len(set(p.get("deny", []))) if p.get("all") else len(set(p.get("modules", [])))
        print(f"  {email:26} 허용 {n}/{len(ids)}")
    for w in soft:
        print("  -", w)
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
        bad, soft = check(pf, mf)
    assert any("없는것" in w for w in soft), soft          # deny 쪽 유령은 알리기만
    assert not any("없는것" in b for b in bad), bad        # 배포를 막지 않는다
    assert any("w@y.com" in b for b in bad), bad
    assert not any("z@y.com" in b for b in bad), bad
    assert len(bad) == 1, bad

    # 넘어가는 화면(리다이렉트) 짝 — 2026-09-07 강습 계정 실사고 재현
    with tempfile.TemporaryDirectory() as d:
        erp = os.path.join(d, "erp")
        os.makedirs(os.path.join(erp, "cpo"))
        with open(os.path.join(erp, "cpo", "lesson.html"), "w", encoding="utf-8") as f:
            f.write("<script>location.replace('membership.html?manage=lesson');</script>")
        with open(os.path.join(erp, "cpo", "membership.html"), "w", encoding="utf-8") as f:
            f.write("<h1>회원</h1>")
        mf, pf = os.path.join(erp, "m.json"), os.path.join(d, "p.json")
        json.dump({"modules": [{"id": "lesson", "name": "강습", "path": "cpo/lesson.html"},
                               {"id": "member", "name": "회원", "path": "cpo/membership.html"}]},
                  open(mf, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump({"accounts": {"les@y.com": {"modules": ["lesson"]},
                                "ok@y.com": {"modules": ["lesson", "member"]}}},
                  open(pf, "w", encoding="utf-8"), ensure_ascii=False)
        global MODULES
        MODULES, saved = mf, MODULES
        try:
            bad, _ = check(pf, mf)
        finally:
            MODULES = saved
    assert any("les@y.com" in b and "member" in b for b in bad), bad
    assert not any("ok@y.com" in b for b in bad), bad
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        sys.exit(main())
