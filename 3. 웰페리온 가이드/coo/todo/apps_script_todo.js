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
function _findSheet(ss, fallbacks) {
  let candidate = null;
  for (const name of fallbacks) {
    const s = ss.getSheetByName(name);
    if (!s) continue;
    if (s.getLastRow() >= 2) return s;  // 데이터 있는 시트 즉시 반환
    if (!candidate) candidate = s;       // 빈 시트는 후보로만
  }
  return candidate;
}

const TODO_HEADERS = [
  'id', '업무명', '카테고리', '담당자',
  '시작일', '종료일', '내용', '상태',
  '결재요청', '링크', '파일URL',
  '생성자', '생성일', '수정일',
  // 결재 체계 (2026-05-28 신설)
  '부서장싸인', 'GM싸인', '대표싸인', '결재상태', '결재완료시각'
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
  let sh = _findSheet(ss, TODO_SHEET_FALLBACKS);
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
                  130, 130, 130, 100, 150];
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
  let doneSh = _findSheet(ss, DONE_SHEET_FALLBACKS);

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

// ─── 텔레그램 알림 전면 폐기 (2026-05-28 GM 결재) — 결재 SSOT 페이지 단일 운영 ───
// 함수 시그니처는 보존 — 향후 복구 시 본체만 복원하면 됨.
function _notifyTelegram(text, opts) {
  return; // no-op
}

// ─── 결재 라인 자동 산출 (결제 권한 기준 v2.0) ───
function _buildApprovalRoute(record) {
  // content에서 BUDGET 마커 파싱
  const content = String(record['내용'] || '');
  const m = content.match(/===BUDGET===\s*\n([^|]+)\|\s*(\d+)/);
  let budgetCategory = null, budgetAmount = 0;
  if (m) { budgetCategory = m[1].trim(); budgetAmount = Number(m[2]); }

  // 결재요청 필드 (수동 체크)
  const manual = String(record['결재요청'] || '').split(',').map(s => s.trim()).filter(Boolean);

  // 예산 기반 자동 산출
  let auto = [];
  if (budgetCategory && budgetAmount > 0) {
    switch (budgetCategory) {
      case '일상 운영비':           auto = budgetAmount <= 300000 ? ['GM'] : ['부서장', 'GM']; break;
      case '소액 유지보수':         auto = budgetAmount <= 100000 ? ['부서장'] : ['GM']; break;
      case '마케팅':                auto = budgetAmount <= 3000000 ? ['GM'] : ['GM', '대표님']; break;
      case '비상 지출':             auto = budgetAmount <= 500000 ? ['부서장'] : ['GM']; break;
      case '계약·정기 약정':
      case 'IT·소프트웨어':
      case '급여·인건비·외주·교육':
      case '장비 구매·교체':        auto = ['GM', '대표님']; break;
    }
  }

  // 수동 + 자동 합집합 (순서: 부서장 → GM → 대표님)
  const set = {};
  manual.concat(auto).forEach(a => { set[a] = true; });
  const order = ['부서장', 'GM', '대표님'];
  return order.filter(role => set[role]);
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
    'https://wellperion-cao.github.io/wellperion-automation/coo/todo/%EA%B2%B0%EC%9E%AC%20SSOT.html';

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
function _nextApprover(record, route) {
  // 싸인 컬럼 확인 → 미서명 첫 사람
  const map = { '부서장': '부서장싸인', 'GM': 'GM싸인', '대표님': '대표싸인' };
  for (let i = 0; i < route.length; i++) {
    const r = route[i];
    if (!record[map[r]]) return r;
  }
  return null; // 전원 서명 완료
}

// ─── 파일 업로드 (Base64 → Drive) ───
function _uploadFile(base64, fileName, mimeType) {
  // 폴더 ID 조회 또는 자동 생성
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

    // 카테고리 목록 조회
    if (action === 'todo_categories') {
      return _json({ ok: true, data: CATEGORIES });
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
  const map = {title:'업무명',name:'업무명',category:'카테고리',owner:'담당자',startDate:'시작일',endDate:'종료일',content:'내용',status:'상태',approval:'결재요청',link:'링크',fileUrl:'파일URL',creator:'생성자'};
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
        if (body[h] !== undefined && body[h] !== null) existing[i] = body[h];
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
      sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
      _applyStatusColor(sh, rowNum, existing[TODO_HEADERS.indexOf('상태')]);

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
      const signMap = { '부서장': '부서장싸인', 'GM': 'GM싸인', '대표님': '대표싸인' };
      const signCol = signMap[role];
      if (!signCol) return _json({ ok: false, error: '알 수 없는 결재자: ' + role });

      const now = _now();
      if (decision === 'reject') {
        existing[TODO_HEADERS.indexOf('결재상태')] = role + ' 반려';
        existing[TODO_HEADERS.indexOf('수정일')] = now;
        sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
        _notifyTelegram('❌ <b>[결재 반려]</b> ' + role + '\n📌 ' + (record['업무명']||'-') + '\n🆔 ' + id);
        return _json({ ok: true, id: id, message: role + ' 반려 처리됨', decision: 'reject' });
      }

      // approve
      existing[TODO_HEADERS.indexOf(signCol)] = now + (signer && signer !== role ? ' (' + signer + ')' : '');
      record[signCol] = existing[TODO_HEADERS.indexOf(signCol)];
      const next = _nextApprover(record, route);
      if (next) {
        existing[TODO_HEADERS.indexOf('결재상태')] = role + ' 완료';
      } else {
        existing[TODO_HEADERS.indexOf('결재상태')] = '결재완료';
        existing[TODO_HEADERS.indexOf('결재완료시각')] = now;
      }
      existing[TODO_HEADERS.indexOf('수정일')] = now;
      sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);

      // 텔레그램 결재 카드 폐기 (2026-05-28). 단순 진행 알림만 유지.
      if (next) {
        _notifyTelegram('✅ <b>[' + role + ' 싸인 완료]</b> → ' + next + ' 결재 대기\n📌 ' + (record['업무명']||'-') + '\n🆔 ' + id);
      } else {
        _notifyTelegram('🎉 <b>[결재 완료]</b> 전 라인 승인\n📌 ' + (record['업무명']||'-') + '\n🆔 ' + id + '\n✅ ' + now);
      }

      return _json({ ok: true, id: id, message: role + ' 승인 처리됨', next: next || null, decision: 'approve' });
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

    return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processTodoAction(body);

    // ─── 새 업무 추가 ───
    if (action === 'todo_add') {
      const sh = initTodoSheet();
      const id = _genId();
      const now = _now();

      const row = [
        id,
        body['업무명'] || '',
        body['카테고리'] || '',
        body['담당자'] || '',
        body['시작일'] || _today(),
        body['종료일'] || '',
        body['내용'] || '',
        body['상태'] || '진행중',
        body['결재요청'] || '',
        body['링크'] || '',
        body['파일URL'] || '',
        body['생성자'] || '',
        now,  // 생성일
        now   // 수정일
      ];

      const newRow = sh.getLastRow() + 1;
      sh.getRange(newRow, 1, 1, row.length).setValues([row]);
      _applyStatusColor(sh, newRow, row[7]);

      // 텔레그램 알림
      _notifyTelegram(
        '📋 <b>[TODO 신규]</b>\n'
        + '업무명: ' + (body['업무명'] || '-') + '\n'
        + '카테고리: ' + (body['카테고리'] || '-') + '\n'
        + '담당자: ' + (body['담당자'] || '-') + '\n'
        + 'ID: ' + id
      );

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

      // 전달된 필드만 덮어쓰기
      TODO_HEADERS.forEach((h, i) => {
        if (h === 'id' || h === '생성일' || h === '생성자') return; // 불변 필드
        if (body[h] !== undefined && body[h] !== null) {
          existing[i] = body[h];
        }
      });
      // 수정일 갱신
      existing[TODO_HEADERS.indexOf('수정일')] = _now();

      sh.getRange(rowNum, 1, 1, TODO_HEADERS.length).setValues([existing]);
      _applyStatusColor(sh, rowNum, existing[TODO_HEADERS.indexOf('상태')]);

      return _json({ ok: true, id: id, message: '업무가 수정되었습니다.' });
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

    // ─── 완료 처리 ───
    if (action === 'todo_done') {
      const sh = initTodoSheet();
      const id = body.id;
      if (!id) return _json({ ok: false, error: 'id 필수' });

      const rowNum = _findRow(sh, id);
      if (rowNum < 0) return _json({ ok: false, error: '해당 ID를 찾을 수 없습니다: ' + id });

      const statusCol = TODO_HEADERS.indexOf('상태') + 1;
      const modCol = TODO_HEADERS.indexOf('수정일') + 1;

      sh.getRange(rowNum, statusCol).setValue('완료');
      sh.getRange(rowNum, modCol).setValue(_now());
      _applyStatusColor(sh, rowNum, '완료');

      return _json({ ok: true, id: id, message: '업무가 완료 처리되었습니다.' });
    }

    // ─── 파일 업로드 ───
    if (action === 'todo_upload') {
      const id = body.id;
      const base64 = body.file;
      const fileName = body.fileName || '';
      const mimeType = body.mimeType || 'application/octet-stream';

      if (!base64) return _json({ ok: false, error: 'file(Base64) 필수' });

      // Drive에 파일 저장
      const fileUrl = _uploadFile(base64, fileName, mimeType);

      // id가 있으면 해당 TODO의 파일URL 필드에 추가
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

    return _json({ ok: false, error: '알 수 없는 action: ' + action });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
