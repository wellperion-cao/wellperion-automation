#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""labs_loop.py — 랩스 3루프 원장 + 파트너 마케팅 결과물 7일 표 (GM 2026-09-18 「시보는 랩스 모듈
고도화→단순화→파트너사 피드백 3루프만 · 파트너 마케팅 자동화 결과물도 당분간 랩스에서 보자」).

scripts/labs_waiting.py 와 같은 구조: 원천 파일을 읽어 status/labs_loop.json 을 만들고
erp/admin/index.html 파트너사 관리 패널이 표 두 장(결과물 7일 · 3루프 원장)을 그린다.
3루프 원장(loop)만 사람이 --log 로 손으로 쌓는다 — 나머지는 매번 다시 계산한다.

원천(정본은 각 파일 · 여기는 읽기만):
  블로그         status/{gocheok,dietcamp}_blog_daily.json runs[]
  인스타         status/partner_instagram/{jo,dc}.json runs[]
  상담 질문 수   status/counsel_questions.jsonl (tenant · is_test 아닌 것)
  파트너 회신 수 1. AI자료_아카이브/11_카카오톡/{★조재오지점장님,다이어트캠프이승기대표님}/*/*_auto_*.txt (개수만 · 본문은 안 옮긴다)
예약 = counsel_questions.bat(22:10) · partner_instagram_daily.bat(07:20) 끝에 한 줄. 손 실행:
  C:/Python314/python.exe scripts/labs_loop.py
  C:/Python314/python.exe scripts/labs_loop.py --log --module 마케팅 --step 고도화 --note "..." [--week 2026-W38]
  C:/Python314/python.exe scripts/labs_loop.py --selfcheck
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "status" / "labs_loop.json"
KST = timezone(timedelta(hours=9))

TENANTS = {"jo": "3_gocheokgolf", "dc": "2_dietcamp"}
BLOG_FILES = {"jo": "gocheok_blog_daily.json", "dc": "dietcamp_blog_daily.json"}
PARTNER_LABEL = {"jo": "고척", "dc": "다캠"}
KAKAO_DIRS = {"jo": ("★조재오지점장님", "[조재오 지점장님]"), "dc": ("다이어트캠프이승기대표님", "[다이어트캠프 이승기 대표님]")}
DATE_HDR = re.compile(r"^-+\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _load_lines(p: Path) -> list[str]:
    try:
        return p.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []


def week_key(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_start(d: datetime) -> datetime:
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=d.weekday()))


# ---------- 결과물(outputs) — 블로그·인스타 최근 7일 ----------

def blog_outputs_from(data: dict, partner: str, cutoff: datetime) -> list[dict]:
    out = []
    for r in data.get("runs", []):
        try:
            dt = datetime.fromisoformat(r["date"][:19])
        except Exception:  # noqa: BLE001
            continue
        if dt < cutoff:
            continue
        url = r.get("url") or r.get("post_url")
        if url:
            status = "발행"
        elif r.get("result") == "ok":
            status = "임시저장"
        else:
            status = f"실패({(r.get('reason') or '')[:24]})"
        out.append({"_dt": dt, "date": dt.strftime("%Y-%m-%d"), "partner": partner, "channel": "블로그",
                    "title": r.get("topic", ""), "status": status, "link": url or ""})
    return out


def insta_outputs_from(data: dict, partner: str, cutoff: datetime) -> list[dict]:
    out = []
    for r in data.get("runs", []):
        at = r.get("at")
        if not at:
            continue
        try:
            dt = datetime.fromisoformat(at[:19])
        except Exception:  # noqa: BLE001
            continue
        if dt < cutoff:
            continue
        url = r.get("post_url") or r.get("url")
        if url or r.get("published_at"):
            status = "게시"
        elif r.get("sent"):
            status = "임시안(확인 대기)"
        else:
            status = "임시안"
        out.append({"_dt": dt, "date": dt.strftime("%Y-%m-%d"), "partner": partner, "channel": "인스타",
                    "title": r.get("topic", ""), "status": status, "link": url or ""})
    return out


def dedupe_latest(items: list[dict]) -> list[dict]:
    """같은 날 같은 파트너·채널 run 이 여럿이면 마지막 것만(원장 규칙)."""
    by_key: dict[tuple, dict] = {}
    for it in items:
        k = (it["date"], it["partner"], it["channel"])
        if k not in by_key or it["_dt"] > by_key[k]["_dt"]:
            by_key[k] = it
    rows = sorted(by_key.values(), key=lambda r: r["_dt"], reverse=True)
    return [{k: v for k, v in r.items() if k != "_dt"} for r in rows]


# ---------- 주간 집계(weekly) — 이번 주 + 지난주 ----------

def count_by_week(records: list[dict], starts: dict[str, datetime]) -> dict[str, int]:
    out = {wk: 0 for wk in starts}
    for r in records:
        dt = r["_dt"]
        for wk, ws in starts.items():
            if ws <= dt < ws + timedelta(days=7):
                out[wk] += 1
    return out


def counsel_counts_from(lines: list[str], starts: dict[str, datetime]) -> dict[tuple[str, str], int | None]:
    if not lines:
        return {(wk, p): None for wk in starts for p in TENANTS}
    hits: dict[tuple[str, str], int] = {(wk, p): 0 for wk in starts for p in TENANTS}
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if r.get("is_test"):
            continue
        sid = r.get("session_id") or ""
        if sid.startswith(("test-", "cbo-test-", "sito-check-")):
            continue
        partner = next((k for k, t in TENANTS.items() if t == r.get("tenant")), None)
        if not partner:
            continue
        try:
            dt = datetime.fromisoformat(r["ts"][:19])
        except Exception:  # noqa: BLE001
            continue
        for wk, ws in starts.items():
            if ws <= dt < ws + timedelta(days=7):
                hits[(wk, partner)] += 1
    return hits


def reply_counts_from(lines: list[str], tag: str, starts: dict[str, datetime]) -> dict[str, int]:
    out = {wk: 0 for wk in starts}
    cur = None
    for ln in lines:
        m = DATE_HDR.match(ln)
        if m:
            cur = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            continue
        if cur and ln.startswith(tag):
            for wk, ws in starts.items():
                if ws <= cur < ws + timedelta(days=7):
                    out[wk] += 1
    return out


def latest_kakao_file(dirname: str) -> Path | None:
    base = ROOT / "1. AI자료_아카이브" / "11_카카오톡" / dirname
    files = sorted(base.glob("*/*_auto_*.txt"))
    return files[-1] if files else None


# ---------- 조립 ----------

def build(now: datetime, loop: list[dict]) -> dict:
    now_n = now.replace(tzinfo=None)  # 원천 파일 시각이 naive KST 라 계산은 naive 로 맞춘다
    this_start = week_start(now_n)
    last_start = this_start - timedelta(days=7)
    starts = {week_key(this_start): this_start, week_key(last_start): last_start}
    cutoff14 = last_start

    blog_recs, insta_recs = [], []
    for partner, fname in BLOG_FILES.items():
        blog_recs += blog_outputs_from(_load_json(ROOT / "status" / fname, {}), partner, cutoff14)
    for partner in TENANTS:
        insta_recs += insta_outputs_from(_load_json(ROOT / "status" / "partner_instagram" / f"{partner}.json", {}), partner, cutoff14)

    outputs = dedupe_latest([r for r in blog_recs + insta_recs if r["_dt"] >= now_n - timedelta(days=7)])

    counsel_lines = _load_lines(ROOT / "status" / "counsel_questions.jsonl")
    q = counsel_counts_from(counsel_lines, starts)

    weekly = []
    for partner in TENANTS:
        insta_pub = count_by_week([r for r in insta_recs if r["partner"] == partner and r["status"] == "게시"], starts)
        blog_pub = count_by_week([r for r in blog_recs if r["partner"] == partner and r["status"] == "발행"], starts)
        blog_draft = count_by_week([r for r in blog_recs if r["partner"] == partner and r["status"] == "임시저장"], starts)
        dirname, tag = KAKAO_DIRS[partner]
        kfile = latest_kakao_file(dirname)
        replies = reply_counts_from(_load_lines(kfile), tag, starts) if kfile else None
        for wk in starts:
            weekly.append({
                "week": wk, "partner": partner,
                "insta": insta_pub.get(wk, 0), "blog_pub": blog_pub.get(wk, 0), "blog_draft": blog_draft.get(wk, 0),
                "questions": q.get((wk, partner)), "replies": (replies.get(wk) if replies is not None else None),
            })
    weekly.sort(key=lambda r: (r["week"], r["partner"]), reverse=True)

    return {"_about": "랩스 마케팅 결과물 7일 + 3루프 원장 — scripts/labs_loop.py 가 만든다. loop 만 --log 로 손으로 쌓는다.",
            "generated_at": now.isoformat(timespec="seconds"), "outputs": outputs, "weekly": weekly, "loop": loop}


DEFAULT_LOOP = [
    {"week": "2026-W38", "module": "마케팅", "step": "고도화",
     "note": "아침 톡 0통 · 인스타 우선 자동 게시 · 블로그 파생 · 평일 5일·주말 평가(GM 2026-09-18)", "at": "2026-09-18T10:20:00"},
    {"week": "2026-W38", "module": "상담", "step": "고도화",
     "note": "시험·손님 세션 가르기 · 인스타 프로필 링크 · 웰페리온 빈칸 8 · 예약 클릭 세기(제안 2026-09-18)", "at": "2026-09-18T10:20:00"},
]


def selfcheck() -> None:
    now = datetime(2026, 9, 18, 12, 0)
    this_start = week_start(now)
    starts = {week_key(this_start): this_start}
    cutoff = now - timedelta(days=7)

    fake_blog = {"runs": [
        {"date": "2026-09-17 10:00:00", "topic": "가짜글", "result": "ok"},
        {"date": "2026-09-17 11:00:00", "topic": "가짜글", "result": "ok", "url": "http://example.test/1"},
        {"date": "2026-09-01 10:00:00", "topic": "옛글", "result": "ok"},
    ]}
    outs = dedupe_latest(blog_outputs_from(fake_blog, "jo", cutoff))
    assert len(outs) == 1 and outs[0]["status"] == "발행", outs

    fake_lines = [
        json.dumps({"ts": "2026-09-17T10:00:00", "tenant": "3_gocheokgolf", "is_test": False, "session_id": "abc"}),
        json.dumps({"ts": "2026-09-17T10:05:00", "tenant": "3_gocheokgolf", "is_test": False, "session_id": "test-1"}),
        json.dumps({"ts": "2026-09-17T10:10:00", "tenant": "2_dietcamp", "is_test": True, "session_id": "xyz"}),
    ]
    q = counsel_counts_from(fake_lines, starts)
    wk = week_key(this_start)
    assert q[(wk, "jo")] == 1 and q[(wk, "dc")] == 0, q
    assert counsel_counts_from([], starts) == {(wk, "jo"): None, (wk, "dc"): None}

    fake_kakao = [
        "--------------- 2026년 9월 17일 목요일 ---------------",
        "[조재오 지점장님] [오전 10:16] 답1",
        "[조재오 지점장님] [오전 10:17] 답2",
        "--------------- 2026년 9월 1일 화요일 ---------------",
        "[조재오 지점장님] [오전 10:16] 옛답",
    ]
    r = reply_counts_from(fake_kakao, "[조재오 지점장님]", starts)
    assert r[wk] == 2, r

    d = build(now, list(DEFAULT_LOOP))
    assert isinstance(d["outputs"], list) and isinstance(d["weekly"], list) and len(d["loop"]) == 2
    print("labs_loop selfcheck 통과")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="store_true", help="loop 원장에 한 줄 append")
    ap.add_argument("--module", choices=["마케팅", "상담"])
    ap.add_argument("--step", choices=["고도화", "단순화", "피드백"])
    ap.add_argument("--note")
    ap.add_argument("--week")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        selfcheck()
        return

    now = datetime.now(KST)
    existing = _load_json(OUT, {})
    loop = existing.get("loop") or list(DEFAULT_LOOP)

    if args.log:
        if not (args.module and args.step and args.note):
            raise SystemExit("--log 는 --module --step --note 가 다 있어야 한다")
        loop.append({"week": args.week or week_key(now), "module": args.module, "step": args.step,
                    "note": args.note, "at": now.isoformat(timespec="seconds")})

    d = build(now, loop)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"labs_loop outputs {len(d['outputs'])}건 · weekly {len(d['weekly'])}행 · loop {len(d['loop'])}건 → {OUT.name}")


if __name__ == "__main__":
    main()
