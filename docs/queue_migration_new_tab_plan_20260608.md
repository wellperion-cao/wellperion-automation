# AI 배 전용 탭 이관 계획 (2026-06-08)

> GM 결정: AI C레벨 배를 실무진 `todo_list` 탭과 섞지 않고,
> 같은 스프레드시트(`업무&결재 현황 SSOT`) 안에 **신규 탭 `AI배(C레벨)`** 로 분리.

---

## 설계 요약

| 항목 | 기존(S2까지) | 신설(이 계획) |
|---|---|---|
| AI 배 위치 | `todo_list` 탭 — 카테고리 `[7]AI배(C레벨)` | `AI배(C레벨)` 전용 탭 |
| 식별 방식 | 카테고리 컬럼 필터 | 탭 자체가 AI 배 전용 |
| GAS 읽기 | `todo_list` 액션 + 카테고리 필터 | 신규 `ai_list` 액션 + `sheet` 파라미터 |
| 컬럼 스키마 | todo_list 공용 컬럼 | 동일 컬럼 유지(재사용) |
| embed 블록 | 내용 셀 `===AI_QUEUE===` | 동일 유지 |
| 생성기 모드 | `--sheet-name` 미지정 = 구 방식 | `--sheet-name 'AI배(C레벨)'` = 신규 탭 |

---

## 코드 준비 현황 (GM 게이트 없이 완료)

- [x] `scripts/queue_sync_from_sheet.py`
  - `AI_SHEET_NAME = "AI배(C레벨)"` 상수 추가
  - `AI_LIST_ACTION = "ai_list"` 상수 추가
  - `fetch_ai_sheet_rows(sheet_name)` 함수 추가 (GAS 배포 후 동작)
  - `build_queue(..., all_rows_are_ai=bool)` 파라미터 추가
  - CLI `--sheet-name SHEET` 인수 추가

현재 `--sheet-name` 으로 호출하면 GAS 오류(미배포) — 준비 코드, 게이트 후 동작.

---

## 단계별 실행 계획

### STEP A — 탭 생성 (GM 수동 · 게이트 필요)

**GM이 직접 구글 시트에서:**
1. 스프레드시트 열기 (아래 URL 회수 방법 참조)
2. 하단 탭 영역 `+` 클릭 → 새 시트 추가
3. 탭 이름을 **정확히 `AI배(C레벨)`** 로 지정 (공백·특수문자 오타 주의)
4. `todo_list` 탭의 **1행(헤더)** 을 복사 → 새 탭 A1에 붙여넣기
   - 헤더: `id | 업무명 | 담당자 | 상태 | 카테고리 | 종료일 | 난이도 | 내용 | 생성일 | 수정일`
   - (정확한 컬럼 순서는 todo_list 탭 1행 참조)
5. 완료 후 웰리에 "탭 생성 완료" 통보

### STEP B — 20건 이동 (자동 스크립트 · GM 승인 필요)

`scripts/queue_seed_to_sheet.py` 를 `--target-sheet 'AI배(C레벨)'` 옵션으로 실행.
(현재 seed 스크립트는 `todo_list` 대상 — 옵션 추가 후 실행)

사전 검증:
- 새 탭 행 수 = 1(헤더만) 확인
- seed 실행 후 행 수 = 21(헤더+20) 확인
- task_id 중복 없음 확인

### STEP C — todo_list 탭에서 AI 배 행 삭제 (GM 승인 필요)

`todo_list` 탭에서 카테고리 `[7]AI배(C레벨)` 행 20건 삭제.
- 삭제 전 `AI배(C레벨)` 탭 20건 정상 확인 필수
- 삭제 후 `todo_list` 행 수 assert

### STEP D — GAS `ai_list` 액션 추가·배포 (GM clasp 로그인 필요)

`.deploy-todo/업무&결재 현황.js` 에 신규 액션 추가:
```javascript
// ai_list: AI배(C레벨) 전용 탭 조회
// GET ?action=ai_list&sheet=AI배(C레벨)
if (action === "ai_list") {
  const sheetName = params.sheet || "AI배(C레벨)";
  const ws = ss.getSheetByName(sheetName);
  if (!ws) return json({ ok: false, error: "sheet_not_found: " + sheetName });
  // todo_list 와 동일한 컬럼 파싱 로직 재사용
  const rows = readSheet(ws);  // 기존 readSheet 함수 활용
  return json({ ok: true, count: rows.length, data: rows });
}
```

배포 절차:
1. `clasp login` (GM PC에서 대화형 로그인 — RAPT 재인증)
2. `clasp push`
3. Apps Script 웹 앱 새 버전으로 재배포 (Deploy > New deployment)
4. 배포 URL 변경 여부 확인(변경 시 `GAS_URL` 상수 업데이트)

### STEP E — 생성기 전환 검증

```bash
# 신규 탭 모드로 미리보기
python scripts/queue_sync_from_sheet.py --sheet-name "AI배(C레벨)"

# diff 검증 (현재 _queue.json 과 동등 확인)
python scripts/queue_sync_from_sheet.py --sheet-name "AI배(C레벨)" --diff

# 동등 확인 후 --write
python scripts/queue_sync_from_sheet.py --sheet-name "AI배(C레벨)" --write
```

### STEP F — S4 자동 동기화 (별도 GM 승인)

Task Scheduler 예약작업 등록: `queue_sync_from_sheet.py --sheet-name 'AI배(C레벨)' --write`
- 실행 주기: 08:00 보고 직전 (07:55) 및 21:00 마무리 직전 (20:55)
- WRITER 충돌 해소 후 진행 (S5 먼저)

### STEP G — WRITER 전환 (S5 · 별도 GM 승인)

`clevel_post_action.py` / `bot.py` / `ceo_watcher` 등 기존 WRITER 들을
`_queue.json` 직접 쓰기 대신 GAS `ai_update` 액션 호출로 전환.
(설계 상세 = `docs/queue_migration_s4_s5_plan_20260608.md` 참조)

---

## GM 수동 체크리스트

### 탭 생성 전 확인 (STEP A)
- [ ] 스프레드시트 URL 확보 (`clasp login` → `clasp open-container` 또는 직접 시트 열기)
- [ ] `todo_list` 탭 헤더 컬럼 순서 육안 확인
- [ ] 새 탭 이름 **정확히 `AI배(C레벨)`** (복사 붙여넣기 권장)

### 이동 실행 전 확인 (STEP B)
- [ ] 신규 탭 행 수 = 1 (헤더만)
- [ ] `todo_list` AI 배 행 수 = 20 확인
- [ ] 웰리에 "STEP A 완료, B 진행 승인" 통보

### 삭제 전 확인 (STEP C)
- [ ] `AI배(C레벨)` 탭 행 수 = 21 (헤더+20)
- [ ] 임의 3건 task_id 시트↔_queue.json 일치 육안 확인
- [ ] 웰리에 "B 완료, C 진행 승인" 통보

### GAS 배포 전 확인 (STEP D)
- [ ] `clasp login` 완료 (대화형 브라우저 인증)
- [ ] `clasp push` 성공
- [ ] Apps Script 편집기에서 `ai_list` 액션 코드 확인
- [ ] 새 버전 배포 후 테스트 URL 응답 확인

### 생성기 전환 전 확인 (STEP E)
- [ ] `--diff` 출력 = "동등"
- [ ] `--write` 후 hangro_board G1 정상 표시

---

## 스프레드시트 URL 회수 방법

현재 RAPT 재인증 필요로 자동 회수 불가. GM 직접 방법:

**방법 1 (추천):**
1. Google Drive 열기 → `업무&결재 현황 SSOT` 검색
2. 파일 클릭 → URL 확인 (`https://docs.google.com/spreadsheets/d/SHEET_ID/...`)

**방법 2:**
```bash
# GM PC에서 한 번만 실행 (대화형 필수)
cd C:\Users\jjky0\welperion-automation\.deploy-todo
clasp login
clasp open-container
# 브라우저에 시트 URL이 열림
```

---

## 이전 계획과의 관계

| 문서 | 상태 |
|---|---|
| `docs/queue_migration_diagnosis_20260608.md` | 유효(S0~S3 완료 기록) |
| `docs/queue_migration_s4_s5_plan_20260608.md` | 부분 유효 (S4/S5 설계 참조용, 탭 분리 이전 기준) |
| **본 문서** | **현행 정본 — GM 결정 2026-06-08 설계 변경 반영** |

---

*작성: 2026-06-08 / 코드 준비 커밋 포함*
