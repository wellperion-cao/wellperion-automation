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
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from close_days import is_closed, next_business_day  # noqa: E402
from generate_sales_report_image import profile_chrome_pids  # noqa: E402
try:  # 발신 관문(best-effort) — 임포트 실패해도 경보 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

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
        env = _load_env(ENV_PATH)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        owner_id = env.get("OWNER_ID") or env.get("TELEGRAM_CHAT_ID", "")
        if not token or not owner_id:
            log("[경고] TELEGRAM_BOT_TOKEN/OWNER_ID(.env) 없음 — 경보 발송 생략")
            return
        ok = _tg_send(token, int(owner_id), message, source="kakao_auto_daily_report.send_owner_alert", timeout=15)
        log("OWNER 텔레그램 경보 발송 완료" if ok else "[경고] 경보 발송 실패")
    except Exception as exc:
        log(f"[경고] 경보 발송 예외(무시): {exc}")


def kill_switch_enabled() -> bool:
    """status/kakao_auto_send.json 의 enabled 필드. 파일 없음/파싱 실패=False(안전측 기본값)."""
    try:
        cfg = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("enabled", False))
    except Exception:
        return False


# ── 매출보고 정본 렌더 단일화(배99, 2026-07-25 시토) ─────────────────────────────
# 같은 매출시트를 GAS(매출보고_자동발송.js, ~09:00 텔레그램 사진)와 이 파이프라인
# (generate_sales_report_image.py, 09:30 카톡)이 **각각 따로** 렌더해 왔다(약속 L01 위반형).
# 정본 렌더 = generate_sales_report_image.py 산출물(아카이브 PNG) 하나로 확정 —
# 카톡 방향 재사용(봇이 자기 메시지를 getUpdates로 못 받아 텔레그램 사진의 무인 수신이
# 불가)은 기술적으로 막혀 있어, 가능한 유일한 단일화 방향이 이쪽이다.
# 텔레그램도 같은 PNG를 쓰도록 아래 게이트를 배선한다. 기본 OFF —
# **GAS 09:00 사진 푸시 트리거를 끈 뒤에만** status/kakao_auto_send.json 에
# "telegram_photo": true 로 켠다(이중 발송 방지 · 채널 변경이라 GM go 후 전환).
def telegram_photo_enabled() -> bool:
    """킬스위치 파일의 telegram_photo 필드(기본 false=GAS가 계속 담당)."""
    try:
        cfg = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("telegram_photo", False))
    except Exception:
        return False


def send_telegram_photo(image_path: str, caption: str) -> bool:
    """정본 PNG를 텔레그램(GM 보고방)에도 발송 — 기존 사진 관문
    telegram_notifier.TelegramNotifier.send_photo 경유(전역 페이싱+발신 계측 자동 편입, L21)."""
    try:
        agents_dir = str(ROOT / "wellperion-agents")
        if agents_dir not in sys.path:
            sys.path.insert(0, agents_dir)
        from telegram_notifier import TelegramNotifier
        r = TelegramNotifier().send_photo(image_path, caption)
        return bool(isinstance(r, dict) and r.get("ok"))
    except Exception as exc:
        log(f"[경고] 텔레그램 사진 발송 실패(카톡 전송은 계속 진행): {exc}")
        return False


# status/kakao_last_send.json 기록은 더 이상 여기서 하지 않는다(2026-08-04 CTO) — 관문
# kakao_report_sender.py의 write_status()가 단일 기록 지점이다(run_sender/run_sender_message
# 가 --status-file 로 STATUS_FILE 경로를 넘긴다). 이유: 이 래퍼만 상태를 적고 사람이
# kakao_report_sender.py를 직접 불러 재발송하면(09:34 3방 재발송 사고, 2026-08-04) 그
# 결과가 어디에도 안 남아 화면이 옛 실패에 굳어 있었다 — 관문 한 곳으로 옮기면 어느
# 경로로 불러도 같은 파일에 정직하게 반영된다.


# 북극성 대비 블록 헬퍼(_northstar_prefix)는 지웠다 — GM 지시 2026-08-02 로 회장님
# 매출보고에서 이 블록을 빼면서 호출부가 사라졌다. 꺼둔 채 남기면 죽은 코드가 되고
# 나중에 누가 다시 켠다(약속 L21). 블록 자체는 northstar_reach.build_northstar_block()
# 에 그대로 살아 있고, 거기서 매월 1일에만 나가도록 막혀 있다.


def build_caption(target_date: datetime) -> str:
    """보고 대상일(통상 오늘-1일) 기준 "M.D(요일) 매출 및 운영사항 보고드립니다." 한 줄.

    ★북극성 대비 블록을 여기에 넣지 않는다 (GM 지시 2026-08-02).
    기준 = 2026-07-30 자 보고 형식(= 2026-07-31 09:30 발신) — 인사말 한 줄뿐이었다.
    2026-07-31 커밋 05a6d5fd5 가 백그라운드 보고 5종에 북극성 블록을 얹으면서
    이 캡션도 "회장님, 🌟 북극성 대비 — …" 로 시작하고 인사말이 맨 아래로 밀렸다
    (08-01 09:30 발신 1회가 그렇게 나갔다). GM 이 그 형식을 되돌리도록 지시했고,
    북극성 대비는 정비 후 매월 1일에만 별도로 보낸다 — 일일 매출보고에는 안 붙는다."""
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
    # 조사(은/는)는 요일 글자의 받침 유무로 결정 — 월·목·금·일=은 / 화·수·토=는
    josa = "은" if (ord(target_dow) - 0xAC00) % 28 != 0 else "는"
    return (
        f"{target_md}({target_dow}){josa} 휴관일이었습니다. {resume_dow}요일에 "
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


def wait_for_profile_chrome_clear(timeout_sec: int = 60) -> None:
    """이미지 생성이 쓰던 profiles/danggn 크롬이 남아 있으면 발신기가 카톡 창을 포그라운드로
    못 끌어온다(Windows 포그라운드 잠금 — 배348). 고정 sleep 대신 조건 폴링: 정확한 소요시간은
    확정 못 했으므로(추정) 사라지는 즉시 진행, 상한을 넘기면 로그만 남기고 계속한다(안 멈춤)."""
    start = time.time()
    while time.time() - start < timeout_sec:
        if not profile_chrome_pids():
            return
        time.sleep(1.0)
    remaining = profile_chrome_pids()
    if remaining:
        log(f"이미지 생성 크롬 잔존({remaining}) — {timeout_sec}초 대기 후에도 안 사라짐, 그대로 진행")


def run_sender(rooms: "list[str] | None", image_path: str, caption: str, dry_run: bool) -> "tuple[bool, list[str]]":
    """rooms=None → 옵션 없이 3방 일괄 1회 호출. rooms=[...] → 방마다 --only-room 반복 호출."""
    failures: list[str] = []
    targets = rooms if rooms else [None]
    for room in targets:
        cmd = [sys.executable, str(SENDER_SCRIPT), "--image", image_path, "--caption", caption,
               "--status-file", str(STATUS_FILE), "--status-kind", "IMAGE_REPORT"]
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
        cmd = [sys.executable, str(SENDER_SCRIPT), "--message", message,
               "--status-file", str(STATUS_FILE), "--status-kind", "HOLIDAY_NOTICE"]
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
            msg = f"DONE: 카톡 {'검증(dry-run)' if args.dry_run else '전송'} 완료(휴관 안내문) — {notice}"
            log(msg)
            print(msg)
            return 0
        else:
            detail = "; ".join(failures)
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

    # 정본 렌더 단일화(배99): 게이트 ON이면 같은 PNG를 텔레그램에도 발송(GAS 대체).
    if telegram_photo_enabled():
        if args.dry_run:
            log("텔레그램 사진 게이트 ON — dry-run이라 발송 생략")
        else:
            tg_ok = send_telegram_photo(image_path, caption)
            log(f"텔레그램 사진 발송 {'완료' if tg_ok else '실패'} — 정본 PNG 재사용({image_path})")

    wait_for_profile_chrome_clear()
    ok, failures = run_sender(rooms, image_path, caption, args.dry_run)
    if ok:
        detail = "DRY-RUN 검증 완료" if args.dry_run else "3방 전송 완료" if rooms is None else f"{rooms} 전송 완료"
        msg = f"DONE: 카톡 {'검증(dry-run)' if args.dry_run else '전송'} 완료 — {detail}"
        log(msg)
        print(msg)
        return 0
    else:
        detail = "; ".join(failures)
        send_owner_alert(f"⚠️ 카톡 매출보고 자동 발송 실패 — {detail}")
        print(f"FAILED: 카톡 전송 실패 — {detail}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
