// 웰페리온 회원 종합 접수처 전용 Apps Script (QR + 사진)
// ⚠️ 점검 GAS(coo/check/apps_script_v3.js)·업무 GAS(coo/todo/apps_script_todo.js)와
//    완전 독립 — 절대 그 위에 얹지 말 것. 신규 전용 GAS 프로젝트로 배포한다.
// ⚠️ 라이브 '이슈 응답' 시트는 건드리지 않는다. VOC는 별도 시트 탭 「접수 VOC」.
//
// 액션:
//   voc_submit (POST) — 회원 모바일 폼 제출: 유형·위치·사진base64·내용·(선택)연락처
//                       → Drive 'VOC_Photos' 저장 → 공개 URL → 시트 append (상태=접수)
//                       → (설정 시) 텔레그램 핵심멤버방 알림
//   voc_list   (GET)  — 현황 조회: 전체 또는 상태/유형 필터
//   voc_update (POST) — 상태 전환(접수→처리중→완료) · 담당 배정 · 처리메모
//
// 사진은 POST 본문 base64 필수 (GET 쿼리는 유실 — reference_gas_file_upload_must_post).
// 검증은 브라우저로 (curl -L은 GAS 302에서 POST 본문을 떨궈 검증 불가).
//
// 보안(후속 과제 · 이번 차단 아님): 무인증 공개 엔드포인트 → 변조·스팸 위험.
//   최소 hidden token / rate-limit 은 ScriptProperties(VOC_SUBMIT_TOKEN) 기반으로 후속 적용.
//   토큰·챗ID 등 비밀값은 절대 repo 하드코딩 금지 — 전부 ScriptProperties 서버측 보관.

// ─── 상수 ───
var VOC_SHEET = '접수 VOC';
var VOC_HEADERS = [
  '접수ID', '접수일시', '유형', '위치', '사진URL',
  '내용', '연락처', '상태', '담당', '처리메모'
];
var VOC_TYPES = ['분실물', '시설불편', '청결', '기타'];
var VOC_STATUSES = ['접수', '처리중', '완료'];
var VOC_STATUS_COLORS = {
  '접수':  '#e6944e', // 주황
  '처리중': '#5b9fd5', // 파랑
  '완료':  '#6abf7b'  // 초록
};
var VOC_PHOTO_FOLDER_NAME = 'VOC_Photos';

// ─── 종합 접수처 상수 ───
// REG_CATEGORIES: 카테고리 라우팅 SSOT. dept 변경 시 여기 한 줄만 수정.
var REG_CATEGORIES = [
  { key: 'lost',     label: '분실물 접수',         sheet: '접수_분실물',   dept: '운영부' },
  { key: 'facility', label: '시설물 고장 접수',     sheet: '접수_시설고장', dept: '시설부' },
  { key: 'clean',    label: '청결 이슈 접수',       sheet: '접수_청결',     dept: '지원부' },
  { key: 'leave',    label: '휴회 접수',            sheet: '접수_휴회',     dept: '운영부' },
  { key: 'praise',   label: '직원·강사 칭찬합니다', sheet: '접수_칭찬',     dept: '운영부' },
  { key: 'voice',    label: '직원·강사 쓴소리합니다', sheet: '접수_쓴소리', dept: '운영부' }
  // praise/voice → dept: '인사부' 로 바꿀 때 위 두 줄만 수정
];

// 공통 12컬럼 (영문키: 한글헤더)
var REG_COMMON_HEADERS = [
  { key: 'regId',     label: '접수ID'   },
  { key: 'category',  label: '카테고리' },
  { key: 'createdAt', label: '접수일시' },
  { key: 'name',      label: '이름'     },
  { key: 'contact',   label: '연락처'   },
  { key: 'loc',       label: '위치'     },
  { key: 'content',   label: '내용'     },
  { key: 'photoUrl',  label: '사진URL'  },
  { key: 'status',    label: '상태'     },
  { key: 'assignee',  label: '담당'     },
  { key: 'memo',      label: '처리메모' },
  { key: 'dept',      label: '부서'     }
];

// 카테고리별 추가 컬럼 (영문키: 한글헤더)
var REG_EXTRA_HEADERS = {
  lost:     [
    { key: 'itemName',   label: '분실물품'   },
    { key: 'lostWhen',   label: '분실시점'   },
    { key: 'keepWhere',  label: '보관요청'   }
  ],
  facility: [
    { key: 'equipName',  label: '고장설비'     },
    { key: 'severity',   label: '위험도'       },
    { key: 'usable',     label: '사용가능여부' }
  ],
  clean:    [
    { key: 'issueKind',  label: '유형'   },
    { key: 'urgency',    label: '시급도' }
  ],
  leave:    [
    { key: 'memberNo',   label: '회원번호'   },
    { key: 'startDate',  label: '휴회시작일' },
    { key: 'period',     label: '희망기간'   },
    { key: 'reason',     label: '사유'       }
  ],
  praise:   [
    { key: 'targetStaff', label: '대상직원·강사' },
    { key: 'episode',     label: '사례'          }
  ],
  voice:    [
    { key: 'targetStaff',    label: '대상직원·강사' },
    { key: 'episode',        label: '사례'          },
    { key: 'anonymousPref',  label: '익명희망'      }
  ]
};

// ─── 종합 접수처 헬퍼 ───
// 키로 카테고리 객체 반환 (없으면 null)
function _regCatByKey(key) {
  for (var i = 0; i < REG_CATEGORIES.length; i++) {
    if (REG_CATEGORIES[i].key === key) return REG_CATEGORIES[i];
  }
  return null;
}
// 라벨로 카테고리 객체 반환 (없으면 null)
function _regCatByLabel(label) {
  for (var i = 0; i < REG_CATEGORIES.length; i++) {
    if (REG_CATEGORIES[i].label === label) return REG_CATEGORIES[i];
  }
  return null;
}
// 카테고리 키에 대한 전체 헤더 배열 반환 ({key,label}[])
function _regHeadersFor(catKey) {
  var extra = REG_EXTRA_HEADERS[catKey] || [];
  return REG_COMMON_HEADERS.concat(extra);
}

// ─── ScriptProperties 헬퍼 ───
function _vprop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

// ─── 유틸 ───
function _vNow() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
}
function _vGenId() {
  return 'VOC-' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMddHHmmss')
    + ('000' + new Date().getMilliseconds()).slice(-3);
}

// ─── CORS JSON 응답 ───
function _vJson(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ─── 스프레드시트 확보 ───
// 독립형(standalone) 웹앱으로 배포 시 getActiveSpreadsheet()는 null을 반환하므로
// ScriptProperties 'SPREADSHEET_ID' 로 openById() 한다.
// GM 액션: 프로젝트 설정 → 스크립트 속성 → SPREADSHEET_ID = VOC 데이터를 넣을 시트의 ID
//   (시트 URL: https://docs.google.com/spreadsheets/d/<여기>/edit  ← 이 부분이 ID)
function _vGetSpreadsheet() {
  var ssId = _vprop('SPREADSHEET_ID');
  if (!ssId) throw new Error('ScriptProperties에 SPREADSHEET_ID 미설정 — 프로젝트 설정 → 스크립트 속성에 추가');
  return SpreadsheetApp.openById(ssId);
}

// ─── 시트 확보 (없으면 자동 생성 + 헤더) ───
function _vGetSheet() {
  var ss = _vGetSpreadsheet();
  var sh = ss.getSheetByName(VOC_SHEET);
  if (sh) {
    // 헤더 누락 시 보강 (빈 시트 안전)
    if (sh.getLastRow() < 1) {
      sh.getRange(1, 1, 1, VOC_HEADERS.length).setValues([VOC_HEADERS]);
    }
    return sh;
  }
  sh = ss.insertSheet(VOC_SHEET);
  sh.getRange(1, 1, 1, VOC_HEADERS.length).setValues([VOC_HEADERS]);
  sh.getRange(1, 1, 1, VOC_HEADERS.length)
    .setFontWeight('bold')
    .setBackground('#B79F8A')
    .setFontColor('#ffffff');
  var widths = [170, 150, 90, 110, 220, 320, 130, 80, 120, 280];
  widths.forEach(function (w, i) { sh.setColumnWidth(i + 1, w); });
  sh.setFrozenRows(1);
  return sh;
}

// ─── 종합 접수처 시트 확보 (카테고리 키로 접근) ───
// 기존 _vGetSheet의 자동생성·서식 로직 재사용, 헤더만 카테고리별로 다름.
function _regGetSheet(catKey) {
  var cat = _regCatByKey(catKey);
  if (!cat) throw new Error('알 수 없는 카테고리 키: ' + catKey);
  var headers = _regHeadersFor(catKey).map(function (h) { return h.label; });
  var ss = _vGetSpreadsheet();
  var sh = ss.getSheetByName(cat.sheet);
  if (sh) {
    if (sh.getLastRow() < 1) {
      sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    }
    return sh;
  }
  sh = ss.insertSheet(cat.sheet);
  sh.getRange(1, 1, 1, headers.length).setValues([headers]);
  sh.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#B79F8A')
    .setFontColor('#ffffff');
  sh.setFrozenRows(1);
  return sh;
}

// ─── 마스킹 헬퍼 — PII 제거 후 공개 보드용 복제본 반환 ───
// 이름: 첫 글자 + ** (1글자이면 그대로+*). 빈값이면 그대로.
// 연락처: 숫자만 추출해 끝 4자리 유지, 앞 마스킹 → 010-****-NNNN 형태. 4자리 미만이면 ****.
function _regMask(row) {
  var out = {};
  Object.keys(row).forEach(function (k) { out[k] = row[k]; });

  // 이름 마스킹
  var name = String(out.name || '');
  if (name) {
    out.name = name.length === 1 ? name + '*' : name.slice(0, 1) + '**';
  }

  // 연락처 마스킹
  var contact = String(out.contact || '');
  if (contact) {
    var digits = contact.replace(/\D/g, '');
    if (digits.length < 4) {
      out.contact = '****';
    } else {
      // 예: 01012345678 → front=0101234(7자) → 010-****-5678
      var tail = digits.slice(-4);
      var front = digits.slice(0, -4);
      if (front.length <= 3) {
        out.contact = front + '-****-' + tail;
      } else if (front.length <= 6) {
        out.contact = front.slice(0, 3) + '-' + '*'.repeat(front.length - 3) + '-' + tail;
      } else {
        out.contact = front.slice(0, 3) + '-****-' + tail;
      }
    }
  }

  // 사진 비공개 — 공개(마스킹) 보드에 원본 Drive 링크 미노출 (PII).
  //   실무 처리용 reg_list(GATED·내부)는 photoUrl 원본 유지.
  if (out.photoUrl) out.photoUrl = '비공개';

  return out;
}

// ─── 종합 접수처 시트 → 객체 배열 (헤더 배열({key,label}[]) 인자) ───
function _regReadAll(sh, headers) {
  var last = sh.getLastRow();
  if (last < 2) return [];
  var data = sh.getRange(2, 1, last - 1, headers.length).getValues();
  return data.map(function (row) {
    var obj = {};
    headers.forEach(function (h, i) {
      var v = row[i];
      if (v instanceof Date) {
        v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      }
      obj[h.key] = v;
    });
    return obj;
  });
}

// ─── 종합 접수처 상태 셀 색상 (헤더 배열 기준) ───
function _regApplyStatusColor(sh, row, status, headers) {
  var idx = -1;
  for (var i = 0; i < headers.length; i++) {
    if (headers[i].key === 'status') { idx = i + 1; break; }
  }
  if (idx < 0) return;
  var color = VOC_STATUS_COLORS[status] || '#ffffff';
  sh.getRange(row, idx).setBackground(color).setFontColor('#ffffff');
}

// ─── 시트 → 객체 배열 ───
function _vReadAll(sh) {
  var last = sh.getLastRow();
  if (last < 2) return [];
  var data = sh.getRange(2, 1, last - 1, VOC_HEADERS.length).getValues();
  return data.map(function (row) {
    var obj = {};
    VOC_HEADERS.forEach(function (h, i) {
      var v = row[i];
      if (v instanceof Date) {
        v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      }
      obj[h] = v;
    });
    return obj;
  });
}

// ─── 접수ID로 행 번호 찾기 (1-based, 헤더 포함) ───
function _vFindRow(sh, id) {
  var last = sh.getLastRow();
  if (last < 2) return -1;
  var ids = sh.getRange(2, 1, last - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(id)) return i + 2;
  }
  return -1;
}

// ─── 상태 셀 색상 ───
function _vApplyStatusColor(sh, row, status) {
  var colIdx = VOC_HEADERS.indexOf('상태') + 1;
  var color = VOC_STATUS_COLORS[status] || '#ffffff';
  sh.getRange(row, colIdx).setBackground(color).setFontColor('#ffffff');
}

// ─── VOC_Photos Drive 폴더 확보 (없으면 생성) ───
function _vGetPhotoFolder() {
  var folderId = _vprop('VOC_PHOTO_FOLDER');
  var folder = null;
  if (folderId) {
    try { folder = DriveApp.getFolderById(folderId); } catch (e) { folder = null; }
  }
  if (!folder) {
    var existing = DriveApp.getRootFolder().getFoldersByName(VOC_PHOTO_FOLDER_NAME);
    folder = existing.hasNext() ? existing.next()
      : DriveApp.getRootFolder().createFolder(VOC_PHOTO_FOLDER_NAME);
    PropertiesService.getScriptProperties().setProperty('VOC_PHOTO_FOLDER', folder.getId());
  }
  return folder;
}

// ─── 사진 업로드 (Base64 → Drive, 공개 링크) — todo_upload 패턴 복제 ───
function _vUploadPhoto(base64, fileName, mimeType) {
  if (!base64) return '';
  // data:image/...;base64, 접두사 방어 (FileReader.readAsDataURL 결과 호환)
  var b64 = String(base64);
  var comma = b64.indexOf(',');
  if (b64.slice(0, 5) === 'data:' && comma >= 0) b64 = b64.slice(comma + 1);
  var folder = _vGetPhotoFolder();
  var blob = Utilities.newBlob(
    Utilities.base64Decode(b64),
    mimeType || 'image/jpeg',
    fileName || ('voc_' + _vNow().replace(/[: ]/g, '_'))
  );
  var file = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return file.getUrl();
}

// ─── 텔레그램 알림 (점검 GAS handleNotify 패턴) — 토큰=ScriptProperties, repo 하드코딩 금지 ───
// 핵심멤버방 chat_id = TELEGRAM_CHAT_ID (점검 GAS와 동일 키명 — GM이 신규 GAS 속성에 동일 등록).
function _vNotifyTelegram(text) {
  var token = _vprop('TELEGRAM_BOT_TOKEN');
  var chatId = _vprop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return false; // 미설정이면 조용히 통과 (제출 자체는 성공)
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
    return true;
  } catch (e) { return false; }
}

// ═══════════════════════════════════════════
//  액션 처리 (doGet/doPost 공용)
// ═══════════════════════════════════════════

// ─── voc_submit — 회원 모바일 폼 제출 ───
function _vSubmit(body) {
  var type = String(body.type || body['유형'] || '').trim();
  var loc = String(body.loc || body.location || body['위치'] || '').trim();
  var content = String(body.content || body['내용'] || '').trim();
  var contact = String(body.contact || body['연락처'] || '').trim();
  var photo = body.photo || body.file || body.base64 || '';
  var fileName = body.fileName || '';
  var mimeType = body.mimeType || 'image/jpeg';

  if (!type && !content) {
    return _vJson({ ok: false, error: '유형 또는 내용 중 하나는 필수입니다.' });
  }

  var photoUrl = '';
  if (photo) {
    try {
      photoUrl = _vUploadPhoto(photo, fileName, mimeType);
    } catch (e) {
      // 사진 실패해도 접수는 진행 (내용 유실 방지)
      photoUrl = '';
    }
  }

  var sh = _vGetSheet();
  var id = _vGenId();
  var now = _vNow();
  var row = new Array(VOC_HEADERS.length).fill('');
  row[VOC_HEADERS.indexOf('접수ID')]   = id;
  row[VOC_HEADERS.indexOf('접수일시')] = now;
  row[VOC_HEADERS.indexOf('유형')]     = type;
  row[VOC_HEADERS.indexOf('위치')]     = loc;
  row[VOC_HEADERS.indexOf('사진URL')]  = photoUrl;
  row[VOC_HEADERS.indexOf('내용')]     = content;
  row[VOC_HEADERS.indexOf('연락처')]   = contact;
  row[VOC_HEADERS.indexOf('상태')]     = '접수';
  var newRow = sh.getLastRow() + 1;
  sh.getRange(newRow, 1, 1, row.length).setValues([row]);
  _vApplyStatusColor(sh, newRow, '접수');

  // 텔레그램 핵심멤버방 알림 (설정 시)
  _vNotifyTelegram(
    '🙋 <b>[회원 VOC 접수]</b>\n' +
    '유형: ' + (type || '-') + '\n' +
    '위치: ' + (loc || '-') + '\n' +
    '내용: ' + (content ? content.slice(0, 120) : '-') +
    (photoUrl ? '\n📷 사진 첨부' : '') +
    (contact ? '\n☎ ' + contact : '') +
    '\n🆔 ' + id
  );

  return _vJson({ ok: true, id: id, photoUrl: photoUrl, message: 'VOC가 접수되었습니다.' });
}

// ─── voc_list — 현황 조회 ───
function _vList(params) {
  var sh = _vGetSheet();
  var items = _vReadAll(sh);
  var status = String((params && params.status) || '').trim();
  var type = String((params && params.type) || '').trim();
  if (status) items = items.filter(function (r) { return String(r['상태']) === status; });
  if (type)   items = items.filter(function (r) { return String(r['유형']) === type; });
  // 최신 접수 우선
  items.reverse();
  return _vJson({ ok: true, count: items.length, data: items });
}

// ─── voc_update — 상태 전환 · 담당 배정 · 처리메모 ───
function _vUpdate(body) {
  var id = body.id || body['접수ID'];
  if (!id) return _vJson({ ok: false, error: 'id 필수' });
  var sh = _vGetSheet();
  var rowNum = _vFindRow(sh, id);
  if (rowNum < 0) return _vJson({ ok: false, error: '해당 접수ID를 찾을 수 없습니다: ' + id });

  var existing = sh.getRange(rowNum, 1, 1, VOC_HEADERS.length).getValues()[0];

  var newStatus = String(body.status || body['상태'] || '').trim();
  if (newStatus) {
    if (VOC_STATUSES.indexOf(newStatus) < 0) {
      return _vJson({ ok: false, error: '상태는 접수|처리중|완료 만 허용' });
    }
    existing[VOC_HEADERS.indexOf('상태')] = newStatus;
  }

  var assignee = body.assignee !== undefined ? body.assignee
    : (body['담당'] !== undefined ? body['담당'] : undefined);
  if (assignee !== undefined) existing[VOC_HEADERS.indexOf('담당')] = String(assignee);

  var memo = body.memo !== undefined ? body.memo
    : (body['처리메모'] !== undefined ? body['처리메모'] : undefined);
  if (memo !== undefined) existing[VOC_HEADERS.indexOf('처리메모')] = String(memo);

  sh.getRange(rowNum, 1, 1, VOC_HEADERS.length).setValues([existing]);
  if (newStatus) _vApplyStatusColor(sh, rowNum, newStatus);

  return _vJson({
    ok: true, id: id,
    status: existing[VOC_HEADERS.indexOf('상태')],
    assignee: existing[VOC_HEADERS.indexOf('담당')],
    message: 'VOC가 갱신되었습니다.'
  });
}

// ═══════════════════════════════════════════
//  종합 접수처 액션
// ═══════════════════════════════════════════

// ─── reg_submit — 종합 접수처 제출 (public) ───
function _regSubmit(body) {
  // 카테고리 해석: 키 우선, 없으면 라벨로 fallback
  var catRaw = String(body.category || '').trim();
  var cat = _regCatByKey(catRaw) || _regCatByLabel(catRaw);
  if (!cat) {
    return _vJson({ ok: false, error: '알 수 없는 카테고리입니다: ' + catRaw });
  }

  // 이름·연락처 — voice + 익명 희망(anonymousPref==='예')이면 필수 면제
  // 점검 자동접수(source==='check')도 필수 면제: 실연락처 없는 시스템 접수라 고정 출처표기로 채움. 2026-06-20 시우·GM.
  var name    = String(body.name    || '').trim();
  var contact = String(body.contact || '').trim();
  var anonPref = String(body.anonymousPref || '').trim();
  var isAnon = (cat.key === 'voice' && anonPref === '예');
  var isCheck = (String(body.source || '').trim() === 'check');
  if (!isAnon && !isCheck && (!name || !contact)) {
    return _vJson({ ok: false, error: '이름과 연락처는 필수입니다.' });
  }
  // 익명 제출 시 빈값을 '익명'으로 저장
  if (isAnon) {
    if (!name)    name    = '익명';
    if (!contact) contact = '익명';
  }
  // 점검 자동접수 시 빈값을 출처 고정표기로 저장
  if (isCheck) {
    if (!name)    name    = '지원부 점검';
    if (!contact) contact = '자동접수(점검)';
  }

  var loc     = String(body.loc     || body.location || '').trim();
  var content = String(body.content || '').trim();
  var photo   = body.photo || body.file || body.base64 || '';
  var fileName = body.fileName || '';
  var mimeType = body.mimeType || 'image/jpeg';

  // 사진 업로드 (실패해도 접수 진행)
  var photoUrl = '';
  if (photo) {
    try { photoUrl = _vUploadPhoto(photo, fileName, mimeType); } catch (e) { photoUrl = ''; }
  }

  var headers = _regHeadersFor(cat.key); // [{key,label}]
  var id  = _vGenId();
  var now = _vNow();

  // 행 구성 — 공통 컬럼 채우기
  var row = new Array(headers.length).fill('');
  var _set = function (key, val) {
    for (var i = 0; i < headers.length; i++) {
      if (headers[i].key === key) { row[i] = val; return; }
    }
  };
  _set('regId',    id);
  _set('category', cat.label);
  _set('createdAt', now);
  _set('name',     name);
  _set('contact',  contact);
  _set('loc',      loc);
  _set('content',  content);
  _set('photoUrl', photoUrl);
  _set('status',   '접수');
  _set('dept',     cat.dept);

  // extras — 영문키로 body에서 꺼내 한글헤더 위치에 삽입
  var extras = REG_EXTRA_HEADERS[cat.key] || [];
  extras.forEach(function (h) {
    if (body[h.key] !== undefined) _set(h.key, String(body[h.key]));
  });

  var sh = _regGetSheet(cat.key);
  var newRow = sh.getLastRow() + 1;
  sh.getRange(newRow, 1, 1, row.length).setValues([row]);
  _regApplyStatusColor(sh, newRow, '접수', headers);

  // 텔레그램 알림 (익명 접수 시 이름 표기)
  _vNotifyTelegram(
    '📋 <b>[종합 접수처]</b> ' + cat.label + '\n' +
    '부서: ' + cat.dept + '\n' +
    '이름: ' + (isAnon ? '익명' : name) + '\n' +
    '위치: ' + (loc || '-') + '\n' +
    '내용: ' + (content ? content.slice(0, 100) : '-') +
    (photoUrl ? '\n📷 사진 첨부' : '') +
    '\n🆔 ' + id
  );

  return _vJson({ ok: true, id: id, dept: cat.dept });
}

// ─── reg_list — 종합 접수처 목록 조회 (GATED) ───
function _regList(params) {
  var filterCat    = String((params && params.category) || '').trim();
  var filterDept   = String((params && params.dept)     || '').trim();
  var filterStatus = String((params && params.status)   || '').trim();

  var all = [];

  // category 지정 시 해당 시트만, 없으면 전 시트
  var targets = filterCat ? [_regCatByKey(filterCat) || _regCatByLabel(filterCat)] : REG_CATEGORIES;
  targets.forEach(function (cat) {
    if (!cat) return;
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var headers = _regHeadersFor(cat.key);
    var rows = _regReadAll(sh, headers);
    rows.forEach(function (r) { all.push(r); });
  });

  // 필터
  if (filterDept)   all = all.filter(function (r) { return String(r.dept   || '') === filterDept;   });
  if (filterStatus) all = all.filter(function (r) { return String(r.status || '') === filterStatus; });
  if (filterCat) {
    var catObj = _regCatByKey(filterCat) || _regCatByLabel(filterCat);
    if (catObj) all = all.filter(function (r) { return String(r.category || '') === catObj.label; });
  }

  // 접수일시 desc
  all.sort(function (a, b) {
    return String(b.createdAt || '') > String(a.createdAt || '') ? 1 : -1;
  });

  return _vJson({ ok: true, count: all.length, data: all });
}

// ─── reg_update — 종합 접수처 갱신 (GATED) ───
function _regUpdate(body) {
  var id = String(body.id || body['접수ID'] || '').trim();
  if (!id) return _vJson({ ok: false, error: 'id 필수' });

  var newStatus = String(body.status || '').trim();
  if (newStatus && VOC_STATUSES.indexOf(newStatus) < 0) {
    return _vJson({ ok: false, error: '상태는 접수|처리중|완료 만 허용' });
  }

  // category 지정 시 해당 시트만, 없으면 전 시트 순회
  var catRaw = String(body.category || '').trim();
  var targets = catRaw
    ? [_regCatByKey(catRaw) || _regCatByLabel(catRaw)]
    : REG_CATEGORIES;

  for (var i = 0; i < targets.length; i++) {
    var cat = targets[i];
    if (!cat) continue;
    var headers = _regHeadersFor(cat.key);
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { continue; }
    var rowNum = _vFindRow(sh, id);
    if (rowNum < 0) continue;

    // 현재 행 읽기
    var existing = sh.getRange(rowNum, 1, 1, headers.length).getValues()[0];
    var _idx = function (key) {
      for (var j = 0; j < headers.length; j++) {
        if (headers[j].key === key) return j;
      }
      return -1;
    };

    if (newStatus) existing[_idx('status')] = newStatus;

    var assignee = body.assignee !== undefined ? body.assignee : undefined;
    if (assignee !== undefined) {
      var ai = _idx('assignee');
      if (ai >= 0) existing[ai] = String(assignee);
    }
    var memo = body.memo !== undefined ? body.memo : undefined;
    if (memo !== undefined) {
      var mi = _idx('memo');
      if (mi >= 0) existing[mi] = String(memo);
    }

    sh.getRange(rowNum, 1, 1, headers.length).setValues([existing]);
    if (newStatus) _regApplyStatusColor(sh, rowNum, newStatus, headers);

    var statusIdx = _idx('status');
    var assigneeIdx = _idx('assignee');
    return _vJson({
      ok: true, id: id,
      status:   statusIdx  >= 0 ? existing[statusIdx]  : '',
      assignee: assigneeIdx >= 0 ? existing[assigneeIdx] : '',
      message: '접수건이 갱신되었습니다.'
    });
  }

  return _vJson({ ok: false, error: '해당 접수ID를 찾을 수 없습니다: ' + id });
}

// ═══════════════════════════════════════════
//  접근 게이트 (PII 보호 — TOKEN_ENFORCE 스위치)
// ═══════════════════════════════════════════
// ★ 불변식: TOKEN_ENFORCE 가 '1' 이 아니면(기본값) 모든 액션 통과 → 코드 배포만으로는 라이브 영향 0.
//   GM 활성화 절차:
//   ① ScriptProperties ACCESS_TOKEN = <강한 무작위 문자열> 설정
//   ② 웹앱 새 버전 재배포
//   ③ 직원 화면에서 열쇠 1회 입력 확인 (localStorage wp_access_token)
//   ④ ScriptProperties TOKEN_ENFORCE = 1 설정 후 웹앱 새 버전 재배포 → 게이트 발효
var _VOC_PUBLIC_ACTIONS = {
  voc_submit:  true,  // 회원 모바일 폼 제출 — 토큰 면제
  voc_types:   true,  // 유형·상태 목록 조회 — 토큰 면제
  reg_submit:  true,  // 종합 접수처 제출 — 토큰 면제
  reg_board:   true,  // 마스킹 공개 보드 — 이름·연락처 가려서 반환, 토큰 면제
  reg_update:  true   // 상태·담당·메모 갱신 — PII 미포함, 토큰 면제
  // ⚠️ reg_list 는 전체 PII(이름·연락처 원문) 포함 — 절대 public 금지, GATED 유지.
  // voc_list / voc_update 도 게이트 적용.
};
function _vAccessProp_(k) {
  try { return PropertiesService.getScriptProperties().getProperty(k) || ''; } catch (e) { return ''; }
}
function _vCheckAccess_(action, key) {
  if (_VOC_PUBLIC_ACTIONS[action]) return true;            // 공개 액션은 항상 통과
  if (_vAccessProp_('TOKEN_ENFORCE') !== '1') return true; // 스위치 OFF(기본) = 현행 무중단
  var tok = _vAccessProp_('ACCESS_TOKEN');
  if (!tok) return true;                                   // 토큰 미설정 = 안전을 위해 통과
  return String(key || '') === tok;
}

// 공용 라우터 (doGet/doPost)
function _vProcess(action, body, params) {
  // ─── 접근 게이트 확인 ───
  var _gateKey = (body && body.key) || (params && params.key) || '';
  if (!_vCheckAccess_(action, _gateKey)) {
    return _vJson({ ok: false, error: 'unauthorized' });
  }

  // ── 종합 접수처 액션 ──
  if (action === 'reg_submit') return _regSubmit(body);
  if (action === 'reg_list')   return _regList(params || body);
  if (action === 'reg_board') {
    // 마스킹 공개 보드 — _regList 결과에 _regMask 적용
    var boardResult = JSON.parse(_regList(params || body).getContent());
    var masked = (boardResult.data || []).map(_regMask);
    return _vJson({ ok: true, count: masked.length, data: masked });
  }
  if (action === 'reg_update') return _regUpdate(body);

  // ── 레거시 VOC 액션 (하위호환) ──
  if (action === 'voc_submit') return _vSubmit(body);
  if (action === 'voc_update') {
    // 레거시 시트 먼저 시도, 없으면 전 reg 시트 순회
    var legacySh = _vGetSheet();
    var legacyRow = _vFindRow(legacySh, body.id || body['접수ID'] || '');
    if (legacyRow >= 0) return _vUpdate(body);
    return _regUpdate(body);
  }
  if (action === 'voc_list') {
    // 레거시 시트 결과 + 전 reg 시트 결과 병합
    var legacyResult = JSON.parse(_vList(params || body).getContent());
    var regResult    = JSON.parse(_regList(params || body).getContent());
    var merged = (legacyResult.data || []).concat(regResult.data || []);
    merged.sort(function (a, b) {
      var ta = String(a['접수일시'] || a.createdAt || '');
      var tb = String(b['접수일시'] || b.createdAt || '');
      return tb > ta ? 1 : -1;
    });
    return _vJson({ ok: true, count: merged.length, data: merged });
  }
  if (action === 'voc_types')  return _vJson({
    ok: true,
    types:      VOC_TYPES,
    statuses:   VOC_STATUSES,
    categories: REG_CATEGORIES
  });
  return _vJson({ ok: false, error: '알 수 없는 action: ' + action });
}

// ═══════════════════════════════════════════
//  doGet — 조회 + POST redirect 우회
// ═══════════════════════════════════════════
function doGet(e) {
  try {
    var action = (e && e.parameter && e.parameter.action) || '';
    // POST redirect 우회: voc_ write action 이 GET 으로 와도 본문 병합 후 처리
    if (action === 'voc_submit' || action === 'voc_update' ||
        action === 'reg_submit' || action === 'reg_update') {
      var body = {};
      Object.keys(e.parameter).forEach(function (k) { body[k] = e.parameter[k]; });
      if (e.postData && e.postData.contents) {
        try {
          var pb = JSON.parse(e.postData.contents);
          Object.keys(pb).forEach(function (k) { body[k] = pb[k]; });
        } catch (ignored) {}
      }
      return _vProcess(action, body, e.parameter);
    }
    return _vProcess(action, e.parameter, e.parameter);
  } catch (err) {
    return _vJson({ ok: false, error: err.message });
  }
}

// ═══════════════════════════════════════════
//  doPost — 제출 / 갱신 (사진 base64 = POST 본문)
// ═══════════════════════════════════════════
function doPost(e) {
  try {
    var body = {};
    if (e && e.postData && e.postData.contents) {
      try { body = JSON.parse(e.postData.contents); } catch (pe) { body = {}; }
    }
    // application/x-www-form-urlencoded 폴백
    if (e && e.parameter) {
      Object.keys(e.parameter).forEach(function (k) {
        if (body[k] === undefined) body[k] = e.parameter[k];
      });
    }
    var action = body.action || (e && e.parameter && e.parameter.action) || '';
    return _vProcess(action, body, body);
  } catch (err) {
    return _vJson({ ok: false, error: err.message });
  }
}
