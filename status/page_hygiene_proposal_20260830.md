# 주간 페이지 위생 정리안 — 20260830 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: 전체

## 시설부 체계 — `3. 웰페리온 가이드/coo/check/시설부 체계.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `mpEsc` — 월간보고 탭 블록 — FM_DEPT 선언 직후 — fmEsc와 함수 본문이 완전히 동일한 HTML 이스케이프 함수를 별명만 달리해 재선언 — 공용 헬퍼 1개로 통합 가능
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `fcRenderRoundTime` — fcRenderRoundTime 함수 정의 바로 위 한 줄 주석 — #fcRoundTime 폐지 이력은 이미 완료된 리팩터를 가리키는 잔존 메모 — 코드 어디에도 #fcRoundTime 참조 없음
### D. 장황 단순화 (4건)
- [verbose-block] `fmMergeCats` — fmMergeCats 함수 선언 직전 5행 블록 주석 — 버그 원인·경위·재현 조건을 5행 내러티브로 서술 — 커밋 메시지 수준이며 코드 파일 내 가독성을 해침
- [verbose-block] `FM_RETIRED_CATS` — FM_RETIRED_CATS 변수 선언 직전 5행 블록 주석 — 폐지 경위·수치(83칸·70%·78%)·폐지 사유를 5행으로 서술 — 변수명과 renderFmCategory 렌더 텍스트로 이미 의도가 전달됨
- [verbose-block] `renderFmKpi` — renderFmKpi 내 '점검한 날 수' div 직전 3행 블록 주석 — 레이블 변경 이유를 3행 내러티브로 기술 — 레이블 텍스트 '점검한 날 수'가 이미 의도를 전달하므로 코드 내 불필요한 장황 설명
- [verbose-block] `renderA3FacilityMonthlyFromData` — renderA3FacilityMonthlyFromData 내 catRows 빌드 라인 직전 2행 주석 — 버그 발견 경위를 2행으로 기술 — fix는 이미 코드(fmMergeCats 호출)에 반영됐으며 이력 메모가 코드 내에 잔존

## 지원부 체계 — `3. 웰페리온 가이드/coo/check/지원부 체계.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] `inspMemoBoxHtml` — escapeAttr 직후 / renderDayFocusSection 직전 — 공유 배정 메모 섹션 — 개발자가 drawUI 내 주석으로 '렌더 제거·다른 참조 없음'을 명시 선언한 미사용 클러스터(변수 2개 + 함수 3개)
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `_relocateDayItems` — getSched 래퍼 직전 — F1 요일이동 함수 정의부 — getSched 재작성(2026-06-29) 주석 '2026-06-27: _relocateDayItems 제거'로 호출부가 명시적으로 삭제됨. 이 청크 전체에서 호출 없음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `quickAddOpen` — quickAddBarHtml 직후 — 빠른 항목 추가 UI 핸들러 — quickAddBarHtml이 항상 '' 반환(GM 2026-06-12 제거)하므로 .quickadd-btn onclick으로 이 함수를 호출하는 DOM이 생성되지 않음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `quickAddSave` — quickAddOpen 직후 — quickAddOpen(A2)의 addEventListener 등록에만 의존. quickAddOpen이 dead이므로 이 함수를 바인딩하는 코드가 실행되지 않음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `둘째주_휴관_작업_이중_하드코딩` — ① #a3-closedday-print .cdp-grid  ② #tab-manual .manual-body .cd-grid — A·사우나·B·락커룸·C·내부·E·외부 항목 목록이 화면용(cd-card)과 A3 인쇄용(cdp-card) 두 곳에 각각 하드코딩. 한 곳 수정 시 다른 곳이 불일치 가능.
### C. 낡은 안내·버전 배지 (9건)
- [stale-notice] `a3-monthly-print` — #a3-monthly-print 인쇄 컨테이너 — .mrp-main-title 및 전체 본문(제목·KPI 5칩·본문·푸터) — 제목·KPI·본문·푸터 전체가 2026-06-30 기준 하드코딩. '6월 점검 작업 약 100건' 등 6월 데이터가 정적 텍스트로 박혀 있고 오늘(2026-08-30) 기준 2개월 경과. JS 동적 주입 없이 고정 HTML만 존재.
- [stale-notice] `파트너팀_수영팀_대청소_표` — tab-guide — 🏊 파트너팀(수영팀) 업장 청결 관리 tbody 전체 — 표 내 모든 일정(7/3·7/4·7/6·7/10·7/20·7/23·7/24)이 2026-07월로 경과. '7월 종료 — 결과 미기록' 명시됐으며 8월 이후 갱신 없음. '미기록' 다수.
- [stale-notice] `충원_진행_중_텍스트` — tab-policy ⏱ 근무·휴게 시간 컬럼 — 지원부(남) 오전조 근무자 td — 2026-06-24 기준 '충원 진행 중' 문구가 2개월 경과. 실제 충원 완료·방침 변경 여부가 이 셀에 미반영될 수 있음.
- [stale-notice] `최종_등록_기준_배지` — tab-guide 👥 직원 구성·역할 카드 — 하단 설명 p 태그 내 span 배지 — 2개월 전 고정 날짜 배지. 이후 직원 변동 시 실무자가 오래된 기준을 최신으로 오해할 수 있음.
- [stale-notice] `inspMemoBoxHtml` — drawUI 함수 내 라운드 렌더 블록 — zoneOrder 루프 직전 단독 줄 — A 후보와 동일한 사실을 재기술하는 묘비(tombstone) 주석 — 클러스터 삭제 후에도 잔존하면 혼란 이중화
- [stale-notice] `resetManualLocalView` — renderManualItems 끝 직후 / togManualItem 직전 단독 주석 — 이미 제거된 함수를 설명하는 묘비 주석 — 함수 본체·호출부 모두 파일에 없음
- [stale-notice] `renderManualItems` — renderManualItems 함수 내 html 조합 블록 시작 직전 — 이미 제거된 UI 버튼 2개를 설명하는 묘비 주석 — 해당 버튼이 html 어디에도 생성되지 않음
- [stale-notice] `STAFF_SEED_황용석_note` — STAFF_SEED 배열 첫 번째 항목 — 오늘(2026-08-30) 기준 '6월말 퇴직 예정' 시점 경과. 저장 이력 없는 초기 로드 시 사용자에게 stale 정보가 표시됨.
- [stale-notice] `mrSubmitBreakdown_dated_example` — mrSubmitBreakdown() 반환 HTML 마지막 div — 특정 날짜·항목 수·완료율을 하드코딩한 측정 예시가 매월 월간보고 화면에 항상 표시됨. 9월 이후 수치가 실제와 무관해짐.
### D. 장황 단순화 (3건)
- [verbose-block] `_LEGACY_ID_MAP` — JS 마이그레이션 블록 — _migrateLegacyItemIds 함수 직전 — 이 chunk 전체에서 _LEGACY_ID_MAP을 읽는 코드가 없음. 실 마이그레이션은 _LEGACY_ID_MIGRATIONS를 직접 순회. 'alias' 의도이나 실 호출처 미확인.
- [js-function] `groupSubmitBarHtml` — collectGroupSubmits 함수 직후 — 항상 '' 반환하는 스텁이 drawUI 렌더 루프와 renderDayFocusSection 에서 항목 수만큼 반복 호출됨 — 호출부 제거 또는 인라인 '' 대체가 실질적 경량화
- [verbose-block] `dead_seed_sync_comment_pair` — const MGMT_STORAGE_KEY 선언 직전 — 제거된 기능(시드 자동동기) 구현 설명 주석이 폐지 주석 바로 앞에 불필요하게 병존. 폐지 주석 한 줄로 충분.

## 운영부 체계 — `3. 웰페리온 가이드/coo/check/운영부 체계.html`
- ⚠️ 감사 실패: 조각 1/1: JSON 파싱 실패

## 주차관리부 체계 — `3. 웰페리온 가이드/coo/check/주차관리부 체계.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(900s)

## 파트너팀 체계 — `3. 웰페리온 가이드/coo/check/파트너팀 체계.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(900s)

## 전사_일정 — `3. 웰페리온 가이드/coo/check/전사_일정.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `cal-head` — CSS <style> — /* ── 월간 달력 ── */ 섹션 두 번째 룰 — 달력 내비게이션을 .title-row 안으로 이동(GM 지시 2026-08-29) 후 .cal-head 요소가 HTML 정적 마크업과 JS renderCalendar() 출력 HTML 어디에도 없다
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `row.flash` — CSS <style> — @media(max-width:480px) 블록 직후 — highlightDate()가 renderDayPanel() 호출로 교체된 뒤 .row 요소에 flash 클래스를 추가하는 JS 코드가 전혀 없다; @keyframes calFlash도 .row.flash 외 참조처 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `ecard.na` — CSS <style> — .ecard 룰 블록 — inlinePanelHtml()이 .ecard에 부여하는 클래스는 inlineedit뿐이고, 페이지 내 어디에서도 .ecard 요소에 na 클래스를 추가하는 코드가 없다
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — JS — renderDayPanel() 함수 정의 직전 4줄 주석 블록 마지막 줄 — '지금은 칸이 없어'가 사실과 다름 — efTime()이 시간 입력 칸을 이미 생성하고, renderDayPanel() sort 로직도 이미 시각 오름차순 정렬을 구현하고 있다
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — JS — uploadEvidence() 내 '알 수 없는 action' 분기 — 배574 이후 배632·배783·배798이 배포됐으므로 이 alert 문구가 현 시점 사용자에게 올바른 조치를 안내할 수 없다
### D. 장황 단순화 (4건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — CSS <style> — .title-row 룰 직전 주석 — 대응하는 .summary CSS 룰이 이미 없는데 삭제 이유를 설명하는 주석만 남아 있다
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — HTML — <div class='calwrap'> 바로 위 주석 — 삭제 완료된 4칸 타일 기능의 경위를 설명하는 HTML 주석으로, 삭제 후에도 남아 독자에게 잡음만 준다
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — JS — var _pastOpen=false 선언 직전 2줄 주석 — 이미 삭제된 sitem·renderTiles 함수를 설명하는 주석이 남아 있고, 대응 함수가 없어 코드에 아무 기여도 없다
- [css-class] `ecard-top` — CSS <style> — .ecard-top, .ecard-top .ename 룰 및 .efield input,.efield select,.ecard-top input 복합선택자 — inlinePanelHtml()이 ecard-head만 생성하고 ecard-top 요소를 만들지 않아 .ecard-top 관련 룰이 전혀 매칭되지 않는다. 복합선택자(.efield input,.efield select,.ecard-top input) 때문에 단일 snippet 자동적용이 불가해 A 대신 D로 낮춤

## 업무 현황 SSOT — `3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html`
### A. 죽은 코드(자동삭제 대상) (5건)
- [css-class] `date-picker-modal` — <style> 블록 Date Picker Modal 섹션 — openDateRangePicker()가 동적으로 생성하는 오버레이 div에 .date-picker-modal 클래스를 부착하는 코드가 없음; inline style="max-width:320px;"가 이미 직접 적용되어 이 CSS 셀렉터의 매칭 요소 0건
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `PLAN_TEMPLATE` — JS 상수 선언부, REJECT_MARK 상수 다음 줄 — 파일 전체에서 PLAN_TEMPLATE 식별자를 참조하는 호출부 0건; 카테고리별 서식은 CATEGORY_TEMPLATES, 문서 서식은 buildDocTemplate()으로 대체되어 이 상수가 실제로 쓰이지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `BUDGET_CATEGORIES` — routeApproval() 함수 직전 상수 선언 — 파일 전체에서 BUDGET_CATEGORIES를 참조하는 호출부 0건; 예산 항목은 HTML <select> 옵션과 routeApproval() switch문에 직접 하드코딩되어 이 배열이 사용되지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `updateHeaderSub` — updateHeaderSub() 함수 내부, return; 이후 unreachable 블록 — 함수 첫 실행 줄 return;에 의해 이하 5줄이 절대 도달 불가한 dead code (2026-05-30 GM 비활성화 확인); 함수는 DOMContentLoaded에서 호출되나 아무것도 실행하지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `deptHeadFor` — OWNER_COLORS 상수 직후, ownerChip() 함수 직전 — 코드 내 '카테고리 자동 부서장 삽입 폐지 (2026-06-17 COO A)' 주석과 일치; deptHeadFor() 호출부 0건, CAT_DEPT_HEAD도 이 함수 외 직접 참조 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (3건)
- [duplicate-text] `TODO_API_URL` — 라이브스트립 IIFE 상단 (두 번째 <script> 블록) — 외부 스크립트의 const TODO_API_URL과 동일한 GAS 엔드포인트 URL을 별도 변수명으로 재선언; URL 변경 시 두 곳 동기화 필요한 중복
- [duplicate-text] `STAFF_TOKENS` — ALL_TASKS 상태 변수 선언 구역 — MEMBERS 배열과 STAFF_TOKENS Set이 동일한 8인 실무진 명단을 별도로 중복 관리; 인원 변경 시 두 곳 모두 수정해야 하는 drift 위험
- [duplicate-text] `renderQeval·renderTodoTable 헤더2장 주석` — renderQeval 함수 내 rows 배열 직전 / renderTodoTable 함수 내 h 변수 직전(두 곳) — 동일 CSS 그리드 패턴(헤더 2장 배치 이유)을 칼럼명만 달리한 채 두 함수에 각각 중복 서술 — 패턴 설명은 한 군데로 충분
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `approval-filter` — <style> 블록 Filter Bar 섹션 — buildFilters()가 생성하는 필터 버튼 어디에도 .approval-filter 클래스를 부착하는 코드가 없어 이 규칙이 적용되는 요소가 현재 0건; 결재 필터 버튼 구현 계획의 잔재로 추정
### D. 장황 단순화 (3건)
- [verbose-block] `ls-body` — .ls-body @container 폴백 규칙(@container(max-width:530px)) 직전 CSS 주석 — 단일 @container 한 줄을 설명하는 8줄 주석; 핵심("@media 대신 @container — 바깥 그리드에 의해 카드 자체 폭이 줄어들기 때문")은 1~2줄로 충분하며 구버전 pixel 측정치·재현 경위까지 포함해 장황
- [verbose-block] `qevDecodeDateScore` — qevDecodeDateScore 함수 직전 블록 주석 하단 5줄(「2026-08-25 수정:」 단락) — 구버전 KST 보정 접근법·실측 13건 근거를 5줄로 서술한 패치 이력 — 현 동작의 WHY(UTC raw 읽기)는 앞 3줄이 이미 담고 있어 중복·장황
- [verbose-block] `ymd` — renderTodoTable 내 ymd 내부함수 body(return kstDateStr(v) 위 4줄 전체) — 한 줄 래퍼(return kstDateStr(v))에 이전 절단 방식의 결함과 적용 범위를 4줄로 서술한 패치 이력 주석 — 현 동작 설명이 아닌 변경 이력

## 결재 현황 SSOT — `3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `sheet-links` — <style> 블록, .header .sub 규칙 직후 3행 — HTML 본문 전체에 class="sheet-links"(복수)를 갖는 요소가 없음. 헤더 링크는 .sheet-link(단수)만 사용.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `getUser` — updateHeaderSub 함수 직전 JS 블록 — updateHeaderSub()가 첫 줄 return;으로 즉시 종료하므로 그 안의 getUser() 호출부는 절대 실행되지 않음. 파일 내 다른 호출부 없음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `시스템 결재는 GM 종착` — renderRepApprovalRow() 인라인 <span> 과 repEscalate() confirm 대화상자 두 곳 — 동일 안내 문장이 카드 본문 상시 노출 UI(renderRepApprovalRow span)와 버튼 클릭 confirm 메시지(repEscalate) 두 군데에 정자로 중복 기재됨.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `__PV` — <head> 첫 번째 <script> 블록 최상단 주석 — 2026-07-15 나우열M 수정으로 has('pv') 무조건 스킵 방식이 폐기됐으나 외부 주석은 여전히 CEO의 'has('pv')로 교체'를 현행 동작으로 기술함. 실제 코드는 '매번 fetch+비교, 같은 주소 재이동만 차단' 방식으로 이미 교체됨.
### D. 장황 단순화 (1건)
- [verbose-block] `updateHeaderSub` — updateHeaderSub 함수 내 return; 이후 6행 — 함수 첫 줄 return;(2026-05-30 GM 지시)으로 인해 절대 실행되지 않는 6행이 함수 본문을 차지해 가독성을 해침.

## 공지 템플릿 — `3. 웰페리온 가이드/coo/notice/notice_template.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `ntool-img-btn` — CSS <style> 블록 — .ntool-fmt-bar select 규칙 직후 — HTML 마크업·JS 전체에서 class="ntool-img-btn" 사용처 0건; 이미지 삽입은 <label>+hidden input(#noticeImgInput)으로 구현됨
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `sep` — CSS <style> 블록 — /* fmt-bar — v2.27 그룹 박스화 */ 주석 직후 — .ntool-fmt-bar 내 class="sep" 요소 없음; v2.27 그룹 박스화(.fmt-group) 도입 후 구분자 역할이 .fmt-group 경계로 대체되어 잔재만 남음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `title` — <head> 내 <title> 태그 — <h1>은 'v2.2'인데 <title>은 'v2.1' — 브라우저 탭·북마크·히스토리에 구버전 표기
### D. 장황 단순화 (4건)
- [verbose-block] `imgHtml` — JS — ntCollectData 함수 내부 — v2.36 '폐기' 표기 후에도 imgHtml이 ntCollectData → ntCaptureToCanvas(d.imgHtml) → ntBuildPageHtml 파라미터 체인에 항상 빈 문자열로 전달됨; bodyHtml+imgHtml concatenation 결과에 영향 0
- [verbose-block] `fs` — JS — ntUpdatePreview 함수 상단 및 ntCollectData 함수 내부(2곳) — ntUpdatePreview 내 fs는 선언 후 미사용(본문 기본 크기는 frameMin×factor 계산); ntBuildPageHtml도 v2.58부터 fs 파라미터를 무시하고 (18×0.17) 고정 산출 — 주석에도 명시됨; d.fs 전달 체인 전체가 dead
- [verbose-block] `notice-quote` — CSS <style> 블록 — #noticePreview 미리보기 규칙군 하단 — v2.32 마크다운 파서 폐기 후 .notice-quote·.notice-hr를 미리보기에 주입하는 JS 경로 없음; 인용구는 <blockquote>(ntFmtQuote), 구분선은 <hr>(ntFmtHr)로 대체되어 #noticePreview .ntool-pv-body blockquote/hr 규칙이 동일 효과를 처리
- [verbose-block] `notice-divider` — CSS <style> 블록 — #noticePreview 미리보기 규칙군 중반 — v2.32 마크다운 파서 폐기 후 ntUpdatePreview는 contenteditable innerHTML을 그대로 삽입 — .notice-divider·.notice-list·.notice-line·.notice-tail을 미리보기에 주입하는 JS 경로 없음; NOTICE_PRESETS 포함 모든 JS가 이 클래스를 생성하지 않음. #noticePreview .notice-imgs 2규칙도 동일(imgHtml 항상 '')

## 메인가이드 O1(운영통합체계) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] `renderCheckAdvice` — home KPI IIFE — buildCheckAdvice 정의 직후 — IIFE 스코프 내 호출부 전무. buildFacilityGroupCard·buildSupportRoundCard 양쪽에서 buildCheckAdvice 결과를 advice 지역변수로 받으나 반환 HTML 문자열에 미삽입 — 💡 조언 기능이 구현됐다가 render 연결 없이 방치된 상태
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### D. 장황 단순화 (7건)
- [verbose-block] `loadKpiStrip` — loadKpiStrip IIFE 내 el.innerHTML = card(...) 직전 주석 2줄 — 배587 배번·19/46/53 실측값 등 프로젝트 관리 메타데이터가 인라인 주석에 포함돼 장황함. WHY(월간운영계획 동명 카드와 모수 혼동 방지)는 한 줄로 압축 가능하며 이력 세부는 git 로그 소관.
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — GM1 초기화 블록 — setTimeout(gm1RetrySSOTSync, 2000) 직후 — 이미 제거된 두 함수(gm1RenderAlertSignal·gm1RenderCruiseSummary)에 대한 경위 설명 3줄. 함수 본체 없이 역사 기록만 남아 있으며 커밋 메시지·PR 설명이 적합한 위치
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — GM1 IIFE 닫기 직후 — KPI 대시보드 v1 IIFE 직전 — 제거된 위젯에 대한 단독 메모 한 줄. 전후에 대응 코드가 없어 빈 기록만 존재. 커밋 메시지 위치가 적합
- [verbose-block] `FACILITY_RANGES_옛값` — home KPI IIFE — buildRangesMap 정의 직전 — 계약서로 이관 완료된 기준값을 '참고용'으로 주석 보존 중. 정본은 별도 계약서 md에 존재하므로 소스 내 복사본은 중복 잔류이며 오해 유발(옛값 실수 재사용 위험 — 주석 자체가 '사고 원인'으로 기술)
- [verbose-block] `CHECK_CARD_MIN_H` — home KPI IIFE — var CHECK_CARD_MIN_H = '0' 선언 직전 — 리터럴 '0' 상수를 설명하는 4줄 지시 기록 주석. 값은 이미 적용 완료이므로 설명 자체는 git log 수준 정보. 변수 선언 본체는 제외 대상이 아님
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — FACILITY_GROUPS 배열 마지막 항목 직후 — 배열 닫기 직전 — 배열에서 이미 삭제된 F그룹 항목의 결정 경위를 3줄로 기술. 동일 정보가 시설부 체계.html 같은 날 주석에도 존재(중복). 커밋 메시지 위치가 적합
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — buildFacilityGroupCard 반환부 — 그룹별 완료율 div 직전 — 일시 제거 후 복원된 경위를 설명하는 3줄 인라인 주석. 현재 코드 상태로 충분하며 복원 이유는 커밋 메시지 영역. 복원된 표 HTML 자체는 제외 대상이 아님

## 메인가이드 O2(공지) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [None] `완료의 단일 정의` —  — 내용 없는 열기·닫기 주석 쌍. 실제 섹션은 3285줄 callout div 로 대체됐고 이 두 줄은 빈 껍데기만 남음. 사이에 아무 DOM 요소 없음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (3건)
- [None] `common-promises` —  — <details> <summary> 텍스트(2998줄)가 이미 '우리의 약속'을 표기. 토글 바디 안 H3가 동일 제목을 반복해 펼쳤을 때 두 번 노출됨.
- [None] `common-incidents` —  — <details> <summary>(3075줄)가 동일 제목 '재발방지 현황' 표시. 토글 바디 H3가 중복.
- [None] `con-absolute` —  — <details> <summary>(3166줄)가 '절대 원칙' 동일 제목 표시. 토글 바디 H3 중복.
### C. 낡은 안내·버전 배지 (1건)
- [None] `source` —  — 최종 날짜 2026-05-28. 현재 페이지에는 2026-08 콘텐츠 다수 존재. 출처 div가 4개월 이상 뒤처져 있어 오해 유발.
### D. 장황 단순화 (7건)
- [None] `mxReadJson` —  — 5줄 산문 블록 주석. 결정 이유를 서술하지만 함수 시그니처·동작은 코드 자체로 명확. 유지보수에 필요한 핵심(raw 먼저, GAS 폴백)은 1줄로 압축 가능.
- [None] `부팅 6단계 표 삭제` —  — 삭제 이유를 설명하는 HTML 주석. 삭제 완료 후 남겨진 설명문. 읽는 사람에게 필요 없는 이력 노트.
- [None] `보고 표 형식 의무 삭제` —  — 폐기 설명 주석. 규칙 삭제 사유 서술이 코드 안에 남아 있음. git 커밋 메시지로 충분한 내용.
- [None] `브릿지 스킬 이관 주석` —  — 이관 이유 설명 주석 3줄. 이관 완료 후 callout div(3285줄)가 정본 위치를 이미 명시. 중복 설명.
- [None] `GM 보고 표준 쿵짝표 교체` —  — 교체 배경·경위 6줄 서사 주석. 섹션 시작 주석으로서의 역할은 첫 줄 하나면 충분. 나머지 5줄은 사후 회고로 git 로그에 있어야 할 내용.
- [None] `쿵짝표 두 종류 구분 주석` —  — 구분 이유 3줄 설명. 바로 다음 H4·table 두 종류 표가 자기설명적. 설명 주석이 불필요하게 선행.
- [None] `CPO Do/Don't 추정 블록 삭제` —  — 삭제 완료 후 남긴 단줄 메모 주석. CPO 탭 바디 하단에 달린 이력 노트. 콘텐츠 없음.

## 메인가이드 O3(재등록) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] `common-promises-h3` — 우리의 약속 <details> → toggle-body 상단, #common-promises div 첫 자식 h3 — <details> summary에 이미 '📌 우리의 약속 — AI·실무진이 다같이 지키는 것'이 있는데 toggle-body 첫 요소로 동일 제목 h3 반복 — 열면 제목이 두 번 노출됨
- [duplicate-text] `common-incidents-h3` — 재발방지 현황 <details> → toggle-body 상단, #common-incidents div 첫 자식 h3 — <details> summary에 이미 '🛡️ 재발방지 현황 — 같은 실수 두 번 안 나게 + 공식 값'이 있는데 body 첫 h3로 동일 제목 반복
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `gm1RenderAlertSignal` — GM1 IIFE 초기화 블록 / gm1FetchSsot 호출 직후 — 이미 삭제된 함수 2개에 대한 묘비석 주석 — 함수도 없고 정적 HTML DOM도 없어 독자에게 전달하는 현재 정보가 없음
- [stale-notice] `위임큐위젯제거` — GM1 IIFE 종료 직후 / KPI 대시보드 IIFE 시작 전 — 이미 완료된 위젯 제거를 알리는 단일 주석 줄 — 위젯과 로더 모두 이미 없으므로 현재 독자에게 전달하는 정보 없음
### D. 장황 단순화 (9건)
- [verbose-block] `mxReadJson-fetch-order-comment` — 매트릭스 JS 스크립트 블록, mxReadJson 함수 선언 5줄 직전 — 2026-08-01 fetch 순서 변경 경위를 6줄로 서술 — 코드 자체가 raw→GAS 폴백 순서를 명확히 구현하므로 이력 주석은 장황
- [verbose-block] `부팅-6단계-삭제-설명-comment` — AI 부팅·조직도 <details> toggle-body, '부팅 6단계' callout div 직전 — 이미 완료된 삭제 경위를 HTML 주석으로 보존. 바로 아래 callout이 정본 스킬을 안내하므로 중복 설명
- [verbose-block] `보고-표-형식-삭제-설명-comment` — 보고·업무 흐름 <details> toggle-body, 업무 수행 파이프라인 h3 직전 — 폐기된 옛 규칙의 삭제 이유를 본문 주석으로 보존 — 현행 쿵짝표 섹션이 이미 현 표준을 충분히 안내
- [verbose-block] `브릿지-완료4요건-위임잘림방어-이관-comment` — 완료·연속성·끊김 방어 <details> toggle-body, '일하는 규칙 3종' h3 직전 — 스킬로 이관 완료 후 경위를 본문 주석으로 보존. 아래 callout('정본 = wellperion-boot 스킬 §8')이 이미 독자를 안내
- [verbose-block] `쿵짝표-교체-설명-comment` — 보고·업무 흐름 <details> toggle-body, 🥁 쿵짝표 h3 직전 — 2026-08-08 교체 경위를 6줄 서술한 HTML 주석 — 이력 배경이며 현행 독자(AI C레벨)에게 불필요한 장황함
- [dead-markup] `완료4요건-위임잘림방어-orphaned-markers` — 완료·연속성·끊김 방어 <details> toggle-body, '일하는 규칙 3종' callout div 직후 (두 주석 사이에 콘텐츠 없음) — 콘텐츠가 wellperion-boot 스킬로 이관된 후 섹션 시작·닫기 주석 마커만 남음 — 두 마커 사이에 아무 내용도 없는 빈 구간
- [verbose-block] `CPO-DosDonts-삭제-설명-comment` — cpo 탭 패널, 협업 리듬 p 요소 직후 (탭 내 마지막 요소) — 2026-06-05 삭제 완료 후 경위 설명 주석만 단독으로 남아 있음 — 현재 독자에게 불필요한 이력 메모
- [verbose-block] `시토-운영-헌장-재편-역사-comment` — cto 탭 패널, 시토 운영 헌장 4묶음 h3 직전 (별도 헤더 주석 다음 줄) — 2026-06-26 재편 경위를 인라인 주석으로 보존 — 현재 4묶음 표가 이미 구조를 정의하므로 이력 서술 불필요
- [verbose-block] `FACILITY_RANGES_옛값` — home KPI IIFE / buildRangesMap 정의 직전 FACILITY_RANGES 삭제 주석 하단 — 계약서·GAS fcheck_ranges_get 이관 후 '참고용으로만' 남겨진 14줄 주석 변수 — 정본은 외부 계약서이므로 이 복사본은 오인·사고 재발 리스크만 남아 있음

## 메인가이드 O4 — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [dead-markup] `완료의 단일 정의` — O4 > 🌉 완료·연속성·끊김 방어 토글 > callout div 직후 (<!-- ══ /일의 브릿지 ══ --> 다음 줄) — wellperion-boot 스킬 §8로 본문 이관 후 섹션 개폐 마커 쌍만 잔류 — 사이에 아무 내용도 없는 고아 섹션 마커
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `작업 사이클 보고 포맷` — O4 > 📋 보고·업무 흐름 토글 끝부분 callout tip 직후, </div></details> 직전 — 쿵짝표(8요소)로 교체 시 본문과 여는 마커는 제거됐으나 닫힘 마커만 잔류 — 매칭 여는 주석 없는 고아 닫힘 마커
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] `common-promises` — O4 > 📌 우리의 약속 toggle body > #common-promises div 첫째 자식 — <details> summary '우리의 약속 — AI·실무진이 다같이 지키는 것'과 실질적으로 동일한 제목이 toggle 펼침 시 h3로 한 번 더 노출됨
- [duplicate-text] `common-incidents` — O4 > 🛡️ 재발방지 현황 toggle body > #common-incidents div 첫째 자식 — <details> summary '재발방지 현황 — 같은 실수 두 번 안 나게 + 공식 값'과 실질적으로 동일한 제목이 toggle 펼침 시 h3로 한 번 더 노출됨
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `Fable 시험 운용` — O4 > 전C-Level 통합원칙 toggle > ⑨ 토큰 라우팅 매트릭스 테이블 아래 단락 — 2026-07-25 기준 '시험 운용 중' 안내가 2026-08-30 현재 36일째 갱신 없음 — 시험 종료·결과·확대 판단 반영 여부 불명
- [stale-notice] `source` — O4 탭 패널 + KPI 스크립트 이후 맨 끝, M1 article 직전 — v1.0/v1.1(2026-04-24)·g4 흡수(2026-05-28) 버전 표기가 2026-08 대규모 개편 후에도 갱신되지 않아 O4 섹션의 현재 소스 구성을 오해하게 함
### D. 장황 단순화 (5건)
- [verbose-block] `쿵짝표 교체 changelog` — O4 > 📋 보고·업무 흐름 토글 > 🥁 쿵짝표 h3 직전 — 교체 완료 후 교체 경위·사고 원인·실측 수치를 6줄로 서술한 changelog 주석 — 렌더링 없이 소스만 팽창시키며 git log가 담당해야 할 내용
- [verbose-block] `브릿지 본문 이관 주석` — O4 > 🌉 완료·연속성·끊김 방어 토글 > 일하는 규칙 3종 h3 직전 — 이관 완료 후 이관 경위·GM 지시 인용을 3줄 주석으로 남겨 소스 노이즈 발생 — git log에 남겨야 할 내용
- [verbose-block] `보고 표 형식 의무 삭제 주석` — O4 > 📋 보고·업무 흐름 토글 > 업무 수행 파이프라인 h3 직전 — 삭제 완료된 규칙에 대한 사후 설명 주석 — 변경은 기정사실이므로 소스 잔류 불필요
- [verbose-block] `부팅 6단계 표 삭제 주석` — O4 > 🔌 AI 부팅·조직도 토글 > callout div 직전 — 표 삭제 이유를 서술한 사후 주석 — 작업 완료 후 소스에 잔류하는 changelog 노이즈
- [verbose-block] `CPO Do/Don't 삭제 주석` — O4 > cpo 탭 패널 > 협업 리듬 p 직후, 패널 종료 </div> 직전 — 2개월 이상 전 삭제 완료된 블록의 사유 주석이 잔류 — 소스에 남겨둘 이유 없는 완료된 changelog

## 문의회원 — `3. 웰페리온 가이드/cpo/member/membership.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [dead-markup] `holdStatusCard` — #pane-active 내부 — holdOnlyBackBtn 직후 — 휴회 카드 삭제(2026-08-13 GM 승인) 이후 진입점 0; 같은 파일 주석이 '도달 불가능(닫힌 루프)'임을 명시; 내용 없는 display:none 빈 요소
  - 게이트: 소비자 27건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `_oaMaskPhone` — _oaRender 함수 직전, 담당자 배정 pane 블록 — 함수 바로 옆 주석에 '실측 결과 이 파일에서 _oaMaskPhone 호출은 여기 한 곳뿐이었다'라고 명시하고, 그 유일 호출부를 직접 표시(esc(m.phone))로 교체함 — 현재 파일 내 호출처 0
  - 게이트: 소비자 6건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `_verifyFetchActiveFull` — _verifyFetchActiveFull 함수 말미 — bare 블록 {} 닫힘(}) 직후 — 함수 본체 전체가 bare 블록 {} 안에서 항상 return하므로 그 아래 return Promise.resolve(null)은 절대 도달 불가 — 실행 경로가 없는 죽은 구문
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (3건)
- [duplicate-text] `contact-by-select` — CSS — select 옵션 팝업 색상 보정 구역 (color-scheme 선언 직후) — 이후 선언된 전수 방어 규칙 `select, select option{ color:var(--text); background-color:var(--paper); }`와 속성·값 완전 동일 — 특이도가 높아도 같은 값이므로 실제 렌더 차이 없음
- [duplicate-text] `oa-owner-sel` — CSS — 담당자 배정 select 색상 보정 구역 — 전수 방어 `select, select option` 규칙과 속성·값 완전 동일; 이 클래스에 별도 베이스 배경 규칙이 없어 삭제 시 렌더 동일
- [duplicate-text] `_tapSectionHtmlLesson` — function _tapSectionHtml(s) 와 function _tapSectionHtmlLesson(s) 각각의 return 블록 및 empty/caveat 처리 분기 — 두 함수의 return 블록(button.tap-sec-head · span.mdash-chip · span.tap-caret · div.tap-sec-body HTML)이 문자 그대로 동일 반복 — item 렌더 분기(key 판별·showTime)와 '더 보기' 문구만 달라, 공통 골격 함수 + renderRow 콜백 인자로 병합 가능한 중복
### C. 낡은 안내·버전 배지 (8건)
- [stale-notice] `카드5·6삭제_주석` — #memberTabNav 내부 최하단 주석 블록 (/* 카드5·6(대기자/LOSS 회원 관리) 삭제(FB260801-141806 ... */) — 이미 삭제된 DOM(대기자·LOSS 카드)의 삭제 경위 4줄 서술 — 해당 DOM 부재로 실무 가독성 기여 없음
- [stale-notice] `참고_dInqMonth·dTourMon제거_주석` — #memberTabNav 닫힘 직후 '참고(정직 기록, 배754)' HTML 주석 — 삭제된 id(dInqMonth·dTourMon)의 제거 이유를 5줄 설명 — 해당 id가 DOM에 없어 현재 코드 이해에 혼란만 가중
- [stale-notice] `gvizLoadLessonInquiry_` — gvizLoadLessonInquiry_ 함수 선언 상단 주석 '// 강습 문의 목록 — gviz 어댑터(GAS lesson_inquiry_list 대체). USE_GVIZ=true일 때만 호출.' — lessonLoad 함수 내 [2026-07-16 시토] 주석이 '강습 문의는 항상 GAS로 읽는다(gviz 우회 제거)'를 명시하고 실제로 직접 GAS fetch만 실행하지만, 이 함수의 주석은 여전히 'USE_GVIZ=true일 때만 호출'이라 안내 — 강습 경로에서 이 함수가 미호출임을 숨기는 낡은 안내.
- [stale-notice] `_lessonSportTabResolved_` — _lessonRosterFor 함수 내 주석 및 _lessonEnsureSportTabLoaded_ 구현 전체 — _lessonRosterFor 주석이 '종목탭 경로는 현재 통째로 무효다(코드는 남아 있으나 결과에 영향 0)'이라 명시. _lessonEnsureSportTabLoaded_가 fetch를 실행하지만 Google 시트가 없는 탭 요청에 첫 번째 시트를 반환하고 _looksLikeInquiryTab 가드가 항상 빈맵({})을 저장 → 실제로는 항상 LESSON_INSTRUCTOR_ROSTER 폴백만 사용됨. 주석이 이 사실을 인정하면서 코드 상태는 방치.
- [stale-notice] `_mregRender` — _mregRender 내 프로그램칸 <td> 렌더 블록, '★2026-08-05 재지시' 주석 바로 아래 — 2026-08-04 결정이 2026-08-05에 번복됐음을 작성자 스스로 '참고용'으로 표기한 구 사유 주석 — 이미 해소된 우려이며 현행 코드(_mregProgLabel 두 표 통일)와 무관
- [stale-notice] `_loadHoldIntake` — _loadHoldIntake 함수 정의 직전 ponytail 주석 3행 — openHoldManage() 삭제 완료 후 폐루프로 남은 함수군을 '이번엔 안 지웠다'로 마무리한 stale known-debt 주석 — 해소 시점이 기록되지 않은 채 잔존해 진입 가능 여부를 코드 검토 없이 판단 불가
- [stale-notice] `_renderHoldIntake` — _renderHoldIntake 내 var intake = _holdIntake || []; 직전 주석 3행 — 테스트 접수 실물 삭제(배146)·화면 필터 제거(배174) 두 조치 모두 완료된 것을 기술하는 stale notice — '남겨두면 안 보일 수 있다' 경고가 이미 해소된 상황에서 코드에 잔존
- [stale-notice] `dismissBeginnerBanner` — esc() 함수 아래, 메인 script 태그 최말미 — #beginnerBanner 마크업·dismissBeginnerBanner 함수·localStorage 키가 이미 2026-07-15에 전부 삭제된 것을 기록한 사후 주석 — 현재 파일에 참조하는 코드가 전혀 없어 정보값 0
### D. 장황 단순화 (9건)
- [verbose-block] `_refreshDiskCache_head_comment` — <head> 첫 번째 <script> 블록 상단 주석 블록 (/* 다음 번 진입을 최신으로 만든다 — ... */) — CDP 실측 절차·F5 vs 북마크 동작 차이·한계까지 12줄로 서술 — 함수 동작 이해에 필요한 내용은 3줄 이내로 요약 가능; 나머지는 디버깅 일지 성격
- [verbose-block] `db-toolbar-search-group_flexwrap_comment` — CSS .db-toolbar-search-group 규칙 내 인라인 주석 (/* flex-wrap 추가(2026-07-20 시포 · GM 지적: 모바일에서 화면이 우측으로 밀림). ... */) — flex-wrap 추가 이유를 버그 재현 조건·화면 폭별 동작까지 7줄로 서술 — '모바일 가로 스크롤 방지'로 1줄 요약 가능
- [verbose-block] `_lessonValidOwners` — _lessonOwnerOptionsFor 함수와 _lessonFindRow 함수 사이의 2줄 삭제 묘비 주석 — '남겨 두면 다음 사람이 오인한다'고 경고하는 묘비 주석 자체가 남아 동일한 혼란을 야기. 함수가 이미 삭제(2026-07-27)됐으므로 묘비 주석도 함께 제거해야 경고와 행동이 일치함.
- [verbose-block] `_lessonSportMgmt` — _lessonSportMgmt 함수 본문 주석 — '★타팀 오염 제거 폐기' 및 '★팀장 자동 대입 폐기' 설명 구간(각 약 15~20줄) — 이미 제거된 두 기능(타팀 오염 제거·팀장 자동 대입)의 폐기 경위를 실무진 피드백 ID·실측 건수·경합 가설 분석까지 포함해 각각 인라인에 기술. PR 설명 수준의 역사 기록이 현재 동작 코드(~15줄)를 압도해 가독성을 저해.
- [verbose-block] `임하윤` — lessonLoad 함수 내 [2026-07-16 시토] gviz 제거 설명 주석 '실고객 유실 버그(임하윤 010-7331-3903 등)' 부분 — 버그 재현 사례로 실고객 이름과 전화번호가 소스코드 주석에 직접 삽입됨. 해당 PII 없이도 'intake 누락 버그' 설명이 완전하며, 버전 관리 이력에 실고객 정보가 영구 노출되는 문제 있음.
- [verbose-block] `NARROW_COL_WIDTHS` — NARROW_COL_WIDTHS 객체 정의 내부, ALWAYS_HIDE_COLS 선언 인근 — 해당 5개 Contact 컬럼이 ALWAYS_HIDE_COLS에도 포함돼 _activeDisplayCols에서 먼저 필터링되므로, _activeRowHtml의 NARROW_COL_WIDTHS[h] 참조 시점에 이 키들은 절대 도달하지 않는 죽은 설정값
- [verbose-block] `_activeCacheSelfTest` — _activeCacheClear 직후, _activeApplyData 이전 — 콘솔 직접 호출 전용 자체점검 함수(약 30줄)가 프로덕션 코드에 인라인 — 프로덕션 실행 경로에서 미호출이며 사용자 기능에 기여 없음
- [verbose-block] `_completenessSelfTest` — _renderActiveCompleteness 직후, _activeRender 이전 — _activeCacheSelfTest와 동일 패턴 — 콘솔 전용 자체점검 함수(약 35줄)가 프로덕션 인라인. 프로덕션 경로 미호출
- [verbose-block] `LOSS_REASON_LEGACY_MAP` — LOSS_REASON_LEGACY_MAP 객체 하단 '// v1 구값(직접 매칭)' 아래 2행 — _normLossReason이 INQ_LOSS_REASON_OPTIONS.indexOf(s) >= 0 이면 early-return하므로, 현행 옵션에 이미 포함된 v1 값 5개(key === value self-mapping)는 실행 도달 불가 — 논리적으로 무효한 항목

## 강습회원관리 — `3. 웰페리온 가이드/cpo/member/강습회원관리.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `title` — <head> title 태그 — 페이지 자체가 '통합됨' 툼스톤으로만 동작하는데 타이틀은 독립 페이지처럼 표기되어 브라우저 탭·북마크 오인 유발
### D. 장황 단순화 (1건)
- [verbose-block] `desc` — .desc 텍스트 블록 전체 — 하위 그룹 상세 열거 `(문의·금일 등록·전체 명단)`는 툼스톤 문구에서 불필요 — 버튼 레이블이 목적지를 이미 전달하며, 세부 탭명은 실제 페이지 진입 후 확인 가능

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `openModal` — 1) 헤더 .header-actions (전 탭 항상 노출), 2) 기획 작업대 탭 .section-badge-actions — 완전 동일 버튼 — 동일 onclick(openModal(null))·동일 레이블 버튼이 두 곳 중복. 작업대 탭 진입 시 동시에 노출되어 실무진 혼란 유발 가능.
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `header-feedback-slot-unimplemented-link` — 헤더 .header-feedback-slot, 피드백 버튼 바로 아래 — 2026-07-29 GM 지시로 추가 예정이던 링크 엘리먼트가 2026-08-30 현재까지 미구현. 주석만 잔존.
- [stale-notice] `성인강습-변경이력-주석` — 성인강습 탭 수영 테이블 tbody — 동일 유형 주석 3개 연속 (1:1강습 앞 / 단체반 앞 / 아쿠아로빅 앞) — 2026-07-25 확정 변경 내용이 테이블 데이터에 이미 반영 완료. 변경 경위 서술은 커밋 메시지에 속하며 런타임 HTML에 잔존 불필요.
### D. 장황 단순화 (4건)
- [verbose-block] `_todoPost` — _todoPost 함수 직전 블록 주석 — 6줄 분량의 과거 사고 서술(INC-013·INC-014·no-cors 이력)이 프로덕션 코드에 임베드됨. '왜 text/plain+redirect인가' 한 줄로 대체 가능.
- [verbose-block] `savePlan` — savePlan 함수 직전 블록 주석 — 과거 잘못된 구현 방식 서술 3줄. 함수 반환값(boolean)과 현재 로직이 의도를 이미 충분히 표현.
- [verbose-block] `deletePlan` — deletePlan 함수 내 _todoPost 호출 직전 인라인 주석 — 과거 잘못된 동작 서술 2줄. 현재 결과 확인 로직이 의도를 직접 표현하므로 중복.
- [verbose-block] `submitPlan` — submitPlan 함수 내 savePlan().then 호출 직전 인라인 주석 — 과거 사건 참조 포함 2줄 설명. savePlan(item).then(function(ok){ if (ok) closeModal(); }) 코드 자체가 의도를 이미 표현.

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `post-metric` — CSS 블록 — .post-metric / .post-metric b 연속 2룰 — JS 렌더링 함수(renderChannelPerf·renderSummary 등) 및 정적 HTML 전체 검색 결과 class='post-metric' 부여 코드 0건
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `chip-row` — CSS 블록 — .chip-row / .chip / .chip svg 연속 3룰 — chipIconSvg()는 SVG 내용만 반환하고, 감싸는 span은 chanIconHtml()에서 cls='chan-icon'으로 부여 — chip·chip-row 클래스는 이 페이지 어디에도 동적·정적으로 삽입되지 않음
  - 게이트: 적용 후 파싱 무결성 실패(<div> 태그 불균형(open=131, close=132)) — 롤백
- [css-class] `header h1` — CSS 블록 — #m1-dash .header h1 룰 — 헤더 마크업에 <h3> 태그만 존재하고 <h1> 요소가 없음 — 이 셀렉터가 적용될 DOM 노드 부재
  - 게이트: 소비자 39건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] `S2 AI-CMO 탭 반응 루프 참고` — ① 정적 HTML measure-pending div(편별 반응 성적표 섹션 앞) / ② 두 번째 <script> 블록 fetch 완료 후 wrap.innerHTML 하단 measure-pending — "판정 기준·측정 [한계/정의] 전체 = S2 AI-CMO 탭 '반응 루프' 참고(재서술 안 함)" 문구가 같은 섹션 위·아래에 각각 한 번씩, 총 두 번 렌더됨
- [duplicate-text] `전환율 최근 기간 덜 익어` — ① renderTypeSplit() footer 주석 / ② loadYtdTrend() ytd-note 완료 텍스트 — "전환율은 그 [유형/달] 문의자가 지금까지 가입한 비율이라 최근 기간일수록 아직 덜 익어 낮게 보입니다" 취지 설명이 유형별 표 하단과 월별 추이 표 하단에 각각 독립적으로 반복
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `관찰 모드 2026-07-20~2026-08-20` — 정적 HTML — 편별 반응 성적표 섹션 직전 measure-pending div 첫 문장 — 관찰 종료일(2026-08-20)이 현재 날짜(2026-08-30) 기준 10일 경과 — '관찰 모드 중' 안내가 시제상 틀림
- [stale-notice] `2026-07-31 조치 완료 renderContentAttribution` — JS renderContentAttribution() 렌더 — '2026-07-31 조치 완료' 단락 — 배포 완료 후 약 30일이 경과한 현재도 '조치 완료' 문구가 measure-pending 스타일의 강조 알림으로 상단에 표시됨 — '쌓이는 중'이 이미 현실이라면 알림 톤이 아닌 현황 표 형태로 전환 필요
### D. 장황 단순화 (1건)
- [verbose-block] `renderContentAttribution 4단락 설명` — JS renderContentAttribution() — measure-pending + '원인(실측)' div + '2026-07-31 조치 완료' div + '구조적 한계' div 4개 연속 — '데이터 쌓이는 중' 상태를 설명하는 데 4개 div 약 350자를 사용. 핵심 메시지는 '블로그·카페 배포 완료·신규 문의부터 적재, 카카오·당근·인스타는 구조적으로 채널 단위까지만 가능' 두 줄로 압축 가능

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `month-select-wrap` — CSS line 123 (주 규칙); line 127에 @media print{.month-select-wrap{display:none!important}} 단독 블록도 존재 — HTML 마크업 및 JS innerHTML 어디에도 이 클래스 미사용. 대응 UI는 .tb-month 클래스로 대체됨. print 전용 블록도 함께 삭제 필요
  - 게이트: 소비자 7건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-lbl` — CSS line 124 (.month-select-wrap 바로 아래) — HTML 마크업 및 JS innerHTML 어디에도 이 클래스 미사용. 레이블 요소는 class="lbl"이며 .tb-month .lbl 규칙이 담당
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `panel-flush` — CSS line 142 (주 규칙); @media print 내 .panel,.panel-flush 결합 셀렉터 2곳(line 226, 236)도 함께 정리 필요 — HTML 본문 전체 및 JS 생성 마크업(renderKpiTable·maybeRenderChannelFunnel·renderTypeBars 등) 어디에도 panel-flush 클래스 미사용
  - 게이트: 소비자 6건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `TOKEN_ENFORCE` — JS — const GAS_URL 선언 바로 아래 주석 — TOKEN_ENFORCE 게이트가 스스로 '폐기·휴면'임을 명시한 이미 해소된 안내. 현존하지 않는 시스템을 코드 내 참조

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — About stat(.stat-label) + Membership section-desc + Facilities section-desc — '100% 사전 예약제' 정책이 About stat 수치(100% / 사전 예약제), Facilities 안내('모든 시설은 사전 예약으로 운영됩니다'), Membership 안내('웰페리온은 100% 사전 예약제로 운영됩니다') 세 곳에 중복 언급됨
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 법인 멤버십 membership-features 네 번째 li — 법인 멤버십 혜택에 '수영·골프'를 명시하지만 Programs 섹션(WJO·Ballet·Barre·Squash)과 Facilities 섹션(Training Zone·Glass Court·Studio·Sauna·Lounge·Terrace) 어디에도 수영장·골프 시설이 소개되지 않아 페이지 내 불일치
### D. 장황 단순화 (1건)
- [verbose-block] `about-visual` — About 섹션 about-inner 첫 번째 컬럼 — 500px 높이 박스에 15% 투명도 'W' 한 글자만 표시 — 실사진·실콘텐츠 없는 플레이스홀더 상태로 정보 기여 없음; CSS도 font-size:64px color:rgba(183,159,138,0.15) 등 placeholder 전용 스타일로만 구성

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `ep-table-wrap` — @media(max-width:640px) 블록, 118번째 줄 — -webkit-overflow-scrolling:touch는 iOS 13+ / Chrome 66+ 이후 모든 브라우저에서 지원 종료된 deprecated 속성이며, overflow-x:auto는 base CSS .ep-table-wrap 룰에 이미 동일 값으로 선언되어 있어 이 모바일 룰 전체가 무효·중복
### D. 장황 단순화 (1건)
- [verbose-block] `buildM5Map` — buildM5Map 함수 내부, if(m){} 블록 (214–222줄) — 2줄짜리 조건 분기에 3줄 주석이 달려 있고, 첫 번째 주석의 우선순위 방향(< 기호, 발행완료를 가장 낮은 값으로 표기)이 실제 코드 동작('발행완료가 있으면 덮어씀')과 상충하여 혼란 유발

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `hero-band` — 두 번째 <style> 블록 — .back-kiosk 선언 직전 '종합접수처로 돌아가기' 섹션 — .wlp-inq .hero-band 첫 번째 룰셋에 position:relative가 이미 포함돼 있어 이 두 번째 선언은 CSS 효과 0
  - 게이트: 소비자 26건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `wpToSurvey` — 첫 번째 <script> 블록 — window.wpToSurvey 함수 직전 4줄 주석 — ① <!-- UTM 귀속 프리필 --> 외부 HTML 주석 ② <!-- 6종 문의 유형 --> HTML 주석 ③ 여름방학 특강 카드 HTML 주석 세 곳에 동일 내용 기술
### D. 장황 단순화 (1건)
- [verbose-block] `UTM 귀속 프리필` — 첫 번째 <script> 블록 바로 위 HTML 주석 (2줄) — 스크립트 내부 4줄 주석이 더 상세해 외부 주석은 'UTM 승계 스크립트' 한 줄로 충분; 채널 열거는 JS 코드에서 직접 확인 가능

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
- ⚠️ 감사 실패: 조각 1/1: JSON 파싱 실패

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — L124-125 info-box + L176 ✅ 사용 조건 아코디언 세 번째 li — 방 이름이 카톡 채팅방 제목과 정확히 일치해야 한다는 내용이 info-box('정확히 일치')와 사용 조건 아코디언('완전히 동일한 글자')에 실질적으로 동일하게 반복됨 — 한 곳에만 남기면 충분
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — L101 헤더 h1 내 버전 배지 — v1.0 배지는 2026-08-14 no-cors 수정 등 이후 변경분이 반영되지 않아 현재 실제 버전과 불일치할 가능성 있음
### D. 장황 단순화 (1건)
- [verbose-block] `addRoom` — L261-265 addRoom() 함수 내 fetch() 직전 — 5행짜리 구현 일지 주석 — no-cors 제거 이유는 코드 자체(redirect:'follow', res.ok 판독)로 이미 자명하고, 타 파일 교차참조(wp_inquiry_form.html)는 커밋 메시지·위키 소관; 한 줄로 충분

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 조각 1/1: JSON 파싱 실패

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(900s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `header-right` — CSS <style> 블록, .header-meta 규칙 아래 — HTML 전체에 class="header-right" 참조 없음. 헤더는 .header-btns로만 구성되며 해당 클래스 사용 불가.
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `nsNote` — 채널별 분해 탭 > 북극성 KPI 연결 섹션, 하단 설명 div — 색상 안내가 실제 JS 동작과 불일치. renderYearKpi에서 nsYearFill은 80~99%→'accent'(#B79F8A 베이지), <80%→'orange'(#e6944e)로 렌더링하지만 note는 '노란/적색'이라 기술.
- [stale-notice] `renderQuarters` — JS renderQuarters 함수, 분기 색상 배열 정의부 — CSS에 .bar-fill.warn 규칙이 없음(.gauge-fill.warn만 존재). Q3 분기 막대가 배경색 없이 투명으로 렌더링됨. 2026-Q3는 현재 진행중(8월)이므로 즉시 시각 오류 발생.
### D. 장황 단순화 (1건)
- [verbose-block] `미수금 OCF 영향 분석` — 미수금 탭 > OCF 영향 분석 섹션, 첫 번째 <p> 태그 — 재무 담당자 대상 ERP에서 OCF 개념 교육 문단은 과잉. 섹션 전체가 placeholder 상태(실측값 없음)이므로 설명만 남아 가독성 저하.

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `API_URL` — JS 섹션 최상단 // ─── 설정 ─── 블록 — 실 배포 URL이 이미 세팅돼 있는데 '배포 후 교체' 주석이 그대로 남아 미완료 상태처럼 오독됨
### D. 장황 단순화 (1건)
- [verbose-block] `getFilteredItems` — JS 섹션 하단 // ─── 공유 모달 ─── 블록 아래 — applyFilter() 내부의 3-조건 필터 체인(filterMonth·filterCategory·filterApproval → allExpenses)과 동일 로직을 별도 함수로 중복 작성 — 순수 필터 헬퍼 1개로 통합 가능

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] `obD` — ONBOARDING 섹션 — obFmt 정의 직전 행 — 조각1 전체 JS에서 obD( 호출부 0개. obFmt(v)가 동일 기능(완료 기한 슬라이스)을 대체하며 실제 호출되고, obCheckEvents()도 .slice(0,10)을 인라인 처리함.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [js-function] `ORG_GUIDE_ITEMS_DRAFT` — ORG_GUIDE_ITEMS 배열 선언 직전, 운영기준 섹션 변수 선언부 — 선언 이후 조각1 전체에서 읽거나 조건 분기에 사용하는 곳이 없음. 동일 블록의 ORG_GUIDE_CACHE_·ORG_GUIDE_LOADING_·ORG_GUIDE_ERR_·ORG_GUIDE_NAV_BOUND_는 모두 실사용되나 이 draft 플래그만 고립.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `doc-type.t-hwp` — 페이지 하단 <style> 블록, .doc-type 연속 규칙 두 번째 줄 — renderDocs() items 배열에 type="HWP" 항목이 없어 t-hwp 클래스를 생성하는 코드 경로 없음. 사용처 0.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `doc-type.t-docx` — 페이지 하단 <style> 블록, .doc-type 연속 규칙 두 번째 줄 — renderDocs() items 배열에 type="DOCX" 항목이 없어 t-docx 클래스를 생성하는 코드 경로 없음. 사용처 0.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (3건)
- [duplicate-text] `disp` — openOrgGuideModal() 내부 — orgChartHtml() 에도 동일 객체 리터럴 존재(주석 없이) — openOrgGuideModal의 주석 자체가 'orgChartHtml과 동일 표시명 매핑(상수 중복, 의미 무변경)'임을 명시. 동일 리터럴이 두 함수에 각자 하드코딩됨.
- [duplicate-text] `__bm` — buildHrCard() 함수 안 및 openPrintView() 함수 안 — 생년 파싱+유효성+만 나이 계산 블록(birth), 주소 추출 블록(addr/__am) 각각 verbatim 2회 등장 — buildHrCard와 openPrintView 두 함수에 생년 추출·유효성 검증·만 나이 계산 블록(약 3행)과 주소 정규식 추출 블록(약 2행)이 동일하게 복붙됨. geoScript 생성 패턴도 유사 반복.
- [duplicate-text] `renderEval` — renderEval() admin 분기 muted 소제목 + evalCriteriaSection() ⚠ alert 블록 — eval 탭 내 '정성평가 추후 도입 예정' 안내가 두 곳 중복 노출 — renderEval()의 muted 한 줄과 evalCriteriaSection() alert(정성평가(상담 품질 등 기록에 없는 영역)는 추후 별도 도입 예정).
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <head> 첫 번째 HTML 주석 블록 (8행) — 2026-08-06 캐시 재현 조사 경위 기록. 대응 조치(아래 meta 태그 3개 추가)는 이미 완료·배포됨. 'A-6 재검증 20260806 #1·#2 재현 유력 원인' 등 해소된 이슈 추적 문구가 포함된 완료된 조사 로그.
- [stale-notice] `kpiResult` — openPerfEval() 내부, kpiResult 함수 선언 직전 — 웨이브1 교정 완료 후 이미 해소된 변경 이력 주석. 프리필은 제거됐고 현 코드(weightedScore(readSel("pk")))가 의도를 직접 표현하므로 '제거' 기록 주석 불필요.
- [stale-notice] `loadBonus` — openPerfEval() 내부, loadBonus 함수 선언 직전 — 웨이브1 변경 이력 주석. loadBonus 구현(fetch get-work-eval → pBonusBox 표시 분기)이 동작을 직접 드러내므로 역사 주석 불필요.
### D. 장황 단순화 (4건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 최상단 /* ===...=== */ 주석 블록 (약 18행) — 색 체계 3계층 선언·변수명 계약·시맨틱 hex 일치 주석·클래스 계약 등 설계 문서 수준의 설명. :root 변수 이름과 선택적 인라인 주석으로 대체 가능하며, 상세 내용은 별도 설계 문서로 분리가 적합.
- [verbose-block] `loadOne` — loadOne() 함수 내 TOCTOU·스테일 창 설명 주석 3곳 (각 4~6행) — localWriteGuardActive_ 가드의 필요성을 동일 함수 안에서 서로 다른 각도로 3회 반복 설명(진입시점, await 직후, catch). 가드 의도를 함수 상단에 한 줄로 요약하면 충분.
- [verbose-block] `criteriaSection` — criteriaSection() 함수 정의 전체(약 75줄) + 보조 perfCriteriaCard()(약 25줄) — renderEval() 2026-08-17 리팩터에서 호출부 제거 후 페이지 내 호출처 없음. 다면평가·포상 체계 HTML 생성 블록 사문화. perfCriteriaCard()도 criteriaSection()에서만 호출되므로 동일하게 실행 경로 없음.
- [verbose-block] `evalConsole` — evalConsole() 함수 정의 전체(약 28줄) — renderEval()에서 호출 제거 후 페이지 내 호출처 0. 평가 실시 콘솔 버튼 그룹 HTML을 생성하나 렌더되지 않음. perfEvalStart·selfEvalStart·workEvalStart·leaderEvalSubmitStart·leaderReviewStart 래퍼 5개도 이 함수 내 onclick에서만 참조되어 실질 진입 불가.

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [js-function] `shiftKind` — JS <script> 블록 — isCloser 정의 직후 — render() 및 전체 코드에서 호출부 0. 반환값(sh-open/sh-close/sh-mid)이 DOM에 한 번도 적용되지 않음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [js-function] `usedOf` — JS <script> 블록 — openApply 함수 직전 — 호출부 0. 연도 무관 전체 합산이지만 실사용은 2026 한정인 usedAnnual2026으로 완전 대체됨
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `deptband` — <style> 블록 — .covrow 규칙 근처 — HTML 정적 마크업 및 render() JS 어디에도 deptband 클래스 부여 없음. render()는 covrow/deptfirst만 생성
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — const RETIRED 선언 바로 위 블록 주석 마지막 줄 — 이지영이 이미 RETIRED 객체에 반영("이지영":"2026-06-27")됐으므로 '미반영' 문구가 사실과 다름. 배158 티켓 레퍼런스는 해소된 개발 이력

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-id] `gate` — <head> 두 번째 <style> 블록 — 2026-07-10 2차 개편으로 비밀번호 게이트 제거 — body에 #gate 요소 없고 JS 참조 0건
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `AMBIENT` — JS 메인 스크립트 — ambientFeed 직전. PERSONA_LINE은 약 700줄 위 — AMBIENT 14건 중 12건이 PERSONA_LINE 값과 텍스트 완전 동일(A-1~A-12 전원). 고유 항목은 2건뿐
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `1.5초→4.5초` — JS 메인 스크립트 — setTimeout(...enableSampleFallback..., 4500) 바로 위 — 완료된 변경 기록 — 코드엔 4500만 있고 이전값 1500은 없음
- [stale-notice] `1.6초→4.6초` — 정직 배지 스크립트(두 번째 <script>) — setTimeout(sampleBadges, 4600) 바로 위 — 완료된 변경 기록 — 코드엔 4600만 있고 이전값 1600은 없음
### D. 장황 단순화 (6건)
- [css-class] `dim` — 첫 번째 <style> 블록 — .lf-row.newest 아래, @keyframes lfin 직전 — opacity:1은 브라우저 기본값 — 피드 페이드아웃 제거(2026-07-10) 후 남은 노-옵 룰
- [js-function] `fmtAsOf` — JS 메인 스크립트 — api() 정의 아래, loadRealData 직전 — 파일 전체에서 fmtAsOf() 호출 0건 — 일정 데이터 실연동 범위 제외(2026-07-10) 이후 call site 소멸
- [js-function] `agentSum` — JS 메인 스크립트 — renderTodayAgent 직전 — 주석에 "계속 사용"이라 되어 있으나 파일 전체에서 agentSum() 호출 0건. todayCount로 직접 관리
- [js-function] `sheen` — JS 메인 스크립트 — boxRound 함수 직후 (유기적 바디 보강 섹션) — 가전 표면 광택 헬퍼 — 모니터가 원목 장부로 교체된 이후 sheen() 호출 0건
- [js-function] `screenSheen` — JS 메인 스크립트 — sheen 함수 직후 (유기적 바디 보강 섹션) — 유리 화면 반사 헬퍼 — 모니터 제거 이후 screenSheen() 호출 0건
- [js-function] `boxRound` — JS 메인 스크립트 — vGrain 함수 직후 (유기적 바디 보강 섹션) — 수직모서리·윗코너 라운딩 헬퍼 — carveBox로 대체된 이후 boxRound() 호출 0건

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `cm-msg ok` — CSS <style> 79행 — .cm-msg 블록 3번째 줄 — JS 전체에서 msg.className에 'ok'를 할당하는 코드 없음. submitCheck 성공 경로는 closeOv→reloadRows→renderChecklist로 전환되므로 녹색 메시지 표시 경로 자체가 존재하지 않음.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `hdrSub` — HTML 88행 <small id="hdrSub"> 초기값 & JS 182행 renderModeSelect() textContent 할당 — 두 군데 동일 — 동일 문자열이 HTML 인라인과 JS renderModeSelect() 두 곳에 중복. init()이 즉시 renderModeSelect()를 호출해 textContent를 덮어쓰므로 HTML 초기값은 실제 렌더에 도달하지 않음.
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `modal wide` — CSS <style> 80행 — .modal.wide 규칙 바로 위 주석 — 이전 수치(480px·2줄)·날짜·지시 출처가 코드에 굳어진 변경 이력. 변경이 이미 반영된 현재 시점에서 'before' 정보는 낡음.
- [stale-notice] `renderModeSelect` — JS 178~180행 — renderModeSelect 함수 직전 주석 블록 — [추가 2026-07-04 r2] 버전 태그·날짜·'완전히 무변경' 보증 문구는 커밋 이력용 서술로 현재 코드에 불필요.
### D. 장황 단순화 (1건)
- [verbose-block] `textarea` — CSS <style> 29행 — textarea 규칙 바로 위 주석 — 핵심 이유(가로 resize → width:100% 충돌)는 한 마디면 충분; '매니저 지적·날짜·면담 작성칸 확대' 귀속 부연은 커밋 메시지 수준의 이력으로 주석에서 과잉.

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `wf_sub` — ovWrite 모달 — openWrite() L316(wf_sub '기한…·저장 후 수정 불가') vs HTML L125(.lock-note '저장 후에는 수정할 수 없습니다') — 같은 모달 안에서 '저장 후 수정 불가' 경고가 wf_sub 동적 부제목과 .lock-note 정적 안내 두 곳에 동시 노출
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `textarea-resize-comment` — L29 — CSS textarea{resize:vertical} 룰 직전 주석 — 2026-08-25 매니저 지적으로 이미 반영 완료된 변경(resize:vertical 적용)을 기술하는 이력 주석 — 해소된 사항이라 현재 실무 판단 근거로 기능하지 않음
- [stale-notice] `modal-wide-comment` — L41-43 — CSS .modal.wide 룰 직전 3줄 주석 — 480→680px 확대가 이미 적용 완료된 이력 주석 — 기술 결정(모바일 대응)은 max-width:680px 값 및 .ov padding:16px 코드 자체로 확인 가능
### D. 장황 단순화 (2건)
- [css-id] `lg_sub` — L104 — ovLogin 모달 내 <p> 요소 — id='lg_sub'가 JS 전체에서 getElementById('lg_sub')로 참조되지 않음 — id 속성만 불필요한 잉여 마크업
- [css-class] `--blue` — L11 — :root 변수 선언부 — 이 파일 내 어떤 CSS 룰·인라인 스타일에도 var(--blue) 참조 없음

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `serif` — CSS 전역 블록 — body{} 바로 다음, .wrap 이전 — HTML body 전체에 class="serif" 사용처 0건 — h1·.node-chro .nm·.sec-letter 등 모든 serif 폰트 요소는 element/하위 선택자로 직접 지정되어 있어 이 유틸리티 클래스가 쓰일 여지 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `EXEC_URL` — 첫 번째 <script>(정직 배지 IIFE) 3행 및 두 번째 <script>(자동화로그 IIFE) 3행 — 동일 문자열 2곳 — 동일 GAS /exec URL이 두 IIFE에 각각 리터럴 하드코딩 — URL 변경 시 두 곳 모두 수정 필요, 단일 변경점(SSOT) 부재
### C. 낡은 안내·버전 배지 (6건)
- [stale-notice] `pill-action-count` — header .header-meta 네 번째 pill — 헤더 배지는 '48종'이나 섹션 G 표 캡션은 '액션 전체 — 54종' — cal-* 4종·fix-emp-field·geo-distance·hr-schedule-feed 등 신설 이후 미갱신(6종 차이)
- [stale-notice] `pill-update-date` — header .header-meta 첫 번째 pill — 본문 최신 기록이 2026-08-26(@86 clasp 배포)임에도 갱신일이 2026-08-04로 약 7주 뒤처짐
- [stale-notice] `footer-update-date` — footer 두 번째 div — footer 갱신일도 2026-08-04로 동결 — 헤더 pill과 동일한 stale 날짜가 두 곳에 불일치 상태로 공존
- [stale-notice] `pill-db-count` — header .header-meta 세 번째 pill — 섹션 G 실제 표에 연차원장·보드명단·공휴일·개인일정 탭 4종이 추가(2026-07-28·08-25 신설)됐으나 pill 목록에 미반영 — 나열된 5탭 외 4탭 누락
- [stale-notice] `sec-g-db-heading` — 섹션 G — DB 표 바로 위 <h3> — '운영 탭 2종 + 관리자 전용 탭 3종'(합산 12) 기술이나 실제 표 비-DB 행은 9개(휴무·연차원장·보드명단·공휴일·자동화로그·업무평가·자기평가·리더십평가·개인일정) — 분류 수치가 현황과 불일치
- [stale-notice] `autolog-comment-pageRoot` — autologSection <div> 바로 위 HTML 주석 블록 — 참조된 #pageRoot ID가 문서 어디에도 존재하지 않으며, [변경 2026-07-05]·[스타일 2026-07-06] 이력 메모는 완료된 작업 — 구조를 오독하게 만드는 낡은 내부 주석

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
- ⚠️ 감사 실패: 조각 1/1: JSON 파싱 실패

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> 블록 — .m-values 관련 CSS 영역, 두 줄 — HTML 전체에 class="val-chips" 요소가 없음; m-values 섹션은 img·quote만 사용하며 별도 칩 목록 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (5건)
- [duplicate-text] `4대보험-복리후생-중복` — m-perk 카드 '4대보험 완비 / 국민연금·고용·산재·건강보험' vs m-list 복리후생 섹션 '4대보험 (국민연금·고용·산재·건강)' — 국민연금·고용·산재·건강보험 내용이 비주얼 perk 카드와 복리후생 목록 두 곳에 동일하게 반복
- [duplicate-text] `퇴직금-연차-중복` — m-perk 카드 '퇴직금 · 연차 제도' vs m-list 복리후생 '퇴직금 제도' + '연차 / 월차 제도' — 퇴직금·연차 내용이 perk 카드와 복리후생 목록 두 곳에 반복
- [duplicate-text] `직원할인-카페-중복` — m-perk-wide 'AI 업무 서포트' 카드 본문 말미 '· 직원할인(카페)' vs m-list 복리후생 '직원할인(카페)' — 직원할인(카페) 항목이 AI 서포트 카드 끝과 복리후생 목록에 중복
- [duplicate-text] `contact-phone-duplicate` — m-contact cbox '02-6261-1202 / 나우열 매니저' vs m-foot .contact 동일 정보 — 전화번호와 담당자명이 지원·문의 카드와 페이지 하단 푸터에 그대로 반복
- [duplicate-text] `경력3년-자격-우대-중복` — 자격요건 '수행·의전 경력 3년 이상 (경력직)' vs 우대사항 '3년 이상 수행·의전 경력자' — 동일한 3년 경력 기준이 자격 요건(필수)과 우대 사항(선호)에 동일 임계값으로 중복 기재
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `추가-스프린트-태그` — 첫 번째 <script> 블록 첫 줄 주석 — A-5·P2·G5·시안2 등 개발 스프린트 태그는 커밋 이후 추적 맥락이 없어 유지보수자에게 의미 없는 잡음
### D. 장황 단순화 (1건)
- [verbose-block] `values-diagram-comment` — <style> 블록 — .values-diagram 규칙 직전 4줄 CSS 주석 — 1·2차 실패 이력, 커밋 해시(42c3b999), 래스터라이즈 툴체인을 4줄로 기록 — ERP 운영자·유지보수자에게 불필요한 구현 고고학

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
### B. 중복 설명 병합 (4건)
- [duplicate-text] `지원서류 안내 중복` — Section 08 우대 사항·지원 서류 마지막 항목 ↔ .m-contact .apply-line — 이력서·자기소개서·자격증 사본 안내가 Section 08 목록과 문의 섹션 apply-line에 동일 내용으로 반복
- [duplicate-text] `연락처 중복` — .m-foot .contact ↔ .m-contact .cbox (이메일·전화 카드) — 02-6261-1202 / 나우열 매니저 연락처가 문의 카드(.m-contact)와 페이지 푸터(.m-foot)에 동일하게 반복
- [duplicate-text] `정착지원금 중복` — Section 04 .m-perk 첫 번째 카드 ↔ Section 01 .deal-foot — 月 100~130만원 정착지원금 수치·정책이 보상(01) 섹션과 혜택·복지(04) 섹션에 각각 서술되어 반복
- [duplicate-text] `파트너등급제 중복` — Section 04 .m-perk 두 번째 카드 ↔ Section 01 col-5 등급표 — 5단계 파트너 등급 경로가 Section 01 상세 표와 Section 04 혜택 카드에 중복 서술
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `시안 블록 주석` — <style> 최상단 주석 블록 (CSS 첫 주석) — 라이브 공개 파일에 '시안' 레이블 및 마이그레이션 이력(2026-08-25 A-2)이 잔존 — 완료된 이식 작업 설명으로 현행성 없음
- [stale-notice] `Hero 매니저 노트 주석` — .m-hero CSS 섹션 구분 주석 — 특정 날짜(2026-08-26)의 개발 지적 메모가 라이브 CSS에 잔존 — 단순 섹션 구분 주석으로 정리 가능
- [stale-notice] `2026.6 기준 위탁 강사 예외 안내` — Section 09 운영 안내 두 번째 항목 — '2026.6 기준' 시점 태그가 현재 기준 3개월 이상 경과 — 정책 지속 여부·날짜 유효성 재확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `m-perk-wide 유니폼 혼재` — Section 04 .m-perk-wide 내 <p> 태그 — '강습 유니폼 제공'이 AI 서포트 설명 문장 끝에 '·' 구분으로 혼재 — 별개 혜택 항목이 같은 p 태그에 이어 붙여져 가독성 저하

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — style 섹션 — .m-values .t-sub 바로 아래 — HTML body 전체에 class="val-chips" 참조 0회. 동일 역할의 .chips/.chip 패턴이 .m-tags 섹션에서 실제 사용되며 이 선언은 완전히 대체·방치됨.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (3건)
- [duplicate-text] `전화번호_나우열매니저` — .m-contact .cbox (☎ 문의 전화 박스) + .m-foot .contact div — '02-6261-1202'와 '나우열 매니저' 조합이 연락처 카드 섹션과 하단 푸터 두 곳에 동일하게 반복 표기.
- [duplicate-text] `영어회화_급여조정` — .m-salary .note 끝 문장 + .m-shift 우대사항 첫 번째 li — '영어 회화 가능자 → 급여 추가 조정' 내용이 연봉 카드 note와 우대사항 리스트 두 곳에 별도 서술로 중복.
- [duplicate-text] `유니폼제공` — .m-perk-wide p 끝 구절 '근무 유니폼 제공' + .m-tags .chip '유니폼 제공 등' — 유니폼 지급 복지가 AI 서포트 카드 문단 끝과 복지 칩 목록 두 곳에 중복 등장.
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `m-hero .badge.closed` — style 섹션 — .m-hero .badge 블록 바로 다음 줄 — JS closed-state 핸들러는 #mContact와 #topStatus에만 closed 클래스를 추가하며 #heroBadge(.m-hero .badge)에는 부여하지 않음. 이 규칙이 실제 적용되는 경로가 없음.
- [stale-notice] `values-diagram-comment` — style 섹션 — .values-diagram 선언 바로 위 블록 주석 — 1·2차 구현 실패 원인, git 커밋 해시(42c3b999), 외부 패키지명(node @resvg/resvg-js) 등 내부 이력이 프로덕션 CSS 주석으로 노출됨. git 로그·PR 설명에 속하는 정보.
- [css-id] `sloganQuote` — .m-values 카드 — quote div — id="sloganQuote"와 id="sloganText" 모두 이 파일 내 JS·CSS 선택자에서 참조 0회. 과거 JS 주도 슬로건 교체 기능의 잔존 ID 속성으로 추정.
### D. 장황 단순화 (2건)
- [verbose-block] `ladder-step-desc` — .m-ladder .ladder-row 내 ②~⑥ step span 텍스트 — '진급 2단계'~'진급 6단계' span 설명이 단계 번호의 단순 반복으로 정보 밀도 0. ①사원의 '연차가 아닌 성과로 평가'와 달리 읽을 가치가 없는 자리 채움.
- [verbose-block] `js-version-comments` — script 블록 1 상단 주석 '[추가 2026-07-16 A-5 P2·G5, 2026-07-18 시안2 전환 반영]'; script 블록 2·3 상단 주석 '[추가 2026-07-18 A-5]'(각 1회) — 세 script 블록 모두 내부 시안 번호·날짜가 포함된 changelog성 주석으로 시작. git 커밋 메시지에 속하는 변경 이력이 프로덕션 HTML 소스에 노출됨.

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — CSS <style> 블록 45–46번 줄, .m-values 정의 직후 — 페이지 전체 HTML 어디에도 class="val-chips" 요소가 없음 — 인재상 도식이 chip 목록에서 PNG img 단일 태그로 교체될 때 CSS만 잔류
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (4건)
- [duplicate-text] `정규직 수습 3개월` — ① 163줄 .badge('정규직(수습 3개월)'), ② 169줄 .note('정규직 · 수습 3개월'), ③ 226줄 근무조건 목록('정규직 (수습 3개월)') — 동일 고용형태 내용이 히어로 배지·급여카드 노트·근무조건 목록 세 곳에 반복 기재
- [duplicate-text] `4대보험 퇴직금 격주휴무` — ① 169줄 .note('4대보험 · 퇴직금 · 격주휴무 적용'), ② 235줄 .off('격주휴무'), ③ 254–255줄 복리후생 목록('4대보험 … 퇴직금', '격주휴무 · 연차') — 급여카드·근무 시프트 카드·복리후생 목록 세 곳에 같은 항목 중복 나열
- [duplicate-text] `이력서 사진 포함` — ① 257줄 복리후생 목록('이력서(사진 포함) · 자기소개서(선택)'), ② 284줄 .hint('이력서(사진 포함)와 자기소개서를 위 이메일로…') — 제출 서류 안내가 지원·문의 섹션과 복리후생 목록 두 곳에 중복
- [duplicate-text] `직원할인 카페` — ① 210줄 .m-perk-wide p('직원할인(카페) · 4대보험 적용'), ② 256줄 복리후생 목록('직원할인(카페) · 유니폼 제공') — AI 서포트 와이드 카드 서술과 복리후생 목록에 직원할인(카페) 항목 중복 나열
### C. 낡은 안내·버전 배지 (4건)
- [css-class] `badge closed` — CSS <style> 블록 31번 줄, .m-hero .badge 직후 — JS 마감 처리 로직(346–360줄)이 mContact·topStatus에만 .closed를 추가하고 #heroBadge에는 .closed를 추가하지 않으므로 이 선택자는 실행 중 절대 일치하지 않음
- [css-id] `heroBadge` — 163번 줄, .m-hero .badge 요소의 id 속성 — 3개 script 블록 어디에도 getElementById('heroBadge') 또는 querySelector('#heroBadge') 참조 없음 — 이전 버전 잔류 ID
- [css-id] `sloganQuote` — 187번 줄, .quote div의 id 속성 — JS 3개 블록 어디에도 이 ID 참조 없음 — 이전 슬로건 동적 교체 로직에서 쓰이다 제거된 잔류 ID로 추정
- [css-id] `sloganText` — 187번 줄, .s-line div의 id 속성 — JS 어디에도 이 ID 참조 없음 — sloganQuote와 함께 이전 동적 교체 로직 잔류 흔적
### D. 장황 단순화 (2건)
- [verbose-block] `values-diagram-comment` — CSS <style> 블록 50–53번 줄, .values-diagram 규칙 직전 4줄 주석 — 이전 실패 구현 2회 시도 경위와 커밋 해시를 CSS 파일에 직접 기재 — git 커밋 메시지에 있어야 할 개발 이력이 라이브 파일에 삽입돼 가독성 저해
- [verbose-block] `js-version-tags` — 329번 줄, 첫 번째 <script> 블록 첫 줄 (유사 패턴: 366줄, 412줄) — 스프린트 코드('[A-5 P2·G5]')·이터레이션 태그('[추가 2026-07-16]')가 소스 주석에 반복 삽입 — git log로 대체 가능한 장황한 변경 이력 노트

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `val-chips` — <style> 55-56행 — .m-values 블록 내 — HTML 본문 전체에서 val-chips 속성을 가진 요소가 없음. 실제 사용 클래스는 .chips(287행 div, 102-103행 CSS). val-chips 두 규칙은 어떤 요소에도 적용되지 않음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `badge.closed` — <style> 36행 — .m-hero .badge 규칙 바로 다음 — JS 마감 로직(1번 script)은 #mContact와 #topStatus에만 closed 클래스를 추가하며, 히어로 배지(#heroBadge .badge)에 closed를 부여하는 코드가 3개 script 블록 어디에도 없어 이 CSS 규칙이 절대 적용되지 않음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 1) 307-308행 m-contact .cbox (02-6261-1202 · 나우열 매니저) 2) 319행 m-foot .contact div — 전화번호 '02-6261-1202'와 담당자명 '나우열 매니저'가 지원·문의 카드와 페이지 푸터에 동일하게 두 번 노출됨
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 1) 237행 m-perk-wide > p 말미 '유니폼 제공(근무 유니폼 회사 지급)' 2) 294행 m-tags .chip '유니폼 제공 등' — 유니폼 지급 복지가 AI 서포트 복지 카드 본문과 스킬·복지 태그 두 곳에 중복 기재됨
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 122행 — .jpg-dl-btn 규칙 직전 — '2026-07-18 A-5·시안2' 날짜·버전 배지와 과거 시안 전환 맥락이 남아 현 독자에게 무의미한 내부 이력 메타
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 142행 — .apply-open-btn 규칙 직전 — '2026-07-18 A-5' 버전 배지가 CSS 섹션 구분 주석에 내부 이력 메타로 남아 있음
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 2번째 <script> 블록 393행 최상단 — '[추가 2026-07-18 A-5]' 날짜·버전 배지가 JS 블록 주석에 내부 이력 메타로 남아 있음
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 3번째 <script> 블록 439행 최상단 — '[추가 2026-07-18 A-5]' 버전 배지가 동일하게 JS 블록 주석에 내부 이력 메타로 남음
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 60-63행 — .values-diagram 규칙 직전 4줄 블록 주석 — 구현 실패 이력 3단계·커밋 해시(42c3b999)·NPM 패키지명까지 4줄로 서술한 개발 이력 주석. 유지보수 가독성을 해치며 1줄 요약으로 대체 가능

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `big-line` — <style> 블록, .hero-sub 규칙 직후 — HTML 본문·JS 렌더 출력 어디에도 class="big-line" 사용처 없음 — 이전 슬라이드 레이아웃 잔재
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `cols` — <style> 블록, .kicker .k-sub 규칙 직후 — HTML 본문·JS 렌더 어디에도 class="cols" 사용처 없음. @media print 내 .cols{gap:16px;} 및 .doc-head,.kicker,.cols{page-break-inside:avoid;} 의 .cols 셀렉터도 수동 정리 필요
  - 게이트: 소비자 832건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] `esc` — 두 번째 <script> 블록(기간 셀렉터 IIFE) 최상단 — 첫 번째 IIFE와 동일 본문 2회 선언 — 두 IIFE 모두에 함수 본문이 완전 동일한 esc() 선언 — 공유 스코프로 추출 시 1개만 유지 가능
- [duplicate-text] `fmtWon` — 두 번째 <script> 블록(기간 셀렉터 IIFE) 최상단 — 첫 번째 IIFE와 동일 본문 2회 선언 — 두 IIFE 모두에 함수 본문이 완전 동일한 fmtWon() 선언 — 공유 스코프로 추출 시 1개만 유지 가능
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `zoom_0.7_comment` — HTML 최상단 <!-- --> 주석 블록 두 번째 줄 — 실제 CSS zoom 값은 0.74(2026-07-07 실측 정정) — 상단 주석만 0.7로 남아 시제 불일치. 해당 줄 '0.7' → '0.74' 수정 필요
- [stale-notice] `이전_gviz_폐기_주석` — HTML 최상단 <!-- --> 주석 블록, 강습팀 매출 항목 두 번째 줄 — 이미 해소된 구버전 오류 안내 — 강습팀은 GAS team_sales_h1로 전환 완료. 단 SALES_GVIZ가 운영부 베이스맵 용도로 JS 내 여전히 활성(readGvizDeptMap 호출)이라 '폐기' 표현이 독자에게 오해 유발
### D. 장황 단순화 (1건)
- [verbose-block] `상단_html_주석_개발이력` — HTML 최상단 <!-- --> 주석 블록 전체(약 16줄) — GM 요청 날짜·정정 이력·기능 추가 날짜 등 커밋 로그로 충분한 개발 이력이 HTML 본문에 인라인 혼재 — 데이터소스·아키텍처 배선 기술만 남기고 날짜·이력 문구는 커밋 메시지로 이관 권장

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `hint` — line 18, <style> 블록 마지막 룰 — `.hint` 클래스가 `<style>`에 정의되어 있으나 `<body>` 내 어떤 요소에도 `class="hint"`가 존재하지 않아 참조 횟수 0인 죽은 CSS 룰셋.
  - 게이트: 소비자 1118건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
- (정리 후보 없음)

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
- (정리 후보 없음)

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] `wp-typography.css` — <head> 최하단 — 인라인 <style> 블록 직후 — 즉시 리다이렉트 스텁(content="0")이라 사용자가 렌더된 화면을 볼 시간이 없고, 마크업 내 typography 클래스를 참조하는 요소가 단 하나도 없음; body·a 스타일은 인라인 <style>이 이미 완전히 커버
  - 게이트: 소비자 105건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
