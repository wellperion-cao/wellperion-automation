# -*- coding: utf-8 -*-
"""매출·회원 현황 보고 화면을 PNG 로 찍는다 — 화면이 스스로 「통과」라고 한 때만.

왜 있나
    09:30 카톡 매출보고 그림을 「시트 캡처」에서 「ERP 보고 화면」으로 바꾸기 위한 렌더러다.
    시트 캡처와 달리 이 화면은 여러 원천(보고 시트·강습 계약 블록·ERP 월별 매출·ERP 지출)을
    합쳐 그린다. 원천 하나가 조용히 멈추면 화면은 그 칸만 비운 채 멀쩡해 보이고, 그대로 찍히면
    아무도 모르게 틀린 보고가 회장님 방으로 나간다.

    그래서 화면 쪽에 자체 점검을 심었고(window.__REPORT_READY), 이 스크립트는 그 판정이
    ok 일 때만 그림을 만든다. ok 가 아니면 아무것도 만들지 않고 이유를 적고 끝낸다.
    ▸사람이 눈으로 확인하는 절차를 만들지 않는다 — 확인은 화면이 하고, 차단은 이 파일이 한다.

출력 규약 (generate_sales_report_image.py 와 같다 — 발송 오케스트레이터가 그대로 받는다)
    성공: stdout 에 `IMAGE: <절대경로>` + exit 0
    실패: stdout 에 `FAILED: <이유>`        + exit 1

쓰는 법
    python scripts/report_page_capture.py                # 찍기
    python scripts/report_page_capture.py --check-only   # 점검 결과만 보기(그림 안 만듦)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

URL = ("https://wellperion-cao.github.io/wellperion-automation/coo/report/"
       "%EB%A7%A4%EC%B6%9C%ED%9A%8C%EC%9B%90%ED%98%84%ED%99%A9%EB%B3%B4%EA%B3%A0.html")

# A3 가로 = 1587x1123px(.page 와 같은 값). 화면 폭이 이보다 좁으면 브라우저가 줄여 그리므로 고정한다.
VIEWPORT = {"width": 1660, "height": 1260}
READY_TIMEOUT_MS = 90_000        # 구글 앱스스크립트 4개 조회가 다 끝날 때까지(느린 날 대비 넉넉히)


def archive_dir() -> Path:
    """기존 매출보고 이미지와 같은 자리에 남긴다 — 보관 폴더를 새로 만들지 않는다."""
    try:
        from generate_sales_report_image import get_archive_dir  # noqa: WPS433
        return get_archive_dir()
    except Exception:
        d = ROOT / "status" / "sales_report_images"
        d.mkdir(parents=True, exist_ok=True)
        return d


def capture(check_only: bool = False) -> "tuple[int, str]":
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 1, "playwright 가 설치돼 있지 않습니다 (pip install playwright)"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2, locale="ko-KR",
                                  timezone_id="Asia/Seoul")
        # 사내 게이트 통과 — 비밀번호를 치는 대신 통과 표시만 미리 넣는다(gate.js 의 세션 키).
        ctx.add_init_script("try{sessionStorage.setItem('welp_gate_ok','1')}catch(e){}")
        page = ctx.new_page()
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function("() => window.__REPORT_READY != null", timeout=READY_TIMEOUT_MS)
            ready = page.evaluate("() => window.__REPORT_READY")
        except Exception as exc:
            browser.close()
            return 1, f"화면이 자체 점검을 끝내지 못했습니다 — {exc}"

        if not ready.get("ok"):
            browser.close()
            return 1, "자체 점검 실패 — " + " / ".join(ready.get("fails") or ["사유 미상"])

        note = ""
        if ready.get("warns"):
            note = " · 주의 " + " / ".join(ready["warns"])

        if check_only:
            browser.close()
            return 0, f"자체 점검 통과({ready.get('checked')}항목){note}"

        out = archive_dir() / f"매출회원현황보고_{datetime.now():%Y%m%d}.png"
        page.locator("#sheet").screenshot(path=str(out))
        browser.close()
        if not out.exists() or out.stat().st_size < 50_000:
            return 1, "그림이 만들어지지 않았거나 너무 작습니다"
        return 0, str(out.resolve())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true", help="점검 결과만 보고 그림은 만들지 않는다")
    args = ap.parse_args()

    code, msg = capture(check_only=args.check_only)
    if code:
        print(f"FAILED: {msg}")
        return 1
    print(msg if args.check_only else f"IMAGE: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
