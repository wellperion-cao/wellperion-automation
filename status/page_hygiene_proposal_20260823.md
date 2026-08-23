# 주간 페이지 위생 정리안 — 20260823 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: 전체

## 시설부 체계 — `3. 웰페리온 가이드/coo/check/시설부 체계.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] `fcRenderChips` — fcTimerState 함수 직전 / 회차 칩 폐지 선언 블록 — 개발자가 '폐지 — no-op'으로 명시한 3개 함수(fcRenderChips·fcUpdateChips·fcChipGo). 함수 바디 전체가 주석뿐이며 이 조각 내 호출부 0. 회차 통합(2026-07-08) 이후 실행 경로 없음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] `fmEsc` — 월간보고 탭 script 블록 최상단 (FM_DEPT 선언 직후) — fmEsc와 mpEsc가 동일 페이지 내에 바이트 단위 동일한 HTML 이스케이프 로직을 각자 정의. IIFE 내부 escapeHTML(조각 1)까지 합산 시 3중 중복 가능.
- [duplicate-text] `mpEsc` — 이달 부서 현황 탭 script 블록 최상단 (MP_DEPT 선언 직후) — fmEsc와 완전히 동일한 구현. 같은 파일 내 두 번째 정의.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `fcRoundChange` — setInspector 함수 직후 — 주석이 '(구)·select 폐지·호출부 없음'으로 스스로 낡은 코드임을 선언하지만, window 노출 + 실 기능 바디(captureRound 등) 존재로 조각 1 HTML의 인라인 onclick 잔존 가능성을 배제할 수 없어 stale-notice로 분류.
### D. 장황 단순화 (1건)
- [verbose-block] `fcWorkDelta` — fcBuildSubmission 함수 직후 / fcWorkDelta 함수 선두 주석 4줄 — 함수 동작(seen 집합으로 신규 줄만 필터)이 코드 자체로 명확한데, 4줄 설계 배경·타 파이썬 파일 참조 주석이 붙어 실무 가독성을 저해. PR 기록 수준의 내용.

## 지원부 체계 — `3. 웰페리온 가이드/coo/check/지원부 체계.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [js-function] `parseCSVLine` — JS 스태프 로드 함수 그룹 내 parseCSVLine 정의 — loadStaffFromSheet가 '시트 동적로드 비활성화' 주석 후 FALLBACK 고정으로 전환 — CSV fetch 경로 자체가 제거돼 이 파서의 호출부가 전무
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `STAFF_CSV_URL` — JS 상수 선언부 — loadStaffFromSheet 내 CSV fetch가 비활성화된 이후 이 URL을 참조하는 코드가 전무
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] `둘째주_휴관작업_목록` — #a3-closedday-print 인쇄 컨테이너 + #tab-manual > .manual-section(🗓 둘째주 휴관 작업) — A·B·C·E 구역 둘째주 휴관 작업 체크리스트가 인쇄 전용 컨테이너와 매뉴얼 탭 화면 섹션 두 곳에 동일 항목으로 이중 존재
- [duplicate-text] `dashEsc` — dashEsc(대시보드) / mrEsc(월간보고) / mpEsc(월간계획) / escapeHTML(공통) 각 정의부 — HTML 특수문자 이스케이프 함수 4개가 같은 파일에 중복 선언 — null 처리 방식과 quot 이스케이프 포함 여부만 미미하게 다르고 목적은 동일
### C. 낡은 안내·버전 배지 (7건)
- [stale-notice] `a3-monthly-print` — #a3-monthly-print 인쇄 컨테이너 본문 전체(mrp-main-title·mrp-footer 포함) — '지원부 점검 체계 — 2026년 6월 작업 요약', '본 요약은 2026-06-30 기준' 정적 텍스트가 하드코딩 — 현재 2026-08-23 기준 2개월 경과, 다른 A3 컨테이너와 달리 JS 동적 주입 주석 없이 그대로 인쇄됨
- [stale-notice] `swim-team-schedule` — #tab-guide 파트너팀(수영팀) 대청소 일정 표 행 2·3·5 — 행2 '7월 한 달간(매일 새벽 5:30) 진행중', 행3 '7/10·7/24 예정', 행5 '7/23·7/24 예정' — 7월 일정이 현재(2026-08-23) 시점에 이미 경과했으나 상태 배지가 갱신되지 않음
- [stale-notice] `autoSyncSeedsIfChanged` — autoSyncSeedsIfChanged 함수 전체 — 2026-06-27 폐지 선언 — 첫 줄 return; 이후 try-catch 전체가 JS 엔진이 절대 도달하지 못하는 unreachable dead code; 이 chunk 내 별도 호출부 없음
- [stale-notice] `quickAddBarHtml` — quickAddBarHtml 함수 정의부 및 연관 quickAddOpen·quickAddSave — GM 2026-06-12 기능 제거 — 본문이 return '' 고정이므로 버튼 DOM을 생성하지 않고, onclick 기반인 quickAddOpen·quickAddSave도 진입 경로가 사실상 없음
- [stale-notice] `setupAttr` — setupAttr 함수 정의부 (quickAddBarHtml 보존 주석 직후) — 보존 근거 주석('quickAddBarHtml이 공유하므로 보존')이 무효 — quickAddBarHtml이 return '' 스텁이 된 이후 이 chunk 내 setupAttr 호출부 없음
- [stale-notice] `_relocateDayItems` — _relocateDayItems 함수 정의부 — getSched 오버라이드 내 2026-06-29 명시 제거(F1 잔재 주석) — 요일 필터는 applyBaseOverrides/_itemOnDay로 대체됐으며 이 chunk 내 호출부 없음
- [stale-notice] `STAFF_SEED` — STAFF_SEED 배열 첫 번째 항목 note 필드 — 오늘(2026-08-23) 기준 '6월말 퇴직 예정'은 이미 약 2개월 경과 — 저장 이력 없는 기기에서 시드 재주입 시 오래된 인사 정보 노출
### D. 장황 단순화 (1건)
- [verbose-block] `cell` — renderCsTable 함수 및 renderStaffTable 함수 각 상단 — 동일한 인라인 CSS 문자열이 renderCsTable·renderStaffTable 양쪽에 각각 하드코딩 복제됨 — 상위 const 변수나 CSS 클래스 하나로 추출 가능

## 운영부 체계 — `3. 웰페리온 가이드/coo/check/운영부 체계.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 주차관리부 체계 — `3. 웰페리온 가이드/coo/check/주차관리부 체계.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 파트너팀 체계 — `3. 웰페리온 가이드/coo/check/파트너팀 체계.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 전사_일정 — `3. 웰페리온 가이드/coo/check/전사_일정.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 업무 현황 SSOT — `3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 결재 현황 SSOT — `3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 공지 템플릿 — `3. 웰페리온 가이드/coo/notice/notice_template.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [dead-markup] `noticeImages` — JS 두 번째 <script> 블록, NOTICE_PRESETS 객체 정의 직후 / el() 함수 선언 바로 위 — 선언만 있고 push·read·전달 없음; v2.36에서 이미지 삽입이 contenteditable 직접 삽입으로 교체되면서 배열 자체가 폐기됨
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `ntool-img-thumb` — CSS <style> 블록, .ntool-pv-ftr 섹션과 .ntool-saved 섹션 사이 썸네일 주석 섹션 전체 — ntAddImages()는 img를 contenteditable에 직접 삽입하므로 .ntool-img-thumb·.ntool-img-item 요소를 생성하는 정적 HTML 및 JS가 파일 전체에 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `ntool-fmt-bar-sep` — CSS <style> 블록, /* fmt-bar — v2.27 그룹 박스화 + 호버 효과 */ 주석 섹션 내 .ntool-fmt-bar button:active 규칙 직후 — .ntool-fmt-bar 내 class='sep' 요소가 정적 HTML에도 JS 생성 코드에도 없음; fmt-group 방식 전환 후 고아 규칙
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] `ntFmtBoldLine-폐기-주석` — JS 두 번째 <script>, ntFmtStrike 정의 직후 / ntUpdatePreview 함수 직전 — 삭제된 함수 ntFmtBoldLine에 대한 폐기 주석만 남아 있고 함수 본체가 파일 어디에도 없음
- [stale-notice] `마크다운-파서-폐기-주석` — JS 두 번째 <script>, ntFmtBoldLine 폐기 주석 아래 빈 줄 이후 / ntUpdatePreview 함수 직전 — 파서 본체가 이미 제거된 상태에서 '폐기됨'을 알리는 주석만 잔존; 바로 뒤에 본문이 없고 빈 줄만 이어짐
- [stale-notice] `title-version-v2.1` — <head> title 요소 — JS 내부 버전 주석이 v2.65까지 진행됐으나 title은 v2.1 표기; topbar h1의 v2.2와도 불일치
- [stale-notice] `h1-version-v2.2` — .topbar .left h1 요소 — v2.2 표기이나 코드는 v2.65 이상 기능 포함(ntPaper·ntOrient·ntVerifySaved 등); title의 v2.1과도 불일치
### D. 장황 단순화 (2건)
- [verbose-block] `BRANDS-pantone-wm` — JS 두 번째 <script>, BRANDS.main 항목 (9개 브랜드 항목 모두 동일 패턴) — BRANDS[*].pantone · BRANDS[*].wm 는 ntUpdatePreview·ntBuildPageHtml·ntCollectData 어디에서도 참조되지 않는 미사용 메타데이터 필드
- [verbose-block] `CSS-버전-히스토리-주석` — CSS <style> 블록, .cat-card 규칙 직전 (동일 패턴 주석이 .ntool-subtitle-input·.ntool-editor·.ntool-pv-subtitle 등 전반에 산재) — 날짜·GM 지시 기록 등 운영 이력성 주석이 CSS 전반에 산재해 선택자 파악을 저해; 버전 이력은 git 커밋으로 관리하는 것이 적합

## 메인가이드 O1(운영통합체계) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] `deptCard` — O1 인라인 <script> · loadHub() IIFE 내부 · moduleCard 정의 직후 — IIFE 내부 선언으로 외부 참조 불가. render() 등 IIFE 내 어디서도 호출되지 않음. 주석의 '다른 호출부'는 IIFE 구조상 존재할 수 없어 실질 호출부 0. badge 파라미터도 함수 본문에서 미사용
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `front_card` — O1 인라인 <script> 최상단 · var CHECK_API 선언부 직전 두 번째 줄 — front_card 스키마가 '예약' 상태로 명시된 채 구현 여부 불명. 스크립트는 hardcoded moduleCard() 9개 호출로 완전히 동작하여 이 주석이 가리키는 후속 전환과 무관한 상태로 방치됨
### D. 장황 단순화 (1건)
- [verbose-block] `부서별체계삭제주석` — O1 article · 종합접수처 처리 절차 div 아래 — 이미 실행 완료된 섹션 삭제 결정을 3줄 HTML 주석으로 보존. 변경 이력은 git log가 담당하며 페이지 내 삭제 설명은 실무 가독성에 기여하지 않음

## 메인가이드 O2(공지) — `3. 웰페리온 가이드/wellperion_guide(main).html`
- ⚠️ 감사 실패: 조각 2/4: 타임아웃(300s)

## 메인가이드 O3(재등록) — `3. 웰페리온 가이드/wellperion_guide(main).html`
- ⚠️ 감사 실패: 조각 2/4: 타임아웃(300s)

## 메인가이드 O4 — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [dead-markup] `탭 4: MCP→CLI 전환` — O4 탭 패널 컨테이너 — data-panel="token-adv" 패널 직후 — 탭 주석만 있고 대응하는 tab-panel div가 없음; 렌더 결과가 전혀 없는 빈 플레이스홀더 주석
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `탭 7: 핵심 프롬프트` — O4 탭 패널 컨테이너 — data-panel="selflearn" 패널 직후, 최외곽 </div> 직전 — 탭 주석만 있고 대응하는 tab-panel div가 없음; article 종료 직전에 panel 없이 주석만 남아 있는 죽은 플레이스홀더
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `v1.0 현재` — O4 > selflearn 탭 > 고도화 진화 로드맵 ul 첫 번째 항목 — 같은 탭 callout에서 ai_education_auto_learner.py(v2.0의 자동 수집·요약·텔레그램 보고)가 이미 가동 중임을 명시하므로 'v1.0 (현재)=수동' 레이블이 실제 운영 상태와 불일치

## 문의회원 — `3. 웰페리온 가이드/cpo/member/membership.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] `iSportMgmt` — gvizLessonRows_ 함수 — 헤더 인덱스 선언 블록 — 선언 후 함수 내 out.push({...}) 어디에도 row[iSportMgmt]·iSportMgmt 참조 없는 죽은 지역변수. 인근 주석이 '신모델은 JSON 종목별관리 칸을 안 쓰고 Contact 태그를 정본으로 함(2026-07-22)'이라 명시함.
  - 게이트: 소비자 7건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (6건)
- [stale-notice] `_gzLessonSportMgmtParse_` — _gzContactsBySport_ 함수 직전 정의 — gvizLessonRows_ 주석 '신모델은 JSON 종목별관리 칸을 안 쓰고 Contact 태그를 정본으로 함(2026-07-22 디버그)'에 따라 이 파서의 사용 목적이 폐기됐으며 이 조각 내 호출부 0. 조각 3·4 확인 불가로 A 대신 C 처리.
- [stale-notice] `_lessonValidOwners` — _lessonTeamLeadOf 와 _lessonRosterFor 함수 사이 주석 블록 — 삭제 완료된 함수의 삭제 이유를 설명하는 잔류 주석. 함수 본체는 이 조각에 없으므로 주석만 낡은 변경 이력으로 남아 오인을 유발.
- [stale-notice] `ownerAssignHook` — switchTab 함수 — registered 탭 로드 블록 아래 — 이미 제거된 훅을 설명하는 역사적 주석. 현재 switchTab 본문에 ownerAssign 관련 실행 코드가 없고 이 주석만 잔류.
- [stale-notice] `manageFamilyLabel` — switchFamily 함수 — titleEl 참조 직전 — #manageFamilyLabel 삭제는 이미 완료된 작업. 완료된 삭제 이유를 설명하는 주석이 낡은 안내로 잔류.
- [stale-notice] `beginnerBanner` — showToast 함수 직후 · esc 함수 직전 주석 블록 — 삭제된 배너 기능을 설명하는 주석만 남아 있음 — 이 파편 전체에 #beginnerBanner·dismissBeginnerBanner 참조가 하나도 없고 주석 자체가 '아무 코드가 읽지 않아 무해'라고 명시
- [stale-notice] `openChurnReasonModal` — _tapOpenChurnReason 함수 직전 주석 2번째 줄 — 전환이 이미 구현 완료된 상태라 '더 이상 열지 않는다'는 확인 문장만 남음 — 함수 본문이 openUnregReasonModal 호출만 하고 있어 주석 없이도 의도가 자명
### D. 장황 단순화 (3건)
- [verbose-block] `_lessonSportMgmt` — _lessonSportMgmt 함수 내 '★타팀 오염 제거 폐기(2026-07-27 시포 · 실무진 피드백 FB260727-102835)' 주석 시작부터 '→ 이제 화면은 시트 값을 그대로 보여준다.' 까지 약 30줄 주석 블록 — 실측 건수·이전 구현 역사·고민 과정을 약 30줄 서술. '화면은 시트 값 그대로 표시' 한 줄로 충분한 의사결정 WHY를 역사 서술로 장황하게 늘여 실무 가독성 저해.
- [verbose-block] `_activateCellMemo` — _activateCellText 아래 · _activateCellSelect 위 — buildDbRow에서 memo 칼럼 td를 렌더하지 않아 이 파편 내 호출부가 없음 — memo는 buildNewInputRow(신규 행 form)에서 단순 input으로만 처리되고 _activateCellMemo를 거치지 않음
- [verbose-block] `_comboDateTime` — _activateCellSchedule 아래 · buildScheduleEditBlock 위 — 이 파편 전체에서 _comboDateTime 호출 위치가 없음 — 인접한 _resCollect·_ctCollect·buildScheduleEditBlock·saveReconModal 어디에도 미사용

## 강습회원관리 — `3. 웰페리온 가이드/cpo/member/강습회원관리.html`
### D. 장황 단순화 (1건)
- [verbose-block] `meta-refresh` — 6번째 줄 (<head> 내) — 바로 아래 7번째 줄 JS location.replace()가 hash까지 포함해 더 완전하게 리다이렉트하므로 meta-refresh는 JS 환경(내부 ERP 전제)에서 실질적 fallback 가치 없이 중복됨; JS 버전이 우선 실행돼 meta-refresh가 발동될 경우가 없음

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] `stat-label` — About 섹션 about-stats 세 번째 stat (.stat-num:100% / .stat-label:사전 예약제) vs. Membership section-desc 첫 문장 — 「100% 사전 예약제」가 About 통계 카드와 멤버십 섹션 설명 첫 문장에 동일한 사실로 반복 명시됨
- [duplicate-text] `membership-cta-sub` — #membership section-desc (두 번째 문장) vs. membership-cta-box 내 membership-cta-sub (동일 섹션 내 수행부) — 「투어 방문 후 상담을 통해 맞춤 멤버십을 안내해 드립니다」(section-desc)와 「시설 투어와 1:1 상담을 통해 맞춤 멤버십을 안내해 드립니다」(CTA sub)가 동일 섹션 내에서 사실상 같은 메시지 반복
### D. 장황 단순화 (1건)
- [verbose-block] `about-visual` — About 섹션 about-inner 좌측 열 (첫 번째 grid 자식) — height:500px 블록에 color:rgba(183,159,138,0.15) — 불투명도 15% 글자 「W」만 존재; 실제 사진·영상 없는 미완성 플레이스홀더가 공개 홈페이지에 대형 빈 공간으로 노출됨

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `buildM5Map` — JS buildM5Map 함수 선언 직전 구분선 주석 — 주석·함수명·내부 변수(m5Map, m5Status)가 'M5'를 사용하나 UI 배지('M3 검수대기')·오류 문구('M3 검수 상태 불러오기 실패')·표 내 표기('M3 반영')는 모두 'M3' — 단계명 변경 후 주석·함수명이 갱신되지 않음
- [stale-notice] `M5 상태 우선` — JS resolveBadge 함수 상단 첫 번째 주석 — 주석이 'M5 상태 우선'이라 적혀 있으나 UI 전체는 'M3'로 통일 — buildM5Map과 동일한 단계명 불일치
- [stale-notice] `더 진행된` — JS buildM5Map else 분기 주석 — 첫 번째 주석 '덮어씌우지 않음'이 실제 코드 및 두 번째 주석 '발행완료가 있으면 우선(덮어씌움)'과 모순 — 이전 로직 설명을 삭제하지 않고 그대로 남겨 실제 동작을 오기술함

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `wlp-inq .hero-band` — 두 번째 <style> 블록, /* 기둥 기준 */ 주석 바로 아래 .back-kiosk 선언 직전 — 첫 번째 .wlp-inq .hero-band 규칙({background:var(--bg);max-width:720px;...;position:relative})에 이미 position:relative가 포함돼 있어 이 독립 선언은 계산 스타일을 전혀 변경하지 않는 완전 무효 규칙임
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `여름방학특강숨김안내` — <script> wpToSurvey 블록 내부 세 번째 주석 줄 — 동일 정보(숨김 경위·복원 방법)가 HTML 마크업 주석 '<!-- 여름방학 특강 카드 — 숨김(2026-08-07 GM 지시, 삭제 아님). 시즌 특강 재개 시 이 주석을 해제하고...'에 이미 더 완전하게 기재돼 있어 JS 주석 줄이 중복
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `6버튼` — <script> wpToSurvey 블록 내부 두 번째 주석 줄 — 여름방학 특강 카드가 2026-08-07 숨김 처리되어 wpToSurvey를 실제로 호출하는 버튼은 현재 5개뿐인데 주석이 '6버튼'이라 표기하고 버튼 목록에도 여름방학 특강 없이 6개를 나열해 현황과 불일치
### D. 장황 단순화 (1건)
- [verbose-block] `UTM귀속프리필HTML주석` — <script> wpToSurvey 블록 직전 HTML 주석 — 바로 아래 <script> 내부 첫 줄 JS 주석('// ── 자체 Survey(WP /ko/inquiry-form/) 이동 시 현재 페이지 UTM 승계 → 폼이 채널귀속 유지 ──')이 같은 내용을 이미 요약하므로 바깥 HTML 주석은 장황한 중복 설명

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 파일 최상단 HTML 주석 블록 전체 (<!-- Wellperion English Inquiry Block … -->) — 구현 완료된 GM 지시 7회분 의사결정 이력·픽셀 측정값·타 페이지 비교를 70여 줄 주석으로 적재. 이미 git 커밋 메시지에 보관된 내용이며 실제 HTML 도달 전 독자 피로를 유발. 5줄 이하 파일 메타 요약으로 압축 가능.
- [css-class] `wp-inq-video` — 인트로 동영상 래퍼 div (<div class="wp-inq-video" style="width:100%;…">) — <style> 블록 내 .wp-inq-video 룰이 전혀 없고 모든 스타일이 인라인으로 처리됨. 파일 헤더 주석에서도 'Inline styles only' 방침을 명시. 단, wp-typography.css 내 참조 가능성이 남아 A 제외 D로 분류.

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — (1) 전송 대상 카드 info-box vs (2) 사용 조건 아코디언 3번째 li — "방 이름 = 카톡 채팅방 창 제목과 정확 일치" 요건이 info-box("정확히 일치해야 전송됩니다")와 사용 조건 accordion li("완전히 동일한 글자여야 합니다")에 거의 동일 내용으로 이중 노출.
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `addRoom` — script > addRoom() 함수 본체 — fetch 호출 직전 블록 주석 — 2026-08-14 버그 수정 이력 서술. 픽스가 이미 코드에 반영됐으므로 '전에는…했다' 시제의 경고문이 현재 코드 기준으로 stale.
- [stale-notice] `deleteRoom` — script > deleteRoom() 함수 본체 — fetch 호출 직전 인라인 주석 — addRoom과 동일 이력 주석. addRoom 주석이 제거되면 '저장과 같은 이유로'라는 역참조 자체가 허공 참조가 됨.
### D. 장황 단순화 (2건)
- [verbose-block] `feedback_page_layout_left_full_width` — style 블록 > .content 룰셋 직전 주석 — 내부 패턴 식별자 태그가 CSS 룰셋 자체로 이미 명확한 내용을 별도 주석으로 부연. 실무 독자 가독성 기여 없음.
- [verbose-block] `feedback_input_no_rerender_ime` — style 블록 > .add-row input 룰셋 직전 주석 — IME-safe 설계 의도를 나타내는 내부 태그 주석. 패턴 코드명이 붙어 장황해진 메타 주석으로 단순화 또는 제거 후보.

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `header-right` — CSS 36행 — .header-meta 아래 .header-right 룰셋 — HTML 전체에 class="header-right" 참조 없음; 동일 컨테이너 역할을 .header-btns(211행)가 수행
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 미수금 탭 > 미수금 및 정산 대기 현황 섹션 392~394행, info-banner 직후 placeholder — 바로 위 info-banner(382~390행)가 동일 결론(소스 미배관)을 이미 더 상세히 전달; 이 placeholder는 같은 섹션에서 즉시 반복
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `asOf` — 헤더 .header-meta 내 209행, asOf span 초기값 — JS loadData 성공 시 rm.asOf로 교체(664행)되므로 'v1.0' 배지는 연동 실패 상태에서만 사용자에게 노출됨; 페이지가 지속 업데이트된 상태에서 v1.0은 의미없는 stale 버전 표기
### D. 장황 단순화 (2건)
- [verbose-block] `nsNote` — 채널별 분해 탭 > 북극성 KPI 연결 > nsNote div 348행 — 게이지·막대 차트 색상이 이미 시각적으로 범례를 전달; 색상 의미를 텍스트로 재설명하는 것은 실무 가독성을 낮추는 장황
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 미수금 탭 > 미수금 OCF 영향 분석 섹션 401행, 첫 번째 p 태그 — 재무 실무진 대상 페이지에서 미수금·OCF 기초 회계 정의 재설명은 불필요; 데이터 소스 미배관 상태에서 더욱 장황

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] `getFilteredItems` — JS — applyFilter() 본문 / getFilteredItems() 전체 — month·cat·approval 3중 필터를 allExpenses에 적용하는 동일 로직이 두 함수에 중복 구현됨
- [duplicate-text] `byCat` — JS — renderDashboard() 내 byCat 블록 / showShareModal() 내 byCat 블록 — 카테고리별 금액 집계(forEach → byCat 누적) 로직이 renderDashboard와 showShareModal 두 곳에 동일하게 존재
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — JS 설정 섹션 — const API_URL 선언 직전 주석 — API_URL에 이미 실 GAS 배포 주소가 설정돼 있어 '배포 후 교체' 지시문이 더 이상 유효하지 않음
- [stale-notice] `--purple` — :root CSS 변수 선언부 (style 블록 상단) — 이 파일의 CSS 규칙 및 JS 어디서도 참조되지 않는 색상 변수 9개(--green-bg, --red-bg, --yellow, --yellow-bg, --blue, --blue-bg, --purple, --purple-bg, --orange-bg)가 선언만 된 채로 존재
### D. 장황 단순화 (1건)
- [verbose-block] `filterCategory` — HTML filter-bar — id=filterCategory select 요소 — 카테고리 옵션을 동적으로 채우는 코드가 없어 '전체 카테고리' 단일 옵션만 노출되며 필터 효과 없음

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
- ⚠️ 감사 실패: 조각 1/2: 타임아웃(300s); 조각 2/2: 타임아웃(300s)

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `cm-msg.ok` — CSS <style> 블록, .cm-msg.err 룰 바로 아래 — submitCheck() 성공 경로는 closeOv() + reloadRows() 호출로 끝나며, cm_msg 요소에 'cm-msg ok' className을 할당하는 JS 코드가 전혀 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `renderModeSelect` — JS 스크립트, renderModeSelect() 함수 정의 직전 — 2026-07-04 r2 마이그레이션 시점의 안전 확인 메모 — 현재(2026-08-23) 기능이 안정 통합되어 '기존 무변경' 메모는 시제 오류이자 불필요 이력
- [css-id] `lg_sub` — 로그인 모달 내 <p class="sub" id="lg_sub"> 요소, PIN 게이트 오버레이 안 — JS 전체에서 getElementById('lg_sub') 참조가 0건 — 동적 텍스트 변경 의도로 추가된 것으로 추정되나 미구현 채 잔존
- [css-class] `--amber` — :root 변수 블록, --green·--red 선언 바로 뒤 같은 줄 — 이 파일 내에서 var(--amber) 및 var(--blue) 참조가 전혀 없음; 삭제 전 wp-typography.css에서 해당 변수를 사용하는지 확인 필요

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] `hero-cta-callout` — line 151 (.hero > p) / line 245 (.cta-inner > p 두 번째 문장) — '부서 채용 공고를 확인하라'는 동일 행동 유도 메시지가 페이지 상단 hero와 하단 CTA 블록에 중복 표기
- [duplicate-text] `about-lead-stats-overlap` — line 159 (.about-lead 단락) / lines 161-164 (.about-stats 카드 4장) — about-lead 산문이 언급한 '한남동·9년·스포츠+스파+커뮤니티+공간' 수치를 바로 아래 about-stats 4개 카드가 동일하게 재표시
### D. 장황 단순화 (2건)
- [verbose-block] `perkcard-premium-p` — line 192 (.perkcard '프리미엄 환경' > p) — '한남동'(line 161 stat)과 '3,000평'(line 163 stat)은 상단 about-stats에서 이미 노출; 두 번째 문장은 새 정보 없는 수사적 장식
- [verbose-block] `cta-inner` — lines 242-247 (.cta 블록 전체, dept 그리드~footer 사이) — hero h1 슬로건('기준을 만드는 사람들')·about-lead 문구('하루의 완성도')·hero p 안내('채용 공고 확인')를 모두 반복; 부서 그리드 링크 버튼이 이미 직접 행동 유도 수행

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> 블록 — .m-values 그룹 하단 / values-diagram 주석 바로 위 — 페이지 전체 마크업에 class="val-chips" 요소가 0개 — .m-values 카드 내 chip 열 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (3건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk 카드(4대보험 완비 / 퇴직금·연차 제도) vs .m-list 복리후생 목록 — 4대보험·퇴직금·연차 항목이 bento 상단 perk 시각 카드와 하단 복리후생 텍스트 목록에 동시 기재
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-list 자격요건 카드 vs .m-list 우대사항·지원서류 카드 — '수행·의전 경력 3년 이상' 내용이 자격요건(경력직)과 우대사항 두 곳에 표현만 달리해 중복 기재
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-contact .cbox(☎ 02-6261-1202 / 나우열 매니저) vs .m-foot .contact — 전화번호 02-6261-1202 · 나우열 매니저 문구가 지원·문의 섹션과 푸터에 동시 노출
### D. 장황 단순화 (4건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 — .values-diagram 룰셋 바로 위 4행 CSS 주석 — 실패 시도 이력·커밋 해시(42c3b999)·외부 라이브러리명 등 구현 히스토리를 4행 나열 — 'PNG 고정(html2canvas 호환)' 한 줄로 압축 가능
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> IIFE 최상단 주석 1행 — 버전 태그 [A-5 P2·G5, 시안2] 및 작업일이 코드 주석에 노출 — 폴백 설명은 유효하나 태그·날짜는 유지보수 독자에게 noise
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 두 번째 <script> downloadPageAsJpg 함수 선언 위 주석 1행 — 버전 태그 [추가 2026-07-18 A-5] 포함 — 지연로드 설명 자체는 유효하나 태그·날짜는 noise
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 세 번째 <script> openApplyModal 함수 선언 위 주석 1행 — 버전 태그 [추가 2026-07-18 A-5] 포함 — 액션명·스팸 처리 설명은 유효하나 태그·날짜는 noise

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `m-hero .badge.closed` — <style> 블록, .m-hero .badge 룰셋 바로 아래 — 이 페이지의 JS 3개 블록은 .closed를 #topStatus와 #mContact에만 추가하며, .m-hero 내 #heroBadge에 .closed를 부여하는 코드가 전혀 없다.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (4건)
- [duplicate-text] `contact-phone-manager-duplicate` — .m-foot .contact div (페이지 최하단 푸터) — .m-contact contact-grid2 내 cbox에 '02-6261-1202'와 '나우열 매니저'가 이미 표시되어 있으며, 푸터에 동일 정보가 재반복된다.
- [duplicate-text] `이력서-제출안내-duplicate` — .m-list '우대 사항·지원 서류' 섹션 마지막 li — .m-contact .hint에도 '이력서(사진 포함)·자기소개서·보유 자격증 사본을 위 이메일로 보내주시면'이라는 동일 서류 목록이 반복된다.
- [duplicate-text] `파트너등급제-progression-duplicate` — .m-perk '파트너 등급제' 카드 p 태그 — .m-ladder '등급별 성장 경로' 섹션에 동일 5단계 등급이 수업료율 포함 상세 표시되므로 perk 카드의 단계 나열이 중복이다.
- [duplicate-text] `정착지원금-amount-duplicate` — .m-salary .note — .m-perk 첫 카드(정착지원금)에 '일반 月 100만원 / 시니어 月 130만원, 3개월'이 동일하게 서술되어 금액·기간 정보가 이중 노출된다.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `2026.6-기준-transitional-notice` — .m-list '운영 안내' 섹션 두 번째 li — 2026년 6월 전환 시점 기준의 과도기 문구로, 현재(2026-08-23) 전환 완료 여부에 따라 유효기간이 지난 안내일 수 있다.
### D. 장황 단순화 (2건)
- [verbose-block] `values-diagram-impl-history-comment` — <style> 블록, .values-diagram 룰셋 바로 위 주석 — 과거 실패 구현 경위(1차·2차·커밋 해시)를 CSS 주석에 내장. 이 맥락은 git 커밋 메시지에 속하며 프로덕션 CSS 가독성을 해친다.
- [verbose-block] `script-task-tracking-comments` — 첫 번째 <script> 블록 최상단 한 줄 주석 — 태스크 ID(A-5 P2·G5)·날짜·시안 번호 등 티켓 추적 정보가 프로덕션 JS에 포함되어 git 히스토리에 속하는 내용이 소스를 오염시킨다. 두 번째·세 번째 <script> 블록의 '[추가 2026-07-18 A-5]' 주석도 동일 패턴.

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — CSS 스타일 블록 — .m-values 관련 CSS 영역 (val-chips 두 줄) — HTML 어디에도 class="val-chips" 요소가 없음. m-values 섹션이 PNG 이미지 방식으로 대체된 후 CSS 두 규칙만 잔존
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — m-contact 카드 내 cbox(☎) 및 m-foot .contact 영역 — "나우열 매니저 / 02-6261-1202" 연락처가 지원·문의 카드와 하단 푸터 두 곳에 동일하게 반복 표시
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — m-salary .note 및 m-shift 우대사항 섹션 — 영어 회화 가능자에 대한 급여 추가조정 안내가 연봉 카드("영어 회화 가능자 등 우대 시 급여 추가 조정")와 우대사항("외국어(영어) 회화 가능자 (급여 추가조정)") 두 곳에 실질적으로 동일하게 반복
### C. 낡은 안내·버전 배지 (4건)
- [css-class] `badge.closed` — CSS 스타일 블록 — .m-hero .badge 규칙 바로 아래 — JS는 마감 시 mContact와 topStatus 요소에만 closed 클래스를 추가. heroBadge(.badge) 요소에 closed를 추가하는 코드 경로가 없으므로 이 CSS 규칙이 실제 적용되지 않을 가능성이 높음
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> 블록 첫 줄 주석 — A-5, P2·G5, 시안2 등 내부 이터레이션 버전 배지가 현재와 무관한 과거 식별자
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 두 번째 <script> 블록 첫 줄 주석 (downloadPageAsJpg 함수 위) — A-5 이터레이션 버전 배지 — 이미 지난 시점 식별자
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 세 번째 <script> 블록 첫 줄 주석 (openApplyModal 함수 위) — A-5 이터레이션 버전 배지 — 이미 지난 시점 식별자
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — CSS 스타일 블록 — .values-diagram 규칙 바로 위 4줄 주석 — SVG→PNG 교체 경위(1차·2차 실패 이력, 커밋 해시 42c3b999)를 설명하는 장문 구현 이력 주석. 현재 코드 유지보수에 필요하지 않은 역사적 맥락

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(300s)

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `hint` — <style> 블록 마지막 줄 — 페이지 내 class="hint" 를 가진 요소가 전혀 없음 — 순수 미사용 CSS 룰셋
  - 게이트: 소비자 1058건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `잠시 후 새 주소로 자동 이동합니다` — <p> 태그 두 번째 문장 — meta refresh content="0" + JS location.replace()로 즉각 이동 — '잠시 후'는 딜레이가 있다는 잘못된 시제

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
### D. 장황 단순화 (1건)
- [verbose-block] `cache-bypass-comment` — head, <script> 바로 위 주석 (전체 7줄 파일 기준 상단부) — 7줄짜리 리다이렉트 스텁에 74자 설명 주석. 핵심은 '?v= 캐시버스팅' 한 구절로 충분하며 날짜 꼬리표는 이미 2.5개월 경과해 값어치가 낮음.

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
- (정리 후보 없음)

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] `wp-typography.css` — <head> 말미, </head> 직전 줄 — content="0" 즉시 리다이렉트 스텁에서 외부 CSS를 네트워크로 추가 로드하나, 인라인 <style>이 font-family·a 색상을 이미 완전히 커버함. 폴백(자동이동 실패) 표시 시에도 외부 시트 없이 정상 렌더링됨 — 불필요한 왕복 요청.
  - 게이트: 소비자 98건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
