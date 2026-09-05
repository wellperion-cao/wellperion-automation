#!/usr/bin/env bash
# deploy_misc.sh 가 서버에 올려 실행하는 쪽 — env 확인 · 표 생성 · selftest · cron · 첫 동기화 · erp-api 재기동 · 확인.
set -euo pipefail
for k in RENEWAL_GAS_URL CHECK_GAS_URL SCHEDULE_GAS_URL; do   # ops(vendor_list)=CHECK_GAS_URL · schedule(load_schedule)=SCHEDULE_GAS_URL (배990)
  grep -q "^$k=" /srv/erp/api.env || { echo "api.env 에 $k 없음 — 먼저 채운다"; exit 1; }
done
cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print("schema ok")'
/usr/bin/python3 /srv/erp/api/sync_misc.py --selftest
/usr/bin/python3 /srv/erp/api/api_misc.py --selftest
echo "*/5 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_misc.py >> /srv/erp/sync_misc.log 2>&1" | sudo tee /etc/cron.d/erp-misc-sync >/dev/null
/usr/bin/python3 /srv/erp/api/sync_misc.py
sudo systemctl restart erp-api && sleep 2 && systemctl is-active erp-api
curl -s http://127.0.0.1:8001/api/misc/health; echo
curl -s http://127.0.0.1:8001/api/misc/renewal/stats | head -c 200; echo
curl -s http://127.0.0.1:8001/api/misc/ops/vendor_list | head -c 200; echo
curl -s http://127.0.0.1:8001/api/misc/schedule/load_schedule | head -c 200; echo
curl -s "http://127.0.0.1:8001/api/todo?limit=1" | head -c 200; echo
