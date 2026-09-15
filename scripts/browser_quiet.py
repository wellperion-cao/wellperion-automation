# -*- coding: utf-8 -*-
"""자동화 브라우저 창을 GM 화면 밖에 띄운다 (2026-09-15 GM 지적 「이번주 내내 화면이 전체화면으로 확대돼 불편」).

원인 — 아침 통·매출보고 이미지·발행·수집 스크립트 12개가 화면 있는(headless=False) 크롬을 `--start-maximized` 로 띄웠다.
로그인 세션·봇 감지 때문에 headless 로 못 바꾸는 자리들이라, 창을 없애는 대신 **두 모니터 밖 좌표**에 같은 크기로 띄운다.
스크린샷·클릭·업로드는 그대로 된다(2026-09-15 실측: chromium·chrome 둘 다 viewport 1920×953 · 스크린샷 0.3초).
`--disable-backgrounding-occluded-windows` 는 화면 밖 창의 렌더 절전을 끈다 — 이게 없으면 가려진 창은 그림을 안 그린다.

쓰는 법 — 각 스크립트의 launch args 에서 "--start-maximized" 를 *quiet_args() 로 바꾼다.
  사람이 창을 보고 싶으면 환경변수 WP_BROWSER_SHOW=1 → 종전처럼 최대화로 뜬다(로그인 캡처 등 손이 필요한 자리).
"""
import os

WINDOW = "1920,1040"          # 최대화와 같은 급의 창(가로 1920 · 뷰포트 953px) — 보고 이미지 폭이 안 바뀐다
OFFSCREEN = "-4000,-4000"     # 주 모니터(0,0~3440)·보조 모니터(-1920~0) 둘 다 밖


def quiet_args():
    if os.environ.get("WP_BROWSER_SHOW") == "1":
        return ["--start-maximized"]
    return ["--window-size=" + WINDOW, "--window-position=" + OFFSCREEN,
            "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"]


if __name__ == "__main__":
    os.environ.pop("WP_BROWSER_SHOW", None)
    a = quiet_args()
    assert "--start-maximized" not in a and any(x.startswith("--window-position=-") for x in a)
    os.environ["WP_BROWSER_SHOW"] = "1"
    assert quiet_args() == ["--start-maximized"]
    print("selftest ok")
