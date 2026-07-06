# notify_prefs.py
# GM 2026-07-06 저신호 무음. 복원=해당 키 False 로.
# 고신호(검수카드·발행결과·07/08/12/21시 보고·항로·북극성)는 여기 없음=항상 발송.
#
# 중앙 플래그 — 되돌리기 쉬운 단일 지점. 각 호출부는 best-effort(try/except)로
# import 실패해도 발송이 막히지 않게(False 폴백) 감싼다.

MUTED = {
    "pre_task": True,       # 정기 루틴 H-15분 사전 알림 (pre_task_notifier.py)
    "produce_done": True,   # 🎨 제작완료 사진카드 (scripts/publish_register.py, 검수카드와 중복)
    "pending_ping": True,   # ⏳ 발행 처리 시작(발행검증대기) 안내 (telegram_bot/bot.py)
    "personal_0600": True,  # 🕕 06시 · 개인 — 하루시작·운동 슬롯 (telegram_bot/daily_scheduler.py)
}


def muted(kind: str) -> bool:
    return bool(MUTED.get(kind, False))
