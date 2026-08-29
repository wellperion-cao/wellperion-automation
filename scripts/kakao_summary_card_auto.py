#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/kakao_summary_card_auto.py — 카톡 아침 요약 카드 07:30 무인 발송 오케스트레이터

배경(2026-07-14 CTO, 배906): 매일 09:30 매출 상세 이미지 발송(kakao_auto_daily_report.py, 3방
회장님·관리부·★운영부)과 별개로, 경보·4지표(매출·점검·전환·주차)·미니그래프를 담은
"아침 요약 카드"를 그보다 앞선 07:30에 **카톡 ★운영부 1방에만** 자동 발송한다
(GM go 확정 — 배906 note. 2026-07-14 GM 정정: 발송 대상=운영부 단독, 회장님·관리부 제외).

두 코어 스크립트를 하나의 무인 흐름으로 묶는다(kakao_auto_daily_report.py와 동일 설계):
    1) scripts/kakao_summary_card.py   — 카드 이미지 생성(라이브 SSOT만, 목업 금지)
    2) scripts/kakao_report_sender.py  — 카톡 ★운영부 1방에 전송(이미지만, 캡션 없음 — 카드
       자체가 날짜·브랜드·지표를 전부 담고 있어 별도 캡션 불필요)
    대상 방은 kakao_rooms.json(9:30 매출보고 3방 공용 SSOT)을 건드리지 않고, 이 스크립트
    안에 TARGET_ROOM 상수로 고정한다 — 9:30 매출 시트 보고(3방)는 완전히 별개로 무영향.

킬스위치(역롤백, 절대 원칙): status/kakao_summary_card_send.json 의 {"enabled": true/false}.
    파일이 없거나 enabled != true 면 **무인 스케줄 실행(=--rooms 미지정 실행)** 은 아무
    것도 하지 않고 로그만 남기고 exit 0 한다 — GM go 승인 전 무인 실발송 금지.
    단 --rooms 로 방을 직접 지정한 실행(검증·부분전송용)은 킬스위치와 무관하게 즉시
    실행한다(수동 검증까지 막으면 안전검증 자체가 불가능해지므로).
    가장 확실한 역롤백 2단: ①이 파일을 enabled:false로 되돌리면 다음 실행부터 즉시
    중단, ②Task Scheduler에서 Wellperion-Kakao-Morning-Card-0730 예약 자체를 삭제/비활성화.

사용:
    python scripts/kakao_summary_card_auto.py                          # 무인 실행(킬스위치 게이트, 운영부 1방 실발송)
    python scripts/kakao_summary_card_auto.py --dry-run --rooms "김남욱" # 수동 검증(게이트 무시, 미전송)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # 발신 관문(best-effort) — 임포트 실패해도 경보 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = Path(__file__).resolve().parent / "kakao_summary_card.py"
SENDER_SCRIPT = Path(__file__).resolve().parent / "kakao_report_sender.py"
ENV_PATH = ROOT / "telegram_bot" / ".env"
KILL_SWITCH_FILE = ROOT / "status" / "kakao_summary_card_send.json"
STATUS_FILE = ROOT / "status" / "kakao_summary_card_last_send.json"

# 발송 대상 = ★운영부 1방 단독(2026-07-14 GM 정정 — 회장님·관리부 제외).
# 9:30 매출보고 3방 공용 kakao_rooms.json은 건드리지 않고 여기서 고정한다.
TARGET_ROOM = "★운영부"  # 2026-08-04 시토: SSOT(kakao_rooms.json)와 표기 일치 — 발송 자체는 _title_key
# 정규화로 공백 무관하게 되지만, 등록부 드리프트 체커(notify_registry_check.py)가 SSOT 표기와
# 다르면 CODE_ROOM_NOT_IN_SSOT로 매번 걸린다(발송 실패 아님 — 표기 정합 문제만 수정).


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _load_env(path: Path) -> dict:
    env: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception as exc:
        log(f"[경고] .env 읽기 실패: {exc}")
    return env


def send_owner_alert(message: str) -> None:
    """OWNER 텔레그램 DM으로 실패 경보(best-effort)."""
    try:
        env = _load_env(ENV_PATH)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        owner_id = env.get("OWNER_ID") or env.get("TELEGRAM_CHAT_ID", "")
        if not token or not owner_id:
            log("[경고] TELEGRAM_BOT_TOKEN/OWNER_ID(.env) 없음 — 경보 발송 생략")
            return
        ok = _tg_send(token, int(owner_id), message, source="kakao_summary_card_auto.send_owner_alert", timeout=15)
        log("OWNER 텔레그램 경보 발송 완료" if ok else "[경고] 경보 발송 실패")
    except Exception as exc:
        log(f"[경고] 경보 발송 예외(무시): {exc}")


def kill_switch_enabled() -> bool:
    """status/kakao_summary_card_send.json 의 enabled 필드. 파일 없음/파싱 실패=False(안전측 기본값)."""
    try:
        cfg = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("enabled", False))
    except Exception:
        return False


def write_status(ok: bool, detail: str) -> None:
    """status/kakao_summary_card_last_send.json 갱신 — kakao_auto_daily_report.py의
    write_status와 동일 스키마({ok, detail, at})."""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(
            json.dumps(
                {
                    "ok": ok,
                    "detail": detail[:300],
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"[경고] status/kakao_summary_card_last_send.json 기록 실패(무시): {exc}")


def _run(cmd: list[str]) -> "tuple[int, str]":
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _parse_tag(output: str, tag: str) -> "str | None":
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith(tag):
            return line[len(tag):].strip()
    return None


def generate_card() -> "tuple[bool, str]":
    """kakao_summary_card.py 실행. 반환: (성공여부, IMAGE경로 또는 실패사유)."""
    cmd = [sys.executable, str(GEN_SCRIPT)]
    log(f"카드 생성 실행: {' '.join(cmd)}")
    rc, output = _run(cmd)
    print(output, end="" if output.endswith("\n") else "\n")
    image_path = _parse_tag(output, "IMAGE:")
    if rc == 0 and image_path:
        return True, image_path
    reason = _parse_tag(output, "FAILED:") or "알 수 없는 오류(카드 생성 단계)"
    return False, reason


def run_sender(rooms: "list[str] | None", image_path: str, dry_run: bool) -> "tuple[bool, list[str]]":
    """rooms=None → 기본 대상(TARGET_ROOM=★운영부 1방)으로 발송. rooms=[...] → 지정된
    방마다 --only-room 반복 호출(검증용, 다른 방 지정 가능). 캡션 없음(카드 자체가
    날짜·지표를 전부 담고 있음 — 별도 텍스트 메시지 불필요)."""
    failures: list[str] = []
    targets = rooms if rooms else [TARGET_ROOM]
    for room in targets:
        # --sender 아침요약카드 — kakao_report_sender 사람 방 발신 가드(배 11070 ⑤) 통과용.
        cmd = [sys.executable, str(SENDER_SCRIPT), "--image", image_path, "--caption", "", "--only-room", room,
               "--sender", "아침요약카드"]
        if dry_run:
            cmd.append("--dry-run")
        label = room
        log(f"카톡 전송 실행[{label}]: {' '.join(cmd)}")
        rc, output = _run(cmd)
        print(output, end="" if output.endswith("\n") else "\n")
        tail = output.strip().splitlines()[-1] if output.strip() else "출력 없음"
        log(f"카톡 전송 결과[{label}]: rc={rc} tail={tail}")
        if rc != 0 or "DONE:" not in output:
            failures.append(f"{label}: {tail}")
    return (len(failures) == 0), failures


def main() -> int:
    ap = argparse.ArgumentParser(description="카톡 아침 요약 카드 07:30 무인 발송 오케스트레이터")
    ap.add_argument("--rooms", default=None,
                     help="콤마구분 방 이름(검증·부분전송용). 지정 시 킬스위치와 무관하게 즉시 실행")
    ap.add_argument("--dry-run", action="store_true", help="sender에 --dry-run 전달(실전송 안 함)")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("FAILED: 이 스크립트는 Windows 전용입니다.")
        return 1

    rooms = [r.strip() for r in args.rooms.split(",") if r.strip()] if args.rooms else None

    if rooms is None:
        if not kill_switch_enabled():
            log(f"킬스위치 OFF({KILL_SWITCH_FILE} 없음 또는 enabled=false) — 무인 실행 생략(아무 작업 안 함)")
            print("SKIPPED: 킬스위치 비활성 — 아무 작업도 하지 않음")
            return 0
        log(f"킬스위치 ON — 무인 발송 진행 (대상: {TARGET_ROOM})")
    else:
        log(f"--rooms 지정({rooms}) — 킬스위치와 무관하게 즉시 실행(수동 검증 모드)")

    ok, image_or_reason = generate_card()
    if not ok:
        msg = f"⚠️ 카톡 아침 요약 카드 자동 파이프라인 실패 — 카드 생성 단계: {image_or_reason}"
        log(msg)
        send_owner_alert(msg)
        print(f"FAILED: 카드 생성 실패 — {image_or_reason}")
        return 1
    image_path = image_or_reason
    log(f"카드 생성 성공: {image_path}")

    ok, failures = run_sender(rooms, image_path, args.dry_run)
    if ok:
        detail = "DRY-RUN 검증 완료" if args.dry_run else f"{TARGET_ROOM} 전송 완료" if rooms is None else f"{rooms} 전송 완료"
        write_status(True, detail)
        msg = f"DONE: 카톡 아침 요약 카드 {'검증(dry-run)' if args.dry_run else '전송'} 완료 — {detail}"
        log(msg)
        print(msg)
        return 0
    else:
        detail = "; ".join(failures)
        write_status(False, detail)
        send_owner_alert(f"⚠️ 카톡 아침 요약 카드 자동 발송 실패 — {detail}")
        print(f"FAILED: 카톡 전송 실패 — {detail}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
