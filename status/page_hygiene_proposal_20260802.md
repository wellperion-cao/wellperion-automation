# 주간 페이지 위생 정리안 — 20260802 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: 전체

## 시설부 체계 — `3. 웰페리온 가이드/coo/check/시설부 체계.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 지원부 체계 — `3. 웰페리온 가이드/coo/check/지원부 체계.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 운영부 체계 — `3. 웰페리온 가이드/coo/check/운영부 체계.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 주차관리부 체계 — `3. 웰페리온 가이드/coo/check/주차관리부 체계.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 파트너팀 체계 — `3. 웰페리온 가이드/coo/check/파트너팀 체계.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 전사_일정 — `3. 웰페리온 가이드/coo/check/전사_일정.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] <style> 블록 — .ecard.na 아래, .egrid 위 — 구 편집 모드(GM 2026-07-15 제거) 잔여 CSS. JS·HTML 어디서도 ecard-top 클래스를 생성하지 않음
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] <style> 블록 — .ecard-top 바로 아래 — 위와 동일. .ename 클래스도 현재 JS·HTML 어디서도 생성·참조 없음
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] <style> 블록 — .ecard 섹션 — ecard 요소에 na 클래스를 추가하는 JS 코드 없음. 구 편집 모드 잔여
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] JS — saveToServer 함수 정의 직전 — 이미 제거된 함수들을 나열하는 역사적 주석. 현행 코드 이해에 기여하지 않으며 '제거됨'을 선언하는 자기 무효화 주석
### D. 장황 단순화 (2건)
- [verbose-block] <style> 블록 끝 — body.embed .sheet-links 규칙 바로 위 — CSS 규칙 1줄을 설명하는 4줄 주석. 선택자 body.embed .sheet-links a.sheet-link:not(.hlink-add){display:none!important}가 의도를 충분히 전달
- [verbose-block] <style> 블록 — .efield 섹션 (동일 패턴이 :focus 규칙에도 반복: .efield input:focus,.efield select:focus,.ecard-top input:focus) — 복합 선택자에 죽은 .ecard-top input(·:focus) 부분이 포함됨. .efield input·select는 살아있어 규칙 전체 삭제 불가 — 선택자에서 ',ecard-top input' 조각만 제거 필요

## 업무 현황 SSOT — `3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 결재 현황 SSOT — `3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 공지 템플릿 — `3. 웰페리온 가이드/coo/notice/notice_template.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 메인가이드 O1(운영통합체계) — `3. 웰페리온 가이드/wellperion_guide(main).html`
- ⚠️ 감사 실패: JSON 파싱 실패

## 메인가이드 O2(공지) — `3. 웰페리온 가이드/wellperion_guide(main).html`
- ⚠️ 감사 실패: JSON 파싱 실패

## 메인가이드 O3(재등록) — `3. 웰페리온 가이드/wellperion_guide(main).html`
- ⚠️ 감사 실패: JSON 파싱 실패

## 메인가이드 O4 — `3. 웰페리온 가이드/wellperion_guide(main).html`
- ⚠️ 감사 실패: JSON 파싱 실패

## 문의회원 — `3. 웰페리온 가이드/cpo/member/membership.html`
- ⚠️ 감사 실패: JSON 파싱 실패

## 강습회원관리 — `3. 웰페리온 가이드/cpo/member/강습회원관리.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] line 16, :root 블록 두 번째 줄 — --accent, --accent-bg 두 CSS 커스텀 변수가 :root에 선언되었으나 파일 내 var(--accent) / var(--accent-bg) 참조 0건. 나머지 6개 변수(--bg·--paper·--text·--dim·--border·--teal·--teal-bg)는 모두 사용됨
  - 게이트: git grep 오류(rc=129): error: unknown option `accent'
usage: git grep [<options>] [-e] <pattern> [<rev>...] [[--] <path>...]

    --[no-]cached         search in index instead of in the work tree
    --no-index            f
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] line 8-9, <script>location.replace 직후 HTML 주석 — SSOT .md 규칙상 결정 경위·변경 이력은 HTML 본문이 아닌 이력 파일(docs/CLAUDE_이력.md 등)에 보관. 이행 완료된 과거 이동 결정 설명이라 현행 실무 안내 기능 없음
### D. 장황 단순화 (3건)
- [verbose-block] line 11-12, <head> 폰트 로딩 2줄 — meta refresh=0 + JS location.replace 이중 즉시 리다이렉트 스텁에서 CDN 폰트를 내려받아도 실제 렌더 전 이탈하므로 항상 낭비. 목적지 membership.html이 별도로 폰트를 로드함
- [verbose-block] line 35, </style> 이후 두 번째 외부 스타일시트 — 페이지 내 마크업(.card·.icon·.title·.desc·.action-btn)은 전부 인라인 <style>만 사용. wp-typography 클래스 참조 없음. 즉시 리다이렉트 스텁에 불필요한 외부 스타일 로드
- [verbose-block] line 34, </style> 직후 — 즉시 리다이렉트 스텁에서 인증 게이트가 실행되면 게이트 처리 시간만큼 리다이렉트 지연 추가. 목적지 membership.html이 자체 gate.js를 보유하므로 이중 게이트는 비용만 발생

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 문의흐름지도 — `3. 웰페리온 가이드/cmo/funnel/문의흐름지도.html`
### D. 장황 단순화 (1건)
- [verbose-block] <head> 말미, 인라인 <style> 블록 직후 — content="0" 즉시 리디렉트 페이지에 외부 타이포그래피 CSS를 로드 — 실제 렌더 시간이 없어 네트워크 왕복 비용만 발생하며, 필요한 스타일은 인라인 <style> 블록으로 이미 완결됨

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] renderKpiTable 함수 상단 변수 선언부 (inquiries·convDone·convRate 줄 사이) — 선언 후 rows 배열·함수 어디에도 참조되지 않음 — inquiries·convDone·convRate만 사용, convInq는 사실상 dead variable
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] .cover-notice (표지 하단) / .page-footer (페이지 최하단) — "개인정보 미포함" 안내가 cover-notice와 page-footer 두 곳에 중복 — footer 쪽이 더 적절한 위치
- [duplicate-text] 섹션 04 .panel-note 상단 / maybeRenderChannelFunnel() 렌더 하단 <div> — "전환율=전화매칭 누적 추정" 설명이 패널 상단 note와 JS가 렌더하는 테이블 하단 주석 div 두 곳에 중복
### D. 장황 단순화 (3건)
- [js-function] 두 번째 <script> 블록, GAS_URL 상수 선언 직후 — 항상 인자를 그대로 반환하는 no-op passthrough — fetch() 호출 3곳 전부 _wpUrl(x)를 x로 인라인하면 함수 자체 제거 가능
- [css-class] CSS 「수기 입력란 (호환 유지)」 주석 아래 4개 룰셋 — HTML body 및 JS 렌더 문자열 어디에도 manual-section·manual-row 클래스 사용처 없음; "(호환 유지)" 주석으로 의도 보존한 것이어서 A 제외
- [css-class] CSS .panel 룰셋 바로 아래; @media print 내 .panel,.panel-flush{...} 에도 공유 참조 — HTML body 및 JS 렌더 문자열 어디에도 class="panel-flush" 사용처 없음 — 현 파일 한정 미사용

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] about-stats(.stat-label) / facilities .section-desc / membership .section-desc — 3곳 — '사전 예약제' 또는 '사전 예약으로 운영' 메시지가 About 통계·시설 안내·멤버십 안내 3개 섹션에 반복 — 멤버십 1곳으로 통합 가능
### D. 장황 단순화 (1건)
- [verbose-block] about 섹션 > about-inner 첫 번째 열 — 반투명 'W' 글자만 렌더링하는 500px 높이 placeholder 박스 — 실제 시설 사진 미삽입 상태로 시각 가치 없음

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] JS — buildM5Map 함수 선언부 주석 — 함수명은 buildM5Map·파라미터명은 m5Status인데 주석은 'M3 큐'로 표기. resolveBadge 내 '// M3 상태 우선' 주석도 동일 패턴 — 파일 전반 M3/M5 명칭 혼용 stale
### D. 장황 단순화 (2건)
- [verbose-block] JS — buildM5Map 내부 else 블록 — 2줄 로직에 3줄 주석, '덮어씌우지 않음'이라 쓰고 실제론 발행완료시 덮어씌움 — 주석이 코드와 모순·장황. '발행완료면 앞 항목 덮어씌움' 한 줄 주석으로 교체 가능
- [verbose-block] CSS :root 변수 선언 블록 — 파일 내 var(--purple)/var(--purple-bg) 사용처 0 — 나머지 6색(green/red/yellow/blue/orange/accent)은 전부 사용 중. 죽은 변수 유력

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] 두 번째 <style> 블록, .wlp-inq 룰셋 CSS 변수 선언줄 (--bg 바로 뒤) — var(--paper) 참조가 파일 전체에 0회. 카드 배경은 background:#fff 리터럴로 직접 기술되어 이 변수를 우회함.
  - 게이트: git grep 오류(rc=129): error: unknown option `paper'
usage: git grep [<options>] [-e] <pattern> [<rev>...] [[--] <path>...]

    --[no-]cached         search in index instead of in the work tree
    --no-index            fi
### B. 중복 설명 병합 (2건)
- [duplicate-text] type-grid 바로 위 HTML 주석 / 파일 최상단 주석 1단락 '★ 구글폼(forms.gle…) 완전 탈피' / wpToSurvey 함수 상단 인라인 주석 2행 — 구글폼 탈피·6종 Survey 귀속 사실이 세 주석에 각각 반복 기술됨.
- [duplicate-text] <script> 태그 바로 위 HTML 주석 vs. wpToSurvey 함수 상단 3줄 인라인 주석 — UTM 승계 목적·동작이 외부 HTML 주석과 함수 내부 주석 양쪽에 거의 동일하게 중복 설명됨.
### C. 낡은 안내·버전 배지 (1건)
- [css-class] 두 번째 <style> 블록, HERO 섹션 CSS — 2026-07-16 GM 최종확정('코럴 최소' 방침)으로 background가 var(--beige)로 전환됐으나 클래스명이 divider-coral 그대로 남아 혼동 유발. 현재 상태와 이름이 불일치.
### D. 장황 단순화 (1건)
- [verbose-block] 파일 최상단 HTML 주석 전체 (~80줄, <link> 태그 직전까지) — 다크 히어로 6회 반전·로고 겹침 3단계 수정·방향전환 이력 등 현재 이미 폐기·해소된 설계 경위가 80줄을 채움. 현재 운영 상태(베이지 통일·헤더 숨김·lang-switch)는 CSS/JS 인라인 주석이 이미 커버. 이력은 git 커밋 로그에 속함.

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 36-37번줄, .action-btn:hover 바로 다음 — `.action-btn.green` 적용 요소가 HTML 전체에 없음. 녹색 버튼은 별도 `.btn-add` 클래스로 독립 정의됨(63-64번줄). JS renderRooms에도 동적 추가 없음.
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] ①톡방 카드 info-box 127-128번줄('방 이름은 카카오톡에서 실제로 열려 있는 채팅방 창 제목과 정확히 일치해야 전송됩니다') ②✅ 사용 조건 아코디언 179번줄('방 이름은 여기 목록의 이름과 완전히 동일한 글자여야 합니다') — 동일 규칙(이름 정확 일치 필수)이 두 곳에 반복. info-box는 항상 노출되고, 아코디언은 접혀 있어 사용자가 두 번 읽게 됨. 공백·오탈자 예시는 아코디언에만 있으므로 info-box에서 한 줄로 통합 가능.
### C. 낡은 안내·버전 배지 (2건)
- [dead-markup] <head> 96번줄 최하단 — 이 파일의 로컬 자산 경로는 `../../_assets/`(언더스코어 포함, gate.js 8번줄·print_options.js 312번줄) 인데, 이 link만 `../../assets/`(언더스코어 없음)로 불일치 — 404로 실로드 실패 가능성 높음.
- [stale-notice] ✅ 사용 조건 아코디언, 178번줄 — '실측 검증됨' 표현은 카카오톡 PC 앱 UI 업데이트 시 즉시 stale. 바로 아래 '⚠️ 한계' 아코디언이 이 취약성을 이미 명시해 모순 가능성 있음.
### D. 장황 단순화 (1건)
- [verbose-block] :root 변수 블록 19-20번줄 — yellow·teal 계열 6개 변수가 이 파일의 CSS 규칙·인라인 스타일·JS 어디에도 참조되지 않음. 디자인 팔레트 복사-붙여넣기 잔재로 추정.

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] CSS <style> 블록 · .header-btns 정의 바로 위 — HTML 전체에 class="header-right" 사용 0건 — header div 두 번째 자식은 header-btns가 flex container 담당
  - 게이트: 소비자 14건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] 미수금 탭 · info-banner 바로 아래 placeholder — 직전 info-banner가 '데이터 소스 미배관' 동일 메시지를 이미 상세 기술 — 연속 중복
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] header-meta 인라인 · JS 덮어쓰기 대상 — JS 성공 시 실측 날짜로 교체됨. 실패 시 잔류하는 'v1.0' 버전 배지는 의미 없는 고정 문자열
### D. 장황 단순화 (2건)
- [verbose-block] 채널별 분해 탭 · 북극성 KPI 연결 섹션 하단 — 색상 범례는 막대 시각으로 자명 · 72억·달성률은 gauge-label·bar-row-val이 이미 표시 — 중복 설명
- [verbose-block] 미수금 탭 · 미수금 OCF 영향 분석 섹션 첫 문단 — 실무자 대상 운영 대시보드에서 OCF 용어 정의 교육 산문 — 실측 데이터도 없는 플레이스홀더 섹션에서 장황

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-id] renderDashboard 함수 내 grid.innerHTML 템플릿 문자열 두 번째 dash-card — id='budgetCard'를 설정하나 CSS 셀렉터·document.getElementById 어디에서도 미참조. fillBudgetCard()는 budgetMonthVal·budgetRateVal만 조회. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [dead-markup] loadExpenses 함수 상단, loadingMsg 선언 직후 두 줄 — loadExpenses 내 emptyState·listEl 지역변수가 이 함수 내 한 번도 참조되지 않음. loadingMsg.style.display만 사용. renderList가 동일 DOM을 자체 조회함.
  - 게이트: 소비자 39건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] applyFilter 함수(JS 중반부) 및 getFilteredItems 함수(JS 하단) — applyFilter와 getFilteredItems가 동일한 3-조건 필터(월/카테고리/승인상태)를 각각 독립 구현. applyFilter가 getFilteredItems()를 호출하면 내부 5줄 중복 제거 가능.
### D. 장황 단순화 (2건)
- [verbose-block] :root 블록 전체 — --green-bg, --red-bg, --yellow, --yellow-bg, --blue, --blue-bg, --purple, --purple-bg, --orange-bg 총 9개 변수가 이 파일 CSS 규칙·JS 내 직접·간접 모두 미참조. --red/--orange/--green은 --danger/--warning/--success alias로 살아있으나 -bg 계열과 blue/yellow/purple 색상 전체는 미사용.
- [verbose-block] loadFromLocal 함수 선언부 — action 파라미터를 선언하나 함수 본체 전체에서 미사용. 호출부(apiCall catch, loadExpenses catch) 모두 action 값과 무관하게 전체 리스트를 반환받음.

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 77행 — .cm-msg 규칙셋 세 번째 줄 — JS 전체에서 cm_msg 엘리먼트에 'ok' 클래스를 부여하는 코드가 없음. submitCheck()는 'cm-msg err'와 'cm-msg'만 설정(359·330·352행). · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
### B. 중복 설명 병합 (1건)
- [duplicate-text] 85행 <small id="hdrSub"> 정적 텍스트 vs 179행 renderModeSelect() textContent 재설정 — 동일 문자열이 HTML 정적 텍스트(85행)와 JS renderModeSelect()(179행) 두 곳에 존재. init()이 항상 renderModeSelect()를 즉시 호출하므로 정적 텍스트는 사용자에게 노출되기 전에 덮어써짐.
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] 151~152행 — EXEC_URL 상단 블록 주석 — PIN 1202를 JS 주석 평문으로 노출. 코드 설명 목적이나 실제 PIN 값이 소스에 박혀 있어 보안 위생 불량. 아래 175~177행 주석과 이중 기재.
- [stale-notice] 175~177행 — renderModeSelect() 함수 상단 변경이력 주석 — '추가 2026-07-04 r2' 날짜 태그는 변경 이력 메모로 기능이 안정화된 현재 낡음. PIN 1202를 재차 평문 노출(151행과 이중 기재). '기존 흐름 그대로 진행' 등 구현 당시 맥락 설명은 코드 자체가 대체함.
- [stale-notice] 194행 — proceedCheckin() 함수 직전 인라인 주석 — '기존 init() 로직 그대로'는 리팩터링 당시 임시 메모. 함수명 proceedCheckin이 의미를 이미 전달하므로 주석이 추가 정보를 제공하지 않음.

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 71번째 줄, .banner.ok 바로 앞 — setBanner() 호출 3곳(249·299·336줄) 모두 cls='ok' 또는 빈값 — 'err' 클래스가 이 파일 내에서 한 번도 적용되지 않음
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] ovWrite 모달 120번째 줄 — openWrite()가 wf_sub에 '기한 … · 저장 후 수정 불가'(311줄)를 이미 설정하므로 같은 모달 내 lock-note가 동일 경고를 반복
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] script 블록 131번째 줄, 최상단 주석 2번째 줄 — 날짜·버전 태그 '[변경 2026-07-04 r2]'는 git 이력으로 관리해야 할 변경 기록 — 소스 내 날짜 배지가 stale
- [stale-notice] 138번째 줄, WEEK_QUESTIONS 상수 바로 위 주석 — '2026-07-23 개정' 날짜 태그가 소스 주석에 박혀 stale — 파서 형식 계약('1) … | 2) … | 소감:')만 남기면 충분
- [stale-notice] 85번째 줄, header 내 brand small 요소 초기값 — init()(353줄)이 즉시 hdrSub를 '{name} 님의 성찰 기록'으로 덮어쓰고, renderPickList()(190줄)도 즉시 덮어써 HTML 초기 텍스트가 사용자에게 사실상 노출되지 않음
### D. 장황 단순화 (1건)
- [verbose-block] 9~12번째 줄 :root 변수 블록, --amber 바로 뒤 인라인 — 파일 내 어디에도 var(--blue) 참조 없음 — --green·--red·--amber·--accent 등 나머지 변수는 모두 참조됨

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] line 192 · perks2 섹션 마지막 perkcard(프리미엄 환경) — "한남동 3,000평" 수치는 line 163 about-stats 세 번째 카드(통합 라이프스타일 공간)에서 이미 스캔 가능한 형태로 표시되어 있음. perks 카드는 같은 수치를 서술체로 재기술해 중복.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] line 136 · <head> 끝 — 페이지 안 모든 스타일은 인라인 <style> 에 자기완결적으로 정의되어 있음. HTML 마크업 어디에도 wp-typography.css 고유 클래스로 추정되는 참조가 없어 실제 적용 여부 불확실. 파일이 네이티브 요소(p·h1 등)에 스타일을 적용한다면 무해하게 살아있을 수 있음.
### D. 장황 단순화 (1건)
- [verbose-block] lines 242–247 · body 하단, footer 직전 — 내부에 <a>·<button> 등 클릭 가능 요소가 전혀 없는 순수 장식 마감 블록. "채용 공고를 확인해보세요" 메시지는 hero(line 151)와 사실상 동일하며, 실제 링크 기능은 위의 .grid 부서 카드가 모두 담당함. 삭제 또는 버튼 하나 추가로 기능화 검토 대상.

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 — .m-values 영역 CSS 근처 (45–46번째 줄 추정) — HTML body 어디에도 class="val-chips" 사용처 없음 — 같은 디렉터리 5개 파일 전부 동일하게 미사용 확인
  - 게이트: 소비자 14건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] .m-perk 카드(3개) + .m-perk-wide ↔ .m-list 복리후생 섹션 — 4대보험·퇴직금·연차·직원할인이 상단 perk 카드/배너와 하단 복리후생 리스트 두 곳에 동일 내용 중복 기재
- [duplicate-text] .m-contact .cbox ↔ .m-foot .contact — 02-6261-1202 · 나우열 매니저 연락처가 m-contact 박스와 m-foot 두 곳에 완전 중복
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] <style> 블록 — .values-diagram 규칙 바로 위 — PNG 채택 경위(실패 1·2차 시도 포함)를 프로덕션 HTML에 내장 — git 이력이 보관해야 할 내용
### D. 장황 단순화 (3건)
- [verbose-block] 첫 번째 <script> 블록 상단 1행 — 내부 시안 번호(A-5 P2 G5)·날짜 포함 changelog 주석 — 코드 이해에 무기여
- [verbose-block] 두 번째 <script> 블록 상단 1행 — 내부 버전 태그 changelog 주석 — 코드 이해에 무기여
- [verbose-block] 세 번째 <script> 블록 상단 1행 — 내부 버전 태그 changelog 주석 — 코드 이해에 무기여

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] <style> 블록 — .m-values 관련 룰 묶음 (.m-values .t-kicker 직전) — HTML 어디에도 class="val-chips" 요소가 없음. .m-values 섹션은 img.values-diagram + .quote 로만 구성되며 칩 목록 마크업 없음.
  - 게이트: 소비자 14건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] <style> 블록 — .m-hero .badge 룰 직후 — JS 마감 처리 코드가 #mContact·#topStatus 에만 'closed' 클래스를 추가함. #heroBadge(.badge) 에는 어떠한 classList 조작도 없어 이 셀렉터가 매칭될 수 없음. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
### B. 중복 설명 병합 (2건)
- [duplicate-text] .m-contact .cbox(☎ 02-6261-1202 · 나우열 매니저) + .m-foot .contact(문의 : 02-6261-1202 · 나우열 매니저) — 동일 전화번호와 담당자명이 지원 카드와 푸터 두 곳에 동시 노출. 변경 시 두 곳 동기화 필요.
- [duplicate-text] .m-perk-wide p '근무 유니폼 제공' + .m-tags .chip '유니폼 제공 등' — 유니폼 제공 항목이 AI 서포트 혜택 카드 본문과 태그 칩 두 곳에 중복 기재.
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] 첫 번째 <script> 블록 최상단 주석 — 작업일자·태스크ID 태그([A-5 P2·G5])는 git 커밋 메시지 정보로 코드 내 상시 노출 불필요. 함수 동작 설명은 별도 한 줄로 정리 가능.
- [stale-notice] 두 번째 <script> 블록 최상단 주석 — 작업일자·태스크ID 태그가 코드에 노출. 동작 설명은 함수명 downloadPageAsJpg 로 자명.
- [stale-notice] 세 번째 <script> 블록 최상단 주석 — 작업일자·태스크ID 태그 노출. 스팸가드 구현 위치 메모는 코드 읽으면 자명(website 허니팟 필드 존재).
### D. 장황 단순화 (2건)
- [verbose-block] <style> 블록 — .values-diagram 룰 직전 8줄 CSS 주석 블록 — PNG 교체 경위(1차 SVG 경로 판정 실패·2차 div 렌더 파손·래스터라이즈 결정·커밋 해시 42c3b999)가 CSS 주석에 내장됨. git 커밋 히스토리 내용으로 운영 파일 노출 불필요.
- [verbose-block] .m-ladder .ladder-row — .step ②~⑤의 <span> 텍스트 ('진급 2단계'~'진급 5단계') — '진급 2단계'~'진급 5단계'는 순번 숫자를 텍스트로 반복한 것 이상의 정보 없음. ①사원의 '연차가 아닌 성과로 평가'만 실질 안내. 나머지 4칸은 단계명 자체(주임·대리·과장·차장)가 충분.

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] line 25, <head> 마지막 줄 — 0초 리다이렉트 스텁에서 외부 CSS 로드. 인라인 <style>이 이미 body·.box·h1·p·a.btn·.hint 전부 커버하며, wp-typography.css가 스타일을 입힐 요소가 없다. 즉시 이탈되는 페이지에서 불필요한 네트워크 요청만 발생.
  - 게이트: 소비자 89건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] <head> 마지막 태그 — noscript 아래 — location.replace()로 즉시 리다이렉트되는 스텁 페이지; body에 클래스·선택자 0건, 인라인 스타일만 사용 → stylesheet 요청이 화면 렌더에 전혀 기여하지 않음
  - 게이트: 소비자 89건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] line 4, HTML head — <p> 본문 '항해 지도는 G1 오늘의 항로 · 북극성별 보기로 통합되었습니다.'와 내용 동일. 이 페이지는 즉시 리다이렉트되므로 검색엔진이 이 description을 인덱싱하지 않아 SEO 목적도 없음.
### D. 장황 단순화 (2건)
- [verbose-block] line 10, HTML head — 인라인 <style>이 이 페이지의 모든 셀렉터(body·.box·p·a·a:hover)를 완전히 정의하며, 마크업 어디에도 타이포그래피 클래스 참조 없음. 즉시 리다이렉트 스텁이라 실제 노출 시간 ≈ 0ms — 외부 시트 로드가 불필요한 네트워크 요청.
- [verbose-block] lines 5–9, HTML head comment — 이식 경위·구 selector(#gm1-northstar-view) 등 이력 설명 5줄이 프로덕션 HTML에 박혀 있음. 운영 지시('하드삭제 금지')만 남기면 4줄은 git 커밋 메시지 영역.

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### D. 장황 단순화 (2건)
- [verbose-block] <head> 마지막 줄 (</head> 바로 위) — 0초 즉시 리다이렉트 스텁에 전체 타이포그래피 시트 로드 — 인라인 body/a 스타일이 이미 충분, 단일 폴백 문단에 과잉 로드
- [verbose-block] <body> 첫 번째 줄 HTML 주석 — 개발 이력·의사결정 근거가 HTML 소스에 인라인 기재 — git 커밋 메시지에 있어야 할 내용, 렌더링 결과물에 불필요
