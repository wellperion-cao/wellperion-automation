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


# GAS 재시도 (2026-09-10 시토) — 모든 미러 동기화가 이 한 자리를 거친다.
#   ★왜: GAS /exec 는 멀쩡한 요청에도 가끔 404·읽기 타임아웃·302 무한리다이렉트를 돌려준다.
#     서버 로그 실측(2026-09-10): 404 906회 · 타임아웃 434회 · 302 루프 21회. 한 번만 시도하면
#     그 회차가 통째로 '조회 실패'가 되어, 회원 미러 경보가 5분마다 켜졌다 꺼졌다 하고(오늘 08:00
#     ended·corp, 08:35 archive) 사람은 진짜 고장과 잡음을 구별하지 못한다.
#   ★원천(구글)을 못 고치니 부르는 쪽이 견딘다. 단 값을 지어내지는 않는다 — 세 번 다 실패하면
#     여전히 None 이고, 호출부는 옛 미러를 그대로 둔다.
#   ★인증 거절(401·403)은 다시 걸어도 같으므로 즉시 포기한다 — 진짜 고장을 재시도로 덮지 않는다.
GAS_TRIES = 3
GAS_BACKOFF_SEC = (2, 5)          # 1차 실패 뒤 2초, 2차 실패 뒤 5초
GAS_NO_RETRY_CODES = (400, 401, 403)


def gas_fetch(url, query, timeout=60, label="", require_ok=True):
    """GAS /exec 한 번 읽기 — 일시 실패는 다시 시도한다. 성공 dict, 끝내 실패 None."""
    full = url + "?" + urllib.parse.urlencode(query)
    for attempt in range(1, GAS_TRIES + 1):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "wellperion-erp-api"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            if not isinstance(data, dict) or (require_ok and not data.get("ok")):
                why = "응답 ok=false"
            else:
                if attempt > 1:
                    print("[ok] %s — %d번째 시도에 성공(앞선 실패는 일시 오류)" % (label, attempt))
                return data
        except Exception as e:
            code = getattr(e, "code", None)
            why = "%s: %s" % (type(e).__name__, str(e)[:120])
            if code in GAS_NO_RETRY_CODES:
                print("[warn] %s 조회 실패(재시도 안 함): %s" % (label, why))
                return None
        if attempt < GAS_TRIES:
            time.sleep(GAS_BACKOFF_SEC[attempt - 1])
    print("[warn] %s 조회 실패 — %d번 다 실패: %s" % (label, GAS_TRIES, why))
    return None


def gas_get(action, params, timeout=60):
    """GAS GET. 성공 시 dict, 실패 시 None(지어내지 않는다)."""
    url = os.environ.get("FUNNEL_EXEC_URL", "")
    if not url:
        raise SystemExit("FUNNEL_EXEC_URL 없음 — %s 를 확인" % ENV_FILE)
    q = {"action": action}
    if params:
        q.update(params)
    return gas_fetch(url, q, timeout=timeout, label=action)


def replace_type(conn, kind, rows, now):
    """한 유형을 upsert 로 갈아끼운다 — 시트가 정본이라 미러는 원천과 같아야 한다.
    호출부가 '조회 성공 + 행 있음'을 이미 확인한 뒤에만 부른다(빈 값으로 지우지 않기 위해).
    [2026-09-05 시토 · 배1039-A] 통째 DELETE→INSERT 를 diff 삭제(이 배치에 없는 id 만) + upsert 로 바꿨다.
    서버가 문의 원장에 직접 쓰는 순간 그 행의 id 가 이번 GAS 배치에도 있으면 그대로 살아남는다."""
    recs = []
    for r in rows:
        key = str(r.get("rowKey") or r.get("rowIndex") or "")
        if not key:
            continue
        if db.is_test_payload(r):    # 테스트/더미 문의는 미러에 안 싣는다(AWS DB 더미 전수정리 · 2026-09-05)
            continue
        ts = r.get("timestamp")
        code = channel_code_of(r.get("channel"), ts)
        recs.append((
            db.TENANT, "%s|%s" % (kind, key), kind, key,
            r.get("name"), r.get("phone"), r.get("status"), ts,
            json.dumps(r, ensure_ascii=False), now,
            # channel_captured_at = 유입경로를 '포착한' 시각(now) — 문의 제출 시각(ts)이 아니다(검수 L5).
            # unknown 행은 애초에 못 잡았으니 채우지 않는다.
            code, now if code != "unknown" else None,
        ))
    ids = [r[1] for r in recs]
    with conn:
        if ids:
            conn.execute("DELETE FROM inquiries WHERE tenant_id=%s AND type=%s AND id <> ALL(%s)", (db.TENANT, kind, ids))
        else:
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


def _gas_fetch_selftest():
    """재시도 규칙 자체점검 — 네트워크 없이 urlopen 만 갈아끼워 확인한다."""
    import urllib.error
    real_open, real_sleep = urllib.request.urlopen, time.sleep
    calls = {"n": 0}

    class _Fake:                       # urlopen 의 컨텍스트 매니저 흉내
        def __init__(self, payload): self._p = payload
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self._p).encode("utf-8")

    def _run(sequence):
        calls["n"] = 0
        def fake(req, timeout=None):
            i = calls["n"]; calls["n"] += 1
            item = sequence[min(i, len(sequence) - 1)]
            if isinstance(item, Exception):
                raise item
            return _Fake(item)
        urllib.request.urlopen = fake
        return gas_fetch("https://x/exec", {"action": "t"}, label="selftest")

    try:
        time.sleep = lambda *_: None   # 자체점검은 기다리지 않는다
        e404 = urllib.error.HTTPError("https://x/exec", 404, "Not Found", {}, None)
        assert _run([e404, {"ok": True, "v": 1}])["v"] == 1, "일시 404 는 다시 시도해 살려낸다"
        assert calls["n"] == 2, "성공하면 남은 시도는 쓰지 않는다"
        assert _run([e404]) is None, "세 번 다 실패하면 값을 지어내지 않고 None"
        assert calls["n"] == GAS_TRIES
        e403 = urllib.error.HTTPError("https://x/exec", 403, "Forbidden", {}, None)
        assert _run([e403]) is None and calls["n"] == 1, "인증 거절은 재시도로 덮지 않는다"
        assert _run([{"ok": False}]) is None, "ok=false 도 실패로 본다"
    finally:
        urllib.request.urlopen, time.sleep = real_open, real_sleep


def selftest():
    assert channel_code_of("카카오톡 채널", "2026-09-05") == "kakao"
    assert channel_code_of("네이버 블로그", "2026-09-10 09:00:00") == "naver_blog"
    assert channel_code_of("카카오톡 채널", "2026-09-04") == "unknown", "반영일 이전은 소급 없이 unknown"
    assert channel_code_of("아무말", "2026-09-05") == "unknown", "매핑 불가는 unknown"
    assert channel_code_of("카카오톡", None) == "unknown", "타임스탬프 없으면 unknown"

    _gas_fetch_selftest()

    db.TENANT = "selftest"                    # 같은 DB · 다른 tenant — 실데이터는 한 줄도 안 건드린다
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
