# CPO·CMO 페이지 정리안 — 2026-07-14 (COO 확대 · GM 승인 대기)

감사 10페이지(CPO 3·CMO 7). **총 정리후보 29건.** 전건 보존확인: 실데이터·GAS·onclick·폼·SSOT·링크 무관.

## CPO (시포) — 18건
- **문의회원.html** (7,029줄, 전반 관리 양호): 죽은 CSS 10건(grep 0 — .funnel-arrow·.kpi-label/note·.cell-saving·.pii-reveal-btn·.month-cb·.dash-tag·.prep-*·.guide-acc*·.funnel-bar-month·.db-count-label) + 낡은 안내 2건(완료된 GAS 배포 온보딩 절차가 가이드탭·주석에 남아 열람자 혼동)
- **상품기획.html** (1,262줄): 죽은 CSS/JS 4건(아코디언·정책비교·수기드롭다운·배지변형, grep 0 ~60줄) + ⚠️"테스트 탭"(빈 스캐폴딩, **시포 작업공간일 수 있어 확인 요**) + 장황 주석(참고·강제 아님)
- **강습회원관리.html**: 정리 불필요(리다이렉트 스텁·깔끔)

## CMO (시모) — 11건
- **마케팅현황대시보드.html**: 죽은 JS 2건(_wpKey/_wpGate/_num, 오늘 대청소로 CSS 0)
- **월간마케팅보고서.html**: 죽은 CSS 3블록+변수 3쌍 + 죽은 JS(_wpKey/_wpGate) — 구 차트·PII게이트 잔재
- **홈페이지.html**: 죽은 @font-face 1건(local만·효과없음)
- **wp_inquiry_block.html**(ko): 낡은 주석 3건("4종→6종"·영상 placeholder·준비중 안내 — 전부 완료된 작업)
- **wp_inquiry_block_en.html**: 낡은 주석 1건("4→3종")
- **AI시리즈보드·문의흐름지도**: 정리 불필요(깔끔)

## 카테고리
- **A 죽은코드(grep 0·무시각변화)**: 21건 — 위험 0
- **B 낡은 안내·주석 정정**: 6건 — 완료된 온보딩 잔재
- **확인요**: 상품기획 테스트 탭 1건(시포)

## 반영: GM 승인 → 시포·시모 적용(가역) → 웰리 라이브 검수.
