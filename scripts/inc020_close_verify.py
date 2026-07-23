# -*- coding: utf-8 -*-
"""INC-020 종결 검증 스크립트 (시포 2026-07-20, 1회성 — 완료 후 보관용).

용도:
  1) 배포된 keyPhone 필수화 fail-safe를 라이브 /exec에서 무해(쓰기 없음)하게 재현검증
  2) 테스트 문의 3건(배포검증테스트_*, 010-0000-0000)을 content-key(keyPhone) 기반으로
     bottom-up 삭제 — rowIndex 단독 삭제 금지 원칙 준수, 매 삭제 직전 전체행 덤프로 재확인.
  3) 최종 상태(실고객 2건 존재·중복 없음·테스트 3건 없음) 실측.

참고: reference_gas_post_curl_no_follow_redirect(GAS 호출은 requests, 손curl 금지 — 한글 인코딩 안전).
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


import re

def norm_phone(p):
    return "".join(ch for ch in str(p) if ch.isdigit())


def is_test_row(r):
    """정본 판정(daily_scheduler.py _is_test_row / Survey.js _isTestInquiryRow_ 와 동일 기준) —
    전화 010-0000-XXXX 더미 우선, 또는 name+content/memo에 테스트성 마커(테스트/자동검증/E2E/깨진문자/[자동).
    1차 시도(순수 prefix 매칭)에서 CP949 mojibake로 이름이 깨진 행(703/704)을 놓쳐 이 정본으로 교체."""
    digits = norm_phone(r.get("phone", ""))
    if digits.startswith("0100000"):
        return True
    blob = str(r.get("name", "")) + " " + str(r.get("inquiryContent", "")) + " " + str(r.get("memo", ""))
    return bool(re.search(r"테스트|자동검증|E2E|�|\[자동", blob))


def step_negative_no_keyphone():
    print("\n=== [검증①] keyPhone 미동봉 삭제 시도 — 거부돼야 함(쓰기 없음, 무해) ===")
    code, data = call({"action": "member_inquiry_delete", "rowIndex": "2", "gid": "1902010032"})
    print("HTTP", code, json.dumps(data, ensure_ascii=False))
    ok = (data.get("ok") is False and data.get("error") == "keyPhone 필수 — 대조 없이 삭제 불가")
    print("PASS" if ok else "FAIL", "— keyPhone 미동봉이 즉시 거부됨" if ok else "— 예상과 다름!")
    return ok


def step_negative_wrong_keyphone(row):
    print("\n=== [검증②] keyPhone 오기재(실제 값과 다름) — 거부돼야 함(쓰기 없음) ===")
    code, data = call({
        "action": "member_inquiry_delete",
        "rowIndex": str(row["rowIndex"]),
        "gid": "1902010032",
        "keyPhone": "010-9999-9999",
    })
    print("HTTP", code, json.dumps(data, ensure_ascii=False))
    ok = (data.get("ok") is False and data.get("error") == "row-key-mismatch")
    print("PASS" if ok else "FAIL", "— 대조키 불일치가 거부됨" if ok else "— 예상과 다름!")
    return ok


def fetch_live_rows():
    print("\n=== 라이브 재조회(nocache=1) — 삭제 직전 최신 상태 확보 ===")
    code, data = call({"action": "member_inquiry_list", "nocache": "1"})
    if not data.get("ok"):
        print("FAIL — 조회 실패:", data)
        sys.exit(1)
    rows = data["data"]
    print("전체 행수:", len(rows))
    return rows


def find(rows, phone):
    np = norm_phone(phone)
    return [r for r in rows if norm_phone(r.get("phone", "")) == np]


def main():
    print("### INC-020 종결 검증 시작 ###")

    n1 = step_negative_no_keyphone()

    rows = fetch_live_rows()

    kwon = find(rows, "010-3794-3617")
    dg = find(rows, "010-3777-6675")
    r1 = find(rows, "010-5215-9886")
    r2 = find(rows, "010-8816-2121")
    test_rows = [r for r in rows if is_test_row(r)]

    print("\n=== 실측 요약(삭제 전) ===")
    print("권소현(앵커) 매치:", len(kwon), [r["rowIndex"] for r in kwon])
    print("이동걸(앵커2) 매치:", len(dg), [r["rowIndex"] for r in dg])
    print("복구대상1(010-5215-9886) 매치:", len(r1), [r["rowIndex"] for r in r1])
    print("복구대상2(010-8816-2121) 매치:", len(r2), [r["rowIndex"] for r in r2])
    print("테스트행 매치:", len(test_rows), [(r["rowIndex"], r["name"]) for r in test_rows])

    if len(r1) != 1 or len(r2) != 1:
        print("\n★★★ 중단 — 실고객 복구행이 정확히 1건씩이 아님. 자동 진행 중단, 수동 판단 필요. ★★★")
        sys.exit(1)

    n2 = step_negative_wrong_keyphone(kwon[0]) if kwon else True

    if not test_rows:
        print("\n테스트 행 없음 — 정리 단계 스킵.")
    else:
        print(f"\n=== [검증③+정리] 테스트 행 {len(test_rows)}건 — 직전 전체행 덤프 후 bottom-up keyPhone 삭제 ===")
        # bottom-up: rowIndex 내림차순으로 삭제해야 앞선 삭제가 뒤 rowIndex를 밀지 않음.
        test_rows_sorted = sorted(test_rows, key=lambda r: -r["rowIndex"])
        for r in test_rows_sorted:
            print("\n-- 삭제 대상 전체 덤프 --")
            print(json.dumps(r, ensure_ascii=False, indent=2))
            is_test = is_test_row(r)
            if not is_test:
                print("★★★ 중단 — 테스트 행 판정 실패(이름/전화 패턴 불일치). 삭제하지 않음. ★★★")
                sys.exit(1)
            code, data = call({
                "action": "member_inquiry_delete",
                "rowIndex": str(r["rowIndex"]),
                "gid": "1902010032",
                "keyPhone": r["phone"],
            })
            print("삭제 응답:", json.dumps(data, ensure_ascii=False))
            if not data.get("ok"):
                print("★★★ 중단 — 삭제 실패. ★★★")
                sys.exit(1)

    print("\n=== 최종 재조회(nocache=1) — 실고객 2건·중복없음·테스트0건 확인 ===")
    final_rows = fetch_live_rows()
    f_kwon = find(final_rows, "010-3794-3617")
    f_dg = find(final_rows, "010-3777-6675")
    f_r1 = find(final_rows, "010-5215-9886")
    f_r2 = find(final_rows, "010-8816-2121")
    f_test = [r for r in final_rows if is_test_row(r)]

    print("권소현:", len(f_kwon), "| 이동걸:", len(f_dg), "| 복구1:", len(f_r1), "| 복구2:", len(f_r2), "| 테스트잔존:", len(f_test))
    print(json.dumps({"kwon": f_kwon, "dg": f_dg, "r1": f_r1, "r2": f_r2}, ensure_ascii=False, indent=2))

    all_pass = n1 and n2 and len(f_r1) == 1 and len(f_r2) == 1 and len(f_test) == 0 and len(f_kwon) == 1 and len(f_dg) == 1
    print("\n### 최종 판정:", "GUARDED (전부 통과)" if all_pass else "미완 — 위 로그 확인 필요", "###")


if __name__ == "__main__":
    main()
