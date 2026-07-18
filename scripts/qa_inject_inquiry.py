# -*- coding: utf-8 -*-
"""문의 QA 정본 주입·스캔·검증 도구 (시토 2026-07-08).

■ 왜 이 스크립트가 정본인가 (한글 깨짐 재발 방지)
  - Funnel GAS(Survey.js) doGet 은 모든 action 을 쿼리파라미터로 처리한다.
  - Windows 에서 `curl "...?name=한글..."` 로 직접 주입하면 한글이 CP949(윈도우 기본)로
    퍼센트인코딩돼 GAS 가 UTF-8 로 오독 → "전화"→"������ȭ" 식 mojibake 로 시트에 저장된다.
    (2026-07-08 [자동QA] 테스트 1건이 이 경로로 문의 알림방 한글을 깨뜨림.)
  - Python requests 는 params 를 항상 UTF-8 퍼센트인코딩한다 → 한글 안전.
  - 따라서 문의 QA 주입은 반드시 이 스크립트(requests)로만. 손 curl 금지.
  참고 메모리: reference_gas_post_curl_no_follow_redirect, reference_python_console_utf8_env

■ 발송 코드는 정상 — 손대지 않는다. 수정 대상은 '주입 인코딩' 뿐(시모 진단 확정).

사용법:
  python scripts/qa_inject_inquiry.py scan            # 폼시트 깨진 행 스캔(읽기전용·미발송)
  python scripts/qa_inject_inquiry.py verify          # UTF-8 테스트 문의 1건 주입→알림 실측+readback
  python scripts/qa_inject_inquiry.py alert-test      # 🧪[TEST] 알림 1건만(행 생성 없음)
"""
import sys, io, json, time
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Funnel GAS webapp exec URL (scripts/telegram_health_check.py _FUNNEL_DIAG_URL 동일 소스)
FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)

# FORM_SHEETS (Survey.js 정본과 동기) — gid = 폼 응답탭
FORM_SHEETS = [
    {"gid": 1902010032, "type": "멤버십"},
    {"gid": 111889422, "type": "성인강습"},
    {"gid": 268994754, "type": "유소년강습"},
]

# mojibake/QA 탐지 시그니처
_BAD_MARKERS = ["�", "자동QA", "[자동QA]", "QA]", "테스트"]
_MOJIBAKE_BYTES = ["ȭ", "�", "Ʈ", "̷", "װ", "ũ", "ǥ"]  # CP949→UTF-8 오독 잔재 문자


def _get(params, timeout=40):
    """doGet 경로 호출 — requests 가 params 를 UTF-8 인코딩(한글 안전)."""
    r = requests.get(FUNNEL_EXEC_URL, params=params, timeout=timeout, allow_redirects=True)
    r.encoding = "utf-8"
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:500]}


def scan(max_row=400):
    """preview_notify_msg 로 각 폼시트 행을 미발송 미리보기 → mojibake 행 색출."""
    rows_param = ",".join(str(n) for n in range(2, max_row + 1))
    found = []
    for cfg in FORM_SHEETS:
        gid = cfg["gid"]
        print(f"\n── 스캔: {cfg['type']} (gid={gid}) rows 2~{max_row} ──")
        code, data = _get({"action": "preview_notify_msg", "gid": gid, "rows": rows_param})
        if not isinstance(data, dict) or not data.get("ok"):
            print(f"  응답 이상: HTTP {code} · {str(data)[:200]}")
            continue
        items = data.get("data") or data.get("previews") or []
        for it in items:
            msg = json.dumps(it, ensure_ascii=False)
            if any(m in msg for m in _MOJIBAKE_BYTES) or "자동QA" in msg or "�" in msg:
                rownum = it.get("row") or it.get("rowNum") or it.get("rownum") or "?"
                print(f"  ⚠ 깨진 행 발견: gid={gid} row={rownum}")
                print(f"    {msg[:300]}")
                found.append({"gid": gid, "type": cfg["type"], "row": rownum, "raw": msg[:300]})
    print("\n════ 스캔 요약 ════")
    if found:
        for f in found:
            print(f"  · {f['type']} gid={f['gid']} row={f['row']}")
        print(f"  총 {len(found)}건 — 삭제 대상")
    else:
        print("  깨진 행 없음(저장된 mojibake 행 미발견 — 알림 전용 주입이었을 수 있음)")
    return found


def verify():
    """UTF-8 테스트 문의 1건 주입 → 신규문의 알림 실발송 + readback 무결성 확인."""
    name = "[UTF8검증]한글자동테스트"
    params = {
        "action": "submit_inquiry",
        "name": name,
        "phone": "010-0000-0000",
        "type": "멤버십 상담",
        "inflow": "전화",
        "message": "한글 인코딩 검증 — 종목·유입채널·내용 정상 렌더 확인용(자동 삭제 대상)",
    }
    print("── 주입 파라미터(UTF-8) ──")
    print(json.dumps(params, ensure_ascii=False, indent=2))
    code, data = _get(params)
    print(f"\n주입 응답: HTTP {code} · {json.dumps(data, ensure_ascii=False)}")
    inq_id = data.get("id") if isinstance(data, dict) else None

    time.sleep(2)
    print("\n── readback (inquiry_list 에서 방금 행 조회) ──")
    code2, data2 = _get({"action": "inquiry_list"})
    ok = False
    if isinstance(data2, dict) and data2.get("ok"):
        for row in data2.get("data", []):
            if row.get("id") == inq_id or row.get("이름") == name:
                stored = row.get("이름", "")
                clean = "�" not in stored and stored == name
                print(f"  저장된 이름: {stored!r}  → {'✅ 무결(UTF-8 정상)' if clean else '❌ 깨짐'}")
                ok = clean
                break
        else:
            print("  방금 행을 목록에서 못 찾음(캐시 지연 가능) — 텔레그램 알림 육안 확인")
    else:
        print(f"  inquiry_list 응답 이상: {str(data2)[:200]}")
    print("\n※ 문의 알림방(-5516675010)에 방금 [UTF8검증] 알림이 한글 정상으로 떴는지 육안 확인하세요.")
    print("※ 이 테스트 행은 '문의접수' 시트에 남습니다([UTF8검증] 태그로 식별·정리 가능).")
    return ok


def alert_test():
    """행 생성 없이 🧪[TEST] 알림 1건만 발송(경로 점검용)."""
    code, data = _get({"action": "test_form_submit_notify"})
    print(f"alert-test 응답: HTTP {code} · {json.dumps(data, ensure_ascii=False)}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if mode == "scan":
        scan()
    elif mode == "verify":
        verify()
    elif mode == "alert-test":
        alert_test()
    else:
        print(f"알 수 없는 모드: {mode} (scan|verify|alert-test)")
