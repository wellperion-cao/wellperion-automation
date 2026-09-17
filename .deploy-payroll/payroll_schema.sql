-- 웰페리온 ERP 강사 페이롤 — PostgreSQL 미러/이관 스키마 v1.0 (CFO 2026-09-17)
-- 원천 = 구글 시트 「강사페이롤_DB(ERP)」(cao) 탭 11개와 1:1. 컬럼명은 시트 헤더를 영문으로 옮긴 것(주석에 시트 헤더).
-- 1단계(병행): 시트 → 이 표로 10분 cron 미러(읽기 전용, server/erp_api/sync_proc.py 관례). 2단계: 수집기(sync)를 서버로 옮기고 시트는 증빙 사본만.
-- 금액은 numeric(14,4) — 시트는 반올림하지 않는다(표시만 반올림). 시각은 Asia/Seoul.

CREATE SCHEMA IF NOT EXISTS payroll;

-- 설정_강사
CREATE TABLE IF NOT EXISTS payroll.instructor (
  name              text PRIMARY KEY,            -- 강사명
  team              text NOT NULL,               -- 팀 (PT·수영·골프·스쿼시·필라테스·체조·루프·GX)
  grade             text,                        -- 직급
  active            boolean NOT NULL DEFAULT true,-- 활성 Y/N
  broj_trainer_name text,                        -- 브로제이강사명 (예 '수영 강대경')
  broj_trainer_id   text,                        -- trainer_id
  sheet_format      text NOT NULL DEFAULT '30분격자', -- 시트형식: 수영격자 | 30분격자
  pay_rate          numeric(6,4) NOT NULL,       -- 지급율 H5 (0.5 · 0.55 · 0.6)
  parking_fee       numeric(12,2) NOT NULL DEFAULT 0,   -- 주차비 M5
  card_fee_rate     numeric(6,4) NOT NULL DEFAULT 0.025,-- 카드수수료율
  duty_allowance    numeric(12,2) NOT NULL DEFAULT 0,   -- 업무추진비 A5
  billing_method    text NOT NULL DEFAULT '표준', -- 청구방식: 표준 | 100회
  team_incentive    boolean NOT NULL DEFAULT false,     -- 팀인센티브 Y/N
  team_incentive_threshold numeric(14,2) DEFAULT 110000000, -- 팀인센티브기준액
  team_incentive_base_rate numeric(6,4) DEFAULT 0.01,  -- 팀인센티브기본율
  team_incentive_high_rate numeric(6,4) DEFAULT 0.02,  -- 팀인센티브상위율
  promo_unit        numeric(12,2) NOT NULL DEFAULT 20000, -- 프로모션단가
  source_sheet_id   text,                        -- 원본시트ID (증빙 사본 원본)
  note              text,                        -- 비고
  updated_at        timestamptz                  -- 수정일시
);

-- 설정_지급규칙 (강사명 '*' = 공통, 강사 행이 공통을 덮는다)
CREATE TABLE IF NOT EXISTS payroll.pay_rule (
  instructor_name text NOT NULL,                 -- 강사명 ('*' 허용)
  member_type     text NOT NULL,                 -- 회원구분
  method          text NOT NULL,                 -- 방식: 비율 | 고정
  value           text NOT NULL,                 -- 값: 'H5'(강사 지급율) | 0.6 | 20000
  note            text,
  updated_at      timestamptz,
  PRIMARY KEY (instructor_name, member_type)
);

-- 설정_회원구분
CREATE TABLE IF NOT EXISTS payroll.member_type (
  member_type     text PRIMARY KEY,              -- 회원구분
  deduct_rate     numeric(6,4) NOT NULL DEFAULT 0,-- 공제율 (비회원 0.1)
  product_prefix  text,                          -- 상품명접두 ((정)·(비)·(WSC))
  note            text
);

-- 설정_수업코드 (수영·체조 격자 코드표)
CREATE TABLE IF NOT EXISTS payroll.lesson_code (
  team          text NOT NULL,                   -- 팀
  code          text NOT NULL,                   -- 코드 (A~X 한 글자)
  name_pattern  text,                            -- 수업명패턴 ('WSC|5' = 모두 포함)
  unit_fee      numeric(12,2) NOT NULL,          -- 1회수업료
  note          text,
  PRIMARY KEY (team, code)
);

-- 등록 = N월P 행
CREATE TABLE IF NOT EXISTS payroll.registration (
  month             char(7) NOT NULL,            -- 월 'YYYY-MM'
  instructor_name   text NOT NULL,               -- 강사명
  ticket_id         text NOT NULL,               -- 수강권ID (브로제이 lesson_ticket_id)
  member_name       text NOT NULL,               -- 회원명 (한글만, 숫자 제거)
  member_name_raw   text,                        -- 회원명원문
  member_id         text,                        -- member_id
  registered_on     date,                        -- 등록일 C
  valid_until       date,                        -- 유효기간 D
  count_total       integer,                     -- 등록회수 E
  remain_month_start integer,                    -- 월초잔여 F
  amount            numeric(12,2) NOT NULL,      -- 결제금액 G
  paid_on           date,                        -- 결제일
  sales_manager     text,                        -- 결제담당자
  product_name      text,                        -- 상품명
  reg_kind          text,                        -- 등록분류 H (신규/재등록)
  member_type       text,                        -- 회원구분 I
  remark            text,                        -- 특이사항 R
  source            text,                        -- 출처 (API/수기)
  status            text,                        -- 상태 (정상/환불/…)
  collected_at      timestamptz,                 -- 수집시각
  PRIMARY KEY (month, instructor_name, ticket_id)
);

-- 세션 = N월S 칸
CREATE TABLE IF NOT EXISTS payroll.session (
  reservation_id  text PRIMARY KEY,              -- reservation_id
  month           char(7) NOT NULL,
  instructor_name text NOT NULL,
  held_at         timestamptz NOT NULL,          -- 일시 (KST)
  lesson_name     text,                          -- 수업명
  member_name     text,
  member_name_raw text,
  ticket_id       text,                          -- 수강권ID
  ticket_name     text,                          -- 수강권명
  attendance      text,                          -- 출석: SHOW | NO_SHOW | NONE | CANCEL
  code            text,                          -- 코드 (수영·체조 격자 한 글자, 미판별 '?')
  record_label    text,                          -- 기록명 (코드+회원명+회차, 예 'B황주원1')
  seq_in_month    integer,                       -- 회차
  code_path       text,                          -- 판별경로 (단가역조회/수업명/보조)
  collected_at    timestamptz
);
CREATE INDEX IF NOT EXISTS session_month_instr ON payroll.session (month, instructor_name);

-- 보정 (수기)
CREATE TABLE IF NOT EXISTS payroll.override (
  id              bigserial PRIMARY KEY,
  month           char(7) NOT NULL,
  instructor_name text NOT NULL,
  target          text NOT NULL,                 -- 대상: 등록 | 월합계
  key             text,                          -- 키 (등록 = 수강권ID)
  field           text NOT NULL,                 -- 항목 (진행·월초잔여·결제금액·회원구분·등록회수·특이사항·팀매출)
  value           text,                          -- 값
  reason          text,                          -- 사유
  created_by      text,                          -- 등록자
  created_at      timestamptz,                   -- 등록시각
  cancelled       boolean NOT NULL DEFAULT false -- 취소 Y
);

-- 월합계 (계산 캐시)
CREATE TABLE IF NOT EXISTS payroll.month_summary (
  month             char(7) NOT NULL,
  instructor_name   text NOT NULL,
  team              text,
  reg_count         integer,                     -- 등록건수
  new_count         integer,                     -- 신규
  renew_count       integer,                     -- 재등록
  progress          integer,                     -- 진행 ΣO
  remain            integer,                     -- 잔여 ΣP
  billed            numeric(14,4),               -- 청구합 J5
  duty_allowance    numeric(14,4),               -- 업무추진비 A5
  team_incentive    numeric(14,4),               -- 팀인센티브 K5
  card_fee          numeric(14,4),               -- 카드수수료 L5
  parking_fee       numeric(14,4),               -- 주차비 M5
  total_pay         numeric(14,4),               -- 지급총액 N5
  consumed          numeric(14,4),               -- 소진 ΣT
  unconsumed        numeric(14,4),               -- 미소진 ΣU
  month_sales       numeric(14,4),               -- 당월매출 F5
  promo_count       integer,                     -- 프로모션수 T3
  promo_fee         numeric(14,4),               -- 프로모션강습료 U3
  flag_count        integer,
  closed            boolean NOT NULL DEFAULT false, -- 마감
  calculated_at     timestamptz,
  PRIMARY KEY (month, instructor_name)
);

-- 플래그
CREATE TABLE IF NOT EXISTS payroll.flag (
  id              bigserial PRIMARY KEY,
  month           char(7) NOT NULL,
  instructor_name text NOT NULL,
  kind            text NOT NULL,                 -- 유형
  key             text,
  detail          text,                          -- 내용
  status          text NOT NULL DEFAULT '미처리',-- 상태
  at              timestamptz
);

-- 증빙 사본
CREATE TABLE IF NOT EXISTS payroll.evidence (
  id              bigserial PRIMARY KEY,
  month           char(7) NOT NULL,
  instructor_name text NOT NULL,
  file_id         text NOT NULL,                 -- 사본파일ID
  url             text,
  created_by      text,
  created_at      timestamptz,
  format          text                           -- 형식(+경고)
);

-- 동기화 로그
CREATE TABLE IF NOT EXISTS payroll.sync_log (
  id            bigserial PRIMARY KEY,
  ran_at        timestamptz NOT NULL,            -- 실행시각
  actor         text,                            -- 주체 (trigger/화면 사용자)
  month         char(7),
  instructor_name text,
  api_calls     integer,                         -- API호출수
  result        text,                            -- 결과
  seconds       numeric(8,2),                    -- 소요초
  error         text
);

-- 계산 규칙(서버 계산기로 옮길 때 그대로): 시트 수식과 동일, 반올림 없음.
--   J = amount * (1 - member_type.deduct_rate)        (표에 없는 구분 → 0 + 플래그)
--   K = J * 10 / 110 ; L = J - K ; M = L / count_total
--   N = pay_rule: 비율 → M * (value='H5' ? instructor.pay_rate : value) / 고정 → value
--   O = count(session where attendance in (SHOW, NO_SHOW) and ticket_id = registration.ticket_id)  (없으면 member_name 조인)
--   P = remain_month_start - O ; Q = N * O ; T = M * O ; U = M * P
--   billed = ΣQ (표준) | ΣQ / ΣO * 100 (100회)
--   team_incentive = team_sales / 1.1 * (team_sales >= threshold ? high_rate : base_rate)  (team_incentive=true 이고 override 팀매출 있을 때)
--   total_pay = duty_allowance + billed + team_incentive - (billed * card_fee_rate + parking_fee)
--   promo_count = Σ O where remark like '%프로모션%' ; promo_fee = promo_count * promo_unit

-- 설정_열람권한 (매니저 지시 2026-09-17: A강사 페이롤 = 본인 · 팀장 · 경영지원부 · 관리부)
CREATE TABLE IF NOT EXISTS payroll.viewer_scope (
  account      text PRIMARY KEY,               -- 계정 (ERP 로그인 이메일)
  scope        text NOT NULL,                  -- 범위: 전체 | 팀 | 본인
  teams        text,                           -- 팀 (범위=팀, 쉼표 구분)
  instructors  text,                           -- 강사명 (범위=본인, 쉼표 구분)
  note         text,
  updated_at   timestamptz
);
-- 적용 규칙: 조회·수집·보정·증빙·마감 요청의 viewer(로그인 계정)로 범위를 정한다.
--   전체 = 모든 강사 · 팀 = teams 에 속한 강사 · 본인 = instructors 에 적힌 강사.
--   관리 기능(수집·보정·설정·증빙·마감)은 전체 범위 계정만. 서버 이관 뒤에는 viewer 를 믿지 말고
--   erp_auth 가 넣는 X-Erp-User 헤더로 판정할 것(시트 단계에서는 화면 비밀번호가 1차 잠금).
