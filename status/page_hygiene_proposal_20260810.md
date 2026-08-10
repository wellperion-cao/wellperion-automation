# 주간 페이지 위생 정리안 — 20260810 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: cmo

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 문의흐름지도 — `3. 웰페리온 가이드/cmo/funnel/문의흐름지도.html`
- (정리 후보 없음)

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] HTML — .cover 내 cover-notice · page-footer 두 곳 — '개인정보 미포함' 고지가 표지 cover-notice와 page-footer에 중복. 표지가 '이름·연락처' 구체적 명시로 더 충분하므로 footer 분은 단순 반복.
### C. 낡은 안내·버전 배지 (3건)
- [css-class] CSS — 수기 입력란 블록 (.manual-input 룰 직전) — .manual-section · .manual-row · :first-child · :last-child 4개 룰은 HTML body에 해당 클래스 사용 0회. '호환 유지' 주석이 미래 재사용 암시하나 현재 렌더에 기여 없음.
- [stale-notice] CSS — .comment-val 룰 직전 주석 — 2026-07-23 이미 수리 완료된 버그 경위를 프로덕션 CSS에 인라인으로 남긴 사고 노트. 현재 동작 설명이 아닌 과거 이슈 기록으로 git 히스토리에 속하는 내용.
- [stale-notice] JS — GAS_URL 상수 직후, _wpUrl 함수 선언 직전 — 폐기된 PII 클라이언트 게이트·'GM 옵션A' 설계 경위 기록 주석. 현재 코드 이해에 불필요한 과거 설계 결정 노트.
### D. 장황 단순화 (2건)
- [js-function] JS — 상수 블록 하단 — 항등 함수(_wpUrl(x)===x). 4개 호출부를 GAS_URL + '...' 직접 사용으로 교체하면 함수 전체 제거 가능. 현재 아무 변환도 없음.
- [verbose-block] JS — renderKpiTable rows 배열 3번째 항목(전환율 row) — rateVal 필드는 선언 후 읽히는 곳 없음. 렌더 로직은 r.val만 참조. 잉여 속성으로 순수 노이즈.

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] .page-footer 직전 HTML 주석 블록 — 2026-08-03 해소된 버그 경위 주석. 결론(두 소스의 갱신 주기 구분)은 이미 푸터 텍스트에 사용자 언어로 완전히 흡수됨 — 주석은 중복 인시던트 로그로만 남아 있음.
### D. 장황 단순화 (2건)
- [verbose-block] buildM5Map 함수 내 if/else 블록 (script 상단부) — 3줄 주석이 2줄 코드를 설명. 첫 주석은 전체 우선순위 순서를 나열하지만 코드는 발행완료 케이스만 구현 — 의도·코드 불일치로 혼란 유발. 주석 줄 수가 로직 줄 수를 초과.
- [verbose-block] script IIFE 전체 — 8개 함수 구분선 주석(resolveBadge·buildM5Map·renderCard·renderTable·toggleCard·esc·fetchJson·메인 각 앞) — 함수명 자체(resolveBadge, buildM5Map, renderCard 등)가 이미 섹션을 명확히 구분. 장식선 8개는 정보 추가 없이 코드 부피만 늘림.

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] <script> 블록 내 wpToSurvey IIFE 첫 번째 설명 주석줄 — 여름특강 카드는 2026-08-07 GM 지시로 주석처리됐고 그 자리에 오넛티(추석 선물세트)가 들어왔으나 버튼 목록에 '여름특강'이 잔류해 실제 6버튼 구성과 불일치
### D. 장황 단순화 (1건)
- [verbose-block] type-grid 내 유소년 강습 카드와 오넛티 카드 사이 HTML 주석 블록 전체 — GM 지시(삭제 아님)로 보존하는 블록이나 오넛티 카드 위치 이동 복원 안내까지 포함해 19줄 주석으로 비대; '시즌 재개 시 주석해제 + 오넛티 위치 되돌리기' 1줄로 압축 가능

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] 상단 subtitle <span>(고정문구)과 하단 <p> 마감 문단 — 예약제 안내가 상단 'By Appointment Only'와 하단 'All visits and phone inquiries are handled by appointment only. Walk-ins are not available.' 두 곳에 반복
### D. 장황 단순화 (4건)
- [verbose-block] 파일 최상단 전체 HTML 주석 블록(1~35행) — 완료된 GM 지시 3건(2026-07-20) 이력과 실측 경위가 파일 본문에 인라인 체인지로그로 남아 있음 — git 커밋 메시지로 충분
- [verbose-block] <style> 블록 첫 번째 주석(-75px 룰 위) — 완료된 실측 경위(-75px 도출 근거)를 CSS 주석 3줄로 유지 — 값 자체가 코드에 있으므로 주석 불필요
- [verbose-block] <style> 블록 두 번째 주석(::before 룰 위) — 50vw 기법 선택 경위와 '눈대중 아님' 강조가 CSS 주석에 남아 장황 — 기법은 코드에서 자명
- [verbose-block] <style> 블록 세 번째 주석(#header-outer 룰 위) — 함정 경위 3줄 인라인 설명 — KOR 버튼 공존 주의사항만 한 줄로 줄이거나 삭제 가능
