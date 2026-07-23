# 점검 월간 리포트 매월1일 텔레그램 자동 — 시토 핸드오프 (배208 Phase C)

작성: 시우(COO) · 2026-07-03 · 배208 3단계(자동화). 텔레그램 발송·스케줄=시토 infra 영역.

## 한 줄
매월 1일, 전월 지원부 점검 월간 리포트를 자동 집계해 **점검관리방 텔레그램에 요약 3~5줄+페이지 링크**를 발송한다. 데이터·콘텐츠는 시우가 완비(monthly_report 라이브), 발송 배선·스케줄만 시토.

## 시우가 완비한 것 (Phase A·B, 라이브)
- GAS `?action=monthly_report&dept=support&month=YYYY-MM` — 집계 완비. 응답: monthTotals{sumTotal,sumDone,avgPct,sessionCount,activeDays,issueCount}·dailySeries·byZone/Shift/Inspector·issues{total,byZone,list}·**improvements[문구]**·denomNote.
- 화면 '월간보고' 탭 + A3 인쇄(지원부 체계.html) — 페이지는 열 때 라이브 fetch라 **별도 '페이지 갱신' 불필요**(자동 최신).

## 시토가 붙일 것 (Phase C)
1. **매월 1일 트리거**(Task Scheduler, 예: Wellperion-Monthly-Check-Report-0900-D1). 전월(YYYY-MM) 계산.
2. **요약 생성**: monthly_report(전월) 호출 → 아래 3~5줄 구성:
   - `📊 [전월] 지원부 점검 월간 리포트`
   - `완료율(잠정) NN% · 세션 NN · 활성 NN일`  ※'잠정'=분모정합 배14 후 확정(현재 서버 today_live 금요일 수리 완료됨→7월부터 정합)
   - `이슈 총 NN건 · 최다 M월DD일(NN건)`
   - `개선시사: {improvements[0]}`
   - `상세: {리포트 페이지 링크}`  (https://wellperion-cao.github.io/wellperion-automation/coo/check/지원부 체계.html → 월간보고 탭. 앵커 가능하면 #tab-monthly)
3. **발송처**: 점검관리방 `-5136037543`(기존 daily_scheduler 패턴·chat_id SSOT .env). 기존 인프라 확장(새 봇/토큰 불필요).

## 경계·주의
- 콘텐츠·집계 의미=시우(배208). 발송·스케줄·infra=시토. 문제 시 텔레그램 소유=시토.
- '잠정' 문구 유지(완료율 신뢰=분모정합 후). 이슈=monthly_report 원문 무가공(지어내기 금지).
- 6월은 테스트기간이라 첫 실발송=8월1일(7월 집계)이 실질 시작. 필요 시 6·7월 수동 1회 테스트.

## 데이터 검증(참고)
- 6월 실측: 완료율 avgPct 81%(잠정)·세션66·활성17일·이슈193·improvements 3문구(f구역 최저70%·6/18 최다33건·70%미만 2일). 라이브 확인됨.
