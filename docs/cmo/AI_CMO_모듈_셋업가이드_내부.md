# AI CMO 콘텐츠 모듈 — 내부 셋업 가이드 (GM·시모 전용)

> ★내부 전용 · ERP 페이지 노출 금지. 이 모듈이 반무인으로 돌기 위한 3대 셋업. 실측 기반(2026-07-15).

## 0. 반무인 흐름 요약

AI 자동생성 → 사람 [승인] 1회(텔레그램) → 스크립트 무인 5채널 발행.

- 제작(창작) 단계는 예약작업으로 자동 실행되지만 **발행은 절대 자동이 아니다** — `review_queue.json`에 `status='검수대기'`로만 적재하고 GM 텔레그램에 [✅승인]/[❌반려] 카드가 발송된다.
- GM이 카드에서 [✅승인]을 탭하는 순간, 텔레그램 봇(`telegram_bot/bot.py`)의 콜백이 발행 엔진(`ig_review_publish_watcher.py --once`)을 그 자리에서 1회 호출해 채널별로 무인 발행한다. **폴링(주기적 자동 재확인)은 폐기됨** — 승인 탭이 유일한 트리거.
- 모델 상세 = 스펙 `docs/superpowers/specs/2026-07-15-cmo-content-module-semi-unmanned-m1-design.md`.

## 1. 채널 계정·세션 등록 (1회 셋업)

로그인 세션은 `profiles/` 하위 영속 Chrome 프로필(`launch_persistent_context`)로 저장된다. 일부 채널은 프로필 손상 시 대비용 쿠키 백업(`storage_state`)도 별도 파일로 둔다.

| 채널 | 방식 | 프로필/세션 경로 | 재로그인 방법 |
|---|---|---|---|
| 인스타그램 (2계정) | 영속 Chrome 프로필 | `profiles/instagram/{account}/` (기본 `namuk.wellperion`, 공식 `wellperion`) | `python scripts\instagram_upload_playwright.py --mode setup [--account wellperion]` (수동 로그인) 또는 `--mode setup-auto` (자동 감지 저장, Enter 불필요) |
| 네이버 블로그 | 영속 Chrome 프로필 + 쿠키 백업 | `profiles/naver-blog/` (프로필) · `profiles/naver-blog_state.json` (쿠키 백업) | `python scripts\naver_blog_upload_playwright.py --mode setup` |
| 네이버 카페 | 영속 Chrome 프로필 + 쿠키 백업 | `profiles/naver-cafe/` (프로필) · `profiles/naver-cafe_state.json` (쿠키 백업) | `python scripts\cafe_upload_playwright.py --mode setup` |
| 당근마켓 비즈 | 영속 Chrome 프로필 + 쿠키 백업 | `profiles/danggn/` (프로필) · `profiles/danggn_state.json` (쿠키 백업) | `python scripts\danggn_upload_playwright.py --mode setup` (세션 만료 시 자동 발행이 수동 폴백으로 전환) |
| 카카오 채널 관리자 | 영속 Chrome 프로필 | `profiles/kakao-channel/` | `python scripts\kakao_channel_upload_playwright.py --mode setup` |

세션 만료 시 공통 패턴: 발행 스크립트가 `[ERROR] 로그인 세션이 만료되었습니다.` 류 메시지를 내며 자동 발행을 중단 → 위 표의 `--mode setup`(IG는 `setup-auto` 권장)으로 GM이 1회 재로그인.

각 업로더는 `--mode` 인자에 `setup` 외에도 `dryrun`(브라우저 열되 미발행)·`publish`(실제 발행)를 공통 지원하며, 블로그·카페·당근은 `migrate-cookies`(구 쿠키 마이그레이션), 당근은 추가로 `check`·`engagement`도 지원한다.

## 2. 예약작업 (무인 구동 스케줄)

`Get-ScheduledTask`로 실측한 `Wellperion-*` 태스크 중 CMO 콘텐츠 모듈 관련 항목(전부 `State: Ready`):

| 태스크명 | 시각 | 하는 일 | 스크립트 |
|---|---|---|---|
| Wellperion-IG-Series-Produce-0730 | 07:30 | AI 시리즈(공식/개인) 다음 편 제작 → M5 검수큐 적재(발행 안 함). 같은 배치에서 실전사례(namuk 개인계정) 재고표 기반 반자동 발송도 이어서 실행 | `ig/start_ig_series_producer.bat` → `scripts/ig_series_producer.py` + `scripts/case_series_dispatch.py` |
| Wellperion-LSeries-Daily-Card-0845 | 08:45 | 강습(L)시리즈 당일 예약 카드 발송(승인/발행은 절대 하지 않음) | `launchers/lesson_series_daily_card_hidden.vbs` → `scripts/lesson_series_daily_card.bat` |
| Wellperion-Engagement-Collect-0930 | 09:30 | 당근·블로그 인게이지먼트(반응) 수집(로그인 불필요) | `ops/start_engagement_collect.bat` |
| Wellperion-IG-Reach-Collect-0945 | 09:45 | 인스타그램 계정·게시물 도달(reach)/노출 수집(Graph API) | `ops/start_ig_reach_collect.bat` |
| Wellperion-IG-Token-Refresh-Weekly | 주간 | IG Graph API 토큰 주간 갱신 | `launchers/ig_token_refresh_hidden.vbs` |
| Wellperion-CMO-Daily-Marketing-2100 | 21:00 | 마케팅 피드백 일일 집계 | `launchers/weekly_marketing_feedback_daily_hidden.vbs` |
| Wellperion-CMO-Weekly-Marketing-Feedback | 주간 | 마케팅 피드백 주간 리포트 | `launchers/weekly_marketing_feedback_hidden.vbs` |
| Wellperion-CMO-Monthly-Report | 월간 | CMO 월간 리포트 | `scripts/monthly_marketing_report.py` |

**발행 엔진(`ig_review_publish_watcher.py`) 자체는 예약작업이 아니다.** GM의 텔레그램 [✅승인] 탭 콜백(`telegram_bot/bot.py` → `cmd_publish_callback`)이 그 순간 `--once`로 1회 호출하는 이벤트 구동 방식이며, 상시 상주 봇은 `WellperionTelegramBot` 태스크(`launchers/bot_hidden.vbs`)로 항상 켜져 있다.

## 3. 큐·게이트 배선 (검수→승인→발행)

- **큐 파일**: `3. 웰페리온 가이드/cmo/review/review_queue.json` — 검수 카드와 발행 엔진이 공유하는 단일 SSOT.
- **상태 전이**: `검수대기` → (GM 승인 탭) → `승인` → (발행 엔진 채널 분기 실행) → `발행완료` / `발행실패` / `수동발행대기`(세션 만료 등 자동 폴백). 반려 시 `반려`.
- **채널 분기** (`ig_review_publish_watcher.py` 내부, GM 승인 2026-07-13 — 전채널 자동 공개발행):
  - 블로그 → `naver_blog_upload_playwright.py --mode publish`
  - 카페 → `cafe_upload_playwright.py --mode publish`
  - 당근 → `danggn_upload_playwright.py --mode publish` (세션 만료 시 수동 폴백)
  - 카카오 → `kakao_channel_upload_playwright.py --mode publish`
  - 나머지(인스타 등) → `instagram_upload_playwright.py --mode publish`
- **안전망**: 발행 직전 `scripts/publish_preflight.py`(발행 요새화 §1 사전점검 — 본문·이미지·태그·링크 온전성 검사)와 `scripts/publish_integrity_gate.py`(§2 무결성 게이트, 블로그·카페·당근 공유 판정 프레임)가 깨진 글의 발행을 차단(FAIL) 또는 경고(WARN)한다.
- **발행요약**: 같은 실행(run)에서 `발행완료`로 전환된 항목들을 `scripts/publish_digest.py`의 `send_publish_digest()`가 콘텐츠(폴더) 단위로 묶어 문의·컨택·등록 알림 텔레그램방에 통합요약 1건으로 발신(멱등 — `.publish_digest_sent.json` 해시로 재발신 방지).
- **동시성**: 큐 갱신·git 커밋은 `git_lock.py`의 `GitLock`으로 직렬화, 발행 자체는 `.publish.lock`(스테일 회수 1200초)으로 중복 실행을 막는다.

## 4. 타 업체 도입 시 (제품화·내부 메모)

자기 채널만 §1처럼 등록(영속 프로필 setup 1회)하면 동일 엔진(§2 예약 제작 + §3 큐·게이트·발행)을 재사용할 수 있다. 상세 설계 = `docs/superpowers/specs/2026-07-15-cmo-content-module-semi-unmanned-m1-design.md` (배747 계열, C-Level 자율화 두뇌 제품화 레퍼런스).

## 5. 주의(정직)

- **제작(창작)은 AI/사람 협업이 필요하다.** 공식/개인 시리즈는 헤드리스 claude(시모)가 로드맵을 읽어 초안을 쓰고, 실전사례(namuk)는 창작 코드가 구조적으로 없어(설계상 "정직 가드") 시모가 미리 만들어둔 파일만 읽는다 — 파일이 없으면 카드를 만들지 않는다(빈 카드·지어낸 카드 발송 금지).
- **발행만 AI 개입 없이 무인이다.** GM의 텔레그램 [✅승인] 탭이 유일한 게이트이며, 그 뒤 5채널(인스타×2·블로그·카페·당근·카카오) 발행은 스크립트가 전담한다.
- **완전무인(자동승인)은 아직 없다.** 신뢰가 누적되고(라이브검증 무결 반복) 게이트가 더 강화된 뒤에만 검토 대상이며, 현재는 예약작업이 GM 승인 없이 발행까지 진행하는 경로가 존재하지 않는다.
- 표에 없는 채널·프로필(예: `profiles/bing/`, `profiles/wordpress/`)은 CMO 콘텐츠 발행 파이프라인과 직접 연결된 근거를 찾지 못해 **확인 필요**로 남긴다.
