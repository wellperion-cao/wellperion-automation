"""웰페리온 CMO KPI 집계기 v0
채널별 KPI를 한 곳에 집계하는 골격 스크립트.
외부 API 토큰 없이 동작하는 v0.

입력 소스:
  1. 3. 웰페리온 가이드/cmo/review/review_queue.json  — 발행완료 건수·채널별
  2. status/kpi_manual.json                           — litt.ly 클릭수 등 수동 입력 (없으면 생성)
  3. apps_script cmo_summary 액션 (URL 있으면 호출, 없으면 skip)

출력:
  status/cmo_kpi.json  — 채널별 발행수·검수대기·승인·수동 클릭수·집계일시
  콘솔 요약표

TODO (v1 이상, GM 결재 후):
  - IG Insights (Meta Graph API) — 토큰 필요
  - 네이버 블로그 통계 — 토큰/쿠키 필요
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ──────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(r"C:\Users\jjky0\welperion-automation")

REVIEW_QUEUE_PATH = PROJECT_ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
KPI_MANUAL_PATH   = PROJECT_ROOT / "status" / "kpi_manual.json"
KPI_OUTPUT_PATH   = PROJECT_ROOT / "status" / "cmo_kpi.json"

# apps_script URL (설정되어 있으면 호출, 없으면 skip)
APPS_SCRIPT_URL: str | None = None  # 예: "https://script.google.com/macros/s/.../exec?action=cmo_summary"


# ──────────────────────────────────────────────
# 소스 1: review_queue.json 파싱
# ──────────────────────────────────────────────

def load_review_queue() -> list[dict]:
    """review_queue.json 로드. 없으면 빈 리스트."""
    if not REVIEW_QUEUE_PATH.exists():
        print(f"[skip] review_queue.json 없음: {REVIEW_QUEUE_PATH}")
        return []
    try:
        with open(REVIEW_QUEUE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[ok] review_queue.json 로드: {len(data)}건")
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[warn] review_queue.json 파싱 실패 ({e}), 인코딩 폴백 시도")
        # cp949 폴백 (한글 Windows 저장 파일 대응)
        try:
            with open(REVIEW_QUEUE_PATH, "r", encoding="cp949") as f:
                data = json.load(f)
            print(f"[ok] review_queue.json (cp949) 로드: {len(data)}건")
            return data if isinstance(data, list) else []
        except Exception as e2:
            print(f"[warn] review_queue.json 읽기 실패: {e2}")
            return []


def aggregate_review_queue(records: list[dict]) -> dict[str, dict]:
    """채널별 발행수·검수대기·승인 집계."""
    channel_stats: dict[str, dict] = defaultdict(lambda: {
        "published": 0,
        "pending_review": 0,
        "approved": 0,
        "total": 0,
    })

    # 상태값 정규화 맵 (한글 깨짐 포함 대응 — 실제 값은 원본 JSON 인코딩에 따라 다를 수 있음)
    STATUS_PUBLISHED    = {"발행완료", "게시완료", "완료"}
    STATUS_PENDING      = {"검수대기", "검토중", "대기"}
    STATUS_APPROVED     = {"승인", "검수완료", "approved"}

    for rec in records:
        channel = rec.get("channel", "미분류")
        # 채널명이 깨진 경우 "미분류"로 처리
        if not isinstance(channel, str) or len(channel) > 80:
            channel = "미분류"

        status = str(rec.get("status", "")).strip()
        stats = channel_stats[channel]
        stats["total"] += 1

        if status in STATUS_PUBLISHED:
            stats["published"] += 1
        elif status in STATUS_PENDING:
            stats["pending_review"] += 1
        elif status in STATUS_APPROVED:
            stats["approved"] += 1
        # 그 외 상태는 total만 카운트

    return dict(channel_stats)


# ──────────────────────────────────────────────
# 소스 2: kpi_manual.json (수동 입력)
# ──────────────────────────────────────────────

MANUAL_TEMPLATE = {
    "_desc": "litt.ly 클릭수 등 수동 입력 KPI. 값 갱신 후 cmo_kpi_collector.py 재실행.",
    "litt_ly_clicks": {
        "_desc": "litt.ly/wellperion 월별 클릭수 (수동 입력)",
        "2026-05": 0
    },
    "naver_blog_views": {
        "_desc": "네이버 블로그 월별 조회수 (수동 입력, v1에서 자동화 예정)",
        "2026-05": 0
    },
    "naver_cafe_views": {
        "_desc": "네이버 카페 월별 조회수 (수동 입력)",
        "2026-05": 0
    }
}


def load_or_create_manual_kpi() -> dict:
    """kpi_manual.json 로드. 없으면 템플릿으로 생성."""
    if not KPI_MANUAL_PATH.exists():
        KPI_MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(KPI_MANUAL_PATH, "w", encoding="utf-8") as f:
            json.dump(MANUAL_TEMPLATE, f, ensure_ascii=False, indent=2)
        print(f"[생성] kpi_manual.json 신규 생성: {KPI_MANUAL_PATH}")
    try:
        with open(KPI_MANUAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[ok] kpi_manual.json 로드")
        return data
    except Exception as e:
        print(f"[warn] kpi_manual.json 읽기 실패: {e}")
        return {}


# ──────────────────────────────────────────────
# 소스 3: apps_script cmo_summary (선택)
# ──────────────────────────────────────────────

def fetch_apps_script_summary() -> dict | None:
    """apps_script URL이 설정된 경우에만 호출. 없으면 None 반환."""
    if not APPS_SCRIPT_URL:
        print("[skip] apps_script URL 미설정 - skip")
        return None

    try:
        import urllib.request
        with urllib.request.urlopen(APPS_SCRIPT_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"[ok] apps_script cmo_summary 호출 성공")
        return data
    except Exception as e:
        print(f"[warn] apps_script 호출 실패: {e}")
        return None


# ──────────────────────────────────────────────
# 출력 빌드 & 저장
# ──────────────────────────────────────────────

def build_kpi_output(
    channel_stats: dict[str, dict],
    manual: dict,
    apps_script_data: dict | None,
) -> dict:
    """최종 cmo_kpi.json 구조 빌드."""
    now_kst = datetime.now(timezone.utc).astimezone()
    collected_at = now_kst.strftime("%Y-%m-%dT%H:%M:%S%z")

    # 수동 KPI 정리
    litt_ly_clicks  = manual.get("litt_ly_clicks",  {})
    naver_blog      = manual.get("naver_blog_views", {})
    naver_cafe      = manual.get("naver_cafe_views", {})

    output = {
        "_version": "v0",
        "_desc": "CMO KPI 집계 (v0 — 외부 API 없음, 수동 입력+review_queue 기반)",
        "collected_at": collected_at,
        "channels": channel_stats,
        "manual_kpi": {
            "litt_ly_clicks":    {k: v for k, v in litt_ly_clicks.items() if not k.startswith("_")},
            "naver_blog_views":  {k: v for k, v in naver_blog.items()     if not k.startswith("_")},
            "naver_cafe_views":  {k: v for k, v in naver_cafe.items()     if not k.startswith("_")},
        },
        "apps_script_summary": apps_script_data,
        "TODO_v1": {
            "ig_insights":      "Meta Graph API — IG 도달수·좋아요·저장 (GM 결재 필요, 토큰 미발급)",
            "naver_blog_stats": "네이버 블로그 통계 API — 조회수·유입 (GM 결재 필요)",
        },
    }
    return output


def save_kpi(output: dict) -> None:
    KPI_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KPI_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[저장] {KPI_OUTPUT_PATH}")


# ──────────────────────────────────────────────
# 콘솔 요약표
# ──────────────────────────────────────────────

def print_summary(output: dict) -> None:
    print("\n" + "=" * 56)
    print("  CMO KPI 집계 요약표")
    print(f"  집계일시: {output['collected_at']}")
    print("=" * 56)

    channels = output.get("channels", {})
    if channels:
        print(f"  {'채널':<30} {'발행':>4} {'검수대기':>6} {'승인':>4} {'전체':>4}")
        print("  " + "-" * 52)
        for ch, st in channels.items():
            label = ch[:28] if len(ch) > 28 else ch
            print(f"  {label:<30} {st['published']:>4} {st['pending_review']:>6} {st['approved']:>4} {st['total']:>4}")
    else:
        print("  채널 데이터 없음 (review_queue.json 확인 필요)")

    print()
    manual = output.get("manual_kpi", {})
    litt = manual.get("litt_ly_clicks", {})
    blog = manual.get("naver_blog_views", {})
    cafe = manual.get("naver_cafe_views", {})
    if litt or blog or cafe:
        print("  [수동 입력 KPI]")
        for ym, v in litt.items():
            print(f"    litt.ly 클릭수  {ym}: {v:,}")
        for ym, v in blog.items():
            print(f"    네이버 블로그   {ym}: {v:,}")
        for ym, v in cafe.items():
            print(f"    네이버 카페     {ym}: {v:,}")

    print()
    print("  [v1 예정 - GM 결재 후]")
    for k, v in output.get("TODO_v1", {}).items():
        print(f"    {k}: {v}")
    print("=" * 56)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main() -> None:
    print("CMO KPI 집계기 v0 시작\n")

    # 소스 1
    records = load_review_queue()
    channel_stats = aggregate_review_queue(records)

    # 소스 2
    manual = load_or_create_manual_kpi()

    # 소스 3
    apps_data = fetch_apps_script_summary()

    # 빌드 & 저장
    output = build_kpi_output(channel_stats, manual, apps_data)
    save_kpi(output)

    # 콘솔 요약
    print_summary(output)

    print("\n완료.")


if __name__ == "__main__":
    main()
