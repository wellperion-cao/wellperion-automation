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
