# -*- coding: utf-8 -*-
"""서버 쪽 구글(Apps Script) 의존 호출 수 — 최근 24시간 (2026-09-14 시토 · GM 「구글 삭제까지」).
AWS 이관 표(cto/aws_migration.html)의 삭제 조건 둘째 항목을 실측으로 채운다.

두 숫자를 가른다 — 뜻이 다르다:
  · gas_judged_24h  = 아직 구글이 판정해야 하는 쓰기(NO_SERVER_ACTIONS · 지금은 unlock_round 하나) 건수.
                      이것이 0 이어야 구글을 지울 수 있다.
  · pushback_24h    = 서버 원장에 적은 뒤 시트 사본을 맞추려고 되민 건수(gas_status ok). 사본 유지용이라
                      구글을 지우는 날 같이 끄는 것이지 「의존」이 아니다.
출력 = /srv/erp/www/status/gas_calls_24h.json (www = repo/3. 웰페리온 가이드 심볼릭링크) (git 미러 안의 미추적 파일 — pull 이 지우지 않는다).
크론 = /etc/cron.d/erp-gas-calls (매시 5분). write_log.at 은 KST 문자열(YYYY-MM-DD HH:MM)이라 문자열 비교로 자른다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/srv/erp/common")
sys.path.insert(0, "/srv/erp/api")
import db  # noqa: E402

OUT = os.environ.get("ERP_GAS_CALLS_OUT", "/srv/erp/www/status/gas_calls_24h.json")
KST = timezone(timedelta(hours=9))


def main():
    try:
        from api_write import NO_SERVER_ACTIONS
        judged = sorted(NO_SERVER_ACTIONS.keys())
    except Exception:
        judged = ["unlock_round"]
    since = (datetime.now(KST) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    c = db.connect(readonly=True)
    base = "FROM write_log WHERE at > %s AND tenant_id <> 'selftest' AND gas_status NOT IN ('test','skipped')"
    n_judged = c.execute("SELECT count(*) " + base + " AND action = ANY(%s)", (since, judged)).fetchone()[0]
    n_push = c.execute("SELECT count(*) " + base + " AND gas_status = 'ok'", (since,)).fetchone()[0]
    out = {"generated_at": datetime.now(KST).isoformat(timespec="minutes"), "since": since,
           "gas_judged_24h": int(n_judged), "judged_actions": judged, "pushback_24h": int(n_push)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False))
    assert out["gas_judged_24h"] >= 0 and out["pushback_24h"] >= 0


if __name__ == "__main__":
    main()
