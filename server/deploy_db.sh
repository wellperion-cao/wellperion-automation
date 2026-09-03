#!/usr/bin/env bash
# 웰페리온 ERP 서버 DB(PostgreSQL) 배포 — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105 (장기 결정 1·2·3·4·9).
#   bash server/deploy_db.sh          # 그 다음 deploy_auth.sh · deploy_api.sh 로 두 서비스를 새 코드로 재기동
# 하는 일: common/ 을 올리고 ①PostgreSQL 설치·기동(db.env 는 처음 한 번만 생성) ②schema ③SQLite→PG 이관(파일은 .bak 으로)
#          ④백업 스크립트 + cron(KST 03:00 → S3). S3 버킷·인스턴스 역할은 scripts/aws_bootstrap.py backup 이 먼저 만들어 둔다.
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
S="ssh -i $KEY -o StrictHostKeyChecking=accept-new $HOST"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

$S 'mkdir -p /srv/erp/common'
$SCP server/common/db.py server/common/schema.sql server/common/migrate_sqlite_to_pg.py \
     server/common/setup_postgres.sh server/common/erp-pg-backup.sh $HOST:/srv/erp/common/
$S 'bash /srv/erp/common/setup_postgres.sh \
    && python3 /srv/erp/common/migrate_sqlite_to_pg.py \
    && sudo install -m 755 /srv/erp/common/erp-pg-backup.sh /usr/local/bin/erp-pg-backup.sh \
    && printf "%s\n" "CRON_TZ=Asia/Seoul" \
         "0 3 * * * ec2-user /usr/local/bin/erp-pg-backup.sh >> /srv/erp/backup.log 2>&1" \
       | sudo tee /etc/cron.d/erp-pg-backup >/dev/null \
    && echo "DB 배포 완료 — 이제 deploy_auth.sh · deploy_api.sh"'
