/* 월간 보고 A3 — 원장 연결 (2026-08-28 시우 · GM 지시 "매월마다 누적하고 추적하고 기록")
 *
 * 왜 있나
 *   보고서의 숫자를 매달 사람이 손으로 옮겨 적고 있었다. 이 파일이 원장
 *   (status/monthly_report_ledger.json)을 읽어 화면의 숫자 자리를 그 달 값으로 채운다.
 *   달을 바꾸려면 주소 끝에 ?m=2026-07 을 붙인다 — 파일을 매월 새로 만들지 않는다.
 *
 * 어떻게 쓰나
 *   숫자 자리에 <span data-f="sales.month" data-fmt="won"></span> 처럼 적어 둔다.
 *   data-f = 원장 안 경로(점으로 내려간다) · data-fmt = 표기법(won/num/pct/pct1)
 *   data-w = 막대 너비를 그 값(%)으로 (예 data-w="sales.month_rate_pct")
 *
 * 원칙
 *   · 원장에 그 달이 없으면 숫자를 지어내지 않고 '—' 로 두고 맨 위에 띠를 띄운다.
 *   · 값이 null 이면 '측정 불가' 로 적는다 — 0 으로 채우지 않는다(약속 L25).
 *   · HTML 에 이미 적혀 있는 값은 원장이 없을 때 그대로 남는다(연결 실패가 화면을 비우지 않게).
 */
(function () {
  var LEDGER = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/status/monthly_report_ledger.json';

  function monthParam() {
    var m = new URLSearchParams(location.search).get('m');
    return (m && /^\d{4}-\d{2}$/.test(m)) ? m : null;   // 없으면 문서에 박힌 기본 달을 쓴다
  }

  function dig(obj, path) {
    return String(path).split('.').reduce(function (o, k) {
      return (o === null || o === undefined) ? undefined : o[k];
    }, obj);
  }

  function fmt(v, how) {
    if (v === null) return '측정 불가';
    if (v === undefined) return null;                  // 경로 자체가 없으면 손대지 않는다
    if (how === 'won') return Number(v).toLocaleString('ko-KR') + ' 원';
    if (how === 'num') return Number(v).toLocaleString('ko-KR');
    if (how === 'pct') return Math.round(Number(v)) + '%';
    if (how === 'pct1') return Number(v).toFixed(1) + '%';
    if (how === 'eok') return (Number(v) / 100000000).toFixed(2) + '억';
    return String(v);
  }

  /* 안내 띠는 보고서 종이 '밖'에 붙인다 — 종이 안에 넣으면 A3 한 장 높이를 밀어내 아래 표가 잘린다.
     그리고 인쇄물에는 나오지 않는다(마감 전이라는 사실은 각주가 이미 적고 있다 · 화면 확인용). */
  function banner(msg, tone) {
    var page = document.getElementById('sheet');
    if (!page || !page.parentNode) return;
    var d = document.createElement('div');
    d.className = 'ledger-note';
    d.style.cssText = 'width:1587px;margin:8px auto -18px;padding:8px 16px;font-size:12.5px;font-weight:700;' +
      'border-radius:4px;border:1.5px solid ' +
      (tone === 'bad' ? '#9E2A2A;background:#FBEDED;color:#9E2A2A' : '#96601A;background:#FBF5EA;color:#96601A');
    d.textContent = msg;
    page.parentNode.insertBefore(d, page);
    if (!document.getElementById('ledger-note-print')) {
      var st = document.createElement('style');
      st.id = 'ledger-note-print';
      st.textContent = '@media print{.ledger-note{display:none !important;}}';
      document.head.appendChild(st);
    }
  }

  function apply(month, data) {
    document.querySelectorAll('[data-f]').forEach(function (el) {
      var out = fmt(dig(data, el.getAttribute('data-f')), el.getAttribute('data-fmt'));
      if (out !== null && out !== undefined) el.textContent = out;
    });
    document.querySelectorAll('[data-w]').forEach(function (el) {
      var v = dig(data, el.getAttribute('data-w'));
      if (typeof v === 'number') el.style.width = Math.max(0, Math.min(100, v)) + '%';
    });
    // 문서 머리의 기준 시각도 원장 값으로 맞춘다 — 화면과 각주가 서로 다른 시각을 말하면 안 된다.
    var asOf = document.querySelector('[data-asof]');
    if (asOf && data.asOf) asOf.textContent = data.asOf;
    if (data.closed === false) banner('이 달은 아직 마감 전입니다 — 숫자는 ' + (data.asOf || '') + ' 기준이며 마감 시 달라집니다.', 'warn');
  }

  fetch(LEDGER + '?cb=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (led) {
      var months = (led && led.months) || {};
      var want = monthParam() || document.body.getAttribute('data-default-month');
      var data = months[want];
      if (!data) {
        banner('원장에 ' + want + ' 자료가 아직 없습니다 — 화면 숫자는 문서에 적힌 값 그대로입니다.', 'bad');
        return;
      }
      /* 계획 장은 지난달 실적을 함께 인용한다(예 "8월은 5.45억이었습니다").
         data-f="prev.…" 로 적으면 여기서 붙인 지난달 줄에서 값을 찾는다 — 그 값도 손으로 안 적는다. */
      var pm = document.body.getAttribute('data-prev-month');
      if (pm && months[pm]) data = Object.assign({}, data, { prev: months[pm] });
      apply(want, data);
    })
    .catch(function () {
      banner('보고 원장을 불러오지 못했습니다 — 화면 숫자는 문서에 적힌 값 그대로입니다(새로고침하면 다시 시도합니다).', 'bad');
    });
})();
