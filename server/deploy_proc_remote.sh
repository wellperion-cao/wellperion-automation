#!/usr/bin/env bash
# deploy_proc.sh 가 서버에 올려 실행하는 쪽 — env 확인 · 표 생성 · selftest · cron · 첫 동기화 · erp-api 재기동 · 확인.
# cron 이 10분인 이유: 전량 조회가 실측 37.7초다(2026-09-11). 5분마다 돌리면 GAS 실행 할당량을 헛되이 먹는다.
set -euo pipefail
for k in PROC_GAS_URL SALES_GATE_PW; do
  grep -q "^$k=" /srv/erp/api.env || { echo "api.env 에 $k 없음 — 먼저 채운다"; exit 1; }
done
cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print("schema ok")'
/usr/bin/python3 /srv/erp/api/sync_proc.py --selftest
/usr/bin/python3 /srv/erp/api/api_proc.py --selftest
echo "*/10 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_proc.py >> /srv/erp/sync_proc.log 2>&1" | sudo tee /etc/cron.d/erp-proc-sync >/dev/null
/usr/bin/python3 /srv/erp/api/sync_proc.py
sudo systemctl restart erp-api && sleep 2 && systemctl is-active erp-api
curl -s http://127.0.0.1:8001/api/proc/health; echo
