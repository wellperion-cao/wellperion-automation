# -*- coding: utf-8 -*-
"""relay_routes() 담당자 표 회귀검사.

이 표에 없는 역할의 배는 build_relay_message 가 `clevel not in contacts` 로 통째로
걸러낸다 — 전달문을 채워도 사람 방에 영영 안 나가고, 발송 실패가 아니라 '보낼 게 없음'
으로 보여 아무 경보도 울리지 않는다. 2026-08-10 에 시포가, 2026-08-18 에 시토·시우가
같은 통로로 막혀 있었다. 다시 빠지면 여기서 걸린다.

실행: C:/Python314/python.exe scripts/test_relay_contacts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from send_ops_digest import relay_routes

REQUIRED = ("cpo", "cto", "coo")


def main() -> int:
    room, contacts = relay_routes()[0]
    missing = [r for r in REQUIRED if r not in contacts]
    assert not missing, f"relay 담당자 표에 빠진 역할: {missing} — 그 역할 배는 사람 방에 안 나간다"
    assert all(str(contacts[r]).strip() for r in REQUIRED), "담당자 이름이 빈 역할이 있다"
    print(f"OK — 방 '{room}' · 담당자 {len(contacts)}역할 {sorted(contacts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
