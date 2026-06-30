// 웰페리온 GM TODO 전용 Apps Script
// apps_script_v3.js(체크리스트)와 완전 독립 — 의존성 없음
// 시트: TODO | 헤더 14열
// CRUD + 파일 업로드(Base64→Drive) + 텔레그램 알림(선택)

// ─── 상수 ───
// 시트명 fallback (GM이 수동 변경 시 자동 매칭 · 2026-05-28)
const TODO_SHEET = '업무&결재 현황';        // 메인 — 신규 생성 시 이름
const TODO_SHEET_FALLBACKS = [
  '업무&결재 현황', '업무&결재현황',
  '업무 현황',
  'TODO',
  '업무 현황 SSOT'
];
const DONE_SHEET_NAME = '업무 완료 현황';   // 백업 (상태=완료 자동 복사 + 결재완료 자동 복사)
// ⚠ 완료보관(아카이브) 전용 fallback — '업무 완료 현황' 정확 매칭 우선.
// '결재 현황'/'결재 현황 SSOT'(결재 진행 SSOT 탭)은 의도적으로 제외: 완료 건이 결재 현황 탭으로
//   잘못 복사되던 오탐 차단(2026-06-26 시로). 완료보관은 오직 '업무 완료 현황'/'TODO_완료' 만 대상.
const DONE_SHEET_FALLBACKS = [
  '업무 완료 현황',
  'TODO_완료'
];

// 데이터 있는 시트 우선 — 첫 행 헤더에 '업무명' 또는 'id' 있으면 정식 시트
// autoDetect=true: fallback 이름이 모두 빗나가도 'id'+'업무명' 헤더를 가진
//   데이터 최다 시트를 자동 인식 (시트명 불일치로 인한 0건 사고 영구 차단 · 2026-05-29)
function _findSheet(ss, fallbacks, autoDetect) {
  let candidate = null;
  for (const name of fallbacks) {
    const s = ss.getSheetByName(name);
    if (!s) continue;
    if (s.getLastRow() >= 2) return s;  // 데이터 있는 시트 즉시 반환
    if (!candidate) candidate = s;       // 빈 시트는 후보로만
  }
  // 이름 매칭 실패 — 헤더 기반 자동 탐지 (TODO 조회 전용; DONE 복사 시엔 끔)
  if (autoDetect) {
    let best = null, bestRows = 0;
    ss.getSheets().forEach(s => {
      const lc = s.getLastColumn();
      if (lc < 2) return;
      const hdr = s.getRange(1, 1, 1, Math.min(lc, 3)).getValues()[0].map(String);
      if (hdr.indexOf('id') >= 0 && hdr.indexOf('업무명') >= 0) {
        const rows = s.getLastRow();
        if (rows > bestRows) { bestRows = rows; best = s; }
      }
    });
    if (best && bestRows >= 2) return best;  // 데이터 든 정식 시트 발견
  }
  return candidate;
}

const TODO_HEADERS = [
  'id', '업무명', '카테고리', '담당자',
  '시작일', '종료일', '내용', '상태',
  '결재요청', '링크', '파일URL',
  '생성자', '생성일', '수정일',
  // 결재 체계 (2026-05-28 신설)
  '부서장싸인', 'GM싸인', '대표싸인', '결재상태', '결재완료시각',
  // 결과보고서 자동 생성 (2026-05-29 신설)
  '결과보고서URL',
  // 업무 중요도 평가 (2026-06-03 신설 · 2026-06-10 확정) — 하=1·중=5·상=10. 담당자 제안 → 부서장 결재단계 확정.
  // ※ 가중치 점수 계산은 프론트(업무 현황 SSOT.html DIFF_WEIGHT)에서 수행. GAS는 '난이도' 셀(하/중/상) 원본만 저장.
  // append-only: 기존 컬럼 인덱스 불변. initTodoSheet 자동 마이그레이션이 재배포 시 시트에 컬럼 추가.
  '난이도',
  // 완료일 (2026-06-10 시토) — 상태→'완료' 전환 시점의 날짜(yyyy-MM-dd, Asia/Seoul) 자동 스탬프.
  // 결재완료시각과 별개: 결재 안 거친 업무도 완료일이 찍혀 G1 '오늘/지난 입항' 100% 정확.
  // append-only 맨 끝 추가 → 기존 컬럼 인덱스 불변. initTodoSheet 자동 마이그레이션이 시트에 컬럼 추가.
  '완료일'
];

// 카테고리 목록 (2026-06-10 GM 확정 9분류 — 프론트(업무·결재·G1 SSOT)와 동일 라벨·띄어쓰기 통일)
const CATEGORIES = [
  '[1] 매출 및 영업',
  '[2] 인사',
  '[3] 파트너팀',
  '[4] 운영 정책',
  '[5] 시설 및 환경',
  '[6] 회원·CS',
  '[7] IT·시스템·자동화',
  '[8] 교육·조직문화',
  '[9] 회의'
];

// 상태 목록 + 셀 색상
const STATUS_COLORS = {
  '진행중': '#4285f4', // 파랑
  '완료':   '#34a853', // 초록
  '보류':   '#9e9e9e'  // 회색
};

// ─── ScriptProperties 헬퍼 ───
function _prop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

// ─── 시트 초기화 ───
function initTodoSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = _findSheet(ss, TODO_SHEET_FALLBACKS, true);
  if (sh) {
    // 기존 시트 — 결재 컬럼 자동 마이그레이션 (2026-05-28)
    const existingHeaders = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    const newCols = TODO_HEADERS.filter(h => !existingHeaders.includes(h));
    if (newCols.length) {
      const startCol = existingHeaders.length + 1;
      sh.getRange(1, startCol, 1, newCols.length).setValues([newCols]);
      sh.getRange(1, startCol, 1, newCols.length)
        .setFontWeight('bold')
        .setBackground('#0b8043')  // 결재 컬럼 = 초록 (구분)
        .setFontColor('#ffffff');
      const newWidths = [130, 130, 130, 100, 150];
      newCols.forEach((_, i) => sh.setColumnWidth(startCol + i, newWidths[i] || 120));
    }
    return sh;
  }

  sh = ss.insertSheet(TODO_SHEET);
  sh.getRange(1, 1, 1, TODO_HEADERS.length).setValues([TODO_HEADERS]);
  sh.getRange(1, 1, 1, TODO_HEADERS.length)
    .setFontWeight('bold')
    .setBackground('#1a73e8')
    .setFontColor('#ffffff');

  // 결재 컬럼 5개는 별도 색 강조
  sh.getRange(1, 15, 1, 5).setBackground('#0b8043');

  const widths = [130, 200, 130, 80, 100, 100, 300, 70, 70, 200, 200, 80, 130, 130,
                  130, 130, 130, 100, 150, 200];
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

// ─── 생성일 DESC 자동 정렬 (헤더 1행 고정, 데이터 행만) ───
// 대상: 업무&결재 현황 탭 + AI배(C레벨) 탭 (이슈대장 제외).
// 1차: 생성일 desc / 2차: id desc (타임스탬프 기반 ID라 최신=사전 후순).
// 빈 생성일은 맨 아래로 밀림.
function _sortSheetByCreated(sh) {
  var lastRow = sh.getLastRow();
  if (lastRow < 3) return; // 헤더 + 1행 이하는 정렬 불필요
  var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var createdCol = headers.indexOf('생성일') + 1; // 1-based
  var idCol = headers.indexOf('id') + 1;
  if (createdCol < 1) return; // 생성일 컬럼 없으면 스킵
  var dataRows = lastRow - 1; // 헤더 제외 데이터 행 수
  var numCols = sh.getLastColumn();
  var range = sh.getRange(2, 1, dataRows, numCols);
  var values = range.getValues();
  var backgrounds = range.getBackgrounds();
  var fontColors = range.getFontColors();
  var fontWeights = range.getFontWeights();

  // 각 행에 배경·글자색·굵기를 붙여 정렬
  var rows = values.map(function(v, i) {
    return { v: v, bg: backgrounds[i], fc: fontColors[i], fw: fontWeights[i] };
  });

  // 셀값이 Date 객체일 수 있으므로 getTime()으로 숫자 변환, 아니면 문자열로 폴백
  function _toTs(v) {
    if (!v && v !== 0) return -Infinity;
    if (v instanceof Date) return isNaN(v.getTime()) ? -Infinity : v.getTime();
    var s = String(v).trim();
    if (!s) return -Infinity;
    var d = new Date(s);
    return isNaN(d.getTime()) ? s : d.getTime(); // 파싱 실패 시 문자열 그대로(문자열 비교)
  }

  rows.sort(function(a, b) {
    var ca = _toTs(a.v[createdCol - 1]);
    var cb = _toTs(b.v[createdCol - 1]);
    // 빈값(-Infinity)은 맨 아래
    if (ca === -Infinity && cb === -Infinity) return 0;
    if (ca === -Infinity) return 1;
    if (cb === -Infinity) return -1;
    // 생성일 desc (숫자는 숫자 비교, 문자열은 문자열 비교)
    if (cb !== ca) return cb > ca ? 1 : -1;
    // 보조: id desc (타임스탬프형 id)
    if (idCol >= 1) {
      var ia = String(a.v[idCol - 1] || '');
      var ib = String(b.v[idCol - 1] || '');
      return ib > ia ? 1 : ib < ia ? -1 : 0;
    }
    return 0;
  });

  var sortedValues = rows.map(function(r) { return r.v; });
  var sortedBg     = rows.map(function(r) { return r.bg; });
  var sortedFc     = rows.map(function(r) { return r.fc; });
  var sortedFw     = rows.map(function(r) { return r.fw; });

  range.setValues(sortedValues);
  range.setBackgrounds(sortedBg);
  range.setFontColors(sortedFc);
  range.setFontWeights(sortedFw);
}

// 타임스탬프 기반 ID 생성 (TODO-yyyyMMddHHmmssSSS)
function _genId() {
  return 'TODO-' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMddHHmmss')
    + ('000' + new Date().getMilliseconds()).slice(-3);
}

// 시트 데이터 → 객체 배열
function _readAll(sh) {
  const last = sh.getLastRow();
  if (last < 2) return [];
  const data = sh.getRange(2, 1, last - 1, TODO_HEADERS.length).getValues();
  return data.map(row => {
    const obj = {};
    TODO_HEADERS.forEach((h, i) => { obj[h] = row[i]; });
    return obj;
  });
}

// ID로 행 번호 찾기 (1-based, 헤더 포함)
function _findRow(sh, id) {
  const last = sh.getLastRow();
  if (last < 2) return -1;
  const ids = sh.getRange(2, 1, last - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(id)) return i + 2;
  }
  return -1;
}

// 상태 셀 색상 적용
function _applyStatusColor(sh, row, status) {
  const colIdx = TODO_HEADERS.indexOf('상태') + 1;
  const color = STATUS_COLORS[status] || '#ffffff';
  sh.getRange(row, colIdx).setBackground(color).setFontColor('#ffffff');
}

// 완료보관('업무 완료 현황') 시트에 완료 건 복사 (수동 완료·결재완료 공통)
// 동시 완료 시 보관행 유실 방지 — getLastRow 읽기~append 임계구역을 ScriptLock 으로 보호(2026-06-26 시로).
function _copyToDoneSheet(srcSheet, srcRow) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  // ── 동시성 가드: 보관 append 직렬화(다중 완료 동시 호출 시 같은 newRow 덮어쓰기 방지) ──
  const lock = LockService.getScriptLock();
  try { lock.waitLock(20000); } catch (e) { /* 잠금 실패해도 보관 시도는 진행(데이터 우선) */ }
  try {
    let doneSh = _findSheet(ss, DONE_SHEET_FALLBACKS, false);

    // 시트가 없으면 자동 생성 (메인 fallback 이름 우선)
    if (!doneSh) {
      doneSh = ss.insertSheet(DONE_SHEET_NAME);
      // 헤더 = TODO_HEADERS(끝에 '완료일' 포함) + 보관시각(아카이브 복사 시각).
      //   ※ '완료일' 중복 제거(2026-06-26 시로): 과거엔 TODO_HEADERS에 완료일이 없어 concat(['완료일'])
      //     했으나, 현재 TODO_HEADERS 끝이 이미 '완료일'이라 헤더가 2번 찍히던 버그. 추가 컬럼은 '보관시각'으로 명명.
      const headers = TODO_HEADERS.concat(['보관시각']);
      doneSh.getRange(1, 1, 1, headers.length).setValues([headers]);
      doneSh.getRange(1, 1, 1, headers.length)
        .setFontWeight('bold')
        .setBackground('#34a853')
        .setFontColor('#ffffff');
      const widths = [130, 200, 130, 80, 100, 100, 300, 70, 70, 200, 200, 80, 130, 130, 130];
      widths.forEach((w, i) => { if (i < headers.length) doneSh.setColumnWidth(i + 1, w); });
      doneSh.setFrozenRows(1);
    }

    // 원본 행 데이터 읽기
    const rowData = srcSheet.getRange(srcRow, 1, 1, TODO_HEADERS.length).getValues()[0];
    // 보관시각 추가 (아카이브로 복사된 시점)
    rowData.push(_now());

    // 완료 시트에 추가
    const newRow = doneSh.getLastRow() + 1;
    doneSh.getRange(newRow, 1, 1, rowData.length).setValues([rowData]);
    // 상태 셀 녹색 표시
    const statusCol = TODO_HEADERS.indexOf('상태') + 1;
    doneSh.getRange(newRow, statusCol).setBackground('#34a853').setFontColor('#ffffff');
    SpreadsheetApp.flush();  // 잠금 해제 전 기록 확정
  } finally {
    try { lock.releaseLock(); } catch (e) {}
  }
}

// ─── CORS JSON 응답 ───
function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ═══ 공지 서식 공용 저장 (전 PC 공유) — 2026-06-04 ═══
// 브라우저 localStorage(PC별 개별) → 공용 시트탭으로 이전. notice_list/save/delete.
var NOTICE_SHEET = '공지서식저장';
var NOTICE_HEADERS = ['id','savedAt','brand','type','orient','titleKr','titleEn','subtitle','startDate','endDate','ff','fs','lh','body'];
function _getNoticeSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(NOTICE_SHEET);
  if (!sh) { sh = ss.insertSheet(NOTICE_SHEET); sh.appendRow(NOTICE_HEADERS); }
  else if (sh.getLastRow() === 0) { sh.appendRow(NOTICE_HEADERS); }
  return sh;
}
function _processNoticeAction(body) {
  var action = body.action || '';
  var sh = _getNoticeSheet();
  var data = sh.getDataRange().getValues();
  var headers = (data[0] && data[0].length) ? data[0] : NOTICE_HEADERS;
  if (action === 'notice_list') {
    var items = [];
    for (var r = 1; r < data.length; r++) {
      if (!String(data[r][0])) continue;
      var o = {};
      for (var c = 0; c < headers.length; c++) o[headers[c]] = data[r][c];
      items.push(o);
    }
    items.reverse(); // 최근 저장이 위로
    return _json({ ok: true, count: items.length, data: items });
  }
  if (action === 'notice_save') {
    var id = String(body.id || '');
    if (!id) return _json({ ok: false, error: 'id 필수' });
    var rowArr = NOTICE_HEADERS.map(function(h){ return h === 'id' ? id : (body[h] !== undefined && body[h] !== null ? String(body[h]) : ''); });
    var foundRow = -1;
    for (var r2 = 1; r2 < data.length; r2++) { if (String(data[r2][0]) === id) { foundRow = r2 + 1; break; } }
    var targetRow = foundRow > 0 ? foundRow : sh.getLastRow() + 1;
    var rng = sh.getRange(targetRow, 1, 1, NOTICE_HEADERS.length);
    // 대상 행을 '텍스트'로 고정한 뒤 기록 → 날짜(startDate)·숫자(fs)·저장일 자동변환 방지
    try { rng.setNumberFormat('@'); } catch (e) {}
    rng.setValues([rowArr]);
    return _json({ ok: true, id: id });
  }
  if (action === 'notice_delete') {
    var did = String(body.id || '');
    if (!did) return _json({ ok: false, error: 'id 필수' });
    for (var r3 = 1; r3 < data.length; r3++) { if (String(data[r3][0]) === did) { sh.deleteRow(r3 + 1); return _json({ ok: true, id: did }); } }
    return _json({ ok: false, error: '해당 id 없음' });
  }
  return _json({ ok: false, error: '알 수 없는 notice action: ' + action });
}

// ═══ 상품 기획 저장 (CPO 기획 작업대 — 시트 공용) — 2026-06-30 ═══
var PRODUCT_SHEET = '상품기획저장';
var PRODUCT_HEADERS = ['id','구분','제안명','구성','가격가설','근거','상태','작성자','updated_at'];
function _getProductSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(PRODUCT_SHEET);
  if (!sh) { sh = ss.insertSheet(PRODUCT_SHEET); sh.appendRow(PRODUCT_HEADERS); }
  else if (sh.getLastRow() === 0) { sh.appendRow(PRODUCT_HEADERS); }
  return sh;
}
function _processProductPlanAction(body) {
  var action = body.action || '';
  var sh = _getProductSheet();
  var data = sh.getDataRange().getValues();
  var headers = (data[0] && data[0].length) ? data[0] : PRODUCT_HEADERS;
  if (action === 'product_plan_list') {
    var items = [];
    for (var r = 1; r < data.length; r++) {
      if (!String(data[r][0])) continue;
      var o = {};
      for (var c = 0; c < headers.length; c++) o[headers[c]] = data[r][c];
      items.push(o);
    }
    return _json({ ok: true, count: items.length, data: items });
  }
  if (action === 'product_plan_save') {
    var item = body.item || body;
    var id = String(item.id || '');
    if (!id) id = 'PP-' + new Date().getTime();
    var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
    var rowArr = PRODUCT_HEADERS.map(function(h) {
      if (h === 'id') return id;
      if (h === 'updated_at') return now;
      return (item[h] !== undefined && item[h] !== null) ? String(item[h]) : '';
    });
    var foundRow = -1;
    for (var r2 = 1; r2 < data.length; r2++) { if (String(data[r2][0]) === id) { foundRow = r2 + 1; break; } }
    var targetRow = foundRow > 0 ? foundRow : sh.getLastRow() + 1;
    var rng = sh.getRange(targetRow, 1, 1, PRODUCT_HEADERS.length);
    try { rng.setNumberFormat('@'); } catch (e) {}
    rng.setValues([rowArr]);
    return _json({ ok: true, id: id });
  }
  if (action === 'product_plan_delete') {
    var did = String(body.id || '');
    if (!did) return _json({ ok: false, error: 'id 필수' });
    for (var r3 = 1; r3 < data.length; r3++) { if (String(data[r3][0]) === did) { sh.deleteRow(r3 + 1); return _json({ ok: true, id: did }); } }
    return _json({ ok: false, error: '해당 id 없음' });
  }
  return _json({ ok: false, error: '알 수 없는 product_plan action: ' + action });
}

// ═══ GitHub 콘텐츠 파일 중계 (GM 편집 → 자동 커밋·push) — 2026-05-29 ═══
// 보안: ① 커밋 가능 경로는 coo 하위 .json 으로 한정(코드 조작 차단)
//       ② EDIT_KEY 일치 필수  ③ 토큰은 ScriptProperties 서버측 보관(브라우저 비노출)
function _ghHeaders() {
  const token = _prop('GITHUB_TOKEN');
  if (!token) return null;
  return { 'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
}
function _ghUrl(path) {
  const repo = _prop('GITHUB_REPO') || 'wellperion-cao/wellperion-automation';
  const apiPath = String(path).split('/').map(encodeURIComponent).join('/');
  return 'https://api.github.com/repos/' + repo + '/contents/' + apiPath;
}
function _ghPathAllowed(path) {
  // 웰페리온 ERP coo 하위 .json + cmo 검수 큐 .json 만 허용
  var p = String(path);
  if (/^3\. 웰페리온 가이드\/coo\/.+\.json$/.test(p)) return true;
  if (/^3\. 웰페리온 가이드\/cmo\/review\/.+\.json$/.test(p)) return true;
  return false;
}
function _githubReadFile(path) {
  const headers = _ghHeaders();
  if (!headers) return { ok: false, error: 'GITHUB_TOKEN 미설정' };
  if (!_ghPathAllowed(path)) return { ok: false, error: '허용되지 않은 경로' };
  const branch = _prop('GITHUB_BRANCH') || 'master';
  const r = UrlFetchApp.fetch(_ghUrl(path) + '?ref=' + branch, { method: 'get', headers: headers, muteHttpExceptions: true });
  const code = r.getResponseCode();
  if (code === 200) {
    const j = JSON.parse(r.getContentText());
    const text = Utilities.newBlob(Utilities.base64Decode(j.content)).getDataAsString('UTF-8');
    return { ok: true, content: text, sha: j.sha };
  }
  if (code === 404) return { ok: true, content: '', sha: null };  // 아직 없음
  return { ok: false, error: 'GitHub ' + code };
}
function _githubCommitFile(path, contentText, message, key) {
  const headers = _ghHeaders();
  if (!headers) return { ok: false, error: 'GITHUB_TOKEN 미설정 — Apps Script 속성에 추가 필요' };
  const editKey = _prop('EDIT_KEY');
  if (editKey && String(key) !== editKey) return { ok: false, error: '편집 키 불일치' };
  if (!_ghPathAllowed(path)) return { ok: false, error: '허용되지 않은 경로(coo 하위 .json 만 가능)' };
  const branch = _prop('GITHUB_BRANCH') || 'master';
  // 현재 sha 조회 (있으면 갱신, 없으면 신규 생성)
  let sha = null;
  const getR = UrlFetchApp.fetch(_ghUrl(path) + '?ref=' + branch, { method: 'get', headers: headers, muteHttpExceptions: true });
  if (getR.getResponseCode() === 200) sha = JSON.parse(getR.getContentText()).sha;
  const payload = {
    message: message || ('edit via SSOT ' + _now()),
    content: Utilities.base64Encode(contentText, Utilities.Charset.UTF_8),
    branch: branch
  };
  if (sha) payload.sha = sha;
  const putR = UrlFetchApp.fetch(_ghUrl(path), {
    method: 'put', contentType: 'application/json', headers: headers,
    payload: JSON.stringify(payload), muteHttpExceptions: true
  });
  const code = putR.getResponseCode();
  if (code === 200 || code === 201) {
    const j = JSON.parse(putR.getContentText());
    return { ok: true, commit: (j.commit && j.commit.sha) || null, path: path };
  }
  return { ok: false, error: 'GitHub ' + code + ': ' + putR.getContentText().slice(0, 160) };
}

// ═══ 인스타 검수 큐 status 중계 (검수카드 [승인]/[반려] → GitHub 기록) — 2026-05-30 ═══
// review_queue.json 에서 해당 id 의 status 를 승인|반려 로 갱신 후 GitHub commit.
// 토큰은 기존 GITHUB_TOKEN 재사용(서버측 ScriptProperties). 경로는 cmo/review/*.json 만 허용.
function _reviewSetStatus(id, status, key) {
  if (!id) return { ok: false, error: 'id 필수' };
  var allowed = { '승인': true, '반려': true };
  if (!allowed[status]) return { ok: false, error: 'status 는 승인|반려 만 허용' };
  var editKey = _prop('EDIT_KEY');
  if (editKey && String(key) !== editKey) return { ok: false, error: '편집 키 불일치' };
  var path = '3. 웰페리온 가이드/cmo/review/review_queue.json';
  var rf = _githubReadFile(path);
  if (!rf.ok) return { ok: false, error: '큐 읽기 실패: ' + (rf.error || '') };
  var arr;
  try { arr = JSON.parse(rf.content || '[]'); } catch (e) { return { ok: false, error: '큐 JSON 파싱 실패' }; }
  if (!Array.isArray(arr)) return { ok: false, error: '큐 형식 오류(배열 아님)' };
  var found = false, prev = '';
  for (var i = 0; i < arr.length; i++) {
    if (String(arr[i].id) === String(id)) { prev = arr[i].status; arr[i].status = status; found = true; break; }
  }
  if (!found) return { ok: false, error: '해당 id 없음: ' + id };
  var body = JSON.stringify(arr, null, 2) + '\n';
  var msg = 'review: ' + id + ' status ' + (prev || '?') + '→' + status + ' (검수카드 중계)';
  var cr = _githubCommitFile(path, body, msg, key);
  if (!cr.ok) return { ok: false, error: '커밋 실패: ' + (cr.error || '') };
  return { ok: true, id: id, status: status, prev: prev, commit: cr.commit || null };
}

// ─── 텔레그램 알림 전면 폐기 (2026-05-28 GM 결재) — 결재 SSOT 페이지 단일 운영 ───
// 함수 시그니처는 보존 — 향후 복구 시 본체만 복원하면 됨.
function _notifyTelegram(text, opts) {
  return; // no-op
}

// ─── 카테고리 → 부서장 매핑 (결재선 1단계 자동, 2026-06-10 GM 확정 9분류) ───
// 인사·파트너팀=나우열M([2][3]) / 운영부=이경연 실장([4]) / 시설부=이정헌 소장([5]).
// 매핑 없는 카테고리([1][6][7][8][9])는 부서장 생략 → GM→대표 폴백.
var CAT_DEPT_HEAD = {
  '[2] 인사':        '나우열M',
  '[3] 파트너팀':    '나우열M',
  '[4] 운영 정책':   '이경연 실장',
  '[5] 시설 및 환경': '이정헌 소장'
};
function _deptHeadFor(category) { return CAT_DEPT_HEAD[String(category || '')] || ''; }

// ─── 결재 라인 자동 산출 — (명시 체크한 부서장) → GM (2026-06-16 GM: 대표 단계 폐지 / 2026-06-17 COO A: 카테고리 자동 부서장 삽입 폐지) ───
// 중간 결재자: 결재요청에 명시 체크한 부서장만(카테고리 자동삽입 안 함).
// 결재 필요 여부 = 수동 결재요청 또는 예산(BUDGET 마커) 존재.
// 담당자=김남욱GM이면 부서장 단계 생략. GM은 항상 최종.
function _buildApprovalRoute(record) {
  const content = String(record['내용'] || '');
  const hasBudget = /===BUDGET===\s*\n[^|]+\|\s*\d+/.test(content);
  const manual = String(record['결재요청'] || '').split(',').map(s => s.trim()).filter(Boolean);

  // 결재 불필요 → 빈 라인
  if (manual.length === 0 && !hasBudget) return [];

  // 중간 결재자 = 결재요청에 명시 체크한 부서장만. 카테고리 자동 부서장 삽입 폐지(2026-06-17 COO A) — 시설 카테고리라고 소장 자동삽입 안 함.
  var MID = ['이경연 실장','이정헌 소장','나우열M'];
  var owners = String(record['담당자'] || '').split(',').map(function(s){ return s.trim(); });
  var midName = manual.filter(function(m){ return MID.indexOf(m) >= 0; })[0] || '';

  // 표준 결재선: (명시 체크한 부서장) → GM(최종). GM이 라인 마지막 = GM 서명 시 결재완료.
  const ownerIsGM = owners.indexOf('김남욱GM') >= 0;
  const route = [];
  if (midName && !ownerIsGM) route.push('부서장');
  route.push('GM');
  return route;
}

// ─── 결재 알림 (옵션 A · 2026-05-28: 알림 전용 + 페이지 링크) ───
function _sendApprovalCard(record, route, currentRole) {
  if (!currentRole || !route.includes(currentRole)) return;
  const id = record['id'];
  const title = record['업무명'] || '(제목 없음)';
  const owner = record['담당자'] || '-';

  // 예산 한 줄만 표시
  const content = String(record['내용'] || '');
  const budgetMatch = content.match(/===BUDGET===\s*\n([^|]+)\|\s*(\d+)/);
  let budgetLine = '';
  if (budgetMatch) {
    const amt = Number(budgetMatch[2]).toLocaleString('ko-KR');
    budgetLine = '\n💰 ' + budgetMatch[1].trim() + ' · ' + amt + '원';
  }

  const routeViz = route.map(r => r === currentRole ? '<b>[' + r + ']</b>' : r).join(' → ');
  const pageUrl = _prop('APPROVAL_PAGE_URL') ||
    'https://wellperion-cao.github.io/wellperion-automation/coo/todo/%EA%B2%B0%EC%9E%AC%20%ED%98%84%ED%99%A9%20SSOT.html';

  const text =
    '🔔 <b>[결재 요청]</b> ' + currentRole + '님 차례\n' +
    '━━━━━━━━━━━━━━━━\n' +
    '📌 ' + title + '\n' +
    '👤 담당: ' + owner + budgetLine + '\n' +
    '🧭 결재 라인: ' + routeViz + '\n\n' +
    '👉 <a href="' + pageUrl + '">결재 SSOT 페이지 열기</a>\n' +
    '🆔 ' + id;

  _notifyTelegram(text);  // 알림 전용 — 결재는 페이지에서
}

// ─── 결재 라인 다음 단계 산출 ───
// role(현재 서명자) 전달 시: 서명자가 결재선 마지막 단계(=종착, 이제 GM)면
// 앞선 단계에 미서명(phantom: 결재선엔 있으나 실제로 건너뛴 부서장 등)이 있어도
// 최종 완료(null)로 확정한다. → GM 사인 후 결재완료 정합(2026-06-16 시우: 대표 단계 폐지).
function _nextApprover(record, route, role) {
  if (!route || !route.length) return null;
  // 현재 서명자가 결재선 마지막이면 최종 — phantom 미서명에 막히지 않음.
  if (role && route[route.length - 1] === role) return null;
  // 싸인 컬럼 확인 → 미서명 첫 사람
  const map = { '부서장': '부서장싸인', 'GM': 'GM싸인' };
  for (let i = 0; i < route.length; i++) {
    const r = route[i];
    if (!record[map[r]]) return r;
  }
  return null; // 전원 서명 완료
}

// ─── TODO_Files Drive 폴더 확보 (없으면 생성) ───
function _getTodoFolder() {
  let folderId = _prop('TODO_FILES_FOLDER');
  let folder;

  if (folderId) {
    try {
      folder = DriveApp.getFolderById(folderId);
    } catch (e) {
      folder = null;
    }
  }

  if (!folder) {
    // 루트에 'TODO_Files' 폴더 생성
    const existing = DriveApp.getRootFolder().getFoldersByName('TODO_Files');
    if (existing.hasNext()) {
      folder = existing.next();
    } else {
      folder = DriveApp.getRootFolder().createFolder('TODO_Files');
    }
    // 폴더 ID 저장
    PropertiesService.getScriptProperties().setProperty('TODO_FILES_FOLDER', folder.getId());
  }
  return folder;
}

// ─── 파일 업로드 (Base64 → Drive) ───
function _uploadFile(base64, fileName, mimeType) {
  const folder = _getTodoFolder();

  const blob = Utilities.newBlob(
    Utilities.base64Decode(base64),
    mimeType || 'application/octet-stream',
    fileName || 'upload_' + _now().replace(/[: ]/g, '_')
  );
  const file = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return file.getUrl();
}


// ═══════════════════════════════════════════
//  home_kpi — 매출·지출·이슈(VOC) 자동 집계 (읽기 전용) — 2026-06-08 시뽀(CFO)
//  3개 외부 시트를 openById 로 읽어 home 대시보드용 JSON 반환.
//  ⚠️ 읽기 전용 — 어떤 시트도 변형하지 않음. 숫자 못 구하면 해당 필드 null.
// ═══════════════════════════════════════════

// 외부 시트 ID
var KPI_SALES_SHEET_ID   = '1oG63rj17-RMk2cdiVbwp4TOp-yN73uc04jDV7RfN9BI';
// 26년 매출 분석 시트 — 1~5월 월별 마감 총합(AV3:AV7) 출처 (2026-06-20 GM 제공, 시뽀 연동).
// 탭명: '26년 매출 분석' (gid=195790960). AV열 3~7행 = 1월~5월 순서(GM 확인).
var KPI_SALES_ANALYSIS_SHEET_ID = '1gCQNny8TDls5SjrtMkINu4HCltvFkoXmkTeXO_c3q58';
// 연 매출 목표 — GM 결재 2026-06-20, 연 매출 목표 72억(공식값 단일출처). 분석시트에 셀 없어 상수 고정.
var KPI_YEAR_TARGET = 7200000000;
// GM 확정 정본 지출 시트(2026-06-10). 빈 ERP 시트(17R_Sjz…) 아님 — 실제 구매·지출 거래행이 있는 시트.
// '지출 현황' 탭(gid 821406206) = 거래행(승인건 포함) 표면. 첫 탭 자동선택 금지(칸밀림 오판 원인).
var KPI_EXPENSE_SHEET_ID = '1umSF9rf3K0TuAvR5l0F_gvXHxcOLVKKvkSUfTtbRhdc';
var KPI_EXPENSE_GID      = 821406206;
var KPI_VOC_SHEET_ID     = '1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ';
var KPI_VOC_GID          = 1576318230;

// 월 지출 예산 — 1차 출처='지출 현황' 시트의 '예산' 라벨 셀(GM이 시트에서 수시 변경, 재배포 불필요).
// 시트에 '예산' 셀이 없을 때만 이 상수 fallback 사용. 미설정이면 null/0.
var MONTHLY_EXPENSE_BUDGET = 0;

// "12,007,816" · "25.43%" · 숫자 등을 number 로 파싱. 못 구하면 null.
function _kpiNum(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return isNaN(v) ? null : v;
  var s = String(v).replace(/,/g, '').replace(/%/g, '').replace(/[₩원\s]/g, '').trim();
  if (s === '') return null;
  var n = Number(s);
  return isNaN(n) ? null : n;
}

// Date 객체 또는 "2026. 1. 5" · "2026-01-05" 문자열 → {y,m,d} 또는 null
function _kpiParseDate(v) {
  if (v instanceof Date && !isNaN(v.getTime())) {
    return { y: v.getFullYear(), m: v.getMonth() + 1, d: v.getDate() };
  }
  var s = String(v || '').trim();
  if (!s) return null;
  // "2026. 1. 5" / "2026.1.5" / "2026-1-5" / "2026/1/5"
  var m = s.match(/(\d{4})\s*[.\-\/]\s*(\d{1,2})\s*[.\-\/]\s*(\d{1,2})/);
  if (m) return { y: +m[1], m: +m[2], d: +m[3] };
  return null;
}

function _kpiToday() {
  var n = new Date();
  return { y: n.getFullYear(), m: n.getMonth() + 1, d: n.getDate() };
}

// ── 매출 ──
// 월별 탭("N월" 포함) 중 현재 월 탭 자동 선택. 최신 날짜 블록 "총 매출 합계" 행 파싱.
// year = 모든 "N월 매출보고" 탭 각 최신 블록 누적매출 합.

// 라벨 셀(labelCol) 우측에서 비어있지 않은 값 최대 4개를 읽어
// {today, month, target, rate} 로 반환하는 공용 헬퍼.
function _kpiReadBlock(row, labelCol) {
  var nums = [];
  for (var cc = labelCol + 1; cc < row.length && nums.length < 4; cc++) {
    var raw = row[cc];
    if (raw === '' || raw === null || raw === undefined) continue;
    nums.push({ raw: raw, parsed: _kpiNum(raw) });
  }
  if (nums.length < 2) return null;
  var today  = nums[0] ? nums[0].parsed : null;
  var month  = nums[1] ? nums[1].parsed : null;
  var target = nums[2] ? nums[2].parsed : null;
  var rate   = null;
  if (nums[3]) {
    var rraw = String(nums[3].raw || '');
    var rp   = nums[3].parsed;
    if (rp !== null) {
      if (rraw.indexOf('%') < 0 && rp > 0 && rp <= 1) rate = Math.round(rp * 10000) / 100;
      else rate = Math.round(rp * 100) / 100;
    }
  }
  if (rate === null && month !== null && target) rate = Math.round((month / target) * 10000) / 100;
  return { today: today, month: month, target: target, rate: rate };
}

// 팀별 breakdown 대상 라벨 목록 (시트 셀값에 포함되면 매칭)
var BREAKDOWN_LABELS = [
  '회원권 매출', '옵션 매출',
  '수영팀 매출', 'P.T팀 매출', '골프팀 매출',
  '스쿼시팀 매출', '체조팀 매출', 'P.L팀 매출', 'GXE'
];
// 표시 이름 정규화 (셀에 포함된 키 → 짧은 표시명)
var BREAKDOWN_NAME_MAP = {
  '회원권 매출': '회원권', '옵션 매출': '옵션',
  '수영팀 매출': '수영팀', 'P.T팀 매출': 'PT팀', '골프팀 매출': '골프팀',
  '스쿼시팀 매출': '스쿼시팀', '체조팀 매출': '체조팀',
  'P.L팀 매출': 'PL팀', 'GXE': 'GXE'
};

function _kpiParseSalesTab(sheet) {
  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();
  if (lastRow < 2 || lastCol < 2) return null;
  var values = sheet.getRange(1, 1, lastRow, lastCol).getValues();

  // "총 매출 합계" 가 들어간 셀을 모두 찾는다. 가장 오른쪽=최신(이번달) 블록 채택.
  // ⚠ 시트 구조 실측(2026-06-20 시뽀): "보고" 탭 블록은 '월별'이 아니라 '같은 달의
  //   일자별 누적 스냅샷'(예: 6/18 누적·6/19 누적). 따라서 모든 블록 month 를 무지성
  //   합산하면 같은 6월을 중복 더해 가짜 연간(8.33억) 이 나온다. → 블록을 '월(month-of-year)'
  //   기준으로 묶어 월별 최신 1개만 취하고, 그 월별 마감값을 합쳐야 진짜 연간이 된다.
  var best = null; // {r, c} 최신 블록
  var anchors = []; // 모든 "총 매출 합계" 셀 위치
  for (var r = 0; r < values.length; r++) {
    for (var c = 0; c < values[r].length; c++) {
      var cell = String(values[r][c] || '');
      if (cell.indexOf('총 매출 합계') >= 0) {
        anchors.push({ r: r, c: c });
        if (!best || c > best.c) best = { r: r, c: c };
      }
    }
  }
  if (!best) return null;

  // 합계 행 파싱(최신 블록)
  var summary = _kpiReadBlock(values[best.r], best.c);
  if (!summary || summary.month === null) return null;

  // 블록의 '월'을 추정: 같은 컬럼에서 위로 스캔해 날짜형 셀("26. 6. 19" / "2026-06-19")의
  //   월(month) 숫자를 읽는다. 못 찾으면 null.
  function _blockMonthOf(anchorR, anchorC) {
    for (var rr = anchorR; rr >= 0 && rr > anchorR - 12; rr--) {
      for (var cc = anchorC; cc < anchorC + 6 && cc < values[rr].length; cc++) {
        var sv = String(values[rr][cc] || '').trim();
        if (!sv) continue;
        // "2026. 6. 19" / "2026-6-19" 형
        var m4 = sv.match(/\d{4}\s*[.\-\/]\s*(\d{1,2})\s*[.\-\/]\s*\d{1,2}/);
        if (m4) return +m4[1];
        // "26. 6. 19(금)" / "26.6.19" 형 (2자리 연도)
        var m2 = sv.match(/\b\d{2}\s*[.\-\/]\s*(\d{1,2})\s*[.\-\/]\s*\d{1,2}/);
        if (m2) return +m2[1];
      }
    }
    return null;
  }

  // 연간 누적 = '서로 다른 월'의 마감값만 합산. 같은 달의 일자별 스냅샷은
  //   가장 오른쪽(=최신) 1개만 채택해 중복 합산을 막는다.
  // 데이터가 1개 월뿐이면(=1~5월 마감값 부재) 연간은 '집계 보완 중'(null) 으로 정직 표기.
  var monthBlocks = {}; // monthOfYear → {c, month}
  var unknownMonth = false;
  for (var ai = 0; ai < anchors.length; ai++) {
    var ablk = _kpiReadBlock(values[anchors[ai].r], anchors[ai].c);
    if (!ablk || ablk.month === null) continue;
    var moy = _blockMonthOf(anchors[ai].r, anchors[ai].c);
    if (moy === null) { unknownMonth = true; continue; }
    // 같은 달은 더 오른쪽(최신) 블록으로 덮어쓴다.
    if (!monthBlocks[moy] || anchors[ai].c > monthBlocks[moy].c) {
      monthBlocks[moy] = { c: anchors[ai].c, month: ablk.month };
    }
  }
  var distinctMonths = [];
  for (var mk in monthBlocks) { if (monthBlocks.hasOwnProperty(mk)) distinctMonths.push(mk); }
  var yearSum = 0;
  for (var dm = 0; dm < distinctMonths.length; dm++) yearSum += monthBlocks[distinctMonths[dm]].month;
  // 진짜 연간으로 인정하는 조건: 서로 다른 월이 2개 이상 (월 마감 누적이 실제로 쌓였을 때).
  //   월이 1개뿐이거나(=6월만), 월 식별 불가 블록이 섞였으면 → 연간 null(보완 중).
  var yearValid = (distinctMonths.length >= 2) && !unknownMonth;

  // 최신 블록 기준 컬럼(best.c). 같은 컬럼에서 아래 행들을 스캔해 breakdown 추출.
  // 최대 15행 아래까지만 탐색 (블록 범위 이탈 방지).
  var breakdown = [];
  var seen = {};
  for (var ri = best.r + 1; ri < Math.min(best.r + 16, values.length); ri++) {
    var labelCell = String(values[ri][best.c] || '').trim();
    for (var li = 0; li < BREAKDOWN_LABELS.length; li++) {
      var key = BREAKDOWN_LABELS[li];
      if (labelCell.indexOf(key) >= 0 && !seen[key]) {
        seen[key] = true;
        var blk = _kpiReadBlock(values[ri], best.c);
        if (blk) {
          var displayName = BREAKDOWN_NAME_MAP[key] || key;
          breakdown.push({
            name:   displayName,
            today:  blk.today,
            month:  blk.month,
            target: blk.target,
            rate:   blk.rate
          });
        }
        break;
      }
    }
  }

  return {
    today: summary.today, month: summary.month,
    target: summary.target, rate: summary.rate,
    // 월 매출/달성률: month=월누적·rate=월 달성률(시트 "총 매출 합계" 행). 항상 유효.
    // 연간 매출: 서로 다른 월 2개+ 마감값이 쌓였을 때만 합산값, 아니면 null(=홈에서 '집계 보완 중').
    year: yearValid ? yearSum : null,
    breakdown: breakdown
  };
}

// 실측 구조(2026-06-08·재확인 2026-06-20): 매출 시트는 월별 탭이 아니라 단일 "보고" 탭 안에서
// 날짜별 컬럼 블록이 가로로 반복(각 블록 7컬럼). 최신=가장 오른쪽 블록.
// "총 매출 합계" 행의 우측 4칸 = 금일|월누적|월목표|월달성률. → _kpiParseSalesTab 재사용.
// ▶ 월 매출/달성률: month=월누적(예 423,857,058)·rate=월 달성률(예 71.72%). 데이터 있음 → 항상 산출.
// ▶ 연간 매출/달성률: 블록이 '같은 달의 일자별 스냅샷'이라 무지성 합산 시 6월 중복 → 가짜 연간(8.33억).
//   _kpiParseSalesTab 이 블록을 '월'로 묶어 월별 최신 1개만 취하고 서로 다른 월 2개+ 일 때만 합산.
//   현재 시트엔 6월만 존재(1~5월 마감값·연 목표 부재) → year=null → 홈에서 '집계 보완 중' 정직 표기.
//   (2026-06-10 시토 year=month 버그 / 2026-06-20 시뽀 같은달 중복합산 8.33억 버그 제거)
// 주차 매출 breakdown 행 — 크롤러가 매일 발행하는 라이브 JSON 직독(2026-06-19 시토).
// status/parking_revenue.json(payAmt 합=카드 총 정산액)을 raw GitHub에서 읽어 {name:'주차', month}.
// 실패(404·파싱오류·status!=정상)는 null → 홈 KPI에 무영향(fail-safe). 시트 비의존.
function _kpiParkingRevenueRow() {
  try {
    var url = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/status/parking_revenue.json';
    var resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true });
    if (resp.getResponseCode() !== 200) return null;
    var j = JSON.parse(resp.getContentText());
    if (!j || j.status !== '정상') return null;
    var amt = Number(j['매출금액']);
    if (isNaN(amt)) return null;
    return { name: '주차', today: null, month: amt, target: null, rate: null };
  } catch (e) { return null; }
}

function _kpiSales() {
  try {
    var ss = SpreadsheetApp.openById(KPI_SALES_SHEET_ID);
    // 우선순위: "보고" 탭 → "총 매출 합계" 포함 탭 자동탐지
    var tab = ss.getSheetByName('보고');
    if (!tab) {
      var sheets = ss.getSheets();
      for (var i = 0; i < sheets.length; i++) {
        var p0 = _kpiParseSalesTab(sheets[i]);
        if (p0 && p0.month !== null) { tab = sheets[i]; break; }
      }
    }
    var cur = tab ? _kpiParseSalesTab(tab) : null;
    if (!cur) return { today: null, month: null, year: null, target: null, rate: null, breakdown: [] };
    // 연간 매출 = 서로 다른 월 마감값 합(_kpiParseSalesTab.year). 1개 월뿐이면 null(보완 중).
    //   ⚠ null 을 month 로 덮어쓰지 않는다 — 같은 달 중복합산 가짜 연간 방지(2026-06-20 시뽀).
    var year = (cur.year !== null && cur.year !== undefined) ? cur.year : null;
    // 연간 매출 보완 — 26년 매출 분석 시트 AV3:AV7 (1~5월 월별 마감 총합, GM 2026-06-20 제공).
    // 기존 시트(KPI_SALES_SHEET_ID)는 6월 단일이라 year=null. 분석 시트에서 1~5월 합을 읽어 보완.
    // AV열 3~7행 = 1~5월 순서(행3=1월·행7=5월, GM 확인). 빈 셀·0은 합산 제외.
    // 6월 month(cur.month)가 있으면 연간 = 1~5월합 + 6월month. 어느 하나라도 없으면 null 유지.
    // 연 목표 = GM 결재 2026-06-20 확정 72억(KPI_YEAR_TARGET 상수). 분석시트에 셀 없어 상수 단일출처.
    var yearTarget = KPI_YEAR_TARGET || null;
    var yearRate = null;
    try {
      if (year === null && cur.month !== null && KPI_SALES_ANALYSIS_SHEET_ID) {
        var anaSs = SpreadsheetApp.openById(KPI_SALES_ANALYSIS_SHEET_ID);
        var anaTab = anaSs.getSheetByName('26년 매출 분석');
        if (anaTab) {
          // AV = 48번째 컬럼. getRange(row, col, numRows, numCols)
          var avVals = anaTab.getRange(3, 48, 5, 1).getValues(); // AV3:AV7
          var sum15 = 0;
          var validMonths = 0;
          for (var ai = 0; ai < avVals.length; ai++) {
            var v = _kpiNum(avVals[ai][0]);
            if (v !== null && v > 0) { sum15 += v; validMonths++; }
          }
          // 1~5월 중 1개라도 유효한 값이 있으면 보완 진행
          if (validMonths > 0) {
            year = sum15 + cur.month; // 1~5월 마감합 + 6월 현재 누적
          }
        }
      }
    } catch (anaErr) {
      // 분석 시트 오류는 무시 — year null 유지(집계 보완 중 표시)
    }
    // 연 달성률: year 있고 yearTarget 있을 때만 산출. Math.round 소수점1자리.
    yearRate = (year !== null && yearTarget) ? Math.round((year / yearTarget) * 1000) / 10 : null;
    // 주차 매출을 breakdown 'GXE' 행 바로 아래에 삽입(없으면 맨 끝). 시트 총합/hero 값은 불변.
    var bd = cur.breakdown || [];
    var park = _kpiParkingRevenueRow();
    if (park) {
      var gi = -1;
      for (var bi = 0; bi < bd.length; bi++) { if (bd[bi].name === 'GXE') { gi = bi; break; } }
      if (gi >= 0) bd.splice(gi + 1, 0, park); else bd.push(park);
    }
    return { today: cur.today, month: cur.month, year: year,
             target: cur.target, rate: cur.rate,
             yearTarget: yearTarget, yearRate: yearRate,
             breakdown: bd };
  } catch (err) {
    return { today: null, month: null, year: null, target: null, rate: null,
             yearTarget: null, yearRate: null, error: String(err) };
  }
}

// ── 지출 ── (2026-06-10 시토·시뽀: GM 확정 정본 '지출 현황' 탭으로 재연결)
// 시트 1umSF… '지출 현황' 탭(gid 821406206) = 구매·지출 거래행 표면. 컬럼 구조(1-base):
//   1 날짜 · 2 타임스탬프 · 3 구매요청자 · 4 소속 · 5 물품명 · 6 링크 · 7 가격 · 8 목적
//   · 9 승인자 · 10 비고 · 11 이미지 · 12 "구매 진행상황"(=승인/미승인/캔슬) · 13 승인날짜 …
// 헤더에서 날짜·가격·진행상황 컬럼을 키워드로 탐지(고정 인덱스 의존 금지).
// 합산 규칙: 진행상황이 정확히 '승인'인 행만(='미승인'·'캔슬' 제외). 가격 음수(환불·반품)는
//   그대로 차감 — 시트의 월별 '승인건' 합계(예: 2026-06=5,907,240, 골프 -257,760 포함)와 일치.
// 거래행 아래 부서별·월별 요약 블록은 1열이 날짜가 아니므로 _kpiParseDate 가드로 자동 제외.
// '지출 현황' 탭 values 에서 '예산'(또는 '월 예산'·'월예산') 라벨 셀을 찾아 우측 첫 숫자값 반환.
// 라벨과 같은 행 우측 셀(오른쪽으로 스캔) 우선, 없으면 바로 아래 셀. 못 찾으면 null.
function _kpiExpenseBudget(values) {
  for (var r = 0; r < values.length; r++) {
    for (var c = 0; c < values[r].length; c++) {
      var cell = String(values[r][c] || '').replace(/\s/g, '');
      if (cell === '예산' || cell === '월예산' || cell === '월간예산' || cell.indexOf('월예산') >= 0) {
        // 같은 행 우측 스캔
        for (var cc = c + 1; cc < values[r].length; cc++) {
          var rv = _kpiNum(values[r][cc]);
          if (rv !== null && rv > 0) return rv;
        }
        // 바로 아래 셀
        if (r + 1 < values.length) {
          var dv = _kpiNum(values[r + 1][c]);
          if (dv !== null && dv > 0) return dv;
        }
      }
    }
  }
  return null;
}

// 진단 — '지출 현황' 탭의 월별 승인지출 합계(YYYY-MM → 합). 예산 산정 근거용.
// GET ?action=expense_monthly → { ok, months:[{ym, sum, count}], avg3, avg6, max }
function _kpiExpenseMonthly() {
  try {
    var ss = SpreadsheetApp.openById(KPI_EXPENSE_SHEET_ID);
    var sheets = ss.getSheets();
    var sh = null;
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === KPI_EXPENSE_GID) { sh = sheets[i]; break; }
    }
    if (!sh) return _json({ ok: false, error: 'expense_tab_not_found' });
    var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
    var values = sh.getRange(1, 1, lastRow, lastCol).getValues();
    var hdr = values[0].map(function (h) { return String(h || '').replace(/\s/g, '').trim(); });
    function _col(names) {
      for (var i2 = 0; i2 < hdr.length; i2++) {
        for (var j = 0; j < names.length; j++) { if (hdr[i2].indexOf(names[j]) >= 0) return i2; }
      }
      return -1;
    }
    var dateCol = _col(['날짜']), priceCol = _col(['가격', '금액']), statusCol = _col(['진행상황', '승인상태']);
    var agg = {};
    for (var r = 1; r < values.length; r++) {
      var row = values[r];
      var st = String(row[statusCol] || '').replace(/\s/g, '').trim();
      if (st !== '승인') continue;
      var d = _kpiParseDate(row[dateCol]);
      if (!d) continue;
      var price = _kpiNum(row[priceCol]);
      if (price === null) continue;
      var ym = d.y + '-' + ('0' + d.m).slice(-2);
      if (!agg[ym]) agg[ym] = { ym: ym, sum: 0, count: 0 };
      agg[ym].sum += price; agg[ym].count++;
    }
    var months = [];
    for (var k in agg) { if (agg.hasOwnProperty(k)) months.push(agg[k]); }
    months.sort(function (a, b) { return a.ym < b.ym ? -1 : 1; });
    function avgLast(n) {
      var arr = months.slice(-n); if (!arr.length) return null;
      var s = 0; for (var i3 = 0; i3 < arr.length; i3++) s += arr[i3].sum;
      return Math.round(s / arr.length);
    }
    var maxSum = 0; for (var m2 = 0; m2 < months.length; m2++) if (months[m2].sum > maxSum) maxSum = months[m2].sum;
    return _json({ ok: true, months: months, avg3: avgLast(3), avg6: avgLast(6), max: maxSum });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

// '지출 현황' 탭에 '예산' 라벨+금액 기록(idempotent). 라벨 셀이 이미 있으면 그 우측에 덮어씀.
// 없으면 헤더 우측 여백(데이터 영역 밖, 1행)에 '예산' | 금액 신설. POST ?action=expense_set_budget&amount=...&key=...
function _expenseSetBudget(amount, key) {
  try {
    var editKey = _prop('EDIT_KEY');
    if (editKey && String(key) !== editKey) return _json({ ok: false, error: '편집 키 불일치' });
    var amt = _kpiNum(amount);
    if (amt === null || amt <= 0) return _json({ ok: false, error: 'invalid_amount' });
    var ss = SpreadsheetApp.openById(KPI_EXPENSE_SHEET_ID);
    var sheets = ss.getSheets();
    var sh = null;
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === KPI_EXPENSE_GID) { sh = sheets[i]; break; }
    }
    if (!sh) return _json({ ok: false, error: 'expense_tab_not_found' });
    var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
    var values = sh.getRange(1, 1, lastRow, lastCol).getValues();
    // 기존 '예산' 라벨 셀 탐색
    for (var r = 0; r < values.length; r++) {
      for (var c = 0; c < values[r].length; c++) {
        var cell = String(values[r][c] || '').replace(/\s/g, '');
        if (cell === '예산' || cell === '월예산' || cell === '월간예산') {
          sh.getRange(r + 1, c + 2).setValue(amt);  // 라벨 우측 셀에 기록
          return _json({ ok: true, mode: 'updated', row: r + 1, col: c + 2, amount: amt });
        }
      }
    }
    // 없으면 헤더행(1행) 우측 여백에 '예산' | 금액 신설
    var lbl = lastCol + 2;  // 데이터 영역과 한 칸 띄움
    sh.getRange(1, lbl).setValue('예산');
    sh.getRange(1, lbl + 1).setValue(amt);
    return _json({ ok: true, mode: 'created', row: 1, col: lbl + 1, amount: amt });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function _kpiExpense() {
  try {
    var ss = SpreadsheetApp.openById(KPI_EXPENSE_SHEET_ID);
    var sheets = ss.getSheets();
    var sh = null;
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === KPI_EXPENSE_GID) { sh = sheets[i]; break; }
    }
    if (!sh) {
      // gid 미발견 → 이름 추정('지출 현황' 포함). 첫 탭 자동선택은 칸밀림 오판 원인 → 최후수단.
      for (var k = 0; k < sheets.length; k++) {
        if (sheets[k].getName().replace(/\s/g, '').indexOf('지출현황') >= 0) { sh = sheets[k]; break; }
      }
    }
    if (!sh) return { today: null, month: null, year: null, budget: null, rate: null,
                      error: 'expense_tab_not_found' };
    var lastRow = sh.getLastRow();
    var lastCol = sh.getLastColumn();
    if (lastRow < 2 || lastCol < 2) {
      return { today: null, month: null, year: null, budget: null, rate: null };
    }
    var values = sh.getRange(1, 1, lastRow, lastCol).getValues();
    var hdr = values[0].map(function (h) { return String(h || '').replace(/\s/g, '').trim(); });
    function _col(names) {
      for (var i2 = 0; i2 < hdr.length; i2++) {
        for (var j = 0; j < names.length; j++) {
          if (hdr[i2].indexOf(names[j]) >= 0) return i2;
        }
      }
      return -1;
    }
    var dateCol   = _col(['날짜']);
    var priceCol  = _col(['가격', '금액']);
    var statusCol = _col(['진행상황', '승인상태']);
    var deptCol   = _col(['소속', '부서']);  // 부서별 breakdown용(없으면 -1 → '기타')
    if (priceCol < 0 || statusCol < 0 || dateCol < 0) {
      return { today: null, month: null, year: null, budget: null, rate: null,
               error: 'expense_cols_not_found' };
    }
    var t = _kpiToday();
    var today = 0, month = 0, year = 0, any = false;
    var deptMonth = {};  // 부서명 → 이번달 승인지출 합
    for (var r = 1; r < values.length; r++) {
      var row = values[r];
      // 진행상황이 정확히 '승인'인 행만. '미승인'·'캔슬'은 제외(부분일치 금지).
      var st = String(row[statusCol] || '').replace(/\s/g, '').trim();
      if (st !== '승인') continue;
      var d = _kpiParseDate(row[dateCol]);
      if (!d) continue;  // 거래행이 아님(요약 블록 등) → 제외
      var price = _kpiNum(row[priceCol]);
      if (price === null) continue;  // 음수(환불)는 유지, 빈 값만 제외
      any = true;
      if (d.y === t.y) {
        year += price;
        if (d.m === t.m) {
          month += price;
          if (d.d === t.d) today += price;
          // 이번달 부서별 합산(소속 4열). 빈 소속은 '기타'.
          var dept = (deptCol >= 0) ? String(row[deptCol] || '').trim() : '';
          if (!dept) dept = '기타';
          deptMonth[dept] = (deptMonth[dept] || 0) + price;
        }
      }
    }
    // 부서별 breakdown — 이번달 합 큰 순. share=부서합/month(비중%). 매출 breakdown과 동형.
    var breakdown = [];
    for (var dn in deptMonth) {
      if (!deptMonth.hasOwnProperty(dn)) continue;
      breakdown.push({
        name:  dn,
        month: deptMonth[dn],
        share: (month !== 0) ? Math.round((deptMonth[dn] / month) * 10000) / 100 : null
      });
    }
    breakdown.sort(function (a, b) { return b.month - a.month; });
    // 예산 — '지출 현황' 시트의 '예산' 라벨 셀 우측값 우선, 없으면 상수 fallback.
    var budget = _kpiExpenseBudget(values);
    if (budget === null && MONTHLY_EXPENSE_BUDGET && MONTHLY_EXPENSE_BUDGET > 0) {
      budget = MONTHLY_EXPENSE_BUDGET;
    }
    var rate = (budget && budget > 0) ? Math.round((month / budget) * 10000) / 100 : null;
    if (!any) return { today: null, month: null, year: null, budget: budget, rate: rate, breakdown: [] };
    return { today: today, month: month, year: year, budget: budget, rate: rate, breakdown: breakdown };
  } catch (err) {
    return { today: null, month: null, year: null, budget: null, rate: null, error: String(err) };
  }
}

// ── 이슈(VOC) ──
// gid 로 탭 찾고, 타임스탬프·진행 상황 컬럼 탐지.
// todayNew/done/pending/rate.
function _kpiVoc() {
  try {
    var ss = SpreadsheetApp.openById(KPI_VOC_SHEET_ID);
    var sheets = ss.getSheets();
    var sh = null;
    for (var i = 0; i < sheets.length; i++) {
      if (sheets[i].getSheetId() === KPI_VOC_GID) { sh = sheets[i]; break; }
    }
    if (!sh) {
      // gid 미발견 → 이름 추정(응답/VOC/이슈 포함)
      for (var k = 0; k < sheets.length; k++) {
        var nm = sheets[k].getName();
        if (/응답|VOC|이슈/i.test(nm)) { sh = sheets[k]; break; }
      }
    }
    if (!sh) sh = sheets[0];
    var lastRow = sh.getLastRow();
    var lastCol = sh.getLastColumn();
    if (lastRow < 2 || lastCol < 2) {
      return { todayNew: null, pending: null, done: null, rate: null };
    }
    var values = sh.getRange(1, 1, lastRow, lastCol).getValues();
    var hdr = values[0].map(function (h) { return String(h || '').trim(); });
    function _col(names) {
      for (var i2 = 0; i2 < hdr.length; i2++) {
        for (var j = 0; j < names.length; j++) {
          if (hdr[i2].indexOf(names[j]) >= 0) return i2;
        }
      }
      return -1;
    }
    var tsCol     = _col(['타임스탬프', '타임 스탬프', '제출 시간', '제출시간']);
    var statusCol = _col(['진행 상황', '진행상황']);
    var t = _kpiToday();
    var total = 0, todayNew = 0, done = 0;
    for (var r = 1; r < values.length; r++) {
      var row = values[r];
      // 유효행 판정: 타임스탬프 또는 어떤 값이라도 있어야
      var hasTs = tsCol >= 0 && row[tsCol] !== '' && row[tsCol] !== null;
      var rowHasData = row.some(function (c) { return c !== '' && c !== null && c !== undefined; });
      if (!rowHasData) continue;
      total++;
      if (hasTs) {
        var d = _kpiParseDate(row[tsCol]);
        if (d && d.y === t.y && d.m === t.m && d.d === t.d) todayNew++;
      }
      if (statusCol >= 0) {
        var stv = String(row[statusCol] || '');
        if (stv.indexOf('완료') >= 0) done++;
      }
    }
    var pending = total - done;
    var rate = total > 0 ? Math.round((done / total) * 10000) / 100 : null;
    if (total === 0) return { todayNew: null, pending: null, done: null, rate: null };
    return { todayNew: todayNew, pending: pending, done: done, rate: rate };
  } catch (err) {
    return { todayNew: null, pending: null, done: null, rate: null, error: String(err) };
  }
}

function _homeKpi() {
  var sales   = _kpiSales();
  var expense = _kpiExpense();
  var voc     = _kpiVoc();
  return _json({
    ok: true,
    sales: sales,
    expense: expense,
    voc: voc,
    asOf: _now()
  });
}

// ═══════════════════════════════════════════
//  gm_hangro — G1 '오늘의 항로' 서버 단일 머지 엔진 (2026-06-11 시토 · G1 신뢰성 고도화 ②a)
//  ─────────────────────────────────────────────────────────────────────────────
//  ⚠️ 추가만(미사용·비파괴). 기존 action·G1 JS·daily_scheduler·ceo_morning_pipeline 절대 미변경.
//  현행 G1 머지 JS(wellperion_guide(main).html 7300~7460·7700~7745)를 GAS로 1:1 미러링.
//  시트(todo_list) + _queue.json(raw GitHub, UrlFetchApp)을 서버에서 읽어 동일 결과 산출.
//  ②c 라이브 검증 후 G1·텔레그램·08:00 파이프라인을 이 엔드포인트로 하나씩 전환.
//
//  [G1 라인 ↔ GAS 로직 매핑표]
//   G1 7298-7306 ssotDateLocal      → _gmHangroDateLocal
//   G1 7308-7309 GM1_QUEUE_URL       → GM_HANGRO_QUEUE_URL
//   G1 7314-7333 gm1NextApprover     → _gmHangroNextApprover (GM1_DEPT_HEADS·GM1_CAT_DEPT_HEAD 동일)
//   G1 7350-7419 시트 항목 머지       → _gmHangroBuildItems ① 루프 (needsGm·inflight·일반 분기 동일)
//   G1 7375 _isG1Owner(GM+AI C레벨)   → _gmHangroIsG1Owner
//   G1 7398-7416 완료일 우선·slice(0,10) → 동일(완료일→결재완료시각→'' / new Date 변환 금지)
//   G1 7421-7454 _queue 머지(PENDING·IN_PROGRESS·DONE·폐기) → _gmHangroBuildItems ② 루프 + dedup(_sheetsId)
//   G1 7729-7746 active/done/donePast/hold/apprGm/inflight 분류 → _gmHangroClassify
//   G1 7736-7737 오늘 입항 vs 지난 입항(_doneDate===todayStr) → 동일(.slice(0,10) 날짜 비교)
//
//  ※ _queue.json 은 GAS가 raw GitHub 로 직접 읽음(공개 URL · 인증 불필요) → 시트+큐 병합 모두 서버에서.
//    fetch 실패 시 큐 빈 배열로 폴백(시트분만 — G1 동일 동작). 응답 메타에 queueOk 플래그로 명시.
// ═══════════════════════════════════════════
var GM_HANGRO_QUEUE_URL = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/status/_queue.json';
var GM_HANGRO_DEPT_HEADS = ['이경연 실장', '이정헌 소장', '나우열M'];
var GM_HANGRO_CAT_DEPT_HEAD = { '[2] 인사': '나우열M', '[3] 파트너팀': '나우열M', '[4] 운영 정책': '이경연 실장', '[5] 시설 및 환경': '이정헌 소장' };

// G1 ssotDateLocal 미러 — 시트값 → 'YYYY-MM-DD'(KST). ISO/Date 모두 앞 10자.
function _gmHangroDateLocal(v) {
  if (!v) return '';
  if (v instanceof Date && !isNaN(v.getTime())) {
    return Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
  }
  var s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  var d = new Date(s);
  if (isNaN(d.getTime())) return s.slice(0, 10);
  return Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd');
}

// G1 gm1NextApprover 미러 — '지금 누구 차례'(부서장/GM) 또는 null(전원 완료·결재선 없음). 대표 단계 폐지(2026-06-16).
function _gmHangroNextApprover(row) {
  var approval = String(row['결재요청'] || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
  if (!approval.length) return null;
  var owners = String(row['담당자'] || '').split(',').map(function (s) { return s.trim(); });
  var ownerIsGM = owners.indexOf('김남욱GM') >= 0;
  // 중간 결재자 = 결재요청에 명시 체크한 부서장만. 카테고리 자동 부서장 삽입 폐지(2026-06-17 COO A). 프론트 gm1NextApprover와 정합.
  var midName = approval.filter(function (m) { return GM_HANGRO_DEPT_HEADS.indexOf(m) >= 0; })[0] || '';
  var route = [];
  if (midName && !ownerIsGM) route.push('부서장');
  route.push('GM');
  var map = { '부서장': row['부서장싸인'], 'GM': row['GM싸인'] };
  for (var i = 0; i < route.length; i++) { if (!map[route[i]]) return route[i]; }
  return null;
}

// G1 _isG1Owner 미러 — GM 본인 + AI C레벨(영문직책·닉네임)만 항로 합류.
function _gmHangroIsG1Owner(owner) {
  return owner.indexOf('김남욱GM') >= 0
    || /AI (CEO|CMO|CTO|COO|CFO|CPO|CHRO)/.test(owner)
    || /웰리|시모|시토|시우|시뽀|시포|시로/.test(owner);
}

// 시트행 + 큐를 G1 동일 규칙으로 머지 → 항목 배열. (G1 gm1FetchSsot 본문 미러)
function _gmHangroBuildItems(rows, queue) {
  var items = [];

  // ── ① 시트 항목 ──
  (rows || []).forEach(function (row) {
    var owner = String(row['담당자'] || '');
    var title = String(row['업무명'] || '').trim();
    if (!title) return;
    var apr = String(row['결재상태'] || '');
    var sd = _gmHangroDateLocal(row['시작일']);
    var ed = _gmHangroDateLocal(row['종료일']);
    var reqStr = String(row['결재요청'] || '');
    var _next = _gmHangroNextApprover(row);
    var _aprPending = String(reqStr).trim() !== '' && apr !== '결재완료' && !/반려/.test(apr);
    var needsGm = _aprPending && _next === 'GM';
    var _aprInflightOther = _aprPending && _next !== null && _next !== 'GM';
    var base = 'ssot-' + (row['id'] || title);
    var _isG1Owner = _gmHangroIsG1Owner(owner);

    if (needsGm) {
      items.push({
        id: base, title: (/\[결재\]/.test(title) ? title : '[결재] ' + title), status: '진행중',
        category: '결재', _apprKind: 'gm',
        isToday: true, startDate: sd, endDate: ed, ssotAuto: true, owner: owner,
        _sheetsId: String(row['id'] || '')
      });
    } else if (_aprInflightOther && _isG1Owner) {
      items.push({
        id: base, title: (/\[결재\]/.test(title) ? title : '[결재] ' + title), status: '진행중',
        category: '결재', _apprKind: 'inflight', _nextApprover: _next,
        apprReq: reqStr, apprStatus: apr,
        isToday: true, startDate: sd, endDate: ed, ssotAuto: true, owner: owner,
        _sheetsId: String(row['id'] || '')
      });
    } else if (_isG1Owner) {
      var st = String(row['상태'] || '');
      // 완료일(우선) → 결재완료시각(레거시) → ''(지난 입항으로 안전 분류). slice(0,10) — new Date 변환 금지.
      var _doneRaw = String(row['완료일'] || '').trim() || row['결재완료시각'] || '';
      if (_doneRaw instanceof Date && !isNaN(_doneRaw.getTime())) {
        _doneRaw = Utilities.formatDate(_doneRaw, 'Asia/Seoul', 'yyyy-MM-dd');
      }
      var _doneLocal = _doneRaw ? String(_doneRaw).trim().slice(0, 10) : '';
      var status = (st === '완료') ? '완료' : (st === '보류') ? '보류' : '진행중';
      items.push({
        id: base, title: title, status: status,
        category: '업무',
        apprReq: String(row['결재요청'] || ''), apprStatus: apr,
        isToday: true, startDate: sd, endDate: ed, ssotAuto: true, owner: owner,
        _doneDate: (st === '완료') ? _doneLocal : '',
        _history: false,
        _sheetsId: String(row['id'] || '')
      });
    }
  });

  // ── ② _queue.json AI 진행배 머지 (PENDING·IN_PROGRESS·DONE·폐기) ──
  var sheetIds = {};
  items.forEach(function (it) { if (it._sheetsId) sheetIds[it._sheetsId] = true; });
  var CLEVEL_LABEL = { ceo: 'AI CEO', cmo: 'AI CMO', cto: 'AI CTO', coo: 'AI COO', cfo: 'AI CFO', cpo: 'AI CPO', chro: 'AI CHRO' };
  (queue || []).forEach(function (q) {
    var _qActive = (q.status === 'PENDING' || q.status === 'IN_PROGRESS');
    var _qHist = (q.status === 'DONE' || q.status === '완료' || q.status === '폐기');
    if (!_qActive && !_qHist) return;
    var tid = String(q.task_id || '');
    if (!tid) return;
    if (sheetIds[tid]) return;
    var qid = 'queue-' + tid;
    if (items.some(function (it) { return it.id === qid; })) return;
    var clvLabel = CLEVEL_LABEL[String(q.clevel || '').toLowerCase()] || String(q.clevel || 'AI');
    var statusMap = { PENDING: '대기', IN_PROGRESS: '진행중', DONE: '완료' };
    var _qDone = (q.status === 'DONE' || q.status === '완료');
    items.push({
      id: qid,
      title: String(q.title || tid),
      status: (q.status === '폐기') ? '폐기' : (statusMap[q.status] || '진행중'),
      category: '업무',
      description: String(q.next || q.summary || ''),
      isToday: true,
      ssotAuto: true,
      queueSource: true,
      owner: clvLabel,
      _doneDate: _qDone ? String(q.processed_at || '').slice(0, 10) : '',
      _history: (q.status === '폐기'),
      _sheetsId: ''
    });
  });

  return items;
}

// G1 분류 미러 — 활성 항로/오늘 입항/지난 입항/보류/GM 결재차례/결재 진행중. (G1 7729-7746)
function _gmHangroClassify(items, todayStr) {
  function _apprPending(t) {
    var rq = String(t.apprReq || t.approval || '').trim(), a = String(t.apprStatus || '').trim();
    return rq && a !== '결재완료' && !/반려/.test(a);
  }
  var apprWait = items.filter(function (t) { return t.status === '완료' && _apprPending(t); });
  var active = items.filter(function (t) { return t.status === '진행중'; });
  var doneAll = items.filter(function (t) { return t.status === '완료' && !_apprPending(t); });
  var done = doneAll.filter(function (t) { return (t._doneDate || '') === todayStr; });   // 오늘 입항
  var donePast = doneAll.filter(function (t) { return (t._doneDate || '') !== todayStr; }); // 지난 입항
  var hold = items.filter(function (t) { return t.status === '보류'; });
  var disposed = items.filter(function (t) { return t.status === '폐기'; });
  var apprActiveGm = active.filter(function (t) { return t.category === '결재' && t._apprKind !== 'inflight'; });
  var apprInflight = active.filter(function (t) { return t.category === '결재' && t._apprKind === 'inflight'; });
  active = active.filter(function (t) { return t.category !== '결재'; });
  return {
    active: active,                                  // 활성 항로(결재배 제외)
    done: done,                                      // 🏁 오늘 완료 (아이콘 표준 A안)
    donePast: donePast,                              // 🗄️ 지난 완료
    hold: hold,                                      // 보류
    disposed: disposed,                              // 폐기(검색 전용)
    apprGm: apprActiveGm.concat(apprWait),           // GM이 지금 결재할 차례
    apprInflight: apprInflight,                      // 결재 진행 중(부서장·대표 대기)
    apprGmTotal: apprWait.length + apprActiveGm.length,
    apprInflightTotal: apprInflight.length
  };
}

// 메인 — gm_hangro: 시트+큐 서버 머지 → 분류된 항로 JSON. {ok,count,data} 봉투 준수.
function _gmHangro() {
  try {
    var sh = initTodoSheet();
    var rows = _readAll(sh);
    var queue = [];
    var queueOk = false;
    try {
      var qr = UrlFetchApp.fetch(GM_HANGRO_QUEUE_URL + '?_=' + Date.now(), { muteHttpExceptions: true });
      if (qr.getResponseCode() === 200) {
        var parsed = JSON.parse(qr.getContentText());
        if (Array.isArray(parsed)) { queue = parsed; queueOk = true; }
      }
    } catch (qe) { queue = []; queueOk = false; }  // 큐 실패 → 시트분만(G1 동일 폴백)

    var items = _gmHangroBuildItems(rows, queue);
    var td = _today();  // KST 'yyyy-MM-dd' — G1 todayStr() 동일 기준
    var c = _gmHangroClassify(items, td);

    return _json({
      ok: true,
      count: items.length,
      data: items,            // 머지·분류 전 전체 항목(G1 gm1SsotItems 동등)
      buckets: c,             // 분류 결과(활성/오늘입항/지난입항/보류/결재차례/진행중)
      meta: {
        today: td,
        queueOk: queueOk,     // false면 _queue 병합 누락 — 시트분만(②c 결정 포인트)
        queueMerged: queueOk,
        note: queueOk ? '시트+_queue 서버 머지 완료' : '_queue fetch 실패 — 시트분만(클라이언트 _queue 병합 잔류 필요)',
        asOf: _now()
      }
    });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

// ═══════════════════════════════════════════
//  doGet — 조회
// ═══════════════════════════════════════════
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';

    if (action === 'todo_list') {
      const sh = initTodoSheet();
      let items = _readAll(sh);

      // owner 필터 (선택)
      const owner = e.parameter.owner || '';
      if (owner) {
        items = items.filter(r => String(r['담당자']) === owner);
      }

      // 상태 필터 (선택)
      const status = e.parameter.status || '';
      if (status) {
        items = items.filter(r => String(r['상태']) === status);
      }

      // 카테고리 필터 (선택)
      const cat = e.parameter.category || '';
      if (cat) {
        items = items.filter(r => String(r['카테고리']) === cat);
      }

      return _json({ ok: true, count: items.length, data: items });
    }

    // ─── home 대시보드 KPI 자동집계 (매출·지출·VOC) — 2026-06-08 시뽀(CFO) ───
    // GET ?action=home_kpi → { ok, sales, expense, voc, asOf }. 읽기 전용.
    if (action === 'home_kpi') {
      return _homeKpi();
    }

    // ─── G1 '오늘의 항로' 서버 단일 머지 (2026-06-11 시토 · ②a 미사용·비파괴) ───
    // GET ?action=gm_hangro → { ok, count, data, buckets, meta }. 읽기 전용.
    // 시트+_queue.json 을 서버에서 G1 동일 규칙으로 머지·분류. ②c 검증 후 G1·텔레그램·08:00 전환.
    if (action === 'gm_hangro') {
      return _gmHangro();
    }

    // ─── 지출 월별 패턴 진단 (예산 산정 근거용, 읽기전용) — 2026-06-10 시뽀 ───
    if (action === 'expense_monthly') {
      return _kpiExpenseMonthly();
    }

    // ─── 월 지출 예산 기록 ('지출 현황' 시트 '예산' 셀) — GET·POST 공용, EDIT_KEY ───
    if (action === 'expense_set_budget') {
      return _expenseSetBudget(e.parameter.amount || '', e.parameter.key || '');
    }

    // 카테고리 목록 조회
    if (action === 'todo_categories') {
      return _json({ ok: true, data: CATEGORIES });
    }

    // ─── 콘텐츠 파일 읽기 (GM 편집 페이지용) — 2026-05-29 ───
    if (action === 'read_file') {
      const r = _githubReadFile(e.parameter.path || '');
      return _json(r);
    }

    // ─── 콘텐츠 파일 커밋 (GM 편집 → GitHub 자동 push) — 2026-05-29 ───
    if (action === 'commit_file') {
      const r = _githubCommitFile(e.parameter.path || '', e.parameter.content || '',
                                  e.parameter.message || '', e.parameter.key || '');
      return _json(r);
    }

    // ─── 인스타 검수 status 중계 (검수카드 [승인]/[반려]) — 2026-05-30 ───
    if (action === 'review_set_status') {
      const r = _reviewSetStatus(e.parameter.id || '', e.parameter.status || '', e.parameter.key || '');
      return _json(r);
    }

    // POST redirect 우회: URL에 todo_ 또는 approval_ write action이 오면 doPost 로직 실행
    //   (approval_rep_* = 대표 결재 2단계 — 대표싸인 컬럼 set; 2026-06-16 GM)
    if (action.startsWith('todo_') || action.startsWith('approval_')) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      if (e.postData && e.postData.contents) {
        try { const pb = JSON.parse(e.postData.contents); Object.keys(pb).forEach(k => body[k] = pb[k]); } catch(ignored){}
      }
      body.action = action;
      return _processTodoAction(body);
    }

    // 공지 서식 공용 저장 — list/save/delete (GET·POST 공용)
    if (action.startsWith('notice_')) {
      const nbody = {};
      Object.keys(e.parameter).forEach(k => nbody[k] = e.parameter[k]);
      if (e.postData && e.postData.contents) {
        try { const pb2 = JSON.parse(e.postData.contents); Object.keys(pb2).forEach(k => nbody[k] = pb2[k]); } catch(ignored2){}
      }
      nbody.action = action;
      return _processNoticeAction(nbody);
    }

    // 상품 기획 저장 — list (GET 조회)
    if (action.startsWith('product_plan_')) {
      const pbody = {};
      Object.keys(e.parameter).forEach(k => pbody[k] = e.parameter[k]);
      pbody.action = action;
      return _processProductPlanAction(pbody);
    }

    // ─── AI배(C레벨) 전용 탭 조회 (2026-06-08 GM 결정: 탭 분리 설계) ───
    // GET ?action=ai_list[&sheet=AI배(C레벨)]
    // 전용 탭에서 모든 행을 todo_list 와 동일한 컬럼 구조로 반환한다.
    if (action === 'ai_list') {
      const sheetName = e.parameter.sheet || 'AI배(C레벨)';
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const ws = ss.getSheetByName(sheetName);
      if (!ws) return _json({ ok: false, error: 'sheet_not_found: ' + sheetName });
      const rows = _readAll(ws);
      return _json({ ok: true, count: rows.length, data: rows });
    }

    // ─── AI배(C레벨) 전용 탭 생성 (1회성 · GM 승인 후 실행) ───
    // GET ?action=ai_sheet_create[&sheet=AI배(C레벨)]
    // 탭이 이미 있으면 ok:true + created:false 반환(idempotent).
    // 없으면 신규 생성 + todo_list 와 동일 헤더 기록.
    if (action === 'ai_sheet_create') {
      const sheetName = e.parameter.sheet || 'AI배(C레벨)';
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const existing = ss.getSheetByName(sheetName);
      if (existing) {
        const rowCount = Math.max(0, existing.getLastRow() - 1); // 헤더 제외
        return _json({ ok: true, created: false, sheet: sheetName, rows: rowCount, message: '이미 존재하는 탭' });
      }
      const ws = ss.insertSheet(sheetName);
      ws.getRange(1, 1, 1, TODO_HEADERS.length).setValues([TODO_HEADERS]);
      ws.getRange(1, 1, 1, TODO_HEADERS.length)
        .setFontWeight('bold')
        .setBackground('#7b1fa2')   // AI배 탭은 보라색(todo_list 파랑과 구분)
        .setFontColor('#ffffff');
      const widths = [130, 200, 130, 80, 100, 100, 300, 70, 70, 200, 200, 80, 130, 130,
                      130, 130, 130, 100, 150, 200, 80];
      widths.forEach((w, i) => { if (i < TODO_HEADERS.length) ws.setColumnWidth(i + 1, w); });
      ws.setFrozenRows(1);
      return _json({ ok: true, created: true, sheet: sheetName, rows: 0, message: '탭 생성 완료' });
    }

    // ─── AI배(C레벨) 전용 탭 행 추가 ───
    // POST {action:'ai_add', sheet:'AI배(C레벨)', 업무명:..., 담당자:..., ...}
    // todo_add 와 동일한 필드 구조 — 전용 탭에만 기록.
    if (action === 'ai_add') {
      const sheetName = e.parameter.sheet || 'AI배(C레벨)';
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const ws = ss.getSheetByName(sheetName);
      if (!ws) return _json({ ok: false, error: 'sheet_not_found: ' + sheetName });
      const id = _genId();
      const now = _now();
      const row = new Array(TODO_HEADERS.length).fill('');
      row[0] = id;
      row[1] = e.parameter['업무명'] || e.parameter.title || e.parameter.name || '';
      row[2] = e.parameter['카테고리'] || e.parameter.category || '';
      row[3] = e.parameter['담당자'] || e.parameter.owner || '';
      row[4] = e.parameter['시작일'] || e.parameter.startDate || _today();
      row[5] = e.parameter['종료일'] || e.parameter.endDate || '';
      row[6] = e.parameter['내용'] || e.parameter.content || '';
      row[7] = e.parameter['상태'] || e.parameter.status || '진행중';
      row[8] = e.parameter['결재요청'] || '';
      row[9] = e.parameter['링크'] || '';
      row[10] = e.parameter['파일URL'] || '';
      row[11] = e.parameter['생성자'] || '';
      row[12] = now;
      row[13] = now;
      row[17] = e.parameter['결재요청'] ? '대기' : '';
      row[TODO_HEADERS.indexOf('난이도')] = e.parameter['난이도'] || e.parameter.difficulty || '';
      const newRow = ws.getLastRow() + 1;
      ws.getRange(newRow, 1, 1, row.length).setValues([row]);
      _applyStatusColor(ws, newRow, row[7]);
      // 행 추가 후 생성일 desc 자동 정렬 (상시 유지)
      _sortSheetByCreated(ws);
      return _json({ ok: true, id: id, sheet: sheetName, message: 'AI배 업무 추가 완료' });
    }

    // ─── AI배(C레벨) 전용 탭 행 삭제 ───
    // POST {action:'ai_delete', sheet:'AI배(C레벨)', id:'ROW_ID'}
    if (action === 'ai_delete') {
      const sheetName = e.parameter.sheet || 'AI배(C레벨)';
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const ws = ss.getSheetByName(sheetName);
      if (!ws) return _json({ ok: false, error: 'sheet_not_found: ' + sheetName });
      const delId = e.parameter.id || '';
      if (!delId) return _json({ ok: false, error: 'id 필수' });
      const rowNum = _findRow(ws, delId);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + delId });
      ws.deleteRow(rowNum);
      return _json({ ok: true, id: delId, message: 'AI배 업무 삭제 완료' });
    }

    // ─── 생성일 desc 일회 정렬 트리거 (초기 셋업용) ───
    // GET ?action=sort_by_created[&sheet=탭명]  — 탭 미지정 시 기본 2개 탭 모두 정렬.
    if (action === 'sort_by_created') {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const targetName = e.parameter.sheet || '';
      const targets = targetName
        ? [targetName]
        : ['업무&결재 현황', 'AI배(C레벨)'];
      const results = [];
      targets.forEach(function(name) {
        const ws = ss.getSheetByName(name);
        if (!ws) { results.push({ sheet: name, ok: false, error: 'sheet_not_found' }); return; }
        const before = ws.getLastRow() - 1;
        _sortSheetByCreated(ws);
        results.push({ sheet: name, ok: true, rows: before });
      });
      return _json({ ok: true, results: results });
    }

    return _json({ ok: false, error: '알 수 없는 action: ' + action });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

// ═══════════════════════════════════════════
//  doPost — 추가 / 수정 / 삭제 / 완료 / 업로드
// ═══════════════════════════════════════════
// 영문 → 한글 필드 매핑
function _mapFields(body) {
  const map = {title:'업무명',name:'업무명',category:'카테고리',owner:'담당자',startDate:'시작일',endDate:'종료일',content:'내용',status:'상태',approval:'결재요청',link:'링크',fileUrl:'파일URL',creator:'생성자',difficulty:'난이도'};
  Object.keys(map).forEach(en => { if (body[en] !== undefined && !body[map[en]]) body[map[en]] = body[en]; });
  return body;
}

// TODO action 처리 (doGet/doPost 공용)
function _processTodoAction(body) {
  body = _mapFields(body);
  const action = body.action || '';

    // ─── 부서장 결재 PIN 등록 (관리자 1회 셋업) — 2026-06-17 시우(COO) B1 ───
    // 평문 PIN은 ScriptProperties 에만 저장(코드·커밋·로그 비노출). EDIT_KEY 게이트.
    // 파라미터로 받은 값만 set — 코드에 하드코딩 금지. 빈 값은 무시(기존 설정 보존).
    // PIN 게이트(todo_sign @1597)는 속성이 set 되는 순간 자동 강제됨(_deptPinOptional 은 미설정시에만 통과).
    if (action === 'approval_set_pins') {
      var _ek = _prop('EDIT_KEY');
      if (_ek && String(body.key || '') !== _ek) return _json({ ok: false, error: '편집 키 불일치' });
      var _pinMap = {
        ops:     'APPROVAL_PIN_OPS',      // 이경연 실장(운영)
        fac:     'APPROVAL_PIN_FAC',      // 이정헌 소장(시설)
        partner: 'APPROVAL_PIN_PARTNER'   // 나우열M(파트너)
      };
      var _props = PropertiesService.getScriptProperties();
      var _set = [];
      Object.keys(_pinMap).forEach(function(_p) {
        var _v = String(body[_p] || '').trim();
        if (_v) { _props.setProperty(_pinMap[_p], _v); _set.push(_pinMap[_p]); }  // 키명만 기록, 값 비노출
      });
      if (!_set.length) return _json({ ok: false, error: 'set 할 PIN 값이 없습니다(ops/fac/partner 파라미터).' });
      return _json({ ok: true, set: _set, message: _set.length + '개 부서장 PIN 등록됨(값 비노출).' });
    }

    // ─── 새 업무 추가 ───
    if (action === 'todo_add') {
      // sheet 파라미터 있으면 해당 탭에 insert (AI배(C레벨) 전용 탭 이관용)
      let sh;
      if (body['sheet']) {
        const ss = SpreadsheetApp.getActiveSpreadsheet();
        sh = ss.getSheetByName(body['sheet']);
        if (!sh) return _json({ ok: false, error: 'sheet_not_found: ' + body['sheet'] });
      } else {
        sh = initTodoSheet();
      }
      const id = _genId();
      const now = _now();
      const row = new Array(TODO_HEADERS.length).fill('');
      row[0] = id;
      row[1] = body['업무명'] || '';
      row[2] = body['카테고리'] || '';
      row[3] = body['담당자'] || '';
      row[4] = body['시작일'] || _today();
      row[5] = body['종료일'] || '';
      row[6] = body['내용'] || '';
      row[7] = body['상태'] || '진행중';
      row[8] = body['결재요청'] || '';
      row[9] = body['링크'] || '';
      row[10] = body['파일URL'] || '';
      row[11] = body['생성자'] || '';
      row[12] = now;
      row[13] = now;
      // 결재 컬럼 14~18: 신설 — 결재요청 있으면 '대기', 없으면 빈칸
      row[17] = body['결재요청'] ? '대기' : '';
      // 업무 중요도: 담당자 제안값(하/중/상). 부서장 결재단계에서 확정·조정 가능. (index는 indexOf로 안전 산출)
      row[TODO_HEADERS.indexOf('난이도')] = body['난이도'] || '';
      const newRow = sh.getLastRow() + 1;
      sh.getRange(newRow, 1, 1, row.length).setValues([row]);
      _applyStatusColor(sh, newRow, row[7]);

      // 행 추가 후 생성일 desc 자동 정렬 (상시 유지)
      _sortSheetByCreated(sh);

      // 텔레그램 결재 발송 폐기 (2026-05-28 GM 결재) — 결재 SSOT 페이지 단일 운영.
      // 일반 신규 알림만 유지 (결재요청 유무 무관, 짧은 알림).
      _notifyTelegram('📋 <b>[TODO 신규]</b>\n업무명: '+(body['업무명']||'-')+'\n카테고리: '+(body['카테고리']||'-')+'\n담당자: '+(body['담당자']||'-')+(body['결재요청']?'\n결재요청: '+body['결재요청']:'')+'\nID: '+id);
      return _json({ ok: true, id: id, message: '업무가 추가되었습니다.' });
    }

    // ─── 수정 ───
    if (action === 'todo_update') {
      const sh = initTodoSheet();
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      const existing = sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).getValues()[0];
      const prevApproval = existing[TODO_HEADERS.indexOf('결재요청')];
      TODO_HEADERS.forEach((h, i) => {
        if (h === 'id' || h === '생성일' || h === '생성자') return;
        // 빈 문자열('')은 기존값 보존 — 편집 시 빈값 전송으로 다른 필드 초기화되는 버그 근본 차단
        // (2026-06-05 COO). G1·업무현황 SSOT 모든 호출 경로 공통 방어. 의도적 비우기는 별도 센티넬 필요.
        if (body[h] !== undefined && body[h] !== null && body[h] !== '') existing[i] = body[h];
      });
      existing[TODO_HEADERS.indexOf('수정일')] = _now();

      // 완료일 자동 스탬프 (2026-06-10 시토) — 상태가 '완료'이고 완료일이 비어있을 때만 오늘 날짜 기록.
      //   이미 값 있으면 보존(덮어쓰기 X). 완료가 아니면 손대지 않음. G1 '오늘/지난 입항' 판정 정확도용.
      var _doneIdx = TODO_HEADERS.indexOf('완료일');
      if (_doneIdx >= 0 && String(existing[TODO_HEADERS.indexOf('상태')]) === '완료'
          && !String(existing[_doneIdx] || '').trim()) {
        existing[_doneIdx] = _today();
      }

      // 결재요청 새로 추가/변경된 경우 + 결재상태가 미설정/대기인 경우 → 카드 발송
      const newApproval = existing[TODO_HEADERS.indexOf('결재요청')];
      const approvalStatusIdx = TODO_HEADERS.indexOf('결재상태');
      const currentApprovalStatus = String(existing[approvalStatusIdx] || '');
      const approvalChanged = newApproval && newApproval !== prevApproval;
      if (approvalChanged && (currentApprovalStatus === '' || currentApprovalStatus === '대기')) {
        existing[approvalStatusIdx] = '대기';
      }
      // 반려된 업무를 담당자가 결재요청을 실제로 변경/추가해 재상신할 때만 → 대기(부서장부터 재승인).
      // approvalChanged 가드(2026-06-17 COO B4): 본문만 수정 저장 시 결재대기 부활 안 함 — '반려' 흔적 보존.
      // 반려 시 싸인은 이미 초기화됨 (2026-06-05 GM). 의도적 재상신은 결재요청 값 변경으로 표명.
      if (approvalChanged && /반려/.test(currentApprovalStatus)) {
        existing[approvalStatusIdx] = '대기';
      }
      sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
      _applyStatusColor(sh, rowNum, existing[TODO_HEADERS.indexOf('상태')]);

      // 결과보고서는 자동 생성하지 않음 — 페이지의 "인쇄/PDF 저장" 버튼으로 수동 생성 (2026-05-29 GM 결재)
      // 텔레그램 결재 발송 폐기 (2026-05-28 GM 결재). 결재는 결재 SSOT 페이지에서만 진행.
      return _json({ ok: true, id: id, message: '업무가 수정되었습니다.' });
    }

    // ─── 결재 싸인 (봇 콜백 호출) — 2026-05-28 신설 ───
    if (action === 'todo_sign') {
      const sh = initTodoSheet();
      const id = body.id;
      const role = body.role || '';  // '부서장' / 'GM' / '대표님'
      const decision = body.decision || '';  // 'approve' / 'reject'
      const signer = body.signer || role;
      if (!id || !role || !decision) return _json({ ok: false, error: 'id·role·decision 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });

      const existing = sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).getValues()[0];
      const record = {};
      TODO_HEADERS.forEach((h, i) => record[h] = existing[i]);
      const route = _buildApprovalRoute(record);
      const signMap = { '부서장': '부서장싸인', 'GM': 'GM싸인' };  // 대표 단계 폐지(2026-06-16) — '대표싸인' 컬럼은 데이터 호환 위해 보존하나 미사용
      const signCol = signMap[role];
      if (!signCol) return _json({ ok: false, error: '알 수 없는 결재자: ' + role });

      // ── 결재 비밀번호 서버 검증 (GM) — 평문 PIN은 서버 ScriptProperties에만 저장 (2026-05-29 COO 보안) ──
      // GM 콘솔: 프로젝트 설정 → 스크립트 속성에 APPROVAL_PIN_GM 등록 후 사용. 대표 단계 폐지로 APPROVAL_PIN_REP 미사용(2026-06-16).
      // 승인·반려 공통 게이트 (이 아래 reject/approve 분기보다 먼저 차단).
      var _pinKey = { 'GM': 'APPROVAL_PIN_GM' }[role];
      // 부서장 PIN(선택): 카테고리→부서장 매핑으로 키 결정. 속성 미설정 시 PIN 없이 통과(정책 미확정 — GM 확인 포인트, 2026-06-02).
      var _deptPinOptional = false;
      if (role === '부서장') {
        var _MID_PIN = { '이경연 실장':'APPROVAL_PIN_OPS', '이정헌 소장':'APPROVAL_PIN_FAC', '나우열M':'APPROVAL_PIN_PARTNER' };
        // 부서장 PIN 키 = 화면이 표시하는 부서장과 동일 순서로 결정: ① 결재요청(GM 지정 최우선) → ② 담당자 → ③ 카테고리.
        // deptHeadNameOf(프론트)와 정합 — 라벨은 '이정헌 소장'인데 서버는 담당자 기준 '이경연 실장' PIN과 대조해 거부되던 버그 수정 (2026-06-15 시우)
        var _reqDH = String(record['결재요청'] || '').split(',').map(function(s){ return s.trim(); }).filter(function(m){ return _MID_PIN[m]; })[0];
        var _ownerDH = String(record['담당자'] || '').split(',').map(function(s){ return s.trim(); }).filter(function(m){ return _MID_PIN[m]; })[0];
        var _mid = _reqDH || _ownerDH || _deptHeadFor(record['카테고리']);
        _pinKey = (_mid && _MID_PIN[_mid]) ? _MID_PIN[_mid] : null;
        _deptPinOptional = true;  // 부서장은 속성 미설정 시 차단하지 않음(graceful)
      }
      if (_pinKey) {
        var _expected = String(_prop(_pinKey) || '').trim();   // 저장값 앞뒤 공백/개행 방어
        var _submitted = String(body.pin || '').trim();        // 입력값 앞뒤 공백/개행 방어
        // 부서장: PIN 속성 미설정이면 PIN 없이 통과(정책 확정 전 차단 방지). GM/대표는 종전대로 필수.
        // 진단: 거부 시 어떤 비번 키로 대조했는지 반환(키 '이름'만 — 실제 PIN 값은 미노출, 보안 안전). 2026-06-15 시우.
        if (!_expected) {
          if (!_deptPinOptional) return _json({ ok: false, error: role + ' 결재 비밀번호가 서버에 설정되지 않았습니다(관리자 설정 필요).', pinKey: _pinKey });
        } else if (_submitted !== _expected) {
          return _json({ ok: false, error: '비밀번호가 일치하지 않습니다.', pinKey: _pinKey });
        }
      }

      const now = _now();
      if (decision === 'reject') {
        // 반려 = 싸인 초기화 + 결재요청 비움 → 업무현황 복귀(담당자가 수정·재상신 가능). '반려' 맥락은 결재상태에 남김.
        // 결재완료시각도 비움. 업무 '상태'는 진행중 유지(완료 아님). (2026-06-11 시우 — 반려건이 업무현황에서 사라지던 문제 수정)
        existing[TODO_HEADERS.indexOf('부서장싸인')] = '';
        existing[TODO_HEADERS.indexOf('GM싸인')] = '';
        existing[TODO_HEADERS.indexOf('대표싸인')] = '';
        existing[TODO_HEADERS.indexOf('결재완료시각')] = '';
        existing[TODO_HEADERS.indexOf('결재요청')] = '';        // 결재선 잠금해제 → 업무현황 복귀
        existing[TODO_HEADERS.indexOf('결재상태')] = role + ' 반려';  // 반려 사실/주체 보존(재상신·수정 시 초기화됨)
        // 반려 사유 기록(2026-06-17 COO B3): 신규 컬럼 회피 — 기존 '내용'에 append-only 로그.
        //   업무현황 SSOT의 parseContent가 그대로 파싱·표시 → 담당자에게 반려 사유 노출. 기존 결재완료건 무영향.
        var _reason = String(body.reason || '').trim();
        if (_reason) {
          var _cIdx = TODO_HEADERS.indexOf('내용');
          var _prevContent = String(existing[_cIdx] || '');
          existing[_cIdx] = _prevContent + (_prevContent ? '\n' : '') + '===반려이력===\n[' + _today() + ' ' + role + '] ' + _reason;
        }
        existing[TODO_HEADERS.indexOf('수정일')] = now;
        sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
        _notifyTelegram('❌ <b>[결재 반려]</b> ' + role + ' → 업무현황 복귀(수정·재상신 가능)\n📌 ' + (record['업무명']||'-') + (_reason ? '\n📝 사유: ' + _reason : '') + '\n🆔 ' + id);
        return _json({ ok: true, id: id, message: role + ' 반려 처리됨 — 업무현황 복귀', decision: 'reject' });
      }

      // approve
      existing[TODO_HEADERS.indexOf(signCol)] = now + (signer && signer !== role ? ' (' + signer + ')' : '');
      record[signCol] = existing[TODO_HEADERS.indexOf(signCol)];
      const next = _nextApprover(record, route, role);
      if (next) {
        existing[TODO_HEADERS.indexOf('결재상태')] = role + ' 완료';
      } else {
        // 최종 승인 — 결재완료 + 업무 자동 완료 이관(상태=완료·완료일 오늘) → 업무현황 완료 라인·G1 '오늘 입항' 정확 (2026-06-11 시우)
        existing[TODO_HEADERS.indexOf('결재상태')] = '결재완료';
        existing[TODO_HEADERS.indexOf('결재완료시각')] = now;
        existing[TODO_HEADERS.indexOf('상태')] = '완료';
        existing[TODO_HEADERS.indexOf('완료일')] = _today();
      }
      existing[TODO_HEADERS.indexOf('수정일')] = now;
      sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
      if (!next) _applyStatusColor(sh, rowNum, '완료');
      // 결재완료(최종 승인) 건도 완료보관 시트에 복사 — todo_done 과 동일 보관 경로(2026-06-26 시로).
      //   기존엔 todo_done(수동 완료)만 _copyToDoneSheet 를 호출해 결재로 끝난 업무가 아카이브에서 누락되던 버그.
      //   서명/승인 처리 흐름은 위 그대로, '보관 복사'만 추가(인자=todo_done 동일: sh, rowNum).
      if (!next) _copyToDoneSheet(sh, rowNum);

      // 결과보고서는 자동 생성하지 않음 — 페이지 "인쇄/PDF 저장" 버튼으로 수동 (2026-05-29 GM 결재)
      // 텔레그램 결재 카드 폐기 (2026-05-28). 단순 진행 알림만 유지.
      if (next) {
        _notifyTelegram('✅ <b>[' + role + ' 싸인 완료]</b> → ' + next + ' 결재 대기\n📌 ' + (record['업무명']||'-') + '\n🆔 ' + id);
      } else {
        _notifyTelegram('🎉 <b>[결재 완료]</b> 전 라인 승인\n📌 ' + (record['업무명']||'-') + '\n🆔 ' + id + '\n✅ ' + now);
      }

      return _json({ ok: true, id: id, message: role + ' 승인 처리됨', next: next || null, decision: 'approve' });
    }

    // ─── 결재 리셋 (GM 전용) — 결재요청 전으로 복원, 업무현황에서 수정 가능 (2026-06-05 GM) ───
    if (action === 'todo_reset') {
      const sh = initTodoSheet();
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      // PIN 검증: 버튼 경로(비번 전송)는 일치해야 통과(실수 방지). 비번 미전송 호출은 허용 — 삭제(todo_delete)와 동일 개방 수준 (2026-06-05 GM)
      var _expected = _prop('APPROVAL_PIN_GM');
      var _submitted = String(body.pin || '');
      if (_submitted && _expected && _submitted !== _expected) return _json({ ok: false, error: '비밀번호가 일치하지 않습니다.' });
      const existing = sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).getValues()[0];
      const _nm = existing[TODO_HEADERS.indexOf('업무명')];
      existing[TODO_HEADERS.indexOf('결재요청')] = '';
      existing[TODO_HEADERS.indexOf('부서장싸인')] = '';
      existing[TODO_HEADERS.indexOf('GM싸인')] = '';
      existing[TODO_HEADERS.indexOf('대표싸인')] = '';
      existing[TODO_HEADERS.indexOf('결재상태')] = '';
      existing[TODO_HEADERS.indexOf('결재완료시각')] = '';
      existing[TODO_HEADERS.indexOf('수정일')] = _now();
      sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
      _notifyTelegram('↩ <b>[결재 리셋]</b> 결재요청 전으로 복원\n📌 ' + (_nm || '-') + '\n🆔 ' + id);
      return _json({ ok: true, id: id, message: '결재 리셋됨 — 업무현황에서 수정 가능' });
    }

    // ─── 삭제 ───
    if (action === 'todo_delete') {
      let sh;
      if (body['sheet']) {
        const ss = SpreadsheetApp.getActiveSpreadsheet();
        sh = ss.getSheetByName(body['sheet']);
        if (!sh) return _json({ ok: false, error: 'sheet_not_found: ' + body['sheet'] });
      } else {
        sh = initTodoSheet();
      }
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      sh.deleteRow(rowNum);
      return _json({ ok: true, id: id, message: '업무가 삭제되었습니다.' });
    }

    // ─── 완료 ───
    if (action === 'todo_done') {
      const sh = initTodoSheet();
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });

      // 상태 '완료'로 변경
      const statusCol = TODO_HEADERS.indexOf('상태') + 1;
      const modCol = TODO_HEADERS.indexOf('수정일') + 1;
      sh.getRange(rowNum, statusCol).setValue('완료');
      sh.getRange(rowNum, modCol).setValue(_now());
      _applyStatusColor(sh, rowNum, '완료');

      // 완료일 자동 스탬프 (2026-06-10 시토) — 비어있을 때만 오늘 날짜 기록(이미 있으면 보존).
      const doneCol = TODO_HEADERS.indexOf('완료일') + 1;
      if (doneCol >= 1) {
        const prevDone = sh.getRange(rowNum, doneCol).getValue();
        if (!String(prevDone || '').trim()) sh.getRange(rowNum, doneCol).setValue(_today());
      }

      // TODO_완료 시트에 복사
      _copyToDoneSheet(sh, rowNum);

      return _json({ ok: true, id: id, message: '업무가 완료되었습니다.' });
    }

    // ─── 파일 업로드 (Base64 → Drive) ───
    // 프론트(apiCall=GET)·doPost 공용 진입점으로 이관 (2026-06-02 COO):
    // 기존엔 도달불가 doPost 死코드에만 존재해 첨부 업로드가 동작하지 않던 버그 수정.
    if (action === 'todo_upload') {
      const id = body.id;
      const base64 = body.file || body.base64;
      const fileName = body.fileName || '';
      const mimeType = body.mimeType || 'application/octet-stream';
      if (!base64) return _json({ ok: false, error: 'file(Base64) 필수' });

      const fileUrl = _uploadFile(base64, fileName, mimeType);

      if (id) {
        const sh = initTodoSheet();
        const rowNum = _findRow(sh, id);
        if (rowNum > 0) {
          const fileColIdx = TODO_HEADERS.indexOf('파일URL') + 1;
          const modColIdx = TODO_HEADERS.indexOf('수정일') + 1;
          const current = sh.getRange(rowNum, fileColIdx).getValue() || '';
          const updated = current ? current + '\n' + fileUrl : fileUrl;
          sh.getRange(rowNum, fileColIdx).setValue(updated);
          sh.getRange(rowNum, modColIdx).setValue(_now());
        }
      }

      return _json({ ok: true, url: fileUrl, message: '파일이 업로드되었습니다.' });
    }

    // ═══ 대표 결재 2단계 — GM 결재완료(결재상태) 위에 대표싸인 컬럼 3상태 파생 (2026-06-16 GM) ═══
    //   빈값=대표 미올림 / 'PENDING'=GM이 대표 올림(서명본 대기) / URL=서명본 업로드됨=대표 결재완료.
    //   결재상태 컬럼('결재완료')과 독립 — GM 종착 결재완료 로직은 손대지 않는다.

    // 대표 결재 올리기 — 결재상태='결재완료'일 때만 '대표싸인'='PENDING' set.
    if (action === 'approval_rep_escalate') {
      const sh = initTodoSheet();
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      const apprCol = TODO_HEADERS.indexOf('결재상태') + 1;
      const repCol = TODO_HEADERS.indexOf('대표싸인') + 1;
      const apprStatus = String(sh.getRange(rowNum, apprCol).getValue() || '').trim();
      if (apprStatus !== '결재완료') return _json({ ok: false, error: 'GM 결재완료 건만 대표 올림 가능 (현재: ' + (apprStatus || '미결') + ')' });
      const repNow = String(sh.getRange(rowNum, repCol).getValue() || '').trim();
      if (/^https?:\/\//.test(repNow)) return _json({ ok: false, error: '이미 대표 결재완료(서명본 있음)' });
      sh.getRange(rowNum, repCol).setValue('PENDING');
      sh.getRange(rowNum, TODO_HEADERS.indexOf('수정일') + 1).setValue(_now());
      return _json({ ok: true, id: id, repSign: 'PENDING', message: '대표 결재 라인에 올렸습니다 (서명본 대기).' });
    }

    // 대표 서명본 업로드 = 대표 결재완료 트리거 — Drive 업로드 URL을 '대표싸인' 컬럼에 직접 저장.
    if (action === 'approval_rep_sign_upload') {
      const id = body.id;
      const base64 = body.file || body.base64;
      const fileName = body.fileName || '';
      const mimeType = body.mimeType || 'application/octet-stream';
      if (!id) return _json({ ok: false, error: 'id 필수' });
      if (!base64) return _json({ ok: false, error: 'file(Base64) 필수' });
      const sh = initTodoSheet();
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      const apprCol = TODO_HEADERS.indexOf('결재상태') + 1;
      const apprStatus = String(sh.getRange(rowNum, apprCol).getValue() || '').trim();
      if (apprStatus !== '결재완료') return _json({ ok: false, error: 'GM 결재완료 건만 대표 서명본 업로드 가능' });
      const fileUrl = _uploadFile(base64, fileName, mimeType);
      const repCol = TODO_HEADERS.indexOf('대표싸인') + 1;
      sh.getRange(rowNum, repCol).setValue(fileUrl);  // 대표 서명본 = 대표싸인 칸에 직접
      sh.getRange(rowNum, TODO_HEADERS.indexOf('수정일') + 1).setValue(_now());
      return _json({ ok: true, id: id, url: fileUrl, repSign: fileUrl, message: '대표 서명본 업로드 완료 — 대표 결재완료.' });
    }

    // 대표 올림 취소 — '대표싸인'을 빈값으로. 이미 URL(서명완료)이어도 허용하되 주의(GM 확인성).
    if (action === 'approval_rep_cancel') {
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });
      const sh = initTodoSheet();
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      const repCol = TODO_HEADERS.indexOf('대표싸인') + 1;
      const prev = String(sh.getRange(rowNum, repCol).getValue() || '').trim();
      sh.getRange(rowNum, repCol).setValue('');
      sh.getRange(rowNum, TODO_HEADERS.indexOf('수정일') + 1).setValue(_now());
      return _json({ ok: true, id: id, prev: prev, message: '대표 올림 취소됨.' });
    }

    // ─── 첨부 파일 삭제 — 파일URL 컬럼에서 해당 URL 제거 + Drive 원본 휴지통 이동 (2026-06-03 GM) ───
    if (action === 'todo_remove_file') {
      const id = body.id;
      const url = String(body.url || '').trim();
      if (!id || !url) return _json({ ok: false, error: 'id·url 필수' });
      const sh = initTodoSheet();
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });
      const col = TODO_HEADERS.indexOf('파일URL') + 1;
      const current = String(sh.getRange(rowNum, col).getValue() || '');
      const remaining = current.split('\n').map(s => s.trim()).filter(Boolean).filter(u => u !== url);
      sh.getRange(rowNum, col).setValue(remaining.join('\n'));
      sh.getRange(rowNum, TODO_HEADERS.indexOf('수정일') + 1).setValue(_now());
      // Drive 원본 휴지통 이동(파일 ID 추출 가능 시). 실패해도 시트 링크는 이미 제거됨.
      try { const m = url.match(/[-\w]{25,}/); if (m) DriveApp.getFileById(m[0]).setTrashed(true); } catch (e) {}
      return _json({ ok: true, message: '첨부가 삭제되었습니다.', remaining: remaining.length });
    }

    // ─── 고아 첨부 정리 — 어떤 task에도 참조되지 않은 TODO_Files 파일 휴지통 이동 (2026-06-03 GM) ───
    // 안전: dryRun=1 이면 목록만. maxBytes>0 이면 그 크기 이하만 대상(작은 테스트파일만, 실제 첨부 보호).
    if (action === 'todo_orphan_cleanup') {
      const dryRun = String(body.dryRun || '') === '1' || body.dryRun === true;
      const maxBytes = Number(body.maxBytes || 0);
      const folder = _getTodoFolder();
      const sh = initTodoSheet();
      const col = TODO_HEADERS.indexOf('파일URL') + 1;
      const last = sh.getLastRow();
      const referenced = {};
      if (last >= 2) {
        sh.getRange(2, col, last - 1, 1).getValues().forEach(function (r) {
          String(r[0] || '').split('\n').forEach(function (u) { const m = String(u).match(/[-\w]{25,}/); if (m) referenced[m[0]] = 1; });
        });
      }
      const files = folder.getFiles();
      const report = [];
      while (files.hasNext()) {
        const f = files.next();
        const fid = f.getId();
        if (referenced[fid]) continue;                 // 참조됨 → 유지
        const size = f.getSize();
        if (maxBytes > 0 && size > maxBytes) continue;  // 크기 초과 → 유지(실제 첨부 보호)
        const info = { id: fid, name: f.getName(), size: size, created: String(f.getDateCreated()) };
        if (!dryRun) { try { f.setTrashed(true); info.trashed = true; } catch (e) { info.error = String(e); } }
        report.push(info);
      }
      return _json({ ok: true, dryRun: dryRun, count: report.length, files: report });
    }

    return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

// doPost용 ai_ 액션 처리 (ai_add·ai_delete — doGet과 공용 로직)
function _processAiAction(body) {
  const action = body.action || '';
  const sheetName = body.sheet || 'AI배(C레벨)';
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ws = ss.getSheetByName(sheetName);
  if (!ws) return _json({ ok: false, error: 'sheet_not_found: ' + sheetName });

  if (action === 'ai_add') {
    // _mapFields 이미 적용된 body 사용
    const id = _genId();
    const now = _now();
    const row = new Array(TODO_HEADERS.length).fill('');
    row[0] = id;
    row[1] = body['업무명'] || '';
    row[2] = body['카테고리'] || '';
    row[3] = body['담당자'] || '';
    row[4] = body['시작일'] || _today();
    row[5] = body['종료일'] || '';
    row[6] = body['내용'] || '';
    row[7] = body['상태'] || '진행중';
    row[8] = body['결재요청'] || '';
    row[9] = body['링크'] || '';
    row[10] = body['파일URL'] || '';
    row[11] = body['생성자'] || '';
    row[12] = now;
    row[13] = now;
    row[17] = body['결재요청'] ? '대기' : '';
    row[TODO_HEADERS.indexOf('난이도')] = body['난이도'] || '';
    const newRow = ws.getLastRow() + 1;
    ws.getRange(newRow, 1, 1, row.length).setValues([row]);
    _applyStatusColor(ws, newRow, row[7]);
    _sortSheetByCreated(ws);
    return _json({ ok: true, id: id, sheet: sheetName, message: 'AI배 업무 추가 완료' });
  }

  if (action === 'ai_delete') {
    const delId = body.id || '';
    if (!delId) return _json({ ok: false, error: 'id 필수' });
    const rowNum = _findRow(ws, delId);
    if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + delId });
    ws.deleteRow(rowNum);
    return _json({ ok: true, id: delId, message: 'AI배 업무 삭제 완료' });
  }

  return _json({ ok: false, error: '알 수 없는 ai action: ' + action });
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const act = body.action || '';
    // 대용량/파일 쓰기 = POST(text/plain JSON 본문)로 받는다 — GET URL 길이초과 회피 (2026-06-29)
    if (act === 'commit_file') return _json(_githubCommitFile(body.path || '', body.content || '', body.message || '', body.key || ''));
    if (act === 'read_file') return _json(_githubReadFile(body.path || ''));
    if (act === 'review_set_status') return _json(_reviewSetStatus(body.id || '', body.status || '', body.key || ''));
    if (act === 'expense_set_budget') return _expenseSetBudget(body.amount || '', body.key || '');
    if (act.indexOf('notice_') === 0) return _processNoticeAction(body);
    if (act.indexOf('product_plan_') === 0) return _processProductPlanAction(body);
    if (act.indexOf('ai_') === 0) return _processAiAction(_mapFields(body));
    return _processTodoAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
