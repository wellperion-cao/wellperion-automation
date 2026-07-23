# 시토 v1 설계서 — 일일 북극성 추천기 엔진
> 작성: 2026-06-29 · 상태: **G1/G2/G3 GM 잠금 확정 · 1단계(두뇌 드라이런 엔진) 빌드 완료** · 스펙 원본: `.omc/specs/deep-interview-daily-northstar-recommender.md`
>
> **GM 잠금 결정(2026-06-29):** G1=`status/northstar_pending.json`(git 추적) · G2=미승인은 다음날 06:30 새 추천 시 자동 보류(만료)·당일 자정 아님 · G3=**파일럿 폐기→처음부터 전 C-Level(7역할)**, 웰리가 전사 top3 선정·역할 태그.
>
> **G3 범위 수정(2026-07-03 GM):** cfo·chro 는 나우열M 실무 담당 도메인이라 AI 항로 배 대상이 아님 → top3 후보 선정 대상에서 **제외**. 대상 = **ceo·cmo·coo·cto·cpo(5역할)**. 반영 = `scripts/northstar_recommender.py` `TARGET_ROLES`.

---

## 한눈 요약

| 항목 | 내용 |
|---|---|
| 목적 | 매일 06:30, 북극성 대비 현재 갭을 읽어 "오늘의 다음 한 수" 3후보를 텔레그램으로 제안 |
| 두뇌 | 웰리(AI CEO) — 후보 선정·경로지도·우선순위 판단 |
| 손 | 시토(AI CTO) — 스케줄러·입력 수집·카드 발송·승인 콜백·큐 등록 |
| 대상 | **처음부터 전 C-Level(7역할 ceo·cmo·coo·cto·cpo·cfo·chro, gm 제외)** — 웰리가 전사 top3 선정·역할 태그 (G3 확정) |
| 1관문 | ✅ **1단계 빌드 완료** — `scripts/northstar_recommender.py` 드라이런 엔진. GM 1단계 확인 후 2단계(스케줄러·텔레그램·콜백) |
| 자율 범위 | 제안까지만. 실행은 GM 승인 후 기존 파이프라인 |

---

## 1. 아키텍처 개요

```
[Task Scheduler 06:30]
        │
        ▼
scripts/northstar_recommender.py   ← 시토 엔진 진입점
        │
        ├─ [입력 수집] ─────────────────────────────────────┐
        │   coo/bootsetup_matrix.json  (웰리 row: 북극성·KPI·소유·ideas)
        │   status/_queue.json         (active 배·완료건 next)
        │   status/kpi_values.json     (목표 대비 현재치)
        │                                                    │
        ├─ [두뇌 호출] ─────────────────────────────────────┘
        │   claude CLI (model_router 폴백·project_ai_self_learning_pipeline과 동일 결)
        │   프롬프트: 웰리 추천 로직 규칙 v1 + 입력 데이터 주입
        │   → 후보 3개 JSON 반환 (제목·경로지도·근거·난이도 배)
        │
        ├─ [텔레그램 카드 발송]
        │   telegram_bot/bot.py 공유 토큰 + GM Chat ID 사용
        │   포맷: 06:30 북극성 추천 카드 (§3 참고)
        │
        └─ [승인 대기 → 콜백 처리]
            telegram_bot/bot.py handle_message 확장
            [승인1/2/3] → _queue.json PENDING 배 등록
            [보류] → 무동작 로그만
```

### 스크립트 위치

| 파일 | 역할 |
|---|---|
| `scripts/northstar_recommender.py` | 메인 엔진 (신규 생성) |
| `telegram_bot/bot.py` | 승인 콜백 핸들러 확장 (기존 파일 수정) |
| `launchers/northstar_recommender.vbs` | 숨김 런처 (신규 생성) |

---

## 2. 웰리 추천 로직 규칙 v1 (두뇌 — 변경 금지·설계 전제)

| 규칙 | 내용 |
|---|---|
| **입력** | `bootsetup_matrix.json` 웰리 row (dims[0]=북극성, dims[3]=KPI, owns, ideas) + `_queue.json` (active 배·완료건 next) + `kpi_values.json` |
| **후보 3개** | 신호 3종 중 각기 다른 하나 기반으로 생성 |
| **신호①** | 북극성 갭 — 북극성 서술 대비 비어있는 다음 한 걸음 (소유/ideas 참고) |
| **신호②** | KPI 미달 — kpi_values 목표 밑 지표를 올릴 한 수 |
| **신호③** | 다음 한 걸음 — _queue 완료건 next 중 미착수 |
| **우선순위 가중** | 북극성 직접기여 > KPI 미달 시급 > 브릿지 연속성 |
| **중복방지** | 이미 _queue active인 배는 후보 제외 |
| **다양성** | 3개는 가능하면 서로 다른 신호/영역 |
| **후보 출력 필드** | 제목 · 경로지도(북극성→…→지금→오늘 한 수) · 근거(어느 신호·어느 갭/지표) · 난이도 배(⛵/⛴️/🛳️) |

---

## 3. 텔레그램 카드 포맷

```
🧭 [06:30] 웰리 — 오늘의 북극성 한 수

┌ 후보 ① ⛴️여객선
│ 제목: (한 줄)
│ 경로: 북극성 → [브릿지 단계] → 지금 → 오늘 한 수
│ 근거: 신호③ — "배 X next 미착수"
└

┌ 후보 ② 🛳️크루즈
│ 제목: (한 줄)
│ 경로: …
│ 근거: 신호① — "북극성 ○○ 갭"
└

┌ 후보 ③ ⛵돛단배
│ 제목: (한 줄)
│ 경로: …
│ 근거: 신호② — "KPI ○○ 현재 X / 목표 Y"
└

👉 [승인1] [승인2] [승인3] [보류]
```

- 텍스트 버튼(일반 메시지 회신 방식) — 기존 봇 handle_message 패턴 재사용
- 카드 발송 후 `northstar_pending.json` (scratchpad 위치)에 3후보 임시 보관
- 승인/보류 응답 시 해당 파일 조회 후 처리

---

## 4. 승인 콜백 — telegram_bot/bot.py 확장 지점

```python
# handle_message 확장 (기존 패턴 동일)
if text in ("[승인1]", "[승인2]", "[승인3]"):
    idx = int(text[-1]) - 1
    # northstar_pending.json에서 후보 idx 읽기
    # _queue.json 배열 끝에 PENDING 배 append
    # ship_no = 현재 최대 + 1
    # clevel = "ceo" (웰리 파일럿)
    # 등록 완료 텔레그램 확인 메시지 발송
elif text == "[보류]":
    # 로그만 기록, 다음 사이클 재추천
```

- **기존 봇 핸들러 구조 보존** — if/elif 체인 끝에 추가
- `northstar_pending.json`: `status/` 디렉터리 내 (git 추적, 커밋 대상 아님 → .gitignore 추가 검토)

---

## 5. 06:30 트리거 — Windows Task Scheduler

| 항목 | 값 |
|---|---|
| 작업 이름 | `Wellperion-NorthStar-0630` |
| 트리거 | 매일 06:30 |
| 실행 | `launchers/northstar_recommender.vbs` (숨김 창) |
| VBS 내용 | `pythonw scripts/northstar_recommender.py` (백그라운드) |
| schedule.json 등록 | `{"name": "northstar_recommender", "time": "06:30", "script": "scripts/northstar_recommender.py"}` |

- 기존 `.bat` 방식 대신 `.vbs` 숨김 런처 — `reference_scheduled_task_hidden_window` 정책 준수
- `PYTHONIOENCODING=utf-8` 환경변수 필수 (한글 출력 — `reference_python_console_utf8_env`)

---

## 6. 폐루프 — 완료 배 효과 → 다음 사이클 환류

```
완료된 배 (post_action --status DONE)
        │
        ▼
scripts/northstar_recommender.py
  입력 수집 시 _queue.json 완료건 next 재읽기
  → 다음 사이클 신호③ 갱신
        │
        ▼
kpi_values.json 변화 추적
  (KPI 직접 연결 배: 완료 후 kpi_values 변화를 다음 추천 신호②로)
```

**측정 정직성 원칙** (`project_dashboard_conversion_data_honest_limits` 준수):
- 측정 가능한 것만: _queue 완료 건수·next 연결 여부·KPI 수치 변화
- 추정은 '추정' 라벨 명시
- v1은 정성 추적 허용 (GM이 텔레그램에 "효과 있었음" 회신 → 로그 기록)

---

## 7. 성공기준 4가지 — 관찰·기록 방법

| 기준 | 관찰 방법 | 기록 위치 |
|---|---|---|
| **3초 파악 + 1탭 승인** | GM이 카드 수신 후 승인 응답까지 시간 (텔레그램 타임스탬프 차이) | northstar_log.jsonl |
| **북극성 실제 기여** | 승인→완료된 배의 next가 KPI·파이프라인 진척으로 이어졌는지 (정성+kpi_values 변화) | northstar_log.jsonl |
| **추천 적중률** | 보류 없이 승인된 비율 (승인 수 / 전체 제안 수) | northstar_log.jsonl |
| **과정 투명·신뢰** | 카드에 경로지도+근거가 항상 있는지 (엔진 자체 보장, 누락 시 에러) | 엔진 로그 |

로그 형식: `status/northstar_log.jsonl` — 1행 1사이클 (날짜·후보3개·승인인덱스·보류여부·응답시간)

---

## 8. 단계별 구현 순서

| 단계 | 내용 | 리스크 | GM 결정 필요 |
|---|---|---|---|
| **①** | 입력 수집 모듈 — matrix·queue·kpi 파싱 | 낮음 | 없음 |
| **②** | 웰리 두뇌 호출 — claude CLI 프롬프트 설계·테스트 | 중간 (프롬프트 튜닝 필요) | 없음 (dry-run으로 GM 확인 후 진행) |
| **③** | 텔레그램 카드 발송 — 포맷·06:30 트리거 | 낮음 | 없음 |
| **④** | 승인 콜백 → _queue 등록 | 중간 (봇 핸들러 충돌 주의) | 없음 |
| **⑤** | 폐루프 — 완료 효과 환류 + 로그 | 낮음 | 없음 |
| **⑥** | v1 실증 2주 → 6 C-Level 확장 | 높음 (각 C-Level 북극성 데이터 정합 필요) | **GM 확장 승인 필요** |

**리스크 1**: 웰리 두뇌 호출 비용 — claude CLI 1회 호출 = 토큰 비용. 06:30 1회/일이라 낮음.  
**리스크 2**: `northstar_pending.json` 덮어쓰기 — 승인 전 다음 날 06:30 실행 시 전날 pending 덮어쓰임. v1은 당일 승인 가정, 미승인 건은 보류로 간주.  
**리스크 3**: 봇 미가동 시 카드 미발송 — 기존 봇 재기동 정책(`reference_bot_elevated_restart`) 그대로 적용.

---

## 9. GM 결정 지점 — ✅ 전부 확정 (2026-06-29)

| 번호 | 질문 | **GM 잠금 결정** |
|---|---|---|
| **G1** | `northstar_pending.json` 위치 | ✅ **`status/northstar_pending.json` (git 추적)** |
| **G2** | 미승인 건 처리 | ✅ **다음날 06:30 새 추천 생성 시 자동 보류(만료)** — 당일 자정 만료 아님 |
| **G3** | 추천 대상 시작 | ✅ **처음부터 전 C-Level(7역할)** — 파일럿 폐기. 입력=matrix 7 C-Level행 전부, 웰리가 전사 top3 선정·각 후보에 역할·북극성 태그 |
| **G3 수정(2026-07-03)** | 추천 대상 범위 | ✅ **cfo·chro 제외** — 나우열M 실무 담당 도메인, AI 항로 배 대상 아님. 대상 = ceo·cmo·coo·cto·cpo(5역할) |

---

## 10. 1단계 빌드 결과 (2026-06-29)

- **신규:** `scripts/northstar_recommender.py` — 드라이런 추천 엔진(라이브 부작용 0).
  - 입력 수집: `bootsetup_matrix.json`(7 C-Level행 북극성=dims[0]·KPI=dims[3]·owns·ideas) + `status/_queue.json`(active 배·완료건 next) + `status/kpi_values.json`.
  - 두뇌: claude CLI(`model_router` 폴백 경유, self_learning 패턴 재사용) — 웰리 추천 로직(신호3·우선순위·다양성·중복방지·전사 top3). 실패 시 규칙기반 폴백.
  - 출력: 콘솔 + `status/northstar_pending.json`(date·candidates[3]{role,title,path_map,rationale,difficulty,signal}·status=proposed). **텔레그램 전송·스케줄러 등록 없음.**
  - `--dry-run` 기본.
- **2단계(GM 1단계 확인 후):** 06:30 Task Scheduler(§5) · 텔레그램 카드(§3) · 봇 승인콜백→_queue 등록(§4) · 폐루프(§6).

---

*설계서 끝 — 1단계 완료. GM 1단계 확인 시 시토가 ③→⑥ 순서로 2단계 빌드 착수.*
