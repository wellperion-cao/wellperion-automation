# -*- coding: utf-8 -*-
"""전사일정 다리(배577) 자체점검 — 거르는 규칙이 실제로 거르는지 한 번에 확인한다.

네트워크를 타지 않는다: 판정 함수(_schedule_is_dup)와 후보 거르기(bridge_to_schedule 의
조회 전 구간)만 본다. 조회 이후는 GAS 응답이 필요해 여기서 다루지 않는다.

실행: C:/Python314/python.exe scripts/test_schedule_bridge.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ops_daily_digest as d  # noqa: E402


def test_dup():
    items = [
        {"name": "승강기 정기검사", "next_due": "2026-08-20"},
        {"name": "오넛티 납품", "next_due": "2026-08-25", "source": "kakao_digest"},
    ]
    # 같은 날짜·같은 이름 = 중복
    assert d._schedule_is_dup("승강기 정기검사", "2026-08-20", items)
    # 띄어쓰기·기호만 다른 것도 중복(정규화)
    assert d._schedule_is_dup("승강기  정기 검사", "2026-08-20", items)
    # 한쪽이 다른 쪽을 품어도 중복
    assert d._schedule_is_dup("승강기 정기검사 입회", "2026-08-20", items)
    # 날짜가 다르면 중복 아님 — 같은 이름이어도 다른 일이다
    assert not d._schedule_is_dup("승강기 정기검사", "2026-09-20", items)
    # 아예 다른 일은 중복 아님
    assert not d._schedule_is_dup("소방 점검", "2026-08-20", items)
    print("  ok  중복 판정")


def test_filter():
    """조회 전에 걸러져야 하는 것들 — 전부 걸러지면 GAS 를 부르지도 않고 빈 목록이 나온다."""
    past = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    bad = [
        {"date": past, "title": "지난 미팅"},          # 지난 날짜
        {"date": "다음 주 목요일", "title": "교육"},    # 날짜 형식 아님
        {"date": "2026-09-01", "title": ""},           # 이름 빈칸
        "문자열",                                       # dict 아님
    ]
    assert d.bridge_to_schedule(bad, "2026-08-14", "★운영부", dry_run=True) == []
    assert d.bridge_to_schedule([], "2026-08-14", "★운영부", dry_run=True) == []
    print("  ok  후보 거르기(지난날짜·형식오류·빈이름·잡값)")


def test_cap():
    """하루 상한을 넘으면 전부 건너뛴다 — 판독이 헛짚은 날 달력을 어지럽히지 않는다."""
    fut = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    many = [{"date": fut, "title": f"일정{i}"} for i in range(d._SCHEDULE_MAX_PER_RUN + 1)]
    assert d.bridge_to_schedule(many, "2026-08-14", "★운영부", dry_run=True) == []
    print(f"  ok  하루 상한 {d._SCHEDULE_MAX_PER_RUN}건 초과 시 전량 보류")


def test_reply():
    added = [{"next_due": "2026-08-20", "name": "승강기 정기검사", "dept": "시설부"}]
    line = d._schedule_reply_lines(added)
    assert "전사일정에 넣었습니다" in line
    assert "8/20(목)" in line and "승강기 정기검사" in line and "시설부" in line
    assert d._schedule_reply_lines([]) == ""
    print("  ok  방 회신 한 줄")


def test_parse():
    raw = ('{"message":"안녕","issues":[],'
           '"schedules":[{"date":"2026-08-20","title":"승강기 정기검사","dept":"시설부"}]}')
    msg, issues, scheds, ok = d.parse_brain_json(raw)
    assert ok and msg == "안녕" and issues == [] and len(scheds) == 1
    # schedules 가 없는 옛 응답도 그대로 돈다(회귀 0)
    msg2, _, scheds2, ok2 = d.parse_brain_json('{"message":"안녕","issues":[]}')
    assert ok2 and scheds2 == []
    # 파싱 실패도 4개를 돌려준다
    assert len(d.parse_brain_json("그냥 글")) == 4
    print("  ok  응답 파싱(schedules 유무·파싱실패)")


if __name__ == "__main__":
    print("전사일정 다리 자체점검")
    test_dup()
    test_filter()
    test_cap()
    test_reply()
    test_parse()
    print("전부 통과")
