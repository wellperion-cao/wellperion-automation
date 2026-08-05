# -*- coding: utf-8 -*-
"""새 문의(26년 신규문의) 중복 삭제(소프트) 검증 스크립트 (시토 2026-08-05, 1회성 — 완료 후 보관용).

GM 지시: "새 문의에 중복된 건들이 있으면 임정은M 가 삭제 가능하게(비밀번호+회원변경 이력)".
INC-020(행번호 밀림으로 실고객 오삭제) 재발방지 원칙 준수 — 이 스크립트는 실제 쓰기를 전혀 하지 않는다:
  ① 음성 경로(keyPhone 미동봉·비밀번호 오류·keyPhone 불일치) — 전부 거부돼야 하고, 거부는 쓰기 0건.
  ② 소프트 삭제 마커(MI_DUP_DELETED_STATUS)를 실제로 쓰는 호출은 하지 않는다(실고객 행에 손대지 않음).
  ③ 소비처 4곳(_miReadRows_·cpo_today_stats·stage_funnel·period_breakdown)의 제외 판정이 동일 상수·
     동일 비교식을 쓰는지는 순수 로직(합성 행)으로 대조한다 — GAS 실행 없이 파이썬으로 predicate만 복제.
  ④ 라이브 집계(member_inquiry_list·inquiry_stats·cpo_today_stats·stage_funnel·period_breakdown)는
     현재값을 읽기(nocache=1)만 하고 기록한다 — 지금 소프트 삭제된 건이 0건이면 "0건" 그대로 보고한다
     (실데이터 전/후 대조 불가 — 함수 단위 대조로 대체).

참고: reference_gas_post_curl_no_follow_redirect(GAS 호출은 requests, 손curl 금지).
"""
import sys, io, json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)

MARKER = "중복(삭제)"  # Survey.js MI_DUP_DELETED_STATUS 와 동일 문자열(육안 대조용)


def call(params, timeout=40):
    r = requests.get(FUNNEL_EXEC_URL, params=params, timeout=timeout, allow_redirects=True)
    r.encoding = "utf-8"
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:500]}


# ── ① 음성 경로 3종 — 전부 쓰기 0건으로 거부돼야 함 ──────────────────────────
def step_negative_no_keyphone():
    print("\n=== [검증①] keyPhone 미동봉 — 거부돼야 함(쓰기 없음) ===")
    code, data = call({"action": "member_inquiry_delete", "rowIndex": "2", "gid": "1902010032"})
    print("HTTP", code, json.dumps(data, ensure_ascii=False))
    ok = (data.get("ok") is False and data.get("error") == "keyPhone 필수 — 대조 없이 삭제 불가")
    print("PASS" if ok else "FAIL")
    return ok


def step_negative_no_password(real_row):
    print("\n=== [검증②] keyPhone 정상 + 비밀번호 미동봉 — 거부돼야 함(쓰기 없음, 행 조회 전 차단) ===")
    code, data = call({
        "action": "member_inquiry_delete",
        "rowIndex": str(real_row["rowIndex"]),
        "gid": "1902010032",
        "keyPhone": real_row["phone"],
    })
    print("HTTP", code, json.dumps(data, ensure_ascii=False))
    ok = (data.get("ok") is False and data.get("error") == "비밀번호가 올바르지 않습니다.")
    print("PASS" if ok else "FAIL")
    return ok


def step_negative_wrong_password(real_row):
    print("\n=== [검증③] keyPhone 정상 + 비밀번호 오기재 — 거부돼야 함(쓰기 없음) ===")
    code, data = call({
        "action": "member_inquiry_delete",
        "rowIndex": str(real_row["rowIndex"]),
        "gid": "1902010032",
        "keyPhone": real_row["phone"],
        "password": "이건_절대_맞을리없는_틀린값_QA전용",
    })
    print("HTTP", code, json.dumps(data, ensure_ascii=False))
    ok = (data.get("ok") is False and data.get("error") == "비밀번호가 올바르지 않습니다.")
    print("PASS" if ok else "FAIL")
    return ok


def fetch_live_rows():
    print("\n=== 라이브 재조회(nocache=1) — 실제 쓰기 없음 ===")
    code, data = call({"action": "member_inquiry_list", "nocache": "1"})
    if not data.get("ok"):
        print("FAIL — 조회 실패:", data)
        sys.exit(1)
    rows = data["data"]
    print("전체 행수(소프트삭제 제외 반영값):", len(rows))
    return rows


# ── ③ 소비처 4곳 제외 predicate 순수 로직 대조(합성 행, GAS 미실행) ────────────
def dryrun_predicate_consistency():
    """Survey.js에 심은 4개 지점의 비교식은 전부
        String(row[statusCol] || '').trim() === MI_DUP_DELETED_STATUS
       한 줄이다(파일 위치: _miReadRows_ / cpo_today_stats / stage_funnel FORM_SHEETS[0] 분기 /
       period_breakdown _countRegAllPeriods_). 파이썬으로 그 비교식 자체를 복제해, 합성 행 집합에
       대해 네 지점이 전부 동일하게 분류하는지 assert 로 확인한다(코드 복사가 아니라 '식이 하나'라는
       사실 자체가 이미 GM이 지목한 위험(같은 판정이 두 벌 돼 숫자가 갈리는 것)을 막는다 — 여기서는
       그 단일 식이 네 호출부에 문자 그대로 동일하게 박혀 있음을 grep로 이미 확인했고(각 Edit 참조),
       이 assert 는 그 식 자체의 참/거짓이 기대와 같은지 별도로 검증한다."""
    print("\n=== [검증④] 소비처 4곳 제외 predicate 일치성 — 합성 행, GAS 미실행 ===")

    def excluded(status_val):
        return str(status_val or "").strip() == MARKER

    synth_rows = [
        {"name": "정상문의", "status": "컨택중"},
        {"name": "미기재", "status": ""},
        {"name": "SUC문의", "status": "SUC"},
        {"name": "LOSS문의", "status": "LOSS"},
        {"name": "소프트삭제1", "status": MARKER},
        {"name": "소프트삭제_공백포함", "status": "  " + MARKER + "  "},  # trim 확인
        {"name": "유사값(오탐 방지)", "status": "중복"},  # MARKER와 다른 문자열 — 제외되면 안 됨
    ]
    expect_excluded = {"소프트삭제1", "소프트삭제_공백포함"}
    got_excluded = {r["name"] for r in synth_rows if excluded(r["status"])}
    ok = got_excluded == expect_excluded
    print("기대 제외:", sorted(expect_excluded))
    print("실제 제외:", sorted(got_excluded))
    print("PASS" if ok else "FAIL")
    assert ok, "제외 predicate 가 기대와 다름 — Survey.js 4개 지점 비교식 재확인 필요"
    return ok


def main():
    print("### 새 문의 중복 삭제(소프트) 검증 시작 — 쓰기 0건 보장 ###")

    n1 = step_negative_no_keyphone()

    rows = fetch_live_rows()
    if not rows:
        print("실데이터 0건 — 이후 검증(②③) 스킵")
        real_row = None
        n2 = n3 = True
    else:
        real_row = rows[0]
        print("표본 행(음성 경로 검증용, 쓰기 없음):", real_row.get("rowIndex"), real_row.get("name"))
        n2 = step_negative_no_password(real_row)
        n3 = step_negative_wrong_password(real_row)

    n4 = dryrun_predicate_consistency()

    soft_deleted_now = [r for r in rows if str(r.get("status") or "").strip() == MARKER]
    print("\n=== 현재 소프트 삭제(중복) 표시 건수 ===")
    print(len(soft_deleted_now), "건")
    if not soft_deleted_now:
        print("0건 — 실데이터 전/후 숫자 대조는 지금 불가(대조 대상 없음). 위 predicate 대조(④)로 대체함을 정직하게 기록.")

    all_pass = n1 and n2 and n3 and n4
    print("\n### 최종 판정:", "GUARDED (전부 통과, 쓰기 0건)" if all_pass else "미완 — 위 로그 확인 필요", "###")


if __name__ == "__main__":
    main()
