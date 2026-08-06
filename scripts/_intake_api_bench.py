# -*- coding: utf-8 -*-
"""1회용 — intake-api 신규 배포 왕복 실측(읽기 전용). 방법은 배240 실측과 동일:
   존재하지 않는 액션(순수 고정비용) vs 실제 액션(ping, 쓰기 없음), 각 median."""
import statistics
import time
import urllib.request

URL = "https://script.google.com/macros/s/AKfycbyLc2cnOeyyCpdrluJrgrUNrfhSJS3W-9wte5ndOBNS5S8Dux7KwcV8WAAXs2bwi2yFcw/exec"


def timed(action, n):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(URL + "?action=" + action, timeout=30) as r:
                r.read()
        except Exception as e:
            print("  err:", e)
            continue
        times.append(time.perf_counter() - t0)
    return times


for action, n in [("nope_no_such_action", 8), ("ping", 8)]:
    ts = timed(action, n)
    print(f"{action}: n={len(ts)} median={statistics.median(ts):.2f}s all={[round(t,2) for t in ts]}")
