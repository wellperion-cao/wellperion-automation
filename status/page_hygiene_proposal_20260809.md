# 주간 페이지 위생 정리안 — 20260809 (하위모델 감사 → GM 승인 대기)

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
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] CSS — .egrid 선언 직전 두 줄 — .ecard-top·.ename 클래스는 inlinePanelHtml()이 생성하는 마크업(ecard-head·egrid·inline-actions 구조)에도, HTML 정적 마크업에도 등장하지 않음. 단, 복합 선택자 .efield input,.efield select,.ecard-top input{...} 중 ecard-top input 부분은 이 snippet에 미포함 — 해당 줄은 snippet 자동 적용 불가, 별도 수동 정리 필요
  - 게이트: 소비자 12건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] CSS — .ecard 블록 내 — .na 클래스가 JS 전체에서 className 또는 classList 할당으로 부여되는 경우 0건. HTML 정적 마크업에도 없음
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### D. 장황 단순화 (2건)
- [verbose-block] CSS — body.embed .sheet-links a.sheet-link:not(.hlink-add) 규칙 직전 — 4줄 구현 경위 주석. 규칙 자체는 유효하나 경위는 git log에 보존 가능 — /* 임베드: 감싸는 페이지 ERP 링크 중복 방지 */ 한 줄로 대체 가능
- [verbose-block] HTML — <footer id="foot"> — '서버(자동저장)'과 '편집→☁️ 자동저장으로 즉시 반영' 두 곳에서 자동저장을 반복 언급. '편집→서버 자동저장 · 전 부서 공유(?dept=) · 업무·결재 연동' 한 줄로 충분

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
### B. 중복 설명 병합 (1건)
- [duplicate-text] <head> 4번째 줄 — 직후 <script>location.replace()가 동일 목적지(+hash 보존)로 이미 리디렉션 — JS 환경에서 이중 실행. meta는 no-JS 전용 폴백 역할만.
### D. 장황 단순화 (1건)
- [verbose-block] .card 세 번째 자식 — JS redirect 즉시 실행(0ms)으로 노출 빈도 거의 0. 그룹 내 하위 항목 열거(문의·금일 등록·전체 명단)는 목적지 페이지에서 확인 가능 — 버튼 단독으로 충분.

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 문의흐름지도 — `3. 웰페리온 가이드/cmo/funnel/문의흐름지도.html`
- (정리 후보 없음)

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] (1) about .stat-label '사전 예약제' / (2) membership .section-desc '웰페리온은 100% 사전 예약제로 운영됩니다' / (3) facilities .section-desc '모든 시설은 사전 예약으로 운영됩니다' — '100% 사전 예약제' 메시지가 세 섹션에서 반복 노출. Membership 한 곳으로 통합해도 메시지 손실 없음.
- [duplicate-text] (1) about .section-desc '전문 파트너 코칭' / (2) membership .membership-features 첫 번째 li '전문 파트너 전담 코칭' — about 설명과 멤버십 특전 목록에 거의 동일한 표현이 이중 노출.
### C. 낡은 안내·버전 배지 (1건)
- [dead-markup] about 섹션 .about-inner 첫 번째 컬럼 — 500px 높이 박스에 'W' 한 자만 — 교체되지 않은 이미지 플레이스홀더. 방문자에게 빈 회색 박스로 보임.

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] .content 닫는 </div> 직후, .page-footer 직전 — 과거 사고 경위 메모(2026-08-03)가 HTML 주석으로 잔존하나 같은 정보(사람이 갱신하는 스냅샷 / 매일 자동 갱신)는 page-footer 가시 텍스트에 이미 반영됨 — 사용자에겐 노출도 안 되는 이중 기록
### D. 장황 단순화 (1건)
- [verbose-block] renderCard 함수 첫 번째 줄 — renderCard 는 hasCard(= ep.has_card && cards && cards[ep.num])가 truthy일 때만 호출되므로 null/undefined 인자가 들어오는 경로가 현재 없음. renderTable ternary else가 no-card 케이스를 별도 처리함

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] line 230 — SCRIPT 블록 wpToSurvey IIFE 상단 주석 2번째 줄 — 여름특강은 2026-08-07 GM 지시로 숨김됐고 추석선물세트(ohnutti) 버튼이 추가됐으나 목록 미반영 — 현행 활성 6버튼(멤버십·성인강습·유소년강습·추석선물세트·공간렌트·비즈니스)과 불일치
- [stale-notice] line 113 — .video-frame div 직전 HTML 주석 — YouTube iframe이 이미 삽입돼 영상이 실재하므로 '자리(placeholder)' 표현이 현행 상태와 불일치

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] L3, 최상단 주석 첫 단락 세 번째 줄 — <link rel="stylesheet" href="../../assets/wp-typography.css">가 L42에 실재하므로 'Inline styles only' 주장이 사실과 불일치 — 외부 스타일시트 의존성 있음
- [stale-notice] L76–77, 비디오 섹션 인라인 주석 — padding-top:56.25%는 .wp-inq-video div 자체(L78)가 아닌 그 내부 div(L79)에 선언됨 — 주석이 가리키는 요소가 틀림
### D. 장황 단순화 (2건)
- [verbose-block] L1–41 파일 최상단 HTML 주석 블록 전체 — 4개 '2026-07-20 GM instruction' 이력·함정 해설·구현 판단 근거 ~40줄이 HTML 주석에 inline 박혀 있음 — 렌더·기능에 무관하며 git commit 메시지 영역
- [dead-markup] L78, 비디오 wrapper div class 속성 — <style> 블록에 .wp-inq-video CSS 규칙 없음 — 모든 레이아웃은 inline style로 완결되어 class 속성이 시각·동작에 기여하지 않는 것으로 보임; wp-typography.css 미확인으로 A 보류

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] 아코디언 '✅ 사용 조건' ul 세 번째 li — 상단 카드 info-box('방 이름은 카카오톡에서… 정확히 일치해야 전송됩니다')가 동일 제약을 이미 서술 — 아코디언 항목은 표현만 다른 반복
### D. 장황 단순화 (2건)
- [verbose-block] :root CSS 변수 블록 — --shadow-card 바로 위 줄 — 파일 내 var(--teal), var(--teal-bg), var(--teal-border) 참조 0건 — 미사용 디자인 토큰 3개
- [verbose-block] :root CSS 변수 블록 — --teal 바로 위 줄 — 파일 내 var(--yellow), var(--yellow-bg), var(--yellow-border) 참조 0건 — 미사용 디자인 토큰 3개

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 내 .header-btns 규칙 직전 — HTML 전체에 class="header-right" 사용처 0. 실제 버튼 래퍼는 .header-btns.
  - 게이트: 소비자 15건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### D. 장황 단순화 (3건)
- [verbose-block] #tabReceivable > 미수금 OCF 영향 분석 section-card 첫 번째 <p> — CFO·GM 대상 운영 페이지에 OCF 기초 개념 정의 교육 문장. 독자 수준 불일치.
- [verbose-block] #tabReceivable > .info-banner <span> 내 두 번째 문장 — 운영 현황 페이지에 GAS API 구현 방식(openById) 노출. 소스 미배관 사실 전달에 불필요.
- [verbose-block] #tabChannel > 북극성 KPI 연결 section-card > #nsNote 마지막 문장 — gaugeClass() + gauge-fill.good/warn/bad CSS가 이미 동일 기준을 시각 표현. 텍스트 범례 중복.

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] <style> 블록 — .covrow 규칙 바로 아래 — 정적 HTML과 JS render() 전체 어디에도 deptband 클래스를 부여하는 코드가 없음. 참조 0건.
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [js-function] JS 영역 — usedAnnual2026 함수 정의 바로 위 — 파일 전체에서 정의만 있고 호출부 0. 같은 역할(연차·반차 합산)을 usedAnnual2026()이 모든 호출 지점에서 수행. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [dead-markup] 자체 로그인 게이트 섹션 — 두 번째 message listener 직전 주석 아래 — 할당 후 파일 어디서도 읽기·호출 없음. 리팩터 중 '기존 함수 보존' 의도였으나 미완된 채 방치. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
### B. 중복 설명 병합 (1건)
- [duplicate-text] ERP 백엔드 연동 섹션 — erpLoad() 정의 직후 — 동일한 wp-pass 이벤트를 게이트 섹션의 두 번째 listener(resolveGate → erpLoad 포함)가 이미 온전히 처리. 첫 번째가 살아 있어 wp-pass 수신 시 erpLoad()가 이중 실행됨.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] JS 영역 — moveMonth 함수 바로 아래 — "오늘" 버튼이 실제 오늘(2026-08)이 아닌 6월 2026으로 하드코딩. 샘플 데이터 월 기준으로 고정된 것으로 현재 월과 불일치.
### D. 장황 단순화 (1건)
- [verbose-block] ovShift 모달 — h3 바로 아래 — 개발 경위 메모(디지털화 절차)가 최종 사용자 UI에 그대로 노출. 실무진 사용 맥락에서 불필요한 내부 구현 주석.

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] CSS <style> — .cm-msg 블록 3번째 줄 — submitCheck() 성공 경로는 closeOv()만 호출하고 cm_msg.className에 'ok'를 적용하지 않음. 실패 경로만 'cm-msg err'를 씀. 페이지 전체에 classList.add('ok') 또는 className='cm-msg ok' 호출부 0. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] JS <script> — renderModeSelect 함수 직전 — 2026-07-04 구현 당시 이행 메모. 코드에 이미 반영돼 주석 역할 소멸. PIN 1202 평문을 클라이언트 JS 주석에 노출.
- [stale-notice] JS <script> 최상단 — const EXEC_URL 위 — 보안 보증 의도 주석이지만 PIN 1202 평문 포함. 클라이언트 JS로 누구나 열람 가능하므로 주석으로 기록하는 것이 오히려 노출 위험. 실제 인증은 erpPost 호출이 담당.

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-id] 로그인 모달 · <p class="sub" id="lg_sub"> — JS 전체에 getElementById('lg_sub') 호출 0건 — ID 속성만 사용 안 됨, 요소·텍스트 자체는 표시됨
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] ovWrite 모달 하단 정적 마크업 — openWrite()가 wf_sub에 '· 저장 후 수정 불가'를 동적 주입하므로 같은 모달 내 동일 경고 이중 표시
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] <script> 블록 최상단 주석 — [변경 2026-07-04 r2] 형식의 인라인 변경이력 — 이력 추적은 git 역할. 설명 내용(멘토 PIN 분리·교차접근 불가)은 유효하나 changelog 형식 자체가 stale
- [stale-notice] WEEK_QUESTIONS 선언 직전 한 줄 주석 — 날짜 박힌 확정 이력 주석 — 파서 형식 설명은 유용하나 '매니저 확정본 · 2026-07-23' 부분이 changelog stale
### D. 장황 단순화 (1건)
- [css-class] style 블록 · .banner 룰셋 직후 — setBanner() 호출이 '' 또는 'ok'만 사용 — 'err' 전달 0건. .banner.ok와 짝으로 방어적 추가 추정

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] .about-lead 단락 + .about-stats 수치카드 블록 — 한남동·9년·스포츠·스파·커뮤니티·카페 3개 팩트가 산문(about-lead)과 수치카드(about-stats) 두 곳에 동시 표현 — 카드가 단락을 그대로 요약 반복
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] .about-lead 단락 (about-stats '9년+' 카드도 동일) — 자동갱신 로직 없이 하드코딩된 운영 연수 — 매해 stale. 2026년 기준 이미 10년 전후 경계
### D. 장황 단순화 (1건)
- [verbose-block] footer — 외부 지원자 대상 공개 채용 페이지에 내부 시스템 운영 메타 레이블 노출 — 지원자에게 불필요한 내부 맥락

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 45–46줄, .m-values 사이 — HTML에 class="val-chips" 요소 없음. 칩 컨테이너는 .chips/.chip 사용. JS 참조도 없음
  - 게이트: 소비자 16건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (3건)
- [duplicate-text] m-perk 카드 3개(4대보험 완비·퇴직금·연차) ↔ m-list '복리후생' 섹션 — 4대보험·퇴직금·연차 세 항목이 시각 카드(m-perk)와 텍스트 목록(m-list 복리후생) 양쪽에 완전히 중복 기재
- [duplicate-text] m-perk-wide 설명 말미 '· 직원할인(카페)' ↔ m-list 복리후생 '직원할인(카페)' — 같은 문구가 두 섹션에 반복
- [duplicate-text] m-list '자격 요건': '수행·의전 경력 3년 이상' ↔ m-list '우대 사항': '3년 이상 수행·의전 경력자' — 동일 내용이 자격요건과 우대사항 두 목록에 동시 등장해 독자 혼란 유발
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] <style> 블록 50–53줄, .values-diagram 규칙 직전 — 결정 경위·시도 이력을 CSS 주석에 박아둔 것. SSOT .md 규칙(경위는 이력파일, 본문 금지) 위반. 커밋 해시·스프린트 번호는 git log가 관리
- [stale-notice] 첫 번째 <script> 블록 최상단 — 날짜·스프린트 버전 태그가 소스 내 박혀있는 변경 이력 주석. git history 중복
- [stale-notice] 두 번째 <script> 블록 최상단 — 날짜·스프린트 버전 태그 주석
- [stale-notice] 세 번째 <script> 블록 최상단 — 날짜·스프린트 버전 태그 주석

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (2건)
- [css-class] <style> 블록, .m-values .t-sub 규칙 직후 — HTML 전체에 class="val-chips" 요소 없음 — .m-values 내 동일 역할을 .chips/.chip이 대체
  - 게이트: 소비자 16건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] <style> 블록, .m-hero .badge 규칙 직후 — 마감 IIFE가 closed 클래스를 mContact·topStatus에만 추가 — heroBadge(.badge)에는 추가 경로 없음
  - 게이트: 소비자 6건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (4건)
- [duplicate-text] 자격요건 카드 li 항목 + m-contact .hint 텍스트 — 「이력서(사진 포함)·자기소개서」가 자격요건 리스트와 contact hint에 동일 내용으로 중복 기술
- [duplicate-text] m-salary .note div 내부 — 「수습 3개월」이 같은 .note 내 '정규직(수습 3개월)'과 '수습 3개월 월 270만원 지급' 두 곳에 등장
- [duplicate-text] m-salary .note + 우대사항 m-shift 카드 — 「영어 회화 가능자·급여 추가조정」이 급여 note와 우대사항 리스트 양쪽에 실질 동일 내용으로 중복
- [duplicate-text] m-perk-wide 카드 본문 + m-tags chip — 「유니폼 제공」이 AI 서포트 카드 본문('근무 유니폼 제공')과 복지 chip('유니폼 제공 등') 두 곳에 반복
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] 첫 번째 <script> 블록 최상단 — 버전·날짜 태그(A-5 P2·G5, 2026-07-16) 및 시안 번호가 역사적 기록 — 기능 코드가 의미를 자체 전달
- [stale-notice] 두 번째 <script> 블록 최상단 — 날짜·버전 태그 패턴 동일, 이미 구현 완료된 함수의 역사적 주석
- [stale-notice] 세 번째 <script> 블록 최상단 — 날짜·버전 태그 패턴 동일
### D. 장황 단순화 (1건)
- [verbose-block] <style> 블록, .values-diagram 규칙 직전 — 4줄 구현 일지(1차·2차·3차 시도 내역)를 CSS에 인라인 — git history로 충분, 코드 가독성 저해

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록, .m-hero .badge 룰셋 직후 — JS가 .closed를 추가하는 대상은 #mContact와 #topStatus뿐 — .m-hero .badge(#heroBadge)에는 클래스 변경 코드 없음
  - 게이트: 소비자 6건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (4건)
- [duplicate-text] .m-contact .cbox(☎ 문의 전화) + .m-foot .contact 인라인 — 전화번호 02-6261-1202 / 나우열 매니저가 지원·문의 카드와 푸터 두 곳에 중복
- [duplicate-text] .m-contact .hint 문장 + m-list '복리후생·지원 서류' 리스트 항목 — 이력서(사진 포함)·자기소개서 안내가 hint 문장과 복리후생 리스트 두 곳에 동시 등장
- [duplicate-text] .m-salary .note + .m-perk-wide <p> + m-list '복리후생' 항목 (3회) — 4대보험이 급여 노트, AI서포트 카드 설명, 복리후생 리스트에 세 번 반복
- [duplicate-text] .m-perk 카드 <h3> + m-list '복리후생·지원 서류' 항목 — 유니폼 제공이 혜택 카드(h3)와 복리후생 리스트 양쪽에 등장
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] <style> 블록, .values-diagram 룰 직전 (4행 주석 블록) — 1차·2차 구현 실패 경위·특정 git 해시(42c3b999)를 CSS 주석에 박은 것은 커밋 메시지로 남겨야 할 과거 기록; 현행 운영에 필요한 정보 없음
- [stale-notice] 1번째 <script> 블록 첫 줄 (동일 패턴이 2·3번째 script 블록에도 반복: '[추가 2026-07-18 A-5]') — 스프린트 코드(A-5 P2·G5)·시안번호·날짜 태그는 git 커밋 메시지 정보 — 코드 주석으로 잔류시켜야 할 내용 아님
### D. 장황 단순화 (1건)
- [verbose-block] .m-perk-wide 카드 내 <div> > <p> — AI 서포트 설명문 뒤에 이질적인 '직원할인(카페)·4대보험'이 점(·)으로 덧붙여져 맥락 혼합 — 두 항목은 복리후생 리스트에 이미 존재

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### D. 장황 단순화 (2건)
- [verbose-block] body > div.box > div.hint — meta refresh 0초 + JS location.replace 이중 즉시 리다이렉트로 사용자가 이 텍스트를 볼 수 없음; 폴백 케이스(JS·meta 모두 불능)에서도 .btn 링크 하나면 충분하고, 즐겨찾기 변경 안내·대안 버튼 경로 설명은 잉여
- [css-class] <style> 내 .hint 룰셋 — 위 .hint 마크업 블록이 제거되면 이 CSS 룰은 참조처가 0이 됨 — 독립 기능 없음

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
### D. 장황 단순화 (2건)
- [verbose-block] <head> 내 <script> 직전 1줄 — 1줄짜리 location.replace 스텁에 50자+ 한국어 설명 주석 — 코드 자체가 의도를 충분히 설명함
- [verbose-block] <body> 태그 인라인 style 속성 — JS 실행 환경에서는 body 렌더 전에 리다이렉트되어 사실상 노출 0; noscript 폴백까지 뚫린 극단 케이스 전용 텍스트에 CSS 선언 5개는 과잉

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] head > meta[name=description] — 본문 <p> '항해 지도는 자율 작업 현황 ▸ 북극성별 보기로 통합되었습니다'와 동일 문장 반복. 0초 meta refresh 스텁이라 검색엔진 description 노출 실익 없음.

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] <body> 첫 줄 HTML 주석 — 2026-07-03 결정 경위 주석 — 한 달 넘은 이관 사유로, 리다이렉트 스텁이라는 사실은 페이지 자체(meta refresh + 본문 안내문)로 이미 명백하며 결정 경위는 SSOT .md 규칙상 본문 기재 금지 대상
### D. 장황 단순화 (1건)
- [verbose-block] <head> 외부 CSS 로드 — meta refresh 0초 리다이렉트 스텁에서 외부 타이포그래피 CSS 네트워크 요청은 사용자에게 렌더링되지 않음. 폴백 화면 스타일은 인라인 <style> 블록(body·a 두 규칙)이 이미 처리하므로 추가 로드 불필요
