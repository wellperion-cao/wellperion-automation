#!/usr/bin/env bash
# 소형 GAS 읽기 거울 배포(배 960 #9) — 이 PC(git-bash)에서 실행.
# sync_misc.py·api_misc.py·schema.sql 을 올리고 cron 5분을 걸고 erp-api 를 재기동한다.
# 선행: /srv/erp/api.env 에 RENEWAL_GAS_URL 이 있어야 한다(값은 저장소에 두지 않는다 — 서버 파일에만).
#       없으면 remote 쪽이 이름을 대며 멈춘다.
#   bash server/deploy_misc.sh
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
$SCP server/erp_api/sync_misc.py server/erp_api/api_misc.py $HOST:/srv/erp/api/
$SCP server/common/schema.sql $HOST:/srv/erp/common/
$SCP server/deploy_misc_remote.sh $HOST:/tmp/deploy_misc_remote.sh
$S 'bash /tmp/deploy_misc_remote.sh'
