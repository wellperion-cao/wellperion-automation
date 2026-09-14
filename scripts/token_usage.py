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
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CLAUDE_JSON = Path.home() / ".claude.json"
OUT_PATH = REPO / "status" / "token_usage.json"
CACHE_PATH = REPO / "status" / "token_usage_file_cache.json"
ACCOUNTS_LOG = REPO / "status" / "token_usage_accounts.jsonl"

# 원격 PC 판 토큰 수집기(GM 지시 2026-09-14) — 다른 계정 PC(info@·lessons@)가 자기 사용량을
# 서버에 올리면(token_usage_push.py) 여기서 읽어 by_account 에 합친다. 열쇠 없으면 조용히 건너뛴다.
TOKEN_PUSH_KEY_FILE = Path.home() / ".claude" / "token_push.key"
REMOTE_URL = "https://erp.wellperion.com/api/token_usage/remote"


def read_push_key():
    """토큰 수집기 열쇠 — 파일(%USERPROFILE%\\.claude\\token_push.key) 우선, 없으면 환경변수."""
    try:
        with open(TOKEN_PUSH_KEY_FILE, encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return os.environ.get("ERP_TOKEN_PUSH_KEY") or None


def fetch_remote(key):
    req = urllib.request.Request(REMOTE_URL, headers={"X-Token-Push-Key": key})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))

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


# 세션이 어느 AI C-Level 인지 — 첫 사용자 메시지 안에 그 역할의 정의 파일 경로나 --role/--clevel 플래그가
# 박혀 있으면 잡힌다(GM 지시 2026-09-14 · CLAUDE.md §1 닉네임 표). 못 잡으면 폴더 이름을 그대로 쓴다.
ROLE_NICK = {
    "ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
    "coo": "시우", "cpo": "시포", "cto": "시토", "cbo": "시보",
}
ROLE_RE = re.compile(r'ai-(ceo|cfo|chro|cmo|coo|cpo|cto|cbo)\.md|--(?:role|clevel)[= ]"?(ceo|cfo|chro|cmo|coo|cpo|cto|cbo)"?', re.I)


def parse_file(path):
    """jsonl 한 파일 → {day: {model: bucket}}, project 이름, role(잡히면)."""
    days = {}
    project = "unknown"
    role = None
    sess_seen = {}  # day -> set(sessionId), bucket 안 sessions 중복 방지용
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if role is None:
                    m = ROLE_RE.search(line)
                    if m:
                        role = (m.group(1) or m.group(2)).lower()
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
    return {"days": days, "project": project, "role": role}


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

    # 계정별 집계(GM 지시 2026-09-14) — session_id(=파일명) → 계정 매핑을 먼저 읽는다.
    # 09-09 이전 세션은 이 로그에 없다 — 그런 세션은 전부 "미상(09-09 이전)" 한 계정으로 묶는다.
    session_account = {}
    if ACCOUNTS_LOG.exists():
        with open(ACCOUNTS_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    session_account[rec["sessionId"]] = rec["account"]
                except Exception:
                    continue
    UNKNOWN_ACCOUNT = "미상(09-09 이전)"
    acct_totals = {}  # account -> {input,cache_creation,cache_read,output,cost_usd,sessions:set}
    acct_proj = {}     # (account, project) -> {sessions:set, output, cost_usd} — "어디에 많이 썼나"

    for path in files:
        key = str(path)
        try:
            st = path.stat()
        except Exception:
            continue
        sig = "%d:%d" % (int(st.st_mtime), st.st_size)
        cached = cache.get(key)
        # "role" 이 없는 옛 캐시(스키마 변경 전)는 무효 처리 — 다시 파싱해 역할을 잡는다
        if cached and cached.get("sig") == sig and "role" in cached.get("data", {}):
            parsed = cached["data"]
        else:
            parsed = parse_file(path)
        new_cache[key] = {"sig": sig, "data": parsed}

        project = parsed.get("project", "unknown")
        where_label = ROLE_NICK.get(parsed.get("role"), project)  # 역할이 잡히면 폴더 대신 닉네임
        session_id = path.stem  # 파일명 = 세션ID(실측 2026-09-14) — sessionId 필드를 다시 파싱할 필요가 없다
        account = session_account.get(session_id, UNKNOWN_ACCOUNT)
        for day, models in parsed.get("days", {}).items():
            if day < cutoff:
                continue
            for model, b in models.items():
                # 옛 파일캐시 잔존분 방어(신규 필드 없음) — 아래 merged_days 쪽과 같은 이유로 .get() 을 쓴다
                b_safe = dict(b, cache_creation_5m=b.get("cache_creation_5m", 0), cache_creation_1h=b.get("cache_creation_1h", 0))
                krw, _, _ = cost_for_bucket(model, b_safe)
                usd = krw / USD_KRW
                at = acct_totals.setdefault(account, {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "cost_usd": 0.0, "sessions": set()})
                at["input"] += b["input"]; at["cache_creation"] += b["cache_creation"]
                at["cache_read"] += b["cache_read"]; at["output"] += b["output"]
                at["cost_usd"] += usd; at["sessions"].add(session_id)
                ap = acct_proj.setdefault((account, where_label), {"sessions": set(), "output": 0, "cost_usd": 0.0})
                ap["sessions"].add(session_id); ap["output"] += b["output"]; ap["cost_usd"] += usd

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

    by_account = {}
    for account, at in acct_totals.items():
        projs = sorted(
            ((proj, ap) for (acc, proj), ap in acct_proj.items() if acc == account),
            key=lambda x: x[1]["cost_usd"], reverse=True,
        )
        where = [
            {"project": proj, "sessions": len(ap["sessions"]), "output": ap["output"], "cost_usd": round(ap["cost_usd"], 2)}
            for proj, ap in projs[:8]
        ]
        by_account[account] = {
            "input": at["input"], "cache_creation": at["cache_creation"],
            "cache_read": at["cache_read"], "output": at["output"],
            "cost_usd": round(at["cost_usd"], 2), "sessions": len(at["sessions"]), "where": where,
        }
    for a in KNOWN_ACCOUNTS:  # 기록이 아직 없는 계정도 줄을 세운다(GM 지시 2026-09-09 관례 그대로)
        by_account.setdefault(a, {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "cost_usd": 0.0, "sessions": 0, "where": []})

    # 원격 PC 판 병합 — 이 PC 자기 계정+자기 호스트분은 건너뛴다(이중 집계 방지).
    remote_hosts = []
    remote_error = None
    push_key = read_push_key()
    if push_key:
        this_account, this_host = current_account(), socket.gethostname()
        try:
            remote = fetch_remote(push_key)
            for fname, payload in remote.items():
                acc = payload.get("account") or "미상"
                host = payload.get("host") or "미상"
                if acc == this_account and host == this_host:
                    continue
                remote_hosts.append(fname)
                rb = by_account.setdefault(acc, {"input": 0, "cache_creation": 0, "cache_read": 0,
                                                  "output": 0, "cost_usd": 0.0, "sessions": 0, "where": []})
                rb["input"] += payload.get("input", 0)
                rb["cache_creation"] += payload.get("cache_creation", 0)
                rb["cache_read"] += payload.get("cache_read", 0)
                rb["output"] += payload.get("output", 0)
                rb["cost_usd"] = round(rb["cost_usd"] + payload.get("cost_usd", 0.0), 2)
                rb["sessions"] += payload.get("sessions", 0)
                rb["where"] = sorted(rb["where"] + payload.get("where", []),
                                      key=lambda x: x.get("cost_usd", 0), reverse=True)[:8]
        except Exception as e:
            remote_error = "%s: %s" % (type(e).__name__, str(e)[:150])

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
            "by_account": by_account,
            "remote_hosts": remote_hosts,
            **({"remote_error": remote_error} if remote_error else {}),
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
