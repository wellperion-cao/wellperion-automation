#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/kakao_auto_daily_report.py — 카톡 매출보고 9시 무인 발송 오케스트레이터

배경(2026-07-07 CTO): 두 코어 스크립트를 하나의 무인 흐름으로 묶는다.
    1) scripts/generate_sales_report_image.py — 텔레그램 사진 없이 이미지 자체 생성
    2) scripts/kakao_report_sender.py         — 카톡 방(들)에 전송
    이 오케스트레이터가 09:00 예약작업(Task Scheduler)에 등록되면 텔레그램 버튼 탭 없이도
    완전자동 3방 발송이 가능해진다.

킬스위치(역롤백, 절대 원칙): status/kakao_auto_send.json 의 {"enabled": true/false}.
    파일이 없거나 enabled != true 면 **무인 스케줄 실행(=--rooms 미지정 실행)** 은 아무
    것도 하지 않고 로그만 남기고 exit 0 한다 — GM go 승인 전 무인 실발송 금지.
    단 --rooms 로 방을 직접 지정한 실행(검증·부분전송용)은 킬스위치와 무관하게 즉시
    실행한다(수동 검증까지 막으면 안전검증 자체가 불가능해지므로).

흐름:
    1) generate_sales_report_image.py 실행 → stdout `IMAGE: <경로>` 파싱.
       실패(FAILED: 또는 파싱 실패)면 OWNER 텔레그램 경보 + exit 1.
    2) 성공 시 caption 자동 생성(보고 대상일=오늘-1일, "M.D(요일) 매출 및 운영사항
       보고드립니다.") 후 kakao_report_sender.py 실행.
       --rooms 지정 시 방마다 --only-room 반복 호출(콤마구분), 미지정 시 옵션 없이
       3방 일괄 1회 호출. --dry-run 은 그대로 sender에 전달.
    3) sender가 DONE이면 status/kakao_last_send.json 갱신(있으면 재사용) + 정상 로그.
       실패(BLOCKED/일부 방 실패)면 OWNER 텔레그램에 실패 방·사유 1줄 경보.

휴관일 인지(2026-07-07 CTO, GM 확정 규칙 · 배488): 보고 대상일(=기준일-1일)이
    휴관일(신정·설날·추석·매월 2·4째 일요일 — scripts/close_days.py 판정)이면 이미지
    생성·전송을 건너뛰고, 대신 "M.D(요일)은(는) 휴관일이었습니다. …" 안내문 텍스트만
    3방에 전송한다(kakao_report_sender.py --message 경로). 정상 영업일이면 기존 이미지
    경로 그대로.

사용:
    python scripts/kakao_auto_daily_report.py                          # 무인 실행(킬스위치 게이트, 3방 실발송)
    python scripts/kakao_auto_daily_report.py --dry-run --rooms "김남욱" # 수동 검증(게이트 무시, 미전송)
    python scripts/kakao_auto_daily_report.py --as-of 20260112 --dry-run --rooms "김남욱"  # 특정 기준일 시뮬레이션
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from close_days import is_closed, next_business_day  # noqa: E402

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = Path(__file__).resolve().parent / "generate_sales_report_image.py"
SENDER_SCRIPT = Path(__file__).resolve().parent / "kakao_report_sender.py"
ENV_PATH = ROOT / "telegram_bot" / ".env"
KILL_SWITCH_FILE = ROOT / "status" / "kakao_auto_send.json"
STATUS_FILE = ROOT / "status" / "kakao_last_send.json"

_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── .env 직독(하드코딩 금지) — scripts/telegram_health_check.py와 동일 방식 ──────────
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
        import requests
        env = _load_env(ENV_PATH)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        owner_id = env.get("OWNER_ID") or env.get("TELEGRAM_CHAT_ID", "")
        if not token or not owner_id:
            log("[경고] TELEGRAM_BOT_TOKEN/OWNER_ID(.env) 없음 — 경보 발송 생략")
            return
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(owner_id), "text": message},
            timeout=15,
        )
        if resp.status_code != 200 or not resp.json().get("ok", False):
            log(f"[경고] 경보 발송 실패: status={resp.status_code} body={resp.text[:200]}")
        else:
            log("OWNER 텔레그램 경보 발송 완료")
    except Exception as exc:
        log(f"[경고] 경보 발송 예외(무시): {exc}")


def kill_switch_enabled() -> bool:
    """status/kakao_auto_send.json 의 enabled 필드. 파일 없음/파싱 실패=False(안전측 기본값)."""
    try:
        cfg = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("enabled", False))
    except Exception:
        return False


def write_status(ok: bool, detail: str, kind: str = "IMAGE_REPORT") -> None:
    """status/kakao_last_send.json 갱신 — telegram_bot/bot.py의 _write_kakao_status와 동일 스키마
    ({ok, detail, at}) 재사용, T2 카톡전송관리 페이지가 이 파일을 그대로 읽는다.
    kind: "IMAGE_REPORT"(정상 이미지 보고, 기본값) 또는 "HOLIDAY_NOTICE"(휴관 안내문만 전송)."""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(
            json.dumps(
                {
                    "ok": ok,
                    "detail": detail[:300],
                    "kind": kind,
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"[경고] status/kakao_last_send.json 기록 실패(무시): {exc}")


def build_caption(target_date: datetime) -> str:
    """보고 대상일(통상 오늘-1일) 기준 "M.D(요일) 매출 및 운영사항 보고드립니다." 생성."""
    weekday_kr = _WEEKDAY_KR[target_date.weekday()]
    return f"{target_date.month}.{target_date.day}({weekday_kr}) 매출 및 운영사항 보고드립니다."


def build_holiday_notice(target: datetime, as_of: datetime) -> str:
    """보고 대상일(target=기준일-1일)이 휴관일일 때의 안내문 생성.

    biz = 기준일(as_of)부터 첫 영업일(=휴관 지나 다음 보고 대상이 될 날).
    resume = biz+1일부터 첫 영업일(=biz분 매출을 실제로 보고하게 될 날).
    예) target=6/28(일, 휴관) → biz=6/29(월) → resume=6/30(화)
        "6/28(일)은 휴관일이었습니다. 화요일에 월요일분부터 이어서 매출·운영사항
        보고드리겠습니다."
    """
    target_md = f"{target.month}/{target.day}"
    target_dow = _WEEKDAY_KR[target.weekday()]
    biz = next_business_day(as_of)
    resume = next_business_day(biz + timedelta(days=1))
    biz_dow = _WEEKDAY_KR[biz.weekday()]
    resume_dow = _WEEKDAY_KR[resume.weekday()]
    return (
        f"{target_md}({target_dow})은(는) 휴관일이었습니다. {resume_dow}요일에 "
        f"{biz_dow}요일분부터 이어서 매출·운영사항 보고드리겠습니다."
    )


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


def generate_image() -> "tuple[bool, str]":
    """generate_sales_report_image.py 실행. 반환: (성공여부, IMAGE경로 또는 실패사유)."""
    cmd = [sys.executable, str(GEN_SCRIPT)]
    log(f"이미지 생성 실행: {' '.join(cmd)}")
    rc, output = _run(cmd)
    print(output, end="" if output.endswith("\n") else "\n")
    image_path = _parse_tag(output, "IMAGE:")
    if rc == 0 and image_path:
        return True, image_path
    reason = _parse_tag(output, "FAILED:") or "알 수 없는 오류(이미지 생성 단계)"
    return False, reason


def run_sender(rooms: "list[str] | None", image_path: str, caption: str, dry_run: bool) -> "tuple[bool, list[str]]":
    """rooms=None → 옵션 없이 3방 일괄 1회 호출. rooms=[...] → 방마다 --only-room 반복 호출."""
    failures: list[str] = []
    targets = rooms if rooms else [None]
    for room in targets:
        cmd = [sys.executable, str(SENDER_SCRIPT), "--image", image_path, "--caption", caption]
        if dry_run:
            cmd.append("--dry-run")
        if room:
            cmd.extend(["--only-room", room])
        label = room or "전체(3방 일괄)"
        log(f"카톡 전송 실행[{label}]: {' '.join(cmd)}")
        rc, output = _run(cmd)
        print(output, end="" if output.endswith("\n") else "\n")
        tail = output.strip().splitlines()[-1] if output.strip() else "출력 없음"
        log(f"카톡 전송 결과[{label}]: rc={rc} tail={tail}")
        if rc != 0 or "DONE:" not in output:
            failures.append(f"{label}: {tail}")
    return (len(failures) == 0), failures


def run_sender_message(rooms: "list[str] | None", message: str, dry_run: bool) -> "tuple[bool, list[str]]":
    """휴관일 안내문 전용 — kakao_report_sender.py를 --message로 호출(이미지 경로 없음).
    rooms=None → 옵션 없이 3방 일괄 1회 호출. rooms=[...] → 방마다 --only-room 반복 호출."""
    failures: list[str] = []
    targets = rooms if rooms else [None]
    for room in targets:
        cmd = [sys.executable, str(SENDER_SCRIPT), "--message", message]
        if dry_run:
            cmd.append("--dry-run")
        if room:
            cmd.extend(["--only-room", room])
        label = room or "전체(3방 일괄)"
        log(f"카톡 안내문 전송 실행[{label}]: {' '.join(cmd)}")
        rc, output = _run(cmd)
        print(output, end="" if output.endswith("\n") else "\n")
        tail = output.strip().splitlines()[-1] if output.strip() else "출력 없음"
        log(f"카톡 안내문 전송 결과[{label}]: rc={rc} tail={tail}")
        if rc != 0 or "DONE:" not in output:
            failures.append(f"{label}: {tail}")
    return (len(failures) == 0), failures


def main() -> int:
    ap = argparse.ArgumentParser(description="카톡 매출보고 9시 무인 발송 오케스트레이터")
    ap.add_argument("--rooms", default=None,
                     help="콤마구분 방 이름(검증·부분전송용). 지정 시 킬스위치와 무관하게 즉시 실행")
    ap.add_argument("--dry-run", action="store_true", help="sender에 --dry-run 전달(실전송 안 함)")
    ap.add_argument("--as-of", default=None, metavar="YYYYMMDD",
                     help="실행 기준일(기본=오늘). 시뮬레이션·테스트용 — 보고 대상일=기준일-1일")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("FAILED: 이 스크립트는 Windows 전용입니다.")
        return 1

    rooms = [r.strip() for r in args.rooms.split(",") if r.strip()] if args.rooms else None

    try:
        as_of = datetime.strptime(args.as_of, "%Y%m%d") if args.as_of else datetime.now()
    except ValueError:
        print(f"FAILED: --as-of 형식 오류(YYYYMMDD 필요): {args.as_of!r}")
        return 1

    if rooms is None:
        if not kill_switch_enabled():
            log(f"킬스위치 OFF({KILL_SWITCH_FILE} 없음 또는 enabled=false) — 무인 실행 생략(아무 작업 안 함)")
            print("SKIPPED: 킬스위치 비활성 — 아무 작업도 하지 않음")
            return 0
        log("킬스위치 ON — 무인 3방 발송 진행")
    else:
        log(f"--rooms 지정({rooms}) — 킬스위치와 무관하게 즉시 실행(수동 검증 모드)")

    target = as_of - timedelta(days=1)
    log(f"기준일(as_of)={as_of.strftime('%Y-%m-%d')} / 보고 대상일(target)={target.strftime('%Y-%m-%d')}")

    if is_closed(target):
        notice = build_holiday_notice(target, as_of)
        log(f"휴관일 분기 — 안내문: {notice!r}")

        ok, failures = run_sender_message(rooms, notice, args.dry_run)
        if ok:
            detail = f"휴관 안내문 발송 완료 — {notice}"
            write_status(True, detail, kind="HOLIDAY_NOTICE")
            msg = f"DONE: 카톡 {'검증(dry-run)' if args.dry_run else '전송'} 완료(휴관 안내문) — {notice}"
            log(msg)
            print(msg)
            return 0
        else:
            detail = "; ".join(failures)
            write_status(False, detail, kind="HOLIDAY_NOTICE")
            send_owner_alert(f"⚠️ 카톡 휴관 안내문 자동 발송 실패 — {detail}")
            print(f"FAILED: 카톡 휴관 안내문 전송 실패 — {detail}")
            return 1

    ok, image_or_reason = generate_image()
    if not ok:
        msg = f"⚠️ 카톡 매출보고 자동 파이프라인 실패 — 이미지 생성 단계: {image_or_reason}"
        log(msg)
        send_owner_alert(msg)
        print(f"FAILED: 이미지 생성 실패 — {image_or_reason}")
        return 1
    image_path = image_or_reason
    log(f"이미지 생성 성공: {image_path}")

    caption = build_caption(target)
    log(f"caption: {caption!r}")

    ok, failures = run_sender(rooms, image_path, caption, args.dry_run)
    if ok:
        detail = "DRY-RUN 검증 완료" if args.dry_run else "3방 전송 완료" if rooms is None else f"{rooms} 전송 완료"
        write_status(True, detail)
        msg = f"DONE: 카톡 {'검증(dry-run)' if args.dry_run else '전송'} 완료 — {detail}"
        log(msg)
        print(msg)
        return 0
    else:
        detail = "; ".join(failures)
        write_status(False, detail)
        send_owner_alert(f"⚠️ 카톡 매출보고 자동 발송 실패 — {detail}")
        print(f"FAILED: 카톡 전송 실패 — {detail}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
