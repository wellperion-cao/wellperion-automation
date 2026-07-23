# 지원부 주말 회차 정합 — 시우 인계 (웰리 작성 2026-06-27)

> GM이 시우(COO)에게 직접 지시한 작업. 웰리는 손 뗌. 이 문서 = 웰리가 오늘 만진 이력 + 진단 결과 인계(중복 진단 방지).

## 목표 (GM)
- 지원부 주말 점검 회차 정답 = **오전조 + 마감조 (남/여 각 2칸)**. 현재는 "오후조"로 잘못 표시.
- GM이 점검 항목 시트를 직접 수정함 + "이 시트를 한번만 매뉴얼에 적용 + 백·프론트 통일" 지시.
- ⚠️ GM이 말한 "**이 시트**"가 무엇인지(시스템이 읽는 `지원_매뉴얼` 탭 자체인지, 별도 정리 시트→매뉴얼 복사인지) **미확정** — GM이 시우에게 직접 알려준 것으로 보임. 시트 정본 먼저 확정할 것.

## 현재 라이브 상태 (안전)
- 점검 GAS home 사용 exec = `AKfycbyXw4...` **@122 = 원복 상태(수정 전과 동일)**.
- today_live(주말 2026-06-27): byGender.m/f 모두 **pmTotal=10**, am/close=0. home 화면 = 🚹지원부(남)/🚺지원부(여) 각 "오후조" 1칸(0/7).
- 레포도 롤백 커밋됨(`.deploy-check/지원팀 일일점검.js`).

## 오늘 웰리 이력 (반복 금지 교훈)
1. 주말 pm 제외 수정 시도(`_buildTodayMaster`에 `isWeekend` 분기) → 배포 @119~@121.
2. **결과: 주말 항목도 전부 pm 회차라, "주말 pm 제외"가 주말 데이터를 통째로 0으로 만듦**(total=0 → "회차 데이터 없음").
3. + clasp deploy를 deploymentId 없이 해서 home이 쓰는 URL(@118)이 아닌 새 URL(@119)에 배포된 혼선도 겪음(→ home deploymentId 지정 재배포로 해결).
4. @122로 **롤백 완료**. 라이브 점검 화면 즉흥 실험은 위험 — **로컬 모의 검증 후 1회 배포** 원칙 준수할 것(메모리 `project_support_check_zone_routing`).

## explore 진단 결론 (코드는 전부 정상)
- **`_shiftBucket`** (`.deploy-check/지원팀 일일점검.js:2475`): `"오전"→am` · `"마감"/"close"→close` · **나머지(오후 포함)→pm 폴백**.
- **`_roundBucket`**(2577): 회차값에서 숫자 제거 후 `_shiftBucket`.
- 점검페이지 `_check_support.js`: `ROUNDS_WEEKEND=[am1, close1]` (pm 없음·정상).
- home `parseGenderKpi`(main.html:10722): `byGender.{g}.{bucket}Total > 0`인 회차만 렌더(정상).
- **→ 유일한 변수 = 시트(`지원_매뉴얼`, SHEET_ITEMS) 주말 항목의 회차 컬럼(ITEM_ROUNDS_COL=10) 값.** 그게 `pm1`/`오후조`면 오후조로 나옴. **`am1,close1`(또는 `오전조,마감조`)로 바꾸면 코드 무수정으로 통일됨.**
- 반영 메커니즘 = 시트 직독(별도 sync 없음). 시트 고치면 다음 today_live부터 반영. home은 캐시 주의(no-store는 이미 적용됨, 커밋 af7b6646).

## 미해결·확인 필요 (시우가 풀 것)
- **시트 실값 혼선**: `action=items&dept=support` 응답이 회차 컬럼에 요일값(`sat`,`tue,fri`)이 들어있고 8개만 반환됨. 시트의 회차/일정 컬럼이 바뀌어 입력됐거나, items 액션이 다른 모집단을 봄 — **시트를 직접 열어 헤더·주말 항목 회차/일정 칸 실측**이 먼저.
- GM이 고친 "이 시트"가 `지원_매뉴얼`인지 별도 시트인지 확정 → 별도면 매뉴얼로 1회 반영.
- 통일 후 검증: 주말 today_live byGender가 am+close, home 주말 = 남/여 각 오전조+마감조 2칸 (오늘 토요일이면 라이브 즉시 검증 가능).

## 정본 위치
- GAS: `.deploy-check/지원팀 일일점검.js` (scriptId 1FLQAzjq, home exec AKfycbyXw4...)
- 시트: `지원_매뉴얼` 탭 (GAS 바인딩 스프레드시트)
- 프론트: `3. 웰페리온 가이드/wellperion_guide(main).html`(home), `_check_support.js`(점검페이지)
