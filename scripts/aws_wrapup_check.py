# -*- coding: utf-8 -*-
"""AWS 이관 뒷정리 검수 — 매일 한 번 재서 이상·관문 도달만 말한다 (2026-09-15 시토 · GM 「검수·뒷정리 실수 없게 챙겨줘 · 제일 중요」).

이관 현황 화면(cto/aws_migration.html)은 2026-09-15 GM 지시로 지웠다. 남은 뒷정리는 화면이 아니라 이 검수기가 챙긴다 —
자가건강 디제스트(self_health_watchdog · 09:10 하루 1통)에 한 섹션으로 실린다. 정상이면 침묵, 이상·관문 도달만 줄로 낸다.

재는 것(전부 읽기 전용 · 값을 고치지 않는다):
  ① 구글 판정 쓰기 24h(서버 gas_calls_24h.json · gas_judged_24h) — 0 이 7일 이어져야 구글 앱을 끌 수 있다(관문 A).
  ② 되밀기 실패·미전송(서버 write_log) — 접수(reg_update · 시트 은퇴 · sheet-missing)는 빼고 센다.
  ③ 서버 API 건강(failed_modules) · 쓰기 영역 스위치 전부 server 인지.
  ④ 인사 열쇠(HR_GAS_PASSWORD) 학습됐는지 · 직원 표 행 수(자동 적재 결과).
  ⑤ 실무진 피드백 중 「느리·안 됨·오류」 낱말이 든 열린 배.
  ⑥ 뒷정리 배 4척(12645·12646·12649·12658) + 날짜 관문(지출 전환 9/19 · 깃허브 착수 9/19 · 매출 손입력 폐지 10/1).
상태 = status/aws_wrapup.json(연속 0일 수·마지막 측정). 관문 A 도달(7일)은 줄로 올린다 — 그 다음 행동(끄기·결재 카드)은 시토가 한다.

  python scripts/aws_wrapup_check.py            # 측정 + 상태 갱신 + 줄 출력
  python scripts/aws_wrapup_check.py --selftest # 서버 없이 판정 규칙만
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "status" / "aws_wrapup.json"
QUEUE = ROOT / "status" / "_queue.json"
KST = dt.timezone(dt.timedelta(hours=9))
SHIPS = {12645: "인사 4장·잔여 마무리", 12646: "깃허브 탈피", 12649: "지출·인건비 서버 입력 전환", 12658: "마케팅 자동업로드 서버 배선"}
GATES = [("2026-09-19", 12649, "지출·인건비 시트 → 서버 입력 전환(이번 주)"),
         ("2026-09-19", 12646, "깃허브 탈피 착수(서버 git + S3 백업)"),
         ("2026-10-01", None, "매출 손입력 시트 폐지")]
ZERO_DAYS_NEEDED = 7
SSH = ["ssh", "-i", os.path.expanduser("~/.aws/wellperion-sito.pem"), "-o", "ConnectTimeout=12", "-o", "BatchMode=yes",
       "ec2-user@15.164.151.105"]
# 서버에서 한 번에 재는 작은 파이썬 — 결과 한 줄 JSON. 여기서 아무것도 고치지 않는다.
REMOTE = "\n".join([
    "python3 - <<'PY'",
    "import json,subprocess",
    "o={}",
    "try: o['gas']=json.load(open('/srv/erp/www/status/gas_calls_24h.json',encoding='utf-8'))",
    "except Exception as e: o['gas_err']=str(e)[:80]",
    "def q(sql):",
    "    return subprocess.run(['sudo','-u','postgres','psql','-d','erp','-Atc',sql],capture_output=True,text=True,timeout=20).stdout.strip()",
    "try:",
    "    o['pb_bad']=int(q(\"select count(*) from write_log where gas_status not in ('ok','test','pending') and action<>'reg_update' and at > to_char(now() at time zone 'Asia/Seoul' - interval '1 day','YYYY-MM-DD HH24:MI')\") or 0)",
    "    o['hr_rows']=int(q('select count(*) from hr.employee where vanished_at is null') or 0)",
    "except Exception as e: o['db_err']=str(e)[:80]",
    "try:",
    "    r=subprocess.run(['sudo','grep','-c','^HR_GAS_PASSWORD=.','/srv/erp/api.env'],capture_output=True,text=True,timeout=10); o['hr_key']=r.stdout.strip()=='1'",
    "except Exception as e: o['hr_key_err']=str(e)[:80]",
    "try:",
    "    h=json.loads(subprocess.run(['curl','-s','127.0.0.1:8001/api/health'],capture_output=True,text=True,timeout=10).stdout); o['health_ok']=bool(h.get('ok')); o['failed_modules']=h.get('failed_modules')",
    "    i=json.loads(subprocess.run(['curl','-s','127.0.0.1:8001/api/intake/health'],capture_output=True,text=True,timeout=10).stdout); o['origin_mode']=i.get('origin_mode')",
    "except Exception as e: o['health_err']=str(e)[:80]",
    "print(json.dumps(o,ensure_ascii=False))",
    "PY",
])


def measure_server():
    r = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                       **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    return json.loads(line[-1]) if line else {"ssh_err": (r.stderr or "no output")[-160:]}


def load_queue_items():
    try:
        q = json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return q if isinstance(q, list) else q.get("items", q.get("queue", []))


def judge(server, items, state, today):
    """(lines, new_state). 줄이 비면 정상."""
    lines, st = [], dict(state or {})
    gas = server.get("gas") or {}
    judged = gas.get("gas_judged_24h")
    if judged is None:
        lines.append("▪ 구글 판정 건수 못 읽음 — " + str(server.get("gas_err") or server.get("ssh_err") or "값 없음")[:80])
    else:
        streak = int(st.get("zero_streak_days") or 0)
        if judged == 0:
            streak = streak + 1 if st.get("last_day") != today else streak
        else:
            streak = 0
            lines.append("▪ 구글이 아직 판정한 쓰기 %d건(24h) — 관문 A 연속일 0 으로 되돌림" % judged)
        st.update(zero_streak_days=streak, last_day=today, last_judged=judged)
        if streak >= ZERO_DAYS_NEEDED and not st.get("gate_a_reached"):
            st["gate_a_reached"] = today
            lines.append("▪ 관문 A 도달 — 구글 판정 0건 %d일 연속 · 다음 = 구글 앱·시트 끄기(되돌림 가능 · 시토)" % streak)
    if server.get("pb_bad"):
        lines.append("▪ 시트 되밀기 실패·미전송 %d건(24h · 접수 제외) — pushback 로그 확인" % server["pb_bad"])
    if server.get("health_ok") is False or server.get("failed_modules"):
        lines.append("▪ 서버 API 이상 — failed_modules %s" % (server.get("failed_modules"),))
    om = server.get("origin_mode") or {}
    not_server = [k for k, v in om.items() if k.startswith("write_") and v != "server" and k != "write_reception"]
    if not_server:
        lines.append("▪ 쓰기 영역이 서버 원천에서 벗어남 — %s" % ", ".join(not_server))
    if server.get("hr_key") is False:
        days = int(st.get("hr_key_missing_days") or 0)
        if st.get("hr_key_day") != today:
            days += 1
        st.update(hr_key_missing_days=days, hr_key_day=today)
        if days >= 2:
            lines.append("▪ 인사 적재 열쇠 아직 0(%d일째) — 인사 라인(우열M)이 인사 허브를 한 번 여는지 확인" % days)
    elif server.get("hr_key") and int(server.get("hr_rows") or 0) == 0:
        lines.append("▪ 인사 열쇠는 있는데 직원 표 0행 — hr_autoload.log 확인(10분 크론)")
    kw = ("느리", "느려", "안 돼", "안돼", "안 됨", "안됨", "오류", "에러", "먹통")
    for s in items:
        t = str(s.get("title") or "")
        if "실무진 피드백" in t and s.get("status") in ("PENDING", "IN_PROGRESS") and any(k in t for k in kw):
            lines.append("▪ 실무진 피드백 열림 — %s" % t[:70])
    by = {s.get("ship_no"): s for s in items}
    for due, no, what in GATES:
        s = by.get(no) if no else None
        open_ = (s is not None and s.get("status") in ("PENDING", "IN_PROGRESS")) if no else True
        if today > due and open_:
            lines.append("▪ 기한 지남 %s — %s" % (due[5:].replace("-", "/"), what))
    return lines, st


def section(now=None):
    """self_health_watchdog 용 — 줄 목록(비면 정상)."""
    today = (now or dt.datetime.now(KST)).strftime("%Y-%m-%d")
    try:
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except Exception:
        state = {}
    try:
        server = measure_server()
    except Exception as e:  # noqa: BLE001
        server = {"ssh_err": str(e)[:120]}
    lines, st = judge(server, load_queue_items(), state, today)
    st["measured_at"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    st["server"] = {k: v for k, v in server.items() if k != "origin_mode"}
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return (["🧹 AWS 이관 뒷정리 — 시토"] + lines) if lines else []


def selftest():
    ok_server = {"gas": {"gas_judged_24h": 0}, "pb_bad": 0, "health_ok": True, "failed_modules": {}, "hr_key": True, "hr_rows": 12,
                 "origin_mode": {"write_member": "server", "write_todo": "server", "write_reception": "server"}}
    items = [{"ship_no": 12649, "status": "PENDING", "title": "[시토] 지출"}, {"ship_no": 12646, "status": "PENDING", "title": "[시토] 깃허브"}]
    lines, st = judge(ok_server, items, {}, "2026-09-16")
    assert lines == [] and st["zero_streak_days"] == 1, (lines, st)
    lines, st = judge(ok_server, items, {"zero_streak_days": 6, "last_day": "2026-09-21"}, "2026-09-22")
    assert any("관문 A 도달" in l for l in lines) and st["gate_a_reached"] == "2026-09-22", lines
    lines, st = judge(dict(ok_server, gas={"gas_judged_24h": 2}), items, {"zero_streak_days": 5, "last_day": "2026-09-19"}, "2026-09-20")
    assert st["zero_streak_days"] == 0 and any("판정한 쓰기 2건" in l for l in lines)
    lines, _ = judge(dict(ok_server, pb_bad=3, hr_rows=0), items + [{"title": "[시포] 실무진 피드백 — 저장이 너무 느려요", "status": "PENDING"}], {}, "2026-09-16")
    assert any("되밀기" in l for l in lines) and any("직원 표 0행" in l for l in lines) and any("실무진 피드백" in l for l in lines), lines
    lines, _ = judge(ok_server, items, {}, "2026-09-20")
    assert sum("기한 지남" in l for l in lines) == 2, lines            # 9/19 관문 둘 다 지남 · 10/1 은 아직
    lines, st = judge(dict(ok_server, hr_key=False), items, {"hr_key_missing_days": 1, "hr_key_day": "2026-09-15"}, "2026-09-16")
    assert any("열쇠 아직 0(2일째)" in l for l in lines), lines
    lines, _ = judge({"ssh_err": "timeout"}, [], {}, "2026-09-16")
    assert lines and "못 읽음" in lines[0]
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        out = section()
        print("\n".join(out) if out else "정상 — 낼 줄 없음 · 상태 " + str(STATE))
