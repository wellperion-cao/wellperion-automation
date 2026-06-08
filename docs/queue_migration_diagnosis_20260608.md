# AI 배 _queue → 구글시트 SSOT 이관 안전진단
작성: AI CTO(시토) · 2026-06-08 · 이관 재개 전 read-only 진단

---

## A) P1 미러 생성기(`queue_sync_from_sheet.py`) 검증

| 테스트 | 방법 | 결과 |
|---|---|---|
| 실시트 `--diff` | GAS todo_list 실조회 → 생성본 vs 현행 _queue 비교 | 생성본 = `[]`(시트 AI행 0건이므로 정상) |
| round-trip 줄단위 (S0 수정 전) | 현행 20건 → 시트행 역변환 → 재생성 → 줄비교 | **FAIL — 65줄 diff** |
| round-trip 줄단위 (S0 수정 후) | 동일 방법 (커밋 a37e9a4 적용) | **PASS — 0줄 diff, 20건** |

**판정: PASS** (S0 수정 완료 후 기준)

S0에서 수정한 결함 2개:
1. `note_progress` 등 비표준 필드 화이트리스트 → 임베드 전체 키 복원 방식으로 전환(누락 필드 0)
2. 고정 순서 삽입 → 임베드 키 순서 그대로 삽입(필드 순서 불일치 해소)

관련 커밋: `a37e9a4` (fix), `29a425a` (S2 dedup 스크립트 추가)

---

## B) 시트(todo_list) 사고 잔재 점검

- 실측: GAS `?action=todo_list` 조회 → 전체 **55행**
- `[7]AI배(C레벨)` 카테고리 = **0건**
- 어제(2026-06-07) 2단계 대량처리 사고의 잔재 **없음**
- revert(`9458937`) 복구 완전 — 다음 sync 시 중복 생성 위험 없음

---

## C) 현행 `_queue.json` AI 배 목록 — 20건

| # | task_id | clevel | status |
|---|---|---|---|
| 1 | CEO-2026-05-30-REPORT-CONTENT-POLISH | ceo | PENDING |
| 2 | CTO-2026-06-04-DANGGN-SEMIAUTO | cto | DONE |
| 3 | COO-2026-06-04-SUPPORT-ISSUE-SAVE | coo | DONE |
| 4 | CHRO-2026-06-04-HR-NOTION-TO-SHEETS | chro | 폐기 |
| 5 | COO-2026-06-04-TODO-UPDATE-EMPTY-OVERWRITE | coo | DONE |
| 6 | CMO-2026-06-06-INQUIRY-DASHBOARD-PIPELINE | cmo | DONE |
| 7 | CMO-2026-06-06-CHANNEL-EXPANSION | cmo | DONE |
| 8 | CMO-2026-06-06-EXPERIMENT-01-IG-CTA | cmo | IN_PROGRESS |
| 9 | CMO-2026-06-06-CHANNEL-ENGAGEMENT | cmo | IN_PROGRESS |
| 10 | CTO-2026-06-08-CFO-SHEET-LINK | cto | PENDING |
| 11 | COO-2026-06-07-OPS-GUIDELINE | coo | IN_PROGRESS |
| 12 | CHRO-2026-06-07-GAS-SHEETS-REDEPLOY | chro | 폐기 |
| 13 | CHRO-2026-06-07-OPS-STAFF-TRAINING | chro | IN_PROGRESS |
| 14 | CMO-2026-06-07-KAKAO-PUBLISH-RND | cmo | DONE |
| 15 | CMO-2026-06-07-UNPUBLISHED-CONTENT | cmo | IN_PROGRESS |
| 16 | CMO-2026-06-07-FUNNEL-DATA-CONNECT | cmo | IN_PROGRESS |
| 17 | CMO-2026-06-07-GUIDE-PRICING-UPDATE | cmo | IN_PROGRESS |
| 18 | CTO-2026-06-08-TELEGRAM-ALERT-AUDIT | cto | PENDING |
| 19 | CMO-2026-06-08-AI8-RELEASE | cmo | DONE |
| 20 | CTO-2026-06-08-QUEUE-SHEET-MIGRATION-RESUME | cto | IN_PROGRESS |

집계: IN_PROGRESS 9 / DONE 6 / PENDING 3 / 폐기 2

---

## D) 미세 단계별 실행계획

| 스텝 | 동작 | 검증 | 롤백 | GM수동? |
|---|---|---|---|---|
| **S0** ✅완료 | 생성기 결함 수정: `note_progress` 보존 + 키순서 임베드 순서 보존 | round-trip `--diff` = 0줄 (PASS) | `git revert a37e9a4` | 불필요 |
| **S1** | 시트에 AI 배 **1건만** 수동 시드 입력(임베드 블록 + task_id 필수). 대상: `CEO-2026-05-30-REPORT-CONTENT-POLISH` | `python scripts/queue_sync_from_sheet.py --diff` → 1건만 정확히 생성·중복 0 | 시트에서 해당 1행 삭제 | **GM(시트 직접 입력) 또는 시토 `queue_seed_to_sheet.py --execute --limit 1` 승인** |
| **S2** | 나머지 19건 시드 insert — `queue_seed_to_sheet.py --execute` (task_id dedup 가드 자동, 1건씩 순차, insert 후 count assert) | insert 전후 AI행 count 검증(1→20), task_id 유니크 확인 | task_id 기준 해당 행만 시트 삭제 | 불필요(스크립트 자동) |
| **S3** | `queue_sync_from_sheet.py --write` 최초 1회 실행 → _queue.json 시트발 재생성 | 재생성 20건, 8시/21시/G1 readers 실측 정상 | `git checkout status/_queue.json` | 불필요 |
| **S4** | 동기화 트리거 등록(Task Scheduler 주기 실행 or 8시 보고 직전 1회). WRITER 비활성 시간대만 | 1주기 후 _queue 무변동·중복 0 | 예약작업 비활성화 | **GM(예약작업 등록 실행)** |
| **S5** (선택) | GAS `CATEGORIES` 드롭다운에 `[7]AI배(C레벨)` 정식 등재 + 재배포 | 드롭다운 노출 확인 | 이전 버전 재배포 | **GM(GAS 재배포)** |

### 중복 0 보장 메커니즘 (S1~S2 핵심)
- 시드 insert 전 시트 현황 조회 → 같은 task_id 존재 시 SKIP (idempotent)
- insert 후 count assert: `before_count + inserted == after_count` 불일치 시 즉시 중단
- 어제 사고 원인(가드 없이 1회 대량 blind-append) 구조적으로 차단

---

## E) 다음에 실행해도 안전한 첫 스텝

**S1 — 시트 1건 시드 입력**

두 가지 경로 중 하나:

**경로 A (시토 스크립트, 즉시 가능)**
```
python scripts/queue_seed_to_sheet.py --execute --limit 1
```
- 시트에 `CEO-2026-05-30-REPORT-CONTENT-POLISH` 1건만 insert
- dedup 가드·count assert 자동 검증
- 실패 시 자동 중단

**경로 B (GM 시트 직접 입력)**
- todo_list 시트 빈 행 → 카테고리: `[7]AI배(C레벨)`
- 업무명: `[웰리-01] 아침/저녁 자동보고 내용 가다듬기`
- 내용 셀:
```
===AI_QUEUE===
{"task_id":"CEO-2026-05-30-REPORT-CONTENT-POLISH","clevel":"ceo","status":"PENDING","priority":"NORMAL","enqueued_at":"2026-05-30","note":"형식은 GM 승인 완료(표+결정중심·3분류·제목요약·운영기본값 SSOT). 내용 디테일은 GM 회사 출근 후 구체 피드백 예정 → 그때 반영."}
===END===
```

S1 완료 후: `python scripts/queue_sync_from_sheet.py --diff` → 1건 생성 확인 → S2 승인 시 진행.

---

*진단 기준: 2026-06-08 실측. 시트 접근 = GAS 무인증 공개 엔드포인트(정상 동작). 인증 문제 없음.*
