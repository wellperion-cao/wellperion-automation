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

KST = timezone(timedelta(hours=9))

GRAPH_API_BASE = "https://graph.instagram.com"
GRAPH_API_VERSION = "v21.0"  # 미검증 — 실전 호출 시 최신 버전 재확인

ACCOUNT_METRIC = "reach"  # 계정 일별 도달. impressions는 media-level에서만 시도(§ 메트릭명 주석 참조)
MEDIA_METRICS = "reach,impressions"  # 미검증 — impressions는 일부 버전에서 deprecated 이력 있음


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
    url = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}/{business_id}/insights"
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
    url = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}/{business_id}/media"
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
    url = f"{GRAPH_API_BASE}/{GRAPH_API_VERSION}/{media_id}/insights"
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
    args = parser.parse_args()

    print(f"=== IG 노출·도달 수집 [{now_kst()}] (배#546) ===")

    token, business_id = _get_credentials()
    if not token or not business_id:
        print("BLOCKED: IG_ACCESS_TOKEN 또는 IG_BUSINESS_ID 미설정 — GM 배치 인증 세션 전. 부작용 없음, 종료.")
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

    update_ledger(account_result, media_results, dry_run=args.dry_run)
    print(f"DONE: 계정 도달 1건 + 게시물 {len(media_results)}건 수집 → {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
