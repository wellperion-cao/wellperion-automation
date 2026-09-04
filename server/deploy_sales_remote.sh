#!/usr/bin/env bash
# deploy_sales.sh 가 서버에 올려 실행하는 쪽 — env 확인 · 표 생성 · selftest · cron · 첫 동기화 · erp-api 재기동 · 확인.
set -euo pipefail
for k in SALES_GAS_URL PROC_GAS_URL DEPTREP_GAS_URL SALES_GATE_PW DEPTREP_TOKEN; do
  grep -q "^$k=" /srv/erp/api.env || { echo "api.env 에 $k 없음 — 먼저 채운다"; exit 1; }
done
cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print("schema ok")'
/usr/bin/python3 /srv/erp/api/sync_sales.py --selftest
/usr/bin/python3 /srv/erp/api/api_sales.py --selftest
echo "*/5 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_sales.py >> /srv/erp/sync_sales.log 2>&1" | sudo tee /etc/cron.d/erp-sales-sync >/dev/null
/usr/bin/python3 /srv/erp/api/sync_sales.py
sudo systemctl restart erp-api && sleep 2 && systemctl is-active erp-api
curl -s http://127.0.0.1:8001/api/sales/health; echo
