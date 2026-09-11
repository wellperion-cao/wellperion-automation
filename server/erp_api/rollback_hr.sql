-- ═══════════════════════════════════════════════════════════════════════════════════════════════
-- hr 스키마 되돌리기 — 인사 데이터 AWS 이관 1단계 (aws2 §C-2 · 2026-09-11 CHRO)
-- ⛔ 실행 전 세 가지가 전부 갖춰져야 한다:
--    1) pg_dump 필수 — hr 스키마만 1회 떠 둔다(되돌리기의 되돌리기는 이 덤프뿐이다):
--         sudo -u postgres pg_dump -d erp -n hr -Fc -f /srv/erp/backup/hr_before_rollback.dump
--    2) 실행 주체 = CTO(시토) · DB 관리자 역할(postgres)로 psql 직접 실행 — db.init_schema()(schema.sql) 경로로 타지 않는다.
--    3) 매니저 승인 후 — 이 파일은 사람이 켠 절만 실행하는 수동 절차다. 자동 실행(cron·서비스)에 걸지 않는다.
-- 실행:
--    sudo -u postgres psql -d erp -v ON_ERROR_STOP=1 -f rollback_hr.sql                  # 기본 — 파괴적 절은 전부 꺼져 있다
--    sudo -u postgres psql -d erp -v ON_ERROR_STOP=1 -v run_id=123 -f rollback_hr.sql    # 4절(run 단위)을 켰을 때만 run_id 필요
-- ⛔ DROP SCHEMA 를 쓰지 않는다 — hr_app 의 권한·기본권한·search_path 가 스키마에 묶여 있어 통째로 날리면 재부여 누락 사고가
--    난다. 표는 남기고 내용만 비운다(TRUNCATE) — 권한·인덱스·FK·CHECK 가 그대로 산다.
-- 절 구성 — 각 절은 /* … */ 로 켜고 끈다. 그대로 실행하면 0·1·2·7·8 만 돌아 어떤 행도 지워지지 않는다.
--    0) 적재 락 확인(항상)        1) 사전 보존(항상)          2) 미완 run 닫기(항상)
--    3) 전체 초기화(꺼짐)         3-1) 부서 수동 속성 복원(꺼짐 · 적재 후)
--    4) run 단위 되돌리기(꺼짐)   5) 탭 단위 되돌리기(꺼짐)   6) 스키마 변경 되돌리기(꺼짐)
--    7) hr_app 권한 재부여(항상)  8) 사후 확인(항상)
--    ★3·4·5·6 은 서로 대안이다 — 한 번에 하나만 켠다. 켠 채로 커밋·배포하지 않는다(켜는 것은 실행 직전 · 끝나면 다시 끈다).
-- 파일 전체가 한 트랜잭션(BEGIN … COMMIT) — 중간에 실패하면 psql 이 멈추고(ON_ERROR_STOP) 전부 되돌아간다.
-- 규약: 리터럴 백분율 기호를 쓰지 않는다(schema.sql 과 습관을 맞춘다 — 이 파일은 psql 직접 실행이라 제한 자체는 없다).
--       원문자 대신 1) 2) 3). 개인정보 값은 어떤 절에서도 출력하지 않는다(건수만).
-- ═══════════════════════════════════════════════════════════════════════════════════════════════
\set ON_ERROR_STOP on
BEGIN;

-- ── 0. 적재 실행 락(항상) ─────────────────────────────────────────────────────────────────────
-- migrate_hr.py --apply 가 잡는 세션 advisory lock 과 같은 키(HR_RUN_LOCK_KEY = 11050002 · aws2 §0.3).
-- 적재가 도는 중이면 여기서 멈춘다 — 적재 트랜잭션 밑에서 표를 비우는 사고를 구조로 막는다.
-- 이 세션이 락을 쥔 동안(psql 종료까지) 새 적재도 시작하지 못한다.
DO $$
BEGIN
  IF NOT pg_try_advisory_lock(11050002) THEN
    RAISE EXCEPTION USING MESSAGE = '적재(migrate_hr.py --apply)가 실행 중이다(advisory lock 11050002 점유) — 끝난 뒤 다시 실행';
  END IF;
END $$;

-- ── 1. 사전 보존(항상) — 사람이 손으로 채운 부서 속성 백업 ────────────────────────────────────
-- 적재기 seed_departments 는 현재근무자 부서명으로 '이름만' 다시 만든다. board_group·leave_applicable·sort_order·active 는
-- 사람이 채운 값이라 초기화하면 사라진다 → 여기 보존해 두고 3-1절로 되돌린다.
-- 백업표는 이 파일이 만들고 이 파일만 지운다(3절 TRUNCATE 목록에 없다). 2회 이상 실행하면 saved_at 별로 누적된다.
CREATE TABLE IF NOT EXISTS hr._dept_manual_backup (
  saved_at         TIMESTAMPTZ NOT NULL,
  tenant_id        TEXT NOT NULL,
  name             TEXT NOT NULL,
  board_group      TEXT,
  leave_applicable BOOLEAN,
  sort_order       INTEGER,
  active           BOOLEAN
);
INSERT INTO hr._dept_manual_backup (saved_at, tenant_id, name, board_group, leave_applicable, sort_order, active)
SELECT now(), tenant_id, name, board_group, leave_applicable, sort_order, active FROM hr.department;

-- ── 2. 미완 run 닫기(항상) ────────────────────────────────────────────────────────────────────
-- 0절 락을 쥐고 있으므로 지금 running 인 run 은 전부 '강제 종료로 남은 것'이다. 실행 이력은 지우지 않고 상태만 닫는다.
UPDATE hr.migration_run
   SET status = 'aborted', finished_at = now(),
       note = COALESCE(note, '') || ' / aborted by rollback_hr.sql'
 WHERE status = 'running';

-- ── 3. hr 적재표 초기화 — 전체(꺼짐) ─────────────────────────────────────────────────────────
-- 한 문장 TRUNCATE 로 FK 순서 문제를 없앤다(참조하는 표를 같은 문장에 다 넣어야 통한다 — 목록이 곧 계약).
-- ⛔ 목록에 넣지 않는 표: hr.access_log(열람 원장 — 절대 비우지 않는다) · hr.automation_log · hr.holiday · hr.command_queue
--    (1단계 미적재 · FK 없음) · hr._dept_manual_backup(1절 백업).
-- leave_ledger·schedule_change_request·personal_calendar_event 는 비어 있어도 employee/person 을 참조하므로 목록에 있어야 한다.
-- RESTART IDENTITY = 각 표 BIGSERIAL 을 1 부터 다시. 역인덱스(hr.legacy_row_map)도 여기서 비워지고, 다음 적재가 탭 트랜잭션
-- 안에서 다시 채운다(별도 SQL 없음). 부서 seed 재적재 지점 = 다음 migrate_hr.py --apply 의 seed_departments.
/*
TRUNCATE TABLE
  hr.migration_step, hr.migration_run, hr.legacy_row_map,
  hr.applicant_document, hr.application_stage_history,
  hr.leave_entry, hr.leave_ledger, hr.schedule_change_request, hr.personal_calendar_event,
  hr.onboarding_item, hr.resignation, hr.evaluation, hr.applicant, hr.job_posting, hr.hire_blacklist,
  hr.employee, hr.department, hr.person
RESTART IDENTITY;
*/

-- ── 3-1. 부서 수동 속성 복원(꺼짐 · 3절 뒤 migrate_hr.py --apply 1회가 끝난 다음 별도 실행) ───────
-- 1절 백업 중 부서별 가장 최근 것(saved_at 내림차순)으로 되돌린다. 적재가 만들지 않은 부서(이름이 바뀐 것)는 남는다 — 사람이 확인.
/*
UPDATE hr.department d
   SET board_group = b.board_group, leave_applicable = b.leave_applicable, sort_order = b.sort_order, active = b.active
  FROM (SELECT DISTINCT ON (tenant_id, name) * FROM hr._dept_manual_backup ORDER BY tenant_id, name, saved_at DESC) b
 WHERE b.tenant_id = d.tenant_id AND b.name = d.name;
*/

-- ── 4. run 단위 부분 되돌리기(꺼짐 · -v run_id=N 필요) ────────────────────────────────────────
-- 전체 초기화 대신 한 번의 apply 실행만 무르는 길. 그 run 의 batch_at 이 기준이다(aws2 §A-11 · §C-2 4절).
-- ⚠️ 순서 고정 — 4-b(새 행 삭제)가 4-c(옛 행 되살리기)보다 먼저다. 되살린 옛 행과 새 행이 같은 열쇠로 둘 다 살아나면
--    부분 유일 인덱스(ux_hr_*_live)에 걸린다.
-- ⚠️ 이 절은 batch_at 이 기록된 run(이번 변경 이후의 apply)에만 쓸 수 있다 — 없으면 4-0 에서 멈춘다.
/*
-- 4-0. 대상 run 확인(없거나 batch_at 이 비었으면 멈춘다)
CREATE TEMP TABLE _rb_run ON COMMIT DROP AS
  SELECT run_id, batch_at FROM hr.migration_run WHERE run_id = :run_id;
DO $$
BEGIN
  IF (SELECT count(*) FROM _rb_run) <> 1 OR (SELECT batch_at FROM _rb_run) IS NULL THEN
    RAISE EXCEPTION USING MESSAGE = 'run_id 가 없거나 batch_at 이 비어 있다 — run 단위 되돌리기 불가(전체 초기화 3절 또는 탭 단위 5절)';
  END IF;
END $$;

-- 4-a. 그 run 이 새로 만든 행을 가리키는 FK 끊기 — ON DELETE RESTRICT 라 먼저 끊어야 4-b 가 통한다. 다음 apply 의
--      link_fks(살아 있는 행끼리 NULL 만 채움 · aws2 §A-5-2)가 다시 잇는다.
UPDATE hr.leave_entry             SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run));
UPDATE hr.resignation             SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run));
UPDATE hr.onboarding_item         SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run));
UPDATE hr.leave_ledger            SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run));
UPDATE hr.schedule_change_request SET requester_employee_id = NULL WHERE requester_employee_id IN (SELECT employee_id FROM hr.employee WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run));
UPDATE hr.applicant               SET posting_id = NULL WHERE posting_id IN (SELECT posting_id FROM hr.job_posting WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run));

-- 4-b. 그 run 이 새로 만든 행 삭제(created_at 이 배치 시각 이후이고 synced_at 이 그 배치 시각인 행 = 이번 run 이 삽입한 행.
--      전부터 있던 행은 갱신돼도 created_at 이 배치 시각보다 앞이라 걸리지 않는다). 종속 표 → 참조 표 순서.
DELETE FROM hr.leave_entry     WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.resignation     WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.onboarding_item WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.applicant       WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.evaluation      WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.hire_blacklist  WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.employee        WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);
DELETE FROM hr.job_posting     WHERE created_at >= (SELECT batch_at FROM _rb_run) AND synced_at = (SELECT batch_at FROM _rb_run);

-- 4-c. 그 run 이 닫은 행 되살리기(8표)
UPDATE hr.employee        SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.job_posting     SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.applicant       SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.evaluation      SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.onboarding_item SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.resignation     SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.hire_blacklist  SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);
UPDATE hr.leave_entry     SET vanished_at = NULL, vanish_reason = NULL, vanished_run_id = NULL WHERE vanished_run_id = (SELECT run_id FROM _rb_run);

-- 4-d. 역인덱스에서 사라진 PK 를 가리키는 항목 제거 — 다음 apply 가 살아 있는 행 기준으로 다시 채운다(row_map_sql).
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.employee'        AND NOT EXISTS (SELECT 1 FROM hr.employee        t WHERE t.employee_id    = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.job_posting'     AND NOT EXISTS (SELECT 1 FROM hr.job_posting     t WHERE t.posting_id     = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.applicant'       AND NOT EXISTS (SELECT 1 FROM hr.applicant       t WHERE t.applicant_id   = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.evaluation'      AND NOT EXISTS (SELECT 1 FROM hr.evaluation      t WHERE t.eval_id        = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.onboarding_item' AND NOT EXISTS (SELECT 1 FROM hr.onboarding_item t WHERE t.item_id        = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.resignation'     AND NOT EXISTS (SELECT 1 FROM hr.resignation     t WHERE t.resignation_id = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.hire_blacklist'  AND NOT EXISTS (SELECT 1 FROM hr.hire_blacklist  t WHERE t.blacklist_id   = m.target_id);
DELETE FROM hr.legacy_row_map m WHERE m.target_table = 'hr.leave_entry'     AND NOT EXISTS (SELECT 1 FROM hr.leave_entry     t WHERE t.leave_id       = m.target_id);

-- 4-e. 실행 이력은 지우지 않는다(migration_run·migration_step 삭제 금지) — 상태만 aborted 로.
UPDATE hr.migration_run
   SET status = 'aborted', note = COALESCE(note, '') || ' / rolled back by rollback_hr.sql'
 WHERE run_id = (SELECT run_id FROM _rb_run);
*/

-- ── 5. 탭 단위 되돌리기(꺼짐) ─────────────────────────────────────────────────────────────────
-- migrate_hr.py 꼬리말 안내(탭 하나만 지우고 다시 적재)와 같은 뜻을 SQL 로. 예시 = 휴무 탭(다른 표가 참조하지 않아 바로 지운다).
-- 직원 표(현재근무자·퇴사자)는 휴무·퇴사처리·온보딩·연차원장·근무변경이 employee_id 로 참조한다(ON DELETE RESTRICT) —
-- 먼저 그 FK 를 NULL 로 끊고 지운다(4-a 와 같은 문장에서 조건만 legacy_tab 으로 · 다음 apply 가 다시 잇는다).
-- 지원자는 applicant_document·application_stage_history 가 CASCADE 라 바로 지워진다.
/*
DELETE FROM hr.leave_entry    WHERE tenant_id = 'wellperion' AND legacy_tab = '휴무';
DELETE FROM hr.legacy_row_map WHERE tenant_id = 'wellperion' AND legacy_tab = '휴무';
*/

-- ── 6. 스키마 변경 자체의 되돌리기(꺼짐) — 부분 유일 인덱스 → 표 수준 UNIQUE · vanished 3칸 제거 ───
-- ⚠️ 이 절을 쓰면 schema.sql 도 같이 되돌려야 한다(aws2 커밋 revert) — 아니면 다음 init_schema 가 위 변경을 다시 만든다.
--    적재기(migrate_hr.py)·API(api_hr.py)도 같은 커밋으로 되돌린다(둘 다 새 칸을 읽는다).
-- ⚠️ 6-a 는 닫힌(vanished) 행의 물리 삭제다 — 되돌릴 수 없다(1)의 pg_dump 가 유일한 복구 지점). 표 수준 UNIQUE 는
--    닫힌 행이 남아 있으면 중복으로 실패하므로 먼저 지워야 한다.
/*
-- 6-a. 닫힌 행을 가리키는 FK 끊기 → 닫힌 행 삭제(종속 표 → 참조 표 순서)
UPDATE hr.leave_entry             SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE vanished_at IS NOT NULL);
UPDATE hr.resignation             SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE vanished_at IS NOT NULL);
UPDATE hr.onboarding_item         SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE vanished_at IS NOT NULL);
UPDATE hr.leave_ledger            SET employee_id = NULL WHERE employee_id IN (SELECT employee_id FROM hr.employee WHERE vanished_at IS NOT NULL);
UPDATE hr.schedule_change_request SET requester_employee_id = NULL WHERE requester_employee_id IN (SELECT employee_id FROM hr.employee WHERE vanished_at IS NOT NULL);
UPDATE hr.applicant               SET posting_id = NULL WHERE posting_id IN (SELECT posting_id FROM hr.job_posting WHERE vanished_at IS NOT NULL);
DELETE FROM hr.leave_entry     WHERE vanished_at IS NOT NULL;
DELETE FROM hr.resignation     WHERE vanished_at IS NOT NULL;
DELETE FROM hr.onboarding_item WHERE vanished_at IS NOT NULL;
DELETE FROM hr.applicant       WHERE vanished_at IS NOT NULL;
DELETE FROM hr.evaluation      WHERE vanished_at IS NOT NULL;
DELETE FROM hr.hire_blacklist  WHERE vanished_at IS NOT NULL;
DELETE FROM hr.employee        WHERE vanished_at IS NOT NULL;
DELETE FROM hr.job_posting     WHERE vanished_at IS NOT NULL;

-- 6-b. 부분 유일 인덱스 8개 · 되짚기 인덱스 7개 제거(ix_hr_leave_legacy 는 변경 전부터 있던 것 — 유지)
DROP INDEX IF EXISTS hr.ux_hr_emp_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_posting_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_appl_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_eval_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_onbo_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_resign_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_blacklist_legacy_live;
DROP INDEX IF EXISTS hr.ux_hr_leave_name_date_live;
DROP INDEX IF EXISTS hr.ix_hr_emp_legacy;
DROP INDEX IF EXISTS hr.ix_hr_posting_legacy;
DROP INDEX IF EXISTS hr.ix_hr_appl_legacy;
DROP INDEX IF EXISTS hr.ix_hr_eval_legacy;
DROP INDEX IF EXISTS hr.ix_hr_onbo_legacy;
DROP INDEX IF EXISTS hr.ix_hr_resign_legacy;
DROP INDEX IF EXISTS hr.ix_hr_blacklist_legacy;

-- 6-c. 표 수준 UNIQUE 복구(PostgreSQL 기본 이름 · 이미 있으면 건너뜀)
DO $$
DECLARE
  spec TEXT[][] := ARRAY[
    ARRAY['employee',        'employee_tenant_id_legacy_tab_legacy_row_key',        'tenant_id, legacy_tab, legacy_row'],
    ARRAY['job_posting',     'job_posting_tenant_id_legacy_tab_legacy_row_key',     'tenant_id, legacy_tab, legacy_row'],
    ARRAY['applicant',       'applicant_tenant_id_legacy_tab_legacy_row_key',       'tenant_id, legacy_tab, legacy_row'],
    ARRAY['evaluation',      'evaluation_tenant_id_legacy_tab_legacy_row_key',      'tenant_id, legacy_tab, legacy_row'],
    ARRAY['onboarding_item', 'onboarding_item_tenant_id_legacy_tab_legacy_row_key', 'tenant_id, legacy_tab, legacy_row'],
    ARRAY['resignation',     'resignation_tenant_id_legacy_tab_legacy_row_key',     'tenant_id, legacy_tab, legacy_row'],
    ARRAY['hire_blacklist',  'hire_blacklist_tenant_id_legacy_tab_legacy_row_key',  'tenant_id, legacy_tab, legacy_row'],
    ARRAY['leave_entry',     'leave_entry_tenant_id_person_name_raw_work_date_key', 'tenant_id, person_name_raw, work_date']
  ];
  i INTEGER;
BEGIN
  FOR i IN 1 .. array_length(spec, 1) LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c
                     JOIN pg_class cl ON cl.oid = c.conrelid
                     JOIN pg_namespace n ON n.oid = cl.relnamespace
                    WHERE n.nspname = 'hr' AND cl.relname = spec[i][1] AND c.conname = spec[i][2]) THEN
      EXECUTE 'ALTER TABLE hr.' || quote_ident(spec[i][1]) || ' ADD CONSTRAINT ' || quote_ident(spec[i][2])
           || ' UNIQUE (' || spec[i][3] || ')';
    END IF;
  END LOOP;
END $$;

-- 6-d. 칸 제거(8표 + migration_run)
ALTER TABLE hr.employee        DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.job_posting     DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.applicant       DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.evaluation      DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.onboarding_item DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.resignation     DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.hire_blacklist  DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.leave_entry     DROP COLUMN IF EXISTS vanished_at, DROP COLUMN IF EXISTS vanish_reason, DROP COLUMN IF EXISTS vanished_run_id;
ALTER TABLE hr.migration_run   DROP COLUMN IF EXISTS batch_at,    DROP COLUMN IF EXISTS warnings,      DROP COLUMN IF EXISTS aborted_by_run;
*/

-- ── 7. hr_app 권한 재부여(항상 · 멱등) ────────────────────────────────────────────────────────
-- server/deploy_chro_account.sh 의 GRANT 블록과 같은 문장(비밀번호 생성·ALTER ROLE PASSWORD 줄은 제외 — 비밀값은 그 스크립트만
-- 만들고 api.env 에만 둔다). TRUNCATE 는 표를 유지하므로 권한이 사라지지 않지만, 6절이나 수동 DROP 뒤를 대비해 항상 마지막에 둔다.
-- hr_app 역할이 없으면(배포 스크립트 미실행) 여기서 멈춘다 — 그 자체가 배포 순서 오류 신호다.
GRANT USAGE, CREATE ON SCHEMA hr TO hr_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA hr TO hr_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA hr TO hr_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA hr GRANT ALL PRIVILEGES ON TABLES TO hr_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA hr GRANT ALL PRIVILEGES ON SEQUENCES TO hr_app;
ALTER ROLE hr_app SET search_path = hr;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM hr_app;

-- ── 8. 사후 확인(항상 · 건수만 — 개인정보 값 출력 없음) ─────────────────────────────────────
-- 표별 살아 있는/닫힌 행수(6절을 켰다면 vanished_at 칸이 없으므로 총 행수만) · running run 0건 · 부분 유일 인덱스 8개(6절 뒤엔 0개).
DO $$
DECLARE
  t TEXT; live BIGINT; closed BIGINT; has_col BOOLEAN;
BEGIN
  FOREACH t IN ARRAY ARRAY['employee', 'job_posting', 'applicant', 'evaluation',
                           'onboarding_item', 'resignation', 'hire_blacklist', 'leave_entry'] LOOP
    SELECT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'hr' AND table_name = t AND column_name = 'vanished_at') INTO has_col;
    IF has_col THEN
      EXECUTE 'SELECT count(*) FILTER (WHERE vanished_at IS NULL), count(*) FILTER (WHERE vanished_at IS NOT NULL) FROM hr.' || quote_ident(t)
         INTO live, closed;
      RAISE NOTICE USING MESSAGE = '[확인] hr.' || t || ' 살아 있는 행 ' || live || ' / 닫힌 행 ' || closed;
    ELSE
      EXECUTE 'SELECT count(*) FROM hr.' || quote_ident(t) INTO live;
      RAISE NOTICE USING MESSAGE = '[확인] hr.' || t || ' 행 ' || live || ' (vanished_at 칸 없음 — 6절 적용 상태)';
    END IF;
  END LOOP;
END $$;
SELECT count(*) AS running_runs FROM hr.migration_run WHERE status = 'running';          -- 0 이어야 한다
SELECT indexname FROM pg_indexes WHERE schemaname = 'hr' AND indexname ~ '^ux_hr_.*_live$' ORDER BY 1;   -- 8개(6절 뒤엔 0개)

COMMIT;
-- 끝. 3절을 켰다면 다음 순서: migrate_hr.py --dry-run → --apply 1회 → 3-1절(부서 수동 속성 복원) → erp-chro 재기동.
