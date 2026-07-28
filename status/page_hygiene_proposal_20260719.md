# 주간 페이지 위생 정리안 — 20260719 (하위모델 감사 → GM 승인 대기)

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

## 강습팀 업장관리 — `3. 웰페리온 가이드/coo/check/강습팀 업장관리.html`
- ⚠️ 감사 실패: 파일 읽기 실패: [Errno 2] No such file or directory: 'C:\\Users\\jjky0\\welperion-automation\\3. 웰페리온 가이드/coo/check/강습팀 업장관리.html'

## 전사_일정 — `3. 웰페리온 가이드/coo/check/전사_일정.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] CSS block — .ecard 그룹 하단 — `.na` 클래스를 `.ecard`에 부여하는 JS·HTML 코드가 전무함 — 구 편집 UI 잔재 · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [css-class] CSS block — .ecard-top 룰셋 — inlinePanelHtml()·정적 HTML 어디서도 class="ecard-top" 생성 없음 — 구 편집 UI 잔재
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] CSS block — .ecard-top .ename 룰셋 — .ecard-top 자체가 생성되지 않으므로 자식 규칙도 사문; .ename 클래스 할당 코드 없음
  - 게이트: 소비자 4건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] .honesty 배너 첫 문장 — GAS SSOT(schedule_ssot.json)에 항목 데이터가 이미 채워진 경우 '확인 중' 상태는 해소됐을 수 있음
### D. 장황 단순화 (3건)
- [verbose-block] CSS block — .efield input 복합 선택자 — 복합 선택자 내 `.ecard-top input` 파트만 죽은 선택자 — `.efield input,.efield select`로 줄이면 충분
- [verbose-block] CSS block — .efield input:focus 복합 선택자 — 복합 선택자 내 `.ecard-top input:focus` 파트만 죽은 선택자 — 앞 두 선택자만 남기면 충분
- [verbose-block] JS block — efRepeat() 함수 직후, saveToServer() 직전 — 이미 제거된 함수들의 폐기 경위를 나열하는 이력 주석 — 코드 동작과 무관, SSOT 규칙상 경위는 git 이력에 귀속

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

## 문의회원 — `3. 웰페리온 가이드/cpo/member/문의회원.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 강습회원관리 — `3. 웰페리온 가이드/cpo/member/강습회원관리.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> :root 선언 블록 3번째 줄 (--border:#3d3835 직전) — 페이지 내 어떤 CSS 규칙·인라인 스타일에도 var(--accent) 또는 var(--accent-bg) 참조 없음. 타 페이지 템플릿 복사 잔여 변수 2개.
  - 게이트: git grep 오류(rc=129): error: unknown option `accent'
usage: git grep [<options>] [-e] <pattern> [<rev>...] [[--] <path>...]

    --[no-]cached         search in index instead of in the work tree
    --no-index            f

## 상품기획 — `3. 웰페리온 가이드/cpo/product/상품기획.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 마케팅현황대시보드 — `3. 웰페리온 가이드/cmo/funnel/마케팅현황대시보드.html`
- ⚠️ 감사 실패: 파일 읽기 실패: [Errno 2] No such file or directory: 'C:\\Users\\jjky0\\welperion-automation\\3. 웰페리온 가이드/cmo/funnel/마케팅현황대시보드.html'

## 문의흐름지도 — `3. 웰페리온 가이드/cmo/funnel/문의흐름지도.html`
- (정리 후보 없음)

## 월간마케팅보고서 — `3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html`
### A. 죽은 코드(자동삭제 대상) (3건)
- [css-class] CSS <style> 내, 화면용 월 선택기 블록 — .month-select-wrap 다음 줄 — HTML에 class="month-select-lbl" 사용처 없음. 같은 역할을 .tb-month .lbl{...}이 실제로 담당 중. · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [css-class] CSS <style> 내, 화면용 월 선택기 블록 첫 줄 — HTML에 class="month-select-wrap" 사용처 없음. @media print{.month-select-wrap{display:none!important}} 도 함께 dead. 실 월 선택기 DOM은 .tb-month > select#monthSelect 구조.
  - 게이트: 소비자 2건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
- [css-class] CSS <style> 내, .panel 바로 다음 줄 — HTML에 class="panel-flush" 사용처 없음. .panel만 실제로 사용 중. 인쇄 CSS의 .panel,.panel-flush 그룹 선택자 중 panel-flush 부분도 dead.
  - 게이트: 소비자 3건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] 표지 .cover-notice 및 .page-footer 두 곳에 동일 취지 중복 — PII 미포함 고지가 표지(.cover-notice)와 푸터(.page-footer)에 각각 등장. 인쇄 단면 보고서 기준 표지 한 곳으로 충분.
### D. 장황 단순화 (2건)
- [js-function] JS 두 번째 <script> 블록, const GAS_URL 선언 직후 — 인자를 그대로 반환하는 no-op 래퍼. 3개 fetch 호출이 모두 _wpUrl()로 감싸져 있으나 실효 없음. 주석 자체가 '폐기·passthrough'로 명시.
- [css-class] CSS <style> 내, 수기 입력란 블록 (주석+4개 규칙). 인쇄 CSS에도 .manual-section{border:...} 추가 포함. — HTML에 .manual-section·.manual-row 사용처 없음. '호환 유지' 코멘트로 인해 A 모호 원칙 적용 → D 분류. .manual-input은 GM 코멘트 입력란에서 실사용 중이므로 보존.

## 홈페이지 — `3. 웰페리온 가이드/cmo/home/홈페이지.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## AI시리즈보드 — `3. 웰페리온 가이드/cmo/series/AI시리즈보드.html`
### C. 낡은 안내·버전 배지 (3건)
- [stale-notice] JS — buildM5Map 함수 정의 위 섹션 주석 — 섹션 주석은 'M3 큐'라 명시하지만 함수명·변수명 전체(buildM5Map, m5Map, m5Status)는 M5를 사용. 표시 레이블('M3 반영', 'M3 검수대기')과 resolveBadge 내 '// M3 상태 우선' 주석은 M3로 통일돼 있어 코드 식별자만 구버전 M5 명칭으로 방치된 상태.
- [stale-notice] JS — resolveBadge 함수 내부, 두 번째 줄 — 주석 'M3 상태 우선'이지만 직후 참조 변수는 m5Status(M5 명칭). buildM5Map 섹션 주석과 동일한 M5→M3 미반영 패턴.
- [stale-notice] JS — buildM5Map else 블록 — 주석 '가장 최근 상태 유지'는 실제 동작과 모순. 실제 동작은 '먼저 들어온 항목 유지, 이후 발행완료만 덮어씌움(선착순 + 발행완료 예외)' — 배열 순서가 '최근순'임을 보장하지 않으면 주석이 거짓이 됨.
### D. 장황 단순화 (1건)
- [verbose-block] JS — renderCard 함수 첫 줄 — 유일한 호출부(renderTable)에서 hasCard = ep.has_card && cards && cards[String(ep.num)] 가 truthy일 때만 호출되므로 card는 항상 non-null — null 가드 미도달. 동일 폴백 텍스트가 renderTable 삼항 else 분기에도 이미 존재.

## wp_inquiry_block — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] line 72 — .wlp-inq 변수 선언부 (두 번째 <style> 블록 첫 줄) — 파일 전체에서 var(--paper) 참조 0회 — .type-card는 background:#fff 하드코딩 사용, 이 변수를 소비하는 CSS 규칙 없음
  - 게이트: git grep 오류(rc=129): error: unknown option `paper'
usage: git grep [<options>] [-e] <pattern> [<rev>...] [[--] <path>...]

    --[no-]cached         search in index instead of in the work tree
    --no-index            fi
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] line 89 CSS 룰셋 + line 143 HTML <div class="divider-coral"> — 클래스명 'coral'이지만 background:var(--beige) 적용 — 시안F GM 최종확정 때 '코럴 최소' 방침으로 디바이더 색이 coral→beige로 전환됐으나 클래스명 미갱신
### D. 장황 단순화 (1건)
- [verbose-block] line 1–63 파일 최상단 HTML 주석 전체 (~63줄) — GM 피드백①②③ 및 방향전환 7회 전 과정의 결정 경위·폐기 사유가 SSOT 본문에 삽입 — CLAUDE.md '결정 경위·사고 기록·폐기 사유 본문 금지' 위반; 이력은 짝 이력 파일에 날짜별 append 대상이며 파일 정체성(파일명·주입대상·날짜·최종 설계 결론) 3–4줄만 남겨야 함. 특히 line 4–5의 '다크 풀블리드 히어로+화이트 에디토리얼' 설명은 이미 폐기된 B안 초안 묘사로 현행 시안F와 불일치

## wp_inquiry_block_en — `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] 17줄 subtitle span ↔ 69–71줄 하단 p 태그 — "By Appointment Only" 개념이 상단 subtitle(17줄)과 하단 문구(70줄 "…by appointment only. Walk-ins are not available.") 두 곳 반복; 하단이 더 구체적이므로 상단 span의 · By Appointment Only 토큰 제거 가능 — 단 High-end 포지셔닝 문구는 페이지 내 유일하므로 span 전체 삭제 시 해당 문구 대안 필요
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] 32–39줄, video wrapper 내부 플레이스홀더 UI 블록 — "Video coming soon" 문구가 기한 없이 방문자에게 노출; 영상 미준비라면 섹션 전체 display:none이 UX상 적절
### D. 장황 단순화 (2건)
- [verbose-block] 21–29줄, video 섹션 진입 주석 블록 — 코드 샘플·옵션 설명 9줄 개발자 가이드가 프로덕션 HTML에 인라인; <!-- TODO: replace with video --> 한 줄로 충분
- [css-class] 30줄, video 섹션 외부 래퍼 div — <style> 블록에 .wp-inq-video 룰 없음, 파일 내 JS 없음; 레이아웃은 인라인 스타일로 완결 — 클래스가 현재 시각·동작에 기여 없음

## 카톡전송관리 — `3. 웰페리온 가이드/cto/automation/카톡전송관리.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 자율현황 — `3. 웰페리온 가이드/자율현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출지출현황 — `3. 웰페리온 가이드/cfo/finance/매출지출현황.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 매출현황 — `3. 웰페리온 가이드/cfo/finance/매출현황.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 — .header-btns 규칙 바로 아래 — HTML 전체에 class="header-right" 사용처 없음; 헤더 우측은 .header-btns 가 동일 flex 레이아웃 별도 선언
  - 게이트: 소비자 9건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (1건)
- [duplicate-text] tabChannel > #nsNote HTML / tabOverview > #cmpNote JS 문자열 — 채널탭 nsNote '연 목표 72억(GM 결재 확정)이 유일한 확정 목표'와 개요탭 cmpNote JS '확정 목표는 연 72억뿐'이 서로 다른 탭에서 동일 사실 반복
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] header > .header-meta 인라인 — JS 성공 시 rm.asOf 값으로 덮어쓰나 오류·미연결 시 'v1.0' 버전 배지 고정 노출 — 갱신 메커니즘 없는 하드코딩 버전명
- [stale-notice] tabChannel > 채널 테이블 .section-card 하단 — renderChannels()가 채널 데이터 로드 후 테이블 tbody 만 채우고 이 노트 div 를 제거·숨김 처리하지 않아 데이터가 있어도 '소스 미배관' 문구 상시 잔류
### D. 장황 단순화 (2건)
- [verbose-block] tabReceivable > 미수금 OCF 영향 분석 section-card 첫 문단 — CFO 실무진 대상 내부 ERP 페이지에서 OCF 개념 정의 불필요; 아래 placeholder 3줄과 독립적으로 제거 가능
- [verbose-block] tabChannel > #nsNote HTML 마지막 문장 — gaugeClass() JS 로직과 gauge-fill/bar-fill CSS 색상 클래스가 이미 시각으로 전달하는 내용을 텍스트로 중복 설명

## 지출현황 — `3. 웰페리온 가이드/cfo/finance/지출현황.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] line 317 — JS <script> 상단 설정 블록, const API_URL 선언 바로 위 — URL이 이미 실 운영 엔드포인트로 채워져 있어 '배포 후 교체' 지시는 이미 완료된 작업을 가리키는 낡은 주석
### D. 장황 단순화 (1건)
- [verbose-block] lines 11–16 — :root 블록 — 이 파일의 CSS 규칙 및 JS 인라인 스타일 어디에도 참조되지 않는 토큰 9개(--green-bg·--red-bg·--yellow·--yellow-bg·--blue·--blue-bg·--purple·--purple-bg·--orange-bg) — 같은 줄의 --green·--red·--orange는 --success/--danger/--warning alias를 통해 실사용 중이므로 줄 전체 삭제 불가

## 인사허브 — `3. 웰페리온 가이드/chro/hub/index.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 휴가 — `3. 웰페리온 가이드/chro/hub/leave.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [js-function] JS — openApply() 직전 줄 — usedAnnual2026()로 완전 대체됐으며 코드 전체에서 단 한 번도 호출되지 않음 · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [css-class] CSS — covrow 스타일 블록 인근 — JS 렌더 함수 전체와 HTML 정적 마크업 어디에도 deptband 클래스를 적용하는 코드가 없음; covrow·deptfirst가 동일 역할 수행 · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [dead-markup] JS — 두 번째 message 리스너(resolveGate 호출) 직전 — erpLoad 참조를 저장했으나 이후 코드 전체에서 단 한 번도 읽히거나 호출되지 않는 미아 변수 · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
- [dead-markup] JS — erpBulk() 아래, 게이트 구현 이전 블록 — 게이트 도입 후 두 번째 message 리스너(resolveGate 경유)로 완전 대체됐으나 삭제되지 않아 wp-pass 수신 시 erpLoad()가 이중 실행됨
  - 게이트: 소비자 5건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] JS — moveMonth() 바로 다음 — '오늘' 버튼이 실제 오늘(new Date())이 아닌 2026-06-01로 고정 — 현재 날짜(2026-07-19)에서 누르면 6월로 역행
### D. 장황 단순화 (1건)
- [verbose-block] JS — isOpener·isCloser 정의 다음 — 함수는 정의됐으나 render 루프가 항상 'sh-work'를 하드코딩해 shiftKind()를 단 한 번도 호출하지 않음; 연계 CSS(.sh-open·.sh-close·.sh-mid 선택자)도 DOM에 실제로 붙지 않아 사문화

## 오피스 — `3. 웰페리온 가이드/chro/hub/office.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 온보딩 — `3. 웰페리온 가이드/chro/hub/onboarding.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] 77번줄 — <style> 블록 .cm-msg 룰셋 그룹 내 — JS 전체에서 .ok 클래스를 cm_msg에 추가하는 코드 없음 — submitCheck 성공 경로는 'cm-msg'(351번줄), 실패는 'cm-msg err'(358번줄)만 사용; .ok는 미참조 · 자동적용 조건 충족(다음 GM go 시 적용 예정)
  - 게이트: 소비자 0건(선언 자체만) — 자동삭제 가능
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] 174~176번줄 — renderModeSelect 함수 직전 — SSOT 규칙(결정 경위·사고 기록 본문 금지) 위반 인라인 변경이력 — '[추가 날짜·r2]'·'무변경 보증' 문구가 소스에 잔류
### D. 장황 단순화 (3건)
- [verbose-block] 150~151번줄 — JS 블록 최상단, EXEC_URL 상수 직전 — PIN 값(1202)을 GitHub Pages 공개 소스에 노출; '마스터 비밀번호 없음' 자기보증은 GAS 스코프 제한이 이미 담보하므로 장황
- [verbose-block] 193번줄 — proceedCheckin 함수 직전 — 함수명 proceedCheckin과 호출 경로(chooseMode→proceedCheckin)로 이미 자명 — 제거 후 가독성 동일
- [css-class] 11번줄 — :root 블록 — 파일 전체에 var(--amber)·var(--blue) 참조 없음 — 미사용 팔레트 변수 2종; --green·--red는 실사용 중

## 온보딩(셀프) — `3. 웰페리온 가이드/chro/hub/onboarding-self.html`
### B. 중복 설명 병합 (1건)
- [duplicate-text] ovWrite 모달 — textarea 세 개 하단 lock-note div — '저장 후 수정 불가' 경고가 wf_sub(openWrite에서 '기한 … · 저장 후 수정 불가'로 주입)와 lock-note 두 곳에 동시 표시됨
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] JS 최상단 블록 주석 — EXEC_URL 선언 직전 (script 태그 첫 번째 주석 2번째 줄) — 2026-07-04에 이미 적용 완료된 변경의 버전 이력 태그 — 현재 코드에 반영된 상태로 주석 내 잔존하는 날짜 이력 마커
### D. 장황 단순화 (2건)
- [dead-markup] ovLogin 모달 본문 — 비밀번호 label 직전 — id='lg_sub'가 JS 전체에서 getElementById 등 참조 0건 — 정적 텍스트 요소에 기능 없는 ID 부여
- [css-class] CSS 스타일 블록 — .banner.ok 바로 위 줄 — setBanner() 호출부 전수 확인 결과 cls 인자로 'err'를 전달하는 케이스 0건 — .banner.ok만 실사용됨

## 조직구조 — `3. 웰페리온 가이드/chro/hub/structure.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용허브 — `3. 웰페리온 가이드/chro/recruiting/index.html`
### B. 중복 설명 병합 (2건)
- [duplicate-text] line 191 — perks2 섹션 ✨ 프리미엄 환경 perkcard p 본문 — '3,000평' 수치는 line 162 about-stats 카드(통합 라이프스타일 공간)에서 이미 제시됨. perkcard에서 '한남동 3,000평'으로 재진술은 중복.
- [duplicate-text] line 158 — about-lead 단락 (about-stats 카드 4개와 정보 완전 중첩) — about-lead 산문이 담는 4개 사실(한남동·9년·스포츠·스파·커뮤니티·공간)이 바로 아래 about-stats 카드 4개(한남동/9년+/3,000평/4in1)에 스캔형으로 재제시됨. 산문이 추가하는 정보가 없어 두 레이어가 완전 중복.
### D. 장황 단순화 (1건)
- [verbose-block] line 241–246 — 부서 grid 직후 마무리 CTA 블록 — 히어로 H1 '기준을 만드는 사람들'과 히어로 P '채용 공고를 확인하고 … 시작하세요'를 구문만 달리해 재진술. 부서 grid 아래에서 링크·버튼 없이 스크롤 길이만 늘리며 신규 정보 0.

## 채용-쇼퍼 — `3. 웰페리온 가이드/chro/recruiting/chauffeur.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] CSS <style> 45–46번 줄 — .m-values 블록 직후 — HTML 전체에 class="val-chips" 사용처 0건. 실제 칩 UI는 .chips/.chip 클래스가 담당
  - 게이트: 소비자 10건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (2건)
- [duplicate-text] .m-perk-wide 카드 p 태그 말미 + .m-list 복리후생 리스트 — '직원할인(카페)'가 AI 서포트 카드 설명 말미에 별개 혜택으로 끼워 넣기식 기재 + 복리후생 리스트에 중복. AI 카드 설명과 의미적으로 무관
- [duplicate-text] .m-salary .note + .m-perk 카드 2종(4대보험 완비·퇴직금·연차 제도) + .m-list 복리후생 리스트 — 동일 혜택 3종이 급여 카드 note·perk 카드 2개·복리후생 리스트에 총 3회 중복 언급
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] CSS <style> — .values-diagram 규칙 바로 위 — SVG→div→PNG 시도 실패 경위·커밋 해시(42c3b999) 등 결정 이력 주석. 현행 구현(PNG img 단일 태그)이 확정된 이후 불필요. git 로그가 정본
- [stale-notice] 첫 번째 <script> 블록 1행 — 태스크 ID(A-5, P2·G5)·시안 버전(시안2)을 박아둔 작업 이력 주석. 구현 확정 이후 죽은 메타 태그
- [stale-notice] 두 번째 <script> 블록 1행 — 시안 버전 배지(2026-07-18 A-5) 포함 작업 이력 주석. 현행 구현 확정 후 불필요
- [stale-notice] 세 번째 <script> 블록 1행 — 시안 버전 배지(2026-07-18 A-5) 포함 작업 이력 주석. 현행 구현 확정 후 불필요

## 채용-골프프로 — `3. 웰페리온 가이드/chro/recruiting/golfpro.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-운영 — `3. 웰페리온 가이드/chro/recruiting/operations.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-주차 — `3. 웰페리온 가이드/chro/recruiting/parking.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 채용-사우나 — `3. 웰페리온 가이드/chro/recruiting/sauna.html`
### A. 죽은 코드(자동삭제 대상) (1건)
- [css-class] <style> 블록 · .m-values 관련 규칙 앞 2줄 — HTML 전체에서 class="val-chips" 참조 0건. 인재상 칩 UI가 PNG 이미지로 대체되며 남겨진 잔존 규칙.
  - 게이트: 소비자 10건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등
### B. 중복 설명 병합 (3건)
- [duplicate-text] .m-perk 카드 '명확한 진급 체계' p 텍스트 + .m-ladder 카드 세 step 박스 — '주임→반장→팀장 3단계 진급'이 m-perk 카드 설명 문장과 m-ladder 시각 박스 두 곳에 동일 내용으로 반복됨.
- [duplicate-text] .m-shift '우대 사항' li + .m-tags .chip 중 '서비스 마인드 및 태도' — '서비스 마인드 보유'(우대사항 리스트)와 '서비스 마인드 및 태도'(복지·스킬 칩) 두 곳에 중복.
- [duplicate-text] .m-perk-wide p 끝 '유니폼 제공(근무 유니폼 회사 지급)' + .m-tags chip '유니폼 제공 등' — 유니폼 지급 사실이 혜택 카드 본문과 칩 두 곳에 중복 표기됨.
### C. 낡은 안내·버전 배지 (4건)
- [css-class] <style> 블록 · .m-hero .badge 규칙 바로 아래 줄 — 마감 동기 IIFE는 mContact·topStatus만 업데이트하며 badge 요소에 .closed를 추가하지 않음 — 이 CSS는 현재 어떤 경우에도 적용되지 않음.
- [stale-notice] <style> 블록 · .values-diagram 규칙 직전 4줄 블록 주석 — 이미 실행된 설계 결정의 경위·실패 이력이 CSS 소스 본문에 잔존. 프로젝트 SSOT 원칙(결정 경위·사고 기록 본문 금지) 위배 — git 커밋 메시지 소관.
- [stale-notice] 3개 <script> 블록 각 첫 줄(나머지 2개: '// [추가 2026-07-18 A-5] JPG 다운로드 버튼…', '// [추가 2026-07-18 A-5] 자체 지원 접수 폼…') — 날짜·버전 태그 포함 인라인 변경 이력 주석 3건이 JS 소스에 잔존. git 커밋 메시지 소관, 소스 내 변경 이력 본문 금지 원칙 위배.
- [css-id] HTML · .quote div id="sloganQuote" 및 내부 .s-line div id="sloganText" — id="sloganQuote"·id="sloganText" 두 ID 모두 세 <script> 블록 어디에서도 참조되지 않음 — 슬로건 동적 교체 기능 계획의 잔존 흔적으로 추정.

## 헌법한장 — `3. 웰페리온 가이드/헌법한장.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 전사회의 — `3. 웰페리온 가이드/전사회의.html`
- ⚠️ 감사 실패: 타임아웃(240s)

## 웰페리온 대시보드(웹) — `3. 웰페리온 가이드/wellperion_dashboard_web.html`
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] JS 블록 최상단 · APPS_URL 선언 한 줄 위 — APPS_URL이 이미 실제 /exec URL로 채워져 있어 배포 지시 주석이 이행 완료됨 — 존치해도 무해하나 실무진 혼동 여지
- [stale-notice] footer 인라인 텍스트 — PIN 인증 후 이름·연락처가 포함된 90일 미만 명단(roster)이 렌더링되므로 '개인정보 미포함' 문구가 사실과 불일치
- [stale-notice] JS 블록 · SNAPSHOT 상수 선언부 — 스냅샷 날짜 2026-06-08 기준 오늘(2026-07-19) 대비 41일 경과; 6월 데이터가 22.97% 진행 중 상태로 고정돼 GAS 장애 시 실무진이 최신 수치로 오판할 위험
- [stale-notice] header > .sub 텍스트 노드 — 연도 '2026년'이 하드코딩돼 이듬해 수동 수정 필요; JS로 동적 삽입하거나 GAS 응답에서 연도를 받아 치환 권장

## index(리다이렉트 스텁) — `3. 웰페리온 가이드/index.html`
- (정리 후보 없음)

## 항해지도(리다이렉트 스텁) — `3. 웰페리온 가이드/항해지도.html`
### C. 낡은 안내·버전 배지 (1건)
- [stale-notice] line 8 — HTML 주석 블록 — 주석이 이식 목적지를 #gm1-northstar-view 로 기록하지만 실제 meta refresh(line 3)·JS(line 23)·앵커 링크(line 20) 세 곳 모두 #G1/northstar 를 사용 — 주석의 앵커 ID가 실제 배선과 불일치
### D. 장황 단순화 (1건)
- [verbose-block] lines 5–9 — 파일 상단 HTML 주석 블록 — 5줄 이력 서술은 25줄 스텁 파일에서 비중 과다; '외부 북마크용 리다이렉트 스텁 — 삭제 금지 (→ #G1/northstar, 2026-07-06 시토)' 1줄로 압축 가능

## northstar_today(리다이렉트 스텁) — `3. 웰페리온 가이드/northstar_today.html`
### D. 장황 단순화 (1건)
- [verbose-block] <body> 최상단 HTML 주석 — 2026-07-03 완료된 마이그레이션 경위를 소스 주석으로만 보존 — 이미 해소된 히스토리이며, 리다이렉트 meta·body 문구가 목적을 충분히 전달하므로 장황 주석으로만 남음.
