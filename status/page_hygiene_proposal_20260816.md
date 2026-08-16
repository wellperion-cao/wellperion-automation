# 주간 페이지 위생 정리안 — 20260816 (하위모델 감사 → GM 승인 대기)

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
- ⚠️ 감사 실패: 타임아웃(240s)

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
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `title-통합이전` — <head> title 태그 — "(통합 이전)" 레이블은 통합 작업 중 임시 표기. 통합이 완료된 현재 시점에서 해소된 상태 표시가 제목에 그대로 남아 있음.
### D. 장황 단순화 (2건)
- [verbose-block] `desc-parenthetical` — .desc 설명 텍스트 내 괄호 — 리다이렉트 안내문에 대상 페이지의 내부 그룹 세부 구조를 명시. 대상 페이지 구조 변경 시 동기화 누락 위험이 있고, 리다이렉트 용도에 과잉 정보.
- [verbose-block] `style-block` — <head> 스타일 블록 전체 — JS location.replace()가 즉시 실행되어 사용자가 이 페이지를 실제로 볼 확률이 거의 0. 6개 CSS 변수·5개 클래스 전체 다크테마 설정은 no-JS 폴백에 과잉 — 인라인 3줄로 대체 가능.

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [css-class] `month-select-wrap` — CSS 화면용 월 선택기 섹션 (`.tb-month` 정의 직상단) — HTML 마크업이 `.tb-month`로 교체됨 — 파일 전체에서 class="month-select-wrap" 0회
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-lbl` — CSS 화면용 월 선택기 섹션, month-select-wrap 규칙 바로 아래 — `.tb-month .lbl`로 교체됨 — 파일 전체에서 class="month-select-lbl" 0회
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `month-select-wrap` — CSS 인쇄 숨김 규칙 (인쇄 미디어 쿼리 내부) — 대상 클래스 `.month-select-wrap`이 마크업에 없으므로 print hide 규칙도 무효
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] `panel-flush` — CSS panel 섹션, `.panel` 규칙 바로 아래 — HTML·JS 전체에서 class="panel-flush" 0회 — 정의만 존재, 사용 없음. 인쇄 미디어 내 `.panel,.panel-flush{...}` 복합 룰은 `.panel` 공유로 자동 제거 불가(수동 편집 필요)
  - 게이트: 소비자 5건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `TOKEN_ENFORCE` — JS 상수 섹션, GAS_URL 선언 직후 — project_pii_gate_aggregates_public_no_key_ux.md 기록상 PII 게이트 폐기(집계 공개·개별키 UX 제거) — TOKEN_ENFORCE 서버 게이트 현행 여부 불확실

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `사전 예약제` — 1) About .stat-label — '사전 예약제' / 2) Facilities .section-desc — '모든 시설은 사전 예약으로 운영됩니다' / 3) Membership .section-desc — '웰페리온은 100% 사전 예약제로 운영됩니다' — 동일 운영 정책(100% 사전 예약제)이 About 통계·Facilities·Membership 세 섹션 본문에 각각 독립 서술. Membership 첫 문장이 About stat과 거의 동일 표현으로 중복도 최고.
### D. 장황 단순화 (1건)
- [verbose-block] `about-visual` — About 섹션 .about-inner 첫 번째 열 — 500px 높이 그리드 열 전체를 점유하나 opacity 0.15 'W' 단일 문자만 표시. 시설 실사·영상 등 실콘텐츠 없이 CSS 2규칙(기본+모바일)이 배선된 빈 시각 공간. 방문자 기준 정보 전달값 0.

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — page-footer div 바로 위 HTML 주석 블록 — 2026-08-03 과거 사고 기록 — CLAUDE.md '결정 경위·사고 기록 본문 금지' 위반. 이미 해소된 사항이며 풋터가 동일 사실(series_data=수동스냅샷, review_queue=자동갱신)을 이미 표시해 중복.
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — <head> 외부 스타일시트 링크 — 스크립트 경로는 ../../_assets/page_ping.js(언더스코어 있음)인데 이 CSS는 ../../assets/wp-typography.css(언더스코어 없음) — 디렉터리명 불일치로 파일 실재 여부 불명.
### D. 장황 단순화 (1건)
- [verbose-block] `a` — <style> 블록 전역 a 태그 룰 — 정적 HTML과 JS 생성 HTML(renderTable·renderCard) 어디에도 <a> 요소 없어 적용 대상 없음. 단 외부 CSS·page_ping.js 주입 가능성 배제 불가로 D 분류.

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `wlp-inq .hero-band` — 두 번째 <style> 블록 하단 — .back-kiosk 규칙 직전 '기둥 기준' 주석 바로 아래 — position:relative 는 상단 첫 번째 .wlp-inq .hero-band 규칙(background·max-width·margin·padding 포함)에 이미 선언돼 있어 두 번째 단독 규칙은 동일 셀렉터·동일 속성·동일 값의 완전 중복
  - 게이트: 소비자 8건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `wpToSurvey` — UTM 귀속 프리필 <script> 블록 내부 두 번째 주석 줄 — 여름방학 특강 카드가 2026-08-07 GM 지시로 주석 처리됐으므로 현재 활성 버튼은 5개인데 주석은 6버튼·'여름특강' 포함으로 표기돼 현행과 불일치

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `wp-inq-video` — 76~77행 인라인 주석 — 16:9 비율을 담당하는 padding-top:56.25%는 .wp-inq-video 자신이 아니라 그 자식 div(79행)에 인라인으로 걸려 있음 — 주석의 귀속 설명이 틀림.
- [css-class] `wp-inq-video` — 78행 비디오 래퍼 div — 파일 내 <style> 블록에 .wp-inq-video 룰 없음. 모든 스타일은 인라인 처리. 외부 wp-typography.css 참조 가능성 배제 불가 → A 제외·C 분류(모호=자동삭제 금지).
### D. 장황 단순화 (1건)
- [verbose-block] `HTML_header_comment` — 파일 1~41행 전체 — 2026-07-20 GM 지시 3건·웰리 검수 메모·구현 근거를 41행 changelog로 소스에 적재 — 결과(CSS·마크업)는 이미 코드에 반영됨. 보존 가치 있는 유일한 줄은 'To update: edit this file…' 1줄. 나머지는 결정 경위로 이력 파일 분리 대상.

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — info-box(122~126번째 줄) / input#addName placeholder(136번째 줄) / ✅ 사용 조건 아코디언 li(176번째 줄) 3곳 — "방 이름이 카톡 채팅방 제목과 정확히 일치해야 함" 메시지가 세 곳에서 반복. info-box 1곳만 남겨도 동일하게 전달 가능
### D. 장황 단순화 (4건)
- [verbose-block] `addRoom` — addRoom() 함수 내 fetch 호출 직전 261~265번째 줄 — 5줄 변경이력 서술 — 과거 fix 경위·타파일(wp_inquiry_form.html) 참조는 커밋 메시지 자리. 핵심(redirect follow + ok 판독)은 코드 자체로 자명하며 deleteRoom 주석이 이미 한 줄로 요약
- [verbose-block] `deleteRoom` — deleteRoom() 함수 내 fetch 호출 직전 286번째 줄 — 날짜·담당자 기재 변경이력 주석 — git log가 담당. addRoom 주석과 이유 중복, 코드 자체가 redirect follow+json 판독으로 자명
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <script> 블록 첫 줄 215번째 줄 — 타파일(상품기획.html) 이름 하드 참조 — 그 파일이 이동·삭제·개명되면 이 주석이 즉시 거짓. 패턴 설명도 코드로 자명
- [verbose-block] `--yellow` — :root CSS 변수 블록 19~20번째 줄 — --yellow* 3종·--teal* 3종 총 6개 CSS 커스텀 프로퍼티가 이 파일 내 CSS 규칙·HTML·JS 어디서도 var()로 참조되지 않음. 공유 팔레트 템플릿 복사본으로 추정

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `header-right` — CSS <style> 블록, .header-btns 정의 직전 — HTML 내 class="header-right" 사용처 0. .header 자식은 <div class="header-btns"> 하나만 사용.
  - 게이트: 자동적용 잠김(소유=cfo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `tabReceivable-placeholder` — tabReceivable — 미수금 및 정산 대기 현황 카드 하단 — 바로 위 info-banner가 동일한 '데이터 소스 미배관' 상황을 이미 완전히 설명(배관 예정 방식까지 포함). placeholder는 info-banner를 단축 반복.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `asOf` — header-meta, 담당: 나우열M 옆 — JS loadData() 성공 시 '실측 {rm.asOf}'로 덮어씀. 실패 시 'v1.0' 버전 표기가 남아 실제 버전인 것처럼 노출. 'v1.0'은 아무 의미 없는 하드코딩 초기값.
### D. 장황 단순화 (2건)
- [verbose-block] `nsNote` — tabChannel — 북극성 KPI 연결 카드 하단 — 색상 범례(녹·노·적 기준)는 게이지·바 시각이 이미 표현. '연 목표 72억'은 게이지 라벨에 이미 노출. JS에서 nsNote 갱신 없음 — 순수 정적 설명 텍스트.
- [verbose-block] `ocf-edu-paragraph` — tabReceivable — 미수금 OCF 영향 분석 카드 첫 단락 — 전체 섹션이 '데이터 소스 미배관' 상태인데 OCF 개념 정의 교육 단락이 선행. 실무 대시보드에서 불필요한 개념 설명.

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `getFilteredItems` — JS 하단, showShareModal 함수 아래 — applyFilter() 내부의 month/cat/approval 3단 필터 조건과 완전 동일 로직이 중복 존재
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `API_URL` — JS 설정 블록, const API_URL 선언 직전 주석 — 실제 배포 URL이 이미 채워진 상태에서 '배포 후 교체' 지시 주석이 남아 시제 불일치
### D. 장황 단순화 (3건)
- [dead-markup] `filterCategory` — filter-bar 내 두 번째 select 요소 — 카테고리 옵션을 동적으로 채우는 JS 함수(populateCategoryFilter 등)가 없어 항상 '전체 카테고리' 고정 — applyFilter가 읽어도 value='' 이므로 필터 조건이 절대 발동 안 됨
- [verbose-block] `--yellow` — :root CSS 변수 블록 내 4개 행 — --yellow/--yellow-bg/--blue/--blue-bg/--purple/--purple-bg/--orange-bg 는 이 파일 CSS 룰·인라인 스타일·JS 어디서도 직접 참조되지 않음(--orange만 --warning 경유 간접 사용). 같은 행에 있는 --green-bg/--red-bg도 동일하게 미사용
- [verbose-block] `fillBudgetCard` — fillBudgetCard 함수 직전 주석 2줄 — 함수명·HOME_KPI_URL·budget 조건 분기로 의도가 이미 명확 — 주석이 구현 내용을 반복하여 가독성 기여 없음

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] `shiftKind` — JS — isOpener/isCloser 정의 아래 — isOpener·isCloser는 covStatus에서 직접 호출되나 shiftKind 자체는 파일 내 호출부 0
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [js-function] `usedOf` — JS — openApply 섹션 위 — 파일 내 usedOf( 호출부 0 — usedAnnual2026으로 완전 대체됨
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [dead-markup] `_origMsgLoad` — JS — 게이트 섹션 두 번째 message listener 직전 — erpLoad를 변수에 저장했으나 _origMsgLoad를 읽는 코드 없음 — 리팩터링 잔재
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `deptband` — <style> 블록 — .covrow 스타일 아래 — deptband 클래스는 정적 HTML과 JS render() 생성 마크업 모두에 사용되지 않음
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `addEventListener message wp-pass 첫번째리스너` — JS — erpLoad 함수 직후, 게이트 섹션 이전 — wp-pass 리스너 2개 중 첫 번째 — 동일 메시지 수신 시 erpLoad()가 두 번 실행됨; 게이트 섹션 두 번째 리스너가 resolveGate 경유로 동일 역할 완전 수행
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `goToday` — JS — moveMonth 아래 — "오늘" 버튼이 실제 오늘이 아닌 2026-06-01 고정값으로 이동 — new Date() 교체 필요
- [css-class] `sh-open sh-close sh-mid` — <style> 블록 — cell-tag 근무 색상 섹션 — shiftKind()가 호출되지 않아 sh-open·sh-close·sh-mid가 DOM에 실제 적용되지 않는 미활성 스타일
### D. 장황 단순화 (1건)
- [verbose-block] `ovShift p.sub` — ovShift 모달 부제목 <p> — 괄호 내 "이경연 실장 제출 절차 디지털화"는 개발 구현 경위 메모가 직원용 UI에 노출된 것

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `--blue` — :root 변수 블록 (line 11) — CSS 커스텀 프로퍼티 --blue가 정의되어 있으나 페이지 전체에서 var(--blue) 참조가 0건
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] `변경 2026-07-04 r2` — script 블록 최상단 주석 (백엔드 연동 블록 내) — 변경이력 태그([변경 2026-07-04 r2]) 포함 — CLAUDE.md '결정 경위·사고 기록 본문 금지' 원칙 위반. 멘토/신입 분리 설명은 현행 운영 맥락이나 r2 태그 자체는 이력 메모
### D. 장황 단순화 (2건)
- [verbose-block] `renderPickList` — renderPickList 함수 직전 주석 — 3줄 엣지케이스 주석 — 핵심(이름 미지정 시 명단 표시)은 한 줄로 충분, 드문 경우 설명은 장황
- [verbose-block] `WEEK_QUESTIONS` — WEEK_QUESTIONS 상수 선언 직전 주석 — 날짜 태그(2026-07-23)·개정이력·파서 포맷 힌트를 한 줄에 혼재 — 이력 태그는 본문 금지 대상, 파서 포맷 힌트는 parseReflectNote 주석에 이미 중복 서술

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] `about-lead` — about 섹션 — about-lead 단락 3번째 문장 — 단락 내 '한남동' · '9년' · '스포츠·스파·커뮤니티·공간(4 in 1)' 세 수치가 바로 아래 about-stats 카드 4개 중 3개와 정확히 중복 노출됨
### D. 장황 단순화 (1건)
- [verbose-block] `cta-inner` — 페이지 하단 .cta .cta-inner — hero가 이미 '각 부서의 채용 공고를 확인하세요'를 선언했고, cta-inner에는 링크·버튼이 전혀 없어 '부서를 확인하세요'를 말하면서 이미 위로 스크롤해야 하는 구조 — 행동 유도가 막힌 장식 텍스트 블록

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `m-hero .badge.closed` — <style> 헤더 — .m-hero 블록 하단 — JS 마감 처리 시 mContact·topStatus에만 .closed 추가; heroBadge 요소에는 .closed를 절대 붙이지 않으므로 이 규칙은 매칭 불가
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `m-foot .contact` — m-foot 카드 — 페이지 최하단 — 02-6261-1202 + 나우열 매니저가 m-contact .cbox에 이미 존재; 푸터 블록은 완전 중복
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 운영 안내 m-list — 두 번째 항목 — 2026.6 기준이라는 시점 고정 안내로, 현재(2026-08-16) 시점과 2개월 이상 경과 — 대상 강사 여부 이미 확정됐을 것
### D. 장황 단순화 (2건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — <style> — .values-diagram 규칙 직전 4행 주석 — 구현 이력(1차·2차 시도 실패 경위)은 git 커밋 메시지 자리이며, img 태그 하나를 이해하는 데 불필요한 4행 산문
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — 3개 <script> 블록 첫 줄 주석 (마감동기 / JPG다운로드 / 지원폼) — [추가 날짜·시안번호] 형식의 개발 이력 태그 3건 — 코드 기능을 설명하지 않고 git 히스토리 역할을 CSS 주석으로 대체한 장황 표기

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] `val-chips` — CSS <style> 44–45행, .m-values 룰셋 바로 아래 — HTML 전체에 class="val-chips" 요소 없음 — m-values 섹션은 img.values-diagram + .quote만 사용
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] `phone-nawool-duplicate` — .cbox(☎ 문의 전화) + .m-foot .contact 두 곳 — 02-6261-1202 / 나우열 매니저가 연락처 카드(cbox)와 하단 푸터(.m-foot .contact)에 완전 동일 내용 반복
- [duplicate-text] `english-wage-adjustment-duplicate` — .m-salary .note + .m-shift 우대사항 카드 두 곳 — 영어 회화 가능자 우대 시 급여 추가조정 내용이 연봉 카드 note와 우대 사항 li에 중복 기재
### C. 낡은 안내·버전 배지 (1건)
- [css-class] `m-hero badge closed` — CSS <style> 30행 — 마감 처리 JS가 mContact·topStatus만 변경하며 .badge 요소에 .closed를 추가하는 코드가 없음 — 트리거 경로 부재
### D. 장황 단순화 (1건)
- [verbose-block] `values-diagram-css-comment` — CSS <style> 49–52행, .values-diagram 룰셋 직전 — 실패 2회 경위·커밋 해시·라이브러리명을 HTML 내 CSS 주석으로 장문 보존 — git 히스토리/이력 파일에 있어야 할 내용

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] `val-chips` — CSS 블록, .m-values 섹션 직후 — HTML 전체에 class="val-chips" 요소 없음; 실제 칩 컨테이너는 .chips
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `val-chips span` — CSS 블록, .val-chips 바로 아래 — .val-chips 부모가 사용되지 않으므로 자식 선택자도 도달 불가
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
- [css-class] `cbox cval a` — CSS 블록, .m-contact 섹션, .cbox .cval 직후 — .cval 내부에 <a> 요소 없음; 이메일·전화번호 모두 평문 텍스트
  - 게이트: 자동적용 잠김(소유=chro 도메인 · 사람이 판단)
### B. 중복 설명 병합 (3건)
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk 첫 번째 카드 p 태그 vs .m-ladder 카드 .ladder-row — 3단계 진급(주임→반장→팀장, 성과 기반) 내용이 .m-perk 카드 설명과 .m-ladder 3-step 블록에 동일하게 반복
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-perk-wide p 태그 vs .m-tags .chip — "유니폼 제공" 항목이 m-perk-wide 설명(근무 유니폼 회사 지급)과 m-tags 칩(유니폼 제공 등) 두 곳에 중복
- [duplicate-text] ⚠️ 대상 이름 없음(자동적용 불가) — .m-contact .cbox(전화) vs .m-foot .contact — 전화 02-6261-1202 + 나우열 매니저가 지원·문의 카드와 하단 푸터에 동일 반복
### C. 낡은 안내·버전 배지 (3건)
- [css-class] `m-hero badge closed` — CSS 블록, .m-hero .badge 직후 — JS fetch 결과로 마감 처리 시 heroBadge에는 .closed 추가하는 코드 없음; mContact·topStatus만 변경됨
- [stale-notice] `pageBucket` — 첫 번째 <script> IIFE 내부, pageKey 선언 직전 — <body>에 data-jobbucket 속성 없음; pageBucket은 항상 "" → if(pageBucket) 분기 절대 실행 안 됨
- [stale-notice] ⚠️ 대상 이름 없음(자동적용 불가) — 첫 번째 <script> 첫 줄 주석 — 버전·날짜 태그(A-5, P2·G5, 시안2)는 git 이력 정보; 코드 실행과 무관한 잔류 주석
### D. 장황 단순화 (1건)
- [verbose-block] ⚠️ 대상 이름 없음(자동적용 불가) — CSS 블록, .values-diagram 룰셋 직전 — 실패 이력·커밋 해시·시도 과정 4줄이 프로덕션 CSS 주석에 박혀 있음; git blame 영역 내용

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `title` — <head> title 태그 — "주소가 바뀌었습니다"는 URL 이전 초기 전환 안내. 브라우저 탭·히스토리에 계속 노출되는 stale 마이그레이션 메시지.
- [stale-notice] `hint` — body > .box > .hint (최하단) — 북마크 갱신 촉구는 URL 이전 직후 일회성 안내. 0초 자동리다이렉트 환경에서 이 텍스트를 읽는 경로가 없으며, 폴백 도달 사용자에게도 버튼 하나면 충분.

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
- (정리 후보 없음)

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
- (정리 후보 없음)

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### D. 장황 단순화 (1건)
- [verbose-block] `wp-typography.css` — <head> 마지막 줄 — 0초 리다이렉트 스텁에 외부 타이포그래피 CSS 전체 로드 — 인라인 <style>이 이미 body·a 두 요소를 완전히 커버하고, 이 페이지에서 wp-typography.css의 어떤 클래스도 사용되지 않음
