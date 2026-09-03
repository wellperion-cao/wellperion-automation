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
  ③ 업무 SSOT 신규 행(생성일=오늘 KST · 생성자≠AI) → 「📝 오늘 올라온 업무 N건」 12:00·17:05.
     지문 notified_new{id:날짜}. 발신 이름 "업무등록묶음"(주석=OFF).
  ④ 저녁 점수판 — 17:05 합본 맨 아래 「📊 오늘 업무 마감 — 완료 N건 / 목표 3」. 발신은 합본
     (중간관리자알림합본·live)에 얹히므로 SCOREBOARD_ON 플래그로 막아 둔다(GM 승인 후 True).
  ② 미배정 잔량 한 줄은 send_ops_digest(07:50 아침 통)·ceo_morning_pipeline(08:00 항로 꼬리)에 있다.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from collectors.ops_shared import SSOT_API_URL, gas_get  # noqa: E402
from module_heartbeat import last_heartbeat, record_heartbeat  # noqa: E402

HEARTBEAT_ID = "rep-approval-relay"
ROOM = "★중간관리자"
SENDER = "대표결재전달"          # kakao_report_sender.AUTO_PIPELINE_SENDERS 에 넣어야 사람 방 통과
SENDER_NEW = "업무등록묶음"      # ③ 신규 업무 묶음 — 같은 집합에 주석(OFF) 상태
SCOREBOARD_ON = False           # ④ 점수판 — 17:05 live 합본에 얹히므로 GM 승인 전엔 False
DAILY_DONE_TARGET = 3           # ④ 하루 완료 목표(GM 기획 3단계)
SIGNOFF = "AI 웰리 드림"        # send_ops_digest.RELAY_SIGNOFF 와 동일(ops_daily_digest 자동글 필터가 이 문구를 안다)
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
    return bool(v) and v != "PENDING"


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
_LEDGERS = ("notified", "notified_gm", "notified_new")


def load_notified(key: str = "notified") -> dict[str, str]:
    rec = last_heartbeat(HEARTBEAT_ID) or {}
    n = rec.get(key)
    return dict(n) if isinstance(n, dict) else {}


def _save_notified(key: str, merged: dict[str, str], detail: str) -> None:
    extra = {k: load_notified(k) for k in _LEDGERS}
    extra[key] = merged
    record_heartbeat(HEARTBEAT_ID, detail=detail, extra=extra)


def pick_new(rows: list[dict], notified: dict[str, str], col: str = "대표싸인") -> list[dict]:
    """서명이 찍혔는데 아직 전달 안 한 건 — 수정일(서명이 수정일을 갱신) 오름차순."""
    new = [r for r in rows if is_signed(r, col) and str(r.get("id") or "").strip() not in notified]
    return sorted(new, key=lambda r: str(r.get("수정일") or ""))


def _line_item(r: dict, compact: bool = False) -> list[str]:
    title = str(r.get("업무명") or "").strip()
    owner = str(r.get("담당자") or "").strip() or "담당 미지정"
    if compact:
        return [f"▪ {title} — {owner}"]
    cat = _CAT_RE.sub("", str(r.get("카테고리") or "").strip())
    detail = f"   담당 {owner}" + (f" · {cat}" if cat else "")
    return [f"▪ {title}", detail]


def _md(today: str | None) -> tuple[str, str]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    _, m, d = today.split("-")
    return today, f"{int(m)}/{int(d)}"


def build_messages(rep_rows: list[dict], gm_rows: list[dict] | None = None, today: str | None = None) -> list[str]:
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
    per_msg = MAX_ITEMS_PER_MSG if not compact else (5 if both else 7)   # 제목1+절이름2+마감2 = 10줄 안
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
            lines += _line_item(r, compact)
        if ci == len(chunks) - 1:
            lines.append("각 담당자께서는 결재된 내용대로 진행해 주시고, 진행 상황은 업무 화면에 남겨 주세요.")
            lines.append(SIGNOFF)
        msgs.append("\n".join(lines))
    return msgs


# ── ③ 오늘 올라온 업무(업무 SSOT 신규 행) ────────────────────────────────────
def pick_new_rows(rows: list[dict], notified: dict[str, str], today: str) -> list[dict]:
    """생성일(KST)=오늘 · 생성자가 AI 가 아닌 행 · 아직 안 알린 것. 생성자 빈칸=사람(페이지 직접 등록)."""
    return [r for r in rows
            if _kst_day(r.get("생성일")) == today
            and not _AI_RE.search(str(r.get("생성자") or ""))
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
    if send_via_gate(msg, dry_run, SENDER_NEW) and not dry_run:
        for r in new:
            notified[str(r.get("id")).strip()] = today
        _save_notified("notified_new", notified, f"{ROOM} 신규 업무 알림 {len(new)}건 ({today})")
    return 0


# ── ④ 저녁 점수판 ────────────────────────────────────────────────────────────
def _done_day(r: dict) -> str:
    return _kst_day(r.get("완료일") or r.get("수정일"))


def scoreboard_section(rows: list[dict], today: str | None = None) -> str:
    """📊 오늘 업무 마감 — 완료 N건 / 목표 3 · 이번 주 완료 N건 · 빈 날 N일(월요일~오늘 중 완료 0건인 날).
    완료 = 상태 '완료' · 완료일(없으면 수정일)로 센다 — 요약줄 옮겨 적기 없음."""
    today, _ = _md(today)
    d1 = date.fromisoformat(today)
    monday = d1 - timedelta(days=d1.weekday())
    done_days = [_done_day(r) for r in rows if str(r.get("상태") or "").strip() == "완료"]
    n_today = done_days.count(today)
    week = [d for d in done_days if monday.isoformat() <= d <= today]
    empty = sum(1 for i in range((d1 - monday).days + 1)
                if (monday + timedelta(days=i)).isoformat() not in week)
    return (f"📊 오늘 업무 마감 — 완료 {n_today}건 / 목표 {DAILY_DONE_TARGET}\n"
            f"   이번 주 완료 {len(week)}건 · 빈 날 {empty}일")


def send_via_gate(text: str, dry_run: bool, sender: str = SENDER) -> bool:
    """kakao_report_sender.py 관문 호출. 실제 전송이 로그로 확인될 때만 True."""
    cmd = [sys.executable, str(SCRIPTS_DIR / "kakao_report_sender.py"),
           "--message", text, "--only-room", ROOM, "--sender", sender]
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
    msgs = build_messages(new, new_gm)
    for i, t in enumerate(msgs, 1):
        print(f"── 미리보기 {i}/{len(msgs)} ({t.count(chr(10)) + 1}줄) ──")
        print(t)
    if not msgs or not send:
        return 0
    sent_all = all(send_via_gate(t, dry_run) for t in msgs)
    if sent_all and not dry_run:
        today = datetime.now().strftime("%Y-%m-%d")
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
        {"id": "B", "업무명": "을", "담당자": "나우열M", "카테고리": "[2] 인사", "대표싸인": "PENDING", "수정일": "2026-09-02"},
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
    assert lines[1] == "▪ 병" and lines[2] == "   담당 담당 미지정", lines[1:3]
    assert lines[3] == "▪ 갑" and lines[4] == "   담당 이경연 실장 · 운영 정책", lines[3:5]
    assert len(lines) <= 10
    many = [dict(rows[0], id=f"A{i}") for i in range(6)]
    msgs = build_messages(many, today="2026-09-03")
    assert len(msgs) == 1 and msgs[0].startswith("📋 9/3 대표님 결재 완료 6건\n▪ 갑 — 이경연 실장") and len(msgs[0].splitlines()) <= 10, msgs
    many = [dict(rows[0], id=f"A{i}") for i in range(9)]
    msgs = build_messages(many, today="2026-09-03")
    assert len(msgs) == 2 and "(1/2)" in msgs[0] and SIGNOFF not in msgs[0] and msgs[1].endswith(SIGNOFF)
    assert all(len(m.splitlines()) <= 10 for m in msgs)
    assert build_messages([]) == []
    # ① GM 절 — 둘 다 있으면 한 통 두 절, 같은 건은 대표님 절에만, GM 만 있으면 제목이 GM
    gm = [dict(rows[1], GM싸인="2026-09-03 10:00 (페이지)"), dict(rows[0])]
    assert [r["id"] for r in pick_new(gm, {}, "GM싸인")] == ["B"]   # A 는 GM싸인 없음
    msgs = build_messages([rows[0]], gm, today="2026-09-03")
    lines = msgs[0].splitlines()
    assert lines[0] == "📋 9/3 대표님·GM 결재 완료 2건" and lines[1] == "🤵 대표님" and lines[2] == "▪ 갑 — 이경연 실장", lines
    assert lines[3] == "👤 GM" and lines[4] == "▪ 을 — 나우열M" and len(lines) <= 10, lines
    assert build_messages([], gm, today="2026-09-03")[0].startswith("📋 9/3 GM 결재 완료 2건\n▪ 을")
    # ③ 신규 등록 — 생성일 KST(UTC 15:00Z = 다음날 00:00 KST)·AI 생성자 제외·지문 제외
    nr = [
        {"id": "N1", "업무명": "추석 선물", "담당자": "나우열M", "생성자": "", "생성일": "2026-09-02T15:30:00.000Z", "종료일": "2026-09-05T15:00:00.000Z"},
        {"id": "N2", "업무명": "AI 배", "담당자": "웰리", "생성자": "AI 웰리", "생성일": "2026-09-03T01:00:00.000Z"},
        {"id": "N3", "업무명": "어제 건", "담당자": "x", "생성자": "김남욱GM", "생성일": "2026-09-02T10:00:00.000Z"},
        {"id": "N4", "업무명": "이미 알림", "담당자": "x", "생성자": "김남욱GM", "생성일": "2026-09-03T01:00:00.000Z"},
    ]
    picked = pick_new_rows(nr, {"N4": "2026-09-03"}, "2026-09-03")
    assert [r["id"] for r in picked] == ["N1"], picked
    t = build_new_rows_message(picked, "2026-09-03").splitlines()
    assert t[0] == "📝 9/3 오늘 올라온 업무 1건" and t[1] == "▪ 추석 선물" and t[2] == "   담당 나우열M · 마감 9/6" and t[-1] == SIGNOFF, t
    assert build_new_rows_message([], "2026-09-03") == ""
    t9 = build_new_rows_message([dict(nr[0], id=f"N{i}") for i in range(9)], "2026-09-03").splitlines()
    assert len(t9) == 10 and t9[7] == "▪ 외 3건", t9
    # ④ 점수판 — 완료일 우선·없으면 수정일·KST, 주간=월요일부터, 빈 날=완료 0건인 날
    sb = [
        {"상태": "완료", "완료일": "2026-08-31"}, {"상태": "완료", "완료일": "", "수정일": "2026-09-02T15:30:00.000Z"},
        {"상태": "완료", "완료일": "2026-09-03"}, {"상태": "진행중", "완료일": "2026-09-03"}, {"상태": "완료", "완료일": "2026-08-30"},
    ]
    s = scoreboard_section(sb, "2026-09-03")   # 수요일 → 월31·화1·수2·목3 = 4일 중 완료 있는 날 31·3 → 빈 날 2
    assert s == "📊 오늘 업무 마감 — 완료 2건 / 목표 3\n   이번 주 완료 3건 · 빈 날 2일", s
    print("[selfcheck] rep_approval_relay OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="대표님 결재 완료 → ★중간관리자 전달")
    ap.add_argument("--send", action="store_true", help="관문(kakao_report_sender) 호출. 없으면 미리보기만")
    ap.add_argument("--dry-run", action="store_true", help="--send 와 함께: 관문 DRY-RUN(카톡 창에 붙였다 지움)")
    ap.add_argument("--new-rows", action="store_true", help="③ 오늘 올라온 업무 묶음(미리보기·--send)")
    ap.add_argument("--scoreboard", action="store_true", help="④ 저녁 점수판 미리보기(발신 없음)")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        sys.exit(0)
    if a.scoreboard:
        _rows = fetch_rows()
        print(scoreboard_section(_rows) if _rows is not None else "[scoreboard] 조회 실패")
        sys.exit(0)
    if a.new_rows:
        sys.exit(run_new_rows(send=a.send, dry_run=a.dry_run))
    sys.exit(run(send=a.send, dry_run=a.dry_run))
