# 주간 페이지 위생 정리안 — 20260906 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: 전체

## 시설부 체계 — `3. 웰페리온 가이드/coo/check/시설부 체계.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `day-type.closed` — CSS :root 블록 이후 .day-type 룰셋 — renderBoard()·renderDayToolbar() 등 칸반 렌더 전체 경로에서 'closed' 값을 부착하는 코드가 없음. day-type은 'weekday'·'weekend' 두 값만 사용.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `mpEsc` — 월간운영계획 탭 섹션 상단 — MP_DEPT 선언 직후 — fmEsc와 함수 본문이 한 글자도 다르지 않은 완전 동일 이스케이프 헬퍼. 페이지 내 두 번 선언.
  - 게이트: 근거: 리포 참조 25건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (8건)
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — tabs div — 시설점검 버튼 바로 앞 HTML 주석 — 탭 변경 완료(2026-06-12) 이후 실무 안내 기능이 없는 개발 이력 주석. 현재 운영과 무관.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — 규정 탭 board-scroll 내 board-col 사이 주석 — 이관 완료 후 남겨진 이력 주석. 해당 컬럼은 이미 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — 규정 탭 board-scroll 말미 (board-fullwidth 닫힘 직전) — 분리 완료 이후 남겨진 이력 주석.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — 규정 탭 board-fullwidth 닫힘 직후 — 이관 완료 후 남겨진 이력 주석.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — tab-fcheck div 직전 HTML 주석 — UI·JS 완전 제거 완료 후 남겨진 이력 주석. 현재 기능적 의미 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [dead-markup] ⚠️ 대상 이름 없음(자동적용 불가) — tab-manual div 최상단 HTML 주석 — 이관·재구성이 완료된 Phase 1 경위 주석. 실무 운영에 불필요.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [css-class] `admin-card` — CSS 본문 — .status-dot 룰 직전 블록 — 「현황 대시보드」 탭이 2026-07-14 완전 제거됐지만 .admin-card·.tip-card·.status-dot CSS 룰이 잔존. chunk 1 내 모든 JS 렌더 함수에서 해당 클래스를 부착하는 코드 없음.
  - 게이트: 근거: 리포 참조 27건(git grep 실측) — 확인 필요
- [css-class] `tip-card` — CSS 본문 — .hidden 룰 직전 블록 — .admin-card와 동일한 제거된 대시보드 연관 CSS. 페이지 내 HTML·JS 템플릿에서 'tip-card' 클래스 부착 코드 미발견.
  - 게이트: 근거: 리포 참조 10건(git grep 실측) — 확인 필요
### D. 장황 단순화 (6건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — fcStore 초기화 직전 JS — 「F 안전」 제거 경위 3개 연속 블록 시작부 — 이미 삭제 완료된 항목(소방일일·경보확인·에스컬레이터·정수기)의 삭제 경위를 설명하는 연속 3개 블록(합산 ~40줄). 삭제된 코드가 없으므로 경위 설명도 불필요하며, 커밋/PR 메시지에 속하는 내용.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] `fmCatCanon` — fmCatCanon 함수 선언 직전 — 6줄 감사 경위 서술. '카테고리 이름 이음동의어 정규화(AI초안 배지 제거 전/후 통합)' 한 줄로 대체 가능.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [verbose-block] `FM_RETIRED_CATS` — FM_RETIRED_CATS 변수 선언 직전 — 5줄 감사 배경 설명. 객체 값에 이미 '2026-08-26 폐지 — 입력 화면에 칸 없음'이 담겨 있어 중복 서술.
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [verbose-block] `renderFmKpi` — renderFmKpi 함수 내 el.innerHTML 할당 직전 — 3줄 라벨 변경 이유. 출력 라벨 '점검한 날 수'가 의도를 충분히 전달하므로 경위 서술 불필요.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [verbose-block] `renderA3FacilityMonthlyFromData` — renderA3FacilityMonthlyFromData 내 catRows 생성 직전 — 버그 수정 경위 메모. fmMergeCats 호출이 이미 코드에 반영돼 있어 '왜 과거에 버그가 있었는지' 설명은 잉여.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [verbose-block] `fcSave` — fcSave 함수 내 _abNote 변수 선언 직전 — 3줄 대화 재현 포함 개발 배경 메모. 코드의 abnormalNote 조건부 삽입 패턴 자체가 의도를 충분히 전달.
  - 게이트: 근거: 리포 참조 14건(git grep 실측) — 확인 필요

## 지원부 체계 — `3. 웰페리온 가이드/coo/check/지원부 체계.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [js-function] `inspMemoBoxHtml` — renderDayFocusSection 직후 — window._inspMemo 선언부터 _saveInspMemo 닫는 중괄호까지 — drawUI 내 주석 '다른 참조 없음(GM 2026-06-17)' 명시. inspMemoBoxHtml 렌더 호출이 제거됐고 세 함수 모두 진입점 없음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [js-function] `wpLdyRenderToday` — wpLdyMonthStats 함수 직전 — 주석 포함 함수 전체 — 코드 자체 주석 '화면에서 부르지 않는 함수' 명시. wpLdyRenderAll 호출 목록에서도 제외됨(주석에 '남겨 뒀지만 여기서 부르지 않는다' 기재).
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `둘째주 휴관 작업 4구역 목록` — #a3-closedday-print > .cdp-grid (cdp-card 4개) 와 #tab-manual > 🗓 둘째주 휴관 작업 .manual-body > .cd-grid (cd-card 4개) — A·사우나/B·락커룸/C·내부/E·외부 4구역 항목 텍스트가 인쇄 전용 컨테이너(cdp-*)와 매뉴얼 탭 화면(cd-*)에 완전 동일 내용으로 이중 하드코딩됨 — CSS 클래스명만 다를 뿐 내용 일치
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (10건)
- [stale-notice] `a3-monthly-print 정적 June-2026 리포트` — <div id="a3-monthly-print"> 전체 본문 (mrp-doc 블록) — printA3Monthly() 가 이 컨테이너를 그대로 출력하는데 내용이 '2026년 6월 작업 요약'·'본 요약은 2026-06-30 기준' 으로 하드코딩 → 현재(2026-09-06) 인쇄 시 항상 3개월 전 고정 리포트만 출력됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `최종 등록 기준 2026-06-24` — #tab-guide 직원 구성·역할 카드 하단 <p> 요소 — 직원 목록은 JS가 동적으로 채우는데 '최종 등록 기준 2026-06-24' 날짜 배지는 정적 하드코딩 — 이후 직원 정보가 갱신돼도 배지는 2.5개월째 자동 업데이트되지 않음
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [stale-notice] `resetManualLocalView` — renderManualItems 함수 직전 독립 한 줄 주석 — 삭제된 함수를 언급하는 고아 주석. 함수 본체가 없어 참조 불가한 이름.
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [stale-notice] `v2.50` — let _manualEdit=false; 선언 직전 2줄 — 버전 배지 주석 — 기능이 이미 통합·운영 중이며 버전 번호는 실무 참조 가치가 없음.
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `v2.48` — /* isAddedItem — 추가 항목 판별 */ 주석 직전 — v2.48·v2.49·v2.51 버전 배지 주석 — 변경이 이미 병합·운영 중.
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `wpLdySheetSetRemark` — wpLdySheetSet 함수 본문 직전 주석 — 삭제된 함수 wpLdySheetSetRemark의 묘비 주석만 남음 — 함수 본체는 없고 과거 이력만 기록
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [stale-notice] `wpLdyRenderMonth` — wpLdyRenderMonth 선언 직전 경고 주석 — 2026-09-04 이후 화면 호출 경로가 없다고 주석이 직접 명시; 함수 첫 줄에서 wpLdyCards 엘리먼트 없으면 즉시 return
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [stale-notice] `시드 자동동기 폐지` — wpLdyLoadLocal(); wpLdyMarkTodo(); 호출 직전 두 주석 블록 — 첫 주석은 이미 폐지된 자동동기 기능(setTimeout·시그니처 가드)을 설명하고, 두 번째가 2026-06-27 폐지 선언 — 함께 삭제된 기능의 이력만 남긴다
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [stale-notice] `STAFF_SEED` — STAFF_SEED 배열 첫 번째 항목 — 오늘(2026-09-06) 기준 '6월말 퇴직 예정' 문구는 약 2개월 전 이미 경과 — 저장 이력 없는 첫 로드 시 낡은 상태가 화면에 노출됨
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [stale-notice] `_relocateDayItems` — _relocateDayItems 함수 선언 직전 주석 — getSched 재정의에서 2026-06-29 '_relocateDayItems 제거'라고 명시 — 함수는 정의돼 있으나 getSched·getNightSched 어디서도 호출하지 않음
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] `DAY_FOCUS` — JS roundHasItems() 함수 및 _roundProgress() 함수 내부 close1 분기 — const DAY_FOCUS={} (빈 객체) 이고 주석도 '하드코딩 비움 — 자동 무력화(no-op)' 라고 명시 → if(DAY_FOCUS[dow]) 조건이 항상 false 이므로 roundHasItems·_roundProgress 두 함수의 해당 forEach 블록이 절대 실행되지 않는 영구 dead branch
  - 게이트: 근거: 리포 참조 86건(git grep 실측) — 확인 필요
- [dead-markup] `groupSubmitBarHtml` — collectGroupSubmits 함수 직후 — 기능 제거 후 항상 빈 문자열 반환 stub. drawUI 2곳·renderDayFocusSection 1곳에서 호출하나 출력 기여 없음.
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [verbose-block] `quickAddBarHtml` — quickAddBarHtml 함수 전체 — 항상 빈 문자열만 반환 — 기능이 2026-06-12에 제거됐고 선언만 남아 있어 어떤 렌더에도 콘텐츠를 기여하지 않는다
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요

## 운영부 체계 — `3. 웰페리온 가이드/coo/check/운영부 체계.html`
### C. 낡은 안내·버전 배지 (3건)
- [css-class] `--paper` — head > style > :root 블록 — 페이지가 리다이렉트 스텁으로 전환된 이후 이 파일 내 인라인 스타일·style 블록 어디에서도 var(--paper) 참조 없음 — 전체 페이지 시절 템플릿 잔류 변수 가능성
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `paper'
usage: git grep [<options>] [) — 확인 필요
- [css-class] `--accent-bg` — head > style > :root 블록 — 페이지가 리다이렉트 스텁으로 전환된 이후 이 파일 내 어디에서도 var(--accent-bg) 참조 없음 — 전체 페이지 시절 템플릿 잔류 변수 가능성
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `accent-bg'
usage: git grep [<options) — 확인 필요
- [css-class] `--border` — head > style > :root 블록 — 페이지가 리다이렉트 스텁으로 전환된 이후 이 파일 내 어디에서도 var(--border) 참조 없음 — 전체 페이지 시절 템플릿 잔류 변수 가능성
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `border'
usage: git grep [<options>] ) — 확인 필요

## 주차관리부 체계 — `3. 웰페리온 가이드/coo/check/주차관리부 체계.html`
### A. 죽은 코드(자동삭제 대상) (9건)
- [css-class] `loading` — style 블록 — .hidden 정의 직후 — 페이지 내 class="loading" 요소 없음. 비동기 상태는 인라인 스타일·id별 요소로 처리
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 244건(git grep 실측) — 확인 필요
- [css-class] `time-slot` — style 블록 — .progress-text 정의 직후 — time-slot·slot-header·slot-time 클래스 요소가 HTML 및 JS 출력물 어디에도 없음. 시간대 슬롯 UI는 미구현
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [css-class] `admin-card` — style 블록 — .saving 정의 이후 /* Dashboard */ 주석 구간 — mpRender·loadParkingRevenue는 인라인 스타일·dash-stat-* 클래스 사용. admin-card·admin-row·status-dot 클래스 요소 미존재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 27건(git grep 실측) — 확인 필요
- [css-class] `tip-card` — style 블록 — .status-dot 정의 직후 — tip-card 클래스를 생성하는 정적 HTML·JS 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 10건(git grep 실측) — 확인 필요
- [css-class] `group-submit-bar` — style 블록 — .extra-input.tip-field 정의 이후 — 카테고리별 개별 제출 UI가 조 단위 제출(park-round-bar+submit-bar) 체계로 대체됨. group-submit-* 클래스 요소 미존재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [css-class] `night-btn` — style 블록 — .submit-btn.submitted 정의 직후 — 야간조 없음(pp_shift 카드·PARK_ROUNDS_* 명시). night-btn 클래스 요소 미존재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 17건(git grep 실측) — 확인 필요
- [css-class] `header-util-btns` — style 블록 — /* ── Header utility buttons ── */ 주석 하단 — 헤더 버튼은 .sheet-links·.tab-dropdown·인라인 스타일로 구현됨. header-util-btns 클래스 요소 미존재(print 규칙에 나열됐으나 실요소 없어 no-op)
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 27건(git grep 실측) — 확인 필요
- [css-class] `report-btn` — style 블록 — .util-btn.print-btn 정의 이후 — util-btn 요소는 print-btn만 사용 중. report-btn·share-btn 클래스 요소 정적 HTML·JS 어디에도 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
- [js-function] `tog` — 인라인 스크립트 — togManual 정의 직후 — togManual(this) 로 접이식 토글 구현 중. tog() 호출부가 HTML·JS 어디에도 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 793건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `pg_clean` — PARK_GUIDE_SEED.guide id:pg_clean vs PARK_MANUAL_SEED.manual id:pm_clean — 가이드 탭 pg_clean과 매뉴얼 탭 pm_clean이 '주차관리인 청결관리' 내용을 문장 단위로 거의 동일하게 반복(지상·지하 바닥 청소/통행로/쓰레기/배수구/화장실/청소 장비 7개 항목 일치)
  - 게이트: 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-valet 닫는 태그 직후 HTML 주석 — 이미 제거된 탭과 2026-06-23 완료된 전환을 서술하는 완료 이력 주석. 현재 구조에 정보를 추가하지 않음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — .tabs 내 🧹 일일점검 버튼 바로 위 주석 — 탭 이름 변경이 이미 완료. 현재 버튼 텍스트는 '🧹 일일점검'으로 수정 완료 상태이며 이 주석은 사후 이력 서술
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-check div 바로 위 HTML 주석 — 탭 독립 분리가 이미 완료된 사건 기록. 현재 구조에서 왜 check 탭이 독립인지 설명하는 역할은 소멸
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — #tab-policy 근무·휴게 시간 섹션 — 컬러 바 타임라인 도식(근무자 A/B flex-bar)과 그 아래 요약 표 — A 라인·B 라인 컬러 바 시각화와 바로 아래 요약 표가 동일 정보(A=정시~50분 근무, B=10분~정시 근무)를 중복 표현. 표 단독으로 실무 안내 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 파트너팀 체계 — `3. 웰페리온 가이드/coo/check/파트너팀 체계.html`
### A. 죽은 코드(자동삭제 대상) (12건)
- [js-function] `reviveInstr` — PAGE IIFE — applyLiveInstr 직후 — IIFE 전체에서 reviveInstr() 호출부 0건. 정의만 존재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
- [css-class] `sheet-links` — head <style> — .sheet-link 직전 — HTML 전체에 class="sheet-links" 요소 없음. 개별 링크는 .sheet-link 단독 적용
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 52건(git grep 실측) — 확인 필요
- [css-class] `mode-badge` — head <style> — class="mode-badge" 요소 없음. JS 생성 HTML에도 미사용
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [css-class] `tabs` — head <style> — 이 페이지 탭은 .header-top 안 <button class='tab'>. class='tabs' 래퍼 요소 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 163건(git grep 실측) — 확인 필요
- [css-class] `day-type` — head <style> — .mode-badge 직후 — class='day-type' 요소 없음. 체크리스트 템플릿 잔재 4룰
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 42건(git grep 실측) — 확인 필요
- [css-class] `loading` — head <style> — .hidden 직후 — class='loading' 요소 없음. JS 생성 HTML에도 미사용
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 244건(git grep 실측) — 확인 필요
- [css-class] `closed-msg` — head <style> — class='closed-msg' 요소 없음. 영업종료 안내 잔재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [css-class] `saving` — head <style> — .group-submitted 직후 — class='saving' 요소 없음. JS에도 .saving 참조 없음. .toast-msg(z-index:300)로 대체된 것으로 보임
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 61건(git grep 실측) — 확인 필요
- [css-class] `toast-msg` — head <style> — @media print 직전 — class='toast-msg' 요소 없음. JS 내 querySelector('.toast-msg') 호출 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 30건(git grep 실측) — 확인 필요
- [css-class] `highlight` — head <style> — manual-body 룰 그룹 — class='highlight' 요소가 manual-body 안에 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 127건(git grep 실측) — 확인 필요
- [css-class] `day-focus-section` — head <style> — manual-body 룰 그룹 하단 — class='day-focus-section' 요소 없음. 수동 탭 특화 잔재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [css-class] `manual-body-ul` — head <style> — .manual-body 룰 그룹 — manual-body 내 콘텐츠는 전부 <div> 구조. <ul>·<li> 요소 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `ERP_API_ON` — PAGE IIFE — WORK_TODO_API 선언 아래 — 같은 IIFE 스코프에 var ERP_API_ON이 2회 선언. 첫 번째는 매출 배관 위. 동일 표현식 중복 — var 호이스팅으로 두 번째는 no-op이나 혼란 유발
  - 게이트: 근거: 리포 참조 113건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `tab-guide` — head <style> — .content 룰 직후 — 이 페이지 ID는 tab-ptguide(접두 pt-). #tab-guide는 존재하지 않는 ID — 셀렉터 앞부분 스테일
  - 게이트: 근거: 리포 참조 47건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `reviveInstr_docblock` — PAGE IIFE — reviveInstr 함수 직전 — reviveInstr이 미호출(dead)이므로 이 설명 주석도 참조 대상 없음. 함수 삭제 시 함께 정리 필요
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `todo_cache_bug_comment` — PAGE IIFE — WORK_TODO_API 변수 직전 — 해결된 구 버그 배경 설명. PR 메시지 수준 내용이 코드 본문에 남아 가독성 저해
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 전사_일정 — `3. 웰페리온 가이드/coo/check/전사_일정.html`
### B. 중복 설명 병합 (3건)
- [duplicate-text] `드롭다운-GM지시-2026-08-24` — CSS .fsel 블록 위 주석(line 19-20) ↔ JS renderChips() 위 한 줄 주석('// 부서·분류 = 드롭다운 2개 (GM 지시 2026-08-24)...') — 드롭다운 도입 배경(GM 지시 2026-08-24, 칩→드롭다운)이 CSS 주석과 JS 주석 두 곳에 동일하게 반복됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `달력클릭-dayPanel-GM지시-2026-08-12` — HTML #dayPanel div 위 인라인 주석 ↔ JS renderDayPanel() 직전 4줄 주석('// 날짜를 누르면 그날 할 일이 달력 바로 아래에 뜬다 (GM 지시 2026-08-12)...') — 날짜 클릭 시 패널 전개 배경(GM 지시 2026-08-12)이 HTML 주석과 JS 주석 두 곳에 반복 기술됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `CAL_MAX_LABELS-4개-근거-중복` — CSS .cal-cell 위 주석 '한 칸에 일정 이름 4줄...' · .cal-grid 위 주석 'minmax(0,1fr)...' / JS 'var CAL_MAX_LABELS=4' 주석 · renderCalendar 내 '2개까지만 보이고' 주석 — 4곳 — 달력 라벨 4개 표시(GM 지시 2026-08-24) 배경이 CSS 2곳+JS 2곳 합계 4개 주석에 중복 기술됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `배574` — uploadEvidence() — GAS '알 수 없는 action' 분기 내부 — 사용자에게 노출되는 alert 본문이 이미 지난 배포(배574)를 '배포 후 시도하라'고 안내 — 해당 배포 완료 후 오도성 메시지
  - 게이트: 근거: 리포 참조 15건(git grep 실측) — 확인 필요
- [stale-notice] `배990-미래형-주석` — JS var ERP_API_ON 선언 직전 3줄 주석 — 2026-09-04 작성 시 미래형('배포되는 순간')이었으나 오늘(2026-09-06) 기준 배990이 배포됐다면 현재 시제로 갱신 필요 — 독자가 '아직 배포 전'으로 오독할 수 있음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `--line` — HTML #dayPanel div 인라인 style 속성 — `--line` CSS 변수가 :root에 정의되지 않아 항상 #ddd 폴백 적용 — 파일 내 모든 다른 경계선은 `var(--border)` 사용, 다크모드 토큰 불일치
  - 게이트: 근거: 실측 실패(git grep 오류(rc=128): fatal: no pattern given) — 확인 필요
### D. 장황 단순화 (10건)
- [verbose-block] `배798-D0버그-주석블록` — statusOf() 함수 직전 5줄 주석 — 수정 완료된 버그 원인을 5줄로 상술 — 함수 내 today0 계산식(new Date(...).getTime())이 의도를 이미 드러냄
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `손소독제-done판정-주석블록` — statusOf() 내 done 판정 if문 직전 6줄 주석 — 해결된 사고 경위를 6줄 산문으로 기술 — done 판정 조건식 자체가 로직을 충분히 설명
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `배783-SERVER_REV-주석블록` — var SERVER_REV='' 선언 직전 5줄 주석 — 동시 저장 충돌 방지 배경을 5줄 서술 — SERVER_REV 변수명+saveToServer stale-rev 처리 코드가 의도를 이미 드러냄
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `isPastOneOff-접힘-주석블록` — var _pastOpen=false 선언 직전 4줄 주석 — isPastOneOff 동작 원칙을 4줄 서술 — 함수명과 statusOf().k 조건식이 이미 의도를 표현
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [dead-markup] `sitem-renderTiles-삭제-주석` — var _pastOpen=false 선언 블록 첫 머리 2줄 주석 — 삭제된 JS 함수(sitem·renderTiles) 자리의 묘비 주석 — 함수 자체가 없어 가리키는 코드가 존재하지 않음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [dead-markup] `CSS-summary-삭제-주석` — CSS .title-row 블록 직전(line 29) — 삭제된 CSS 블록 자리에 남겨진 묘비 주석 — 삭제 대상 코드가 이미 없어 정보 가치 없음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `타일삭제-HTML-주석블록` — HTML #draftBanner div 아래 / .calwrap div 위 빈 줄 — 삭제 완료된 타일에 대한 배경 설명 — 타일 마크업이 없어 잔류 주석이 가리키는 DOM이 존재하지 않음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `embed-ERP링크-CSS-주석블록` — CSS body.embed .sheet-links a.sheet-link:not(.hlink-add) 선택자 직전 — CSS :not(.hlink-add) 선택자가 의도를 충분히 표현 — 4줄 배경 설명은 과잉
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `h1-calNav-배치-HTML-주석` — HTML h1.title-row 직전 3줄 주석 — 이미 실현된 UI 배치 변경 경위를 3줄로 설명 — 마크업 위치 자체가 이미 자명
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `sub-범례병합-HTML-주석` — HTML p.sub 직전 3줄 주석 — 안내 문구 개편 배경을 3줄로 설명 — 현재 p.sub 문구가 내용을 담고 있어 이력 설명 불필요
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 업무 현황 SSOT — `3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] `deptHeadFor` — JS Constants 섹션 — OWNER_COLORS 아래 CAT_DEPT_HEAD 선언 — 주석에 '카테고리 자동 부서장 삽입 폐지 (2026-06-17 COO A)' 명시. renderTaskCard 결재선 계산은 이미 _MID 배열 직접 검색으로 대체돼 deptHeadFor() 호출부 0.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 11건(git grep 실측) — 확인 필요
- [js-function] `PLAN_TEMPLATE` — JS 마커 상수 블록 — REJECT_MARK 선언 직후 — 파일 전체에서 PLAN_TEMPLATE를 참조하는 코드 없음. 기획안 서식은 buildDocTemplate('plan')이 직접 HTML로 생성하며 이 상수를 쓰지 않음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [dead-markup] `updateHeaderSub` — updateHeaderSub() 함수 내부 — return; 문 직후 5줄 — 함수 첫 실행문이 return;이라 이하 5줄은 절대 실행 불가. 주석 '날짜|담당자 덮어쓰기 중단'으로 의도적 비활성화 확인.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [css-class] `date-picker-modal` — CSS — Date Picker Modal 섹션 — .date-picker-modal 클래스가 HTML 정적 마크업과 openDateRangePicker() JS 어디에도 부여되지 않음. 동 함수는 overlay에 'modal-overlay show'만 적용하고 너비는 인라인 style="max-width:320px;"로 이미 처리됨.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — renderQeval 내 헤더 2장 주석 vs renderTodoTable 내 헤더 2장 주석 — '헤더 2장을 맨 앞에 둔다 — 그리드 자동배치가 1장은 좌측열 맨 위, 1장은 우측열 맨 위에 앉혀 두 열 모두 … 칼럼 라벨이 보이게 한다(2026-08-24 표시 개편).' 패턴 설명이 두 렌더 함수에 거의 동일 문장으로 반복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (4건)
- [verbose-block] `routeApproval` — routeApproval() 함수 전체 — 9개 switch case 전부 ['GM']을 반환하고, 계산한 지역변수 amt가 어떤 조건에도 쓰이지 않음. return BUDGET_CATEGORIES.includes(category) ? ['GM'] : [] 한 줄로 대체 가능.
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — IIFE 최상단 quantEvalCompute 직전 — /* ══ 실시간 평가점수 — 허브(chro/hub/index.html) 평가탭 「업무 정량평가」 … 2026-09-01 매니저 지시] … */ 블록 — 산식 설명(총점·볼륨·품질 축 가중치)과 정체 판정 규칙 교체 이력이 합쳐져 30줄 이상 인라인 주석을 이룸; 이력 내용은 커밋 메시지 또는 외부 문서가 적절하고 코드 탐색을 심각하게 방해
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — qevDecodeDateScore 함수 본문 첫 주석 블록 — /* 규모점수 열의 사후 지연 "날짜서식 오염" 방어 정규화(2026-08-24 … A-12 대조표(2점/3점/5점) … */ — 함수 선언 직후 — A-12 대조표·실측 13건·보정 없이 raw 날짜 성분 일치 판정 경위 등 8줄 진단 이력이 3줄짜리 로직 본문보다 길어 가독성 역전
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — renderTodoTable 내 ymd 래퍼 함수 내부 주석 — // 8/21 KST 환산 함수(kstDateStr)로 통일(2026-08-24 A-12 진단 인계) … 손대지 않는다. — kstDateStr 교체 배경을 6줄로 서술; 래퍼 함수 본문(return kstDateStr(v); 1줄)보다 주석이 압도적으로 길어 실무 가독성 저해
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 결재 현황 SSOT — `3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] `getUser` — updateHeaderSub() 직후 — JS 상단부 — updateHeaderSub()의 첫 실행 구문이 return;이므로 getUser() 호출 라인이 절대 실행되지 않아 이 함수의 유일한 호출부가 죽은 코드임
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [css-class] `sheet-links` — CSS <style> — .header 섹션 이후 링크 스타일 그룹 — HTML 전체에 class="sheet-links" 요소가 없음. 헤더 링크 버튼은 .sheet-link(단수)를 사용하며 동적 생성 코드에서도 sheet-links(복수)는 생성하지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 52건(git grep 실측) — 확인 필요
- [dead-markup] `updateHeaderSub_unreachable_body` — updateHeaderSub() 함수 내부 — return; 이후 6줄 — updateHeaderSub()의 첫 구문이 return;이므로 이하 코드는 절대 실행되지 않음. 2026-05-30 GM 지시로 영구 return 삽입해 헤더 갱신 비활성화 확정
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [js-function] `setFilter` — setRoleFilter 아래 — 필터 함수 그룹 — 상태 필터 버튼(전체/진행중/결재완료/반려)이 2026-06-05 GM 지시로 삭제돼 HTML·동적 생성 코드 어디에서도 setFilter()를 호출하지 않음. 호출부 0
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `approval-card-rejected` — CSS <style> — .approval-card 상태 색 규칙 — renderApprovalCard에서 반려 카드는 항상 st-rejected와 rejected 두 클래스를 동시에 부여하므로 .approval-card.rejected는 .approval-card.st-rejected와 항상 동일 요소에 중복 적용됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `activeFilter_status_url_infra` — applyUrlParams() 내 if (p.get('f')) activeFilter = p.get('f'); 분기, buildShareUrl() 내 f 파라미터 설정, render() 내 activeFilter 결재상태 분기 로직 — 상태 필터 버튼 UI가 2026-06-05 삭제됐으나 ?f= URL 파라미터 읽기·쓰기 코드와 render() 내 결재완료/반려/미결 분기가 잔존. 칸반 뷰에서 activeFilter는 항상 '전체'로만 동작
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `render_listview_fallback` — render() 함수 내 — if (currentView === 'calendar') { ... return; } 블록 이후 html 변수 조립 및 el.innerHTML = html; 까지 전체 블록 — currentView는 'kanban'과 'calendar'만 가질 수 있어(초기화 IIFE·setView() 강제 폴백) 두 분기 각각 return 후 남은 리스트뷰 렌더 코드가 절대 실행되지 않음. 리스트 뷰는 2026-06-03 GM 확정으로 폐지
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 공지 템플릿 — `3. 웰페리온 가이드/coo/notice/notice_template.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] `ntool-img-btn` — <style> — ntool-fmt-bar 섹션 직후 두 줄 — 현재 이미지 삽입 버튼은 인라인 style을 가진 <label>로 대체됐고, 페이지 HTML·JS 어디에도 class="ntool-img-btn" 참조가 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [css-class] `ntool-fmt-bar .sep` — <style> — .ntool-fmt-bar button:active 룰 직후 — v2.27 이후 fmt-bar 구분자가 .fmt-group 박스화로 대체됐고, .ntool-fmt-bar 안에 class="sep" 요소가 HTML에도 JS 동적 생성에도 존재하지 않음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] `title-version` — <head> <title> 태그 — topbar <h1>은 v2.2인데 <title>은 v2.1로 한 버전 뒤처져 있음(브라우저 탭·북마크에 stale 버전 노출)
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요
- [stale-notice] `ntFmtBoldLine` — <script> 2번째 블록 — window.ntFmtHr 정의 직후 — 삭제된 함수의 묘비 주석이며 함수 본체가 코드 어디에도 없음; 참조·호출부 0건
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [stale-notice] `md-parser-tombstone` — <script> 2번째 블록 — ntFmtBoldLine 묘비 주석 직후, ntUpdatePreview 함수 직전 — 제거된 마크다운 파서 전체에 대한 묘비 주석; 빈 줄 2개와 함께 잔류해 코드 흐름을 끊음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `imgHtml` — <script> 2번째 블록 — ntCollectData 함수 내부 — imgHtml은 항상 빈 문자열로 고정되어 ntBuildPageHtml 5번째 인자로 전달되지만 '<div class="body">'+bodyHtml+imgHtml 연결에서 아무 영향을 주지 않음; 파라미터 자체가 폐기됐음을 주석이 인정하면서도 코드에 잔류
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [verbose-block] `css-gm-task-comment` — <style> — .cat-card 룰셋 직전 — GM 지시 날짜와 태스크 배경을 CSS에 기록; 설계 이유는 git 커밋 메시지에 귀속해야 하며 CSS 내 존치 시 유지보수 혼란 유발
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 메인가이드 O1(운영통합체계) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### B. 중복 설명 병합 (3건)
- [duplicate-text] `common-promises` — O1 공통탭 > 📌 우리의 약속 <details> toggle-body > div#common-promises 안 h3 — <details><summary>가 이미 '📌 우리의 약속 — AI·실무진이 다같이 지키는 것'을 노출하므로 펼쳤을 때 동일 아이콘·제목이 summary와 inner h3 두 곳에 동시 표시됨
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [duplicate-text] `common-incidents` — O1 공통탭 > 🛡️ 재발방지 현황 <details> toggle-body > div#common-incidents 안 h3 — <details><summary>가 이미 '🛡️ 재발방지 현황 — 같은 실수 두 번 안 나게 + 공식 값'을 노출하므로 펼쳤을 때 동일 제목 중복 표시
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [duplicate-text] `OPS_STAFF` — O1 article > 두 번째 <script> 블록 상단 (2/3/4층 전용 IIFE) — 첫 번째 IIFE(loadHub)에서 이미 동일한 값으로 선언하면서 바로 옆 주석에 '약속 L01 — 값 복제 금지'라고 명시했음에도 다음 script 블록 IIFE에서 같은 값으로 재선언. 한 쪽 수정 시 다른 쪽이 틀어지는 유지보수 위험
  - 게이트: 근거: 리포 참조 19건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (7건)
- [stale-notice] `완료_단일정의_위임잘림_orphan` — O1 공통탭 > 🌉 완료·연속성·끊김 방어 <details> toggle-body, 🗂️ 할 일 정리 h3 바로 위 — section 시작·끝 주석 사이에 콘텐츠가 전혀 없음 — 해당 섹션 본문은 wellperion-boot 스킬로 이관됐고 빈 마커 쌍만 고아로 남아 있음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `bridge_move_changelog_comment` — O1 공통탭 > 🌉 완료·연속성·끊김 방어 <details> toggle-body 최상단, 일하는 규칙 3종 h3 직전 — 이 주석 바로 아래 callout이 이미 '정본 = wellperion-boot 스킬 §8'라고 안내하므로 주석의 changelog 내용이 callout과 완전히 중복 — 이관 완료된 사건을 설명하는 옛 메모
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `report_format_deletion_comment` — O1 공통탭 > 📋 보고·업무 흐름 <details> toggle-body 최상단, 🧭 업무 수행 파이프라인 h3 직전 — 삭제 대상은 이미 제거됐고 교체 이유를 설명하는 주석만 남음 — 바로 아래 쿵짝표 섹션이 신규 표준을 직접 보여주므로 changelog 주석의 가치 소멸
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `boot6step_deletion_comment` — O1 공통탭 > 🔌 AI 부팅·조직도 <details> toggle-body 상단, callout div 직전 — 바로 아래 callout이 '단계 상세 정본 = wellperion-boot 스킬'을 이미 안내하므로 삭제 이유 주석이 callout 내용과 중복되는 changelog
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `evalEl` — O1 article > 두 번째 <script> 블록 > loadMonth 함수 > evalEl.innerHTML 할당 — 2026-08-27 측정값을 정적으로 하드코딩한 채 2026-09-06 현재까지 갱신 없음. '(정적값)' 레이블 자체가 수동 갱신 필요를 선언하나 갱신이 이뤄지지 않아 10일 전 수치를 현재값처럼 표시 중
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [stale-notice] `gm1RenderAlertSignal` — O1 GM1 초기화 블록 — gm1FetchSsot() 호출 직후 — 제거 완료된 두 함수(gm1RenderAlertSignal·gm1RenderCruiseSummary)의 사후 설명 주석 — 코드·DOM 모두 없으므로 잔존 이력 노이즈
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [stale-notice] `위임큐위젯제거` — // ── /GM1 통합 태스크 시스템 ── 종료 직후, KPI 대시보드 v1 섹션 시작 전 — 이미 완료된 위젯 삭제를 기록한 섹션 구분 주석 — 위젯 자체가 없으므로 이 메모도 불필요한 역사 기록
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] `kungjjak_history_comment` — O1 공통탭 > 📋 보고·업무 흐름 <details> > 🥁 쿵짝표 h3 직전 — 6줄 주석이 구 포맷 교체 사유와 실측 일화를 서술 — 실무 독자가 운영 중 얻는 가치 없음; 현행 쿵짝표가 바로 아래 있어 충분
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `raw_vs_gas_comment` — O1 매트릭스 <script> 블록 내 mxReadJson 함수 직전 — 5줄 JS 주석이 해소된 GAS-먼저 성능 이슈를 장황하게 설명 — '저장은 GAS 유지' 1줄만 남겨도 핵심 정보 충분
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — O1 article > '이 모듈은 · COO 운영 허브' 소개 박스 하단 — border-top dashed flex 컨테이너 (🔢·🚫·🔗 세 줄) — 🔢 큰 숫자+작은 경고 / 🚫 가짜 숫자 없음 / 🔗 카드=문 세 줄은 UI 설계 철학 해설로, 바로 위 두 단락(계획→현황→접수→개선 흐름 및 숫자로 뜬다는 설명)이 이미 충분한 오리엔테이션을 제공. 매일 화면을 쓰는 실무진에게 반복 노출되는 부연 설명
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 메인가이드 O2(공지) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] `toggleInc` — 재발방지 현황 섹션 incidents IIFE 내 선언부 — 함수가 정의되어 있으나 실제 onclick 핸들러는 동일 로직의 인라인 익명 IIFE로 구현되어 있어 toggleInc 호출부 0
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### B. 중복 설명 병합 (2건)
- [duplicate-text] `common-promises` — 우리의 약속 details toggle 내 id=common-promises 블록 첫 번째 자식 h3 — 부모 details의 summary가 이미 '우리의 약속 — AI·실무진이 다같이 지키는 것'을 표시하며, 토글을 열면 내부 h3가 동일 제목을 재출력해 제목이 두 번 보임
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [duplicate-text] `common-incidents` — 재발방지 현황 details toggle 내 id=common-incidents 블록 첫 번째 자식 h3 — 부모 details summary '재발방지 현황 — 같은 실수 두 번 안 나게 + 공식 값'과 내부 h3가 동일 문구 반복 — 토글 열면 제목 중복 표시
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (6건)
- [stale-notice] `쿵짝표_교체이력_주석` — 보고·업무 흐름 details toggle 내 쿵짝표 h3 직전 HTML 주석 — 2026-08-08 교체 조치 이미 완료. '시토가 헛답한 뿌리' 등 해소된 사고 경위를 HTML 주석에 상세 기술 — 조치 후 가이드 운영에 기여 없음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `브릿지_위임잘림_이동주석` — 완료·연속성·끊김 방어 details toggle 내 HTML 주석 — 2026-08-08 wellperion-boot 스킬 §8 이전 완료. 이전 경위 설명 주석만 남아 현행 가이드 운영에 기여 없음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `완료의단일정의_빈섹션마커` — 완료·연속성·끊김 방어 details toggle 내 인접 빈 섹션 마커 쌍 — 개폐 마커 사이에 실제 내용이 전혀 없음 — 두 섹션(완료의 단일 정의·위임 잘림 방어)의 본문이 모두 제거되어 껍데기 마커만 잔존
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `CPO_DoNot_삭제주석` — CPO 탭 패널 내 HTML 주석 — 2026-06-05 삭제 조치 완료. 현재 해당 위치에 내용이 없으며 삭제 경위 주석만 잔존
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `에이전트키트_이동안내` — 결과물 3대 기준 섹션 하단 p태그 — 이전이 이미 완료되어 T1 탭에 실재. '이동했다'는 포인터만 남아 있어 현재 안내 역할 종료
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `source-div-version` — O2 섹션 최하단 source div — v1.0·v1.1(2026-04-24) 버전 표기가 이후 CBO 신설(2026-09-02)·쿵짝표 교체(2026-08-08) 등 대규모 개정을 미반영. '관련 메모리 11건' 수도 현행과 불일치 가능성 높음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `common-promises-description` — id=common-promises 블록 내 설명 div (h3 직후) — JSON에서 로드된 약속 목록이 내용을 직접 전달하며, 섹션 제목이 '한 곳에서 다같이'의 의미를 이미 포함 — 설명 div 없이도 가이드 이해 무결함
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 메인가이드 O3(재등록) — `3. 웰페리온 가이드/wellperion_guide(main).html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] `gm1CalOpenDay` — gm1CalOpenDay 함수 — info.innerHTML 의 <strong> 스타일 문자열 조합 부분 — isDone 참·거짓 두 분기 모두 빈 문자열('')을 반환하는 항등 삼항 — 실행 결과에 전혀 영향 없는 무동작 표현식
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] `common-promises-heading` — details.toggle '우리의 약속' > .toggle-body > #common-promises 상단 h3+설명 div — details summary에 이미 '📌 우리의 약속 — AI·실무진이 다같이 지키는 것'이 렌더되므로, 토글을 열면 h3가 같은 제목을 한 번 더 반복함
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [duplicate-text] `common-incidents-heading` — details.toggle '재발방지 현황' > .toggle-body > #common-incidents 상단 h3 — details summary에 이미 '🛡️ 재발방지 현황 — 같은 실수 두 번 안 나게 + 공식 값'이 노출됨; 토글 열면 h3가 제목 반복
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `source-div-O3` — O3 article 최하단 .source div (KPI 스크립트 다음, article 닫히기 직전) — v1.0·v1.1 버전명과 (2026-04-24) 날짜가 최신 업데이트 이력(2026-08-08 ~ 2026-09-02)과 괴리; 'g4 흡수'·'메모리 11건 cross-link' 등 내부 개발 이력 메모가 실무진 화면에 그대로 노출됨
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (10건)
- [verbose-block] `comment-부팅6단계표삭제` — details#con-ai-boot .toggle-body 내 callout 앞 주석 — 삭제 완료된 콘텐츠의 이유를 서술하는 개발 변경 이력 주석; 변경이 이미 반영됐으므로 불필요한 소스 노이즈
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `comment-보고표형식삭제` — details '보고·업무 흐름' .toggle-body 내 h3 '업무 수행 파이프라인' 바로 위 — 폐기 완료된 보고 규칙에 대한 이유 설명 개발 주석; 변경 반영 후 불필요
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `comment-쿵짝표교체이력` — details '보고·업무 흐름' .toggle-body 내 h3 '🥁 쿵짝표 — GM 문답·작업 보고 표준' 바로 위 — 교체 이유·사고 경위를 5줄 이상 서술한 변경 이력 주석; 변경 완료 후 소스 가독성 저해
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `comment-브릿지완료위임이동` — details '완료·연속성·끊김 방어' .toggle-body 오프닝 주석 — 스킬 이동 완료 후 남은 이유 설명 개발 주석; 이동이 반영된 이상 불필요
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [dead-markup] `comment-완료4요건단독마커` — details '완료·연속성·끊김 방어' .toggle-body 내 브릿지 주석 바로 다음 줄 — wellperion-boot 스킬로 이동된 '완료의 단일 정의' 섹션의 개방 마커만 홀로 남음; 대응 본문 없는 고아 마커
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [dead-markup] `comment-위임잘림방어클로즈` — details '완료·연속성·끊김 방어' .toggle-body 내 완료4요건 마커 다음 줄 — 대응하는 오프닝 섹션 없이 남은 고아 클로징 마커; 내용이 스킬로 이전돼 본체가 없음
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [dead-markup] `comment-작업사이클보고포맷클로즈` — details '보고·업무 흐름' .toggle-body 최하단 (쿵짝표 두 종류 섹션 뒤) — 현재 섹션 오프닝은 '쿵짝표 두 종류 구분'인데 클로징이 폐기된 구 섹션명('작업 사이클 보고 포맷')을 참조하는 불일치·고아 마커
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `FACILITY_RANGES_옛값` — home KPI 섹션 — fetchFacilityRanges 함수 직전 주석 블록 10줄 — GAS fcheck_ranges_get·계약서로 이관된 옛 하드코딩 수치를 10줄 주석으로 보관; 계약서 링크 한 줄로 충분하며 '사고 원인'이라 명시된 사본 수치가 장기 오독·실수 재발 위험 생성
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [verbose-block] `gm1RenderAlertSignal` — gm1 초기화 블록 — gm1RetrySSOTSync 호출 직후 3줄 묘비 주석 — 이미 제거된 두 함수(gm1RenderAlertSignal·gm1RenderCruiseSummary)의 존재를 설명하는 묘비 주석; 함수·대상 DOM 양쪽 모두 부재해 독자 혼란만 가중
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [verbose-block] `위임큐위젯제거` — GM1 통합 태스크 시스템 클로징 주석 직후 단독 줄 — 위젯 제거 사실만 기록한 묘비 주석 한 줄; 실행 코드·DOM 없이 역사 기록 용도만이며 커밋 로그로 충분
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요

## 메인가이드 O4 — `3. 웰페리온 가이드/wellperion_guide(main).html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 우리의 약속 <details> 토글 내부 — div#common-promises 상단 <h3> 및 설명 단락 — toggle <summary>에 '📌 우리의 약속 — AI·실무진이 다같이 지키는 것'이 이미 표시되나, 토글 展개 시 내부에 동일 제목의 <h3>과 '우리가 한 곳에서 다같이 보고 지키는 약속입니다. 새 약속이 생기면 여기 모입니다.' 설명 단락이 또 나타나 동일 정보가 2중 노출됨
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 재발방지 현황 <details> 토글 내부 — div#common-incidents 상단 <h3> — toggle <summary>에 '🛡️ 재발방지 현황 — 같은 실수 두 번 안 나게 + 공식 값'이 이미 표시되나, 토글 展개 시 내부에 동일 제목의 <h3>이 또 나타나 동일 정보 2중 노출
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (5건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — CTO 역할 원칙(메모리 단일화) 표 — '대기 보고 포맷' 행 괄호 설명 — '대기 보고 포맷(3섹션 + 🔴 GM 결정·5필드)' 괄호 내 '5필드' 표현은 2026-07-22 GM 확정으로 폐기된 옛 보고 포맷을 가리키며, 같은 O4 '📋 보고·업무 흐름' 토글 내 삭제 주석에서 이미 폐기 완료됐다고 명시된 규칙과 충돌
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 전 C-Level 통합 원칙 ⑨ 토큰 라우팅 매트릭스 — <p> 단락 'Fable = 시험 운용 중' — 'Fable = 시험 운용 중(GM go 2026-07-25)' 문구가 현재 날짜 2026-09-06 기준 6주 이상 경과; '확대·축소 판단 전까지 이 표가 현행 기준이다'는 조건 문구가 시험이 아직 진행 중인 것처럼 오인시킬 수 있어 시제 불일치 가능성
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — O4 탭 패널 최하단 <div class='source'> — 'AI C-Level 협업 매뉴얼 v1.0 + C-Level 실무 가이드라인 v1.1 (2026-04-24) 통합'이라는 버전 표기가 현재 페이지에 반영된 2026-08~09 변경분(쿵짝표·CBO 신규 탭 등)과 4개월 이상 불일치
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — // ── /GM1 통합 태스크 시스템 종료 직후 단독 주석 1줄 — 위젯 삭제 완료를 기록한 묘비 주석. 삭제 대상 코드가 이미 없어 주석만 잔류하며 읽는 측 혼란 유발.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `FACILITY_RANGES_옛값` — buildRangesMap 함수 직전 — FACILITY_RANGES 이관 설명 주석 블록 내 — 2026-07-20 GAS fcheck_ranges_get으로 이관 완료된 옛 하드코딩 기준값. 본문 주석이 직접 '사고 원인'으로 명시. 참고 목적이라 표기됐으나 오해·재사용 위험 잔존.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — O4 전역 HTML 주석 8건 — AI 부팅 토글 내 '부팅 6단계 표 삭제' 주석, 보고·업무 흐름 토글 내 '5필드 규칙 삭제' 및 '쿵짝표 교체 연유' 주석, 완료·연속성 토글 내 '브릿지 스킬 이전' 및 '완료 단일정의 마커' 주석, CPO 탭 'Do/Don't 삭제' 주석, COO 탭 '시우 정체성 확정 메타' 주석, CTO 탭 '시토 헌장 확정 메타' 주석 — 이미 완료된 삭제·이전·구조 변경의 배경을 HTML 주석에 장황하게 기술; 행동은 이행됐고 git log가 이력을 보존하므로 소스 주석이 현재 상태 이해에 추가로 기여하는 정보 없음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — gm1FetchSsot() 호출 직후, setTimeout(gm1RetrySSOTSync) 앞 3줄 주석 — 제거된 두 함수(gm1RenderAlertSignal·gm1RenderCruiseSummary)의 삭제 경위를 설명하는 묘비 주석 3줄. 코드가 없으므로 코드 맥락 역할을 하지 않으며 커밋/PR 설명에 있어야 할 내용.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 문의회원 — `3. 웰페리온 가이드/cpo/member/membership.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [js-function] `_oaMaskPhone` — _oaOwnerOptionsForSport 아래, _oaRender 위 — 코드 내 주석 '실측 결과 이 파일에서 _oaMaskPhone 호출은 여기 한 곳뿐이었다'가 유일 호출부를 명시하며, 그 호출부(_mregRender)가 마스킹 해제(2026-08-05) 후 esc(m.phone)으로 교체돼 호출부 0이 됨.
  - 게이트: 소비자 7건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [dead-markup] `_verifyFetchActiveFull` — _verifyFetchActiveFull 함수 본문 끝, 내부 bare block {} 닫힘(}) 직후 — 함수 전체가 bare block {}로 감싸이고 그 안의 fetch promise 체인이 항상 return하므로 bare block 닫힘 뒤의 이 return문은 어떤 실행 경로로도 도달 불가한 죽은 코드; 같은 패턴이 _verifyFetchList 마지막 return(조건 분기 폴백)과 달리 여기서는 분기 없이 항상 내부 블록이 먼저 반환
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (4건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — HTML body — (1) pane-ownerAssign·pane-membershipReg 블록 직후, type-membership div 직전 / (2) #pane-active 상단 요약카드·holdStatusCard 주석 블록 사이 — "이탈방지 액션 모듈(⏰갱신임박·📉저이용)이 이탈관리 모달·오늘 할 일로 이관됐다, 여기 없음" 메시지가 같은 페이지 HTML 주석으로 두 곳에 반복됨. 장문(4줄, #cpoStatusBoard 삭제·카드 이관까지 포함)과 단문(2줄)이 동일 지시 사항(GM 2026-07-15)을 설명하며 핵심 문구 '여기 없음(중복 아님)'이 양쪽에 동일하게 등장.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] `newOnly=1` — _mdashComputeKpi 인라인 주석·_mdashRenderMonthlyReg 인라인 주석·_lessonComboMRegLoad 주석·_mdashSetPeriod 주석 등 4~5곳 — '서버가 newOnly=1로 신규만 반환하므로 클라이언트 재필터 불필요'라는 동일 사실이 서로 다른 함수 주석에 4~5회 반복 등장
  - 게이트: 근거: 리포 참조 50건(git grep 실측) — 확인 필요
- [duplicate-text] `_mregOwnerCell` — _mregOwnerCell 내 컨택 칸 주석 + _mregSaveContact 함수 내 주석 (+ _oaAppendContact docstring 포함 총 3곳) — 2026-08-12 GM 지적 '이어붙이기' 변경 경위(덮어쓰기 문제·동일 GM 인용구 '예전에 컨택 내용이 사라지는 경우는 말도 안 되지 않냐'·_oaAppendContact 통일 결정)가 _mregOwnerCell, _mregSaveContact 두 함수에서 거의 동일한 문장으로 반복 서술.
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [duplicate-text] `contactsPrev` — saveConsultModal(payload.contactsPrev 앞)·openContactModal(_ctModal.prevCount 앞)·_saveCell(payload.contactsPrev 앞) 세 곳 — contactsPrev의 불변식('서버가 쓰기 의도를 판별하는 기준값')을 세 함수에서 거의 동일 문장으로 각각 설명. _saveCell이 가장 범용 위치이므로 한 곳만 남기고 나머지 두 곳은 '// contactsPrev → _saveCell 주석 참고' 한 줄로 축약 가능.
  - 게이트: 근거: 리포 참조 21건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (9건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — HTML body 모달 영역 — #churnOverlay 닫힘 태그 직후, #lossReasonOverlay 시작 직전 단독 주석 블록 — 2026-07-22에 폐기·제거된 openHoldModal 및 member_hold_preview를 설명하는 사망 기록 주석. 실제 DOM 요소가 없고, 대체처(cpo/member/휴회접수.html / 회원관리 '휴회 접수 관리' 카드)는 코드베이스 다른 곳에서 확인 가능하므로 이 주석이 추가하는 운영 정보가 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `_lessonRosterFor` — _lessonRosterFor 함수 내 블록 주석 (함수 상단부) — 2026-07-27 실측에서 종목탭 경로가 '현재 통째로 무효(결과에 영향 0)'임이 확인됐지만 코드 수정 없이 경보 주석만 남아 있어 미해소 상태를 영구 선언하는 꼴
  - 게이트: 근거: 리포 참조 21건(git grep 실측) — 확인 필요
- [stale-notice] `USE_GVIZ` — USE_GVIZ 변수 선언 줄 인라인 주석 — INC-013 버그가 '라이브 실증'으로 이미 해소됐음을 밝히면서도 rowIndex 수치·복구 경로 등 인시던트 경위 전문이 변수 한 줄에 끝까지 붙어 있음 — 이미 해소된 경보 문구
  - 게이트: 근거: 리포 참조 50건(git grep 실측) — 확인 필요
- [stale-notice] `showWaitMembers` — _activeWireSearch 함수 직전 주석 블록 — 이미 삭제된 showWaitMembers의 제거 경위를 설명하는 사후 메모가 내용상 무관한 _activeWireSearch 직전에 잔류. 설명 대상 함수는 파일에 없고 참조도 없음.
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `_mregProgLabel` — _mregRender 함수 내 _mregProgLabel 호출부 위 주석 — '(2026-08-04 원 사유, 참고용)' 2줄은 번복된 결정의 과거 이유를 보존 중. 현재 코드는 _mregProgLabel 축약값을 사용하며 주석이 설명하는 '원문 그대로' 방침은 현재 동작과 정반대.
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [stale-notice] `_renderHoldIntake` — _renderHoldIntake 함수 내 var intake = _holdIntake || [] 바로 위 — 배146에서 테스트 접수 2건 시트 물리 삭제 완료, 배174에서 화면 필터도 이미 제거됨. 두 조치 모두 완료된 완료 이력 주석만 남아 있어 실무진에게 현재 기준 무의미한 안내가 됨.
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [stale-notice] `_loadHoldIntake` — _loadHoldIntake 함수 정의 바로 위 — 주석 자체가 '닫힌 루프·진입점 없음·이번엔 안 지웠다'라고 기술. 해소 계획 없이 미결로 방치된 stale TODO. 지목된 함수군의 외부 진입점 유무는 다른 조각에서 확인 필요.
  - 게이트: 근거: 리포 참조 24건(git grep 실측) — 확인 필요
- [js-function] `_activateCellMemo` — _activateCellSelect 아래 / _activateCellInquiry 위 — buildDbRow에서 메모 열(td) 생성 코드 없음. buildNewInputRow는 makeInput('memo')를 직접 사용. 이 조각 전체에서 _activateCellMemo 호출부 없음. 메모 데이터는 payload(_saveCell)에 살아있으나 셀 활성화 진입점이 보이지 않음.
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [stale-notice] `dismissBeginnerBanner` — esc() 함수 정의 아래, 첫 번째 </script> 태그 바로 위 — #beginnerBanner 마크업과 dismissBeginnerBanner 함수가 2026-07-15에 이미 삭제(net-zero) 완료됐고 localStorage 키도 아무 코드가 읽지 않음을 주석 스스로 밝힘 — 완료된 삭제 작업의 메모가 이미 해소된 낡은 안내로 잔류
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### D. 장황 단순화 (9건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — CSS — color-scheme 방어 규칙 세 블록 (.contact-by-select option / .cell-select option / .oa-owner-sel + .mreg-owner-sel option) — 세 규칙이 각각 color:var(--text);background-color:var(--paper)를 선언하지만, 바로 뒤에 등장하는 'select, select option { color:var(--text); background-color:var(--paper); }' 전수 방어 규칙과 동일한 값을 선언한다. 특이도 차이가 있어도 선언 값이 동일하므로 렌더 결과가 같다 — 세 규칙은 순수 중복으로 실무진이 같은 패턴을 반복 읽어야 하는 인지 부하를 추가함.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — HTML body — #memberTabNav 닫힘 태그 직후 「참고(정직 기록, 배754)」 HTML 주석 블록 — 제거된 dInqMonth·dTourMon 값이 왜 없어졌는지와 부분적 대체 조회 방법을 4줄로 설명하는 이력 주석. 현재 동작하지 않는 값의 배경 기록으로, 코드 운영·화면 기능에 기여하지 않음. '월간 예약(dTourMon)은 표면 노출처가 없어졌음(정직 기록)'처럼 손실을 인정하는 문구를 포함해 실무 가독성을 저해.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <head> 첫 번째 <script> 블록 — _refreshDiskCache IIFE 내부 블록 주석 하단 ▸실증 방법(재현하려면 그대로 따라 한다 · 표식 CACHEPROOF-20260824) ①~④ 4단계 절차 — 함수 목적·한계 설명(배경 재요청, 첫 진입 시 구 화면 가능성)은 유효하지만, ①브라우저 캐시 유지 진입 ②새 배포 업로드 ③재진입 확인 ④재입 확인 등 QA 재현 절차 9줄은 프로덕션 소스에 내장하기에 지나치다. 커밋 메시지나 별도 문서(CACHEPROOF-20260824)로 이동해도 함수 동작에 영향 없음.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] `_lessonComboMRegLoad` — _lessonComboMRegLoad 함수 직전 주석 블록 전체 — 4줄짜리 함수(_cpoStats 읽어 두 필드에 textContent 세팅)에 변경 이력 3회차(배361·배349·2026-08-10 정리)가 모두 누적돼 주석이 함수 본문의 3배 이상 길어짐
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [verbose-block] `_gasPrewarm` — _gasPrewarm IIFE 직전 블록 주석 전체 — GAS 서버 예열+선입수 목적은 한두 줄로 요약 가능하나 실측 타이밍 수치·레이스 가드 설명·ponytail 메타까지 10줄 이상 쌓여 있음
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [verbose-block] `LESSON_INSTRUCTOR_ROSTER` — LESSON_INSTRUCTOR_ROSTER 변수 선언 직전 주석 5줄 — '이 변수가 정본'이라는 한 줄 사실을 피드백 번호·삭제된 JSON 경위·약속 L21 인용·아쿠아 누락 이유까지 5줄로 풀어 설명하고 있음
  - 게이트: 근거: 리포 참조 23건(git grep 실측) — 확인 필요
- [verbose-block] `_activeCacheSelfTest` — _activeCacheSave/_activeCacheLoad 함수 블록 아래 — 콘솔에서만 수동 호출하는 개발용 자체점검 함수(약 25줄). 프로덕션 코드 경로에서 호출부 없음. 실무진 가독성에 기여하지 않음.
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [verbose-block] `_completenessSelfTest` — _renderActiveCompleteness 함수 아래 — 콘솔에서만 수동 호출하는 개발용 자체점검 함수(약 30줄). _activeCacheSelfTest와 동일 패턴. 프로덕션 실행 경로 없음.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [verbose-block] `NARROW_COL_WIDTHS` — NARROW_COL_WIDTHS 객체 리터럴 끝 5개 항목 — 5개 키가 ALWAYS_HIDE_COLS 멤버이기도 해 _activeDisplayCols()가 displayCols에서 항상 사전 제거한다. _activeRowHtml의 narrowW = NARROW_COL_WIDTHS[h] 룩업이 이 키에 도달하는 경로가 없는 dead 설정.
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요

## 강습회원관리 — `3. 웰페리온 가이드/cpo/member/강습회원관리.html`
- ⚠️ 감사 실패: 파일 읽기 실패: [Errno 2] No such file or directory: 'C:\\Users\\jjky0\\welperion-automation\\3. 웰페리온 가이드/cpo/member/강습회원관리.html'

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `section-divider` — <style> 섹션 구분선 블록 — .card/.info-box 정의 직전 — HTML 전체와 JS 동적 렌더 함수(renderCard·_polCard·renderCards·renderPolicyTable) 모두에서 class="section-divider" 사용처 0건
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `badge v1.0` — 헤더 h1 — 페이지 최상단 — 2026-07~09 사이 멤버십 등급·법인 정책·강습 유효기간·요금 정책 다수 GM 확정·변경됐으나 버전 배지는 v1.0 그대로 동결
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `staffFeedbackLink-todo` — header-feedback-slot — feedback-cta-btn 아래 HTML 주석 — GM 지시(2026-07-29)로 피드백 모음 페이지 링크를 삽입하라고 명시했지만 실제 <a> 엘리먼트 없이 주석만 잔류 — 미구현 TODO 주석
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (5건)
- [verbose-block] `_todoPost` — _todoPost 함수 정의 직전 블록 주석 — 해소된 구버전 버그(INC-013·INC-014) 경위 설명 6줄 — 현재 코드 동작 이해에 불필요하며 커밋/PR 메시지에 속하는 역사 서술
  - 게이트: 근거: 리포 참조 9건(git grep 실측) — 확인 필요
- [verbose-block] `savePlan-legacy-comment` — savePlan 함수 정의 직전 블록 주석 — 제거된 구현의 실패 방식 3줄 — 현재 함수 시그니처와 반환값으로 이미 자명한 내용
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `deletePlan-legacy-comment` — deletePlan 함수 내 _todoPost 호출 직전 인라인 주석 — 구버전 동작 비교 2줄 — 현재 코드(_todoPost 응답 분기)가 명백하므로 역사 서술 잉여
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `submitPlan-legacy-comment` — submitPlan 함수 내 savePlan().then 직전 인라인 주석 — 해소된 이전 패턴 비교 2줄 — 현재 로직(savePlan 결과 확인 후 closeModal)으로 자명하며 커밋 메시지 내용
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `pol-card-hack-comment` — <style> 내 .pol-card table 룰 직전 블록 주석 — 이미 제거된 width:100vw hack의 삭제 경위 3줄 — 해당 hack이 코드에 없으므로 역사 주석만 잔류
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
### A. 죽은 코드(자동삭제 대상) (9건)
- [css-class] `m1-dash .header h1` — <style> 블록 — .header 그룹 내 h1 선택자 — 헤더 마크업은 <h3>만 사용. <h1>이 .header 안에 없어 이 규칙이 적용되는 요소가 없음. 바로 아래 .header h3가 실제 사용 선택자
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `chip-row` — <style> 블록 — .chip-row 선택자 (본문 CSS 1회, print에는 없음) — 채널 아이콘 렌더는 chanIconHtml()이 .chan-icon 클래스를 사용. 페이지 내 .chip-row 클래스를 생성하는 JS·HTML 없음
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `chip` — <style> 블록 — .chip 본문 CSS 선택자 — .chan-icon이 동일 역할을 수행하며, 이 페이지 HTML·JS 어디에도 class="chip"을 생성하지 않음
  - 게이트: 소비자 1244건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `chip` — <style> 블록 — .chip svg 본문 CSS 선택자 — .chip 자체가 미사용이므로 하위 svg 선택자도 적용되는 요소 없음
  - 게이트: 소비자 1244건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `chip` — @media print 블록 — .chip 인쇄 CSS — .chip 클래스가 페이지 전체에서 미사용이라 인쇄 규칙도 적용되지 않음
  - 게이트: 소비자 1244건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `chip` — @media print 블록 — .chip svg 인쇄 CSS — .chip 미사용과 동일 근거
  - 게이트: 소비자 1244건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `post-metric` — <style> 블록 — .post-metric 본문 CSS — renderChannelPerf·renderSummary·renderAllChannels 등 모든 렌더 함수의 innerHTML에 .post-metric 클래스 생성이 없음
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `post-metric` — <style> 블록 — .post-metric b 본문 CSS — .post-metric 자체가 미사용이므로 하위 b 선택자도 적용되는 요소 없음
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `post-metric` — @media print 블록 — .post-metric 인쇄 CSS — .post-metric 클래스가 페이지 전체에서 미사용이라 인쇄 규칙도 적용되지 않음
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `reaction-scorecard-wrap` — 편별 반응 성적표 섹션 — 정적 measure-pending 박스 <strong> 및 JS 렌더 각주(measure-pending) 양쪽 — 'S2 AI-CMO 탭 반응 루프 참고(재서술 안 함)' 포인터가 같은 섹션에 두 번 노출됨. C 항목으로 정적 박스를 갱신하면 자연 해소
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `measure-pending` — 편별 반응 성적표 섹션 — #reaction-scorecard-wrap 바로 위 정적 HTML — 관찰 기간 2026-07-20~2026-08-20이 오늘(2026-09-06) 기준 17일 전 종료됨. '관찰 모드 · 알림 미발송' 안내가 이미 해소된 경고 문구로 시제 불일치
  - 게이트: 근거: 리포 참조 25건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `renderContentAttribution` — renderContentAttribution() 함수 — '콘텐츠(게시물) 단위 귀속' 섹션 JS 렌더 HTML — 원인·조치·구조적 한계를 3개 div에 걸쳐 700자+ 서술. 2026-07-31 배포 후 37일 경과 시점에 배경 서술 비중이 판단치보다 압도적으로 커 실무 스캔 가독성 저하. 핵심 3줄(배포완료·귀속가능채널·귀속불가채널)로 압축 가능
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `month-select-wrap` — CSS 화면용 월 선택기 섹션 (/* 화면용 월 선택기 (인쇄 숨김) */ 블록) — HTML의 월 선택기 래퍼는 class="tb-month" 사용 — .month-select-wrap은 파일 내 어느 HTML 요소에도 적용되지 않음
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-lbl` — CSS 화면용 월 선택기 섹션 — HTML의 '보고 월' 레이블은 class="lbl"(tb-month 자식) 사용 — .month-select-lbl은 파일 내 어느 요소에도 미적용
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-wrap` — CSS 화면용 월 선택기 섹션 마지막 줄 (인라인 @media print) — .month-select-wrap이 HTML에 존재하지 않아 이 인쇄 숨김 규칙도 적용 대상 없음; 툴바 전체가 이미 .toolbar{display:none!important}로 숨겨져 이중으로 무효
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `TOKEN_ENFORCE` — JS 상수 섹션 (const GAS_URL 선언 직후) — 2026-06-18에 이미 폐기된 TOKEN_ENFORCE 기능을 언급하는 과거 상태 주석; 현재 코드와 무관한 역사적 메모
  - 게이트: 근거: 리포 참조 114건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `GAS_URL` — JS /* ── 상수 ── */ 블록 — 이 파일 내 어디에서도 GAS_URL이 읽히지 않음 — wpCmoRead() 호출부는 모두 인라인 URL 문자열 사용; GAS 배선 모호성으로 A 대신 D 처리
  - 게이트: 근거: 리포 참조 403건(git grep 실측) — 확인 필요
- [verbose-block] `gmMemo` — JS GM 메모 IIFE 상단 — localStorage 저장 구현을 설명하는 4행 주석이 과거 버그·page_score·의사결정 맥락을 장황하게 서술; 코드 자체로 의도 충분히 명백
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — about 섹션 stat 블록(.stat-label '사전 예약제') / facilities 섹션-desc('모든 시설은 사전 예약으로 운영됩니다') / membership 섹션-desc('웰페리온은 100% 사전 예약제로 운영됩니다') — '100% 사전 예약제' 운영 정책 문구가 About 통계, Facilities 안내, Membership 설명 세 곳에 실질적으로 동일한 내용으로 반복 기재됨
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `ai-owner` — div.header-left > h1 내 span 태그 — <style> 블록에 .ai-owner CSS 룰 없음, JS에서 querySelector 등 참조 없음. span의 모든 시각 스타일(display, margin, padding, border, font-size 등)이 인라인 style 속성으로 이미 완결돼 있어 이 class 속성이 실질적 기능을 하지 않음
  - 게이트: 소비자 39건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — div.info-box 첫째 문장 — 바로 아래 ssot-note에 '읽기 전용 … 이 화면은 비추기만 합니다'라고 명시돼 있어 '수정하세요' 문구와 모순됨. 수정 대상이 이 화면이 아닌 소스 파일(instagram/_AI시리즈_로드맵.md)이므로 문구가 오해를 유발하거나 시제·맥락이 낡음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — renderTable JS 함수 내 ep-detail-row 생성 ternary else 분기 — hasCard=false인 에피소드는 부모 tr에 onclick 핸들러가 없어 toggleCard가 절대 호출되지 않음. CSS .ep-detail-row{display:none}으로 기본 숨김 상태인 detail row가 항상 렌더되지만 사용자에게 도달할 경로가 없어 '기획 카드 미작성' DOM 블록이 영구 불노출 상태로 남음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `main-content` — @media (max-width:520px) 블록 내부 — 주석 '키오스크 규칙은 최상위로 옮김(아래)' 직후 — CSS 표준은 @media 중첩을 허용하지 않아 브라우저가 이 블록 전체를 파싱 오류로 건너뜀; 주석 자체도 규칙이 이미 이동됐음을 명시
  - 게이트: 소비자 39건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] `scrollbar-width` — 첫 번째 @media (min-width:700px) and (orientation:portrait) 블록 끝 미니파이 행 — 글로벌 스크롤바 규칙(아래쪽 독립 블록, 동일 내용)과 중복 — html·body 스크롤바 숨김 3선언이 키오스크 @media 안과 전체 뷰포트 글로벌 두 곳에 동일하게 존재; 글로벌 선언이 키오스크 조건을 포함하므로 @media 내부 사본은 무의미한 중복
  - 게이트: 근거: 리포 참조 76건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `wlp-inq .social-bar` — 두 번째 @media (min-width:700px) and (orientation:portrait) 블록 — .back-kiosk 규칙 직전 — 같은 키오스크 미디어 조건의 첫 번째 블록에서 .social-bar{display:none!important}로 아이콘 바를 숨기므로 여기서 margin·gap을 재정의해도 시각 효과가 없음; 숨김이 의도라면 이 규칙은 잉여, 숨김이 실수라면 별도 display 복원이 필요한 별개 문제
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 헤더 서브텍스트 <span>("By Appointment Only") · 하단 고정 안내 <p>("All visits and phone inquiries are handled by appointment only. Walk-ins are not available.") — 예약제 정책이 헤더 태그라인과 하단 고정 안내 두 곳에 중복 고지되며, 하단 문장이 상단 언급 내용을 완전히 포함함
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 파일 최상단 HTML 주석 블록 전체 (<!-- Wellperion English Inquiry Block — … re-inject via draft-inquiry-en mode. -->) — 이미 적용 완료된 GM 지시 4건·웰리 검수 1건을 약 45줄 주석으로 상세 서술; 변경 배경은 Git 이력으로 보존 가능하며 파일 내 인라인 축적 주석은 마크업 가독성을 저하시킴
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 내 CSS 룰 4개 전방 한국어 설명 주석 (/* 하단 여백 제거… */ / /* 아이보리 배경 풀블리드… */ / /* 상단 잔여 흰/회색 띠… */ / /* KOR 버튼… */) — CSS 선언 코드 약 10줄에 설명 주석 약 12줄이 붙어 비율 역전; 실측 수치·KO 비교·적용 경위 등 커밋 메시지 수준의 결정 배경이 운영 스타일 블록에 인라인 축적돼 스캔 가독성 저하
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — ① 전송 대상 톡방 card > .info-box 마지막 문장 / ② 사용 조건 accordion > ul > li 세 번째 항목 「방 이름은 여기 목록의 이름과 <strong>완전히 동일한 글자</strong>여야 합니다…」 — 방 이름이 채팅방 창 제목과 완전히 일치해야 한다는 동일 규칙이 info-box와 사용 조건 accordion li에 각각 별도 문장으로 기술됨 — 한 곳만 있어도 충분
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] `addRoom` — script 블록 addRoom() 함수 내 fetch() 호출 직전 5행 주석 — 이미 제거된 no-cors 방식의 과거 행동 서술(역사 기록) + 타 파일(wp_inquiry_form.html) 표준 교차 참조 포함 — 현재 코드 동작(redirect:'follow' + r.json())은 코드 자체로 자명
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [verbose-block] `_roomsFetch` — script 블록 _roomsFetch() 함수 선언 직전 3행 주석 — 배치 번호(배 922)·타 파일(membership.html 배 942) 교차 참조 포함으로 자체 완결성 낮음 — ERP_API_ON 분기·6분 쿨다운 로직은 이미 코드에서 직접 드러남
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — header div.header-top > div > h1 직전 HTML 주석 — badge로 소유자가 이미 렌더링되고 있으며, 닉네임/직급 구분 이유는 정책 SSOT에 속하는 내용 — 이 인라인 주석은 페이지 자체 가독성에 기여 없음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
### 자동 적용됨 (3건)
- [js-function] `shipStatusLabel` — shipStatusLabel() 호출부 0. renderHangro()는 s.status를 직접 문자열로 비교하며 이 함수를 쓰지 않음 (소비자 0건(선언 자체만) — 자동삭제 가능)
- [js-function] `dupKeySet` — dupKeySet()·isSuspect() 모두 호출부 0. 구 renderTrash(보관함 표)가 2026-08-27 삭제되며 유일 소비처 消滅 (소비자 0건(선언 자체만) — 자동삭제 가능)
- [js-function] `NOTIFY_FREQ_LABEL` — NOTIFY_FREQ_LABEL 키 참조부 0. alertTimeHtml·notifySeverity·renderAlertBoard 어느 곳도 이 객체를 읽지 않음. 소비처였던 alertRowHtml이 2026-09-05 삭제됨 (소비자 0건(선언 자체만) — 자동삭제 가능)
### A. 죽은 코드(자동삭제 대상) (8건)
- [js-function] `parseJsonl` — 메인 IIFE 상단 — parseJson 바로 아래 — 정의 후 Promise.all 결과물을 포함한 파일 전체에서 parseJsonl() 호출부 0. 모든 fetch 결과는 parseJson()으로만 파싱됨
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `last` — 메인 IIFE 상단 — parseJsonl 바로 아래 — last() 호출부 0. kakaoLast·latestDate 등 변수명과 혼동될 수 있으나 함수 호출 자체가 없음
  - 게이트: 소비자 3169건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-id] `layer-autonomy` — CSS <style> 블록 — .honest-note 선언 바로 위 — id="layer-autonomy" HTML 요소 없음. HTML 주석에 '레이어 제목 삭제 GM 2026-08-08' 이라 명시되어 있으나 CSS 룰셋은 같이 걷히지 않음
  - 게이트: 소비자 15건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `routines` — CSS <style> 블록 — #layer-autonomy 아래, .feed-status 위 — routines·rcard·rcard-*·pill·rrow 등 이 블록의 모든 클래스가 HTML body 및 JS innerHTML 생성 어디서도 사용되지 않음. 섹션1 「상시 자율 루틴 카드」 HTML이 이미 제거됨
  - 게이트: 소비자 14건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `coo-tier` — CSS <style> 블록 — details.coo-details 선언 바로 위 — coo-tier·coo-tier-h 클래스가 HTML body 및 JS 생성 HTML에 없음. 바로 아래 details.coo-details는 renderHangro()가 실사용하므로 별도 보존
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `coo-flow` — CSS <style> 블록 — details.coo-details 테이블 스타일 아래, .gtbl-wrap 위 — coo-flow·coo-flow-step·coo-flow-arrow·coo-tag 클래스가 HTML body 및 JS 생성 HTML 전체에서 사용되지 않음
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `autopanel-headline` — CSS <style> 블록 — .autopanel.health 아래, .statchip 위 — autopanel-headline·autopanel-body·autopanel-time 클래스가 HTML body 및 JS 생성 HTML 전체에서 사용되지 않음. autopanel 카드 본문이 인라인 HTML로 직접 작성되어 서브클래스 불필요
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `statchip static` — CSS <style> 블록 — .statchip.dead 바로 위 — notifySeverity()가 반환하는 sev 값은 ok·warn·bad·dead 4가지뿐이며 'static'은 없음. JS innerHTML 전체에서 statchip static 클래스 생성 없음
  - 게이트: 선언조차 검색에 안 잡힘 — 추적 안 되는 파일일 수 있다. 판정 거부(안전측)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `esc` — 첫 번째 <script>(ERP 화면 완성도·열람 IIFE) 및 두 번째 <script>(메인 IIFE) 각각에 독립 정의 — 두 IIFE가 각각 esc() 함수를 별도 선언하며 본문 로직이 거의 동일(null 처리 방식만 미세 차이). 같은 파일 내 두 벌 유지
  - 게이트: 근거: 리포 참조 3932건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — CSS <style> 블록 — .feed-status 아래 — '.cmo-loop·.cpo-live-strip' CSS는 이미 삭제됐고 그 사실을 알리는 묘비 주석만 남아 있음. 현 상태 정보 없음. git log에 이력 보존
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 메인 IIFE Promise.all() 배열 — a[0]·a[1]·a[2]·a[4]·a[5]·a[6]·a[7]·a[10]·a[11]·a[15]·a[19]·a[20]·a[21] 등 Promise.resolve('') 슬롯 12개 이상 — 인덱스 정렬용 Promise.resolve('') 슬롯 각각에 fetch 중단 경위를 2~4줄로 설명하는 블록 주석이 붙어 있어 배열이 70줄 이상이 됨. 실제 fetch 항목 식별이 어려워 가독성 저해. git log로 충분한 이력
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [js-function] `SUP_CATS` — JS 전역 선언부 — SUPPLY_API·SUPPLY_KEY 근처 — 선언 후 코드 어디서도 참조되지 않음. renderSupply의 분류 셀은 inCell(text input) 직접 입력, 새 품목은 cat:'비품' 하드코딩, select 드롭다운에 바인딩되지 않음.
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단) · 근거: 리포 참조 0건(선언뿐 · git grep 실측) — 삭제 안전
### B. 중복 설명 병합 (1건)
- [duplicate-text] `sales-desc-notice-center-total` — sales 패널 — chartSalesTrend 카드 desc + 동일 패널 하단 notice — 「센터 전체 = 운영부(회원권) + 강습」 핵심 문구가 카드 .desc와 하단 .notice(「센터 전체 = 운영부(회원권) + 강습(부서별). 6월은 부분월. 매출 마스터 시트 실시간 연동.」) 두 곳에 반복됨. 상단 desc를 제거하거나 notice 한 줄로 통합 가능.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `sales-notice-6월부분월` — sales 패널 — 매출현황 표 하단 notice — 「6월은 부분월」은 현재일(2026-09-06) 기준 6월이 이미 완결월이므로 시제 오류. 진행월은 9월.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `preconnect-googleapis` — <head> 상단 — 폰트 preconnect — 두 폰트 CSS(WantedSans·Pretendard) 모두 jsdelivr CDN에서 로드되므로 fonts.googleapis.com으로의 실제 연결이 발생하지 않아 효과 없는 힌트. 짝 힌트(fonts.gstatic.com)도 없음.
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `header-right` — CSS <style> 블록 — .header-right 규칙셋 — HTML 전체에 class="header-right" 참조 없음; .header-btns만 실사용되며 header-right는 호출부 0
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단) · 근거: 리포 참조 25건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] `(당월 · 「보고」 팀별 + 주차 실측)` — tabOverview 채널 요약 h3 부제, tabChannel 채널 상세 분해 h3 부제 — 두 섹션에 글자 그대로 동일 — 데이터 출처 부제가 개요·채널 탭 두 섹션 헤더에 정확히 중복; 탭이 서로 다른 콘텐츠임을 강조하는 맥락에서 동일 표현 반복
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [duplicate-text] `receivable-source-missing-notice` — tabReceivable — info-banner 바로 아래 placeholder div — 같은 화면 안에서 info-banner가 이미 '미수금·정산대기 소스 미배관'을 4줄로 설명한 직후, placeholder가 동일 메시지를 한 줄로 반복
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `ocf-definition-paragraph` — tabReceivable — '미수금 OCF 영향 분석' 섹션 첫 단락 + <br> — 실무 담당자 대상 운영 대시보드에 OCF 교과서 정의를 장황 서술; 섹션 제목 '미수금 OCF 영향 분석' 자체가 이미 맥락 전달
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `nsNote-colorlegend` — tabChannel — 북극성 KPI 연결 섹션 id="nsNote" 마지막 문장 — 게이지 색상 범례는 gaugeClass() 로직이 막대 색으로 시각화; 텍스트로 동일 정보를 재서술해 읽기 부담만 추가
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `API_URL` — script 설정 섹션 — const API_URL 선언 바로 위 주석 1행 — URL이 이미 실제 GAS 배포 엔드포인트로 채워져 있으므로 '배포 후 교체' 지시 주석은 완료된 안내다.
  - 게이트: 근거: 리포 참조 253건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `--blue` — :root CSS 변수 블록 3~8번째 선언 줄 — --green-bg, --red-bg, --yellow, --yellow-bg, --blue, --blue-bg, --purple, --purple-bg, --orange-bg 이 파일 내 CSS 규칙·JS 템플릿 어디서도 var()로 참조되지 않는다. --green/--red/--orange는 --success/--danger/--warning alias 경유 사용되므로 보존.
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `blue'
usage: git grep [<options>] [-) — 확인 필요
- [dead-markup] `filterCategory` — filter-bar — filterCategory select 요소 — filterMonth는 populateMonthFilter()가 데이터 기반으로 동적 옵션을 채우지만 filterCategory는 JS 어디서도 옵션을 추가하지 않아 기본 단일 옵션만 영구 유지, 사용자가 선택할 수 없어 실질 필터링이 불가능한 빈 드롭다운이다.
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
### B. 중복 설명 병합 (4건)
- [duplicate-text] `disp` — openOrgGuideModal 함수 내 — orgChartHtml 내 동일 객체와 중복 — 같은 내용의 disp 객체가 orgChartHtml과 openOrgGuideModal 두 곳에 각각 선언됨. 코드 자체에 '상수 중복, 의미 무변경'이라고 명시함.
  - 게이트: 근거: 리포 참조 7767건(git grep 실측) — 확인 필요
- [duplicate-text] `birth` — buildHrCard 함수 내, openPrintView 함수 내 — 생년 파싱 블록이 두 함수에 약 7행 동일 복사 — 생년 추출·유효성 검증·나이 계산 코드 블록(var birth 초기화 → 정규식 4단계 → 범위 검증 → 만 나이 보정)이 buildHrCard와 openPrintView 두 함수에 거의 그대로 복사되어 있음.
  - 게이트: 근거: 리포 참조 28건(git grep 실측) — 확인 필요
- [duplicate-text] `addr` — buildHrCard 함수 내, openPrintView 함수 내 — 주소 파싱 블록이 두 함수에 동일 복사 — 주소 추출 코드 블록(var addr 초기화 → 정규식 2단계)이 buildHrCard와 openPrintView 두 함수에 동일하게 반복됨.
  - 게이트: 근거: 리포 참조 148건(git grep 실측) — 확인 필요
- [duplicate-text] `geoSpan` — buildHrCard 함수 내(geoDist), openPrintView 함수 내(geoDist2) — geo-distance 인라인 fetch 블록 2회 반복 — geoSpan+geoScript 인라인 fetch 패턴이 두 팝업 생성 함수에 거의 동일하게(element ID만 geoDist/geoDist2로 다름) 반복됨. 동일 geo-distance API 호출 구조.
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (5건)
- [stale-notice] `ORG_GUIDE_ITEMS_DRAFT` — JS 전역 변수 선언부 — ORG_GUIDE_ITEMS 배열 직전 — false로 선언된 채 파일 내 어디서도 읽히지 않음(if(ORG_GUIDE_ITEMS_DRAFT) 등 분기 없음). 2026-07-31 백엔드 전환 완료 후 정리되지 않은 draft 상태 플래그 잔재.
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <head> 내 meta Cache-Control 태그 바로 위 HTML 주석 — A-6 재검증 20260806 디버깅 세션의 조사 경위(실측 헤더 값·이슈 #1·#2 재현 원인)를 담은 해소 후 주석. meta 태그 자체는 유효하지만 디버깅 이력 서술은 낡은 맥락.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] `evalCriteriaSection` — evalCriteriaSection() 말미 — 평가 기준 접이식 패널(admin 노출) 최하단 alert — 2026-08-17 추가된 '잠정·매니저 확정 대기' 문구가 2026-09-06 기준 20일 경과, 확정·변경 여부 미반영이면 실무진에 혼선 유발
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [stale-notice] `criteriaSection` — criteriaSection() 내부 — '기존 다면평가/포상 체계' 섹션 타이틀 — '전환 검토 대상' 라벨이지만 WP_PERF_EVAL 기반 정기 성과평가는 이미 renderEval에 가동 중 — 전환 완료 후에도 '미전환'으로 오독될 수 있는 표현 잔류
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
- [dead-markup] `qevPersonModal` — HTML body 하단 qevPersonModal div 직전 주석 및 블록 전체 — 현 renderEval은 quantEvalRenderHTML을 호출하지 않아 openQevPersonModal() 진입 경로가 없음 — 모달이 DOM에 상시 존재하나 사용자가 열 수 없는 UI 고아 상태
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### D. 장황 단순화 (5건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — CSS <style> 블록 최상단 /* ============ WELLPERION 인사 운영 허브 — FINAL ... */ 약 50행 블록 주석 — 색 3계층 선언 철학·변수명 계약 경위·시맨틱 hex 매핑 규칙 등을 50행 이상 서술한 설계 문서형 주석. 일상 유지보수 시 실제 CSS 변수·값 탐색을 방해.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] `empBirthCell` — empBirthCell 함수 정의 직전 — // [수정 2026-07-15 A-5 — admin PII 표시 회귀 수정] 로 시작하는 8행 주석 — 백엔드 2026-07-14 응답 변경 이후 구코드 폐기 경위와 새 필드(생년월일·나이) 대응관계를 상세 서술. 이미 적용 완료된 변경의 조사 경위가 'WHY' 이상으로 장황.
  - 게이트: 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [verbose-block] `loadOne` — loadOne 함수 내 두 번째 localWriteGuardActive_ 호출 직전 — // [추가 2026-08-10 A-5 즉시반영 경합수정] 로 시작하는 9행 주석 — TOCTOU 경합 시나리오(불합격 처리 후 화면 미반영 실증 결함)를 서술한 9행 주석. 'await 직후 가드 재확인' 한 줄로 충분한 의도가 재현 경위·결함 설명까지 포함해 장황.
  - 게이트: 근거: 리포 참조 7건(git grep 실측) — 확인 필요
- [verbose-block] `renderEval` — renderEval() 함수 본문 최상단 주석 블록(11줄) — 2026-08-17·08-30 두 차례 UI 개편 경위와 매니저 발언까지 함수 내 주석으로 기록 — git 커밋 메시지 영역이며 함수 진입 가독성 저해
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [verbose-block] `dashCalEvents` — dashCalEvents() 내 DB.appl forEach 블록 상단, 입사예정·첫출근 파생 로직 직전(5줄 블록) — 08-04·08-17 수정 이력과 구 결함 사례(조희제 r133)가 forEach 로직 중간에 5줄 인라인 주석으로 삽입 — 현 동작은 코드 자체로 표현, 히스토리 노트는 git 커밋 메시지 영역
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `deptband` — CSS <style> — th.hol,td.hol 규칙 바로 아래 — HTML 마크업과 JS render() 템플릿 리터럴 어디에도 class='deptband'가 없음. 실제 부서 구분 행은 covrow·deptfirst·deptcell 클래스만 사용.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [js-function] `window.addEventListener` — JS — setOfflineBadge 함수 아래, erpLoad 함수 위 — 게이트 섹션에 동일 'wp-pass' 메시지를 처리하는 두 번째 리스너(resolveGate→erpLoad)가 존재. 두 리스너가 동시에 발화해 erpLoad()가 이중 실행됨. 두 번째 리스너가 sessionStorage 저장·_gateResolved 가드를 포함하여 기능을 완전히 대체.
  - 게이트: 근거: 리포 참조 87건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `RETIRED` — JS — RETIRED 상수 선언 직전 블록 주석 — '이지영 06-27 퇴사 미반영'은 이미 RETIRED={이지영:'2026-06-27'}으로 코드 반영 완료(2026-09-06 현재). '미반영' 표현이 현재 상태와 정반대여서 오해를 유발. 내부 배포 추적번호 '배158'은 실무 운영에 불필요한 내부 로그 잔재.
  - 게이트: 근거: 리포 참조 37건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [js-function] `shiftKind` — JS — isCloser 함수 정의 다음 줄 — render()가 근무 셀 태그를 항상 'sh-work'로 하드코딩하여 shiftKind()를 호출하지 않음(call site 0). 반환 클래스 sh-open·sh-close·sh-mid는 렌더링에 적용되지 않아 관련 CSS 분기도 실질적 미사용. A 대신 D로 분류한 이유: 향후 셀 색상 구분 확장 의도로 작성된 미연결 헬퍼로 판단.
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-id] `gate` — 두 번째 <style> 블록 전체 — <link rel=stylesheet> 직전 — 2026-07-10 CMD 비밀번호 입장 단계 완전 제거 이후 #gate HTML 요소가 삭제됐으나 gate 전용 CSS 블록이 그대로 잔존
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 1094건(git grep 실측) — 확인 필요
- [js-function] `screenSheen` — JS 유기적 바디 보강 블록 — sheen() 함수 직후 — 파일 전체에서 screenSheen() 호출부 0건 — 지브리 원목 장부 디자인으로 모니터 렌더링이 교체되며 LCD 광택 연출 함수가 폐기된 것으로 추정
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 2건(git grep 실측) — 확인 필요
- [js-function] `fmtAsOf` — JS Pages판 전용 블록 — api() 함수 직후 — 파일 전체에서 fmtAsOf() 호출부 0건 — 정의만 존재
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `AMBIENT` — JS 앰비언트 피드 블록 — const AMBIENT=[...] 배열 정의부 — AMBIENT 14개 항목 중 10개 이상이 PERSONA_LINE 객체의 에이전트별 값과 텍스트 완전 일치(A-1 '이력서 한 장씩 다시 확인', A-6 '숫자 하나하나 대조 중', A-2 '지원자와 일정 통화 조율' 등) — PERSONA_LINE에서 파생하면 동일 문구의 단일 출처 유지 가능
  - 게이트: 근거: 리포 참조 5건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `agentSum` — JS 이벤트 엔진 — todayCount 변수 선언 직후 — 인라인 주석이 '계속 사용'이라고 명시하나 파일 전체에서 agentSum() 호출부 0건 — 주석이 현재 코드 상태를 잘못 설명함
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `lf-row.dim` — 첫 번째 <style> 블록 — .lf-row 규칙군 내부 — opacity:1은 CSS 기본값이므로 두 규칙이 아무 시각적 효과를 내지 않는 no-op — JS renderFeed가 여전히 클래스를 배정해 행별 스타일 차이가 있는 것처럼 보여 독자 혼란 유발
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `cm-msg.ok` — line 79 — CSS .cm-msg 블록 — submitCheck() 성공 경로는 closeOv+reloadRows 호출 후 종료되어 cm_msg에 ok 클래스를 적용하는 코드가 전혀 없음. 실패 경로만 'cm-msg err'를 사용(line 362). 이 파일 내 JS 전체를 탐색해도 'cm-msg ok' 또는 classList.add('ok') 형태 참조 없음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 4건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `추가 2026-07-04 r2` — lines 178-180 — renderModeSelect 함수 직전 — '기존…완전히 무변경' 변경 보증 메모는 2026-07-04 적용 시점 리뷰어를 위한 one-time 검증 문구. r2 버전 태그·날짜는 git 커밋 히스토리 귀속 내용이며 현재는 코드 노이즈
  - 게이트: 근거: 리포 참조 4건(git grep 실측) — 확인 필요
- [stale-notice] `면담 체크리스트 팝업 확대 2026-08-25` — line 80 — CSS .modal.wide 선언 직전 — CSS 변경 이력('480→680px')이 코드에 내장됨. 변경이 이미 적용된 현재 변경 전 수치는 독자 노이즈이며 git blame으로 확인 가능한 내용
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (2건)
- [css-class] `--amber` — line 11 — :root 변수 블록 — --amber, --blue 두 CSS 커스텀 프로퍼티가 이 파일의 CSS 선언부·인라인 스타일 어디서도 var(--amber)/var(--blue)로 참조되지 않음
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `amber'
usage: git grep [<options>] [) — 확인 필요
- [dead-markup] `lg_sub` — line 101 — #ovLogin 모달 내 p.sub — id='lg_sub'가 JS 전체(submitLogin·verifyAndLoad·renderChecklist 등)에서 getElementById/querySelector로 단 한 번도 참조되지 않음. lg_owner·lg_pw·lg_err·lg_btn만 접근됨
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-id] `lg_sub` — 로그인 모달 <p class="sub"> 태그 속성 — id="lg_sub"가 JS(getElementById/querySelector) 및 CSS 선택자 어디에도 참조되지 않음 — 정적 텍스트 단락이라 id 불필요
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `lock-note` — 성찰 작성 모달(#ovWrite) 내부, #wf_submit 버튼 직전 — 같은 모달에서 id="wf_sub"가 openWrite() 실행 시 이미 '저장 후 수정 불가'를 표시하므로 lock-note가 동일 메시지를 중복 출력함
  - 게이트: 근거: 리포 참조 6건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `modal-wide-migration-comment` — .modal.wide CSS 룰셋 직전 주석 블록 — 480px→680px 이관은 완료된 과거 사건이며 현재 코드에 480px 참조가 전혀 없음; 완료된 마이그레이션 설명이 잔존해 후속 수정 시 혼선 유발
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `--blue` — :root CSS 변수 선언 블록 (--amber:#e0b15c; 바로 뒤) — 이 파일의 CSS·HTML·JS 어디에도 var(--blue) 참조 없음; 다른 14개 CSS 변수는 모두 페이지 내에서 소비되나 --blue만 미사용 상태
  - 게이트: 근거: 실측 실패(git grep 오류(rc=129): error: unknown option `blue'
usage: git grep [<options>] [-) — 확인 필요

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `serif` — <style> 블록 상단, .wrap 정의 바로 위 줄 — HTML 본문 전체에서 class="serif"를 사용하는 요소가 0건; h1·.node-chro .nm·.sec-letter·.safety h2 등 serif 폰트가 필요한 요소는 각자 CSS selector에 직접 font-family를 지정해 이 유틸리티 클래스가 불필요
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 856건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `EXEC_URL` — 첫 번째 <script> IIFE(정직 배지, F섹션 직후) 첫 줄 + 두 번째 <script> IIFE(자동화로그 섹션) 첫 줄 — 동일한 GAS /exec URL 리터럴이 두 IIFE에 각각 하드코딩됨; URL 변경 시 두 곳 모두 수정해야 하는 유지보수 위험
  - 게이트: 근거: 리포 참조 202건(git grep 실측) — 확인 필요
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] `갱신일-header-pill` — <header> .header-meta, 첫 번째 pill — 페이지 본문 최신 변경은 2026-08-26(@86 개인일정 탭 배포완료)이나 헤더 배지가 53일 이전인 2026-08-04로 고정
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `갱신일-footer` — <footer> 두 번째 <div> 인라인 텍스트 — 헤더 pill과 동일한 stale 갱신일 — 실제 최신 변경(2026-08-26)과 불일치
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `쓰기액션수-pill` — <header> .header-meta, 네 번째 pill — G섹션 표 헤더에 '액션 전체 — 54종'으로 명시됨; 2026-08-17 fix-emp-field 신설·2026-08-25 cal-add/list/update/delete 4종 신설 이후 헤더 카운트가 미갱신으로 6종 차이 발생
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [stale-notice] `읽기DB-pill` — <header> .header-meta, 세 번째 pill — G섹션 표에는 2026-07-28 신설 연차원장·보드명단·공휴일 탭과 2026-08-25 신설 개인일정 탭이 추가됐으나 헤더 pill 열거에 4개 탭 누락
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `item-첫출근캘린더` — 섹션 B, 세 번째 .item — h3 '첫 출근 예정일 · 입사예정/첫출근 캘린더 · 아침브리핑 (2026-08-04 신설, 2026-08-17 결함수정)' 카드 전체 — 3개 기능이 혼합된 h3 제목에 날짜 2개, 본문에 '2026-08-17 이전 결함' 발생 경위·연락처 우선매칭 알고리즘(전화일치→등재, 이름일치+전화한쪽없음→폴백, 양쪽전화있고다름→동명이인 미등재)·아침브리핑 분기 조건·경고 문구가 수백 자로 혼재; 현행 기능 파악보다 변경이력 독해 부담이 더 큼
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
- [verbose-block] `item-개인캘린더` — 섹션 E, 네 번째 .item — h3 '매니저 개인 캘린더 (2026-08-25 신설·배포완료 @84, 2026-08-26 완료처리+HR자동일정 확장+전사등재 5필드·배포완료 @86)' 카드 전체 — h3 제목에 두 사이클 배포 이력이 나열돼 가로폭 초과; 본문 400자 이상이 @84·@86 배포 상세 로그·ensureSchemaHeader_ 결함수정 경위·라이브 왕복검증 6건 목록으로 구성돼 현재 기능 파악이 어려움
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .hero > p / .cta-inner > p — 히어로 단락('각 부서의 채용 공고를 확인하고, 웰페리온에서 만들어갈 다음 이야기를 함께 시작하세요.')과 하단 CTA 단락('지금 관심 있는 부서의 채용 공고를 확인해보세요.')이 동일한 행동유도 메시지를 반복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <head> stylesheet link — href='../../assets/wp-typography.css' — CSS 링크는 ../../assets/(언더스코어 없음)를 참조하지만 본문 JS 스크립트는 ../../_assets/page_ping.js(언더스코어 있음)를 참조 — 디렉터리명 불일치로 wp-typography.css가 404일 가능성
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — footer 마지막 텍스트 — '본 페이지는 웰페리온 ERP · AI CHRO 인사 챕터에서 운영됩니다' — 외부 지원자 대상 공개 채용 페이지에 내부 시스템 운영 메타정보가 노출되어 채용 독자에게 혼선 유발 가능; 운영팀 식별용이라면 HTML 주석으로 이동 검토
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> 블록 — .m-values .t-kicker 룰 직전 두 줄 — HTML 전체에서 class="val-chips" 사용처 없음; .chips 클래스가 실제 사용됨(m-tags 섹션)
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 30건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (5건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk 카드(4대보험 완비) vs .m-list(복리후생) 섹션 — 4대보험(국민연금·고용·산재·건강) 내용이 perk 비주얼 카드와 복리후생 리스트 두 곳에 동일하게 노출
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk 카드(퇴직금·연차 제도) vs .m-list(복리후생) 섹션 — 퇴직금·연차 제도가 perk 카드 헤딩·설명과 복리후생 리스트 두 곳에 동일하게 노출
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk-wide p 말미 '· 직원할인(카페)' vs .m-list(복리후생) '직원할인(카페)' — 직원할인(카페) 항목이 AI 서포트 카드 설명 말미에 비맥락적으로 부착되고 복리후생 리스트에도 동일 존재
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-contact .cbox(☎ 02-6261-1202 · 나우열 매니저) vs .m-foot .contact(동일 내용) — 담당자 연락처·성명이 문의 박스와 푸터 두 곳에 동일하게 노출
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-list 자격 요건 '수행·의전 경력 3년 이상' vs .m-list 우대 사항 '3년 이상 수행·의전 경력자' — 3년 이상 경력이 필수 자격 요건에도 있고 우대 사항에도 동일하게 명기 — 요건이면 우대 재열거 불필요
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (3건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 .values-diagram 룰 직전 4줄 주석 — 설계 실패 이력(1·2차 시도, 커밋 해시)을 4줄로 기록 — 현재 img 단일 태그만 있는 상황에서 독자 가독성을 해치는 역사 설명
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> 블록 IIFE 직전 주석 1줄 — 날짜·시안·내부 티켓 번호 태그를 포함한 개발 이력 주석 — 현재 코드 이해에 불필요한 버전 메타데이터
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 지원하기 폼 CSS 섹션 구분 주석 — 날짜·시안 번호가 삽입된 섹션 구분 주석 — 섹션 제목만 있어도 충분하며 버전 태그가 장황함
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
### B. 중복 설명 병합 (4건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 08 우대사항·지원서류 마지막 li 대비 '지원 및 문의' apply-line — '이력서(사진 포함)·자기소개서·보유 자격증 사본' 제출 요건이 08섹션과 문의 섹션 apply-line 두 곳에서 사실상 동일한 내용으로 반복 서술
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 01 deal-foot(정착지원금 月 100~130만원, 3개월) vs 섹션 04 '정착지원금 (입사 3개월)' m-perk 카드 — 정착지원금 기간(3개월)·금액(일반 100만·시니어 130만) 정보가 01 보상 카드와 04 혜택 카드에 중복 서술
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 01 파트너 등급표(①~⑤) vs 섹션 04 파트너 등급제 perk 카드 vs about-line '파트너 등급제' stat 칩 — 어소시에이트→기본→마스터→시니어→팀리더 등급 구조가 세 곳에서 반복 노출(01 수치 표·04 산문 설명·about 통계 칩)
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — '지원 및 문의' m-contact cbox(문의 전화·나우열 매니저) vs m-foot .contact 라인 — 전화번호 02-6261-1202와 '나우열 매니저' 정보가 문의 섹션 cbox와 페이지 최하단 footer에 그대로 중복
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 최상단 주석 블록 — 파일이 이미 라이브 운영 중인데 '시안'·'이식' 등 마이그레이션 문구와 리비전 태그(A-2)가 그대로 잔존
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> Hero 섹션 주석 — 개발 경위(매니저 지적 일자·타 파일 비교)가 라이브 코드에 잔존; 현 운영 시점 실무진에게 무의미한 내부 맥락
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> 블록 첫 줄 — 타 파일(golfpartner.html) 패턴 비교 메모가 라이브 코드에 잔존; 유지보수 시 불필요한 교차 참조 혼선 유발
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 09 운영 안내 두 번째 li — '2026.6 기준' 시점 표기가 현재(2026-09) 기준 3개월 경과; 규정 자체의 유효성은 별론으로 하더라도 날짜 기준점이 stale
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 섹션 04 혜택 m-perk-wide 내 p 텍스트 — '강습 유니폼 제공'이 별도 혜택임에도 AI 서포트 설명 문장 뒤에 '·'로 병기되어 가독성 저하; 독립 bullet 또는 별도 perk 항목으로 분리 권장
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `m-hero .badge.closed` — <style> 블록 · .m-hero .badge 규칙 바로 아래 줄 — JS 마감 처리 코드는 #mContact와 #topStatus에만 .closed 클래스를 부여하며 .badge 요소에 .closed를 추가하는 호출부가 존재하지 않아 이 셀렉터는 절대 매칭되지 않는 죽은 규칙
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 8건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (2건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-salary .note 카드 / .m-shift 우대사항 카드 — '영어 회화 가능자 급여 추가 조정' 정보가 연봉 카드 note('영어 회화 가능자 등 우대 시 급여 추가 조정')와 우대사항 카드('외국어(영어) 회화 가능자 · 급여 추가조정') 두 곳에 동일 내용으로 기재
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-contact .cbox / .m-foot .contact — 전화번호 02-6261-1202 와 '나우열 매니저'가 m-contact 섹션 cbox와 m-foot .contact 두 곳에 동일하게 표기
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 · .values-diagram 규칙 직전 CSS 주석 — SVG→div→PNG 전환 실패 이력을 서술하는 과거형 엔지니어링 일지로 PNG 확정 완료 후 실무 참고 가치 없음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> 블록 첫 줄 (IIFE 시작 전) — 개발 완료 날짜·시안 버전 태그([추가 2026-07-16 A-5 P2·G5, 2026-07-18 시안2 전환 반영])가 현 시점에서 정보 가치 없이 목적 설명과 혼재
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 두 번째 <script> 블록 첫 줄 (downloadPageAsJpg 함수 선언 전) — 개발 완료 날짜·버전 태그 [추가 2026-07-18 A-5] 가 스테일
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 세 번째 <script> 블록 첫 줄 (openApplyModal 함수 선언 전) — 개발 완료 날짜·버전 태그 [추가 2026-07-18 A-5] 가 스테일
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — .m-ladder .ladder-row 내 ② 주임 ~ ⑥ 부장 스텝 5개 — 5개 스텝 설명이 모두 '진급 N단계'로 직급명·번호에서 이미 자명한 정보를 반복하여 가독성 향상 여지 있음
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> 블록 — .m-values .t-sub 룰셋 직후 두 줄 — HTML 전체 및 JS 어디에도 class="val-chips" 요소 없음. 태그 섹션은 .chips/.chip으로 대체 구현됨.
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 30건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (3건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-salary .note / .m-perk-wide p / .m-list 복리후생 섹션 세 곳 — 4대보험·퇴직금이 급여 카드 note, AI혜택 카드 p 말미('직원할인(카페) · 4대보험 적용'), 복리후생 리스트 3곳에 중복. AI 혜택 카드 문구는 카드 주제와 이질적인 잔류 삽입.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-salary .note / .m-shift .off 배지 / .m-list 복리후생 섹션 세 곳 — 격주휴무가 급여 카드 note('격주휴무 적용'), 근무시간 카드 off 배지('격주휴무'), 복리후생 리스트('격주휴무 · 연차/월차') 3곳에 중복 기재.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-contact .hint / .m-list 복리후생·지원 서류 섹션 — 이력서(사진 포함) 제출 안내가 지원 섹션 hint와 복리후생·지원 서류 리스트 두 곳에 반복 기재.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [css-class] `m-hero .badge.closed` — <style> 블록 — .m-hero .badge 룰셋 직후 — 마감 처리 JS가 topStatus·mContact에만 closed 클래스를 추가하고, heroBadge(#heroBadge, .badge 요소)에는 추가하지 않아 이 룰이 실제로 적용되지 않는다. 상응하는 JS 분기 미구현.
  - 게이트: 근거: 리포 참조 8건(git grep 실측) — 확인 필요
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <script> 첫 번째 블록 IIFE 상단; 두 번째 블록('JPG 다운로드'); 세 번째 블록('자체 지원 접수 폼'); <style> 블록 지원하기 폼 구획 주석 — 개발 단계 코드명(A-5, P2·G5, 시안2 전환) 버전 배지가 프로덕션 JS·CSS 주석 4곳에 잔류. 배포 후 의미 없는 개발 이력 마커.
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요
### D. 장황 단순화 (1건)
- [verbose-block] `values-diagram` — <style> 블록 — .values-diagram 룰셋 직전 4행 주석 — 5행 구현 이력 주석이 CSS에 삽입됨. 커밋 메시지로 이관하거나 1행('/* html2canvas 호환성 이슈로 오프라인 PNG 고정. SVG·div 재구성 시도 금지. */')으로 압축 가능.
  - 게이트: 근거: 리포 참조 37건(git grep 실측) — 확인 필요

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — <style> — .m-values 구역 CSS 내 2줄 (.m-values 정의 바로 아래) — HTML 전체에 class="val-chips" 요소가 없음. m-values 카드는 img.values-diagram + .quote 구조만 사용하며 칩 UI 마크업 미존재
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단) · 근거: 리포 참조 30건(git grep 실측) — 확인 필요
### B. 중복 설명 병합 (1건)
- [duplicate-text] `contact-phone-footer` — .m-foot .contact 행 — .m-contact 두 번째 .cbox와 중복 — 02-6261-1202 · 나우열 매니저 정보가 상단 지원/문의 카드(.m-contact .cbox)와 하단 푸터 contact 행에 이중 노출
  - 게이트: 근거: 이름이 리포 검색에 안 잡힘(서술형 이름·미추적 파일 가능) — 확인 필요
### C. 낡은 안내·버전 배지 (2건)
- [css-class] `badge.closed` — <style> — .m-hero 섹션 CSS 내 1줄 — JS 마감 동기 스크립트가 mContact·topStatus만 .closed 처리하고 heroBadge(.badge)에는 .closed를 추가하는 코드가 없어 이 룰이 실제 적용된 적 없음
  - 게이트: 근거: 리포 참조 12건(git grep 실측) — 확인 필요
- [stale-notice] `추가 2026-07-18 A-5` — <script> JPG 다운로드 함수 최상단 주석 (apply 폼 함수 상단 동일 패턴 포함, 2회 등장) — 날짜·시안 버전 스탬프(A-5, 2026-07-18)가 코드 이력 주석으로 잔류 — git 히스토리로 추적 가능한 정보가 소스에 중복 기재
  - 게이트: 근거: 리포 참조 16건(git grep 실측) — 확인 필요
### D. 장황 단순화 (2건)
- [verbose-block] `values-diagram-comment` — <style> — .values-diagram 규칙 바로 위 4줄 블록 주석 — html2canvas 실패 경위·2차 시도 실패 이유 등 구현 이력 전체를 CSS 주석으로 서술 — 한 줄(예: /* PNG: resvg-js 3× rasterize, 원본 42c3b999 */)로 대체 가능
  - 게이트: 근거: 리포 참조 3건(git grep 실측) — 확인 필요
- [verbose-block] `pageBucket` — <script> 첫 번째 IIFE 내 — fetch 콜백 var hit 할당 직전 if(pageBucket) 분기 포함 — body 태그에 data-jobbucket 속성이 없어 pageBucket은 항상 ""; if(pageBucket) 분기는 절대 실행되지 않는 죽은 분기. pageKey 분기만으로 동일하게 동작함
  - 게이트: 근거: 리포 참조 17건(git grep 실측) — 확인 필요

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
### A. 죽은 코드(자동삭제 대상) (5건)
- [css-class] `big-line` — <style> 블록 메인 CSS, .slogan-en 선언 바로 위 2줄 — HTML 본문 및 JS 생성 마크업 전체에서 class="big-line" 0건 — Part 1~4 슬라이드 재편 시 사용되지 않은 채 남은 타이포 클래스
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `cols` — <style> 블록 메인 CSS, h2.sec 선언 직전 3줄 — HTML 본문 및 JS 생성 마크업 전체에서 class="cols" 0건 — 2026-07-08 Part 1~4 구조 전환 후 남은 2단 그리드 잔재
  - 게이트: 소비자 983건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `_h1best` — 첫 번째 <script> IIFE, renderSales 함수 끝 단일 라인(window._h1best1·_h1best2·_h1have와 같은 줄) — renderAward는 window._h1best1·_h1best2·_h1have만 읽으며 window._h1best는 파일 어디서도 읽히지 않음(죽은 쓰기 할당)
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] `_sel` — 두 번째 <script> IIFE(기간 셀렉터) 상단 변수 선언부 — 선언·초기화 후 selectPeriod 내 _sel = id 쓰기만 있고 파일 어디서도 읽히지 않는 죽은 상태 변수 — 현재 선택 UI는 .pbtn.on 클래스 토글로 직접 처리됨
  - 게이트: 소비자 576건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-id] `foot` — <div class="foot" id="foot"> 요소, live-view 섹션 최하단 — CSS에 #foot 선택자 없음, JS에서 getElementById('foot') 호출 없음 — id 속성이 완전 미참조
  - 게이트: 소비자 1141건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> 블록 최하단, @media print A4 zoom 규칙 바로 위 8줄 주석 — zoom:0.74 한 줄 규칙을 8줄 실측 실험 로그가 감쌈 — 값이 확정된 현재 "/* zoom=0.74: A4 가로 1장 기준, 0.77 이상이면 2장 분기 */" 1줄로 압축 가능
  - 게이트: 근거: 실측 불가(symbol 없음) — 확인 필요

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `hint` — <style> 블록 마지막 줄 — `.hint` 클래스가 스타일에 정의되어 있으나 body 내 어떤 요소에도 사용되지 않음(`.box` 안에는 h1·p·a.btn만 존재).
  - 게이트: 소비자 1255건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
- (정리 후보 없음)

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
### D. 장황 단순화 (1건)
- [verbose-block] `meta[name=description]` — <head> 영역 3번째 meta 태그 — 0초 meta-refresh + JS location.replace가 동시에 발동하므로 사용자가 이 스텁 페이지를 실제로 볼 일이 없고, 크롤러도 리다이렉트 목적지의 메타를 우선 채택함. description의 실수신자가 존재하지 않음.
  - 게이트: 근거: 리포 참조 1건(git grep 실측) — 확인 필요

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### D. 장황 단순화 (1건)
- [verbose-block] `wp-typography.css` — <head> 마지막 줄 (인라인 <style> 직후) — 0초 즉시 리다이렉트 스텁에 외부 타이포그래피 시트 전체 로드 — 페이지가 렌더링되기 전 리다이렉트되므로 네트워크 요청만 발생하고 실효 없음. fallback 단락(p·a)은 이미 인라인 style 블록의 body/a 룰로 충분히 커버됨
  - 게이트: 근거: 리포 참조 129건(git grep 실측) — 확인 필요
