#!/usr/bin/env bash
# ERP PostgreSQL 일일 백업 — pg_dump → S3 wellperion-erp-backup (30일 수명주기 · 장기 결정 9).
# 설치 위치 /usr/local/bin/erp-pg-backup.sh · cron /etc/cron.d/erp-pg-backup (KST 03:00) · 권한 = EC2 인스턴스 역할.
# 배포: scp 로 서버 /usr/local/bin/erp-pg-backup.sh 로 덮어쓰기 (server/** 는 sparse-checkout 밖 · git pull 로 안 바뀜).
#
# 일요일(KST) = 업로드 직후, 삭제 전 로컬 덤프($F)로 복원 리허설(임시 DB erp_restore_test)까지 실행.
# S3 읽기 권한 없이 검증한다 — 백업 역할이 s3:PutObject 만 갖는 쓰기 전용 설계는 그대로 유지한다(2026-09-08 GM 결정).
# 리허설 실패해도 백업 자체는 이미 올라갔으므로 스크립트 exit 는 0 유지.
set -euo pipefail
. /srv/erp/db.env
F=/tmp/erp-$(TZ=Asia/Seoul date +%Y%m%d-%H%M).sql.gz
pg_dump "$ERP_DB_URL" | gzip > "$F"
aws s3 cp --only-show-errors "$F" "s3://wellperion-erp-backup/erp/$(basename "$F")" --region ap-northeast-2
echo "$(date '+%F %T') 백업 완료 erp/$(basename "$F") $(stat -c %s "$F")B"

# 상담봇 문답 기록도 같이 올린다 (2026-09-11 · GM 「AWS에 저장시켜두는거지?」).
# 이 기록은 DB 가 아니라 디스크 파일(/srv/erp/chat_log.jsonl + 회전본)이라 위 pg_dump 에 안 들어간다 —
# 이 줄이 없으면 인스턴스가 죽는 순간 손님 질문이 통째로 사라진다. 회전본까지 한 덩어리로 묶는다.
# 실패해도 DB 백업은 이미 끝났으므로 스크립트를 멈추지 않는다.
C=/tmp/chat-$(TZ=Asia/Seoul date +%Y%m%d-%H%M).tar.gz
if ls /srv/erp/chat_log.jsonl* /srv/erp/chat_feedback.jsonl* >/dev/null 2>&1; then
  if tar -czf "$C" -C /srv/erp $(cd /srv/erp && ls chat_log.jsonl* chat_feedback.jsonl* 2>/dev/null) \
     && aws s3 cp --only-show-errors "$C" "s3://wellperion-erp-backup/chat/$(basename "$C")" --region ap-northeast-2; then
    echo "$(date '+%F %T') 상담기록 백업 완료 chat/$(basename "$C") $(stat -c %s "$C")B"
  else
    echo "$(date '+%F %T') 상담기록 백업 실패 — 다음 회차 재시도"
  fi
  rm -f "$C"
fi

# 서버 파일 원장도 같이 올린다 (2026-09-18 · 배 12752 P1 #9 — 백업이 DB dump+chat_log 뿐이라 파트너 FAQ·권한·KPI 가 인스턴스와 함께 사라졌다).
# 대상: /srv/erp/counselbot/** (FAQ·프로필·테넌트) · /srv/erp/auth/*.json (account_perms·dept_presets·eval_kpi·modules 등 데이터 · app.py 코드 제외)
#       · /srv/erp/partner_secrets.json (api_partner_secrets.py 정본 · 600 — tar 가 모드를 보존하므로 root 로 풀면 600 그대로).
# billing_subscriptions·billing_secrets·billing_charges 는 DB 표(common/schema.sql) — 위 pg_dump 가 -t/-n 없이 DB 전체를 뜨므로 이미 들어간다.
# 보존 = chat/ 과 같은 버킷 수명주기(30일). 실패해도 DB 백업은 끝났으므로 멈추지 않는다.
# 복원: aws s3 cp s3://wellperion-erp-backup/files/<날짜>.tar.gz /tmp/f.tgz  (S3 읽기는 관리자 자격으로 · 백업 역할은 쓰기 전용)
#   sudo tar -xzpf /tmp/f.tgz -C /   → /srv/erp/counselbot/ · /srv/erp/auth/*.json · /srv/erp/partner_secrets.json 이 원래 자리에 놓인다
#   그 뒤 systemctl restart erp-auth erp-api (auth 는 json 을 기동 때 읽는다 · 상담봇은 파일 직독이라 재기동 불필요)
#   DB 는 gunzip -c erp-<날짜>.sql.gz | psql "$ERP_DB_URL" (billing 표 포함) · 순서 = DB 먼저, 파일 다음.
#   확인: ls -l /srv/erp/partner_secrets.json 이 -rw------- 인지 · /api/auth/check 200 · 상담봇 FAQ 1건 조회.
B=/tmp/files-$(TZ=Asia/Seoul date +%Y%m%d-%H%M).tar.gz
FILES=$(ls -d /srv/erp/counselbot /srv/erp/auth/*.json /srv/erp/partner_secrets.json 2>/dev/null || true)
if [ -n "$FILES" ]; then
  if tar -czf "$B" -C / $(echo "$FILES" | sed 's#^/##')      && aws s3 cp --only-show-errors "$B" "s3://wellperion-erp-backup/files/$(basename "$B")" --region ap-northeast-2; then
    echo "$(date '+%F %T') 파일 원장 백업 완료 files/$(basename "$B") $(stat -c %s "$B")B"
  else
    echo "$(date '+%F %T') 파일 원장 백업 실패 — 다음 회차 재시도"
  fi
  rm -f "$B"
fi

if [ "$(TZ=Asia/Seoul date +%u)" = "7" ]; then
  T0=$(date +%s)
  TABLES="members reception_items hold_items todo_items inquiries member_change_log write_log sync_meta"
  # 주의: 이 서브셸은 if 조건식이라 bash 가 set -e 를 무시한다(문서화된 동작) — 실패는 매 단계 `|| exit 1` 로 직접 검사한다.
  if OUT=$(
    sudo -n -u postgres dropdb --if-exists erp_restore_test || exit 1
    sudo -n -u postgres createdb erp_restore_test || exit 1
    gunzip -c "$F" | sudo -n -u postgres psql -q -v ON_ERROR_STOP=1 erp_restore_test > /dev/null || exit 1
    for t in $TABLES; do
      n=$(sudo -n -u postgres psql -tAc "SELECT count(*) FROM $t" erp_restore_test) || exit 1
      case "$n" in ''|*[!0-9]*) exit 1 ;; esac
      printf '%s=%s ' "$t" "$n"
    done
  2>&1); then
    sudo -n -u postgres dropdb --if-exists erp_restore_test
    echo "$(date '+%F %T') 복원 리허설 OK 표 $(echo "$TABLES" | wc -w)개 행 ${OUT}· 소요 $(( $(date +%s) - T0 ))초"
  else
    sudo -n -u postgres dropdb --if-exists erp_restore_test 2>/dev/null || true
    echo "$(date '+%F %T') 복원 리허설 실패: ${OUT}"
  fi
fi

rm -f "$F"
