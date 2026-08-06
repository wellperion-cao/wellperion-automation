# -*- coding: utf-8 -*-
"""쿵짝의 받는 쪽 짝(2026-08-06 배397) — hangro_board._received_unanswered 자체 점검.
「남이 나에게 띄운 배가 아직 열려 있으면 뜨고, 내가 보낸 배·AI 내부 배는 안 뜬다」."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import hangro_board as HB  # noqa: E402


def _item(owner, status, days_ago, from_role="ceo", audience=""):
    d = (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()
    return {
        "owner": owner, "status": status, "_from": from_role, "audience": audience,
        "enqueued_at": d, "note": "", "_raw_summary": "", "updated_at": "",
        "title": "t", "priority": "NORMAL", "end_date": "",
    }


def test_open_received_ship_shows():
    items = [_item("cto", "PENDING", days_ago=3)]
    out = HB._received_unanswered(items, "cto")
    assert len(out) == 1


def test_closed_ship_does_not_show():
    items = [_item("cto", "DONE", days_ago=3)]
    assert HB._received_unanswered(items, "cto") == []


def test_under_one_day_does_not_show():
    items = [_item("cto", "PENDING", days_ago=0)]
    assert HB._received_unanswered(items, "cto") == []


def test_self_sent_excluded():
    items = [_item("cto", "PENDING", days_ago=3, from_role="cto")]  # 내가 나에게 띄운 배
    assert HB._received_unanswered(items, "cto") == []


def test_other_owners_ships_not_mine():
    items = [_item("coo", "PENDING", days_ago=3, from_role="ceo")]
    assert HB._received_unanswered(items, "cto") == []


def test_ai_internal_ships_excluded():
    items = [_item("cto", "PENDING", days_ago=3, audience="ai")]  # 자율현황行, G1 제외
    assert HB._received_unanswered(items, "cto") == []


def test_sorted_oldest_first():
    items = [_item("cto", "PENDING", days_ago=2), _item("cto", "PENDING", days_ago=6, from_role="cpo")]
    out = HB._received_unanswered(items, "cto")
    assert [it["_from"] for it in out] == ["cpo", "ceo"]


if __name__ == "__main__":
    test_open_received_ship_shows()
    test_closed_ship_does_not_show()
    test_under_one_day_does_not_show()
    test_self_sent_excluded()
    test_other_owners_ships_not_mine()
    test_ai_internal_ships_excluded()
    test_sorted_oldest_first()
    print("OK — all _received_unanswered self-checks passed")
