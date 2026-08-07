/* ══════════════════════════════════════════════════════════════════════
   프로필월 생성기 — 파트너팀 체계 ▸ 🖼 프로필월 탭
   ----------------------------------------------------------------------
   기존 파트너강사 프로필월(2. 브랜드_자료/03_파트너강사 프로필월) 판형을
   실측해 그대로 재현한다. 판형 938×760 · 3배(2,814×2,280) 출력.
   실측 근거: 스쿼시 이상훈 팀장 프로필.png (원본 좌표 추출)
     카드 x36~887 y40~727 / 사진블록 x36~462 우하단 라운드 r=213
     구분선·소제목 #D2AF95 / 매트 #606060 / 블록톤 #F4F6F9
   외부 라이브러리 없음(캔버스 직접 렌더) — 사내망·오프라인에서도 동작.
   ══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var A = '../../_assets/profile/';          // coo/check/ 기준 자산 경로
  var SC = 3;                                // 출력 배율(3배 = 2814×2280)

  // ── 실측 제원 (938×760 좌표계) ──
  var G = {
    W: 938, H: 760,
    mat: '#606060',   // (미사용) 구 판형의 회색 매트 — 2026-08-07 카드가 판형을 꽉 채우도록 바뀌며 안 그린다

    card: { x: 36, y: 40, w: 852, h: 688 },
    block: { x: 36, y: 40, w: 427, h: 688, r: 213, bg: '#f4f6f9' },
    text: { x: 502, right: 887 },
    // ★세로 위치는 원본 실측에 맞춘 값이다(2026-08-03 대조):
    //   이름 잉크 상단 ≈95 · 영문 ≈145 · 첫 구분선 =218. 임의로 바꾸면 원본과 어긋난다.
    nameTop: 92, nameSize: 46, enSize: 38, secGap: 38,
    secTitle: 16.5, secColor: '#d2af95', body: 15.2, bodyLh: 25.8,
    wm: { x: 413, y: 666, w: 48 }
  };

  var state = {
    img: null,        // 원본 사진 (Image)
    cut: null,        // 배경 제거 결과 (Canvas)
    zoom: 1, offX: 0, offY: 0,
    wmark: null, fontsReady: false
  };

  /* ── 폰트 로드 ── */
  function loadFonts() {
    if (!window.FontFace) { state.fontsReady = true; return Promise.resolve(); }
    var defs = [
      ['700', 'Pretendard-Bold.otf'],
      ['600', 'Pretendard-SemiBold.otf'],
      ['500', 'Pretendard-Medium.otf']
    ];
    return Promise.all(defs.map(function (d) {
      var f = new FontFace('PretendardPW', 'url(' + A + d[1] + ')', { weight: d[0] });
      return f.load().then(function (ff) { document.fonts.add(ff); });
    })).then(function () { state.fontsReady = true; })
      .catch(function () { state.fontsReady = true; });   // 실패해도 시스템 폰트로 진행
  }

  function font(weight, size) {
    return weight + ' ' + size + 'px PretendardPW, "Malgun Gothic", sans-serif';
  }

  /* ══ 배경 제거(누끼) ══
     벽처럼 '밝고 채도 낮은' 화소를 테두리에서부터 번져나가며 지운다.
     인물(어두운 옷·채도 높은 피부)에서 자동으로 멈춘다. 안쪽 로고·글씨는
     테두리와 연결돼 있지 않아 지워지지 않는다. */
  function cutout(img, lumMin, bgHex) {
    var w = img.naturalWidth, h = img.naturalHeight;
    var cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, w, h), p = d.data;
    var SPREAD_MAX = 48, TOL = 100;

    function cand(i) {
      var r = p[i], g = p[i + 1], b = p[i + 2];
      var lum = 0.299 * r + 0.587 * g + 0.114 * b;
      if (lum < lumMin) return false;
      var mx = Math.max(r, g, b), mn = Math.min(r, g, b);
      return (mx - mn) <= SPREAD_MAX;
    }

    var bg = new Uint8Array(w * h);
    var q = new Int32Array(w * h), qh = 0, qt = 0;
    function push(x, y) {
      if (x < 0 || y < 0 || x >= w || y >= h) return;
      var k = y * w + x;
      if (bg[k]) return;
      if (!cand(k * 4)) return;
      bg[k] = 1; q[qt++] = k;
    }
    for (var x = 0; x < w; x++) { push(x, 0); push(x, h - 1); }
    for (var y = 0; y < h; y++) { push(0, y); push(w - 1, y); }

    while (qh < qt) {
      var k = q[qh++], kx = k % w, ky = (k / w) | 0, i = k * 4;
      var nb = [[kx - 1, ky], [kx + 1, ky], [kx, ky - 1], [kx, ky + 1]];
      for (var n = 0; n < 4; n++) {
        var nx = nb[n][0], ny = nb[n][1];
        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
        var j = ny * w + nx;
        if (bg[j]) continue;
        var jj = j * 4;
        if (!cand(jj)) continue;
        var dist = Math.abs(p[i] - p[jj]) + Math.abs(p[i + 1] - p[jj + 1]) + Math.abs(p[i + 2] - p[jj + 2]);
        if (dist > TOL) continue;
        bg[j] = 1; q[qt++] = j;
      }
    }

    // 알파 → 살짝 흐리게(경계 계단 완화) 후 지정 배경색과 합성
    var al = new Float32Array(w * h);
    for (var m = 0; m < w * h; m++) al[m] = bg[m] ? 0 : 1;
    var sm = new Float32Array(w * h);
    for (var yy = 0; yy < h; yy++) for (var xx = 0; xx < w; xx++) {
      var s = 0, c = 0;
      for (var dy = -1; dy <= 1; dy++) for (var dx = -1; dx <= 1; dx++) {
        var ax = xx + dx, ay = yy + dy;
        if (ax < 0 || ay < 0 || ax >= w || ay >= h) continue;
        s += al[ay * w + ax]; c++;
      }
      sm[yy * w + xx] = s / c;
    }
    var br = parseInt(bgHex.slice(1, 3), 16), bgc = parseInt(bgHex.slice(3, 5), 16), bb = parseInt(bgHex.slice(5, 7), 16);
    for (var t = 0; t < w * h; t++) {
      var a = sm[t], o = t * 4;
      p[o] = Math.round(p[o] * a + br * (1 - a));
      p[o + 1] = Math.round(p[o + 1] * a + bgc * (1 - a));
      p[o + 2] = Math.round(p[o + 2] * a + bb * (1 - a));
      p[o + 3] = 255;
    }
    cx.putImageData(d, 0, 0);
    return cv;
  }

  /* ── 우하단만 둥근 사각형 경로 ── */
  function blockPath(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x, y);
    c.lineTo(x + w, y);
    c.lineTo(x + w, y + h - r);
    c.arcTo(x + w, y + h, x + w - r, y + h, r);
    c.lineTo(x, y + h);
    c.closePath();
  }

  function lines(v) {
    return String(v || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
  }
  function val(id) { var e = document.getElementById(id); return e ? e.value : ''; }

  /* ══ 렌더 ══ */
  function render(canvas, s) {
    var c = canvas.getContext('2d');
    canvas.width = G.W * s; canvas.height = G.H * s;
    /* ★카드가 판형을 꽉 채우게 한다 (2026-08-07 GM 지시).
       이전에는 938×760 전체를 회색 매트(#606060)로 깔고 그 안에 852×688 카드를 얹었다.
       그 결과 사방에 회색 테두리(상40·하32·좌36·우50)가 남아 인쇄물이 규격에 안 맞았다.
       그리기 좌표는 기존 카드 좌표계를 그대로 두고, 변환으로 카드 영역을 캔버스 전체에 대응시킨다
       — 좌표 상수를 건드리지 않아 글자·사진 위치 비율이 원본 그대로 유지된다. */
    var fx = G.W / G.card.w, fy = G.H / G.card.h;
    c.setTransform(s * fx, 0, 0, s * fy, -G.card.x * s * fx, -G.card.y * s * fy);
    c.textBaseline = 'alphabetic';

    c.fillStyle = '#fff'; c.fillRect(G.card.x, G.card.y, G.card.w, G.card.h);

    // 사진 블록
    c.save();
    blockPath(c, G.block.x, G.block.y, G.block.w, G.block.h, G.block.r);
    c.fillStyle = G.block.bg; c.fill(); c.clip();
    var src = state.cut || state.img;
    if (src) {
      var sw = src.width || src.naturalWidth, sh = src.height || src.naturalHeight;
      var base = Math.max(G.block.w / sw, G.block.h / sh);
      var k = base * state.zoom;
      var dw = sw * k, dh = sh * k;
      var dx = G.block.x + (G.block.w - dw) / 2 + state.offX;
      var dy = G.block.y + (G.block.h - dh) / 2 + state.offY;
      c.drawImage(src, dx, dy, dw, dh);
    }
    c.restore();

    // W 마크
    if (state.wmark) {
      var wr = state.wmark.naturalHeight / state.wmark.naturalWidth;
      c.drawImage(state.wmark, G.wm.x, G.wm.y, G.wm.w, G.wm.w * wr);
    }

    // ── 텍스트 ──
    var tx = G.text.x, tw = G.text.right - G.text.x;
    var y = G.nameTop;

    var nameKo = val('pwName') || '이름';
    c.fillStyle = '#1f1f1f'; c.font = font(700, G.nameSize);
    c.fillText(nameKo, tx, y + G.nameSize * 0.79);

    var badge = val('pwBadge').trim();
    if (badge) {
      var bw = c.measureText(nameKo).width;
      c.font = font(600, 17);
      var pw = c.measureText(badge).width, padX = 16, bh = 30;
      var bx = tx + bw + 12, by = y + G.nameSize * 0.79 - 24;
      c.fillStyle = '#efe4d7';
      if (c.roundRect) { c.beginPath(); c.roundRect(bx, by, pw + padX * 2, bh, 999); c.fill(); }
      else c.fillRect(bx, by, pw + padX * 2, bh);
      c.fillStyle = '#8a6b4c';
      c.fillText(badge, bx + padX, by + 21);
    }
    y += G.nameSize + 4;

    c.fillStyle = '#1f1f1f'; c.font = font(700, G.enSize);
    c.fillText(val('pwNameEn'), tx, y + G.enSize * 0.79);
    y += G.enSize + G.secGap;   // 첫 구분선이 원본과 같은 y=218 에 오도록

    [['경력사항', 'pwCareer'], ['자격사항', 'pwCert'], ['주요 프로그램', 'pwProgram']].forEach(function (sec) {
      var items = lines(val(sec[1]));
      if (!items.length) return;
      c.strokeStyle = G.secColor; c.lineWidth = 1.5;
      c.beginPath(); c.moveTo(tx, y + 0.75); c.lineTo(G.text.right, y + 0.75); c.stroke();
      c.fillStyle = G.secColor; c.font = font(600, G.secTitle);
      c.fillText(sec[0], tx, y + 9 + G.secTitle * 0.82);
      y += 9 + G.secTitle + 8;

      c.fillStyle = '#232323'; c.font = font(500, G.body);
      items.forEach(function (it) {
        c.fillStyle = '#555'; c.fillText('·', tx + 1, y + G.body * 0.82);
        c.fillStyle = '#232323';
        var t = it, m = tw - 12;
        while (c.measureText(t).width > m && t.length > 4) t = t.slice(0, -2);
        if (t !== it) t = t.slice(0, -1) + '…';
        c.fillText(t, tx + 12, y + G.body * 0.82);
        y += G.bodyLh;
      });
      y += 22;
    });
  }

  /* ══ UI 배선 ══ */
  function draw() {
    var cv = document.getElementById('pwCanvas');
    if (cv) render(cv, 1);
  }

  function onPhoto(file) {
    if (!file) return;
    var url = URL.createObjectURL(file);
    var im = new Image();
    im.onload = function () {
      state.img = im; state.cut = null;
      state.zoom = 1; state.offX = 0; state.offY = 0;
      var z = document.getElementById('pwZoom'); if (z) z.value = 100;
      var ox = document.getElementById('pwOffX'); if (ox) ox.value = 0;
      var oy = document.getElementById('pwOffY'); if (oy) oy.value = 0;
      if (document.getElementById('pwCut').checked) doCut();
      else draw();
    };
    im.src = url;
  }

  function doCut() {
    if (!state.img) return;
    var st = document.getElementById('pwStatus');
    if (st) st.textContent = '배경 제거 중…';
    setTimeout(function () {
      try {
        state.cut = cutout(state.img, parseInt(val('pwLum') || '115', 10), G.block.bg);
        if (st) st.textContent = '배경 제거 완료';
      } catch (e) {
        state.cut = null;
        if (st) st.textContent = '배경 제거 실패 — 원본 사진으로 진행합니다';
      }
      draw();
    }, 30);
  }

  function download() {
    var out = document.createElement('canvas');
    render(out, SC);
    out.toBlob(function (b) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(b);
      var parts = [val('pwSport'), val('pwName'), val('pwBadge')].filter(Boolean);
      a.download = (parts.join(' ') || '프로필') + ' 프로필.png';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 3000);
    }, 'image/png');
  }

  function init() {
    if (!document.getElementById('pwCanvas')) return;
    var wm = new Image();
    wm.onload = function () { state.wmark = wm; draw(); };
    wm.src = A + 'wmark.png';

    ['pwName', 'pwNameEn', 'pwBadge', 'pwCareer', 'pwCert', 'pwProgram'].forEach(function (id) {
      var e = document.getElementById(id);
      if (e) e.addEventListener('input', draw);
    });
    document.getElementById('pwPhoto').addEventListener('change', function (ev) { onPhoto(ev.target.files[0]); });
    document.getElementById('pwCut').addEventListener('change', function (ev) {
      if (ev.target.checked) doCut(); else { state.cut = null; draw(); }
    });
    document.getElementById('pwLum').addEventListener('change', function () {
      if (document.getElementById('pwCut').checked) doCut();
    });
    document.getElementById('pwZoom').addEventListener('input', function (e) { state.zoom = e.target.value / 100; draw(); });
    document.getElementById('pwOffX').addEventListener('input', function (e) { state.offX = +e.target.value; draw(); });
    document.getElementById('pwOffY').addEventListener('input', function (e) { state.offY = +e.target.value; draw(); });
    document.getElementById('pwDownload').addEventListener('click', download);

    loadFonts().then(draw);
    draw();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
