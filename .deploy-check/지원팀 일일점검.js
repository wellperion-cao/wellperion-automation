// 웰페리온 지원팀 일일 점검 - Apps Script v3.0
// 3시트 구조: 남성구역 / 여성구역 / 공용구역 + 점검자
// v2 → v3 변경: 성별구역 열 삭제, 제자리 갱신(중복 방지), 점검자 자동 배정, 근무시간 기입

const SHEET_MALE   = '남성구역';
const SHEET_FEMALE = '여성구역';
const SHEET_COMMON = '공용구역';
const SHEET_STAFF  = '점검자';
const SHEET_ITEMS  = '점검항목';   // GM 편집 점검 항목 마스터 (시트 영구 저장)

// S1(2026-06-10 시토): 측정형 항목 식별 — '타입'(check|measure) + '필드정의'(measure 영문키 목록) 2열 추가.
// 기존 항목은 '타입' 빈값 → 'check' 안전 폴백. 이 단계는 동작 변화 없음(프론트가 아직 안 읽음).
// S4 갭②(2026-06-10 시토): '부서'(dept) 10열 추가 — 점검항목 마스터가 전 dept 공유 시트라
// getItems/saveItems가 dept 무필터면 시설 measure 항목이 지원·운영·주차 화면에 빈칸 노출.
// 빈값 → 'support'(레거시 기존 항목=원본 지원부) 안전 폴백.
const ITEM_HEADERS = ['항목ID','카테고리','항목명','상세','성별','시간대','정렬','타입','필드정의','부서'];
const ITEM_DEPT_COL = 9;   // '부서' 0-based 인덱스(10번째 열)
function _itemDept(v){ var d = String(v == null ? '' : v).trim(); return d || 'support'; }

const BOT_TOKEN = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
const CHAT_ID   = PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID');

const HEADERS = [
  '날짜','항목ID','항목명','카테고리','시간대',
  '점검결과','이슈메모','노하우','제출상태','제출시각',
  '점검자','교대',
  // S2(2026-06-10 시토): 13열 측정값 — measure 영문키 JSON 문자열 패스스루(예 {"ph":7.2}).
  // payload에 measure 없으면 빈칸. boolean 점검(6열 '완료'/'미완료')·완료율 판정 영향 0.
  '측정값',
  // F1(2026-06-11 시우): 14열 반영완료 — 이슈/노하우 후속조치 완료 플래그('Y'/빈값).
  // 완료율·집계와 무관(별도 컬럼). payload에 reflected 없으면 빈칸.
  '반영완료'
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
  { id:'tang1',name:'탕 청소 업체 작업 완료 확인', cat:'F 탕청소 현황',     slot:'마감 22:00~22:30' },
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

// S2(2026-06-10 시토): measure 값을 13열 저장용 문자열로 정규화.
// 문자열이면 그대로(클라가 보낸 영문키 JSON), 객체면 JSON.stringify, 없으면 빈문자.
// boolean 점검·완료율 판정과 무관 — 단순 패스스루.
function _measureStr(m) {
  if (m === undefined || m === null || m === '') return '';
  if (typeof m === 'string') return m;
  try { return JSON.stringify(m); } catch (e) { return ''; }
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
  var widths = [100,70,220,140,150,80,200,200,110,130,100,70,180,90];  // 13열 측정값 + 14열 반영완료
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
      slotToShift(item.slot),
      '',  // S2: 13열 측정값 — 시드 시 빈칸
      ''   // F1: 14열 반영완료 — 시드 시 빈칸
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
      String(data[i][11]) || slotToShift(String(data[i][4])),
      String(data[i][12] || ''),  // S2: 13열 측정값(구 데이터엔 없음 → 빈칸)
      String(data[i][13] || '')   // F1: 14열 반영완료(구 데이터엔 없음 → 빈칸)
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
  if (action === 'items')     return getItems(e.parameter);
  if (action === 'board')     return getBoard(e.parameter);
  if (action === 'weekly')    return handleWeekly(e.parameter);
  if (action === 'issuelog')  return handleIssueLogGet(e.parameter);
  if (action === 'setup_issue_tabs') { setupIssueLogSheets(); return jsonRes({ok:true,msg:'이슈대장 탭 생성 완료'}); }
  if (action === 'setup_facility_tabs') { return setupFacilitySheets(); }
  if (action === 'setup_dept_tabs') { return setupDeptSheets(e.parameter.dept || 'support'); }
  if (action === 'migrate_item_dept') { return jsonRes(migrateItemDept()); }

  var date = e.parameter.date;
  if (!date) return jsonRes({ error: 'date required' });
  if (action === 'staff') return getStaff();

  var zone = e.parameter.zone;
  var dept = e.parameter.dept || 'support';
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // dept 파라미터로 전 부서 전용 탭 분기 (S5 거짓완료 차단 · 2026-06-10 시토)
  var tabs = _deptTabs(dept);
  var baseMale   = tabs.male;
  var baseFemale = tabs.female;
  var baseCommon = tabs.common;

  // 해당 부서 전용 탭이 없으면 데이터 부재로 빈 응답 (타 부서 탭 폴백 없음 → 거짓완료 0)
  var names = [];
  if (!zone || zone === 'all') {
    names = [baseMale, baseFemale, baseCommon];
  } else {
    var zoneMap = { male: baseMale, female: baseFemale, common: baseCommon };
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
          measure: String(data[i][12] || ''),   // S2: 13열 측정값(없으면 빈문자)
          reflected: String(data[i][13] || '') === 'Y',   // F1: 14열 반영완료
          gender: name === baseMale ? 'm' : name === baseFemale ? 'f' : 'all',
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
  return jsonRes({ date: date, zone: zone || 'all', rows: rows, groupSubmits: _getGroupSubmits(date) });
}

// ─── 그룹별 제출 영속 (2026-06-05 GM) — PropertiesService 날짜별 JSON, 병합·빈값 덮어쓰기 방지 ───
var GSUB_PROP_PREFIX = 'gsub_';
function _saveGroupSubmits(date, gs) {
  if (!date || !gs || typeof gs !== 'object') return;
  var props = PropertiesService.getScriptProperties();
  var key = GSUB_PROP_PREFIX + date;
  var existing = {};
  try { existing = JSON.parse(props.getProperty(key) || '{}'); } catch (e) {}
  Object.keys(gs).forEach(function (k) { if (gs[k]) existing[k] = gs[k]; });  // 제출분만 추가/갱신(해제 없음)
  props.setProperty(key, JSON.stringify(existing));
}
function _getGroupSubmits(date) {
  try { return JSON.parse(PropertiesService.getScriptProperties().getProperty(GSUB_PROP_PREFIX + date) || '{}'); }
  catch (e) { return {}; }
}

// ════════════════════════════════════════════
// API: 저장 (제자리 갱신 — 중복 방지)
// ════════════════════════════════════════════

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    if (body.action && body.action.indexOf('todo_') === 0) return handleTodoPost(body);
    if (body.action === 'save')           return handleSave(body);
    if (body.action === 'notify')         return handleNotify(body);
    if (body.action === 'seed')           return handleSeed(body);
    if (body.action === 'saveItems')      return saveItems(body);
    if (body.action === 'saveBoard')      return saveBoard(body);
    if (body.action === 'issuelog_add')   return handleIssueLogAdd(body);
    if (body.action === 'issuelog_update') return handleIssueLogUpdate(body);
    if (body.action === 'snapshot_append') return handleSnapshotAppend(body);   // F3: 제출 스냅샷 적립
    return jsonRes({ error: 'unknown action' });
  } catch (err) {
    return jsonRes({ error: err.message });
  }
}

function handleSave(body) {
  _saveGroupSubmits(body.date, body.groupSubmits);   // 그룹별 제출 영속(zone/v2 두 경로 공통) — 2026-06-05 GM
  if (!body.zone) return _handleSaveV2Compat(body);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var date = body.date;
  var zone = body.zone;
  var dept = body.dept || 'support';
  var checks = body.checks || [];

  // dept별 전용 탭으로 라우팅 (S5 단일 출처 _deptTabs · 2026-06-10 시토)
  // 읽기와 동일 맵 사용 → 부서별 저장 위치 = 읽기 위치 정합(거짓완료·데이터 유실 0).
  var sheetMap = _deptTabs(dept);
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
      inspector, shift,
      _measureStr(c.measure),  // S2: 13열 측정값 패스스루(없으면 빈칸)
      c.reflected ? 'Y' : ''   // F1: 14열 반영완료
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
  _sortByDateDesc(sheet);
  return jsonRes({ success: true, updated: updated, added: added });
}

// ─── 시트를 날짜 내림차순 정렬(최신 날짜가 상위로 누적) — 2026-06-04 GM 지시 ───
// 헤더(1행) 유지, 2행부터 [날짜 내림차순, 항목ID 오름차순]으로 정렬. 셀 서식도 함께 이동.
function _sortByDateDesc(sheet) {
  if (!sheet) return;
  var last = sheet.getLastRow();
  if (last < 3) return;  // 헤더 + 1행 이하면 정렬 불필요
  sheet.getRange(2, 1, last - 1, HEADERS.length)
       .sort([{ column: 1, ascending: false }, { column: 2, ascending: true }]);
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
  var dept = body.dept || 'support';

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

  // dept별 전용 탭으로 라우팅 (S5 단일 출처 _deptTabs · 2026-06-10 시토)
  var _dt = _deptTabs(dept);
  var tMale   = _dt.male;
  var tFemale = _dt.female;
  var tCommon = _dt.common;

  var buckets = {};
  buckets[tMale] = [];
  buckets[tFemale] = [];
  buckets[tCommon] = [];
  checks.forEach(function(c) {
    // _routeItem은 지원부 탭명 기준이므로 결과를 시설부 탭명으로 리매핑
    var supportTarget = _routeItem(c.itemId, c.cat, gender);
    var target = supportTarget === SHEET_MALE   ? tMale
               : supportTarget === SHEET_FEMALE ? tFemale
               : tCommon;
    buckets[target].push(c);
  });

  var totalSaved = 0;
  [tMale, tFemale, tCommon].forEach(function(name) {
    var items = buckets[name];
    if (items.length === 0) return;
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;

    var data = sheet.getDataRange().getValues();
    // 비파괴 저장(2026-06-05 COO): 날짜 행 전체 삭제 금지 — itemId 단위 update/add 로 전환.
    // 다른 push(탭 전환 등)가 먼저 저장한 같은 날짜 항목(특히 공용 이슈) 유실 차단.
    var existingMap = {};
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]) === date || formatDate(data[i][0]) === date) {
        existingMap[String(data[i][1])] = i + 1;
      }
    }

    var newRows = [];
    items.forEach(function(c) {
      var rowNum = existingMap[c.itemId];
      var values = [
        date, c.itemId, c.name, c.cat, c.slot,
        c.checked ? '완료' : '미완료',
        c.issue || '', c.tip || '',
        submitStatus, submitAt,
        submitter || defaultInspector(name, c.slot || ''),
        c.shift || slotToShift(c.slot || ''),
        _measureStr(c.measure),  // S2: 13열 측정값 패스스루(없으면 빈칸)
        c.reflected ? 'Y' : ''   // F1: 14열 반영완료
      ];
      if (rowNum) {
        sheet.getRange(rowNum, 1, 1, HEADERS.length).setValues([values]);
        _applyRowStyle(sheet, rowNum, values);
        totalSaved++;
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
      totalSaved += newRows.length;
    }
    _sortByDateDesc(sheet);   // 최신 날짜가 상위로 누적
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
  var dept = body.dept || 'support';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  // dept별 전용 탭에 시드 (S5 단일 출처 _deptTabs · 2026-06-10 시토)
  var _st = _deptTabs(dept);
  var zones = [
    { name: _st.male,   items: ZONE_ITEMS },
    { name: _st.female, items: ZONE_ITEMS },
    { name: _st.common, items: COMMON_ITEMS },
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
  var widths = [180, 180, 240, 360, 80, 180, 70, 90, 200, 90];  // 타입·필드정의·부서 추가
  for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i + 1, widths[i]);
  return sheet;
}

// ─── 항목 조회 (GET ?action=items[&dept=...]) ───
// S4 갭②(2026-06-10 시토): dept 필터 — 요청 dept(기본 'support')와 일치하는 항목만 반환.
// 항목 '부서' 빈값 = 레거시(원본 지원부) → 'support' 폴백. 시설/운영/주차 화면 교차노출 차단.
function getItems(params) {
  var reqDept = (params && params.dept) ? String(params.dept).trim() : 'support';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ items: [] });
  var data = sheet.getDataRange().getValues();
  var items = [];
  for (var i = 1; i < data.length; i++) {
    if (!data[i][0] && !data[i][2]) continue; // id·항목명 모두 없으면 건너뜀
    if (_itemDept(data[i][ITEM_DEPT_COL]) !== reqDept) continue; // dept 불일치 제외
    // S1(2026-06-10 시토): type 빈값 → 'check' 폴백. fields = measure 입력 영문키 목록(없으면 빈문자).
    var itemType = String(data[i][7] || '').trim() || 'check';
    items.push({
      id:     String(data[i][0] || ''),
      cat:    String(data[i][1] || ''),
      name:   String(data[i][2] || ''),
      detail: String(data[i][3] || ''),
      gender: String(data[i][4] || 'all'),
      slot:   String(data[i][5] || ''),
      order:  data[i][6] !== '' && data[i][6] != null ? Number(data[i][6]) : (i),
      type:   itemType,
      fields: String(data[i][8] || ''),
      dept:   _itemDept(data[i][ITEM_DEPT_COL])
    });
  }
  return jsonRes({ items: items });
}

// ─── 항목 저장 (POST {action:'saveItems', dept, items:[...]}) — 본 dept만 재기록 ───
// S4 갭②(2026-06-10 시토): 점검항목 마스터는 전 dept 공유 시트. 과거 '전체 재기록'은
// 한 dept가 저장하면 타 dept 항목을 전부 소실시킴(잠재 데이터유실). → 본 dept 행만 교체,
// 타 dept 행은 보존(읽어서 다시 기록). dept 빈값 → 'support'(레거시) 폴백.
function saveItems(body) {
  var reqDept = body.dept ? String(body.dept).trim() : 'support';
  var items = body.items || [];
  var sheet = initItemSheet();

  // 1) 기존 시트에서 타 dept 행 보존 수집
  var lastRow = sheet.getLastRow();
  var preserved = [];
  if (lastRow > 1) {
    var existing = sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).getValues();
    for (var e = 0; e < existing.length; e++) {
      var r = existing[e];
      if (!r[0] && !r[2]) continue; // 빈 행 스킵
      if (_itemDept(r[ITEM_DEPT_COL]) !== reqDept) preserved.push(r); // 타 dept만 보존
    }
  }

  // 2) 본 dept 신규 행 구성(부서 컬럼에 reqDept 박제)
  var mine = items.map(function (it, idx) {
    return [
      String(it.id || ''),
      String(it.cat || ''),
      String(it.name || ''),
      String(it.detail || ''),
      String(it.gender || 'all'),
      String(it.slot || ''),
      it.order !== undefined && it.order !== '' ? it.order : (idx + 1),
      // S1(2026-06-10 시토): 타입·필드정의 패스스루(빈값→'check' 폴백). 영문키만(한글 키 금지).
      String(it.type || '').trim() || 'check',
      String(it.fields || ''),
      reqDept   // S4 갭②: 부서
    ];
  });

  // 3) 헤더 아래 전체 비우고 [보존 타 dept + 본 dept] 재기록
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).clearContent();
  }
  var rows = preserved.concat(mine);
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, ITEM_HEADERS.length).setValues(rows);
  }
  return jsonRes({ ok: true, count: mine.length, total: rows.length, dept: reqDept });
}

// ════════════════════════════════════════════
// 요일별 트렐로 보드 (매뉴얼 탭) — 모든 기기 동기화
// 저장소: ScriptProperties (단일 JSON blob, 9KB 한도 내 — 14셀 짧은 텍스트)
// 한글은 영문키(action/key/board) + UTF-8 POST 본문으로만 처리(GET 쿼리 한글 금지)
// ════════════════════════════════════════════

const BOARD_PROP_PREFIX = 'BOARD_';   // ScriptProperties 키 접두사
const BOARD_DEFAULT_KEY  = 'SUPPORT_MANUAL_BOARD';

// ─── 보드 조회 (GET ?action=board[&key=SUPPORT_MANUAL_BOARD]) ───
function getBoard(params) {
  var key = (params && params.key) ? String(params.key) : BOARD_DEFAULT_KEY;
  var raw = PropertiesService.getScriptProperties().getProperty(BOARD_PROP_PREFIX + key);
  var board = null;
  if (raw) {
    try { board = JSON.parse(raw); } catch (err) { board = null; }
  }
  // board=null → 프론트가 시드/로컬 폴백 사용
  return jsonRes({ ok: true, key: key, board: board });
}

// ─── 보드 저장 (POST {action:'saveBoard', key, board}) — last-write-wins 전체 덮어쓰기 ───
function saveBoard(body) {
  var key = body.key ? String(body.key) : BOARD_DEFAULT_KEY;
  var board = body.board || {};
  PropertiesService.getScriptProperties()
    .setProperty(BOARD_PROP_PREFIX + key, JSON.stringify(board));
  return jsonRes({ ok: true, key: key, savedAt: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') });
}

// ─── 점검항목 마스터 dept 1회 마이그레이션 (S4 갭② · 2026-06-10 시토) ───
// 기존 시트는 '부서' 열 빈값 → getItems가 전부 'support'로 폴백(시설 항목이 지원부에 노출).
// id 접두사로 dept 추정해 박제: 'fac'/'facility' → facility, 그 외 → support.
// 에디터 1회 실행 또는 GET ?action=migrate_item_dept 로 호출(신규 배포 불필요).
function migrateItemDept() {
  var sheet = initItemSheet();   // 헤더 10열 보장
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return { ok: true, updated: 0, note: 'no data' };
  var rng = sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length);
  var data = rng.getValues();
  var updated = 0;
  for (var i = 0; i < data.length; i++) {
    if (!data[i][0] && !data[i][2]) continue;
    var cur = String(data[i][ITEM_DEPT_COL] == null ? '' : data[i][ITEM_DEPT_COL]).trim();
    if (cur) continue;   // 이미 dept 있으면 보존(멱등)
    var id = String(data[i][0] || '').toLowerCase();
    data[i][ITEM_DEPT_COL] = (id.indexOf('fac') === 0) ? 'facility' : 'support';
    updated++;
  }
  rng.setValues(data);
  return { ok: true, updated: updated };
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
  // S1(2026-06-10 시토): 기존 시드 항목은 모두 check형(타입='check', 필드정의 빈값).
  // 남/여 공통 구역 항목 (S4 갭②: 부서='support' — 기존 지원부 마스터)
  ZONE_ITEMS.forEach(function (it) {
    rows.push([it.id, it.cat, it.name, '', 'all', it.slot, order++, 'check', '', 'support']);
  });
  // 공용 구역 항목
  COMMON_ITEMS.forEach(function (it) {
    rows.push([it.id, it.cat, it.name, '', 'all', it.slot, order++, 'check', '', 'support']);
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

// ════════════════════════════════════════════
// 부서별 시트 탭 라우팅 헬퍼 (2026-06-08 시토)
// dept='facility' → 시설_* 탭 / dept='support'(기본) → 기존 탭
// ════════════════════════════════════════════

var SHEET_FACILITY_MALE   = '시설_남성구역';
var SHEET_FACILITY_FEMALE = '시설_여성구역';
var SHEET_FACILITY_COMMON = '시설_공용구역';

// S5 거짓완료 차단(2026-06-10 시토): dept → 점검 데이터 시트 탭 3종 단일 출처.
// 기존엔 facility만 분기, ops·parking은 분기 누락 → support 탭으로 폴백되어 '남의 부서 제출 도장'을
// 자기 화면에 거짓완료 노출(GM 신고). dept별 전용 탭으로 완전 분리(미존재 탭 = 빈 데이터 = 정직).
// support/facility 탭명은 종전과 100% 동일 → 두 부서 동작 불변(회귀 0). 읽기·쓰기 라우팅 공용.
var DEPT_TAB_MAP = {
  support:  { male: SHEET_MALE,            female: SHEET_FEMALE,            common: SHEET_COMMON },
  facility: { male: SHEET_FACILITY_MALE,   female: SHEET_FACILITY_FEMALE,   common: SHEET_FACILITY_COMMON },
  ops:      { male: '운영_남성구역',        female: '운영_여성구역',          common: '운영_공용구역' },
  parking:  { male: '주차_남성구역',        female: '주차_여성구역',          common: '주차_공용구역' }
};
// dept 미지정·미등록 dept → support(레거시) 안전 폴백.
function _deptTabs(dept) {
  var d = String(dept == null ? '' : dept).trim();
  return DEPT_TAB_MAP[d] || DEPT_TAB_MAP.support;
}

// ─── 시설부 데이터 탭 생성/보장 (2026-06-10 시토) ───
// 지원부 setupNewStructure 패턴 재사용: _createCheckSheet(13열 HEADERS, 측정값 포함) + 오늘 시드.
// 멱등: 이미 있으면 _createCheckSheet가 clear 후 헤더 재기록(데이터 보존 아님 → 최초 1회용).
// GET ?action=setup_facility_tabs 로 호출(신규 배포 불필요, @HEAD 또는 에디터 실행).
function setupFacilitySheets() {
  return setupDeptSheets('facility');   // 하위호환: 기존 setup_facility_tabs 엔드포인트 유지
}

// ─── dept별 데이터 탭 생성/시드 (S5 일반화 · 2026-06-10 시토) ───
// _deptTabs 단일 출처로 임의 dept(support/facility/ops/parking) 탭을 생성·시드.
// _createCheckSheet는 clear 후 헤더 재기록(데이터 보존 아님) → 최초 1회용. GET ?action=setup_dept_tabs&dept=ops
function setupDeptSheets(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var created = [];
  [t.male, t.female, t.common].forEach(function (name) {
    var existed = !!ss.getSheetByName(name);
    _createCheckSheet(ss, name);   // 13열 HEADERS(측정값 포함) 헤더 기록
    created.push((existed ? '재생성:' : '신규:') + name);
  });
  // 오늘 날짜 빈 데이터 시드(남/여=ZONE_ITEMS, 공용=COMMON_ITEMS)
  var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  _seedDate(ss.getSheetByName(t.male),   today, ZONE_ITEMS,   t.male);
  _seedDate(ss.getSheetByName(t.female), today, ZONE_ITEMS,   t.female);
  _seedDate(ss.getSheetByName(t.common), today, COMMON_ITEMS, t.common);
  return jsonRes({ ok: true, dept: dept, created: created, seededDate: today });
}

var SHEET_ISSUE_FACILITY = '시설_이슈대장';
var SHEET_ISSUE_SUPPORT  = '지원_이슈대장';

var ISSUE_HEADERS = ['등록일', '구역', '점검자', '이슈내용', '상태', '처리일', '비고'];

// dept 파라미터 → 점검 데이터 시트 탭명 배열 반환 (DEPT_TAB_MAP 단일 출처)
// 전 부서 전용 탭만 — 폴백 없음(탭 미존재 시 빈 데이터로 명확 분리, 거짓완료 0).
function _getSheetsForDept(dept) {
  var t = _deptTabs(dept);
  return [t.male, t.female, t.common];
}

// ════════════════════════════════════════════
// action=weekly — 최근 7일 완료율 집계 (2026-06-08 시토)
// GET ?action=weekly&dept=facility|support
// 응답: { ok:true, dept, data:[{date, total, done, pct}, ...] }
// ════════════════════════════════════════════

function handleWeekly(params) {
  var dept = params.dept || 'support';
  var sheetNames = _getSheetsForDept(dept);
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // 최근 7일 날짜 배열 생성 (오늘 포함, 내림차순)
  var today = new Date();
  var tz = 'Asia/Seoul';
  var days = [];
  for (var i = 0; i < 7; i++) {
    var d = new Date(today);
    d.setDate(today.getDate() - i);
    days.push(Utilities.formatDate(d, tz, 'yyyy-MM-dd'));
  }

  // 각 시트에서 날짜별 행 수집
  var byDate = {};
  days.forEach(function(dt) { byDate[dt] = { total: 0, done: 0, measure: [] }; });

  sheetNames.forEach(function(name) {
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;
    var data = sheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      var rowDate = formatDate(data[i][0]);
      if (!byDate[rowDate]) continue;
      byDate[rowDate].total++;
      if (String(data[i][5]) === '완료') byDate[rowDate].done++;   // 완료율 판정 불변
      // S2(2026-06-10 시토): 13열 측정값이 있는 행만 수집(없으면 무시). 완료율과 무관.
      var mv = String(data[i][12] || '');
      if (mv) byDate[rowDate].measure.push({ itemId: String(data[i][1]), name: String(data[i][2]), measure: mv });
    }
  });

  // 날짜 오름차순으로 결과 배열 구성 (차트 표시용)
  var result = days.slice().reverse().map(function(dt) {
    var s = byDate[dt];
    var pct = s.total > 0 ? Math.round(s.done / s.total * 100) : 0;
    return { date: dt, total: s.total, done: s.done, pct: pct, measure: s.measure };  // S2: 측정값 배열(없으면 [])
  });

  return jsonRes({ ok: true, dept: dept, data: result });
}

// ════════════════════════════════════════════
// 이슈대장 시트 탭 초기화 (에디터 1회 실행용)
// ════════════════════════════════════════════

function initIssueLogSheet(tabName) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(tabName);
  if (!sheet) { sheet = ss.insertSheet(tabName); }
  // 이미 헤더가 있으면 건드리지 않음
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(ISSUE_HEADERS);
    sheet.getRange(1, 1, 1, ISSUE_HEADERS.length)
      .setBackground('#2a2725').setFontColor('#B79F8A')
      .setFontWeight('bold').setHorizontalAlignment('center');
    sheet.setFrozenRows(1);
    var widths = [110, 120, 100, 280, 80, 110, 180];
    for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i + 1, widths[i]);
  }
  return sheet;
}

// 두 탭 일괄 신설 (Apps Script 에디터에서 1회 실행)
function setupIssueLogSheets() {
  initIssueLogSheet(SHEET_ISSUE_FACILITY);
  initIssueLogSheet(SHEET_ISSUE_SUPPORT);
  Logger.log('이슈대장 탭 신설 완료: ' + SHEET_ISSUE_FACILITY + ', ' + SHEET_ISSUE_SUPPORT);
}

// ════════════════════════════════════════════
// action=issuelog — 이슈대장 조회 (2026-06-08 시토)
// GET ?action=issuelog&dept=facility|support[&open=1]
// open=1: 미처리·처리중만 / 생략: 전체
// 응답: { ok:true, dept, open:bool, issues:[{id, date, zone, inspector, issue, status, resolvedAt, note}] }
// ════════════════════════════════════════════

function handleIssueLogGet(params) {
  var dept = params.dept || 'support';
  var onlyOpen = params.open === '1';
  var tabName = dept === 'facility' ? SHEET_ISSUE_FACILITY : SHEET_ISSUE_SUPPORT;

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(tabName);
  if (!sheet) {
    // 탭이 없으면 빈 배열 반환 (setupIssueLogSheets 미실행 상태 대응)
    return jsonRes({ ok: true, dept: dept, open: onlyOpen, issues: [] });
  }

  var data = sheet.getDataRange().getValues();
  var issues = [];
  for (var i = 1; i < data.length; i++) {
    if (!data[i][0] && !data[i][3]) continue; // 날짜·이슈내용 모두 없으면 건너뜀
    var status = String(data[i][4] || '미처리');
    if (onlyOpen && status === '완료') continue;
    issues.push({
      id: i,                                        // 시트 행 번호(1-based 헤더 제외)를 임시 식별자로 사용
      date:       data[i][0] ? formatDate(data[i][0]) : '',
      zone:       String(data[i][1] || ''),
      inspector:  String(data[i][2] || ''),
      issue:      String(data[i][3] || ''),
      status:     status,
      resolvedAt: data[i][5] ? formatDate(data[i][5]) : '',
      note:       String(data[i][6] || '')
    });
  }
  return jsonRes({ ok: true, dept: dept, open: onlyOpen, issues: issues });
}

// ════════════════════════════════════════════
// action=issuelog_add — 이슈 등록 (2026-06-08 시토)
// POST { action:'issuelog_add', dept, date, zone, inspector, issue, status, resolvedAt, note }
// 응답: { ok:true, dept, row }
// ════════════════════════════════════════════

function handleIssueLogAdd(body) {
  var dept = body.dept || 'support';
  var tabName = dept === 'facility' ? SHEET_ISSUE_FACILITY : SHEET_ISSUE_SUPPORT;
  var sheet = initIssueLogSheet(tabName);

  var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  var row = [
    body.date       || now,
    body.zone       || '',
    body.inspector  || '',
    body.issue      || '',
    body.status     || '미처리',
    body.resolvedAt || '',
    body.note       || ''
  ];
  sheet.appendRow(row);
  var addedRow = sheet.getLastRow();
  _applyIssueRowStyle(sheet, addedRow, row);
  return jsonRes({ ok: true, dept: dept, row: addedRow });
}

// ════════════════════════════════════════════
// action=issuelog_update — 이슈 상태 갱신 (2026-06-08 시토)
// POST { action:'issuelog_update', dept, row, status, resolvedAt, note }
// row: 시트 데이터 행 번호 (헤더 제외 1-based, handleIssueLogGet의 id 필드)
// 응답: { ok:true, dept, row }
// ════════════════════════════════════════════

function handleIssueLogUpdate(body) {
  var dept = body.dept || 'support';
  var tabName = dept === 'facility' ? SHEET_ISSUE_FACILITY : SHEET_ISSUE_SUPPORT;
  var rowNum = parseInt(body.row, 10);
  if (!rowNum || rowNum < 1) return jsonRes({ ok: false, error: 'row required' });

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(tabName);
  if (!sheet) return jsonRes({ ok: false, error: 'sheet not found: ' + tabName });

  var sheetRow = rowNum + 1; // 헤더 1행 오프셋
  if (sheetRow > sheet.getLastRow()) return jsonRes({ ok: false, error: 'row out of range' });

  var existing = sheet.getRange(sheetRow, 1, 1, ISSUE_HEADERS.length).getValues()[0];
  if (body.status     !== undefined) existing[4] = body.status;
  if (body.resolvedAt !== undefined) existing[5] = body.resolvedAt;
  if (body.note       !== undefined) existing[6] = body.note;

  sheet.getRange(sheetRow, 1, 1, ISSUE_HEADERS.length).setValues([existing]);
  _applyIssueRowStyle(sheet, sheetRow, existing);
  return jsonRes({ ok: true, dept: dept, row: rowNum });
}

// ─── 이슈대장 행 스타일 ───
function _applyIssueRowStyle(sheet, row, values) {
  var statusCell = sheet.getRange(row, 5);
  var status = String(values[4] || '미처리');
  if (status === '완료') {
    statusCell.setBackground('#e6f3ea').setFontColor('#2c8a4f');
  } else if (status === '처리중') {
    statusCell.setBackground('#fef3e2').setFontColor('#c0851b');
  } else {
    statusCell.setBackground('#fce8e4').setFontColor('#c0392b');
  }
}

// ════════════════════════════════════════════
// F3(2026-06-11 시우): 제출 스냅샷 적립 — 점검일지 시트에 조 제출 시 1행 append
// POST { action:'snapshot_append', dept, date, zone(gender:m/f/all), shift, submitter,
//        submittedAt, total, done, pct, issuesCount, issues(텍스트) }
// 기존 일별 덮어쓰기 모델(남/여/공용 시트)은 그대로 — 본 시트는 append-only 누적 기록 전용.
// 집계(getShiftStatsG·handleWeekly)·텔레그램과 완전 독립(별도 시트). dept별 탭 분리.
// ════════════════════════════════════════════

var SNAPSHOT_HEADERS = ['제출시각','날짜','부서','구역','교대','점검자','총항목','완료','완료율(%)','이슈건수','이슈내용','점검시작','점검완료','소요(분)'];

function _snapshotTabName(dept) {
  var d = String(dept == null ? '' : dept).trim() || 'support';
  return '점검일지_' + d;
}

function _initSnapshotSheet(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var name = _snapshotTabName(dept);
  var sheet = ss.getSheetByName(name);
  if (!sheet) { sheet = ss.insertSheet(name); }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(SNAPSHOT_HEADERS);
    sheet.getRange(1, 1, 1, SNAPSHOT_HEADERS.length)
      .setBackground('#2a2725').setFontColor('#B79F8A')
      .setFontWeight('bold').setHorizontalAlignment('center');
    sheet.setFrozenRows(1);
    var widths = [160, 100, 80, 70, 70, 110, 70, 60, 80, 80, 360, 140, 140, 80];
    for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i + 1, widths[i]);
  } else if (sheet.getLastColumn() < SNAPSHOT_HEADERS.length) {
    // 기존 11열 시트 보강 — 12~14열(점검시작·점검완료·소요(분)) 헤더 라벨 추가
    var start = sheet.getLastColumn() + 1;
    var labels = SNAPSHOT_HEADERS.slice(start - 1);
    sheet.getRange(1, start, 1, labels.length).setValues([labels])
      .setBackground('#2a2725').setFontColor('#B79F8A')
      .setFontWeight('bold').setHorizontalAlignment('center');
    var extra = [140, 140, 80];
    for (var j = 0; j < labels.length; j++) sheet.setColumnWidth(start + j, extra[j] || 100);
  }
  return sheet;
}

function handleSnapshotAppend(body) {
  var dept = body.dept || 'support';
  var sheet = _initSnapshotSheet(dept);
  var at = body.submittedAt || Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
  var row = [
    at,
    body.date || '',
    dept,
    body.zone || '',
    body.shift || '',
    body.submitter || '',
    (body.total != null ? body.total : ''),
    (body.done != null ? body.done : ''),
    (body.pct != null ? body.pct : ''),
    (body.issuesCount != null ? body.issuesCount : ''),
    body.issues || '',
    body.startedAt || '',
    body.finishedAt || '',
    (body.durationMin != null ? body.durationMin : '')
  ];
  sheet.appendRow(row);
  return jsonRes({ ok: true, dept: dept, row: sheet.getLastRow() });
}
