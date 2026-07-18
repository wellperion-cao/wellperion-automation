/* ════════════════════════════════════════════════════════════════════
   웰페리온 공용 상단 네비 — 단일 소스 공유 컴포넌트 (정본 · 이 파일만 편집)
   삽입: 페이지에 <div id="wlp-nav"></div> + <script src="/wellperion-automation/_assets/wlp_nav.js"></script>
   자족형(외부 fetch 없음 · 데이터 인라인) · 파일럿: 월간운영계획.html (2026-07-18)
   ════════════════════════════════════════════════════════════════════ */
(function(){
  'use strict';

  var ROOT = '/wellperion-automation/';

  // 담당자 그룹 — 순서·라벨·URL 단일 정본. kind:'screen'=화면소유(페이지명 소링크 노출) / 'domain'=도메인소유(칩만)
  var GROUPS = [
    { nick:'웰리', title:'AI CEO', kind:'screen', pages:[
      { label:'헌법한장', href: ROOT + '헌법한장.html' },
      { label:'오늘의 항로 (G1)', href: ROOT + 'wellperion_guide(main).html#G1' }
    ]},
    { nick:'시토', title:'AI CTO', kind:'screen', pages:[
      { label:'자율 작업 현황', href: ROOT + '자율현황.html' }
    ]},
    { nick:'시우', title:'AI COO', kind:'screen', pages:[
      { label:'월간 운영', href: ROOT + '월간운영계획.html' },
      { label:'전사 일정', href: ROOT + 'coo/check/전사_일정.html' }
    ]},
    { nick:'시모', title:'AI CMO', kind:'domain', pages:[
      { label:'시모 AI CMO', href: ROOT + 'wellperion_guide(main).html#M1' }
    ]},
    { nick:'시포', title:'AI CPO', kind:'domain', pages:[
      { label:'시포 AI CPO', href: ROOT + 'cpo/member/문의회원.html' }
    ]},
    { nick:'시로', title:'AI CHRO', kind:'domain', pages:[
      { label:'시로 AI CHRO', href: ROOT + 'coo/todo/업무 현황 SSOT.html' }
    ]},
    { nick:'시뽀', title:'AI CFO', kind:'domain', pages:[
      { label:'시뽀 AI CFO', href: ROOT + 'cfo/finance/매출지출현황.html' }
    ]}
  ];

  function esc(s){
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  // 현재 페이지 판정 = location.pathname(디코드) 파일명 기준(로컬 file:// · 라이브 GitHub Pages 양쪽 대응). 링크에 #해시가 있으면 location.hash도 일치해야 함.
  function isCurrent(href){
    var hashIdx = href.indexOf('#');
    var hash = hashIdx >= 0 ? href.slice(hashIdx) : '';
    var path = hashIdx >= 0 ? href.slice(0, hashIdx) : href;
    var base = path.split('/').pop();
    try{ base = decodeURIComponent(base); }catch(e){}
    var curBase = location.pathname.split('/').pop();
    try{ curBase = decodeURIComponent(curBase); }catch(e){}
    if(base !== curBase) return false;
    if(hash) return hash === location.hash;
    return true;
  }

  function renderGroup(g){
    var repHref = g.pages[0].href;
    var repCur = isCurrent(repHref);
    var html = '<span class="wlp-grp">';
    html += '<a class="wlp-role' + (repCur ? ' wlp-cur' : '') + '" href="' + esc(repHref) + '">' + esc(g.nick) + ' ' + esc(g.title) + '</a>';
    if(g.kind === 'screen'){
      html += '<span class="wlp-pages">';
      g.pages.forEach(function(p, i){
        if(i > 0) html += '<span class="wlp-sep">·</span>';
        var cur = isCurrent(p.href);
        html += '<a class="wlp-page' + (cur ? ' wlp-cur' : '') + '" href="' + esc(p.href) + '">' + esc(p.label) + '</a>';
      });
      html += '</span>';
    }
    html += '</span>';
    return html;
  }

  function injectStyle(){
    if(document.getElementById('wlp-nav-style')) return;
    // 중립색 전략(GM 지시): prefers-color-scheme(OS 설정)은 페이지 자체의 밝기와 무관해 불일치가 나므로 사용 안 함.
    // 기본 텍스트=color:inherit(호스트 페이지가 이미 자기 배경에 맞춰 고른 색을 그대로 승계=항상 읽힘).
    // 링크=currentColor에 골드를 혼합(color-mix)해 포인트색 부여하되 명도는 호스트 색을 따라가 밝은/어두운 배경 양쪽에서 대비 유지.
    var css = ''
      + '.wlp-nav{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;font:inherit;font-size:12px;line-height:1.7;padding:7px 12px;margin:0 0 14px;border-radius:10px;background:rgba(127,127,127,0.12);border:1px solid rgba(127,127,127,0.32);color:inherit;}'
      + '.wlp-nav .wlp-grp{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap;}'
      + '.wlp-nav .wlp-pages{display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap;}'
      + '.wlp-nav a{color:color-mix(in srgb, currentColor 60%, #e8b84b 40%);text-decoration:none;}'
      + '.wlp-nav a:hover{text-decoration:underline;}'
      + '.wlp-nav .wlp-role{font-weight:800;}'
      + '.wlp-nav .wlp-page{font-weight:500;}'
      + '.wlp-nav .wlp-sep,.wlp-nav .wlp-div{opacity:0.5;}'
      + '.wlp-nav .wlp-div{margin:0 2px;}'
      + '.wlp-nav a.wlp-cur{background:rgba(127,127,127,0.30);border-radius:14px;padding:1px 9px;font-weight:800;}'
      + '@media (max-width:720px){.wlp-nav{gap:5px 9px;font-size:11px;padding:6px 10px;}}';
    var tag = document.createElement('style');
    tag.id = 'wlp-nav-style';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  function render(){
    var mount = document.getElementById('wlp-nav');
    if(!mount) return;
    var body = GROUPS.map(renderGroup).join('<span class="wlp-div">│</span>');
    mount.innerHTML = '<nav class="wlp-nav" aria-label="웰페리온 네비게이션">' + body + '</nav>';
  }

  injectStyle();
  render();
})();
