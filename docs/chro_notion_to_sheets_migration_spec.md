# CHRO 인사 운영 허브 — Notion → Google Sheets 이관 기술명세

> 역설계 출처: `3. 웰페리온 가이드/chro/hub/index.html` (1645줄) 단독 정독.
> GAS 소스(`NOTION_FN`)는 로컬 미존재 → 프론트가 보내는 요청·기대 응답으로부터 백엔드 계약을 추론.
> **목표: 프론트 index.html 수정 최소화** — GAS 내부만 Notion API → Sheets read/write로 교체.
> 데드라인: **2026-06-07(일) Notion 구독 종료**.

---

## 0. 핵심 요약 (보고용)

| 항목 | 값 |
|---|---|
| GAS action 수 (write) | **5개** — register / resign / schedule-interview / update-interview / hire-complete |
| GAS action 수 (read) | **1개** (`db` 파라미터 기반, 6개 DB 공용) + 게이트 인증 1개(`db:"emp"` 재사용) |
| 시트 탭 수 | **6개** (emp·hire·appl·onbo·eval·exit) + 기존 매출보고서 시트(현재근무자/퇴사자) 연동 |
| 민감(Data Boundary) 필드 수 | **9종** (주민번호·생년월일·급여 범위·연락처·이메일·평가 총점/등급·피드백·면담 내용·퇴사 사유) |
| GM이 export할 DB 수 | **6개** (전 DB CSV/시트 복사) |
| 매출보고서 시트 이중기록 action | **3개** (register · resign · hire-complete) |

---

## 1. 프론트 ↔ GAS 통신 계약 (공통)

### 1.1 엔드포인트
```
NOTION_FN = https://script.google.com/macros/s/AKfycby…SSHQ/exec
```
모든 호출은 `POST` + `Content-Type: text/plain;charset=utf-8` (CORS preflight 회피용 — GAS doPost 라우팅). 본문은 JSON 문자열.

### 1.2 인증 모델
- 게이트 진입 시 `{db:"emp", password:pw}` POST → 응답 `{role:"admin"|"viewer", results:[...]}`.
- 인증 판정(프론트): `status===401` 이거나 `gateData.error`에 unauthorized/권한/비밀번호 정규식 매치, **또는 `gateData.role`이 없으면** 거부.
- 즉, **read 응답에는 반드시 `role` 키가 있어야 함** (없으면 프론트가 미인증으로 간주).
- read 호출 payload: `{db, password}`. write 호출 payload: `{action, adminPassword, …}`.
- `viewer`는 모든 write 버튼이 렌더되지 않음(프론트 `SESSION_ROLE==="admin"` 가드). GAS도 write action에서 `adminPassword` 검증 후 비관리자면 `status 401 + {error}` 반환해야 함.

### 1.3 read 응답 envelope
```js
extractResults(raw):
  raw.results (배열) || raw (배열 자체) || []
```
→ GAS read는 `{role, results:[ {…행…}, … ]}` 형태. 행은 **평탄화된 단일 객체**(중첩 Notion property 구조 아님).

### 1.4 프론트가 의존하는 3대 인코딩 규칙 (GAS가 반드시 재현)
| 규칙 | 프론트 코드 | 의미 | 시트 이관 시 |
|---|---|---|---|
| **날짜** | `dt(r,f)=r["date:"+f+":start"]` | Notion date property를 `date:<필드명>:start` 키로 평탄화 | 시트는 컬럼 1개(`입사일` 등)에 ISO 문자열 저장 → GAS read 시 `date:입사일:start` 키로 재포장 |
| **관계(relation)** | `parseArr(field)` → URL 배열 → `normId(url)` 32hex 추출 → emp명 매핑 | relation은 **연결 대상의 Notion page URL 배열** | 시트는 관계를 **연결 대상 키(emp ID 또는 성명)** 로 저장. GAS read 시 가짜 URL(`…/{32hex}`) 또는 성명 배열로 재포장 |
| **체크박스** | `isYes(v)= v==="__YES__"\|\|v===true\|\|v==="true"` | true는 `"__YES__"` 센티넬 | 시트 TRUE/`Y`/`O` → GAS read 시 `"__YES__"` 로 치환 |
| **page url** | `r.url` (각 행) | Notion 페이지 URL. relation·식별자·"Notion ↗" 링크에 사용 | 시트 행마다 고유 `id`(uuid/행키) 부여 → `url` 자리에 `…/{id}` 합성 |

> **이관 핵심**: 시트 컬럼 평면 구조라도 GAS read 함수가 위 4개 규칙대로 **출력 모양만 유지**하면 프론트는 무수정 동작한다.

---

## 2. DB별 데이터 모델 (역설계)

각 DB에서 프론트가 **읽는(R)** 필드와 모달이 **쓰는(W)** 필드. `[date]`=Notion date(평탄화), `[rel]`=relation(URL배열), `[chk]`=checkbox(`__YES__`), `[url]`=page url, 그 외 text/select/number.

### 2.1 임직원 명부 (`emp`)
| 필드(노션 prop명) | 타입 | R/W | 비고 |
|---|---|---|---|
| `성명` | title | R/W | empNameByUrl 매핑 키 |
| `부서` | select | R/W | 차트 groupCount, register/hire-complete W |
| `소속` | select | R/W | 검색·필터 |
| `직급` | text | R/W | |
| `고용 형태` | select | R/W | 정규/계약/파트타임/파트너 |
| `재직 상태` | select | R/W | 수습중/재직중/휴직중/퇴사. resign 시 "퇴사"로 |
| `입사일` | `[date]` | R/W | `date:입사일:start` |
| `연락처` | text(전화) | R/W | **민감** |
| `이메일`(G메일) | text | W | register payload `email` |
| `계약 만료일` | `[date]` | R | `date:계약 만료일:start` — 대시보드 60일 임박 알림 |
| `url` | `[url]` | R | relation 해석·퇴사처리 타겟(employeePageId) |
| 주민번호 | text | (미표시) | **민감** — 시트엔 존재하나 UI 미노출. 모달 경고: 자동입력 안됨, 시트 수기 |
| 생년월일 | `[date]` | (미표시) | **민감** |
| 근무시간 | text | (미표시) | 모달 경고: 시트 수기 |

### 2.2 채용 공고 (`hire`)
| 필드 | 타입 | R | 비고 |
|---|---|---|---|
| `포지션명` | title | R | |
| `채용 상태` | select | R | 공고 준비/공고중/서류심사/면접 진행/처우 협의/채용 완료/보류 |
| `채용 유형` | select | R | |
| `부서` | select | R | |
| `우선순위` | select | R | 긴급/높음/보통/낮음 |
| `모집 인원` | number/text | R | |
| `지원자 수` | number | R | |
| `면접자 수` | number | R | |
| `급여 범위` | text | R | **민감** |
| `공고 시작일` | `[date]` | R | |
| `공고 마감일` | `[date]` | R | 대시보드 마감 경과 알림 |
| `채용 채널` | `[rel]` 또는 multi | R | `parseArr().join(", ")` |
| `담당 C-Level` | `[rel]` 또는 multi | R | |
| `주요 업무` | rich text | R | whitespace pre-wrap |
| `url` | `[url]` | R | 지원자 `연결 공고` 매칭 키(`normId`) |

### 2.3 지원자 트래킹 (`appl`)
| 필드 | 타입 | R/W | 비고 |
|---|---|---|---|
| `지원자명` | title | R | |
| `지원 포지션` | text | R | |
| `전형 단계` | select | R/W | 서류 검토/1차 면접/2차 면접/최종 합격/보류/불합격. schedule·update·hire-complete가 W |
| `면접 평점` | select | R/W | A~F/미평가. update-interview W |
| `연결 공고` | `[rel]` | R | jobItem이 `normId(공고url)` 매칭 |
| `연락처` | text | R | **민감** |
| `이메일` | text | R | **민감** |
| `지원일` | `[date]` | R | |
| `면접 일정` | `[date]` | R/W | schedule-interview W |
| `담당 면접관` | text | R/W | schedule-interview W |
| `메모` | rich text | R/W | 평가지 "이력 요약"·update note append·hire-complete "입사 완료" 표시 |
| `url` | `[url]` | R | 모든 write의 `applicantPageId` |

### 2.4 온보딩 체크리스트 (`onbo`)
| 필드 | 타입 | R | 비고 |
|---|---|---|---|
| `체크 항목` | title | R | |
| `카테고리` | select | R | 서류·계약/시스템 접근/시설·장비/교육·OT/조직 적응 |
| `완료 여부` | `[chk]` | R | `isYes` |
| `대상 신입 직원` | text/rel | R | |
| `담당자` | text | R | |
| `완료 기한` | `[date]` | R | |

> 현재 write 액션 없음(읽기 전용 대시보드). 신규 입사자 발생 시 항목 생성은 수동.

### 2.5 인사평가 (`eval`)
| 필드 | 타입 | R | 비고 |
|---|---|---|---|
| `평가명` | title | R | `[제외…` 접두 시 UI 숨김 |
| `평가 등급` | select | R | A/B/C |
| `평가 종류` | select | R | 직원평가/상호평가/리더십평가/자체평가 |
| `평가 주기` | select | R | 월간/분기/반기/연간 |
| `총점` | number | R | **민감** |
| `대상자` | `[rel]` | R | resolveRel → emp명 |
| `평가자` | text | R | |
| `평가 기간` | `[date]` | R | |
| `가산점` | number/text | R | |
| `포상 여부` | `[chk]` | R | |
| `포상 내역` | text | R | |
| `피드백` | rich text | R | **민감**(평가 원문) |

> write 액션 없음(읽기 전용).

### 2.6 퇴사 처리 (`exit`)
| 필드 | 타입 | R/W | 비고 |
|---|---|---|---|
| `처리 건명` | title | R/W | resign 시 생성 |
| `퇴사 유형` | select | R/W | 자진 퇴사/계약 만료/권고 퇴사/해고 |
| `처리 완료 여부` | `[chk]` | R | |
| `연결 임직원` | `[rel]` | R/W | resolveRel → emp명. resign이 employeePageId로 연결 |
| `최종 근무일` | `[date]` | R/W | resign payload `lastDay` |
| `퇴사 신청일` | `[date]` | R | |
| `퇴사 사유` | text | R/W | **민감**. resign `reason` |
| `퇴사 면담 여부` | `[chk]` | R | |
| `장비 반납 여부` | `[chk]` | R | |
| `시스템 계정 회수` | `[chk]` | R | |
| `퇴직금 지급 여부` | `[chk]` | R | **민감** |
| `면담 내용` | rich text | R | **민감** |

---

## 3. 액션 카탈로그 (5 write + 1 read)

### A0. read (DB 조회 / 게이트)
- **payload**: `{db:"emp"|"hire"|"appl"|"onbo"|"eval"|"exit", password}`
- **응답**: `{role:"admin"|"viewer", results:[행…]}` (게이트는 `db:"emp"` 재사용; 권한 실패 시 401 또는 `{error}` + role 없음)
- **부수효과**: 없음(읽기). 3회 재시도·22초 타임아웃·localStorage 캐시(프론트).

### A1. register — 신규 입사자 등록 (`openHireModal`)
- **payload**: `{action:"register", adminPassword, name, sosok, dept, rank, empType, status, joinDate, phone, email}`
- **기대 응답**: `{ok:true, notionRoster:true, notionMsg, sheet:{attempted, ok, msg}}`
  - 실패 시 `{ok:false, error|notionMsg}` 또는 401.
- **부수효과**: ① **임직원 명부(emp) 행 추가** ② **매출보고서 "현재근무자" 시트 행 추가**(sheet.attempted). 주민번호·생년월일·근무시간은 미입력(경고).

### A2. resign — 퇴사 처리 (`openResignModal`)
- **payload**: `{action:"resign", adminPassword, employeePageId, employeeName, lastDay, exitType, reason}`
- **기대 응답**: `{ok:true, name, exitRecord:true|false, exitRecordMsg, sheet:{attempted, ok, msg}}`
- **부수효과**: ① **emp `재직 상태`→"퇴사"** ② **exit DB 레코드 생성**(`연결 임직원`=employeePageId) ③ **매출보고서 현재근무자→퇴사자 이동**(sheet.attempted).

### A3. schedule-interview — 면접 일정 등록 (`openScheduleModal`)
- **payload**: `{action:"schedule-interview", adminPassword, applicantPageId, stage, interviewDate, interviewer}`
- **기대 응답**: `{ok:true}` (실패 `{ok:false,error}`)
- **부수효과**: appl `전형 단계`→stage(1차/2차), `면접 일정`=interviewDate, `담당 면접관`=interviewer. **시트 이중기록 없음**.

### A4. update-interview — 면접 평가 등록 (`openInterviewEvalModal`)
- **payload**: `{action:"update-interview", adminPassword, applicantPageId, grade, nextStage, note}`
- **기대 응답**: `{ok:true}`
- **부수효과**: appl `면접 평점`=grade(A~F), `전형 단계`=nextStage, `메모`에 note append. **시트 없음**.

### A5. hire-complete — 입사 확정 (`openHireCompleteModal`)
- **payload**: `{action:"hire-complete", adminPassword, applicantPageId, name, dept, sosok, rank, empType, joinDate}`
- **기대 응답**: `{ok:true, empPage:true|false, empPageMsg, sheet:{ok, msg}}`
- **부수효과(3중)**: ① **emp 신규 페이지 생성** ② **매출보고서 현재근무자 시트 행 추가** ③ **지원자(appl) 메모에 "입사 완료" 표시**.

> **응답 형태 일관성 주의**: 프론트는 register/resign/hire-complete에서 `data.sheet.ok`·`data.sheet.msg`·`data.notionRoster`·`data.empPage`·`data.exitRecord` 등 **세부 필드명을 그대로 참조**해 성공/실패 라인을 그린다. GAS 재작성 시 이 키 이름을 **반드시 유지**해야 한다(아래 §4 시그니처 참조).

---

## 4. 구글시트 6탭 스키마 제안

> 동일 스프레드시트(예: `웰페리온 인사 마스터`)에 6탭. 1행=헤더(노션 prop명 그대로 → GAS 매핑 단순). 첫 컬럼 `id`(고유키, `url` 합성용).
> 체크박스 컬럼은 TRUE/FALSE 또는 `O`/공백. 날짜는 `YYYY-MM-DD` 텍스트.

### 4.1 `emp` 탭
`id | 성명 | 부서 | 소속 | 직급 | 고용 형태 | 재직 상태 | 입사일 | 연락처 | 이메일 | 계약 만료일 | 주민번호 | 생년월일 | 근무시간`
- relation 없음. `url`=`내부키합성(id)`.

### 4.2 `hire` 탭
`id | 포지션명 | 채용 상태 | 채용 유형 | 부서 | 우선순위 | 모집 인원 | 지원자 수 | 면접자 수 | 급여 범위 | 공고 시작일 | 공고 마감일 | 채용 채널 | 담당 C-Level | 주요 업무`
- `채용 채널`·`담당 C-Level`은 콤마 구분 텍스트 → GAS read에서 `parseArr` 호환되게 JSON 배열 문자열 또는 단일 문자열로.

### 4.3 `appl` 탭
`id | 지원자명 | 지원 포지션 | 전형 단계 | 면접 평점 | 연결 공고(hire.id) | 연락처 | 이메일 | 지원일 | 면접 일정 | 담당 면접관 | 메모`
- `연결 공고`=hire 탭의 id 값 저장 → GAS read 시 `…/{hire.id}` URL 배열로 합성(프론트 `normId` 매칭).

### 4.4 `onbo` 탭
`id | 체크 항목 | 카테고리 | 완료 여부 | 대상 신입 직원 | 담당자 | 완료 기한`

### 4.5 `eval` 탭
`id | 평가명 | 평가 등급 | 평가 종류 | 평가 주기 | 총점 | 대상자(emp.id) | 평가자 | 평가 기간 | 가산점 | 포상 여부 | 포상 내역 | 피드백`
- `대상자`=emp.id → read 시 `…/{emp.id}` URL 배열로(resolveRel → 성명).

### 4.6 `exit` 탭
`id | 처리 건명 | 퇴사 유형 | 처리 완료 여부 | 연결 임직원(emp.id) | 최종 근무일 | 퇴사 신청일 | 퇴사 사유 | 퇴사 면담 여부 | 장비 반납 여부 | 시스템 계정 회수 | 퇴직금 지급 여부 | 면담 내용`

### 4.7 기존 매출보고서 시트 — **이중기록 지점 (이미 존재)**
- "현재근무자" 시트 / "퇴사자" 시트 2개 탭.
- register·hire-complete → 현재근무자 행 추가. resign → 현재근무자 행 삭제+퇴사자 행 추가.
- **이관 후에도 유지**: GAS가 emp 탭과 매출보고서 시트를 **동시 갱신**(트랜잭션 아님 — 부분 실패 시 `sheet.ok=false` 보고). 컬럼 매핑(성명·부서·소속·입사일 등)은 매출보고서 시트 기존 헤더에 맞춰 GAS 내부 매핑 테이블로 관리.

---

## 5. 새 GAS 함수 명세 (Notion → Sheets, 프론트 계약 불변)

> `doPost(e)`에서 `body=JSON.parse(e.postData.contents)` 후 `body.action` 없으면 read, 있으면 write 라우팅. `ContentService.createTextOutput(JSON.stringify(res)).setMimeType(JSON)` 반환. 401은 GAS가 status를 못 바꾸므로 **body `{error}` + role 누락**으로 표현(프론트가 이미 이중 검사함).

```text
// ── 공통 ──
SHEET_ID = "<인사 마스터 스프레드시트 ID>"
SALES_SHEET_ID = "<매출보고서 스프레드시트 ID>"
ADMIN_PW, VIEWER_PW = PropertiesService (기존 NOTION_TOKEN 자리 대체)

readSheet(tabName) -> rows[]
  values = Sheet.getDataRange().getValues()
  header = values[0]; 각 행을 {header[i]: cell} 객체로
  변환규칙:
    - 날짜형 헤더(입사일/계약 만료일/지원일/면접 일정/공고*/완료 기한/최종 근무일/퇴사 신청일/평가 기간)
        → 추가키 row["date:"+h+":start"] = isoOrEmpty(cell)
    - 체크박스 헤더(완료 여부/포상 여부/처리 완료 여부/*여부/시스템 계정 회수)
        → row[h] = truthy(cell) ? "__YES__" : ""
    - 관계 헤더(연결 공고/대상자/연결 임직원/채용 채널/담당 C-Level)
        → row[h] = splitToUrlArray(cell)   // [".../{id}", ...]
    - row.url = SHEET_BASE + "/" + row.id   // normId가 32hex 추출 가능한 형태 권장
  반환 rows

// ── READ (action 없음) ──
handleRead(body):
  pw=body.password; role = pw===ADMIN_PW?"admin": pw===VIEWER_PW?"viewer": null
  if(!role) return {error:"unauthorized"}        // role 누락 = 프론트가 거부
  return { role, results: readSheet(body.db) }    // db ∈ emp/hire/appl/onbo/eval/exit

// ── WRITE 공통 가드 ──
requireAdmin(body): if(body.adminPassword!==ADMIN_PW) return {error:"관리자 비밀번호 오류"} (role 미포함)

// A1 register(body) -> {ok, notionRoster, notionMsg, sheet:{attempted,ok,msg}}
//   appendRow(emp, {성명:name,부서:dept,소속:sosok,직급:rank,고용형태:empType,
//                   재직상태:status,입사일:joinDate,연락처:phone,이메일:email,id:uuid})
//   notionRoster=true (=emp 시트 성공)
//   sheet = appendSalesCurrent({성명,부서,소속,입사일})  // 매출보고서 현재근무자

// A2 resign(body) -> {ok,name,exitRecord,exitRecordMsg,sheet:{attempted,ok,msg}}
//   empRow = findById(emp, employeePageId의 normId)
//   set empRow.재직상태="퇴사"
//   appendRow(exit,{처리건명:name+" 퇴사",퇴사유형:exitType,최종근무일:lastDay,
//                   퇴사사유:reason,연결임직원:employeePageId,id:uuid}) → exitRecord
//   sheet = moveSalesToResigned(name)   // 현재근무자→퇴사자

// A3 scheduleInterview(body) -> {ok}
//   applRow=findById(appl,applicantPageId); set 전형단계=stage,면접일정=interviewDate,담당면접관=interviewer

// A4 updateInterview(body) -> {ok}
//   applRow=findById(appl,applicantPageId); set 면접평점=grade,전형단계=nextStage; 메모 append "\n[면접] "+note

// A5 hireComplete(body) -> {ok,empPage,empPageMsg,sheet:{ok,msg}}
//   appendRow(emp,{성명:name,부서:dept,소속:sosok,직급:rank,고용형태:empType,
//                  재직상태:"재직중",입사일:joinDate,id:uuid}) → empPage
//   sheet=appendSalesCurrent(...)
//   applRow=findById(appl,applicantPageId); 메모 append "\n[입사 완료]"
```

**프론트 무수정 보장 체크포인트**
- read 응답 키: `role`, `results`. ✅
- 행 키: 노션 prop명 그대로 + `date:*:start` + `__YES__` + `url`. ✅
- write 응답 키: `ok`, `error`, `name`, `notionRoster`, `notionMsg`, `exitRecord`, `exitRecordMsg`, `empPage`, `empPageMsg`, `sheet.{attempted,ok,msg}`. ✅
- (선택) index.html 내 사용자 문구 "Notion 임직원 명부"는 표시용 라벨이라 기능 영향 없음 — 추후 "임직원 시트"로 카피 교체 가능(필수 아님).

---

## 6. 민감정보 식별 (Data Boundary)

| # | 필드 | 위치(탭) | UI 노출 | 분류 |
|---|---|---|---|---|
| 1 | 주민번호 | emp | 미노출(시트만) | 고유식별정보 — **최고 민감** |
| 2 | 생년월일 | emp | 미노출 | 개인정보 |
| 3 | 연락처(전화) | emp·appl | 노출 | 개인정보 |
| 4 | 이메일 | emp·appl | 노출 | 개인정보 |
| 5 | 급여 범위 | hire | 노출 | 처우정보 |
| 6 | 총점·평가 등급 | eval | 노출 | 인사평가 |
| 7 | 피드백(평가 원문) | eval | 노출 | 인사평가 — 민감 |
| 8 | 면담 내용 | exit | 노출 | 민감 |
| 9 | 퇴사 사유·퇴직금 지급 여부 | exit | 노출 | 민감 |

**시트 보관 주의점**
1. **접근 권한 분리**: 인사 마스터 스프레드시트는 **GAS 실행 서비스계정 + GM·CHRO 담당 2~3인만** 공유. "링크 있는 모두" 금지. 프론트는 시트에 직접 접근하지 않고 GAS 경유만 하므로, 시트 공유 범위를 **GAS 소유자 계정으로 최소화**.
2. **주민번호**: 가능하면 **별도 잠금 탭/별도 스프레드시트**로 분리하고 허브 GAS read에서 해당 컬럼 제외(현재도 UI 미노출). 평문 저장 시 시트 보호 범위 설정.
3. **마스킹**: read 응답에서 viewer 역할에는 연락처·이메일·총점·피드백·면담 내용을 마스킹(`010-****-1234`)하는 옵션 추가 권장(현재 프론트는 viewer에도 동일 데이터 전달 — 강화 여지).
4. **감사 로그**: write action마다 별도 `_log` 탭에 (timestamp, action, 대상, 실행자) 기록 권장.
5. **PIPA 원칙**(허브 운영 원칙 §4와 일치): 이력서·처우·평가 자료 접근 권한 분리 유지.

---

## 7. GM 수동 액션 — Notion export (DB별)

> Notion 각 DB를 **CSV 또는 "Markdown & CSV"** 로 export → 시트 탭에 붙여넣기. **relation·날짜 컬럼 형식 확인 필수**.

| # | Notion DB | export 형식 | 시트 탭 | 변환 주의 |
|---|---|---|---|---|
| 1 | 임직원 명부 | CSV | `emp` | 주민번호·생년월일·근무시간 컬럼 포함 확인. 날짜 `YYYY-MM-DD`로. **각 행에 고유 id 부여**(추후 relation 매칭 키) |
| 2 | 채용 공고 | CSV | `hire` | `채용 채널`·`담당 C-Level`이 relation/multi면 콤마 텍스트로 평탄화 |
| 3 | 지원자 트래킹 | CSV | `appl` | `연결 공고` relation → **hire의 id 값으로 치환**(공고 제목 기준 수동 매칭). `메모` 줄바꿈 보존 |
| 4 | 온보딩 체크리스트 | CSV | `onbo` | `완료 여부` 체크박스 → TRUE/FALSE |
| 5 | 인사평가 | CSV | `eval` | `대상자` relation → **emp id로 치환**. `[제외…` 접두 평가명 보존(프론트가 필터) |
| 6 | 퇴사 처리 | CSV | `exit` | `연결 임직원` relation → emp id. 4개 체크박스·면담 내용 보존 |

추가: **매출보고서 현재근무자/퇴사자 시트는 이미 구글시트**(export 불필요). emp 탭과 정합성만 확인.

> Notion CSV는 relation을 **"대상 페이지 제목"** 으로 export하므로, GM은 export 후 **제목→id 매핑**을 한 번 수행해야 함(또는 GAS read에서 성명/제목 기준 매칭으로 우회 설계 — id 부여를 생략하고 성명 매칭만 쓰면 GM 작업 감소).

---

## 8. 이관 단계별 체크리스트 (6/07 일요일 데드라인 역순)

**D-3 (6/04~05) — 설계·골격**
- [ ] 인사 마스터 스프레드시트 생성, 6탭 헤더 입력(§4), 권한 최소화(§6-1)
- [ ] 매출보고서 스프레드시트 ID·현재근무자/퇴사자 시트 헤더 확보
- [ ] 기존 GAS 프로젝트에 새 함수 골격 작성(§5), `SHEET_ID`/`ADMIN_PW`/`VIEWER_PW` PropertiesService 설정

**D-2 (6/05~06) — 데이터 이관**
- [ ] **GM: Notion 6개 DB CSV export**(§7) → 6탭 붙여넣기
- [ ] 각 행 `id` 부여, relation 컬럼 id/성명 매칭 정리
- [ ] 날짜·체크박스 형식 정규화(YYYY-MM-DD / TRUE·FALSE)
- [ ] emp ↔ 매출보고서 현재근무자 정합성 대조(재직자 누락·중복 확인)

**D-1 (6/06) — 검증**
- [ ] GAS read 6개 DB: 프론트가 받던 모양(`role`,`results`,`date:*:start`,`__YES__`,`url`) 출력 단위테스트
- [ ] 5개 write action 시뮬레이션(테스트 행으로 register→hire-complete→resign→update/schedule)
- [ ] 매출보고서 동시기록(sheet.ok) 동작 확인
- [ ] **clasp push ≠ 배포** — `/exec` 반영 위해 **새 버전 배포** 수행(기존 NOTION_FN URL 유지되도록 같은 배포 갱신)
- [ ] index.html에서 게이트·6탭·write 모달 전체 E2E(헤더 NOTION_FN URL 무변경 확인)

**D-Day (6/07) — 전환·종료**
- [ ] 운영 데이터 최신본 재export·재반영(주말 변경분 동기화)
- [ ] 프론트 무수정 최종 확인(필요 시 "Notion" 라벨 카피만 교체 — 선택)
- [ ] **Notion 구독 종료 전 최종 백업**(전 DB CSV 아카이브 보관)
- [ ] 구독 해지

**사후**
- [ ] viewer 마스킹·감사 로그(`_log` 탭) 강화(§6-3,4)
- [ ] 주민번호 별도 잠금탭 분리(§6-2)

---

### 부록 A. 프론트가 절대 깨지면 안 되는 키 목록 (회귀 가드)
read 행: `성명·부서·소속·직급·고용 형태·재직 상태·연락처·이메일` / `포지션명·채용 상태·채용 유형·우선순위·모집 인원·지원자 수·면접자 수·급여 범위·채용 채널·담당 C-Level·주요 업무` / `지원자명·지원 포지션·전형 단계·면접 평점·연결 공고·담당 면접관·메모` / `체크 항목·카테고리·완료 여부·대상 신입 직원·담당자` / `평가명·평가 등급·평가 종류·평가 주기·총점·대상자·평가자·가산점·포상 여부·포상 내역·피드백` / `처리 건명·퇴사 유형·처리 완료 여부·연결 임직원·퇴사 사유·퇴사 면담 여부·장비 반납 여부·시스템 계정 회수·퇴직금 지급 여부·면담 내용`
date키: `date:입사일:start·date:계약 만료일:start·date:공고 시작일:start·date:공고 마감일:start·date:지원일:start·date:면접 일정:start·date:완료 기한:start·date:평가 기간:start·date:최종 근무일:start·date:퇴사 신청일:start`
공통: `url`(전 행), 응답 `role`·`results`, write `ok·error·sheet.{attempted,ok,msg}·notionRoster·notionMsg·exitRecord·exitRecordMsg·empPage·empPageMsg·name`
