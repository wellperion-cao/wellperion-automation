# -*- coding: utf-8 -*-
"""AI·서버 비용 실측 — 힉스필드 크레딧 + AWS 사용액 → status/cost_status.json (2026-09-15 GM 「AI 토큰 현황 안에 힉스필드 사용량 + AWS 비용관리까지」).

원천 둘, 둘 다 이 PC 에서 바로 읽힌다(2026-09-15 실측):
  · 힉스필드 = `higgsfield account status --json`(잔여 크레딧·플랜) + `account transactions --size 100 --json`(건별 사용).
  · AWS      = Cost Explorer(boto3 · ~/.aws/credentials 기본 프로필). 사용액(Usage)과 크레딧 상쇄(Credit)를 갈라 읽는다 —
               지금은 크레딧이 사용액을 전부 상쇄해 실청구 0 이다. 상쇄가 끝나는 날부터 실청구가 생긴다.
비용 = Cost Explorer 는 호출당 $0.01 이라 하루 한 번만 읽는다(같은 날 파일이 있으면 건너뜀 · --force 로 강제).
출력 = status/cost_status.json + 3. 웰페리온 가이드/status/cost_status.json(화면이 읽는 사본 · erp/admin 비용 현황 판).
예약 = gas_dependency_publish.py(매시) 가 이 스크립트를 함께 돌리고 두 파일을 저장·배포한다.
  python scripts/cost_collect.py [--force] [--selftest]
"""
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = [ROOT / "status" / "cost_status.json", ROOT / "3. 웰페리온 가이드" / "status" / "cost_status.json"]
USD_KRW = 1400                 # token_usage.py 와 같은 고정 환율
AWS_BUDGET_KRW = 150000        # 결재 SSOT 「AI 운영 예산 월 150만원」 안의 AWS 추정치(2026-09-02)
KST = dt.timezone(dt.timedelta(hours=9))


def _now():
    return dt.datetime.now(KST)


# ── 힉스필드 ────────────────────────────────────────────────────────────────────────────────────
def _hf(args):
    exe = shutil.which("higgsfield")
    if not exe:
        raise RuntimeError("higgsfield CLI 없음")
    r = subprocess.run([exe] + args + ["--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200])
    return json.loads(r.stdout)


def higgsfield(status, tx, today):
    """status/tx = CLI JSON. 이번 달 사용 크레딧·모델별·최근 건."""
    month = today.strftime("%Y-%m")
    by_model, spent, last = {}, 0.0, None
    for it in tx.get("items", []):
        if it.get("action") != "spend":
            continue
        day = str(it.get("created_at", ""))[:10]
        c = abs(float(it.get("credits") or 0))
        if day.startswith(month):
            spent += c
            by_model[it.get("display_name") or "?"] = round(by_model.get(it.get("display_name") or "?", 0) + c, 2)
        if last is None:
            last = {"at": day, "model": it.get("display_name"), "credits": c}
    return {"plan": status.get("subscription_plan_type"), "credits_left": status.get("credits"),
            "month": month, "month_spent": round(spent, 2),
            "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1])), "last": last,
            "note": "크레딧 = 힉스필드 안의 단위(플랜 요금 안에 포함) · 이번 달 사용은 거래 목록 100건 안에서 센다"}


# ── AWS ─────────────────────────────────────────────────────────────────────────────────────────
def aws(today):
    import boto3
    ce = boto3.client("ce", region_name="us-east-1")
    m0 = today.replace(day=1)
    prev0 = (m0 - dt.timedelta(days=1)).replace(day=1)
    end = (today + dt.timedelta(days=1)).isoformat()

    def usage_by_service(s, e):
        r = ce.get_cost_and_usage(TimePeriod={"Start": s, "End": e}, Granularity="MONTHLY", Metrics=["UnblendedCost"],
                                  Filter={"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Usage"]}},
                                  GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}])
        rows = {}
        for t in r["ResultsByTime"]:
            for g in t["Groups"]:
                rows[g["Keys"][0]] = round(rows.get(g["Keys"][0], 0) + float(g["Metrics"]["UnblendedCost"]["Amount"]), 2)
        return dict(sorted(rows.items(), key=lambda x: -x[1]))

    mtd = usage_by_service(m0.isoformat(), end)
    prev = usage_by_service(prev0.isoformat(), m0.isoformat())
    r = ce.get_cost_and_usage(TimePeriod={"Start": m0.isoformat(), "End": end}, Granularity="MONTHLY", Metrics=["UnblendedCost"],
                              GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}])
    rec = {g["Keys"][0]: round(float(g["Metrics"]["UnblendedCost"]["Amount"]), 2) for t in r["ResultsByTime"] for g in t["Groups"]}
    usage = round(sum(mtd.values()), 2)
    credit = rec.get("Credit", 0.0)
    net = round(usage + credit + rec.get("Tax", 0.0), 2)
    days = max(today.day, 1)
    return {"month": m0.strftime("%Y-%m"), "usage_usd": usage, "usage_krw": round(usage * USD_KRW),
            "credit_usd": credit, "net_usd": net, "net_krw": round(net * USD_KRW),
            "daily_avg_usd": round(usage / days, 2),
            "month_projection_krw": round(usage / days * 30 * USD_KRW),
            "by_service": mtd, "prev_month_usage_usd": round(sum(prev.values()), 2),
            "budget_krw": AWS_BUDGET_KRW, "usd_krw": USD_KRW,
            "note": "사용액 = 실제 쓴 만큼 · 크레딧 = AWS 가 깎아 준 만큼 · 실청구 = 카드로 나가는 돈(크레딧이 남는 동안 0)"}


def write(out):
    for p in OUT:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--force" not in argv and OUT[0].exists():
        try:
            if json.loads(OUT[0].read_text(encoding="utf-8")).get("generated_at", "")[:10] == _now().strftime("%Y-%m-%d"):
                print("오늘 것 있음 — 건너뜀(--force 로 강제)")
                return 0
        except Exception:  # noqa: BLE001
            pass
    today = _now().date()
    out = {"generated_at": _now().isoformat(), "higgsfield": None, "aws": None, "errors": {}}
    try:
        out["higgsfield"] = higgsfield(_hf(["account", "status"]), _hf(["account", "transactions", "--size", "100"]), today)
    except Exception as e:  # noqa: BLE001
        out["errors"]["higgsfield"] = str(e)[:200]
    try:
        out["aws"] = aws(today)
    except Exception as e:  # noqa: BLE001
        out["errors"]["aws"] = str(e)[:200]
    write(out)
    print("wrote", OUT[0], "hf=%s aws=%s errors=%s" % (bool(out["higgsfield"]), bool(out["aws"]), out["errors"]))
    return 1 if len(out["errors"]) == 2 else 0


def selftest():
    today = dt.date(2026, 9, 15)
    st = {"credits": 624.21, "email": "x", "subscription_plan_type": "plus"}
    tx = {"items": [{"action": "spend", "created_at": "2026-09-06T06:30:21Z", "credits": -52, "display_name": "Seedance 2.5"},
                    {"action": "spend", "created_at": "2026-09-06T06:29:20Z", "credits": -2.37, "display_name": "GPT 6 Astra"},
                    {"action": "spend", "created_at": "2026-08-30T06:29:20Z", "credits": -9, "display_name": "GPT 6 Astra"},
                    {"action": "grant", "created_at": "2026-09-01T00:00:00Z", "credits": 700, "display_name": "plan"}]}
    h = higgsfield(st, tx, today)
    assert h["month_spent"] == 54.37 and h["by_model"] == {"Seedance 2.5": 52, "GPT 6 Astra": 2.37} and h["credits_left"] == 624.21, h
    assert h["last"]["model"] == "Seedance 2.5"
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
