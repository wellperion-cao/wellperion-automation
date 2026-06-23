---
title: memory-update
purpose: 세션 간 영구 기억을 저장·갱신한다
when_to_use: 중요한 사실·결정·교훈이 생겼을 때. retrospective 후 항상
when_not_to_use: 코드 구조·git 이력 등 repo에 이미 기록된 것 (중복 금지)
inputs:
  - 저장할 사실 또는 교훈
outputs:
  - state/memory/{slug}.md 파일
  - state/memory/MEMORY.md 인덱스 업데이트
---

## workflow

1. 저장 가치 판단:
   - 세션이 끝나도 다음에 알아야 하는가?
   - repo 어디에도 기록되지 않은 non-obvious 사실인가?
2. 기존 메모리 확인 — 중복 시 업데이트, 신규만 추가
3. 파일 작성 (`state/memory/{slug}.md`):
   ```
   ---
   name: {slug}
   description: {한 줄 요약}
   type: fact | decision | lesson | constraint
   ---
   {내용}
   **Why:** {왜 중요한가}
   **Apply:** {다음에 어떻게 적용하나}
   ```
4. `state/memory/MEMORY.md` 인덱스에 한 줄 추가

## do
- 한 파일 = 한 사실
- 오래된 메모리 틀렸으면 수정 (삭제 금지, 교체)
- 파일·함수명 등 코드 구조는 저장 금지 (git으로 추적)

## dont
- repo에 이미 있는 정보 중복 저장 금지
- 이번 세션에만 필요한 임시 정보 저장 금지
- MEMORY.md에 내용 직접 작성 금지 (인덱스만)
