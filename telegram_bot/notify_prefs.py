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
    "personal_0600": False,  # 🕕 06시 · 개인 — 하루시작·운동 슬롯. GM 2026-07-06: 개인은 유지·확대 방향 → 무음 해제(되살림)
    "series_exhausted": True,  # 📭 AI시리즈 기획예정 소진(정상·산출0) — 로드맵 미채움 지속 시 매일 동일문구 반복 소음 (배10188 2026-07-25). 진짜 오류(로드맵 파싱 실패 등)는 별도 경로 — 무영향.
}


def muted(kind: str) -> bool:
    return bool(MUTED.get(kind, False))
