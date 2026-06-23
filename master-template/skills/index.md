# 스킬 목록

| 스킬 | 파일 | 언제 쓰나 |
|------|------|----------|
| intake | `intake/SKILL.md` | 새 작업 진입 시 목표·범위·성공조건 명확화 |
| decompose | `decompose/SKILL.md` | 큰 목표를 검증 가능한 태스크 단위로 분해 |
| implement | `implement/SKILL.md` | 단일 태스크 실행·구현 |
| verify | `verify/SKILL.md` | 실행 결과 검증·완료 4요건 확인 |
| memory-update | `memory-update/SKILL.md` | 세션 간 영구 기억 저장·갱신 |
| retrospective | `retrospective/SKILL.md` | 사이클 종료 후 교훈 도출·ssot 업데이트 |

## 호출 순서 (일반 사이클)

```
intake → decompose → [implement → verify]* → retrospective → memory-update
```

`*` = 태스크 수만큼 반복 (경계 있는 루프, `loop/swarm-loop.md` 참조)
