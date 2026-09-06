#!/usr/bin/env bash
# 나우열M(CHRO 라인) 전용 제한 서버 계정 chro — 이 PC(git-bash)에서 실행. 서버 = AWS 15.164.151.105 (배1093 · GM 결재 2026-09-06).
#   bash server/deploy_chro_account.sh                              # 계정·sshd·hr_app 역할·erp-chro·nginx·sudoers 준비(멱등)
#   bash server/deploy_chro_account.sh --add-key "ssh-ed25519 AAAA... 이름"   # 우열M 쪽 공개키 등록(지문 출력)
#   bash server/deploy_chro_account.sh --revoke <지문>                        # 그 키 한 줄 삭제 → 접속 즉시 끊김
# 마스터 키(wellperion-sito.pem)는 그대로 시토 전용 — chro 는 본인 공개키로만 들어온다. sudo 없음(erp-chro 재기동 한 줄만 예외).
set -euo pipefail
HOST=ec2-user@15.164.151.105
KEY="$HOME/.aws/wellperion-sito.pem"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new"
SCP="scp -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

case "${1:-}" in
  --add-key)
    $SSH "$HOST" bash -s -- "$2" <<'REMOTE_SH'
PUBKEY="$1"
sudo mkdir -p /srv/erp/chro/.ssh
sudo touch /srv/erp/chro/.ssh/authorized_keys
sudo grep -qxF "$PUBKEY" /srv/erp/chro/.ssh/authorized_keys || echo "$PUBKEY" | sudo tee -a /srv/erp/chro/.ssh/authorized_keys >/dev/null
sudo chown -R chro:chro /srv/erp/chro/.ssh
sudo chmod 700 /srv/erp/chro/.ssh
sudo chmod 600 /srv/erp/chro/.ssh/authorized_keys
echo "$PUBKEY" | ssh-keygen -lf -
echo "등록 완료 — 위 지문을 --revoke 에 쓴다"
REMOTE_SH
    exit 0
    ;;
  --revoke)
    $SSH "$HOST" bash -s -- "$2" <<'REMOTE_SH'
FP="$1"
f=/srv/erp/chro/.ssh/authorized_keys
[ -f "$f" ] || { echo "authorized_keys 없음 — 등록된 키가 없다"; exit 0; }
tmp=$(mktemp)
kept=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  got=$(echo "$line" | ssh-keygen -lf - 2>/dev/null | awk '{print $2}')
  if [ "$got" = "$FP" ]; then continue; fi
  echo "$line" >> "$tmp"
  kept=$((kept+1))
done < "$f"
sudo cp "$tmp" "$f" && rm -f "$tmp"
sudo chown chro:chro "$f" && sudo chmod 600 "$f"
echo "삭제 완료 — 지문 $FP 키 제거 (남은 키 $kept 줄)"
REMOTE_SH
    exit 0
    ;;
esac

$SCP server/erp_chro/erp-chro.service server/erp_chro/chro.nginx.conf server/erp_chro/sshd-chro.conf \
     server/erp_chro/sudoers-chro server/erp_chro/chro-login-log.sh "$HOST:/tmp/"

$SSH "$HOST" bash -s <<'REMOTE_SH'
set -euo pipefail

# ── 리눅스 계정(sudo 없음 · 홈 /srv/erp/chro) ─────────────────────────────
id chro >/dev/null 2>&1 || sudo useradd -m -d /srv/erp/chro -s /bin/bash chro
sudo mkdir -p /srv/erp/chro/api
sudo chown chro:chro /srv/erp/chro /srv/erp/chro/api

# ── sshd Match 블록(공개키만 · 포워딩 금지) ───────────────────────────────
sudo install -m 644 /tmp/sshd-chro.conf /etc/ssh/sshd_config.d/90-chro.conf
sudo sshd -t
sudo systemctl reload sshd

# ── 접속 기록 ─────────────────────────────────────────────────────────
sudo install -m 755 /tmp/chro-login-log.sh /etc/profile.d/chro-login-log.sh

# ── sudoers(재기동 한 줄만) ────────────────────────────────────────────
sudo install -m 440 /tmp/sudoers-chro /etc/sudoers.d/91-chro
sudo visudo -c -f /etc/sudoers.d/91-chro

# ── PostgreSQL: hr 스키마 전용 역할 hr_app (비밀번호는 여기서만 생성 · api.env 에만 기록) ──
if ! sudo test -f /srv/erp/chro/api.env; then
  PW=$(openssl rand -hex 24)
  if [ "$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='hr_app'")" != "1" ]; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -qc "CREATE ROLE hr_app LOGIN PASSWORD '$PW'"
  else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -qc "ALTER ROLE hr_app PASSWORD '$PW'"
  fi
  sudo install -o chro -g chro -m 600 /dev/null /srv/erp/chro/api.env
  printf 'ERP_DB_URL=postgresql://hr_app:%s@127.0.0.1/erp\n' "$PW" | sudo tee /srv/erp/chro/api.env >/dev/null
  sudo chown chro:chro /srv/erp/chro/api.env
  sudo chmod 600 /srv/erp/chro/api.env
fi
sudo -u postgres psql -d erp -v ON_ERROR_STOP=1 -qc "
  GRANT USAGE, CREATE ON SCHEMA hr TO hr_app;
  GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA hr TO hr_app;
  GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA hr TO hr_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA hr GRANT ALL PRIVILEGES ON TABLES TO hr_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA hr GRANT ALL PRIVILEGES ON SEQUENCES TO hr_app;
  ALTER ROLE hr_app SET search_path = hr;
  REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM hr_app;
"

# ── systemd 자리(코드 없으면 시작 실패는 정상 — enable 만) ─────────────────
sudo install -m 644 /tmp/erp-chro.service /etc/systemd/system/erp-chro.service
sudo systemctl daemon-reload
sudo systemctl enable erp-chro >/dev/null

# ── nginx: /api/hr/ → 127.0.0.1:8002 (기존 auth_request 관문 상속) ─────────
sudo install -m 644 /tmp/chro.nginx.conf /etc/nginx/conf.d/erp-locations/chro.conf
sudo nginx -t
sudo systemctl reload nginx

echo "=== (a) 계정·권한 ==="
id chro
sudo -l -U chro
echo "=== (b) hr_app 권한 실측 ==="
PGURL=$(sudo cat /srv/erp/chro/api.env | grep '^ERP_DB_URL=' | cut -d= -f2-)
echo "members 접근(거부 기대):"
psql "$PGURL" -Atc "SELECT count(*) FROM public.members" 2>&1 | tail -1 || true
echo "hr 스키마 쓰기(성공 기대):"
psql "$PGURL" -c "CREATE TABLE hr._probe(x int); DROP TABLE hr._probe;" 2>&1 | tail -2
echo "=== (c) chro sudo 범위 ==="
echo "erp-chro 재기동(성공 기대):"
sudo -u chro sudo -n systemctl restart erp-chro 2>&1 | tail -1 || true
echo "erp-api 재기동(거부 기대):"
sudo -u chro sudo -n systemctl restart erp-api 2>&1 | tail -1 || true
echo "=== (d) 기존 서비스 그대로 ==="
systemctl is-active erp-api erp-auth
curl -s -o /dev/null -w "외부 무쿠키 health = %{http_code}\n" http://127.0.0.1/api/health
REMOTE_SH
