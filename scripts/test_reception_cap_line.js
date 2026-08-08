/* 종합접수처 SLA 알림 한 줄 자르기 자기검사 (2026-08-08 · GM 지적).

   GM 이 실제로 받은 알림이 이랬다:
     🔴 [시설물 고장 접수] 자동 부팅 안됨
     T업기 타석 제어 안됨(타석 — 24분 초과 (RECEPTION-91 · 담당 @시설폰)
   접수 내용에 줄바꿈이 있어 한 줄이 두 줄로 벌어졌고, 여는 괄호가 닫히지 않은 채 끝났다.

   대상 함수는 구글 앱스크립트 파일 안에 있어 그대로 불러올 수 없다 — 파일에서 그 함수만
   떼어 내 검사한다(코드가 바뀌면 이 검사도 같이 따라온다).

   node scripts/test_reception_cap_line.js 로 실행. */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const SRC = path.join(__dirname, '..', '3. 웰페리온 가이드', 'coo', 'reception', 'apps_script_reception.js');
const src = fs.readFileSync(SRC, 'utf8');
const m = src.match(/function _regCapLine[\s\S]*?\n}/);
assert.ok(m, '_regCapLine 을 찾지 못했다 — 함수 이름이 바뀌었는지 확인하라');
eval(m[0]);

const REAL = '자동 부팅 안됨\nT업기 타석 제어 안됨(타석 3번) 확인 요청드립니다';
const out = _regCapLine(REAL, 28);
console.log('전:', JSON.stringify(REAL));
console.log('후:', JSON.stringify(out));

assert.ok(!out.includes('\n'), '줄바꿈이 남으면 알림이 여러 줄로 깨진다');
assert.ok(out.endsWith('…'), '잘렸으면 잘린 표시가 있어야 한다');
assert.ok(out.length <= 29, '상한을 넘으면 안 된다: ' + out.length);
// 반쪽 괄호 금지 — 여는 괄호가 있으면 닫는 괄호도 있어야 한다
assert.ok(!/[(\[]/.test(out) || /[)\]]/.test(out), '닫히지 않은 괄호가 남았다: ' + out);

// 상한 안이면 그대로 둔다
assert.strictEqual(_regCapLine('자동문 고장', 28), '자동문 고장');
// 빈 값·공백은 지어내지 않고 밝힌다
assert.strictEqual(_regCapLine(null, 28), '(내용 없음)');
assert.strictEqual(_regCapLine('   ', 28), '(내용 없음)');
// 띄어쓰기가 아예 없는 긴 글은 길이로 자른다(뜻이 끊겨도 길이는 지킨다)
assert.ok(_regCapLine('가'.repeat(60), 28).length <= 29);
// 괄호가 앞쪽에 있으면 통째로 날리지 않는다(내용이 거의 안 남으면 안 된다)
const early = _regCapLine('(긴급) 남성 사우나 온도계 표시가 안 되어 확인이 필요합니다', 28);
assert.ok(early.length >= 10, '괄호 처리가 내용을 너무 많이 지웠다: ' + early);

console.log('OK — 알림 한 줄 자르기 9건 통과');
