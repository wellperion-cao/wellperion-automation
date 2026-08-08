/* 알림 한 장 '시간순 보기' 시간띠 배정 자기검사 (2026-08-08 · GM 지시).
   화면 코드(자율현황.html alertTimeHtml)와 같은 규칙을 실제 등록부 값으로 검증한다.
   위험한 지점 = when_sort 가 비어 '수시'로 새는 것, 그리고 평일·휴일로 갈리는 회차가
   20시와 22시 두 자리로 흩어지는 것.
   node scripts/test_notify_time_bands.js 로 실행. */
const fs = require('fs');
const reg = JSON.parse(fs.readFileSync(__dirname + '/../status/notify_registry.json','utf8'));
const TIME_BANDS = [
  { key:'dawn', label:'새벽·아침', from:'0500', to:'0859' },
  { key:'morn', label:'오전',     from:'0900', to:'1159' },
  { key:'day',  label:'낮',       from:'1200', to:'1759' },
  { key:'eve',  label:'저녁·밤',  from:'1800', to:'2359' },
  { key:'any',  label:'수시',     from:null,   to:null  },
];
function bandOf(ws){
  if(!ws) return 'any';
  for(const b of TIME_BANDS){ if(b.from && ws>=b.from && ws<=b.to) return b.key; }
  return 'any';
}
const g = {};
reg.items.forEach(i => { const b = bandOf(i.when_sort); (g[b]=g[b]||[]).push(i); });
TIME_BANDS.forEach(b => {
  const list = (g[b.key]||[]).sort((x,y)=>{
    const a=x.when_sort||'', c=y.when_sort||'';
    return a===c ? String(x.what||'').localeCompare(String(y.what||'')) : (a<c?-1:1);
  });
  if(!list.length) return;
  console.log(`\n${b.label} — ${list.length}건`);
  list.forEach(i => console.log(`   ${(i.when||'부정기').padEnd(22)} ${i.channel==='kakao'?'카톡':'텔레'} ${String(i.room||'').slice(0,20)}`));
});
const a = require('assert');
a.strictEqual(bandOf('0730'), 'dawn');
a.strictEqual(bandOf('0900'), 'morn');
a.strictEqual(bandOf('1700'), 'day');
a.strictEqual(bandOf('2230'), 'eve');
a.strictEqual(bandOf(null),   'any');
a.strictEqual(bandOf('0459'), 'any', '05시 전은 어느 띠에도 안 든다 — 수시로');
// 22:30 회차가 한 띠에 모였는지(20:30/22:30 로 흩어지지 않았는지)
const late = reg.items.filter(i => String(i.when||'').includes('22:30'));
a.ok(late.length >= 5, '22:30 회차 5건 이상');
a.ok(late.every(i => bandOf(i.when_sort) === 'eve'), '22:30 회차가 전부 저녁·밤 띠에 모여야 한다');
// 시각이 적혀 있는데 '수시'로 새는 것이 없어야 한다 — 2026-08-08 에 8건이 이렇게 새 있었고,
// 시간순 화면을 만들고 나서야 드러났다. 새 발신을 등록할 때 또 빠뜨리면 여기서 걸린다.
const leaked = reg.items.filter(i => !i.when_sort
  && /\d{1,2}:\d{2}/.test(String(i.when || ''))
  && !/마다|주기|폴링|즉시|부정기|편승|~/.test(String(i.when || '')));
a.deepStrictEqual(leaked.map(i => i.id), [], '시각이 있는데 수시로 샌 항목');
console.log('\nOK — 시간띠 배정 9건 통과');
