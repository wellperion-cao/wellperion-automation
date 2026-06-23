# 에이전트 스웜 마스터 템플릿

**어떤 프로젝트든 폴더째 복붙 → README/AGENTS만 수정 → 즉시 가동.**

## 이게 뭔가

재사용 가능한 에이전트 스웜 운영 뼈대.  
오케스트레이터 1 + 전문역할 에이전트 5 + 검증된 스킬 6종으로 구성.  
"문서 말고 코드/장치로 박제"하는 GM 스타일 철학 적용.

## 왜 만들었나

- 새 프로젝트마다 같은 구조를 반복 설계하는 낭비 제거
- 단일 진실(SSOT) + 경계 있는 루프 + 실증 검증을 기본값으로 탑재
- master.txt 18+18 비대 버전을 lean하게 압축

## 구조 한눈에

```
master-template/
  README.md          # 사람용 (이 파일)
  AGENTS.md          # 기계 계약 (에이전트가 읽는 헌법)
  CLAUDE.md          # 얇은 인덱스
  ssot/              # 단일 진실 3종
    약속.json        # 공유 규칙·교훈
    incidents.json   # 재발방지 사례
    canon.json       # 공식값 레지스트리
  agents/            # 역할별 에이전트 정의 5개
  skills/            # 재사용 스킬 6종
  state/             # 작업 큐 + 영구 메모리
  loop/              # 스웜 루프 + 품질 게이트
  scripts/           # 부트스트랩·실행·검증 스크립트
  docs/              # upstreams 참조
```

## 새 프로젝트 시작법

1. 이 폴더를 새 프로젝트 루트에 복사
2. `README.md` → 프로젝트 목적·컨텍스트 수정
3. `AGENTS.md` → 미션·공식값 플레이스홀더 교체
4. `ssot/canon.json` → 실제 프로젝트 공식값 채우기
5. `state/_queue.json` → 첫 번째 태스크 추가
6. `scripts/bootstrap.ps1` (Windows) 또는 `bootstrap.sh` (Linux/Mac) 실행
7. Claude Code에서 `AGENTS.md`를 시작점으로 오케스트레이터 호출

## 핵심 철학

| 원칙 | 구현 |
|------|------|
| 단일 진실 | `ssot/` 3종 JSON — 에이전트가 직독 |
| 코드로 박제 | 약속·재발방지를 문서가 아닌 JSON 기계 계약으로 |
| 실증 검증 | 완료 = 상태값 변경이 아닌 실제 결과 재현 |
| 경계 있는 루프 | 재시도 예산·최대 사이클·정지조건 명시 |
| 토큰 라우팅 | 판단=상위모델 / 루틴=하위모델 |

## 참조 upstreams

`docs/upstreams.md` 참조. 통째 vendoring 금지 — 참조만.
