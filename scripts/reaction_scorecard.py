#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reaction_scorecard.py — 발행 루프를 감싸는 상위 루프: 콘텐츠 1건 = 반응 성적표 1장.

GM 지시(2026-07-20): "이 루프를 또 감싸서 반응에 대한 파악을 하고, 반응이 없으면
반응이 있게 만드는 작업도 필요해." 배834(북극성 지향 제작 루프)의 원래 취지 —
"제작이 북극성/성과를 보고 각을 고르는 폐루프" — 를 잇는다. 클릭 집계는 2026-07-15
GM 결정(커밋 7f87b0b6)으로 삭제됐으므로 되살리지 않는다 — 아래 3종 **실측 가능한**
신호만 대체 입력으로 쓴다(지어낸 지표 금지, 약속 L05):

  ① IG 편별 도달(reach)   — status/ig_reach_ledger.json (배546, 매일 09:45 자동수집)
  ② 당근 조회/찜          — 3. 웰페리온 가이드/cmo/funnel/engagement/engagement_feed.json (배?, 매일 09:30)
  ③ 네이버 카페 조회      — 동일 engagement_feed.json(카페는 GM 데스크톱 세션 필요 · 희소)
  ④ 네이버 블로그         — 동일 engagement_feed.json, RSS 신규감지만 가능(조회수는 로그인 필요
                             → 항상 "미측정", 0으로 위장하지 않음)
  ⑤ 채널별 문의→가입 전환 — status/kpi_values.json roles.cmo(누적 집계 — 편별 귀속 불가,
                             §2 참고 문맥으로만 언급. 이 스크립트의 판정에는 쓰지 않음)
  ✗ IG 좋아요·저장         — 비공개 지표, 수집 불가(쓰지 않음)

저장 위치: status/cmo_reaction_scorecard.json 단일 파일 — status/ig_reach_ledger.json ·
status/kpi_values.json 등 기존 status/*.json 플랫 원장 관례를 그대로 따른다(새 폴더·새
레지스트리 시스템 신설 없음). 콘텐츠 그룹키는 publish_digest.py와 동일한 "folder"
(예: instagram/260718_L4_필라테스) — 기존 그룹핑 재사용.

판정(반응 없음): **최근 발행분 대비 상대 기준**만 쓴다(절대 숫자 무의미). IG 도달을
1차 신호로 — 최근 POOL_SIZE편(같은 계정·공식) 중 매칭 성공한 항목들의 최신 도달 중앙값
대비 현재 편이 LOW_RATIO 미만이면 "저조". 비교 표본이 MIN_POOL 미만이거나 발행
MIN_AGE_HOURS 시간 미경과면 "판정보류"(억지 판정 금지).

개선안: 반무인(GM 확정 2026-07-15) — 자동 생성해 GM께 제안만 한다. 재발행·수정 등
비가역 행동은 절대 자동 실행하지 않음(GM 승인 후 시모가 수행). 제안은 실측 수치와
로드맵(instagram/_공식시리즈_로드맵.md) ANGLE 카드에 근거해 구체적으로 작성(일반론 금지).

실행:
  스캔만(파일 갱신, 텔레그램 없음):        python scripts\\reaction_scorecard.py --scan
  스캔 + 저조 건 GM 알림(운영 경로):        python scripts\\reaction_scorecard.py --scan --alert
  로직만 확인(파일 저장·전송 전부 생략):    python scripts\\reaction_scorecard.py --scan --dry-run
  한 장 요약 출력(주기 보고용 텍스트):      python scripts\\reaction_scorecard.py --summary

자동 실행 연계: ig_reach_collector.py main() 성공 경로 끝에서 scan_and_alert()를
best-effort 호출(신규 예약작업 미생성 — 매일 09:45 IG 도달 수집에 편승, 2026-07-20 배834).

텔레그램: 저조 건 알림·요약 모두 GM 개인 업무보고봇 방(TELEGRAM_CHAT_ID)으로만 발송한다
(GM 2026-07-20 지시 — 실무진방 금지, 승인 필요한 제안이므로 GM 개인 방이 맞는 경로).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향(기존 스크립트들과 동일 패턴)
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass

    def pace(*a, **k):
        return None

# ── 경로 (기존 구조 그대로 — 새 폴더 없음) ─────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = _SCRIPT_DIR.parent
REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
IG_REACH_LEDGER_PATH = ROOT / "status" / "ig_reach_ledger.json"
ENGAGEMENT_FEED_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "funnel" / "engagement" / "engagement_feed.json"
OFFICIAL_ROADMAP_PATH = ROOT / "instagram" / "_공식시리즈_로드맵.md"
SCORECARD_PATH = ROOT / "status" / "cmo_reaction_scorecard.json"
ENV_PATH = ROOT / "telegram_bot" / ".env"

OFFICIAL_ACCOUNT = "wellperion"
PUBLISHED_STATUS = "발행완료"

# ── 판정 파라미터 (실측 캘리브레이션 여지 — 표본이 부족하면 억지 판정하지 않음) ──
MIN_AGE_HOURS = 24       # T+24h 미만이면 "판정보류(24시간 미경과)"
MIN_POOL = 3              # 비교풀 매칭 3건 미만이면 "판정보류(표본부족)"
POOL_SIZE = 5             # 비교풀 = 최근 발행순 상위 N편(현재 편 제외)
LOW_RATIO = 0.5           # 현재/중앙값 < 이 비율이면 "저조"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"  # GM 개인 업무보고봇 방(8254867551)

_OUTPUT_SUFFIX_RE = re.compile(r"/output\([^)]*\)\s*$")
_TZOFF_RE = re.compile(r"[+-]\d{2}:\d{2}$")


# ── 공용 유틸 ──────────────────────────────────────────────────────
def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_env_value(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        if ENV_PATH.exists():
            for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _parse_dt(raw) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        if len(s) == 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.strptime(s, "%Y-%m-%d")
        s2 = s.replace("Z", "")
        s2 = _TZOFF_RE.sub("", s2)
        return datetime.fromisoformat(s2)
    except Exception:
        return None


def _base_key(folder: str) -> str:
    return _OUTPUT_SUFFIX_RE.sub("", (folder or "").strip())


def _norm_url(u: str | None) -> str:
    if not u:
        return ""
    u = u.strip()
    u = u.split("?", 1)[0]
    return u.rstrip("/")


# ── ① 공식 IG 발행 목록 (review_queue.json 재사용, publish_digest.py 그룹핑과 동일 관례) ──
def load_official_ig_published(now: datetime | None = None) -> list[dict]:
    """account==wellperion · channel에 '인스타' 포함 · status==발행완료 항목을 folder 단위로
    1건씩(post_url 있는 엔트리 우선) 뽑아 published_dt 내림차순 정렬."""
    items = _load_json(REVIEW_QUEUE_PATH, [])
    if not isinstance(items, list):
        return []
    by_folder: dict[str, dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("account") != OFFICIAL_ACCOUNT:
            continue
        if "인스타" not in (it.get("channel") or ""):
            continue
        if it.get("status") != PUBLISHED_STATUS:
            continue
        dt = _parse_dt(it.get("published_at"))
        if dt is None:
            continue
        folder = _base_key(it.get("folder") or "")
        if not folder:
            continue
        cur = by_folder.get(folder)
        cur_has_url = bool(cur and (cur.get("post_url") or "").strip())
        new_has_url = bool((it.get("post_url") or "").strip())
        if cur is None or (new_has_url and not cur_has_url) or (
            new_has_url == cur_has_url and dt > cur["published_dt"]
        ):
            by_folder[folder] = {
                "folder": folder,
                "title": it.get("title") or "(제목 없음)",
                "post_url": it.get("post_url"),
                "published_at": it.get("published_at"),
                "published_dt": dt,
                "id": it.get("id"),
            }
    out = list(by_folder.values())
    out.sort(key=lambda x: x["published_dt"], reverse=True)
    return out


def _sibling_channel_entries(folder: str) -> dict[str, dict]:
    """같은 folder 그룹의 채널별(블로그·카페·당근) post_url — publish_digest.py의 folder
    그룹핑과 동일 로직. 카카오는 반응 공개 비노출이라 조회 안 함(engagement_collector.py 주석)."""
    items = _load_json(REVIEW_QUEUE_PATH, [])
    if not isinstance(items, list):
        return {}
    out: dict[str, dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        if _base_key(it.get("folder") or "") != folder:
            continue
        ch = it.get("channel") or ""
        if "블로그" in ch:
            key = "blog"
        elif "카페" in ch:
            key = "cafe"
        elif "당근" in ch:
            key = "danggn"
        else:
            continue
        url = (it.get("post_url") or "").strip()
        if url and (key not in out or not out[key].get("post_url")):
            out[key] = {"post_url": url, "channel": ch}
        elif key not in out:
            out[key] = {"post_url": url, "channel": ch}
    return out


# ── ② IG 도달 신호 (status/ig_reach_ledger.json 재사용) ─────────────────
def _ig_reach_signal(post_url: str | None, ledger: dict) -> dict | None:
    if not post_url:
        return None
    target = _norm_url(post_url)
    for media in ledger.get("media_snapshots") or []:
        if not isinstance(media, dict):
            continue
        if _norm_url(media.get("permalink")) != target:
            continue
        snaps = media.get("snapshots") or []
        if not snaps:
            return None
        latest = snaps[-1]
        return {
            "status": "measured",
            "media_id": media.get("media_id"),
            "first_seen": media.get("first_seen"),
            "latest_date": latest.get("date"),
            "latest_reach": latest.get("reach"),
            "snapshot_count": len(snaps),
        }
    return None


# ── ③④ 당근·카페·블로그 신호 (engagement_feed.json 재사용) ────────────
def _engagement_signal(post_url: str | None, channel_key: str, events: list[dict]) -> dict | None:
    """channel_key: '당근'|'카페'|'블로그'. url 매칭 최신(collected_at) 이벤트 1건.
    없으면 None(→ 상위에서 '미측정' 표기)."""
    if not post_url:
        return None
    target = _norm_url(post_url)
    matches = [
        e for e in events
        if isinstance(e, dict) and e.get("channel") == channel_key and _norm_url(e.get("url")) == target
    ]
    if not matches:
        return None
    matches.sort(key=lambda e: e.get("collected_at") or "", reverse=True)
    latest = matches[0]
    return latest


def _danggn_signal(post_url: str | None, events: list[dict]) -> dict | None:
    e = _engagement_signal(post_url, "당근", events)
    if e is None:
        return None
    return {
        "status": "measured",
        "views": e.get("totalViews", e.get("dViews")),
        "bookmarks": e.get("totalBookmarks", e.get("dInterest")),
        "collected_at": e.get("collected_at"),
    }


def _cafe_signal(post_url: str | None, events: list[dict]) -> dict | None:
    e = _engagement_signal(post_url, "카페", events)
    if e is None:
        return None
    return {
        "status": "measured",
        "views": e.get("totalViews", e.get("dViews")),
        "collected_at": e.get("collected_at"),
    }


def _blog_signal(post_url: str | None, events: list[dict]) -> dict | None:
    """블로그는 RSS 신규감지만 가능 — 조회수는 항상 미측정(로그인 필요, 0 위장 금지)."""
    e = _engagement_signal(post_url, "블로그", events)
    if e is None:
        return None
    return {"status": "detected_no_views", "collected_at": e.get("collected_at"),
            "note": "발행 감지됨 — 조회수는 네이버 로그인 필요라 수집 불가(0 아님, 미측정)"}


# ── 로드맵 ANGLE 조회 (ig_series_producer.py 파서 재사용 — 신규 파서 미작성) ──
def _lookup_roadmap_angle(folder: str) -> dict | None:
    try:
        from ig_series_producer import parse_roadmap_episodes, parse_episode_cards
    except Exception:
        return None
    try:
        text = OFFICIAL_ROADMAP_PATH.read_text(encoding="utf-8")
        episodes = parse_roadmap_episodes(text)
        cards = parse_episode_cards(text)
    except Exception:
        return None
    basename = folder.rsplit("/", 1)[-1]
    for ep in episodes:
        if ep.get("folder") == basename:
            card = cards.get(ep["num"], {})
            return {"num": ep["num"], "title": ep.get("title"), "angle": card.get("ANGLE"),
                    "goal_kpi": card.get("GOAL_KPI")}
    return None


def _upcoming_roadmap_candidates(limit: int = 2) -> list[dict]:
    """§2 로드맵에서 상태=='기획예정' 행 상위 limit건 — 다음 편 제안 참고용(발명 아님, 로드맵 SSOT)."""
    try:
        from ig_series_producer import parse_roadmap_episodes
    except Exception:
        return []
    try:
        episodes = parse_roadmap_episodes(OFFICIAL_ROADMAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = [ep for ep in episodes if "기획예정" in (ep.get("status") or "")]
    return out[:limit]


# ── 판정 ──────────────────────────────────────────────────────────
def judge(current_reach: int | None, pool_reach: list[int], age_hours: float) -> tuple[str, str]:
    """반환: (verdict, reason). verdict ∈ {"판정보류", "저조", "정상범위"}."""
    if age_hours < MIN_AGE_HOURS:
        return "판정보류", f"발행 {age_hours:.1f}시간 경과 — {MIN_AGE_HOURS}시간 미경과(측정 시점 아님)"
    if current_reach is None:
        return "판정보류", "IG 도달 데이터 미매칭(수집 지연 또는 게시물 목록 이탈)"
    if len(pool_reach) < MIN_POOL:
        return "판정보류", f"비교 표본 부족(매칭 {len(pool_reach)}건 < {MIN_POOL}건)"
    sorted_pool = sorted(pool_reach)
    n = len(sorted_pool)
    median = sorted_pool[n // 2] if n % 2 else (sorted_pool[n // 2 - 1] + sorted_pool[n // 2]) / 2
    if median <= 0:
        return "판정보류", "비교풀 중앙값 0 — 판정 불가"
    ratio = current_reach / median
    if ratio < LOW_RATIO:
        return "저조", f"현재 도달 {current_reach} / 최근 {n}편 중앙값 {median:.0f} = {ratio*100:.0f}%(<{LOW_RATIO*100:.0f}%)"
    return "정상범위", f"현재 도달 {current_reach} / 최근 {n}편 중앙값 {median:.0f} = {ratio*100:.0f}%"


def _propose_improvement(cur: dict, pool_items: list[dict]) -> str:
    """반응 저조 시 개선안 초안 — 실측 수치·로드맵 ANGLE 근거만 사용(일반론 금지, 발명 금지).
    최종 각(角) 확정·재발행 등 비가역 행동은 GM 승인 필요(반무인, 2026-07-15 GM 확정)."""
    matched = [p for p in pool_items if p.get("reach") is not None]
    if not matched:
        return "비교 대상 편의 도달 데이터가 없어 구체 제안 불가 — 표본 축적 후 재평가."
    top = max(matched, key=lambda p: p["reach"])
    cur_angle = _lookup_roadmap_angle(cur["folder"])
    top_angle = _lookup_roadmap_angle(top["folder"])
    lines = []
    lines.append(
        f"최근 최고 도달 편 = '{top['title']}'(도달 {top['reach']}, {top['folder']}) — "
        f"현재 편 도달({cur.get('reach')})의 {(top['reach'] / cur['reach']):.1f}배."
    )
    if top_angle and top_angle.get("angle"):
        lines.append(f"그 편의 로드맵 각(ANGLE)='{top_angle['angle']}'"
                      + (f"(GOAL_KPI={top_angle['goal_kpi']})" if top_angle.get("goal_kpi") else "") + ".")
    if cur_angle and cur_angle.get("angle"):
        lines.append(f"현재 편 각(ANGLE)='{cur_angle['angle']}' — 표본 1건 비교라 각 자체가 원인이라 단정은 어려움.")
    else:
        lines.append("현재 편은 공식 로드맵 미등재(각 태그 없음) — 로드맵 등재 검토 필요.")
    upcoming = _upcoming_roadmap_candidates(limit=2)
    if upcoming:
        cand = " / ".join(f"'{ep['title']}'({ep['message'][:40]}…)" for ep in upcoming)
        lines.append(f"다음 편 후보(로드맵 §2 '기획예정'): {cand} — 우선 검토 제안.")
    lines.append("⚠️ 표본 규모상 결정적 원인 단정 불가 — 최종 각 확정·재작업은 시모 정성 판단 + GM 승인 필요(자동 재발행 없음).")
    return " ".join(lines)


# ── 성적표 조립 ────────────────────────────────────────────────────
def build_scorecards(now: datetime | None = None) -> dict[str, dict]:
    now = now or datetime.now()
    ig_ledger = _load_json(IG_REACH_LEDGER_PATH, {"media_snapshots": []})
    feed = _load_json(ENGAGEMENT_FEED_PATH, {"events": []})
    events = feed.get("events") or []
    published = load_official_ig_published(now)

    # 매칭된 IG 도달값 미리 계산(비교풀 산출에 재사용)
    reach_by_folder: dict[str, dict] = {}
    for p in published:
        sig = _ig_reach_signal(p.get("post_url"), ig_ledger)
        reach_by_folder[p["folder"]] = sig

    existing = _load_json(SCORECARD_PATH, {})
    if not isinstance(existing, dict):
        existing = {}

    scorecards: dict[str, dict] = {}
    for idx, p in enumerate(published):
        folder = p["folder"]
        age_hours = (now - p["published_dt"]).total_seconds() / 3600.0
        ig_sig = reach_by_folder.get(folder)
        current_reach = ig_sig["latest_reach"] if ig_sig else None

        # 비교풀: 현재 편보다 먼저 발행된(=현재보다 나중 인덱스) 최근 POOL_SIZE편 중 매칭 성공분
        pool_source = published[idx + 1: idx + 1 + POOL_SIZE * 2]  # 여유있게 확보 후 매칭 성공분만 채택
        pool_items = []
        for q in pool_source:
            qsig = reach_by_folder.get(q["folder"])
            if qsig and isinstance(qsig.get("latest_reach"), (int, float)):
                pool_items.append({"folder": q["folder"], "title": q["title"], "reach": qsig["latest_reach"]})
            if len(pool_items) >= POOL_SIZE:
                break
        pool_reach = [p2["reach"] for p2 in pool_items]

        verdict, reason = judge(current_reach, pool_reach, age_hours)

        siblings = _sibling_channel_entries(folder)
        danggn_sig = _danggn_signal(siblings.get("danggn", {}).get("post_url"), events)
        cafe_sig = _cafe_signal(siblings.get("cafe", {}).get("post_url"), events)
        blog_sig = _blog_signal(siblings.get("blog", {}).get("post_url"), events)

        prior = existing.get(folder, {})
        card = {
            "folder": folder,
            "title": p["title"],
            "published_at": p["published_at"],
            "age_hours_at_scan": round(age_hours, 1),
            "channels": {
                "instagram": ig_sig or {"status": "미측정", "note": "도달 데이터 미매칭(수집 지연 가능)"},
                "danggn": danggn_sig or {"status": "미측정", "note": "engagement_feed 매칭 없음(신규 발행 직후이거나 수집 전)"},
                "cafe": cafe_sig or {"status": "미측정", "note": "카페 조회는 GM 데스크톱 세션 수동 수집 — 희소"},
                "blog": blog_sig or {"status": "미측정", "note": "RSS 신규감지 전 또는 조회수 자체가 로그인 필요(수집 불가)"},
            },
            "verdict": verdict,
            "verdict_reason": reason,
            "compare_pool": pool_items,
            "measured_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "alerted": bool(prior.get("alerted")),
        }
        if verdict == "저조":
            card["improvement_proposal"] = _propose_improvement(
                {"folder": folder, "reach": current_reach}, pool_items
            )
        scorecards[folder] = card

    return scorecards


def scan(now: datetime | None = None, dry_run: bool = False) -> dict[str, dict]:
    scorecards = build_scorecards(now)
    if not dry_run:
        _save_json(SCORECARD_PATH, scorecards)
    return scorecards


# ── GM 개인 방 알림(저조 건, 반무인 — 제안만·자동실행 없음) ──────────────
def _send_gm(text: str) -> bool:
    token = _load_env_value(TELEGRAM_TOKEN_ENV_KEY)
    chat_id = _load_env_value(TELEGRAM_CHAT_ID_ENV_KEY)
    if not token or not chat_id:
        print("[ERROR] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정 — GM 알림 발송 불가", file=sys.stderr)
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
        pace()
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            log_outbound(text, chat_id=chat_id, source="reaction_scorecard._send_gm", ok=ok, kind="sendMessage")
            return ok
    except Exception as e:
        print(f"[WARN] GM 알림 발송 실패: {e}", file=sys.stderr)
        log_outbound(text, chat_id=chat_id, source="reaction_scorecard._send_gm", ok=False, kind="sendMessage")
        return False


def scan_and_alert(now: datetime | None = None, dry_run: bool = False) -> dict[str, dict]:
    """스캔 후 verdict=='저조' & 아직 미알림인 건만 GM 업무보고봇 방에 발송(중복 방지: alerted 플래그).
    best-effort — 텔레그램 실패해도 스캔 결과 자체는 반환/저장(dry_run 아니면)."""
    scorecards = build_scorecards(now)
    for folder, card in scorecards.items():
        if card.get("verdict") != "저조" or card.get("alerted"):
            continue
        msg = (
            f"📉 콘텐츠 반응 저조 감지 — {card['title']}\n"
            f"{card['verdict_reason']}\n\n"
            f"제안: {card.get('improvement_proposal', '(제안 생성 실패)')}\n\n"
            f"※ 반무인 — 이 알림은 제안만입니다. 재발행·수정 등 실제 조치는 GM 승인 후 진행됩니다."
        )
        if dry_run:
            print("[DRY-RUN] → GM 업무보고봇 방 대상(실전송 없음)")
            print(msg)
            print("-" * 40)
            continue
        ok = _send_gm(msg)
        if ok:
            card["alerted"] = True
            print(f"[INFO] 저조 알림 발송 완료: {folder}")
        else:
            print(f"[WARN] 저조 알림 발송 실패: {folder}")
    if not dry_run:
        _save_json(SCORECARD_PATH, scorecards)
    return scorecards


# ── 한 장 요약 (주기 보고 — 기존 GM 업무보고 경로에 텍스트로 얹는 용도) ──────
def build_summary_text(scorecards: dict[str, dict] | None = None, limit: int = 10) -> str:
    scorecards = scorecards if scorecards is not None else _load_json(SCORECARD_PATH, {})
    items = sorted(scorecards.values(), key=lambda c: c.get("published_at") or "", reverse=True)[:limit]
    if not items:
        return "콘텐츠 반응 성적표 — 아직 집계된 편 없음."
    lines = [f"콘텐츠 반응 성적표 (최근 {len(items)}편)", ""]
    for c in items:
        ig = c["channels"].get("instagram", {})
        reach = ig.get("latest_reach", "—") if ig.get("status") == "measured" else "미측정"
        tag = {"저조": "🔻", "정상범위": "✅", "판정보류": "⏳"}.get(c["verdict"], "•")
        lines.append(f"{tag} {c['title']} — 도달 {reach} · {c['verdict']}({c['verdict_reason']})")
        if c["verdict"] == "저조" and c.get("improvement_proposal"):
            lines.append(f"   └ 제안: {c['improvement_proposal']}")
    return "\n".join(lines)


def _parse_args():
    p = argparse.ArgumentParser(description="발행 콘텐츠 반응 성적표 — 측정/판정/개선제안(반무인)")
    p.add_argument("--scan", action="store_true", help="성적표 스캔·갱신(status/cmo_reaction_scorecard.json)")
    p.add_argument("--alert", action="store_true", help="스캔 후 저조 건 GM 업무보고봇 방 알림 발송")
    p.add_argument("--summary", action="store_true", help="현재 성적표 한 장 요약 텍스트 출력")
    p.add_argument("--dry-run", action="store_true", help="파일 저장·텔레그램 실전송 생략(로직만 확인)")
    return p.parse_args()


def main():
    args = _parse_args()
    if args.summary and not args.scan and not args.alert:
        print(build_summary_text())
        return
    if args.alert:
        cards = scan_and_alert(dry_run=args.dry_run)
    elif args.scan or not (args.summary):
        cards = scan(dry_run=args.dry_run)
    else:
        cards = _load_json(SCORECARD_PATH, {})
    print(f"[INFO] 성적표 {len(cards)}건 처리 완료" + (" (dry-run, 저장 없음)" if args.dry_run else f" → {SCORECARD_PATH}"))
    for folder, c in cards.items():
        print(f"  - {c['title']} [{folder}] → {c['verdict']}: {c['verdict_reason']}")
    if args.summary:
        print("-" * 60)
        print(build_summary_text(cards))


if __name__ == "__main__":
    main()
