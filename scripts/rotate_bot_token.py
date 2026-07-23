# -*- coding: utf-8 -*-
"""텔레그램 봇 토큰 교체기 (배9952 · 2026-07-23 시토).

왜 스크립트인가
  재발급 순간부터 옛 토큰은 즉시 죽는다 — 그 뒤 `.env` 를 손으로 고치는 동안 알림이
  멈춰 있다. 손편집은 오타·줄바꿈 사고도 잦다. 이 도구는 **검증 → 백업 → 한 줄 교체 →
  재확인**을 한 번에 해서 중단을 초 단위로 줄인다.

안전 규칙
  - 토큰 값을 **절대 출력하지 않는다**(로그·에러 메시지 포함). 확인은 봇 username 으로 한다.
  - 새 토큰이 **실제로 살아 있는지 먼저 확인**(getMe)한 뒤에만 .env 를 건드린다.
    죽은 값을 써 넣어 멀쩡한 설정까지 날리는 일을 막는다.
  - 교체 전 .env 를 타임스탬프 백업으로 남긴다(되돌릴 유일한 근거).
  - `.env` 의 다른 줄은 손대지 않는다 — TELEGRAM_BOT_TOKEN 한 줄만 바꾼다.

사용:
  python scripts/rotate_bot_token.py --token <새토큰>
  python scripts/rotate_bot_token.py --verify-only          # 지금 .env 토큰이 살아있는지만 확인
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "telegram_bot" / ".env"
KEY = "TELEGRAM_BOT_TOKEN"
TOKEN_RE = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$")


def read_env_token() -> str | None:
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{KEY}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def check_alive(token: str) -> tuple[bool, str]:
    """getMe 로 살아있는지 확인. 반환 (ok, 봇 username 또는 사유). 토큰은 반환하지 않는다."""
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=25)
        data = r.json()
    except Exception as exc:
        return False, f"연결 실패: {type(exc).__name__}"
    if not data.get("ok"):
        return False, f"거부됨(code={data.get('error_code')} {data.get('description', '')[:60]})"
    return True, str((data.get("result") or {}).get("username") or "?")


def swap(new_token: str) -> int:
    if not TOKEN_RE.match(new_token):
        print("[중단] 토큰 형식이 아닙니다. (숫자:영문숫자 형태여야 합니다)")
        return 1

    ok, info = check_alive(new_token)
    if not ok:
        print(f"[중단] 새 토큰이 살아있지 않습니다 — {info}. .env 는 건드리지 않았습니다.")
        return 1
    print(f"[확인] 새 토큰 정상 — 봇 @{info}")

    if not ENV_PATH.exists():
        print(f"[중단] {ENV_PATH} 없음")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ENV_PATH.with_name(f".env.bak_{stamp}")
    shutil.copy2(ENV_PATH, backup)
    print(f"[백업] {backup.name}")

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    hit = 0
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{KEY}="):
            lines[i] = f"{KEY}={new_token}"
            hit += 1
    if hit == 0:
        lines.append(f"{KEY}={new_token}")
        print(f"[주의] {KEY} 줄이 없어 새로 추가했습니다.")
    elif hit > 1:
        print(f"[주의] {KEY} 줄이 {hit}개였습니다 — 전부 갱신했습니다(중복 정리 권장).")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if read_env_token() != new_token:
        print("[실패] 기록 후 재확인 불일치 — 백업으로 되돌리세요.")
        return 1
    print("[완료] .env 교체·재확인 통과.")
    print("       다음: 봇·스케줄러 재기동 → GAS 6곳 스크립트 속성 교체(런북 §1)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="텔레그램 봇 토큰 교체 (값 미출력)")
    p.add_argument("--token", help="새 토큰")
    p.add_argument("--verify-only", action="store_true", help="현재 .env 토큰 생존만 확인")
    args = p.parse_args()

    if args.verify_only or not args.token:
        cur = read_env_token()
        if not cur:
            print("[확인] .env 에 토큰이 없습니다.")
            return 1
        ok, info = check_alive(cur)
        print(f"[확인] 현재 .env 토큰 — {'정상 @' + info if ok else '죽었거나 거부됨: ' + info}")
        return 0 if ok else 1

    return swap(args.token)


if __name__ == "__main__":
    sys.exit(main())
