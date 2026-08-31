# -*- coding: utf-8 -*-
"""
ERP 시스템 현황 발행기 (erp_status_publisher)
─────────────────────────────────────────────
서버/로컬에서만 보이던 상태를 ERP가 읽을 수 있는 status/erp_status.json 으로 발행한다.
GM은 파일을 못 여니, 이 한 파일이 ERP "🖥️ 시스템 현황" 섹션의 데이터 소스가 된다.

수집 항목 (※ '기계 상태'만 — AI 업무/할일은 자율현황 🧭 항로가 단일 출처라 여기서 다루지 않음.
           G1 은 2026-08-05 부로 GM 개인 판만 남았다 · 자율화규약 v1.1 부칙 1):
  - 텔레그램 봇 / 일일 스케줄러 생존 (로그 파일 최신성)
  - 주요 예약작업 상태 (schtasks, 실패해도 '불명'으로 안전 처리)

사용:
  python scripts/erp_status_publisher.py            # status/erp_status.json 만 갱신
  python scripts/erp_status_publisher.py --push     # 갱신 + git 커밋·푸시 (ERP 반영)

설계 원칙: 모든 수집은 실패해도 '불명'으로 떨어지고 절대 예외로 죽지 않는다(fail-safe).
값은 사람이 바로 읽는 한국어 plain text 로 채운다(약속 L10/L12).
"""
import json
import re
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # 발신 관문(best-effort) — 임포트 실패해도 발행 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
OUT = STATUS_DIR / "erp_status.json"
BRIDGE_LAST = STATUS_DIR / "_bridge_last.json"  # 직전 다리 상태(스팸 방지)
ENV_PATH = ROOT / "telegram_bot" / ".env"

# home 히어로 KPI 서버측 스냅샷 (배9660, 2026-07-27 시토 — GM 2026-07-25 착수 승인).
# 신규 예약작업 없이 이 발행기의 기존 30분 주기(daily_scheduler.py IntervalTrigger)에
# 편승한다(L21 net-zero). 콜드/시크릿 첫 로드가 home_kpi GAS 라이브 집계(7~8.6초)를
# 기다리지 않고 GitHub raw(~수십ms)로 먼저 그려지게 하기 위함. 정확성은 무손상 —
# 프론트가 이 스냅샷으로 먼저 페인트한 뒤 반드시 라이브 값으로 덮어써 갱신한다.
HOME_KPI_GAS_URL = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
HOME_KPI_OUT = STATUS_DIR / "home_kpi_snapshot.json"

sys.path.insert(0, str(ROOT / "scripts"))
try:
    from integration_health import check_bridges, check_queue_mirror  # 연동 다리 자가점검 단일 정의
except Exception:
    check_bridges = None
    check_queue_mirror = None
try:
    import sync_queue_mirror  # 큐 미러 단방향·멱등 동기화(자가치유용)
except Exception:
    sync_queue_mirror = None
try:
    import notify_registry_check as _nrc  # 알림 등록부 드리프트 체커(배NOTI, 2026-08-01)
except Exception:
    _nrc = None

# 감시할 예약작업 (작업명 → 사람이 읽을 이름)
WATCH_TASKS = {
    "WellperionTelegramBot": "텔레그램 봇 기동(로그온)",
    "\\Welperion\\Auto-Shutdown-2330": "PC 자동 종료",
}

# 알려진 양성(benign) 스케줄러 결과코드 — '정상인데 실패로 보이는 착오'만 정직 재분류한다.
# 정직 원칙: 진짜 실패는 그대로 '실패'로 둔다. 아래는 (1) 업데이트 결과가 이중경로로 검증되고
# (Start-AI CEO.bat 이 claude_update.log 로 매일 실수행) (2) bat 이 설계상 fail-soft(항상 exit 0)인
# 자동-업데이트 작업이, 프로세스 종료코드와 무관한 '스케줄러-레벨 거절/종료'(0x800710E0=operator
# refused)를 last_result 로 흘리는 경우에 한정. 이 작업이 다른 코드로 실패하면 여전히 '실패'로 뜬다.
BENIGN_SKIP_TASKS = ("wellperion-morning-update",)
BENIGN_SKIP_CODES = {0x800710E0}  # The operator or administrator has refused the request


def _now_kst():
    return datetime.now(KST)


def _minutes_since(path: Path):
    """파일 최종 수정으로부터 경과 분. 없으면 None."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, KST)
        return (_now_kst() - mtime).total_seconds() / 60.0
    except Exception:
        return None


def _state_from_minutes(mins, warn_after=35):
    """로그 경과 분 → 정상/이상/불명."""
    if mins is None:
        return "불명", "기록 없음"
    if mins <= warn_after:
        return "정상", f"{int(mins)}분 전 활동"
    return "이상", f"{int(mins)}분째 조용함"


# 봇 기동 직후 하트비트 첫 갱신을 기다려 주는 창(분). 하트비트 주기는 300초라
# 두 번 놓칠 만큼만 준다 — 더 길면 진짜 폴링 정지를 그만큼 늦게 잡는다.
_BOT_START_GRACE_MIN = 10
_BOT_START_MARK = "Bot starting."
_BOT_LOG_TAIL_BYTES = 65536   # 기동 줄은 항상 로그 끝쪽에 있다 — 전체를 읽지 않는다


def _bot_start_minutes_ago(bot_log: Path):
    """bot.log 의 마지막 'Bot starting.' 줄이 몇 분 전인지. 못 찾으면 None."""
    try:
        with open(bot_log, "rb") as f:
            f.seek(0, 2)  # 파일 끝으로
            f.seek(max(0, f.tell() - _BOT_LOG_TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if _BOT_START_MARK not in line:
            continue
        try:
            stamp = datetime.strptime(line.split(" | ")[0].split(",")[0],
                                      "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        except (ValueError, IndexError):
            return None
        return (_now_kst() - stamp).total_seconds() / 60.0
    return None


def collect_processes():
    items = []
    sched_log = ROOT / "telegram_bot" / "scheduler.log"
    bot_log = ROOT / "telegram_bot" / "bot.log"
    bot_heartbeat = ROOT / "telegram_bot" / "bot_heartbeat.txt"

    s_state, s_detail = _state_from_minutes(_minutes_since(sched_log))
    items.append({"name": "일일 스케줄러", "state": s_state,
                  "detail": s_detail, "note": "정각 보고를 쏘는 시계"})

    # 봇 생존 판정 = 하트비트(bot_heartbeat.txt) 신선도 단일 기준(2026-07-22 수정).
    # 이전엔 bot.log mtime(outbound 발신)으로 판정해 정기 발신 없는 낮 시간대
    # 정상 무발신을 '이상(🔴)'으로 오탐(510분째 조용함 → 점검 필요). '조용함≠죽음' —
    # 폴링 생존은 bot.py 가 5분마다 갱신하는 하트비트로만 확인 가능(getMe는
    # API 도달성만 봄, 폴링 생존은 못 봄). 기준(20분=4회 미갱신 → 폴링 정지
    # 의심)은 telegram_health_check.py _HEARTBEAT_STALE_MIN 과 동일 재사용
    # (배102, 2026-07-03 CTO).
    hb_mins = _minutes_since(bot_heartbeat)
    boot_mins = _bot_start_minutes_ago(bot_log)
    if hb_mins is None:
        b_state, b_detail = "불명", "하트비트 파일 없음(봇 미재기동)"
    elif hb_mins <= 20:
        b_state, b_detail = "정상", f"하트비트 {int(hb_mins)}분 전(생존)"
    elif boot_mins is not None and boot_mins <= _BOT_START_GRACE_MIN:
        # ★2026-08-16 시토 — 기동 직후 유예. 이 PC 는 00:30 에 꺼지고 05:55 에 켜진다.
        #   재기동 직후엔 어제 밤에 멈춘 하트비트가 그대로 남아 있어 "329분째 미갱신"으로
        #   보인다 — 봇은 멀쩡히 방금 떴는데 GM 이 ERP 를 열면 매일 아침 가짜 경보를 본다
        #   (자가점검 실측 2026-08-16 · bot.log 기동 이력 90회 전부 05:56대).
        #   가짜 경보가 매일 뜨면 진짜 경보도 안 읽히므로 여기서 없앤다.
        #   ▸판정 근거는 bot.log 의 "Bot starting." 줄 시각이다 — 파일 mtime 이 아니다.
        #     mtime 은 낮 시간대 발신에도 갱신돼, 폴링만 죽고 발신은 도는 진짜 사고
        #     (INC-011)를 이 유예가 덮어 버린다. 기동 줄은 그 부류에 안 흔들린다.
        b_state = "정상"
        b_detail = (f"기동 {int(boot_mins)}분 전 — 하트비트 첫 갱신 대기(유예 "
                    f"{_BOT_START_GRACE_MIN}분)")
    else:
        b_state, b_detail = "이상", f"하트비트 {int(hb_mins)}분째 미갱신(폴링 정지 의심)"

    # outbound 무발신(bot.log)은 참고 정보로만 붙인다 — 단독으로 이상 승격 금지.
    out_mins = _minutes_since(bot_log)
    if out_mins is not None:
        b_detail += f" · 최근 발신 {int(out_mins)}분 전"

    items.append({"name": "텔레그램 봇", "state": b_state,
                  "detail": b_detail, "note": "보고·승인 중계"})
    return items


def collect_tasks():
    items = []
    for task, label in WATCH_TASKS.items():
        state, detail = "불명", "조회 실패"
        try:
            r = subprocess.run(
                ["schtasks", "/query", "/tn", task, "/fo", "LIST"],
                capture_output=True, text=True, timeout=15,
            )
            out = (r.stdout or "") + (r.stderr or "")
            if "Ready" in out or "준비" in out:
                state, detail = "정상", "예약됨(준비)"
            elif "Running" in out or "실행" in out:
                state, detail = "정상", "실행 중"
            elif "Disabled" in out or "사용 안 함" in out:
                state, detail = "이상", "꺼져 있음"
            elif r.returncode != 0:
                state, detail = "불명", "작업 없음/권한"
        except Exception:
            pass
        items.append({"name": label, "state": state, "detail": detail})
    return items


# git 푸시 동기화 판정 기준값 — 한 곳(2026-07-30 GM 승인). 미푸시가 이 값 초과거나
# origin 최신 커밋이 이만큼(분) 넘게 과거면 '경고'. (2026-07-30 실측: 42→64건까지 밀리며
# 약 4시간 아무 화면에도 안 보였다 — 이 기준이면 30분 안에 잡힌다.)
GIT_UNPUSHED_WARN = 10
GIT_STALE_WARN_MIN = 60


def collect_git_sync():
    """git 푸시 동기화 상태 — 미푸시 커밋 수 · origin 최신 커밋 시각 · 판정.
    ★새 fetch 를 강제하지 않는다(GM 지시 2026-07-30 — 부하 추가 금지). post_commit_push.py
    워처가 이미 수시로 fetch 하므로 로컬에 남아 있는 origin/master ref 를 그대로 읽는다
    (부하 0 추가). 조회 자체가 실패하면 '불명'으로 떨어진다(정상으로 위장하지 않음)."""
    try:
        r = subprocess.run(
            ["git", "rev-list", "--count", "origin/master..HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return {"state": "불명", "detail": "미푸시 조회 실패", "unpushed": None, "origin_at": None}
        unpushed = int((r.stdout or "0").strip() or "0")
    except Exception:
        return {"state": "불명", "detail": "미푸시 조회 실패", "unpushed": None, "origin_at": None}

    origin_at_str = None
    origin_age_min = None
    try:
        r2 = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "origin/master"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        if r2.returncode == 0 and (r2.stdout or "").strip():
            origin_at_str = r2.stdout.strip()
            origin_dt = datetime.fromisoformat(origin_at_str)
            origin_age_min = (_now_kst() - origin_dt.astimezone(KST)).total_seconds() / 60.0
    except Exception:
        pass

    # ★2026-08-16 시토 — origin 지연은 **올릴 게 남아 있을 때만** 경고다.
    #   미푸시가 0이면 로컬과 origin 이 같다 = 막힌 게 없다. 그런데도 "origin 최신 N분 전"
    #   하나로 경고를 띄우던 탓에, 아무도 커밋하지 않는 밤(PC 00:30 종료 · 05:55 기동)이
    #   지나면 매일 아침 ERP 가 경고를 달고 떴다(자가점검 실측 2026-08-16 — 같은 화면의
    #   bridges 는 "미푸시 없음·정상"이라 두 칸이 서로 어긋나 보였다).
    #   이 지연 기준이 원래 잡으려던 것은 "push 배관이 죽어 커밋이 밀린다"이고, 그건
    #   정의상 미푸시가 있어야 성립한다.
    warn = unpushed > GIT_UNPUSHED_WARN or (
        unpushed > 0 and origin_age_min is not None and origin_age_min > GIT_STALE_WARN_MIN
    )
    state = "경고" if warn else "정상"
    age_txt = f"{int(origin_age_min)}분 전" if origin_age_min is not None else "확인 불가"
    return {
        "state": state,
        "detail": f"미푸시 {unpushed}건 · origin 최신 {age_txt}",
        "unpushed": unpushed,
        "origin_at": origin_at_str,
    }


def _self_heal_queue_mirror():
    """큐 미러 드리프트 자가치유: sync_queue_mirror(단방향·멱등) 자동 실행.
    실패해도 예외를 삼킨다(fail-soft) — 실패 시 재확인에서 여전히 '이상'으로 남을 뿐."""
    if sync_queue_mirror is None:
        return
    try:
        sync_queue_mirror.main()
    except Exception:
        pass


def collect_bridges():
    """연동 다리 점검 → erp_status.json 'bridges' 필드용 리스트. 실패해도 빈 결과.

    큐 미러 드리프트(GM 피드백 2026-07-18): 알림 전에 먼저 자가치유를 시도한다.
    '큐 미러 동기' 다리가 '이상'이면 sync_queue_mirror 를 자동 실행 → 재점검.
    치유되면 조용히 '정상'으로 반영(알림 없음). 치유 실패(진짜 이상)면 '이상' 그대로
    남아 alert_newly_broken() 이 기존 경로(GM 개인봇 1줄)로만 알린다 — 실무진 방 금지.
    """
    if check_bridges is None:
        return []
    try:
        rows = check_bridges()
    except Exception:
        return []
    healed: list[tuple[str, bool, str]] = []
    for nm, ok, detail in rows:
        if not ok and nm == "큐 미러 동기" and check_queue_mirror is not None:
            _self_heal_queue_mirror()
            try:
                nm2, ok2, detail2 = check_queue_mirror()
                if ok2:
                    detail2 = "드리프트 감지 → 자가치유 완료(자동 동기화) — " + detail2
                nm, ok, detail = nm2, ok2, detail2
            except Exception:
                pass
        healed.append((nm, ok, detail))
    return [
        {"name": nm, "state": "정상" if ok else "이상", "detail": detail}
        for nm, ok, detail in healed
    ]


def _live_task_names():
    """현재 Task Scheduler 에 '실존'하는 작업 leaf 이름 집합(소문자).
    권위 있는 현행 목록 = Get-ScheduledTask(모던 CIM API). 삭제됐지만 legacy schtasks 뷰에
    남는 손상/고아(orphaned) 등록 = 유령. 유령은 이 집합에 없으므로 걷어낼 수 있다.
    조회 실패 시 None → 호출부는 필터를 적용하지 않는다(안전: 멀쩡한 작업 오삭제 방지).
    """
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-ScheduledTask | Select-Object -ExpandProperty TaskName"],
            capture_output=True, text=True, timeout=30,
        )
        names = {ln.strip().lower() for ln in (r.stdout or "").splitlines() if ln.strip()}
        return names or None
    except Exception:
        return None


def collect_archive_summary():
    """완료 보관함 요약 3개(총건수·입항완료·마지막 정리시각).

    ★2026-07-31 시토(GM '자율현황도 항상 단순화') — 자율현황 화면이 이 세 숫자를 얻으려고
      `status/_queue_archive.json` **3.2MB 를 통째로 내려받고 있었다.** 그 화면이 한 번 열릴 때
      받는 3.86MB 중 83%가 이 한 파일이었다(실측). 쓰는 것은 arr.length · DONE 개수 ·
      가장 최근 processed_at 셋뿐인데 3,162건 전체를 실어 나른 것이다.
      → 여기(이미 30분마다 도는 발행기)에서 미리 세어 erp_status.json 에 담는다. 화면은
        이미 그 파일을 받고 있으므로 **새 파일도 새 요청도 늘지 않는다**(약속 L21).
      읽기 실패해도 None 을 돌려 화면이 종전 경로로 폴백하게 둔다(무중단).
    """
    try:
        p = ROOT / "status" / "_queue_archive.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else (raw.get("items") or [])
        if not isinstance(items, list):
            return None
        done = sum(1 for t in items if isinstance(t, dict) and t.get("status") == "DONE")
        latest = ""
        for t in items:
            if not isinstance(t, dict):
                continue
            v = str(t.get("processed_at") or "")
            if v > latest:
                latest = v
        return {"total": len(items), "done": done, "latest_processed_at": latest}
    except Exception:
        return None


_SCHEDULER_SRC = Path(__file__).resolve().parent.parent / "telegram_bot" / "daily_scheduler.py"
_JOB_ID_RE = re.compile(r"""add_job\((?:.|\n){0,600}?id\s*=\s*['"]([^'"]+)['"]""")


def collect_scheduler_jobs():
    """상주 스케줄러(daily_scheduler)가 들고 있는 정기 작업 목록.

    ★왜 여기 붙였나(배39 · 2026-08-13): 자동화는 두 곳에서 돈다 —
      ①윈도우 예약작업(schtasks) ②상주 스케줄러 안의 정기 작업.
      화면은 지금까지 ①만 셌다. 그래서 "자동화 30개"라고 적혀 있어도 실제로는
      그보다 훨씬 많이 돌고 있었고, ②가 통째로 멈춰도 화면 숫자는 안 변했다.
      **새 등록부는 만들지 않는다** — 스케줄러 소스에 이미 있는 등록 목록을 그대로 읽는다.
    """
    try:
        src = _SCHEDULER_SRC.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return {"count": 0, "items": [], "note": "스케줄러 소스를 못 읽었습니다"}
    ids = []
    for m in _JOB_ID_RE.finditer(src):
        jid = m.group(1)
        if jid not in ids:
            ids.append(jid)
    return {"count": len(ids), "items": ids, "note": ""}


def collect_automation_health():
    """Task Scheduler Wellperion 작업 → 자동화 건강 집계.
    결과코드 0 = 정상, 0 아님 = 실패, 한 번도 안 돎(1999년 기본값) = 미실행.
    측정 불가·schtasks 실패 시 fail-safe로 빈 결과 반환(전체 발행 안 깨짐).
    """
    NEVER_RUN_YEAR = "1999"  # schtasks 기본값 — 한 번도 안 돎
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/fo", "LIST", "/v"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0 and not r.stdout:
            return {"summary": "집계 중 (schtasks 조회 실패)", "total": 0,
                    "healthy": 0, "rate": 0, "items": []}

        # 블록 분리 (각 작업은 '호스트 이름:' 행으로 시작)
        blocks = []
        cur = []
        for line in r.stdout.split("\n"):
            s = line.strip()
            if s.startswith("호스트 이름:") or s.startswith("Host Name:"):
                if cur:
                    blocks.append("\n".join(cur))
                cur = [line]
            else:
                cur.append(line)
        if cur:
            blocks.append("\n".join(cur))

        def _field(block, *keys):
            """블록에서 첫 매칭 필드 값 추출."""
            for line in block.split("\n"):
                for key in keys:
                    if key in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            return parts[1].strip()
            return ""

        items = []
        for block in blocks:
            name = _field(block, "작업 이름:", "Task Name:")
            if not name:
                continue
            # 작업명에 wellperion(대소문자 무관) 포함된 것만
            if "wellperion" not in name.lower():
                continue

            last_result_raw = _field(block, "마지막 결과:", "Last Result:")
            last_run = _field(block, "마지막 실행 시간:", "Last Run Time:")
            next_run = _field(block, "다음 실행 시간:", "Next Run Time:")

            # 분류
            if not last_result_raw:
                state = "불명"
                last_result_code = None
            else:
                try:
                    code = int(last_result_raw)
                    last_result_code = code
                    # 1999년 기본값 = 한 번도 안 돎
                    if NEVER_RUN_YEAR in last_run:
                        # next_run에 실제 미래 예정 시각이 있으면 = 정상 대기(월간 등)
                        # sentinel(없음/비활성) 포함 시에만 진짜 '미실행'
                        never_sentinels = (NEVER_RUN_YEAR, "N/A", "해당 없음", "사용 안 함", "없음")
                        has_real_next_run = bool(next_run) and not any(
                            s in next_run for s in never_sentinels
                        )
                        state = "대기" if has_real_next_run else "미실행"
                    elif code == 0:
                        state = "정상"
                    elif (any(t in name.lower() for t in BENIGN_SKIP_TASKS)
                          and (code & 0xFFFFFFFF) in BENIGN_SKIP_CODES):
                        # 정상인데 스케줄러가 비0으로 흘리는 알려진 양성 코드 → 정직 재분류
                        state = "정상(건너뜀)"
                    else:
                        state = "실패"
                except ValueError:
                    state = "불명"
                    last_result_code = last_result_raw

            items.append({
                "name": name.lstrip("\\"),
                "state": state,
                "last_run": last_run,
                "last_result": last_result_code,
                "next_run": next_run,
            })

        # 유령 배제: 삭제됐지만 legacy schtasks 뷰에 남은 손상/고아 등록을 걷어낸다.
        # 라이브 존재하는 작업만 발행(권위 목록=Get-ScheduledTask). 조회 실패 시 필터 미적용(안전).
        live = _live_task_names()
        if live is not None:
            items = [it for it in items
                     if it["name"].split("\\")[-1].lower() in live]

        total = len(items)
        healthy = sum(1 for i in items if i["state"] in ("정상", "대기", "정상(건너뜀)"))
        rate = round(healthy / total * 100) if total > 0 else 0
        summary = f"자동화 {healthy}/{total} 정상 ({rate}%)"

        return {
            "summary": summary,
            "total": total,
            "healthy": healthy,
            "rate": rate,
            "items": items,
        }
    except Exception as e:
        return {"summary": f"집계 중 (오류: {e})", "total": 0,
                "healthy": 0, "rate": 0, "items": []}


def _read_env_token():
    """telegram_bot/.env 직독 → (token, chat_id). 실패 시 (None, None)."""
    token = chat = None
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat = line.split("=", 1)[1].strip()
    except Exception:
        pass
    return token, chat


def _send_telegram(text, kind="tech_check"):
    """텔레그램 1줄 발송. 실패해도 발행에 영향 없게 전부 삼킴.

    ★2026-07-24 GM 지시: '연동 다리 끊김' 같은 점검 결과는 **확인방(자동화현황방)** 으로.
      GM 이 손으로 할 일이 아니라 기계가 스스로 확인한 결과라, GM 업무보고방에 섞이면
      정작 결정해야 할 건이 묻힌다. 분류 판단은 scripts/alert_router.py 한 곳(약속 L01).
    """
    try:
        token, chat = _read_env_token()
        if not token or not chat:
            return False
        try:
            import sys as _sys
            from pathlib import Path as _P
            _sys.path.insert(0, str(_P(__file__).resolve().parent))
            from alert_router import route
            chat = route(kind)
        except Exception:
            pass  # 라우터를 못 읽으면 기존 대상 유지 — 알림 자체를 잃지 않는다
        return _tg_send(token, chat, text, source="erp_status_publisher._send_telegram", timeout=10)
    except Exception:
        return False


def _bridge_sig(name: str, detail: str) -> str:
    import hashlib
    return hashlib.sha256(f"{name}|{detail}".encode("utf-8")).hexdigest()[:16]


def alert_newly_broken(bridges):
    """직전과 같은 (다리, 사유) **내용**이면 재발신하지 않는다 — 시간 쿨다운이 아니라
    내용-지문(2026-08-04 웰리 판정). 확인: 08-03 21:18·22:17 같은 사유(시트 GAS
    todo_list 타임아웃) 1시간 간격 재경보는 실측으로 플래핑(20:47 정상 → 21:18 이상
    → 22:17 이상 재검출 → 22:47 정상, git log status/erp_status.json 3커밋 확인)이었다
    — 옛 로직(상태-전이만 보는 dedup)은 복구→재발이면 매번 '새로 깨짐'으로 재알렸는데,
    사람이 보기엔 몇 분 새 같은 사유가 반복 도배되는 것과 다를 바 없다. 사유가 바뀌거나
    복구 후 다른 사유로 재발하면 즉시 다시 알린다. BRIDGE_LAST를 '깨진 이름 목록'에서
    '이름→지문' 으로 바꿔 이 판정을 그대로 흡수 — 새 상태파일 없음."""
    try:
        broken_now = {b["name"]: b.get("detail", "") for b in bridges if b["state"] == "이상"}
        prev_sigs = {}
        if BRIDGE_LAST.exists():
            try:
                raw = json.loads(BRIDGE_LAST.read_text(encoding="utf-8"))
                prev_sigs = raw if isinstance(raw, dict) else {}  # 구 형식(list)은 폐기 — 새로 시작
            except Exception:
                prev_sigs = {}

        new_sigs, to_alert = {}, []
        for name, detail in broken_now.items():
            sig = _bridge_sig(name, detail)
            new_sigs[name] = sig
            if prev_sigs.get(name) != sig:
                to_alert.append((name, detail))

        if to_alert:
            lines = [f"🔗 연동 다리 끊김 감지 ({len(to_alert)}건)"]
            for nm, detail in sorted(to_alert):
                lines.append(f"⚠️ {nm}: {detail}")
            _send_telegram("\n".join(lines))
        # 복구된 다리는 new_sigs에서 자연히 빠짐 → 다음에 같은 사유로 재발해도 다시 알림
        try:
            BRIDGE_LAST.write_text(json.dumps(new_sigs, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    except Exception:
        pass


def fetch_home_kpi():
    """home_kpi GAS 라이브 호출(fail-safe). 실패 시 None — 호출부가 기존 파일을 보존한다."""
    try:
        url = HOME_KPI_GAS_URL + "?action=home_kpi&_pv=" + str(int(_now_kst().timestamp()))
        req = urllib.request.Request(url, headers={"User-Agent": "wellperion-erp-publisher"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("ok"):
            return data
        return None
    except Exception:
        return None


def fetch_sales_month_in_progress():
    """당월 '진행중' 누적 매출 — ★운영부 아침 정리(ops_daily_digest)가 이미 쓰는 sales_month 재사용.

    home 매출 정본(AV열)은 달이 끝나야 채워져 당월엔 항상 null → 히어로가 "이번달 미마감"으로
    굳는다(2026-08-03 GM 지적). 같은 값을 이미 매일 정확히 뽑고 있는 소스를 그대로 실어 보낸다
    — 새 엔드포인트·새 헬퍼 없음(약속 L21). 실패는 None(정직 — 숫자 위조 금지).
    """
    try:
        from collectors.ops_shared import gas_get
        from ops_daily_digest import PROC_EXEC_URL, _proc_password

        pw = _proc_password()
        if not pw:
            print("[erp_status] sales_month_in_progress: 실패 — 처리방 비밀번호 없음")
            return None
        # attempts=1 고정(2026-08-06 시토) — gas_get 기본 재시도는 3회라 이 한 호출만으로
        #   최대 3×60=180초가 되어 호출부(daily_scheduler.py 의 timeout=150)를 단독으로 넘겼다.
        #   실측: 이 작업은 매시간 도는데 누적 150초 타임아웃 184회. 당월 매출은 다음 회차에
        #   회복되는 값이라 여기서 물고 늘어질 이유가 없다 — 한 번 시도하고 없으면 비운다.
        resp = gas_get(
            PROC_EXEC_URL, {"action": "sales_month", "password": pw},
            timeout=40, attempts=1, label="home_kpi 당월매출",
        )
        if resp is None:
            print("[erp_status] sales_month_in_progress: 실패 — GAS 응답 없음")
            return None
        d = resp.json()
        if not d.get("ok"):
            print(f"[erp_status] sales_month_in_progress: 실패 — GAS ok=false({d.get('error')})")
            return None
        m = _now_kst().month
        v = (d.get("total") or [None] * 12)[m - 1]
        if v is None:
            print(f"[erp_status] sales_month_in_progress: 실패 — {m}월 값 없음(null)")
            return None
        return {
            "month": m,
            "value": int(v),
            "source": "sales_month(월별 매출보고 말일탭 Y70:Y80) — 마감 전 진행중 누적",
            "asOf": _now_kst().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print(f"[erp_status] sales_month_in_progress: 예외 — {e}")
        return None


def kr_amt(n) -> str:
    """한국식 금액 표기: 271488886 → '2억 7,148만'. ERP home krAmt와 동일 규칙.

    정본(2026-08-08 배446) — 같은 규칙을 각 보고기가 따로 갖고 있으면 표기가 어긋난다(약속 L01).
    """
    try:
        n = round(float(n))
    except (TypeError, ValueError):
        return "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    eok = n // 100000000
    man = (n % 100000000) // 10000
    if eok > 0 and man > 0:
        return f"{sign}{eok}억 {man:,}만"
    if eok > 0:
        return f"{sign}{eok}억"
    if man > 0:
        return f"{sign}{man:,}만"
    return f"{sign}{n:,}원"


def read_sales_month_display() -> tuple[str, bool]:
    """이달 매출 표시값 — (금액문자열, 진행중여부). 값이 없으면 ('—', False).

    왜 있나(2026-08-08 배446 · GM 지적 "8시에 온 내용도 이달 매출은 안나오네"):
      home_kpi 의 sales.month 는 '마감 정본'(AV열)이라 달이 끝나야 채워진다. 8월 들어
      6일 연속으로 08시 보고 매출란이 '—' 로 나갔고, 09:30 ★운영부 보고는 아예
      '[연동 예정]' 문자열이었다. 값 자체는 sales.monthInProgress 로 이미 매일 수집돼
      스냅샷에 들어 있는데 보고기들이 그 칸을 안 읽었다.
      2026-08-03 에 ERP 히어로 화면만 고치고 같은 값을 쓰는 다른 소비자를 안 찾은 결과다.

    마감값이 있으면 그것을 쓰고(진행중=False), 없을 때만 당월 진행중 누적으로 떨어진다.
    진행중 값은 '이번 달 것'일 때만 쓴다 — 달이 바뀌었는데 지난달 누적이 남아 있으면 버린다.
    소비자는 진행중=True 면 '(진행 중)' 같은 표시를 붙여 마감 매출과 구분한다.
    """
    try:
        snap = json.loads(HOME_KPI_OUT.read_text(encoding="utf-8"))
        sales = ((snap.get("data") or {}).get("sales")) or {}
    except Exception:
        return "—", False
    return pick_sales_month(sales, _now_kst().month)


def pick_sales_month(sales: dict, cur_month: int) -> tuple[str, bool]:
    """read_sales_month_display 의 판정만 떼어낸 순수 함수 — 파일을 안 읽는다.

    자기검사 = scripts/test_sales_month_display.py (달 바뀜 경계가 이 함수의 유일한 위험).
    """
    if sales.get("month") is not None:
        return kr_amt(sales["month"]), False
    mip = sales.get("monthInProgress") or {}
    if mip.get("value") is not None and mip.get("month") == cur_month:
        return kr_amt(mip["value"]), True
    return "—", False


def publish_home_kpi_snapshot():
    """home 히어로 KPI 스냅샷 발행 — status/home_kpi_snapshot.json.

    실패해도 예외를 삼키고 기존 파일을 그대로 둔다(옛 값이라도 '스냅샷임을 표시한 옛 값'이
    유지되는 게, 파일이 통째로 사라져 '—'로 굳는 것보다 안전). 성공 시에만 최신화한다.
    """
    try:
        data = fetch_home_kpi()
        if data is None:
            return False
        # 당월 진행중 누적 — 프론트가 "이번달 미마감" 대신 실제 숫자를 띄우는 데 쓴다.
        # AV열(마감 정본)은 손대지 않는다 — 달이 마감되면 기존 hasCurMonth 분기로 자동 승계.
        mip = fetch_sales_month_in_progress()
        if isinstance(data.get("sales"), dict):
            if mip is not None:
                data["sales"]["monthInProgress"] = mip
            else:
                # 이번 회차 조회 실패 — 직전 스냅샷의 당월값을 승계(조용한 승계 금지, 배347).
                prev_mip = None
                try:
                    prev = json.loads(HOME_KPI_OUT.read_text(encoding="utf-8"))
                    prev_mip = prev.get("data", {}).get("sales", {}).get("monthInProgress")
                except Exception:
                    prev_mip = None
                if prev_mip is not None:
                    data["sales"]["monthInProgress"] = prev_mip
                    print(f"[erp_status] home_kpi: 당월매출 조회 실패 — 직전 스냅샷 값 승계"
                          f"(asOf={prev_mip.get('asOf')})")
                else:
                    print("[erp_status] home_kpi: 당월매출 조회 실패, 승계할 직전 값도 없음 — 비움")
        now = _now_kst()
        payload = {
            "_doc": "home 히어로 KPI 서버측 스냅샷 단일 출처. erp_status_publisher.py가 30분 주기로 발행. "
                    "프론트는 이 값으로 먼저 페인트(스냅샷 표시) 후 반드시 라이브로 덮어써 갱신한다.",
            "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_at_kst": now.strftime("%Y-%m-%d %H:%M"),
            "data": data,
        }
        HOME_KPI_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def build():
    # 시스템 현황 = '기계 상태'만(봇·스케줄러·예약작업). 각 AI 업무는 자율현황 🧭 항로가 단일 출처
    # → 여기서 중복 집계/표시하지 않는다(약속 L01 한 곳만, 2026-06-16 GM 지적).
    systems = collect_processes() + collect_tasks()
    bridges = collect_bridges()
    automation_health = collect_automation_health()
    # 예약작업 옆에 스케줄러 정기작업 수를 같이 실어 보낸다(배39) — 한 화면에서 둘 다 세도록.
    automation_health["scheduler_jobs"] = collect_scheduler_jobs()
    git_sync = collect_git_sync()
    broken_bridges = [b["name"] for b in bridges if b["state"] == "이상"]
    abnormal = [s["name"] for s in systems if s["state"] == "이상"] + broken_bridges
    if git_sync["state"] == "경고":
        abnormal.append("git 푸시 동기화")
    if abnormal:
        summary = "⚠️ 점검 필요: " + ", ".join(abnormal)
    elif any(s["state"] == "불명" for s in systems):
        summary = "대체로 정상 (일부 확인 불가)"
    else:
        summary = "✅ 전체 정상"
    now = _now_kst()
    return {
        "_doc": "ERP 시스템 현황 단일 출처. erp_status_publisher.py 가 발행. ERP가 읽어 표시.",
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "systems": systems,
        "bridges": bridges,
        "automation_health": automation_health,
        "git_sync": git_sync,
        "archive_summary": collect_archive_summary(),
    }


# home 카드가 쓰는 GAS 주소 — 화면(wellperion_guide(main).html)과 같은 것을 본다.
# 다른 주소를 쓰면 대조가 대조가 아니게 된다(약속 L01).
RECEPTION_GAS = "https://script.google.com/macros/s/AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7jVm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec"
TODO_GAS = "https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
CHECK_GAS = "https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec"

KPI_CROSSCHECK_OUT = STATUS_DIR / "home_kpi_crosscheck.json"


def _kpi_crosscheck_rules():
    """home 카드 안에서 서로 맞아떨어져야 하는 관계만 모은다.

    ★2026-08-26 GM 물음 "이제 home에 있는 데이터를 믿어도 되는거지?" 에 대한 장치다.
      그날 하루에만 기준이 어긋난 곳이 3군데 나왔고(유형별 큰숫자가 누적 / 상단 3칸이 전체 기준 /
      시설부 안전 카테고리가 이름 변경으로 두 줄로 갈림) 전부 GM 이 먼저 발견하셨다.
      공통점은 '한 카드 안에서 기준이 둘로 갈렸다' 는 것이다 — 그건 원천을 몰라도 잡을 수 있다.
      합이 맞는지만 보면 된다.
    ▸새 감시 스크립트·새 예약작업을 만들지 않는다(약속 L21). 이미 30분마다 도는 이 발행기에 얹는다.
    ▸판정은 '원천 대 원천'이다 — 화면 DOM 을 읽지 않는다. 화면이 이 원천을 그대로 그리므로,
      원천에서 합이 안 맞으면 화면도 안 맞는다.
    """
    import datetime as _dt
    import urllib.request as _ur

    ym = _dt.date.today().strftime("%Y-%m")
    out = []

    def _get(url):
        return json.loads(_ur.urlopen(url, timeout=60).read().decode("utf-8"))

    # ① 종합접수처 — 이번달 접수 = 미처리 + 처리중 + 완료, 그리고 유형별 합 = 이번달 접수
    try:
        d = _get(RECEPTION_GAS + "?action=reg_board")
        rows = d.get("data") or []
        mon = [r for r in rows if str(r.get("createdAt") or "")[:7] == ym]
        by = lambda st: len([r for r in mon if (r.get("status") or r.get("상태")) == st])
        parts = by("접수") + by("처리중") + by("완료")
        out.append({"card": "종합접수처", "what": "이번달 접수 = 미처리+처리중+완료",
                    "left": len(mon), "right": parts, "ok": len(mon) == parts})
        cats = {}
        for r in mon:
            cats[r.get("category") or r.get("카테고리") or ""] = cats.get(r.get("category") or r.get("카테고리") or "", 0) + 1
        out.append({"card": "종합접수처", "what": "유형별 합 = 이번달 접수",
                    "left": sum(cats.values()), "right": len(mon), "ok": sum(cats.values()) == len(mon)})
    except Exception as e:
        out.append({"card": "종합접수처", "what": "조회 실패", "error": f"{type(e).__name__}: {e}", "ok": None})

    # ② 업무 카드 — 전체 = 진행 + 완료 + 보류 (이번달·전체 두 벌 다)
    try:
        rows = _get(TODO_GAS + "?action=todo_list").get("data") or []
        staff = ["이경연 실장", "나우열M", "최준용M", "임정은M", "윤병현AM", "백승화 사원", "이정헌 소장"]
        is_staff = lambda o: any(x.strip() in staff for x in str(o or "").split(","))
        st = lambda r: str(r.get("상태") or "진행중").strip()
        cr = lambda r: str(r.get("생성일") or "")[:10]
        alls = [r for r in rows if is_staff(r.get("담당자"))]
        for label, arr in (("전체", alls), ("이번달", [r for r in alls if cr(r)[:7] == ym])):
            parts = (len([r for r in arr if st(r) not in ("완료", "보류")])
                     + len([r for r in arr if st(r) == "완료"])
                     + len([r for r in arr if st(r) == "보류"]))
            out.append({"card": "업무 현황", "what": f"{label} 합계 = 진행+완료+보류",
                        "left": len(arr), "right": parts, "ok": len(arr) == parts})
    except Exception as e:
        out.append({"card": "업무 현황", "what": "조회 실패", "error": f"{type(e).__name__}: {e}", "ok": None})

    # ③ 시설부 점검 카테고리 분리 검사는 2026-08-31 에 제거했다.
    #    이 검사는 2026-08-26 의 실사고('F 안전' 과 'F 안전(AI초안)' 이 두 줄로 서서 새 줄이
    #    0% 로 보였다)를 잡으려고 붙였다. 같은 날 시설부 체계.html 이 fmMergeCats() 로
    #    렌더 단계에서 접미사를 떼고 합치게 됐고, 그 병합은 카테고리 이름을 가리지 않는다 —
    #    앞으로 어느 카테고리가 갈려도 화면에는 한 줄로만 뜬다. 사람이 보는 화면에서 사고가
    #    재현될 수 없게 된 것이다.
    #    반면 시트 원본은 지난 기록 보존을 위해 두 줄을 일부러 남긴다(비파괴). 그래서 이 검사는
    #    고칠 수도 없고 고쳐서도 안 되는 상태를 매일 '어긋남 1건'으로 띄웠다 — 늘 켜져 있는
    #    경보는 읽히지 않는 경보라 다른 진짜 어긋남까지 같이 묻는다.

    # ④ 지원부 월간 이슈 — 「이슈 원문 보기 (N건)」 표제의 건수와 펼침 목록(세션 단위 병합) 행수가
    #    서로 다른 값인데 라벨이 하나만 보여줘 불일치처럼 읽혔다(2026-08-26 감사·57건 vs 34행).
    #    이제 두 화면 모두 total·sessionsWithIssue 두 숫자를 같이 적는다(지원부 체계.html) —
    #    여기서는 서버가 돌려주는 sessionsWithIssue 가 실제 list 길이와 맞는지만 본다(내적 정합).
    try:
        d = _get(CHECK_GAS + f"?action=monthly_report&dept=support&month={ym}")
        issues = d.get("issues") or {}
        list_len = len(issues.get("list") or [])
        swi = issues.get("sessionsWithIssue")
        out.append({"card": "지원부 점검", "what": "이슈 sessionsWithIssue = 펼침 목록 행수",
                    "left": swi, "right": list_len, "ok": (swi == list_len)})
    except Exception as e:
        out.append({"card": "지원부 점검", "what": "조회 실패", "error": f"{type(e).__name__}: {e}", "ok": None})

    # ④ 전사일정 — 저장소 파일과 화면이 읽는 서버 사본이 같은가
    #    2026-08-31 GM 지적("크롬창에 계속 반영이 안 되어 있어"). 이 화면은 저장소 파일을 밑그림으로만
    #    쓰고 실제 값은 GAS 서버 사본에서 읽는다. 그래서 파일에만 적으면 화면에는 영영 안 뜨는데,
    #    적은 사람은 적었으니 됐다고 믿는다 — 그날 딜라이브 일정 변경이 정확히 그렇게 사라져 있었고,
    #    같은 자리에서 웰리와 시토가 각각 한 번씩 걸렸다. 건수만 대조해도 이 부류는 전부 잡힌다.
    #    (규칙 수는 늘지 않는다 — 같은 날 없앤 시설부 카테고리 헛경보 자리를 이 검사가 대신한다.)
    try:
        # 주소는 화면이 들고 있는 것 하나만 쓴다 — 여기 또 적으면 두 벌이 되고, 배포가 바뀌면
        # 한쪽만 옛 주소로 남아 이 검사가 조용히 '못 잼'으로 빠진다(약속 L01).
        _page = (ROOT / "3. 웰페리온 가이드" / "coo" / "check" / "전사_일정.html").read_text(encoding="utf-8")
        _gas = re.search(r'SCHEDULE_GAS_URL\s*=\s*"([^"]+)"', _page).group(1)
        srv = _get(_gas + "?action=load_schedule&cb=1")
        srv_n = len(((srv.get("data") or {}).get("items")) or [])
        repo_n = len(json.loads(
            (ROOT / "status" / "schedule_ssot.json").read_text(encoding="utf-8")).get("items") or [])
        out.append({"card": "전사일정", "what": "저장소 파일 = 화면이 읽는 서버 사본",
                    "left": repo_n, "right": srv_n, "ok": (repo_n == srv_n),
                    "detail": ("" if repo_n == srv_n else
                               "파일에만 적고 서버에 안 올린 일정이 있습니다 — 화면에는 안 뜹니다")})
    except Exception as e:
        out.append({"card": "전사일정", "what": "조회 실패", "error": f"{type(e).__name__}: {e}", "ok": None})

    return out


def publish_kpi_crosscheck():
    """home 카드의 내적 정합을 재고 status/home_kpi_crosscheck.json 에 남긴다.

    어긋난 것이 있으면 아침 자가점검(hangro_board 부팅 슬라이스)이 이 파일을 읽어 표에 올린다 —
    GM 이 먼저 발견하는 구조를 끊는 것이 목적이다(약속 L20).
    """
    try:
        rows = _kpi_crosscheck_rules()
    except Exception as e:
        print(f"[erp_status] kpi_crosscheck: 실패({e}) — 기존 파일 유지")
        return False
    bad = [r for r in rows if r.get("ok") is False]
    err = [r for r in rows if r.get("ok") is None]
    payload = {
        "_doc": "home 카드 내적 정합 대조 — 한 카드 안에서 합이 맞는지만 본다(원천 대 원천). "
                "erp_status_publisher 가 30분마다 갱신. 어긋나면 아침 자가점검이 표에 올린다.",
        "generated_at_kst": _now_kst().strftime("%Y-%m-%d %H:%M"),
        "checked": len(rows), "mismatch": len(bad), "unmeasured": len(err),
        "rows": rows,
    }
    KPI_CROSSCHECK_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[erp_status] kpi_crosscheck: {len(rows)}건 중 어긋남 {len(bad)}건 · 못 잼 {len(err)}건")
    return True


def main():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[erp_status] wrote {OUT}")
    print(f"[erp_status] summary: {payload['summary']}")

    # home 히어로 KPI 스냅샷 — 같은 30분 주기에 편승(배9660). 실패해도 erp_status 발행에 무영향.
    home_kpi_ok = publish_home_kpi_snapshot()
    print(f"[erp_status] home_kpi_snapshot: {'갱신' if home_kpi_ok else '실패(기존 유지)'}")

    # home 카드 내적 정합 대조 — 같은 30분 주기에 편승(2026-08-26 GM 지시). 새 예약작업 없음(L21).
    publish_kpi_crosscheck()

    # 알림 등록부 드리프트 체크 — 30분 주기에 편승(배NOTI, 2026-08-01 시토). 신규 예약작업 없음(L21).
    if _nrc is not None:
        try:
            _nrc.main(write_json=True)
            print("[erp_status] notify_registry_check: 갱신")
        except Exception as e:
            print(f"[erp_status] notify_registry_check: 실패({e})")

    # 연동 다리 — 새로 깨진 것만 텔레그램 1줄 경고(실패해도 발행 무영향)
    alert_newly_broken(payload.get("bridges", []))

    if "--push" in sys.argv:
        try:
            # ★커밋에 반드시 경로를 준다(`-- <path>`). 2026-07-20 시포.
            #   경로 없는 `git commit`은 '인덱스에 올라와 있는 것 전부'를 커밋한다. 이 저장소는 여러 세션이
            #   동시에 작업하는 공용 워킹트리라, 남이 staged 해둔 낡은 파일까지 딸려 들어간다.
            #   실제 사고: f155761d 가 낡은 membership.html을 함께 커밋해 CPO 화면 수정(b8b1e3e7)을 통째로 되돌림.
            #   `-- <path>`를 주면 그 경로의 '워킹트리 내용만' 커밋하고 인덱스는 건드리지 않는다.
            commit_paths = [str(OUT)]
            if HOME_KPI_OUT.exists():
                commit_paths.append(str(HOME_KPI_OUT))
                # 신규 파일(첫 발행)은 아직 미추적 상태라 `git commit -- <path>`만으로는 안 잡힌다.
                # 특정 경로만 add(=safe — `-A`처럼 남의 staged 변경을 끌어들이지 않음).
                subprocess.run(["git", "add", str(HOME_KPI_OUT)], cwd=ROOT, check=False)
            drift_out = STATUS_DIR / "notify_drift.json"
            if drift_out.exists():
                commit_paths.append(str(drift_out))
            subprocess.run(
                ["git", "commit", "-m",
                 "chore(erp): 시스템 현황 자동 발행 (erp_status.json)",
                 "--"] + commit_paths,
                cwd=ROOT, check=True,
            )
            # ★--autostash 제거(2026-07-29 시토 · INC-034 뿌리): 공유 작업트리에서 pop 이
            #   충돌하면 남의 미커밋 변경이 stash 에 갇힌 채 트리가 되돌아가고도 exit 0 이 난다.
            #   더러우면 당기지 않는다 — 이번 회차 push 가 non-ff 로 실패해도 다음 회차에 회복되지만,
            #   사라진 남의 일은 회복되지 않는다. 구현·근거 = scripts/git_lock.pull_rebase_safe.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from git_lock import pull_rebase_safe  # noqa: E402
            pull_rebase_safe(str(ROOT), str(ROOT), "erp_status_publisher")
            # timeout(2026-08-06 시토) — 네트워크 왕복이 무제한 대기라 호출부의 150초를
            #   통째로 잡아먹을 수 있었다. 못 밀면 다음 회차가 회복한다(발행 파일은 이미 커밋됨).
            subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=True, timeout=45)
            print("[erp_status] pushed")
        except subprocess.TimeoutExpired as e:
            print(f"[erp_status] push timeout — 다음 회차에 재시도: {e}")
        except subprocess.CalledProcessError as e:
            print(f"[erp_status] push skipped/failed: {e}")


if __name__ == "__main__":
    main()
