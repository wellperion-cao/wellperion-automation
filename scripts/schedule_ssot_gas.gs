// 웰페리온 전사 일정 SSOT — 자동저장 백엔드 (Apps Script, standalone)
// #860 코드-ready. 배포·발효는 GM go 이후(clasp push/deploy 금지 — 이 파일은 커밋만).
//
// 저장소: ScriptProperties 단일 JSON blob('SCHEDULE_SSOT' 키). 항목 15~30개라 시트 불필요.
// 프론트(전사_일정.html)는 SCHEDULE_GAS_URL이 설정돼 있으면 이 백엔드를 SSOT로 쓰고,
// 없거나 실패하면 github seed(schedule_ssot.json)로 폴백한다.
//
// action 규약(프로젝트 GAS 관례 — Code.gs getBoard/saveBoard와 동일 패턴):
//   GET  ?action=load_schedule           → { ok:true, data: {...} | null }
//   POST { action:'save_schedule', data:{...} } → { ok:true, count:N } | { ok:false, error }

var SCHEDULE_PROP = 'SCHEDULE_SSOT';
var SCHEDULE_BAK_PROP = 'SCHEDULE_SSOT_BAK';

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) || '';
  if (action === 'load_schedule') return loadSchedule_();
  return jsonRes_({ ok: true, msg: '웰페리온 전사 일정 SSOT 백엔드 정상 동작 중' });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var body = JSON.parse(e.postData.contents);
    var action = body.action || '';
    if (action === 'save_schedule') return saveSchedule_(body);
    return jsonRes_({ ok: false, error: '알 수 없는 action: ' + action });
  } catch (err) {
    return jsonRes_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

// ─── 조회: 저장된 전체 schedule JSON 반환. 저장본 없으면 data:null(프론트가 github seed 폴백) ───
function loadSchedule_() {
  var raw = PropertiesService.getScriptProperties().getProperty(SCHEDULE_PROP);
  var data = null;
  if (raw) {
    try { data = JSON.parse(raw); } catch (err) { data = null; }
  }
  return jsonRes_({ ok: true, data: data });
}

// ─── 저장: 전체 schedule JSON 덮어쓰기. items 배열 없으면 거부(파괴적 저장 방지) ───
// 저장 직전 기존 값을 SCHEDULE_SSOT_BAK에 1개 백업(롤백 안전망).
function saveSchedule_(body) {
  var data = body.data;
  if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
    return jsonRes_({ ok: false, error: 'items 배열이 없는 JSON은 저장할 수 없습니다.' });
  }
  var props = PropertiesService.getScriptProperties();
  var prev = props.getProperty(SCHEDULE_PROP);
  if (prev) props.setProperty(SCHEDULE_BAK_PROP, prev);
  props.setProperty(SCHEDULE_PROP, JSON.stringify(data));
  return jsonRes_({
    ok: true,
    count: data.items.length,
    savedAt: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
  });
}

function jsonRes_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
