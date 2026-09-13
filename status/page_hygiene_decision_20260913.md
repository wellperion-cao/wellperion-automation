# 주간 페이지 위생 결정서 — 20260913 (웰리 CEO 검토)

검토 원본: `status/page_hygiene_proposal_20260913.md` (310건)
결정일: 2026-09-13 · 결정자: AI CEO 웰리

---

## 🔴 긴급 — 개인정보 보안 (시토 즉시 처리)

| 파일 | 위치 | 내용 | 조치 |
|---|---|---|---|
| `문의회원.html` | `lessonLoad` 주석 내 | 실고객 성명·전화번호 `임하윤 010-7331-3903` 노출 | 주석에서 실데이터 제거 (익명 처리) |

---

## ✅ 시토 즉시 실행 승인 — 0-참조 · 삭제 안전

`리포 참조 0건(선언뿐)` 실측 확인 항목만. 기능 영향 없음.

| # | 파일 | 항목 | 종류 |
|---|---|---|---|
| 1 | `결재 현황 SSOT.html` | `kanban-col.col-rep` CSS — col-rep 컬럼 2026-06-16 폐지 | css |
| 2 | `wellperion_guide(main).html` O3 | `GM1_QUEUE_RAW_URL` — 큐 fetch 중단 후 호출부 소멸 | js const |
| 3 | `wellperion_guide(main).html` O4 | `GM1_QUEUE_RAW_URL` — 동일 (청크 내 중복) | js const |
| 4 | `오피스.html` | `wallBoardBBox()` — 말풍선 겹침 로직 교체 후 0건 | js func |
| 5 | `주차관리부 체계.html` | `pm_valet` A3_GUIDELINE 중복값 — 선언뿐 0건 | js obj |
| 6 | `주차관리부 체계.html` | `parkChecklistDailyN` getElementById — 항상 null | dead markup |
| 7 | `조직구조.html` | `읽기 DB — 7종 + 운영 탭 2종` h3 텍스트 — stale 카운트 | stale text |
| 8 | `인사허브 index.html` | `wpl-foot` — 0건(선언뿐) | verbose block |

---

## 📋 도메인별 C-Level 배분 (웰리 승인 · 해당 CLevel 실행 결정)

### COO 도메인 → 시우 결정
- 시설부 체계.html: `tb2` 변수 (A류 죽은코드 1건)
- 지원부 체계.html: `inspMemoBoxHtml` · `quickAddBarHtml` 클러스터 (A류 2건)
- 지원부 체계.html: `FALLBACK_STAFF` — DUTY_ROSTER와 불일치 (C류 · 기능 영향 가능)
- 업무 현황 SSOT.html: `deptHeadFor` · `PLAN_TEMPLATE` · `BUDGET_CATEGORIES` · `updateHeaderSub` dead code (A류 4건)
- 결재 현황 SSOT.html: `sheet-links` · `card-link-btn` · `getUser` · `setFilter` (A류 4건)

### CHRO 도메인 → 시로 결정
- 인사허브 index.html: `t-hwp` · `t-docx` CSS (A류 2건)
- 휴가.html: `deptband` · `shiftKind` · `usedOf` (A류 3건)
- 오피스.html: `gate` CSS 블록 · `screenSheen` · `sheen` · `boxRound` (A류 4건)
- 온보딩.html: `cm-msg.ok` CSS (A류 1건)
- 온보딩셀프.html: `lg_sub` id (A류 1건)
- 조직구조.html: `serif` CSS (A류 1건)

### CPO 도메인 → 시포 결정
- 문의회원.html: `holdStatusCard` — 도달불가 div (29참조 · C류)
- 문의회원.html: `_oaMaskPhone` 고아 함수 (C류 · 8참조)

### CTO 도메인 → 시토 결정
- 카톡전송관리.html: `--yellow` CSS 변수 (A류 · grep 오류로 수동확인 필요)

---

## ⏸️ 보류 — 추가 판단 필요

| 항목 | 사유 |
|---|---|
| `지원부 체계.html FALLBACK_STAFF` | 기능 폴백 경로 · 시우가 near-term 개편 여부 확인 후 결정 |
| `업무현황 SSOT ERP_API_ON=false` | 2026-09-06 지혈 되돌림 · 근본 수리 시점과 연동 결정 필요 |
| CFO 화면 전체 | `feedback_cfo_screens_belong_to_nawoolm_hands_off` 규칙 — AI 불개입 |
| 메인가이드 `evalEl` 하드코딩 (54/100) | Q3 종료 후 갱신 필요 · 시기 맞춰 처리 |
| 채용 페이지 중복 텍스트 B류 | 콘텐츠 결정 → 시모·시로 협의 후 |

---

## 통계 요약

| 구분 | 건수 |
|---|---|
| 긴급 (보안) | 1 |
| 시토 즉시 실행 | 8 |
| 도메인 C-Level 배분 | ~30 |
| 보류 | ~5 |
| 미적용 (파일 없음: 강습회원관리.html) | 해당 섹션 전체 |
| 나머지 (기호 없는 주석 정리 · B/D류 장황) | 시토가 도메인 일괄 정리 시 포함 |

---

> 다음 실행: 시토가 §🔴 + §✅ 를 이번 주 안에 처리. 도메인 배분 건은 각 C-Level이 본인 화면 작업 시 함께 처리.
