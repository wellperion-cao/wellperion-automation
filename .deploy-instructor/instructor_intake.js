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
//   doPost(action:'staff_feedback_photo') — 2026-07-29 GM 지시(사진 첨부 확정). 실무진
//            피드백(cpo/member/실무진피드백.html) 사진을 staff_feedback/<접수ID> 하위폴더에
//            저장하고 공개 링크를 반환한다. 콘텐츠 접수 시트에는 쓰지 않는다.
//            ★피드백 시트 10번째 칸("첨부사진")에 쓰는 것도 이 파일이 한다
//            (_writeFeedbackPhotoColumn_). funnel-v2 Survey.js 는 이 칸을 쓰지 않는다 —
//            종전 주석이 Survey.js 몫이라 잘못 적어 두어 2026-08-05 바로잡음.
//
// 계약(doPost body, JSON):
//   { name, team, intro, benefit, agree,
//     photos: [{b64, mime, fname}, ...],           // 0~5장
//     video: {b64, mime, fname} | null,             // 50MB 이하만 base64 첨부(폼 단에서 가드)
//     videoLink: "" }                                // video 없을 때 대용량 링크 폴백
//   응답: {ok:true, drive_folder, sheet_row} | {ok:false, err}
//
// 계약(doPost body, staff_feedback_photo, JSON):
//   { action:'staff_feedback_photo', feedbackId:'FB260729-132718', photos:[{b64,mime,fname}] }
//   응답: {ok:true, urls:[...], folder} | {ok:false, err}
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
    // ★2026-07-29 GM 지시(사진 첨부 확정) — 실무진 피드백 사진은 이 경로로 분기.
    //   기존 콘텐츠 접수(강사) 흐름은 이 분기 아래로 손대지 않는다(action 미지정 시 그대로 진행).
    if (d.action === 'staff_feedback_photo') return _handleFeedbackPhotoUpload_(d);
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

// ─── 실무진 피드백 사진 첨부 (2026-07-29 GM 지시 — 콘텐츠 접수 GAS 재사용) ───
// 목적: 사진 업로드→드라이브 저장→공개 링크 회수→피드백 시트 10번째 칸 기록까지 전부
//   이 프로젝트 하나가 맡는다. funnel-v2 Survey.js(피드백 제출·조회·처리 뒷단, 188/200)는
//   ★손대지 않는다·배포 0회 소모★(GM 확정 구조 원문) — 같은 스프레드시트(_MI_SS_ID,
//   Survey.js 의 MEMBER_SPREADSHEET_ID 와 동일 ID)를 이 GAS가 직접 열어 쓰기만 한다.
// 순서 계약(클라이언트): ① staff_feedback_submit(Survey.js, 기존·무변경)으로 먼저 피드백
//   텍스트를 접수해 접수ID 를 받는다 → ② 사진이 있으면 그 접수ID 로 이 액션을 호출한다.
//   접수ID 가 아직 시트에 없으면(순서가 바뀌면) sheetWrite.ok=false 로 알리고 사진 저장
//   자체는 성공 처리한다(사진을 잃지 않는다 — 재조회로 나중에도 복구 가능).
// 저장 위치: 콘텐츠 접수 폴더(INTAKE_DRIVE_FOLDER_ID)와 안 섞이게 전용 하위 폴더
//   staff_feedback/<접수ID> 로 분리한다(GM 지시 원문 그대로).
// 계약: { action:'staff_feedback_photo', feedbackId:'FB260729-132718', photos:[{b64,mime,fname}] }
//   응답: {ok:true, urls:[...], folder, sheetWrite:{ok,...}} | {ok:false, err}
var FEEDBACK_PHOTO_ROOT_NAME = 'staff_feedback';
var FEEDBACK_PHOTO_MAX_COUNT = 5;
var FEEDBACK_PHOTO_MAX_B64_LEN = 4000000;   // base64 약 4MB ≈ 원본 3MB — 1600px 리사이즈 결과물엔 넉넉한 여유치
// 실무진 피드백 탭이 있는 스프레드시트 — Survey.js _MI_SS_ID/MEMBER_SPREADSHEET_ID 와 동일(단일 출처 재사용, 새 시트 아님).
var FEEDBACK_SHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
var FEEDBACK_SHEET_TAB = '실무진 피드백';
var FEEDBACK_PHOTO_COLUMN = '첨부사진';   // 10번째 칸 이름 — 기존 9칸 이름·순서는 절대 바꾸지 않고 맨 오른쪽에만 추가

function _getOrCreateSubfolder_(parent, name) {
  var it = parent.getFoldersByName(name);
  if (it.hasNext()) return it.next();
  return parent.createFolder(name);
}

// 접수ID 대조로 「첨부사진」 칸에 링크를 쓴다. 칸이 없으면 맨 오른쪽에 새로 만든다(기존 9칸 불변).
function _writeFeedbackPhotoColumn_(feedbackId, urls) {
  var sh;
  try { sh = SpreadsheetApp.openById(FEEDBACK_SHEET_ID).getSheetByName(FEEDBACK_SHEET_TAB); }
  catch (e) { return { ok: false, err: '피드백 시트를 열 수 없습니다: ' + String(e) }; }
  if (!sh) return { ok: false, err: "'" + FEEDBACK_SHEET_TAB + "' 탭을 찾을 수 없습니다" };
  var lastCol = sh.getLastColumn();
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  var ix = function (name) { for (var i = 0; i < hdr.length; i++) if (String(hdr[i]).trim() === name) return i; return -1; };
  var cId = ix('접수ID');
  if (cId < 0) return { ok: false, err: "'접수ID' 헤더를 찾을 수 없습니다" };
  var cPhoto = ix(FEEDBACK_PHOTO_COLUMN);
  if (cPhoto < 0) {
    cPhoto = lastCol;   // 기존 9칸 뒤 = 10번째 칸(맨 오른쪽 추가만·기존 칸 이동 없음)
    sh.getRange(1, cPhoto + 1).setValue(FEEDBACK_PHOTO_COLUMN);
  }
  var last = sh.getLastRow();
  if (last < 2) return { ok: false, err: '피드백 데이터가 없습니다' };
  var ids = sh.getRange(2, cId + 1, last - 1, 1).getValues();
  var rowNo = -1;
  for (var r = 0; r < ids.length; r++) { if (String(ids[r][0]).trim() === feedbackId) { rowNo = r + 2; break; } }
  if (rowNo < 0) return { ok: false, err: '접수ID를 시트에서 찾을 수 없습니다: ' + feedbackId };
  // 눌리는 링크로 쓴다 (2026-08-05 GM 지적: "사진이 보이는 게 아니라 그냥 링크가 보이고, 눌러도 안 넘어간다").
  //   종전 setValue(urls.join('\n')) 은 URL을 맨 문자열로 넣었다 — 시트는 setValue 로 들어온 문자열을
  //   자동으로 링크로 만들어 주지 않아서, 보이는 건 긴 주소뿐이고 눌러도 아무 일이 없었다.
  //   ★셀 안에 그림을 직접 띄우는 =IMAGE 는 쓸 수 없다: 구글이 IMAGE 함수의 드라이브 주소 지원을
  //   막아서 어떤 형태로 넣어도 #REF! 가 뜬다(2026-08-05 실측 — /file/d/ 형태·uc?export=view·
  //   thumbnail?id= 모두 동일. 셋 다 브라우저로는 image/jpeg 를 정상 반환하지만 시트 IMAGE 는 거부한다).
  //   그래서 '사진 1·2…' 라벨에 진짜 하이퍼링크를 건다 — 한 번 누르면 사진이 열리고, 맨 URL 텍스트는 안 남는다.
  sh.getRange(rowNo, cPhoto + 1).setRichTextValue(_photoLinkRichText_(urls));
  // 여러 장이면 줄이 늘어난다 — 기본 행 높이(21px)에선 둘째 줄부터 잘려 안 보인다. 사람이 넓혀 둔 건 안 건드린다.
  if (sh.getRowHeight(rowNo) < 21 * urls.length) sh.setRowHeight(rowNo, 21 * urls.length);
  return { ok: true, row: rowNo, col: cPhoto + 1, count: urls.length };
}

// 줄마다 '사진 1·2…'에 진짜 하이퍼링크를 건다(맨 URL 텍스트를 안 남기려는 것).
function _photoLinkRichText_(urls) {
  var labels = urls.map(function (u, i) { return '사진 ' + (i + 1); });
  var b = SpreadsheetApp.newRichTextValue().setText(labels.join('\n'));
  var pos = 0;
  for (var i = 0; i < labels.length; i++) {
    b.setLinkUrl(pos, pos + labels[i].length, urls[i]);
    pos += labels[i].length + 1;             // +1 = 줄바꿈 한 글자
  }
  return b.build();
}

function _handleFeedbackPhotoUpload_(d) {
  var feedbackId = String(d.feedbackId || '').trim();
  if (!/^FB\d{6}-\d{6}$/.test(feedbackId)) {
    return _json({ ok: false, err: '올바르지 않은 접수ID 형식입니다 (예: FB260729-132718)' });
  }
  var photos = d.photos || [];
  if (!photos.length) return _json({ ok: false, err: '첨부할 사진이 없습니다' });
  if (photos.length > FEEDBACK_PHOTO_MAX_COUNT) {
    return _json({ ok: false, err: '사진은 최대 ' + FEEDBACK_PHOTO_MAX_COUNT + '장까지 첨부할 수 있습니다' });
  }
  for (var i = 0; i < photos.length; i++) {
    var raw = String(photos[i].b64 || '');
    if (raw.length > FEEDBACK_PHOTO_MAX_B64_LEN) {
      return _json({ ok: false, err: (i + 1) + '번째 사진이 너무 큽니다. 화면을 새로고침한 뒤 다시 시도해 주세요(자동 축소 실패로 추정).' });
    }
  }
  try {
    var rootId = PropertiesService.getScriptProperties().getProperty('INTAKE_DRIVE_FOLDER_ID');
    if (!rootId) return _json({ ok: false, err: 'INTAKE_DRIVE_FOLDER_ID 미설정' });
    var root = DriveApp.getFolderById(rootId);
    var fbRoot = _getOrCreateSubfolder_(root, FEEDBACK_PHOTO_ROOT_NAME);
    var folder = _getOrCreateSubfolder_(fbRoot, feedbackId);
    var urls = photos.map(function (p) { return _saveFile_(p.b64, p.mime, p.fname || 'photo.jpg', folder); });
    var sheetWrite;
    try { sheetWrite = _writeFeedbackPhotoColumn_(feedbackId, urls); }
    catch (eW) { sheetWrite = { ok: false, err: String(eW) }; }
    return _json({ ok: true, urls: urls, folder: folder.getUrl(), sheetWrite: sheetWrite });
  } catch (err) {
    return _json({ ok: false, err: '사진 저장에 실패했습니다: ' + String(err) });
  }
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
    if (action === 'diag_token_fp') return _tokenFingerprint(p.key || 'BOT_TOKEN');
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

// ─── 봇 토큰 지문 진단 (Survey.js/todo GAS 동형 · 배47 잔여작업 · 2026-07-27 시토) ───
// 토큰 자체가 아니라 sha256 앞 8자리(지문)만 반환 — 값 비노출 원칙 유지. INTAKE_READ_TOKEN 게이트 하위.
function _tokenFingerprint(key) {
  var t = PropertiesService.getScriptProperties().getProperty(key || 'BOT_TOKEN');
  if (!t) return _json({ ok: true, key: key || 'BOT_TOKEN', hasToken: false, fp: null });
  var bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, t, Utilities.Charset.UTF_8);
  var hex = bytes.map(function (b) { return ('0' + (b & 0xFF).toString(16)).slice(-2); }).join('');
  return _json({ ok: true, key: key || 'BOT_TOKEN', hasToken: true, fp: hex.slice(0, 8) });
}

// ─── 텔레그램 알림 (Survey.js _notifyTelegram 동형, .deploy-funnel/Survey.js:834-839) ───
function _notifyTelegram(text) {
  var p = PropertiesService.getScriptProperties();
  var token = p.getProperty('BOT_TOKEN'), chat = p.getProperty('INTAKE_CHAT_ID');
  if (!token || !chat) return;
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage',
    { method: 'post', payload: { chat_id: chat, text: text }, muteHttpExceptions: true });
}
