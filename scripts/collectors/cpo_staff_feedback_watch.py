# -*- coding: utf-8 -*-
"""
cpo_staff_feedback_watch.py — 실무진 피드백이 들어오면 그 자리에서 담당 C-Level '배'로 띄운다.

왜 있나 (2026-07-25 GM 지시)
  "이건은 발생할때마다 체크해서 해줄순없나?"
  실무진 피드백(회원관리 화면 상단 💬 버튼 → 실무진피드백.html → GAS staff_feedback_submit)은
  접수 즉시 업무보고방에 1줄 알림이 간다. 그런데 알림은 흘러가고, 아무도 배로 옮기지 않으면
  '접수' 상태 그대로 시트에 남는다 — 실제로 7/24~25 접수 8건 중 6건이 아무 배도 없이 방치돼
  있었고, 그중 3건은 같은 증상(CONTACT 유실)의 반복 신고였다. 큐에 없으면 항로에도 없다(약속 L15).

무엇을 하나
  1. staff_feedback_list 로 전체 피드백을 읽는다(읽기 전용).
  2. 처리상태가 아직 '접수'인 건 중 배가 없는 것만 status/_queue.json 에 배로 올린다.
     - 대조키 = 접수ID(FB…). 행번호로 찾지 않는다(실고객 오삭제 사고와 동종 위험 회피).
     - 활성 큐 + 아카이브 양쪽을 보고 중복을 막는다(한 피드백 = 한 배).
     - 담당은 화면(업무 구분)·종류 키워드로 가른다(route_clevel, 2026-07-27 배10309) —
       애매하면 시포(cpo)로 보낸다(안전 폴백). 화면이 어디든 무조건 시포로 서던 문제 수정.
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
from clevel_colors import nickname as clevel_nickname  # noqa: E402

MODULE_ID = "cpo-staff-feedback-watch"
ARCHIVE_PATH = ROOT / "status" / "_queue_archive.json"

# 주소·토큰 정본 = .deploy-funnel-v2/Survey.js(FUNNEL_EXEC_URL · INTAKE_SUBMIT_TOKEN).
# 실무진피드백.html 이 쓰는 것과 같은 값 — 자체 발명 아님.
FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"

OPEN_STATUS = ("PENDING", "IN_PROGRESS")
# 급한정도 → 배 무게. 값이 없거나 모르는 값이면 보통으로 본다.
# ★2026-07-27 GM 결정(①안 "급함이면 다른 배보다 먼저 집는다") — 급한정도를 무게 칸에 넣지 않는다.
#   전에는 급함→🛳️크루즈로 무게 칸에 밀어넣었다. 그런데 자율 착수 규칙은 "🛳️크루즈는 무거우니
#   안전하게 멈춤(park)"이라 ★급하다고 표시할수록 자율 착수에서 빠지는★ 정반대 동작이 됐다(배10320 실측).
#   본질 = 무게(얼마나 큰 일인가)와 급한정도(얼마나 급한가)는 다른 축인데 한 칸에 섞은 범주 오류.
#   게다가 접수 시점에는 작업 무게를 알 수 없다 — 실무진이 고른 건 무게가 아니라 급한 정도다.
#   그래서 무게는 접수 기본값(⛴️여객선)으로 두고, 급한정도는 ship['urgency'] 별도 칸에 그대로 남긴다.
#   순서 반영은 선별 게이트(welly_auto_runner._sort_key)가 이 칸을 읽어서 한다.
DEFAULT_PRIORITY = "⛴️여객선"   # 접수 시점엔 실제 무게를 알 수 없음 — 중간값
URGENCY_ALLOWED = ("급함", "보통", "천천히")

# ★2026-07-27 배10309(시우→시포) — 화면이 무엇이든 전부 시포 배로 서던 문제를 고친다.
#   '업무 구분'(screen) 선택값이 폼(실무진피드백.html)의 '어떤 업무인가요?'에서 담당을 가리려고
#   있는 칸인데, build_ship() 이 clevel 을 'cpo' 로 하드코딩해 그 값을 제목에만 쓰고 버리고 있었다.
#   이 폼은 여러 화면이 공유하는 단일 창구(멤버십·강습·종합접수처 + 앞으로 더 붙을 화면들)라
#   화면값 문자열을 하나씩 나열하지 않고 키워드로 판정한다 — 새 화면이 붙어도 코드 재수정 없이 맞는다.
#   매핑 근거는 지어내지 않고 이미 쓰는 도메인 정의 그대로 옮긴다:
#     회원·문의·강습 = 시포(cpo) / 점검·공지·접수·VOC = 시우(coo) /
#     시설 배선·자동화·화면 장애 = 시토(cto) / 마케팅·콘텐츠 = 시모(cmo).
#   인사·재무(시로·시뽀)는 나우열M 관할이라 자동 배정 대상이 아니다 — 해당하면 시우로 보내 사람이 본다.
#   순서가 먼저인 항목이 우선 매치된다. 어느 것도 안 맞으면 시포로 보낸다(지금 동작 유지 = 안전 폴백,
#   잘못 보내 사라지는 것보다 낫다).
_CLEVEL_KEYWORDS = (
    ("cto", ("시설", "배선", "자동화", "장애")),
    ("cmo", ("마케팅", "콘텐츠", "홍보")),
    ("coo", ("인사", "재무", "급여", "채용", "회계")),  # 나우열M 관할 — 자동배정 아님, 시우가 사람에게 넘김
    ("coo", ("점검", "공지", "접수", "VOC", "voc")),
    ("cpo", ("회원", "강습", "문의", "멤버십")),
)


def route_clevel(screen: str, kind: str) -> str:
    """화면(업무 구분)·종류 텍스트로 담당 C-Level 을 고른다. 애매하면 cpo(안전 폴백)."""
    text = f"{screen} {kind}"
    for clevel, keywords in _CLEVEL_KEYWORDS:
        if any(k in text for k in keywords):
            return clevel
    return "cpo"


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
    # 화면 이름 칸은 2026-07-25 에 '화면' → '업무 구분' 으로 이름이 바뀌었는데 여기가 옛 이름만 읽고 있었다.
    # 그래서 그 뒤 올라온 배는 제목에서 화면 이름이 통째로 빠졌다(예: 배10302 "실무진 피드백 — 불편해요: 행간격이…"
    # — 멤버십인지 강습인지 제목만 보고 알 수 없었다). 두 이름 다 받아 옛 행도 그대로 읽는다. 2026-07-27 시포.
    screen = str(row.get("업무 구분") or row.get("화면") or "").strip()
    kind = str(row.get("종류") or "").strip()
    urgency = str(row.get("급한정도") or "").strip()
    writer = str(row.get("작성자") or "").strip()
    content = str(row.get("내용") or "").strip()
    at = str(row.get("접수시각") or "").strip()

    head = " ".join(x for x in (screen, kind) if x)
    first = re.sub(r"\s+", " ", content)[:44]
    title = f"실무진 피드백 — {head}: {first}" if head else f"실무진 피드백 — {first}"

    clevel = route_clevel(screen, kind)
    nick = clevel_nickname(clevel)

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
        "task_id": f"{clevel.upper()}-{today}-FB-{_slug(fid or first)}",
        "clevel": clevel,
        "title": f"[{nick}] {title}",
        "status": "PENDING",
        "priority": DEFAULT_PRIORITY,
        # 급한정도는 무게와 별개 칸으로 — 선별 게이트가 이 값을 먼저 보고 순서를 정한다(GM ①안 2026-07-27).
        "urgency": urgency if urgency in URGENCY_ALLOWED else "보통",
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
