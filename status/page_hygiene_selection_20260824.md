# 주간 페이지 위생 — 웰리 선택 (2026-08-24)

원본: `status/page_hygiene_proposal_20260823.md`
선택자: AI CEO 웰리
실행자: 시토 (CTO)

## 집행 목록 8건

| # | 파일 | 유형 | 식별자 | 근거 |
|---|---|---|---|---|
| 1 | `3. 웰페리온 가이드/coo/check/지원부 체계.html` | js-function | `parseCSVLine` | loadStaffFromSheet가 FALLBACK 고정 전환 후 호출부 전무 |
| 2 | `3. 웰페리온 가이드/coo/check/지원부 체계.html` | dead-markup | `STAFF_CSV_URL` | parseCSVLine과 동일 — fetch 비활성화 후 참조 0 |
| 3 | `3. 웰페리온 가이드/coo/check/지원부 체계.html` | stale-notice | `autoSyncSeedsIfChanged` | 2026-06-27 폐지 선언, 첫 줄 return; 이후 전부 unreachable |
| 4 | `3. 웰페리온 가이드/coo/notice/notice_template.html` | dead-markup | `noticeImages` | v2.36 contenteditable 직접삽입 전환 후 배열 폐기, push·read·전달 없음 |
| 5 | `3. 웰페리온 가이드/coo/notice/notice_template.html` | css-class | `ntool-img-thumb` + `ntool-img-item` | 해당 요소를 생성하는 정적 HTML·JS 전무 |
| 6 | `3. 웰페리온 가이드/coo/notice/notice_template.html` | css-class | `ntool-fmt-bar-sep` | fmt-group 방식 전환 후 class='sep' 요소 생성 코드 없음 |
| 7 | `3. 웰페리온 가이드/wellperion_guide(main).html` | js-function | `deptCard` | IIFE 내부 선언 — render() 등 IIFE 내 호출부 0 |
| 8 | `3. 웰페리온 가이드/cfo/finance/매출현황.html` | css-class | `header-right` | HTML 전체에 class="header-right" 참조 0, header-btns가 역할 수행 |

## 스킵 이유 요약

- "소비자 건 확인" 표시된 항목(iSportMgmt·hint·wp-typography.css 등) → 참조 존재, 보존
- `⚠️ 대상 이름 없음` A등급 → 위치 특정 불가, 자동화 위험
- 시설부/지원부 체계.html 중 `quickAddBarHtml`·`_relocateDayItems` → 인접 onclick 잔존 가능성 언급됨, 1주 더 관찰
- `STAFF_SEED` note 인사 데이터 → GM 결재 필요
- 타임아웃 실패 21개 페이지 → 감사 미실행, 판단 불가
- C/D등급(stale 주석·장황) → 이번 주 A등급 우선 집행 후 다음 주 처리

## 시토 집행 지시

위 8건을 파일별 묶음으로 실행:
1. `지원부 체계.html` — parseCSVLine 함수·STAFF_CSV_URL 상수·autoSyncSeedsIfChanged 함수 제거 (3건)
2. `notice_template.html` — noticeImages 배열·ntool-img-thumb CSS·ntool-fmt-bar-sep CSS 제거 (3건)
3. `wellperion_guide(main).html` — deptCard 함수 제거 (1건)
4. `매출현황.html` — header-right CSS 룰셋 제거 (1건)

각 파일 수정 후 라이브 렌더 200·콘솔0 확인 필수.
