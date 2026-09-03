#!/usr/bin/env bash
# ERP PostgreSQL 일일 백업 — pg_dump → S3 wellperion-erp-backup (30일 수명주기 · 장기 결정 9).
# 설치 위치 /usr/local/bin/erp-pg-backup.sh · cron /etc/cron.d/erp-pg-backup (KST 03:00) · 권한 = EC2 인스턴스 역할.
set -euo pipefail
. /srv/erp/db.env
F=/tmp/erp-$(TZ=Asia/Seoul date +%Y%m%d-%H%M).sql.gz
pg_dump "$ERP_DB_URL" | gzip > "$F"
aws s3 cp --only-show-errors "$F" "s3://wellperion-erp-backup/erp/$(basename "$F")" --region ap-northeast-2
echo "$(date '+%F %T') 백업 완료 erp/$(basename "$F") $(stat -c %s "$F")B"
rm -f "$F"
