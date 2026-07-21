# -*- coding: utf-8 -*-
"""발행완료 과대보고 감사기 (2026-07-21 · GM "이번이 마지막" 재발방지 박제).

문제(8회 반복): 콘텐츠가 임시저장/임시등록(초안)까지만 됐는데 review_queue status를
'발행완료'로 마킹 → GM이 안 된 걸 됐다고 믿고 지나감(과대보고).

이 감사기는 review_queue.json을 훑어 **'발행완료'인데 공개 URL 실측 증거가 없는 항목**을
적발한다. 공개 URL을 가진 항목은 라이브(HTTP 200)까지 실측한다.
검증 없이는 발행완료를 신뢰하지 않는다 = 코드가 과대보고를 잡아낸다.

정책:
  - 공개 URL이 필요한 채널(네이버 블로그·카페·카카오·당근·인스타그램)에서 status='발행완료'인데
    published_url/post_url이 없으면 → 🔴 OVERCLAIM_SUSPECT(URL 미확인).
  - published_url이 있으면 → curl HTTP 확인. 200 아니면 🟠 URL_DEAD.
    (네이버 카페는 삭제글도 200 반환하는 함정이 있어 200이어도 '카페는 수동확인 권장' 주석만 단다.)
  - '임시저장'·'검수대기'·'발행검증대기' 등은 정상(감사 대상 아님).

사용:
  python scripts/publish_status_audit.py            # 감사 리포트(적발 있으면 exit 1)
  python scripts/publish_status_audit.py --no-http  # URL 라이브체크 생략(빠름·오프라인)
  python scripts/publish_status_audit.py --alert     # 적발 시 텔레그램 1줄 경고(GM 업무보고방)

종료코드: 0=적발 없음(깨끗) / 1=과대보고 의심 적발.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"

# 공개 URL이 반드시 있어야 '발행완료'가 성립하는 채널 키워드
URL_REQUIRED_CHANNEL_KW = ("블로그", "카페", "카카오", "당근", "인스타")
DONE_STATUS = "발행완료"
CAFE_KW = "카페"  # 삭제글도 200 함정 채널


def _load_queue() -> list:
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] 큐 파싱 실패: {e}")
        return []


def _url_of(item: dict) -> str:
    for k in ("published_url", "post_url", "url"):
        v = item.get(k)
        if v and str(v).strip() and str(v).strip() != "None":
            return str(v).strip()
    return ""


def _http_status(url: str, timeout: int = 12) -> int:
    """공개 URL HTTP 상태코드. 실패=0."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def audit(check_http: bool = True) -> list[dict]:
    """과대보고 의심 목록 반환."""
    suspects: list[dict] = []
    for item in _load_queue():
        if item.get("status") != DONE_STATUS:
            continue
        channel = str(item.get("channel", ""))
        if not any(kw in channel for kw in URL_REQUIRED_CHANNEL_KW):
            continue  # 공개 URL 불필요 채널(있으면)은 스킵
        item_id = str(item.get("id", ""))
        url = _url_of(item)
        if not url:
            suspects.append({
                "id": item_id, "channel": channel, "level": "🔴 URL_MISSING",
                "detail": "발행완료인데 공개 URL 없음 — 실제 발행 미확인(과대보고 의심)",
            })
            continue
        if check_http:
            code = _http_status(url)
            if code != 200:
                suspects.append({
                    "id": item_id, "channel": channel, "level": "🟠 URL_DEAD",
                    "detail": f"발행완료 URL이 HTTP {code} — 공개 안 됨/삭제 의심", "url": url,
                })
            elif CAFE_KW in channel:
                # 200이어도 카페는 삭제글도 200 → 정보성 주석만(적발 아님)
                pass
    return suspects


def _alert_telegram(suspects: list[dict]) -> None:
    """적발 시 텔레그램 1줄 경고(업무보고방). 토큰 stdout 노출 금지."""
    env = ROOT / "telegram_bot" / ".env"
    token = chat = ""
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not token or not chat:
        return
    n = len(suspects)
    ids = ", ".join(s["id"].split("-")[-1] for s in suspects[:6])
    msg = f"🔴 발행완료 과대보고 의심 {n}건 감지 — {ids} (publish_status_audit)"
    try:
        import urllib.parse
        data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="발행완료 과대보고 감사기")
    ap.add_argument("--no-http", action="store_true", help="URL 라이브체크 생략")
    ap.add_argument("--alert", action="store_true", help="적발 시 텔레그램 경고")
    args = ap.parse_args()

    suspects = audit(check_http=not args.no_http)
    if not suspects:
        print("[OK] 발행완료 과대보고 의심 0건 — 깨끗.")
        return 0
    print(f"[적발] 발행완료 과대보고 의심 {len(suspects)}건:")
    for s in suspects:
        line = f"  {s['level']}  {s['id']}  [{s['channel']}]  {s['detail']}"
        if s.get("url"):
            line += f"  {s['url']}"
        print(line)
    if args.alert:
        _alert_telegram(suspects)
    return 1


if __name__ == "__main__":
    sys.exit(main())
