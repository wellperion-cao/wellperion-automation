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

$S 'mkdir -p /srv/erp/auth /srv/erp/common'
$SCP server/erp_auth/app.py server/erp_auth/account_perms.json server/erp_auth/admin.html $HOST:/srv/erp/auth/   # account_perms.json=계정별 권한 정본(배951) · admin.html=관리자 콘솔(배1076, app.py 가 같은 폴더에서 읽는다)
$SCP server/common/db.py server/common/schema.sql $HOST:/srv/erp/common/      # DB 접속은 common/db.py 하나 (db.env 는 deploy_db.sh 가 만든다)
$SCP server/erp_auth/erp-auth.service $HOST:/tmp/erp-auth.service
if $S 'sudo test -d /etc/letsencrypt/live/erp.wellperion.com'; then   # /etc/letsencrypt/live 는 root 만 읽는다 — sudo 없이는 늘 거짓이라 443 블록을 덮어버린다
  echo "certbot 이 이미 손댄 erp.conf — 덮지 않음(HTTPS 443 블록 보존)"
else
  $SCP server/erp_auth/erp.nginx.conf $HOST:/tmp/erp.conf
fi

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

$S 'test -f /tmp/erp.conf && sudo mv -f /tmp/erp.conf /etc/nginx/conf.d/erp.conf; sudo mv /tmp/erp-auth.service /etc/systemd/system/erp-auth.service \
    && sudo systemctl daemon-reload && sudo systemctl enable --now erp-auth >/dev/null && sudo systemctl restart erp-auth \
    && sleep 2 && sudo nginx -t 2>&1 | tail -1 && sudo systemctl reload nginx \
    && systemctl is-active erp-auth && curl -s -o /dev/null -w "check 무쿠키 = %{http_code}\n" http://127.0.0.1:8000/auth/check'
