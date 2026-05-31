# 웰페리온 자동화 (welperion-automation)
메인 SSOT. 모든 sub-project·자동화·콘텐츠·자산은 본 폴더 하위 통합. 자산 위치 상세 → `INDEX.md`.

## 0. 회사 정보
| 항목 | 값 |
|---|---|
| 상호 | 주식회사 웰페리온 (Wellperion) |
| 주소 | 서울특별시 용산구 서빙고로 413, 101동 지1층 101호외 2 (한남동) |
| 포지셔닝 | 하이엔드 프라이빗 스포츠클럽 멤버십 커뮤니티 |
| 브랜드 용어 | "피트니스" 금지 → "스포츠클럽" / "현대하이페리온" 금지 → "웰페리온" |
| 미션 | 지속되지 않는 건강 문제를 해결한다 |
| 공식 링크 | https://litt.ly/wellperion |
| 업무보고 봇 | @namuki_report_bot (Chat ID 8254867551) |


## 1. AI C-Level 7 에이전트
`wellperion-agents/.claude/agents/` 정의. 보고 라인: 6 C-레벨 → AI CEO → GM님.
| 직책 | 파일 | 라우팅 키워드 |
|---|---|---|
| AI CEO | ai-ceo.md | 전사 전략·통합 판단 |
| AI CFO | ai-cfo.md | 재무 |
| AI CHRO | ai-chro.md | 인사 |
| AI CMO | ai-cmo.md | 마케팅 |
| AI COO | ai-coo.md | 운영 |
| AI CPO | ai-cpo.md | 회원·CS |
| AI CTO | ai-cto.md | 시설·기술 |


## 2. R/R SSOT — 가이드허브
- AI C-Level 운영 가이드: `3. 웰페리온 가이드/wellperion_guide(main).html` → `id="g10"` 영역
- 공통 탭 (전 C-Level 필수): `data-panel="common"` — 절대 원칙 3대·업무 처리 3단계·보고 표 형식 의무
- 본인 탭: `data-panel="{role}"` — 페르소나·핵심역할·담당 KPI·실무진·핵심업무·협업 리듬
- 규칙: 작업 전 반드시 가이드허브 fetch. R/R 하드코딩 금지. Notion AI 조직 DB는 폐기 진행 중 — 호출 금지.
- 본인 위임 task: `status/{role}.json` + `status/_queue.json` read


## 3. 보고·승인
- 일일 08:00 통합 보고: `wellperion-agents/scripts/ceo_morning_pipeline.py` (예약작업 Wellperion-CEO-Morning-Brief-0800-Live, 08:00). 구 ceo_morning_brief_08.py는 폐기·미존재
- 텔레그램 (범위: C-Level 보고 + GM 승인 회신 전용): `telegram_bot/bot.py` + `daily_scheduler.py` (PID 가동)
- GM 자유텍스트 지시 채널: CLI(현 세션) · 모바일 Claude Code (remote)
- 봇 토큰 SSOT: `telegram_bot/.env`
- ※ CEO 인박스 DB(INB)는 2026-05-29 폐기 (텔레그램 보고+승인 전용화)
- 모든 C-Level(+CEO)은 작업 완료·대기 시마다 표준 사이클 보고 출력: ①기록 위치 ②Before&After(완료만) ③진행현황(완료/진행중 위임/대기 큐/미시작) ④남은 할일(상태·ID·담당AI·최종책임자(사람)·일). 포맷 정본 → 가이드허브 g10 공통 탭.


## 4. 운영 제약
### 거버넌스
1. 모든 출력 한국어. 영어 최소화, 약어 한글 병기
2. 금지항목 외 자율 진행 (💰결제·🔒보안·🚫금지·전략·공식값만 GM 결재)

### 토큰·실행 효율 (5대 원칙)
1. 이미 읽은 파일 재확인 금지
2. 불필요한 도구 호출 금지
3. 의존성 없는 도구 호출 병렬 실행
4. 20줄+ 불필요 출력은 서브에이전트(Haiku) 위임
5. 사용자가 설명한 내용 반복 금지

### 토큰 라우팅 매트릭스 (2026-05-29 GM 옵션 B 결재)
| 모델 | 담당 |
|---|---|
| Haiku 4.5 | 단순 read·lookup · 1줄 보고 · 텔레그램 송부 |
| Sonnet 4.6 | 자동화 가동 · 집계 · patch · git · 콘텐츠 가공 · 일일 보고 빌드 · 로그 정리 |
| Opus 4.7 | 판단 · 결정 · 진행 · 검토 · 결재 · 정책 정립 · 이슈 진단 · R&D 방향 · Peer Cross-Check |
- 메인 CEO·6 C-Level 에이전트 = Opus 4.7 유지(판단·결재 본업).
- 반복 작업(가동·patch·집계·git·송부)은 무조건 Sonnet/Haiku 서브에이전트(`executor` 등) 위임 강화.
- 메인 모델로 반복 작업 처리 시 토큰 사고 — 위임 누락 자체가 위반.

상세 교육자료·고도화 프롬프트 → 가이드허브 참조 (6번)

## 5. post-action 훅
위치: `wellperion-agents/scripts/clevel_post_action.py`
용도: .bat 종료 직전 업무자동화DB patch + 텔레그램 1줄 보고.
인자: `--clevel --task-id --status --summary [--version] [--changelog] [--dry-run]`


## 6. 가이드허브 — GM·AI CEO 통합 SSOT
위치: `3. 웰페리온 가이드/wellperion_guide(main).html`
배포: https://wellperion-cao.github.io/wellperion-automation/
GM 업무·AI C-Level 협업 매뉴얼·교육자료·고도화 프롬프트의 단일 마스터 문서.
세부 지식은 본 CLAUDE.md에 복사하지 않고, 필요 시 허브를 펼쳐 참조한다 (허브 = 원본, CLAUDE.md = 인덱스).
