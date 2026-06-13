# AI C레벨 배(_queue.json) → 구글시트 일원화 — 마이그레이션 계획서

작성: AI CTO(시토) · 2026-06-07 · 1단계 산출물
근거: GM 결정 "AI C레벨 배를 구글시트로 일원화 → G1에서 GM 일처럼 편집되게."

---

## 0. 채택 아키텍처 (한 줄 요약)

**구글시트 = AI 배 SSOT(단일 진실) / `status/_queue.json` = 시트에서 자동 생성되는 캐시(미러).**

- 모든 READER(8시·21시 보고, daily_scheduler, hangro_board, ceo_watcher, G1 HTML)는
  앞으로도 `_queue.json` 을 **있는 그대로** 계속 읽는다 → 보고 깨질 위험 0.
- 새 동기화기(`scripts/queue_sync_from_sheet.py`)가 시트 AI행 → `_queue.json` **단방향 재생성**.
- WRITER(clevel_post_action 등)의 시트 직접 쓰기 전환은 2단계 이후 과제.

---

## 1. 블라스트 반경 (`_queue.json` 읽기/쓰기 계약)

### 쓰기(WRITER) — 1단계에서 손대지 않음
| 파일 | 어떻게 쓰는가 | 핵심 필드 |
|---|---|---|
| `wellperion-agents/scripts/clevel_post_action.py` | 브릿지: DONE 표시 + processed_at + next/terminal, '다음'을 PENDING append(NEXT-*) | task_id, status, processed_at, next, terminal, next_missing, artifact, depends_on, from, origin, enqueued_at, clevel, title |
| `telegram_bot/bot.py` (결재 회신 라우터 ~L464-641) | PENDING 후보 조회 → 단일 매칭 status 패치(APPROVED/ON_HOLD/REJECTED) + approval/approved_at/approval_comment | status, approval, approved_at, approval_comment |
| `scripts/ceo_watcher.py` | 큐 선두(pop(0)) 검증 후 처리, _verify_log 기록 | task_id, clevel, status |
| `wellperion-agents/scripts/queue_archive.py` | DONE N일 경과분을 `_archive.json` 으로 이동(원자적) | status, processed_at/completed_at/updated_at/enqueued_at |

### 읽기(READER) — 1단계 무수정 (계속 `_queue.json` 읽음)
| 파일 | 읽는 필드 |
|---|---|
| `wellperion-agents/scripts/ceo_morning_pipeline.py` (8시) | status, task_id, clevel, title, priority, note, deadline, processed_at, completed_at, updated_at, brief |
| `wellperion-agents/scripts/ceo_evening_wrap.py` (21시) | status, processed_at, task_id, clevel, title |
| `telegram_bot/daily_scheduler.py` | status(!=DONE), clevel, title |
| `scripts/hangro_board.py` (G1 보드) | task_id, clevel, status, title, deadline, processed_at, priority |
| G1 HTML `3. 웰페리온 가이드/wellperion_guide(main).html` | task_id, title, clevel, status, next (raw.githubusercontent fetch) |

### 무관 (제외)
- `review_queue.json` (발행/검수 큐) — AI 배와 별개. 본 계획 대상 아님.

### `_queue.json` 현행 스키마 (필드 출현 기준)
필수: `task_id`, `clevel`, `title`, `status`(PENDING/IN_PROGRESS/DONE/폐기/ON_HOLD)
선택(있을 때만): `priority`, `depends_on`, `deadline`, `enqueued_at`, `processed_at`,
`terminal`, `next`, `next_missing`, `brief`, `note`, `from`, `origin`, `artifact`,
`commit_sha`, `remind_on`, `disposed_at`, `owner`, `tech`, `approval`, `approved_at`,
`approval_comment`, `archived_at`

> **불변식:** 미러 재생성기는 이 스키마/필드명을 **100% 그대로** 산출해야 한다(readers 무수정).

---

## 2. 시트 매핑 설계 (todo_list 컬럼 → `_queue.json`)

### AI 배 행 식별 (시각적 분리)
- **신규 카테고리 `[7]AI배(C레벨)`** 로 AI 배 행을 표시. GM/실무진 행과 한 시트 안에서 분리.
- GAS `CATEGORIES` 드롭다운에 아직 없지만 **셀 자유 입력으로 동작**(재배포 불필요).
  드롭다운 정식 등재는 GM 수동(GAS 재배포) — 선택 항목(§5).

### 컬럼 직접 매핑
| 시트 컬럼 | `_queue.json` 필드 | 비고 |
|---|---|---|
| 업무명 | title | |
| 담당자 | clevel | 'AI CTO'/'시토'/'cto' → `cto` 정규화 |
| 상태 | status | 진행중→IN_PROGRESS, 대기→PENDING, 완료→DONE, 보류→ON_HOLD, 폐기→폐기 |
| 종료일 | deadline | |
| 난이도 | priority | 상→HIGH, 하/중→NORMAL (보수적; 임베드값 우선) |
| 수정일 | processed_at | status=DONE 일 때만 |
| 생성일 | enqueued_at | |
| id | task_id | 임베드 미존재 시 폴백 |

### 부족 필드 인코딩 (신규 컬럼 없이 — GAS 재배포 회피)
시트 `내용` 셀 안에 **BUDGET 마커(`===BUDGET===`)와 동일한 발상**의 임베드 블록:

```
(사람이 읽는 본문)
===AI_QUEUE===
{"task_id":"CTO-...","depends_on":null,"terminal":true,"brief":"...","next":"...",
 "from":"cto","origin":"bridge","artifact":"...","note":"...","enqueued_at":"..."}
===END===
```

- 블록은 동기화기가 파싱(명시값 우선), 본문은 note 폴백으로 사용.
- 신규 컬럼/GAS 변경 0 → **완전 비파괴**. (정식 컬럼 승격은 2단계 선택.)

---

## 3. 단계별 로드맵 (단계마다 readers 안전성 명시)

### 1단계 — 비파괴 미러 생성기 (**본 작업 완료**)
- 산출: `scripts/queue_sync_from_sheet.py` (NEW), 본 계획서 (NEW).
- 동작: 시트 AI행 → `_queue.json` 호환 JSON **생성·미리보기**(stdout). `--diff`/`--mock`/`--write`.
- **readers 안전:** 파일 포맷 불변 → 100% 안전. 아직 자동 쓰기 안 함(수동 `--write`만).
- 변경 파일: 신규 2개만. 기존 자동화/GAS 무수정.

### 2단계 — 동기화 자동화 (읽기 일원화)
- 시트가 SSOT가 되도록, 주기적으로(또는 G1 편집 직후) `queue_sync_from_sheet.py --write` 실행.
- 트리거 후보: Task Scheduler 주기 실행 / G1 편집 후 훅 / 8시·21시 보고 직전 1회.
- **readers 안전:** 여전히 `_queue.json` 만 읽음 → 무수정. 단, **쓰기 충돌 방지**가 핵심 위험(§4).
- 변경 파일: 트리거 등록(스케줄러 설정/배치) — 기존 .py 무수정 권장.

### 3단계 — WRITER 시트 전환 (양방향 정리)
- `clevel_post_action.py`(브릿지)·`bot.py`(결재)·`ceo_watcher.py` 가
  `_queue.json` 직접 쓰기 → **GAS todo_* API(시트) 쓰기**로 전환.
- 전환 후 `_queue.json` 은 순수 캐시(읽기 전용 미러). 양쪽 쓰기 이중화 기간을 두고 점진 전환.
- **readers 안전:** readers는 끝까지 `_queue.json` 만 읽으므로, 미러 생성기가 살아있는 한 안전.
- 변경 파일: 위 3개 WRITER + 신규 GAS 액션(`ai_queue_*`) — **GAS 재배포 필요(GM 수동)**.

### 4단계 — G1 편집 UI 통합 (GM 체감 목표)
- G1 HTML에서 AI 배를 GM 일처럼 인라인 편집(담당자/상태/내용) → todo_* API로 시트 기록.
- `[7]AI배(C레벨)` 카테고리 전용 뷰/색상으로 시각 구분.
- **readers 안전:** 동일(미러 경유). 변경 파일: G1 HTML + GAS(드롭다운/색상) — GAS 재배포(GM 수동).

---

## 4. 위험 & 완화

| 위험 | 영향 | 완화 |
|---|---|---|
| **쓰기 충돌**(2단계): 미러 `--write` 와 기존 WRITER(브릿지/결재)가 동시 `_queue.json` 갱신 | 한쪽 변경 유실 | 2단계는 WRITER 전환(3단계) 전까지 **미러를 읽기 보강용으로만**(또는 WRITER 비활성 시간대 sync). 원자적 .tmp→replace는 이미 적용. |
| 시트 임베드 블록 손상(GM이 `내용` 직접 편집) | task_id/메타 유실 | 파싱 실패 시 컬럼 폴백(id→task_id). 정식 컬럼 승격(2단계 선택)으로 근본 완화. |
| 담당자/상태 표기 흔들림 | clevel/status 오분류 | 정규화 테이블(별칭 다수) + 미매칭 시 원문 보존. |
| GAS 무인증 개방(기존 보안 과제) | 시트 변조 가능 | 별도 보안 과제(메모리 기록됨). 본 계획 범위 밖. |
| processed_at 누락 → 8시/21시 '마무리' 0건 | 보고 누락 | DONE 행은 수정일→processed_at 자동 채움. 임베드값 우선. |

---

## 5. GM 수동 필요 항목 (결재·재배포)

| 항목 | 시점 | 사유 |
|---|---|---|
| GAS `CATEGORIES` 에 `[7]AI배(C레벨)` 정식 등재 | 2단계(선택) | 드롭다운 노출용. 미등재여도 셀 자유입력으로 동작. **clasp push ≠ 재배포** — 새 버전 배포 필요. |
| GAS 신규 액션 `ai_queue_*` 추가 + 재배포 | 3단계 | WRITER의 시트 직접 쓰기 전환. |
| `내용` 임베드 → 정식 컬럼 승격(append-only) + 재배포 | 2단계(선택) | 손상 위험 근본 완화. 기존 컬럼 인덱스 불변(append-only) 유지. |
| G1 HTML AI 배 편집 UI 배포(push + 라이브 검증) | 4단계 | Pages는 origin 기준 — push+라이브 검증까지가 완료. |

> 1단계(본 작업)는 **GM 수동 불필요** — 신규 파일 2개 생성·검증만. GAS 재배포 없음.

---

## 6. 검증 방법

- **스키마 동등성:** `python scripts/queue_sync_from_sheet.py --mock <샘플> --diff`
  → 모의 AI행으로 생성한 결과가 현행 `_queue.json` 스키마와 줄 단위 일치하는지 확인.
- **reader 계약:** 생성 항목이 hangro_board / bot 결재후보 / 8시·21시 집계의 필드 접근을
  모두 만족(task_id·clevel·status·deadline·priority·processed_at·enqueued_at·title).
  1단계 검증에서 PASS 확인(모의 2건 — PENDING 1·DONE 1).
- **비파괴 확인:** 기본 실행은 stdout 미리보기뿐(`--write` 명시해야 파일 변경).
  실데이터 `_queue.json` 은 1단계에서 건드리지 않음.

---

## 7. 변경 파일 요약 (1단계)

- `scripts/queue_sync_from_sheet.py` (NEW) — 시트 AI행 → `_queue.json` 단방향 미러 생성기.
- `docs/queue_to_sheets_migration_plan.md` (NEW) — 본 계획서.
- 기존 자동화(.py)·GAS·`_queue.json` 실데이터 무수정. git push 없음.

---

## 8. 2026-06-13 재개 실측 진단 — 현 상태·위험·권고 (시토, read-only)

**실측 결과 (시트·데이터 변경 0):**
- 06-08 이관은 **기능적으로 완료**됨: 전용탭 `AI배(C레벨)` seed 21건 + GAS v@53(`ai_list`/`ai_sheet_create`) 배포 + 동등검증 PASS (근거: `queue_migration_move_result_20260608.md`).
- `todo_list` 카테고리 AI배 = **0건** (06-07 사고 잔재 없음 — revert 깨끗, 실측 확인).
- **미진행:** S4(자동 동기화 스케줄)·S5(WRITER 시트 전환) — 둘 다 GM 게이트 대기. 스케줄러/배치/훅에 `queue_sync_from_sheet --write` **미등록** 실측 확인.

**🔴 핵심 위험 — SSOT 갈라짐(divergence):**
- 06-08 이후 5일간 S4/S5 미적용 → 기존 WRITER(브릿지·결재·watcher)가 `_queue.json`에 계속 직접 씀.
- 결과: `_queue.json` = **33건(최신, 06-13)** vs 전용탭 = **21건(06-08 화석)**.
- **시트→`_queue` `--write`(S4)를 지금 켜면 최신 33건이 낡은 21건으로 덮여 06-09~13 작업·상태가 유실됨.** 이것이 06-07 사고 메커니즘. **S4 선행 절대 금지.**

**안전 재개 단계 (실행 전 GM 승인 · 각 검증·롤백):**
| 단계 | 내용 | 검증 | GM수동 |
|---|---|---|---|
| R0 | 진실 소스 = `_queue`(최신) 채택 확정 | — | 결정 |
| R1 | 전용탭 화석 21건 비우기 | 시트 0건 ASSERT | GAS |
| R2 | 현 `_queue` 살아있는 건만 → 전용탭 재seed (1건씩, `queue_seed_to_sheet`) | 건별 ASSERT | — |
| R3 | 동등 검증 `queue_sync --diff` = 동등 | DIFF 0 | — |
| R4 | S4 자동 sync 등록(07:55/20:55) | 1회 dry-run | 승인 |
| R5 | S5 WRITER→GAS `ai_update` 전환 | 이중화 기간 | 승인·재배포 |

**권고 (시토):**
- 이관은 06-08에 기능 완료됐고 이후 미동기화로도 5일 무문제 → **S4/S5 우선순위 낮음.**
- 'G1 인라인 편집'(4단계) 목적이 GM의 'AI배 읽기전용 원복'(웰리 관리, 2026-06-07) 방침과 상충 → **목적 재확인 전까지 S4/S5 보류** 권고.
- 사고 방지: 전용탭 화석은 누군가 `--write` 시 폭탄 → **R1(비우기)** 또는 전용탭 헤더에 "⚠️ 06-08 화석·미동기화" 경고 권고.

*실측: 2026-06-13 시토 / 데이터·시트 변경 0(read-only)*
