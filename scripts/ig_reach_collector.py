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


# 1회 실행 시간 상한 — 크롤이 길어져도 본 수집 작업을 붙잡지 않는다. 미처리분은 다음 회차로.
RECONCILE_MAX_SECONDS = 480      # 회수기 내부 상한(이 시간 넘으면 스스로 남은 건 이월 후 정상 저장)
RECONCILE_HARD_TIMEOUT = 600     # 프로세스 강제 종료 백스톱(내부 상한이 안 먹을 때만 발동)


def _run_reconcile_published() -> None:
    """scripts/reconcile_published.py 를 별도 프로세스로 1회 실행(읽기 크롤 → URL 백필).

    별도 프로세스인 이유: 회수기는 Playwright 비동기 크롤을 쓴다 — 같은 프로세스에 올리면
    이 수집기의 종료·예외 처리에 얽힌다. 실패·타임아웃은 전부 삼키고 본 작업(도달 수집)에
    영향 0. 결과 1줄 기록은 회수기 자신이 worklog 로 남긴다.
    """
    import subprocess  # noqa: PLC0415 — best-effort 경로에서만 필요

    script = ROOT / "scripts" / "reconcile_published.py"
    if not script.exists():
        print("[WARN] reconcile_published.py 미존재 — 발행 주소 회수 건너뜀")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--max-seconds", str(RECONCILE_MAX_SECONDS)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=RECONCILE_HARD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN] 발행 주소 회수 {RECONCILE_HARD_TIMEOUT}초 초과 — 강제 종료(다음 회차 재시도)")
        return
    tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()][-3:]
    for ln in tail:
        print(f"  [회수] {ln}")
    if proc.returncode != 0:
        print(f"[WARN] 발행 주소 회수 종료코드 {proc.returncode}(무해 — 다음 회차 재시도)")


PUBLISH_AUDIT_MAX_SECONDS = 240  # 감사기 HTTP 실측 상한 — 넘으면 남은 건 다음 회차로


def _run_publish_status_audit() -> None:
    """scripts/publish_status_audit.py 를 1회 실행(읽기 전용 감사 → 상태파일·worklog 기록).

    2026-07-23: 이 감사기는 GM 이 '발행 안 했는데 발행완료로 보고' 재발방지로 만들게 한 것인데
    어느 주기 실행에도 안 붙어 한 번도 안 돌았다. 위 회수기와 같은 방식의 best-effort 편승 —
    신규 예약작업 없음. 발행·삭제·텔레그램 발송 0(감사기는 큐를 읽기만 한다).
    """
    import publish_status_audit  # noqa: PLC0415 — best-effort 경로에서만 필요

    res = publish_status_audit.audit_and_record(
        check_http=True, max_seconds=PUBLISH_AUDIT_MAX_SECONDS)
    n = len(res.get("suspects", []))
    print(f"  [감사] 발행완료 과대보고 의심 {n}건 — status/publish_audit_state.json 기록"
          + (" (빠진 것 화면에 표면화)" if n else " · 깨끗"))


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

    try:
        return _collect_reach(args)
    finally:
        # 발행 주소 자동 회수 대조 편승(2026-07-23 배9578 — 회수기 reconcile_published.py 는
        # 만들어져 있는데 어느 자동 실행 경로에도 안 붙어 '발행완료인데 주소 없음' 48건이 쌓였다).
        # 위 반응 성적표와 같은 방식의 best-effort 편승 — 신규 예약작업·신규 스케줄러 없음.
        # ★finally 인 이유: 위 수집이 토큰 만료(60일)로 BLOCKED 되어 조기 return 해도 회수는 돌아야 한다
        #   (그렇지 않으면 '붙여놨는데 안 도는' 같은 고장을 반복한다).
        if not args.dry_run:
            try:
                _run_reconcile_published()
            except Exception as e:
                print(f"[WARN] 발행 주소 회수 대조 연계 실패(IG 도달 수집 자체는 완료): {e}")
            # 회수 '뒤'에 감사 — 방금 백필된 주소가 감사 결과에 반영되도록 순서를 지킨다.
            try:
                _run_publish_status_audit()
            except Exception as e:
                print(f"[WARN] 발행완료 과대보고 감사 연계 실패(IG 도달 수집 자체는 완료): {e}")


def _collect_reach(args) -> int:
    """IG 도달·노출 수집 본체 — 토큰 없으면 BLOCKED 로그만 남기고 종료(부작용 0)."""
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

    # 반응 성적표 스캔 연계(2026-07-20 배834 — 발행 루프를 감싸는 상위 루프: 반응 파악→개선제안).
    # 신규 예약작업 미생성 — 매일 09:45 이 수집 직후(방금 갱신한 도달 데이터가 곧바로 반영되도록)
    # best-effort 편승. 실패해도 위 도달 수집 자체는 이미 완료된 상태이므로 종료코드에 영향 없음.
    if not args.dry_run:
        try:
            import reaction_scorecard
            reaction_scorecard.scan_and_alert()
        except Exception as e:
            print(f"[WARN] 반응 성적표 스캔 연계 실패(IG 도달 수집 자체는 완료): {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
