# 웰페리온 자동화 (welperion-automation)
메인 SSOT. 모든 sub-project·자동화·콘텐츠·자산은 본 폴더 하위 통합. 자산 위치 상세 → `INDEX.md`.

> 💰 **토큰 캐시 2규칙(고정)** — ① **모델 라우팅:** 루틴(read·patch·집계·송부)=Sonnet/Haiku, Opus=판단·검토만 (상세 매트릭스=S2 g10⑨). ② **idle:** 긴 작업 후 자리 비울 땐 `/clear`로 캐시 끊기.

## 0. 회사 정보
| 항목 | 값 |
|---|---|
| 상호 | 주식회사 웰페리온 (Wellperion) |
| 주소 | 서울특별시 용산구 서빙고로 413, 101동 지1층 101호외 2 (한남동) |
| 포지셔닝 | 하이엔드 프라이빗 스포츠클럽 멤버십 커뮤니티 |
| 브랜드 용어 | "피트니스" 금지 → "스포츠클럽" / "현대하이페리온" 금지 → "웰페리온" / "가이드허브" 금지 → "웰페리온 ERP" |
| 미션 | 지속되지 않는 건강 문제를 해결한다 |
| 공식 링크 | http://wellperion.com/ (회사 대표 홈, HTTP 전용) · 문의 진입점 → http://wellperion.com/ko/inquiry/ |
| 업무보고 봇 | @namuki_report_bot (Chat ID 8254867551) |


## 1. AI C-Level 7 에이전트
`wellperion-agents/.claude/agents/` 정의. 보고 라인: 6 C-레벨 → AI CEO → GM님.
| 직책 | 닉네임 | 파일 | 라우팅 키워드 |
|---|---|---|---|
| AI CEO | 웰리 | ai-ceo.md | 전사 전략·통합 판단 |
| AI CFO | 시뽀 | ai-cfo.md | 재무 |
| AI CHRO | 시로 | ai-chro.md | 인사 |
| AI CMO | 시모 | ai-cmo.md | 마케팅 |
| AI COO | 시우 | ai-coo.md | 운영 |
| AI CPO | 시포 | ai-cpo.md | 회원·CS |
| AI CTO | 시토 | ai-cto.md | 시설·기술 |


## 2. R/R SSOT — 웰페리온 ERP
> **운영 원칙·R/R 단일 출처 = S2 웰페리온 ERP g10(공통탭 + 본인탭).** CLAUDE.md는 인덱스 — 원칙 상세 하드코딩 금지, 원칙 추가는 S2에만.
- AI C-Level 운영 가이드: `3. 웰페리온 가이드/wellperion_guide(main).html` → `id="g10"` 영역
- 공통 탭 (전 C-Level 필수): `data-panel="common"` — 절대 원칙 3대·업무 처리 3단계·보고 표 형식 의무
- 본인 탭: `data-panel="{role}"` — 페르소나·핵심역할·담당 KPI·실무진·핵심업무·협업 리듬
- 규칙: 작업 전 반드시 웰페리온 ERP fetch. R/R 하드코딩 금지. Notion AI 조직 DB는 폐기 진행 중 — 호출 금지.
- 본인 위임 task: **`status/_queue.json` 단일 출처**에서 본인 clevel의 PENDING·IN_PROGRESS만. `status/{role}.json`은 보조(메타)뿐 — 완료건 부활 금지, 큐 비면 '대기'.


## 3. 보고·승인
- 일일 08:00 통합 보고: `wellperion-agents/scripts/ceo_morning_pipeline.py` (예약작업 Wellperion-CEO-Morning-Brief-0800-Live, 08:00). 구 ceo_morning_brief_08.py는 폐기·미존재
- 텔레그램 (범위: C-Level 보고 + GM 승인 회신 전용): `telegram_bot/bot.py` + `daily_scheduler.py` (PID 가동)
- GM 자유텍스트 지시 채널: CLI(현 세션) · 모바일 Claude Code (remote)
- 봇 토큰 SSOT: `telegram_bot/.env`
- ※ CEO 인박스 DB(INB)는 2026-05-29 폐기 (텔레그램 보고+승인 전용화)
- 보고 포맷·운영 원칙 상세 = S2 g10 공통탭 fetch (사이클 보고 3섹션+5필드 등 정본은 S2 단일 출처).


## 3-1. 할일 단일 정의 — 🧭 오늘의 항로 + 항해 세계관 (2026-06-05 GM 정립 · 2026-06-06 재박제·커밋)
> ⚠️ 이 정의는 2026-06-05 GM과 정립했으나 **커밋 누락으로 작업트리 리셋에 유실** → 보고 용어 어긋남. 이번엔 커밋으로 영구 박제.
> **항해 세계관 (층위 혼동 금지):**
> - 🌟 **북극성** = 목적지·비전 (어디로 가나 · 7모듈·장기)
> - 🌊 **항해** = 배들이 항로를 따라 움직이는 **전체 파이프라인·여정** (시스템 세계관 이름 — **일일 보고 '제목' 아님**)
> - 🧭 **항로** = 오늘 가는 뱃길 = **오늘 할 일** (모든 일일 할일 표면의 **제목·이름표 표준**)
> - 🚢 **배** = 개별 업무·프로젝트·미션 (무게=priority: 🛳️크루즈/⛴️여객선/⛵돛단배)
> - ⚓ **항로점** = 어제가 남긴 '다음'(브릿지) / 🌀 **표류** = 완료했는데 '다음' 없음
- **제목 단일 규칙:** 8시·21시 텔레그램 보고 + G1 + 모든 일일 할일 표면 제목 = **「🧭 오늘의 항로」 하나.** "오늘의 항해"·"오늘 할 일"을 **제목으로 쓰지 말 것**(항해는 본문 세계관 설명 한정 — 항로와 한 글자 차이라 제목 혼용 시 혼란).
- **"할일·업무·오늘할일·todo·리스트업·뭐 할까" 어떤 표현이든 = 「🧭 오늘의 항로」로 응답.** 다른 목록 임의 생성 금지.
- 항로 = G1 '오늘의 항로' 보드 = **업무현황 SSOT(S3 · GAS `todo_list`) + `status/_queue.json`(PENDING·IN_PROGRESS) 머지**. retrievable 두 소스에서 항상 꺼낸다(추측·생략 금지).
- ⚠️ '개인' 분류 항목은 아직 GM PC localStorage 한정 → GM 전용 retrievable 저장소 구축 후 항로 100% 합류(후속).


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

- 박제 원리(행동=코드/훅·지식만 메모리·추가는 net-zero) 정본 = S2 g10 공통탭 통합원칙. 반복 지적은 '코드 강제 누락' 신호.

### 토큰 라우팅 매트릭스 (2026-05-29 GM 옵션 B 결재)
> 라우팅 표 정본 = **S2 g10 공통탭 ▸ 전 C-Level 통합원칙 ⑨ 토큰 라우팅 매트릭스** (Haiku=단순 read·lookup·송부 / Sonnet=가동·patch·집계·git·콘텐츠·로그 / Opus=판단·결정·검토·결재·이슈진단). 상세·갱신은 S2에만 — 표 중복 금지(2026-06-06 단일화).
- 메인 CEO·6 C-Level 에이전트 = Opus 유지(판단·결재 본업).
- 반복 작업(가동·patch·집계·git·송부)은 무조건 Sonnet/Haiku 서브에이전트(`executor` 등) 위임 강화.
- 메인 모델로 반복 작업 처리 시 토큰 사고 — 위임 누락 자체가 위반.

상세 교육자료·고도화 프롬프트 → 웰페리온 ERP 참조 (6번)

## 5. post-action 훅
위치: `wellperion-agents/scripts/clevel_post_action.py`
용도: .bat 종료 직전 업무자동화DB patch + 텔레그램 1줄 보고.
인자: `--clevel --task-id --status --summary [--version] [--changelog] [--dry-run]`


## 6. 웰페리온 ERP — GM·AI CEO 통합 SSOT
위치: `3. 웰페리온 가이드/wellperion_guide(main).html`
배포: https://wellperion-cao.github.io/wellperion-automation/
GM 업무·AI C-Level 협업 매뉴얼·교육자료·고도화 프롬프트의 단일 마스터 문서.
세부 지식은 본 CLAUDE.md에 복사하지 않고, 필요 시 허브를 펼쳐 참조한다 (허브 = 원본, CLAUDE.md = 인덱스).
