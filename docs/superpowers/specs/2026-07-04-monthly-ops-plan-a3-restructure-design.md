# 월간 운영 계획·보고 — A3 프린트 2층 구조 재설계 (design)

- 날짜: 2026-07-04
- 소유: 웰리(AI CEO) 두뇌 / 시토(CTO) 손 (엔진·렌더)
- 승인: GM (2026-07-04, brainstorming — 2층 구조·연간+월별 A3·연속 이니셔티브 5개 확정)
- 정본 파일: `status/monthly_ops_plan.json` (데이터) · `3. 웰페리온 가이드/월간운영계획.html` (렌더)

## 1. 문제 (현재 구조 한계)
- 현재 `months.{YYYY-MM}.objectives[]`에 **연속 과제(1월부터 이어지는 ERP·부서체계·채용 등)와 당월 신규 과제가 뒤섞여** 매월 스냅샷으로만 찍힘.
- 연속성·진척 궤적이 안 보이고, A3 프린트 기준 '전체 구조'가 없음.
- GM 요구: ①연속/신규 구분 ②매월 핵심과제 정리 ③진척도 표현 ④A3 프린트(연간+월별 2장).

## 2. 해결 = 2층 모델
### 층① 연속 이니셔티브 (multi-month threads)
새 top-level `initiatives[]` 레지스트리. 여러 달 이어지는 큰 줄기 = 연간 타임라인·월별 상단밴드의 소스.

확정 5개:
| id | 이니셔티브 | since~until | owner | 진척 소스 |
|---|---|---|---|---|
| erp-build | 🚀 웰페리온 ERP 구축 | 2026-01~08 | cto | **기존 `erp_progress` 재사용**(중복 금지) |
| dept-system | 🏢 4부서 체계 안정화(90일) | 2026-05~08 | coo | initiatives.monthly |
| hiring | 👥 직원 채용·교육(4직군) | 2026-06~ | chro/나우열M | initiatives.monthly |
| support-manual | 📋 지원부 매뉴얼·점검 체계 | 2026-06~ | coo | initiatives.monthly |
| strategy-roadmap | 🗺️ 전략 로드맵 6단계(상위 프레임) | 연간 | ceo | **기존 `strategy_roadmap` 재사용**(중복 금지) |

- **중복 금지(L01):** erp-build·strategy-roadmap는 기존 키(`erp_progress`·`strategy_roadmap`)를 `source_ref`로 참조만. 나머지 3개만 `initiatives[].monthly`에 월별 진척점 신규 보유.
- 스키마: `{id, title, icon, owner, since, until, northstar, target, source_ref?, monthly?:{"2026-06":{pct,status,note,delta?}}}`.

### 층② 당월 핵심과제 (month-specific)
- 기존 `months.{}.objectives[]` 유지 + 각 objective에 `initiative_id`(nullable) 추가.
  - `initiative_id` 있음 = 그 연속 이니셔티브의 **당월 실행분(이월·연속)**.
  - `initiative_id` 없음 = **당월 신규**(그달 시작·완결형: 여름방학특강·시설 리뉴얼·회원관리 변경·컴플레인/비품·내부 밸류업 등).
- 나머지 필드(owner·target·metric·status·progress·note·northstar)는 그대로.

## 3. 진척 표현
- 각 과제: **진척바(%) + 상태배지**(계획/진행/완료/이월) + **전월→당월 델타**(연속과제는 궤적).
- 델타 = 당월 pct − 전월 pct(연속 이니셔티브·이월 objective에 한함). 신규는 델타 없음(당월 착수).
- 상태배지 색: 계획=회색·진행=금색·완료=초록·이월=청록(기존 status_enum 재사용).

## 4. A3 프린트 (2장)
공통: A3 가로(`@page { size: A3 landscape }`), 좌측정렬·풀폭·인쇄 스타일. 기존 부서 A3 프린트 패턴(project_dept_a3_guideline_print) 준용. 화면 뷰 = A3 프린트 미리보기와 WYSIWYG(feedback_wysiwyg_print_unit_parity).

### 4-1. 연간 A3 (전체 로드맵)
- 이니셔티브 5행 × 월(1~12) 가로 타임라인. 각 셀 = 진척점(pct)·상태색. since~until 스팬 막대.
- 전략 로드맵 6단계 진척 스트립(기존 strategy_roadmap 재사용).
- 하단: 각 월 핵심과제(신규) 요약 칸(월별 1~2줄).
- 데이터 희소 구간(1~5월 상세 미기록)은 정직 표기(연속 스팬은 그리되 상세 없음 명시).

### 4-2. 월별 A3 (선택월 상세)
- **상단밴드:** 그달 연속 이니셔티브 진척(그 달 monthly point + 델타 궤적).
- **본문:** 그달 objectives를 **신규 / 이월(연속)** 2구획으로 나눠 표. 칼럼 = 과제 | 담당 | 목표 | 진척바 | 상태 | 북극성.
- 월 선택기(기존 유지).

## 5. 비목표 (YAGNI)
- 매출/지출 값은 이 파일 저장 금지(INC-001) — 💰 섹션 CFO 라이브 미러 유지.
- 1~5월 objectives 소급 입력 안 함(연속 스팬만 표기·상세는 6월부터).
- 개인 북극성·실무 도달율 로직 변경 없음(기존 렌더 유지).

## 6. 정합·재사용
- SSOT 규칙: 정본=json, 페이지=렌더만. 누적기록 금지(현행만).
- 기존 소스 재사용: `erp_progress`·`strategy_roadmap`·`practitioners`·`ai_utilization` 무손상.
- 매출·연간히스토리·점검·이슈 섹션 = 현행 유지(본 재설계는 '계획/과제' 층에 한정).

## 7. 검증
- JSON 파싱 OK · 라이브 시크릿 렌더(연간 A3·월별 A3 2026-07)에서 연속 5개 타임라인·당월 신규/이월 분리·진척바·델타 실측 · A3 인쇄 미리보기 WYSIWYG 확인 · 스크린샷.
