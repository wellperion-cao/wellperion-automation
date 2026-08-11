#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scripts/ops_morning_pipeline.py — 아침 요약 자동 파이프라인 오케스트레이터 (★운영부 + ★중간관리자)

매일 08:00, 등록된 각 방(ROOMS)마다 순서대로: ①scripts/ops_export_kakao.py 실행(카톡 대화
내보내기) → ②scripts/ops_daily_digest.py 실행해 '어제' 요약 텍스트 획득 → ③요약이 비었거나
(어제=휴관 등 대화없음) 실패면 조용히 종료(로그만 남김, 아무 방·GM에도 발송 안 함) →
④(★운영부만) 요약이 있으면 GM 텔레그램(개인 보고봇)으로 승인요청 발송(요약 전문 +
[✅ 방에 발송]/[✏️ 수정요청]/[⏸️ 보류] 인라인버튼) → ⑤대기 상태를 gitignore된 아카이브에 저장.
한 방이 실패해도 다음 방은 계속 돈다(방마다 독립 — 예외도 잡아서 다음 방으로 넘어간다).

배536(2026-08-11 GM→시토) — ★중간관리자도 ★운영부와 동일하게 매일 대화 원문 수집 +
대화 정리 생성까지 돈다(위 ①②만). ④⑤ GM 승인요청 발송은 ★운영부 전용으로 남긴다 —
telegram_bot/bot.py의 opsdig: 콜백이 방·대기파일 경로를 ★운영부로 하드코딩하고 있어(★게이트),
★중간관리자까지 그 버튼을 태우면 오발송 위험이 있다. ★중간관리자의 대화 정리는
ops_daily_digest.py가 자기 방 폴더의 _pending_digest.json에 이미 저장하므로 정보 소실은 없다
(카톡 승인발송 콜백 확장은 범위 밖 — 후속).

★게이트(절대 원칙, ★운영부): 이 스크립트는 절대 ★운영부 방에 직접 전송하지 않는다. 방 전송은
telegram_bot/bot.py 의 opsdig: 콜백(GM이 [✅ 방에 발송] 버튼을 탭했을 때)에서만 발생한다.

★개인정보(필수): 대화 원문·요약·대기 파일은 전부 gitignore된
"1. AI자료_아카이브/11_카카오톡/{방}/" 하위에만 저장. status/·docs/ 등 추적경로 금지.

사용:
    python scripts/ops_morning_pipeline.py             # 실전(카톡 내보내기 포함, GM 텔레그램 실발송)
    python scripts/ops_morning_pipeline.py --dry-run    # 내보내기 생략(기존 최신 txt 재사용) +
                                                          # 텔레그램 실발송 대신 콘솔 출력(구성 실측용).
                                                          # 승인요청이 성공해도 대기 파일은 저장하지 않음
                                                          # (실제 GM 승인 플로우를 오염시키지 않기 위함).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
EXPORT_SCRIPT = ROOT / "scripts" / "ops_export_kakao.py"
DIGEST_SCRIPT = ROOT / "scripts" / "ops_daily_digest.py"
ENV_PATH = ROOT / "telegram_bot" / ".env"
KAKAO_ROOM_DIR = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / "★운영부"
PENDING_PATH = KAKAO_ROOM_DIR / "_pending_digest.json"

_SEP = "=" * 60


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


# 배536 — 07:30 파이프라인이 순서대로 도는 방 목록. ★운영부만 GM 승인요청(카톡 발송 게이트)
# 대상이다(위 모듈 docstring 참조). 새 방을 추가할 땐 이 목록에 한 줄 더하면 된다.
ROOMS = [
    {"room": "★ 운영부", "send_approval": True},
    {"room": "★ 중간관리자", "send_approval": False},
]


def run_export(room: str) -> "tuple[bool, str]":
    """scripts/ops_export_kakao.py --room {room} 실행(라이브 카톡 조작). 반환: (성공, EXPORT_OK 경로 / 실패사유).
    실패 시 owner 텔레그램 경보는 ops_export_kakao.py 자체가 발송하므로 여기서 중복 발송하지 않는다."""
    proc = subprocess.run(
        [PY, "-u", str(EXPORT_SCRIPT), "--room", room],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    log(f"[export:{room}] rc={proc.returncode}\n{out.strip()}")
    for line in out.splitlines():
        if line.startswith("EXPORT_OK:"):
            return True, line.split("EXPORT_OK:", 1)[1].strip()
        if line.startswith("EXPORT_FAIL:"):
            return False, line.split("EXPORT_FAIL:", 1)[1].strip()
    return False, f"내보내기 스크립트 출력에서 계약 라인을 찾지 못함(rc={proc.returncode})"


def run_digest(room: str) -> "tuple[bool, str]":
    """scripts/ops_daily_digest.py --room {room} 실행 → stdout 구분선(60개 '=') 사이 메시지 본문 추출.
    ops_daily_digest.py는 수정 금지(호출만) — 현재 출력 형식(헤더/구분선/메시지/구분선)에 맞춰 파싱한다."""
    proc = subprocess.run(
        [PY, "-u", str(DIGEST_SCRIPT), "--room", room],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    out = proc.stdout or ""
    log(f"[digest:{room}] rc={proc.returncode}\n{out.strip()[-1500:]}")
    if proc.returncode != 0:
        tail_src = (proc.stderr or out).strip().splitlines()
        reason = tail_src[-1] if tail_src else "알 수 없는 오류"
        return False, reason

    parts = out.split(_SEP)
    # 정상 출력 구조: [헤더..., "\n[대상일]...\n", "\n<메시지 본문>\n", "\n"] — 메시지는 parts[2].
    if len(parts) < 4:
        return False, "요약 두뇌 출력 형식을 파싱하지 못함(구분선 부족)"
    message = parts[2].strip()
    if not message:
        return False, "요약 메시지가 비어 있음"
    return True, message


def build_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ 방에 발송", "callback_data": "opsdig:send"}],
            [
                {"text": "✏️ 수정요청", "callback_data": "opsdig:revise"},
                {"text": "⏸️ 보류", "callback_data": "opsdig:hold"},
            ],
        ]
    }


def build_approval_text(message: str) -> str:
    return "📋 ★운영부 전날 정리 — 방에 발송할까요? (GM 승인 대기)\n\n" + message


def send_approval_request(message: str, dry_run: bool) -> bool:
    """GM 텔레그램(개인 보고봇, telegram_bot/.env OWNER_ID)으로 승인요청 발송.
    dry_run이면 실발송 대신 구성(텍스트+버튼)을 콘솔에 그대로 출력한다."""
    text = build_approval_text(message)

    if dry_run:
        log("[dry-run] 텔레그램 실발송 생략 — 아래는 실제 전송될 메시지/버튼 구성:")
        print("\n" + _SEP)
        print(text)
        print(_SEP)
        print(json.dumps(build_keyboard(), ensure_ascii=False, indent=2))
        print(_SEP + "\n")
        return True

    env = _load_env(ENV_PATH)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = env.get("OWNER_ID") or env.get("TELEGRAM_CHAT_ID", "")
    if not token or not owner_id:
        log("[실패] TELEGRAM_BOT_TOKEN/OWNER_ID(.env) 없음 — 승인요청 발송 불가")
        return False

    data = urllib.parse.urlencode({
        "chat_id": owner_id,
        "text": text,
        "reply_markup": json.dumps(build_keyboard()),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
            log(f"[텔레그램] 승인요청 발송 {'성공' if ok else '실패'}(status={resp.status})")
            return ok
    except Exception as exc:
        log(f"[실패] 승인요청 발송 예외: {exc}")
        return False


def save_pending(message: str) -> None:
    KAKAO_ROOM_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "message": message,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }
    PENDING_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[대기 저장] {PENDING_PATH}")


def _run_room(room: str, dry_run: bool, send_approval: bool) -> int:
    log(f"[시작] {room} 아침 요약 (dry_run={dry_run})")

    if dry_run:
        log("[1/4] --dry-run: 카톡 내보내기 생략(기존 최신 txt 재사용은 ops_daily_digest.py가 자동 수행)")
    else:
        log("[1/4] 카톡 대화 내보내기 실행...")
        exp_ok, exp_detail = run_export(room)
        if not exp_ok:
            log(f"[종료:{room}] 내보내기 실패 — {exp_detail} "
                f"(방·GM 승인요청 모두 발송 안 함, 로그만. GM 경보는 export 스크립트가 자체 발송함)")
            return 0

    log("[2/4] AI 요약 두뇌 호출...")
    dig_ok, dig_result = run_digest(room)
    if not dig_ok:
        log(f"[종료:{room}] 요약 생성 불가 — {dig_result} (방·GM 승인요청 모두 발송 안 함, 로그만)")
        return 0
    message = dig_result
    log(f"[3/4] 요약 생성 완료 ({len(message)}자)")

    if not send_approval:
        log(f"[완료:{room}] 수집·정리 생성 완료 — 카톡 승인요청 발송은 이 방 범위 밖(대화 정리는 "
            f"ops_daily_digest.py가 이 방 폴더의 _pending_digest.json에 이미 저장함)")
        return 0

    log("[4/4] GM 승인요청 발송...")
    sent = send_approval_request(message, dry_run)
    if not sent:
        log("[실패] GM 승인요청 발송 실패 — 대기 파일 저장 생략")
        return 1

    if dry_run:
        log("[dry-run 종료] 대기 파일 저장 생략(콘솔 확인용 — 실제 GM 승인 플로우 오염 방지)")
        return 0

    save_pending(message)
    log("[완료] GM 승인 대기 중 — 방 전송은 GM이 텔레그램 [✅ 방에 발송] 버튼을 눌러야만 "
        "telegram_bot/bot.py의 opsdig: 콜백이 처리한다(게이트).")
    return 0


def run(dry_run: bool) -> int:
    log(f"[시작] 아침 요약 파이프라인 (dry_run={dry_run}) — 대상 방: {', '.join(r['room'] for r in ROOMS)}")
    codes = []
    for cfg in ROOMS:
        try:
            codes.append(_run_room(cfg["room"], dry_run, cfg["send_approval"]))
        except Exception as exc:
            # 한 방의 예외가 다른 방을 막지 않는다(GM 2026-08-11 지시 — 방마다 독립).
            log(f"[예외:{cfg['room']}] {type(exc).__name__}: {exc}")
            codes.append(1)
    return 1 if any(c != 0 for c in codes) else 0


def main():
    parser = argparse.ArgumentParser(
        description="★운영부+★중간관리자 아침 요약 자동 파이프라인 — 방마다 내보내기→AI요약"
                     "(★운영부만 GM 텔레그램 승인요청까지 · 방 전송은 GM 버튼 게이트)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="카톡 내보내기 생략(기존 최신 txt 재사용) + 텔레그램 실발송 대신 콘솔 출력, 대기 파일 저장 생략")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
