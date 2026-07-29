# CTO·CFO·CHRO 페이지 정리안 — 2026-07-14 (전사 마지막 웨이브 · GM 승인 대기)

감사 17페이지(CTO 2·CFO 3·CHRO 허브 6·CHRO 채용 6). **총 정리후보 21건.** 전건 보존확인: 데이터·GAS·onclick·폼·링크 무관.

## CTO (시토) — 3건
- 카톡전송관리: 죽은 `.callout` CSS 1 (grep 0)
- 자율현황: 죽은 `.rrow .rv.warn` CSS 1 + "북극성 임베드 제거" 중복 주석 3곳→1 통합 1

## CFO (시뽀) — 6건
- 매출지출현황: 죽은 백업파일 pointer 주석(백업 유실) 1 + write-only 변수 SALES_ETC/ETC_G(읽는 곳 0) 1
- 매출현황: 죽은 CSS(.receivable-*·미사용 .badge-*) 2 + 미사용 별칭변수(--primary 등) 1
- 지출현황: 미사용 별칭변수(--primary·--card-bg) 1

## CHRO (시로) — 12건
- 허브 index: ★**죽은 JS 대형 ~355줄**(구 v4 지원자모달 레이아웃 잔재·도달불가, .docs-grid류는 분리보존) + 죽은 `.pipe-*` CSS + OB_GUIDE 데이터 onboarding.html과 중복(검토요=단일화) = 3
- 허브 onboarding: 죽은 `.backlink` CSS 1 · onboarding-self: 죽은 `.wf-msg.ok` CSS 1
- 허브 office·structure·leave: 정리 불필요(깔끔)
- 채용 6p: 죽은 CSS 7 (.chip.gold/.legend 복붙·.s-probation 인라인패턴 3p·.perk 아이콘 font-size·.dept .btn+.btn)

## 카테고리
- **A 죽은코드(grep 0)**: 18건 — 위험 0 (CHRO index 355줄 포함)
- **B 낡은주석 정정**: 2건
- **검토요(데이터 단일화)**: OB_GUIDE 중복 1건 — 병합은 별건 검토

## 반영: GM 승인 → 각 도메인 적용(가역) → 웰리 라이브 검수. OB_GUIDE 단일화는 별도.
