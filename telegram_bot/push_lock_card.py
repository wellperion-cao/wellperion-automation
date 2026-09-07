"""push_lock_card.py — 🔒 자물쇠 라인(배1098 · GM 지시 2026-09-07) GM 승인 카드 콜백.

telegram_bot/bot.py 가 CallbackQueryHandler(handle_callback, pattern=r"^plk:") 로 등록한다.
callback_data = "plk:<요청id>:<a|r>". 여기서는 status/push_approvals.json 의 해당 요청
status 만 approved/rejected 로 바꾼다 — 실제 cherry-pick·push·브랜치 삭제는
scripts/post_commit_push.py --sweep(daily_scheduler push_sweeper·5분 주기)이 한다
(약속 L21 — 승인 카드는 상태만 바꾸고 무거운 git 작업은 관문 한 곳에 둔다).
telegram_bot/work_room_agent.py 의 wrk: 카드와 같은 구조(callback 접두 안 겹침).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCR = str(REPO_ROOT / "scripts")
if _SCR not in sys.path:
    sys.path.insert(0, _SCR)

import push_lock  # noqa: E402


async def handle_callback(update, ctx) -> None:
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("plk:"):
        return
    await q.answer()
    parts = q.data.split(":")
    if len(parts) != 3:
        return
    req_id, decision = parts[1], parts[2]
    decided_by = "GM"
    user = update.effective_user
    if user:
        decided_by = f"{user.full_name}({user.id})"
    status = "approved" if decision == "a" else "rejected"
    ok, req = push_lock.decide(req_id, status, decided_by)
    if not ok or not req:
        # 이미 처리된 요청(파일 승인·다른 경로) — 누른 사람에게 그 사실을 답한다(2026-09-07 웰리 · GM 카드 무반응 사고).
        prev = next((r for r in push_lock.load_approvals()["requests"] if r.get("id") == req_id), None)
        prev_status = (prev or {}).get("status", "없음")
        note = {"pushed": "이미 승인·배포됨", "approved": "이미 승인됨(배포 대기)", "rejected": "이미 반려됨",
                "conflict": "충돌로 보류 중"}.get(prev_status, f"처리 불가(상태 {prev_status})")
        try:
            await q.edit_message_text(text=f"ℹ️ {req_id} — {note}", reply_markup=None)
        except Exception:
            pass
        return
    label = "✅ 승인" if decision == "a" else "⛔ 반려"
    tail = "다음 스위퍼 주기(5분 내) master 로 올라갑니다." if decision == "a" else "브랜치를 지웁니다."
    try:
        await q.edit_message_text(
            text=f"{label} — {req_id} ({req.get('branch', '')})\n{tail}",
            reply_markup=None,
        )
    except Exception:
        pass
