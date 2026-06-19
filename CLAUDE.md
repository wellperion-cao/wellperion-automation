# 웰페리온 자동화 (welperion-automation)
메인 SSOT. 모든 sub-project·자동화·콘텐츠·자산은 본 폴더 하위 통합. 자산 위치 → `INDEX.md`.

> 💰 **토큰 캐시 2규칙(고정)** — ① **모델 라우팅:** 루틴(read·patch·집계·송부)=Sonnet/Haiku, Opus=판단·검토만 (상세=S2⑨). ② **idle:** 긴 작업 후 자리 비울 땐 `/clear`로 캐시 끊기.

> 📐 **SSOT .md 규칙(누적기록 금지 · 2026-06-12)** — 모든 살아있는 SSOT .md = **현행 규칙·파이프라인·상태만** 담는다. 결정 경위·사고 기록·폐기 사유 본문 금지. 규칙 변경 = 해당 섹션 **교체**, 경위는 짝 이력 파일에 날짜별 append (본 파일 → `docs/CLAUDE_이력.md` / AI 시리즈 → `instagram/_AI시리즈_이력.md`). 스크립트가 파싱하는 표는 구조 변경 금지.

## 0. 회사 정보
| 항목 | 값 |
|---|---|
| 상호 | 주식회사 웰페리온 (Wellperion) |
| 주소 | 서울특별시 용산구 서빙고로 413, 101동 지1층 101호외 2 (한남동) |
| 포지셔닝 | 하이엔드 프라이빗 스포츠클럽 멤버십 커뮤니티 |
| 브랜드 용어 | "피트니스" 금지→"스포츠클럽" / "현대하이페리온" 금지→"웰페리온" / "가이드허브" 금지→"웰페리온 ERP" |
| 미션 | 지속되지 않는 건강 문제를 해결한다 |
| 공식 링크 | http://wellperion.com/ (대표 홈, HTTP 전용) · 문의 → http://wellperion.com/ko/inquiry/ |
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
> **운영 원칙·R/R 단일 출처 = S2 웰페리온 ERP(공통탭 + 본인탭).** CLAUDE.md는 인덱스 — 원칙 상세 하드코딩·S2 외 추가 금지.
- AI C-Level 운영 가이드: `3. 웰페리온 가이드/wellperion_guide(main).html` → `id="S2"` 영역
- 공통 탭 (`data-panel="common"`): 절대 원칙 3대·업무 처리 3단계·보고 표 형식 의무
- **부팅 흡수(중요):** 약속·재발방지·공식값은 S2가 **클라이언트 JS 렌더만** 함 → 페이지(HTML)를 읽어선 흡수 안 됨("불러오는 중…"만 보임). 부팅 시 `ssot/약속.json`·`ssot/incidents.json`·`ssot/canon_values.json`을 **직독**해 흡수한다. 정본=ssot/, S2=렌더(사람용).
- 본인 탭 (`data-panel="{role}"`): 페르소나·핵심역할·담당 KPI·실무진·핵심업무·협업 리듬
- 규칙: 작업 전 반드시 웰페리온 ERP fetch. R/R 하드코딩 금지. Notion AI 조직 DB 폐기 진행 중 — 호출 금지.
- 본인 위임 task: **`status/_queue.json` 단일 출처**에서 본인 clevel의 PENDING·IN_PROGRESS만. `status/{role}.json`은 보조(메타)뿐 — 완료건 부활 금지, 큐 비면 '대기'.

## 3. 보고·승인
- 일일 08:00 통합 보고: `wellperion-agents/scripts/ceo_morning_pipeline.py` (예약작업 Wellperion-CEO-Morning-Brief-0800-Live). 구 ceo_morning_brief_08.py 폐기·미존재.
- 텔레그램 (C-Level 보고 + GM 승인 회신 전용): `telegram_bot/bot.py` + `daily_scheduler.py` (PID 가동)
- GM 지시 채널: CLI(현 세션) · 모바일 Claude Code (remote)
- 봇 토큰 SSOT: `telegram_bot/.env`
- CEO 인박스 DB(INB) = 폐기 — 호출 금지.
- 보고 포맷·원칙 상세 = S2 공통탭 fetch (사이클 보고 3섹션+5필드 등 정본은 S2 단일 출처).

## 3-1. 할일 단일 정의 — 🧭 오늘의 항로 + 항해 세계관
> **항해 세계관 (층위 혼동 금지):**
> - 🌟 **북극성** = 목적지·비전 (7모듈·장기)
> - 🌊 **항해** = 전체 파이프라인·여정 (시스템 세계관 이름 — **일일 보고 '제목' 아님**)
> - 🧭 **항로** = 오늘 가는 뱃길 = **오늘 할 일** (일일 할일 표면의 **제목·이름표 표준**)
> - 🚢 **배** = 개별 업무·프로젝트·미션 (무게=priority: 🛳️크루즈/⛴️여객선/⛵돛단배)
> - ⚓ **닻(대기/정박)** = 출항 전(아직 시작 안 함) 또는 진행중 멈춰 다시 정박(보류·대기 복귀)
> - 🏁 **완료** = 입항·도착 / 🔗 **항로점** = 완료하며 '다음'을 남김(다리 놓음) / 🌀 **표류** = 완료인데 '다음' 없음 → **핵심조언 + "👉 다음 정하세요" 촉구 둘 다** 표시(그냥 두지 않는다)
- **제목 단일 규칙:** 8시·21시 텔레그램 보고 + G1 + 모든 일일 할일 표면 = **「🧭 오늘의 항로」 하나.** "오늘의 항해"·"오늘 할 일"은 **제목 사용 금지** (항해는 본문 세계관 설명 한정).
- **"할일·업무·오늘할일·todo·리스트업·뭐 할까" 어떤 표현이든 = 「🧭 오늘의 항로」로 응답.** 다른 목록 임의 생성 금지.
- 항로 = G1 '오늘의 항로' 보드 = **업무현황 SSOT(S3 · GAS `todo_list`) + `status/_queue.json`(PENDING·IN_PROGRESS) 머지**. 두 소스에서 항상 꺼낸다(추측·생략 금지).
- **업무 단일 진실 = G1 (약속 L15).** 모든 C-Level은 본인 업무를 사소한 것이라도 `status/_queue.json` 본인 '배'로 적고 진행하며 즉시 커밋·푸시(GM이 보는 곳). 큐에 없으면 항로에도 없다.
- **아침 항로 리스트업 양식 = 약속 L16 · 3섹터 마크다운 표 (전 C-Level 통일 · 아이콘 표준 A안).** 섹터: 🚢 진행중 / ⚓ 대기중 / 🏁 입항 완료 (오늘). 표 칼럼 5개: 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언. 배 칸=난이도 배(⛵/⛴️/🛳️)만 · 상태는 섹터 제목에만. 담당=닉네임+식별번호(_queue ship_no·예 '시모 28'·배마다 고정). 본질+핵심조언=한 칸 합침. 대기중: 보류 건='보류' 꼬리표. 입항 완료 (오늘): 🔗(다음있음=항로점) · 🌀(다음없음=표류, →핵심조언+'👉 다음 뭐 할지 정하세요' 촉구). 완료 표현='입항 완료 (오늘)' 통일. ★⚓=대기/정박·완료는 🏁. 상세 정본 = `ssot/약속.json` L16.
- ⚠️ '개인' 분류 항목은 아직 GM PC localStorage 한정 → GM 전용 retrievable 저장소 구축 후 항로 100% 합류(후속).

## 4. 운영 제약
### 거버넌스
1. 모든 출력 한국어. 영어 최소화, 약어 한글 병기.
2. 금지항목 외 자율 진행 (💰결제·🔒보안·🚫금지·전략·공식값만 GM 결재).

### 토큰·실행 효율 (5대 원칙)
1. 이미 읽은 파일 재확인 금지
2. 불필요한 도구 호출 금지
3. 의존성 없는 도구 호출 병렬 실행
4. 20줄+ 불필요 출력은 서브에이전트(Haiku) 위임
5. 사용자가 설명한 내용 반복 금지

- 박제 원리(행동=코드/훅·지식만 메모리·추가는 net-zero) 정본 = S2 공통탭. 반복 지적은 '코드 강제 누락' 신호.

### 토큰 라우팅 매트릭스
> 정본 = **S2 공통탭 ▸ 통합원칙 ⑨** (Haiku=read·lookup·송부 / Sonnet=가동·patch·집계·git·콘텐츠·로그 / Opus=판단·결정·검토·결재·이슈진단). 상세·갱신은 S2에만 — 표 중복 금지.
- 메인 CEO·6 C-Level = Opus 유지(판단·결재 본업).
- 반복 작업(가동·patch·집계·git·송부)은 무조건 Sonnet/Haiku 서브에이전트(`executor` 등) 위임. 메인 모델로 처리 시 위반.

상세 교육자료·고도화 프롬프트 → 웰페리온 ERP 참조 (6번)

## 5. post-action 훅
위치: `wellperion-agents/scripts/clevel_post_action.py`
용도: .bat 종료 직전 업무자동화DB patch + 텔레그램 1줄 보고.
인자: `--clevel --task-id --status --summary [--version] [--changelog] [--dry-run]`

## 6. 웰페리온 ERP — GM·AI CEO 통합 SSOT
위치: `3. 웰페리온 가이드/wellperion_guide(main).html`
배포: https://wellperion-cao.github.io/wellperion-automation/
GM 업무·AI C-Level 협업 매뉴얼·교육자료·고도화 프롬프트 단일 마스터. 세부 지식은 허브를 펼쳐 참조 (허브=원본, CLAUDE.md=인덱스).
