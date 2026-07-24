# -*- coding: utf-8 -*-
"""
알림 등록부 드리프트 체커 (notify_registry_check)
─────────────────────────────────────────────
status/notify_registry.json(카톡·텔레그램 발신 SSOT)이 실제 코드(telegram_bot/daily_scheduler.py
scheduler.add_job 등록분)·실제 예약작업(status/erp_status.json automation_health.items)과
어긋나지 않았는지 대조한다. GM 지시(2026-07-20) — "표가 하드코딩이라 코드가 바뀌어도
안 따라온 것"이 근본 원인이었던 재발 방지용.

이 스크립트는 예약작업을 등록하거나 발송 로직을 건드리지 않는다 — 읽고 대조만 한다.

판정 종류:
  1) MISSING_IN_REALITY — 등록부(schtasks 트리거)가 참조하는 예약작업 이름이
     automation_health.items 에 더 이상 없음 (등록부가 죽은 참조를 갖고 있음).
  2) CODE_MARKER_GONE   — 등록부(apscheduler 트리거)가 전제하는 daily_scheduler.py
     코드 마커(예: schedule_map 06/12/18/21/23, nudge_map, daily_digest_early/late,
     pre_task_notifier, 킬스위치 env 변수명)가 코드에서 사라짐.
  3) UNREGISTERED_TASK  — automation_health.items 중 이름이 발신형(Report/Digest/Card/
     Brief/Alert/Notify/Nudge/Check/Sales/Marketing/Series/Ops/Expiry 포함)으로 보이는데
     notify_registry.json 어느 항목의 source 에도 안 걸림 (신규 발신 가능성 — 이름
     휴리스틱이라 오탐 가능, 최종 판단은 사람).

사용:
  python scripts/notify_registry_check.py            # 콘솔 출력만
  python scripts/notify_registry_check.py --json      # status/notify_drift.json 저장(자율현황 보드 배너 소스)
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "status" / "notify_registry.json"
ERP_STATUS_PATH = ROOT / "status" / "erp_status.json"
SCHEDULER_PATH = ROOT / "telegram_bot" / "daily_scheduler.py"
DRIFT_OUT = ROOT / "status" / "notify_drift.json"

# apscheduler 트리거 항목이 전제하는 코드 마커 — 없어지면 CODE_MARKER_GONE
# ★배10011(2026-07-24): '"18": (18, 0)'·CHECK_MORNING_1200_ENABLED·CHECK_2300_GM_DM_ENABLED
#   3개는 의도적 삭제(18시→21시 흡수, 12/23시 킬스위치 삭제)라 목록에서도 함께 제거했다 —
#   남겨두면 이 체커가 "코드에서 사라졌다"고 매번 오탐(CODE_MARKER_GONE)한다.
APSCHEDULER_MARKERS = [
    'schedule_map = {',
    '"06": (6, 0)',
    '"12": (12, 0)',
    '"21": (21, 0)',
    '"23": (23, 0)',
    'nudge_map = {',
    'id="daily_digest_early"',
    'id="daily_digest_late"',
    'id="pre_task_notifier"',
    'KAKAO_DEPTHEAD_ROOM',
    'KAKAO_GO_STREAM2',
    'id="stream_3_mgmt_0930"',
]

# automation_health 항목명이 '발신형'인지 판정하는 이름 휴리스틱(오탐 가능)
NOTIFY_SHAPED_HINTS = (
    'Report', 'Digest', 'Card', 'Brief', 'Alert', 'Notify', 'Nudge',
    'Check', 'Sales', 'Marketing', 'Series', 'Ops', 'Expiry', 'Share',
)
# 이름은 발신형처럼 보이지만 실제로는 집계/인프라라 알려진 예외(오탐 억제)
KNOWN_NON_NOTIFY = {
    'WellperionDailyScheduler', 'WellperionTelegramBot',
    'Wellperion-Telegram-HealthCheck-1300',  # 정상 시 침묵 — 등록부에 이미 포함됨
}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[WARN] {path} 로드 실패: {e}", file=sys.stderr)
        return None


def main():
    as_json = '--json' in sys.argv

    registry = load_json(REGISTRY_PATH) or {}
    reg_items = registry.get('items', [])
    erp = load_json(ERP_STATUS_PATH) or {}
    ah_items = ((erp.get('automation_health') or {}).get('items')) or []
    ah_names = {it.get('name') for it in ah_items if it.get('name')}

    scheduler_src = ''
    if SCHEDULER_PATH.exists():
        scheduler_src = SCHEDULER_PATH.read_text(encoding='utf-8')
    else:
        print(f"[WARN] {SCHEDULER_PATH} 없음 — apscheduler 마커 대조 스킵", file=sys.stderr)

    mismatches = []

    # ── 1) 등록부(schtasks 트리거) → 실제 예약작업 존재 확인 ──────────────
    # state=='dead'는 제외 — 죽었다고 이미 확정한 항목이 예약작업 부재로 또 걸리는 건
    # 오탐(배10011: win-2300-kakao-check가 배10008 삭제로 이 케이스가 됨).
    for item in reg_items:
        if item.get('trigger') != 'schtasks':
            continue
        if item.get('state') == 'dead':
            continue
        task_name = str(item.get('source', '')).split('·')[0].strip()
        if not task_name:
            continue
        if task_name not in ah_names:
            mismatches.append({
                'kind': 'MISSING_IN_REALITY',
                'registry_id': item.get('id'),
                'task_name': task_name,
                'detail': f"등록부 항목 '{item.get('id')}'가 참조하는 예약작업 '{task_name}'이 "
                          f"automation_health.items에 없음(작업명 변경·삭제 가능성)",
            })

    # ── 2) 등록부(apscheduler 트리거) → 코드 마커 존재 확인 ────────────────
    apscheduler_ids = {item.get('id') for item in reg_items if item.get('trigger') == 'apscheduler'}
    if apscheduler_ids and scheduler_src:
        for marker in APSCHEDULER_MARKERS:
            if marker not in scheduler_src:
                mismatches.append({
                    'kind': 'CODE_MARKER_GONE',
                    'registry_id': None,
                    'task_name': marker,
                    'detail': f"daily_scheduler.py에서 코드 마커 '{marker}' 소실 — "
                              f"apscheduler 트리거 등록부 항목({len(apscheduler_ids)}건) 재검증 필요",
                })

    # ── 3) 실제 예약작업 → 등록부 미커버 발신형 이름 탐지(휴리스틱) ────────
    registered_task_names = set()
    for item in reg_items:
        if item.get('trigger') == 'schtasks':
            registered_task_names.add(str(item.get('source', '')).split('·')[0].strip())

    for name in sorted(ah_names):
        if name in registered_task_names or name in KNOWN_NON_NOTIFY:
            continue
        if any(hint in name for hint in NOTIFY_SHAPED_HINTS):
            mismatches.append({
                'kind': 'UNREGISTERED_TASK',
                'registry_id': None,
                'task_name': name,
                'detail': f"예약작업 '{name}'이 발신형 이름인데 notify_registry.json 어느 항목에도 "
                          f"안 걸림 — 신규 발신이면 등록부에 추가 필요(이름 휴리스틱, 오탐 가능)",
            })

    result = {
        'generated_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'),
        'registry_items': len(reg_items),
        'automation_health_items': len(ah_items),
        'mismatch_count': len(mismatches),
        'mismatches': mismatches,
    }

    print(f"알림 등록부 드리프트 체크 — 등록부 {len(reg_items)}건 · 예약작업 {len(ah_items)}건")
    if not mismatches:
        print("불일치 0건 — 등록부·코드·예약작업 정합.")
    else:
        print(f"불일치 {len(mismatches)}건:")
        for m in mismatches:
            print(f"  [{m['kind']}] {m['detail']}")

    if as_json:
        DRIFT_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n저장: {DRIFT_OUT}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
