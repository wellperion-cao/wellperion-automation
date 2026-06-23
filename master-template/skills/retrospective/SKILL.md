---
title: retrospective
purpose: 사이클 종료 후 교훈을 도출하고 ssot를 업데이트한다
when_to_use: 매 사이클 완료 후. 인시던트 발생 후
when_not_to_use: 사이클 미완료 상태 (완료 4요건 통과 후 실행)
inputs:
  - 사이클 실행 기록
  - PASS/FAIL 결과
  - 발생한 오류·블록 사유
outputs:
  - 교훈 목록 (잘된 것·개선점·재발방지)
  - ssot/약속.json 업데이트 (새 교훈 추가)
  - ssot/incidents.json 업데이트 (인시던트 발생 시)
  - memory-update 스킬 호출
---

## workflow

1. **잘된 것**: 이번 사이클에서 효과적이었던 것
2. **개선점**: 다음에 다르게 할 것
3. **재발방지**: 같은 실수가 반복되지 않으려면?
4. 새 교훈이 기존 약속과 중복 아닌지 확인
5. 새 약속 → `ssot/약속.json`에 추가 (id 채번: P-NNN)
6. 인시던트 발생 시 → `ssot/incidents.json`에 추가
7. memory-update 스킬 호출

## do
- 교훈은 구체적으로 (추상적인 "더 잘하자" 금지)
- 인시던트는 차단 조치가 코드/장치로 박제된 경우만 GUARDED 전환
- 약속 추가 시 기존과 중복 확인 필수

## dont
- 문서만 쓰고 코드 박제 없이 GUARDED 전환 금지
- 교훈 없이 통과 금지 (짧더라도 1개 이상)
- 약속 삭제 금지 (비활성화만: "활성": false)
