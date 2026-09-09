#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""클로드 대화 로그(~/.claude/projects/**/*.jsonl)에서 날짜×모델별 토큰 사용량을 집계해
status/token_usage.json 을 만든다. ERP 「토큰 사용량」 화면(cto/automation)의 원천.
GM 질문 2026-09-09.

네 종류(입력·캐시생성·캐시읽기·출력)를 뭉치지 않는다 — 캐시읽기가 총량 대부분이라
합치면 실제 부담보다 크게 보인다. 최근 30일만 담는다(화면 속도).
계정(cao@/info@) 구분은 대화 기록에 없다 — 오늘 이후 처음 보는 세션에만
현재 로그인 계정을 귀속시켜 token_usage_accounts.jsonl 에 append 한다(과거분은 미상).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CLAUDE_JSON = Path.home() / ".claude.json"
OUT_PATH = REPO / "status" / "token_usage.json"
CACHE_PATH = REPO / "status" / "token_usage_file_cache.json"
ACCOUNTS_LOG = REPO / "status" / "token_usage_accounts.jsonl"

KST = timezone(timedelta(hours=9))
KEEP_DAYS = 30


def kst_date(ts_str):
    """ISO8601 타임스탬프(대개 UTC 'Z') → KST 날짜 문자열. 못 읽으면 None."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d")
    except Exception:
        return None


def proj_name(cwd):
    base = os.path.basename((cwd or "").replace("\\", "/").rstrip("/"))
    return base or "unknown"


def empty_bucket():
    return {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "sessions": []}


def parse_file(path):
    """jsonl 한 파일 → {day: {model: bucket}}, project 이름."""
    days = {}
    project = "unknown"
    sess_seen = {}  # day -> set(sessionId), bucket 안 sessions 중복 방지용
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage") or {}
                if not usage:
                    continue
                model = msg.get("model") or "unknown"
                if model.startswith("<"):
                    continue  # <synthetic> 등 내부 placeholder — 토큰 0 고정, 표에 넣을 값이 없다
                day = kst_date(rec.get("timestamp"))
                if not day:
                    continue
                if rec.get("cwd"):
                    project = proj_name(rec.get("cwd"))
                bucket = days.setdefault(day, {}).setdefault(model, empty_bucket())
                bucket["input"] += int(usage.get("input_tokens") or 0)
                bucket["cache_creation"] += int(usage.get("cache_creation_input_tokens") or 0)
                bucket["cache_read"] += int(usage.get("cache_read_input_tokens") or 0)
                bucket["output"] += int(usage.get("output_tokens") or 0)
                sid = rec.get("sessionId")
                if sid:
                    seen = sess_seen.setdefault(day, set())
                    if sid not in seen:
                        seen.add(sid)
                        bucket["sessions"].append(sid)
    except Exception:
        pass
    return {"days": days, "project": project}


def load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def current_account():
    try:
        with open(CLAUDE_JSON, encoding="utf-8") as f:
            d = json.load(f)
        return (d.get("oauthAccount") or {}).get("emailAddress") or "미상"
    except Exception:
        return "미상"


def append_new_sessions(today_str, sessions_today, account):
    """오늘 처음 보는 세션만 로그에 append(중복 없이)."""
    if not sessions_today:
        return
    known = set()
    if ACCOUNTS_LOG.exists():
        with open(ACCOUNTS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    known.add(json.loads(line)["sessionId"])
                except Exception:
                    continue
    new = sessions_today - known
    if not new:
        return
    with open(ACCOUNTS_LOG, "a", encoding="utf-8") as f:
        for sid in sorted(new):
            f.write(json.dumps({"sessionId": sid, "account": account, "first_seen": today_str}, ensure_ascii=False) + "\n")


# 회사가 쓰는 클로드 계정 — GM 지시 2026-09-09 (cao 외 info·lessons 추가).
# 아직 그 계정으로 뜬 세션이 없어도 화면에 줄을 세워 「아직 기록 없음」으로 보이게 한다.
KNOWN_ACCOUNTS = [
    "cao@wellperion.com",
    "info@wellperion.com",
    "lessons@wellperion.com",
]


def account_summary():
    counts = {a: 0 for a in KNOWN_ACCOUNTS}
    if ACCOUNTS_LOG.exists():
        with open(ACCOUNTS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                counts[rec.get("account", "미상")] = counts.get(rec.get("account", "미상"), 0) + 1
    return counts


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    cutoff = (datetime.now(KST) - timedelta(days=KEEP_DAYS - 1)).strftime("%Y-%m-%d")

    files = sorted(PROJECTS_DIR.rglob("*.jsonl")) if PROJECTS_DIR.exists() else []
    cache = load_cache()
    new_cache = {}

    merged_days = {}  # day -> model -> bucket(sets for sessions)
    proj_totals = {}  # project -> bucket(sets)
    sessions_today = set()

    for path in files:
        key = str(path)
        try:
            st = path.stat()
        except Exception:
            continue
        sig = "%d:%d" % (int(st.st_mtime), st.st_size)
        cached = cache.get(key)
        if cached and cached.get("sig") == sig:
            parsed = cached["data"]
        else:
            parsed = parse_file(path)
        new_cache[key] = {"sig": sig, "data": parsed}

        project = parsed.get("project", "unknown")
        for day, models in parsed.get("days", {}).items():
            if day < cutoff:
                continue
            for model, b in models.items():
                mb = merged_days.setdefault(day, {}).setdefault(model, {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "sessions": set()})
                mb["input"] += b["input"]
                mb["cache_creation"] += b["cache_creation"]
                mb["cache_read"] += b["cache_read"]
                mb["output"] += b["output"]
                mb["sessions"].update(b["sessions"])

                pb = proj_totals.setdefault(project, {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "sessions": set()})
                pb["input"] += b["input"]
                pb["cache_creation"] += b["cache_creation"]
                pb["cache_read"] += b["cache_read"]
                pb["output"] += b["output"]
                pb["sessions"].update(b["sessions"])

                if day == today:
                    sessions_today.update(b["sessions"])

    save_cache(new_cache)
    append_new_sessions(today, sessions_today, current_account())

    days_out = {
        day: {
            model: {
                "input": b["input"], "cache_creation": b["cache_creation"],
                "cache_read": b["cache_read"], "output": b["output"],
                "sessions": len(b["sessions"]),
            }
            for model, b in models.items()
        }
        for day, models in merged_days.items()
    }
    proj_out = {
        p: {
            "input": b["input"], "cache_creation": b["cache_creation"],
            "cache_read": b["cache_read"], "output": b["output"],
            "sessions": len(b["sessions"]),
        }
        for p, b in proj_totals.items()
    }

    out = {
        "generated_at": datetime.now(KST).isoformat(),
        "range": {"from": cutoff, "to": today},
        "cache_read_note": "캐시 읽기는 같은 대화를 이어갈 때 다시 읽는 양이라 실제 새로 쓴 양과 다르다.",
        "days": days_out,
        "projects": proj_out,
        "accounts": {
            "current": current_account(),
            "tracked_since": "2026-09-09",
            "sessions_by_account": account_summary(),
        },
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", OUT_PATH, "days=%d projects=%d" % (len(days_out), len(proj_out)))


if __name__ == "__main__":
    main()
    with open(OUT_PATH, encoding="utf-8") as _f:
        _d = json.load(_f)
    for _day, _models in _d["days"].items():
        assert len(_day) == 10 and _day[4] == "-" and _day[7] == "-", "날짜 형식 오류: %s" % _day
        for _m, _b in _models.items():
            for _k in ("input", "cache_creation", "cache_read", "output", "sessions"):
                assert _b[_k] >= 0, "음수 발견: %s/%s/%s" % (_day, _m, _k)
    print("자기검사 통과")
