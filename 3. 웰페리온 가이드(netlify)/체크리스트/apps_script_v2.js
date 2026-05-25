// 웰페리온 지원팀 일일 점검 - Apps Script v2.0
// 시트: "일일점검" (데이터) + "점검자" (스태프)

const SHEET_NAME = '일일점검';
const STAFF_SHEET = '점검자';
const BOT_TOKEN = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
const CHAT_ID = PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID');

function doGet(e) {
  const date = e.parameter.date;
  if (!date) return jsonRes({ error: 'date required' });

  const action = e.parameter.action;
  if (action === 'staff') return getStaff();

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) return jsonRes({ rows: [] });

  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const rows = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    if (String(row[0]) === date || formatDate(row[0]) === date) {
      rows.push({
        itemId: String(row[1]),
        name: String(row[2]),
        cat: String(row[3]),
        slot: String(row[4]),
        checked: String(row[5]) === '완료',
        issue: String(row[6] || ''),
        tip: String(row[7] || ''),
        submitted: String(row[8]) === '제출완료',
        submittedAt: String(row[9] || ''),
        submitter: String(row[10] || ''),
        shift: String(row[11] || ''),
        gender: String(row[12] || ''),
        submitted_am: String(row[8]).includes('오전') || String(row[8]) === '제출완료',
        submittedAt_am: String(row[9] || ''),
        submitter_am: String(row[10] || ''),
        submitted_pm: String(row[8]).includes('오후'),
        submittedAt_pm: '',
        submitter_pm: ''
      });
    }
  }
  return jsonRes({ rows });
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const action = body.action;

    if (action === 'save') return handleSave(body);
    if (action === 'notify') return handleNotify(body);

    return jsonRes({ error: 'unknown action' });
  } catch (err) {
    return jsonRes({ error: err.message });
  }
}

function handleSave(body) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);

  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow([
      '날짜', '항목ID', '항목명', '카테고리', '시간대',
      '점검결과', '이슈메모', '노하우', '제출상태', '제출시각',
      '점검자', '교대', '성별구역'
    ]);
  }

  const date = body.date;
  const checks = body.checks || [];

  // 기존 날짜 데이터 삭제 후 재입력
  const data = sheet.getDataRange().getValues();
  const rowsToDelete = [];
  for (let i = data.length - 1; i >= 1; i--) {
    if (String(data[i][0]) === date || formatDate(data[i][0]) === date) {
      rowsToDelete.push(i + 1);
    }
  }
  rowsToDelete.forEach(r => sheet.deleteRow(r));

  // 제출 상태 결정
  let submitStatus = '미제출';
  const parts = [];
  if (body.submitted_am) parts.push('오전조 제출완료');
  if (body.submitted_pm) parts.push('오후조 제출완료');
  if (body.submitted_night) parts.push('야간조 제출완료');
  if (parts.length > 0) submitStatus = parts.join(' / ');

  let submitAt = '';
  if (body.submittedAt_am) submitAt = body.submittedAt_am;
  if (body.submittedAt_pm) submitAt = body.submittedAt_pm;
  if (body.submittedAt_night) submitAt = body.submittedAt_night;

  let submitter = '';
  const submitters = [];
  if (body.submitter_am) submitters.push(body.submitter_am);
  if (body.submitter_pm) submitters.push(body.submitter_pm);
  if (body.submitter_night) submitters.push(body.submitter_night);
  submitter = submitters.join(' / ');

  // 새 데이터 입력
  const newRows = checks.map(c => [
    date,
    c.itemId,
    c.name,
    c.cat,
    c.slot,
    c.checked ? '완료' : '미완료',
    c.issue || '',
    c.tip || '',
    submitStatus,
    submitAt,
    submitter,
    c.shift || '',
    c.gender || ''
  ]);

  if (newRows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, newRows.length, 13).setValues(newRows);
  }

  return jsonRes({ success: true });
}

function handleNotify(body) {
  if (!BOT_TOKEN || !CHAT_ID) return jsonRes({ success: false, reason: 'no telegram config' });

  const msg = body.message || '';
  if (!msg) return jsonRes({ success: false, reason: 'empty message' });

  try {
    const url = 'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage';
    UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({
        chat_id: CHAT_ID,
        text: msg,
        parse_mode: 'HTML'
      })
    });
    return jsonRes({ success: true });
  } catch (err) {
    return jsonRes({ success: false, reason: err.message });
  }
}

function getStaff() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(STAFF_SHEET);
  if (!sheet) return jsonRes({ staff: [] });

  const data = sheet.getDataRange().getValues();
  const staff = [];
  for (let i = 1; i < data.length; i++) {
    if (data[i][0]) {
      staff.push({
        name: String(data[i][0]),
        role: String(data[i][1] || ''),
        shift: String(data[i][2] || ''),
        gender: String(data[i][3] || '')
      });
    }
  }
  return jsonRes({ staff });
}

function formatDate(d) {
  if (d instanceof Date) {
    return Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd');
  }
  return String(d);
}

function jsonRes(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// 초기 설정 (1회만 실행)
// 스크립트 속성에 텔레그램 봇 토큰과 채팅 ID를 설정합니다
function setupTelegram() {
  const props = PropertiesService.getScriptProperties();
  // 아래 값을 실제 값으로 변경 후 1회 실행
  // props.setProperty('TELEGRAM_BOT_TOKEN', '여기에_봇_토큰');
  // props.setProperty('TELEGRAM_CHAT_ID', '여기에_채팅_ID');
  Logger.log('현재 설정: BOT_TOKEN=' + props.getProperty('TELEGRAM_BOT_TOKEN'));
  Logger.log('현재 설정: CHAT_ID=' + props.getProperty('TELEGRAM_CHAT_ID'));
}
