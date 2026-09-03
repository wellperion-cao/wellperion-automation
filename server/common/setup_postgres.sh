#!/usr/bin/env bash
# 서버 안에서 실행(deploy_db.sh 가 ssh 로 부른다) — PostgreSQL 설치·기동·DB/계정 생성·db.env. 전부 멱등.
# 로컬 전용(listen localhost 기본값) · shared_buffers 는 기본 128MB(2GB 서버 안쪽) · 워드프레스 MariaDB 는 건드리지 않는다.
set -euo pipefail
ENV=/srv/erp/db.env
PGDATA=/var/lib/pgsql/data

rpm -q postgresql17-server >/dev/null 2>&1 || sudo dnf install -y -q postgresql17-server postgresql17
[ -f $PGDATA/PG_VERSION ] || sudo postgresql-setup --initdb >/dev/null
# 127.0.0.1 접속을 ident → 비밀번호(scram) 로. 이미 바뀌었으면 sed 가 아무것도 안 한다.
sudo sed -i -E 's/^(host\s+all\s+all\s+(127\.0\.0\.1\/32|::1\/128)\s+)ident/\1scram-sha-256/' $PGDATA/pg_hba.conf
sudo systemctl enable --now postgresql >/dev/null
sudo systemctl reload postgresql

if [ ! -f $ENV ]; then
  PW=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
  (umask 077; echo "ERP_DB_URL=postgresql://erp:$PW@127.0.0.1/erp" > $ENV)
fi
PW=$(sed -n 's#^ERP_DB_URL=postgresql://erp:\([^@]*\)@.*#\1#p' $ENV)
if [ "$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='erp'")" != "1" ]; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -qc "CREATE ROLE erp LOGIN PASSWORD '$PW'"
fi
if [ "$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='erp'")" != "1" ]; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -qc "CREATE DATABASE erp OWNER erp"
fi
python3 -c "import psycopg2" 2>/dev/null || pip3 install --user -q psycopg2-binary
echo "postgres 준비 완료: $(psql "$(cut -d= -f2- $ENV)" -tAc 'select version()' | cut -d, -f1)"
