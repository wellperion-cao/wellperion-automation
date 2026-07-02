// 웰페리온 지출현황 전용 Apps Script v1.0
// apps_script_todo.js와 동일 패턴 — 완전 독립 운영
// 시트: 지출현황 | 헤더 12열
// CRUD + 월별/카테고리별 집계 + 텔레그램 알림

// ─── 상수 ───
const EXPENSE_SPREADSHEET_ID = '17R_SjzG0BWCQYF21yIkR74xw8Wzajr54JFpEQ3h0_SE';
const EXPENSE_SHEET = '지출현황';

const EXPENSE_HEADERS = [
  'id', '날짜', '카테고리', '항목명', '금액',
  '결제수단', '비고', '영수증URL',
  '등록자', '등록일', '수정일', '승인상태'
];

const EXPENSE_CATEGORIES = [
  '시설유지보수',
  '인건비',
  '마케팅',
  '사무용품',
  '식음료',
  '외주용역',
  '보험/세금',
  '기타'
];

const PAYMENT_METHODS = [
  '법인카드',
  '계좌이체',
  '현금',
  '개인카드(후정산)',
  '기타'
];

const APPROVAL_STATUS = {
  '대기':   '#ff9800',
  '승인':   '#34a853',
  '반려':   '#ea4335',
  '보류':   '#9e9e9e'
};

// ─── ScriptProperties 헬퍼 ───
function _prop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

// ─── 시트 초기화 ───
function initExpenseSheet() {
  const ss = SpreadsheetApp.openById(EXPENSE_SPREADSHEET_ID);
  let sh = ss.getSheetByName(EXPENSE_SHEET);
  if (sh) return sh;

  sh = ss.insertSheet(EXPENSE_SHEET);
  sh.getRange(1, 1, 1, EXPENSE_HEADERS.length).setValues([EXPENSE_HEADERS]);
  sh.getRange(1, 1, 1, EXPENSE_HEADERS.length)
    .setFontWeight('bold')
    .setBackground('#1a73e8')
    .setFontColor('#ffffff');

  const widths = [150, 100, 110, 200, 100, 100, 250, 200, 80, 130, 130, 80];
  widths.forEach((w, i) => sh.setColumnWidth(i + 1, w));
  sh.setFrozenRows(1);

  // 금액 열 숫자 형식
  sh.getRange(2, EXPENSE_HEADERS.indexOf('금액') + 1, 999, 1)
    .setNumberFormat('#,##0');

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
  return 'EXP-' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMddHHmmss')
    + ('000' + new Date().getMilliseconds()).slice(-3);
}

function _readAll(sh) {
  const last = sh.getLastRow();
  if (last < 2) return [];
  const data = sh.getRange(2, 1, last - 1, EXPENSE_HEADERS.length).getValues();
  return data.map(row => {
    const obj = {};
    EXPENSE_HEADERS.forEach((h, i) => { obj[h] = row[i]; });
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

function _applyApprovalColor(sh, row, status) {
  const colIdx = EXPENSE_HEADERS.indexOf('승인상태') + 1;
  const color = APPROVAL_STATUS[status] || '#ffffff';
  sh.getRange(row, colIdx).setBackground(color).setFontColor('#ffffff');
}

// ─── CORS JSON 응답 ───
function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─── 텔레그램 알림 ───
function _notifyTelegram(text) {
  const token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  const chatId = _prop('CHAT_ID') || _prop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return;

  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log('텔레그램 알림 실패: ' + e.message);
  }
}

// ─── 영문↔한글 필드 매핑 ───
function _mapFields(body) {
  const map = {
    date: '날짜', category: '카테고리', itemName: '항목명', title: '항목명',
    amount: '금액', paymentMethod: '결제수단', note: '비고', memo: '비고',
    receiptUrl: '영수증URL', creator: '등록자', approval: '승인상태'
  };
  Object.keys(map).forEach(en => {
    if (body[en] !== undefined && !body[map[en]]) body[map[en]] = body[en];
  });
  return body;
}

// ═══════════════════════════════════════════
//  공용 액션 처리
// ═══════════════════════════════════════════
function _processExpenseAction(body) {
  body = _mapFields(body);
  const action = body.action || '';

  // ─── 목록 조회 ───
  if (action === 'expense_list') {
    const sh = initExpenseSheet();
    let items = _readAll(sh);

    const month = body.month || '';
    if (month) {
      items = items.filter(r => String(r['날짜']).startsWith(month));
    }
    const cat = body.category || body['카테고리'] || '';
    if (cat) {
      items = items.filter(r => String(r['카테고리']) === cat);
    }
    const creator = body.creator || body['등록자'] || '';
    if (creator) {
      items = items.filter(r => String(r['등록자']) === creator);
    }

    return _json({ ok: true, count: items.length, data: items });
  }

  // ─── 카테고리/결제수단 목록 ───
  if (action === 'expense_meta') {
    return _json({
      ok: true,
      categories: EXPENSE_CATEGORIES,
      paymentMethods: PAYMENT_METHODS,
      approvalStatuses: Object.keys(APPROVAL_STATUS)
    });
  }

  // ─── 새 지출 추가 ───
  if (action === 'expense_add') {
    const sh = initExpenseSheet();
    const id = _genId();
    const now = _now();
    const amount = Number(body['금액']) || 0;
    const row = [
      id,
      body['날짜'] || _today(),
      body['카테고리'] || '',
      body['항목명'] || '',
      amount,
      body['결제수단'] || '',
      body['비고'] || '',
      body['영수증URL'] || '',
      body['등록자'] || '',
      now, now,
      body['승인상태'] || '대기'
    ];
    const newRow = sh.getLastRow() + 1;
    sh.getRange(newRow, 1, 1, row.length).setValues([row]);
    _applyApprovalColor(sh, newRow, row[11]);

    // 금액 1원 이상이면 GM님 결재 알림
    if (amount > 0) {
      _notifyTelegram(
        '💰 <b>[지출 등록]</b>\n'
        + '항목: ' + (body['항목명'] || '-') + '\n'
        + '금액: ' + amount.toLocaleString() + '원\n'
        + '카테고리: ' + (body['카테고리'] || '-') + '\n'
        + 'ID: ' + id
      );
    }
    return _json({ ok: true, id: id, message: '지출이 등록되었습니다.' });
  }

  // ─── 수정 ───
  if (action === 'expense_update') {
    const sh = initExpenseSheet();
    const id = body.id;
    if (!id) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(sh, id);
    if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });

    const existing = sh.getRange(rowNum, 1, 1, EXPENSE_HEADERS.length).getValues()[0];
    EXPENSE_HEADERS.forEach((h, i) => {
      if (h === 'id' || h === '등록일' || h === '등록자') return;
      if (body[h] !== undefined && body[h] !== null) existing[i] = body[h];
    });
    existing[EXPENSE_HEADERS.indexOf('수정일')] = _now();
    sh.getRange(rowNum, 1, 1, EXPENSE_HEADERS.length).setValues([existing]);
    _applyApprovalColor(sh, rowNum, existing[EXPENSE_HEADERS.indexOf('승인상태')]);
    return _json({ ok: true, id: id, message: '지출이 수정되었습니다.' });
  }

  // ─── 삭제 ───
  if (action === 'expense_delete') {
    const sh = initExpenseSheet();
    const id = body.id;
    if (!id) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(sh, id);
    if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
    sh.deleteRow(rowNum);
    return _json({ ok: true, id: id, message: '지출이 삭제되었습니다.' });
  }

  // ─── 월별/카테고리별 집계 ───
  if (action === 'expense_summary') {
    const sh = initExpenseSheet();
    const items = _readAll(sh);
    const month = body.month || '';

    const filtered = month
      ? items.filter(r => String(r['날짜']).startsWith(month))
      : items;

    // 카테고리별 합계
    const byCategory = {};
    let total = 0;
    filtered.forEach(r => {
      const cat = String(r['카테고리']) || '기타';
      const amt = Number(r['금액']) || 0;
      byCategory[cat] = (byCategory[cat] || 0) + amt;
      total += amt;
    });

    // 월별 합계
    const byMonth = {};
    items.forEach(r => {
      const d = String(r['날짜']);
      const m = d.substring(0, 7);
      const amt = Number(r['금액']) || 0;
      byMonth[m] = (byMonth[m] || 0) + amt;
    });

    // 결제수단별 합계
    const byPayment = {};
    filtered.forEach(r => {
      const pm = String(r['결제수단']) || '기타';
      const amt = Number(r['금액']) || 0;
      byPayment[pm] = (byPayment[pm] || 0) + amt;
    });

    return _json({
      ok: true,
      month: month || '전체',
      total: total,
      count: filtered.length,
      byCategory: byCategory,
      byMonth: byMonth,
      byPayment: byPayment
    });
  }

  // ─── 승인 처리 ───
  if (action === 'expense_approve') {
    const sh = initExpenseSheet();
    const id = body.id;
    const status = body['승인상태'] || '승인';
    if (!id) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(sh, id);
    if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });

    const approvalCol = EXPENSE_HEADERS.indexOf('승인상태') + 1;
    const modCol = EXPENSE_HEADERS.indexOf('수정일') + 1;
    sh.getRange(rowNum, approvalCol).setValue(status);
    sh.getRange(rowNum, modCol).setValue(_now());
    _applyApprovalColor(sh, rowNum, status);
    return _json({ ok: true, id: id, message: '승인 상태가 변경되었습니다.' });
  }

  return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

// ═══════════════════════════════════════════
//  doGet / doPost
// ═══════════════════════════════════════════
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';

    // expense_ 계열 action은 모두 공용 처리기로
    if (action.startsWith('expense_')) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      body.action = action;
      return _processExpenseAction(body);
    }

    return _json({ ok: false, error: '알 수 없는 action: ' + action });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processExpenseAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
