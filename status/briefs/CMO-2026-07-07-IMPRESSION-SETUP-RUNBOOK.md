# IG 노출·도달(Reach/Impressions) 측정 셋업 절차서 — 배#546

작성: 2026-07-07 · AI CMO(시모) · GM go(무료 확인 범위, 2026-07-07)
※ 본 문서 작성 시점 = **준비물만**. 실제 토큰 발급·OAuth 로그인·라이브 API 호출은 미실행(금지 범위). GM 배치 인증 세션에서 아래 GM 단계만 진행하면 나머지는 자동/자율 진행.
※ 대상 계정 = 공식 **@wellperion**(개인 namuk.wellperion은 배#31 별도 트랙 — engagement PoC만 적용, 본 배와 무관).

---

## 0. 결론 요약

| 항목 | 값 |
|---|---|
| 비용 | 무료 (IG Graph API reach/impressions는 과금 없음) |
| App Review 필요 여부 | 불필요 — 자기 계정(Self-User Access Token) 전용 |
| FB 페이지 연결 필요 여부 | 불필요 — 2024년 "Instagram API with Instagram Login" 경로는 FB 페이지 매개 없이 IG 계정 직결 |
| GM 액션 | 2건 (①계정 확인 ②OAuth 로그인 동의 1회) |
| 나머지 | 시토(토큰 갱신 스케줄러)·시모(수집·배선) 자율 |

---

## 1. 기존 인프라 실측

- `scripts/.env`에 **이미** `META_APP_ID` / `META_APP_SECRET` / `META_LONG_LIVED_TOKEN` / `META_PAGE_ACCESS_TOKEN`(공란) / `META_REDIRECT_URI=https://wellperion.com/auth/callback`가 존재. 단, 코드베이스 전체에서 이 4개 키를 실제로 읽는 `.py` 스크립트가 **하나도 없음**(grep 0건) — 과거 시도의 잔재로 추정, 용도·발급 시점·유효기간 불명.
  - ⚠️ **미검증**: `META_LONG_LIVED_TOKEN`이 지금도 유효한지, 애초에 IG용이었는지 FB용이었는지 확인 불가(문서·git 이력 없음, `.env`는 git 비추적). **재사용 가정 금지** — GM 배치 인증 세션에서 "재사용 시도(무해)→실패 시 신규 발급" 순서로 처리 권장.
  - `FACEBOOK_ENABLED=false` / `INSTAGRAM_ENABLED=false`(같은 파일)와 함께 있는 걸 보면, 과거 FB/IG 포스팅 자동화 시도의 미완성 잔재일 가능성 높음.
- 기존 IG 자동화 2건은 **전부 Playwright 세션 기반**(Graph API 아님):
  - `scripts/ig_engagement_poc.py` — `profiles/instagram/namuk.wellperion` Persistent Context로 프로필·게시물 DOM을 긁어 좋아요·댓글·팔로워 수집(view/impressions는 IG 비공개 지표라 DOM에 없음 → 이 방식으론 절대 못 얻음, 그래서 배#546이 필요).
  - `scripts/engagement_collector.py` — 당근(공개 HTML)·블로그(RSS)·카페/카카오(Playwright)만 수집, **인스타그램은 정책상 명시적 제외**(`flag_login_required()`, "Meta Graph API 토큰 필요" 주석 존재 — 배#546이 바로 이 공백을 메움).
  - → **재사용 가능분**: 없음(세션 기반 스크레이핑과 Graph API는 인증 메커니즘이 완전히 다름). **신규 필요분**: OAuth 토큰 교환·저장·갱신·수집 전부.
  - `마케팅현황대시보드.html` 채널퍼널 표(`renderChannelClickInquiry`, 라인 1227-1318)에 이미 "노출(분모)은 미측정" 각주가 박혀 있음(라인 1304) — 배#546이 채우는 자리가 코드 주석에 명시돼 있었음.

---

## 2. GM 단계 (배치 인증 세션 1회, 클릭 수준)

**사전 조건:** @wellperion 계정 비번 로그인 가능한 상태에서 진행.

### ① @wellperion 프로페셔널 계정 확인/전환
1. 모바일 Instagram 앱 → @wellperion 계정 로그인
2. 프로필 → ☰(우측 상단 메뉴) → **설정 및 개인정보** → **계정 유형 및 도구**
3. 화면에 "**프로페셔널 계정으로 전환**"이 보이면 → 눌러서 전환(카테고리: 스포츠클럽/피트니스센터류 중 택1, 실제 화면 문구는 IG 최신 UI에 따라 다를 수 있음) → "비즈니스" 선택(크리에이터 아님)
4. 이미 "프로페셔널 계정"이라고 표시돼 있으면 → 이 단계 스킵, 다음으로
5. (확인만 하면 됨, 별도 승인/결제 없음)

### ② Meta 앱 1회 OAuth 로그인 동의
1. (시토가 사전에 Meta for Developers에서 앱 파라미터를 준비해 링크 하나로 전달 — GM은 그 링크를 클릭만)
2. 링크 클릭 → Instagram 로그인 화면 → @wellperion 계정으로 로그인(이미 로그인돼 있으면 스킵)
3. "웰페리온 앱이 다음 항목에 접근하려고 합니다: 프로필 정보, 미디어, 인사이트" 같은 동의 화면 → **허용**
4. 리다이렉트 완료 화면("연동 완료" 등) 확인 → 끝. 추가 클릭 없음.

**소요 시간**: 총 5분 이내, 1세션으로 끝남(추가 재방문 불필요 — 이후 60일 자동 갱신은 백그라운드에서 처리).

---

## 3. 우리 단계 (시토/시모 자율, 토큰 발급 후)

1. **단기→장기 토큰 교환**
   - GM OAuth 동의 직후 발급되는 단기 토큰(1시간)을 `https://graph.instagram.com/access_token?grant_type=ig_exchange_token`으로 즉시 장기 토큰(60일)으로 교환.
2. **토큰 보관 위치(제안)** — `scripts/.env`에 신규 키 추가(기존 `META_*` 4종은 용도 불명확이라 재사용하지 않고 아래 신규 키로 명확화):
   - `IG_ACCESS_TOKEN=` (장기 토큰, 60일)
   - `IG_BUSINESS_ID=` (@wellperion의 IG 사용자 ID, 첫 OAuth 완료 후 `/me?fields=user_id`로 확인)
   - `IG_TOKEN_ISSUED_AT=` (발급일, 갱신 주기 계산용)
3. **60일 자동 갱신** — 기존 Task Scheduler + `launchers/*.vbs` 숨김런처 인프라 재사용(신규 예약작업은 **시토와 협업**해서 만듦, 본 배가 직접 등록하지 않음):
   - `https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token`을 **매일 1회** 호출(장기 토큰은 만료 24시간 전부터 갱신 가능 → 매일 시도가 가장 안전) → 새 토큰으로 `.env` 갱신 + `IG_TOKEN_ISSUED_AT` 갱신.
   - 실패(만료 임박인데 갱신도 실패) 시 텔레그램 경보 — 기존 `telegram_health_check.py` 패턴 재사용 제안.
4. **수집 주기** — 일 1회, 기존 `ops/start_engagement_collect.bat`(09:30 예약) 파이프라인에 4번째 스텝으로 추가하는 안 제안(현재: 당근→블로그→IG(Playwright PoC)→커밋). `scripts/ig_reach_collector.py`(§4)를 그 뒤에 추가.
5. **대시보드 배선** — §5 참조(지점만 식별, 구현은 데이터 쌓인 후).

---

## 4. 수집 스크립트 골격

`scripts/ig_reach_collector.py` (신규, `engagement_collector.py` 패턴 미러) — §5 참조. **토큰 없으면 즉시 BLOCKED 로그 후 종료, 부작용 0. 현재는 문법 검증만 완료, 라이브 호출 미실행(미검증).**

---

## 5. 대시보드 배선 지점 (식별만, 구현 아님)

- 파일: `3. 웰페리온 가이드/cmo/funnel/마케팅현황대시보드.html`
- 함수: `renderChannelClickInquiry()` (라인 1227~1318) — 현재 컬럼: 채널|클릭|문의|클릭→문의|가입|문의→가입. 라인 1304 각주 "노출(분모)은 미측정"이 배#546이 채울 자리.
- 데이터 소스 연결 방법(제안, 데이터 쌓인 후 실행):
  - `scripts/ig_reach_collector.py`가 쌓을 `status/ig_reach_ledger.json`을 `kpi_collector.py` 또는 별도 소형 집계기가 읽어 `funnel_conversion.json`류(기존 `_fcData`/`_csByUtmSource` 옆)에 `impressionsByChannel.인스타그램` 필드로 합류.
  - 표에 **7번째 컬럼 "노출(도달)"** 추가하되, 인스타그램 행만 실측치·나머지 채널(네이버·카카오·당근)은 "미측정"(현행 유지) — 억지 통일 금지 원칙(§4 CLAUDE.md 준용).
  - 대안: 표 옆에 별도 소형 위젯(당근 노출 위젯, 라인 1875 부근 패턴과 동일한 카드형)으로 IG 노출·도달만 별도 표시 — 채널마다 측정 가능 지표가 다르므로(4부서 점검 지표 지도 사례와 동일 원리) 표 통합보다 이 방식이 정직성 원칙에 더 부합할 수 있음. **결정은 데이터 첫 수집 후 시모가 확정.**

---

## 6. 정직 한계 (미검증·소급 불가 사항)

- **소급 불가**: 프로페셔널 계정 전환 이전 게시물은 인사이트 API 대상 제외 — 과거 게시물 노출·도달은 영구 미측정.
- **스토리 24시간 소멸**: 스토리 노출·도달은 게시 후 24시간 이내에만 조회 가능 — 일 1회 배치로는 놓치는 스토리 발생 가능(스토리 발행 즉시 수집 별도 트리거 필요, 후속 과제로 남김).
- **메트릭명 변경 잦음**: Meta는 Graph API 버전마다 `impressions`/`reach`/`views` 메트릭 이름·가용성을 자주 바꿈(2024~2025년 사이 일부 버전에서 media-level `impressions` deprecated, `views`로 대체된 사례 있음) — 본 문서·골격 스크립트의 메트릭명은 **작성 시점 기준 추정치**이며, 실제 첫 라이브 호출 시 최신 Graph API 공식 문서로 재확인 필수(미검증).
- **기존 `META_LONG_LIVED_TOKEN` 유효성**: 위 §1 지적대로 재사용 가정 금지, 검증 안 됨.
- **본 절차서 자체**: 라이브 API를 한 번도 호출하지 않고 작성됨(GM 인증 전이므로 금지) — 엔드포인트·응답 필드명은 Meta 공식 문서 기반 설계이나 실전 검증 전.
