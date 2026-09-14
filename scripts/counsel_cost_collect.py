#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""상담봇 건당 비용 집계 — journalctl 과거 데이터를 counsel_usage.jsonl 로 이관 후 API 집계 호출.

사용법:
  # 서버에서 직접 실행 (journalctl 접근 필요)
  python3 scripts/counsel_cost_collect.py --backfill
  # 저장소에 status/counsel_cost.json 쓰기
  python3 scripts/counsel_cost_collect.py --write-repo
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent.parent
STATUS_DIR = HERE / "status"

USAGE_LOG = os.environ.get("ERP_COUNSEL_USAGE_LOG", "/srv/erp/counsel_usage.jsonl")

# Bedrock 가격 (원/tok · USD/MTok × 1,400원 · 2026)
_PRICE = {
    "opus":   {"in": 0.021,  "out": 0.105,  "cache_write": 0.02625, "cache_read": 0.0021},
    "sonnet": {"in": 0.0042, "out": 0.021,  "cache_write": 0.00525, "cache_read": 0.00042},
}

_USAGE_RE = re.compile(
    r"\[concierge-usage\] tenant=(\S*) model=(\S+) in=(\d+) out=(\d+) "
    r"cache_write=(\d+) cache_read=(\d+)"
)
# 구형 포맷 (tenant 없음 — 2026-09-11 이전 로그)
_USAGE_RE_OLD = re.compile(
    r"\[concierge-usage\] model=(\S+) in=(\d+) out=(\d+) "
    r"cache_write=(\d+) cache_read=(\d+)"
)
# [concierge] 줄로 tenant 파악 (구형 로그 보완)
_CONCIERGE_RE = re.compile(r"\[concierge\] tenant=(\S+) model=(\S+)")


def _model_key(model: str) -> str:
    return "opus" if "opus" in model.lower() else "sonnet"


def _cost_krw(model: str, in_: int, out: int, cw: int, cr: int) -> float:
    p = _PRICE[_model_key(model)]
    return in_ * p["in"] + out * p["out"] + cw * p["cache_write"] + cr * p["cache_read"]


def backfill_from_journalctl(days: int = 30) -> int:
    """journalctl 에서 [concierge-usage] 줄을 읽어 counsel_usage.jsonl 에 추가한다.
    이미 있는 항목은 ts 기준으로 중복 제거한다."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        result = subprocess.run(
            ["journalctl", "--no-pager", "--since", since, "--output=short-iso",
             "-u", "erp-api", "-u", "erp-api-live", "-u", "erp-api-beta"],
            capture_output=True, text=True, timeout=60
        )
        lines = result.stdout.splitlines()
    except Exception as e:
        print("journalctl 실패: %s" % e, file=sys.stderr)
        return 0

    # 기존 counsel_usage.jsonl ts 목록
    existing_ts: set = set()
    try:
        with open(USAGE_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    existing_ts.add(json.loads(line)["ts"])
                except Exception:
                    pass
    except OSError:
        pass

    added = 0
    # 줄 쌍: [concierge-usage] 바로 뒤에 [concierge] 가 온다 (tenant 정보)
    last_tenant = ""
    for raw in lines:
        # ts 파싱 (short-iso: 2026-09-14T09:12:34+0900)
        ts_match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)
        ts_str = ts_match.group(1) if ts_match else ""

        cm = _CONCIERGE_RE.search(raw)
        if cm:
            last_tenant = cm.group(1)

        um = _USAGE_RE.search(raw)
        if not um:
            um_old = _USAGE_RE_OLD.search(raw)
            if um_old:
                tenant, model = last_tenant, um_old.group(1)
                in_, out, cw, cr = int(um_old.group(2)), int(um_old.group(3)), int(um_old.group(4)), int(um_old.group(5))
            else:
                continue
        else:
            tenant, model = um.group(1) or last_tenant, um.group(2)
            in_, out, cw, cr = int(um.group(3)), int(um.group(4)), int(um.group(5)), int(um.group(6))

        if ts_str in existing_ts:
            continue

        row = {"ts": ts_str, "tenant": tenant, "model": model,
               "in": in_, "out": out, "cache_write": cw, "cache_read": cr}
        os.makedirs(os.path.dirname(USAGE_LOG) or ".", exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        existing_ts.add(ts_str)
        added += 1

    return added


def aggregate(days: int = 30) -> dict:
    """counsel_usage.jsonl 을 읽어 테넌트별·모델별 건당 비용을 집계한다."""
    cutoff = datetime.now(timezone(timedelta(hours=9))) - timedelta(days=days)
    buckets: dict = {}
    try:
        with open(USAGE_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone(timedelta(hours=9)))
                except (KeyError, ValueError):
                    continue
                if ts < cutoff:
                    continue
                key = (row.get("tenant", "unknown"), _model_key(row.get("model", "")))
                b = buckets.setdefault(key, {"calls": 0, "in": 0, "out": 0,
                                             "cache_write": 0, "cache_read": 0, "cost": 0.0})
                b["calls"] += 1
                b["in"] += row.get("in", 0)
                b["out"] += row.get("out", 0)
                b["cache_write"] += row.get("cache_write", 0)
                b["cache_read"] += row.get("cache_read", 0)
                b["cost"] += _cost_krw(row.get("model", ""), row.get("in", 0), row.get("out", 0),
                                       row.get("cache_write", 0), row.get("cache_read", 0))
    except OSError:
        pass

    result = []
    for (tenant, model), b in sorted(buckets.items()):
        c = b["calls"]
        result.append({
            "tenant": tenant, "model": model, "calls": c,
            "avg_in": round(b["in"] / c) if c else 0,
            "avg_out": round(b["out"] / c) if c else 0,
            "avg_cache_read": round(b["cache_read"] / c) if c else 0,
            "cache_hit_rate": round(b["cache_read"] / (b["in"] + b["cache_read"]), 3)
                              if (b["in"] + b["cache_read"]) else 0,
            "total_cost_krw": round(b["cost"]),
            "avg_cost_krw": round(b["cost"] / c, 1) if c else 0,
        })
    return {
        "generated": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M:%S"),
        "days": days,
        "tenants": result,
        "pricing_basis": "Bedrock USD/MTok × 1,400원 추정 — AWS 청구서와 대조 필요",
    }


def write_repo(data: dict) -> None:
    STATUS_DIR.mkdir(exist_ok=True)
    out_path = STATUS_DIR / "counsel_cost.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("저장: %s" % out_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="journalctl 과거 데이터 이관")
    ap.add_argument("--write-repo", action="store_true", help="status/counsel_cost.json 갱신")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    if args.backfill:
        n = backfill_from_journalctl(args.days)
        print("이관 %d건" % n)

    data = aggregate(args.days)
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if args.write_repo:
        write_repo(data)


# 자가점검
def _selfcheck():
    import tempfile, os as _os
    tmp = tempfile.mktemp(suffix=".jsonl")
    rows = [
        {"ts": "2026-09-14T09:00:00", "tenant": "1_wellperion", "model": "claude-sonnet-4-6",
         "in": 200, "out": 250, "cache_write": 0, "cache_read": 28000},
        {"ts": "2026-09-14T10:00:00", "tenant": "1_wellperion", "model": "claude-sonnet-4-6",
         "in": 180, "out": 220, "cache_write": 0, "cache_read": 28000},
    ]
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    _os.environ["ERP_COUNSEL_USAGE_LOG"] = tmp
    global USAGE_LOG
    USAGE_LOG = tmp
    data = aggregate(days=30)
    assert len(data["tenants"]) == 1
    t = data["tenants"][0]
    assert t["calls"] == 2
    assert t["avg_cost_krw"] > 0
    # sonnet: cache_read 28000 × 0.00042 + in 190 × 0.0042 + out 235 × 0.021 ≈ 17.5원
    assert 10 < t["avg_cost_krw"] < 30, "건당 비용 범위 이상: %s" % t["avg_cost_krw"]
    _os.unlink(tmp)
    print("selfcheck OK — avg_cost_krw=%.1f원" % t["avg_cost_krw"])


if __name__ == "__main__" and "--selfcheck" in sys.argv:
    _selfcheck()
