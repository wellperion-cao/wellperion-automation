#!/usr/bin/env bash
# 전환 퍼널 첫 단 측정 API 배포(배1034) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_track.sh
# 하는 일: api_track.py·schema.sql 을 올리고 track_events 표를 만들고, 공개 POST location(로그인 없이,
# intake 존 재사용 — intake 존 자체는 deploy_intake.sh 가 이미 심어둠)을 넣고, 90일 지난 행을 지우는
# 일일 cron 을 걸고 erp-api 를 재기동한다. 끝에 view/click POST + summary 집계 + 봇 UA 제외 + 잘못된 event
# 400 을 실측하고, 테스트로 쌓인 행을 지운다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$SCP server/erp_api/api_track.py server/erp_api/prune_track.py $HOST:/srv/erp/api/
$SCP server/common/schema.sql $HOST:/srv/erp/common/
$SCP server/erp_api/track.nginx.conf $HOST:/tmp/track.conf

$S "cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print(\"schema ok — track_events\")' \
    && sudo mv /tmp/track.conf /etc/nginx/conf.d/erp-locations/track.conf \
    && printf 'CRON_TZ=Asia/Seoul\n20 3 * * * ec2-user /usr/bin/python3 /srv/erp/api/prune_track.py >> /srv/erp/prune_track.log 2>&1\n' \
       | sudo tee /etc/cron.d/erp-track-prune >/dev/null \
    && sudo chmod 644 /etc/cron.d/erp-track-prune \
    && sudo systemctl restart erp-api && sleep 2 && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx && sleep 2 \
    && systemctl is-active erp-api"

echo "--- view POST (무쿠키) ---"
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"event":"view","page":"/ko/inquiry","sid":"deploycheck1"}' \
  https://erp.wellperion.com/api/track; echo
echo "--- click POST (무쿠키) ---"
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"event":"click","page":"/ko/inquiry","target":"inquiry_btn","sid":"deploycheck1"}' \
  https://erp.wellperion.com/api/track; echo
echo "--- 봇 UA (is_bot=true 로 저장 — summary 에서 빠져야 정상) ---"
curl -s -X POST -H 'Content-Type: application/json' -A 'Googlebot/2.1' \
  --data '{"event":"view","page":"/ko/inquiry","sid":"deploycheck_bot"}' \
  https://erp.wellperion.com/api/track; echo
echo "--- 없는 event → 400 ---"
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' \
  --data '{"event":"nope"}' https://erp.wellperion.com/api/track
echo "--- summary(로그인 없이 → 401/302 기대) ---"
curl -s -o /dev/null -w '%{http_code}\n' 'https://erp.wellperion.com/api/track/summary?group=page'
