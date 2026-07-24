// 강사 콘텐츠 접수 전용 Apps Script (P1 — 접수 폼 + 저장 + 알림)
// ⚠️ VOC(.deploy-voc)·문의(Survey.js)·점검·업무 GAS와는 별개 프로젝트다.
//    이 스크립트가 배포된 GAS 프로젝트 = scriptId 1Q5Riwzq…yta4PhGP0.
//    2026-07-23 이전에는 「웰페리온 | 강습 문의 알림」(자동 접수 알림.js · onFormSubmit
//    폼 트리거)이 같은 프로젝트에 동거했으나, 구글 폼 삭제·자체폼+텔레그램 대체로
//    GM 지시에 따라 폐기·제거됨 → _archive/gas_lesson_mail_alert_20260723/ 보존.
//    따라서 현재 이 프로젝트의 정본 파일 = appsscript.json + instructor_intake.js 2종뿐.
// 계획서 정본: docs/superpowers/plans/2026-07-22-강사콘텐츠-접수모듈-P1.md (Task 1)
// 스펙: docs/superpowers/specs/2026-07-22-강사콘텐츠-접수시안모듈-design.md (§4-1·§5)
//
// 액션:
//   doPost — 강사가 프론트(instructor_intake.html)에서 이름·팀·사진(3~5)·영상(선택)·소개·
//            회원가치·동의를 JSON POST → 파일은 base64 → Drive 강사별 폴더 저장 → 「강사접수」
//            시트에 메타 append → 텔레그램 접수 알림.
//
// 계약(doPost body, JSON):
//   { name, team, intro, benefit, agree,
//     photos: [{b64, mime, fname}, ...],           // 0~5장
//     video: {b64, mime, fname} | null,             // 50MB 이하만 base64 첨부(폼 단에서 가드)
//     videoLink: "" }                                // video 없을 때 대용량 링크 폴백
//   응답: {ok:true, drive_folder, sheet_row} | {ok:false, err}
//
// 필요 ScriptProperties(배포 시 GM이 등록 — 4개):
//   BOT_TOKEN, INTAKE_CHAT_ID, INTAKE_SHEET_ID, INTAKE_DRIVE_FOLDER_ID
//
// 보안: 업로드 MIME 화이트리스트(ALLOW_MIME) — 조달 putPhoto(.deploy-procurement/procurement.js:95)
//   주입 차단 패턴 준용. data: 접두사 방어는 VOC _vUploadPhoto(.deploy-voc/VOC_배포.js:462) 동형.
//   토큰·시트ID·폴더ID·챗ID는 repo 하드코딩 금지 — 전부 ScriptProperties 서버측 보관.

var ALLOW_MIME = { 'image/jpeg': 1, 'image/png': 1, 'image/webp': 1, 'video/mp4': 1 };

// ─── 시트 헤더 계약 (2026-07-23 수리) ───
// doPost 가 append 하는 row 배열(아래 `var row = [...]`)과 1:1 동일 순서다. 순서 변경 금지.
//   [new Date(), d.name, d.team, d.intro, d.benefit, urls.join, vurl, folder.getUrl(), '접수']
var INTAKE_HEADER = ['접수일시', '성함', '분류', '한줄소개', '회원이얻는것', '사진링크', '영상링크', '드라이브폴더', '상태'];

// ─── 접수 탭 지정 (2026-07-24 수리 · 배9888) ───
// ★고친 이유: 종전 getSheets()[0] 은 '맨 앞 탭'을 잡는다. INTAKE_SHEET_ID 는 2021년부터
//   쓰는 라이브 강습 운영 스프레드시트('3-1) 강습, WSC 강습 문의 관리')이고, 접수가 들어갈
//   곳은 그 안의 '마케팅 접수' 탭이다 — 지금은 우연히 맨 앞이라 맞아떨어질 뿐, 누가 탭 순서를
//   한 번만 바꾸면 접수가 '강습 신규문의' 탭에 append 된다(강습 데이터 오염).
//   → 이름으로 잡아 순서 변경에 영향받지 않게 한다. 조회 경로는 없으면 만들지 않는다(읽기 전용 유지).
var INTAKE_SHEET_NAME = '마케팅 접수';

function _intakeSheet_(createIfMissing) {
  var id = PropertiesService.getScriptProperties().getProperty('INTAKE_SHEET_ID');
  if (!id) return null;
  var ss = SpreadsheetApp.openById(id);
  var sh = ss.getSheetByName(INTAKE_SHEET_NAME);
  if (!sh && createIfMissing) sh = ss.insertSheet(INTAKE_SHEET_NAME);
  return sh || null;
}

// 1행이 헤더인가? — 오판이 안전한 쪽(= 데이터로 간주 → 헤더 삽입)으로 판정한다.
// 데이터로 보는 신호: 1열이 Date · 날짜/타임스탬프 문자열 · 숫자 · 빈칸.
// 그 외(사람이 붙인 어떤 제목이든)는 헤더로 인정 → 중복 삽입 없음.
function _looksLikeHeader_(vals) {
  if (!vals || !vals.length) return false;
  var a = vals[0];
  if (a instanceof Date) return false;                             // 접수일시 값 = 데이터
  var s = String(a === null || a === undefined ? '' : a).trim();
  if (!s) return false;                                            // 빈칸 = 헤더 아님
  if (/^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/.test(s)) return false;      // "2026-07-22T05:22:35Z" = 데이터
  if (/^\d+(\.\d+)?$/.test(s)) return false;                       // 숫자 = 데이터
  return true;
}

function _fallbackHeader_(width) {
  var h = [];
  for (var i = 0; i < width; i++) h.push('col' + (i + 1));
  return h;
}

// 헤더 보장 — 기존 데이터 행은 절대 덮어쓰지·지우지 않는다(삽입만).
function _ensureIntakeHeader_(sh) {
  var last = sh.getLastRow(), width = sh.getLastColumn();
  if (last < 1 || width < 1) {                                     // 완전 빈 시트 → 헤더만 기록
    sh.getRange(1, 1, 1, INTAKE_HEADER.length).setValues([INTAKE_HEADER]);
    return true;
  }
  if (_looksLikeHeader_(sh.getRange(1, 1, 1, width).getValues()[0])) return true;
  sh.insertRowBefore(1);                                           // 데이터 보존 — 앞에 한 줄 삽입
  sh.getRange(1, 1, 1, INTAKE_HEADER.length).setValues([INTAKE_HEADER]);
  return true;
}

// ─── 파일 저장 (base64 → Drive, 공개 링크) — VOC _vUploadPhoto 패턴 복제 ───
function _saveFile_(b64, mime, fname, folder) {
  if (!ALLOW_MIME[mime]) throw new Error('허용되지 않은 형식: ' + mime);
  var raw = b64.indexOf(',') >= 0 ? b64.split(',')[1] : b64;   // data: 접두사 방어(VOC L462 동형)
  var blob = Utilities.newBlob(Utilities.base64Decode(raw), mime, fname);
  var f = folder.createFile(blob);
  f.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return f.getUrl();
}

// ─── 접수 처리 ───
function doPost(e) {
  try {
    var d = JSON.parse(e.postData.contents);
    if (!d.name || !d.team || !d.agree) return _json({ ok: false, err: '필수 항목 누락' });
    var root = DriveApp.getFolderById(PropertiesService.getScriptProperties().getProperty('INTAKE_DRIVE_FOLDER_ID'));
    var folder = root.createFolder(d.team + '_' + d.name + '_' + _stamp());
    var urls = (d.photos || []).map(function (p) { return _saveFile_(p.b64, p.mime, p.fname, folder); });
    var vurl = d.video ? _saveFile_(d.video.b64, d.video.mime, d.video.fname, folder) : (d.videoLink || '');
    var sh = _intakeSheet_(true);                                  // 이름으로 지정 · 없으면 생성
    if (!sh) return _json({ ok: false, err: 'INTAKE_SHEET_ID 미설정' });
    var row = [new Date(), d.name, d.team, d.intro || '', d.benefit || '', urls.join('\n'), vurl, folder.getUrl(), '접수'];
    try { _ensureIntakeHeader_(sh); } catch (hErr) { }             // 헤더 보장 실패해도 접수 저장은 계속
    sh.appendRow(row);
    _notifyTelegram('🎬 새 강사 콘텐츠 접수: ' + d.name + ' / ' + d.team + ' (사진 ' + urls.length + '장' + (vurl ? '·영상' : '') + ')');
    return _json({ ok: true, drive_folder: folder.getUrl(), sheet_row: sh.getLastRow() });
  } catch (err) { return _json({ ok: false, err: String(err) }); }
}

// ─── 조회 액션 (읽기 전용 · 토큰 가드) — 2026-07-23 GM 승인 ───
// 목적: INTAKE_SHEET_ID 가 ScriptProperties 전용이라 접수 데이터를 볼 방법이 없어
//   시트 배선 여부조차 확인 불가 → 토큰 가드형 조회 액션 추가.
// ★기존 배포본 호환: action 파라미터가 없으면 종전 헬스체크 응답을 그대로 반환한다
//   (구 배포본은 파라미터를 전부 무시하고 이 응답만 냈다 — 기존 호출부 무손상).
// ★읽기 전용: 아래 경로에는 시트·드라이브 쓰기/삭제 코드가 없다(get 계열만 사용).
// ★토큰은 코드에 하드코딩하지 않는다 — ScriptProperties INTAKE_READ_TOKEN.
var _HEALTH_MSG = '마케팅 접수 GAS 정상 (POST로 접수)';

function doGet(e) {
  var p = (e && e.parameter) || {};
  var action = p.action || '';
  // 액션 미지정 = 종전 배포본과 동일한 헬스체크 응답(회귀 0)
  if (!action) return _json({ ok: true, msg: _HEALTH_MSG });

  var expected = PropertiesService.getScriptProperties().getProperty('INTAKE_READ_TOKEN');
  // 토큰 미설정·미제출·불일치 → 데이터 반환 금지
  if (!expected || !p.token || String(p.token) !== String(expected)) {
    return _json({ ok: false, error: 'unauthorized' });
  }
  try {
    if (action === 'diag') return _json(_intakeDiag_());
    if (action === 'rows') return _json(_intakeRows_(p));
    return _json({ ok: false, error: 'unknown_action' });
  } catch (err) { return _json({ ok: false, error: String(err) }); }
}

// 배선 진단 — 시트 ID 값 자체는 응답에 넣지 않는다(노출 최소화). 설정 여부만 노출.
function _intakeDiag_() {
  var sp = PropertiesService.getScriptProperties();
  var sheetId = sp.getProperty('INTAKE_SHEET_ID');
  var out = {
    ok: true,
    sheet_id_set: !!(sheetId && String(sheetId).trim()),
    sheet_name: '',
    row_count: 0,
    drive_folder_id: sp.getProperty('INTAKE_DRIVE_FOLDER_ID') || ''
  };
  if (!out.sheet_id_set) { out.sheet_error = 'INTAKE_SHEET_ID 미설정'; return out; }
  try {
    var sh = _intakeSheet_(false);                       // 조회는 만들지 않는다(읽기 전용)
    if (!sh) { out.ok = false; out.sheet_error = "'" + INTAKE_SHEET_NAME + "' 탭 없음"; return out; }
    var last = sh.getLastRow(), width = sh.getLastColumn();
    var first = (last > 0 && width > 0) ? sh.getRange(1, 1, 1, width).getValues()[0] : [];
    var hasHeader = _looksLikeHeader_(first);
    out.sheet_name = sh.getName();
    out.header_ok = hasHeader;                        // false = 1행이 데이터(헤더 없음)
    out.row_count = hasHeader ? Math.max(0, last - 1) : last;   // 헤더 없으면 1행도 접수 건
    out.header = hasHeader ? first : _fallbackHeader_(width);
    if (!hasHeader && last > 0) out.first_row = first;           // 헤더 오인되던 실제 1행 노출
  } catch (err) {
    out.ok = false;
    out.sheet_error = String(err);                     // 시트 없음·권한 없음을 그대로 노출
  }
  return out;
}

// 접수 행 조회 — 필드명은 시트 실제 헤더 사용, 헤더가 없으면 col1..colN 폴백(1행도 데이터로 반환).
// limit(기본 100·최대 500)·since(ISO) 지원.
function _intakeRows_(p) {
  var sh = _intakeSheet_(false);                         // 조회는 만들지 않는다(읽기 전용)
  if (!sh) return { ok: false, error: "INTAKE_SHEET_ID 미설정 또는 '" + INTAKE_SHEET_NAME + "' 탭 없음" };
  var last = sh.getLastRow(), width = sh.getLastColumn();
  if (last < 1 || width < 1) {
    return { ok: true, sheet_name: sh.getName(), header_ok: false, count: 0, total_rows: 0, rows: [] };
  }
  var first = sh.getRange(1, 1, 1, width).getValues()[0];
  var hasHeader = _looksLikeHeader_(first);
  // 헤더가 없거나 깨졌으면 col1..colN 폴백 — 1행도 데이터로 전부 반환(행 손실 0)
  var header = hasHeader
    ? first.map(function (h, i) { return String(h).trim() || ('col' + (i + 1)); })
    : _fallbackHeader_(width);
  var dataStart = hasHeader ? 2 : 1;
  var total = last - dataStart + 1;
  if (total < 1) {
    return { ok: true, sheet_name: sh.getName(), header_ok: hasHeader, count: 0, total_rows: 0, rows: [] };
  }
  var limit = parseInt(p.limit, 10);
  limit = (isNaN(limit) || limit < 1) ? 100 : Math.min(limit, 500);
  var since = p.since ? new Date(p.since) : null;
  if (since && isNaN(since.getTime())) since = null;

  var start = Math.max(dataStart, last - limit + 1);   // 최근 limit건
  var values = sh.getRange(start, 1, last - start + 1, width).getValues();
  var rows = [];
  for (var i = 0; i < values.length; i++) {
    var ts = values[i][0];
    var tsd = (ts instanceof Date) ? ts : (ts ? new Date(ts) : null);   // 문자열 타임스탬프도 인정
    if (since && !(tsd && !isNaN(tsd.getTime()) && tsd >= since)) continue;
    var o = { _row: start + i };
    for (var c = 0; c < width; c++) {
      var v = values[i][c];
      o[header[c]] = (v instanceof Date)
        ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
        : v;
    }
    rows.push(o);
  }
  return { ok: true, sheet_name: sh.getName(), header_ok: hasHeader, count: rows.length, total_rows: total, rows: rows };
}

function _json(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function _stamp() { return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMdd_HHmmss'); }

// ─── 텔레그램 알림 (Survey.js _notifyTelegram 동형, .deploy-funnel/Survey.js:834-839) ───
function _notifyTelegram(text) {
  var p = PropertiesService.getScriptProperties();
  var token = p.getProperty('BOT_TOKEN'), chat = p.getProperty('INTAKE_CHAT_ID');
  if (!token || !chat) return;
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage',
    { method: 'post', payload: { chat_id: chat, text: text }, muteHttpExceptions: true });
}
