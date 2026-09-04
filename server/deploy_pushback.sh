#!/usr/bin/env bash
# 서버 원본 전환 장치 배포(배 960 레인 J) — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105.
#   bash server/deploy_pushback.sh
# 하는 일: 스위치(origin_switch.py)·되밀기 워커(pushback.py)·고친 관문 2종을 올리고, 원장에 되밀기 칸을 붙이고(IF NOT EXISTS),
# 스위치 파일이 없으면 전부 dual 로 깔고, 1분 cron 을 걸고, erp-api 를 재기동한 뒤 자체점검·끝단점검·헬스를 보여준다.
# ★전환은 이 스크립트가 하지 않는다 — 스위치는 전부 dual 로 남는다(첫 전환 = 09-08 문의 폼 · 사람이 한 줄 고친다).
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"

R="$(dirname "$0")/.."
$SCP "$R/server/erp_api/origin_switch.py" "$R/server/erp_api/pushback.py" \
     "$R/server/erp_api/api_intake.py" "$R/server/erp_api/api_write.py" $HOST:/srv/erp/api/
$SCP "$R/server/erp_api/origin_switch.example.json" $HOST:/srv/erp/api/
$SCP "$R/server/common/schema.sql" $HOST:/srv/erp/common/

$S "set -e
    cd /srv/erp/common && /usr/bin/python3 -c 'import db; c=db.connect(); db.init_schema(c); print(\"schema ok — 되밀기 칸 3개\")'
    sudo mkdir -p /srv/erp/status && sudo chown ec2-user:ec2-user /srv/erp/status
    test -f /srv/erp/status/origin_switch.json || cp /srv/erp/api/origin_switch.example.json /srv/erp/status/origin_switch.json
    printf 'CRON_TZ=Asia/Seoul\n* * * * * ec2-user /usr/bin/python3 /srv/erp/api/pushback.py >> /srv/erp/pushback.log 2>&1\n' \
      | sudo tee /etc/cron.d/erp-pushback >/dev/null
    sudo chmod 644 /etc/cron.d/erp-pushback
    cd /srv/erp/api
    /usr/bin/python3 origin_switch.py
    /usr/bin/python3 api_write.py
    /usr/bin/python3 pushback.py --selftest
    sudo systemctl restart erp-api && sleep 3 && systemctl is-active erp-api
    # cron 은 EnvironmentFile 없이 도니 api.env 를 워커가 직접 읽어야 한다 — 못 읽으면 되밀기가 전부 no-url 이 된다.
    /usr/bin/python3 -c \"import os,sys; sys.path.insert(0,'/srv/erp/api'); from sync_inquiries import load_env; load_env(); \
        print('api.env 읽기 =', all(k in os.environ for k in ('INTAKE_GAS_URL','RECEPTION_EXEC_URL','TODO_GAS_URL')))\"
    /usr/bin/python3 pushback.py --e2e
    echo '— 스위치(전부 dual 이어야 정상) —'; cat /srv/erp/status/origin_switch.json | /usr/bin/python3 -c 'import json,sys; d=json.load(sys.stdin); print({k:v for k,v in d.items() if not k.startswith(\"_\")})'
    echo '— 헬스 —'; curl -s http://127.0.0.1:8001/api/intake/health; echo"
