#!/usr/bin/env bash
# 이중기록 대조 배포(배 960) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_reconcile.sh
# 하는 일: reconcile_dual_write.py·api_intake.py 를 올리고, /srv/erp/status 를 만들고, 매일 06:10(KST) cron 을 걸고,
# nginx 에 대조 결과만 로그인 뒤로 넣는 정확일치 location 을 반영한 뒤 한 번 돌려 결과를 보여준다.
# 전환(서버 원본)은 이 스크립트가 하지 않는다 — streak_ok_days 를 보고 사람이 판단한다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$SCP server/erp_api/reconcile_dual_write.py server/erp_api/api_intake.py $HOST:/srv/erp/api/
$SCP server/erp_api/intake.nginx.conf $HOST:/tmp/intake.conf
$S "set -e
    /usr/bin/python3 /srv/erp/api/reconcile_dual_write.py --selftest
    sudo mkdir -p /srv/erp/status && sudo chown ec2-user:ec2-user /srv/erp/status
    printf 'CRON_TZ=Asia/Seoul\n10 6 * * * ec2-user /usr/bin/python3 /srv/erp/api/reconcile_dual_write.py >> /srv/erp/reconcile.log 2>&1\n' \
      | sudo tee /etc/cron.d/erp-reconcile >/dev/null
    sudo chmod 644 /etc/cron.d/erp-reconcile
    sudo cp /tmp/intake.conf /etc/nginx/conf.d/erp-locations/intake.conf
    sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx
    sudo systemctl restart erp-api && sleep 3
    /usr/bin/python3 /srv/erp/api/reconcile_dual_write.py
    curl -s -o /dev/null -w '무쿠키 /api/intake/reconcile = %{http_code} (401 이어야 정상)\n' https://erp.wellperion.com/api/intake/reconcile
    curl -s http://127.0.0.1:8001/api/intake/reconcile | head -c 400; echo"
