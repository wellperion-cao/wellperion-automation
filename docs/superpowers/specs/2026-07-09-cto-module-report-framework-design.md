# 설계 스펙: 시토 자율화 두뇌 — 모듈 자동보고 프레임워크

## 메타
- 작성: 2026-07-09 · 담당: AI CTO(시토)
- 유형: brownfield (기존 보고 스크립트 흡수)
- 임계 모호성: 5% (source: ./.claude/settings.json) · 최종 ≈4% · 상태: PASSED
- 상위 지시: GM "Fable이 떠난 뒤에도 Sonnet C-Level이 똑똑하게 도는 뼈대(자율화 두뇌·가드레일·아키텍처)를 지금 찍어라 — 복리로 남는다"
- 물린 것: 배237(웰리 GM보좌·층 분리) · T2 자율현황.html · telegram_bot 인프라 · 예약작업

## 목표 (Goal)
모듈마다 손배선된 보고 스크립트(monthly_check_report·kakao_auto_daily_report·weekly_marketing_feedback·northstar_recommender 등 N개 + 각자 .bat + 각자 예약작업)를 **레지스트리 1 + 범용 리포터 1 + 예약작업 3(일/주/월)**으로 수렴한다. 모듈을 레지스트리에 한 줄 등록하면 일/주/월 텔레그램 보고가 자동 생성·발송된다. 1차 적용 대상 = **자율현황(T2) 도메인의 자동화 모듈**이며, 자율현황 보드가 이 레지스트리로 라이브 구동된다. GM이 결정할 것(설정변경·이상징후)은 **CLI/모바일 원격의 AskUserQuestion 카드**로 surface해 GM은 버튼만 클릭한다. 목적 = AI가 없어도 실무진이 자율현황 보드 하나로 "무엇이 언제 보고되고, 무엇이 살아있고, 무엇이 문제인지" 스스로 파악.

## 토폴로지 (Topology)
| 컴포넌트 | 상태 | 설명 | 커버리지/보류 |
|---|---|---|---|
| 모듈 레지스트리 | active | `status/module_registry.json` — 선언형 모듈 목록(신규=한 줄) | AC-1,2 |
| 범용 리포터 | active | `scripts/module_reporter.py --cadence daily\|weekly\|monthly` | AC-3,4,7 |
| 수집기 인터페이스 | active | `scripts/collectors/` — 모듈별 `collect()`→표준 payload | AC-5 |
| 결정 큐 + 카드 surface | active | pending 결정을 AskUserQuestion 카드로(설정변경·이상징후) | AC-6 |
| 예약작업 3 (일/주/월) | active | 기존 난립 예약작업 대체·1회씩 리포터 호출 | AC-8 |
| 자율현황(T2) 프론트 | active | 레지스트리를 렌더(읽기). 등록/수정 UI는 후속(GM go) | AC-9 |

## 제약 (Constraints)
- **결정 채널 = CLI/모바일 원격 AskUserQuestion 카드.** 텔레그램 인라인 버튼·ERP 결정 UI 신규 구축 안 함. 텔레그램 보고는 "결정 대기 N건" 플래그만.
- **정기 보고 = 자동 발송.** GM 승인 없이 일/주/월 자동. 오직 설정변경·이상징후만 카드 결정.
- **기존수정 원칙**: 새 보고기 만들지 않고 기존 스크립트를 `collect()` 수집기로 감싼다.
- **봇 토큰 = `.env` 단일출처(`TELEGRAM_BOT_TOKEN`) 재사용.** 신규 평문 자격증명 0.
- **Windows 예약작업 제약 준수**: .bat 영문·단계분리·PYTHONIOENCODING=utf-8 (메모리 reference_powershell_scheduledtasks_limitation).
- **멱등**: 모듈+날짜+주기 dedup. 재실행 중복발송 0.
- **웰리 경계 불가침**: `gm_aide_scan.py`·`gm_profile_builder.py` 안 건드림. 웰리 결과는 원하면 나중에 '모듈 등록'만(레일 공유).
- **정직 꼬리표 표준**: 측정/부분/미측정/표본부족 — 모든 보고 공통.

## 비목표 (Non-Goals)
- 채널 ID/PW 웹등록·자동로그인 금고 (CMO M3 예시 — 제 모듈은 봇토큰만 쓰므로 제외)
- ERP 화면 내 모듈 등록/수정 UI (1차=읽기 렌더만, 편집 UI는 GM go 후 후속)
- 점검·매출 모듈 온보딩 (1차 자율현황 검증 후 후속 순차 흡수)
- 웰리 GM보좌(배237) 로직 변경 (층 분리 유지)
- 자동 가중치·점수 고도화 (v2, 데이터 축적 후)

## 데이터 모델
### 레지스트리 항목 (모듈 1개 = 1줄)
```json
{
  "id": "automation_health",
  "name": "자율현황 자동화 건강",
  "owner": "cto",
  "bot_room": "종합보고방",
  "cadence": ["weekly@mon@09:00"],
  "collector": "collectors.automation_health",
  "frontend_anchor": "자율현황.html#health",
  "enabled": true,
  "honesty_default": "측정"
}
```
### 수집기 표준 반환 (모든 모듈 동일 규격)
```json
{
  "title": "자율현황 자동화 건강",
  "summary_line": "가동 10/10 · 실패 0 · 지난주 대비 +1",
  "metrics": [{"label":"가동","value":"10/10"},{"label":"실패","value":0}],
  "honesty_tag": "측정",
  "link": "https://.../자율현황.html"
}
```
### 결정 아이템 (pending → 카드)
```json
{
  "decision_id": "dec-20260709-...",
  "type": "설정변경|이상징후",
  "module": "automation_health",
  "summary": "발송 3회 연속 실패 — 재시도/끄기/조사 택1",
  "options": ["재시도","모듈 끄기","조사 지시"],
  "raised_at": "...", "status": "pending"
}
```

## 흐름 (Data Flow)
### 보고 흐름
`module_reporter.py --cadence daily` → 레지스트리에서 오늘 주기·`enabled` 필터 → 각 `collect()` 호출 → 표준 템플릿 포맷 → 모듈 `bot_room` 발송 → `status/module_report_log.jsonl` 기록. 실패는 삼키지 않고 `telegram_health_check`로 감지.

### 결정 흐름 (버튼 클릭)
리포터/수집기가 설정변경 필요·이상징후 감지 → `status/module_decisions.json`에 pending 적재 → 텔레그램 보고에 "결정 대기 N건" 1줄 → **GM이 CLI/모바일 세션 들어오면 AskUserQuestion 카드로 surface** → GM 버튼 클릭 → 결정 반영(레지스트리 patch 등)·큐에서 해소·원장 기록.

## 에러 처리·가드레일
- **킬스위치**: 모듈 `enabled=false` 한 줄 → 즉시 정지(역롤백 1초).
- **조용한 실패 방어**: 발송 실패 시 health_check 경보(기존 telegram_health_check 연동).
- **멱등 dedup**: 모듈+날짜+주기 키. 재실행 안전.
- **정직 가드**: 수집기가 표본부족·미측정이면 % 대신 원수치+꼬리표(메모리 reference_stage_funnel_source_composition_trap·check_completion_rate 교훈).
- **드라이런**: `--dry-run`으로 발송 없이 payload 검증.

## 수용 기준 (Acceptance Criteria)
- [ ] AC-1 `status/module_registry.json` 존재·스키마 유효, 자율현황 도메인 모듈 1개 이상 등록
- [ ] AC-2 신규 모듈 = 레지스트리 한 줄 추가만으로 보고 대상 편입(코드 변경 0)
- [ ] AC-3 `module_reporter.py --cadence weekly --dry-run` → 등록 모듈 payload 정상 생성(발송 0)
- [ ] AC-4 실발송 1회 → 지정 봇방 도착·`module_report_log.jsonl` 기록·재실행 시 중복발송 0(멱등)
- [ ] AC-5 최소 1개 수집기(자율현황 건강)가 표준 payload 반환, 기존 로직 흡수(신규 중복 0)
- [ ] AC-6 이상징후/설정변경 발생 시 pending 결정 적재→CLI AskUserQuestion 카드로 surface→버튼 클릭 반영
- [ ] AC-7 `enabled=false` 시 해당 모듈 발송 정지(킬스위치)
- [ ] AC-8 예약작업 3개(일/주/월) 각 1회 리포터 호출로 배선, 흡수된 난립 예약작업 목록 문서화
- [ ] AC-9 자율현황(T2) 보드가 레지스트리를 읽어 모듈·주기·최근발송·상태 렌더(읽기)
- [ ] AC-10 웰리 `gm_aide_scan.py`·`gm_profile_builder.py` 무변경(diff 0)

## 노출된 가정 & 해소
| 가정 | 도전 | 해소 |
|---|---|---|
| 결정=텔레그램 인라인 버튼일 것 | GM: "지금처럼 CLI에서, 모바일 원격도 됨" | 결정 채널=AskUserQuestion 카드. 텔레그램 버튼 인프라 안 지음 |
| 1차=점검·매출·자율현황 3개 | GM: "웰리 충돌 안 되는 선 자율현황쪽" | 1차=자율현황 도메인. 점검·매출은 후속 |
| 모든 결정을 GM이 승인 | GM: "설정변경+이상징후만" | 정기 보고 자동, 결정만 카드 |
| 새 보고기를 지을 것 | 기존수정 원칙 | 기존 스크립트를 수집기로 감쌈 |

## 기술 맥락 (brownfield 실측)
- 흩어진 보고기: `monthly_check_report`·`monthly_ops_report`·`monthly_marketing_report`·`weekly_marketing_feedback`·`kakao_auto_daily_report`·`northstar_recommender` + 각자 .bat/예약작업
- 텔레그램 인프라: `telegram_bot/bot.py`·`daily_scheduler.py`·`notify_prefs.py`·`telegram_health_check.py`
- 자율현황(T2): 배237 병합으로 이미 "돌아가는 자동화" 보드 존재 → 레지스트리가 이 보드를 라이브 구동(프론트 앵커)
- 웰리 층: `gm_aide_scan.py`·`gm_profile_builder.py` = GM 개인 보좌(불가침)

## 온톨로지 (핵심 엔티티)
| 엔티티 | 유형 | 필드 | 관계 |
|---|---|---|---|
| 모듈(Module) | core | id·name·owner·bot_room·cadence·collector·frontend_anchor·enabled·honesty | Reporter가 순회, Registry에 속함 |
| 레지스트리(Registry) | core | modules[] | Module 다수 보유 |
| 리포터(Reporter) | core | cadence 필터·dispatch·dedup | Module.collect() 호출→Report 발송 |
| 수집기(Collector) | supporting | collect()→payload | Module에 1:1 |
| 보고(Report) | supporting | title·summary·metrics·honesty·link | Collector 산출·bot_room 발송 |
| 결정(Decision) | core | type·module·options·status | 이상징후/설정변경 시 발생·카드 surface |
| 봇방(BotRoom) | external | 텔레그램 chat | Report 도착지 |

<details>
<summary>인터뷰 요약 (승인 설계 + 3결정 카드)</summary>

- 척추: 옵션 A(레지스트리+범용 리포터) 확정
- 순서: 옵션 3(프레임워크 먼저→내 모듈 정리) 확정
- 결정 채널: CLI/모바일 AskUserQuestion 카드 (텔레그램 버튼 아님)
- 1차 레퍼런스: 자율현황(T2) 도메인 (웰리 층 분리)
- 결정 범위: 설정변경 + 이상징후만 (정기 보고 자동)
</details>
