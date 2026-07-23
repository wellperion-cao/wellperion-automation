/* 🎉 팡파레 — 업무·결재가 끝나는 순간의 축하 연출 (2026-07-23 시우 · GM 지시)
 *
 * 정본 = 이 파일 하나. 업무 현황 SSOT·결재 현황 SSOT 두 페이지가 함께 참조한다
 * (약속 L01 '한 곳만 본다' — 페이지마다 복붙하면 한쪽만 고쳐져 어긋난다).
 *
 * 설계
 *  - 외부 라이브러리·CDN 없음. canvas 만으로 그린다(오프라인·CSP 안전).
 *  - pointer-events:none — 축하 중에도 화면 조작을 막지 않는다.
 *  - 2.4초 뒤 스스로 사라지고 DOM에서 제거된다(잔여물 0).
 *  - 애니메이션을 꺼둔 분(prefers-reduced-motion)께는 색종이 없이 문구만.
 *  - 어떤 예외도 업무 처리를 막지 않는다(전부 try/catch로 삼킨다).
 *
 * 사용:  fanfare('🎉 입항 완료!<br>수고하셨습니다', true)
 *        두 번째 인자 true = 큰 축하(최종 결재 완료·업무 완료), 생략 = 작은 축하(중간 단계).
 */
(function () {
  if (window.fanfare) return;              // 중복 로드 방어

  var CSS = [
    '.fanfare-canvas{position:fixed;inset:0;pointer-events:none;z-index:9998}',
    '.fanfare-wrap{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;',
    'pointer-events:none;z-index:9999;transition:opacity .6s ease}',
    '.fanfare-wrap.out{opacity:0}',
    '.fanfare-msg{background:rgba(20,18,16,0.92);color:#f4efe6;border:1px solid rgba(224,180,80,0.5);',
    'border-radius:6px;padding:16px 28px;font-size:19px;font-weight:700;letter-spacing:-0.01em;',
    'box-shadow:0 12px 40px rgba(0,0,0,0.35);text-align:center;line-height:1.5;max-width:80vw;',
    'word-break:keep-all;animation:fanfarePop .45s cubic-bezier(.2,1.5,.4,1)}',
    '.fanfare-msg.big{font-size:23px;padding:20px 34px;border-color:rgba(224,180,80,0.85)}',
    '@keyframes fanfarePop{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}',
    '@media (prefers-reduced-motion:reduce){.fanfare-msg{animation:none}}'
  ].join('');

  function injectCss() {
    if (document.getElementById('fanfare-css')) return;
    var st = document.createElement('style');
    st.id = 'fanfare-css';
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  var COLORS = ['#E0B450', '#5B9FD5', '#6FBF9B', '#D98E6A', '#B98FD0', '#F0F0F0'];

  window.fanfare = function (msg, big) {
    try {
      injectCss();
      var wrap = document.createElement('div');
      wrap.className = 'fanfare-wrap';
      wrap.innerHTML = '<div class="fanfare-msg' + (big ? ' big' : '') + '">'
        + (msg || '수고하셨습니다!') + '</div>';
      document.body.appendChild(wrap);
      setTimeout(function () {
        wrap.classList.add('out');
        setTimeout(function () { if (wrap.parentNode) wrap.parentNode.removeChild(wrap); }, 700);
      }, 2400);

      if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;

      var cv = document.createElement('canvas');
      cv.className = 'fanfare-canvas';
      document.body.appendChild(cv);
      var W = cv.width = window.innerWidth, H = cv.height = window.innerHeight;
      var ctx = cv.getContext('2d');
      var N = big ? 150 : 90, ps = [], i;
      for (i = 0; i < N; i++) {
        ps.push({
          x: W * (0.5 + (Math.random() - 0.5) * 0.5), y: H * 0.42 + Math.random() * 30,
          vx: (Math.random() - 0.5) * 15, vy: -7 - Math.random() * 12,
          w: 5 + Math.random() * 6, h: 8 + Math.random() * 8,
          c: COLORS[(Math.random() * COLORS.length) | 0],
          rot: Math.random() * 6.28, vr: (Math.random() - 0.5) * 0.35, life: 0
        });
      }
      var MAX = 150;
      (function tick() {
        ctx.clearRect(0, 0, W, H);
        var alive = 0;
        for (var j = 0; j < ps.length; j++) {
          var p = ps[j];
          p.life++;
          if (p.life > MAX) continue;
          alive++;
          p.vy += 0.42; p.vx *= 0.99;
          p.x += p.vx; p.y += p.vy; p.rot += p.vr;
          ctx.save();
          ctx.globalAlpha = Math.max(0, 1 - p.life / MAX);
          ctx.translate(p.x, p.y);
          ctx.rotate(p.rot);
          ctx.fillStyle = p.c;
          ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
          ctx.restore();
        }
        if (alive) requestAnimationFrame(tick);
        else if (cv.parentNode) cv.parentNode.removeChild(cv);
      })();
    } catch (e) { /* 축하가 실패해도 업무 처리는 계속된다 */ }
  };
})();
