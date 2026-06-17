// 웰페리온 랜딩 페이지 추적 Apps Script v1.0
// 리틀리(litt.ly) 대체 — 클릭·문의 추적 → 시트 누적
// 시트 2개: 클릭로그 | 문의접수

// ─── 상수 ───
const LANDING_SPREADSHEET_ID = '1g9Ohmd8C_WxyvWt9EX58oEFZLiOAJ_EG7t7XteJFuGE';
const CLICK_SHEET = '클릭로그';
const INQUIRY_SHEET = '문의접수';

// 회원부 시트 (유효회원 탭)
const MEMBER_SPREADSHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
const MEMBER_SHEET = '유효회원';
const MEMBER_PHONE_COL = '휴대폰 번호';   // 회원부 전화번호 헤더
const MEMBER_DATE_COL  = '등록 일자';      // 회원부 등록일 헤더

const CLICK_HEADERS = ['id', '시각', '링크명', '링크URL', 'UTM소스', 'UTM미디엄', '리퍼러', '디바이스'];
const INQUIRY_HEADERS = ['id', '시각', '이름', '연락처', '문의유형', '내용', '유입채널', 'UTM소스', 'UTM미디엄', '상태', '메모'];

const INQUIRY_TYPES = ['투어 예약', '프로그램 문의', '멤버십 상담', '시설 안내', '기타'];

// ─── 구글폼 응답 시트 (실제 문의 — 자체폼 휴면 대체, 2026-06-05) ───
// 5채널 콘텐츠 → wellperion.com/ko/inquiry → 구글폼 작성 → 각 폼 응답시트 누적.
// 대시보드(inquiry_list·funnel_conversion)가 이 응답들을 읽어 '문의수=0' 빈틈을 메움.
// gid 기반 탭 조회(이름 변경에 강함). 컬럼은 헤더 키워드로 탐색(폼 문항 순서 변동 대비).
// ※ 여름특강(5종 하위폼)은 구조 미확정 → 추후 추가.
const FORM_SHEETS = [
  { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1902010032, type: '멤버십',     channelKeys: ['채널', '경로', '알게'] },  // '26년 신규문의' 스태프 로그(멤버십 단일출처·날짜 'YYYY. M. D'·문의채널 드롭다운). 구 폼응답탭 953023270 대체 — 폼3건이 아닌 실제 로그 집계(2026-06-13 GM 확인)
  { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 111889422, type: '성인강습',   channelKeys: ['경로', '채널'] },
  { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 268994754, type: '유소년강습', channelKeys: ['경로', '채널'] }
  // ─── 신규 2종 틀 (시모·GM 2026-06-12 승인 — 공간 렌트·비즈니스 파트너) ───
  // ★ 준비중: GM이 구글폼 2개 생성 후 ① ssId=실제 응답 스프레드시트 ID ② gid='__GID__'→실제 응답탭 gid(숫자)
  //   로 교체하고, 아래 두 줄 앞의 주석(//)을 풀어 활성화한다.
  //   ⚠️ gid 가 문자열 '__GID__' 인 상태에서는 _sheetByGid_ 매칭(=== 숫자 비교)이 실패 → 자동 스킵(무중단).
  //   ⚠️ clasp push ≠ 웹앱 배포 — gid 교체 후 새 버전 웹앱 재배포 1회(GM/CTO) 필요. (명세: 문의_신규유형_폼설계_260612.md §5)
  , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 2014877540, type: '공간렌트',       channelKeys: ['경로', '채널', '알게'] }  // 2026-06-15 멤버십 시트로 통합(설문지 응답 시트12)
  , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1356708303, type: '비즈니스파트너', channelKeys: ['경로', '채널', '알게'] }  // 2026-06-15 멤버십 시트로 통합(설문지 응답 시트13)
];

// 강습 '팀 정리' 스프레드시트 (통합본 → 팀별 별도 시트로 재취합, 팀장이 등록/실패/컨택중 처리). 수강등록 전환 정본.
// 통합본(1b0XU1) 종목탭은 중간 분배본이라 등록상태 없음 → 팀별 스프레드시트가 정본(2026-06-16 GM 링크).
var _LESSON_DEBUG = [];  // 진단: 팀시트별 상태칼럼·표본값·등록수 (응답 lessonDebug)
var LESSON_TEAM_SHEETS = [
  { ssId: '1mRTWBoR7UJeJSJIW9ZDxfK0ZFc14AaBNR_CpfLEsd-E', gid: 1063990264, 유형: '성인강습',   명: 'P.T 성인' },
  { ssId: '1mRTWBoR7UJeJSJIW9ZDxfK0ZFc14AaBNR_CpfLEsd-E', gid: 1328034138, 유형: '유소년강습', 명: 'P.T 유소년' },
  { ssId: '1NbML3Jp84HAa2yxnuc8MyHundDOzhroYZ7OIG6Ot7gM', gid: 230929728,  유형: '성인강습',   명: '필라테스 성인' },
  { ssId: '1NbML3Jp84HAa2yxnuc8MyHundDOzhroYZ7OIG6Ot7gM', gid: 754969527,  유형: '유소년강습', 명: '필라테스 유소년' },
  { ssId: '1vH9To5zglQAVq0W653sv6G7DkUXftxEfaHh3KI6CMYk', gid: 1063990264, 유형: '성인강습',   명: '스쿼시 성인' },
  { ssId: '1vH9To5zglQAVq0W653sv6G7DkUXftxEfaHh3KI6CMYk', gid: 1328034138, 유형: '유소년강습', 명: '스쿼시 유소년' },
  { ssId: '1-Ubck9WiScv26qlvxy1W2RCTctEg_TTxQLnko_OJV4o', gid: 1063990264, 유형: '성인강습',   명: '골프 성인' },
  { ssId: '1-Ubck9WiScv26qlvxy1W2RCTctEg_TTxQLnko_OJV4o', gid: 1328034138, 유형: '유소년강습', 명: '골프 유소년' },
  { ssId: '10rjNd5w8NunuA3EZXv1-4vlDfCqxnOnoVrq8U9Md69E', gid: 1063990264, 유형: '성인강습',   명: '수영 성인' },
  { ssId: '10rjNd5w8NunuA3EZXv1-4vlDfCqxnOnoVrq8U9Md69E', gid: 1328034138, 유형: '유소년강습', 명: '수영 유소년' },
  { ssId: '10rjNd5w8NunuA3EZXv1-4vlDfCqxnOnoVrq8U9Md69E', gid: 1219410707, 유형: '유소년강습', 명: '모자수영' },
  { ssId: '10rjNd5w8NunuA3EZXv1-4vlDfCqxnOnoVrq8U9Md69E', gid: 1214469613, 유형: '성인강습',   명: '아쿠아로빅' },
  { ssId: '1ZqsKzM6DyJpN3brxqwsP8sW9pACbFmWxZ0JCUHthkcs', gid: 1063990264, 유형: '유소년강습', 명: '유소년체조' }
];

function _sheetByGid_(ssId, gid) {
  var sheets = SpreadsheetApp.openById(ssId).getSheets();
  for (var i = 0; i < sheets.length; i++) { if (sheets[i].getSheetId() === gid) return sheets[i]; }
  return null;
}

function _findCol_(headers, keys) {
  for (var i = 0; i < headers.length; i++) {
    var h = String(headers[i] || '');
    for (var k = 0; k < keys.length; k++) { if (h.indexOf(keys[k]) >= 0) return i; }
  }
  return -1;
}

// ─── 유입채널 표준화 (시모·GM 2026-06-13 확정 — 마케팅용 10버킷) ───
// 자유텍스트(과거 리셉션 + 구글폼 자유입력)로 300여 개 난립한 채널 원문을 표준 10종으로 정규화한다.
// 비파괴: 시트 원본은 손대지 않고, 대시보드 집계(byChannel/byChannelMonth) '읽기 시점'에만 적용.
// ⚠️ 과거 리셉션이 '온라인 (네이버/동커/카카오/인스타)'로 뭉뚱그린 묶음(약 26%)은 단일 채널 귀속이 불가능
//    → '기타·미상'으로 보존(날조 금지). 채널별 ROI는 구글폼 드롭다운(Layer B) 이후 신규 데이터부터 정확해진다.
var CANONICAL_CHANNELS = ['네이버', '동부이촌동 커뮤니티', '인스타그램', '카카오톡', '당근마켓',
                          '소개·지인', '기존·과거 회원', '오프라인', '유선전화', '기타·미상'];

function _canonicalChannel_(raw) {
  var s = String(raw == null ? '' : raw).trim();
  if (!s) return '기타·미상';
  // 과거 '온라인 (...)' 묶음 = 다채널 합산 → 단일 귀속 불가
  if (/^온라인\s*[\(（]/.test(s)) return '기타·미상';
  if (/인스타|instagram|insta/i.test(s)) return '인스타그램';
  if (/카카오|카톡|챗톡|쳇톡|챗봇|쳇봇|kakao/i.test(s)) return '카카오톡';
  if (/당근|daangn/i.test(s)) return '당근마켓';
  if (/동부이촌동|동커|동\.커|이촌동|카페/.test(s)) return '동부이촌동 커뮤니티';
  if (/네이버|naver|플레이스|블로그|블러그|검색|인터넷/i.test(s)) return '네이버';  // '지도' 단독 제외('인지도' 오탐 방지·네이버지도는 '네이버'로 포착)
  if (/소개|지인|친구|friend|추천|동기/i.test(s)) return '소개·지인';
  if (/회원|가족|자녀|아이|아들|딸|형|누나|언니|동생|둘째|첫째|보호자|학부모|부모|母|수강|강습|다녔|다니|이용|경험|기존|과거|재수강|정회원|연회원|멤버십회원|멤버쉽|wsc|준회원|수강생/i.test(s)) return '기존·과거 회원';
  if (/전화|유선|통화|문자/.test(s)) return '유선전화';
  if (/간판|현수막|홍보물|우편|워크인|방문|지나가|지나는|집근처|근처|동네|거주|입주|하이페리온|길에|봤|보여서|아파트|오프라인/.test(s)) return '오프라인';
  return '기타·미상';
}

// ─── 진행상태 → 전환 단계 rank 매핑 (설계 SSOT 2026-06-15) ───
// 0=이탈, 1=문의(기본), 2=응대, 3=예약, 4=방문, 5=가입
function _stageOf_(raw) {
  var s = String(raw == null ? '' : raw).trim();
  if (!s) return 1; // 빈칸 → 최소단계(①문의)
  if (/이탈|보류|포기|거절|취소|loss/i.test(s)) return 0;
  // SUC / 단기SUC = 수강등록 성공(강습 팀시트 정본값) → 가입(5)
  if (/^(suc|단기\s*suc)$/i.test(s))            return 5;
  if (/가입|등록|전환|회원/.test(s))             return 5;
  if (/방문|내방|방문완료/.test(s))              return 4;
  if (/예약|투어|상담/.test(s))                  return 3;
  if (/응대|연락|통화|문자|회신/.test(s))        return 2;
  if (/신규|접수/.test(s))                       return 1;
  return 1; // 미인식 → ① 문의(안전 처리)
}

// 날짜 정규화 — 구글폼(Date 또는 'YYYY-MM-DD HH:mm:ss') + 수기 로그('YYYY. M. D [오전/오후 H:MM:SS]') 모두 Date로.
// '26년 신규문의' 탭 타임스탬프가 한글 형식(예: 2026. 6. 5)이라 기존 ISO 파서로는 NaN → 여기서 Date로 변환.
function _parseAnyDate_(v) {
  if (v instanceof Date) return v;
  var s = String(v || '').trim();
  if (!s) return v;
  var m = s.match(/^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/);   // 2026. 6. 5  /  2026. 6. 5 오후 3:27:41
  if (m) {
    var mm = ('0' + m[2]).slice(-2), dd = ('0' + m[3]).slice(-2);
    return new Date(m[1] + '-' + mm + '-' + dd + 'T12:00:00+09:00');  // 정오 고정 — 일 경계 TZ 오차 방지
  }
  return v;  // ISO 등 그 외 형식은 원형 유지(하류 _toDate_/_countByPeriod_가 처리)
}

// 구글폼/스태프 로그 응답 → 정규화 문의 배열 {시각, 연락처, 유입채널, 문의유형}. 접근 실패 시트는 건너뜀.
function _collectFormInquiries_() {
  var out = [];
  FORM_SHEETS.forEach(function(cfg) {
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) return;
      var last = sh.getLastRow();
      var lastCol = sh.getLastColumn();
      if (last < 2 || lastCol < 1) return;
      var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
      var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화']);
      var idxChan  = _findCol_(headers, cfg.channelKeys);          // 대분류(문의 채널) — 폴백 기준
      var idxChanFine = _findCol_(headers, ['중분류']);             // 문의 경로(중분류) — 정밀(있을 때만, 멤버십 탭)
      var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
      if (idxDate < 0) idxDate = 0;  // 못 찾으면 1열(구글폼 기본). 26년신규문의=B칸(타임스탬프) 자동 포착
      var rows = sh.getRange(2, 1, last - 1, lastCol).getValues();
      rows.forEach(function(r) {
        if (!r[idxDate] && (idxPhone < 0 || !r[idxPhone])) return; // 빈 행 스킵
        // 채널 = 대분류 기본, 단 중분류가 '확실한 버킷'으로 표준화될 때만 중분류 우선(회귀 방지).
        // 예) 대분류 '온라인 (네이버/…/당근)'→기타·미상 이지만 중분류 'N-플레이스(검색)'→네이버 로 정밀화.
        //     중분류가 매핑 불가('옥외홍보' 등)면 대분류 유지 → 절대 후퇴 없음.
        var chanRaw = (idxChan >= 0 ? String(r[idxChan] || '').trim() : '');
        if (idxChanFine >= 0) {
          var midRaw = String(r[idxChanFine] || '').trim();
          if (midRaw && _canonicalChannel_(midRaw) !== '기타·미상') chanRaw = midRaw;
        }
        out.push({
          시각:     _parseAnyDate_(r[idxDate]),  // 타임스탬프(구글폼 A칸 Date / 26년신규문의 B칸 'YYYY. M. D')
          연락처:   idxPhone >= 0 ? r[idxPhone] : '',
          유입채널: chanRaw || '기타',
          문의유형: cfg.type
        });
      });
    } catch (e) { /* 폼 시트 접근 실패는 무시(대시보드 무중단) */ }
  });
  return out;
}

// 강습 종목별 팀시트(importrange 분배본) → 수강등록 전환 분자 집계. 접근 실패/빈 시트는 건너뜀(대시보드 무중단).
// ⚠️ 종목시트 행은 '문의 total'에 더하지 않는다(통합본과 중복). 여기선 '등록' 카운트(rank===5)만 산출.
// 반환: { '성인강습': {registered, channels:{채널:{registered}}}, '유소년강습': {...} } (config 유형으로 합산)
// 강습 '구조화 상태값' 판정 — 짧은 코드형 상태만(자유메모 배제). 스쿼시=SUC/LOSS/가망/컨택중 포함.
function _isLessonStatusVal_(v) {
  var s = String(v == null ? '' : v).trim();
  if (!s || s.length > 15) return false;  // 자유메모(긴 문장) 배제
  return /^(등록|등록완료|미등록|실패|컨택중|컨택|대기|보류|취소|환불|가망|상담중|상담|suc|단기\s*suc|loss|성공)$/i.test(s);
}
function _isLessonReg_(v) {
  var s = String(v == null ? '' : v).trim();
  if (s.length > 15) return false;  // 자유메모 배제(노이즈)
  if (/미등록|등록취소|취소|환불|대기|보류|불가|loss|가망|컨택/i.test(s)) return false;
  return /^(등록|등록완료|suc|단기\s*suc|성공)$/i.test(s);  // 구조화 성공값만 (단기SUC 포함)
}

// 강습 수강등록 집계 — 팀별 정리시트에서 상태열을 '값'으로 탐지(등록/실패/컨택중 최다 열) 후 '등록' 카운트.
function _collectLessonRegistrations_() {
  var out = {};
  _LESSON_DEBUG = [];
  LESSON_TEAM_SHEETS.forEach(function(cfg) {
    var dbg = { 명: cfg.명, gid: cfg.gid, statusHeader: '(미발견)', statusHits: 0, rows: 0, registered: 0, 표본: [] };
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) { dbg.statusHeader = '(시트 미발견)'; _LESSON_DEBUG.push(dbg); return; }
      var last = sh.getLastRow();
      var lastCol = sh.getLastColumn();
      dbg.rows = Math.max(0, last - 1);
      if (last < 2 || lastCol < 1) { _LESSON_DEBUG.push(dbg); return; }
      var data = sh.getRange(1, 1, last, lastCol).getValues();
      var headers = data[0];
      dbg.headers = headers.map(function(h) { return String(h || ''); }).slice(0, 20);
      var idxChan = _findCol_(headers, ['경로', '채널', '알게', '중분류']);
      // 구조화 상태열만 탐지 — 고유값 2~30(자유메모=고유값 수백 → 배제) + 코드형 상태값 최다 열
      var best = -1, bestCnt = 0;
      for (var c = 0; c < lastCol; c++) {
        var cnt = 0, distinct = {}, dn = 0;
        for (var r = 1; r < data.length; r++) {
          var cv = String(data[r][c] || '').trim();
          if (!cv) continue;
          if (!distinct[cv]) { distinct[cv] = 1; dn++; }
          if (_isLessonStatusVal_(cv)) cnt++;
        }
        if (dn >= 2 && dn <= 30 && cnt > bestCnt) { bestCnt = cnt; best = c; }
      }
      dbg.statusHits = bestCnt;
      dbg.statusHeader = best >= 0 ? String(headers[best] || '') : '(상태값 없음)';
      if (best < 0) { _LESSON_DEBUG.push(dbg); return; }
      var tp = cfg.유형;
      if (!out[tp]) out[tp] = { registered: 0, channels: {} };
      var O = out[tp];
      var seen = {};
      for (var r2 = 1; r2 < data.length; r2++) {
        var sv = String(data[r2][best] || '').trim();
        if (sv && !seen[sv] && dbg.표본.length < 10) { seen[sv] = 1; dbg.표본.push(sv); }
        if (!_isLessonReg_(data[r2][best])) continue;
        var ch = _canonicalChannel_(idxChan >= 0 ? data[r2][idxChan] : '');
        O.registered++; dbg.registered++;
        if (!O.channels[ch]) O.channels[ch] = { registered: 0 };
        O.channels[ch].registered++;
      }
    } catch (e) { dbg.error = String(e); }
    _LESSON_DEBUG.push(dbg);
  });
  return out;
}

// ─── 시트 초기화 ───
function _getSheet(name, headers) {
  const ss = SpreadsheetApp.openById(LANDING_SPREADSHEET_ID);
  let sh = ss.getSheetByName(name);
  if (sh) return sh;

  sh = ss.insertSheet(name);
  sh.getRange(1, 1, 1, headers.length).setValues([headers]);
  sh.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#2a2725')
    .setFontColor('#B79F8A');
  sh.setFrozenRows(1);
  return sh;
}

function initSheets() {
  _getSheet(CLICK_SHEET, CLICK_HEADERS);
  _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
  return 'OK';
}

// ─── 유틸 ───
function _now() { return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'); }
function _genId(prefix) {
  return prefix + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyyMMddHHmmss')
    + ('000' + new Date().getMilliseconds()).slice(-3);
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function _prop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

// 전화번호 정규화 — 숫자만 추출, 국가코드 82→0 치환, 빈값→''
function normalizePhone_(s) {
  if (!s) return '';
  var digits = String(s).replace(/\D/g, '');
  if (digits.length >= 11 && digits.slice(0, 2) === '82') {
    digits = '0' + digits.slice(2);
  }
  return digits;
}

function _notifyTelegram(text) {
  const token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  const chatId = _prop('CHAT_ID') || _prop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return;
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
  } catch (e) { Logger.log('텔레그램 실패: ' + e.message); }
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
var _SURVEY_PUBLIC_ACTIONS = {
  submit_inquiry: true,  // 방문자 문의 제출 — 토큰 면제
  track_click:    true   // 클릭 추적 — 토큰 면제
  // 그 외 inquiry_list / click_stats / funnel_conversion / period_breakdown /
  // type_channel_breakdown / stage_funnel / weekly_trend 는 게이트 적용.
};
function _accessProp_(k) {
  try { return PropertiesService.getScriptProperties().getProperty(k) || ''; } catch (e) { return ''; }
}
function _checkSurveyAccess_(action, key) {
  if (_SURVEY_PUBLIC_ACTIONS[action]) return true;           // 공개 액션은 항상 통과
  if (_accessProp_('TOKEN_ENFORCE') !== '1') return true;    // 스위치 OFF(기본) = 현행 무중단
  var tok = _accessProp_('ACCESS_TOKEN');
  if (!tok) return true;                                     // 토큰 미설정 = 안전을 위해 통과
  return String(key || '') === tok;
}

// ═══════════════════════════════════════════
//  액션 처리
// ═══════════════════════════════════════════
function _processAction(body) {
  const action = body.action || '';

  // ─── 접근 게이트 확인 ───
  if (!_checkSurveyAccess_(action, body.key)) {
    return _json({ ok: false, error: 'unauthorized' });
  }

  // ─── 클릭 추적 ───
  if (action === 'track_click') {
    const sh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    const row = [
      _genId('CLK-'),
      _now(),
      body.linkName || '',
      body.linkUrl || '',
      body.utmSource || '',
      body.utmMedium || '',
      body.referrer || '',
      body.device || ''
    ];
    sh.getRange(sh.getLastRow() + 1, 1, 1, row.length).setValues([row]);
    return _json({ ok: true });
  }

  // ─── 문의 접수 ───
  if (action === 'submit_inquiry') {
    const sh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    const id = _genId('INQ-');
    const row = [
      id,
      _now(),
      body.name || '',
      body.phone || '',
      body.type || '기타',
      body.message || '',
      body.inflow || '',
      body.utmSource || '',
      body.utmMedium || '',
      '신규',
      ''
    ];
    sh.getRange(sh.getLastRow() + 1, 1, 1, row.length).setValues([row]);

    _notifyTelegram(
      '🔔 <b>[신규 문의]</b>\n'
      + '이름: ' + (body.name || '-') + '\n'
      + '연락처: ' + (body.phone || '-') + '\n'
      + '유형: ' + (body.type || '-') + '\n'
      + '유입채널: ' + (body.inflow || '-') + '\n'
      + '내용: ' + (body.message || '-').substring(0, 100)
    );

    return _json({ ok: true, id: id, message: '문의가 접수되었습니다.' });
  }

  // ─── 클릭 통계 ───
  if (action === 'click_stats') {
    var csFrom = body.from || '';   // YYYY-MM-DD (optional) — 기간 필터
    var csTo   = body.to   || '';
    // 캐시 조회 (cs_v3 — from/to 기간 필터 버전, 범위별 키)
    var csCache = CacheService.getScriptCache();
    var csCacheKey = 'cs_v3_' + csFrom + '_' + csTo;
    var csHit = csCache.get(csCacheKey);
    if (csHit) return _json(JSON.parse(csHit));

    const sh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    const last = sh.getLastRow();
    if (last < 2) return _json({ ok: true, total: 0, byLink: {}, byLinkUrl: {}, byUtmSource: {}, from: csFrom, to: csTo });

    var data = sh.getRange(2, 1, last - 1, CLICK_HEADERS.length).getValues();
    // 기간 필터 (from/to 둘 다 있을 때만 · 시각=인덱스 1). 없으면 누적.
    if (csFrom && csTo) {
      var csF = new Date(csFrom + 'T00:00:00+09:00').getTime();
      var csT = new Date(csTo + 'T23:59:59+09:00').getTime();
      data = data.filter(function(row) {
        var t = row[1] ? new Date(row[1]).getTime() : NaN;
        return !isNaN(t) && t >= csF && t <= csT;
      });
    }
    const byLink = {};
    const byLinkUrl = {};  // 링크명 → 가장 최근 링크URL (대시보드 '↗ 보기' 링크 + litt.ly 등 출처 확인용)
    const byUtmSource = {};  // UTM 소스별 클릭 건수 집계
    data.forEach(function(row) {
      var name = row[2] || '기타';
      byLink[name] = (byLink[name] || 0) + 1;
      if (row[3]) byLinkUrl[name] = row[3];

      // UTM 소스 집계 (인덱스 4): 'homepage' 또는 빈값 → '직접/홈', 그 외는 원문 그대로
      var utmRaw = String(row[4] || '').trim();
      var utmKey = (!utmRaw || utmRaw === 'homepage') ? '직접/홈' : utmRaw;
      byUtmSource[utmKey] = (byUtmSource[utmKey] || 0) + 1;
    });

    var csResult = { ok: true, total: data.length, byLink: byLink, byLinkUrl: byLinkUrl, byUtmSource: byUtmSource, from: csFrom, to: csTo };
    try { csCache.put(csCacheKey, JSON.stringify(csResult), 300); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(csResult);
  }

  // ─── 문의 목록 ───
  if (action === 'inquiry_list') {
    const sh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    const last = sh.getLastRow();
    const items = [];
    if (last >= 2) {
      const data = sh.getRange(2, 1, last - 1, INQUIRY_HEADERS.length).getValues();
      data.forEach(row => {
        const obj = {};
        INQUIRY_HEADERS.forEach((h, i) => { obj[h] = row[i]; });
        items.push(obj);
      });
    }
    // 구글폼 문의 합류 (개인정보 제외 — 시각·유형·채널만 노출)
    _collectFormInquiries_().forEach(function(f) {
      items.push({ id: '', 시각: f.시각, 이름: '', 연락처: '', 문의유형: f.문의유형, 내용: '', 유입채널: f.유입채널, 상태: '신규', 메모: '구글폼' });
    });
    return _json({ ok: true, count: items.length, data: items });
  }

  // ─── 문의→가입 전환 집계 ───
  if (action === 'funnel_conversion') {
    // 캐시 조회
    var fcCache = CacheService.getScriptCache();
    var fcHit = fcCache.get('fc_v1');
    if (fcHit) return _json(JSON.parse(fcHit));

    // ① 회원부 전화번호 Set 생성
    var memberSs  = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var memberSh  = memberSs.getSheetByName(MEMBER_SHEET);
    var memberLast = memberSh.getLastRow();
    var memberSet = {};
    if (memberLast >= 2) {
      var memberHeaders = memberSh.getRange(1, 1, 1, memberSh.getLastColumn()).getValues()[0];
      var phoneColIdx   = memberHeaders.indexOf(MEMBER_PHONE_COL);
      if (phoneColIdx >= 0) {
        var memberPhones = memberSh.getRange(2, phoneColIdx + 1, memberLast - 1, 1).getValues();
        memberPhones.forEach(function(r) {
          var n = normalizePhone_(r[0]);
          if (n) memberSet[n] = true;
        });
      }
    }

    // ② 문의접수 시트 집계
    var inqSh   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var inqLast = inqSh.getLastRow();
    var totalInq = 0, totalConv = 0;
    var byChannel = {};  // { 채널명: {inquiries, converted} }

    if (inqLast >= 2) {
      var inqData = inqSh.getRange(2, 1, inqLast - 1, INQUIRY_HEADERS.length).getValues();
      // 헤더 인덱스
      var idxPhone   = INQUIRY_HEADERS.indexOf('연락처');   // 3
      var idxChannel = INQUIRY_HEADERS.indexOf('유입채널'); // 6

      inqData.forEach(function(row) {
        var phone   = normalizePhone_(row[idxPhone]);
        var channel = _canonicalChannel_(row[idxChannel]);

        totalInq++;
        if (!byChannel[channel]) byChannel[channel] = { inquiries: 0, converted: 0 };
        byChannel[channel].inquiries++;

        if (phone && memberSet[phone]) {
          totalConv++;
          byChannel[channel].converted++;
        }
      });
    }

    // ②-b 구글폼 응답 문의 합류 (실제 문의 — 자체폼 휴면 대체, 2026-06-05)
    _collectFormInquiries_().forEach(function(f) {
      var phone   = normalizePhone_(f.연락처);
      var channel = _canonicalChannel_(f.유입채널);
      totalInq++;
      if (!byChannel[channel]) byChannel[channel] = { inquiries: 0, converted: 0 };
      byChannel[channel].inquiries++;
      if (phone && memberSet[phone]) { totalConv++; byChannel[channel].converted++; }
    });

    // ③ 반환 JSON — 집계 수치만, 개인정보 절대 미포함
    var rate = totalInq > 0 ? Math.round((totalConv / totalInq) * 1000) / 10 : 0;
    var channelArr = Object.keys(byChannel).map(function(ch) {
      var d = byChannel[ch];
      return {
        channel:   ch,
        inquiries: d.inquiries,
        converted: d.converted,
        rate:      d.inquiries > 0 ? Math.round((d.converted / d.inquiries) * 1000) / 10 : 0
      };
    });
    channelArr.sort(function(a, b) { return b.inquiries - a.inquiries; });

    var fcResult = {
      ok: true,
      total: { inquiries: totalInq, converted: totalConv, rate: rate },
      byChannel: channelArr,
      generatedAt: _now()
    };
    // 캐시 저장 (100KB 초과 시 생략)
    try { fcCache.put('fc_v1', JSON.stringify(fcResult), 300); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(fcResult);
  }

  // ─── 유형×채널×등록 교차 집계 (마케팅 대시보드 고도화 2026-06-16) ───
  // 멤버십·성인강습·유소년 각각 어느 채널로 문의가 들어와 등록(전환)까지 갔는지 매트릭스.
  // 전환 기준 = 멤버십·기타는 유효회원 전화매칭 / 강습은 종목별 팀시트 '등록'(정본).
  // 출처미상률 = '기타·미상' 비율(문의 시점 채널 미캡처 가시화 — INC-003 정직성, 날조 금지).
  if (action === 'type_channel_breakdown') {
    var tcFrom = body.from || '';   // YYYY-MM-DD (optional) — 문의 날짜 기간 필터
    var tcTo   = body.to   || '';
    var tcCache = CacheService.getScriptCache();
    var tcCacheKey = 'tc_v5_' + tcFrom + '_' + tcTo;
    var tcHit = tcCache.get(tcCacheKey);
    if (tcHit) return _json(JSON.parse(tcHit));

    // 회원부 전화 Set (유효회원 = 멤버십 등록 정본). 시트 미발견 시 빈 Set로 계속(throw 금지 — funnel_conversion 동일 패턴).
    var tcMemberSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    var tcMemberSet = {};
    if (tcMemberSh) {
      var tcML = tcMemberSh.getLastRow();
      if (tcML >= 2) {
        var tcMH = tcMemberSh.getRange(1, 1, 1, tcMemberSh.getLastColumn()).getValues()[0];
        var tcPI = tcMH.indexOf(MEMBER_PHONE_COL);
        if (tcPI >= 0) {
          tcMemberSh.getRange(2, tcPI + 1, tcML - 1, 1).getValues().forEach(function(r) {
            var n = normalizePhone_(r[0]); if (n) tcMemberSet[n] = true;
          });
        }
      }
    }

    // 문의 수집: 문의접수 시트 + 구글폼/로그(유형 포함). (정규화전화+유형) 키로 dedup — 양쪽 중복 1건만(전화 빈값은 각각 카운트).
    var tcRows = []; // {유형, 채널, 연락처, 시각}
    var tcSeen = {};
    function _tcPush_(유형, 채널raw, 연락처, 시각) {
      var tp = String(유형 || '기타').trim() || '기타';
      var ph = normalizePhone_(연락처);
      if (ph) {
        var key = ph + '|' + tp;
        if (tcSeen[key]) return; // 같은 전화+유형 중복 제거
        tcSeen[key] = true;
      }
      tcRows.push({ 유형: tp, 채널: _canonicalChannel_(채널raw), 연락처: 연락처, 시각: 시각 });
    }
    var tcInqSh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var tcIL = tcInqSh.getLastRow();
    if (tcIL >= 2) {
      var tcID = tcInqSh.getRange(2, 1, tcIL - 1, INQUIRY_HEADERS.length).getValues();
      var tcChI = INQUIRY_HEADERS.indexOf('유입채널');
      var tcTpI = INQUIRY_HEADERS.indexOf('문의유형');
      var tcPhI = INQUIRY_HEADERS.indexOf('연락처');
      var tcDtI = INQUIRY_HEADERS.indexOf('시각');
      tcID.forEach(function(r) {
        _tcPush_(r[tcTpI], r[tcChI], r[tcPhI], _parseAnyDate_(r[tcDtI]));
      });
    }
    _collectFormInquiries_().forEach(function(f) {
      _tcPush_(f.문의유형, f.유입채널, f.연락처, f.시각);
    });

    // periodMode: from/to 둘 다 있으면 '문의'는 기간뷰, '등록(전환)'은 누적(등록일 데이터 없음 → 기간 산출 불가).
    var tcPeriod = !!(tcFrom && tcTo);
    var tcF = tcPeriod ? new Date(tcFrom + 'T00:00:00+09:00').getTime() : 0;
    var tcT = tcPeriod ? new Date(tcTo + 'T23:59:59+09:00').getTime() : 0;
    function _tcInPeriod(row) {
      if (!tcPeriod) return true;
      var t = (row.시각 instanceof Date) ? row.시각.getTime() : (row.시각 ? new Date(row.시각).getTime() : NaN);
      return !isNaN(t) && t >= tcF && t <= tcT;
    }

    // 강습 수강등록 정본(종목별 팀시트) — 강습 유형 전환 분자로 사용(누적)
    var tcLessons = _collectLessonRegistrations_();

    // 집계: 문의(total/inquiries/unknown)=기간뷰 · 등록(memberMatched)=누적(전체 기간, 기간 무관)
    var tcTypes = {};
    tcRows.forEach(function(row) {
      var tp = row.유형, ch = row.채널;
      if (!tcTypes[tp]) tcTypes[tp] = { total: 0, memberMatched: 0, unknown: 0, channels: {} };
      var T = tcTypes[tp];
      if (!T.channels[ch]) T.channels[ch] = { inquiries: 0, memberMatched: 0 };
      var phone = normalizePhone_(row.연락처);
      if (phone && tcMemberSet[phone]) { T.memberMatched++; T.channels[ch].memberMatched++; }  // 등록=누적
      if (_tcInPeriod(row)) {  // 문의=기간뷰
        T.total++;
        if (ch === '기타·미상') T.unknown++;
        T.channels[ch].inquiries++;
      }
    });

    // 강습 유형은 종목시트 '등록'을 전환 정본으로 사용(문의 total엔 미가산 — 분자만 대체)
    function _isLesson_(tp) { return tp === '성인강습' || tp === '유소년강습'; }
    function _lessonChanReg_(tp, ch) {
      var L = tcLessons[tp];
      if (!L || !L.channels[ch]) return 0;
      return L.channels[ch].registered;
    }

    var tcOut = {};
    var ovTotal = 0, ovConverted = 0, ovUnknown = 0;
    Object.keys(tcTypes).forEach(function(tp) {
      var T = tcTypes[tp];
      var lesson = _isLesson_(tp);
      var lessonReg = (tcLessons[tp] && tcLessons[tp].registered) || 0;
      var converted = lesson ? lessonReg : T.memberMatched; // 강습=종목시트 등록 / 그 외=유효회원 매칭
      ovTotal += T.total; ovConverted += converted; ovUnknown += T.unknown;
      var chArr = Object.keys(T.channels).map(function(ch) {
        var c = T.channels[ch];
        var chConv = lesson ? _lessonChanReg_(tp, ch) : c.memberMatched;
        return { channel: ch, inquiries: c.inquiries,
                 memberMatched: c.memberMatched, // 하위호환 유지
                 converted: chConv,
                 rate: tcPeriod ? null : (c.inquiries > 0 ? Math.round((chConv / c.inquiries) * 1000) / 10 : 0) };
      });
      chArr.sort(function(a, b) { return b.inquiries - a.inquiries; });
      tcOut[tp] = {
        total: T.total,
        memberMatched: T.memberMatched, // 하위호환 유지
        rate: tcPeriod ? null : (T.total > 0 ? Math.round((T.memberMatched / T.total) * 1000) / 10 : 0), // 하위호환 유지
        converted: converted,
        convRate: tcPeriod ? null : (T.total > 0 ? Math.round((converted / T.total) * 1000) / 10 : 0),
        convSource: lesson ? '종목시트 수강등록' : '유효회원 매칭',
        unknownChannel: T.unknown,
        unknownRate: T.total > 0 ? Math.round((T.unknown / T.total) * 1000) / 10 : 0,
        channels: chArr
      };
    });

    var tcResult = {
      ok: true,
      generatedAt: _now(),
      periodMode: tcPeriod,
      period: { from: tcFrom, to: tcTo },
      convBasis: tcPeriod
        ? '문의·교차=선택기간 / 등록(전환)=누적(등록일 데이터 없음 → 기간 무관) · 전환율은 기간선택 시 숨김(분모·분자 시점 불일치)'
        : '멤버십=유효회원 매칭 / 강습=종목별 팀시트 수강등록(등록/실패/컨택중) 집계',
      lessonDebug: _LESSON_DEBUG,
      types: tcOut,
      overall: {
        total: ovTotal,
        converted: ovConverted,
        convRate: ovTotal > 0 ? Math.round((ovConverted / ovTotal) * 1000) / 10 : 0,
        unknownChannel: ovUnknown,
        unknownRate: ovTotal > 0 ? Math.round((ovUnknown / ovTotal) * 1000) / 10 : 0
      }
    };
    try { tcCache.put(tcCacheKey, JSON.stringify(tcResult), 300); } catch (e) { /* 캐시 실패 무시 */ }
    return _json(tcResult);
  }

  // ─── 기간별 집계 (일/주/월 + custom range) ───
  if (action === 'period_breakdown') {
    var from = body.from || '';  // YYYY-MM-DD (optional)
    var to   = body.to   || '';  // YYYY-MM-DD (optional)

    // 캐시 조회
    var pbCache = CacheService.getScriptCache();
    var pbKey   = 'pb_' + from + '_' + to;
    var pbHit   = pbCache.get(pbKey);
    if (pbHit) return _json(JSON.parse(pbHit));

    // ── 기간 시작 시각 계산 (Asia/Seoul 달력 기준) ──
    function _periodStarts_() {
      var now = new Date();
      // Seoul 현지 날짜·요일 문자열로 기준점 산출
      var seoulNowStr = Utilities.formatDate(now, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      var todayStr    = seoulNowStr.substring(0, 10); // 'yyyy-MM-dd'

      // 이번 주 월요일 계산 (Asia/Seoul 기준 요일)
      var dow = parseInt(Utilities.formatDate(now, 'Asia/Seoul', 'u'), 10); // 1=월 … 7=일
      var daysSinceMonday = dow - 1;
      var monDate = new Date(now.getTime() - daysSinceMonday * 86400000);
      var weekStr = Utilities.formatDate(monDate, 'Asia/Seoul', 'yyyy-MM-dd');

      // 이번 달 1일
      var monthStr = todayStr.substring(0, 7) + '-01';

      // Date 객체 (ISO 8601 +09:00 파싱)
      var dayStart   = new Date(todayStr  + 'T00:00:00+09:00');
      var weekStart  = new Date(weekStr   + 'T00:00:00+09:00');
      var monthStart = new Date(monthStr  + 'T00:00:00+09:00');

      return { dayStart: dayStart, weekStart: weekStart, monthStart: monthStart,
               dayStr: todayStr, weekStr: weekStr, monthStr: monthStr };
    }

    // 타임스탬프 배열(Date|string) → {day, week, month} 카운트
    function _countByPeriod_(timestamps, ps) {
      var day = 0, week = 0, month = 0;
      timestamps.forEach(function(ts) {
        var d;
        if (ts instanceof Date) {
          d = ts;
        } else {
          var s = String(ts).trim();
          // 'yyyy-MM-dd HH:mm:ss' → ISO
          d = new Date(s.replace(' ', 'T') + '+09:00');
        }
        if (isNaN(d.getTime())) return;
        if (d >= ps.monthStart) month++;
        if (d >= ps.weekStart)  week++;
        if (d >= ps.dayStart)   day++;
      });
      return { day: day, week: week, month: month };
    }

    // 타임스탬프(Date|string) → Date 변환 헬퍼
    function _toDate_(ts) {
      if (ts instanceof Date) return ts;
      var s = String(ts || '').trim();
      if (!s) return new Date(NaN);
      return new Date(s.replace(' ', 'T') + '+09:00');
    }

    var ps = _periodStarts_();

    // ── clicks 집계 ──
    var clickSh   = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    var clickLast = clickSh.getLastRow();
    var clickTs   = [];
    var clickRows = []; // 전체 raw rows — custom range용
    if (clickLast >= 2) {
      var clickData = clickSh.getRange(2, 1, clickLast - 1, CLICK_HEADERS.length).getValues();
      clickData.forEach(function(r) { if (r[1]) { clickTs.push(r[1]); clickRows.push(r); } }); // 인덱스 1 = 시각
    }
    var clickCounts = _countByPeriod_(clickTs, ps);

    // ── inquiries 집계 — _collectFormInquiries_ 한 번만 호출 ──
    var formInquiries = _collectFormInquiries_(); // 【중복 제거】 단일 호출 후 재사용

    var inqSh2   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var inqLast2 = inqSh2.getLastRow();
    var inqTs    = [];
    var inqMonthRows = []; // {유입채널, 문의유형} — 이번달만 보관
    var inqSheetRows = []; // {시각(Date), 연락처, 유입채널, 문의유형} — conversion·custom용
    if (inqLast2 >= 2) {
      var inqData2 = inqSh2.getRange(2, 1, inqLast2 - 1, INQUIRY_HEADERS.length).getValues();
      var idxChanI  = INQUIRY_HEADERS.indexOf('유입채널'); // 6
      var idxTypeI  = INQUIRY_HEADERS.indexOf('문의유형'); // 4
      var idxPhoneI = INQUIRY_HEADERS.indexOf('연락처');   // 3
      inqData2.forEach(function(r) {
        if (!r[1]) return;
        inqTs.push(r[1]);
        var d = _toDate_(r[1]);
        var ch = _canonicalChannel_(r[idxChanI]);
        var tp = String(r[idxTypeI] || '기타').trim() || '기타';
        inqSheetRows.push({ d: d, 연락처: r[idxPhoneI], 유입채널: ch, 문의유형: tp });
        if (!isNaN(d.getTime()) && d >= ps.monthStart) {
          inqMonthRows.push({ 유입채널: ch, 문의유형: tp });
        }
      });
    }

    // 구글폼 문의 합산 (재사용)
    formInquiries.forEach(function(f) {
      if (!f.시각) return;
      inqTs.push(f.시각);
      var d = _toDate_(f.시각);
      var ch = _canonicalChannel_(f.유입채널);
      var tp = String(f.문의유형  || '기타').trim() || '기타';
      inqSheetRows.push({ d: d, 연락처: f.연락처, 유입채널: ch, 문의유형: tp });
      if (!isNaN(d.getTime()) && d >= ps.monthStart) {
        inqMonthRows.push({ 유입채널: ch, 문의유형: tp });
      }
    });

    var inqCounts = _countByPeriod_(inqTs, ps);

    // byChannelMonth / byTypeMonth (이번달만)
    var byChannelMonth = {};
    var byTypeMonth    = {};
    inqMonthRows.forEach(function(row) {
      var ch = row.유입채널;
      var tp = row.문의유형;
      byChannelMonth[ch] = (byChannelMonth[ch] || 0) + 1;
      byTypeMonth[tp]    = (byTypeMonth[tp]    || 0) + 1;
    });

    // ── conversion (월 단위만) — 회원 전화 Set 재사용 ──
    var mbrSs2   = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var mbrSh2   = mbrSs2.getSheetByName(MEMBER_SHEET);
    var mbrLast2 = mbrSh2.getLastRow();
    var mbrSet2  = {};
    if (mbrLast2 >= 2) {
      var mbrHeaders2  = mbrSh2.getRange(1, 1, 1, mbrSh2.getLastColumn()).getValues()[0];
      var mbrPhoneIdx2 = mbrHeaders2.indexOf(MEMBER_PHONE_COL);
      if (mbrPhoneIdx2 >= 0) {
        var mbrPhones2 = mbrSh2.getRange(2, mbrPhoneIdx2 + 1, mbrLast2 - 1, 1).getValues();
        mbrPhones2.forEach(function(r) { var n = normalizePhone_(r[0]); if (n) mbrSet2[n] = true; });
      }
    }

    // 이번달 문의 전환 카운트 (inqSheetRows 재사용 — 시트 재읽기 없음)
    var convInq = 0, convConv = 0;
    inqSheetRows.forEach(function(row) {
      if (isNaN(row.d.getTime()) || row.d < ps.monthStart) return;
      convInq++;
      var phone = normalizePhone_(row.연락처);
      if (phone && mbrSet2[phone]) convConv++;
    });
    var convRate = convInq > 0 ? Math.round((convConv / convInq) * 1000) / 10 : 0;

    // ── custom range (from/to 둘 다 있을 때만) ──
    var customObj = null;
    if (from && to) {
      var cFrom = new Date(from + 'T00:00:00+09:00');
      var cTo   = new Date(to   + 'T23:59:59+09:00');

      // custom clicks
      var cClicks = 0;
      clickRows.forEach(function(r) {
        var d = _toDate_(r[1]);
        if (!isNaN(d.getTime()) && d >= cFrom && d <= cTo) cClicks++;
      });

      // custom inquiries + byChannel + byType + conversion
      var cInqTotal = 0;
      var cByChannel = {};
      var cByType    = {};
      var cConvInq = 0, cConvConv = 0;
      inqSheetRows.forEach(function(row) {
        if (isNaN(row.d.getTime()) || row.d < cFrom || row.d > cTo) return;
        cInqTotal++;
        cByChannel[row.유입채널] = (cByChannel[row.유입채널] || 0) + 1;
        cByType[row.문의유형]    = (cByType[row.문의유형]    || 0) + 1;
        cConvInq++;
        var phone = normalizePhone_(row.연락처);
        if (phone && mbrSet2[phone]) cConvConv++;
      });
      var cConvRate = cConvInq > 0 ? Math.round((cConvConv / cConvInq) * 1000) / 10 : 0;

      customObj = {
        from: from,
        to:   to,
        clicks:    cClicks,
        inquiries: cInqTotal,
        byChannel: cByChannel,
        byType:    cByType,
        conversion: { inquiries: cConvInq, converted: cConvConv, rate: cConvRate }
      };
    }

    // ── 유형별 등록 현황 (이번 달) ──
    // 멤버십: 유효회원 시트 '등록 일자' 기준 이번달 신규등록 카운트
    // 강습(성인·유소년): 종목별 팀시트 수강등록(SUC/단기SUC/등록) 기준 — _collectLessonRegistrations_ 반환값
    var regByTypeMonth = {};

    // 멤버십 등록 — 회원부 시트 '등록 일자' 컬럼 기준 이번달 카운트
    try {
      var regMbrHeaders = mbrSh2.getRange(1, 1, 1, mbrSh2.getLastColumn()).getValues()[0];
      var regDateIdx    = regMbrHeaders.indexOf(MEMBER_DATE_COL);
      if (regDateIdx >= 0 && mbrLast2 >= 2) {
        var regDateVals = mbrSh2.getRange(2, regDateIdx + 1, mbrLast2 - 1, 1).getValues();
        var mbrRegCount = 0;
        regDateVals.forEach(function(r) {
          var d = _toDate_(r[0]);
          if (!isNaN(d.getTime()) && d >= ps.monthStart) mbrRegCount++;
        });
        regByTypeMonth['멤버십'] = mbrRegCount;
      }
    } catch (e) { /* 회원 등록일 집계 실패 무시 */ }

    // 강습 등록 — 팀시트 수강등록 정본 (누적값; 등록일 미제공 → 이번달 구분 불가, 전체 등록수 표시)
    try {
      var lessonRegs = _collectLessonRegistrations_();
      ['성인강습', '유소년강습'].forEach(function(tp) {
        if (lessonRegs[tp]) regByTypeMonth[tp] = lessonRegs[tp].registered || 0;
      });
    } catch (e) { /* 강습 등록 집계 실패 무시 */ }

    var pbResult = {
      ok:          true,
      generatedAt: _now(),
      periods: {
        dayStart:   ps.dayStr,
        weekStart:  ps.weekStr,
        monthStart: ps.monthStr
      },
      clicks:    { day: clickCounts.day, week: clickCounts.week, month: clickCounts.month },
      inquiries: {
        day:            inqCounts.day,
        week:           inqCounts.week,
        month:          inqCounts.month,
        byChannelMonth: byChannelMonth,
        byTypeMonth:    byTypeMonth
      },
      conversion: {
        month: { inquiries: convInq, converted: convConv, rate: convRate }
      },
      regByTypeMonth: regByTypeMonth  // 유형별 등록 현황 (멤버십=이번달신규 / 강습=누적)
    };
    if (customObj !== null) pbResult.custom = customObj;

    // 캐시 저장 (100KB 초과 시 생략)
    try { pbCache.put(pbKey, JSON.stringify(pbResult), 300); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(pbResult);
  }

  // ─── 전환 단계 퍼널 (5단계 누적 깔때기) ───
  if (action === 'stage_funnel') {
    // 캐시 조회
    var sfCache = CacheService.getScriptCache();
    var sfHit   = sfCache.get('sf_v1');
    if (sfHit) return _json(JSON.parse(sfHit));

    // ① 회원부 전화번호 Set 생성 (funnel_conversion 방식 그대로)
    var sfMemberSs   = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var sfMemberSh   = sfMemberSs.getSheetByName(MEMBER_SHEET);
    var sfMemberLast = sfMemberSh.getLastRow();
    var sfMemberSet  = {};
    if (sfMemberLast >= 2) {
      var sfMemberHeaders  = sfMemberSh.getRange(1, 1, 1, sfMemberSh.getLastColumn()).getValues()[0];
      var sfPhoneColIdx    = sfMemberHeaders.indexOf(MEMBER_PHONE_COL);
      if (sfPhoneColIdx >= 0) {
        var sfMemberPhones = sfMemberSh.getRange(2, sfPhoneColIdx + 1, sfMemberLast - 1, 1).getValues();
        sfMemberPhones.forEach(function(r) {
          var n = normalizePhone_(r[0]); if (n) sfMemberSet[n] = true;
        });
      }
    }

    // ② 이번달 기준일 산출 (period_breakdown 방식)
    var sfNow       = new Date();
    var sfMonthStr  = Utilities.formatDate(sfNow, 'Asia/Seoul', 'yyyy-MM') + '-01';
    var sfMonthStart = new Date(sfMonthStr + 'T00:00:00+09:00');

    // 타임스탬프 → Date 변환 헬퍼 (period_breakdown._toDate_ 동일 로직)
    function _sfToDate_(ts) {
      if (ts instanceof Date) return ts;
      var s = String(ts || '').trim();
      if (!s) return new Date(NaN);
      return new Date(s.replace(' ', 'T') + '+09:00');
    }

    // ③ 집계 버킷 초기화
    // total: 전체기간 / month: 이번달
    // 각 단계 = 해당 rank 이상 도달한 문의 수(누적 깔때기). 이탈(rank 0)은 이탈 버킷만.
    var sfTotal = { 문의: 0, 응대: 0, 예약: 0, 방문: 0, 가입: 0, 이탈: 0 };
    var sfMonth = { 문의: 0, 응대: 0, 예약: 0, 방문: 0, 가입: 0, 이탈: 0 };

    // 문의 1건 집계 내부 함수
    function _sfCount_(rank, isThisMonth) {
      var buckets = [sfTotal];
      if (isThisMonth) buckets.push(sfMonth);
      buckets.forEach(function(b) {
        if (rank === 0) {
          b.이탈++;
          b.문의++; // 이탈도 ①문의에는 포함(SSOT §집계)
        } else {
          if (rank >= 1) b.문의++;
          if (rank >= 2) b.응대++;
          if (rank >= 3) b.예약++;
          if (rank >= 4) b.방문++;
          if (rank >= 5) b.가입++;
        }
      });
    }

    // ④-a INQUIRY_SHEET 순회
    // 상태=INQUIRY_HEADERS idx9, 전화=idx3, 날짜=idx1
    var sfInqSh   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var sfInqLast = sfInqSh.getLastRow();
    if (sfInqLast >= 2) {
      var sfInqData = sfInqSh.getRange(2, 1, sfInqLast - 1, INQUIRY_HEADERS.length).getValues();
      sfInqData.forEach(function(row) {
        var statusRaw = row[9]; // '상태' idx9
        var phone     = normalizePhone_(row[3]);
        var dateVal   = row[1];
        var rank      = _stageOf_(statusRaw);
        if (phone && sfMemberSet[phone]) rank = Math.max(rank, 5); // 회원 신뢰 우선
        if (rank === 0 && phone && sfMemberSet[phone]) rank = 5;   // 이탈+회원매칭 → 가입 우선
        var d = _sfToDate_(dateVal);
        var isThisMonth = !isNaN(d.getTime()) && d >= sfMonthStart;
        _sfCount_(rank, isThisMonth);
      });
    }

    // ④-b FORM_SHEETS 순회 (상태 칸 _findCol_ 탐색, 없으면 rank=1)
    FORM_SHEETS.forEach(function(cfg) {
      try {
        var sfSh = _sheetByGid_(cfg.ssId, cfg.gid);
        if (!sfSh) return;
        var sfLast    = sfSh.getLastRow();
        var sfLastCol = sfSh.getLastColumn();
        if (sfLast < 2 || sfLastCol < 1) return;
        var sfHeaders  = sfSh.getRange(1, 1, 1, sfLastCol).getValues()[0];
        var sfIdxStatus = _findCol_(sfHeaders, ['진행상태', '상태', '진행', '단계']);
        var sfIdxPhone  = _findCol_(sfHeaders, ['연락처', '휴대폰', '핸드폰', '전화']);
        var sfIdxDate   = _findCol_(sfHeaders, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
        if (sfIdxDate < 0) sfIdxDate = 0;
        var sfRows = sfSh.getRange(2, 1, sfLast - 1, sfLastCol).getValues();
        sfRows.forEach(function(r) {
          if (!r[sfIdxDate] && (sfIdxPhone < 0 || !r[sfIdxPhone])) return; // 빈 행 스킵
          var statusRaw = sfIdxStatus >= 0 ? r[sfIdxStatus] : '';
          var phone     = sfIdxPhone  >= 0 ? normalizePhone_(r[sfIdxPhone]) : '';
          var rank      = _stageOf_(statusRaw); // 상태 칸 없으면 statusRaw='' → rank=1
          if (phone && sfMemberSet[phone]) rank = Math.max(rank, 5);
          if (rank === 0 && phone && sfMemberSet[phone]) rank = 5;
          var dateRaw = _parseAnyDate_(r[sfIdxDate]);
          var d = _sfToDate_(dateRaw);
          var isThisMonth = !isNaN(d.getTime()) && d >= sfMonthStart;
          _sfCount_(rank, isThisMonth);
        });
      } catch (e) { /* 폼 시트 접근 실패는 무시(대시보드 무중단) */ }
    });

    // ⑤ retain 계산 (이번달 기준, 각 단계/직전단계 × 100, 소수1자리)
    function _pct_(num, den) {
      if (!den) return 0;
      return Math.round((num / den) * 1000) / 10;
    }
    var sfRetain = {
      응대: _pct_(sfMonth.응대, sfMonth.문의),
      예약: _pct_(sfMonth.예약, sfMonth.응대),
      방문: _pct_(sfMonth.방문, sfMonth.예약),
      가입: _pct_(sfMonth.가입, sfMonth.방문)
    };

    var sfResult = {
      ok:          true,
      generatedAt: _now(),
      total:  sfTotal,
      month:  sfMonth,
      retain: sfRetain
    };
    // 캐시 저장 (100KB 초과 시 생략)
    try { sfCache.put('sf_v1', JSON.stringify(sfResult), 300); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(sfResult);
  }

  // ─── 주간 추세 (최근 8주 시계열) ───
  if (action === 'weekly_trend') {
    // 캐시 조회
    var wtCache = CacheService.getScriptCache();
    var wtHit = wtCache.get('wt_v1');
    if (wtHit) return _json(JSON.parse(wtHit));

    // ── 이번 주 월요일 기준 8주 구간 산출 (Asia/Seoul) ──
    var wtNow = new Date();
    var wtDow = parseInt(Utilities.formatDate(wtNow, 'Asia/Seoul', 'u'), 10); // 1=월 … 7=일
    var wtMonDate = new Date(wtNow.getTime() - (wtDow - 1) * 86400000);
    var wtWeekStr = Utilities.formatDate(wtMonDate, 'Asia/Seoul', 'yyyy-MM-dd');
    var wtThisWeekStart = new Date(wtWeekStr + 'T00:00:00+09:00');

    // 8개 구간: 7주 전 월요일 ~ 이번 주 일요일
    var wtBuckets = [];  // [{start: Date, end: Date, weekStart: 'YYYY-MM-DD', inquiries: 0, clicks: 0}]
    for (var wi = 7; wi >= 0; wi--) {
      var bucketStart = new Date(wtThisWeekStart.getTime() - wi * 7 * 86400000);
      var bucketEnd   = new Date(bucketStart.getTime()     + 7 * 86400000);
      var bucketStr   = Utilities.formatDate(bucketStart, 'Asia/Seoul', 'yyyy-MM-dd');
      wtBuckets.push({ start: bucketStart, end: bucketEnd, weekStart: bucketStr, inquiries: 0, clicks: 0 });
    }

    // 타임스탬프(Date|string) → Date 변환 (period_breakdown 의 _toDate_ 와 동일 로직)
    function _wtToDate_(ts) {
      if (ts instanceof Date) return ts;
      var s = String(ts || '').trim();
      if (!s) return new Date(NaN);
      return new Date(s.replace(' ', 'T') + '+09:00');
    }

    // ── 클릭 타임스탬프 집계 ──
    var wtClickSh   = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    var wtClickLast = wtClickSh.getLastRow();
    if (wtClickLast >= 2) {
      var wtClickData = wtClickSh.getRange(2, 1, wtClickLast - 1, CLICK_HEADERS.length).getValues();
      wtClickData.forEach(function(r) {
        if (!r[1]) return;
        var d = _wtToDate_(r[1]);
        if (isNaN(d.getTime())) return;
        for (var bi = 0; bi < wtBuckets.length; bi++) {
          if (d >= wtBuckets[bi].start && d < wtBuckets[bi].end) {
            wtBuckets[bi].clicks++;
            break;
          }
        }
      });
    }

    // ── 문의 타임스탬프 집계 — 문의접수 시트 + 구글폼 합산 ──
    var wtInqSh   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var wtInqLast = wtInqSh.getLastRow();
    if (wtInqLast >= 2) {
      var wtInqData = wtInqSh.getRange(2, 1, wtInqLast - 1, INQUIRY_HEADERS.length).getValues();
      wtInqData.forEach(function(r) {
        if (!r[1]) return;
        var d = _wtToDate_(r[1]);
        if (isNaN(d.getTime())) return;
        for (var bi = 0; bi < wtBuckets.length; bi++) {
          if (d >= wtBuckets[bi].start && d < wtBuckets[bi].end) {
            wtBuckets[bi].inquiries++;
            break;
          }
        }
      });
    }

    // 구글폼 문의 합산
    _collectFormInquiries_().forEach(function(f) {
      if (!f.시각) return;
      var d = _wtToDate_(f.시각);
      if (isNaN(d.getTime())) return;
      for (var bi = 0; bi < wtBuckets.length; bi++) {
        if (d >= wtBuckets[bi].start && d < wtBuckets[bi].end) {
          wtBuckets[bi].inquiries++;
          break;
        }
      }
    });

    // ── 응답 조립 (오래된→최신 순, start/end Date 는 제거) ──
    var wtWeeks = wtBuckets.map(function(b) {
      return { weekStart: b.weekStart, inquiries: b.inquiries, clicks: b.clicks };
    });

    var wtResult = { ok: true, weeks: wtWeeks, generatedAt: _now() };
    try { wtCache.put('wt_v1', JSON.stringify(wtResult), 300); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(wtResult);
  }

  return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

// ═══════════════════════════════════════════
//  doGet / doPost
// ═══════════════════════════════════════════
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) || '';
    if (action) {
      const body = {};
      Object.keys(e.parameter).forEach(k => body[k] = e.parameter[k]);
      return _processAction(body);
    }
    return _json({ ok: false, error: 'action 필수' });
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    return _processAction(body);
  } catch (err) {
    return _json({ ok: false, error: err.message });
  }
}
