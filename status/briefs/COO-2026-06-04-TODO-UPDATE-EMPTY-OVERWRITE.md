# COO-2026-06-04-TODO-UPDATE-EMPTY-OVERWRITE — 업무 편집 시 빈값 덮어쓰기(초기화) 근본 차단

**인계: 시토(CTO) → 시우(COO)** · 2026-06-04 · GM 직접 버그 제보("편집하면 다른 필드 초기화")

## 증상 (GM)
G1/업무 카드에서 일정 또는 내용 한쪽을 편집·저장하면, 편집 안 한 다른 필드(종료일·결재·진척 등)가 이상하게 변경되거나 **초기화**됨.

## 근본 원인 (시토 진단 확정)
- 프론트 `gm1SyncUpdate`(메인 가이드 ~8145)가 **빈 문자열('') 필드까지 todo_update로 전송**.
- GAS `todo_update`(`coo/todo/apps_script_todo.js:562-564`)가 `if (body[h] !== undefined && body[h] !== null) existing[i] = body[h];` → **빈 문자열을 갱신값으로 받아 기존값 덮어씀**.
- 한 필드만 편집해도 모달에 안 로드/빈 필드가 ''로 전송돼 시트에서 초기화.

## 시토 즉시 핫픽스(완료·배포)
- G1 `gm1SyncUpdate`: 빈값·null 필드를 querystring 전송 제외(action·id만 항상). → 서버 기존값 보존. (commit f28fb27)

## 시우 근본 작업 (요청)
1. **GAS `todo_update` 빈값 스킵** (`apps_script_todo.js:562-564`): 조건에 `&& body[h] !== ''` 추가 → 모든 호출 경로 보호(프론트 어디서 빈값 보내도 안전). **단 의도적 '비우기'(종료일 삭제 등)가 막히므로**, 비우기가 필요하면 별도 센티넬(예 `__CLEAR__`) 설계 검토. **GAS 웹앱 재배포 필수**(clasp push≠배포, 메모리 [[reference_clasp_webapp_redeploy]]).
2. **업무현황 SSOT(`coo/todo/업무 현황 SSOT.html`) 동일 패턴 점검**: 편집 저장 시 빈값 전송으로 같은 초기화 버그 있는지 확인·동일 방어 적용.
3. 라이브 실측: 한 필드만 편집→나머지 필드 보존되는지 + 의도적 비우기 동작 확인.

## 참고
- 시토 핫픽스로 G1은 당장 해소. 근본(GAS)·업무현황 페이지는 본 작업으로 완전 차단.
- API: `SSOT_API_URL`(AKfycbxDw…/exec)
