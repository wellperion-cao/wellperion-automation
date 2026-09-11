#!/usr/bin/env bash
# 지출품의(구매요청) 원장 배포 — 이 PC(git-bash)에서 실행.
# sync_proc.py·api_proc.py·schema.sql 을 올리고 cron 10분을 걸고 erp-api 를 재기동한다.
# 선행: /srv/erp/api.env 에 PROC_GAS_URL · SALES_GATE_PW (값은 저장소에 두지 않는다 — 서버 파일에만).
#   bash server/deploy_proc.sh
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
$SCP server/erp_api/sync_proc.py server/erp_api/api_proc.py $HOST:/srv/erp/api/
$SCP server/common/schema.sql $HOST:/srv/erp/common/
$SCP server/deploy_proc_remote.sh $HOST:/tmp/deploy_proc_remote.sh
$S 'bash /tmp/deploy_proc_remote.sh'
