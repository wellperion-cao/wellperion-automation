# -*- coding: utf-8 -*-
"""문의 시트 → 서버 PostgreSQL 미러 동기화 (읽기 전용 단방향).

원천은 이미 프로덕션에서 도는 GAS 엔드포인트(scripts/cpo_report.py FUNNEL_EXEC_URL)를
그대로 재사용한다 — 시트 파싱을 새로 포팅하지 않는다(드리프트 0). 시트·GAS 는 절대 쓰지 않는다.

실행: python3 /srv/erp/api/sync_inquiries.py   (cron 5분)
자체점검: python3 sync_inquiries.py --selftest  (같은 DB 의 tenant 'selftest' 로 upsert 로직만 확인, 네트워크 없음)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

# 문의 유입 경로 채우기(배1006 · status/briefs/CMO-유입경로-발행원장-정의서-20260903.md 표 A).
# 측정 시작 규칙(GM 확정) — 이 반영일 이전 문의는 전부 unknown(소급 채움 금지).
CHANNEL_CUTOVER = "2026-09-05"

# GAS 가 돌려주는 channel 값은 출처(멤버십=canonical 10버킷 / 강습=자유텍스트)가 달라 정규식으로 통일 판정한다.
# 표 A 11종 중 이 6개만 문의 channel 텍스트에서 신뢰 가능하게 구분된다 — 나머지(ig_personal/ig_official 등)는
# ponytail: 폼이 아직 UTM만 캡처하고 계정 구분·post_id 는 안 보내 unknown 처리. 폼 개편(정의서 §5, 시모 소유) +
# GAS 가 raw UTM(source/content/campaign)을 member_inquiry_list·lesson_inquiry_list 에 실어 보내면 그때 세분화.
_CHANNEL_CODE_PATTERNS = [
    (re.compile(r"블로그|blog", re.I), "naver_blog"),
    (re.compile(r"카카오|카톡|kakao", re.I), "kakao"),
    (re.compile(r"당근|danggn|daangn", re.I), "danggn"),
    (re.compile(r"동부이촌동|이촌동|카페", re.I), "naver_cafe"),
    (re.compile(r"소개|지인|추천", re.I), "referral"),
    (re.compile(r"간판|현수막|오프라인|워크인|지나가|방문", re.I), "direct_visit"),
    (re.compile(r"네이버|naver|플레이스|검색", re.I), "search"),
]


def channel_code_of(raw_channel, timestamp):
    """channel 자유텍스트 + 제출시각 → channel_code 11종(표 A). 못 맞추거나 반영일 이전이면 unknown."""
    if not timestamp or timestamp < CHANNEL_CUTOVER:
        return "unknown"
    s = str(raw_channel or "")
    for pat, code in _CHANNEL_CODE_PATTERNS:
        if pat.search(s):
            return code
    return "unknown"

ENV_FILE = os.environ.get("ERP_API_ENV", "/srv/erp/api.env")

# (type, GAS action, 추가 파라미터) — 화면들이 쓰는 액션 그대로.
SOURCES = [
    ("멤버십", "member_inquiry_list", None),
    ("성인강습", "lesson_inquiry_list", {"type": "성인강습"}),
    ("유소년강습", "lesson_inquiry_list", {"type": "유소년강습"}),
]

def load_env():
    """/srv/erp/api.env 를 읽어 os.environ 에 채운다(비밀값은 저장소에 두지 않는다)."""
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def gas_get(action, params, timeout=60):
    """GAS GET 1회. 성공 시 dict, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("FUNNEL_EXEC_URL", "")
    if not url:
        raise SystemExit("FUNNEL_EXEC_URL 없음 — %s 를 확인" % ENV_FILE)
    q = {"action": action}
    if params:
        q.update(params)
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "wellperion-erp-api"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("[warn] %s 조회 실패: %s: %s" % (action, type(e).__name__, str(e)[:120]))
        return None
    if not data.get("ok"):
        print("[warn] %s 응답 ok=false" % action)
        return None
    return data


def replace_type(conn, kind, rows, now):
    """한 유형을 통째로 갈아끼운다 — 시트가 정본이라 미러는 원천과 같아야 한다.
    호출부가 '조회 성공 + 행 있음'을 이미 확인한 뒤에만 부른다(빈 값으로 지우지 않기 위해)."""
    recs = []
    for r in rows:
        key = str(r.get("rowKey") or r.get("rowIndex") or "")
        if not key:
            continue
        if db.is_test_payload(r):    # 테스트/더미 문의는 미러에 안 싣는다(AWS DB 더미 전수정리 · 2026-09-05)
            continue
        ts = r.get("timestamp")
        recs.append((
            db.TENANT, "%s|%s" % (kind, key), kind, key,
            r.get("name"), r.get("phone"), r.get("status"), ts,
            json.dumps(r, ensure_ascii=False), now,
            channel_code_of(r.get("channel"), ts), ts or None,
        ))
    with conn:
        conn.execute("DELETE FROM inquiries WHERE tenant_id=%s AND type=%s", (db.TENANT, kind))
        conn.executemany(
            "INSERT INTO inquiries"
            " (tenant_id,id,type,row_key,name,phone,status,timestamp,data,synced_at,channel_code,channel_captured_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id,id) DO UPDATE SET type=EXCLUDED.type, row_key=EXCLUDED.row_key, name=EXCLUDED.name,"
            " phone=EXCLUDED.phone, status=EXCLUDED.status, timestamp=EXCLUDED.timestamp, data=EXCLUDED.data,"
            " synced_at=EXCLUDED.synced_at, channel_code=EXCLUDED.channel_code,"
            " channel_captured_at=EXCLUDED.channel_captured_at", recs)
    return len(recs)


def main():
    load_env()
    conn = db.connect()
    # 서버 시계는 UTC — 저장소·화면이 다 KST 라 여기서 맞춰 적는다(읽는 쪽이 헷갈리지 않게).
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    total, failed = 0, []
    for kind, action, params in SOURCES:
        data = gas_get(action, params)
        rows = (data or {}).get("data")
        if not isinstance(rows, list) or not rows:
            failed.append(kind)  # 실패 — 기존 미러를 그대로 둔다(빈 값으로 덮지 않음)
            continue
        n = replace_type(conn, kind, rows, now)
        total += n
        print("[ok] %s %d건" % (kind, n))
    with conn:
        db.meta_set(conn, "last_sync", now)
        db.meta_set(conn, "last_failed", ",".join(failed))
    conn.close()
    print("[done] %s · 갱신 %d건 · 실패 %s" % (now, total, failed or "없음"))
    return 1 if failed else 0


def selftest():
    assert channel_code_of("카카오톡 채널", "2026-09-05") == "kakao"
    assert channel_code_of("네이버 블로그", "2026-09-10 09:00:00") == "naver_blog"
    assert channel_code_of("카카오톡 채널", "2026-09-04") == "unknown", "반영일 이전은 소급 없이 unknown"
    assert channel_code_of("아무말", "2026-09-05") == "unknown", "매핑 불가는 unknown"
    assert channel_code_of("카카오톡", None) == "unknown", "타임스탬프 없으면 unknown"

    db.TENANT = "selftest"                      # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
    conn = db.connect()
    rows = [{"rowKey": "a", "name": "홍길동", "timestamp": "2026-01-01"},
            {"rowKey": "b", "name": "김철수", "timestamp": "2026-02-01"},
            {"name": "키없음"},
            {"rowKey": "c", "name": "테스트", "phone": "123", "note": "테스트", "timestamp": "2026-01-01"}]
    try:
        assert replace_type(conn, "멤버십", rows, "t0") == 2, "rowKey 없는 행·테스트 더미 행은 버린다"
        assert replace_type(conn, "멤버십", rows[:1], "t1") == 1, "같은 유형은 통째로 교체"
        assert conn.execute("SELECT COUNT(*) FROM inquiries WHERE tenant_id=%s", (db.TENANT,)).fetchone()[0] == 1
        replace_type(conn, "성인강습", rows, "t1")
        assert conn.execute("SELECT COUNT(*) FROM inquiries WHERE tenant_id=%s AND type='멤버십'", (db.TENANT,)).fetchone()[0] == 1, \
            "다른 유형 교체가 남의 유형을 지우면 안 된다"
    finally:
        with conn:
            conn.execute("DELETE FROM inquiries WHERE tenant_id=%s", (db.TENANT,))
        conn.close()
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
