# 회원 종합 접수처 (QR + 사진) — GM 배포·QR·텔레그램 안내

> 코드는 모두 준비 완료. 아래는 **GM 환경/게이트가 필요한 라이브 단계**입니다.
> 라이브 '이슈 응답' 시트·점검 GAS 는 건드리지 않습니다(VOC 는 완전 별도).

## 산출물 (레포 준비 완료)
| 파일 | 역할 |
|---|---|
| `coo/voc/apps_script_voc.js` | VOC 전용 백엔드 GAS (submit·list·update·사진 base64→Drive·텔레그램 알림) |
| `coo/reception/reception_block.html` | 회원용 모바일 폼 정본 (워드프레스 ko/reception 주입 소스. QR `?loc=` 프리필, 다크·모바일) |
| `coo/check/운영부 체계.html` ▸ VOC 탭 | 운영부 현황 보드(접수/처리중/완료 칸반 + 담당배정·상태전환) |

---

## 데이터 저장 위치

**운영부 시트 (`1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ`) 한 곳에 통합.**
카테고리별 탭이 자동 생성됨:

| 탭 이름 | 유형 |
|---|---|
| `접수_분실물` | 분실물 접수 |
| `접수_시설고장` | 시설물 고장 접수 |
| `접수_청결` | 청결 이슈 접수 |
| `접수_칭찬` | 직원·강사 칭찬 |
| `접수_쓴소리` | 직원·강사 쓴소리 |

> 기존 구글폼(분실물·시설물고장·청결)은 **은퇴** — 신규 접수는 종합접수처로 단일화. 옛 폼의 기존 응답 데이터는 원래 탭에 아카이브 보존.
> ⚠️ 휴회 접수는 ERP에서 **폐지**(브로제이로 이관). `접수_휴회` 탭이 시트에 남아 있으면 GM이 구글시트에서 수동 삭제(라이브 데이터 자동삭제는 안전상 미수행 — 미배포로 데이터 없을 가능성 높음).

---

## GM 설정 액션 (라이브화 필수)

### 1) VOC 전용 GAS 프로젝트 생성·배포
1. https://script.google.com → **새 프로젝트**. (점검·업무 GAS 와 **별도 프로젝트** — 절대 같은 스크립트에 얹지 말 것)
2. `coo/voc/apps_script_voc.js` 전체 내용을 `Code.gs` 에 붙여넣기.
3. **프로젝트 설정 → 스크립트 속성**에서 아래 키 등록:

| 속성 키 | 값 |
|---|---|
| `SPREADSHEET_ID` | `1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ` |
| `TELEGRAM_BOT_TOKEN` | 봇 토큰 (기존 점검 GAS 봇 재사용 가능) |
| `TELEGRAM_CHAT_ID` | 핵심멤버방 chat_id |

4. **배포** → *새 배포* → 유형 **웹 앱** → 실행 계정 **나(cao@wellperion.com)**, 액세스 **모든 사용자** → 배포.
5. 발급된 `/exec` URL 복사.

> ⚠️ `/exec` 반영은 **새 버전 재배포** 필요. 코드만 저장해선 라이브에 반영되지 않음.

### 2) /exec URL 폼에 입력 (placeholder 교체)
배포 후 받은 `/exec` 주소로 `reception_block.html` 안의 `VOC_API` 변수를 교체:
- `coo/reception/reception_block.html` — `var VOC_API = '여기';`

> 교체 후 `scripts/wordpress_admin_playwright.py --mode draft-reception` 으로 워드프레스 재주입 + 커밋·푸시.

### 3) 모바일 폼 라이브 호스팅
폼은 워드프레스 `ko/reception` 페이지에 직접 주입됨 (`reception_block.html` → WP 8434):
`http://wellperion.com/ko/reception/`

위치별 QR 은 여기에 `?loc=` 만 붙이면 됨.

---

## 익명 접수 정책

**쓴소리(voice) 카테고리에서 '익명 희망'을 체크하면 이름·연락처 입력 생략 가능.**
시트에는 '익명'으로 저장됨. 나머지 카테고리는 기존대로 이름·연락처 필수.

---

## 위치별 QR 생성·비치

| 위치 | QR URL |
|---|---|
| 리셉션 | `http://wellperion.com/ko/reception/?loc=리셉션` |
| 락커룸 | `http://wellperion.com/ko/reception/?loc=락커룸` |
| 운동장(헬스장) | `http://wellperion.com/ko/reception/?loc=헬스장` |
| 주차장 | `http://wellperion.com/ko/reception/?loc=주차장` |

QR 생성: qr-code-generator.com 등에 URL 입력 → PNG 다운로드.
비치처: 리셉션 데스크·남/녀 락커룸 입구·헬스장 게시판·주차장 정산기 옆. A6 코팅 카드 권장.

---

## 후속 과제 (이번 차단 아님)

- **무인증 공개 엔드포인트·사진 공개 링크 = 변조·스팸·개인정보 위험.** 최소 hidden token(`VOC_SUBMIT_TOKEN`) + rate-limit + 사진 접근 제한을 후속 적용.
