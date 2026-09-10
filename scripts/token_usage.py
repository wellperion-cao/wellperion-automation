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

# 단가표 — 출처 = Anthropic 공개 단가(claude-api 스킬 확인, 2026-09-10) · 값이 바뀌면 이 표만 고친다.
# 백만 토큰당 USD. cache_read·cache_write_5m·cache_write_1h 는 공식 캐시 경제학 공식으로 계산:
#   캐시읽기 = input×0.1 (Fable 5.1 만 예외로 input×0.025 — 공식 확인됨, 스킬 shared/models.md)
#   캐시생성 5분 = input×1.25, 캐시생성 1시간 = input×2 (전 모델 공통, 스킬 shared/prompt-caching.md)
# 이 공식으로 모든 모델이 "같은 자"로 잡힌다 — 모델 간 금액 비교 가능(GM 09-09 지적 해결).
PRICE_TABLE = {
    "claude-fable-5-1":  {"input": 10.00, "output": 50.00, "cache_read": 0.25, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
    "claude-fable-5":    {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write_5m": 12.50, "cache_write_1h": 20.00},
    "claude-opus-5":     {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
    "claude-opus-4-8":   {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
    "claude-opus-4-7":   {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
    "claude-opus-4-6":   {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write_5m": 6.25, "cache_write_1h": 10.00},
    "claude-sonnet-5":   {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write_5m": 2.50, "cache_write_1h": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write_5m": 3.75, "cache_write_1h": 6.00},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00},  # 로그 실측 id(날짜접미 포함) — 같은 모델, 값 동일
}
USD_KRW = 1400  # 환율 고정(GM 지시 2026-09-09) — 실시간 조회 안 함(외부 호출 금지)


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
    return {"input": 0, "cache_creation": 0, "cache_creation_5m": 0, "cache_creation_1h": 0,
            "cache_read": 0, "output": 0, "sessions": []}


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
                cc = usage.get("cache_creation") or {}  # {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens} — 5분/1시간 단가 갈라 매기는 근거
                bucket["cache_creation_5m"] += int(cc.get("ephemeral_5m_input_tokens") or 0)
                bucket["cache_creation_1h"] += int(cc.get("ephemeral_1h_input_tokens") or 0)
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

# 실제 청구액 — 계정별 고정 정액 구독료(USD/월). GM 지시 2026-09-10.
# 토큰을 API 정가로 환산한 금액(pricing.*.krw)은 "많이 쓰면 이만큼 손해"가 아니다 —
# 실제로 나가는 돈은 이 정액뿐이라 많이 쓸수록 이득이다. 두 값을 혼동하지 않도록 화면에 나란히 낸다.
SUBSCRIPTION_USD = {
    "cao@wellperion.com": 200,
    "info@wellperion.com": 200,
    "lessons@wellperion.com": 100,
}


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


def cost_for_bucket(model, b):
    """모델·버킷(input/cache_creation[_5m/_1h]/cache_read/output) → (원화, 단가있는토큰수, 단가미상토큰수).
    단가표에 없는 모델은 전체가 단가미상. 있는 모델은 캐시읽기·캐시생성(5분/1시간 분리)까지 전부
    공식 단가로 매긴다 — 옛 로그처럼 5분/1시간 분리값이 없는 cache_creation 잔여분만 단가미상으로 뺀다."""
    price = PRICE_TABLE.get(model)
    total = b["input"] + b["cache_creation"] + b["cache_read"] + b["output"]
    if not price:
        return 0.0, 0, total
    usd = (b["input"] * price["input"] + b["output"] * price["output"]) / 1_000_000
    priced = b["input"] + b["output"]
    unpriced = 0
    cache_read_price = price.get("cache_read")
    if cache_read_price is not None:
        usd += b["cache_read"] * cache_read_price / 1_000_000
        priced += b["cache_read"]
    else:
        unpriced += b["cache_read"]
    known_split = b["cache_creation_5m"] + b["cache_creation_1h"]
    write_5m_price = price.get("cache_write_5m")
    write_1h_price = price.get("cache_write_1h")
    if write_5m_price is not None and write_1h_price is not None:
        usd += (b["cache_creation_5m"] * write_5m_price + b["cache_creation_1h"] * write_1h_price) / 1_000_000
        priced += known_split
        unpriced += max(b["cache_creation"] - known_split, 0)  # 옛 로그(5분/1시간 분리 없음) 잔여분만
    else:
        unpriced += b["cache_creation"]
    return usd * USD_KRW, priced, unpriced


def sum_model_buckets(days_out, day_filter):
    """days_out(day->model->bucket) 중 day_filter 통과 날짜만 모델별로 합산."""
    result = {}
    for day, models in days_out.items():
        if not day_filter(day):
            continue
        for model, b in models.items():
            acc = result.setdefault(model, {"input": 0, "cache_creation": 0, "cache_creation_5m": 0,
                                             "cache_creation_1h": 0, "cache_read": 0, "output": 0})
            for k in ("input", "cache_creation", "cache_creation_5m", "cache_creation_1h", "cache_read", "output"):
                acc[k] += b[k]
    return result


def price_summary(model_buckets):
    total_krw = 0.0
    priced_tokens = 0
    unpriced_tokens = 0
    by_model = {}
    for model, b in model_buckets.items():
        krw, p_tok, u_tok = cost_for_bucket(model, b)
        total_krw += krw
        priced_tokens += p_tok
        unpriced_tokens += u_tok
        by_model[model] = {"krw": round(krw), "priced_tokens": p_tok, "unpriced_tokens": u_tok}
    total_tok = priced_tokens + unpriced_tokens
    pct = round(unpriced_tokens / total_tok * 100, 1) if total_tok else 0.0
    return {
        "krw": round(total_krw), "priced_tokens": priced_tokens,
        "unpriced_tokens": unpriced_tokens, "unpriced_pct": pct, "by_model": by_model,
    }


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
                mb = merged_days.setdefault(day, {}).setdefault(model, {"input": 0, "cache_creation": 0, "cache_creation_5m": 0, "cache_creation_1h": 0, "cache_read": 0, "output": 0, "sessions": set()})
                mb["input"] += b["input"]
                mb["cache_creation"] += b["cache_creation"]
                mb["cache_creation_5m"] += b.get("cache_creation_5m", 0)  # 옛 파일캐시 잔존분 방어(신규 필드 없음)
                mb["cache_creation_1h"] += b.get("cache_creation_1h", 0)
                mb["cache_read"] += b["cache_read"]
                mb["output"] += b["output"]
                mb["sessions"].update(b["sessions"])

                pb = proj_totals.setdefault(project, {"input": 0, "cache_creation": 0, "cache_creation_5m": 0, "cache_creation_1h": 0, "cache_read": 0, "output": 0, "sessions": set()})
                pb["input"] += b["input"]
                pb["cache_creation"] += b["cache_creation"]
                pb["cache_creation_5m"] += b.get("cache_creation_5m", 0)
                pb["cache_creation_1h"] += b.get("cache_creation_1h", 0)
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
                "cache_creation_5m": b["cache_creation_5m"], "cache_creation_1h": b["cache_creation_1h"],
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
            "cache_creation_5m": b["cache_creation_5m"], "cache_creation_1h": b["cache_creation_1h"],
            "cache_read": b["cache_read"], "output": b["output"],
            "sessions": len(b["sessions"]),
        }
        for p, b in proj_totals.items()
    }

    today_date = datetime.now(KST).date()
    month_start = today_date.replace(day=1).isoformat()
    last7_start = (today_date - timedelta(days=6)).isoformat()
    prev7_start = (today_date - timedelta(days=13)).isoformat()
    prev7_end = (today_date - timedelta(days=7)).isoformat()

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
        "billing": {
            "usd_month_fixed": sum(SUBSCRIPTION_USD.values()),
            "krw_month_fixed": round(sum(SUBSCRIPTION_USD.values()) * USD_KRW),
            "accounts_usd": SUBSCRIPTION_USD,
            "note": "Claude 구독은 계정별 고정 정액이다(GM 지시 2026-09-10) — 토큰을 얼마나 쓰든 매달 나가는 돈은 이 금액뿐이다.",
        },
        "pricing": {
            "usd_krw": USD_KRW,
            "usd_krw_note": "환율 1,400원 고정 · 실시간 조회 안 함",
            "price_table_note": "출처 = Anthropic 공개 단가(claude-api 스킬 확인, 2026-09-10) · 값이 바뀌면 PRICE_TABLE 만 고친다",
            "unpriced_note": "표에 있는 모델은 캐시읽기·캐시생성(5분/1시간)까지 전부 공식 단가로 매겨 모델 간 금액이 '같은 자'로 비교된다. 단가표에 없는 모델(신규·미등록)만 전체가 단가미상 토큰으로 빠진다.",
            "this_month": price_summary(sum_model_buckets(days_out, lambda d: d >= month_start)),
            "last_7d": price_summary(sum_model_buckets(days_out, lambda d: d >= last7_start)),
            "prev_7d": price_summary(sum_model_buckets(days_out, lambda d: prev7_start <= d <= prev7_end)),
            "by_model": price_summary(sum_model_buckets(days_out, lambda d: True))["by_model"],
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
            for _k in ("input", "cache_creation", "cache_creation_5m", "cache_creation_1h", "cache_read", "output", "sessions"):
                assert _b[_k] >= 0, "음수 발견: %s/%s/%s" % (_day, _m, _k)
    for _period in ("this_month", "last_7d", "prev_7d"):
        _p = _d["pricing"][_period]
        assert _p["krw"] >= 0, "%s krw 음수" % _period
        assert 0 <= _p["unpriced_pct"] <= 100, "%s unpriced_pct 범위 밖: %s" % (_period, _p["unpriced_pct"])
        assert _p["priced_tokens"] + _p["unpriced_tokens"] >= 0
    print("자기검사 통과")
