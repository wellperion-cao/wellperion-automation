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
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import FUNNEL_EXEC_URL, gas_get  # noqa: E402
from publish_digest import _load_env_val  # noqa: E402

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
        return "이탈"
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
    """담당자 미배정 + 활성(등록/이탈 종결 아님)."""
    if str(row.get("owner", "") or "").strip():
        return False
    return not (_is_registered(row, is_lesson) or _is_loss(row))


def _field_for(kind: str) -> str:
    return "program" if kind == "membership" else "sport"


def _type_label(kind: str) -> str:
    return {"membership": "멤버십", "adult": "성인강습", "youth": "유소년강습"}[kind]


def _special_notes(groups: dict[str, list[dict]]) -> str:
    """정직한 자동 요약 — 종목/프로그램 3건+ 쏠림만(과장 없음), 당일(오늘) 스코프 한정.
    담당배정 3일+ 지연(누적·최근30일)은 스코프가 달라 여기 섞지 않고 build_digest 에서
    별도 '📌 누적 미배정(참고, 최근30일)' 라인으로 분리 표기한다(당일 특이사항 과장 방지)."""
    notes: list[str] = []
    concentration: dict[str, int] = {}
    for kind, rows in groups.items():
        field = _field_for(kind)
        for r in rows:
            sp = str(r.get(field, "") or "").strip() or "미분류"
            if kind == "membership":
                sp = _short_program(sp)
            key = f"{_type_label(kind)} {sp}"
            concentration[key] = concentration.get(key, 0) + 1
    for key, cnt in concentration.items():
        if cnt >= 3:
            notes.append(f"{key} {cnt}건 쏠림")
    return " · ".join(notes) if notes else "없음"


def build_digest(today: str | None = None, sample: bool = False, sample_n: int = 15) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]

    mem_raw = _fetch_list("member_inquiry_list")
    adult_raw = _fetch_list("lesson_inquiry_list", type="성인강습")
    youth_raw = _fetch_list("lesson_inquiry_list", type="유소년강습")

    mem_t = _today_rows(mem_raw, today)
    adult_t = _today_rows(adult_raw, today)
    youth_t = _today_rows(youth_raw, today)
    groups = {"membership": mem_t, "adult": adult_t, "youth": youth_t}
    raw_groups = {"membership": mem_raw, "adult": adult_raw, "youth": youth_raw}

    a, b, c = len(mem_t), len(adult_t), len(youth_t)
    total_new = a + b + c

    # 담당배정 3일+ 지연(최근 30일 내, 전체 리스트 기준) → 별도 "참고" 라인으로 분리 표기(당일 아님).
    stale_unassigned: list[tuple[str, str]] = []
    for kind, rows in raw_groups.items():
        for r in rows:
            if _is_test_row(r):
                continue
            d = _days_since(str(r.get("timestamp", "") or ""), today)
            if _is_unassigned_active(r, kind != "membership") and 3 <= d <= 30:
                nm = str(r.get("name", "") or "-").strip() or "-"
                sp = _short_program(str(r.get(_field_for(kind), "") or "").strip())
                sub = f"{_type_label(kind)}·{sp}" if sp and sp != "-" else _type_label(kind)
                stale_unassigned.append((nm, sub))
    special = _special_notes(groups)

    header = (
        f"📊 [하루 일과 정리] {today}({weekday})\n"
        f"🔔 문의 및 컨택&등록 현황 보고"
    )
    section_new = (
        f"■ 신규 문의  총 {total_new}건\n"
        f"멤버십({a}) + 성인강습({b}) + 유소년강습({c})\n"
        f"특이사항: {html.escape(special)}"
    )
    if stale_unassigned:
        head = ", ".join(f"{nm}({tp})" for nm, tp in stale_unassigned[:5])
        tail = f" 외 {len(stale_unassigned) - 5}건" if len(stale_unassigned) > 5 else ""
        section_new += (
            f"\n📌 누적 미배정(참고, 최근30일) {len(stale_unassigned)}건 — {head}{tail} 👉 배정 필요"
        )

    # 컨택&등록 현황 — 3리스트 통합, "실제 진전"(컨택이력≥1 또는 등록판정) 있는 행만.
    # 담당 미배정 + 진전없음(활성) 건은 이 리스트에서 빼고 아래 별도 라인으로 분리한다
    # (신규 문의 섹션과 완전 동일 목록이 되는 중복을 방지 — GM 07-21 지적).
    # sample=True: 리스트 형태 확인용으로 당일 대신 최근 진전건(timestamp 내림차순 top N).
    src_groups = raw_groups if sample else groups
    progress_rows: list[tuple[dict, str]] = []
    unassigned_rows: list[tuple[str, str]] = []
    for kind, rows in src_groups.items():
        for r in rows:
            if _is_test_row(r):
                continue
            if _has_progress(r):
                progress_rows.append((r, kind))
            elif not sample and _is_unassigned_active(r, kind != "membership"):
                nm = str(r.get("name", "") or "-").strip() or "-"
                unassigned_rows.append((nm, _type_label(kind)))
    if sample:
        progress_rows.sort(key=lambda rk: str(rk[0].get("timestamp", "") or ""), reverse=True)
        progress_rows = progress_rows[:sample_n]

    # 정직한 헤더 카운트 — 등록판정과 "실제 컨택이력(contacts[]≥1)"만 센다.
    # status 자유텍스트(예: 컨택중)만 있고 contacts[] 이력이 없는 건은 어느 쪽에도 세지 않는다
    # (라벨에서 "(이력없음)"으로 별도 노출 — _progress_label 참조).
    reg_cnt = sum(1 for r, kind in progress_rows if _is_registered(r, kind != "membership"))
    contact_cnt = sum(
        1 for r, kind in progress_rows
        if _has_contacts(r) and not _is_registered(r, kind != "membership")
    )

    if not progress_rows:
        contact_body = "컨택·등록 진전 0건"
    else:
        rows_fmt = []
        for r, kind in progress_rows:
            name = html.escape(str(r.get("name", "") or "-").strip() or "-")
            raw_field = _short_program(str(r.get(_field_for(kind), "") or "").strip())
            type_field = html.escape(f"{_type_label(kind)}({raw_field or '-'})")
            owner = html.escape(str(r.get("owner", "") or "").strip() or "담당미정")
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
        contact_head = f"🤝 컨택 & 등록 현황  총 {len(progress_rows)}건 (컨택 {contact_cnt}·등록 {reg_cnt})"
    section_contact = f"{contact_head}\n{contact_body}"
    if unassigned_rows:
        names = " · ".join(f"{nm}({tp})" for nm, tp in unassigned_rows)
        section_contact += f"\n🆕 담당배정 필요 {len(unassigned_rows)}건: {html.escape(names)}"

    return (
        f"{header}\n\n{section_new}\n\n"
        f"━━━━━━━━━━\n{section_contact}"
    )


def send_test(text: str) -> dict:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 미설정 — telegram_bot/.env 확인 필요")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": GM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
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
