# -*- coding: utf-8 -*-
"""GM 신규 스트림 #3 '매출 및 운영+인사 현황 보고' — v3 (2026-07-21 GM 피드백 반영: 압축).

목적: GM이 매일 매출 이미지에 손으로 옮겨 적어온 '인사&파트너팀 진행사항 + 핵심 보고·
진행현황'을 업무 SSOT(G1 항로 · SSOT_API_URL action=todo_list)에서 자동 조립해 수기입력을
대체할 수 있는지 실데이터로 검증하는 시안. 매출 숫자는 별도 파이프라인(카톡 이미지 자동)
이라 이 스크립트 범위 밖 — placeholder로 명시하고 지어내지 않는다.

승인 전까지는 daily_scheduler.py 라이브 파이프라인과 완전히 분리된 독립 스크립트다 —
daily_scheduler.py는 import/수정하지 않는다(PID락·토큰 미설정 시 sys.exit 부작용 위험).

데이터: scripts/collectors/ops_shared.py 의 SSOT_API_URL·gas_get·TODO_DONE_STATUSES 재사용
(중복정의 금지). action=todo_list.

★실측 필드(2026-07-21 실호출로 확인 — 추측 아님):
  id·업무명·카테고리·담당자·시작일·종료일·내용·상태·결재요청·링크·파일URL·생성자·생성일·
  수정일·부서장싸인·GM싸인·대표싸인·결재상태·결재완료시각·결과보고서URL·난이도·완료일·결재의견
  상태 실측 어휘(117건 중) = 완료(64)·진행중(47)·보류(5) + 드물게 인코딩 깨진 테스트 잔재
  1~2건(업무명/상태에 유니코드 대체문자 � 포함) → _is_garbled()로 필터.
  카테고리 실측(2026-07-21 재확인) = "[1] 매출 및 영업"·"[2] 인사"·"[3] 파트너팀"·
  "[4] 운영 정책"·"[5] 시설 및 환경"·"[6] 회원·CS"·"[7] IT·시스템·자동화"·
  "[8] 교육·조직문화"·"[9] 회의" (+ 일부 공백 2건 → 🗂 미분류로 정직 표기, 임의 배정 금지).
  결재요청 실측값 = ""(95)·"GM"(14)·"나우열M,GM"(3)·"이경연 실장,GM"(2)·"GM,대표님"(2)·
  "이정헌 소장"(1). 결재상태 실측값 = ""(94)·"결재완료"(17)·"대기"(5)·"GM 반려"(1).
  → "결재요청 있음 & 결재상태 != 결재완료" = GM 결재 대기(2026-07-21 실호출 5건 전부 '대기').

마감 초과 판정: 종료일 ISO 문자열의 날짜부(앞 10자)를 오늘 날짜와 직접 문자열 비교한다.
KST 변환은 하지 않음 — build_work_block()이 수정일 필드를 동일하게 원문 그대로
startswith 비교하는 기존 선례를 그대로 따름(과설계 방지). 하루 안팎 오차 가능성 있는
근사치임을 인지하고 사용.

★v2 변경(2026-07-21 GM 피드백):
  1) 각 건에 종료일 D-day 표기(~MM/DD(D±n)), 종료일 없으면 '일정미정'.
  2) 지연(종료일<오늘 & 활성) 건을 맨 위 '⏰ 지연' 별도 목록으로 분리(카테고리 목록에서는 제외).
  3) 활성 업무 전부를 카테고리 실측값 그대로 9개 섹션으로 분리 렌더('운영'으로 뭉치지 않음).
     담당자는 _short_owner()로 콤마구분 이름 전부 '·'로 노출(축약·인원수 뭉개기 금지).
  4) GM 전용 2섹션 추가: 📋 결재 현황(결재요청 있는데 결재상태 미완인 건) · 🎯 분기 운영 목표
     (status/monthly_ops_plan.json → strategy_roadmap.items 중 quarter 문자열의 (N~M월)
     구간에 오늘 월이 포함되는 항목을 실측 렌더. 파일/키 없거나 매칭 항목 없으면
     '[분기 운영 목표: 연동 예정]' placeholder로 정직 표기 — 지어내기 금지).

★v3 변경(2026-07-21 GM 피드백 "너무 길다, 조금 정리해달라" — 렌더 압축, 데이터소스·판정
로직은 v2 그대로 재사용):
  1) 진행 현황: 활성 업무 전체 나열(9섹션 리스트) 삭제 → 카테고리별 **건수** 한 줄 요약으로
     대체(_COUNT_LABEL_MAP). 0건 카테고리는 줄에서 생략.
  2) ⏳ 임박(D-7 이내, 지연 아님) 리스트를 신설해 진행 현황 아래에 추가 — 액션이 임박한 건만
     별도로 보이게 한다(_delta_days()).
  3) 지연·결재 대기 각 줄에서 말미 [상태] 태그 제거(줄당 정보 밀도 압축).
  4) 지연 D-day 표기에서 "(D+n 초과)" → "(D+n)"으로 축약(_dday_label()).
  5) 맨 위에 "■ 업무 총 N · 진행중 a·보류 b | ⏰지연 k · 📋결재대기 m" 한눈 요약 라인 추가,
     완료(오늘) 카운트는 요약에서 제외(별도 요청 없어 압축).
  6) 🎯 분기 운영 목표: <pre> 박스·출처 경로 문구 제거, "· 제목 — 진행 N%" 한 줄 리스트로 축약.
  7) 맨 아래 "· 전체 항목 상세는 업무 SSOT 페이지 / 상세판 원하면 말씀" 안내 1줄 추가.
  텔레그램 4096자 제한: build_digest()가 블록 단위로 잘라 리스트[str]를 반환, 여러 메시지로
  분할 발송한다(블록 중간에서 <pre> 깨지지 않게 블록 경계에서만 자름).

발신: scripts/publish_digest.py 의 _load_env_val("TELEGRAM_BOT_TOKEN") 재사용(자기완결,
부작용 없음). <pre> 정렬을 위해 parse_mode=HTML 필요 — publish_digest._send()는 parse_mode
미지원이라 이 파일 안에서 requests.post로 직접 sendMessage.

★ 대상 chat_id = 8254867551(GM 업무보고방) 고정 — 다른 방 발송 금지.
★ git add/commit 금지(테스트 시안).
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import SSOT_API_URL, TODO_DONE_STATUSES, gas_get  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

GM_CHAT_ID = "8254867551"  # GM 개인 업무보고방(@namuki_report_bot) — 고정, override 불가

_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]

TELEGRAM_MSG_LIMIT = 4096

MONTHLY_OPS_PLAN_PATH = REPO_ROOT / "status" / "monthly_ops_plan.json"

# 카테고리 실측값 → GM 요청 9섹션 라벨(제시된 순서 그대로).
_CATEGORY_ORDER = [
    ("[2] 인사", "🧑‍💼 인사"),
    ("[3] 파트너팀", "🤝 파트너팀"),
    ("[4] 운영 정책", "🏢 운영정책"),
    ("[5] 시설 및 환경", "🏗 시설·환경"),
    ("[6] 회원·CS", "👥 회원·CS"),
    ("[7] IT·시스템·자동화", "💻 IT·자동화"),
    ("[8] 교육·조직문화", "📚 교육·조직문화"),
    ("[9] 회의", "🗓 회의"),
    ("[1] 매출 및 영업", "💰 매출·영업"),
]
_UNCATEGORIZED_LABEL = "🗂 미분류"

# v3: 진행 현황 압축용 — 카테고리 긴 라벨(_CATEGORY_ORDER 두 번째 값) → 건수 줄 짧은 라벨.
_COUNT_LABEL_MAP: dict[str, str] = {
    "🧑‍💼 인사": "🧑‍💼인사",
    "🤝 파트너팀": "🤝파트너팀",
    "🏢 운영정책": "🏢운영정책",
    "🏗 시설·환경": "🏗시설",
    "👥 회원·CS": "👥회원CS",
    "💻 IT·자동화": "💻IT",
    "📚 교육·조직문화": "📚교육",
    "🗓 회의": "🗓회의",
    "💰 매출·영업": "💰매출영업",
    _UNCATEGORIZED_LABEL: "🗂미분류",
}
_COUNT_LABEL_ORDER = [label for _, label in _CATEGORY_ORDER] + [_UNCATEGORIZED_LABEL]

# 결재상태 실측 완료 어휘(2026-07-21 확인) — 이 외(대기·GM 반려·공백)는 전부 미완 취급.
_APPROVAL_DONE_STATUSES = {"결재완료"}

_QUARTER_RANGE_RE = re.compile(r"\((\d+)~(\d+)월\)")


def _is_garbled(s: str) -> bool:
    """GAS 응답에 드물게 섞이는 인코딩 깨진 테스트 잔재 행 필터(실측: 유니코드 대체문자)."""
    return "�" in s


def _fetch_todo() -> list[dict]:
    resp = gas_get(SSOT_API_URL, params={"action": "todo_list"}, timeout=40, label="ops-mgmt-digest")
    if resp is None:
        return []
    data = resp.json()
    if not data.get("ok"):
        return []
    items = data.get("data", [])
    return [
        x for x in items
        if not _is_garbled(str(x.get("업무명", "")))
        and not _is_garbled(str(x.get("상태", "")))
    ]


def _category_label(item: dict) -> str:
    cat = str(item.get("카테고리", "")).strip()
    for raw, label in _CATEGORY_ORDER:
        if cat == raw:
            return label
    return _UNCATEGORIZED_LABEL


def _short_owner(owner: str) -> str:
    """담당자 전원 그대로 노출('외 N인' 축약 금지 — GM 피드백)."""
    names = [n.strip() for n in str(owner or "").split(",") if n.strip()]
    return "·".join(names) if names else "담당미정"


def _short_title(title: str, n: int = 26) -> str:
    t = str(title or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def _due_date10(item: dict) -> str:
    return str(item.get("종료일", "") or "")[:10]


def _is_overdue(item: dict, today: str) -> bool:
    due = _due_date10(item)
    if not due:
        return False
    return due < today


def _delta_days(due10: str, today: str) -> int | None:
    """due10 - today 일수 차이. 파싱 불가/공백이면 None."""
    if not due10:
        return None
    try:
        d_due = datetime.strptime(due10, "%Y-%m-%d")
        d_today = datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        return None
    return (d_due - d_today).days


def _dday_label(due10: str, today: str) -> str:
    """~MM/DD(D±n) 형식. due10 비어있으면 '일정미정'. (v3: 지연 표기 "D+n 초과"→"D+n" 축약)"""
    if not due10:
        return "일정미정"
    delta = _delta_days(due10, today)
    if delta is None:
        return f"~{due10[5:7]}/{due10[8:10]}"
    mmdd = f"{due10[5:7]}/{due10[8:10]}"
    if delta < 0:
        return f"~{mmdd}(D+{-delta})"
    if delta == 0:
        return f"~{mmdd}(D-day)"
    return f"~{mmdd}(D-{delta})"


def _is_pending_approval(item: dict) -> bool:
    req = str(item.get("결재요청", "")).strip()
    if not req:
        return False
    status = str(item.get("결재상태", "")).strip()
    return status not in _APPROVAL_DONE_STATUSES


def _load_quarter_goals(today: str) -> str:
    """status/monthly_ops_plan.json → strategy_roadmap.items 중 오늘 월이 포함된
    quarter 구간 항목 렌더. 파일/키 없거나 매칭 없으면 정직 placeholder.
    (v3: <pre> 박스·출처 경로 문구 제거 — "· 제목 — 진행 N%" 한 줄 리스트로 압축)"""
    placeholder = "🎯 분기 운영 목표\n[분기 운영 목표: 연동 예정]"
    try:
        plan = json.loads(MONTHLY_OPS_PLAN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return placeholder
    items = plan.get("strategy_roadmap", {}).get("items", [])
    month = int(today[5:7])
    matched: list[dict] = []
    for it in items:
        q = str(it.get("quarter", "") or "")
        m = _QUARTER_RANGE_RE.search(q)
        if not m:
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= month <= hi:
            matched.append(it)
    if not matched:
        return placeholder
    lines = ["🎯 분기 운영 목표"]
    for it in matched:
        title = html.escape(str(it.get("title", "")))
        progress = it.get("progress", "")
        lines.append(f"· {title} — 진행 {progress}%")
    return "\n".join(lines)


def _chunk_blocks(blocks: list[str], limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """블록(문단) 단위로 텔레그램 4096자 제한에 맞춰 메시지를 분할한다.
    블록 중간에서 자르지 않아 <pre> 태그가 깨지지 않는다."""
    messages: list[str] = []
    current = ""
    for b in blocks:
        candidate = f"{current}\n\n{b}" if current else b
        if len(candidate) > limit and current:
            messages.append(current)
            current = b
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


def build_staff_feedback_block(today: str) -> str:
    """💬 실무진 피드백 — 오늘 접수분과 아직 안 끝난 건을 「하루 일과 정리」 안에 한 블록으로 접는다.

    GM 지시 2026-08-06: "문의 접수랑 같은 맥락으로 진행 — 접수 시 즉각 알림 + 처리 완료 시
    메모랑 같이 알림 + 하루 일과 정리에도 추가." 앞의 둘은 GAS(Survey.js)가 문의알림방으로
    보내고, 이 함수가 셋째다.

    ★새 알림을 만들지 않는다(GM 지시 2026-08-06 "텔레그램 알림 계속 오는 그런건 하지말아줘").
    이미 나가는 「하루 일과 정리」 한 통 안에 몇 줄을 얹을 뿐이라 발신 건수는 그대로다.

    소스·토큰은 cpo_staff_feedback_watch 의 것을 그대로 재사용한다(주소를 두 벌로 두지 않는다·약속 L01).
    조회 실패는 정직하게 '측정 불가'로 적고 넘어간다 — 이 블록 하나 때문에 하루 정리 전체가
    죽으면 안 된다.
    """
    try:
        from collectors.cpo_staff_feedback_watch import FB_GAS_URL, FB_TOKEN
        import urllib.parse
        import urllib.request

        q = urllib.parse.urlencode({"action": "staff_feedback_list", "t": FB_TOKEN})
        with urllib.request.urlopen(FB_GAS_URL + "?" + q, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = data.get("data") or data.get("rows") or []
        if not data.get("ok"):
            raise RuntimeError(str(data.get("error") or "응답 실패"))
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 블록만 정직 표기하고 계속 간다
        return f"💬 실무진 피드백\n측정 불가 — 조회 실패({type(exc).__name__})"

    # 접수ID = FByyMMdd-HHmmss. 날짜 비교는 이 앞자리로만 한다(접수시각 문자열 서식이 시트마다 흔들린다).
    ymd = today[2:].replace("-", "")   # 2026-08-06 -> 260806
    todays = [r for r in rows if str(r.get("접수ID", "")).startswith("FB" + ymd)]
    open_rows = [r for r in rows if "처리완료" not in str(r.get("처리상태", ""))]
    done_today = [r for r in todays if "처리완료" in str(r.get("처리상태", ""))]

    head = (
        f"💬 실무진 피드백  오늘 접수 {len(todays)} · "
        f"오늘 처리완료 {len(done_today)} · 아직 안 끝난 것 {len(open_rows)}"
    )
    if not open_rows:
        return head + "\n남은 건 없음."

    # 오래된 것부터 — 며칠 묵었는지가 실무진 신뢰를 깎는 정도다.
    open_rows.sort(key=lambda r: str(r.get("접수ID", "")))
    lines = []
    for r in open_rows[:8]:
        who = html.escape(str(r.get("작성자", "")).strip() or "무기명")
        body = html.escape(_short_title(str(r.get("내용", "")).replace("\n", " "), 34))
        state = html.escape(str(r.get("처리상태", "")).strip() or "접수")
        rid = str(r.get("접수ID", ""))
        day = rid[6:8] if len(rid) >= 8 else ""
        mon = rid[4:6] if len(rid) >= 6 else ""
        when = f"{int(mon)}/{int(day)}" if mon.isdigit() and day.isdigit() else "?"
        lines.append(f"· {when} · {who} · {body} · {state}")
    more = f"\n· 외 {len(open_rows) - 8}건" if len(open_rows) > 8 else ""
    return head + "\n<pre>\n" + "\n".join(lines) + more + "\n</pre>"


def _today_changes_block(items, active, overdue, pending_approval, today: str) -> str:
    """어제와 달라진 것만 — 오늘 새로 지연된 것 · 어제 끝난 것.

    [2026-08-29 GM 지시 · 텔레그램 중복 정리] 「📅 오늘 잡힌 일정」 절 삭제 — 같은 일정이
    하루 다섯 번(06시·08시·09:30·20:30·23시) 나열되고 있었다. 일정 나열은 08시
    「오늘의 항로」 한 곳만 남긴다(_schedule_today 헬퍼도 여기뿐이라 같이 지움)."""
    yday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    newly = [x for x in overdue if _delta_days(_due_date10(x), today) == -1]
    done_yday = [x for x in items
                 if str(x.get("상태", "")).strip() in TODO_DONE_STATUSES
                 and str(x.get("수정일", "") or x.get("updatedAt", ""))[:10] == yday]
    lines = ["🆕 어제와 달라진 것"]
    if newly:
        names = " · ".join(f"{_short_owner(x.get('담당자',''))} {_short_title(x.get('업무명',''), 20)}"
                           for x in newly[:3])
        lines.append(f"· ⏰ 오늘 새로 지연 {len(newly)}건 — {html.escape(names)}"
                     + (f" 외 {len(newly)-3}건" if len(newly) > 3 else ""))
    else:
        lines.append("· ⏰ 오늘 새로 지연된 것 없음")
    if done_yday:
        names = " · ".join(_short_title(x.get("업무명", ""), 20) for x in done_yday[:3])
        lines.append(f"· ✅ 어제 끝낸 것 {len(done_yday)}건 — {html.escape(names)}"
                     + (f" 외 {len(done_yday)-3}건" if len(done_yday) > 3 else ""))
    else:
        lines.append("· ✅ 어제 끝낸 것 없음")
    return "\n".join(lines)


def build_digest(today: str | None = None, channel: str = "telegram") -> list[str]:
    """v3: 액션 필요한 항목(지연·임박·결재대기)만 리스트로 남기고, 진행현황 전체 나열은
    카테고리별 건수 요약으로 대체한다(GM 피드백 "너무 길다"). 데이터 소스·판정 로직은 v2 재사용.

    channel="kakao"(2026-08-05 GM 지시 — "현장 업무는 카카오톡으로, 카카오는 간단명확하게"):
    실무진 카카오(★운영부)에는 담당자 이름이 붙어 오늘 바로 움직일 수 있는 항목(⏰지연·⏳임박·
    📋결재대기)만 남기고, 개인에게 할 일을 지우지 않는 집계용 정보(🔧 카테고리별 건수·🎯 분기
    운영 목표 진행률)는 뺀다. channel 기본값은 "telegram"이라 기존 호출부(GM 개인 업무보고방)는
    100% 그대로 — 정보 소실 아님, 텔레그램에는 이 두 블록이 계속 그대로 나간다."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    header = f"🌙 하루의 마무리 — 매출·운영 {today}({weekday})\n📈 매출 및 운영+인사 현황 보고"
    # 2026-08-08 배446 — 여기가 7일 연속 '[연동 예정]' 문자열로 나갔다(텔레그램 + ★운영부 카톡).
    # 값은 home_kpi 스냅샷에 이미 있었고 판정·표기는 erp_status_publisher 한 곳이 한다(약속 L01).
    try:
        from erp_status_publisher import read_sales_month_display
        _s_text, _in_progress = read_sales_month_display()
    except Exception:
        _s_text, _in_progress = "—", False
    sales_line = f"■ 매출  {_s_text}{' (진행 중)' if _in_progress else ''}"

    items = _fetch_todo()
    if not items:
        return [
            f"{header}\n\n{sales_line}\n\n"
            "■ 업무 총 0건\n업무 SSOT(G1) 응답 없음 — 소스 확인 필요."
        ]

    active = [x for x in items if str(x.get("상태", "")).strip() not in TODO_DONE_STATUSES]
    in_progress = [x for x in active if str(x.get("상태", "")).strip() == "진행중"]
    standby = [x for x in active if str(x.get("상태", "")).strip() == "보류"]

    overdue = [x for x in active if _is_overdue(x, today)]
    overdue_ids = {id(x) for x in overdue}
    pending_approval = [x for x in items if _is_pending_approval(x)]

    summary_line = (
        f"■ 업무 총 {len(items)}건 · 진행중 {len(in_progress)}·보류 {len(standby)} | "
        f"⏰지연 {len(overdue)} · 📋결재대기 {len(pending_approval)}"
    )

    # ── 🆕 오늘 달라진 것 (GM 지적 2026-08-12 "새로운 내용이 없을까? 9시면 그래도 하루
    #    일과 정리하는 내용이 들어가야 할 것 같은데") ─────────────────────────────
    #   그 전 본문은 '지금 상태 스냅샷'이라 매일 거의 같은 그림이었다 — 지연 목록 14건 중
    #   대부분이 두 달 넘게 같은 자리에 있으니 훑어도 새 정보가 없었다. 그래서 맨 위에
    #   **어제와 달라진 것만** 세 줄로 올린다. 새 소스·새 발신 없음(이미 읽는 데이터 + 전사일정).
    changed_lines = _today_changes_block(items, active, overdue, pending_approval, today)

    # ⏰ 지연(일정 초과) — 종료일<오늘 & 활성. 최다 초과부터 정렬. (v3: [상태] 태그 제거)
    overdue_sorted = sorted(overdue, key=lambda x: _due_date10(x))
    if overdue_sorted:
        lines = []
        for x in overdue_sorted:
            owner = html.escape(_short_owner(x.get("담당자", "")))
            title = html.escape(_short_title(x.get("업무명", "")))
            due = html.escape(_dday_label(_due_date10(x), today))
            lines.append(f"· {owner} · {title} · {due}")
        section_overdue = (
            f"⏰ 지연 (일정 초과) {len(overdue_sorted)}건\n"
            "<pre>\n" + "\n".join(lines) + "\n</pre>"
        )
    else:
        section_overdue = "⏰ 지연 (일정 초과) 0건\n지연 건 없음."

    # 🔧 진행 현황 — v3: 전체 나열 삭제, 카테고리별 건수 한 줄 + 임박(D-7) 리스트만.
    buckets: dict[str, list[dict]] = {label: [] for label in _COUNT_LABEL_ORDER}
    for x in active:
        if id(x) in overdue_ids:
            continue
        buckets[_category_label(x)].append(x)

    count_parts = [
        f"{_COUNT_LABEL_MAP[label]} {len(buckets[label])}"
        for label in _COUNT_LABEL_ORDER
        if buckets[label]
    ]
    count_line = " · ".join(count_parts) if count_parts else "활성 건 없음"

    imminent = [
        x for x in active
        if id(x) not in overdue_ids
        and (d := _delta_days(_due_date10(x), today)) is not None
        and 0 <= d <= 7
    ]
    imminent_sorted = sorted(imminent, key=lambda x: _due_date10(x))
    if imminent_sorted:
        lines = []
        for x in imminent_sorted:
            owner = html.escape(_short_owner(x.get("담당자", "")))
            title = html.escape(_short_title(x.get("업무명", "")))
            due = html.escape(_dday_label(_due_date10(x), today))
            lines.append(f"· {owner} · {title} · {due}")
        imminent_body = "<pre>\n" + "\n".join(lines) + "\n</pre>"
    else:
        imminent_body = "임박 없음"

    imminent_section = f"⏳ 임박 (D-7 이내, 지연 아님)\n{imminent_body}"
    if channel == "kakao":
        section_progress = imminent_section  # 🔧 카테고리별 건수 집계는 텔레그램에만(개인 할일 아님)
    else:
        section_progress = (
            "🔧 진행 현황 (카테고리별 건수)\n"
            f"{count_line}\n"
            "※ 지연 제외 활성 건수.\n\n"
            f"{imminent_section}"
        )

    # 📋 결재 대기 — 결재요청 있는데 결재상태 미완인 건. (v3: [상태] 태그 제거)
    if pending_approval:
        lines = []
        for x in pending_approval:
            owner = html.escape(_short_owner(x.get("담당자", "")))
            title = html.escape(_short_title(x.get("업무명", ""), 30))
            req = html.escape(str(x.get("결재요청", "")).strip())
            lines.append(f"· {owner} · {title} · 요청:{req}")
        section_approval = (
            f"📋 결재 대기 {len(pending_approval)}건\n"
            "<pre>\n" + "\n".join(lines) + "\n</pre>"
        )
    else:
        section_approval = "📋 결재 대기 0건\n대기 중인 결재 없음."

    footer = "· 전체 항목 상세는 업무 SSOT 페이지 / 상세판 원하면 말씀"

    divider = "━━━━━━━━━━"

    # 💬 실무진 피드백 — 결재 대기 다음에 붙인다(GM 지시 2026-08-06 "하루 일과 정리에도 추가").
    #   자리를 여기로 잡은 이유: 위 세 블록은 업무 SSOT 기반이고 이건 실무진이 화면에서 직접
    #   올린 것이라, 섞지 않고 뒤에 따로 세운다.
    section_feedback = build_staff_feedback_block(today)

    blocks = [
        f"{header}\n\n{sales_line}\n{summary_line}\n\n{changed_lines}",
        section_overdue,
        f"{divider}\n{section_progress}",
        f"{divider}\n{section_approval}",
        f"{divider}\n{section_feedback}",
    ]
    if channel == "kakao":
        blocks.append(footer)  # 🎯 분기 운영 목표(진행률)는 텔레그램에만 — 오늘 할 일 아님
    else:
        section_quarter = _load_quarter_goals(today)
        blocks.append(f"{section_quarter}\n\n{footer}")
    return _chunk_blocks(blocks)


def send_test(text: str) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 미설정 — telegram_bot/.env 확인 필요")
    return _tg_send(token, GM_CHAT_ID, text, source="report_stream_3_impl.send_test",
                     extra={"parse_mode": "HTML"}, timeout=15)


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    messages = build_digest(today)
    print(f"=== 렌더된 메시지 ({len(messages)}개, 4096자 분할 적용) ===")
    for i, text in enumerate(messages, 1):
        print(f"--- 메시지 {i}/{len(messages)} ({len(text)}자) ---")
        print(text)
    print("=== 발송 결과 ===")
    for i, text in enumerate(messages, 1):
        result = send_test(text)
        print(f"메시지 {i}/{len(messages)}: {result}")


if __name__ == "__main__":
    main()
