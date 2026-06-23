# 경계 있는 스웜 루프

## 핵심 원칙

무한 루프 금지. 모든 반복에 경계가 있다.

## 13단계 루프

```
사이클 시작
│
├─ 1. 부팅: ssot 3종 직독 (약속·incidents·canon)
│
├─ 2. 큐 확인: _queue.json PENDING/IN_PROGRESS 태스크 확인
│         └─ 큐 비면 → 대기 (새 지시 대기)
│
├─ 3. 인테이크: intake 스킬 실행 (모호도 > 5% → 휴먼 확인)
│
├─ 4. 계획·분해: decompose 스킬 실행
│         └─ 병렬 가능 태스크 식별
│
├─ 5. 라우팅: 태스크별 에이전트·모델 배정 (토큰 라우팅 원칙)
│
├─ 6. 실행: executor → implement 스킬
│         └─ 독립 태스크 병렬 실행
│
├─ 7. 검증: reviewer → verify 스킬 (완료 4요건)
│         ├─ PASS → 8단계
│         └─ FAIL → 재시도 예산 차감 → 6단계 (한도 내)
│
├─ 8. 큐 업데이트: 태스크 DONE 전환
│
├─ 9. 수렴 확인: 목표 달성 여부
│         ├─ 달성 → 10단계
│         └─ 미달성 → 다음 사이클 (최대 사이클 내)
│
├─ 10. 반성: retrospective 스킬 실행
│
├─ 11. 메모리 업데이트: memory-update 스킬 실행
│
├─ 12. 완료 선언 또는 BLOCKED 보고
│
└─ 사이클 종료
```

## 경계 (반드시 준수)

| 경계 | 기본값 | 위치 |
|------|--------|------|
| 태스크당 재시도 최대 | 3회 | canon.json `loop_limits.max_retries_per_task` |
| 최대 사이클 | 10 | canon.json `loop_limits.max_cycles` |
| 수렴 판단 | 3사이클 연속 진전 없음 | canon.json `loop_limits.stall_threshold_cycles` |

## 정지 조건

아래 중 하나 → 즉시 중단 + 오케스트레이터 BLOCKED 보고:

- 재시도 예산 소진
- 최대 사이클 초과
- 수렴 불가 (stall_threshold 초과)
- 휴먼 승인 필요 항목 미승인
- 공식값 누락으로 진행 불가
- 파괴적 동작 감지

## 수렴 조건

모든 PENDING/IN_PROGRESS 태스크가 DONE 상태 + 목표 성공조건 충족.
