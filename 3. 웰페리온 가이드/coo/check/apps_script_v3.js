// 웰페리온 지원팀 일일 점검 - Apps Script v3.0
// 3시트 구조: 남성구역 / 여성구역 / 공용구역 + 점검자
// v2 → v3 변경: 성별구역 열 삭제, 제자리 갱신(중복 방지), 점검자 자동 배정, 근무시간 기입

const SHEET_MALE   = '남성구역';
const SHEET_FEMALE = '여성구역';
const SHEET_COMMON = '공용구역';
const SHEET_STAFF  = '점검자';
const SHEET_ITEMS  = '점검항목';   // GM 편집 점검 항목 마스터 (시트 영구 저장)

const ITEM_HEADERS = ['항목ID','카테고리','항목명','상세','성별','시간대','정렬'];

const BOT_TOKEN = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
const CHAT_ID   = PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID');

const HEADERS = [
  '날짜','항목ID','항목명','카테고리','시간대',
  '점검결과','이슈메모','노하우','제출상태','제출시각',
  '점검자','교대'
];

// ─── 남성/여성 공통 항목 (A 사우나 + B 락커룸) ───
const ZONE_ITEMS = [
  { id:'a1',   name:'A-1 사우나 탕',              cat:'A 사우나 점검',    slot:'오픈 05:30~08:00' },
  { id:'a2',   name:'A-2 건/습식 사우나',          cat:'A 사우나 점검',    slot:'오픈 05:30~08:00' },
  { id:'a3',   name:'A-3 사우나 내부',             cat:'A 사우나 점검',    slot:'오픈 05:30~08:00' },
  { id:'b6',   name:'요일별 락커 청소',             cat:'B-6 데일리 락커',  slot:'오픈 05:30~08:00' },
  { id:'b1',   name:'B-1 파우더',                  cat:'B 락커룸',         slot:'오전 08:00~12:00' },
  { id:'b2',   name:'B-2 휴게실',                  cat:'B 락커룸',         slot:'오전 08:00~12:00' },
  { id:'b3',   name:'B-3 찜질방/수면실',            cat:'B 락커룸',         slot:'오전 08:00~12:00' },
  { id:'b4',   name:'B-4 마루바닥',                cat:'B 락커룸',         slot:'오전 08:00~12:00' },
  { id:'b5',   name:'B-5 사우나 화장실',            cat:'B 락커룸',         slot:'오전 08:00~12:00' },
  { id:'a_pm', name:'A-1/A-2/A-3 오후 재점검',     cat:'A 사우나 재점검',  slot:'오후 14:00~18:00' },
  { id:'b_pm', name:'B-2/B-3/B-4/B-5 오후 재점검', cat:'B 락커룸 재점검',  slot:'오후 14:00~18:00' },
  { id:'b_ev', name:'B 락커룸 저녁 재점검',         cat:'저녁 점검',        slot:'저녁 19:00~22:00' },
  { id:'cls2', name:'사우나/파우더 최종 체크',       cat:'마감 점검',        slot:'마감 22:00~22:30' },
];

// ─── 공용구역 항목 (C 세탁물 + D 외부 + E 외곽 + 인수인계 + 마감) ───
const COMMON_ITEMS = [
  { id:'c1a',  name:'세탁물 입고 운반',            cat:'C 세탁물 (오전)',   slot:'오전 08:00~12:00' },
  { id:'c1b',  name:'운동복/양말 상태 + 배치',     cat:'C 세탁물 (오전)',   slot:'오전 08:00~12:00' },
  { id:'c1c',  name:'타올류 상태 + 배치',          cat:'C 세탁물 (오전)',   slot:'오전 08:00~12:00' },
  { id:'e1',   name:'E-1 센터 복도 바닥',          cat:'E 외곽 청결',       slot:'오전 08:00~12:00' },
  { id:'e2',   name:'E-2 센터 거울/유리창',        cat:'E 외곽 청결',       slot:'오전 08:00~12:00' },
  { id:'e3',   name:'E-3 청소 비품 관리',          cat:'E 외곽 청결',       slot:'오전 08:00~12:00' },
  { id:'e4',   name:'E-4 헬스장',                  cat:'E 외곽 청결',       slot:'오전 08:00~12:00' },
  { id:'e5',   name:'E-5 골프장',                  cat:'E 외곽 청결',       slot:'오전 08:00~12:00' },
  { id:'d1',   name:'D-1 외부 화장실',             cat:'D 외부 (오전)',     slot:'오전 후반 10:00~12:00' },
  { id:'d2',   name:'D-2 복도 휴지통',             cat:'D 외부 (오전)',     slot:'오전 후반 10:00~12:00' },
  { id:'d3',   name:'D-3 메인 계단',               cat:'D 외부 (오전)',     slot:'오전 후반 10:00~12:00' },
  { id:'d4',   name:'D-4 메인 복도 휴게공간',      cat:'D 외부 (오전)',     slot:'오전 후반 10:00~12:00' },
  { id:'d5',   name:'D-5 분리수거장',              cat:'D 외부 (오전)',     slot:'오전 후반 10:00~12:00' },
  { id:'hw1',  name:'세탁물 출고 운반',            cat:'교대 인수인계',     slot:'인수인계 13:00~14:00' },
  { id:'hw2',  name:'인수인계 카톡 보고',          cat:'교대 인수인계',     slot:'인수인계 13:00~14:00' },
  { id:'d6',   name:'D-6 G.X룸',                  cat:'D 외부 (오후)',     slot:'오후 14:00~18:00' },
  { id:'d7',   name:'D-7 센터 화분',              cat:'D 외부 (오후)',     slot:'오후 14:00~18:00' },
  { id:'d9',   name:'D-9 수영장 계단',            cat:'D 외부 (오후)',     slot:'오후 14:00~18:00' },
  { id:'d8',   name:'D-8 키즈 샤워실',            cat:'저녁 점검',         slot:'저녁 19:00~22:00' },
  { id:'e6',   name:'E-6 주차장',                 cat:'저녁 점검',         slot:'저녁 19:00~22:00' },
  { id:'cls1', name:'세탁물 마감 출고',            cat:'마감 점검',         slot:'마감 22:00~22:30' },
  { id:'cls3', name:'전 구역 마감 확인',           cat:'마감 점검',         slot:'마감 22:00~22:30' },
];

// ─── 점검자 기본 데이터 (근무시간 포함) ───
const DEFAULT_STAFF = [
  ['남 반장',       '반장',       '중간', '남', '09:00~18:00', '09:00~18:00'],
  ['여 반장',       '반장',       '중간', '여', '09:00~18:00', '09:00~18:00'],
  ['여 오전 주임',  '사우나 주임', '오전', '여', '05:30~14:00', '07:30~14:00'],
  ['여 오후 주임',  '사우나 주임', '오후', '여', '13:00~22:30', '13:00~20:00'],
  ['남 오전 주임',  '사우나 주임', '오전', '남', '05:30~14:00', '07:30~14:00'],
  ['남 오후 주임',  '사우나 주임', '오후', '남', '13:00~22:30', '13:00~20:00'],
  ['중간 주임(남)', '중간 주임',   '중간', '남', '09:00~18:00', '09:00~18:00'],
  ['중간 주임(여)', '중간 주임',   '중간', '여', '09:00~18:00', '09:00~18:00'],
  ['탕청소 업체',   '탕청소',      '야간', '공통','22:30~05:30', '20:00~07:30'],
  ['','','','','',''],
  ['이경연',        '운영부 실장', '오후', '여', '13:00~22:30', '13:00~20:00'],
  ['임정은',        '운영부 M',    '중간', '여', '09:00~18:00', '09:00~18:00'],
  ['최준용',        '운영부 M',    '중간', '남', '09:00~18:00', '09:00~18:00'],
  ['윤병현',        '운영부 AM',   '오후', '남', '13:00~22:30', '13:00~20:00'],
];

// ─── 시간대 → 교대 매핑 ───
function slotToShift(slot) {
  if (slot.includes('05:30') || slot.includes('오전') || slot.includes('오픈')) return '오전';
  if (slot.includes('인수인계')) return '중간';
  return '오후';
}

// ─── 구역 + 시간대 → 기본 점검자 자동 배정 ───
function defaultInspector(sheetName, slot) {
  const shift = slotToShift(slot);
  if (sheetName === SHEET_MALE) {
    if (shift === '오전') return '남 오전 주임';
    return '남 오후 주임';
  }
  if (sheetName === SHEET_FEMALE) {
    if (shift === '오전') return '여 오전 주임';
    return '여 오후 주임';
  }
  if (shift === '오전') return '중간 주임(남)';
  if (shift === '중간') return '중간 주임(남)';
  return '중간 주임(여)';
}

function formatDate(d) {
  if (d instanceof Date) return Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd');
  return String(d);
}

function jsonRes(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ════════════════════════════════════════════
// 초기 세팅 (Apps Script 에디터에서 1회 실행)
// ════════════════════════════════════════════

function setupNewStructure() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  _createCheckSheet(ss, SHEET_MALE);
  _createCheckSheet(ss, SHEET_FEMALE);
  _createCheckSheet(ss, SHEET_COMMON);
  _createStaffSheet(ss);

  var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  _seedDate(ss.getSheetByName(SHEET_MALE),   today, ZONE_ITEMS,   SHEET_MALE);
  _seedDate(ss.getSheetByName(SHEET_FEMALE), today, ZONE_ITEMS,   SHEET_FEMALE);
  _seedDate(ss.getSheetByName(SHEET_COMMON), today, COMMON_ITEMS, SHEET_COMMON);

  Logger.log('setupNewStructure 완료: 3시트 + 점검자 + 오늘(' + today + ') 시드');
}

function _createCheckSheet(ss, name) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) { sheet = ss.insertSheet(name); } else { sheet.clear(); }
  sheet.appendRow(HEADERS);
  sheet.getRange(1, 1, 1, HEADERS.length)
    .setBackground('#2a2725').setFontColor('#B79F8A')
    .setFontWeight('bold').setHorizontalAlignment('center');
  sheet.setFrozenRows(1);
  var widths = [100,70,220,140,150,80,200,200,110,130,100,70];
  for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i+1, widths[i]);
}

function _createStaffSheet(ss) {
  var sheet = ss.getSheetByName(SHEET_STAFF);
  if (!sheet) { sheet = ss.insertSheet(SHEET_STAFF); } else { sheet.clear(); }
  var h = ['이름','역할(직함)','교대','성별구역','근무시간/평일','근무시간/주말&공휴일'];
  sheet.appendRow(h);
  sheet.getRange(1, 1, 1, h.length)
    .setBackground('#2a2725').setFontColor('#B79F8A')
    .setFontWeight('bold').setHorizontalAlignment('center');
  sheet.setFrozenRows(1);
  if (DEFAULT_STAFF.length > 0) {
    sheet.getRange(2, 1, DEFAULT_STAFF.length, 6).setValues(DEFAULT_STAFF);
  }
}

function _seedDate(sheet, date, items, sheetName) {
  var rows = items.map(function(item) {
    return [
      date, item.id, item.name, item.cat, item.slot,
      '미완료', '', '', '미제출', '',
      defaultInspector(sheetName, item.slot),
      slotToShift(item.slot)
    ];
  });
  if (rows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, HEADERS.length).setValues(rows);
  }
}

// ─── 기존 "일일점검" 시트에서 마이그레이션 (1회) ───
function migrateFromOldSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var old = ss.getSheetByName('일일점검');
  if (!old) { Logger.log('"일일점검" 시트 없음'); return; }

  setupNewStructure();

  var data = old.getDataRange().getValues();
  var seen = {};
  for (var i = 1; i < data.length; i++) {
    var itemId = String(data[i][1]);
    var dateStr = formatDate(data[i][0]);
    var key = dateStr + '::' + itemId;
    if (seen[key]) continue;
    seen[key] = true;

    var isZone = ZONE_ITEMS.some(function(it) { return it.id === itemId; });
    var isCommon = COMMON_ITEMS.some(function(it) { return it.id === itemId; });
    if (!isZone && !isCommon) continue;

    var targetName = isCommon ? SHEET_COMMON : SHEET_MALE;
    var target = ss.getSheetByName(targetName);
    target.appendRow([
      dateStr, itemId, String(data[i][2]), String(data[i][3]), String(data[i][4]),
      String(data[i][5]), String(data[i][6]||''), String(data[i][7]||''),
      String(data[i][8]), String(data[i][9]||''),
      String(data[i][10]) || defaultInspector(targetName, String(data[i][4])),
      String(data[i][11]) || slotToShift(String(data[i][4]))
    ]);
  }
  Logger.log('마이그레이션 완료 (중복 제거 포함). 기존 "일일점검"은 수동 삭제하세요.');
}

// ════════════════════════════════════════════
// API: 조회
// ════════════════════════════════════════════

function doGet(e) {
  var action = e.parameter.action || '';
  if (action === 'todo_list') return handleTodoGet(e.parameter);
  if (action === 'items')     return getItems();

  var date = e.parameter.date;
  if (!date) return jsonRes({ error: 'date required' });
  if (action === 'staff') return getStaff();

  var zone = e.parameter.zone;
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // v2 호환: zone 없으면 전체 병합 + v2 응답 필드
  var names = [];
  if (!zone || zone === 'all') {
    names = [SHEET_MALE, SHEET_FEMALE, SHEET_COMMON];
  } else {
    var zoneMap = { male: SHEET_MALE, female: SHEET_FEMALE, common: SHEET_COMMON };
    if (zoneMap[zone]) names.push(zoneMap[zone]);
  }

  var rows = [];
  names.forEach(function(name) {
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;
    var data = sheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]) === date || formatDate(data[i][0]) === date) {
        var submitStr = String(data[i][8] || '');
        var hasAm = submitStr.indexOf('오전') >= 0 || submitStr === '제출완료';
        var hasPm = submitStr.indexOf('오후') >= 0;
        var hasNight = submitStr.indexOf('야간') >= 0;
        rows.push({
          zone: name,
          itemId: String(data[i][1]),
          name: String(data[i][2]),
          cat: String(data[i][3]),
          slot: String(data[i][4]),
          checked: String(data[i][5]) === '완료',
          issue: String(data[i][6] || ''),
          tip: String(data[i][7] || ''),
          submitted: submitStr !== '미제출',
          submittedAt: String(data[i][9] || ''),
          submitter: String(data[i][10] || ''),
          shift: String(data[i][11] || ''),
          gender: name === SHEET_MALE ? 'm' : name === SHEET_FEMALE ? 'f' : 'all',
          submitted_am: hasAm,
          submittedAt_am: hasAm ? String(data[i][9] || '') : '',
          submitter_am: hasAm ? String(data[i][10] || '') : '',
          submitted_pm: hasPm,
          submittedAt_pm: hasPm ? String(data[i][9] || '') : '',
          submitter_pm: hasPm ? String(data[i][10] || '') : '',
          submitted_night: hasNight,
          submittedAt_night: hasNight ? String(data[i][9] || '') : '',
          submitter_night: hasNight ? String(data[i][10] || '') : ''
        });
      }
    }
  });
  return jsonRes({ date: date, zone: zone || 'all', rows: rows });
}

// ════════════════════════════════════════════
// API: 저장 (제자리 갱신 — 중복 방지)
// ════════════════════════════════════════════

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    if (body.action && body.action.indexOf('todo_') === 0) return handleTodoPost(body);
    if (body.action === 'save')      return handleSave(body);
    if (body.action === 'notify')    return handleNotify(body);
    if (body.action === 'seed')      return handleSeed(body);
    if (body.action === 'saveItems') return saveItems(body);
    return jsonRes({ error: 'unknown action' });
  } catch (err) {
    return jsonRes({ error: err.message });
  }
}

function handleSave(body) {
  if (!body.zone) return _handleSaveV2Compat(body);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var date = body.date;
  var zone = body.zone;
  var checks = body.checks || [];

  var sheetMap = { male: SHEET_MALE, female: SHEET_FEMALE, common: SHEET_COMMON };
  var sheetName = sheetMap[zone];
  if (!sheetName) return jsonRes({ error: 'invalid zone: ' + zone });

  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) return jsonRes({ error: 'sheet not found: ' + sheetName });

  var data = sheet.getDataRange().getValues();
  var existingMap = {};
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][0]) === date || formatDate(data[i][0]) === date) {
      existingMap[String(data[i][1])] = i + 1;
    }
  }

  var updated = 0, added = 0;
  var newRows = [];
  checks.forEach(function(c) {
    var rowNum = existingMap[c.itemId];
    var inspector = c.submitter || defaultInspector(sheetName, c.slot || '');
    var shift = c.shift || slotToShift(c.slot || '');
    var values = [
      date, c.itemId, c.name, c.cat, c.slot,
      c.checked ? '완료' : '미완료',
      c.issue || '', c.tip || '',
      body.submitStatus || '미제출',
      body.submittedAt || '',
      inspector, shift
    ];
    if (rowNum) {
      sheet.getRange(rowNum, 1, 1, HEADERS.length).setValues([values]);
      _applyRowStyle(sheet, rowNum, values);
      updated++;
    } else {
      newRows.push(values);
    }
  });

  if (newRows.length > 0) {
    var startRow = sheet.getLastRow() + 1;
    sheet.getRange(startRow, 1, newRows.length, HEADERS.length).setValues(newRows);
    for (var k = 0; k < newRows.length; k++) {
      _applyRowStyle(sheet, startRow + k, newRows[k]);
    }
    added = newRows.length;
  }
  return jsonRes({ success: true, updated: updated, added: added });
}

// ─── v2 프론트엔드 하위 호환 (zone 없이 genderTab으로 호출) ───

function _routeItem(itemId, cat, genderTab) {
  if (itemId.indexOf('_f') >= 0) return SHEET_FEMALE;
  if (itemId.indexOf('_m') >= 0) return SHEET_MALE;
  if (cat && (cat.charAt(0) === 'A' || cat.charAt(0) === 'B'
      || cat.indexOf('사우나') >= 0 || cat.indexOf('락커') >= 0
      || cat.indexOf('데일리') >= 0)) {
    return genderTab === 'f' ? SHEET_FEMALE : SHEET_MALE;
  }
  return SHEET_COMMON;
}

function _handleSaveV2Compat(body) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var date = body.date;
  var checks = body.checks || [];
  var gender = body.genderTab || 'm';

  var parts = [];
  if (body.submitted_am) parts.push('오전조 제출완료');
  if (body.submitted_pm) parts.push('오후조 제출완료');
  if (body.submitted_night) parts.push('야간조 제출완료');
  var submitStatus = parts.length > 0 ? parts.join(' / ') : '미제출';
  var submitAt = body.submittedAt_am || body.submittedAt_pm || body.submittedAt_night || '';
  var submitters = [];
  if (body.submitter_am) submitters.push(body.submitter_am);
  if (body.submitter_pm) submitters.push(body.submitter_pm);
  if (body.submitter_night) submitters.push(body.submitter_night);
  var submitter = submitters.join(' / ');

  var buckets = {};
  buckets[SHEET_MALE] = [];
  buckets[SHEET_FEMALE] = [];
  buckets[SHEET_COMMON] = [];
  checks.forEach(function(c) {
    var target = _routeItem(c.itemId, c.cat, gender);
    buckets[target].push(c);
  });

  var totalSaved = 0;
  [SHEET_MALE, SHEET_FEMALE, SHEET_COMMON].forEach(function(name) {
    var items = buckets[name];
    if (items.length === 0) return;
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;

    var data = sheet.getDataRange().getValues();
    for (var i = data.length - 1; i >= 1; i--) {
      if (String(data[i][0]) === date || formatDate(data[i][0]) === date) {
        sheet.deleteRow(i + 1);
      }
    }

    var newRows = items.map(function(c) {
      return [
        date, c.itemId, c.name, c.cat, c.slot,
        c.checked ? '완료' : '미완료',
        c.issue || '', c.tip || '',
        submitStatus, submitAt,
        submitter || defaultInspector(name, c.slot || ''),
        c.shift || slotToShift(c.slot || '')
      ];
    });
    if (newRows.length > 0) {
      var startRow = sheet.getLastRow() + 1;
      sheet.getRange(startRow, 1, newRows.length, HEADERS.length).setValues(newRows);
      for (var k = 0; k < newRows.length; k++) {
        _applyRowStyle(sheet, startRow + k, newRows[k]);
      }
      totalSaved += newRows.length;
    }
  });

  return jsonRes({ success: true, saved: totalSaved });
}

function _applyRowStyle(sheet, row, values) {
  var r = sheet.getRange(row, 6);
  if (values[5] === '완료') { r.setBackground('#e6f3ea').setFontColor('#2c8a4f'); }
  else { r.setBackground('#f5f2ef').setFontColor('#8c8b83'); }
  if (values[6] && String(values[6]).length > 0) {
    sheet.getRange(row, 7).setBackground('#fce8e4').setFontColor('#c0392b');
  }
  if (values[7] && String(values[7]).length > 0) {
    sheet.getRange(row, 8).setBackground('#f0ebf8').setFontColor('#7b5ea7');
  }
  if (values[8] && values[8] !== '미제출') {
    sheet.getRange(row, 9).setBackground('#e6f3ea').setFontColor('#2c8a4f');
  }
}

// ─── 날짜별 빈 데이터 시드 ───
function handleSeed(body) {
  var date = body.date;
  if (!date) return jsonRes({ error: 'date required' });
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var zones = [
    { name: SHEET_MALE,   items: ZONE_ITEMS },
    { name: SHEET_FEMALE, items: ZONE_ITEMS },
    { name: SHEET_COMMON, items: COMMON_ITEMS },
  ];
  var seeded = 0;
  zones.forEach(function(z) {
    var sheet = ss.getSheetByName(z.name);
    if (!sheet) return;
    var data = sheet.getDataRange().getValues();
    var exists = false;
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]) === date || formatDate(data[i][0]) === date) { exists = true; break; }
    }
    if (exists) return;
    _seedDate(sheet, date, z.items, z.name);
    seeded += z.items.length;
  });
  return jsonRes({ success: true, seeded: seeded });
}

// ════════════════════════════════════════════
// 텔레그램 / 점검자 / 유틸
// ════════════════════════════════════════════

function handleNotify(body) {
  if (!BOT_TOKEN || !CHAT_ID) return jsonRes({ success: false, reason: 'no telegram config' });
  var msg = body.message || '';
  if (!msg) return jsonRes({ success: false, reason: 'empty message' });
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: CHAT_ID, text: msg, parse_mode: 'HTML' })
    });
    return jsonRes({ success: true });
  } catch (err) {
    return jsonRes({ success: false, reason: err.message });
  }
}

function getStaff() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_STAFF);
  if (!sheet) return jsonRes({ staff: [] });
  var data = sheet.getDataRange().getValues();
  var staff = [];
  for (var i = 1; i < data.length; i++) {
    if (data[i][0]) {
      staff.push({
        name: String(data[i][0]),
        role: String(data[i][1] || ''),
        shift: String(data[i][2] || ''),
        gender: String(data[i][3] || ''),
        weekdayHours: String(data[i][4] || ''),
        weekendHours: String(data[i][5] || '')
      });
    }
  }
  return jsonRes({ staff: staff });
}

// ════════════════════════════════════════════
// 점검 항목 마스터 (GM 편집 — 시트 영구 저장)
// ════════════════════════════════════════════

// ─── 점검항목 시트 자동 생성 ───
function initItemSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (sheet) return sheet;
  sheet = ss.insertSheet(SHEET_ITEMS);
  sheet.appendRow(ITEM_HEADERS);
  sheet.getRange(1, 1, 1, ITEM_HEADERS.length)
    .setBackground('#2a2725').setFontColor('#B79F8A')
    .setFontWeight('bold').setHorizontalAlignment('center');
  sheet.setFrozenRows(1);
  var widths = [180, 180, 240, 360, 80, 180, 70];
  for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i + 1, widths[i]);
  return sheet;
}

// ─── 항목 조회 (GET ?action=items) ───
function getItems() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ items: [] });
  var data = sheet.getDataRange().getValues();
  var items = [];
  for (var i = 1; i < data.length; i++) {
    if (!data[i][0] && !data[i][2]) continue; // id·항목명 모두 없으면 건너뜀
    items.push({
      id:     String(data[i][0] || ''),
      cat:    String(data[i][1] || ''),
      name:   String(data[i][2] || ''),
      detail: String(data[i][3] || ''),
      gender: String(data[i][4] || 'all'),
      slot:   String(data[i][5] || ''),
      order:  data[i][6] !== '' && data[i][6] != null ? Number(data[i][6]) : (i)
    });
  }
  return jsonRes({ items: items });
}

// ─── 항목 저장 (POST {action:'saveItems', items:[...]}) — 전체 재기록 ───
function saveItems(body) {
  var items = body.items || [];
  var sheet = initItemSheet();
  // 헤더만 남기고 기존 데이터 전체 삭제
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).clearContent();
  }
  var rows = items.map(function (it, idx) {
    return [
      String(it.id || ''),
      String(it.cat || ''),
      String(it.name || ''),
      String(it.detail || ''),
      String(it.gender || 'all'),
      String(it.slot || ''),
      it.order !== undefined && it.order !== '' ? it.order : (idx + 1)
    ];
  });
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, ITEM_HEADERS.length).setValues(rows);
  }
  return jsonRes({ ok: true, count: rows.length });
}

// ─── 항목 마스터 1회 시드 (Apps Script 에디터에서 1회 실행) ───
// 현재 기본 항목(ZONE_ITEMS + COMMON_ITEMS)을 점검항목 시트에 채운다.
function seedItemMaster() {
  var sheet = initItemSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).clearContent();
  }
  var rows = [];
  var order = 1;
  // 남/여 공통 구역 항목
  ZONE_ITEMS.forEach(function (it) {
    rows.push([it.id, it.cat, it.name, '', 'all', it.slot, order++]);
  });
  // 공용 구역 항목
  COMMON_ITEMS.forEach(function (it) {
    rows.push([it.id, it.cat, it.name, '', 'all', it.slot, order++]);
  });
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, ITEM_HEADERS.length).setValues(rows);
  }
  Logger.log('seedItemMaster 완료: ' + rows.length + '개 항목 시드');
}

// ─── 중복 제거 유틸 (신규 시트 대상, 1회 실행) ───
function removeDuplicates() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  [SHEET_MALE, SHEET_FEMALE, SHEET_COMMON].forEach(function(name) {
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;
    var data = sheet.getDataRange().getValues();
    var seen = {};
    var toDelete = [];
    for (var i = 1; i < data.length; i++) {
      var key = formatDate(data[i][0]) + '::' + String(data[i][1]);
      if (seen[key]) { toDelete.push(i + 1); } else { seen[key] = true; }
    }
    for (var j = toDelete.length - 1; j >= 0; j--) { sheet.deleteRow(toDelete[j]); }
    if (toDelete.length > 0) Logger.log(name + ': 중복 ' + toDelete.length + '행 삭제');
  });
  Logger.log('removeDuplicates 완료');
}

// ─── 매일 자동 시드 (트리거 등록용) ───
function dailySeed() {
  var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  handleSeed({ date: today });
  Logger.log('dailySeed 완료: ' + today);
}

function setupTelegram() {
  var props = PropertiesService.getScriptProperties();
  Logger.log('BOT_TOKEN=' + props.getProperty('TELEGRAM_BOT_TOKEN'));
  Logger.log('CHAT_ID=' + props.getProperty('TELEGRAM_CHAT_ID'));
}

// ════════════════════════════════════════════
// TO DO LIST CRUD (멀티유저 시스템)
// ════════════════════════════════════════════

const SHEET_TODO = 'TODO';
const TODO_HEADERS = ['id','업무명','카테고리','담당자','시작일','종료일','내용','상태','결재요청','생성일','수정일'];

// ─── TODO 시트 자동 생성 ───
function initTodoSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_TODO);
  if (sheet) return sheet;
  sheet = ss.insertSheet(SHEET_TODO);
  sheet.appendRow(TODO_HEADERS);
  sheet.getRange(1, 1, 1, TODO_HEADERS.length)
    .setBackground('#2a2725').setFontColor('#B79F8A')
    .setFontWeight('bold').setHorizontalAlignment('center');
  sheet.setFrozenRows(1);
  var widths = [120, 240, 130, 140, 110, 110, 300, 80, 80, 130, 130];
  for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i + 1, widths[i]);
  Logger.log('TODO 시트 생성 완료');
  return sheet;
}

// ─── TODO 조회 (GET) ───
function handleTodoGet(params) {
  var sheet = initTodoSheet();
  var data = sheet.getDataRange().getValues();
  var owner = params.owner || '';
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (!row[0]) continue; // id 없으면 건너뜀
    if (owner && String(row[3]).indexOf(owner) < 0) continue;
    rows.push({
      id: String(row[0]),
      title: String(row[1] || ''),
      category: String(row[2] || ''),
      owner: String(row[3] || ''),
      startDate: row[4] ? formatDate(row[4]) : '',
      endDate: row[5] ? formatDate(row[5]) : '',
      content: String(row[6] || ''),
      status: String(row[7] || '진행중'),
      approval: String(row[8] || ''),
      createdAt: row[9] ? formatDate(row[9]) : '',
      updatedAt: row[10] ? formatDate(row[10]) : ''
    });
  }
  return jsonRes({ success: true, todos: rows });
}

// ─── TODO 쓰기 (POST) ───
function handleTodoPost(body) {
  var action = body.action;
  if (action === 'todo_add')    return todoAdd(body);
  if (action === 'todo_update') return todoUpdate(body);
  if (action === 'todo_delete') return todoDelete(body);
  if (action === 'todo_done')   return todoDone(body);
  return jsonRes({ error: 'unknown todo action: ' + action });
}

// ─── 추가 ───
function todoAdd(body) {
  var sheet = initTodoSheet();
  var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
  var id = 'TD-' + new Date().getTime();
  var row = [
    id,
    body.title || '',
    body.category || '',
    body.owner || '',
    body.startDate || '',
    body.endDate || '',
    body.content || '',
    body.status || '진행중',
    body.approval || '',
    now,
    now
  ];
  sheet.appendRow(row);
  var lastRow = sheet.getLastRow();
  _applyTodoRowStyle(sheet, lastRow, row);
  return jsonRes({ success: true, id: id, action: 'added' });
}

// ─── 수정 ───
function todoUpdate(body) {
  if (!body.id) return jsonRes({ error: 'id required' });
  var sheet = initTodoSheet();
  var data = sheet.getDataRange().getValues();
  var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][0]) === body.id) {
      var row = [
        body.id,
        body.title !== undefined ? body.title : String(data[i][1]),
        body.category !== undefined ? body.category : String(data[i][2]),
        body.owner !== undefined ? body.owner : String(data[i][3]),
        body.startDate !== undefined ? body.startDate : (data[i][4] ? formatDate(data[i][4]) : ''),
        body.endDate !== undefined ? body.endDate : (data[i][5] ? formatDate(data[i][5]) : ''),
        body.content !== undefined ? body.content : String(data[i][6]),
        body.status !== undefined ? body.status : String(data[i][7]),
        body.approval !== undefined ? body.approval : String(data[i][8]),
        data[i][9] ? formatDate(data[i][9]) : now,
        now
      ];
      sheet.getRange(i + 1, 1, 1, TODO_HEADERS.length).setValues([row]);
      _applyTodoRowStyle(sheet, i + 1, row);
      return jsonRes({ success: true, id: body.id, action: 'updated' });
    }
  }
  return jsonRes({ error: 'not found: ' + body.id });
}

// ─── 삭제 ───
function todoDelete(body) {
  if (!body.id) return jsonRes({ error: 'id required' });
  var sheet = initTodoSheet();
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][0]) === body.id) {
      sheet.deleteRow(i + 1);
      return jsonRes({ success: true, id: body.id, action: 'deleted' });
    }
  }
  return jsonRes({ error: 'not found: ' + body.id });
}

// ─── 완료 ───
function todoDone(body) {
  if (!body.id) return jsonRes({ error: 'id required' });
  var sheet = initTodoSheet();
  var data = sheet.getDataRange().getValues();
  var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][0]) === body.id) {
      sheet.getRange(i + 1, 8).setValue('완료');  // 상태
      sheet.getRange(i + 1, 11).setValue(now);     // 수정일
      _applyTodoRowStyle(sheet, i + 1, data[i]);
      return jsonRes({ success: true, id: body.id, action: 'done' });
    }
  }
  return jsonRes({ error: 'not found: ' + body.id });
}

// ─── TODO 행 스타일 ───
function _applyTodoRowStyle(sheet, row, values) {
  var statusCell = sheet.getRange(row, 8);
  var status = String(values[7] || '');
  if (status === '완료') {
    statusCell.setBackground('#e6f3ea').setFontColor('#2c8a4f');
  } else if (status === '보류') {
    statusCell.setBackground('#fef3e2').setFontColor('#c0851b');
  } else {
    statusCell.setBackground('#f5f2ef').setFontColor('#8c8b83');
  }
  if (String(values[8]) === 'Y') {
    sheet.getRange(row, 9).setBackground('#fce8e4').setFontColor('#c0392b');
  }
}
