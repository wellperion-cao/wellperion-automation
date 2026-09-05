# 상담봇 업체 정본(테넌트 프로필) — 정형화 스키마 v1.0 (GM 지시 2026-09-05)

> 상담봇(옛 이름 AEO 채팅봇)이 업체 하나를 맡을 때 갖고 있어야 하는 정보의 **단일 형식**. 업체가 달라도 칸은 같다.
> 파일 = `server/counselbot/tenants/{n}_{업체}.json` (프로필 정본 · 저장소 · 배포마다 서버 `profile.json` 으로 복사).
> ★FAQ 는 다르다(시토 배1036 원칙 · 2026-09-05): 서버 `/srv/erp/faq/{tenant}/faq.json` 이 **라이브 정본**(관리자 페이지가 편집) · 저장소 파일은 **첫 배포 씨앗 + 되밀기 사본**. 배포 스크립트는 서버에 faq.json 이 있으면 덮지 않는다. 내용을 바꿀 땐 관리자 API(생기기 전엔 scp 1회)로 서버를 고치고 저장소로 되밀어 둔다.
> 지어내지 않는다 — 못 받은 칸은 `null` 또는 `"미수령"`. 대표가 확인한 칸만 `verified: true`.

| 구역 | 칸 | 뜻 | 누가 채우나 | 검증 |
|---|---|---|---|---|
| `tenant` | `id` · `name` · `name_en` · `type`(스포츠클럽·PT센터·필라테스…) | 업체 식별 | 시보 | 대표 확인 |
| `identity` | `one_liner`(한 줄) · `philosophy` · `tone`(어투 규칙) · `service_concept`(공통 = 「컨시어지」 호텔급 서비스 마인드 · GM 09-05 · 원칙 7 = 설계 §3-2) · `sales_style`(업체별 세일즈 결 — 공통 세일즈 원칙 5 = 설계 §3-3) · `counselor_persona`{name·greeting·handoff·typing_ms·emoji}(★GM 2026-09-05: 고객 화면은 FAQ·봇 느낌이 아니라 **진짜 상담원과 대화하는 느낌** — 사람 말투·이모지·「답변 중…」 표시 · 'FAQ'·'AI'·'초안' 낱말은 고객 화면에 안 보임) | 봇의 말투와 자기소개 — 브랜드가이드 §1·§2 에서 온다 | 시보 초안 → 대표 | 대표 확인 |
| `facts` | `address` · `hours`{weekday·weekend·holiday·closed_rules[](예 "매월 둘째·넷째 일요일")·closed_dates[]} · `phone` · `parking` · `capacity` · `founded` | 사실 정보 — 검색·AI 검색(GEO)이 같은 문장으로 읽어야 함 | 대표 | 대표 확인 필수 |
| `channels` | `reservation_url`(상담 예약 링크 · 봇이 못 답할 때 보내는 곳) · `kakao` · `instagram` · `blog` · `naver_place` | 손님을 넘길 곳 | 대표 | 링크 실제 열림 확인 |
| `offerings[]` | `name` · `who`(누구에게) · `what`(무엇을) · `how`(진행 방식) · `price_policy`(금액 대신 "상담 시 안내" 등 문장) | 상품·프로그램 | 시보(원자료) → 대표 | 대표 확인 |
| `policies[]` | `topic`(연기·휴회·환불·양도·예약·노쇼…) · `text`(문장) | 규정 — 금액·법적 판단은 넣지 않는다 | 대표 | 대표 확인 필수 |
| `faq[]` | `id` · `q` · `a` · `alt[]`(같은 뜻 다른 표현) · `source`(근거 파일/답변 날짜) · `verified`(대표 확인) · `updated` | 상담봇이 답하는 유일한 근거 | 시보 초안 → 대표 → 미답 학습 | `verified:false` 는 위젯에 「초안」 표시 |
| `guards` | `forbidden_topics[]`(금액·의료·계약…) · `medical_words[]` · `handoff_text`(못 답할 때 문장) | 지어내기·위험 답 차단 — 코드가 읽는다 | 시보(공통 기본값) · 업체별 추가 | 시토 selfcheck |
| `learning` | `unanswered_days` · `question_bank[]`(대표께 여쭐 것) · `ask_channel`(카톡 방 이름) · `ask_time` | 못 답한 질문을 대표께 되돌리는 회로 | 시보 | 발신 로그 |
| `kpi` | `baseline`(도입 첫 주 · 월 문의 수 등) · `metric`("봇 자력 답변 비율/월") · `target` | 건별 KPI 1개 | 시보 ↔ 대표 합의 | 월 보고 |
| `meta` | `version` · `updated` · `owner_ai`("시보") · `status`(수집중·초안·대표확인·라이브) | 판·상태 | 시보 | — |

**정본화 절차(모든 업체 동일)**
1. **수집** — 온보딩 체크리스트(`onboarding_checklist.md` 20문항)를 원자료(자료·설문·아침 질문)로 채운다. 못 받은 것은 `미수령`.
2. **초안** — 시보가 위 칸에 옮긴다(`status: 초안`). 사실을 더하지 않는다.
3. **대표 확인** — 초안 페이지(다캠 라인 `/dietcamp/drafts_*.html` 류)로 보여 드리고 틀린 줄만 받는다 → `verified: true`.
4. **라이브** — 배포 스크립트가 서버 사본을 갱신(`status: 라이브`). 위젯은 `verified` 인 FAQ 만 「확정」, 나머지는 「초안」 표시.
5. **학습** — 미답 목록(`/api/chat/{tenant}/unanswered`) → 아침 질문 1개 → 답이 오면 `faq[]` 한 줄 추가 → 3 으로.

**현재 코드가 읽는 최소 부분집합**: `meta.reservation_url` + `faq[].{id,q,a,alt}` (시토 배1018). 나머지 칸은 v1.1 에서 코드가 읽게 확장(시토) — 그 전에도 정본 파일에는 다 적어 둔다(정형화가 먼저, 코드가 따라온다).

**「왜 쌓나」를 함께 쌓는다(GM 2026-09-05).** 질문 정본 = `question_bank.json`(110문 · 질문마다 why·feeds). 업체별 답 = `tenants/{t}_qa.json` — 한 답마다 `{q_id, answer, source(자료/인터뷰/카톡 날짜), answered_on, promoted_to(정본 칸)}`. 정본 칸의 문장이 어디서 왔는지는 이 파일로 되짚는다. 기반 단계 = 인터뷰 1회로 한 번에(하루 1문으로는 넉 달) · 보강 = 아침 카톡 1문/일.
