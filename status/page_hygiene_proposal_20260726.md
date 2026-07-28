# 주간 페이지 위생 정리안 — 20260726 (하위모델 감사 → GM 승인 대기)

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
- [css-class] <style> 블록 — .ecard 규칙 바로 다음 줄 — JS·정적 HTML 어디에도 ecard 엘리먼트에 na 클래스를 부여하는 코드 없음 · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [css-class] <style> 블록 — .ecard.na 다음 두 줄 — 구 편집 패널 잔류 CSS; 현재 inlinePanelHtml은 .ecard-head만 렌더하며 .ecard-top·.ename 엘리먼트는 생성되지 않음
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] JS — deleteInline 함수 직후, saveToServer 함수 직전 — 이미 제거된 함수들을 나열하는 이력 주석; 참조 코드가 존재하지 않아 실무 안내 가치 소진
### D. 장황 단순화 (1건)
- [verbose-block] header-top 영역 — h1 바로 아래 — 3문장 중 2·3번째(반복규칙 설명·입력 경로)는 페이지 내 honesty 배너·UI 자체로 이미 전달; 첫 문장만 남겨도 충분

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
- [css-class] line 16, :root 블록 — 페이지 내 CSS·HTML 어디서도 var(--accent)·var(--accent-bg)를 참조하지 않음. 나머지 --border:#3d3835; 은 .card border에 사용 중이므로 보존.
  - 게이트: git grep 오류(rc=129): error: unknown option `accent'
usage: git grep [<options>] [-e] <pattern> [<rev>...] [[--] <path>...]

    --[no-]cached         search in index instead of in the work tree
    --no-index            f
### D. 장황 단순화 (1건)
- [verbose-block] line 35, </style> 직후 — <head> 안에서 location.replace()가 즉시 실행되는 스텁 페이지에 타이포그래피 시트 로드는 사실상 렌더에 기여하지 않음. 인라인 스타일과 Pretendard만으로 카드 표시 충분.

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 콘텐츠문의현황 — `3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 문의흐름지도 — `3. 웰페리온 가이드/cmo/funnel/문의흐름지도.html`
### D. 장황 단순화 (1건)
- [verbose-block] <head> 11번째 줄, 인라인 <style> 블록 바로 아래 — 0초 meta-refresh 리디렉션 전용 톰스톤 페이지이며, 렌더에 필요한 모든 스타일(body·a)이 이미 인라인 <style> 블록에 정의되어 있어 외부 CSS 로드는 불필요한 네트워크 왕복만 추가함.

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 내 .action-btn 스타일 하단 — 페이지 마크업 전체를 탐색해도 class="action-btn green" 조합 사용처가 0. 녹색 버튼은 모두 .btn-add 클래스를 사용.
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] ✅ 사용 조건 아코디언 3번째 li — 같은 내용이 ① info-box("방 이름은 카카오톡에서…정확히 일치해야") ② 입력 placeholder("카톡 채팅방 제목과 정확히 일치") ③ 아코디언 li 세 곳에 반복. 아코디언 li가 가장 제거 비용이 낮음.
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] header h1 내 badge span — v1.0 배지가 실제 릴리스 이력과 연결되지 않으면 초기 버전 표기로 방치될 가능성 있음. 배488이 명시된 현황과 버전 번호 체계가 따로 놀음.

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] CSS <style> 블록, .header 관련 규칙 묶음 — HTML 본문 어디에도 class="header-right" 요소 없음. 헤더 오른쪽 영역은 class="header-btns" 로 직접 배치됨. 이전 마크업 리팩토링 후 잔존한 규칙.
  - 게이트: 소비자 12건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] tabOverview .section-card h3 부제 / tabChannel .section-card h3 부제 — 두 곳 동일 문자열 — 개요 탭 '채널별 매출 요약'과 채널 탭 '채널별 매출 상세 분해' 섹션 헤더 부제가 완전 동일한 텍스트로 반복.
- [duplicate-text] tabOverview .info-banner / tabTrend .section-card .placeholder — 동일 취지 두 곳 — 개요 탭 info-banner '미마감 월은 정직하게 비웁니다'와 월별 추이 탭 placeholder '미마감 월은 빈칸(정직 표기)'이 같은 정책을 중복 안내.
### D. 장황 단순화 (3건)
- [verbose-block] tabReceivable 「미수금 OCF 영향 분석」 section-card 첫 번째 단락 — 데이터 소스 미배관 상태에서 OCF 개념 설명 단락이 선행하고 하위 세 항목이 전부 자리표시자임. 실무진 스캔 시 불필요한 교육 텍스트.
- [verbose-block] tabChannel #nsNote div 마지막 문장 — 막대 차트·게이지 색상이 JS gaugeClass()·bar-fill 클래스로 이미 시각화되어 있어 텍스트 범례 반복이 장황.
- [verbose-block] tabReceivable .info-banner 마지막 문장 + 직하 .placeholder — 동일 메시지 두 번 — info-banner '가짜 수치는 표시하지 않습니다'와 바로 아래 placeholder '표시할 실측값 없음'이 동일 의미를 중복 전달해 장황.

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] JS 하단 — 공유 모달 함수 직후 — applyFilter() 내 month/cat/approval 3단계 필터 로직이 getFilteredItems()에 동일하게 반복됨 — applyFilter()가 getFilteredItems()를 호출하면 제거 가능
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] JS 설정 섹션 — const API_URL 선언 바로 위 주석 — API_URL이 이미 실배포 URL로 채워진 상태이므로 '배포 후 교체' 안내 문구가 현실과 불일치
- [stale-notice] head 섹션 link 태그 — gate.js와 print_options.js는 _assets/ 경로를 쓰는데 이 링크만 assets/(언더스코어 없음)를 참조 — 경로 불일치로 404 가능성
### D. 장황 단순화 (3건)
- [verbose-block] :root CSS 변수 블록 (head > style) — --green-bg, --red-bg, --yellow, --yellow-bg, --blue, --blue-bg, --purple, --purple-bg, --orange-bg 9종이 파일 내 어디서도 var()로 참조되지 않음. 팔레트 예비 변수로 추정
- [verbose-block] JS localStorage fallback 섹션 — action 파라미터를 선언하지만 함수 본문에서 단 한 번도 사용하지 않음 — 항상 wellperion_expenses 고정 키만 읽음
- [dead-markup] filter-bar — filterCategory select — filterMonth는 populateMonthFilter()로 옵션이 동적 주입되지만 filterCategory에는 대응하는 populate 함수가 없어 항상 value='' 단일 상태 — applyFilter()의 if(cat) 분기가 사실상 항상 false

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 — .cm-msg 룰셋 아래 — JS 어디에도 className에 'ok'를 추가하는 코드 없음. submitCheck()는 '' 또는 'cm-msg err'만 설정; 저장 성공 시 closeOv()로 모달 닫기만 함. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] renderModeSelect 함수 직전 JS 주석 블록 — 날짜·버전(r2) 변경 이력 주석은 git 커밋 메시지로 처리할 내용 — 소스 본문 경위 기록 금지 원칙 위반. 부가적으로 'PIN 1202'을 클라이언트 소스에 평문 노출하며 상단 백엔드 주석과 중복.
### D. 장황 단순화 (1건)
- [verbose-block] <style> :root 변수 정의 라인 — 이 파일 어디에도 var(--amber), var(--blue) 참조 없음 — 디자인 토큰 템플릿 잔재 2종. 같은 라인 내 --green·--red는 실사용 중이므로 보존.

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ovWrite 모달 내부 — lock-note div + openWrite() JS의 wf_sub 세팅 동시 표시 — 동일 모달 내에서 '저장 후 수정 불가' 경고가 wf_sub(JS: '기한 … · 저장 후 수정 불가')와 lock-note div('⚠ 저장 후에는 수정할 수 없습니다…') 두 곳에 중복 표시됨
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] <script> 태그 최상단 첫 번째 주석 블록 — [변경 2026-07-04 r2] stale 버전 태그; 멘토 PIN(1202) 평문이 퍼블릭 소스에 노출 — 변경 이력은 git 커밋, PIN은 소스 외부로 이전 필요
- [stale-notice] WEEK_QUESTIONS 상수 선언 직전 인라인 주석 — 날짜·'확정본' 태그는 stale 버전 메타데이터; 파서 포맷 설명은 parseReflectNote 함수 구현으로 이미 자명
### D. 장황 단순화 (2건)
- [verbose-block] <style> 블록 내 .banner.err 룰셋 — setBanner() 호출 3곳 전수 확인 결과 'ok' 또는 빈 문자열만 전달 — 'err' 클래스가 동적으로 적용되는 경로 없음; 모호성 원칙 적용 A 대신 D 분류
- [verbose-block] renderPickList 함수 선언 직전 주석 블록 — 드문 엣지케이스를 3줄로 설명 — 실무진이 읽을 소스 주석보다 UI 안내 문구로 이전하거나 삭제가 적합

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (4건)
- [duplicate-text] line 159 .about-lead / lines 161–164 .about-stats — about-lead 산문에 등장하는 '한남동', '9년간', '스포츠·스파·커뮤니티·공간' 세 사실이 바로 아래 about-stats 카드(한남동/9년+/4in1)에서 동일하게 재진술됨 — 같은 섹션 안에서 산문+카드 이중 표현
- [duplicate-text] line 192 .perks2 ✨카드 — '한남동'과 '3,000평'은 이미 §회사소개 about-stats에서 독립 stat 카드 2장으로 제시된 수치 — 다른 섹션에서 동일 숫자 재사용
- [duplicate-text] line 151 .hero p / line 244 .cta-inner h2 — hero: '웰페리온에서 만들어갈 다음 이야기를 함께 시작하세요' — cta-inner h2: '당신의 다음 이야기, 웰페리온에서' — '다음 이야기' + '채용 공고 확인' 핵심 메시지가 페이지 상단·하단 두 곳에 반복
- [css-class] lines 102, 112–116 style 블록 — .dept.soon과 .dept.closed의 .tag/.btn/opacity 선언 3쌍이 속성값 100% 동일 — 공통 selector(.dept.soon, .dept.closed)로 병합 가능한 CSS 중복
### D. 장황 단순화 (1건)
- [verbose-block] line 159 §웰페리온은 어떤 곳인가요 — .about-lead — 동일 섹션의 about-stats 카드 4장이 한남동/9년+/3,000평/4in1 핵심 팩트를 이미 스캔 가능 형태로 커버 → 산문 단락은 가독성 대비 정보 밀도가 낮음

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] CSS <style> 블록, .m-values .t-sub 규칙 직후 — HTML 전체에 class="val-chips" 요소 없음. 실제 칩 목록은 .chips/.chip 클래스 사용 — val-chips는 완전 미사용 잔류 규칙
  - 게이트: 소비자 10건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (3건)
- [duplicate-text] .m-contact .cbox (☎ 문의 전화) 와 .m-foot .contact 푸터 두 곳 — 전화번호 02-6261-1202 · 나우열 매니저 조합이 연락 카드와 하단 푸터에 동일하게 중복 노출
- [duplicate-text] ① .m-salary .note ("4대보험 · 퇴직금 · 연차 적용") ② m-perk 카드 3개 제목·본문 ③ m-list 복리후생 리스트 — 4대보험·퇴직금·연차가 급여 카드 note, 개별 혜택 카드(m-perk 3개), 복리후생 리스트 세 곳에 중복 열거
- [duplicate-text] m-perk-wide 카드 p 말미 · m-list 복리후생 리스트 마지막 항목 — "직원할인(카페)" 문구가 AI 서포트 와이드 카드 설명 끝과 복리후생 리스트 두 곳에 중복
### D. 장황 단순화 (1건)
- [verbose-block] CSS <style> 블록, .values-diagram 규칙 직전 — 5줄 구현 이력 주석 — 1·2차 실패 경위까지 서술. 「/* PNG 고정: html2canvas SVG·div 시도 실패로 오프라인 래스터라이즈 대체(2026-07-18) */」 1행으로 압축 가능

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 — .m-hero .badge 룰셋 직후 — JS 마감 처리 로직이 #topStatus·#mContact 두 요소만 갱신하며 .m-hero 내 .badge 요소에 'closed' 클래스를 추가하는 코드가 이 파일 어디에도 없음.
  - 게이트: 소비자 5건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] m-contact 카드 cbox + m-foot .contact 배지 — 전화번호 02-6261-1202와 '나우열 매니저'가 지원·문의 카드와 하단 푸터 연락 배지에 동일하게 두 번 노출됨.
- [duplicate-text] '우대 사항·지원 서류' m-list 카드 + m-contact hint 텍스트 — '이력서(사진 포함)·자기소개서·보유 자격증 사본' 안내가 지원 서류 목록 카드와 문의 카드 hint 텍스트에 거의 동일하게 반복됨.
### D. 장황 단순화 (7건)
- [verbose-block] <style> 블록 — .values-diagram 룰 직전 4줄 주석 — 현재 선택 이유를 기술한 구현 이력 주석으로 운영에 필요한 정보가 없고 git 커밋 메시지에 속하는 내용.
- [verbose-block] 첫 번째 <script> 블록 첫 줄 주석 — 버전 태그(A-5 P2·G5)·날짜가 포함된 작업 추적 주석으로 git 로그 영역; 함수 동작은 코드에서 직접 파악 가능.
- [verbose-block] 두 번째 <script> 블록 첫 줄 주석 — 버전 태그·날짜가 포함된 작업 추적 주석; downloadPageAsJpg 함수 로직이 자기 설명적임.
- [verbose-block] 세 번째 <script> 블록 첫 줄 주석 — 버전 태그·날짜가 포함된 작업 추적 주석; git 로그 영역.
- [verbose-block] 첫 번째 <script> 블록 — 즉시 실행 함수 내 변수 선언 및 if(pageBucket) 분기 — <body>에 data-jobbucket 속성이 없으므로 pageBucket은 항상 빈 문자열이며 if(pageBucket) 분기는 이 페이지에서 절대 실행되지 않음.
- [dead-markup] .m-hero .badge 요소 — id="heroBadge" — id="heroBadge"는 CSS 룰·JS getElementById·querySelector 어디서도 참조되지 않아 기능 없는 유령 ID.
- [dead-markup] .quote 요소(id="sloganQuote") + .s-line 요소(id="sloganText") — id="sloganQuote"·id="sloganText" 둘 다 CSS·JS 어디서도 참조되지 않아 유령 ID 2개.

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 — .m-values 스타일 영역 — HTML 본문 어디에도 class="val-chips" 요소가 없음. m-values 카드는 img.values-diagram + .quote 만으로 구성되어 이 CSS 룰셋이 적용될 요소가 존재하지 않음.
  - 게이트: 소비자 10건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (3건)
- [duplicate-text] .m-salary .note 와 .m-shift 우대사항 리스트 — "영어 회화 가능자 우대 시 급여 추가 조정" 동일 사실이 연봉 카드 note("영어 회화 가능자 등 우대 시 급여 추가 조정")와 우대사항 li("외국어(영어) 회화 가능자 (급여 추가조정)") 두 곳에 중복 표기.
- [duplicate-text] .m-perk-wide 본문 과 .m-tags .chip — "근무 유니폼 제공"(m-perk-wide 설명 문장 말미)과 "유니폼 제공 등"(chips)이 동일 혜택을 두 곳에 표기.
- [duplicate-text] .contact-grid2 .cbox(.csub) 와 .m-foot .contact — "나우열 매니저 / 02-6261-1202" 연락처가 지원문의 카드 cbox와 하단 m-foot contact 두 곳에 동일하게 표기.
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] <style> 블록 — .m-hero 스타일 영역 — 마감 처리 JS가 #topStatus 와 #mContact 만 변경하며 hero .badge 에는 closed 클래스를 추가하지 않음. 이 CSS 룰이 실제 적용되는 경로가 없음.
- [stale-notice] 첫 번째 <script> 블록 첫 줄 주석 — 작업 ID·시안 버전([추가 YYYY-MM-DD A-5 ...]) 태그는 git 커밋 메시지에 속하는 이력 정보. 코드 내 stale reference.
- [stale-notice] 두 번째 <script> 블록 첫 줄 주석 — 동일 패턴 작업 ID 태그. 기능 설명은 유효하나 [추가 날짜 A-5] 접두 태그는 git 이력에 속함.
- [stale-notice] 세 번째 <script> 블록 첫 줄 주석 — 동일 패턴 작업 ID 태그.
### D. 장황 단순화 (3건)
- [verbose-block] <style> 블록 — .values-diagram 바로 위 — 개발 실패 경위·커밋 해시(42c3b999)·비교 이력을 4줄 CSS 주석으로 기술. 실무 가독성을 저하시키는 고고학적 기록으로 git 커밋 메시지에 속함.
- [dead-markup] .m-values 카드 — id="sloganQuote" 및 id="sloganText" — id="sloganQuote"(quote div)와 id="sloganText"(s-line div) 두 ID가 JS·CSS 어디에서도 참조되지 않음. 요소는 정상 렌더되나 ID가 불필요하게 잔류.
- [dead-markup] .m-hero .badge div — id="heroBadge" — id="heroBadge"가 JS·CSS 어디에도 참조되지 않으며 .m-hero .badge.closed CSS 룰도 현재 미작동(C 후보). ID 잔류.

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## AI운영한장 — `3. 웰페리온 가이드/AI운영한장.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] line 25, </style> 직후 <head> 내부 — 리다이렉트 전용 스텁으로 JS location.replace(line 13)가 즉시 실행되고 meta-refresh(line 12)가 0초로 설정되어 브라우저가 이 CSS를 렌더에 적용할 기회가 없음. 페이지 내 모든 선택자(body·h1·p·.box·a.btn·.hint)는 인라인 <style> 블록에 완결 정의되어 있어 외부 파일이 추가하는 스타일이 없음.
  - 게이트: 소비자 87건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] <head> 섹션, <noscript> 바로 다음 줄 — <head> 내 location.replace() 스크립트가 동기 실행되어 CSS 파싱·적용 전에 페이지가 교체됨. 리다이렉트 스텁에서 외부 CSS 파일은 실제로 화면에 적용되지 않는 불필요한 네트워크 요청.
  - 게이트: 소비자 87건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [dead-markup] <head> 영역, link 태그 — 페이지 전체가 인라인 <style> 블록만 사용하며, wp-typography.css의 클래스·ID·규칙을 참조하는 마크업이 단 한 곳도 없음. 순수 리다이렉트 스텁에 타이포그래피 시트는 불필요.
  - 게이트: 소비자 87건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] HTML 주석 블록 내 앵커 참조 — 주석의 이식 앵커가 #gm1-northstar-view인데, 실제 meta refresh·JS redirect·앵커 링크 세 곳 모두 #G1/northstar를 가리킴. 앵커가 이후 변경됐거나 주석이 낡은 상태.

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] <body> 첫 번째 줄, 리다이렉트 스텁 설명 주석 — 2026-07-03 완료된 마이그레이션 경위 주석 — 이미 실행·안정화된 이력 메모가 프로덕션 스텁 HTML에 잔류 중
### D. 장황 단순화 (1건)
- [verbose-block] <head> 인라인 <style> 블록 직후 — content="0" 즉시 리다이렉트 스텁에서 외부 CSS 파일 로드는 불필요 — 인라인 <style>이 이미 body·a 폴백 렌더링을 완전히 커버하며 타이포그래피 클래스가 이 페이지 본문에 전혀 사용되지 않음
