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
`notion-c-level-agents/.claude/agents/` 정의. 보고 라인: 6 C-레벨 → AI CEO → GM님.
| 직책 | 파일 | 라우팅 키워드 |
|---|---|---|
| AI CEO | ai-ceo.md | 전사 전략·통합 판단 |
| AI CFO | ai-cfo.md | 재무 |
| AI CHRO | ai-chro.md | 인사 |
| AI CMO | ai-cmo.md | 마케팅 |
| AI COO | ai-coo.md | 운영 |
| AI CPO | ai-cpo.md | 회원·CS |
| AI CTO | ai-cto.md | 시설·기술 |


## 2. Notion R/R 연동
- AI 조직 DB: `33f0407d-a948-805d-80b7-d792667cae33`
- Data Source ID: `33f0407d-a948-80d2-ad27-000b132ef146`
- 조회: `notion_wrapper.py` / `mcp__notion__API-query-data-source`
- 환경 변수: `telegram_bot/.env` NOTION_API_KEY (3 HardLink)
- 규칙: 작업 전 반드시 Fetch. 로컬과 충돌 시 Notion 우선. R/R 하드코딩 금지.


## 3. 보고·승인
- 일일 08:00 통합 보고: `notion-c-level-agents/scripts/ceo_morning_brief_08.py`
- 텔레그램: `telegram_bot/bot.py` + `daily_scheduler.py` (PID 가동)
- CEO 인박스 DB: `fed0015b-23cc-4faf-8acb-d3310edf4f72` (INBOX_DB_ID)
- 봇 토큰 SSOT: `telegram_bot/.env`


## 4. 운영 제약
### 거버넌스
1. 모든 출력 한국어. 영어 최소화, 약어 한글 병기
2. SOP·분석·보고 시 Notion DB 선행 조회
3. Notion DB 쓰기·수정 = GM님 명시 승인 후
4. 금지항목 외 자율 진행 (💰결제·🔒보안·🚫금지·전략·공식값만 GM 결재)

### 토큰·실행 효율 (5대 원칙)
1. 이미 읽은 파일 재확인 금지
2. 불필요한 도구 호출 금지
3. 의존성 없는 도구 호출 병렬 실행
4. 20줄+ 불필요 출력은 서브에이전트(Haiku) 위임
5. 사용자가 설명한 내용 반복 금지

상세 교육자료·고도화 프롬프트 → 가이드허브 참조 (6번)

## 5. post-action 훅
위치: `notion-c-level-agents/scripts/clevel_post_action.py`
용도: .bat 종료 직전 업무자동화DB patch + 텔레그램 1줄 보고.
인자: `--clevel --task-id --status --summary [--version] [--changelog] [--dry-run]`


## 6. 가이드허브 — GM·AI CEO 통합 SSOT
위치: `3. 웰페리온 가이드/wellperion_guide(main).html`
배포: https://wellperion-cao.github.io/wellperion-automation/
GM 업무·AI C-Level 협업 매뉴얼·교육자료·고도화 프롬프트의 단일 마스터 문서.
세부 지식은 본 CLAUDE.md에 복사하지 않고, 필요 시 허브를 펼쳐 참조한다 (허브 = 원본, CLAUDE.md = 인덱스).
