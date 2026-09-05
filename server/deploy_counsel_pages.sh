#!/usr/bin/env bash
# 상담봇 고객 페이지 배포(배1036) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_counsel_pages.sh
# 하는 일: counsel/index.html(공통 템플릿) 을 다캠·스포짐 폴더에 올리고(1_wellperion 은 ERP 루트 자체가 git
# 5분 동기화라 scp 안 함 — 커밋·푸시만 하면 뜬다), 공개 nginx location 2개(counsel-public·spogym)를 넣고 reload.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
PAGE="3. 웰페리온 가이드/counsel/index.html"

$S "sudo mkdir -p /srv/www/3_spogym && sudo chown ec2-user:ec2-user /srv/www/3_spogym && mkdir -p /srv/www/2_dietcamp/counsel /srv/www/3_spogym/counsel"
$SCP "$PAGE" "$HOST:/srv/www/2_dietcamp/counsel/index.html"
$SCP "$PAGE" "$HOST:/srv/www/3_spogym/counsel/index.html"
$SCP server/erp_api/counsel-public.nginx.conf $HOST:/tmp/counsel-public.conf
$SCP server/erp_api/spogym.nginx.conf $HOST:/tmp/spogym.conf
$S "sudo mv /tmp/counsel-public.conf /etc/nginx/conf.d/erp-locations/counsel-public.conf \
    && sudo mv /tmp/spogym.conf /etc/nginx/conf.d/erp-locations/spogym.conf \
    && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx"

echo "--- 다캠·스포짐(즉시) ---"
for p in "dietcamp/counsel/" "spogym/counsel/"; do
  printf '%s = ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' "https://erp.wellperion.com/$p"
done
echo "--- 웰페리온(git 5분 동기화 뒤 200 — 지금은 404 가 정상일 수 있다) ---"
curl -s -o /dev/null -w 'counsel/ = %{http_code}\n' "https://erp.wellperion.com/counsel/"
