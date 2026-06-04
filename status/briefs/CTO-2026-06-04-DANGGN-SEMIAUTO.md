# CTO 위임 브리프 — 당근 비즈프로필 반자동 발행 구현
**task_id**: CTO-2026-06-04-DANGGN-SEMIAUTO  
**발행일**: 2026-06-04  
**결재**: GM 옵션 B 완료  
**수신**: AI CTO (시토)  
**우선순위**: NORMAL  

---

## 0. 진척 업데이트 (2026-06-04 CMO 시모 — B 결재 반영)

✅ **완료·라이브 검증**: 제목(`#title-input`) + 본문(`[contenteditable="true"]`) 자동입력 + **임시저장**(`button:has-text("저장")`) 작동 확정. `--mode setup --then-draft` 원샷(cao@wellperion.com 구글 로그인)으로 실행. 임시저장 글은 소식목록 아닌 "작성 중인 소식 이어쓰기"로 복원됨.

⚠️ **잔여 핵심 과제 = 이미지 5장 자동첨부** (이것이 B 결재의 본체). 당근 이미지 버튼이 `input[type=file]` **0개** = **Shadow DOM / canvas 기반** 추정. `page.evaluate`로 shadowRoot 침투 탐색 or 업로드 버튼 클릭→`expect_file_chooser` 방식 R&D 필요. `scripts/poc-evidence/danggn_write_page.png` 참조.

⚠️ **세션 제약 정정**: 1차 "TTL 8~9h"보다 엄격 — bizprofile 별도 goto 시 강제 sign-out. **반드시 `--mode setup --then-draft` 원샷**(로그인→같은 context 즉시 글쓰기), 작업마다 **GM 재로그인 1회**(구글 계정 선택). publish 자동화보다 이 세션/이미지 문제 우선.

실측 증거 = `scripts/poc-evidence/danggn_*.png` · 메모리 `project_danggn_manual_b_confirmed`.

---

## 1. 목표

당근 비즈프로필 소식글 **반자동 발행** 파이프라인 완성.

- GM이 아침에 `--mode setup`(headful 로그인) 1회 실행
- 당일 sessionId TTL(KST 약 17:08) 이내에 스크립트가 자동으로 draft → publish 처리
- 결과를 텔레그램(@namuki_report_bot) 보고

현행 유지: 구현 완료 전까지 B안(GM 5분 수동 업로드) 그대로 운영.

---

## 2. 핵심 제약 (변경 불가)

| 제약 | 내용 |
|---|---|
| sessionId TTL ~8~9시간 | 당근이 sessionId를 단기 TTL로 발급 (KST ~17:08 만료). 익일 자동 발행 불가 |
| headful 로그인 필수 | setup은 카카오 OAuth 경유 GM 직접 인증 — 완전 무인 자동화 불가 |
| 공개 API 없음 | 당근 비즈프로필 소식글 업로드 공개 API 미제공 — Playwright 브라우저 자동화만 가능 |
| 딥링크 불가 | 앱 전용 UI, Windows 환경 딥링크 트리거 구조적 불가 |

---

## 3. 선결 과제 (시토 구현 범위)

### 3-1. 에디터 DOM 실측 (필수 선행)

GM이 `--mode setup` 완료 후 headful 세션을 유지한 상태에서 아래 URL의 DOM을 캡처해야 한다.

- 글쓰기 에디터 URL: `https://bizprofile.daangn.com/biz_accounts/2769927/manager/home/` → 소식 작성 버튼 클릭 후 에디터 진입
- 캡처 대상: 제목 입력칸, 본문 텍스트에디터, 이미지 첨부 버튼, 임시저장(draft) 버튼, 발행(publish) 버튼의 CSS selector / XPath

### 3-2. `run_draft()` 구현

파일: `scripts/danggn_upload_playwright.py` — `run_draft()` 함수 (현재 스텁)

구현 내용:
1. Persistent Profile로 브라우저 실행 (`_launch_context` 재사용)
2. 비즈프로필 글쓰기 에디터 진입
3. 제목 자동 입력 (`post.title`)
4. 본문 자동 입력 (`post.body`)
5. 이미지 첨부 (`post.image_paths` 순서대로, 당근 이미지 업로드 DOM 실측 결과 적용)
6. 임시저장(draft) 버튼 클릭
7. 결과 확인 후 텔레그램 보고 (`telegram_report()` 재사용)

### 3-3. `run_publish()` 구현

파일: `scripts/danggn_upload_playwright.py` — `run_publish()` 함수 (현재 스텁)

구현 내용:
1. draft 완료 상태에서 발행 버튼 클릭 (또는 draft → publish 연속 처리)
2. GM go 가드는 이미 구현됨 (`publish_guard_ok()`) — 유지
3. 발행 성공 URL 캡처 후 텔레그램 보고

### 3-4. 세션 갱신 가능성 탐색 (추가 탐색)

draft 실행 후 sessionId 재발급 여부 실측.  
TTL이 연장되면 이중(오전/오후) 발행도 가능해짐 — 확인 후 CEO 보고.

---

## 4. 입력 규격 (CMO 제공, 기존 B안 SOP 그대로)

| 항목 | 경로 | 비고 |
|---|---|---|
| 이미지 | `instagram/{폴더}/output(당근)/*.jpg` | 시모가 콘텐츠 작업 폴더 내 당근용 별도 출력 |
| 카피 | `instagram/{폴더}/danggn_copy.md` | 제목(첫줄) + `---` 구분선 + 본문 형식 |

실행 예시:
```powershell
python scripts\danggn_upload_playwright.py --mode draft `
    --content-dir "instagram\260604_웰페리온_예시"
```

---

## 5. 검증 단계 (순서 엄수)

| 단계 | 명령 | 기준 |
|---|---|---|
| 1. dryrun | `--mode dryrun --content-dir {폴더}` | 제목·본문·이미지 조립 검증 통과 |
| 2. setup | `--mode setup` (headful, GM 직접 실행) | sessionId 발급 확인 |
| 3. check | `--mode check` | 세션 유지 확인 |
| 4. draft | `--mode draft --content-dir {폴더}` | 당근 비즈 임시저장 성공 |
| 5. publish | `--mode publish --i-am-sure --content-dir {폴더}` | **GM 결재 게이트 통과 후에만** 실 발행 |

- draft 성공 확인 전 publish 진행 금지
- publish는 별도 GM go 확인 후 진행

---

## 6. 참조

| 항목 | 경로 |
|---|---|
| R&D 결과 | `scripts/danggn_재도전_R&D.md` |
| 발행 스크립트 | `scripts/danggn_upload_playwright.py` |
| 쿠키 분석 스크립트 | `scripts/check_danggn_cookies.py` |
| Persistent Profile | `profiles/danggn/` |
| 메모리 | `project_danggn_manual_b_confirmed` |

---

## 7. 완료 조건

- [ ] `run_draft()` — 제목/본문/이미지 자동입력 + 임시저장 성공 (실 브라우저 검증)
- [ ] `run_publish()` — 실 발행 성공 (GM go 가드 통과 후 검증)
- [ ] 텔레그램 보고 정상 송출
- [ ] CEO 보고 (세션 갱신 여부 포함)
