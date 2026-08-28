/* 종합접수처 접수 건의 부서 자동 배정(_regDeptFor) 자체 점검.
   실행: node scripts/test_reg_dept_for.js  (저장소 루트에서)

   왜 있나: 장소 글자에 따라 담당이 갈리는 분기라, 잘못 갈리면 엉뚱한 담당자에게 접수가 나간다.
   성별을 알 수 없는 건은 반드시 빈 값으로 남아 화면에서 사람이 배정해야 한다 — 임의로 한쪽
   반장님께 찍어 보내지 않는 성질이 깨지는지를 이 파일이 잡는다.
   (2026-08-28 GM 지시로 '지원부'(구분 전) 값을 없애고 빈 값으로 바꿨다.) */
const fs = require('fs');

const SRC = '3. 웰페리온 가이드/coo/reception/apps_script_reception.js';
const src = fs.readFileSync(SRC, 'utf8');
const table = src.match(/var REG_LOC_DEPT = \{[\s\S]*?\n\};/);
if (!table) throw new Error('REG_LOC_DEPT 를 ' + SRC + ' 에서 찾지 못했습니다');
const found = src.match(/function _regDeptFor[\s\S]*?\n}/);
if (!found) throw new Error('_regDeptFor 를 ' + SRC + ' 에서 찾지 못했습니다');
eval(table[0]);
eval(found[0]);

const clean = { key: 'clean', dept: '' };
const complaint = { key: 'complaint', dept: '운영부' };
const lost = { key: 'lost', dept: '운영부' };
const cases = [
  // 성별이 적혀 있으면 그 구역 반장님 — 장소 표보다 먼저다
  [clean, '여자사우나', '지원부(여)'],
  [clean, '남자사우나', '지원부(남)'],
  [clean, '여성탈의실', '지원부(여)'],
  [clean, '여자락커', '지원부(여)'],
  // 장소 표 — GM 확정 2026-08-28: 수영장은 지원부가 아니라 수영팀이 답한다
  [clean, '수영장', '수영팀'],
  [clean, '헬스장', 'P.T팀'],
  [clean, '체조장', '체조팀'],
  [complaint, '수영장', '수영팀'],
  // 알 수 없는 건 = 빈 값(사람이 배정) — '지원부'로 되돌아가면 안 된다
  [clean, '', ''],
  [clean, '1층 에스컬레이터 전', ''],
  [clean, '기타', ''],
  [clean, '락커', ''],
  [complaint, '락커', ''],
  // 컴플레인의 '기타'는 리셉션 응대라 운영부가 맞다
  [complaint, '기타', '운영부'],
  // 청결·컴플레인 아닌 분류는 장소를 보지 않는다
  [lost, '여자사우나', '운영부'],
  [lost, '수영장', '운영부'],
];

for (const [cat, loc, expected] of cases) {
  const got = _regDeptFor(cat, loc);
  if (got !== expected) throw new Error(`${cat.key}/${loc || '(빈칸)'}: "${got}" ≠ "${expected}"`);
}
// '지원부'(구분 전)는 어떤 입력으로도 다시 나오면 안 된다
for (const loc of ['', '락커', '기타', '수영장', '1층 에스컬레이터 전', '골프장']) {
  for (const cat of [clean, complaint]) {
    if (_regDeptFor(cat, loc) === '지원부') throw new Error(`'지원부' 가 되살아났다: ${cat.key}/${loc}`);
  }
}
console.log('PASS — ' + cases.length + '건 + 지원부 부활 방지 12건');
