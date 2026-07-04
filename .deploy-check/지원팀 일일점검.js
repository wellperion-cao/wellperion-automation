// 웰페리온 지원팀 일일 점검 - Apps Script v3.0
// 3시트 구조: 남성구역 / 여성구역 / 공용구역 + 점검자
// v2 → v3 변경: 성별구역 열 삭제, 제자리 갱신(중복 방지), 점검자 자동 배정, 근무시간 기입

// 2026-06-12 GM: 지원부 시트 지원_ 접두사 통일 + 공용구역 폐기(점검(남)→남성/점검(여)→여성).
const SHEET_MALE   = '지원_남성구역';
const SHEET_FEMALE = '지원_여성구역';
const SHEET_COMMON = '__support_common__';   // 폐기 sentinel(실제 시트 아님): 공용 라우팅분은 활성 성별탭으로 보냄(_handleSaveV2Compat remap).
const SHEET_STAFF  = '점검자';
const SHEET_ITEMS  = '지원_매뉴얼';   // GM 편집 점검 항목 마스터(=매뉴얼 단일출처, 시트 영구 저장)

// S1(2026-06-10 시토): 측정형 항목 식별 — '타입'(check|measure) + '필드정의'(measure 영문키 목록) 2열 추가.
// 기존 항목은 '타입' 빈값 → 'check' 안전 폴백. 이 단계는 동작 변화 없음(프론트가 아직 안 읽음).
// S4 갭②(2026-06-10 시토): '부서'(dept) 10열 추가 — 점검항목 마스터가 전 dept 공유 시트라
// getItems/saveItems가 dept 무필터면 시설 measure 항목이 지원·운영·주차 화면에 빈칸 노출.
// 빈값 → 'support'(레거시 기존 항목=원본 지원부) 안전 폴백.
// 2b-1(2026-06-11 시우): '회차'(rounds) 11열 추가 — 이슈→항목 승격 시 선택한 5조(am1,pm1…)를
// 보존. dept(인덱스9) 뒤에 붙여 기존 인덱스 불변. 빈값 → 프론트 itemRounds가 roundOfSlot 폴백(하위호환).
// 2026-06-27: '시드'(seed) 12번째 열은 과거 잔재 — seed 개념 폐기. 시트=항목 마스터 단일출처.
// getItems/_buildTodayMaster는 더는 seed 행을 skip하지 않음(시트 행 전체가 마스터). syncSeedItems=no-op(되쓰기 차단).
// 2026-06-27: GM 확정 12칸 스키마 — '시간대' 열 폐지(회차=타이밍 축). 시트=항목 마스터 단일출처.
// 헤더: 항목ID|카테고리|항목명|상세|성별|정렬|타입|필드정의|부서|회차|점검일정|시드
const ITEM_HEADERS = ['항목ID','카테고리','항목명','상세','성별','정렬','타입','필드정의','부서','회차','점검일정'];   // 2026-06-29 시우: '시드'칸 폐지(11칸). 성별·타입·부서·회차·점검일정 = 시트엔 한글 저장.
const ITEM_DEPT_COL = 8;    // '부서' 0-based 인덱스(9번째 열)
const ITEM_ROUNDS_COL = 9;  // '회차' 0-based 인덱스(10번째 열) — 오전조/오후조/마감조 라벨 또는 am1,pm1,close1. 빈값 폴백
const ITEM_SCHED_COL = 10;  // '점검일정' 0-based 인덱스(11번째 열) — 요일·몇째주 구조저장 "tue,fri|2" 형식. 빈값 가능
const ITEM_SEED_COL = 11;   // '시드' 12번째 열 — 2026-06-29 개념 완전 폐기. 항상 빈칸·어떤 로직도 읽지 않음(데드 컬럼).
function _isSeedRow(row){ return false; }   // 2026-06-29 시우: seed 개념 폐기 — 항상 false(되살아나지 않게 박제). 과거 'Y' 보존이 saveItems 시 시드행 중복증식의 뿌리였음.
// ─── 부서/성별/타입/회차 한글 ↔ 영어 (2026-06-29 시우) — 시트엔 한글 저장, 페이지엔 영어 전달(거르기·탭 무변경) ───
function _itemDept(v){ var d = String(v == null ? '' : v).trim(); if(!d) return 'support'; var m={'지원부':'support','시설부':'facility'}; return m[d] || d; }   // 한글 부서 → 표준코드(거르기용). 영어/기타는 그대로.
function _deptToKorean(d){ d = String(d||'').trim(); var m={'support':'지원부','facility':'시설부'}; return m[d] || (d || '지원부'); }
function _genderToEnglish(v){ v = String(v||'').trim(); var m={'공통':'all','남':'m','여':'f','남녀공통':'all','전체':'all','all':'all','m':'m','f':'f'}; return m[v] || 'all'; }
function _genderToKorean(v){ v = String(v||'').trim(); var m={'all':'공통','m':'남','f':'여','공통':'공통','남':'남','여':'여'}; return m[v] || '공통'; }
function _typeToEnglish(v){ v = String(v||'').trim(); var m={'점검':'check','측정':'measure'}; if(m[v]) return m[v]; return v || 'check'; }   // 빈값·영어는 그대로(빈→check)
function _typeToKorean(v){ v = String(v||'').trim(); var m={'check':'점검','measure':'측정'}; return m[v] || (v ? v : '점검'); }
function _roundsToEnglish(v){ v = String(v||'').trim(); if(!v) return ''; var m={'오전조':'am1','오후조':'pm1','마감조':'close1','야간조':'night1'}; return v.split(/[,·]/).map(function(x){ x=x.trim(); return m[x]||x; }).filter(Boolean).join(','); }
function _roundsToKorean(v){ v = String(v||'').trim(); if(!v) return ''; var m={'am1':'오전조','pm1':'오후조','close1':'마감조','night1':'야간조'}; return v.split(/[,·]/).map(function(x){ x=x.trim(); return m[x]||x; }).filter(Boolean).join(', '); }

const BOT_TOKEN = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
const CHAT_ID   = '-5136037543';  // 점검 관리 방 (시우 102, 2026-06-24) — ScriptProperty UI 50개+ 잠김으로 코드 고정. BOT_TOKEN은 property 유지.

// 2026-06-15 GM 스키마 v2: 시간대→회차(조 단위) · 담당자를 점검자 앞으로 · 교대 열 삭제(14열).
const HEADERS = [
  '날짜','항목ID','항목명','카테고리','회차',
  '점검결과','이슈','노하우','제출상태','제출시각',
  '근무자','점검자','측정값','반영완료','소요시간'
]; // (닫힘 — 아래 _roundLabel). 15열 소요시간(분)=(제출시각 − 회차 시작시각). 못 구하면 빈칸. _ensureHeaders가 헤더라벨 자동정합.
// 슬롯/교대 → 조(회차) 라벨. 프론트 roundOfSlot과 동일 매핑(오전조/오후조/마감조). GM 2026-06-15.
function _roundLabel(slot, shift) {
  var s = String(slot || '');
  if (s.indexOf('마감') >= 0 || s.indexOf('저녁') >= 0) return '마감조';
  if (s.indexOf('오후') >= 0) return '오후조';
  if (String(shift || '') === 'pm') return '오후조';
  return '오전조';   // 오픈·오전·인수인계·내부외부·all·am → 오전조
}
// ─── 회차 키(am1/pm1/close1) → 조 라벨. 시트 회차열(5열) 정본. GM 2026-06-15 시우 ───
function _roundKeyLabel(rk) {
  var r = String(rk || '');
  if (r.indexOf('close') >= 0 || r.indexOf('night') >= 0) return '마감조';
  if (r.indexOf('pm') >= 0) return '오후조';
  return '오전조';   // am1·오픈 등
}
// ─── 회차라벨(오전조/오후조/마감조) → 제출도장 shiftKey(am/pm/night). led.sub/subAt 조회용. 2026-06-20 시우 ───
function _labelToShiftKey(label) {
  var l = String(label || '');
  // ★2026-06-26 시우: '마감' 라벨은 'close'(led.sub.close)로 분리. '탕청소'·'야간'은 'night' 유지.
  //   순서 주의 — 마감 체크를 야간 체크보다 먼저(탕청소엔 '마감' 글자 없으니 안전).
  if (l.indexOf('마감') >= 0) return 'close';
  if (l.indexOf('야간') >= 0 || l.indexOf('탕청소') >= 0 || l.indexOf('저녁') >= 0) return 'night';
  if (l.indexOf('오후') >= 0) return 'pm';
  if (l.indexOf('오전') >= 0) return 'am';
  return '';
}
// ─── 조 라벨 → 회차 키. 이슈-단독(미체크) 항목의 1차 회차 추정용 ───
function _roundLabelToKey(label) {
  var l = String(label || '');
  if (l.indexOf('마감') >= 0) return 'close1';
  if (l.indexOf('오후') >= 0) return 'pm1';
  return 'am1';
}
// ─── 항목 → 저장 대상 시트명 해석(부서·성별·라우팅 단일 출처). 2026-06-15 시우 ───
function _resolveTarget(dept, itemId, cat, gender) {
  var dt = _deptTabs(dept);
  var st = _routeItem(itemId, cat, gender);   // SHEET_MALE/FEMALE/COMMON 센티넬
  if (st === SHEET_MALE) return dt.male;
  if (st === SHEET_FEMALE) return dt.female;
  if (dept === 'support') return (gender === 'f' ? dt.female : dt.male);   // 지원부 공용 폐기 → 활성 성별탭
  return dt.common;
}

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

// ─── 진단 핸들러: 설정 유무만 반환(비밀값 노출 없음). action=diag 전용. 2026-06-30 시토 ───
function handleCheckDiag() {
  var hasToken = !!(BOT_TOKEN && String(BOT_TOKEN).trim());
  var hasChatId = !!(CHAT_ID && String(CHAT_ID).trim());
  return jsonRes({ ok: true, system: 'check', hasToken: hasToken, hasChatId: hasChatId });
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
  // G열(이슈·인덱스6) — 2026-06-25 시우·GM: 이슈를 G열에 직접 저장하므로 숨김 가드 제거. G열 표시 유지.
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
      '',  // 13열 측정값 — 시드 시 빈칸
      '',  // 14열 반영완료 — 시드 시 빈칸
      ''   // 15열 점검시각 — 시드 시 빈칸(HEADERS 15열 정합)
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
   if (action === 'sort_snapshot') { return sortSnapshotDesc(e.parameter.dept || 'support'); }
   if (action === 'sort_manual_order') { return sortManualByPageOrder(); }
  if (action === 'items')     return getItems(e.parameter);
  if (action === 'board')     return getBoard(e.parameter);
  if (action === 'weekly')    return handleWeekly(e.parameter);
  if (action === 'today_live') return handleTodayLive(e.parameter);   // 오늘 실시간 현황(cr 원장 기반·읽기전용) — home·대시보드 단일값. 2026-06-16 시우.
  if (action === 'monthly_report') return handleMonthlyReport(e.parameter);   // 지원부 점검 월간 리포트 집계(snapshot+이슈대장). 완료율=denomNote 월별 분기(7월+ 확정/6월 이전 참고). 배208 후속. 2026-07-03 시우.
  if (action === 'issuelog')  return handleIssueLogGet(e.parameter);
  if (action === 'setup_issue_tabs') { setupIssueLogSheets(); return jsonRes({ok:true,msg:'이슈대장 탭 생성 완료'}); }
  if (action === 'setup_facility_tabs') { return setupFacilitySheets(); }
  if (action === 'facility_items') { return jsonRes({ ok: true, items: FACILITY_ITEMS }); }   // 시설 측정 항목 마스터(완료율 분모) — 프론트 fcheck 렌더용. 2026-06-17 시우.
  if (action === 'setup_dept_tabs') { return setupDeptSheets(e.parameter.dept || 'support'); }
  if (action === 'migrate_item_dept') { return jsonRes(migrateItemDept()); }
  if (action === 'purge_custom') { return purgeCustomItems(e.parameter.dept || 'support'); }
  if (action === 'ensure_headers') { return ensureAllHeaders(e.parameter.dept || 'support'); }
  if (action === 'vendor_list') { return vendorList(); }
  if (action === 'clear_check_ledger') { return clearCheckLedger(e.parameter.dept || 'support'); }
  if (action === 'clear_zone_checks') { return clearZoneCheckedRows(e.parameter.dept || 'support', e.parameter.date || '', e.parameter.all === '1'); }
  if (action === 'delete_item_row') { return deleteItemRow(e.parameter.dept || 'support', e.parameter.date || '', e.parameter.zone || '', e.parameter.itemId || ''); }
  if (action === 'purge_orphan_checks') { return purgeOrphanChecks(e.parameter.dept || 'support'); }   // 매뉴얼에 없는 고아/테스트 항목ID를 원장·시트에서 일괄 제거. 2026-06-16 시우.
  if (action === 'dedup_items') { return dedupItems(e.parameter.dept || 'support'); }   // 지원_매뉴얼 중복 항목ID 1줄로 정리(시드행 중복 청소)+시드칸 전체 비움. 백업탭 적립. 2026-06-29 시우.
  if (action === 'set_round_duty') { return setRoundDuty(e.parameter.dept || 'support', e.parameter.zone || 'male', e.parameter.date || '', e.parameter.round || '', e.parameter.name || ''); }   // 지정 date+round 구역행 근무자(11열) 단일 통일 — stale 기본값 오염 보정. 점검결과·점검자·이슈 무변경. 2026-06-29 시우.
  if (action === 'normalize_subat_format') { return normalizeSubatFormat(e.parameter.dept || 'support'); }   // 제출시각(10열) 표시형식을 'yyyy-MM-dd HH:mm'로 통일 — 일부 셀 날짜만 표시(시간가림) 정정. 값 무변경(표시만). 2026-06-29 시우.
  if (action === 'set_ledger_duty') { return setLedgerDuty(e.parameter.dept || 'support', e.parameter.date || '', e.parameter.gender || 'm', e.parameter.round || '', e.parameter.name || ''); }   // 페이지 원장(ScriptProperties led.cr[].du) 근무자 통일 — stale 오염 보정. 시트 set_round_duty의 페이지측 짝. 2026-06-29 시우.
  if (action === 'migrate_sched_korean') { return migrateSchedKorean(e.parameter.dept || 'support'); }   // 점검일정 칸 기존 영어값을 한글 표시로 1회 전환(왕복검증 후). 2026-06-29 시우.
  if (action === 'migrate_sheet_korean') { return migrateSheetKorean(e.parameter.dept || 'support'); }   // 성별·타입·부서·회차 기존값 한글 전환(왕복검증) + 시드칸 삭제. 2026-06-29 시우.
  if (action === 'list_tabs') { return jsonRes({ tabs: SpreadsheetApp.getActiveSpreadsheet().getSheets().map(function(s){ return { name: s.getName(), gid: s.getSheetId() }; }) }); }   // gid→탭 확인용. 2026-06-15 시우.
  if (action === 'dump_snapshot') {   // 점검일지 스냅샷 전체행 덤프 — 진단용. 2026-06-16 시우.
    var _ssh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_snapshotTabName(e.parameter.dept || 'support'));
    if (!_ssh) return jsonRes({ error: 'no snapshot sheet' });
    var _sdd = _ssh.getDataRange().getValues(), _sout = [];
    for (var _sx = 1; _sx < _sdd.length; _sx++) { if(!String(_sdd[_sx][1]||'')&&!String(_sdd[_sx][0]||''))continue; _sout.push({ at: String(_sdd[_sx][0]), date: String(_sdd[_sx][1]), zone: String(_sdd[_sx][3]), shift: String(_sdd[_sx][4]), by: String(_sdd[_sx][5]), done: String(_sdd[_sx][7]), total: String(_sdd[_sx][6]) }); }
    return jsonRes({ total: _sout.length, rows: _sout });
  }
  if (action === 'dedup_snapshot') { return dedupSnapshot(e.parameter.dept || 'support'); }   // 점검일지 중복(버킷줄·재제출줄) 청소. 2026-06-16 시우.
  if (action === 'dump_zone') {   // 구역 시트 전체행(전 날짜) 덤프 — 진단용. 2026-06-15 시우.
    var _dz = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'male']);
    if (!_dz) return jsonRes({ error: 'no sheet' });
    var _dd = _dz.getDataRange().getValues(), _out = [];
    for (var _i = 1; _i < _dd.length; _i++) { _out.push({ date: String(_dd[_i][0]), id: String(_dd[_i][1]), round: String(_dd[_i][4] || ''), status: String(_dd[_i][5]), submit: String(_dd[_i][8] || ''), subAt: String(_dd[_i][9] || ''), duty: String(_dd[_i][10] || ''), inspector: String(_dd[_i][11] || ''), measure: String(_dd[_i][12] || ''), reflect: String(_dd[_i][13] || ''), chkAt: String(_dd[_i][14] || ''), issue: String(_dd[_i][6] || '') }); }
    return jsonRes({ sheet: _dz.getName(), total: _out.length, rows: _out });
  }
  if (action === 'dedup_zone') {   // (날짜,항목ID,회차) 완전동일 중복행 제거 — 첫 행만 남김. 내용 다른 행은 보존(병합 안 함). 진단·청소. 2026-06-19 시우.
    var _qz = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'male']);
    if (!_qz) return jsonRes({ error: 'no sheet' });
    var _onlyDate = e.parameter.date || '';   // 지정 시 그 날짜만(미지정=전 날짜)
    var _qd = _qz.getDataRange().getValues();
    var _seen = {}, _delRows = [], _kept = 0;
    for (var _qi = 1; _qi < _qd.length; _qi++) {
      var _row = _qd[_qi];
      var _dt = formatDate(_row[0]);
      if (_onlyDate && _dt !== _onlyDate) continue;
      var _key = _dt + '|' + String(_row[1]) + '|' + String(_row[4]);   // 날짜|항목ID|회차
      // 실질내용 시그니처(시각 제외): 결과5·이슈6·노하우7·제출8·근무10·점검자11·측정12·반영13
      var _sig = [5,6,7,8,10,11,12,13].map(function(c){ return String(_row[c] == null ? '' : _row[c]); }).join('');
      if (_seen[_key] === undefined) { _seen[_key] = _sig; _kept++; }
      else if (_seen[_key] === _sig) { _delRows.push(_qi + 1); }   // 완전동일만 삭제대상. 내용다르면 보존
    }
    _delRows.sort(function(a, b){ return b - a; });   // 내림차순 삭제(인덱스 안전)
    _delRows.forEach(function(rn){ _qz.deleteRow(rn); });
    return jsonRes({ ok: true, sheet: _qz.getName(), date: _onlyDate || 'all', kept: _kept, removed: _delRows.length });
  }
  if (action === 'collapse_submitted') {   // (날짜,항목ID,회차) 제출완료 행 보존, 내용 동일한 작업행(미제출) 중복만 제거. 시각/제출상태 제외 비교. 2026-06-19 시우.
    var _cz = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'male']);
    if (!_cz) return jsonRes({ error: 'no sheet' });
    var _cOnly = e.parameter.date || '';
    var _cd = _cz.getDataRange().getValues();
    var _SUB = '제출완료';   // '제출완료'
    var _gmap = {};
    for (var _ci = 1; _ci < _cd.length; _ci++) {
      var _cr = _cd[_ci];
      var _cdt = formatDate(_cr[0]);
      if (_cOnly && _cdt !== _cOnly) continue;
      var _ck = _cdt + '|' + String(_cr[1]) + '|' + String(_cr[4]);
      var _ccsig = [5,6,7,10,11,12,13].map(function(c){ return String(_cr[c] == null ? '' : _cr[c]); }).join('');
      var _csub = (String(_cr[8] || '').indexOf(_SUB) >= 0);
      if (!_gmap[_ck]) _gmap[_ck] = [];
      _gmap[_ck].push({ rn: _ci + 1, csig: _ccsig, sub: _csub });
    }
    var _cDel = [], _cKept = 0, _cKeys = 0;
    Object.keys(_gmap).forEach(function(k){
      var arr = _gmap[k]; _cKeys++;
      if (arr.length < 2) { _cKept += arr.length; return; }
      var keeper = null;
      for (var i = 0; i < arr.length; i++) { if (arr[i].sub) { keeper = arr[i]; break; } }
      if (!keeper) keeper = arr[0];
      arr.forEach(function(r){
        if (r === keeper) { _cKept++; }
        else if (r.csig === keeper.csig) { _cDel.push(r.rn); }   // 내용 동일 → 중복, 삭제
        else { _cKept++; }                                       // 내용 다름 → 보존
      });
    });
    _cDel.sort(function(a, b){ return b - a; });
    _cDel.forEach(function(rn){ _cz.deleteRow(rn); });
    return jsonRes({ ok: true, sheet: _cz.getName(), date: _cOnly || 'all', keys: _cKeys, kept: _cKept, removed: _cDel.length });
  }
  if (action === 'clear_non_keep') {   // 지정 날짜(keep) 외 행 전부 삭제 — '오늘것만 남김'. 2026-06-15 시우.
    var _kz = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'male']);
    var _keep = e.parameter.date || '';
    if (!_kz || !_keep) return jsonRes({ error: 'sheet/date 필수' });
    var _kd = _kz.getDataRange().getValues(), _del = [];
    for (var _j = _kd.length - 1; _j >= 1; _j--) { var _dv = String(_kd[_j][0]); if (!(_dv === _keep || formatDate(_kd[_j][0]) === _keep)) _del.push(_j + 1); }
    var _rm = 0, _mode = 'delete';
    if (_del.length > 0 && _del.length >= (_kd.length - 1)) {
      // 전 데이터행 삭제 = 시트 빔(구글시트 '마지막행 삭제' 금지) → 내용만 비움. 마지막 빈행은 getDataRange서 제외돼 read 무영향. GM 2026-06-15.
      _mode = 'clear';
      _del.forEach(function(rn){ _kz.getRange(rn, 1, 1, Math.max(1, _kz.getLastColumn())).clearContent(); _rm++; });
    } else {
      _del.forEach(function(rn){ _kz.deleteRow(rn); _rm++; });   // 내림차순이라 안전
    }
    return jsonRes({ ok: true, sheet: _kz.getName(), kept: _keep, removed: _rm, mode: _mode });
  }
  if (action === 'migrate_schema') {   // GM 스키마 v2: 기존행(담당자 이동된 15열)을 새 14열(회차·교대삭제)로 재작성. 2026-06-15 시우.
    var _mz = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'male']);
    if (!_mz) return jsonRes({ error: 'no sheet' });
    var _md = _mz.getDataRange().getValues();
    var _new = [HEADERS.slice()];
    for (var _mi = 1; _mi < _md.length; _mi++) {
      var r = _md[_mi];
      if (!String(r[0] || '')) continue;
      // 입력=현재순서(담당자 이동됨): 0날짜 1ID 2명 3카테 4시간대 5결과 6이슈 7노하우 8제출상태 9제출시각 10담당자 11점검자 12교대 13측정 14반영
      _new.push([ r[0], r[1], r[2], r[3], _roundLabel(r[4], r[12]), r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[13], r[14] ]);
    }
    _mz.clearContents();
    _mz.getRange(1, 1, _new.length, HEADERS.length).setValues(_new);
    return jsonRes({ ok: true, sheet: _mz.getName(), rows: _new.length - 1 });
  }
  if (action === 'set_inspector') {   // 특정 날짜 행들의 점검자(12열)를 실제 이름으로 일괄 교체. 2026-06-15 시우.
    var _sz = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'male']);
    var _sdate = e.parameter.date || '', _sname = e.parameter.name || '';
    if (!_sz || !_sdate || !_sname) return jsonRes({ error: 'sheet/date/name 필수' });
    var _sd = _sz.getDataRange().getValues(), _sn = 0;
    for (var _si = 1; _si < _sd.length; _si++) {
      if (String(_sd[_si][0]) === _sdate || formatDate(_sd[_si][0]) === _sdate) { _sz.getRange(_si + 1, 12).setValue(_sname); _sn++; }   // 12열=점검자(v2)
    }
    return jsonRes({ ok: true, sheet: _sz.getName(), updated: _sn, name: _sname });
  }
  if (action === 'rename_items') {   // custom_→기존ID 정규화: 매뉴얼 마스터 + 구역시트 itemID 일괄 변경. 2026-06-15 시우.
    var _rmap; try { _rmap = JSON.parse(e.parameter.map || '{}'); } catch (_e) { return jsonRes({ error: 'map JSON 오류' }); }
    var _rss = SpreadsheetApp.getActiveSpreadsheet();
    var _ro = { master: 0, sheets: 0 };
    var _rim = _rss.getSheetByName(SHEET_ITEMS);
    if (_rim) { var _rid = _rim.getDataRange().getValues(); for (var i = 1; i < _rid.length; i++) { var id = String(_rid[i][0]); if (_rmap[id]) { _rim.getRange(i + 1, 1).setValue(_rmap[id]); _ro.master++; } } }
    ['male', 'female', 'common'].forEach(function (z) { var nm = _deptTabs('support')[z]; if (!nm) return; var sh = _rss.getSheetByName(nm); if (!sh) return; var sd = sh.getDataRange().getValues(); for (var j = 1; j < sd.length; j++) { var id2 = String(sd[j][1]); if (_rmap[id2]) { sh.getRange(j + 1, 2).setValue(_rmap[id2]); _ro.sheets++; } } });
    return jsonRes({ ok: true, master: _ro.master, sheets: _ro.sheets });
  }
  if (action === 'dump_cr') {   // cr 원장 백업: chk_<dept>_* ScriptProperties 전수 JSON 덤프(마이그레이션 전 롤백 안전망). 2026-06-17 시우.
    var _dd = String(e.parameter.dept || 'support').trim() || 'support';
    var _dp = PropertiesService.getScriptProperties().getProperties();
    var _dout = {}, _dn = 0;
    Object.keys(_dp).forEach(function (k) { if (k.indexOf(CHK_PROP_PREFIX + _dd + '_') === 0) { _dout[k] = _dp[k]; _dn++; } });
    return jsonRes({ ok: true, dept: _dd, count: _dn, props: _dout });
  }
  if (action === 'migrate_cr_keys') {   // 원장 체크키 id 부분 치환(고아 차단): rename_items 짝. led.cr(<round>_<id>)+led.c(<id> 평면)+led.seen(<bucket>_<id>) 동시. 2026-06-17 시우.
    // map은 id 단위(예 {"c1a":"op3"}). cr/seen 키는 첫 '_'로 split→(prefix,id), id 정확매칭 시 prefix+'_'+newId 재조립(done카운트 split과 동일 line 2206).
    // c는 평면 {id:1}이라 id 직접매칭. b4_m 류 추가 '_' id는 첫 '_' 1회 split이라 id='b4_m' 보존(map 대상 아니라 무해). 체크값·메타 보존(키만 변경).
    var _mmap; try { _mmap = JSON.parse(e.parameter.map || '{}'); } catch (_e2) { return jsonRes({ error: 'map JSON 오류' }); }
    if (!_mmap || !Object.keys(_mmap).length) return jsonRes({ error: 'map 비어있음' });
    var _mdept = String(e.parameter.dept || 'support').trim() || 'support';
    var _mprops = PropertiesService.getScriptProperties();
    var _mall = _mprops.getProperties();
    var _mProps = 0, _mCr = 0, _mC = 0, _mSeen = 0, _mLog = [];
    // 회차/버킷 접두키(<prefix>_<id>) 치환 헬퍼: 객체의 키만 바꾸고 값 보존, 신키 없을 때만 이관.
    function _migPrefixedKeys(obj) {
      var n = 0;
      Object.keys(obj).forEach(function (ck) {
        var us = String(ck).indexOf('_'); if (us < 0) return;
        var pre = ck.slice(0, us), id = ck.slice(us + 1);
        if (!_mmap[id]) return;                       // id 정확매칭만(부분문자열 아님)
        var nk = pre + '_' + _mmap[id];
        if (nk === ck) return;
        if (obj[nk] === undefined) obj[nk] = obj[ck];
        delete obj[ck]; n++;
      });
      return n;
    }
    Object.keys(_mall).forEach(function (key) {
      if (key.indexOf(CHK_PROP_PREFIX + _mdept + '_') !== 0) return;
      var led; try { led = JSON.parse(_mall[key] || '{}'); } catch (e3) { return; }
      if (!led || typeof led !== 'object') return;
      var changed = false, short = key.replace(CHK_PROP_PREFIX + _mdept + '_', '');
      if (led.cr && typeof led.cr === 'object') { var nc = _migPrefixedKeys(led.cr); if (nc) { _mCr += nc; changed = true; _mLog.push(short + ' cr:' + nc); } }
      if (led.seen && typeof led.seen === 'object') { var ns = _migPrefixedKeys(led.seen); if (ns) { _mSeen += ns; changed = true; _mLog.push(short + ' seen:' + ns); } }
      if (led.c && typeof led.c === 'object') {     // 평면 {id:1} — id 직접매칭
        var nf = 0;
        Object.keys(led.c).forEach(function (id) {
          if (!_mmap[id]) return;
          if (led.c[_mmap[id]] === undefined) led.c[_mmap[id]] = led.c[id];
          delete led.c[id]; nf++;
        });
        if (nf) { _mC += nf; changed = true; _mLog.push(short + ' c:' + nf); }
      }
      if (changed) { _mprops.setProperty(key, JSON.stringify(led)); _mProps++; }
    });
    return jsonRes({ ok: true, dept: _mdept, props: _mProps, cr: _mCr, c: _mC, seen: _mSeen, log: _mLog });
  }
  if (action === 'restore_cr') {   // cr 원장 복구: dump_cr JSON을 역주입(마이그레이션 롤백용). props={key:jsonStr} 형식. 2026-06-17 시우.
    var _rb; try { _rb = JSON.parse(e.parameter.props || '{}'); } catch (_re) { return jsonRes({ error: 'props JSON 오류' }); }
    if (!_rb || !Object.keys(_rb).length) return jsonRes({ error: 'props 비어있음' });
    var _rpr = PropertiesService.getScriptProperties();
    var _rn = 0;
    Object.keys(_rb).forEach(function (k) { if (typeof _rb[k] === 'string') { _rpr.setProperty(k, _rb[k]); _rn++; } });
    return jsonRes({ ok: true, restored: _rn });
  }
  if (action === 'update_items_cl_reorder') {   // 마감점검 cl1~cl8 id·name·order 일괄 갱신. nameMap={id:name}, orderMap={id:order}. 2026-06-17 시우.
    var _um; try { _um = JSON.parse(e.parameter.map || '{}'); } catch (_ue) { return jsonRes({ error: 'map JSON 오류' }); }
    var _uss = SpreadsheetApp.getActiveSpreadsheet();
    var _ushi = _uss.getSheetByName(SHEET_ITEMS);
    if (!_ushi) return jsonRes({ error: 'SHEET_ITEMS 없음' });
    var _ud = _ushi.getDataRange().getValues();
    var _uUpdId = 0, _uUpdName = 0, _uUpdOrder = 0;
    for (var ui = 1; ui < _ud.length; ui++) {
      var uid = String(_ud[ui][0] || '');
      if (!uid || !_um[uid]) continue;
      var upd = _um[uid];
      if (upd.newId && upd.newId !== uid) { _ushi.getRange(ui + 1, 1).setValue(upd.newId); _uUpdId++; }
      if (upd.name != null) { _ushi.getRange(ui + 1, 3).setValue(upd.name); _uUpdName++; }
      if (upd.order != null) { _ushi.getRange(ui + 1, 6).setValue(upd.order); _uUpdOrder++; }  // 12칸: 정렬=6열(구 7열)
    }
    return jsonRes({ ok: true, updId: _uUpdId, updName: _uUpdName, updOrder: _uUpdOrder });
  }
  if (action === 'migrate_support_sheets') { return migrateSupportSheets(); }
  if (action === 'purge_dept_items') { return purgeDeptItems(e.parameter.dept || ''); }
  if (action === 'delete_facility_sheets') { return deleteFacilitySheets(); }
  if (action === 'delete_facility_empty_genders') { return deleteFacilityEmptyGenderSheets(); }   // 빈 껍데기 시설_남성/여성구역 2개만 정밀 삭제(공용구역 절대 보존, 데이터행0 확인). 1회성. 2026-06-20 시우.
  if (action === 'hide_issue_col') { return hideIssueColumn(e.parameter.dept || 'support'); }   // G열(이슈·인덱스6) 데이터행 비우기 + 컬럼 숨김(물리삭제 X·인덱스 보존). 1회성. 2026-06-20 시우.
  if (action === 'show_issue_col') { return showIssueColumn(e.parameter.dept || 'support'); }   // G열 숨김 해제 — hide_issue_col 실행 후 이슈 저장 재활성화 시 1회 실행. 2026-06-25 시우.
  if (action === 'clear_old_duration') { return clearOldDuration(e.parameter.dept || 'support'); }   // O열(소요시간·인덱스14) 옛 시각값(1899-12-30 시리얼) 비우기. 컬럼 숨김 X — 소요시간은 화면 표시 유지. 1회성. 2026-06-20 시우.
  if (action === 'fix_item_type_dept') {   // 지정 항목ID의 타입(7열)→check·부서(9열)→support 정정. F/G 칸어긋남 교정. GET ?action=fix_item_type_dept&ids=f1,f2,...,g1. 2026-06-27 시우.
    var _fim = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_ITEMS);
    if (!_fim) return jsonRes({ error: 'no SHEET_ITEMS' });
    var _fids = String(e.parameter.ids || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (!_fids.length) return jsonRes({ error: 'ids 필수' });
    var _fset = {}; _fids.forEach(function (x) { _fset[x] = 1; });
    var _fid = _fim.getDataRange().getValues(), _fn = 0, _fhit = [];
    for (var _fi = 1; _fi < _fid.length; _fi++) {
      if (_fset[String(_fid[_fi][0])]) {
        _fim.getRange(_fi + 1, 7).setValue('check');     // 7열=타입(idx6)
        _fim.getRange(_fi + 1, 9).setValue('support');   // 9열=부서(idx8)
        _fn++; _fhit.push(String(_fid[_fi][0]));
      }
    }
    return jsonRes({ ok: true, fixed: _fn, ids: _fhit });
  }
  if (action === 'dump_items_raw') {   // 지원_매뉴얼 원본 12칸 전수 덤프(파싱 전) — 칸 어긋남 진단. 2026-06-27 시우.
    var _dir = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_ITEMS);
    if (!_dir) return jsonRes({ error: 'no SHEET_ITEMS' });
    var _dird = _dir.getDataRange().getValues(), _dirOut = [];
    for (var _dri = 0; _dri < _dird.length; _dri++) {
      _dirOut.push(_dird[_dri].map(function (c) { return String(c == null ? '' : c); }));
    }
    return jsonRes({ rows: _dirOut.length, cols: (_dird[0] || []).length, data: _dirOut });
  }
  if (action === 'revert_phantom_rows') {   // 조간 누수 유령 행만 '미제출'로 정밀 되돌림 — 9열 제출상태→미제출·10열 제출시각→''·15열 소요시간→''. 점검결과·근무자·점검자·이슈 전부 보존. 백업 후 1회성. 2026-06-27 시우.
    // GET ?action=revert_phantom_rows&dept=support&date=2026-06-26&zone=female&round=마감조&ids=c2,c5,c6,d1,d2
    var _rpz = _deptTabs(e.parameter.dept || 'support')[e.parameter.zone || 'female'];
    var _rpsh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_rpz);
    if (!_rpsh) return jsonRes({ error: 'no sheet: ' + _rpz });
    var _rpdate = e.parameter.date || '', _rpround = e.parameter.round || '';
    var _rpids = String(e.parameter.ids || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (!_rpdate || !_rpids.length) return jsonRes({ error: 'date·ids 필수' });
    var _rpset = {}; _rpids.forEach(function (x) { _rpset[x] = 1; });
    var _rpd = _rpsh.getDataRange().getValues(), _rpn = 0, _rphit = [];
    for (var _rpi = 1; _rpi < _rpd.length; _rpi++) {
      var _row = _rpd[_rpi];
      var _dok = String(_row[0]) === _rpdate || formatDate(_row[0]) === _rpdate;
      var _rok = !_rpround || String(_row[4]) === _rpround;   // 회차열(idx4) 라벨 매칭(예: '마감조')
      if (_dok && _rok && _rpset[String(_row[1])]) {
        _rpsh.getRange(_rpi + 1, 9).setValue('미제출');   // 9열 제출상태(idx8)
        _rpsh.getRange(_rpi + 1, 10).setValue('');         // 10열 제출시각(idx9)
        _rpsh.getRange(_rpi + 1, 15).setValue('');         // 15열 소요시간(idx14)
        _rpn++; _rphit.push(String(_row[1]) + '/' + String(_row[4]));
      }
    }
    return jsonRes({ ok: true, sheet: _rpz, date: _rpdate, round: _rpround, reverted: _rpn, hit: _rphit });
  }

  if (action === 'diag') return handleCheckDiag();   // 읽기전용 진단: 설정 유무 불리언만 반환(비밀값 노출 없음). 2026-06-30 시토.

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
        var hasNight = submitStr.indexOf('야간') >= 0 || submitStr.indexOf('탕청소') >= 0;
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
          duty: String(data[i][10] || ''),                 // 11열 담당자(점검자 앞·v2)
          submitter: String(data[i][11] || ''),            // 12열 점검자
          shift: '',                                       // 교대 열 삭제(v2) — roundOfSlot은 slot(회차명)으로 동작
          measure: String(data[i][12] || ''),              // 13열 측정값
          reflected: String(data[i][13] || '') === 'Y',    // 14열 반영완료
          gender: name === baseMale ? 'm' : name === baseFemale ? 'f' : 'all',
          submitted_am: hasAm,
          submittedAt_am: hasAm ? String(data[i][9] || '') : '',
          submitter_am: hasAm ? String(data[i][11] || '') : '',     // [근본수정 2026-06-26 시우 #7] 제출자=점검자(12열 idx11). 구버전은 근무자(11열 idx10)를 잘못 반환.
          submitted_pm: hasPm,
          submittedAt_pm: hasPm ? String(data[i][9] || '') : '',
          submitter_pm: hasPm ? String(data[i][11] || '') : '',     // [근본수정 2026-06-26 시우 #7] 제출자=점검자(idx11)
          submitted_night: hasNight,
          submittedAt_night: hasNight ? String(data[i][9] || '') : '',
          submitter_night: hasNight ? String(data[i][11] || '') : ''  // [근본수정 2026-06-26 시우 #7] 제출자=점검자(idx11)
        });
      }
    }
  });
  // checkedLedger(2026-06-11 시우): 정상완료 항목은 시트행 미기록 → 이 원장으로 STATE 체크 복원.
  // 과거일/타기기 admin 완료율 회귀 방지(시트 col5 비의존). dept별 분리.
  // 2026-06-12 시토: 남/여 동기화 근본수정 — gender 파라미터로 해당 성별 원장만 반환(미지정 시 성별맵 전체).
  // 프론트(loadState)는 &gender=<m|f>로 단일 성별을 요청 → 남↔여 체크 섞임 0.
  var gParam = String(e.parameter.gender || '').trim();
  var checkedLedger;
  if (gParam) {
    checkedLedger = _getCheckLedger(dept, date, gParam);
  } else {
    // 성별 미지정(레거시·admin 집계): 성별맵 전체 반환 — 호출부가 필요 성별을 선택.
    checkedLedger = { m: _getCheckLedger(dept, date, 'm'), f: _getCheckLedger(dept, date, 'f'), all: _getCheckLedger(dept, date, 'all') };
  }
  return jsonRes({ date: date, zone: zone || 'all', rows: rows, groupSubmits: _getGroupSubmits(date), checkedLedger: checkedLedger, inspMemos: _getInspMemos(dept, gParam) });
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

// ─── 완료 체크 원장(ledger) — 항목별 시트 최소화 대응(2026-06-11 시우, GM 옵션A) ───
// 시트 행을 '이상치만' 기록하도록 바꾸면 정상완료 항목은 행이 사라져, 다른 기기/캐시 비운 뒤
// 과거일 admin 대시보드가 STATE 복원 불가 → 완료율 회귀(거의 0%). 이를 막기 위해 날짜+dept별로
// 체크된 itemId 집합을 ScriptProperties에 경량 적립(_saveGroupSubmits와 동일 패턴, merge-only 아님).
// 키: chk_<dept>_<date>, 값: {"<itemId>":1,...}. col5 카운트가 아닌 이 원장으로 admin·복원 정합.
// payload는 항상 활성 성별탭의 전체 스케줄을 보내므로, 이번 payload에 들어온 항목만 set/remove.
// (타 성별 항목은 payload에 없어 그대로 보존 — 성별탭 단위 정합)
var CHK_PROP_PREFIX = 'chk_';
// 2026-06-12 시토: 남/여 동기화 근본수정 — 원장 키에 gender 삽입(성별별 분리 저장).
// gender 미지정/구버전 호출은 'all' 슬롯으로 격리(레거시 평면 원장과 별개). round 누수는 c 구조로 2순위 대응.
function _chkGender(g) { g = String(g || '').trim(); return (g === 'm' || g === 'f') ? g : 'all'; }
function _chkKey(dept, date, gender) {
  return CHK_PROP_PREFIX + (String(dept || 'support').trim() || 'support') + '_' + _chkGender(gender) + '_' + date;
}
// 구역 시트의 '완료' 행 제거(GM 2026-06-12) — 정상완료는 시트에 남으면 안 되는데(원장이 복원원천) 옛 행이 남아
// 가짜 완료로 복원되던 문제 정리. date 주면 그 날짜만, 없으면 전체. GET ?action=clear_zone_checks&dept=support[&date=YYYY-MM-DD]
function clearZoneCheckedRows(dept, date, all) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var removed = 0;
  [t.male, t.female, t.common].forEach(function (name) {
    var sh = ss.getSheetByName(name); if (!sh) return;
    var last = sh.getLastRow();
    // all=true(+날짜 없음)면 헤더 제외 전체 데이터 내용 비우기(행 전체삭제 제약 회피).
    if (all && !date) {
      if (last > 1) { var lc = sh.getLastColumn() || 1; sh.getRange(2, 1, last - 1, lc).clearContent(); removed += (last - 1);
        if (sh.getMaxRows() > 2) sh.deleteRows(3, sh.getMaxRows() - 2); }
      return;
    }
    var data = sh.getDataRange().getValues();
    for (var i = data.length - 1; i >= 1; i--) {
      var isDone = String(data[i][5] || '') === '완료';
      var dateOk = !date || String(data[i][0]) === date || formatDate(data[i][0]) === date;
      if (all ? dateOk : (isDone && dateOk)) { sh.deleteRow(i + 1); removed++; }
    }
  });
  return jsonRes({ ok: true, dept: dept, date: date || '(전체)', all: !!all, removed: removed });
}
// 특정 (zone 시트 × 날짜 × itemId) 한 행만 정밀 삭제 — 오라우팅으로 샌 행 청소용. 2026-06-15 시우.
// GET ?action=delete_item_row&dept=support&date=YYYY-MM-DD&zone=female&itemId=custom_...
function deleteItemRow(dept, date, zone, itemId) {
  if (!date || !zone || !itemId) return jsonRes({ error: 'date·zone·itemId 필수' });
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var name = t[zone];
  if (!name) return jsonRes({ error: 'invalid zone: ' + zone });
  var sh = ss.getSheetByName(name);
  if (!sh) return jsonRes({ error: 'sheet not found: ' + name });
  var data = sh.getDataRange().getValues();
  var match = [];
  for (var i = data.length - 1; i >= 1; i--) {
    var dateOk = String(data[i][0]) === date || formatDate(data[i][0]) === date;
    if (dateOk && String(data[i][1]) === itemId) match.push(i + 1);
  }
  var removed = 0;
  // 마지막 비고정행까지 삭제하면 구글시트 예외('고정되지 않은 행을 모두 삭제 불가') → 전체 삭제가 되는 경우 내용비우기로 폴백. GM 2026-06-16 시우.
  if (match.length > 0 && match.length >= (data.length - 1)) {
    var cols = Math.max(1, sh.getLastColumn());
    match.forEach(function (rn) { sh.getRange(rn, 1, 1, cols).clearContent(); removed++; });
  } else {
    match.forEach(function (rn) { sh.deleteRow(rn); removed++; });   // 내림차순이라 안전
  }
  return jsonRes({ ok: true, sheet: name, date: date, itemId: itemId, removed: removed });
}
// 매뉴얼(SHEET_ITEMS) 정상 id에 없는 고아·테스트 항목ID를 원장(cr)+구역시트 행에서 일괄 제거. 2026-06-16 시우.
// 고아 체크가 원장에 남으면 복원→재저장 루프로 시트에 되살아남(검증 테스트 __v_* 등). GET ?action=purge_orphan_checks&dept=support
function purgeOrphanChecks(dept) {
  dept = dept || 'support';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var valid = {};
  var im = ss.getSheetByName(SHEET_ITEMS);
  if (im) {
    var idata = im.getDataRange().getValues();
    for (var i = 1; i < idata.length; i++) {
      var iid = String(idata[i][0] || ''); if (!iid) continue;
      if (_itemDept(idata[i][ITEM_DEPT_COL]) !== dept) continue;
      valid[iid] = 1;
    }
  }
  if (Object.keys(valid).length === 0) return jsonRes({ ok: false, error: '매뉴얼 항목 0 — 안전상 중단(전수 삭제 방지)' });
  var purgedLedger = 0, purgedRows = 0, orphanIds = {};
  var props = PropertiesService.getScriptProperties();
  var all = props.getProperties();
  Object.keys(all).forEach(function (key) {
    if (key.indexOf(CHK_PROP_PREFIX + dept + '_') !== 0) return;
    var led; try { led = JSON.parse(all[key] || '{}'); } catch (e) { return; }
    if (!led) return;
    var changed = false;
    if (led.cr && typeof led.cr === 'object') {
      Object.keys(led.cr).forEach(function (ck) {
        var us = String(ck).indexOf('_'); if (us < 0) return;
        var id = ck.slice(us + 1);
        if (!valid[id]) { delete led.cr[ck]; purgedLedger++; orphanIds[id] = 1; changed = true; }
      });
    }
    if (led.c && typeof led.c === 'object') {
      Object.keys(led.c).forEach(function (id) { if (!valid[id]) { delete led.c[id]; orphanIds[id] = 1; changed = true; } });
    }
    if (changed) props.setProperty(key, JSON.stringify(led));
  });
  var t = _deptTabs(dept);
  [t.male, t.female, t.common].forEach(function (name) {
    var sh = ss.getSheetByName(name); if (!sh) return;
    var data = sh.getDataRange().getValues();
    var del = [];
    for (var r = data.length - 1; r >= 1; r--) {
      var id2 = String(data[r][1] || '');
      if (id2 && !valid[id2]) { del.push(r + 1); orphanIds[id2] = 1; }
    }
    if (del.length > 0 && del.length >= (data.length - 1)) {
      var cols = Math.max(1, sh.getLastColumn());
      del.forEach(function (rn) { sh.getRange(rn, 1, 1, cols).clearContent(); purgedRows++; });
    } else {
      del.forEach(function (rn) { try { sh.deleteRow(rn); } catch (e) { var c2 = Math.max(1, sh.getLastColumn()); sh.getRange(rn, 1, 1, c2).clearContent(); } purgedRows++; });
    }
  });
  return jsonRes({ ok: true, dept: dept, purgedLedger: purgedLedger, purgedRows: purgedRows, orphanIds: Object.keys(orphanIds) });
}
// 지원부 시트 리네임/정리 마이그레이션(GM 2026-06-12). 멱등: 이미 새 이름이면 스킵.
//   남성구역→지원_남성구역 · 여성구역→지원_여성구역 · 점검항목→지원_매뉴얼 · 공용구역 삭제.
// 검수안전: 기존행은 그대로 보존(탭 이름만 변경). 대상 새 이름이 이미 있으면 옛 탭 보존(수동확인 필요)으로 표시.
// GET ?action=migrate_support_sheets
function migrateSupportSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var log = [];
  function rename(oldName, newName) {
    var oldSh = ss.getSheetByName(oldName);
    var newSh = ss.getSheetByName(newName);
    if (newSh) { log.push('이미존재(스킵):' + newName + (oldSh ? ' / 옛탭 ' + oldName + ' 잔존' : '')); return; }
    if (!oldSh) { log.push('옛탭없음(스킵):' + oldName); return; }
    oldSh.setName(newName);
    log.push('리네임:' + oldName + '→' + newName);
  }
  rename('남성구역', SHEET_MALE);     // 지원_남성구역
  rename('여성구역', SHEET_FEMALE);   // 지원_여성구역
  rename('점검항목', SHEET_ITEMS);    // 지원_매뉴얼
  var common = ss.getSheetByName('공용구역');
  if (common) { ss.deleteSheet(common); log.push('삭제:공용구역'); }
  else { log.push('공용구역없음(스킵)'); }
  return jsonRes({ ok: true, log: log });
}

// 죽은 시설부 점검 시트 삭제(GM 2026-06-12) — 시설부 점검 미운영 → 4시트 데드. 거래업체(시설_거래업체)는 보존.
// GET ?action=delete_facility_sheets
function deleteFacilitySheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var targets = [SHEET_FACILITY_MALE, SHEET_FACILITY_FEMALE, SHEET_FACILITY_COMMON, SHEET_ISSUE_FACILITY];
  var log = [];
  targets.forEach(function (name) {
    if (name === SHEET_VENDOR) return;   // 안전: 거래업체는 절대 삭제 안 함
    var sh = ss.getSheetByName(name);
    if (sh) { ss.deleteSheet(sh); log.push('삭제:' + name); }
    else { log.push('없음(스킵):' + name); }
  });
  return jsonRes({ ok: true, log: log });
}

// 빈 껍데기 시설_남성구역·시설_여성구역 2개만 정밀 삭제(GM 2026-06-20 시우).
// 근거: 시설부는 공용 단일 탭(시설_공용구역)에만 측정 기록 — 남/여는 측정칸으로 구분. 남/여 탭은
// setupDeptSheets가 지원부 3탭 구조를 복제하며 잘못 생성한 빈 껍데기(데이터행 0·쓰기경로 없음).
// 안전장치: ① 시설_공용구역은 대상에서 원천 배제(절대 삭제 안 함) ② 삭제 전 데이터행 0 확인,
// 행이 1건이라도 있으면 그 탭은 건너뛰고 skipped로 보고(전수확인 후 수동 판단). GET ?action=delete_facility_empty_genders
function deleteFacilityEmptyGenderSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var targets = [SHEET_FACILITY_MALE, SHEET_FACILITY_FEMALE];   // 공용구역(SHEET_FACILITY_COMMON)은 절대 미포함
  var log = [];
  targets.forEach(function (name) {
    if (name === SHEET_FACILITY_COMMON || name === SHEET_VENDOR) { log.push('보호(스킵):' + name); return; }   // 이중 안전
    var sh = ss.getSheetByName(name);
    if (!sh) { log.push('없음(스킵):' + name); return; }
    var rows = Math.max(0, sh.getLastRow() - 1);   // 헤더 제외 데이터행 수
    if (rows > 0) { log.push('데이터' + rows + '행 존재→삭제보류(수동확인):' + name); return; }
    ss.deleteSheet(sh);
    log.push('삭제(빈탭):' + name);
  });
  return jsonRes({ ok: true, log: log });
}

// G열(이슈·인덱스6) 숨김 해제 필요 시 사용(2026-06-25 시우·GM): 이슈는 G열에 다시 저장되므로,
// 과거 hide_issue_col 실행으로 숨겨진 시트라면 G열을 수동으로 표시(showColumns)해야 함.
// 이 함수 자체는 보존(인덱스 보호 목적), 물리 삭제 절대 안 함. GET ?action=hide_issue_col&dept=support
function hideIssueColumn(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var ISSUE_COL = 7;   // G열(1-based) = 이슈(종합접수처), 0-based 인덱스6
  var log = [];
  [t.male, t.female].forEach(function (name) {   // 지원_남성구역 · 지원_여성구역
    var sh = ss.getSheetByName(name);
    if (!sh) { log.push('없음(스킵):' + name); return; }
    var last = sh.getLastRow();
    var cleared = 0;
    if (last > 1) { sh.getRange(2, ISSUE_COL, last - 1, 1).clearContent(); cleared = last - 1; }   // 데이터행 G열만 비움(헤더·타 열 무손상)
    sh.hideColumns(ISSUE_COL);   // 컬럼 숨김(인덱스 보존)
    log.push(name + ' G열 비움' + cleared + '행·숨김');
  });
  return jsonRes({ ok: true, dept: dept, col: 'G(이슈/index6)', log: log });
}

// G열 숨김 해제 — hide_issue_col 실행 후 이슈 저장 재활성화 시 1회 실행. GET ?action=show_issue_col&dept=support. 2026-06-25 시우.
function showIssueColumn(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var ISSUE_COL = 7;   // G열(1-based)
  var log = [];
  [t.male, t.female].forEach(function (name) {
    var sh = ss.getSheetByName(name);
    if (!sh) { log.push('없음(스킵):' + name); return; }
    sh.showColumns(ISSUE_COL);
    log.push(name + ' G열 숨김해제');
  });
  return jsonRes({ ok: true, dept: dept, col: 'G(이슈/index6)', log: log });
}

// O열(소요시간·15열·0-based 인덱스14) 옛 시각값 비우기(GM 2026-06-20 시우).
// 1차 배포 전 행에 '점검시각' 시리얼(1899-12-30 + HH:MM)이 남아 '소요시간' 헤더와 불일치.
// 시작시각 없는 옛 데이터 → 소요시간 계산 불가 → 빈칸이 정합. 컬럼 숨김 X (소요시간은 화면 표시).
// 신규 제출이 기록하는 '분(정수)' 값은 항상 숫자라 시리얼 날짜(Date 객체·문자열 "Sat Dec 30 1899…")와 구분 가능.
// GET ?action=clear_old_duration&dept=support
function clearOldDuration(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var DUR_COL = 15;   // O열(1-based) = 소요시간, 0-based 인덱스14
  var log = [];
  [t.male, t.female].forEach(function (name) {
    var sh = ss.getSheetByName(name);
    if (!sh) { log.push('없음(스킵):' + name); return; }
    var last = sh.getLastRow();
    if (last < 2) { log.push(name + ' 데이터행 없음'); return; }
    var vals = sh.getRange(2, DUR_COL, last - 1, 1).getValues();
    var cleared = 0;
    for (var i = 0; i < vals.length; i++) {
      var v = vals[i][0];
      if (v === '' || v === null || v === undefined) continue;
      // 옛 시각값 판별: Date 객체(시리얼)이거나 "Sat Dec 30 1899" 문자열
      var isOld = false;
      if (v instanceof Date) {
        isOld = true;   // 시트에서 Date로 읽히는 값은 전부 옛 시각(소요시간=분 정수는 숫자로 읽힘)
      } else if (typeof v === 'string' && v.indexOf('1899') >= 0) {
        isOld = true;
      }
      if (isOld) { sh.getRange(i + 2, DUR_COL).clearContent(); cleared++; }
    }
    log.push(name + ' O열 옛값 비움' + cleared + '행');
  });
  return jsonRes({ ok: true, dept: dept, col: 'O(소요시간/index14)', log: log });
}

// 항목 마스터(지원_매뉴얼)에서 특정 dept 행 제거(GM 2026-06-12) — 깨진 인코딩 facility 데드행 정리·경량화.
// 시설부 점검 미운영 → facility 16행(글자깨짐) 잔존 무의미. support 행만 남겨 매뉴얼 단일출처화.
// GET ?action=purge_dept_items&dept=facility
function purgeDeptItems(dept) {
  dept = String(dept || '').trim();
  if (!dept) return jsonRes({ ok: false, error: 'dept required' });
  var sheet = initItemSheet();   // 12열 보장
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return jsonRes({ ok: true, dept: dept, removed: 0 });
  var data = sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).getValues();
  var removed = 0;
  for (var i = data.length - 1; i >= 0; i--) {
    if (_itemDept(data[i][ITEM_DEPT_COL]) === dept) { sheet.deleteRow(i + 2); removed++; }
  }
  return jsonRes({ ok: true, dept: dept, removed: removed });
}

// 완료원장 일괄 비우기(GM 2026-06-12) — 오염된 체크 원장(전 날짜·성별) 제거. GET ?action=clear_check_ledger&dept=support
function clearCheckLedger(dept) {
  var props = PropertiesService.getScriptProperties();
  var all = props.getProperties();
  var prefix = CHK_PROP_PREFIX + (String(dept || 'support').trim() || 'support') + '_';
  var removed = 0;
  Object.keys(all).forEach(function (k) { if (k.indexOf(prefix) === 0) { props.deleteProperty(k); removed++; } });
  return jsonRes({ ok: true, dept: dept, removed: removed });
}
// 항상 { c:{...}, sub:{...}, subAt:{...} } 정규화 형태로 반환(구버전 평면 원장 승격).
function _getCheckLedger(dept, date, gender) {
  var led = {};
  try { led = JSON.parse(PropertiesService.getScriptProperties().getProperty(_chkKey(dept, date, gender)) || '{}'); }
  catch (e) { led = {}; }
  if (!led.c) {
    var flat = {};
    Object.keys(led).forEach(function (k) { if (k !== 'c' && k !== 'sub' && k !== 'subAt' && led[k]) flat[k] = 1; });
    led = { c: flat, sub: led.sub || {}, subAt: led.subAt || {} };
  }
  if (!led.sub) led.sub = {};
  if (!led.subAt) led.subAt = {};
  return led;
}
// 원장 구조: { c:{itemId:1,...}, sub:{am,pm,night}, subAt:{am,pm,night} }
// c=체크된 itemId 집합, sub=교대별 제출자, subAt=교대별 제출시각. 무이슈 완전완료일(시트행 0건)에도
// admin 제출자·완료율 카드를 복원하기 위해 제출 메타도 함께 적립.
// body: 전체 save payload(submitter_am 등 포함). checks: 이번 payload 항목만 반영(set/remove).
function _updateCheckLedger(dept, date, body) {
  if (!date) return;
  // 2026-06-12 시토: 저장 payload의 활성 성별탭(body.genderTab)으로 원장 키 분리 → 남/여 섞임 차단.
  var gender = (body && body.genderTab) || 'm';
  var checks = (body && body.checks) || [];
  var props = PropertiesService.getScriptProperties();
  var key = _chkKey(dept, date, gender);
  var led = {};
  try { led = JSON.parse(props.getProperty(key) || '{}'); } catch (e) {}
  // 하위호환: 구버전(평면 {itemId:1}) 원장이면 c 필드로 승격
  if (!led.c) {
    var flat = {};
    Object.keys(led).forEach(function (k) { if (k !== 'c' && k !== 'sub' && k !== 'subAt' && led[k]) flat[k] = 1; });
    led = { c: flat, sub: {}, subAt: {} };
  }
  if (!led.c) led.c = {};
  if (!led.sub) led.sub = {};
  if (!led.subAt) led.subAt = {};
  checks.forEach(function (c) {
    var id = String(c.itemId || '');
    if (!id) return;
    if (c.checked) led.c[id] = 1; else delete led.c[id];   // 이번 payload 범위 내에서만 set/remove
  });
  if (body) {
    if (body.submitter_am)    led.sub.am = String(body.submitter_am);
    if (body.submitter_pm)    led.sub.pm = String(body.submitter_pm);
    if (body.submitter_night) led.sub.night = String(body.submitter_night);
    if (body.submitter_close) led.sub.close = String(body.submitter_close);   // [근본수정 2026-06-26 시우] 마감조 전용칸(pm과 독립). 미전송 구버전 프론트면 자동 무시(하위호환).
    if (body.submittedAt_am)    led.subAt.am = String(body.submittedAt_am);
    if (body.submittedAt_pm)    led.subAt.pm = String(body.submittedAt_pm);
    if (body.submittedAt_night) led.subAt.night = String(body.submittedAt_night);
    if (body.submittedAt_close) led.subAt.close = String(body.submittedAt_close);
  }
  // 회차별 영속(2026-06-12 시우·GM): roundChecks = 현재 성별의 전체 회차 체크 키('<round>_<id>') 목록.
  // 프론트가 매 저장 시 현 상태 전체를 보내므로 led.cr 전체 교체 → 복원도 회차별(오전·오후·마감 격리).
  if (body && body.roundChecks) {
    // 회차별 머지(2026-06-17 시우·GM): 전량교체→이번 payload 회차만 교체, 타 회차 보존.
    // 오전조 제출+resetShiftChecks 후 pushToServer가 led.cr를 덮어써 제출분이 사라지던 회귀 차단.
    var thisRounds = {};
    (body.roundChecks || []).forEach(function (k) {
      var us = String(k).indexOf('_'); if (us < 0) return;
      thisRounds[String(k).slice(0, us)] = 1;
    });
    (body.roundUnchecked || []).forEach(function (k) {   // 체크해제 회차도 교체 대상(취소 정합)
      var us = String(k).indexOf('_'); if (us < 0) return;
      thisRounds[String(k).slice(0, us)] = 1;
    });
    if (!led.cr) led.cr = {};
    Object.keys(led.cr).forEach(function (k) {   // 이번 회차 키만 제거, 타 회차 보존
      var us = String(k).indexOf('_'); if (us < 0) return;
      if (thisRounds[String(k).slice(0, us)]) delete led.cr[k];
    });
    var _rcm = body.roundCheckMeta || {};
    (body.roundChecks || []).forEach(function (k) {
      if (!k) return;
      var m = _rcm[String(k)];
      // 항목별 점검자·시각·담당·이슈·노하우·온도측정·반영완료 메타가 있으면 객체로, 없으면 1(레거시 하위호환). GM 2026-06-15 시우.
      // (회차×항목) 단위 메타 정합 저장 — read 응답에 props JSON 그대로 반영됨.
      led.cr[String(k)] = (m && (m.by || m.at || m.du || m.iss || m.tip || m.measure || m.reflected))
        ? { by: String(m.by || ''), at: String(m.at || ''), du: String(m.du || ''),
            iss: String(m.iss || ''), tip: String(m.tip || ''),
            measure: String(m.measure || ''), reflected: String(m.reflected || '') }
        : 1;
    });
    // 버그수정 2026-06-25 시우: 이슈/노하우 있는 미체크 항목도 led.cr에 기록.
    // 기존엔 roundChecks(체크된 항목)만 led.cr에 기록 → 미체크 이슈는 cr에 없어 today_live에서 이슈 0건.
    // roundCheckMeta에는 이미 미체크 이슈 항목이 포함됨(페이지 _buildPushPayload 수정 완료) → cr에도 반영.
    Object.keys(_rcm).forEach(function (k) {
      if (!k) return;
      if (led.cr[String(k)]) return;   // 이미 체크 항목으로 기록됨
      var m = _rcm[String(k)];
      if (!m || (!m.iss && !m.tip)) return;   // 이슈/노하우 없으면 제외
      led.cr[String(k)] = { by: String(m.by || ''), at: String(m.at || ''), du: String(m.du || ''),
        iss: String(m.iss || ''), tip: String(m.tip || ''),
        measure: String(m.measure || ''), reflected: String(m.reflected || '') };
    });
  }
  // 점검 타이머 영속(2026-06-17 시우·GM): body.timers = { '<rk>':{s,e}, night:{s,e} } (ms 문자열).
  // led.timers에 머지 저장 — 빈값이 기존값 덮지 않게 값 있을 때만 갱신(머지). loadState가 led.timers로 복원.
  // ⚠ cr 회차머지 패턴과 정합(상시전송이지만 빈 타이머가 기존값 못 지움). support 한정·완료율 무관.
  if (body && body.timers && typeof body.timers === 'object') {
    if (!led.timers) led.timers = {};
    Object.keys(body.timers).forEach(function (rk) {
      var t = body.timers[rk] || {};
      var cur = led.timers[rk] || {};
      var s = (t.s != null && String(t.s) !== '') ? String(t.s) : (cur.s || '');
      var e = (t.e != null && String(t.e) !== '') ? String(t.e) : (cur.e || '');
      if (s || e) led.timers[rk] = { s: s, e: e };
    });
  }
  // led.seen — 분모 적립(P2 2026-06-16 시우·architect): 이번 save payload의 가시 항목 전량(체크 여부 무관).
  // 키: '<bucket>_<id>' (bucket = _shiftBucket(shift), 회차버킷 단일화). 매 저장 시 전량 교체(roundChecks 동일 패턴).
  // ⚠ 읽기 전용 분모 — led.sub(제출도장)과 완전 무관, 완료율/weekly 집계에 영향 0. support 한정.
  if (body && checks.length > 0) {
    var _seen = {};
    checks.forEach(function (c) {
      var id = String(c.itemId || '');
      if (!id) return;
      var bk = _shiftBucket(String(c.shift || 'pm'));
      _seen[bk + '_' + id] = 1;
    });
    led.seen = _seen;
  }
  props.setProperty(key, JSON.stringify(led));
}

// 정상완료(완료 & 이슈·노하우·측정 모두 없음) = 이상치 아님 → 신규 시트행 미기록 대상.
// 미완료 / 이슈 / 노하우 / 측정값 중 하나라도 있으면 '이상치' → 행 기록 유지.
function _isAnomalyCheck(c) {
  if (!c.checked) return true;                       // 미완료
  if (c.issue && String(c.issue).length > 0) return true;   // 이슈
  if (c.tip && String(c.tip).length > 0) return true;       // 노하우
  if (_measureStr(c.measure)) return true;           // 측정값
  return false;                                      // 정상완료
}

// 이상치-필터(정상완료 스킵)는 스냅샷(점검일지) 기반 완료율 백업이 있는 부서에만 적용.
// 지원부(support)만 5조·스냅샷 보유 → support 한정. 나머지 부서는 전체기록 유지(완료율 회귀 방지).
// GM 2026-06-11: 스코프=지원부. 타 부서 스냅샷 도입 시 여기 확장.
function _anomalyOnlyDept(dept) {
  return String(dept || 'support') === 'support';
}

// 시트에 행을 둘지 결정 — support는 '완료 또는 이슈/노하우/측정'만 기록(미완료·무이슈 노이즈 제외 → 시트=체크 일치).
// GM 2026-06-15: 시트랑 체크 안 맞는 미완료-무이슈 행 차단. 완료율은 원장(checkedLedger) 기반이라 시트 행 가감과 무관(회귀 0).
// 사전시드(handleSeed)는 여전히 금지. 읽기 날짜필터로 과거일 무영향.
function _shouldRow(dept, c) {
  if (!_anomalyOnlyDept(dept)) return true;                       // 타부서: 전체 기록
  if (c.checked) return true;                                     // 완료
  if (c.issue && String(c.issue).length) return true;             // 이슈
  if (c.tip && String(c.tip).length) return true;                 // 노하우
  if (c.measure && String(_measureStr(c.measure)).length) return true;  // 측정값
  return false;                                                   // 미완료·무이슈 = 노이즈 → 행 안 둠
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
    if (body.action === 'notify_round')   return handleNotifyRound(body);
    if (body.action === 'seed')           return handleSeed(body);
    if (body.action === 'saveItems')      return saveItems(body);
    if (body.action === 'syncSeedItems')  return syncSeedItems(body);   // Part1 시우: 페이지 시드 명단 → seed='Y' 격리행 멱등 upsert(타·shadow·added 불변)
    if (body.action === 'saveBoard')      return saveBoard(body);
    if (body.action === 'issuelog_add')   return handleIssueLogAdd(body);
    if (body.action === 'issuelog_update') return handleIssueLogUpdate(body);
    if (body.action === 'snapshot_append') return handleSnapshotAppend(body);   // F3: 제출 스냅샷 적립
    if (body.action === 'vendor_save')    return vendorSave(body);               // 거래업체 전체 교체 저장(시설_거래업체 시트)
    if (body.action === 'save_insp_memo') return saveInspMemo(body);            // 회차 점검자 배정 메모(공유). 2026-06-16 시우.
    if (body.action === 'unlock_round')  return handleUnlockRound(body);       // 관리자 PIN 제출잠금 해제. 2026-06-17 시우.
    if (body.action === 'save_facility_measure') return saveFacilityMeasure(body);   // 시설 측정값 저장 → 시설_공용구역 행 기록(입력=완료). weekly&dept=facility 자동집계. 2026-06-17 시우.
    return jsonRes({ error: 'unknown action' });
  } catch (err) {
    return jsonRes({ error: err.message });
  }
}

// ─── 회차별 행 저장(2026-06-15 GM·시우): 시트 행 키 = (날짜+회차+항목ID). 원장(cr) 회차별 진실을
//     시트가 그대로 미러링 → 오전조 op·마감조 cls 각각 독립 행. "시트=페이지 회차별 동일시" 정본.
//     roundChecks(회차별 체크 진실)에서 행 생성 → 미완료·무이슈 노이즈 0. 활성 성별탭만 갱신(타성별 무영향).
// 자가치유(2026-06-19 시우): 저장 후 같은 (날짜,회차라벨,항목ID) 쌍둥이 행이 생기면 즉시 접음.
// 제출완료 행 우선 보존 / 내용(결과·이슈·노하우·근무·점검자·측정·반영, 제출상태·시각 제외) 동일한 행만 제거 → 내용 다른 행은 보존.
// 정상(쌍둥이 없음)이면 무동작 = 회귀 0. 멀티콜 엣지로 인한 시트 2행 표시를 구조적으로 차단.
function _collapseDupRowsForDate(sheet, date) {
  if (!sheet || !date) return 0;
  var vals = sheet.getDataRange().getValues();
  var grp = {};
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    var dt = (String(r[0]) === date || formatDate(r[0]) === date);
    if (!dt) continue;
    var key = String(r[4]) + '|' + String(r[1]);   // 회차라벨|항목ID (이미 date로 필터됨)
    var csig = [5,6,7,10,11,12,13].map(function(c){ return String(r[c] == null ? '' : r[c]); }).join('');
    var sub = (String(r[8] || '').indexOf('제출완료') >= 0);
    if (!grp[key]) grp[key] = [];
    grp[key].push({ rn: i + 1, csig: csig, sub: sub });
  }
  var del = [];
  Object.keys(grp).forEach(function(k){
    var arr = grp[k];
    if (arr.length < 2) return;
    var keeper = null;
    for (var x = 0; x < arr.length; x++) { if (arr[x].sub) { keeper = arr[x]; break; } }
    if (!keeper) keeper = arr[0];
    arr.forEach(function(r){ if (r !== keeper && r.csig === keeper.csig) del.push(r.rn); });
  });
  del.sort(function(a, b){ return b - a; });
  del.forEach(function(rn){
    try { sheet.deleteRow(rn); }
    catch (e) { var cc = Math.max(HEADERS.length, sheet.getLastColumn()); sheet.getRange(rn, 1, 1, cc).clearContent(); }
  });
  return del.length;
}
// ═══════════════════════════════════════════
//  이슈 → 점검관리방 텔레그램 알림 (2026-06-25 시우·GM)
//  종합접수처 자동전송 완전 삭제 — 이슈는 점검 시트 G열 기록 + 점검관리방(-5136037543) 알림으로 대체.
// ═══════════════════════════════════════════

// 실시간 이슈 드립 on/off (2026-06-26 시토·GM). false=폐지 — 점검 중 자동저장마다 이슈를 항목별로
// 쪼개 보내던 알림(🔴 점검 이슈)이 회차 제출 요약(handleNotifyRound: 점검자·완료율·전체이슈·링크 종합)과
// 같은 이슈를 이중 발송하던 중복의 원인. 제출 요약이 단일 SSOT 알림. 재활성 필요 시 true 1줄로 즉시 복원.
var CHK_ISSUE_DRIP_ENABLED = false;

// 이슈 배열 → 점검관리방 텔레그램 1건 알림(이슈 여러 개면 목록으로 묶어 1메시지). fail-soft.
// issues: [{date,itemId,itemName,cat,roundLabel,issue}], gender: 'm'|'f'
function _checkNotifyIssues(issues, gender) {
  if (!CHK_ISSUE_DRIP_ENABLED) return;   // 실시간 드립 폐지 — 제출 요약(handleNotifyRound)이 단일 알림
  if (!issues || !issues.length) return;
  if (!BOT_TOKEN || !CHAT_ID) return;
  var zone = (String(gender || '') === 'f') ? '여성구역' : '남성구역';
  var lines = ['🔴 점검 이슈 — ' + zone];
  issues.forEach(function (it) {
    lines.push('· [' + String(it.roundLabel || '') + '] ' + String(it.itemName || it.itemId || '') + ': ' + String(it.issue || ''));
  });
  var msg = lines.join('\n');
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: CHAT_ID, text: msg })
    });
  } catch (e) { /* fail-soft: 알림 실패가 점검 저장에 영향 없음 */ }
}

// 이미 알림 보낸 이슈 키 추적(영속) — 자동저장·재제출마다 같은 이슈 재발송되던 중복 차단. 2026-06-25 시토·GM.
// 키 = date|itemId|issueText. 원장(_chkKey JSON)의 noti 필드에 누적. 이슈 텍스트가 바뀌면 새 키=새 알림(정상).
// noti 이력은 점검 원장(_chkKey)과 분리된 전용 속성에 저장 — 원장 저장/재구성(_updateCheckLedger)이
// noti를 날려 매 저장마다 같은 이슈가 재발송되던 스팸 차단. 2026-06-25 시우 fix(전용키 분리).
function _checkLoadNotified(dept, date, gender) {
  try { return JSON.parse(PropertiesService.getScriptProperties().getProperty('CHKNOTI|' + dept + '|' + date + '|' + (gender || 'm')) || '{}'); }
  catch (e) { return {}; }
}
function _checkSaveNotified(dept, date, gender, notiObj) {
  try { PropertiesService.getScriptProperties().setProperty('CHKNOTI|' + dept + '|' + date + '|' + (gender || 'm'), JSON.stringify(notiObj || {})); }
  catch (e) { /* fail-soft */ }
}

function _writePerRoundRows(dept, date, body) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var gender = body.genderTab || 'm';
  var checks = body.checks || [];
  var roundChecks = body.roundChecks || [];
  var rcm = body.roundCheckMeta || {};

  // 제출 상태·시각 — 영속 원장(led.sub/subAt) 단일출처. 2026-06-20 시우·GM.
  // ★버그수정: 과거엔 body.submitted_*(이번 payload 플래그)로 submitStatus 1개를 만들어 모든 행에 붙였다.
  //   자동저장(includeSubmitMeta 미포함)이 그 회차 행을 재기록할 때 플래그가 없어 '미제출'로 덮어써,
  //   제출돼 텔레그램까지 나간 회차가 시트 I열만 '미제출'로 회귀하던 버그(handleSave가 _updateCheckLedger를
  //   먼저 호출하므로, 이 시점 led.sub는 영속 제출상태 = 텔레그램 발화조건과 동일). 회차별로 led.sub에서 산출.
  var _led = _getCheckLedger(dept, date, gender);
  var _ledSub   = (_led && _led.sub)   || {};
  var _ledSubAt = (_led && _led.subAt) || {};
  var _ledTimers = (_led && _led.timers) || {};
  // 회차라벨(오전조/오후조/마감조) → 제출완료 표기. shiftKey(am/pm/night)의 제출도장(led.sub)이 곧 진실.
  function _roundSubmitStatus(roundLabel) {
    var sk = _labelToShiftKey(roundLabel);
    return (sk && _ledSub[sk]) ? (roundLabel + ' 제출완료') : '미제출';
  }
  // 소요시간(분): 회차 타이머 시작(led.timers[rk].s) ~ 제출시각(led.subAt[shiftKey]). 못 구하면 빈칸(억지계산 금지).
  function _roundDurationMin(roundKey, roundLabel) {
    var t = _ledTimers[roundKey] || {};
    var startMs = Number(t.s);
    if (!startMs || isNaN(startMs)) return '';
    // 종료시각: 타이머 완료(e) 우선, 없으면 그 조 제출시각(subAt). 둘 다 없으면 빈칸.
    var endMs = Number(t.e);
    if (!endMs || isNaN(endMs)) {
      var sk = _labelToShiftKey(roundLabel);
      var subAtStr = sk ? _ledSubAt[sk] : '';
      endMs = subAtStr ? new Date(String(subAtStr).replace(' ', 'T')).getTime() : NaN;
    }
    if (!endMs || isNaN(endMs)) return '';
    var min = Math.round((endMs - startMs) / 60000);
    if (min < 0 || min >= 24 * 60) return '';   // 음수·자정넘김 등 비정상은 빈칸
    return min + '분';
  }

  var meta = {};
  checks.forEach(function (c) { meta[String(c.itemId)] = c; });

  // 이슈 수집 — G열 저장 + 점검관리방 알림 대상. 중복 dedup: 같은 (날짜+항목ID+이슈텍스트) 1건만. 2026-06-25 시우·GM.
  var issuesToForward = [];   // [{date,itemId,itemName,cat,roundLabel,issue}]
  var _issueSeen = {};        // (date+itemId+issue) 메모리 1차 dedup(복제버그 3회차 동일값 차단)

  // 원할 행 — 대상 시트명별 그룹
  var wantByTarget = {};   // target → [{rl,id,values}]
  var seen = {};
  var primaryTarget = _deptTabs(dept)[gender === 'f' ? 'female' : 'male'];
  function pushWant(round, id, checkedRound) {
    var c = meta[id] || { itemId: id, name: '', cat: '' };
    var target = _resolveTarget(dept, id, c.cat, gender);
    if (!target) return;
    var rl = _roundKeyLabel(round);
    var mm = rcm[round + '_' + id] || {};
    var inspector = mm.by || c.submitter || defaultInspector(target, c.slot || '');
    // 제출시각(10열): 회차별 led.subAt 우선 → 항목 체크시각 → 항목 폴백.
    var _rSk = _labelToShiftKey(rl);
    var _rSubAt = _rSk ? (_ledSubAt[_rSk] || '') : '';
    var at = mm.at ? (date + ' ' + mm.at) : (c.checkedAt || _rSubAt || '');
    var duty = mm.du || body.duty || '';
    // (회차×항목) 단위 메타 우선(mm) — 이슈/노하우/온도측정/반영완료를 회차별로 격리. 없으면 항목단위(c.*) 폴백. GM 2026-06-15 시우.
    var iss = (mm.iss != null && mm.iss !== '') ? String(mm.iss) : (c.issue || '');
    // 이슈 수집 — 같은 (날짜+항목ID+이슈텍스트)는 1건만(복제버그 3회차 동일값 차단). 2026-06-25 시우.
    var _issTrim = String(iss || '').trim();
    if (_issTrim) {
      var _dk = date + '|' + id + '|' + _issTrim;
      if (!_issueSeen[_dk]) {
        _issueSeen[_dk] = 1;
        issuesToForward.push({ date: date, itemId: id, itemName: c.name, cat: c.cat, roundLabel: rl, issue: _issTrim });
      }
    }
    var tip = (mm.tip != null && mm.tip !== '') ? String(mm.tip) : (c.tip || '');
    var measure = (mm.measure != null && mm.measure !== '') ? _measureStr(mm.measure) : _measureStr(c.measure);
    var reflected = (mm.reflected != null && mm.reflected !== '') ? (mm.reflected ? 'Y' : '') : (c.reflected ? 'Y' : '');
    var values = [
      date, id, c.name, c.cat, rl,
      checkedRound ? '완료' : '미완료',
      _issTrim, tip,   // 2026-06-25 시우·GM: G열(이슈)=실제 이슈 텍스트 저장. 종합접수처 전송 폐지 — 이슈는 시트 G열 기록+점검관리방 알림으로.
      _roundSubmitStatus(rl), at, duty, inspector,   // 9열 제출상태=회차별 led.sub 단일출처(미제출 회귀 버그 수정)
      measure, reflected,
      _roundDurationMin(round, rl)    // 15열 소요시간(분) — (제출시각 − 시작시각). 못 구하면 빈칸
    ];
    var sk = target + ' ' + rl + ' ' + id;
    if (seen[sk]) return; seen[sk] = 1;
    if (!wantByTarget[target]) wantByTarget[target] = [];
    wantByTarget[target].push({ rl: rl, id: id, values: values });
  }

  // (1) 회차별 체크된 (회차,항목)
  var checkedIds = {};
  roundChecks.forEach(function (k) {
    k = String(k); var us = k.indexOf('_'); if (us < 0) return;
    var round = k.slice(0, us), id = k.slice(us + 1);
    checkedIds[id] = 1;
    pushWant(round, id, true);
  });
  // (2) 미체크지만 이슈/노하우/측정 있는 항목 → 1차 회차 행 보존
  checks.forEach(function (c) {
    var id = String(c.itemId);
    if (checkedIds[id]) return;
    if (c.issue || c.tip || _measureStr(c.measure)) {
      pushWant(_roundLabelToKey(_roundLabel(c.slot, c.shift)), id, false);
    }
  });
  // (3) F2(GM 2026-06-16 시우): 제출한 회차의 미체크 항목 → '미완료' 행 기록(시트=그 회차 전 항목 완료/미완료).
  // ★#8(2026-06-26 시우): 자동저장이 보내는 '미제출(작업중) 회차'의 미체크분은 led.cr 동기화(취소 즉시반영·_updateCheckLedger)용일 뿐 —
  //   시트 '미완료' 행으로는 쓰지 않는다(미완료 노이즈 0). 회차 제출도장(led.sub) 있는 회차만 행 기록 → F2 보존+자동저장 led.cr 정합.
  //   하위호환: 구버전 프론트는 제출회차만 roundUnchecked로 보내므로 게이트 통과(동작 불변).
  (body.roundUnchecked || []).forEach(function (k) {
    k = String(k); if (roundChecks.indexOf(k) >= 0) return;   // 체크된 회차항목은 (1)에서 완료로 기록됨
    var us = k.indexOf('_'); if (us < 0) return;
    var _ruRound = k.slice(0, us);
    var _ruSk = _labelToShiftKey(_roundKeyLabel(_ruRound));   // 회차 → 제출도장 shiftKey(am/pm/close)
    if (!(_ruSk && _ledSub[_ruSk])) return;                   // 미제출 회차 미체크분은 시트행 미기록(led.cr만 정리)
    pushWant(_ruRound, k.slice(us + 1), false);
  });

  // ★취소 정합(GM 2026-06-16 시우): 활성 성별탭에 남길 행이 0건이어도 primaryTarget을 처리 대상에 포함 →
  //   날짜 행 전량삭제 경로 진입(아래 primaryTarget 분기). 이게 없으면 마지막 체크를 풀어도 옛 행이 시트에 남아
  //   새로고침 시 (여성처럼 cr 없을 때) 시트행이 부활시키던 'uncheck 미반영' 버그. rows.length===0이면 삭제만 하고 미기록.
  if (!wantByTarget[primaryTarget]) wantByTarget[primaryTarget] = [];

  // 기록: 대상별로 이 날짜 행을 회차별 진실로 교체
  var total = 0;
  Object.keys(wantByTarget).forEach(function (name) {
    var sheet = ss.getSheetByName(name); if (!sheet) return;
    _ensureHeaders(sheet);
    var rows = wantByTarget[name].map(function (w) { return w.values; });
    if (name === primaryTarget) {
      // 회차별 업서트(2026-06-17 시우·GM): 전량삭제→이번 payload가 다루는 회차만 삭제·재기록, 타 회차 행 보존.
      //   오전조 제출+리셋·재전송 사이클에서 pm1/close1(및 보존된 am1) 행이 사라지던 회귀 차단.
      //   이번 회차 집합 = wantByTarget[name]의 회차라벨(취소로 rows=[]여도 roundUnchecked가 라벨을 넣어줌 → 그 회차만 비움).
      var handledLabels = {};
      wantByTarget[name].forEach(function (w) { handledLabels[w.rl] = 1; });
      var data = sheet.getDataRange().getValues();
      var delRows = [];
      for (var i = data.length - 1; i >= 1; i--) {
        var dateOk = String(data[i][0]) === date || formatDate(data[i][0]) === date;
        if (!dateOk) continue;
        var rl0 = String(data[i][4]);   // 5열 회차라벨
        if (handledLabels[rl0]) delRows.push(i + 1);   // 이번 회차만 삭제 대상(타 회차 보존)
      }
      delRows.forEach(function (rn) {   // 내림차순(이미 내림차순으로 쌓임)
        try { sheet.deleteRow(rn); }
        catch (e) { var _cc = Math.max(HEADERS.length, sheet.getLastColumn()); sheet.getRange(rn, 1, 1, _cc).clearContent(); }
      });
      if (rows.length) {
        var startRow = sheet.getLastRow() + 1;
        sheet.getRange(startRow, 1, rows.length, HEADERS.length).setValues(rows);
        for (var k = 0; k < rows.length; k++) _applyRowStyle(sheet, startRow + k, rows[k]);
        total += rows.length;
      }
    } else {
      // 비주력 대상(드문 _f 라우팅 등) = 회차+항목 단위 업서트(대량삭제 금지 — 타항목 보호)
      var d2 = sheet.getDataRange().getValues();
      var exist = {};
      for (var j = 1; j < d2.length; j++) {
        if (String(d2[j][0]) === date || formatDate(d2[j][0]) === date) {
          exist[String(d2[j][4]) + ' ' + String(d2[j][1])] = j + 1;
        }
      }
      var add = [];
      wantByTarget[name].forEach(function (w) {
        var rn = exist[w.rl + ' ' + w.id];
        if (rn) { sheet.getRange(rn, 1, 1, HEADERS.length).setValues([w.values]); _applyRowStyle(sheet, rn, w.values); total++; }
        else add.push(w.values);
      });
      if (add.length) {
        var sr = sheet.getLastRow() + 1;
        sheet.getRange(sr, 1, add.length, HEADERS.length).setValues(add);
        for (var m = 0; m < add.length; m++) _applyRowStyle(sheet, sr + m, add[m]);
        total += add.length;
      }
    }
    _collapseDupRowsForDate(sheet, date);   // 자가치유: 멀티콜로 생긴 (날짜·회차·항목) 쌍둥이 즉시 접음(제출완료 우선)
    _sortByDateDesc(sheet);
  });

  // 점검관리방 텔레그램 알림(fail-soft): 이슈 있는 제출 → 점검관리방(-5136037543) 1건 발송. 2026-06-25 시우·GM.
  try {
    var _noti = _checkLoadNotified(dept, date, gender);
    var _fresh = [];
    issuesToForward.forEach(function (it) {
      var _nk = it.date + '|' + it.itemId + '|' + String(it.issue || '').trim();
      if (!_noti[_nk]) { _noti[_nk] = 1; _fresh.push(it); }
    });
    if (_fresh.length) {                                  // 새 이슈만 발송 — 이미 보낸 건 재발송 안 함
      _checkNotifyIssues(_fresh, gender);
      _checkSaveNotified(dept, date, gender, _noti);
    }
  } catch (e) {}

  return jsonRes({ success: true, perRound: true, saved: total });
}

function handleSave(body) {
  _saveGroupSubmits(body.date, body.groupSubmits);   // 그룹별 제출 영속(zone/v2 두 경로 공통) — 2026-06-05 GM
  _updateCheckLedger(body.dept, body.date, body);   // 완료 체크 원장 적립(2026-06-11 시우) — 과거일 복원·완료율 회귀 방지
  // 회차별 행 저장(GM 2026-06-15): roundChecks 키가 있으면(빈 배열 포함) 회차기반 페이로드 → (날짜+회차+항목) 키로 시트=원장 미러.
  // ★GM 2026-06-16 시우: 전부 취소하면 roundChecks=[]가 와서 V2Compat(마지막행 deleteRow 예외)로 새던 'uncheck 미반영' 차단 — 빈 배열도 _writePerRoundRows로.
  if (Array.isArray(body.roundChecks)) return _writePerRoundRows(body.dept || 'support', body.date, body);
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
      date, c.itemId, c.name, c.cat, _roundLabel(c.slot, c.shift),   // 5열 회차(조 단위)
      c.checked ? '완료' : '미완료',
      c.issue || '', c.tip || '',
      body.submitStatus || '미제출',
      c.checkedAt || body.submittedAt || '',   // 항목별 체크시각 우선
      body.duty || '', inspector,              // 11열 담당자 · 12열 점검자
      _measureStr(c.measure),                  // 13열 측정값
      c.reflected ? 'Y' : ''                   // 14열 반영완료
    ];
    if (rowNum) {
      // 기존 행은 제자리 갱신 유지(이력 보존 — 정상완료로 바뀐 기존 이상치 행도 정확히 반영).
      sheet.getRange(rowNum, 1, 1, HEADERS.length).setValues([values]);
      _applyRowStyle(sheet, rowNum, values);
      updated++;
    } else if (_shouldRow(dept, c)) {
      // support: 완료·이슈있는 항목만 신규기록(미완료-무이슈 제외). 타부서: 전체. GM 2026-06-15.
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

// ─── 시트를 [날짜 내림차순, 제출시각(J열) 오름차순, 카테고리, 항목ID]로 정렬 — 2026-06-04 GM / 2026-06-20 GM·시우 ───
// ★GM 2026-06-20: 정렬이 뒤죽박죽 → 같은 날짜 안에서 J열(제출시각·인덱스9) 오름차순(먼저 제출=위)으로 점검 진행순서가 자연히 보이게.
//   빈 제출시각은 맨 아래. 카테고리(_MANUAL_CAT_ORDER)·항목ID는 제출시각이 같을 때의 3·4순위 타이브레이커로만 남김.
//   range.sort는 한글·시각 혼재를 원하는 순서로 못 정렬해 JS 정렬 후 setValues + 행 서식 재적용.
function _sortByDateDesc(sheet) {
  if (!sheet) return;
  var last = sheet.getLastRow();
  if (last < 3) return;  // 헤더 + 1행 이하면 정렬 불필요
  var rng = sheet.getRange(2, 1, last - 1, HEADERS.length);
  var vals = rng.getValues();
  function dts(v) { if (v instanceof Date) return v.getTime(); var t = new Date(String(v == null ? '' : v).replace(' ', 'T')).getTime(); return isNaN(t) ? 0 : t; }
  function subTs(v) {   // J열 제출시각 → ms. 빈값·파싱불가는 무한대(맨 아래로).
    var s = (v instanceof Date) ? v.getTime() : new Date(String(v == null ? '' : v).replace(' ', 'T')).getTime();
    return (v == null || String(v) === '' || isNaN(s)) ? Infinity : s;
  }
  vals.sort(function (a, b) {
    var da = dts(a[0]), db = dts(b[0]); if (da !== db) return db - da;                 // 1순위: 날짜 내림차순(최신 위)
    var sa = subTs(a[9]), sb = subTs(b[9]); if (sa !== sb) return sa - sb;             // 2순위: 제출시각(J열·인덱스9) 오름차순, 빈값 맨 아래
    var ra = _manualCatRank(a[3]), rb = _manualCatRank(b[3]); if (ra !== rb) return ra - rb; // 3순위: 카테고리(오픈점검→A→B→C→D→E→마감)
    var ia = String(a[1]), ib = String(b[1]); return ia < ib ? -1 : (ia > ib ? 1 : 0);  // 4순위: 항목ID
  });
  rng.setValues(vals);
  for (var k = 0; k < vals.length; k++) _applyRowStyle(sheet, k + 2, vals[k]);          // 정렬 후 상태색 재적용(setValues는 서식 미이동)
}

// ─── v2 프론트엔드 하위 호환 (zone 없이 genderTab으로 호출) ───

function _routeItem(itemId, cat, genderTab) {
  // 추가항목(custom_/cx_)은 랜덤 id 접미사에 우연히 든 _f/_m 부분문자열로 오라우팅됨
  // (실측 2026-06-15: custom_1780808043234_fpxs5 → '_f' 매칭 → 남자 점검이 여성 시트로 유실).
  // id 기반 성별판정에서 제외하고 현재 탭(genderTab) 기준으로 라우팅. 2026-06-15 시우.
  // 2026-06-17 시우(근본수정): 부분문자열 indexOf→접미사 경계 정확매칭.
  // 실제 성별항목 id는 '_m'/'_f'로 끝남(b4_m 수면실·b4_f 찜질방). custom_..._fpxs5 같은
  // 우연 부분문자열은 '_f'/'_m' 뒤에 영숫자가 와 비매칭(과거 오라우팅 차단). custom_ 접두사 특례 불필요.
  var _rid = String(itemId);
  if (/_f(_|$)/.test(_rid)) return SHEET_FEMALE;
  if (/_m(_|$)/.test(_rid)) return SHEET_MALE;
  if (cat && (cat.charAt(0) === 'A' || cat.charAt(0) === 'B'
      || cat.indexOf('사우나') >= 0 || cat.indexOf('락커') >= 0
      || cat.indexOf('데일리') >= 0)) {
    return genderTab === 'f' ? SHEET_FEMALE : SHEET_MALE;
  }
  return SHEET_COMMON;
}

// ─── 라우팅 회귀 자기검사 (4부서 동시) — GAS 편집기서 실행하면 PASS/FAIL 로그. 2026-06-17 시우. ───
function _selfTestRouting() {
  var F = SHEET_FEMALE, M = SHEET_MALE, C = SHEET_COMMON;
  var cases = [
    // [itemId, cat, genderTab, expect]
    ['b4_f', 'B 락커룸', 'f', F],          // 여 성별항목 접미사
    ['b4_m', 'B 락커룸', 'm', M],          // 남 성별항목 접미사
    ['custom_1780808043234_fpxs5', '추가', 'm', C],  // ★과거 오라우팅 버그: '_f' 우연포함→이제 공용
    ['custom_1780808043234_mxyz9', '추가', 'f', C],  // '_m' 우연포함→이제 공용
    ['a1', 'A 사우나 점검', 'm', M],        // 카테고리 A→활성 성별탭(남)
    ['a1', 'A 사우나 점검', 'f', F],        // 카테고리 A→활성 성별탭(여)
    ['cx_ops_daily', '운영점검', 'm', C],   // 비A/B 일반→공용
    ['floor_safety', '안전', 'm', C]        // _f/_m 없음→공용
  ];
  var pass = 0, fail = 0, log = [];
  cases.forEach(function (t) {
    var got = _routeItem(t[0], t[1], t[2]);
    var ok = got === t[3];
    ok ? pass++ : fail++;
    log.push((ok ? 'PASS' : 'FAIL') + ' id=' + t[0] + ' g=' + t[2] + ' got=' + got + ' exp=' + t[3]);
  });
  var summary = '_selfTestRouting: ' + pass + ' PASS / ' + fail + ' FAIL\n' + log.join('\n');
  Logger.log(summary);
  return summary;
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
  if (body.submitted_close) parts.push('마감조 제출완료');   // 2026-06-26 시우: close 시프트 보강(am/pm/night 동일 패턴)
  if (body.submitted_night) parts.push('탕청소 제출완료');
  var submitStatus = parts.length > 0 ? parts.join(' / ') : '미제출';
  var submitAt = body.submittedAt_am || body.submittedAt_pm || body.submittedAt_close || body.submittedAt_night || '';
  var submitters = [];
  if (body.submitter_am) submitters.push(body.submitter_am);
  if (body.submitter_pm) submitters.push(body.submitter_pm);
  if (body.submitter_close) submitters.push(body.submitter_close);   // 2026-06-26 시우: close 보강
  if (body.submitter_night) submitters.push(body.submitter_night);
  var submitter = submitters.join(' / ');

  // dept별 전용 탭으로 라우팅 (S5 단일 출처 _deptTabs · 2026-06-10 시토)
  var _dt = _deptTabs(dept);
  var tMale   = _dt.male;
  var tFemale = _dt.female;
  var tCommon = _dt.common;

  // 2026-06-12 GM: 지원부 공용구역 폐기 → 공용 항목도 활성 성별탭(점검(남)→남성/점검(여)→여성)으로 라우팅.
  // 공용항목→성별탭 강제는 지원부 한정(타부서는 공용탭 유지). dept 스코프 명시로 타부서 회귀 차단. 2026-06-17 시우.
  var commonToGender = (dept === 'support');
  var buckets = {};
  buckets[tMale] = [];
  buckets[tFemale] = [];
  if (tCommon) buckets[tCommon] = [];
  checks.forEach(function(c) {
    // _routeItem은 지원부 탭명 기준이므로 결과를 dept별 탭명으로 리매핑
    var supportTarget = _routeItem(c.itemId, c.cat, gender);
    var target = supportTarget === SHEET_MALE   ? tMale
               : supportTarget === SHEET_FEMALE ? tFemale
               : commonToGender ? (gender === 'f' ? tFemale : tMale)
               : tCommon;
    if (!buckets[target]) buckets[target] = [];
    buckets[target].push(c);
  });

  var totalSaved = 0;
  [tMale, tFemale, tCommon].filter(function(n){return !!n;}).forEach(function(name) {
    var items = buckets[name];
    if (items.length === 0) return;
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;
    _ensureHeaders(sheet);   // 담당자(15열) 등 신규 컬럼 헤더 자동 보강(기존 시트 마이그레이션)

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
    var rowsToDelete = [];
    items.forEach(function(c) {
      var rowNum = existingMap[c.itemId];
      var values = [
        date, c.itemId, c.name, c.cat, _roundLabel(c.slot, c.shift),   // 5열 회차(조 단위)
        c.checked ? '완료' : '미완료',
        c.issue || '', c.tip || '',
        submitStatus, (c.checkedAt || submitAt),
        body.duty || '',                                               // 11열 담당자
        c.submitter || submitter || defaultInspector(name, c.slot || ''),  // 12열 점검자
        _measureStr(c.measure),                                        // 13열 측정값
        c.reflected ? 'Y' : '',                                        // 14열 반영완료
        ''                                                             // 15열 점검시각(V2Compat은 항목별 시각 없음 → 빈값)
      ];
      if (rowNum) {
        if (!_shouldRow(dept, c)) {
          // 미완료·무이슈 = 시트에 둘 필요 없음 → 기존 행 삭제(시트=체크 일치). GM 2026-06-15.
          rowsToDelete.push(rowNum);
        } else {
          sheet.getRange(rowNum, 1, 1, HEADERS.length).setValues([values]);
          _applyRowStyle(sheet, rowNum, values);
          totalSaved++;
        }
      } else if (_shouldRow(dept, c)) {
        // support: 완료·이슈있는 항목만 신규기록(미완료-무이슈 제외). 타부서: 전체. GM 2026-06-15.
        newRows.push(values);
      }
    });
    if (rowsToDelete.length) {
      rowsToDelete.sort(function(a, b){ return b - a; });   // 내림차순 삭제(인덱스 안정)
      rowsToDelete.forEach(function(rn){
        try { sheet.deleteRow(rn); }
        catch (e) { var _cc = Math.max(HEADERS.length, sheet.getLastColumn()); sheet.getRange(rn, 1, 1, _cc).clearContent(); }   // 마지막행 삭제 예외 폴백. GM 2026-06-16 시우.
      });
    }
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

// 기존 점검 시트 헤더 자동 보강 — HEADERS가 늘어나면(예 담당자 15열) 헤더행만 갱신(데이터 무변경·멱등).
function _ensureHeaders(sheet) {
  if (!sheet) return;
  if (sheet.getLastColumn() < HEADERS.length) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  }
}
// 해당 dept의 구역 시트 3종에 담당자(15열) 등 신규 헤더 즉시 보강. GET ?action=ensure_headers&dept=support
function ensureAllHeaders(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var t = _deptTabs(dept);
  var done = [];
  [t.male, t.female, t.common].forEach(function (name) {
    var sh = ss.getSheetByName(name); if (!sh) return;
    _ensureHeaders(sh);
    if (sh.getLastColumn() >= HEADERS.length) sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);   // 1행 헤더 라벨 강제정합(담당자→근무자 등 변경 반영, 데이터행 무영향). 2026-06-16 시우.
    done.push(name);
  });
  return jsonRes({ ok: true, dept: dept, sheets: done, headers: HEADERS });
}

// ════════════════════════════════════════════
// 거래업체 (시설부) — 시설_거래업체 시트 (GM 2026-06-12)
// 미사용 '점검자' 시트를 전환(rename) 또는 신규 생성. 1행=1업체, 전체 교체 저장(레이스 없음).
// ════════════════════════════════════════════
var SHEET_VENDOR = '시설_거래업체';
var VENDOR_HEADERS = ['id', '분류', 'colKey', '업체명', '담당자', '연락처', '계약형태', '단가', '갱신일', '거래상태', '비고', '생성일', '수정일'];
function _vendorSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_VENDOR);
  if (!sh) {
    var old = ss.getSheetByName('점검자');   // 미사용 점검자 시트 전환(추천)
    if (old) { old.setName(SHEET_VENDOR); sh = old; sh.clear(); }
    else { sh = ss.insertSheet(SHEET_VENDOR); }
    sh.getRange(1, 1, 1, VENDOR_HEADERS.length).setValues([VENDOR_HEADERS]);
  } else if (sh.getLastColumn() < VENDOR_HEADERS.length) {
    sh.getRange(1, 1, 1, VENDOR_HEADERS.length).setValues([VENDOR_HEADERS]);
  }
  return sh;
}
// GET ?action=vendor_list → { ok, vendors:[{id,col,label,name,...}] }
function vendorList() {
  var sh = _vendorSheet();
  var data = sh.getDataRange().getValues();
  var out = [];
  for (var i = 1; i < data.length; i++) {
    var r = data[i];
    if (!String(r[0] || '') && !String(r[3] || '')) continue;   // 빈 행 스킵
    out.push({
      id: _vstr(r[0]), label: _vstr(r[1]), col: _vstr(r[2]) || _vstr(r[1]),
      name: _vstr(r[3]), manager: _vstr(r[4]), contact: _vstr(r[5]),
      contract: _vstr(r[6]), price: _vstr(r[7]), renewal: _vstr(r[8]),
      status: _vstr(r[9]) || '거래중', note: _vstr(r[10]),
      createdAt: _vstr(r[11]), updatedAt: _vstr(r[12])
    });
  }
  return jsonRes({ ok: true, vendors: out });
}
// POST {action:'vendor_save', vendors:[...]} → 데이터행 전체 교체
function vendorSave(body) {
  var sh = _vendorSheet();
  var vendors = (body && body.vendors) || [];
  var last = sh.getLastRow();
  if (last > 1) sh.getRange(2, 1, last - 1, VENDOR_HEADERS.length).clearContent();
  if (vendors.length) {
    var rows = vendors.map(function (v) {
      return [String(v.id || ''), String(v.label || ''), String(v.col || ''), String(v.name || ''),
        String(v.manager || ''), String(v.contact || ''), String(v.contract || ''), String(v.price || ''),
        String(v.renewal || ''), String(v.status || '거래중'), String(v.note || ''),
        String(v.createdAt || ''), String(v.updatedAt || '')];
    });
    var rng = sh.getRange(2, 1, rows.length, VENDOR_HEADERS.length);
    rng.setNumberFormat('@');   // 텍스트 고정 — 날짜(생성일 등) 자동변환 방지
    rng.setValues(rows);
  }
  return jsonRes({ ok: true, count: vendors.length });
}
// 셀값 안전 문자열화(Date면 yyyy-MM-dd)
function _vstr(x) {
  if (x instanceof Date) { return Utilities.formatDate(x, Session.getScriptTimeZone(), 'yyyy-MM-dd'); }
  return String(x == null ? '' : x);
}

// custom_ 항목 일괄 삭제(GM 2026-06-12): ① 점검항목 마스터(해당 dept의 custom_만) ② 구역 시트(남/여/공용)의 custom_ 행.
// GET ?action=purge_custom&dept=support 로 호출(배포 후). 기본항목 수정분(custom_ 아닌 shadow)은 보존.
function purgeCustomItems(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var d = String(dept || 'support');
  var removed = { items: 0, rows: 0 };
  // 1) 점검항목 마스터: 항목ID(0열)=custom_ AND 부서(9열)=dept 인 행 삭제
  var itemSheet = ss.getSheetByName(SHEET_ITEMS);
  if (itemSheet) {
    var idata = itemSheet.getDataRange().getValues();
    for (var i = idata.length - 1; i >= 1; i--) {
      var iid = String(idata[i][0] || '');
      var idept = String(idata[i][9] || '');
      if (iid.indexOf('custom_') === 0 && (idept === d || idept === '')) {
        itemSheet.deleteRow(i + 1); removed.items++;
      }
    }
  }
  // 2) 구역 시트: 항목ID(1열)=custom_ 행 삭제
  var t = _deptTabs(d);
  [t.male, t.female, t.common].forEach(function (name) {
    var sh = ss.getSheetByName(name); if (!sh) return;
    var zd = sh.getDataRange().getValues();
    for (var j = zd.length - 1; j >= 1; j--) {
      if (String(zd[j][1] || '').indexOf('custom_') === 0) { sh.deleteRow(j + 1); removed.rows++; }
    }
  });
  return jsonRes({ ok: true, dept: d, removed: removed });
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
  // 2026-06-12 GM·시토: 이상치-only 부서(support)는 항목 사전시드 금지.
  // 사전시드하면 모든 항목이 시트행으로 깔려 → 누적·거짓완료·체크리셋 재발("똑같은데"의 뿌리). 시트엔 이상치/이슈만.
  if (_anomalyOnlyDept(dept)) return jsonRes({ success: true, seeded: 0, note: 'anomaly-only dept: no pre-seed' });
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

// ─── 회차 제출 텔레그램 보고(2026-06-15 GM·시우) — 프론트 submitRound에서만 호출. 서버는 단순 전송(자기증식 금지).
// body: { action:'notify_round', dept, date, gender, round(am1|pm1|close1), issues(JSON 배열 or 문자열), pct, pageLink }
// 토큰 SSOT = handleNotify와 동일(ScriptProperties BOT_TOKEN/CHAT_ID). 봇/Chat 없으면 미발송 보고.
function handleNotifyRound(body) {
  if (!BOT_TOKEN || !CHAT_ID) return jsonRes({ success: false, reason: 'no telegram config' });
  var roundLabel = _roundKeyLabel(body.round || '');
  // 이슈: JSON 배열 문자열 / 배열 / 문자열 모두 수용 → 목록 문자열로 정규화.
  var issues = body.issues;
  if (typeof issues === 'string') {
    try { var p = JSON.parse(issues); if (Array.isArray(p)) issues = p; } catch (e) {}
  }
  var issueText;
  if (Array.isArray(issues)) {
    var list = issues.map(function (x) { return String(x || '').trim(); }).filter(function (x) { return x.length; });
    issueText = list.length ? list.join(', ') : '없음';
  } else {
    var s = String(issues == null ? '' : issues).trim();
    issueText = s.length ? s : '없음';
  }
  var pct = (body.pct == null || body.pct === '') ? '' : String(body.pct);
  // 프론트가 완성 메시지(message)를 보내면 그대로(plain). 없으면 서버 조립. URL의 &는 plain이라 안전(HTML 파싱 깨짐 없음).
  var msg;
  if (body.message) {
    msg = String(body.message);
  } else {
    var lines = [
      '🧹 지원부 점검 — ' + roundLabel + ' 제출',
      '완료율 ' + pct + '%',
      '이슈: ' + issueText
    ];
    if (body.pageLink) lines.push(String(body.pageLink));
    msg = lines.join('\n');
  }
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: CHAT_ID, text: msg, disable_web_page_preview: true })
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
  if (sheet) { _ensureItemCols(sheet); return sheet; }
  sheet = ss.insertSheet(SHEET_ITEMS);
  sheet.appendRow(ITEM_HEADERS);
  sheet.getRange(1, 1, 1, ITEM_HEADERS.length)
    .setBackground('#2a2725').setFontColor('#B79F8A')
    .setFontWeight('bold').setHorizontalAlignment('center');
  sheet.setFrozenRows(1);
  var widths = [180, 180, 240, 360, 80, 70, 90, 200, 90, 120, 140];  // 11칸(시드 폐지 2026-06-29): …부서·회차·점검일정
  for (var i = 0; i < widths.length; i++) sheet.setColumnWidth(i + 1, widths[i]);
  return sheet;
}
// 구버전 시트(11열 이하)에 '일정'(12열) 등 누락 열 보장 — saveItems 전체폭 read/write 전에 호출(범위오류 방지).
function _ensureItemCols(sheet) {
  var need = ITEM_HEADERS.length;
  var have = sheet.getMaxColumns();
  if (have < need) sheet.insertColumnsAfter(have, need - have);
  sheet.getRange(1, 1, 1, need).setValues([ITEM_HEADERS]);   // 헤더 정합(신규 열 라벨 기록)
}

// ─── 항목 조회 (GET ?action=items[&dept=...]) ───
// S4 갭②(2026-06-10 시토): dept 필터 — 요청 dept(기본 'support')와 일치하는 항목만 반환.
// 항목 '부서' 빈값 = 레거시(원본 지원부) → 'support' 폴백. 시설/운영/주차 화면 교차노출 차단.
// ─── 점검일정(요일·몇째주) 한글 ↔ 영어 변환 (2026-06-29 시우) ───
// 시트(DB)엔 사람이 읽는 한글(매주 화요일 · 토요일 · 둘째·넷째주)로 저장, 페이지엔 코드가 쓰는 영어(tue| · sat|2,4)로 변환해 전달.
// 페이지 JS·요일 거르기는 영어 그대로 받아 무변경. 변환은 GAS 길목(getItems 읽기·saveItems 쓰기)에서만 — 페이지 0변경.
var _SCHED_E2K = { mon:'월', tue:'화', wed:'수', thu:'목', fri:'금', sat:'토', sun:'일' };
var _SCHED_K2E = { '월':'mon','화':'tue','수':'wed','목':'thu','금':'fri','토':'sat','일':'sun' };
var _SCHED_WK_E2K = { '1':'첫째','2':'둘째','3':'셋째','4':'넷째','5':'다섯째' };
var _SCHED_WK_K2E = { '첫째':'1','둘째':'2','셋째':'3','넷째':'4','다섯째':'5' };
var _SCHED_DAY_ORDER = ['mon','tue','wed','thu','fri','sat','sun'];
// 영어 sched 정규화(요일·주차 표준순서) — 비교/왕복검증 기준
function _schedNormEng(eng){
  eng = String(eng||'').trim(); if(!eng) return '';
  var p = eng.split('|'); var days=(p[0]||'').split(',').filter(Boolean); var wks=(p[1]||'').split(',').filter(Boolean);
  var ds = _SCHED_DAY_ORDER.filter(function(d){return days.indexOf(d)>=0;});
  var ws = []; ['1','2','3','4','5'].forEach(function(w){ if(wks.indexOf(w)>=0) ws.push(w); }); if(wks.indexOf('b')>=0) ws.push('b');
  if(!ds.length && !ws.length) return '';
  return ds.join(',')+'|'+ws.join(',');
}
// 영어 → 한글 표시
function _schedToKorean(eng){
  eng = String(eng||'').trim();
  if(eng && !/[a-z]/i.test(eng)) return eng;   // 이미 한글이면 그대로
  var n = _schedNormEng(eng);
  if(!n) return '매일';
  var p = n.split('|'); var days=(p[0]||'').split(',').filter(Boolean); var wks=(p[1]||'').split(',').filter(Boolean);
  var dayStr = days.map(function(d){ return _SCHED_E2K[d]||d; }).join('·');
  var ords = wks.filter(function(w){return w!=='b';}).map(function(w){ return _SCHED_WK_E2K[w]||w; });
  var wkParts = []; if(ords.length) wkParts.push(ords.join('·')+'주'); if(wks.indexOf('b')>=0) wkParts.push('격주');
  var wkStr = wkParts.join(' · ');
  if(days.length && !wks.length) return '매주 '+dayStr+'요일';
  if(days.length && wks.length) return wkStr+' '+dayStr+'요일';   // 주간 앞 · 요일 뒤 (GM 2026-06-29) 예: 둘째·넷째주 토요일
  return wkStr;
}
// 한글/영어 → 영어(페이지 표준형). '요일' 접미 먼저 제거(일요일의 '일'과 충돌 방지) 후 요일자 스캔.
function _schedToEnglish(s){
  s = String(s||'').trim();
  if(!s || s.indexOf('매일')>=0) return '';
  if(/[a-z]/i.test(s) && !/[월화수목금토일]/.test(s)) return _schedNormEng(s);   // 영어 입력
  var t = s.replace(/요일/g,'');
  var days=[]; '월화수목금토일'.split('').forEach(function(c){ if(t.indexOf(c)>=0) days.push(_SCHED_K2E[c]); });
  var wks=[]; Object.keys(_SCHED_WK_K2E).forEach(function(k){ if(s.indexOf(k)>=0) wks.push(_SCHED_WK_K2E[k]); });
  if(s.indexOf('격주')>=0) wks.push('b');
  var ds = _SCHED_DAY_ORDER.filter(function(d){return days.indexOf(d)>=0;});
  var ws=[]; ['1','2','3','4','5'].forEach(function(w){ if(wks.indexOf(w)>=0) ws.push(w); }); if(wks.indexOf('b')>=0) ws.push('b');
  if(!ds.length && !ws.length) return '';
  return ds.join(',')+'|'+ws.join(',');
}

// ─── 성별·타입·부서·회차 기존값 한글 전환 + 시드칸 삭제 (GET ?action=migrate_sheet_korean[&dept=support]) — 2026-06-29 시우 ───
// 시트 칸을 사람이 읽는 한글로 1회 전환. 각 칸 왕복검증(한글→영어가 원래와 같은지) 통과해야만 기록(거르기 회귀 0). 끝에 데드 '시드' 열 삭제.
function migrateSheetKorean(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ ok: false, error: 'no item sheet' });
  var last = sheet.getLastRow(), lastCol = sheet.getLastColumn();
  if (last < 2) return jsonRes({ ok: true, changed: 0 });
  var data = sheet.getRange(2, 1, last - 1, lastCol).getValues();
  var changed = 0, mism = [];
  // 0성별=idx4 · 타입=idx6 · 부서=idx8 · 회차=idx9 · 점검일정=idx10
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    if (!String(r[0] || '').trim() && !String(r[2] || '').trim()) continue;   // 빈 행 스킵
    var id = String(r[1] || '');
    // 성별
    var g0 = String(r[4] || ''), gK = _genderToKorean(g0);
    if (_genderToEnglish(gK) !== _genderToEnglish(g0)) mism.push('성별:' + id);
    else if (gK !== g0) { r[4] = gK; changed++; }
    // 타입
    var t0 = String(r[6] || ''), tK = _typeToKorean(t0);
    if (_typeToEnglish(tK) !== _typeToEnglish(t0)) mism.push('타입:' + id);
    else if (tK !== t0) { r[6] = tK; changed++; }
    // 부서
    var d0 = String(r[8] || ''), dK = _deptToKorean(d0);
    if (_itemDept(dK) !== _itemDept(d0)) mism.push('부서:' + id);
    else if (dK !== d0) { r[8] = dK; changed++; }
    // 회차
    var rd0 = String(r[9] || ''), rdK = _roundsToKorean(rd0);
    if (_roundsToEnglish(rdK) !== _roundsToEnglish(rd0)) mism.push('회차:' + id);
    else if (rdK !== rd0) { r[9] = rdK; changed++; }
    // 점검일정(이미 한글일 수 있음 — 재정합)
    if (lastCol > 10) {
      var s0 = String(r[10] || ''), sK = _schedToKorean(_schedToEnglish(s0));
      if (_schedNormEng(_schedToEnglish(sK)) !== _schedNormEng(_schedToEnglish(s0))) mism.push('점검일정:' + id);
      else if (sK !== s0) { r[10] = sK; changed++; }
    }
  }
  if (mism.length) return jsonRes({ ok: false, error: '왕복검증 불일치 — 안전상 중단(미기록)', mism: mism });
  sheet.getRange(2, 1, data.length, lastCol).setValues(data);
  // 데드 '시드' 열 삭제
  var seedDeleted = false;
  var hdr = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  for (var c = hdr.length - 1; c >= 0; c--) {
    if (String(hdr[c]).trim() === '시드') { sheet.deleteColumn(c + 1); seedDeleted = true; break; }
  }
  // 헤더 라벨 11칸 정합
  sheet.getRange(1, 1, 1, ITEM_HEADERS.length).setValues([ITEM_HEADERS]);
  return jsonRes({ ok: true, changed: changed, seedDeleted: seedDeleted, cols: sheet.getLastColumn() });
}

// ─── 점검일정 기존값 한글 전환 (GET ?action=migrate_sched_korean[&dept=support]) — 2026-06-29 시우 ───
// 시트의 점검일정 칸(영어 tue| 등)을 한글 표시(매주 화요일 등)로 1회 전환. 각 칸 왕복검증(한글→영어가 원래와 같은지) 통과해야만 기록(거르기 회귀 0 보장). 빈칸→'매일'.
function migrateSchedKorean(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ ok: false, error: 'no item sheet' });
  var last = sheet.getLastRow();
  if (last < 2) return jsonRes({ ok: true, changed: 0 });
  var col = ITEM_SCHED_COL + 1;   // 1-based
  var rng = sheet.getRange(2, col, last - 1, 1);
  var vals = rng.getValues();
  var ids = sheet.getRange(2, 2, last - 1, 1).getValues();
  var changed = [], mismatches = [];
  for (var i = 0; i < vals.length; i++) {
    var cur = String(vals[i][0] == null ? '' : vals[i][0]).trim();
    var eng = _schedToEnglish(cur);
    var kor = _schedToKorean(eng);
    var back = _schedToEnglish(kor);
    if (_schedNormEng(back) !== _schedNormEng(eng)) { mismatches.push({ id: String(ids[i][0] || ''), cur: cur, eng: eng, kor: kor, back: back }); continue; }
    if (kor !== cur) { vals[i][0] = kor; changed.push(String(ids[i][0] || '') + ': "' + cur + '" → "' + kor + '"'); }
  }
  if (mismatches.length) return jsonRes({ ok: false, error: '왕복검증 불일치 — 안전상 중단(미기록)', mismatches: mismatches });
  rng.setValues(vals);
  return jsonRes({ ok: true, changed: changed.length, detail: changed });
}

function getItems(params) {
  var reqDept = (params && params.dept) ? String(params.dept).trim() : 'support';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ items: [] });
  var data = sheet.getDataRange().getValues();
  var items = [];
  for (var i = 1; i < data.length; i++) {
    if (!data[i][0] && !data[i][2]) continue; // id·항목명 모두 없으면 건너뜀
    // seed='Y' skip 제거(2026-06-27): 시트=단일출처 → seed 행도 마스터로 포함.
    if (_itemDept(data[i][ITEM_DEPT_COL]) !== reqDept) continue; // dept 불일치 제외
    // S1(2026-06-10 시토): type 빈값 → 'check' 폴백. fields = measure 입력 영문키 목록(없으면 빈문자).
    var itemType = _typeToEnglish(data[i][6]);   // 한글(점검/측정)→영어. 빈값→check.
    items.push({
      id:     String(data[i][0] || ''),
      cat:    String(data[i][1] || ''),
      name:   String(data[i][2] || ''),
      detail: String(data[i][3] || ''),
      gender: _genderToEnglish(data[i][4]),   // 한글(공통/남/여)→영어(all/m/f). 탭 거르기 무변경.
      slot:   '',   // 시간대 열 폐지(12칸) — slot 무효. 프론트는 회차/카테고리 기반.
      order:  data[i][5] !== '' && data[i][5] != null ? Number(data[i][5]) : (i),
      type:   itemType,
      fields: String(data[i][7] || ''),
      dept:   _itemDept(data[i][ITEM_DEPT_COL]),
      // 회차(rounds) — 시트엔 한글(오전조/오후조/마감조) 저장, 페이지엔 영어코드(am1/pm1/close1)로 변환. 빈값 → 프론트 폴백.
      rounds: _roundsToEnglish(data[i][ITEM_ROUNDS_COL]),
      // 점검일정(요일·몇째주) — 시트엔 한글 저장, 페이지엔 영어("tue,fri|2")로 되돌려 전달(거르기 무변경). 2026-06-29 시우.
      sched: _schedToEnglish(data[i][ITEM_SCHED_COL] == null ? '' : data[i][ITEM_SCHED_COL])
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
      // 2026-06-29 시우: '시드' 개념 완전 폐기 — seed='Y' 행 별도 보존 제거(이게 saveItems 시 시드행 1개씩 중복증식의 뿌리). 타 dept 행만 보존.
      if (_itemDept(r[ITEM_DEPT_COL]) !== reqDept) preserved.push(r);
    }
  }

  // 2) 본 dept 신규 행 구성(부서 컬럼에 reqDept 박제)
  var mine = items.map(function (it, idx) {
    return [
      String(it.id || ''),
      String(it.cat || ''),
      String(it.name || ''),
      String(it.detail || ''),
      _genderToKorean(it.gender || 'all'),   // 성별(한글 저장 공통/남/여) — getItems가 영어로 되돌림. 2026-06-29 시우.
      it.order !== undefined && it.order !== '' ? it.order : (idx + 1),
      // S1: 타입 패스스루(빈값→check). 시트엔 한글(점검/측정) 저장. 2026-06-29 시우.
      _typeToKorean(String(it.type || '').trim() || 'check'),
      String(it.fields || ''),
      _deptToKorean(reqDept),   // 부서(한글 저장 지원부) — _itemDept가 거르기 때 표준코드로 되돌림. 2026-06-29 시우.
      _roundsToKorean(it.rounds || ''),   // 회차(한글 저장 오전조/오후조/마감조) — getItems가 am1/pm1/close1로 되돌림. 2026-06-29 시우.
      _schedToKorean(it.sched || '')     // 점검일정(한글 저장 매주 화요일 등) — getItems가 영어로 되돌림. 2026-06-29 시우. ★시드칸 폐지(11칸 스키마)
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

// ─── 페이지 원장 근무자 통일 (GET ?action=set_ledger_duty&dept&date=yyyy-MM-dd&gender=m|f&round=am1&name) — 2026-06-29 시우 ───
// 페이지(지원부 체계)는 시트가 아닌 ScriptProperties 원장 led.cr[<round>_<id>].du 에서 근무자를 읽어 복원한다.
// set_round_duty(시트 col10)의 페이지측 짝 — 같은 stale 오염을 원장에서도 1명으로 통일. round=원장 회차접두(am1/pm1/close1), 빈값이면 전 회차.
function setLedgerDuty(dept, date, gender, round, name) {
  if (!date || !gender || !name) return jsonRes({ ok: false, error: 'date/gender/name required' });
  var props = PropertiesService.getScriptProperties();
  var key = _chkKey(dept, date, gender);
  var led;
  try { led = JSON.parse(props.getProperty(key) || '{}'); } catch (e) { return jsonRes({ ok: false, error: 'ledger parse fail' }); }
  if (!led.cr || typeof led.cr !== 'object') return jsonRes({ ok: true, changed: 0, note: 'no cr ledger', key: key });
  var changed = [], before = [];
  Object.keys(led.cr).forEach(function (k) {
    if (round && String(k).indexOf(round + '_') !== 0) return;   // 지정 회차접두만(빈값=전부)
    var m = led.cr[k];
    if (!m || typeof m !== 'object') return;
    if (String(m.du || '') !== name) { before.push({ k: k, was: String(m.du || '') }); m.du = name; changed.push(k); }
  });
  if (changed.length) props.setProperty(key, JSON.stringify(led));
  return jsonRes({ ok: true, changed: changed.length, keys: changed, before: before, key: key, gender: gender, round: round, name: name });
}

// ─── 제출시각 표시형식 통일 (GET ?action=normalize_subat_format[&dept=support]) — 2026-06-29 시우 ───
// 일부 셀의 제출시각이 '날짜만'(2026. 6. 29)으로 표시돼 시간이 가려지는 문제 정정. 값은 그대로(시간 보유), 표시형식만 'yyyy-MM-dd HH:mm'로 통일. 빈칸·텍스트는 무영향.
function normalizeSubatFormat(dept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tabs = _deptTabs(dept);   // {male,female,common}
  var COL = 10, FMT = 'yyyy-MM-dd HH:mm', out = {};
  Object.keys(tabs).forEach(function (k) {
    var sh = ss.getSheetByName(tabs[k]);
    if (!sh) return;
    var last = sh.getLastRow();
    if (last < 2) { out[tabs[k]] = { rows: 0 }; return; }
    sh.getRange(2, COL, last - 1, 1).setNumberFormat(FMT);
    out[tabs[k]] = { rows: last - 1 };
  });
  // 검증: 남 시트 제출시각 표시값 중 시간(:) 없는 칸 카운트(빈칸 제외) — 0이어야 통과
  var msh = ss.getSheetByName(tabs.male || SHEET_MALE), noTime = 0, sample = [];
  if (msh) {
    var last = msh.getLastRow();
    if (last >= 2) {
      var disp = msh.getRange(2, COL, last - 1, 1).getDisplayValues();
      var ids = msh.getRange(2, 2, last - 1, 1).getValues();
      for (var i = 0; i < disp.length; i++) {
        var d = String(disp[i][0] || '');
        if (d && !/\d{1,2}:\d{2}/.test(d)) { noTime++; if (sample.length < 10) sample.push(String(ids[i][0] || '') + '=' + d); }
      }
    }
  }
  return jsonRes({ ok: true, format: FMT, col: COL, sheets: out, male_noTimeAfter: noTime, male_noTimeSample: sample });
}

// ─── 회차 근무자 통일 보정 (GET ?action=set_round_duty&dept&zone&date=yyyy-MM-dd&round&name) — 2026-06-29 시우 ───
// stale 기본값 오염(아침 미리선택된 근무자로 첫 몇 건이 잘못 기록)을 실제 근무자 1명으로 통일. 11열(근무자)만 변경 — 점검결과·점검자·이슈·시각 전부 보존.
function setRoundDuty(dept, zoneKey, dateStr, round, name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(_deptTabs(dept)[zoneKey]);
  if (!sheet) return jsonRes({ ok: false, error: 'no zone sheet for ' + zoneKey });
  if (!dateStr || !round || !name) return jsonRes({ ok: false, error: 'date/round/name required' });
  var tz = Session.getScriptTimeZone();
  var last = sheet.getLastRow();
  if (last < 2) return jsonRes({ ok: true, changed: 0 });
  var data = sheet.getRange(2, 1, last - 1, HEADERS.length).getValues();
  var changed = [], before = [];
  for (var i = 0; i < data.length; i++) {
    var c = data[i][0];
    var dd = (c instanceof Date) ? c : (c ? new Date(c) : null);
    var ds = (dd && !isNaN(dd.getTime())) ? Utilities.formatDate(dd, tz, 'yyyy-MM-dd') : String(c || '');
    var rd = String(data[i][4] || '');
    if (ds === dateStr && rd === round) {
      if (String(data[i][10] || '') !== name) {
        before.push({ id: String(data[i][1] || ''), was: String(data[i][10] || '') });
        data[i][10] = name;
        changed.push(String(data[i][1] || ''));
      }
    }
  }
  if (changed.length) sheet.getRange(2, 1, data.length, HEADERS.length).setValues(data);
  return jsonRes({ ok: true, changed: changed.length, ids: changed, before: before, zone: zoneKey, date: dateStr, round: round, name: name });
}

// ─── 매뉴얼 항목 중복 정리 (GET ?action=dedup_items[&dept=support]) — 2026-06-29 시우 ───
// '시드' 개념 폐기 잔재 청소: 같은 항목ID가 〈시드 빈칸〉+〈시드='Y'〉 2줄로 증식된 것을 1줄로.
// 안전: ①원본 전체를 백업탭(_매뉴얼백업_dedup)에 적립(역롤백) ②항목ID별 1줄만 보존(시드 빈칸행 우선) ③생존행 시드칸 전부 '' ④멱등(재실행 시 removed 0).
function dedupItems(reqDept) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ ok: false, error: 'no item sheet' });
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return jsonRes({ ok: true, before: 0, after: 0, removed: [] });
  var W = ITEM_HEADERS.length;
  var all = sheet.getRange(2, 1, lastRow - 1, W).getValues();

  // 1) 백업탭 덮어쓰기 — 헤더 + 원본 전체(역롤백 안전망)
  var bkName = '_매뉴얼백업_dedup';
  var bk = ss.getSheetByName(bkName);
  if (!bk) bk = ss.insertSheet(bkName);
  bk.clearContents();
  bk.getRange(1, 1, 1, W).setValues([ITEM_HEADERS]);
  if (all.length > 0) bk.getRange(2, 1, all.length, W).setValues(all);

  // 2) 항목ID별 dedup — 첫 등장행 보존(시드칸 폐지로 우선규칙 불필요). 2026-06-29 시우.
  var order = [], pick = {}, removed = [];
  for (var i = 0; i < all.length; i++) {
    var r = all[i];
    var id = String(r[0] || '').trim();
    if (!id && !String(r[2] || '').trim()) continue;   // 완전 빈 행 스킵
    if (!pick[id]) { pick[id] = r; order.push(id); }
    else removed.push(id);
  }

  // 3) 생존행 재기록(11칸 정합)
  var out = order.map(function (id) {
    var r = pick[id].slice(0, W);
    while (r.length < W) r.push('');
    return r;
  });
  sheet.getRange(2, 1, lastRow - 1, W).clearContent();
  if (out.length > 0) sheet.getRange(2, 1, out.length, W).setValues(out);

  return jsonRes({ ok: true, before: all.length, after: out.length, removedCount: removed.length, removed: removed, backupTab: bkName, dept: reqDept });
}

// ─── 시드 단방향 동기화 (POST {action:'syncSeedItems', dept, seeds:[...]}) — Part1 시우 2026-06-23 ───
// 페이지가 전체 시드 명단(WEEKDAY/WEEKEND/NIGHT_* + ROUND_MAP 회차)을 단방향 push.
// seed='Y' 격리행만 멱등 upsert(항목ID 키): 있으면 update·없으면 append·payload에 없는 옛 seed행 삭제.
// → N회 호출해도 seed행 = payload와 1:1(중복 0). shadow/added/타 dept 행은 절대 안 건드림.
// Part1 단계: getItems·_countTodaySchedule이 seed행 skip → 적재만 하고 분모·렌더 무변화.
function syncSeedItems(body) {
  // 2026-06-27 시드 개념 폐기 — 시트=항목 마스터 단일출처. 하드코딩 배열 되쓰기 차단(GM 삭제분 부활 방지).
  return jsonRes({ ok: true, deprecated: true, note: 'seed 폐기 — 시트 단일출처(되쓰기 no-op)' });
  // (이하 레거시 — 도달 불가)
  var reqDept = body.dept ? String(body.dept).trim() : 'support';
  var seeds = body.seeds || [];
  var sheet = initItemSheet();

  // 1) payload → seed 행(부서·시드='Y' 박제). 항목ID 기준 dedup(중복 id는 마지막 승).
  var seedMap = {};   // id → row
  var seedOrder = [];
  for (var s = 0; s < seeds.length; s++) {
    var it = seeds[s] || {};
    var sid = String(it.id || '').trim();
    if (!sid) continue;
    if (!seedMap[sid]) seedOrder.push(sid);
    seedMap[sid] = [
      sid,
      String(it.cat || ''),
      String(it.name || ''),
      String(it.detail || ''),
      String(it.gender || 'all'),
      String(it.slot || ''),
      (it.order !== undefined && it.order !== '') ? it.order : (seedOrder.length),
      String(it.type || '').trim() || 'check',
      String(it.fields || ''),
      reqDept,
      String(it.rounds || ''),
      String(it.sched || ''),
      'Y'   // 시드 격리 플래그
    ];
  }

  // 2) 기존 시트 전 행 분류: non-seed(타·shadow·added=불변 보존) + 기존 seed 행 위치 맵.
  var lastRow = sheet.getLastRow();
  var preserved = [];        // seed 아닌 모든 행 그대로 보존
  if (lastRow > 1) {
    var existing = sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).getValues();
    for (var e = 0; e < existing.length; e++) {
      var r = existing[e];
      if (!r[0] && !r[2]) continue;   // 빈 행 스킵
      if (!_isSeedRow(r)) preserved.push(r);   // 시드 아닌 행만 보존(시드행은 payload로 전량 교체)
    }
  }

  // 3) 멱등 교체: [보존 non-seed] + [payload seed행 1:1]. payload에 없는 옛 seed행은 자동 소멸(누락=삭제).
  var seedRows = seedOrder.map(function (id) { return seedMap[id]; });
  if (lastRow > 1) {
    sheet.getRange(2, 1, lastRow - 1, ITEM_HEADERS.length).clearContent();
  }
  var rows = preserved.concat(seedRows);
  if (rows.length > 0) {
    sheet.getRange(2, 1, rows.length, ITEM_HEADERS.length).setValues(rows);
  }
  return jsonRes({ ok: true, seedCount: seedRows.length, preserved: preserved.length, total: rows.length, dept: reqDept });
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
  // 2b-1: 회차(11열) 빈값 — 기본 항목은 프론트 ROUND_MAP/roundOfSlot이 라운드 결정(시드 불필요).
  ZONE_ITEMS.forEach(function (it) {
    rows.push([it.id, it.cat, it.name, '', 'all', order++, 'check', '', 'support', '', '', '']);
  });
  // 공용 구역 항목
  COMMON_ITEMS.forEach(function (it) {
    rows.push([it.id, it.cat, it.name, '', 'all', order++, 'check', '', 'support', '', '', '']);
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
  support:  { male: SHEET_MALE,            female: SHEET_FEMALE,            common: null },
  // 시설부는 공용 단일 탭(남/여는 측정칸으로 구분 — saveFacilityMeasure가 시설_공용구역만 기록). male/female=null로 빈탭 재생성 차단(2026-06-20 시우).
  facility: { male: null,                  female: null,                    common: SHEET_FACILITY_COMMON },
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
  [t.male, t.female, t.common].filter(function(n){return !!n;}).forEach(function (name) {
    var existed = !!ss.getSheetByName(name);
    _createCheckSheet(ss, name);   // 13열 HEADERS(측정값 포함) 헤더 기록
    created.push((existed ? '재생성:' : '신규:') + name);
  });
  // 오늘 날짜 빈 데이터 시드 — support만(ZONE/COMMON=지원부 청소 항목 모델).
  // facility 등은 측정폼(saveFacilityMeasure, 항목×회차)이 데이터 단일 원천이라 시드 금지
  // (시드하면 지원부 항목이 시설 분모를 오염시키고 회차 라벨도 불일치). 헤더만 생성.
  var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  var seededDate = null;
  if (dept === 'support') {
    if (t.male)   _seedDate(ss.getSheetByName(t.male),   today, ZONE_ITEMS,   t.male);
    if (t.female) _seedDate(ss.getSheetByName(t.female), today, ZONE_ITEMS,   t.female);
    if (t.common) _seedDate(ss.getSheetByName(t.common), today, COMMON_ITEMS, t.common);
    seededDate = today;
  }
  return jsonRes({ ok: true, dept: dept, created: created, seededDate: seededDate, note: (dept === 'support' ? '시드 완료' : '헤더만 생성(측정폼이 데이터 원천 — 시드 없음)') });
}

// ════════════════════════════════════════════
// 시설부 측정 항목 마스터 (작업일지 PDF 근거 · 2026-06-17 시우)
// 완료율 분모 = 이 항목 수. 분자 = 측정값이 입력된 항목 수(입력률).
// 측정형(지어내기 금지·L05): 항목명·기준값은 작업일지260604/260601 PDF 실측.
// ai:true 4건 = 작업일지 미기재 'AI초안(GM검토)' — 프론트 배지로 구분 노출, 분모 동일 포함.
// id는 시설_공용구역 시트행 itemId로 그대로 저장(weekly measure 수집 키).
// ════════════════════════════════════════════
var FACILITY_ITEMS = [
  // 2-A 시간대별 측정 (사우나 — 탕별 남/여, 찜질방 A/B는 측정 컬럼으로 분리)
  { id:'fc_sauna_ontang',  name:'사우나 온탕 온도(남/여, 기준39℃)',  cat:'A 사우나 측정',   unit:'℃',    ai:false },
  { id:'fc_sauna_yeoltang',name:'사우나 열탕 온도(남/여, 기준42℃)',  cat:'A 사우나 측정',   unit:'℃',    ai:false },
  { id:'fc_sauna_dry',     name:'사우나 건식 온도(남/여, 기준78℃)',  cat:'A 사우나 측정',   unit:'℃',    ai:false },
  { id:'fc_sauna_wet',     name:'사우나 습식 온도(남/여, 기준48℃)',  cat:'A 사우나 측정',   unit:'℃',    ai:false },
  { id:'fc_sauna_jjim',    name:'찜질방 온도(A/B, 기준68℃)',         cat:'A 사우나 측정',   unit:'℃',    ai:false },
  { id:'fc_pool_ph',       name:'수영장 pH농도',                     cat:'B 수영장 수질',   unit:'pH',   ai:false },
  { id:'fc_pool_temp',     name:'수영장 수온',                       cat:'B 수영장 수질',   unit:'℃',    ai:false },
  { id:'fc_pool_cl',       name:'수영장 CL농도(잔류염소)',           cat:'B 수영장 수질',   unit:'ppm',  ai:false },
  { id:'fc_tank_k2',       name:'온수탱크 2번 온도',                 cat:'C 온수탱크',      unit:'℃',    ai:false },
  { id:'fc_tank_k3',       name:'온수탱크 3번 온도',                 cat:'C 온수탱크',      unit:'℃',    ai:false },
  { id:'fc_tank_k4',       name:'온수탱크 4번 온도',                 cat:'C 온수탱크',      unit:'℃',    ai:false },
  { id:'fc_ahu_AHU1',      name:'공조기 AHU1 가동상태',              cat:'D 공조기',        unit:'ok/x', ai:false },
  { id:'fc_ahu_AHU2',      name:'공조기 AHU2 가동상태',              cat:'D 공조기',        unit:'ok/x', ai:false },
  { id:'fc_ahu_AHU3',      name:'공조기 AHU3 가동상태',              cat:'D 공조기',        unit:'ok/x', ai:false },
  { id:'fc_ahu_AHU4',      name:'공조기 AHU4 가동상태',              cat:'D 공조기',        unit:'ok/x', ai:false },
  // 2-B 1일 1회 설비 점검 (기계실)
  { id:'fc_eq_night',      name:'심야전기(05:00)',                   cat:'E 기계실 가동값', unit:'A',    ai:false },
  { id:'fc_eq_tank1',      name:'1번 탱크온도(05:00)',               cat:'E 기계실 가동값', unit:'℃',    ai:false },
  { id:'fc_eq_gas',        name:'가스검침(06:00)',                   cat:'E 기계실 가동값', unit:'㎥',   ai:false },
  { id:'fc_eq_hotw',       name:'고온수기(05:00)',                   cat:'E 기계실 가동값', unit:'ok/x', ai:false },
  { id:'fc_eq_pump',       name:'연동펌프(05:00)',                   cat:'E 기계실 가동값', unit:'ok/x', ai:false },
  { id:'fc_eq_heat',       name:'축열조(14:00)',                     cat:'E 기계실 가동값', unit:'',     ai:false },
  { id:'fc_eq_final',      name:'최종퇴실(시각/성명)',               cat:'E 기계실 가동값', unit:'',     ai:false },
  // 2-D AI초안(GM 검토) — 작업일지 미기재, 시설 매뉴얼상 권장 (배지 구분)
  { id:'fc_ai_fire',       name:'소방시설 일일 작동점검',            cat:'F 안전(AI초안)',  unit:'ok/x', ai:true },
  { id:'fc_ai_elev',       name:'엘리베이터·에스컬레이터 가동확인',  cat:'F 안전(AI초안)',  unit:'ok/x', ai:true },
  { id:'fc_ai_water',      name:'정수기·비품 점검',                  cat:'F 안전(AI초안)',  unit:'ok/x', ai:true },
  { id:'fc_ai_alarm',      name:'측정 기준범위 이탈 경보 확인',      cat:'F 안전(AI초안)',  unit:'ok/x', ai:true }
];

// ─── 시설 측정값 저장 (POST {action:'save_facility_measure', date, round, inspector, items:[{id,name,cat,measure,done}]}) ───
// 시설_공용구역 시트에 해당 (날짜,회차) 행을 측정 항목 단위로 교체 기록. col5(점검결과)='완료'면 입력완료, col12=측정값.
// col4=회차 라벨(예 '07시'·'1일'). round 미지정 시 '측정'(하위호환 — 기존 단일스냅샷 동작).
// weekly&dept=facility가 col5/col12를 읽어 입력률 완료율 + measure 배열을 자동 집계(행 단위 카운트 → 회차별 행이 늘면 자동 합산, 서버 추가 집계 불필요).
// ⚠ facility 전용 탭(시설_공용구역)만 기록 — 지원부 코드 경로·시트 일절 미접촉(무회귀 0).
function saveFacilityMeasure(body) {
  var date = String(body.date || '').trim();
  if (!date) return jsonRes({ ok: false, error: 'date 필수' });
  var round = String(body.round || '').trim() || '측정';   // 회차 라벨(없으면 '측정' = 기존 단일스냅샷 하위호환)
  var inspector = String(body.inspector || '박호균').trim() || '박호균';
  var items = body.items || [];
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var name = SHEET_FACILITY_COMMON;   // 시설_공용구역(단일 점검탭 — 남/여는 측정컬럼으로 구분, §2-E)
  var sheet = ss.getSheetByName(name);
  if (!sheet) { _createCheckSheet(ss, name); sheet = ss.getSheetByName(name); }
  _ensureHeaders(sheet);

  // 1) 이 (날짜,회차) 기존 행만 제거(같은 회차 재제출 = 재진술, 중복 누적 방지). 다른 회차 행은 보존.
  var data = sheet.getDataRange().getValues();
  for (var i = data.length - 1; i >= 1; i--) {
    var sameDate = (String(data[i][0]) === date || formatDate(data[i][0]) === date);
    var sameRound = (String(data[i][4]) === round);
    if (sameDate && sameRound) {
      try { sheet.deleteRow(i + 1); }
      catch (e) { var _cc = Math.max(HEADERS.length, sheet.getLastColumn()); sheet.getRange(i + 1, 1, 1, _cc).clearContent(); }
    }
  }

  // 2) 측정 항목 단위로 14열 행 구성 — 측정값 있으면 '완료'(입력완료), 없으면 '미완료'. col4=회차 라벨.
  var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
  var rows = items.map(function (it) {
    var measure = _measureStr(it.measure);
    var done = (it.done === true || it.done === 1 || (measure !== ''));
    return [
      date, String(it.id || ''), String(it.name || ''), String(it.cat || ''), round,
      done ? '완료' : '미완료', '', '',
      done ? '제출완료' : '미제출', done ? now : '',
      inspector, inspector,
      measure, '', done ? now : ''
    ];   // 15열(HEADERS와 일치): …측정값·반영완료·점검시각. 점검시각=입력시각(done일 때).
  });
  if (rows.length) {
    var startRow = sheet.getLastRow() + 1;
    sheet.getRange(startRow, 1, rows.length, HEADERS.length).setValues(rows);
  }
  var doneCnt = 0; rows.forEach(function (r) { if (r[5] === '완료') doneCnt++; });
  return jsonRes({ ok: true, dept: 'facility', date: date, round: round, total: rows.length, done: doneCnt, pct: rows.length ? Math.round(doneCnt / rows.length * 100) : 0 });
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

// 교대 라벨 정규화(2026-06-11 시우): 스냅샷 '교대' 열은 코드('am'/'pm'/'night')와
// 한글 라벨('오전조[1]…','오후조…','야간…','마감…')이 섞여 들어옴(라운드 vs 제출 경로 상이).
// 완료율 일·주 집계에서 같은 (구역,교대) 셀의 중복 라운드 행을 한 셀로 묶기 위한 버킷 키.
function _shiftBucket(s) {
  var v = String(s == null ? '' : s).trim();
  if (v.indexOf('야간') === 0 || v.indexOf('탕청소') === 0 || v === 'night') return 'night';
  if (v.indexOf('오전') === 0 || v === 'am') return 'am';
  // 마감조는 오후조와 별도 회차 — 같은 zone|pm 키 충돌로 한 회차 누락되던 버그 수정(2026-06-16).
  if (v.indexOf('마감') === 0 || v.indexOf('close') >= 0) return 'close';
  // 오후/all/그 외 → pm 버킷
  return 'pm';
}

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
  var dayset = {};
  days.forEach(function (dt) { dayset[dt] = true; });

  // ─── 1차 출처: 점검일지_<dept> 스냅샷(요약 1행/라운드)에서 일별 total/done 집계 ───
  // 같은 날짜의 (구역 zone × 교대버킷) 셀별로 '최신 제출시각' 행만 채택(라운드 재제출=재진술이라
  // 합산 시 중복카운트 위험) → 셀별 done/total을 날짜 단위로 Σ. 항목별 시트 col5 비의존.
  // 셀 키: zone(m/f/all) + '|' + bucket(am/pm/night).
  var snapByDate = {};   // { date: { cellKey: {total,done,at} } }
  var snapSheet = ss.getSheetByName(_snapshotTabName(dept));
  if (snapSheet) {
    var sdata = snapSheet.getDataRange().getValues();
    // 열: 0=제출시각,1=날짜,3=구역,4=교대,6=총항목,7=완료,8=완료율
    for (var r = 1; r < sdata.length; r++) {
      var sd = formatDate(sdata[r][1]);
      if (!dayset[sd]) continue;
      var zone = String(sdata[r][3] || '');
      var bucket = _shiftBucket(sdata[r][4]);
      var tot = Number(sdata[r][6]); if (isNaN(tot)) tot = 0;
      var don = Number(sdata[r][7]); if (isNaN(don)) don = 0;
      var at = String(sdata[r][0] || '');
      var cellKey = zone + '|' + bucket;
      if (!snapByDate[sd]) snapByDate[sd] = {};
      var cell = snapByDate[sd][cellKey];
      if (!cell || at >= cell.at) {   // 최신(또는 동률 시 후순위) 행 채택
        snapByDate[sd][cellKey] = { total: tot, done: don, at: at };
      }
    }
  }

  // ─── 폴백 출처: 스냅샷 없는 날짜만 항목별 시트 col5 카운트(레거시/기능 이전 일자) ───
  // 측정값(measure)은 항목별 시트에만 있으므로 전체 일자에 대해 함께 수집(완료율과 무관).
  var legacyByDate = {};
  days.forEach(function (dt) { legacyByDate[dt] = { total: 0, done: 0, measure: [] }; });
  sheetNames.forEach(function (name) {
    var sheet = ss.getSheetByName(name);
    if (!sheet) return;
    var data = sheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      var rowDate = formatDate(data[i][0]);
      if (!legacyByDate[rowDate]) continue;
      legacyByDate[rowDate].total++;
      if (String(data[i][5]) === '완료') legacyByDate[rowDate].done++;
      var mv = String(data[i][12] || '');
      if (mv) legacyByDate[rowDate].measure.push({ itemId: String(data[i][1]), name: String(data[i][2]), measure: mv });
    }
  });

  // 날짜 오름차순으로 결과 배열 구성 (차트 표시용)
  var result = days.slice().reverse().map(function (dt) {
    var cells = snapByDate[dt];
    var total = 0, done = 0, src = 'snapshot';
    if (cells) {
      Object.keys(cells).forEach(function (k) { total += cells[k].total; done += cells[k].done; });
    }
    // 스냅샷 셀이 없으면 폴백(항목별 시트 col5). 둘 다 0이면 데이터 없음(total=0 → pct=0).
    if (total === 0) {
      var lg = legacyByDate[dt];
      total = lg.total; done = lg.done; src = 'sheet';
    }
    var pct = total > 0 ? Math.round(done / total * 100) : 0;
    return { date: dt, total: total, done: done, pct: pct, src: src, measure: legacyByDate[dt].measure };
  });

  return jsonRes({ ok: true, dept: dept, data: result });
}

// ════════════════════════════════════════════
// action=monthly_report — 지원부 점검 월간 리포트 집계 (배208 1단계, 2026-07-03 시우)
// GET ?action=monthly_report&dept=support&month=YYYY-MM (month 생략 시 이번달)
// IO(handleMonthlyReport)/순수집계(_aggregateMonthly) 분리 — 후자는 SpreadsheetApp 무의존(Node 단위테스트 가능).
// 완료율=denomNote 월별 분기(배14 2026-07-03 분모 시트 단일화 기준) — 7월+ 확정, 6월 이전 참고값. 배208 후속.
// ════════════════════════════════════════════

// 날짜값(Date객체 또는 'YYYY-MM-DD'·'YYYY. M. D' 등 문자열)에서 {y,m,d} 추출. 실패 시 null.
function _parseDateParts_(v) {
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return null;
    return { y: v.getFullYear(), m: v.getMonth() + 1, d: v.getDate() };
  }
  var s = String(v == null ? '' : v).trim();
  if (!s) return null;
  var m = s.match(/(\d{4})\s*[.\-\/]\s*(\d{1,2})(?:\s*[.\-\/]\s*(\d{1,2}))?/);
  if (!m) return null;
  return { y: Number(m[1]), m: Number(m[2]), d: m[3] ? Number(m[3]) : 1 };
}
function _pad2_(n) { return n < 10 ? '0' + n : '' + n; }
// 'YYYY-MM' 추출
function _ymOf_(v) {
  var p = _parseDateParts_(v);
  return p ? (p.y + '-' + _pad2_(p.m)) : '';
}
// 'YYYY-MM-DD' 추출(일자 미상 시 01일 보정)
function _ymdOf_(v) {
  var p = _parseDateParts_(v);
  return p ? (p.y + '-' + _pad2_(p.m) + '-' + _pad2_(p.d)) : '';
}
function _isTestVal_(v) {
  return /test|테스트/i.test(String(v == null ? '' : v));
}

// 순수 집계 함수 — SpreadsheetApp 무호출. snapRows/issueRows = 헤더 제외 2차원 배열(원본 셀값 그대로).
// snapRows 열: 0제출시각 1날짜 2부서 3구역 4교대 5점검자 6총항목 7완료 8완료율 9이슈건수 10이슈내용 11점검시작 12점검완료 13소요(분)
// issueRows 열: 0등록일 1구역 2점검자 3이슈내용 4상태 5처리일 6비고
// (배208-2A, 2026-07-03) 지원_이슈대장이 빈 시트라 issueRows는 더 이상 이슈 집계에 쓰지 않는다.
// 시그니처는 하위호환 위해 유지하되 미사용 — 이슈는 전부 snapshot 9열(이슈건수)·10열(이슈내용 원문)에서 집계한다.
// scheduleTotals(옵션, 2026-07-04 배173+배14): { 'YYYY-MM-DD': number } — today_live와 동일 기준(주말 pm 제외)
// 스케줄 기대 분모 맵(IO인 handleMonthlyReport가 _scheduleExpectedTotal로 만들어 넘김). 순수함수 유지를 위해
// SpreadsheetApp을 직접 안 부르고 완성된 데이터만 받는다 — 없으면(구버전 호출·facility 등) 기존 방식 그대로 폴백.
function _aggregateMonthly(snapRows, issueRows, month, scheduleTotals) {
  snapRows = snapRows || [];
  issueRows = issueRows || []; // 하위호환 유지용(미사용) — 배208-2A
  scheduleTotals = scheduleTotals || null;
  var testExcludedCount = 0;

  // 1) Test 행 제외 + 2) 월 필터
  var filtered = [];
  snapRows.forEach(function (row) {
    var inspector = row[5], zone = row[3];
    if (_isTestVal_(inspector) || _isTestVal_(zone)) { testExcludedCount++; return; }
    var ym = _ymOf_(row[1]);
    if (ym !== month) return;
    filtered.push(row);
  });

  // 3) Dedup: (날짜,구역,교대버킷) 키 → 최신 제출시각 1건만(handleWeekly 패턴 참고: at 문자열 비교로 최신 채택)
  var dedupMap = {};
  filtered.forEach(function (row) {
    var ymd = _ymdOf_(row[1]);
    var zone = String(row[3] == null ? '' : row[3]);
    var bucket = _shiftBucket(row[4]);
    var key = ymd + '|' + zone + '|' + bucket;
    var at = String(row[0] == null ? '' : row[0]);
    var cell = dedupMap[key];
    if (!cell || at >= cell.at) {
      dedupMap[key] = { row: row, at: at, ymd: ymd, zone: zone, bucket: bucket };
    }
  });
  var sessions = Object.keys(dedupMap).map(function (k) { return dedupMap[k]; });

  // 4) 집계
  var byDate = {};          // ymd -> {sumTotal,sumDone,sessionCount,issueCount}
  var byZoneMap = {};       // zone -> {...}
  var byShiftMap = {};      // bucket -> {...}
  var byInspectorMap = {};  // inspector -> {sessionCount,pctSum}
  var zoneShiftTotals = {}; // zone|bucket -> {total:true,...} — denomInconsistent 판정용
  var denomInconsistent = false;
  var issueList = [];       // snapshot 10열(이슈내용) 원문 목록 — 배208-2A

  sessions.forEach(function (s) {
    var row = s.row;
    var total = Number(row[6]); if (isNaN(total)) total = 0;
    var done = Number(row[7]); if (isNaN(done)) done = 0;
    var issueCnt = Number(row[9]); if (isNaN(issueCnt)) issueCnt = 0;
    var inspector = String(row[5] == null ? '' : row[5]).trim() || '(미기재)';

    if (!byDate[s.ymd]) byDate[s.ymd] = { sumTotal: 0, sumDone: 0, sessionCount: 0, issueCount: 0 };
    byDate[s.ymd].sumTotal += total; byDate[s.ymd].sumDone += done;
    byDate[s.ymd].sessionCount++; byDate[s.ymd].issueCount += issueCnt;

    if (!byZoneMap[s.zone]) byZoneMap[s.zone] = { zone: s.zone, sessionCount: 0, sumTotal: 0, sumDone: 0, issueCount: 0 };
    byZoneMap[s.zone].sessionCount++; byZoneMap[s.zone].sumTotal += total;
    byZoneMap[s.zone].sumDone += done; byZoneMap[s.zone].issueCount += issueCnt;

    if (!byShiftMap[s.bucket]) byShiftMap[s.bucket] = { shift: s.bucket, sessionCount: 0, sumTotal: 0, sumDone: 0 };
    byShiftMap[s.bucket].sessionCount++; byShiftMap[s.bucket].sumTotal += total; byShiftMap[s.bucket].sumDone += done;

    if (!byInspectorMap[inspector]) byInspectorMap[inspector] = { inspector: inspector, sessionCount: 0, pctSum: 0 };
    byInspectorMap[inspector].sessionCount++;
    byInspectorMap[inspector].pctSum += (total > 0 ? (done / total * 100) : 0);

    var zsKey = s.zone + '|' + s.bucket;
    if (!zoneShiftTotals[zsKey]) zoneShiftTotals[zsKey] = {};
    zoneShiftTotals[zsKey][total] = true;

    var issueText = String(row[10] == null ? '' : row[10]).trim();
    if (issueText) {
      issueList.push({ date: s.ymd, zone: s.zone, shift: s.bucket, inspector: inspector, text: issueText });
    }
  });
  issueList.sort(function (a, b) { return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0); });

  Object.keys(zoneShiftTotals).forEach(function (k) {
    if (Object.keys(zoneShiftTotals[k]).length > 1) denomInconsistent = true;
  });

  // [배14+배173, 2026-07-04] 분모 단일화: scheduleTotals(today_live와 동일 스케줄 기대치, 주말 pm 제외)가
  // 있으면 세션기록 합계(c.sumTotal) 대신 그 값을 분모로 쓴다. 진행중인 날(아직 일부 회차 미제출)이 "제출된
  // 것만 분모"라 100%로 뜨던 버그 제거 — 완결된 과거일은 세션기록 합계 = 스케줄 합계라 값이 그대로 유지된다.
  // scheduleTotals에 해당 날짜가 없으면(구버전 호출·facility 등) 기존 방식(세션기록 합계) 그대로 폴백 — 하위호환.
  var dailySeries = Object.keys(byDate).sort().map(function (d) {
    var c = byDate[d];
    var total = c.sumTotal, done = c.sumDone;
    if (scheduleTotals && Object.prototype.hasOwnProperty.call(scheduleTotals, d) && typeof scheduleTotals[d] === 'number') {
      total = scheduleTotals[d];
      if (done > total) done = total;   // 안전장치: today_live 클램프와 동일 원칙(분모 불변, 분자만 상한)
    }
    return {
      date: d, sumTotal: total, sumDone: done,
      pct: total > 0 ? Math.round(done / total * 100) : null,
      sessionCount: c.sessionCount, issueCount: c.issueCount
    };
  });

  // [배208-3, 2026-07-04] top-level avgPct/issueCount 안정화: dailySeries 값에서 항상 재집계하되
  // Number() 방어로 undefined/NaN 오염이 조용히 top-level만 null로 만드는 경우를 차단.
  var monthSumTotal = 0, monthSumDone = 0, monthIssueCount = 0;
  dailySeries.forEach(function (d) {
    monthSumTotal   += Number(d.sumTotal) || 0;
    monthSumDone    += Number(d.sumDone) || 0;
    monthIssueCount += Number(d.issueCount) || 0;
  });

  // avgPct 정의(scheduleTotals 제공 시): 분모=이번달 활성일들의 스케줄 기대치 합(주말 pm 제외) — 진행중인
  // 당일도 포함된다("당일 전체 예정 대비 지금까지 완료"). 당일이 아직 안 끝났으면 낮게 나오는 게 정상(왜곡 아님).
  // sessionCount·activeDays=0이면(이번달 아직 데이터 없음) avgPct=null 그대로(진짜 무데이터 — 지어내지 않음).
  var monthTotals = {
    sumTotal: monthSumTotal, sumDone: monthSumDone,
    avgPct: monthSumTotal > 0 ? Math.round(monthSumDone / monthSumTotal * 100) : null,
    sessionCount: sessions.length,
    activeDays: dailySeries.length,
    issueCount: monthIssueCount
  };

  var byZone = Object.keys(byZoneMap).map(function (z) {
    var c = byZoneMap[z];
    return {
      zone: c.zone, sessionCount: c.sessionCount, sumTotal: c.sumTotal, sumDone: c.sumDone,
      pct: c.sumTotal > 0 ? Math.round(c.sumDone / c.sumTotal * 100) : null, issueCount: c.issueCount
    };
  }).sort(function (a, b) { return b.sessionCount - a.sessionCount; });

  var byShift = Object.keys(byShiftMap).map(function (s) {
    var c = byShiftMap[s];
    return {
      shift: c.shift, sessionCount: c.sessionCount, sumTotal: c.sumTotal, sumDone: c.sumDone,
      pct: c.sumTotal > 0 ? Math.round(c.sumDone / c.sumTotal * 100) : null
    };
  });

  var byInspector = Object.keys(byInspectorMap).map(function (i) {
    var c = byInspectorMap[i];
    return { inspector: c.inspector, sessionCount: c.sessionCount, avgPct: c.sessionCount > 0 ? Math.round(c.pctSum / c.sessionCount) : null };
  }).sort(function (a, b) { return b.sessionCount - a.sessionCount; });

  // 이슈 집계 — 배208-2A: 지원_이슈대장(빈 시트) 폐기 → snapshot 9열(이슈건수)·10열(이슈내용 원문) 기준.
  // total/byZone은 위에서 이미 dedup·월필터·test제외까지 끝난 sessions 집계(byDate/byZoneMap)를 그대로 재사용.
  var issueByZone = Object.keys(byZoneMap).map(function (z) {
    return { zone: byZoneMap[z].zone, count: byZoneMap[z].issueCount };
  }).sort(function (a, b) { return b.count - a.count; });

  // 개선시사 자동 문구 — 규칙기반(집계값에서 파생, 지어내기 금지). 완료율은 잠정(denomNote 맥락 유지).
  var improvements = [];
  var zonesWithPct = byZone.filter(function (z) { return z.pct !== null && z.sessionCount > 0; });
  if (zonesWithPct.length > 0) {
    var worstZone = zonesWithPct.reduce(function (a, b) { return b.pct < a.pct ? b : a; });
    improvements.push(worstZone.zone + ' 구역 완료율 최저(' + worstZone.pct + '%) — 집중 필요');
  }
  if (dailySeries.length > 0) {
    var maxIssueDay = dailySeries.reduce(function (a, b) { return b.issueCount > a.issueCount ? b : a; });
    if (maxIssueDay.issueCount > 0) {
      var dp = maxIssueDay.date.split('-');
      improvements.push(Number(dp[1]) + '월 ' + Number(dp[2]) + '일 이슈 최다(' + maxIssueDay.issueCount + '건)');
    }
    var lowPctDays = dailySeries.filter(function (d) { return d.pct !== null && d.pct < 70; });
    if (lowPctDays.length > 0) {
      improvements.push('완료율 70% 미만 ' + lowPctDays.length + '일 — 원인 점검');
    }
  }
  if (sessions.length < 5) {
    improvements.push('표본 부족 — 추세 판단 유보');
  }

  // denomNote — 배14(2026-07-03) 분모 시트 단일화 반영: 대상월이 그 이전이면 참고값, 이후면 확정. 배208 후속(2026-07-03 시우).
  var denomNote = (month >= '2026-07')
    ? '완료율=확정(분모 시트 단일화 반영, 배14)'
    : '완료율=참고값(2026-07-03 분모 통일 이전 데이터·집계기준 상이)';

  return {
    ok: true,
    dept: null,   // handleMonthlyReport(IO)에서 채움
    month: month,
    testExcludedCount: testExcludedCount,
    dailySeries: dailySeries,
    monthTotals: monthTotals,
    byZone: byZone,
    byShift: byShift,
    byInspector: byInspector,
    // total=이슈건수(9열) 누적, sessionsWithIssue=이슈내용(10열) 비지 않은 세션 수 — '건수' 오해 방지(배208 후속). 2026-07-03 시우.
    issues: { total: monthTotals.issueCount, sessionsWithIssue: issueList.length, byZone: issueByZone, list: issueList, byStatus: {} },
    improvements: improvements,
    denomNote: denomNote,
    denomInconsistent: denomInconsistent
  };
}

// ════════════════════════════════════════════
// action=monthly_report&dept=facility — 시설부 점검 월간 리포트 집계 (배406, 2026-07-04 시우)
// 지원부(배208)와 데이터 구조가 근본적으로 다름 — 지원부=구역×교대 완료율 스냅샷(점검일지_support),
// 시설부=항목×회차 실측정값(시설_공용구역, FACILITY_ITEMS 25종·saveFacilityMeasure 저장).
// 완료율식 이식 불가 전제 확인(탐색 결과, 2026-07-04): 시설부는 스냅샷 탭 자체가 없음(제출 UI가
// save_facility_measure만 호출·snapshot_append 미호출) → support처럼 zone/shift가 아니라
// cat(카테고리 A~F)·round(회차 자유텍스트)·item 단위로 별도 설계.
// 이슈: 시설_공용구역 6열(이슈) 헤더는 있으나 saveFacilityMeasure가 항상 ''로 저장 —
// fcheck 화면에 이슈 등록 UI가 없어 실제로 채워지지 않음(정직 확인, ❌ 미측정).
// 대신 프론트 FC_RANGES(시설부 체계.html, GM·박호균 조정 기준값)를 서버에 1:1 미러해
// 측정값 기준이탈을 실측 기반으로 집계(지어낸 기준 아님 — 이미 라이브 UI가 쓰는 값 그대로).
// ════════════════════════════════════════════

// 프론트 FC_RANGES(시설부 체계.html) 1:1 미러 — 값 변경 시 양쪽 동시 수정 필수.
// 온수탱크(k2/k3/k4)·공조기(AHU ok/x)·안전점검(AI초안 4종)은 프론트에서도 기준 미설정 → 여기도 미포함(❌ 미측정, 지어내기 금지).
var FC_MEASURE_RANGES = {
  fc_sauna_ontang_a: { min: 36, max: 42 }, fc_sauna_ontang_b: { min: 36, max: 42 },
  fc_sauna_yeoltang_a: { min: 39, max: 45 }, fc_sauna_yeoltang_b: { min: 39, max: 45 },
  fc_sauna_dry_a: { min: 75, max: 81 }, fc_sauna_dry_b: { min: 75, max: 81 },
  fc_sauna_wet_a: { min: 45, max: 51 }, fc_sauna_wet_b: { min: 45, max: 51 },
  fc_sauna_jjim_a: { min: 65, max: 71 }, fc_sauna_jjim_b: { min: 65, max: 71 },
  fc_pool_ph: { min: 7.0, max: 7.8 },
  fc_pool_temp: { min: 26, max: 30 },
  fc_pool_cl: { min: 0.4, max: 1.0 }
};
// measure(13열) JSON 문자열({"sauna_ontang_a":"39.5",...}) → 필드id 복원('fc_'+key) 후 범위 판정.
// 파싱 실패·기준 미설정 필드는 조용히 스킵(경보 아님) — 순수함수(SpreadsheetApp 무의존, Node 단위테스트 가능).
function _facilityRangeHits(measureStr) {
  var hits = [];
  if (!measureStr) return hits;
  var obj = null;
  try { obj = JSON.parse(measureStr); } catch (e) { return hits; }
  if (!obj || typeof obj !== 'object') return hits;
  Object.keys(obj).forEach(function (k) {
    var cfg = FC_MEASURE_RANGES['fc_' + k];
    if (!cfg) return;
    var num = parseFloat(obj[k]);
    if (isNaN(num)) return;
    if (num < cfg.min || num > cfg.max) hits.push({ field: k, value: num, min: cfg.min, max: cfg.max });
  });
  return hits;
}

// 순수 집계 함수 — SpreadsheetApp 무호출. rows = 시설_공용구역 헤더 제외 2차원 배열(원본 셀값).
// 열(HEADERS 정본): 0날짜 1항목ID 2항목명 3카테고리 4회차 5점검결과 6이슈(항상'') 7노하우
//                   8제출상태 9제출시각 10근무자 11점검자 12측정값 13반영완료(항상'') 14소요시간(주의: 실제론 점검시각 재기록 — 진짜 소요분 아님, 미사용)
// 세션 = (날짜,회차) 1건 = save_facility_measure 1회 제출(회차 전체 항목을 통째 교체 기록).
function _aggregateMonthlyFacility(rows, month) {
  rows = rows || [];
  var testExcludedCount = 0;

  var filtered = [];
  rows.forEach(function (row) {
    var inspector = row[11];
    if (_isTestVal_(inspector)) { testExcludedCount++; return; }
    var ym = _ymOf_(row[0]);
    if (ym !== month) return;
    filtered.push(row);
  });

  var byDate = {};        // ymd -> {total,done,roundSet:{}}
  var byCatMap = {};       // cat -> {cat,total,done}
  var byRoundMap = {};     // round -> {round,total,done,daySet:{}}
  var byInspectorMap = {}; // inspector -> {inspector,total,done,sessionSet:{}}
  var sessionSet = {};     // 'ymd|round' -> true (월 전체 세션 수)
  var outOfRangeList = [];
  var outOfRangeByItem = {}; // itemId -> {itemId,name,count}

  filtered.forEach(function (row) {
    var ymd = _ymdOf_(row[0]);
    var itemId = String(row[1] == null ? '' : row[1]);
    var itemName = String(row[2] == null ? '' : row[2]);
    var cat = String(row[3] == null ? '' : row[3]).trim() || '(미분류)';
    var round = String(row[4] == null ? '' : row[4]).trim() || '(미기재)';
    var done = (String(row[5]) === '완료');
    var inspector = String(row[11] == null ? '' : row[11]).trim() || '(미기재)';
    var measure = String(row[12] == null ? '' : row[12]);
    var sKey = ymd + '|' + round;
    sessionSet[sKey] = true;

    if (!byDate[ymd]) byDate[ymd] = { total: 0, done: 0, roundSet: {} };
    byDate[ymd].total++; if (done) byDate[ymd].done++;
    byDate[ymd].roundSet[round] = true;

    if (!byCatMap[cat]) byCatMap[cat] = { cat: cat, total: 0, done: 0 };
    byCatMap[cat].total++; if (done) byCatMap[cat].done++;

    if (!byRoundMap[round]) byRoundMap[round] = { round: round, total: 0, done: 0, daySet: {} };
    byRoundMap[round].total++; if (done) byRoundMap[round].done++;
    byRoundMap[round].daySet[ymd] = true;

    if (!byInspectorMap[inspector]) byInspectorMap[inspector] = { inspector: inspector, total: 0, done: 0, sessionSet: {} };
    byInspectorMap[inspector].total++; if (done) byInspectorMap[inspector].done++;
    byInspectorMap[inspector].sessionSet[sKey] = true;

    _facilityRangeHits(measure).forEach(function (h) {
      outOfRangeList.push({ date: ymd, round: round, itemId: itemId, name: itemName, field: h.field, value: h.value, min: h.min, max: h.max });
      if (!outOfRangeByItem[itemId]) outOfRangeByItem[itemId] = { itemId: itemId, name: itemName, count: 0 };
      outOfRangeByItem[itemId].count++;
    });
  });
  outOfRangeList.sort(function (a, b) { return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0); });

  var dailySeries = Object.keys(byDate).sort().map(function (d) {
    var c = byDate[d];
    var oorThatDay = outOfRangeList.filter(function (o) { return o.date === d; }).length;
    return { date: d, total: c.total, done: c.done, pct: c.total > 0 ? Math.round(c.done / c.total * 100) : null, sessionCount: Object.keys(c.roundSet).length, outOfRangeCount: oorThatDay };
  });

  var monthTotal = 0, monthDone = 0;
  dailySeries.forEach(function (d) { monthTotal += d.total; monthDone += d.done; });

  var monthTotals = {
    total: monthTotal, done: monthDone,
    avgPct: monthTotal > 0 ? Math.round(monthDone / monthTotal * 100) : null,
    sessionCount: Object.keys(sessionSet).length,
    activeDays: dailySeries.length,
    outOfRangeCount: outOfRangeList.length
  };

  var byCategory = Object.keys(byCatMap).map(function (c) {
    var v = byCatMap[c];
    return { cat: v.cat, total: v.total, done: v.done, pct: v.total > 0 ? Math.round(v.done / v.total * 100) : null };
  }).sort(function (a, b) { return b.total - a.total; });

  var byRound = Object.keys(byRoundMap).map(function (r) {
    var v = byRoundMap[r];
    return { round: v.round, total: v.total, done: v.done, pct: v.total > 0 ? Math.round(v.done / v.total * 100) : null, sessionCount: Object.keys(v.daySet).length };
  }).sort(function (a, b) { return b.total - a.total; });

  var byInspector = Object.keys(byInspectorMap).map(function (i) {
    var v = byInspectorMap[i];
    return { inspector: v.inspector, sessionCount: Object.keys(v.sessionSet).length, avgPct: v.total > 0 ? Math.round(v.done / v.total * 100) : null };
  }).sort(function (a, b) { return b.sessionCount - a.sessionCount; });

  var outOfRangeByItemArr = Object.keys(outOfRangeByItem).map(function (k) { return outOfRangeByItem[k]; })
    .sort(function (a, b) { return b.count - a.count; });

  var improvements = [];
  var catsWithPct = byCategory.filter(function (c) { return c.pct !== null && c.total > 0; });
  if (catsWithPct.length > 0) {
    var worstCat = catsWithPct.reduce(function (a, b) { return b.pct < a.pct ? b : a; });
    improvements.push(worstCat.cat + ' 입력률 최저(' + worstCat.pct + '%) — 집중 필요');
  }
  if (outOfRangeByItemArr.length > 0) {
    improvements.push(outOfRangeByItemArr[0].name + ' 기준이탈 최다(' + outOfRangeByItemArr[0].count + '건) — 설비 점검 필요');
  }
  var roundsLowPct = byRound.filter(function (r) { return r.pct !== null && r.pct < 70; });
  if (roundsLowPct.length > 0) {
    improvements.push(roundsLowPct.map(function (r) { return r.round; }).join('·') + ' 회차 입력률 70% 미만 — 원인 점검');
  }
  if (Object.keys(sessionSet).length < 5) {
    improvements.push('표본 부족 — 추세 판단 유보');
  }

  return {
    ok: true,
    dept: null, // handleMonthlyReport(IO)에서 채움
    month: month,
    testExcludedCount: testExcludedCount,
    dailySeries: dailySeries,
    monthTotals: monthTotals,
    byCategory: byCategory,
    byRound: byRound,
    byInspector: byInspector,
    outOfRange: { total: outOfRangeList.length, byItem: outOfRangeByItemArr, list: outOfRangeList },
    // 이슈(사람이 등록하는 정성 이슈)는 시설점검 화면에 등록 UI가 없어 실제 미가동 — 지어내기 금지, 정직 태그.
    issues: { total: 0, note: '❌ 미측정 · 시설점검 이슈 등록 UI 미가동(시설_이슈대장·측정값 6열 모두 실사용 데이터 없음). 측정값 기준이탈(outOfRange)이 가장 가까운 대체 신호 — 원문 이슈와는 다른 지표.' },
    improvements: improvements,
    denomNote: '완료율=입력률(항목 제출완료 수/전체 항목 수, 회차별 항목 구성 상이)',
    measureNote: '기준이탈 판정은 사우나 5종·수영장 3종(FC_RANGES)만 가능 — 온수탱크 3종·공조기 4종·안전점검(AI초안) 4종은 기준 미설정으로 판정 대상 제외(❌ 미측정, GM 기준 확정 시 추가).'
  };
}

// IO 담당: 스냅샷(점검일지_<dept>)+이슈대장 시트 read → _aggregateMonthly 호출 → JSON 반환.
// GET ?action=monthly_report&dept=support&month=YYYY-MM(생략 시 오늘 기준 이번달)
// dept=facility는 구조가 근본적으로 달라(시설_공용구역 항목단위 실측) _aggregateMonthlyFacility로 완전 분기(배406).
function handleMonthlyReport(params) {
  params = params || {};
  var dept = params.dept || 'support';
  var month = params.month || '';
  if (!/^\d{4}-\d{2}$/.test(month)) {
    month = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM');
  }
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  if (dept === 'facility') {
    var fcSheet = ss.getSheetByName(SHEET_FACILITY_COMMON);
    var fcRows = (fcSheet && fcSheet.getLastRow() > 1) ? fcSheet.getDataRange().getValues().slice(1) : [];
    var fcResult = _aggregateMonthlyFacility(fcRows, month);
    fcResult.dept = dept;
    return jsonRes(fcResult);
  }

  var snapSheet = ss.getSheetByName(_snapshotTabName(dept));
  var snapRows = [];
  if (snapSheet && snapSheet.getLastRow() > 1) {
    snapRows = snapSheet.getDataRange().getValues().slice(1);
  }

  var issueTabName = dept === 'facility' ? SHEET_ISSUE_FACILITY : SHEET_ISSUE_SUPPORT;
  var issueSheet = ss.getSheetByName(issueTabName);
  var issueRows = [];
  if (issueSheet && issueSheet.getLastRow() > 1) {
    issueRows = issueSheet.getDataRange().getValues().slice(1);
  }

  // [배14+배173, 2026-07-04] 스케줄 기대치 맵 — 이 달 1일~말일 각 날짜의 today_live 기준 예정 총량.
  // support 한정(_buildTodayMaster/today_live도 support 전용) — 다른 dept는 빈 맵 → _aggregateMonthly가
  // 기존 방식(세션기록 합계)으로 폴백해 무변경.
  var scheduleTotals = {};
  if (dept === 'support') {
    var ymParts = month.split('-');
    var y = Number(ymParts[0]), mo = Number(ymParts[1]);
    if (y && mo) {
      var daysInMonth = new Date(y, mo, 0).getDate();
      for (var dd = 1; dd <= daysInMonth; dd++) {
        var ymd = y + '-' + _pad2_(mo) + '-' + _pad2_(dd);
        scheduleTotals[ymd] = _scheduleExpectedTotal(dept, ymd);
      }
    }
  }

  var result = _aggregateMonthly(snapRows, issueRows, month, scheduleTotals);
  result.dept = dept;
  return jsonRes(result);
}

// ════════════════════════════════════════════
// action=today_live — 오늘 실시간 점검 현황(읽기 전용·제출도장 안 찍음)
// GET ?action=today_live&dept=support[&date=YYYY-MM-DD]
// 분자(done): cr 회차원장(키 '<round>_<id>')을 회차버킷(am/pm/close/night)별로 카운트 — 남/여/공용 합산.
// 분모(total): 지원_매뉴얼 시트 + ROUND_MAP(GAS 내장) 기반 — 클라 _roundProgress와 동일 단일출처.
//   시트항목 id → ROUND_MAP(하드코딩) 우선, 없으면 시트 rounds 컬럼. gender 필터 동일 적용.
//   DAY_FOCUS(요일별 pm가산)도 반영. 하드코딩 상수 없음 — 시트 변경 즉시 반영.
// ⚠ sub(제출도장) 절대 안 찍음. support 한정.
// 응답: { ok, dept, date, am, pm, close, night, amTotal, pmTotal, closeTotal, nightTotal, total, done, pct, byGender:{m,f,all:{...}} }
// ════════════════════════════════════════════

// 회차키(am1/pm1/close1/night1…) → 버킷(am/pm/close/night).
function _roundBucket(roundKey) {
  var base = String(roundKey == null ? '' : roundKey).replace(/[0-9\[\]]+$/, '');
  return _shiftBucket(base);
}

// ─── 분모·분자 단일출처: 항목 마스터(action=items와 동일 모집단) ───────────────
// GM 확정(2026-06-24): 점검 마스터 = getItems가 반환하는 NON-seed 지원부 행(시트 실물 기준·페이지 배열: 평일30/주말31/야간포함45).
//   분모 규칙 = 각 항목을 '대표 버킷'(rounds 배열의 첫 회차)에 1회만 계상. 멀티회차(am1,pm1,close1)는
//   대표=am 1회만(과거 회차전개 3중계상=259 부풀림 제거). gender all→[m,f]·m→[m]·f→[f].
//   DAY_FOCUS(df_*) 항목은 rounds 비어있고 id에 요일 인코딩(df_wed1) → 오늘 요일과 일치할 때만 close 1회.
//   분자(done)도 동일 모집단·대표버킷으로 정합(handleTodayLive에서 이 master 사용).
// _TL_ROUND_MAP·_TL_DAY_FOCUS_CNT·_TL_NIGHT_CNT(하드코딩 가산) 전부 폐기 — 마스터가 유일 출처.

var _TL_DOW_TOKEN = { 0: 'sun', 1: 'mon', 2: 'tue', 3: 'wed', 4: 'thu', 5: 'fri', 6: 'sat' };

// sched 문자열 파싱(화면 parseSched와 동일): "tue,fri|2,4" → {days:['tue','fri'], weeks:['2','4']}.
function _tlParseSched(s) {
  s = String(s == null ? '' : s).trim();
  var p = s.split('|');
  var days  = (p[0] || '').split(',').filter(Boolean);
  var weeks = (p.length > 1 ? p[1].split(',') : []).filter(Boolean);
  return { days: days, weeks: weeks };
}

// sched 요일/주차 필터(화면 _itemOnDay + 주차 격주 반영). 빈 sched=항상 통과.
//   days 있으면 오늘 요일토큰이 days에 있어야 통과. weeks 있으면 'b'(격주) 또는 이번주차(week)가 weeks에 있어야 통과.
function _tlPassesSched(sched, dowTok, week) {
  var p = _tlParseSched(sched);
  if (p.days.length && p.days.indexOf(dowTok) < 0) return false;
  if (p.weeks.length && p.weeks.indexOf('b') < 0 && p.weeks.indexOf(String(week)) < 0) return false;
  return true;
}

// 항목 마스터 빌드 → { byId:{id:{buckets:[unique shifts], glist, gender}}, count }.
// getItems와 동일하게 seed='Y' 행 제외(중복 차단). 오늘(dow) sched 요일/주차 필터 반영.
// ★ 화면정합(2026-06-25 시우): (a) 시프트 presence — 항목을 회차마다 1회씩(시프트당 unique) 계상(과거: 첫 회차 1버킷만).
//   (b) sched 요일/주차 필터 추가(화면 parseSched/_itemOnDay 동치) — 화면에 안 뜨는 항목은 분모서도 제외.
//   (c) df_* 처리 유지: rounds 비고 id가 df로 시작 → close 1회(요일은 sched 필터가 처리). night는 합계 제외 유지.
function _buildTodayMaster(dept, dow, week) {
  var master = { byId: {}, count: 0 };
  var dowTok = _TL_DOW_TOKEN[dow];

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return master;
  var last = sheet.getLastRow();
  if (last < 2) return master;
  var vals = sheet.getRange(2, 1, last - 1, Math.max(ITEM_HEADERS.length, sheet.getLastColumn())).getValues();

  vals.forEach(function (row) {
    var id      = String(row[0] || '').trim();
    var name    = String(row[2] || '').trim();
    // [근본수정 2026-07-03] 원시 성별 셀은 한글로 저장됨(saveItems가 _genderToKorean으로 기록·2026-06-29 시우)인데
    // 여기선 변환 없이 그대로 비교해 gender==='all' 매치가 전부 실패 → glist에 '공통'/'남'/'여' 원문이 들어가
    // totalByG/doneByG(m·f·all 키만 존재)에서 전부 스킵되어 total=done=0 도배(getItems는 이미 _genderToEnglish 적용·정합).
    var gender  = _genderToEnglish(row[4]);
    var sched   = _schedToEnglish(row[ITEM_SCHED_COL] == null ? '' : row[ITEM_SCHED_COL]);   // '일정'(요일|주차) 컬럼 — getItems와 동일 패턴(2026-06-30 시우)
    var deptVal = _itemDept(row[ITEM_DEPT_COL]);
    var roundsRaw = String(row[ITEM_ROUNDS_COL] == null ? '' : row[ITEM_ROUNDS_COL]).trim();   // '회차' 컬럼

    if (!id && !name) return;             // 빈 행
    if (deptVal !== 'support') return;    // 지원부만
    // seed skip 제거(2026-06-27): getItems와 동일하게 seed 행도 포함(시트=단일출처).
    if (!id) return;

    // sched 요일/주차 필터(화면 _itemOnDay + 격주): 오늘 안 뜨는 항목은 분모 제외.
    if (!_tlPassesSched(sched, dowTok, week)) return;

    var glist = (gender === 'all') ? ['m', 'f'] : [gender];

    // 시프트 presence: id가 df로 시작 & rounds 비었으면 close 1회. 아니면 rounds 각 토큰 bucket(시프트당 dedup). night 제외.
    var buckets = {};
    if (id.indexOf('df') === 0 && !roundsRaw) {
      buckets['close'] = 1;
    } else {
      var rounds = roundsRaw ? roundsRaw.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : [];
      rounds.forEach(function (r) {
        var b = _roundBucket(r);
        if (b === 'am' || b === 'pm' || b === 'close') buckets[b] = 1;
      });
    }
    var bucketList = Object.keys(buckets);
    if (!bucketList.length) return;       // 회차 미정 + df_ 아님 → 분모 제외(미분류)

    master.byId[id] = { buckets: bucketList, glist: glist, gender: gender };
    master.count++;
  });

  return master;
}

// ─── 스케줄 기대 분모 단일출처 — today_live·monthly_report 공유(배173+배14 정합, 2026-07-04 시우) ───
// master.byId(=_buildTodayMaster 결과) → 성별×버킷(am/pm/close/night) 카운트. handleTodayLive의 totalByG와
// monthly_report의 스케줄기대치가 이 함수 하나를 같이 써야 두 값이 절대 어긋나지 않는다(중복코드 금지).
function _tlTotalByGFromMaster(master) {
  var totalByG = { m: { am: 0, pm: 0, close: 0, night: 0 }, f: { am: 0, pm: 0, close: 0, night: 0 }, all: { am: 0, pm: 0, close: 0, night: 0 } };
  Object.keys(master.byId).forEach(function (id) {
    var info = master.byId[id];
    info.glist.forEach(function (g) {
      if (!totalByG[g]) return;
      info.buckets.forEach(function (b) {
        if (totalByG[g][b] !== undefined) totalByG[g][b]++;
      });
    });
  });
  return totalByG;
}

// 'YYYY-MM-DD' → week(몇째주, 화면 getDayInfo와 동일: Math.ceil(일/7)).
function _tlWeekOfDate(dateStr) {
  return Math.ceil(Number(String(dateStr).slice(8, 10)) / 7);
}

// 날짜 하나의 '오늘 예정' 총 항목수(스케줄 기대 분모) — today_live의 total과 완전히 같은 기준.
// [배173, 2026-07-04] 주말(토·일)은 오후조가 없다(오전조+마감조만 정상) — pm 버킷은 분모에서 제외.
//   실측(2026-07-04 토): 시트 sched 필터를 통과한 주말 pm 항목이 분모에 얹혀 105로 부풀림(정답=76).
// monthly_report(handleMonthlyReport)가 날짜별로 이 함수를 호출해 스케줄 기대치 맵을 만들고,
// _aggregateMonthly가 세션기록 합계 대신 이 값을 분모로 써 today_live와 정합시킨다(배14).
function _scheduleExpectedTotal(dept, dateStr) {
  var dateObj = new Date(dateStr + 'T00:00:00+09:00');
  var dow = dateObj.getDay();
  var week = _tlWeekOfDate(dateStr);
  var master = _buildTodayMaster(dept, dow, week);
  var totalByG = _tlTotalByGFromMaster(master);
  var isWeekend = (dow === 0 || dow === 6);
  var total = 0;
  ['m', 'f', 'all'].forEach(function (g) {
    total += totalByG[g].am + (isWeekend ? 0 : totalByG[g].pm) + totalByG[g].close;
  });
  return total;
}

function handleTodayLive(params) {
  var dept = String(params.dept || 'support').trim() || 'support';
  if (dept !== 'support') {
    return jsonRes({ ok: false, dept: dept, error: 'today_live는 support 전용(facility/parking은 weekly 사용)' });
  }
  var tz = 'Asia/Seoul';
  var date = String(params.date || '').trim() || Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');

  var genders = ['m', 'f', 'all'];
  var buckets = ['am', 'pm', 'close', 'night'];
  function newBuckets() { return { am: 0, pm: 0, close: 0, night: 0 }; }

  // ─── 마스터(분모·분자 단일출처): action=items와 동일 모집단(non-seed 지원부 항목·시트 실물 기준·페이지 배열: 평일30/주말31/야간포함45) ───
  var dateObj = new Date(date + 'T00:00:00+09:00');
  var dow = dateObj.getDay();
  var week = Math.ceil(Number(date.slice(8, 10)) / 7);   // 화면 getDayInfo와 동일: Math.ceil(일/7)
  var master = _buildTodayMaster(dept, dow, week);   // { byId:{id:{buckets:[unique shifts],glist}}, count }
  var isWeekend = (dow === 0 || dow === 6);   // [배173, 2026-07-04] 주말=오전조+마감조만 정상(오후조 없음) — 아래 total/done·genderSummary가 pm 제외

  // ─── 분자(done): cr 원장 — (항목,시프트) presence(마스터 항목·시프트당 1회). 분모와 동일 기준 ───
  // 멀티회차 항목이 am1·pm1·close1 체크되면 done도 각 시프트(am/pm/close)에 1회씩(분모 시프트 presence와 정합).
  // 마스터에 없는 고아 id(리네임 잔재) 또는 마스터 항목에 없는 시프트는 분모가 없으므로 제외(100% 초과 차단).
  var doneByG = { m: newBuckets(), f: newBuckets(), all: newBuckets() };
  genders.forEach(function (g) {
    var led = _getCheckLedger(dept, date, g);
    var cr = (led && led.cr && typeof led.cr === 'object') ? led.cr : {};
    var seenPair = {};   // 이 성별에서 done 1회 처리한 '항목|시프트'
    Object.keys(cr).forEach(function (k) {
      if (!cr[k]) return;
      var us = String(k).indexOf('_');
      if (us < 0) return;
      var round = String(k).slice(0, us);
      var id = String(k).slice(us + 1);
      if (!id) return;
      var info = master.byId[id];
      if (!info) return;                   // 마스터 밖 고아 → 제외(분모 없음)
      // [근본수정 2026-07-03 시토] 이 체크가 기록된 성별(g)이 항목의 실제 적용성별(glist)에 없으면 제외.
      // 기존엔 이 필터가 없어 성별 재배정·id 재사용으로 남은 타성별 잔재 체크가 엉뚱한 성별의 분자에
      // 얹혔다 → done>total 발생 → 아래 클램프가 분모를 분자로 강제상향 → 매 회차 100% 왜곡의 근본원인.
      if (info.glist.indexOf(g) < 0) return;
      var b = _roundBucket(round);
      if (info.buckets.indexOf(b) < 0) return;   // 마스터 항목에 없는 시프트 → 제외(분모 없음·night 포함)
      var pk = id + '|' + b;
      if (seenPair[pk]) return;            // (항목,시프트)당 1회만
      seenPair[pk] = 1;
      doneByG[g][b]++;
    });
  });

  // ─── 분모(total): 위에서 빌드한 동일 master를 시프트 presence(시프트당 1회)로 계상(성별 분리) ───
  // _tlTotalByGFromMaster로 단일화(2026-07-04) — monthly_report의 스케줄기대치(_scheduleExpectedTotal)와
  // 완전히 같은 집계 함수를 공유해 두 소스가 절대 어긋나지 않게 한다(배14).
  var totalByG = _tlTotalByGFromMaster(master);
  // [근본수정 2026-07-03 시토] 'gender=all 강제 분자=분모(totalByG.all[b] = doneByG.all[b])' 라인 제거.
  // genderTab은 항상 m|f만 저장되어(_chkGender) gender='all' 원장은 실사용된 적이 없다(doneByG.all 항상 0).
  // 강제 등식은 아무 것도 고치지 않으면서 향후 'all' 원장이 생기면 '분모=분자 항상 100%' 왜곡을 재도입할
  // 위험만 있던 죽은 코드 — totalByG.all은 자연값(0)으로 둔다.

  // 최종 안전장치(2026-07-03 시토 수정): 분모(마스터=오늘 예정)는 절대 불변 유지 — 분자를 분모 이하로
  // 캡핑해 100% 초과만 차단한다. 기존엔 반대로 분모를 분자에 맞춰 끌어올려(강제 done=total) 부분완료도
  // 항상 100%로 표시되는 '하한 왜곡' 버그였다(GM 2026-07-03 신고: 매 회차·매 성별 분자=분모 도배).
  genders.forEach(function (g) {
    buckets.forEach(function (b) {
      if (doneByG[g][b] > totalByG[g][b]) doneByG[g][b] = totalByG[g][b];
    });
  });

  // ─── 합산(남+여+공용) ───
  var sumDone = newBuckets(), sumTotal = newBuckets();
  genders.forEach(function (g) {
    buckets.forEach(function (b) { sumDone[b] += doneByG[g][b]; sumTotal[b] += totalByG[g][b]; });
  });
  // total/done/pct = am+pm+close 만 (야간은 외주 탕청소 별도 회차 — GM 확정 2026-06-16).
  // night 필드는 참고용으로 응답에 유지하되 합계에서 제외.
  // [배173, 2026-07-04] 주말(토·일)은 오후조 없음(오전조+마감조만 정상) — pm은 분모·분자 모두 제외.
  // 평일은 기존과 동일(am+pm+close 무변경). pm/pmTotal 필드 자체는 진단용으로 응답엔 그대로 남긴다.
  var done  = sumDone.am  + (isWeekend ? 0 : sumDone.pm)  + sumDone.close;
  var total = sumTotal.am + (isWeekend ? 0 : sumTotal.pm) + sumTotal.close;
  var pct = total > 0 ? Math.round(done / total * 100) : 0;

  // ─── 이슈 집계 — led.cr 메타에서 iss 필드 수집(2026-06-25 시우): 단일 소스 ───
  // today_live가 이슈를 집계하지 않아 allIssues=0 고정이던 버그 수정.
  // 저장 소스: _updateCheckLedger → led.cr[k].iss. 여기서 직접 읽어 반환.
  // dedup: 같은 (성별+항목ID+이슈텍스트)는 1건만(동일 항목 복수 회차 제출 시 중복 방지).
  var allIssues = [];
  var _issSeenTL = {};
  ['m', 'f'].forEach(function (g) {
    var led = _getCheckLedger(dept, date, g);
    var cr = (led && led.cr && typeof led.cr === 'object') ? led.cr : {};
    Object.keys(cr).forEach(function (k) {
      var m = cr[k];
      if (!m || typeof m !== 'object') return;
      var iss = String(m.iss || '').trim();
      if (!iss) return;
      var us = String(k).indexOf('_'); if (us < 0) return;
      var round = k.slice(0, us), id = k.slice(us + 1);
      var dk = g + '|' + id + '|' + iss;
      if (_issSeenTL[dk]) return;
      _issSeenTL[dk] = 1;
      allIssues.push({ gender: g, roundKey: round, itemId: id, issue: iss, tip: String(m.tip || ''), by: String(m.by || '') });
    });
  });

  function genderSummary(g) {
    var gd = doneByG[g], gt = totalByG[g];
    var gdone = gd.am + (isWeekend ? 0 : gd.pm) + gd.close;   // night 제외, 주말은 pm도 제외(배173)
    var gtot  = gt.am + (isWeekend ? 0 : gt.pm) + gt.close;   // night 제외, 주말은 pm도 제외(배173)
    return { am: gd.am, pm: gd.pm, close: gd.close, night: gd.night,
             amTotal: gt.am, pmTotal: gt.pm, closeTotal: gt.close, nightTotal: gt.night,
             done: gdone, total: gtot, pct: gtot > 0 ? Math.round(gdone / gtot * 100) : 0 };
  }

  return jsonRes({
    ok: true, dept: dept, date: date,
    dow: dow, schedType: (dow === 0 || dow === 6 ? 'weekend' : 'weekday'),  // 진단용
    am: sumDone.am, pm: sumDone.pm, close: sumDone.close, night: sumDone.night,
    amTotal: sumTotal.am, pmTotal: sumTotal.pm, closeTotal: sumTotal.close, nightTotal: sumTotal.night,
    total: total, done: done, pct: pct,
    allIssues: allIssues,   // 2026-06-25 시우: led.cr 메타에서 이슈 집계 — 쓰기·읽기 단일 소스 정합
    byGender: { m: genderSummary('m'), f: genderSummary('f'), all: genderSummary('all') }
  });
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

// ════════════════════════════════════════════
// 점검일지 스냅샷 제출시각 내림차순 정렬(최근 최상위) — 1회성 유지보수. GET ?action=sort_snapshot&dept=support. 2026-06-16 시우.
// ════════════════════════════════════════════
function sortSnapshotDesc(dept){
  dept = dept || 'support';
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var name = _snapshotTabName(dept);
  var sheet = ss.getSheetByName(name);
  if (!sheet) return jsonRes({ ok: false, error: '스냅샷 시트 없음: ' + name });
  var last = sheet.getLastRow(), lastCol = sheet.getLastColumn();
  if (last < 3) return jsonRes({ ok: true, msg: '정렬 대상 없음', rows: Math.max(0, last - 1) });
  var rng = sheet.getRange(2, 1, last - 1, lastCol);
  var vals = rng.getValues();
  function ts(v){
    if (v instanceof Date) return v.getTime();
    var s = String(v == null ? '' : v).trim(); if (!s) return 0;
    var t = new Date(s.replace(' ', 'T')).getTime();
    return isNaN(t) ? 0 : t;
  }
  vals.sort(function(a, b){ return ts(b[0]) - ts(a[0]); });
  rng.setValues(vals);
  return jsonRes({ ok: true, dept: dept, sheet: name, sorted: vals.length });
}

// 지원_매뉴얼(항목 마스터) 행을 페이지 기본순서(카테고리 GROUP_ORDER + 정렬칸)로 재배열 + 정렬칸 1..N 재부여.
// 1회성 유지보수. GET ?action=sort_manual_order. 2026-06-16 시우.
var _MANUAL_CAT_ORDER = ['오픈 점검','A 사우나점검','B 락커룸','C 내부','D 업장','E 외부','교대 인수인계','마감 점검'];
function _manualCatRank(cat){ var i = _MANUAL_CAT_ORDER.indexOf(String(cat == null ? '' : cat).trim()); return i >= 0 ? i : 90; }
function sortManualByPageOrder(){
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_ITEMS);
  if (!sheet) return jsonRes({ ok: false, error: '매뉴얼 시트 없음: ' + SHEET_ITEMS });
  var last = sheet.getLastRow(), lastCol = sheet.getLastColumn();
  if (last < 3) return jsonRes({ ok: true, msg: '정렬 대상 없음', rows: Math.max(0, last - 1) });
  var rng = sheet.getRange(2, 1, last - 1, lastCol);
  var vals = rng.getValues();
  var dec = vals.map(function(r, i){
    var sortv = parseFloat(r[5]); if (isNaN(sortv)) sortv = 9999;  // 12칸: 정렬=idx5(구 idx6)
    return { r: r, i: i, d: _itemDept(r[ITEM_DEPT_COL]), rank: _manualCatRank(r[1]), sortv: sortv };
  });
  dec.sort(function(a, b){
    if (a.d !== b.d) return a.d < b.d ? -1 : 1;
    if (a.rank !== b.rank) return a.rank - b.rank;
    if (a.sortv !== b.sortv) return a.sortv - b.sortv;
    return a.i - b.i;
  });
  var out = dec.map(function(o, k){ var r = o.r.slice(); r[5] = k + 1; return r; });  // 12칸: 정렬=idx5
  rng.setValues(out);
  return jsonRes({ ok: true, sheet: SHEET_ITEMS, sorted: out.length, order: out.map(function(r){ return String(r[0]); }) });
}

// ── 회차 점검자 배정 메모(공유·아무나 편집) — ScriptProperties 단일저장. 키=imemo_{dept}_{gender}_{round}. 2026-06-16 시우. ──
function _inspMemoKey(dept, gender, round){
  return 'imemo_' + (String(dept == null ? 'support' : dept).trim() || 'support') + '_' + (String(gender == null ? 'm' : gender).trim() || 'm') + '_' + String(round == null ? '' : round).trim();
}
function saveInspMemo(body){
  var dept = body.dept || 'support', gender = body.gender || 'm', round = String(body.round == null ? '' : body.round).trim();
  if (!round) return jsonRes({ ok: false, error: 'round 필수' });
  var memo = String(body.memo == null ? '' : body.memo);
  var props = PropertiesService.getScriptProperties();
  if (memo === '') props.deleteProperty(_inspMemoKey(dept, gender, round));
  else props.setProperty(_inspMemoKey(dept, gender, round), memo);
  return jsonRes({ ok: true, dept: dept, gender: gender, round: round });
}
function _getInspMemos(dept, gender){
  var out = {};
  try{
    var props = PropertiesService.getScriptProperties();
    var g = String(gender == null ? '' : gender).trim();
    if (!g) return out;
    ['am1','pm1','close1'].forEach(function(rk){
      var v = props.getProperty(_inspMemoKey(dept, g, rk));
      if (v != null && v !== '') out[rk] = v;
    });
  }catch(e){}
  return out;
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
  // (날짜·구역·회차) 동일 행이 있으면 덮어쓰기(재제출=갱신·중복 방지), 없으면 추가. GM 2026-06-16 시우.
  var _data = sheet.getDataRange().getValues();
  var _hit = 0;
  for (var _r = _data.length - 1; _r >= 1; _r--) {
    var _rd = (formatDate(_data[_r][1]) === String(body.date || '') || String(_data[_r][1]) === String(body.date || ''));
    if (_rd && String(_data[_r][3]) === String(body.zone || '') && String(_data[_r][4]) === String(body.shift || '')) {
      sheet.getRange(_r + 1, 1, 1, row.length).setValues([row]); _hit = 1; break;
    }
  }
  if (!_hit) sheet.appendRow(row);
  // 항상 제출시각(1열) 내림차순 = 최신 최상위 유지.
  var _ls = sheet.getLastRow();
  if (_ls > 2) sheet.getRange(2, 1, _ls - 1, sheet.getLastColumn()).sort({ column: 1, ascending: false });
  return jsonRes({ ok: true, dept: dept, mode: _hit ? 'update' : 'append', row: sheet.getLastRow() });
}
// 점검일지 중복 청소(1회): ①조 버킷줄(am/pm/night) 제거 — 회차줄로 대체됨 ②(날짜·구역·회차) 중복은 최신 제출시각만 보존. GM 2026-06-16 시우.
function dedupSnapshot(dept) {
  dept = dept || 'support';
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(_snapshotTabName(dept));
  if (!sheet) return jsonRes({ error: 'no snapshot' });
  var data = sheet.getDataRange().getValues();
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    if (!String(data[i][1] || '') && !String(data[i][0] || '')) continue;
    rows.push({ idx: i + 1, at: String(data[i][0] || ''), date: (formatDate(data[i][1]) || String(data[i][1] || '')), zone: String(data[i][3] || ''), shift: String(data[i][4] || '') });
  }
  var del = [], removedBucket = 0, removedDup = 0;
  rows.forEach(function (r) { if (/^(am|pm|night)$/.test(r.shift)) { r._del = 1; del.push(r.idx); removedBucket++; } });
  var best = {};
  rows.forEach(function (r) { if (r._del) return; var k = r.date + '|' + r.zone + '|' + r.shift; if (!best[k] || r.at > best[k].at) best[k] = r; });
  rows.forEach(function (r) { if (r._del) return; var k = r.date + '|' + r.zone + '|' + r.shift; if (best[k] !== r) { del.push(r.idx); removedDup++; } });
  del.sort(function (a, b) { return b - a; });
  del.forEach(function (rn) { try { sheet.deleteRow(rn); } catch (e) { var c = Math.max(1, sheet.getLastColumn()); sheet.getRange(rn, 1, 1, c).clearContent(); } });
  return jsonRes({ ok: true, dept: dept, removedBucket: removedBucket, removedDup: removedDup });
}

// ─── 관리자 PIN 제출잠금 해제. 2026-06-17 시우 ───
// body: { action:'unlock_round', dept, date, gender, round, pin }
// round: am1 | pm1 | close1  →  baseShift: am | pm
// 원장(ScriptProperties) led.sub/subAt 해당 shiftKey 삭제 → 체크 데이터(led.c, led.cr) 보존.
// PIN SSOT: ScriptProperties 키 CHECK_UNLOCK_PIN (없으면 기본값 '1234').
var CHECK_UNLOCK_PIN_DEFAULT = '1234';
function _roundToShiftKey(round) {
  var r = String(round || '');
  if (r.indexOf('close') >= 0) return 'close';   // [근본수정 2026-06-26 시우] 마감조 잠금해제=led.sub.close만 삭제(탕청소 night·오후 pm 무영향). 구버전은 'night'였음.
  if (r.indexOf('pm') >= 0)    return 'pm';
  return 'am';
}
function handleUnlockRound(body) {
  var dept   = String(body.dept   || 'support').trim();
  var date   = String(body.date   || '').trim();
  var gender = String(body.gender || 'm').trim();
  var round  = String(body.round  || '').trim();
  var pin    = String(body.pin    || '').trim();

  if (!date || !round) return jsonRes({ ok: false, reason: 'PARAM' });

  // PIN 검증
  var props = PropertiesService.getScriptProperties();
  var correctPin = props.getProperty('CHECK_UNLOCK_PIN') || CHECK_UNLOCK_PIN_DEFAULT;
  if (pin !== correctPin) return jsonRes({ ok: false, reason: 'PIN' });

  // 원장 로드
  var key = _chkKey(dept, date, gender);
  var led = {};
  try { led = JSON.parse(props.getProperty(key) || '{}'); } catch (e) {}
  if (!led.sub)   led.sub   = {};
  if (!led.subAt) led.subAt = {};

  // shiftKey(am/pm/night) 기반으로 제출 메타만 삭제(체크 데이터 보존)
  var shiftKey = _roundToShiftKey(round);
  delete led.sub[shiftKey];
  delete led.subAt[shiftKey];

  props.setProperty(key, JSON.stringify(led));
  return jsonRes({ ok: true, dept: dept, date: date, gender: gender, round: round, shiftKey: shiftKey });
}

// ─── 점검 알림 채팅방 진단 함수 ───────────────────────────────────────────────
// CHAT_ID는 코드 상수(-5136037543)로 고정. 이 함수는 ScriptProperty 잔존값 확인용.
function getCheckRoomChatId() {
  return { code_const: '-5136037543', property_value: PropertiesService.getScriptProperties().getProperty('TELEGRAM_CHAT_ID') };
}
