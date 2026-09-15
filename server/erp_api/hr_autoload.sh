#!/usr/bin/env bash
# 인사 시트 → 서버 자동 적재 (2026-09-15 시토 · GM 「비번 있는 부분도 변환 · 다 이관」).
# 적재 열쇠(HR_GAS_PASSWORD)가 서버에 생기는 순간(등록 화면 또는 화면 읽기에서 학습) 사람 손 없이 1단계 적재를 돌린다.
# 조건 = 열쇠 있음 AND hr.employee 살아 있는 행 0(아직 한 번도 적재 안 됨) AND 잠금 없음. 한 번 채워지면 다시는 안 돈다.
# 결과 = /srv/erp/logs/hr_autoload.log + /srv/erp/logs/hr_apply_report.json(개인정보 원문 없음). 크론 = /etc/cron.d/erp-hr-autoload(10분).
set -u
cd /srv/erp/api || exit 1
set -a; . /srv/erp/api.env; . /srv/erp/db.env 2>/dev/null; set +a
LOG=/srv/erp/logs/hr_autoload.log
[ -n "${HR_GAS_PASSWORD:-}" ] || exit 0
LOCK=/tmp/hr_autoload.lock
exec 9>"$LOCK"; flock -n 9 || exit 0
N=$(sudo -u postgres psql -d erp -Atc "select count(*) from hr.employee where vanished_at is null" 2>/dev/null || echo x)
[ "$N" = "0" ] || exit 0
echo "$(date '+%F %T') 열쇠 확인 · 직원 0행 → 적재 시작" >> "$LOG"
python3 migrate_hr.py --apply --report /srv/erp/logs/hr_apply_report.json >> "$LOG" 2>&1
echo "$(date '+%F %T') 적재 종료 rc=$? · 직원 행=$(sudo -u postgres psql -d erp -Atc 'select count(*) from hr.employee where vanished_at is null')" >> "$LOG"
