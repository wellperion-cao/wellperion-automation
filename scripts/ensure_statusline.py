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


def wanted_command() -> str:
    # 경로에 공백이 있어 각각 따옴표로 감싼다. HUD 경로는 슬래시로 통일(윈도우도 인식).
    return '"%s" "%s"' % (NODE, HUD.as_posix())


def main() -> int:
    ap = argparse.ArgumentParser(description="statusline 설정 자가복구(멱등)")
    ap.add_argument("--check", action="store_true", help="확인만 하고 고치지 않는다")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

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
