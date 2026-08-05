/* board_sync.js — 부서 보드 백엔드 동기화 공용 엔진.
   운영부/지원부/시설부/주차관리부 체계.html 4곳에 복붙돼 있던 load*FromBackend/persist*Data
   17벌(약 470줄)을 대체. 각 페이지의 데이터 모델·렌더·편집 로직은 그대로 두고,
   "GAS 백엔드에서 읽고/쓰고, localStorage 폴백하고, IME 입력 중엔 재렌더를 보류한다"는
   공통 배관만 여기로 뽑았다. (GM 2026-08-05 웰리 위임 — 모듈 병합)

   사용법 (페이지 쪽 코드):
     const XXX_SYNC_CFG = {
       key: XXX_STORAGE_KEY,        // localStorage/GAS 저장 키
       wrapId: 'xxx-board',         // 편집 중(IME) 여부를 검사할 DOM 컨테이너 id
       guard: 'cell',               // 'cell'  = .dv-cell.editing 존재 시 재렌더 보류(카드 보드)
                                     // 'focus' = wrap 안에 포커스 있으면 보류(입력 표)
       localLoad: loadXxxData,      // 기존 로컬(localStorage) 로더 — 그대로 재사용
       apply: applyXxxStored,       // 기존 stored→전역 데이터 반영 함수 — 그대로 재사용
       render: renderXxxBoard,      // 기존 렌더 함수 — 그대로 재사용
       getData: function(){ return XXX_DATA; },  // 저장 시 보낼 현재 데이터
       label: '규정',                // 저장 인디케이터 문구("○○ 저장 중...")
       renderBeforeFetch: false,    // true면 fetch 전에도 1회 즉시 렌더(일부 페이지 원래 동작 보존용)
       action: 'board', saveAction: 'saveBoard'   // GAS action 이름(대부분 기본값 그대로)
     };
     async function loadXxxFromBackend(){ return BoardSync.load(XXX_SYNC_CFG); }
     function persistXxxData(){ return BoardSync.persist(XXX_SYNC_CFG); }        // 즉시 저장
     function persistXxxData(){ return BoardSync.persistDebounced(XXX_SYNC_CFG); } // 800ms 코일싱 저장(입력표형)

   ⚠ cfg 객체는 반드시 "한 번만 만들어진 안정적인 참조"여야 한다(매 호출마다 새로 만들면 안 됨) —
      persistDebounced가 cfg 위에 타이머(_timer)를 붙여 재사용하기 때문. */
var BoardSync = (function(){
  function isEditing(wrap, guard){
    if(!wrap) return false;
    if(guard==='focus') return wrap.contains(document.activeElement);
    return !!wrap.querySelector('.dv-cell.editing');
  }
  function guardedRender(cfg){
    var wrap = document.getElementById(cfg.wrapId);
    if(wrap && !isEditing(wrap, cfg.guard)) cfg.render();
  }
  async function load(cfg){
    cfg.localLoad();
    if(cfg.renderBeforeFetch) cfg.render();
    if(!ONLINE) return;
    try{
      var res = await fetch(API_URL+'?action='+(cfg.action||'board')+'&key='+encodeURIComponent(cfg.key), {method:'GET', redirect:'follow'});
      var data = await res.json();
      if(data && data.ok && data.board && typeof data.board==='object'){
        cfg.apply(data.board);
        localStorage.setItem(cfg.key, JSON.stringify(cfg.getData()));
      }
      // data.board===null → 백엔드에 아직 없음 → 로컬/시드 유지(이후 첫 저장 시 백엔드에 기록)
    }catch(e){ /* 네트워크 실패 → 이미 로드된 localStorage/시드 유지 */ }
    guardedRender(cfg);
  }
  function push(cfg){
    var ind = document.getElementById('saveIndicator');
    if(ind){ind.style.display='block'; ind.textContent=cfg.label+' 저장 중...';}
    fetch(API_URL,{method:'POST',redirect:'follow',
      headers:{'Content-Type':'text/plain'},
      body:JSON.stringify({action:cfg.saveAction||'saveBoard', key:cfg.key, board:cfg.getData()})
    }).then(function(){ if(ind){ind.textContent=cfg.label+' 저장 완료'; setTimeout(function(){ind.style.display='none';},1500);} })
      .catch(function(){ if(ind){ind.textContent=cfg.label+' 저장 (로컬 보관됨)'; setTimeout(function(){ind.style.display='none';},1500);} });
  }
  function persist(cfg){
    localStorage.setItem(cfg.key, JSON.stringify(cfg.getData()));
    if(!ONLINE) return;
    push(cfg);
  }
  function persistDebounced(cfg){
    localStorage.setItem(cfg.key, JSON.stringify(cfg.getData()));
    if(!ONLINE) return;
    clearTimeout(cfg._timer);
    cfg._timer = setTimeout(function(){ push(cfg); }, cfg.debounceMs||800);
  }
  return {load:load, persist:persist, persistDebounced:persistDebounced};
})();
