# -*- coding: utf-8 -*-
"""대표님 결재 촬영본 업로드 → ★중간관리자 방 「결재받은 목록」 전달 (GM 지시 2026-09-03).

GM 원문: "결재 SSOT 대표님 결재 촬영본 업로드 하면 중간관리자방에는 결재받은 목록 리스트업해서
전달해주고, GM업무에도 반영 및 진행해줘"

무엇을 본다 — 업무&결재 시트(SSOT_API_URL action=todo_list · GM 행 포함) 의 「대표싸인」 칸.
  결재 현황 SSOT.html uploadRepSign() 이 촬영본을 올리면 GAS(approval_rep_sign_upload)가 이 칸에
  서명본 URL 을 적는다 — 그것이 대표 결재완료의 유일한 트리거다(그 페이지 986줄 주석).
  판정은 _owner_directive.js ownerSigned() 와 같다: 비어 있지 않고 'PENDING' 이 아니면 서명.
  ('PENDING' = GM 이 대표님께 올렸지만 아직 서명본이 없는 상태. 2026-05~06 초기 2건은 URL 대신
  "2026-06-05 10:38:24 (페이지)" 처럼 날짜 문구로 찍혀 있다 — 그것도 서명이다.)

어디로 — ★중간관리자(나우열M · 이정헌 소장 · 이경연 실장 · GM). 발신 관문은
  scripts/kakao_report_sender.py 하나뿐(약속 L21) — 여기서는 subprocess 로 그 관문을 부를 뿐
  새 발신기를 만들지 않는다. 사람 방이라 --sender 가 AUTO_PIPELINE_SENDERS 에 있어야 나간다.
  "대표결재전달" 은 GM 상시 지시(2026-09-03 "즉시 전달")로 켜져 있고, daily_scheduler 의 10분
  주기 잡(rep_approval_relay_immediate · 08~22시)이 run(send=True) 를 부른다.

중복 방지 — status/heartbeats/rep-approval-relay.json 의 notified{id: 날짜}. 실제 발신이
  확인된 건만 적는다(미리보기·게이트 거부는 안 적는다 → 다음 회차에 다시 후보가 된다).

GM업무 반영 — 서명 행 자체는 이미 GM업무.html 🤵 대표님 표에 「✅ 보고완료 M/D」로 실린다
  (_owner_directive.js · GM 지시 2026-09-02). 여기 하트비트의 notified 를 같은 파일이 읽어
  「📨 중간관리자 전달 M/D」 배지를 덧붙인다 — GM 화면에서 결재→전달까지 한 줄로 보인다.

수동: python scripts/rep_approval_relay.py (미리보기만) / --send (관문 호출) / --new-rows / --scoreboard.

★2026-09-03 확장(GM 승인 "추천 진행" · 중간관리자 4단계 업무 모듈 보완) — 같은 파일에 세 축 추가:
  ① GM 서명(GM싸인 칸) 도 같은 회차에 — 대표님·GM 둘 다 있으면 한 통에 두 절(🤵 대표님 / 👤 GM).
     지문 notified_gm{id:날짜}. 발신 이름은 "대표결재전달" 그대로(같은 성격).
  ③ 업무 SSOT 신규 행(생성일=오늘 KST · 생성자≠AI) → 「📝 오늘 올라온 업무 N건」.
     지문 notified_new{id:날짜}. 발신 이름 "업무등록묶음".
     ▸2026-09-19 GM 지시("즉시 반영") — 12:00·17:05 두 묶음 잡을 걷고 daily_scheduler 의
       10분 주기 잡(rep_approval_relay_immediate · 08~22시 · 조용 시간대 건너뜀)으로 합쳤다.
     ▸2026-09-10 GM: "직원들이 업무 SSOT 올리면 알림 띄울 수 있어? 운영부방에?" — 이 축만 ★운영부 방에도
       같은 통을 보낸다(ROOM_OPS). 순서는 ★중간관리자 먼저이고, 커서는 그쪽이 성공했을 때만 닫는다 —
       ★운영부 발신이 실패해도 같은 건이 중간관리자 방으로 두 번 가지 않는다. ①②④ 축은 종전대로 중간관리자 방만.
  ④ 저녁 점수판 — 17:05 합본 맨 아래 「📊 오늘 업무 마감 — 완료 N건 / 목표 3」. 발신은 합본
     (중간관리자알림합본·live)에 얹히므로 SCOREBOARD_ON 플래그로 막아 둔다(GM 승인 후 True).
  ② 미배정 잔량 한 줄은 send_ops_digest(07:50 아침 통)·ceo_morning_pipeline(08:00 항로 꼬리)에 있다.

★2026-09-15 10:2x GM 지시("반려된 것도 중간관리자방에 안내하면 좋을듯") — ⑥ 반려 축 추가.
  결재상태에 '반려'가 찍힌 건을 승인 통과 같은 판정·같은 관문으로 전달(--reject / run_reject).
  나우열M 담당은 텔레그램 업무관리 방(AtoA), 그 밖은 ★중간관리자. 지문 notified_reject.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from urllib.parse import quote

from collectors.ops_shared import SSOT_API_URL, gas_get  # noqa: E402
from module_heartbeat import last_heartbeat, record_heartbeat  # noqa: E402
from manager_task_index import OPS_DEPT_STAFF  # noqa: E402 — 운영부 6인 정본(배 12682 · 웰리 배포, 이 파일은 안 건드린다)

HEARTBEAT_ID = "rep-approval-relay"
ROOM = "★중간관리자"
# ★운영부 — 신규 업무 알림만 이 방에도 간다(GM 2026-09-10). 결재 전달·점수판은 종전대로 중간관리자 방만.
ROOM_OPS = "★운영부"
SEND_STAGGER_SECONDS = 6        # 두 방 알림이 같은 초에 겹치지 않게(send_ops_digest 와 같은 간격)
SENDER = "대표결재전달"          # kakao_report_sender.AUTO_PIPELINE_SENDERS 에 넣어야 사람 방 통과
SENDER_NEW = "업무등록묶음"      # ③ 신규 업무 묶음 — 같은 집합에 주석(OFF) 상태
SCOREBOARD_ON = True            # ④ 점수판 — GM 승인 2026-09-03 "추천 진행" 으로 켬(17:05 합본 꼬리)
# ④ 1인당 하루 상한(목표 아님) — GM 확정 2026-09-16 "「하루 3건」은 상한이지 목표가 아니다,
#   '목표'라고 쓰지 마라". 팀 전체가 채워야 할 합계가 아니라 사람마다 하루 최대 3건이라는 뜻.
DAILY_DONE_TARGET = 3
SIGNOFF = "웰페리온 AI 드림"    # send_ops_digest.RELAY_SIGNOFF 와 동일(ops_daily_digest 자동글 필터가 이 문구를 안다)
MAX_ITEMS_PER_MSG = 3           # 제목+상세 2줄씩(3건=6줄)+제목1+마감2 = 9줄 → 한 통 10줄 안쪽. 넘으면 1줄 항목으로
_CAT_RE = re.compile(r"^\[\d+\]\s*")
_AI_RE = re.compile(r"웰리|시뽀|시로|시모|시우|시포|시토|\bai\b", re.IGNORECASE)   # _owner_directive.js aiOwnerRe 와 같은 어휘


def _kst_day(v) -> str:
    """시트 날짜값 → KST 'YYYY-MM-DD'. ISO Z(UTC) 는 +9h, 그 외('2026-06-10'·'2026-09-02 18:25 (페이지)')는 앞 10자."""
    s = str(v or "").strip()
    if "T" in s and s.endswith("Z"):
        try:
            return (datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s[:10]


def _gm_key() -> str:
    from hangro_board import _gm_key as _k   # 정본 — 열쇠 읽는 자리는 그 함수 하나
    return _k()


def is_signed(row: dict, col: str = "대표싸인") -> bool:
    """_owner_directive.js ownerSigned() 와 같은 판정 — 대표싸인·GM싸인 공용."""
    v = str(row.get(col) or "").strip()
    return bool(v) and v not in ("PENDING", "GM종결")   # GM종결 = GM 최종승인(대표님 보고 없이 종료 · 2026-09-16) — 대표님 서명 아님


is_rep_signed = is_signed   # 호환(ceo_morning_pipeline 등 기존 호출부)


def fetch_rows() -> list[dict] | None:
    params = {"action": "todo_list"}
    k = _gm_key()
    if k:
        params.update({"include_gm": "1", "gmkey": k})
    resp = gas_get(SSOT_API_URL, params, timeout=40, label="rep-approval-relay")
    if resp is None:
        return None
    try:
        res = resp.json()
    except Exception:
        return None
    rows = res.get("data") or res.get("todos") if isinstance(res, dict) else None
    return rows if isinstance(rows, list) else None


# 지문 3벌이 한 파일에 산다 — notified(대표)·notified_gm(GM)·notified_new(신규 등록).
# record_heartbeat 는 파일을 통째로 다시 쓰므로 한 벌만 바꿔도 세 벌을 다 실어야 한다(_save_notified).
_LEDGERS = ("notified", "notified_gm", "notified_new", "notified_reject", "notified_direct")


def load_notified(key: str = "notified") -> dict[str, str]:
    rec = last_heartbeat(HEARTBEAT_ID) or {}
    n = rec.get(key)
    return dict(n) if isinstance(n, dict) else {}


def _save_notified(key: str, merged: dict[str, str], detail: str) -> None:
    extra = {k: load_notified(k) for k in _LEDGERS}
    extra[key] = merged
    record_heartbeat(HEARTBEAT_ID, detail=detail, extra=extra)


def pick_new(rows: list[dict], notified: dict[str, str], col: str = "대표싸인") -> list[dict]:
    """서명이 찍혔는데 아직 전달 안 한 건 — 수정일(서명이 수정일을 갱신) 오름차순.
    상태=완료 행은 뺀다 — 끝난 일에 「진행·결과보고서」 전달이 나가면 오독이다(2026-09-16 12:27 ★중간관리자 사고:
    9/15 완료된 「홈페이지 자주 묻는 질문」이 GM 최종승인 뒤 옛 코드로 전달됨 · 웰리 정정 1통)."""
    new = [r for r in rows if is_signed(r, col) and str(r.get("상태") or "").strip() != "완료"
           and str(r.get("id") or "").strip() not in notified]
    return sorted(new, key=lambda r: str(r.get("수정일") or ""))


# ── 전달 경로(GM 지시 2026-09-15) ────────────────────────────────────────────
# GM 원문: "결재완료 알림 담당자가 운영부방에 있으면 이경연실장이 전달 꼭 해주는걸로,
#          담당자가 전달 받았는지도 확인해서 진행 후 결과보고서까지 만들어서 SSOT 할 수 있도록".
# 담당자 → 부서 리더 매핑의 정본 = ssot/ownership_map.json 부서_리더(약속 L01 — 표를 여기 베끼지 않는다).
_DEPT_TABLE: list | None = None


def _dept_table() -> list:
    global _DEPT_TABLE
    if _DEPT_TABLE is None:
        try:
            m = json.loads((REPO_ROOT / "ssot" / "ownership_map.json").read_text(encoding="utf-8"))
            _DEPT_TABLE = (m.get("부서_리더") or {}).get("부서") or []
        except Exception:
            _DEPT_TABLE = []
    return _DEPT_TABLE


def delivery_leader(owner: str) -> str:
    """담당자 이름 → 그 사람에게 전달해 줄 부서 리더. 명단에 없으면 '' (지어내지 않는다)."""
    nm = _owner_key(owner)
    for d in _dept_table():
        if nm in (d.get("구성원") or []):
            return str(d.get("리더") or "")
    return ""


def delivery_note(r: dict, no: int | None = None) -> str:
    """그 건을 누가 누구에게 전달하고 무엇으로 회신하는지 한 조각. 번호가 있으면 회신 규격까지."""
    owner = _owner_key(r.get("담당자"))
    if not owner:
        return "담당 지정 후 전달 부탁드립니다"
    leader = delivery_leader(owner)
    tail = f" · #{no} 전달완료 회신" if isinstance(no, int) else ""
    if _HOLD_OWNER_RE.search(owner) and "나우열" not in owner:
        return "GM 본인 건"      # 남에게 전달할 것이 없다 — 회신도 안 받는다
    if "나우열" in owner:
        return "업무관리 방(AtoA) 전달" + tail
    if not leader:
        return "전달 담당을 정해 주세요" + tail
    if leader == owner:
        return "직접 진행" + tail
    return f"{leader}님 → {owner} 전달" + tail


def _line_item(r: dict, compact: bool = False, nos: dict | None = None) -> list[str]:
    title = str(r.get("업무명") or "").strip()
    owner = str(r.get("담당자") or "").strip() or "담당 미지정"
    note = delivery_note(r, (nos or {}).get(str(r.get("id") or "").strip()))
    if compact:
        return [f"▪ {title} — {owner} · {note}"]
    cat = _CAT_RE.sub("", str(r.get("카테고리") or "").strip())
    detail = f"   담당 {owner}" + (f" · {cat}" if cat else "") + f" · {note}"
    return [f"▪ {title}", detail]


def _md(today: str | None) -> tuple[str, str]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    _, m, d = today.split("-")
    return today, f"{int(m)}/{int(d)}"


def build_messages(rep_rows: list[dict], gm_rows: list[dict] | None = None, today: str | None = None,
                   nos: dict | None = None) -> list[str]:
    """실무진 전달문 — 제목 줄 · 항목(▪)+상세(들여쓰기 3칸) · 빈 줄 없음 · 끝에 할 일 한 줄.
    대표님·GM 둘 다 있으면 한 통에 두 절(🤵 대표님 / 👤 GM). 같은 건이 양쪽에 있으면 대표님 절에만.
    4건까지는 제목+상세 2줄, 넘으면 「▪ 제목 — 담당」 1줄로 줄여 한 통 10줄 안쪽을 지킨다(8건 넘으면 분할)."""
    rep_ids = {str(r.get("id")).strip() for r in rep_rows}
    gm_rows = [r for r in (gm_rows or []) if str(r.get("id")).strip() not in rep_ids]
    total = len(rep_rows) + len(gm_rows)
    if not total:
        return []
    _, md = _md(today)
    both = bool(rep_rows) and bool(gm_rows)
    who = "대표님" if rep_rows and not gm_rows else ("GM" if gm_rows and not rep_rows else "대표님·GM")
    compact = total > MAX_ITEMS_PER_MSG or both
    # 마감 문구가 2줄(전달완료 회신 · 결과보고서)로 늘어 한 통 자리가 하나씩 줄었다(GM 2026-09-15).
    per_msg = MAX_ITEMS_PER_MSG if not compact else (4 if both else 6)   # 제목1+절이름2+마감3 = 10줄 안
    flat = [("🤵 대표님", r) for r in rep_rows] + [("👤 GM", r) for r in gm_rows]
    chunks = [flat[i:i + per_msg] for i in range(0, total, per_msg)]
    msgs = []
    for ci, chunk in enumerate(chunks):
        part = f" ({ci + 1}/{len(chunks)})" if len(chunks) > 1 else ""
        lines = [f"📋 {md} {who} 결재 완료 {total}건{part}"]
        last_sec = None
        for sec, r in chunk:
            if both and sec != last_sec:
                lines.append(sec)
                last_sec = sec
            lines += _line_item(r, compact, nos)
        if ci == len(chunks) - 1:
            # 담당이 비어 있다는 말은 항목 줄에 이미 붙어 있다(delivery_note) — 따로 한 줄 더 쓰지 않는다.
            # GM 지시 2026-09-15 — 전달 → 전달 확인 → 진행 → 결과보고서까지가 한 흐름이라 마감이 두 줄이다.
            lines.append("전달하신 분은 위 #번호로 「전달완료」 한 줄만 답해 주세요(회신 올 때까지 아침 정리에 실립니다).")
            lines.append("진행 끝나면 사진·최종 금액·완료 시각을 이 방에 올려 주세요 — 결과보고서 A4 초안을 드리고, 담당자께서 결재 SSOT 행에 등록하시면 됩니다.")
            lines.append(SIGNOFF)
        msgs.append("\n".join(lines))
    return msgs


# ── 전달 확인 원장 (GM 지시 2026-09-15 "담당자가 전달 받았는지도 확인해서") ──────────
# 새 리마인더·새 상태 파일을 만들지 않는다(약속 L21) — 이미 도는 ★중간관리자 원장에 건별로
# 한 줄 얹으면, 07:50 아침 정리(send_ops_digest.build_reply_nudge_items)가 「#번호 했다」
# 회신이 올 때까지 그 줄을 계속 싣고 sync_ledger_replies 가 회신으로 닫는다.
MGR_LEDGER = REPO_ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★중간관리자" / "_digest_ledger.json"


def build_delivery_asks(rows: list[dict]) -> list[dict]:
    """전달 확인을 받을 건만 원장 이슈 꼴로 만든다. 담당이 비었거나 부서 명단에 없는 건은
    뺀다 — 주인 없는 일은 사람한테 묻지 않는다(build_reply_nudge_items 와 같은 규칙)."""
    asks = []
    for r in rows:
        owner = _owner_key(r.get("담당자"))
        leader = delivery_leader(owner)
        title = str(r.get("업무명") or "").strip()
        if not owner or not leader or not title:
            continue
        asks.append({
            "issue": f"결재완료 전달 — {title}" + (f" ({owner})" if owner != leader else ""),
            "owner": leader,           # 회신을 받을 사람 = 부서 리더(운영부=이경연 실장 · 시설부=이정헌 소장)
            "status": "open",
            "kind": "reply",
            "todo_id": str(r.get("id") or "").strip(),
        })
    return asks


def register_delivery_asks(asks: list[dict], today: str, save: bool) -> dict[str, int]:
    """원장 번호 규칙(ops_daily_digest.assign_ledger_no)으로 #번호를 매겨 {업무 id: 번호} 를
    돌려준다. save=True 일 때만 오늘 자리에 더해 파일에 쓴다 — 통이 실제로 나간 뒤에 부른다
    (안 나간 통의 번호가 원장에 남으면 아무도 모르는 미회신 건이 쌓인다)."""
    if not asks:
        return {}
    try:
        from ops_daily_digest import assign_ledger_no, save_ledger
        ledger = json.loads(MGR_LEDGER.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[rep-approval-relay] 전달 확인 원장 읽기 실패 — 번호 없이 보냅니다 ({exc})")
        return {}
    assign_ledger_no(ledger, asks)
    if save:
        entry = next((e for e in ledger if isinstance(e, dict) and e.get("date") == today), None)
        if entry is None:
            entry = {"date": today, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "source_file": "rep_approval_relay", "issues": []}
            ledger.append(entry)
            ledger.sort(key=lambda e: str(e.get("date", "")))
        entry.setdefault("issues", []).extend(asks)
        save_ledger(ledger, path=MGR_LEDGER)   # 전역 LEDGER_PATH 는 ★운영부다 — 이 방 경로를 명시
        print(f"[rep-approval-relay] 전달 확인 {len(asks)}건 원장 등록 → #{[a.get('no') for a in asks]}")
    return {a["todo_id"]: a["no"] for a in asks
            if isinstance(a.get("no"), int) and a.get("todo_id")}


# ── ⑤ 담당별 진행 현황(GM업무 열린 행) ─────────────────────────────────────
# GM 지시 2026-09-09 — 신규 등록(③)과 결재 완료(①)는 이미 나가는데, **진행 중인 건이
# 담당에게 전달되는 축**이 없었다. 열린 행을 사람별로 갈라 그 사람 방으로 보낸다.
#   ▸GM 본인·외부 업체 담당분은 보내지 않는다 — GM 원문 "도저히 안 되는건 내가 일단 머금는걸로".
#   ▸나우열M 은 카톡이 아니라 텔레그램 업무관리 방이 채널이라 이 통에서 뺀다(방 분리 규칙).
#   ▸사람별 소제목으로 갈라 한 통에 담는다. 실장·소장이 자기 것을 골라 읽지 않아도 되게.
SENDER_ASSIGN = "업무등록묶음"      # 같은 성격이라 발신 이름을 나누지 않는다(약속 L21)

# 이 이름이 담당 칸에 들어 있으면 전달하지 않는다(GM 이 쥐는 것 + 외부 업체).
#   업체명이 담당 칸에 들어간 행도 제외한다 — 사람이 아니라 계약 상대라 이 방에서 할 일이 없다.
_HOLD_OWNER_RE = re.compile(r"GM|김남욱|나우열")
_VENDOR_RE = re.compile(r"브로제이|더함비즈|성실케어|카처|테크노짐|갤럭시아|우리강화|바디프렌드|\(|\)")


def _owner_key(raw: str) -> str:
    """담당 칸 → 사람 한 명 이름. 「최준용M,이경연 실장」처럼 여럿이면 앞사람 기준."""
    return str(raw or "").split(",")[0].strip()


def pick_assign_rows(rows: list[dict]) -> dict[str, list[dict]]:
    """열린 행을 담당별로 묶는다. GM·외부 업체·나우열M 은 뺀다."""
    out: dict[str, list[dict]] = {}
    for r in rows:
        if str(r.get("상태") or "").strip() == "완료":
            continue
        who = _owner_key(r.get("담당자"))
        if not who or _HOLD_OWNER_RE.search(who):
            continue
        if _VENDOR_RE.search(who):        # 「성실케어(김재훈 본부장)」·「브로제이·더함비즈」 등 업체
            continue
        out.setdefault(who, []).append(r)
    return out


def build_assign_message(by_owner: dict[str, list[dict]], today: str | None = None) -> str:
    if not by_owner:
        return ""
    _, md = _md(today)
    total = sum(len(v) for v in by_owner.values())
    lines = [f"📋 {md} 업무 현황 — 진행 중인 것 {total}건"]
    for who in sorted(by_owner, key=lambda k: -len(by_owner[k])):
        items = by_owner[who]
        # 사람당 두 줄만 쓴다 — 이름·건수 한 줄, 가장 급한 것 한 줄. 카톡은 길면 안 읽힌다.
        # 전체 목록은 업무 화면에서 본인 이름으로 거르면 되므로 여기 다 옮기지 않는다.
        dated = [r for r in items if len(_kst_day(r.get("종료일"))) == 10]
        soonest = min(dated, key=lambda r: _kst_day(r.get("종료일"))) if dated else items[0]
        due = _kst_day(soonest.get("종료일"))
        # 기한이 이미 지난 것을 「가장 급한 것」이라 부르면 사람이 무엇이 문제인지 모른다.
        # 지난 것은 며칠 지났는지, 앞으로 올 것은 날짜를 적는다.
        if len(due) == 10:
            gap = (date.fromisoformat(due) - date.today()).days
            tail = f" — {-gap}일 지남" if gap < 0 else f" — {int(due[5:7])}/{int(due[8:10])}"
            head = "가장 오래 밀린 것" if gap < 0 else "가장 급한 것"
        else:
            tail, head = "", "기한 없는 것"
        lines.append(f"👤 {who} {len(items)}건")
        lines.append(f"   {head} · {str(soonest.get('업무명') or '').strip()[:32]}{tail}")
    # 카톡은 공백에서 링크를 끊는다 — 경로에 공백이 있으면 %20 으로 넣는다.
    lines.append("📎 업무 화면 https://erp.wellperion.com/coo/todo/"
                 "%EC%97%85%EB%AC%B4%20%ED%98%84%ED%99%A9%20SSOT.html")
    lines.append("👉 끝난 건은 완료로 바꿔 주시고, 담당·마감이 다르면 알려 주세요.")
    lines.append(SIGNOFF)
    return "\n".join(lines)


def run_assign_brief(send: bool = False, dry_run: bool = False) -> int:
    rows = fetch_rows()
    if rows is None:
        print("[assign-brief] 업무 시트 조회 실패 — 이번 회차 건너뜀")
        return 1
    by_owner = pick_assign_rows(rows)
    msg = build_assign_message(by_owner)
    total = sum(len(v) for v in by_owner.values())
    print(f"[assign-brief] 담당 {len(by_owner)}명 · 진행 중 {total}건")
    if msg:
        print(f"── 미리보기 ({len(msg.splitlines())}줄) ──\n{msg}")
    if not msg or not send:
        return 0
    send_via_gate(msg, dry_run, SENDER_ASSIGN)
    return 0


# ── ③ 오늘 올라온 업무(업무 SSOT 신규 행) ────────────────────────────────────
def pick_new_rows(rows: list[dict], notified: dict[str, str], today: str) -> list[dict]:
    """생성일(KST)=오늘 · 생성자가 AI 가 아닌 행 · 아직 안 알린 것. 생성자 빈칸=사람(페이지 직접 등록)."""
    # 나우열M 라인(인사·재무) 행은 카톡 방(★중간관리자·★운영부)에 싣지 않는다 — 나우열M 소통은 텔레그램
    #   업무관리 방 한 곳(웰리·시로·나우열M)뿐이다(GM 2026-09-14 「운영부 카톡방에 우열M 전달을 왜 해? 업무관리방에만」).
    return [r for r in rows
            if _kst_day(r.get("생성일")) == today
            and not _AI_RE.search(str(r.get("생성자") or ""))
            and "나우열" not in f'{r.get("담당자") or ""} {r.get("생성자") or ""}'
            and not is_hr_row(r)
            and str(r.get("id") or "").strip() not in notified]


def build_new_rows_message(rows: list[dict], today: str | None = None) -> str:
    if not rows:
        return ""
    _, md = _md(today)
    compact = len(rows) > MAX_ITEMS_PER_MSG
    lines = [f"📝 {md} 오늘 올라온 업무 {len(rows)}건"]
    for r in rows[:6]:   # 1줄 항목 6건 + 「외 N건」 1줄 + 제목1 + 마감2 = 10줄
        if compact:
            lines += _line_item(r, True)
        else:
            owner = str(r.get("담당자") or "").strip() or "담당 미지정"
            due = _kst_day(r.get("종료일"))
            due_md = f" · 마감 {int(due[5:7])}/{int(due[8:10])}" if len(due) == 10 else ""
            lines += [f"▪ {str(r.get('업무명') or '').strip()}", f"   담당 {owner}{due_md}"]
    if len(rows) > 6:
        lines.append(f"▪ 외 {len(rows) - 6}건")
    lines.append("담당·마감이 현장과 맞는지 봐 주시고, 다르면 업무 화면에서 바로 고쳐 주세요.")
    lines.append(SIGNOFF)
    return "\n".join(lines)


def run_new_rows(send: bool = False, dry_run: bool = False) -> int:
    rows = fetch_rows()
    if rows is None:
        print("[work-intake] 업무 시트 조회 실패 — 이번 회차 건너뜀")
        return 1
    today, _ = _md(None)
    notified = load_notified("notified_new")
    new = pick_new_rows(rows, notified, today)
    msg = build_new_rows_message(new, today)
    print(f"[work-intake] 오늘 올라온 업무 {len(new)}건(미알림)")
    if msg:
        print(f"── 미리보기 ({len(msg.splitlines())}줄) ──\n{msg}")
    if not new or not send:
        return 0
    ok = send_via_gate(msg, dry_run, SENDER_NEW)
    if ok and not dry_run:
        # ★운영부 방에도 같은 통 (GM 2026-09-10 "직원들이 업무 SSOT 올리면 알림 띄울 수 있어? 운영부방에?").
        #   중간관리자 방이 먼저다 — 그쪽이 성공했을 때만 커서를 닫으므로, 운영부 발신이 실패해도
        #   같은 건이 다음 회차에 중간관리자 방으로 또 가지는 않는다(중복 방지 유지).
        time.sleep(SEND_STAGGER_SECONDS)
        if not send_via_gate(msg, dry_run, SENDER_NEW, room=ROOM_OPS):
            print(f"[work-intake] {ROOM_OPS} 발신 실패 — {ROOM} 은 나갔습니다(이번 건은 그 방에만).")
        for r in new:
            notified[str(r.get("id")).strip()] = today
        _save_notified("notified_new", notified, f"신규 업무 알림 {len(new)}건 ({today})")
    return 0


# ── ④ 저녁 점수판 ────────────────────────────────────────────────────────────
def _done_day(r: dict) -> str:
    return _kst_day(r.get("완료일") or r.get("수정일"))


# ── ④+⑤ 운영부 6인(OPS_DEPT_STAFF) 일별 등록·완료 — 점수판 문구와 하트비트 적재가
# 같은 집계 하나를 나눠 쓴다(약속 L01 — 두 곳이 각자 세면 숫자가 갈린다). GM 확정 2026-09-16:
# 「하루 3건」은 1인당 상한(목표 아님) · 대상은 실장 포함 6명(이지영 사원 제외·진수아 사원 합류,
# manager_task_index.OPS_DEPT_STAFF 가 정본) · 즉시 통 3종(새 접수·완료 통보·대표님 결재 전달)은
# 이 배선과 무관 — 손대지 않는다.
OPS_COUNT_HEARTBEAT_ID = "mgr-ops-daily-count"


def _ops_new_on(rows: list[dict], day: str) -> list[dict]:
    """day 에 생성 + 운영부 6인 담당 + 사람이 등록(AI 생성자 제외) — pick_new_rows 와 같은
    생성일·AI 판정이지만 나우열 제외·notified 지문은 안 쓴다(알림 여부와 무관하게 전부 센다)."""
    return [r for r in rows
            if _kst_day(r.get("생성일")) == day
            and not _AI_RE.search(str(r.get("생성자") or ""))
            and str(r.get("담당자") or "").strip() in OPS_DEPT_STAFF]


def _ops_done_on(rows: list[dict], day: str) -> list[dict]:
    return [r for r in rows
            if str(r.get("상태") or "").strip() == "완료"
            and _done_day(r) == day
            and str(r.get("담당자") or "").strip() in OPS_DEPT_STAFF]


def ops_daily_counts(rows: list[dict], today: str | None = None) -> dict:
    """운영부 6인 오늘·이번 주 등록·완료 집계 + 사람별 오늘 값. scoreboard_section(문구)과
    record_ops_daily_counts(적재)가 이 하나를 같이 쓴다."""
    today, _ = _md(today)
    d1 = date.fromisoformat(today)
    monday = d1 - timedelta(days=d1.weekday())
    week_days = [(monday + timedelta(days=i)).isoformat() for i in range((d1 - monday).days + 1)]
    new_today = _ops_new_on(rows, today)
    done_today = _ops_done_on(rows, today)
    week_new = sum(len(_ops_new_on(rows, d)) for d in week_days)
    week_done = sum(len(_ops_done_on(rows, d)) for d in week_days)
    per_person = {}
    for name in OPS_DEPT_STAFF:
        n = sum(1 for r in new_today if str(r.get("담당자") or "").strip() == name)
        m = sum(1 for r in done_today if str(r.get("담당자") or "").strip() == name)
        if n or m:
            per_person[name] = {"등록": n, "완료": m}
    return {"today": today, "n_new": len(new_today), "n_done": len(done_today),
            "week_new": week_new, "week_done": week_done, "per_person": per_person}


def scoreboard_section(rows: list[dict], today: str | None = None) -> str:
    """📊 오늘 업무 마감 — 등록 N · 완료 N(1인 최대 3 · 6명) · 이번 주 등록 N · 완료 N
    (문구 GM 확정 2026-09-16). 대상은 운영부 6인(OPS_DEPT_STAFF)만 — 나우열M 라인은 안 센다."""
    c = ops_daily_counts(rows, today)
    return (f"📊 오늘 업무 마감 — 등록 {c['n_new']}건 · 완료 {c['n_done']}건"
            f"(1인 최대 {DAILY_DONE_TARGET} · {len(OPS_DEPT_STAFF)}명) · "
            f"이번 주 등록 {c['week_new']}건 · 완료 {c['week_done']}건")


def record_ops_daily_counts(rows: list[dict], today: str | None = None, *, root: Path | None = None) -> dict:
    """⑤ 사람별 일별 등록·완료를 하트비트에 적재 — MGR 하트비트 membership_log 와 같은 방식
    (읽고-병합-쓰기, 최근 30일만 · 새 파일 없음 · module_heartbeat 재사용). 17:05 점수판 발신
    성공 뒤에만 호출부가 부른다. root — selfcheck 전용(실제 status/heartbeats/ 를 안 건드리려고)."""
    c = ops_daily_counts(rows, today)
    kwargs = {"root": root} if root is not None else {}
    prev = last_heartbeat(OPS_COUNT_HEARTBEAT_ID, **kwargs) or {}
    log_ = dict(prev.get("daily_counts") or {})
    log_[c["today"]] = c["per_person"]
    log_ = dict(sorted(log_.items())[-30:])
    return record_heartbeat(OPS_COUNT_HEARTBEAT_ID, detail=f"운영부 6인 일별 등록·완료 — {c['today']}",
                            extra={"state": {"date": c["today"]}, "daily_counts": log_}, **kwargs)


# ── ⑥ 반려 알림(GM 지시 2026-09-15 10:2x "반려된 것도 중간관리자방에 안내") ──────────────
# 반려 판정 칸 = 결재상태(실측 2026-09-16: ''(193)·'결재완료'(57)·'GM 반려'(3)). 담당→방 갈래는
# 신규 업무 축(pick_new_rows)의 나우열 제외 규칙을 그대로 재사용 — 나우열M 담당은 카톡 어느 방에도
# 안 싣고 텔레그램 업무관리 방(AtoA · GM 계정 발신)으로, 그 밖(실장·소장·실무진)은 ★중간관리자.
# 새 발신기 없음 — ★중간관리자는 kakao_report_sender 관문(SENDER 재사용), AtoA 는 이미 쓰는
# notify.telegram_user_send.send_as_gm(WORK_ROOM_CHAT_ID) 그대로.
REJECT_COL = "결재상태"


def is_rejected(row: dict) -> bool:
    return "반려" in str(row.get(REJECT_COL) or "")


def _reject_who(row: dict) -> str:
    return str(row.get(REJECT_COL) or "").replace("반려", "").strip() or "GM"


def _reject_reason(row: dict) -> str:
    """결재의견(JSON 문자열 · [{role,name,time,text}]) 마지막 항목 text. 비어 있으면 GM 지시 문구."""
    try:
        ops = json.loads(row.get("결재의견") or "[]")
    except Exception:
        ops = []
    text = str((ops[-1] or {}).get("text") or "").strip() if isinstance(ops, list) and ops else ""
    return text or "GM 반려 · 사유는 GM 께"


def pick_reject(rows: list[dict], notified: dict[str, str]) -> list[dict]:
    """반려 상태인데 아직 전달 안 한 건 — 수정일(반려가 수정일을 갱신) 오름차순."""
    picked = [r for r in rows if is_rejected(r) and str(r.get("id") or "").strip() not in notified]
    return sorted(picked, key=lambda r: str(r.get("수정일") or ""))


def split_reject_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(나우열M 몫 · 그 밖) — 나우열M 은 카톡 방에 안 싣는다(GM 2026-09-14 재확정)."""
    nawool = [r for r in rows if "나우열" in _owner_key(r.get("담당자"))]
    naw_ids = {str(r.get("id") or "").strip() for r in nawool}
    rest = [r for r in rows if str(r.get("id") or "").strip() not in naw_ids]
    return nawool, rest


def _reject_lines(r: dict) -> list[str]:
    title = str(r.get("업무명") or "").strip()
    when = _kst_day(r.get("수정일"))
    when_md = f"{int(when[5:7])}/{int(when[8:10])}" if len(when) == 10 else when
    return [f"▪ {title} — 반려({_reject_who(r)}·{when_md})",
            f"반려 사유 = {_reject_reason(r)}",
            "👉 사유 반영해 다시 올려 주시면 됩니다"]


def build_reject_message(rows: list[dict], today: str | None = None) -> str:
    if not rows:
        return ""
    _, md = _md(today)
    lines = [f"⛔ {md} 결재 반려 {len(rows)}건"]
    for r in rows:
        lines += _reject_lines(r)
    lines.append(SIGNOFF)
    return "\n".join(lines)


def run_reject(send: bool = False, dry_run: bool = False) -> int:
    rows = fetch_rows()
    if rows is None:
        print("[reject-relay] 업무 시트 조회 실패 — 이번 회차 건너뜀(0건으로 적지 않는다)")
        return 1
    notified = load_notified("notified_reject")
    if not notified:
        # 반려 축 첫 실행 = 기준선만 찍는다(그 시점 이미 반려 상태인 옛 건이 「새 반려」로 안 나가게 —
        # 2026-09-09 접수 통 사고와 같은 자리). 지문이 비어 있을 때마다 이 길을 타므로 자가복구된다.
        seed_today = datetime.now().strftime("%Y-%m-%d")
        notified = {str(r.get("id")).strip(): f"seed-{seed_today}" for r in rows if is_rejected(r)}
        _save_notified("notified_reject", notified, f"반려 축 기준선 {len(notified)}건(seed · 전달 안 함)")
        print(f"[reject-relay] 반려 축 첫 실행 — 기존 {len(notified)}건 seed, 이번 회차 반려 없음")
    picked = pick_reject(rows, notified)
    nawool, rest = split_reject_rows(picked)
    today = datetime.now().strftime("%Y-%m-%d")
    msg_rest = build_reject_message(rest, today)
    msg_naw = build_reject_message(nawool, today)
    print(f"[reject-relay] 반려 {len(picked)}건 — ★중간관리자 {len(rest)}건 · AtoA(나우열M) {len(nawool)}건")
    if msg_rest:
        print(f"── ★중간관리자 미리보기 ──\n{msg_rest}")
    if msg_naw:
        print(f"── AtoA(업무관리) 미리보기 ──\n{msg_naw}")
    if not picked or not send:
        return 0
    ok_rest = send_via_gate(msg_rest, dry_run) if msg_rest else True
    ok_naw = True
    if msg_naw:
        if dry_run:
            print(f"  [AtoA] DRY-RUN — 발송 안 함({len(msg_naw)}자)")
        else:
            from notify.telegram_user_send import send_as_gm, WORK_ROOM_CHAT_ID
            ok_naw = send_as_gm(WORK_ROOM_CHAT_ID, msg_naw)
    if ok_rest and ok_naw and not dry_run:
        for r in picked:
            notified[str(r.get("id")).strip()] = today
        _save_notified("notified_reject", notified,
                       f"반려 전달 ★중간관리자 {len(rest)}·AtoA {len(nawool)}건 ({today})")
    elif not dry_run:
        print("[reject-relay] 일부 방 발신 실패 — 기록 안 함, 다음 회차 재후보")
    return 0


# ── ⑦ 결재완료 → 담당자가 실제로 있는 방에 직접 안내 (GM 지시 2026-09-18 11:5x) ──────────
# GM 원문: "현재 결재 SSOT 결재 완료 시 카카오톡방에 있는 담당자를 찾아서 안내"(배 2760).
# ①/⑥ 은 이미 ★중간관리자 한 곳에만 올려 실장·소장이 손으로 나눠 주는 방식(2026-09-15 설계 —
#   "담당자가 전달 받았는지도 확인해서" 원장으로 전달 여부를 따로 추적한다). 이번 지시는 그
#   중계를 건너뛰고 담당자 본인이 있는 방에 바로 꽂으라는 것 — ①/⑥ 을 대체하지 않고 더한다.
# 트리거는 새로 만들지 않는다 — 실측(2026-09-18): 결재상태='결재완료' 58건이 전부 이미 대표싸인·
#   GM싸인 둘 중 하나가 서명돼 있다(같은 조건). 따로 재면 이중 트리거만 늘 뿐이라 is_signed 를 그대로 쓴다.
# 방 갈래(2026-09-19 GM 지시 개정 — "결재완료된 건들은 모두 운영부방으로, 현재 운영부만 쓰고
#   있기 때문에") — 나우열M=텔레그램 AtoA(GM 계정 발신) 외 전부 ★운영부 직접. 임정은M 만 예외로
#   ★중간관리자에 남는다 — kakao_report_sender.via_manager_violation 실장경유가드(그 방에 그분이
#   계셔 실장을 건너뛴다 — GM 지시 2026-08-16)가 ★운영부 직송을 막기 때문(있던 가드를 그대로 지킨다).
#   ▸2026-09-15 도입판은 운영부 6인만 ★운영부·그 밖은 ★중간관리자였다 — 이번 개정으로 기본값이
#     뒤집혔다(그 밖=★운영부, 예외만 ★중간관리자).
NOTIFY_TELEGRAM = "텔레그램(AtoA)"
APPROVAL_URL = "https://erp.wellperion.com/coo/todo/" + quote("결재 현황 SSOT.html")
# 인사 건 제외(GM 결정 2026-09-19 09:4x 카드) — 계약해지·진급·추가근무 같은 인사·처우는
# 운영부방(도 신규 업무 통)에 안 싣는다. 카테고리 칸이 있으면 그 값을 먼저 본다(실측: 인사 건
# 3건 전부 「[3] 인사&파트너팀」) — 없을 때만 업무명 낱말로 판정한다.
HR_CATEGORY_RE = re.compile(r"인사")
HR_KEYWORD_RE = re.compile(r"계약해지|해지|진급|승진|채용|퇴사|퇴직|급여|연봉|징계|추가근무|근무수당|인사")


def is_hr_row(row: dict) -> bool:
    cat = _CAT_RE.sub("", str(row.get("카테고리") or "").strip())
    if cat:
        return bool(HR_CATEGORY_RE.search(cat))
    return bool(HR_KEYWORD_RE.search(str(row.get("업무명") or "")))


# 조용 시간대 — 이 30분 예약은 daily_scheduler 를 안 거치고 Windows 작업 스케줄러가
#   직접 rep_approval_relay.py 를 부르므로(GM 지시 2026-09-18 배 2760 · 30분 08~22시), 기존
#   ①(_run_rep_approval_relay 의 22~08시 스킵)과 달리 여기서 직접 막아야 한다. 세 창은 같은
#   카톡 PC 에 다른 예약통이 이미 kakao_ui_lock 을 쥐는 시각과 겹친다 — 07:00~08:00(다이어트캠프
#   07:00·아침정리 07:50·GM 브리핑 08:00) · 09:00~09:40(스트림#3 매출보고 09:30) · 21:25~21:40
#   (GM 체크인 21:30·일요 주간카드 21:40). 겹쳐도 lock 이 순서를 지켜 주지만, 굳이 줄을 세워
#   다른 통을 늦출 이유가 없어 이 축만 건너뛰고 다음 30분 회차에 다시 잡는다(지문은 그대로라
#   유실 없음).
_QUIET_WINDOWS = (("07:00", "08:00"), ("09:00", "09:40"), ("21:25", "21:40"))


def _in_quiet_window(now: datetime | None = None) -> bool:
    hm = (now or datetime.now()).strftime("%H:%M")
    return any(a <= hm < b for a, b in _QUIET_WINDOWS)


def route_direct(owner: str) -> tuple[str, str]:
    """(보낼 방, 문구 접두). NOTIFY_TELEGRAM 이면 카톡 관문이 아니라 텔레그램으로 보낸다.
    2026-09-19 GM 지시로 기본값이 ★운영부로 바뀌었다 — 나우열M(텔레그램 유지)·임정은M(실장경유
    가드) 두 예외만 빼고 전부 ★운영부."""
    if "나우열" in owner:
        return (NOTIFY_TELEGRAM, "")
    if "임정은" in owner:
        return (ROOM, "이경연 실장님, ")   # 실장경유가드 대상 — ★운영부로 못 보낸다
    return (ROOM_OPS, "")


def pick_approval_done(rows: list[dict], notified: dict[str, str]) -> list[dict]:
    """대표싸인·GM싸인 둘 중 하나가 signed 인 행(=결재완료) · notified_direct 지문 제외 · 수정일 오름차순."""
    seen: dict[str, dict] = {}
    for col in ("대표싸인", "GM싸인"):
        for r in rows:
            rid = str(r.get("id") or "").strip()
            if rid and rid not in notified and rid not in seen and is_signed(r, col):
                seen[rid] = r
    return sorted(seen.values(), key=lambda r: str(r.get("수정일") or ""))


def build_direct_message(rows: list[dict], prefix: str = "", today: str | None = None) -> str:
    """무슨 일(제목+담당) · 어디(결재 SSOT 링크) · 무엇을(진행 요청) 3줄 뼈대 — 잡담 없이."""
    if not rows:
        return ""
    _, md = _md(today)
    lines = [f"{prefix}📋 {md} 결재 완료 {len(rows)}건 — 공유드립니다"]
    for r in rows[:5]:
        lines.append(f"▪ {str(r.get('업무명') or '').strip()} ({str(r.get('담당자') or '').strip()})")
    if len(rows) > 5:
        lines.append(f"▪ 외 {len(rows) - 5}건")
    lines.append(f"📎 결재 SSOT {APPROVAL_URL}")
    lines.append("담당자분은 진행 기록을 업무 SSOT 행에 남겨 주세요.")
    lines.append(SIGNOFF)
    return "\n".join(lines)


def notify_approval_done(send: bool = False, dry_run: bool = False) -> int:
    rows = fetch_rows()
    if rows is None:
        print("[approval-done] 업무 시트 조회 실패 — 이번 회차 건너뜀")
        return 1
    notified = load_notified("notified_direct")
    if not notified:
        # 첫 실행 = 기준선만(①/⑥ 축과 같은 자리) — 옛 결재완료 건이 한꺼번에 쏟아지지 않게.
        # 단, 최근 2일 안에 서명된 행은 seed 에서 뺀다 — 첫 실행이 방금 결재된 건까지
        # 조용히 삼켜 통보가 안 나가는 사고를 막는다(2026-09-18 5건 미통보 실사고).
        seed_today = datetime.now().strftime("%Y-%m-%d")
        cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        notified = {str(r.get("id")).strip(): f"seed-{seed_today}"
                   for r in rows if (is_signed(r) or is_signed(r, "GM싸인"))
                   and _kst_day(r.get("수정일")) < cutoff}
        _save_notified("notified_direct", notified, f"직접안내 축 기준선 {len(notified)}건(seed · 최근 2일 서명 제외 · 전달 안 함)")
        print(f"[approval-done] 첫 실행 — 기존 {len(notified)}건 seed(최근 2일 서명 제외), 이번 회차는 다음 회차로")
        return 0
    picked_all = pick_approval_done(rows, notified)
    today = datetime.now().strftime("%Y-%m-%d")
    hr_rows = [r for r in picked_all if is_hr_row(r)]
    picked = [r for r in picked_all if not is_hr_row(r)]
    if hr_rows:
        # 인사 건은 운영부·중간관리자·AtoA 어디에도 안 보낸다(GM 결정 2026-09-19) — 지문만 남겨 다시 안 뜨게.
        for r in hr_rows:
            notified[str(r.get("id")).strip()] = f"hr-skip-{today}"
        _save_notified("notified_direct", notified, f"인사 건 제외 {len(hr_rows)}건 ({today})")
        print(f"[approval-done] 인사 건 {len(hr_rows)}건 — 발송 제외(hr-skip 기록)")
    by_route: dict[tuple[str, str], list[dict]] = {}
    for r in picked:
        route = route_direct(_owner_key(r.get("담당자")))
        by_route.setdefault(route, []).append(r)
    print(f"[approval-done] 결재완료(미안내) {len(picked)}건 — " +
         " · ".join(f"{room} {len(rr)}건" for (room, _), rr in by_route.items()))
    quiet = _in_quiet_window()
    done_ids: list[str] = []   # 실제로 시도해서 성공한 건만 — 건너뛴 방·실패는 다음 회차 재후보
    for (room, prefix), rr in by_route.items():
        msg = build_direct_message(rr, prefix, today)
        print(f"── {room} 미리보기 ──\n{msg}")
        if not send:
            continue
        if room != NOTIFY_TELEGRAM and quiet:
            # 카톡 방만 건너뛴다 — 텔레그램(AtoA)은 UI 충돌이 없어 창과 무관하게 나간다.
            print(f"[approval-done] {room} — 조용 시간대라 건너뜀, 지문은 그대로 다음 회차 재후보")
            continue
        if room == NOTIFY_TELEGRAM:
            if dry_run:
                print("  [AtoA] DRY-RUN — 발송 안 함")
                ok = True
            else:
                from notify.telegram_user_send import send_as_gm, WORK_ROOM_CHAT_ID
                ok = send_as_gm(WORK_ROOM_CHAT_ID, msg)
        else:
            ok = send_via_gate(msg, dry_run, SENDER, room=room)
        if ok:
            done_ids += [str(r.get("id")).strip() for r in rr]
        else:
            print(f"[approval-done] {room} 발신 실패 — 기록 안 함, 다음 회차 재후보")
    if send and not dry_run and done_ids:
        for rid in done_ids:
            notified[rid] = today
        _save_notified("notified_direct", notified, f"결재완료 직접안내 {len(done_ids)}건 ({today})")
    elif send and not dry_run and picked:
        print("[approval-done] 일부 방 발신 실패 — 기록 안 함, 다음 회차 재후보")
    return 0


def send_via_gate(text: str, dry_run: bool, sender: str = SENDER, room: str = ROOM) -> bool:
    """kakao_report_sender.py 관문 호출. 실제 전송이 로그로 확인될 때만 True."""
    cmd = [sys.executable, str(SCRIPTS_DIR / "kakao_report_sender.py"),
           "--message", text, "--only-room", room, "--sender", sender]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = [ln for ln in out.strip().splitlines() if "[gate]" in ln or "전송 완료" in ln or "DRY-RUN" in ln or "스킵" in ln]
    for ln in tail[-3:]:
        print("  " + ln)
    return proc.returncode == 0 and "텍스트 전송 완료" in out


def run(send: bool = False, dry_run: bool = False) -> int:
    rows = fetch_rows()
    if rows is None:
        print("[rep-approval-relay] 업무 시트 조회 실패 — 이번 회차 건너뜀(0건으로 적지 않는다)")
        return 1
    notified = load_notified()
    notified_gm = load_notified("notified_gm")
    new = pick_new(rows, notified)
    if not notified_gm:
        # GM 축 첫 실행 = 기준선만 찍는다(과거 GM 서명은 전달 대상 아님 — 오늘 이후만). 지문이
        # 비어 있을 때마다 이 길을 타므로, 옛 코드가 파일을 덮어 지문이 날아가도 45건이 쏟아지지 않는다.
        today = datetime.now().strftime("%Y-%m-%d")
        notified_gm = {str(r.get("id")).strip(): f"seed-{today}" for r in rows if is_signed(r, "GM싸인")}
        _save_notified("notified_gm", notified_gm, f"GM 서명 축 기준선 {len(notified_gm)}건(seed · 전달 안 함)")
        print(f"[rep-approval-relay] GM 서명 축 첫 실행 — 기존 {len(notified_gm)}건 seed, 이번 회차 GM 절 없음")
    new_gm = pick_new(rows, notified_gm, "GM싸인")
    print(f"[rep-approval-relay] 전체 {len(rows)}행 · 대표 서명 {sum(1 for r in rows if is_signed(r))}건(전달 전 {len(new)}) "
          f"· GM 서명 {sum(1 for r in rows if is_signed(r, 'GM싸인'))}건(전달 전 {len(new_gm)})")
    # 전달 확인 번호를 먼저 매겨 문구에 박고, 원장 쓰기는 통이 나간 뒤에 한다(GM 2026-09-15).
    today = datetime.now().strftime("%Y-%m-%d")
    rep_ids = {str(r.get("id")).strip() for r in new}
    asks = build_delivery_asks(new + [r for r in new_gm if str(r.get("id")).strip() not in rep_ids])
    nos = register_delivery_asks(asks, today, save=False)
    msgs = build_messages(new, new_gm, nos=nos)
    for i, t in enumerate(msgs, 1):
        print(f"── 미리보기 {i}/{len(msgs)} ({t.count(chr(10)) + 1}줄) ──")
        print(t)
    if not msgs or not send:
        return 0
    sent_all = all(send_via_gate(t, dry_run) for t in msgs)
    if sent_all and not dry_run:
        register_delivery_asks(asks, today, save=True)
        for r in new:
            notified[str(r.get("id")).strip()] = today
        for r in new_gm:
            notified_gm[str(r.get("id")).strip()] = today
        _save_notified("notified", notified, f"{ROOM} 결재 완료 전달 대표 {len(new)}·GM {len(new_gm)}건 ({today})")
        _save_notified("notified_gm", notified_gm, f"{ROOM} 결재 완료 전달 대표 {len(new)}·GM {len(new_gm)}건 ({today})")
        print(f"[rep-approval-relay] 전달 기록 대표 {len(new)}·GM {len(new_gm)}건 → status/heartbeats/{HEARTBEAT_ID}.json")
    elif not dry_run:
        print("[rep-approval-relay] 관문에서 안 나갔다(게이트 OFF 또는 중복 가드) — 기록 안 함, 다음 회차 재후보")
    return 0


def _selfcheck() -> None:
    rows = [
        {"id": "A", "업무명": "갑", "담당자": "이경연 실장", "카테고리": "[4] 운영 정책", "대표싸인": "https://x/1", "수정일": "2026-09-03T03:02:06.000Z"},
        {"id": "B", "업무명": "을", "담당자": "나우열M", "카테고리": "[3] 인사&파트너팀", "대표싸인": "PENDING", "수정일": "2026-09-02"},
        {"id": "C", "업무명": "병", "담당자": "", "카테고리": "", "대표싸인": "2026-06-05 10:38:24 (페이지)", "수정일": "2026-06-05"},
        {"id": "D", "업무명": "정", "담당자": "김남욱 GM", "카테고리": "[7] IT·시스템·자동화", "대표싸인": "", "수정일": "2026-09-03"},
    ]
    new = pick_new(rows, {"C": "2026-08-01"})
    assert [r["id"] for r in new] == ["A"], new          # PENDING·빈칸 제외, 기록된 C 제외
    assert [r["id"] for r in pick_new(rows, {})] == ["C", "A"]   # 수정일 오름차순
    msgs = build_messages(pick_new(rows, {}), today="2026-09-03")
    assert len(msgs) == 1 and "\n\n" not in msgs[0], msgs
    lines = msgs[0].splitlines()
    assert lines[0] == "📋 9/3 대표님 결재 완료 2건" and lines[-1] == SIGNOFF, lines
    assert lines[1] == "▪ 병" and lines[2] == "   담당 담당 미지정 · 담당 지정 후 전달 부탁드립니다", lines[1:3]
    # 전달 경로(GM 2026-09-15) — 담당이 부서 명단에 있으면 그 부서 리더가 전달, 번호가 있으면 회신 규격까지
    assert lines[3] == "▪ 갑" and lines[4] == "   담당 이경연 실장 · 운영 정책 · 직접 진행", lines[3:5]
    assert len(lines) <= 10
    lines = build_messages(pick_new(rows, {}), today="2026-09-03", nos={"A": 301})[0].splitlines()
    assert lines[4] == "   담당 이경연 실장 · 운영 정책 · 직접 진행 · #301 전달완료 회신", lines[4]
    assert "전달완료" in lines[-3] and "결과보고서 A4" in lines[-2], lines[-3:]
    dept = [dict(rows[0], id="E", 업무명="무", 담당자="윤병현AM")]
    assert build_messages(dept, today="2026-09-03", nos={"E": 302})[0].splitlines()[2] \
        == "   담당 윤병현AM · 운영 정책 · 이경연 실장님 → 윤병현AM 전달 · #302 전달완료 회신"
    assert [a["owner"] for a in build_delivery_asks(dept)] == ["이경연 실장"]
    assert build_delivery_asks([rows[2]]) == []          # 담당 빈칸은 원장에 안 올린다
    many = [dict(rows[0], id=f"A{i}") for i in range(6)]
    msgs = build_messages(many, today="2026-09-03")
    assert len(msgs) == 1 and msgs[0].startswith("📋 9/3 대표님 결재 완료 6건\n▪ 갑 — 이경연 실장 · 직접 진행") and len(msgs[0].splitlines()) <= 10, msgs
    many = [dict(rows[0], id=f"A{i}") for i in range(9)]
    msgs = build_messages(many, today="2026-09-03")
    assert len(msgs) == 2 and "(1/2)" in msgs[0] and SIGNOFF not in msgs[0] and msgs[1].endswith(SIGNOFF)
    assert all(len(m.splitlines()) <= 10 for m in msgs), [len(m.splitlines()) for m in msgs]
    assert build_messages([]) == []
    # ① GM 절 — 둘 다 있으면 한 통 두 절, 같은 건은 대표님 절에만, GM 만 있으면 제목이 GM
    gm = [dict(rows[1], GM싸인="2026-09-03 10:00 (페이지)"), dict(rows[0])]
    assert [r["id"] for r in pick_new(gm, {}, "GM싸인")] == ["B"]   # A 는 GM싸인 없음
    assert pick_new([{"id": "D", "대표싸인": "https://x/서명.png", "상태": "완료", "수정일": "2026-09-16"}], {}) == []   # 완료 행은 전달 안 함
    assert pick_new([{"id": "E", "대표싸인": "GM종결", "수정일": "2026-09-16"}], {}) == []   # GM 최종승인은 대표 서명 아님
    msgs = build_messages([rows[0]], gm, today="2026-09-03")
    lines = msgs[0].splitlines()
    assert lines[0] == "📋 9/3 대표님·GM 결재 완료 2건" and lines[1] == "🤵 대표님" and lines[2] == "▪ 갑 — 이경연 실장 · 직접 진행", lines
    # 나우열M 건은 카톡 방이 채널이 아니다 — 전달 경로를 업무관리 방(AtoA)으로 적는다(방 분리 규칙 유지)
    assert lines[3] == "👤 GM" and lines[4] == "▪ 을 — 나우열M · 업무관리 방(AtoA) 전달" and len(lines) <= 10, lines
    assert build_messages([], gm, today="2026-09-03")[0].startswith("📋 9/3 GM 결재 완료 2건\n▪ 을")
    # ③ 신규 등록 — 생성일 KST(UTC 15:00Z = 다음날 00:00 KST)·AI 생성자 제외·지문 제외
    nr = [
        {"id": "N1", "업무명": "추석 선물", "담당자": "윤병현AM", "생성자": "", "생성일": "2026-09-02T15:30:00.000Z", "종료일": "2026-09-05T15:00:00.000Z"},
        # 나우열M 라인 행은 카톡 통에서 뺀다(GM 2026-09-14) — 담당자든 생성자든
        {"id": "N5", "업무명": "인사 행", "담당자": "나우열M", "생성자": "", "생성일": "2026-09-03T01:00:00.000Z"},
        {"id": "N6", "업무명": "재무 행", "담당자": "x", "생성자": "나우열M", "생성일": "2026-09-03T01:00:00.000Z"},
        {"id": "N2", "업무명": "AI 배", "담당자": "웰리", "생성자": "AI 웰리", "생성일": "2026-09-03T01:00:00.000Z"},
        {"id": "N3", "업무명": "어제 건", "담당자": "x", "생성자": "김남욱GM", "생성일": "2026-09-02T10:00:00.000Z"},
        {"id": "N4", "업무명": "이미 알림", "담당자": "x", "생성자": "김남욱GM", "생성일": "2026-09-03T01:00:00.000Z"},
    ]
    picked = pick_new_rows(nr, {"N4": "2026-09-03"}, "2026-09-03")
    assert [r["id"] for r in picked] == ["N1"], picked
    t = build_new_rows_message(picked, "2026-09-03").splitlines()
    assert t[0] == "📝 9/3 오늘 올라온 업무 1건" and t[1] == "▪ 추석 선물" and t[2] == "   담당 윤병현AM · 마감 9/6" and t[-1] == SIGNOFF, t
    assert build_new_rows_message([], "2026-09-03") == ""
    t9 = build_new_rows_message([dict(nr[0], id=f"N{i}") for i in range(9)], "2026-09-03").splitlines()
    assert len(t9) == 10 and t9[7] == "▪ 외 3건", t9
    # ④+⑤ 점수판·적재 — 운영부 6인만 센다(나우열M·비운영부 제외) · 등록=생성일·AI 아님 · 완료=완료일 우선 없으면 수정일
    assert set(OPS_DEPT_STAFF) == {"이경연 실장", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "진수아 사원"}, OPS_DEPT_STAFF
    sb = [
        # 2026-09-03(수) 등록 2건 — 이경연 실장·최준용M(운영부) / 나우열M(제외) / AI 생성(제외)
        {"id": "S1", "담당자": "이경연 실장", "생성자": "", "생성일": "2026-09-03T01:00:00.000Z", "상태": "진행중"},
        {"id": "S2", "담당자": "최준용M", "생성자": "김남욱GM", "생성일": "2026-09-03T02:00:00.000Z", "상태": "진행중"},
        {"id": "S3", "담당자": "나우열M", "생성자": "", "생성일": "2026-09-03T03:00:00.000Z", "상태": "진행중"},
        {"id": "S4", "담당자": "윤병현AM", "생성자": "AI 웰리", "생성일": "2026-09-03T04:00:00.000Z", "상태": "진행중"},
        # 완료 — 09-03(오늘) 이경연 실장 1건 · 09-01(이번 주) 최준용M 1건 · 08-30(지난주, 주간 집계 밖) 1건
        {"id": "S5", "담당자": "이경연 실장", "상태": "완료", "완료일": "2026-09-03"},
        {"id": "S6", "담당자": "최준용M", "상태": "완료", "완료일": "", "수정일": "2026-09-01T15:30:00.000Z"},
        {"id": "S7", "담당자": "이경연 실장", "상태": "완료", "완료일": "2026-08-30"},
        {"id": "S8", "담당자": "진수아 사원", "상태": "진행중", "완료일": "2026-09-03"},  # 완료 아님 — 제외
    ]
    c = ops_daily_counts(sb, "2026-09-03")   # 수요일 → 월31·화1·수2 = 월31 밖(월요일=08-31)
    assert c == {"today": "2026-09-03", "n_new": 2, "n_done": 1, "week_new": 2, "week_done": 2,
                 "per_person": {"이경연 실장": {"등록": 1, "완료": 1}, "최준용M": {"등록": 1, "완료": 0}}}, c
    s = scoreboard_section(sb, "2026-09-03")
    assert s == "📊 오늘 업무 마감 — 등록 2건 · 완료 1건(1인 최대 3 · 6명) · 이번 주 등록 2건 · 완료 2건", s
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _d:
        _root = Path(_d)
        rec = record_ops_daily_counts(sb, "2026-09-03", root=_root)
        assert rec.get("ok") is True, rec
        assert rec["daily_counts"]["2026-09-03"] == c["per_person"], rec
        rec2 = record_ops_daily_counts(sb, "2026-09-04", root=_root)  # 다른 날 재적재 — 기존 날짜가 안 지워진다
        assert set(rec2["daily_counts"]) == {"2026-09-03", "2026-09-04"}, rec2["daily_counts"]
    print("[selfcheck] ops_daily_counts·record_ops_daily_counts OK")
    # ⑥ 반려 축(GM 2026-09-15 10:2x) — 결재상태에 '반려' 포함 칸만·지문 제외·나우열M 은 AtoA 갈래
    rj = [
        {"id": "R1", "업무명": "짐벌 카메라", "담당자": "나우열M", "결재상태": "GM 반려",
         "수정일": "2026-09-15T01:18:07.000Z",
         "결재의견": '[{"role":"GM","name":"김남욱GM","time":"2026-09-10 19:43:21","text":"그럼 안사도되?"}]'},
        {"id": "R2", "업무명": "바디프렌드 안마의자", "담당자": "윤병현AM", "결재상태": "GM 반려",
         "수정일": "2026-09-15T07:23:18.000Z", "결재의견": ""},
        {"id": "R3", "업무명": "이미 알림", "담당자": "이경연 실장", "결재상태": "대표 반려",
         "수정일": "2026-09-14T00:00:00.000Z", "결재의견": ""},
        {"id": "R4", "업무명": "결재완료 건", "담당자": "이경연 실장", "결재상태": "결재완료",
         "수정일": "2026-09-15T00:00:00.000Z", "결재의견": ""},
    ]
    picked = pick_reject(rj, {"R3": "2026-09-14"})
    assert [r["id"] for r in picked] == ["R1", "R2"], picked   # R3 지문 제외 · R4 결재완료(반려 아님) 제외
    nawool, rest = split_reject_rows(picked)
    assert [r["id"] for r in nawool] == ["R1"] and [r["id"] for r in rest] == ["R2"], (nawool, rest)
    lines = build_reject_message(rest, "2026-09-16").splitlines()
    assert lines[0] == "⛔ 9/16 결재 반려 1건" and lines[1] == "▪ 바디프렌드 안마의자 — 반려(GM·9/15)", lines
    assert lines[2] == "반려 사유 = GM 반려 · 사유는 GM 께", lines[2]   # 결재의견 빈칸 → GM 지시 기본문구
    assert lines[3] == "👉 사유 반영해 다시 올려 주시면 됩니다" and lines[-1] == SIGNOFF, lines
    lines2 = build_reject_message(nawool, "2026-09-16").splitlines()
    assert lines2[1] == "▪ 짐벌 카메라 — 반려(GM·9/15)" and lines2[2] == "반려 사유 = 그럼 안사도되?", lines2
    assert build_reject_message([]) == ""
    # ⑦ 결재완료 직접안내(GM 2026-09-18) — 나우열M=AtoA · 운영부(임정은 제외)=★운영부 직접 · 임정은·그 밖=★중간관리자
    assert route_direct("나우열M") == (NOTIFY_TELEGRAM, "")
    assert route_direct("임정은M") == (ROOM, "이경연 실장님, ")
    assert route_direct("최준용M") == (ROOM_OPS, "")
    assert route_direct("이정헌 소장") == (ROOM_OPS, "")   # 2026-09-19 개정 — 나우열M·임정은M 외 전부 ★운영부
    assert route_direct("김남욱GM") == (ROOM_OPS, "")
    ad = [
        {"id": "AD1", "업무명": "짐벌 카메라", "담당자": "최준용M", "대표싸인": "https://x/1", "수정일": "2026-09-18T01:00:00.000Z"},
        {"id": "AD2", "업무명": "이미 안내", "담당자": "이경연 실장", "대표싸인": "https://x/2", "수정일": "2026-09-17T00:00:00.000Z"},
        {"id": "AD3", "업무명": "GM싸인만", "담당자": "임정은M", "GM싸인": "2026-09-18 10:00 (페이지)", "수정일": "2026-09-18T02:00:00.000Z"},
        {"id": "AD4", "업무명": "미서명", "담당자": "윤병현AM", "대표싸인": "PENDING", "수정일": "2026-09-18T03:00:00.000Z"},
    ]
    picked = pick_approval_done(ad, {"AD2": "2026-09-17"})
    assert [r["id"] for r in picked] == ["AD1", "AD3"], picked   # 지문 있는 AD2·미서명 AD4 제외
    msg = build_direct_message([ad[0]], "", "2026-09-18").splitlines()
    assert msg[0] == "📋 9/18 결재 완료 1건 — 공유드립니다" and msg[1] == "▪ 짐벌 카메라 (최준용M)", msg
    assert msg[-2] == "담당자분은 진행 기록을 업무 SSOT 행에 남겨 주세요.", msg
    # 인사 건 제외(GM 결정 2026-09-19) — 카테고리 「인사&파트너팀」 이면 업무명과 무관하게 인사, 없으면 낱말 판정
    assert is_hr_row({"업무명": "최현준 골프팀장 계약해지 및 인수인계", "카테고리": "[3] 인사&파트너팀"}) is True
    assert is_hr_row({"업무명": "골프팀 팀리더 김태엽 진급", "카테고리": "[3] 인사&파트너팀"}) is True
    assert is_hr_row({"업무명": "남 지원부 추가근무", "카테고리": ""}) is True   # 카테고리 없을 때 낱말 판정
    assert is_hr_row({"업무명": "CCTV 100대 전체 교체 계약", "카테고리": "[5] 시설 및 환경"}) is False
    assert APPROVAL_URL.startswith("https://erp.wellperion.com/coo/todo/%") and APPROVAL_URL.endswith("SSOT.html")
    # 조용 시간대(GM 지시 2026-09-18 배 2760 — 30분 예약이 다른 예약통과 카톡 UI 를 안 다투게)
    from datetime import datetime as _dt
    assert _in_quiet_window(_dt(2026, 9, 18, 7, 30)) is True    # 07:00~08:00
    assert _in_quiet_window(_dt(2026, 9, 18, 9, 20)) is True    # 09:00~09:40
    assert _in_quiet_window(_dt(2026, 9, 18, 21, 30)) is True   # 21:25~21:40
    assert _in_quiet_window(_dt(2026, 9, 18, 12, 0)) is False
    assert _in_quiet_window(_dt(2026, 9, 18, 8, 0)) is False    # 경계값 — 08:00 은 창 밖(포함 안 함)
    # 나우열M 은 어떤 owner 문자열이 와도 kakao 방(ROOM/ROOM_OPS)이 아니라 텔레그램으로만 간다
    for who in ("나우열M", "나우열M,이경연 실장", "재무 나우열M"):
        room, _ = route_direct(who)
        assert room == NOTIFY_TELEGRAM, (who, room)
    assert build_direct_message([]) == ""
    print("[selfcheck] rep_approval_relay OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="대표님 결재 완료 → ★중간관리자 전달")
    ap.add_argument("--send", action="store_true", help="관문(kakao_report_sender) 호출. 없으면 미리보기만")
    ap.add_argument("--dry-run", action="store_true", help="--send 와 함께: 관문 DRY-RUN(카톡 창에 붙였다 지움)")
    ap.add_argument("--new-rows", action="store_true", help="③ 오늘 올라온 업무 묶음(미리보기·--send)")
    ap.add_argument("--scoreboard", action="store_true", help="④ 저녁 점수판 미리보기(발신 없음)")
    ap.add_argument("--assign-brief", action="store_true",
                    help="⑤ 담당별 진행 현황 묶음(미리보기·--send) — GM·외부업체·나우열M 제외")
    ap.add_argument("--reject", action="store_true",
                    help="⑥ 결재 반려 알림(미리보기·--send) — 나우열M 은 AtoA, 그 밖은 ★중간관리자")
    ap.add_argument("--approval-done", action="store_true",
                    help="⑦ 결재완료 → 담당자 방 직접 안내(미리보기·--send) — 나우열M=AtoA·운영부=★운영부·그 밖=★중간관리자")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        sys.exit(0)
    if a.scoreboard:
        _rows = fetch_rows()
        print(scoreboard_section(_rows) if _rows is not None else "[scoreboard] 조회 실패")
        sys.exit(0)
    if a.assign_brief:
        sys.exit(run_assign_brief(send=a.send, dry_run=a.dry_run))
    if a.reject:
        sys.exit(run_reject(send=a.send, dry_run=a.dry_run))
    if a.approval_done:
        sys.exit(notify_approval_done(send=a.send, dry_run=a.dry_run))
    if a.new_rows:
        sys.exit(run_new_rows(send=a.send, dry_run=a.dry_run))
    sys.exit(run(send=a.send, dry_run=a.dry_run))
