#!/usr/bin/env bash
# 상용 3환경 중 라이브가 아닌 두 벌(alpha·beta)을 세운다 — 이 PC(git-bash)에서 실행.
#   bash server/deploy_env.sh beta      배포 전 시험 환경 (127.0.0.1:8002 · https://erp.wellperion.com/beta/api/)
#   bash server/deploy_env.sh alpha     반복 개발 환경   (127.0.0.1:8003 · https://erp.wellperion.com/alpha/api/)
#
# 왜 따로 세우나 — 날고 있는 비행기를 고치지 말고, 한 대 더 만들어 손님 없이 이착륙해 본 뒤 태운다.
#   · 코드가 따로다   /srv/erp/{env}/api  ← 라이브 /srv/erp/api 와 별개. 여기서 먼저 돌려 보고 라이브에 올린다.
#   · 자료가 따로다   DB erp_{env}        ← 라이브 erp 를 건드리지 않는다.
#   · 손님이 없다     밖으로 나가는 주소(구글 시트·브로제이·텔레그램 방)를 이 환경엔 아예 안 준다.
#                     그래서 여기서 무슨 짓을 해도 실무진 시트에 한 줄도 안 적힌다.
#   · 원본 스위치가 server 하나다 — 이관이 끝난 세상을 미리 살아 보는 자리다.
# 라이브 배포는 종전대로 server/deploy_api.sh 다. 이 스크립트는 라이브를 절대 건드리지 않는다.
set -euo pipefail
ENV="${1:-}"
case "$ENV" in
  beta)  PORT=8002 ;;
  alpha) PORT=8003 ;;
  *) echo "쓰는 법: bash server/deploy_env.sh {alpha|beta}" >&2; exit 2 ;;
esac

HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
R="/srv/erp/$ENV"
cd "$(dirname "$0")/.."

echo "[1/6] 코드 올리기 → $R"
$S "mkdir -p $R/api $R/common $R/status"
$SCP server/erp_api/*.py $HOST:$R/api/
$SCP scripts/diet_camp_agent.py scripts/close_days.py $HOST:$R/api/   # api_chat 이 부르는 stdlib 모듈 두 개(라이브도 같은 자리)
$SCP server/common/db.py server/common/schema.sql $HOST:$R/common/

echo "[2/6] 자료칸 만들기 → DB erp_$ENV"
$S "sudo -u postgres psql -tAc \"select 1 from pg_database where datname='erp_$ENV'\" | grep -q 1 \
    || sudo -u postgres psql -c 'CREATE DATABASE erp_$ENV OWNER erp'"
# 비밀번호는 서버 안에서만 옮긴다 — 이 PC 셸에 찍히지 않는다.
$S "umask 077; sed 's#/erp\$#/erp_$ENV#' /srv/erp/db.env > $R/db.env"
$S "cd $R/common && ERP_DB_ENV=$R/db.env python3 -c 'import db; c=db.connect(); db.init_schema(c)'"

echo "[3/6] 환경파일 — 밖으로 나가는 주소는 안 준다"
# 라이브 api.env 에서 외부 목적지(…_URL · …_CHAT_ID)만 걷어내고 나머지 설정은 그대로 물려준다.
# 걷어내는 이유: 하나라도 남으면 시험 요청이 진짜 구글 시트·진짜 카톡방에 닿는다. 그 순간 빈 비행기가 아니다.
# ★ERP_API_ENV 도 같이 박는다(2026-09-12 실측) — api_misc.py 가 뜰 때 부르는 load_env() 는 이 변수가 없으면
#   기본값 /srv/erp/api.env(라이브)를 읽어 os.environ 에 라이브 GAS 주소를 통째로 넣는다. 그래서 이 줄이 없던
#   동안 beta 의 dual 액션이 진짜 업무 SSOT 시트에 행을 만들었다(시험 행 1건 즉시 삭제). 빈 비행기가 아니었다.
$S "umask 077; { \
      echo 'ERP_ENV=$ENV'; \
      echo 'ERP_PORT=$PORT'; \
      echo 'ERP_DB_ENV=$R/db.env'; \
      echo 'ERP_ORIGIN_SWITCH=$R/status/origin_switch.json'; \
      echo 'ERP_API_ENV=$R/api.env'; \
      grep -v -E '^[A-Z0-9_]*(_URL|_CHAT_ID)=' /srv/erp/api.env; \
    } > $R/api.env"
$S "if [ ! -f $R/status/origin_switch.json ]; then printf '%s\n' '{' '  \"_\": \"빈 비행기 — 서버가 유일 원본. 이 환경엔 구글 시트로 나가는 주소가 없어서 되밀기도 없다.\",' '  \"default\": \"server\"' '}' > $R/status/origin_switch.json; echo '원본 스위치 새로 만듦'; else echo '원본 스위치 이미 있음 — 그대로 둔다'; fi"

echo "[4/6] 서비스 등록 · 기동"
$SCP "server/erp_api/erp-api@.service" $HOST:/tmp/erp-api@.service
$S "sudo mv /tmp/erp-api@.service /etc/systemd/system/erp-api@.service \
    && sudo systemctl daemon-reload \
    && sudo systemctl enable --now erp-api@$ENV >/dev/null \
    && sudo systemctl restart erp-api@$ENV && sleep 2 && systemctl is-active erp-api@$ENV"

echo "[5/6] 주소 열기 → /$ENV/api/"
$S "sudo tee /etc/nginx/conf.d/erp-locations/env-$ENV.conf >/dev/null <<'N'
# /$ENV/api/... → 127.0.0.1:$PORT/api/...  ($ENV 환경 · 라이브와 코드·자료가 완전히 별개)
# 로그인 관문은 라이브와 똑같이 건다 — 관문 동작까지 같아야 시험한 의미가 있다.
location ^~ /$ENV/api/ {
    auth_request /auth/check;
    auth_request_set \$erp_user \$upstream_http_x_erp_user;
    client_max_body_size 10m;
    proxy_pass http://127.0.0.1:$PORT/api/;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-For \$remote_addr;
    proxy_set_header X-Erp-User \$erp_user;
}
N
    sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx"

echo "[6/6] 확인"
$S "curl -s -o /dev/null -w '$ENV 내부 health = %{http_code}\n' http://127.0.0.1:$PORT/api/health; \
    curl -s -o /dev/null -w '라이브 health(안 건드렸는지) = %{http_code}\n' http://127.0.0.1:8001/api/health; \
    sudo -u postgres psql -tAc \"select count(*) from pg_database where datname in ('erp','erp_$ENV')\" | xargs -I{} echo '자료칸 {}개(라이브+$ENV)'"
