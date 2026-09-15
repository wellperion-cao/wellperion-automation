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
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# 캡처 주소 = ERP 판(erp.wellperion.com)이 기본이다. 화면은 hostname 이 erp 일 때만 서버 API(ERP_API_ON)를
# 켜므로, GitHub Pages 공개 사본을 찍으면 회원 5칸·입장 3칸 서버 전환분이 한 칸도 안 들어가고 22칸 전부
# 시트(GAS) 값이 된다 — 「서버판」이라는 이름과 어긋난다(2026-09-15 GM 지적 · 시포 실측).
# 로그인 벽은 기존 로그인 쿠키(erp_session)로 지난다 — 새 인증 체계·새 공개 통로를 만들지 않는다.
# 토큰이 없으면 종전대로 공개 사본으로 내려간다(발송이 멈추지 않게). 바꾸려면 env REPORT_CAPTURE_URL.
_PAGE = "%EB%A7%A4%EC%B6%9C%ED%9A%8C%EC%9B%90%ED%98%84%ED%99%A9%EB%B3%B4%EA%B3%A0.html"
_PAGES_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/report/" + _PAGE
_ERP_URL = "https://erp.wellperion.com/coo/report/" + _PAGE


def _session_token() -> str:
    """telegram_bot/.env 의 ERP_SESSION_TOKEN 한 줄(저장소 밖) — ops_shared 와 같은 관례."""
    try:
        from collectors.ops_shared import _env_line
        return _env_line("ERP_SESSION_TOKEN")
    except Exception:
        return ""


# ★기본은 아직 공개 사본이다 — 봇 계정에 /coo/report/ 권한이 없어 ERP 판은 /auth/forbidden 으로 막힌다
# (2026-09-15 실측). 권한이 열리면 env REPORT_CAPTURE_URL 에 _ERP_URL 을 넣는 것만으로 서버 원천으로 바뀐다.
URL = os.environ.get("REPORT_CAPTURE_URL") or _PAGES_URL
# 1~3면 = 화면의 .page 세 덩어리(id) — 1면 매출 및 회원 현황 보고 · 2면 문의 등록 상세 · 3면 운영 현황(GM 지시 2026-09-14).
PAGES3 = ("sheet", "sheet2", "sheet3")

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


def capture(check_only: bool = False, pages: "tuple[str, ...]" = ("sheet",)) -> "tuple[int, str]":
    """pages 의 요소(id)마다 PNG 한 장. 성공 msg = 경로들을 '|' 로 이은 문자열(1면만이면 경로 하나)."""
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
        # ERP 판을 찍을 때만 로그인 쿠키를 얹는다(서버 API 가 켜지는 유일한 조건 = erp 도메인).
        if "erp.wellperion.com" in URL:
            tok = _session_token()
            if tok:
                ctx.add_cookies([{"name": "erp_session", "value": tok,
                                  "domain": "erp.wellperion.com", "path": "/"}])
        page = ctx.new_page()
        try:
            # 캐시 버스터 — 공개 사본(Pages)은 CDN 캐시라 방금 올린 판이 아니라 옛 판이 찍힐 수 있다
            # (2026-09-15 실측: 화면은 새 판인데 캡처만 옛 판이 나왔다).
            _u = URL + ("&" if "?" in URL else "?") + "cb=" + str(int(time.time()))
            page.goto(_u, wait_until="domcontentloaded", timeout=60_000)
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

        # READY 뒤에도 늦게 오는 칸(일 단위·두 장부 대조 등)이 「불러오는 중…」으로 남은 채 찍히던 것(2026-09-14 실측)
        # — 그 글자가 사라질 때까지 최대 60초 더 기다린다. 끝내 남으면 그대로 찍는다(사유는 그림에 보인다).
        try:
            page.wait_for_function(
                "() => !document.body.innerText.includes('불러오는 중')"
                " && (function(){var e=document.getElementById('p2les');"
                "return !e || e.innerText.trim().length > 10;})()", timeout=150_000)
        except Exception:
            pass

        outs = []
        for i, pid in enumerate(pages, start=1):
            loc = page.locator("#" + pid)
            if loc.count() == 0:
                browser.close()
                return 1, f"화면에 {i}면(#{pid})이 없습니다 — 화면 판이 낡았거나 id 가 바뀜"
            suffix = "" if len(pages) == 1 else f"_{i}면"
            out = archive_dir() / f"매출회원현황보고_{datetime.now():%Y%m%d}{suffix}.png"
            loc.screenshot(path=str(out))
            if not out.exists() or out.stat().st_size < 50_000:
                browser.close()
                return 1, f"{i}면 그림이 만들어지지 않았거나 너무 작습니다"
            outs.append(str(out.resolve()))
        browser.close()
        return 0, "|".join(outs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true", help="점검 결과만 보고 그림은 만들지 않는다")
    ap.add_argument("--pages", type=int, default=1, choices=(1, 3), help="1=1면만(종전) · 3=1~3면 각각")
    args = ap.parse_args()

    code, msg = capture(check_only=args.check_only, pages=PAGES3 if args.pages == 3 else ("sheet",))
    if code:
        print(f"FAILED: {msg}")
        return 1
    print(msg if args.check_only else f"IMAGE: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
