#!/usr/bin/env bash
# 웰페리온 ERP 로그인 관문 배포 — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105 (배852).
#   bash server/deploy_auth.sh
# 하는 일: app.py·nginx 설정·systemd 유닛을 올리고 재기동. auth.env(비밀값)는 처음 한 번만 만들고 다시 덮지 않는다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$S 'mkdir -p /srv/erp/auth'
$SCP server/erp_auth/app.py $HOST:/srv/erp/auth/app.py
$SCP server/erp_auth/erp.nginx.conf $HOST:/tmp/erp.conf
$SCP server/erp_auth/erp-auth.service $HOST:/tmp/erp-auth.service

if ! $S 'test -f /srv/erp/auth.env'; then
  TOKEN=$(grep '^TELEGRAM_BOT_TOKEN=' telegram_bot/.env | cut -d= -f2- | tr -d '"'"'"' ')
  ADMIN_PW=$(C:/Python314/python.exe -c "import secrets;print(secrets.token_urlsafe(9))")
  $S "umask 077; cat > /srv/erp/auth.env <<EOF
ERP_JWT_SECRET=$(C:/Python314/python.exe -c "import secrets;print(secrets.token_hex(32))")
ERP_ADMIN_EMAIL=cao@wellperion.com
ERP_ADMIN_PW=$ADMIN_PW
TG_BOT_TOKEN=$TOKEN
TG_CHAT_ID=8254867551
EOF"
  echo "ADMIN_PW=$ADMIN_PW"      # 첫 관리자 비밀번호 — 이 줄만 GM 께 따로 전한다
fi

$S 'sudo mv /tmp/erp.conf /etc/nginx/conf.d/erp.conf && sudo mv /tmp/erp-auth.service /etc/systemd/system/erp-auth.service \
    && sudo systemctl daemon-reload && sudo systemctl enable --now erp-auth >/dev/null && sudo systemctl restart erp-auth \
    && sleep 2 && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx \
    && systemctl is-active erp-auth && curl -s -o /dev/null -w "check 무쿠키 = %{http_code}\n" http://127.0.0.1:8000/auth/check'
