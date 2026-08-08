/* G1 히어로 '이어가는 날들' 지속일수 계산 자기검사 (2026-08-08).
   이 숫자는 GM 이 매일 아침 보는 값이라 하루라도 어긋나면 바로 티가 난다.
   위험한 지점 = 표의 날짜 표기(2025.6.27 처럼 점 구분·한 자리 월일)와 월 경계.
   node scripts/test_gm_habit_streak.js 로 실행. */
function streak(name, dateText, nowText) {
  var p = dateText.trim().split(/[.\-\/]/).map(Number);
  if (p.length < 3 || !p[0] || isNaN(p[0])) return null;
  var start = new Date(p[0], p[1] - 1, p[2]);
  var now = new Date(nowText);
  var days = Math.floor((now.setHours(0, 0, 0, 0) - start.setHours(0, 0, 0, 0)) / 86400000);
  return days >= 0 ? { name: name.replace(/\s*\(.*\)\s*/, '').trim(), days: days } : null;
}

var assert = require('assert');
var NOW = '2026-08-08';

// 실제 '끊어야 할 습관 추적' 표 값
assert.strictEqual(streak('금연', '2025.6.27', NOW).days, 407);
assert.strictEqual(streak('절주', '2026.1.1', NOW).days, 219);
assert.strictEqual(streak('과도한 소비 (가계부)', '2025.5.1', NOW).days, 464);
// 괄호 설명은 이름에서 뗀다 — 칩이 길어지면 줄이 밀린다
assert.strictEqual(streak('과도한 소비 (가계부)', '2025.5.1', NOW).name, '과도한 소비');
// 머리글 행(td 없음)·아직 안 온 날짜는 세지 않는다
assert.strictEqual(streak('머리글', '시작일', NOW), null);
assert.strictEqual(streak('미래', '2027.1.1', NOW), null);
// 시작한 날 당일은 0일째(음수 아님)
assert.strictEqual(streak('오늘시작', '2026.8.8', NOW).days, 0);

console.log('OK — 지속일수 계산 7건 통과');
