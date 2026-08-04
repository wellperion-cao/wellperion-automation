// 회원 유효/종료 판정 자체 점검 (배354 · 2026-08-04 시토)
// 목적: member_active_list / cpo_today_stats / member_owner_bulk_set / member_active_summary
//   4곳이 모두 .deploy-funnel-v2/Survey.js 의 _memberIsValid_ 하나만 쓰게 고쳤다(약속 L01).
//   이 점검은 그 함수를 소스에서 그대로 뽑아 실행해, 잔여일이 빈값·공백·0·음수·정상 숫자일 때
//   기대한 대로 판정하는지 확인한다. 프레임워크·픽스처 없이 assert 만 쓴다.
// 실행: node scripts/check_member_valid_parity.js
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const src = fs.readFileSync(path.join(__dirname, '..', '.deploy-funnel-v2', 'Survey.js'), 'utf8');
const m = src.match(/var MEMBER_LOSS_TAGS_[\s\S]*?\r?\nfunction _memberIsValid_[\s\S]*?\r?\n}\r?\n/);
assert(m, '_memberIsValid_ 정의를 Survey.js에서 못 찾음 — 함수가 삭제/이름변경 됐는지 확인');

// eslint-disable-next-line no-eval
eval(m[0]);

const cases = [
  // [설명, remCell, reVCell, 기대값]
  ['잔여일 빈 문자열(신규 등록 직후) = 유효',           '',    '',    true],
  ['잔여일 공백만 = 유효',                             '   ', '',    true],
  ['잔여일 미기재(undefined) = 유효',                  undefined, '', true],
  ['잔여일 미기재(null) = 유효',                       null,  '',    true],
  ['잔여일 0 = 유효(만료 당일까지 유효)',               '0',   '',    true],
  ['잔여일 양수 = 유효',                               '15',  '',    true],
  ['잔여일 음수(진짜 종료) = 종료',                     '-1',  '',    false],
  ['잔여일 미기재라도 재등록분류 LOSS면 종료',           '',    'LOSS', false],
  ['잔여일 미기재라도 재등록분류 환불이면 종료',          '',    '환불', false],
  ['잔여일 미기재라도 재등록분류 양도LOSS면 종료',        '',    '양도LOSS', false],
  ['잔여일 양수인데 재등록분류 LOSS면 종료',              '5',   'LOSS', false],
];

let fail = 0;
for (const [label, rem, reV, expect] of cases) {
  const got = _memberIsValid_(rem, reV);
  if (got !== expect) {
    fail++;
    console.error(`FAIL: ${label} — got ${got}, expect ${expect}`);
  }
}

// 4개 호출부가 전부 이 함수 하나만 부르는지(재정의 없이 재사용하는지) 소스 레벨로도 확인 —
// 과거 버그가 "각자 계산"이라 여기서 호출 개수로 회귀를 잡는다.
// 정의(function _memberIsValid_() 1건) 제외 — 실제 호출부만 센다.
const callSites = (src.match(/_memberIsValid_\(/g) || []).length - 1;
assert.strictEqual(callSites, 4, `_memberIsValid_ 호출 개수 기대 4, 실제 ${callSites} — 판정 로직이 다시 복제됐을 수 있음`);

if (fail > 0) {
  console.error(`${fail}건 실패`);
  process.exit(1);
}
console.log(`OK — ${cases.length}건 통과, 호출부 ${callSites}곳 모두 단일 함수 재사용 확인`);
