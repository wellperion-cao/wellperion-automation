#!/usr/bin/env bash
# AEO 채팅봇 백엔드 배포(배1018 · 시토) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_chat.sh
# 하는 일: api_chat.py + diet_camp_agent.py(금지어 관문 재사용) 를 /srv/erp/api/ 에 올리고,
#   센터별 faq.json 을 없을 때만 /srv/erp/faq/{tenant}/ 에 심고(있으면 안 건드린다 — 이미 채워둔 내용 보호.
#   /srv/www 가 아니라 /srv/erp/faq 인 이유 = /srv/www/1_wellperion 은 git 저장소 체크아웃 심볼릭 링크라
#   그 안에 쓰면 서버 워처와 충돌한다),
#   nginx 공개 location(intake 와 같은 zone) 을 넣고 erp-api 재기동 뒤 4가지 curl 로 실측한다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$SCP server/erp_api/api_chat.py $HOST:/srv/erp/api/
$SCP scripts/diet_camp_agent.py $HOST:/srv/erp/api/   # FORBIDDEN(금액·계약 금지어) 재사용 — 이 파일만 stdlib 로 끝난다
$SCP server/erp_api/chat.nginx.conf $HOST:/tmp/chat.conf
$SCP "3. 웰페리온 가이드/cbo/model/chat_widget.html" $HOST:/srv/www/2_dietcamp/chat_widget.html   # 위젯 — 다캠 페이지와 같은 origin

for t in "1_wellperion" "2_dietcamp"; do
  $S "mkdir -p '/srv/erp/faq/$t'"
  if ! $S "test -f '/srv/erp/faq/$t/faq.json'"; then
    $SCP "server/erp_api/seed_faq/$t.json" "$HOST:/srv/erp/faq/$t/faq.json"
  fi
done

$S 'sudo mv /tmp/chat.conf /etc/nginx/conf.d/erp-locations/chat.conf \
    && sudo systemctl restart erp-api && sleep 2 && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx && sleep 2 \
    && systemctl is-active erp-api'

# git-bash(Windows) 로 curl --data 에 한글을 인라인으로 주면 로컬 코드페이지가 끼어들어 깨진다 —
# 임시 파일에 UTF-8 로 적고 --data-binary @file 로 보낸다(서버 쪽 ssh curl 은 이 문제가 없다).
TMP="$(mktemp -d)"
printf '{"q":"운영 시간은 어떻게 되나요"}' > "$TMP/q1.json"
printf '{"q":"오늘 저녁 메뉴 추천해 주세요"}' > "$TMP/q2.json"
printf '{"q":"지금 카드로 결제하고 싶어요 얼마인가요"}' > "$TMP/q3.json"
echo "--- 매칭 질문 ---"
curl -s -X POST -H 'Content-Type: application/json' --data-binary @"$TMP/q1.json" \
  https://erp.wellperion.com/api/chat/1_wellperion | cut -c1-150; echo
echo "--- 비매칭 질문 ---"
curl -s -X POST -H 'Content-Type: application/json' --data-binary @"$TMP/q2.json" \
  https://erp.wellperion.com/api/chat/1_wellperion | cut -c1-150; echo
echo "--- 금지어(결제) ---"
curl -s -X POST -H 'Content-Type: application/json' --data-binary @"$TMP/q3.json" \
  https://erp.wellperion.com/api/chat/1_wellperion | cut -c1-150; echo
echo "--- 없는 tenant ---"
curl -s -o /dev/null -w '%{http_code}\n' https://erp.wellperion.com/api/chat/3_none -X POST \
  -H 'Content-Type: application/json' --data '{"q":"x"}'
rm -rf "$TMP"
