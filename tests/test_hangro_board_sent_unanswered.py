# -*- coding: utf-8 -*-
"""쿵짝 회수(2026-08-04 GM 지시) — hangro_board._sent_unanswered 자체 점검.
「보낸 배가 아직 열려 있으면 뜨고, 답이 와서 닫혔으면 안 뜬다」+「1일 미만은 안 뜬다」."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import hangro_board as HB  # noqa: E402


def _item(owner, status, days_ago, from_role="cto"):
    d = (dt.date.today() - dt.timedelta(days=days_ago)).isoformat()
    return {
        "owner": owner, "status": status, "_from": from_role,
        "enqueued_at": d, "note": "", "_raw_summary": "", "updated_at": "",
        "title": "t", "priority": "NORMAL", "end_date": "",
    }


def test_open_ship_still_unanswered_shows():
    items = [_item("coo", "PENDING", days_ago=3)]
    out = HB._sent_unanswered(items, "cto")
    assert len(out) == 1


def test_closed_ship_does_not_show():
    items = [_item("coo", "DONE", days_ago=3)]
    out = HB._sent_unanswered(items, "cto")
    assert out == []


def test_under_one_day_does_not_show():
    items = [_item("coo", "PENDING", days_ago=0)]
    out = HB._sent_unanswered(items, "cto")
    assert out == []


def test_self_dispatched_excluded():
    items = [_item("cto", "PENDING", days_ago=3)]  # --mine (owner == role)
    out = HB._sent_unanswered(items, "cto")
    assert out == []


def test_other_senders_ships_not_mine():
    items = [_item("coo", "PENDING", days_ago=3, from_role="cmo")]
    out = HB._sent_unanswered(items, "cto")
    assert out == []


def test_sorted_oldest_first():
    items = [_item("coo", "PENDING", days_ago=2), _item("cmo", "PENDING", days_ago=6)]
    out = HB._sent_unanswered(items, "cto")
    assert [it["owner"] for it in out] == ["cmo", "coo"]


if __name__ == "__main__":
    test_open_ship_still_unanswered_shows()
    test_closed_ship_does_not_show()
    test_under_one_day_does_not_show()
    test_self_dispatched_excluded()
    test_other_senders_ships_not_mine()
    test_sorted_oldest_first()
    print("OK — all _sent_unanswered self-checks passed")
