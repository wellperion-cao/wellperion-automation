import json
from pathlib import Path

_DIR = Path(__file__).parent / "tenants"


def load_tenant(tenant_id: str = "wellperion") -> dict:
    p = _DIR / f"{tenant_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"업체 설정 없음: {p}")
    return json.loads(p.read_text(encoding="utf-8"))
