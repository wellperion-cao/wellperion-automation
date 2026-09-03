#!/usr/bin/env bash
# 웰페리온 문의 미러 API 배포 — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_api.sh
# 하는 일: app.py·sync_inquiries.py·systemd 유닛·nginx location·cron 을 올리고 기동한다.
# api.env(원천 URL)는 처음 한 번만 만들고 다시 덮지 않는다. erp-auth·erp.conf 는 건드리지 않는다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$S 'mkdir -p /srv/erp/api'
$SCP server/erp_api/app.py server/erp_api/sync_inquiries.py $HOST:/srv/erp/api/
$SCP server/erp_api/erp-api.service $HOST:/tmp/erp-api.service
$SCP server/erp_api/api.nginx.conf $HOST:/tmp/api.conf

if ! $S 'test -f /srv/erp/api.env'; then
  # 원천 GAS 엔드포인트는 저장소 정본(scripts/cpo_report.py FUNNEL_EXEC_URL)에서 그대로 가져온다.
  GAS=$(grep -A2 '^FUNNEL_EXEC_URL' scripts/cpo_report.py | tr -d ' "()\n' | sed 's/^FUNNEL_EXEC_URL=//')
  $S "umask 077; cat > /srv/erp/api.env <<E2
FUNNEL_EXEC_URL=$GAS
ERP_DB=/srv/erp/erp.db
E2"
fi

$S 'sudo mkdir -p /etc/nginx/conf.d/erp-locations \
    && sudo mv /tmp/api.conf /etc/nginx/conf.d/erp-locations/api.conf \
    && sudo mv /tmp/erp-api.service /etc/systemd/system/erp-api.service \
    && echo "*/5 * * * * ec2-user /usr/bin/python3 /srv/erp/api/sync_inquiries.py >> /srv/erp/sync_inquiries.log 2>&1" \
       | sudo tee /etc/cron.d/erp-api-sync >/dev/null \
    && sudo systemctl daemon-reload && sudo systemctl enable --now erp-api >/dev/null && sudo systemctl restart erp-api \
    && sleep 2 && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx \
    && systemctl is-active erp-api \
    && curl -s -o /dev/null -w "내부 health = %{http_code}\n" http://127.0.0.1:8001/api/health \
    && curl -s -o /dev/null -w "외부 무쿠키 health = %{http_code}\n" http://127.0.0.1/api/health'
