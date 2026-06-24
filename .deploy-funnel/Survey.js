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

const CLICK_HEADERS = ['id', '시각', '링크명', '링크URL', 'UTM소스', 'UTM미디엄', '리퍼러', '디바이스', 'UTM캠페인'];
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
  // ─── 영문 문의 3종 (시모 2026-06-24) ───
  , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1887747109, type: '멤버십(영문)',    channelKeys: ['How Did You Hear About Us?', '경로', '채널'] }
  , { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 311319200,  type: '성인강습(영문)',  channelKeys: ['How Did You Hear About Us?', '경로', '채널'] }
  , { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 931249179,  type: '유소년강습(영문)', channelKeys: ['How Did You Hear About Us?', '경로', '채널'] }
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
                          '소개·지인', '기존·과거 회원', '오프라인', '기타·미상'];

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
  // 멤버십 '26년 신규문의' 탭 실사용 코드(2026-06-20 시포 실측): 결제완납·결제완료·완납·키오스크 완 = 가입(5)
  if (/가입|등록|전환|회원|완납|결제완|키오스크\s*완/.test(s)) return 5;
  if (/방문|내방|방문완료/.test(s))              return 4;
  if (/예약|투어|상담/.test(s))                  return 3;
  // 멤버십 실사용 코드: 컨택중 = 응대(2)
  if (/응대|연락|통화|문자|회신|컨택/.test(s))   return 2;
  if (/신규|접수/.test(s))                       return 1;
  return 1; // 미인식 → ① 문의(안전 처리)
}

// ─── CTA(웹폼) 문의 → '26년 신규문의'(실무진 처리 로그) 미러 기록 (2026-06-20 GM A안) ───
// 마케팅 CTA 문의가 실무진 처리 화면(문의DB=26년 신규문의)에도 떠서 진행상태를 찍을 수 있게 한다.
// '[웹접수]' 표식을 비고에 남겨, 집계(_collectFormInquiries_·stage_funnel ④-b)에서 제외 →
//   문의접수 시트로 이미 1회 집계되므로 이중집계 방지(전환은 유효회원 전화매칭으로 자동 반영).
// fail-soft: 미러 실패가 CTA 접수 자체를 막지 않는다(문의접수 기록은 이미 성공).
var WEB_INTAKE_TAG = '[웹접수]';
function _mirrorInquiryToStaffLog_(body, inqId) {
  try {
    var sh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid); // 12AWcAlg '26년 신규문의'
    if (!sh) return;
    var lastCol = sh.getLastColumn();
    var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
    var newRow = new Array(lastCol).fill('');
    function put(keys, val) { var i = _findCol_(headers, keys); if (i >= 0) newRow[i] = val; }
    put(['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜'], Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy. M. d'));
    put(['성함', '이름'], body.name || '');
    put(['연락처', '휴대폰', '핸드폰', '전화'], body.phone || '');
    put(['진행현황', '진행상태', '상태'], '신규');
    put(['채널', '경로', '알게'], _canonicalChannel_(body.utmSource || body.inflow || ''));
    put(['접수 담당자', '담당'], '웹 자동접수');
    var memo = WEB_INTAKE_TAG + ' 유형:' + (body.type || '-')
             + (body.message ? ' / ' + String(body.message).substring(0, 200) : '')
             + ' (utm:' + (body.utmSource || '-') + '/' + (body.utmMedium || '-') + ', ' + inqId + ')';
    put(['비고', '메모'], memo);
    sh.getRange(sh.getLastRow() + 1, 1, 1, lastCol).setValues([newRow]);
  } catch (e) { /* 미러 실패 무시 — CTA 접수 무중단 */ }
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

// 타임스탬프(Date | 'yyyy-MM-dd HH:mm:ss' 문자열 | 'YYYY. M. D' 한글) → Date(KST 고정).
// ★ 단일 정규화 SSOT — 클릭(_now() 문자열)·문의(_parseAnyDate_) 모두 이 함수로 통일해
//   날짜 파싱 불일치(클릭<문의 누락 버그, 2026-06-18 INC) 방지. period_breakdown._toDate_ 와 동일 로직.
//   클릭 시각은 'yyyy-MM-dd HH:mm:ss'(공백 구분·오프셋 없음)으로 저장됨 → 반드시 'T'+'+09:00'로 ISO화.
function _normTs_(ts) {
  var v = _parseAnyDate_(ts);          // 한글 'YYYY. M. D' 먼저 흡수
  if (v instanceof Date) return v;
  var s = String(v || '').trim();
  if (!s) return new Date(NaN);
  return new Date(s.replace(' ', 'T') + '+09:00');  // 'yyyy-MM-dd HH:mm:ss' → ISO(KST)
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
      var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화', 'Mobile Phone', 'Phone', "Guardian's Mobile Phone"]);
      var idxChan  = _findCol_(headers, cfg.channelKeys);          // 대분류(문의 채널) — 폴백 기준
      var idxChanFine = _findCol_(headers, ['중분류']);             // 문의 경로(중분류) — 정밀(있을 때만, 멤버십 탭)
      var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
      if (idxDate < 0) idxDate = 0;  // 못 찾으면 1열(구글폼 기본). 26년신규문의=B칸(타임스탬프) 자동 포착
      var idxMemoCfi = _findCol_(headers, ['비고', '메모']);  // [웹접수] 표식 탐지용
      var rows = sh.getRange(2, 1, last - 1, lastCol).getValues();
      rows.forEach(function(r) {
        if (!r[idxDate] && (idxPhone < 0 || !r[idxPhone])) return; // 빈 행 스킵
        // CTA 웹폼 미러 행([웹접수])은 문의접수 시트로 이미 1회 집계됨 → 여기선 제외(이중집계 방지)
        if (idxMemoCfi >= 0 && String(r[idxMemoCfi] || '').indexOf(WEB_INTAKE_TAG) >= 0) return;
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

// 강습 수강등록 — 팀시트(LESSON_TEAM_SHEETS)별 '명' 단위 등록수 집계(종목별 펼침용).
// _collectLessonRegistrations_ 와 동일한 상태열 탐지 + _isLessonReg_ 로직 재사용 — 단지 cfg.유형이 아닌 cfg.명 키로 분해.
// 반환: { 'P.T 성인': {유형, registered, statusHeader, statusHits, rows, sheetFound}, ... } (시트 미발견/상태열 미발견은 registered=null로 정직 표기 — 0으로 날조 금지)
function _collectLessonRegByName_() {
  var out = {};
  LESSON_TEAM_SHEETS.forEach(function(cfg) {
    var rec = { 유형: cfg.유형, 명: cfg.명, registered: null, statusHeader: '(미발견)', statusHits: 0, rows: 0, sheetFound: false };
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) { rec.statusHeader = '(시트 미발견)'; out[cfg.명] = rec; return; }
      rec.sheetFound = true;
      var last = sh.getLastRow();
      var lastCol = sh.getLastColumn();
      rec.rows = Math.max(0, last - 1);
      if (last < 2 || lastCol < 1) { rec.registered = 0; rec.statusHeader = '(빈 시트)'; out[cfg.명] = rec; return; }
      var data = sh.getRange(1, 1, last, lastCol).getValues();
      var headers = data[0];
      // 상태열 탐지 — _collectLessonRegistrations_ 와 동일(고유값 2~30 + 코드형 상태값 최다 열)
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
      rec.statusHits = bestCnt;
      if (best < 0) { rec.statusHeader = '(상태값 없음)'; out[cfg.명] = rec; return; } // 상태열 못 찾음 → null 유지(0 날조 금지)
      rec.statusHeader = String(headers[best] || '');
      var reg = 0;
      for (var r2 = 1; r2 < data.length; r2++) { if (_isLessonReg_(data[r2][best])) reg++; }
      rec.registered = reg;  // 시트·상태열 존재 → 0도 실측치(정직)
    } catch (e) { rec.error = String(e); }  // 접근 실패 → registered=null 유지
    out[cfg.명] = rec;
  });
  return out;
}

// 강습 종목별 문의수 — 팀시트(LESSON_TEAM_SHEETS) 전체 행을 타임스탬프(B열 등) 기준 기간 집계.
// 각 팀시트 = 통합 문의의 종목별 분배본 → 행 1개 = 문의 1건(상태 무관). from/to(YYYY-MM-DD KST) 범위만 카운트, 미지정=전체.
// 반환: { '수영 성인': {명, 유형, inquiries|null, sheetFound}, ... } (시트 미발견=null, 정직표기).
function _collectLessonInqByName_(from, to) {
  var out = {};
  var cFrom = (from) ? new Date(from + 'T00:00:00+09:00') : null;
  var cTo   = (to)   ? new Date(to   + 'T23:59:59+09:00') : null;
  LESSON_TEAM_SHEETS.forEach(function(cfg) {
    var rec = { 명: cfg.명, 유형: cfg.유형, inquiries: null, sheetFound: false };
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) { out[cfg.명] = rec; return; }
      rec.sheetFound = true;
      var last = sh.getLastRow(), lastCol = sh.getLastColumn();
      if (last < 2 || lastCol < 1) { rec.inquiries = 0; out[cfg.명] = rec; return; }
      var hdrs = sh.getRange(1, 1, 1, lastCol).getValues()[0];
      var idxDate = _findCol_(hdrs, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
      if (idxDate < 0) idxDate = 0;  // 못 찾으면 1열(구글폼 기본)
      var rows = sh.getRange(2, 1, last - 1, lastCol).getValues();
      var n = 0;
      rows.forEach(function(r) {
        var dateRaw = r[idxDate];
        if (!dateRaw) return;
        if (!cFrom || !cTo) { n++; return; }  // 기간 미지정 = 행 전체
        var d = _parseAnyDate_(dateRaw);
        if (!(d instanceof Date) || isNaN(d.getTime())) return;
        if (d >= cFrom && d <= cTo) n++;
      });
      rec.inquiries = n;
    } catch (e) { rec.error = String(e); }  // 접근 실패 → inquiries=null 유지
    out[cfg.명] = rec;
  });
  return out;
}

// ─── 종목별 등록 표시 SSOT (GM 지정 2026-06-18) ───
// GM 종목 ↔ LESSON_TEAM_SHEETS '명' 매핑. 시트 없는 종목(바레·발레)은 sheet:null → registered=null('데이터 미연결').
var LESSON_DISPLAY = {
  '성인강습': [
    { 명: '수영',   sheet: '수영 성인' },
    { 명: '골프',   sheet: '골프 성인' },
    { 명: '스쿼시', sheet: '스쿼시 성인' },
    { 명: 'P.T',    sheet: 'P.T 성인' },
    { 명: '필라테스', sheet: '필라테스 성인' },
    { 명: '바레',   sheet: null },   // 등록 데이터 출처 없음(2026-06-18 grep 확인) → null
    { 명: '발레',   sheet: null }    // 등록 데이터 출처 없음 → null
  ],
  '유소년강습': [
    { 명: '수영',          sheet: '수영 유소년' },
    { 명: '골프',          sheet: '골프 유소년' },
    { 명: '스쿼시',        sheet: '스쿼시 유소년' },
    { 명: '체조&트램폴린', sheet: '유소년체조' }
  ]
};

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

function _notifyTelegram(text, chatIdOverride) {
  const token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  const chatId = chatIdOverride || _prop('CHAT_ID') || _prop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) return;
  try {
    UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
  } catch (e) { Logger.log('텔레그램 실패: ' + e.message); }
}

// ─── 신규 문의 감지 → 텔레그램 '문의 알림' 방 발송 (시모, 2026-06-24) ───
// FORM_SHEETS 각 시트의 신규 행을 5분마다 감지해 TELEGRAM_INQUIRY_CHAT_ID 방으로 알림.
// ScriptProperties INQ_LASTROW_<ssId>_<gid> 에 마지막 처리 행수 저장 → 중복 방지.
// 최초 실행: 기준선만 저장, 과거 문의 일괄발송 없음.
var _INQUIRY_CHAT_ID_FALLBACK = '-5516675010';  // '문의 알림' 방 — 프로퍼티 없을 때 폴백(그룹 ID, 민감정보 아님)

function _notifyNewInquiries_() {
  var props = PropertiesService.getScriptProperties();
  var inquiryChatId = props.getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;

  FORM_SHEETS.forEach(function(cfg) {
    var propKey = 'INQ_LASTROW_' + cfg.ssId + '_' + cfg.gid;
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) return;
      var lastRow = sh.getLastRow();
      var storedStr = props.getProperty(propKey);

      // 최초 실행: 기준선 저장 후 종료 (과거분 폭주 방지)
      if (!storedStr) {
        props.setProperty(propKey, String(lastRow));
        Logger.log('[문의알림] 기준선 저장 — ' + cfg.type + ' lastRow=' + lastRow);
        return;
      }

      var storedRow = parseInt(storedStr, 10) || 1;
      if (lastRow <= storedRow) return; // 신규 없음

      // 헤더 읽기
      var lastCol = sh.getLastColumn();
      if (lastCol < 1) { props.setProperty(propKey, String(lastRow)); return; }
      var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
      var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
      var idxName  = _findCol_(headers, ['성함', '이름', 'Full Name', 'Name', "Child's Full Name"]);
      var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화', 'Mobile Phone', 'Phone', "Guardian's Mobile Phone"]);
      var idxChan  = _findCol_(headers, cfg.channelKeys || ['채널', '경로', '알게', 'How Did You Hear']);
      var idxMemo  = _findCol_(headers, ['비고', '메모']);

      // 신규 행 처리
      var newRows = sh.getRange(storedRow + 1, 1, lastRow - storedRow, lastCol).getValues();
      newRows.forEach(function(r) {
        // [웹접수] 미러 행 제외 (이미 submit_inquiry에서 발송)
        if (idxMemo >= 0 && String(r[idxMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) return;
        // 완전 빈 행 스킵
        if (!r[idxDate >= 0 ? idxDate : 0] && (idxPhone < 0 || !r[idxPhone])) return;

        var ts = idxDate >= 0 ? r[idxDate] : '';
        var tsStr = '';
        try {
          var d = _normTs_(ts);
          tsStr = isNaN(d.getTime()) ? String(ts).substring(0, 16) : Utilities.formatDate(d, 'Asia/Seoul', 'MM/dd HH:mm');
        } catch (e) { tsStr = String(ts).substring(0, 16); }

        var name  = idxName  >= 0 ? String(r[idxName]  || '').trim() : '-';
        var phone = idxPhone >= 0 ? String(r[idxPhone] || '').trim() : '-';
        var chan  = idxChan  >= 0 ? String(r[idxChan]  || '').trim() : '-';
        if (!name)  name  = '-';
        if (!phone) phone = '-';
        if (!chan)  chan  = '-';

        var msg = '🔔 [신규 문의]\n'
          + '유형: ' + cfg.type + '\n'
          + '이름: ' + name + '\n'
          + '연락처: ' + phone + '\n'
          + '유입채널: ' + chan + '\n'
          + '시각: ' + tsStr;
        _notifyTelegram(msg, inquiryChatId);
      });

      // 기준선 갱신
      props.setProperty(propKey, String(lastRow));
    } catch (e) {
      Logger.log('[문의알림] ' + cfg.type + ' 오류: ' + e.message);
    }
  });
}

// '문의 알림' 방 5분 트리거 — 중복 설치 방지. GAS 에디터 또는 clasp push 후 1회 수동 실행.
function installInquiryNotifyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === '_notifyNewInquiries_') {
      Logger.log('트리거 이미 존재 — 스킵');
      return;
    }
  }
  ScriptApp.newTrigger('_notifyNewInquiries_')
    .timeBased().everyMinutes(5).create();
  Logger.log('트리거 설치 완료: _notifyNewInquiries_ 5분 주기');
}

// '문의 알림' 방 → GAS 토큰 작동 1회 확인 (일회용 — GAS 에디터에서 수동 실행)
// ① 봇 토큰 존재여부 Logger 출력 ② 토큰 있으면 테스트 메시지 발송 후 응답코드 출력
function verifyInquiryNotify() {
  var token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  if (!token) {
    Logger.log('[작동확인] 토큰 미설정 — TELEGRAM_BOT_TOKEN 프로퍼티 추가 필요');
    return;
  }
  Logger.log('[작동확인] 봇 토큰 확인됨 (길이=' + token.length + ')');
  var chatId = _INQUIRY_CHAT_ID_FALLBACK;
  var msg = '✅ [작동 확인] GAS에서 신규 문의 알림이 이 방으로 정상 발송됩니다 — 시모';
  try {
    var res = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: msg }),
      muteHttpExceptions: true
    });
    Logger.log('[작동확인] 응답코드=' + res.getResponseCode());
  } catch (e) {
    Logger.log('[작동확인] 발송 오류: ' + e.message);
  }
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
  track_click:    true,  // 클릭 추적 — 토큰 면제
  ping_inquiry_notify: true,  // [진단용] BOT_TOKEN 확인 + 문의 알림 방 테스트 발송 (시모 2026-06-24)
  // 마케팅 집계(PII 미노출) 면제 — 2026-06-17 CMO, 시토 게이트 공유
  // 아래 5개 액션은 집계 숫자만 반환 · 이름·전화 등 원시 개인정보 미노출 → 면제 안전.
  // inquiry_list 등 원시 행/PII 반환 액션은 절대 면제 금지(게이트 유지).
  period_breakdown:       true,
  funnel_conversion:      true,
  type_channel_breakdown: true,
  click_stats:            true,
  campaign_stats:         true,  // 콘텐츠별 클릭 집계(PII 미노출) — 면제 안전
  lead_time_stats:        true,  // 문의→등록 평균 전환 소요일(집계 숫자만·PII 미노출) — 면제 안전 (2026-06-23 CMO)
  today_live:             true,
  lesson_breakdown:       true,  // 종목별 등록수만 반환(PII 미노출) — 면제 안전
  // 문의회원 페이지(CPO) 익명 읽기 — 이름·전화·메모 0 노출 → 공개 안전(2026-06-22 A안)
  member_inquiry_list:    true,
  member_calendar:        true,
  member_inquiry_update:  true,  // 2026-06-22 GM '전체 공개' — 실명·전화 포함 수정
  member_inquiry_add:     true,  // 2026-06-23 전화·직접 문의 수기 추가
  member_inquiry_delete:  true,  // 행 삭제
  member_registered_list:     true,  // 2026-06-23 등록현황(SUC/단기SUC) 조회
  member_registered_setmonth: true,  // 등록회원 1~12월 체크 토글
  member_registered_delete:   true,  // 등록 해제(행 삭제)
  member_active_list:         true,  // 멤버십 회원 명단(유효회원·전화 마스킹)
  member_active_update:       true,  // 2026-06-24 멤버십 셀 인라인 수정(유효회원 시트·전화 제외)
  cpo_today_stats:            true   // 2026-06-24 CPO 오늘/이번달 문의·등록 건수(PII 미노출)
};
// add_utm_field 비밀 가드값 — 폼 변형 액션 무단호출 차단. _SURVEY_PUBLIC_ACTIONS에 넣지 말 것.
var _ADD_UTM_GUARD = 'wp-utm-field-2026-i-am-sure';
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
//  문의회원 페이지 전용 — '26년 신규문의' 익명 읽기 (CPO cpo/member/문의회원.html)
//  ★ A안(2026-06-22 GM go): 이름·전화·메모 완전 제거(빈값) → 공개 페이지 안전, PII_GATE 불필요.
//     실명 표시·편집(CRUD)은 별도 접근통제(B안) 후속. 기존 inquiry_list(대시보드 집계)와 무관.
// ═══════════════════════════════════════════
var _MI_SS_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
var _MI_SHEET = '26년 신규문의';
function _miSheet_() { return SpreadsheetApp.openById(_MI_SS_ID).getSheetByName(_MI_SHEET); }
function _miHeaders_(sh) {
  var last = sh.getLastColumn();
  if (last < 1) return [];
  return sh.getRange(1, 1, 1, last).getValues()[0].map(function(v){ return String(v).trim(); });
}
function _miColIdx_(headers, names) {
  var arr = Array.isArray(names) ? names : [names];
  for (var i = 0; i < arr.length; i++) { var idx = headers.indexOf(arr[i]); if (idx >= 0) return idx; }
  for (var k = 0; k < arr.length; k++) { for (var j = 0; j < headers.length; j++) { if (headers[j].indexOf(arr[k]) >= 0) return j; } }
  return -1;
}
function _miToISO_(val) {
  if (!val) return '';
  if (val instanceof Date && !isNaN(val.getTime())) {
    return val.getFullYear() + '-' + String(val.getMonth()+1).padStart(2,'0') + '-' + String(val.getDate()).padStart(2,'0');
  }
  var s = String(val).trim();
  var m = s.match(/(\d{4})[\.\-\/]?\s*(\d{1,2})[\.\-\/]?\s*(\d{1,2})/);
  if (m) return m[1] + '-' + ('0'+m[2]).slice(-2) + '-' + ('0'+m[3]).slice(-2);
  return s;
}
// 셀에서 시간(HH:MM) 추출 — Date면 getHours, 문자열이면 'HH:MM' 매칭. 자정(00:00)=시간미설정으로 간주.
function _miTime_(val) {
  if (!val) return '';
  if (val instanceof Date && !isNaN(val.getTime())) {
    var hh = val.getHours(), mm = val.getMinutes();
    if (hh === 0 && mm === 0) return '';
    return ('0'+hh).slice(-2) + ':' + ('0'+mm).slice(-2);
  }
  var t = String(val).match(/(\d{1,2}):(\d{2})/);
  return t ? ('0'+t[1]).slice(-2) + ':' + t[2] : '';
}
// 익명 행 배열 반환(이름·전화·메모 비움). 빈 행 스킵.
function _miReadRows_() {
  var sh = _miSheet_();
  if (!sh) return [];
  var hdr = _miHeaders_(sh);
  var last = sh.getLastRow();
  var out = [];
  if (last < 2) return out;
  var data = sh.getRange(2, 1, last - 1, hdr.length).getValues();
  var iName  = _miColIdx_(hdr, ['성함','이름']);  // '성함' 우선 — '이름'이 '접수 담당자 혹은 본인 이름' 칸을 먼저 잡던 버그 차단(2026-06-24)
  var iPhone = _miColIdx_(hdr, ['연락처','전화','휴대폰']);
  var iProg  = _miColIdx_(hdr, ['관심 있는 프로그램 종류','관심프로그램','프로그램']);
  var iStat  = _miColIdx_(hdr, ['진행현황','진행상황','진행상태','상태']);
  var iTs    = _miColIdx_(hdr, ['타임스탬프','접수일','날짜']);
  var iTour  = _miColIdx_(hdr, ['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담']);
  var iExp1  = _miColIdx_(hdr, ['체험1 확정시간','체험1']);
  var iExp2  = _miColIdx_(hdr, ['체험2 확정시간','체험2']);
  var iOwner = _miColIdx_(hdr, ['담당','담당자']);
  var iMemo  = _miColIdx_(hdr, ['메모','비고','담당자메모']);
  var iChan  = _miColIdx_(hdr, ['문의채널','유입채널','채널','경로','알게']);
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var hasName  = iName  >= 0 && row[iName];
    var hasPhone = iPhone >= 0 && row[iPhone];
    if (!hasName && !hasPhone) continue; // 완전 빈 행 스킵
    out.push({
      rowIndex: r + 2,
      name:     iName  >= 0 ? String(row[iName]  || '') : '',  // 2026-06-22 GM '전체 공개' — 실명 노출
      phone:    iPhone >= 0 ? String(row[iPhone] || '') : '',  // 연락처 노출
      program:  iProg  >= 0 ? String(row[iProg]  || '') : '',
      status:   iStat  >= 0 ? String(row[iStat]  || '') : '',
      channel:  (iChan >= 0 && row[iChan]) ? _canonicalChannel_(String(row[iChan])) : '',  // 유입채널 표준 10버킷(빈값은 빈값 유지)
      tourDate: _miToISO_(iTour >= 0 ? row[iTour] : ''),
      tourTime: _miTime_(iTour >= 0 ? row[iTour] : ''),
      exp1:     _miToISO_(iExp1 >= 0 ? row[iExp1] : ''),
      exp1Time: _miTime_(iExp1 >= 0 ? row[iExp1] : ''),
      exp2:     _miToISO_(iExp2 >= 0 ? row[iExp2] : ''),
      exp2Time: _miTime_(iExp2 >= 0 ? row[iExp2] : ''),
      timestamp:_miToISO_(iTs   >= 0 ? row[iTs]   : ''),
      memo:     iMemo  >= 0 ? String(row[iMemo]  || '') : '',
      owner:    iOwner >= 0 ? String(row[iOwner] || '') : ''
    });
  }
  return out;
}

// ═══════════════════════════════════════════
//  액션 처리
// ═══════════════════════════════════════════
// ═══ 등록현황 탭 (Phase 3 — SUC/단기SUC 등록회원 누적 + 1~12월 체크) ═══
var _REG_SHEET = '26년 등록현황';
var _REG_HEADER = ['이름','전화','프로그램','등록일','1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
function _regSheet_() {
  var ss = SpreadsheetApp.openById(_MI_SS_ID);
  var sh = ss.getSheetByName(_REG_SHEET);
  if (!sh) {
    sh = ss.insertSheet(_REG_SHEET);
    sh.getRange(1, 1, 1, _REG_HEADER.length).setValues([_REG_HEADER]);
    sh.setFrozenRows(1);
  }
  return sh;
}
function _regNormPhone_(p) { return String(p == null ? '' : p).replace(/[^0-9]/g, ''); }
// SUC/단기SUC 전환 시 등록현황에 upsert(전화 키). 신규=등록일 오늘+행추가. 기존=이름·프로그램만 갱신(등록일 보존).
function _regUpsert_(name, phone, program) {
  var key = _regNormPhone_(phone);
  if (!key) return;
  var sh = _regSheet_();
  var last = sh.getLastRow();
  if (last >= 2) {
    var data = sh.getRange(2, 1, last - 1, 3).getValues();  // 이름·전화·프로그램
    for (var i = 0; i < data.length; i++) {
      if (_regNormPhone_(data[i][1]) === key) {
        if (name)    sh.getRange(i + 2, 1).setValue(name);
        if (program) sh.getRange(i + 2, 3).setValue(program);
        return;
      }
    }
  }
  var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
  var row = new Array(_REG_HEADER.length).fill('');
  row[0] = name || ''; row[1] = phone || ''; row[2] = program || ''; row[3] = today;
  sh.appendRow(row);
}

function _processAction(body) {
  const action = body.action || '';
  // nocache=1 → 캐시 읽기 우회(강제 재계산·재캐싱). 워머 트리거가 캐시를 미리 데우는 용도(2026-06-19 시토).
  var _nc = (body.nocache === '1');

  // ─── 접근 게이트 확인 ───
  if (!_checkSurveyAccess_(action, body.key)) {
    return _json({ ok: false, error: 'unauthorized' });
  }

  // ─── 클릭 추적 ───
  if (action === 'track_click') {
    const sh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    // 기존 시트에 UTM캠페인 헤더가 없을 경우 9번째 셀 1회 보정
    if (!sh.getRange(1, 9).getValue()) {
      sh.getRange(1, 9).setValue('UTM캠페인')
        .setFontWeight('bold')
        .setBackground('#2a2725')
        .setFontColor('#B79F8A');
    }
    const row = [
      _genId('CLK-'),
      _now(),
      body.linkName || '',
      body.linkUrl || '',
      body.utmSource || '',
      body.utmMedium || '',
      body.referrer || '',
      body.device || '',
      body.utmCampaign || ''
    ];
    sh.getRange(sh.getLastRow() + 1, 1, 1, row.length).setValues([row]);
    return _json({ ok: true });
  }

  // ─── [진단] BOT_TOKEN 확인 + 문의 알림 방 테스트 발송 (시모 2026-06-24, 일회용) ───
  if (action === 'ping_inquiry_notify') {
    var diagToken = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
    if (!diagToken) return _json({ ok: false, error: 'BOT_TOKEN 미설정 — GAS ScriptProperties에 추가 필요' });
    var diagChatId = _prop('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
    var diagMsg = '✅ [진단] GAS BOT_TOKEN 확인됨. 문의 알림 방 발송 정상 (시모 2026-06-24)';
    try {
      var diagRes = UrlFetchApp.fetch('https://api.telegram.org/bot' + diagToken + '/sendMessage', {
        method: 'post', contentType: 'application/json',
        payload: JSON.stringify({ chat_id: diagChatId, text: diagMsg }),
        muteHttpExceptions: true
      });
      return _json({ ok: true, token_len: diagToken.length, chat_id: diagChatId, tg_code: diagRes.getResponseCode() });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
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

    // GM A안(2026-06-20): 실무진 처리 화면(문의DB=26년 신규문의)에도 미러 기록 → 즉시 처리 가능. fail-soft.
    _mirrorInquiryToStaffLog_(body, id);

    _notifyTelegram(
      '🔔 <b>[신규 문의]</b>\n'
      + '이름: ' + (body.name || '-') + '\n'
      + '연락처: ' + (body.phone || '-') + '\n'
      + '유형: ' + (body.type || '-') + '\n'
      + '유입채널: ' + (body.inflow || '-') + '\n'
      + '내용: ' + (body.message || '-').substring(0, 100),
      _prop('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK
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
    if (csHit && !_nc) return _json(JSON.parse(csHit));

    const sh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    const last = sh.getLastRow();
    if (last < 2) return _json({ ok: true, total: 0, byLink: {}, byLinkUrl: {}, byUtmSource: {}, from: csFrom, to: csTo });

    var data = sh.getRange(2, 1, last - 1, CLICK_HEADERS.length).getValues();
    // 기간 필터 (from/to 둘 다 있을 때만 · 시각=인덱스 1). 없으면 누적.
    if (csFrom && csTo) {
      var csF = new Date(csFrom + 'T00:00:00+09:00').getTime();
      var csT = new Date(csTo + 'T23:59:59+09:00').getTime();
      data = data.filter(function(row) {
        var t = row[1] ? _normTs_(row[1]).getTime() : NaN;  // 문의 집계와 동일 정규화(공백→T·KST) — 클릭 누락 버그 수정
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
    try { csCache.put(csCacheKey, JSON.stringify(csResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(csResult);
  }

  // ─── 콘텐츠별 클릭 집계 (campaign_stats) ───
  // UTM캠페인(슬러그)별 클릭 수·최다 채널 집계. 빈 캠페인은 '직접/기타'로 분류.
  if (action === 'campaign_stats') {
    var campFrom = body.from || '';
    var campTo   = body.to   || '';
    var campCache = CacheService.getScriptCache();
    var campKey = 'camp_v1_' + campFrom + '_' + campTo;
    var campHit = campCache.get(campKey);
    if (campHit && !_nc) return _json(JSON.parse(campHit));

    var campSh = _getSheet(CLICK_SHEET, CLICK_HEADERS);
    var campLast = campSh.getLastRow();
    if (campLast < 2) return _json({ ok: true, total: 0, campaigns: [], from: campFrom, to: campTo });

    var campData = campSh.getRange(2, 1, campLast - 1, CLICK_HEADERS.length).getValues();
    // 기간 필터 (click_stats 와 동일 패턴)
    if (campFrom && campTo) {
      var campF = new Date(campFrom + 'T00:00:00+09:00').getTime();
      var campT = new Date(campTo   + 'T23:59:59+09:00').getTime();
      campData = campData.filter(function(row) {
        var t = row[1] ? _normTs_(row[1]).getTime() : NaN;
        return !isNaN(t) && t >= campF && t <= campT;
      });
    }

    // UTM캠페인(인덱스 8) · UTM소스(인덱스 4) 집계
    var campMap = {};  // { campaignKey: { clicks, channels: { src: n } } }
    campData.forEach(function(row) {
      var raw = String(row[8] || '').trim();
      var key = raw || '직접·기타';
      if (!campMap[key]) campMap[key] = { clicks: 0, channels: {} };
      campMap[key].clicks++;
      var src = String(row[4] || '').trim() || '직접/홈';
      campMap[key].channels[src] = (campMap[key].channels[src] || 0) + 1;
    });

    // 최다 채널 산출 + 클릭 내림차순 정렬
    var campArr = Object.keys(campMap).map(function(slug) {
      var d = campMap[slug];
      var topCh = '', topN = 0;
      Object.keys(d.channels).forEach(function(ch) {
        if (d.channels[ch] > topN) { topN = d.channels[ch]; topCh = ch; }
      });
      return { campaign: slug, clicks: d.clicks, topChannel: topCh };
    });
    campArr.sort(function(a, b) { return b.clicks - a.clicks; });

    var campResult = { ok: true, total: campData.length, campaigns: campArr, from: campFrom, to: campTo };
    try { campCache.put(campKey, JSON.stringify(campResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(campResult);
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

  // ─── 문의회원 페이지(CPO): 익명 문의 목록 (A안 공개·이름/전화/메모 0) ───
  if (action === 'member_inquiry_list') {
    var miRows = _miReadRows_();
    return _json({ ok: true, count: miRows.length, data: miRows, anon: true });
  }

  // ─── 문의회원 페이지(CPO): 행 추가 (전화·직접 문의 수기 입력) ───
  if (action === 'member_inquiry_add') {
    var maSh = _miSheet_();
    if (!maSh) return _json({ ok: false, error: '시트 없음' });
    var maHdr = _miHeaders_(maSh);
    var maRow = new Array(maHdr.length).fill('');
    function _maSet(colNames, val) {
      if (val === undefined || val === null || val === '') return;
      var ci = _miColIdx_(maHdr, colNames);
      if (ci >= 0) maRow[ci] = val;
    }
    var maNow = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
    if (!body.name && !body.phone) return _json({ ok: false, error: '이름 또는 전화번호 필수' });
    _maSet(['성함','이름'], body.name);
    _maSet(['연락처','전화','휴대폰'], body.phone);
    _maSet(['관심 있는 프로그램 종류','관심프로그램','프로그램'], body.program);
    _maSet(['진행현황','진행상황','진행상태','상태'], body.status || '신규');
    _maSet(['문의채널','유입채널','채널','경로'], body.channel || '유선전화');
    _maSet(['담당','담당자'], body.owner);
    _maSet(['메모','비고','담당자메모'], body.memo);
    _maSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], body.tour);
    _maSet(['체험1 확정시간','체험1'], body.exp1);
    _maSet(['체험2 확정시간','체험2'], body.exp2);
    _maSet(['타임스탬프','접수일','날짜'], body.timestamp || maNow);
    maSh.appendRow(maRow);
    if (body.status === 'SUC' || body.status === '단기SUC') {
      try { _regUpsert_(body.name, body.phone, body.program); } catch (e) {}
    }
    try { _notifyTelegram('➕ 전화·직접 문의 추가 — ' + (body.name || '(이름없음)') + ' · ' + (body.phone || '-') + ' · 채널:' + (body.channel || '유선전화')); } catch (e) {}
    return _json({ ok: true, message: '추가되었습니다.', rowIndex: maSh.getLastRow() });
  }

  // ─── 문의회원 페이지(CPO): 예약 달력 (익명·상담/체험 일정) ───
  if (action === 'member_calendar') {
    var mcMonth = String(body.month || '');  // 'YYYY-MM'
    var mcRows = _miReadRows_();
    var mcEvents = [];
    mcRows.forEach(function(row){
      function add(dateStr, kind, timeStr) {
        if (!dateStr) return;
        if (mcMonth && dateStr.slice(0,7) !== mcMonth) return;
        mcEvents.push({ date: dateStr, kind: kind, time: timeStr || '', name: '', program: row.program, status: row.status });
      }
      add(row.tourDate, '상담', row.tourTime);
      add(row.exp1, '체험', row.exp1Time);
      add(row.exp2, '체험', row.exp2Time);
    });
    return _json({ ok: true, month: mcMonth, count: mcEvents.length, events: mcEvents });
  }

  // ─── 문의회원 페이지(CPO): 행 수정 (이름·전화·진행상태·관심프로그램·메모·담당·일정) ───
  //   2026-06-22 GM '전체 공개' — 실명·전화도 수정 대상. 빈문자는 의도적 클리어로 간주(undefined만 스킵).
  if (action === 'member_inquiry_update') {
    var muRow = parseInt(body.rowIndex, 10);
    if (!muRow || muRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var muSh = _miSheet_();
    if (!muSh) return _json({ ok: false, error: '시트 없음' });
    var muHdr = _miHeaders_(muSh);
    function _muSet(colNames, val) {
      if (val === undefined || val === null) return;
      var ci = _miColIdx_(muHdr, colNames);
      if (ci >= 0) muSh.getRange(muRow, ci + 1).setValue(val);
    }
    _muSet(['성함','이름'], body.name);
    _muSet(['연락처','전화','휴대폰'], body.phone);
    _muSet(['관심 있는 프로그램 종류','관심프로그램','프로그램'], body.program);
    _muSet(['진행현황','진행상황','진행상태','상태'], body.status);
    _muSet(['문의채널','유입채널','채널','경로'], body.channel);
    _muSet(['메모','비고','담당자메모'], body.memo);
    _muSet(['담당','담당자'], body.owner);
    _muSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], body.tour);
    _muSet(['체험1 확정시간','체험1'], body.exp1);
    _muSet(['체험2 확정시간','체험2'], body.exp2);
    // carry-over: SUC/단기SUC = 등록회원 → 등록현황 탭 자동 이관(문의명단에서 넘어감)
    if (body.status === 'SUC' || body.status === '단기SUC') {
      try { _regUpsert_(body.name, body.phone, body.program); } catch (e) {}
    }
    try { _notifyTelegram('📝 문의회원 수정(공개페이지) — 행 ' + muRow + ' · 상태:' + (body.status || '-') + ' · 담당:' + (body.owner || '-')); } catch (e) {}
    return _json({ ok: true, rowIndex: muRow, message: '수정되었습니다.' });
  }

  // ─── 문의회원 페이지(CPO): 행 삭제 ───
  if (action === 'member_inquiry_delete') {
    var mdRow = parseInt(body.rowIndex, 10);
    if (!mdRow || mdRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var mdSh = _miSheet_();
    if (!mdSh) return _json({ ok: false, error: '시트 없음' });
    if (mdRow > mdSh.getLastRow()) return _json({ ok: false, error: '행 범위 초과' });
    mdSh.deleteRow(mdRow);
    try { _notifyTelegram('🗑 문의회원 삭제(공개페이지) — 행 ' + mdRow); } catch (e) {}
    return _json({ ok: true, rowIndex: mdRow, message: '삭제되었습니다.' });
  }

  // ─── UTM 귀속(파일럿): 구글폼에 '유입경로(자동)' 텍스트 항목 추가 + prefill entry ID 회수 (2026-06-23 ship113) ───
  //   ★ 가드 필수 — 폼을 실제로 변형하므로 _SURVEY_PUBLIC_ACTIONS 화이트리스트에 절대 넣지 않는다.
  //     비밀 파라미터 key === _ADD_UTM_GUARD 일치할 때만 실행(무단호출 차단).
  //   멱등: 이미 '유입경로(자동)' 항목이 있으면 추가하지 않고 기존 entry ID만 회수.
  //   동작: FormApp.openById → 편집권한 확인 → (없으면 추가) → createResponse().toPrefilledUrl()에서 entry.<숫자> 추출 반환.
  if (action === 'add_utm_field') {
    if (String(body.key || '') !== _ADD_UTM_GUARD) {
      return _json({ ok: false, error: 'guard-mismatch' });
    }
    var aufFormId = String(body.formId || '').trim();
    var aufViewUrl = String(body.viewUrl || '').trim();   // forms.gle/d/e/ 게시 URL — 편집 file ID 미상일 때
    var aufSearchHint = String(body.searchHint || '').trim(); // DriveApp 검색 폴백용 제목 키워드(예: '성인'·'유소년'·'여름')
    var aufListOnly = (String(body.listOnly || '') === '1'); // 진단: 검색 후보만 반환(폼 미변형)
    // ─── 진단 모드: 제목 키워드로 편집가능 폼 후보 전부 나열(변형 없음) — 정확한 file ID 식별용 ───
    if (aufListOnly) {
      if (!aufSearchHint) return _json({ ok: false, error: 'searchHint 필수(listOnly)' });
      var aufCands = [];
      try {
        var lit = DriveApp.searchFiles(
          'mimeType = "application/vnd.google-apps.form" and title contains "' + aufSearchHint.replace(/"/g, '') + '" and trashed = false');
        while (lit.hasNext()) {
          var lf = lit.next();
          var canEdit = false, pub = '';
          try { var lform = FormApp.openById(lf.getId()); lform.getEditUrl(); canEdit = true; pub = lform.getPublishedUrl(); } catch (le) {}
          aufCands.push({ id: lf.getId(), name: lf.getName(), canEdit: canEdit, publishedUrl: pub });
        }
      } catch (e) { return _json({ ok: false, error: 'driveSearch-failed', detail: String(e) }); }
      return _json({ ok: true, listOnly: true, hint: aufSearchHint, count: aufCands.length, candidates: aufCands });
    }
    if (!aufFormId && !aufViewUrl) return _json({ ok: false, error: 'formId 또는 viewUrl 필수' });
    var aufForm = null;
    var aufResolveLog = [];
    // ① formId 직접 지정 시 우선
    if (aufFormId) {
      try { aufForm = FormApp.openById(aufFormId); aufForm.getEditUrl(); }
      catch (e) { aufResolveLog.push('openById:' + String(e)); aufForm = null; }
    }
    // ② viewUrl → openByUrl 시도 (※ forms.gle 게시 URL은 편집ID와 달라 실패할 수 있음 → 검증)
    if (!aufForm && aufViewUrl) {
      try {
        var f2 = FormApp.openByUrl(aufViewUrl); f2.getEditUrl();
        // 게시 URL 일치 검증 — openByUrl이 엉뚱한 폼을 반환하지 않았는지 확인(오결합 방지)
        if (String(f2.getPublishedUrl()).indexOf(aufViewUrl.replace('/viewform', '')) >= 0 ||
            aufViewUrl.indexOf(String(f2.getId())) >= 0) {
          aufForm = f2;
        } else {
          aufResolveLog.push('openByUrl-mismatch:got=' + f2.getId());
        }
      }
      catch (e) { aufResolveLog.push('openByUrl:' + String(e)); }
    }
    // ③ DriveApp 검색 폴백 — 단 후보가 정확히 1개(편집가능)일 때만 사용(다중매칭=오결합 위험 → 거부)
    if (!aufForm && aufSearchHint) {
      try {
        var fit = DriveApp.searchFiles(
          'mimeType = "application/vnd.google-apps.form" and title contains "' + aufSearchHint.replace(/"/g, '') + '" and trashed = false');
        var editable = [];
        while (fit.hasNext()) {
          var df = fit.next();
          try { var f3 = FormApp.openById(df.getId()); f3.getEditUrl(); editable.push(f3); }
          catch (e3) { /* 편집불가 후보 무시 */ }
        }
        if (editable.length === 1) { aufForm = editable[0]; }
        else if (editable.length > 1) { aufResolveLog.push('driveSearch-ambiguous:' + editable.length + '개 매칭 → listOnly로 확인 필요'); }
        else { aufResolveLog.push('driveSearch-none'); }
      } catch (e) { aufResolveLog.push('driveSearch:' + String(e)); }
    }
    if (!aufForm) {
      return _json({ ok: false, error: 'no-access', detail: aufResolveLog.join(' | ') });
    }
    var AUF_TITLE = '유입경로(자동)';
    // 멱등: 동일 제목 텍스트 항목 탐색
    var aufItem = null;
    var aufTextItems = aufForm.getItems(FormApp.ItemType.TEXT);
    for (var ai = 0; ai < aufTextItems.length; ai++) {
      if (String(aufTextItems[ai].getTitle()).trim() === AUF_TITLE) { aufItem = aufTextItems[ai]; break; }
    }
    var aufCreated = false;
    if (!aufItem) {
      aufForm.addTextItem()
        .setTitle(AUF_TITLE)
        .setHelpText('자동 입력 항목 — 비워두셔도 됩니다')
        .setRequired(false);
      aufCreated = true;
    }
    // prefill entry ID 회수: 제목으로 Item을 다시 조회(addTextItem 반환값/멱등 조회값 타입 불일치 회피) →
    //   .asTextItem().createResponse('__PROBE__') → form.createResponse().withItemResponse(...).toPrefilledUrl()
    //   → URL에서 entry.<숫자>=__PROBE__ 정규식으로 entry 번호 추출.
    var aufEntryId = '';
    try {
      var aufLookup = null;
      var aufAllText = aufForm.getItems(FormApp.ItemType.TEXT);
      for (var aj = 0; aj < aufAllText.length; aj++) {
        if (String(aufAllText[aj].getTitle()).trim() === AUF_TITLE) { aufLookup = aufAllText[aj]; break; }
      }
      if (!aufLookup) return _json({ ok: false, error: 'item-not-found-after-add', created: aufCreated });
      var aufTextItem = aufLookup.asTextItem();
      var aufResp = aufForm.createResponse().withItemResponse(aufTextItem.createResponse('__PROBE__'));
      var aufPrefillUrl = aufResp.toPrefilledUrl();
      var aufMatch = aufPrefillUrl.match(/entry\.(\d+)=__PROBE__/);
      if (!aufMatch) aufMatch = aufPrefillUrl.match(/entry\.(\d+)/);  // 폴백
      aufEntryId = aufMatch ? aufMatch[1] : '';
    } catch (e) {
      return _json({ ok: false, error: 'prefill-failed', detail: String(e), created: aufCreated });
    }
    return _json({
      ok: true,
      entryId: aufEntryId,
      created: aufCreated,
      formId: aufForm.getId(),
      viewUrl: aufForm.getPublishedUrl(),
      title: AUF_TITLE
    });
  }

  // ─── 회원관리 페이지(CPO): 등록회원 명단 조회 (등록기간 from~to 필터, 1~12월 체크 포함) ───
  if (action === 'member_registered_list') {
    var rlSh = _regSheet_();
    var rlLast = rlSh.getLastRow();
    var rlRows = [];
    if (rlLast >= 2) {
      var rlData = rlSh.getRange(2, 1, rlLast - 1, _REG_HEADER.length).getValues();
      var rlFrom = String(body.from || '');  // YYYY-MM-DD (doGet이 쿼리를 body로 병합)
      var rlTo   = String(body.to   || '');
      for (var ri = 0; ri < rlData.length; ri++) {
        var rr = rlData[ri];
        if (!rr[0] && !rr[1]) continue;  // 빈 행 스킵
        var regDate = _miToISO_(rr[3]);
        if (rlFrom && regDate && regDate < rlFrom) continue;
        if (rlTo   && regDate && regDate > rlTo)   continue;
        var months = [];
        for (var m = 0; m < 12; m++) {
          var cv = rr[4 + m];
          months.push(cv === true || cv === 1 || (typeof cv === 'string' && cv.trim() !== ''));
        }
        rlRows.push({
          rowIndex: ri + 2,
          name:     String(rr[0] || ''),
          phone:    String(rr[1] || ''),
          program:  String(rr[2] || ''),
          regDate:  regDate,
          months:   months
        });
      }
    }
    return _json({ ok: true, count: rlRows.length, data: rlRows });
  }

  // ─── 회원관리 페이지(CPO): 등록회원 월별 체크 토글 ───
  if (action === 'member_registered_setmonth') {
    var smPhone = _regNormPhone_(body.phone);
    var smMonth = parseInt(body.month, 10);  // 1~12
    var smChecked = (body.checked === true || body.checked === 'true' || body.checked === 1 || body.checked === '1');
    if (!smPhone || !(smMonth >= 1 && smMonth <= 12)) return _json({ ok: false, error: 'phone·month(1~12) 필수' });
    var smSh = _regSheet_();
    var smLast = smSh.getLastRow();
    if (smLast < 2) return _json({ ok: false, error: '등록회원 없음' });
    var smData = smSh.getRange(2, 2, smLast - 1, 1).getValues();  // 전화 열
    for (var si = 0; si < smData.length; si++) {
      if (_regNormPhone_(smData[si][0]) === smPhone) {
        smSh.getRange(si + 2, 4 + smMonth).setValue(smChecked ? 'O' : '');  // col5=1월 … col16=12월
        return _json({ ok: true, message: '저장됨', phone: smPhone, month: smMonth, checked: smChecked });
      }
    }
    return _json({ ok: false, error: '해당 등록회원 없음' });
  }

  // ─── 회원관리 페이지(CPO): 등록 해제(등록현황 행 삭제, 전화 키) ───
  if (action === 'member_registered_delete') {
    var rdPhone = _regNormPhone_(body.phone);
    if (!rdPhone) return _json({ ok: false, error: 'phone 필수' });
    var rdSh = _regSheet_();
    var rdLast = rdSh.getLastRow();
    if (rdLast < 2) return _json({ ok: false, error: '등록회원 없음' });
    var rdData = rdSh.getRange(2, 2, rdLast - 1, 1).getValues();  // 전화 열
    for (var di = 0; di < rdData.length; di++) {
      if (_regNormPhone_(rdData[di][0]) === rdPhone) {
        rdSh.deleteRow(di + 2);
        try { _notifyTelegram('➖ 등록 해제 — ' + (body.name || rdPhone)); } catch (e) {}
        return _json({ ok: true, message: '등록 해제되었습니다.' });
      }
    }
    return _json({ ok: false, error: '해당 등록회원 없음' });
  }

  // ─── 회원관리 페이지(CPO): 멤버십 회원 명단 ('유효회원' 시트, 읽기전용·전화 마스킹) ───
  //   scope=valid(기본): 잔여일>0 유효회원(2026-06-24 GM) / scope=ended: 종료·이탈(잔여일≤0 또는 LOSS·환불·양도LOSS)
  //   ★빈 헤더·쓰레기 날짜헤더(GMT/표준시) 컬럼 제외 + 회원명 없는 빈/이상 행 제외(전체 컬럼은 그대로 노출).
  if (action === 'member_active_list') {
    var aaScope = (String(body.scope || 'valid') === 'ended') ? 'ended' : 'valid';
    var aaSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!aaSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var aaLast = aaSh.getLastRow();
    var aaCols = aaSh.getLastColumn();
    if (aaLast < 1 || aaCols < 1) return _json({ ok: true, scope: aaScope, headers: [], count: 0, data: [] });
    var aaHdrRaw = aaSh.getRange(1, 1, 1, aaCols).getValues()[0].map(function(v){ return String(v).trim(); });
    // 유지 컬럼: 빈 헤더·GMT/표준시 쓰레기 날짜헤더 제외
    var aaKeep = aaHdrRaw.map(function(h){ return h && !/GMT|표준시/.test(h); });
    var aaHdrs = [];
    for (var ah = 0; ah < aaHdrRaw.length; ah++) if (aaKeep[ah]) aaHdrs.push(aaHdrRaw[ah]);
    // 핵심 컬럼 인덱스(공백·줄바꿈 무시) — 헤더가 '잔여일\n(일)'·'재등록\n분류'라 정규화 매칭
    function _aaIdx(want){ var w = String(want).replace(/\s/g,''); for (var i=0;i<aaHdrRaw.length;i++){ if (aaHdrRaw[i].replace(/\s/g,'').indexOf(w) >= 0) return i; } return -1; }
    var aiName = _aaIdx('회원명'), aiRem = _aaIdx('잔여일'), aiRe = _aaIdx('재등록분류');
    var aiCha = _aaIdx('등록회차'), aiCls = _aaIdx('등록분류');  // 등록회차>=2 → 등록분류 '재등록' 표시규칙용
    var _AA_LOSS = { 'LOSS':1, '환불':1, '양도LOSS':1 };
    var aaRows = [];
    if (aaLast >= 2) {
      var aaData = aaSh.getRange(2, 1, aaLast - 1, aaCols).getValues();
      for (var ai = 0; ai < aaData.length; ai++) {
        var arow = aaData[ai];
        var nm = aiName >= 0 ? String(arow[aiName] == null ? '' : arow[aiName]).trim() : '';
        if (!nm) continue;  // 회원명 없는 빈/이상 행 제외
        var remRaw = aiRem >= 0 ? String(arow[aiRem] == null ? '' : arow[aiRem]).replace(/[^0-9\-]/g, '') : '';
        var rem = (remRaw === '' || remRaw === '-') ? NaN : parseInt(remRaw, 10);
        var reV = aiRe >= 0 ? String(arow[aiRe] == null ? '' : arow[aiRe]).trim() : '';
        var isValid = !isNaN(rem) && rem > 0 && !_AA_LOSS[reV];  // 유효 = 잔여일>0 & 이탈표시 없음
        if (aaScope === 'valid' && !isValid) continue;
        if (aaScope === 'ended' && isValid) continue;   // 종료 = 유효가 아닌 모든 회원명 보유 행
        var obj = { rowIndex: ai + 2 };   // 시트 실제 행번호(인라인 수정 저장용)
        for (var ac = 0; ac < aaHdrRaw.length; ac++) {
          if (!aaKeep[ac]) continue;
          var key = aaHdrRaw[ac];
          var v = arow[ac];
          if (v instanceof Date && !isNaN(v.getTime())) v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
          v = (v === null || v === undefined) ? '' : String(v);
          if (key === MEMBER_PHONE_COL) { var pp = v.replace(/[^0-9]/g, ''); v = pp.length >= 10 ? pp.slice(0,3) + '-****-' + pp.slice(-4) : (pp ? '***' : ''); }
          obj[key] = v;
        }
        // 등록회차>=2 → 등록분류 '재등록' 표시(시트 미변경 · 표시 규칙) 2026-06-24 GM
        if (aiCls >= 0) {
          var _chaM = (aiCha >= 0 ? String(arow[aiCha] == null ? '' : arow[aiCha]) : '').match(/\d+/);
          if (_chaM && parseInt(_chaM[0], 10) >= 2) obj[aaHdrRaw[aiCls]] = '재등록';
        }
        aaRows.push(obj);
      }
    }
    return _json({ ok: true, scope: aaScope, headers: aaHdrs, count: aaRows.length, data: aaRows });
  }

  // ─── 멤버십 회원관리: 셀 인라인 수정(유효회원 시트 write-back · 전화 컬럼 제외) 2026-06-24 GM ───
  if (action === 'member_active_update') {
    var auRow = parseInt(body.rowIndex, 10);
    if (!auRow || auRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var auCol = String(body.col || '').trim();
    if (!auCol) return _json({ ok: false, error: 'col 필수' });
    if (auCol.replace(/\s/g, '').indexOf('휴대폰') >= 0) return _json({ ok: false, error: '전화번호는 마스킹 표시라 여기서 수정 불가(시트에서 직접)' });
    var auSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!auSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var auHdr = auSh.getRange(1, 1, 1, auSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    var _auW = auCol.replace(/\s/g, '');
    var auIdx = -1;
    for (var au1 = 0; au1 < auHdr.length; au1++) { if (auHdr[au1].replace(/\s/g, '') === _auW) { auIdx = au1; break; } }
    if (auIdx < 0) { for (var au2 = 0; au2 < auHdr.length; au2++) { if (auHdr[au2] && auHdr[au2].replace(/\s/g, '').indexOf(_auW) >= 0) { auIdx = au2; break; } } }
    if (auIdx < 0) return _json({ ok: false, error: '컬럼 미발견: ' + auCol });
    auSh.getRange(auRow, auIdx + 1).setValue(body.value == null ? '' : String(body.value));
    return _json({ ok: true, rowIndex: auRow, col: auCol });
  }

  // ─── CPO 오늘 현황(PII 미노출 집계): 오늘/이번달 문의·등록 건수 2026-06-24 GM ───
  if (action === 'cpo_today_stats') {
    var ctTz = 'Asia/Seoul';
    var ctToday = Utilities.formatDate(new Date(), ctTz, 'yyyy-MM-dd');
    var ctMonth = ctToday.slice(0, 7);
    var ctTI = 0, ctMI = 0, ctTR = 0, ctMR = 0;
    // 문의: 26년 신규문의 타임스탬프
    try {
      var ciSh = _miSheet_();
      if (ciSh && ciSh.getLastRow() >= 2) {
        var ciH = _miHeaders_(ciSh);
        var ciTs = _miColIdx_(ciH, ['타임스탬프','접수일','날짜']);
        var ciNm = _miColIdx_(ciH, ['성함','이름']);
        var ciPg = _miColIdx_(ciH, ['관심 있는 프로그램 종류','관심 있는 프로그램 종목','관심프로그램','프로그램']);
        if (ciTs >= 0) {
          var ciData = ciSh.getRange(2, 1, ciSh.getLastRow() - 1, ciH.length).getValues();
          for (var ci = 0; ci < ciData.length; ci++) {
            if (ciNm >= 0 && !String(ciData[ci][ciNm] || '').trim() && !ciData[ci][ciTs]) continue;
            // 멤버십 문의만(플래티넘·노블레스 계열). 프로그램 칸 없으면 전부 포함(폴백).
            if (ciPg >= 0) { var ciPv = String(ciData[ci][ciPg] || ''); if (ciPv.indexOf('플래티넘') < 0 && ciPv.indexOf('노블레스') < 0) continue; }
            var ciD = _miToISO_(ciData[ci][ciTs]);
            if (ciD === ctToday) ctTI++;
            if (ciD && ciD.slice(0, 7) === ctMonth) ctMI++;
          }
        }
      }
    } catch (eCi) {}
    // 등록: 유효회원 등록일자
    try {
      var crSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
      if (crSh && crSh.getLastRow() >= 2) {
        var crH = crSh.getRange(1, 1, 1, crSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).replace(/\s/g, ''); });
        var crIdx = -1;
        for (var cj = 0; cj < crH.length; cj++) { if (crH[cj].indexOf('등록일자') >= 0) { crIdx = cj; break; } }
        if (crIdx >= 0) {
          var crData = crSh.getRange(2, crIdx + 1, crSh.getLastRow() - 1, 1).getValues();
          for (var cr = 0; cr < crData.length; cr++) {
            var cv = crData[cr][0];
            var crD = (cv instanceof Date && !isNaN(cv.getTime())) ? Utilities.formatDate(cv, ctTz, 'yyyy-MM-dd') : _miToISO_(cv);
            if (crD === ctToday) ctTR++;
            if (crD && crD.slice(0, 7) === ctMonth) ctMR++;
          }
        }
      }
    } catch (eCr) {}
    return _json({ ok: true, date: ctToday, todayInquiry: ctTI, monthInquiry: ctMI, todayReg: ctTR, monthReg: ctMR });
  }

  // ─── 문의→가입 전환 집계 ───
  if (action === 'funnel_conversion') {
    // from/to(YYYY-MM-DD KST) 있으면 그 범위로 문의·전환 필터, 없으면 전체 누적(하위호환). 2026-06-23 시모.
    var fcFrom = body.from || '';
    var fcTo   = body.to   || '';
    var fcPeriod = !!(fcFrom && fcTo);
    var fcF = fcPeriod ? new Date(fcFrom + 'T00:00:00+09:00').getTime() : 0;
    var fcT = fcPeriod ? new Date(fcTo   + 'T23:59:59+09:00').getTime() : 0;
    function _fcInPeriod(ts) {
      if (!fcPeriod) return true;
      var t = ts ? _normTs_(ts).getTime() : NaN;   // 단일 정규화 SSOT(클릭/문의 통일)
      return !isNaN(t) && t >= fcF && t <= fcT;
    }
    // 캐시 조회 (범위별 키 — 기간 필터 버전)
    var fcCache = CacheService.getScriptCache();
    var fcCacheKey = 'fc_v2_' + fcFrom + '_' + fcTo;
    var fcHit = fcCache.get(fcCacheKey);
    if (fcHit && !_nc) return _json(JSON.parse(fcHit));

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
      var idxDateFc  = INQUIRY_HEADERS.indexOf('시각');     // 1

      inqData.forEach(function(row) {
        if (!_fcInPeriod(row[idxDateFc])) return;   // 기간 필터(미지정=전체 누적)
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
      if (!_fcInPeriod(f.시각)) return;   // 기간 필터(미지정=전체 누적)
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
      periodMode: fcPeriod,
      period: { from: fcFrom, to: fcTo },
      convBasis: fcPeriod
        ? '문의=선택기간(시각 기준) / 전환=선택기간 문의 중 유효회원 전화매칭(등록일 미사용 → 기간 내 문의가 전환된 누적값)'
        : '전체 누적 — 유효회원 전화매칭',
      generatedAt: _now()
    };
    // 캐시 저장 (범위별 키 — 100KB 초과 시 생략)
    try { fcCache.put(fcCacheKey, JSON.stringify(fcResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
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
    if (tcHit && !_nc) return _json(JSON.parse(tcHit));

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
      var t = row.시각 ? _normTs_(row.시각).getTime() : NaN;  // 단일 정규화 SSOT — 클릭/문의 파싱 통일(공백→T·KST)
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
    try { tcCache.put(tcCacheKey, JSON.stringify(tcResult), 1800); } catch (e) { /* 캐시 실패 무시 */ }
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
    if (pbHit && !_nc) return _json(JSON.parse(pbHit));

    // ── 기간 시작 시각 계산 (Asia/Seoul 달력 기준) ──
    function _periodStarts_() {
      var now = new Date();
      // Seoul 현지 날짜·요일 문자열로 기준점 산출
      var seoulNowStr = Utilities.formatDate(now, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
      var todayStr    = seoulNowStr.substring(0, 10); // 'yyyy-MM-dd'

      // 이번 주 = 최근 7일(오늘 포함 직전 7일, 롤링) — GM 정의 2026-06-17
      // (구 '월요일 기준'은 주초엔 1~2일치만 잡혀 실제 일주일 등록/문의와 어긋남)
      var weekAgoDate = new Date(now.getTime() - 6 * 86400000);
      var weekStr = Utilities.formatDate(weekAgoDate, 'Asia/Seoul', 'yyyy-MM-dd');

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
        var d = _normTs_(ts);  // 단일 정규화 SSOT(click_stats 와 동일 파싱)
        if (isNaN(d.getTime())) return;
        if (d >= ps.monthStart) month++;
        if (d >= ps.weekStart)  week++;
        if (d >= ps.dayStart)   day++;
      });
      return { day: day, week: week, month: month };
    }

    // 타임스탬프(Date|string) → Date 변환 헬퍼 (단일 정규화 SSOT _normTs_ 위임)
    function _toDate_(ts) { return _normTs_(ts); }

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

    // ── 유형별 등록 현황 — 기간별 집계 (2026-06-17 기간연동 확장) ──
    // 등록 = 진행현황(상태) 값이 SUC 또는 단기SUC인 행. 날짜 = B열 기준.
    // 기간: day·week·month·year + custom(from/to 있을 때). 문의와 동일 cohort.
    // 강습: 진행현황 없으면 null(프론트 → '—' + '누적' 주석).

    // yearStart 산출 (이번 연도 1월 1일 00:00 +09:00)
    var yearStr   = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy') + '-01-01';
    var yearStart = new Date(yearStr + 'T00:00:00+09:00');

    // 시트 하나에서 기간별 SUC 카운트를 한 번에 추출 — rows 재사용
    function _countRegAllPeriods_(sh, last, lastCol) {
      if (!sh || last < 2 || lastCol < 1) return null;
      try {
        var hdrs = sh.getRange(1, 1, 1, lastCol).getValues()[0];
        // 팀시트 상태 헤더 = '진행 상황'(띄어쓰기) → '상황'·'진행 상황' 키 포함 필수(붙여쓰기만으론 미매칭)
        var idxStatus = _findCol_(hdrs, ['진행현황', '진행 상황', '진행상황', '진행상태', '상황', '상태']);
        // 날짜 = '타임스탬프'(13개 팀시트·멤버십 전부 공통). '문의일'은 PT·필라에만 있고 실제 등록(SUC)시점과 어긋나 미사용(2026-06-17 프로브 실측: PT 6월 등록 2건은 타임스탬프 기준만 포착).
        var idxDate   = _findCol_(hdrs, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
        if (idxDate < 0) idxDate = 0;
        if (idxStatus < 0) return null; // 진행현황 컬럼 없으면 집계 불가
        var rows = sh.getRange(2, 1, last - 1, lastCol).getValues();
        var day = 0, week = 0, month = 0, year = 0, custom = 0;
        var cFrom = (from && to) ? new Date(from + 'T00:00:00+09:00') : null;
        var cTo   = (from && to) ? new Date(to   + 'T23:59:59+09:00') : null;
        rows.forEach(function(r) {
          var dateRaw = r[idxDate];
          if (!dateRaw) return;
          var d = _toDate_(_parseAnyDate_(dateRaw));
          if (isNaN(d.getTime())) return;
          if (!_isLessonReg_(r[idxStatus])) return;
          if (d >= ps.dayStart)   day++;
          if (d >= ps.weekStart)  week++;
          if (d >= ps.monthStart) month++;
          if (d >= yearStart)     year++;
          if (cFrom && cTo && d >= cFrom && d <= cTo) custom++;
        });
        return { day: day, week: week, month: month, year: year, custom: (cFrom ? custom : null) };
      } catch (e) { return null; }
    }

    // 유형별 집계 누산기 초기화
    var regByType = {};

    // 멤버십 — FORM_SHEETS[0] (26년 신규문의 스태프 로그, 진행현황 컬럼 있음)
    try {
      var memCfg = FORM_SHEETS[0];
      var memSh  = _sheetByGid_(memCfg.ssId, memCfg.gid);
      var memRes = _countRegAllPeriods_(memSh, memSh ? memSh.getLastRow() : 0, memSh ? memSh.getLastColumn() : 0);
      regByType['멤버십'] = memRes; // null이면 프론트 '—'
    } catch (e) { regByType['멤버십'] = null; }

    // 강습 — LESSON_TEAM_SHEETS 유형별 합산 (날짜 기준 기간별)
    try {
      var lCounts = { '성인강습': { day:0,week:0,month:0,year:0,custom:0 },
                      '유소년강습': { day:0,week:0,month:0,year:0,custom:0 } };
      var lFound  = { '성인강습': false, '유소년강습': false };
      LESSON_TEAM_SHEETS.forEach(function(cfg) {
        try {
          var lsh = _sheetByGid_(cfg.ssId, cfg.gid);
          var lr  = _countRegAllPeriods_(lsh, lsh ? lsh.getLastRow() : 0, lsh ? lsh.getLastColumn() : 0);
          if (lr !== null) {
            var b = lCounts[cfg.유형];
            b.day   += lr.day;   b.week  += lr.week;
            b.month += lr.month; b.year  += lr.year;
            if (lr.custom !== null) b.custom += lr.custom;
            lFound[cfg.유형] = true;
          }
        } catch (e) { /* 팀시트 접근 실패 무시 */ }
      });
      ['성인강습', '유소년강습'].forEach(function(tp) {
        regByType[tp] = lFound[tp] ? lCounts[tp] : null;
      });
    } catch (e) { /* 강습 등록 집계 실패 무시 */ }

    var pbResult = {
      ok:          true,
      generatedAt: _now(),
      periods: {
        dayStart:   ps.dayStr,
        weekStart:  ps.weekStr,
        monthStart: ps.monthStr,
        yearStart:  yearStr
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
      regByType: regByType  // 기간별 등록: {멤버십:{day,week,month,year,custom}, 성인강습:…, 유소년강습:…}
    };
    if (customObj !== null) pbResult.custom = customObj;

    // 캐시 저장 (100KB 초과 시 생략)
    try { pbCache.put(pbKey, JSON.stringify(pbResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(pbResult);
  }

  // ─── 전환 단계 퍼널 (5단계 누적 깔때기) ───
  if (action === 'stage_funnel') {
    // 캐시 조회
    var sfCache = CacheService.getScriptCache();
    var sfHit   = sfCache.get('sf_v1');
    if (sfHit && !_nc) return _json(JSON.parse(sfHit));

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
        var sfIdxMemo = _findCol_(sfHeaders, ['비고', '메모']);  // [웹접수] 표식 탐지용
        var sfRows = sfSh.getRange(2, 1, sfLast - 1, sfLastCol).getValues();
        sfRows.forEach(function(r) {
          if (!r[sfIdxDate] && (sfIdxPhone < 0 || !r[sfIdxPhone])) return; // 빈 행 스킵
          // CTA 웹폼 미러 행([웹접수])은 문의접수(④-a)로 이미 집계 → 제외(이중집계 방지)
          if (sfIdxMemo >= 0 && String(r[sfIdxMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) return;
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
    try { sfCache.put('sf_v1', JSON.stringify(sfResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(sfResult);
  }

  // ─── 주간 추세 (최근 8주 시계열) ───
  if (action === 'weekly_trend') {
    // 캐시 조회
    var wtCache = CacheService.getScriptCache();
    var wtHit = wtCache.get('wt_v1');
    if (wtHit && !_nc) return _json(JSON.parse(wtHit));

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
    try { wtCache.put('wt_v1', JSON.stringify(wtResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(wtResult);
  }

  // ─── 종목별 등록 집계 (대시보드 강습 펼침 — GM 2026-06-18) ───
  // 성인/유소년강습을 GM 지정 종목 단위로 펼쳐 '등록' 수만 반환. 문의는 종목 데이터 없음 → 프론트가 대분류로 표기.
  // 등록 = LESSON_TEAM_SHEETS 팀시트 상태열 SUC/등록 등(_isLessonReg_). 정본 = _collectLessonRegByName_.
  // 정직성: 시트 없는 종목(바레·발레)=registered:null('데이터 미연결'), 0으로 채우지 않음. 시트 있고 등록 0=실측 0.
  if (action === 'lesson_breakdown') {
    var lbFrom = body.from || '';   // YYYY-MM-DD (기간별 문의 집계용)
    var lbTo   = body.to   || '';
    var lbCache = CacheService.getScriptCache();
    var lbKey = 'lb_v2_' + lbFrom + '_' + lbTo;   // 기간별 캐시키
    var lbHit = lbCache.get(lbKey);
    if (lbHit && !_nc) return _json(JSON.parse(lbHit));

    var byName    = _collectLessonRegByName_();              // 등록(누적): { 'P.T 성인': {registered|null,...}, ... }
    var byNameInq = _collectLessonInqByName_(lbFrom, lbTo);  // 문의(기간별): { 'P.T 성인': {inquiries|null,...}, ... }
    var usedSheets = {};
    var data = {};

    // 종목 '명' → 팀시트 cfg 역참조(시트 바로가기 URL 생성)
    var cfgByName = {};
    LESSON_TEAM_SHEETS.forEach(function(cfg) { cfgByName[cfg.명] = cfg; });
    function _lessonSheetUrl(sheetName) {
      var cfg = cfgByName[sheetName];
      return cfg ? ('https://docs.google.com/spreadsheets/d/' + cfg.ssId + '/edit#gid=' + cfg.gid) : null;
    }

    Object.keys(LESSON_DISPLAY).forEach(function(grp) {
      data[grp] = LESSON_DISPLAY[grp].map(function(item) {
        var reg = null, inq = null, src = null, sheetUrl = null;
        if (item.sheet) {
          usedSheets[item.sheet] = true;
          var rec  = byName[item.sheet];
          var recI = byNameInq[item.sheet];
          if (rec)  { reg = rec.registered; src = rec.statusHeader; }  // null이면 그대로(데이터 미연결)
          if (recI) { inq = recI.inquiries; }
          sheetUrl = _lessonSheetUrl(item.sheet);
        }
        return { 명: item.명, registered: reg, inquiries: inq, sheet: item.sheet || null, sheetUrl: sheetUrl, statusSource: src };
      });
    });

    // GM 목록 밖이지만 시트엔 존재하는 종목 → others(누락·날조 금지)
    var others = [];
    LESSON_TEAM_SHEETS.forEach(function(cfg) {
      if (usedSheets[cfg.명]) return;
      var rec  = byName[cfg.명];
      var recI = byNameInq[cfg.명];
      others.push({ 유형: cfg.유형, 명: cfg.명,
        registered: rec ? rec.registered : null,
        inquiries: recI ? recI.inquiries : null,
        sheetUrl: _lessonSheetUrl(cfg.명) });
    });

    // 매칭 안 된(시트 없는) GM 종목 → 프론트 '데이터 미연결' 표기용
    var unmatched = [];
    Object.keys(LESSON_DISPLAY).forEach(function(grp) {
      LESSON_DISPLAY[grp].forEach(function(item) {
        if (!item.sheet) unmatched.push({ 유형: grp, 명: item.명, reason: '등록·문의 데이터 출처 없음' });
      });
    });

    var lbResult = {
      ok: true,
      generatedAt: _now(),
      range: { from: lbFrom, to: lbTo },
      basis: '종목별 문의 = 팀시트 행을 타임스탬프 기준 기간 집계 · 등록 = 팀시트 상태열 수강등록(SUC/등록) 누적 · 시트없는종목(바레·발레)=null(데이터 미연결)',
      data: data,
      others: others,
      unmatched: unmatched
    };
    try { lbCache.put(lbKey, JSON.stringify(lbResult), 1800); } catch (e) { /* 캐시 실패 무시 */ }
    return _json(lbResult);
  }

  // ─── 등록 자동매칭 온디맨드 실행 ───
  if (action === 'member_match_run') {
    var mmResult = member_match_autostamp_();
    return _json({ ok: true, matched: mmResult.matched, total: mmResult.total, error: mmResult.error || null });
  }

  // ─── 문의→등록 평균 전환 소요일 (lead_time_stats) ───────────────
  // 신규문의 시트(gid MATCH_SHEET_GID)에서 문의일(타임스탬프)과 '등록일(자동)'(=#3 자동매칭 스탬프)이
  // 둘 다 있는 행만 추려 소요일 = (등록일 − 문의일)을 일 단위로 계산.
  // ★ 정직성: 음수(등록일<문의일)·비현실치(>730일)는 이상치로 제외하고 제외 건수를 함께 반환(숨기지 않음).
  // 반환: { ok, avgDays, medianDays, n, excluded, from, to }. from/to 있으면 '문의일' 기준 기간 필터.
  // PII 미노출(집계 숫자만) → 공개 액션 화이트리스트 면제 안전.
  if (action === 'lead_time_stats') {
    var ltFrom = body.from || '';   // YYYY-MM-DD (optional) — 문의일 기준 기간
    var ltTo   = body.to   || '';
    var ltCache = CacheService.getScriptCache();
    var ltKey = 'lt_v1_' + ltFrom + '_' + ltTo;
    var ltHit = ltCache.get(ltKey);
    if (ltHit && !_nc) return _json(JSON.parse(ltHit));

    var ltSh = null;
    try { ltSh = _sheetByGid_(MEMBER_SPREADSHEET_ID, MATCH_SHEET_GID); } catch (e) { /* 접근 실패 */ }
    if (!ltSh) return _json({ ok: true, avgDays: null, medianDays: null, n: 0, excluded: 0, from: ltFrom, to: ltTo, note: '신규문의 시트 미발견' });

    var ltLast = ltSh.getLastRow(), ltLastCol = ltSh.getLastColumn();
    if (ltLast < 2 || ltLastCol < 1) return _json({ ok: true, avgDays: null, medianDays: null, n: 0, excluded: 0, from: ltFrom, to: ltTo });

    var ltHeaders = ltSh.getRange(1, 1, 1, ltLastCol).getValues()[0];
    var iInqDate = _findCol_(ltHeaders, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
    if (iInqDate < 0) iInqDate = 0;  // 못 찾으면 1열(타임스탬프 기본)
    var iRegDate = -1;
    for (var lh = 0; lh < ltHeaders.length; lh++) {
      if (String(ltHeaders[lh]).trim() === MATCH_DATE_COL) { iRegDate = lh; break; }
    }
    if (iRegDate < 0) return _json({ ok: true, avgDays: null, medianDays: null, n: 0, excluded: 0, from: ltFrom, to: ltTo, note: "'" + MATCH_DATE_COL + "' 칼럼 미발견 — 자동매칭 미실행?" });

    // 문의일·등록일(자동) 셀 → Date(KST). Date·'YYYY. M. D'·'yyyy-MM-dd[ HH:mm:ss]'·'yyyy/M/d' 모두 흡수.
    function _ltDate(v) {
      if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
      var s = String(v == null ? '' : v).trim();
      if (!s) return null;
      var m = s.match(/(\d{4})[.\-\/]\s*(\d{1,2})[.\-\/]\s*(\d{1,2})/);  // 2026. 6. 5 / 2026-06-05 / 2026/6/5
      if (m) {
        var mm = ('0' + m[2]).slice(-2), dd = ('0' + m[3]).slice(-2);
        var d = new Date(m[1] + '-' + mm + '-' + dd + 'T12:00:00+09:00');  // 정오 고정(일경계 TZ 오차 방지)
        return isNaN(d.getTime()) ? null : d;
      }
      var d2 = new Date(s);
      return isNaN(d2.getTime()) ? null : d2;
    }
    var ltRows = ltSh.getRange(2, 1, ltLast - 1, ltLastCol).getValues();
    var ltF = (ltFrom && ltTo) ? new Date(ltFrom + 'T00:00:00+09:00').getTime() : null;
    var ltT = (ltFrom && ltTo) ? new Date(ltTo   + 'T23:59:59+09:00').getTime() : null;
    var MS_DAY = 86400000;
    var MAX_REALISTIC = 730;  // 2년 초과 = 비현실 이상치(데이터 오류·재등록 등)
    var ltDays = [], ltExcluded = 0;
    ltRows.forEach(function(r) {
      var rawInq = r[iInqDate], rawReg = r[iRegDate];
      if (!rawInq || !rawReg) return;  // 둘 다 있는 행만
      // 문의일=타임스탬프('YYYY. M. D'), 등록일(자동)=Date 또는 'yyyy-MM-dd' 문자열.
      var dInq = _ltDate(rawInq);
      var dReg = _ltDate(rawReg);
      if (!dInq || !dReg) return;
      // 문의일 기준 기간 필터(지정 시)
      if (ltF !== null) { var ti = dInq.getTime(); if (ti < ltF || ti > ltT) return; }
      // 자정 기준 일수 차(시각 노이즈 제거)
      var d0Inq = new Date(dInq.getFullYear(), dInq.getMonth(), dInq.getDate()).getTime();
      var d0Reg = new Date(dReg.getFullYear(), dReg.getMonth(), dReg.getDate()).getTime();
      var diff = Math.round((d0Reg - d0Inq) / MS_DAY);
      if (diff < 0 || diff > MAX_REALISTIC) { ltExcluded++; return; }  // 이상치 제외(건수 보고)
      ltDays.push(diff);
    });

    var ltN = ltDays.length;
    var ltAvg = null, ltMed = null;
    if (ltN > 0) {
      var sum = 0; ltDays.forEach(function(d) { sum += d; });
      ltAvg = Math.round((sum / ltN) * 10) / 10;
      var sorted = ltDays.slice().sort(function(a, b) { return a - b; });
      var mid = Math.floor(ltN / 2);
      ltMed = (ltN % 2 === 0) ? Math.round(((sorted[mid - 1] + sorted[mid]) / 2) * 10) / 10 : sorted[mid];
    }
    var ltResult = { ok: true, avgDays: ltAvg, medianDays: ltMed, n: ltN, excluded: ltExcluded, from: ltFrom, to: ltTo };
    try { ltCache.put(ltKey, JSON.stringify(ltResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(ltResult);
  }

  return _json({ ok: false, error: '알 수 없는 action: ' + action });
}

// ═══════════════════════════════════════════
//  #3 등록 자동매칭 — 신규문의 시트에 등록상태 자동 스탬프
//  신규문의 시트 등록상태 자동 스탬프 · 진행상황 칼럼 불변 · 배포=clasp push→웹앱 새버전
// ═══════════════════════════════════════════

// 신규문의 시트 gid (FORM_SHEETS[0] 과 동일 — 멤버십 '26년 신규문의')
var MATCH_SHEET_GID = 1902010032;
var MATCH_STAMP_COL  = '등록매칭(자동)';
var MATCH_DATE_COL   = '등록일(자동)';

/**
 * member_match_autostamp_()
 * 유효회원 시트(MEMBER_SPREADSHEET_ID/유효회원 탭)에서 (정규화 전화 → 등록일) 맵을 구성하고,
 * 신규문의 시트(gid 1902010032)의 각 행 연락처와 매칭하여
 * '등록매칭(자동)' / '등록일(자동)' 칼럼을 스탬프한다.
 * - 두 칼럼이 없으면 맨 오른쪽에 생성(있으면 재사용).
 * - '진행상황' 등 기존 칼럼은 읽기만 하며 절대 수정하지 않는다.
 * - 멱등: 재실행 안전(기존 스탬프 덮어쓰기, 매칭 없으면 빈 문자열).
 * 반환: { matched, total }
 */
function member_match_autostamp_() {
  // ① 유효회원 시트 → (정규화전화 → 등록일) 맵
  var memberMap = {};
  try {
    var mSs   = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var mSh   = mSs.getSheetByName(MEMBER_SHEET);
    var mLast = mSh ? mSh.getLastRow() : 0;
    if (mSh && mLast >= 2) {
      var mHeaders   = mSh.getRange(1, 1, 1, mSh.getLastColumn()).getValues()[0];
      // 공백·줄바꿈 무시 매칭 — 유효회원 헤더가 '등록\n일자'(줄바꿈)라 exact indexOf 실패하던 버그 수정(2026-06-23).
      function _mHdrIdx(name) {
        var want = String(name).replace(/\s+/g, '');
        for (var hi = 0; hi < mHeaders.length; hi++) {
          if (String(mHeaders[hi]).replace(/\s+/g, '') === want) return hi;
        }
        return -1;
      }
      var mPhoneIdx  = _mHdrIdx(MEMBER_PHONE_COL);
      var mDateIdx   = _mHdrIdx(MEMBER_DATE_COL);
      if (mPhoneIdx >= 0) {
        var mColCount = mSh.getLastColumn();
        var mData = mSh.getRange(2, 1, mLast - 1, mColCount).getValues();
        mData.forEach(function(r) {
          var ph = normalizePhone_(r[mPhoneIdx]);
          if (ph) {
            var regDate = mDateIdx >= 0 ? r[mDateIdx] : '';
            memberMap[ph] = regDate;
          }
        });
      }
    }
  } catch (e) {
    Logger.log('member_match_autostamp_: 유효회원 시트 오픈 실패 — ' + e.message);
    return { matched: 0, total: 0, error: e.message };
  }

  // ② 신규문의 시트 열기
  var inqSh = null;
  try {
    inqSh = _sheetByGid_(MEMBER_SPREADSHEET_ID, MATCH_SHEET_GID);
  } catch (e) { /* 스프레드시트 공유 문제 등 */ }
  if (!inqSh) {
    Logger.log('member_match_autostamp_: 신규문의 시트(gid ' + MATCH_SHEET_GID + ') 미발견');
    return { matched: 0, total: 0, error: '신규문의 시트 미발견' };
  }

  var inqLast    = inqSh.getLastRow();
  var inqLastCol = inqSh.getLastColumn();
  if (inqLast < 2 || inqLastCol < 1) return { matched: 0, total: 0 };

  // ③ 헤더 행 확인 — 전화·등록매칭·등록일 칼럼 인덱스 결정
  var headers = inqSh.getRange(1, 1, 1, inqLastCol).getValues()[0];

  var phoneIdx = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화']);

  // '등록매칭(자동)' 칼럼: 없으면 맨 오른쪽에 추가
  var stampColIdx = -1;
  for (var hi = 0; hi < headers.length; hi++) {
    if (String(headers[hi]).trim() === MATCH_STAMP_COL) { stampColIdx = hi; break; }
  }
  if (stampColIdx < 0) {
    stampColIdx = inqLastCol;  // 0-based → 열 번호는 +1
    inqSh.getRange(1, stampColIdx + 1).setValue(MATCH_STAMP_COL);
  }

  // '등록일(자동)' 칼럼: 없으면 등록매칭 바로 오른쪽에 추가
  var dateColIdx = -1;
  // 헤더를 다시 읽어 최신 상태 반영
  var headersNow = inqSh.getRange(1, 1, 1, inqSh.getLastColumn()).getValues()[0];
  for (var hj = 0; hj < headersNow.length; hj++) {
    if (String(headersNow[hj]).trim() === MATCH_DATE_COL) { dateColIdx = hj; break; }
  }
  if (dateColIdx < 0) {
    dateColIdx = stampColIdx + 1;
    inqSh.getRange(1, dateColIdx + 1).setValue(MATCH_DATE_COL);
  }

  // ④ 각 문의 행 순회 — 매칭 후 스탬프
  if (phoneIdx < 0) {
    Logger.log('member_match_autostamp_: 연락처 칼럼 미발견');
    return { matched: 0, total: 0, error: '연락처 칼럼 미발견' };
  }

  var rowCount  = inqLast - 1;
  var readCols  = Math.max(phoneIdx + 1, stampColIdx + 1, dateColIdx + 1);
  var dataRange = inqSh.getRange(2, 1, rowCount, readCols);
  var dataVals  = dataRange.getValues();

  var matched = 0;
  var stampUpdates = [];  // [[stampVal, dateVal], ...]
  dataVals.forEach(function(row) {
    var ph = normalizePhone_(row[phoneIdx]);
    if (ph && memberMap.hasOwnProperty(ph)) {
      var regDate = memberMap[ph];
      var dateStr = '';
      if (regDate instanceof Date) {
        dateStr = Utilities.formatDate(regDate, 'Asia/Seoul', 'yyyy-MM-dd');
      } else if (regDate) {
        dateStr = String(regDate).trim();
      }
      stampUpdates.push(['등록', dateStr]);
      matched++;
    } else {
      stampUpdates.push(['', '']);
    }
  });

  // ⑤ 배치 쓰기 (등록매칭·등록일 두 칼럼 동시)
  var stampRange = inqSh.getRange(2, stampColIdx + 1, rowCount, 1);
  var dateRange  = inqSh.getRange(2, dateColIdx  + 1, rowCount, 1);
  var stampVals  = stampUpdates.map(function(p) { return [p[0]]; });
  var dateVals2  = stampUpdates.map(function(p) { return [p[1]]; });
  stampRange.setValues(stampVals);
  dateRange.setValues(dateVals2);

  Logger.log('member_match_autostamp_: matched=' + matched + ' / total=' + rowCount);
  return { matched: matched, total: rowCount };
}

/** 공개 트리거용 래퍼 (Apps Script 트리거는 인자 없는 최상위 함수여야 함) */
function memberMatchAutostamp() {
  return member_match_autostamp_();
}

/**
 * installMemberMatchTrigger()
 * 매일 새벽 2시(Asia/Seoul) member_match_autostamp_ 를 실행하는 시간 트리거를 설치한다.
 * 동일 트리거가 이미 있으면 중복 생성하지 않는다.
 * ★ 이 함수는 Apps Script 편집기에서 수동으로 1회 실행한다(공개 — 실행 드롭다운에 보임).
 */
function installMemberMatchTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'memberMatchAutostamp') {
      Logger.log('installMemberMatchTrigger_: 트리거 이미 존재 — 중복 설치 생략');
      return '이미 존재';
    }
  }
  ScriptApp.newTrigger('memberMatchAutostamp')
    .timeBased()
    .everyDays(1)
    .atHour(2)
    .inTimezone('Asia/Seoul')
    .create();
  Logger.log('installMemberMatchTrigger_: 매일 02:00(KST) 트리거 설치 완료');
  return '설치 완료';
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

// ─── 대시보드 캐시 워머 (2026-06-19 시토) ────────────────────────────────
// 시간 트리거가 5분마다 호출 → 무거운 집계(type_channel·funnel_conversion 등)를
// nocache=1로 강제 재계산해 캐시를 미리 데움 → 사용자는 항상 캐시 히트(~1.5초).
// Claude/LLM 토큰 무관(구글 서버 실행). 자기 /exec 호출이라 새 OAuth 스코프 없음.
var _WARM_EXEC_URL = 'https://script.google.com/macros/s/AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec';

function warmDashboardCache() {
  // 대시보드 초기 로드와 동일 범위(이번 달 1일~오늘, KST)로 키 정합.
  var tz = 'Asia/Seoul';
  var now = new Date();
  var from = Utilities.formatDate(now, tz, 'yyyy-MM') + '-01';
  var to   = Utilities.formatDate(now, tz, 'yyyy-MM-dd');
  var range = '&from=' + from + '&to=' + to;
  var qs = [
    'action=funnel_conversion',                 // fc_v1 (범위 무관)
    'action=type_channel_breakdown' + range,    // tc — 가장 무거움
    'action=click_stats' + range,
    'action=period_breakdown' + range
  ];
  qs.forEach(function(q) {
    try {
      UrlFetchApp.fetch(_WARM_EXEC_URL + '?' + q + '&nocache=1', { muteHttpExceptions: true, followRedirects: true });
    } catch (e) { /* 개별 실패 무시 — 다음 주기 재시도 */ }
  });
}

// 워머 트리거 설치/제거 — GM이 GAS 에디터에서 1회 실행(ScriptApp 스코프 인가).
function installWarmTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'warmDashboardCache') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('warmDashboardCache').timeBased().everyMinutes(5).create();
  warmDashboardCache(); // 즉시 1회 데움
  return '워머 트리거 설치 완료(5분 주기) + 즉시 1회 실행';
}

function removeWarmTrigger() {
  var n = 0;
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'warmDashboardCache') { ScriptApp.deleteTrigger(t); n++; }
  });
  return '워머 트리거 ' + n + '개 제거';
}

// ─── [일회용 진단] 영문 문의 응답탭 gid 조회 (시모, 2026-06-24) ──────────────
// 목적: FORM_SHEETS 에 영문 폼 3종(멤버십·공간렌트·비즈니스파트너 영문) gid 를 추가하기 위해
//       두 스프레드시트의 전체 탭 목록과 gid 를 Logger 에 출력한다.
// 실행법: GAS 에디터 상단 함수 선택창에서 listInquirySheetTabs 선택 → 실행(▶) → 실행 로그 확인.
// 결과 이용: 영문 헤더 또는 English/영문/EN 이 탭명·헤더에 포함된 탭의 gid 를 FORM_SHEETS 에 등록.
function listInquirySheetTabs() {
  var targets = [
    { label: '멤버십/공간/파트너 시트', ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U' },
    { label: '강습 시트',               ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw' }
  ];

  targets.forEach(function(t) {
    Logger.log('==============================');
    Logger.log('[' + t.label + '] ssId=' + t.ssId);
    Logger.log('==============================');

    var ss;
    try { ss = SpreadsheetApp.openById(t.ssId); }
    catch (e) { Logger.log('  ERROR: 시트 열기 실패 — ' + e.message); return; }

    var sheets = ss.getSheets();
    sheets.forEach(function(sh) {
      var name   = sh.getName();
      var gid    = sh.getSheetId();
      var lastCol = sh.getLastColumn();
      var headerPreview = '';

      if (lastCol > 0 && sh.getLastRow() > 0) {
        try {
          var hdrs = sh.getRange(1, 1, 1, Math.min(lastCol, 6)).getValues()[0];
          headerPreview = hdrs.map(function(v) { return String(v || '').trim(); })
                              .filter(function(v) { return v; })
                              .join(' | ');
        } catch (e2) { headerPreview = '(헤더 읽기 오류)'; }
      } else {
        headerPreview = '(빈 탭)';
      }

      // 영문 탭 여부 표시 — 탭명 또는 첫 헤더에 English/영문/EN/english 포함
      var isEn = /english|영문|\bEN\b/i.test(name) || /english|영문|\bEN\b/i.test(headerPreview);
      var mark = isEn ? '  ★ [영문 후보]' : '';

      Logger.log('  탭명="' + name + '" gid=' + gid + mark);
      Logger.log('  헤더=' + (headerPreview || '(없음)'));
    });
  });

  Logger.log('==============================');
  Logger.log('완료. 위 gid 를 FORM_SHEETS 영문 항목에 입력하세요.');
}
