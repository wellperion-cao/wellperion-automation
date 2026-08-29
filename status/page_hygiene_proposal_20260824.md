# 주간 페이지 위생 정리안 — 20260824 (하위모델 감사 → GM 승인 대기)

자동화: scripts/weekly_page_hygiene.py · 대상: coo

## 시설부 체계 — `3. 웰페리온 가이드/coo/check/시설부 체계.html`
### A. 죽은 코드(자동삭제 대상) (6건)
- [css-class] `shift-divider` — <style> 블록 — .progress 섹션 직후 10개 연속 규칙 — 옛 교대 점검 shift UI 잔재 — 탭 제거(2026-06-12) 후 HTML·JS renderBoard·renderPolicyBoard 등 어디에도 미사용
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `time-slot` — <style> 블록 — .slot-time 그룹 4개 연속 — 시간대 슬롯 UI 잔재 — 탭 재설계 후 HTML·JS 전체에 사용처 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `day-focus-section` — <style> 블록 — /* 요일별 트렐로 칸반 보드 */ 주석 바로 아래 — 주석에 '매뉴얼 탭 주 콘텐츠'로 언급되나 실제 칸반은 board-col 구조 사용 — day-focus-section·day-focus-title 클래스 HTML·JS 어디에도 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `group-submit-bar` — <style> 블록 — .group-submit-bar 그룹 4개 연속 — 그룹 제출 UI 잔재 — 현재 HTML 탭 구조 및 JS 렌더 어디에도 사용 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `closed-msg` — <style> 블록 — .hidden 바로 다음 줄 — 휴관 메시지 클래스 — HTML·JS 전체에서 closed-msg 사용처 없음; 휴관 상태 표시 로직 자체 미존재
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [css-class] `mode-badge` — <style> 블록 — .day-type.closed 직후 — 모드 뱃지 클래스 — HTML·JS 전체에 mode-badge 사용처 없음
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (2건)
- [duplicate-text] `가스누출대응절차` — ① tab-manual 공통 안전수칙 <li>; ② tab-guide ② 김종현 차장 [비상·예외 대응] <li> — 동일 절차 문구가 두 탭에 문자 그대로 중복 — 한 탭에서 다른 탭 참조 링크로 대체 가능
- [duplicate-text] `mpEsc` — 이달 부서 현황 탭 — mpEsc 정의부 — fmEsc(월간보고 탭 상단)와 함수 본문이 문자 그대로 동일 복제 — chunk1의 escapeHTML까지 합산 3중 중복
### C. 낡은 안내·버전 배지 (2건)
- [stale-notice] `version-badge-v1.0` — header h1 내부 <span> — 페이지 제목 오른쪽 — 초기 배포(2026-06-05) 이후 배64·배171·배406·배1042·배1074·배9182·배9199 등 대형 변경 다수 적용되었으나 버전 표기가 v1.0으로 stale 고정
- [js-function] `fcRoundChange` — fcRoundChange 함수 정의부 — 회차 전환 select UI 폐지(2026-07-08) 후 onchange 호출부 없는 호환성 스텁; 주석 자체가 '잔존 호출 대비'로 명시
### D. 장황 단순화 (5건)
- [verbose-block] `A3_GUIDELINE-comment` — JS 블록 — const A3_GUIDELINE 선언 직전 9줄 — 상수 구조·사용법·금지사항을 9줄로 장황히 기술 — // A3 가이드라인 압축본 {title, policy[], guide[]} — printA3Guideline 전용 한 줄로 충분
- [verbose-block] `fcAutoSaveNotes` — var _fcNotesTimer 선언 직전 7줄 주석 블록 — 결정 경위(GM 날짜·배포번호·현장 미확인)를 7줄 산문으로 박아 가독성 저해; '기계실 6칸은 12:00 게이트 없이 saveBoard 즉시 저장' 한 줄로 압축 가능
- [verbose-block] `fcWorkDelta` — fcWorkDelta 함수 선언 직전 4줄 주석 — 변경 요청 출처·외부 스크립트 참조·누적 방지 이유가 커밋 메시지 수준 산문으로 기재됨; 함수명과 seen 집합 본체가 이미 의도를 설명
- [verbose-block] `fcSave` — fcSave — Promise.all.then 콜백 내 _r0/_r1 오류 검사 직전 4줄 주석 — 과거 버그 경위·이전 코드 동작을 4줄 산문으로 기술; 현재 코드가 이미 해당 검사를 구현했으므로 이유 설명은 커밋 메시지 영역
- [verbose-block] `notify_round` — fcSave — try 블록 내 notify_round fetch 직전 3줄 주석 — 요청 출처(GM·날짜)·엔드포인트 설계 이유를 3줄 주석으로 박아 놓음; try{} 구조와 fetch body로 맥락이 이미 명확

## 지원부 체계 — `3. 웰페리온 가이드/coo/check/지원부 체계.html`
### A. 죽은 코드(자동삭제 대상) (4건)
- [dead-markup] `groupSubmitBarHtml` — groupSubmitBarHtml 함수 — return '' 이후 전체 사문 본문 — 함수 첫 줄 return ''로 이하 전체가 절대 실행 불가. eslint-disable-next-line no-unreachable 명시. GM 2026-06-12 '이 항목 제출 기능 제거' 주석 확인.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [dead-markup] `if(false && total>0&&done===total&&!isRoundSubmitted` — _onCkAfter 함수 내 정상(주간)모드 라운드 완료 자동제출 블록 — if(false && ...) 조건으로 어떤 상황에서도 진입 불가. 선행 주석 '자동제출 폐기'가 의도를 명시.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `inspMemoBoxHtml` — drawUI 직후 renderDayFocusSection 이전 — 점검자 배정 메모 상태변수·렌더·입력·저장 함수 블록 전체 — drawUI 내 주석 '렌더 제거. 함수 정의·백엔드 save_insp_memo는 무해해 잔존(다른 참조 없음)'으로 파일 자체가 호출 경로 없음을 선언. 이 청크 전체에 inspMemoBoxHtml 호출 없음.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
- [js-function] `onManualCk` — renderManualItems 이후 매뉴얼 탭 체크박스 이벤트 핸들러 — renderManualItems가 id='mcb_*' 체크박스를 전혀 생성하지 않음(주석 '매뉴얼 = 체크박스·완료표시 없음'). getElementById 항상 null 반환 → .checked 접근 시 TypeError.
  - 게이트: 자동적용 잠김(소유=coo 도메인 · 사람이 판단)
### B. 중복 설명 병합 (1건)
- [duplicate-text] `cd-zone` — #tab-manual 내 '둘째주 휴관 작업' manual-section(.cd-grid) — 동일 4구역 목록이 #a3-closedday-print(.cdp-grid)에도 정적 HTML로 중복 존재 — A·B·C·E 4구역 휴관작업 목록이 화면용(cd-card)과 A3 인쇄용(cdp-card) 두 곳에 별도 하드코딩 — 이미 B 락커룸 '거울 위 먼지 주의' 굵은글씨가 화면용엔 있고 인쇄용엔 없는 불일치가 발생해 비동기화를 확인
### C. 낡은 안내·버전 배지 (4건)
- [stale-notice] `v1.1` — header h1 — 페이지 제목 옆 인라인 버전 배지 — 헤더 제목에 박힌 버전·날짜·변경이력 설명이 2026-07-14(현재 2026-08-24) 기준 stale; '온도경고·반영완료·제출스냅샷'은 배포 changelog이지 운영 UI 상시 표시 정보가 아님
- [stale-notice] `수영팀청소일정예정` — #tab-guide 파트너팀(수영팀) 업장 청결 관리 표 — 3행(도보라인 때 제거 7/10·7/24 예정), 4행(화장실 7/20 예정), 5행(기타 7/23·7/24 예정) — 수영팀 7월 대청소 일정 3건이 '예정' 상태이지만 현재 날짜(2026-08-24) 기준 모두 경과 — 완료·취소·연기 여부 미기록 상태로 방치된 stale 일정; 2행 '진행중(7월 한 달간)'도 July 종료로 stale
- [stale-notice] `mrp-main-title` — #a3-monthly-print .mrp-doc — A3 월간보고 인쇄 전용 컨테이너 제목 및 전체 정적 본문 — A3 월간보고 인쇄 컨테이너에 '2026년 6월 작업 요약' 전체가 정적 HTML로 하드코딩됨; 다른 인쇄 컨테이너(a3-manual-print 등)와 달리 host-div가 없어 printA3Monthly()가 동적으로 내용을 교체하지 않는 구조이므로 현재 출력 시 6월 과거 데이터가 그대로 인쇄됨
- [stale-notice] `APP_VER` — 페이지 하단 버전 자동 최신화 IIFE 내 버전 상수 — 오늘(2026-08-24) 기준 약 56일 경과. 이후 배포 변경에 대해 localStorage 자동 초기화 미발동 → 구 캐시 잔존 가능.
### D. 장황 단순화 (2건)
- [dead-markup] `tab-manage` — #tab-check-f 아래, #tab-schedule 위 — 항목관리 탭을 매뉴얼 탭으로 통합 이전 후 남은 빈 패널 — 탭 버튼 목록 전수 확인 결과 switchTab('manage') 호출 버튼이 없고 콘텐츠도 비어 있어 실제 진입·표시 경로 없음; 주석의 'switchTab 참조 보존' 근거가 현재 코드에서 성립하지 않음
- [verbose-block] `_seedBtn` — renderManualItems 함수 내 셋업 안내 HTML 빌드 직전 빈 상수 선언 — 항상 빈 문자열. 템플릿 ${_seedBtn} 삽입부도 아무 출력 없음. 변수 선언과 ${_seedBtn} 참조를 동시 제거해도 동작 무변경.

## 운영부 체계 — `3. 웰페리온 가이드/coo/check/운영부 체계.html`
- ⚠️ 감사 실패: 조각 1/1: 타임아웃(900s)
