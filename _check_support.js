
const API_URL = 'https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec';
const ONLINE = API_URL.length > 0;
const DEPT = 'support';
function withDept(obj){ obj.dept = DEPT; return obj; }
const DEPT_Q = '&dept=' + encodeURIComponent(DEPT);
const STAFF_CSV_URL = 'https://docs.google.com/spreadsheets/d/1DKEKRrpsi9Nit7dNdNGsXLYtzie3PopbwD7EJzJCku0/gviz/tq?tqx=out:csv&sheet=%EC%A0%90%EA%B2%80%EC%9E%90';

/* ── Track which gender tab is active ── */
let activeGenderTab = 'm';

/* ── A: Staff list (fallback + dynamic) ── */
// 점검자 명단 (HTML 고정 · 시트 동적로드 비활성 GM 2026-05-29).
// 여: 이경연 실장·이연희 반장·임정은M / 남: 최준용M·김남욱GM·윤병현AM (GM 2026-06-04 추가)
const FALLBACK_STAFF = [
  {name:'지원팀 반장(여) · 이경연 실장', role:'반장', shift:'all', gender:'f'},
  {name:'이연희 반장', role:'반장', shift:'all', gender:'f'},
  {name:'임정은M', role:'점검자', shift:'all', gender:'f'},
  {name:'지원팀 반장(남) · 최준용M', role:'반장', shift:'all', gender:'m'},
  {name:'김남욱GM', role:'점검자', shift:'all', gender:'m'},
  {name:'윤병현AM', role:'점검자', shift:'all', gender:'m'}
];
let STAFF_LIST = [...FALLBACK_STAFF];

async function loadStaffFromSheet(){
  // 점검자 고정 2명(지원팀 반장 여/남) — 시트 동적 로드 비활성화 (GM 2026-05-29).
  // 기존 8명이 시트에서 다시 들어오지 않도록 STAFF_LIST는 FALLBACK 고정 유지.
  STAFF_LIST=[...FALLBACK_STAFF];
  populateSubmitterDropdowns();
  populateDutyDropdowns();
}

/* ── 점검 항목 마스터 (GM 편집 · 시트 영구 저장) ──
   CUSTOM_ITEMS = 편집 가능한 항목 마스터. 시트(점검항목 탭)와 동기화.
   프론트 항목 모델 {id, slot, shift, dayType, gender, category, name, detail}
   ↔ 시트 컬럼 {항목ID, 카테고리, 항목명, 상세, 성별, 시간대, 정렬} 매핑. */
let CUSTOM_ITEMS = [];
const ITEM_CACHE_KEY = 'wcheck_items_cache'; // 오프라인 폴백 캐시
/* 2b-1(2026-06-11 시우): 이슈→항목 승격 모달이 참조하는 항목별 렌더 컨텍스트.
   renderItem이 항목 id별로 {cat,slot,shift,round,gender}를 적립 → openPromoteFromIssue가 prefill. */
const PROMOTE_CTX = {};
let promoteSourceId = null;   // 현재 승격 진행 중인 원본 이슈 항목 id(반영완료 마킹용)

/* ── 온도 측정 대상 항목 설정 (2026-06-11 시우) ──
   key=항목ID, fields=[{key(영문),label(표시),min,max,unit}].
   매뉴얼 기준값: 건식 90~100℃ / 습식 60~70℃ / 온탕 39~42℃ / 열탕 43~45℃ / 냉탕 15~20℃.
   measure 13열에 {"건식":95,...} JSON으로 영속(GAS 측정값 패스스루 재사용 — 스키마 변경 불필요).
   기준 벗어나면 클라에서 빨간 경고만 표시(저장은 그대로 — 거짓완료 유발 안 함). */
const TEMP_CONFIG = {
  a1:   { fields:[ {key:'온탕',label:'온탕',min:39,max:42,unit:'℃'}, {key:'열탕',label:'열탕',min:43,max:45,unit:'℃'}, {key:'냉탕',label:'냉탕',min:15,max:20,unit:'℃'} ] },
  a2:   { fields:[ {key:'건식',label:'건식',min:90,max:100,unit:'℃'}, {key:'습식',label:'습식',min:60,max:70,unit:'℃'} ] }
};
function tempFieldsFor(id){ return (TEMP_CONFIG[id] && TEMP_CONFIG[id].fields) || null; }
/* STATE 온도값 키: temp_<id>_<fieldKey>. 측정값 JSON 직렬화(저장/푸시용). */
function collectTempJSON(id){
  const fields=tempFieldsFor(id); if(!fields) return '';
  const obj={}; let any=false;
  fields.forEach(f=>{ const v=STATE['temp_'+id+'_'+f.key]; if(v!==undefined&&v!==''&&v!==null){obj[f.key]=v;any=true;} });
  return any?JSON.stringify(obj):'';
}
/* 측정값 JSON(measure) → STATE 온도값 복원. */
function restoreTempFromMeasure(id,measureStr){
  if(!measureStr) return; let obj=null;
  try{ obj=JSON.parse(measureStr); }catch(e){ return; }
  if(!obj||typeof obj!=='object') return;
  Object.keys(obj).forEach(k=>{ STATE['temp_'+id+'_'+k]=obj[k]; });
}
/* 온도 입력 변경 핸들러 — 값 저장 후 즉시 재렌더(경고 갱신). */
function onTemp(id,fieldKey,elemId,gender){
  const g=gender||activeGenderTab;
  const d=getDateG(g);
  STATE['temp_'+id+'_'+fieldKey]=document.getElementById(elemId).value;
  saveState(d,g);
  drawUI(d,g);
}
/* 반영완료 토글 (2026-06-11 시우) — 이슈/노하우 후속 조치 완료 표시. STATE reflected_<id>. */
function toggleReflected(id,gender){
  const g=gender||activeGenderTab;
  const d=getDateG(g);
  STATE['reflected_'+id]=!STATE['reflected_'+id];
  saveState(d,g);
  drawUI(d,g);
}

/* ════════════════════════════════════════════════════════════
   2b-1(2026-06-11 시우·GM): 이슈 → 점검·매뉴얼 항목 원클릭 승격.
   이슈 텍스트가 달린 항목 옆 '➕ 점검·매뉴얼 항목으로' → 모달 → CUSTOM_ITEM 1개 생성
   (mgmtSaveItems 파이프라인). 회차 다중선택은 rounds로 보존 →
   점검표(선택 회차)·매뉴얼board에 단일 소스(WEEKDAY+CUSTOM_ITEMS)로 동시 등장.
   ════════════════════════════════════════════════════════════ */
/* 현재 스케줄에 등장하는 구역(group.title) 목록 — 카테고리 선택 옵션용(중복 제거, 등장순) */
function promoteZoneTitles(){
  const out=[]; const seen={};
  try{
    const d=getDateG(activeGenderTab);
    const sched=getSched(d);
    if(sched)sched.forEach(slot=>slot.groups.forEach(g=>{
      const t=g.title; if(t&&!seen[t]){seen[t]=1;out.push(t);}
    }));
  }catch(e){}
  return out;
}
/* 승격 모달 열기 — 원본 이슈 항목의 컨텍스트로 prefill. */
function openPromoteFromIssue(id,gender){
  const ctx=PROMOTE_CTX[id]||{};
  const g=gender||ctx.gender||activeGenderTab;
  promoteSourceId=id;
  // 헤더 복원(매뉴얼 신규추가 모드에서 바뀐 문구 되돌림)
  const _t=document.getElementById('promoteTitle'); if(_t)_t.textContent='이슈 → 점검·매뉴얼 항목 추가';
  const _st=document.getElementById('promoteSubtitle'); if(_st)_st.textContent='자주 발생하는 이슈를 점검표와 매뉴얼에 항목으로 등록합니다. 선택한 회차에 자동으로 등장합니다.';
  const issText=STATE['iss_'+id]||'';
  // 항목명: 이슈 텍스트 prefill(수정 가능)
  const nameEl=document.getElementById('promoteName');
  if(nameEl)nameEl.value=issText;
  // 상세: 비움(선택)
  const detEl=document.getElementById('promoteDetail');
  if(detEl)detEl.value='';
  // 성별: 기본 all
  const genEl=document.getElementById('promoteGender');
  if(genEl)genEl.value='all';
  // 구역(카테고리) 옵션 구성 + 현재 구역 선택
  const catSel=document.getElementById('promoteCatSelect');
  if(catSel){
    const titles=promoteZoneTitles();
    let opts=titles.map(t=>`<option value="${escapeAttr(t)}">${escapeHTML(t)}</option>`).join('');
    opts+='<option value="__custom__">+ 직접 입력…</option>';
    catSel.innerHTML=opts;
    catSel.disabled=false;   // 이슈 승격 경로는 구역 선택 가능(manualAddItem이 잠갔던 것 해제)
    const cur=ctx.cat||'';
    if(cur&&titles.indexOf(cur)>=0){catSel.value=cur;}
    else if(cur){catSel.value='__custom__';}
    else{catSel.value=titles.length?titles[0]:'__custom__';}
  }
  promoteOnCatChange();
  const catIn=document.getElementById('promoteCatCustom');
  if(catIn && catSel && catSel.value==='__custom__')catIn.value=ctx.cat||'';
  // 회차 체크박스: 기본=이 항목의 현재 회차들(itemRounds). 없으면 현재 라운드 또는 현재 시각 근처 조.
  let defRounds=[];
  const liveItem={id:id,slot:ctx.slot,shift:ctx.shift};
  // CUSTOM 항목이면 rounds 보유 → itemRounds가 그걸 반환. 기본 항목이면 ROUND_MAP/슬롯 폴백.
  const ci=(CUSTOM_ITEMS||[]).find(x=>x.id===id);
  if(ci)liveItem.rounds=ci.rounds;
  try{ defRounds=itemRounds(liveItem)||[]; }catch(e){ defRounds=[]; }
  if(!defRounds.length){ defRounds=[ctx.round||autoRoundForNow()]; }
  ROUND_KEYS.forEach(rk=>{
    const cb=document.getElementById('promoteRound_'+rk);
    if(cb)cb.checked=defRounds.indexOf(rk)>=0;
  });
  // 사우나 내부류 안내(3조 전부 권장)
  const hint=document.getElementById('promoteRoundHint');
  if(hint){
    const c=(ctx.cat||'');
    const sauna=c.indexOf('사우나')>=0||/^A/.test(c);
    hint.style.display=sauna?'block':'none';
  }
  const modal=document.getElementById('promoteModal');
  if(modal)modal.style.display='flex';
}
function closePromoteModal(){
  const modal=document.getElementById('promoteModal');
  if(modal)modal.style.display='none';
  promoteSourceId=null;
}
/* 구역 select 변경 — '직접 입력' 선택 시 텍스트 입력칸 표시 */
function promoteOnCatChange(){
  const sel=document.getElementById('promoteCatSelect');
  const inp=document.getElementById('promoteCatCustom');
  if(!sel||!inp)return;
  inp.style.display=(sel.value==='__custom__')?'block':'none';
}
/* 승격 저장 → CUSTOM_ITEM 1개 생성(mgmtSaveItems) → 점검표·매뉴얼 동시 등장 + 원본 이슈 반영완료 */
function promoteSave(){
  if(typeof requireEditAuth==='function' && !requireEditAuth())return;
  const id=promoteSourceId;
  const ctx=(id&&PROMOTE_CTX[id])||{};
  const g=ctx.gender||activeGenderTab;
  const nameEl=document.getElementById('promoteName');
  const name=(nameEl&&nameEl.value||'').trim();
  if(!name){ alert('항목명을 입력하세요.'); if(nameEl)nameEl.focus(); return; }
  // 구역(카테고리)
  const catSel=document.getElementById('promoteCatSelect');
  let category='';
  if(catSel){
    category=catSel.value==='__custom__'
      ? (document.getElementById('promoteCatCustom').value||'').trim()
      : catSel.value;
  }
  if(!category)category='추가 점검';
  // 회차 다중선택
  const rounds=ROUND_KEYS.filter(rk=>{const cb=document.getElementById('promoteRound_'+rk);return cb&&cb.checked;});
  if(!rounds.length){ alert('최소 1개 회차를 선택하세요.'); return; }
  // 성별 / 상세
  const gender=(document.getElementById('promoteGender')||{}).value||'all';
  const detail=((document.getElementById('promoteDetail')||{}).value||'').trim();
  // 대표 slot/shift — 선택 회차의 첫 라운드 baseShift 기준(라벨은 표시 안 됨, 폴백용)
  const firstR=roundDef(rounds[0]);
  const baseShift=firstR?firstR.baseShift:'pm';
  const slotLabel=ctx.slot||(firstR?(firstR.name+' '+firstR.time):'추가 점검');
  // 신규 CUSTOM 항목 (기존 id 생성 규칙 mgmtGenerateId 사용 — STATE 충돌 회피)
  const newItem={
    id: mgmtGenerateId(),
    slot: slotLabel,
    shift: baseShift,
    dayType: 'both',
    gender: gender,
    category: category,
    name: name,
    detail: detail,
    order: undefined,
    rounds: rounds.slice()   // 2b-1: 선택 회차 다중 — itemRounds가 이 배열 사용
  };
  const next=(CUSTOM_ITEMS||[]).concat([newItem]);
  mgmtSaveItems(next);   // CUSTOM_ITEMS 갱신 + 시트 저장(saveItems POST, 회차 포함)
  // 원본 이슈 반영완료 마킹
  if(id){
    const d=getDateG(g);
    STATE['reflected_'+id]=true;
    saveState(d,g);
  }
  closePromoteModal();
  if(typeof mgmtInjectCustomItems==='function')mgmtInjectCustomItems();
  if(typeof renderManualItems==='function')renderManualItems();
  drawUI(getDateG(g),g);
  alert('매뉴얼·점검에 추가됨\n선택한 회차 '+rounds.map(roundLabel).join(', ')+'에 등장합니다.\n(다른 기기는 Ctrl+Shift+R 새로고침)');
}

/* 시간대(slot) → 교대조(shift) 추정 (기본 항목 배열의 slot 명명 규칙 기준) */
function slotToShiftFront(slot){
  var s = slot || '';
  if(s.indexOf('야간')>=0||s.indexOf('23:')>=0||s.indexOf('00:')>=0||s.indexOf('01:')>=0||s.indexOf('02:')>=0||s.indexOf('03:')>=0||s.indexOf('20:30')>=0||s.indexOf('21:00')>=0||s.indexOf('22:00~23')>=0) return 'night';
  if(s.indexOf('상시')>=0) return 'all';
  if(s.indexOf('오픈')>=0||s.indexOf('오전')>=0||s.indexOf('05:30')>=0||s.indexOf('07:30')>=0||s.indexOf('인수인계')>=0||s.indexOf('08:00')>=0||s.indexOf('10:00')>=0) return 'am';
  return 'pm';
}

/* 2b-1(2026-06-11 시우): 시트 회차 문자열("am1,pm1") ↔ 프론트 rounds 배열 변환.
   유효 라운드 키(ROUND_KEYS)만 통과 — 오타·공백·빈값은 폐기 → 빈 배열이면 itemRounds가 폴백. */
function parseRoundsStr(s){
  if(!s) return [];
  return String(s).split(',').map(function(x){return x.trim();})
    .filter(function(x){return x && ROUND_KEYS.indexOf(x)>=0;});
}
function roundsToStr(arr){
  if(!Array.isArray(arr)) return '';
  return arr.filter(function(x){return ROUND_KEYS.indexOf(x)>=0;}).join(',');
}

/* 시트 행 → 프론트 항목 모델 */
function itemFromSheet(row){
  return {
    id: row.id || mgmtGenerateId(),
    slot: row.slot || '상시',
    shift: row.shift || slotToShiftFront(row.slot),
    dayType: row.dayType || 'both',
    gender: row.gender || 'all',
    category: row.cat || '추가 점검',
    name: row.name || '',
    detail: row.detail || '',
    order: row.order,
    rounds: parseRoundsStr(row.rounds),   // 2b-1: 회차 다중선택(빈 배열=폴백)
    sched: row.sched || ''   // 일정(요일·몇째주) "mon,wed,fri|2"
  };
}

/* 프론트 항목 모델 → 시트 행(API 계약 필드) */
function itemToSheet(it, idx){
  return {
    id: it.id,
    cat: it.category || '',
    name: it.name || '',
    detail: it.detail || '',
    gender: it.gender || 'all',
    slot: it.slot || '',
    order: (it.order !== undefined && it.order !== '') ? it.order : (idx + 1),
    type: it.type || 'check',
    fields: it.fields || '',
    rounds: roundsToStr(it.rounds),   // 2b-1: 회차 → "am1,pm1" (없으면 빈문자)
    sched: it.sched || ''   // 일정(요일·몇째주) → "mon,wed,fri|2"
  };
}

/* 시트에서 항목 마스터 로드 (loadStaffFromSheet 미러) */
async function loadItemMasterFromSheet(){
  if(!ONLINE){
    try{ CUSTOM_ITEMS = JSON.parse(localStorage.getItem(ITEM_CACHE_KEY)) || []; }catch(e){ CUSTOM_ITEMS = []; }
    return;
  }
  try{
    const res = await fetch(API_URL+'?action=items'+DEPT_Q,{method:'GET',redirect:'follow'});
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    CUSTOM_ITEMS = items.map(itemFromSheet);
    localStorage.setItem(ITEM_CACHE_KEY, JSON.stringify(CUSTOM_ITEMS)); // 오프라인 폴백
  }catch(e){
    // 실패 시 캐시 폴백, 그래도 없으면 빈 배열 (기본 항목은 항상 렌더)
    try{ CUSTOM_ITEMS = JSON.parse(localStorage.getItem(ITEM_CACHE_KEY)) || []; }catch(_){ CUSTOM_ITEMS = []; }
  }
  // 로드 후 현재 화면 갱신
  if(typeof mgmtInjectCustomItems==='function') mgmtInjectCustomItems();
  if(typeof renderManualItems==='function') renderManualItems();
}

function parseCSVLine(line){
  const result=[];let cur='',inQ=false;
  for(let i=0;i<line.length;i++){
    const c=line[i];
    if(c==='"'){if(inQ&&line[i+1]==='"'){cur+='"';i++}else{inQ=!inQ}}
    else if(c===','&&!inQ){result.push(cur.trim());cur=''}
    else{cur+=c}
  }
  result.push(cur.trim());
  return result;
}

function getStaffForGender(g){
  // g='m' or 'f'
  // Show staff matching gender or gender='all' (팀장, 탕청소 업체)
  return STAFF_LIST.filter(s=>{
    if(s.gender==='all') return true;
    return s.gender===g;
  });
}

/* R4(2026-06-11 시우): 점검자 = 자유 입력(text). 기존 명단 select 채우기는 무력화.
   저장값(localStorage)만 input에 복원. STAFF_LIST/getStaffForGender는 admin 통계 등
   참조 호환 위해 보존(호출돼도 input에는 영향 없음). */
function populateSubmitterDropdowns(){
  populateOneDropdown('submitterM','m');
  populateOneDropdown('submitterF','f');
}

/* 점검자 = 매번 빈칸 자유입력(GM 2026-06-12): 저장값 복원·옵션 채우기 모두 없음.
   '담당자(아래)'가 기억 역할을 대신한다. */
function populateOneDropdown(selId,gender){
  const el=document.getElementById(selId);
  if(!el)return;
  el.value='';   // 자동복원 끔 — 매 진입 시 빈칸
}

/* 담당자 명단 = 지원부 규정 '실제 운영 근무조'(tab-policy 표)와 일치 유지. GM 2026-06-12.
   ※ 규정 근무조 변경 시 본 배열도 함께 갱신(단일 출처는 규정 표, 여기는 미러). */
const DUTY_ROSTER={
  f:[{shift:'오전',name:'우춘화 주임'},{shift:'중간',name:'이연희 반장'},{shift:'마감',name:'김미영 주임'},{shift:'마감',name:'이경미 주임'}],
  m:[{shift:'오전',name:'천진석 주임'},{shift:'중간',name:'김유정 주임'},{shift:'마감',name:'박남일 주임'}]
};
/* 담당자(날짜 우측) = 규정 근무조 드롭다운, 선택값 localStorage 기억. GM 2026-06-12.
   submit 게이트와 무관(점검자 입력만 제출 활성). 선택값=담당자명 → 제출 시 시트 담당자 칸에 기록. */
/* 규정 '실제 운영 근무조' 표를 DOM에서 파싱 → 담당자 명단 SSOT. 표 갱신 시 자동 반영(하드코딩 폴백). */
function parseDutyRoster(){
  try{
    const out={m:[],f:[]};
    const ps=[].slice.call(document.querySelectorAll('p'));
    function parseAfter(marker,key){
      const p=ps.find(x=>x.textContent.indexOf(marker)>=0);
      if(!p)return;
      let t=p.nextElementSibling;
      while(t&&t.tagName!=='TABLE')t=t.nextElementSibling;
      if(!t)return;
      const rows=[].slice.call(t.querySelectorAll('tr')).slice(1);
      rows.forEach(function(r){
        const tds=r.querySelectorAll('td'); if(tds.length<2)return;
        const shift=tds[0].textContent.trim();
        const cleaned=tds[1].textContent.replace(/\([^)]*\)/g,'');
        cleaned.split('·').forEach(function(n){ const nm=n.trim(); if(nm)out[key].push({shift:shift,name:nm}); });
      });
    }
    parseAfter('여직원 근무조','f');
    parseAfter('남직원 근무조','m');
    return (out.m.length||out.f.length)?out:null;
  }catch(e){ return null; }
}
function populateDutyDropdowns(){
  const live=parseDutyRoster();
  const R=live||DUTY_ROSTER;
  populateOneDuty('dutyM','m',R);
  populateOneDuty('dutyF','f',R);
}
function populateOneDuty(selId,gender,roster0){
  const el=document.getElementById(selId);
  if(!el)return;
  const saved=localStorage.getItem('wcheck_duty_'+gender)||'';
  const roster=(roster0||DUTY_ROSTER)[gender]||[];
  let html='<option value="">담당자 선택</option>';
  roster.forEach(r=>{
    const label=r.name;  // 직함+이름만 표시(오전/오후 등 shift 라벨 제거) — GM 2026-06-13
    html+='<option value="'+escapeAttr(r.name)+'"'+(r.name===saved?' selected':'')+'>'+escapeHTML(label)+'</option>';
  });
  el.innerHTML=html;
  if(saved)el.value=saved;
}
/* 현재 탭 담당자 선택값(시트 기록용) */
function getDutyForGender(g){const el=document.getElementById(g==='f'?'dutyF':'dutyM');return el?el.value||'':'';}
function onDutyChangeG(g){
  const el=document.getElementById(g==='f'?'dutyF':'dutyM');
  if(el)localStorage.setItem('wcheck_duty_'+g,el.value||'');
}

function getStaffInfo(name){
  return STAFF_LIST.find(s=>s.name===name)||null;
}

function getSubmitterForGender(g){
  const selId=g==='f'?'submitterF':'submitterM';
  return document.getElementById(selId).value;
}

function isNightShiftWorkerG(g){
  const sub=getSubmitterForGender(g);
  const info=getStaffInfo(sub);
  return info&&info.shift==='night';
}

function shouldShowItemForGender(item,gender){
  // gender = 'm' or 'f'
  const itemGender=item.gender||'all';
  if(itemGender==='all') return true;
  return itemGender===gender;
}

/* ── Data: gender field added (m/f/all) ── */

const WEEKDAY=[
  {slot:"오픈 05:30~08:00",shift:"am",groups:[
    {title:"A 사우나점검",items:[
      {id:"a1",name:"A-1 사우나 탕",detail:"오픈 시 수위/온도 확인 후 오버풀 타이머 가동 | 탕 청결\n배수: 냉탕 매일 / 온탕·열탕 격일 (마개+스위치 확인) / 휴관일 전 냉·온·열탕 전부 배수\n[온탕 평일] 6회: 06:00, 10:00, 11:00, 12:00, 15:00, 20:00\n[열탕 평일] 6회: 06:00, 10:30, 11:30, 12:30, 15:30, 20:40\n[온탕 주말] 3회: 10:00, 14:00, 18:00 / [열탕 주말] 3회: 10:30, 14:30, 18:30",gender:"all"},
      {id:"a2",name:"A-2 건/습식 사우나",detail:"온도 체크 (건식 90~100°C / 습식 60~70°C 기준) | 건식/습식 내부 청결\n바닥·타일 물때 제거 | 수요일 고압세척 + 산성세제 금지\n비품: 모래시계 확인",gender:"all"},
      {id:"a3",name:"A-3 사우나 내부",detail:"배수로/배수구 청소 | 바닥 미끄럼 | 타일/유리 물때 | 탈수기 밑 | 좌식 의자 | 거울\n비품: 바가지, 목욕의자, 거품바구니, 쓰레기통, 치약, 소금, 샴푸, 린스, 바디워시, 비누",gender:"all"}
    ]}
  ]},
  {slot:"오전 08:00~12:00",shift:"am",groups:[
    {title:"B 락커룸",items:[
      {id:"b1",name:"B-1 요일별 락커 청소",detail:"요일별 지정 락커 청소 진행",gender:"all"},
      {id:"b2",name:"B-2 파우더",detail:"선풍기 | 드라이기 | 휴지통 | 소독기 | 발건조기 | 청소 진행\n비품: 빗, 면봉, 휴지, 로션, 스킨",gender:"all"},
      {id:"b3",name:"B-3 휴게실",detail:"TV 관리 | 소파 및 테이블 관리",gender:"all"},
      {id:"b4_f",name:"B-4 찜질방 (여)",detail:"온도/청결 관리\n쑥 제거(휴관일 전) / 쑥 입고(휴관일 후)",gender:"f"},
      {id:"b4_m",name:"B-4 수면실 (남)",detail:"청결 관리\n매트리스/바스타올 관리",gender:"m"},
      {id:"b5",name:"B-5 마루바닥",detail:"바닥 미끄럼/청결 | 휴지통\n비품: 1회용 밀대 타올 (수시)",gender:"all"},
      {id:"b6",name:"B-6 사우나 화장실",detail:"소변기/대변기/바닥/세면공간\n비품: 휴지통, 화장지, 핸드페이퍼, 손세정제",gender:"all"}
    ]},
    {title:"오픈 점검",items:[
      {id:"c1a",name:"세탁물 입고 운반",detail:"입고된 세탁물을 세탁실로 운반",gender:"all"},
      {id:"c1b",name:"운동복/양말 상태 + 배치",detail:"상태 체크 후 사이즈별 배치",gender:"all"},
      {id:"c1c",name:"타올류 상태 + 배치",detail:"거품타올/타올/바스타올 상태 체크 후 배치",gender:"all"}
    ]}
  ]},
  {slot:"내부·외부 점검",shift:"all",groups:[
    {title:"C 내부",items:[
      {id:"c1",name:"C-1 외부 화장실",detail:"골프장/B1/B2 화장실 체크 | 악취 관리 최우선\n비품: 휴지통, 화장지, 핸드페이퍼, 손세정제",gender:"all"},
      {id:"c2",name:"C-2 복도 휴지통",detail:"운영사무실 앞 / B1 복도(헬스장 입구 구석)",gender:"all"},
      {id:"c3",name:"C-3 메인 계단",detail:"B1-B2 메인 계단 벽/바닥 청결 (남 주임 전담)",gender:"m"},
      {id:"c4",name:"C-4 센터 복도·거울/유리창",detail:"센터 복도 바닥: 1F/B1/B2 에스컬레이터 공간 전체 복도\n거울/유리창 물때 | 손톱깍이장 청소 (화요일 집중)",gender:"all"},
      {id:"c5",name:"C-5 분리수거장",detail:"에스컬레이터 아래 분리수거 진행",gender:"all"},
      {id:"c6",name:"C-6 청소 비품 관리",detail:"비품 지정 위치 배치 | 깔끔하게 관리",gender:"all"},
      {id:"c7",name:"C-7 메인 복도 휴게공간",detail:"소파/바닥 청결 (여 주임 전담)",gender:"f"},
      {id:"c8",name:"C-8 센터 화분",detail:"물 공급 (여 주임 전담 / 금요일 집중)",gender:"f"},
      {id:"c9",name:"C-9 키즈 샤워실",detail:"파우더룸 정리 20:30\n2주 1회 샤워실 청소 수 13:00 (남 주임 전담)",gender:"m"},
      {id:"c10",name:"C-10 수영장 계단",detail:"주 1회 청소",gender:"all"}
    ]},
    {title:"D 업장",items:[
      {id:"d1",name:"D-1 헬스장",detail:"매일: 머신/런닝머신 땀 | 월수금: 런닝머신 바닥 | 화목: 스트레칭 공간 | 주말: 거울",gender:"all"},
      {id:"d2",name:"D-2 골프장",detail:"매일: 복도 청소 | 월수금: 타석(스크린천) | 화목: 타석(기계) | 주말: 레슨룸",gender:"all"},
      {id:"d3",name:"D-3 G.X룸",detail:"거울/바닥 청소 (남 주임 전담 / 화요일 집중)",gender:"m"}
    ]},
    {title:"E 외부",items:[
      {id:"e1",name:"E-1 주차장",detail:"바닥 쓰레기 치우기 | 주차장 화장실 | 차단기 확인\n휴관일: 집중 청소",gender:"all"}
    ]}
  ]},
  {slot:"인수인계 13:00~14:00",shift:"pm",groups:[
    {title:"교대 인수인계",items:[
      {id:"hw1",name:"세탁물 출고 운반",detail:"세탁물 출고 운반 + 카카오톡 인수인계 보고",gender:"all"},
      {id:"hw2",name:"인수인계 카톡 보고",detail:"오전조 → 오후조 인수사항 카카오톡 공유",gender:"all"}
    ]}
  ]},
  {slot:"마감 22:00~22:30",shift:"pm",groups:[
    {title:"마감 점검",items:[
      {id:"cls1",name:"세탁물 마감 출고",detail:"마감 세탁물 최종 출고 운반 | 마감 출고 빠짐없이 확인",gender:"all"},
      {id:"cls2",name:"사우나/파우더 최종 체크",detail:"남/여 사우나 & 파우더 공간 청결 상태 체크\n시설/운영부 마감자 카톡 보고\n미비 시 경고 / 경고 3회 경징계",gender:"all"},
      {id:"cls3",name:"전 구역 마감 확인",detail:"전 구역 이상 유무 | 미수금 정산 | 다음날 일정 준비 완료 확인",gender:"all"}
    ]}
  ]}
  // '상시 F 회원 응대'는 점검 항목에서 제거 → '가이드' 탭으로 이관·합병 (GM 2026-06-11)
];

const WEEKEND=[
  {slot:"오픈 07:30~08:00",shift:"am",groups:[
    {title:"A 사우나점검",items:[
      {id:"a1",name:"A-1 사우나 탕",detail:"수위/온도 체크 | 탕 청결 | 오버풀 관리\n[온탕 주말] 3회: 10:00, 14:00, 18:00\n[열탕 주말] 3회: 10:30, 14:30, 18:30",gender:"all"},
      {id:"a2",name:"A-2 건/습식 사우나",detail:"온도 체크 | 내부 청결",gender:"all"},
      {id:"a3",name:"A-3 사우나 내부",detail:"배수로/배수구 | 바닥 | 타일/유리 | 탈수기 | 거울",gender:"all"}
    ]}
  ]},
  {slot:"오전 08:00~12:00",shift:"am",groups:[
    {title:"B 락커룸",items:[
      {id:"b1",name:"B-1 요일별 락커 청소",detail:"요일별 지정 락커 청소 진행",gender:"all"},
      {id:"b2",name:"B-2 파우더",detail:"선풍기 | 드라이기 | 휴지통 | 소독기 | 발건조기 | 청소 진행",gender:"all"},
      {id:"b3",name:"B-3 휴게실",detail:"TV | 소파 | 테이블",gender:"all"},
      {id:"b4_f",name:"B-4 찜질방 (여)",detail:"온도/청결 관리",gender:"f"},
      {id:"b4_m",name:"B-4 수면실 (남)",detail:"청결 관리 | 매트리스/바스타올",gender:"m"},
      {id:"b5",name:"B-5 마루바닥",detail:"미끄럼/청결 | 휴지통",gender:"all"},
      {id:"b6",name:"B-6 사우나 화장실",detail:"소변기/대변기/바닥/세면공간",gender:"all"}
    ]},
    {title:"오픈 점검",items:[
      {id:"c1a",name:"세탁물 입고 + 상태 체크",detail:"운동복/양말 사이즈별 배치 | 타올류 배치",gender:"all"}
    ]}
  ]},
  {slot:"인수인계 13:00~14:00",shift:"pm",groups:[
    {title:"교대 인수인계",items:[
      {id:"hw1",name:"세탁물 출고 + 인수인계",detail:"카카오톡 보고 의무",gender:"all"}
    ]}
  ]},
  {slot:"내부·외부 점검",shift:"all",groups:[
    {title:"C 내부",items:[
      {id:"c1",name:"C-1 외부 화장실",detail:"골프장/B1/B2",gender:"all"},
      {id:"c2",name:"C-2 복도 휴지통",detail:"운영사무실 앞 / B1 복도",gender:"all"},
      {id:"c3",name:"C-3 메인 계단",detail:"B1-B2 벽/바닥 (남 주임 전담)",gender:"m"},
      {id:"c4",name:"C-4 센터 복도·거울/유리창",detail:"센터 복도 바닥: 1F/B1/B2\n거울/유리창 물때",gender:"all"},
      {id:"c5",name:"C-5 분리수거장",detail:"에스컬레이터 아래",gender:"all"},
      {id:"c6",name:"C-6 청소 비품 관리",detail:"지정 위치 배치",gender:"all"},
      {id:"c7",name:"C-7 메인 복도 휴게공간",detail:"소파/바닥 (여 주임 전담)",gender:"f"}
    ]},
    {title:"D 업장",items:[
      {id:"d1",name:"D-1 헬스장",detail:"거울 청소 (주말)",gender:"all"},
      {id:"d2",name:"D-2 골프장",detail:"레슨룸 청소 (주말)",gender:"all"}
    ]},
    {title:"E 외부",items:[
      {id:"e1",name:"E-1 주차장",detail:"바닥 쓰레기 | 화장실 | 차단기",gender:"all"}
    ]}
  ]},
  {slot:"마감 18:00",shift:"pm",groups:[
    {title:"마감 점검",items:[
      {id:"cls1",name:"세탁물 최종 출고",detail:"마감 세탁물 운반",gender:"all"},
      {id:"cls2",name:"사우나/파우더 최종 체크",detail:"남/여 사우나 & 파우더 청결 최종 체크 (카톡 보고)",gender:"all"},
      {id:"cls3",name:"마감 탕청소",detail:"별도 2인 1조 | 탕청소 업체 20:30 출근",gender:"all"}
    ]}
  ]}
  // '상시 F 회원 응대'는 점검 항목에서 제거 → '가이드' 탭으로 이관·합병 (GM 2026-06-11)
];

/* ── D: Night shift (탕청소 업체) ── */
const NIGHT_WEEKDAY=[
  {slot:"23:00~23:30",shift:"night",groups:[
    {title:"초기 점검 및 준비",items:[
      {id:"n_prep",name:"청소 도구 준비 및 초기 점검",detail:"청소 도구 상태 확인 | 세제/장비 준비 | 구역별 점검 시작",gender:"all"}
    ]}
  ]},
  {slot:"23:30~00:30 남 사우나",shift:"night",groups:[
    {title:"남 사우나 탕청소",items:[
      {id:"n_m_tang",name:"냉탕/온탕/열탕 배수 + 탕 내부 청소",detail:"배수 후 탕 내부 벽면/바닥 세척 | 배수구 이물질 제거",gender:"all"},
      {id:"n_m_shower",name:"샤워부스 청소",detail:"샤워부스 벽면/바닥/배수구 세척",gender:"all"},
      {id:"n_m_floor",name:"바닥 + 배수구",detail:"전체 바닥 세척 | 배수구 이물질 제거 및 소독",gender:"all"},
      {id:"n_m_roller",name:"돌돌이 (격주)",detail:"격주 돌돌이 작업 실시",gender:"all"}
    ]}
  ]},
  {slot:"00:30~01:30",shift:"night",groups:[
    {title:"요일별 집중 청소 (야간)",items:[
      {id:"n_daily_focus",name:"요일별 집중 청소",detail:"해당 요일 집중 청소 항목 수행 (요일별 항목 참고)",gender:"all"}
    ]}
  ]},
  {slot:"01:30~02:00",shift:"night",groups:[
    {title:"휴게시간",items:[
      {id:"n_break",name:"휴게시간",detail:"30분 휴식",gender:"all"}
    ]}
  ]},
  {slot:"02:00~03:00 여 사우나",shift:"night",groups:[
    {title:"여 사우나 탕청소",items:[
      {id:"n_f_tang",name:"냉탕/온탕/열탕 배수 + 탕 내부 청소",detail:"배수 후 탕 내부 벽면/바닥 세척 | 배수구 이물질 제거",gender:"all"},
      {id:"n_f_shower",name:"샤워부스 청소",detail:"샤워부스 벽면/바닥/배수구 세척",gender:"all"},
      {id:"n_f_floor",name:"바닥 + 배수구",detail:"전체 바닥 세척 | 배수구 이물질 제거 및 소독",gender:"all"},
      {id:"n_f_roller",name:"돌돌이 (격주)",detail:"격주 돌돌이 작업 실시",gender:"all"}
    ]}
  ]},
  {slot:"03:00~04:00",shift:"night",groups:[
    {title:"여 사우나 화장실 + 마감",items:[
      {id:"n_f_toilet",name:"여 사우나 화장실 청소",detail:"소변기/대변기/바닥/세면공간 세척",gender:"all"},
      {id:"n_daily_focus2",name:"요일별 청소 마무리",detail:"요일별 잔여 집중 청소 항목 마무리",gender:"all"},
      {id:"n_final",name:"최종 마감 점검",detail:"전 구역 최종 확인 | 탕 배수 일지 작성",gender:"all"}
    ]}
  ]}
];

const NIGHT_WEEKEND=[
  {slot:"20:30~21:00",shift:"night",groups:[
    {title:"초기 점검 및 준비",items:[
      {id:"n_prep",name:"청소 도구 준비 및 초기 점검",detail:"청소 도구 상태 확인 | 세제/장비 준비 | 구역별 점검 시작",gender:"all"}
    ]}
  ]},
  {slot:"21:00~22:00 남 사우나",shift:"night",groups:[
    {title:"남 사우나 탕청소",items:[
      {id:"n_m_tang",name:"냉탕/온탕/열탕 배수 + 탕 내부 청소",detail:"배수 후 탕 내부 벽면/바닥 세척 | 배수구 이물질 제거",gender:"all"},
      {id:"n_m_shower",name:"샤워부스 청소",detail:"샤워부스 벽면/바닥/배수구 세척",gender:"all"},
      {id:"n_m_floor",name:"바닥 + 배수구",detail:"전체 바닥 세척 | 배수구 이물질 제거 및 소독",gender:"all"},
      {id:"n_m_roller",name:"돌돌이 (격주)",detail:"격주 돌돌이 작업 실시",gender:"all"}
    ]}
  ]},
  {slot:"22:00~23:00",shift:"night",groups:[
    {title:"요일별 집중 청소 (야간)",items:[
      {id:"n_daily_focus",name:"요일별 집중 청소",detail:"해당 요일 집중 청소 항목 수행 (요일별 항목 참고)",gender:"all"}
    ]}
  ]},
  {slot:"23:00~23:30",shift:"night",groups:[
    {title:"휴게시간",items:[
      {id:"n_break",name:"휴게시간",detail:"30분 휴식",gender:"all"}
    ]}
  ]},
  {slot:"23:30~00:30 여 사우나",shift:"night",groups:[
    {title:"여 사우나 탕청소",items:[
      {id:"n_f_tang",name:"냉탕/온탕/열탕 배수 + 탕 내부 청소",detail:"배수 후 탕 내부 벽면/바닥 세척 | 배수구 이물질 제거",gender:"all"},
      {id:"n_f_shower",name:"샤워부스 청소",detail:"샤워부스 벽면/바닥/배수구 세척",gender:"all"},
      {id:"n_f_floor",name:"바닥 + 배수구",detail:"전체 바닥 세척 | 배수구 이물질 제거 및 소독",gender:"all"},
      {id:"n_f_roller",name:"돌돌이 (격주)",detail:"격주 돌돌이 작업 실시",gender:"all"}
    ]}
  ]},
  {slot:"00:30~01:30",shift:"night",groups:[
    {title:"여 화장실 + 마감",items:[
      {id:"n_f_toilet",name:"여 사우나 화장실 청소",detail:"소변기/대변기/바닥/세면공간 세척",gender:"all"},
      {id:"n_daily_focus2",name:"요일별 청소 마무리",detail:"요일별 잔여 집중 청소 항목 마무리",gender:"all"},
      {id:"n_final",name:"최종 마감 점검",detail:"전 구역 최종 확인 | 탕 배수 일지 작성",gender:"all"}
    ]}
  ]}
];

/* ── E: Day-of-week focused cleaning ── */
const DAY_FOCUS={
  1:[ // 월
    {id:"df_mon1",name:"화장실 전체 청소",detail:"남/여 화장실 전면 세척",gender:"all"},
    {id:"df_mon2",name:"탈수기 물때/곰팡이",detail:"탈수기 내부 물때 및 곰팡이 제거",gender:"all"},
    {id:"df_mon3",name:"B-2 파우더 집중",detail:"파우더 공간 집중 청소",gender:"all"},
    {id:"df_mon4",name:"B-6 사우나 화장실 집중",detail:"사우나 화장실 집중 세척 (탕 배수: 마개+스위치 확인)",gender:"all"}
  ],
  2:[ // 화
    {id:"df_tue1",name:"세면대 배수 파이프",detail:"세면대 배수 파이프 분해 청소",gender:"all"},
    {id:"df_tue2",name:"배수구 악취 소독/머리카락",detail:"배수구 악취 소독 및 머리카락 제거",gender:"all"},
    {id:"df_tue3",name:"탕 내 비품 점검",detail:"탕 내부 비품 상태 확인 및 교체",gender:"all"},
    {id:"df_tue4",name:"C-4 거울/유리창 집중",detail:"센터 거울 및 유리창 집중 세척",gender:"all"},
    {id:"df_tue5",name:"D-3 G.X룸 거울",detail:"G.X룸 거울 집중 세척",gender:"m"}
  ],
  3:[ // 수
    {id:"df_wed1",name:"건/습식 사우나 바닥",detail:"고압세척 + 산성세제 집중 세척",gender:"all"},
    {id:"df_wed2",name:"C-9 키즈샤워실 집중",detail:"키즈샤워실 집중 청소",gender:"m"}
  ],
  4:[ // 목
    {id:"df_thu1",name:"화장실 전체 청소",detail:"남/여 화장실 전면 세척",gender:"all"},
    {id:"df_thu2",name:"탈수기 물때/곰팡이",detail:"탈수기 내부 물때 및 곰팡이 제거",gender:"all"},
    {id:"df_thu3",name:"B-2 파우더 집중",detail:"파우더 공간 집중 청소",gender:"all"},
    {id:"df_thu4",name:"B-6 사우나 화장실 집중",detail:"사우나 화장실 집중 세척",gender:"all"}
  ],
  5:[ // 금
    {id:"df_fri1",name:"세면대 배수 파이프",detail:"세면대 배수 파이프 분해 청소",gender:"all"},
    {id:"df_fri2",name:"배수구 악취 소독/머리카락",detail:"배수구 악취 소독 및 머리카락 제거",gender:"all"},
    {id:"df_fri3",name:"탕 내 비품 점검",detail:"탕 내부 비품 상태 확인 및 교체",gender:"all"},
    {id:"df_fri4",name:"C-8 센터 화분 집중",detail:"화분 물 공급 및 주변 정리 집중",gender:"f"}
  ],
  6:[ // 토
    {id:"df_sat1",name:"벽체 곰팡이/물때",detail:"벽체 곰팡이 및 물때 제거",gender:"all"},
    {id:"df_sat2",name:"거울/유리창 물때",detail:"거울 및 유리창 물때 집중 제거",gender:"all"},
    {id:"df_sat3",name:"천정 환기구 먼지",detail:"천정 환기구 먼지 제거",gender:"all"},
    {id:"df_sat4",name:"방제",detail:"방제 작업 실시",gender:"all"}
  ],
  0:[ // 일
    {id:"df_sun1",name:"탕청소 업체 휴무",detail:"탕청소 업체 휴무일",gender:"all"},
    {id:"df_sun2",name:"E-1 주차장 집중",detail:"주차장 집중 청소",gender:"all"},
    {id:"df_sun3",name:"개인락커 + 미비 부분",detail:"개인락커 점검 및 미비 사항 보완",gender:"all"}
  ]
};

/* ── Helper functions ── */

function getDayInfo(ds){
  const d=new Date(ds+'T00:00:00'),dow=d.getDay(),wk=Math.ceil(d.getDate()/7);
  if(dow===0&&(wk===2||wk===4))return{type:'closed',label:'휴관일',cls:'closed'};
  if(ds.slice(5)==='01-01')return{type:'closed',label:'휴관일',cls:'closed'};
  if(dow===0||dow===6)return{type:'weekend',label:'주말',cls:'weekend'};
  return{type:'weekday',label:'평일',cls:'weekday'};
}

function getDayOfWeek(ds){return new Date(ds+'T00:00:00').getDay()}

function getSched(ds){
  const i=getDayInfo(ds);
  if(i.type==='closed')return null;
  return i.type==='weekend'?WEEKEND:WEEKDAY;
}

function getNightSched(ds){
  const i=getDayInfo(ds);
  if(i.type==='closed')return null;
  return i.type==='weekend'?NIGHT_WEEKEND:NIGHT_WEEKDAY;
}

function getActiveSchedG(ds,g){
  if(isNightShiftWorkerG(g)){
    return getNightSched(ds);
  }
  return getSched(ds);
}

function getAllItems(sched){
  const items=[];
  if(!sched)return items;
  sched.forEach(slot=>{slot.groups.forEach(g=>{g.items.forEach(it=>{items.push({...it,shift:slot.shift,slot:slot.slot,cat:g.title})})})});
  return items;
}

/* ════════════════════════════════════════════════════════════
   3조(라운드) 분류 레이어 — 순수 분류만(기존 WEEKDAY/항목 id/셋업·집계 무변경).
   조→기존슬롯 매핑은 slot 라벨 문자열 기반(roundOfSlot). 정상(주간)모드에만 적용,
   야간(탕청소 업체)모드는 기존 그대로. (시우·GM 2026-06-11 · 1단계)
   ════════════════════════════════════════════════════════════ */
/* 3조(라운드) — 평일 3조(오전 10시 / 오후 15시 / 마감 20시) · 주말 2조(오전 12시 / 마감 18시).
   ROUNDS = 전 키 마스터(am1·pm1·close1) — roundDef/roundLabel/promote 모달 등 전역 참조용.
   날짜별 노출·시각은 getRoundsFor(date) / roundHourFor(date)가 분기(평일/주말). */
const ROUNDS_WEEKDAY=[
  {key:'am1',name:'오전조[1]',time:'10시',hour:10,baseShift:'am'},
  {key:'pm1',name:'오후조[1]',time:'15시',hour:15,baseShift:'pm'},
  {key:'close1',name:'마감조[1]',time:'20시',hour:20,baseShift:'pm'}
];
const ROUNDS_WEEKEND=[
  {key:'am1',name:'오전조[1]',time:'12시',hour:12,baseShift:'am'},
  {key:'close1',name:'마감조[1]',time:'18시',hour:18,baseShift:'pm'}
];
/* 마스터(전 키) — 평일 라벨/시각 기준. 전역 참조부(roundDef·promote 등) 호환용. */
const ROUNDS=ROUNDS_WEEKDAY.slice();
const ROUND_KEYS=ROUNDS.map(r=>r.key);
/* 날짜에 맞는 조 배열(평일 3조 / 주말 2조). 휴관일은 평일 폴백(렌더는 휴관 분기에서 차단). */
function getRoundsFor(ds){
  const i=(typeof getDayInfo==='function')?getDayInfo(ds):null;
  return (i&&i.type==='weekend')?ROUNDS_WEEKEND:ROUNDS_WEEKDAY;
}
function roundDef(rk){return ROUNDS.find(r=>r.key===rk)||null}
/* 날짜 인지 조 정의(주말 시각 반영). 날짜 없으면 마스터 폴백. */
function roundDefFor(rk,ds){const arr=ds?getRoundsFor(ds):ROUNDS;return arr.find(r=>r.key===rk)||roundDef(rk)}
function roundLabel(rk){const r=roundDef(rk);return r?(r.name+' '+r.time):rk}
/* 슬롯 라벨(또는 shift)로 라운드 분류. 인식 못한 슬롯은 baseShift 기준 폴백
   (am→am1, pm→close1). */
function roundOfSlot(slotLabel,shift){
  const s=String(slotLabel||'');
  if(s.indexOf('오픈')>=0||s.indexOf('오전 후반')>=0||(s.indexOf('오전')>=0&&s.indexOf('08:00')>=0))return 'am1';
  if(s.indexOf('인수인계')>=0)return 'am1';
  if(s.indexOf('오후')>=0)return 'pm1';
  if(s.indexOf('저녁')>=0||s.indexOf('마감')>=0)return 'close1';
  // 폴백: shift 기준
  if(shift==='am')return 'am1';
  if(shift==='pm')return 'close1';
  return 'am1';
}
/* 날짜별 조 대표시각(시). 주말 am1=12·close1=18 / 평일 am1=10·pm1=15·close1=20. */
function roundHourFor(rk,ds){const r=roundDefFor(rk,ds);return r?r.hour:10}
/* 현재 시각으로 가장 가까운(직전/현재) 조 자동선택 — 그 날짜의 조 집합 기준. */
function autoRoundForNow(ds){
  const arr=ds?getRoundsFor(ds):ROUNDS;
  const h=new Date().getHours();
  let best=arr[0].key,bestGap=Infinity;
  arr.forEach(r=>{
    const gap=h-r.hour; // 직전/현재 조 우선(>=0 작은 gap), 아직 안온 조는 큰 페널티
    const score=gap>=0?gap:(100-gap);
    if(score<bestGap){bestGap=score;best=r.key}
  });
  return best;
}
/* 현재 선택된 라운드(성별별). localStorage 영속 → 새로고침/날짜이동해도 유지
   (loadState가 STATE를 비워도 보존). 저장값 없으면 시간대 기준 자동 선택. */
function roundLSKey(g){return 'wcheck_round_'+g}
function getRoundG(g){
  const ds=(typeof getDateG==='function')?getDateG(g):'';
  const keys=ds?getRoundsFor(ds).map(r=>r.key):ROUND_KEYS;
  const v=localStorage.getItem(roundLSKey(g));
  if(v&&keys.indexOf(v)>=0)return v;        // 저장값이 그날 조 집합에 있으면 사용
  return autoRoundForNow(ds);               // 없으면(주말↔평일 전환 등) 시간대 자동선택
}
function setRoundG(g,rk){
  const ds=(typeof getDateG==='function')?getDateG(g):'';
  const keys=ds?getRoundsFor(ds).map(r=>r.key):ROUND_KEYS;
  if(keys.indexOf(rk)<0)return;
  localStorage.setItem(roundLSKey(g),rk);
  drawUI(getDateG(g),g);
}
/* 라운드별 제출 잠금 — STATE + localStorage 미러 영속.
   loadState가 ONLINE 시 STATE를 서버값으로 덮어써도(라운드 락은 서버 미저장)
   localStorage 미러로 새로고침·날짜이동 후에도 잠금 표시가 유지됨. GAS 스키마 무변경. */
function roundSubKey(d,g,rk){return 'submitted_'+d+'_'+g+'_'+rk}
function roundSubLSKey(d,g,rk){return 'wcheck_rsub_'+d+'_'+g+'_'+rk}
function isRoundSubmitted(d,g,rk){
  if(STATE[roundSubKey(d,g,rk)])return true;
  return localStorage.getItem(roundSubLSKey(d,g,rk))==='1';
}
/* 라운드 제출 메타 읽기(제출자/시각) — STATE 우선, 없으면 localStorage 미러 */
function roundSubMeta(d,g,rk){
  const by=STATE['submitter_'+d+'_'+g+'_'+rk]||localStorage.getItem('wcheck_rsubBy_'+d+'_'+g+'_'+rk)||'';
  const at=STATE['submittedAt_'+d+'_'+g+'_'+rk]||localStorage.getItem('wcheck_rsubAt_'+d+'_'+g+'_'+rk)||'';
  return {by,at};
}
/* 특정 baseShift에 속한 라운드 키들 */
function roundsOfShift(sh){return ROUNDS.filter(r=>r.baseShift===sh).map(r=>r.key)}
/* 그 라운드에 가시 항목이 1개라도 있는지(성별 반영). 빈 조(pm2 등)는 false.
   shift 완료 판정에서 빈 조는 '제출 불필요'로 간주(비어서 제출 불가한 조가
   shift 집계를 영원히 막지 않도록). */
function roundHasItems(date,g,rk){
  const sched=getSched(date);
  if(!sched)return false;
  let n=0;
  /* 멤버십(itemRounds) 기준 — 렌더와 동일하게 이 조에 뜨는 항목 수 집계 */
  sched.forEach(slot=>slot.groups.forEach(gr=>gr.items.forEach(it=>{
    if(!shouldShowItemForGender(it,g))return;
    const ctx={...it,slot:slot.slot,shift:slot.shift};
    if(itemRounds(ctx).indexOf(rk)>=0)n++;
  })));
  if(rk==='close1'){const dow=getDayOfWeek(date);if(DAY_FOCUS[dow])DAY_FOCUS[dow].forEach(it=>{if(shouldShowItemForGender(it,g))n++});}
  return n>0;
}
/* 라운드별 타이머 키(확장: 날짜+성별+라운드). drawUI/타이머가 라운드 인지. */
function timerKeys(d,g,rk){return {sk:'timerStart_'+d+'_'+g+'_'+rk, ek:'timerEnd_'+d+'_'+g+'_'+rk}}
/* 조 선택바 렌더 (성별별) — 그 날짜의 조만(평일 3조 / 주말 2조), 주말 시각 반영. */
function renderRoundBar(g){
  const bar=document.getElementById(g==='f'?'roundBarF':'roundBarM');
  if(!bar)return;
  const d=getDateG(g);
  const cur=getRoundG(g);
  let html='';
  getRoundsFor(d).forEach(r=>{
    const act=r.key===cur?' active':'';
    const done=isRoundSubmitted(d,g,r.key)?' done':'';
    html+=`<button class="round-seg${act}${done}" onclick="setRoundG('${g}','${r.key}')">`
        +`<span class="rs-name">${r.name}</span><span class="rs-time">${r.time}</span></button>`;
  });
  bar.innerHTML=html;
}

/* ════════════════════════════════════════════════════════════
   2a단계 — 항목 다회차(multi-round) 멤버십 + 구역별 그룹핑 (시우·GM 2026-06-11).
   · ROUND_MAP: 항목 id → 등장할 라운드 키 배열. 없으면 roundOfSlot 폴백(단일 라운드).
   · itemRounds(it): 그 항목이 멤버인 라운드 키 배열. CUSTOM override는 영향 없음.
   · 사우나 내부 권역(a*·b1·b5) = 5회 전부. 락커룸 내부 = 오전/오후/저녁 3회. 등.
   · 화면 렌더는 구역(group.title)별로 묶고, 옛 슬롯 시간 라벨은 표시하지 않음.
   ════════════════════════════════════════════════════════════ */
/* A~E 5그룹(2026-06-12, 시우·GM): A 사우나점검·B 락커룸·C 세탁물·D 내부(D-1~D-11)·E 외부(E-1~E-3 헬스장/골프장/주차장)
   = 전 조(오전조 am1·오후조 pm1·마감조 close1) 공통 기본. 오후조=인수인계(hw*)·마감조=마감점검(cls*) 추가.
   B-6 데일리락커(b6)=B 락커룸 편입. E-1+E-2→D-4 병합(e2 제거), id는 체크이력 보존 위해 유지. 고아·누락 0. */
const ROUND_MAP={
  /* A 사우나점검 = 전 조 */
  a1:['am1','pm1','close1'],
  a2:['am1','pm1','close1'],
  a3:['am1','pm1','close1'],
  /* B 락커룸 = 전 조 (b1 요일별락커 신규·b2~b6 +1시프트, 2026-06-13 ID정규화) */
  b1:['am1','pm1','close1'],
  b2:['am1','pm1','close1'],
  b3:['am1','pm1','close1'],
  b4_f:['am1','pm1','close1'],
  b4_m:['am1','pm1','close1'],
  b5:['am1','pm1','close1'],
  b6:['am1','pm1','close1'],
  /* C 세탁물 = 전 조 */
  /* 오픈 점검(세탁물 입고 등) = 오전조 전용 (마감 점검의 반대, GM 2026-06-12) */
  c1a:['am1'], c1b:['am1'], c1c:['am1'],
  /* C 내부(c1~c10) + D 업장(d1 헬스장·d2 골프장·d3 G.X) + E 외부(e1 주차장) = 전 조 (2026-06-13 ID정규화) */
  c1:['am1','pm1','close1'], c2:['am1','pm1','close1'], c3:['am1','pm1','close1'], c4:['am1','pm1','close1'], c5:['am1','pm1','close1'],
  c6:['am1','pm1','close1'], c7:['am1','pm1','close1'], c8:['am1','pm1','close1'], c9:['am1','pm1','close1'], c10:['am1','pm1','close1'],
  d1:['am1','pm1','close1'], d2:['am1','pm1','close1'], d3:['am1','pm1','close1'],
  e1:['am1','pm1','close1'],
  /* 시트 custom 구역항목(웰니스 D-4·VIP D-5·분수대 E-2·신발장 B-7) = 전 조 */
  custom_1781258818293_zmiwd:['am1','pm1','close1'], custom_1781261094618_l2ipe:['am1','pm1','close1'], custom_1781258912840_8z19q:['am1','pm1','close1'], custom_1781255718419_bxvec:['am1','pm1','close1'],
  /* 추가 — 오후조 전용 교대 인수인계(hw*) */
  hw1:['pm1'], hw2:['pm1'],
  /* 추가 — 마감조 전용 마감 점검(cls*) */
  cls1:['close1'], cls2:['close1'], cls3:['close1']
};
/* 항목 → 멤버 라운드 배열. 우선순위:
   1) 2b-1 CUSTOM 항목의 명시 rounds(이슈 승격 시 선택한 회차 다중) — 유효 키만.
   2) 기본 항목 ROUND_MAP.
   3) roundOfSlot 단일 라운드 폴백(구 데이터·회차 미지정 CUSTOM 하위호환).
   it 객체에 slot/shift가 묶여 들어옴(getAllItems/렌더 슬롯 기준). */
function itemRounds(it){
  if(it&&Array.isArray(it.rounds)){
    const valid=it.rounds.filter(function(rk){return ROUND_KEYS.indexOf(rk)>=0;});
    if(valid.length)return valid;
  }
  if(it&&ROUND_MAP[it.id])return ROUND_MAP[it.id];
  const r=roundOfSlot(it&&it.slot,it&&it.shift);
  return [r];
}
/* 회차별 체크 키 — 같은 항목 id라도 라운드마다 독립(10시 체크해도 12시엔 미체크).
   2026-06-12: 성별 격리 — 키에 gender 삽입(남/여 탭 STATE 분리, 동기화 버그 차단).
   g 미지정 시 현재 보고 있는 탭(activeGenderTab) 기준(전 호출부 비파괴). */
function chkKey(round,id,g){return 'chk_'+(g||activeGenderTab)+'_'+round+'_'+id}
/* 특정 라운드에서 이 항목이 체크됐는지. 라운드 키 우선, 없으면 레거시 STATE[id] 폴백
   (서버 복원·야간모드 호환: 서버는 항목단위만 저장 → 복원 시 모든 라운드에 반영). */
function isChecked(id,round,g){
  if(round&&STATE[chkKey(round,id,g)])return true;
  return !!STATE[id];
}
/* 이 항목이 어느 라운드에서든 체크됐는지(shift 집계·스냅샷·텔레그램·서버푸시용 브리지).
   레거시 STATE[id](서버 복원·야간) 또는 전 라운드 중 하나라도 체크 → true.
   ⚠ 슬롯 컨텍스트 유무와 무관히 전 라운드를 스캔(over-approx) — '어디서든 체크'를
   놓치지 않아 shift % 가 falsely 떨어지지 않게(비회귀 핵심). it=객체 또는 id 문자열.
   2026-06-12: 같은 성별(g) 내 전 라운드 스캔으로 over-approx 비회귀 정신 유지. */
function isCheckedAny(it,g){
  const id=(typeof it==='object'&&it)?it.id:it;
  if(STATE[id])return true;
  for(let i=0;i<ROUND_KEYS.length;i++){if(STATE[chkKey(ROUND_KEYS[i],id,g)])return true;}
  return false;
}

let STATE={};
/* 2026-06-12: localStorage 키 성별 분리 — 남/여 탭이 독립 STATE를 가져 새로고침 후에도 격리.
   g 미지정 시 현재 탭(activeGenderTab) 기준. 서버(GAS)는 dept+date만 키로 써 성별 병합(admin 집계 보존). */
const LK=(d,g)=>`wcheck3_${g||activeGenderTab}_${d}`;

function saveSubmitterG(g,v){localStorage.setItem('wcheck_submitter_'+g,v)}
function onSubmitterChangeG(g){
  // 점검자 = 자동저장 안 함(매번 빈칸 자유입력). 입력 즉시 제출버튼만 재평가.
  const d=getDateG(g);
  drawUI(d,g);
}

function loadLocal(d,g){try{return JSON.parse(localStorage.getItem(LK(d,g)))||{}}catch{return{}}}
function saveLocal(d,o,g){localStorage.setItem(LK(d,g),JSON.stringify(o))}

async function loadState(d,g){
  const gg=g||activeGenderTab;
  if(!ONLINE){STATE=loadLocal(d,gg);return}
  try{
    // 2026-06-12 시토: 남/여 동기화 근본수정 — 현재 성별(gg) 원장만 요청(&gender=). 서버가 성별별 분리 반환.
    const r=await fetch(API_URL+'?date='+d+DEPT_Q+'&gender='+encodeURIComponent(gg),{redirect:'follow'});
    const j=await r.json();
    STATE={};
    (j.rows||[]).forEach(row=>{
      // 2026-06-12 시우: 서버 응답이 성별 구분돼 오면(row.gender) 현재 성별(gg)만 STATE 반영 —
      // 성별화 체크는 chkKey에 기록해 화면 격리 유지. gender 미동반(레거시·서버 미격리)이면 기존 동작.
      if(row.gender&&row.gender!==gg)return;
      // 체크 복원은 '회차원장(cr)'만 사용(아래). 시트 행의 완료/미완료는 회차정보가 없어
      // roundOfSlot로 잘못된 회차에 복원→리셋처럼 보이던 문제 → 행으로 체크 복원 안 함. GM 2026-06-12.
      if(row.issue)STATE['iss_'+row.itemId]=row.issue;
      if(row.tip)STATE['tip_'+row.itemId]=row.tip;
      if(row.measure)restoreTempFromMeasure(row.itemId,row.measure);   // 온도 측정값 복원
      if(row.reflected)STATE['reflected_'+row.itemId]=true;            // 반영완료 복원
      if(row.submitted_am)STATE._submitted_am=true;
      if(row.submittedAt_am)STATE._submittedAt_am=row.submittedAt_am;
      if(row.submitter_am)STATE._submitter_am=row.submitter_am;
      if(row.submitted_pm)STATE._submitted_pm=true;
      if(row.submittedAt_pm)STATE._submittedAt_pm=row.submittedAt_pm;
      if(row.submitter_pm)STATE._submitter_pm=row.submitter_pm;
      if(row.submitted_night)STATE._submitted_night=true;
      if(row.submittedAt_night)STATE._submittedAt_night=row.submittedAt_night;
      if(row.submitter_night)STATE._submitter_night=row.submitter_night;
      if(row.submitted)STATE._submitted_am=true;
      if(row.submittedAt&&!STATE._submittedAt_am)STATE._submittedAt_am=row.submittedAt;
    });
    // 완료 체크 원장 복원(2026-06-11 시우): 정상완료 항목은 시트행이 없으므로(이상치만 기록)
    // 서버 원장(chk_<dept>_<date>)으로 STATE[itemId] 복원 → 과거일/타기기 admin 완료율 회귀 방지.
    // 구조: {c:체크itemId집합, sub:{am,pm,night}, subAt:{...}}. 제출 메타는 행이 없을 때만 보강(행 우선).
    if(j.checkedLedger){
      // 2026-06-12 시토: 남/여 동기화 근본수정 — &gender 요청으로 서버가 현재 성별(gg) 원장만 반환.
      // bare STATE[id] 금지(남↔여 누수원). 성별키(chkKey) 전 라운드에 복원 → 탭 전환·재렌더 시 gg 격리 유지.
      // 만약 서버가 성별맵 전체({m,f,all})를 보낸 레거시 응답이면 현재 성별 슬롯만 선택.
      let cl=j.checkedLedger;
      if(cl&&!cl.c&&!cl.cr&&(cl.m||cl.f||cl.all))cl=cl[gg]||{};
      // 회차별 복원만(2026-06-12): '<round>_<id>' → 그 회차에만. 레거시 led.c 전 회차 복원은
      // 회차정보가 없어 '전 회차 동기화·전부 완료' 오염을 유발 → 제거. 옛 데이터는 다시 체크하면 정상화.
      if(cl&&cl.cr&&typeof cl.cr==='object'){
        Object.keys(cl.cr).forEach(k=>{
          if(!cl.cr[k])return;
          const us=String(k).indexOf('_'); if(us<0)return;
          const rk=k.slice(0,us), id=k.slice(us+1);
          if(ROUND_KEYS.indexOf(rk)>=0)STATE[chkKey(rk,id,gg)]=true;
        });
      }
      const sub=cl.sub||{}, subAt=cl.subAt||{};
      if(sub.am&&!STATE._submitter_am){STATE._submitter_am=sub.am;STATE._submitted_am=true;}
      if(sub.pm&&!STATE._submitter_pm){STATE._submitter_pm=sub.pm;STATE._submitted_pm=true;}
      if(sub.night&&!STATE._submitter_night){STATE._submitter_night=sub.night;STATE._submitted_night=true;}
      if(subAt.am&&!STATE._submittedAt_am)STATE._submittedAt_am=subAt.am;
      if(subAt.pm&&!STATE._submittedAt_pm)STATE._submittedAt_pm=subAt.pm;
      if(subAt.night&&!STATE._submittedAt_night)STATE._submittedAt_night=subAt.night;
    }
    // 그룹별 제출 복원 (서버 영속 → 새로고침해도 유지) — 2026-06-05 GM
    if(j.groupSubmits){Object.keys(j.groupSubmits).forEach(key=>{
      const v=j.groupSubmits[key]||{};
      STATE['_gsub_'+key]=true;
      if(v.by)STATE['_gsubBy_'+key]=v.by;
      if(v.at)STATE['_gsubAt_'+key]=v.at;
    });}
    // (나) 방지: 이 날짜+성별에 서버 미반영 체크가 있으면 로컬 chkKey를 서버 위에 오버레이(미저장분 유실 방지).
    // 저장 완료되면 _dirtyKeys 해제 → 이후엔 서버 우선(옛 데이터 부활 위험 없음). GM 2026-06-12
    if(_dirtyKeys[d+'__'+gg]){
      try{
        Object.keys(STATE).forEach(k=>{ if(k.indexOf('chk_'+gg+'_')===0)delete STATE[k]; });   // 서버 체크 제거
        const _loc=loadLocal(d,gg); Object.keys(_loc).forEach(k=>{ if(k.indexOf('chk_'+gg+'_')===0 && _loc[k]===true)STATE[k]=true; });   // 로컬(진실) 적용
      }catch(e){}
    }
  }catch(e){STATE=loadLocal(d,gg)}
}

let saveTimer=null;
let _stagedPush={};   // 성별(g) → 저장 페이로드 '스냅샷'. 저장 시점에 즉시 캡처 → 이후 STATE 초기화·탭전환 레이스에 면역. GM 2026-06-12
let _dirtyKeys={};    // '날짜__성별' → 서버 미저장 변경 있음(탭이동 시 로컬 보존용). 서버 확정 후 해제.

/* 현재 STATE에서 성별 g의 저장 페이로드를 만든다(스냅샷용·즉시 전송용 공용).
   ⚠ 핵심: roundChecks·checks·이슈를 '지금' STATE에서 떠서 객체로 고정 → 디바운스가 늦게 떠도 그 성별의 그 시점 값이 정확히 전송. */
function _buildPushPayload(d,g,includeSubmitMeta){
  g=g||activeGenderTab;
  const sched=getActiveSchedG(d,g);
  const checks=[];
  const dow=getDayOfWeek(d);
  if(sched){
    sched.forEach(slot=>{slot.groups.forEach(gr=>{gr.items.forEach(it=>{
      // 타 성별 전용 항목은 전송 제외(여성시트에 남성탭 미완료가 쌓이던 누수 차단). 공용('all')은 포함.
      if(typeof shouldShowItemForGender==='function'&&!shouldShowItemForGender(it,g))return;
      checks.push({itemId:it.id,name:it.name,cat:gr.title,slot:slot.slot,shift:slot.shift,gender:g,
        checked:isCheckedAny(it,g),issue:STATE['iss_'+it.id]||'',tip:STATE['tip_'+it.id]||'',
        measure:collectTempJSON(it.id),reflected:!!STATE['reflected_'+it.id]});
    })})});
    if(DAY_FOCUS[dow]){
      DAY_FOCUS[dow].forEach(it=>{
        if(typeof shouldShowItemForGender==='function'&&!shouldShowItemForGender(it,g))return;
        checks.push({itemId:it.id,name:it.name,cat:'요일별 집중 청소',slot:'요일별',shift:'focus',gender:g,
          checked:isCheckedAny(it,g),issue:STATE['iss_'+it.id]||'',tip:STATE['tip_'+it.id]||'',
          measure:collectTempJSON(it.id),reflected:!!STATE['reflected_'+it.id]});
      });
    }
  }
  const _cpfx='chk_'+g+'_';
  const roundChecks=Object.keys(STATE).filter(k=>k.indexOf(_cpfx)===0&&STATE[k]===true).map(k=>k.slice(_cpfx.length));
  const p={action:'save',date:d,checks,dept:DEPT,genderTab:g,roundChecks:roundChecks,
    duty:(typeof getDutyForGender==='function'?getDutyForGender(g):''),
    groupSubmits:collectGroupSubmits()};
  /* ★폐루프 절단(시우 2026-06-13): 제출메타(submitted_*/submitter_*)는 '명시적 제출' 때만 전송.
     자동저장이 시트/원장 복원분을 상시 재도장(자기증식·거짓 대량제출) 차단 — includeSubmitMeta=true일 때만 포함. */
  if(includeSubmitMeta){
    p.submitted_am=!!STATE._submitted_am; p.submittedAt_am=STATE._submittedAt_am||''; p.submitter_am=STATE._submitter_am||'';
    p.submitted_pm=!!STATE._submitted_pm; p.submittedAt_pm=STATE._submittedAt_pm||''; p.submitter_pm=STATE._submitter_pm||'';
    p.submitted_night=!!STATE._submitted_night; p.submittedAt_night=STATE._submittedAt_night||''; p.submitter_night=STATE._submitter_night||'';
  }
  return p;
}

/* 페이로드 1건 실제 전송 */
async function _postPayload(payload){
  const d=payload.date, g=payload.genderTab;
  const ind=document.getElementById('saveIndicator');
  if(ind){ind.style.display='block';ind.textContent='저장 중...';}
  try{
    const r=await fetch(API_URL,{method:'POST',redirect:'follow',headers:{'Content-Type':'text/plain'},body:JSON.stringify(payload)});
    let ok=false; try{const j=await r.json(); ok=!!(j&&(j.success||j.ok)&&!j.error);}catch(_){ ok=false; }
    if(ok){
      delete _dirtyKeys[d+'__'+g];   // 서버 확정시에만 오버레이 해제(거짓완료·리셋 차단)
      if(ind)ind.textContent='저장 완료';
    }else{
      if(ind)ind.textContent='저장 실패 (로컬 보관·재시도)';   // 서버 미확정 → _dirtyKeys 유지
    }
  }catch(e){ if(ind)ind.textContent='저장 실패 (로컬 저장됨)'; }
  if(ind)setTimeout(()=>{ind.style.display='none'},1500);
}

/* 스테이징된(성별별) 스냅샷을 모두 전송. 탭전환 직전에도 호출(떠나는 탭 체크를 정확히 영속). */
function flushStagedPush(){
  clearTimeout(saveTimer); saveTimer=null;
  const gs=Object.keys(_stagedPush);
  if(!gs.length)return Promise.resolve();
  return Promise.all(gs.map(function(g){ const p=_stagedPush[g]; delete _stagedPush[g]; return _postPayload(p); }));
}
/* 하위호환 별칭 */
function flushPendingSave(){ return flushStagedPush(); }

function saveState(d,g){
  g=g||activeGenderTab;
  saveLocal(d,STATE,g);
  _dirtyKeys[d+'__'+g]=true;
  if(!ONLINE)return;
  _stagedPush[g]=_buildPushPayload(d,g);   // 즉시 스냅샷(성별 분리 — 남/여 안 섞임, STATE 초기화에 면역)
  clearTimeout(saveTimer);
  saveTimer=setTimeout(flushStagedPush,1200);
}

/* 직접·즉시 전송(제출·리셋 등 await 호출). 현재 STATE 기준으로 빌드해 바로 보냄. */
async function pushToServer(d,g,includeSubmitMeta){
  g=g||activeGenderTab;
  if(_stagedPush[g])delete _stagedPush[g];   // 같은 성별 스테이징분은 즉시전송으로 대체(중복 방지)
  return _postPayload(_buildPushPayload(d,g,includeSubmitMeta));
}

function getShiftStatsG(sched,sh,ds,gender){
  let total=0,done=0;
  const dow=ds?getDayOfWeek(ds):-1;
  sched.forEach(slot=>{
    const match=(sh==='am'&&(slot.shift==='am'||slot.shift==='all'))||(sh==='pm'&&(slot.shift==='pm'||slot.shift==='all'))||(sh==='night'&&slot.shift==='night');
    if(match){
      slot.groups.forEach(g=>{g.items.forEach(it=>{
        if(shouldShowItemForGender(it,gender)){total++;if(isCheckedAny(it))done++}
      })});
    }
  });
  if((sh==='am'||sh==='pm')&&dow>=0&&DAY_FOCUS[dow]&&!isNightShiftWorkerG(gender)){
    if(sh==='pm'){
      DAY_FOCUS[dow].forEach(it=>{
        if(shouldShowItemForGender(it,gender)){total++;if(isCheckedAny(it))done++}
      });
    }
  }
  if(sh==='night'&&dow>=0&&DAY_FOCUS[dow]){
    DAY_FOCUS[dow].forEach(it=>{
      if(shouldShowItemForGender(it,gender)){total++;if(isCheckedAny(it))done++}
    });
  }
  return{total,done,pct:total?Math.round(done/total*100):0};
}

/* Admin uses "all" gender to count everything */
function getShiftStatsAll(sched,sh,ds){
  let total=0,done=0;
  const dow=ds?getDayOfWeek(ds):-1;
  sched.forEach(slot=>{
    const match=(sh==='am'&&(slot.shift==='am'||slot.shift==='all'))||(sh==='pm'&&(slot.shift==='pm'||slot.shift==='all'))||(sh==='night'&&slot.shift==='night');
    if(match){
      slot.groups.forEach(g=>{g.items.forEach(it=>{
        total++;if(isCheckedAny(it))done++;
      })});
    }
  });
  if((sh==='am'||sh==='pm')&&dow>=0&&DAY_FOCUS[dow]){
    if(sh==='pm'){
      DAY_FOCUS[dow].forEach(it=>{total++;if(isCheckedAny(it))done++});
    }
  }
  if(sh==='night'&&dow>=0&&DAY_FOCUS[dow]){
    DAY_FOCUS[dow].forEach(it=>{total++;if(isCheckedAny(it))done++});
  }
  return{total,done,pct:total?Math.round(done/total*100):0};
}

function getDateG(g){
  const id=g==='f'?'checkDateF':'checkDateM';
  return document.getElementById(id).value;
}
// v2.51 — 로컬(KST) 날짜 직렬화. toISOString()(UTC)은 9시간 차로 날짜가 어긋나 ±1일 이동이 깨짐.
function fmtLocalDate(d){const y=d.getFullYear(),m=String(d.getMonth()+1).padStart(2,'0'),day=String(d.getDate()).padStart(2,'0');return `${y}-${m}-${day}`}
function setTodayG(g){
  const id=g==='f'?'checkDateF':'checkDateM';
  document.getElementById(id).value=fmtLocalDate(new Date());
  renderG(g);
}
function moveDateG(g,n){
  const id=g==='f'?'checkDateF':'checkDateM';
  const e=document.getElementById(id),d=new Date(e.value+'T00:00:00');
  d.setDate(d.getDate()+n);e.value=fmtLocalDate(d);
  renderG(g);
}
function setAdminToday(){document.getElementById('adminDate').value=fmtLocalDate(new Date());renderAdmin()}
function moveAdminDate(n){const e=document.getElementById('adminDate'),d=new Date(e.value+'T00:00:00');d.setDate(d.getDate()+n);e.value=fmtLocalDate(d);renderAdmin()}

async function renderG(g){
  const d=getDateG(g);
  const elId=g==='f'?'checklistF':'checklistM';
  const el=document.getElementById(elId);
  el.innerHTML='<div class="loading">불러오는 중...</div>';
  await loadState(d,g);
  drawUI(d,g);
}

function drawUI(d,gender){
  // gender = 'm' or 'f'
  const info=getDayInfo(d),dn=['일','월','화','수','목','금','토'],dt=new Date(d+'T00:00:00');
  const dow=dt.getDay();
  document.getElementById('dayType').innerHTML=`<span class="day-type ${info.cls}">${info.label}</span>`;
  document.getElementById('headerSub').textContent=`${d} (${dn[dow]})`;

  const nightMode=isNightShiftWorkerG(gender);
  const sched=nightMode?getNightSched(d):getSched(d);
  const elId=gender==='f'?'checklistF':'checklistM';
  const el=document.getElementById(elId);
  const submitBarId=gender==='f'?'submitBarF':'submitBarM';

  if(!sched){el.innerHTML='<div class="closed-msg">휴관일입니다.</div>';document.getElementById(submitBarId).style.display='none';return}
  document.getElementById(submitBarId).style.display='flex';

  const sfx=gender==='f'?'F':'M';
  const btnAm=document.getElementById('submitAm'+sfx);
  const btnPm=document.getElementById('submitPm'+sfx);
  const btnNight=document.getElementById('submitNight'+sfx);

  if(nightMode){
    btnAm.style.display='none';btnPm.style.display='none';btnNight.style.display='block';
  }else{
    btnAm.style.display='block';btnPm.style.display='block';btnNight.style.display='none';
  }

  /* 3조 선택바: 정상(주간)모드만 노출·동작. 야간모드는 숨김(기존 흐름 보존). */
  const roundBar=document.getElementById(gender==='f'?'roundBarF':'roundBarM');
  if(roundBar)roundBar.style.display=nightMode?'none':'flex';
  if(!nightMode)renderRoundBar(gender);

  let html='';
  let currentShift='';

  if(nightMode){
    const nightStats=getShiftStatsG(sched,'night',d,gender);
    html+=`<div class="shift-divider night-shift"><div class="shift-label">야간조 (탕청소 업체)</div>
      <div class="shift-progress">
        <div class="progress-text"><span>${nightStats.done}/${nightStats.total}</span><span>${nightStats.pct}%</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${nightStats.pct}%;background:var(--orange)"></div></div>
      </div>`;
    if(STATE._submitted_night){
      const who=STATE._submitter_night?` (${STATE._submitter_night})`:'';
      const when=STATE._submittedAt_night?new Date(STATE._submittedAt_night).toLocaleString('ko-KR'):'';
      html+=`<div class="shift-submitted">제출 완료${who} ${when}</div>`;
    }
    html+=`</div>`;

    sched.forEach(slot=>{
      html+=`<div class="time-slot"><div class="slot-header"><span class="slot-time night">${slot.slot}</span></div>`;
      slot.groups.forEach(g=>{
        const visItems=g.items.filter(it=>shouldShowItemForGender(it,gender));
        if(visItems.length===0)return;
        let gd=0;visItems.forEach(it=>{if(STATE[it.id])gd++});
        const ok=gd===visItems.length,badge=ok?'<span class="cat-badge done">완료</span>':`<span class="cat-badge pending">${gd}/${visItems.length}</span>`;
        html+=`<div class="category"><div class="cat-header" onclick="tog(this)"><span class="cat-title">${g.title}</span>${badge}</div><div class="cat-body${ok?'':' open'}">`;
        visItems.forEach(it=>{html+=renderItem(it,slot.shift,gender)});
        html+=groupSubmitBarHtml(g,gender);
        html+=quickAddBarHtml(slot.slot,slot.shift,g.title,gender);
        html+='</div></div>';
      });
      html+='</div>';
    });

    if(DAY_FOCUS[dow]){
      const focusItems=DAY_FOCUS[dow].filter(it=>shouldShowItemForGender(it,gender));
      if(focusItems.length>0){
        html+=renderDayFocusSection(dow,focusItems,'night',gender);
      }
    }

    updateNightSubmitButtonG(sched,nightStats,d,gender);

  }else{
    /* ── 3조(라운드) 단위 렌더 — 선택된 1개 조의 슬롯만 표시 ──
       조 통계·잠금은 라운드 독립. 기존 am/pm 집계(getShiftStatsG)·_submitted_am/pm은
       제출 시 submitRound가 함께 세팅(비회귀). 바닥 고정 버튼은 라운드 제출버튼으로 대체. */
    const curRound=getRoundG(gender);
    const rdef=roundDef(curRound)||ROUNDS[0];
    /* ── 2a: 항목 다회차 멤버십 + 구역(group.title)별 그룹핑 ──
       슬롯 필터 대신, 전 슬롯 항목 중 itemRounds(it)가 현재 조를 포함하는 것만 수집.
       옛 슬롯 시간 라벨은 화면에서 비표시(데이터 slot 필드는 보존). 구역 title로 버킷팅. */
    const zoneOrder=[];           // 구역 제목 등장 순서
    const zoneMap={};             // title → { items:[{...it,slot,shift,itemShift}], group:<대표 group 객체> }
    sched.forEach(slot=>{
      const itemShift=slot.shift==='all'?'pm':slot.shift;
      slot.groups.forEach(g=>{
        g.items.forEach(it=>{
          if(!shouldShowItemForGender(it,gender))return;
          const ctx={...it,slot:slot.slot,shift:slot.shift};
          if(itemRounds(ctx).indexOf(curRound)<0)return;   // 이 조 멤버 아님 → 스킵
          const title=g.title;
          if(!zoneMap[title]){zoneMap[title]={items:[],group:g,slot:slot.slot,shift:slot.shift};zoneOrder.push(title);}
          zoneMap[title].items.push({it,itemShift});
        });
      });
    });
    /* 매뉴얼에서 숨긴 구역 점검에서도 제외 + 그룹 순서 적용 */
    if(typeof getHiddenGroups==='function'){const _hg=getHiddenGroups();for(let zi=zoneOrder.length-1;zi>=0;zi--){if(_hg.has(zoneOrder[zi]))zoneOrder.splice(zi,1);}}
    if(typeof groupRank==='function')zoneOrder.sort((a,b)=>groupRank(a)-groupRank(b));
    /* 요일별 집중청소는 마감조(close1)에 합류(기존 pm 통계 포함과 정합) */
    const focusInRound=(curRound==='close1'&&DAY_FOCUS[dow])?DAY_FOCUS[dow].filter(it=>shouldShowItemForGender(it,gender)):[];

    /* 이 조 진행도 계산(가시 항목 기준, 회차별 체크 키) */
    let rTotal=0,rDone=0;
    zoneOrder.forEach(title=>zoneMap[title].items.forEach(({it})=>{rTotal++;if(isChecked(it.id,curRound))rDone++;}));
    focusInRound.forEach(it=>{rTotal++;if(isChecked(it.id,curRound))rDone++});
    const rPct=rTotal?Math.round(rDone/rTotal*100):0;
    const rSubmitted=isRoundSubmitted(d,gender,curRound);

    /* 조 헤더(진행바 + 제출완료 표시) */
    html+=`<div class="shift-divider"><div class="shift-label">${rdef.name} (${rdef.time})</div>
      <div class="shift-progress">
        <div class="progress-text"><span>${rDone}/${rTotal}</span><span>${rPct}%</span></div>
        <div class="progress-bar"><div class="progress-fill" style="width:${rPct}%;background:var(--green)"></div></div>
      </div>`;
    if(rSubmitted){
      const meta=roundSubMeta(d,gender,curRound);
      const who=meta.by?` (${meta.by})`:'';
      const when=meta.at?new Date(meta.at).toLocaleString('ko-KR'):'';
      html+=`<div class="shift-submitted">제출 완료${who} ${when}</div>`;
    }
    html+=`</div>`;

    if(zoneOrder.length===0&&focusInRound.length===0){
      html+=`<div class="closed-msg" style="padding:40px 20px;">이 시간대 점검 항목이 아직 없습니다.<br><span style="font-size:13px;color:var(--dim);">셋업 편집에서 추가할 수 있습니다.</span></div>`;
    }

    /* 구역(title)별 카드 — 옛 슬롯 시간 헤더 없이 바로 구역 단위로 출력. 빈 구역은 위에서 미생성. */
    zoneOrder.forEach(title=>{
      const bucket=zoneMap[title];
      const visItems=bucket.items;          // [{it,itemShift}]
      /* 매뉴얼에서 정한 그룹 내 순서(orderMap) 점검에도 적용 */
      const _om=(typeof getItemOrder==='function')?getItemOrder():{};
      visItems.sort((a,b)=>{const oa=_om[a.it.id],ob=_om[b.it.id];if(oa==null&&ob==null)return 0;if(oa==null)return 1;if(ob==null)return -1;return oa-ob;});
      let gd=0;visItems.forEach(({it})=>{if(isChecked(it.id,curRound))gd++});
      const ok=gd===visItems.length,badge=ok?'<span class="cat-badge done">완료</span>':`<span class="cat-badge pending">${gd}/${visItems.length}</span>`;
      html+=`<div class="category"><div class="cat-header" onclick="tog(this)"><span class="cat-title">${(typeof groupDisplay==='function')?groupDisplay(title):title}</span>${badge}</div><div class="cat-body${ok?'':' open'}">`;
      visItems.forEach(({it,itemShift})=>{
        html+=renderItem(it,itemShift,gender,curRound);
      });
      html+=groupSubmitBarHtml(bucket.group,gender,curRound);
      /* 빠른 항목 추가 — 대표 슬롯/시프트로 등록(커스텀은 roundOfSlot 폴백 단일 라운드) */
      html+=quickAddBarHtml(bucket.slot,bucket.shift,title,gender);
      html+='</div></div>';
    });

    if(focusInRound.length>0){
      html+=renderDayFocusSection(dow,focusInRound,'pm',gender,curRound);
    }

    /* 라운드 제출 버튼(인-플로우) — 바닥 고정 버튼 대신. 점검자 입력 + 1건 이상 체크 시 활성. */
    const sub=getSubmitterForGender(gender);
    let rBtn='';
    if(rSubmitted){
      if(rDone<rTotal){
        rBtn=`<button class="submit-btn primary" style="max-width:none;width:100%;" onclick="submitRound('${curRound}','${gender}')"${sub?'':' disabled'}>➕ 이 조 추가 제출 (남은 ${rTotal-rDone}건)</button>`;
      }else{
        rBtn=`<button class="submit-btn submitted" style="max-width:none;width:100%;" disabled>이 조 제출 완료</button>`;
      }
    }else if(!sub){
      rBtn=`<button class="submit-btn primary" style="max-width:none;width:100%;" disabled>↑ 점검자 이름을 먼저 입력</button>`;
    }else{
      rBtn=`<button class="submit-btn primary" style="max-width:none;width:100%;" onclick="submitRound('${curRound}','${gender}')"${rDone===0?' disabled':''}>이 조 점검 제출 (${rDone}/${rTotal})</button>`;
    }
    html+=`<div style="margin:16px 0 8px;">${rBtn}</div>`;

    /* 바닥 고정 제출바는 라운드 모드에서 숨김(라운드 버튼이 대체) */
    document.getElementById(submitBarId).style.display='none';
  }

  el.innerHTML=html;
  setCheckTime(gender);
}

/* 점검 타이머 — 시작 ▶ / 완료 ■ / 다시 ↺ 상태머신. 시작·완료 시각과 소요(분)을
   날짜+성별별 STATE에 적립, 제출 스냅샷에 함께 기록 (시우·GM 2026-06-11). */
function _hhmm(ms){const dt=new Date(ms);return String(dt.getHours()).padStart(2,'0')+':'+String(dt.getMinutes()).padStart(2,'0')}
function _timerDuration(start,end){
  if(!start||!end)return null;
  const m=Math.round((end-start)/60000);
  return (m>=0&&m<24*60)?m:null; // 음수·자정넘김 등 비정상은 빈값
}
/* 활성 타이머 키 결정: 정상(주간)모드=라운드별 독립 키, 야간모드=기존 날짜+성별 키.
   라운드 전환 시 그 조의 타이머 상태가 자연히 복원됨(키가 라운드 포함). */
function activeTimerKeys(gender){
  const d=getDateG(gender);
  if(isNightShiftWorkerG(gender)){
    return {sk:'timerStart_'+d+'_'+gender, ek:'timerEnd_'+d+'_'+gender};
  }
  const rk=getRoundG(gender);
  const t=timerKeys(d,gender,rk);
  return {sk:t.sk, ek:t.ek};
}
/* 해당 날짜+성별(+라운드) STATE 값으로 타이머 UI 복원 (없으면 idle). drawUI 끝에서 호출. */
function setCheckTime(gender){
  const btn=document.getElementById(gender==='f'?'timerBtnF':'timerBtnM');
  const el=document.getElementById(gender==='f'?'checkTimeF':'checkTimeM');
  if(!btn||!el)return;
  const k=activeTimerKeys(gender);
  const start=STATE[k.sk];
  const end=STATE[k.ek];
  btn.classList.remove('running','done');
  if(!start){
    btn.textContent='▶ 점검 시작';el.textContent='--:--';
  }else if(start&&!end){
    btn.textContent='■ 점검 완료';btn.classList.add('running');
    el.textContent='시작 '+_hhmm(start)+' (진행중)';
  }else{
    btn.textContent='↺ 다시';btn.classList.add('done');
    const dur=_timerDuration(start,end);
    el.textContent=_hhmm(start)+' → '+_hhmm(end)+(dur!=null?' ('+dur+'분)':'');
  }
}
/* idle→running(시작 기록) → done(완료·소요분) → idle(리셋, 새 점검) */
function toggleCheckTimer(gender){
  const d=getDateG(gender);
  const k=activeTimerKeys(gender);
  const sk=k.sk, ek=k.ek;
  const start=STATE[sk], end=STATE[ek];
  if(!start){                       // idle → running
    STATE[sk]=Date.now();delete STATE[ek];
  }else if(start&&!end){            // running → done
    STATE[ek]=Date.now();
  }else{                            // done → idle (새 점검)
    delete STATE[sk];delete STATE[ek];
  }
  saveState(d,gender);
  setCheckTime(gender);
}

/* v2.48 — 점검 항목 사용자 수정 기능. v2.49 onclick HTML 충돌 fix
   v2.51 — 시트(saveItems) 기반 부활: 기본 항목 편집은 같은 id의 shadow 항목을
   CUSTOM_ITEMS에 저장(시트 영구), renderItem이 override 맵으로 덮어쓴다.
   shadow = id가 'custom_' 또는 'cx_'으로 시작하지 않는 CUSTOM_ITEMS 항목(기본 항목 id 그대로). */
/* isAddedItem — 추가 항목 판별. 레거시 custom_ 및 신규 cx_ 둘 다 인식. */
function isAddedItem(id){ return /^(custom_|cx_)/.test(String(id||'')); }
function isShadowItem(it){ return it && it.id && !isAddedItem(it.id); }
/* getItemOverrides — CUSTOM_ITEMS의 shadow 항목에서 {id:{name,detail,slot,shift,cat}} 맵 구성.
   renderItem이 이 맵으로 기본 항목 표시를 덮어쓴다(시트가 SSOT). */
function getItemOverrides(){
  const map={};
  (CUSTOM_ITEMS||[]).forEach(it=>{
    if(!isShadowItem(it)) return;
    const o={};
    if(it.name!==undefined && it.name!=='') o.name=it.name;
    if(it.detail!==undefined && it.detail!=='') o.detail=it.detail;
    if(it.slot!==undefined && it.slot!=='') o.slot=it.slot;
    if(it.shift!==undefined && it.shift!=='') o.shift=it.shift;
    if(it.category!==undefined && it.category!=='') o.cat=it.category;
    if(it.gender!==undefined && it.gender!=='') o.gender=it.gender;
    if(Array.isArray(it.rounds) && it.rounds.length) o.rounds=it.rounds;
    if(it.sched!==undefined && it.sched!=='') o.sched=it.sched;
    map[it.id]=o;
  });
  return map;
}
function findBaseItem(id){
  const today=kstToday();   // KST 오늘(UTC 어긋남 차단)
  let found=null;
  function scan(sched){
    if(!sched||found)return;
    sched.forEach(slot=>slot.groups.forEach(g=>g.items.forEach(it=>{
      if(it.id===id)found={name:it.name,detail:it.detail,slot:slot.slot,shift:slot.shift,cat:g.title,gender:it.gender||'all'};
    })));
  }
  scan(getSched(today));
  scan(getNightSched(today));
  if(!found&&typeof DAY_FOCUS!=='undefined'){
    for(const dow in DAY_FOCUS){
      DAY_FOCUS[dow].forEach(it=>{
        if(it.id===id)found={name:it.name,detail:it.detail,slot:'요일별 집중 청소',shift:'focus',cat:'요일별 집중'};
      });
      if(found)break;
    }
  }
  return found||{name:'',detail:'',slot:'',shift:'am',cat:''};
}
let _editingItemId=null;
window.editItem=function(id){
  const ov=getItemOverrides()[id]||{};
  const base=findBaseItem(id);
  _editingItemId=id;
  document.getElementById('editName').value=ov.name||base.name;
  document.getElementById('editDetail').value=ov.detail||base.detail;
  document.getElementById('editSlot').value=ov.slot||base.slot||'';
  document.getElementById('editShift').value=ov.shift||base.shift||'am';
  document.getElementById('editCat').value=ov.cat||base.cat||'';
  const _ci=(CUSTOM_ITEMS||[]).find(x=>x.id===id);
  const _gsel=document.getElementById('editGender');
  if(_gsel)_gsel.value=(_ci&&_ci.gender)||ov.gender||base.gender||'all';
  // 회차(조) 다중선택 — 현재 등장 회차 pre-check
  let _curR=[];
  try{ _curR=itemRounds({id:id, rounds:(_ci&&_ci.rounds)||ov.rounds, slot:ov.slot||base.slot, shift:ov.shift||base.shift})||[]; }catch(e){ _curR=[]; }
  const _rc=document.getElementById('editRounds');
  if(_rc)_rc.innerHTML=(typeof ROUND_KEYS!=='undefined'?ROUND_KEYS:[]).map(function(rk){return '<label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer;background:var(--bg);border:1px solid var(--border);border-radius:7px;padding:6px 10px;"><input type="checkbox" class="editRoundCb" value="'+rk+'"'+(_curR.indexOf(rk)>=0?' checked':'')+'> '+roundLabel(rk)+'</label>';}).join('');
  // 일정(요일·몇째주) 체크박스 렌더 — item.sched("mon,wed,fri|2") 우선, 없으면 빈값
  renderSchedPickers((_ci&&_ci.sched)||ov.sched||'');
  document.getElementById('itemEditModal').style.display='flex';
};
/* 일정 구조저장 형식: "days|weeks" — days=요일csv(mon..sun), weeks=몇째주csv(1..5) 또는 'b'(격주). 빈=매일/매주. */
const SCHED_DAYS=[['mon','월'],['tue','화'],['wed','수'],['thu','목'],['fri','금'],['sat','토'],['sun','일']];
const SCHED_WEEKS=[['1','첫째'],['2','둘째'],['3','셋째'],['4','넷째'],['5','다섯째'],['b','격주']];
function parseSched(s){ s=String(s||''); const p=s.split('|'); return { days:(p[0]||'').split(',').filter(Boolean), weeks:(p[1]||'').split(',').filter(Boolean) }; }
function buildSched(days,weeks){ days=days||[];weeks=weeks||[]; if(!days.length&&!weeks.length)return ''; return days.join(',')+'|'+weeks.join(','); }
function renderSchedPickers(sched){
  const cur=parseSched(sched);
  const dEl=document.getElementById('editDays');
  if(dEl)dEl.innerHTML=SCHED_DAYS.map(function(d){return '<label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer;background:var(--paper);border:1px solid var(--border);border-radius:7px;padding:5px 9px;"><input type="checkbox" class="editDayCb" value="'+d[0]+'"'+(cur.days.indexOf(d[0])>=0?' checked':'')+'> '+d[1]+'</label>';}).join('');
  const wEl=document.getElementById('editWeeks');
  if(wEl)wEl.innerHTML=SCHED_WEEKS.map(function(w){return '<label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer;background:var(--paper);border:1px solid var(--border);border-radius:7px;padding:5px 9px;"><input type="checkbox" class="editWeekCb" value="'+w[0]+'"'+(cur.weeks.indexOf(w[0])>=0?' checked':'')+'> '+w[1]+(w[0]==='b'?'':'주')+'</label>';}).join('');
}
window.saveItemEdit=function(){
  const id=_editingItemId;
  if(!id)return;
  const base=findBaseItem(id);
  const newName=document.getElementById('editName').value.trim();
  const newDetail=document.getElementById('editDetail').value;
  const newSlot=document.getElementById('editSlot').value.trim();
  const newShift=document.getElementById('editShift').value;
  const newCat=document.getElementById('editCat').value.trim();
  const _ge=document.getElementById('editGender');
  const newGender=_ge?(_ge.value||'all'):'all';
  const newRounds=[].slice.call(document.querySelectorAll('#editRounds .editRoundCb')).filter(function(c){return c.checked;}).map(function(c){return c.value;});
  const newDays=[].slice.call(document.querySelectorAll('#editDays .editDayCb')).filter(function(c){return c.checked;}).map(function(c){return c.value;});
  const newWeeks=[].slice.call(document.querySelectorAll('#editWeeks .editWeekCb')).filter(function(c){return c.checked;}).map(function(c){return c.value;});
  const newSched=buildSched(newDays,newWeeks);
  const list=(CUSTOM_ITEMS||[]).slice();
  let item=list.find(it=>it.id===id);
  if(item){
    /* 이미 CUSTOM_ITEMS에 존재(추가 항목 custom_… 또는 기존 shadow) → 필드 갱신 */
    item.name=newName||item.name;
    item.detail=newDetail;
    if(newSlot)item.slot=newSlot;
    if(newShift)item.shift=newShift;
    if(newCat)item.category=newCat;
    item.gender=newGender;
    if(newRounds.length)item.rounds=newRounds;
    item.sched=newSched;   /* 일정(요일·몇째주) — 빈문자면 매일/상시로 복귀 */
  }else{
    /* 기본 항목(시트에 없음) → 같은 id로 shadow 항목 생성(baseline 복사 후 편집값 반영) */
    item={
      id:id,
      slot:newSlot||base.slot||'상시',
      shift:newShift||base.shift||slotToShiftFront(newSlot||base.slot),
      dayType:'both',
      gender:newGender,
      category:newCat||base.cat||'추가 점검',
      name:newName||base.name,
      detail:newDetail!==undefined?newDetail:base.detail,
      order:undefined,
      rounds:newRounds.length?newRounds:undefined,
      sched:newSched   /* 일정(요일·몇째주) */
    };
    list.push(item);
  }
  if(typeof markEditTs==='function')markEditTs(id);   // '수정됨' 배지 = 오늘만 표시(다음날 사라짐)
  mgmtSaveItems(list);   /* CUSTOM_ITEMS 갱신 + 시트 저장(saveItems POST) */
  document.getElementById('itemEditModal').style.display='none';
  _editingItemId=null;
  renderG(activeGenderTab);
  if(typeof renderManualItems==='function')renderManualItems();
};
window.cancelItemEdit=function(){
  document.getElementById('itemEditModal').style.display='none';
  _editingItemId=null;
};
window.resetItem=function(id){
  if(!confirm('이 항목을 기본값으로 초기화할까요?'))return;
  /* shadow(기본항목 편집분)면 제거 → 기본값 복귀. custom_ 추가항목은 초기화 버튼 미노출이라 여기 도달 안 함 */
  const next=(CUSTOM_ITEMS||[]).filter(it=>it.id!==id);
  mgmtSaveItems(next);   /* 시트에서도 shadow 제거 */
  renderG(activeGenderTab);
  if(typeof renderManualItems==='function')renderManualItems();
};
/* ── 매뉴얼 탭 셋업: 항목 추가/삭제/일괄정리 (GM 2026-06-12) — 시트(점검항목) 단일출처 ── */
/* 매뉴얼 '＋ 항목 추가' = 이슈승격과 동일한 모달 재사용(회차 다중선택 확보) — 원본 이슈 없이 신규.
   회차를 골라야 점검의 그 조(오전/오후/마감)에 등장. mgmtGenerateId로 custom_ 1건 생성. */
window.manualAddItem=function(cat){
  promoteSourceId=null;   // 원본 이슈 없음(신규 추가) → promoteSave가 reflected 마킹 건너뜀
  const t=document.getElementById('promoteTitle'); if(t)t.textContent='점검·매뉴얼 항목 추가';
  const st=document.getElementById('promoteSubtitle'); if(st)st.textContent='새 점검 항목을 등록합니다. 선택한 회차(조)에 점검 화면과 매뉴얼에 함께 등장합니다.';
  const nameEl=document.getElementById('promoteName'); if(nameEl)nameEl.value='';
  const detEl=document.getElementById('promoteDetail'); if(detEl)detEl.value='';
  const genEl=document.getElementById('promoteGender'); if(genEl)genEl.value='all';
  const catSel=document.getElementById('promoteCatSelect');
  if(catSel){
    // 그룹 ＋ 추가 = 그 구역에 고정. 기존 구역 + (사용자 추가 구역) 포함, 새 구역 임의생성은 금지.
    const titles=promoteZoneTitles().slice();
    if(cat&&titles.indexOf(cat)<0)titles.push(cat);
    catSel.innerHTML=titles.map(t2=>`<option value="${escapeAttr(t2)}">${escapeHTML((typeof groupDisplay==='function')?groupDisplay(t2):t2)}</option>`).join('');
    if(cat)catSel.value=cat;
    else if(titles.length)catSel.value=titles[0];
    catSel.disabled=false;   // 기존 구역 중 선택 가능(클릭한 구역이 기본). 새 구역 임의생성만 금지(+직접입력 없음).
  }
  promoteOnCatChange();
  const catIn=document.getElementById('promoteCatCustom');
  if(catIn)catIn.style.display='none';
  // 회차: 기본 오후조 1개 체크(GM이 자유 조정) — 최소 1개 강제는 promoteSave가 검증
  ROUND_KEYS.forEach(rk=>{const cb=document.getElementById('promoteRound_'+rk);if(cb)cb.checked=(rk==='pm1');});
  const hint=document.getElementById('promoteRoundHint'); if(hint)hint.style.display='none';
  const modal=document.getElementById('promoteModal'); if(modal)modal.style.display='flex';
};
window.manualDeleteItem=function(id){
  const isCustom=isAddedItem(id);
  const hasShadow=(CUSTOM_ITEMS||[]).some(it=>it.id===id);   // 시트에 같은 id 항목(추가 or 편집분·옛 b6)이 있나
  if(isCustom||hasShadow){
    if(!confirm('이 항목을 삭제할까요? (시트에서도 제거)'))return;
    const next=(CUSTOM_ITEMS||[]).filter(it=>it.id!==id);
    mgmtSaveItems(next);
    if(!isCustom){ const h=getHiddenIds(); h.add(id); saveHiddenIds(h); }  // 코드 기본항목과 id 겹치면 숨김도 같이
  }else{
    // 순수 기본 항목(코드) = 숨김. 코드 기본값 보존 → 필요 시 '숨김 복구'로 되돌림.
    if(!confirm('이 기본 항목을 점검·매뉴얼에서 숨길까요? (하단 "숨긴 항목"에서 복구 가능)'))return;
    const h=getHiddenIds(); h.add(id); saveHiddenIds(h);
  }
  renderG(activeGenderTab);
  if(typeof renderManualItems==='function')renderManualItems();
};
window.manualUnhideItem=function(id){
  const h=getHiddenIds(); h.delete(id); saveHiddenIds(h);
  renderG(activeGenderTab);
  if(typeof renderManualItems==='function')renderManualItems();
};
/* 매뉴얼 그룹 내 항목 정렬(위/아래) — id→정렬값 맵. 매뉴얼·점검 양쪽 동일 순서. GM 2026-06-12.
   ※ 현재 이 PC(localStorage) 기준. 전 기기 동기화는 후속. */
function getItemOrder(){ try{return JSON.parse(localStorage.getItem('wcheck_item_order')||'{}')||{}}catch(e){return {}} }
function saveItemOrder(m){ localStorage.setItem('wcheck_item_order',JSON.stringify(m)); }
/* 같은 카테고리(그룹) 내에서 항목을 위(-1)/아래(+1)로 1칸 이동 */
window.moveManualItem=function(id,dir){
  const cats=window._catItemIds||{};
  let cat=null; for(const c in cats){ if(cats[c].indexOf(id)>=0){cat=c;break;} }
  if(!cat)return;
  const ids=cats[cat].slice();
  const i=ids.indexOf(id), j=i+dir;
  if(j<0||j>=ids.length)return;
  const tmp=ids[i]; ids[i]=ids[j]; ids[j]=tmp;
  const om=getItemOrder();
  ids.forEach((x,k)=>{ om[x]=k; });   // 해당 그룹 전체에 순차 정렬값 재부여(안정)
  saveItemOrder(om);
  if(typeof renderManualItems==='function')renderManualItems();
  if(typeof renderG==='function')renderG(activeGenderTab);   // 점검에도 반영
};
/* 그룹(구역) 순서 — 기본값(GM 2026-06-12: C세탁물 상단·마감점검은 E외부 아래) + localStorage 사용자 조정. */
const GROUP_ORDER_DEFAULT=['오픈 점검','A 사우나점검','B 락커룸','D 내부','E 외부','마감 점검','교대 인수인계'];
function getGroupOrder(){ try{return JSON.parse(localStorage.getItem('wcheck_group_order')||'{}')||{}}catch(e){return {}} }
function saveGroupOrder(m){ localStorage.setItem('wcheck_group_order',JSON.stringify(m)); }
function groupRank(title){
  const o=getGroupOrder();
  if(o[title]!=null)return o[title];
  const i=GROUP_ORDER_DEFAULT.indexOf(title);
  return i>=0?i:90;   // 미정의 그룹은 뒤로(동순위는 안정정렬로 등장순 유지)
}
/* 그룹을 위(-1)/아래(+1)로 1칸 이동 — 매뉴얼·점검 동일 순서 */
window.moveManualGroup=function(title,dir){
  const order=(window._groupSorted||[]).slice();
  const i=order.indexOf(title), j=i+dir;
  if(i<0||j<0||j>=order.length)return;
  const tmp=order[i]; order[i]=order[j]; order[j]=tmp;
  const o=getGroupOrder();
  order.forEach((t,k)=>{ o[t]=k; });   // 전체 그룹에 순차 순위 재부여
  saveGroupOrder(o);
  if(typeof renderManualItems==='function')renderManualItems();
  if(typeof renderG==='function')renderG(activeGenderTab);
};
/* 일정 배지 — 항목명/상세에 적은 요일·주기를 배지로(헬스장 월화수목금처럼). GM 2026-06-12.
   요일(월~일): 'X요일'·'월수금'·'화목'·'월화수목금' / df_ id. 주기: 격주·둘째주·주N회·월N회·2·4주·매주·휴관일. */
function scheduleBadges(it, name, detail){
  const M={mon:'월',tue:'화',wed:'수',thu:'목',fri:'금',sat:'토',sun:'일'};
  const order=['월','화','수','목','금','토','일']; const dset={};
  // 구조저장(it.sched "mon,wed,fri|2") 우선 — 매뉴얼 편집 체크박스로 설정된 정식 일정.
  const _sc=(it&&it.sched)?String(it.sched):'';
  if(_sc){
    const _p=_sc.split('|'); const _d=(_p[0]||'').split(',').filter(Boolean); const _w=(_p[1]||'').split(',').filter(Boolean);
    let h2='';
    _d.forEach(function(dk){ if(M[dk])h2+=' <span style="font-size:10px;color:#7b5ea7;background:rgba(123,94,167,0.16);padding:1px 6px;border-radius:6px;font-weight:700;">'+M[dk]+'</span>'; });
    const WL={'1':'첫째주','2':'둘째주','3':'셋째주','4':'넷째주','5':'다섯째주','b':'격주'};
    _w.forEach(function(wk){ if(WL[wk])h2+=' <span style="font-size:10px;color:#1f8a70;background:rgba(31,138,112,0.14);padding:1px 6px;border-radius:6px;font-weight:700;">'+WL[wk]+'</span>'; });
    return h2;
  }
  // sched 미설정 = 배지 없음. 요일·주기(격주·몇째주·주N회·휴관일 등) 모두 sched 체크값에서만 표시.
  // detail/name 텍스트 파싱 전면 폐기 — 체크 안 했는데 떠 보이던 버그 차단(GM 2026-06-13).
  return '';
}
/* ── 구역(그룹) 자체 CRUD — 추가/이름변경/삭제(숨김). 매뉴얼·점검 동일 반영. GM 2026-06-12.
   rename = 원본 구역명→표시명 맵(아이템 데이터 무변경, 표시단계 매핑). hidden = 구역 통째 숨김. added = 빈 구역 등록. */
function getGroupRename(){ try{return JSON.parse(localStorage.getItem('wcheck_group_rename')||'{}')||{}}catch(e){return {}} }
function getHiddenGroups(){ try{return new Set(JSON.parse(localStorage.getItem('wcheck_group_hidden')||'[]'))}catch(e){return new Set()} }
function getAddedGroups(){ try{return JSON.parse(localStorage.getItem('wcheck_group_added')||'[]')||[]}catch(e){return []} }
function groupDisplay(t){ const r=getGroupRename(); return r[t]||t; }
/* 배지(수정됨/추가) 만료 — 하루만 표시, 다음날(KST) 사라짐. GM 2026-06-12.
   추가=custom_ id의 생성 타임스탬프 기준 / 수정됨=편집 시각 localStorage 기록 기준. */
function getEditTs(){ try{return JSON.parse(localStorage.getItem('wcheck_edit_ts')||'{}')||{}}catch(e){return {}} }
function markEditTs(id){ const m=getEditTs(); m[id]=kstToday(); localStorage.setItem('wcheck_edit_ts',JSON.stringify(m)); }
function isEditFresh(id){ return getEditTs()[id]===kstToday(); }
function isCustomFresh(id){
  const s=String(id||'');
  // 신규 cx_YYYYMMDD_NNN 형식: 날짜를 id에서 직접 파싱
  const cxm=s.match(/^cx_(\d{4})(\d{2})(\d{2})_/);
  if(cxm){ return (cxm[1]+cxm[2]+cxm[3])===kstToday().replace(/-/g,''); }
  // 레거시 custom_<ms>_<rand> 형식: 타임스탬프 기반
  const m=s.match(/^custom_(\d+)/); if(!m)return false;
  try{ const d=new Date(Number(m[1])+9*3600*1000); return d.toISOString().slice(0,10)===kstToday(); }catch(e){ return false; }
}
window.addManualGroup=function(){
  const n=prompt('새 구역(그룹) 이름 — 예: F 주차장'); if(n==null)return;
  const t=n.trim(); if(!t){alert('이름을 입력하세요.');return;}
  const a=getAddedGroups(); if(a.indexOf(t)<0){a.push(t);localStorage.setItem('wcheck_group_added',JSON.stringify(a));}
  if(typeof renderManualItems==='function')renderManualItems();
  alert('빈 구역 "'+t+'" 추가됨. 그 구역의 ＋ 항목 추가로 항목을 넣으세요.');
};
window.renameManualGroup=function(orig){
  const cur=groupDisplay(orig);
  const n=prompt('구역 이름 변경', cur); if(n==null)return;
  const t=n.trim(); if(!t)return;
  const r=getGroupRename(); if(t===orig){delete r[orig];}else{r[orig]=t;} localStorage.setItem('wcheck_group_rename',JSON.stringify(r));
  if(typeof renderManualItems==='function')renderManualItems();
  if(typeof renderG==='function')renderG(activeGenderTab);
};
window.deleteManualGroup=function(orig){
  if(!confirm('구역 "'+groupDisplay(orig)+'" 전체를 점검·매뉴얼에서 제거할까요?\n(이 구역의 모든 항목이 함께 빠집니다 — 하단 "숨긴 구역"에서 복구 가능)'))return;
  const h=getHiddenGroups(); h.add(orig); localStorage.setItem('wcheck_group_hidden',JSON.stringify([...h]));
  if(typeof renderManualItems==='function')renderManualItems();
  if(typeof renderG==='function')renderG(activeGenderTab);
};
window.restoreManualGroup=function(orig){
  const h=getHiddenGroups(); h.delete(orig); localStorage.setItem('wcheck_group_hidden',JSON.stringify([...h]));
  if(typeof renderManualItems==='function')renderManualItems();
  if(typeof renderG==='function')renderG(activeGenderTab);
};
window.manualPurgeCustom=function(){
  const customs=(CUSTOM_ITEMS||[]).filter(it=>isAddedItem(it.id));
  if(!customs.length){alert('정리할 추가항목(custom_/cx_)이 없습니다.');return;}
  if(!confirm('점검 화면에서 즉석 추가돼 쌓인 추가항목(custom_/cx_) '+customs.length+'건을 모두 삭제합니다.\n(기본 항목 수정분=수정됨 은 유지됩니다.)\n계속할까요?'))return;
  const next=(CUSTOM_ITEMS||[]).filter(it=>!isAddedItem(it.id));
  mgmtSaveItems(next);
  renderG(activeGenderTab);
  if(typeof renderManualItems==='function')renderManualItems();
  alert(customs.length+'건 정리 완료. (다른 기기는 새로고침)');
};

function renderItem(it,shift,gender,round){
  const g=gender||activeGenderTab;
  /* 회차별 체크 독립: round 있으면 라운드 키, 없으면(야간·매뉴얼 등) 레거시 STATE[id]. */
  const _ckd=round?isChecked(it.id,round):!!STATE[it.id];
  const ck=_ckd?'checked':'',cls=_ckd?'item checked':'item';
  const iss=STATE['iss_'+it.id]||'',tip=STATE['tip_'+it.id]||'';
  /* v2.48 — 사용자 override 반영 */
  const ov=getItemOverrides()[it.id]||{};
  const itemName=ov.name||it.name;
  const itemDetail=ov.detail||it.detail;
  const isEdited=!!(ov.name||ov.detail);
  const det=itemDetail.replace(/\n/g,'<br>');
  const esc=escapeAttr;
  // Use unique element ids per gender tab to avoid collisions
  const pfx=g+'_';
  /* 점검 화면 항목 편집/초기화 제거(GM 2026-06-12): 항목 수정·추가는 '매뉴얼' 탭 단일출처. 점검=체크+이슈/노하우만. */
  const shiftLabel={am:'오전조',pm:'오후조',night:'야간조',focus:'요일집중',all:'전체'};
  let metaInfo='';
  if(ov.slot||ov.shift||ov.cat){
    const m=[];
    if(ov.slot)m.push('시간 '+ov.slot);
    if(ov.shift)m.push(shiftLabel[ov.shift]||ov.shift);
    if(ov.cat)m.push('카테고리 '+ov.cat);
    metaInfo='<span style="font-size:10px;color:#5b9fd5;margin-left:6px;">('+m.join(' · ')+')</span>';
  }
  /* 수정됨 메타(시간·시간대·카테고리)는 길고 무의미 → 제거(GM 2026-06-12). 작은 '수정됨'만(하루 만료). */
  const editedTag=(isEdited&&(typeof isEditFresh!=='function'||isEditFresh(it.id)))?'<span style="font-size:10px;color:#e6c84e;font-weight:700;margin-left:4px;">수정됨</span>':'';
  /* 온도 측정칸 (해당 항목만) — 기준 벗어나면 빨간 경고 */
  const tempFields=tempFieldsFor(it.id);
  let tempHtml='';
  if(tempFields){
    const cells=tempFields.map(f=>{
      const tid=`${pfx}temp_${it.id}_${f.key}`;
      const val=STATE['temp_'+it.id+'_'+f.key];
      const hasVal=val!==undefined&&val!==''&&val!==null;
      const num=hasVal?Number(val):NaN;
      const bad=hasVal&&!isNaN(num)&&(num<f.min||num>f.max);
      const warn=bad?`<span style="color:#c0392b;font-weight:700;font-size:11px;margin-left:4px;">⚠ 기준 ${f.min}~${f.max}${f.unit}</span>`:'';
      const inStyle=bad?'border-color:#c0392b;color:#c0392b;background:#fce8e4;':'';
      return `<div style="display:flex;align-items:center;gap:6px;margin:3px 0;">
        <span style="font-size:12px;color:var(--dim);min-width:48px;">${f.label}</span>
        <input type="number" step="0.1" inputmode="decimal" class="temp-input" id="${tid}" value="${hasVal?esc(String(val)):''}" placeholder="${f.min}~${f.max}" style="width:80px;padding:4px 6px;border:1px solid var(--border);border-radius:6px;font-size:13px;${inStyle}" onchange="onTemp('${it.id}','${f.key}','${tid}','${g}')">
        <span style="font-size:12px;color:var(--dim);">${f.unit}</span>${warn}
      </div>`;
    }).join('');
    tempHtml=`<div class="temp-box" style="margin-top:6px;padding:6px 8px;background:rgba(91,159,213,0.06);border-radius:8px;"><div style="font-size:11px;color:#5b9fd5;font-weight:700;margin-bottom:2px;">온도 측정</div>${cells}</div>`;
  }
  /* 반영완료 토글 — 이슈/노하우 입력이 있을 때만 노출 */
  const hasMemo=!!(iss||tip);
  const isRef=!!STATE['reflected_'+it.id];
  const refBtn=hasMemo?`<button class="tiny-btn" style="${isRef?'background:rgba(44,138,79,0.14);color:#2c8a4f;border-color:rgba(44,138,79,0.4);':'background:rgba(140,139,131,0.12);color:#8c8b83;border-color:rgba(140,139,131,0.3);'}font-size:12px;" title="이슈/노하우 후속 조치 완료 표시" onclick="toggleReflected('${it.id}','${g}')">${isRef?'✓ 반영완료':'반영완료'}</button>`:'';
  /* 2b-1(2026-06-11 시우): 이슈 → 점검·매뉴얼 항목 승격. 이슈 텍스트가 있을 때만 노출.
     클릭 시 현재 항목의 구역(카테고리)·라운드·슬롯 컨텍스트를 PROMOTE_CTX에 적립해 모달이 prefill. */
  PROMOTE_CTX[it.id]={cat:(ov.cat||it.cat||it.category||''),slot:(ov.slot||it.slot||''),shift:(ov.shift||it.shift||shift||''),round:round||'',gender:g};
  const promoteBtn=iss?`<button class="tiny-btn" style="background:rgba(91,159,213,0.12);color:#5b9fd5;border-color:rgba(91,159,213,0.35);font-size:12px;" title="이 이슈를 점검표·매뉴얼 항목으로 추가" onclick="openPromoteFromIssue('${it.id}','${g}')">➕ 점검·매뉴얼 항목으로</button>`:'';
  const _rArg=round?`,'${round}'`:'';
  /* 요일·주기 일정 배지 (편집 시 '월수금'·'둘째주'·'격주' 입력하면 헬스장처럼 배지로 표시). GM 2026-06-12 */
  const _dayChips=(typeof scheduleBadges==='function')?scheduleBadges(it,itemName,itemDetail):'';
  return `<div class="${cls}">
    <div class="item-row"><input type="checkbox" id="cb_${pfx}${it.id}" ${ck} onchange="onCk('${it.id}','${shift}','${g}'${_rArg})"><label for="cb_${pfx}${it.id}">${itemName}${_dayChips}${editedTag}</label>
      <div class="item-btns"><button class="tiny-btn issue" onclick="togX('${pfx}iss_${it.id}')">이슈</button><button class="tiny-btn tip" onclick="togX('${pfx}tip_${it.id}')">노하우</button>${refBtn}</div>
    </div>
    <div class="item-detail">${det}</div>${tempHtml}
    <input class="extra-input issue-field${iss?' show':''}" id="${pfx}iss_${it.id}" placeholder="이슈 내용..." value="${esc(iss)}" onchange="onExtra('iss_${it.id}','${pfx}iss_${it.id}')">
    ${promoteBtn?`<div class="promote-bar" style="margin:4px 0 2px;">${promoteBtn}</div>`:''}
    <input class="extra-input tip-field${tip?' show':''}" id="${pfx}tip_${it.id}" placeholder="노하우/개선 의견..." value="${esc(tip)}" onchange="onExtra('tip_${it.id}','${pfx}tip_${it.id}')">
  </div>`;
}

function escapeAttr(s){return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

function renderDayFocusSection(dow,items,shift,gender,round){
  const dayNames=['일','월','화','수','목','금','토'];
  const _ck = it => round ? isChecked(it.id,round) : !!STATE[it.id];
  let gd=0;items.forEach(it=>{if(_ck(it))gd++});
  const ok=gd===items.length,badge=ok?'<span class="cat-badge done">완료</span>':`<span class="cat-badge pending">${gd}/${items.length}</span>`;
  let html=`<div class="day-focus-section">
    <div class="day-focus-title">${dayNames[dow]}요일 집중 청소</div>
    <div class="category"><div class="cat-header" onclick="tog(this)"><span class="cat-title">요일별 집중 청소 항목</span>${badge}</div><div class="cat-body${ok?'':' open'}">`;
  items.forEach(it=>{html+=renderItem(it,shift,gender,round)});
  html+='</div></div></div>';
  return html;
}

function updateSubmitButtonsG(sched,amStats,pmStats,gender){
  const sfx=gender==='f'?'F':'M';
  const btnAm=document.getElementById('submitAm'+sfx),btnPm=document.getElementById('submitPm'+sfx);
  const sub=getSubmitterForGender(gender);
  /* 점검자 미선택 시: 드롭다운 강조 + 버튼에 사유 안내(회색 이유가 '점검자 미선택'임을 명시) */
  const selEl=document.getElementById('submitter'+sfx);
  if(selEl) selEl.style.boxShadow = sub ? '' : '0 0 0 2px var(--accent)';
  if(STATE._submitted_am){
    if(amStats.done<amStats.total){
      btnAm.textContent=`➕ 오전조 추가 제출 (남은 ${amStats.total-amStats.done}건)`;btnAm.disabled=!sub;btnAm.className='submit-btn primary';
    }else{
      btnAm.textContent='오전조 제출 완료';btnAm.disabled=true;btnAm.className='submit-btn submitted';
    }
  }else if(!sub){
    btnAm.textContent='↑ 점검자를 먼저 선택';btnAm.disabled=true;btnAm.className='submit-btn primary';
  }else{
    btnAm.textContent=amStats.done===amStats.total&&amStats.total>0?'오전조 제출':`오전조 제출 (${amStats.done}/${amStats.total})`;
    btnAm.disabled=amStats.done===0;btnAm.className='submit-btn primary';
  }
  if(STATE._submitted_pm){
    if(pmStats.done<pmStats.total){
      btnPm.textContent=`➕ 오후조 추가 제출 (남은 ${pmStats.total-pmStats.done}건)`;btnPm.disabled=!sub;btnPm.className='submit-btn primary';
    }else{
      btnPm.textContent='오후조 제출 완료';btnPm.disabled=true;btnPm.className='submit-btn submitted';
    }
  }else if(!sub){
    btnPm.textContent='↑ 점검자를 먼저 선택';btnPm.disabled=true;btnPm.className='submit-btn primary';
  }else{
    btnPm.textContent=pmStats.done===pmStats.total&&pmStats.total>0?'오후조 제출':`오후조 제출 (${pmStats.done}/${pmStats.total})`;
    btnPm.disabled=pmStats.done===0;btnPm.className='submit-btn primary';
  }
}

function updateNightSubmitButtonG(sched,nightStats,d,gender){
  const sfx=gender==='f'?'F':'M';
  const btnNight=document.getElementById('submitNight'+sfx);
  const sub=getSubmitterForGender(gender);
  if(STATE._submitted_night){
    if(nightStats.done<nightStats.total){
      btnNight.textContent=`➕ 야간조 추가 제출 (남은 ${nightStats.total-nightStats.done}건)`;btnNight.disabled=!sub;btnNight.className='submit-btn night-btn';
    }else{
      btnNight.textContent='야간조 제출 완료';btnNight.disabled=true;btnNight.className='submit-btn submitted';
    }
  }else if(!sub){
    btnNight.textContent='↑ 점검자를 먼저 선택';btnNight.disabled=true;btnNight.className='submit-btn night-btn';
  }else{
    btnNight.textContent=nightStats.done===nightStats.total&&nightStats.total>0?'야간조 제출':`야간조 제출 (${nightStats.done}/${nightStats.total})`;
    btnNight.disabled=nightStats.done===0;btnNight.className='submit-btn night-btn';
  }
}

let _ckDrawTimer=null;
function onCk(id,shift,gender,round){
  const d=getDateG(gender);
  const pfx=gender+'_';
  const cb=document.getElementById('cb_'+pfx+id);
  const val=cb?cb.checked:false;
  /* 회차별 체크 독립: round 있으면 라운드 키에만 기록(다른 회차 미영향).
     round 없으면(야간모드 등) 기존 레거시 키 유지(비회귀). */
  if(round){ if(val)STATE[chkKey(round,id,gender)]=true; else delete STATE[chkKey(round,id,gender)]; }
  else { STATE[id]=val; }
  saveState(d,gender);
  /* 빠른 연속체크 레이스 방지(GM 2026-06-12): 클릭한 항목 행만 즉시 가볍게 반영하고,
     무거운 전체 redraw + 완료판정은 연속체크가 멈춘 뒤 1회만(디바운스). */
  if(cb){ const _row=cb.closest('.item'); if(_row)_row.classList.toggle('checked',val); }
  clearTimeout(_ckDrawTimer);
  _ckDrawTimer=setTimeout(function(){ _ckDrawTimer=null; _onCkAfter(d,gender); },250);
}
function _onCkAfter(d,gender){
  drawUI(d,gender);
  const nightMode=isNightShiftWorkerG(gender);
  const sched=nightMode?getNightSched(d):getSched(d);
  if(!sched)return;

  if(nightMode){
    // 야간모드: 기존 shift 단위 자동제출 유지
    const stats=getShiftStatsG(sched,'night',d,gender);
    if(stats.pct===100&&!STATE['_submitted_night']){
      const sub=getSubmitterForGender(gender);
      if(!sub){alert('점검자 이름을 먼저 입력하세요.');return}
      if(confirm(`야간조 항목을 모두 완료했습니다.\n${sub}님 이름으로 제출할까요?`)){
        submitShift('night',gender);
      }
    }
    return;
  }

  // 정상(주간)모드: 현재 라운드(조) 100% 완료 시 그 조 제출 제안
  const curRound=getRoundG(gender);
  const rdef=roundDef(curRound)||ROUNDS[0];
  const dow=getDayOfWeek(d);
  let total=0,done=0;
  /* 멤버십(itemRounds) 기준 + 회차별 체크(isChecked) — 렌더 진행도와 정합 */
  sched.forEach(slot=>slot.groups.forEach(g=>g.items.forEach(it=>{
    if(!shouldShowItemForGender(it,gender))return;
    const ctx={...it,slot:slot.slot,shift:slot.shift};
    if(itemRounds(ctx).indexOf(curRound)<0)return;
    total++; if(isChecked(it.id,curRound))done++;
  })));
  if(curRound==='close1'&&DAY_FOCUS[dow])DAY_FOCUS[dow].forEach(it=>{ if(shouldShowItemForGender(it,gender)){total++; if(isChecked(it.id,curRound))done++;} });
  /* 2026-06-13 인시던트: 라운드 100% 자동제출 confirm 오발화(항목 적은 라운드가 즉시 100% 도달 →
     거짓제출·연쇄리셋). 자동제출 폐기 — 제출은 명시 '조 제출' 버튼으로만(체크 자동저장은 유지). */
  if(false && total>0&&done===total&&!isRoundSubmitted(d,gender,curRound)){
    const sub=getSubmitterForGender(gender);
    if(!sub){alert('점검자 이름을 먼저 입력하세요.');return}
    if(confirm(`${rdef.name} ${rdef.time} 항목을 모두 완료했습니다.\n${sub}님 이름으로 제출할까요?`)){
      submitRound(curRound,gender);
    }
  }
}

function onExtra(stateKey,elemId){
  const d=getDateG(activeGenderTab);
  STATE[stateKey]=document.getElementById(elemId).value;
  saveState(d);
}
function togX(id){const e=document.getElementById(id);e.classList.toggle('show');if(e.classList.contains('show'))e.focus()}
function tog(h){h.nextElementSibling.classList.toggle('open')}
/* v2.50 — 매뉴얼 탭 현재 점검 항목 자동 동기화 */
/* v2.52 — 점검 탭 override(시트 편집분) 매뉴얼 뷰에도 반영 (방안 A) */
/* 편집 모드(GM 2026-06-12): 평소엔 깔끔한 참조 뷰, 켜면 추가·편집·삭제·▲▼ 순서변경 노출. */
let _manualEdit=false;
window.toggleManualEdit=function(){ _manualEdit=!_manualEdit; renderManualItems(); };
function renderManualItems(){
  const el=document.getElementById('manual-items-sync');
  if(!el)return;
  // WEEKDAY를 기준으로 항목 수집 (평일 = 기본 표준 스케줄)
  const sched=typeof WEEKDAY!=='undefined'?WEEKDAY:[];
  // 점검 탭 override 맵 — 시트 편집분(shadow 항목)을 단일출처로 적용
  const ovMap=typeof getItemOverrides==='function'?getItemOverrides():{};
  // 카테고리별로 항목 모으기 (중복 id 제거)
  const catMap={};
  let catOrder=[];
  const seen=new Set();
  const hidden=(typeof getHiddenIds==='function')?getHiddenIds():new Set();
  const hiddenItems=[];
  function pushItem(cat,it){
    if(!catMap[cat]){catMap[cat]=[];catOrder.push(cat);}
    if(!seen.has(it.id)){seen.add(it.id);catMap[cat].push(it);}
  }
  sched.forEach(slot=>{
    slot.groups.forEach(grp=>{
      grp.items.forEach(it=>{
        // 기본 항목: override가 있으면 name·detail·성별 합성
        const ov=ovMap[it.id]||{};
        if(hidden.has(it.id)){ if(!seen.has(it.id)){seen.add(it.id);hiddenItems.push({id:it.id,name:ov.name||it.name,cat:grp.title});} return; }
        pushItem(grp.title,{
          id:it.id,
          name:ov.name||it.name,
          detail:ov.detail||it.detail,
          gender:ov.gender||it.gender,
          sched:ov.sched||'',
          _edited:!!(ov.name||ov.detail||ov.gender||ov.rounds||ov.sched)
        });
      });
    });
  });
  // GM이 추가한 항목(CUSTOM_ITEMS)도 함께 표시
  if(typeof CUSTOM_ITEMS!=='undefined'){
    CUSTOM_ITEMS.forEach(ci=>{
      if(hidden.has(ci.id))return;   // 숨긴 항목 제외
      pushItem(ci.category||'추가 점검',{id:ci.id,name:ci.name,detail:ci.detail,gender:ci.gender,sched:ci.sched||'',_custom:true});
    });
  }
  /* 빈 구역(사용자 추가) 합류 + 숨긴 구역 분리 + 순서 적용 */
  (typeof getAddedGroups==='function'?getAddedGroups():[]).forEach(g=>{ if(!catMap[g]){catMap[g]=[];catOrder.push(g);} });
  const _hiddenG=(typeof getHiddenGroups==='function')?getHiddenGroups():new Set();
  const _hiddenGroupList=catOrder.filter(c=>_hiddenG.has(c));
  catOrder=catOrder.filter(c=>!_hiddenG.has(c));
  catOrder.sort((a,b)=>groupRank(a)-groupRank(b));
  window._groupSorted=catOrder.slice();
  /* 그룹 내 정렬 적용(orderMap 우선, 없으면 등장순) + 그룹별 id목록 캡처(↑/↓ 이동용) */
  const _orderMap=(typeof getItemOrder==='function')?getItemOrder():{};
  window._catItemIds={};
  catOrder.forEach(cat=>{
    const arr=catMap[cat];
    arr.forEach((it,i)=>{ it._ord=(_orderMap[it.id]!=null)?_orderMap[it.id]:i; });
    arr.sort((a,b)=>a._ord-b._ord);
    window._catItemIds[cat]=arr.map(it=>it.id);
  });
  /* 셋업 버튼 공통 스타일(인라인) */
  const _btn='font-size:11px;font-weight:700;border-radius:6px;padding:3px 8px;cursor:pointer;font-family:inherit;border:1px solid;white-space:nowrap;';
  const _customCount=(typeof CUSTOM_ITEMS!=='undefined'?CUSTOM_ITEMS:[]).filter(it=>isAddedItem(it.id)).length;
  const EM=_manualEdit;   // 편집 모드 여부
  let html='';
  /* 셋업 안내 + 편집모드 토글 + 추가항목 일괄정리(GM 2026-06-12): 매뉴얼=항목 단일출처(시트 동기화). 점검은 읽기전용. */
  const _emBtn=`<button onclick="toggleManualEdit()" style="${_btn}${EM?'color:#fff;background:var(--accent);border-color:var(--accent);':'color:var(--accent);background:var(--bg);border-color:var(--accent);'}">${EM?'✓ 편집 모드 (끄기)':'✎ 편집 모드'}</button>`;
  const _addGroupBtn=EM?`<button onclick="addManualGroup()" style="${_btn}color:var(--accent);background:var(--bg);border-color:var(--accent);">＋ 구역 추가</button>`:'';
  html+=`<div style="background:var(--accent-bg);border:1px solid var(--accent);border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:12px;color:var(--text);line-height:1.6;">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;"><span><b style="color:var(--accent);">매뉴얼 = 항목 단일출처</b> · 편집 모드를 켜면 구역(A·B…) <b>추가·이름변경·삭제·순서(▲▼)</b>와 항목 추가·편집·삭제가 나타납니다.</span><span style="display:inline-flex;gap:6px;">${_addGroupBtn}${_emBtn}</span></div>
  </div>`;
  catOrder.forEach((cat,gi)=>{
    const items=catMap[cat];
    html+=`<div style="background:var(--paper);border:1px solid var(--border);border-radius:10px;margin-bottom:10px;overflow:hidden;">`;
    /* 그룹 헤더: (편집모드) 그룹 ▲▼ 이동 + 구역명 + ＋항목추가 */
    const _gUp=gi>0?`<button onclick="moveManualGroup('${escapeAttr(cat)}',-1)" style="${_btn}color:var(--text);background:var(--bg);border-color:var(--border);" title="구역 위로">▲</button>`:`<button disabled style="${_btn}color:var(--text);background:var(--bg);border-color:var(--border);opacity:.25;cursor:default;">▲</button>`;
    const _gDn=gi<catOrder.length-1?`<button onclick="moveManualGroup('${escapeAttr(cat)}',1)" style="${_btn}color:var(--text);background:var(--bg);border-color:var(--border);" title="구역 아래로">▼</button>`:`<button disabled style="${_btn}color:var(--text);background:var(--bg);border-color:var(--border);opacity:.25;cursor:default;">▼</button>`;
    const _gMove=EM?`<span style="display:inline-flex;gap:3px;margin-right:6px;">${_gUp}${_gDn}</span>`:'';
    const _gActions=EM?`<span style="display:inline-flex;gap:4px;flex-wrap:wrap;">`
      +`<button onclick="renameManualGroup('${escapeAttr(cat)}')" style="${_btn}color:#5b9fd5;background:rgba(91,159,213,0.12);border-color:rgba(91,159,213,0.35);">이름변경</button>`
      +`<button onclick="deleteManualGroup('${escapeAttr(cat)}')" style="${_btn}color:#c0392b;background:rgba(192,57,67,0.1);border-color:rgba(192,57,67,0.4);">구역삭제</button>`
      +`<button onclick="manualAddItem('${escapeAttr(cat)}')" style="${_btn}color:var(--accent);background:var(--bg);border-color:var(--accent);">＋ 항목</button>`
      +`</span>`:'';
    html+=`<div style="padding:10px 16px;font-size:13px;font-weight:700;color:var(--accent);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;"><span style="display:flex;align-items:center;">${_gMove}${groupDisplay(cat)}</span>${_gActions}</div>`;
    items.forEach((it,idx)=>{
      const detHtml=it.detail?it.detail.replace(/\n/g,'<br>'):'';
      const hasDet=!!detHtml;
      const genderLabel=it.gender==='m'?' <span style="font-size:10px;color:var(--blue);background:var(--blue-bg);padding:1px 6px;border-radius:6px;">남</span>':it.gender==='f'?' <span style="font-size:10px;color:var(--orange);background:var(--orange-bg);padding:1px 6px;border-radius:6px;">여</span>':'';
      const customLabel=(it._custom&&isCustomFresh(it.id))?' <span style="font-size:10px;color:var(--accent);background:var(--accent-bg);padding:1px 6px;border-radius:6px;">추가</span>':'';
      const editedLabel=(it._edited&&isEditFresh(it.id))?' <span style="font-size:10px;color:#e6c84e;background:rgba(230,200,78,0.12);padding:1px 6px;border-radius:6px;">수정됨</span>':'';
      /* 매뉴얼 = 셋업/참조 전용(GM 2026-06-12): 체크박스·완료표시 없음. 체크는 점검 탭에서만. */
      const nameStyle='font-size:13px;font-weight:600;';
      const arrow=hasDet?`<span class="m-arrow" style="font-size:11px;color:var(--dim);transition:transform .2s;">&#9660;</span>`:'';
      const nameCursor=hasDet?'cursor:pointer;':'';
      /* 셋업 버튼: 편집(전체) + 삭제(전체 — 추가항목=완전삭제 / 기본항목=숨김) */
      let setup=`<button onclick="event.stopPropagation();editItem('${it.id}')" style="${_btn}color:#5b9fd5;background:rgba(91,159,213,0.12);border-color:rgba(91,159,213,0.35);">편집</button>`;
      setup+=`<button onclick="event.stopPropagation();manualDeleteItem('${it.id}')" style="${_btn}color:#c0392b;background:rgba(192,57,67,0.1);border-color:rgba(192,57,67,0.4);">삭제</button>`;
      if(!it._custom&&it._edited)setup+=`<button onclick="event.stopPropagation();resetItem('${it.id}')" style="${_btn}color:#8c8b83;background:rgba(140,139,131,0.12);border-color:rgba(140,139,131,0.3);">초기화</button>`;
      /* 그룹 내 순서 이동(위/아래) — 편집 모드에서만, 경계에서 비활성 */
      const _mvBtn='font-size:12px;font-weight:700;border-radius:6px;padding:2px 7px;cursor:pointer;font-family:inherit;border:1px solid var(--border);background:var(--bg);color:var(--text);line-height:1.2;';
      const _up=idx>0?`<button onclick="event.stopPropagation();moveManualItem('${it.id}',-1)" style="${_mvBtn}" title="위로">▲</button>`:`<button disabled style="${_mvBtn}opacity:.25;cursor:default;">▲</button>`;
      const _dn=idx<items.length-1?`<button onclick="event.stopPropagation();moveManualItem('${it.id}',1)" style="${_mvBtn}" title="아래로">▼</button>`:`<button disabled style="${_mvBtn}opacity:.25;cursor:default;">▼</button>`;
      html+=`<div style="padding:10px 16px;border-bottom:1px solid rgba(61,56,53,0.35);">`;
      html+=`<div style="${nameCursor}min-width:0;" ${hasDet?'onclick="togManualItem(this)"':''}><div style="${nameStyle}display:flex;align-items:center;gap:6px;justify-content:space-between;"><span>${it.name}${genderLabel}${customLabel}${editedLabel}${(typeof scheduleBadges==='function')?scheduleBadges(it,it.name,it.detail):''}</span>${arrow}</div>`;
      if(hasDet)html+=`<div class="manual-item-detail" style="font-size:12px;color:var(--dim);margin-top:5px;line-height:1.5;">${detHtml}</div>`;
      html+=`</div>`;
      /* 편집 모드: 항목명 아래 별도 줄에 액션바(▲▼ · 편집 · 삭제) — overflow 잘림 방지, 항상 보임 */
      if(EM)html+=`<div style="display:flex;align-items:center;gap:6px;margin-top:8px;flex-wrap:wrap;">${_up}${_dn}<span style="display:inline-block;width:6px;"></span>${setup}</div>`;
      html+=`</div>`;
    });
    html+=`</div>`;
  });
  /* 숨긴 기본 항목 — 복구 가능(편집 모드에서만) */
  if(EM&&hiddenItems.length){
    html+=`<div style="background:var(--paper);border:1px dashed var(--border);border-radius:10px;margin-top:6px;overflow:hidden;opacity:.85;">`;
    html+=`<div style="padding:10px 16px;font-size:13px;font-weight:700;color:var(--dim);border-bottom:1px solid var(--border);">숨긴 항목 (${hiddenItems.length}) — 점검에서 제외됨</div>`;
    hiddenItems.forEach(hi=>{
      html+=`<div style="padding:8px 16px;border-bottom:1px solid rgba(61,56,53,0.25);display:flex;align-items:center;justify-content:space-between;gap:10px;"><span style="font-size:13px;color:var(--dim);text-decoration:line-through;">${hi.name} <span style="font-size:10px;">(${hi.cat})</span></span><button onclick="manualUnhideItem('${hi.id}')" style="${_btn}color:var(--accent);background:var(--accent-bg);border-color:var(--accent);">복구</button></div>`;
    });
    html+=`</div>`;
  }
  /* 숨긴 구역 — 복구 가능(편집 모드에서만) */
  if(EM&&_hiddenGroupList.length){
    html+=`<div style="background:var(--paper);border:1px dashed var(--border);border-radius:10px;margin-top:6px;overflow:hidden;opacity:.85;">`;
    html+=`<div style="padding:10px 16px;font-size:13px;font-weight:700;color:var(--dim);border-bottom:1px solid var(--border);">숨긴 구역 (${_hiddenGroupList.length}) — 점검에서 제외됨</div>`;
    _hiddenGroupList.forEach(g=>{
      html+=`<div style="padding:8px 16px;border-bottom:1px solid rgba(61,56,53,0.25);display:flex;align-items:center;justify-content:space-between;gap:10px;"><span style="font-size:13px;color:var(--dim);text-decoration:line-through;">${groupDisplay(g)}</span><button onclick="restoreManualGroup('${escapeAttr(g)}')" style="${_btn}color:var(--accent);background:var(--accent-bg);border-color:var(--accent);">복구</button></div>`;
    });
    html+=`</div>`;
  }
  el.innerHTML=html||'<div style="color:var(--dim);font-size:13px;">항목 없음</div>';
}

/* 매뉴얼 탭 개별 항목 점검완료 체크 → 기존 체크 저장 시스템(STATE+saveState+pushToServer) 재사용 */
function onManualCk(id){
  const d=getDateG(activeGenderTab)||kstToday();   // KST 오늘(UTC 어긋남 차단)
  STATE[id]=document.getElementById('mcb_'+id).checked;
  saveState(d);
  renderManualItems();
}

/* 매뉴얼 탭 항목 상세 토글 (이름 영역 클릭, 체크박스는 제외) */
function togManualItem(nameEl){
  const det=nameEl.querySelector('.manual-item-detail');
  if(!det)return;
  const open=det.style.display!=='none';
  det.style.display=open?'none':'block';
  const arrow=nameEl.querySelector('.m-arrow');
  if(arrow)arrow.style.transform=open?'rotate(0deg)':'rotate(90deg)';
}

function togManual(h){
  const body=h.nextElementSibling;
  const arrow=h.querySelector('.arrow');
  body.classList.toggle('open');
  arrow.classList.toggle('open');
}

/* ── 그룹별 제출 (2026-06-05 GM: 항목 묶음 단위 제출, 조 마감은 별도 유지) ── */
function groupKey(g){ return 'g_' + ((g.items && g.items[0]) ? g.items[0].id : ''); }
function isGroupSubmitted(g){ return !!STATE['_gsub_' + groupKey(g)]; }
async function submitGroup(gkey, gender){
  const sub = getSubmitterForGender(gender);
  if(!sub){ alert('점검자를 선택해주세요.'); return; }
  const d = getDateG(gender);
  STATE['_gsub_' + gkey] = true;
  STATE['_gsubAt_' + gkey] = new Date().toLocaleString('sv-SE').replace('T',' ');   // KST(타 제출경로와 통일, UTC 9h어긋남 차단)
  STATE['_gsubBy_' + gkey] = sub;
  saveLocal(d, STATE, gender);
  if(ONLINE) await pushToServer(d);   // 텔레그램 알림 없음(조 마감 때만) — GM
  drawUI(d, gender);
}
function collectGroupSubmits(){
  const out = {};
  Object.keys(STATE).forEach(k=>{
    if(k.indexOf('_gsub_') === 0){
      const key = k.slice(6);
      out[key] = { by: STATE['_gsubBy_' + key] || '', at: STATE['_gsubAt_' + key] || '' };
    }
  });
  return out;
}
// 그룹 제출 버튼/배지 HTML — '이 항목 제출' 기능 제거(GM 2026-06-12): 조 단위 제출만 사용(렌더 경량화).
function groupSubmitBarHtml(g, gender, round){
  return '';
  // eslint-disable-next-line no-unreachable
  const gk = groupKey(g);
  const visItems = (g.items||[]).filter(it=>shouldShowItemForGender(it,gender));
  /* 회차별 체크 독립: round 있으면 그 회차 체크 기준 미흡건 계산 */
  const _ck = it => round ? isChecked(it.id,round) : !!STATE[it.id];
  const remain = visItems.length - visItems.filter(_ck).length;
  if(STATE['_gsub_' + gk]){
    const by = STATE['_gsubBy_' + gk] ? ' (' + STATE['_gsubBy_' + gk] + ')' : '';
    const at = STATE['_gsubAt_' + gk] ? new Date(STATE['_gsubAt_' + gk]).toLocaleString('ko-KR') : '';
    // 제출됐지만 미완료(미흡) 항목이 남으면 '완료'로 막지 않고 추가 제출 허용 (2026-06-05 GM)
    if(remain > 0){
      return '<div class="group-submit-bar"><span class="group-submitted" style="color:var(--accent)">⚠ 일부 제출' + by + ' · 미흡 ' + remain + '건</span>' +
        '<button class="group-submit-btn" onclick="submitGroup(\'' + gk + '\',\'' + gender + '\')">➕ 추가 제출 (남은 ' + remain + '건)</button></div>';
    }
    return '<div class="group-submit-bar"><span class="group-submitted">✅ 제출됨' + by + ' ' + at + '</span></div>';
  }
  return '<div class="group-submit-bar"><button class="group-submit-btn" onclick="submitGroup(\'' + gk + '\',\'' + gender + '\')">이 항목 제출</button></div>';
}

async function submitShift(shift,gender){
  const sub=getSubmitterForGender(gender);
  if(!sub){alert('점검자를 선택해주세요.');return}
  const d=getDateG(gender);
  const labels={am:'오전조',pm:'오후조',night:'야간조'};
  const genderLabel=gender==='f'?'여':'남';
  const label=labels[shift]||shift;
  /* 거짓제출 가드(시우 2026-06-13): 가시항목 체크 0이면 confirm 경고 — done>0이면 무조건 통과(정상흐름 무파괴). */
  try{
    const _gsched=(shift==='night')?getNightSched(d):getSched(d);
    if(_gsched){
      const _st=getShiftStatsG(_gsched,shift,d,gender);
      if(_st.done===0 && !confirm(`${label}(${genderLabel}) 점검 항목이 하나도 체크되지 않았습니다.\n그래도 제출하시겠습니까?`))return;
    }
  }catch(e){}
  const _isAdd=!!STATE['_submitted_'+shift];
  STATE['_submitted_'+shift]=true;
  STATE['_submittedAt_'+shift]=new Date().toLocaleString('sv-SE').replace('T',' ');
  STATE['_submitter_'+shift]=sub;
  saveLocal(d,STATE,gender);
  if(ONLINE)await pushToServer(d,gender,true);   // ★명시적 제출 — 제출메타 전송(폐루프 절단: 자동저장은 미전송)
  await sendTelegramNotify(d,shift,sub,gender);
  /* F3(2026-06-11 시우): 제출 스냅샷 적립 + 체크박스 리셋 — 추가제출(_isAdd)이 아닌 최초 제출에만.
     스냅샷=append-only 누적 기록(집계/텔레그램 무손상). 리셋=다음 점검 준비(체크/온도/반영 STATE만 비움,
     제출완료 플래그·이슈/노하우는 보존 → 보드 '제출완료' 표시 유지). 오프라인이면 리셋 보류(중복 푸시 방지). */
  if(!_isAdd && ONLINE){
    await appendSubmitSnapshot(d,shift,sub,gender);
    resetShiftChecks(d,shift,gender);
    await pushToServer(d);   // 리셋된 체크 상태를 서버 반영(다음 점검 빈 체크)
  }
  alert(`${d} ${label} 점검(${genderLabel})이 ${sub}님 이름으로 ${_isAdd?'추가 ':''}제출되었습니다.`);
  drawUI(d,gender);
}

/* ── 라운드(조) 단위 제출·잠금 (시우·GM 2026-06-11 · 1단계) ──
   1) 그 조 잠금(submitted_<date>_<gender>_<round>)+제출자·시각·타이머 적립
   2) 스냅샷 1행 적립(shift 칸=라운드 라벨 '오전조[1]' 등 / 점검자=자유입력 / 타이머=그 라운드)
   3) ⚠ 비회귀: 그 라운드가 속한 기존 shift(am/pm)의 모든 라운드가 제출되면
      _submitted_<shift>를 세팅 + 기존 submitShift 백엔드 경로(스냅샷·텔레그램·집계)를 1회 호출
      → getShiftStatsG·_submitted_am/pm·admin 대시보드·텔레그램이 계속 동작(0으로 안 떨어짐). */
async function submitRound(round,gender){
  const sub=getSubmitterForGender(gender);
  if(!sub){alert('점검자 이름을 먼저 입력하세요.');return}
  const d=getDateG(gender);
  const rdef=roundDef(round); if(!rdef){alert('알 수 없는 조');return}
  const genderLabel=gender==='f'?'여':'남';
  /* 거짓제출 가드(시우 2026-06-13): 그 라운드 가시항목 체크 0이면 confirm 경고 — done>0이면 무조건 통과.
     집계는 appendRoundSnapshot의 itemRounds+isChecked 로직 재사용. */
  try{
    const _rsched=getSched(d);
    if(_rsched){
      const _dow=getDayOfWeek(d); let _rdone=0;
      _rsched.forEach(slot=>slot.groups.forEach(g=>g.items.forEach(it=>{
        if(!shouldShowItemForGender(it,gender))return;
        const ctx={...it,slot:slot.slot,shift:slot.shift};
        if(itemRounds(ctx).indexOf(round)<0)return;
        if(isChecked(it.id,round,gender))_rdone++;
      })));
      if(round==='close1'&&DAY_FOCUS[_dow])DAY_FOCUS[_dow].forEach(it=>{ if(shouldShowItemForGender(it,gender)&&isChecked(it.id,round,gender))_rdone++; });
      if(_rdone===0 && !confirm(`${rdef.name} 점검 항목이 하나도 체크되지 않았습니다.\n그래도 제출하시겠습니까?`))return;
    }
  }catch(e){}
  const _isAdd=isRoundSubmitted(d,gender,round);
  /* 1) 라운드 잠금 + 메타 (STATE + localStorage 미러 영속) */
  const nowIso=new Date().toLocaleString('sv-SE').replace('T',' ');   // KST(타 제출경로와 통일, UTC 9h어긋남 차단)
  STATE[roundSubKey(d,gender,round)]=true;
  STATE['submittedAt_'+d+'_'+gender+'_'+round]=nowIso;
  STATE['submitter_'+d+'_'+gender+'_'+round]=sub;
  STATE['submitter_'+gender]=sub;                 // 자유입력 점검자 유지(R4)
  localStorage.setItem(roundSubLSKey(d,gender,round),'1');
  localStorage.setItem('wcheck_rsubBy_'+d+'_'+gender+'_'+round,sub);
  localStorage.setItem('wcheck_rsubAt_'+d+'_'+gender+'_'+round,nowIso);
  saveLocal(d,STATE,gender);
  if(ONLINE)await pushToServer(d,gender,true);   // ★명시적 제출 — 제출메타 전송(폐루프 절단)
  /* 2) 라운드 스냅샷(최초 제출만) */
  if(!_isAdd && ONLINE){
    await appendRoundSnapshot(d,round,sub,gender);
  }
  /* 3) 비회귀: 같은 shift의 모든 라운드가 제출되면 기존 shift 제출 경로 1회 발화 */
  const baseShift=rdef.baseShift;
  const sibRounds=roundsOfShift(baseShift);
  /* 빈 조(가시 항목 0)는 제출 불필요로 간주 → 항목 있는 조가 모두 제출되면 shift 완료 */
  const allDone=sibRounds.every(rk=>!roundHasItems(d,gender,rk)||isRoundSubmitted(d,gender,rk));
  if(allDone && !STATE['_submitted_'+baseShift]){
    STATE['_submitted_'+baseShift]=true;
    STATE['_submittedAt_'+baseShift]=new Date().toLocaleString('sv-SE').replace('T',' ');
    STATE['_submitter_'+baseShift]=sub;
    saveLocal(d,STATE,gender);
    if(ONLINE)await pushToServer(d,gender,true);   // ★shift 완료 메타 전송(폐루프 절단)
    await sendTelegramNotify(d,baseShift,sub,gender);     // 기존 조 마감 텔레그램(집계 정합)
    if(ONLINE)await appendSubmitSnapshot(d,baseShift,sub,gender);  // 기존 shift 스냅샷(집계 무손상)
  }
  alert(`${d} ${rdef.name} ${rdef.time} 점검(${genderLabel})이 ${sub}님 이름으로 ${_isAdd?'추가 ':''}제출되었습니다.`);
  drawUI(d,gender);
}

/* 라운드 스냅샷 1행 적립 — shift 칸에 라운드 라벨 기록(GAS 무변경: '교대' 컬럼에 들어감). */
async function appendRoundSnapshot(date,round,submitter,gender){
  if(!ONLINE)return;
  const sched=getSched(date);
  if(!sched)return;
  const rdef=roundDef(round); if(!rdef)return;
  /* 그 조의 가시 항목·이슈 수집 */
  const dow=getDayOfWeek(date);
  let total=0,done=0,issues=[];
  /* 멤버십(itemRounds) 기준 + 회차별 체크(isChecked) — 라운드 진행도·스냅샷 정합 */
  sched.forEach(slot=>slot.groups.forEach(g=>g.items.forEach(it=>{
    if(!shouldShowItemForGender(it,gender))return;
    const ctx={...it,slot:slot.slot,shift:slot.shift};
    if(itemRounds(ctx).indexOf(round)<0)return;
    total++; if(isChecked(it.id,round,gender))done++;
    if(STATE['iss_'+it.id])issues.push(STATE['iss_'+it.id]);
  })));
  if(round==='close1'&&DAY_FOCUS[dow])DAY_FOCUS[dow].forEach(it=>{ if(shouldShowItemForGender(it,gender)){total++; if(isChecked(it.id,round,gender))done++; if(STATE['iss_'+it.id])issues.push(STATE['iss_'+it.id]);} });
  const pct=total?Math.round(done/total*100):0;
  const zone=gender==='f'?'f':gender==='m'?'m':'all';
  const t=timerKeys(date,gender,round);
  const tStart=STATE[t.sk], tEnd=STATE[t.ek];
  const startedAt=tStart?new Date(tStart).toLocaleString('sv-SE').replace('T',' '):'';
  const finishedAt=tEnd?new Date(tEnd).toLocaleString('sv-SE').replace('T',' '):'';
  const dur=_timerDuration(tStart,tEnd);
  try{
    await fetch(API_URL,{method:'POST',redirect:'follow',
      headers:{'Content-Type':'text/plain'},
      body:JSON.stringify({action:'snapshot_append',dept:DEPT,date,zone,
        shift:rdef.name+' '+rdef.time,   // 라운드 라벨(예: '오전조[1] 10시') → 시트 '교대' 칸
        submitter,
        submittedAt:new Date().toLocaleString('sv-SE').replace('T',' '),
        total,done,pct,
        issuesCount:issues.length,issues:issues.join(' / '),
        startedAt,finishedAt,durationMin:(dur!=null?dur:'')})
    });
  }catch(e){}
}

/* 제출 스냅샷을 점검일지 시트에 1행 적립 (집계와 독립) */
async function appendSubmitSnapshot(date,shift,submitter,gender){
  if(!ONLINE)return;
  const nightMode=(shift==='night');
  const sched=nightMode?getNightSched(date):getSched(date);
  if(!sched)return;
  const stats=getShiftStatsG(sched,shift,date,gender);
  const ids=collectShiftItemIds(date,shift,gender);
  let issues=[];
  ids.forEach(id=>{ if(STATE['iss_'+id])issues.push(STATE['iss_'+id]); });
  const zone=gender==='f'?'f':gender==='m'?'m':'all';
  // 점검 타이머 적립 (해당 date+gender STATE에서 읽음, 없으면 빈값)
  const tStart=STATE['timerStart_'+date+'_'+gender], tEnd=STATE['timerEnd_'+date+'_'+gender];
  const startedAt=tStart?new Date(tStart).toLocaleString('sv-SE').replace('T',' '):'';
  const finishedAt=tEnd?new Date(tEnd).toLocaleString('sv-SE').replace('T',' '):'';
  const dur=_timerDuration(tStart,tEnd);
  try{
    await fetch(API_URL,{method:'POST',redirect:'follow',
      headers:{'Content-Type':'text/plain'},
      body:JSON.stringify({action:'snapshot_append',dept:DEPT,date,zone,shift,submitter,
        submittedAt:new Date().toLocaleString('sv-SE').replace('T',' '),
        total:stats.total,done:stats.done,pct:stats.pct,
        issuesCount:issues.length,issues:issues.join(' / '),
        startedAt,finishedAt,durationMin:(dur!=null?dur:'')})
    });
  }catch(e){}
}

/* 제출된 교대조에 속한 항목 id 수집 (체크 리셋·이슈 집계용) */
function collectShiftItemIds(date,shift,gender){
  const nightMode=(shift==='night');
  const sched=nightMode?getNightSched(date):getSched(date);
  const ids=[];
  if(sched){
    sched.forEach(slot=>{
      const match=(shift==='am'&&(slot.shift==='am'||slot.shift==='all'))||(shift==='pm'&&(slot.shift==='pm'||slot.shift==='all'))||(shift==='night'&&slot.shift==='night');
      if(match){slot.groups.forEach(g=>{g.items.forEach(it=>{ids.push(it.id)})})}
    });
  }
  /* 요일별 집중 청소는 오후조 통계에 포함되므로 pm 리셋 시 함께 */
  if(shift==='pm'){const dow=getDayOfWeek(date);if(DAY_FOCUS[dow])DAY_FOCUS[dow].forEach(it=>ids.push(it.id));}
  return ids;
}

/* 제출 후 해당 교대조 항목의 체크/온도/반영 STATE 비움 — 다음 점검 준비.
   제출완료 플래그(_submitted_*)·이슈/노하우(iss_/tip_)는 보존(기록·보드 표시 유지). */
function resetShiftChecks(date,shift,gender){
  const ids=collectShiftItemIds(date,shift,gender);
  ids.forEach(id=>{
    delete STATE[id];
    delete STATE['reflected_'+id];
    /* 회차별 체크 키도 함께 비움(다음 점검 준비) — 현재 성별 키만 */
    ROUND_KEYS.forEach(rk=>delete STATE[chkKey(rk,id,gender)]);
    const tf=tempFieldsFor(id);
    if(tf)tf.forEach(f=>delete STATE['temp_'+id+'_'+f.key]);
  });
  saveLocal(date,STATE,gender);
}

async function sendTelegramNotify(date,shift,submitter,gender){
  const nightMode=(shift==='night');
  const sched=nightMode?getNightSched(date):getSched(date);
  if(!sched)return;
  const labels={am:'오전조',pm:'오후조',night:'야간조'};
  const genderLabel=gender==='f'?'여':'남';
  const label=labels[shift]||shift;
  const stats=getShiftStatsG(sched,shift,date,gender);
  let issues=[];
  sched.forEach(slot=>{
    const match=(shift==='am'&&(slot.shift==='am'||slot.shift==='all'))||(shift==='pm'&&(slot.shift==='pm'||slot.shift==='all'))||(shift==='night'&&slot.shift==='night');
    if(match){
      slot.groups.forEach(g=>{g.items.forEach(it=>{
        if(STATE['iss_'+it.id])issues.push(`  - ${it.name}: ${STATE['iss_'+it.id]}`);
      })});
    }
  });
  const dow=getDayOfWeek(date);
  if(DAY_FOCUS[dow]){
    DAY_FOCUS[dow].forEach(it=>{
      if(STATE['iss_'+it.id])issues.push(`  - ${it.name}: ${STATE['iss_'+it.id]}`);
    });
  }
  let msg=`[지원부 체계 점검 ${label} 제출 (${genderLabel})]\n날짜: ${date}\n점검자: ${submitter}\n완료: ${stats.done}/${stats.total} (${stats.pct}%)`;
  if(issues.length)msg+=`\n\n이슈 ${issues.length}건:\n${issues.join('\n')}`;
  try{
    if(ONLINE){
      await fetch(API_URL,{method:'POST',redirect:'follow',
        headers:{'Content-Type':'text/plain'},
        body:JSON.stringify({action:'notify',date,shift,submitter,genderTab:gender,message:msg})
      });
    }
  }catch(e){}
}

/* ── 대시보드 데이터 수집 헬퍼 ── */
function collectDashboardData(d){
  const info=getDayInfo(d),sched=getSched(d),nightSched=getNightSched(d);
  const dn=['일','월','화','수','목','금','토'],dt=new Date(d+'T00:00:00');
  const dow=dt.getDay();

  if(!sched) return {closed:true,d,dow,dn,info};

  let amTotal=0,amDone=0,pmTotal=0,pmDone=0,nightTotal=0,nightDone=0;
  let closingTotal=0,closingDone=0;
  sched.forEach(slot=>{slot.groups.forEach(g=>{g.items.forEach(it=>{
    if(slot.shift==='am'){amTotal++;if(isCheckedAny(it))amDone++}
    else if(slot.shift==='pm'||slot.shift==='all'){pmTotal++;if(isCheckedAny(it))pmDone++}
  })})});
  // 마감 항목 별도 카운트 (pm 포함이지만 별도 표시용)
  sched.forEach(slot=>{
    if(slot.slot.includes('마감')){
      slot.groups.forEach(g=>{g.items.forEach(it=>{closingTotal++;if(isCheckedAny(it))closingDone++})});
    }
  });
  if(nightSched){
    nightSched.forEach(slot=>{slot.groups.forEach(g=>{g.items.forEach(it=>{
      nightTotal++;if(STATE[it.id])nightDone++;
    })})});
  }
  if(DAY_FOCUS[dow]){
    DAY_FOCUS[dow].forEach(it=>{pmTotal++;if(isCheckedAny(it))pmDone++});
  }

  const total=amTotal+pmTotal+nightTotal,done=amDone+pmDone+nightDone;
  const pct=total?Math.round(done/total*100):0;

  // 이슈/노하우 수집
  let issuesAm=[],issuesPm=[],issuesNight=[],issuesFocus=[];
  let allTips=[];
  sched.forEach(slot=>{slot.groups.forEach(g=>{g.items.forEach(it=>{
    const issVal=STATE['iss_'+it.id],tipVal=STATE['tip_'+it.id];
    if(issVal){
      const entry={slot:slot.slot,shift:slot.shift,name:it.name,memo:issVal,cat:g.title,id:it.id};
      if(slot.shift==='am') issuesAm.push(entry);
      else issuesPm.push(entry);
    }
    if(tipVal) allTips.push({slot:slot.slot,shift:slot.shift,name:it.name,memo:tipVal});
  })})});
  if(nightSched){
    nightSched.forEach(slot=>{slot.groups.forEach(g=>{g.items.forEach(it=>{
      if(STATE['iss_'+it.id])issuesNight.push({slot:slot.slot,shift:'night',name:it.name,memo:STATE['iss_'+it.id],cat:g.title,id:it.id});
      if(STATE['tip_'+it.id])allTips.push({slot:slot.slot,shift:'night',name:it.name,memo:STATE['tip_'+it.id]});
    })})});
  }
  if(DAY_FOCUS[dow]){
    DAY_FOCUS[dow].forEach(it=>{
      if(STATE['iss_'+it.id])issuesFocus.push({slot:'요일별',shift:'focus',name:it.name,memo:STATE['iss_'+it.id],cat:'요일별 집중 청소',id:it.id});
      if(STATE['tip_'+it.id])allTips.push({slot:'요일별',shift:'focus',name:it.name,memo:STATE['tip_'+it.id]});
    });
  }
  const allIssues=[...issuesAm,...issuesPm,...issuesNight,...issuesFocus];

  // 점검자별 통계 수집
  const submitterStats={};
  function countForSubmitter(name,shift){
    if(!name)return;
    if(!submitterStats[name])submitterStats[name]={done:0,total:0,issues:0,shifts:new Set()};
    submitterStats[name].shifts.add(shift);
  }
  // 오전 제출자
  if(STATE._submitter_am){
    const name=STATE._submitter_am;
    if(!submitterStats[name])submitterStats[name]={done:0,total:0,issues:0,shifts:new Set()};
    submitterStats[name].done+=amDone;
    submitterStats[name].total+=amTotal;
    submitterStats[name].shifts.add('오전');
    issuesAm.forEach(()=>submitterStats[name].issues++);
  }
  // 오후 제출자
  if(STATE._submitter_pm){
    const name=STATE._submitter_pm;
    if(!submitterStats[name])submitterStats[name]={done:0,total:0,issues:0,shifts:new Set()};
    submitterStats[name].done+=pmDone;
    submitterStats[name].total+=pmTotal;
    submitterStats[name].shifts.add('오후');
    issuesPm.forEach(()=>submitterStats[name].issues++);
    issuesFocus.forEach(()=>submitterStats[name].issues++);
  }
  // 야간 제출자
  if(STATE._submitter_night){
    const name=STATE._submitter_night;
    if(!submitterStats[name])submitterStats[name]={done:0,total:0,issues:0,shifts:new Set()};
    submitterStats[name].done+=nightDone;
    submitterStats[name].total+=nightTotal;
    submitterStats[name].shifts.add('야간');
    issuesNight.forEach(()=>submitterStats[name].issues++);
  }

  return {
    closed:false,d,dow,dn,info,sched,nightSched,
    amTotal,amDone,pmTotal,pmDone,nightTotal,nightDone,closingTotal,closingDone,
    total,done,pct,
    issuesAm,issuesPm,issuesNight,issuesFocus,allIssues,allTips,
    submitterStats,
    amPct:amTotal?Math.round(amDone/amTotal*100):0,
    pmPct:pmTotal?Math.round(pmDone/pmTotal*100):0,
    nightPct:nightTotal?Math.round(nightDone/nightTotal*100):0,
    closingPct:closingTotal?Math.round(closingDone/closingTotal*100):0
  };
}

async function renderAdmin(){
  const d=document.getElementById('adminDate').value;
  const el=document.getElementById('adminView');
  const info=getDayInfo(d);
  const dn=['일','월','화','수','목','금','토'],dt=new Date(d+'T00:00:00');
  const dow=dt.getDay();

  if(!getSched(d)){el.innerHTML=`<div class="admin-card"><h3>${d} (${dn[dow]}) - 휴관일</h3></div>`;return}
  el.innerHTML='<div class="loading">불러오는 중...</div>';
  await loadState(d);

  const data=collectDashboardData(d);
  if(data.closed){el.innerHTML=`<div class="admin-card"><h3>${d} (${dn[dow]}) - 휴관일</h3></div>`;return}

  let html='';

  /* ━━━ 요약 카드 ━━━ */
  html+=`<div class="dash-section-title">${d} (${dn[dow]}) <span class="day-type ${data.info.cls}">${data.info.label}</span> 현황 요약</div>`;
  html+=`<div class="dash-stat-row">`;
  html+=`<div class="dash-stat-card"><div class="num">${data.total}</div><div class="label">총 점검 항목</div></div>`;
  html+=`<div class="dash-stat-card"><div class="num" style="color:var(--green)">${data.done}</div><div class="label">완료</div></div>`;
  html+=`<div class="dash-stat-card"><div class="num" style="color:var(--red)">${data.total-data.done}</div><div class="label">미완료</div></div>`;
  html+=`<div class="dash-stat-card"><div class="num">${data.pct}%</div><div class="label">완료율</div></div>`;
  html+=`</div>`;

  /* ━━━ 교대별 통계 ━━━ */
  html+=`<div class="dash-section-title">교대별 통계</div>`;
  html+=`<table class="dash-table"><tr><th>교대</th><th>완료</th><th>총 항목</th><th>완료율</th><th>제출</th><th style="min-width:80px">그래프</th></tr>`;

  const shiftRows=[
    {label:'오전',done:data.amDone,total:data.amTotal,pct:data.amPct,sub:STATE._submitted_am,who:STATE._submitter_am,color:'green'},
    {label:'오후',done:data.pmDone,total:data.pmTotal,pct:data.pmPct,sub:STATE._submitted_pm,who:STATE._submitter_pm,color:'blue'},
    {label:'야간',done:data.nightDone,total:data.nightTotal,pct:data.nightPct,sub:STATE._submitted_night,who:STATE._submitter_night,color:'orange'},
    {label:'마감',done:data.closingDone,total:data.closingTotal,pct:data.closingPct,sub:null,who:null,color:'accent'}
  ];
  shiftRows.forEach(r=>{
    if(r.total===0)return;
    const subTxt=r.sub?`<span style="color:var(--green);font-weight:600">제출(${r.who||'-'})</span>`:(r.label==='마감'?'-':'<span style="color:var(--red);font-weight:600">미제출</span>');
    html+=`<tr><td><strong>${r.label}</strong></td><td>${r.done}</td><td>${r.total}</td><td>${r.pct}%</td><td>${subTxt}</td>`;
    html+=`<td><div class="dash-bar-wrap"><div class="dash-bar ${r.color}" style="width:${r.pct}%"></div></div></td></tr>`;
  });
  html+=`</table>`;

  /* ━━━ 점검자별 통계 ━━━ */
  const subs=Object.entries(data.submitterStats);
  if(subs.length>0){
    html+=`<div class="dash-section-title">점검자별 통계</div>`;
    html+=`<table class="dash-table"><tr><th>점검자</th><th>교대</th><th>완료</th><th>총 항목</th><th>이슈</th><th style="min-width:80px">완료율</th></tr>`;
    subs.forEach(([name,st])=>{
      const pct=st.total?Math.round(st.done/st.total*100):0;
      const shifts=[...st.shifts].join(', ');
      html+=`<tr><td><strong>${escapeHTML(name)}</strong></td><td>${shifts}</td><td>${st.done}</td><td>${st.total}</td>`;
      html+=`<td>${st.issues>0?'<span style="color:var(--red);font-weight:600">'+st.issues+'건</span>':'0건'}</td>`;
      html+=`<td><div class="dash-bar-wrap"><div class="dash-bar green" style="width:${pct}%"></div></div> ${pct}%</td></tr>`;
    });
    html+=`</table>`;
  }

  /* ━━━ 교대별 상세 카드 (기존 기능 유지) ━━━ */
  html+=`<div class="dash-section-title">교대별 상세</div>`;
  html+=buildAdminShiftCard('am','오전조',data.amDone,data.amTotal,data.amPct,STATE._submitted_am,STATE._submitter_am,STATE._submittedAt_am?new Date(STATE._submittedAt_am).toLocaleString('ko-KR'):'-',data.sched,null,dow,dn);
  html+=buildAdminShiftCard('pm','오후조',data.pmDone,data.pmTotal,data.pmPct,STATE._submitted_pm,STATE._submitter_pm,STATE._submittedAt_pm?new Date(STATE._submittedAt_pm).toLocaleString('ko-KR'):'-',data.sched,null,dow,dn);
  if(data.nightSched){
    html+=buildAdminShiftCard('night','야간조 (탕청소)',data.nightDone,data.nightTotal,data.nightPct,STATE._submitted_night,STATE._submitter_night,STATE._submittedAt_night?new Date(STATE._submittedAt_night).toLocaleString('ko-KR'):'-',null,data.nightSched,dow,dn);
  }

  /* ━━━ 이슈 목록 ━━━ */
  if(data.allIssues.length){
    html+=`<div class="dash-section-title" style="color:var(--red)">이슈 목록 (${data.allIssues.length}건)</div>`;
    const shiftGroups=[
      {key:'am',label:'오전조',items:data.issuesAm},
      {key:'pm',label:'오후조',items:data.issuesPm},
      {key:'night',label:'야간조',items:data.issuesNight},
      {key:'focus',label:'요일별 집중',items:data.issuesFocus}
    ];
    shiftGroups.forEach(sg=>{
      if(sg.items.length===0)return;
      html+=`<div class="dash-issue-card"><div style="font-size:13px;font-weight:700;color:var(--accent);margin-bottom:8px">${sg.label} (${sg.items.length}건)</div>`;
      sg.items.forEach(i=>{
        html+=`<div class="dash-issue-item"><div class="dash-issue-name">${i.name} <span class="dash-issue-meta">${i.slot} | ${i.cat}</span></div><div class="dash-issue-memo">${i.memo}</div></div>`;
      });
      html+=`</div>`;
    });
  }else{
    html+=`<div class="admin-card" style="border-color:rgba(106,191,123,0.3)"><h3 style="color:var(--green)">이슈 없음</h3><div style="font-size:13px;color:var(--dim)">오늘 보고된 이슈가 없습니다.</div></div>`;
  }

  /* ━━━ 노하우 ━━━ */
  if(data.allTips.length){
    html+='<div class="tip-card"><h3>노하우/개선 의견 ('+data.allTips.length+'건)</h3>';
    data.allTips.forEach(t=>{const sl={am:'오전',pm:'오후',night:'야간',all:'상시',focus:'집중'}[t.shift]||t.shift;html+=`<div style="padding:6px 0;border-bottom:1px solid rgba(167,139,218,0.2)"><div style="font-size:13px;font-weight:600">${t.name} <span style="color:var(--dim);font-size:11px">${sl}</span></div><div style="color:var(--purple);font-size:12px">${t.memo}</div></div>`});
    html+='</div>';
  }

  el.innerHTML=html;
}

function buildAdminShiftCard(shiftKey,label,done,total,pct,submitted,submitterName,submittedAt,daySched,nightSched,dow,dn){
  const dotColor=pct===100?'green':pct>0?'yellow':'red';
  const fillColor=shiftKey==='night'?'var(--orange)':'var(--green)';
  let html=`<div class="admin-shift-card ${shiftKey}"><h3>${label}</h3>`;
  // Submission status
  html+=`<div class="admin-shift-meta">`;
  if(submitted){
    html+=`<span class="submitted-badge">제출 완료</span> (${submitterName||'-'}) ${submittedAt}`;
  }else{
    html+=`<span class="not-submitted">미제출</span>`;
  }
  html+=`</div>`;
  // Progress
  html+=`<div class="admin-progress-wrap">
    <div class="progress-text"><span><span class="status-dot ${dotColor}"></span>${done}/${total}</span><span>${pct}%</span></div>
    <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${fillColor}"></div></div>
  </div>`;
  // Category breakdown
  const sched=nightSched||daySched;
  if(sched){
    sched.forEach(slot=>{
      let match=false;
      if(shiftKey==='am'&&(slot.shift==='am')) match=true;
      if(shiftKey==='pm'&&(slot.shift==='pm'||slot.shift==='all')) match=true;
      if(shiftKey==='night'&&slot.shift==='night') match=true;
      if(!match)return;
      slot.groups.forEach(g=>{
        let gd=0,gt=g.items.length;g.items.forEach(it=>{if(shiftKey==='night'?STATE[it.id]:isCheckedAny(it))gd++});
        const d2=gd===gt?'green':gd>0?'yellow':'red';
        const slotLabel=shiftKey==='night'?` ${slot.slot}`:'';
        html+=`<div class="admin-row"><span><span class="status-dot ${d2}"></span>${g.title}<span style="color:var(--dim);font-size:11px">${slotLabel}</span></span><span>${gd}/${gt}</span></div>`;
      });
    });
  }
  // Day focus in pm card
  if(shiftKey==='pm'&&DAY_FOCUS[dow]){
    let dfDone=0,dfTotal=DAY_FOCUS[dow].length;
    DAY_FOCUS[dow].forEach(it=>{if(isCheckedAny(it))dfDone++});
    const dfDot=dfDone===dfTotal?'green':dfDone>0?'yellow':'red';
    html+=`<div class="admin-row"><span><span class="status-dot ${dfDot}"></span>요일별 집중 청소 <span style="color:var(--dim);font-size:11px">${dn[dow]}요일</span></span><span>${dfDone}/${dfTotal}</span></div>`;
  }
  // Day focus in night card
  if(shiftKey==='night'&&DAY_FOCUS[dow]){
    let dfDone=0,dfTotal=DAY_FOCUS[dow].length;
    DAY_FOCUS[dow].forEach(it=>{if(STATE[it.id])dfDone++});
    const dfDot=dfDone===dfTotal?'green':dfDone>0?'yellow':'red';
    html+=`<div class="admin-row"><span><span class="status-dot ${dfDot}"></span>요일별 집중 청소 <span style="color:var(--dim);font-size:11px">${dn[dow]}요일</span></span><span>${dfDone}/${dfTotal}</span></div>`;
  }
  html+='</div>';
  return html;
}

/* ═══════════════════════════════════════════
   Toast 메시지
   ═══════════════════════════════════════════ */
let _toastTimer=null;
function showToast(msg){
  const el=document.getElementById('toastMsg');
  el.textContent=msg;el.style.display='block';
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(()=>{el.style.display='none'},2500);
}

function _copyToClipboard(text){
  if(navigator.clipboard){
    navigator.clipboard.writeText(text).then(()=>showToast('클립보드에 복사되었습니다'));
  }else{
    const ta=document.createElement('textarea');
    ta.value=text;document.body.appendChild(ta);ta.select();
    document.execCommand('copy');document.body.removeChild(ta);
    showToast('클립보드에 복사되었습니다');
  }
}

/* ═══════════════════════════════════════════
   현재 활성 탭 판별
   ═══════════════════════════════════════════ */
function getActiveTab(){
  const tabs=['manual','check-m','check-f','admin'];
  for(const t of tabs){
    const el=document.getElementById('tab-'+t);
    if(el&&!el.classList.contains('hidden'))return t;
  }
  return 'check-m';
}

/* ═══════════════════════════════════════════
   인쇄: 현재 활성 탭을 A4 맞춤 인쇄
   ═══════════════════════════════════════════ */
function printCurrentTab(){
  const tab=getActiveTab();
  // 모든 content에 data-print-active 제거
  document.querySelectorAll('.content').forEach(c=>c.removeAttribute('data-print-active'));
  // 활성 탭에 마킹
  const activeEl=document.getElementById('tab-'+tab);
  if(activeEl)activeEl.setAttribute('data-print-active','true');
  // 카테고리 펼치기
  activeEl.querySelectorAll('.cat-body').forEach(b=>{
    if(!b.classList.contains('open')){b.classList.add('open','print-opened')}
  });
  window.print();
  // 복원
  activeEl.querySelectorAll('.cat-body.print-opened').forEach(b=>{
    b.classList.remove('open','print-opened');
  });
  activeEl.removeAttribute('data-print-active');
}

/* ═══════════════════════════════════════════
   보고용: 격식체 텍스트 클립보드 복사
   ═══════════════════════════════════════════ */
async function copyReport(){
  const tab=getActiveTab();
  const d=(tab==='admin')?document.getElementById('adminDate').value
         :(tab==='check-f')?document.getElementById('checkDateF').value
         :document.getElementById('checkDateM').value;
  const dn=['일','월','화','수','목','금','토'];
  const dow=new Date(d+'T00:00:00').getDay();

  // 데이터 로드
  await loadState(d);
  const data=collectDashboardData(d);

  if(data.closed){
    _copyToClipboard('━━━ 지원부 체계 일일 점검 보고 ━━━\n보고일: '+d+' ('+dn[dow]+')\n\n휴관일입니다.');
    return;
  }

  const lines=[];
  lines.push('━━━ 지원부 체계 일일 점검 보고 ━━━');
  lines.push('보고일: '+d+' ('+dn[dow]+')');
  lines.push('');

  // 교대별 상세
  const shifts=[
    {label:'오전 점검',done:data.amDone,total:data.amTotal,shift:'am',sched:data.sched},
    {label:'오후 점검',done:data.pmDone,total:data.pmTotal,shift:'pm',sched:data.sched},
    {label:'야간 점검',done:data.nightDone,total:data.nightTotal,shift:'night',sched:data.nightSched}
  ];

  shifts.forEach(s=>{
    if(s.total===0)return;
    lines.push('■ '+s.label+' ('+s.done+'/'+s.total+' '+(s.done===s.total?'완료':'진행중')+')');
    if(s.sched){
      s.sched.forEach(slot=>{
        let match=false;
        if(s.shift==='am'&&(slot.shift==='am'))match=true;
        if(s.shift==='pm'&&(slot.shift==='pm'||slot.shift==='all'))match=true;
        if(s.shift==='night'&&slot.shift==='night')match=true;
        if(!match)return;
        slot.groups.forEach(g=>{
          g.items.forEach(it=>{
            const _on=s.shift==='night'?!!STATE[it.id]:isCheckedAny(it);
            const ck=_on?'v':'_';
            const iss=STATE['iss_'+it.id];
            let line='  '+ck+' '+it.name;
            if(iss) line+=' -- '+iss;
            else if(_on) line+=' -- 양호';
            lines.push(line);
          });
        });
      });
    }
    lines.push('');
  });

  // 요일별 집중
  if(DAY_FOCUS[dow]&&DAY_FOCUS[dow].length>0){
    let dfDone=0;DAY_FOCUS[dow].forEach(it=>{if(isCheckedAny(it))dfDone++});
    lines.push('■ '+dn[dow]+'요일 집중 청소 ('+dfDone+'/'+DAY_FOCUS[dow].length+')');
    DAY_FOCUS[dow].forEach(it=>{
      const _on=isCheckedAny(it);
      const ck=_on?'v':'_';
      const iss=STATE['iss_'+it.id];
      let line='  '+ck+' '+it.name;
      if(iss) line+=' -- '+iss;
      else if(_on) line+=' -- 양호';
      lines.push(line);
    });
    lines.push('');
  }

  // 이슈 사항
  if(data.allIssues.length>0){
    lines.push('■ 이슈 사항');
    data.allIssues.forEach(i=>{
      const shLabel={am:'오전',pm:'오후',night:'야간',focus:'집중'}[i.shift]||i.shift;
      lines.push('  ! '+i.name+' ('+shLabel+') -- '+i.memo);
    });
    lines.push('');
  }

  // 노하우
  if(data.allTips.length>0){
    lines.push('■ 노하우/개선 의견');
    data.allTips.forEach(t=>{
      lines.push('  * '+t.name+' -- '+t.memo);
    });
    lines.push('');
  }

  lines.push('━━━ 총 '+data.total+'건 | 완료 '+data.done+'건 ('+data.pct+'%) | 이슈 '+data.allIssues.length+'건 ━━━');

  _copyToClipboard(lines.join('\n'));
}

/* ═══════════════════════════════════════════
   공유용: 간단 1줄 형식
   ═══════════════════════════════════════════ */
async function copyShare(){
  const tab=getActiveTab();
  const d=(tab==='admin')?document.getElementById('adminDate').value
         :(tab==='check-f')?document.getElementById('checkDateF').value
         :document.getElementById('checkDateM').value;
  const dn=['일','월','화','수','목','금','토'];
  const dow=new Date(d+'T00:00:00').getDay();

  await loadState(d);
  const data=collectDashboardData(d);

  if(data.closed){
    _copyToClipboard(d+' ('+dn[dow]+') 휴관일');
    return;
  }

  const parts=[];
  if(data.amTotal>0){
    parts.push('[오전] '+data.amDone+'/'+data.amTotal+(data.amDone===data.amTotal?' 완료':' 진행중'));
  }
  if(data.pmTotal>0){
    parts.push('[오후] '+data.pmDone+'/'+data.pmTotal+(data.pmDone===data.pmTotal?' 완료':' 진행중'));
  }
  if(data.nightTotal>0){
    parts.push('[야간] '+data.nightDone+'/'+data.nightTotal+(data.nightDone===data.nightTotal?' 완료':' 진행중'));
  }

  let line=d+' ('+dn[dow]+') '+parts.join(' | ');

  if(data.allIssues.length>0){
    const issueSummary=data.allIssues.map(i=>i.name+' '+i.memo).join(', ');
    line+=' | 이슈 '+data.allIssues.length+'건: '+issueSummary;
  }else{
    line+=' | 이슈 없음';
  }

  _copyToClipboard(line);
}

function switchTab(tab, opts){
  // 탭 떠나기 전, 대기 중인 저장 스냅샷을 즉시 전송(떠나는 탭 체크 영속 보장 — 스냅샷이라 레이스 없음). GM 2026-06-12
  try{ flushStagedPush(); }catch(e){}
  // 점검(남)·점검(여) 비밀번호 보호
  if(opts==='lock' && sessionStorage.getItem('checkAuth')!=='1'){
    var pw = prompt('점검 탭 비밀번호를 입력하세요');
    if(pw !== '1234'){ if(pw !== null) alert('비밀번호가 틀립니다.'); return; }
    sessionStorage.setItem('checkAuth','1');
  }
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>{
    var oc = t.getAttribute('onclick') || '';
    if(oc.indexOf("'"+tab+"'") >= 0) t.classList.add('active');
  });
  document.getElementById('tab-policy').classList.toggle('hidden',tab!=='policy');
  document.getElementById('tab-guide').classList.toggle('hidden',tab!=='guide');
  document.getElementById('tab-chem').classList.toggle('hidden',tab!=='chem');
  document.getElementById('tab-manual').classList.toggle('hidden',tab!=='manual');
  document.getElementById('tab-check-m').classList.toggle('hidden',tab!=='check-m');
  document.getElementById('tab-check-f').classList.toggle('hidden',tab!=='check-f');
  document.getElementById('tab-admin').classList.toggle('hidden',tab!=='admin');
  document.getElementById('tab-manage').classList.toggle('hidden',tab!=='manage');
  // Show correct submit bar
  document.getElementById('submitBarM').style.display=(tab==='check-m')?'flex':'none';
  document.getElementById('submitBarF').style.display=(tab==='check-f')?'flex':'none';
  if(tab==='check-m'){activeGenderTab='m';renderG('m')}
  if(tab==='check-f'){activeGenderTab='f';renderG('f')}
  if(tab==='admin'){renderAdmin();renderAdminExtra();}
  if(tab==='manual'){renderBoard();renderManualItems();}
}

/* ═══════════════════════════════════════════════
   요일별 트렐로 보드 (매뉴얼 탭) — 7컬럼 × 남/여 = 14셀
   저장: localStorage(SUPPORT_MANUAL_BOARD) 즉시 영속 + 기존 패턴대로 API 베스트에포트 POST
   ═══════════════════════════════════════════════ */
const BOARD_STORAGE_KEY = 'SUPPORT_MANUAL_BOARD'; // 21셀 내용 영속 키 (7요일×남/여/외곽)
const BOARD_DAYS = [
  {key:'mon',label:'월',weekend:false},
  {key:'tue',label:'화',weekend:false},
  {key:'wed',label:'수',weekend:false},
  {key:'thu',label:'목',weekend:false},
  {key:'fri',label:'금',weekend:false},
  {key:'sat',label:'토',weekend:true},
  {key:'sun',label:'일',weekend:true}
];
/* 분류 3개: 남 / 여 / 외곽(외부·주차장·건물 외곽). cls = CSS 색 클래스 */
const BOARD_GENDERS = [
  {gk:'m',cls:'male',label:'👨 남'},
  {gk:'f',cls:'female',label:'👩 여'},
  {gk:'outer',cls:'outer',label:'🏢 외곽'}
];

/* 시드(seed) — 기존 요일별 집중 청소 표 + 남/여 전담 + 외부·주차장·건물 외곽 항목을 요일·분류 셀로 분배.
   각 값은 줄바꿈(\n) 구분 항목 리스트 텍스트. 줄 맨 앞 "시간대::" 표기 시 그 시간대 그룹으로 묶임.
   GM이 이후 직접 편집·저장. */
const BOARD_SEED = {
  mon:{
    m:'오전(08:00~12:00)::화장실 전체 청소\n오전(08:00~12:00)::탈수기 물때·곰팡이 제거\n오전(08:00~12:00)::B-1 파우더 관리\n오전(08:00~12:00)::B-5 사우나 화장실 (탕 배수: 마개+스위치)\n오전(08:00~12:00)::E-4 헬스장: 런닝머신 바닥\n오전(08:00~12:00)::E-5 골프장: 타석(스크린천)',
    f:'오전(08:00~12:00)::화장실 전체 청소\n오전(08:00~12:00)::탈수기 물때·곰팡이 제거\n오전(08:00~12:00)::B-1 파우더 관리\n오전(08:00~12:00)::B-5 사우나 화장실 (탕 배수: 마개+스위치)\n오전(08:00~12:00)::E-4 헬스장: 런닝머신 바닥\n오전(08:00~12:00)::E-5 골프장: 타석(스크린천)\n오후(14:00~18:00)::D-4 메인 복도 휴게공간 (여 전담)',
    outer:'오전후반(10:00~12:00)::D-3 메인 계단 B1-B2 (남 전담)\n오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장\n오후(14:00~18:00)::E-6 주차장 바닥·화장실·차단기'
  },
  tue:{
    m:'오전(08:00~12:00)::세면대 배수 파이프 청소\n오전(08:00~12:00)::배수구 소독·머리카락 제거\n오전(08:00~12:00)::탕 내 비품 점검\n오전(08:00~12:00)::E-2 거울·유리창 (화요일 집중)\n오후(14:00~18:00)::D-6 G.X룸 거울·바닥 (남 전담·화요일 집중)\n오전(08:00~12:00)::E-4 헬스장: 스트레칭 공간\n오전(08:00~12:00)::E-5 골프장: 타석(기계)',
    f:'오전(08:00~12:00)::세면대 배수 파이프 청소\n오전(08:00~12:00)::배수구 소독·머리카락 제거\n오전(08:00~12:00)::탕 내 비품 점검\n오전(08:00~12:00)::E-2 거울·유리창 (화요일 집중)\n오전(08:00~12:00)::E-4 헬스장: 스트레칭 공간\n오전(08:00~12:00)::E-5 골프장: 타석(기계)',
    outer:'오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장\n오후(14:00~18:00)::E-6 주차장 바닥·화장실·차단기'
  },
  wed:{
    m:'오전(08:00~12:00)::건/습식 사우나 바닥 고압세척 (산성세제 금지)\n오후(13:00~)::D-8 키즈 샤워실 (남 전담·2주1회 13:00)\n오전(08:00~12:00)::E-4 헬스장: 런닝머신 바닥\n오전(08:00~12:00)::E-5 골프장: 타석(스크린천)',
    f:'오전(08:00~12:00)::건/습식 사우나 바닥 고압세척 (산성세제 금지)\n오전(08:00~12:00)::E-4 헬스장: 런닝머신 바닥\n오전(08:00~12:00)::E-5 골프장: 타석(스크린천)',
    outer:'오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장\n오후(14:00~18:00)::E-6 주차장 바닥·화장실·차단기'
  },
  thu:{
    m:'오전(08:00~12:00)::화장실 전체 청소\n오전(08:00~12:00)::탈수기 물때·곰팡이 제거\n오전(08:00~12:00)::B-1 파우더 관리\n오전(08:00~12:00)::B-5 사우나 화장실\n오전(08:00~12:00)::E-4 헬스장: 스트레칭 공간\n오전(08:00~12:00)::E-5 골프장: 타석(기계)',
    f:'오전(08:00~12:00)::화장실 전체 청소\n오전(08:00~12:00)::탈수기 물때·곰팡이 제거\n오전(08:00~12:00)::B-1 파우더 관리\n오전(08:00~12:00)::B-5 사우나 화장실\n오전(08:00~12:00)::E-4 헬스장: 스트레칭 공간\n오전(08:00~12:00)::E-5 골프장: 타석(기계)',
    outer:'오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장\n오후(14:00~18:00)::E-6 주차장 바닥·화장실·차단기'
  },
  fri:{
    m:'오전(08:00~12:00)::세면대 배수 파이프 청소\n오전(08:00~12:00)::배수구 소독·머리카락 제거\n오전(08:00~12:00)::탕 내 비품 점검\n오전(08:00~12:00)::E-4 헬스장: 런닝머신 바닥\n오전(08:00~12:00)::E-5 골프장: 타석(스크린천)',
    f:'오전(08:00~12:00)::세면대 배수 파이프 청소\n오전(08:00~12:00)::배수구 소독·머리카락 제거\n오전(08:00~12:00)::탕 내 비품 점검\n오후(14:00~18:00)::D-7 센터 화분 물 공급 (여 전담·금요일 집중)\n오전(08:00~12:00)::E-4 헬스장: 런닝머신 바닥\n오전(08:00~12:00)::E-5 골프장: 타석(스크린천)',
    outer:'오전후반(10:00~12:00)::D-3 메인 계단 B1-B2 (남 전담)\n오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장\n오후(14:00~18:00)::E-6 주차장 바닥·화장실·차단기'
  },
  sat:{
    m:'오전(08:00~12:00)::벽체 곰팡이·물때 제거\n오전(08:00~12:00)::거울·유리창 물때 제거\n오전(08:00~12:00)::천정 환기구 먼지 제거\n오전(08:00~12:00)::방제\n오전(08:00~12:00)::E-4 헬스장: 거울\n오전(08:00~12:00)::E-5 골프장: 레슨룸',
    f:'오전(08:00~12:00)::벽체 곰팡이·물때 제거\n오전(08:00~12:00)::거울·유리창 물때 제거\n오전(08:00~12:00)::천정 환기구 먼지 제거\n오전(08:00~12:00)::방제\n오전(08:00~12:00)::여 사우나 청소\n오전(08:00~12:00)::E-4 헬스장: 거울\n오전(08:00~12:00)::E-5 골프장: 레슨룸',
    outer:'오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장\n오후(14:00~18:00)::E-6 주차장 바닥·화장실·차단기'
  },
  sun:{
    m:'오전(08:00~12:00)::탕청소 업체 휴무\n오전(08:00~12:00)::개인락커 + 미비 부분 보완\n오전(08:00~12:00)::E-4 헬스장: 거울\n오전(08:00~12:00)::E-5 골프장: 레슨룸',
    f:'오전(08:00~12:00)::탕청소 업체 휴무\n오전(08:00~12:00)::개인락커 + 미비 부분 보완\n오전(08:00~12:00)::여 사우나 청소\n오전(08:00~12:00)::E-4 헬스장: 거울\n오전(08:00~12:00)::E-5 골프장: 레슨룸',
    outer:'종일(휴관일 집중)::E-6 주차장 집중 (바닥·화장실·차단기)\n오전후반(10:00~12:00)::D-1 외부 화장실 (골프장/B1/B2)\n오전후반(10:00~12:00)::D-2 복도 휴지통 수거\n오전후반(10:00~12:00)::D-5 분리수거장'
  }
};

let BOARD_DATA = {}; // {dayKey:{m:'...', f:'...', outer:'...'}}

/* stored(객체) → BOARD_DATA 병합 (없으면 시드 폴백) · 3분류(m/f/outer) */
function applyBoardStored(stored){
  BOARD_DATA={};
  BOARD_DAYS.forEach(d=>{
    const s=(stored&&stored[d.key])||{};
    const seed=BOARD_SEED[d.key]||{};
    const cell={};
    BOARD_GENDERS.forEach(g=>{
      const gk=g.gk;
      cell[gk]=(s[gk]!==undefined&&s[gk]!==null)?s[gk]:(seed[gk]||'');
    });
    BOARD_DATA[d.key]=cell;
  });
}

/* 로컬 폴백 로드 (오프라인·동기 초기 렌더용) */
function loadBoardData(){
  let stored=null;
  try{ stored=JSON.parse(localStorage.getItem(BOARD_STORAGE_KEY)); }catch(e){ stored=null; }
  applyBoardStored(stored);
}

/* 백엔드에서 보드 로드 → 있으면 사용·로컬 캐시, 없거나 실패 시 localStorage 폴백.
   모든 기기 동기화의 핵심: 페이지 로드마다 백엔드를 진실 소스로 사용(last-write-wins). */
async function loadBoardFromBackend(){
  loadBoardData(); // 즉시 로컬/시드로 1차 렌더 가능하게
  if(!ONLINE) return;
  try{
    const res=await fetch(API_URL+'?action=board&key='+encodeURIComponent(BOARD_STORAGE_KEY),{method:'GET',redirect:'follow'});
    const data=await res.json();
    if(data && data.ok && data.board && typeof data.board==='object'){
      applyBoardStored(data.board);
      localStorage.setItem(BOARD_STORAGE_KEY, JSON.stringify(BOARD_DATA)); // 오프라인 폴백 캐시 갱신
    }
    // data.board===null → 백엔드에 아직 없음 → 로컬/시드 유지(이후 첫 저장 시 백엔드에 기록)
  }catch(e){ /* 네트워크 실패 → 이미 로드된 localStorage/시드 유지 */ }
  // 편집 중인 셀이 있으면 재렌더 보류(IME 조합·입력 보호). 없을 때만 갱신.
  const wrap=document.getElementById('manual-board');
  if(wrap && !wrap.querySelector('.dv-cell.editing')) renderBoard();
}

function persistBoardData(){
  // 1) localStorage 즉시 영속 (페이지 표준 오프라인 폴백 패턴)
  localStorage.setItem(BOARD_STORAGE_KEY, JSON.stringify(BOARD_DATA));
  // 2) 기존 저장 패턴대로 API 베스트에포트 POST (GAS가 action 미지원 시 무해히 무시)
  if(!ONLINE) return;
  const ind=document.getElementById('saveIndicator');
  if(ind){ind.style.display='block';ind.textContent='보드 저장 중...';}
  fetch(API_URL,{method:'POST',redirect:'follow',
    headers:{'Content-Type':'text/plain'},
    body:JSON.stringify({action:'saveBoard',key:BOARD_STORAGE_KEY,board:BOARD_DATA})
  }).then(()=>{if(ind){ind.textContent='보드 저장 완료';setTimeout(()=>{ind.style.display='none'},1500);}})
    .catch(()=>{if(ind){ind.textContent='보드 저장 (로컬 보관됨)';setTimeout(()=>{ind.style.display='none'},1500);}});
}

/* 선택된 요일 집합(다중선택). JS getDay(): 0=일~6=토 → BOARD_DAYS 순서로 매핑 */
const DOW_TO_DAYKEY=['sun','mon','tue','wed','thu','fri','sat'];
const BOARD_SELDAYS_KEY='SUPPORT_MANUAL_BOARD_SELDAYS'; // 선택 요일 영속 키(localStorage)
const ALL_DAY_KEYS=BOARD_DAYS.map(d=>d.key);
/* KST 오늘 날짜 문자열 (YYYY-MM-DD). UTC+9 보정 */
function kstToday(){
  const d=new Date(Date.now()+9*3600*1000);
  return d.toISOString().slice(0,10);
}
/* 선택 요일 Set. 저장값이 오늘(KST) 날짜와 같을 때만 복원 — 날짜 바뀌면 오늘 요일로 리셋 */
function loadSelectedDays(){
  let saved=null;
  try{ saved=JSON.parse(localStorage.getItem(BOARD_SELDAYS_KEY)); }catch(e){ saved=null; }
  if(saved&&saved.date===kstToday()&&Array.isArray(saved.days)){
    const valid=saved.days.filter(k=>ALL_DAY_KEYS.indexOf(k)>=0);
    if(valid.length) return new Set(valid);
  }
  // 저장값 없거나 날짜 달라졌으면: 오늘 요일(KST) 1개만 켬
  const todayKey=DOW_TO_DAYKEY[new Date(Date.now()+9*3600*1000).getUTCDay()];
  return new Set([todayKey]);
}
let SELECTED_DAYS = loadSelectedDays();
function saveSelectedDays(){
  // BOARD_DAYS 순서 보존하여 날짜와 함께 저장
  const ordered=ALL_DAY_KEYS.filter(k=>SELECTED_DAYS.has(k));
  try{ localStorage.setItem(BOARD_SELDAYS_KEY, JSON.stringify({date:kstToday(),days:ordered})); }catch(e){}
}

/* ── 시간대(time slot) = 항목의 저장 속성 ──
   저장 형식: 각 줄 맨 앞 "시간대::내용". BOARD_DATA(localStorage+백엔드)에 그대로 영속 → 시간대가 항목 속성으로 기록됨.
   표준 시간대 프리셋(편집 시 빠른 지정용). 기존 시드·저장값의 임의 라벨도 하위호환 파싱됨. */
const BOARD_TIMESLOTS=[
  {key:'오전(08:00~12:00)', short:'오전', t:'08:00'},
  {key:'오전후반(10:00~12:00)', short:'오전후반', t:'10:00'},
  {key:'오후(13:00~)', short:'오후(13시)', t:'13:00'},
  {key:'오후(14:00~18:00)', short:'오후', t:'14:00'},
  {key:'야간(18:00~)', short:'야간', t:'18:00'},
  {key:'종일(휴관일 집중)', short:'종일', t:'24:00'}
];
/* 라벨 → 정렬 기준 시각. 라벨 안 'HH:MM' 첫 등장 시각으로 시간 순 정렬(없으면 맨 뒤) */
function timeslotSortKey(label){
  if(!label||label==='기타') return '99:99';
  const m=String(label).match(/(\d{1,2}):(\d{2})/);
  return m ? (m[1].padStart(2,'0')+':'+m[2]) : '98:98';
}

/* 한 줄 파싱: "시간대::내용" → {tb:'시간대', text:'내용'}. 표기 없으면 tb='' (기타로 묶음) */
function parseBoardLine(line){
  const idx=line.indexOf('::');
  if(idx>0 && idx<=20){ // 시간대 라벨은 짧음 → 오작동 방지(URL :: 등 회피)
    return {tb:line.slice(0,idx).trim(), text:line.slice(idx+2).trim()};
  }
  return {tb:'', text:line};
}

/* 텍스트(줄바꿈 항목) → 2열 표(시간 | 내용) HTML. 시간 순 정렬·하위호환 파싱 유지 */
function boardCellBodyHTML(text){
  const lines=(text||'').split('\n').map(l=>l.trim()).filter(l=>l.length);
  if(!lines.length) return '<div class="dv-empty">항목 없음 — 편집으로 추가</div>';
  // 각 행을 {tb, text} 파싱 후 시간 순 정렬
  const rows=lines.map(l=>parseBoardLine(l));
  rows.sort((a,b)=>{
    const ka=timeslotSortKey(a.tb||'기타'), kb=timeslotSortKey(b.tb||'기타');
    if(ka!==kb) return ka<kb?-1:1;
    return 0;
  });
  // 모든 행이 시간대 없는 '기타'면 시간 열 숨김(단순 1열 표)
  const allEtc=rows.every(r=>!r.tb);
  let html='<table class="dv-timetable">';
  if(!allEtc) html+='<colgroup><col class="dv-tt-timecol"><col></colgroup>';
  rows.forEach(r=>{
    html+='<tr>';
    if(!allEtc) html+='<td class="dv-tt-time">'+(r.tb?escapeHTML(r.tb):'—')+'</td>';
    html+='<td class="dv-tt-task">'+escapeHTML(r.text)+'</td>';
    html+='</tr>';
  });
  html+='</table>';
  return html;
}

/* 요일 툴바 렌더 (7요일 다중선택 toggle + 전체 선택/해제 토글) */
function renderDayToolbar(){
  const bar=document.getElementById('day-toolbar');
  if(!bar)return;
  const todayKey=DOW_TO_DAYKEY[new Date().getDay()];
  const allOn=ALL_DAY_KEYS.every(k=>SELECTED_DAYS.has(k));
  let html='';
  BOARD_DAYS.forEach(d=>{
    const active=SELECTED_DAYS.has(d.key)?' active':'';
    const we=d.weekend?' is-weekend':'';
    const sub=(d.key===todayKey)?'오늘':(d.weekend?'주말':'평일');
    html+='<button type="button" class="day-tab'+active+we+'" onclick="toggleBoardDay(\''+d.key+'\')">'
        +'<span class="dt-day">'+d.label+'</span><span class="dt-sub">'+sub+'</span></button>';
  });
  // 전체 선택/해제 토글 (전부 켜져 있으면 '전체 해제', 아니면 '전체 선택')
  html+='<button type="button" class="day-tab day-all'+(allOn?' active':'')+'" onclick="toggleAllBoardDays()">'
      +'<span class="dt-day">'+(allOn?'전체 해제':'전체 선택')+'</span></button>';
  bar.innerHTML=html;
}

/* 트렐로 칸반 렌더 — 켠 요일마다 컬럼 1개. 각 컬럼 안 남/여/외곽 카드그룹 세로.
   textarea는 셀당 1개씩만 생성·재사용(IME 안전 / 편집 중 재렌더는 호출부에서 차단). */
function renderBoard(){
  renderDayToolbar();
  const wrap=document.getElementById('manual-board');
  if(!wrap)return;
  const todayKey=DOW_TO_DAYKEY[new Date().getDay()];
  const days=BOARD_DAYS.filter(d=>SELECTED_DAYS.has(d.key)); // BOARD_DAYS 순서 유지
  if(!days.length){
    wrap.classList.add('is-empty');
    wrap.innerHTML='<div class="board-empty">위 <b>요일 버튼</b>을 눌러 보고 싶은 요일을 켜세요. (여러 개 동시 선택 가능 · <b>전체 선택</b>으로 7요일 한 번에)</div>';
    return;
  }
  wrap.classList.remove('is-empty');
  let html='';
  days.forEach(d=>{
    const cell=BOARD_DATA[d.key]||{};
    const we=d.weekend?' is-weekend':'';
    const isToday=d.key===todayKey;
    html+='<div class="board-col'+we+'">';
    html+='<div class="board-col-head"><span class="bday">'+d.label+'</span>'
        +'<span class="day-type '+(d.weekend?'weekend':'weekday')+'">'+(d.weekend?'주말':'평일')+'</span>'
        +(isToday?'<span class="day-type" style="background:var(--green-bg);color:var(--green);margin-left:4px;">오늘</span>':'')+'</div>';
    html+='<div class="board-col-body">';
    BOARD_GENDERS.forEach(g=>{
      const gk=g.gk, cls=g.cls, lab=g.label;
      const cid=d.key+'_'+gk;
      const val=cell[gk]||'';
      html+='<div class="dv-cell '+cls+'" id="cell_'+cid+'">';
      html+='<div class="dv-cell-head"><span class="dv-cell-label '+cls+'">'+lab+'</span>'
          +'<div style="display:flex;align-items:center;gap:4px">'
          +'<button type="button" class="dv-edit-btn" id="btn_'+cid+'" onclick="boardToggleEdit(\''+d.key+'\',\''+gk+'\')">편집</button>'
          +'<button type="button" class="dv-edit-btn cancel" id="cancelbtn_'+cid+'" style="display:none" onclick="boardCancelEdit(\''+d.key+'\',\''+gk+'\')">취소</button>'
          +'</div></div>';
      html+='<div class="dv-body">'+boardCellBodyHTML(val)+'</div>';
      // 표 직접 편집 그리드 — 행 단위 [시간 | 내용 | 삭제]. 편집 진입 시 buildGridRows로 행 생성(IME 안전: 입력 중 재생성 안 함)
      html+='<div class="dv-grid" id="grid_'+cid+'">'
          +'<table class="dv-grid-table"><colgroup><col class="dv-g-timecol"><col><col class="dv-g-delcol"></colgroup>'
          +'<thead><tr><th class="dv-grid-th">시간대</th><th class="dv-grid-th">내용</th><th class="dv-grid-th"></th></tr></thead>'
          +'<tbody id="gridbody_'+cid+'"></tbody></table>'
          +'<button type="button" class="dv-g-addrow" onclick="boardGridAddRow(\''+cid+'\')">＋ 행 추가</button>'
          +'</div>';
      html+='<div class="dv-edit-hint">각 행의 <b>시간대 칸</b>(예: 오전(08:00~12:00) · 비워도 됨)과 <b>내용 칸</b>을 표에서 바로 수정하세요. <b>＋ 행 추가</b>/<b>✕</b>로 행을 늘리거나 지웁니다. 저장 시 모든 기기에 반영·시간 순 정렬됩니다.</div>';
      html+='</div>';
    });
    html+='</div></div>';
  });
  // 시간대 프리셋 datalist (모든 시간 칸 공유 — 입력 시 표준 시간대 자동완성)
  html+='<datalist id="dv-timeslot-options">';
  BOARD_TIMESLOTS.forEach(ts=>{ html+='<option value="'+escapeHTML(ts.key)+'">'+escapeHTML(ts.short)+'</option>'; });
  html+='</datalist>';
  wrap.innerHTML=html;
}

/* ── 표 직접 편집: 그리드 행 빌드·추가·삭제·직렬화 ──
   행 1개 = [시간 input | 내용 textarea(자동 높이) | 삭제]. 편집 진입 시 1회 빌드(IME 안전). */
function boardMakeGridRow(tb,text){
  const tr=document.createElement('tr');
  // 시간 칸
  const tdT=document.createElement('td');
  const inT=document.createElement('input');
  inT.type='text'; inT.className='dv-g-time'; inT.value=tb||'';
  inT.setAttribute('list','dv-timeslot-options');
  inT.placeholder='시간대(선택)';
  tdT.appendChild(inT); tr.appendChild(tdT);
  // 내용 칸 (textarea — 길면 칸 안에서 줄바꿈·높이 자동 확장)
  const tdC=document.createElement('td');
  const taC=document.createElement('textarea');
  taC.className='dv-g-task'; taC.rows=1; taC.value=text||'';
  taC.addEventListener('input',function(){ boardGridAutoSize(taC); });
  tdC.appendChild(taC); tr.appendChild(tdC);
  // 삭제 칸
  const tdD=document.createElement('td');
  const btnD=document.createElement('button');
  btnD.type='button'; btnD.className='dv-g-del'; btnD.textContent='✕';
  btnD.title='행 삭제';
  btnD.onclick=function(){ const tb2=tr.parentNode; tr.remove(); };
  tdD.appendChild(btnD); tr.appendChild(tdD);
  return {tr:tr, ta:taC};
}
/* 내용 textarea 높이를 내용에 맞게 자동 조정(칸 밖으로 넘침 방지) */
function boardGridAutoSize(ta){
  ta.style.height='auto';
  ta.style.height=Math.max(38,ta.scrollHeight)+'px';
}
/* 그리드를 현재 텍스트 값으로 채움 (편집 진입 시 1회). 시간 순 정렬·하위호환 파싱 유지 */
function boardGridBuild(cid,text){
  const body=document.getElementById('gridbody_'+cid);
  if(!body) return;
  body.innerHTML='';
  const lines=(text||'').split('\n').map(l=>l.trim()).filter(l=>l.length);
  let rows=lines.map(l=>parseBoardLine(l));
  rows.sort((a,b)=>{ const ka=timeslotSortKey(a.tb||'기타'),kb=timeslotSortKey(b.tb||'기타'); return ka<kb?-1:(ka>kb?1:0); });
  if(!rows.length) rows=[{tb:'',text:''}]; // 빈 셀이면 빈 행 1개 제공
  rows.forEach(r=>{ const made=boardMakeGridRow(r.tb,r.text); body.appendChild(made.tr); boardGridAutoSize(made.ta); });
}
/* 행 추가 — 기존 행 보존하고 빈 행 1개 append(IME 안전: 기존 입력칸 재생성 없음) */
function boardGridAddRow(cid){
  const body=document.getElementById('gridbody_'+cid);
  if(!body) return;
  const made=boardMakeGridRow('','');
  body.appendChild(made.tr);
  boardGridAutoSize(made.ta);
  made.ta.focus();
}
/* 그리드 → "시간대::내용" 라인 문자열로 직렬화(기존 저장/백엔드 포맷·하위호환 유지).
   시간 없는 행은 내용만, 내용 빈 행은 제외. */
function boardGridSerialize(cid){
  const body=document.getElementById('gridbody_'+cid);
  if(!body) return '';
  const out=[];
  body.querySelectorAll('tr').forEach(tr=>{
    const t=tr.querySelector('.dv-g-time'); const c=tr.querySelector('.dv-g-task');
    if(!c) return;
    const tb=(t?t.value:'').trim();
    const text=c.value.replace(/\n/g,' ').trim(); // 셀 내 줄바꿈은 공백으로(라인 포맷 보호)
    if(!text) return; // 내용 없는 행은 저장 제외
    out.push(tb?(tb+'::'+text):text);
  });
  return out.join('\n');
}

/* 편집 중인 셀이 있으면 토글 보류(저장/닫기 유도) */
function boardHasEditing(){
  const wrap=document.getElementById('manual-board');
  return !!(wrap && wrap.querySelector('.dv-cell.editing'));
}

/* 요일 toggle (켜고 끄기) → 컬럼 증감. 편집 중이면 보류. 선택 상태 localStorage 영속 */
function toggleBoardDay(dayKey){
  if(boardHasEditing()){
    alert('편집 중인 카드를 먼저 저장하거나 닫아주세요.');
    return;
  }
  if(SELECTED_DAYS.has(dayKey)) SELECTED_DAYS.delete(dayKey);
  else SELECTED_DAYS.add(dayKey);
  saveSelectedDays();
  renderBoard();
}

/* 전체 선택/해제 토글. 전부 켜져 있으면 모두 해제, 아니면 모두 켬 */
function toggleAllBoardDays(){
  if(boardHasEditing()){
    alert('편집 중인 카드를 먼저 저장하거나 닫아주세요.');
    return;
  }
  const allOn=ALL_DAY_KEYS.every(k=>SELECTED_DAYS.has(k));
  SELECTED_DAYS = allOn ? new Set() : new Set(ALL_DAY_KEYS);
  saveSelectedDays();
  renderBoard();
}

/* 편집 토글 + 저장. 표 그리드(행 단위 [시간|내용]) 직접 편집.
   진입 시 그리드를 현재 값으로 1회 빌드(IME 안전), 저장 시 그리드→라인 직렬화. */
function boardToggleEdit(dayKey,gk){
  const cid=dayKey+'_'+gk;
  const cell=document.getElementById('cell_'+cid);
  const btn=document.getElementById('btn_'+cid);
  const cancelbtn=document.getElementById('cancelbtn_'+cid);
  if(!cell||!btn)return;
  const editing=cell.classList.contains('editing');
  if(!editing){
    // 편집 진입 — 게이트(기존 항목 편집과 동일 비밀번호)
    if(typeof requireEditAuth==='function' && !requireEditAuth()) return;
    // 먼저 editing 노출(그리드 display:block) → 그래야 textarea 높이 자동조정(scrollHeight) 정상 측정
    cell.classList.add('editing');
    // 그리드를 현재 저장값으로 빌드(편집 진입 시 1회 — 입력 중 재빌드 안 함)
    boardGridBuild(cid,(BOARD_DATA[dayKey]&&BOARD_DATA[dayKey][gk])||'');
    btn.textContent='저장';
    btn.classList.add('save');
    if(cancelbtn) cancelbtn.style.display='';
    const firstTask=cell.querySelector('.dv-g-task');
    if(firstTask) firstTask.focus();
  }else{
    // 저장 — 그리드를 라인 포맷으로 직렬화 후 반영(기존 저장/백엔드 포맷 유지)
    const serialized=boardGridSerialize(cid);
    BOARD_DATA[dayKey][gk]=serialized;
    cell.classList.remove('editing');
    btn.textContent='편집';
    btn.classList.remove('save');
    if(cancelbtn) cancelbtn.style.display='none';
    // 본문(표) 노드만 갱신 — 시간 순 정렬·하위호환 렌더
    const oldBody=cell.querySelector('.dv-body');
    if(oldBody) oldBody.innerHTML=boardCellBodyHTML(serialized);
    persistBoardData();
  }
}

/* 취소 — 편집 중 미저장 변경분 폐기, 편집 모드 종료(다음 진입 시 저장값으로 다시 빌드됨) */
function boardCancelEdit(dayKey,gk){
  const cid=dayKey+'_'+gk;
  const cell=document.getElementById('cell_'+cid);
  const btn=document.getElementById('btn_'+cid);
  const cancelbtn=document.getElementById('cancelbtn_'+cid);
  if(!cell||!btn)return;
  cell.classList.remove('editing');
  btn.textContent='편집';
  btn.classList.remove('save');
  if(cancelbtn) cancelbtn.style.display='none';
}

/* ═══════════════════════════════════════════════
   지원부 규정 트렐로 보드 (규정 탭) — 주제별 칸(컬럼) × 편집 카드
   상태(확정) 열 폐기. 매뉴얼 보드와 동일 영속 패턴(localStorage + 백엔드 best-effort).
   저장키: SUPPORT_POLICY_BOARD. 인증 게이트 requireEditAuth(1234) 재사용.
   ═══════════════════════════════════════════════ */
const POLICY_STORAGE_KEY = 'SUPPORT_POLICY_BOARD';
/* 주제별 칸(컬럼) 정의. cls = 좌측 색 바 클래스(dv-cell 재사용) */
const POLICY_COLS = [
  {key:'ops',   label:'운영 기준', cls:'male'},
  {key:'meet',  label:'정기 회의', cls:'female'}
];
/* 시드 — 기존 규정 표·정기회의 표 내용 무손실 이관.
   각 카드 = {id, title, body}. 공식값(운영시간 등)은 원문 그대로. GM이 이후 직접 편집·저장. */
const POLICY_SEED = {
  ops:[
    {id:'op_hours', title:'운영시간', body:'평일 06:00~22:30 / 주말·공휴일 08:00~20:00\n휴관: 신정·명절·매월 2·4번째 일요일'},
    {id:'op_shift', title:'근무조 편성', body:'오전조 05:30~14:15 / 중간조 10:00 또는 12:00~ / 오후조 14:00~22:30'},
    {id:'op_zone',  title:'담당 구역', body:'A(사우나) B(락커룸) C(세탁물) D(사우나 외부) E(외곽+헬스장+골프장)'},
    {id:'op_clean', title:'위생·청결', body:'대리석·코팅면 산성세제 금지 / 전기설비 비닐 포장 후 청소'},
    {id:'op_safe',  title:'안전 보고', body:'즉시 조치 불가 시 팀장·소장 즉시 보고 의무'},
    {id:'op_warn',  title:'마감 경고', body:'사우나·파우더 마감 미비 시 경고 / 3회 → 경징계'},
    {id:'op_tub',   title:'탕청소 위탁', body:'야간 업체 위탁 / 평일 23:00 / 주말 20:30 출근'}
  ],
  meet:[
    {id:'mt_week',  title:'주간 브리핑', body:'주기: 매주 월 오전\n참석: 최준용M·윤병현AM·오전조\n안건: 지난주 이슈 / 이번주 집중 구역 / 비품 현황'},
    {id:'mt_month', title:'월간 운영 회의', body:'주기: 매월 첫째주 화\n참석: 최준용M·윤병현AM\n안건: 이슈·노하우 취합 / 매뉴얼 개정 여부'},
    {id:'mt_urgent',title:'긴급 회의', body:'주기: 이슈 발생 즉시\n참석: 해당 담당자+팀장\n안건: 원인 분석 / 즉시 조치'}
  ]
};

let POLICY_DATA = {}; // {colKey:[{id,title,body}, ...]}

/* stored(객체) → POLICY_DATA 병합 (없으면 시드 폴백) */
function applyPolicyStored(stored){
  POLICY_DATA={};
  POLICY_COLS.forEach(c=>{
    const arr=(stored&&Array.isArray(stored[c.key]))?stored[c.key]:null;
    if(arr){
      POLICY_DATA[c.key]=arr.map(card=>({
        id:card&&card.id?String(card.id):policyGenId(),
        title:card&&card.title!=null?String(card.title):'',
        body:card&&card.body!=null?String(card.body):''
      }));
    }else{
      POLICY_DATA[c.key]=(POLICY_SEED[c.key]||[]).map(card=>({id:card.id,title:card.title,body:card.body}));
    }
  });
}
function policyGenId(){ return 'pol_'+Date.now()+'_'+Math.random().toString(36).slice(2,7); }

/* 로컬 폴백 로드 (오프라인·동기 초기 렌더용) */
function loadPolicyData(){
  let stored=null;
  try{ stored=JSON.parse(localStorage.getItem(POLICY_STORAGE_KEY)); }catch(e){ stored=null; }
  applyPolicyStored(stored);
}

/* 백엔드 로드 → 있으면 사용·로컬 캐시, 없거나 실패 시 localStorage 폴백(매뉴얼 보드와 동일 패턴) */
async function loadPolicyFromBackend(){
  loadPolicyData(); // 즉시 로컬/시드로 1차 렌더
  if(!ONLINE) return;
  try{
    const res=await fetch(API_URL+'?action=board&key='+encodeURIComponent(POLICY_STORAGE_KEY),{method:'GET',redirect:'follow'});
    const data=await res.json();
    if(data && data.ok && data.board && typeof data.board==='object'){
      applyPolicyStored(data.board);
      localStorage.setItem(POLICY_STORAGE_KEY, JSON.stringify(POLICY_DATA));
    }
  }catch(e){ /* 네트워크 실패 → 로컬/시드 유지 */ }
  const wrap=document.getElementById('policy-board');
  if(wrap && !wrap.querySelector('.dv-cell.editing')) renderPolicyBoard();
}

function persistPolicyData(){
  localStorage.setItem(POLICY_STORAGE_KEY, JSON.stringify(POLICY_DATA));
  if(!ONLINE) return;
  const ind=document.getElementById('saveIndicator');
  if(ind){ind.style.display='block';ind.textContent='규정 저장 중...';}
  fetch(API_URL,{method:'POST',redirect:'follow',
    headers:{'Content-Type':'text/plain'},
    body:JSON.stringify({action:'saveBoard',key:POLICY_STORAGE_KEY,board:POLICY_DATA})
  }).then(()=>{if(ind){ind.textContent='규정 저장 완료';setTimeout(()=>{ind.style.display='none'},1500);}})
    .catch(()=>{if(ind){ind.textContent='규정 저장 (로컬 보관됨)';setTimeout(()=>{ind.style.display='none'},1500);}});
}

/* 카드 본문(줄바꿈) → 표시 HTML. 빈 값이면 안내. */
function policyCardBodyHTML(body){
  const lines=(body||'').split('\n').map(l=>l.trim()).filter(l=>l.length);
  if(!lines.length) return '<div class="dv-empty">내용 없음 — 편집으로 추가</div>';
  return lines.map(l=>'<div class="pol-line">'+escapeHTML(l)+'</div>').join('');
}

/* 트렐로 칸반 렌더 — 칸(컬럼)마다 카드 세로. 카드별 편집/취소/저장 + 카드 추가/삭제.
   textarea는 편집 진입 시 1회 생성·재사용(IME 안전). */
function renderPolicyBoard(){
  const wrap=document.getElementById('policy-board');
  if(!wrap)return;
  let html='';
  POLICY_COLS.forEach(col=>{
    const cards=POLICY_DATA[col.key]||[];
    html+='<div class="board-col">';
    html+='<div class="board-col-head"><span class="bday" style="font-size:17px;">'+escapeHTML(col.label)+'</span>'
        +'<span class="day-type weekday">'+cards.length+'개</span></div>';
    html+='<div class="board-col-body">';
    cards.forEach(card=>{
      const cid=col.key+'__'+card.id;
      html+='<div class="dv-cell '+col.cls+'" id="polcell_'+cid+'">';
      html+='<div class="dv-cell-head"><span class="dv-cell-label '+col.cls+'">'+escapeHTML(card.title||'(제목 없음)')+'</span>'
          +'<div style="display:flex;align-items:center;gap:4px">'
          +'<button type="button" class="dv-edit-btn" id="polbtn_'+cid+'" onclick="policyToggleEdit(\''+col.key+'\',\''+card.id+'\')">편집</button>'
          +'<button type="button" class="dv-edit-btn cancel" id="polcancel_'+cid+'" style="display:none" onclick="policyCancelEdit(\''+col.key+'\',\''+card.id+'\')">취소</button>'
          +'</div></div>';
      html+='<div class="dv-body">'+policyCardBodyHTML(card.body)+'</div>';
      // 편집 폼 — 제목 input + 본문 textarea + 카드 삭제 (편집 진입 시 값 채움, IME 안전: 입력 중 재생성 없음)
      html+='<div class="pol-edit" id="poledit_'+cid+'">'
          +'<label class="pol-edit-lab">제목</label>'
          +'<input type="text" class="pol-edit-title" id="poltitle_'+cid+'" placeholder="카드 제목">'
          +'<label class="pol-edit-lab">내용 (줄바꿈으로 항목 구분)</label>'
          +'<textarea class="pol-edit-body" id="polbody_'+cid+'" rows="4" placeholder="내용을 입력하세요"></textarea>'
          +'<button type="button" class="pol-del-btn" onclick="policyDeleteCard(\''+col.key+'\',\''+card.id+'\')">이 카드 삭제</button>'
          +'</div>';
      html+='<div class="dv-edit-hint">제목·내용을 수정하고 <b>저장</b>을 누르면 모든 기기에 반영됩니다. 공식값(운영시간 등)은 임의 변경하지 마세요.</div>';
      html+='</div>';
    });
    html+='<button type="button" class="dv-g-addrow" onclick="policyAddCard(\''+col.key+'\')">＋ 카드 추가</button>';
    html+='</div></div>';
  });
  wrap.innerHTML=html;
}

function policyFindCard(colKey,id){
  const arr=POLICY_DATA[colKey]||[];
  for(let i=0;i<arr.length;i++){ if(arr[i].id===id) return {arr:arr,idx:i,card:arr[i]}; }
  return null;
}

/* 편집 중인 카드가 있는지 */
function policyHasEditing(){
  const wrap=document.getElementById('policy-board');
  return !!(wrap && wrap.querySelector('.dv-cell.editing'));
}

/* 편집 토글 + 저장. 진입 시 폼에 현재값 채움(1회), 저장 시 폼값 → 데이터 반영. */
function policyToggleEdit(colKey,id){
  const cid=colKey+'__'+id;
  const cell=document.getElementById('polcell_'+cid);
  const btn=document.getElementById('polbtn_'+cid);
  const cancelbtn=document.getElementById('polcancel_'+cid);
  const found=policyFindCard(colKey,id);
  if(!cell||!btn||!found)return;
  const editing=cell.classList.contains('editing');
  if(!editing){
    if(typeof requireEditAuth==='function' && !requireEditAuth()) return;
    cell.classList.add('editing');
    // 폼에 현재값 채움 (편집 진입 시 1회 — 입력 중 재생성 안 함)
    const ti=document.getElementById('poltitle_'+cid);
    const bo=document.getElementById('polbody_'+cid);
    if(ti) ti.value=found.card.title||'';
    if(bo) bo.value=found.card.body||'';
    btn.textContent='저장';
    btn.classList.add('save');
    if(cancelbtn) cancelbtn.style.display='';
    if(ti) ti.focus();
  }else{
    const ti=document.getElementById('poltitle_'+cid);
    const bo=document.getElementById('polbody_'+cid);
    found.card.title=ti?ti.value.trim():found.card.title;
    found.card.body=bo?bo.value:found.card.body;
    cell.classList.remove('editing');
    btn.textContent='편집';
    btn.classList.remove('save');
    if(cancelbtn) cancelbtn.style.display='none';
    // 제목·본문 노드만 갱신
    const labEl=cell.querySelector('.dv-cell-label');
    if(labEl) labEl.textContent=found.card.title||'(제목 없음)';
    const bodyEl=cell.querySelector('.dv-body');
    if(bodyEl) bodyEl.innerHTML=policyCardBodyHTML(found.card.body);
    persistPolicyData();
  }
}

/* 취소 — 미저장 변경분 폐기, 편집 모드 종료(다음 진입 시 저장값으로 다시 채움) */
function policyCancelEdit(colKey,id){
  const cid=colKey+'__'+id;
  const cell=document.getElementById('polcell_'+cid);
  const btn=document.getElementById('polbtn_'+cid);
  const cancelbtn=document.getElementById('polcancel_'+cid);
  if(!cell||!btn)return;
  cell.classList.remove('editing');
  btn.textContent='편집';
  btn.classList.remove('save');
  if(cancelbtn) cancelbtn.style.display='none';
}

/* 카드 추가 — 빈 카드 1개 추가 후 재렌더·편집 진입 */
function policyAddCard(colKey){
  if(typeof requireEditAuth==='function' && !requireEditAuth()) return;
  if(policyHasEditing()){ alert('편집 중인 카드를 먼저 저장하거나 닫아주세요.'); return; }
  if(!Array.isArray(POLICY_DATA[colKey])) POLICY_DATA[colKey]=[];
  const nid=policyGenId();
  POLICY_DATA[colKey].push({id:nid,title:'새 카드',body:''});
  persistPolicyData();
  renderPolicyBoard();
  policyToggleEdit(colKey,nid); // 바로 편집 진입
}

/* 카드 삭제 */
function policyDeleteCard(colKey,id){
  if(typeof requireEditAuth==='function' && !requireEditAuth()) return;
  if(!confirm('이 카드를 삭제할까요?')) return;
  const found=policyFindCard(colKey,id);
  if(!found) return;
  found.arr.splice(found.idx,1);
  persistPolicyData();
  renderPolicyBoard();
}

/* ── Init ── */
const today=kstToday();   // KST 오늘(UTC toISOString는 자정~09시 어제로 어긋남 — 오전조 차단)
document.getElementById('checkDateM').value=today;
document.getElementById('checkDateF').value=today;
document.getElementById('adminDate').value=today;
document.getElementById('checkDateM').addEventListener('change',()=>renderG('m'));
document.getElementById('checkDateF').addEventListener('change',()=>renderG('f'));
document.getElementById('adminDate').addEventListener('change',renderAdmin);

// 점검자 입력칸 = 빈칸 시작(자동복원 없음). 담당자 드롭다운(명단·기억) 채우기.
populateSubmitterDropdowns();
populateDutyDropdowns();

loadStaffFromSheet();
loadItemMasterFromSheet(); // 점검 항목 마스터를 시트에서 로드 (비동기 — 완료 시 화면 갱신)
loadBoardData(); renderBoard(); loadBoardFromBackend(); // 요일별 보드: 로컬 즉시 렌더 후 백엔드 동기화(모든 기기 반영)
loadPolicyData(); renderPolicyBoard(); loadPolicyFromBackend(); // 규정 트렐로 보드: 로컬 즉시 렌더 후 백엔드 동기화
renderG('m');

/* ═══════════════════════════════════════════════
   항목 관리 (CRUD) — localStorage 기반
   ═══════════════════════════════════════════════ */

const MGMT_STORAGE_KEY = 'wcheck_custom_items';
let mgmtEditingId = null; // null = 추가 모드, string = 편집 중인 ID

/* ── 관리자 편집 게이트 (비밀번호 1234, 세션당 1회) ──
   조회·열람은 게이트 없음. 추가/편집저장/삭제 등 변경 시에만 호출. */
function requireEditAuth(){
  if(sessionStorage.getItem('editAuth')==='1') return true;
  var pw = prompt('항목 편집 비밀번호를 입력하세요');
  if(pw !== '1234'){ if(pw !== null) alert('비밀번호가 틀립니다.'); return false; }
  sessionStorage.setItem('editAuth','1');
  return true;
}

/* mgmtLoadItems → 시트 동기화된 CUSTOM_ITEMS 반환 (localStorage 폐기) */
function mgmtLoadItems(){
  return CUSTOM_ITEMS;
}
/* mgmtSaveItems → CUSTOM_ITEMS 갱신 + 시트 저장(saveItems) + 오프라인 캐시 */
function mgmtSaveItems(items){
  CUSTOM_ITEMS = items;
  localStorage.setItem(ITEM_CACHE_KEY, JSON.stringify(items)); // 오프라인 폴백 캐시
  if(!ONLINE) return;
  const payload = items.map(itemToSheet);
  const ind = document.getElementById('saveIndicator');
  if(ind){ ind.style.display='block'; ind.textContent='항목 저장 중...'; }
  fetch(API_URL,{method:'POST',redirect:'follow',
    headers:{'Content-Type':'text/plain'},
    body:JSON.stringify(withDept({action:'saveItems',items:payload}))
  }).then(()=>{ if(ind){ind.textContent='항목 저장 완료';setTimeout(()=>{ind.style.display='none'},1500);} })
    .catch(()=>{ if(ind){ind.textContent='항목 저장 실패 (로컬 보관됨)';setTimeout(()=>{ind.style.display='none'},1500);} });
}

function mgmtGenerateId(){
  const d=new Date();
  const ymd=d.getFullYear().toString()
    +(String(d.getMonth()+1).padStart(2,'0'))
    +(String(d.getDate()).padStart(2,'0'));
  // 당일 cx_ 항목 개수 기반 순번 (zero-pad 3자리)
  const todayPrefix='cx_'+ymd;
  const seq=((CUSTOM_ITEMS||[]).filter(it=>String(it.id||'').indexOf(todayPrefix)===0).length)+1;
  return todayPrefix+'_'+String(seq).padStart(3,'0');
}

/* ── 점검 화면 카테고리별 빠른 항목 추가 (셋업 편집기 데이터계층 재사용) ──
   카테고리 하단 "＋ 항목 추가" → 인라인 입력칸 1회 생성(한글 IME 조합 중 재렌더 금지) →
   CUSTOM_ITEMS push → mgmtSaveItems(기존 saveItems POST) → renderG 재렌더.
   slot/shift는 렌더 루프의 라이브 값을 그대로 전달(형식 보존), gender는 탭(m/f). */
function quickAddBarHtml(slot, shift, category, gender){
  // 점검 화면 항목추가 제거(GM 2026-06-12): 항목 추가·수정은 '매뉴얼' 탭 단일출처. 점검=체크+이슈/노하우만.
  return '';
}

function quickAddOpen(btn, slot, shift, category, gender){
  const bar = btn.closest('.quickadd-bar');
  if(!bar || bar.querySelector('.quickadd-form')) return; // 이미 열림
  btn.style.display='none';
  const form=document.createElement('div');
  form.className='quickadd-form';
  // 입력칸은 1회만 생성 후 재사용 — 조합 중 DOM 재생성 금지
  form.innerHTML=
    '<input type="text" class="quickadd-name" placeholder="항목명 (필수)" autocomplete="off">'+
    '<input type="text" class="quickadd-detail" placeholder="상세 (선택)" autocomplete="off">'+
    '<div class="quickadd-actions">'+
      '<button class="quickadd-save">저장</button>'+
      '<button class="quickadd-cancel">취소</button>'+
    '</div>';
  bar.appendChild(form);
  const nameEl=form.querySelector('.quickadd-name');
  const detailEl=form.querySelector('.quickadd-detail');
  const meta={slot:slot, shift:shift, category:category, gender:gender};
  form.querySelector('.quickadd-save').addEventListener('click',()=>quickAddSave(form,meta));
  form.querySelector('.quickadd-cancel').addEventListener('click',()=>{ const b=bar.querySelector('.quickadd-btn'); if(b)b.style.display=''; form.remove(); });
  // Enter=저장(IME 조합 확정 중 Enter는 무시: isComposing)
  nameEl.addEventListener('keydown',e=>{ if(e.key==='Enter' && !e.isComposing){ e.preventDefault(); quickAddSave(form,meta); } });
  detailEl.addEventListener('keydown',e=>{ if(e.key==='Enter' && !e.isComposing){ e.preventDefault(); quickAddSave(form,meta); } });
  nameEl.focus();
}

function quickAddSave(form, meta){
  const nameEl=form.querySelector('.quickadd-name');
  const detailEl=form.querySelector('.quickadd-detail');
  const name=(nameEl.value||'').trim();
  if(!name){ alert('항목명을 입력해주세요.'); nameEl.focus(); return; }
  const newItem={
    id: mgmtGenerateId(),               // 신규 custom_… (기존 ID 재사용 금지 → STATE 유실 방지)
    slot: meta.slot,
    shift: meta.shift,
    dayType: 'both',
    gender: meta.gender,                // 점검(남)→'m' / 점검(여)→'f'
    category: meta.category,
    name: name,
    detail: (detailEl.value||'').trim(),
    order: undefined                    // 말미(itemToSheet가 idx+1 부여)
  };
  const next=(CUSTOM_ITEMS||[]).concat([newItem]);
  mgmtSaveItems(next);                  // CUSTOM_ITEMS 갱신 + 시트 저장(saveItems POST)
  renderG(meta.gender);                 // 재렌더 → 새 항목이 해당 카테고리에 체크박스로 합류
}


function escapeHTML(s){
  if(!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── 커스텀 항목을 기존 스케줄에 주입 ── */
function mgmtGetCustomItemsForSchedule(schedType){
  // schedType: 'weekday' or 'weekend'
  // GM이 시트에 저장한 항목(CUSTOM_ITEMS)을 해당 스케줄에 주입.
  const items = mgmtLoadItems();
  return items.filter(item => {
    /* shadow(기본 항목 편집분, id가 custom_ 아님)는 신규 주입 제외 — renderItem override 맵으로만 반영(중복 방지) */
    if(isShadowItem(item)) return false;
    if(!item.dayType || item.dayType === 'both') return true;
    return item.dayType === schedType;
  });
}

function mgmtBuildCustomSlots(customItems){
  // 커스텀 아이템을 slot+shift+category 기준으로 그룹핑하여
  // 기존 스케줄 포맷과 동일한 구조로 반환
  const slotMap = {};
  customItems.forEach(item => {
    const key = item.slot + '|' + item.shift;
    if(!slotMap[key]){
      slotMap[key] = { slot: item.slot, shift: item.shift, groups: {} };
    }
    if(!slotMap[key].groups[item.category]){
      slotMap[key].groups[item.category] = [];
    }
    slotMap[key].groups[item.category].push({
      id: item.id,
      name: item.name,
      detail: item.detail || '',
      gender: item.gender || 'all',
      rounds: Array.isArray(item.rounds) ? item.rounds : [],   // 2b-1: 회차 멤버십 전달(itemRounds용)
      _custom: true
    });
  });

  // 배열로 변환
  return Object.values(slotMap).map(slot => ({
    slot: slot.slot,
    shift: slot.shift,
    groups: Object.entries(slot.groups).map(([title, items]) => ({
      title: title,
      items: items,
      _custom: true
    }))
  }));
}

/* 커스텀 항목을 WEEKDAY/WEEKEND 배열에 병합 (원본 변경 없이 합친 새 배열 반환) */
function mgmtMergeSchedule(baseSched, customSlots){
  if(!customSlots || customSlots.length === 0) return baseSched;

  // 깊은 복사
  const merged = baseSched.map(slot => ({
    slot: slot.slot,
    shift: slot.shift,
    groups: slot.groups.map(g => ({
      title: g.title,
      items: [...g.items]
    }))
  }));

  customSlots.forEach(cs => {
    // 같은 slot+shift 슬롯 찾기
    let existSlot = merged.find(s => s.slot === cs.slot && s.shift === cs.shift);
    if(!existSlot){
      // 없으면 새 슬롯 추가
      merged.push({
        slot: cs.slot,
        shift: cs.shift,
        groups: cs.groups.map(g => ({ title: g.title, items: [...g.items], _custom: true }))
      });
    } else {
      cs.groups.forEach(cg => {
        // 같은 카테고리 찾기
        let existGroup = existSlot.groups.find(g => g.title === cg.title);
        if(existGroup){
          // 기존 그룹에 항목 추가
          cg.items.forEach(item => existGroup.items.push(item));
        } else {
          // 새 그룹 추가
          existSlot.groups.push({ title: cg.title, items: [...cg.items], _custom: true });
        }
      });
    }
  });

  return merged;
}

/* 현재 스케줄에 커스텀 항목 반영 (이 함수를 getSched/getNightSched 래핑에 사용) */
function mgmtInjectCustomItems(){
  // 커스텀 항목이 변경될 때마다 현재 탭을 다시 그리기
  const tab = document.querySelector('.tab.active');
  if(!tab) return;
  const onclick = tab.getAttribute('onclick') || '';
  if(onclick.includes('check-m')) renderG('m');
  else if(onclick.includes('check-f')) renderG('f');
  else if(onclick.includes('admin')) renderAdmin();
}

/* getSched / getNightSched를 래핑하여 커스텀 항목 포함 */
const _origGetSched = getSched;
const _origGetNightSched = getNightSched;

/* 매뉴얼 셋업에서 숨긴(삭제한) 기본 항목 id (GM 2026-06-12). 추가항목(custom_)은 완전삭제, 기본항목은 숨김. */
function getHiddenIds(){ try{return new Set(JSON.parse(localStorage.getItem('wcheck_hidden_items')||'[]'))}catch(e){return new Set()} }
function saveHiddenIds(set){ localStorage.setItem('wcheck_hidden_items',JSON.stringify([...set])); }
/* 스케줄(기본 항목)에 매뉴얼 편집분(성별·이름·상세·회차) override 적용 + 숨김 항목 제거.
   custom_ 항목은 자체 필드 보유라 패스. 빈 그룹은 제거. */
function applyBaseOverrides(sched){
  if(!sched) return sched;
  const ov = (typeof getItemOverrides==='function')?getItemOverrides():{};
  const hidden = getHiddenIds();
  return sched.map(slot=>({
    slot:slot.slot, shift:slot.shift, _custom:slot._custom,
    groups: slot.groups.map(g=>({
      title:g.title, _custom:g._custom,
      items: g.items.filter(it=>!hidden.has(it.id)).map(it=>{
        if(it._custom) return it;
        const o=ov[it.id]; if(!o) return it;
        const m={...it};
        if(o.name) m.name=o.name;
        if(o.detail!==undefined) m.detail=o.detail;
        if(o.gender) m.gender=o.gender;          // 성별 편집 → 점검 표시 반영
        if(Array.isArray(o.rounds)&&o.rounds.length) m.rounds=o.rounds;  // 회차 편집 → 등장 조 반영
        return m;
      })
    })).filter(g=>g.items.length>0)
  })).filter(slot=>slot.groups.length>0);
}

getSched = function(ds){
  const base = _origGetSched(ds);
  if(!base) return null;
  const info = getDayInfo(ds);
  const schedType = info.type; // 'weekday' or 'weekend'
  const customItems = mgmtGetCustomItemsForSchedule(schedType).filter(i => i.shift !== 'night');
  const customSlots = mgmtBuildCustomSlots(customItems);
  return applyBaseOverrides(mgmtMergeSchedule(base, customSlots));
};

getNightSched = function(ds){
  const base = _origGetNightSched(ds);
  if(!base) return null;
  const info = getDayInfo(ds);
  const schedType = info.type;
  const customItems = mgmtGetCustomItemsForSchedule(schedType).filter(i => i.shift === 'night');
  const customSlots = mgmtBuildCustomSlots(customItems);
  return applyBaseOverrides(mgmtMergeSchedule(base, customSlots));
};

/* 커스텀 항목 표시 시 뱃지 추가를 위해 renderItem 래핑 */
const _origRenderItem = renderItem;
renderItem = function(it, shift, gender){
  let html = _origRenderItem(it, shift, gender);
  if(it._custom){
    // 항목명 뒤에 커스텀 뱃지 삽입
    html = html.replace('</label>', '<span class="mgmt-badge-custom">커스텀</span></label>');
  }
  return html;
};

/* 셋업 편집기 제거(GM 2026-06-12): 항목 추가=이슈승격 모달·점검 화면 빠른추가로 대체.
   아래 setupAttr는 점검 화면 빠른추가(quickAddBarHtml)가 공유하므로 보존(공유 데이터계층). */
/* onclick 속성용: HTML 따옴표(escapeAttr) + JS 작은따옴표/역슬래시 이스케이프 (시간대 라벨에 ' 포함 시 깨짐 방지) */
function setupAttr(s){ return escapeAttr(String(s)).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }

/* 초기 렌더링 */
renderManualItems();

;

/* ── 대시보드 고도화: 주간 트렌드·이슈대장 ── */
const DASH_API = API_URL;
const DASH_DEPT = 'support';
const DASH_DN = ['일','월','화','수','목','금','토'];

function dashEsc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function dashTodayStr(){const d=new Date();return d.getFullYear()+'-'+(''+(d.getMonth()+1)).padStart(2,'0')+'-'+(''+(d.getDate())).padStart(2,'0');}

async function renderAdminExtra(){
  renderWeekly();
  renderIssuelog();
}

async function renderWeekly(){
  const el=document.getElementById('weeklyView');
  if(!el)return;
  try{
    const r=await fetch(DASH_API+'?action=weekly&dept='+DASH_DEPT,{redirect:'follow'});
    const j=await r.json();
    const data=j.data||[];
    if(data.length===0){el.innerHTML='<div style="padding:14px;text-align:center;color:var(--green);font-size:13px;">주간 데이터 없음</div>';return;}
    const today=dashTodayStr();
    const maxPct=Math.max(...data.map(x=>x.pct),1);
    let html='<div style="display:flex;align-items:flex-end;gap:6px;height:110px;padding:6px 0 4px;overflow-x:auto;">';
    data.forEach(d=>{
      const isToday=d.date===today;
      const barH=Math.max(Math.round((d.pct/maxPct)*80),3);
      const dateLabel=d.date.slice(5).replace('-','/');
      const dayName=DASH_DN[new Date(d.date+'T00:00:00').getDay()];
      const pctColor=d.pct>=90?'var(--green)':d.pct>=60?'var(--yellow)':'var(--red)';
      html+=`<div style="display:flex;flex-direction:column;align-items:center;gap:3px;flex:1;min-width:34px;">
        <div style="font-size:10px;font-weight:700;color:${pctColor};">${d.pct}%</div>
        <div style="flex:1;width:100%;display:flex;align-items:flex-end;justify-content:center;">
          <div style="width:26px;height:${barH}px;border-radius:4px 4px 0 0;background:${isToday?'var(--green)':'var(--accent)'};min-height:3px;" title="${dashEsc(d.date+' '+d.pct+'% ('+d.done+'/'+d.total+')')}"></div>
        </div>
        <div style="font-size:10px;color:var(--dim);text-align:center;line-height:1.3;">${dateLabel}<br><span style="color:${isToday?'var(--green)':'var(--dim)'};">(${dayName})</span></div>
      </div>`;
    });
    html+='</div>';
    el.innerHTML=html;
  }catch(e){
    el.innerHTML='<div style="padding:12px;color:var(--red);font-size:13px;">주간 데이터 로드 실패</div>';
  }
}

async function renderIssuelog(){
  const el=document.getElementById('issuelogView');
  if(!el)return;
  try{
    const r=await fetch(DASH_API+'?action=issuelog&dept='+DASH_DEPT+'&open=1',{redirect:'follow'});
    const j=await r.json();
    const issues=j.issues||[];
    if(issues.length===0){
      el.innerHTML='<div class="admin-card" style="border-color:rgba(106,191,123,0.3);"><h3 style="color:var(--green);">미결 이슈 없음</h3><div style="font-size:13px;color:var(--dim);">모든 이슈가 처리되었습니다.</div></div>';
      return;
    }
    let html='<div style="overflow-x:auto;"><table class="dash-table"><tr><th>등록일</th><th>구역</th><th>점검자</th><th>이슈내용</th><th>상태</th><th>처리일</th></tr>';
    issues.forEach(iss=>{
      const sColor=iss.status==='미처리'?'var(--red)':iss.status==='처리중'?'var(--yellow)':'var(--green)';
      html+=`<tr><td>${dashEsc(iss.date)}</td><td>${dashEsc(iss.zone)}</td><td>${dashEsc(iss.inspector)}</td><td>${dashEsc(iss.issue)}</td><td style="color:${sColor};font-weight:700;">${dashEsc(iss.status)}</td><td>${dashEsc(iss.resolvedAt||'-')}</td></tr>`;
    });
    html+='</table></div>';
    el.innerHTML=html;
  }catch(e){
    el.innerHTML='<div style="padding:12px;color:var(--red);font-size:13px;">이슈대장 로드 실패</div>';
  }
}
