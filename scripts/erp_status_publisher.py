# -*- coding: utf-8 -*-
"""
ERP 시스템 현황 발행기 (erp_status_publisher)
─────────────────────────────────────────────
서버/로컬에서만 보이던 상태를 ERP가 읽을 수 있는 status/erp_status.json 으로 발행한다.
GM은 파일을 못 여니, 이 한 파일이 ERP "🖥️ 시스템 현황" 섹션의 데이터 소스가 된다.

수집 항목 (※ '기계 상태'만 — 업무/할일은 G1 오늘의 항로가 단일 출처라 여기서 다루지 않음):
  - 텔레그램 봇 / 일일 스케줄러 생존 (로그 파일 최신성)
  - 주요 예약작업 상태 (schtasks, 실패해도 '불명'으로 안전 처리)

사용:
  python scripts/erp_status_publisher.py            # status/erp_status.json 만 갱신
  python scripts/erp_status_publisher.py --push     # 갱신 + git 커밋·푸시 (ERP 반영)

설계 원칙: 모든 수집은 실패해도 '불명'으로 떨어지고 절대 예외로 죽지 않는다(fail-safe).
값은 사람이 바로 읽는 한국어 plain text 로 채운다(약속 L10/L12).
"""
import json
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
    if hb_mins is None:
        b_state, b_detail = "불명", "하트비트 파일 없음(봇 미재기동)"
    elif hb_mins <= 20:
        b_state, b_detail = "정상", f"하트비트 {int(hb_mins)}분 전(생존)"
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

    warn = unpushed > GIT_UNPUSHED_WARN or (
        origin_age_min is not None and origin_age_min > GIT_STALE_WARN_MIN
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
    # 시스템 현황 = '기계 상태'만(봇·스케줄러·예약작업). 각 AI 업무는 G1 오늘의 항로가 단일 출처
    # → 여기서 중복 집계/표시하지 않는다(약속 L01 한 곳만, 2026-06-16 GM 지적).
    systems = collect_processes() + collect_tasks()
    bridges = collect_bridges()
    automation_health = collect_automation_health()
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


def main():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[erp_status] wrote {OUT}")
    print(f"[erp_status] summary: {payload['summary']}")

    # home 히어로 KPI 스냅샷 — 같은 30분 주기에 편승(배9660). 실패해도 erp_status 발행에 무영향.
    home_kpi_ok = publish_home_kpi_snapshot()
    print(f"[erp_status] home_kpi_snapshot: {'갱신' if home_kpi_ok else '실패(기존 유지)'}")

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
