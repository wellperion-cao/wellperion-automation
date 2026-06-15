# 컨텍스트 정비·교육자료 SSOT 설계 (제안)

> 작성: AI CTO(시토) · 2026-06-15 · GM 지적 3건 대응
> 성격: **설계 제안** — 승인 후 가이드 T2(SSOT)에 반영하고 본 제안 문서는 폐기(단일출처 유지).

## 0. GM 지적 (배경)
1. 정비 범위표에 **AI CEO(웰리)가 없다.**
2. 식별자 번호가 제각각(CMO-002·CPO-002·COO-001·CHRO-005·CFO-004·CTO-003) — **왜 다른가.**
3. 교육자료 정리·토큰 소비를 **어디에 SSOT하고, AI가 어떻게 읽고 개선할지** 설계 필요. (+ G1 가시화)

식별자 진단: 옛 노션 자동화 DB 이관 잔재(임의 번호). **T2 표시용 외 코드 미참조**(실측) → 정합 안전.

---

## 1. (A) 정비 범위 정합 — CEO 추가 + 식별자 규칙화
- **AI CEO(웰리) 행 추가** (7 C-Level 완성). 웰리 = 매 턴 최대 컨텍스트.
- **식별자 규칙 = `CTX-{역할}`** (자기설명형, 노션 임의번호 폐기):
  `CTX-CEO · CTX-CMO · CTX-COO · CTX-CTO · CTX-CFO · CTX-CHRO · CTX-CPO`

| 역할 | 식별자 | 정비 범위(요약) |
|---|---|---|
| **AI CEO(웰리)** | CTX-CEO | **MEMORY.md 인덱스·ai-ceo.md·CEO 부팅 주입 슬림화 + 전사 정비 취합** |
| AI CMO | CTX-CMO | 마케팅 SOP·콘텐츠 파이프라인·채널 성과·베이스라인 |
| AI CPO | CTX-CPO | 회원·CS SOP·상품 아카이브·문의 응대 |
| AI COO | CTX-COO | 운영 SOP·체크리스트·이슈 응답·리셉션 |
| AI CHRO | CTX-CHRO | 인사·파트너 SOP·계약·조직도·복지 |
| AI CFO | CTX-CFO | 재무·지출·수익 SOP·예산·세무 |
| AI CTO | CTX-CTO | 인프라·자동화·시설 SOP + 🗜️ 캐시·상시 컨텍스트 압축(전사) |

---

## 2. (B) 교육자료 정리 SSOT + AI 활용
**문제:** 지금은 파일을 보관함 폴더로 옮기기만 함 → AI가 "무슨 학습자료가 어디 있는지" 알 길이 없음(매번 폴더 스캔).

**설계:**
- **정책 SSOT = 가이드 T2** (현행 유지).
- **산출 SSOT(신규) = `status/education_index.json`** — 기계가독 매니페스트.
  ```json
  [{ "file":"claude_agents_guide.pdf", "archived":"2026-06-21",
     "month":"2026-06", "category":"교육", "keywords":["claude","agent"],
     "summary":"에이전트 설계 1줄 요약", "path":"Desktop/_정리완료/03_교육/2026-06/..." }]
  ```
- **생성:** `education_archive_weekly.py`가 파일 이동 시 인덱스에 append(멱등). 자가학습 `ai_education_auto_learner.py`의 요약을 `summary`에 합류.
- **AI 활용:** 에이전트가 학습자료 필요 시 **폴더 스캔 대신 index.json을 키워드로 조회** → 경로·요약 즉시 확보·인용. (교육=CHRO, 기술자료=CTO 등 역할별 활용)

---

## 3. (C) 토큰 소비 가시화 SSOT + 개선 루프
**무엇이 토큰을 먹나 (쉬운 말):** 매 턴 자동으로 읽히는 것들이 누적되면 무거워짐 —
- 메모리 인덱스(MEMORY.md) · CLAUDE.md · 에이전트 프롬프트(ai-*.md)
- 큰 가이드 HTML 부분조회 · `review_queue.json` · `status/_queue.json` · 각종 캐시/스냅샷

**설계:**
- **SSOT(신규) = `status/context_budget.json`** — 각 항목의 크기·추세·정비 액션.
  ```json
  { "measured":"2026-06-21", "items":[
    {"name":"MEMORY.md","lines":120,"approx_tokens":4800,"prev":118,"threshold":150,"action":"net-zero 유지"},
    {"name":"_queue.json","ships_active":10,"ships_terminal":41,"action":"terminal 14일+ 아카이브"} ]}
  ```
- **측정기(신규) = `scripts/context_budget_report.py`** — 알려진 무거운 파일을 스캔해 크기·추세 계산 → context_budget.json 기록 + 텔레그램 1줄 추세(멱등·읽기전용).
- **읽고 개선:** 일요일 정비 때 이 SSOT를 보고 **임계 초과 항목부터 슬림화**. 측정→감축 루프. **자동은 '후보 제시'까지, 실제 삭제는 사람 확인**(살아있는 데이터 보호).

---

## 4. (D) G1 가시화
- 본 설계 작업 = CTO 배로 G1 등록(가독 summary). 이후 P1~P3 진행 상태를 배 카드에 반영.

## 5. 적용 순서 (GM 승인 후)
- **P1** 가이드 T2 범위표: **CEO 행 추가 + 식별자 CTX-* 정합** (S2·T1 포인터도 정합). SSOT 단일 수정.
- **P2** `education_index.json` 스키마 + `education_archive_weekly.py`·learner 인덱싱 연결.
- **P3** `context_budget.json` + `context_budget_report.py` + 일요일 정비 연결(텔레그램 추세).
- 적용 완료 시 본 제안 문서 폐기(SSOT=T2 단일).
