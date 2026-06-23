# 마스터 템플릿 인덱스

> 이 파일은 인덱스. 원칙 상세 하드코딩 금지 — AGENTS.md와 ssot/가 단일 출처.

## 핵심 포인터

| 항목 | 위치 |
|------|------|
| 에이전트 헌법 | `AGENTS.md` |
| 공유 약속 L01~L17 | `ssot/약속.json` |
| 재발방지 | `ssot/incidents.json` |
| 공식값 | `ssot/canon.json` |
| KPI | `ssot/kpi.json` |
| 작업 큐 | `state/_queue.json` |
| 스웜 루프 | `loop/swarm-loop.md` |
| 품질 게이트 | `loop/quality-gates.md` |

## 부팅 순서

1. `ssot/약속.json` 직독 (L01~L17)
2. `ssot/incidents.json` 직독
3. `ssot/canon.json` 직독
4. `AGENTS.md` 전체 흡수
5. `agents/본인.md` 흡수
6. `state/_queue.json` 본인 배 확인

## 에이전트 목록

`agents/` 폴더:
- `웰리.md` — AI CEO·오케스트레이터 (Opus)
- `시모.md` — AI CMO·마케팅 (Sonnet)
- `시우.md` — AI COO·운영 (Sonnet)
- `시토.md` — AI CTO·시설·기술 (Sonnet)
- `시포.md` — AI CPO·회원·CS (Sonnet, TODO)
- `시뽀.md` — AI CFO·재무 (Sonnet, TODO)
- `시로.md` — AI CHRO·인사 (Sonnet, TODO)
- `_role-template.md` — 새 역할 추가용 빈 8차원 골격

## 스킬 목록

`skills/index.md` 참조.
