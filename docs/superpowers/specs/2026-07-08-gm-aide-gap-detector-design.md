# Deep Interview Spec: 자율 틈 감지기 (GM 보좌 자율화 phase2 — 배237(b))

## Metadata
- Interview ID: gm-aide-gap-detector-2026-07-08
- Rounds: 7 (+ Round 0 topology)
- Final Ambiguity Score: 4.7%
- Type: brownfield (기존 gm_aide_scan.py / gm_profile_builder.py / 자율현황.html 확장)
- Generated: 2026-07-08
- Threshold: 0.05
- Threshold Source: ./.claude/settings.json
- Initial Context Summarized: no
- Status: PASSED
- 상위 배: CEO-2026-07-02-GM-AIDE-AUTONOMY (ship 237) — phase1 완료 후속 phase2

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.96 | 0.35 | 0.336 |
| Constraint Clarity | 0.95 | 0.25 | 0.238 |
| Success Criteria | 0.96 | 0.25 | 0.240 |
| Context Clarity | 0.93 | 0.15 | 0.140 |
| **Total Clarity** | | | **0.953** |
| **Ambiguity** | | | **0.047** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 공통 뼈대 (gap-detector framework) | active | 가역성 라우터 + 자율 실행 레인 + 사후통지 + G1 기록. 감지기들이 공유하는 파이프라인 | 이번 스펙 전면 커버 |
| 감지기 ① 대기/지연 감시 | active | 오래 멈춘 배 + 구조적 depends_on 해소 배 감지 → 가역 자율조치 | 이번 스펙 MVP·전면 커버 |
| 감지기 ② 루틴 누락 자가보완 | deferred | 스케줄 작업 누락 감지 (2026-07-08 GM 확정 유보 — 뼈대 검증 후 플러그인. 기존 시토 헬스체크와 경계 정리 필요) |
| 감지기 ③ KPI 드롭 선제감지 | deferred | 지표 악화 선제 감지 (2026-07-08 GM 확정 유보 — KPI 데이터 성숙 후) |
| 감지기 ④ GM 약속/결정 추적 | deferred | GM 발언 파싱 (2026-07-08 GM 확정 유보 — LLM 정확도 리스크, 순수 제안형) |

## Goal
기존 자율 엔진(gm_aide_scan)이 '포착→제안'만 하고 실제 자율 처리는 0(auto_applied:0)인 상태를, **"기대 상태 ↔ 실제 상태의 틈을 감지해 가역이면 자율 처리, 비가역이면 제안"** 하는 통합 뼈대로 확장한다. 첫 감지기(MVP)로 **대기/지연 감시**를 붙여 자율 실행 레인을 실증한다. 목적은 **GM 개입 감소** — 되돌릴 수 있는 일은 웰리가 알아서 처리하고, GM 화면엔 진짜 필요한 비가역 결정만 최소로 올린다.

## Constraints
- **가역성 3조건 (전부 충족해야만 자율 실행):** ①1초 안에 원복 가능 ②GM/외부에 안 나감 ③데이터 무손실. 하나라도 불충족 → 자동으로 제안 레인.
- **애매하면 제안** — 판정 불확실 시 무조건 보수적으로 제안 레인 폴백.
- **웰리 = 두뇌.** 실제 도메인 작업 실행(재가동)은 비가역 → 제안. 자율 실행은 표면화·재촉·상태정합 등 가역 조치에 한정.
- **새 알림 스트림 금지.** 재촉·요약은 기존 06:30 gm_aide_scan 스캔에 묶어 발송. 건별 즉시 텔레그램 금지(257 카드 누적 역설 방지).
- **재촉 대상 = 담당 C-Level (GM 아님).** C-Level은 상주 프로세스가 아니므로 재촉은 G1/큐 '재개가능' 태그(pull)로 남아 부팅 시 잡힘.
- **자유문장 depends_on 미판정.** 구조적 참조(다른 배 ship_no/task_id 명시)만 해소 판정. LLM 추정은 이번 범위 밖.
- **엔진 재사용.** 새 예약작업 0 — 기존 Wellperion-GM-Aide-Scan-0630 슬롯에 얹음.
- **_queue.json 동시편집 안전** — read-before-write, INC-008 머지 드라이버 의존, 파괴적 git 금지.

## Non-Goals
- 감지기 ②③④ 구현 (이번 스펙은 뼈대 + ①만)
- 실제 도메인 작업의 자율 재가동 (비가역 → 제안까지만)
- 자유문장 depends_on의 LLM 해소 판정
- GM에게 가는 건별 즉시 알림 / 새 알림 채널
- 미응답 추천 재포착 (기존 unapproved_recommendation이 이미 담당 — 중복 금지)

## Acceptance Criteria
- [ ] 가역성 라우터: 틈 하나를 입력하면 3조건 판정 후 '자율' 또는 '제안' 레인으로 라우팅(애매=제안). 단위 판정 재현.
- [ ] 대기/지연 감지 — 정체: IN_PROGRESS 배 중 updated_at이 무게별 임계(🛳️크루즈 2일·⛴️여객선 3일·⛵돛단배 5일) 초과 무변화면 '지연'으로 포착.
- [ ] 대기/지연 감지 — 재개가능: depends_on이 다른 배 ship_no/task_id를 명시 참조하고 그 배가 DONE이면 '재개가능'으로 포착. 자유문장 depends_on은 미포착.
- [ ] 자율 조치(가역): 포착 배에 ①G1/큐 note에 '⚓재개가능' 또는 '⏳N일 정체' 태그 ②담당 C-Level 재촉 마커 ③구조적 depends_on 해소 시 상태 정합 정리. 전부 되돌리기 가능하게 기록.
- [ ] 제안 조치(비가역): 실제 재가동·오래 방치 배 닫기/재설계는 06:30 제안 카드로만(자동 실행 안 함).
- [ ] 사후통지: 자율현황.html '층① 자율로 한 일'에 각 자율조치 = 사유 + 되돌리기 근거 상시 기록(pull) + 06:30/일일보 '어제 자율 N건 처리' 1줄 요약. 새 알림 없음.
- [ ] 성공지표 노출: 자율 처리 비율(감지 틈 중 자율로 닫은 %) + 사후보고 신뢰도(GM이 되돌린 비율 = 불신 지표) 자율현황에 집계.
- [ ] 회귀 0: 기존 gm_aide_scan 제안 경로·unapproved_recommendation·프로필 근거 연동 무손상.
- [ ] 라이브 발효 게이트: 코드+드라이런+샘플까지. 실제 자율 write 발효는 GM go(북극성 재설계 배420 패턴 준수).

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 4개 감지기 다 만든다 | YAGNI / 증분 검증 | 뼈대 + MVP 1종만. 3종 확정·후속 플러그인 |
| 카드·알림 늘리면 자율화 | GM "내가 더 손 쓰게 되는데?" | 개입 감소가 성공기준. 재촉=C-Level(GM 아님)·사후보고=pull+일일1줄 |
| depends_on 해소 자동 판정 가능 | depends_on은 자유문장 | 구조적 참조만 판정, 자유문장 미판정(오판 방지) |
| 자율 처리분 GM이 매번 확인 | 확인=또 GM 일(Contrarian) | 기본 pull(자율현황 층①), 매번 확인 불요 |
| 웰리가 재가동까지 자동 | 실제 실행=비가역 | 표면화·재촉(가역)까지 자율, 재가동은 제안 |
| 정체 임계 일률 | 우선순위별 노이즈(Simplifier) | 무게별 차등 2/3/5일 |

## Technical Context (brownfield)
- **엔진:** `scripts/gm_aide_scan.py` (포착→제안, auto_applied:0), `scripts/gm_profile_builder.py` (프로필 일일갱신). 예약작업 Wellperion-GM-Aide-Scan-0630. → 여기에 가역성 라우터 + 자율 실행 레인 신설.
- **데이터:** `status/_queue.json` (배 SSOT, 필드 status·priority·updated_at·depends_on·ship_no·task_id·note·next), `status/gm_observation_ledger.jsonl`, `status/kpi_values.json`.
- **사후보고 표면:** `자율현황.html` (배237 phase1 병합 보드 — 층① 자율로 한 일 / 층② 돌아가는 자동화). 재사용.
- **안전:** INC-008 _queue 머지 드라이버, INC-009 파괴적 git 금지, 완료훅 clevel_post_action --next(모든 배 next 강제 → 표류 배 0 = 이 감지기가 대기/지연으로 대체 포착).

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| 틈(gap) | core domain | 유형(정체/재개가능)·대상배·근거·감지시각 | 감지기가 생성, 라우터가 분류 |
| 감지기(detector) | core domain | 이름·기대치소스·트리거조건 | 틈을 생성, 뼈대에 플러그인 |
| 가역성 라우터 | core domain | 3조건 판정·레인(자율/제안) | 틈을 자율조치 또는 제안카드로 라우팅 |
| 자율 조치 | core domain | 종류(태그/재촉/상태정합)·사유·되돌리기근거 | 가역 틈에서 생성, 자율현황 층①에 기록 |
| 제안 카드 | supporting | 대상배·비가역사유·경로 | 비가역 틈에서 생성, 06:30 카드(기존 경로) |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|----------------|
| 1-2 | 3 | 3 | - | - | N/A |
| 3-5 | 5 | 2 | 0 | 3 | 60→100% |
| 6-7 | 5 | 0 | 0 | 5 | 100% (수렴) |

## Interview Transcript
<details>
<summary>Full Q&A (Round 0 + 7 rounds)</summary>

- **R0 토폴로지:** 뼈대 + 감지기 4종 = 5 구성. 이번=뼈대+MVP 1종, 3종 후속(확정).
- **R1 MVP 감지기:** 대기/지연 감시 (가역·즉시·새 데이터 의존 0).
- **R2 자율 조치 범위:** 재촉+G1태그+상태정합 (가역 3종). GM 지적="자동화인데 내가 더 손 쓰게 되는 듯" → 개입 감소 원칙 부상.
- **R3 성공기준:** 자율 처리 비율 + 사후보고 신뢰도.
- **R4 사후보고(Contrarian):** 기본 pull(자율현황 층①) + 일일 1줄. 새 알림 0.
- **R5 방아쇠:** 멈춤 기간 + 구조적 depends_on만. 자유문장 미판정.
- **R6 임계값(Simplifier):** 무게별 차등 2/3/5일.
- **R7 자동화 깊이:** 표면화+재촉(가역) 자율, 재가동은 제안. 재촉=C-Level 태그(pull).

</details>
