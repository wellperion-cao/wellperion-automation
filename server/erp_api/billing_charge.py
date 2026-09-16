# -*- coding: utf-8 -*-
"""랩스 구독 카드 자동결제 — 매달 1일 정기 청구 cron (배12680 · 2026-09-16 시토).

api_billing.run_due_charges() 를 그대로 부른다 — HTTP 왕복 없이 내부 함수 호출(cron 은 같은 서버
프로세스라 이게 더 단순하고, 관리자 인증 헤더를 cron 에 흉내 낼 필요도 없다). 도래 기준 = 구독의
next_charge<=오늘(신규 청구) + billing_charges 의 retry_at<=오늘(3일 뒤 1회 재시도).

실행: python3 /srv/erp/api/billing_charge.py           (매일 09:00 · 도래한 것만 실제로 청구한다)
      python3 billing_charge.py --once                 — cron 없이 한 번(등록은 배포 때 — 다른 erp-*-sync 와 같은 자리)
자체점검: python3 billing_charge.py --selftest          (같은 DB 의 tenant 'selftest' · 네트워크 없음 — api_billing.selftest 재사용)

등록 예정(배포 때): /etc/cron.d/erp-billing-charge
  0 9 * * * root cd /srv/erp/api && /usr/bin/python3 billing_charge.py >> /var/log/erp-billing-charge.log 2>&1
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_inquiries import db, load_env  # noqa: E402 — 같은 env·같은 DB
import api_billing  # noqa: E402


def main():
    load_env()
    conn = db.connect()
    db.init_schema(conn)   # 멱등 — billing_subscriptions·billing_secrets·billing_charges 표가 없으면 만든다
    conn.close()
    results = api_billing.run_due_charges()
    ok = sum(1 for r in results if r.get("ok"))
    failed = [r for r in results if not r.get("ok")]
    print("billing charge %s · 대상 %d · 성공 %d · 실패 %d %s" % (
        api_billing._now_str(), len(results), ok, len(failed),
        ("· " + ",".join("%s(%s)" % (r["tenant"], r.get("error") or r.get("skipped", "")) for r in failed)) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        api_billing.selftest()
        sys.exit(0)
    load_env()
    sys.exit(main())
