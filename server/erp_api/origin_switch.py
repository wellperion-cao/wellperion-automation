# -*- coding: utf-8 -*-
"""폼·영역별 원본 스위치 — dual(이중기록) ↔ server(서버 원본) (배 960 레인 J · 2026-09-04 시토).

파일 한 줄로 갈린다: /srv/erp/status/origin_switch.json   (저장소 본 = origin_switch.example.json)
  dual    지금까지 그대로 — 서버 원장에 적고 그 자리에서 GAS 로 넘겨 GAS 응답을 화면에 돌려준다.
  server  서버 원장에만 적고 즉시 ok — GAS 왕복을 안 기다리니 화면 응답이 빨라진다. 시트는 pushback.py 가 되민다.
재시작 없음(파일 mtime 이 바뀌면 다음 요청이 새 값을 읽는다) · 되돌리기 = 값을 dual 로 고치면 그 순간부터 종전 동작.
파일이 없거나 깨졌으면 전부 dual — 스위치 사고로 저장이 멈추는 일은 없다.

자체점검: python3 origin_switch.py
"""
import json
import os

DEFAULT = "dual"
PATH = os.environ.get("ERP_ORIGIN_SWITCH", "/srv/erp/status/origin_switch.json")
EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "origin_switch.example.json")

# 로그인 뒤 쓰기(api_write)는 액션이 수십 개라 하나씩 스위치를 두지 않는다 — GAS 목적지로 갈린 다섯 영역이 단위.
#   열쇠 = api_write._gas_key() 가 돌려주는 env 이름. 값 = 스위치 파일에 사람이 적는 이름.
WRITE_AREA = {"RECEPTION_EXEC_URL": "write_reception", "TODO_GAS_URL": "write_todo",
              "CHECK_GAS_URL": "write_check", "SCHEDULE_GAS_URL": "write_schedule",
              "PROC_GAS_URL": "write_proc", "FUNNEL_EXEC_URL": "write_member"}
# 스위치 열쇠 전수 = 공개 접수 폼(api_intake.FORMS) + 위 다섯 영역. example.json 과 같아야 한다(자체점검이 지킨다).
NAMES = ("inquiry", "instructor", "sunday", "reception", "selftest") + tuple(sorted(set(WRITE_AREA.values())))
# server 로 못 바꾸는 폼·영역 (배 960 M2 · 2026-09-04). 스위치 파일에 'server' 라 적혀 있어도 dual 로 돌린다.
#   접수(reception): 서버가 매기는 접수번호는 L260904-101010 인데 접수 GAS 는 RECEPTION-<n> 을 매긴다.
#   손님이 받아 간 번호로 직원이 시트에서 찾지 못한다 — 번호 모양이 같아지기 전에는 전환 대상이 아니다.
NO_SERVER = {"reception": "server 미지원(접수번호 형식 L… vs RECEPTION-n)"}
_cache = {"stamp": None, "map": {}}


def _load():
    try:
        stamp = os.stat(PATH).st_mtime_ns
    except OSError:                       # 파일 없음 = 아직 아무것도 전환 안 함
        _cache["stamp"], _cache["map"] = None, {}
        return _cache["map"]
    if stamp != _cache["stamp"]:
        _cache["stamp"] = stamp           # 깨진 파일을 매 요청 다시 읽지 않는다(고쳐 저장하면 mtime 이 또 바뀐다)
        try:
            with open(PATH, encoding="utf-8") as f:
                data = json.load(f)
            _cache["map"] = {k: v for k, v in data.items() if isinstance(v, str) and not k.startswith("_")}
        except (OSError, ValueError, AttributeError):
            _cache["map"] = {}            # 못 읽으면 전부 dual
    return _cache["map"]


def mode(name):
    """'server' 는 파일에 그대로 적혀 있을 때만. 그 밖(파일 없음·오타·깨짐·모르는 이름)은 전부 dual."""
    if name in NO_SERVER:                 # 전환 자체가 막힌 자리 — 파일에 뭐라 적혀 있든 dual
        return DEFAULT
    m = _load()
    v = m.get(name) or m.get("default") or DEFAULT
    return "server" if v == "server" else DEFAULT


def modes():
    """헬스가 그대로 싣는 표 — 지금 어느 폼·영역이 서버 원본인지."""
    return {n: mode(n) for n in NAMES}


if __name__ == "__main__":   # python3 origin_switch.py — 파일 하나 만들어 갈림·되돌림 확인(DB·서버 없음)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        PATH = os.path.join(d, "origin_switch.json")

        def put(text):
            with open(PATH, "w", encoding="utf-8") as f:
                f.write(text)
            _cache["stamp"] = None        # 같은 밀리초 안에 두 번 쓰는 건 시험뿐 — 실제로는 mtime 이 다르다

        assert mode("inquiry") == "dual"                       # 파일 없음 = 전환 전
        put('{"inquiry": "server"}')
        assert mode("inquiry") == "server" and mode("instructor") == "dual"   # 켠 폼만 갈린다
        put('{"inquiry": "dual"}')
        assert mode("inquiry") == "dual"                       # 되돌리기 = 값 한 줄
        put('{"default": "server", "inquiry": "dual"}')
        assert mode("instructor") == "server" and mode("inquiry") == "dual"   # 개별 값이 default 를 이긴다
        put('{"inquiry": "SERVER"}')
        assert mode("inquiry") == "dual"                       # 오타·대문자는 전환이 아니다
        put("{망가진 파일")
        assert mode("inquiry") == "dual" and modes()["write_todo"] == "dual"  # 깨져도 저장은 멈추지 않는다
        put('{"_메모": "사람이 읽는 줄", "write_todo": "server"}')
        assert mode("write_todo") == "server" and set(modes()) == set(NAMES)
        put('{"reception": "server"}')                         # 배 960 M2 — 접수는 켜도 안 켜진다
        assert mode("reception") == "dual" and set(NO_SERVER) <= set(NAMES)
        put('{"default": "server"}')
        assert mode("reception") == "dual" and mode("inquiry") == "server"

    with open(EXAMPLE, encoding="utf-8") as f:                 # 저장소 본과 열쇠가 어긋나면 사람이 못 켠다
        ex = json.load(f)
    assert set(k for k in ex if not k.startswith("_")) == set(NAMES) | {"default"}, sorted(ex)
    assert all(v == "dual" for k, v in ex.items() if not k.startswith("_")), "본은 전부 dual 이어야 한다"
    print("자체점검 통과")
