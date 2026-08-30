# -*- coding: utf-8 -*-
"""GM 신규 밤 보고 '문의 및 컨택&등록 현황 보고' 첫 시안 — 독립 테스트 스크립트 (2026-07-21).

목적: GM 지정 신규 포맷을 오늘 실데이터로 렌더해 GM 개인 업무보고방(8254867551)에
1회 테스트 발송한다. 승인 전까지는 daily_scheduler.py 22:30 라이브 파이프라인과
완전히 분리된 독립 스크립트다 — daily_scheduler.py는 import/수정하지 않는다
(PID락·토큰 미설정 시 sys.exit 부작용이 있어 임포트 자체가 위험).

데이터: .deploy-funnel/Survey.js GAS(FUNNEL_EXEC_URL) 의 member_inquiry_list·
lesson_inquiry_list(type=성인강습/유소년강습) — scripts/collectors/ops_shared.py 재사용
(FUNNEL_EXEC_URL·gas_get 중복정의 금지).

판정 정본(cpo_report.py:51-52 = daily_scheduler.py:2708-2709 과 동일 기준):
- 등록 = status ∈ {SUC, 단기SUC} (강습은 "등록완료/등록/성공" 텍스트 상태도 등록으로 인정)
- 이탈/종결 = status ∈ {LOSS, 환불, 양도LOSS}
- 컨택 = contacts[] 비어있지 않음(≥1)
- 그 외 status 가 있는 값(예: "상담중" 등 실무진이 적어둔 진행 텍스트)은 그 값 그대로 라벨 사용
  — 새 상태 어휘를 발명하지 않고 시트에 있는 값을 정직하게 노출한다.

한계(정직 표기, 이번 시안 미해결): 멤버십 문의행에는 regProgram/lossReason 이 없어
등록 종목·이탈 사유는 강습(lesson) 쪽만 표시 가능 — 리스트 API 자체가 미포함.

발신: scripts/publish_digest.py 의 _load_env_val("TELEGRAM_BOT_TOKEN") 로 토큰만
재사용(자기완결 함수, 부작용 없음). <pre> 정렬 표를 위해 parse_mode=HTML 이 필요한데
publish_digest._send() 는 parse_mode 를 지원하지 않으므로, 전송은 이 파일 안에서
requests.post 로 직접 sendMessage(parse_mode="HTML") 한다.

★ 대상 chat_id 는 8254867551(GM 업무보고방) 로 고정 — 다른 방 발송 금지.
"""
from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import FUNNEL_EXEC_URL, gas_get  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402
try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

GM_CHAT_ID = "8254867551"  # GM 개인 업무보고방(@namuki_report_bot) — 고정, override 불가

_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]
_LOSS_STATUSES = {"LOSS", "환불", "양도LOSS"}
_SUCCESS_STATUSES = {"SUC", "단기SUC"}
# 강습(lesson) status 텍스트 등록 판정 — "미등록" 오탐 방지(부정 lookbehind).
_LESSON_REG_RE = re.compile(r"(?<!미)등록완료|(?<!미)등록|성공", re.I)
_TEST_ROW_RE = re.compile(r"테스트|test|시분초확인|확인용", re.I)
_TEST_EPOCH_RE = re.compile(r"_\d{10,}$")  # 이름 끝 epoch 접미(테스트 자동생성행)
# 실측(2026-07-21): status 어휘 = 신규/가망/대기/컨택중/LOSS/SUC/단기SUC/재문의로 종결/공백.
# "신규"·"가망"·"대기"는 아직 실제 컨택이 일어나지 않은 접수 직후 placeholder — contacts[]가
# 없다면 진전으로 보지 않는다(GM 지정: "등록/상담/컨택 등 진행상태 있는 것"만 진전).
_PRE_CONTACT_STATUSES = {"", "신규", "가망", "대기"}
# owner 칸에 값이 있어도 실담당자가 아닌 자동 입력값(웹 접수 시 시스템이 채움) —
# 이 값들은 '배정됨'으로 오판하면 안 되고 미배정으로 취급한다(GM 07-23 지적: 서혜진·임동균 증발).
_AUTO_OWNER_VALUES = ("웹 자동접수", "자동접수", "-")


# 2026-08-01 GM 지시 — 북극성 대비 블록 제외(하루 일과 정리는 그대로 진행)


def _disp_width(s: str) -> int:
    """전각(한글 등 Wide/Fullwidth)=2, 그 외=1 로 계산한 표시폭 — <pre> 표 정렬용."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad_disp(s: str, width: int) -> str:
    pad = width - _disp_width(s)
    return s + (" " * pad if pad > 0 else "")


def _is_test_row(row: dict) -> bool:
    name = str(row.get("name", "") or "")
    return bool(_TEST_ROW_RE.search(name) or _TEST_EPOCH_RE.search(name))


def _fetch_list(action: str, **params) -> list[dict]:
    resp = gas_get(FUNNEL_EXEC_URL, params=dict(action=action, **params), label=action)
    if resp is None:
        return []
    d = resp.json()
    return d.get("data", []) if d.get("ok") else []


def _today_rows(rows: list[dict], today: str) -> list[dict]:
    kept = []
    for r in rows:
        if _is_test_row(r):
            continue
        if str(r.get("timestamp", "") or "").startswith(today):
            kept.append(r)
    return kept


def _is_registered(row: dict, is_lesson: bool) -> bool:
    status = str(row.get("status", "") or "").strip()
    if status in _SUCCESS_STATUSES:
        return True
    if is_lesson and status and _LESSON_REG_RE.search(status):
        return True
    return False


def _is_loss(row: dict) -> bool:
    return str(row.get("status", "") or "").strip() in _LOSS_STATUSES


def _has_contacts(row: dict) -> bool:
    return bool(row.get("contacts"))


def _has_progress(row: dict) -> bool:
    """오늘 컨택&등록 현황 리스트 포함 기준 — 컨택 이력이 있거나, status가 접수직후
    placeholder(신규/가망/대기/공백)를 벗어난 실제 진행 상태(컨택중/등록/이탈 등)인 것."""
    if _has_contacts(row):
        return True
    status = str(row.get("status", "") or "").strip()
    return bool(status) and status not in _PRE_CONTACT_STATUSES


def _progress_label(row: dict, is_lesson: bool) -> str:
    if _is_registered(row, is_lesson):
        return "등록완료"
    if _is_loss(row):
        return "LOSS"
    status = str(row.get("status", "") or "").strip()
    if status:
        if status not in _PRE_CONTACT_STATUSES and not _has_contacts(row):
            # status는 "컨택중" 등 진행 텍스트인데 contacts[] 이력이 비어있음 — 창작 없이
            # 불일치를 그대로 드러낸다(source of truth = contacts[]).
            return f"{status}(이력없음)"
        return status  # 실무진이 시트에 남긴 진행 텍스트 그대로(예: 상담중) — 새 어휘 발명 금지
    if _has_contacts(row):
        return "컨택완료"
    return "미컨택"


def _short_program(program: str) -> str:
    """멤버십 프로그램명을 등급만으로 축약(뒤 시설 목록 제거) — 플래티넘/플래티넘+골프/노블레스/노블레스+골프."""
    p = str(program or "").strip()
    if not p:
        return "-"
    return p.split("(")[0].strip() or p


def _days_since(timestamp: str, today: str) -> int:
    ts = str(timestamp or "")[:10]
    try:
        d0 = datetime.strptime(ts, "%Y-%m-%d")
        d1 = datetime.strptime(today, "%Y-%m-%d")
        return (d1 - d0).days
    except Exception:
        return 0


def _is_unassigned_active(row: dict, is_lesson: bool) -> bool:
    """담당자 미배정 + 활성(등록/이탈 종결 아님).
    owner 가 비어있거나 _AUTO_OWNER_VALUES(웹 자동접수 등 실담당자 아닌 자동값)면 미배정으로 본다."""
    owner = str(row.get("owner", "") or "").strip()
    if owner and owner not in _AUTO_OWNER_VALUES:
        return False
    return not (_is_registered(row, is_lesson) or _is_loss(row))


def _uncontacted_membership(raw_groups: dict[str, list[dict]], today: str) -> list[tuple[str, int]]:
    """회원(멤버십) 문의 중 접수 후 24시간(1일)+ 지났는데 컨택기록(contacts[]) 0건인 활성 건.

    ★2026-08-08 시포(GM 지시) — "미배정 보고를 멈추긴 하는데, 컨택이 안 된 건에 대해서는
    계속 보고해야지". 배472(시토)로 신규 멤버십 문의 담당자가 접수 시 자동으로 채워지면서
    owner 기준 미배정 판정(_is_unassigned_active)이 이 도메인에서는 상시 0건이 된다 — 담당은
    채워졌지만 실제 연락은 아직 없었을 수 있는 방치를 놓친다. 그래서 판정 기준을 담당(owner)
    유무 → 컨택(contacts[]) 유무로 바꾼다. 문턱 24시간은 강습 SLA(unassigned_nudge.SLA_HOURS)
    와 같은 개념을 재사용(순환 임포트라 상수 자체는 못 끌어오므로 이 파일이 이미 쓰는 날짜 단위
    _days_since 로 표현 — 하루 이상 경과 = 접수 당일 이후). 강습(성인/유소년)은
    unassigned_nudge.collect_sla_violations() 가 이미 24시간 SLA로 카카오 ★부서장 방에 따로
    알리므로 여기서는 멤버십만 담아 중복 발신을 피한다. 등록완료·이탈종결(LOSS)은 제외
    (판정 함수 재사용 = _is_registered/_is_loss/_has_contacts, 새 판정 없음). 경과일 내림차순
    (오래된 순) 반환, 상한 없음(GM "계속 보고해야지" — 방치가 오래될수록 더 눈에 띄어야 한다)."""
    out: list[tuple[str, int]] = []
    for r in raw_groups.get("membership", []):
        if _is_test_row(r):
            continue
        if _is_registered(r, False) or _is_loss(r):
            continue
        if _has_contacts(r):
            continue
        d = _days_since(str(r.get("timestamp", "") or ""), today)
        if d < 1:  # 접수 당일(24시간 미만)은 정상 응대 흐름에 맡긴다
            continue
        nm = str(r.get("name", "") or "-").strip() or "-"
        out.append((nm, d))
    out.sort(key=lambda x: -x[1])
    return out


def _field_for(kind: str) -> str:
    return "program" if kind == "membership" else "sport"


# 종목 표기가 두 벌로 갈리는 것을 한 이름으로 모은다(2026-07-31 GM 지시).
# GM: "뮤지컬이랑 영어뮤지컬이랑은 같은 건데, 영어뮤지컬로 다 통일 시켜줘."
# 원천(유소년 문의 시트)에는 '뮤지컬 (Brad Little Star Academy)' 로 들어오고, 화면에서는
# 앞부분만 잘려 '뮤지컬'·'영어 뮤지컬' 두 갈래로 보였다 — 같은 반이 두 팀처럼 갈라져
# 각각 7건·3건으로 떴다. 갈라지면 어느 쪽도 자기 일로 안 읽는다.
# ★표기 통일이지 판정 로직이 아니다 — 시트 값은 건드리지 않는다(원천 불변).
_SPORT_CANON = (
    ("뮤지컬", "영어 뮤지컬"),
)


def _sport_canon(sport: str) -> str:
    s = (sport or "").strip()
    for needle, canon in _SPORT_CANON:
        if needle in s:
            return canon
    return s


def _team_for(kind: str, sport: str = "") -> str:
    """그 문의를 실제로 맡는 팀 — 2026-07-31 GM 확정.

    GM: "이게 임정은M 한테만 해당되는 거야? 강습팀은? 멤버십은 운영부, 강습팀은 각 강습팀
         이런 식으로 알려줘야 해."
    그 전엔 묵은 문의를 이름만 죽 나열하고 '👉 배정 필요'로 끝냈다 — 방에 있는 누구도
    자기 일이라고 읽지 않는다. 받는 사람이 자기 줄을 찾을 수 있어야 움직인다.
    """
    if kind == "membership":
        return "운영부(멤버십)"
    sp = _sport_canon(sport)
    return f"강습팀·{sp}" if sp and sp != "-" else "강습팀"


def _type_label(kind: str) -> str:
    return {"membership": "멤버십", "adult": "성인강습", "youth": "유소년강습"}[kind]


def _concentration_map(groups: dict[str, list[dict]]) -> tuple[dict[str, int], dict[str, int]]:
    """{유형 종목/프로그램: 건수}, {유형: 유형 전체 건수} 집계 헬퍼."""
    concentration: dict[str, int] = {}
    type_total: dict[str, int] = {}
    for kind, rows in groups.items():
        field = _field_for(kind)
        type_label = _type_label(kind)
        for r in rows:
            type_total[type_label] = type_total.get(type_label, 0) + 1
            sp = str(r.get(field, "") or "").strip() or "미분류"
            if kind == "membership":
                sp = _short_program(sp)
            key = f"{type_label} {sp}"
            concentration[key] = concentration.get(key, 0) + 1
    return concentration, type_total


def _special_notes(
    groups: dict[str, list[dict]], raw_groups: dict[str, list[dict]], today: str
) -> str:
    """정직한 자동 요약 — 종목/프로그램 쏠림, 당일(오늘) 스코프 한정.
    단순 "당일 3건+"가 아니라 최근 30일 기준선 대비 비중 1.5배 이상일 때만 쏠림으로 적는다
    (예: 멤버십 플래티넘은 평소에도 최다 상품이라 매일 3건+ 떠서 노이즈였음 — GM 07-23 지적).
    기준선 표본(해당 유형 최근 30일 실건수)이 10건 미만이면 기준선을 불신하고 쏠림 판정을 보류한다.
    담당배정 3일+ 지연(누적·최근30일)은 스코프가 달라 여기 섞지 않고 build_digest 에서
    별도 '📌 누적 미배정(참고, 최근30일)' 라인으로 분리 표기한다(당일 특이사항 과장 방지)."""
    today_conc, today_type_total = _concentration_map(groups)

    base_groups: dict[str, list[dict]] = {}
    for kind, rows in raw_groups.items():
        base_groups[kind] = [
            r for r in rows
            if not _is_test_row(r) and 0 <= _days_since(str(r.get("timestamp", "") or ""), today) <= 30
        ]
    base_conc, base_type_total = _concentration_map(base_groups)

    notes: list[str] = []
    for key, cnt in today_conc.items():
        if cnt < 3:
            continue
        type_label = key.split(" ", 1)[0]
        today_total = today_type_total.get(type_label, 0)
        base_total = base_type_total.get(type_label, 0)
        if today_total <= 0 or base_total < 10:
            continue  # 표본 부족(해당 유형 최근30일 10건 미만) → 기준선 불신, 쏠림 판정 보류
        today_ratio = cnt / today_total
        base_ratio = base_conc.get(key, 0) / base_total
        is_spike = (today_ratio >= base_ratio * 1.5) if base_ratio > 0 else today_ratio > 0
        if is_spike:
            notes.append(f"{key} {cnt}건 쏠림")
    return " · ".join(notes) if notes else "없음"


# ══════════════════════════════════════════════════════════════════════════
# 부서(팀) 톡방 처리완료 통보(2026-08-01 GM 지시) — 종합접수처와 같은 원칙: 개인 회신이
# 아니라 팀 방으로. "배정·등록이 진행되면 그 팀 방에 한 줄." 새 발신경로 없음(약속 L21) —
# report_stream_1_inquiry.py 가 이 build_digest() 결과를 문의알림방(텔레그램)+★부서장
# (카카오, kakao-depthead-inquiry)에 그대로 보내는 기존 배선에 얹는다. 킬스위치·멱등커서
# = status/dept_completion_notify.json(종합접수처와 동일 파일 공용 — 새 레지스트리 안 만듦).
# 문의행에는 고유 id가 없어(_id 칸 미제공, tests/test_report_stream_1_impl.py 확인) 키를
# kind|name|timestamp 로 합성한다(한 사람이 같은 시각에 같은 유형으로 두 번 접수하는 사례는
# 실질적으로 없음). 완료시각 칸도 없어 "직전 실행 이후 새로 배정/등록된 것"만 커서로 가른다.
# ══════════════════════════════════════════════════════════════════════════
COMPLETION_STATE_PATH = REPO_ROOT / "status" / "dept_completion_notify.json"
_COMPLETION_CAP = 0  # 0 = 전부 보여줌(GM 지시 2026-08-30 "…외 N건 말고 다 보고 싶다"). 종전 6건


def _load_completion_state() -> dict:
    try:
        if COMPLETION_STATE_PATH.exists():
            return json.loads(COMPLETION_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"enabled": False, "reception_seen_done_ids": [], "inquiry_seen_keys": []}


def _save_completion_state(state: dict) -> None:
    try:
        COMPLETION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMPLETION_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _row_key(kind: str, row: dict) -> str:
    name = str(row.get("name") or "").strip()
    ts = str(row.get("timestamp") or "").strip()
    return f"{kind}|{name}|{ts}"


def _completion_block(raw_groups: dict[str, list[dict]], state: dict | None = None,
                       persist: bool = True) -> str:
    """새로 배정되거나 등록판정된 문의를 팀별로 묶어 알림 블록으로 렌더."""
    state = state if state is not None else _load_completion_state()
    if not state.get("enabled"):
        return ""
    seen = set(state.get("inquiry_seen_keys") or [])
    all_true_keys: set[str] = set()
    assigned_now: list[tuple[str, dict, str]] = []
    registered_now: list[tuple[str, dict, str]] = []

    for kind, rows in raw_groups.items():
        is_lesson = kind != "membership"
        field = _field_for(kind)
        for r in rows:
            if _is_test_row(r):
                continue
            key = _row_key(kind, r)
            owner = str(r.get("owner", "") or "").strip()
            team = _team_for(kind, str(r.get(field, "") or ""))
            if owner and owner not in _AUTO_OWNER_VALUES:
                akey = "A:" + key
                all_true_keys.add(akey)
                if akey not in seen:
                    assigned_now.append((team, r, owner))
            if _is_registered(r, is_lesson):
                rkey = "R:" + key
                all_true_keys.add(rkey)
                if rkey not in seen:
                    registered_now.append((team, r, owner))

    if persist:
        state["inquiry_seen_keys"] = sorted(seen | all_true_keys)
        _save_completion_state(state)

    events = [("배정", team, r, who) for team, r, who in assigned_now]
    events += [("등록", team, r, who) for team, r, who in registered_now]
    if not events:
        return ""

    def _fmt(label: str, team: str, r: dict, who: str) -> str:
        name = str(r.get("name") or "-").strip() or "-"
        return f"✅ 문의 {label} — {name}({team}) · 담당 {who or '-'}"

    shown = events if _COMPLETION_CAP <= 0 else events[:_COMPLETION_CAP]
    lines = [f"━━━━━━━━━━\n✅ 처리 완료 알림 {len(events)}건"]
    lines += [_fmt(*e) for e in shown]
    if len(events) > len(shown):
        lines.append(f"  …외 {len(events) - len(shown)}건 더")
    return "\n".join(lines)


def seed_completion_cursor() -> int:
    """처리완료 통보를 켜기(enabled:true) 직전 1회 실행 — 지금 이미 배정/등록된 건 전부를
    커서에 채워, 켜는 첫 회차에 오래된 배정·등록건이 한꺼번에 '신규 완료'로 통보되는 것을
    막는다. enabled 값 자체는 건드리지 않는다."""
    mem_raw = _fetch_list("member_inquiry_list")
    adult_raw = _fetch_list("lesson_inquiry_list", type="성인강습")
    youth_raw = _fetch_list("lesson_inquiry_list", type="유소년강습")
    raw_groups = {"membership": mem_raw, "adult": adult_raw, "youth": youth_raw}

    all_true_keys: set[str] = set()
    for kind, rows in raw_groups.items():
        is_lesson = kind != "membership"
        for r in rows:
            if _is_test_row(r):
                continue
            key = _row_key(kind, r)
            owner = str(r.get("owner", "") or "").strip()
            if owner and owner not in _AUTO_OWNER_VALUES:
                all_true_keys.add("A:" + key)
            if _is_registered(r, is_lesson):
                all_true_keys.add("R:" + key)

    state = _load_completion_state()
    state["inquiry_seen_keys"] = sorted(all_true_keys)
    _save_completion_state(state)
    return len(all_true_keys)


SCOPE_KINDS = {
    "all": ("membership", "adult", "youth"),
    "membership": ("membership",),          # 운영부(멤버십 담당) 몫
    "lesson": ("adult", "youth"),           # 부서장(강습 팀장) 몫
}


def build_digest(today: str | None = None, sample: bool = False, sample_n: int = 15,
                  persist_completion: bool = True, scope: str = "all",
                  completion_state: dict | None = None) -> str:
    """scope — 'all'(종전 그대로) / 'membership'(멤버십만) / 'lesson'(성인+유소년 강습만).

    2026-08-27 GM 지시: 한 통에 멤버십·강습이 섞여 있어 각 담당이 자기 것을 못 찾는다
    (실측: 멤버십 미컨택 11건이 중앙값 13.9일 방치 — 강습 5~7일의 두 배). 방을 갈라 보낸다.
    completion_state — 같은 회차에서 여러 번 부를 때 '이미 알린 건' 커서를 공유하려고 받는다.
    안 주면 종전대로 파일에서 읽는다.
    """
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    kinds = SCOPE_KINDS.get(scope) or SCOPE_KINDS["all"]

    mem_raw = _fetch_list("member_inquiry_list") if "membership" in kinds else []
    adult_raw = _fetch_list("lesson_inquiry_list", type="성인강습") if "adult" in kinds else []
    youth_raw = _fetch_list("lesson_inquiry_list", type="유소년강습") if "youth" in kinds else []

    mem_t = _today_rows(mem_raw, today)
    adult_t = _today_rows(adult_raw, today)
    youth_t = _today_rows(youth_raw, today)
    groups = {k: v for k, v in (("membership", mem_t), ("adult", adult_t), ("youth", youth_t))
              if k in kinds}
    raw_groups = {k: v for k, v in (("membership", mem_raw), ("adult", adult_raw), ("youth", youth_raw))
                  if k in kinds}

    a, b, c = len(mem_t), len(adult_t), len(youth_t)
    total_new = sum(len(rows) for rows in groups.values())

    # 당일 신규 3분류(정합 확인용) — 항상 today rows(groups, 테스트행 이미 제외) 기준,
    # sample 여부와 무관하게 always 계산한다(GM 07-23 지적: 서혜진·임동균 2건 증발 방지).
    # 진전(p) / 담당배정 필요(u, owner 미배정·자동값) / 기타(o, 배정됐지만 아직 진전없음).
    progress_today = 0
    unassigned_today: list[tuple[str, str]] = []
    for kind, rows in groups.items():
        is_lesson = kind != "membership"
        for r in rows:
            if _has_progress(r):
                progress_today += 1
            elif _is_unassigned_active(r, is_lesson):
                nm = str(r.get("name", "") or "-").strip() or "-"
                unassigned_today.append((nm, _type_label(kind)))
    other_today = total_new - progress_today - len(unassigned_today)

    # 회원(멤버십) 문의 '연락 아직 안 됨' → 별도 "참고" 라인(당일 아님, 상한 없음).
    # 옛 owner 기준 "3일 넘게 담당이 안 정해진 문의" 자리를 대체한다 — GM 08-08 지시,
    # 판정 상세는 _uncontacted_membership() 참조.
    uncontacted = _uncontacted_membership(raw_groups, today)
    special = _special_notes(groups, raw_groups, today)

    _scope_label = {"membership": " · 멤버십", "lesson": " · 강습(성인·유소년)"}.get(scope, "")
    header = (
        f"📊 [하루 일과 정리] {today}({weekday})\n"
        f"🔔 문의 및 컨택&등록 현황 보고{_scope_label}"
    )
    _breakdown = " + ".join(
        p for p in (f"멤버십({a})" if "membership" in kinds else "",
                    f"성인강습({b})" if "adult" in kinds else "",
                    f"유소년강습({c})" if "youth" in kinds else "") if p
    )
    section_new = (
        f"■ 신규 문의  총 {total_new}건\n"
        f"{_breakdown}\n"
        f"특이사항: {html.escape(special)}"
    )
    recon_parts = [f"진전 {progress_today}건", f"담당배정 필요 {len(unassigned_today)}건"]
    if other_today:
        recon_parts.append(f"기타 {other_today}건")
    section_new += "\n└ " + " · ".join(recon_parts)
    # ★2026-08-20 시포 — 이름 목록과 촉구 문구는 여기서 뺐다(GM 신고: "담당배정 필요건,
    #   연락 아직 안 된 문의건 관련해서 중복된 것 같아").
    #   같은 방에 이 정리와 배정 독려 두 통이 연달아 나가는데, 양쪽에 같은 제목의 촉구가
    #   실려 있었다. 2026-08-05 에 배정 독려를 눈에 띄게 하려고 밖으로 뺄 때 원래 자리의
    #   줄을 안 지워 15일간 둘 다 나갔다. 촉구·이름 목록은 배정 독려 한 통이 전담한다
    #   (unassigned_nudge._render_message). 여기 남는 것은 위 `└ 진전 N건 · 담당배정 필요 N건`
    #   정합 숫자뿐 — 목록이 아니라 당일 신규가 어떻게 갈렸는지 세는 줄이라 중복이 아니다.

    # 컨택&등록 현황 — 3리스트 통합, "실제 진전"(컨택이력≥1 또는 등록판정) 있는 행만.
    # 담당배정 필요 건은 위 신규 문의 섹션(🆕)으로 이전했다 — 정의상 진전이 없는 건이라
    # 컨택&등록 목록에는 애초에 나오지 않으므로 여기서는 더 이상 분리 수집하지 않는다
    # (GM 07-23 지적: "10건 목록 안에 없는 사람이 왜 여기 있냐").
    # sample=True: 리스트 형태 확인용으로 당일 대신 최근 진전건(timestamp 내림차순 top N).
    src_groups = raw_groups if sample else groups
    progress_rows: list[tuple[dict, str]] = []
    for kind, rows in src_groups.items():
        for r in rows:
            if _is_test_row(r):
                continue
            if _has_progress(r):
                progress_rows.append((r, kind))
    if sample:
        progress_rows.sort(key=lambda rk: str(rk[0].get("timestamp", "") or ""), reverse=True)
        progress_rows = progress_rows[:sample_n]

    # 정직한 헤더 카운트 — 등록판정 / 실제 컨택이력(contacts[]≥1) / 이력없음(둘 다 아님, status
    # 자유텍스트만 있는 건 — 라벨에서 "(이력없음)"으로 별도 노출, _progress_label 참조)
    # 3분류 합이 반드시 총건수와 일치하도록 서로 배타적으로 계산한다(GM 07-23 지적: 10≠8+0).
    reg_cnt = sum(1 for r, kind in progress_rows if _is_registered(r, kind != "membership"))
    contact_cnt = sum(
        1 for r, kind in progress_rows
        if _has_contacts(r) and not _is_registered(r, kind != "membership")
    )
    no_history_cnt = sum(
        1 for r, kind in progress_rows
        if not _is_registered(r, kind != "membership") and not _has_contacts(r)
    )

    if not progress_rows:
        contact_body = "컨택·등록 진전 0건"
    else:
        rows_fmt = []
        for r, kind in progress_rows:
            name = html.escape(str(r.get("name", "") or "-").strip() or "-")
            raw_field = _short_program(str(r.get(_field_for(kind), "") or "").strip())
            type_field = html.escape(f"{_type_label(kind)}({raw_field or '-'})")
            # 표시도 판정과 같은 기준 — "웹 자동접수" 등 자동 입력값은 실담당자가 아니므로
            # 사람 이름처럼 보이지 않게 '담당미정'으로 통일한다(_is_unassigned_active 와 동일 규약).
            owner_raw = str(r.get("owner", "") or "").strip()
            if owner_raw in _AUTO_OWNER_VALUES:
                owner_raw = ""
            owner = html.escape(owner_raw or "담당미정")
            label = html.escape(_progress_label(r, kind != "membership"))
            rows_fmt.append((name, type_field, owner, label))
        # 전각(한글=2폭) 보정 고정폭 정렬 — 한글/영문 혼재해도 [라벨] 칸이 세로로 맞도록.
        w_name = max(_disp_width(x[0]) for x in rows_fmt)
        w_type = max(_disp_width(x[1]) for x in rows_fmt)
        w_owner = max(_disp_width(x[2]) for x in rows_fmt)
        lines = [
            f"· {_pad_disp(name, w_name)} · {_pad_disp(type_field, w_type)} · "
            f"{_pad_disp(owner, w_owner)}  [{label}]"
            for name, type_field, owner, label in rows_fmt
        ]
        contact_body = "<pre>\n" + "\n".join(lines) + "\n</pre>"

    if sample:
        contact_head = (
            f"🤝 컨택 & 등록 현황  (샘플·최근 진전 {len(progress_rows)}건 — 리스트 형태 확인용)\n"
            f"※ 실제 일일보고는 '당일' 컨택·등록 건만 표시됩니다."
        )
    else:
        contact_head = (
            f"🤝 컨택 & 등록 현황  총 {len(progress_rows)}건 "
            f"(컨택 {contact_cnt}·등록 {reg_cnt}·이력없음 {no_history_cnt})"
        )
    section_contact = f"{contact_head}\n{contact_body}"

    completion = "" if sample else _completion_block(raw_groups, state=completion_state,
                                                      persist=persist_completion)
    tail = f"\n\n{completion}" if completion else ""
    return (
        f"{header}\n\n{section_new}\n\n"
        f"━━━━━━━━━━\n{section_contact}{tail}"
    )


def send_test(text: str) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 미설정 — telegram_bot/.env 확인 필요")
    return _tg_send(token, GM_CHAT_ID, text, source="report_stream_1_impl.send_test",
                     extra={"parse_mode": "HTML"}, timeout=15)


def _selftest_uncontacted() -> None:
    """멤버십 '연락 아직 안 됨'(_uncontacted_membership) 자가검사(가짜 행·조회/발신 0건).
    확인: ①담당(owner)만 채워지고 컨택이 없는 건은 여전히 잡힘(GM 08-08 지적 시나리오) ②컨택
    이력 있는 건은 제외 ③접수 당일(24시간 미만)은 제외 ④등록완료·이탈종결(LOSS)은 제외
    ⑤경과일 내림차순(오래된 순)."""
    today = "2026-08-08"

    def _d(n: int) -> str:
        return (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d 09:00:00")

    rows = [
        {"name": "배정만됨미컨택", "timestamp": _d(5), "owner": "임정은", "contacts": [], "status": ""},
        {"name": "당일접수", "timestamp": _d(0), "owner": "임정은", "contacts": [], "status": ""},
        {"name": "컨택있음", "timestamp": _d(5), "owner": "임정은",
         "contacts": [{"note": "1차 상담"}], "status": ""},
        {"name": "등록완료", "timestamp": _d(10), "owner": "임정은", "contacts": [], "status": "SUC"},
        {"name": "이탈", "timestamp": _d(10), "owner": "임정은", "contacts": [], "status": "LOSS"},
        {"name": "더오래됨", "timestamp": _d(20), "owner": "임정은", "contacts": [], "status": ""},
    ]
    out = _uncontacted_membership({"membership": rows}, today)
    names = [nm for nm, _ in out]
    assert "배정만됨미컨택" in names, "담당만 채워지고 컨택 없는 건이 안 잡힘(핵심 회귀)"
    assert "당일접수" not in names, "24시간 미만 접수가 잡힘"
    assert "컨택있음" not in names, "컨택 이력 있는 건이 잡힘"
    assert "등록완료" not in names, "등록완료건이 잡힘"
    assert "이탈" not in names, "이탈(LOSS)건이 잡힘"
    assert names == ["더오래됨", "배정만됨미컨택"], f"경과일 내림차순(오래된 순)이 아님: {names}"
    assert _uncontacted_membership({"membership": []}, today) == [], "빈 목록이면 빈 결과여야 함"
    print(f"  [판정] {len(out)}건 — 담당만됨·미컨택 포착/컨택있음·당일·등록·LOSS 제외/오래된 순 — 전부 통과")
    print("SELFTEST OK: 멤버십 '연락 아직 안 됨' 판정 정상(실조회·실발신 0건)")


def main() -> None:
    if "--selftest" in sys.argv:
        _selftest_uncontacted()
        return
    sample = "--sample" in sys.argv
    today = datetime.now().strftime("%Y-%m-%d")
    text = build_digest(today, sample=sample)
    print("=== 렌더된 메시지 ===")
    print(text)
    print("=== 발송 결과 ===")
    result = send_test(text)
    print(result)


if __name__ == "__main__":
    main()
