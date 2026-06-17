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
    from integration_health import check_bridges  # 연동 다리 자가점검 단일 정의
except Exception:
    check_bridges = None

# 감시할 예약작업 (작업명 → 사람이 읽을 이름)
WATCH_TASKS = {
    "WellperionTelegramBot": "텔레그램 봇 기동(로그온)",
    "\\Welperion\\Auto-Shutdown-2330": "PC 자동 종료",
}


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


def collect_bridges():
    """연동 다리 점검 → erp_status.json 'bridges' 필드용 리스트. 실패해도 빈 결과."""
    if check_bridges is None:
        return []
    try:
        rows = check_bridges()
    except Exception:
        return []
    return [
        {"name": nm, "state": "정상" if ok else "이상", "detail": detail}
        for nm, ok, detail in rows
    ]


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
