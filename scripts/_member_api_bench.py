# -*- coding: utf-8 -*-
"""1회용 — member-api 신규 배포 왕복 실측(읽기 전용). 방법은 intake-api 실측과 동일:
   존재하지 않는 action(순수 고정비용) vs 실제 action(ping, 쓰기 없음), 각 median.
   ⚠ GM 의 authorize() 1회 승인 전까지는 전부 403 이 정상(권한 미승인) — 그 경우
   이 스크립트는 에러 개수만 찍고 median 을 못 낸다(값 없음 그대로 보고, 조작 금지)."""
import statistics
import time
import urllib.request

URL = "https://script.google.com/macros/s/AKfycbw4KuH1j8x5pFx8yZtn0aMXouNd4I0Vywq1T6v-CTbf15GB1PIMCHK8IcloA7WWHpV8BQ/exec"


def timed(action, n):
    times = []
    errs = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(URL + "?action=" + action, timeout=30) as r:
                r.read()
        except Exception as e:
            errs += 1
            print("  err:", e)
            continue
        times.append(time.perf_counter() - t0)
    return times, errs


for action, n in [("nope_no_such_action", 8), ("ping", 8)]:
    ts, errs = timed(action, n)
    if ts:
        print(f"{action}: n={len(ts)} median={statistics.median(ts):.2f}s all={[round(t,2) for t in ts]}")
    else:
        print(f"{action}: n=0 (errs={errs}) — 응답 실패뿐, median 없음")
