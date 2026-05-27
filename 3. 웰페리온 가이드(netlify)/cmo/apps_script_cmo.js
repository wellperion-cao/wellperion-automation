// 웰페리온 CMO 콘텐츠 파이프라인 Apps Script v1.0
// 시트: 파이프라인 | 헤더 14열
// 4-Stage 콘텐츠 관리 + 3채널 발행 추적

// ─── 상수 ───
const CMO_SPREADSHEET_ID = '1oAbeLSnDnUZjfwpStsKndzojNi5u9mXOcKx237KgAy8';
const CMO_SHEET = '파이프라인';

const CMO_HEADERS = [
  'id', '콘텐츠명', '카테고리', '현재단계',
  'IG', '블로그', '카페',
  '검수상태', '담당자', '콘텐츠폴더', '비고',
  '생성자', '생성일', '수정일'
];

const CONTENT_CATEGORIES = [
  'WJO', '발레', '바레', '스쿼시',
  '시설안내', '이벤트', '회원후기', '기타'
];

const STAGES = ['가공', '검수', '발행', '추적', '완료'];

const STAGE_COLORS = {
  '가공':   '#e6944e',
  '검수':   '#a78bda',
  '발행':   '#5b9fd5',
  '추적':   '#6abf7b',
  '완료':   '#8c8b83'
};

const CHANNEL_STATUS = ['대기', '진행중', '완료', '건너뜀'];

const REVIEW_STATUS = ['대기', '요청', '승인', '반려'];

// ─── ScriptProperties 헬퍼 ───
function _prop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

// ─── 시트 초기화 ───
function initCmoSheet() {
  const ss = SpreadsheetApp.openById(CMO_SPREADSHEET_ID);
  let sh = ss.getSheetByName(CMO_SHEET);
  if (sh) return sh;

  sh = ss.insertSheet(CMO_SHEET);
  sh.getRange(1, 1, 1, CMO_HEADERS.length).setValues([CMO_HEADERS]);
  sh.getRange(1, 1, 1, CMO_HEADERS.length)
    .setFontWeight('bold')
    .setBackground('#2a2725')
    .setFontColor('#B79F8A');

  const widths = [150, 200, 80, 80, 70, 70, 70, 80, 80, 250, 200, 80, 130, 130];
  widths.forEach((w, i) => sh.setColumnWidth(i + 1, w));
  sh.setFrozenRows(1);
  return sh;
}

// ─── 유틸 ───
function _now() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
}
function _today() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
}
function _genId() {
  return 'CMO-' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMddHHmmss')
    + ('000' + new Date().getMilliseconds()).slice(-3);
}

function _readAll(sh) {
  const last = sh.getLastRow();
  if (last < 2) return [];
  const data = sh.getRange(2, 1, last - 1, CMO_HEADERS.length).getValues();
  return data.map(row => {
    const obj = {};
    CMO_HEADERS.forEach((h, i) => { obj[h] = row[i]; });
    return obj;
  });
}

function _findRow(sh, id) {
  const last = sh.getLastRow();
  if (last < 2) return -1;
  const ids = sh.getRange(2, 1, last - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(id)) return i + 2;
  }
  return -1;
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function _notifyTelegram(text) {
  const token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  const chatId = _prop('CHAT_ID') || _prop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return;
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
  } catch (e) { Logger.log('텔레그램 실패: ' + e.message); }
}

function _mapFields(body) {
  const map = {
    name:'콘텐츠명', title:'콘텐츠명', category:'카테고리', stage:'현재단계',
    ig:'IG', blog:'블로그', cafe:'카페', review:'검수상태',
    owner:'담당자', folder:'콘텐츠폴더', note:'비고', creator:'생성자'
  };
  Object.keys(map).forEach(en => {
    if (body[en] !== undefined && !body[map[en]]) body[map[en]] = body[en];
  });
  return body;
}

// ═══════════════════════════════════════════
//  공용 액션 처리
// ═══════════════════════════════════════════
function _processCmoAction(body) {
  body = _mapFields(body);
  const action = body.action || '';

  // ─── 목록 조회 ───
  if (action === 'cmo_list') {
    const sh = initCmoSheet();
    let items = _readAll(sh);
    const stage = body.stage || body['현재단계'] || '';
    if (stage) items = items.filter(r => String(r['현재단계']) === stage);
    const cat = body.category || body['카테고리'] || '';
    if (cat) items = items.filter(r => String(r['카테고리']) === cat);
    return _json({ ok: true, count: items.length, data: items });
  }

  // ─── 메타 정보 ───
  if (action === 'cmo_meta') {
    return _json({
      ok: true,
      categories: CONTENT_CATEGORIES,
      stages: STAGES,
      channelStatus: CHANNEL_STATUS,
      reviewStatus: REVIEW_STATUS
    });
  }

  // ─── 새 콘텐츠 추가 ───
  if (action === 'cmo_add') {
    const sh = initCmoSheet();
    const id = _genId();
    const now = _now();
    const row = [
      id,
      body['콘텐츠명'] || '',
      body['카테고리'] || '',
      body['현재단계'] || '가공',
      body['IG'] || '대기',
      body['블로그'] || '대기',
      body['카페'] || '대기',
      body['검수상태'] || '대기',
      body['담당자'] || '',
      body['콘텐츠폴더'] || '',
      body['비고'] || '',
      body['생성자'] || '',
      now, now
    ];
    const newRow = sh.getLastRow() + 1;
    sh.getRange(newRow, 1, 1, row.length).setValues([row]);
    _notifyTelegram('📋 <b>[CMO 콘텐츠 등록]</b>\n' + (body['콘텐츠명']||'-') + ' (' + (body['카테고리']||'-') + ')');
    return _json({ ok: true, id: id, message: '콘텐츠가 등록되었습니다.' });
  }

  // ─── 수정 ───
  if (action === 'cmo_update') {
    const sh = initCmoSheet();
    const id = body.id;
    if (!id) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(sh, id);
    if (rowNum < 0) return _json({ ok: false, error: 'ID 없음: ' + id });
    const existing = sh.getRange(rowNum, 1, 1, CMO_HEADERS.length).getValues()[0];
    CMO_HEADERS.forEach((h, i) => {
      if (h === 'id' || h === '생성일' || h === '생성자') return;
      if (body[h] !== undefined && body[h] !== null) existing[i] = body[h];
    });
    existing[CMO_HEADERS.indexOf('수정일')] = _now();
    sh.getRange(rowNum, 1, 1, CMO_HEADERS.length).setValues([existing]);
    return _json({ ok: true, id: id, message: '콘텐츠가 수정되었습니다.' });
  }

  // ─── 단계 이동 ───
  if (action === 'cmo_advance') {
    const sh = initCmoSheet();
    const id = body.id;
    if (!id) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(sh, id);
    if (rowNum < 0) return _json({ ok: false, error: 'ID 없음: ' + id });
    const existing = sh.getRange(rowNum, 1, 1, CMO_HEADERS.length).getValues()[0];
    const curStage = String(existing[CMO_HEADERS.indexOf('현재단계')]);
    const curIdx = STAGES.indexOf(curStage);
    if (curIdx < 0 || curIdx >= STAGES.length - 1) {
      return _json({ ok: false, error: '더 이상 진행할 단계가 없습니다.' });
    }
    const nextStage = STAGES[curIdx + 1];
    existing[CMO_HEADERS.indexOf('현재단계')] = nextStage;
    existing[CMO_HEADERS.indexOf('수정일')] = _now();
    sh.getRange(rowNum, 1, 1, CMO_HEADERS.length).setValues([existing]);
    const name = existing[CMO_HEADERS.indexOf('콘텐츠명')];
    _notifyTelegram('➡️ <b>[CMO 단계 이동]</b>\n' + name + ': ' + curStage + ' → ' + nextStage);
    return _json({ ok: true, id: id, from: curStage, to: nextStage });
  }

  // ─── 삭제 ───
  if (action === 'cmo_delete') {
    const sh = initCmoSheet();
    const id = body.id;
    if (!id) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(sh, id);
    if (rowNum < 0) return _json({ ok: false, error: 'ID 없음: ' + id });
    sh.deleteRow(rowNum);
    return _json({ ok: true, id: id, message: '삭제되었습니다.' });
  }

  // ─── 파이프라인 현황 요약 ───
  if (action === 'cmo_summary') {
    const sh = initCmoSheet();
    const items = _readAll(sh);
    const byStage = {};
    STAGES.forEach(s => { byStage[s] = 0; });
    items.forEach(r => {
      const s = String(r['현재단계']);
      byStage[s] = (byStage[s] || 0) + 1;
    });
    const byCategory = {};
    items.forEach(r => {
      const c = String(r['카테고리']) || '기타';
      byCategory[c] = (byCategory[c] || 0) + 1;
    });
    return _json({ ok: true, total: items.length, byStage: byStage, byCategory: byCategory });
  }

  return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

// ═══════════════════════════════════════════
//  doGet / doPost
// ═══════════════════════════════════════════
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';
    if (action.startsWith('cmo_')) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      body.action = action;
      return _processCmoAction(body);
    }
    return _json({ ok: false, error: '알 수 없는 action: ' + action });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processCmoAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
