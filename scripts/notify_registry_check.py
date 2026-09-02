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
# ★배10011 L21 정산(2026-07-24): 'nudge_map = {' 도 같은 이유로 제거 — 17:00/22:00 독려
#   슬롯은 커밋 f36d56393(2026-07-23, GM 승인)로 코드가 실제 삭제됐고, 이를 전제하던
#   등록부 항목(tg-1700-nudge-pm·tg-2200-nudge-close)도 이번에 함께 지웠다(끄기가
#   아니라 삭제 — L21). 마커만 남기면 아무도 안 쓰는데 영구 오탐만 낸다.
APSCHEDULER_MARKERS = [
    'schedule_map = {',
    '"06": (6, 0)',
    '"12": (12, 0)',
    '"21": (21, 0)',
    '"23": (23, 0)',
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
    # 배10011(2026-07-24) — "Ops" 문자열이 NOTIFY_SHAPED_HINTS에 우연히 걸린 오탐 확인.
    # monthly_ops_sync.py 코드 직접 확인: 텔레그램/알림 호출 0건(순수 데이터 동기화 작업).
    'Wellperion-MonthlyOps-Sync-Daily',
}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[WARN] {path} 로드 실패: {e}", file=sys.stderr)
        return None


def main(write_json=None):
    as_json = write_json if write_json is not None else '--json' in sys.argv

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

    # ── 3-2) daily_scheduler 발신 잡 → 등록부 커버 확인 (2026-08-12 시토 · 배541) ──
    #   왜: 3번 검사는 **schtasks 예약작업만** 본다. 텔레그램 발신의 대부분은 상주
    #   daily_scheduler 의 apscheduler 잡인데, 그쪽은 2번(마커가 아직 있나)만 있어서
    #   **새 잡이 생겨도 아무 검사에도 안 걸렸다.** 실측 2026-08-12: 웰리가 2026-08-10 에 건
    #   08:00 아침 브리핑·20:30 저녁 정리본이 매일 정상 발송 중인데 등록부엔 없었다 —
    #   자율현황 「알림 한 장」에 안 보이고, 죽어도 아무도 모르는 상태로 이틀 갔다.
    #   판정 = add_job(id="…") 을 긁어 등록부 어느 항목의 job_id 에도 없으면 UNREGISTERED_JOB.
    #   ▸id 를 f-string 등으로 동적 생성하는 잡(끼니 슬롯·시간대 보고)은 긁히지 않는다 —
    #     이 검사가 못 보는 사각이며, 그 잡들은 사람이 등록부에 직접 넣어야 한다.
    NON_NOTIFY_JOBS = {
        # 사람 방으로 아무것도 안 보내는 내부 잡 — 코드 확인 후 제외(이름 휴리스틱 아님)
        'env_reload_watcher',       # .env 변경 감지 재적재
        'erp_status_publisher',     # status/erp_status.json 갱신
        'kpi_collector_morning', 'kpi_collector_evening',  # status/kpi_values.json 갱신
        'parking_revenue_crawler',  # 주차 매출 수집
        'dashboard_cache_warm',     # 회원 목록 캐시 예열
        'push_sweeper',             # 미푸시 커밋 밀어내기
        'queue_archive_sweep',      # 큐 보관함 이동
        'git_lock_janitor_10min',   # 죽은 .git/index.lock 청소
        'test_hourly',              # 스케줄러 생존 표시용 로그 한 줄
        # 2026-09-02 — 이 잡은 원래 30분 무응답 시 체크인을 한 번 더 보냈는데, GM 지적("9:00 에 오고
        # 9:31 에도 중복해서 왔네")으로 재알림을 없앴다. 지금은 1시간 뒤 미응답('M')만 기록하고
        # 아무 방으로도 보내지 않는다 — 그래서 발신 등록부 대상이 아니다.
        'checkin_followup_5min',
        # 아래 3개는 2026-08-12 코드 전수 확인 — 사람 방으로 가는 발신이 0건이다.
        'bot_health_check',         # 실패 시 이 PC 데스크톱 알림창만(local_fallback_alert) · API 발신 없음
        'sales_session_guard_0810', # sales_session_guard.py 에 발신 호출 0건 · 만료 시 로그인 창만 띄움
        'ig_publish_verify_sweep',  # 발행완료 도장+커밋만 · 결과 요약은 ig-publish-multichannel-summary 담당
        'page_ping_collect',        # 화면 열람 흔적을 status/page_ping.json 으로만 낸다 · 발신 없음
    }
    reg_job_ids: set[str] = set()
    for item in reg_items:
        jid = item.get('job_id')
        if isinstance(jid, str):
            reg_job_ids.add(jid)
        elif isinstance(jid, list):
            reg_job_ids.update(str(x) for x in jid)
    if scheduler_src:
        seen_jobs = []
        for m in re.finditer(r'\.add_job\(', scheduler_src):
            seg = scheduler_src[m.end():m.end() + 700]
            j = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', seg)
            if j:
                seen_jobs.append(j.group(1))
        for job_id in sorted(set(seen_jobs)):
            if job_id in reg_job_ids or job_id in NON_NOTIFY_JOBS:
                continue
            mismatches.append({
                'kind': 'UNREGISTERED_JOB',
                'registry_id': None,
                'task_name': job_id,
                'detail': f"daily_scheduler 잡 '{job_id}'이 notify_registry.json 어느 항목의 job_id 에도 "
                          f"없음 — 사람 방으로 보내는 발신이면 등록부에 추가하고, 내부 전용이면 "
                          f"NON_NOTIFY_JOBS 에 근거와 함께 넣는다",
            })

    # ── 4) 등록부 room → 방 SSOT 존재 확인 (2026-08-01 시토 · 배202) ──────────
    #   왜: 방 이름이 등록부·발신 코드·화면에 제각각 적혀 있었다. 실측 3건 —
    #     ①'★운영부'(공백 없음) vs 발신 코드가 실제로 찾는 창 제목 '★ 운영부'(공백 있음)
    #     ②방 칸에 "차의주 회장님·웰페리온 관리부·★운영부(3방)" 같은 문장이 들어가 방 개수가 틀림
    #     ③★중간관리자 는 어디에도 등록 안 된 채 발신만 나감
    #   카톡 전송기는 **창 제목 정확 일치**로 방을 찾으므로 공백 한 칸이 곧 발송 실패다.
    #   새 감시기를 만들지 않고 이미 도는 이 대조기에 얹는다(약속 L21 — 관문에만).
    kakao_rooms = load_json(ROOT / 'scripts' / 'kakao_rooms.json') or {}
    troom = load_json(ROOT / 'status' / 'telegram_rooms.json') or {}
    # all_rooms 는 방 이름 문자열이 들어 있기도 하고 {name: ...} 꼴이기도 하다.
    # ★2026-09-02 — 문자열만 들어 있는 지금 형태에서 이 줄이 터져 대조기 전체가 죽어 있었다
    #   (자율현황 화면엔 「드리프트 9건 · 확인 필요」 경고만 뜬 채 아무도 확인 못 하는 상태).
    #   두 꼴을 다 받는다 — 등록부 형식이 어느 쪽으로 바뀌어도 감시가 멈추지 않는다.
    def _room_name(r):
        return (r.get('name') if isinstance(r, dict) else str(r or '')).strip()

    known_kakao = {n for n in (_room_name(r) for r in (kakao_rooms.get('all_rooms') or [])) if n}
    known_tg = {k for k in troom if not k.startswith('_')}
    for item in reg_items:
        # dead=죽었다고 확정한 것, unknown=방이 어디인지 저장소에서 확인 불가라고 정직 표기한 것.
        # 둘 다 '아직 모른다'를 이미 적어 둔 상태라 매번 다시 걸리면 영구 오탐이 된다(2026-08-01).
        if item.get('state') in ('dead', 'unknown'):
            continue
        ch = item.get('channel')
        known = known_kakao if ch == 'kakao' else (known_tg if ch == 'telegram' else None)
        if known is None:
            continue
        # 한 발신이 여러 방으로 나가면 ' / ' 로 나눠 적는다(문장 금지 — 그래야 셀 수 있다).
        for name in [n.strip() for n in str(item.get('room', '')).split('/') if n.strip()]:
            if name in known:
                continue
            where = 'scripts/kakao_rooms.json all_rooms' if ch == 'kakao' else 'status/telegram_rooms.json'
            mismatches.append({
                'kind': 'ROOM_NOT_IN_SSOT',
                'registry_id': item.get('id'),
                'task_name': name,
                'detail': f"등록부 '{item.get('id')}'의 방 '{name}'이 방 SSOT({where})에 없음 — "
                          f"오타·표기 드리프트이거나 미등록 방(카톡은 창 제목 불일치 = 발송 실패)",
            })

    # ── 4-2) 모듈 등록부의 발신 방(bot_id/bot_room) → 방 SSOT 존재 확인 (2026-08-01) ──
    #   왜: 발신 방 이름이 두 곳에 적힌다 — notify_registry.json(room) 과
    #   module_registry.json(notify_spec.bot_id). 4번 검사는 앞의 것만 봤다.
    #   ★정정(2026-08-01 시토). 이 검사를 넣을 때 근거로 "cmo-publish-digest 의 발송 문이 닫힌 채
    #   5일간 요약이 안 나갔다"고 적었다. **틀렸다.** ①그 모듈은 `module_reporter` 를 거치지 않고
    #   `publish_digest.py` 가 `.env` 로 직접 보낸다 — 여기서 이름을 못 찾아도 발송은 막히지 않는다.
    #   ②안 나간 진짜 이유는 GM 지시(2026-07-27 · 커밋 7c2c5e92f)로 **개인계정(namuk) 발행은
    #   실무진 방 발신에서 제외**됐고, 그 5일간 발행이 전부 개인계정이었기 때문이다(공식계정 0건).
    #   재기 전에 말한 것이 원인이다.
    #   ▸그래서 이 검사가 잡는 범위도 좁다: **`module_reporter.resolve_chat_id` 를 타는 모듈만**
    #     실제로 발송이 막힌다. 그 밖의 모듈은 '이름이 방 목록에 없다'는 표기 불일치일 뿐이다.
    #     검사는 그대로 두되(이름은 맞춰 두는 게 맞다) **막힌다고 단정하지 않는다.**
    mod_reg = load_json(ROOT / 'status' / 'module_registry.json') or {}
    for mod in (mod_reg.get('modules') or []):
        if not mod.get('enabled'):
            continue
        spec = mod.get('notify_spec') or {}
        if spec.get('channel') != 'telegram':
            continue
        room = spec.get('bot_id') or spec.get('bot_room')
        # 숫자로 준 것은 chat_id 그대로라 방 이름 대조 대상이 아니다(resolve_chat_id 와 같은 규칙).
        # None 은 '아직 안 켠 것'이라 결함이 아니다 — 이름을 적었는데 그 방이 없을 때만 잡는다.
        if not isinstance(room, str) or not room or room in known_tg:
            continue
        mismatches.append({
            'kind': 'MODULE_ROOM_NOT_IN_SSOT',
            'registry_id': mod.get('id'),
            'task_name': room,
            'detail': f"모듈 '{mod.get('id')}' 의 발신 방 '{room}' 이 status/telegram_rooms.json 에 없음 — "
                      f"이름을 맞춰야 한다. ※`module_reporter` 를 거쳐 보내는 모듈이면 방 번호를 못 구해 "
                      f"발송이 조용히 막히고, 직접 보내는 모듈이면 표기 불일치다(발송 여부는 별도 확인)",
        })

    # ── 5) 발신 코드가 박아 둔 카톡 방 이름 → 방 SSOT 존재 확인 (2026-08-01 · 배202) ──
    #   등록부만 맞춰 두면 반쪽이다. 실제로 창을 찾아 보내는 건 코드에 박힌 문자열이고,
    #   카톡은 창 제목 정확 일치라 여기 오타 한 칸이 곧 발송 실패다. 코드를 SSOT 를 읽도록
    #   바꾸는 대신(발신 경로 회귀 위험) 대조만 한다 — 어긋나면 여기서 잡힌다.
    CODE_ROOM_CONSTS = [
        ('telegram_bot/daily_scheduler.py', r'KAKAO_DEPTHEAD_ROOM\s*=\s*"([^"]+)"'),
        ('telegram_bot/daily_scheduler.py', r'KAKAO_OPS_ROOM\s*=\s*"([^"]+)"'),
        ('scripts/kakao_summary_card_auto.py', r'TARGET_ROOM\s*=\s*"([^"]+)"'),
        ('scripts/send_ops_digest.py', r'TARGET_ROOM\s*=\s*"([^"]+)"'),
        ('scripts/kakao_report_sender.py', r'CHAIRMAN_ROOM_NAME\s*=\s*"([^"]+)"'),
    ]
    for rel, pat in CODE_ROOM_CONSTS:
        f = ROOT / rel
        if not f.exists():
            continue
        for name in re.findall(pat, f.read_text(encoding='utf-8')):
            if name in known_kakao:
                continue
            mismatches.append({
                'kind': 'CODE_ROOM_NOT_IN_SSOT',
                'registry_id': None,
                'task_name': name,
                'detail': f"{rel} 이 발신 대상으로 쓰는 카톡 방 '{name}'이 "
                          f"scripts/kakao_rooms.json all_rooms 에 없음 — 창 제목 불일치면 발송이 조용히 실패한다",
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
