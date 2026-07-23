# 설계: 스킬·플러그인 숙련 학습 — 시토 자기학습 파이프라인 통합

- 날짜: 2026-07-02
- 상태: 설계 승인(GM) → 구현계획 대기
- 두뇌=웰리(CEO) / 엔진=시토(CTO)
- brainstorming(superpowers) 산출물

## Goal
시토의 기존 **주간 자기학습 파이프라인**(`ai_learning_proposer.py`, 매주 일요일)에 **'설치된 스킬·플러그인'을 학습 대상으로 통합**한다. 매주 설치 스킬(OMC + superpowers + 기타)을 훑어, 우리 최근 작업·GM 성향에 맞는 **활용법을 발굴·제안**하고, 승인 시 **치트시트에 박제**한다. 도구가 진화해도 안 녹슬게 매주 복리로 흡수.

## 통합 원칙 (핵심)
이것은 **별도 시스템이 아니라 시토 자기학습의 학습 대상 확장**이다. 하나의 주간 자기학습이 이제 두 입력을 먹는다: ① 외부 AI 기술·사례(기존) ② 설치 스킬·플러그인 인벤토리(신규). 제안→승인→반영→효과 환류 루프·일요일 슬롯·두뇌(model_router)·텔레그램은 **전부 그대로 재사용**.

## Non-Goals (v1 제외)
- 반복 작업의 커스텀 스킬 자동생성(skillify) — 제외
- 훅/자동호출로 행동 자동변경 — 제외 (깊이=발굴+추천, GM 결정)
- 승인 없는 자동 반영 — 제외 (모든 카드 status='제안' 불변)

## Design (A안 — 통합)

### 데이터 흐름
```
[매주 일요일 · 기존 예약작업 Wellperion-AI-Learning-Proposer-Weekly]
 ① (신규) skill_inventory 수집
    ~/.claude/plugins/cache/**/skills/*/SKILL.md 훑어 설치 스킬·플러그인 목록
    (name·description·source) + docs/skill_cheatsheet.md 대조로 '새것/미활용' 표시
 ② (기존 확장) ai_learning_proposer
    입력 = 외부사례 요약(기존) + 스킬 인벤토리(신규) + 최근 작업 맥락
           (status/gm_observation_ledger.jsonl · _queue 최근 제목)
    → LLM(model_router)이 '이 작업엔 이 스킬, 이렇게' 활용제안 카드 M개 생성
      (반영위치 = "스킬·플러그인 활용" 신규 영역)
 ③ (기존 그대로) 제안 → GM 승인 → 반영 → 효과 환류
```

### 컴포넌트 (경계 명확)
1. **skill_inventory 수집기** (신규 `scripts/skill_inventory.py`)
   - 하는 일: 디스크의 플러그인 캐시에서 설치 스킬·플러그인을 열거(디스크가 정본), 치트시트 대조로 '미활용' 표시, 인벤토리 JSON 출력.
   - 의존: 파일시스템 read만. 라이브 부작용 0.
2. **proposer 확장** (기존 `scripts/ai_learning_proposer.py`)
   - `IMPROVEMENT_AREAS`에 "스킬·플러그인 활용" 추가.
   - LLM 프롬프트에 스킬 인벤토리 + 최근 작업 맥락 주입, 활용제안 카드 생성.
   - 나머지(카드 조립·저장·승인·효과) 무변경 재사용.
3. **치트시트** (신규 `docs/skill_cheatsheet.md`)
   - 반영 대상. GM 승인 카드의 활용팁을 수동 박제(기존 '반영=수동' 원칙).

### 안전 (기존 원칙 불변)
- 모든 신규 카드 status='제안'. 반영(치트시트 기록)은 GM 승인 후 수동.
- 스크립트는 read + JSON/제안 쓰기만. 메모리·프롬프트·CLAUDE.md·행동 자동변경 0.
- 새 예약작업 0개 — 기존 일요일 슬롯 재사용.

## Acceptance Criteria
- [ ] `skill_inventory.py`가 설치 스킬(OMC+superpowers 등) 목록화 + '미활용' 표시.
- [ ] 일요일 proposer 실행 시 '스킬·플러그인 활용' 제안 카드가 (기존 5영역과 함께) 생성됨.
- [ ] 활용 카드도 기존 제안→승인→반영 흐름·G1/텔레그램에 정상 편입.
- [ ] 승인 카드의 활용팁이 `docs/skill_cheatsheet.md`에 박제되는 경로 확인.
- [ ] 새 예약작업 0 — 기존 `Wellperion-AI-Learning-Proposer-Weekly` 그대로.
- [ ] 효과 환류에 스킬 카드 포함('그 스킬 실제로 썼나·도움됐나' 다음 주 입력).

## 기존 자산 (브라운필드)
- `scripts/ai_learning_proposer.py` — 제안 생성+승인/반영/효과 machinery(재사용).
- `scripts/ai_education_auto_learner.py` — 외부사례 수집·요약(09:30).
- `scripts/learning_effect_meter.py` — 효과 측정.
- `scripts/model_router.py` — claude CLI 두뇌(재시도 하드닝 반영됨).
- `status/gm_observation_ledger.jsonl` — 최근 작업·GM 성향 맥락 소스.
