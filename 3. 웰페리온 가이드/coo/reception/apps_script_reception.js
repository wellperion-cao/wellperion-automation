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
// 레거시 접수 원장 탭. 2026-07-27 실측 — 이 탭은 현재 스프레드시트에 없다(실제 탭 8개: 접수_청결·
//   접수_시설고장·접수_분실물·접수_컴플레인·접수_칭찬·접수_쓴소리·휴회접수·습득물). 즉 옛 이름을
//   바꿔도 옮길 대상이 없다 — 레거시 경로가 탭을 새로 만들 때만 쓰이는 이름이라 새 이름으로 둔다.
var LEGACY_RECEPTION_SHEET = '접수 RECEPTION';
var LEGACY_RECEPTION_HEADERS = [
  '접수ID', '접수일시', '유형', '위치', '사진URL',
  '내용', '연락처', '상태', '처리메모'
];
var LEGACY_RECEPTION_STATUSES = ['접수', '처리중', '완료'];

// 「전달문구」 초안임을 드러내는 접두어 — 단일 출처.
//   여기 한 곳에서만 정의하고, 초안 생성(_regDraftMemo)과 자동 상태 전환 판정
//   (_regEffectiveStatusOnMemo)이 둘 다 이 값을 쓴다(약속 L01 — 두 곳에 적으면 어긋난다).
var REG_DRAFT_PREFIX = '[초안] ';

// ─── 답변(처리메모) 등록 시 자동 상태 전환 규칙 (순수함수 — GAS API 미의존, Node에서 테스트 가능) ───
// reg_update(_regUpdate)·voc_update(_vUpdate) 두 '답변 등록' 경로가 공유한다.
// 규칙: '접수' 상태에서 처리메모가 채워지면 '처리중'으로 한 단계만 자동 이동.
//   · 사람이 상태를 직접 지정했으면(newStatus) 그 값이 그대로 이긴다.
//   · '완료' 전환은 자동화 대상 아님 — 추가 답변·재문의가 남을 수 있어 사람이 드롭다운으로 직접.
//   · 이미 '완료'인 건은 메모를 고쳐도 상태를 건드리지 않는다(재오픈도 사람이 드롭다운으로 — 되돌릴 수 있게).
//   · ★초안 문구([초안] 접두어)는 승격시키지 않는다 — 2026-08-05 GM 제안으로 접수 시점에 전달문구
//     초안을 자동으로 채우게 되면서, 아무도 안 본 건까지 '처리중'으로 올라가 「접수(아무도 안 봄)」와
//     「처리중(누가 보고 있음)」 구분이 사라졌다(웰리 실측 2026-08-05 RECEPTION-54·58·64).
//     실무진이 초안을 고치거나 접두어를 지워 '실제 답변'이 되는 순간 승격된다.
// 2026-08-04 시토 (RECEPTION-81 — 답변은 나갔는데 상태가 그대로라 며칠째 SLA 초과로 뜨던 문제).
// 2026-08-06 시토 (초안 배제 — 위 세 번째 규칙).
function _regEffectiveStatusOnMemo(curStatus, newStatus, memo) {
  if (newStatus) return newStatus;
  if (memo === undefined) return '';
  var m = String(memo).trim();
  if (!m) return '';
  if (m.indexOf(REG_DRAFT_PREFIX.trim()) === 0) return '';   // 초안은 '누가 보고 있음'이 아니다
  if (curStatus === '접수') return '처리중';
  return '';
}
var LEGACY_RECEPTION_STATUS_COLORS = {
  '접수':  '#e6944e', // 주황
  '처리중': '#5b9fd5', // 파랑
  '완료':  '#6abf7b'  // 초록
};
// 접수 사진 Drive 폴더 이름. 2026-07-27 GM 지시로 VOC_Photos → RECEPTION_Photos 개명.
//   폴더는 실물 자원이라 '이름을 바꾸면 못 찾는' 위험이 있다 → 평소 조회는 ScriptProperty 에 저장된
//   폴더 ID 로 하고(이름 무관), 이름 조회는 폴백일 뿐이며 새 이름→옛 이름 순으로 본다.
//   실제 폴더 개명은 rename_legacy_resources 액션이 한 번 수행한다(사진·링크는 ID 기준이라 불변).
var RECEPTION_PHOTO_FOLDER_NAME     = 'RECEPTION_Photos';
var RECEPTION_PHOTO_FOLDER_NAME_OLD = 'VOC_Photos';

// ─── 종합 접수처 상수 ───
// REG_CATEGORIES: 카테고리 라우팅 SSOT. dept 변경 시 여기 한 줄만 수정.
// slaHours: 처리기한(SLA) SSOT — 보드에 하드코딩 복사 금지. null = SLA 없음(칭찬: 표시·계산 제외).
var REG_CATEGORIES = [
  // 분실물 720h(30일) — GM 확정 2026-07-28. 원래 168h(7일)였는데, 습득물은 주인이 찾아갈
  // 때까지 보관하는 성격이라 7일이 지나면 전부 '초과'로 잡혔다. 실측(2026-07-28) 기한초과
  // 29건 중 12건이 이것이어서 진짜 방치된 컴플레인 10건이 숫자에 묻혔다. 30일 = 보관 기간
  // 개념(넘으면 폐기·기증 등 정리 대상). 기한 개념을 없애지 않은 이유 = 영원히 쌓이는 것도 막아야 해서.
  { key: 'lost',     label: '분실물 접수',         sheet: '접수_분실물',   dept: '운영부', slaHours: 720 },
  { key: 'facility', label: '시설물 고장 접수',     sheet: '접수_시설고장', dept: '시설부', slaHours: 24 },
  { key: 'clean',    label: '청결 이슈 접수',       sheet: '접수_청결',     dept: '지원부', slaHours: 12 },
  { key: 'praise',   label: '직원·강사 칭찬합니다', sheet: '접수_칭찬',     dept: '운영부', slaHours: null },
  { key: 'voice',    label: '직원·강사 쓴소리합니다', sheet: '접수_쓴소리', dept: '운영부', slaHours: 72 },
  { key: 'complaint', label: '컴플레인 접수',        sheet: '접수_컴플레인', dept: '운영부', slaHours: 48 }
  // praise/voice → dept: '인사부' 로 바꿀 때 위 두 줄만 수정
  // ★defaultAssignee 는 2026-08-21 GM 확정으로 뺐다 — 접수처의 사람 분류는 접수자·처리자 둘뿐이다.
  //   기본 담당자를 찍어 두면 '@운영부' 처럼 사람 아닌 값이 담당인 척 남는다. 배정은 부서가 한다.
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
// 컴플레인의 부서 — 장소로 가른다 (GM 확정 2026-08-25).
//   그전에는 컴플레인이 분류만 보고 무조건 '운영부'로 갔다. GM 지적: "컴플레인이 강습부서일수도
//   있고, 시설부 지원부 일수도 있는데, 무조건 운영부로 가게하면 안되는데?"
//   실측(같은 날 컴플레인 39건 처리 이력): 운영부가 아닌 사람이 절반 가까이 처리하고 있었다
//   — 이정헌 소장 5 · 김종현 차장 1 · 윤병현AM 1 · 이경연 실장 3 · 최준용M 13.
//   장소 13개는 접수 폼의 고정 선택지(reception_block.html LOCATIONS)와 1:1로 맞춘 것이다.
//   ▸컴플레인에만 적용한다 — 분실물·습득물은 리셉션 보관이라 운영부가 맞고, 시설물 고장은
//     시설부, 청결은 아래 성별 규칙이 이미 맞다. 장소를 전 분류에 적용하면 분실물이 P.T팀으로 간다.
//   ▸목록에 없는 장소(자유입력·빈칸)면 종전대로 그 분류의 기본 부서로 둔다.
var REG_COMPLAINT_LOC_DEPT = {
  '헬스장': 'P.T팀',
  '수영장': '수영팀',
  '남자사우나': '지원부(남)',
  '여자사우나': '지원부(여)',
  '락커': '지원부',
  '골프장': '골프팀',
  '스쿼시장': '스쿼시팀',
  '체조장': '체조팀',
  'G.X룸': 'G.X팀',
  '주차장': '주차관리부',
  '리셉션': '운영부',
  '카페': '카페',
  '기타': '운영부'
};

// 청결 접수의 부서 — 남/여 구역 담당 반장님이 갈린다(GM 지시 2026-08-15 · 부서 3개 → 11개).
// 장소에 남/여가 적혀 있을 때만 자동으로 가르고, 안 적혀 있으면 REG_CATEGORIES 의 옛 '지원부' 값을
// 그대로 둔다 — 그 값은 11개 목록에 없어 화면의 '지원부(구분 전)' 칸으로 모이고 사람이 배정한다.
// 임의로 남/여를 찍으면 엉뚱한 반장님께 연락이 간다(실측 2026-08-17: 청결 14건 중 장소가 성별을
// 밝힌 건은 여자사우나 3건뿐, 나머지 11건은 수영장·골프장 등 성별과 무관한 장소였다).
function _regDeptFor(cat, loc) {
  if (!cat) return '';
  var s = String(loc || '').trim();
  if (cat.key === 'complaint') {
    return REG_COMPLAINT_LOC_DEPT[s] || cat.dept;
  }
  if (cat.key !== 'clean') return cat.dept;
  if (/여자|여성/.test(s)) return '지원부(여)';
  if (/남자|남성/.test(s)) return '지원부(남)';
  return cat.dept;
}

// 사진 미수집 카테고리 — GM 결정(2026-07-08): 칭찬·쓴소리는 폼+시트컬럼 모두 사진 제거.
// _regHeadersFor 가 photoUrl 을 정의에서 빼야 reg_submit/reg_update 의 위치기반(_set) 쓰기가
// clean_reg_columns 로 물리 삭제된 실제 시트 컬럼과 계속 정렬된다(안 그러면 컬럼 밀림 발생).
var REG_NO_PHOTO_CATS = { praise: true, voice: true };

// 카테고리 키에 대한 전체 헤더 배열 반환 ({key,label}[])
// 맨 뒤에 붙는 칸 (2026-07-28 시우 · 점수 랭킹제 GM 지시).
// ★왜 COMMON 이 아니라 TAIL 인가: _regGetSheet 는 시트가 새로 생길 때만 헤더를 쓴다.
//   이미 데이터가 있는 시트의 헤더는 그대로 남는데, _regUpdate/_regSubmit 은 '코드의 헤더 순서'로
//   열 번호를 계산한다. COMMON 중간에 칸을 넣으면 그 뒤의 카테고리별 추가칸(분실물품·분실시점 등)이
//   한 칸씩 밀려 기존 데이터 위에 엉뚱한 값을 쓰게 된다. 맨 뒤에 붙이면 기존 열 번호가 하나도
//   안 움직이고, 새 칸만 지금 마지막 열 다음에 생긴다(무중단).
// handler=처리자: ★시트엔 '처리자' 칸이 이미 있었고 값도 들어 있었는데, 코드의 헤더 목록에 없어서
//   _regReadAll 이 그 열을 통째로 버리고 있었다 — 화면·알림·집계 어디에도 안 보였다(2026-07-28 실측).
//   저장이 안 된 게 아니라 '읽지를 않고' 있었다. 키를 등록하는 것만으로 옛 값까지 같이 살아난다.
// reporter=접수자: 누가 적었는지. 점수의 절반(접수 1점)이 여기서 나온다.
var REG_TAIL_HEADERS = [
  { key: 'handler',  label: '처리자' },
  { key: 'reporter', label: '접수자' },
  // 회원 안내(회원 셀프 조회 노출 문구). 처리메모(내부)와 별개. 2026-08-03 복구.
  { key: 'memberReply', label: '회원안내' }
];

function _regHeadersFor(catKey) {
  var extra = REG_EXTRA_HEADERS[catKey] || [];
  var common = REG_NO_PHOTO_CATS[catKey]
    ? REG_COMMON_HEADERS.filter(function (h) { return h.key !== 'photoUrl'; })
    : REG_COMMON_HEADERS;
  return common.concat(extra).concat(REG_TAIL_HEADERS);
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
// ★2026-08-05 시토 — 한 번의 요청 안에서 스프레드시트를 여러 번 여는 것을 막는다.
//   reg_list·reg_scoreboard·reg_staff_suggest·reg_board 는 카테고리 6개를 돌며 시트를 여는데,
//   그때마다 _regGetSheet → _vGetSpreadsheet 를 거쳐 openById 를 새로 호출하고 있었다(요청당 6번).
//   openById 는 파일을 여는 호출이라 한 번이 가장 비싸다. GAS 전역 변수는 실행 1회 동안만
//   살아 있으므로 여기 담아 두면 같은 요청 안에서만 재사용되고, 다음 요청은 다시 새로 연다
//   — 오래된 값을 들고 있을 위험이 없다.
var _VSS_CACHE = null;

function _vGetSpreadsheet() {
  if (_VSS_CACHE) return _VSS_CACHE;
  var ssId = _vprop('SPREADSHEET_ID');
  if (!ssId) throw new Error('ScriptProperties에 SPREADSHEET_ID 미설정 — 프로젝트 설정 → 스크립트 속성에 추가');
  _VSS_CACHE = SpreadsheetApp.openById(ssId);
  return _VSS_CACHE;
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
  var widths = [170, 150, 90, 110, 220, 320, 130, 80, 280];
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
      return sh;
    }
    // 아직 없는 헤더 이름만 맨 뒤에 덧붙인다(2026-07-28 시우).
    //   기존 헤더는 절대 건드리지 않는다 — 읽는 쪽(_regReadAll)이 한글 헤더 '이름'으로 찾기 때문에
    //   이름을 바꾸거나 겹쳐 쓰면 그 조회가 조용히 끊긴다.
    //   ★'있는지'로 판정한다(개수로 하지 않는다): 실측 2026-07-28 — '처리자' 칸은 이미 전 시트에
    //   있었고 값도 들어 있었다(코드 헤더 목록에만 없어서 모든 화면·집계에서 안 보였을 뿐).
    //   개수만 보고 뒤에 이어 쓰면 같은 이름이 두 개가 되고, 빈 쪽이 값을 덮어 읽힌다.
    var have = sh.getLastColumn();
    var existingLabels = have > 0 ? sh.getRange(1, 1, 1, have).getValues()[0].map(String) : [];
    var missing = headers.filter(function (label) { return existingLabels.indexOf(label) < 0; });
    if (missing.length) {
      sh.getRange(1, have + 1, 1, missing.length).setValues([missing]);
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

// 알림 한 줄용 길이 자르기 (2026-08-08 GM 지적).
// 그 전엔 내용을 24자에서 그냥 잘랐다. 접수 내용에 줄바꿈이 있으면 알림 한 줄이 여러 줄로
// 깨지고, 낱말·괄호 한가운데서 끊겨 뜻이 안 통했다. GM 이 받은 실제 알림:
//   "🔴 [시설물 고장 접수] 자동 부팅 안됨 / T업기 타석 제어 안됨(타석 — 24분 초과 (…"
// 두 줄로 벌어지고 여는 괄호가 닫히지 않은 채 끝났다.
// ▸줄바꿈·연속 공백을 한 칸으로 눌러 한 줄로 만들고, 상한 안에서 마지막 띄어쓰기까지만 남긴다.
// ▸잘렸으면 …을 붙여 잘렸다는 것이 보이게 한다(잘린 티가 나는 게 뜻이 끊기는 것보다 낫다).
// ▸같은 규칙이 카톡 쪽에도 있다(scripts/send_ops_digest.py _cap_line) — 여기는 구글 서버에서
//   도는 코드라 그 함수를 못 부른다. 규칙을 바꾸면 두 곳을 같이 고친다.
function _regCapLine(s, n) {
  var t = String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  if (!t) return '(내용 없음)';
  if (t.length <= n) return t;
  var head = t.slice(0, n);
  var cut = head.lastIndexOf(' ');
  if (cut >= Math.floor(n / 2)) head = head.slice(0, cut);
  // 괄호가 열린 채로 끝나면 그 괄호 앞에서 끊는다 — "안됨(타석…" 처럼 반쪽 괄호가 남으면
  // 읽는 사람이 뒤에 뭐가 있었는지 되묻게 된다(GM 이 지적한 그 모양이다).
  var open = Math.max(head.lastIndexOf('('), head.lastIndexOf('['));
  var close = Math.max(head.lastIndexOf(')'), head.lastIndexOf(']'));
  if (open > close && open >= Math.floor(n / 3)) head = head.slice(0, open);
  return head.replace(/[\s·\-—(\[,]+$/, '') + '…';
}

// ─── SLA 초과 '전환 시점' 텔레그램 알림 (COO 배163 · 2026-07-27) ───
// 기존 _vNotifyTelegram 재사용(신규 알림 채널·봇 없음). 매 호출마다 스팸 발송 방지를 위해
// '이번에 새로 초과 전환된 건'만 알린다 — 직전 체크의 초과 ID 집합을 ScriptProperties에 저장해 비교.
// 호출 경로: 시간 트리거(30분마다) — installReceptionSlaTrigger()로 설치.
// ★2026-08-05 시토 실측: 라이브 GAS에 getProjectTriggers()로 직접 조회해 _regSlaCheckTrigger
// CLOCK 트리거가 실제로 걸려 있음을 확인했다(이전 주석 "이 배포에선 미설치"는 낡은 정보 — 정정).
var REG_SLA_NOTIFIED_PROP = 'REG_SLA_NOTIFIED_IDS';
var REG_DASHBOARD_URL = 'https://wellperion-cao.github.io/wellperion-automation/coo/reception/종합접수처_현황.html';

function _regSlaOverdueNow() {
  var boardResult = JSON.parse(_regList({}).getContent());
  var rows = (boardResult.data || []).map(_regComputeSla);
  return rows.filter(function (r) { return r.slaStatus === '초과'; });
}

// dryRun=true(기본): 문구만 만들고 발송·상태저장 안 함(테스트 안전). dryRun=false: 실제 발송 + 상태 저장.
function _regNotifySlaOverdue(dryRun) {
  if (dryRun === undefined) dryRun = true;
  var overdue = _regSlaOverdueNow();
  var prevIds = [];
  try {
    var raw = PropertiesService.getScriptProperties().getProperty(REG_SLA_NOTIFIED_PROP);
    prevIds = raw ? JSON.parse(raw) : [];
  } catch (e) { prevIds = []; }

  var curIds = overdue.map(function (r) { return String(r.regId || ''); });
  var newlyOverdue = overdue.filter(function (r) { return prevIds.indexOf(String(r.regId || '')) < 0; });
  newlyOverdue.sort(function (a, b) { return (a.remainH || 0) - (b.remainH || 0); }); // 많이 밀린 순

  var result = { ok: true, overdueTotal: overdue.length, newlyOverdue: newlyOverdue.length, notified: false, text: '' };

  if (newlyOverdue.length > 0) {
    var lines = [];
    lines.push('⏰ <b>[종합접수처 SLA 초과]</b>');
    lines.push('신규 초과 ' + newlyOverdue.length + '건 · 전체 초과 ' + overdue.length + '건');
    newlyOverdue.slice(0, 10).forEach(function (r) {
      var overAbs = (r.remainH !== null && r.remainH !== undefined) ? Math.abs(r.remainH) : null;
      var over = (overAbs === null) ? '-'
        : overAbs < 1  ? Math.round(overAbs * 60) + '분'
        : overAbs < 24 ? Math.round(overAbs) + '시간'
        : Math.floor(overAbs / 24) + '일';
      lines.push('  🔴 [' + (r.category || '') + '] ' + _regCapLine(r.content, 28) +
        // ★2026-08-21 GM 확정 — '담당/미배정' 표기 제거(접수처에 담당자 개념 없음).
        //   부서는 같은 줄 위 그룹 제목이 이미 말해 준다.
        ' — ' + over + ' 초과 (' + (r.regId || '') + ')');
    });
    if (newlyOverdue.length > 10) lines.push('  … 외 ' + (newlyOverdue.length - 10) + '건');
    lines.push('👉 확인: ' + REG_DASHBOARD_URL);
    result.text = lines.join('\n');
    if (!dryRun) {
      _vNotifyTelegram(result.text);
      result.notified = true;
    }
  }

  if (!dryRun) {
    try { PropertiesService.getScriptProperties().setProperty(REG_SLA_NOTIFIED_PROP, JSON.stringify(curIds)); } catch (e) {}
  }
  return result;
}

// 시간 트리거 핸들러(실발송 고정) — installReceptionSlaTrigger()가 이 함수를 30분 주기로 건다.
function _regSlaCheckTrigger() {
  _regNotifySlaOverdue(false);
}

// 트리거 설치(멱등 — 기존 동일 핸들러 있으면 스킵). 배포 1회성 설치용, GAS 에디터 실행 또는
// action=reg_install_sla_trigger(GATED) 경유로 1회만 호출한다. 2026-07-27 시토(GM 승인 배포).
function installReceptionSlaTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === '_regSlaCheckTrigger') {
      Logger.log('installReceptionSlaTrigger: 트리거 이미 존재 — 스킵');
      return '이미 존재';
    }
  }
  ScriptApp.newTrigger('_regSlaCheckTrigger').timeBased().everyMinutes(30).create();
  Logger.log('installReceptionSlaTrigger: 30분 주기 트리거 설치 완료');
  return '설치 완료';
}

// 트리거 제거 (GM 지시 2026-08-12 "이것좀 더이상 안뜨게 하고싶은데").
// 왜: 이 30분 알림은 '새로 기한을 넘긴 건'마다 즉시 울린다. 적체가 24건 쌓여 있는 동안은
// 하루에도 여러 번 울리는데, 같은 내용을 매일 22:30 종합접수 정리(report_stream_2b_reception)가
// 이미 한 번에 알려 준다 — 실시간 알림은 그 위에 얹힌 중복 소음이었다(약속 L21).
// 정보 손실 0: 기한 초과 목록은 22:30 정리와 종합접수처 화면에 그대로 남는다.
// 되돌리기: installReceptionSlaTrigger() 또는 action=reg_install_sla_trigger 한 번.
function uninstallReceptionSlaTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === '_regSlaCheckTrigger') {
      ScriptApp.deleteTrigger(triggers[i]);
      removed++;
    }
  }
  Logger.log('uninstallReceptionSlaTrigger: ' + removed + '개 제거');
  return { removed: removed };
}

// ─── 종합 접수처 라벨→키 별칭 (시트 실헤더 라벨 드리프트 흡수 · SSOT) ───
// 시트 1행 실제 라벨이 REG_COMMON/EXTRA_HEADERS 정의 라벨과 다른 경우(예: 분실물 탭)를 흡수.
var REG_LABEL_ALIASES = { '분실위치': 'loc', '위치': 'loc', '물품상세': 'content' };   // '위치'·'분실위치' = loc 구헤더 하위호환(장소 rename 전/후 모두 정독). '장소'는 REG_COMMON_HEADERS 정의라 자동 매핑.

// ─── 종합 접수처 시트 → 객체 배열 (헤더-이름 기준 매핑 · 컬럼 물리삭제/순서변경에 안전) ───
// headers({key,label}[])로 라벨→키 맵을 만들고, 시트 1행 실제 헤더 라벨로 각 열의 키를 찾는다.
// 매칭 안 되는 컬럼(빈칸·잔재 라벨)은 조용히 무시 — 위치기반이 아니므로 중간 컬럼 삭제에도 값이 안 밀림.
// ─── 쓰기용 열 위치 맵 (2026-07-28 시우) ───
// 읽기(_regReadAll)는 예전부터 '헤더 이름'으로 열을 찾아 안전했는데, 쓰기(_regSubmit·_regUpdate)는
// '코드에 적힌 순서'로 열 번호를 셌다. 두 방식이 어긋나 있어도 읽을 땐 멀쩡해 보이니 아무도 몰랐다.
// 실측 2026-07-28: 컴플레인 시트는 실제로 [… 처리자, 조치문자, 접수자] 순인데 코드 순서로는
// 접수자가 '조치문자' 자리에 해당했다 — 그대로 뒀으면 새 접수마다 조치문자 칸을 덮어썼다.
// 분실물 시트도 7번째가 '물품상세'(=내용 별칭)라 코드 순서와 다르다.
// → 쓰기도 읽기와 똑같이 '헤더 이름'으로 찾는다. 한 곳에서 같은 규칙을 쓰면 어긋날 수가 없다.
function _regKeyCols(sh, headers) {
  var lastCol = sh.getLastColumn();
  var label2key = {};
  headers.forEach(function (h) { label2key[h.label] = h.key; });
  Object.keys(REG_LABEL_ALIASES).forEach(function (label) {
    if (!(label in label2key)) label2key[label] = REG_LABEL_ALIASES[label];
  });
  var out = {};
  if (lastCol < 1) return out;
  var labels = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(String);
  labels.forEach(function (label, i) {
    var key = label2key[label];
    if (key && !(key in out)) out[key] = i;   // 같은 이름이 둘이면 앞쪽(원본)을 쓴다
  });
  return out;
}

// ★2026-08-05 시토 — 읽기 열 위치를 쓰기와 같은 함수(_regKeyCols)에서 구하도록 바꿨다.
//   왜: 같은 키에 해당하는 헤더가 한 시트에 두 개 있을 때 읽기와 쓰기가 서로 다른 칸을 골랐다.
//   예전 읽기는 헤더를 왼쪽부터 훑으며 obj[key] 를 계속 덮어써서 '마지막 칸'이 이겼고,
//   쓰기(_regKeyCols)는 주석대로 '앞쪽 원본'을 골랐다. 두 규칙이 반대라 값이 엇갈렸다.
//   실측 2026-08-05: 분실물 시트는 7번째가 '물품상세'(=content 별칭), 17번째가 나중에 덧붙은
//   '내용'이다. 접수는 전부 7번째에 저장되는데 읽기는 비어 있는 17번째를 읽어, 라이브 27건
//   전부 내용이 빈칸으로 나왔다(적체 리마인드·다이제스트·현황판에 품목 설명이 안 보였다).
//   이제 읽기·쓰기가 같은 한 곳에서 열을 찾으니 다시 어긋날 수가 없다.
//   덤으로 열 위치를 행마다 다시 찾지 않고 한 번만 구한다(라벨 조회 81행×19열 → 19회).
function _regReadAll(sh, headers) {
  var lastCol = sh.getLastColumn();
  var last = sh.getLastRow();
  if (last < 2 || lastCol < 1) return [];

  var keyCols = _regKeyCols(sh, headers);
  var pairs = Object.keys(keyCols).map(function (k) { return [k, keyCols[k]]; });

  var data = sh.getRange(2, 1, last - 1, lastCol).getValues();
  return data.map(function (row) {
    var obj = {};
    pairs.forEach(function (p) {
      var v = row[p[1]];
      if (v instanceof Date) {
        v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      }
      obj[p[0]] = v;
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
    if (!existing.hasNext()) {   // 아직 개명 전이면 옛 이름으로 한 번 더 — 새 폴더를 만들어 갈라지지 않게
      existing = DriveApp.getRootFolder().getFoldersByName(RECEPTION_PHOTO_FOLDER_NAME_OLD);
    }
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
function _vNotifyTelegram(text, photoUrl, chatIdOverride) {
  var token = _vprop('TELEGRAM_BOT_TOKEN');
  var chatId = chatIdOverride || _vprop('TELEGRAM_CHAT_ID');   // 3번째 인자로 다른 방(예: 시설팀) 지정 가능. 2026-08-16.
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
  if (newStatus && LEGACY_RECEPTION_STATUSES.indexOf(newStatus) < 0) {
    return _vJson({ ok: false, error: '상태는 접수|처리중|완료 만 허용' });
  }

  var memo = body.memo !== undefined ? body.memo
    : (body['처리메모'] !== undefined ? body['처리메모'] : undefined);

  // 답변(처리메모) 자동 상태 전환 — 규칙은 _regEffectiveStatusOnMemo 단일 정의(파일 상단 참고).
  var curStatus = String(existing[LEGACY_RECEPTION_HEADERS.indexOf('상태')] || '');
  var effStatus = _regEffectiveStatusOnMemo(curStatus, newStatus, memo);
  if (effStatus) existing[LEGACY_RECEPTION_HEADERS.indexOf('상태')] = effStatus;

  if (memo !== undefined) existing[LEGACY_RECEPTION_HEADERS.indexOf('처리메모')] = String(memo);

  sh.getRange(rowNum, 1, 1, LEGACY_RECEPTION_HEADERS.length).setValues([existing]);
  if (effStatus) _vApplyStatusColor(sh, rowNum, effStatus);

  return _vJson({
    ok: true, id: id,
    status: existing[LEGACY_RECEPTION_HEADERS.indexOf('상태')],
    message: '접수건이 갱신되었습니다.'
  });
}

// ═══════════════════════════════════════════
//  종합 접수처 액션
// ═══════════════════════════════════════════

// ─── 「전달문구」 초안 자동 채움 (GM 제안 2026-08-05) ───
// 화면(종합접수처_현황.html 776~784행)은 이미 있는 처리메모(memo)를 「전달문구」로 그대로
// 보여줄 뿐이다 — 새 칸·새 화면 없이 접수 시점에 memo 를 채워 넣기만 하면 화면은 저절로 뜬다.
// ★사람이 이미 쓴 memo 는 절대 덮지 않는다 — _regShouldDraftMemo 가 비어 있을 때만 통과시키고,
//   호출부(_regSubmit)는 그 판정을 거쳐야만 memo 를 채운다(공개 제출 폼엔 memo 입력 자체가 없어
//   신규 접수는 항상 빈 상태로 들어온다 — 그래도 규칙은 방어적으로 한 번 더 확인한다).
// ★앞에 '[초안] '을 붙여 초안임을 드러낸다 — 실무진이 그대로 보낼지 판단하고, 고치는 순간부터는
//   위 덮어쓰기 금지 규칙이 사람 문구로 지켜준다.
// ★분류를 모르거나 본문이 너무 짧으면 빈 문자열을 돌려준다(빈칸 > 엉뚱한 초안).
// 톤 = ssot/약속.json L07(표준 문의 안내)·L08(브랜드 말투) + wellperion-brand 스킬 §5:
//   "피트니스"·"하이엔드프라이빗" 금지, "스포츠클럽", 압박 없이 알리는 격조 있는 톤.
// 순수함수 — GAS API 미의존, Node에서도 그대로 테스트 가능(_regEffectiveStatusOnMemo 와 같은 원칙).
var REG_DRAFT_MIN_CONTENT_LEN = 2;   // 이보다 짧은 본문(빈칸·한 글자)은 판단 근거가 부실 → 초안 생략
// 본문만 적는다 — 앞의 '[초안] ' 접두어는 _regDraftMemo 가 REG_DRAFT_PREFIX 로 붙인다(파일 상단 단일 출처).
var REG_DRAFT_TEMPLATES = {
  lost:      '분실물 접수 확인했습니다. 운영팀이 확인 후 보관 여부를 안내드리겠습니다.',
  facility:  '시설물 고장 확인했습니다. 시설팀이 신속히 점검 후 조치하겠습니다.',
  clean:     '청결 관련 사항 확인했습니다. 지원팀이 즉시 확인해 정리하겠습니다.',
  praise:    '소중한 칭찬 감사합니다. 담당 직원에게 잘 전달하겠습니다.',
  voice:     '소중한 의견 감사합니다. 관련 부서에 전달해 개선하겠습니다.',
  complaint: '불편을 드려 죄송합니다. 운영팀이 확인 후 신속히 조치하겠습니다.'
};
// 이미 사람이 쓴 memo 가 있으면 false — 덮어쓰기 금지 규칙의 단일 판정점.
function _regShouldDraftMemo(existingMemo) {
  return !String(existingMemo || '').trim();
}

// ─── 회원 안내(memberReply) 완료 시 자동 채움 (2026-08-18 GM 지시) ───
// 위 REG_DRAFT_TEMPLATES(처리메모 초안·실무진이 보는 문구)와는 다른 글 — 이건 회원이 직접 읽는
// '처리 결과 안내'라 접두어 없이 그대로 나가고, 상태가 '완료'로 바뀌는 순간에만 채운다(접수
// 시점엔 아직 결과가 없어 미리 넣으면 거짓말이 된다). 덮어쓰기 금지 판정은 같은 규칙(빈 값인지만
// 본다)이라 새 함수를 만들지 않고 _regShouldDraftMemo 를 그대로 재사용한다(약속 L21).
// 문구는 GM 확정본 그대로(2026-08-18) — 임의 수정 금지.
var REG_MEMBER_REPLY_TEMPLATES = {
  lost:      '말씀해 주신 물품 접수했습니다. 리셉션에서 보관 중이니 방문하실 때 말씀해 주시면 확인해 드리겠습니다.',
  facility:  '알려주신 부분 확인해 조치를 마쳤습니다. 이용에 불편을 드려 죄송합니다.',
  clean:     '말씀해 주신 곳 확인하고 정리했습니다. 알려주셔서 감사합니다.',
  praise:    '따뜻한 말씀 감사합니다. 해당 직원에게 그대로 전해 드렸습니다.',
  voice:     '말씀해 주신 내용 잘 받았습니다. 내부에서 확인해 개선하겠습니다.',
  complaint: '불편을 드려 죄송합니다. 말씀해 주신 부분 확인해 조치했습니다.'
};
// 카테고리 키로 완료 안내 문구(또는 빈 문자열) 반환. 순수함수 — GAS API 미의존.
function _regMemberReplyDraft(catKey) {
  return REG_MEMBER_REPLY_TEMPLATES[catKey] || '';
}
// 카테고리 키 + 본문으로 초안 문자열(또는 빈 문자열) 반환.
function _regDraftMemo(catKey, content) {
  var tpl = REG_DRAFT_TEMPLATES[catKey];
  if (!tpl) return '';                                                              // 모르는 분류 → 비워 둔다
  if (String(content || '').trim().length < REG_DRAFT_MIN_CONTENT_LEN) return '';   // 본문 부실 → 비워 둔다
  return REG_DRAFT_PREFIX + tpl;
}
// assert 기반 자체점검 — GAS 에디터에서 직접 실행하거나 action=reg_draft_selftest(GET, read-only)로 호출.
// 새 테스트 프레임워크 없이 순수함수만 검증 — 시트를 전혀 건드리지 않는다.
function _regAssertEq_(actual, expected, label, failures) {
  if (actual !== expected) {
    failures.push(label + ': expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
  }
}
function _regDraftMemoSelfCheck() {
  var failures = [];
  Object.keys(REG_DRAFT_TEMPLATES).forEach(function (key) {
    var out = _regDraftMemo(key, '테스트 접수 본문입니다');
    _regAssertEq_(out, REG_DRAFT_PREFIX + REG_DRAFT_TEMPLATES[key], 'draft:' + key, failures);
    _regAssertEq_(out.indexOf(REG_DRAFT_PREFIX) === 0, true, 'prefix:' + key, failures);
    // 초안은 상태를 올리지 않는다(2026-08-06 시토) — 아래 자동 상태 전환 점검과 짝.
    _regAssertEq_(_regEffectiveStatusOnMemo('접수', '', out), '', 'draft-no-promote:' + key, failures);
  });

  // ─── 답변(처리메모) 자동 상태 전환 점검 (2026-08-06 시토) ───
  _regAssertEq_(_regEffectiveStatusOnMemo('접수', '', '실무진이 직접 쓴 답변입니다'), '처리중', 'memo-promotes', failures);
  _regAssertEq_(_regEffectiveStatusOnMemo('접수', '', REG_DRAFT_PREFIX + '무엇이든'), '', 'draft-prefix-blocks', failures);
  _regAssertEq_(_regEffectiveStatusOnMemo('접수', '완료', REG_DRAFT_PREFIX + '무엇이든'), '완료', 'explicit-status-wins', failures);
  _regAssertEq_(_regEffectiveStatusOnMemo('완료', '', '추가 답변'), '', 'done-stays-done', failures);
  _regAssertEq_(_regEffectiveStatusOnMemo('접수', '', ''), '', 'empty-memo-no-change', failures);
  _regAssertEq_(_regEffectiveStatusOnMemo('접수', '', undefined), '', 'undefined-memo-no-change', failures);
  _regAssertEq_(_regDraftMemo('unknown_cat', '충분히 긴 본문입니다'), '', 'unknown-cat-blank', failures);
  _regAssertEq_(_regDraftMemo('lost', ''), '', 'empty-content-blank', failures);
  _regAssertEq_(_regDraftMemo('lost', ' '), '', 'whitespace-content-blank', failures);
  _regAssertEq_(_regDraftMemo('lost', 'a'), '', 'too-short-content-blank', failures);
  _regAssertEq_(_regShouldDraftMemo(''), true, 'should-draft-empty', failures);
  _regAssertEq_(_regShouldDraftMemo('   '), true, 'should-draft-whitespace', failures);
  _regAssertEq_(_regShouldDraftMemo('사람이 이미 쓴 메모'), false, 'should-not-draft-existing-memo', failures);

  // ─── 회원 안내(memberReply) 완료 시 자동 채움 점검 (2026-08-18) ───
  Object.keys(REG_MEMBER_REPLY_TEMPLATES).forEach(function (key) {
    _regAssertEq_(_regMemberReplyDraft(key), REG_MEMBER_REPLY_TEMPLATES[key], 'memberReply:' + key, failures);
  });
  _regAssertEq_(_regMemberReplyDraft('unknown_cat'), '', 'memberReply-unknown-cat-blank', failures);
  // 빈 값이면 채운다
  _regAssertEq_(_regShouldDraftMemo('') && !!_regMemberReplyDraft('lost'), true, 'memberReply-fills-when-empty', failures);
  // 사람이 이미 쓴 값이면 안 덮는다
  _regAssertEq_(_regShouldDraftMemo('회원에게 이미 보낸 안내'), false, 'memberReply-keeps-existing', failures);

  // ─── 읽기·쓰기 열 일치 점검 (2026-08-05 시토) ───
  // 같은 키에 해당하는 헤더가 한 시트에 둘 있을 때(분실물의 '물품상세'·'내용') 읽기와 쓰기가
  // 같은 칸을 고르는지 확인한다. 이게 어긋나 라이브 분실물 27건의 내용이 전부 빈칸으로 나왔다.
  // 새 액션·새 파일을 만들지 않으려고 기존 자체점검(reg_draft_selftest, GET·read-only)에 얹었다.
  // 시트를 흉내 낸 가짜 객체만 쓰므로 실제 시트는 전혀 건드리지 않는다.
  var _lostHeaderRow = ['접수ID', '카테고리', '접수일시', '이름', '연락처', '장소', '물품상세',
                        '사진URL', '상태', '담당', '처리메모', '부서', '분실물품', '분실시점',
                        '처리자', '접수자', '내용', '기한일수', '회원안내'];
  var _lostDataRow = new Array(_lostHeaderRow.length).fill('');
  _lostDataRow[6] = '검은색 무선이어폰 세트';   // 접수가 실제로 저장되는 칸('물품상세')
  var _fakeSheet = {
    getLastColumn: function () { return _lostHeaderRow.length; },
    getLastRow:    function () { return 2; },
    getRange: function (r, c, nr, nc) {
      var all = [_lostHeaderRow, _lostDataRow];
      return { getValues: function () {
        return all.slice(r - 1, r - 1 + nr).map(function (row) { return row.slice(c - 1, c - 1 + nc); });
      } };
    }
  };
  var _lostHeaders = _regHeadersFor('lost');
  _regAssertEq_(_regKeyCols(_fakeSheet, _lostHeaders).content, 6, 'keycols-content-first-match', failures);
  _regAssertEq_(_regReadAll(_fakeSheet, _lostHeaders)[0].content, '검은색 무선이어폰 세트',
                'readall-content-matches-write-column', failures);

  return { ok: failures.length === 0, failures: failures, checked: Object.keys(REG_DRAFT_TEMPLATES).length * 2 + 9 + Object.keys(REG_MEMBER_REPLY_TEMPLATES).length + 3 };
}

// ─── 일회성 정비: 시트에서 '담당' 열 지우기 (2026-08-21 GM 확정 · 시우) ───
// 접수처의 사람 분류는 접수자·처리자 둘뿐이다. 코드는 이 배포부터 '담당'을 읽지도 쓰지도
// 않는다 — 남은 것은 시트에 박혀 있는 옛 '담당' 열과 그 값뿐이라 이 함수가 한 번만 지운다.
//
// 왜 열을 지워도 다른 값이 밀리지 않나: 이 스크립트의 읽기·쓰기는 전부 _regKeyCols 로
//   '시트 실제 헤더 이름'에서 열 위치를 구한다(2026-07-28 시우 · 2026-08-05 시토). 코드에
//   박힌 순번을 쓰는 곳은 존재하지 않는 레거시 탭('접수 RECEPTION') 경로뿐이다.
// 되돌리기: 열은 다시 만들 수 있지만 값은 복구되지 않는다. 실행 전 스프레드시트 사본을 뜬다.
// 여러 번 실행해도 안전하다(이미 없으면 건너뛴다).
function regDropAssigneeColumn() {
  var out = [];
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { out.push(cat.sheet + ' — 시트 없음'); return; }
    var lastCol = sh.getLastColumn();
    if (lastCol < 1) { out.push(cat.sheet + ' — 빈 시트'); return; }
    var labels = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(String);
    var i = labels.indexOf('담당');
    if (i < 0) { out.push(cat.sheet + ' — 담당 열 없음(이미 정리됨)'); return; }
    sh.deleteColumn(i + 1);
    out.push(cat.sheet + ' — 담당 열 삭제(' + (i + 1) + '번째)');
  });
  _regBoardCacheClear_();
  var msg = out.join('\n');
  Logger.log(msg);
  return msg;
}

// ─── reg_submit — 종합 접수처 제출 (public) ───
// ─── 재제출 흡수 (배597 · GM 지적 2026-08-13) ────────────────────────────────
//   왜 여기(관문)에 두나: 접수 쓰기는 _regSubmit 하나만 지난다. 폼마다 막으면 우회로가 생긴다(약속 L21).
var REG_MERGE_WINDOW_MIN = 30;   // 이 시간 안의 같은 건만 흡수. 길게 잡으면 진짜 두 번째 신고를 삼킨다.
var REG_MERGE_SCAN_ROWS  = 20;   // 시트는 최신순 정렬이라 위 몇 줄만 본다(전수 스캔 안 함).

function _regNormPhone_(v) { return String(v == null ? '' : v).replace(/[^0-9]/g, ''); }
function _regNormText_(v)  { return String(v == null ? '' : v).replace(/\s+/g, '').toLowerCase(); }

// createdAt 은 Date 로 오기도, 'yyyy-MM-dd HH:mm:ss' 문자열로 오기도 한다. 둘 다 받는다.
function _regParseTs_(v) {
  if (v instanceof Date) return v.getTime();
  var s = String(v == null ? '' : v).trim();
  var m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
  if (!m) return 0;
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime();
}

// 최근 같은 건이 있으면 그 행의 **빈칸만** 채우고 접수ID 를 돌려준다. 없으면 빈 문자열.
// 사람이 이미 적어 둔 값은 절대 덮지 않는다.
function _regMergeRecent_(cat, headers, contact, content, body, loc, photoUrl) {
  try {
    var wantPhone = _regNormPhone_(contact);
    if (!wantPhone) return '';                     // 익명·자동접수는 흡수 대상 아님
    var sh = _regGetSheet(cat.key);
    var last = sh.getLastRow();
    if (last < 2) return '';
    var width   = Math.max(sh.getLastColumn(), headers.length);
    var keyCols = _regKeyCols(sh, headers);
    var ci = keyCols['contact'], cai = keyCols['createdAt'], idi = keyCols['regId'];
    if (ci === undefined || cai === undefined || idi === undefined) return '';
    var sti = keyCols['status'], coi = keyCols['content'];

    var extras     = REG_EXTRA_HEADERS[cat.key] || [];
    var firstExtra = extras.length ? extras[0].key : '';   // 분실물=분실물품 · 고장=장비명 …
    var wantItem   = (firstExtra && body[firstExtra] !== undefined)
                     ? _regNormText_(body[firstExtra]) : '';
    var wantSig    = _regNormText_(content) + '|' + wantItem;

    var scan = Math.min(REG_MERGE_SCAN_ROWS, last - 1);
    var vals = sh.getRange(2, 1, scan, width).getValues();
    var nowMs = new Date().getTime();

    for (var i = 0; i < scan; i++) {
      var r = vals[i];
      if (_regNormPhone_(r[ci]) !== wantPhone) continue;
      if (sti !== undefined && String(r[sti] || '').trim() !== '접수') continue;  // 이미 처리 들어간 건은 건드리지 않는다
      var haveItem = (firstExtra && keyCols[firstExtra] !== undefined)
                     ? _regNormText_(r[keyCols[firstExtra]]) : '';
      var haveSig  = _regNormText_(coi !== undefined ? r[coi] : '') + '|' + haveItem;
      if (haveSig !== wantSig) continue;
      var t = _regParseTs_(r[cai]);
      if (!t || (nowMs - t) > REG_MERGE_WINDOW_MIN * 60 * 1000) continue;

      var changed = false;
      var fill = function (key, val) {
        if (!val) return;
        var k = keyCols[key];
        if (k === undefined) return;
        if (String(r[k] == null ? '' : r[k]).trim() !== '') return;   // 이미 값이 있으면 안 덮는다
        r[k] = val;
        changed = true;
      };
      fill('loc', loc);
      fill('photoUrl', photoUrl);
      extras.forEach(function (h) {
        if (body[h.key] !== undefined) fill(h.key, String(body[h.key]));
      });
      if (changed) sh.getRange(i + 2, 1, 1, width).setValues([r]);

      // 조용히 삼키지 않는다 — 보완이 있었으면 한 줄만 더 알린다(새 접수 알림은 안 나간다).
      if (changed) {
        try {
          _vNotifyTelegram(
            '📋 <b>[종합 접수처]</b> ' + cat.label + ' — 같은 건 보완\n' +
            '접수ID: ' + String(r[idi] || '') + '\n' +
            '보탠 내용: ' + (loc ? '장소 ' + loc + ' ' : '') + (photoUrl ? '사진 ' : '') + '\n' +
            '(회원이 같은 건을 다시 보내 새 접수 대신 기존 건에 합쳤습니다)',
            ''
          );
        } catch (e2) {}
      }
      return String(r[idi] || '');
    }
  } catch (e) {
    Logger.log('[_regMergeRecent_] 흡수 판정 건너뜀(새 접수로 진행): ' + e);
  }
  return '';
}

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
  // ★같은 사람이 같은 건을 다시 보내면 새 접수를 만들지 않고 기존 접수에 얹는다 (GM 지적 2026-08-13).
  //   실측: RECEPTION-103(08:48:30 · 장소 빈칸) 과 104(08:50:55 · 장소 '남자사우나') 가 같은 회원·
  //   같은 물품으로 2분 24초 차이로 두 건 들어왔다. 회원이 잘못 보낸 것을 **고칠 방법이 없어서**
  //   다시 보낸 것이다(회원 셀프 조회 reg_lookup 은 읽기 전용). 접수 창구에 '수정'이 없으니 재제출이
  //   유일한 길이고, 그러면 운영부는 같은 물건을 두 번 찾는다.
  //   판정은 좁게 — 같은 카테고리 · 같은 연락처(숫자만) · 같은 내용/물품 · 아직 '접수' 상태 · 30분 이내.
  //   하나라도 다르면 새 접수로 둔다(진짜 두 번째 신고를 삼키지 않는다).
  var _mergedId = _regMergeRecent_(cat, headers, contact, content, body, loc, photoUrl);
  if (_mergedId) {
    _regBoardCacheClear_();
    return _vJson({ ok: true, id: _mergedId, dept: cat.dept, merged: true });
  }


  var id  = _vNextSeqId();
  var now = _vNow();

  // 행 구성 — 열 위치는 '시트 실제 헤더 이름' 기준(2026-07-28 시우, _regKeyCols).
  //   전에는 코드에 적힌 순서로 넣었는데, 시트가 그 순서와 달라도 티가 안 났다
  //   (읽기는 이름으로 찾으니 멀쩡해 보임). 컴플레인 시트에서 실제로 어긋나 있었다.
  var _shForCols = _regGetSheet(cat.key);
  var _keyCols = _regKeyCols(_shForCols, headers);
  var row = new Array(Math.max(_shForCols.getLastColumn(), headers.length)).fill('');
  var _set = function (key, val) {
    if (key in _keyCols) { row[_keyCols[key]] = val; }
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
  _set('dept',     _regDeptFor(cat, loc));
  // ★2026-08-21 GM 확정 — 접수처의 사람 분류는 접수자·처리자 둘뿐이다. '담당'은 없앤 칸이라
  //   새 접수에 기본 담당자를 더 이상 찍지 않는다. 그 자동값이 '@운영부' 같은 부서 문자열로
  //   남아 사람이 정해진 것처럼 보였고, 실제로는 아무도 안 잡고 있었다(실측 2026-08-21: 기한초과
  //   13건 중 8건). 배정은 부서가 하고, 처리한 사람은 완료할 때 '처리자' 칸에 남는다.
  //   ▸시트의 '담당' 열과 기존 값은 지우지 않는다 — 옛 기록이고, 열을 지우면 인덱스가 밀린다.
  // 접수자 (2026-07-28 시우 · 점수 랭킹제) — 직원이 대신 적어 준 경우 그 직원 이름,
  //   회원이 폼에서 직접 넣은 경우는 '회원'. 접수 1점의 근거가 되는 칸이라
  //   비워 두면 점수가 안 붙는다(그래서 기본값을 반드시 남긴다).
  _set('reporter', String(body.reporter || '').trim() || (isCheck ? '자동(점검)' : '회원'));

  // extras — 영문키로 body에서 꺼내 한글헤더 위치에 삽입
  var extras = REG_EXTRA_HEADERS[cat.key] || [];
  extras.forEach(function (h) {
    if (body[h.key] !== undefined) _set(h.key, String(body[h.key]));
  });

  // 「전달문구」 초안 — memo 가 비어 있을 때만(사람이 이미 쓴 memo 는 절대 덮지 않는다).
  //   공개 제출 폼엔 memo 입력 자체가 없어 신규 접수는 항상 빈 상태로 들어온다.
  if (_regShouldDraftMemo(body.memo)) {
    var draftMemo = _regDraftMemo(cat.key, content);
    if (draftMemo) _set('memo', draftMemo);
  }

  var sh = _shForCols;
  var newRow = sh.getLastRow() + 1;
  sh.getRange(newRow, 1, 1, row.length).setValues([row]);
  _regApplyStatusColor(sh, newRow, '접수', headers);

  // 최신 접수가 시트 상단에 오도록 접수일시(createdAt) 내림차순 정렬 (헤더 1행 고정) — GM 2026-07-15.
  //   행 전체(색상 포함)가 함께 이동하므로 상태색·사진URL 등 정합 유지. reg_update/delete 는 ID 스캔이라 행위치 무관.
  try { _regSortSheetDesc(sh, headers); } catch (e) {}

  // 카테고리별 추가 칸(고장설비·분실물품 등)을 알림에도 싣는다 — 2026-08-27 GM 지적.
  //   시설물 고장 폼은 '고장설비' 칸에 증상을 적고 '내용'은 비워 두는 경우가 많다(공개 폼에서
  //   내용은 필수가 아니다). 그런데 알림 문구가 content 만 읽어서, 실제로는 내용이 들어와 있는
  //   접수가 텔레그램에서는 '내용: -' 로 나갔다(실측 RECEPTION-136 정태용 · 2026-08-27).
  //   원장에는 멀쩡히 저장돼 있었으므로 데이터 문제가 아니라 알림 문구 문제다.
  var _extraLine = extras.map(function (h) {
    var v = String(body[h.key] == null ? '' : body[h.key]).trim();
    return v ? (h.label + ': ' + v.slice(0, 100)) : '';
  }).filter(function (s) { return s; }).join('\n');
  var _extraBlock = _extraLine ? (_extraLine + '\n') : '';

  // 텔레그램 알림 (익명 접수 시 이름 표기) — 사진 있으면 sendPhoto 로 실제 첨부
  _vNotifyTelegram(
    '📋 <b>[종합 접수처]</b> ' + cat.label + '\n' +
    '부서: ' + _regDeptFor(cat, loc) + '\n' +
    '이름: ' + (isAnon ? '익명' : name) + '\n' +
    '위치: ' + (loc || '-') + '\n' +
    _extraBlock +
    '내용: ' + (content ? content.slice(0, 100) : '-') + '\n' +
    '🕒 ' + now,
    photoUrl
  );

  // 시설부 접수는 시설팀 방에도 별도로 한 번 더 발송(TELEGRAM_FACILITY_CHAT_ID 속성). 드리프트로 사라진 것 복구 2026-08-16.
  if (cat.key === 'facility') {
    var _facChat = _vprop('TELEGRAM_FACILITY_CHAT_ID');
    if (_facChat) _vNotifyTelegram('🔧 <b>[시설물 고장 접수]</b>\n이름: ' + name + '\n위치: ' + (loc || '-') + '\n' + _extraBlock + '내용: ' + (content ? content.slice(0, 100) : '-') + '\n🕒 ' + now, photoUrl, _facChat);
  }

  _regBoardCacheClear_();
  _regLookupCacheClearFor_(contact, name);   // 방금 접수한 사람이 곧바로 조회해도 새 건이 보이게
  return _vJson({ ok: true, id: id, dept: _regDeptFor(cat, loc) });
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

// ─── reg_lookup — 회원 셀프 조회 (공개 · 전화+이름 2차확인 · 회원안전 필드만) ───
// 전화+이름이 둘 다 맞는 행만 반환(남의 번호로 열람 불가) + rate-limit. 내부메모(처리메모)·담당·
// 처리자·접수자·연락처·사진은 응답에서 제외 — 회원안전 필드(내용·상태·회원안내)만 내보낸다.
// ⚠️ '내용'은 회원 원문 노출(GM 결정). 직원은 처리 메모를 '처리메모/회원안내'에만 쓸 것.
function _regLookup(params) {
  var phone = String((params && params.phone) || '').replace(/\D/g, '');
  var name  = String((params && params.name)  || '').replace(/\s/g, '');
  if (!phone || !name) {
    return _vJson({ ok: false, error: '이름과 전화번호를 모두 입력해 주세요.' });
  }
  // 조회 결과 캐시(45초) — 시트 6개를 매번 통째로 읽던 것을 재조회에서는 건너뛴다.
  // reg_board·reg_dashboard 가 쓰던 방식 그대로다(새 장치 0). 쓰기 때 함께 지운다.
  var _lkKey = _regLookupCacheKey_(phone, name);
  try {
    var _lkHit = CacheService.getScriptCache().get(_lkKey);
    if (_lkHit) return _vJson(JSON.parse(_lkHit));
  } catch (e) {}

  if (!_vRateLimitOk_(_vFp_('lookup|' + phone + '|' + name))) {
    return _vJson({ ok: false, error: '요청이 많아 잠시 후 다시 시도해 주세요.', code: 'RATE_LIMIT' });
  }

  var out = [];
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var rows = _regReadAll(sh, _regHeadersFor(cat.key));
    rows.forEach(function (r) {
      var rc = String(r.contact || '').replace(/\D/g, '');
      var rn = String(r.name || '').replace(/\s/g, '');
      if (!rc || rc !== phone) return;   // 전화 일치
      if (rn !== name)         return;   // 이름 일치 (둘 다 맞아야)
      out.push({
        regId:       r.regId       || '',
        category:    r.category    || '',
        createdAt:   r.createdAt   || '',
        status:      r.status      || '',
        content:     r.content     || '',
        memberReply: r.memberReply || ''
      });
    });
  });
  out.sort(function (a, b) { return String(b.createdAt || '') > String(a.createdAt || '') ? 1 : -1; });
  var _lkOut = { ok: true, count: out.length, data: out };
  try { CacheService.getScriptCache().put(_lkKey, JSON.stringify(_lkOut), 45); } catch (e) {}
  return _vJson(_lkOut);
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
    rows.forEach(function (r) {
      // 화면 placeholder 용 — 완료 시 자동으로 채워질 문구를 미리 실어 보낸다(정본은 위
      //   REG_MEMBER_REPLY_TEMPLATES 한 곳뿐, 화면은 이 값을 그대로 참조만 한다. 약속 L01).
      r.memberReplyTemplate = _regMemberReplyDraft(cat.key);
      all.push(r);
    });
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

  // 처리자 이름을 통일한 값을 같이 실어 보낸다(2026-07-31 웰리).
  // ★소비자(알림·보드)는 이 값으로 묶기만 하고 판정을 다시 만들지 않는다 — 규칙이 두 벌이 되면
  //   지금과 똑같이 갈라진다(약속 L01). 실제로 점수판은 통일하고 22:30 적체 알림은 안 해서
  //   같은 메시지 안에서 최준용M(3건)·최준용(5건)이 따로 떴다.
  // ▸담당(assigneeCanon)은 2026-08-21 GM 확정으로 뺐다 — 접수처의 사람 분류는 접수자·처리자뿐.
  all.forEach(function (r) {
    r.handlerCanon = _regStaffCanonList(r.handler);
  });

  return _vJson({ ok: true, count: all.length, data: all });
}

// 처리자 입력 자동완성용 — 지금까지 실제로 쓰인 이름(통일된 표기)을 많이 쓰인 순으로.
// 드롭다운(선택제)이 아니라 '제안'이다. GM 제약: 처리자가 회원일 수 있어 자유 입력을 막지 않는다.
// 고르는 사람은 표기가 통일되고, 새 이름은 그냥 쳐 넣으면 된다.
// ▸담당(assignee)은 2026-08-21 GM 확정으로 제안 재료에서 뺐다 — 없앤 칸이라 옛 값이
//   자동완성으로 되살아나면 안 된다. 접수자(reporter)는 '회원'·'자동(점검)'이 섞여 제외.
function _regStaffSuggest() {
  var count = {};
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    _regReadAll(sh, _regHeadersFor(cat.key)).forEach(function (r) {
      _regStaffCanonList(r.handler).forEach(function (n) {
        count[n] = (count[n] || 0) + 1;
      });
    });
  });
  var names = Object.keys(count).sort(function (a, b) { return count[b] - count[a]; });
  return _vJson({ ok: true, names: names.slice(0, 40) });
}

// ─── 직원 이름 표기 통일 (2026-07-28 시우 · 2026-07-31 웰리 규칙화) ───
// 왜: 담당·처리자를 손으로 타이핑해서 같은 사람이 여러 이름으로 남는다
//   (최준용/최준용M · 백승화/벡승화(오타)/백승화사원 · 윤병현/윤병현AM · 이경연/이경연실장).
//   한 사람이 둘로 갈라지면 순위가 거짓이 되고, 그 순간 아무도 점수를 안 믿는다.
// ▸판정은 여기 한 곳에서만 한다(점수판·보드·알림이 각자 세면 또 갈라진다).
//
// ★2026-07-31 웰리 — 명단 방식을 규칙 방식으로 바꿨다. GM 실측 지적:
//   "알림방 보니까 최준용M 3건, 최준용 3건 이렇게 같은 사람 체크가 안 된다."
//   옛 주석은 "화면이 드롭다운이라 새 값은 안 갈라진다"고 적혀 있었지만 사실이 아니었다 —
//   담당자 칸은 자유 입력이고(회원이 담당이 될 수 있어 GM 이 선택제를 안 쓰기로 함),
//   그래서 명단에 없는 표기는 계속 새로 갈라졌다. 명단 7명으로는 못 막는다.
// 규칙: 공백을 없애고 끝의 직급 표기를 떼서 남는 것이 같으면 같은 사람으로 본다.
//   최준용M · 최준용 · '최준용 M' → 전부 열쇠 '최준용'.
//   회원 이름은 직급이 안 붙으므로 규칙을 그대로 통과한다(회원 담당을 막지 않는다).
// ★2026-08-27 GM 지적 — 강습·지원 쪽 직함이 빠져 있어 '김태엽프로'·'박주혜강사'·'천주희시니어'가
//   직함이 붙은 채 화면에 나왔다(실측: 접수·처리자 고유값 26개 중 3개). 프로·강사·시니어·주니어·
//   코치·반장을 더한다. GM: "앞에 이름 3글자만."
var REG_STAFF_TITLE_RE = /(GM|AM|M|매니저|사원|주임|대리|과장|차장|부장|실장|소장|팀장|프로|강사|시니어|주니어|코치|반장|님)$/;
// 규칙으로 못 잡는 것만 남긴다(오타 등). 명단이 아니라 예외표다 — 늘리지 말 것.
var REG_STAFF_TYPO = { '벡승화': '백승화' };
// 열쇠 → 화면에 보여줄 대표 표기. 없으면 열쇠를 그대로 쓴다.
// ★2026-08-27 GM 확정 — 접수처 화면에는 직함을 붙이지 않고 이름만 보여준다.
//   GM: "접수+완료 이름들이 나오는데 각 직함은 빼고 이름만 일단 하자, 다들 이름을 먼저 넣으니 그게 맞는 것 같아."
//   표를 비우면 _regStaffCanon 이 직함을 벗긴 열쇠를 그대로 돌려준다 — 옛 저장값('박호균과장')도
//   같은 열쇠('박호균')로 모이므로 점수판 집계는 그대로다(정규화는 _regStaffKey 한 곳).
var REG_STAFF_DISPLAY = {};

function _regStaffKey(name) {
  var s = String(name || '').replace(/\s+/g, '');
  if (!s) return '';
  var prev;
  do {                       // '최준용 M님' 처럼 두 겹으로 붙는 경우까지 벗긴다
    prev = s;
    if (s.length > 2) s = s.replace(REG_STAFF_TITLE_RE, '');
  } while (s !== prev);
  return REG_STAFF_TYPO[s] || s;
}

function _regStaffCanon(name) {
  var key = _regStaffKey(name);
  if (!key) return '';
  return REG_STAFF_DISPLAY[key] || key;
}

// 한 칸에 두 사람이 적히는 경우('이경연/ 임정은')를 각각으로 나눈다 — 지금은 그 표기가
// 제3의 사람처럼 잡혀 두 사람 어느 쪽 목록에도 안 뜬다. 2026-07-31 실측 확인.
function _regStaffCanonList(raw) {
  var parts = String(raw || '').split(/[\/,·]|및/);
  var out = [], seen = {};
  parts.forEach(function (p) {
    var c = _regStaffCanon(p);
    if (c && !seen[c]) { seen[c] = 1; out.push(c); }
  });
  return out;
}

// 점수가 붙지 않는 값 — 사람이 아닌 것(단일 정의 · reg_scoreboard 와 reg_dashboard 가 함께 쓴다).
//   GM 지시 2026-08-27 "시설팀 / 회원 이런건 없애줘" — 실측 당시 '시설팀' 1건이 순위표에
//   사람처럼 올라 있었다. 팀·부로 끝나는 이름은 조직이지 사람이 아니라 규칙 한 줄로 막는다
//   (이름을 하나씩 적어 넣으면 다음에 '운영부'·'지원부'가 들어올 때 또 샌다).
//   ▸종전에는 같은 목록이 두 함수 안에 각각 있어 한쪽만 고치면 갈라졌다 — 여기로 모았다(약속 L01).
var REG_NON_STAFF = { '회원': 1, '익명': 1, '자동(점검)': 1, '지원부 점검': 1 };
var REG_NON_STAFF_RE = /(팀|부)$/;
function _regIsNonStaff(who) {
  var s = String(who || '').trim();
  return !!(REG_NON_STAFF[s] || REG_NON_STAFF_RE.test(s));
}

// ─── reg_scoreboard — 접수·처리 점수판 (GM 지시 2026-07-28) ───
// 왜 만들었나: 접수한 사람이 곧 처리까지 떠안는 구조라, 적을수록 손해가 되어 아예 안 적게 된다.
//   GM: "접수받는거 1점 + 처리 완료 1점 등으로 점수 랭킹제로 하는건 어때?"
//   → 적는 행위 자체에 점수를 붙여, 접수를 피할 이유를 없앤다.
// 셈법(단순 유지 — 복잡해지면 아무도 안 믿는다):
//   · 접수 1점 = reporter(접수자)에 직원 이름이 있는 건. '회원'·'자동(점검)'은 사람이 아니라 제외.
//   · 완료 1점 = status='완료' 인 건의 처리자(handler). ▸2026-08-21 GM 확정으로 담당(assignee)
//     대체 계산을 뺐다 — 담당 칸 자체가 없어졌다. 처리자가 비면 점수는 안 붙는다(완료 저장 시
//     처리자를 필수로 받으므로 새 건은 항상 채워진다 · 2026-08-18 GM 지시).
//   한 건이 최대 2점(적은 사람 1 + 끝낸 사람 1). 같은 사람이 둘 다 하면 2점 다 가져간다.
// period: week(이번 주 월요일부터) | month(이번 달 1일부터) | all. 기본 month.
function _regScoreboard(params) {
  var period = String((params && params.period) || 'month').trim().toLowerCase();
  var tz = Session.getScriptTimeZone() || 'Asia/Seoul';
  var now = new Date();
  var since = null;
  if (period === 'week') {
    var dow = now.getDay();                    // 0=일
    var back = (dow === 0) ? 6 : dow - 1;      // 이번 주 월요일까지 되감기
    since = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back);
  } else if (period === 'month') {
    since = new Date(now.getFullYear(), now.getMonth(), 1);
  }
  var sinceStr = since ? Utilities.formatDate(since, tz, 'yyyy-MM-dd') : '';

  var tally = {};   // 이름 → {intake, done}
  var _add = function (who, field) {
    // 한 칸에 두 사람이면 대표(첫 사람)에게만 준다 — 한 건 1점 원칙을 지킨다(2026-07-31 웰리).
    who = (_regStaffCanonList(who)[0] || '');
    if (!who || _regIsNonStaff(who)) return;
    if (!tally[who]) tally[who] = { intake: 0, done: 0 };
    tally[who][field]++;
  };

  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    var rows = _regReadAll(sh, _regHeadersFor(cat.key));
    rows.forEach(function (r) {
      var created = String(r.createdAt || '').slice(0, 10);
      if (sinceStr && created && created < sinceStr) return;
      _add(r.reporter, 'intake');
      if (String(r.status || '') === '완료') {
        _add(r.handler, 'done');
      }
    });
  });

  var board = Object.keys(tally).map(function (name) {
    return { name: name, intake: tally[name].intake,
             done: tally[name].done, total: tally[name].intake + tally[name].done };
  });
  board.sort(function (a, b) {
    if (b.total !== a.total) return b.total - a.total;
    return b.done - a.done;   // 동점이면 '끝낸 것'이 많은 쪽이 위
  });
  // 공동 순위(같은 점수면 같은 등수)
  var rank = 0, prev = null;
  board.forEach(function (x, i) {
    if (x.total !== prev) { rank = i + 1; prev = x.total; }
    x.rank = rank;
  });
  return { ok: true, period: period, since: sinceStr,
           at: Utilities.formatDate(now, tz, 'yyyy-MM-dd HH:mm'), board: board };
}

// ─── reg_dashboard — 현황판 통합 조회 (공개 · 읽기 전용 · 시트 1회 스캔) ───
// 보드가 reg_board·reg_scoreboard·reg_staff_suggest 를 각각(=시트 3중 읽기, GAS 직렬 호출)
//   부르던 것을 한 번에 합친다. ★시트에 아무것도 쓰지 않는다(순수 읽기) — 원본 데이터 불변.
// 반환: { ok, count, board:[…reg_board 동일], scoreboard:{…reg_scoreboard 동일}, staffNames:[…reg_staff_suggest 동일] }.
// 판정은 전부 기존 단일 함수(_regMask·_regComputeSla·_regStaffCanonList) 재사용 — 규칙이 두 벌이 되지 않게(약속 L01).
// 캐시: 필터 없는 기본 호출 60초(반복 로드 즉답). pv(사진 원본) 여부 + period 로 키 분리. 쓰기 시 _regBoardCacheClear_ 가 무효화.
function _regDashboard(params) {
  var src = params || {};
  var staffPhoto = String(src.pv || '') === REG_STAFF_PHOTO_KEY;
  var period = String(src.period || 'all').trim().toLowerCase();
  var cacheKey = 'reg_dash_v1' + (staffPhoto ? '_staff' : '') + '_' + period;

  try {
    var hit = CacheService.getScriptCache().get(cacheKey);
    if (hit) return _vJson(JSON.parse(hit));
  } catch (e) {}

  // ── 전 카테고리 시트를 딱 1회만 읽는다(읽기 전용) ──
  var rows = [];
  REG_CATEGORIES.forEach(function (cat) {
    var sh;
    try { sh = _regGetSheet(cat.key); } catch (e) { return; }
    _regReadAll(sh, _regHeadersFor(cat.key)).forEach(function (r) { rows.push(r); });
  });
  // 처리자 통일값 부착 — 판정은 _regStaffCanonList 단일 재사용(reg_list 와 동일)
  rows.forEach(function (r) {
    r.handlerCanon = _regStaffCanonList(r.handler);
  });
  rows.sort(function (a, b) { return String(b.createdAt || '') > String(a.createdAt || '') ? 1 : -1; });

  // ── (1) board: 마스킹 + SLA — reg_board 와 동일 파이프 재사용 ──
  var board = rows.map(function (r) { return _regComputeSla(_regMask(r, staffPhoto)); });

  // ── (2) scoreboard: 같은 rows 로 집계 — reg_scoreboard 와 동일 규칙(판정=_regStaffCanonList 재사용) ──
  var tz = Session.getScriptTimeZone() || 'Asia/Seoul';
  var now = new Date();
  var since = null;
  if (period === 'week') {
    var dow = now.getDay();
    var back = (dow === 0) ? 6 : dow - 1;
    since = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back);
  } else if (period === 'month') {
    since = new Date(now.getFullYear(), now.getMonth(), 1);
  }
  var sinceStr = since ? Utilities.formatDate(since, tz, 'yyyy-MM-dd') : '';
  var tally = {};
  var _add = function (who, field) {
    who = (_regStaffCanonList(who)[0] || '');
    if (!who || _regIsNonStaff(who)) return;
    if (!tally[who]) tally[who] = { intake: 0, done: 0 };
    tally[who][field]++;
  };
  rows.forEach(function (r) {
    var created = String(r.createdAt || '').slice(0, 10);
    if (sinceStr && created && created < sinceStr) return;
    _add(r.reporter, 'intake');
    if (String(r.status || '') === '완료') _add(r.handler, 'done');
  });
  var sbBoard = Object.keys(tally).map(function (name) {
    return { name: name, intake: tally[name].intake, done: tally[name].done, total: tally[name].intake + tally[name].done };
  });
  sbBoard.sort(function (a, b) { return b.total !== a.total ? b.total - a.total : b.done - a.done; });
  var rank = 0, prev = null;
  sbBoard.forEach(function (x, i) { if (x.total !== prev) { rank = i + 1; prev = x.total; } x.rank = rank; });
  var scoreboard = { ok: true, period: period, since: sinceStr,
    at: Utilities.formatDate(now, tz, 'yyyy-MM-dd HH:mm'), board: sbBoard };

  // ── (3) 처리자 제안: 같은 rows 로 빈도순 — reg_staff_suggest 와 동일 ──
  var scount = {};
  rows.forEach(function (r) {
    _regStaffCanonList(r.handler).forEach(function (n) {
      scount[n] = (scount[n] || 0) + 1;
    });
  });
  var staffNames = Object.keys(scount).sort(function (a, b) { return scount[b] - scount[a]; }).slice(0, 40);

  var out = { ok: true, count: board.length, board: board, scoreboard: scoreboard, staffNames: staffNames };
  try { CacheService.getScriptCache().put(cacheKey, JSON.stringify(out), 60); } catch (e) {}
  return _vJson(out);
}

// ─── reg_update — 종합 접수처 갱신 (GATED) ───
// reg_board 공개·직원(사진) 두 캐시 + reg_dashboard 캐시 동시 무효화 — 쓰기 액션(submit/update/delete/renumber 등)마다 호출.
// 회원 셀프 조회 캐시 키 — 전화+이름 한 쌍당 하나(남의 결과가 섞이지 않게 지문으로 만든다)
function _regLookupCacheKey_(phone, name) {
  return 'reg_lookup_v1_' + _vFp_(phone + '|' + name);
}

// 쓰기 직후 회원 조회 캐시도 지운다 — 방금 접수한 건이 45초 동안 안 보이는 일을 막는다.
function _regLookupCacheClearFor_(phone, name) {
  try {
    var pp = String(phone || '').replace(/[^0-9]/g, '');
    var nn = String(name || '').replace(/\s/g, '');
    if (!pp || !nn) return;
    CacheService.getScriptCache().remove(_regLookupCacheKey_(pp, nn));
  } catch (e) {}
}

function _regBoardCacheClear_() {
  try {
    var c = CacheService.getScriptCache();
    c.remove('reg_board_v1'); c.remove('reg_board_staff_v1');
    // reg_dashboard 캐시(공개/사진 × all/week/month) 함께 무효화 — 쓰기 직후 최신 반영.
    c.removeAll(['reg_dash_v1_all','reg_dash_v1_week','reg_dash_v1_month',
                 'reg_dash_v1_staff_all','reg_dash_v1_staff_week','reg_dash_v1_staff_month']);
  } catch (e) {}
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

    // 현재 행 읽기 — 열 폭·열 위치 모두 '시트 실제 헤더' 기준(2026-07-28 시우, _regKeyCols).
    var width = Math.max(sh.getLastColumn(), headers.length);
    var existing = sh.getRange(rowNum, 1, 1, width).getValues()[0];
    var keyCols = _regKeyCols(sh, headers);
    var _idx = function (key) {
      return (key in keyCols) ? keyCols[key] : -1;
    };

    var si = _idx('status');
    var curStatus = si >= 0 ? String(existing[si] || '') : '';
    var memo = body.memo !== undefined ? body.memo : undefined;

    // 답변(처리메모) 자동 상태 전환 — 규칙은 _regEffectiveStatusOnMemo 단일 정의(위 참고).
    var effStatus = _regEffectiveStatusOnMemo(curStatus, newStatus, memo);
    if (effStatus && si >= 0) existing[si] = effStatus;

    if (memo !== undefined) {
      var mi = _idx('memo');
      if (mi >= 0) existing[mi] = String(memo);
    }
    // 처리자 (2026-07-28 시우) — 화면은 예전부터 이 값을 보내고 있었는데 서버가 안 받아
    //   저장되지 않았다. 시트엔 '처리자' 칸이 이미 있었으니 이제 그 칸에 들어간다.
    var handler = body.handler !== undefined ? body.handler : undefined;
    if (handler !== undefined) {
      var hi = _idx('handler');
      if (hi >= 0) existing[hi] = String(handler);
    }
    // 접수자 — 점수판의 '접수 1점'이 나오는 칸. 화면에서 나중에 채우거나 고칠 수 있어야 한다
    //   (지금 쌓여 있는 옛 접수건은 이 칸이 비어 있어 접수 점수가 0이다). 2026-07-28 시우.
    var reporter = body.reporter !== undefined ? body.reporter : undefined;
    if (reporter !== undefined) {
      var ri = _idx('reporter');
      if (ri >= 0) existing[ri] = String(reporter);
    }
    // 회원 안내 — 현황판 '회원 안내' 칸 입력 → 회원 셀프 조회 노출. 2026-08-03 복구.
    var memberReply = body.memberReply !== undefined ? body.memberReply : undefined;
    if (memberReply !== undefined) {
      var mri = _idx('memberReply');
      if (mri >= 0) existing[mri] = String(memberReply);
    }
    // 접수자 이름 — 이름 표기 통합용(직함 붙은 표기로 일괄 수정 시). 2026-08-15 시우.
    // 병합 손실(daeb4512b 2026-08-18) 복원 — 2026-08-20 시토.
    var nameVal = body.name !== undefined ? body.name : undefined;
    if (nameVal !== undefined) {
      var nmi = _idx('name');
      if (nmi >= 0) existing[nmi] = String(nameVal);
    }
    // 대상 직원·강사 칸 — praise/voice 카테고리에서 쓰인다. 2026-08-15 시우.
    var targetStaffVal = body.targetStaff !== undefined ? body.targetStaff : undefined;
    if (targetStaffVal !== undefined) {
      var tsi = _idx('targetStaff');
      if (tsi >= 0) existing[tsi] = String(targetStaffVal);
    }
    // 부서 재배정 — 수동 배정 또는 부서 체계 변경 시. 2026-08-15 시우.
    var deptVal = body.dept !== undefined ? body.dept : undefined;
    if (deptVal !== undefined) {
      var dpi = _idx('dept');
      if (dpi >= 0) existing[dpi] = String(deptVal);
    }
    // 완료로 전환되는 순간, 회원 안내가 비어 있으면 카테고리 문구를 채운다(2026-08-18 GM 지시 —
    //   105건 중 3건만 채워져 사실상 안 쓰이던 문제). 사람이 이미 쓴 값은 절대 덮지 않는다.
    if (effStatus === '완료') {
      var mriDone = _idx('memberReply');
      if (mriDone >= 0 && _regShouldDraftMemo(existing[mriDone])) {
        var mrDraft = _regMemberReplyDraft(cat.key);
        if (mrDraft) existing[mriDone] = mrDraft;
      }
    }

    // 읽은 폭 그대로 되쓴다 — headers.length 로 쓰면 시트가 더 넓을 때 뒤 칸이 잘린다.
    sh.getRange(rowNum, 1, 1, existing.length).setValues([existing]);
    if (effStatus) _regApplyStatusColor(sh, rowNum, effStatus, headers);

    var statusIdx = _idx('status');
    _regBoardCacheClear_();
    return _vJson({
      ok: true, id: id,
      status:   statusIdx  >= 0 ? existing[statusIdx]  : '',
      message: '접수건이 갱신되었습니다.'
    });
  }

  return _vJson({ ok: false, error: '해당 접수ID를 찾을 수 없습니다: ' + id });
}

// 접수 삭제 비밀번호 기본값 (GM 지정 2026-07-31). ScriptProperties 의 REG_DELETE_PIN 이 있으면 그쪽이 이긴다.
var REG_DELETE_PIN_DEFAULT = '1200';

// ─── reg_delete — 접수ID로 행 정밀 삭제 (GATED·내부) ───
// category 지정 시 해당 시트만, 없으면 전 reg 시트 순회하며 첫 일치 행 삭제. 배포검증 더미 청소용.
// 안전: id 정확매칭(_vFindRow, col A) 1행만 삭제. id 없으면 거부. GATED(공개 액션 목록 미포함).
// ★2026-07-31(GM 지정) — 현황 화면에 삭제 버튼이 생기면서 비밀번호 확인을 **서버에서도** 한다.
//   화면에서만 물으면 액션 이름을 아는 누구나 그냥 부를 수 있다(TOKEN_ENFORCE 는 기본 OFF).
//   pin 은 ScriptProperties 의 REG_DELETE_PIN 을 우선 쓰고, 없으면 GM 이 정한 기본값을 쓴다
//   — 나중에 값을 바꿀 때 코드 재배포 없이 속성만 고치면 되게.
function _regDelete(body) {
  var _pinWant = _vAccessProp_('REG_DELETE_PIN') || REG_DELETE_PIN_DEFAULT;
  var _pinGot = String((body && (body.pin || body.pw)) || '').trim();
  if (_pinGot !== String(_pinWant)) {
    return _vJson({ ok: false, error: '삭제 비밀번호가 올바르지 않습니다.', code: 'BAD_PIN' });
  }
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

// ─── hold_intake_test_rows — 휴회접수 탭의 테스트 행 조회·삭제 (GATED) ───
// 2026-07-27 시포→시우 인계(배146). GM 지시로 반려된 테스트 접수 2건을 시트에서 지운다.
// ★행번호로 지우지 않는다. INC-020(행 인덱스 삭제로 실고객 오삭제) 재발 방지 —
//   '성함' 과 '연락처' 두 칸을 동시에 대조해 찾은 행만 지운다.
// ★안전장치 3겹: ①이름이 '[테스트]' 로 시작 + 연락처가 010-0000- 로 시작하는 행만 후보
//   ②confirm !== 'yes' 면 지우지 않고 후보 목록만 반환(기본이 미리보기)
//   ③아래에서 위로 지운다(중간 삭제로 인덱스가 밀려 엉뚱한 행을 지우는 것 방지).
var HOLD_INTAKE_SHEET = '휴회접수';

// ─── hold_intake_stats — 휴회접수 집계 (2026-07-31 GM 지시 · 월간운영계획 종합접수처 칸용) ───
// GM: "월간운영계획에 종합접수처 칸에 휴회도 넣어줄 수 있지?"
// ▸건수만 돌려준다 — 성함·연락처(PII)는 절대 싣지 않는다. 월간운영계획은 집계만 쓴다.
// ▸테스트 행([테스트] + 010-0000-)은 빼고 센다(가짜 숫자 방지).
// ▸상태 칸이 없으면 상태 분해 없이 총건수만 — 없는 칸을 지어내지 않는다(약속 L05).
function _holdIntakeStats() {
  var ss = _vGetSpreadsheet();
  var sh = ss.getSheetByName(HOLD_INTAKE_SHEET);
  if (!sh) return _vJson({ ok: false, error: HOLD_INTAKE_SHEET + ' 탭이 없습니다' });
  var last = sh.getLastRow();
  if (last < 2) return _vJson({ ok: true, total: 0, byStatus: {}, thisMonth: 0 });

  var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(String);
  var iName = headers.indexOf('성함');
  var iTel = headers.indexOf('연락처');
  var iStat = headers.indexOf('처리상태');
  var iWhen = -1;
  for (var h = 0; h < headers.length; h++) {
    if (/타임스탬프|접수일|신청일/.test(headers[h])) { iWhen = h; break; }
  }
  var data = sh.getRange(2, 1, last - 1, headers.length).getValues();
  var tz = Session.getScriptTimeZone() || 'Asia/Seoul';
  var ym = Utilities.formatDate(new Date(), tz, 'yyyy-MM');
  var total = 0, thisMonth = 0, byStatus = {};
  for (var r = 0; r < data.length; r++) {
    var nm = iName >= 0 ? String(data[r][iName] || '').trim() : '';
    var tel = iTel >= 0 ? String(data[r][iTel] || '').trim() : '';
    if (nm.indexOf('[테스트]') === 0 && tel.indexOf('010-0000-') === 0) continue;
    if (!nm && !tel) continue;                    // 빈 행 제외
    total++;
    if (iStat >= 0) {
      var st = String(data[r][iStat] || '').trim() || '접수';
      byStatus[st] = (byStatus[st] || 0) + 1;
    }
    if (iWhen >= 0) {
      var w = data[r][iWhen];
      var ws = (w instanceof Date) ? Utilities.formatDate(w, tz, 'yyyy-MM') : String(w || '').slice(0, 7).replace('.', '-');
      if (ws === ym) thisMonth++;
    }
  }
  return _vJson({ ok: true, total: total, byStatus: byStatus, thisMonth: thisMonth,
                  hasStatus: iStat >= 0, hasDate: iWhen >= 0, month: ym });
}
// ─── hold_done_keys — 휴회접수 탭에서 '완료' 처리된 행의 매칭키(해시) 반환 (읽기 전용·PII 없음) ───
function _holdDoneKeys() {
  var ss = _vGetSpreadsheet();
  var sh = ss.getSheetByName(HOLD_INTAKE_SHEET);   // '휴회접수'
  if (!sh) return _vJson({ ok:false, error: HOLD_INTAKE_SHEET + ' 탭 없음' });
  var last = sh.getLastRow();
  if (last < 2) return _vJson({ ok:true, keys:[], count:0 });
  var headers = sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0].map(String);
  function col(cands){ for(var i=0;i<headers.length;i++){ for(var j=0;j<cands.length;j++){ if(headers[i].indexOf(cands[j])>=0) return i; } } return -1; }
  var iName=col(['성함','이름']), iTel=col(['연락처']), iStart=col(['휴회시작일','시작']),
      iStat=col(['상태']), iDone=col(['처리일시']), iMemo=col(['처리메모','메모']);
  var data = sh.getRange(2,1,last-1,headers.length).getValues();
  var tz = 'Asia/Seoul';
  function ymd(v){ if (v instanceof Date) return Utilities.formatDate(v,tz,'yyyyMMdd'); return String(v==null?'':v).replace(/\D/g,'').slice(0,8); }
  var keys = [];
  for (var r=0; r<data.length; r++){
    var row = data[r];
    var memo   = iMemo>=0 ? String(row[iMemo]||'') : '';
    var stat   = iStat>=0 ? String(row[iStat]||'') : '';
    var doneAt = iDone>=0 ? String(row[iDone]||'').trim() : '';
    var done = memo.indexOf('휴회완료') >= 0;   // K열 '처리메모' = '휴회완료' 만 완료로 인정(빈칸·'휴회 X'는 유지). 2026-08-16.
    if (!done) continue;
    var ph  = iTel>=0   ? String(row[iTel]||'').replace(/\D/g,'') : '';
    var st8 = iStart>=0 ? ymd(row[iStart]) : '';
    var nm  = iName>=0  ? String(row[iName]||'').replace(/\s/g,'') : '';
    keys.push(_vFp_(ph + '|' + st8 + '|' + nm));
  }
  return _vJson({ ok:true, keys:keys, count:keys.length });
}

// ─── hold_complete — 휴회접수 특정 행을 완료 처리(처리메모=휴회완료·처리일시=오늘) ───
function _holdComplete(body){
  var phone = String((body&&body.phone)||'').replace(/\D/g,'');
  var start = String((body&&body.start)||'').replace(/\D/g,'').slice(0,8);
  var name  = String((body&&body.name)||'').replace(/\s/g,'');
  if(!phone && !name) return _vJson({ ok:false, error:'식별정보 부족' });
  var ss=_vGetSpreadsheet(); var sh=ss.getSheetByName(HOLD_INTAKE_SHEET);
  if(!sh) return _vJson({ ok:false, error:HOLD_INTAKE_SHEET+' 탭 없음' });
  var last=sh.getLastRow(); if(last<2) return _vJson({ ok:false, error:'데이터 없음' });
  var headers=sh.getRange(1,1,1,sh.getLastColumn()).getValues()[0].map(String);
  function col(cands){ for(var i=0;i<headers.length;i++){ for(var j=0;j<cands.length;j++){ if(headers[i].indexOf(cands[j])>=0) return i; } } return -1; }
  var iName=col(['성함','이름']),iTel=col(['연락처']),iStart=col(['휴회시작일','시작']),iDone=col(['처리일시']),iMemo=col(['처리메모','메모']);
  var tz='Asia/Seoul';
  function ymd(v){ if(v instanceof Date) return Utilities.formatDate(v,tz,'yyyyMMdd'); return String(v==null?'':v).replace(/\D/g,'').slice(0,8); }
  var data=sh.getRange(2,1,last-1,headers.length).getValues();
  for(var r=0;r<data.length;r++){
    var row=data[r];
    var ph=iTel>=0?String(row[iTel]||'').replace(/\D/g,''):'';
    var st=iStart>=0?ymd(row[iStart]):'';
    var nm=iName>=0?String(row[iName]||'').replace(/\s/g,''):'';
    if(ph===phone && st===start && nm===name){
      var rowNum=r+2;
      if(iMemo>=0) sh.getRange(rowNum,iMemo+1).setValue('휴회완료');
      if(iDone>=0 && !String(row[iDone]||'').trim()) sh.getRange(rowNum,iDone+1).setValue(Utilities.formatDate(new Date(),tz,'yyyy-MM-dd'));
      return _vJson({ ok:true, matched:true });
    }
  }
  return _vJson({ ok:false, error:'일치 행 없음' });
}

function _holdIntakeTestRows(body) {
  var ss = _vGetSpreadsheet();
  var sh = ss.getSheetByName(HOLD_INTAKE_SHEET);
  if (!sh) return _vJson({ ok: false, error: HOLD_INTAKE_SHEET + ' 탭이 없습니다' });
  var last = sh.getLastRow();
  if (last < 2) return _vJson({ ok: true, found: [], deleted: 0, message: '데이터 행 없음' });

  var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(String);
  var iName = headers.indexOf('성함');
  var iTel  = headers.indexOf('연락처');
  if (iName < 0 || iTel < 0) {
    return _vJson({ ok: false, error: "'성함'·'연락처' 칸을 찾지 못했습니다 — 헤더: " + headers.join(',') });
  }

  var data = sh.getRange(2, 1, last - 1, headers.length).getValues();
  var found = [];
  for (var r = 0; r < data.length; r++) {
    var nm = String(data[r][iName] || '').trim();
    var tel = String(data[r][iTel] || '').trim();
    if (nm.indexOf('[테스트]') === 0 && tel.indexOf('010-0000-') === 0) {
      found.push({ row: r + 2, 성함: nm, 연락처: tel });
    }
  }
  if (String((body && body.confirm) || '') !== 'yes') {
    return _vJson({ ok: true, dryRun: true, found: found,
                    message: '미리보기입니다. 실제 삭제는 confirm="yes" 를 함께 보내세요.' });
  }
  for (var k = found.length - 1; k >= 0; k--) sh.deleteRow(found[k].row);
  _regBoardCacheClear_();
  return _vJson({ ok: true, dryRun: false, deleted: found.length, found: found });
}

// ─── rename_legacy_resources — 구글 실물 자원(드라이브 폴더·시트 탭) 이름의 VOC 제거 (GATED·일회성) ───
// 2026-07-27 GM 지시 '연결된 부분도 다 수정'. 코드 상수만 바꾸면 실물과 어긋나므로 실물을 여기서 바꾼다.
// 안전: ①드라이브 폴더는 ID 로 잡아 rename 한다 — 폴더 ID·그 안 파일 ID·공개 사진 URL 전부 불변이라
//   기존 접수 사진 링크가 깨지지 않는다. ②시트 탭은 있을 때만 바꾼다(없으면 건드리지 않고 보고만).
// 멱등: 이미 새 이름이면 아무것도 안 한다. 두 번 돌려도 결과 같음.
function _renameLegacyResources() {
  var done = [];

  // 1) 접수 사진 Drive 폴더
  try {
    var folder = _vGetPhotoFolder();   // ID 우선 → 이름 폴백(새→옛). 여기서 이미 올바른 폴더를 잡는다.
    var curName = folder.getName();
    if (curName === RECEPTION_PHOTO_FOLDER_NAME) {
      done.push('드라이브 폴더: 이미 ' + RECEPTION_PHOTO_FOLDER_NAME + ' (변경 없음)');
    } else {
      folder.setName(RECEPTION_PHOTO_FOLDER_NAME);
      done.push('드라이브 폴더: ' + curName + ' → ' + RECEPTION_PHOTO_FOLDER_NAME +
                ' (폴더 ID ' + folder.getId() + ' 불변 · 사진 링크 영향 없음)');
    }
  } catch (e) {
    done.push('드라이브 폴더: 실패 — ' + e);
  }

  // 2) 레거시 접수 원장 시트 탭 (있을 때만)
  try {
    var ss = _vGetSpreadsheet();
    var old = ss.getSheetByName('접수 VOC');
    if (!old) {
      done.push("시트 탭: '접수 VOC' 없음 — 바꿀 대상 없음(현재 탭 " + ss.getSheets().length + '개)');
    } else if (ss.getSheetByName(LEGACY_RECEPTION_SHEET)) {
      done.push("시트 탭: '" + LEGACY_RECEPTION_SHEET + "' 가 이미 있어 자동 병합하지 않음 — 사람이 확인 필요");
    } else {
      old.setName(LEGACY_RECEPTION_SHEET);
      done.push("시트 탭: '접수 VOC' → '" + LEGACY_RECEPTION_SHEET + "'");
    }
  } catch (e) {
    done.push('시트 탭: 실패 — ' + e);
  }

  return _vJson({ ok: true, done: done });
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

// ★ Q~V 추가칸 (2026-08-16 에 시트에 손으로 붙인 6칸). 일부러 LF_HEADERS 밖에 둔다 — 두 가지 이유:
//   ① LF_HEADERS 는 _lfSubmit·_lfHandover 가 위치(index) 기준으로 읽고 쓰는 목록이다. 여기에 칸을
//      더하면 물리 컬럼 순서와 어긋나는 순간 남의 칸을 덮어쓴다.
//   ② 공개 응답(lf_gallery·lf_disposal)은 LF_HEADERS 만 읽는다 → 내부메모·주인연락처가 자동으로
//      공개 경로에서 빠진다. 목록을 분리해 두는 것 자체가 노출 차단이다.
//   읽기·쓰기 모두 '헤더 이름'으로 칸을 찾는다(공백 무시) — 컬럼을 옮기거나 지워도 안전.
var LF_EXTRA_HEADERS = [
  { key: 'ownerName',     label: '주인성함'     },
  { key: 'ownerContact',  label: '주인연락처'   },
  { key: 'receiverPhone', label: '수령자연락처' },
  { key: 'keepLoc',       label: '보관위치'     },
  { key: 'providedDate',  label: '제공일'       },
  { key: 'memo',          label: '내부메모'     }
];

// 시트 1행에서 Q~V 칸의 0-based 위치를 이름으로 찾는다. 시트에 없는 칸은 결과에서 빠진다.
function _lfExtraCols_(sh) {
  var out = {};
  try {
    var hdr = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
                .map(function (x) { return String(x).replace(/\s/g, ''); });
    LF_EXTRA_HEADERS.forEach(function (h) {
      var ci = hdr.indexOf(h.label);
      if (ci >= 0) out[h.key] = ci;
    });
  } catch (e) {}
  return out;
}

// 한 행의 Q~V 칸을 이름으로 찍는다(위치 기반 아님). 빈 값은 건드리지 않는다 — 기존 값 보존.
function _lfSetByLabel_(sh, rowNum, values) {
  try {
    var cols = _lfExtraCols_(sh);
    Object.keys(values).forEach(function (k) {
      var v = values[k];
      if (v == null || String(v) === '') return;
      if (cols[k] === undefined) return;
      sh.getRange(rowNum, cols[k] + 1).setValue(v);
    });
  } catch (e) {}
}

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
  // ★ 접수 시점에 채워지는 Q~V 칸 = 보관위치·내부메모 두 개 (실무진 신고 FB260820-143647).
  //   나머지 4칸(주인성함·주인연락처·수령자연락처·제공일)은 수령할 때 정해지므로 _lfHandover 가 채운다.
  _lfSetByLabel_(sh, newRow, {
    keepLoc: String(body.storageLoc || body.keepLoc || '').trim(),
    memo:    String(body.memo || '').trim()
  });

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
  // ★ Q~V 추가칸을 붙여 보낸다 (실무진 신고 FB260820-143647 · 2026-08-24 시우).
  //   화면(종합접수처_현황.html 960~962행)은 keepLoc·memo·ownerName·ownerContact 를 이미 그리고
  //   있었는데 lf_list 가 그 칸을 실어 보내지 않아 계속 빈 상태로 보였다. 화면이 아니라 여기가 원인이다.
  //   _regReadAll 과 같은 범위(2행~마지막)를 같은 순서로 읽으므로 행 인덱스가 그대로 맞는다.
  var _xCols = _lfExtraCols_(sh);
  var _xKeys = Object.keys(_xCols);
  if (_xKeys.length) {
    var _lastRow = sh.getLastRow();
    if (_lastRow >= 2) {
      var _grid = sh.getRange(2, 1, _lastRow - 1, sh.getLastColumn()).getValues();
      for (var _i = 0; _i < rows.length && _i < _grid.length; _i++) {
        for (var _k = 0; _k < _xKeys.length; _k++) {
          var _key = _xKeys[_k], _v = _grid[_i][_xCols[_key]];
          if (_v instanceof Date) _v = Utilities.formatDate(_v, 'Asia/Seoul', 'yyyy-MM-dd');
          rows[_i][_key] = _v;
        }
      }
    }
  }
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
  // Q~V 추가칸(주인성함·주인연락처·수령자연락처·보관위치·제공일·내부메모) — 헤더명으로 찾아 저장(positional 아님·컬럼순서 무관). 2026-08-16.
  // ponytail: _lfSetByLabel_ 과 같은 일을 하는 블록이다. 2026-08-24 에 합치려 했으나
  //   truncation-guard 가 "최근 7일 안에 들어온 줄 삭제"로 잡아 되돌렸다(가드 우회 안 함).
  //   2026-08-23 이후 아무 때나 이 블록을 _lfSetByLabel_(sh, rowNum, {...}) 호출로 바꾸면 된다.
  try {
    var _hdr = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function(x){ return String(x).replace(/\s/g,''); });
    var _setLF = function(name, val){ if(val==null || String(val)==='') return; var ci=_hdr.indexOf(name); if(ci>=0) sh.getRange(rowNum, ci+1).setValue(val); };
    _setLF('주인성함',     String(body.ownerName    || '').trim());
    _setLF('주인연락처',   String(body.ownerPhone   || '').trim());
    _setLF('수령자연락처', String(body.receiverPhone || '').trim());
    _setLF('보관위치',     String(body.storageLoc   || '').trim());
    _setLF('제공일',       String(body.providedDate || '').trim());
    _setLF('내부메모',     String(body.memo         || '').trim());
  } catch(e) {}

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
  reg_dashboard: true,  // 현황판 통합 조회 — reg_board 와 동일 마스킹(이름·연락처 가림), 읽기 전용, 토큰 면제
  hold_done_keys: true,   // 완료 매칭키(해시)만 — PII 없음, 읽기 전용. 2026-08-16.
  reg_update:  true,  // 상태·담당·메모 갱신 — PII 미포함, 토큰 면제
  reg_lookup:  true,  // 회원 셀프 조회 — 전화+이름 2차확인·회원안전 필드만·rate-limit, 토큰 면제
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
    // 어느 방으로 나가는지 — 발신 등록부의 room 값이 실제와 맞는지 대조하려면 이게 필요하다.
    // 2026-07-31 실측: 등록부에는 '핵심멤버방'(2026-06-24 3분류로 사라진 옛 이름)이 적혀 있는데
    // 실제 목적지를 확인할 방법이 없어 대조가 불가능했다. chat_id 는 방 식별자일 뿐 개인정보가
    // 아니므로 그대로 노출한다(그룹 chat_id 는 이미 저장소 여러 곳에 공개돼 있다).
    chatId:           String(_vprop('TELEGRAM_CHAT_ID') || ''),
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
  // 구글 실물 자원(드라이브 폴더·시트 탭) 이름의 VOC 제거 · 일회성 · GATED. 2026-07-27 시우(GM 지시).
  if (action === 'rename_legacy_resources') return _renameLegacyResources();
  // 휴회접수 탭 테스트 행 조회·삭제(키 대조) · GATED. 기본은 미리보기, confirm='yes' 일 때만 삭제. 2026-07-27 시우(배146).
  if (action === 'hold_intake_test_rows') return _holdIntakeTestRows(body);

  // ── 종합 접수처 액션 ──
  if (action === 'reg_submit') return _regSubmit(body);
  if (action === 'reg_list')   return _regList(params || body);
  if (action === 'reg_lookup') return _regLookup(params || body);  // 회원 셀프 조회(공개·전화+이름·회원안전 필드만). 2026-08-03 복구.
  if (action === 'reg_dashboard') return _regDashboard(params || body);  // 현황판 통합 조회(공개·읽기전용·시트 1회 스캔). 2026-08-05.
  // 「전달문구」 초안 자체점검(read-only·시트 미접촉) — 배포 후 라이브 확인용. 2026-08-05 시토.
  if (action === 'reg_draft_selftest') return _vJson(_regDraftMemoSelfCheck());
  if (action === 'reg_staff_suggest') return _regStaffSuggest();  // 담당자 입력 자동완성 제안(공개 read·PII 없음). 2026-07-31 웰리.
  if (action === 'hold_intake_stats') return _holdIntakeStats();  // 휴회접수 건수 집계(공개 read·PII 없음). 2026-07-31 웰리.
  if (action === 'hold_done_keys') return _holdDoneKeys();   // 휴회 완료행 매칭키(읽기·PII없음). 2026-08-16.
  if (action === 'hold_complete') return _holdComplete(body);   // 휴회 완료 버튼 처리(쓰기). 2026-08-16.
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
  if (action === 'reg_scoreboard') return _vJson(_regScoreboard(params || body));  // 접수·처리 점수판(공개 read·PII 없음). 2026-07-28 시우.
  // 시트 헤더 행 그대로 보기(읽기 전용·PII 없음) — 칸을 늘릴 때 '지금 실제로 뭐가 있는지'를
  // 추측하지 않고 눈으로 확인하려고 둔다. 2026-07-28 시우(중복 헤더 사고 방지).
  if (action === 'reg_headers') {
    var _hOut = {};
    REG_CATEGORIES.forEach(function (c) {
      try {
        var s = _regGetSheet(c.key);
        var lc = s.getLastColumn();
        _hOut[c.label] = lc > 0 ? s.getRange(1, 1, 1, lc).getValues()[0].map(String) : [];
      } catch (e) { _hOut[c.label] = ['ERR: ' + e]; }
    });
    return _vJson({ ok: true, headers: _hOut });
  }
  if (action === 'reg_update') return _regUpdate(body);
  if (action === 'reg_delete') return _regDelete(body);   // 접수ID로 행 정밀 삭제(배포검증 더미 청소용·GATED). 2026-06-20 시우.
  if (action === 'reg_renumber') return _regRenumber(body); // 전체 통합 순번 RECEPTION-1.. 재부여(일회성·멱등·GATED). 2026-06-30 시토.
  if (action === 'reg_sort') return _vJson({ ok: true, sorted: _regSortAllDesc() }); // 전 접수시트 접수일시 desc 정렬(멱등·GATED). 이후 reg_submit이 자동 유지. 2026-07-15 시우.
  // SLA 초과 전환 알림 체크(GATED). dryRun 파라미터 없으면 기본 dry-run(발송·상태저장 없음) — 실제 발송은 dryRun=0/false 명시 호출만. 2026-07-27 시우(배163).
  if (action === 'reg_sla_check') {
    var _slaP = params || body || {};
    var _slaDryRunFlag = String(_slaP.dryRun || '');
    var _slaDry = !(_slaDryRunFlag === '0' || _slaDryRunFlag.toLowerCase() === 'false');
    return _vJson(_regNotifySlaOverdue(_slaDry));
  }
  // SLA 초과 알림 30분 트리거 설치(멱등·일회성·GATED). 배포 직후 1회만 호출. 2026-07-27 시토.
  if (action === 'reg_install_sla_trigger') return _vJson({ ok: true, result: installReceptionSlaTrigger() });
  // SLA 30분 실시간 알림 끄기(GATED · GM 지시 2026-08-12). 되돌리기 = 위 install 한 번.
  if (action === 'reg_uninstall_sla_trigger') return _vJson({ ok: true, result: uninstallReceptionSlaTrigger() });

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
