# -*- coding: utf-8 -*-
"""웰페리온 ERP 서버 DB 접속 — 코드 전체에서 DB 를 여는 단 하나의 자리 (장기 결정 2·3 · 2026-09-03).

connect()  ERP_DB_URL(postgresql://erp:***@127.0.0.1/erp) 로 PostgreSQL 에 붙는다. 환경변수가 없으면
           /srv/erp/db.env 한 줄을 읽고, 그래도 없으면 명확한 오류. SQLite 폴백 없음.
TENANT     모든 표의 tenant_id 값. 지금은 'wellperion' 하나(배101 SaaS 전환 때 요청별로 바뀐다).
Conn       sqlite3.Connection 흉내 — execute()/executemany()/with(커밋·롤백)/close(). 호출부 diff 를 줄이려는 얇은 껍데기.
           행은 DictRow(r["col"]·r[0]·keys() 다 된다). 자리표시자는 %s.
init_schema(conn)  schema.sql 적용(멱등). meta_set(conn,k,v)  sync_meta upsert.

RDS 로 옮길 때 = db.env 의 ERP_DB_URL 한 줄만 바꾼다. 파이썬 3.9.
"""
import os
import re

import psycopg2
import psycopg2.extras

Error = psycopg2.Error
IntegrityError = psycopg2.IntegrityError
TENANT = "wellperion"
ENV_FILE = os.environ.get("ERP_DB_ENV", "/srv/erp/db.env")
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# 테스트/더미 페이로드 판별 (AWS DB 더미 전수정리 · 배 984 · 2026-09-05 시토 — GM 지시).
# ★값 전체가 테스트 자체선언이거나 연락처가 명백한 더미일 때만 잡는다 — "테스트"란 낱말은 체험·시험 상담
#   메모(예: "테스트 후 결정", "페어링 테스트")에 실제 회원 기록으로도 정상 등장해서, 낱말 하나만으로 걸면
#   진짜 상담 기록을 오탐 삭제한다(2026-09-05 감사 실사례). 자체선언 태그([테스트]·[자동QA]류)와
#   더미 연락처(010-0000-0000·전부 0·자릿수 미달)만 마커로 본다.
_TEST_TAG_RE = re.compile(r"\[테스트\]|\[자동qa\]|\[자동검증\]|테스트입니다|테스트\s*중\s*입니다", re.I)
_TEST_PHONE_RE = re.compile(r"^0?10-?0000-?0000$|^0{10,11}$|^\d{1,4}$")
_TEST_EXACT_VALUES = {"테스트", "test", "더미", "dummy", "샘플"}
_TEST_TEXT_KEYS = ("name", "title", "content", "note", "memo", "reporter", "itemDesc", "ownerName",
                   "요청자", "물품", "handler", "round", "shift", "submitter", "reason", "보류사유")
_NAME_KEYS = ("name", "reporter", "ownerName")     # 실명이 있으면 더미 전화 하나만으로는 안 잡는다(외국인·워크인 실고객 실사례)
_TEST_PHONE_KEYS = ("phone", "contact", "hp")


def is_test_payload(payload):
    """쓰기 관문(/api/write · /api/intake/*)에 실린 payload 나 GAS 미러 동기화 행이 테스트/더미인지 판별.
    True 면 호출부가 저장은 하되 GAS 전달·미러 동기화·알림·집계에서 뺀다(재유입 차단).
    ★더미 연락처(010-0000-0000 등)만으로는 안 잡는다 — 실명이 있으면 그 전화도 실고객일 수 있다
    (2026-09-05 감사: 외국인 실문의가 010-0000-0000 을 플레이스홀더로 씀). 자체선언 태그가 최우선,
    이름 없이 더미 전화만 있을 때만 보조로 잡는다."""
    if not isinstance(payload, dict):
        return False
    has_name = False
    for key in _TEST_TEXT_KEYS:
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            vv = v.strip()
            if vv.lower() in _TEST_EXACT_VALUES or _TEST_TAG_RE.search(vv):
                return True
            if key in _NAME_KEYS:
                has_name = True
    if has_name:
        return False
    for key in _TEST_PHONE_KEYS:
        v = payload.get(key)
        if isinstance(v, str) and _TEST_PHONE_RE.match(v.replace(" ", "")):
            return True
    return False


def _url():
    url = os.environ.get("ERP_DB_URL")
    if not url:
        try:
            with open(ENV_FILE, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("ERP_DB_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    if not url:
        raise RuntimeError("ERP_DB_URL 없음 — 환경변수 또는 %s 를 확인" % ENV_FILE)
    return url


class Conn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, args=()):
        cur = self.raw.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(sql, args)
        return cur

    def executemany(self, sql, seq):
        with self.raw.cursor() as cur:
            cur.executemany(sql, seq)

    def __enter__(self):
        return self

    def __exit__(self, *exc):          # 정상 종료 = 커밋 · 예외 = 롤백 · 연결은 유지(sqlite 와 같은 뜻)
        return self.raw.__exit__(*exc)

    def close(self):
        self.raw.close()


def connect(readonly=False):
    raw = psycopg2.connect(_url())
    if readonly:                        # 읽기 전용 API 는 미러를 못 건드리게 세션에 못을 박는다
        raw.set_session(readonly=True)
    return Conn(raw)


def init_schema(conn):
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        with conn:
            conn.execute(f.read())


def meta_set(conn, k, v):
    conn.execute("INSERT INTO sync_meta (tenant_id, k, v) VALUES (%s, %s, %s)"
                 " ON CONFLICT (tenant_id, k) DO UPDATE SET v = EXCLUDED.v", (TENANT, k, v))


def meta_get(conn, k):
    r = conn.execute("SELECT v FROM sync_meta WHERE tenant_id=%s AND k=%s", (TENANT, k)).fetchone()
    return r[0] if r else None


if __name__ == "__main__":   # python3 db.py — is_test_payload 자체점검(DB 없이 · 2026-09-05 AWS 감사)
    assert is_test_payload({"name": "테스트", "phone": "123", "note": "테스트"})            # 자체선언 더미
    assert is_test_payload({"content": "테스트 중 입니다.", "name": "최**"})
    assert is_test_payload({"itemDesc": "테스트입니다 체조장 문 앞에서 습득"})
    assert is_test_payload({"title": "[테스트] 배960 쓰기관문 왕복"})
    assert is_test_payload({"phone": "010-0000-0000", "staff": "", "action": "member_archive_restore"})  # 이름 없음
    assert not is_test_payload({"name": "Sina.Melchin@gmx.de", "phone": "010-0000-0000"})  # 실고객 플레이스홀더 전화
    assert not is_test_payload({"content": "롤러괄사를 사용했는데...", "name": "이정숙"})   # 실제 컴플레인
    assert not is_test_payload({"itemDesc": "토끼 당근 손수건", "staff": "진수아"})
    assert not is_test_payload({"title": "브로제이 단말기 설치 및 테스트", "owner": "나우열M"})  # 실제 업무(설비 테스트)
    assert not is_test_payload({"memo": "테스트진행", "content": "불편하다"})               # 실제 컴플레인+내부메모
    assert not is_test_payload("not-a-dict")
    print("자체점검 통과")
