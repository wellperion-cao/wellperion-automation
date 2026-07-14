# C레벨 자율 실행 루프 + 모듈 등록부 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시토(CTO) 도메인에서 [모듈 등록부 → 프론트 카드 → 웰리 오케스트레이션 자율 실행(가역) → 검증 → 환류] 한 바퀴를 실제로 관통시켜, "AI 없어도 도는" 운영층 자립의 첫 발판을 세운다.

**Architecture:** 단일 모듈 등록부(`status/module_registry.json`)를 SSOT로 두고, 화면·알림 규격·자율 루프가 모두 이 한 곳을 읽는다(헌법 원리1). 웰리 오케스트레이션은 부트스트랩 — 초기엔 웰리 세션이 큐 선별·검증하되, 반복 검증을 코드(`scripts/`)로 굳혀 점차 AI 개입을 줄인다. 계약(등록부 스키마·오케스트레이션 프로토콜)은 Fable이 직접 작성, 이행(HTML 렌더·구현)은 Sonnet executor 위임.

**Tech Stack:** Python 3.14(로더·선별기·검증, pytest), JSON(등록부 SSOT), HTML/JS(2창 렌더·기존 GAS+raw GitHub 폴백 패턴), 기존 `_queue.json`·`clevel_post_action.py`·`gm_aide_scan.py` 자산 재사용.

## Global Constraints
- 헌법 원리1: 등록부 단일 SSOT. 데이터 출처(`bootsetup_matrix.json`·`_queue.json`·`kpi.json`·GAS)는 **가리킬 뿐 복사 금지**.
- 가역만 자율 완료. 비가역(발행·배포·삭제·외부전송·결제·보안·전략·공식값)은 GM 결재.
- 웰리 직접 도메인 실행 금지 — 큐 읽기·위임·검증·기록만. 실행은 담당 C레벨(시토).
- 프론트 이번 범위 = `헌법한장.html` + `자율현황.html` 2창만. 등록부를 **읽어 렌더**(하드코딩 금지).
- 라이브 발효 = GM go + 즉시 역롤백 게이트. 로컬 구현·계획은 가역(GM 확인 불요).
- 파일명 영문·경로 한글/공백 주의(`3. 웰페리온 가이드/`). 커밋 직후 origin push(INC-006 가드).
- 성공 기준: GM 개입 0 · 거짓 완료 0(웰리 검증이 시크릿 크롬 라이브와 일치).

---

## 계약 태스크 (Fable 직접 — 지능·오래 감)

### Task 1: 모듈 등록부 스키마 + 로더

**Files:**
- Create: `status/module_registry.json`
- Create: `scripts/module_registry.py`
- Test: `tests/test_module_registry.py`

**Interfaces:**
- Produces: `load_registry(path=None) -> dict`, `validate_module(mod: dict) -> list[str]`(위반 사유 목록·빈 리스트=통과), `MODULE_FIELDS`(필수 필드 튜플), `get_modules_by_role(role: str) -> list[dict]`.

**등록부 모듈 카드 스키마 (필수 필드):**
```json
{
  "id": "cto-automation-health",
  "owner_role": "cto",
  "owner_nick": "시토",
  "feature": "자동화 건강 점수판 — 예약작업 실행결과 30분 갱신",
  "data_source": {"kind": "gas|json|sheet", "ref": "erp_status.json"},
  "notify_spec": {"daily": false, "weekly": true, "monthly": false, "channel": "telegram", "bot_id": null},
  "front_card": {"window": "자율현황", "anchor": "layer-automation"},
  "autonomy": "auto|semi|mech|propose|manual",
  "ai_free_fallback": "예약작업이 사람 세션 없이 상시 가동",
  "feedback": {"enabled": true, "audience": "gm+clevel", "entries": []},
  "reversible": true
}
```

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_module_registry.py`: 빈 필드 모듈에 `validate_module`이 위반 사유 반환, 완전 모듈은 빈 리스트. `load_registry`가 `modules` 배열 반환. `autonomy`가 허용값 밖이면 위반.
- [ ] **Step 2: 테스트 실패 확인** — `python -m pytest tests/test_module_registry.py -v` → FAIL(모듈 없음).
- [ ] **Step 3: 최소 구현** — `module_registry.py`에 `MODULE_FIELDS`, `AUTONOMY_LEVELS`, `load_registry`(UTF-8·`modules` 키), `validate_module`(필수 필드·autonomy·reversible 타입 체크), `get_modules_by_role`.
- [ ] **Step 4: 등록부 초기화** — `status/module_registry.json`에 `{"_doc": "모듈 단일 등록부(SSOT). 화면·알림·자율이 이 한 곳을 읽는다.", "modules": []}`.
- [ ] **Step 5: 테스트 통과 확인** — `python -m pytest tests/test_module_registry.py -v` → PASS.
- [ ] **Step 6: 커밋** — `feat(registry): 모듈 등록부 스키마+로더 (자율화 계약 SSOT)`.

### Task 2: 시토 도메인 모듈 등록

**Files:**
- Modify: `status/module_registry.json`
- Test: `tests/test_module_registry.py`(등록 검증 케이스 추가)

**Interfaces:**
- Consumes: Task 1 `validate_module`, `MODULE_FIELDS`.

- [ ] **Step 1: 실패 테스트** — 등록부의 모든 모듈이 `validate_module` 통과(위반 0)함을 도는 테스트. 최소 3개 시토 모듈 존재 assert.
- [ ] **Step 2: 실패 확인** — 모듈 0개라 FAIL.
- [ ] **Step 3: 시토 모듈 3~5개 선언** — 실측 기반: `cto-automation-health`(자동화 건강 점수판·auto), `cto-aide-gap-detector`(자율 틈 감지기·auto·reversible), `cto-check-gas`(점검 GAS 파이프·mech), 각 `data_source`·`front_card`·`ai_free_fallback` 실값. 자율수준·가역성은 실제 상태 정직 반영.
- [ ] **Step 4: 통과 확인** — pytest PASS.
- [ ] **Step 5: 커밋** — `feat(registry): 시토 도메인 모듈 3~5개 등록(정직 상태)`.

### Task 3: 웰리 오케스트레이션 프로토콜 + 시토 자율 실행 모드

**Files:**
- Modify: `wellperion-agents/.claude/agents/ai-ceo.md`
- Modify: `wellperion-agents/.claude/agents/ai-cto.md`

**Interfaces:** (프롬프트 계약 — 코드 아님)

- [ ] **Step 1: ai-ceo.md에 오케스트레이션 프로토콜 섹션 추가** — "§7 자율 실행 오케스트레이션(부트스트랩)": ① 큐에서 가역·담당 C레벨 배 선별(`scripts/welly_orchestrate.py` 선별기) ② 담당 C레벨에 위임(Agent) ③ 시크릿 크롬 라이브 실측 검증(거짓 완료 0) ④ G1 기록·커밋 ⑤ **"이 검증을 코드·게이트로 굳힐 수 있나?" 매 사이클 자문(부트스트랩 이관)**. 비가역·판단 필요는 제안·GM 결재. 웰리 직접 도메인 실행 금지 재확인.
- [ ] **Step 2: ai-cto.md에 자율 실행 모드 섹션 추가** — "자율 실행 모드": 웰리 위임 수신 시 본인 등록부 모듈 범위 내 가역 작업을 실행하고 아티팩트·라이브 링크를 반환(완료 게이트=증거 필수). 비가역은 준비·제안만.
- [ ] **Step 3: 정합 확인** — 두 파일이 헌법 두뇌-손 분리·가역 게이트와 모순 없는지 grep 검토(하드코딩 원칙 복사 금지, S2 포인터 유지).
- [ ] **Step 4: 커밋** — `feat(agents): 웰리 오케스트레이션 프로토콜+시토 자율 실행 모드(부트스트랩)`.

### Task 4: 자율 대상 선별기 + 검증 규칙 1개 코드화 (부트스트랩 이관 시작)

**Files:**
- Create: `scripts/welly_orchestrate.py`
- Test: `tests/test_welly_orchestrate.py`

**Interfaces:**
- Consumes: Task 1 `load_registry`, `get_modules_by_role`; `status/_queue.json`.
- Produces: `select_autonomous_ships(clevel: str, queue: list) -> list[dict]`(가역·해당 clevel·PENDING/IN_PROGRESS·등록부 모듈 범위), `verify_reversible_meta(ship: dict) -> dict`(코드화한 검증 규칙 1개 — 예: 커밋 존재·아티팩트 필드 비어있지 않음 확인, `{passed: bool, evidence: str}`).

- [ ] **Step 1: 실패 테스트** — 가역·시토·활성 배만 선별됨(비가역·타 clevel·DONE 제외). `verify_reversible_meta`가 아티팩트 없는 완료를 `passed=False`로 판정(거짓 완료 차단).
- [ ] **Step 2: 실패 확인** — FAIL.
- [ ] **Step 3: 구현** — 선별기(등록부 교차 필터)+검증 규칙 1개. 라이브 부작용 0(순수 read·판정).
- [ ] **Step 4: 통과 확인** — pytest PASS.
- [ ] **Step 5: 커밋** — `feat(orchestrate): 자율 대상 선별기+검증규칙1 코드화(부트스트랩 이관)`.

---

## 이행 태스크 (Sonnet executor 위임 — 양산)

### Task 5: 자율현황.html 등록부 모듈 카드 렌더

**Files:**
- Modify: `3. 웰페리온 가이드/자율현황.html`

- [ ] **Step 1** — 등록부(`status/module_registry.json`)를 GAS read_file→raw GitHub 폴백 패턴으로 로드(기존 창의 로더 재사용).
- [ ] **Step 2** — `#layer-automation` 영역에 모듈 카드 렌더: 특징기능·자율수준 배지(정직)·AI없이도-fallback·환류 접점. 기존 하드코딩 카드와 중복 제거(등록부가 SSOT).
- [ ] **Step 3: 라이브 검증** — 시크릿 크롬으로 배포본 실측: 등록부 모듈이 카드로 표시·콘솔 에러 0·스크린샷. (라이브 발효는 GM go)
- [ ] **Step 4: 커밋** — `feat(자율현황): 등록부 모듈 카드 렌더(하드코딩→SSOT)`.

### Task 6: 헌법한장.html 등록부 렌더 연결

**Files:**
- Modify: `3. 웰페리온 가이드/헌법한장.html` (Fable 시안 v2를 실 페이지 기준으로 반영)

- [ ] **Step 1** — Fable 시안(북극성·불변원리·환류 루프·8주체 모듈 매트릭스)을 실 페이지 구조로 이식.
- [ ] **Step 2** — 8주체 모듈 매트릭스가 등록부를 읽어 자율수준·fallback을 렌더(정적 예시→SSOT 직독).
- [ ] **Step 3: 라이브 검증** — 시크릿 크롬 실측·A3 인쇄 가독·스크린샷.
- [ ] **Step 4: 커밋** — `feat(헌법한장): 시안 반영+등록부 렌더`.

### Task 7: 환류 칸 수집 경로

**Files:**
- Modify: `3. 웰페리온 가이드/자율현황.html`(모듈 카드 피드백 접점)
- Modify: `scripts/module_registry.py`(피드백 append 헬퍼)

**Interfaces:**
- Produces: `append_feedback(module_id: str, text: str, author: str) -> None`(등록부 `feedback.entries`에 멱등 append).

- [ ] **Step 1: 실패 테스트** — `append_feedback`가 해당 모듈 `feedback.entries`에 항목 추가·중복 방지.
- [ ] **Step 2: 실패 확인 → 구현 → 통과** (`tests/test_module_registry.py`).
- [ ] **Step 3** — 프론트 카드에 "이거 맞아요?" 접점(주체=등록부 audience). 수집→등록부 경로 연결(발효는 GM go).
- [ ] **Step 4: 커밋** — `feat(registry): 환류 칸 수집 경로(다음 루프 입력)`.

### Task 8: 파일럿 1바퀴 실행 + 검증 (측정된 성공 확정)

**Files:** (실행·검증 — 산출물은 `_queue.json` 기록·커밋)

- [ ] **Step 1** — 웰리 오케스트레이션 프로토콜로 시토 가역 배 실 N건 선별(`select_autonomous_ships`).
- [ ] **Step 2** — 각 배를 시토(executor)에 위임 실행(웰리 직접 실행 0).
- [ ] **Step 3** — 시크릿 크롬 라이브 실측 검증 + `verify_reversible_meta`(거짓 완료 0 확인).
- [ ] **Step 4** — G1 기록·커밋(`clevel_post_action.py` 완료 훅). GM 개입 0 확인.
- [ ] **Step 5** — 파일럿 결과 요약: 처리 건수·거짓 완료 0·코드화 이관 1건·환류 1건. GM 보고(L18 표).

---

## Self-Review
- **Spec coverage:** 자율루프(T3·T4·T8)·모듈등록부(T1·T2·T7)·프론트2창(T5·T6)·환류(T7)·부트스트랩 이관(T4·T8 Step3)·측정된 성공(T8) — 전 active 컴포넌트 커버. defer 3종은 등록부 필드(`notify_spec`·`data_source`)로 규격만(구현 없음) — 의도된 non-goal.
- **Placeholder scan:** 각 태스크에 파일·인터페이스·검증 명시. HTML 렌더 태스크는 라이브 검증 기준으로 대체(순수 TDD 부적합 도메인).
- **Type consistency:** `load_registry`/`validate_module`/`get_modules_by_role`(T1) → `select_autonomous_ships`(T4) → `append_feedback`(T7) 시그니처 일관. `autonomy` 허용값 T1 정의·T2 사용 일치.
