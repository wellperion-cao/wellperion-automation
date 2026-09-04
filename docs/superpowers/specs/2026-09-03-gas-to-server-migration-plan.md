# GAS·구글시트 → 서버 전사 이전 계획 (배 960)

작성: AI 시토 | 2026-09-03 | GM 지시 「GAS·구글시트에 되어 있는 것들은 다 서버로 옮겨서 문제없게 — 마감 후 실무진 미사용 시간에」
전제: 실무진은 아침에 이전을 못 느껴야 한다(화면·시트 그대로, 저장만 서버로). 서버 = AWS erp.wellperion.com · PostgreSQL(`server/common/db.py`) · 장기 결정 5번(서버 API 가 유일한 쓰기 창구, 시트는 되밀기 사본).

## 1. 이전 방식 3가지 (화면마다 하나만 고른다)

| 방식 | 뜻 | 화면이 바꾸는 것 | 되돌리기 |
|---|---|---|---|
| **읽기 거울** | 서버가 5분마다 GAS 를 떠와 DB 에 두고 GAS 응답 모양 그대로 API 로 준다 | ERP 도메인이면 `/api/...` 먼저, 실패 시 GAS 폴백 | 없음(GAS 그대로 살아 있음) |
| **쓰기 이중기록** | 화면 → 서버 API → DB 에 먼저 적고 → 같은 본문을 GAS 에 그대로 넘겨 시트도 쌓는다 | 저장 주소 1줄 | 주소 1줄을 GAS `/exec` 로 원복 |
| **서버 원본** | 서버 DB 가 정본. 시트는 서버가 되밀어 주는 사본(GAS 는 쓰기 안 받음) | 없음(이중기록 단계에서 이미 서버로 보냄) | api.env 의 GAS URL 로 되밀기 재개 |

**이중기록 → 서버 원본 전환 규칙:** 이중기록 시작일부터 **3일 연속 대조 무결**(날짜별 서버 행수 = 시트 행수 · 본문 키 대조 불일치 0) → 서버 원본 전환 → 시트는 되밀기 사본. 대조 스크립트 = `intake_log`/`write_log` ↔ 해당 시트 미러(sync_*) 비교. 불일치 1건이라도 나오면 3일 카운트 리셋.

## 2. GAS 프로젝트별 이전표 (배포ID 앞 14자 · 쓰는 파일 수 = 저장소 실측 2026-09-03)

| # | GAS 프로젝트 (배포ID) | 액션 | 쓰는 화면(대표) · 파일 수 | 담당 | 이전 방식 | 상태 | 야간 창 |
|---|---|---|---|---|---|---|---|
| 1 | 퍼널·문의 Survey (`AKfycbykgMyFc-`) | 읽기: 문의 3종·회원 목록 | 문의현황 · membership · renewal · 오넛티 · 실무진피드백 · 종합접수처_현황 · 업무 SSOT · 26파일 | 시포 | 읽기 거울 (`sync_inquiries`·`sync_members` → `/api/inquiries`·`/api/members`) | **완료** | 09-02~03 |
| 1b | 〃 | 쓰기: 회원 수정·문의 상태·피드백 | membership.html 등 | 시포·시토 | 쓰기 이중기록 (`api_write.py` `/api/write` · 배 961) | **오늘 완료** | 09-03 |
| 1c | 〃 | 읽기: `period_breakdown` `funnel_conversion` `funnel_conversion_detail` `lesson_breakdown` | 월간마케팅보고서 · 콘텐츠문의현황 | 시모 | 읽기 거울 (`sync_funnel.py` + `api_funnel.py` · 규격 §4) | **완료 09-04**(쿼리형 404 수리) | 09-04 |
| 2 | 문의 접수 Intake (`AKfycbyLc2cnOe` · 시험용 head `AKfycbzeGDag3X`) | 쓰기: 문의 폼 POST | wp_inquiry_form.html · _en (WP 8394·8408 주입) | 시모 | 쓰기 이중기록 (`api_intake.py` `/api/intake/inquiry`) | **서버 완료 · 주소 교체 대기(§3)** | 09-04 |
| 3 | 강사 접수 (`AKfycbz4wWhqIC`) | 쓰기: 접수 POST | instructor_intake.html · GM의일요일.html (`cmo/_api.js`) | 시모 | 쓰기 이중기록 (`/api/intake/instructor` · `/sunday`) | **서버 완료 · 주소 교체 대기(§3)** | 09-04 |
| 4 | 종합접수처 (`AKfycbwk2XS1FN` · `.deploy-reception`) | 읽기: reg_board · lf_list · hold · scoreboard | 종합접수처_현황 · 월간운영계획 · 15파일 | 시우(실행=시토) | 읽기 거울 (`sync_reception` → `/api/reception/*` · 배 922 레인 R) | **오늘 완료** | 09-03 |
| 4b | 〃 | 쓰기: 회원 접수 폼(WP 8434) · 습득물 등록·처리 · reg_update | reception_block · lost_found_register 등 | 시우(실행=시토) | 쓰기 이중기록 (`/api/intake/reception` · WP 8434·8751 공개 폼 서버행 고정 완료) | **완료 09-04** | 09-04 |
| 5 | 점검 3부서 (`AKfycbyXw4ZaA6` 전사_일정·체계 · `AKfycbyHY37y5C` 지원팀 일일점검) | 읽기: board · 원장 · today_live · monthly | 시설부·지원부·주차관리부 체계 · 전사_일정 · GM업무 · 21파일 | 시우(실행=시토) | 읽기 거울 (`sync_check` → `/api/check/{dept}` · 배 922 레인 S) | **오늘 완료** | 09-03 |
| 5b | 〃 | 쓰기: 점검 체크 저장 · 일정 등록 | 〃 | 시우(실행=시토) | 쓰기 이중기록 (`/api/write` 확장 · 11종) | **완료 09-04** | 09-04 |
| 6 | 업무·결재 현황 (`AKfycbxDwFkrxK` · `.deploy-todo`) | 읽기: todo_list · gm_hangro · home_kpi · CFO 월별 | 업무/결재 SSOT · GM업무 · 자율현황 · 매출현황 · 25파일 | 시우(실행=시토) | 읽기 거울 (`sync_todo` → `/api/todo/*` · 배 922 레인 T) | **오늘 완료** | 09-03 |
| 6b | 〃 | 쓰기: 업무·결재 저장 · GM업무 카드 | 업무/결재 SSOT · GM업무 | 시토 | 쓰기 이중기록 (`/api/write` 확장 · erp_write.js) | **완료 09-04** | 09-04 |
| 7 | 인사 허브 (`AKfycbyyXrdM7n` · 저장소 `.deploy-*` 없음 → info@ 또는 시트 내장) | 읽기·쓰기: 조직·일정·휴가·온보딩·채용 | chro/hub 10화면 · recruiting 6화면 · 18파일 | 시토(시로 큐 제외) | 읽기 거울 → 쓰기 이중기록 | 예정 | 09-08 (소스 확보 = info@ 로그인 선행) |
| 8 | 매출 배관 sales-api (`AKfycbzXcWyi-P` · `.deploy-salesops`) · 운영요약 (`AKfycbxUAQ3Def`) · 보고시트 (`AKfycbwSn7ZyfX`) | 읽기: 매출·지출 집계 | 매출지출현황 · 월간운영계획 · 매출회원현황보고 · 파트너팀 체계 | 시토(시뽀 큐 제외) | 읽기 거울 (`sync_sales.py`·`api_sales.py` · 보고시트 실배포 = `AKfycbznAmvB`) | **완료 09-04**(쓰기 10액션은 이중기록 단계로) | 09-04 |
| 9 | 지출현황 (`AKfycbzKIAxYYL`) · 리셉션 업무 (`AKfycbxcPsm-Xt`) · 라커관리 (`AKfycbyyN0I7od`) · renewal 개인 GAS (`AKfycbzY3ZvW_T`) | 각 1화면 | 지출현황 · 리셉션 업무/index · 라커관리 · renewal | 시토 | renewal = 거울(`sync_misc`·`api_misc`) · 리셉션 업무·라커 = 쓰기 이중기록(`/api/write` · 읽기는 GAS+서버 정상본 폴백) · 지출현황 = 보류(열람 0) | **완료 09-04**(지출현황만 보류) | 09-04 |
| 10 | 시트 내장·비화면 GAS: 텔레그램 매출보고 · 카톡방 목록(kakao_rooms) · 폼안내(`.deploy-forms`) · 웰리보이스 | 트리거·알림 | 화면 없음(봇·시트 트리거) | 시토 | **서버 cron 이전 대상 아님 — 4건 중 3건은 이미 대체·트리거 없음(§7 실측)** | **3/4 종료 09-04 · 웰리보이스만 미해결(info@ 로그인 필요)** | — |

**서버 원본 전환 1호 = #2 문의 폼** — 09-04 주소 교체 → 09-05·06·07 대조 3일 → **09-08 서버 원본**(시트는 되밀기). 이후 #3 → #4b → #5b → #6b 순으로 같은 3일 규칙.

## 3. 시모가 바꿀 주소 3개 (화면 fetch 주소만 · 본문·헤더 그대로 `text/plain` POST)

| 화면 | 지금 주소 | 바꿀 주소 | 비고 |
|---|---|---|---|
| `cmo/survey/wp_inquiry_form.html` · `_en` 의 `GAS_PROD` | `script.google.com/macros/s/AKfycbyLc2cnOe…/exec` | `https://erp.wellperion.com/api/intake/inquiry` | WP 8394·8408 재주입까지가 완료 · `ROLLBACK` 주석 줄에 옛 주소 남길 것 |
| `cmo/_api.js` 의 `intake` (instructor_intake.html 이 읽음) | `…/AKfycbz4wWhqIC…/exec` | `https://erp.wellperion.com/api/intake/instructor` | |
| `cmo/sunday/GM의일요일.html` (instructor 주소 재조회) | 〃 | `https://erp.wellperion.com/api/intake/sunday` | 같은 GAS 로 넘어감 · 서버에선 폼 이름만 다르게 남음 |

응답 = GAS 응답 그대로(`{ok:true,…}`) · GAS 가 죽으면 `{ok:true, queued:true, id, gas_status}` (손님은 성공 · 서버 행에 `error:…` 남음 · 아침에 `/api/intake/health` 로 실패 건수 확인). 응답에 CORS `*` 실려 있어 wellperion.com(http) 에서 그대로 읽힌다. 한도 = 본문 2MB · IP 당 분당 20회(초과 429).

## 4. 시모 퍼널 읽기 4액션 거울 규격 (#1c · 09-04 야간 창)

- `sync_funnel.py` (cron 5분): GAS `?action=funnel_conversion` · `funnel_conversion_detail` · `lesson_breakdown` · `period_breakdown&from=<이번달1일>&to=<오늘>` 및 최근 3개월 월별 range 를 떠와 `funnel_cache(tenant_id, action, params, data, synced_at)` 에 통째로 둔다.
- `api_funnel.py`: `GET /api/funnel/{action}?<GAS 와 같은 쿼리>` → 캐시 응답 그대로 + `_source=sheet-mirror` · 캐시에 없는 range 는 그 자리에서 GAS 1회 호출 후 저장(첫 조회만 느림).
- 화면(월간마케팅보고서·콘텐츠문의현황): `wpCmoFetch(GAS_URL + '?action=…')` → ERP 도메인이면 `/api/funnel/…` 먼저, 실패 시 GAS 폴백(시설부 체계.html 과 같은 규칙).

## 5. 되돌리기 한 줄

**화면의 저장·조회 주소를 GAS `/exec` 로 되돌린다(주소 1줄) — 데이터는 시트에 그대로 있고 서버 행은 남는다.**

### 5-1. 서버 원본 전환 절차 (사람이 한다 · 장치 = 배 960 레인 J · 2026-09-04)

1. `GET /api/intake/reconcile` 의 `streak_ok_days` 가 **3 이상**인지 본다(3일 연속 대조 무결 · 아니면 여기서 멈춘다).
2. 서버의 `/srv/erp/status/origin_switch.json` 에서 그 폼·영역 한 줄을 `"server"` 로 고친다(재시작 없음 · 본 = `server/erp_api/origin_switch.example.json`).
3. 10분 뒤 `GET /api/intake/health` 의 `pushback.unpushed` 가 **0**, `pushback.failed` 가 **0**, `last_pushed_at` 이 방금인지 본다.
4. 다음 날 아침 대조를 다시 본다 — 그 날 `mismatch` 가 0 이면 전환 성공(시트는 되밀기 사본으로 계속 찬다).
5. 이상이 보이면 그 줄을 `"dual"` 로 되돌린다 — 그 순간부터 종전 이중기록(코드 변경 0). 못 되민 행은 `status/pushback_failed.json`.

**server 모드에서 달라지는 것:** 화면은 GAS 왕복(최대 55초)을 안 기다리고 즉시 `{ok:true}` 를 받는다(응답이 빨라진다).
시트는 `pushback.py`(1분 cron)가 같은 본문을 그대로 되밀어 채우므로 실무진·기존 GAS 트리거는 영향 0.
대신 **GAS 응답값을 화면에 못 돌려준다** — 접수번호는 서버가 같은 모양(`L`+yyMMdd-HHmmss)으로 매기고, GAS 가 되밀 때
거부한 행(입력 검증·토큰)은 `gas-error` 로 남아 헬스·실패 파일에 뜬다. 그래서 **응답값을 쓰는 쓰기 영역은 전환 대상이 아니다**(폼부터 한다).

## 6. 오늘(09-03) 산출물

- `server/erp_api/api_intake.py` · `intake.nginx.conf` · `intake-zone.nginx.conf` · `server/deploy_intake.sh` · `schema.sql` 의 `intake_log` — 배포·selftest 검증 완료(무쿠키 POST 200 · intake_log 2행 tenant `selftest` · gas_status `skipped` · `/api/health` 는 그대로 401).
- 함께 오늘 완료: 레인 R·S·T 읽기 거울 3종 · 배 961 `/api/write`.

## 7. #10 시트 내장·비화면 GAS — 실측 결과 (2026-09-04 시토)

GM 「옮길 수 있는 것들은 옮겨야 하지 않아?」 에 대한 답 = **옮길 것이 없다.** 4건을 소스로 열어 확인한 결과 3건은
이미 대체됐거나 애초에 시간 트리거가 없고, 1건은 소스를 못 찾았다. 없는 일에 서버 cron 을 새로 만들면
같은 일을 두 장치가 하게 된다(약속 L21 중복 장치 금지).

| 잡 | 발신 대상·시각 | 시간 트리거 | 기존 파이썬 등가물 | 판정 |
|---|---|---|---|---|
| 텔레그램 매출보고 (`매출보고_자동발송.js` · GM 개인계정 scriptId `1f7Py-qdO6…`) | 텔레그램 `8254867551` · 매일 09:00 | 있음(`sendDailyReport` 일일) | `scripts/kakao_auto_daily_report.py` + `generate_sales_report_image.py` (예약작업 `Wellperion-Kakao-Sales-Report-0930` 09:30 · 텔레그램+카톡 4방) | **이미 대체 완료.** 트리거는 아직 돌지만 `sendDailyReport` 가 배99(2026-07-25)로 no-op — 발신 0. 라이브 소스 재확인 09-04 |
| `.deploy-salesreport/Code.gs` (보고시트 P20·I16·I18 쓰기 웹앱) | 발신 없음(시트 칸 쓰기만) | 없음 | 호출자 = `scripts/sales_report_ops_summary.py` (예약작업 08:00) | 트리거·발신 자체가 없는 **수신용 웹앱** — 이전 대상 아님 |
| 폼안내 (`.deploy-forms` · scriptId `1o8EfB_jMeX…`) | 발신 없음(구글폼 설명·마감 문구) | 없음 — oauthScopes 에 `script.scriptapp` 이 없어 **트리거 생성 자체가 불가**(라이브 clone 으로 확인) | 없음(사람이 에디터에서 손으로 돌리는 정비 함수) | 이전 대상 아님 |
| 카톡방 목록 (kakao_rooms) | 발신 없음 | 없음 | `server/erp_api/sync_kakao.py` (서버 cron 5분) | **이미 서버에 있음** — 읽기 거울 완료(배 922 레인 W) |
| 웰리보이스 | 불명 | 불명 | 불명 | **미해결.** 저장소 전체·cao@ GAS 13개 어디에도 없다. info@ 계정 또는 시트 내장 스크립트로 추정 — 소스 확보에 계정 로그인 선행 |

**GAS 트리거 끄는 순서(남은 것 = 매출보고 하나 · 급하지 않음).** 지금도 발신 0 이라 안 꺼도 이중 발신은 없다.
치우는 김에 지울 때만 이 순서로 한다: ① `status/kakao_auto_send.json` 의 `telegram_photo` 가 `true` 인지 확인
(09:30 파이썬이 유일 발신자라는 뜻) → ② GM/cao 가 GM 개인 구글계정 Apps Script 에서 `sendDailyReport` 시간
트리거 삭제 → ③ 다음 날 `logs/telegram_sent-<날짜>.log` 의 `sendPhoto` 가 하루 1건(09:30)인지 확인.
역롤백 = `telegram_photo` 를 `false` 로 되돌리고 `sendDailyReport` 의 배99 return 한 줄 삭제.
