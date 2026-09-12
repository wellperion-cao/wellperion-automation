#!/usr/bin/env bash
# 범용 업체 사이트 배포 — aws요청.json 한 장으로 /srv/www/{id}+nginx location+https 검증.
# 사용법: bash server/deploy_tenant.sh <aws요청.json 경로>
# aws요청.json 스키마:
#   { "tenant_id": "3_foo", "site_dir": "3. 웰페리온 가이드/cbo/foo",
#     "public_url": "/foo/", "faq_dir": "경로/선택" }
# nginx conf 는 이 스크립트가 템플릿으로 생성 — 업체별 *.nginx.conf 추가 불필요.
set -euo pipefail

REQ="${1:-}"
[[ -n "$REQ" ]] || { echo "Usage: $0 <aws요청.json>" >&2; exit 1; }

HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

TENANT_ID=$(python -c "import json; d=json.load(open('$REQ')); print(d['tenant_id'])")
SITE_DIR=$(python -c "import json; d=json.load(open('$REQ')); print(d['site_dir'])")
PUBLIC_URL=$(python -c "import json; d=json.load(open('$REQ')); print(d['public_url'])")
FAQ_DIR=$(python -c "import json; d=json.load(open('$REQ')); print(d.get('faq_dir',''))")

SLUG="${PUBLIC_URL#/}"; SLUG="${SLUG%/}"

TMP="$(mktemp -d)"
for f in "$SITE_DIR"/*.html; do
  [[ -e "$f" ]] || continue
  grep -v 'page_ping.js' "$f" > "$TMP/$(basename "$f")"
done

$S "sudo mkdir -p /srv/www/${TENANT_ID}/img && sudo chown -R ec2-user:ec2-user /srv/www/${TENANT_ID}"
$SCP "$TMP"/*.html $HOST:/srv/www/${TENANT_ID}/ 2>/dev/null || true
$SCP "$SITE_DIR"/img/*.jpg $HOST:/srv/www/${TENANT_ID}/img/ 2>/dev/null || true

if [[ -n "$FAQ_DIR" ]]; then
  $S "mkdir -p /srv/erp/faq/${TENANT_ID}"
  if ! $S "test -f /srv/erp/faq/${TENANT_ID}/faq.json"; then
    $SCP "${FAQ_DIR}/faq.json" $HOST:/srv/erp/faq/${TENANT_ID}/faq.json 2>/dev/null || true
  fi
fi

cat > "$TMP/${SLUG}.conf" <<NGINX
# 자동생성 — deploy_tenant.sh (${TENANT_ID})
location ^~ /${SLUG}/ {
    alias /srv/www/${TENANT_ID}/;
    index index.html;
    try_files \$uri \$uri/ =404;
    add_header X-Robots-Tag "noindex" always;
}
NGINX

$SCP "$TMP/${SLUG}.conf" $HOST:/tmp/${SLUG}.conf
$S "sudo mv /tmp/${SLUG}.conf /etc/nginx/conf.d/erp-locations/${SLUG}.conf \
    && sudo nginx -t 2>&1 | tail -1 \
    && sudo systemctl reload nginx \
    && ls -la /srv/www/${TENANT_ID}"
rm -rf "$TMP"

printf 'index.html = '; curl -s -o /dev/null -w '%{http_code}\n' "https://erp.wellperion.com/${SLUG}/index.html"
