# -*- coding: utf-8 -*-
"""
CPO(시포) 일/주/월 자동 보고 생성기 — C-Level 자율화 두뇌 첫 배(④ 텔레그램 자동보고).
스펙 정본: .omc/specs/deep-interview-cpo-autonomy-brain.md

기존 인프라 재활용(맨땅 신축 금지):
- 발신: telegram_bot/daily_scheduler.py 의 send_telegram 패턴(HTTP POST) 재사용.
- 방: telegram_bot/.env 기존 3방 분리(TELEGRAM_INQUIRY_CHAT_ID 등) 재사용 — 새 방 생성 없음.
- 데이터: .deploy-funnel/Survey.js GAS 기존 액션(member_inquiry_list·cpo_today_stats·
  cpo_churn_stats) 재사용 — 새 시트·새 백엔드 없음.
- 상태 노출: status/kakao_last_send.json 패턴(카톡전송관리.html)과 동일하게
  status/cpo_report_state.json 을 raw.githubusercontent 로 ERP에서 직접 조회.

재사용 설계(타 C-Level 확산용):
  render_header() · _gas_get() · run()/_send_telegram()/_write_state() 골격은 그대로 두고
  build_daily_report/build_weekly_report/build_monthly_report 3개 함수 안의 데이터
  소스·집계 로직만 자기 도메인 것으로 교체하면 동일 파이프라인 재사용 가능.

게이트(v1 안전장치): CPO_REPORT_LIVE 환경변수(telegram_bot/.env) 미설정/0/false = OFF
  → 렌더만 하고 실제 발신은 하지 않는다. GM이 메시지 룩 확인 후 값을 1로 바꿔야 발효.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

try:  # 발신 공용 관문(페이싱+429재시도+검수+로깅, best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(token, chat_id, text, **k):
        return False

try:  # GAS 재시도 GET 전송 정본(약속 L01) — 임포트 실패해도 _gas_get 은 폴백으로 동작
    from collectors.ops_shared import gas_get as _gas_get_shared
except Exception:
    _gas_get_shared = None

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "telegram_bot" / ".env"
STATE_FILE = REPO_ROOT / "status" / "cpo_report_state.json"

# 문의회원 데이터 GAS 엔드포인트 — daily_scheduler.py FUNNEL_EXEC_URL 과 동일(SSOT).
FUNNEL_EXEC_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)

_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
_LOSS_STATUSES = {"LOSS", "환불", "양도LOSS"}
_SUCCESS_STATUSES = {"SUC", "단기SUC"}
# 해소·취소 계열(=이미 끝난 문의) 판별. 배9597 결정정합 게이트 A4.
# ★대조키 없음이 설계의 핵심: 종결 표시가 문의 행 자체(status 칸)에 들어 있어 다른 원천과
#   맞춰볼 필요가 없다 — 행번호(INC row-delete race)도, 전화번호도 키로 쓰지 않는다.
#   전화번호 단독 대조는 실측상 위험(2026-07-24): 재문의 고객은 같은 번호에 문의 행이 2줄
#   생기고(라이브 3건 확인), 옛 행이 종결이라고 번호로 빼면 살아있는 새 문의까지 사라진다.
# 키워드 판별인 이유: 진행상태는 실무진이 시트에서 값을 늘릴 수 있어 값 하드코딩은 곧 낡는다.
#   Survey.js `_lessonScopeFilter_` 의 terminal 정규식과 같은 방식(도메인 내 일관).
_CLOSED_STATUS_RE = re.compile(r"종결|취소|해소")


def _is_closed_status(status: str) -> bool:
    """문의가 '해소·취소'로 이미 끝났는지(행 자체 표시 기준). 끝난 문의는 일일 액션카드에서 제외."""
    return bool(_CLOSED_STATUS_RE.search(str(status or "")))
_AUTO_FOOTER = "_본 메시지는 자동 발송입니다._"


# ── 환경변수 로드 (telegram_bot/.env 재사용, 신규 자격증명 저장 없음) ─────────────
def _load_env() -> dict:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_INQUIRY_CHAT_ID", "TELEGRAM_CHAT_ID", "CPO_REPORT_LIVE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


ENV = _load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
# 실무진 문의방 (project_telegram_3room_split — 핵심멤버방 3분류 중 '문의' 방)
INQUIRY_CHAT_ID = int(ENV.get("TELEGRAM_INQUIRY_CHAT_ID") or -5516675010)
# GM 채널 (@namuki_report_bot, Chat 8254867551)
GM_CHAT_ID = int(ENV.get("TELEGRAM_CHAT_ID") or 8254867551)


def report_live_enabled() -> bool:
    """CPO_REPORT_LIVE 게이트. 미설정/0/false/off = OFF(렌더만).
    라이브 발효는 GM이 메시지 룩 확인 후 값을 켜는 것(코드는 기본 OFF)."""
    v = str(ENV.get("CPO_REPORT_LIVE", "")).strip().lower()
    return v in ("1", "true", "on", "yes")


# ── 공용 GAS 조회 헬퍼 ────────────────────────────────────────────────────────
# 2026-08-05(시토, 흩어진 파이프라인 통합) — 전송(HTTP GET 재시도) 자체는
# collectors.ops_shared.gas_get(정본, 약속 L01)에 위임한다. 여기 남는 건 action
# 파라미터 조립 + GAS 응답의 ok 필드 판정뿐 — daily_scheduler.py 가 예전에 똑같은
# retry-loop 을 갖고 있다가 ops_shared 로 옮긴 것과 같은 정리. ★동작 무변경: 원본은
# "HTTP 200인데 ok=false"면 다음 시도로 넘어갔다(ok=true를 볼 때까지 최대 attempts회) —
# 그 재시도 의미를 지키려고 ops_shared.gas_get(attempts=1)을 바깥 루프로 감싼다
# (ops_shared.gas_get 자체의 attempts=3 재시도는 "이 한 번의 시도"에 대해서만 쓰지 않음).
def _gas_get(action: str, params: dict | None = None, timeout: int = 40, attempts: int = 3) -> dict | None:
    """GAS GET 재시도 헬퍼. 성공(ok=true) 시 dict, 실패 시 None(정직 실패 신호 — 지어내지 않음)."""
    q = {"action": action}
    if params:
        q.update(params)
    for _ in range(attempts):
        resp = (
            _gas_get_shared(FUNNEL_EXEC_URL, q, timeout=timeout, attempts=1, label=f"cpo_report:{action}")
            if _gas_get_shared is not None
            else _gas_get_fallback(q, timeout)
        )
        if resp is None:
            continue
        try:
            data = resp.json()
        except Exception:
            continue
        if data.get("ok"):
            return data
    return None


def _gas_get_fallback(q: dict, timeout: int):
    """ops_shared 임포트 실패 시에만 쓰는 원본 그대로의 단발 GET(폴백 — 기동 실패 금지)."""
    try:
        return requests.get(FUNNEL_EXEC_URL, params=q, timeout=timeout, allow_redirects=True)
    except Exception:
        return None


def fetch_member_inquiries() -> list[dict] | None:
    """문의회원 라이프사이클 원본 행. 실패 시 None(정직 '데이터 없음' 표기용)."""
    data = _gas_get("member_inquiry_list")
    if data is None:
        return None
    return data.get("data", [])


def fetch_active_members(scope: str = "valid") -> list[dict] | None:
    """유효회원 명단 원본 행(member_active_list). 실패 시 None. 배286 후속(2026-08-01) —
    기간(시작일자·잔여일) 미기재 회원 감시(cpo_member_rollup)가 이 함수를 쓴다."""
    data = _gas_get("member_active_list", {"scope": scope}, timeout=60)
    if data is None:
        return None
    return data.get("data", [])


_LESSON_TYPES = ("성인강습", "유소년강습")


def fetch_lesson_inquiries(lesson_type: str, scope: str = "all") -> list[dict] | None:
    """강습(성인·유소년) 문의 원본 행. 실패 시 None(정직 '데이터 없음' 표기용).
    멤버십(member_inquiry_list)과 별개 원천이라 별도 fetch — 화면과 같은 액션을 쓴다."""
    data = _gas_get("lesson_inquiry_list", {"type": lesson_type, "scope": scope}, timeout=60)
    if data is None:
        return None
    return data.get("data", [])


def unassigned_lesson_candidates(rows: list[dict]) -> list[dict]:
    """★아무도 손대지 않은 강습 문의 — 진행상태·담당자·메모·컨택 흔적이 '전부' 비어 있는 건.

    2026-07-23 시포 실측으로 드러난 구멍: 2026-03 이후 166건(성인 78·유소년 88)이 이 상태였다.
    상태 미입력이 원인이 아니라 '담당자 미배정'이 원인이다 — 빈칸 136건 중 132건(97%)이
    담당자도 없었고, 담당자가 붙은 건은 상태가 대부분 채워져 있었다. 즉 배정이 안 되면
    아무도 안 잡고, 고객은 연락을 못 받는다(지표 문제가 아니라 고객 유실).

    판정은 '흔적 없음' 하나로만 한다 — 상태만 비었고 상담 메모가 있는 건은 응대는 된 것이라
    여기서 제외한다(과잉 경보 금지). GM 지침(2026-07-23): 건별 반복 알림 금지, 하루 일과
    정리에만 모아서 1회 표시."""
    out = []
    for r in rows:
        def _blank(k: str) -> bool:
            return not str(r.get(k) or "").strip()
        if _blank("status") and _blank("owner") and _blank("memo") and _blank("note") and not r.get("contacts"):
            out.append(r)
    return out


def is_external_lesson(sport) -> bool:
    """외부 파트너가 직접 응대하는 강습인가 — 지금은 뮤지컬(Brad Little Star Academy) 하나.

    2026-07-25 GM: "뮤지컬팀이 직접 응대를 하는데 문의랑 응대 안 한 것도 운영부로 컨택이 오니까
    우리가 머금고 컨택 여하도 확인이 가능해야 해."
      → 집계에서 빼지 않는다(우리가 계속 들고 본다). 다만 '오늘 우리 실무진이 컨택할 몫'과는
        갈라 놓는다 — 안 그러면 미응대 377건 중 127건(34%)이 전부 앞줄을 차지해, 정작 우리가
        연락해야 할 수영·스쿼시 건이 25일 뒤로 밀린다(실측).
    판정은 종목 문자열의 '뮤지컬' 한 토큰뿐이다. 화면 쪽 같은 규칙 = membership.html
    _isExternalLessonSport() — 둘 중 하나를 고치면 다른 쪽도 같이 고칠 것.
    """
    return "뮤지컬" in str(sport or "")


def lesson_unassigned_summary(days: int = 30) -> dict | None:
    """최근 N일 강습 미응대(흔적 0) 집계 — 일과 정리용. 전 기간이 아니라 '지금 손쓸 수 있는'
    최근분만 센다(3~4개월 전 건까지 매일 세면 숫자가 굳어 무감각해진다).
    실패 시 None(미측정 — 0으로 날조하지 않는다)."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    total, by_type, ok_any = 0, {}, False
    # 전체 재고(기간 무제한)와 '가장 오래된 순' 목록도 함께 낸다(2026-07-25 GM 확정).
    #   최근 N일만 세던 탓에 30일이 지난 건은 어느 화면·지표에도 안 나타났다 —
    #   실측 377건(성인 188·유소년 189), 가장 오래된 2021-10-30. 숨은 재고가 되는 게 문제라
    #   ①숫자는 한 줄에 괄호로 병기하고 ②처리는 '오늘 할 일'에 매일 조금씩만 흘려보낸다.
    #   별도 목록·별도 화면은 만들지 않는다(볼 곳만 늘고 아무도 안 본다 — GM 지시).
    total_all, oldest, total_external = 0, [], 0
    for t in _LESSON_TYPES:
        rows = fetch_lesson_inquiries(t)
        if rows is None:
            by_type[t] = None
            continue
        ok_any = True
        cands = unassigned_lesson_candidates(rows)
        recent = [r for r in cands if _lesson_date_str(r.get("timestamp")) >= cutoff]
        by_type[t] = len(recent)
        total += len(recent)
        total_all += len(cands)
        for r in cands:
            d = _lesson_date_str(r.get("timestamp"))
            if is_external_lesson(r.get("sport")):
                total_external += 1
                continue   # 우리 실무진이 컨택할 몫이 아니다 — '오래된 순' 목록에는 넣지 않는다
            if d:
                oldest.append({"date": d, "type": t, "name": str(r.get("name") or "").strip(),
                                "sport": str(r.get("sport") or "").strip()})
    if not ok_any:
        return None
    oldest.sort(key=lambda x: x["date"])
    return {"days": days, "total": total, "by_type": by_type,
            "total_all": total_all, "total_external": total_external,
            "total_ours": total_all - total_external, "oldest": oldest[:5]}


_MONTH_ABBR = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
               "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _lesson_date_str(v) -> str:
    """강습 timestamp를 'YYYY-MM-DD'로. 시트가 값을 Date로 자동 변환해 두 포맷이 섞여 들어온다
    ('2026-07-23 …' / 'Wed Jul 23 2026 …') — 둘 다 인식. 못 읽으면 '' (비교에서 자동 탈락)."""
    s = str(v or "").strip()
    m = re.search(r"(\d{4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\w{3} (\w{3}) (\d{1,2}) (\d{4})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), _MONTH_ABBR.get(m.group(1), 0), int(m.group(2)))
    return ""


def fetch_cpo_today_stats() -> dict | None:
    return _gas_get("cpo_today_stats")


def fetch_cpo_churn_stats() -> dict | None:
    return _gas_get("cpo_churn_stats")


def fetch_member_registered_list(date_from: str, date_to: str, new_only: bool = False) -> list[dict] | None:
    """유효회원 시트 등록일자 기준 원본 행(member_registered_list, 화면 '멤버십 신규 등록현황'과 동일 소스).
    new_only=True → 서버가 신규만 필터(_isNewRegistration_, cpo_today_stats 카드와 동일 판정 — 배361).
    실패 시 None. 배312(2026-08-08) — 주간 보고 '이번 주 등록·LOSS' 신규/재등록 집계용."""
    params = {"from": date_from, "to": date_to}
    if new_only:
        params["newOnly"] = "1"
    data = _gas_get("member_registered_list", params, timeout=60)
    if data is None:
        return None
    return data.get("data", [])


def fetch_lesson_roster(lesson_type: str) -> list[dict] | None:
    """강습(성인·유소년) 등록완료(SUC) 회원 명단(lesson_registered_roster) — 화면 '강습 회원 관리'
    탭과 동일 소스. 행에 owner/contacts/status 필드 포함(membership.html _lessonMemGapOf가 그대로
    읽는 필드 — 데이터 완성도 판정 재사용). 실패 시 None. 배312(2026-08-08)."""
    data = _gas_get("lesson_registered_roster", {"type": lesson_type}, timeout=60)
    if data is None:
        return None
    return data.get("roster", [])


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _is_active_status(status: str) -> bool:
    """진행상태가 이탈·전환(가입) 어느 쪽도 아닌 '진행중' 상태인지. 신규 상태값이 추가돼도
    LOSS/SUC 계열이 아니면 활성으로 보는 포괄 정의(값 하드코딩 최소화)."""
    s = str(status or "").strip()
    if _is_closed_status(s):
        return False  # 배9597 — 해소·취소로 끝난 문의는 활성 아님(액션카드 제외)
    return bool(s) and s not in _LOSS_STATUSES and s not in _SUCCESS_STATUSES


def _phone_key(v) -> str:
    """전화번호 대조키 — 숫자만 남긴다(하이픈·공백·국가번호 표기 차이 흡수)."""
    return re.sub(r"\D", "", str(v or ""))


def suc_missing_from_member_list(rows: list[dict], grace_days: int = 1) -> dict | None:
    """등록(SUC) 처리됐는데 회원 명단(유효+법인)에 없는 건.

    ★왜 여기 있나(2026-08-10 시포 · GM 지적).
    종전엔 GAS(Survey.js)가 SUC 로 바뀌는 **그 순간** 텔레그램으로 "회원 명단 미반영"을 쐈다.
    그런데 등록은 저장이 두 번으로 갈린다 — ①진행상태를 SUC 로 ②곧이어 뜨는 '등록 종목' 모달 저장.
    ①에서 알림이 나가고 ②로 몇 초 뒤 정상 반영되므로, **정상 흐름마다 경보가 울렸다**
    (유선영님 건 — GM 이 "종목 등록돼 명단에 있는데?" 라고 지적). 즉시 알림은 그래서 뺐다.
    대신 하루가 지나도 여전히 안 들어간 건만 이 일일 점검이 잡는다 — 새 장치를 만들지 않고
    이미 매일 도는 문의 일일 액션에 한 칸 붙인다(약속 L21).

    grace_days: 오늘 막 등록한 건은 아직 종목 저장 중일 수 있어 뺀다(기본 1일).
    반환 None = 조회 실패(0 으로 위장하지 않는다).
    """
    valid = fetch_active_members("valid")
    corp = fetch_active_members("corp")
    if valid is None or corp is None:
        return None

    have = set()
    for m in list(valid) + list(corp):
        for k, v in m.items():
            if "휴대폰" in str(k) or "연락처" in str(k):
                key = _phone_key(v)
                if key:
                    have.add(key)

    cutoff = (datetime.now().date() - timedelta(days=grace_days)).isoformat()
    missing = []
    for r in rows:
        if str(r.get("status") or "").strip() not in _SUCCESS_STATUSES:
            continue
        ts = str(r.get("timestamp") or "")
        if ts and ts > cutoff:
            continue  # 오늘·어제 건은 아직 종목 저장 중일 수 있다
        key = _phone_key(r.get("phone"))
        if key and key not in have:
            missing.append({"name": r.get("name") or "이름미상",
                            "phone": r.get("phone") or "",
                            "date": ts})
    missing.sort(key=lambda x: x["date"])
    return {"total": len(missing), "oldest": missing[:3], "rows": missing}


# ── 라이프사이클 분류기 (일일 보고 3종 소스) ──────────────────────────────────
def uncontacted_candidates(rows: list[dict]) -> list[dict]:
    """연락이력(contacts) 0건 + 진행상태 활성 — 아직 한 번도 컨택 기록이 없는 후보."""
    return [r for r in rows if not r.get("contacts") and _is_active_status(r.get("status"))]


def todays_reservations(rows: list[dict], today: str) -> list[dict]:
    """오늘 날짜 상담·체험 예약 보유 문의자(reservations[].date == today)."""
    out = []
    for r in rows:
        if _is_closed_status(r.get("status")):
            continue  # 배9597 — 해소·취소로 끝난 문의의 예약은 오늘 액션이 아니다
        for res in (r.get("reservations") or []):
            if res.get("date") == today:
                out.append({**r, "_res_time": res.get("time", "")})
                break
    return out


def churn_risk_candidates(rows: list[dict], today: str, stale_days: int = 14) -> list[dict]:
    """이탈위험 후보(휴리스틱·추정) — 최초 문의(timestamp) 기준 stale_days일+ 경과,
    진행상태 활성, 미래 예약 없음. **정직 표기**: 연락메모 텍스트 안 날짜는 구조화 데이터가
    아니라 파싱하지 않음 — '최초 문의일' 기준 근사치이며 실제 마지막 컨택일 기준 실측이 아니다."""
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=stale_days)).strftime("%Y-%m-%d")
    out = []
    for r in rows:
        if not _is_active_status(r.get("status")):
            continue
        ts = r.get("timestamp", "")
        if not ts or ts > cutoff:
            continue
        has_future_res = any((res.get("date") or "") >= today for res in (r.get("reservations") or []))
        if has_future_res:
            continue
        out.append(r)
    return out


# ── 공용 헤더 (타 C-Level 재사용 가능 — 아이콘·라벨·타이틀만 교체) ────────────
def render_header(icon: str, clevel_label: str, title: str, date_str: str) -> str:
    weekday = _WEEKDAY_KOR[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    return f"{icon} [{clevel_label}] {title}\n{date_str}({weekday})"


# ── 일일 보고 (실무진 문의방) — "오늘 처리할 것" ────────────────────────────
def build_daily_report(today: str | None = None) -> str:
    today = today or _today_str()
    header = render_header("📋", "AI CPO-시포", "오늘 처리할 것", today)

    rows = fetch_member_inquiries()
    if rows is None:
        return f"{header}\n\n⚠️ 데이터 없음 — 문의 데이터 조회 실패(GAS 응답 없음). 잠시 후 재시도됩니다.\n\n{_AUTO_FOOTER}"

    today_new = [r for r in rows if r.get("timestamp") == today]
    uncontacted = uncontacted_candidates(rows)
    todays_res = todays_reservations(rows, today)
    churn_cands = churn_risk_candidates(rows, today)

    lines = [header, ""]

    lines.append(f"① 오늘 신규 문의 {len(today_new)}건")
    if not today_new:
        lines.append("  없음")
    for r in today_new[:8]:
        lines.append(f"  · {r.get('name') or '(이름없음)'} / {r.get('channel') or '채널미상'}")
    if len(today_new) > 8:
        lines.append(f"  …외 {len(today_new) - 8}건")

    lines.append("")
    lines.append(f"② 미컨택 문의(연락기록 0건) {len(uncontacted)}건")
    if not uncontacted:
        lines.append("  없음")
    for r in uncontacted[:8]:
        lines.append(f"  · {r.get('name') or '(이름없음)'} / 접수 {r.get('timestamp') or '-'}")
    if len(uncontacted) > 8:
        lines.append(f"  …외 {len(uncontacted) - 8}건")

    lines.append("")
    lines.append(f"③ 오늘 상담·체험 예약 {len(todays_res)}건")
    if not todays_res:
        lines.append("  데이터 없음(오늘 예약 없음)")
    for r in todays_res[:8]:
        lines.append(f"  · {r.get('_res_time') or '시간미정'} {r.get('name') or '(이름없음)'}")

    lines.append("")
    lines.append(f"④ LOSS 예방 대상(추정) {len(churn_cands)}건" + (" — 👉 후속 연락 필요" if churn_cands else ""))
    lines.append(f"  ※ 정직 꼬리표: 최초 문의일 기준 {14}일+ 무진전 근사치 — 연락메모 내 날짜는 미반영(구조화 데이터 아님), 실측 아님")
    for r in churn_cands[:5]:
        lines.append(f"  · {r.get('name') or '(이름없음)'} / 최초문의 {r.get('timestamp') or '-'}")
    if len(churn_cands) > 5:
        lines.append(f"  …외 {len(churn_cands) - 5}건")

    lines.append("")
    lines.append(_AUTO_FOOTER)
    return "\n".join(lines)


# ── 주간 보고 (GM 채널) — 현황 롤업 ─────────────────────────────────────────
def build_weekly_report(today: str | None = None) -> str:
    today = today or _today_str()
    header = render_header("📊", "AI CPO-시포", "주간 현황 롤업(GM)", today)

    rows = fetch_member_inquiries()
    churn = fetch_cpo_churn_stats()

    if rows is None:
        return f"{header}\n\n⚠️ 데이터 없음 — 문의 데이터 조회 실패(GAS 응답 없음).\n\n{_AUTO_FOOTER}"

    week_start = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    week_rows = [r for r in rows if (r.get("timestamp") or "") >= week_start]

    channel_count: dict[str, int] = {}
    converted = 0
    for r in week_rows:
        ch = r.get("channel") or "채널미상"
        channel_count[ch] = channel_count.get(ch, 0) + 1
        if str(r.get("status", "")) in _SUCCESS_STATUSES:
            converted += 1

    conv_rate = f"{round(converted / len(week_rows) * 100, 1)}%" if week_rows else "데이터 없음(표본 0건)"
    churn_cands = churn_risk_candidates(rows, today)

    lines = [header, ""]
    lines.append(f"신규문의 {len(week_rows)}건 (최근 7일 · {week_start}~{today})")
    lines.append(f"문의→등록 전환 {converted}건 · 전환율 {conv_rate}")
    lines.append("")
    lines.append("채널별 유입 (최근 7일):")
    if not channel_count:
        lines.append("  데이터 없음")
    else:
        for ch, c in sorted(channel_count.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  · {ch}: {c}건")
    lines.append("")
    if churn is not None:
        lines.append(
            f"LOSS 현황(누적): LOSS율 {churn.get('lossRate', '-')}% · "
            f"당월 LOSS {churn.get('monthLossCount', '-')}건"
        )
    else:
        lines.append("LOSS 현황: 데이터 없음(조회 실패)")
    lines.append(f"LOSS 예방 대상(추정) {len(churn_cands)}건" + (" — 👉 후속 연락 필요" if churn_cands else ""))
    lines.append("")
    lines.append("※ 정직 표기: 전환율은 표본기간(최근 7일 접수건) 기준 근사 — 진행 중인 건은 향후 전환될 수 있어 최종치 아님")
    lines.append(_AUTO_FOOTER)
    return "\n".join(lines)


# ── 월간 보고 (GM 채널) — 현황 롤업 ─────────────────────────────────────────
def build_monthly_report(today: str | None = None) -> str:
    today = today or _today_str()
    header = render_header("📈", "AI CPO-시포", "월간 현황 롤업(GM)", today)

    today_stats = fetch_cpo_today_stats()
    churn = fetch_cpo_churn_stats()
    rows = fetch_member_inquiries()

    if today_stats is None and churn is None and rows is None:
        return f"{header}\n\n⚠️ 데이터 없음 — 전체 소스 조회 실패.\n\n{_AUTO_FOOTER}"

    lines = [header, ""]

    if today_stats is not None:
        mi = today_stats.get("monthInquiry")
        mr = today_stats.get("monthReg")
        ml = today_stats.get("monthLoss")
        conv = "데이터 없음(측정 준비 중)"
        if isinstance(mi, (int, float)) and mi > 0 and isinstance(mr, (int, float)):
            conv = f"{round(mr / mi * 100, 1)}%(근사)"
        lines.append(f"이번달 신규문의 {mi if mi is not None else '-'}건 · 신규등록 {mr if mr is not None else '-'}건 · 문의→가입 전환율 {conv}")
        lines.append(f"이번달 LOSS {ml if ml is not None else '-'}건")
    else:
        lines.append("이번달 문의·등록 집계: 데이터 없음(조회 실패)")

    lines.append("")
    if rows is not None:
        month = today[:7]
        month_res = 0
        for r in rows:
            for res in (r.get("reservations") or []):
                if str(res.get("date", "")).startswith(month):
                    month_res += 1
        lines.append(f"이번달 상담·체험 예약 활성 {month_res}건")
    else:
        lines.append("예약 활성 건수: 데이터 없음(조회 실패)")

    lines.append("")
    if churn is not None:
        lines.append(
            f"LOSS 방지 성과: 유효회원 {churn.get('activeCount', '-')}명 · "
            f"당월 LOSS율 {churn.get('monthLossRate', '-')}% · "
            f"30일내 갱신임박 {churn.get('renewCount', '-')}명"
        )
    else:
        lines.append("LOSS 방지 성과: 데이터 없음(조회 실패)")

    lines.append("")
    lines.append("※ 정직 표기: 신규문의 대비 신규등록 전환율은 서로 다른 코호트(이번달 접수 vs 이번달 등록)의 근사치 — 등록자가 반드시 이번달 문의자는 아님. 정밀 전환율은 kpi_values.json '이번달_전환율'(등록일 기준) 축적 후 대체 예정.")
    lines.append(_AUTO_FOOTER)
    return "\n".join(lines)


# ── 발신 + 상태 기록 ─────────────────────────────────────────────────────────
def _send_telegram(chat_id: int, text: str) -> bool:
    if not TELEGRAM_TOKEN:
        return False
    return _tg_send(TELEGRAM_TOKEN, chat_id, text, source="cpo_report._send_telegram", timeout=15)


def _write_state(kind: str, chat_label: str, ok: bool, sent: bool, detail: str = "") -> None:
    """status/cpo_report_state.json — ERP 노출용(카톡전송관리.html status/kakao_last_send.json 과 동일 패턴)."""
    state: dict = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    state[kind] = {
        "ok": ok,
        "sent": sent,
        "chat": chat_label,
        "live_gate": report_live_enabled(),
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "detail": detail,
    }
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_BUILDERS = {"daily": build_daily_report, "weekly": build_weekly_report, "monthly": build_monthly_report}
_TARGETS = {
    "daily": (INQUIRY_CHAT_ID, "문의알림방"),
    "weekly": (GM_CHAT_ID, "GM채널"),
    "monthly": (GM_CHAT_ID, "GM채널"),
}


def run(kind: str, dry_run: bool = True) -> str:
    """kind: 'daily'|'weekly'|'monthly'.
    dry_run=True → 무조건 렌더만(발신 안 함).
    dry_run=False 라도 report_live_enabled()==False 면 발신하지 않는다(이중 안전장치 —
    개발 중 실무진 라이브 방에 테스트 메시지 발신 금지 가드레일)."""
    if kind not in _BUILDERS:
        raise ValueError(f"unknown kind: {kind}")

    text = _BUILDERS[kind]()
    chat_id, chat_label = _TARGETS[kind]
    live = report_live_enabled()

    if dry_run or not live:
        _write_state(kind, chat_label, ok=True, sent=False, detail="dry-run 또는 게이트 OFF — 렌더만, 발신 안 함")
        return text

    ok = _send_telegram(chat_id, text)
    _write_state(kind, chat_label, ok=ok, sent=ok, detail="실발신 성공" if ok else "실발신 실패")
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CPO 일/주/월 자동보고 생성기 (dry-run 기본)")
    parser.add_argument("--kind", choices=["daily", "weekly", "monthly", "all"], default="all")
    parser.add_argument("--send", action="store_true", help="실발신 시도(게이트 OFF면 여전히 렌더만)")
    args = parser.parse_args()

    kinds = ["daily", "weekly", "monthly"] if args.kind == "all" else [args.kind]
    for k in kinds:
        print(f"===== {k} =====")
        print(run(k, dry_run=not args.send))
        print()
