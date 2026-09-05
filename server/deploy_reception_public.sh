#!/usr/bin/env bash
# 종합접수처 공개 쓰기 통로 배포(배 984 · 2026-09-05 시토) — 이 PC(git-bash)에서 실행.
#   bash server/deploy_reception_public.sh
# 하는 일: reception-public.nginx.conf 를 erp-locations 에 올리고 /srv/erp/uploads 디렉터리를 만든 뒤 reload.
# 선행: deploy_api.sh 로 api_reception.py(submit·lost·photo 라우트)가 먼저 올라가 있어야 한다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$SCP server/erp_api/reception-public.nginx.conf $HOST:/tmp/reception-public.conf
$S 'sudo mkdir -p /srv/erp/uploads/reception /srv/erp/uploads/lost-found && sudo chown -R ec2-user:ec2-user /srv/erp/uploads \
    && sudo mv /tmp/reception-public.conf /etc/nginx/conf.d/erp-locations/reception-public.conf \
    && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx'
curl -s -o /dev/null -w "공개 submit(빈 본문 400 예상) = %{http_code}\n" -X POST https://erp.wellperion.com/api/reception/submit -d '{}'
