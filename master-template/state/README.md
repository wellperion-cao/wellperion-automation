# state/ — 작업 상태 단일 진실

## _queue.json

모든 태스크의 단일 진실. 규칙:

- 태스크 추가: planner 또는 오케스트레이터만
- 상태 변경: 담당 에이전트가 실행 시
- 완료된 태스크 삭제 금지 (기록 보존)
- 큐가 비면 → 대기 상태 (새 지시 대기)
- DONE 전환 조건: 완료 4요건(`loop/quality-gates.md`) 모두 통과

## memory/

세션 간 영구 기억 저장소. 규칙:

- 파일별 1개 사실
- `MEMORY.md`: 인덱스 (한 줄 per 메모리)
- 삭제 금지 (오래되거나 틀린 것은 교체)
- repo에 이미 있는 정보 저장 금지

## 태스크 상태 전환

```
PENDING → IN_PROGRESS → DONE
                      ↘ BLOCKED → IN_PROGRESS (재시도)
                                ↘ PENDING (에스컬레이션 후 재개)
```
