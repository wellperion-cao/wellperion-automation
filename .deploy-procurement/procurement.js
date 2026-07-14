/** 웰페리온 지출품의 백엔드 — 시트 '지출품의' 탭 읽기/쓰기 (품의·검토·집행·정산·영수증)
 * 시트: 1. 웰페리온 지출 관리 및 현황
 * 컬럼(1-base): 1날짜 2타임 3요청자 4소속 5물품 6링크 7가격 8목적 9승인자 10비고 11이미지 12진행상황 13승인날짜 14배송 15지출증빙 16항목1 17항목2
 *   확장열: 25번호(#) 26구매날짜 27배송비(참고 — 가격=총액에 이미 포함) 28결제수단(카드/현금) — 2026-07-14 배송비·결제 신설
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
  try { return route(p); }
  catch(err2){ console.error("[route]", p && p.action, String(err2)); return out({ ok:false, error:"server_error: " + String(err2) }); } // 무음 장애 방지(2026-07-06 감사)
}
function route(p){
  if (p.action === "lowprice_set") return lowpriceSet(p); // 검토결과 쓰기(별도 시트·adminPassword) — 기존 게이트 앞 분기
  if (p.action === "lowprice_del") return lowpriceDel(p); // 검토결과 행삭제(별도 시트·adminPassword) — 기존 게이트 앞 분기
  if (p.action === "sales_dept_pub") return salesDeptPub(p); // 공개 강습 팀집계(무인증·운영부/PII 제외) — 공개 페이지(파트너팀 체계.html)용, 2026-07-14
  if (p.action === "sales_instr_pub") return salesInstrPub(p); // 공개 강사별(무인증·6팀·진행월) — 파트너팀 페이지 강사별 실시간(매니저 승인 2026-07-14, 강습부 시트로 이미 공개중), 노출증가0
  if (String(p.password) !== PW) return out({ ok:false, error:"unauthorized" });
  switch (p.action){
    case "diag_naver": return diagNaver(p); // 진단(2026-07-06 감사: 무인증→비번 게이트 뒤로 이동)
    case "list":    return listItems(p);
    case "add":     return addItem(p);
    case "status":  return setStatus(p);
    case "setno":   return setNo(p);
    case "setdate": return setDate(p);
    case "colprobe": return colProbe(p); // 열 점검(읽기전용·값 비반환) — 신규 열 배정 전 검증용, 2026-07-14
    case "proc_summary": return procSummary(p);
    case "sales_probe": return salesProbe(p);
    case "sales_dept": return salesDept(p);
    case "sales_ops":  return salesOps(p);
    case "sales_month": return salesMonthTot(p);
    case "labor_zero": return laborZero(p);
    case "labor_time": return laborTime(p);
    case "receipt": return addReceipt(p);
    case "photo":   return addPhoto(p);
    case "delete":  return delRow(p);
    default:        return out({ ok:false, error:"unknown action: " + p.action });
  }
}
function sh(){ return SpreadsheetApp.openById(SHEET_ID).getSheetByName(TAB); }
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
  var thumb = String(p.thumb || p.fileData || "").replace(/[^A-Za-z0-9+/=]/g,""); // base64 문자만 허용
  var mimeOk = function(m){ return /^image\/[A-Za-z0-9.+-]{1,30}$/.test(String(m||"")); }; // mime 화이트리스트 — 속성 이스케이프 주입 차단(검증 발견 수정 2026-07-14)
  var mime = mimeOk(p.thumbMime) ? p.thumbMime : (mimeOk(p.mimeType) ? p.mimeType : "image/jpeg");
  s.getRange(row, 11).setValue("data:"+mime+";base64,"+thumb); // data URI
  return f.getUrl();
}
function dateNum(s){
  var m = String(s||"").match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  return m ? (parseInt(m[1],10)*10000 + parseInt(m[2],10)*100 + parseInt(m[3],10)) : 0;
}
function listItems(p){
  p = p || {};
  var noimg = !!p.noimg; // 경량 모드: 이미지·증빙 base64 제외(이상지출 집계 등 필드만 필요할 때 — 2026-07-06 감사)
  var mode = p.mode || "active"; // active=품의/검토/정산(미완료), done=그 외(완료/승인 등, 기간필터)
  var ACTIVE = {"품의":1,"검토":1,"정산":1};
  var s = sh(); var lr = s.getLastRow();
  if (lr < FIRST_ROW) return out({ ok:true, count:0, data:[] });
  var v = s.getRange(FIRST_ROW, 1, lr - FIRST_ROW + 1, 17).getValues();
  var fm = s.getRange(FIRST_ROW, 11, lr - FIRST_ROW + 1, 1).getFormulas(); // 이미지열 =IMAGE 수식
  var lc = s.getLastColumn();
  var nos = lc >= 25 ? s.getRange(FIRST_ROW, 25, lr - FIRST_ROW + 1, 1).getValues() : null; // 번호열(25)
  var pds = lc >= 26 ? s.getRange(FIRST_ROW, 26, lr - FIRST_ROW + 1, 1).getValues() : null; // 구매날짜열(26, 2026-07-08 신설)
  var shp = lc >= 27 ? s.getRange(FIRST_ROW, 27, lr - FIRST_ROW + 1, 1).getValues() : null; // 배송비열(27, 2026-07-14 신설 — 가격=총액에 포함된 참고값)
  var pys = lc >= 28 ? s.getRange(FIRST_ROW, 28, lr - FIRST_ROW + 1, 1).getValues() : null; // 결제수단열(28, 카드/현금 — 빈값=카드 취급)
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
      가격: r[6], 목적: r[7], 승인자: r[8], 이미지: noimg ? "" : extractImage(r[10], fm[i][0]), 상태: st,
      승인날짜: fmtDate(r[12]), 지출증빙: noimg ? "" : driveThumb(String(r[14]||"")), 항목1: r[15], 항목2: r[16],
      번호: nos ? nos[i][0] : "",
      구매날짜: pds ? fmtDate(pds[i][0]) : "",
      배송비: shp ? shp[i][0] : "",
      결제: pys ? String(pys[i][0]||"") : ""
    });
  }
  return out({ ok:true, count:data.length, mode:mode, data:data });
}

function addItem(p){
  var s = sh();
  var now = new Date();
  var ts = Utilities.formatDate(now,"Asia/Seoul","yyyy. M. d a h:mm:ss");
  // 동시 제출 경합 방지(2026-07-06 감사): append~행번호~고정번호 발급 전 구간을 LockService로 보호
  var lock = LockService.getScriptLock();
  var locked = false; try { locked = lock.tryLock(5000); } catch(eL){}
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
  if (p.구매날짜) s.getRange(row, 26).setValue(p.구매날짜); // 구매(예정)날짜 — 새 행 26열에만 기록(기존·회계열 무관, 2026-07-08)
  var shipAmt = Math.round(parseFloat(String(p.배송비==null?"":p.배송비).replace(/[^0-9.\-]/g,"")) || 0); // 소수점 반올림·음수는 아래 >0 가드로 차단(검증 발견 수정 2026-07-14)
  if (shipAmt > 0){ var r27 = s.getRange(row, 27); r27.setNumberFormat("#,##0"); r27.setValue(shipAmt); } // 배송비(참고) — 가격(7열)=총액에 이미 포함, 회계 집계 무변경. 숫자서식 강제(미지정 시 시트가 날짜로 오인한 실측 버그, 2026-07-14)
  var payKind = String(p.결제||"").trim();
  if (payKind === "현금" || payKind === "카드") s.getRange(row, 28).setValue(payKind); // 결제수단 — 빈값=카드 취급
  if (locked) { try { lock.releaseLock(); } catch(eL2){} }
  if (p.fileData) putPhoto(s, row, p); // 품의 첨부사진 → 이미지 열(=IMAGE 썸네일)
  var instant = null;
  // 시세 비교 기준 = 총액 − 배송비(물품가) — 총액(배송비 포함)을 네이버 물품단가와 그대로 대조하면 배송비만큼 '비쌈' 오탐(검증 발견 수정 2026-07-14)
  var priceNum = parseInt(String(p.가격==null?"":p.가격).replace(/[^0-9]/g,""), 10) || 0;
  var cmpPrice = (shipAmt > 0 && priceNum > shipAmt) ? String(priceNum - shipAmt) : (p.가격||"");
  var shipNote = (shipAmt > 0 && priceNum > shipAmt) ? " · 품의가=배송비 제외 물품가 기준" : "";
  try { instant = instantLowprice_(row, p.물품||"", cmpPrice, no, shipNote); } catch(e){ console.error("[instant]", String(e)); instant = { ok:false, error:String(e) }; } // 제출즉시 최저가(실패해도 품의는 성공)
  return out({ ok:true, no:no, instant:instant });
}

/** 제출 즉시 최저가 조사 — 네이버 쇼핑 검색(가격 낮은순 1건) → 검토시트 upsert.
 *  키(Script Properties NAVER_CLIENT_ID/SECRET) 없으면 안전하게 skip. 단순검색이라 신뢰도 '하(참고)' → 9시 cron 에이전트가 보완(2단 구조).
 */
function instantLowprice_(row, 물품, 가격, no, note){
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
    reviewUpsert_(row, [물품||"", "", "", "", price||"", "", "하", 검토일, "자동·네이버쇼핑 제출즉시·검색결과없음 → 모델명 보완요"], no);
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
  var 비고 = "자동·네이버쇼핑 제출즉시(참고시세) · 9시 보완예정" + (matched ? "" : " · ⚠관련성낮음(모델명 보완요)") + (mall ? " · "+mall : "") + (note || "");
  // B품의물품 C동일제품 D최저가 E판매처링크 F품의가 G품의가대비 H신뢰도 I검토일 J비고
  reviewUpsert_(row, [물품||"", name, low||"", link, price||"", 대비, "하", 검토일, 비고], no);
  return { ok:true, found:1, matched:matched, low:low, name:name };
}

function comma_(n){ return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); } // 천단위 콤마(로케일 무관)

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

// 열 점검(읽기전용) — 신규 열 배정 전 안전검증: 마지막열·헤더(2행)·지정범위의 비어있지 않은 셀 '개수'만 반환(셀 값 비반환·PII 없음). 2026-07-14 배송비/결제 열 신설 검증용.
function colProbe(p){
  var s = sh(); var lr = s.getLastRow(), lc = s.getLastColumn();
  var head = s.getRange(2, 1, 1, Math.min(lc, 40)).getDisplayValues()[0];
  var from = parseInt(p.colFrom,10) || 18, to = parseInt(p.colTo,10) || Math.min(lc, 30);
  var counts = {};
  if (lr >= FIRST_ROW && to >= from && from <= lc){
    var v = s.getRange(FIRST_ROW, from, lr - FIRST_ROW + 1, Math.min(to, lc) - from + 1).getValues();
    for (var c = from; c <= Math.min(to, lc); c++){
      var n = 0;
      for (var i = 0; i < v.length; i++){ if (String(v[i][c-from]) !== "") n++; }
      counts[c] = n;
    }
  }
  return out({ ok:true, lastRow:lr, lastCol:lc, header2:head, nonEmpty:counts });
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
    // 허용 영역 화이트리스트(PII 차단): 일자탭=팀 집계 O8:T80(기본)/월집계 블록 V60:AB90(win=monthly) / 집계탭('총 매출'류)=상단 집계표만
    var AGG = { "총 매출":"A1:P80", "총 매출(분류)":"A1:P80", "보고":"A1:P80" };
    var rng = AGG[tab] || (String(p.win||"") === "monthly" ? "V60:AB90" : "O8:T80");
    if (sht) grid = sht.getRange(rng).getDisplayValues();
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
function salesInstrPub(p){
  var hit = swrGet_(p, "sales_instr_v1"); if (hit) return out(hit);
  var now = new Date();
  var year = parseInt(Utilities.formatDate(now,"Asia/Seoul","yyyy"),10);
  var curMo = parseInt(Utilities.formatDate(now,"Asia/Seoul","M"),10);
  var curDay = parseInt(Utilities.formatDate(now,"Asia/Seoul","d"),10);
  var files = salesFiles_();
  var dmap = laborDeptMap_();
  var SIX = { "수영":1, "P.T":1, "필라테스":1, "골프":1, "스쿼시":1, "체조&트램":1 };
  var month = 0, instr = [];
  if (files[curMo]){
    var ss = SpreadsheetApp.openById(files[curMo]);
    var startDay = Math.min(curDay, daysInMonth_(year, curMo));
    for (var d=startDay; d>=1; d--){
      var sht = ss.getSheetByName(String(d));
      if (!sht) continue;
      var rows = parseInstrList_(sht, dmap, SIX);
      if (rows && rows.length){ instr = rows; month = curMo; break; }
    }
  }
  var res = { ok:true, month:month, instr:instr, at:Utilities.formatDate(now,"Asia/Seoul","yyyy-MM-dd HH:mm") };
  swrPut_("sales_instr_v1", res);
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
  var no = (p.번호 != null && p.번호 !== "") ? p.번호 : (p.no != null ? p.no : ""); // 고정 일련번호(#) — 있으면 K열 기록
  var r = reviewUpsert_(row, bj, no);
  return out({ ok:true, row:row, mode:r });
}

// 내부 전용: 검토시트 A열(품의행) 기준 upsert (외부=lowpriceSet, 내부=제출즉시조사 공용). 행번호 row + B~J 9칸 배열 + K열 고정번호(#, 선택).
// K열(품의번호)은 행 삭제·재정렬에도 불변인 매칭키 — 대시보드 배지가 번호 우선 매칭(2026-07-06 감사).
function reviewUpsert_(row, bj, no){
  var sheet = SpreadsheetApp.openById(REVIEW_SHEET_ID).getSheets()[0]; // 첫 시트
  if (String(sheet.getRange(1, 11).getValue() || "") === "") sheet.getRange(1, 11).setValue("품의번호"); // K1 헤더(1회성)
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
    if (no != null && no !== "") sheet.getRange(found, 11).setValue(no);
    return "update";
  }
  sheet.appendRow([row].concat(bj).concat([no != null ? no : ""])); // 새 행 A~K append
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
