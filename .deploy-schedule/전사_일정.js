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
  if (action === 'schedule_dropped') return droppedLog_();
  return jsonRes_({ ok: true, msg: '웰페리온 전사 일정 SSOT 백엔드 정상 동작 중' });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var body = JSON.parse(e.postData.contents);
    var action = body.action || '';
    if (action === 'save_schedule') return saveSchedule_(body);
    if (action === 'upload_evidence') return uploadEvidence_(body);
    return jsonRes_({ ok: false, error: '알 수 없는 action: ' + action });
  } catch (err) {
    return jsonRes_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

// ─── 조회: 저장된 전체 schedule JSON 반환. 저장본 없으면 data:null(프론트가 github seed 폴백) ───
function loadSchedule_() {
  var props = PropertiesService.getScriptProperties();
  var raw = props.getProperty(SCHEDULE_PROP);
  var data = null;
  if (raw) {
    try { data = JSON.parse(raw); } catch (err) { data = null; }
  }
  // rev = 이 저장본의 판번호. 저장할 때 받은 rev 와 서버 rev 가 다르면 그 사이에 남이 저장한 것이다.
  return jsonRes_({ ok: true, data: data, rev: props.getProperty(SCHEDULE_REV_PROP) || '' });
}

// ─── 저장: 전체 schedule JSON 덮어쓰기. items 배열 없으면 거부(파괴적 저장 방지) ───
// 저장 직전 기존 값을 SCHEDULE_SSOT_BAK에 1개 백업(롤백 안전망).
//
// ★유실 방지 3종 (GM 지적 2026-08-12 "아무 기록없이 날라간것들이 많고")
//   저장은 55건 전체를 한 덩어리로 덮어쓴다. 그래서 휴대폰과 PC를 같이 열어 두면 나중 저장이
//   앞선 것을 통째로 밀어내고, 되돌릴 것은 직전 1벌뿐이라 그마저 다음 저장에 사라졌다.
//   무엇이 언제 없어졌는지 적는 곳도 없었다. 아래 셋으로 막는다.
//   ① 급감 거부 — 항목이 30% 넘게 줄면 저장을 거절한다(force:true 로만 통과).
//   ② 백업 3벌 롤링 — 직전 1벌이 아니라 최근 3벌을 남긴다.
//   ③ 사라진 항목 기록 — 없어진 id·이름을 남겨 무엇이 언제 빠졌는지 되짚을 수 있게 한다.
var SCHEDULE_BAK_KEEP = 3;                       // 롤링 백업 벌 수
var SCHEDULE_DROP_LOG_PROP = 'SCHEDULE_DROPPED'; // 사라진 항목 기록
var SCHEDULE_DROP_LOG_MAX = 120;                 // 기록 상한(속성 용량 보호)
var SCHEDULE_SHRINK_GUARD = 0.7;                 // 이전 건수의 70% 미만이면 거부
// ★2026-08-26 시토 — 낙관적 잠금(배783 · 실사고 2026-08-25).
//   그날 141건이 134건으로 줄며 3건이 사라졌는데 위 급감 가드(70%)는 5% 감소라 그냥 통과했다.
//   뿌리는 '먼저 읽어 둔 스냅샷을 나중에 통째로 저장' 이라 건수 비율로는 영영 못 잡는다.
//   그래서 판번호(rev)를 대조한다 — load 때 받은 rev 를 save 에 실어 보내고, 서버 rev 와 다르면
//   그 사이에 남이 저장한 것이므로 거부하고 최신본을 돌려준다(호출부가 다시 읽어 병합 후 재시도).
//   ▸rev 를 안 보내는 옛 호출부는 그대로 통과시킨다(회귀 0) — 단 그 경우 **항목이 하나라도
//     사라지는 저장이면 거부**한다. 오늘 사고는 이 한 줄만으로도 막혔다.
var SCHEDULE_REV_PROP = 'SCHEDULE_SSOT_REV';

function saveSchedule_(body) {
  var data = body.data;
  if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
    return jsonRes_({ ok: false, error: 'items 배열이 없는 JSON은 저장할 수 없습니다.' });
  }
  var props = PropertiesService.getScriptProperties();
  var prev = props.getProperty(SCHEDULE_PROP);
  var prevItems = [];
  if (prev) {
    try { prevItems = (JSON.parse(prev) || {}).items || []; } catch (err) { prevItems = []; }
  }

  // ① 급감 거부 — 실수·경합으로 목록이 통째로 밀려나는 것을 서버에서 막는다.
  if (prevItems.length >= 5 && data.items.length < Math.floor(prevItems.length * SCHEDULE_SHRINK_GUARD)
      && body.force !== true) {
    return jsonRes_({
      ok: false,
      error: '항목이 ' + prevItems.length + '건에서 ' + data.items.length + '건으로 크게 줄어 저장을 막았습니다. '
           + '다른 기기에서 연 화면이 덮어쓰는 중일 수 있습니다 — 새로고침 후 다시 시도하세요.',
      prevCount: prevItems.length, newCount: data.items.length
    });
  }

  // ③ 사라진 항목 기록 — id 로 대조해 이번 저장에서 빠진 것을 남긴다.
  var nowStr = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
  var keep = {};
  data.items.forEach(function (it) { if (it && it.id) keep[it.id] = true; });
  var dropped = prevItems.filter(function (it) { return it && it.id && !keep[it.id]; });

  // ④ 판번호 대조 — 내가 읽은 뒤 남이 저장했으면 덮어쓰지 않는다(배783 · 실사고 2026-08-25).
  var serverRev = props.getProperty(SCHEDULE_REV_PROP) || '';
  var baseRev = (body.baseRev == null) ? null : String(body.baseRev);
  if (baseRev !== null && serverRev && baseRev !== serverRev && body.force !== true) {
    return jsonRes_({
      ok: false, error: 'stale-rev',
      message: '이 화면을 연 뒤에 다른 곳에서 일정이 저장됐습니다. 최신본을 받아 합친 뒤 다시 저장하세요.',
      serverRev: serverRev, baseRev: baseRev, data: prev ? JSON.parse(prev) : null
    });
  }
  // rev 를 안 보내는 옛 호출부: 항목이 사라지는 저장만 막는다(늘거나 그대로면 통과 — 회귀 0).
  if (baseRev === null && dropped.length && body.force !== true) {
    return jsonRes_({
      ok: false, error: 'silent-drop',
      message: '이번 저장에서 ' + dropped.length + '건이 사라집니다. 다른 곳에서 저장한 항목을 덮어쓰는 중일 수 있어 막았습니다 — 새로고침 후 다시 시도하세요.',
      droppedIds: dropped.map(function (it) { return it.id; }).slice(0, 20)
    });
  }
  if (dropped.length) {
    var log = [];
    try { log = JSON.parse(props.getProperty(SCHEDULE_DROP_LOG_PROP) || '[]') || []; } catch (err) { log = []; }
    dropped.forEach(function (it) {
      log.push({ at: nowStr, id: it.id, name: it.name || '', type: it.type || '', next_due: it.next_due || '' });
    });
    props.setProperty(SCHEDULE_DROP_LOG_PROP,
      JSON.stringify(log.slice(-SCHEDULE_DROP_LOG_MAX)));
  }

  // ② 백업 3벌 롤링 — 오래된 것부터 밀어낸다.
  if (prev) {
    for (var i = SCHEDULE_BAK_KEEP; i > 1; i--) {
      var older = props.getProperty(SCHEDULE_BAK_PROP + '_' + (i - 1));
      if (older) props.setProperty(SCHEDULE_BAK_PROP + '_' + i, older);
    }
    props.setProperty(SCHEDULE_BAK_PROP + '_1', prev);
    props.setProperty(SCHEDULE_BAK_PROP, prev);  // 옛 키도 유지 — 기존 복구 절차가 이걸 본다
  }

  props.setProperty(SCHEDULE_PROP, JSON.stringify(data));
  var newRev = nowStr + '#' + data.items.length;   // 판번호 = 저장시각+건수(사람이 읽어도 뜻이 보인다)
  props.setProperty(SCHEDULE_REV_PROP, newRev);
  // ※ 캘린더 반영은 여기서 부르지 않는다 — 웹앱 배포본이 캘린더 권한을 새로 받아야 하고,
  //    승인 전에는 저장 자체가 막힌다(저장이 본업이다). 시간 트리거가 1시간마다 따라잡는다.
  return jsonRes_({
    ok: true,
    count: data.items.length,
    dropped: dropped.length,
    savedAt: nowStr,
    rev: newRev
  });
}

// ─── 사라진 항목 되짚기 (GET ?action=schedule_dropped) ───
// 무엇이 언제 빠졌는지 사람이 확인하는 창구. 되살리기는 백업(SCHEDULE_SSOT_BAK_1~3)에서 한다.
function droppedLog_() {
  var raw = PropertiesService.getScriptProperties().getProperty(SCHEDULE_DROP_LOG_PROP);
  var log = [];
  if (raw) { try { log = JSON.parse(raw) || []; } catch (err) { log = []; } }
  return jsonRes_({ ok: true, count: log.length, dropped: log });
}

// ─── 증빙 사진 업로드 (GM 지시 2026-08-12 "사진 업로드할 수 있게 해줘, 증빙(링크) 필요없어") ───
// 파일은 드라이브에 두고 URL 만 돌려준다. 일정 자체는 ScriptProperties 한 덩어리(9KB 상한)에
// 들어가므로 사진을 그 안에 넣으면 일정 전체가 저장 불가가 된다 — 반드시 드라이브에 둔다.
// 폴더는 처음 한 번만 만들고 그 id 를 속성에 적어 둔다(매번 검색하면 느리고 중복 폴더가 생긴다).
var EVIDENCE_FOLDER_PROP = 'SCHEDULE_EVIDENCE_FOLDER_ID';
var EVIDENCE_FOLDER_NAME = '웰페리온 전사일정 증빙';

function evidenceFolder_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty(EVIDENCE_FOLDER_PROP);
  if (id) {
    try { return DriveApp.getFolderById(id); } catch (err) { /* 지워졌으면 아래에서 새로 만든다 */ }
  }
  var it = DriveApp.getFoldersByName(EVIDENCE_FOLDER_NAME);
  var folder = it.hasNext() ? it.next() : DriveApp.createFolder(EVIDENCE_FOLDER_NAME);
  props.setProperty(EVIDENCE_FOLDER_PROP, folder.getId());
  return folder;
}

function uploadEvidence_(body) {
  if (!body.file) return jsonRes_({ ok: false, error: '파일이 비어 있습니다.' });
  var name = body.fileName || ('증빙_' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMdd_HHmmss') + '.jpg');
  var mime = body.mimeType || 'image/jpeg';
  var blob = Utilities.newBlob(Utilities.base64Decode(body.file), mime, name);
  var file = evidenceFolder_().createFile(blob);
  // 링크를 아는 사람은 열 수 있게 — 화면에서 바로 눌러 봐야 하기 때문이다.
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return jsonRes_({ ok: true, url: file.getUrl(), name: name });
}

// ─── 구글 캘린더 동기화 (GM 지시 2026-09-02 "전사일정과 내 핸드폰 캘린더 연동") ───
// 전사일정 → 캘린더 한 방향만. 폰에서 고친 것은 돌아오지 않는다 —
// 저장이 전체 덮어쓰기 구조라(saveSchedule_) 양방향으로 만들면 유실 사고가 되돌아온다.
//
// 전용 캘린더('웰페리온 전사일정')를 따로 만든다. GM 개인 일정과 섞이지 않고 폰에서 껐다 켤 수 있다.
// 대조 키 = 일정 id(이벤트 태그 'sid'). 같은 일정이 두 번 생기지 않고, 전사일정에서 빠지면 캘린더에서도 지운다.
var CAL_ID_PROP = 'SCHEDULE_CALENDAR_ID';
var CAL_NAME = '웰페리온 전사일정';
var CAL_TAG = 'sid';
var CAL_TZ = 'Asia/Seoul';
var CAL_REMIND_TIMED = 10;    // 시간 있는 일정: 10분 전 (GM 확정 2026-09-02)
var CAL_REMIND_ALLDAY = 360;  // 종일 일정: 자정 기준 360분 전 = 전날 18:00 (종일은 '10분 전'이 자정 직전이라 못 쓴다)
var CAL_PAST_DAYS = 7;        // 되돌아보는 범위(지난 7일) — 이 밖의 옛 일정은 건드리지 않는다

function scheduleCalendar_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty(CAL_ID_PROP);
  if (id) {
    var cal = CalendarApp.getCalendarById(id);
    if (cal) return cal;
  }
  var found = CalendarApp.getCalendarsByName(CAL_NAME);
  var target = (found && found.length) ? found[0] : CalendarApp.createCalendar(CAL_NAME, { timeZone: CAL_TZ });
  props.setProperty(CAL_ID_PROP, target.getId());
  return target;
}

// 'yyyy-MM-dd' + 'HH:mm'(빈 값이면 종일) → 이벤트 1건 upsert 에 쓰는 시각
function calDate_(dateStr, timeStr) {
  var p = String(dateStr).split('-');
  var t = String(timeStr || '').split(':');
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]),
                  t.length === 2 ? Number(t[0]) : 0, t.length === 2 ? Number(t[1]) : 0, 0);
}

function syncCalendar_() {
  var raw = PropertiesService.getScriptProperties().getProperty(SCHEDULE_PROP);
  if (!raw) return { ok: false, error: '저장된 일정이 없습니다.' };
  var items = (JSON.parse(raw) || {}).items || [];

  var from = new Date(); from.setDate(from.getDate() - CAL_PAST_DAYS); from.setHours(0, 0, 0, 0);
  var fromStr = Utilities.formatDate(from, CAL_TZ, 'yyyy-MM-dd');
  var to = new Date(); to.setFullYear(to.getFullYear() + 3);

  var cal = scheduleCalendar_();
  var existing = {};
  cal.getEvents(from, to).forEach(function (ev) {
    var sid = ev.getTag(CAL_TAG);
    if (sid) existing[sid] = ev;
  });

  var made = 0, updated = 0, removed = 0;
  var seen = {};
  items.forEach(function (it) {
    if (!it || !it.id || !it.next_due) return;
    if (String(it.next_due) < fromStr) return;   // 범위 밖 과거는 넣지 않는다
    seen[it.id] = true;

    var timed = /^\d{2}:\d{2}$/.test(String(it.time || ''));
    var start = calDate_(it.next_due, it.time);
    var end = timed ? new Date(start.getTime() + 60 * 60 * 1000) : start;
    var title = (it.dept ? '[' + it.dept + '] ' : '') + (it.name || '(제목 없음)');
    var desc = [
      it.assignee ? '담당: ' + it.assignee : '',
      it.type ? '구분: ' + it.type : '',
      it.note ? String(it.note).slice(0, 500) : '',
      '전사일정 자동 동기화 · 고유번호 ' + it.id
    ].filter(String).join('\n');

    var ev = existing[it.id];
    if (ev) {
      // 시간제↔종일이 바뀌면 갈아끼운다(CalendarApp 은 그 전환을 직접 못 바꾼다)
      var wasAllDay = ev.isAllDayEvent();
      if (wasAllDay === timed) { ev.deleteEvent(); ev = null; }
      else {
        if (ev.getTitle() !== title) ev.setTitle(title);
        if (ev.getDescription() !== desc) ev.setDescription(desc);
        if (ev.getStartTime().getTime() !== start.getTime()) {
          if (timed) ev.setTime(start, end); else ev.setAllDayDate(start);
        }
        updated++;
      }
    }
    if (!ev) {
      ev = timed ? cal.createEvent(title, start, end, { description: desc })
                 : cal.createAllDayEvent(title, start, { description: desc });
      ev.setTag(CAL_TAG, it.id);
      ev.removeAllReminders();
      ev.addPopupReminder(timed ? CAL_REMIND_TIMED : CAL_REMIND_ALLDAY);
      made++;
    }
  });

  // 전사일정에서 빠진 것은 캘린더에서도 지운다 — 남겨 두면 없어진 일정이 폰에서 계속 울린다
  Object.keys(existing).forEach(function (sid) {
    if (!seen[sid]) { existing[sid].deleteEvent(); removed++; }
  });

  return { ok: true, calendarId: cal.getId(), created: made, updated: updated, removed: removed };
}

// ★GM 이 GAS 편집기에서 이 함수 하나만 실행하면 개통된다 —
//   권한 승인 + 캘린더 생성 + 1시간마다 자동 갱신 트리거 + 즉시 1회 동기화.
//   ▸시간 트리거로 도는 이유 = 웹앱을 다시 배포하지 않아도 되기 때문이다.
//     재배포하면 실무진이 쓰는 저장 화면이 권한 재승인 전까지 멈춘다.
function setupCalendarSync() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'hourlyCalendarSync') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('hourlyCalendarSync').timeBased().everyHours(1).create();
  var r = syncCalendar_();
  Logger.log(JSON.stringify(r));
  return r;
}

function hourlyCalendarSync() { syncCalendar_(); }

function jsonRes_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
