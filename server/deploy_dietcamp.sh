#!/usr/bin/env bash
# 다이어트캠프 라인 배포(시보 배 892) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_dietcamp.sh
# 하는 일: /srv/www/{1_wellperion(링크),2_dietcamp} 를 만들고, cbo/dietcamp/*.html 을 2_dietcamp 로 올리고(저장소 전용 page_ping 줄은 뺀다),
# nginx 공개 location(auth_request 없음) 을 넣고 reload 한다. 끝에 https 200 을 확인한다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
SRC="3. 웰페리온 가이드/cbo/dietcamp"
TMP="$(mktemp -d)"
for f in "$SRC"/{before_after_*,drafts_*}.html; do
  grep -v 'page_ping.js' "$f" > "$TMP/$(basename "$f")"   # 저장소 전용 핑 스크립트 제거(서버엔 없는 경로)
done
$S "sudo mkdir -p /srv/www/2_dietcamp/img && sudo chown -R ec2-user:ec2-user /srv/www/2_dietcamp && [ -e /srv/www/1_wellperion ] || sudo ln -s /srv/erp/www /srv/www/1_wellperion"
$SCP "$TMP"/*.html $HOST:/srv/www/2_dietcamp/
$SCP "$SRC"/img/*.jpg $HOST:/srv/www/2_dietcamp/img/ 2>/dev/null || true   # 대표님 사진 웹 사본(브랜드가이드 v0.2 · 배 892)
$S "mkdir -p /srv/erp/faq/2_dietcamp"
if ! $S "test -f /srv/erp/faq/2_dietcamp/faq.json"; then
  $SCP "2. 브랜드_자료/10_다이어트캠프_브랜드가이드/07_FAQ/faq.json" $HOST:/srv/erp/faq/2_dietcamp/faq.json   # 첫 배포만 — 있으면 안 건드린다(배1036 관리자 API 편집 보호 · deploy_chat.sh 와 같은 원칙)
fi
$SCP "server/counselbot/tenants/2_dietcamp.json" $HOST:/srv/erp/faq/2_dietcamp/profile.json   # 프로필은 매번 갱신(관리자 API 가 안 건드리는 칸)
$SCP server/erp_api/dietcamp.nginx.conf $HOST:/tmp/dietcamp.conf
$S "sudo mv /tmp/dietcamp.conf /etc/nginx/conf.d/erp-locations/dietcamp.conf && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx && ls -la /srv/www /srv/www/2_dietcamp"
rm -rf "$TMP"
for f in "$SRC"/{before_after_*,drafts_*}.html; do
  b=$(basename "$f"); printf '%s = ' "$b"; curl -s -o /dev/null -w '%{http_code}
' "https://erp.wellperion.com/dietcamp/$b"
done
