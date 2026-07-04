/*
  웰페리온 공용 인쇄 옵션 드롭다운 — _assets/print_options.js
  ────────────────────────────────────────────────────────────────
  사용법: 페이지 <head> 또는 </body> 직전에 한 줄만 삽입.
    <script src="/wellperion-automation/_assets/print_options.js"></script>

  동작:
    1) 페이지의 기존 인쇄 트리거([onclick*="print"] 또는 텍스트에 🖨️/인쇄 포함된 a·button)를
       탐지해 "🖨️ 인쇄 ▾" 드롭다운 버튼으로 승격(같은 자리·같은 class 상속). 못 찾으면 아무 것도 안 함.
    2) 드롭다운: 용지(A4/A3) · 방향(세로/가로) · 인쇄 항목(전체 + 섹션별 체크박스, h2 제목 자동 감지).
    3) 적용: 용지·방향 변경 → <style id="po-page-style"> @page 규칙을 페이지 자체 @page보다 뒤에
       주입(문서상 나중 = 우선, !important 불필요). 항목 해제 → 해당 섹션에 po-print-hide 클래스
       (@media print에서만 display:none) 부여. 기존 @media print CSS와 비파괴적으로 공존.
    4) 마지막 선택은 localStorage(wlp_print_opts)에 기억, 다음 방문 시 복원.
    5) 자체완결(외부 CSS/JS 의존 0). 페이지 CSS 변수(--paper·--text·--border-strong·--accent 등)가
       있으면 그대로 흡수, 없으면 라이트/다크 자동 중립색 폴백.

  비파괴 원칙: 기존 DOM 구조를 재배치하지 않는다(섹션 그룹핑은 클래스 부여만). 트리거 승격 외에는
  페이지의 다른 요소를 건드리지 않는다.
*/
(function(){
  'use strict';
  if(window.__wlpPrintOptions) return;   // 중복 include 가드
  window.__wlpPrintOptions = true;

  var STORE_KEY = 'wlp_print_opts';

  // ── 유틸 ──
  function slug(s){
    return String(s || '').trim().toLowerCase()
      .replace(/[^a-z0-9ㄱ-ㆎ가-힣]+/g, '-')
      .replace(/(^-+|-+$)/g, '') || 'sec';
  }
  function truncate(s, n){
    s = String(s || '').trim().replace(/\s+/g, ' ');
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }
  function loadState(){
    try{ return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {}; }catch(e){ return {}; }
  }
  function saveState(st){
    try{ localStorage.setItem(STORE_KEY, JSON.stringify(st)); }catch(e){}
  }

  // ── 1) 기존 인쇄 트리거 탐지 ──
  function findTrigger(){
    var byAttr = document.querySelector('[onclick*="print"]');
    if(byAttr) return byAttr;
    var cands = document.querySelectorAll('a, button');
    for(var i = 0; i < cands.length; i++){
      var t = cands[i].textContent || '';
      if(t.indexOf('🖨') !== -1 || t.indexOf('인쇄') !== -1) return cands[i]; // 🖨
    }
    return null;
  }

  // ── 섹션 자동 감지: h2 제목 기준 그룹핑(또는 최상위 section/article) ──
  function findCommonParent(nodes){
    if(!nodes.length) return document.body;
    var chain = [], n = nodes[0];
    while(n){ chain.push(n); n = n.parentElement; }
    for(var i = 0; i < chain.length; i++){
      var ok = true;
      for(var j = 1; j < nodes.length; j++){
        if(!chain[i].contains(nodes[j])){ ok = false; break; }
      }
      if(ok) return chain[i];
    }
    return document.body;
  }

  function detectSections(){
    // 우선순위 1: 최상위 <section>/<article> 2개 이상이면 그대로 사용
    var semantic = [];
    ['body', '.wrap', 'main', '#app'].forEach(function(sel){
      var host = sel === 'body' ? document.body : document.querySelector(sel);
      if(!host) return;
      Array.prototype.forEach.call(host.children, function(c){
        if(/^(SECTION|ARTICLE)$/.test(c.tagName) && semantic.indexOf(c) === -1) semantic.push(c);
      });
    });
    if(semantic.length >= 2){
      return semantic.map(function(el, i){
        var h = el.querySelector('h1,h2,h3,h4');
        var label = truncate(h ? h.textContent : ('섹션 ' + (i + 1)), 26);
        return { key: slug(label) + '-' + i, label: label, els: [el] };
      });
    }
    // 우선순위 2: h2 기준 그룹핑 — h2(또는 h2를 품은 블록)를 새 섹션 시작점으로,
    // 첫 h2 이전 콘텐츠(헤더·배너 등)는 토글 대상에서 제외(항상 인쇄).
    var h2s = Array.prototype.slice.call(document.querySelectorAll('h2'));
    if(!h2s.length) return [];
    var root = findCommonParent(h2s);
    var children = Array.prototype.slice.call(root.children);
    var sections = [], current = null;
    children.forEach(function(child){
      var ownH2 = child.tagName === 'H2' ? child : null;
      var nestedH2 = !ownH2 ? child.querySelector('h2') : null;
      if(ownH2 || nestedH2){
        var h = ownH2 || nestedH2;
        var label = truncate(h.textContent, 26);
        current = { key: slug(label) + '-' + sections.length, label: label, els: [child] };
        sections.push(current);
      } else if(current){
        current.els.push(child);
      }
    });
    return sections;
  }

  // ── 위젯 CSS(1회 주입) — 페이지 테마 변수 흡수 + 중립 폴백(라이트/다크 자동) ──
  function injectWidgetStyle(){
    if(document.getElementById('po-style')) return;
    var css =
      '.po-wrap{position:relative; display:inline-block;' +
        '--po-fb-bg:#ffffff; --po-fb-text:#18181b; --po-fb-border:#d8d8d8; --po-fb-surface:#f2f2f4; --po-fb-dim:#84848c; --po-fb-accent:#6d5acd;}' +
      '@media (prefers-color-scheme: dark){ .po-wrap{ --po-fb-bg:#201f23; --po-fb-text:#f2f0ee; --po-fb-border:#423f47; --po-fb-surface:#2a2830; --po-fb-dim:#96939c; --po-fb-accent:#8f7cf0; } }' +
      '.po-toggle{font:inherit; background:transparent; -webkit-appearance:none; appearance:none;}' +
      '.po-panel{position:absolute; top:calc(100% + 6px); right:0; z-index:9999; min-width:236px; max-width:290px;' +
        'background:var(--paper,var(--po-fb-bg)); color:var(--text,var(--po-fb-text));' +
        'border:1px solid var(--border-strong,var(--po-fb-border)); border-radius:11px;' +
        'box-shadow:0 10px 30px rgba(0,0,0,0.24); padding:12px 14px; font-size:12px; line-height:1.5;' +
        'font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;}' +
      '.po-panel[hidden]{display:none;}' +
      '.po-row{margin-bottom:10px;}' +
      '.po-row:last-of-type{margin-bottom:0;}' +
      '.po-label{display:block; font-size:10px; font-weight:700; letter-spacing:0.02em; text-transform:uppercase;' +
        'color:var(--dim,var(--po-fb-dim)); margin-bottom:6px;}' +
      '.po-seg{display:flex; gap:5px; flex-wrap:wrap;}' +
      '.po-chip{font-size:11.5px; padding:4px 11px; border-radius:20px; cursor:pointer; line-height:1.4;' +
        'border:1px solid var(--border-strong,var(--po-fb-border)); background:var(--surface,var(--po-fb-surface));' +
        'color:var(--text,var(--po-fb-text)); font-family:inherit;}' +
      '.po-chip.on{background:var(--accent,var(--po-fb-accent)); border-color:var(--accent,var(--po-fb-accent)); color:#fff;}' +
      '.po-chip:focus-visible{outline:2px solid var(--accent,var(--po-fb-accent)); outline-offset:2px;}' +
      '.po-sep{border:none; border-top:1px dashed var(--border,var(--po-fb-border)); margin:8px 0;}' +
      '.po-sections{max-height:180px; overflow-y:auto; padding-right:2px; margin-top:2px;}' +
      '.po-chk{display:flex; align-items:center; gap:7px; padding:2.5px 0; cursor:pointer; font-size:11.5px;}' +
      '.po-chk input{cursor:pointer; accent-color:var(--accent,var(--po-fb-accent));}' +
      '.po-chk-all{font-weight:700; margin-bottom:3px;}' +
      '.po-print-btn{width:100%; margin-top:10px; padding:7.5px 10px; border:none; border-radius:8px; cursor:pointer;' +
        'font-size:12.5px; font-weight:700; font-family:inherit; background:var(--accent,var(--po-fb-accent)); color:#fff;}' +
      '.po-print-btn:hover{filter:brightness(1.08);}' +
      '.po-print-btn:focus-visible{outline:2px solid var(--accent,var(--po-fb-accent)); outline-offset:2px;}' +
      // 폴백(트리거 없는 페이지) 전용: 화면 우상단 고정 미니 버튼. .po-toggle 리셋 위에 자체 시각 chrome만 얹음
      // — 기존 트리거 승격 케이스(.po-toggle만 쓰고 페이지 class를 같이 상속)에는 영향 없음(별도 modifier class).
      '.po-toggle.po-toggle-fallback{display:inline-flex; align-items:center; gap:2px; white-space:nowrap;' +
        'font-size:12px; padding:6px 12px; border-radius:20px;' +
        'background:var(--paper,var(--po-fb-bg)); color:var(--accent-soft,var(--text,var(--po-fb-text)));' +
        'border:1px solid var(--border-strong,var(--po-fb-border)); box-shadow:0 4px 14px rgba(0,0,0,0.18);}' +
      '.po-toggle.po-toggle-fallback:hover{filter:brightness(1.06);}' +
      '.po-wrap.po-floating{position:fixed; top:12px; right:12px;}' +
      '@media print{ .po-print-hide{ display:none !important; } .po-wrap{ display:none !important; } }';
    var st = document.createElement('style');
    st.id = 'po-style';
    st.textContent = css;
    document.head.appendChild(st);
  }

  // ── @page 동적 주입(문서상 나중 = 페이지 자체 @page 규칙보다 우선) ──
  function ensurePageStyleEl(){
    var el = document.getElementById('po-page-style');
    if(!el){
      el = document.createElement('style');
      el.id = 'po-page-style';
      document.head.appendChild(el);
    }
    return el;
  }
  function applyPageStyle(paper, orientation){
    ensurePageStyleEl().textContent = '@page{ size: ' + paper + ' ' + orientation + '; margin: 8mm; }';
  }
  function applySections(sections, checkedMap){
    sections.forEach(function(sec){
      var hide = checkedMap[sec.key] === false;
      sec.els.forEach(function(el){ el.classList.toggle('po-print-hide', hide); });
    });
  }

  function init(){
    var trigger = findTrigger();
    var isFallback = !trigger; // 인쇄 트리거가 없는 페이지 — 플로팅 버튼을 스스로 생성(전 페이지 커버리지)
    injectWidgetStyle();

    var sections = detectSections();
    var state = loadState();
    var paper = (state.paper === 'A3') ? 'A3' : 'A4';
    var orientation = (state.orientation === 'landscape') ? 'landscape' : 'portrait';
    var checked = {};
    sections.forEach(function(sec){
      checked[sec.key] = (state.sections && Object.prototype.hasOwnProperty.call(state.sections, sec.key))
        ? !!state.sections[sec.key] : true;
    });

    function persist(){ saveState({ paper: paper, orientation: orientation, sections: checked }); }
    function apply(){ applyPageStyle(paper, orientation); applySections(sections, checked); }

    // ── DOM 구성 ──
    var wrap = document.createElement('span');
    wrap.className = 'po-wrap' + (isFallback ? ' po-floating' : '');

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'po-toggle-btn';
    btn.className = 'po-toggle' + (isFallback ? ' po-toggle-fallback' : '') +
      (trigger && trigger.className ? (' ' + trigger.className) : '');
    btn.setAttribute('aria-haspopup', 'true');
    btn.setAttribute('aria-expanded', 'false');
    btn.textContent = '🖨️ 인쇄 ▾'; // 🖨️ 인쇄 ▾

    var panel = document.createElement('div');
    panel.id = 'po-panel';
    panel.className = 'po-panel';
    panel.setAttribute('role', 'menu');
    panel.hidden = true;

    // 용지
    var rowPaper = document.createElement('div');
    rowPaper.className = 'po-row';
    var lblPaper = document.createElement('span'); lblPaper.className = 'po-label'; lblPaper.textContent = '용지';
    var segPaper = document.createElement('div'); segPaper.className = 'po-seg';
    ['A4', 'A3'].forEach(function(p){
      var c = document.createElement('button');
      c.type = 'button';
      c.className = 'po-chip' + (paper === p ? ' on' : '');
      c.textContent = p;
      c.setAttribute('aria-pressed', String(paper === p));
      c.addEventListener('click', function(){
        paper = p;
        Array.prototype.forEach.call(segPaper.children, function(x){ x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
        c.classList.add('on'); c.setAttribute('aria-pressed', 'true');
        persist(); apply();
      });
      segPaper.appendChild(c);
    });
    rowPaper.appendChild(lblPaper); rowPaper.appendChild(segPaper);

    // 방향
    var rowOri = document.createElement('div');
    rowOri.className = 'po-row';
    var lblOri = document.createElement('span'); lblOri.className = 'po-label'; lblOri.textContent = '방향';
    var segOri = document.createElement('div'); segOri.className = 'po-seg';
    [['portrait', '세로'], ['landscape', '가로']].forEach(function(pair){
      var val = pair[0], text = pair[1];
      var c = document.createElement('button');
      c.type = 'button';
      c.className = 'po-chip' + (orientation === val ? ' on' : '');
      c.textContent = text;
      c.setAttribute('aria-pressed', String(orientation === val));
      c.addEventListener('click', function(){
        orientation = val;
        Array.prototype.forEach.call(segOri.children, function(x){ x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
        c.classList.add('on'); c.setAttribute('aria-pressed', 'true');
        persist(); apply();
      });
      segOri.appendChild(c);
    });
    rowOri.appendChild(lblOri); rowOri.appendChild(segOri);

    panel.appendChild(rowPaper);
    panel.appendChild(rowOri);

    // 인쇄 항목(섹션 자동 감지 결과가 있을 때만 노출)
    if(sections.length){
      var hr = document.createElement('hr'); hr.className = 'po-sep';
      panel.appendChild(hr);

      var rowItems = document.createElement('div'); rowItems.className = 'po-row';
      var lblItems = document.createElement('span'); lblItems.className = 'po-label'; lblItems.textContent = '인쇄 항목';
      rowItems.appendChild(lblItems);

      var allLbl = document.createElement('label'); allLbl.className = 'po-chk po-chk-all';
      var allChk = document.createElement('input'); allChk.type = 'checkbox'; allChk.id = 'po-chk-all';
      var allSpan = document.createElement('span'); allSpan.textContent = '전체';
      allLbl.appendChild(allChk); allLbl.appendChild(allSpan);
      rowItems.appendChild(allLbl);

      var secWrap = document.createElement('div'); secWrap.className = 'po-sections';
      var secChecks = [];
      sections.forEach(function(sec){
        var lbl = document.createElement('label'); lbl.className = 'po-chk';
        var chk = document.createElement('input'); chk.type = 'checkbox'; chk.checked = !!checked[sec.key];
        chk.setAttribute('data-sec-key', sec.key);
        var span = document.createElement('span'); span.textContent = sec.label;
        lbl.appendChild(chk); lbl.appendChild(span);
        secWrap.appendChild(lbl);
        secChecks.push(chk);
        chk.addEventListener('change', function(){
          checked[sec.key] = chk.checked;
          syncAllState();
          persist(); apply();
        });
      });
      rowItems.appendChild(secWrap);
      panel.appendChild(rowItems);

      function syncAllState(){
        var total = secChecks.length;
        var onCount = secChecks.filter(function(c){ return c.checked; }).length;
        allChk.checked = onCount === total;
        allChk.indeterminate = onCount > 0 && onCount < total;
      }
      syncAllState();

      allChk.addEventListener('change', function(){
        var on = allChk.checked;
        allChk.indeterminate = false;
        secChecks.forEach(function(c, i){ c.checked = on; checked[sections[i].key] = on; });
        persist(); apply();
      });
    }

    var printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.className = 'po-print-btn';
    printBtn.textContent = '🖨️ 인쇄'; // 🖨️ 인쇄
    printBtn.addEventListener('click', function(){
      apply();
      closePanel();
      setTimeout(function(){ window.print(); }, 20);
    });
    panel.appendChild(printBtn);

    function openPanel(){
      panel.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      document.addEventListener('mousedown', onDocClick, true);
      document.addEventListener('keydown', onKeyDown, true);
    }
    function closePanel(){
      panel.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
      document.removeEventListener('mousedown', onDocClick, true);
      document.removeEventListener('keydown', onKeyDown, true);
    }
    function onDocClick(e){ if(!wrap.contains(e.target)) closePanel(); }
    function onKeyDown(e){ if(e.key === 'Escape'){ closePanel(); btn.focus(); } }

    btn.addEventListener('click', function(){
      if(panel.hidden) openPanel(); else closePanel();
    });

    wrap.appendChild(btn);
    wrap.appendChild(panel);

    if(isFallback){
      document.body.appendChild(wrap); // 트리거 없는 페이지 — 우상단 플로팅으로 스스로 부착
    } else {
      trigger.parentNode.replaceChild(wrap, trigger); // 트리거 있는 페이지 — 기존대로 그 자리에 승격
    }

    apply(); // 저장된 선택 즉시 반영(초기 @page·섹션 숨김)
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
