# 당근 비즈프로필 자동업로드 재도전 R&D
작성일: 2026-06-04  
작성: worker-4 (AI CTO 위임)  
기반 스크립트: `scripts/danggn_upload_playwright.py` v0.1

---

## 0. 현황 요약

| 항목 | 값 |
|---|---|
| 스크립트 | setup/check/dryrun/draft/publish 모드 구현 |
| 프로필 경로 | `profiles/danggn/` — Chromium Persistent Profile |
| 마지막 check 결과 | 세션 미유지 (login 리다이렉트) |
| 쿠키 DB 실측 | 2026-06-04 실측 완료 |

---

## 1. 발행 직전 즉시 로그인 전략

### 결론: **조건부 가능 (반자동 성립 — 단, 당일 08:08 UTC 이전만)**

### 근거 (쿠키 DB 실측)

```
host=accounts.daangn.com  name=sessionId
  expires=2026-06-04 08:08:08 UTC  is_persistent=1  secure=1

host=accounts.daangn.com  name=device_id
  expires=2027-07-08 08:08:08 UTC  is_persistent=1  secure=1
```

- `sessionId`는 `is_persistent=1` — 세션쿠키(브라우저 종료 소멸)가 아니라 디스크에 영속 저장됨.
- 그러나 TTL이 **당일 08:08 UTC (KST 17:08)까지만** 유효. 약 8~9시간 수명.
- 즉 **setup(로그인) 직후 → 당일 17:08 KST 이전**이라면 브라우저 재시작 후에도 check가 성공함.
- 문제는 check를 오후 1:59에 실행했고 sessionId 만료시각이 08:08 UTC(17:08 KST)였는데, **실측 당시 이미 만료**됐을 가능성이 높음(만료 직후 check 실행).

### 반자동 성립 시나리오

```
GM 1회 로그인 (setup, headful) 
  → sessionId 발급 (당일 ~8~9시간 유효)
  → 당일 17:08 KST 이전에 스크립트가 draft/publish 실행
  → 세션 살아 있으면 자동 업로드 성공
```

### 제약 및 위험

| 제약 | 내용 |
|---|---|
| TTL ~8~9시간 | 발행을 당일 로그인 당일에만 할 수 있음. 익일 발행 불가 |
| headful 필수 | setup은 GM 인터랙티브 로그인(카카오/전화 인증 포함) 필요 — 자동화 불가 |
| 당근 쿠키 갱신 여부 미확인 | draft 실행 시 세션 갱신이 되는지 추가 실측 필요 |
| 스크립트 draft/publish 미구현 | 에디터 DOM 실측 후 다음 단계 구현 필요 |

### PoC 절차 (구현 전제)

1. GM이 `--mode setup` 실행 (headful, KST 오전 중)
2. setup 성공(sessionId 발급) 직후 `--mode check` 실행 → 세션 유효 확인
3. 당일 17:08 KST 이전 `--mode draft` 실행 (에디터 DOM 자동입력 구현 필요)
4. 성공 시 `--mode publish` (GM go 가드 통과 후)

---

## 2. 쿠키 만료 원인 분석

### 결론: **단기 TTL 세션쿠키 (브라우저 종료 소멸 아님 — TTL 문제)**

### 상세

| 쿠키 | 도메인 | 만료 | 유형 |
|---|---|---|---|
| `sessionId` | accounts.daangn.com | ~8~9시간 TTL | 인증 핵심 — 단기 TTL |
| `device_id` | accounts.daangn.com | 2027-07-08 | 장기 영속 (기기 식별용, 인증 아님) |
| `_clsk` | .daangn.com | 익일 | MS Clarity 분석용 |
| `_ga*` | .daangn.com | 1년 | Google Analytics |
| `_fbp`, `_gcl_au` | .daangn.com | ~3개월 | 광고 추적 |

- Persistent Profile이 sessionId를 디스크에 저장하는 구조는 **정상 작동**하고 있음.
- 세션쿠키(만료일 없음) 저장 불가 문제가 아니라, **당근이 sessionId 자체를 ~8~9시간 단기 TTL로 발급**하는 것이 근본 원인.
- 로그인 방식은 카카오 OAuth 경유 추정 — OAuth access token 수명과 연동된 단기 TTL.
- `bizprofile.daangn.com` 도메인의 쿠키는 별도 없음 — 인증은 `accounts.daangn.com` sessionId 단일 경로.

### 왜 check가 실패했나

setup이 오전에 실행된 경우, sessionId 만료(~17:08 KST) 이후 check를 실행하면 login 리다이렉트 발생. Persistent Profile 저장 자체는 성공했으나 TTL 도과가 원인.

---

## 3. 당근 앱 딥링크 / 공유 인텐트

### 결론: **비즈프로필 글쓰기 딥링크 — 공개 미확인, 사실상 불가**

### 근거

- 당근 앱 URL scheme(`karrot://`)의 공개 개발자 문서 없음. 공식 딥링크 스펙 비공개.
- 비즈프로필 소식 글쓰기 전용 딥링크는 검색·공식 문서 어디에도 확인 불가.
- 당근 비즈니스 공식 가이드(businessdaangn.gitbook.io)에 API·딥링크·자동화 섹션 없음.
- 앱 공유 인텐트(Android Intent / iOS Universal Link)로 텍스트+이미지를 비즈프로필 에디터에 프리필하는 공개 경로 없음.
- **모바일 앱 의존** — Windows 자동화 환경에서 앱 딥링크 트리거 자체가 구조적으로 불가.

### 구조적 불가 사유

당근 비즈프로필 글쓰기는 앱 전용 UI(또는 bizprofile.daangn.com 웹). 딥링크로 에디터 열기는 앱에서만 가능하며, PC 자동화(Playwright)에서 앱 인텐트를 트리거하는 경로가 없음. Windows 스크립트로 딥링크 경유 업로드는 구조적 불가.

---

## 4. 당근 비즈 공식 API / 파트너 채널

### 결론: **공개 API 없음, 파트너 채널 미확인 — 구조적 불가**

### 근거

- `business.daangn.com` 전체 메뉴 확인: 광고(간편/전문가모드), 검색광고, 비즈프로필, 브랜드프로필, 알바 — API 또는 개발자 포털 없음.
- `businessdaangn.gitbook.io` 공식 가이드: 비즈프로필 생성·운영 사용자 가이드만 존재. API·자동화·파트너 섹션 없음.
- GitHub `daangn` org: `karrot-conversion-tracker-tool-support` 등 광고 전환추적 툴만 공개. 비즈프로필 소식 업로드 API 없음.
- 당근 광고 API(전문가모드)는 광고 집행 전용이며 소식글 업로드와 무관.
- 소셜 미디어 플랫폼 중 당근은 Facebook Graph API·네이버 블로그 Open API 같은 콘텐츠 업로드 공개 API를 제공하지 않음.

### 구조적 불가 사유

당근은 소식글(비즈프로필 게시글) 업로드를 위한 공개 REST API, Webhook, 파트너 채널을 제공하지 않음. 제3자 자동화는 구조적으로 스크래핑·브라우저 자동화(Playwright 등)에만 의존할 수밖에 없음.

---

## 5. 종합 판단 및 권고

### 자동화 가능 여부 매트릭스

| 전략 | 가능 여부 | 조건 |
|---|---|---|
| 완전 자동화 (스크립트 단독) | **불가** | sessionId 단기 TTL, GM 로그인 필수 |
| 반자동 (GM 1회 로그인 → 당일 자동 발행) | **조건부 가능** | 로그인 당일 17:08 KST 이전 / draft DOM 구현 필요 |
| 앱 딥링크 경유 | **불가** | 공개 스펙 없음, 앱 전용, Windows 불가 |
| 공식 API | **불가** | 공개 API 미제공 |

### 권고

**B안(수동 운영) 유지를 기본으로 하되, 반자동(전략 1) 구현을 단계적으로 추진.**

#### 단기 (B안 유지)
- 현재 draft/publish 에디터 자동입력 미구현 상태 → 수동 업로드 병행.
- GM이 업로드 시점에 수동 로그인 후 스크립트 연계하는 반자동 절차 정립.

#### 중기 (반자동 구현 목표)
1. **에디터 DOM 실측**: GM이 `--mode setup` 후 bizprofile.daangn.com 글쓰기 에디터 접속 → DOM 구조 캡처 (headful 필수).
2. **draft 자동입력 구현**: 제목/본문/이미지 업로드 DOM 실측 결과 기반.
3. **반자동 운영 플로우**:
   ```
   GM 아침 setup 실행 (1~2분)
   → 스크립트 자동으로 draft/publish 처리 (당일 17시 KST 이전)
   → 텔레그램 결과 보고
   ```
4. **세션 갱신 가능성 탐색**: draft 실행 후 sessionId 재발급 여부 실측 (TTL 연장 가능하면 이중 업로드도 가능).

#### 구조적 한계 (변경 불가)
- headful 로그인 1회는 영구적으로 GM 수동 개입 필요.
- 완전 무인 자동화는 당근이 공개 API를 제공하지 않는 한 불가.

---

## 6. 참고: 쿠키 분석 스크립트

`scripts/check_danggn_cookies.py` — Persistent Profile 쿠키 DB 직접 조회 (이름·만료일만, 값 비공개).  
실측 결과는 위 §2 참조.
