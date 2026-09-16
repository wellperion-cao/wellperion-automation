#!/usr/bin/env bash
# 다이어트캠프 라인 배포(시보 배 892) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_dietcamp.sh
# 하는 일: /srv/www/{1_wellperion(링크),2_dietcamp} 를 만들고, cbo/dietcamp/*.html + dc.css 를 2_dietcamp 로 올리고(저장소 전용 page_ping 줄은 뺀다),
# nginx 공개 location(auth_request 없음) 을 넣고 reload 한다. 끝에 https 200 을 확인한다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
SRC="3. 웰페리온 가이드/cbo/dietcamp"            # 둘러보기(tour.html · tour/frames)만 여기 남았다
DOCS="3. 웰페리온 가이드/erp/admin/dietcamp"     # 소개서·브랜드·전략·초안·Before/After·dc.css·img — 2026-09-16 웰리 배 2513 이관(옛 자리는 meta refresh 스텁이라 그대로 올리면 손님 화면이 깨진다)
TMP="$(mktemp -d)"
for f in "$DOCS"/{before_after_*,drafts_*,intro,brand,strategy}.html "$SRC"/tour.html; do
  grep -v 'page_ping.js' "$f" > "$TMP/$(basename "$f")"   # 저장소 전용 핑 스크립트 제거(서버엔 없는 경로)
done
# 손님이 보는 두 장(홈·문의 폼) + 대표님이 보는 한 장(문의 관리).
# 손님용 「내 문의 현황」은 2026-09-14 GM 지시로 뺐다 — 다캠에는 필요 없다.
# 이 셋은 cbo/dietcamp(내부 열람)가 아니라 공개 폴더 "3. 웰페리온 가이드/dietcamp/" 에 있다.
PUB="3. 웰페리온 가이드/dietcamp"
for f in "$PUB"/{index,inquiry,manage}.html; do
  [ -f "$f" ] && grep -v 'page_ping.js' "$f" > "$TMP/$(basename "$f")"
done
$S "sudo mkdir -p /srv/www/2_dietcamp/img && sudo chown -R ec2-user:ec2-user /srv/www/2_dietcamp && [ -e /srv/www/1_wellperion ] || sudo ln -s /srv/erp/www /srv/www/1_wellperion"
$SCP "$TMP"/*.html $HOST:/srv/www/2_dietcamp/
$SCP "$DOCS/dc.css" $HOST:/srv/www/2_dietcamp/dc.css
$SCP "$DOCS"/img/*.jpg "$DOCS"/img/*.png $HOST:/srv/www/2_dietcamp/img/ 2>/dev/null || true   # 대표님 사진 웹 사본(브랜드가이드 v0.2 · 배 892)
# 둘러보기(tour.html) 프레임 740장 — 저장소 밖(.gitignore) · 영상에서 다시 뽑는다(tour.html 머리 주석) · tar 로 한 번에(2026-09-15 시보)
if [ -d "$SRC/tour/frames" ]; then tar -C "$SRC" -cf - tour | $S "mkdir -p /srv/www/2_dietcamp && tar -C /srv/www/2_dietcamp -xf -"; fi
$S "mkdir -p /srv/erp/faq/2_dietcamp"
if ! $S "test -f /srv/erp/faq/2_dietcamp/faq.json"; then
  $SCP "2. 브랜드_자료/10_다이어트캠프_브랜드가이드/07_FAQ/faq.json" $HOST:/srv/erp/faq/2_dietcamp/faq.json   # 첫 배포만 — 있으면 안 건드린다(배1036 관리자 API 편집 보호 · deploy_chat.sh 와 같은 원칙)
fi
$SCP "server/counselbot/tenants/2_dietcamp.json" $HOST:/srv/erp/faq/2_dietcamp/profile.json   # 프로필은 매번 갱신(관리자 API 가 안 건드리는 칸)
$SCP server/erp_api/dietcamp.nginx.conf $HOST:/tmp/dietcamp.conf
$S "sudo mv /tmp/dietcamp.conf /etc/nginx/conf.d/erp-locations/dietcamp.conf && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx && ls -la /srv/www /srv/www/2_dietcamp"
rm -rf "$TMP"
for f in "$DOCS"/{before_after_*,drafts_*,intro,brand,strategy}.html "$SRC"/tour.html "$DOCS/dc.css"; do
  b=$(basename "$f"); printf '%s = ' "$b"; curl -s -o /dev/null -w '%{http_code}
' "https://erp.wellperion.com/dietcamp/$b"
done
