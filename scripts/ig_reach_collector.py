# scripts/ig_reach_collector.py
# 배#546 — @wellperion IG 노출·도달(reach/impressions) 수집기 골격
#
# ⚠️ 미검증(2026-07-07 작성) — 라이브 API 호출 0회로 작성됨. GM 배치 인증(러너북:
# status/briefs/CMO-2026-07-07-IMPRESSION-SETUP-RUNBOOK.md) 완료 전까지 이 스크립트는
# 절대 실제 호출을 하지 않는다(토큰 없으면 BLOCKED 로그만 남기고 즉시 종료, 부작용 0).
# 엔드포인트·메트릭 이름은 Meta 공식 문서 기반 추정 — 실전 첫 호출 시 최신 문서로 재확인 필수
# (Graph API는 버전마다 impressions/reach/views 가용성이 바뀌는 이력이 있음).
#
# 인증: Instagram API with Instagram Login (2024경로) — FB 페이지 매개 불필요, 자기계정 전용.
# 필요 env (scripts/.env, 없으면 신규 추가 — 기존 META_* 4종은 용도·유효성 불명이라 재사용 안 함):
#   IG_ACCESS_TOKEN   장기 사용자 토큰(60일, GM OAuth 동의 후 발급)
#   IG_BUSINESS_ID    @wellperion IG 사용자 ID
#
# 사용법(토큰 준비된 후):
#   python scripts/ig_reach_collector.py             # 계정 일별 도달 + 최근 게시물 노출·도달
#   python scripts/ig_reach_collector.py --dry-run    # 파일 저장 없이 결과만 출력
#
# 출력: status/ig_reach_ledger.json (account_reach_series + media_snapshots, 멱등 upsert)
#       3. 웰페리온 가이드/cmo/funnel/ig_reach_summary.json (Pages 서빙 경로 요약 — 대시보드 fetch용, 배#546)
#
# 요약 JSON만 재생성(네트워크 호출 0회): python scripts/ig_reach_collector.py --summary-only

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import requests
except ImportError:
    requests = None

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "scripts" / ".env"
LEDGER_PATH = ROOT / "status" / "ig_reach_ledger.json"
# Pages는 "3. 웰페리온 가이드/**"·"ssot/**"만 서빙(status/는 미서빙) → 대시보드가 fetch할 요약본을
# Pages 서빙 경로에 별도 발행. 정본(SSOT)은 위 LEDGER_PATH — 이 파일은 파생 요약(재생성 가능).
SUMMARY_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "funnel" / "ig_reach_summary.json"
ACCOUNT_RECENT_N = 14  # 대시보드에 넘기는 최근 계정 일별 도달 개수(전체 이력 아님)
MEDIA_TOP_N = 5        # 게시물 도달 상위 N(최신 스냅샷 기준 reach 내림차순)

KST = timezone(timedelta(hours=9))

GRAPH_API_BASE = "https://graph.instagram.com"  # 2026-07-07 라이브 검증: 버전 접두사 없이 호출

ACCOUNT_METRIC = "reach"  # 계정 일별 도달 — 라이브 검증됨(7/5=34·7/6=17)
# 2026-07-07 라이브 검증: media impressions는 CAROUSEL 등에서 미지원("does not support the impressions
# metric for this media product type") → reach만 사용(안정). views는 지원되나 유형별 편차 있어 v1 제외.
MEDIA_METRICS = "reach"


def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _load_ledger() -> dict:
    if LEDGER_PATH.exists():
        try:
            return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"account_reach_series": [], "media_snapshots": [], "note": "ig_reach_collector.py 자동 생성 — 미검증 골격(배#546)"}


def _save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def build_summary(ledger: dict) -> dict:
    """ledger(SSOT) → Pages 서빙용 요약. 정직 원칙: 계정 도달은 합산하지 않고 일별 그대로 넘긴다
    (여러 날을 더하면 동일인 중복집계 — '고유 도달'이 아니게 됨). 게시물은 최신 스냅샷 reach 상위 N만."""
    account_series = sorted(
        (r for r in ledger.get("account_reach_series", []) if r.get("date")),
        key=lambda r: r["date"],
    )
    account_recent = account_series[-ACCOUNT_RECENT_N:]
    latest_account = account_recent[-1] if account_recent else None

    media_latest = []
    for m in ledger.get("media_snapshots", []):
        snaps = [s for s in (m.get("snapshots") or []) if s.get("date")]
        if not snaps:
            continue
        last = sorted(snaps, key=lambda s: s["date"])[-1]
        media_latest.append({
            "media_id": m.get("media_id"),
            "permalink": m.get("permalink"),
            "reach": last.get("reach"),
            "impressions": last.get("impressions"),
            "date": last.get("date"),
        })
    media_latest.sort(key=lambda x: (x.get("reach") or 0), reverse=True)

    return {
        "channel": "인스타그램",
        "updated_at": now_kst(),
        "latest_account_reach": latest_account,
        "account_reach_recent": account_recent,
        "media_reach_top": media_latest[:MEDIA_TOP_N],
        "media_tracked_count": len(media_latest),
        "note": (
            "계정 도달=일별 스냅샷(기간 합산 시 동일인 중복 집계 — '고유 도달' 아님, 최근 값만 표시) · "
            "게시물 도달=Graph API reach(고유 도달 근사) · impressions는 게시물 유형 제약으로 수집 제외"
            "(2026-07-07 라이브 검증, reach만) · ig_reach_collector.py 자동 생성(배#546)"
        ),
    }


def _save_summary(summary: dict) -> None:
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_credentials():
    """env에서 토큰·계정ID 로드. 하나라도 없으면 (None, None) 반환 — 호출부가 BLOCKED 처리."""
    if load_dotenv is not None and ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    token = os.getenv("IG_ACCESS_TOKEN")
    business_id = os.getenv("IG_BUSINESS_ID")
    if not token or not business_id:
        return None, None
    return token, business_id


def fetch_account_reach(token: str, business_id: str) -> dict | None:
    """계정 일별 도달 조회. 실전 호출 전 최신 Graph API 문서로 metric/period 파라미터 재확인 필요(미검증)."""
    if requests is None:
        print("[BLOCKED] requests 라이브러리 미설치 — 호출 불가")
        return None
    url = f"{GRAPH_API_BASE}/{business_id}/insights"
    params = {
        "metric": ACCOUNT_METRIC,
        "period": "day",
        "access_token": token,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_recent_media(token: str, business_id: str, limit: int = 10) -> list[dict]:
    """최근 게시물 목록(id·permalink·timestamp)만 조회 — 노출·도달은 미디어별로 별도 호출."""
    if requests is None:
        return []
    url = f"{GRAPH_API_BASE}/{business_id}/media"
    params = {
        "fields": "id,permalink,timestamp",
        "limit": limit,
        "access_token": token,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", [])


def fetch_media_insights(token: str, media_id: str) -> dict | None:
    """게시물 단위 노출·도달. impressions 메트릭 가용성은 API 버전·게시물 유형에 따라 다름(미검증)."""
    if requests is None:
        return None
    url = f"{GRAPH_API_BASE}/{media_id}/insights"
    params = {
        "metric": MEDIA_METRICS,
        "access_token": token,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _extract_metric_value(insights_json: dict, metric_name: str):
    """Graph API insights 응답({"data":[{"name":..,"values":[{"value":N}]}]})에서 값 추출.
    미검증 — 실전 응답 구조 확인 후 필요 시 조정."""
    if not insights_json:
        return None
    for item in insights_json.get("data", []):
        if item.get("name") == metric_name:
            values = item.get("values") or []
            if values:
                return values[-1].get("value")
    return None


def update_ledger(account_result: dict | None, media_results: list[dict], dry_run: bool = False) -> dict:
    ledger = _load_ledger()
    ledger.setdefault("account_reach_series", [])
    ledger.setdefault("media_snapshots", [])
    today = datetime.now(KST).strftime("%Y-%m-%d")

    if account_result is not None:
        reach_val = _extract_metric_value(account_result, ACCOUNT_METRIC)
        existing = next((r for r in ledger["account_reach_series"] if r.get("date") == today), None)
        if existing:
            existing["reach"] = reach_val
        else:
            ledger["account_reach_series"].append({"date": today, "reach": reach_val})

    for media_id, permalink, insights in media_results:
        reach_val = _extract_metric_value(insights, "reach")
        impressions_val = _extract_metric_value(insights, "impressions")
        entry = next((m for m in ledger["media_snapshots"] if m.get("media_id") == media_id), None)
        if not entry:
            entry = {"media_id": media_id, "permalink": permalink, "first_seen": today, "snapshots": []}
            ledger["media_snapshots"].append(entry)
        snap = {"date": today, "reach": reach_val, "impressions": impressions_val}
        existing_snap = next((s for s in entry["snapshots"] if s.get("date") == today), None)
        if existing_snap:
            existing_snap.update(snap)
        else:
            entry["snapshots"].append(snap)

    if not dry_run:
        _save_ledger(ledger)
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="@wellperion IG 노출·도달 수집기 (배#546, 미검증 골격)")
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 없이 결과만 출력")
    parser.add_argument("--summary-only", action="store_true", help="네트워크 호출 없이 기존 ledger로 요약 JSON만 재생성")
    args = parser.parse_args()

    print(f"=== IG 노출·도달 수집 [{now_kst()}] (배#546) ===")

    if args.summary_only:
        summary = build_summary(_load_ledger())
        _save_summary(summary)
        print(f"DONE: 네트워크 호출 없음 — 기존 ledger로 요약만 재생성 → {SUMMARY_PATH}")
        return 0

    token, business_id = _get_credentials()
    if not token or not business_id:
        _save_summary(build_summary(_load_ledger()))
        print("BLOCKED: IG_ACCESS_TOKEN 또는 IG_BUSINESS_ID 미설정 — GM 배치 인증 세션 전. 외부 API 호출 없음(기존 ledger로 요약만 갱신 후 종료).")
        return 0

    # 여기부터는 토큰 존재 시 실행되는 경로 — 배#546 준비 단계(현재 실행)에서는
    # env에 토큰이 없어 도달하지 않음. GM 인증 완료 후 첫 실행 시 실전 검증 필요.
    try:
        account_result = fetch_account_reach(token, business_id)
    except Exception as e:
        print(f"BLOCKED: 계정 도달 조회 실패 — {e}")
        return 0

    media_results = []
    try:
        for media in fetch_recent_media(token, business_id):
            media_id = media.get("id")
            permalink = media.get("permalink")
            try:
                insights = fetch_media_insights(token, media_id)
            except Exception as e:
                print(f"  [WARN] 게시물 {media_id} 인사이트 실패: {e}")
                continue
            media_results.append((media_id, permalink, insights))
    except Exception as e:
        print(f"BLOCKED: 게시물 목록 조회 실패 — {e}")

    ledger = update_ledger(account_result, media_results, dry_run=args.dry_run)
    if not args.dry_run:
        _save_summary(build_summary(ledger))
    print(f"DONE: 계정 도달 1건 + 게시물 {len(media_results)}건 수집 → {LEDGER_PATH} (요약 → {SUMMARY_PATH})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
