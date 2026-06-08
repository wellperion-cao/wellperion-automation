# AI 배 이관 S4·S5 실행계획
작성: AI CTO(시토) · 2026-06-08 · S3 완료 후

---

## 현재 상태 (S3 완료 기준)

| 항목 | 상태 |
|---|---|
| 구글시트 `[7]AI배(C레벨)` | **SSOT(원본)** — 20건 시드 완료 |
| `status/_queue.json` | **미러(캐시)** — 시트발 재생성 완료 |
| 수동 `--write` 1회 | 완료 (trailing newline 정규화만, 데이터 무변화) |
| readers(8시·21시·G1·hangro_board) | 여전히 `_queue.json` 직접 읽음 — 무수정 |
| WRITER(clevel_post_action·bot·watcher) | 여전히 `_queue.json` 직접 씀 — **미전환** |

---

## 핵심 위험: 쓰기 충돌

S4(자동 동기화)를 켜면 **미러 생성기(`--write`)와 기존 WRITER가 동시에 `_queue.json`을 덮어쓸 수 있다.**

| WRITER | 쓰기 빈도 | 충돌 위험 |
|---|---|---|
| `clevel_post_action.py` | 브릿지 완료 시마다 | 중 — 수시 발생 |
| `telegram_bot/bot.py` 결재 라우터 | GM 결재 회신 시마다 | 중 — 수시 발생 |
| `scripts/ceo_watcher.py` | 큐 선두 처리 시 | 중 — 자동 실행 |
| `wellperion-agents/scripts/queue_archive.py` | 야간 아카이브 | 낮음 |
| **미러 생성기 `--write`** | S4 트리거 주기마다 | 위와 충돌 |

**충돌 시 결과:** 한쪽 변경 유실. 원자적 `.tmp→replace`가 적용돼 있어 파일 손상은 없지만, 마지막 쓰기가 이전 쓰기를 덮어씀.

---

## 권고 설계: WRITER 시트 전환(S5) 선행이 안전

| 방식 | 장단점 |
|---|---|
| **A. 자동 동기화만(S4) — WRITER 미전환** | 빠르지만 충돌 상시 위험. 동기화 주기와 WRITER가 겹치면 변경 유실. 근본 해결 아님. |
| **B. WRITER 시트 전환(S5) 후 S4** | 안전·완결적. _queue.json은 순수 읽기 전용 미러가 돼 충돌 원천 차단. GAS 재배포 필요(GM 수동). |

**권고: B안.** S4(자동 동기화 트리거)는 S5(WRITER 전환) 완료 후 켜는 것이 안전. S4를 먼저 켜더라도 **WRITER 비활성 시간대(새벽 2~6시)에만** 한정하면 임시 완화 가능.

---

## S4 — 동기화 자동화 (트리거 등록)

> ⚠️ **지금 켜지 마라** — S5(WRITER 전환) 완료 전에는 WRITER 비활성 시간대 한정 or 미실행.

### S4-a: Task Scheduler 주기 등록 (GM 수동)

| 스텝 | 동작 | 검증 | 롤백 | GM수동? |
|---|---|---|---|---|
| S4-a1 | `launchers/sync_queue_from_sheet.vbs` 숨김 런처 생성 (`python queue_sync_from_sheet.py --write` 래핑) | 파일 존재 확인 | 파일 삭제 | 불필요(시토) |
| S4-a2 | Task Scheduler에 예약작업 등록: 매일 새벽 03:00, `sync_queue_from_sheet.vbs` 실행 | 작업 목록에 등재 확인 | 작업 비활성화/삭제 | **GM (관리자 권한 실행)** |
| S4-a3 | 1주기 후 `_queue.json` 무변동·중복 0 확인 | `git diff status/_queue.json` = 0 | 작업 비활성화 | 불필요 |

### S4-b: 8시·21시 보고 직전 1회 동기화 (대안)

| 스텝 | 동작 | 검증 | 롤백 | GM수동? |
|---|---|---|---|---|
| S4-b1 | `ceo_morning_pipeline.py` 맨 앞에 `subprocess.run(['python', 'queue_sync_from_sheet.py', '--write'])` 추가 | 8시 보고 정상 실행 확인 | 해당 라인 제거 | 불필요(시토) |
| S4-b2 | `ceo_evening_wrap.py` 동일하게 추가 | 21시 보고 정상 실행 확인 | 동일 | 불필요(시토) |

**S4 권고: S4-b(보고 직전 1회)가 더 단순하고 충돌 위험 낮음.** 보고 직전은 WRITER가 거의 쉬는 시간대이며, 실패해도 보고가 직전 `_queue.json`으로 fallback.

---

## S5 — WRITER 시트 직접 쓰기 전환

> S4보다 큰 작업. GAS 재배포 필수(GM 수동). 3개 WRITER 순차 전환.

### 사전 조건
- GAS에 `ai_queue_update`, `ai_queue_done`, `ai_queue_approve` 액션 추가 + 재배포 (GM 수동)
- `_queue.json`이 순수 읽기 전용 미러로 확정된 후 전환

### S5 스텝

| 스텝 | 동작 | 검증 | 롤백 | GM수동? |
|---|---|---|---|---|
| S5-0 | GAS에 `ai_queue_update(id, fields)` 액션 추가 — 시트 AI행 특정 컬럼(상태·수정일·next 등) 업데이트 | `?action=ai_queue_update` 호출 테스트 | GAS 이전 버전 재배포 | **GM (GAS 재배포)** |
| S5-1 | `clevel_post_action.py`: `_queue.json` 직접 패치 → GAS `ai_queue_update` POST 전환. 병렬 이중화 기간(2주) 유지 | 브릿지 완료 후 시트 상태 업데이트 확인, `--diff` 0줄 | 코드 revert | 불필요(시토) |
| S5-2 | `telegram_bot/bot.py` 결재 라우터: status 패치 → GAS `ai_queue_update` 전환. 이중화 유지 | GM 결재 회신 후 시트 반영 확인 | 코드 revert | 불필요(시토) |
| S5-3 | `ceo_watcher.py`: `_queue.json` 처리 → GAS 전환. 이중화 유지 | watcher 실행 후 시트 반영 확인 | 코드 revert | 불필요(시토) |
| S5-4 | 2주 이중화 기간 후 `_queue.json` 직접 쓰기 코드 제거. 미러 생성기만 남음 | `_queue.json` 쓰기 코드 0건 확인 | 이전 커밋 cherry-pick | 불필요(시토) |

### S5-0 GAS 액션 설계 (시토 초안 — GM 결재 후 재배포)

```javascript
// GAS에 추가할 ai_queue_update 액션
case 'ai_queue_update': {
  const id = params.id;  // task_id or 시트 행 id
  const fields = params.fields;  // {status, processed_at, next, ...}
  const sheet = ss.getSheetByName('AI배');  // [7]AI배(C레벨) 전용 탭 or 필터
  // id로 행 찾아 내용 셀 임베드 블록 업데이트
  // → _queue.json은 다음 --write 때 자동 반영
  break;
}
```

---

## GM 수동 필요 항목 요약

| # | 항목 | 시점 | 사유 |
|---|---|---|---|
| 1 | Task Scheduler 예약작업 등록 (S4-a2) | S4 실행 시 | 관리자 권한 필요 |
| 2 | GAS `ai_queue_update` 액션 추가 + 재배포 (S5-0) | S5 실행 시 | GAS 재배포 필요 |
| 3 | 시트 URL 회수 | 별도 | clasp 재인증 후 `open-container` or GAS `getActiveSpreadsheet().getUrl()` 추가 재배포 |

**GM 수동 총 3건 (S4 진행 시 1건, S5 진행 시 2건)**

---

## 시트 URL 회수 불가 사유

- `.deploy-todo/.clasp.json`에 `parentId` 미기재 (컨테이너 바인딩이라 코드에 시트 ID 없음)
- `clasp open-container` → "Parent ID not set" 오류
- Apps Script API `/v1/projects/{scriptId}` → clasp 인증 만료(401/invalid_rapt)
- GAS `getActiveSpreadsheet().getUrl()` 호출은 재배포 없이 불가
- **결론: clasp 재인증(`clasp login`) 후 `clasp open-container` 실행하면 브라우저에서 시트가 열림 — 그게 시트 URL. GM이 직접 확인 가능.**

---

## 다음 액션 (우선순위순)

1. **즉시 가능**: S4-b (8시 보고 직전 동기화 1줄 추가) — GM 승인 시 시토 실행
2. **GM 수동**: `clasp login` 재인증 → `clasp open-container` → 시트 URL 확인
3. **중기**: S5-0 GAS 액션 설계 확정 → GM 결재 → 재배포 → S5-1~4 순차 전환
