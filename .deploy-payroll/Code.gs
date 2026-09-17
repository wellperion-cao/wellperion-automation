/*******************************************************************
 * 웰페리온 ERP — 강사 페이롤 백엔드  v1.0  2026-09-17 (CFO)
 *
 *  ■ 무엇을 하나
 *    브로제이 API(결제이력·수강권·일정/출석·강사)를 하루 1회 수집해 「강사페이롤_DB」 시트에 저장하고,
 *    강사별 설정표(지급율·주차비·업무추진비·팀 인센티브·청구 방식·수업 코드)로 페이롤을 계산해
 *    ERP 화면(파트너팀 체계 ▸ 💰 페이롤)에 JSON 으로 돌려준다. 관리부 증빙은 강사 원본 시트 형식 사본으로 만든다.
 *    전신 = 강사 시트 바인딩 스크립트 broj_payroll v2.1.3 (2026-09-16, 강대경 9월 수기 기준값과 0원 차이 검증).
 *
 *  ■ 설치 (DB 시트에서 확장 프로그램 ▸ Apps Script)
 *    1) 이 코드를 Code.gs 로 붙여넣기 · appsscript.json 교체(시간대 Asia/Seoul · V8 · 스코프)
 *    2) 프로젝트 설정 ▸ 스크립트 속성
 *         BROJ_API_KEY        브로제이 읽기 키(CENTER · READ)       ← 코드에 넣지 않음
 *         PAYROLL_PW          화면 조회 비밀번호
 *         PAYROLL_ADMIN_PW    수집·보정·설정·증빙·마감 비밀번호
 *         EVIDENCE_FOLDER_ID  증빙 사본 폴더(cfo/페이롤증빙) ID    ← 없으면 사본은 DB 시트 폴더에 생성
 *    3) 함수 setupTabs 1회 실행(권한 승인) → 탭 12개·설정 시딩
 *    4) 배포 ▸ 새 배포 ▸ 웹 앱 · 실행 = 나(cao@ — 페이롤은 cao 계정이 통제) · 액세스 = 모든 사용자 → /exec URL 을 화면 PAYROLL_API 에
 *    5) 10월 병행 개시 시 installDailySyncTrigger 1회 실행(매일 05:00 runDailySync)
 *
 *  ■ 열람 권한 (매니저 지시 2026-09-17 「A강사 페이롤은 A강사·팀장·경영지원부·관리부」)
 *    설정_열람권한: 계정(ERP 로그인 이메일) · 범위(전체|팀|본인) · 팀(팀 범위일 때, 쉼표로 여럿) · 강사명(본인 범위, 쉼표로 여럿)
 *    화면이 /auth/me 로 읽은 로그인 계정을 viewer 로 보내면 그 범위 밖 강사는 조회·수집·보정이 막힌다(관리 기능은 전체 범위만).
 *    viewer 가 없으면(= ERP 밖에서 비밀번호로 연 경영지원·관리부 화면) 종전대로 전체. 강사·팀장 개인 계정이 ERP 에 생기는 시점에
 *    설정_열람권한에 줄만 추가하면 켜진다. 계정 사칭을 막는 단단한 검증은 서버(PostgreSQL·erp_auth) 이관 때.
 *
 *  ■ 계약 (procurement 관례) — POST JSON {action, password[, adminPassword], ...} → {ok, ...}
 *    ping · payroll_list · payroll_month · payroll_team · payroll_config_get · payroll_config_set · payroll_override_set · payroll_override_del
 *    payroll_run_sync · payroll_flags · payroll_flag_close · payroll_evidence_create · payroll_close · payroll_sync_log
 *
 *  ■ 계산 규칙 (강사 시트 수식과 동일 · 반올림 없음, 표시만 반올림)
 *    J 공제후   = 결제금액 × (1 − 회원구분 공제율)           비회원 10% · 그 외 0 · 표에 없는 구분 = 0(플래그)
 *    K 부가세   = J × 10/110       L 최종 = J − K            M 1회단가 = L / 등록회수
 *    N 지급단가 = 지급규칙(강사·회원구분): 비율 방식 = M × 비율(기본 = 강사 지급율 H5) · 고정 방식 = 고정액(예 강습권 20,000)
 *    O 진행     = 출석 SHOW/NO_SHOW 세션 수(수강권ID 조인, 폴백 회원명)     P 잔여 = 월초잔여 − O
 *    Q 청구     = N × O            T 소진 = M × O            U 미소진 = M × P
 *    청구합     = ΣQ (표준) | ΣQ ÷ ΣO × 100 (청구방식 = 100회, 김상식형)
 *    지급총액   = 업무추진비 + 청구합 + 팀매출인센티브 − (청구합 × 카드수수료율 + 주차비)
 *    팀매출인센티브 = (팀매출 ÷ 1.1) × (팀매출 ≥ 기준액 ? 상위율 : 기본율)   (사용 강사만)
 *    프로모션   = 특이사항에 「프로모션」 포함 행의 진행 합 · 프로모션 강습료 = 그 합 × 프로모션 단가(20,000)
 *******************************************************************/
var BROJ_BASE = 'https://api.broj.co.kr';
var GROUP_ID = '01M1XBZTZSR5C4BRZ7VC73NPNC';               // (주)웰페리온
var LESSON_TAGS = ['PT', '수영', '스쿼시', '체조&트램폴린', '필라테스', '골프', '유료GX', '영어뮤지컬'];
var COUNT_STATUSES = ['SHOW', 'NO_SHOW'];                  // 진행 세션으로 세는 출석 상태(매니저 규칙 2026-09-16)
var TZ = 'Asia/Seoul';

var TABS = {
  '설정_강사':   ['강사명', '팀', '직급', '활성', '브로제이강사명', 'trainer_id', '시트형식', '지급율', '주차비', '카드수수료율', '업무추진비', '청구방식', '팀인센티브', '팀인센티브기준액', '팀인센티브기본율', '팀인센티브상위율', '프로모션단가', '원본시트ID', '비고', '수정일시'],
  '설정_지급규칙': ['강사명', '회원구분', '방식', '값', '비고', '수정일시'],
  '설정_회원구분': ['회원구분', '공제율', '상품명접두', '비고'],
  '설정_수업코드': ['팀', '코드', '수업명패턴', '1회수업료', '비고'],
  '설정_열람권한': ['계정', '범위', '팀', '강사명', '비고', '수정일시'],
  '등록':   ['월', '강사명', '수강권ID', '회원명', '회원명원문', 'member_id', '등록일', '유효기간', '등록회수', '월초잔여', '결제금액', '결제일', '결제담당자', '상품명', '등록분류', '회원구분', '특이사항', '출처', '상태', '수집시각'],
  '세션':   ['월', '강사명', 'reservation_id', '일시', '수업명', '회원명', '회원명원문', '수강권ID', '수강권명', '출석', '코드', '기록명', '회차', '판별경로', '수집시각'],
  '보정':   ['월', '강사명', '대상', '키', '항목', '값', '사유', '등록자', '등록시각', '취소'],
  '월합계': ['월', '강사명', '팀', '등록건수', '신규', '재등록', '진행', '잔여', '청구합', '업무추진비', '팀인센티브', '카드수수료', '주차비', '지급총액', '소진', '미소진', '당월매출', '프로모션수', '프로모션강습료', '플래그수', '마감', '계산시각'],
  '플래그': ['월', '강사명', '유형', '키', '내용', '상태', '시각'],
  '증빙':   ['월', '강사명', '사본파일ID', 'URL', '생성자', '생성시각', '형식'],
  '동기화로그': ['실행시각', '주체', '월', '강사', 'API호출수', '결과', '소요초', '오류']
};

// ───────────────────────── 진입점 ─────────────────────────
function doGet(e) { return route_((e && e.parameter) || {}); }
function doPost(e) {
  var p = {};
  try { p = JSON.parse(e.postData.contents); } catch (err) { p = (e && e.parameter) || {}; }
  return route_(p);
}
function out_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
function route_(p) {
  var a = String(p.action || '');
  try {
    if (a === 'ping') return out_({ ok: true, system: 'payroll', at: now_() });
    if (badPw_(p.password)) return out_({ ok: false, error: 'unauthorized' });
    switch (a) {
      case 'payroll_list':          return out_(listPayroll_(p.month, p.instructor, p.viewer));
      case 'payroll_month':         return out_(payrollMonth_(p.month, p.team, p.viewer));
      case 'payroll_team':          return out_(teamSummary_(p.month, p.team, p.viewer));
      case 'payroll_config_get':    return out_(configGet_(p.viewer));
      case 'payroll_flags':         var sc0 = scopeFor_(loadConfig_(), p.viewer);
                                    return out_({ ok: true, scope: sc0.mode, rows: readTab_('플래그').filter(function (r) { return (!p.month || ym7_(r['월']) === p.month) && (!p.instructor || r['강사명'] === p.instructor) && allowName_(sc0, r['강사명']); }) });
      case 'payroll_sync_log':      return out_({ ok: true, rows: readTab_('동기화로그').slice(-(+p.limit || 30)) });
    }
    if (badAdmin_(p.adminPassword)) return out_({ ok: false, error: 'unauthorized_admin' });
    var scA = scopeFor_(loadConfig_(), p.viewer);                       // 관리 기능(수집·보정·설정·증빙·마감)은 전체 범위 계정만
    if (scA.mode !== '전체') return out_({ ok: false, error: 'forbidden_scope: 관리 기능은 경영지원부·관리부 계정만' });
    switch (a) {
      case 'payroll_config_set':    return out_(configSet_(p.table, p.rows || [], p.by));
      case 'payroll_override_set':  return out_(overrideSet_(p));
      case 'payroll_override_del':  return out_(overrideDel_(p.row));
      case 'payroll_run_sync':      return out_(runSyncAction_(p));
      case 'payroll_flag_close':    return out_(flagClose_(p.row));
      case 'payroll_evidence_create': return out_(evidenceCreate_(p.month, p.instructor, p.by));
      case 'payroll_close':         return out_(closeMonth_(p.month, p.instructor, p.reopen));
    }
    return out_({ ok: false, error: 'unknown_action: ' + a });
  } catch (err) {
    return out_({ ok: false, error: 'server_error: ' + (err && err.message ? err.message : err) });
  }
}
function prop_(k) { return PropertiesService.getScriptProperties().getProperty(k); }
function badPw_(pw) { var need = prop_('PAYROLL_PW'); return !need || String(pw || '') !== need; }          // fail-closed
function badAdmin_(pw) { var need = prop_('PAYROLL_ADMIN_PW'); return !need || String(pw || '') !== need; }
function now_() { return Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd HH:mm:ss'); }

// ───────────────────────── DB(시트) ─────────────────────────
function db_() { var id = prop_('PAYROLL_DB_ID'); return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet(); }
function tab_(name) {
  var ss = db_(), sh = ss.getSheetByName(name);
  if (!sh) { sh = ss.insertSheet(name); sh.appendRow(TABS[name]); sh.setFrozenRows(1); }
  var mi = TABS[name].indexOf('월');
  if (mi >= 0 && !sh._monthFmt) { try { sh.getRange(1, mi + 1, sh.getMaxRows(), 1).setNumberFormat('@'); } catch (e) {} sh._monthFmt = true; }
  return sh;
}
function readTab_(name) {
  var sh = tab_(name), n = sh.getLastRow();
  if (n < 2) return [];
  var head = TABS[name], vals = sh.getRange(2, 1, n - 1, head.length).getValues(), rows = [];
  for (var i = 0; i < vals.length; i++) {
    var o = { _row: i + 2 }, empty = true;
    for (var c = 0; c < head.length; c++) { var v = vals[i][c]; if (v instanceof Date) v = Utilities.formatDate(v, TZ, 'yyyy-MM-dd HH:mm:ss'); o[head[c]] = v; if (v !== '' && v != null) empty = false; }
    if (!empty) rows.push(o);
  }
  return rows;
}
function rowArr_(name, o) { return TABS[name].map(function (h) { return o[h] == null ? '' : o[h]; }); }
/** 키 열 조합이 같은 행은 갱신, 없으면 추가 */
function keyVal_(col, v) { return col === '월' ? ym7_(v) : String(v == null ? '' : v); }
function upsert_(name, keyCols, objs) {
  var sh = tab_(name), existing = readTab_(name), idx = {};
  existing.forEach(function (r) { idx[keyCols.map(function (k) { return keyVal_(k, r[k]); }).join('|')] = r._row; });
  var add = [], addIdx = {}, upd = 0;                       // addIdx: 같은 배치 안 같은 키가 두 번 오면(결제 2건→같은 수강권) 두 번째가 첫 추가행을 덮어쓴다(중복 append 방지)
  objs.forEach(function (o) {
    var k = keyCols.map(function (c) { return keyVal_(c, o[c]); }).join('|');
    var row = rowArr_(name, o);
    if (idx[k]) { sh.getRange(idx[k], 1, 1, TABS[name].length).setValues([row]); upd++; }
    else if (addIdx[k] != null) { add[addIdx[k]] = row; }
    else { addIdx[k] = add.length; add.push(row); }
  });
  if (add.length) sh.getRange(sh.getLastRow() + 1, 1, add.length, TABS[name].length).setValues(add);
  return { added: add.length, updated: upd };
}
function deleteRows_(name, pred) {
  var sh = tab_(name), rows = readTab_(name).filter(pred).map(function (r) { return r._row; }).sort(function (a, b) { return b - a; });
  rows.forEach(function (r) { sh.deleteRow(r); });
  return rows.length;
}
function setupTabs() {
  Object.keys(TABS).forEach(function (n) { tab_(n); });
  seedConfig_();
  return 'ok';
}
/** 최초 설정 시딩(이미 값이 있으면 건드리지 않음) — 강대경 원본 시트 실측값 */
function seedConfig_() {
  if (!readTab_('설정_회원구분').length) upsert_('설정_회원구분', ['회원구분'], [
    { '회원구분': '정회원', '공제율': 0, '상품명접두': '(정)', '비고': '' },
    { '회원구분': '비회원', '공제율': 0.1, '상품명접두': '(비)', '비고': '시설이용료 10% 공제' },
    { '회원구분': '비회원a', '공제율': 0, '상품명접두': '', '비고': '' },
    { '회원구분': 'WSC', '공제율': 0, '상품명접두': '(WSC)', '비고': '' },
    { '회원구분': '직원', '공제율': 0, '상품명접두': '', '비고': '지급단가 60%' },
    { '회원구분': '직원가족', '공제율': 0, '상품명접두': '', '비고': '지급단가 40%' },
    { '회원구분': '필드레슨', '공제율': 0, '상품명접두': '', '비고': '골프 · 지급단가 70%' },
    { '회원구분': '강습권', '공제율': 0, '상품명접두': '', '비고': '지급단가 고정 20,000(PT·골프)' }
  ]);
  if (!readTab_('설정_수업코드').length) upsert_('설정_수업코드', ['팀', '코드'], [
    { '팀': '수영', '코드': 'B', '수업명패턴': 'WSC|5', '1회수업료': 47500, '비고': 'wsc 1:5 4회' },
    { '팀': '수영', '코드': 'C', '수업명패턴': 'WSC|2', '1회수업료': 70000, '비고': 'wsc 1:2 4회' },
    { '팀': '수영', '코드': 'F', '수업명패턴': 'WSC|1', '1회수업료': 92500, '비고': 'wsc 1:1 4회' },
    { '팀': '수영', '코드': 'X', '수업명패턴': 'WSC|5|1회', '1회수업료': 50000, '비고': 'wsc 1:5 1회' },
    { '팀': '수영', '코드': 'G', '수업명패턴': '정|1', '1회수업료': 85000, '비고': '성인 1:1 4회 정회원' },
    { '팀': '수영', '코드': 'H', '수업명패턴': '비|1', '1회수업료': 88773, '비고': '성인 1:1 4회 비회원' },
    { '팀': '수영', '코드': 'I', '수업명패턴': '정|2', '1회수업료': 70000, '비고': '성인 1:2 4회 정회원' },
    { '팀': '수영', '코드': 'J', '수업명패턴': '비|2', '1회수업료': 75273, '비고': '성인 1:2 4회 비회원' },
    { '팀': '수영', '코드': 'O', '수업명패턴': '노블레스', '1회수업료': 16364, '비고': '노블레스 8회' },
    { '팀': '수영', '코드': 'K', '수업명패턴': '플래티넘|남', '1회수업료': 27000, '비고': '비/플래티넘 남 8회' },
    { '팀': '수영', '코드': 'M', '수업명패턴': '플래티넘|남|26', '1회수업료': 33750, '비고': '비/플래티넘 남 8회(26.02 인상)' },
    { '팀': '수영', '코드': 'L', '수업명패턴': '플래티넘|여', '1회수업료': 24300, '비고': '비/플래티넘 여 8회' },
    { '팀': '수영', '코드': 'N', '수업명패턴': '플래티넘|여|26', '1회수업료': 30375, '비고': '비/플래티넘 여 8회(26.02 인상)' },
    { '팀': '수영', '코드': 'Q', '수업명패턴': '4회', '1회수업료': 27000, '비고': '4회' },
    { '팀': '수영', '코드': 'P', '수업명패턴': '모자', '1회수업료': 60000, '비고': '모자' },
    { '팀': '수영', '코드': 'D', '수업명패턴': '포도|베네뎀', '1회수업료': 24545, '비고': '포도/베네뎀' },
    { '팀': '체조', '코드': 'A', '수업명패턴': 'WSC|5', '1회수업료': 47500, '비고': 'wsc 1:5 4회(체조 시트 A)' },
    { '팀': '체조', '코드': 'B', '수업명패턴': 'WSC|2', '1회수업료': 70000, '비고': 'wsc 1:2 4회' },
    { '팀': '체조', '코드': 'C', '수업명패턴': 'WSC|1', '1회수업료': 92500, '비고': 'wsc 1:1 4회' }
  ]);
  if (!readTab_('설정_열람권한').length) upsert_('설정_열람권한', ['계정'], [
    { '계정': 'cao@wellperion.com', '범위': '전체', '팀': '', '강사명': '', '비고': '경영지원부', '수정일시': now_() },
    { '계정': 'info@wellperion.com', '범위': '전체', '팀': '', '강사명': '', '비고': '관리부', '수정일시': now_() },
    { '계정': 'ceo@wellperion.com', '범위': '전체', '팀': '', '강사명': '', '비고': '대표', '수정일시': now_() },
    { '계정': 'coo@wellperion.com', '범위': '전체', '팀': '', '강사명': '', '비고': 'GM', '수정일시': now_() },
    { '계정': '', '범위': '팀', '팀': '수영', '강사명': '', '비고': '예시 — 수영 팀장 계정이 생기면 계정칸에 이메일을 적는다(팀 전체 열람)', '수정일시': now_() },
    { '계정': '', '범위': '본인', '팀': '', '강사명': '강대경', '비고': '예시 — 강사 개인 계정이 생기면 계정칸에 이메일을 적는다(본인만 열람)', '수정일시': now_() }
  ]);
  if (!readTab_('설정_강사').length) upsert_('설정_강사', ['강사명'], [
    // 9월 시트 요약 블록 실측(2026-09-17): H5 지급율 · M5 주차비 · A5 업무추진비 · J5 청구방식 · K5 팀인센티브. 시트형식 = 수영격자(하루 2열·시간블록·*이름*) / 30분격자(하루 1열·30분행·이름)
    { '강사명': '강대경', '팀': '수영', '직급': '시니어', '활성': 'Y', '브로제이강사명': '수영 강대경', 'trainer_id': '', '시트형식': '수영격자', '지급율': 0.5, '주차비': 100000, '카드수수료율': 0.025, '업무추진비': 0, '청구방식': '표준', '팀인센티브': 'N', '팀인센티브기준액': 110000000, '팀인센티브기본율': 0.01, '팀인센티브상위율': 0.02, '프로모션단가': 20000, '원본시트ID': '1nO09_lMIY0_mn0tJP6cA0grd8c-uMB8fQfjsTRa2FJE', '비고': '1단계 검증 완료(9월 진행15·청구446,250·지급335,094)', '수정일시': now_() },
    { '강사명': '이형주', '팀': '체조', '직급': '팀장', '활성': 'Y', '브로제이강사명': '', 'trainer_id': '', '시트형식': '수영격자', '지급율': 0.5, '주차비': 100000, '카드수수료율': 0.025, '업무추진비': 0, '청구방식': '표준', '팀인센티브': 'N', '팀인센티브기준액': 110000000, '팀인센티브기본율': 0.01, '팀인센티브상위율': 0.02, '프로모션단가': 20000, '원본시트ID': '1ECN2do-8eC0di8r1JvnRBAeC3MWSRKJKxRryjtQJQ6Y', '비고': '체조 코드 A/B/C · 스케줄러합계 = N월S!E105', '수정일시': now_() },
    { '강사명': '김상식', '팀': 'PT', '직급': '팀장', '활성': 'Y', '브로제이강사명': '', 'trainer_id': '', '시트형식': '30분격자', '지급율': 0.55, '주차비': 100000, '카드수수료율': 0.025, '업무추진비': 3000000, '청구방식': '100회', '팀인센티브': 'Y', '팀인센티브기준액': 110000000, '팀인센티브기본율': 0.01, '팀인센티브상위율': 0.02, '프로모션단가': 20000, '원본시트ID': '1smllGs3_JebJBKJNjms-vIF_v0cxlKpGa8tvuhZrwE0', '비고': '청구합 = ΣQ÷진행×100 · 팀매출은 보정(월합계·팀매출)으로 입력', '수정일시': now_() },
    { '강사명': '김재용', '팀': 'PT', '직급': '강사', '활성': 'Y', '브로제이강사명': '', 'trainer_id': '', '시트형식': '30분격자', '지급율': 0.5, '주차비': 50000, '카드수수료율': 0.025, '업무추진비': 0, '청구방식': '표준', '팀인센티브': 'N', '팀인센티브기준액': 110000000, '팀인센티브기본율': 0.01, '팀인센티브상위율': 0.02, '프로모션단가': 20000, '원본시트ID': '1lP0ZxHifKlSsi3lq_qEhAU-nZg2ZzRZMFq3q7PzFzEk', '비고': '', '수정일시': now_() },
    { '강사명': '박찬중', '팀': '골프', '직급': '프로', '활성': 'Y', '브로제이강사명': '', 'trainer_id': '', '시트형식': '30분격자', '지급율': 0.6, '주차비': 50000, '카드수수료율': 0.025, '업무추진비': 0, '청구방식': '표준', '팀인센티브': 'N', '팀인센티브기준액': 110000000, '팀인센티브기본율': 0.01, '팀인센티브상위율': 0.02, '프로모션단가': 20000, '원본시트ID': '121sQYXFZD_fAkl09xIeQvAFoZHd0sxK9PJ8bZfCBcfA', '비고': '필드레슨 70%', '수정일시': now_() }
  ]);
  if (!readTab_('설정_지급규칙').length) upsert_('설정_지급규칙', ['강사명', '회원구분'], [
    { '강사명': '*', '회원구분': '정회원', '방식': '비율', '값': 'H5', '비고': '강사 지급율', '수정일시': now_() },
    { '강사명': '*', '회원구분': '비회원', '방식': '비율', '값': 'H5', '비고': '', '수정일시': now_() },
    { '강사명': '*', '회원구분': '비회원a', '방식': '비율', '값': 'H5', '비고': '', '수정일시': now_() },
    { '강사명': '*', '회원구분': 'WSC', '방식': '비율', '값': 'H5', '비고': '', '수정일시': now_() },
    { '강사명': '*', '회원구분': '직원', '방식': '비율', '값': 0.6, '비고': '', '수정일시': now_() },
    { '강사명': '*', '회원구분': '직원가족', '방식': '비율', '값': 0.4, '비고': '', '수정일시': now_() },
    { '강사명': '*', '회원구분': '필드레슨', '방식': '비율', '값': 0.7, '비고': '골프', '수정일시': now_() },
    { '강사명': '*', '회원구분': '강습권', '방식': '고정', '값': 20000, '비고': 'PT·골프', '수정일시': now_() }
  ]);
}

// ───────────────────────── 설정 ─────────────────────────
function loadConfig_() {
  var instr = readTab_('설정_강사'), rules = readTab_('설정_지급규칙'), mt = readTab_('설정_회원구분'), codes = readTab_('설정_수업코드');
  return { instructors: instr, rules: rules, memberTypes: mt, codes: codes, viewers: readTab_('설정_열람권한') };
}
/** 로그인 계정(viewer) → 열람 범위. 계정이 표에 없으면 전체(전환기 기본 · 화면은 조회 비밀번호로 이미 잠겨 있다) */
function scopeFor_(cfg, viewer) {
  var v = String(viewer || '').trim().toLowerCase();
  if (!v) return { mode: '전체', teams: [], names: [], viewer: '' };
  var row = (cfg.viewers || []).filter(function (r) { return String(r['계정'] || '').trim().toLowerCase() === v; })[0];
  if (!row) return { mode: '전체', teams: [], names: [], viewer: v };
  var split = function (x) { return String(x || '').split(/[,·\/]/).map(function (t) { return t.trim(); }).filter(Boolean); };
  var mode = String(row['범위'] || '전체').trim();
  return { mode: (mode === '팀' || mode === '본인') ? mode : '전체', teams: split(row['팀']), names: split(row['강사명']), viewer: v };
}
/** 그 강사를 이 범위로 볼 수 있나 */
function allowName_(sc, name) {
  if (!sc || sc.mode === '전체') return true;
  var n = String(name || '').trim();
  if (sc.mode === '본인') return sc.names.indexOf(n) >= 0;
  var it = readTab_('설정_강사').filter(function (r) { return String(r['강사명']).trim() === n; })[0];
  return !!it && sc.teams.indexOf(String(it['팀']).trim()) >= 0;
}
/** 설정 조회 — 범위 밖 강사는 목록에서 뺀다(화면 드롭다운이 곧 권한) */
function configGet_(viewer) {
  var cfg = loadConfig_(), sc = scopeFor_(cfg, viewer);
  if (sc.mode !== '전체') {
    cfg.instructors = cfg.instructors.filter(function (r) { return allowName_(sc, r['강사명']); });
    cfg.viewers = [];                                                  // 남의 계정 권한표는 내려보내지 않는다
  }
  return { ok: true, config: cfg, scope: sc.mode, viewer: sc.viewer };
}
function cfgFor_(cfg, name) {
  var it = cfg.instructors.filter(function (r) { return String(r['강사명']).trim() === String(name).trim(); })[0];
  if (!it) throw new Error('설정_강사에 없는 강사: ' + name);
  var deduct = {}; cfg.memberTypes.forEach(function (m) { deduct[String(m['회원구분']).trim()] = num_(m['공제율']); });
  var rules = {};
  cfg.rules.forEach(function (r) { if (String(r['강사명']).trim() === '*') rules[String(r['회원구분']).trim()] = r; });
  cfg.rules.forEach(function (r) { if (String(r['강사명']).trim() === String(name).trim()) rules[String(r['회원구분']).trim()] = r; });  // 강사별 규칙이 공통(*) 을 덮음
  var codes = cfg.codes.filter(function (c) { return String(c['팀']).trim() === String(it['팀']).trim(); });
  return { it: it, deduct: deduct, rules: rules, codes: codes, rate: num_(it['지급율']) };
}
function configSet_(table, rows, by) {
  if (!TABS[table] || table.indexOf('설정_') !== 0) return { ok: false, error: 'bad_table' };
  var keys = { '설정_강사': ['강사명'], '설정_지급규칙': ['강사명', '회원구분'], '설정_회원구분': ['회원구분'], '설정_수업코드': ['팀', '코드'] }[table];
  rows.forEach(function (r) { if ('수정일시' in TABS[table].reduce(function (o, h) { o[h] = 1; return o; }, {})) r['수정일시'] = now_() + (by ? ' ' + by : ''); });
  var res = upsert_(table, keys, rows);
  return { ok: true, table: table, added: res.added, updated: res.updated };
}

// ───────────────────────── 규칙 엔진 ─────────────────────────
function computeRow_(reg, c, progress) {
  var G = num_(reg['결제금액']), E = num_(reg['등록회수']), F = (reg['월초잔여'] === '' || reg['월초잔여'] == null) ? E : num_(reg['월초잔여']);
  var gb = String(reg['회원구분'] || '').trim();
  var known = gb in c.deduct;
  var J = known ? G * (1 - c.deduct[gb]) : 0;
  var K = J * 10 / 110, L = J - K, M = E ? L / E : 0;
  var rule = c.rules[gb], N = 0, ruleTxt = '', badWay = '';
  if (rule) {
    var v = rule['값'];
    var way = String(rule['방식'] || '').trim();
    if (way === '고정') { N = num_(v); ruleTxt = '고정 ' + N; }
    else if (way === '비율' || way === '') { var rate = (String(v).trim().toUpperCase() === 'H5') ? c.rate : num_(v); N = M * rate; ruleTxt = '단가×' + rate; }
    else { N = 0; ruleTxt = '미지원방식 ' + way; badWay = way; }     // 시급·인원제 등은 아직 미구현 → 0 + 플래그(조용히 0 이 되지 않게)
  }
  var O = progress || 0, P = F - O, Q = N * O, T = M * O, U = M * P;
  return { J: J, K: K, L: L, M: M, N: N, O: O, P: P, Q: Q, T: T, U: U, F: F, ruleTxt: ruleTxt, known: known, hasRule: !!rule, badWay: badWay };
}
function applyOverrides_(rows, sessions, overrides) {
  var byKey = {};
  overrides.forEach(function (o) { if (String(o['취소']).toUpperCase() === 'Y') return; byKey[o['대상'] + '|' + o['키'] + '|' + o['항목']] = o; });
  rows.forEach(function (r) {
    ['진행', '월초잔여', '결제금액', '회원구분', '등록회수', '특이사항'].forEach(function (f) {
      var o = byKey['등록|' + r['수강권ID'] + '|' + f];
      if (o) { r._ovr = r._ovr || []; r._ovr.push({ '항목': f, '값': o['값'], '사유': o['사유'] }); r[f === '진행' ? '_progressOverride' : f] = (f === '진행' ? +o['값'] : o['값']); }
    });
  });
  return byKey;
}
function summarize_(rows, sessions, c, ym, summaryOvr) {
  var s = { 등록건수: rows.length, 신규: 0, 재등록: 0, 진행: 0, 잔여: 0, 청구합: 0, 소진: 0, 미소진: 0, 당월매출: 0, 프로모션수: 0 };
  rows.forEach(function (r) {
    if (String(r['등록분류']) === '신규') s.신규++; else if (String(r['등록분류']) === '재등록') s.재등록++;
    s.진행 += r._c.O; s.잔여 += r._c.P; s.청구합 += r._c.Q; s.소진 += r._c.T; s.미소진 += r._c.U;
    if (String(r['등록일'] || '').slice(0, 7) === ym) s.당월매출 += num_(r['결제금액']);
    if (String(r['특이사항'] || '').indexOf('프로모션') >= 0) s.프로모션수 += r._c.O;
  });
  var it = c.it, method = String(it['청구방식'] || '표준').trim();
  if (method === '100회' && s.진행 > 0) s.청구합 = s.청구합 / s.진행 * 100;     // 김상식형: ΣQ ÷ 진행 × 100
  s.청구방식 = method;
  s.업무추진비 = num_(it['업무추진비']);
  var teamSales = summaryOvr && summaryOvr['팀매출'] != null ? num_(summaryOvr['팀매출']) : 0;
  s.팀매출 = teamSales;
  s.팀인센티브 = 0;
  s.팀매출필요 = String(it['팀인센티브']).toUpperCase() === 'Y';
  if (s.팀매출필요 && teamSales > 0) {
    var rate = teamSales >= num_(it['팀인센티브기준액']) ? num_(it['팀인센티브상위율']) : num_(it['팀인센티브기본율']);
    s.팀인센티브 = (teamSales / 1.1) * rate;
  }
  s.카드수수료율 = num_(it['카드수수료율'], 0.025);
  s.카드수수료 = s.청구합 * s.카드수수료율;
  s.주차비 = num_(it['주차비']);
  s.지급총액 = s.업무추진비 + s.청구합 + s.팀인센티브 - (s.카드수수료 + s.주차비);
  s.프로모션강습료 = s.프로모션수 * num_(it['프로모션단가'], 20000);
  // 스케줄러 금액 합계(P5 검산): 수영격자 = Σ수업료표 단가 × 지급율(N월S!E128×H5) / 30분격자 = 출석 세션마다 그 회원의 지급단가 N 합(N월S 36행 합)
  if (it['시트형식'] === '수영격자') s.스케줄러합계 = sessions.reduce(function (a, x) { return a + num_(x['수업료']); }, 0) * c.rate;
  else {
    var nByTicket = {}, nByName = {};
    rows.forEach(function (r) { nByTicket[r['수강권ID']] = r._c.N; if (nByName[r['회원명']] == null) nByName[r['회원명']] = r._c.N; });
    s.스케줄러합계 = sessions.reduce(function (a, x) { if (COUNT_STATUSES.indexOf(String(x['출석'])) < 0) return a; var n = nByTicket[x['수강권ID']]; if (n == null) n = nByName[x['회원명']] || 0; return a + n; }, 0);
  }
  return s;
}
/** 월·강사 계산 결과(등록행 계산·세션·합계·플래그) — 화면 응답과 월합계 캐시가 같은 함수를 쓴다 */
function calc_(ym, name) {
  var cfg = loadConfig_(), c = cfgFor_(cfg, name);
  var regs = readTab_('등록').filter(function (r) { return ym7_(r['월']) === ym && r['강사명'] === name; });
  var sess = readTab_('세션').filter(function (r) { return ym7_(r['월']) === ym && r['강사명'] === name; });
  var ovr = readTab_('보정').filter(function (r) { return ym7_(r['월']) === ym && r['강사명'] === name && String(r['취소']).toUpperCase() !== 'Y'; });
  return calcCore_(ym, name, c, regs, sess, ovr);
}
/** 이미 읽어온 등록·세션·보정 슬라이스로 한 강사 계산 — 대량 조회(payrollMonth_)가 시트를 강사마다 다시 읽지 않게 */
function calcCore_(ym, name, c, regs, sess, ovr) {
  var codePrice = {}; c.codes.forEach(function (x) { codePrice[String(x['코드']).trim()] = +x['1회수업료'] || 0; });
  sess.forEach(function (x) { x['수업료'] = codePrice[String(x['코드']).trim()] || 0; });
  // 진행 = 출석 세션(SHOW/NO_SHOW) 수 — 수강권ID 조인, 없으면 회원명
  var progByTicket = {}, progByName = {};
  sess.forEach(function (x) {
    if (COUNT_STATUSES.indexOf(String(x['출석'])) < 0) return;
    progByTicket[x['수강권ID']] = (progByTicket[x['수강권ID']] || 0) + 1;
    progByName[x['회원명']] = (progByName[x['회원명']] || 0) + 1;
  });
  var summaryOvr = {};
  ovr.forEach(function (o) { if (o['대상'] === '월합계') summaryOvr[o['항목']] = o['값']; });
  applyOverrides_(regs, sess, ovr);
  var flags = [];
  regs.forEach(function (r) {
    var prog = (r._progressOverride != null) ? r._progressOverride : (progByTicket[r['수강권ID']] != null ? progByTicket[r['수강권ID']] : (progByName[r['회원명']] || 0));
    r._c = computeRow_(r, c, prog);
    if (!r._c.known) flags.push({ 유형: '회원구분미정의', 키: r['수강권ID'], 내용: r['회원명'] + ' 회원구분 「' + r['회원구분'] + '」 공제율 표에 없음 → 공제후 0' });
    if (!r._c.hasRule) flags.push({ 유형: '지급규칙없음', 키: r['수강권ID'], 내용: r['회원명'] + ' 회원구분 「' + r['회원구분'] + '」 지급규칙 없음 → 지급단가 0' });
    if (r._c.P < 0) flags.push({ 유형: '잔여음수', 키: r['수강권ID'], 내용: r['회원명'] + ' 잔여 ' + r._c.P });
    if (r._c.badWay) flags.push({ 유형: '지급방식미지원', 키: r['수강권ID'], 내용: r['회원명'] + ' 회원구분 「' + r['회원구분'] + '」 방식 「' + r._c.badWay + '」 은 아직 계산기가 없음 → 지급단가 0(보정으로 넣을 것)' });
    if (String(r['상태']) && String(r['상태']) !== '정상') flags.push({ 유형: '등록상태', 키: r['수강권ID'], 내용: r['회원명'] + ' ' + r['상태'] });
  });
  var ticketSet = {}; regs.forEach(function (r) { ticketSet[r['수강권ID']] = 1; });
  sess.forEach(function (x) {
    if (COUNT_STATUSES.indexOf(String(x['출석'])) >= 0 && !ticketSet[x['수강권ID']] && !regs.some(function (r) { return r['회원명'] === x['회원명']; }))
      flags.push({ 유형: '등록없는세션', 키: x['reservation_id'], 내용: x['일시'] + ' ' + x['회원명'] + ' 출석 세션이 있으나 이 달 등록 행 없음(이관 수강권·전월 등록)' });
    if (String(x['코드']) === '?' ) flags.push({ 유형: '코드미판별', 키: x['reservation_id'], 내용: x['일시'] + ' ' + x['회원명'] + ' ' + x['수강권명'] });
  });
  // 같은 회원이 한 달에 두 줄 이상(구·신 수강권) — 강사 시트는 이름 COUNTIFS 라 세션을 줄마다 세어 청구가 부풀 수 있다.
  // ERP 는 수강권ID 로 갈라 세므로 값이 다를 수 있어, 회귀 대조 때 먼저 볼 수 있게 표시한다(반박검증 2026-09-17).
  var byMember = {};
  regs.forEach(function (r) { var n = String(r['회원명'] || '').trim(); if (n) (byMember[n] = byMember[n] || []).push(r); });
  Object.keys(byMember).forEach(function (n) {
    if (byMember[n].length > 1) flags.push({ 유형: '중복등록', 키: byMember[n].map(function (r) { return r['수강권ID']; }).join(','),
      내용: n + ' 이 달 등록 ' + byMember[n].length + '건(수강권 여러 개) — 수기 시트는 이름으로 세어 이중 계상될 수 있음, ERP 는 수강권ID 로 분리 집계' });
  });
  var summary = summarize_(regs, sess, c, ym, summaryOvr);
  if (summary.팀매출필요 && !(summary.팀매출 > 0))
    flags.push({ 유형: '팀매출미입력', 키: ym, 내용: name + ' 은 팀매출 인센티브 대상인데 팀매출이 없어 인센티브 0 — 보정(대상=월합계·항목=팀매출)으로 입력할 것' });
  return { cfg: c, regs: regs, sessions: sess, overrides: ovr, summary: summary, flags: flags };
}
/** 계산 결과 r 을 화면용 JSON 으로 정형(listPayroll_·payrollMonth_ 공용) */
function shapeCalc_(r, ym, name, closed, syncedAt) {
  var today = new Date();
  var regs = r.regs.map(function (x) {
    var c = x._c, end = x['유효기간'] ? new Date(String(x['유효기간']).slice(0, 10)) : null;
    return { key: x['수강권ID'], 회원명: x['회원명'], 회원명원문: x['회원명원문'], 회원구분: x['회원구분'], 등록일: String(x['등록일'] || '').slice(0, 10), 유효기간: String(x['유효기간'] || '').slice(0, 10),
      dday: end ? Math.round((end - today) / 86400000) : null, 등록회수: +x['등록회수'] || 0, 월초잔여: c.F, 결제금액: +x['결제금액'] || 0, 등록분류: x['등록분류'], 상품명: x['상품명'],
      공제후: c.J, 부가세: c.K, 최종: c.L, 단가: c.M, 지급단가: c.N, 규칙: c.ruleTxt, 진행: c.O, 잔여: c.P, 청구: c.Q, 소진: c.T, 미소진: c.U, 출처: x['출처'], 상태: x['상태'], 특이사항: x['특이사항'], 보정: x._ovr || [] };
  });
  var sessions = r.sessions.map(function (x) { return { rid: x['reservation_id'], 일시: x['일시'], 수업: x['수업명'], 회원: x['회원명'], 수강권ID: x['수강권ID'], 수강권명: x['수강권명'], 출석: x['출석'], 코드: x['코드'], 기록명: x['기록명'], 회차: x['회차'], 수업료: x['수업료'], 판별: x['판별경로'] }; });
  return { instructor: name, team: r.cfg.it['팀'], 직급: r.cfg.it['직급'], config: r.cfg.it, regs: regs, sessions: sessions, summary: r.summary, flags: r.flags, overrides: r.overrides, syncedAt: syncedAt || '', closed: !!closed };
}
function listPayroll_(ym, name, viewer) {
  if (!ym || !name) return { ok: false, error: 'month/instructor required' };
  var sc = scopeFor_(loadConfig_(), viewer);
  if (!allowName_(sc, name)) return { ok: false, error: 'forbidden_scope: 이 계정은 「' + name + '」 페이롤을 볼 권한이 없습니다' };
  var r = calc_(ym, name);
  var closed = readTab_('월합계').some(function (m) { return ym7_(m['월']) === ym && m['강사명'] === name && String(m['마감']) === '마감'; });
  var last = readTab_('동기화로그').filter(function (l) { return ym7_(l['월']) === ym; }).slice(-1)[0];
  var o = shapeCalc_(r, ym, name, closed, last ? last['실행시각'] : '');
  o.ok = true; o.month = ym; return o;
}
/** 한 달·한 팀 전체를 한 번의 시트 읽기로 계산 — 화면이 받아 캐시하면 강사·팀 전환이 네트워크 없이 즉시 */
function payrollMonth_(ym, team, viewer) {
  if (!ym) return { ok: false, error: 'month required' };
  var cfg = loadConfig_(), sc = scopeFor_(cfg, viewer);
  var regsAll = readTab_('등록').filter(function (r) { return ym7_(r['월']) === ym; });
  var sessAll = readTab_('세션').filter(function (r) { return ym7_(r['월']) === ym; });
  var ovrAll = readTab_('보정').filter(function (r) { return ym7_(r['월']) === ym && String(r['취소']).toUpperCase() !== 'Y'; });
  var msAll = readTab_('월합계').filter(function (m) { return ym7_(m['월']) === ym; });
  var last = readTab_('동기화로그').filter(function (l) { return ym7_(l['월']) === ym; }).slice(-1)[0];
  var syncedAt = last ? last['실행시각'] : '';
  var gReg = {}, gSess = {}, gOvr = {}, closedMap = {};
  regsAll.forEach(function (r) { (gReg[r['강사명']] = gReg[r['강사명']] || []).push(r); });
  sessAll.forEach(function (r) { (gSess[r['강사명']] = gSess[r['강사명']] || []).push(r); });
  ovrAll.forEach(function (r) { (gOvr[r['강사명']] = gOvr[r['강사명']] || []).push(r); });
  msAll.forEach(function (m) { if (String(m['마감']) === '마감') closedMap[m['강사명']] = 1; });
  var instrs = cfg.instructors.filter(function (it) {
    return String(it['활성']).toUpperCase() === 'Y' && (!team || team === '전체' || String(it['팀']).trim() === String(team).trim()) && allowName_(sc, it['강사명']);
  });
  var out = instrs.map(function (it) {
    var name = String(it['강사명']).trim(), c = cfgFor_(cfg, name);
    var r = calcCore_(ym, name, c, (gReg[name] || []).slice(), (gSess[name] || []).slice(), (gOvr[name] || []).slice());
    return shapeCalc_(r, ym, name, closedMap[name], syncedAt);
  });
  return { ok: true, month: ym, team: team || '전체', scope: sc.mode, syncedAt: syncedAt, instructors: out };
}
/** 월합계·플래그 탭 갱신(수집 후·보정 후) */
function recompute_(ym, name) {
  var r = calc_(ym, name), s = r.summary;
  var closed = readTab_('월합계').some(function (m) { return ym7_(m['월']) === ym && m['강사명'] === name && String(m['마감']) === '마감';});
  deleteRows_('월합계', function (m) { return m['강사명'] === name && String(m['월']).indexOf('-') < 0; });   // 월이 일련번호로 깨진 오염행 제거
  upsert_('월합계', ['월', '강사명'], [{ '월': ym, '강사명': name, '팀': r.cfg.it['팀'], '등록건수': s.등록건수, '신규': s.신규, '재등록': s.재등록, '진행': s.진행, '잔여': s.잔여, '청구합': s.청구합, '업무추진비': s.업무추진비, '팀인센티브': s.팀인센티브, '카드수수료': s.카드수수료, '주차비': s.주차비, '지급총액': s.지급총액, '소진': s.소진, '미소진': s.미소진, '당월매출': s.당월매출, '프로모션수': s.프로모션수, '프로모션강습료': s.프로모션강습료, '플래그수': r.flags.length, '마감': closed ? '마감' : '진행', '계산시각': now_() }]);
  deleteRows_('플래그', function (f) { return ym7_(f['월']) === ym && f['강사명'] === name && String(f['상태']) !== '처리'; });
  if (r.flags.length) {
    var sh = tab_('플래그');
    sh.getRange(sh.getLastRow() + 1, 1, r.flags.length, TABS['플래그'].length).setValues(r.flags.map(function (f) { return rowArr_('플래그', { '월': ym, '강사명': name, '유형': f.유형, '키': f.키, '내용': f.내용, '상태': '열림', '시각': now_() }); }));
  }
  return s;
}
function teamSummary_(ym, team, viewer) {
  var sc = scopeFor_(loadConfig_(), viewer);
  var rows = readTab_('월합계').filter(function (m) { return (!ym || ym7_(m['월']) === ym) && (!team || team === '전체' || m['팀'] === team) && allowName_(sc, m['강사명']); });
  var totals = {}; rows.forEach(function (m) { var t = m['팀'] || '?'; totals[t] = totals[t] || { 강사수: 0, 진행: 0, 청구합: 0, 지급총액: 0, 소진: 0, 미소진: 0, 플래그수: 0 };
    totals[t].강사수++; ['진행', '청구합', '지급총액', '소진', '미소진', '플래그수'].forEach(function (k) { totals[t][k] += +m[k] || 0; }); });
  return { ok: true, month: ym, rows: rows, totals: totals, scope: sc.mode };
}
function overrideSet_(p) {
  if (!p.month || !p.instructor || !p.target || !p.field) return { ok: false, error: 'missing fields' };
  var sh = tab_('보정');
  sh.appendRow(rowArr_('보정', { '월': p.month, '강사명': p.instructor, '대상': p.target, '키': p.key || '', '항목': p.field, '값': p.value, '사유': p.reason || '', '등록자': p.by || '', '등록시각': now_(), '취소': '' }));
  var s = recompute_(p.month, p.instructor);
  return { ok: true, row: sh.getLastRow(), summary: s };
}
function overrideDel_(row) {
  var sh = tab_('보정'), r = +row; if (!r || r < 2) return { ok: false, error: 'bad row' };
  sh.getRange(r, TABS['보정'].indexOf('취소') + 1).setValue('Y');
  var ym = sh.getRange(r, 1).getValue(), name = sh.getRange(r, 2).getValue();
  recompute_(ym, name);
  return { ok: true };
}
function flagClose_(row) { var sh = tab_('플래그'); sh.getRange(+row, TABS['플래그'].indexOf('상태') + 1).setValue('처리'); return { ok: true }; }
function closeMonth_(ym, name, reopen) {
  var sh = tab_('월합계'), rows = readTab_('월합계').filter(function (m) { return ym7_(m['월']) === ym && m['강사명'] === name; });
  if (!rows.length) recompute_(ym, name), rows = readTab_('월합계').filter(function (m) { return ym7_(m['월']) === ym && m['강사명'] === name; });
  sh.getRange(rows[0]._row, TABS['월합계'].indexOf('마감') + 1).setValue(reopen ? '진행' : '마감');
  return { ok: true, closed: !reopen };
}

// ───────────────────────── 수집(브로제이 → 등록·세션) ─────────────────────────
function runSyncAction_(p) {
  var ym = p.month || Utilities.formatDate(new Date(), TZ, 'yyyy-MM');
  if (p.scope === 'team' || p.scope === 'all') {
    PropertiesService.getScriptProperties().setProperty('SYNC_REQUEST', JSON.stringify({ month: ym, team: p.team || '', at: now_() }));
    ScriptApp.newTrigger('runQueuedSync').timeBased().after(1000).create();
    return { ok: true, queued: true, month: ym };
  }
  if (!p.instructor) return { ok: false, error: 'instructor required' };
  return syncOne_(ym, p.instructor, 'api');
}
function runQueuedSync() {
  var props = PropertiesService.getScriptProperties(), req = JSON.parse(props.getProperty('SYNC_REQUEST') || '{}');
  props.deleteProperty('SYNC_REQUEST');
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'runQueuedSync') ScriptApp.deleteTrigger(t); });
  if (!req.month) return;
  syncMany_(req.month, req.team, 'queue');
}
function runDailySync() {
  var ym = Utilities.formatDate(new Date(), TZ, 'yyyy-MM'), d = new Date().getDate();
  syncMany_(ym, '', 'trigger');
  if (d <= 5) { var prev = new Date(); prev.setDate(0); syncMany_(Utilities.formatDate(prev, TZ, 'yyyy-MM'), '', 'trigger'); }   // 월초 5일까지 전월도
}
function installDailySyncTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'runDailySync') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('runDailySync').timeBased().atHour(5).everyDays(1).inTimezone(TZ).create();
  log_('trigger', '', '전체', 0, '매일 05:00 runDailySync 설치', 0, '');
}
/** 여러 강사 — 그룹 재료(매출·일정·강사)는 1회만 받고 강사별로 나눔. 4.5분 넘으면 SYNC_CURSOR 에 남겨 이어감 */
function syncMany_(ym, team, actor) {
  var started = Date.now(), cfg = loadConfig_();
  var closedSet = {}; readTab_('월합계').forEach(function (m) { if (ym7_(m['월']) === ym && String(m['마감']) === '마감') closedSet[m['강사명']] = 1; });
  var targets = cfg.instructors.filter(function (i) { return String(i['활성']).toUpperCase() === 'Y' && (!team || team === '전체' || i['팀'] === team) && !closedSet[i['강사명']]; }).map(function (i) { return i['강사명']; });
  var props = PropertiesService.getScriptProperties(), cursor = JSON.parse(props.getProperty('SYNC_CURSOR') || 'null');
  if (cursor && cursor.month === ym && cursor.remaining) targets = cursor.remaining;
  var mat = fetchMaterials_(ym);
  var results = [];
  for (var i = 0; i < targets.length; i++) {
    results.push(syncOne_(ym, targets[i], actor, mat));
    if (Date.now() - started > 270000 && i < targets.length - 1) {
      props.setProperty('SYNC_CURSOR', JSON.stringify({ month: ym, remaining: targets.slice(i + 1) }));
      ScriptApp.newTrigger('runQueuedSyncCursor').timeBased().after(60000).create();
      log_(actor, ym, '전체', mat._calls.n, '시간 한도 — ' + (targets.length - i - 1) + '명 이어감', Math.round((Date.now() - started) / 1000), '');
      return results;
    }
  }
  props.deleteProperty('SYNC_CURSOR');
  return results;
}
function runQueuedSyncCursor() {
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'runQueuedSyncCursor') ScriptApp.deleteTrigger(t); });
  var cursor = JSON.parse(PropertiesService.getScriptProperties().getProperty('SYNC_CURSOR') || 'null');
  if (cursor && cursor.month) syncMany_(cursor.month, '', 'cursor');
}
/** 그룹 재료 1회 수집: 매출이력(월)·일정(월)·강사 목록 */
function fetchMaterials_(ym) {
  var y = +ym.slice(0, 4), m = +ym.slice(5, 7), lastDay = new Date(y, m, 0).getDate();
  var endDate = Utilities.formatDate(new Date(Math.min(new Date(y, m, 0).getTime(), Date.now())), TZ, 'yyyy-MM-dd');
  var calls = { n: 0 };
  var sales = fetchSales_(ym + '-01', endDate, calls);
  var sched = list_(call_('get', '/v1/schedules', { group_id: GROUP_ID, search_start: ym + '-01', search_end: ym + '-' + ('0' + lastDay).slice(-2) }, null, calls));
  var trainers = list_(call_('get', '/v1/trainers', { group_id: GROUP_ID }, null, calls));
  var booked = {}; sched.forEach(function (s) { ((s.reservations || {}).booked || []).forEach(function (b) { if (b.lesson_ticket_id) booked[b.lesson_ticket_id] = (booked[b.lesson_ticket_id] || 0) + 1; }); });
  return { ym: ym, sales: sales, sched: sched, trainers: trainers, bookedThisMonth: booked, tickets: {}, _calls: calls };
}
function syncOne_(ym, name, actor, mat) {
  var started = Date.now(), errTxt = '';
  try {
    var cfg = loadConfig_(), c = cfgFor_(cfg, name), it = c.it;
    mat = mat || fetchMaterials_(ym);
    var key = String(it['브로제이강사명'] || name).replace(/\s/g, ''), short = String(name).replace(/\s/g, '');
    var tr = mat.trainers.filter(function (t) { return String(t.name || '').replace(/\s/g, '') === key; })[0] || mat.trainers.filter(function (t) { return String(t.name || '').replace(/\s/g, '').indexOf(short) >= 0; })[0];
    if (!tr) throw new Error('브로제이 강사 목록에 「' + name + '」 없음');
    if (!it['trainer_id']) upsert_('설정_강사', ['강사명'], [Object.assign({}, it, { 'trainer_id': tr.trainer_id })]);
    // 1) 결제 → 등록
    var mine = mat.sales.filter(function (s) {
      if (s.history_type !== 'PAYMENT') return false;
      var tag = s.sales_tag_name || '', isLesson = LESSON_TAGS.indexOf(tag) >= 0 || (tag === '' && s.product_type === 'RESERVATION_TICKET');
      return isLesson && String(s.sales_manager_name || '').replace(/\s/g, '').indexOf(short) >= 0;
    });
    var memberIds = uniq_(mine.map(function (s) { return s.member_id; })).filter(function (id) { return !mat.tickets[id]; });
    if (memberIds.length) { var tb = fetchTicketsBatch_(memberIds, mat._calls); Object.keys(tb).forEach(function (k) { mat.tickets[k] = tb[k]; }); }
    var deductPrefix = {}; cfg.memberTypes.forEach(function (m) { if (m['상품명접두']) deductPrefix[String(m['상품명접두'])] = String(m['회원구분']); });
    var regs = [], unmatched = [];
    mine.forEach(function (s) {
      var tks = mat.tickets[s.member_id] || [], t = matchTicket_(tks, s);
      if (!t) { unmatched.push(s); return; }
      var prior = tks.filter(function (x) { return x.created_at && t.created_at && x.created_at < t.created_at; }).length;
      var g = gubun_(s.product_name, deductPrefix);
      regs.push({ '월': ym, '강사명': name, '수강권ID': t.lesson_ticket_id, '회원명': baseName_(s.customer_name), '회원명원문': s.customer_name, 'member_id': s.member_id,
        '등록일': String(t.start_at || '').slice(0, 10), '유효기간': String(t.end_at || '').slice(0, 10), '등록회수': t.origin_usage_count || parseCount_(s.product_name),
        '월초잔여': monthStartRemain_(t, mat.bookedThisMonth[t.lesson_ticket_id] || 0, parseCount_(s.product_name)), '결제금액': s.product_total_payment_price || 0, '결제일': String(s.paid_at).slice(0, 10),
        '결제담당자': s.sales_manager_name || '', '상품명': s.product_name, '등록분류': prior > 0 ? '재등록' : '신규', '회원구분': g.label, '특이사항': g.note, '출처': 'API', '상태': g.label ? '정상' : '확인필요', '수집시각': now_() });
    });
    // 재수집 = 완전 재작성: 이 강사·이 달 API 등록행 선삭제(월이 날짜/일련번호로 깨져도 제거). 수기 행(출처≠API)은 무접촉.
    var stale = function (r) { return r['강사명'] === name && String(r['출처']) === 'API' && (ym7_(r['월']) === ym || String(r['월']).indexOf('-') < 0); };
    deleteRows_('등록', stale);
    var res1 = upsert_('등록', ['월', '강사명', '수강권ID'], regs);
    // 2) 일정·출석 → 세션 (코드 = 수강권ID 조인 → 단가 → 코드표 역조회, 폴백 수강권명)
    var unitByTicket = {};
    readTab_('등록').filter(function (r) { return ym7_(r['월']) === ym && r['강사명'] === name; }).forEach(function (r) { unitByTicket[r['수강권ID']] = computeRow_(r, c, 0).M; });
    var codesByPrice = {}; c.codes.forEach(function (x) { var p = Math.round(+x['1회수업료']); (codesByPrice[p] = codesByPrice[p] || []).push(String(x['코드']).trim()); });
    var items = [];
    mat.sched.filter(function (s) { return (s.trainer_ids || []).indexOf(tr.trainer_id) >= 0; }).forEach(function (s) {
      var kst = new Date(new Date(s.schedule_start_at).getTime() + 9 * 3600 * 1000);
      ((s.reservations || {}).booked || []).forEach(function (b) {
        var st = (b.attendance || {}).attendance_status || '미처리';
        items.push({ rid: b.reservation_id, tid: b.lesson_ticket_id, name: baseName_(b.member_name), raw: b.member_name, tname: ((b.ticket || {}).lesson_ticket_name || ''), lesson: String(s.lesson_name || '').trim(), t: kst, status: st });
      });
    });
    items.sort(function (a, b) { return a.t - b.t; });
    var seq = {}, sessRows = [];
    items.forEach(function (x) {
      var cnt = COUNT_STATUSES.indexOf(x.status) >= 0;
      if (cnt) seq[x.name] = (seq[x.name] || 0) + 1;
      var cd = codeFor_(x, unitByTicket, codesByPrice, c.codes);
      sessRows.push({ '월': ym, '강사명': name, 'reservation_id': x.rid, '일시': Utilities.formatDate(x.t, 'UTC', 'yyyy-MM-dd HH:mm'), '수업명': x.lesson, '회원명': x.name, '회원명원문': x.raw, '수강권ID': x.tid || '', '수강권명': x.tname,
        '출석': x.status, '코드': cd.code, '기록명': cnt ? cd.code + x.name + seq[x.name] : '', '회차': cnt ? seq[x.name] : '', '판별경로': cd.via, '수집시각': now_() });
    });
    deleteRows_('세션', function (r) { return r['강사명'] === name && (ym7_(r['월']) === ym || String(r['월']).indexOf('-') < 0); });
    var res2 = upsert_('세션', ['월', '강사명', 'reservation_id'], sessRows);
    var s = recompute_(ym, name);
    var secs = Math.round((Date.now() - started) / 1000);
    log_(actor, ym, name, mat._calls.n, '등록 ' + regs.length + '(+' + res1.added + '/~' + res1.updated + ') 미매칭 ' + unmatched.length + ' · 세션 ' + sessRows.length + '(+' + res2.added + ') · 청구 ' + Math.round(s.청구합) + ' 지급 ' + Math.round(s.지급총액), secs, unmatched.map(function (u) { return String(u.paid_at).slice(0, 10) + ' ' + u.product_name; }).join(' | '));
    return { ok: true, month: ym, instructor: name, calls: mat._calls.n, regs: { total: regs.length, added: res1.added, updated: res1.updated, unmatched: unmatched.length }, sessions: { total: sessRows.length, added: res2.added, updated: res2.updated }, summary: s, secs: secs };
  } catch (err) {
    errTxt = String(err && err.message || err);
    log_(actor, ym, name, mat ? mat._calls.n : 0, '오류', Math.round((Date.now() - started) / 1000), errTxt);
    return { ok: false, month: ym, instructor: name, error: errTxt };
  }
}
function log_(actor, ym, name, calls, result, secs, err) {
  tab_('동기화로그').appendRow([now_(), actor, ym, name, calls, result, secs, err || '']);
}

// ───────────────────────── 규칙 헬퍼 (v2.1.3 이식) ─────────────────────────
function baseName_(n) { var s = String(n || '').trim(), m = s.match(/^[가-힣]+(?:\s+[가-힣]+)*/); s = m ? m[0] : s.replace(/[^가-힣\s]/g, '').trim(); return s.replace(/\s+/g, ' ').trim(); }
function gubun_(prod, prefixMap) {
  var p = String(prod || '').trim().replace(/^★+/, '');
  var keys = Object.keys(prefixMap || {}).sort(function (a, b) { return b.length - a.length; });
  for (var i = 0; i < keys.length; i++) if (p.indexOf(keys[i]) === 0) return { label: prefixMap[keys[i]], note: '' };
  if (p.indexOf('(WSC)') >= 0 || p.indexOf('WSC') >= 0) return { label: 'WSC', note: '' };
  if (p.indexOf('(준)') === 0) return { label: '정회원', note: '준회원 상품 — 회원구분 확인' };
  return { label: '', note: '회원구분 확인 필요' };
}
function parseCount_(prod) { var m = String(prod || '').match(/(\d+)\s*회/); return m ? +m[1] : ''; }
function toDate_(s) { if (!s) return ''; var p = String(s).slice(0, 10).split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
function matchTicket_(tickets, s) {
  var pn = String(s.product_name || '').replace(/\s/g, ''), pd = String(s.paid_at || '').slice(0, 10);
  var cand = tickets.filter(function (t) { return String(t.name || '').replace(/\s/g, '') === pn; });
  if (!cand.length) cand = tickets.filter(function (t) { return t.created_at && t.created_at >= pd; });
  if (!cand.length) return null;
  cand.sort(function (a, b) { return Math.abs(dayDiff_(a.created_at, pd)) - Math.abs(dayDiff_(b.created_at, pd)); });
  return cand[0];
}
function dayDiff_(a, b) { if (!a || !b) return 9999; return (toDate_(a) - toDate_(b)) / 86400000; }
/** F열(월초 잔여) = 현재 잔여 + 이달 예약으로 차감된 수(브로제이는 예약 시점 차감), 등록회수 이내 */
function monthStartRemain_(t, bookedCnt, fallbackCnt) {
  var origin = t.origin_usage_count || fallbackCnt || 0;
  if (t.usage_count == null) return origin;
  var v = (+t.usage_count || 0) + (+bookedCnt || 0);
  return origin ? Math.min(v, origin) : v;
}
function codeFor_(it, unitByTicket, codesByPrice, codes) {
  var lab = labelCode_(it.tname, codes);
  var u = unitByTicket[String(it.tid || '')];
  if (u) {
    var cands = codesByPrice[Math.round(u)] || [];
    if (cands.length === 1) return { code: cands[0], via: 'ID조인' };
    if (cands.length > 1) return { code: (lab && cands.indexOf(lab) >= 0) ? lab : cands[0], via: 'ID조인+이름' };
  }
  return { code: lab || '?', via: lab ? '이름라벨' : '미판별' };
}
/** 수강권 이름 → 코드: 설정_수업코드.수업명패턴 = '|' 로 나눈 토큰이 모두 포함되면 매칭(긴 패턴 우선). '5' 같은 숫자 토큰은 "1:5" 로 본다 */
function labelCode_(tname, codes) {
  var s = String(tname || ''), best = null, bestLen = -1;
  (codes || []).forEach(function (c) {
    var pat = String(c['수업명패턴'] || ''); if (!pat) return;
    var toks = pat.split('|').filter(Boolean), ok = toks.every(function (t) { return /^\d$/.test(t) ? (new RegExp('1\\s*:\\s*' + t)).test(s) : (t === '26' ? true : s.indexOf(t) >= 0); });
    if (ok && pat.length > bestLen) { best = String(c['코드']).trim(); bestLen = pat.length; }
  });
  return best || '';
}
/** 숫자 파싱 — 쉼표·원·공백 제거, 끝의 % 는 /100(설정표에 '60%' 로 적어도 0.6). 못 읽으면 기본값.
 *  (인벤토리 반박검증 2026-09-17: 시트에 텍스트로 들어간 결제금액·퍼센트 리터럴이 0으로 먹히던 자리) */
function num_(v, dflt) {
  if (v === null || v === undefined || v === '') return dflt === undefined ? 0 : dflt;
  if (typeof v === 'number') return isNaN(v) ? (dflt === undefined ? 0 : dflt) : v;
  var s = String(v).trim().replace(/[,\s₩]/g, '').replace(/원$/, ''), pct = /%$/.test(s);
  if (pct) s = s.slice(0, -1);
  var n = parseFloat(s);
  if (isNaN(n)) return dflt === undefined ? 0 : dflt;
  return pct ? n / 100 : n;
}
/** 월 정규화 — 시트가 "2026-09" 를 날짜로 바꿔 "2026-09-01 00:00:00" 이 돼도 앞 7자(YYYY-MM)로 비교한다 */
function ym7_(v) { return String(v == null ? '' : v).slice(0, 7); }
function uniq_(a) { var s = {}; return a.filter(function (x) { if (!x || s[x]) return false; s[x] = 1; return true; }); }
function list_(j) { if (Array.isArray(j)) return j; if (j && Array.isArray(j.data)) return j.data; if (j && Array.isArray(j.items)) return j.items; return []; }

// ───────────────────────── BROJ API ─────────────────────────
function key_() { var k = prop_('BROJ_API_KEY'); if (!k) throw new Error('스크립트 속성 BROJ_API_KEY 가 없습니다.'); return k; }
function call_(method, path, params, body, calls) {
  var qs = Object.keys(params || {}).map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); }).join('&');
  var url = BROJ_BASE + path + (qs ? '?' + qs : '');
  var opt = { method: method, headers: { 'API-KEY': key_(), 'Accept': 'application/json' }, muteHttpExceptions: true };
  if (body) { opt.contentType = 'application/json'; opt.payload = JSON.stringify(body); }
  for (var i = 0; i < 4; i++) {
    var res = UrlFetchApp.fetch(url, opt), code = res.getResponseCode();
    if (calls) calls.n++;
    if (code === 200) { Utilities.sleep(1100); return JSON.parse(res.getContentText()); }
    if (code === 429) { Utilities.sleep(20000); continue; }
    throw new Error('BROJ HTTP ' + code + ' ' + path + ' — ' + res.getContentText().slice(0, 200));
  }
  throw new Error('BROJ rate limit(429) 지속');
}
function fetchSales_(startDate, endDate, calls) {
  var all = [], cursor = null, pages = 0;
  do {
    var p = { start_date: startDate, end_date: endDate, page_size: 200 };
    if (cursor) p.cursor = cursor;
    var j = call_('get', '/v1/groups/' + GROUP_ID + '/sales/history/products', p, null, calls);
    all = all.concat(j.data || []);
    var pg = j.pagination || {}; cursor = pg.has_next ? pg.next_cursor : null; pages++;
  } while (cursor && pages < 40);
  return all;
}
function fetchTicketsBatch_(memberIds, calls) {
  var outp = {};
  for (var i = 0; i < memberIds.length; i += 50) {
    var j = call_('post', '/v1/groups/' + GROUP_ID + '/members/tickets', null, { member_ids: memberIds.slice(i, i + 50), include_expired: true }, calls);
    (j.data || []).forEach(function (el) { outp[el.member_id] = walkTickets_(el); });
  }
  return outp;
}
function walkTickets_(o) {
  var acc = [];
  (function walk(x) { if (!x || typeof x !== 'object') return; if (Array.isArray(x)) { x.forEach(walk); return; } if ('origin_usage_count' in x && 'trainer_name' in x) { acc.push(x); return; } Object.keys(x).forEach(function (k) { walk(x[k]); }); })(o);
  return acc;
}

// ───────────────────────── 증빙 사본 (강사 원본 시트 형식) ─────────────────────────
var P_FIRST_ROW = 7, P_LAST_ROW = 117, P_COL_KEY = 23;
function evidenceCreate_(ym, name, by) {
  if (!ym || !name) return { ok: false, error: 'month/instructor required' };
  var r = calc_(ym, name), it = r.cfg.it, m = +ym.slice(5, 7);
  if (!it['원본시트ID']) return { ok: false, error: '설정_강사.원본시트ID 없음' };
  var src = DriveApp.getFileById(String(it['원본시트ID']));
  var folderId = prop_('EVIDENCE_FOLDER_ID'), folder = folderId ? DriveApp.getFolderById(folderId) : DriveApp.getFileById(db_().getId()).getParents().next();
  var title = '〔증빙〕' + ym + ' ' + name + ' 페이롤_' + Utilities.formatDate(new Date(), TZ, 'yyyyMMdd-HHmm');
  var copy = src.makeCopy(title, folder), ss = SpreadsheetApp.openById(copy.getId());
  var tabP = m + '월P', tabS = m + '월S', shP = ss.getSheetByName(tabP), shS = ss.getSheetByName(tabS);
  if (!shP || !shS) return { ok: false, error: '원본에 ' + tabP + '/' + tabS + ' 탭 없음' };
  // 증빙 외 탭 정리(당월 P/S · 소멸명단 · DATA · 기록 가이드만 남김)
  ss.getSheets().forEach(function (s) { var n = s.getName(); if ([tabP, tabS, 'DATA', '소멸명단', '기록 가이드'].indexOf(n) < 0 && ss.getSheets().length > 1) ss.deleteSheet(s); });
  // N월P 재작성
  var n = P_LAST_ROW - P_FIRST_ROW + 1;
  shP.getRange(P_FIRST_ROW, 1, n, 9).clearContent(); shP.getRange(P_FIRST_ROW, 18, n, 1).clearContent(); shP.getRange(P_FIRST_ROW, P_COL_KEY, n, 1).clearContent();
  shP.getRange(P_FIRST_ROW, 1, n, P_COL_KEY).clearDataValidations();   // 원본 I열(회원구분) 등 드롭다운 검증이 ERP 값('WSC' 등)을 막지 않게 사본에서 해제
  var star = it['시트형식'] === '수영격자';
  var rows = r.regs.slice().sort(function (a, b) { return String(a['등록일']) < String(b['등록일']) ? -1 : 1; });
  // 원본 수식 범위 실측: J열 수식이 있는 첫 행(복사 원본) · 마지막 행(상단 합계 SUM($Q$7:$Q48) 범위 끝)
  var jF = shP.getRange(P_FIRST_ROW, 10, n, 1).getFormulas(), tplRow = 0, lastFormulaRow = 0, warnings = [], formulaFilled = 0, beyond = 0;
  for (var q = 0; q < jF.length; q++) if (jF[q][0]) { if (!tplRow) tplRow = P_FIRST_ROW + q; lastFormulaRow = P_FIRST_ROW + q; }
  if (rows.length > n) warnings.push('등록 ' + rows.length + '건 중 ' + (rows.length - n) + '건은 ' + P_LAST_ROW + '행 한도로 사본에 못 실음');
  rows.forEach(function (x, i) {
    var R = P_FIRST_ROW + i; if (R > P_LAST_ROW) return;
    shP.getRange(R, 1, 1, 9).setValues([[i + 1, star ? '*' + x['회원명'] + '*' : x['회원명'], toDate_(x['등록일']), toDate_(x['유효기간']), +x['등록회수'] || '', x._c.F, +x['결제금액'] || 0, x['등록분류'], x['회원구분']]]);
    shP.getRange(R, 3, 1, 2).setNumberFormat('yy. m. d');
    shP.getRange(R, 18).setValue('ERP ' + (x['출처'] || '') + (x['특이사항'] ? ' · ' + x['특이사항'] : '') + ((x._ovr || []).length ? ' · 보정 ' + x._ovr.map(function (o) { return o.항목 + '=' + o.값; }).join(',') : ''));
    shP.getRange(R, P_COL_KEY).setValue(x['수강권ID']);
    if (shP.getRange(R, 10).getFormula() === '') {
      if (tplRow) shP.getRange(tplRow, 10, 1, 12).copyTo(shP.getRange(R, 10, 1, 12), SpreadsheetApp.CopyPasteType.PASTE_FORMULA, false);   // 원본 수식 행 복사(형식별 J·N·O 수식 그대로)
      else shP.getRange(R, 10, 1, 12).setFormulas([rowFormulas_(R, tabS)]);
      formulaFilled++;
    }
    if (R > lastFormulaRow) beyond++;
  });
  if (beyond) warnings.push('등록 ' + beyond + '행이 원본 수식·합계 범위(' + lastFormulaRow + '행) 밖 — 상단 합계(J5 등)에 안 잡히므로 원본 서식 행 추가 필요');
  // N월S: 이름 칸 초기화 후 출석 세션 기입 (수영격자형 = 하루 2열·시간 블록 / 1열형 = 하루 1열·30분 행)
  writeGrid_(shS, r.sessions.filter(function (s) { return COUNT_STATUSES.indexOf(String(s['출석'])) >= 0; }), star);
  var url = ss.getUrl();
  tab_('증빙').appendRow(rowArr_('증빙', { '월': ym, '강사명': name, '사본파일ID': copy.getId(), 'URL': url, '생성자': by || '', '생성시각': now_(), '형식': it['시트형식'] + (warnings.length ? ' · ' + warnings.join(' / ') : '') }));
  return { ok: true, fileId: copy.getId(), url: url, name: title, rows: rows.length, sessions: r.sessions.length, formulaFilled: formulaFilled, warnings: warnings };
}
function rowFormulas_(R, tabS) {
  return [
    '=sumif(I' + R + ', "비회원", G' + R + ')*0.9 + sumif(I' + R + ', "정회원", G' + R + ') + sumif(I' + R + ', "WSC", G' + R + ') + sumif(I' + R + ', "비회원a", G' + R + ') + sumif(I' + R + ', "직원", G' + R + ') + sumif(I' + R + ', "직원가족", G' + R + ')',
    '=iferror(J' + R + '*10/110,"")', '=iferror(J' + R + '-K' + R + ',"")', '=iferror(L' + R + '/E' + R + ',"")',
    '=sumif(I' + R + ', "정회원", M' + R + ')*$H$5 + sumif(I' + R + ', "비회원", M' + R + ')*$H$5 + sumif(I' + R + ', "비회원a", M' + R + ')*$H$5 + sumif(I' + R + ', "직원", M' + R + ')*60% + sumif(I' + R + ', "직원가족", M' + R + ')*40% + sumif(I' + R + ', "WSC", M' + R + ')*$H$5',
    "=iferror(countifs('" + tabS + "'!$B$3:$BI$117, B" + R + '),"")', '=iferror(F' + R + '-O' + R + ',"")', '=iferror(N' + R + '*O' + R + ',"")',
    '', '=iferror(D' + R + '-$S$6&"일 남음","")', '=SUM(M' + R + '*O' + R + ')', '=SUM(M' + R + '*P' + R + ')'
  ];
}
function writeGrid_(shS, sessions, twoCol) {
  var S_FIRST = 3, S_LAST = Math.min(124, shS.getMaxRows()), S_COLS = Math.min(61, shS.getMaxColumns()), nRows = S_LAST - S_FIRST + 1;
  var labelDisp = shS.getRange(S_FIRST, 1, nRows, 1).getDisplayValues();
  var headerDisp = shS.getRange(2, 1, 1, S_COLS).getDisplayValues()[0];
  var colOfDay = {}; headerDisp.forEach(function (v, c) { if (c === 0) return; var d = dayOfHeader_(v); if (d !== null && colOfDay[d] === undefined) colOfDay[d] = c; });   // 0-based · A열(=today() 라벨)은 제외
  var blocks = [], maxGap = 1;
  for (var r = 0; r < nRows; r++) { var h = hourOfLabel_(labelDisp[r][0]); if (h !== null) { if (blocks.length) { blocks[blocks.length - 1].r1 = r - 1; maxGap = Math.max(maxGap, r - blocks[blocks.length - 1].r0); } blocks.push({ hour: h.h, min: h.m, r0: r, r1: nRows - 1 }); } }
  if (!blocks.length) throw new Error('N월S A열에 시간 라벨이 없습니다.');
  // 마지막 블록(21:00/21:30)은 다음 라벨이 없어 끝을 모른다 → 가장 큰 블록 크기까지, 단 A열에 다른 글자(하단 합계·수업료표 라벨)가 나오면 그 앞까지
  var last = blocks[blocks.length - 1], end = Math.min(last.r0 + maxGap - 1, nRows - 1);
  for (var rr2 = last.r0 + 1; rr2 <= end; rr2++) if (String(labelDisp[rr2][0] || '').trim() !== '') { end = rr2 - 1; break; }
  last.r1 = end;
  var lastBlockRow = last.r1;
  // 이름 칸만 초기화(날짜 열 · 시간 블록 범위) — 수업료 수식 열·하단 표는 무접촉
  Object.keys(colOfDay).forEach(function (d) { var rg = shS.getRange(S_FIRST, colOfDay[d] + 1, lastBlockRow + 1, 1); rg.clearContent(); rg.clearDataValidations(); });
  var grid = shS.getRange(S_FIRST, 1, nRows, S_COLS).getValues();
  sessions.forEach(function (s) {
    var d = +String(s['일시']).slice(8, 10), hh = +String(s['일시']).slice(11, 13), mm = +String(s['일시']).slice(14, 16);
    var c = colOfDay[d]; if (c === undefined) return;
    var blk = (twoCol ? null : blocks.filter(function (b) { return b.hour === hh && b.min === (mm < 30 ? 0 : 30); })[0]) || blocks.filter(function (b) { return b.hour === hh; })[0] || blocks[0];
    for (var rr = blk.r0; rr <= blk.r1; rr++) {
      if (String(grid[rr][c] || '') === '') {
        var rec = twoCol ? s['기록명'] : s['회원명'];
        shS.getRange(S_FIRST + rr, c + 1).setValue(rec); grid[rr][c] = rec;
        if (twoCol) { var fee = shS.getRange(S_FIRST + rr, c + 2); if (fee.getFormula() === '' && fee.getValue() === '') fee.setFormula('=IFERROR(VLOOKUP(LEFT(' + colA1_(c + 1) + (S_FIRST + rr) + ',1),$G$129:$H$144,2,0),"")'); }
        break;
      }
    }
  });
}
function hourOfLabel_(v) {
  var s = String(v || '').trim(), mm = s.match(/^(오전|오후|AM|PM)?\s*(\d{1,2})\s*:\s*(\d{2})\s*(오전|오후|AM|PM)?$/i);
  if (!mm) return null;
  var h = +mm[2], ap = (mm[1] || mm[4] || '').toUpperCase();
  if (ap === '오후' || ap === 'PM') { if (h < 12) h += 12; } else if (ap === '오전' || ap === 'AM') { if (h === 12) h = 0; }
  return { h: h, m: +mm[3] };
}
function dayOfHeader_(v) {
  var s = String(v || '').trim(), mm;
  if ((mm = s.match(/^\d{2,4}\s*[.\-\/]\s*(\d{1,2})\s*[.\-\/]\s*(\d{1,2})/))) return +mm[2];
  if ((mm = s.match(/^(\d{1,2})\s*[.\/]\s*(\d{1,2})\s*\(?/))) return +mm[2];
  return null;
}
function colA1_(c) { var s = ''; while (c > 0) { var r = (c - 1) % 26; s = String.fromCharCode(65 + r) + s; c = Math.floor((c - 1) / 26); } return s; }
