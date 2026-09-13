# 주간 페이지 위생 정리안 — 20260913 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: 전체

## 시설부 체계 — `3. 웰페리온 가이드/coo/check/시설부 체계.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] `tb2` — boardMakeGridRow 함수 / btnD.onclick 핸들러 — tb2에 tr.parentNode를 할당하나 이후 어디에도 참조되지 않음. tr.remove() 단독으로 충분.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 136건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 하단 — 규정 탭 CSS 섹션 — #policy-board display:contents 동작 설명이 CSS 주석(이 항목)과 HTML 주석(#policy-flow 내 '<!-- 단일 트렐로 칸반 흐름: 정기회의(JS 렌더 컬럼) → ... -->') 두 곳에 중복. 한 곳으로 통합 가능.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [js-function] `fmEsc` — FM_DEPT 선언 직후(월간보고 탭 섹션) — mpEsc는 MP_DEPT 선언 직후(이달 부서 현황 탭 섹션) — fmEsc·mpEsc 두 함수의 본문이 바이트 단위로 동일하며, 이 파일에는 piece 1/2에 정의된 escapeHTML까지 포함하면 동일 로직이 3개 존재함
  - 게이트: 근거: 리포 참조 25건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (14건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-fcheck 직전 — tab-monthly 주석 앞 — 이미 완료된 탭 제거·코드 삭제를 기록한 주석. 해당 기능 전부 소멸, 주석만 잔존.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — .tabs 영역 — fcheck 탭 버튼 앞 주석 — 제거 완료된 탭에 대한 완료 메모 주석. 구 탭은 이미 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — .tabs 영역 — monthly 탭 버튼 뒤 주석 — 폐기 완료된 탭 버튼 제거 메모. 버튼은 이미 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #policy-flow 내부 — 근무·휴게 board-col 닫힘 뒤 — 이관 완료된 마이그레이션 완료 메모 주석. 컬럼은 이미 제거됨.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #policy-flow 내부 — 직원 구성 주석 바로 뒤 — 분리 완료된 컬럼 삭제 메모. 해당 컬럼은 이미 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-policy 최하단 — /board-fullwidth 닫힘 태그 뒤 — 이관 완료된 개발 메모. 이관 대상 콘텐츠는 이미 이 파일에 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-manual 최상단 — .board-intro 앞 — 이관·재구성 완료된 개발 메모. 대상 코드는 이미 제거됨.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — saunaTbl 함수 정의 직전 단독 주석줄 — 이미 완료된 제거 작업 이력. 현재 코드에 없는 topBox·fcRender를 언급해 독자 혼란 유발.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — const SAUNA 배열 선언 줄 끝 인라인 주석 — 과거 구조 변경 이력. 현재 코드(A칸만 정의)에 이미 반영돼 주석 없이도 자명.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — FC_RANGE_MAP 초기화 설명 블록 내 4줄 주석 — 판정에 미사용이라고 명시된 구 하드코딩 참조값. 계약서 이관 후 '참고용'으로만 잔류하며 실질 정보 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — BROJAY_ITEMS 정의 직전 / 안전점검 제거 이력 3개 블록 중 첫 번째 — 이미 삭제된 안전점검 카테고리의 1차 변경 이력. 커밋 메시지 수준의 내용이 코드에 잔류.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 안전점검 제거 이력 3개 블록 중 두 번째 — 이미 제거된 fc_ai_alarm 항목의 결정 근거 기록. 해당 항목은 현재 코드에 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 안전점검 제거 이력 3개 블록 중 세 번째 — 안전점검 카테고리 전체 제거의 의사결정 기록. 이미 완료된 작업의 사후 이력이 코드에 잔류.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `fcRoundTime` — function fcRenderRoundTime 선언 직전 단일 행 주석 — #fcRoundTime 폐지 마이그레이션은 이미 완료 — 현 코드 전체에 #fcRoundTime 참조가 없으므로 이행 안내 부분은 낡은 기록임
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### D. 장황 단순화 (6건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-fcheck 최상단 — #facLegalAsk div 바로 앞 — 배치 이유·설계 철학을 3줄로 서술. 한 줄 요약 메모로 대체 가능하며 실무 가독성에 기여 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] `FM_RETIRED_CATS` — var FM_RETIRED_CATS 선언 직전 5행 주석 블록 — 감사 경위·83칸 수치·폐지 사유 5행 서술 — FM_RETIRED_CATS 선언값('2026-08-26 폐지 — 입력 화면에 칸 없음')과 renderFmCategory 하단 ※ 문구로 이미 표현되어 중복 장황
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [verbose-block] `fmMergeCats` — function fmMergeCats 선언 직전 6행 주석 블록 — 과거 버그 발생 경위를 6행에 걸쳐 서술 — 함수 목적('카테고리명 변형 정규화 후 집계')은 1행으로 표현 가능. 구체적 수치(80칸·9칸·2일치)는 독자 맥락 없이는 오히려 혼란 유발
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [verbose-block] `renderFmKpi` — renderFmKpi 함수 내부, el.innerHTML 할당 직전 3행 주석 — 완료된 라벨 변경에 대한 감사 경위·예시 수치를 3행 서술 — '점검한 날 수'라는 라벨 자체가 의도를 표현하므로 추가 설명 불필요
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [verbose-block] `renderA3FacilityMonthlyFromData` — renderA3FacilityMonthlyFromData 내부, catRows 변수 선언 직전 2행 주석 — 수정 완료된 버그의 발생 경위 2행 서술 — 현재 코드('fmSortByCat(fmMergeCats(...))')가 이미 수정 의도를 표현하므로 경위 주석은 장황
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [verbose-block] `fcSave` — window.fcSave 함수 내부, _abNote/_abText 변수 선언 직전 3행 주석 — GM 질문 사례·대화 맥락을 3행 서술 — 변수명(_abNote·abnormalNote)과 폴백 삼항 로직이 이미 의도를 표현하므로 경위 설명 불필요
  - 게이트: 근거: 리포 참조 15건(git grep 실측) — 확인 필요

## 지원부 체계 — `3. 웰페리온 가이드/coo/check/지원부 체계.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [js-function] `inspMemoBoxHtml` — escapeAttr 함수 바로 다음 블록 — drawUI 내 주석 '다른 참조 없음' 명시 — 렌더에서 메모칸 제거 후 상태 변수(window._inspMemo, _inspMemoTimer)와 두 함수(inspMemoBoxHtml, onInspMemoInput)가 호출 없이 잔존
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [js-function] `quickAddBarHtml` — JS — quickAddOpen 함수 직전 — GM 지시(2026-06-12)로 삭제된 기능의 스텁. 항상 '' 반환 — 어떤 호출부도 의미 있는 출력을 받지 못함
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 13건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `cdp-grid` — #a3-closedday-print 내 .cdp-grid 블록 (동일 내용이 #tab-manual .manual-section .cd-grid에도 존재) — 둘째주 휴관 작업 전체 목록(A사우나/B락커룸/C내부/E외부)이 인쇄용 컨테이너(cdp-* 클래스)와 매뉴얼 탭 .manual-section(cd-* 클래스)에 각각 별개 정적 HTML로 이중 하드코딩되어 한쪽 수정 시 나머지에 반영되지 않는다.
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (7건)
- [stale-notice] `mrp-main-title` — #a3-monthly-print 내 .mrp-main-title 및 .mrp-footer('본 요약은 2026-06-30 기준') — A3 월간보고 인쇄 컨테이너 본문 전체가 '2026년 6월 작업 요약(2026-06-30 기준)'으로 정적 하드코딩되어 현재(2026-09-13) 기준 2.5개월 경과. 다른 인쇄 컨테이너(csguide·supply·onboarding 등)는 모두 'JS가 … 주입' 주석이 있으나 이 컨테이너는 없어 인쇄 시 구버전 문서가 그대로 출력됨.
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
- [stale-notice] `FALLBACK_STAFF` — JS 초기화 블록 FALLBACK_STAFF 상수 — 2026-09-04 개편된 현 DUTY_ROSTER(우춘화·이연희·김미영·이경미·천진석·박남일·김훈)와 불일치. 이경연 실장·임정은M·최준용M·윤병현AM은 현 근무조에 없으며 isNightShiftWorkerG 등 fallback 경로가 잘못된 shift:'all' 기준으로 실행될 수 있음.
  - 게이트: 근거: 리포 참조 14건(git grep 실측) — 확인 필요
- [stale-notice] `inspMemo_removal_comment` — drawUI 함수 내 — zoneOrder.length===0 분기 직전 라운드 모드 블록 — A 후보(inspMemoBoxHtml 클러스터) 정리 시 함께 의미 없어지는 설명 주석
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `resetManualLocalView_removal_comment` — renderManualItems 함수 닫힘 직후, togManualItem 정의 앞 — 이미 삭제된 함수에 대한 잔류 주석 — 참조할 코드가 없어 맥락 없이 부동
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `wpLdyRenderToday_dead_notice` — wpLdyGoOpening 함수 다음, wpLdyRenderToday 정의 바로 위 — wpLdyRenderAll이 wpLdyRenderToday를 호출하지 않음이 확인된 dead 함수 표시 주석 — 함수 본체가 청크 말미에서 잘려 완결 스니펫 제공 불가(함수 전체는 별도 A 검토 대상)
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `STAFF_SEED` — JS — const STAFF_SEED 배열 첫 번째 항목 — '6월말 퇴직 예정'은 2026-09-13 현재 이미 경과한 시점 — 시드 활성화 시 완료된 사건을 예정으로 표시
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [stale-notice] `mrSubmitBreakdown` — JS — mrSubmitBreakdown 함수 반환 HTML 마지막 문단 — 2026-08-25 8월 실측 수치를 '이달' 예시로 하드코딩. 9월 이후 매달 KPI 설명 카드에 구 수치가 영구 노출됨
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] `day-focus-section` — <style> 블록 내 .day-focus-section / .day-focus-title 정의 — const DAY_FOCUS={} 가 주석('하드코딩 비움 — no-op')에 따라 의도적으로 항상 빈 객체여서 이 CSS가 붙을 동적 마크업이 생성되지 않으며, 정적 HTML에도 해당 클래스 사용처가 없음.
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [js-function] `groupSubmitBarHtml` — collectGroupSubmits 함수 바로 다음 — 항상 빈 문자열 반환 — renderItem·야간 drawUI에서 다수 호출되지만 출력이 없어 모든 호출이 무연산; 완전 제거는 호출부(html+=groupSubmitBarHtml(...)) 다수를 함께 정리해야 함
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
- [verbose-block] `wpLdyRenderMonth` — JS — wpLdyAddNewInput 직후 약 80행 함수 — 자체 주석이 '2026-09-04 이후 UI 호출 없음'을 명시. 실행 시 wpLdyCards 엘리먼트 부재로 즉시 return. 실검산 트리거 없어 코드 부피만 점유
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요

## 운영부 체계 — `3. 웰페리온 가이드/coo/check/운영부 체계.html`
- (정리 후보 없음)

## 주차관리부 체계 — `3. 웰페리온 가이드/coo/check/주차관리부 체계.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `mode-badge` — CSS <style> 블록 line 24 — 파일 내 HTML 요소 및 JS 어디서도 class='mode-badge'를 사용하는 곳이 없음 — 페이지 고유 <style> 블록에만 존재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 7건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (6건)
- [duplicate-text] `타임라인 도식` — tab-policy > 근무·휴게 시간 accordion > manual-body, 타임라인 도식 블록 — 바로 아래 <table>이 근무자 A(정시~50분 근무·50분~정시 휴게)와 근무자 B(10분~정시 근무·정시~10분 휴게)를 동일하게 정리하고 있어 다이어그램과 표가 같은 정보를 이중 표시함
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [duplicate-text] `pm_weekly` — PARK_MANUAL_SEED.pm_weekly.body ↔ A3_MANUAL.right[2].weekly 7행 테이블 — 요일별 집중점검 7일 일정이 편집 가능 매뉴얼 카드(pm_weekly)와 A3_MANUAL 정적 상수에 각각 하드코딩돼 GM이 카드를 수정해도 A3 인쇄물에 반영 안 됨
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [duplicate-text] `pm_clean` — PARK_MANUAL_SEED.pm_clean.body ↔ A3_MANUAL.right[3].subs[0].lines ↔ A3_GUIDELINE.guide[5].lines — 주차관리인 청결관리 내용이 편집 가능 보드 카드·A3 매뉴얼·A3 가이드라인 3곳에 동일 기재돼 변경 시 3중 수동 수정 필요
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [duplicate-text] `pm_valet` — PARK_MANUAL_SEED.pm_valet.body ↔ A3_MANUAL.right[5].subs[0].lines ↔ A3_GUIDELINE.policy[6].lines ↔ A3_GUIDELINE.guide[6].lines — 발렛 입출차 절차가 편집 가능 보드 카드·A3 매뉴얼·A3 가이드라인 policy·guide 4곳에 각자 하드코딩돼 요금·절차 변경 시 최소 4곳 수동 수정 필요
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [duplicate-text] `pg_clean__pm_clean` — PARK_GUIDE_SEED.guide id='pg_clean' (JS ~line 1194) / PARK_MANUAL_SEED.manual id='pm_clean' (JS ~line 1220) — 가이드 탭과 매뉴얼 탭에 '주차관리인 청결관리' 항목이 문장 수준으로 거의 동일하게 중복
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `교대휴게_타임라인_표` — 근무·휴게 시간 아코디언 — 시각 타임라인 바(lines ~615-640) 직후 동일 내용 table(lines ~642-659) — 근무자 A/B 교대 휴게 규칙을 시각 바 차트와 표 두 번 반복 — 화면에 나란히 위치
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (7건)
- [stale-notice] `version-badge` — header > h1 내 버전 배지 — v1.1·2026-08-18 이후 2026-09-11 GM 지시로 점검 탭 구조·UI·조 버튼·제출 바·날짜 바 등 다수 변경되었으나 버전 표시가 갱신되지 않음
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [css-class] `group-submit-bar` — <style> 블록 — 2026-09-11 점검 탭 전면 개편(단일 park-submit-bar + parkingSubmitBtn)으로 그룹별 제출 버튼 UI가 제거된 것으로 보이나, JS가 truncate되어 renderParkingDailyCheck 내 사용 여부 미확인 — 확정 보류
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [stale-notice] `AI 초안` — printA3ParkingChecklist 함수, host.innerHTML 조립 시작부 — PARK_CHECKLIST.daily 주석에 '2026-09-11 GM 확인'이 명시돼 14개 항목이 승인됐으나 인쇄 헤더의 '[AI 초안 — GM 검토]' 배지가 제거되지 않아 인쇄물마다 미검토 상태로 출력됨
  - 게이트: 근거: 리포 참조 26건(git grep 실측) — 확인 필요
- [stale-notice] `GAS 미연동` — PARK_ROUNDS_WEEKDAY 선언 직전 섹션 헤더 주석 — printA3ParkingChecklist가 이제 PARK_ITEMS(loadParkItemsFromServer·saveItems 서버 연동)를 읽으므로 '지원부 점검 GAS 미연동·제출/저장/API 없음·화면 매뉴얼 탭 하드코딩' 설명이 현재 구현과 불일치
  - 게이트: 근거: 리포 참조 14건(git grep 실측) — 확인 필요
- [stale-notice] `충원 진행 중` — A3_GUIDELINE.policy[0].lines[3] 및 A3_MANUAL.right[4].subs[1].lines[0] — PARKING_TABLES.staff는 GM 실시간 편집 가능하나 A3_GUIDELINE·A3_MANUAL의 '충원 진행 중' 문구는 정적 상수라 오후조가 충원돼도 인쇄물에 '충원 진행 중'이 자동 반영 안 됨
  - 게이트: 근거: 리포 참조 18건(git grep 실측) — 확인 필요
- [stale-notice] `v1.1_2026-08-18` — header h1 인라인 span (HTML line 528) — 2026-09-11 GM 지시로 날짜 이동·타이머·주간점검 폐지·항목 화면편집 등 대규모 기능 추가가 있었으나 버전 배지는 v1.1·2026-08-18 그대로
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `AI_초안_GM_검토` — printA3ParkingChecklist 함수 내 html 문자열 (JS ~line 2142) — JS 주석 line ~2047 '2026-09-11 GM 확인 — 항목 14개'로 GM이 이미 점검 항목을 확정했으나 A3 인쇄 헤더에 'AI 초안' 라벨이 남아있음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (4건)
- [verbose-block] `공지문_법조항_설명단락` — tab-guide > 주차장 이용 안내 공지문 accordion > manual-body, 두 번째 단락 — 법 조항 검토 경위는 작성자 기록용으로, 이 아코디언을 열어 링크 버튼을 쓰는 현장 직원에게 불필요한 장황 설명; 법 조항 본문은 링크된 별도 문서(주차장_이용안내_공지문.html)에 있음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `snapshot_append` — submitParkingDailyCheck 함수, snapshot_append erpCheckPost 호출 직전 — 버그 수정 이력·실측 수치·타 부서 비교를 7줄로 나열하는 changelog 주석 — 현재 WHY는 '집계 원장이 snapshot 시트 기반이라 save 후 별도 호출 필요' 한 줄로 충분하고 날짜·실측값은 PR 설명에 속함
  - 게이트: 근거: 리포 참조 39건(git grep 실측) — 확인 필요
- [verbose-block] `unlock_round` — loadParkingCheckState 함수, _submitted 판정 직전 — 버그 수정 경위·과거 오동작·지원부 비교를 5줄로 설명하는 changelog 주석 — 현재 의미는 '잠금 판정=checkedLedger.sub, 시트 행은 폴백' 한 줄로 충분
  - 게이트: 근거: 리포 참조 34건(git grep 실측) — 확인 필요
- [dead-markup] `parkChecklistDailyN` — renderParkingDailyCheck 함수 (JS ~line 2580) — id='parkChecklistDailyN'인 HTML 요소가 파일 내 존재하지 않아 getElementById가 항상 null 반환; if(dN) 가드로 무해하지만 의미 없는 참조
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전

## 파트너팀 체계 — `3. 웰페리온 가이드/coo/check/파트너팀 체계.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-id] `claude-agent-glow-border-inner` — <head> 말미 wp-typography.css 링크 위 — DOM에 #claude-agent-glow-border-inner 요소 없음 — Claude 에디터가 주입한 글로우 애니메이션 블록
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [css-class] `day-type` — 첫 번째 <style> 블록 — .mode-badge 앞 4줄 — HTML 본문 및 JS 템플릿 문자열 어디에도 day-type 클래스 없음 — 체크리스트 템플릿 복사 잔여
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 44건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `ERP_API_ON` — IIFE 내 fetchWorkTodoList 선언 직전 — 두 번째 ERP_API_ON 선언 — 동일 IIFE 상단(pubGet 근처)에 이미 var ERP_API_ON 선언·할당됨; var 재선언은 무의미
  - 게이트: 근거: 리포 참조 167건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `SEED` — IIFE 내 MONTH_TARGET_SUM 계산 앞 — 폴백 데이터 내 '진행중' 5건 종료일이 2026-04~07 — 오늘(2026-09-13) 기준 모두 경과; API 실패 시 노출되면 완료 업무가 진행중으로 표시됨
  - 게이트: 근거: 리포 참조 172건(git grep 실측) — 확인 필요
- [stale-notice] `tab-guide` — 첫 번째 <style> 블록 — .content{padding:16px...} 바로 뒤 — #tab-guide 요소는 DOM에 없음(실제 ID는 #tab-ptguide) — 탭 ID 개명 시 CSS 미갱신 오타
  - 게이트: 근거: 리포 참조 50건(git grep 실측) — 확인 필요
- [stale-notice] `pubGet` — IIFE 내 pubGet 함수 선언 직전 — 2026-08-04 배관 분리 후 '구매요청과 같은 Apps Script' 설명이 사실과 다름; 바로 위 주석이 분리를 이미 명시해 내용 충돌
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `WORK_TODO_API` — IIFE 내 var WORK_TODO_API 선언 바로 위 5줄 — 해소된 localStorage 캐시 버그 경위를 5줄로 설명; 현재 구현(GAS 직접 호출)이 근거를 자명하게 대신
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요

## 전사_일정 — `3. 웰페리온 가이드/coo/check/전사_일정.html`
### C. 낡은 안내·버전 배지 (3건)
- [css-class] `cal-head` — CSS — .cal-head 규칙 블록 — 달력 내비게이션이 h1.title-row > .cal-nav 으로 이동(GM 지시 2026-08-29)된 뒤 HTML·renderCalendar() 어디에도 cal-head 요소가 생성되지 않는다
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [css-class] `flash` — CSS — .row.flash 및 @keyframes calFlash — highlightDate()가 renderDayPanel()로 교체된 이후 인라인 JS 전체에서 flash 클래스를 추가하는 코드가 없다
  - 게이트: 근거: 리포 참조 11건(git grep 실측) — 확인 필요
- [stale-notice] `uploadEvidence` — JS uploadEvidence 함수 — GAS 응답 오류 처리 분기 — 현재 커밋 번호 990+이며 배574는 이미 오래 전 배포됐다; 이 분기에 빠지면 사용자에게 잘못된 재시도 안내를 준다
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
### D. 장황 단순화 (4건)
- [css-class] `ecard-na` — CSS — .ecard.na 규칙 — 인라인 JS·HTML 어디서도 ecard 요소에 na 클래스를 부여하지 않는다
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — HTML — .calwrap 바로 위 삭제 경위 주석 — 타일이 이미 제거된 뒤에도 3줄 삭제 경위 주석이 남아 마크업 가독성을 해친다
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — JS — _pastOpen 변수 선언 직전 삭제 경위 주석 — 삭제된 함수의 경위를 설명하는 주석이 남아 코드 스캔 시 혼란을 준다
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — CSS — .title-row 규칙 직전 삭제 경위 주석 — 이미 존재하지 않는 CSS 규칙에 대한 삭제 경위 주석이 불필요하게 남아 있다
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 업무 현황 SSOT — `3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] `deptHeadFor` — JS 상수 블록, OWNER_COLORS 선언 직후 — 카테고리 자동 부서장 삽입 폐지(2026-06-17 COO A) 이후 deptHeadFor()를 호출하는 코드가 이 파일에 없음; CAT_DEPT_HEAD는 이 함수에서만 사용
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [dead-markup] `PLAN_TEMPLATE` — JS, REJECT_MARK 상수 정의 아래 — 문서 자동채움은 buildDocTemplate()과 CATEGORY_TEMPLATES가 전담하며, PLAN_TEMPLATE를 참조하는 호출부가 코드 어디에도 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [dead-markup] `BUDGET_CATEGORIES` — JS, routeApproval() 함수 직전, 결제 권한 기준 v2.0 주석 아래 — BUDGET_CATEGORIES를 참조하는 코드가 전혀 없음; 예산 선택지는 HTML select 옵션에 하드코딩, 라우팅은 routeApproval() switch에서 문자열 직접 비교
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [dead-markup] `updateHeaderSub` — updateHeaderSub() 함수 본문, return; 주석 줄 다음 5줄 — 함수 첫 줄 return;이 항상 실행되므로 이후 5줄이 영구 도달 불가(unreachable dead code)
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 10건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — renderQeval → hdrFields 조립 직전 — renderTodoTable 에도 '헤더 2장을 맨 앞에 둔다 — 그리드 자동배치…' 주석이 거의 동일 구조로 존재 — 그리드 레이아웃 원리 설명이 두 함수 내에 중복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (5건)
- [stale-notice] `ERP_API_ON` — fetchTodoList() 선언 바로 위, TODO_API_URL 아래 — 2026-09-06 지혈 되돌림으로 ERP_API_ON이 항상 false → fetchTodoList() 내 /api/todo fetch 분기 전체가 영구 사문화됐으나 '근본 수리는 권한 밖' 주석으로 장기 잔류 예상
  - 게이트: 근거: 리포 참조 167건(git grep 실측) — 확인 필요
- [css-class] `chip approval` — CSS, .task-meta 칩 스타일 그룹 — renderTaskCard()의 결재 칩은 전부 inline style로 렌더링하며 chip.approval 클래스를 적용하는 코드가 이 조각에서 발견되지 않음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [css-class] `approval-filter` — CSS, .filter-btn 스타일 그룹 — buildFilters()가 생성하는 필터 버튼 어디에도 approval-filter 클래스를 부여하는 코드가 없음 — 과거 결재 필터 버튼 기능의 잔해로 추정
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — renderTodoTable → var ymd 함수 선언 내부 4줄 주석 — '원문 절단 방식' 버그는 kstDateStr 전환으로 이미 해소됐고, '카드 배지 반대 방향 하루 밀림' 별개 결함 메모도 2026-08-24 이후 현황 불명 — 두 항목 모두 현행 코드에 대응하는 설명이 없음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — qevDecodeDateScore 함수 직전 블록 주석 후반 5줄(2026-08-25 수정 단락) — '이전 버전' +9h 보정 로직은 이미 제거됐으므로 그 실패 경위를 서술하는 5줄은 현행 코드에 대응하는 내용이 없음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] `OWNER_COLORS` — JS 상수 블록, OWNER_CHIP · OWNER_COLORS · CAT_CHIP · CAT_COLORS 선언 — OWNER_COLORS 8개 항목 모두 동일한 OWNER_CHIP 참조, CAT_COLORS 9개 항목도 모두 CAT_CHIP — 확장점을 위한 룩업 구조지만 현재는 단일 상수와 기능적으로 동일해 17줄 반복이 가독성 부담
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — IIFE 시작부 직전 4줄 블록 주석 — GAS 계산 위임 방침과 두 판 분리 결정을 4줄로 서술하나 운영에 필요한 정보는 '서버가 계산, 화면은 표시만' 한 줄로 충분 — 나머지는 과거 의사결정 맥락
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — var QEVAL_R_SCORE 선언 직전 14줄 블록 주석 — 산식 요약·데이터 게이트·구버전 정체 판정 실패 경위가 14줄에 걸쳐 서술돼 있으나, 현행 운영 참조에는 산식 한 줄 + 정체 규칙 인라인 주석으로 충분하고 '종전 규칙' 실패 경위는 이미 해소된 내용
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 결재 현황 SSOT — `3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html`
### A. 죽은 코드(자동삭제 대상) (5건)
- [css-class] `sheet-links` — <style> 블록 상단, .header h1 아래 — DOM 전체에 class="sheet-links"를 쓰는 요소가 없음. 헤더는 .sheet-link(단수)·.header-right를 사용하며 .sheet-links(복수)는 어디서도 참조되지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 57건(git grep 실측) — 확인 필요
- [css-class] `card-link-btn` — <style> 블록, .deeplink-highlight 바로 위 — 2026-06-03 GM 확정으로 카드별 링크 버튼이 제거됨(renderApprovalCard 주석 확인). 이후 어떤 render 함수도 card-link-btn 클래스를 출력하지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [css-class] `kanban-col.col-rep` — <style> 블록, .kanban-col.col-done/.col-reject 인접 — renderKanban()의 COLS 배열에 cls:'col-rep'가 없음. 2026-06-16 대표 단계 폐지로 col-rep 컬럼 자체가 삭제됐으며 이후 .col-rep이 부여된 요소가 전혀 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [js-function] `getUser` — JS 본문, updateHeaderSub 바로 위 — updateHeaderSub() 내 return; 이후의 도달불가 코드에서만 호출됨. 파일 전체에서 getUser() 호출부는 해당 dead-body 한 곳뿐
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [js-function] `setFilter` — JS 본문 하단, toggleDetail 바로 위 — 상태 필터 버튼(전체/진행중/완료/반려)이 삭제된 이후 render() 내 어떤 onclick도 setFilter를 참조하지 않음. applyUrlParams는 activeFilter를 직접 설정하며 setFilter를 거치지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `updateHeaderSub` — updateHeaderSub 함수 내 return; 이후 — return; 뒤에 오는 6줄은 어떤 실행 경로로도 도달 불가. 2026-05-30 GM 결정으로 동결됐으나 함수 본문이 그대로 남아 있음
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
- [stale-notice] `__PV` — <head> 내 캐시 버스팅 스크립트 최상단 — 빌드 버전이 2026-07-18 이후 갱신되지 않음. 서버에서 fetch한 최신본의 __PV 값이 이와 같으면 캐시 강제갱신이 발동하지 않아 사용자에게 옛 페이지가 남을 수 있음
  - 게이트: 근거: 리포 참조 14건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `print_options_comment` — </body> 직전, print_options.js <script> 앞 주석 — 8줄짜리 히스토리 주석으로, 현재 구현에서 이미 해결된 충돌 경위를 설명. 실무진이 기능을 이해하는 데 필요한 정보가 아니며 PR 설명이나 changelog로 이전 가능
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 공지 템플릿 — `3. 웰페리온 가이드/coo/notice/notice_template.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `ntool-img-btn` — <style> 블록 — .ntool-img-btn 룰셋 2개 — 마크업 전체에서 class="ntool-img-btn" 참조 0건. 이미지 업로드 버튼(label)은 inline style로 대체되어 있으며 이 클래스는 어떤 요소에도 적용되지 않음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 4건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `title` — <head> — <title> 태그 — <title>은 v2.1이지만 topbar h1 텍스트는 '내부게시물 생성 v2.2'로 버전 불일치.
  - 게이트: 근거: 리포 참조 26560건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `imgHtml` — ntCollectData() 함수 내부 — 반환 객체, ntCaptureToCanvas → ntBuildPageHtml 인자로 3단계 경유 — 주석에 '폐기' 명시. 항상 빈 문자열('')로 선언되어 ntBuildPageHtml 본문 연결(bodyHtml+imgHtml)에 실제로 아무것도 추가하지 않음. 함수 시그니처 세 곳에 잔존하는 흔적.
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [verbose-block] `fs` — ntUpdatePreview() 함수 내부 — ntUpdatePreview에서 fs는 선언 후 한 번도 참조되지 않음. 본문 기본 크기는 var fsVmin=(18*0.17).toFixed(2) 하드코딩으로 직접 산출하므로 fs가 쓰일 자리가 없음(v2.58 주석이 이 결정을 설명).
  - 게이트: 근거: 리포 참조 5728건(git grep 실측) — 확인 필요

## 메인가이드 O1(운영통합체계) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### C. 낡은 안내·버전 배지 (5건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — O1 #o1-module-hub 인라인 스크립트 상단 첫 번째 주석 줄 — 「Pages 서빙 후속·front_card 스키마 예약」은 미래 계획 메모 — 2026-09-13 현재 이행 여부 불명확하며 TO-DO 노트처럼 남아 있음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — O1 #o1-module-hub 스크립트 내 apiFirst 재사용 설명 주석 (withTimeout 호출 직전) — 「위 734행」은 절대 행 번호 참조 — 파일 수정마다 틀어지는 stale 위치 주석
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — O1 #o1-month-section 내부 마지막 div (이번 달 details 패널 하단) — 배선이 완료된 이후에도 이 텍스트가 남아 있으면 오보 — 완료 시점에 제거 또는 동적 조건부 표시로 교체 필요
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `placeholder-note` — O1 > 5번 락커 관리 manual-section > manual-body 마지막 placeholder-note — "윤병현AM 작업중 · 실무 입력 대기" 문구에 날짜 없이 남아 있어 작업 완료·취소 여부 확인 불가.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [stale-notice] `evalEl` — O1 IIFE > loadMonth 함수 > evalEl.innerHTML 할당 (o1-month-eval 렌더링) — 2026-08-27 실측 정적값이 3분기 내내 갱신 없이 고정 노출됨. 54/100 점수·"종합접수처 미결을 닫으면 ①③이 오른다" 액션 아이템의 현재 유효성 확인 필요.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — O1 #o1-siljang-today 섹션 바로 앞 HTML 주석 — ▸1차·▸2차 개발 경과를 7줄로 기록한 리비전 이력 주석 — 3차 구현이 이미 적용된 후 운영자에게 불필요한 과거 시도 기록
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — O1 #o1-month-section 닫힘 직후·#o1-docs-archive 열림 직전 HTML 주석 — 설계 구조(1·2·3·4층)와 구현 패턴을 6줄 HTML 주석으로 서술 — 층별 구조는 이미 화면 UI로 드러나 있어 주석 설명이 중복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — O1 #o1-module-hub 스크립트 블록 바로 아래 HTML 주석 — 이미 삭제된 요소의 삭제 사유를 설명하는 자기참조 주석 — '없는 것'을 설명하며 운영 가치 없음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 메인가이드 O2(공지) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [dead-markup] `gm1InProgressCount` — gm1FetchSsot() 내 ── ② _queue.json 집계 블록 — queue가 'var queue = []'로 하드코딩돼 forEach가 무실행이며, 2026-08-26 주석이 'gm1InProgressCount·gm1ParkedCount·gm1QueueFetchFailed 셋 읽는 곳이 0'이라 명시. 렌더 위치(#today-task-list)는 2026-08-08 삭제됨.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [dead-markup] `gm1QueueFetchFailed` — gm1RenderToday() → html 변수 초기화 직후 — 큐 fetch가 queue=[]로 대체된 이후 gm1QueueFetchFailed를 true로 세팅하는 코드가 이 파일 어디에도 없어 이 if 블록은 절대 진입 불가. 2026-08-26 주석이 해당 변수를 '읽는 곳이 0인 셋 중 하나'로 명시.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 4건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (5건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — IIFE > loadMonth() 함수, evalEl.innerHTML 하드코딩 블록 ('── 3층 · 이번 달 ──' 주석 이후) — 리더 평가 6축 수치(3분기 54/100, 리더 면모 11/20 등)가 '2026-08-27 실측 · 3분기(정적값)'으로 하드코딩 — 라이브 대시보드에서 2주 이상 고정 출력되며 자동 갱신 없음. 분기 종료 전 교체 필요.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 개인락커 manual-body 내 placeholder-note div > 골프 락커·스쿼시 락커 단락 — "윤병현AM 작업중 · 실무 입력 대기 — 임의 작성 금지" 문구 — 담당 AM의 작업 완료 여부가 불명확하여 대기 상태가 방치될 가능성 있음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `위임큐위젯제거` — // ── /GM1 통합 태스크 시스템 바로 다음 줄 — 실제 코드 없이 '제거됐다'는 사실만 기록하는 단독 비석 주석. 대상 코드가 이미 삭제돼 설명할 실체가 없음.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [stale-notice] `gm1RenderAlertSignal` — gm1 초기화 블록 setTimeout(gm1RetrySSOTSync, 2000) 직후 — 삭제된 함수(gm1RenderAlertSignal·gm1RenderCruiseSummary)와 존재하지 않는 DOM을 묘사하는 비석 주석. 이미 제거된 코드를 가리켜 참고 가치 소진.
  - 게이트: 근거: 리포 참조 15건(git grep 실측) — 확인 필요
- [stale-notice] `결재포인터삭제` — gm1RenderToday() → cardIdx 루프 직전 — 결재 포인터·진행 미션 포인터 두 블록이 삭제된 것을 설명하는 이중 비석 주석 묶음. 기능 코드 없이 변경 이력만 서술.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `FACILITY_RANGES_옛값` — fetchFacilityRanges() 함수 직전 계약서 이관 설명 블록 내 — 계약서(docs/superpowers/specs/2026-07-20-fcheck-ranges-contract.md)로 이관된 구버전 수치. 코드 주석 자체에 '사고 원인'이라 명시하며 '참고용 보존'이라 쓰여 있으나 정본이 계약서에 있으므로 여기 중복 보관 불필요.
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요

## 메인가이드 O3(재등록) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [dead-markup] `gm1InProgressCount` — gm1FetchSsot() → Promise.all 콜백 내 ② 큐 집계 블록 — queue는 항상 []로 고정(큐 fetch 2026-08-26 중단). 두 변수 소비처(진행배 배너 DOM)가 이미 삭제됨 — 코드 자체 주석 '읽는 곳이 0' 명시
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [dead-markup] `FACILITY_RANGES_옛값` — home KPI IIFE 내 fetchFacilityRanges() 정의 직후 — 전줄 주석 처리된 구버전 기준값 사본. 코드 자체 '옛 값(복사본, 사고 원인)은 참고용으로만 보존' 명시. 실값은 GAS fcheck_ranges_get 정본
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] `출처-요금확정본-하단` — O3 > details 요금 안내 > 요금표 마지막 문단 — 같은 details 블록 안에 출처 문단이 상단(날짜 범위 2026.1.1~12.31 포함)과 하단(날짜 범위 없는 축약본)으로 두 번 등장 — 하단이 정보량이 적은 중복본
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `공통정책-테이블` — O3 > details 요금 안내 > ▌ 공통 정책 표 — 휴회·환불·양도·회원권기간 4항목이 같은 O3 섹션 상단 멤버십 개요 표(조각 앞부분)에 이미 동일 내용으로 존재 — 공통 정책 표는 중복 집약이며 신규 정보는 '중복 할인' 1행뿐
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `gm1QueueFetchFailed` — gm1RenderToday() 내 html 빌드 최상단 — 큐 fetch 중단(2026-08-26) 후 gm1QueueFetchFailed를 true로 세팅하는 경로가 O3 내에 없어 이 경고 배너는 렌더될 수 없음
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [js-function] `gm1FetchWithFallback` — gm1FetchSsot() 선언 직전 (GM1_QUEUE_*_URL 변수 직후) — 큐 fetch 중단(2026-08-26) 이후 gm1FetchSsot 내 호출부가 'var queue = []'로 교체됨. O3 내 다른 호출처 없음
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [dead-markup] `GM1_QUEUE_RAW_URL` — gm1FetchWithFallback 함수 바로 위 — gm1FetchWithFallback의 인자로 전달될 4개 URL 상수. 호출부 소멸 후 참조처 없음. 특히 ARCH 2개는 아카이브 fetch용으로 별도 호출 경로도 없음
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### D. 장황 단순화 (3건)
- [verbose-block] `결재포인터-진행미션-삭제-tombstone` — gm1RenderToday() 내 active.forEach 루프 직전 — 삭제된 기능 묘비 주석 2개 연속 — 현행 코드에 관한 정보가 없고, 히스토리는 git 커밋이 정본
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `위임큐위젯제거-tombstone` — /GM1 통합 태스크 시스템 클로징 마커와 KPI 대시보드 v1 IIFE 사이 — 실행 코드 없는 단독 묘비 주석 한 줄 — 제거된 위젯을 기념하나 현행 코드에 기여 없음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `gm1RenderAlertSignal-tombstone` — GM1 init 말미, setInterval(_gm1AutoRefresh) 직후 — 삭제된 두 함수(gm1RenderAlertSignal·gm1RenderCruiseSummary) 묘비 주석; 해당 DOM도 정적 HTML에 없었음을 주석 스스로 인정
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 메인가이드 O4 — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [dead-markup] `gm1QueueFetchFailed` — gm1RenderToday() — 진행중 카드 루프 직전 — queue fetch가 2026-08-26 끊린 뒤 gm1QueueFetchFailed를 true로 설정하는 코드가 이 파일 어디에도 없으므로 이 조건 분기는 절대 실행되지 않는다
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [dead-markup] `gm1InProgressCount` — gm1FetchSsot() 내 Promise.all 콜백 — ② _queue.json 블록 — queue는 var queue=[]로 하드코딩되어 항상 빈 배열이고, 코드 주석(★2026-08-26 배798 감사)이 gm1InProgressCount·gm1ParkedCount·gm1QueueFetchFailed 세 변수 모두 '읽는 곳이 0'이라고 명시한다
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [js-function] `gm1FetchWithFallback` — gm1FetchSsot 함수 직전 — GM1_QUEUE_* 상수 선언 다음 — 유일한 호출부였던 gm1FetchSsot 내 queue fetch가 var queue=[]로 대체(2026-08-26)된 뒤 이 청크 전체에 gm1FetchWithFallback( 호출 지점이 없다; O4 IIFE 내부 함수라 외부 청크 호출 경로도 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [dead-markup] `GM1_QUEUE_RAW_URL` — gm1FetchSsot 함수 직전 선언부 — gm1FetchWithFallback이 더 이상 호출되지 않으므로 이 4개 URL 상수는 이 청크 내 어디에서도 참조되지 않는다; 큐 fetch 중단(2026-08-26)으로 유일한 사용 맥락이 사라짐
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### B. 중복 설명 병합 (2건)
- [duplicate-text] `출처_요금확정본_하단` — O4 ▸ ⑤ 요금 섹션 — 공통 정책 표 바로 아래 p 태그 — ⑤ 요금 섹션 상단에 '출처: 26년 멤버십 요금 확정본 (2026.1.1~12.31) · 변경 시 갱신' p 태그가 이미 있고, 하단에 단축 표기(괄호 날짜 없음)로 한 번 더 등장 — 하단이 상단의 중복
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `공통정책표_중복행` — O4 ▸ ⑤ 요금 섹션 ▸ ▌ 공통 정책 표 (회원권 기간·휴회·환불 위약금·양도 4행) — 공통 정책 표의 '회원권 기간(매년 1/1~12/31)·휴회(불가)·환불 위약금(10%, 24시간 취소)·양도(1회, 가족·법인, 5만원)' 4행이 이 chunk 상단 시설이용 overview 표(편의 서비스·양도·휴회·환불·클럽 성격·위치)와 실질 동일 내용으로 중복 — '중복 할인 불가' 1행만 신규
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `evalEl.innerHTML` — IIFE 스크립트 > loadMonth() > evalEl 할당 블록 전체 — 2026-08-27 기준 Q3 리더 평가 수치(54/100 등)를 JS 문자열에 하드코딩하고 코드 자신이 '3분기(정적값)'로 명시. 오늘(2026-09-13) 기준 17일 경과, Q3 종료 전까지 미갱신된 낡은 안내
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### D. 장황 단순화 (5건)
- [verbose-block] `manual-section-업무7` — O4/O1 article > 리셉션 업무 토글 내 7번 manual-section — '7. 리셉션 매뉴얼 (오픈·업무·마감) AI 초안 · GM 검토 전' 블록 전체 — 2026-08-29 이관 후 15일 경과하도록 'AI 초안 · GM 검토 전' 상태 유지. 오픈·업무·마감 3개 섹션 절차 내용이 IIFE 내 WEEKDAY 체크리스트(정본)와 기능 중복이며, 미확정 초안이 확정 매뉴얼 옆에 노출되어 실무진 혼란 유발 가능. '₩303,000' 등 구체 수치가 검증 없이 하드코딩됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `tombstone-결재포인터삭제` — gm1RenderToday() — 진행중 카드 루프 직전 — 이미 삭제 완료된 결재 포인터의 묘비 주석; 현재 코드 이해에 기여하지 않으며 PR 이력 정보에 불과하다
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `tombstone-상시미션포인터삭제` — gm1RenderToday() — 결재 포인터 묘비 주석 바로 다음 — 삭제된 상시미션 포인터의 묘비 주석; GM 대화까지 인용한 장황한 삭제 이력으로 현재 코드 맥락에 기여하는 정보가 없다
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `tombstone-gm1RenderAlertSignal` — 초기화 블록 끝 — gm1FetchSsot() 호출 직후 setTimeout 블록 앞 — 이미 제거된 두 함수의 묘비 주석; 현재 코드에 기여하는 정보가 없다
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `tombstone-위임큐위젯제거` — GM1 IIFE 닫힘과 KPI 대시보드 IIFE 시작 사이 — 2026-06-05 제거된 위임 큐 위젯의 묘비 주석 한 줄; 현재 코드 맥락에서 불필요한 이력 기록
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 문의회원 — `3. 웰페리온 가이드/cpo/member/membership.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `hz-more` — CSS <style> 블록 — .hz-zone.z-theme 규칙 직후 (헤더 접힘 드롭다운 영역) — 대응 HTML <details class='hz-more'> 요소가 헤더 전체에 존재하지 않음. 2026-09-02 정리 시 관련 버튼들이 '접기' 대신 완전 제거되어 CSS 4규칙만 고립됐다.
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `_oaMaskPhone` — _oaRender 섹션 직전 _oaMaskPhone 함수 정의부 — _mregRender 주석이 '실측 결과 이 파일에서 _oaMaskPhone 호출은 여기 한 곳뿐이었다'를 명시한 뒤 해당 호출을 직접 esc()로 대체함 — 유일 호출부가 제거되어 함수 정의만 남은 고아 함수
  - 게이트: 소비자 8건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — _gasPrewarm IIFE 주석 + _snapActiveGet_ 상단 주석 — GAS 첫/재호출 실측 수치(유효회원 6.7초/3.1초 · 종료회원 7.2/3.4 · 문의 25.6/3.1)가 두 주석 블록에 거의 동일하게 반복되며, _snapActiveGet_ 쪽이 '수치 정정'이라며 더 상세한 최신본임
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (12건)
- [dead-markup] `holdStatusCard` — pane-active 카드 내부 (#activeSummary 직후) — 인접 주석이 '도달 불가능 — 진입점 openHoldManage() 호출부 0 확인 후 삭제, JS 클러스터 전체 함께 지워야 함'이라 명시. 이 div는 빈 채로 항상 display:none.
  - 게이트: 근거: 리포 참조 29건(git grep 실측) — 확인 필요
- [stale-notice] `salesedu` — gdoc-tpl 숨김 블록 — 가이드&교육 허브 salesedu 카드 — '내용은 이후 채웁니다(준비 중)' 자리표시자 콘텐츠 3항목이 생성 이후 장기간 채워지지 않아, 실무진이 가이드 허브에서 이 카드를 클릭하면 빈 안내만 표시됨.
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — gviz 어댑터 헤더 블록 주석 (/* ═══ gviz 직접읽기 어댑터 ... ═══ */) — 'gviz는 읽기전용(member_inquiry_list·lesson_inquiry_list 2건만 대체)'라고 적혀 있으나 lessonLoad 내 '2026-07-16 시토' 주석 및 코드 분기에서 강습(lesson) 경로는 GAS로 완전히 되돌려진 것이 확인됨 — lesson_inquiry_list 대체 설명이 사실과 다름
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — _snapActiveGet_ 함수 상단 주석 — '수치 정정' 단락 — '종전에 적혀 있던 "36초"는 옛 값이다'라고 교정하는 문장이 있으나 "36초" 원본은 이 파일 어디에도 남아 있지 않아 교정 안내 자체가 허공을 가리킴
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — lessonLoad 함수 내 // [2026-07-16 시토] 강습 문의는 항상 GAS로 읽는다 주석 블록 — 버그 근거 예시로 실고객 성명 및 전화번호('임하윤 010-7331-3903')가 주석에 잔류하며 해당 버그는 수정 완료됨 — 수정 의도를 설명하는 코드 주석에 실데이터 식별자가 남아 있음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `NARROW_COL_WIDTHS` — NARROW_COL_WIDTHS 객체 내 'PT Contact' / 'GOLF Contact' / 'P.L Contact' / '스쿼시 Contact' / '수영 Contact' 5개 항목 — 해당 5개 키가 ALWAYS_HIDE_COLS에도 포함되어 _activeDisplayCols()에서 먼저 필터링됨 — narrowW 분기에 절대 도달하지 않는 죽은 설정값. ALWAYS_HIDE_COLS 결정이 NARROW_COL_WIDTHS 선언보다 늦어 잔존.
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [stale-notice] `_loadHoldIntake` — function _loadHoldIntake(force) 선언 직전 3줄 주석 — openHoldManage() 삭제 완료(2026-08-16) 이후 미완 청소 안내가 코드보다 오래 잔류 — 현재 _loadHoldIntake가 다른 경로로 호출된다면 '진입점을 잃었다'는 주석이 잘못된 위험 신호를 줌
  - 게이트: 근거: 리포 참조 29건(git grep 실측) — 확인 필요
- [stale-notice] `_renderHoldIntake` — _renderHoldIntake 내 if (_holdIntake === null …) return 직후, var intake = _holdIntake || [] 직전 — 테스트 접수 실물 삭제(배146)·화면 필터 제거(배174) 모두 2026-07-27 완료 확인된 사안; 완료 경위 서술이 코드에 불필요하게 잔류
  - 게이트: 근거: 리포 참조 13건(git grep 실측) — 확인 필요
- [stale-notice] `_holdActive` — function _holdActive(row) 선언 직전 블록 주석 — openHoldModal/member_hold_preview는 이미 제거 완료; 삭제된 코드의 아키텍처 배경만 남아 현재 코드와 단절된 이력 설명
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [stale-notice] `dismissBeginnerBanner` — esc() 함수 정의 직후 독립 블록 주석 (WriteBuffer IIFE 외부) — 배너 자체가 2026-07-15 삭제 완료된 사건을 기술하는 고아 주석으로, 연관 코드 없이 이미 해소된 변경 이력만 남아 있음
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [stale-notice] `_verifyFetchActiveFull` — _verifyFetchActiveFull 함수 본체 bare-block { } 닫는 중괄호 직후 (함수 마지막 줄) — 함수 몸체 전체가 bare-block { }으로 감싸여 있고 그 안의 return fetch(…)가 함수를 빠져나가므로, 블록 이후의 return Promise.resolve(null)은 어떤 실행 경로로도 도달 불가능한 리팩터링 잔재
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [stale-notice] `RAW_BASE_CPO` — WriteBuffer </script> 직후, CPO 자동보고 <script> 블록 직전 HTML 주석 — 주석은 'raw.githubusercontent 공개 조회'를 명시하나 실제 구현은 RAW_BASE_CPO = '/repo/'(서버 내부 프록시 경로)로 URL 방식이 달라 설명과 코드가 불일치
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### D. 장황 단순화 (7건)
- [verbose-block] `_refreshDiskCache` — <script> 블록 내 _refreshDiskCache IIFE 주석, 실증 절차 4줄 — 2026-08-24 1회성 검증 절차(①~④)와 CACHEPROOF 표식이 검증 완료 후에도 코드에 잔존. IIFE 동작 설명 앞 5줄은 유지 가치 있으나 실증 절차 4줄은 이미 완료된 테스트 기록으로 가독성 소음.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [css-class] `sum-card` — CSS <style> 블록 — 오늘 현황 요약 카드 규칙 영역 — 주석은 '.sum-card 카드를 grid 안으로 이관'이라 하지만 실제 HTML의 해당 그리드 카드들은 전부 .dash-card 클래스를 사용하고, 정적 HTML 전체에서 class='sum-card' 요소가 발견되지 않음. JS 동적 생성 가능성을 배제할 수 없어 A가 아닌 D로 분류.
  - 게이트: 근거: 리포 참조 39건(git grep 실측) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — _lessonRosterFor 함수 직전 주석 (// ★2026-07-27 시포 라이브 실측 — 종목탭 경로는 현재 통째로 무효다 블록) — 스스로 '결과에 영향 0'이라 확인한 탭 조회 경로의 실증 과정(7개 탭 직접 조회·응답 내용·판별 결론)을 9줄에 걸쳐 서술 — '탭이 없어 폴백됨(LESSON_INSTRUCTOR_ROSTER 사용)' 한 줄로 의도 전달 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — _lessonSportMgmt 함수 내 ★'타팀 오염 제거' 폐기 주석 블록 — 폐기된 '타팀 오염 제거' 기능의 삭제 경위·실측 수치(335줄 사라짐·69줄 교체·현직 강사 22명)·구조적 한계를 15줄 이상 서술 — '화면이 시트 원본값을 그대로 표시한다' 한 줄로 의도 전달 가능하며 이후 팀장 자동대입 폐기 주석에서 맥락이 이미 반복됨
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] `_mregProgLabel` — _mregProgLabel 함수 정의 위 주석 블록 2개 연속(2026-08-03 · 2026-08-05) — 1차 주석(기호·시설·개월수 제거 근거 장문)과 2차 주석(두 표 통일 지시)이 각각 8줄 이상으로 중복 서술되어 있으나 실제 변환 규칙은 정규식 3줄이 전부. 2차 결정이 1차를 덮으므로 1차 주석의 '2026-08-04 원 사유, 참고용' 블록은 가독성만 해침.
  - 게이트: 근거: 리포 참조 13건(git grep 실측) — 확인 필요
- [verbose-block] `_saveCell` — _saveCell 함수 내 var payload 조립 직전 9줄 주석 블록 — '바꾼 칸만 payload에 담는다—undefined=건드리지 않음(시트 드롭다운 규칙 위반 방지)' 한 줄로 대체 가능; 도자연·네이버 실명·E642 코드 등 과거 사고 조사 내용이 실무 가독성을 저해
  - 게이트: 근거: 리포 참조 30건(git grep 실측) — 확인 필요
- [verbose-block] `loadDbData` — loadDbData 내 var _dbPromise = _inquiryListFetch() 직전 8줄 주석 블록 — '시트 필터·숨김행으로 gviz 누락 위험 → GAS 직접 읽기로 전환' 한 줄로 대체 가능; gid·건수·커밋 해시·보고 필수 문구는 2026-07-16 조사 기록으로 현재 독자에게 불필요한 장황
  - 게이트: 근거: 리포 참조 17건(git grep 실측) — 확인 필요

## 강습회원관리 — `3. 웰페리온 가이드/cpo/member/강습회원관리.html`
- ⚠️ 감사 실패: 파일 읽기 실패: [Errno 2] No such file or directory: 'C:\\Users\\jjky0\\welperion-automation\\3. 웰페리온 가이드/cpo/member/강습회원관리.html'

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `badge-v1` — 헤더 h1 내 버전 배지 — 피드백 CTA(2026-07-29)·ERP API 듀얼루트(배1050, 2026-09-09) 등 주요 기능이 이후 추가됐으나 v1.0 배지가 갱신되지 않아 stale
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [stale-notice] `feedback-link-placeholder-comment` — .header-feedback-slot 버튼 아래 HTML 주석 — GM 지시(2026-07-29)에서 링크를 추가하기로 했으나 약 6주가 지난 2026-09-13 현재도 실제 링크 없이 todo 주석만 남아 있음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `pol-card-width100vw-removed-comment` — CSS .pol-card table 규칙셋 직전 주석 — width:100vw 핵은 이미 제거됐고 현 코드에 존재하지 않음. '불필요해져 제거' 설명이 과거 이력 기록으로만 남아 현재 코드 독해를 방해
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (2건)
- [css-class] `callout-blue-yellow-green` — CSS .callout 변형 규칙 3개 (.callout.red는 정책 탭 사용 중이므로 제외) — 페이지 정적 HTML 전체와 JS renderCard·renderPolicyTable 어디에도 callout.blue / callout.yellow / callout.green 인스턴스 없음. 향후 콘텐츠 추가 가능성을 고려해 보수 분류 D
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [css-class] `num-badge-orange` — CSS .num-badge 변형 규칙 — 정적 HTML 표(멤버십·성인강습·유소년 탭 전체)와 JS renderCard 어디에도 'num-badge orange' 조합 없음. accent·green·yellow·blue·red 변형은 모두 실사용 중
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `chip-row` — <style> 블록 — .chan-icon svg 규칙 직후 3행 — HTML 정적 마크업 및 모든 JS 렌더 함수에서 .chip/.chip-row 클래스를 생성·적용하는 코드 전무. chipIconSvg() 반환 SVG는 chanIconHtml()이 .chan-icon span 안에 삽입하며 .chip과 무관
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `post-metric` — <style> 블록 — .chip svg 직후 2행 (print @media 블록 내 #m1-dash .post-metric{font-size:7px} 도 함께 삭제 대상) — HTML 마크업 및 모든 JS 렌더 함수에서 .post-metric 클래스를 생성·적용하는 코드 전무. 게시물 지표는 renderChannelPerf 등에서 인라인 스타일만 사용
  - 게이트: 소비자 7건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — HTML body — 편별 반응 성적표 section, #reaction-scorecard-wrap 바로 위 정적 마크업 — 관찰 기간 종료일 2026-08-20 이 오늘(2026-09-13) 기준 24일 전 경과 — 검증 완료 여부 미반영 채로 '관찰 중·검증 중' 문구가 만료 후에도 상시 노출
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — renderContentAttribution() JS 함수 — 원인·조치 설명 div 내 visible text — 2026-07-31 시점 버전 배지(@193) — 오늘(2026-09-13) 기준 수십 배포 이후이며 운영 실무진에게 무의미한 구식별자
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — renderContentAttribution() JS 함수 — measure-pending div 직후 '원인(실측):' 단락(2문장)과 이어지는 '2026-07-31 조치 완료:' 단락 전체 — 배포 6주 후에도 수정 이전 버그 원인·배선 오류 경위가 운영 대시보드에 상시 표시 — '배포 완료·데이터 쌓이는 중·구조적 한계' 세 줄이면 충분하며 역사적 원인 설명 2단락은 실무 가독성 저해
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `month-select-wrap` — CSS /* 화면용 월 선택기 */ 블록, .month-select 정의 앞 첫 번째 룰 — HTML 월 선택기 래퍼가 .tb-month를 사용하며, .month-select-wrap을 class 속성에 가진 요소가 페이지 내 어디에도 없음
  - 게이트: 소비자 11건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-lbl` — CSS /* 화면용 월 선택기 */ 블록, .month-select-wrap 바로 아래 두 번째 룰 — HTML 레이블이 .tb-month .lbl(별개 클래스)을 사용하여 .month-select-lbl을 가진 요소가 없음
  - 게이트: 소비자 5건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-wrap` — CSS .month-select:hover 바로 다음 단독 @media print 룰 — .month-select-wrap 클래스를 가진 요소가 없으므로 이 인쇄 숨김 규칙도 효과 없음
  - 게이트: 소비자 11건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `dark-theme-root-variables` — CSS 상단 :root{} 기본 블록과 /* ── 테마 강제 토글 */ 섹션 :root[data-theme="dark"]{} 블록 — :root 기본 변수 17개가 :root[data-theme="dark"] 블록과 내용 완전 동일. 마찬가지로 @media(prefers-color-scheme:light){:root{}}와 :root[data-theme="light"]{} 블록도 동일 변수 17개 중복
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `gm-memo-comment` — JS, GM 메모 저장 IIFE 바로 위 블록 주석 — localStorage 저장 기능이 이미 구현·작동 중. '죽은 칸', 'page_score 82% 감점 사유'는 해소된 과거 감사 이력 참조로 현 시점에 낡음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [css-class] `panel-flush` — CSS, .panel 정의 바로 아래 — 이 페이지 HTML 마크업과 JS 동적 렌더링 어느 곳에서도 class='panel-flush'를 사용하지 않음
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `stat-label` — About 섹션 .about-stats 셋째 카드 / Membership 섹션 첫 번째 .section-desc — "100% 사전 예약제" 개념이 About 통계 카드와 Membership 안내문에 동일하게 등장; Facilities 섹션 설명에도 "사전 예약" 유사 표현 추가 반복
  - 게이트: 근거: 리포 참조 13건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `about-visual` — About 섹션 .about-inner 좌측 열 — 500px(모바일 280px) 높이 CSS 박스에 알파 15% 'W' 한 글자만 표시. .about-visual CSS 스타일(font-size 64px, letter-spacing 8px 등)이 전부 이 한 글자를 위해 존재 — 실사진이 없는 이미지 플레이스홀더로 보임
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [verbose-block] `og:title` — <head> OG 메타 태그 — 슬로건 'A Day, Well Completed'이 영·한 이중으로 한 태그에 포함('하루의 완성, 웰페리온'). 영문 슬로건은 이미 Hero H1에 노출되므로 OG 태그가 불필요하게 장황
  - 게이트: 근거: 리포 참조 25건(git grep 실측) — 확인 필요

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### D. 장황 단순화 (2건)
- [verbose-block] `ai-owner` — header > h1 내 span 태그 — class="ai-owner"에 대응하는 CSS 규칙이 스타일시트에 정의되지 않았고 JS에서도 해당 클래스를 querySelector·classList로 선택하지 않음. 모든 시각 스타일이 인라인 style 속성으로 완결되어 class 속성이 실질적으로 무효
  - 게이트: 근거: 리포 참조 40건(git grep 실측) — 확인 필요
- [verbose-block] `buildM5Map` — buildM5Map 함수 내 forEach 콜백 if(m) 블록 — '<' 방향이 모호한 우선순위 주석(발행완료가 가장 앞인지 뒤인지 불명확)과 '더 진행된 상태로 덮어씌우지 않음'이라는 설명이 바로 아래 코드(발행완료 확인 시 map[num]을 덮어씀)와 정면으로 모순되어 유지·수정 시 혼란을 유발함
  - 게이트: 근거: 리포 참조 13건(git grep 실측) — 확인 필요

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] `wlp-inq .hero-band` — 두 번째 <style> 태그 L144-145, .back-kiosk 규칙 바로 앞 — position:relative 는 L51 .wlp-inq .hero-band{background:…;position:relative} 에 이미 선언돼 있어 단독 재선언은 효과 없는 중복
  - 게이트: 근거: 리포 참조 21건(git grep 실측) — 확인 필요
- [duplicate-text] `scrollbar-width` — 두 번째 <style> 태그 L13, 미니파이된 첫 키오스크 @media 블록 끝부분 — 동일한 세 규칙이 L20-22 전역(미디어쿼리 밖)에도 그대로 존재; 전역 규칙이 모든 화면에 적용되므로 키오스크 블록 내 복사본은 불필요
  - 게이트: 근거: 리포 참조 75건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `type=steamiron` — type-grid L220-231, 유소년 카드와 오넛티 카드 사이 HTML 주석 블록 — 2026-09-02 GM 지시 이후 오늘(2026-09-13) 기준 11일 경과, 운영부 회신·부가세 확정 여부 미갱신 — 해소됐다면 주석 해제 또는 안내 업데이트 필요
  - 게이트: 근거: 리포 참조 14건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `lang-switch` — 두 번째 <style> 태그 L46-48, lang-switch 아래 @media (max-width:520px) 블록 — 표준 CSS 중첩 @media 구조(CSS Nesting 필요); 내부 600px 블록과 외부 520px 블록의 lang-switch top/right 값이 !important 유무로 충돌; '키오스크 규칙 최상위 이전' 코멘트가 정리 미완료를 시사
  - 게이트: 근거: 리포 참조 55건(git grep 실측) — 확인 필요
- [verbose-block] `social-bar` — 두 번째 <style> 태그 L128, 두 번째 키오스크 @media (min-width:700px) 블록 내부 — L13 첫 번째 키오스크 블록이 .social-bar{display:none!important} 로 숨기므로, 이 margin/gap 재정의는 키오스크 조건에서 렌더 효과가 없는 충돌 규칙
  - 게이트: 근거: 리포 참조 23건(git grep 실측) — 확인 필요

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `appointment-only` — 인트로 부제 <span> / 페이지 하단 <p> — 약속제 전용 안내가 인트로 부제('By Appointment Only')와 하단 고지('by appointment only. Walk-ins are not available') 두 곳에 중복 등장; 핵심 메시지 동일
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `opening-html-comment` — 파일 최상단 HTML 주석 첫 번째 블록 (<!--...-->) — GM 지시·웰리 검수 경위를 40줄 영문 산문으로 나열; 동일 결정 근거가 하단 CSS 인라인 한국어 주석(배경색·여백·로고·KOR버튼 항목별)에 이미 요약돼 있어 이중 장황. 실무자가 실제 마크업에 도달하려면 전체 스크롤 필요.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [css-class] `wp-inq-video` — 인트로 영상 외부 wrapper div (영상 섹션 첫 번째 div) — 이 파일 <style> 블록에 .wp-inq-video 규칙 없음; 모든 스타일이 inline이며 파일 헤더 주석 'Inline styles only' 원칙과 충돌. 외부 wp-typography.css에서의 참조 여부 미확인.
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `--yellow` — :root 블록, --red-border 정의 다음 두 줄 — 페이지 내 CSS 규칙·인라인 스타일·JS 어디에도 var(--yellow*) 또는 var(--teal*) 참조가 전혀 없음
  - 게이트: git grep 오류(rc=129): error: unknown option `yellow'
usage: git grep [<options>] [-e] <pattern> [<rev>...] [[--] <path>...]

    --[no-]cached         search in index instead of in the work tree
    --no-index            f
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 방 목록 관리 카드 info-box 끝 문장 + 사용 조건 아코디언 세 번째 li — "방 이름이 카톡 채팅방 제목과 정확히 일치해야 한다"는 경고가 카드 상단 info-box와 사용 조건 아코디언 3항목에 동일 의미로 중복 등장
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — script 블록 상단 // 주석 3줄 ↔ _roomsPost 함수 정의 직전 /* */ 블록 3줄 — GAS 쓰기 관문의 ERP 이중기록 동작 설명이 스크립트 맨 위 // 주석과 _roomsPost 바로 위 /* */ 블록에 동일 내용으로 이중 기재
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — addRoom() 함수 내, _roomsPost({action:'kakao_rooms_save'…}) 호출 직전 — 이미 적용·확정된 no-cors 제거 이유를 5줄에 걸쳐 역사적 배경·타 파일 교차참조까지 서술 — 1줄 요약 또는 커밋 메시지로 충분
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — ERP_API_ON 변수 선언 바로 위 블록 주석 — ERP_API_ON 조건·_wroteRecently 함수·GAS 폴백 로직이 코드 자체로 명확히 드러나므로 3줄 블록 설명은 과잉 — 1줄 요약으로 대체 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
### A. 죽은 코드(자동삭제 대상) (5건)
- [js-function] `last` — 약 519행, IIFE 내 헬퍼 — 정의만 있고 파일 내 호출부 0
  - 게이트: 소비자 3541건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `parseJsonl` — 약 514–518행 — JSONL 파싱 함수인데 파일 내 호출부 0 — 모든 소스 파일은 parseJson(JSON)으로 처리됨
  - 게이트: 소비자 5건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `shipStatusLabel` — 약 631–636행 — 상태 레이블 변환 함수인데 호출부 0 — renderHangro는 secs 배열 title 리터럴을 직접 씀
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `dupKeySet` — 약 603–618행 (isSuspect 포함) — dupKeySet·isSuspect 쌍 모두 호출부 0 — 구 '전체 배' 중복 강조 UI 제거 후 잔류
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `routines` — <style> 55–77행 — #layer-autonomy·.routines·.rcard*·.pill*·.rrow* 를 사용하는 HTML 마크업·JS innerHTML 없음 — 루틴 카드 섹션 걷힌 뒤 CSS만 잔류
  - 게이트: 소비자 15건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `esc` — 약 323행(📊 ERP 완성도 IIFE)과 약 482행(메인 IIFE) — 두 곳 독립 선언 — 두 IIFE가 동일 목적으로 esc()를 각자 선언 — null 처리만 s||''와 s==null?'' 로 미세하게 다름
  - 게이트: 근거: 리포 참조 4188건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 약 192–197행, 북극성 섹션 직전 — '북극성을 이 자리에 놓는다'는 이관 이유 HTML 주석이 서로 다른 날짜로 세 겹 중첩 — 마지막 한 줄로 충분
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [css-class] `coo-tier` — <style> 약 85–87행 및 97–101행 (.coo-tier·.coo-tier-h·.tier-badge·.coo-flow·.coo-flow-step·.coo-flow-arrow·.coo-tag) — 이 클래스를 쓰는 HTML 마크업·JS innerHTML 없음 — 시우 3층 구조 섹션 삭제 후 CSS만 잔류 추정. 삭제 주석 없어 A 대신 C로 보수적 분류
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 약 270–468행 사이 HTML 주석 묘비 8개 클러스터 (270–276·289–292·300–304·434–437·440–443·451–454·457–463·465–468) — 삭제된 섹션의 경위를 장황하게 서술하는 HTML 주석들이 페이지 중간에 산재 — git 이력이 있으므로 각 1줄로 압축 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 약 1339–1363행 Promise.all 배열 내 Promise.resolve('') 슬롯 13개의 인라인 주석 — 인덱스 유지 목적 빈 슬롯마다 2–4줄 삭제 경위 주석이 달려 로드 코드 전체가 주석 덩어리로 읽힘 — '// a[N] 자리 유지' 한 줄 형식으로 통일 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] `teamSales` — JS 팀 분석 헬퍼 블록 — teamLabor·teamProc·teamCost 정의 사이 — renderPeople() 등 페이지 어디서도 호출되지 않는 호출부 0 함수. 같은 블록의 teamLabor·teamProc·teamCost는 모두 사용 중이나 teamSales만 고립
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — sales 패널 · 월별 매출 추이 카드 내 desc 요소 — 같은 탭 하단 notice('센터 전체 = 운영부(회원권) + 강습(부서별). 6월은 부분월…')가 동일 내용을 다시 안내 — 실무자가 같은 설명을 두 번 읽게 됨
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — sales 패널 · 매출현황 표(salesTbl) 아래 정적 notice — 2026-09-13 현재 6월은 이미 마감 완료월. '6월은 부분월' 안내는 시제가 틀림
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — request 패널 · 품의현황 표(reqTbl) 아래 정적 notice — 실제 상태 기계(STAGES=["품의","검토","정산","완료"], stc, BULK_CFG)에 '집행' 상태가 존재하지 않음. 안내문의 품의→검토→집행→정산이 실제 흐름 품의→검토→정산→완료와 불일치
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `REVIEW_LOADED` — JS 모듈 최상단 변수 선언 및 loadReviewLowest() 내 REVIEW_LOADED=true 대입 — REVIEW_LOADED는 loadReviewLowest()에서 true로 세팅되지만 이 값을 읽는 코드가 페이지 전체에 없음. 중복 로드 방지 가드를 만들려던 의도로 보이나 실제 if(REVIEW_LOADED) 가드가 없어 독자에게 캐시 보호가 있다는 잘못된 기대를 심어 줌
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `header-right` — CSS <style> 블록, .header-meta 바로 아래 — HTML 마크업 어디에도 class="header-right" 요소가 없음; 헤더 우측 영역은 class="header-btns"로 구현되어 있음
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단) · 근거: 리포 참조 26건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `tabTrend-source-placeholder` — tabTrend > 월별 매출 추이 섹션카드, trendBars div 아래 — 데이터 로드 성공 후에도 항상 노출되며, 개요 탭 info-banner가 동일 정본·미마감 정책을 이미 안내함; AV3:AV14 셀 주소는 실무진 불필요 구현 세부
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `nsNote` — tabChannel > 북극성 KPI 연결 섹션 하단 — 색상 임계값(≥100%·80%~99%·80% 미만) 설명이 gaugeClass() 함수 및 bar-fill 색상으로 이미 시각 전달됨; 텍스트 중복
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `API_URL` — <script> 설정 섹션 첫 줄 주석 — 실제 GAS URL이 이미 채워졌으므로 '배포 후 교체' 주석은 해소된 TODO
  - 게이트: 근거: 리포 참조 261건(git grep 실측) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] `--blue` — :root 변수 선언부 — --yellow·--blue·--purple 3개 행 — --yellow, --yellow-bg, --blue, --blue-bg, --purple, --purple-bg 6개 변수 모두 이 파일의 CSS 규칙·인라인 스타일 어디서도 참조되지 않음
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `blue'
usage: git grep [<options>] [-) — 확인 필요
- [verbose-block] `--green-bg` — :root 변수 선언부 — --green·--red·--orange 행의 -bg 접미 변수 — --green-bg·--red-bg·--orange-bg 3개 변수는 이 파일 내 참조 없음; 기반색(--green→--success, --red→--danger, --orange→--warning)은 별칭 경유 실사용 중이므로 해당 행 전체 삭제는 불가
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `green-bg'
usage: git grep [<options>) — 확인 필요
- [dead-markup] `filterCategory` — filter-bar HTML 섹션, filterMonth select 바로 아래 — populateMonthFilter()처럼 카테고리 옵션을 동적 주입하는 함수가 없어 선택 가능한 값이 빈 기본값뿐이며 카테고리 필터로 실작동하지 않음
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `t-hwp` — <style> 블록 하단 · .doc-type 컬러 규칙군 — renderDocs()의 groups 배열 전체를 확인해도 type:"HWP" 항목이 없어, 이 선택자가 매칭할 요소가 생성되지 않음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [css-class] `t-docx` — <style> 블록 하단 · .doc-type 컬러 규칙군 — renderDocs()의 groups 배열 전체를 확인해도 type:"DOCX" 항목이 없어, 이 선택자가 매칭할 요소가 생성되지 않음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] `hireDept` — #hireModal(hireDept·hireSosok·hireType)과 #hireCompleteModal(hcDept·hcSosok·hcType) — 부서·소속 13개·고용형태 4개 option 목록이 두 모달에 완전 중복 선언 — 소속 select 기준 13개 option이 2벌 존재
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [duplicate-text] `정성평가_추후도입_안내` — renderEval() admin 경로 muted 캡션 + evalCriteriaSection() 말미 alert — 같은 탭에서 두 번 표시 — "정성평가는 추후 별도 도입 예정" 메시지가 renderEval() 상단 캡션과 evalCriteriaSection() alert 두 곳에 거의 동일 문구로 반복됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (5건)
- [dead-markup] `ORG_GUIDE_ITEMS_DRAFT` — JS 전역 선언 영역 — ORG_GUIDE_CACHE_ 변수 직전 — 백엔드 전환 완료 후 파일 전체에서 읽히는 참조가 없는 드래프트 단계 잔존 불리언 플래그
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `css_color_changelog_line` — <style> 블록 최상단 블록 주석 내 — v3 FINAL 버전 설명 두 번째 줄 — 이미 완료된 색 변경 이력 메모 — 현재 코드에 녹색 앵커 흔적 없음, 이력 노이즈
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `evalCriteriaSection` — evalCriteriaSection() 함수 말미(현재 admin renderEval에서 활성 호출됨) — 함수 바로 위 주석이 "A-5 2026-08-17 추가 · 매니저 확정본"으로 명시돼 있어, 경고문의 "잠정 — 매니저 확정 대기" 문구는 확정 이후에도 업데이트되지 않은 모순 상태
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [stale-notice] `criteriaSection` — criteriaSection() — 다면평가/포상 체계 sec-title 내 span(preserved dead code) — 정기 성과평가(2026 신설·승인)가 이미 운영 중이므로 구 다면평가를 "전환 검토 대상"으로 표기하는 것은 시제 오류; criteriaSection 자체도 renderEval에서 제거된 preserved dead code
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [stale-notice] `perfCriteriaCard` — perfCriteriaCard() — SESSION_ROLE admin 조건부 muted div(preserved dead code) — "상단 평가 실시 콘솔"은 renderEval() 2026-08-17 개정으로 화면에서 제거됐으나 안내 문구는 존재하지 않는 UI 요소를 여전히 가리킴
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### D. 장황 단순화 (4건)
- [verbose-block] `css_design_system_comment_block` — <style> 최상단, :root { 선언 직전 17줄 블록 주석 — 색 계층 선언·변수 계약·버전 표기를 CSS에 17줄 주석으로 내장 — 실무 CSS 스캔 가독성 저하, 설계 계약은 별도 문서 분리 가능
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `cache_control_head_comment` — <head> no-cache 메타태그 3개 직전 4줄 HTML 주석 — GitHub Pages 캐싱 동작 원리를 4줄 주석으로 과도 설명 — 1줄로 압축 가능
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `buildHrCard` — buildHrCard 함수 내 생년월일·주소 파싱 블록과 openPrintView 함수 내 동일 블록 (~15줄씩) — 4형식 생년 정규식 추출 + 연도 범위 검증 + 만나이 계산 로직이 두 함수에 copy-paste 수준으로 중복 존재 — 공통 헬퍼 분리 후보
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [verbose-block] `wpl-foot` — renderEval() — wpl-card 요약 패널 하단 .wpl-foot div — 정체 기준 설명이 renderWplDetail()의 wpFormulaRow("정체관리") 항목에 이미 분자·분모 단위로 상세 표시되어 관리자가 같은 탭에서 동일 내용을 두 번 읽게 됨; 요약 패널 foot는 "정성평가 추후 도입 예정" 한 줄로 단축 가능
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `deptband` — CSS <style> 블록 — .dept-crit 규칙 아래 — HTML 마크업과 JS 어디에도 deptband 클래스를 적용하는 요소가 없음; 유사 역할은 .covrow .colName이 담당
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [js-function] `shiftKind` — JS 블록 — isCloser 정의 바로 아래 — 파일 내 shiftKind( 호출부 0개; render()는 항상 'sh-work'를 하드코딩하여 직접 삽입
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [js-function] `usedOf` — JS 블록 — openApply 함수 정의 바로 위 — 파일 내 usedOf( 호출부 0개; 동일 계산(연도 필터 포함)을 usedAnnual2026()이 대체 수행
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `addEventListener-message-wp-pass-first` — JS 블록 — erpLoad 함수 정의 바로 아래 (ERP 백엔드 연동 섹션) — 동일한 'wp-pass' 메시지를 처리하는 두 번째 리스너(게이트 섹션)가 resolveGate()를 통해 WP_PW 설정·setOfflineBadge·erpLoad를 모두 포함·확장; 두 리스너 동시 등록으로 erpLoad()가 메시지 수신 시 두 번 호출됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `RETIRED-comment` — JS 블록 — const RETIRED 정의 직전 줄 — 주석 '이지영 06-27 퇴사 미반영'이라 기술하나 바로 아래 RETIRED={"이지영":"2026-06-27"}로 이미 반영 완료; 상태 기술이 현실과 불일치하는 낡은 주석
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `sh-open sh-close sh-mid` — CSS <style> 블록 — sh-work 규칙 및 .tablecard 오버라이드 두 군데 — shiftKind()가 호출되지 않아 .sh-open·.sh-close·.sh-mid 클래스는 어떤 요소에도 적용되지 않음; 두 복합 선택자를 .sh-work 단독으로 단순화 가능
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [css-class] `gate` — head > 두 번째 <style> 블록 (첫 번째 <link rel='stylesheet'> 직전) — 2026-07-10 비밀번호 게이트 완전 제거 후 HTML body에서 id='gate' 요소가 삭제됐으나 게이트 전용 CSS 블록 전체가 잔류
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 1161건(git grep 실측) — 확인 필요
- [js-function] `screenSheen` — IIFE 내 박스 텍스처 헬퍼 블록 (sheen 직후) — 모니터·발광 패널이 원목 장부(standPanel)로 교체된 후 호출부 전무 — 파일 내 screenSheen() 호출 0건
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [js-function] `sheen` — IIFE 내 박스 텍스처 헬퍼 블록 (boxRound 직후, screenSheen 직전) — 금속 광택 유틸리티 — 파일 내 sheen() 호출 0건
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [js-function] `boxRound` — IIFE 내 박스 텍스처 헬퍼 블록 (faceShade·vGrain 직후, sheen 직전) — 수직 모서리 라운딩 유틸리티. carveBox·roundedQuad 도입으로 대체된 후 파일 내 boxRound() 호출 0건
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 4건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `PERSONA_LINE` — PERSONA_LINE 상수(캐릭터 정의 블록) / AMBIENT 배열(enableSampleFallback 내부) — A-1~A-12 유휴 대사 12개가 PERSONA_LINE 객체와 AMBIENT 배열에 1:1 완전 동일 문자열로 중복 보관됨 (예: '이력서 한 장씩 다시 확인', '근로계약 조항 짚어보기' 등 전원 동일)
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] `agentSum` — IIFE 내 todayCount 집계 블록 직후 (renderTodayAgent 앞) — 함수 내 주석 '계속 사용'과 달리 파일 전체에 agentSum() 호출 0건. 집계 경로가 todayCount·tally 직접 증감으로 대체됨
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `fmtAsOf` — IIFE 내 Pages판 전용 섹션 (api 함수 직후) — 날짜 포맷 유틸리티이나 파일 내 fmtAsOf() 호출 0건. REAL_SCHEDULE.asOf는 문자열 리터럴로 직접 할당
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `wallBoardBBox` — IIFE 내 wall signage 섹션, shared board specs(MOTTO_SPEC·TODAY_SPEC·CAL_SPEC) 직후 — 주석 '→ overlap tests'이나 파일 내 wallBoardBBox() 호출 0건. 말풍선 겹침 해소는 plates 기반 독립 로직으로 구현되어 이 함수와 무관
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [stale-notice] `TERM_IV` — IIFE 내 CHRO 터미널 섹션 선언부 / loadRealData() 내 초기화 — TERM_IV·TERM_DL·TERM_OB 배열이 선언 후 어디서도 항목이 추가되지 않아 항상 빈 배열. 터미널 help에 '면접'·'마감'·'온보딩' 명령이 열거되나 항상 빈 결과를 반환. 의도적 프라이버시 결정이지만 help 문구는 이를 안내하지 않아 혼란
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `lf-row.dim` — 메인 <style> 블록 내 .lf-row 규칙 말미 (/* 2026-07-10 매니저 피드백 */ 주석 직후) — .lf-row.dim{opacity:1} 과 .lf-row.dim2{opacity:1} 모두 브라우저 기본값과 동일 — 시각 효과 없음. JS renderFeed()에서 클래스는 여전히 할당되나 CSS 규칙 삭제 후에도 표시 변화 없음
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `cm-msg.ok` — <style> 블록 79번째 줄 — .cm-msg.err 바로 아래 — submitCheck 성공 경로는 closeOv+reloadRows로 끝나며 cm-msg.ok 클래스를 적용하는 JS 경로가 파일 전체에 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <script> 블록 178–180번째 줄 — renderModeSelect 함수 직전 — 2026-07-04 시점 변경 이력 주석. 오늘(2026-09-13) 기준 이미 2개월 이상 경과한 적용 완료 변경이며 이력 정보는 커밋 메시지에 속함
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 80번째 줄 — .modal.wide 규칙 직전 — 이미 적용된 수치(680px)가 바로 아래 CSS에 반영돼 있어 주석이 전달하는 정보는 순수 변경 이력뿐; WHY(레이아웃 이유) 없이 WHAT만 남은 이력 주석
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 29번째 줄 — textarea 규칙 직전 — '가로는 폭:100% 규칙과 충돌' WHY는 유효하나 '2026-08-25 매니저 지적, 면담 작성칸 확대' 이력 애트리뷰션이 혼재해 단순화 후보; WHY만 남기고 이력 부분 제거 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <script> 블록 197번째 줄 — proceedCheckin 함수 직전 — '기존 init() 로직 그대로'는 이전 코드 구조 참조(changelog 성격); 함수명 proceedCheckin만으로 역할이 충분히 전달되므로 실무 가독성 기여가 낮음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-id] `lg_sub` — 104번째 줄 — ovLogin 모달 p.sub 요소의 id 속성 — 파일 전체에서 getElementById('lg_sub') 또는 #lg_sub 참조가 0건; 요소 자체는 살아있으나 id 속성만 미사용 죽은 식별자
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `wf_sub` — 116~125번째 줄 — ovWrite 모달 내 wf_sub(상단)와 lock-note(하단) — 작성 모달 동시 노출 구간에서 '저장 후 수정 불가'(wf_sub, openWrite L316 세팅)와 '저장 후에는 수정할 수 없습니다'(lock-note L125)가 동일 경고를 중복 표시
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
### D. 장황 단순화 (4건)
- [verbose-block] `modal.wide` — 41~43번째 줄 — .modal.wide 룰셋 직전 3행 주석 — '480→680px, 3~4줄→7~9줄로 확대' 이전 값 비교 이력과 매니저 지적 날짜는 현재 코드 독해에 불필요; 모바일 레이아웃 동작 설명 부분만 가치 있음
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [verbose-block] `WEEK_QUESTIONS` — 143번째 줄 — WEEK_QUESTIONS 상수 선언 직전 한 줄 주석 — '매니저 확정본 · 2026-07-23 3~12주차 심층 대화형 개정' 부분은 이력 메타정보로 코드 독해에 불필요; 파서 호환 메모 후반부만 유용
  - 게이트: 근거: 리포 참조 14건(git grep 실측) — 확인 필요
- [verbose-block] `textarea` — 29번째 줄 — textarea 룰 인라인 주석 — 레이아웃 충돌 이유 핵심('가로는 폭:100% 규칙과 충돌') 뒤에 붙은 '(2026-08-25 매니저 지적, 적는 칸 확대)' 이력 서픽스는 중복 잡음
  - 게이트: 근거: 리포 참조 471건(git grep 실측) — 확인 필요
- [dead-markup] `--blue` — 11번째 줄 — :root CSS 변수 선언부 — 파일 내 var(--blue) 참조가 0건; --green·--red·--amber는 각각 실사용 중이나 --blue만 사용처 없음
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `blue'
usage: git grep [<options>] [-) — 확인 필요

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `serif` — CSS <style> 블록, :root 변수 선언 직후 — HTML 전체에서 class="serif"가 적용된 요소가 0개. 서리프 폰트는 h1, .sec-letter, .node-chro .nm, .safety h2 등 각 선택자별 font-family 직접 지정으로 이미 처리됨.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 905건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `평가 실시 콘솔 표시 제거 경고` — 섹션 B — '인사평가 저장·평가지 렌더', '관리자 업무평가·운영부 가산점 산출', '자기평가·리더십평가' 세 item 각각 첫 줄 warn 단락 — '2026-08-17 평가탭 화면 정리로 콘솔 표시만 제거, API·백엔드 무접촉' 사실이 독립 카드 3곳에 거의 동일한 문장으로 반복. 평가 서브섹션 서두에 1회 통합 후 교차참조로 대체 가능.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (5건)
- [stale-notice] `갱신일 2026-08-04 (header pill)` — header .header-meta 영역 첫 번째 pill — 페이지 내 최신 기능 변경이 2026-08-26(@86 배포, 전사등재 5필드 확장)까지 반영되어 있어 header 갱신일 2026-08-04는 stale.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `갱신일 2026-08-04 (footer)` — footer 블록 — header pill과 동일 사유 — 실제 최종 배포 2026-08-26(@86) 대비 stale.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `쓰기 액션 48종` — header .header-meta 영역 네 번째 pill — G섹션 h3은 '액션 전체 — 54종'으로 명시하고 실제 테이블에서 집계해도 54종(cal-* 4종·fix-emp-field·hr-schedule-feed·log-fix·schedreq-approve·schedreq-reject·ledger-set·roster-set·schedboard-roster·leave-balance·holiday-set 등 신규 추가). header의 48종은 6종 미반영으로 stale.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `읽기 DB 7종 + 휴무·자동화로그·업무평가·자기평가·리더십평가 탭 (header pill)` — header .header-meta 영역 세 번째 pill — G섹션 DB 표에는 연차원장·보드명단·공휴일·개인일정·운영기준 탭이 추가 열거되어 있으나 이 pill에 누락. 실제 탭 합산은 17개(7 db:코드 + 운영 4 + 관리자전용 6).
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `읽기 DB — 7종 + 운영 탭 2종 + 관리자 전용 탭 3종` — 섹션 G '데이터 기반' DB 테이블 바로 위 h3 — 실제 테이블에는 운영 탭 4종(휴무·연차원장·보드명단·공휴일)과 관리자 탭 6종(자동화로그·업무평가·자기평가·리더십평가·개인일정·운영기준)이 있어 '운영 탭 2종·관리자 탭 3종' 서술은 stale.
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### D. 장황 단순화 (3건)
- [verbose-block] `매니저 개인 캘린더 item` — 섹션 E '배포·인프라' 4번째 item — @84·@86 버전 이력·비활성 버튼 경위·COO/GM 합의 미확인 경과·ensureSchemaHeader_ 구현 세부·왕복검증 건수까지 단일 카드에 혼재해 실무 가독성 저해. 현재 상태(18열·배포완료·SESSION_ROLE 게이트·비활성 버튼 현황)만 간결하게 정리하면 충분.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `Apps Script 백엔드 @86 item` — 섹션 G '인프라' 첫 번째 item 단락 — @79·@81·@82·@84·@86 전체 버전별 변경 이력이 단일 단락에 연속 기술되어 현재 계약(API 보장 내용)을 파악하기 어려움. 최신 버전 핵심 계약만 표로 요약하고 이력은 접이식·changelog 분리 권고.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `첫 출근 예정일 · 입사예정/첫출근 캘린더 · 아침브리핑 item` — 섹션 B '온보딩·재직 관리' 3번째 item — 이미 해소된 2026-08-17 이전 결함 경위(조희제 r133 사례·동명이인 4쌍 실측 배경 등)가 현재 동작 설명보다 길어 핵심 파악을 방해. 결함 서술 1줄 요약 후 현재 동작(연락처 우선매칭·미등재/등재 분기) 중심으로 재편 권고.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] `about-lead` — L159 — .about-lead 문단 / about-stats 그리드(L161~164) — about-lead 문단이 언급하는 3가지 사실(한남동 위치·9년·스포츠·스파·커뮤니티)이 바로 아래 stat 카드 3개와 완전히 겹치며, 복지 섹션 마지막 카드(L192)도 '한남동 3,000평'을 재언급해 4번째 stat까지 페이지 내 3곳에 분산 중복된다.
  - 게이트: 근거: 리포 참조 11건(git grep 실측) — 확인 필요
- [duplicate-text] `hero-p` — L151 — hero 섹션 p / L246 — .cta-inner p — hero 섹션 '채용 공고를 확인하고 … 함께 시작하세요'와 CTA '지금 관심 있는 부서의 채용 공고를 확인해보세요'가 동일 행동 유도 문구를 두 번 반복한다. 히어로와 CTA 사이에 콘텐츠가 충분히 짧아 중간 단계 없이 두 번 노출된다.
  - 게이트: 근거: 리포 참조 21건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `dept-soon-closed-duplicate-css` — L102~116 — style 블록 내 .dept.soon / .dept.closed 규칙셋 6줄 — .dept.soon .tag와 .dept.closed .tag, .dept.soon .btn과 .dept.closed .btn, opacity:.78이 선언 값까지 완전히 동일하게 두 번 반복된다. '.dept.soon, .dept.closed' 복합 선택자로 3쌍을 통합하면 6줄→3줄로 축소 가능.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> 블록 — .m-values 정의 직후 — .val-chips 및 .val-chips span 룰이 정의되어 있으나 HTML 본문 어디에도 class="val-chips" 요소가 없고 JS에서도 참조 0건
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 33건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (4건)
- [duplicate-text] `4대보험-perk-vs-복리후생` — m-perk 카드 h3+p ↔ m-list 복리후생 항목 — 4대보험(국민연금·고용·산재·건강) 내용이 시각 카드(h3+p 설명)와 복리후생 목록 항목에 동일하게 반복됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `퇴직금연차-perk-vs-복리후생` — m-perk 카드 h3+p ↔ m-list 복리후생 항목 '퇴직금 제도' + '연차 / 월차 제도' — 퇴직금·연차/월차 제도 내용이 시각 카드와 복리후생 목록에 동일하게 반복됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `직원할인카페-중복` — m-perk-wide AI 카드 p 텍스트 말미 ↔ 복리후생 목록 마지막 항목 — 직원할인(카페)이 AI 업무 서포트 카드 설명 끝에 의미 연결 없이 부록 나열되어 있고 복리후생 목록에도 독립 항목으로 중복 등장
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `3년경력-자격요건-vs-우대사항` — 자격 요건 '수행·의전 경력 3년 이상 (경력직)' ↔ 우대 사항 '3년 이상 수행·의전 경력자' — 3년 이상 수행·의전 경력이 필수(자격 요건)와 우대 사항 양쪽에 모두 등장해 지원자가 필수·우대 구분을 오독할 수 있음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `추가태그주석-fetch` — 첫 번째 <script> 블록 첫 줄 주석 — 완료된 작업 태그(A-5 P2·G5, 시안2)와 날짜가 인라인 주석으로 잔존 — 이력은 git 커밋에 있어야 할 내용
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `추가태그주석-jpg` — 두 번째 <script> 블록 첫 줄 주석 — 완료된 작업 버전 태그(A-5)가 인라인 주석으로 잔존
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `추가태그주석-apply` — 세 번째 <script> 블록 첫 줄 주석 — 완료된 작업 버전 태그(A-5)가 인라인 주석으로 잔존
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `values-diagram-css-comment` — <style> 블록 — .values-diagram 룰 바로 위 — 과거 실패한 접근법(SVG 1·2차 시도, 커밋 해시 42c3b999, resvg-js 도구 명)을 CSS 파일 내 4줄로 서술 — 이 이력은 git 커밋에 있으며 현재 .values-diagram 한 줄 룰로 충분
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
### B. 중복 설명 병합 (3건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 08 마지막 li(이력서(사진 포함) · 자기소개서(선택) · 보유 자격증 사본(해당 시)) vs 지원 및 문의 apply-line(이력서(사진 포함)·자기소개서·보유 자격증 사본을 위 이메일로 보내주시면…) — 지원 서류 목록이 섹션 08과 연락처 안내 두 곳에 반복. '자기소개서(선택)' 명시 여부가 달라 내용 불일치도 발생.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 01 col-5 파트너 등급제 사이드바(어소시에이트/기본/마스터/시니어/팀리더 전 항목) vs 섹션 04 혜택·복지 '파트너 등급제' 항목 설명(어소시에이트 → 기본 → 마스터 → 시니어 → 팀리더) — 등급 경로 전체가 섹션 01 사이드바 표와 섹션 04 혜택 설명에 동일 내용으로 반복.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 지원 및 문의(m-contact) .cbox 문의 전화(02-6261-1202 / 나우열 매니저) vs 페이지 푸터(m-foot .contact)(02-6261-1202 / 나우열 매니저) — 전화번호와 담당자명이 연락처 카드와 페이지 최하단 푸터에 완전 중복 표기.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 최상단 주석 — 파일 복제·이식 이력과 '시안' 표현이 라이브 파일에 잔존하는 개발 메모(2026-08-25 A-2). 현재 상태를 반영하지 않음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 내 Hero 섹션 주석 — 2026-08-26 매니저 검토 이력을 기록한 개발 메모. 라이브 파일에서 유효한 맥락이 없는 과거 이력.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 09 운영 안내, 두 번째 항목 — '2026.6 기준' 날짜 앵커가 현재(2026-09-13) 시점에서 3개월 경과. 정책 유효 여부 재확인 및 날짜 표현 갱신 검토 필요.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `deal-cap` — 섹션 01 m-deal 카드, deal-rate 바로 아래 단락 — 바로 위 대형 숫자(deal-rate '40 → 55%')가 수치를 이미 시각적으로 표시하고, deal-foot에서 '정착지원금 기간(3개월) 40% → 종료 후 55%'로 맥락까지 제공. deal-cap은 동일 수치를 텍스트로 한 번 더 반복.
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `val-chips` — <style> 블록 — .m-values 영역 CSS 근처 — HTML 전체에 class="val-chips" 요소 0건. 동일 기능은 .chips/.chip 클래스가 담당
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 33건(git grep 실측) — 확인 필요
- [css-class] `badge.closed` — <style> 블록 — .m-hero .badge 관련 CSS — JS 마감 분기는 #mContact·#topStatus에만 classList.add('closed')를 호출; .m-hero 내 .badge(#heroBadge)에는 closed 추가 경로 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 15건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] `영어회화_급여추가조정` — .m-salary .note 카드 및 .m-shift 우대사항 카드 — '영어 회화 가능자 → 급여 추가 조정' 안내가 연봉 카드 note와 우대사항 목록 두 곳에 동일 취지로 반복
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `전화번호_나우열매니저` — .m-contact .cbox(☎ 문의 전화) 및 .m-foot .contact — 02-6261-1202 · 나우열 매니저 연락처가 지원문의 카드와 페이지 하단 푸터에 동일하게 반복
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `추가_스프린트_버전태그` — 첫 번째 <script> 블록 첫 줄 주석; 두 번째·세 번째 script 블록 첫 줄도 동일 패턴([추가 2026-07-18 A-5]) — A-5, P2·G5, 시안2 등 내부 스프린트 식별자 참조 주석 — 외부 공개 페이지에서 역할 없는 개발 이력 태그
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `values_diagram_png_history_comment` — <style> 블록 — .values-diagram CSS 규칙 직전 주석 — html2canvas 실패 이력·커밋 해시·래스터라이즈 과정을 4줄로 설명하는 개발 이력 주석 — 실무 유지보수에 불필요한 배경 정보
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> 블록 — .m-values 관련 규칙군 — HTML 본문 전체에 class="val-chips" 사용 0건 — values 섹션이 칩 UI에서 PNG 다이어그램으로 교체되면서 잔류한 스타일 규칙
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 33건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk 카드 세 번째(유니폼) vs .m-list '복리후생·지원 서류' 항목 — "유니폼 제공"이 아이콘+설명 포함 독립 perk 카드와 복리후생 리스트 항목(직원할인(카페) · 유니폼 제공) 양쪽에 중복 등장
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk-wide p 말미 vs .m-list '복리후생·지원 서류' 항목 — "직원할인(카페)"이 AI 업무 서포트 설명 말미에 이질적으로 삽입되고 복리후생 리스트에도 별도 기재 — 맥락 부조화+중복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> 블록 IIFE 본문 첫 줄 주석 — 태스크 코드(A-5 P2·G5)·시안 번호(시안2)·날짜(2026-07-16) 등 내부 이력 태그가 실운영 후 낡은 참조로 전락
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 두 번째 <script> 블록 downloadPageAsJpg 함수 선언 바로 위 — "[추가 2026-07-18 A-5]" 태스크 코드·날짜 태그가 낡은 내부 이력
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 세 번째 <script> 블록 첫 줄 주석 — "[추가 2026-07-18 A-5]" 태스크 코드·날짜 태그가 낡은 내부 이력
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `m-hero .badge.closed` — <style> 블록 — .m-hero .badge 하위 변형 규칙 — 마감 동기 JS가 mContact·topStatus만 업데이트하고 heroBadge에는 .closed를 추가하지 않음 — 런타임에 이 셀렉터가 일치하는 경우 없음
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 — .values-diagram 규칙 바로 위 CSS 주석 — SVG→PNG 전환 실패 이력을 130자 이상 다단 서술 — 핵심은 1줄로 충분 (예: /* PNG: svg/div 방식이 html2canvas에서 실패 — commit 42c3b999 */)
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — CSS 블록 — .m-values{} 선언 바로 다음 두 줄 — val-chips 클래스는 CSS에 두 룰로 정의되나 HTML 전체에 해당 class 속성 사용처 0건. 하단 태그 섹션은 .chips/.chip 클래스를 사용하며 val-chips와 별개.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 33건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (3건)
- [duplicate-text] `02-6261-1202 나우열 매니저` — .m-contact .cbox 문의 전화 박스 + .m-foot .contact 링크 — 전화번호 02-6261-1202와 나우열 매니저 이름이 본문 지원 섹션과 푸터에 동일하게 중복 노출됨.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `주임 반장 팀장 3단계 진급` — .m-perk 명확한 진급 체계 카드 p + .m-ladder .ladder-row step 3개 — 주임→반장→팀장 3단계 진급 구조가 혜택 카드 본문(문장)과 진급 시스템 카드(단계 도식) 두 곳에 내용 중복.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `유니폼 제공` — .m-perk-wide p 텍스트 후반부 + .m-tags .chips 내 span.chip — 유니폼 제공 내용이 AI 서포트 카드 본문(괄호 부연 포함)과 직원 복지 칩 두 곳에 중복.
  - 게이트: 근거: 리포 참조 30건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `values-diagram PNG 교체 결정 주석` — CSS 블록 — .values-diagram 룰 바로 위 4줄 주석 — SVG→PNG 전환 과정의 1차·2차 실패 이력과 커밋 해시(42c3b999)를 담은 결정 로그. 결정은 완료·고정되어 현행 유지보수에 실질적 안내 가치 없음.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `m-hero badge closed` — CSS 블록 — .m-hero .badge 룰 바로 다음 줄 — 마감 처리 JS가 mContact·topStatus에만 closed 클래스를 부여하며 #heroBadge에는 부여하지 않음. 현행 JS로는 이 룰이 발동되지 않는 준비 코드.
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `CSS·JS 날짜 버전 인라인 주석` — CSS 블록 .jpg-dl-btn 위 + JS script 블록 function 위 3곳(JPG·apply·apply sub) — 날짜·버전 레이블(2026-07-18 A-5)이 CSS 및 JS 주석에 반복 삽입. 결정 이력은 git log로 추적 가능하므로 소스 내 날짜 주석의 가독성 대비 정보 가치가 낮음.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `cols` — <style> 블록 — .kicker .k-sub 바로 다음 연속 3줄 — Part 1~4 재구성(2026-07-08 GM) 이후 정적 마크업·JS innerHTML 템플릿 어디서도 class="cols" 참조 없음; @media print 내 .cols{gap:16px;} 및 @media (max-width:820px) 내 .cols{grid-template-columns:1fr;} 잔재도 함께 제거 대상(개별 줄로 별도 확인 필요)
  - 게이트: 소비자 1117건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `big-line` — <style> 블록 — .hero-sub 바로 다음 2줄 — 정적 HTML 마크업과 JS 동적 생성 HTML(renderSales·renderAward·renderDirs·renderArchive 등) 어디서도 class="big-line" 미사용
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `esc` — 1번째 <script> IIFE와 2번째 <script> IIFE 각각의 상단 — esc()·fmtWon()·RAW_BASE('/repo/') 세 심볼이 두 IIFE에 완전히 동일하게 선언됨
  - 게이트: 근거: 리포 참조 4188건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `SALES_GVIZ` — <head> 주석 블록 — 강습팀 매출 소스 설명 중 — 주석은 SALES_GVIZ '폐기'라 하지만 코드는 readGvizDeptMap(SALES_GVIZ, 1) 호출 유지(운영부 베이스맵 용도); '강습팀 용도 폐기, 운영부 베이스맵은 유지'로 정정 필요
  - 게이트: 근거: 리포 참조 22건(git grep 실측) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <head> 블록 주석 전체(약 20줄) — 개발 일지·수정 날짜·이전 시도 실패 기록이 혼재; SSOT는 커밋 로그가 담당하므로 데이터 소스(GAS·GVIZ·JSON 경로) 3줄과 기간 셀렉터 한 줄만 남기고 나머지 축약 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 말단 @media print 블록 내 7줄 CSS 주석 — 실측 실험 과정(분기점 0.77·0.765 등)이 장황하게 남아 있음; 결론 값(zoom:0.74)과 이유 한 줄만으로 충분
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [dead-markup] `_sel` — 2번째 <script> IIFE 변수 선언부 — _sel은 selectPeriod 내 _sel = id 할당만 있고 읽는 곳이 없는 write-only 상태변수; 기능에 영향 없으나 'use strict' 환경에서 선언·할당 동시 제거 필요
  - 게이트: 근거: 리포 참조 660건(git grep 실측) — 확인 필요

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `hint` — <style> 블록 18번째 줄 — .hint 선택자가 정의돼 있으나 <body> 내 어떤 요소에도 class="hint"가 없고 JS로 동적 추가하는 코드도 없음 — 완전 미사용 스타일 규칙
  - 게이트: 소비자 1361건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
- (정리 후보 없음)

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — <head> meta description vs <div class="box"> 첫 번째 <p> — meta description과 visible <p> 본문이 '항해 지도는 자율 작업 현황 ▸ 북극성별 보기로 통합되었습니다' 문장을 거의 동일하게 반복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <script> 블록 전체 — location.replace()는 일반 브라우저 환경에서 예외를 발생시키지 않으므로 try/catch 래핑이 불필요하게 장황하고, 빈 catch(e){} 는 가능한 오류를 묵음 처리함
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### D. 장황 단순화 (1건)
- [verbose-block] `wp-typography.css` — <head> 하단, <style> 블록 직후 — 0초 리다이렉트 스텁 페이지에서 외부 타이포그래피 시트를 로드하나, 본문에 타이포그래피 클래스가 전혀 없고 인라인 <style>이 body·a 선택자를 이미 커버함. 사용자가 실제 렌더링을 볼 가능성이 없는 스텁에서 불필요한 네트워크 요청을 추가함.
  - 게이트: 근거: 리포 참조 137건(git grep 실측) — 확인 필요
