# -*- coding: utf-8 -*-
"""쓰기 권한 관문 — WRITE_MODULES(목적지→허용 모듈 id) + write_allowed() 한 자리(배1112 · 2026-09-14).

api_write.py 와 api_reception_ops.py 양쪽이 이 표를 쓴다. api_write 가 api_reception_ops 를 이미
import 하므로(write_gas_key 재사용) api_reception_ops 가 거꾸로 api_write 를 import 하면 순환이 된다 —
그래서 권한 판정만 여기로 뗐다.

/auth/check 가 응답 헤더 X-Erp-Allowed 로 그 계정이 쓸 수 있는 모듈 id 목록을 돌려주고(관리자는 '*'),
nginx auth_request_set 이 그 값을 상류로 넘긴다(api.nginx.conf·chro.nginx.conf) — 클라이언트가 같은
이름 헤더를 직접 실어 보내도 nginx proxy_set_header 가 덮어써 위조가 안 된다.

HTTP 헤더는 latin-1 만 받는다 — 모듈 id 에 한글이 섞여 있어 /auth/check 가 id 하나하나를
urllib.parse.quote(id, safe='') 로 퍼센트 인코딩해 쉼표로 잇는다. 여기서 unquote 해 되돌린 뒤 비교한다.
"""
import urllib.parse

# 목적지(_gas_key·api_reception_ops.write_gas_key 반환값) → 그 목적지에 쓰기가 허용된 모듈 id 집합.
#   표에 없는 dest 는 제한 없음 — 아직 모듈 id 로 안 갈린 로그인 전용 화면이 많다(배1112 note).
#   saveBoard(공용 보드 · GM_TASK_OWNERS 등)는 dest 가 CHECK_GAS_URL 로 잡히지만 여러 화면이 공유하는
#   범용 저장소라 이 표로 안 가른다 — api_write.write() 가 action 단계에서 따로 건너뛴다.
WRITE_MODULES = {
    "RECEPTION_EXEC_URL": {
        "coo-reception-종합접수처-현황", "coo-reception-lost-found-register",
        "coo-reception-lost-found-disposal", "coo-reception-lost-found-gallery",
        "ceo-wellperion-guide-main",
    },
    "TODO_GAS_URL": {
        "coo-todo-업무-현황-ssot", "coo-todo-결재-현황-ssot", "coo-chairman-gm업무",
        "coo-chairman-회장님-지시사항", "coo-chairman-대표님-지시사항", "coo-notice-게시물-프로필월",
        "cpo-product-상품기획", "cto-automation-카톡전송관리", "ceo-wellperion-guide-main",
        "gm-월간운영계획", "coo-check-파트너팀-체계",
    },
    "CHECK_GAS_URL": {
        "check", "coo-check-운영부-체계", "coo-check-지원부-체계", "coo-check-주차관리부-체계",
        "coo-check-파트너팀-체계", "coo-check-전사-거래업체", "ceo-wellperion-guide-main",
    },
    "SCHEDULE_GAS_URL": {"coo-check-전사-일정", "ceo-wellperion-guide-main", "gm-월간운영계획"},
    "PROC_GAS_URL": {"cfo-finance-매출지출현황", "cfo-finance-지출품의", "coo-product-스팀다리미-구매현황"},
    "FUNNEL_EXEC_URL": {
        "member", "inquiry", "cpo-member-renewal", "cpo-member-lesson",
        "cpo-member-오넛티-접수현황", "cpo-member-실무진피드백", "ceo-wellperion-guide-main",
    },
    "INSTRUCTOR_GAS_URL": {"cpo-member-실무진피드백"},
    # 리셉션 업무·라커관리(api_reception_ops.target) — 두 화면 다 각자 index 모듈 하나씩.
    "RCOPS_GAS_URL": {"coo-리셉션-업무-index"},
    "LOCKER_GAS_URL": {"coo-리셉션-업무-라커관리-index"},
}


def write_allowed(request_headers, dest):
    """이 요청이 dest 로 쓰기를 보내도 되나. 순수 함수 — request_headers 는 get() 지원 dict-like면 된다.

    · X-Erp-Allowed: '*'(관리자) → 항상 허용
    · dest 가 WRITE_MODULES 에 없음 → 제한 없음(아직 모듈 단위로 안 갈린 화면)
    · 헤더가 없거나 빈 값 → 거부(관문을 탄 요청인데 허용 목록이 없다는 뜻)
    · 그 외 → 쉼표로 나눈 각 조각을 unquote 한 뒤 WRITE_MODULES[dest] 와 교집합이 있어야 허용
      (헤더 값은 퍼센트 인코딩돼 있다 — 위 머리말 참고. '*' 는 인코딩 없이 그대로 온다)
    """
    if dest not in WRITE_MODULES:
        return True
    allowed = str((request_headers or {}).get("x-erp-allowed", "") or "").strip()
    if allowed == "*":
        return True
    if not allowed:
        return False
    have = {urllib.parse.unquote(m.strip()) for m in allowed.split(",") if m.strip()}
    return bool(have & WRITE_MODULES[dest])


if __name__ == "__main__":   # python3 write_perm.py — 갈래 자체점검(네트워크·DB 없음)
    assert write_allowed({"x-erp-allowed": "*"}, "CHECK_GAS_URL") is True
    assert write_allowed({}, "CHECK_GAS_URL") is False
    assert write_allowed({"x-erp-allowed": ""}, "CHECK_GAS_URL") is False
    assert write_allowed({"x-erp-allowed": "member,inquiry"}, "FUNNEL_EXEC_URL") is True
    assert write_allowed({"x-erp-allowed": "member"}, "CHECK_GAS_URL") is False
    assert write_allowed({"x-erp-allowed": "coo-check-운영부-체계"}, "CHECK_GAS_URL") is True
    assert write_allowed({"x-erp-allowed": "member"}, "SOME_UNLISTED_DEST") is True   # 표에 없으면 무제한
    assert write_allowed({}, "SOME_UNLISTED_DEST") is True
    assert write_allowed({"x-erp-allowed": "coo-리셉션-업무-index"}, "RCOPS_GAS_URL") is True
    assert write_allowed({"x-erp-allowed": "coo-리셉션-업무-index"}, "LOCKER_GAS_URL") is False
    # 실제 헤더는 퍼센트 인코딩돼 온다(latin-1 만 받는 HTTP 헤더에 한글을 실은 값 · /auth/check 규격).
    _enc_check = urllib.parse.quote("coo-check-운영부-체계", safe="")
    assert write_allowed({"x-erp-allowed": "member," + _enc_check}, "CHECK_GAS_URL") is True
    assert write_allowed({"x-erp-allowed": _enc_check}, "FUNNEL_EXEC_URL") is False   # 다른 모듈이면 여전히 거부
    _enc_todo = urllib.parse.quote("coo-todo-업무-현황-ssot", safe="")
    assert write_allowed({"x-erp-allowed": _enc_todo}, "TODO_GAS_URL") is True
    print("write_perm 자체점검 통과")
