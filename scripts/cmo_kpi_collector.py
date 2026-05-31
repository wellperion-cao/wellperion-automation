"""웰페리온 CMO KPI 집계기 v1
채널별 KPI를 한 곳에 집계. 외부 API 토큰 없이 동작.

입력 소스:
  1. 3. 웰페리온 가이드/cmo/review/review_queue.json  — 검수 큐 (발행상태·채널별)
  2. instagram/{YYMMDD_*}/                           — 콘텐츠 폴더 발행 이력 스캔
  3. status/cmo.json                                 — CMO 에이전트 완료 태스크 이력
  4. status/kpi_manual.json                          — litt.ly 클릭수 등 수동 입력

출력:
  status/cmo_kpi.json         — 채널별 발행수·검수대기·승인·수동 KPI·집계일시
  status/cmo_kpi_report.html  — 독립 HTML 리포트 (메인 가이드 미접촉)
  콘솔 요약표

TODO (v2 이상, GM 결재 후):
  - IG Insights (Meta Graph API) — 도달수·좋아요·저장 (토큰 필요 🔒)
  - 네이버 블로그 통계 API       — 조회수·유입 (토큰/쿠키 필요 🔒)
  - 네이버 카페 통계 API         — 조회수·댓글수 (토큰 필요 🔒)
"""

from __future__ import annotations

import io
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Windows 콘솔이 cp949일 때 인코딩 불가 문자를 '?'로 대체해 UnicodeEncodeError 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp949", "cp950", "euc-kr"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding=sys.stdout.encoding, errors="replace"
    )

# ──────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

REVIEW_QUEUE_PATH = PROJECT_ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
INSTAGRAM_ROOT    = PROJECT_ROOT / "instagram"
CMO_STATUS_PATH   = PROJECT_ROOT / "status" / "cmo.json"
KPI_MANUAL_PATH   = PROJECT_ROOT / "status" / "kpi_manual.json"
KPI_OUTPUT_PATH   = PROJECT_ROOT / "status" / "cmo_kpi.json"
KPI_REPORT_PATH   = PROJECT_ROOT / "status" / "cmo_kpi_report.html"

# 채널 공식 레이블 (정규화 키 → 표시명)
CHANNEL_LABELS: dict[str, str] = {
    "ig":    "IG namuk.wellperion",
    "blog":  "네이버 블로그",
    "cafe":  "동부이촌동 카페",
    "other": "기타",
}

# 채널 키워드 → 채널 키 매핑 (review_queue channel 필드 정규화)
_CH_MAP: list[tuple[str, str]] = [
    ("인스타", "ig"),
    ("Instagram", "ig"),
    ("IG", "ig"),
    ("namuk", "ig"),
    ("블로그", "blog"),
    ("blog", "blog"),
    ("카페", "cafe"),
    ("cafe", "cafe"),
    ("ichon", "cafe"),
]

# 상태값 정규화 셋
STATUS_PUBLISHED = {"발행완료", "게시완료", "완료", "published"}
STATUS_PENDING   = {"검수대기", "검토중", "대기", "pending", "review"}
STATUS_APPROVED  = {"승인", "검수완료", "approved"}

# 콘텐츠 폴더명에서 날짜 추출용 (YYMMDD 6자리 패턴)
_FOLDER_DATE_RE = re.compile(r"^(\d{6})_")


def _normalize_channel(raw: str) -> str:
    """review_queue channel 문자열 → 채널 키."""
    for kw, key in _CH_MAP:
        if kw in raw:
            return key
    return "other"


def _empty_channel_stats() -> dict[str, Any]:
    return {
        "published": 0,
        "pending_review": 0,
        "approved": 0,
        "total_queue": 0,
        "folder_count": 0,   # instagram/ 폴더 기반 집계
        "post_urls": [],      # 발행완료 URL 목록
        "trend": {},          # YYYYMM → 발행수 추이
    }


# ──────────────────────────────────────────────
# 소스 1: review_queue.json 파싱
# ──────────────────────────────────────────────

def load_review_queue() -> list[dict]:
    """review_queue.json 로드. 없으면 빈 리스트."""
    if not REVIEW_QUEUE_PATH.exists():
        print(f"[skip] review_queue.json 없음: {REVIEW_QUEUE_PATH}")
        return []
    for enc in ("utf-8", "cp949", "utf-8-sig"):
        try:
            with open(REVIEW_QUEUE_PATH, "r", encoding=enc) as f:
                data = json.load(f)
            records = data if isinstance(data, list) else []
            print(f"[ok] review_queue.json 로드({enc}): {len(records)}건")
            return records
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    print("[warn] review_queue.json 파싱 실패 — 모든 인코딩 시도 소진")
    return []


def aggregate_review_queue(
    records: list[dict],
    stats: dict[str, dict],
) -> None:
    """review_queue 레코드로 채널별 stats 갱신 (in-place)."""
    for rec in records:
        raw_ch = rec.get("channel", "")
        ch_key = _normalize_channel(str(raw_ch))
        st     = str(rec.get("status", "")).strip()
        s      = stats[ch_key]

        s["total_queue"] += 1
        if st in STATUS_PUBLISHED:
            s["published"] += 1
            url = rec.get("post_url", "")
            if url:
                s["post_urls"].append(url)
        elif st in STATUS_PENDING:
            s["pending_review"] += 1
        elif st in STATUS_APPROVED:
            s["approved"] += 1

        # 기간별 추이 — folder 필드에서 날짜 추출
        folder = rec.get("folder", "")
        m = _FOLDER_DATE_RE.search(Path(folder).name if folder else "")
        if m:
            yymmdd = m.group(1)
            yyyymm = "20" + yymmdd[:2] + "-" + yymmdd[2:4]
            if st in STATUS_PUBLISHED:
                s["trend"][yyyymm] = s["trend"].get(yyyymm, 0) + 1


# ──────────────────────────────────────────────
# 소스 2: instagram/{YYMMDD_*}/ 폴더 스캔
# ──────────────────────────────────────────────

def scan_instagram_folders(stats: dict[str, dict]) -> list[dict]:
    """instagram/ 하위 날짜 폴더를 스캔해 콘텐츠 이력 추출.
    review_queue와 중복 집계 방지를 위해 folder_count만 증가.
    """
    if not INSTAGRAM_ROOT.exists():
        print(f"[skip] instagram/ 폴더 없음: {INSTAGRAM_ROOT}")
        return []

    folders_info: list[dict] = []
    ig_stats = stats["ig"]

    for d in sorted(INSTAGRAM_ROOT.iterdir()):
        if not d.is_dir():
            continue
        m = _FOLDER_DATE_RE.match(d.name)
        if not m:
            continue  # _assets, __pycache__ 등 제외

        yymmdd = m.group(1)
        yyyymm = "20" + yymmdd[:2] + "-" + yymmdd[2:4]

        # 이미지·영상 파일 수 집계
        media_exts = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".gif", ".webp"}
        media_files = [
            f.name for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in media_exts
        ]

        # 기획_초안.md 존재 = 기획 완료 폴더
        has_draft  = (d / "기획_초안.md").exists()
        # 큐레이션 추천 md = 발행용 슬라이드 생성 완료
        has_slides = any(f.suffix == ".md" and "큐레이션" in f.name for f in d.iterdir() if f.is_file())

        folders_info.append({
            "folder": d.name,
            "yyyymm": yyyymm,
            "media_count": len(media_files),
            "has_draft": has_draft,
            "has_slides": has_slides,
        })

        ig_stats["folder_count"] += 1
        # 미디어 파일 있는 폴더 = 발행 이력으로 간주하여 추이 반영
        # (review_queue에 이미 있으면 중복이지만 trend 덮어쓰기 아닌 max 적용)
        if media_files:
            prev = ig_stats["trend"].get(yyyymm, 0)
            # review_queue가 이미 카운트한 경우 더 큰 값 유지
            ig_stats["trend"][yyyymm] = max(prev, 1)

    print(f"[ok] instagram/ 폴더 스캔: {len(folders_info)}개 (미디어 보유 기준 추이 반영)")
    return folders_info


# ──────────────────────────────────────────────
# 소스 3: status/cmo.json — 완료 태스크 이력
# ──────────────────────────────────────────────

def load_cmo_status() -> dict:
    if not CMO_STATUS_PATH.exists():
        print("[skip] status/cmo.json 없음")
        return {}
    try:
        with open(CMO_STATUS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        done_tasks = [
            t for t in data.get("active_tasks", [])
            if t.get("status") == "DONE"
        ]
        print(f"[ok] status/cmo.json 로드: 완료 태스크 {len(done_tasks)}건")
        return data
    except Exception as e:
        print(f"[warn] status/cmo.json 읽기 실패: {e}")
        return {}


# ──────────────────────────────────────────────
# 소스 4: kpi_manual.json (수동 입력)
# ──────────────────────────────────────────────

_MANUAL_TEMPLATE: dict = {
    "_desc": "litt.ly 클릭수 등 수동 입력 KPI. 값 갱신 후 cmo_kpi_collector.py 재실행.",
    "litt_ly_clicks": {
        "_desc": "litt.ly/wellperion 월별 클릭수 (수동 입력)",
        "2026-05": 0,
    },
    "naver_blog_views": {
        "_desc": "네이버 블로그 월별 조회수 (수동 입력 — v2에서 API 자동화 예정 🔒)",
        "2026-05": 0,
    },
    "naver_cafe_views": {
        "_desc": "네이버 카페 월별 조회수 (수동 입력 — v2에서 API 자동화 예정 🔒)",
        "2026-05": 0,
    },
    "ig_reach": {
        "_desc": "IG 도달수 월별 (수동 입력 — Meta Graph API 필요 🔒)",
        "2026-05": 0,
    },
    "ig_impressions": {
        "_desc": "IG 노출수 월별 (수동 입력 — Meta Graph API 필요 🔒)",
        "2026-05": 0,
    },
}


def load_or_create_manual_kpi() -> dict:
    """kpi_manual.json 로드. 없으면 템플릿으로 생성. 신규 키 누락 시 자동 보충."""
    if not KPI_MANUAL_PATH.exists():
        KPI_MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(KPI_MANUAL_PATH, "w", encoding="utf-8") as f:
            json.dump(_MANUAL_TEMPLATE, f, ensure_ascii=False, indent=2)
        print(f"[생성] kpi_manual.json 신규 생성: {KPI_MANUAL_PATH}")
        return dict(_MANUAL_TEMPLATE)

    try:
        with open(KPI_MANUAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 스키마 확장: 신규 키 없으면 보충 (기존값 유지)
        changed = False
        for key, val in _MANUAL_TEMPLATE.items():
            if key not in data:
                data[key] = val
                changed = True
        if changed:
            with open(KPI_MANUAL_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("[ok] kpi_manual.json 스키마 확장 (신규 키 보충)")
        else:
            print("[ok] kpi_manual.json 로드")
        return data
    except Exception as e:
        print(f"[warn] kpi_manual.json 읽기 실패: {e}")
        return {}


def _strip_desc(d: dict) -> dict:
    """_desc 키 제거 후 반환."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ──────────────────────────────────────────────
# 출력 JSON 빌드 & 저장
# ──────────────────────────────────────────────

def build_kpi_output(
    stats: dict[str, dict],
    folders_info: list[dict],
    manual: dict,
    cmo_status: dict,
    now_kst: datetime,
) -> dict:
    collected_at = now_kst.strftime("%Y-%m-%dT%H:%M:%S%z")

    # 채널별 stats: post_urls는 중복 제거
    clean_stats: dict[str, dict] = {}
    for key, s in stats.items():
        cs = dict(s)
        cs["post_urls"] = list(dict.fromkeys(s["post_urls"]))  # 순서 보존 중복 제거
        cs["trend"] = dict(sorted(s["trend"].items()))
        cs["channel_label"] = CHANNEL_LABELS.get(key, key)
        clean_stats[key] = cs

    # 수동 KPI 정리
    manual_kpi: dict[str, dict] = {}
    for key in ("litt_ly_clicks", "naver_blog_views", "naver_cafe_views",
                "ig_reach", "ig_impressions"):
        manual_kpi[key] = _strip_desc(manual.get(key, {}))

    # CMO 에이전트 완료 태스크 요약
    done_tasks = [
        {"task_id": t.get("task_id"), "title": t.get("title"), "artifact_url": t.get("artifact_url")}
        for t in cmo_status.get("active_tasks", [])
        if t.get("status") == "DONE"
    ]

    return {
        "_version": "v1",
        "_desc": "CMO KPI 집계 v1 — review_queue + instagram 폴더 + cmo_status + 수동 입력 병합",
        "collected_at": collected_at,
        "channels": clean_stats,
        "instagram_folders": folders_info,
        "manual_kpi": manual_kpi,
        "cmo_done_tasks": done_tasks,
        "TODO_v2": {
            "ig_insights":      "Meta Graph API — IG 도달수·좋아요·저장 (토큰 필요 🔒, GM 결재 필요)",
            "naver_blog_stats": "네이버 블로그 통계 API — 조회수·유입 (토큰/쿠키 필요 🔒)",
            "naver_cafe_stats": "네이버 카페 통계 API — 조회수·댓글 (토큰 필요 🔒)",
        },
    }


def save_kpi(output: dict) -> None:
    KPI_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KPI_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[저장] {KPI_OUTPUT_PATH}")


# ──────────────────────────────────────────────
# HTML 리포트 생성
# ──────────────────────────────────────────────

def _trend_bars(trend: dict[str, int]) -> str:
    """월별 추이 → 간단한 텍스트 바 차트 HTML."""
    if not trend:
        return "<span class='muted'>데이터 없음</span>"
    max_v = max(trend.values()) or 1
    rows = []
    for ym, v in sorted(trend.items()):
        pct = int(v / max_v * 100)
        rows.append(
            f"<div class='bar-row'>"
            f"<span class='bar-label'>{ym}</span>"
            f"<div class='bar-wrap'><div class='bar-fill' style='width:{pct}%'></div></div>"
            f"<span class='bar-val'>{v}</span>"
            f"</div>"
        )
    return "".join(rows)


def _manual_table(manual_kpi: dict) -> str:
    _labels = {
        "litt_ly_clicks":   "litt.ly 클릭수",
        "naver_blog_views": "네이버 블로그 조회수",
        "naver_cafe_views": "네이버 카페 조회수",
        "ig_reach":         "IG 도달수 🔒",
        "ig_impressions":   "IG 노출수 🔒",
    }
    rows = []
    for key, label in _labels.items():
        months = manual_kpi.get(key, {})
        if not months:
            rows.append(f"<tr><td>{label}</td><td>—</td><td>—</td></tr>")
            continue
        for ym, v in sorted(months.items()):
            rows.append(f"<tr><td>{label}</td><td>{ym}</td><td class='num'>{v:,}</td></tr>")
    return "".join(rows)


def build_html_report(output: dict, now_kst: datetime) -> str:
    collected_at = now_kst.strftime("%Y년 %m월 %d일 %H:%M:%S")
    channels = output.get("channels", {})

    # 채널별 카드 HTML
    channel_cards = []
    for ch_key, s in channels.items():
        label    = s.get("channel_label", ch_key)
        pub      = s.get("published", 0)
        pend     = s.get("pending_review", 0)
        appr     = s.get("approved", 0)
        total_q  = s.get("total_queue", 0)
        folders  = s.get("folder_count", 0)
        trend_html = _trend_bars(s.get("trend", {}))
        urls_html  = ""
        for url in s.get("post_urls", []):
            urls_html += f"<a href='{url}' class='post-link' target='_blank'>{url}</a><br>"

        channel_cards.append(f"""
        <div class="card">
          <div class="card-title">{label}</div>
          <div class="stat-row">
            <div class="stat-box published"><div class="stat-num">{pub}</div><div class="stat-lbl">발행완료</div></div>
            <div class="stat-box pending"><div class="stat-num">{pend}</div><div class="stat-lbl">검수대기</div></div>
            <div class="stat-box approved"><div class="stat-num">{appr}</div><div class="stat-lbl">승인</div></div>
            <div class="stat-box total"><div class="stat-num">{total_q}</div><div class="stat-lbl">큐 전체</div></div>
            <div class="stat-box folders"><div class="stat-num">{folders}</div><div class="stat-lbl">콘텐츠폴더</div></div>
          </div>
          <div class="section-title">기간별 발행 추이</div>
          <div class="trend-chart">{trend_html}</div>
          {'<div class="section-title">발행 URL</div>' + urls_html if urls_html else ""}
        </div>""")

    channel_cards_html = "\n".join(channel_cards) if channel_cards else "<p class='muted'>채널 데이터 없음</p>"

    # 수동 KPI 테이블
    manual_rows = _manual_table(output.get("manual_kpi", {}))

    # 완료 태스크 목록
    done_tasks = output.get("cmo_done_tasks", [])
    task_rows = ""
    for t in done_tasks:
        tid  = t.get("task_id", "—")
        ttl  = t.get("title", "—")
        aurl = t.get("artifact_url") or ""
        link = f"<a href='{aurl}' target='_blank'>링크</a>" if aurl else "—"
        task_rows += f"<tr><td class='mono'>{tid}</td><td>{ttl}</td><td>{link}</td></tr>"

    # TODO v2 목록
    todo_items = "".join(
        f"<li><code>{k}</code>: {v}</li>"
        for k, v in output.get("TODO_v2", {}).items()
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CMO KPI 리포트 — 웰페리온</title>
<style>
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e2e8f0;
    --muted: #64748b;
    --accent: #6366f1;
    --green: #22c55e;
    --yellow: #f59e0b;
    --blue: #3b82f6;
    --gray: #475569;
    --red: #ef4444;
    --font: 'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; line-height: 1.6; padding: 24px; }}
  h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 28px; }}
  .section {{ margin-bottom: 32px; }}
  .section-header {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 16px; }}
  .card-title {{ font-size: 15px; font-weight: 700; margin-bottom: 14px; color: var(--accent); }}
  .stat-row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }}
  .stat-box {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; min-width: 80px; text-align: center; }}
  .stat-box.published {{ border-color: var(--green); }}
  .stat-box.pending {{ border-color: var(--yellow); }}
  .stat-box.approved {{ border-color: var(--blue); }}
  .stat-box.total {{ border-color: var(--gray); }}
  .stat-box.folders {{ border-color: var(--accent); }}
  .stat-num {{ font-size: 24px; font-weight: 800; line-height: 1.2; }}
  .stat-box.published .stat-num {{ color: var(--green); }}
  .stat-box.pending .stat-num {{ color: var(--yellow); }}
  .stat-box.approved .stat-num {{ color: var(--blue); }}
  .stat-box.total .stat-num {{ color: var(--gray); }}
  .stat-box.folders .stat-num {{ color: var(--accent); }}
  .stat-lbl {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}
  .section-title {{ font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin: 12px 0 8px; }}
  .trend-chart {{ display: flex; flex-direction: column; gap: 5px; }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; }}
  .bar-label {{ font-size: 12px; color: var(--muted); min-width: 60px; }}
  .bar-wrap {{ flex: 1; background: var(--border); border-radius: 3px; height: 10px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }}
  .bar-val {{ font-size: 12px; color: var(--text); min-width: 20px; text-align: right; }}
  .post-link {{ color: var(--accent); font-size: 12px; word-break: break-all; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: var(--surface); color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .mono {{ font-family: monospace; font-size: 12px; color: var(--muted); }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .muted {{ color: var(--muted); }}
  .todo-list {{ list-style: none; padding: 0; }}
  .todo-list li {{ padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; color: var(--muted); }}
  .todo-list li:last-child {{ border-bottom: none; }}
  code {{ background: var(--border); padding: 1px 5px; border-radius: 3px; font-family: monospace; font-size: 12px; }}
  .badge-lock {{ background: #7c3aed22; color: #a78bfa; border: 1px solid #7c3aed44; padding: 1px 6px; border-radius: 4px; font-size: 11px; }}
  footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<h1>CMO KPI 리포트</h1>
<div class="subtitle">웰페리온 마케팅 채널별 집계 | 집계일시: {collected_at} | v1</div>

<div class="section">
  <div class="section-header">채널별 발행 현황</div>
  {channel_cards_html}
</div>

<div class="section">
  <div class="section-header">수동 입력 KPI <span class="badge-lock">🔒 일부 항목 토큰 필요</span></div>
  <div class="card">
    <table>
      <thead><tr><th>항목</th><th>기간</th><th class="num">수치</th></tr></thead>
      <tbody>{manual_rows if manual_rows else "<tr><td colspan='3' class='muted'>수동 입력값 없음</td></tr>"}</tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-header">CMO 완료 태스크</div>
  <div class="card">
    <table>
      <thead><tr><th>태스크 ID</th><th>제목</th><th>산출물</th></tr></thead>
      <tbody>{task_rows if task_rows else "<tr><td colspan='3' class='muted'>완료 태스크 없음</td></tr>"}</tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-header">TODO v2 <span class="badge-lock">🔒 GM 결재 필요</span></div>
  <div class="card">
    <ul class="todo-list">{todo_items}</ul>
  </div>
</div>

<footer>
  웰페리온 CMO KPI 리포트 v1 | 외부 API 호출 없음 | 소스: review_queue.json + instagram/ 폴더 + status/cmo.json + kpi_manual.json
</footer>
</body>
</html>"""


def save_html_report(html: str) -> None:
    KPI_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KPI_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[저장] {KPI_REPORT_PATH}")


# ──────────────────────────────────────────────
# 콘솔 출력 안전 헬퍼
# ──────────────────────────────────────────────

def _safe(text: str) -> str:
    """cp949 인코딩 불가 문자를 '?' 로 치환해 콘솔 출력 오류 방지."""
    return text.encode("cp949", errors="replace").decode("cp949")


# ──────────────────────────────────────────────
# 콘솔 요약표
# ──────────────────────────────────────────────

def print_summary(output: dict) -> None:
    print("\n" + "=" * 70)
    print("  CMO KPI 집계 요약표 v1")
    print(f"  집계일시: {output['collected_at']}")
    print("=" * 70)

    channels = output.get("channels", {})
    if channels:
        print(f"  {'채널':<24} {'발행':>4} {'검수대기':>6} {'승인':>4} {'큐전체':>5} {'폴더':>4}")
        print("  " + "-" * 52)
        for ch_key, s in channels.items():
            label = s.get("channel_label", ch_key)
            label = label[:22] if len(label) > 22 else label
            print(
                f"  {label:<24} {s['published']:>4} {s['pending_review']:>6}"
                f" {s['approved']:>4} {s['total_queue']:>5} {s['folder_count']:>4}"
            )
            trend = s.get("trend", {})
            if trend:
                trend_str = "  ".join(f"{ym}={v}" for ym, v in sorted(trend.items()))
                print(f"    추이: {trend_str}")
    else:
        print("  채널 데이터 없음 (review_queue.json 확인 필요)")

    print()
    manual = output.get("manual_kpi", {})
    _lbl = {
        "litt_ly_clicks":   "litt.ly 클릭수",
        "naver_blog_views": "네이버 블로그 조회수",
        "naver_cafe_views": "네이버 카페 조회수",
        "ig_reach":         "IG 도달수",
        "ig_impressions":   "IG 노출수",
    }
    has_manual = any(manual.get(k) for k in _lbl)
    if has_manual:
        print("  [수동 입력 KPI]")
        for key, lbl in _lbl.items():
            months = manual.get(key, {})
            for ym, v in sorted(months.items()):
                print(f"    {lbl:<20} {ym}: {v:,}")

    done = output.get("cmo_done_tasks", [])
    if done:
        print(f"\n  [CMO 완료 태스크: {len(done)}건]")
        for t in done:
            print(_safe(f"    {t.get('task_id','N/A')}: {t.get('title','')[:40]}"))

    print()
    print("  [TODO v2 - GM 결재 후]")
    for k, v in output.get("TODO_v2", {}).items():
        print(_safe(f"    {k}: {v[:60]}"))
    print("=" * 70)
    print(_safe(f"  리포트: {KPI_REPORT_PATH}"))
    print("=" * 70)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main() -> None:
    print("CMO KPI 집계기 v1 시작\n")

    now_kst = datetime.now(timezone.utc).astimezone()

    # 채널별 stats 초기화 (4채널)
    stats: dict[str, dict] = {k: _empty_channel_stats() for k in CHANNEL_LABELS}

    # 소스 1: review_queue
    records = load_review_queue()
    aggregate_review_queue(records, stats)

    # 소스 2: instagram/ 폴더 스캔
    folders_info = scan_instagram_folders(stats)

    # 소스 3: status/cmo.json
    cmo_status = load_cmo_status()

    # 소스 4: 수동 입력
    manual = load_or_create_manual_kpi()

    # JSON 빌드 & 저장
    output = build_kpi_output(stats, folders_info, manual, cmo_status, now_kst)
    save_kpi(output)

    # HTML 리포트 생성
    html = build_html_report(output, now_kst)
    save_html_report(html)

    # 콘솔 요약
    print_summary(output)

    print("\n완료.")


if __name__ == "__main__":
    main()
