# -*- coding: utf-8 -*-
"""결재 비밀번호(PIN) 서버 검증 — 업무·결재 쓰기 3동작의 구글 의존을 끊는 자리 (2026-09-14 시토).

왜 있나
  todo_sign·todo_opinion·todo_opinion_delete 는 원본 스위치가 server 여도 GAS 로 갔다
  (api_write.NO_SERVER_ACTIONS). 이유 하나뿐: 비밀번호를 GAS 스크립트 속성이 갖고 있어서
  서버가 즉시 ok 를 주면 틀린 비번으로 누른 결재가 1분 동안 승인된 것처럼 보였기 때문이다.
  그 판정을 서버가 하게 되면 그 이유가 사라진다.

규칙은 GAS 를 그대로 잇는다 (.deploy-todo/업무&결재 현황.js todo_sign 2919줄 · todo_opinion 3016줄 ·
todo_opinion_delete 3050줄). 비번 이름도 GAS 속성 이름 그대로 쓴다 — 번역표를 두지 않는다.
  · role 'GM'      → APPROVAL_PIN_GM
  · role '부서장'   → 그 건의 부서장 실명으로 갈린다: 이경연 실장=_OPS · 이정헌 소장=_FAC · 나우열M=_PARTNER
    부서장 이름 판정 순서 = 화면 deptHeadNameOf 와 같다: ①결재요청에 적힌 부서장 ②담당자 ③카테고리 매핑
  · todo_opinion_delete → 역할 무관 APPROVAL_PIN_GM

서버가 그 이름의 행을 갖고 있지 않으면 검증하지 않고 GAS 에 맡긴다(defer). 그래서
  · PIN 을 하나도 안 넣은 지금 = 종전과 완전히 같게 동작한다(켜는 스위치가 따로 없다)
  · PIN 을 넣는 순간 그 역할부터 서버가 판정한다
서버가 갖고 있는데 값이 다르면 그 자리에서 거부한다 — GAS 와 같은 문구라 화면은 안 고친다.
※ 서버 값이 GAS 속성과 어긋나면 맞는 비번이 거부된다. 조용히 통과시키는 쪽보다 낫다(사람이 바로 안다).
   그래서 등록은 GAS 속성에 적힌 값과 같은 값으로 한다 — 이 파일이 값을 읽어 오지는 않는다.

평문 저장 금지: sha256(salt + pin) 만 남긴다. 등록은 서버 안에서 이 파일을 직접 돌린다.
    python3 /srv/erp/api/approval_pin.py --set --name APPROVAL_PIN_GM
    (비번은 stdin 으로 받는다 — 명령줄·셸 히스토리·프로세스 목록·로그 어디에도 안 남는다)
자체점검: python3 approval_pin.py --selftest   (DB 없이 판정 규칙만)
"""
import hashlib
import json
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import db  # noqa: E402

# 이 세 동작만 PIN 관문 뒤에 있다(GAS 와 같다). api_write 가 이 목록으로 갈라 부른다.
ACTIONS = ("todo_sign", "todo_opinion", "todo_opinion_delete")

# 부서장 실명 → 비번 이름. GAS _MID_PIN 과 같은 표다.
DEPT_PIN = {"이경연 실장": "APPROVAL_PIN_OPS", "이정헌 소장": "APPROVAL_PIN_FAC", "나우열M": "APPROVAL_PIN_PARTNER"}
# 카테고리 → 부서장. GAS _deptHeadFor·화면 CAT_DEPT_HEAD 와 같은 4줄.
CAT_DEPT_HEAD = {"[2] 인사": "나우열M", "[3] 파트너팀": "나우열M",
                 "[4] 운영 정책": "이경연 실장", "[5] 시설 및 환경": "이정헌 소장"}

DEFER = "defer"     # 서버가 그 비번을 모른다 — 종전대로 GAS 가 판정한다
GM_NAME = "APPROVAL_PIN_GM"


def _s(v):
    return str(v if v is not None else "").strip()


def dept_head_of(record):
    """이 건의 부서장 실명 — 화면 deptHeadNameOf·GAS todo_sign 과 같은 순서(결재요청 → 담당자 → 카테고리)."""
    for field in ("결재요청", "담당자"):
        for name in [x.strip() for x in _s(record.get(field)).split(",")]:
            if name in DEPT_PIN:
                return name
    return CAT_DEPT_HEAD.get(_s(record.get("카테고리")), "")


def pin_name(action, payload, record):
    """이 요청이 대조해야 할 비번 이름. 없으면 ''(대조할 비번이 없는 요청 — GAS 도 그냥 통과시킨다)."""
    if action == "todo_opinion_delete":
        return GM_NAME                       # GAS 3050줄 — 역할 없이 GM 비번 하나
    role = _s(payload.get("role"))
    if role == "GM":
        return GM_NAME
    if role == "부서장":
        return DEPT_PIN.get(dept_head_of(record), "")
    return ""                                # 그 밖의 역할은 GAS 도 비번을 안 본다


def hash_pin(salt, pin):
    return hashlib.sha256((salt + _s(pin)).encode("utf-8")).hexdigest()


def load(conn, name):
    """(salt, pin_hash) 또는 None. 이름 행이 없으면 None — 부른 쪽은 그때 GAS 에 맡긴다."""
    r = conn.execute("SELECT salt, pin_hash FROM approval_pins WHERE tenant_id=%s AND name=%s",
                     (db.TENANT, name)).fetchone()
    return (r["salt"], r["pin_hash"]) if r else None


def mirror_record(conn, item_id):
    """거울(todo_items)의 그 업무 행 — 부서장 판정에 결재요청·담당자·카테고리가 필요하다. 없으면 None."""
    if not _s(item_id):
        return None
    r = conn.execute("SELECT data FROM todo_items WHERE tenant_id=%s AND id=%s",
                     (db.TENANT, _s(item_id))).fetchone()
    if not r:
        return None
    try:
        return json.loads(r["data"])
    except (TypeError, ValueError):
        return None


def judge(name, stored, submitted):
    """대조 결과 — None=통과 · DEFER=서버가 모른다 · dict=거부 응답(GAS 문구 그대로).

    stored = load() 결과. 판정만 하는 순수 함수라 DB 없이 자체점검한다."""
    if not name or stored is None:
        return DEFER
    salt, want = stored
    if hash_pin(salt, submitted) != want:
        # GAS 와 같은 문구·같은 칸(pinKey) — 화면 alert 문구가 안 바뀐다. 실제 비번 값은 안 싣는다.
        return {"ok": False, "error": "비밀번호가 일치하지 않습니다.", "pinKey": name, "noRetry": True}
    return None


def check(conn, action, payload):
    """api_write 가 부르는 자리. None=서버가 맡는다 · DEFER=GAS 에 맡긴다 · dict=즉시 거부."""
    record = mirror_record(conn, payload.get("id"))
    if record is None and action != "todo_opinion_delete":
        return DEFER          # 거울에 그 행이 없으면 부서장을 못 가린다 — 지어내지 않고 GAS 에 맡긴다
    name = pin_name(action, payload, record or {})
    return judge(name, load(conn, name) if name else None, payload.get("pin"))


def set_pin(conn, name, pin):
    """CLI 전용 — 평문은 여기서 해시가 되고 그대로 버려진다."""
    salt = secrets.token_hex(16)
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 9 * 3600))
    with conn:
        conn.execute(
            "INSERT INTO approval_pins (tenant_id,name,salt,pin_hash,updated_at) VALUES (%s,%s,%s,%s,%s)"
            " ON CONFLICT (tenant_id,name) DO UPDATE SET salt=EXCLUDED.salt, pin_hash=EXCLUDED.pin_hash,"
            " updated_at=EXCLUDED.updated_at", (db.TENANT, name, salt, hash_pin(salt, pin), now))
    return now


def selftest():
    # 부서장 판정 — 결재요청이 담당자·카테고리를 이긴다(GAS 2929줄 · 화면 deptHeadNameOf 와 같은 순서)
    assert dept_head_of({"결재요청": "이정헌 소장", "담당자": "나우열M", "카테고리": "[4] 운영 정책"}) == "이정헌 소장"
    assert dept_head_of({"담당자": "백승화 사원,나우열M", "카테고리": "[4] 운영 정책"}) == "나우열M"
    assert dept_head_of({"담당자": "백승화 사원", "카테고리": "[5] 시설 및 환경"}) == "이정헌 소장"
    assert dept_head_of({"담당자": "백승화 사원", "카테고리": "[1] 매출 및 영업"}) == ""   # 매핑 없는 카테고리

    assert pin_name("todo_sign", {"role": "GM"}, {}) == GM_NAME
    assert pin_name("todo_sign", {"role": "부서장"}, {"카테고리": "[2] 인사"}) == "APPROVAL_PIN_PARTNER"
    assert pin_name("todo_sign", {"role": "부서장"}, {"카테고리": "[9] 회의"}) == ""      # 부서장 없음 = 대조 안 함
    assert pin_name("todo_opinion_delete", {}, {}) == GM_NAME                           # 역할 무관 GM 비번
    assert pin_name("todo_sign", {"role": "대표님"}, {}) == ""

    salt = "abcd"
    stored = (salt, hash_pin(salt, "1234"))
    assert judge(GM_NAME, stored, "1234") is None                  # 맞으면 통과
    assert judge(GM_NAME, stored, " 1234 ") is None                # 앞뒤 공백은 GAS 와 같이 무시
    bad = judge(GM_NAME, stored, "9999")
    assert bad["ok"] is False and bad["pinKey"] == GM_NAME and "일치하지" in bad["error"], bad
    assert "1234" not in json.dumps(bad, ensure_ascii=False)       # 거부 응답에 비번이 새지 않는다
    assert judge(GM_NAME, None, "1234") == DEFER                   # 서버가 모르는 비번 = GAS 에 맡긴다
    assert judge("", None, "1234") == DEFER                        # 대조할 비번이 없는 요청도 GAS 에 맡긴다
    # 같은 비번이라도 salt 가 다르면 해시가 다르다(원장이 새도 다른 곳에 그대로 못 쓴다)
    assert hash_pin("s1", "1234") != hash_pin("s2", "1234")
    print("selftest ok")


def _main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--set" not in argv:
        print(__doc__.strip().splitlines()[-4].strip())
        return 2
    try:
        name = argv[argv.index("--name") + 1]
    except (ValueError, IndexError):
        print("--name 이 필요합니다 (%s)" % " · ".join([GM_NAME] + sorted(set(DEPT_PIN.values()))))
        return 2
    if name not in ([GM_NAME] + list(DEPT_PIN.values())):
        print("모르는 비번 이름: %s" % name)
        return 2
    pin = sys.stdin.readline().strip() if not sys.stdin.isatty() else __import__("getpass").getpass("PIN: ")
    if not pin:
        print("빈 비번은 등록하지 않습니다")
        return 2
    at = set_pin(db.connect(), name, pin)
    print("%s 등록됨 (%s) — 값은 저장하지 않았습니다(해시만)." % (name, at))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]) or 0)
