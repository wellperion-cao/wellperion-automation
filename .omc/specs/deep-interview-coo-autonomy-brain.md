# Deep Interview Spec: COO 자율화 두뇌 (레지스트리 구동 뼈대)

## Metadata
- Interview ID: coo-autonomy-brain-20260709
- Rounds: 4 (+ Round 0 topology)
- Final Ambiguity Score: ~5%
- Type: brownfield
- Generated: 2026-07-09
- Threshold: 0.05
- Threshold Source: ./.claude/settings.json
- Status: PASSED (all dimensions ≥0.92; residual = implementation detail resolved in-spec)
- 소유: AI COO(시우) · 두뇌 설계=Fable(Opus) · 문서화=Sonnet

## 배경 (GM 지시 2026-07-09)
Fable로 만들 것 = 개별 결과물이 아니라 **Fable이 떠난 뒤에도 Sonnet 각 C-Level이 똑똑하게 도는 뼈대**(자율화 두뇌·프롬프트·가드레일·아키텍처). 두뇌는 복리로 남는다. GM이 6 C-Level 전원에게 동일 지시 전달함 — 각자 본인 소유 모듈 기준으로 자기 두뇌 셋업. 본 스펙 = 그중 **시우(COO) 것**. (relay 불필요·GM 완료)

GM 4기둥: ①백엔드 단순화(AI 없이도 쓰는 ERP 구조) ②프론트 모듈화(누구나 읽힘·모듈마다 대표기능) ③모듈별 텔레그램 자동보고(봇ID 등록→일/주/월) ④보안 자동로그인(채널 ID/PW).

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.96 | 0.35 | 0.336 |
| Constraint Clarity | 0.95 | 0.25 | 0.238 |
| Success Criteria | 0.93 | 0.25 | 0.233 |
| Context Clarity | 0.92 | 0.15 | 0.138 |
| **Total Clarity** | | | **0.945** |
| **Ambiguity** | | | **~5.5%** |

## Topology (4부품)
| Component | Status | Description | Coverage |
|-----------|--------|-------------|----------|
| 모듈 레지스트리 | active | 6모듈을 표준 스키마 1곳(status/coo_modules.json)에 정의 | AC-1 |
| ERP 모듈 허브 | active | 레지스트리를 기존 O1 운영통합체계에 카드 대시보드로 렌더 | AC-2 |
| 자동보고 러너 | active | 주기별 텔레그램 자동발송(08시 합류+이상 즉시) | AC-3, AC-4 |
| 부팅 두뇌·가드레일 | active | Sonnet 부팅 시 레지스트리 흡수→가역성 라우터→항로 생성 | AC-5, AC-6 |

## Goal
COO 소유 6모듈을 **"레지스트리 구동" 뼈대**로 재구성한다. 모듈 하나를 표준 스키마 1줄로 등록하면 ERP 카드·텔레그램 자동보고·부팅 자율판단이 전부 자동 점등한다. AI가 없어도 실무진이 각 모듈을 읽고 쓸 수 있고(백엔드 단순·프론트 모듈화), Sonnet 세션은 이 뼈대만 흡수하면 똑똑하게 자율로 돈다. **착수 = 파일럿 '점검 현황' 1모듈 end-to-end 관통 → GM 룩 확정 → 나머지 5모듈 레지스트리 복제.**

## COO 소유 모듈 (실측 14페이지 → 6모듈)
1. **점검 현황** (파일럿): 지원·운영·시설·주차·강습팀·파트너팀 체계 — GAS 점검 시트
2. **리셉션·라커**: 종합접수처 현황·라커 대시보드 — GAS reception
3. **업무·결재 SSOT**: 업무현황·결재현황 — GAS todo
4. **공지/안내문**: notice_template — 로컬/GAS
5. **월간운영계획·전사회의**: home 모듈 — kpi.json·GAS
6. **재등록 대시보드(O3)**: 재등록 현황 — GAS

## 부품 상세
### ① 모듈 레지스트리 — status/coo_modules.json (신규·핵심)
각 모듈 표준 스키마: id · name · erp_paths[] · hub("O1") · data_source{type,endpoint,action} · headline_feature(대표기능) · status_metric{compute,display} · telegram{bot,daily_join,anomaly_immediate,weekly,monthly} · autonomy{reversible[],gated[]} · honesty_tags[]. **한 곳 원천(L01)** — 허브·러너·부팅두뇌가 전부 이 파일에서 읽음(중복0).

### ② ERP 모듈 허브 — 기존 O1 운영통합체계.html 확장
새 페이지 신설 안 함. O1에 모듈 카드 대시보드 섹션 추가 — 레지스트리 렌더. 카드=대표기능+실시간 상태지표+주기 배지 → 클릭 시 상세 페이지. 실무진 한눈에·AI 없이 사용.

### ③ 자동보고 러너 — daily_scheduler/telegram_notifier 재사용
레지스트리 telegram 설정을 읽어: 매일 08시 통합보고에 '점검 현황: 지원 X% 시설 Y% ✅' 1줄 자동 합류 + 이상(미완료·100%초과 등) 발생 시 즉시 1줄 알림. 봇 1개(@namuki_report_bot) 재사용. 주/월은 레지스트리 플래그로 후속 확장.

### ④ 부팅 두뇌·가드레일 — gm_aide_scan/bridge 재사용
COO 세션 부팅 시: 레지스트리 로드 → 각 모듈 상태 점검 → **가역성 라우터**로 분기. 자율(가역)=상태 집계·텔레그램 보고·이상 플래그·항로 생성. 제안+GM go(비가역)=시트/GAS 변경·라이브 배포·보안. **정직 꼬리표**(측정/부분/미측정) 카드·보고에 일관 표기.

## Constraints
- 착수 = 파일럿 점검현황 1모듈만 end-to-end. 나머지 5 = 레지스트리 스텁(telegram off)만 등록, GM 룩 확정 후 복제.
- 자율 = 가역 조치만. 비가역(시트/GAS/라이브/보안) = 제안+GM go.
- 허브 = 기존 O1 흡수(새 페이지 0·중복0).
- 점검 백엔드는 지원부와 공유 GAS — 회귀 금지.
- 라이브 발효·보안은 GM go+역롤백(약속·헌법 축6).

## Non-Goals
- ④ 보안 자동로그인: COO 도메인은 외부 로그인 채널 없음(전부 GAS·시트 기반, 이미 자동) → **N/A. 억지 구현 안 함**(이 기둥은 시모 CMO 채널용).
- 6모듈 동시 구축(파일럿 먼저).
- 라이브 GAS/시트 자율 변경(게이트).
- 타 C-Level 두뇌(각자 본인 세션).

## Acceptance Criteria
- [ ] AC-1: status/coo_modules.json 존재·6모듈 스키마 검증 통과(점검현황=완전 배선, 5모듈=스텁)
- [ ] AC-2: O1 운영통합체계에 모듈 카드 대시보드 렌더, 점검현황 카드=라이브 완료율 실측 표시(시크릿 크롬 검증)
- [ ] AC-3: 매일 08시 통합보고에 '점검 현황' 1줄 자동 합류(실발송 확인)
- [ ] AC-4: 이상(미완료/100%초과) 발생 시 즉시 텔레그램 1줄 알림
- [ ] AC-5: COO 부팅 시 레지스트리 로드→가역성 라우터 자율/제안 분기(게이트 OFF 시 라이브 델타0)
- [ ] AC-6: 정직 꼬리표(측정/부분/미측정) 카드·보고 일관 표기
- [ ] AC-7: 나머지 5모듈 복제 절차 문서화(레지스트리 1줄→자동 점등 재현)

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 6모듈 다 지금 짜야 함 | 파일럿으로 증명이 저위험 | 점검현황 1모듈 먼저 |
| 새 허브 페이지 필요 | 새 페이지가 정말 필요한가(대조모드) | 기존 O1 흡수, 새 페이지 0 |
| 두뇌가 알아서 다 처리 | 자율 경계 어디까지 안전한가 | 가역성 라우터(비가역=GM go) |
| 4기둥 다 적용 | 보안 자동로그인이 COO에 있나 | COO 외부채널 0 → ④ N/A |
| 전용 봇 필요 | 봇 여러개 vs 재사용 | 08시 통합보고 봇 1개 재사용 |

## Technical Context (brownfield)
- 재사용: daily_scheduler.py·telegram_notifier.py(자동보고)·gm_aide_scan/bridge(부팅두뇌·가역성 라우터, 배237)·기존 COO 점검 GAS.
- 신규: status/coo_modules.json(레지스트리) + O1 렌더 섹션 + 레지스트리 로더.
- 점검 GAS = 지원부 공유(.deploy-check) — 회귀 가드 필수.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Module | core | id, name, erp_paths, hub, data_source, headline_feature, status_metric, telegram, autonomy, honesty_tags | Registry has many Module |
| Registry | core | modules[] | renders → Hub, feeds → Runner, feeds → BootBrain |
| Hub(O1) | supporting | cards[] | renders Module cards |
| ReportRunner | supporting | schedule, bot, payload | reads Registry.telegram |
| BootBrain | core | reversibility_router, honesty_tags, route_output | reads Registry, writes 항로 |
| ReversibilityRouter | supporting | reversible[], gated[] | routes Module.autonomy |

## Interview Transcript
<details><summary>Round 0~4</summary>

- Round 0 (토폴로지): 4부품 확정 — 레지스트리·허브·러너·부팅두뇌.
- Round 1 (범위/제약): 파일럿 점검현황 1모듈 end-to-end → 복제.
- Round 2 (성공기준): 08시 통합보고 합류 + 이상 즉시 알림.
- Round 3 (자율경계): 가역성 라우터(가역=자율/비가역=GM go).
- Round 4 (프론트/대조모드): 기존 O1 흡수, 새 페이지 0.
</details>
