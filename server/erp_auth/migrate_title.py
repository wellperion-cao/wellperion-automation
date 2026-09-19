# -*- coding: utf-8 -*-
"""users.name → name/title 분리 마이그레이션 (배 12848 2단계 · GM 2026-09-19 「이름에는 이름만」).

서버(/srv/erp/auth)에서 실행 — common/db.py 가 ERP_DB_URL(db.env)을 읽는다.
직급 접미사 정본 = ssot/ranks.json 하나(표기 있으면 표기, 없으면 직급명 그대로) — 여기 복제하지 않는다.

사용:
    python3 migrate_title.py            # dry-run — 무엇을 바꿀지만 표로 출력, DB 안 건드림
    python3 migrate_title.py --apply    # 무모호 행만 실제 UPDATE(name, title)
    python3 migrate_title.py --selftest # DB 없이 split_name_title() 자체점검
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db as _db  # noqa: E402

T = _db.TENANT
_RANKS_PATHS = ("/srv/erp/repo/ssot/ranks.json",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "ssot", "ranks.json"))


def _ranks_raw() -> dict:
    for p in _RANKS_PATHS:
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            continue
    return {}


def suffixes() -> list:
    """[(접미사, 정식직급명), ...] 긴 접미사부터 — "AM" 이 "M" 보다 먼저 매칭돼야 한다.
    표기(예: 매니저→M · 어시스트매니저→AM)가 있으면 그 표기를, 없으면 직급명 그대로 접미사로 쓴다."""
    out = []
    for r in (_ranks_raw().get("ranks") or []):
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        m = re.search(r"표기\s*([A-Za-z]+)", str(r.get("note") or ""))
        out.append((m.group(1) if m else name, name))
    seen, uniq = set(), []
    for suf, name in sorted(out, key=lambda x: -len(x[0])):
        if suf not in seen:
            seen.add(suf)
            uniq.append((suf, name))
    return uniq


def split_name_title(raw: str, sufs: list):
    """(새이름, 직함, 모호사유) 반환 — 모호사유가 있으면 손대지 않는다(그대로 두라는 뜻).
    사유도 직함도 없으면(둘 다 None) 접미사 매칭이 없는 것 — 마이그레이션 대상이 아니다."""
    raw = str(raw or "").strip()
    for suf, full in sufs:
        if raw == suf:
            return raw, None, "이름 전체가 직급뿐 — 사람 이름 패턴 아님"
        if raw.endswith(suf):
            prefix = raw[: -len(suf)].rstrip()
            if len(prefix) < 2:
                return raw, None, "떼어내면 이름이 너무 짧아짐(1자 이하)"
            return prefix, full, None
    return raw, None, None


def _selftest():
    sufs = suffixes() or [("AM", "어시스트매니저"), ("GM", "GM"), ("M", "매니저"), ("실장", "실장"), ("소장", "소장")]
    assert split_name_title("나우열M", sufs) == ("나우열", "매니저", None)
    assert split_name_title("이경연실장", sufs) == ("이경연", "실장", None)
    assert split_name_title("이경연 실장", sufs) == ("이경연", "실장", None)
    assert split_name_title("GM", sufs)[1] is None      # 이름 전체가 직급뿐 — 손대지 않음
    assert split_name_title("홍길동", sufs) == ("홍길동", None, None)   # 접미사 없음 — 대상 아님
    n, t, why = split_name_title("김철수AM", sufs)       # AM 을 M 보다 먼저 매칭해야 함
    assert t == "어시스트매니저" and n == "김철수", (n, t, why)
    print("자체점검 통과")


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    apply = "--apply" in sys.argv
    sufs = suffixes()
    if not sufs:
        print("ssot/ranks.json 을 못 읽었습니다 — 접미사 목록이 비었습니다. 중단.")
        return
    with _db.connect() as c:
        rows = c.execute("SELECT id, email, name, title FROM users WHERE tenant_id=%s ORDER BY id", (T,)).fetchall()
    changed, ambiguous = [], []
    for r in rows:
        if r["title"]:
            continue                                   # 이미 title 있음 — 재작업 안 함
        new_name, title, why = split_name_title(r["name"], sufs)
        if why:
            ambiguous.append((r["id"], r["email"], r["name"], why))
        elif title:
            changed.append((r["id"], r["email"], r["name"], new_name, title))
    print(f"분리 대상 {len(changed)}건 · 모호(손 안 댐) {len(ambiguous)}건 · 전체 {len(rows)}행")
    for i, e, old, new, title in changed:
        print(f"  #{i} {e}: '{old}' -> name='{new}' title='{title}'")
    for i, e, old, why in ambiguous:
        print(f"  ! #{i} {e}: '{old}' — {why}")
    if apply:
        if changed:
            with _db.connect() as c:
                for i, e, old, new, title in changed:
                    c.execute("UPDATE users SET name=%s, title=%s WHERE tenant_id=%s AND id=%s", (new, title, T, i))
            print(f"적용 완료 {len(changed)}건")
        else:
            print("적용할 행 없음")
    else:
        print("dry-run — 실제로 바꾸려면 --apply")


if __name__ == "__main__":
    main()
