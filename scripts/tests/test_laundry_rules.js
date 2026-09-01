// 세탁물 관리 계산 규칙 자가검사 — 지시서 §11 완료 기준 1~9 (브라우저 없이 순수 함수만 검증)
// 원본 = 라이브 페이지 그 자체. 사본을 두면 페이지가 바뀌어도 시험은 옛 코드를 통과시킨다(약속 L01).
const fs = require('fs'), path = require('path');
const PAGE = path.join(__dirname, '..', '..', '3. 웰페리온 가이드', 'coo', 'check', '지원부 체계.html');
const page = fs.readFileSync(PAGE, 'utf8');
const from = page.indexOf('const LAUNDRY_STORAGE_KEY');
const to = page.indexOf('function wpLdyExportJson');
if (from < 0 || to < 0) { console.error('세탁물 관리 코드 블록을 페이지에서 찾지 못했습니다 — 함수명이 바뀌었는지 확인하세요.'); process.exit(1); }
const src = page.slice(from, page.indexOf('}', page.indexOf('document.body.removeChild(a);', to)) + 1);
global.BoardSync = { load: async () => {}, persistDebounced: () => {} };
global.localStorage = { getItem: () => null, setItem: () => {} };
global.document = { getElementById: () => null };
eval(src);

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
}

// ── 시딩 + 기초재고 ──
wpLdyApplyStored(null);
ok('§8 품목 8종 시딩', LAUNDRY_DATA.master.length === 8, LAUNDRY_DATA.master.length);
ok('§8 바스타월 하한 70', LAUNDRY_DATA.master[0].lowLimit === 70);

// 기초재고 미입력 판정 — 안 넣은 품목은 사용량이 계산되지 않으므로 화면이 먼저 알려야 한다
ok('기초재고 전부 미입력 = 8품목', wpLdyOpeningMissing().length === 8, wpLdyOpeningMissing().length);
LAUNDRY_DATA.openingStock = { bath: 300 };
ok('한 품목 입력 후 미입력 7', wpLdyOpeningMissing().length === 7, wpLdyOpeningMissing().length);
LAUNDRY_DATA.openingStock.face = 0;
ok('0 도 입력한 값으로 친다(미입력 6)', wpLdyOpeningMissing().length === 6, wpLdyOpeningMissing().length);
delete LAUNDRY_DATA.openingStock.face;

// 1. 8/1 기초재고 → 입고·마감 기입 → 사용량이 §6 수식과 일치
LAUNDRY_DATA.daily['2026-08-01'] = { bath: { in: 260, end: 280 } };
ok('1) 8/1 사용량 = 300+260+0-280 = 280', wpLdyUsage('bath', '2026-08-01') === 280, wpLdyUsage('bath', '2026-08-01'));

// 2. 8/2 진입 시 전일마감이 8/1 마감값
ok('2) 8/2 전일마감 = 280', wpLdyPrevEnd('bath', '2026-08-02') === 280, wpLdyPrevEnd('bath', '2026-08-02'));

// 3. 8/3 마감 미기입 → 8/4 전일마감은 "가장 최근 기입일"(8/2) 이월
LAUNDRY_DATA.daily['2026-08-02'] = { bath: { in: 240, end: 250 } };
LAUNDRY_DATA.daily['2026-08-03'] = { bath: { in: 230, end: '' } };
ok('3) 8/3 사용량 보류(마감 미기입)', wpLdyUsage('bath', '2026-08-03') === null);
ok('3) 8/4 전일마감 = 8/2의 250', wpLdyPrevEnd('bath', '2026-08-04') === 250, wpLdyPrevEnd('bath', '2026-08-04'));

// 4. 휴관일 = 매월 둘째·넷째 일요일 (2026년 8월: 8/9, 8/23)
ok('4) 8/9 휴관', wpLdyIsClosed('2026-08-09') === true);
ok('4) 8/23 휴관', wpLdyIsClosed('2026-08-23') === true);
ok('4) 8/2(첫째 일요일) 휴관 아님', wpLdyIsClosed('2026-08-02') === false);
ok('4) 8/16(셋째 일요일) 휴관 아님', wpLdyIsClosed('2026-08-16') === false);
ok('4) 8/30(다섯째 일요일) 휴관 아님', wpLdyIsClosed('2026-08-30') === false);
ok('4) 평일 휴관 아님', wpLdyIsClosed('2026-08-05') === false);
// 2026-09-01 GM 정정: 9월(추석 달) 휴관은 9/13 하루뿐 — 9/27(넷째 일요일)은 영업. 정본 = status/close_days.json + scripts/close_days.py
ok('4) 9월은 명절 달 예외 — 9/13 휴관·9/27 영업', wpLdyIsClosed('2026-09-13') && !wpLdyIsClosed('2026-09-27') && !wpLdyIsClosed('2026-09-06'));
ok('4) 수동 등록 휴관(설날 2/17)·신정 1/1 휴관', wpLdyIsClosed('2026-02-17') && wpLdyIsClosed('2026-01-01'));

// 5. 신품 투입 20장 → 당일 사용량 +20, 총 투입 누계 반영
const useBefore = wpLdyUsage('bath', '2026-08-02');
LAUNDRY_DATA.newInput.push({ date: '2026-08-02', itemId: 'bath', qty: 20, memo: '신품 보충' });
ok('5) 신품 20 → 사용량 +20', wpLdyUsage('bath', '2026-08-02') === useBefore + 20);
ok('5) 총 투입 누계 = 기초 300 + 신품 20', wpLdyTotals('bath').input === 320, wpLdyTotals('bath').input);

// 6. 마감재고 하한 미달 판정 (표시는 화면이 하고, 판정 근거는 여기 값)
LAUNDRY_DATA.daily['2026-08-04'] = { bath: { in: 240, end: 60 } };   // 하한 70 미만
ok('6) 8/4 마감 60 < 하한 70', wpLdyEnd('bath', '2026-08-04') < LAUNDRY_DATA.master[0].lowLimit);
ok('6) 결품 경고 발생일수 1일', wpLdyLowDays('2026-08') === 1, wpLdyLowDays('2026-08'));

// 7. 마감재고 과대 입력 → 사용량 음수, 값 보정 없음
LAUNDRY_DATA.daily['2026-08-05'] = { bath: { in: 100, end: 900 } };
const neg = wpLdyUsage('bath', '2026-08-05');
ok('7) 사용량 음수 그대로', neg < 0, neg);
ok('7) 원본 값 보정 없음', LAUNDRY_DATA.daily['2026-08-05'].bath.end === 900);

// 8. ② 요약 카드 4개 정의대로 — 수기 검산
//    8월 bath 입고: 260+240+230+240+100 = 1070 / 사용: 8/1 280, 8/2 240(=280+240+20-250은 290)…
const st = wpLdyMonthStats('2026-08');
let manualIn = 0, manualUse = 0;
['2026-08-01', '2026-08-02', '2026-08-03', '2026-08-04', '2026-08-05'].forEach(d => {
  const i = wpLdyIn('bath', d); if (i !== null) manualIn += i;
  const u = wpLdyUsage('bath', d); if (u !== null) manualUse += u;
});
ok('8) 입고 합계 검산 1070', st.per.bath.inn === manualIn && manualIn === 1070, [st.per.bath.inn, manualIn]);
ok('8) 로스 추정 = Σ사용 − Σ입고', Math.abs(st.per.bath.loss - (manualUse - manualIn)) < 1e-9, [st.per.bath.loss, manualUse - manualIn]);
// 화·수 평균: 8/4(화) 240 · 8/5(수) 100 → 170
ok('8) 화·수 평균 입고 = 170', wpLdyTueWedAvg('2026-08', 'bath') === 170, wpLdyTueWedAvg('2026-08', 'bath'));
ok('8) 화·수 평균 235 미만 = 경고 대상', wpLdyTueWedAvg('2026-08', 'bath') < 235);
ok('8) 신품 투입 누계 20', st.per.bath.newq === 20, st.per.bath.newq);
ok('8) 현재 순환 추정 = 총투입 − 로스누계', Math.abs(wpLdyTotals('bath').circ - (320 - wpLdyTotals('bath').loss)) < 1e-9);

// 9. 월 전환 — 8월 말 마감이 9월 기초로 이월, 8월 데이터 보존
LAUNDRY_DATA.daily['2026-08-31'] = { bath: { in: 200, end: 111 } };
ok('9) 9/1 전일마감 = 8/31 마감 111', wpLdyPrevEnd('bath', '2026-09-01') === 111, wpLdyPrevEnd('bath', '2026-09-01'));
ok('9) 8월 데이터 그대로 조회 가능', wpLdyMonthStats('2026-08').days.length === 6, wpLdyMonthStats('2026-08').days.length);
ok('9) 9월 통계는 8월과 분리', wpLdyMonthStats('2026-09').days.length === 0);

// 저장 왕복(직렬화 안전성) — 다른 탭 데이터와 섞이지 않는 단일 네임스페이스
const round = JSON.parse(JSON.stringify(LAUNDRY_DATA));
wpLdyApplyStored(round);
ok('저장→복원 후 값 보존', wpLdyUsage('bath', '2026-08-01') === 280 && LAUNDRY_DATA.newInput.length === 1);
// issues(출고 이벤트)는 2026-08-08 에 들어왔는데 이 줄이 5개로 남아 그날부터 계속 실패하고 있었다.
ok('네임스페이스 키 6개만', Object.keys(LAUNDRY_DATA).sort().join(',') === 'audit,daily,issues,master,newInput,openingStock',
   Object.keys(LAUNDRY_DATA).sort().join(','));

// ── 오픈 셋팅 / 보충 구분 + 어제 입고분 잔여 (GM 프로세스 2026-08-11) ──
LAUNDRY_DATA.daily['2026-08-10'] = { bath: { in: 300, end: 120 } };
LAUNDRY_DATA.daily['2026-08-11'] = { bath: { in: 280 } };
LAUNDRY_DATA.issues = [
  { date: '2026-08-11', itemId: 'bath', qty: 100, kind: 'open', ts: 1 },
  { date: '2026-08-11', itemId: 'bath', qty: 30,  kind: 'refill', ts: 2 },
  { date: '2026-08-11', itemId: 'bath', qty: 20,  ts: 3 },              // kind 없는 옛 기록
];
ok('오픈 셋팅만 100', wpLdyIssueQtyBy('bath', '2026-08-11', 'open') === 100, wpLdyIssueQtyBy('bath','2026-08-11','open'));
ok('보충 50(옛 기록은 보충으로)', wpLdyIssueQtyBy('bath', '2026-08-11', 'refill') === 50, wpLdyIssueQtyBy('bath','2026-08-11','refill'));
ok('오픈+보충 = 전체 출고 150', wpLdyIssueQty('bath', '2026-08-11') === 150, wpLdyIssueQty('bath','2026-08-11'));
// 어제(8/10) 300 들어왔고 오늘 150 나갔다 → 남은 어제 입고분 150. 오늘 입고 280 은 내일 몫이라 안 센다.
ok('어제 입고분 남음 150', wpLdyInboundLeft('bath', '2026-08-11') === 150, wpLdyInboundLeft('bath','2026-08-11'));
ok('입고 기록 없는 품목은 null', wpLdyInboundLeft('socks', '2026-08-11') === null, wpLdyInboundLeft('socks','2026-08-11'));

console.log('\n결과: ' + pass + ' 통과 · ' + fail + ' 실패');
process.exit(fail ? 1 : 0);
