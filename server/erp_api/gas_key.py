# -*- coding: utf-8 -*-
"""접수 GAS 접근 게이트 열쇠 붙이기 (배 960 치명수리 · 2026-09-04 시토).

접수 GAS(RECEPTION_EXEC_URL)에는 PII 를 내주는 GATED 액션이 있다(reg_list·lf_list·reg_delete·
lf_delete·reg_renumber·hold_complete·voc_list·voc_update …). GAS 쪽 스위치 ScriptProperties
TOKEN_ENFORCE=1 이 켜지면 그 액션들은 `key` 파라미터(=ACCESS_TOKEN)가 있어야 통과한다.
공개 액션(reg_submit·reg_board·reg_dashboard·lf_gallery·diag …)은 스위치와 무관하게 그대로다.

여기서는 api.env 의 RECEPTION_TOKEN 을 접수 GAS 호출에만 붙인다.
★ 값이 비어 있으면 아무것도 하지 않는다 — 스위치를 켜기 전에 배포해도 동작 무변경(회귀 0).
되돌리기 = api.env 에서 RECEPTION_TOKEN 한 줄 지우고 재시작(또는 GAS TOKEN_ENFORCE=0).

회원 GAS(FUNNEL_EXEC_URL) 키 배선(배 12818 · 2026-09-18) — member_active_list 등 5종이 GAS 쪽
ACCESS_TOKEN 자체가 없어 키 유무와 무관하게 무인증 공개돼 있던 것의 1단계 수리. api.env 의
FUNNEL_ACCESS_TOKEN 을 GET 질의(sign_params)에만 붙인다 — 값 없으면 무동작(회귀 0). POST 쓰기
(sign_body·BODY_KEYS)는 이번 건과 무관 — 그대로 둔다.
"""
import json
import os

RECEPTION_URL_KEY = "RECEPTION_EXEC_URL"
# POST 본문에 얹을 열쇠 — {GAS 환경변수 열쇠: (열쇠 값이 든 환경변수, 본문 칸 이름)}.
#   접수 GAS = key(RECEPTION_TOKEN · GATED 액션 통과용)
#   업무 GAS = srvkey(TODO_WRITE_SECRET · 배 960 M4). GAS 쪽 Script Property SERVER_WRITE_SECRET 이 켜지면
#     todo_*·approval_rep_* 쓰기는 이 값이 있어야 통과한다. 서버 api.env 에 값을 넣기 전까지는 본문 무변경.
BODY_KEYS = {RECEPTION_URL_KEY: ("RECEPTION_TOKEN", "key"),
             "TODO_GAS_URL": ("TODO_WRITE_SECRET", "srvkey")}

# 배 12781(2026-09-18 GM 지시) — 리셉션 업무·라커관리 쓰기 비밀번호(adminPassword)는 위 BODY_KEYS 와 달리
# env 가 아니라 partner_secrets(tenant=wellperion) 에 있다(화면 입력 대신 서버가 채운다). 모양이 달라
# 별도 표로 두고 sign_body() 안에서 따로 처리한다.
ADMIN_SECRET_CHANNELS = {"RCOPS_GAS_URL": "reception-admin", "LOCKER_GAS_URL": "locker-admin"}


# GET 질의에 얹을 열쇠 — {GAS url_key: 열쇠 값이 든 환경변수}. 표에 없는 GAS 에는 절대 안 붙는다.
#   접수 GAS = RECEPTION_TOKEN(GATED 액션 통과용)
#   회원 GAS = FUNNEL_ACCESS_TOKEN(배 12818 · member_active_list 등 5종 무인증 PII 노출 수리 1단계 —
#     키 배선만, GAS 쪽 게이트는 아직 안 켰다. 값 없으면 무동작·회귀 0)
PARAM_KEYS = {RECEPTION_URL_KEY: "RECEPTION_TOKEN", "FUNNEL_EXEC_URL": "FUNNEL_ACCESS_TOKEN"}


def key_for(url_key):
    """PARAM_KEYS 표에 있는 GAS 로 갈 때만 열쇠를 준다. 표에 없는 GAS(업무·점검…)에는 절대 안 붙는다."""
    env = PARAM_KEYS.get(url_key, "")
    return os.environ.get(env, "").strip() if env else ""


def sign_params(url_key, params):
    """GET 질의(dict)에 key 를 얹은 새 dict. 열쇠 없으면 원본 그대로."""
    k = key_for(url_key)
    if not k or (params or {}).get("key"):
        return params
    q = dict(params or {})
    q["key"] = k
    return q


def sign_body(url_key, body):
    """POST 본문(bytes JSON)에 그 GAS 의 열쇠 칸을 얹는다(BODY_KEYS) + 리셉션·라커 쓰기 비밀번호를 채운다
    (ADMIN_SECRET_CHANNELS · 배 12781). 열쇠·비밀번호 없음·JSON 아님·이미 있음 = 그 칸은 원본 그대로.

    ★열쇠는 GAS 로 나가는 본문에만 붙는다 — 원장(write_log·intake_log)은 이 함수를 거치기 전 본문을 적으므로
      비밀값이 DB 에 남지 않는다. 값이 비어 있으면 아무것도 하지 않으니 스위치를 켜기 전 배포해도 회귀 0."""
    env, field = BODY_KEYS.get(url_key, ("", ""))
    k = os.environ.get(env, "").strip() if env else ""
    if k:
        try:
            d = json.loads(body.decode("utf-8"))
        except Exception:
            d = None
        if isinstance(d, dict) and not d.get(field):
            d[field] = k
            body = json.dumps(d, ensure_ascii=False).encode("utf-8")
    admin_channel = ADMIN_SECRET_CHANNELS.get(url_key)
    if admin_channel:
        try:
            d = json.loads(body.decode("utf-8"))
        except Exception:
            return body
        if isinstance(d, dict) and not d.get("adminPassword"):
            import api_partner_secrets   # 이 자리에서만 쓰므로 최상단 대신 여기서
            pw = api_partner_secrets.secret_pw("wellperion", admin_channel)
            if pw:
                d["adminPassword"] = pw
                body = json.dumps(d, ensure_ascii=False).encode("utf-8")
    return body


if __name__ == "__main__":
    os.environ.pop("RECEPTION_TOKEN", None)
    assert key_for(RECEPTION_URL_KEY) == ""
    assert sign_params(RECEPTION_URL_KEY, {"action": "lf_list"}) == {"action": "lf_list"}
    body = json.dumps({"action": "reg_delete", "id": "RECEPTION-1"}).encode("utf-8")
    assert sign_body(RECEPTION_URL_KEY, body) == body            # 토큰 없으면 무변경

    os.environ["RECEPTION_TOKEN"] = "s3cret"
    assert key_for(RECEPTION_URL_KEY) == "s3cret"
    assert key_for("FUNNEL_EXEC_URL") == ""                       # FUNNEL_ACCESS_TOKEN 아직 없음
    assert sign_params(RECEPTION_URL_KEY, {"action": "lf_list"})["key"] == "s3cret"
    assert sign_params("TODO_GAS_URL", {"action": "todo_list"}) == {"action": "todo_list"}
    assert json.loads(sign_body(RECEPTION_URL_KEY, body).decode("utf-8"))["key"] == "s3cret"

    # 회원 GAS(FUNNEL_EXEC_URL) GET 키 배선(배 12818) — 비었을 때 무동작 · 있을 때 부착 ·
    # RECEPTION 값과 안 섞임(바이트 단위로 그대로) · POST 서명(BODY_KEYS)은 이번 건과 무관.
    assert sign_params("FUNNEL_EXEC_URL", {"action": "member_active_list"}) == {"action": "member_active_list"}
    os.environ["FUNNEL_ACCESS_TOKEN"] = "f-s3cret"
    assert key_for("FUNNEL_EXEC_URL") == "f-s3cret"
    assert sign_params("FUNNEL_EXEC_URL", {"action": "member_active_list"})["key"] == "f-s3cret"
    assert sign_params(RECEPTION_URL_KEY, {"action": "lf_list"})["key"] == "s3cret"   # 서로 안 샌다
    assert sign_body("FUNNEL_EXEC_URL", body) == body   # POST 서명은 무변경(BODY_KEYS 에 없음)
    os.environ.pop("FUNNEL_ACCESS_TOKEN", None)
    assert key_for("FUNNEL_EXEC_URL") == ""
    assert sign_body("FUNNEL_EXEC_URL", body) == body
    assert sign_body(RECEPTION_URL_KEY, b"not json") == b"not json"

    # 업무 GAS 무인증 쓰기 게이트(배 960 M4) — 서버가 srvkey 를 넣어야 게이트를 켠 날 13종이 안 막힌다.
    todo = json.dumps({"action": "todo_add", "업무명": "시험"}, ensure_ascii=False).encode("utf-8")
    os.environ.pop("TODO_WRITE_SECRET", None)
    assert sign_body("TODO_GAS_URL", todo) == todo                # 값 없으면 본문 무변경(게이트 미배포 상태)
    os.environ["TODO_WRITE_SECRET"] = "t0d0"
    assert json.loads(sign_body("TODO_GAS_URL", todo).decode("utf-8"))["srvkey"] == "t0d0"
    assert "srvkey" not in json.loads(sign_body(RECEPTION_URL_KEY, body).decode("utf-8"))   # 남의 GAS 로 새면 안 된다
    assert sign_body("CHECK_GAS_URL", todo) == todo               # 표에 없는 GAS 는 그대로

    # 배 12781 — 리셉션·라커 쓰기 비밀번호는 partner_secrets 에서(가짜값 Xample1234! · 실값 금지)
    import api_partner_secrets
    _orig = api_partner_secrets.secret_pw
    api_partner_secrets.secret_pw = lambda tenant, channel: "Xample1234!" if (tenant, channel) == ("wellperion", "reception-admin") else ""
    try:
        rc = json.dumps({"action": "update", "tab": "키관리"}, ensure_ascii=False).encode("utf-8")
        assert json.loads(sign_body("RCOPS_GAS_URL", rc).decode("utf-8"))["adminPassword"] == "Xample1234!"
        rc2 = json.dumps({"action": "update", "tab": "키관리", "adminPassword": "화면이보낸값"}, ensure_ascii=False).encode("utf-8")
        assert sign_body("RCOPS_GAS_URL", rc2) == rc2                                    # 이미 있으면 안 건드림
        lk = json.dumps({"action": "update", "db": "men"}, ensure_ascii=False).encode("utf-8")
        assert "adminPassword" not in json.loads(sign_body("LOCKER_GAS_URL", lk).decode("utf-8"))  # 저장소에 없으면 무변경
    finally:
        api_partner_secrets.secret_pw = _orig
    print("gas_key 자체점검 OK")
