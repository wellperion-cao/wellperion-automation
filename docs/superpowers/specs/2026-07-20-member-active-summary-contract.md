# 멤버십 회원관리 로딩 속도 — 백엔드 요약 액션 계약 (§2-A)

작성: 시포(AI CPO) 2026-07-20 · 상위 지시 `status/briefs/시포_배치_20260720_확정스펙.md` §2-A
대상 구현: backend-sheet (`.deploy-funnel-v2/Survey.js` — R5, `.deploy-funnel/Survey.js`는 죽은 사본 절대 건드리지 말 것)

> **지금은 설계·명세만. 코드 수정 없음.** 이 문서만 보고 backend-sheet가 바로 구현 가능하도록 작성.
> GAS 재배포는 비가역·라이브 즉시 반영 — 구현 완료 후 **배포 전 GM 결재 필수**(§7).

## 0. 문제의 정체 — 지금 뭐가 느린가

`3. 웰페리온 가이드/cpo/member/membership.html`의 회원관리 탭이 열릴 때마다
`member_active_list?scope=valid`(전체 ~1,000행 × ~28열)를 통째로 fetch한다 — 콜드 GAS 기준 **~11초**.

이 응답을 기다려야만 화면에 뜨는 것들이 있다(`renderActiveSummary()`, `membership.html:6477-6507`):

| 화면 요소 | 계산 함수 | 코드 위치 |
|---|---|---|
| 상단 6카드 중 "대기자 회원 관리: 대기 N명" | `_validWaitCnt = _waitMembers().length` → `dMemWait` | `membership.html:6495-6496` |
| 상단 카드4 "단기 N명" 서브라인 | `counts['중단기']` → `dMemShort` | `membership.html:6484-6497` |
| 회원관리 탭 드릴다운 헤더의 유형별 칩(멤버십/입주민/법인/단기/보증금/FAN VIP/기타) | `_validTypeCounts` → `_memberOverviewHtml()` typeChips | `membership.html:6483-6493`, `6452-6458` |
| LOSS 카드 진입 헤더 "LOSS 회원 N" (오늘 §2-B로 신설) | `_activeHeaderInfo()` + `_activeBaseRows().length` (scope=ended 전체 fetch 필요) | `membership.html:6426-6434` |
| 대기자 카드 진입 헤더 "대기자 회원 N" (오늘 §2-C로 신설) | 상동, scope=valid 전체 fetch에서 클라 필터 | 상동 |

**아닌 것(이미 빠름, 손댈 필요 없음):** 상단 카드의 "LOSS 회원 관리: 금일/월간" 숫자, "회원 구성"(유효·법인·종료 + 이번달 신규/LOSS) 블록 — 전부 `cpo_today_stats`(캐시 60초, 이미 서버 집계) 기준이라 `member_active_list`를 안 기다린다(`membership.html:6379-6399`, `6757-6771`).

## 1. 원인 확인 — 서버는 이미 같은 걸 두 번 계산하고 있다

`cpo_today_stats`(`Survey.js:5023-5111`)가 이미 `유효회원` 시트를 한 줄씩 훑어서 `memberActive`/`memberCorp`/`memberEnded`/`todayLoss`/`monthLoss`를 뽑아 60초 캐시로 반환한다. **`member_active_list`가 전체 행(28열×1000행)을 통째로 클라이언트에 넘기는 이유는 오직 "화면에서 몇 가지 숫자를 더 세어야 하기 때문"**이다 — 그 숫자들(유형별 분해·대기자 수·LOSS 건수의 기간별 분해)을 서버가 대신 세어서 작은 응답으로 주면, 카드 표시에는 더 이상 전체 행이 필요 없다.

## 2. 계산 로직 — `cpo_today_stats`와 동일한 유효성 판정 재사용

시트: `MEMBER_SPREADSHEET_ID`(`12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U`) → 시트명 `유효회원`(`MEMBER_SHEET`).
헤더 매칭: 공백/개행 무시 후 부분일치(`_aaIdx`/`_crIdx`와 동일 관례) — `잔여일`, `재등록분류`, `회원\n구분`(또는 `회원구분`), `시작\n일자`(공백 제거 후 `시작일자` 포함), `이탈일`→`해지일`→`종료일`(우선순위, `cpo_today_stats`·`member_active_list`와 완전히 동일한 순서).

```
유효(isValid) 판정 — cpo_today_stats·member_active_list와 100% 동일 공식(재정의 금지):
  잔여일 = parseInt(잔여일칸, 숫자만 남기고)
  재등록분류 ∈ {LOSS, 환불, 양도LOSS} 이면 무조건 무효
  isValid = (잔여일이 숫자) && 잔여일 > 0 && 재등록분류가 위 3종이 아님

typeCounts (isValid=true인 행만, 대기자 포함 — 시작일 미래 여부는 상관없이 카운트):
  v = 회원구분칸 trim, 없으면 '기타'
  오타 정규화: '맴버십'→'멤버십', '멥버십'→'멤버십'   (membership.html:6486 TYPO_MAP과 동일)
  KNOWN = [멤버십, 입주민, 중단기, 보증금, 'FAN VIP']
  v가 KNOWN에 없으면 '기타'로 합산
  → counts[v]++

waitingCount (isValid=true인 행 중):
  시작일자칸 값이 'YYYY-MM-DD...' 형식이고 그 날짜 > 오늘(Asia/Seoul) 이면 카운트
  (membership.html:_isFutureStart와 동일 — 문자열 비교로 충분, Date 파싱 불필요)

endedTotal = isValid=false인 행 수 (= 기존 cpo_today_stats.memberEnded와 반드시 같은 값이어야 함 — 교차검증 포인트)

기간 버킷(day/month/year/total) — 프론트 _mdashPeriodRange(membership.html:3470-3477)와 동일 정의:
  오늘(today)    = Asia/Seoul 기준 YYYY-MM-DD
  day   범위 = [today, today]
  month 범위 = [이번달 1일, today]
  year  범위 = [올해 1월 1일, today]
  total      = 범위 없음(날짜 파싱 없이 무조건 포함) — day/month/year는 날짜를 못 읽으면 그 행 제외(제외 규칙까지 동일해야 함)

  lossPeriods: isValid=false인 행의 "LOSS일자"(이탈일→해지일→종료일 우선순위, 없으면 그 행은 day/month/year에서 제외하되 total에는 포함)가
               각 범위에 드는 건수. total = endedTotal과 반드시 일치.
  waitPeriods: waitingCount 대상 행의 "시작일자"가 각 범위에 드는 건수. total = waitingCount와 반드시 일치.
```

## 3. GAS 액션 (신규 1개)

| 액션 | 인증 | 캐시 |
|---|---|---|
| `member_active_summary` | 공개(읽기, 기존 `member_active_list`/`cpo_today_stats`와 동일 등급) | `CacheService` 60초 (`cpo_today_stats`와 동일 TTL·같은 시트라 신선도 요구도 동일) |

**요청:** `GET ?action=member_active_summary` (파라미터 없음 — scope별로 나누지 않고 한 번에 전부 반환, `cpo_today_stats` 스타일)

**응답 예시** (오늘 실측값 기준 — 실제 배포 시 이 숫자와 100% 일치해야 통과, §5 참조):

```json
{
  "ok": true,
  "action": "member_active_summary",
  "date": "2026-07-20",
  "validTotal": 1006,
  "endedTotal": 704,
  "waitingCount": 26,
  "typeCounts": {
    "멤버십": 868,
    "입주민": 77,
    "중단기": 4,
    "보증금": 47,
    "FAN VIP": 7,
    "기타": 3
  },
  "lossPeriods":  { "day": 0, "month": 21, "year": 0, "total": 704 },
  "waitPeriods":  { "day": 0, "month": 0,  "year": 0, "total": 26 }
}
```

- `lossPeriods.year`/`waitPeriods.year` 예시값이 실제로 0이 나올 수 있음(연초~오늘 범위인데 표본 데이터가 그 안에 없는 경우) — **지어내지 말고 로직대로 계산한 실제값**을 반환. 위 JSON은 필드 존재·타입 예시일 뿐, 승인 기준 숫자가 아니다(§5의 교차검증이 진짜 기준).
- 모든 카운트 필드는 정수. 빈 칸/파싱 실패 행은 조용히 제외(에러 아님).
- `ok:false` 응답 시 프론트는 기존 대기 방식(전체 fetch)으로 폴백 — 이 액션은 "있으면 빠르고, 없어도 안 죽는" 부가 최적화여야 한다.

## 4. 프론트 반영 계획 (지금 하지 않음 — 액션 배포 후 배선 시 참고용)

1. `loadCpoTodayStats()` 옆에 `member_active_summary` 병렬 호출 추가(페이지 init, `membership.html:6656` 부근).
2. 응답 도착 즉시:
   - `dMemWait` ← `waitingCount` (`membership.html:6496` 대체)
   - `dMemShort` ← `typeCounts['중단기']` (`membership.html:6497` 대체)
   - `_validTypeCounts` ← `typeCounts`, `_validTotal` ← `validTotal` (전체 fetch 전에 미리 채워 `_memberOverviewHtml()` 칩이 즉시 뜨게)
   - `_activeHeaderInfo()`/`_activeBaseRows()`가 아직 scope별 전체 fetch가 안 끝난 상태에서 LOSS/대기자 카드에 진입하면, `lossPeriods[_actPeriod]`/`waitPeriods[_actPeriod]`로 즉시 헤더 숫자를 보여주고("잠정" 표기 불필요 — 서버가 이미 신뢰 가능한 정답이므로), 이후 `member_active_list` 응답이 도착하면 `_activeBaseRows().length`로 **재계산해 덮어쓴다**(자기 검증 겸 안전망 — 두 값이 다르면 그 자체가 버그 신호이니 콘솔 경고 남길 것).
3. **`member_active_list` 전체 fetch는 삭제하지 않는다.** 표(목록·검색·정렬·더블클릭 인라인편집·재등록상담/종료사유/담당자 통합셀), 이탈방지 액션 패널(`_capClassify` — 갱신임박·저이용 상위 12건 + 클릭 시 회원 오픈), 담당자 배정 서브탭(`ownerAssign`)은 실제 회원 레코드(이름·전화·rowIndex 등)가 있어야 하는 요소라 계속 전체 fetch에 의존한다. 이 항목들은 **로딩 스피너를 유지한 채 백그라운드로 그대로 이어서 로드** — 카드 숫자만 먼저 뜨고 표는 기존 방식대로 뒤따라온다(완전 지연로드가 아니라 "우선순위 재배치").

## 5. 완료 기준 — 교차검증 (요약 카드 숫자 100% 동일)

- [ ] 배포 후 실제 URL로 `?action=member_active_summary` GET 1회 호출 → 5.의 각 필드가 **같은 시각에 뜬 화면의 클라이언트 계산값**과 전부 일치:
  - `validTotal` == 기존 `cpo_today_stats.memberActive + memberCorp`
  - `endedTotal` == 기존 `cpo_today_stats.memberEnded` == LOSS 카드 클릭 시 `_activeBaseRows().length`(scope=ended, 기간=총)
  - `waitingCount` == 대기자 카드 클릭 시 `_activeBaseRows().length`(scope=valid+waiting, 기간=총)
  - `typeCounts` 6종 == 회원관리 탭 진입 후 콘솔에서 `_validTypeCounts` 덤프값
  - `lossPeriods.month` == LOSS 카드에서 "월" 탭 클릭 후 헤더 숫자
- [ ] 캐시 키에 버전 넣기(`member_active_summary_v1`) — 이후 필드 추가 시 버전만 올리면 옛 캐시가 자동 무효화되게(`cpo_today_stats_v4` 관례 그대로 따름).
- [ ] `ok:false`/응답 실패 시에도 페이지가 죽지 않고 기존 방식(전체 fetch만으로 카드 계산)으로 정상 동작.
- [ ] 표·검색·정렬·인라인편집·이탈방지 패널·담당자 배정 — 전부 회귀 없이 그대로 동작(전체 fetch를 안 지웠으니 원칙적으로 회귀 위험 없음, 그래도 배선 시 실측 확인).

## 6. 배포 게이트

GAS 신규 액션 추가 + 웹앱 재배포는 **비가역·라이브 즉시 반영** → 구현 완료 후 **GM 결재 필수**, `clasp push`만으론 반영 안 됨(R6) — 배포는 반드시
`clasp deploy -i AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo`.
배포 전까지는 코드 작성 + 로컬/스테이징 확인까지만 진행.
