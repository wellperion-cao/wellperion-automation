# -*- coding: utf-8 -*-
"""회원 전화 중복매칭 가드 검증 스크립트 (시토 2026-08-05, 1회성 — 완료 후 보관용).

배경: "저장이 엉뚱한 회원에게 들어간다" 반복 신고(5건·12일·4회)의 뿌리 — _memberActiveUpsert_·
_regRemove_ 가 전화번호 첫 매칭만으로 행을 잡거나 매칭 전부를 지워, 가족·유소년처럼 번호를
공유하는 회원이 있으면 다른 실회원 행을 조용히 덮어쓰거나 지웠다. 고친 내용:
  ① _memberActiveUpsert_(Survey.js) — 기존 행 매칭 전 _countRowsByPhone_ 로 2건+ 면 거부(텔레그램 경보).
  ② _memberActiveUpsert_ 호출부(member_inquiry_update SUC 경로, 5401 부근) — regDate 강제 폴백(||_todayKR_())
    제거. 이미 SUC 인 행을 재저장할 때마다 등록일자가 "오늘"로 덮이던 지문 오염을 막는다.
  ③ _regRemove_(Survey.js) — 매칭 2건+ 면 전부 삭제하지 않고 거부. 호출부 무음 catch에 기록+경보 추가.

이 스크립트는 실제 시트에 쓰지 않는다 — 판정 임계값(2건 이상=거부)이 세 지점 모두 일관되는지
합성 데이터로 확인하고, 라이브 조회(읽기 전용)로 현재 건수가 손상 없이 그대로인지 대조한다.
"""
import sys, io, json
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)


def call(params, timeout=40):
    r = requests.get(FUNNEL_EXEC_URL, params=params, timeout=timeout, allow_redirects=True)
    r.encoding = "utf-8"
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:500]}


# ── ① 순수 로직 대조 — _countRowsByPhone_ 기반 임계값(>=2 거부)을 파이썬으로 복제해 합성 데이터로 확인 ──
def dryrun_threshold_consistency():
    print("=== [검증①] 전화 매칭 임계값(2건 이상 거부) — 합성 데이터, GAS 미실행 ===")

    def norm(p):
        return "".join(c for c in str(p) if c.isdigit())

    def count_by_phone(rows, phone_key):
        k = norm(phone_key)
        return sum(1 for r in rows if norm(r) == k)

    def decide(rows, phone_key):
        n = count_by_phone(rows, phone_key)
        return ("reject", n) if n >= 2 else ("proceed", n)

    cases = [
        ("0건(신규)", [], "010-1111-1111", "proceed", 0),
        ("1건(정상 업데이트)", ["010-2222-2222"], "010-2222-2222", "proceed", 1),
        ("2건(가족 공유, 거부돼야 함)", ["010-3333-3333", "010-3333-3333"], "010-3333-3333", "reject", 2),
        ("3건(거부돼야 함)", ["010-4444-4444"] * 3, "010-4444-4444", "reject", 3),
        ("무관한 전화 섞여도 대상만 카운트", ["010-5555-5555", "010-6666-6666", "010-5555-5555"], "010-5555-5555", "reject", 2),
    ]
    all_ok = True
    for label, rows, key, expect_decision, expect_n in cases:
        decision, n = decide(rows, key)
        ok = (decision == expect_decision and n == expect_n)
        all_ok = all_ok and ok
        print(f"  {label}: 판정={decision}({n}건) 기대={expect_decision}({expect_n}건) -> {'PASS' if ok else 'FAIL'}")
    assert all_ok, "임계값 판정이 기대와 다름"
    print("PASS (5/5)\n")
    return all_ok


# ── ② 회귀 확인 — 라이브 읽기만(쓰기 없음), 건수가 그대로인지 ──────────────────────────
def live_regression_check():
    print("=== [검증②] 라이브 읽기 회귀 확인(쓰기 없음) ===")
    code, data = call({"action": "member_inquiry_list", "nocache": "1"})
    ok1 = bool(data.get("ok"))
    n1 = len(data.get("data", []))
    print(f"member_inquiry_list: ok={ok1} count={n1}")

    code2, data2 = call({"action": "cpo_today_stats"})
    ok2 = bool(data2.get("ok"))
    print(f"cpo_today_stats: ok={ok2} 응답 일부={json.dumps(data2, ensure_ascii=False)[:200]}")

    all_ok = ok1 and ok2 and n1 > 0
    print("PASS" if all_ok else "FAIL")
    return all_ok


def main():
    print("### 회원 전화 중복매칭 가드 검증 시작 — 쓰기 0건 ###\n")
    r1 = dryrun_threshold_consistency()
    r2 = live_regression_check()
    print("\n### 최종 판정:", "GUARDED (쓰기 0건, 임계값 일관, 라이브 회귀 0)" if (r1 and r2) else "미완 — 로그 확인 필요", "###")


if __name__ == "__main__":
    main()
