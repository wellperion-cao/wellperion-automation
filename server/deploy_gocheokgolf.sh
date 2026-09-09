#!/usr/bin/env bash
# 고척 QA골프스튜디오 라인 배포(시보 · GM 지시 2026-09-09) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_gocheokgolf.sh
# 하는 일: /srv/www/3_gocheokgolf 를 만들고 cbo/gocheokgolf/*.html + img/*.jpg 를 올린 뒤,
#          nginx 공개 location 을 넣고 reload 한다. 고객 학습용 정리 데이터는 /srv/erp/clients/3_gocheokgolf/ 로 올린다.
#          끝에 https 200 을 확인한다. 구조는 deploy_dietcamp.sh 와 같다(새 관문을 만들지 않는다).
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
SRC="3. 웰페리온 가이드/cbo/gocheokgolf"
TMP="$(mktemp -d)"
for f in "$SRC"/*.html; do
  grep -v 'page_ping.js' "$f" > "$TMP/$(basename "$f")"   # 저장소 전용 핑 스크립트 제거
done
$S "sudo mkdir -p /srv/www/3_gocheokgolf/img && sudo chown -R ec2-user:ec2-user /srv/www/3_gocheokgolf && mkdir -p /srv/erp/clients/3_gocheokgolf"
$SCP "$TMP"/*.html $HOST:/srv/www/3_gocheokgolf/
$SCP "$SRC"/img/*.jpg $HOST:/srv/www/3_gocheokgolf/img/
$SCP "2. 브랜드_자료/11_고척골프_조재오부장님/client.json" $HOST:/srv/erp/clients/3_gocheokgolf/client.json
$SCP server/erp_api/gocheokgolf.nginx.conf $HOST:/tmp/gocheokgolf.conf
$S "sudo mv /tmp/gocheokgolf.conf /etc/nginx/conf.d/erp-locations/gocheokgolf.conf && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx"
rm -rf "$TMP"
for f in "$SRC"/*.html; do
  b=$(basename "$f"); printf '%s = ' "$b"; curl -s -o /dev/null -w '%{http_code}\n' "https://erp.wellperion.com/gocheokgolf/$b"
done
