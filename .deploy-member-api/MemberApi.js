/** 웰페리온 회원관리 배관 (member-api) — 2026-08-20 배 분리 1단계(읽기 전용)
 *
 *  왜 떼어냈나:
 *    회원관리 화면(membership.html)이 매출·강습·마케팅 집계까지 다 얹힌 한 덩어리
 *    GAS(.deploy-funnel-v2/Survey.js)를 거친다. 전례: 고객 접수를 intake-api 로
 *    분리(2026-08-06 GM 결재, 커밋 87566011f) — 실측상 왕복 대부분이 그 덩치를
 *    통째로 로드하는 고정비용이었다. 같은 수법을 회원관리에도 적용해도 되는지
 *    2026-08-20 GM 승인.
 *
 *  담당 액션: member_active_list 딱 1개(+ping 진단) — 유효/종료/법인/보관 회원
 *    명단 조회(읽기 전용). 함수 본문은 Survey.js 9072~9259줄 원문 그대로 이관
 *    (동작 동일성 보장 — 캐시 TTL·정렬·직렬화 규칙 무변경).
 *
 *  ⚠ 쓰기 액션(member_active_update 등)·다른 조회 액션은 여기 없다 — 이번 결재
 *    범위가 "읽기 전용 액션 하나·왕복측정"까지라 그쪽은 계속 Survey.js가 담당한다.
 *  ⚠ 원본(Survey.js)에서 코드를 지우지 않았다 — 두 경로가 당분간 함께 산다.
 *    화면 전환(membership.html 주소 교체)은 이번 배포 범위가 아니다 — 별도 결재 후.
 */

// ── 회원 시트 위치 상수 (Survey.js 15~23줄과 동일 값 — 프로젝트가 달라 상수 공유 불가) ──
const MEMBER_SPREADSHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
const MEMBER_SHEET = '유효회원';
const MEMBER_ARCHIVE_SHEET = 'LOSS보관';
const MEMBER_PHONE_COL = '휴대폰 번호';   // 회원부 전화번호 헤더

// 회원 유효/종료 단일 판정(약속 L01 — 판정 로직 복제 금지, Survey.js 122~129줄과 동일).
//   유효 = (잔여일>=0 또는 잔여일 미기재) & 재등록분류가 이탈표시(LOSS/환불/양도LOSS)가 아님.
var MEMBER_LOSS_TAGS_ = { 'LOSS': 1, '환불': 1, '양도LOSS': 1 };
function _memberIsValid_(remCell, reVCell) {
  var remRaw = String(remCell == null ? '' : remCell).replace(/[^0-9\-]/g, '');
  var rem = (remRaw === '' || remRaw === '-') ? NaN : parseInt(remRaw, 10);
  var reV = String(reVCell == null ? '' : reVCell).trim();
  return (isNaN(rem) || rem >= 0) && !MEMBER_LOSS_TAGS_[reV];
}

function _normPhone_(v) { return String(v == null ? '' : v).replace(/[^0-9]/g, ''); }

// 지문키(rowKey) 재료 — Survey.js 188~210줄과 동일(프론트 _gzNormTsKey_와 바이트 동일 규칙 유지 필수).
function _normTsKey_(v) {
  function pad(n, len) { var s = String(Math.abs(Math.trunc(Number(n) || 0))); while (s.length < len) s = '0' + s; return s; }
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return '';
    return Utilities.formatDate(v, 'Asia/Seoul', 'yyyyMMddHHmmss');
  }
  var s = String(v).trim();
  if (!s) return '';
  var m1 = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (m1) return pad(m1[1], 4) + pad(m1[2], 2) + pad(m1[3], 2) + pad(m1[4] || 0, 2) + pad(m1[5] || 0, 2) + pad(m1[6] || 0, 2);
  var m2 = s.match(/^(\d{4})[.\s]+(\d{1,2})[.\s]+(\d{1,2})(?:\s*(오전|오후)?\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (m2) {
    var hh = parseInt(m2[5] || '0', 10);
    if (m2[4] === '오전') { if (hh === 12) hh = 0; }
    else if (m2[4] === '오후') { if (hh !== 12) hh += 12; }
    return pad(m2[1], 4) + pad(m2[2], 2) + pad(m2[3], 2) + pad(hh, 2) + pad(m2[6] || 0, 2) + pad(m2[7] || 0, 2);
  }
  return s.replace(/[^0-9]/g, '');
}

// 이름 정규화(지문키 세 번째 재료, Survey.js 237~239줄과 동일).
function _normNameKey_(v) {
  return String(v == null ? '' : v).replace(/\s+/g, '').toLowerCase();
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// 조회 캐시(청크) 유틸 — Survey.js 1350~1387줄과 동일(약속 L01, 새 캐시 장치 발명 금지).
var _CACHE_CHUNK_CHARS_ = 30000;
function _cachePutJson_(cache, key, obj, ttlSec) {
  try {
    var str = JSON.stringify(obj);
    var n = Math.max(1, Math.ceil(str.length / _CACHE_CHUNK_CHARS_));
    var payload = {};
    payload[key + '__meta'] = String(n);
    for (var i = 0; i < n; i++) {
      payload[key + '__' + i] = str.substr(i * _CACHE_CHUNK_CHARS_, _CACHE_CHUNK_CHARS_);
    }
    cache.putAll(payload, ttlSec);
  } catch (e) { /* 저장 실패 무시 — 폴백=시트 재조회 */ }
}
function _cacheGetJson_(cache, key) {
  try {
    var meta = cache.get(key + '__meta');
    if (!meta) return null;
    var n = parseInt(meta, 10);
    if (!n || n < 1) return null;
    var keys = [];
    for (var i = 0; i < n; i++) keys.push(key + '__' + i);
    var chunks = cache.getAll(keys);
    var parts = [];
    for (var j = 0; j < n; j++) {
      var part = chunks[key + '__' + j];
      if (part === undefined || part === null) return null;
      parts.push(part);
    }
    return JSON.parse(parts.join(''));
  } catch (e) { return null; }
}

function _processAction(body) {
  const action = body.action || '';

  if (action === 'ping') {
    return _json({
      ok: true, service: 'member-api',
      at: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'),
    });
  }

  // ═══ member_active_list — Survey.js 9072~9259줄 원문 그대로 이관(변수명 aa* 포함 동일 유지) ═══
  if (action === 'member_active_list') {
    var _nc = String(body.nocache || '') === '1';
    // scope='archive' = 지난 연도 LOSS 보관 시트(2026-08-13). 검색이 옛 회원을 놓치지 않도록 조회 통로를 연다.
    var aaScope = String(body.scope || 'valid');
    if (aaScope !== 'ended' && aaScope !== 'corp' && aaScope !== 'archive') aaScope = 'valid';
    var aaSs0 = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    // 법인회원: 별도 시트(법인현황 gid=1612064257) 전체를 제네릭 표시 (2026-06-25 GM)
    if (aaScope === 'corp') {
      var cpSh = null, cpShs = aaSs0.getSheets();
      for (var cps = 0; cps < cpShs.length; cps++) { if (cpShs[cps].getSheetId() === 1612064257) { cpSh = cpShs[cps]; break; } }
      if (!cpSh) cpSh = aaSs0.getSheetByName('법인현황');
      if (!cpSh) return _json({ ok: true, scope: 'corp', headers: [], count: 0, data: [] });
      var cpCols = cpSh.getLastColumn(), cpLast = cpSh.getLastRow();
      if (cpLast < 1 || cpCols < 1) return _json({ ok: true, scope: 'corp', headers: [], count: 0, data: [] });
      var cpHdrRaw = cpSh.getRange(1, 1, 1, cpCols).getValues()[0].map(function(v){ return String(v).trim(); });
      var cpKeep = cpHdrRaw.map(function(h){ return h && !/GMT|표준시/.test(h); });
      var cpHdrs = []; for (var ch = 0; ch < cpHdrRaw.length; ch++) if (cpKeep[ch]) cpHdrs.push(cpHdrRaw[ch]);
      var cpRows = [];
      if (cpLast >= 2) {
        var cpData = cpSh.getRange(2, 1, cpLast - 1, cpCols).getValues();
        for (var cpr = 0; cpr < cpData.length; cpr++) {
          var crow = cpData[cpr];
          var cpAny = false; for (var cc = 0; cc < cpCols; cc++){ if (cpKeep[cc] && String(crow[cc] == null ? '' : crow[cc]).trim()){ cpAny = true; break; } }
          if (!cpAny) continue;
          var cpObj = { rowIndex: cpr + 2 };
          for (var cc2 = 0; cc2 < cpHdrRaw.length; cc2++) {
            if (!cpKeep[cc2]) continue;
            var cv2 = crow[cc2];
            if (cv2 instanceof Date && !isNaN(cv2.getTime())) cv2 = Utilities.formatDate(cv2, 'Asia/Seoul', 'yyyy-MM-dd');
            cv2 = (cv2 === null || cv2 === undefined) ? '' : String(cv2);
            var cpHk = cpHdrRaw[cc2], cpHkN = cpHk.replace(/\s/g, '');
            if (cpHkN.indexOf('휴대폰') >= 0 || cpHkN.indexOf('연락처') >= 0 || cpHkN.indexOf('전화') >= 0) {
              var cpPn = cv2.replace(/[^0-9]/g, ''); if (cpPn.length === 11) cv2 = cpPn.slice(0,3)+'-'+cpPn.slice(3,7)+'-'+cpPn.slice(7); else if (cpPn.length === 10) cv2 = cpPn.slice(0,3)+'-'+cpPn.slice(3,6)+'-'+cpPn.slice(6);
            }
            cpObj[cpHk] = cv2;
          }
          cpRows.push(cpObj);
        }
      }
      return _json({ ok: true, scope: 'corp', headers: cpHdrs, count: cpRows.length, data: cpRows });
    }
    var aaCache = CacheService.getScriptCache();
    var aaCacheKey = 'aacache|' + aaScope + '|' + (String(body.format || '') === 'rows' ? 'rows' : 'obj');
    if (!_nc) {
      var aaHit = _cacheGetJson_(aaCache, aaCacheKey);
      if (aaHit) return _json(aaHit);
    }
    var aaSh = aaSs0.getSheetByName(aaScope === 'archive' ? MEMBER_ARCHIVE_SHEET : MEMBER_SHEET);
    if (!aaSh) {
      if (aaScope === 'archive') return _json({ ok: true, scope: aaScope, headers: [], count: 0, data: [] });
      return _json({ ok: false, error: '유효회원 시트 없음' });
    }
    var aaLast = aaSh.getLastRow();
    var aaCols = aaSh.getLastColumn();
    if (aaLast < 1 || aaCols < 1) return _json({ ok: true, scope: aaScope, headers: [], count: 0, data: [] });
    var aaHdrRaw = aaSh.getRange(1, 1, 1, aaCols).getValues()[0].map(function(v){ return String(v).trim(); });
    var aaKeep = aaHdrRaw.map(function(h){ return h && !/GMT|표준시/.test(h); });
    var aaHdrs = [];
    for (var ah = 0; ah < aaHdrRaw.length; ah++) if (aaKeep[ah]) aaHdrs.push(aaHdrRaw[ah]);
    function _aaIdx(want){ var w = String(want).replace(/\s/g,''); for (var i=0;i<aaHdrRaw.length;i++){ if (aaHdrRaw[i].replace(/\s/g,'').indexOf(w) >= 0) return i; } return -1; }
    var aiName = _aaIdx('회원명'), aiRem = _aaIdx('잔여일'), aiRe = _aaIdx('재등록분류');
    var aiCha = _aaIdx('등록회차'), aiCls = _aaIdx('등록분류');
    var aiTsRk = _aaIdx('등록일자'); if (aiTsRk < 0) aiTsRk = _aaIdx('타임스탬프');
    var aiPhRk = aaHdrRaw.indexOf(MEMBER_PHONE_COL);
    var aaRows = [];
    var aaFull = true;
    var aaNameKey = aiName >= 0 ? aaHdrRaw[aiName] : '';
    if (aaLast >= 2) {
      var aaData = aaSh.getRange(2, 1, aaLast - 1, aaCols).getValues();
      for (var ai = 0; ai < aaData.length; ai++) {
        var arow = aaData[ai];
        var nm = aiName >= 0 ? String(arow[aiName] == null ? '' : arow[aiName]).trim() : '';
        if (!nm) continue;
        if (/^[0-9.]+$/.test(nm) || /^\d{1,3}대$/.test(nm) || /^\d{1,3}\s*[-~]\s*\d{1,3}세$/.test(nm) || nm === '합계') continue;
        var isValid = _memberIsValid_(aiRem >= 0 ? arow[aiRem] : '', aiRe >= 0 ? arow[aiRe] : '');
        if (aaScope === 'valid' && !isValid) continue;
        if (aaScope === 'ended' && isValid) continue;
        var obj = { rowIndex: ai + 2 };
        for (var ac = 0; ac < aaHdrRaw.length; ac++) {
          if (!aaKeep[ac]) continue;
          var key = aaHdrRaw[ac];
          var v = arow[ac];
          if (v instanceof Date && !isNaN(v.getTime())) v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
          v = (v === null || v === undefined) ? '' : String(v);
          if (key === MEMBER_PHONE_COL) { var pp = v.replace(/[^0-9]/g, ''); if (pp.length === 11) v = pp.slice(0,3) + '-' + pp.slice(3,7) + '-' + pp.slice(7); else if (pp.length === 10) v = pp.slice(0,3) + '-' + pp.slice(3,6) + '-' + pp.slice(6); }
          obj[key] = v;
        }
        if (aiCls >= 0 && !String(arow[aiCls] == null ? '' : arow[aiCls]).trim()) {
          var _chaM = (aiCha >= 0 ? String(arow[aiCha] == null ? '' : arow[aiCha]) : '').match(/\d+/);
          if (_chaM && parseInt(_chaM[0], 10) >= 2) obj[aaHdrRaw[aiCls]] = '재등록';
        }
        if (!aaFull && aaNameKey) obj[aaNameKey] = _svMaskName_(obj[aaNameKey]);
        var _aaTsN = _normTsKey_(aiTsRk >= 0 ? arow[aiTsRk] : ''), _aaPhN = _normPhone_(aiPhRk >= 0 ? arow[aiPhRk] : '');
        var _aaNmN = (aaFull && aiName >= 0) ? _normNameKey_(arow[aiName]) : '';
        obj.rowKey = (_aaTsN && _aaPhN) ? (_aaTsN + '|' + _aaPhN + (_aaNmN ? '|' + _aaNmN : '')) : '';
        aaRows.push(obj);
      }
    }
    var aiEnd = _aaIdx('종료일'); if (aiEnd < 0) aiEnd = _aaIdx('만료일'); if (aiEnd < 0) aiEnd = _aaIdx('이용종료'); if (aiEnd < 0) aiEnd = _aaIdx('만기일'); if (aiEnd < 0) aiEnd = _aaIdx('이탈일');
    if (aiEnd >= 0 && aaKeep[aiEnd]) {
      var aiEndKey = aaHdrRaw[aiEnd];
      aaRows.sort(function(a, b){ var av = String(a[aiEndKey] || ''); var bv = String(b[aiEndKey] || ''); return av < bv ? 1 : (av > bv ? -1 : 0); });
    }
    var aaColNames = aaHdrs.slice();
    var aaArr = [];
    for (var ar = 0; ar < aaRows.length; ar++) {
      var aRow = aaRows[ar], aOut = [aRow.rowIndex, aRow.rowKey || ''];
      for (var ac = 0; ac < aaColNames.length; ac++) aOut.push(aRow[aaColNames[ac]] === undefined ? '' : aRow[aaColNames[ac]]);
      aaArr.push(aOut);
    }
    var aaRowsResult = { ok: true, scope: aaScope, format: 'rows', meta: ['rowIndex', 'rowKey'],
                         columns: aaColNames, count: aaArr.length, rows: aaArr };
    var aaObjResult = { ok: true, scope: aaScope, headers: aaHdrs, count: aaRows.length, data: aaRows };
    var aaWantRows = (String(body.format || '') === 'rows');
    var aaResult = aaWantRows ? aaRowsResult : aaObjResult;
    try {
      _cachePutJson_(aaCache, 'aacache|' + aaScope + '|' + (aaWantRows ? 'obj' : 'rows'),
                     aaWantRows ? aaObjResult : aaRowsResult, 360);
    } catch (aaE) {}
    _cachePutJson_(aaCache, aaCacheKey, aaResult, 360);
    return _json(aaResult);
  }

  return _json({ ok: false, error: 'unknown-action', action: action });
}

function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';
    if (action) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      return _processAction(body);
    }
    return _json({ ok: false, error: 'action 필수' });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

/** 최초 1회 권한 승인용 — Apps Script 편집기에서 이 함수를 실행하면
 *  이 프로젝트가 쓰는 권한(스프레드시트 읽기)을 구글이 한 번 물어본다.
 *  승인해야 웹앱(/exec)이 외부에 응답한다(전례: intake-api authorize(), 커밋 87566011f). */
function authorize() {
  var n = 0;
  try { n = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getName().length; } catch (e) {}
  Logger.log('권한 승인 완료 (확인값 ' + n + ') — 이제 웹앱이 응답합니다.');
  return 'OK';
}
