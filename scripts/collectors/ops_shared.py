# -*- coding: utf-8 -*-
"""
ops_shared.py — 운영 다이제스트 2계열(아침 scripts/ops_daily_digest.py ·
밤 telegram_bot/daily_scheduler.py run_daily_digest) 공용 수집층(2026-07-21 순수 리팩터).

두 파일이 "동일 정본 최소 복사" 주석과 함께 각자 들고 있던 GAS URL 상수 3종·재시도 GET
래퍼·UTC→KST 시각 변환·업무완료 상태셋을 이 파일 하나로 수렴한다.

★동작보존 원칙(중요): 값·리턴 시그니처를 그대로 유지한다.
- gas_get(): 두 원본 _gas_get의 재시도(attempts=3)·성공판정(HTTP 200)·리턴(Response|None)
  로직은 동일. 유일한 차이는 daily_scheduler.py 쪽이 실패 시도마다 logger.warning으로
  경보를 남기던 것 — log_fn 콜백으로 그대로 보존(기본값 None=무음, ops_daily_digest.py는
  콜백을 넘기지 않아 기존처럼 무음 유지).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

# 문의·등록 GAS(.deploy-funnel/Survey.js 배포본). inquiry_list=문의알림방 대시보드 소스와 동일 정본.
# env로 오버라이드 가능(기본값=두 소비자 파일이 이전에 각자 갖고 있던 동일 리터럴).
FUNNEL_EXEC_URL = os.environ.get(
    "FUNNEL_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec",
)
# 종합접수처 GAS(.deploy-reception/RECEPTION_배포.js) — reg_list=6종 접수 카테고리(분실물/시설물고장/청결/칭찬/쓴소리/컴플레인).
RECEPTION_EXEC_URL = os.environ.get(
    "RECEPTION_EXEC_URL",
    os.environ.get("VOC_EXEC_URL", "https://script.google.com/macros/s/AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec"),
)
# 실무진 업무현황(업무 SSOT · S3) GAS — action=todo_list.
# ※'G1 항로' 라고 적혀 있던 것을 바로잡았다(2026-08-14) — G1 은 GM 개인 판이고, 이 GAS 는
#   실무진이 굴리는 업무 SSOT(S3) 다. AI 배의 항로는 자율현황 🧭 항로가 따로 갖는다.
SSOT_API_URL = os.environ.get(
    "SSOT_API_URL",
    "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec",
)

# 전사일정 GAS — action=load_schedule / save_schedule.
# 2026-08-14 시토: 같은 리터럴이 gm_checkin·monthly_ops_sync·report_stream_3_impl 세 곳에
# 따로 박혀 있었다(약속 L01 위반 — 배포본이 바뀌면 세 곳을 다 고쳐야 한다). 여기로 모으고
# 세 소비자는 import 한다. 새 소비자도 여기서 가져다 쓴다.
SCHEDULE_GAS_URL = os.environ.get(
    "SCHEDULE_GAS_URL",
    "https://script.google.com/macros/s/AKfycbyHY37y5Cu2OGkqoODbygg5-Q-5ouCOqSOVu_HMFPlKXgudJMtiLXEtstTs3Ow4xvUn/exec",
)

# todo_list '상태' 완료 판정 기준(양쪽 소비자 동일).
TODO_DONE_STATUSES = {"완료", "폐기", "DONE", "완료됨"}

# ★중간관리자 원장 이슈 → 업무 SSOT 행 다리(배1102 · GM 지시 2026-09-07)의 추적 열쇠.
# 만드는 쪽(ops_daily_digest.bridge_to_todo)과 읽는 쪽(send_ops_digest.build_reply_nudge_items)
# 이 같은 문자열을 봐야 다리가 안 끊긴다(약속 L01) — 여기 한 곳에만 둔다.
MGR_LEDGER_MARKER_TAG = "[중간관리자원장"


def mgr_ledger_marker(date: str, issue: str) -> str:
    return f"[중간관리자원장 {date} | {issue}]"


def reception_key() -> str:
    """접수 GAS 접근 게이트 열쇠(GAS ScriptProperties ACCESS_TOKEN 과 같은 값).

    GAS 쪽 TOKEN_ENFORCE=1 이 켜지면 PII 액션(reg_list·lf_list·reg_delete·lf_delete …)은
    key 파라미터가 있어야 통과한다. 값은 저장소에 두지 않는다 — 환경변수 RECEPTION_TOKEN
    우선, 없으면 telegram_bot/.env(저장소 밖) 한 줄(_proc_password 와 같은 관례).
    ★비어 있으면 아무것도 붙지 않는다 = 스위치 켜기 전 동작 무변경."""
    k = os.environ.get("RECEPTION_TOKEN", "").strip()
    if k:
        return k
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "telegram_bot", ".env")
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("RECEPTION_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def gas_get(
    url: str,
    params: dict | None = None,
    *,
    timeout: int = 40,
    attempts: int = 3,
    label: str = "GAS",
    log_fn=None,
) -> object | None:
    """GAS(script.google.com) GET 재시도 래퍼. 성공(HTTP 200) 시 Response, 전량 실패 시 None.
    log_fn(msg: str)을 넘기면 실패 시도마다 호출(선택 — 기본은 무음)."""
    if url == RECEPTION_EXEC_URL and not (params or {}).get("key"):
        _k = reception_key()          # 접수 GAS 의 GATED 액션(reg_list·lf_list …) 통과용. 없으면 무동작.
        if _k:
            params = dict(params or {})
            params["key"] = _k
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if log_fn is not None:
                log_fn(f"{label} HTTP {resp.status_code} (시도 {attempt}/{attempts})")
        except Exception as e:
            if log_fn is not None:
                log_fn(f"{label} 조회 실패 (시도 {attempt}/{attempts}): {e}")
    return None


ERP_API_BASE = os.environ.get("ERP_API_BASE", "https://erp.wellperion.com")


def _env_line(key: str) -> str:
    """telegram_bot/.env 한 줄 읽기 — reception_key 와 같은 관례(값은 저장소에 두지 않는다)."""
    v = os.environ.get(key, "").strip()
    if v:
        return v
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "telegram_bot", ".env")
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def server_reception_rows(*, timeout: int = 20, log_fn=None) -> list | None:
    """서버 원장의 접수 목록. 못 읽으면 None(호출부는 종전 GAS 값으로 간다).

    로그인 쿠키(erp_session)를 그대로 쓴다 — 새 인증 체계도, 새 공개 통로도 만들지 않는다.
    토큰은 telegram_bot/.env 의 ERP_SESSION_TOKEN 한 줄(저장소 밖).
    """
    tok = _env_line("ERP_SESSION_TOKEN")
    if not tok:
        return None
    try:
        r = requests.get(ERP_API_BASE + "/api/reception/board",
                         headers={"Cookie": "erp_session=" + tok}, timeout=timeout)
        if r.status_code != 200:
            if log_fn:
                log_fn(f"서버 접수 조회 HTTP {r.status_code} — 시트 값으로 갑니다")
            return None
        d = r.json()
        return d.get("data") or [] if d.get("ok") else None
    except Exception as e:
        if log_fn:
            log_fn(f"서버 접수 조회 실패: {e} — 시트 값으로 갑니다")
        return None


def merge_reception_rows(sheet_rows: list | None, server_rows: list | None) -> list:
    """시트 목록 + 서버에만 있는 접수를 접수번호로 합친다 (배1166 · 2026-09-09).

    왜 합치나: 9월 5일(배984)부터 새 접수는 서버 원장에만 적히고 시트는 동결됐다. 그런데
    아침·저녁 접수 통은 아직 시트(reg_list)를 읽어서, 그 뒤 들어온 접수가 실무진 통에
    한 번도 안 실렸다(09-07·08 접수 8건 · 그중 회원 타박상 건 포함).

    왜 시트를 버리지 않나: 시트 행에만 있는 칸이 여섯이다(area·dueDate·handlerCanon·
    memberReplyTemplate·occurredAt·policyFix). 통이 그 칸들을 실제로 쓴다(기한·담당 정규화 등).
    서버 값으로 통째 갈아치우면 옛 접수의 그 정보가 사라진다. 그래서 시트 행은 그대로 두고
    **서버에만 있는 접수만 덧붙인다** — 잃는 것 없이 빠진 것만 채운다.
    """
    out = list(sheet_rows or [])
    if not server_rows:
        return out
    have = {str(r.get("regId") or "") for r in out if isinstance(r, dict)}
    for r in server_rows:
        if isinstance(r, dict) and str(r.get("regId") or "") not in have:
            out.append(r)
    return out


def reception_rows(sheet_rows: list | None, *, log_fn=None) -> list:
    """접수 통이 읽어야 하는 최종 목록 — 시트 + 서버 신규분."""
    return merge_reception_rows(sheet_rows, server_reception_rows(log_fn=log_fn))


def reception_elapsed_days(r: dict, now: datetime | None = None) -> int:
    """종합접수처(RECEPTION_EXEC_URL reg_list) 한 건의 접수 경과일수 — 정본.

    ★기준=createdAt(GAS 라벨 '접수일시') 날짜만 비교한 정수 일수. occurredAt('발생시점')은
    쓰지 않는다 — '접수 건이 며칠째'는 언제 접수됐는지 기준이지 언제 사건이 일어났는지가
    아니다(GM 2026-08-05: 같은 건이 ops_daily_digest=35일째 vs report_stream_2b_reception=
    28.8일로 갈라져 지적됨 — occurredAt 혼용 + 소수점 표기가 원인).
    소비자(ops_daily_digest.py·report_stream_2b_reception.py·worklog_gaps.py)는 각자
    다시 세지 말고 이 함수를 import해 쓴다(약속 L01)."""
    now = now or datetime.now()
    try:
        created = datetime.strptime(str(r.get("createdAt", ""))[:10], "%Y-%m-%d").date()
    except Exception:
        return 0
    now_date = now.date() if hasattr(now, "date") else now
    return (now_date - created).days


def utc_iso_to_kst_date(iso_str: str) -> str:
    """문의 API '시각' 필드 → KST YYYY-MM-DD.
    ★2026-07-27 시토(배10357): GAS inquiry_list가 그동안 Date를 그대로 JSON.stringify해
    UTC ISO('...Z')로 내보내던 버그를 서버에서 KST 문자열('YYYY-MM-DD HH:mm:ss', Z 없음)로
    고쳤다(.deploy-funnel-v2/Survey.js). 그 GAS 배포가 나가기 전까지는 라이브가 여전히
    UTC를 준다 — 배포 시점과 이 코드 반영 시점이 어긋나도 이중변환 사고가 안 나도록
    두 포맷을 모두 정확히 처리한다(Z 있으면 UTC로 보고 +9시간, 없으면 이미 KST이므로
    그대로 날짜만 취한다)."""
    s = str(iso_str or "").strip()
    if not s:
        return ""
    try:
        if s.endswith("Z"):
            dt_utc = datetime.fromisoformat(s.rstrip("Z").replace("T", " ")).replace(tzinfo=timezone.utc)
            return (dt_utc + timedelta(hours=9)).strftime("%Y-%m-%d")
        return s[:10]
    except Exception:
        return ""
