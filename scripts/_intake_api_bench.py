# -*- coding: utf-8 -*-
"""GAS 백엔드 왕복 실측(읽기 전용) — 존재하지 않는 action(순수 고정비용) vs 실제 action,
각 median 을 대조한다. 배240(접수 분리) 때 쓴 방법 그대로다.

  python scripts/_intake_api_bench.py            # 등록된 대상 전부
  python scripts/_intake_api_bench.py intake     # 하나만
  python scripts/_intake_api_bench.py --url <exec주소> --name 임시

⚠ 미승인(403) 상태면 median 을 못 낸다 — 그때는 에러 개수만 찍는다. 값을 지어내지 않는다.
※ 2026-08-20: member-api 용으로 같은 파일이 하나 더 생겨 있었다(_member_api_bench.py).
   같은 일을 하는 파일을 둘 두지 않는다(약속 L21) — 여기로 합치고 그쪽은 지웠다.
"""
import argparse
import statistics
import time
import urllib.request

TARGETS = {
    "intake": "https://script.google.com/macros/s/"
              "AKfycbyLc2cnOeyyCpdrluJrgrUNrfhSJS3W-9wte5ndOBNS5S8Dux7KwcV8WAAXs2bwi2yFcw/exec",
    "member": "https://script.google.com/macros/s/"
              "AKfycbw4KuH1j8x5pFx8yZtn0aMXouNd4I0Vywq1T6v-CTbf15GB1PIMCHK8IcloA7WWHpV8BQ/exec",
}


def timed(url: str, action: str, n: int):
    times, errs = [], []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(f"{url}?action={action}", timeout=30) as r:
                r.read()
        except Exception as e:
            errs.append(f"{type(e).__name__}: {str(e)[:60]}")
            continue
        times.append(time.perf_counter() - t0)
    return times, errs


def run(name: str, url: str, n: int = 8) -> None:
    print(f"=== {name} ===")
    for action in ("nope_no_such_action", "ping"):
        ts, errs = timed(url, action, n)
        if ts:
            print(f"{action}: n={len(ts)} median={statistics.median(ts):.2f}s "
                  f"all={[round(t, 2) for t in ts]}")
        else:
            print(f"{action}: n=0 (실패 {len(errs)}회) — median 없음 · {errs[0] if errs else ''}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GAS 백엔드 왕복 실측(읽기 전용)")
    ap.add_argument("target", nargs="?", choices=sorted(TARGETS), help="생략하면 전부")
    ap.add_argument("--url", help="등록 안 된 주소를 임시로 잴 때")
    ap.add_argument("--name", default="임시")
    ap.add_argument("-n", type=int, default=8, help="각 action 반복 횟수(기본 8)")
    a = ap.parse_args()
    if a.url:
        run(a.name, a.url, a.n)
    else:
        for key in ([a.target] if a.target else sorted(TARGETS)):
            run(key, TARGETS[key], a.n)
