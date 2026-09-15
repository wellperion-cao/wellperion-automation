# -*- coding: utf-8 -*-
"""구글 의존 실측(gas_dependency_scan.py)을 돌리고 결과 두 파일만 저장·배포한다 — 예약작업(매시)용 (2026-09-14 시토).
화면 cto/aws_migration.html 의 맨 위 숫자는 이 파일에서 나오므로, 사람이 손으로 돌리지 않아도 매시 갱신된다.
자기검사 = 스캔 결과 JSON 이 열리고 화면 수가 0 보다 크다."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
OUT = [ROOT / "status" / "gas_dependency.json", ROOT / "3. 웰페리온 가이드" / "status" / "gas_dependency.json"]
# 같은 예약(매시)에 얹어 하루 한 번 비용 실측(힉스필드·AWS)도 갱신한다 — 같은 날 것이면 스스로 건너뛴다(2026-09-15 GM).
COST = [ROOT / "status" / "cost_status.json", ROOT / "3. 웰페리온 가이드" / "status" / "cost_status.json"]


def main():
    subprocess.run([PY, str(ROOT / "scripts" / "gas_dependency_scan.py")], check=True, cwd=str(ROOT))
    subprocess.run([PY, str(ROOT / "scripts" / "cost_collect.py")], cwd=str(ROOT))   # 실패해도 의존 실측은 그대로 간다
    d = json.loads(OUT[0].read_text(encoding="utf-8"))
    assert d.get("screens_total", 0) > 0, "스캔 결과가 비었다"
    msg = "chore(cto): 구글 의존 실측 갱신 — 구글만 %d · 예비 %d · 서버만 %d / %d" % (
        d.get("screens_gas_only", 0), d.get("screens_both", 0), d.get("screens_server_only", 0), d.get("screens_total", 0))
    r = subprocess.run([PY, str(ROOT / "scripts" / "safe_commit.py"), "--holder", "gas-dep-scan", "-m", msg]
                       + [str(p.relative_to(ROOT)) for p in OUT + [c for c in COST if c.exists()]], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "")[-300:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
