#!/usr/bin/env bash
# deploy_funnel.sh 가 서버에 올려 실행하는 쪽 — 표 생성 · selftest · cron · 첫 동기화 · erp-api 재기동 · 확인.
set -euo pipefail
cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print("schema ok")'
/usr/bin/python3 /srv/erp/api/sync_funnel.py --selftest
echo "*/5 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_funnel.py >> /srv/erp/sync_funnel.log 2>&1" | sudo tee /etc/cron.d/erp-funnel-sync >/dev/null
/usr/bin/python3 /srv/erp/api/sync_funnel.py
sudo systemctl restart erp-api && sleep 2 && systemctl is-active erp-api
curl -s http://127.0.0.1:8001/api/funnel/health; echo
curl -s "http://127.0.0.1:8001/api/funnel/period_breakdown?from=$(date +%Y-%m-01)&to=$(date +%Y-%m-%d)&_pv=1" | head -c 300; echo
