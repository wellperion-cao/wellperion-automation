// 웰페리온 회원 종합 접수처 전용 Apps Script (QR + 사진)
// ⚠️ 점검 GAS(coo/check/apps_script_v3.js)·업무 GAS(coo/todo/apps_script_todo.js)와
//    완전 독립 — 절대 그 위에 얹지 말 것. 신규 전용 GAS 프로젝트로 배포한다.
// ⚠️ 라이브 '이슈 응답' 시트는 건드리지 않는다. 접수는 별도 시트 탭 「접수 VOC」(레거시 탭명).
//
// 액션:
//   voc_submit (POST) — 회원 모바일 폼 제출: 유형·위치·사진base64·내용·(선택)연락처
//                       → Drive 접수사진 폴더 저장 → 공개 URL → 시트 append (상태=접수)
//                       → (설정 시) 텔레그램 핵심멤버방 알림
//   voc_list   (GET)  — 현황 조회: 전체 또는 상태/유형 필터
//   voc_update (POST) — 상태 전환(접수→처리중→완료) · 담당 배정 · 처리메모
//
// 사진은 POST 본문 base64 필수 (GET 쿼리는 유실 — reference_gas_file_upload_must_post).
// 검증은 브라우저로 (curl -L은 GAS 302에서 POST 본문을 떨궈 검증 불가).
//
// 보안(후속 과제 · 이번 차단 아님): 무인증 공개 엔드포인트 → 변조·스팸 위험.
//   최소 hidden token / rate-limit 은 ScriptProperties(RECEPTION_SUBMIT_TOKEN) 기반으로 후속 적용.
//   토큰·챗ID 등 비밀값은 절대 repo 하드코딩 금지 — 전부 ScriptProperties 서버측 보관.

// ─── 상수 ───
// ★값 '접수 VOC' 는 실제 구글시트 탭 이름이다 — 코드에서만 바꾸면 시트를 못 찾는다.
//   이름 정리는 구글시트 탭을 함께 바꿔야 완결되므로 별건으로 남긴다(2026-07-27 시우).
var LEGACY_RECEPTION_SHEET = '접수 VOC';
var LEGACY_RECEPTION_HEADERS = [
  '접수ID', '접수일시', '유형', '위치', '사진URL',
  '내용', '연락처', '상태', '담당', '처리메모'
];
var LEGACY_RECEPTION_STATUSES = ['접수', '처리중', '완료'];
var LEGACY_RECEPTION_STATUS_COLORS = {
  '접수':  '#e6944e', // 주황
  '처리중': '#5b9fd5', // 파랑
  '완료':  '#6abf7b'  // 초록
};
// ★값 'VOC_Photos' 는 실제 구글드라이브 폴더 이름이다 — 코드만 바꾸면 새 폴더가 생겨
//   기존 접수 사진과 갈라진다. 드라이브 폴더를 함께 바꿔야 완결(별건, 2026-07-27 시우).
var RECEPTION_PHOTO_FOLDER_NAME = 'VOC_Photos';

// ─── 종합 접수처 상수 ───
// REG_CATEGORIES: 카테고리 라우팅 SSOT. dept 변경 시 여기 한 줄만 수정.
// slaHours: 처리기한(SLA) SSOT — 보드에 하드코딩 복사 금지. null = SLA 없음(칭찬: 표시·계산 제외).
var REG_CATEGORIES = [
  { key: 'lost',     label: '분실물 접수',         sheet: '접수_분실물',   dept: '운영부', slaHours: 168 },
  { key: 'facility', label: '시설물 고장 접수',     sheet: '접수_시설고장', dept: '시설부', slaHours: 24 },
  { key: 'clean',    label: '청결 이슈 접수',       sheet: '접수_청결',     dept: '지원부', slaHours: 12 },
  { key: 'praise',   label: '직원·강사 칭찬합니다', sheet: '접수_칭찬',     dept: '운영부', slaHours: null },
  { key: 'voice',    label: '직원·강사 쓴소리합니다', sheet: '접수_쓴소리', dept: '운영부', slaHours: 72 },
  { key: 'complaint', label: '컴플레인 접수',        sheet: '접수_컴플레인', dept: '운영부', slaHours: 48 }
  // praise/voice → dept: '인사부' 로 바꿀 때 위 두 줄만 수정
];

// 공통 12컬럼 (영문키: 한글헤더)
var REG_COMMON_HEADERS = [
  { key: 'regId',     label: '접수ID'   },
  { key: 'category',  label: '카테고리' },
  { key: 'createdAt', label: '접수일시' },
  { key: 'name',      label: '이름'     },
  { key: 'contact',   label: '연락처'   },
  { key: 'loc',       label: '장소'     },
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
    { key: 'lostWhen',   label: '분실시점'   }
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
  praise:   [
    { key: 'targetStaff', label: '대상직원·강사' },
    { key: 'episode',     label: '사례'          }
  ],
  voice:    [
    { key: 'targetStaff',    label: '대상직원·강사' },
    { key: 'episode',        label: '사례'          },
    { key: 'anonymousPref',  label: '익명희망'      }
  ],
  complaint: [
    { key: 'area',        label: '분야'     },
    { key: 'occurredAt',  label: '발생시점' }
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
// 사진 미수집 카테고리 — GM 결정(2026-07-08): 칭찬·쓴소리는 폼+시트컬럼 모두 사진 제거.
// _regHeadersFor 가 photoUrl 을 정의에서 빼야 reg_submit/reg_update 의 위치기반(_set) 쓰기가
// clean_reg_columns 로 물리 삭제된 실제 시트 컬럼과 계속 정렬된다(안 그러면 컬럼 밀림 발생).
var REG_NO_PHOTO_CATS = { praise: true, voice: true };

// 카테고리 키에 대한 전체 헤더 배열 반환 ({key,label}[])
function _regHeadersFor(catKey) {
  var extra = REG_EXTRA_HEADERS[catKey] || [];
  var common = REG_NO_PHOTO_CATS[catKey]
    ? REG_COMMON_HEADERS.filter(function (h) { return h.key !== 'photoUrl'; })
    : REG_COMMON_HEADERS;
  return common.concat(extra);
}

// ─── ScriptProperties 헬퍼 ───
function _vprop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}
// 2026-07-27 'VOC' 낱말 폐기(GM 지시)로 속성 키 이름도 RECEPTION_* 로 옮긴다.
// 다만 속성은 GAS 프로젝트에 저장된 '라이브 상태'라 코드만 바꾸면 값이 사라진 것처럼 보인다.
// → 새 키를 먼저 보고, 없으면 옛 키를 본다. 속성을 손으로 옮기지 않아도 안 멈춘다(무중단 개명).
// 옛 키를 지우는 건 나중에 해도 되고, 안 지워도 해가 없다.
function _vpropCompat(newKey, oldKey) {
  return _vprop(newKey) || _vprop(oldKey);
}

// ─── 접수 위조 방지 게이트 (시토 2026-06-29 GM '접수 막고 보완') ───
// 공개 폼(voc_mobile_form.html)이 숨김토큰 t 를 함께 보내야 reg_submit/voc_submit 통과 + 속도제한.
// 역롤백(즉시·재배포 불요): ScriptProperties RECEPTION_GATE_OFF='1'(옛 키 VOC_GATE_OFF 도 계속 인정) → 게이트 해제.
//   토큰 교체=ScriptProperties RECEPTION_SUBMIT_TOKEN(옛 키 VOC_SUBMIT_TOKEN 폴백, 둘 다 없으면 코드 기본).
// ★토큰 '값'은 폼 6개와 문자 그대로 대조된다 — 이름만 바꾸고 값은 절대 건드리지 않는다(바꾸면 접수가 즉시 막힌다).
// ⚠ 한계: 토큰이 폼(클라이언트)에 노출 → 봇·무차별 위조는 막지만 소스를 본 사람은 우회 가능. 진짜 인증=자체서버 JWT(시토 21, 2026-09 통합).
var RECEPTION_SUBMIT_TOKEN_DEFAULT = 'wlp_voc_7b3f9a2e6c1d4085';
var RECEPTION_SUBMIT_GATE_ENFORCE  = true;   // 코드 기본 ON. OFF=ScriptProperties RECEPTION_GATE_OFF='1'(즉시) 또는 이 값 false 후 재배포.
function _vSubmitGateOk_(body) {
  if (_vpropCompat('RECEPTION_GATE_OFF', 'VOC_GATE_OFF') === '1') return true;   // 즉시 역롤백 스위치
  if (!RECEPTION_SUBMIT_GATE_ENFORCE) return true;
  var expected = _vpropCompat('RECEPTION_SUBMIT_TOKEN', 'VOC_SUBMIT_TOKEN') || RECEPTION_SUBMIT_TOKEN_DEFAULT;
  var got = String((body && (body.t || body.token)) || '');
  return got === expected;
}
function _vFp_(s) {   // 가벼운 내용 지문(중복 차단용)
  var str = String(s || ''), h = 0;
  for (var i = 0; i < str.length; i++) { h = ((h << 5) - h + str.charCodeAt(i)) | 0; }
  return String(h);
}
function _vRateLimitOk_(fp) {   // 전역 분당 상한 + 동일내용 60초 중복 차단. 캐시 장애 시 통과(접수 우선).
  try {
    var cache = CacheService.getScriptCache();
    var cur = parseInt(cache.get('voc_rl_min') || '0', 10);
    if (cur >= 40) return false;
    cache.put('voc_rl_min', String(cur + 1), 60);
    if (fp) {
      var dk = 'voc_rl_dup_' + fp;
      if (cache.get(dk)) return false;
      cache.put(dk, '1', 60);
    }
    return true;
  } catch (e) { return true; }
}

// ─── 유틸 ───
function _vNow() {
  return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
}
// ─── 접수번호 접두사 — 화면·알림에 그대로 노출되는 값이라 여기 한 곳에서만 정한다 ───
// 2026-07-27 GM 지시: 'VOC' 낱말 폐기 → 'RECEPTION'. 숫자는 건드리지 않는다(기존 참조 보존).
// 옛 접두사는 이미 시트에 쌓인 값을 알아보기 위해 남겨둔다(reg_reprefix 마이그레이션이 쓴다).
var REG_ID_PREFIX     = 'RECEPTION-';
var REG_ID_PREFIX_OLD = 'VOC-';

// ─── 전체 통합 순번 ID — RECEPTION-1, RECEPTION-2 … (식별자 겸 순번) ───
// ScriptProperties 'RECEPTION_SEQ'(옛 키 'VOC_SEQ' 폴백)를 단조증가(monotonic) 카운터로 사용
//   → 행을 삭제해도 번호 재사용 안 함(식별자 안정).
//   ※ 개명 무중단 방식: 읽을 땐 새 키→옛 키 순으로 보고, 쓸 땐 새 키에만 쓴다. 첫 접수 때
//     옛 값(예 69)을 읽어 70을 새 키에 적으므로 번호가 되감기지 않는다. 속성 수동 이관 불요.
// LockService 로 동시 접수 시 같은 번호 발급 충돌 방지. 6종 카테고리 통틀어 하나의 일련번호.
function _vNextSeqId() {
  var lock = LockService.getScriptLock();
  try { lock.waitLock(5000); } catch (e) {}
  var props = PropertiesService.getScriptProperties();
  var cur = parseInt(_vpropCompat('RECEPTION_SEQ', 'VOC_SEQ') || '0', 10);
  if (isNaN(cur)) cur = 0;
  var next = cur + 1;
  props.setProperty('RECEPTION_SEQ', String(next));
  try { lock.releaseLock(); } catch (e) {}
  return REG_ID_PREFIX + next;
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
// GM 액션: 프로젝트 설정 → 스크립트 속성 → SPREADSHEET_ID = 접수 데이터를 넣을 시트의 ID
//   (시트 URL: https://docs.google.com/spreadsheets/d/<여기>/edit  ← 이 부분이 ID)
function _vGetSpreadsheet() {
  var ssId = _vprop('SPREADSHEET_ID');
  if (!ssId) throw new Error('ScriptProperties에 SPREADSHEET_ID 미설정 — 프로젝트 설정 → 스크립트 속성에 추가');
  return SpreadsheetApp.openById(ssId);
}

// ─── 시트 확보 (없으면 자동 생성 + 헤더) ───
function _vGetSheet() {
  var ss = _vGetSpreadsheet();
  var sh = ss.getSheetByName(LEGACY_RECEPTION_SHEET);
  if (sh) {
    // 헤더 누락 시 보강 (빈 시트 안전)
    if (sh.getLastRow() < 1) {
      sh.getRange(1, 1, 1, LEGACY_RECEPTION_HEADERS.length).setValues([LEGACY_RECEPTION_HEADERS]);
    }
    return sh;
  }
  sh = ss.insertSheet(LEGACY_RECEPTION_SHEET);
  sh.getRange(1, 1, 1, LEGACY_RECEPTION_HEADERS.length).setValues([LEGACY_RECEPTION_HEADERS]);
  sh.getRange(1, 1, 1, LEGACY_RECEPTION_HEADERS.length)
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
// 직원 현황 보드 사진 노출 키(커튼 수준·공개값 — gate.js와 동일 모델). 현황(gate.js 뒤)만 pv=<이 값>으로 사진 썸네일 노출. 공개 reg_board는 계속 '비공개'.
var REG_STAFF_PHOTO_KEY = 'wlp_reg_pv_2026';

function _regMask(row, staffPhoto) {
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
  //   단, 직원 현황(gate.js 뒤)이 pv 키로 호출하면 원본 유지 → 현황 카드 썸네일용.
  //   실무 처리용 reg_list(GATED·내부)는 photoUrl 원본 유지.
  if (out.photoUrl && !staffPhoto) out.photoUrl = '비공개';

  return out;
}

// ─── SLA(처리기한) 계산 — 카드 객체에 기한/남은시간/상태 부여 ───
// SSOT = REG_CATEGORIES[].slaHours. 보드에 하드코딩 금지.
// 규칙: 완료 상태 → 계산 제외(sla='완료'). slaHours=null(칭찬 등) → slaStatus='-'(SLA 없음).
// 임박 기준: 남은시간 ≤ SLA의 25% 또는 ≤ 2h (둘 중 하나라도 해당 시 '임박').
// 접수일시 'yyyy-MM-dd HH:mm:ss'(Asia/Seoul) 파싱. 반환 객체에 다음 키 추가:
//   slaHours(원 기한), deadline('yyyy-MM-dd HH:mm'), remainH(남은시간·소수1자리·음수=초과), slaStatus('정상'|'임박'|'초과'|'완료'|'-')
function _regComputeSla(row) {
  var out = {};
  Object.keys(row).forEach(function (k) { out[k] = row[k]; });

  var status = String(out.status || out['상태'] || '');
  var catLabel = String(out.category || out['카테고리'] || '');
  var cat = _regCatByLabel(catLabel) || _regCatByKey(catLabel);
  var slaHours = cat ? cat.slaHours : null;

  out.slaHours = slaHours;
  // SLA 없는 카테고리(칭찬 등)
  if (slaHours === null || slaHours === undefined || slaHours === 0) {
    out.slaStatus = '-';
    out.remainH = null;
    out.deadline = '';
    return out;
  }
  // 완료건은 계산 제외
  if (status === '완료') {
    out.slaStatus = '완료';
    out.remainH = null;
    out.deadline = '';
    return out;
  }

  var createdStr = String(out.createdAt || out['접수일시'] || '').trim();
  // 'yyyy-MM-dd HH:mm:ss' → Date (Asia/Seoul로 저장됨)
  var m = createdStr.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) {
    out.slaStatus = '-';
    out.remainH = null;
    out.deadline = '';
    return out;
  }
  var created = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  var deadline = new Date(created.getTime() + slaHours * 3600 * 1000);
  var now = new Date();
  var remainMs = deadline.getTime() - now.getTime();
  var remainH = remainMs / 3600000;

  out.deadline = Utilities.formatDate(deadline, 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
  out.remainH = Math.round(remainH * 10) / 10;

  if (remainH < 0) {
    out.slaStatus = '초과';
  } else if (remainH <= slaHours * 0.25 || remainH <= 2) {
    out.slaStatus = '임박';
  } else {
    out.slaStatus = '정상';
  }
  return out;
}

// ─── 종합 접수처 라벨→키 별칭 (시트 실헤더 라벨 드리프트 흡수 · SSOT) ───
// 시트 1행 실제 라벨이 REG_COMMON/EXTRA_HEADERS 정의 라벨과 다른 경우(예: 분실물 탭)를 흡수.
var REG_LABEL_ALIASES = { '분실위치': 'loc', '위치': 'loc', '물품상세': 'content' };   // '위치'·'분실위치' = loc 구헤더 하위호환(장소 rename 전/후 모두 정독). '장소'는 REG_COMMON_HEADERS 정의라 자동 매핑.

// ─── 종합 접수처 시트 → 객체 배열 (헤더-이름 기준 매핑 · 컬럼 물리삭제/순서변경에 안전) ───
// headers({key,label}[])로 라벨→키 맵을 만들고, 시트 1행 실제 헤더 라벨로 각 열의 키를 찾는다.
// 매칭 안 되는 컬럼(빈칸·잔재 라벨)은 조용히 무시 — 위치기반이 아니므로 중간 컬럼 삭제에도 값이 안 밀림.
function _regReadAll(sh, headers) {
  var lastCol = sh.getLastColumn();
  var last = sh.getLastRow();
  if (last < 2 || lastCol < 1) return [];

  var label2key = {};
  headers.forEach(function (h) { label2key[h.label] = h.key; });
  Object.keys(REG_LABEL_ALIASES).forEach(function (label) {
    if (!(label in label2key)) label2key[label] = REG_LABEL_ALIASES[label];
  });

  var sheetHeaderLabels = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(String);
  var data = sh.getRange(2, 1, last - 1, lastCol).getValues();
  return data.map(function (row) {
    var obj = {};
    sheetHeaderLabels.forEach(function (label, i) {
      var key = label2key[label];
      if (!key) return; // 매칭 안 되는 컬럼(빈칸·잔재)은 무시
      var v = row[i];
      if (v instanceof Date) {
        v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      }
      obj[key] = v;
    });
    return obj;
  });
}

// ─── 종합 접수처 상태 셀 색상 ───
// 실제 시트 1행에서 '상태' 라벨 위치를 우선 탐색(컬럼 삭제/이동에도 안전) — 못 찾으면
// 정의(headers) 기반 위치로 폴백(기존 동작 유지, index 기반 그대로).
function _regApplyStatusColor(sh, row, status, headers) {
  var idx = 0;
  try {
    var lastCol = sh.getLastColumn();
    var actualLabels = sh.getRange(1, 1, 1, lastCol).getValues()[0];
    idx = actualLabels.indexOf('상태') + 1; // 1-based; 0 이면 못 찾음
  } catch (e) { idx = 0; }
  if (idx <= 0) {
    for (var i = 0; i < headers.length; i++) {
      if (headers[i].key === 'status') { idx = i + 1; break; }
    }
  }
  if (idx <= 0) return;
  var color = LEGACY_RECEPTION_STATUS_COLORS[status] || '#ffffff';
  sh.getRange(row, idx).setBackground(color).setFontColor('#ffffff');
}

// ─── 시트 → 객체 배열 ───
function _vReadAll(sh) {
  var last = sh.getLastRow();
  if (last < 2) return [];
  var data = sh.getRange(2, 1, last - 1, LEGACY_RECEPTION_HEADERS.length).getValues();
  return data.map(function (row) {
    var obj = {};
    LEGACY_RECEPTION_HEADERS.forEach(function (h, i) {
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
  var colIdx = LEGACY_RECEPTION_HEADERS.indexOf('상태') + 1;
  var color = LEGACY_RECEPTION_STATUS_COLORS[status] || '#ffffff';
  sh.getRange(row, colIdx).setBackground(color).setFontColor('#ffffff');
}

// ─── 접수 사진 Drive 폴더 확보 (없으면 생성 · 폴더명 VOC_Photos = 기존 자원명) ───
function _vGetPhotoFolder() {
  var folderId = _vpropCompat('RECEPTION_PHOTO_FOLDER', 'VOC_PHOTO_FOLDER');
  var folder = null;
  if (folderId) {
    try { folder = DriveApp.getFolderById(folderId); } catch (e) { folder = null; }
  }
  if (!folder) {
    var existing = DriveApp.getRootFolder().getFoldersByName(RECEPTION_PHOTO_FOLDER_NAME);
    folder = existing.hasNext() ? existing.next()
      : DriveApp.getRootFolder().createFolder(RECEPTION_PHOTO_FOLDER_NAME);
    PropertiesService.getScriptProperties().setProperty('RECEPTION_PHOTO_FOLDER', folder.getId());
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

// ─── Drive URL/문자열에서 파일ID 추출 (사진 sendPhoto용) ───
// _vUploadPhoto 는 file.getUrl() 만 반환 → sendPhoto 시 blob 로딩에 필요한 fileId 를 URL 에서 파싱.
// 지원 형태: .../d/{id}/... · ?id={id} · &id={id}
function _vExtractFileId_(url) {
  var s = String(url || '');
  var m = s.match(/\/d\/([a-zA-Z0-9_-]+)/) || s.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  return m ? m[1] : '';
}

// ─── 텔레그램 알림 (점검 GAS handleNotify 패턴) — 토큰=ScriptProperties, repo 하드코딩 금지 ───
// 핵심멤버방 chat_id = TELEGRAM_CHAT_ID (점검 GAS와 동일 키명 — GM이 신규 GAS 속성에 동일 등록).
// photoUrl 있으면 sendPhoto(Drive blob 업로드, caption=text) 시도, 실패 시 sendMessage 폴백 → 알림 절대 유실 금지.
function _vNotifyTelegram(text, photoUrl) {
  var token = _vprop('TELEGRAM_BOT_TOKEN');
  var chatId = _vprop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return false; // 미설정이면 조용히 통과 (제출 자체는 성공)
  var base = 'https://api.telegram.org/bot' + token;

  // 사진 첨부: Drive URL 직접 전달은 인증 때문에 텔레그램이 못 받음 → blob 을 multipart 로 업로드.
  if (photoUrl) {
    try {
      var fileId = _vExtractFileId_(photoUrl);
      if (fileId) {
        var blob = DriveApp.getFileById(fileId).getBlob();
        var caption = String(text || '');
        if (caption.length > 1024) caption = caption.slice(0, 1024); // 텔레그램 caption 상한
        var resp = UrlFetchApp.fetch(base + '/sendPhoto', {
          method: 'post',
          payload: { chat_id: chatId, caption: caption, parse_mode: 'HTML', photo: blob },
          muteHttpExceptions: true
        });
        if (resp.getResponseCode() === 200) return true;
        // 200 아니면 아래 sendMessage 폴백으로 진행
      }
    } catch (e) { /* blob 로딩·전송 실패 → sendMessage 폴백 */ }
  }

  try {
    UrlFetchApp.fetch(base + '/sendMessage', {
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
  var id = _vNextSeqId();
  var now = _vNow();
  var row = new Array(LEGACY_RECEPTION_HEADERS.length).fill('');
  row[LEGACY_RECEPTION_HEADERS.indexOf('접수ID')]   = id;
  row[LEGACY_RECEPTION_HEADERS.indexOf('접수일시')] = now;
  row[LEGACY_RECEPTION_HEADERS.indexOf('유형')]     = type;
  row[LEGACY_RECEPTION_HEADERS.indexOf('위치')]     = loc;
  row[LEGACY_RECEPTION_HEADERS.indexOf('사진URL')]  = photoUrl;
  row[LEGACY_RECEPTION_HEADERS.indexOf('내용')]     = content;
  row[LEGACY_RECEPTION_HEADERS.indexOf('연락처')]   = contact;
  row[LEGACY_RECEPTION_HEADERS.indexOf('상태')]     = '접수';
  var newRow = sh.getLastRow() + 1;
  sh.getRange(newRow, 1, 1, row.length).setValues([row]);
  _vApplyStatusColor(sh, newRow, '접수');

  // 텔레그램 핵심멤버방 알림 (설정 시) — 사진 있으면 sendPhoto 로 실제 첨부
  _vNotifyTelegram(
    '🙋 <b>[회원 접수]</b>\n' +
    '유형: ' + (type || '-') + '\n' +
    '위치: ' + (loc || '-') + '\n' +
    '내용: ' + (content ? content.slice(0, 120) : '-') + '\n' +
    (contact ? '☎ ' + contact + '\n' : '') +
    '🕒 ' + now,
    photoUrl
  );

  return _vJson({ ok: true, id: id, photoUrl: photoUrl, message: '접수되었습니다.' });
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

  var existing = sh.getRange(rowNum, 1, 1, LEGACY_RECEPTION_HEADERS.length).getValues()[0];

  var newStatus = String(body.status || body['상태'] || '').trim();
  if (newStatus) {
    if (LEGACY_RECEPTION_STATUSES.indexOf(newStatus) < 0) {
      return _vJson({ ok: false, error: '상태는 접수|처리중|완료 만 허용' });
    }
    existing[LEGACY_RECEPTION_HEADERS.indexOf('상태')] = newStatus;
  }

  var assignee = body.assignee !== undefined ? body.assignee
    : (body['담당'] !== undefined ? body['담당'] : undefined);
  if (assignee !== undefined) existing[LEGACY_RECEPTION_HEADERS.indexOf('담당')] = String(assignee);

  var memo = body.memo !== undefined ? body.memo
    : (body['처리메모'] !== undefined ? body['처리메모'] : undefined);
  if (memo !== undefined) existing[LEGACY_RECEPTION_HEADERS.indexOf('처리메모')] = String(memo);

  sh.getRange(rowNum, 1, 1, LEGACY_RECEPTION_HEADERS.length).setValues([existing]);
  if (newStatus) _vApplyStatusColor(sh, rowNum, newStatus);

  return _vJson({
    ok: true, id: id,
    status: existing[LEGACY_RECEPTION_HEADERS.indexOf('상태')],
    assignee: existing[LEGACY_RECEPTION_HEADERS.indexOf('담당')],
    message: '접수건이 갱신되었습니다.'
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
  var id  = _vNextSeqId();
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

  // 최신 접수가 시트 상단에 오도록 접수일시(createdAt) 내림차순 정렬 (헤더 1행 고정) — GM 2026-07-15.
  //   행 전체(색상 포함)가 함께 이동하므로 상태색·사진URL 등 정합 유지. reg_update/delete 는 ID 스캔이라 행위치 무관.
  try { _regSortSheetDesc(sh, headers); } catch (e) {}

  // 텔레그램 알림 (익명 접수 시 이름 표기) — 사진 있으면 sendPhoto 로 실제 첨부
  _vNotifyTelegram(
    '📋 <b>[종합 접수처]</b> ' + cat.label + '\n' +
    '부서: ' + cat.dept + '\n' +
    '이름: ' + (isAnon ? '익명' : name) + '\n' +
    '위치: ' + (loc || '-') + '\n' +
    '내용: ' + (content ? content.slice(0, 100) : '-') + '\n' +
    '🕒 ' + now,
    photoUrl
  );

  _regBoardCacheClear_();
  return _vJson({ ok: true, id: id, dept: cat.dept });
}

// ─── 접수일시(createdAt) 내림차순 정렬 — 최신이 상단 (헤더 1행 고정) ───
//   createdAt = 'yyyy-MM-dd HH:mm:ss'(제로패딩) 문자열이라 문자열 desc = 시간 desc.
//   행 단위 sort 라 상태색 배경·모든 셀이 함께 이동(정합 유지). GM 2026-07-15 시우.
function _regSortSheetDesc(sh, headers) {
  var ci = 0;
  for (var i = 0; i < headers.length; i++) {
    if (headers[i].key === 'createdAt') { ci = i + 1; break; }
  }
  if (!ci) return;
  var lastRow = sh.getLastRow();
  var lastCol = sh.getLastColumn();
  if (lastRow > 2) {
    sh.getRange(2, 1, lastRow - 1, lastCol).sort({ column: ci, ascending: false });
  }
}

// ─── 전 카테고리 시트를 접수일시 내림차순으로 1회 정렬 (기존 데이터 정리용) ───
//   Apps Script 에디터에서 이 함수를 한 번 실행하면 모든 접수 시트가 최신-상단으로 정렬된다.
//   이후에는 reg_submit 이 접수 때마다 자동 정렬해 유지. 멱등(다시 실행해도 순서 동일).
function _regSortAllDesc() {
  var n = 0;
  REG_CATEGORIES.forEach(function (cat) {
    try {
      var sh = _regGetSheet(cat.key);
      _regSortSheetDesc(sh, _regHeadersFor(cat.key));
      n++;
    } catch (e) {}
  });
  return n;
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
// reg_board 공개·직원(사진) 두 캐시 동시 무효화 — 쓰기 액션(submit/update/delete/renumber 등)마다 호출.
function _regBoardCacheClear_() {
  try { var c = CacheService.getScriptCache(); c.remove('reg_board_v1'); c.remove('reg_board_staff_v1'); } catch (e) {}
}

function _regUpdate(body) {
  var id = String(body.id || body['접수ID'] || '').trim();
  if (!id) return _vJson({ ok: false, error: 'id 필수' });

  var newStatus = String(body.status || '').trim();
  if (newStatus && LEGACY_RECEPTION_STATUSES.indexOf(newStatus) < 0) {
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
    _regBoardCacheClear_();
    return _vJson({
      ok: true, id: id,
      status:   statusIdx  >= 0 ? existing[statusIdx]  : '',
      assignee: assigneeIdx >= 0 ? existing[assigneeIdx] : '',
      message: '접수건이 갱신되었습니다.'
    });
  }

  return _vJson({ ok: false, error: '해당 접수ID를 찾을 수 없습니다: ' + id });
}

// ─── reg_delete — 접수ID로 행 정밀 삭제 (GATED·내부) ───
// category 지정 시 해당 시트만, 없으면 전 reg 시트 순회하며 첫 일치 행 삭제. 배포검증 더미 청소용.
// 안전: id 정확매칭(_vFindRow, col A) 1행만 삭제. id 없으면 거부. GATED(공개 액션 목록 미포함).
function _regDelete(body) {
  var id = String((body && (body.id || body['접수ID'])) || '').trim();
  if (!id) return _vJson({ ok: false, error: 'id 필수' });
  var catRaw = String((body && body.category) || '').trim();
  var targets = catRaw ? [_regCatByKey(catRaw) || _regCatByLabel(catRaw)] : REG_CATEGORIES;
  for (var i = 0; i < targets.length; i++) {
    var cat = targets[i];
    if (!cat) continue;
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { continue; }
    var rowNum = _vFindRow(sh, id);
    if (rowNum < 0) continue;
    sh.deleteRow(rowNum);
    _regBoardCacheClear_();
    return _vJson({ ok: true, id: id, category: cat.label, deleted: 1, message: '접수건이 삭제되었습니다.' });
  }
  return _vJson({ ok: false, error: '해당 접수ID를 찾을 수 없습니다: ' + id });
}

// ─── reg_reprefix — 접수번호 앞글자만 교체 (GATED·일회성 마이그레이션) ───
// 2026-07-27 GM 지시 'VOC 낱말 폐기 → RECEPTION'. 숫자는 절대 건드리지 않는다.
// 왜 아래 reg_renumber 를 안 쓰나: 그건 접수일시 순서로 번호를 다시 매긴다. 라이브 65건 실측 결과
//   65건 중 63건의 번호가 바뀐다(삭제된 행 때문에 최대번호 68 ≠ 건수 65) — 실무진이 알던 번호가
//   전부 밀린다. 그래서 '접두사만 치환'하는 이 액션을 따로 둔다.
// 멱등: 이미 RECEPTION- 인 행은 건너뛴다. 두 번 돌려도 결과 같음.
function _regReprefix() {
  var changed = 0, skipped = 0;

  function reprefixCell(sheet, rowNum, idCol) {
    var cell = sheet.getRange(rowNum, idCol);
    var cur = String(cell.getValue() || '');
    if (cur.indexOf(REG_ID_PREFIX_OLD) !== 0) { skipped += 1; return; }
    cell.setValue(REG_ID_PREFIX + cur.slice(REG_ID_PREFIX_OLD.length));
    changed += 1;
  }

  // 종합접수처 카테고리 시트들
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var headers = _regHeadersFor(cat.key);
    var idIdx = -1;
    for (var i = 0; i < headers.length; i++) { if (headers[i].key === 'regId') idIdx = i; }
    if (idIdx < 0) return;
    var last = sh.getLastRow();
    for (var r = 2; r <= last; r++) reprefixCell(sh, r, idIdx + 1);
  });

  // 레거시 '접수 VOC' 시트(있으면)
  try {
    var lss = _vGetSpreadsheet().getSheetByName(LEGACY_RECEPTION_SHEET);
    if (lss && lss.getLastRow() >= 2) {
      var lIdCol = LEGACY_RECEPTION_HEADERS.indexOf('접수ID') + 1;
      if (lIdCol > 0) {
        for (var k = 2; k <= lss.getLastRow(); k++) reprefixCell(lss, k, lIdCol);
      }
    }
  } catch (e) {}

  _regBoardCacheClear_();
  return _vJson({
    ok: true, changed: changed, skipped: skipped,
    message: '접수번호 ' + changed + '건의 앞글자를 ' + REG_ID_PREFIX_OLD + ' → ' + REG_ID_PREFIX +
             ' 로 바꿨습니다(숫자 불변). 이미 바뀐 행 ' + skipped + '건은 건너뜀.'
  });
}

// ─── reg_renumber — 전체 접수 통합 순번 재부여 (GATED·일회성 마이그레이션) ───
// ⚠️ 접두사만 바꾸려고 이걸 부르지 말 것 — 번호가 밀린다(위 reg_reprefix 주석 참고, 2026-07-27 실측).
// 모든 카테고리 시트 + 레거시 '접수 VOC'의 전 행을 접수일시 오름차순으로 모아 VOC-1..N 재부여
// (시트별 접수ID/regId 컬럼만 갱신, 다른 칸 불변) 후 RECEPTION_SEQ=N 동기화 → 새 접수는 RECEPTION-(N+1) 이어감.
// 재실행해도 접수일시 순서가 같으면 같은 번호 → 멱등. 백업은 호출 전 외부(reg_list 덤프)에서 수행.
function _regRenumber(body) {
  var entries = [];   // {sheet, rowNum, idCol(1-based), createdAt}

  // 종합접수처 카테고리 시트들
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var headers = _regHeadersFor(cat.key);
    var idIdx = -1, createdIdx = -1;
    for (var i = 0; i < headers.length; i++) {
      if (headers[i].key === 'regId')     idIdx = i;
      if (headers[i].key === 'createdAt') createdIdx = i;
    }
    if (idIdx < 0) return;
    var last = sh.getLastRow();
    if (last < 2) return;
    var data = sh.getRange(2, 1, last - 1, headers.length).getValues();
    for (var r = 0; r < data.length; r++) {
      var c = data[r][createdIdx];
      if (c instanceof Date) c = Utilities.formatDate(c, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      entries.push({ sheet: sh, rowNum: r + 2, idCol: idIdx + 1, createdAt: String(c || '') });
    }
  });

  // 레거시 '접수 VOC' 시트(있으면)
  try {
    var lss = _vGetSpreadsheet().getSheetByName(LEGACY_RECEPTION_SHEET);
    if (lss && lss.getLastRow() >= 2) {
      var lIdIdx = LEGACY_RECEPTION_HEADERS.indexOf('접수ID');
      var lCrIdx = LEGACY_RECEPTION_HEADERS.indexOf('접수일시');
      var ld = lss.getRange(2, 1, lss.getLastRow() - 1, LEGACY_RECEPTION_HEADERS.length).getValues();
      for (var k = 0; k < ld.length; k++) {
        var c2 = ld[k][lCrIdx];
        if (c2 instanceof Date) c2 = Utilities.formatDate(c2, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
        entries.push({ sheet: lss, rowNum: k + 2, idCol: lIdIdx + 1, createdAt: String(c2 || '') });
      }
    }
  } catch (e) {}

  // 접수일시 오름차순(빈값 뒤로)
  entries.sort(function (a, b) {
    if (!a.createdAt) return 1;
    if (!b.createdAt) return -1;
    return a.createdAt < b.createdAt ? -1 : (a.createdAt > b.createdAt ? 1 : 0);
  });

  var n = 0;
  entries.forEach(function (e) {
    n += 1;
    e.sheet.getRange(e.rowNum, e.idCol).setValue(REG_ID_PREFIX + n);
  });
  PropertiesService.getScriptProperties().setProperty('RECEPTION_SEQ', String(n));

  _regBoardCacheClear_();
  return _vJson({ ok: true, renumbered: n, message: '전체 접수 ' + n + '건을 ' + REG_ID_PREFIX + '1..' + REG_ID_PREFIX + n + ' 로 재부여했습니다.' });
}

// ─── clean_reg_columns — 시트 잔재/빈 컬럼 정리 (GATED·일회성) ───
// REG_CATEGORIES 각 시트에서 잔재 라벨 컬럼을 화이트리스트 기준으로 삭제.
// ★ 데이터-안전: 잔재 라벨이라도 헤더 아래에 값이 하나라도 있으면 삭제하지 않고 보존 → keptWithData 리포트(GM 확인용).
// 화이트리스트: 빈 라벨('' 공백) · '접수문자'·'조치문자'·'처리자'·'접수 문자'·'조치 문자'.
// 추가로 시트명이 '접수_칭찬'/'접수_쓴소리'면 '사진URL' 컬럼도 삭제(GM 결정: 칭찬·쓴소리 사진 미수집 —
// _regHeadersFor 의 REG_NO_PHOTO_CATS 와 짝. 이 두 사이트만 물리 컬럼도 함께 없어져야 정합).
// 공통12+카테고리 extras(데이터 컬럼)는 화이트리스트에 없으므로 항상 보존 — 지원부/점검 시트 무관(이 시트=종합접수처 전용).
// 오른쪽(높은 인덱스)부터 deleteColumn 해서 인덱스 밀림 방지.
function _regCleanColumns() {
  var GHOST_LABELS = { '': true, '접수문자': true, '조치문자': true, '처리자': true, '접수 문자': true, '조치 문자': true };
  var result = [];
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var lastCol = sh.getLastColumn();
    if (lastCol < 1) { result.push({ sheet: cat.sheet, deletedCount: 0, deletedLabels: [] }); return; }

    var lastRow = sh.getLastRow();
    var headerRow = sh.getRange(1, 1, 1, lastCol).getValues()[0]
      .map(function (v) { return String(v == null ? '' : v).trim(); });
    // 데이터 유무 판정용: 헤더(1행) 아래 전 컬럼 값 스냅샷
    var dataVals = (lastRow > 1) ? sh.getRange(2, 1, lastRow - 1, lastCol).getValues() : [];
    function colHasData(col1) {
      var idx = col1 - 1;
      for (var r = 0; r < dataVals.length; r++) {
        if (String(dataVals[r][idx] == null ? '' : dataVals[r][idx]).trim() !== '') return true;
      }
      return false;
    }
    var isPhotoCleanupTarget = (cat.sheet === '접수_칭찬' || cat.sheet === '접수_쓴소리');

    var toDelete = []; // { col:1-based, label }
    var keptWithData = []; // 데이터가 있어 보존한 잔재 컬럼
    headerRow.forEach(function (label, i) {
      var col1 = i + 1;
      var isGhost = !!GHOST_LABELS[label];
      var isPhoto = isPhotoCleanupTarget && label === '사진URL';
      if (isPhoto) { toDelete.push({ col: col1, label: label }); return; }
      if (isGhost) {
        // 데이터-안전: 잔재 라벨이라도 값이 있으면 삭제하지 않고 보존(GM 확인용 리포트)
        if (colHasData(col1)) { keptWithData.push({ col: col1, label: label || '(빈칸)' }); }
        else { toDelete.push({ col: col1, label: label }); }
      }
    });

    // 오른쪽(높은 인덱스)부터 삭제 — 인덱스 밀림 방지
    toDelete.sort(function (a, b) { return b.col - a.col; });
    toDelete.forEach(function (d) { sh.deleteColumn(d.col); });

    result.push({
      sheet: cat.sheet,
      deletedCount: toDelete.length,
      deletedLabels: toDelete.map(function (d) { return d.label || '(빈칸)'; }),
      keptWithData: keptWithData
    });
  });

  _regBoardCacheClear_();
  return _vJson({ ok: true, result: result, message: '시트 컬럼 정리 완료' });
}

// ─── rename_loc_header — loc 헤더셀 '위치'/'분실위치' → '장소' 통일 (GATED·일회성) ───
// 폼 라벨(장소)과 시트 헤더 문구를 일치시킴. 헤더셀 텍스트만 교체 — 쓰기는 인덱스기반이라 무영향,
// 읽기는 REG_COMMON_HEADERS('장소') + alias('위치'/'분실위치'→loc)로 rename 전/후 모두 정독. 2026-07-08 시우.
function _regRenameLocHeader() {
  var OLD_LOC_LABELS = { '위치': true, '분실위치': true };
  var result = [];
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var lastCol = sh.getLastColumn();
    if (lastCol < 1) { result.push({ sheet: cat.sheet, renamed: 0 }); return; }
    var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0];
    var renamedFrom = [];
    for (var i = 0; i < hdr.length; i++) {
      var label = String(hdr[i] == null ? '' : hdr[i]).trim();
      if (OLD_LOC_LABELS[label]) { sh.getRange(1, i + 1).setValue('장소'); renamedFrom.push(label); }
    }
    result.push({ sheet: cat.sheet, renamed: renamedFrom.length, from: renamedFrom });
  });
  _regBoardCacheClear_();
  return _vJson({ ok: true, result: result, message: 'loc 헤더 → 장소 통일 완료' });
}

// ═══════════════════════════════════════════
//  습득 분실물(Lost & Found) — lf_* 액션 패밀리 (시토 배1069 · 2026-07-15)
//  REG_CATEGORIES 와 완전 독립. 전용 시트 「습득물」 1장 + LF-n 별도 순번.
//  기존 헬퍼 재사용: _vGetSpreadsheet · _vNextSeqId 패턴 · _regReadAll · _vFindRow · _vNotifyTelegram · _vExtractFileId_.
//  ★ 공개 갤러리(lf_gallery)는 사진을 '공개'로 반환한다(reg_board 의 photoUrl='비공개' 마스킹과 정반대).
//    민감필드(수령자·수령시각·서명URL·등록직원)는 공개 응답에서 제외 — 코드 경계로 공개 vs GATED 분리.
// ═══════════════════════════════════════════
var LF_SHEET = '습득물';
// 영문키 : 한글헤더 (헤더-라벨 매핑 → 컬럼 물리삭제/순서변경 안전, _regReadAll 재사용)
var LF_HEADERS = [
  { key: 'foundId',     label: '습득ID'         },
  { key: 'createdAt',   label: '등록일시'       },
  { key: 'foundWhen',   label: '습득일시'       },
  { key: 'foundLoc',    label: '습득장소'       },
  { key: 'itemDesc',    label: '습득물설명'     },
  { key: 'photoUrl',    label: '사진URL'        },
  { key: 'status',      label: '상태'           },
  { key: 'receiver',    label: '수령자'         },
  { key: 'handedAt',    label: '수령시각'       },
  { key: 'handoverLoc', label: '수령장소'       },
  { key: 'signUrl',     label: '서명URL'        },
  { key: 'signPurgeAt', label: '서명파기예정일' },
  { key: 'staff',       label: '등록/처리직원'  },
  // ★ 신규(2026-07-15 시토): 수령 시 '주는 담당자' 기록. 물리 컬럼 정합 위해 반드시 맨 끝에 추가
  //   (_lfHandover 는 _lfIdx_ 기반 positional write → 중간 삽입 시 기존 행 오정렬).
  { key: 'handoverStaff', label: '수령담당자'   },
  // ★ 신규(2026-07-18 시우): 폐기 처리일(월별 코호트 폐기). 동일 사유로 반드시 맨 끝에 추가.
  { key: 'disposedAt',    label: '폐기일'       },
  // ★ 신규(2026-07-18 시우): 물품구분 2트랙 처분(consumable/general/valuable). 동일 사유로 반드시 맨 끝에 추가.
  { key: 'category',      label: '물품구분'     }
];
var LF_STATUS = { POSTED: '게시중', HANDED: '수령완료', DISPOSED: '폐기물', POLICE: '경찰인계' };
var LF_PHOTO_FOLDER_NAME = 'LF_Photos';       // 공개 VIEW (갤러리용)
var LF_SIGN_FOLDER_NAME  = 'LF_Signatures';   // 비공개 (수령 서명 = 분쟁 증거)

// LF-n 전용 단조증가 순번 (RECEPTION_SEQ 와 별개 번호공간) — LockService 로 동시 등록 충돌 방지
function _lfNextSeqId_() {
  var lock = LockService.getScriptLock();
  try { lock.waitLock(5000); } catch (e) {}
  var props = PropertiesService.getScriptProperties();
  var cur = parseInt(props.getProperty('LF_SEQ') || '0', 10);
  if (isNaN(cur)) cur = 0;
  var next = cur + 1;
  props.setProperty('LF_SEQ', String(next));
  try { lock.releaseLock(); } catch (e) {}
  return 'LF-' + next;
}

// 습득물 시트 확보 (없으면 헤더와 함께 자동 생성)
function _lfGetSheet_() {
  var ss = _vGetSpreadsheet();
  var headers = LF_HEADERS.map(function (h) { return h.label; });
  var sh = ss.getSheetByName(LF_SHEET);
  if (sh) {
    if (sh.getLastRow() < 1) { sh.getRange(1, 1, 1, headers.length).setValues([headers]); return sh; }
    // 자가치유: 신규 헤더(수령담당자·폐기일 등) 누락 시 빈 헤더칸만 보강 (기존 라벨 무클로버·맨끝 append).
    var lastCol = Math.max(sh.getLastColumn(), 1);
    var width = Math.max(lastCol, headers.length);
    var cur = sh.getRange(1, 1, 1, width).getValues()[0];
    var need = false;
    for (var i = 0; i < headers.length; i++) {
      if (String(cur[i] || '') === '') { cur[i] = headers[i]; need = true; }
    }
    if (need) sh.getRange(1, 1, 1, cur.length).setValues([cur]);
    return sh;
  }
  sh = ss.insertSheet(LF_SHEET);
  sh.getRange(1, 1, 1, headers.length).setValues([headers]);
  sh.getRange(1, 1, 1, headers.length).setFontWeight('bold').setBackground('#B79F8A').setFontColor('#ffffff');
  sh.setFrozenRows(1);
  return sh;
}

// LF 전용 Drive 폴더 확보 (사진=공개 / 서명=비공개) — _vGetPhotoFolder 패턴
function _lfGetFolder_(propKey, folderName) {
  var folderId = _vprop(propKey);
  var folder = null;
  if (folderId) { try { folder = DriveApp.getFolderById(folderId); } catch (e) { folder = null; } }
  if (!folder) {
    var existing = DriveApp.getRootFolder().getFoldersByName(folderName);
    folder = existing.hasNext() ? existing.next() : DriveApp.getRootFolder().createFolder(folderName);
    PropertiesService.getScriptProperties().setProperty(propKey, folder.getId());
  }
  return folder;
}

// Base64 업로드 (사진=ANYONE_WITH_LINK VIEW / 서명=비공개 유지) — _vUploadPhoto 파이프 재사용
function _lfUpload_(base64, fileName, mimeType, isSignature) {
  if (!base64) return '';
  var b64 = String(base64);
  var comma = b64.indexOf(',');
  if (b64.slice(0, 5) === 'data:' && comma >= 0) b64 = b64.slice(comma + 1);
  var folder = isSignature
    ? _lfGetFolder_('LF_SIGN_FOLDER',  LF_SIGN_FOLDER_NAME)
    : _lfGetFolder_('LF_PHOTO_FOLDER', LF_PHOTO_FOLDER_NAME);
  var blob = Utilities.newBlob(
    Utilities.base64Decode(b64),
    mimeType || (isSignature ? 'image/png' : 'image/jpeg'),
    fileName || ('lf_' + (isSignature ? 'sign_' : 'photo_') + _vNow().replace(/[: ]/g, '_'))
  );
  var file = folder.createFile(blob);
  if (!isSignature) file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  // 서명: setSharing 미호출 → 스크립트 소유자 외 비공개 유지 (분쟁 증거·PII 최소).
  return file.getUrl();
}

function _lfIdx_(key) {
  for (var i = 0; i < LF_HEADERS.length; i++) { if (LF_HEADERS[i].key === key) return i; }
  return -1;
}

// ─── _lfMonthIndex_ — 날짜문자열 → 연*12+(월-1) 월코호트 인덱스 (Asia/Seoul 기준). 파싱 실패 시 null ───
function _lfMonthIndex_(dateStr) {
  var baseStr = String(dateStr || '').trim();
  if (!baseStr) return null;
  var baseDate = new Date(baseStr.replace(' ', 'T').slice(0, 10) + 'T00:00:00');
  if (isNaN(baseDate.getTime())) return null; // 파싱 실패
  var ym = Utilities.formatDate(baseDate, 'Asia/Seoul', 'yyyy-MM').split('-');
  return parseInt(ym[0], 10) * 12 + (parseInt(ym[1], 10) - 1);
}

// ─── _lfAutoDispose_ — read-time sweep: 현재월 ≥ 습득월(foundWhen 없으면 createdAt)+2 & 게시중 → 폐기물 자동 전환 (월별 코호트) ───
// GM 재확정(2026-07-18 v2): 습득월M → M+1 공지 → M+2 폐기(월 코호트). 크론 없이 lf_gallery/lf_list/lf_disposal 진입 시마다 호출(자가치유·멱등).
// monthIndex 파싱 실패 행은 건드리지 않음. 변경된 행이 있을 때만 setValues 저장.
function _lfAutoDispose_(sh) {
  var rows = _regReadAll(sh, LF_HEADERS);
  if (!rows.length) return;
  var todayStr = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  var curMonthIdx = _lfMonthIndex_(todayStr);
  var statusIdx = _lfIdx_('status');
  var disposedIdx = _lfIdx_('disposedAt');
  var data = sh.getRange(2, 1, rows.length, LF_HEADERS.length).getValues();
  var changed = false;
  rows.forEach(function (r, i) {
    if (String(r.status || '') !== LF_STATUS.POSTED) return;
    var monthIdx = _lfMonthIndex_(r.foundWhen || r.createdAt);
    if (monthIdx === null) return; // 파싱 실패 행은 건드리지 않음
    if (curMonthIdx < monthIdx + 2) return; // 아직 폐기월 미도래
    // ★ 2트랙 분기(2026-07-18 시우): consumable=자동폐기(현행), 그 외(general/valuable/빈값)=경찰인계.
    //   빈값(기존 미분류 데이터)도 경찰인계 트랙 — 임의폐기 위험 즉시 제거(안전 기본값).
    if (String(r.category || '') === 'consumable') {
      data[i][statusIdx] = LF_STATUS.DISPOSED;
    } else {
      data[i][statusIdx] = LF_STATUS.POLICE;
    }
    data[i][disposedIdx] = todayStr;
    changed = true;
  });
  if (changed) sh.getRange(2, 1, rows.length, LF_HEADERS.length).setValues(data);
}

// ─── lf_submit — 직원 습득물 접수 (게이트 뒤 · 제출토큰) ───
function _lfSubmit(body) {
  var foundWhen = String(body.foundWhen || '').trim();
  var foundLoc  = String(body.foundLoc  || body.loc || '').trim();
  var itemDesc  = String(body.itemDesc  || body.content || '').trim();
  var staff     = String(body.staff     || '').trim();
  var category  = String(body.category  || '').trim();
  if (['consumable', 'general', 'valuable'].indexOf(category) < 0) category = 'general';
  var photo    = body.photo || body.file || body.base64 || '';
  var fileName = body.fileName || '';
  var mimeType = body.mimeType || 'image/jpeg';

  if (!photo) return _vJson({ ok: false, error: '습득물 사진은 필수입니다. (갤러리 노출용)' });
  if (!foundLoc && !itemDesc) return _vJson({ ok: false, error: '습득장소 또는 설명 중 하나는 입력해 주세요.' });

  var photoUrl = '';
  try { photoUrl = _lfUpload_(photo, fileName, mimeType, false); }
  catch (e) { return _vJson({ ok: false, error: '사진 저장 실패: ' + e.message }); }

  var sh = _lfGetSheet_();
  var id = _lfNextSeqId_();
  var now = _vNow();
  var row = new Array(LF_HEADERS.length).fill('');
  var _set = function (key, val) { var i = _lfIdx_(key); if (i >= 0) row[i] = val; };
  _set('foundId', id); _set('createdAt', now); _set('foundWhen', foundWhen);
  _set('foundLoc', foundLoc); _set('itemDesc', itemDesc); _set('photoUrl', photoUrl);
  _set('status', LF_STATUS.POSTED); _set('staff', staff); _set('category', category);
  var newRow = sh.getLastRow() + 1;
  sh.getRange(newRow, 1, 1, row.length).setValues([row]);

  _vNotifyTelegram(
    '🧳 <b>[습득물 접수]</b> ' + id + '\n' +
    '습득장소: ' + (foundLoc || '-') + '\n' +
    '설명: ' + (itemDesc ? itemDesc.slice(0, 100) : '-') + '\n' +
    (staff ? '등록: ' + staff + '\n' : '') +
    '🕒 ' + now,
    photoUrl
  );
  return _vJson({ ok: true, id: id, photoUrl: photoUrl });
}

// ─── lf_gallery — 무인증 공개 갤러리 (게시중만 · 민감필드 미반환) ───
function _lfGallery() {
  var sh = _lfGetSheet_();
  _lfAutoDispose_(sh); // read-time sweep: 월코호트 폐기 대상(현재월≥습득월+2) 자동 전환 후 조회
  var rows = _regReadAll(sh, LF_HEADERS);
  var out = [];
  rows.forEach(function (r) {
    if (String(r.status || '') !== LF_STATUS.POSTED) return;
    // ★ 공개 응답 = 사진·습득정보만. 수령자/수령시각/서명URL/등록직원 등 민감필드 제외.
    out.push({
      foundId:   r.foundId   || '',
      foundWhen: r.foundWhen || '',
      foundLoc:  r.foundLoc  || '',
      itemDesc:  r.itemDesc  || '',
      photoUrl:  r.photoUrl  || '',
      createdAt: r.createdAt || '',
      category:  r.category  || ''
    });
  });
  out.sort(function (a, b) { return String(b.createdAt || '') > String(a.createdAt || '') ? 1 : -1; });
  return _vJson({ ok: true, count: out.length, data: out });
}

// ─── lf_list — 직원용 전체 목록 (GATED · 전 필드) ───
function _lfList(params) {
  var sh = _lfGetSheet_();
  _lfAutoDispose_(sh); // read-time sweep: 월코호트 폐기 대상(현재월≥습득월+2) 자동 전환 후 조회
  var rows = _regReadAll(sh, LF_HEADERS);
  var status = String((params && params.status) || '').trim();
  if (status) rows = rows.filter(function (r) { return String(r.status || '') === status; });
  rows.sort(function (a, b) { return String(b.createdAt || '') > String(a.createdAt || '') ? 1 : -1; });
  return _vJson({ ok: true, count: rows.length, data: rows });
}

// ─── lf_handover — 현장 디지털 서명 수령 → 자동 수령완료 (멱등·중복거부) ───
function _lfHandover(body) {
  var id = String(body.id || body.foundId || '').trim();
  if (!id) return _vJson({ ok: false, error: '습득ID 필수' });
  var receiver    = String(body.receiver || '').trim();
  var handoverLoc = String(body.handoverLoc || '').trim();
  var handoverStaff = String(body.handoverStaff || '').trim();
  var sign = body.signature || body.sign || '';
  if (!receiver) return _vJson({ ok: false, error: '수령자 성함은 필수입니다.' });
  if (!sign)     return _vJson({ ok: false, error: '수령 확인 서명은 필수입니다.' });

  var sh = _lfGetSheet_();
  var rowNum = _vFindRow(sh, id);
  if (rowNum < 0) return _vJson({ ok: false, error: '해당 습득ID를 찾을 수 없습니다: ' + id });

  var existing = sh.getRange(rowNum, 1, 1, LF_HEADERS.length).getValues()[0];
  var curStatus = String(existing[_lfIdx_('status')] || '');
  if (curStatus !== LF_STATUS.POSTED) {
    // 멱등·중복 수령 방지 — 이미 수령완료/폐기물이면 거부
    return _vJson({ ok: false, error: '이미 처리된 습득물입니다 (현재 상태: ' + curStatus + ').', code: 'ALREADY_HANDLED' });
  }

  var signUrl = '';
  try { signUrl = _lfUpload_(sign, 'lf_sign_' + id + '.png', 'image/png', true); }
  catch (e) { return _vJson({ ok: false, error: '서명 저장 실패: ' + e.message }); }

  var now = _vNow();
  // 서명 파기 예정일 = 수령 6개월 후 (개인정보 최소보관 · lf_purge_signatures 가 이후 실제 파기)
  var purge = new Date(); purge.setMonth(purge.getMonth() + 6);
  var purgeStr = Utilities.formatDate(purge, 'Asia/Seoul', 'yyyy-MM-dd');

  existing[_lfIdx_('status')]        = LF_STATUS.HANDED;
  existing[_lfIdx_('receiver')]      = receiver;
  existing[_lfIdx_('handedAt')]      = now;
  existing[_lfIdx_('handoverLoc')]   = handoverLoc;
  existing[_lfIdx_('handoverStaff')] = handoverStaff;
  existing[_lfIdx_('signUrl')]       = signUrl;
  existing[_lfIdx_('signPurgeAt')]   = purgeStr;
  sh.getRange(rowNum, 1, 1, LF_HEADERS.length).setValues([existing]);

  _vNotifyTelegram(
    '✅ <b>[습득물 수령완료]</b> ' + id + '\n' +
    '수령자: ' + receiver + '\n' +
    '담당자: ' + (handoverStaff || '-') + '\n' +
    '수령장소: ' + (handoverLoc || '-') + '\n' +
    '🕒 ' + now
  );
  return _vJson({ ok: true, id: id, status: LF_STATUS.HANDED, signPurgeAt: purgeStr });
}

// ─── lf_delete — 습득ID로 행 정밀 삭제 (GATED·내부, 배포검증 더미 청소용) ───
function _lfDelete(body) {
  var id = String((body && (body.id || body.foundId)) || '').trim();
  if (!id) return _vJson({ ok: false, error: 'id 필수' });
  var sh = _lfGetSheet_();
  var rowNum = _vFindRow(sh, id);
  if (rowNum < 0) return _vJson({ ok: false, error: '해당 습득ID를 찾을 수 없습니다: ' + id });
  sh.deleteRow(rowNum);
  return _vJson({ ok: true, id: id, deleted: 1 });
}

// ─── lf_purge_signatures — 파기예정일 경과 서명 파일 파기 (GATED·스케줄) ───
// signPurgeAt <= 오늘 인 행의 서명 Drive 파일을 휴지통 이동 + 시트 서명URL='(파기됨)'. 멱등.
function _lfPurgeSignatures() {
  var sh = _lfGetSheet_();
  var rows = _regReadAll(sh, LF_HEADERS);
  var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  var purged = 0;
  for (var r = 0; r < rows.length; r++) {
    var row = rows[r];
    var purgeAt = String(row.signPurgeAt || '');
    var signUrl = String(row.signUrl || '');
    if (!signUrl || signUrl === '(파기됨)' || !purgeAt) continue;
    if (purgeAt > today) continue; // 아직 파기일 이전
    try { var fid = _vExtractFileId_(signUrl); if (fid) DriveApp.getFileById(fid).setTrashed(true); } catch (e) {}
    var rowNum = _vFindRow(sh, row.foundId);
    if (rowNum > 0) sh.getRange(rowNum, _lfIdx_('signUrl') + 1).setValue('(파기됨)');
    purged++;
  }
  return _vJson({ ok: true, purged: purged });
}

// ─── lf_disposal — 폐기물 공지 A3 (공개 read · 게이트 불요 · 민감필드 미반환) ───
// 시트 확보→_lfAutoDispose_ sweep→읽기. upcoming=게시중 중 전월 습득 코호트(disposeMonth=습득월+2), disposed=폐기물(폐기일 desc).
function _lfDisposal() {
  var sh = _lfGetSheet_();
  _lfAutoDispose_(sh);
  var rows = _regReadAll(sh, LF_HEADERS);
  var curMonthIdx = _lfMonthIndex_(Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd'));
  var upcoming = [];
  var disposed = [];
  rows.forEach(function (r) {
    var status = String(r.status || '');
    var category = String(r.category || '');
    if (status === LF_STATUS.POSTED) {
      var monthIdx = _lfMonthIndex_(r.foundWhen || r.createdAt);
      if (monthIdx === null) return; // 파싱 실패 행은 제외
      if (monthIdx !== curMonthIdx - 1) return; // 전월 습득분(=다음달 폐기 예정)만 임박 표시
      var disposeIdx = monthIdx + 2;
      var disposeMon = disposeIdx % 12 + 1;
      var disposeMonth = Math.floor(disposeIdx / 12) + '-' + (disposeMon < 10 ? '0' + disposeMon : disposeMon);
      upcoming.push({
        foundId:      r.foundId   || '',
        itemDesc:     r.itemDesc  || '',
        foundLoc:     r.foundLoc  || '',
        foundWhen:    r.foundWhen || '',
        photoUrl:     r.photoUrl  || '',
        disposeMonth: disposeMonth,
        category:     category,
        track:        category === 'consumable' ? 'dispose' : 'police'
      });
    } else if (status === LF_STATUS.DISPOSED || status === LF_STATUS.POLICE) {
      disposed.push({
        foundId:    r.foundId    || '',
        itemDesc:   r.itemDesc   || '',
        foundLoc:   r.foundLoc   || '',
        foundWhen:  r.foundWhen  || '',
        photoUrl:   r.photoUrl   || '',
        disposedAt: r.disposedAt || '',
        category:   category,
        track:      status === LF_STATUS.DISPOSED ? 'dispose' : 'police'
      });
    }
  });
  upcoming.sort(function (a, b) { return String(a.foundId || '').localeCompare(String(b.foundId || '')); });
  disposed.sort(function (a, b) { return String(b.disposedAt || '') > String(a.disposedAt || '') ? 1 : -1; });
  return _vJson({ ok: true, upcoming: upcoming, disposed: disposed });
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
var _RECEPTION_PUBLIC_ACTIONS = {
  voc_submit:  true,  // 회원 모바일 폼 제출 — 토큰 면제
  voc_types:   true,  // 유형·상태 목록 조회 — 토큰 면제
  reg_submit:  true,  // 종합 접수처 제출 — 토큰 면제
  reg_board:   true,  // 마스킹 공개 보드 — 이름·연락처 가려서 반환, 토큰 면제
  reg_update:  true,  // 상태·담당·메모 갱신 — PII 미포함, 토큰 면제
  lf_submit:   true,  // 습득물 접수 — 제출토큰(_vSubmitGateOk_)으로 별도 보호, 접근키 면제
  lf_gallery:  true,  // 습득물 공개 갤러리 — 민감필드 미반환(게시중만), 토큰 면제
  lf_disposal: true,  // 폐기물 공지 A3(게시예정+폐기완료) — 민감필드 미반환, 토큰 면제
  diag:        true   // read-only 진단 — 비밀값 절대 미노출, 불리언만 반환
  // ⚠️ reg_list 는 전체 PII(이름·연락처 원문) 포함 — 절대 public 금지, GATED 유지.
  // ⚠️ lf_list/lf_handover/lf_delete/lf_purge_signatures 는 public 아님(GATED) — 쓰기는 제출토큰 게이트.
  // voc_list / voc_update 도 게이트 적용.
};
function _vAccessProp_(k) {
  try { return PropertiesService.getScriptProperties().getProperty(k) || ''; } catch (e) { return ''; }
}
function _vCheckAccess_(action, key) {
  if (_RECEPTION_PUBLIC_ACTIONS[action]) return true;            // 공개 액션은 항상 통과
  if (_vAccessProp_('TOKEN_ENFORCE') !== '1') return true; // 스위치 OFF(기본) = 현행 무중단
  var tok = _vAccessProp_('ACCESS_TOKEN');
  if (!tok) return true;                                   // 토큰 미설정 = 안전을 위해 통과
  return String(key || '') === tok;
}

// ─── 진단 액션 (read-only · 비밀값 절대 미노출) ───
// hasToken/hasChatId/hasSpreadsheetId: 값 존재 여부만 반환(값 자체 절대 노출 금지).
// 헬스체크(telegram_health_check.py)가 매일 ping — GET ?action=diag 로 호출.
function _vDiag() {
  return _vJson({
    ok:               true,
    system:           'reception',
    hasToken:         !!_vprop('TELEGRAM_BOT_TOKEN'),
    hasChatId:        !!_vprop('TELEGRAM_CHAT_ID'),
    hasSpreadsheetId: !!_vprop('SPREADSHEET_ID'),
    seq:              parseInt(_vpropCompat('RECEPTION_SEQ', 'VOC_SEQ') || '0', 10),
    lfSeq:            parseInt(_vprop('LF_SEQ') || '0', 10)
  });
}

// 공용 라우터 (doGet/doPost)
function _vProcess(action, body, params) {
  // ─── 접근 게이트 확인 ───
  var _gateKey = (body && body.key) || (params && params.key) || '';
  if (!_vCheckAccess_(action, _gateKey)) {
    return _vJson({ ok: false, error: 'unauthorized' });
  }

  // ─── 접수 위조 방지(시토 2026-06-29 GM): 제출·쓰기 액션은 숨김토큰 + 속도제한 ───
  //   lf_submit/lf_handover(습득물 쓰기)도 동일 게이트 — 무단 등록·수령 위조 차단.
  if (action === 'reg_submit' || action === 'voc_submit' ||
      action === 'lf_submit'  || action === 'lf_handover') {
    if (!_vSubmitGateOk_(body)) {
      return _vJson({ ok: false, error: '접수 권한 확인에 실패했습니다. 페이지를 새로고침 후 다시 시도해 주세요.', code: 'BAD_TOKEN' });
    }
    var _fp = _vFp_([
      (body && (body.category || body.type)) || '',
      (body && body.contact) || '',
      (body && body.content) || '',
      (body && (body.foundLoc || body.itemDesc)) || '',   // lf_submit 지문
      (body && (body.id || body.receiver)) || ''           // lf_handover 지문
    ].map(function (x) { return String(x || ''); }).join('|'));
    if (!_vRateLimitOk_(_fp)) {
      return _vJson({ ok: false, error: '요청이 많아 잠시 후 다시 시도해 주세요. (중복·과다 접수 방지)', code: 'RATE_LIMIT' });
    }
  }

  // ── 진단 액션 ──
  if (action === 'diag') return _vDiag();
  // 읽기전용: 전 시트 헤더행 덤프(카테고리별 컬럼 정합 점검용·1회성). 2026-07-08 시우.
  if (action === 'dump_headers') {
    var _dss = SpreadsheetApp.openById(_vprop('SPREADSHEET_ID'));
    var _dout = _dss.getSheets().map(function (sh) {
      var lc = sh.getLastColumn();
      return {
        name: sh.getName(),
        cols: lc,
        dataRows: Math.max(0, sh.getLastRow() - 1),
        headers: lc ? sh.getRange(1, 1, 1, lc).getValues()[0].map(String) : []
      };
    });
    return _vJson({ ok: true, sheets: _dout });
  }
  // 쓰기(잔재/빈 컬럼 삭제) · 일회성 · GATED(공개 액션 아님). 2026-07-08 시우.
  if (action === 'clean_reg_columns') return _regCleanColumns();
  // loc 헤더 '위치'/'분실위치' → '장소' 통일(폼 라벨과 시트 헤더 문구 일치). 쓰기 무영향(인덱스기반). 일회성. 2026-07-08 시우.
  if (action === 'rename_loc_header') return _regRenameLocHeader();
  // 접수번호 앞글자 VOC- → RECEPTION- (숫자 불변) · 일회성 · GATED. 2026-07-27 시우(GM 승인).
  if (action === 'reg_reprefix') return _regReprefix();

  // ── 종합 접수처 액션 ──
  if (action === 'reg_submit') return _regSubmit(body);
  if (action === 'reg_list')   return _regList(params || body);
  if (action === 'reg_board') {
    // 마스킹 공개 보드 — _regList 결과에 _regMask 적용 후 카드별 SLA(처리기한) 계산
    // 필터 없는 호출(페이지 실사용 경로)만 45초 서버 캐시 — 재조회·다수 열람 즉답. 쓰기(reg_submit/update/delete/renumber) 시 즉시 무효화.
    var _rbSrc = params || body || {};
    // 직원 현황(gate.js 뒤) = pv 키 통과 시 사진 원본 유지(썸네일용). 공개 호출은 계속 '비공개'.
    var _rbStaffPhoto = String(_rbSrc.pv || '') === REG_STAFF_PHOTO_KEY;
    var _rbNoFilter = !_rbSrc.category && !_rbSrc.dept;
    // 공개/직원(사진) 결과를 각각 별도 키로 캐시 — 사진노출본이 공개 캐시에 섞이지 않게 분리(속도 유지).
    var _rbCacheKey = _rbStaffPhoto ? 'reg_board_staff_v1' : 'reg_board_v1';
    if (_rbNoFilter) {
      try {
        var _rbHit = CacheService.getScriptCache().get(_rbCacheKey);
        if (_rbHit) return _vJson(JSON.parse(_rbHit));
      } catch (e) {}
    }
    var boardResult = JSON.parse(_regList(params || body).getContent());
    var masked = (boardResult.data || []).map(function (r) { return _regMask(r, _rbStaffPhoto); }).map(_regComputeSla);
    var _rbOut = { ok: true, count: masked.length, data: masked };
    if (_rbNoFilter) {
      try { CacheService.getScriptCache().put(_rbCacheKey, JSON.stringify(_rbOut), 45); } catch (e) {}
    }
    return _vJson(_rbOut);
  }
  if (action === 'reg_update') return _regUpdate(body);
  if (action === 'reg_delete') return _regDelete(body);   // 접수ID로 행 정밀 삭제(배포검증 더미 청소용·GATED). 2026-06-20 시우.
  if (action === 'reg_renumber') return _regRenumber(body); // 전체 통합 순번 RECEPTION-1.. 재부여(일회성·멱등·GATED). 2026-06-30 시토.
  if (action === 'reg_sort') return _vJson({ ok: true, sorted: _regSortAllDesc() }); // 전 접수시트 접수일시 desc 정렬(멱등·GATED). 이후 reg_submit이 자동 유지. 2026-07-15 시우.

  // ── 습득 분실물(Lost & Found) 액션 (시토 배1069 · 2026-07-15) ──
  if (action === 'lf_submit')   return _lfSubmit(body);            // 직원 등록(게이트+제출토큰)
  if (action === 'lf_gallery')  return _lfGallery();               // 무인증 공개 갤러리(게시중·민감필드 미반환)
  if (action === 'lf_list')     return _lfList(params || body);    // 직원용 전체목록(GATED)
  if (action === 'lf_handover') return _lfHandover(body);          // 현장 서명 수령→수령완료(멱등)
  if (action === 'lf_delete')   return _lfDelete(body);            // 더미 청소용 행삭제(GATED)
  if (action === 'lf_disposal') return _lfDisposal();              // 폐기물 공지(공개 read·자동폐기 sweep 포함)
  if (action === 'lf_purge_signatures') return _lfPurgeSignatures(); // 6개월 경과 서명 파기(GATED·스케줄)

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
    statuses:   LEGACY_RECEPTION_STATUSES,
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
        action === 'reg_submit' || action === 'reg_update' ||
        action === 'lf_submit'  || action === 'lf_handover') {
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
