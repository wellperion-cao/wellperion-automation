# Deep Interview Spec: GM 보좌 자율화 체계 (GM-Aide Autonomy)

## Metadata
- Interview ID: di-gm-aide-20260702
- Rounds: 8 (+ Round 0 topology)
- Final Ambiguity Score: 4.5%
- Type: brownfield
- Generated: 2026-07-02
- Threshold: 0.05
- Threshold Source: GM 지시(5% 미만)
- Initial Context Summarized: no
- Status: PASSED
- 배(ship): CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237)
- 두뇌=웰리(CEO) / 엔진=시토(CTO) / 전 C-Level=도메인 관찰 기여

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.97 | 0.35 | 0.3395 |
| Constraint Clarity | 0.96 | 0.25 | 0.2400 |
| Success Criteria | 0.93 | 0.25 | 0.2325 |
| Context Clarity | 0.95 | 0.15 | 0.1425 |
| **Total Clarity** | | | **0.9545** |
| **Ambiguity** | | | **0.0455** |

## Topology
| Component | Status | Description | Coverage |
|-----------|--------|-------------|----------|
| ①관찰·학습 | active | GM 신호 수집 → 성향·습관 모델 | 수치 지표 + LLM 서술 프로필(`gm_profile.md`) 하이브리드, 일일 갱신 |
| ②포착 | active | 놓친 것·다음 할 것 감지 | 범위=시스템 확정 신호 + GM 지시 함의 (예측형 제외) |
| ③선제 실행·사후보고 | active | 적극 자율 실행 + 보고 | 가역=자율/비가역=제안, 웰리 위임→C-Level 실행→검증, G1 보고 |
| ④전 C-Level 도메인 포착 | active | 각 역할이 도메인 관찰 기여 | 공유 원장 append → 웰리 단일 두뇌 통합 |

## Goal
매일(+GM 지시 순간마다) 웰리가 **GM의 성향·습관을 학습한 프로필**과 **공유 관찰 원장**을 근거로, GM이 놓친 것·다음에 해야 할 것을 **선제 포착**한다. 가역적인 일은 담당 C-Level에 위임해 **스스로 처리(적극 자율)**하고 G1에 사후 기록하며, 비가역·금지 5종은 G1에 **제안 배로 대기**시킨다. 목적은 GM이 신경 안 써도 전사가 북극성으로 나아가도록 **웰리가 GM의 손발 겸 보좌**가 되는 것.

## Constraints (경계)
- **자율 수준 = 적극**: 금지 5종(결제·보안·금지·전략·공식값)만 GM 게이트. 그 외는 웰리가 스스로(위임 경유) 실행 후 사후보고.
- **가역성 안전장치**: 되돌릴 수 있는 것(초안·기록·정리·리마인드·발행 준비)만 자율 실행. 비가역(발행·삭제·외부 전송)은 자율 금지 → 제안만.
- **실행 주체**: 웰리는 직접실행 금지(헌법) 유지 — 포착·판단·위임·검증만. 실제 가역 실행은 **담당 C-Level executor**가 수행 → 웰리 검증 → G1 기록. (경량 G1 표면 정리는 웰리 직접 예외 유지)
- **단일 두뇌**: 전 C-Level은 자기 도메인 관찰을 **공유 원장에 append**만, 통합 포착·실행 판단은 웰리 한 곳(중복·엇갈림 방지).
- **보고 채널**: 새 알림 스트림 금지. 자율 실행=G1 입항완료 자동기록 / 제안=G1 대기 배(**사유 + KPI→북극성 경로** 포함). 카드 3일 미응답(GM은 경로 보여야 결정 — 메모리 feedback_gm_decides_by_seeing_kpi_path) 재발 방지.
- **루프 시점**: 하이브리드 — GM 지시 이벤트 즉시(지시 함의) + 06:30 일일 스캔(표류·미승인·루틴 누락) + 프로필 일일 갱신.
- **프라이버시**: GM 관찰은 요약·패턴 위주(민감 원문 저장 자제).
- **관측 정직**: 측정 가능한 것만 측정한 척(추정은 '추정' 라벨).

## Non-Goals (비목표)
- **예측형 포착 제외**: 패턴상 GM이 곧 필요할 것을 앞질러 예측·준비(매월 리포트 선행 등)는 v1 범위 밖. (확정 신호 + 지시 함의까지만)
- **개인 북극성(사랑하는 하루) 자동 개입 제외**: 관찰은 하되 개인 영역 자율 실행은 v1 제외.
- **비가역 자율 실행 영구 금지**: 발행·삭제·외부 전송은 아무리 확신해도 자율 실행 안 함.
- GM 결재 5종 자동 우회 금지.

## Acceptance Criteria
- [ ] **GM 개입 감소**: GM의 반복 지시·리마인드 횟수가 도입 전 대비 감소(원장 기준 추적).
- [ ] **포착 적중률**: 웰리 자율 실행의 사후 거부·롤백율이 낮음 + 제안의 GM 승인율이 높음.
- [ ] **사후보고 신뢰**: GM이 G1의 자율 실행 기록·제안을 무시/'꺼' 없이 유지·활용.
- [ ] **가역성 게이트 동작**: 비가역 작업이 자율 실행되지 않고 100% 제안으로만 뜸(테스트).
- [ ] **헌법 정합**: 웰리 직접실행 0건(위임·검증 경유), 실행은 담당 C-Level 태그로 G1 기록.
- [ ] **경로 투명**: 모든 제안 배에 'KPI→북극성 경로' 한 줄이 붙음.

## Assumptions Exposed & Resolved
| Assumption | Challenge (Round) | Resolution |
|------------|-------------------|------------|
| GM 성향을 어떻게든 '학습'한다 | R1 학습 형태 | 수치 지표 + LLM 서술 프로필 하이브리드 |
| 뭐든 놓친 건 다 챙긴다 | R2 포착 범위 | 확정 신호 + 지시 함의까지. 예측형 제외(비목표) |
| 적극이면 다 자율 실행 | R3 안전(오탐) | 가역성 기준 — 비가역은 제안만 |
| 조용한 자율이 좋다 | R4 Contrarian | 성공=GM개입↓·적중률·보고신뢰 3지표로 판정, 실패 신호 정의 |
| 각자 알아서 챙긴다 | R5 C-Level 구조 | 공유 원장 + 웰리 단일 두뇌 통합 |
| 어딘가 보고하면 본다 | R6 Simplifier | G1 항로 통합(새 알림 금지) — 카드 무시 재발 방지 |
| 언젠가 돈다 | R7 루프 시점 | 하이브리드(이벤트+06:30 일일) |
| 웰리가 직접 실행 | R8 실행 주체 | 웰리 위임·검증만, 담당 C-Level 실행(헌법 정합) |

## Technical Context (브라운필드 — 기존 물림)
- `status/gm_observation_ledger.jsonl` (46건 시드) + `scripts/gm_observation_seed.py` — 관찰 원장 MVP(이미 가동).
- `scripts/northstar_recommender.py` (06:30 --send) — 일일 스캔·제안 진입점으로 확장(추천기와 한 스케줄 물림 후보).
- `scripts/model_router.py` — claude CLI 폴백 두뇌(전멸 시 규칙폴백). 클로드 서버 일시장애에도 무중단.
- `status/_queue.json` + G1 항로 — 제안 배(대기)·자율 실행(입항완료) 기록 표면.
- `project_bridge_mechanized`(완료→다음 자동), `project_ai_self_learning_pipeline`(수집·요약·박제·제안) — 확장 토대.
- 자율 화이트리스트 = S2 공통탭. 헌법 웰리·시토 칸에 GM 보좌 자율화 정의 기록됨(bootsetup_matrix.json).

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| GM 프로필 | core | 선호·습관·자주 놓치는 것·루틴·수치지표 | 관찰 원장에서 학습·갱신 |
| 공유 관찰 원장 | core | observed_at·source·signal_type·summary·pattern_hint | 전 C-Level append, 웰리 read |
| 포착 이벤트 | core | 유형(확정신호/지시함의)·근거·가역성 | 원장·프로필 대비 감지 |
| 선제 액션 | core | 가역/비가역·실행주체(C-Level)·상태 | 포착→위임→실행→검증 |
| G1 보고 | supporting | 입항완료 기록 / 대기 배(사유+경로) | 선제 액션의 표면 |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability |
|-------|-------------|-----|---------|--------|-----------|
| 1 | 5 | 5 | - | - | N/A |
| 2 | 6 | 1 | 0 | 5 | 83% |
| 3 | 5 | 0 | 1 | 5 | 100% |
| 4-8 | 5 | 0 | 0 | 5 | 100% |

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 + 8 rounds)</summary>

- **R0 토폴로지**: 4개 구성요소(관찰·학습/포착/선제·보고/C-Level) 확정.
- **R1 학습 형태**: 수치 지표 + LLM 서술 프로필. (Ambiguity 53%)
- **R2 포착 범위**: 확정 신호 + GM 지시 함의(예측형 제외). (43%)
- **R3 안전장치**: 가역성 기준(가역=자율/비가역=제안). (32%)
- **R4 Contrarian·성공기준**: GM 개입 감소 + 포착 적중률 + 사후보고 신뢰. (19%)
- **R5 C-Level 구조**: 공유 원장 + 웰리 통합(단일 두뇌). (12%)
- **R6 Simplifier·보고**: G1 항로 통합(새 알림 금지). (9%)
- **R7 루프 시점**: 하이브리드(이벤트 + 06:30 일일). (6%)
- **R8 실행 주체**: 웰리 위임·검증 → 담당 C-Level 실행(직접실행 금지 유지). (4.5% ✅)
</details>
