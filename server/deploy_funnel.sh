#!/usr/bin/env bash
# 시모 퍼널 4액션 거울 배포(배 960) — 이 PC(git-bash)에서 실행. sync_funnel.py·api_funnel.py·schema.sql 을 올리고 cron 5분을 걸고 erp-api 를 재기동한다.
#   bash server/deploy_funnel.sh
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
$SCP server/erp_api/sync_funnel.py server/erp_api/api_funnel.py $HOST:/srv/erp/api/
$SCP server/common/schema.sql $HOST:/srv/erp/common/
$SCP server/deploy_funnel_remote.sh $HOST:/tmp/deploy_funnel_remote.sh
$S 'bash /tmp/deploy_funnel_remote.sh'
