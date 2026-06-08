# 부서별 현황판 인프라 결과 — 2026-06-08 시토

> 작업 범위: GAS 신규 action 추가 + 이슈대장 시트 탭 신설 인프라. HTML 현황판은 시우 담당.

---

## 1. 엔드포인트

| 구분 | URL |
|---|---|
| **신규 (현황판용)** | `https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec` |
| 기존 (점검앱 유지) | `https://script.google.com/macros/s/AKfycbzcOTihPYfTWQ64rbNMpfgv9p2keav0mcf7x0LrPhHm8nOUIlsqPTwCOumzE-JIcv1F/exec` |

> 기존 `@7` 배포는 그대로 살아있어 시설부 체계·지원부 체계 HTML 기존 점검앱 무손상.  
> 시우가 현황판 HTML을 만들 때 **신규 URL**을 `API_URL`로 사용할 것.

---

## 2. 신규 action 목록

### 2-1. `action=weekly` — 주간 트렌드 집계

| 항목 | 내용 |
|---|---|
| 메서드 | GET |
| 파라미터 | `action=weekly&dept=facility\|support` |
| 응답 봉투 | `{ ok:true, dept, data:[...] }` |

응답 `data` 배열 원소 스키마:

```json
{
  "date": "2026-06-08",
  "total": 58,
  "done": 45,
  "pct": 78
}
```

- 오늘 포함 최근 7일, 날짜 **오름차순** (차트 표시 최적화)
- `dept=facility`: 시설부 전용 탭(`시설_*`) 존재 시 사용, 없으면 기존 탭 폴백
- `dept=support` (기본): 기존 남성구역/여성구역/공용구역 탭

호출 예시:
```
GET ?action=weekly&dept=facility
GET ?action=weekly&dept=support
```

---

### 2-2. `action=issuelog` — 이슈대장 조회

| 항목 | 내용 |
|---|---|
| 메서드 | GET |
| 파라미터 | `action=issuelog&dept=facility\|support[&open=1]` |
| 응답 봉투 | `{ ok:true, dept, open:bool, issues:[...] }` |

`open=1`: 미처리·처리중만 반환 / 생략: 전체

응답 `issues` 배열 원소 스키마:

```json
{
  "id": 1,
  "date": "2026-06-08",
  "zone": "남성 사우나",
  "inspector": "남 오전 주임",
  "issue": "탕 수위 낮음",
  "status": "미처리",
  "resolvedAt": "",
  "note": ""
}
```

`status` 값: `미처리` / `처리중` / `완료`

호출 예시:
```
GET ?action=issuelog&dept=facility          # 시설부 전체
GET ?action=issuelog&dept=support&open=1    # 지원부 미결만
```

---

### 2-3. `action=issuelog_add` — 이슈 등록

| 항목 | 내용 |
|---|---|
| 메서드 | POST |
| Content-Type | `text/plain` (기존 패턴 동일) |

요청 바디:

```json
{
  "action": "issuelog_add",
  "dept": "facility",
  "date": "2026-06-08",
  "zone": "남성 사우나",
  "inspector": "남 오전 주임",
  "issue": "탕 수위 낮음",
  "status": "미처리",
  "resolvedAt": "",
  "note": ""
}
```

응답: `{ ok:true, dept, row }` — `row`는 시트 데이터 행 번호(이후 update 시 사용)

---

### 2-4. `action=issuelog_update` — 이슈 상태 갱신

| 항목 | 내용 |
|---|---|
| 메서드 | POST |
| Content-Type | `text/plain` |

요청 바디:

```json
{
  "action": "issuelog_update",
  "dept": "facility",
  "row": 1,
  "status": "완료",
  "resolvedAt": "2026-06-09",
  "note": "탕 수위 정상화 확인"
}
```

응답: `{ ok:true, dept, row }`

---

## 3. 시트 탭 구조

### 신설 탭 2개

| 탭명 | 부서 | 용도 |
|---|---|---|
| `시설_이슈대장` | 시설부 | 이슈 등록~처리 이력 누적 |
| `지원_이슈대장` | 지원부 | 이슈 등록~처리 이력 누적 |

**컬럼 구조** (7컬럼):

| 등록일 | 구역 | 점검자 | 이슈내용 | 상태 | 처리일 | 비고 |
|---|---|---|---|---|---|---|

> 탭 실제 신설 방법: GAS 에디터에서 `setupIssueLogSheets()` 함수 1회 실행.  
> (현재 탭 미존재 상태 → issuelog GET 시 빈 배열 정상 반환 중)

### 시설부 전용 점검 탭 (선택적 신설)

향후 시설부 점검 데이터를 지원부와 완전 분리하려면 `시설_남성구역` / `시설_여성구역` / `시설_공용구역` 탭 신설 후 데이터 이관. 현재는 `dept=facility` 호출 시 기존 탭 폴백으로 동작.

---

## 4. 검증 결과

| 호출 | 응답 | 비고 |
|---|---|---|
| `?action=weekly&dept=support` | `{ok:true, dept:"support", data:[7개]}` | 실데이터 포함 정상 |
| `?action=weekly&dept=facility` | `{ok:true, dept:"facility", data:[7개]}` | 폴백 탭 사용 정상 |
| `?action=issuelog&dept=support` | `{ok:true, issues:[]}` | 탭 미신설 → 빈배열 정상 |
| `?action=issuelog&dept=facility&open=1` | `{ok:true, issues:[]}` | 탭 미신설 → 빈배열 정상 |
| 기존 점검앱 (`@7` URL) | 무손상 | 기존 배포 유지 확인 |

---

## 5. 시우에게 — 현황판 HTML 연결 방법

```javascript
// 신규 현황판 HTML에서 사용할 URL
const API_URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';

// 주간 트렌드 조회 (시설부 예시)
fetch(API_URL + '?action=weekly&dept=facility', { redirect: 'follow' })
  .then(r => r.json())
  .then(j => { /* j.data = [{date, total, done, pct}, ...] */ });

// 미결 이슈 조회 (지원부 예시)
fetch(API_URL + '?action=issuelog&dept=support&open=1', { redirect: 'follow' })
  .then(r => r.json())
  .then(j => { /* j.issues = [{id, date, zone, inspector, issue, status, ...}] */ });

// 날짜별 집계 (기존 패턴 — 신규 URL에서도 동작)
fetch(API_URL + '?date=2026-06-08', { redirect: 'follow' });
```

> 기존 `date` 파라미터 조회, `items`, `board`, `staff` 등 기존 action도 신규 URL에서 모두 동작.

---

*작성: AI CTO 시토 · 2026-06-08*
