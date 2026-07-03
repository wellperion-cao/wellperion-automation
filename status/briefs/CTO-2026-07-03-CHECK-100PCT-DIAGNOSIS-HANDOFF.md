# 점검현황 100% 도배 버그 — 시토→시우(COO) 진단 인계

- **작성:** 시토(CTO) 2026-07-03 · **소유 이관:** 시우(COO) · **연결 배:** ship14 `COO-2026-06-25-CHECK-DENOM-UNIFY`
- **발효 게이트:** 라이브 점검 GAS = GM go (로컬검증 후 1회배포·역롤백)

## 1. 증상 (GM 확인 2026-07-03)
점검관리방 텔레그램 "오늘의 점검현황"이 모든 회차 완료수=예정수로 100% 도배:
- 남: 오전 25/25 · 오후 14/14 · 마감 14/14
- 여: 오전 24/24 · 오후 15/15 · 마감 13/13
- GM: "분모랑 분자가 같은 적이 없는데 그냥 다 같게 100%로 채워짐" (요일 따라 예정수만 달라짐)

## 2. 발송/파이썬 측 = 정상 (버그 아님)
`telegram_bot/daily_scheduler.py`
- `_build_digest_check` / `_build_support_check_chart` = today_live의 done/total을 **그대로 표시**만. total=0 guard(`if total else "-"`) 정상.
- 즉 파이썬은 소스가 주는 숫자를 왜곡 없이 렌더. 문제는 **소스(GAS)**.

## 3. 데이터 소스 = 점검 GAS `today_live`
- 엔드포인트: `SUPPORT_CHECK_API_URL` `?action=today_live&dept=support`
- 소스: `.deploy-check/지원팀 일일점검.js` → `handleTodayLive` / `_buildTodayMaster`

### 라이브 실측 (2026-07-03 오전, 시토)
`today_live` → `total=0, done=0, pct=0, schedType=weekday, dow=5`
→ 평일인데 분모(`_buildTodayMaster`)가 **오늘 항목 0개**. 분모 산출도 흔들리는 상태(sched 요일/격주 필터 과다배제 의심).

## 4. 코드 소재 (handleTodayLive)
- 분자(done): `_getCheckLedger` cr 원장 presence로 계상.
- 분모(total): `_buildTodayMaster`(항목시트 × 시프트 presence)로 계상.
- **★용의 1 — 'all'(공용) 강제 동일:** `totalByG.all[b] = doneByG.all[b]` (주석 "gender=all 원장: 분자=분모, 항상 100%"). 이 'all' 버킷이 남+여+all **합계**에 더해져 종일 완료율을 100%로 끌어올림.
- **★용의 2 — 안전장치 클램프:** `if (totalByG[g][b] < doneByG[g][b]) totalByG[g][b] = doneByG[g][b]` → 완료율이 100% **밑으로 내려갈 수 없는 구조**.
- **★핵심 확인 필요(시우):** 남/여 per-gender까지 done==total(25/25)로 나오는 건 위 두 지점만으론 설명 안 됨 → `_getCheckLedger`의 cr 원장이 **예정 항목 전체를 '체크됨'으로 반환**하는지(원장 시딩/복원 문제)를 파고들 것. 이게 per-gender 100%의 진짜 뿌리로 의심.

## 5. 수리 방향 (제안)
1. 분자 = **실제 체크 원장만** 반영(예정 항목 자동 '체크됨' 오염 제거).
2. 분모 = 마스터 유지(단, 평일 0개 반환 원인=sched 필터 동반 점검).
3. 'all' 강제동일 + 안전장치 클램프 재검토: 100% **상한**은 유지하되 **하한 왜곡**(강제 100%) 제거.
4. 화면(`collectDashboardData`)과 today_live 분모 단일화(ship14 4단계)와 함께 처리.
5. 로컬 노드 모의검증 → 라이브 1회 배포 + 역롤백 대기.
