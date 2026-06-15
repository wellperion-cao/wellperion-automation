"""캐논 값 단일출처 로더 — ssot/canon_values.json 직독 헬퍼.

사용:
    from ssot.canon import canon_get
    url = canon_get("inquiry_path")   # → "wellperion.com/ko/inquiry"

    또는 스크립트 디렉터리가 다를 때:
    import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
    from ssot.canon import canon_get
"""
from __future__ import annotations

import json
from pathlib import Path

_CANON_FILE = Path(__file__).parent / "canon_values.json"
_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        data = json.loads(_CANON_FILE.read_text(encoding="utf-8"))
        _cache = {entry["key"]: entry["value"] for entry in data.get("values", [])}
    return _cache


def canon_get(key: str) -> str:
    """캐논 값 반환. 키 미존재 시 KeyError."""
    vals = _load()
    if key not in vals:
        raise KeyError(f"canon_values.json에 키 '{key}' 없음")
    return vals[key]
