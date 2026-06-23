# upstreams.md — 참조 레포지토리

> 통째 vendoring 금지. 참조(학습·설계 영감)만. 코드 직접 포함 시 라이선스 확인 필수.

| 레포 | URL | 용도 | 활용 방식 |
|------|-----|------|----------|
| agents.md | https://github.com/agentsmd/agents.md | AGENTS.md 계약 형식 표준 | 참조 — 계약 구조·우선순위 모델 |
| anthropics/skills | https://github.com/anthropics/skills | Claude 스킬 패턴 | 참조 — SKILL.md frontmatter 형식 |
| revfactory/harness | https://github.com/revfactory/harness | 오케스트레이션 하네스 | 참조 — 루프 구조·에이전트 라우팅 |
| bytedance/deer-flow | https://github.com/bytedance/deer-flow | 멀티에이전트 플로우 | 참조 — 분해·병렬 실행 패턴 |
| HKUDS/ClawTeam | https://github.com/HKUDS/ClawTeam | 팀 에이전트 협업 | 참조 — 역할 분리·핸드오프 패턴 |
| aiming-lab/AutoResearchClaw | https://github.com/aiming-lab/AutoResearchClaw | 자율 리서치 루프 | 참조 — researcher 에이전트 설계 |
| karpathy/autoresearch | https://github.com/karpathy/autoresearch | 자기개선 리서치 | 참조 — retrospective·self-improve 패턴 |
| dwzhu-pku/PaperBanana | https://github.com/dwzhu-pku/PaperBanana | 장문서 이해·검색 | 참조 — 문서 인덱싱·검색 워크플로 |
| supermemoryai/supermemory | https://github.com/supermemoryai/supermemory | 에이전트 메모리 | 참조 — memory/ 폴더 설계 |
| VoltAgent/awesome-claude-code-subagents | https://github.com/VoltAgent/awesome-claude-code-subagents | Claude 서브에이전트 카탈로그 | 참조 — 에이전트 역할 정의 |
| obra/superpowers | https://github.com/obra/superpowers | 에이전트 수퍼파워 패턴 | 참조 — 스킬 설계 |
| msitarzewski/agency-agents | https://github.com/msitarzewski/agency-agents | 에이전시 에이전트 | 참조 — 오케스트레이터 패턴 |
| VectifyAI/PageIndex | https://github.com/VectifyAI/PageIndex | 문서 인덱스·검색 | 참조 — researcher 장문서 처리 |

## 이 템플릿과의 관계

```
upstream 설계 영감
    ↓
GM 스타일 필터 (얇은 규칙·단일 진실·코드 박제)
    ↓
master-template lean scaffold
```

각 upstream의 좋은 아이디어를 흡수하되, 비대해지는 부분은 제거.  
직접 클론·포크가 필요하면 각 URL에서 직접 진행할 것.
