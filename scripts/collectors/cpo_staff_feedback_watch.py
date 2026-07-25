# -*- coding: utf-8 -*-
"""
cpo_staff_feedback_watch.py — 실무진 피드백이 들어오면 그 자리에서 시포 '배'로 띄운다.

왜 있나 (2026-07-25 GM 지시)
  "이건은 발생할때마다 체크해서 해줄순없나?"
  실무진 피드백(회원관리 화면 상단 💬 버튼 → 실무진피드백.html → GAS staff_feedback_submit)은
  접수 즉시 업무보고방에 1줄 알림이 간다. 그런데 알림은 흘러가고, 아무도 배로 옮기지 않으면
  '접수' 상태 그대로 시트에 남는다 — 실제로 7/24~25 접수 8건 중 6건이 아무 배도 없이 방치돼
  있었고, 그중 3건은 같은 증상(CONTACT 유실)의 반복 신고였다. 큐에 없으면 항로에도 없다(약속 L15).

무엇을 하나
  1. staff_feedback_list 로 전체 피드백을 읽는다(읽기 전용).
  2. 처리상태가 아직 '접수'인 건 중 배가 없는 것만 status/_queue.json 에 시포 배로 올린다.
     - 대조키 = 접수ID(FB…). 행번호로 찾지 않는다(실고객 오삭제 사고와 동종 위험 회피).
     - 활성 큐 + 아카이브 양쪽을 보고 중복을 막는다(한 피드백 = 한 배).
  3. 하트비트를 남긴다(가동 신호는 배가 아니라 하트비트로 — 배9995 도배 사고 교훈).

무엇을 안 하나
  - 알림을 새로 보내지 않는다. 접수 알림은 GAS 가 이미 보낸다(중복 발신 금지).
  - 시트를 고치지 않는다. 처리상태 갱신은 사람·시포가 staff_feedback_update 로 한다.
  - 새 예약작업을 만들지 않는다. 3분 주기 cpo_inquiry_snapshot.bat 에 얹어 같이 돈다.

실행: python scripts/collectors/cpo_staff_feedback_watch.py [--dry-run] [--no-push]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from queue_lock import mutate_queue, load_queue  # noqa: E402
from module_heartbeat import record_heartbeat  # noqa: E402
from assign_short_no import next_short_no  # noqa: E402

MODULE_ID = "cpo-staff-feedback-watch"
ARCHIVE_PATH = ROOT / "status" / "_queue_archive.json"

# 주소·토큰 정본 = .deploy-funnel-v2/Survey.js(FUNNEL_EXEC_URL · INTAKE_SUBMIT_TOKEN).
# 실무진피드백.html 이 쓰는 것과 같은 값 — 자체 발명 아님.
FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"

OPEN_STATUS = ("PENDING", "IN_PROGRESS")
# 급한정도 → 배 무게. 값이 없거나 모르는 값이면 보통으로 본다.
PRIORITY = {"급함": "🛳️크루즈", "보통": "⛴️여객선", "천천히": "⛵돛단배"}


def fetch_feedback(timeout=60):
    """접수된 피드백 전체(최신순). 실패 시 (None, 사유) — 조용히 성공으로 위장하지 않는다."""
    body = json.dumps({"action": "staff_feedback_list", "t": FB_TOKEN}).encode("utf-8")
    req = urllib.request.Request(
        FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"
    if not data.get("ok"):
        return None, str(data.get("error") or "ok=false")
    return data.get("rows") or [], None


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title).strip("-")
    return (s[:28] or "TASK").upper()


def _existing_ids(queue, archive) -> set:
    """이미 배가 있는 접수ID 집합. feedback_id 필드가 정본, 옛 배는 note 안 FB… 문자열로도 인정."""
    ids = set()
    for it in list(queue) + list(archive):
        if not isinstance(it, dict):
            continue
        fid = it.get("feedback_id")
        if fid:
            ids.add(str(fid).strip())
            continue
        note = str(it.get("note") or "")
        for m in re.finditer(r"FB\d{6}-\d{6}", note):
            ids.add(m.group(0))
    return ids


def build_ship(row: dict, queue, today: str) -> dict:
    fid = str(row.get("접수ID") or "").strip()
    screen = str(row.get("화면") or "").strip()
    kind = str(row.get("종류") or "").strip()
    urgency = str(row.get("급한정도") or "").strip()
    writer = str(row.get("작성자") or "").strip()
    content = str(row.get("내용") or "").strip()
    at = str(row.get("접수시각") or "").strip()

    head = " ".join(x for x in (screen, kind) if x)
    first = re.sub(r"\s+", " ", content)[:44]
    title = f"실무진 피드백 — {head}: {first}" if head else f"실무진 피드백 — {first}"

    nos = [x.get("ship_no") or 0 for x in queue if isinstance(x, dict)]
    ship_no = (max(nos) + 1) if nos else 1

    note = (
        f"[실무진 피드백 자동 접수 {today}] 접수ID {fid} · 접수 {at}"
        f" · 작성자 {writer or '(미기재 — 되묻기 불가)'}"
        f"{' · 급한정도 ' + urgency if urgency else ''}\n\n"
        f"{content}\n\n"
        "▸ 처리 후 staff_feedback_update 로 시트의 처리상태·처리메모를 채운다"
        "(대조키=접수ID). 실무진이 본인 화면에서 처리 결과를 확인할 수 있어야 완료다."
    )
    return {
        "task_id": f"CPO-{today}-FB-{_slug(fid or first)}",
        "clevel": "cpo",
        "title": f"[시포] {title}",
        "status": "PENDING",
        "priority": PRIORITY.get(urgency, "⛴️여객선"),
        "enqueued_at": today,
        "from": "실무진",
        "note": note,
        "next": "내용 확인 → 원인·조치 → 시트 처리상태 갱신 → 작성자에게 결과 회신",
        "ship_no": ship_no,
        "short_no": next_short_no(queue),
        "module": "home",
        "surface": "autonomy",
        "feedback_id": fid,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="큐에 쓰지 않고 무엇이 올라갈지만 출력")
    ap.add_argument("--no-push", action="store_true", help="큐만 갱신하고 커밋·푸시 생략")
    args = ap.parse_args()

    rows, err = fetch_feedback()
    if rows is None:
        print(f"[error] 피드백 조회 실패 — {err}")
        return 0  # fail-soft: 3분마다 도는 잡이라 다음 회차에 재시도한다.

    pending = [r for r in rows if str(r.get("처리상태") or "").strip() in ("", "접수")]

    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()

    try:
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        archive = []

    if args.dry_run:
        q = load_queue()
        have = _existing_ids(q, archive)
        new = [r for r in pending if str(r.get("접수ID") or "").strip() not in have]
        print(f"전체 {len(rows)}건 · 미처리 {len(pending)}건 · 배 없는 신규 {len(new)}건")
        for r in new:
            print("  +", r.get("접수ID"), "|", str(r.get("내용") or "")[:60].replace("\n", " "))
        return 0

    made = []

    def mutator(queue):
        have = _existing_ids(queue, archive)
        for r in pending:
            fid = str(r.get("접수ID") or "").strip()
            if not fid or fid in have:
                continue
            ship = build_ship(r, queue, today)
            queue.append(ship)
            have.add(fid)
            made.append(ship)
        return queue

    mutate_queue(mutator, holder=MODULE_ID)

    record_heartbeat(
        MODULE_ID,
        detail=f"피드백 {len(rows)}건 · 미처리 {len(pending)}건 · 이번에 배로 올린 것 {len(made)}건",
        extra={"전체": len(rows), "미처리": len(pending), "신규_배": len(made)},
    )

    if not made:
        print(f"[done] 새로 올릴 피드백 없음 (전체 {len(rows)} · 미처리 {len(pending)})")
        return 0

    for s in made:
        print(f"[ship] 배 {s['short_no']} · {s['title']}")

    if args.no_push:
        print("[done] --no-push — 커밋 생략")
        return 0

    # 커밋은 safe_commit 을 통한다(부팅 스킬 §5-2 — 세션 커밋 관문 단일화).
    # git_commit_push 를 직접 부르면 이 저장소가 detached HEAD 로 돌 때 push 가
    # "You are not currently on a branch" 로 죽는다(2026-07-25 실측). safe_commit 은
    # 지정 경로만 담고 HEAD 재검증·원자 갱신까지 하며 그 상황을 함께 처리한다.
    # 제목을 chore(queue) 로 시작한다 — auto_log_adhoc_to_queue 의 SKIP 규칙에 걸려
    # 이 커밋이 또 하나의 완료-배를 낳지 않는다(배 도배 재발 방지).
    import subprocess  # noqa: PLC0415
    msg = f"chore(queue): 실무진 피드백 {len(made)}건 배로 접수 (cpo-staff-feedback-watch)"
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "safe_commit.py"), "-m", msg, "--",
             "status/_queue.json", f"status/heartbeats/{MODULE_ID}.json"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=180,
        )
        print((r.stdout or "").strip()[-400:] or "[warn] safe_commit 출력 없음")
        if r.returncode != 0:
            print(f"[warn] safe_commit rc={r.returncode} — 큐 파일은 로컬에 남음, 다음 회차 재시도")
    except Exception as e:
        print(f"[warn] 커밋 실패(무해 — 큐 파일은 로컬에 남음): {type(e).__name__}: {str(e)[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
