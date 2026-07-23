// 강사 콘텐츠 접수 전용 Apps Script (P1 — 접수 폼 + 저장 + 알림)
// ⚠️ VOC(.deploy-voc)·문의(Survey.js)·점검·업무 GAS와 완전 독립 — 신규 전용 GAS 프로젝트로 배포한다.
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
    var sh = SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty('INTAKE_SHEET_ID')).getSheets()[0];
    var row = [new Date(), d.name, d.team, d.intro || '', d.benefit || '', urls.join('\n'), vurl, folder.getUrl(), '접수'];
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
    var sh = SpreadsheetApp.openById(sheetId).getSheets()[0];
    var last = sh.getLastRow();
    out.sheet_name = sh.getName();
    out.row_count = Math.max(0, last - 1);            // 헤더 1행 제외한 접수 건수
    out.header = last > 0 ? sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0] : [];
  } catch (err) {
    out.ok = false;
    out.sheet_error = String(err);                     // 시트 없음·권한 없음을 그대로 노출
  }
  return out;
}

// 접수 행 조회 — 필드명은 시트 실제 헤더를 그대로 사용. limit(기본 100·최대 500)·since(ISO) 지원.
function _intakeRows_(p) {
  var sheetId = PropertiesService.getScriptProperties().getProperty('INTAKE_SHEET_ID');
  if (!sheetId) return { ok: false, error: 'INTAKE_SHEET_ID 미설정' };
  var sh = SpreadsheetApp.openById(sheetId).getSheets()[0];
  var last = sh.getLastRow(), width = sh.getLastColumn();
  if (last < 2 || width < 1) {
    return { ok: true, sheet_name: sh.getName(), count: 0, total_rows: 0, rows: [] };
  }
  var header = sh.getRange(1, 1, 1, width).getValues()[0].map(function (h, i) {
    return String(h).trim() || ('col' + (i + 1));
  });
  var limit = parseInt(p.limit, 10);
  limit = (isNaN(limit) || limit < 1) ? 100 : Math.min(limit, 500);
  var since = p.since ? new Date(p.since) : null;
  if (since && isNaN(since.getTime())) since = null;

  var start = Math.max(2, last - limit + 1);           // 최근 limit건
  var values = sh.getRange(start, 1, last - start + 1, width).getValues();
  var rows = [];
  for (var i = 0; i < values.length; i++) {
    var ts = values[i][0];
    if (since && !(ts instanceof Date && ts >= since)) continue;
    var o = { _row: start + i };
    for (var c = 0; c < width; c++) {
      var v = values[i][c];
      o[header[c]] = (v instanceof Date)
        ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
        : v;
    }
    rows.push(o);
  }
  return { ok: true, sheet_name: sh.getName(), count: rows.length, total_rows: last - 1, rows: rows };
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
