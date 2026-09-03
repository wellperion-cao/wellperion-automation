#!/usr/bin/env bash
# 공개 접수 폼 이중기록 통로 배포(배 960) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_intake.sh
# 하는 일: api_intake.py·schema.sql 을 올리고 intake_log 표를 만들고, nginx 공개 location(auth_request 없음)+속도제한 zone 을 넣고,
# api.env 에 INTAKE_GAS_URL·INSTRUCTOR_GAS_URL 이 없으면 저장소 정본(폼이 지금 쓰는 주소)에서 채운 뒤 erp-api 를 재기동한다.
# 끝에 selftest 폼으로 1행 기록 + GAS 전달 skipped 를 확인한다. 실제 폼 주소는 바꾸지 않는다(시모 몫).
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."
G="3. 웰페리온 가이드"
INTAKE=$(grep -o "GAS_PROD = 'https://script.google.com/macros/s/[A-Za-z0-9_-]*/exec'" "$G/cmo/survey/wp_inquiry_form.html" | grep -o "https://[^']*")
INSTR=$(grep -o 'intake: "https://script.google.com/macros/s/[A-Za-z0-9_-]*/exec"' "$G/cmo/_api.js" | grep -o 'https://[^"]*')
test -n "$INTAKE" && test -n "$INSTR"

$SCP server/erp_api/api_intake.py $HOST:/srv/erp/api/
$SCP server/common/schema.sql $HOST:/srv/erp/common/
$SCP server/erp_api/intake.nginx.conf $HOST:/tmp/intake.conf
$SCP server/erp_api/intake-zone.nginx.conf $HOST:/tmp/erp-intake-zone.conf
$S "grep -q '^INTAKE_GAS_URL=' /srv/erp/api.env || echo 'INTAKE_GAS_URL=$INTAKE' >> /srv/erp/api.env;
    grep -q '^INSTRUCTOR_GAS_URL=' /srv/erp/api.env || echo 'INSTRUCTOR_GAS_URL=$INSTR' >> /srv/erp/api.env;
    cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print(\"schema ok\")' \
    && sudo mv /tmp/intake.conf /etc/nginx/conf.d/erp-locations/intake.conf \
    && sudo mv /tmp/erp-intake-zone.conf /etc/nginx/conf.d/erp-intake-zone.conf \
    && sudo systemctl restart erp-api && sleep 2 && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx && sleep 2 \
    && systemctl is-active erp-api \
    && curl -s -o /dev/null -w '무쿠키 selftest POST = %{http_code}\n' -X POST -H 'Content-Type: text/plain;charset=utf-8' \
         --data '{\"selftest\":true,\"name\":\"배포검증\"}' http://127.0.0.1/api/intake/selftest \
    && curl -s http://127.0.0.1:8001/api/intake/health && echo \
    && sudo -u postgres psql -d erp -Atc \"SELECT id, tenant_id, form, received_at, gas_status FROM intake_log ORDER BY id DESC LIMIT 3\""
