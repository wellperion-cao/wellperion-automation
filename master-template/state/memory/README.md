# memory/ — 영구 메모리 규약

세션이 끝나도 다음 세션에서 알아야 하는 사실을 저장한다.

## 파일 형식

```markdown
---
name: {slug}
description: {한 줄 요약 — 관련성 판단용}
type: fact | decision | lesson | constraint
---

{내용}

**Why:** {왜 중요한가}
**Apply:** {다음에 어떻게 적용하나}
```

## MEMORY.md 인덱스

```
- [제목](파일명.md) — 훅(한 줄 요약)
```

## 규칙

- 한 파일 = 한 사실
- 중복 발견 시 기존 파일 업데이트 (신규 생성 금지)
- 틀린 메모리 → 교체 (삭제 금지)
- repo 코드 구조·git 이력·임시 정보 저장 금지
