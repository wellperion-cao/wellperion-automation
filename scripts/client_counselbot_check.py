# -*- coding: utf-8 -*-
"""고객 사실 정본(client.json)과 상담봇 정본(tenants/*.json)이 어긋났는지 본다.

왜 있나 — 2026-09-10 (GM 지시: 받은 정보를 가공해 상담봇으로 쓰게 해 달라).
업체에서 받은 값은 두 곳에 산다. 사람이 읽는 쪽은 브랜드 폴더 client.json,
상담봇이 읽는 쪽은 server/counselbot/tenants/{id}.json 이다. 회신이 한 곳에만
들어가면 상담봇은 옛 값을 손님에게 말한다. 자동으로 덮어쓰지 않고 어긋난 칸만 알린다
— 두 파일은 칸 구조가 달라서(시간·시설은 쪼개져 있다) 기계가 옮기면 오히려 틀린다.

쓰는 법:
  C:/Python314/python.exe scripts/client_counselbot_check.py            # 등록된 업체 전부
  C:/Python314/python.exe scripts/client_counselbot_check.py 3_gocheokgolf
  C:/Python314/python.exe scripts/client_counselbot_check.py --self-test

어긋난 칸이 있으면 종료코드 1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# client.json 이 있는 업체만. 새 업체는 여기 한 줄 추가한다.
CLIENTS = {
    "3_gocheokgolf": "2. 브랜드_자료/11_고척골프_조재오부장님/client.json",
}

# (보이는 이름, client.json facts_confirmed 키, 상담봇 프로필에서 꺼내는 길)
FIELDS = [
    ("주소", "address", ("facts", "address")),
    ("전화", "phone", ("facts", "phone")),
    ("주차", "parking", ("facts", "parking")),
    ("규모", "scale", ("facts", "capacity")),
    ("평일·주말 시간", "hours", ("facts", "hours", "weekday")),
    ("인스타그램", "instagram", ("channels", "instagram")),
]


def dig(d: dict, path: tuple[str, ...]):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def check(tenant_id: str, client_path: str) -> list[str]:
    """어긋난 칸을 사람이 읽는 한 줄씩 돌려준다. 빈 목록이면 일치."""
    client = json.loads((ROOT / client_path).read_text(encoding="utf-8"))
    bot = json.loads(
        (ROOT / "server/counselbot/tenants" / f"{tenant_id}.json").read_text(encoding="utf-8")
    )
    facts = client.get("facts_confirmed", {})
    out = []
    for label, ckey, bpath in FIELDS:
        cval = facts.get(ckey)
        bval = dig(bot, bpath)
        if cval is None or bval is None:
            continue  # 한쪽이 미수령이면 어긋남이 아니다
        if str(bval) not in str(cval) and str(cval) not in str(bval):
            out.append(f"  · {label} — 고객 정본「{cval}」 vs 상담봇「{bval}」")
    return out


def self_test() -> None:
    same = {"facts_confirmed": {"phone": "02-1", "address": "가 나 다"}}
    bot_ok = {"facts": {"phone": "02-1", "address": "가 나 다"}}
    bot_bad = {"facts": {"phone": "02-9", "address": "가 나 다"}}
    assert dig(bot_ok, ("facts", "phone")) == "02-1"
    assert dig(bot_ok, ("facts", "없음", "더")) is None
    # 부분 포함은 일치로 본다(상담봇 쪽이 더 짧게 적혀 있는 칸이 있다)
    assert "02-1" in "02-1 (대표)"
    del same, bot_ok, bot_bad
    print("자체 검사 통과")


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--self-test"]
    if "--self-test" in sys.argv[1:]:
        self_test()
        return 0
    targets = args or list(CLIENTS)
    bad = 0
    for tid in targets:
        if tid not in CLIENTS:
            print(f"[{tid}] client.json 이 등록돼 있지 않다 — CLIENTS 에 한 줄 추가하라")
            bad += 1
            continue
        diffs = check(tid, CLIENTS[tid])
        if diffs:
            bad += 1
            print(f"[{tid}] 어긋난 칸 {len(diffs)}개")
            print("\n".join(diffs))
        else:
            print(f"[{tid}] 일치")
    if bad:
        print("\n고친 뒤 다시 돌린다 — 손님에게 나가는 값은 상담봇 쪽이다.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
