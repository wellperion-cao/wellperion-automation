/** 웰페리온 지출품의 백엔드 — 시트 '지출품의' 탭 읽기/쓰기 (품의·검토·집행·정산·영수증)
 * 시트: 1. 웰페리온 지출 관리 및 현황
 * 컬럼(1-base): 1날짜 2타임 3요청자 4소속 5물품 6링크 7가격 8목적 9승인자 10비고 11이미지 12진행상황 13승인날짜 14배송 15지출증빙 16항목1 17항목2
 */
var SHEET_ID = "1umSF9rf3K0TuAvR5l0F_gvXHxcOLVKKvkSUfTtbRhdc";
var TAB = "지출품의";
var PW = "wellperion!@1202";
var RECEIPT_FOLDER = "1WmKrK4cbbZWLluozwkLi_RslGeRL1Vqa"; // cfo ▸ 구매요청 사진백업 폴더(첨부·영수증 원본, 2026-07-04 매니저님 지시로 분리)
var FIRST_ROW = 3; // 헤더 2행, 데이터 3행부터 (배포 후 실데이터로 검증·보정)
var REVIEW_SHEET_ID = "1rUjnf_oxVTnT89B1aU46Z2txYc8k_MdKYdwhulpgw48"; // 검토결과 시트(별도·cao 소유)

function doGet(e){ return route((e && e.parameter) || {}); }
function doPost(e){
  var p = {};
  try { p = JSON.parse(e.postData.contents); } catch(err){ p = (e && e.parameter) || {}; }
  return route(p);
}
function route(p){
  if (p.action === "lowprice_set") return lowpriceSet(p); // 검토결과 쓰기(별도 시트·adminPassword) — 기존 게이트 앞 분기
  if (p.action === "lowprice_del") return lowpriceDel(p); // 검토결과 행삭제(별도 시트·adminPassword) — 기존 게이트 앞 분기
  if (p.action === "diag_naver") return diagNaver(p);     // 임시 진단: GAS→네이버 UrlFetchApp 가능 여부·스코프 확인
  if (String(p.password) !== PW) return out({ ok:false, error:"unauthorized" });
  switch (p.action){
    case "list":    return listItems(p);
    case "add":     return addItem(p);
    case "status":  return setStatus(p);
    case "setno":   return setNo(p);
    case "setdate": return setDate(p);
    case "proc_summary": return procSummary(p);
    case "sales_probe": return salesProbe(p);
    case "sales_dept": return salesDept(p);
    case "labor_zero": return laborZero(p);
    case "labor_time": return laborTime(p);
    case "receipt": return addReceipt(p);
    case "photo":   return addPhoto(p);
    case "delete":  return delRow(p);
    default:        return out({ ok:false, error:"unknown action: " + p.action });
  }
}
function sh(){ return SpreadsheetApp.openById(SHEET_ID).getSheetByName(TAB); }
function out(o){ return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function today(){ return Utilities.formatDate(new Date(),"Asia/Seoul","yyyy. M. d"); }

function fmtDate(v){
  if (Object.prototype.toString.call(v)==="[object Date]") return Utilities.formatDate(v,"Asia/Seoul","yyyy. M. d");
  return String(v||"");
}
function driveThumb(s){
  if (s.indexOf("http")!==0) return "";
  if (s.indexOf("google.com")>=0){
    var m = s.match(/\/d\/([-\w]+)/) || s.match(/[?&]id=([-\w]+)/);
    if (m) return "https://drive.google.com/uc?export=view&id="+m[1]; // 공개파일 <img> 로드(200 image)
  }
  return s;
}
function extractImage(cell, formula){
  if (cell && typeof cell.getContentUrl === "function"){ // 기존 셀 내장 이미지 → 시트 호스팅 URL
    try { var cu = cell.getContentUrl(); if (cu) return cu; } catch(e){}
    try { var u = cell.getUrl(); if (u) return driveThumb(u); } catch(e){}
  }
  var s = String(cell||"");
  if (s.indexOf("data:image")===0) return s; // base64 썸네일(신규 업로드)
  if (formula){ var m = formula.match(/IMAGE\("([^"]+)"/i); if (m) return driveThumb(m[1]); }
  return driveThumb(s);
}
function putPhoto(s, row, p){ // 원본→드라이브(백업), 썸네일 base64→이미지 열(외부 의존 없이 표시)
  var blob = Utilities.newBlob(Utilities.base64Decode(p.fileData), p.mimeType||"image/jpeg", p.fileName||("photo_"+row));
  var f = DriveApp.getFolderById(RECEIPT_FOLDER).createFile(blob);
  try { f.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW); } catch(e){}
  var thumb = p.thumb || p.fileData; // 썸네일 base64(없으면 원본)
  var mime = p.thumbMime || p.mimeType || "image/jpeg";
  s.getRange(row, 11).setValue("data:"+mime+";base64,"+thumb); // data URI
  return f.getUrl();
}
function dateNum(s){
  var m = String(s||"").match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  return m ? (parseInt(m[1],10)*10000 + parseInt(m[2],10)*100 + parseInt(m[3],10)) : 0;
}
function listItems(p){
  p = p || {};
  var mode = p.mode || "active"; // active=품의/검토/정산(미완료), done=그 외(완료/승인 등, 기간필터)
  var ACTIVE = {"품의":1,"검토":1,"정산":1};
  var s = sh(); var lr = s.getLastRow();
  if (lr < FIRST_ROW) return out({ ok:true, count:0, data:[] });
  var v = s.getRange(FIRST_ROW, 1, lr - FIRST_ROW + 1, 17).getValues();
  var fm = s.getRange(FIRST_ROW, 11, lr - FIRST_ROW + 1, 1).getFormulas(); // 이미지열 =IMAGE 수식
  var lc = s.getLastColumn();
  var nos = lc >= 25 ? s.getRange(FIRST_ROW, 25, lr - FIRST_ROW + 1, 1).getValues() : null; // 번호열(25)
  var fromN = p.from ? dateNum(p.from) : 0, toN = p.to ? dateNum(p.to) : 0;
  var data = [];
  for (var i=0;i<v.length;i++){
    var r = v[i];
    if (!r[2]) continue; // 요청자 없으면 빈행
    var st = r[11] || "품의";
    if (mode === "active"){ if (!ACTIVE[st]) continue; }
    else { // done: 미완료 제외 + 기간필터
      if (ACTIVE[st]) continue;
      if (fromN || toN){ var dn = dateNum(fmtDate(r[0])); if (fromN && dn < fromN) continue; if (toN && dn > toN) continue; }
    }
    data.push({
      row: FIRST_ROW + i,
      날짜: fmtDate(r[0]), 요청자: r[2], 소속: r[3], 물품: r[4], 링크: r[5],
      가격: r[6], 목적: r[7], 승인자: r[8], 이미지: extractImage(r[10], fm[i][0]), 상태: st,
      승인날짜: fmtDate(r[12]), 지출증빙: driveThumb(String(r[14]||"")), 항목1: r[15], 항목2: r[16],
      번호: nos ? nos[i][0] : ""
    });
  }
  return out({ ok:true, count:data.length, mode:mode, data:data });
}

function addItem(p){
  var s = sh();
  var now = new Date();
  var ts = Utilities.formatDate(now,"Asia/Seoul","yyyy. M. d a h:mm:ss");
  // 컬럼순 채워서 append: 날짜,타임,요청자,소속,물품,링크,가격,목적,승인자,비고,이미지,진행상황
  s.appendRow([ today(), ts, p.요청자||"", p.소속||"", p.물품||"", p.링크||"",
                p.가격||"", p.목적||"", p.승인자||"", p.비고||"", "", "품의",
                "", "", "", p.항목1||"", p.항목2||"" ]); // 13승인날짜 14배송 15증빙 16항목1 17항목2
  var row = s.getLastRow();
  // 고정 일련번호(신규부터) — 25열에 저장, 행 삭제돼도 불변
  var lr0 = s.getLastRow();
  var nos = s.getRange(FIRST_ROW, 25, Math.max(1, lr0 - FIRST_ROW + 1), 1).getValues();
  var mx = 0; for (var k=0;k<nos.length;k++){ var x=parseInt(String(nos[k][0]).replace(/[^0-9]/g,''),10); if(x>mx) mx=x; }
  var no = mx + 1;
  s.getRange(row, 25).setValue(no);
  if (p.fileData) putPhoto(s, row, p); // 품의 첨부사진 → 이미지 열(=IMAGE 썸네일)
  var instant = null;
  try { instant = instantLowprice_(row, p.물품||"", p.가격||""); } catch(e){ instant = { ok:false, error:String(e) }; } // 제출즉시 최저가(실패해도 품의는 성공)
  return out({ ok:true, no:no, instant:instant });
}

/** 제출 즉시 최저가 조사 — 네이버 쇼핑 검색(가격 낮은순 1건) → 검토시트 upsert.
 *  키(Script Properties NAVER_CLIENT_ID/SECRET) 없으면 안전하게 skip. 단순검색이라 신뢰도 '하(참고)' → 9시 cron 에이전트가 보완(2단 구조).
 */
function instantLowprice_(row, 물품, 가격){
  var props = PropertiesService.getScriptProperties();
  var cid = props.getProperty("NAVER_CLIENT_ID"), csec = props.getProperty("NAVER_CLIENT_SECRET");
  if (!cid || !csec) return { ok:false, skipped:"no_api_key" }; // 키 미설정 → 조사 생략(기존 동작 유지)
  var q = searchQuery_(물품);
  if (!q) return { ok:false, skipped:"no_query" };
  // sort=sim(정확도순)·display=10 → 관련상품 풀 확보. (sort=asc는 검색어 무관 초저가 부속품이 1위로 튀어 오르는 함정)
  var url = "https://openapi.naver.com/v1/search/shop.json?display=10&sort=sim&query=" + encodeURIComponent(q);
  var res = UrlFetchApp.fetch(url, {
    method:"get", muteHttpExceptions:true,
    headers:{ "X-Naver-Client-Id":cid, "X-Naver-Client-Secret":csec }
  });
  if (res.getResponseCode() !== 200) return { ok:false, error:"naver_" + res.getResponseCode() };
  var items = (JSON.parse(res.getContentText()).items) || [];
  var price = parseInt(String(가격).replace(/[^0-9]/g,""), 10) || 0;
  var 검토일 = today();
  if (!items.length){ // 검색결과 없음 → '검색결과없음'으로 기록(배지에 '시세 미확인' 노출)
    reviewUpsert_(row, [물품||"", "", "", "", price||"", "", "하", 검토일, "자동·네이버쇼핑 제출즉시·검색결과없음 → 모델명 보완요"]);
    return { ok:true, found:0 };
  }
  // 관련성 필터: 검색어 핵심토큰(2자+)이 제목에 모두 포함된 결과군 → 그중 최저가. 매칭 없으면 sim 1위(대표상품) fallback.
  var toks = q.split(/\s+/).filter(function(t){ return t.length >= 2; });
  var cands = items.filter(function(it){
    var t = String(it.title||"").replace(/<[^>]+>/g,"");
    return toks.length ? toks.every(function(k){ return t.indexOf(k) >= 0; }) : true;
  });
  var matched = cands.length > 0;
  var pool = matched ? cands : items.slice(0, 1); // 매칭군 중 최저가 / 없으면 가장 관련성 높은 sim 1위
  var picked = pool.reduce(function(a, b){
    return (parseInt(a.lprice,10) || 1e15) <= (parseInt(b.lprice,10) || 1e15) ? a : b;
  });
  var name = String(picked.title||"").replace(/<[^>]+>/g,""); // <b> 태그 제거
  var low = parseInt(picked.lprice, 10) || 0;
  var mall = picked.mallName || "";
  var link = picked.link || "";
  var 대비 = "";
  if (price && low){
    var diff = price - low; // 품의가 - 최저가 (>0=품의가가 비쌈=절감기회 / <0=품의가가 더 쌈=적정)
    if (diff > 0) 대비 = comma_(diff) + "원 비쌈";
    else if (diff < 0) 대비 = comma_(Math.abs(diff)) + "원 쌈";
    else 대비 = "동일";
  } else if (!price) {
    대비 = "가격 입력 요망";
  }
  var 비고 = "자동·네이버쇼핑 제출즉시(참고시세) · 9시 보완예정" + (matched ? "" : " · ⚠관련성낮음(모델명 보완요)") + (mall ? " · "+mall : "");
  // B품의물품 C동일제품 D최저가 E판매처링크 F품의가 G품의가대비 H신뢰도 I검토일 J비고
  reviewUpsert_(row, [물품||"", name, low||"", link, price||"", 대비, "하", 검토일, 비고]);
  return { ok:true, found:1, matched:matched, low:low, name:name };
}

function comma_(n){ return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); } // 천단위 콤마(로케일 무관)

// 권한 동의 강제용: try 없이 UrlFetchApp 직접 호출 → 미동의 시 편집기 실행에서 '권한 검토' 모달이 강제로 뜸. 1회 허용 후 재배포하면 web app 반영.
function authConsent(){
  var r = UrlFetchApp.fetch("https://openapi.naver.com/v1/search/shop.json?display=1&query=test", { muteHttpExceptions:true });
  return r.getResponseCode();
}

// 임시 진단: GAS 런타임에서 네이버 쇼핑 API 호출이 되는지(스코프·연결) 확인. 키는 스크립트 속성서.
function diagNaver(p){
  var t0 = new Date().getTime();
  try {
    var props = PropertiesService.getScriptProperties();
    var cid = props.getProperty("NAVER_CLIENT_ID"), csec = props.getProperty("NAVER_CLIENT_SECRET");
    if (!cid || !csec) return out({ ok:false, stage:"props", msg:"키 미설정", hasId:!!cid, hasSecret:!!csec });
    var res = UrlFetchApp.fetch("https://openapi.naver.com/v1/search/shop.json?display=1&query=test", {
      method:"get", muteHttpExceptions:true,
      headers:{ "X-Naver-Client-Id":cid, "X-Naver-Client-Secret":csec }
    });
    var ms = new Date().getTime() - t0;
    return out({ ok:true, stage:"fetched", code:res.getResponseCode(), len:res.getContentText().length, ms:ms });
  } catch(e){
    var ms2 = new Date().getTime() - t0;
    return out({ ok:false, stage:"exception", error:String(e), ms:ms2 });
  }
}

/** 물품명 → 검색어: 끝의 수량·단위·괄호 제거(대시보드 검색칩과 동일 취지). 예 "명상방석 10개" → "명상방석" */
function searchQuery_(물품){
  var s = String(물품||"").trim();
  if (!s) return "";
  s = s.replace(/\([^)]*\)/g, " ");                       // 괄호 보충설명 제거
  s = s.replace(/\s*[xX×*]\s*\d+\s*$/,"");                 // 끝의 "x N"
  s = s.replace(/\s*\d+\s*(개|매|팩|박스|세트|set|ea|EA|장|구|병|통|kg|g|ml|L|리터|묶음|쌍|족|벌)\s*$/,""); // 끝 수량+단위
  s = s.replace(/\s{2,}/g," ").trim();
  return s;
}

function setStatus(p){
  var row = parseInt(p.row,10); if(!row) return out({ ok:false, error:"no row" });
  var s = sh();
  s.getRange(row, 12).setValue(p.status||""); // 진행상황: 품의 → 검토 → 정산 → 완료
  if (p.status === "검토") s.getRange(row, 13).setValue(today()); // 승인날짜(승인자 승인 시점)
  return out({ ok:true });
}

// 고정 일련번호(#) 수동 설정 — 25열만 기록(다른 열 무변경). 별도 양식으로 들어와 #이 빈 행 보정용. password 게이트(switch 진입 전 검증).
function setNo(p){
  var row = parseInt(p.row,10); if(!row) return out({ ok:false, error:"no row" });
  var no  = parseInt(String(p.no).replace(/[^0-9]/g,''),10); if(!no) return out({ ok:false, error:"no no" });
  var s = sh();
  var cur = s.getRange(row, 25).getValue(); // 덮어쓰기 방지: 이미 값 있으면 skip(force 시만 갱신)
  if (String(cur).replace(/[^0-9]/g,'') && !p.force) return out({ ok:false, error:"already_set", cur:cur });
  s.getRange(row, 25).setValue(no);
  return out({ ok:true, row:row, no:no });
}

// 날짜(1열) 설정 — 서베이 등으로 날짜 없이 들어온 건 보정용. password 게이트(switch 진입 전 검증).
function setDate(p){
  var row = parseInt(p.row,10); if(!row) return out({ ok:false, error:"no row" });
  if(!p.date) return out({ ok:false, error:"no date" });
  sh().getRange(row, 1).setValue(String(p.date)); // 날짜 열(1)
  return out({ ok:true, row:row, date:String(p.date) });
}

// 구매성 지출 월별×부서별 서버측 집계 — 이미지 제외 경량 JSON. 실집행성(반려·미승인·캔슬 제외), 날짜 있는 건만. 대시보드 라이브용(list 대량 payload 회피).
function procSummary(p){
  var s = sh(); var lr = s.getLastRow();
  if (lr < FIRST_ROW) return out({ ok:true, dept:{}, months:[0,0,0,0,0,0,0,0,0,0,0,0] });
  var v = s.getRange(FIRST_ROW, 1, lr - FIRST_ROW + 1, 17).getValues();
  var EXCL = {"반려":1,"미승인":1,"캔슬":1};
  var dept = {}, months = [0,0,0,0,0,0,0,0,0,0,0,0];
  for (var i=0;i<v.length;i++){
    var r = v[i]; if (!r[2]) continue;              // 요청자 없으면 빈행
    var st = r[11] || "품의"; if (EXCL[st]) continue; // 실집행성만
    var dn = dateNum(fmtDate(r[0])); if (!dn) continue; // 날짜 없으면 제외
    var mo = Math.floor((dn % 10000) / 100) - 1; if (mo < 0 || mo > 11) continue;
    var amt = parseInt(String(r[6]).replace(/[^0-9\-]/g,''), 10); if (isNaN(amt)) continue;
    var d = String(r[3] || "기타"); if (d === "체조") d = "체조&트램"; // 대시보드 키와 정렬
    if (!dept[d]) dept[d] = [0,0,0,0,0,0,0,0,0,0,0,0];
    dept[d][mo] += amt; months[mo] += amt;
  }
  return out({ ok:true, dept:dept, months:months });
}

/* ── 매출 종목(팀)별 라이브 집계 — 월별 「매출 보고」 파일 말일탭 팀별 표(O8:T74) 서버측 파싱.
 *    읽기전용·팀 집계만 반환(회원명 등 PII 비반환). 매출마스터(정적)의 종목값 부정확 대체(예: 6월 뮤지컬 실제 3,777,500). */
var SALES_FOLDER = "1Yw-i6L9tWm-t7_sf2qEEih0nbC3fsjKC"; // 월별 매출 보고 폴더

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
    if (sht) grid = sht.getRange(String(p.range||"O8:T74")).getDisplayValues(); // range 지정 가능(진단용)
  }
  return out({ ok:true, month:mo, tabs:names, tab:tab, grid:grid });
}

var LABOR_MASTER_ID = "1uAmZXX0GbiDImORxEwnDFm4_C-r0W43s-_tV_cPq9lE"; // 인건비마스터(A부서 B강사) — 강사→종목 매핑 소스
var SALES_ALIAS = { "아쿠아":"수영", "루프 메소드":"루프매소드", "루프메소드":"루프매소드", "뮤지컬":"뮤지컬", "GXE":"GXE", "기타":"기타" }; // 강사가 아닌 직접 팀/프로그램 라벨

function nameKey_(s){ return String(s||"").replace(/\s+/g,"").replace(/프로$/,""); } // 이름 정규화(공백·'프로' 접미 제거)

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

function daysInMonth_(y, m){ return new Date(y, m, 0).getDate(); } // m=1~12

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
function salesDept(p){
  var cache = CacheService.getScriptCache();
  if (!p.nocache){ var hit = cache.get("sales_dept_v1"); if (hit) return out(JSON.parse(hit)); }
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
  try { cache.put("sales_dept_v1", JSON.stringify(res), 1200); } catch(e){} // 20분 캐시(payload 소형)
  return out(res);
}

/** 타임(시급) 인건비 라이브 — 월별 매출보고 '타임직원' 탭(G.X 및 타임 페이롤)의 블록별 '지급액 합계'(H열) 서버 집계.
 *  라이프가드 등 시급 인력 = 인건비마스터 밖의 실지출(매니저님 확인 2026-07-04). 집계만 반환(PII 비반환)·20분 캐시.
 *  함정 처리: 블록 부서/시간 칸에 적힌 날짜의 월이 파일 월과 다르면 템플릿 잔재로 보고 제외(예: 6·7월 탭에 반복된 '2/22 휴관일' 168,000). */
function laborTime(p){
  var cache = CacheService.getScriptCache();
  if (!p.nocache){ var hit = cache.get("labor_time_v1"); if (hit) return out(JSON.parse(hit)); }
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
  try { cache.put("labor_time_v1", JSON.stringify(res), 1200); } catch(e){}
  return out(res);
}

/** 퇴사자 지급 정리 — 인건비마스터 해당 강사 행의 from월~12월을 0 고정(수식 잔재·선입력 제거, 이전 지급내역 보존).
 *  adminPassword 필수 · 대상 시트=인건비마스터 한정 · before 반환(감사 로그용). */
function laborZero(p){
  if (String(p.adminPassword) !== PW) return out({ ok:false });
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

function addReceipt(p){
  var row = parseInt(p.row,10); if(!row) return out({ ok:false, error:"no row" });
  var s = sh(); var link = "";
  if (p.fileData){
    var blob = Utilities.newBlob(Utilities.base64Decode(p.fileData), p.mimeType||"image/jpeg", p.fileName||("receipt_row"+row));
    var f = DriveApp.getFolderById(RECEIPT_FOLDER).createFile(blob);
    link = f.getUrl();
  } else if (p.link){ link = p.link; }
  s.getRange(row, 15).setValue(link); // 지출증빙
  s.getRange(row, 12).setValue("정산"); // 진행상황 → 정산
  return out({ ok:true, link:link });
}

function addPhoto(p){
  var row = parseInt(p.row,10); if(!row) return out({ ok:false, error:"no row" });
  if(!p.fileData) return out({ ok:false, error:"no file" });
  var url = putPhoto(sh(), row, p);
  return out({ ok:true, url:url });
}

function delRow(p){
  var row = parseInt(p.row,10); if(!row) return out({ ok:false, error:"no row" });
  sh().deleteRow(row); // 시트에서 행 완전 삭제
  return out({ ok:true });
}

// 신규 액션: 검토결과 upsert (기존 add/list/status/photo/delete 무변경)
// 검토시트 컬럼(1-base): A품의행 B품의물품 C동일제품 D최저가 E판매처링크 F품의가 G품의가대비 H신뢰도 I검토일 J비고 (헤더 1행)
function lowpriceSet(p){
  if (String(p.adminPassword) !== PW) return out({ ok:false }); // 비번 자체검증(불일치 시 ok:false)
  var row = parseInt(p.row, 10); if (!row) return out({ ok:false, error:"no row" });
  var bj = [ p.품의물품||"", p.제품||"", p.최저가||"", p.판매처||"", p.품의가||"",
             p.품의가대비||"", p.신뢰도||"", p.검토일||"", p.비고||"" ]; // B~J
  var r = reviewUpsert_(row, bj);
  return out({ ok:true, row:row, mode:r });
}

// 내부 전용: 검토시트 A열(품의행) 기준 upsert (외부=lowpriceSet, 내부=제출즉시조사 공용). 행번호 row + B~J 9칸 배열.
function reviewUpsert_(row, bj){
  var sheet = SpreadsheetApp.openById(REVIEW_SHEET_ID).getSheets()[0]; // 첫 시트
  var lr = sheet.getLastRow();
  var found = 0;
  if (lr >= 2){ // 헤더 1행 건너뛰고 2행부터 A열(품의행) 검색
    var col = sheet.getRange(2, 1, lr - 1, 1).getValues();
    for (var i = 0; i < col.length; i++){
      if (parseInt(col[i][0], 10) === row){ found = i + 2; break; }
    }
  }
  if (found){
    sheet.getRange(found, 2, 1, 9).setValues([bj]); // 기존행 B~J 갱신
    return "update";
  }
  sheet.appendRow([row].concat(bj)); // 새 행 A~J append
  return "append";
}

// 신규 액션: 검토결과 행삭제 (검토시트 실제 행번호 배열·adminPassword 자체검증)
function lowpriceDel(p){
  if (String(p.adminPassword) !== PW) return out({ ok:false });
  var rows = p.reviewRows; // 검토시트 실제 행번호 배열(1-base)
  if (!rows || !rows.length) return out({ ok:false, error:"no rows" });
  var sheet = SpreadsheetApp.openById(REVIEW_SHEET_ID).getSheets()[0];
  rows = rows.map(function(r){return parseInt(r,10);}).filter(function(n){return n>=2;}).sort(function(a,b){return b-a;}); // 헤더보호 + 내림차순(아래부터 삭제)
  rows.forEach(function(n){ sheet.deleteRow(n); });
  return out({ ok:true, deleted:rows });
}
