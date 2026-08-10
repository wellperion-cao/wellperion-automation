/** 웰페리온 매출·인건비 배관 (sales-api) — 2026-08-04 분리 신설
 *
 *  왜 떼어냈나:
 *    구매요청(지출품의)과 이 배관이 Apps Script 하나를 공유하고 있었다.
 *    매출 재계산은 월별 보고서 파일을 여럿 열어야 해서 수십 초가 걸리는데,
 *    그동안 같은 스크립트를 쓰는 구매요청의 가벼운 목록 조회까지 밀려
 *    간헐적으로 404·unauthorized 가 났다(2026-07-08 기록 → 2026-08-04 실측 확인).
 *    실행 컨텍스트를 분리해 '무거운 매출'이 '가벼운 구매요청'을 막지 못하게 한다.
 *
 *  담당 액션(읽기 전용 집계 + 인건비 정리 1건):
 *    무인증(공개 페이지용) : sales_dept_pub · sales_instr_pub   ← 운영부/PII 미반환
 *    비번 게이트           : sales_probe · sales_dept · sales_ops · sales_month
 *                            labor_time · labor_zero
 *
 *  ⚠ 지출품의(구매요청)·자산대장 액션은 여기 없다 — 그쪽은 procurement 프로젝트가 계속 담당한다.
 *  ⚠ 원본은 procurement.js 이며 함수 본문은 원문 그대로 옮겼다(동작 동일성 보장).
 */
var SALES_FOLDER = "1Yw-i6L9tWm-t7_sf2qEEih0nbC3fsjKC"; // 월별 매출 보고 폴더
var LABOR_MASTER_ID = "1uAmZXX0GbiDImORxEwnDFm4_C-r0W43s-_tV_cPq9lE"; // 인건비마스터(A부서 B강사) — 강사→종목 매핑 소스
var SALES_ALIAS = { "아쿠아":"수영", "루프 메소드":"루프매소드", "루프메소드":"루프매소드", "뮤지컬":"뮤지컬", "GXE":"GXE", "기타":"기타" }; // 강사가 아닌 직접 팀/프로그램 라벨
var PW = "wellperion!@1202"; // ※ procurement 와 동일 키 유지(프론트 무수정 이관). 속성 이관은 PROC_PW 정리와 함께 일괄 진행.

function _badPw(v){ return String(v) !== PW; }

function doGet(e){ return route((e && e.parameter) || {}); }
function doPost(e){
  var p = {};
  try { p = JSON.parse(e.postData.contents); } catch(err){ p = (e && e.parameter) || {}; }
  try { return route(p); }
  catch(err2){ console.error("[route]", p && p.action, String(err2)); return out({ ok:false, error:"server_error: " + String(err2) }); }
}
function route(p){
  // 공개(무인증) — 파트너팀 체계 등 게이트 없는 페이지용. 운영부·PII 는 반환하지 않는다.
  if (p.action === "sales_dept_pub")  return salesDeptPub(p);
  if (p.action === "sales_instr_pub") return salesInstrPub(p);
  if (_badPw(p.password)) return out({ ok:false, error:"unauthorized" });
  switch (p.action){
    case "sales_probe": return salesProbe(p);
    case "sales_dept":  return salesDept(p);
    case "sales_ops":   return salesOps(p);
    case "sales_month": return salesMonthTot(p);
    case "labor_time":  return laborTime(p);
    case "labor_zero":  return laborZero(p);
    case "ops_digest_write": return opsDigestWrite(p);
    case "ping":        return out({ ok:true, service:"sales-api", at:Utilities.formatDate(new Date(),"Asia/Seoul","yyyy-MM-dd HH:mm:ss") });
    default:            return out({ ok:false, error:"unknown action: " + p.action });
  }
}


function out(o){ return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

function fmtDate(v){
  if (Object.prototype.toString.call(v)==="[object Date]") return Utilities.formatDate(v,"Asia/Seoul","yyyy. M. d");
  return String(v||"");
}

function today(){ return Utilities.formatDate(new Date(),"Asia/Seoul","yyyy. M. d"); }

/** SWR 이중 캐시(2026-07-07 성능 수술): 신선 20분 + 보존 6시간.
 *  신선 만료 시 보존본을 즉시 반환(stale:true) → 클라이언트가 백그라운드 nocache 재계산 유발.
 *  콜드 재계산(월별 보고서 7파일 오픈, 최대 3분+)을 사용자가 직접 기다리는 일 제거. */
function swrGet_(p, key){
  if (p && p.nocache) return null;
  var c = CacheService.getScriptCache();
  var hit = c.get(key); if (hit) return JSON.parse(hit);
  var st = c.get(key + "_L"); if (st){ var o = JSON.parse(st); o.stale = true; return o; }
  return null;
}

function swrPut_(key, res){
  try{ var js = JSON.stringify(res); var c = CacheService.getScriptCache(); c.put(key, js, 1200); c.put(key + "_L", js, 21600); }catch(e){}
}

function salesFiles_(){ // {월번호: fileId} — 폴더 내 "YYYY년 N월 매출 보고" 자동 탐색(신규 월 파일 자동 인식)
  var year = Utilities.formatDate(new Date(),"Asia/Seoul","yyyy");
  var it = DriveApp.getFolderById(SALES_FOLDER).getFiles();
  var map = {};
  while (it.hasNext()){
    var f = it.next();
    var m = f.getName().match(new RegExp("^" + year + "년\\s*(\\d{1,2})월\\s*매출\\s*보고$"));
    if (m) map[parseInt(m[1],10)] = f.getId();
  }
  return map;
}

function salesProbe(p){ // 구조 점검용(임시): 월 파일의 탭 목록 + 지정 탭 O8:T74 원값(팀 집계 영역만, PII 없음)
  var mo = parseInt(p.month,10)||6;
  var files = salesFiles_();
  if (!files[mo]) return out({ ok:false, error:"no file for month "+mo, months:Object.keys(files) });
  var ss = SpreadsheetApp.openById(files[mo]);
  var names = ss.getSheets().map(function(s){ return s.getName(); });
  var grid = null, tab = String(p.tab||"");
  if (tab){
    var sht = ss.getSheetByName(tab);
    // 허용 영역 화이트리스트(PII 차단): 일자탭=팀 집계 O8:T80(기본)/월집계 블록 V60:AB90(win=monthly) / 집계탭('총 매출'류)=상단 집계표만
    var AGG = { "총 매출":"A1:P80", "총 매출(분류)":"A1:P80", "보고":"A1:P80" };
    var rng = AGG[tab] || (String(p.win||"") === "monthly" ? "V60:AB90" : "O8:T80");
    if (sht) grid = sht.getRange(rng).getDisplayValues();
  }
  return out({ ok:true, month:mo, tabs:names, tab:tab, grid:grid });
}

function nameKey_(s){ return String(s||"").replace(/\s+/g,"").replace(/프로$/,""); }

function laborDeptMap_(){ // 인건비마스터에서 강사명→종목 매핑 생성(소계·전체 제외)
  var v = SpreadsheetApp.openById(LABOR_MASTER_ID).getSheets()[0].getDataRange().getValues();
  var map = {};
  for (var i=0;i<v.length;i++){
    var dept = String(v[i][0]||""), name = String(v[i][1]||"");
    if (!dept || !name) continue;
    if (name.indexOf("소계")>=0 || dept.indexOf("전체")>=0) continue;
    map[nameKey_(name)] = dept;
  }
  return map;
}

function daysInMonth_(y, m){ return new Date(y, m, 0).getDate(); }

/** 말일탭(진행월=최신 데이터 탭) O8:T80 파싱 → {운영부, 종목별} 누적 매출.
 *  구조: 상단=멤버십 담당 블록('합계' 행 T=멤버십 누적) → '강습 매출' 헤더 → 강사별(T=누적) → '분류1' 헤더 → 옵션 블록(T 합=옵션 누적).
 *  운영부 = 멤버십 합계 + 옵션 합(6월 264,471,218 = GM시트와 일치 검증). 강사→종목은 인건비마스터 매핑. */
function parseSalesTab_(sht, dmap, unmapped){
  var g = sht.getRange(8, 15, 73, 6).getValues(); // O8:T80
  var section = "member"; // member → lesson → option
  var memberSum = 0, optionSum = 0, teams = {}, any = false;
  for (var i=0;i<g.length;i++){
    var label = String(g[i][0]||"").trim();
    var t = g[i][5]; t = (typeof t === "number") ? t : parseInt(String(t).replace(/[^0-9\-]/g,""),10);
    if (isNaN(t)) t = 0;
    if (label.indexOf("강습 매출")>=0){ section = "lesson"; continue; }
    if (label.indexOf("분류1")>=0){ section = "option"; continue; }
    if (!label) continue;
    if (section === "member"){
      if (label === "합계"){ memberSum = t; if(t) any = true; }
    } else if (section === "lesson"){
      if (label === "담당" || label === "정회원") continue; // 헤더행
      var team = SALES_ALIAS[label] || dmap[nameKey_(label)];
      if (team){ teams[team] = (teams[team]||0) + t; if(t) any = true; }
      else if (t) { unmapped[label] = (unmapped[label]||0) + t; teams["기타"] = (teams["기타"]||0) + t; any = true; } // 미매핑도 총액 보존(기타)
    } else { // option
      optionSum += t; if(t) any = true;
    }
  }
  if (!any) return null; // 빈 탭(데이터 미기입)
  teams["운영부"] = memberSum + optionSum;
  return teams;
}

/** 매출 종목별×월별 라이브 — 월 파일 자동탐색·말일(최신)탭 파싱·20분 캐시. 값 없는 월은 null(프론트가 기존값 유지 병합). */
function salesDept(p){ return out(salesDeptCompute_(p)); }

/** 공개 강습 팀집계(무인증) — 강습부 대시보드(공개 페이지) 전용. salesDept 결과에서 운영부(회원권 개인매출 집계) 제외, 강습 종목만 반환.
 *  PII 없음(팀 집계). 이 데이터는 강습부 매출 시트가 이미 CSV로 공개 중인 수준 → 노출 증가 없음. 캐시(sales_dept_v1) 공유. */
function salesDeptPub(p){
  var res = salesDeptCompute_(p);
  if (!res || !res.dept) return out({ ok:false, error:"no_data" });
  var pub = {};
  for (var k in res.dept){ if (k === "운영부") continue; pub[k] = res.dept[k]; } // 회원권(운영부) 제외 → 강습 종목만
  return out({ ok:true, dept:pub, monthsLoaded:res.monthsLoaded, src:res.src, at:res.at, stale:res.stale || false });
}

/** 공개 강사별 매출(무인증) — 파트너팀 페이지 강사별 실시간. 진행월(최신 데이터 탭) O8:T80에서 6팀 강사별 실적만 반환.
 *  매니저 승인(2026-07-14): 이 공개페이지는 강습부 시트로 6월까지 강사별을 이미 공개 중 → 노출 증가 없음.
 *  최소노출: 6팀 종목 실제 강사만(프로그램 라벨 아쿠아/뮤지컬/GXE 등 제외·미매핑 제외·매출>0). 진행월 1탭만 파싱(경량). SWR 캐시(20분+6시간). */
/** 공개 강사별(무인증·6팀). `month`(1~12) 지정 시 그 달, 없으면 진행월 — 2026-08-04 확장.
 *  확장 이유: 이전엔 진행월만 반환해서, 달이 바뀌면 지난달 강사별이 '강습부 시트에 입력될 때까지'
 *  빈 채로 남았다(7월 사례). 원천인 매출보고서엔 월별 강사 실적이 이미 다 있으므로 아무 달이나 읽는다.
 *  강습부 시트 입력을 기다리지 않는다 — 이 페이지는 강사분들에게 공개되는 화면이다. */
function salesInstrPub(p){
  var now = new Date();
  var year = parseInt(Utilities.formatDate(now,"Asia/Seoul","yyyy"),10);
  var curMo = parseInt(Utilities.formatDate(now,"Asia/Seoul","M"),10);
  var curDay = parseInt(Utilities.formatDate(now,"Asia/Seoul","d"),10);
  var want = parseInt((p && p.month), 10);
  if (!(want >= 1 && want <= 12)) want = curMo; // 기본 = 진행월(기존 호출 동작 그대로)
  if (want > curMo) return out({ ok:true, month:0, instr:[], note:"future_month" }); // 미래월은 조회 안 함
  var ckey = "sales_instr_v2_" + want; // 월별 캐시 분리(구 sales_instr_v1 키는 미사용)
  var hit = swrGet_(p, ckey); if (hit) return out(hit);
  var files = salesFiles_();
  var dmap = laborDeptMap_();
  var SIX = { "수영":1, "P.T":1, "필라테스":1, "골프":1, "스쿼시":1, "체조&트램":1 };
  var month = 0, instr = [];
  if (files[want]){
    var ss = SpreadsheetApp.openById(files[want]);
    // 지난달은 말일부터, 진행월은 오늘부터 역방향 — 값이 있는 첫 일자탭이 그 달의 누계다.
    var startDay = (want === curMo) ? Math.min(curDay, daysInMonth_(year, want)) : daysInMonth_(year, want);
    for (var d=startDay; d>=1; d--){
      var sht = ss.getSheetByName(String(d));
      if (!sht) continue;
      var rows = parseInstrList_(sht, dmap, SIX);
      if (rows && rows.length){ instr = rows; month = want; break; }
    }
  }
  var res = { ok:true, month:month, instr:instr, at:Utilities.formatDate(now,"Asia/Seoul","yyyy-MM-dd HH:mm") };
  swrPut_(ckey, res);
  return out(res);
}

/** O8:T80 강사별 리스트 [{name,team,val}] — 6팀 종목 실제 강사만(프로그램 라벨·미매핑·0/음수 제외). */
function parseInstrList_(sht, dmap, six){
  var g = sht.getRange(8, 15, 73, 6).getValues(); // O8:T80
  var section = "member", res = [];
  for (var i=0;i<g.length;i++){
    var label = String(g[i][0]||"").trim();
    var t = g[i][5]; t = (typeof t === "number") ? t : parseInt(String(t).replace(/[^0-9\-]/g,""),10);
    if (isNaN(t)) t = 0;
    if (label.indexOf("강습 매출")>=0){ section = "lesson"; continue; }
    if (label.indexOf("분류1")>=0){ section = "option"; continue; }
    if (!label) continue;
    if (section === "lesson"){
      if (label === "담당" || label === "정회원") continue;
      if (SALES_ALIAS[label]) continue; // 프로그램 라벨(아쿠아/뮤지컬/GXE 등)은 개인 강사 아님 → 제외
      var team = dmap[nameKey_(label)];
      if (team && six[team] && t > 0){ res.push({ name:label, team:team, val:t }); }
    }
  }
  return res;
}

function salesDeptCompute_(p){
  var hit = swrGet_(p, "sales_dept_v1"); if (hit) return hit;
  var now = new Date();
  var year = parseInt(Utilities.formatDate(now,"Asia/Seoul","yyyy"),10);
  var curMo = parseInt(Utilities.formatDate(now,"Asia/Seoul","M"),10);
  var curDay = parseInt(Utilities.formatDate(now,"Asia/Seoul","d"),10);
  var files = salesFiles_();
  var dmap = laborDeptMap_();
  var dept = {}, monthsLoaded = [], unmapped = {}, src = {};
  for (var m=1;m<=12;m++){
    if (!files[m]) continue;
    var ss = SpreadsheetApp.openById(files[m]);
    var startDay = (m === curMo) ? Math.min(curDay, daysInMonth_(year, m)) : daysInMonth_(year, m);
    var teams = null, usedTab = "";
    for (var d=startDay; d>=1; d--){ // 최신 일자 탭부터 역방향 — 데이터 있는 첫 탭 채택
      var sht = ss.getSheetByName(String(d));
      if (!sht) continue;
      teams = parseSalesTab_(sht, dmap, unmapped);
      if (teams){ usedTab = String(d); break; }
      if (m !== curMo) break; // 마감월은 말일탭 1회만(빈탭 역주행은 진행월 한정)
    }
    if (!teams) continue;
    for (var k in teams){
      if (!dept[k]) dept[k] = [null,null,null,null,null,null,null,null,null,null,null,null];
      dept[k][m-1] = teams[k];
    }
    monthsLoaded.push(m); src[m] = usedTab;
  }
  var res = { ok:true, dept:dept, monthsLoaded:monthsLoaded, src:src, unmapped:Object.keys(unmapped), at:Utilities.formatDate(now,"Asia/Seoul","yyyy-MM-dd HH:mm") };
  swrPut_("sales_dept_v1", res);
  return res;
}

/** 운영부(회원권) 매출 정밀 — 월별 매출보고 「총 매출」 탭 '합계'행 서버 집계(★환불 차감 반영, 매니저 지시 2026-07-07).
 *  컬럼: B신규 D재등록 F양도 H환불(괄호음수) J옵션 N합계매출(=신규+재등+양도+환불+옵션, 굿즈·카드 제외 — 시트 산식 그대로 신뢰).
 *  반환: 월별 net(합계매출)·refund(환불)·gross(환불 전). 집계만 반환(PII 없음)·20분 캐시. GM시트 대체 정본(대시보드 운영부 소스). */
function salesOps(p){
  var hit = swrGet_(p, "sales_ops_v1"); if (hit) return out(hit);
  var files = salesFiles_();
  var net=[], refund=[], gross=[], monthsLoaded=[];
  for (var i=0;i<12;i++){ net.push(null); refund.push(null); gross.push(null); }
  function pnum(s){ s=String(s==null?"":s).trim(); if(!s) return 0; var neg=/^\(.*\)$/.test(s); s=s.replace(/[(),\s원]/g,""); var v=parseInt(s,10); if(isNaN(v)) return 0; return neg? -v : v; }
  for (var m=1;m<=12;m++){
    if (!files[m]) continue;
    var sht = SpreadsheetApp.openById(files[m]).getSheetByName("총 매출");
    if (!sht) continue;
    var g = sht.getRange(1,1,Math.min(sht.getLastRow(),60),14).getDisplayValues();
    for (var r=0;r<g.length;r++){
      if (String(g[r][0]).trim() !== "합계") continue;
      var sin=pnum(g[r][1]), jae=pnum(g[r][3]), yang=pnum(g[r][5]), hwan=pnum(g[r][7]), opt=pnum(g[r][9]);
      var hap=pnum(g[r][13]);
      var gr = sin+jae+yang+opt;
      net[m-1] = hap || (gr + hwan); // 시트 합계열 우선, 비면 구성요소 재계산
      refund[m-1] = hwan; gross[m-1] = gr;
      monthsLoaded.push(m);
      break;
    }
  }
  var res = { ok:true, net:net, refund:refund, gross:gross, monthsLoaded:monthsLoaded, at:Utilities.formatDate(new Date(),"Asia/Seoul","yyyy-MM-dd HH:mm") };
  swrPut_("sales_ops_v1", res);
  return out(res);
}

/** 월 총매출 정본 — 월별 매출보고 말일탭 Y70:Y80 월 집계 블록(★매니저 확인 2026-07-07 "제일 정확한 매출").
 *  Y70=멤버십(환불반영) · Y71~79=종목별 · Y80=강습 합계. 총매출 = Y70+Y80. 31탭부터 역방향으로 값 있는 첫 탭 채택(진행월 대응).
 *  집계만 반환(PII 없음)·20분 캐시. 대시보드 총매출 1순위 소스. */
function salesMonthTot(p){
  var hit = swrGet_(p, "sales_month_v1"); if (hit) return out(hit);
  var files = salesFiles_();
  var member=[], lessons=[], total=[], monthsLoaded=[], src={};
  for (var i=0;i<12;i++){ member.push(null); lessons.push(null); total.push(null); }
  function ynum(s){ s=String(s==null?"":s); var neg=/\(/.test(s); var v=parseInt(s.replace(/[^0-9]/g,""),10); if(isNaN(v)) return 0; return neg? -v : v; }
  for (var m=1;m<=12;m++){
    if (!files[m]) continue;
    var ss = SpreadsheetApp.openById(files[m]);
    for (var d=31; d>=1; d--){
      var sht = ss.getSheetByName(String(d));
      if (!sht) continue;
      var g = sht.getRange("Y70:Y80").getDisplayValues();
      var mem = ynum(g[0][0]), les = ynum(g[10][0]);
      if (!mem && !les) continue; // 빈 탭 → 이전 일자 탭으로
      member[m-1]=mem; lessons[m-1]=les; total[m-1]=mem+les; src[m]=d; monthsLoaded.push(m);
      break;
    }
  }
  var res = { ok:true, member:member, lessons:lessons, total:total, monthsLoaded:monthsLoaded, src:src, at:Utilities.formatDate(new Date(),"Asia/Seoul","yyyy-MM-dd HH:mm") };
  swrPut_("sales_month_v1", res);
  return out(res);
}

/** 타임(시급) 인건비 라이브 — 월별 매출보고 '타임직원' 탭(G.X 및 타임 페이롤)의 블록별 '지급액 합계'(H열) 서버 집계.
 *  라이프가드 등 시급 인력 = 인건비마스터 밖의 실지출(매니저님 확인 2026-07-04). 집계만 반환(PII 비반환)·20분 캐시.
 *  함정 처리: 블록 부서/시간 칸에 적힌 날짜의 월이 파일 월과 다르면 템플릿 잔재로 보고 제외(예: 6·7월 탭에 반복된 '2/22 휴관일' 168,000). */
function laborTime(p){
  var hit = swrGet_(p, "labor_time_v1"); if (hit) return out(hit);
  var files = salesFiles_();
  var swim = [], other = [], skipped = {};
  for (var i=0;i<12;i++){ swim.push(null); other.push(null); }
  for (var m=1;m<=12;m++){
    if (!files[m]) continue;
    var sht = SpreadsheetApp.openById(files[m]).getSheetByName("타임직원");
    if (!sht) continue;
    var g = sht.getRange(1, 1, Math.min(sht.getLastRow(), 120), 8).getValues();
    var curDept = "", curSkip = false, sw = 0, ot = 0, sk = 0, any = false;
    for (var r=0;r<g.length;r++){
      var a = String(g[r][0]||"").trim(), b = String(g[r][1]||"").trim(), c = String(g[r][2]||"").trim(), d = String(g[r][3]||"").trim();
      if (a && a !== "구분" && !isNaN(parseInt(a,10))){ // 블록 시작(구분 번호)
        curDept = c;
        var dm2 = (c+" "+d).match(/(?:2\d\.\s*(\d{1,2})\.)|(?:(\d{1,2})\s*\/\s*\d{1,2})/); // '26.2.22' 또는 '2/22'
        var bm = dm2 ? parseInt(dm2[1]||dm2[2],10) : 0;
        curSkip = (bm >= 1 && bm <= 12 && bm !== m);
      }
      if (b.indexOf("지급액 합계") >= 0){
        var amt = g[r][7]; amt = (typeof amt === "number") ? amt : parseInt(String(amt).replace(/[^0-9\-]/g,""),10);
        if (isNaN(amt) || !amt) continue;
        any = true;
        if (curSkip){ sk += amt; }
        else if (/수영|가드|아쿠아/.test(curDept)){ sw += amt; }
        else { ot += amt; }
      }
    }
    if (any || sw || ot){ swim[m-1] = sw; other[m-1] = ot; if (sk) skipped[m] = sk; }
  }
  var res = { ok:true, swim:swim, other:other, skipped:skipped, at:Utilities.formatDate(new Date(),"Asia/Seoul","yyyy-MM-dd HH:mm") };
  swrPut_("labor_time_v1", res);
  return out(res);
}

/** 퇴사자 지급 정리 — 인건비마스터 해당 강사 행의 from월~12월을 0 고정(수식 잔재·선입력 제거, 이전 지급내역 보존).
 *  adminPassword 필수 · 대상 시트=인건비마스터 한정 · before 반환(감사 로그용). */
function laborZero(p){
  if (_badPw(p.adminPassword)) return out({ ok:false });
  var name = String(p.name||"").replace(/\s+/g,"");
  var from = parseInt(p.from,10);
  if (!name || !(from>=1 && from<=12)) return out({ ok:false, error:"name/from" });
  var sheet = SpreadsheetApp.openById(LABOR_MASTER_ID).getSheets()[0];
  var lr = sheet.getLastRow();
  var names = sheet.getRange(1, 2, lr, 1).getValues();
  var row = 0;
  for (var i=0;i<names.length;i++){ if (String(names[i][0]).replace(/\s+/g,"") === name){ row = i+1; break; } }
  if (!row) return out({ ok:false, error:"not_found" });
  var rng = sheet.getRange(row, 2+from, 1, 13-from); // m월=열(2+m): from월~12월
  var before = rng.getValues()[0];
  var zeros = [];
  for (var m=from; m<=12; m++) zeros.push(0);
  rng.setValues([zeros]);
  return out({ ok:true, row:row, name:String(p.name), from:from, before:before });
}

/** 운영 현황 한눈에 — 매출 보고 시트에 인사&파트너팀·핵심 업무·시설/지원/주차 요약을
 *  자동으로 얹는 단일 쓰기 액션(2026-08-10 GM 승인). 판정·집계는 여기서 하지 않는다 —
 *  이미 매일 만들어지는 텍스트(text)를 받아 그대로 덮어쓸 뿐이다.
 *  대상 = 이번달 매출 보고 파일의 "운영 현황 한눈에" 탭(없으면 새로 만듦) — 이 탭 하나만
 *  지우고 다시 쓴다. 다른 탭(특히 '보고' 탭 H2:S21 — 매일 회장님께 가는 이미지 원본)은
 *  절대 열지도 않는다. 같은 요청 안에서 재조회한 값도 같이 돌려줘 "성공 응답"만으로
 *  끝내지 않는다(GM 지시). */
function opsDigestWrite(p){
  var text = String(p.text||"");
  if (!text) return out({ ok:false, error:"text 비어있음" });
  var files = salesFiles_();
  var curMo = parseInt(Utilities.formatDate(new Date(),"Asia/Seoul","M"),10);
  var fid = files[curMo];
  if (!fid) return out({ ok:false, error:"이번달(" + curMo + "월) 매출 보고 파일을 못 찾음", months:Object.keys(files) });
  var who = "";
  try { who = Session.getEffectiveUser().getEmail(); } catch(e){}
  var ss = SpreadsheetApp.openById(fid);
  var TAB = "운영 현황 한눈에";
  var sh = ss.getSheetByName(TAB);
  if (!sh){ sh = ss.insertSheet(TAB); sh.setColumnWidth(1, 640); }
  else { sh.clear(); } // 이 탭만 지운다 — 다른 탭은 절대 건드리지 않음
  var lines = text.split("\n");
  sh.getRange(1, 1, lines.length, 1).setValues(lines.map(function(l){ return [l]; }));
  var stamp = Utilities.formatDate(new Date(),"Asia/Seoul","yyyy-MM-dd HH:mm");
  var readback = sh.getRange(1, 1, lines.length, 1).getDisplayValues().map(function(r){ return r[0]; });
  var verified = readback.join("\n") === text;
  return out({ ok:true, month:curMo, tab:TAB, rows:lines.length, at:stamp, verified:verified, execUser:who });
}

/** 최초 1회 권한 승인용 — Apps Script 편집기에서 이 함수를 실행하면
 *  이 프로젝트가 쓰는 권한(스프레드시트·드라이브)을 구글이 한 번 물어본다.
 *  승인해야 웹앱(/exec)이 외부에 응답한다. 이후로는 다시 실행할 필요 없다. */
function authorize(){
  var n = 0;
  try { n = DriveApp.getFolderById(SALES_FOLDER).getName().length; } catch(e){}
  try { n += SpreadsheetApp.openById(LABOR_MASTER_ID).getName().length; } catch(e){}
  Logger.log("권한 승인 완료 (확인값 " + n + ") — 이제 웹앱이 응답합니다.");
  return "OK";
}
