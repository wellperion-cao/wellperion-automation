#!/usr/bin/env bash
# 웰페리온 랩스 공개 라인 배포(시보 요청 2026-09-15) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_labs.sh
# 하는 일: 회사 소개서 한 장(erp/admin/company_intro.html)을 /srv/www/4_labs/intro.html 로 올리고, 그 장이 무는 css 2개를
# 같은 폴더 사본으로 두며(관리 화면 css 는 로그인 벽 뒤라 그대로 못 쓴다), nginx 공개 location 을 넣고 reload 한다.
# 원본은 저장소 HEAD 판만 올린다(작업트리 미커밋 금지 · 2026-09-14 배포 사고 규칙). 끝에 https 200 을 확인한다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
TMP="$(mktemp -d)"; mkdir -p "$TMP/assets"
git show "HEAD:3. 웰페리온 가이드/erp/admin/company_intro.html" \
  | grep -v 'page_ping.js' \
  | sed 's#href="\.\./\.\./assets/wp-ui\.css"#href="assets/wp-ui.css"#' > "$TMP/intro.html"
git show "HEAD:3. 웰페리온 가이드/erp/admin/platform_brand.css" > "$TMP/platform_brand.css"
git show "HEAD:3. 웰페리온 가이드/assets/wp-ui.css" > "$TMP/assets/wp-ui.css"
$S "sudo mkdir -p /srv/www/4_labs/assets && sudo chown -R ec2-user:ec2-user /srv/www/4_labs"
$SCP "$TMP/intro.html" "$TMP/platform_brand.css" $HOST:/srv/www/4_labs/
$SCP "$TMP/assets/wp-ui.css" $HOST:/srv/www/4_labs/assets/
$SCP server/erp_api/labs.nginx.conf $HOST:/tmp/labs.conf
$S "sudo cp /tmp/labs.conf /etc/nginx/conf.d/erp-locations/labs.conf && sudo nginx -t && sudo systemctl reload nginx"
for u in /labs/intro.html /labs/platform_brand.css /labs/assets/wp-ui.css; do
  printf '%s ' "$u"; curl -s -o /dev/null -w '%{http_code}\n' "https://erp.wellperion.com$u"
done
rm -rf "$TMP"
