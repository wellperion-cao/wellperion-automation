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
  ★지금은 게이트 OFF(GM 승인 대기) — kakao_report_sender.AUTO_PIPELINE_SENDERS 에 SENDER 가
  없어 관문이 "[gate] 거부" 로 막는다. 켜는 법 = 그 집합에 "대표결재전달" 한 줄 추가.

중복 방지 — status/heartbeats/rep-approval-relay.json 의 notified{id: 날짜}. 실제 발신이
  확인된 건만 적는다(미리보기·게이트 거부는 안 적는다 → 다음 회차에 다시 후보가 된다).

GM업무 반영 — 서명 행 자체는 이미 GM업무.html 🤵 대표님 표에 「✅ 보고완료 M/D」로 실린다
  (_owner_directive.js · GM 지시 2026-09-02). 여기 하트비트의 notified 를 같은 파일이 읽어
  「📨 중간관리자 전달 M/D」 배지를 덧붙인다 — GM 화면에서 결재→전달까지 한 줄로 보인다.

호출 — telegram_bot/daily_scheduler.run_mgmt_notice_digest(17:05, ★중간관리자 알림성 합본과
  같은 슬롯·같은 방) 이 run(send=True) 를 부른다. 수동: python scripts/rep_approval_relay.py
  (미리보기만) / --send (관문 호출 · 게이트 OFF 면 미리보기와 같음).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
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
SIGNOFF = "AI 웰리 드림"        # send_ops_digest.RELAY_SIGNOFF 와 동일(ops_daily_digest 자동글 필터가 이 문구를 안다)
MAX_ITEMS_PER_MSG = 4           # 제목+상세 2줄씩 → 한 통 10줄 안쪽
_CAT_RE = re.compile(r"^\[\d+\]\s*")


def _gm_key() -> str:
    from hangro_board import _gm_key as _k   # 정본 — 열쇠 읽는 자리는 그 함수 하나
    return _k()


def is_rep_signed(row: dict) -> bool:
    """_owner_directive.js ownerSigned() 와 같은 판정."""
    v = str(row.get("대표싸인") or "").strip()
    return bool(v) and v != "PENDING"


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


def load_notified() -> dict[str, str]:
    rec = last_heartbeat(HEARTBEAT_ID) or {}
    n = rec.get("notified")
    return dict(n) if isinstance(n, dict) else {}


def pick_new(rows: list[dict], notified: dict[str, str]) -> list[dict]:
    """서명본이 찍혔는데 아직 전달 안 한 건 — 수정일(서명본 업로드가 수정일을 갱신) 오름차순."""
    new = [r for r in rows if is_rep_signed(r) and str(r.get("id") or "").strip() not in notified]
    return sorted(new, key=lambda r: str(r.get("수정일") or ""))


def _line_item(r: dict) -> list[str]:
    title = str(r.get("업무명") or "").strip()
    owner = str(r.get("담당자") or "").strip() or "담당 미지정"
    cat = _CAT_RE.sub("", str(r.get("카테고리") or "").strip())
    detail = f"   담당 {owner}" + (f" · {cat}" if cat else "")
    return [f"▪ {title}", detail]


def build_messages(rows: list[dict], today: str | None = None) -> list[str]:
    """실무진 전달문 — 제목 줄 · 항목(▪)+상세(들여쓰기 3칸) · 빈 줄 없음 · 끝에 할 일 한 줄.
    한 통 10줄 안쪽이라 4건 넘으면 여러 통으로 나눈다."""
    if not rows:
        return []
    today = today or datetime.now().strftime("%Y-%m-%d")
    _, m, d = today.split("-")
    msgs = []
    chunks = [rows[i:i + MAX_ITEMS_PER_MSG] for i in range(0, len(rows), MAX_ITEMS_PER_MSG)]
    for ci, chunk in enumerate(chunks):
        part = f" ({ci + 1}/{len(chunks)})" if len(chunks) > 1 else ""
        lines = [f"📋 {int(m)}/{int(d)} 대표님 결재 완료 {len(rows)}건{part}"]
        for r in chunk:
            lines += _line_item(r)
        if ci == len(chunks) - 1:
            lines.append("각 담당자께서는 결재된 내용대로 진행해 주시고, 진행 상황은 업무 화면에 남겨 주세요.")
            lines.append(SIGNOFF)
        msgs.append("\n".join(lines))
    return msgs


def send_via_gate(text: str, dry_run: bool) -> bool:
    """kakao_report_sender.py 관문 호출. 실제 전송이 로그로 확인될 때만 True."""
    cmd = [sys.executable, str(SCRIPTS_DIR / "kakao_report_sender.py"),
           "--message", text, "--only-room", ROOM, "--sender", SENDER]
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
    new = pick_new(rows, notified)
    signed_total = sum(1 for r in rows if is_rep_signed(r))
    print(f"[rep-approval-relay] 전체 {len(rows)}행 · 대표 서명 {signed_total}건 · 전달 전 {len(new)}건")
    msgs = build_messages(new)
    for i, t in enumerate(msgs, 1):
        print(f"── 미리보기 {i}/{len(msgs)} ({t.count(chr(10)) + 1}줄) ──")
        print(t)
    if not new or not send:
        return 0
    sent_all = all(send_via_gate(t, dry_run) for t in msgs)
    if sent_all and not dry_run:
        today = datetime.now().strftime("%Y-%m-%d")
        for r in new:
            notified[str(r.get("id")).strip()] = today
        record_heartbeat(HEARTBEAT_ID, detail=f"{ROOM} 전달 {len(new)}건 ({today})",
                         extra={"notified": notified})
        print(f"[rep-approval-relay] 전달 기록 {len(new)}건 → status/heartbeats/{HEARTBEAT_ID}.json")
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
    assert len(msgs) == 2 and msgs[0].startswith("📋 9/3 대표님 결재 완료 6건 (1/2)") and SIGNOFF not in msgs[0] and msgs[1].endswith(SIGNOFF)
    assert all(len(m.splitlines()) <= 10 for m in msgs)
    assert build_messages([]) == []
    print("[selfcheck] rep_approval_relay OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="대표님 결재 완료 → ★중간관리자 전달")
    ap.add_argument("--send", action="store_true", help="관문(kakao_report_sender) 호출. 없으면 미리보기만")
    ap.add_argument("--dry-run", action="store_true", help="--send 와 함께: 관문 DRY-RUN(카톡 창에 붙였다 지움)")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        sys.exit(0)
    sys.exit(run(send=a.send, dry_run=a.dry_run))
