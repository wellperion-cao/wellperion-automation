# Deep Interview Spec: 배14 지원부 점검 분모 단일출처 통일

## Metadata
- Interview ID: di-ship14-checkdenom
- Rounds: Round0(topology) + Round1(scope depth) + 실측 재라우팅
- Final Ambiguity: ~15% (threshold 20% 통과 — 전제 결함 발견으로 재스코프)
- Type: brownfield
- Generated: 2026-07-03
- Threshold: 0.2 (source: default)
- Status: PASSED — 단, 실측이 선결 결함 발견 → 실행 경로 재라우팅(GM 결정)

## Topology (Round 0 확정)
| 구성요소 | 상태 | 설명 | 커버리지/보류사유 |
|---|---|---|---|
| ① 분모 표시 전환 | active | 화면 collectDashboardData가 today_live 분모 표시 | **선결 미충족**: 서버 today_live 금요일 0 → 서버 수리 후 착수 |
| ② 항목 데이터 이관 | active | 하드코딩 배열·localStorage → 시트 단일화 | localStorage=이미 서버 진실(유실 위험 낮음). 항목 드리프트 34 vs 49 확인 |
| ③ 독려 정합 | deferred | daily_scheduler today_live 읽기 | 확인만(이미 정합 추정) |
| ④ 라이브 배포·검증 | deferred | 로컬 모의 후 라이브 1회+역롤백 | 별도 GM go |

## 핵심 발견 (실측)
- 서버 `today_live`가 **오늘(2026-07-03 금, dow=5) 분모(total)=0** 반환. 인접 평일(목 25/14/13·화 정상) 정상. → done=0(아침)이 아니라 **분모 붕괴**.
- 동일 증상 = `kpi_values` coo 점검완료율 `null`("rows 없음") = 배239 collector null의 **상류 원인**.
- 항목 구성 드리프트: 화면 배열 34개 vs 시트 49개(요일별 청소항목 15개 차이).
- localStorage custom/hidden = 이미 서버 단일 진실(HTML 1630줄) → ② 유실 위험 낮음.

## 결정 (GM 라우팅)
**서버 이상치부터 — 시토 배관, 배239 통합.** 배14 화면 전환(①)은 서버 today_live 금요일 정상화 후 착수. 진단서 = `status/briefs/COO-2026-07-03-TODAYLIVE-FRIDAY-ZERO-HANDOFF.md`.

## 재스코프된 실행 경로
1. [시토·배239 통합] today_live 금요일 dow=5 분모 0 근본원인 진단·수리(로컬 검증 → GM go 배포·역롤백). 진단 리드=핸드오프 진단서.
2. [시토] 수리 검증 → coo 점검완료율 collector 실측 개통(배239 원목표).
3. [시우·배14 ①] 서버 정상화 확인 후 화면 collectDashboardData 분모를 today_live로 전환(하드코딩 계산 경로 제거). 로컬 모의 후 라이브 1회+역롤백.
4. [시우·배14 ②] 항목 드리프트(34→49) 정합 — 화면 항목 렌더도 시트 기준(후속).

## Non-Goals (이번)
- 서버 코드 직접 수리를 시우가 하지 않음(배관=시토). 시우=지표 의미·검수.
- 라이브 배포 이번 세션 안 함(별도 GM go).

## Acceptance Criteria (배14 ① 최종, 서버 수리 후)
- [ ] 서버 today_live 금요일 분모 정상(공용+성별 항목 반영, 0 아님)
- [ ] 화면 분모 = 서버 = 독려 동일 숫자(시크릿 크롬·기기 무관)
- [ ] 하드코딩 WEEKDAY/WEEKEND 분모 계산 경로 제거
- [ ] 회귀 0: CHKNOTI dedup·이슈집계·제출 영속 무변경

## Ontology (Key Entities)
| Entity | Type | 비고 |
|---|---|---|
| today_live | 서버 응답 | byGender m/f/all · amTotal/pmTotal/closeTotal(분모) · done |
| 분모(total) | 지표 | 시프트별 점검 대상 항목 수. 성별별(남≠여 가능) |
| 점검항목(item) | 도메인 | 시트 SHEET_ITEMS 단일 진실. sched(요일|주차) 필터 |
| collectDashboardData | 화면 함수 | 현재 하드코딩 배열 분모 계산(전환 대상) |
| 시프트 | 분류 | am/pm/close/night(night=분모 제외) |
