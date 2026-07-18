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

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = ROOT / "status"
OUT = STATUS_DIR / "erp_status.json"
BRIDGE_LAST = STATUS_DIR / "_bridge_last.json"  # 직전 다리 상태(스팸 방지)
ENV_PATH = ROOT / "telegram_bot" / ".env"

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

    s_state, s_detail = _state_from_minutes(_minutes_since(sched_log))
    items.append({"name": "일일 스케줄러", "state": s_state,
                  "detail": s_detail, "note": "정각 보고를 쏘는 시계"})

    b_mins = _minutes_since(bot_log)
    # 봇 로그는 스케줄러보다 한산할 수 있어 여유 둠
    b_state, b_detail = _state_from_minutes(b_mins, warn_after=180)
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


def _send_telegram(text):
    """텔레그램 1줄 발송. 실패해도 발행에 영향 없게 전부 삼킴."""
    try:
        token, chat = _read_env_token()
        if not token or not chat:
            return False
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def alert_newly_broken(bridges):
    """직전 상태와 비교해 '새로 깨진' 다리만 텔레그램 경고. 같은 깨짐 반복은 무음."""
    try:
        broken_now = {b["name"] for b in bridges if b["state"] == "이상"}
        prev = set()
        if BRIDGE_LAST.exists():
            try:
                prev = set(json.loads(BRIDGE_LAST.read_text(encoding="utf-8")) or [])
            except Exception:
                prev = set()
        newly = broken_now - prev
        if newly:
            details = {b["name"]: b["detail"] for b in bridges}
            lines = [f"🔗 연동 다리 끊김 감지 ({len(newly)}건)"]
            for nm in sorted(newly):
                lines.append(f"⚠️ {nm}: {details.get(nm, '')}")
            _send_telegram("\n".join(lines))
        # 현재 깨진 목록을 상태파일에 저장(복구되면 다음에 재알림 가능)
        try:
            BRIDGE_LAST.write_text(
                json.dumps(sorted(broken_now), ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass
    except Exception:
        pass


def build():
    # 시스템 현황 = '기계 상태'만(봇·스케줄러·예약작업). 각 AI 업무는 G1 오늘의 항로가 단일 출처
    # → 여기서 중복 집계/표시하지 않는다(약속 L01 한 곳만, 2026-06-16 GM 지적).
    systems = collect_processes() + collect_tasks()
    bridges = collect_bridges()
    automation_health = collect_automation_health()
    broken_bridges = [b["name"] for b in bridges if b["state"] == "이상"]
    abnormal = [s["name"] for s in systems if s["state"] == "이상"] + broken_bridges
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
    }


def main():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = build()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[erp_status] wrote {OUT}")
    print(f"[erp_status] summary: {payload['summary']}")

    # 연동 다리 — 새로 깨진 것만 텔레그램 1줄 경고(실패해도 발행 무영향)
    alert_newly_broken(payload.get("bridges", []))

    if "--push" in sys.argv:
        try:
            subprocess.run(["git", "add", str(OUT)], cwd=ROOT, check=True)
            subprocess.run(
                ["git", "commit", "-m",
                 "chore(erp): 시스템 현황 자동 발행 (erp_status.json)"],
                cwd=ROOT, check=True,
            )
            subprocess.run(["git", "pull", "--rebase", "--autostash",
                            "origin", "master"], cwd=ROOT, check=True)
            subprocess.run(["git", "push", "origin", "master"], cwd=ROOT, check=True)
            print("[erp_status] pushed")
        except subprocess.CalledProcessError as e:
            print(f"[erp_status] push skipped/failed: {e}")


if __name__ == "__main__":
    main()
