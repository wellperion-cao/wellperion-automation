# scripts/ig_token_refresh.py
# 배#588 — IG 장기 액세스 토큰(60일) 자동 갱신 + 실패 시 OWNER 텔레그램 경보
#
# 배경: ig_reach_collector.py(배#546)가 쓰는 IG_ACCESS_TOKEN은 Meta
# "Instagram API with Instagram Login" 장기 사용자 토큰(60일 유효)이다.
# Meta 정책상 발급 후 24시간이 지나면 언제든 갱신 가능하며, 갱신 시점부터
# 다시 60일 연장된다 — 만료 전 주기 갱신을 반복하면 끊김 없이 영구 롤링 가능.
# 참고(공식): https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login-for-instagram/#refresh-a-long-lived-token
#
# 저장 위치: scripts/.env (IG_ACCESS_TOKEN / IG_BUSINESS_ID / IG_TOKEN_ISSUED_AT).
# .env는 .gitignore 대상 — 이 스크립트는 git commit을 하지 않는다(로컬 파일만 갱신).
#
# 실행:
#   python scripts/ig_token_refresh.py             # 실제 갱신 시도(성공 시 .env 갱신)
#   python scripts/ig_token_refresh.py --dry-run   # 네트워크 호출 없이 현재 상태만 출력
#
# 스케줄: Wellperion-IG-Token-Refresh-Weekly (매주 월 06:10) — 60일 토큰에
# 충분한 여유(주 1회 x 8회 이상)를 두고 주기 갱신. 갱신 실패(토큰 무효화·
# 24시간 미경과 등) 시 OWNER 텔레그램 경보(scripts/telegram_health_check.py와
# 동일한 .env 직독 + sendMessage 패턴 재사용).

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import requests
except ImportError:
    requests = None

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "scripts" / ".env"
TG_ENV_PATH = ROOT / "telegram_bot" / ".env"  # 봇 토큰 SSOT(CLAUDE.md §3) — .env 직독, 하드코딩 금지

KST = timezone(timedelta(hours=9))
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"


def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _load_env_dict(path: Path) -> dict:
    env: dict = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        env[k.strip()] = v.strip()
    return env


def _update_env_file(path: Path, updates: dict) -> None:
    """path의 KEY=VALUE 줄만 in-place 치환·없으면 파일 끝에 추가.
    나머지 라인·순서·인코딩은 그대로 보존(다른 시크릿 500+건 공존 파일)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _send_owner_alert(message: str, dry_run: bool = False) -> None:
    tg_env = _load_env_dict(TG_ENV_PATH)
    token = tg_env.get("TELEGRAM_BOT_TOKEN")
    owner_id = tg_env.get("OWNER_ID") or tg_env.get("TELEGRAM_CHAT_ID")
    if dry_run:
        print(f"[DRY-RUN] 경보 발송 생략 → chat_id={owner_id}\n{message}", flush=True)
        return
    if not token or not owner_id or requests is None:
        print("[WARN] OWNER 경보 발송 불가 — TELEGRAM_BOT_TOKEN/OWNER_ID 미설정 또는 requests 없음", flush=True)
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(owner_id), "text": message},
            timeout=15,
        )
        ok = resp.status_code == 200 and resp.json().get("ok", False)
        if not ok:
            print(f"[WARN] 경보 발송 실패: status={resp.status_code} body={resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"[WARN] 경보 발송 예외: {e}", flush=True)


def refresh_token(current_token: str) -> dict:
    """Meta 장기 토큰 갱신 호출. 성공 시 {"access_token":..., "expires_in":...} 반환.
    실패(24시간 미경과·토큰 무효 등)는 예외로 전파 — 호출부가 BLOCKED/경보 처리."""
    resp = requests.get(
        REFRESH_URL,
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=15,
    )
    try:
        data = resp.json() if resp.content else {}
    except Exception:
        data = {}
    if resp.status_code != 200 or "access_token" not in data:
        raise RuntimeError(f"status={resp.status_code} body={json.dumps(data, ensure_ascii=False)[:300]}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="IG 장기 액세스 토큰(60일) 자동 갱신 (배#588)")
    parser.add_argument("--dry-run", action="store_true", help="네트워크 호출 없이 현재 상태만 출력")
    args = parser.parse_args()

    print(f"=== IG 토큰 갱신 [{now_kst()}] (배#588) ===", flush=True)

    env = _load_env_dict(ENV_PATH)
    token = env.get("IG_ACCESS_TOKEN")
    issued_at = env.get("IG_TOKEN_ISSUED_AT")

    if not token:
        print("BLOCKED: IG_ACCESS_TOKEN 미설정 — 갱신 대상 없음", flush=True)
        return 0

    age_days = None
    if issued_at:
        try:
            issued_dt = datetime.strptime(issued_at, "%Y-%m-%d").replace(tzinfo=KST)
            age_days = (datetime.now(KST) - issued_dt).days
        except Exception:
            pass
    print(f"현재 토큰 발급일: {issued_at or '?'} (age={age_days if age_days is not None else '?'}일)", flush=True)

    if args.dry_run:
        print("DONE: --dry-run — 네트워크 호출 없음", flush=True)
        return 0

    if requests is None:
        print("BLOCKED: requests 라이브러리 미설치 — 호출 불가", flush=True)
        return 0

    try:
        result = refresh_token(token)
    except Exception as e:
        msg = (
            f"[IG 토큰 갱신 실패] {now_kst()}\n{e}\n"
            f"현재 토큰 발급일={issued_at or '?'} — 만료 임박 시 GM/시모 재인증 필요(배#588)"
        )
        print(f"FAIL: {e}", flush=True)
        _send_owner_alert(msg, dry_run=args.dry_run)
        return 0

    new_token = result.get("access_token")
    expires_in_sec = result.get("expires_in")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    updates = {"IG_ACCESS_TOKEN": new_token, "IG_TOKEN_ISSUED_AT": today}
    if expires_in_sec:
        expires_date = (datetime.now(KST) + timedelta(seconds=int(expires_in_sec))).strftime("%Y-%m-%d")
        updates["IG_TOKEN_EXPIRES_AT"] = expires_date
    _update_env_file(ENV_PATH, updates)
    tail = f", 만료예정={updates.get('IG_TOKEN_EXPIRES_AT')}" if "IG_TOKEN_EXPIRES_AT" in updates else ""
    print(f"DONE: 토큰 갱신 성공 — 새 발급일={today}{tail}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
