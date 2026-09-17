# 강사 페이롤 백엔드 (.deploy-payroll) — cao 계정 배포 절차

ERP 「파트너팀 체계 ▸ 💰 페이롤」(`coo/check/파트너팀_페이롤.html`)이 부르는 Apps Script 웹앱.
정본 = 구글 시트 **강사페이롤_DB(ERP)** (cao 드라이브 `cfo` 폴더) + 이 폴더의 `Code.gs`.
강사 스프레드시트는 관리부 증빙용 사본으로만 생성한다(원본 무접촉). 서버 DB 이관 계약 = `payroll_schema.sql`.

> 이 폴더는 clasp 로 올리지 않는다(이 PC clasp 인증 = partnerspyj@, cao 권한 없음). **cao@ 크롬에서 붙여넣기 배포.**

## 1. 설치 (cao@wellperion.com · 1회)

| # | 할 일 | 비고 |
|---|---|---|
| 1 | 드라이브 `cfo`(`1k7WHBwvsPWA4W201qkqWDBlOLUctxoUJ`) 안에 스프레드시트 **강사페이롤_DB(ERP)** 새로 만들기 | 탭은 스크립트가 만든다 |
| 2 | 같은 폴더에 하위 폴더 **페이롤증빙** 만들고 폴더 ID 메모 | 증빙 사본 저장 위치 |
| 3 | DB 시트 ▸ 확장 프로그램 ▸ Apps Script ▸ `Code.gs` 내용 전체 교체 · 프로젝트 설정에서 「appsscript.json 표시」 켜고 `appsscript.json` 교체 | 시간대 Asia/Seoul 필수(뉴욕이면 날짜·시간 틀어짐) |
| 4 | 프로젝트 설정 ▸ 스크립트 속성 4개: `BROJ_API_KEY`(매니저님 직접 입력) · `PAYROLL_PW` · `PAYROLL_ADMIN_PW` · `EVIDENCE_FOLDER_ID` | 키·비밀번호는 코드에 넣지 않는다 |
| 5 | 편집기에서 함수 **setupTabs** 실행 → 권한 승인 | 탭 11개 + 설정 시딩(회원구분·수업코드·강사 5명·공통 지급규칙) |
| 6 | 배포 ▸ 새 배포 ▸ 웹 앱 · 실행 = **나(cao@)** · 액세스 = **모든 사용자** → `/exec` URL 복사 | |
| 7 | `coo/check/파트너팀_페이롤.html` 의 `PAYROLL_API` 를 그 URL 로 바꿔 커밋(safe_commit) | GitHub Pages 반영 |
| 8 | 화면에서 강대경 · 2026-09 ▸ ⟳ 지금 수집 ▸ 진행 15 · 청구 446,250 · 지급총액 335,094 확인 | 수기 시트와 0원 차이가 기준값 |
| 9 | 🧾 증빙 사본 → 페이롤증빙 폴더에 `〔증빙〕2026-09 강대경 페이롤_…` 생성 확인 | 원본은 안 건드린다 |
| 10 | 10월 병행 개시 때 **installDailySyncTrigger** 1회 실행(매일 05:00 전 강사 수집) | 월초 5일까지는 전월도 같이 수집 |

## 2. DB 시트 탭

| 탭 | 역할 | 키 |
|---|---|---|
| 설정_강사 | 강사별 변수(팀·시트형식·지급율·주차비·카드수수료율·업무추진비·청구방식·팀인센티브·프로모션단가·원본시트ID) | 강사명 |
| 설정_지급규칙 | 회원구분별 지급단가 규칙(비율/고정). `*` = 공통, 강사명 행이 공통을 덮는다 | 강사명+회원구분 |
| 설정_회원구분 | 공제율·상품명 접두 | 회원구분 |
| 설정_수업코드 | 팀별 코드↔1회수업료↔수업명 패턴(수영·체조 격자용) | 팀+코드 |
| 등록 | N월P 행(브로제이 결제이력+수강권) | 월+강사명+수강권ID |
| 세션 | N월S 칸(브로제이 일정·예약·출석) | reservation_id |
| 보정 | 수기 보정(등록 항목·월합계 팀매출 등), 취소 Y 로 무효화 | 행 |
| 월합계 | 계산 캐시(화면 팀 합계·서버 미러 원천) | 월+강사명 |
| 플래그 | 회원구분미정의·지급규칙없음·잔여음수·등록없는세션·코드미판별 | |
| 증빙 | 생성한 사본 파일ID·URL | |
| 동기화로그 | 실행시각·주체·API호출수·결과 | |

## 3. API 계약 (POST JSON, procurement 관례 · `{ok:false,error}` 실패)

| action | 권한 | 입력 | 출력 |
|---|---|---|---|
| ping | — | | `{ok,system:'payroll',at}` |
| payroll_list | password | month, instructor | `{regs[], sessions[], summary{}, flags[], overrides[], config{}, closed}` |
| payroll_team | password | month, team('전체' 가능) | `{rows[]=월합계, totals{팀:{…}}}` |
| payroll_config_get | password | | `{instructors[], rules[], memberTypes[], codes[]}` |
| payroll_flags · payroll_sync_log | password | month/instructor · limit | rows[] |
| payroll_config_set | adminPassword | table, rows[] | 설정 4표 덮어쓰기(행 단위 upsert) |
| payroll_override_set / _del | adminPassword | month, instructor, target(등록/월합계), key, field, value, reason / row | |
| payroll_run_sync | adminPassword | month, instructor 또는 scope='team', team | 팀 범위는 큐(트리거)로 실행 |
| payroll_evidence_create | adminPassword | month, instructor, by | `{fileId,url,name,rows,sessions,warnings[]}` |
| payroll_close | adminPassword | month, instructor, reopen | 마감/재개 |

## 4. 계산 규칙(강사 시트 수식과 동일 · 반올림 없음)

J = 결제금액 × (1−공제율) · K = J×10/110 · L = J−K · M = L/등록회수 · N = 규칙(비율 = M×비율, 고정 = 고정액) · O = 출석 세션(SHOW/NO_SHOW) · P = 월초잔여−O · Q = N×O · T = M×O · U = M×P
청구합 = ΣQ(표준) | ΣQ÷ΣO×100(100회) · 지급총액 = 업무추진비 + 청구합 + 팀인센티브 − (청구합×카드수수료율 + 주차비) · 팀인센티브 = 팀매출/1.1 × (≥기준액 ? 상위율 : 기본율)

## 5. 남은 일

- 나머지 34명 시트 인벤토리(드라이브 재연결 후) → 설정_강사·설정_수업코드 확장(스쿼시·필라테스·루프·GX 형식 확인).
- 팀매출 자동 입력(procurement `sales_dept` 배관 연결) — 지금은 보정(월합계·팀매출) 수기.
- 시토: `payroll_schema.sql` 로 PostgreSQL 미러(시트 → 10분 cron) 후 이관.
