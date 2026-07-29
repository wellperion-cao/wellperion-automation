import sys
sys.path.insert(0, '.')
from scripts.queue_lock import mutate_queue

RESUME_CONDITIONS = (
    "재개조건 4종(외부 트리거 — 순서 무관, 하나라도 발생 시 해당 항목만 착수):\n"
    "①강습 이탈방지 — 시토 배에서 강습 원장 만료일·잔여회차 적재 완료(DONE) 확인됨\n"
    "②저이용 방문데이터 — 브로제이 API 접근권 확보 OR 9월 자체서버 통합 공식 착수 배 DONE\n"
    "③통합 발신 ON — module_registry.json cpo-inquiry-daily-actions.enabled=true 변경 + GM go\n"
    "④강습 전용 게이트 — GM 직접 지시\n"
    "지금 시포 할 일 없음. 트리거 발생 시 해당 항목만 재착수 — 나머지는 계속 대기."
)

def apply(items):
    for s in items:
        if s.get("task_id") == "CPO-2026-07-09-AUTONOMY-BRAIN":
            s["next"] = RESUME_CONDITIONS
            print("[OK] 배 754 next 필드 업데이트 완료")
            print("NEXT_PREVIEW:", RESUME_CONDITIONS[:80])
            return items
    print("[ERROR] 배 754 not found")
    return items

mutate_queue(apply, holder="cpo-resume-condition")
