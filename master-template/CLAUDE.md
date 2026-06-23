# 마스터 템플릿 인덱스

> 이 파일은 인덱스. 원칙 상세 하드코딩 금지 — AGENTS.md와 ssot/가 단일 출처.

## 핵심 포인터

| 항목 | 위치 |
|------|------|
| 에이전트 헌법 | `AGENTS.md` |
| 공유 규칙·교훈 | `ssot/약속.json` |
| 재발방지 | `ssot/incidents.json` |
| 공식값 | `ssot/canon.json` |
| 작업 큐 | `state/_queue.json` |
| 스웜 루프 | `loop/swarm-loop.md` |
| 품질 게이트 | `loop/quality-gates.md` |

## 부팅 순서

1. `ssot/약속.json` 직독
2. `ssot/incidents.json` 직독
3. `ssot/canon.json` 직독
4. `AGENTS.md` 전체 흡수
5. `state/_queue.json` 현황 확인

## 에이전트 목록

`agents/` 폴더:
- `orchestrator.md` — 전체 조율·판단
- `planner.md` — 계획·분해
- `executor.md` — 실행·구현
- `reviewer.md` — 검증·품질
- `researcher.md` — 리서치·정보

## 스킬 목록

`skills/index.md` 참조.
