// 지문키 이름 대조 자가검사 (배491 · 2026-08-10 시토)
//   대상 = .deploy-funnel-v2/Survey.js 의 _findRowsByKey_ / _rowKeyParts_ / _nameColIdx_.
//   왜 필요한가: 형제가 부모 번호를 함께 쓰면 '타임스탬프+전화' 지문이 100% 같아져 행을 못 가린다.
//   이름을 세 번째 재료로 더했는데, 이름을 안 보내는 옛 화면에서 동작이 달라지면 안 된다(회귀 0).
//   실행: node scripts/test_rowkey_name.js   (통과하면 아무 것도 안 찍고 OK 한 줄)
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const SRC = path.join(__dirname, '..', '.deploy-funnel-v2', 'Survey.js');
const src = fs.readFileSync(SRC, 'utf8');

// 필요한 함수 4개만 떼어 낸다(GAS 전역 API에 의존하지 않는 순수 함수들).
function grab(name) {
  const i = src.indexOf('function ' + name + '(');
  assert.ok(i >= 0, name + ' 를 찾지 못함 — 함수 이름이 바뀌었는지 확인');
  let depth = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') { depth++; started = true; }
    else if (src[j] === '}') { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
  }
  throw new Error(name + ' 본문 파싱 실패');
}

const ctx = {};
// _normTsKey_ · _normPhone_ 은 Survey.js 원본을 그대로 쓴다(같은 정규화가 아니면 검사 의미가 없다).
const code = [grab('_normTsKey_'), grab('_normPhone_'), grab('_normNameKey_'),
              grab('_nameColIdx_'), grab('_findRowsByKey_'), grab('_rowKeyParts_')].join('\n');
new Function('exports', code + '\nexports._findRowsByKey_=_findRowsByKey_;'
  + 'exports._rowKeyParts_=_rowKeyParts_;exports._nameColIdx_=_nameColIdx_;'
  + 'exports._normNameKey_=_normNameKey_;')(ctx);

// 가짜 시트 — 실제 사고 데이터(형제 2명, 같은 날·같은 부모 번호).
function fakeSheet(rows) {
  return {
    getLastRow: () => rows.length + 1,
    getRange: (r1, c1, n, w) => ({
      getValues: () => rows.slice(r1 - 2, r1 - 2 + n).map(r => r.slice(c1 - 1, c1 - 1 + w)),
    }),
  };
}
// 칸 순서: 0=타임스탬프, 1=성함, 2=연락처
const HDR = ['타임스탬프', '성함', '연락처'];
const SHEET = fakeSheet([
  ['2026-07-16 00:00:00', '조온동', '010-9284-2623'],
  ['2026-07-16 00:00:00', '조이진', '010-9284-2623'],
  ['2026-07-17 00:00:00', '김하나', '010-1111-2222'],
]);

const nameCol = ctx._nameColIdx_(HDR);
assert.strictEqual(nameCol, 1, "이름 칸을 '성함'(1번)으로 찾아야 한다");

const ts = '20260716000000', ph = '01092842623';

// ① 이름 없이 = 종전 동작. 형제 2건이 그대로 잡혀 호출부가 fail-closed 로 거부한다.
assert.deepStrictEqual(ctx._findRowsByKey_(SHEET, 0, 2, ts, ph), [2, 3],
  '이름을 안 주면 종전처럼 2건이 잡혀야 한다(회귀 0)');

// ② 이름을 주면 형제가 갈린다.
assert.deepStrictEqual(ctx._findRowsByKey_(SHEET, 0, 2, ts, ph, nameCol, '조이진'), [3],
  '이름을 주면 조이진 한 행만 잡혀야 한다');
assert.deepStrictEqual(ctx._findRowsByKey_(SHEET, 0, 2, ts, ph, nameCol, '조온동'), [2],
  '이름을 주면 조온동 한 행만 잡혀야 한다');

// ③ 이름 공백·대소문자는 무시한다(화면이 보내는 값이 정규화 전일 수 있다).
assert.deepStrictEqual(ctx._findRowsByKey_(SHEET, 0, 2, ts, ph, nameCol, ctx._normNameKey_(' 조 이 진 ')), [3],
  '공백이 섞인 이름도 같은 행을 찾아야 한다');

// ④ 없는 이름 = 0건 → 호출부가 거부(엉뚱한 행에 쓰지 않는다).
assert.deepStrictEqual(ctx._findRowsByKey_(SHEET, 0, 2, ts, ph, nameCol, '없는사람'), [],
  '이름이 안 맞으면 0건이어야 한다');

// ⑤ 이름 칸이 없는 시트(-1)는 이름을 줘도 종전 동작으로 되돌아간다.
assert.deepStrictEqual(ctx._findRowsByKey_(SHEET, 0, 2, ts, ph, -1, '조이진'), [2, 3],
  '이름 칸이 없으면 이름 대조를 건너뛰어야 한다');

// ⑥ rowKey 파싱 — 세 번째 파트가 있으면 name, 없으면 빈 값(옛 화면).
assert.deepStrictEqual(ctx._rowKeyParts_({ rowKey: ts + '|' + ph + '|조이진' }),
  { ts: ts, phone: ph, name: '조이진' });
assert.deepStrictEqual(ctx._rowKeyParts_({ rowKey: ts + '|' + ph }),
  { ts: ts, phone: ph, name: '' }, '옛 화면(2부분 키)은 이름이 빈 값이어야 한다');
assert.deepStrictEqual(ctx._rowKeyParts_({ rowKey: ts + '|' + ph, keyName: ' 조 이 진 ' }),
  { ts: ts, phone: ph, name: '조이진' }, 'keyName 으로도 이름을 받을 수 있어야 한다');
assert.strictEqual(ctx._rowKeyParts_({ keyName: '조이진' }), null,
  '타임스탬프·전화가 없으면 지문키를 쓰지 않는다(null)');

// ⑦ '보호자 이름' 같은 곁칸이 먼저 걸리면 안 된다 — 정확일치가 앞선다.
assert.strictEqual(ctx._nameColIdx_(['타임스탬프', '보호자 이름', '성함', '연락처']), 2,
  "'보호자 이름'보다 '성함'을 먼저 잡아야 한다");

console.log('OK — 지문키 이름 대조 자가검사 7종 통과');
