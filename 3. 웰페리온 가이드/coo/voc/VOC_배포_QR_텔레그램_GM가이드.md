# 회원 셀프 VOC (QR + 사진) — GM 배포·QR·텔레그램 안내

> 코드는 모두 준비 완료. 아래는 **GM 환경/게이트가 필요한 라이브 단계**입니다.
> 라이브 '이슈 응답' 시트·점검 GAS 는 건드리지 않습니다(VOC 는 완전 별도).

## 산출물 (레포 준비 완료)
| 파일 | 역할 |
|---|---|
| `coo/voc/apps_script_voc.js` | VOC 전용 백엔드 GAS (submit·list·update·사진 base64→Drive·텔레그램 알림) |
| `coo/voc/voc_mobile_form.html` | 회원용 모바일 폼 (QR `?loc=` 프리필, 다크·모바일) |
| `coo/check/운영부 체계.html` ▸ VOC 탭 | 운영부 현황 보드(접수/처리중/완료 칸반 + 담당배정·상태전환) |

---

## P1·P3 라이브화 — GM이 할 일

### 1) VOC 전용 GAS 프로젝트 생성·배포 (필수)
1. https://script.google.com → **새 프로젝트**. (점검·업무 GAS 와 **별도 프로젝트** — 절대 같은 스크립트에 얹지 말 것)
2. `coo/voc/apps_script_voc.js` 전체 내용을 `Code.gs` 에 붙여넣기.
3. **컨테이너 시트 연결**: 이 스크립트는 `SpreadsheetApp.getActiveSpreadsheet()` 를 씀.
   → VOC 데이터를 적재할 **구글 시트를 하나 열고**, 그 시트의 *확장 프로그램 → Apps Script* 로 들어가 코드를 붙이면 자동 연결됨.
   (라이브 '이슈 응답' 시트가 아닌 **별도/신규 시트** 권장. 탭 「회원셀프VOC」는 첫 제출 시 자동 생성됨.)
4. **배포** → *새 배포* → 유형 **웹 앱** → 실행 계정 **나(cao@wellperion.com)**, 액세스 **모든 사용자**(회원 로그인 불필요) → 배포.
5. 발급된 `/exec` URL 복사.

### 2) /exec URL 3곳에 입력 (placeholder 교체)
배포 후 받은 `/exec` 주소로 아래 `__VOC_GAS_EXEC_URL__` 를 교체:
- `coo/voc/voc_mobile_form.html` — `var VOC_API = '__VOC_GAS_EXEC_URL__';`
- `coo/check/운영부 체계.html` — `const VOC_API = '__VOC_GAS_EXEC_URL__';`

> 교체는 메모장 편집 후 커밋, 또는 SSOT 편집 페이지로 진행. (재배포 ≠ push — clasp 미연동이므로 GAS 코드는 GM이 콘솔에 직접 반영)

### 3) (권장) 모바일 폼 라이브 호스팅
- `voc_mobile_form.html` 은 GitHub Pages 로 자동 노출됨:
  `https://wellperion-cao.github.io/wellperion-automation/coo/voc/voc_mobile_form.html`
- 위치별 QR 은 여기에 `?loc=` 만 붙이면 됨(아래 P4).

---

## P4 — 텔레그램 알림 (코드 완료, GM 설정만)

신규 VOC 접수 시 **핵심멤버방** 자동 알림이 코드에 내장됨(`_vNotifyTelegram`).
GAS 프로젝트 설정 → **스크립트 속성**에 아래 2개 등록 (값은 repo 에 두지 않음 · 서버측 보관):

| 속성 키 | 값 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 봇 토큰 (점검 GAS 와 동일 봇 재사용 가능) |
| `TELEGRAM_CHAT_ID` | 핵심멤버방 chat_id |

> 미설정이어도 접수 자체는 정상 동작(알림만 생략).
> chat_id 확인: 봇을 방에 초대 후 `https://api.telegram.org/bot<토큰>/getUpdates` 의 `chat.id`.

---

## P4 — 위치별 QR 생성·비치 (GM)

### QR 가 가리킬 URL (위치별 `?loc=`)
| 위치 | QR URL |
|---|---|
| 리셉션 | `…/coo/voc/voc_mobile_form.html?loc=리셉션` |
| 락커룸 | `…/coo/voc/voc_mobile_form.html?loc=락커룸` |
| 운동장(헬스장) | `…/coo/voc/voc_mobile_form.html?loc=헬스장` |
| 주차장 | `…/coo/voc/voc_mobile_form.html?loc=주차장` |

(앞부분 `…` = `https://wellperion-cao.github.io/wellperion-automation`)
한글 `?loc=` 는 브라우저가 자동 인코딩하므로 그대로 적어도 동작. QR 생성기에 넣을 땐 인코딩된 형태로 넣어도 무방.

### QR 생성 방법 (택1)
- **무료 생성기**: qr-code-generator.com 등에 위 URL 입력 → PNG 다운로드.
- **구글 차트 API**(즉석): `https://api.qrserver.com/v1/create-qr-code/?size=600x600&data=<URL인코딩>`
- 위치마다 별도 QR(서로 다른 `?loc=`) — 접수 시 위치가 자동 채워져 분류가 쉬움.

### 비치처
리셉션 데스크 · 남/녀 락커룸 입구 · 운동장(헬스장) 게시판 · 주차장 정산기 옆.
A6 코팅 카드 + "불편/건의는 QR 스캔 한 번으로" 안내 문구 권장.

---

## 후속 과제 (이번 차단 아님 · 명시만)
- **무인증 공개 엔드포인트 = 변조·스팸 위험.** 최소 hidden token(`VOC_SUBMIT_TOKEN`) + rate-limit 을 후속 적용.
  (현재 코드는 토큰 게이트 미적용 — 폼 제출 누구나 가능. 운영 시작 후 스팸 관측되면 즉시 토큰화.)
- 사진 Drive 용량 누적 → 주기적 정리 정책(업무 GAS `todo_orphan_cleanup` 패턴 이식 가능).
