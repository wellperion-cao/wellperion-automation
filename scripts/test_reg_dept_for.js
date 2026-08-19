/* 종합접수처 청결 접수의 부서 자동 배정(_regDeptFor) 자체 점검.
   실행: node scripts/test_reg_dept_for.js  (저장소 루트에서)

   왜 있나: 장소 글자에 따라 남/여 반장님이 갈리는 분기라, 잘못 갈리면 엉뚱한 담당자에게
   접수가 나간다. 성별이 안 적힌 장소는 반드시 옛 '지원부' 값을 그대로 둬야 화면의
   '지원부(구분 전)' 칸에 모여 사람이 배정한다 — 그 성질이 깨지는지를 이 파일이 잡는다. */
const fs = require('fs');

const SRC = '3. 웰페리온 가이드/coo/reception/apps_script_reception.js';
const src = fs.readFileSync(SRC, 'utf8');
const found = src.match(/function _regDeptFor[\s\S]*?\n}/);
if (!found) throw new Error('_regDeptFor 를 ' + SRC + ' 에서 찾지 못했습니다');
eval(found[0]);

const clean = { key: 'clean', dept: '지원부' };
const lost = { key: 'lost', dept: '운영부' };
const cases = [
  [clean, '여자사우나', '지원부(여)'],
  [clean, '남자사우나', '지원부(남)'],
  [clean, '여성탈의실', '지원부(여)'],
  [clean, '수영장', '지원부'],       // 성별 없는 장소 = 구분 전 그대로
  [clean, '', '지원부'],             // 장소 빈칸 = 구분 전 그대로
  [lost, '여자사우나', '운영부'],     // 청결 아닌 카테고리는 손대지 않는다
];

for (const [cat, loc, expected] of cases) {
  const got = _regDeptFor(cat, loc);
  if (got !== expected) throw new Error(`${cat.key}/${loc || '(빈칸)'}: ${got} ≠ ${expected}`);
}
console.log('PASS — ' + cases.length + '건');
