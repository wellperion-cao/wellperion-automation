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
const DONE_SHEET_FALLBACKS = [
  '업무 완료 현황',
  '결재 현황',
  'TODO_완료',
  '결재 현황 SSOT'
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
  // 난이도 평가 (2026-06-03 신설) — 하1·중2·상3. 담당자 제안 → 부서장 결재단계 확정.
  // append-only: 기존 컬럼 인덱스 불변. initTodoSheet 자동 마이그레이션이 재배포 시 시트에 컬럼 추가.
  '난이도'
];

// 카테고리 목록
const CATEGORIES = [
  '[1]매출및영업',
  '[2]인사&파트너',
  '[3]운영정책',
  '[4]시설및환경',
  '[5]3대비전',
  '[6]회장님하달'
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

// 결재 현황(완료/반려) 시트에 완료 건 복사
function _copyToDoneSheet(srcSheet, srcRow) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let doneSh = _findSheet(ss, DONE_SHEET_FALLBACKS, false);

  // 시트가 없으면 자동 생성 (메인 fallback 이름 우선)
  if (!doneSh) {
    doneSh = ss.insertSheet(DONE_SHEET_NAME);
    // 헤더 + 완료일 컬럼 추가
    const headers = TODO_HEADERS.concat(['완료일']);
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
  // 완료일 추가
  rowData.push(_now());

  // 완료 시트에 추가
  const newRow = doneSh.getLastRow() + 1;
  doneSh.getRange(newRow, 1, 1, rowData.length).setValues([rowData]);
  // 상태 셀 녹색 표시
  const statusCol = TODO_HEADERS.indexOf('상태') + 1;
  doneSh.getRange(newRow, statusCol).setBackground('#34a853').setFontColor('#ffffff');
}

// ─── CORS JSON 응답 ───
function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
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

// ─── 카테고리 → 부서장 매핑 (결재선 1단계 자동, 2026-06-02 GM 확정 복원) ───
// 운영부=이경연 실장([1][3]) / 시설부=이정헌 소장([4]) / 파트너팀=나우열M([2]).
// 매핑 없는 카테고리([5][6][7][8])는 부서장 생략 → GM 단독(약속 L09: 결재 종착=GM).
var CAT_DEPT_HEAD = {
  '[1] 매출 및 영업': '이경연 실장',
  '[3] 운영 정책':   '이경연 실장',
  '[4] 시설 및 환경': '이정헌 소장',
  '[2] 인사 & 파트너': '나우열M'
};
function _deptHeadFor(category) { return CAT_DEPT_HEAD[String(category || '')] || ''; }

// ─── 결재 라인 자동 산출 — (명시 체크한 부서장) → GM (약속 L09: 결재 종착=GM 단일, 대표 단계 시스템 제외 / 2026-06-17 COO A: 카테고리 자동 부서장 삽입 폐지) ───
// 중간 결재자: 결재요청에 명시 체크한 부서장만(카테고리 자동삽입 안 함).
// 결재 필요 여부 = 수동 결재요청 또는 예산(BUDGET 마커) 존재.
// 담당자=김남욱GM이면 부서장 단계 생략. GM은 항상 최종. (대표 보고는 시스템 밖 오프라인 페이퍼 — approval_rep_* 별도)
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
// 최종 완료(null)로 확정한다. → GM 사인 후 결재완료 정합(약속 L09: 대표 단계 폐지).
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
//  gm_hangro — G1 '오늘의 항로' 서버 단일 머지 엔진 (2026-06-11 시토 · G1 신뢰성 고도화 ②a)
//  ─────────────────────────────────────────────────────────────────────────────
//  ⚠️ 추가만(미사용·비파괴). 기존 action·G1 JS·daily_scheduler·ceo_morning_pipeline 절대 미변경.
//  현행 G1 머지 JS(wellperion_guide(main).html 7300~7460·7700~7745)를 GAS로 1:1 미러링.
//  시트(todo_list) + _queue.json(raw GitHub, UrlFetchApp)을 서버에서 읽어 동일 결과 산출.
//  ②c 라이브 검증 후 G1·텔레그램·08:00 파이프라인을 이 엔드포인트로 하나씩 전환.
//  ※ 정본 = .deploy-todo/업무&결재 현황.js (이 작업본은 동기 미러). 매핑표는 정본 주석 참조.
//  ※ _queue.json 은 GAS가 raw GitHub 로 직접 읽음(공개 URL · 인증 불필요). 실패 시 시트분만 폴백.
// ═══════════════════════════════════════════
var GM_HANGRO_QUEUE_URL = 'https://raw.githubusercontent.com/wellperion-cao/wellperion-automation/master/status/_queue.json';
var GM_HANGRO_DEPT_HEADS = ['이경연 실장', '이정헌 소장', '나우열M'];
var GM_HANGRO_CAT_DEPT_HEAD = { '[2] 인사': '나우열M', '[3] 파트너팀': '나우열M', '[4] 운영 정책': '이경연 실장', '[5] 시설 및 환경': '이정헌 소장' };

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

function _gmHangroNextApprover(row) {
  var approval = String(row['결재요청'] || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
  if (!approval.length) return null;
  var owners = String(row['담당자'] || '').split(',').map(function (s) { return s.trim(); });
  var ownerIsGM = owners.indexOf('김남욱GM') >= 0;
  var midName = approval.filter(function (m) { return GM_HANGRO_DEPT_HEADS.indexOf(m) >= 0; })[0]
    || owners.filter(function (o) { return GM_HANGRO_DEPT_HEADS.indexOf(o) >= 0; })[0]
    || (GM_HANGRO_CAT_DEPT_HEAD[String(row['카테고리'] || '')] || '');
  var midExplicit = midName && approval.indexOf(midName) >= 0;
  var skipMid = midName && owners.indexOf(midName) >= 0 && !midExplicit;
  var route = [];
  if (midName && !ownerIsGM && !skipMid) route.push('부서장');
  if (!ownerIsGM) route.push('GM');
  // 약속 L09: 결재 종착=GM 단일. 대표 단계 폐지(대표 보고는 시스템 밖 오프라인 페이퍼).
  var map = { '부서장': row['부서장싸인'], 'GM': row['GM싸인'] };
  for (var i = 0; i < route.length; i++) { if (!map[route[i]]) return route[i]; }
  return null;
}

function _gmHangroIsG1Owner(owner) {
  return owner.indexOf('김남욱GM') >= 0
    || /AI (CEO|CMO|CTO|COO|CFO|CPO|CHRO)/.test(owner)
    || /웰리|시모|시토|시우|시뽀|시포|시로/.test(owner);
}

function _gmHangroBuildItems(rows, queue) {
  var items = [];

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

function _gmHangroClassify(items, todayStr) {
  function _apprPending(t) {
    var rq = String(t.apprReq || t.approval || '').trim(), a = String(t.apprStatus || '').trim();
    return rq && a !== '결재완료' && !/반려/.test(a);
  }
  var apprWait = items.filter(function (t) { return t.status === '완료' && _apprPending(t); });
  var active = items.filter(function (t) { return t.status === '진행중'; });
  var doneAll = items.filter(function (t) { return t.status === '완료' && !_apprPending(t); });
  var done = doneAll.filter(function (t) { return (t._doneDate || '') === todayStr; });
  var donePast = doneAll.filter(function (t) { return (t._doneDate || '') !== todayStr; });
  var hold = items.filter(function (t) { return t.status === '보류'; });
  var disposed = items.filter(function (t) { return t.status === '폐기'; });
  var apprActiveGm = active.filter(function (t) { return t.category === '결재' && t._apprKind !== 'inflight'; });
  var apprInflight = active.filter(function (t) { return t.category === '결재' && t._apprKind === 'inflight'; });
  active = active.filter(function (t) { return t.category !== '결재'; });
  return {
    active: active, done: done, donePast: donePast, hold: hold, disposed: disposed,
    apprGm: apprActiveGm.concat(apprWait), apprInflight: apprInflight,
    apprGmTotal: apprWait.length + apprActiveGm.length,
    apprInflightTotal: apprInflight.length
  };
}

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
    } catch (qe) { queue = []; queueOk = false; }

    var items = _gmHangroBuildItems(rows, queue);
    var td = _today();
    var c = _gmHangroClassify(items, td);

    return _json({
      ok: true,
      count: items.length,
      data: items,
      buckets: c,
      meta: {
        today: td,
        queueOk: queueOk,
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

    // ─── G1 '오늘의 항로' 서버 단일 머지 (2026-06-11 시토 · ②a 미사용·비파괴) ───
    if (action === 'gm_hangro') {
      return _gmHangro();
    }

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

    // POST redirect 우회: URL에 todo_ write action이 오면 doPost 로직 실행
    if (action.startsWith('todo_')) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      if (e.postData && e.postData.contents) {
        try { const pb = JSON.parse(e.postData.contents); Object.keys(pb).forEach(k => body[k] = pb[k]); } catch(ignored){}
      }
      body.action = action;
      return _processTodoAction(body);
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

    // ─── 새 업무 추가 ───
    if (action === 'todo_add') {
      const sh = initTodoSheet();
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
      // 난이도: 담당자 제안값(하/중/상). 부서장 결재단계에서 확정·조정 가능. (index는 indexOf로 안전 산출)
      row[TODO_HEADERS.indexOf('난이도')] = body['난이도'] || '';
      const newRow = sh.getLastRow() + 1;
      sh.getRange(newRow, 1, 1, row.length).setValues([row]);
      _applyStatusColor(sh, newRow, row[7]);

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

      // 결재요청 새로 추가/변경된 경우 + 결재상태가 미설정/대기인 경우 → 카드 발송
      const newApproval = existing[TODO_HEADERS.indexOf('결재요청')];
      const approvalStatusIdx = TODO_HEADERS.indexOf('결재상태');
      const currentApprovalStatus = String(existing[approvalStatusIdx] || '');
      const approvalChanged = newApproval && newApproval !== prevApproval;
      if (approvalChanged && (currentApprovalStatus === '' || currentApprovalStatus === '대기')) {
        existing[approvalStatusIdx] = '대기';
      }
      // 반려된 업무를 담당자가 수정·저장하면 자동 재상신 → 대기(부서장부터 재승인). 반려 시 싸인은 이미 초기화됨 (2026-06-05 GM)
      if (newApproval && /반려/.test(currentApprovalStatus)) {
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
      const role = body.role || '';  // '부서장' / 'GM' (약속 L09: 대표 단계 폐지)
      const decision = body.decision || '';  // 'approve' / 'reject'
      const signer = body.signer || role;
      if (!id || !role || !decision) return _json({ ok: false, error: 'id·role·decision 필수' });
      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });

      const existing = sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).getValues()[0];
      const record = {};
      TODO_HEADERS.forEach((h, i) => record[h] = existing[i]);
      const route = _buildApprovalRoute(record);
      const signMap = { '부서장': '부서장싸인', 'GM': 'GM싸인' };  // 약속 L09: 결재 종착=GM. '대표싸인' 컬럼은 데이터 호환 위해 보존하나 시스템 결재선 미사용
      const signCol = signMap[role];
      if (!signCol) return _json({ ok: false, error: '알 수 없는 결재자: ' + role });

      // ── 결재 비밀번호 서버 검증 (GM) — 평문 PIN은 서버 ScriptProperties에만 저장 (2026-05-29 COO 보안) ──
      // GM 콘솔: 프로젝트 설정 → 스크립트 속성에 APPROVAL_PIN_GM 등록 후 사용. 대표 단계 폐지로 APPROVAL_PIN_REP 미사용(약속 L09).
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
        // 부서장: PIN 속성 미설정이면 PIN 없이 통과(정책 확정 전 차단 방지). GM은 종전대로 필수.
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
        existing[TODO_HEADERS.indexOf('수정일')] = now;
        sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
        _notifyTelegram('❌ <b>[결재 반려]</b> ' + role + ' → 업무현황 복귀(수정·재상신 가능)\n📌 ' + (record['업무명']||'-') + '\n🆔 ' + id);
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
      const sh = initTodoSheet();
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

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processTodoAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
