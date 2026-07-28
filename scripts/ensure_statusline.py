# -*- coding: utf-8 -*-
"""statusline 설정 자가복구 (2026-07-24 시토 · GM '박제' 지시).

무엇을 하나
  `~/.claude/settings.json` 의 statusLine 이 저장소의 `scripts/wellperion_hud.mjs` 를
  가리키는지 확인하고, 아니면 **고쳐 놓는다.** 이미 맞으면 아무것도 안 한다(멱등).

왜 필요한가 (문서로는 안 막힌다 — 약속 L02)
  - statusLine 설정은 `~/.claude/settings.json` = **저장소 밖**이다. PC 를 바꾸거나 새로
    설치하면 그냥 없다. 배9889 에서 예약 런처가 저장소 밖에 있어 통째로 사라질 뻔한 것과 같다.
  - OMC 가 업데이트되면 statusLine 을 자기 HUD 로 되돌릴 수 있다. 그러면 조용히 원상복구된다.
  → 그래서 7개 Start-AI *.bat(= 모든 C-Level 부팅 경로)이 claude 를 띄우기 **직전에** 이걸 부른다.
    부팅이 곧 점검이라 새 예약 작업이 0개다.

안전
  - 고치기 전 백업(settings.json.bak_YYYYmmdd_HHMMSS)을 남긴다.
  - statusLine 키 하나만 건드린다. 나머지 설정은 읽고 그대로 다시 쓴다.
  - 어떤 실패도 부팅을 막지 않는다(항상 종료코드 0).

사용:
  python scripts/ensure_statusline.py            # 확인 후 필요하면 복구
  python scripts/ensure_statusline.py --check    # 확인만(고치지 않음)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = Path.home() / ".claude" / "settings.json"
NODE = Path(r"C:\Program Files\nodejs\node.exe")
HUD = ROOT / "scripts" / "wellperion_hud.mjs"

# ── 턴 끝나면 다음 배로 이어가기(Stop 훅) 자가복구 — GM 결정 2026-07-28 A안 ──────────
#   왜 여기 얹나: 이 설정이 사는 `<저장소>/.claude/settings.local.json` 은 **git 이 무시하는
#   파일**이라(.gitignore `.claude/*`) PC 를 새로 깔면 그냥 없다. statusLine 이 같은 이유로
#   사라질 뻔했던 것과 똑같은 자리다. 새 점검기·새 예약작업을 만들지 않고 이미 7개 부팅
#   .bat 이 전부 지나가는 이 관문에 흡수한다(약속 L21 — 장치는 늘리지 않는다).
LOCAL_SETTINGS = ROOT / ".claude" / "settings.local.json"
STOP_HOOK_CMD = 'cmd /c "%USERPROFILE%\\welperion-automation\\scripts\\auto_next_ship_hook.cmd"'
STOP_HOOK_SCRIPT = ROOT / "scripts" / "auto_next_ship_hook.cmd"


def wanted_command() -> str:
    # 경로에 공백이 있어 각각 따옴표로 감싼다. HUD 경로는 슬래시로 통일(윈도우도 인식).
    return '"%s" "%s"' % (NODE, HUD.as_posix())


def ensure_stop_hook(check_only: bool) -> None:
    """Stop 훅이 걸려 있는지 확인하고, 없으면 걸어 놓는다(멱등).
    hooks 안의 Stop 키 하나만 건드린다 — SessionStart/SessionEnd 등 나머지는 그대로 둔다."""
    try:
        if not STOP_HOOK_SCRIPT.exists():
            print("[다음배] 훅 스크립트가 없어 건너뜁니다: %s" % STOP_HOOK_SCRIPT)
            return
        if not LOCAL_SETTINGS.exists():
            print("[다음배] settings.local.json 이 없어 건너뜁니다")
            return
        data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            hooks = {}
        cur = ""
        try:
            cur = hooks["Stop"][0]["hooks"][0]["command"]
        except Exception:  # noqa: BLE001
            cur = ""
        if cur == STOP_HOOK_CMD:
            print("[다음배] 정상 — 손댈 것 없음")
            return
        if check_only:
            print("[다음배] 어긋남\n  현재: %s\n  기대: %s" % (cur or "(없음)", STOP_HOOK_CMD))
            return
        shutil.copy2(LOCAL_SETTINGS, LOCAL_SETTINGS.with_name(
            LOCAL_SETTINGS.name + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")))
        hooks["Stop"] = [{"hooks": [{"type": "command", "command": STOP_HOOK_CMD, "timeout": 40}]}]
        data["hooks"] = hooks
        LOCAL_SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[다음배] 복구함\n  전: %s\n  후: %s" % (cur or "(없음)", STOP_HOOK_CMD))
    except Exception as exc:  # noqa: BLE001
        print("[다음배] 점검 건너뜀(부팅 계속): %s: %s" % (type(exc).__name__, exc))


def main() -> int:
    ap = argparse.ArgumentParser(description="statusline 설정 자가복구(멱등)")
    ap.add_argument("--check", action="store_true", help="확인만 하고 고치지 않는다")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ensure_stop_hook(args.check)

    try:
        if not HUD.exists():
            print("[statusline] HUD 스크립트가 없어 건너뜁니다: %s" % HUD)
            return 0
        if not SETTINGS.exists():
            print("[statusline] settings.json 이 없어 건너뜁니다: %s" % SETTINGS)
            return 0

        want = wanted_command()
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        cur = (data.get("statusLine") or {}).get("command")

        if cur == want:
            print("[statusline] 정상 — 손댈 것 없음")
            return 0
        if args.check:
            print("[statusline] 어긋남\n  현재: %s\n  기대: %s" % (cur, want))
            return 0

        shutil.copy2(SETTINGS, SETTINGS.with_name(
            SETTINGS.name + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")))
        data["statusLine"] = {"type": "command", "command": want}
        SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[statusline] 복구함\n  전: %s\n  후: %s" % (cur, want))
    except Exception as exc:
        # 부팅을 막지 않는다 — statusline 은 편의 기능이다.
        print("[statusline] 점검 건너뜀(부팅 계속): %s: %s" % (type(exc).__name__, exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
