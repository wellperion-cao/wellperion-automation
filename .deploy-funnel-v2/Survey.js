// 웰페리온 랜딩 페이지 추적 Apps Script v1.0
// 리틀리(litt.ly) 대체 — 문의 추적 → 시트 누적
// 시트: 문의접수 (클릭 지수는 2026-07 GM 결정으로 전면 삭제)

// ─── 상수 ───
const LANDING_SPREADSHEET_ID = '1g9Ohmd8C_WxyvWt9EX58oEFZLiOAJ_EG7t7XteJFuGE';
const INQUIRY_SHEET = '문의접수';
// QA 격리 전용 탭(2026-07-30 시토, 배195) — submit_inquiry 를 qa=1+토큰으로 부르면 여기로만 쓴다.
// 라이브 문의접수 시트·26년 신규문의 미러·텔레그램 발송을 전혀 안 타서, 애초에 실무진 화면·KPI를
// 더럽히지 않는다(가 안: "쓰기 자체를 생략"은 저장 왕복 검증을 못 해 기각 — 배195 note 참고).
// _getSheet()가 없으면 INQUIRY_HEADERS 그대로 자동 생성한다(첫 QA 호출 시점, 배포 전엔 생성 안 함).
const QA_INQUIRY_SHEET = '문의접수_QA';

// 회원부 시트 (유효회원 탭)
const MEMBER_SPREADSHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
const MEMBER_SHEET = '유효회원';
/* LOSS 보관 시트 — 2026-08-13 GM 지시("1년 단위로 옮기자"). 지난 연도에 LOSS 된 분들을 여기로 옮겨
   유효회원 시트를 가볍게 유지한다. 실측: 1,697행 → 1,191행(30% 감소), 조회 8~11초 → 5.6~7.7초.
   ▸숫자는 안 줄어든다 — LOSS 누적 인원을 세는 곳들은 이 시트 행 수를 더해서 낸다(아래 _lossArchiveCount_).
     시트를 훑지 않고 마지막 행 번호만 읽으므로 속도에 영향이 없다.
   ▸옮긴 분이 재등록하면 그때 유효회원 시트에 새 줄로 등록한다(원래 하던 방식 그대로). */
const MEMBER_ARCHIVE_SHEET = 'LOSS보관';
const MEMBER_CORP_SHEET_NAME = '법인현황';   // 법인 회원 원장 — 이름은 폴백일 뿐, 실제로는 아래 gid 로 찾는다
const MEMBER_CORP_SHEET_GID = 1612064257;   // member_active_list scope='corp' 과 같은 탭(이름이 달라 gid 가 정본)
// ★회원번호(2026-08-26 GM 승인 · 배801 / 2026-08-27 GM 지시로 별도 탭 폐지) — 사람마다 평생 안 바뀌는 번호.
//   번호는 원장 탭(유효회원·법인·LOSS보관)의 '회원번호' 칸에 산다. 같은 진실을 담던 '회원등기부' 탭은
//   지웠다 — 번호·이름·전화만 중복으로 갖고 있었고, 관계 칸은 처음부터 비어 있었다(약속 L01).
//   상세 = status/briefs/CPO-2026-08-26-회원도메인-이행설계.md
const MEMBER_REGISTRY_KEY_COL = '회원번호';
const MEMBER_PHONE_COL = '휴대폰 번호';   // 회원부 전화번호 헤더
const MEMBER_DATE_COL  = '등록 일자';      // 회원부 등록일 헤더

const INQUIRY_HEADERS = ['id', '시각', '이름', '연락처', '문의유형', '내용', '유입채널', 'UTM소스', 'UTM미디엄', '상태', '메모'];

const INQUIRY_TYPES = ['투어 예약', '프로그램 문의', '멤버십 상담', '시설 안내', '기타'];

// ─── 문의 내용(자유서술) 칼럼 탐지 키워드 (시토 2026-06-29 GM '내용도 같이') — 구글폼 응답시트의 자유서술 칸 탐지. 구체 표현 우선(_findCol_은 키워드 순서대로 첫 매치). 칸 없으면 idx<0 → 알림에서 '내용' 줄 자동 생략(무중단). ───
var INQUIRY_CONTENT_KEYS = ['문의 내용', '문의내용', '상담 내용', '상담내용', '남기실 말씀', '하실 말씀', '문의 사항', '문의사항', '요청 사항', '요청사항', '궁금하신 점', '궁금한 점', '추가 문의', '하고 싶은 말', '전달 사항', '메시지', '내용', 'Message', 'Comments', 'Inquiry Details', 'Details', 'Your Message'];

// ─── 구글폼 응답 시트 (실제 문의 — 자체폼 휴면 대체, 2026-06-05) ───
// 5채널 콘텐츠 → wellperion.com/ko/inquiry → 구글폼 작성 → 각 폼 응답시트 누적.
// 대시보드(inquiry_list·funnel_conversion)가 이 응답들을 읽어 '문의수=0' 빈틈을 메움.
// gid 기반 탭 조회(이름 변경에 강함). 컬럼은 헤더 키워드로 탐색(폼 문항 순서 변동 대비).
// ※ 여름특강(5종 하위폼)은 구조 미확정 → 추후 추가.
const FORM_SHEETS = [
  { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1902010032, type: '멤버십',     channelKeys: ['채널', '경로', '알게'],  programKeys: ['관심 있는 프로그램 종목', '종목', '프로그램'] },  // '26년 신규문의' 스태프 로그
  { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 111889422, type: '성인강습',   channelKeys: ['경로', '채널'],          programKeys: ['성인 강습 종목', '종목', '과목'] },
  { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 268994754, type: '유소년강습', channelKeys: ['경로', '채널'],          programKeys: ['WSC 강습 종목', '종목', '과목'] }
  // ─── 신규 2종 틀 (시모·GM 2026-06-12 승인 — 공간 렌트·비즈니스 파트너) ───
  // ★ 준비중: GM이 구글폼 2개 생성 후 ① ssId=실제 응답 스프레드시트 ID ② gid='__GID__'→실제 응답탭 gid(숫자)
  //   로 교체하고, 아래 두 줄 앞의 주석(//)을 풀어 활성화한다.
  //   ⚠️ gid 가 문자열 '__GID__' 인 상태에서는 _sheetByGid_ 매칭(=== 숫자 비교)이 실패 → 자동 스킵(무중단).
  //   ⚠️ clasp push ≠ 웹앱 배포 — gid 교체 후 새 버전 웹앱 재배포 1회(GM/CTO) 필요. (명세: 문의_신규유형_폼설계_260612.md §5)
  , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 2014877540, type: '공간렌트',       channelKeys: ['경로', '채널', '알게'] }  // 2026-06-15 멤버십 시트로 통합
  , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1356708303, type: '비즈니스파트너', channelKeys: ['경로', '채널', '알게'] }  // 2026-06-15 멤버십 시트로 통합
  // ─── 영문 문의 3종 (시모 2026-06-24) — 3종 모두 폐기 ───
  // 멤버십 영문폼 폐기(GM 2026-07-23): '26년 신규문의(영)' 탭 접수 0건(전 기간) → 시트 삭제 예정.
  //   영어 문의는 자체 폼으로 전환돼 한글 탭에 '유입언어'·[영어] 표식으로 함께 쌓인다(탭 분리 불필요).
  //   ★삭제 순서 = 폼 응답 받기 중지 → 이 참조 제거(지금) → 시트 삭제. 순서를 바꾸면 구글이 새 응답탭을
  //   만들어 영어 문의가 아무도 안 보는 곳에 쌓인다(2026-07-09 CRM 누락 사고와 동일 함정).
  // , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1887747109, type: '멤버십(영문)',    channelKeys: ['How Did You Hear About Us?', '경로', '채널'], programKeys: ['Programs of Interest', '종목', '프로그램'] }
  // 영문 강습폼 2종 폐기(GM 2026-07-22): 1-1 성인강습(영) 접수 0건 → 삭제 / 2-1 WSC강습(영) 4건 → 메인 WSC탭 이관 후 삭제.
  //   재개 시 새 폼 gid로 세 줄 복원.
  // , { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 311319200,  type: '성인강습(영문)',  channelKeys: ['How Did You Hear About Us?', '경로', '채널'], programKeys: ['Program of Interest', '종목', '과목'] }
  // , { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 931249179,  type: '유소년강습(영문)', channelKeys: ['How Did You Hear About Us?', '경로', '채널'], programKeys: ['WSC Program of Interest', '종목', '과목'] }
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

// 0-based 열 인덱스 → A1 열문자(예 0→A, 15→P, 25→Z, 26→AA, 27→AB). 열 삭제 시 사람이 읽을 대상 표기용.
function _colLetter_(idx0) {
  var n = idx0 + 1, s = '';
  while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
  return s;
}
function _sheetByGid_(ssId, gid) {
  var sheets = SpreadsheetApp.openById(ssId).getSheets();
  for (var i = 0; i < sheets.length; i++) { if (sheets[i].getSheetId() === gid) return sheets[i]; }
  return null;
}

// 2026-07-20 시포: 기존엔 헤더를 앞칸부터 훑어 아무 키나 먼저 걸리는 칸을 반환 → '26년 신규문의' 탭처럼
//   '날짜'(A)·'타임스탬프'(B)가 별도 칸으로 공존하는 시트에서 키리스트에 '날짜'가 섞여 있으면(예:
//   ['타임스탬프',...,'날짜']) 의도는 B였는데 A가 먼저 걸려 반환되는 버그(_mirrorInquiryToStaffLog_·
//   diag_inquiry_ts·_collectFormInquiries_ 등 다수 호출부 공용). _miColIdx_와 동일하게 키 우선순위대로
//   정확일치를 먼저 훑고, 그래도 없으면 기존 부분일치 폴백 — 모호성 있는 시트에서만 결과가 바뀌고
//   단일 후보뿐인 시트는 기존과 동일하게 동작(회귀 없음).
function _findCol_(headers, keys) {
  for (var k = 0; k < keys.length; k++) {
    for (var i = 0; i < headers.length; i++) { if (String(headers[i] || '') === keys[k]) return i; }
  }
  for (var i = 0; i < headers.length; i++) {
    var h = String(headers[i] || '');
    for (var k = 0; k < keys.length; k++) { if (h.indexOf(keys[k]) >= 0) return i; }
  }
  return -1;
}

// 정확일치 전용 컬럼 탐색 — 부분일치 충돌(예: '담당' ↔ '접수담당자') 방지. 2026-06-26 시우.
function _findColExact_(headers, keys) {
  for (var k = 0; k < keys.length; k++) {
    for (var i = 0; i < headers.length; i++) {
      if (String(headers[i] || '').trim() === keys[k]) return i;
    }
  }
  return -1;
}

// 전화번호 정규화(숫자만) — 행키(rowIndex) 검증용 안정키 비교에 사용. 2026-06-26 시우.
function _normPhone_(v) { return String(v == null ? '' : v).replace(/[^0-9]/g, ''); }

// 회원 유효/종료 단일 판정(약속 L01 — 판정 로직 복제 금지). member_active_list·cpo_today_stats·
//   member_active_summary·member_owner_bulk_set 4곳이 각자 이 계산을 복제해 갖고 있다가, 잔여일
//   미기재(NaN)를 member_active_list 만 '유효'로(배286 2026-08-01), 나머지 3곳은 여전히 '종료'로
//   세는 짝 누락이 났다(웰리 실측 배354 2026-08-04 — 신규등록 직후 회원이 생기면 요약카드와
//   명단이 말없이 갈린다). 이제 모두 이 함수 하나를 부른다.
//   유효 = (잔여일>=0 또는 잔여일 미기재) & 재등록분류가 이탈표시(LOSS/환불/양도LOSS)가 아님.
//   remCell/reVCell = 시트 원본 셀 값(파싱 전) 그대로 넘긴다.
var MEMBER_LOSS_TAGS_ = { 'LOSS': 1, '환불': 1, '양도LOSS': 1 };
/* LOSS 보관 시트에 들어 있는 인원 수. 시트를 훑지 않고 마지막 행 번호만 읽는다(비용 거의 0).
   LOSS 누적을 세는 자리들이 이 값을 더해, 옮기기 전과 **같은 숫자**를 유지한다(화면 숫자 안 바뀜). */
function _lossArchiveCount_(ss) {
  try {
    var sh = (ss || SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID)).getSheetByName(MEMBER_ARCHIVE_SHEET);
    if (!sh) return 0;
    var last = sh.getLastRow();
    return last > 1 ? last - 1 : 0;
  } catch (e) { return 0; }
}
function _memberIsValid_(remCell, reVCell) {
  var remRaw = String(remCell == null ? '' : remCell).replace(/[^0-9\-]/g, '');
  var rem = (remRaw === '' || remRaw === '-') ? NaN : parseInt(remRaw, 10);
  var reV = String(reVCell == null ? '' : reVCell).trim();
  return (isNaN(rem) || rem >= 0) && !MEMBER_LOSS_TAGS_[reV];
}

// keyPhone(정규화)로 시트에서 대상 물리 행 탐색 — rowIndex가 어긋났을 때(예: gviz 압축 인덱스·시트 편집 밀림)
// 올바른 행을 복구해 저장이 엉뚱한 행으로 가지 않게 한다. phCol0=전화 컬럼(0-based). 반환=물리 행(1-based, ≥2) 또는 -1.
// 첫 일치 반환(동일 전화 중복은 드묾·기존 rowIndex 검증과 동일 노출). 2026-07-13 시포(INC-013 근본수리).
function _findRowByPhone_(sh, phCol0, keyPhoneNorm) {
  if (!sh || phCol0 < 0 || !keyPhoneNorm) return -1;
  var last = sh.getLastRow();
  if (last < 2) return -1;
  var col = sh.getRange(2, phCol0 + 1, last - 1, 1).getValues();
  for (var i = 0; i < col.length; i++) {
    if (_normPhone_(col[i][0]) === keyPhoneNorm) return i + 2;
  }
  return -1;
}

// keyPhone(정규화) 매칭 행 '개수'를 센다 — _findRowByPhone_은 첫매칭만 반환해 중복 전화(동일 번호 2행+)에서
// 엉뚱한 쪽으로 오지목할 수 있다(실측 7쌍). 2건+ 이면 첫매칭 강제진행 금지·거부해야 한다(fail-closed).
// 2026-07-22 시포(오지목 근본수리 봉합 B2, GM 지시).
function _countRowsByPhone_(sh, phCol0, keyPhoneNorm) {
  if (!sh || phCol0 < 0 || !keyPhoneNorm) return 0;
  var last = sh.getLastRow();
  if (last < 2) return 0;
  var col = sh.getRange(2, phCol0 + 1, last - 1, 1).getValues();
  var n = 0;
  for (var i = 0; i < col.length; i++) {
    if (_normPhone_(col[i][0]) === keyPhoneNorm) n++;
  }
  return n;
}

// ═══ 지문키(rowKey) — 안정 고유키 R1/R2 (2026-07-22 시포, 오지목 근본수리 설계 §4) ═══
// 정규화(타임스탬프)+정규화(연락처) 조합으로 물리행을 지목 — rowIndex·keyPhone(봉합 B1/B2)보다 상위 진실.
// 실측(멤버십 '26년 신규문의' 631행, 2026-07-22): [타임스탬프+연락처] 조합 충돌 0(전원 유일). 새 칸 신설 없음(GM 확정) —
// 기존 값 조합을 자연키(지문)로 사용.
// ★이름 주의: 기존 _normTs_(위, 타임스탬프→Date 변환 SSOT — _countByPeriod_ 등 집계 다수가 의존)와 역할이 다르다.
//   이름 충돌 시 그 SSOT를 덮어써 집계 전체가 깨지므로 절대 재사용 금지 — 신규 헬퍼는 _normTsKey_로 명명(반환값도 Date가
//   아니라 비교용 정규화 '문자열').
// _normTsKey_: Date/구글시리얼(Date 객체)·'yyyy-MM-dd HH:mm:ss'·'YYYY. M. D 오전/오후 H:MM:SS' 한글형식 모두 흡수해
//   'YYYYMMDDHHMMSS'(14자리 숫자열)로 정규화. 프론트(membership.html _gzNormTsKey_)와 바이트 동일 규칙 유지 필수 —
//   연/월/일/시/분/초 숫자를 뽑아 이어붙이는 방식으로 구현(Date.toString() 등 런타임별 표기 차이 회피). gviz Date 객체
//   vs GAS getValue() Date 객체 모두 동일 결과를 내려면 스프레드시트·스크립트 timezone이 둘 다 Asia/Seoul이어야 함
//   (본 프로젝트 전제 — 어긋나면 Utilities.formatDate 명시 지정으로 흡수).
function _normTsKey_(v) {
  function pad(n, len) { var s = String(Math.abs(Math.trunc(Number(n) || 0))); while (s.length < len) s = '0' + s; return s; }
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return '';
    return Utilities.formatDate(v, 'Asia/Seoul', 'yyyyMMddHHmmss');
  }
  var s = String(v).trim();
  if (!s) return '';
  // ISO형: 'YYYY-MM-DD[ T]HH:mm[:ss]' (시분초 없으면 0으로 채움)
  var m1 = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (m1) return pad(m1[1], 4) + pad(m1[2], 2) + pad(m1[3], 2) + pad(m1[4] || 0, 2) + pad(m1[5] || 0, 2) + pad(m1[6] || 0, 2);
  // 한글형: 'YYYY. M. D [오전/오후 H:MM[:SS]]' (예: '2026. 7. 21 오후 2:17:08')
  var m2 = s.match(/^(\d{4})[.\s]+(\d{1,2})[.\s]+(\d{1,2})(?:\s*(오전|오후)?\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (m2) {
    var hh = parseInt(m2[5] || '0', 10);
    if (m2[4] === '오전') { if (hh === 12) hh = 0; }
    else if (m2[4] === '오후') { if (hh !== 12) hh += 12; }
    return pad(m2[1], 4) + pad(m2[2], 2) + pad(m2[3], 2) + pad(hh, 2) + pad(m2[6] || 0, 2) + pad(m2[7] || 0, 2);
  }
  // 미지 포맷 최후 폴백: 숫자만 추출(설계 원칙 기본형 · 무손실 시도 — 완전 매칭 실패보단 낫다)
  return s.replace(/[^0-9]/g, '');
}

// 영문 멤버십 응답탭(gid 1887747109) program 원문 → 한글 표준 매핑(GM 지시, 2026-07-22 시포).
// "Platinum Membership (Access to Gym + Group Exercise Classes + Sauna)" 같은 영문 원문이 관심프로그램 칸에
// 그대로 병합돼 지저분하게 뜨는 문제 — 영문으로 오면 표준 한글값("플래티넘"/"노블레스" [+골프])으로 정규화한다.
// 비파괴: 한글 원문·기타값은 무변경 그대로 통과(국문 탭 데이터 절대 손대지 않음).
function _normMembershipProgram_(v){
  var s = String(v==null?'':v).trim(); if(!s) return s;
  var low = s.toLowerCase();
  var golf = (low.indexOf('golf')>=0 || s.indexOf('골프')>=0);
  if (low.indexOf('platinum')>=0) return golf ? '플래티넘+골프' : '플래티넘';
  if (low.indexOf('noblesse')>=0 || low.indexOf('noble')>=0) return golf ? '노블레스+골프' : '노블레스';
  return s;   // 한글 원문·기타는 무변경(비파괴 — 국문 탭 데이터 절대 손대지 않음)
}

// 지문키(정규화 타임스탬프+정규화 전화) 동시일치 물리행 전부 탐색 — 안정 고유키(§4 R2). tsCol0/phCol0=0-based 컬럼.
// 반환=물리행 배열(1-based,≥2, 보통 0~1건). 매칭 1건=진행/0건·2건+=거부(fail-closed) — 판단은 호출부 책임.
// 2026-07-22 시포(오지목 근본수리 R2).
// ★2026-08-10 시토(배491) — 이름을 세 번째 재료로 더한다(선택·하위호환).
//   왜: 재료가 타임스탬프+전화뿐이라 **부모 번호를 함께 쓰는 형제**가 같은 날 접수되면 지문이
//   100% 같아진다(실측: 조이진·조온동 둘 다 20260716000000|01092842623). 그래서 자동 배정이
//   거부됐고, 한때 '중복행'으로 오해해 삭제 후보로 잡힐 뻔했다(GM 확인: 중복 아니라 자녀들).
//   유효회원 쪽이 더 급하다 — 등록일자는 날짜만이라 같은 날 등록한 가족이 완전히 겹치는데
//   (실측: Maria Campero·Oscar Garcia Chacon), 정렬 자동화가 매일 자정 시트를 재배치하므로
//   옛 화면에서 저장하면 서로 뒤바뀔 위험이 매일 반복된다.
//   ▸keyNameNorm 을 안 주면(옛 화면·이름 칸 없는 시트) 지금까지와 완전히 같은 동작 — 회귀 0.
//     그 경우에도 형제는 2건이 잡혀 fail-closed 로 거부되므로 안전이 약해지지는 않는다.
function _normNameKey_(v) {
  return String(v == null ? '' : v).replace(/\s+/g, '').toLowerCase();
}

// 이름 칸 찾기 — 정확일치 먼저('보호자 이름' 같은 곁칸에 먼저 걸리지 않게), 없으면 부분일치.
// 못 찾으면 -1 이라 이름 대조를 건너뛴다.
function _nameColIdx_(hdr) {
  var EXACT = ['회원명', '성함', '이름', 'name'];
  var i, h, k;
  for (i = 0; i < hdr.length; i++) {
    h = String(hdr[i]).replace(/\s/g, '').toLowerCase();
    for (k = 0; k < EXACT.length; k++) if (h === EXACT[k].toLowerCase()) return i;
  }
  for (i = 0; i < hdr.length; i++) {
    h = String(hdr[i]).replace(/\s/g, '').toLowerCase();
    for (k = 0; k < EXACT.length; k++) if (h.indexOf(EXACT[k].toLowerCase()) >= 0) return i;
  }
  return -1;
}

/** 화면이 보낸 행 하나만 열어 지문이 맞는지 본다. 맞으면 전수 스캔을 건너뛴다 (2026-08-21 시토 · 배740).
 *
 *  왜: _findRowsByKey_ 는 매번 1,000행을 통째로 읽는다. 저장 1건이 8.5초인데 그중 약 1.4초가 이 스캔이다
 *  (시포 실측 — 지문 없이 전화만으로 저장하면 7.1초).
 *
 *  안전한가: 결과가 달라지지 않는다. 전수 스캔이 하는 일은 ①1건이면 그 행 ②0건이면 거부 ③2건 이상이면
 *  '후보 중 rowIndex 와 같은 행'을 고르는 것이다. 그런데 rowIndex 행의 지문이 이미 맞는다면 ①에서도
 *  그 행이고 ③에서도 그 행이다 — 어느 쪽이든 같은 답이 나온다. 안 맞을 때만 종전대로 전수 스캔한다.
 *  ▸그래서 이 함수는 '맞다'일 때만 지름길이고, '아니다'면 아무 판정도 하지 않는다(판정은 원래 자리에서).
 */
function _rowKeyHitsRow_(sh, row, tsCol0, phCol0, keyTsNorm, keyPhoneNorm, nameCol0, keyNameNorm) {
  if (!sh || !row || row < 2 || tsCol0 < 0 || phCol0 < 0 || !keyTsNorm || !keyPhoneNorm) return false;
  if (row > sh.getLastRow()) return false;
  var useName = (nameCol0 != null && nameCol0 >= 0 && !!keyNameNorm);
  var cols = [tsCol0, phCol0];
  if (useName) cols.push(nameCol0);
  var minCol = Math.min.apply(null, cols), maxCol = Math.max.apply(null, cols);
  var v = sh.getRange(row, minCol + 1, 1, maxCol - minCol + 1).getValues()[0];
  if (_normTsKey_(v[tsCol0 - minCol]) !== keyTsNorm) return false;
  if (_normPhone_(v[phCol0 - minCol]) !== keyPhoneNorm) return false;
  if (useName && _normNameKey_(v[nameCol0 - minCol]) !== keyNameNorm) return false;
  return true;
}

function _findRowsByKey_(sh, tsCol0, phCol0, keyTsNorm, keyPhoneNorm, nameCol0, keyNameNorm) {
  var out = [];
  if (!sh || tsCol0 < 0 || phCol0 < 0 || !keyTsNorm || !keyPhoneNorm) return out;
  var last = sh.getLastRow();
  if (last < 2) return out;
  var useName = (nameCol0 != null && nameCol0 >= 0 && !!keyNameNorm);
  var cols = [tsCol0, phCol0];
  if (useName) cols.push(nameCol0);
  var minCol = Math.min.apply(null, cols), maxCol = Math.max.apply(null, cols);
  var data = sh.getRange(2, minCol + 1, last - 1, maxCol - minCol + 1).getValues();
  var tsIdx = tsCol0 - minCol, phIdx = phCol0 - minCol, nmIdx = useName ? (nameCol0 - minCol) : -1;
  for (var i = 0; i < data.length; i++) {
    if (_normTsKey_(data[i][tsIdx]) !== keyTsNorm) continue;
    if (_normPhone_(data[i][phIdx]) !== keyPhoneNorm) continue;
    if (useName && _normNameKey_(data[i][nmIdx]) !== keyNameNorm) continue;
    out.push(i + 2);
  }
  return out;
}

// body.rowKey('tsNorm|phoneNorm', 프론트가 이미 정규화해 조립) 또는 body.keyTs+body.keyPhone(원시값, 서버가 정규화)
// → {ts, phone} 파츠. 정규화 후 둘 다 있어야 유효(하나라도 없으면 null=지문키 미사용→기존 keyPhone 경로로 폴백).
// 2026-07-22 시포(오지목 근본수리 R2).
// ★2026-08-10 시토(배491): 세 번째 파트(이름)를 선택으로 받는다 — 'ts|phone|nameNorm' 또는 body.keyName.
//   안 오면 name='' 이고 그때 동작은 종전과 완전히 동일하다(하위호환·회귀 0).
function _rowKeyParts_(body) {
  var ts = '', ph = '', nm = '';
  if (body.rowKey !== undefined && body.rowKey !== null && String(body.rowKey) !== '') {
    var parts = String(body.rowKey).split('|');
    ts = parts[0] || ''; ph = parts[1] || ''; nm = _normNameKey_(parts[2] || '');
  } else {
    if (body.keyTs !== undefined && body.keyTs !== null && String(body.keyTs) !== '') ts = _normTsKey_(body.keyTs);
    if (body.keyPhone !== undefined && body.keyPhone !== null && String(body.keyPhone) !== '') ph = _normPhone_(body.keyPhone);
  }
  if (!nm && body.keyName !== undefined && body.keyName !== null) nm = _normNameKey_(body.keyName);
  if (!ts || !ph) return null;
  return { ts: ts, phone: ph, name: nm };
}

// ─── 유입채널 표준화 (시모·GM 2026-06-13 확정 — 마케팅용 10버킷) ───
// 자유텍스트(과거 리셉션 + 구글폼 자유입력)로 300여 개 난립한 채널 원문을 표준 10종으로 정규화한다.
// 비파괴: 시트 원본은 손대지 않고, 대시보드 집계(byChannel/byChannelMonth) '읽기 시점'에만 적용.
// ⚠️ 과거 리셉션이 '온라인 (네이버/동커/카카오/인스타)'로 뭉뚱그린 묶음(약 26%)은 단일 채널 귀속이 불가능
//    → '기타·미상'으로 보존(날조 금지). 채널별 ROI는 구글폼 드롭다운(Layer B) 이후 신규 데이터부터 정확해진다.
// 2026-07-20 시모: 회원관리 화면 드롭다운(membership.html CHANNEL_OPTIONS)에는 있던 '유선전화'가
//   이 배열·아래 정규화 함수엔 누락되어 있었다(주석은 "10버킷"인데 실제론 9개 — 정본 불일치).
//   전화 문의는 실제 발생하는 별도 채널(온라인/오프라인 자기신고도 아님)이라 '기타·미상' 흡수가 아니라
//   10번째 버킷으로 복원 — CHANNEL_OPTIONS와 동일 10종으로 통일(정본 판단: 드롭다운 쪽이 먼저 옳았음).
// ★ 2026-07-28 시모 — '네이버' 단일 버킷을 둘로 나누고 '법인·단체'를 신설(총 12버킷).
//   ① 네이버 분리: 문의 폼(wp_inquiry_form.html CHANNELS)은 고객에게 '네이버 검색·플레이스' 와
//      '네이버 블로그' 를 **이미 따로** 물어보고 있었고 시트에도 원문이 그대로 저장돼 있었다
//      (2026-01-02 행까지 실측 확인). 그런데 아래 _canonicalChannel_ 이 읽을 때마다 둘을 '네이버'
//      하나로 합쳐 버려, 최대 유입(1~7월 706건)이 플레이스에서 오는지 블로그에서 오는지 알 수 없었다.
//      플레이스면 할 일은 리뷰·사진 관리이고 블로그면 발행을 늘리는 것 — 정반대 처방인데 구분이 안 됐다.
//      분리 후 실측: 검색·플레이스 701 / 블로그 5. 원문이 살아 있어 과거분까지 소급 적용됐다.
//   ② 법인·단체 신설: 현장 수기 입력값 '법인&단체' 가 어느 규칙에도 안 걸려 '기타·미상' 으로
//      떨어지고 있었다(문의시트 원문 118행 표본에서 2건 발견). 건당 매출 단위가 큰 B2B 유입인데
//      통계에서 통째로 사라진다. 폼 선택지에는 없고 현장에서만 쓰는 값이라 더 안 보였다.
var CANONICAL_CHANNELS = ['네이버 검색·플레이스', '네이버 블로그', '동부이촌동 커뮤니티', '인스타그램',
                          '카카오톡', '당근마켓', '소개·지인', '기존·과거 회원', '법인·단체',
                          '오프라인', '유선전화', '기타·미상'];

function _canonicalChannel_(raw) {
  var s = String(raw == null ? '' : raw).trim();
  if (!s) return '기타·미상';
  // 과거 '온라인 (...)' 묶음 = 다채널 합산 → 단일 귀속 불가
  if (/^온라인\s*[\(（]/.test(s)) return '기타·미상';
  if (/인스타|instagram|insta/i.test(s)) return '인스타그램';
  if (/카카오|카톡|챗톡|쳇톡|챗봇|쳇봇|kakao/i.test(s)) return '카카오톡';
  if (/당근|daangn|danggn/i.test(s)) return '당근마켓';
  if (/동부이촌동|동커|동\.커|이촌동|카페/.test(s)) return '동부이촌동 커뮤니티';
  // ★ 2026-07-28 시모 — 여기서 '네이버' 하나로 뭉개던 것을 둘로 가른다(위 CANONICAL_CHANNELS 주석 참조).
  //   순서 주의: 블로그를 먼저 본다. 폼 원문이 '네이버 블로그' 라 두 정규식에 모두 걸리기 때문.
  //   ※ 정직 표기: 수식어 없이 '네이버' 라고만 적힌 옛 자유텍스트는 '네이버 검색·플레이스' 로 간다.
  //     폼 선택지가 '네이버 검색·플레이스' 라 대부분은 정확히 일치하지만, 그 소수는 추정이다.
  if (/블로그|블러그|blog/i.test(s)) return '네이버 블로그';
  if (/네이버|naver|플레이스|검색|인터넷/i.test(s)) return '네이버 검색·플레이스';  // '지도' 단독 제외('인지도' 오탐 방지·네이버지도는 여기서 포착)
  // ★ 2026-07-28 시모 — 현장 수기값 '법인&단체'. 이 줄이 없으면 '기타·미상' 으로 묻힌다.
  //   '단체' 는 '단체수업' 같은 강습 문의와 겹칠 수 있어 **법인 계열 표현이 있을 때만** 잡는다.
  //   가장 구체적인 신호라 아래 두 버킷보다 먼저 검사(순서 유지).
  if (/법인|기업|회사\s*단체|단체\s*계약|b2b/i.test(s)) return '법인·단체';
  // ★ 2026-07-29 시모(배10359·GM 지시) — '기존·과거 회원'을 '소개·지인'보다 먼저 검사하도록 순서를 바꿨다.
  //   기존 순서(소개·지인 먼저)에서는 "기존 멤버십 회원님/…지인소개 해주신다함"처럼 두 신호가 같이
  //   나오는 실응대 메모가 전부 '소개·지인'으로 흡수돼 '기존·과거 회원'이 과소집계됐다(라이브 원본 6/19 실증).
  //   재유입(기존·과거 회원) 채널이 소개·지인보다 먼저 걸리는 게 맞다 — 반대로 두면 그냥 편향이 방향만 바뀐다.
  if (/회원|가족|자녀|아이|아들|딸|형|누나|언니|동생|둘째|첫째|보호자|학부모|부모|母|수강|강습|다녔|다니|이용|경험|기존|과거|재수강|정회원|연회원|멤버십회원|멤버쉽|wsc|준회원|수강생/i.test(s)) return '기존·과거 회원';
  if (/소개|지인|친구|friend|추천|동기/i.test(s)) return '소개·지인';
  if (/간판|현수막|홍보물|우편|워크인|방문|지나가|지나는|집근처|근처|동네|거주|입주|하이페리온|길에|봤|보여서|아파트|오프라인/.test(s)) return '오프라인';
  if (/^유선\s*전화$|^전화\s*문의$/.test(s)) return '유선전화';  // 회원관리 드롭다운 수기값(정확일치) — '전화'만으로는 오탐 넓어 정확 패턴만
  return '기타·미상';
}

// ─── 유입채널 원문 3단 해석 (대분류→중분류→자동UTM 순서로 override) — 채널 집계·표시 전 지점 공용 SSOT ───
// 2026-07-20 시모(GM 지시): _collectFormInquiries_ 전용이던 로직을 공용 함수로 분리 — 회원관리 화면(_miReadRows_)이
// 대분류 1칸만 읽어 같은 데이터가 M1과 다르게 집계되던 사고(네이버 21건 vs 203건) 재발방지. 두 호출부 모두 이 함수를
// 통해 같은 규칙을 적용한다(로직 복붙 금지). 결과는 canonical 채널명이 아니라 '원문'(_canonicalChannel_ 적용 전) —
// 호출부가 표시용으로 원문을 쓰거나 canonical로 변환하거나 선택 가능.
// 우선순위: ① 대분류(channelKeys, cfg별 상이) 기본값 → ② '중분류' 칸이 canonical 매핑 가능할 때만 override →
//   ③ '유입경로(자동)' 칸(WP 프리필 UTM, source 또는 'source|campaign') 값이 canonical 매핑 가능할 때만 최종 override.
//   매핑 불가(캠페인 슬러그·옥외홍보 등)면 이전 값 유지 — 절대 후퇴 없음(날조 금지).
function _resolveInquiryChannelRaw_(headers, row, channelKeys) {
  var idxChan = _findCol_(headers, channelKeys);
  var idxChanFine = _findCol_(headers, ['중분류']);
  var idxAuto = _findCol_(headers, ['유입경로(자동)', '유입경로자동', '유입경로_자동']);
  var chanRaw = (idxChan >= 0 ? String(row[idxChan] || '').trim() : '');
  if (idxChanFine >= 0) {
    var midRaw = String(row[idxChanFine] || '').trim();
    if (midRaw && _canonicalChannel_(midRaw) !== '기타·미상') chanRaw = midRaw;
  }
  if (idxAuto >= 0) {
    var autoRaw = String(row[idxAuto] || '').trim();
    if (autoRaw) {
      var autoSrc = autoRaw.split('|')[0].trim();
      if (_canonicalChannel_(autoSrc) !== '기타·미상') chanRaw = autoSrc;
    }
  }
  return chanRaw;
}

// ─── 강습 종목 표준 버킷 (시포·GM 2026-06-26) ───
// 자유라벨('성인 수영 (개인레슨/단체레슨)' 등)을 표준 종목으로 집계한다.
// 라벨 통째 쪼개기 금지 — 한 응답이 여러 종목 다중체크면 각 버킷 +1(부분문자열 매칭).
// 어느 버킷에도 안 걸리고 텍스트가 있으면 '기타'로 귀속(날조 금지).
//
// ★★이름 체계가 LESSON_DISPLAY 와 다르다 — 두 목록을 직접 조인하지 말 것(2026-07-27 실사고).
//   이 함수가 내는 이름          : 수영 · 체조 · P.T · 골프 · 스쿼시 · 필라테스 · 아쿠아로빅
//                                 · 발레 · 바레 · 뮤지컬 · 루프메소드(구 통합옵션) · 기타
//   LESSON_DISPLAY 의 종목명     : 위와 같되 '체조' → '체조&트램폴린', 그리고 '모자수영' 별도
//                                 (이 함수는 '모자수영'을 /수영/ 으로 잡아 '수영' 버킷에 넣는다)
//   실사고: 배140 자동복원이 이 함수 결과('체조')를 LESSON_DISPLAY 명('체조&트램폴린')과
//           정확일치로 맞추려다 실패해, 체조로 돌려야 할 2건이 수영·골프로 잘못 붙었다.
//   두 이름공간을 이어야 하면 정확일치 대신 **명시적 별칭/부분일치**를 쓰고, 매칭 실패 시
//   조용히 다른 값으로 폴백하지 말고 '미매칭'으로 남겨라(틀린 귀속 > 미집계).
//   ※ 이 함수의 출력명을 바꾸는 것은 금지 — 퍼널·대시보드 집계가 이 이름으로 붙어 있다.
function _sportBuckets_(raw) {
  var s = String(raw == null ? '' : raw);
  var out = [];
  function hit(re, key) { if (re.test(s)) out.push(key); }
  hit(/수영/, '수영');
  hit(/필라테스|필라/, '필라테스');
  hit(/P\.?T|피티|퍼스널/i, 'P.T');
  hit(/스쿼시/, '스쿼시');
  hit(/골프/, '골프');
  hit(/아쿠아/, '아쿠아로빅');
  // 발레·바레 분리(시토·GM 2026-07-15): 과거 합쳐진 옵션('웰니스 프로그램(바레, 발레)')은 legacy '루프메소드'로 잔류,
  //   신규 단독 '발레'/'바레'는 각각 분리 집계(다중체크면 각 +1). 종목명 표준=순수 '발레'/'바레'.
  if (/웰니스\s*프로그램|바레\s*[,·]\s*발레|발레\s*[,·]\s*바레/.test(s)) {
    out.push('루프메소드');       // legacy 합산 문자열(발레·바레 둘 다 포함) → 잔류 버킷
  } else {
    hit(/발레/, '발레');
    hit(/바레/, '바레');
  }
  hit(/뮤지컬/, '뮤지컬');
  hit(/체조/, '체조');
  if (out.length === 0 && s.trim()) out.push('기타');
  return out;
}

// ─── 진행상태 → 전환 단계 rank 매핑 (설계 SSOT 2026-06-15) ───
// 0=이탈, 1=문의(기본), 2=응대, 3=예약, 4=방문, 5=가입
function _stageOf_(raw) {
  var s = String(raw == null ? '' : raw).trim();
  if (!s) return 1; // 빈칸 → 최소단계(①문의)
  if (/이탈|보류|포기|거절|취소|종료|loss/i.test(s)) return 0;  // '종료'(강습 STATUS_OPTIONS 종착) 추가 — 미인식→문의(1) 오분류 차단
  // SUC / 단기SUC = 수강등록 성공(강습 팀시트 정본값) → 가입(5)
  if (/^(suc|단기\s*suc)$/i.test(s))            return 5;
  // 멤버십 '26년 신규문의' 탭 실사용 코드(2026-06-20 시포 실측): 결제완납·결제완료·완납·키오스크 완 = 가입(5)
  if (/가입|등록|전환|회원|완납|결제완|키오스크\s*완/.test(s)) return 5;
  // 강습 STATUS_OPTIONS: 'OT완료'·'상담완료' = 만난 단계(상담/OT 완료) → 방문(4). '상담예약'은 아래 예약(3)으로 흘려보냄(완료 미포함).
  if (/(ot|상담)\s*완료/i.test(s))               return 4;
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
    // 타임스탬프 = 문자열이 아니라 실제 Date로 기록(2026-07-20 시포·GM). 문자열로 찍으면 시트 서식과 어긋나
    //   'yyyy. M. d'(시분초 유실) / 'yyyy-MM-dd HH:mm:ss'(ISO 혼재) 처럼 같은 칸에 포맷이 섞인다.
    //   Date로 넣으면 시트 자체 서식(yyyy. m. d 오전/오후 h:mm:ss)이 적용돼 시분초 보존 + 정렬·비교 가능.
    put(['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜'], new Date());
    put(['성함', '이름'], body.name || '');
    put(['연락처', '휴대폰', '핸드폰', '전화'], body.phone || '');
    put(['진행현황', '진행상태', '상태'], '신규');
    put(['채널', '경로', '알게'], _canonicalChannel_(body.utmSource || body.inflow || ''));
    // 담당자 기본값 = 임정은 고정(2026-08-08 GM). '웹 자동접수'는 report_stream_1_impl._AUTO_OWNER_VALUES
    //   에서 '실담당자 아님'으로 판정돼 매일 22:30 미배정 알림이 나갔다 — 이 시트(26년 신규문의)로 들어오는
    //   두 경로(이 CTA 미러 · intake_submit 멤버십 분기) 모두 같은 값을 쓴다. 강습은 팀장 배정이라 제외.
    //   웹접수 식별은 비고의 WEB_INTAKE_TAG 가 계속 담당한다(_isWebIntakeRow_ :1420 — 담당자 칸 아님).
    put(['접수 담당자', '담당'], MEMBER_DEFAULT_OWNER);
    // V열 utm 원문 — intake_submit 경로와 동일 포맷('source|medium|content'). 2026-07-20 시모:
    //   이 미러 경로만 V열을 안 채워 같은 문의가 경로에 따라 계정 구분이 되기도 안 되기도 했다.
    put(['유입경로(자동)', '유입경로자동', '유입경로_자동'],
        body.utmSource ? (String(body.utmSource)
          + (body.utmMedium ? '|' + body.utmMedium : '')
          + (body.utmContent ? '|' + body.utmContent : '')) : '');
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
// ★ 단일 정규화 SSOT — _now() 문자열·_parseAnyDate_ 결과 모두 이 함수로 통일해
//   날짜 파싱 불일치(2026-06-18 INC) 방지. period_breakdown._toDate_ 와 동일 로직.
//   _now() 시각은 'yyyy-MM-dd HH:mm:ss'(공백 구분·오프셋 없음)으로 저장됨 → 반드시 'T'+'+09:00'로 ISO화.
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
      var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
      if (idxDate < 0) idxDate = 0;  // 못 찾으면 1열(구글폼 기본). 26년신규문의=B칸(타임스탬프) 자동 포착
      var idxMemoCfi = _findCol_(headers, ['비고', '메모']);  // [웹접수] 표식 탐지용
      var rows = sh.getRange(2, 1, last - 1, lastCol).getValues();
      rows.forEach(function(r) {
        if (!r[idxDate] && (idxPhone < 0 || !r[idxPhone])) return; // 빈 행 스킵
        // [웹접수] 표식을 두 경로가 공유한다 — 표식만 보고 싸잡아 빼면 안 된다(2026-07-20 시모 실측).
        //   ① CTA 미러(_mirrorInquiryToStaffLog_): 문의접수 시트에도 같이 적힌다 → 여기서 빼야 이중집계 방지.
        //      이 경로만 메모에 '(utm:' 서명을 남긴다.
        //   ② intake_submit(자체 문의폼, 2026-07-16 라이브~): 문의접수 시트에 적지 않는다 → 여기서 빼면
        //      어디에서도 집계되지 않는다. 실제로 07-16 이후 자체폼 문의가 통째로 M1에서 사라져 있었고
        //      (07-20 실측: 그날 멤버십탭 3건 전원 누락), 그래서 UTM을 제대로 달아도 인스타 기여가
        //      대시보드에 뜨지 않았다. 미러 서명이 있을 때만 제외한다.
        var _memoCfi = idxMemoCfi >= 0 ? String(r[idxMemoCfi] || '') : '';
        if (_memoCfi.indexOf(WEB_INTAKE_TAG) >= 0 && _memoCfi.indexOf('(utm:') >= 0) return;
        // 채널 = 대분류→중분류→자동UTM 3단 우선순위(공용 SSOT _resolveInquiryChannelRaw_, 회원관리 화면과 동일 규칙).
        var chanRaw = _resolveInquiryChannelRaw_(headers, r, cfg.channelKeys);
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

// ─── 전체 문의 로우(문의접수 시트 ∪ 구글폼) 단일 수집 — funnel_conversion(집계)·funnel_conversion_detail(명단)
//   공용 SSOT. 2026-07-20 GM 실사용 제보(M1에서 채널 건수 클릭→명단 건수 어긋남) 재발방지: 과거엔 두 액션이
//   이 두 소스를 각자 독립 순회·채널판정해 실서비스에서 건수가 갈렸다(로직 두 곳 복사 금지 원칙 재적용).
//   반환 행: {source:'inq'|'form', name, phone(정규화), channel(canonical), ts(원본 타임스탬프 값), type}.
//   기간 필터(inPeriodFn)는 원본 ts 값을 그대로 받는다(호출부의 _fcInPeriod/_fdInPeriod_와 동일 계약).
function _collectAllInquiryRows_(inPeriodFn) {
  var out = [];
  var inqSh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
  var inqLast = inqSh.getLastRow();
  if (inqLast >= 2) {
    var inqData = inqSh.getRange(2, 1, inqLast - 1, INQUIRY_HEADERS.length).getValues();
    var idxName    = INQUIRY_HEADERS.indexOf('이름');
    var idxPhone   = INQUIRY_HEADERS.indexOf('연락처');
    var idxChannel = INQUIRY_HEADERS.indexOf('유입채널');
    var idxDateFc  = INQUIRY_HEADERS.indexOf('시각');
    var idxType    = INQUIRY_HEADERS.indexOf('문의유형');
    inqData.forEach(function(row) {
      if (!inPeriodFn(row[idxDateFc])) return;   // 기간 필터(미지정=전체 누적)
      out.push({
        source:  'inq',
        name:    idxName >= 0 ? String(row[idxName] || '').trim() : '',
        phone:   normalizePhone_(row[idxPhone]),
        channel: _canonicalChannel_(row[idxChannel]),
        ts:      row[idxDateFc],
        type:    idxType >= 0 ? String(row[idxType] || '') : ''
      });
    });
  }
  _collectFormInquiries_().forEach(function(f) {
    if (!inPeriodFn(f.시각)) return;   // 기간 필터(미지정=전체 누적)
    out.push({
      source:  'form',
      name:    '',   // 구글폼 소스는 이름 미수집(원본 폼 구조 한계) — 호출부가 표시 시 구분 문구 사용
      phone:   normalizePhone_(f.연락처),
      channel: _canonicalChannel_(f.유입채널),
      ts:      f.시각,
      type:    f.문의유형 || ''
    });
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
// ─── [배179 · 2026-07-27] 종목별 '문의'를 문의 응답 탭에서 집계한다 ──────────────────
//  왜 바꿨나: 기존 _collectLessonInqByName_ 은 **팀시트**의 타임스탬프로 문의를 셌다. 그런데
//  팀시트 11곳은 폼 응답 칸(타임스탬프·성함·휴대폰…)이 비어 있어(배155·배173) 타임스탬프가
//  없다 → 수영을 뺀 전 종목이 '문의 0' 으로 나왔다. 화면 실측: 성인 골프·스쿼시·P.T·필라테스·
//  아쿠아로빅 전부 0 인데 등록은 118·49·108·72·25. 문의보다 등록이 많은 불가능한 표였다.
//  문의의 진짜 원천은 강습 '응답' 탭이다 — 거기서 종목을 표준 함수 _sportBuckets_ 로 센다.
//
//  ★이름 두 체계 주의(reference: _sportBuckets_ 주석). 버킷명 ≠ LESSON_DISPLAY 명 이라
//  정확일치로 이으면 조용히 0 이 된다. 아래 별칭표로만 잇고, 못 이으면 null(미측정)로 둔다.
//   · '체조'  → '체조&트램폴린'
//   · '모자수영' 은 버킷이 없다(_sportBuckets_ 가 /수영/ 으로 잡아 '수영'에 합침) → null 로 둔다.
//     0 으로 적으면 '문의가 없다'는 거짓말이 된다. 폼이 모자수영을 따로 받기 전엔 분리 불가.
function _lessonInqBySportFromForms_(from, to) {
  var out = {};   // { '성인강습': {'수영': 12, ...}, '유소년강습': {...} }
  var cFrom = from ? new Date(from + 'T00:00:00+09:00') : null;
  var cTo   = to   ? new Date(to   + 'T23:59:59+09:00') : null;
  ['성인강습', '유소년강습'].forEach(function(type) {
    var tally = {};
    try {
      var gid = (type === '유소년강습') ? LESSON_GID_YOUTH : LESSON_GID;
      (_lessonReadRows_(gid) || []).forEach(function(r) {
        if (cFrom || cTo) {
          var ts = r.timestamp ? new Date(r.timestamp) : null;
          if (!ts || isNaN(ts.getTime())) return;          // 시각 없으면 기간 판정 불가 → 제외
          if (cFrom && ts < cFrom) return;
          if (cTo   && ts > cTo)   return;
        }
        _sportBuckets_(r.sport).forEach(function(b) {
          if (b === '기타') return;
          tally[b] = (tally[b] || 0) + 1;
        });
      });
    } catch (e) { return; }
    out[type] = tally;
  });
  return out;
}
// 버킷명 → LESSON_DISPLAY 명. 못 이으면 null(미측정) — 다른 값으로 폴백하지 않는다.
function _lessonInqLookup_(tally, 명) {
  if (!tally) return null;
  if (명 === '모자수영') return null;                 // 버킷이 '수영'에 합쳐져 분리 불가
  var key = (명 === '체조&트램폴린') ? '체조' : 명;
  return (tally[key] === undefined) ? null : tally[key];
}

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
// GM 종목 ↔ LESSON_TEAM_SHEETS '명' 매핑. 팀시트 없는 외부 프로그램(루프메소드)은 sheet:null + external:true
//   → registered=null, 프론트는 '외부 파트너 유료 프로그램·명단 외부관리(등록 명단 미표시)'로 정직 표기.
var LESSON_DISPLAY = {
  '성인강습': [
    { 명: '수영',   sheet: '수영 성인' },
    { 명: '골프',   sheet: '골프 성인' },
    { 명: '스쿼시', sheet: '스쿼시 성인' },
    { 명: 'P.T',    sheet: 'P.T 성인' },
    { 명: '필라테스', sheet: '필라테스 성인' },
    { 명: '아쿠아로빅', sheet: '아쿠아로빅' },   // 누락 배선(팀시트 존재하나 display 누락) 2026-07-03
    // 발레·바레 분리(시토·GM 2026-07-15): 순수 종목명·external 해제 → 다른 종목처럼 등록집계 대상.
    //   팀시트 없음(sheet:null) → 등록수는 등록원장(강습 등록현황) SUC 카운트 기반(_ledgerRosterByType_). roster 없으면 0에서 누적.
    { 명: '발레', sheet: null, ledger: true },
    { 명: '바레', sheet: null, ledger: true }
  ],
  '유소년강습': [
    { 명: '수영',          sheet: '수영 유소년' },
    { 명: '골프',          sheet: '골프 유소년' },
    { 명: '스쿼시',        sheet: '스쿼시 유소년' },
    { 명: '체조&트램폴린', sheet: '유소년체조' },
    { 명: 'P.T',          sheet: 'P.T 유소년' },       // 누락 배선(팀시트 gid 1328034138) 2026-07-03
    { 명: '필라테스',      sheet: '필라테스 유소년' },  // 누락 배선(팀시트 gid 754969527) 2026-07-03
    { 명: '모자수영',      sheet: '모자수영' },         // 누락 배선(팀시트 gid 1219410707) 2026-07-03
    // 뮤지컬(Brad Little Star Academy) 배선 — GM 지시 2026-07-27(배140). 유소년만 운영.
    //   실측 근거: 유소년 강습문의 146건이 뮤지컬을 언급, 그중 등록(SUC) 14건(전화 중복 제거 11명).
    //   문의는 활발히 들어오는데 LESSON_DISPLAY 에 항목 자체가 없어 등록 집계에서 통째로 빠져 있었다.
    //   팀시트가 없으므로 발레·바레와 동일 패턴(sheet:null + ledger:true) — 새 방식 만들지 않음.
    { 명: '뮤지컬', sheet: null, ledger: true }
  ]
};

// ─── 강습 등록 원장 (금일 등록현황) — 2026-06-27 시포 ───
// 팀시트엔 등록일이 없어 '금일 등록'을 알 수 없으므로, 멤버십(26년 등록현황)과 동형의 원장을 둔다.
// sync-on-load: lesson_registry_list 호출 시 _syncLessonRegistry_()가 팀시트 SUC roster→원장 upsert.
//   신규 전화키 = 등록일 today(KST) 도장 / 기존 키 = 등록일 보존(상태·이름·종목만 갱신).
//   시드: 원장 빈 상태 최초 동기화 = 그 배치 전체를 등록일='2000-01-01'(기준선)로 적재 → 금일 제외.
var _LESSON_REG_SHEET  = '강습 등록현황';
var _LESSON_REG_HEADER = ['유형', '종목', '이름', '전화', '상태', '등록일', '키'];
// 대량 신규 가드 임계 — 하루 정상 신규 등록은 ≤ 십수 건. 초과분은 이관/일괄로 간주(아래 _syncLessonRegistry_).
var _LESSON_BULK_NEW_GUARD = 30;
function _lessonRegSheet_() {
  var ss = SpreadsheetApp.openById(LESSON_SS_ID);   // 이관(2026-07-18 GM): 강습 등록현황=강습SS로 정착(멤버십SS→강습SS). 데이터는 cpo_migrate_lesson_reg로 선복사됨.
  var sh = ss.getSheetByName(_LESSON_REG_SHEET);
  if (!sh) {
    sh = ss.insertSheet(_LESSON_REG_SHEET);
    sh.getRange(1, 1, 1, _LESSON_REG_HEADER.length).setValues([_LESSON_REG_HEADER]);
    sh.getRange(1, 1, 1, _LESSON_REG_HEADER.length).setFontWeight('bold');
  }
  return sh;
}

// 팀시트 없는 종목(LESSON_DISPLAY ledger:true — 발레·바레)의 등록 명단·집계 = 등록원장(강습 등록현황) SUC 행.
//   팀시트 roster가 없어 _collectLessonRoster_/_collectLessonRegByName_로는 집계 불가 → 원장 직접 카운트.
//   반환: { '발레': [{name,phone,status}], '바레': [...] } (유형 일치 + _isLessonReg_ 상태 행만). 원장 비면 {} → 프론트 0.
//   집계는 이 명단 length. 시토·GM 2026-07-15(external 해제 배선).
function _ledgerRosterByType_(type) {
  var out = {};
  try {
    var sh = _lessonRegSheet_();
    var last = sh.getLastRow();
    if (last < 2) return out;
    var rows = sh.getRange(2, 1, last - 1, _LESSON_REG_HEADER.length).getValues();
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i][0] || '').trim() !== type) continue;   // 유형 열(0)
      if (!_isLessonReg_(rows[i][4])) continue;                 // 상태 열(4) = 등록성공(SUC/등록)만
      var sp = String(rows[i][1] || '').trim();                 // 종목 열(1)
      if (!sp) continue;
      if (!out[sp]) out[sp] = [];
      out[sp].push({ name: String(rows[i][2] || ''), phone: _fmtPhone_(rows[i][3]), status: String(rows[i][4] || '').trim() });
    }
  } catch (e) { /* 원장 접근 실패 → {} (0 표기, 날조 금지) */ }
  return out;
}

// 팀시트(LESSON_TEAM_SHEETS)에서 현재 등록(SUC) 회원 명단 수집 — lesson_registered_roster 동일 로직.
//   반환: [{sport, name, phone, status}]. 상태열 못 찾거나 시트 미연결이면 해당 종목 스킵(날조 금지).
function _collectLessonRoster_(type) {
  var display = LESSON_DISPLAY[type] || [];
  var cfgByName = {};
  LESSON_TEAM_SHEETS.forEach(function(c){ cfgByName[c.명] = c; });
  var roster = [];
  display.forEach(function(item){
    var cfg = item.sheet ? cfgByName[item.sheet] : null;
    if (!cfg) return;
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) return;
      var last = sh.getLastRow(), lastCol = sh.getLastColumn();
      if (last < 2 || lastCol < 1) return;
      var data = sh.getRange(1, 1, last, lastCol).getValues();
      var headers = data[0];
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
      if (best < 0) return;
      var iName  = _findCol_(headers, ['성함', '이름', '성명']);
      var iPhone = _findCol_(headers, ['연락처', '전화', '휴대폰']);
      for (var r2 = 1; r2 < data.length; r2++) {
        var sv = data[r2][best];
        if (!_isLessonReg_(sv)) continue;
        roster.push({
          sport:  item.명,
          name:   iName  >= 0 ? String(data[r2][iName] || '') : '',
          phone:  iPhone >= 0 ? _fmtPhone_(data[r2][iPhone]) : '',
          status: String(sv == null ? '' : sv).trim()
        });
      }
    } catch (e) {}
  });

  // ── 팀시트 없는 종목(ledger:true — 발레·바레·뮤지컬) ────────────────────────────
  // [배140 · GM 지시 2026-07-27] 위 루프는 item.sheet 가 있어야 돈다(cfg 없으면 return).
  // 그래서 팀시트가 없는 종목은 roster 가 비고 → 원장에 행이 안 생기고 → 화면은 늘 0 이었다.
  // 읽는 쪽(_ledgerRosterByType_)만 배선되고 쓰는 쪽이 없던 반쪽 상태(2026-07-15 이후).
  //   실측 근거(2026-07-27): 뮤지컬 = 유소년 문의 중 등록(SUC) 11명인데 집계 0.
  //   발레·바레 = 문의 9건·등록 0건이라 우연히 0 이 맞아떨어져 결함이 안 드러났다.
  // GM 이 정본을 지정: 등록 정본 = 강습 '응답' 탭(성인 gid 111889422 / 유소년 268994754).
  // 이미 시스템이 문의 집계에 쓰는 시트라 새 시트·새 연결·새 권한 0.
  // 종목 판정은 표준 함수 _sportBuckets_ 를 그대로 호출한다 — 매칭 규칙을 여기 베끼면
  // 두 벌이 되어 한쪽만 늙는다(약속 L01). 합쳐진 legacy 옵션('웰니스 프로그램(바레, 발레)')이
  // 발레·바레 양쪽에 중복 계상되지 않는 처리도 그 함수가 이미 갖고 있다.
  var ledgerItems = display.filter(function(it){ return !it.sheet && it.ledger; });
  if (ledgerItems.length) {
    try {
      var wanted = {};
      ledgerItems.forEach(function(it){ wanted[it.명] = 1; });
      var inqGid = (type === '유소년강습') ? LESSON_GID_YOUTH : LESSON_GID;
      // 시트를 직접 열어 칸을 찾지 않는다 — 응답탭 헤더는 탭마다 다르고(성인 '성인 강습 종목' vs
      // 유소년 'WSC 강습 종류' 등) 관리칸이 우측에 멱등 생성되는 구조라, 칸 찾기 규칙을 여기 다시
      // 적으면 반드시 한쪽만 늙는다. 실제로 첫 구현에서 유소년 종목 칸을 못 찾아 뮤지컬 0건이었다.
      // 표준 리더 _lessonReadRows_ 가 헤더 별칭·정규화(sport/status/name/phone)를 이미 갖고 있으므로
      // 그대로 재사용한다(약속 L01 — 판정·해석 로직은 단일 지점).
      var inqRows = _lessonReadRows_(inqGid) || [];
      var seenKey = {};   // 같은 사람이 같은 종목에 중복 접수한 경우 1회만
      for (var r3 = 0; r3 < inqRows.length; r3++) {
        var irow = inqRows[r3];
        if (!_isLessonReg_(irow.status)) continue;          // 등록 성공 행만
        var buckets = _sportBuckets_(irow.sport);
        for (var b = 0; b < buckets.length; b++) {
          if (!wanted[buckets[b]]) continue;                // 이 유형의 ledger 종목만
          var dk = buckets[b] + '|' + _normPhone_(irow.phone);
          if (seenKey[dk]) continue;
          seenKey[dk] = 1;
          roster.push({
            sport:  buckets[b],
            name:   String(irow.name || ''),
            phone:  String(irow.phone || ''),
            status: String(irow.status || '').trim(),
            ledgerSrc: true    // 원장 키를 종목까지 스코프하라는 표식 — 아래 _syncLessonRegistry_ 참조
          });
        }
      }
    } catch (eLed) {}
  }

  return roster;
}

// 팀시트 roster → 원장 upsert. CacheService 5분 가드 + LockService 짧은 락(중복쓰기 방지).
function _syncLessonRegistry_() {
  var cache = CacheService.getScriptCache();
  if (cache.get('lesson_reg_synced')) return;          // 5분 내 이미 동기화됨
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return;                     // 다른 호출이 동기화 중 → 스킵(무중단)
  try {
    if (cache.get('lesson_reg_synced')) return;        // 락 획득 후 더블체크
    var today = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
    var sh = _lessonRegSheet_();
    var last = sh.getLastRow();
    var seed = (last < 2);                              // 원장 빈 상태 → 기준선 시드 모드
    var rows = (last >= 2) ? sh.getRange(2, 1, last - 1, _LESSON_REG_HEADER.length).getValues() : [];
    // [배140 · 2026-07-27] 종목 단위 기준선 판정. 원장에 그 종목 행이 0이면 이번에 들어오는
    // 배치는 '오늘 등록'이 아니라 '이제야 연결된 과거 등록자'다 — 종목이 새로 배선될 때마다
    // 그 인원이 당일 신규로 잡혀 KPI 를 부풀린다(뮤지컬 첫 편입 11명이 정확히 이 경우).
    // 대량 신규 가드(_LESSON_BULK_NEW_GUARD=30)는 임계 미만이라 못 막는다 → 종목 단위로 막는다.
    // 원장 전체 시드와 같은 취지·같은 값(2000-01-01)이라 새 규칙이 아니라 적용 범위 확장이다.
    var sportSeen = {};
    for (var s0 = 0; s0 < rows.length; s0++) {
      var sp0 = String(rows[s0][1] || '').trim();
      if (sp0) sportSeen[sp0] = 1;
    }
    var keyIdx = {};
    for (var i = 0; i < rows.length; i++) {
      var k = String(rows[i][6] || '').trim();
      if (k) keyIdx[k] = i;
    }
    var dirty = false;
    var newIdx = [];   // 이번 sync에서 새로 추가된 행 인덱스 — 대량 신규(이관) 감지용
    ['성인강습', '유소년강습'].forEach(function(type){
      _collectLessonRoster_(type).forEach(function(m){
        var np = _normPhone_(m.phone);
        if (!np) return;                               // 전화 없으면 키 불가 → 스킵
        // [배140 · 2026-07-27 회귀 수리] 원장 키는 원래 전화+유형뿐이라 한 사람이 원장에서 1행만
        // 차지한다. 그래서 응답탭發 뮤지컬 행이 이미 수영·체조로 등록돼 있던 같은 사람의 키와
        // 충돌해 그 행의 종목을 통째로 덮어썼다 — 배포 직후 실측에서 수영 1502→1494, 체조
        // 371→369, 뮤지컬 +11(10건은 이동·1건만 진짜 신규)로 드러났다. 아이가 수영도 하고
        // 뮤지컬도 하는 건 정상인데 원장이 그걸 표현하지 못한 것.
        // → 응답탭發(ledgerSrc) 행만 키를 종목까지 스코프해 별도 행으로 앉힌다. 팀시트發 키는
        //   그대로라 기존 2,504행은 손대지 않는다(다음 sync 에서 팀시트가 종목을 원복시킨다).
        // ※ 팀시트끼리의 같은 충돌(수영+골프 동시 등록)은 이 배 이전부터 있던 별개 사안 — 여기서
        //   건드리지 않는다(키 체계 전면 변경은 기존 전 행 재생성 위험).
        var key = np + '|' + type + (m.ledgerSrc ? '|' + String(m.sport || '') : '');
        if (keyIdx.hasOwnProperty(key)) {
          var rr = rows[keyIdx[key]];                  // 기존 키 — 등록일 보존, 상태·이름·종목만 갱신
          if (rr[1] !== m.sport || rr[2] !== m.name || rr[4] !== m.status) {
            rr[1] = m.sport; rr[2] = m.name; rr[4] = m.status; dirty = true;
          }
        } else {
          // 원장 전체가 비었거나(seed), 이 종목이 원장에 처음 들어오는 경우 → 기준선.
          var firstOfSport = !sportSeen[String(m.sport || '').trim()];
          rows.push([type, m.sport, m.name, m.phone, m.status,
                     (seed || firstOfSport) ? '2000-01-01' : today, key]);
          newIdx.push(rows.length - 1);
          keyIdx[key] = rows.length - 1;
          dirty = true;
        }
      });
    });
    /* ─── [배523 · 2026-08-10 시포] 팀시트가 못 잡는 등록자 보충 ───────────────────
       ▸증상: 등록 원장이 2026-07-20 이후 21일째 새 등록을 못 받았다(실측 — 원장 2,515행 중
         마지막 실제 등록일 07-20, 그 뒤 0건). 회원 명단·실무진 화면은 멀쩡했고 KPI 집계만 멈췄다.
       ▸원인: 위 루프는 팀시트(LESSON_TEAM_SHEETS)에서만 등록자를 모은다. 그 팀시트를 채우던
         IMPORTRANGE 가 죽었고(배173 — GM 이 '복구 안 함, ERP 로 간다'로 확정), 그 뒤 아무도
         원장 쪽을 다른 원천으로 옮기지 않았다. 새로 등록한 사람이 팀시트에 안 나타나니 원장에도 없다.
       ▸보충: 강습 응답탭(문의 정본)에서 등록(SUC)인데 원장에 전화키가 아예 없는 사람만 담는다.
         실측 28명(성인 13·유소년 15 · 2026-08-10). 이미 있는 사람은 건드리지 않는다.
       ▸★등록일은 지어내지 않는다 — 기준선(2000-01-01)으로 넣는다. 응답탭에는 등록일 칸이
         자체가 없어서(배198·배365 가 그 칸 신설 건이다) 실제 등록일을 알 수 없다. 오늘로 찍으면
         오늘 28명이 등록한 것처럼 보인다. 명단 정합만 여기서 맞추고, '최근 N일 등록' 측정은
         등록일 칸이 생겨야 가능하다 — 위 응답탭發 불변식(①)과 같은 규칙이다. */
    try {
      ['성인강습', '유소년강습'].forEach(function(bType){
        var bGid = (bType === '유소년강습') ? LESSON_GID_YOUTH : LESSON_GID;
        var bHave = {};
        for (var bi = 0; bi < rows.length; bi++) {
          var bp = _normPhone_(rows[bi][3]);
          if (bp && String(rows[bi][0] || '') === bType) bHave[bp] = 1;
        }
        (_lessonReadRows_(bGid) || []).forEach(function(irow){
          if (!_isLessonReg_(irow.status)) return;
          var bnp = _normPhone_(irow.phone);
          if (!bnp || bHave[bnp]) return;                 // 원장에 이미 있는 사람은 제외
          var bBuckets = _sportBuckets_(irow.sport) || [];
          var bSport = bBuckets.length ? bBuckets[0] : String(irow.sport || '').trim();
          if (!bSport) return;                            // 종목 판정 실패분은 지어내지 않고 건너뛴다
          var bKey = bnp + '|' + bType + '|' + bSport;
          if (keyIdx.hasOwnProperty(bKey)) return;
          rows.push([bType, bSport, String(irow.name || ''), _fmtPhone_(irow.phone),
                     String(irow.status || '').trim(), '2000-01-01', bKey]);
          keyIdx[bKey] = rows.length - 1;
          bHave[bnp] = 1;
          dirty = true;
          // newIdx 에 넣지 않는다 — 이 보충분은 '금일 신규'가 아니라 뒤늦은 편입이라
          // 아래 대량 신규 가드의 판정 대상이 아니다(이미 기준선으로 적재했다).
        });
      });
    } catch (eBackfill) { Logger.log('강습원장 응답탭 보충 실패: ' + eBackfill.message); }

    // ─── 대량 신규 가드(2026-07-15 시포 · KPI 오염 재발방지, 배973 사고 근본수리) ───
    //   sync-on-load 는 '금일 증분 등록'을 잡는 용도(정상 신규 ≤ 십수 건). 팀시트 이관·일괄 연결로
    //   한 번에 다수 신규 키가 유입되면 그것은 '금일 등록'이 아니라 과거 등록자의 뒤늦은 편입 →
    //   today 도장 시 '이번달 강습 등록' KPI 대량 오염. 임계 초과 시 이관 간주 → 등록일=기준선
    //   (2000-01-01, 금월 집계 제외)으로 적재 + 경보. (seed 최초 동기화는 이미 기준선이라 무관.)
    if (!seed && newIdx.length > _LESSON_BULK_NEW_GUARD) {
      newIdx.forEach(function(ix){ rows[ix][5] = '2000-01-01'; });
      try {
        _notifyTelegram('⚠️ <b>강습원장 대량 신규 감지</b> — ' + newIdx.length + '건(임계 ' + _LESSON_BULK_NEW_GUARD + ' 초과) → 이관 간주, 등록일=기준선(2000-01-01) 적재(이번달 KPI 오염 방지). 실제 당일 신규라면 개별 확인 요망.');
      } catch (eBulk) {}
    }
    // ─── [배140 · 2026-07-27 시모] 응답탭發 행 불변식 + 배포사고 잔재 정리(자기 소멸형) ───
    //   ① 불변식: 응답탭에는 '등록일' 칸이 없다 → 응답탭發(키가 '전화|유형|종목') 행의 등록일은
    //      언제나 기준선이어야 한다. 알 수 없는 날짜를 오늘로 찍으면 그날 신규가 부풀어 오른다.
    //      실제로 2026-07-27 배포에서 11행이 오늘 날짜로 찍혔다. 매 sync 마다 되돌린다(자가치유).
    //   ② 잔재 정리: 배선 첫 배포(@152)가 응답탭發 행을 '전화|유형' 키로 넣어 같은 사람의 팀시트
    //      종목 행을 덮어썼다(수영 8·체조 2). @153 에서 키를 종목까지 스코프해 충돌은 막았지만,
    //      @152 가 만든 옛 행이 고아로 남아 같은 사람이 2행이 됐다.
    //      서명 = '키에 종목 스코프가 없는데 종목은 팀시트 없는 종목' — 이 조합은 그 사고로만
    //      생긴다. 팀시트에 현재 등록돼 있으면 위 루프가 이미 종목을 원복시켰으므로 여기 안 걸린다.
    //      처리: 그 사람의 문의 응답 종목에서 팀시트가 있는 종목을 되찾아 복원(= 사고 전 라벨),
    //           되찾을 게 없으면(뮤지컬 전용) 스코프 행이 이미 있으므로 고아 행 제거.
    //      정리 후엔 서명에 걸리는 행이 0이 되어 이 블록은 무해한 무동작 가드로 남는다.
    try {
      var _ledgerOnly = {}, _teamSport = {};
      ['성인강습', '유소년강습'].forEach(function(t){
        _ledgerOnly[t] = {}; _teamSport[t] = {};
        (LESSON_DISPLAY[t] || []).forEach(function(it){
          if (it.sheet) _teamSport[t][it.명] = 1;
          else if (it.ledger) _ledgerOnly[t][it.명] = 1;
        });
      });
      // ① 불변식 — 응답탭發 행 등록일 강제 기준선
      for (var u = 0; u < rows.length; u++) {
        var uk = String(rows[u][6] || '');
        var ut = String(rows[u][0] || '').trim();
        var us = String(rows[u][1] || '').trim();
        if ((_ledgerOnly[ut] || {})[us] && uk.indexOf('|' + us) >= 0) {
          if (String(rows[u][5] || '') !== '2000-01-01') { rows[u][5] = '2000-01-01'; dirty = true; }
        }
      }
      // ② 잔재 정리 — 서명 행 수집
      var _fixIdx = [];
      for (var q = 0; q < rows.length; q++) {
        var qt = String(rows[q][0] || '').trim();
        var qs = String(rows[q][1] || '').trim();
        var qk = String(rows[q][6] || '');
        if (!(_ledgerOnly[qt] || {})[qs]) continue;      // 팀시트 없는 종목 행만
        if (qk.indexOf('|' + qs) >= 0) continue;         // 스코프 키 = 정상 행
        _fixIdx.push(q);
      }
      // ★2026-07-27 즉시 중단(시모) — 아래 자동 복원은 라이브에서 오작동했다.
      //   _sportBuckets_ 는 '체조'를 돌려주는데 LESSON_DISPLAY 유소년 종목명은 '체조&트램폴린'이라
      //   이름이 안 맞아 매칭에 실패했고, 그 결과 체조로 되돌려야 할 2건이 엉뚱하게 수영·골프로
      //   복원됐다(실측: 수영 1502→1504 · 골프 168→169 · 체조 369 그대로).
      //   더 나쁜 건, 잘못 복원된 행은 '스코프 없는 키 + 팀시트 종목'이라 서명에 더는 안 걸려
      //   정상 행과 구분되지 않는다 — 자동 로직이 스스로 만든 오염을 스스로 못 찾는다.
      //   → 자동 복원은 끈다. 남은 3건 교정은 원장 백업을 먼저 뜬 뒤 대조키로 1회 처리한다(배140).
      //   ①등록일 기준선 불변식(위)은 정상 동작 확인돼 그대로 둔다(뮤지컬 11건 전부 기준선 복귀).
      var _AUTO_RESTORE_ENABLED = false;
      if (_AUTO_RESTORE_ENABLED && _fixIdx.length && _fixIdx.length <= 20) {
        var _inqSport = {};                              // 유형 → (전화 → 응답 종목라벨)
        ['성인강습', '유소년강습'].forEach(function(t){
          _inqSport[t] = {};
          var gidT = (t === '유소년강습') ? LESSON_GID_YOUTH : LESSON_GID;
          (_lessonReadRows_(gidT) || []).forEach(function(ir){
            var p = _normPhone_(ir.phone);
            if (p) _inqSport[t][p] = String(ir.sport || '');
          });
        });
        var _drop = {};
        _fixIdx.forEach(function(q){
          var qt = String(rows[q][0] || '').trim();
          var lbl = (_inqSport[qt] || {})[_normPhone_(rows[q][3])] || '';
          var bk = _sportBuckets_(lbl), restore = '';
          // 뒤에서부터 = 문의 라벨에서 팀시트 종목 중 마지막 것. 사고 전 라벨 복원용 —
          // 실측 대조(체조&트램폴린 371→369)로 이 선택이 사고 전 값과 일치함을 확인했다.
          for (var z = bk.length - 1; z >= 0; z--) {
            if ((_teamSport[qt] || {})[bk[z]]) { restore = bk[z]; break; }
          }
          if (restore) { rows[q][1] = restore; dirty = true; }
          else { _drop[q] = 1; }
        });
        var _dropN = 0;
        for (var dk2 in _drop) { if (_drop.hasOwnProperty(dk2)) _dropN++; }
        if (_dropN) {
          var _kept = [];
          for (var w = 0; w < rows.length; w++) { if (!_drop[w]) _kept.push(rows[w]); }
          rows = _kept; dirty = true;
          try {
            _notifyTelegram('🧹 <b>강습원장 잔재 정리</b> — 2026-07-27 배선 배포 사고로 생긴 중복 고아 행 '
              + _dropN + '건 제거(같은 사람·같은 종목의 정상 행은 그대로). 복원 ' + (_fixIdx.length - _dropN) + '건.');
          } catch (eN) {}
        }
      } else if (_fixIdx.length > 20) {
        try { _notifyTelegram('⚠️ <b>강습원장 잔재 서명 다수 감지</b> — ' + _fixIdx.length + '건(상한 20 초과). 자동 정리하지 않음, 수동 확인 요망.'); } catch (eN2) {}
      }
    } catch (eFix) {}

    // ─── [배140 · 2026-07-27] 1회성 교정 — 배포 사고 잔재 3행 (백업 후 실행·자기 종료형) ───
    //   앞선 자동복원(@154)이 종목명 불일치('체조' vs '체조&트램폴린')로 오작동해, 체조로
    //   돌려야 할 2행이 수영·골프로 잘못 붙었고 뮤지컬 전용 1행은 중복으로 남았다.
    //   식별: 유소년 · 스코프 없는 키 · 같은 전화의 스코프 '뮤지컬' 행이 존재 · 현재 종목의
    //         팀시트 명단에는 없음 → 사고로 라벨이 바뀐 행(정상 등록자는 팀시트에 있어 제외).
    //   판정: 그 사람 문의 종목에 체조/트램폴린이 있으면 '체조&트램폴린' 복원, 없으면 잉여 행 제거
    //         (같은 사람·같은 종목의 정상 스코프 행이 이미 있어 정보 손실 0).
    //   안전: ①시트 백업 먼저 ②상한 5행 ③처리 내역 텔레그램 통보 ④ScriptProperties 로 1회만.
    try {
      var _P = PropertiesService.getScriptProperties();
      if (_P.getProperty('LESSON_REG_FIX_20260727') !== 'done') {
        var _BK = '강습 등록현황_백업_20260727';
        var _ssB = SpreadsheetApp.openById(LESSON_SS_ID);
        if (!_ssB.getSheetByName(_BK)) _ssB.getSheetByName(_LESSON_REG_SHEET).copyTo(_ssB).setName(_BK);

        var _muPhone = {};                                  // 스코프 뮤지컬 행이 있는 전화
        for (var m1 = 0; m1 < rows.length; m1++) {
          if (String(rows[m1][6] || '').indexOf('|뮤지컬') >= 0) _muPhone[_normPhone_(rows[m1][3])] = 1;
        }
        var _teamHas = {};                                  // 팀시트 현재 명단(전화|종목)
        (_collectLessonRoster_('유소년강습') || []).forEach(function(mm){
          if (!mm.ledgerSrc) _teamHas[_normPhone_(mm.phone) + '|' + mm.sport] = 1;
        });
        var _inqLbl = {};                                   // 전화 → 문의 종목 라벨
        (_lessonReadRows_(LESSON_GID_YOUTH) || []).forEach(function(ir){
          var p = _normPhone_(ir.phone); if (p) _inqLbl[p] = String(ir.sport || '');
        });

        var _hit = [], _rm = {};
        for (var v = 0; v < rows.length; v++) {
          if (String(rows[v][0] || '').trim() !== '유소년강습') continue;
          var vk = String(rows[v][6] || '');
          if (vk.split('|').length !== 2) continue;         // 스코프 키(3토막)는 정상 행
          var vp = _normPhone_(rows[v][3]), vs = String(rows[v][1] || '').trim();
          if (!_muPhone[vp]) continue;                      // 뮤지컬 등록자가 아니면 무관
          if (_teamHas[vp + '|' + vs]) continue;            // 팀시트에 실재 → 정상 행
          _hit.push(v);
        }
        if (_hit.length && _hit.length <= 5) {
          var _log = [];
          _hit.forEach(function(v){
            if (/체조|트램폴린/.test(_inqLbl[_normPhone_(rows[v][3])] || '')) {
              _log.push(String(rows[v][2] || '') + ': ' + rows[v][1] + ' → 체조&트램폴린');
              rows[v][1] = '체조&트램폴린'; dirty = true;
            } else {
              _log.push(String(rows[v][2] || '') + ': ' + rows[v][1] + ' 잉여행 제거(뮤지컬 정상행 유지)');
              _rm[v] = 1;
            }
          });
          var _rmN = 0; for (var rk in _rm) { if (_rm.hasOwnProperty(rk)) _rmN++; }
          if (_rmN) {
            var _keep = [];
            for (var w2 = 0; w2 < rows.length; w2++) { if (!_rm[w2]) _keep.push(rows[w2]); }
            rows = _keep; dirty = true;
          }
          _P.setProperty('LESSON_REG_FIX_20260727', 'done');
          try {
            _notifyTelegram('🧹 <b>강습원장 교정 완료</b>(배140 · 1회)\n백업: ' + _BK
              + '\n' + _log.join('\n'));
          } catch (eN3) {}
        } else if (_hit.length > 5) {
          try { _notifyTelegram('⚠️ <b>강습원장 교정 보류</b> — 대상 ' + _hit.length + '행(상한 5 초과). 자동 처리하지 않음.'); } catch (eN4) {}
        } else {
          _P.setProperty('LESSON_REG_FIX_20260727', 'done');   // 대상 0 = 이미 정상
        }
      }
    } catch (eFix2) {}

    if (dirty && rows.length) {
      sh.getRange(2, 1, rows.length, _LESSON_REG_HEADER.length).setValues(rows);
      // 행이 줄었으면(잔재 제거) 남은 꼬리 행을 지운다 — 안 지우면 옛 행이 그대로 남아
      // '지웠는데 그대로'가 된다. 전 데이터를 위에 다시 쓴 뒤의 꼬리만 지우므로 인덱스 안전.
      var _tail = last - 1 - rows.length;               // last-1 = 기존 데이터 행수
      if (_tail > 0 && _tail <= 20) sh.deleteRows(2 + rows.length, _tail);
    }
    cache.put('lesson_reg_synced', '1', 300);          // 5분 가드
  } catch (e) {
  } finally {
    lock.releaseLock();
  }
}

// ─── 회원 변경 이력 (배327) ───
// 이전값을 남기는 것이 이 기능의 전부다 — 새값만 남기면 "왜 이렇게 됐지"를 못 푼다.
// 저장은 유효회원과 **같은 파일 안 탭 하나**(새 스프레드시트·새 GAS 없음).
// 기록 실패가 저장을 깨면 안 된다 — 전부 삼킨다. 읽기 전용(삭제·되돌리기 없음).
var MEMBER_LOG_SHEET = '회원변경이력';
// 과거 이력은 복원할 수 없다 — 화면에 "언제부터 쌓기 시작했는지"를 정직하게 띄우기 위한 값.
var MEMBER_LOG_STARTED = '2026-08-03';
// 뒤 4자리만 가린다 — 동명이인이 있어 사람이 누구 건지는 알아볼 수 있어야 한다(웰리 2026-08-03).
function _logMaskPhone_(v) {
  var d = String(v == null ? '' : v).replace(/[^0-9]/g, '');
  if (d.length < 8) return String(v == null ? '' : v);
  return d.slice(0, d.length - 4).replace(/(\d{3})(\d+)/, '$1-$2') + '-****';
}
// '자동'과 '이름미상'은 다르다(웰리 2026-08-03) — 전자는 사람이 안 한 것, 후자는 사람이 했는데
// 이름을 못 받은 것. 판정은 호출 경로로만 한다: 프론트(apiPost)는 staff 키를 항상 실어 보내고,
// 자동접수·스크립트는 아예 안 보낸다. 키가 없으면 자동. 값을 지어내지 않는다.
function _logWho_(body) {
  if (!body || !Object.prototype.hasOwnProperty.call(body, 'staff')) return '자동';
  return String(body.staff || '').trim() || '이름미상';
}
function _memberLog_(rows) {
  try {
    if (!rows || !rows.length) return;
    var ss = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var sh = ss.getSheetByName(MEMBER_LOG_SHEET);
    if (!sh) {
      sh = ss.insertSheet(MEMBER_LOG_SHEET);
      sh.getRange(1, 1, 1, 8).setValues([['시각', '직원', '회원명', '연락처', '항목', '이전값', '새값', '화면']]);
      sh.setFrozenRows(1);
    }
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, 8).setValues(rows);
  } catch (e) {
    // 기록 실패가 회원 저장을 막지 않는다(그건 그대로). 다만 **아무 흔적도 안 남기지는 않는다**
    // — 배342·웰리 2026-08-04. 그동안 이 catch 가 통째로 삼켜서, 이력 append 가 실패해도
    // 응답은 ok:true 였다. 실패가 성공으로 보이니 아무 감시기도 안 울렸다.
    // Logger.log 는 이 파일의 기존 방식이고 Apps Script 실행기록에 남는다(새 장치 0 · 약속 L21).
    Logger.log('[_memberLog_] 이력 기록 실패(회원 저장은 정상): ' + (e && e.message ? e.message : String(e)));
  }
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

// ─── 문의접수 원시 읽기 단일 지점 — 테스트행 제외(2026-07-30 시토, 배209 GM승인) ───
//   inquiry_list·type_channel_breakdown·period_breakdown·stage_funnel·weekly_trend 5곳이
//   각자 _getSheet(INQUIRY_SHEET,...)+getRange().getValues() 를 불러 테스트 태그가 그대로
//   집계에 섞였다(배209 실측 — [UTF8검증]·[진단209검증] 4행이 문의 건수·전환율에 포함됨).
//   판정 로직을 여기 한 곳에만 두고 5곳이 재사용한다(약속 L01·L21 — 복사 금지).
//   제외 기준 = 이름 칸의 명시적 테스트 표시. 'INQ-' id접두는 안 쓴다 — 그건 '이 액션이
//   만든 행'이라는 뜻일 뿐 '테스트'가 아니라서, 나중에 이 액션으로 실제 문의가 들어오면
//   그 행까지 잘못 걸러진다(배209 GM 확정 판단).
var _INQ_TEST_NAME_MARKERS_ = ['[UTF8검증]', '[진단209검증', '자동QA', '[자동QA]'];
function _isTestInquiryName_(name) {
  var s = String(name || '');
  for (var i = 0; i < _INQ_TEST_NAME_MARKERS_.length; i++) {
    if (s.indexOf(_INQ_TEST_NAME_MARKERS_[i]) >= 0) return true;
  }
  return false;
}
// 배209 사고 재발방지(2026-08-04, GM 지적) — 테스트 태그 문의가 실무진 알림방(문의컨택알림방)으로
// 그대로 새던 것. submit_inquiry·intake_submit 알림 발신 직전에 이 함수로 채팅방을 정한다.
// 판정은 위 _isTestInquiryName_ 재사용(새 판정 로직 없음, 약속 L01·L21) — 테스트면 조용히 버리지
// 않고 업무보고방(8254867551)으로 돌린다.
var TELEGRAM_REPORT_CHAT_ID = '8254867551';
function _inquiryNotifyChatId_(name, normalChatId) {
  return _isTestInquiryName_(name) ? TELEGRAM_REPORT_CHAT_ID : normalChatId;
}
// 반환 행은 기존 5곳과 동일 폭·순서(INQUIRY_HEADERS.length 컬럼) — 그 계약은 안 건드리고
// 테스트행만 뺀다. 이름 칸 인덱스는 상수(INQUIRY_HEADERS)가 아니라 시트 실제 헤더 행을
// 매 호출 스캔해 찾는다(열 번호 하드코딩 금지 — reference_inquiry_sheet_write_read_column_mismatch
// 전례: 쓰는 칸과 읽는 칸이 어긋난 적이 있다). 이름 칸을 못 찾으면 거르지 않고 그대로 반환한다
// (과다제외=실고객 누락이 더 나쁘다 — 조용히 통과, throw 금지).
function _readInquirySheetRows_() {
  var sh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
  var last = sh.getLastRow();
  if (last < 2) return [];
  var liveHeaders = sh.getRange(1, 1, 1, INQUIRY_HEADERS.length).getValues()[0];
  var nameIdx = -1;
  for (var hi = 0; hi < liveHeaders.length; hi++) {
    if (String(liveHeaders[hi] || '').trim() === '이름') { nameIdx = hi; break; }
  }
  var rows = sh.getRange(2, 1, last - 1, INQUIRY_HEADERS.length).getValues();
  if (nameIdx < 0) return rows;
  return rows.filter(function(r) { return !_isTestInquiryName_(r[nameIdx]); });
}

// QA 전용 탭 읽기(배195) — QA_INQUIRY_SHEET 는 QA 행만 들어가므로 이름태그 필터가 필요 없다.
// inquiry_list 가 _isQaInquiryCall_(body) 일 때만 이 헬퍼를 쓴다 — 라이브 화면·집계 5곳은
// 이 함수를 절대 호출하지 않는다(QA_INQUIRY_SHEET 를 참조하는 곳은 이 함수 하나뿐).
function _readQaInquirySheetRows_() {
  var sh = _getSheet(QA_INQUIRY_SHEET, INQUIRY_HEADERS);
  var last = sh.getLastRow();
  if (last < 2) return [];
  return sh.getRange(2, 1, last - 1, INQUIRY_HEADERS.length).getValues();
}

function initSheets() {
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

// ─── 조회 캐시(청크) 유틸 — 축1 성능개선(강습·멤버십 문의 목록 조회 캐시). 2026-07-08 시토 ───
//   CacheService 값은 키당 최대 100KB. 강습 목록 응답(~190KB)처럼 큰 JSON은 단일 키 저장 불가 →
//   직렬화 문자열을 3만자(3바이트/자 최악치 기준 ≤90KB) 청크로 분할해 putAll로 원자 저장,
//   읽을 때 메타키(청크수)로 재조립. 어느 단계든 실패하면 null 반환 → 호출부는 시트 재조회 폴백
//   (캐시가 장애점이 되면 안 됨). ok:false 응답은 호출부에서 애초에 저장하지 않음(정책).
var _CACHE_CHUNK_CHARS_ = 30000;

function _cachePutJson_(cache, key, obj, ttlSec) {
  try {
    var str = JSON.stringify(obj);
    var n = Math.max(1, Math.ceil(str.length / _CACHE_CHUNK_CHARS_));
    var payload = {};
    payload[key + '__meta'] = String(n);
    for (var i = 0; i < n; i++) {
      payload[key + '__' + i] = str.substr(i * _CACHE_CHUNK_CHARS_, _CACHE_CHUNK_CHARS_);
    }
    cache.putAll(payload, ttlSec);
  } catch (e) { /* 저장 실패 무시 — 폴백=시트 재조회 */ }
}

function _cacheGetJson_(cache, key) {
  try {
    var meta = cache.get(key + '__meta');
    if (!meta) return null;
    var n = parseInt(meta, 10);
    if (!n || n < 1) return null;
    var keys = [];
    for (var i = 0; i < n; i++) keys.push(key + '__' + i);
    var chunks = cache.getAll(keys);
    var parts = [];
    for (var j = 0; j < n; j++) {
      var part = chunks[key + '__' + j];
      if (part === undefined || part === null) return null;  // 부분 만료(TTL 경계) → 미스 취급(폴백)
      parts.push(part);
    }
    return JSON.parse(parts.join(''));
  } catch (e) { return null; }
}

// ★2026-07-31 시토 — 유효회원 목록 캐시 무효화(한 곳). 유효회원 시트를 바꾸는 경로는 전부
//   이걸 부른다. 캐시 TTL 이 60초라 안 불러도 1분이면 사라지지만, 편집 직후 옛 값이 보이면
//   실무진은 "저장이 안 됐다"고 읽는다(오늘 GM 지적 부류). 그래서 즉시 지운다.
/* scopeList = 지울 명단 이름 배열. 안 주면 종전대로 전부 지운다(하위호환).
   ★2026-08-26 시포(실무진 신고 — "최신 명단 불러오는 중" 에서 수정이 안 됨) 근본수리.
   회원 한 칸을 고칠 때마다 유효·종료·법인·보관 **네 명단 캐시를 전부** 날렸다. 유효회원 시트만
   건드렸는데 나머지 셋까지 지우니, 그 직후 화면을 여는 사람은 콜드 조회를 맞는다 — 실측으로
   그 첫 조회가 83초 걸리다 실패했고, 화면은 그동안 '불러오는 중' 잠금 상태로 멈춰 있었다.
   이제 저장이 실제로 건드린 시트의 캐시만 지운다. */
function _aaCacheClear_(scopeList) {
  try {
    var c = CacheService.getScriptCache();
    // ★2026-08-26 시포 — 'archive' 추가. LOSS보관 시트는 조회전용이라 목록 캐시를 지울 일이 없었는데,
    //   이관 정리(member_archive_restore)가 그 시트에서 행을 지우기 시작했다. 안 지우면 실무진이
    //   정리 직후 새로고침해도 최대 60초 동안 지운 분이 그대로 보인다 — 최영천 건에서 실제로 겪었다.
    /* ★2026-08-26 시포(배11001 1단계) — 키마다 _cacheInvalidateJson_ 을 부르면 캐시를 16번 친다
       (키 8개 × get+removeAll). 저장 1건 실측에서 이 구간만 0.66초였다. meta 를 한 번에 받고
       지울 키도 한 번에 넘겨 호출을 2번으로 줄인다 — 지우는 대상은 글자 하나 안 바뀐다. */
    var scopes = (scopeList && scopeList.length) ? scopeList : ['valid', 'ended', 'corp', 'archive'];
    var fmts = ['obj', 'rows'];
    var bases = [], metaKeys = [];
    for (var si = 0; si < scopes.length; si++) {
      for (var fi = 0; fi < fmts.length; fi++) {
        var _b = 'aacache|' + scopes[si] + '|' + fmts[fi];
        bases.push(_b); metaKeys.push(_b + '__meta');
      }
    }
    var metas = c.getAll(metaKeys) || {};
    var kill = [];
    for (var bi = 0; bi < bases.length; bi++) {
      var b = bases[bi];
      var n = parseInt(metas[b + '__meta'], 10) || 0;
      var max = Math.max(n, 12);            // 메타 유실 대비 여유 청크까지 — 종전과 동일
      kill.push(b + '__meta');
      for (var i = 0; i < max; i++) kill.push(b + '__' + i);
    }
    for (var ki = 0; ki < kill.length; ki += 90) c.removeAll(kill.slice(ki, ki + 90));
  } catch (e) {}
}

// ★문의 조회 캐시 일괄 무효화 — 2026-08-05 시토. 문의 시트를 바꾸는 경로(추가·수정·삭제·자체폼 접수)는
//   전부 이걸 부른다. 종전엔 네 곳이 각자 'micache' 하나만 지웠는데, 예약 달력이 쓰는
//   'mccache|YYYY-MM'(2026-08-05 신설) 은 아무도 안 지웠다. 그래서 상담·체험 일정을 저장하고 달력을
//   다시 열면 최대 60초 동안 옛 일정이 그대로 보였다 — 실무진에겐 '저장이 안 됐다'로 읽히는 그 부류다
//   (유효회원 목록에서 같은 이유로 _aaCacheClear_ 를 만든 것과 같은 사정).
//   달력 키는 월별이라 전부 열거할 수 없다. 현재 월 기준 앞뒤 2개월 + 월 미지정 키를 지운다 —
//   예약은 대개 근시일이라 이 범위가 실사용을 덮는다. 더 먼 달을 편집하면 그 달만 TTL 60초로 자연 해소된다.
function _miCacheClear_() {
  try {
    var c = CacheService.getScriptCache();
    _cacheInvalidateJson_(c, 'micache');
    _cacheInvalidateJson_(c, 'mccache|');          // 월 미지정 조회
    var _mcBase = new Date();
    for (var _mcD = -2; _mcD <= 2; _mcD++) {
      var _mcM = new Date(_mcBase.getFullYear(), _mcBase.getMonth() + _mcD, 1);
      _cacheInvalidateJson_(c, 'mccache|' + Utilities.formatDate(_mcM, 'Asia/Seoul', 'yyyy-MM'));
    }
  } catch (e) { /* 캐시 정리 실패가 저장 자체를 막지 않는다 — TTL 60초로 어차피 사라진다 */ }
}

function _cacheInvalidateJson_(cache, key) {
  try {
    var meta = cache.get(key + '__meta');
    var n = meta ? parseInt(meta, 10) : 0;
    var keys = [key + '__meta'];
    var max = Math.max(n, 12);  // 메타 유실 대비 여유 청크까지 제거
    for (var i = 0; i < max; i++) keys.push(key + '__' + i);
    cache.removeAll(keys);
  } catch (e) { /* 무효화 실패 무시 — TTL(60초) 만료로 자연 해소 */ }
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

// 팀/종목 컬러칩 — 문의알림방 메시지의 종목명 앞에 가이드라인 색 이모지 프리픽스(GM 확정 2026-07-10).
// 미등록 종목은 ''(칩 없음) → 목록 밖 팀은 임의 색 지정 금지.
// 종목 기준 이모지(GM 2026-07-14) — 부분매칭이라 '성인 수영 (개인레슨)' 같은 자유라벨도 잡힘. 첫 매치 우선.
function _teamChip(sport){
  var k=(sport||'').trim(); if(!k) return '';
  var rules=[['아쿠아','💦'],['수영','🏊'],['P.T','🏋️'],['PT','🏋️'],['필라','🧘'],['P.L','🧘'],['스쿼시','🎾'],['골프','⛳'],['트램폴린','🤸'],['체조','🤸'],['멤버십','🎫'],['뮤지컬','🎭'],['발레','🩰'],['바레','🩰'],['루프','🌀']];
  for(var i=0;i<rules.length;i++){ if(k.indexOf(rules[i][0])>=0) return rules[i][1]+' '; }
  return '';
}

// 회원권 프로그램명에서 뒤쪽 시설 나열 괄호 제거 — '노블레스 (Gym + G.X + Swimming + Sauna 이용)' → '노블레스'.
// 콤마 다중 회원권도 각 괄호 제거. 멤버십 1차 컨택 알림 가독성용(GM 2026-07-15). 다 지워지면 원본 유지(빈값 방지).
function _progNameOnly_(p){
  if(!p) return p;
  var s=String(p).replace(/\s*[\(（][^)）]*[\)）]/g,'').replace(/\s*,\s*/g,', ').trim();
  return s || p;
}

// ★전송 성공 여부를 돌려준다 — 2026-08-05 시토.
//   그동안 이 함수는 아무것도 반환하지 않았고, muteHttpExceptions:true 라서 텔레그램이 400·403·429 로
//   거절해도 예외조차 나지 않았다. 즉 "보냈다고 생각하지만 아무도 못 본" 상태를 부르는 쪽에서 구분할
//   방법이 없었다. 그런데 이 함수를 부르는 폴러들(_notifyNewInquiries_·_notifyLessonStatusChanges_)은
//   호출 직후 커서·마커를 다음으로 넘겨 버린다 — 한 번 실패한 신규 문의는 영원히 알림이 안 간다.
//   ▸반환값: true=텔레그램이 200으로 받음 / false=미설정·거절·네트워크 실패.
//   ▸기존 호출부는 반환값을 안 쓰므로 동작 변화 없음(하위호환). 커서를 옮기는 쪽만 이 값을 본다.
function _notifyTelegram(text, chatIdOverride) {
  const token = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN');
  const chatId = chatIdOverride || _prop('CHAT_ID') || _prop('TELEGRAM_CHAT_ID');
  if (!token || !chatId) { Logger.log('텔레그램 미발송 — 토큰/챗ID 미설정'); return false; }
  try {
    var _tgRes = UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'post', contentType: 'application/json',
      payload: JSON.stringify({ chat_id: chatId, text: text, parse_mode: 'HTML' }),
      muteHttpExceptions: true
    });
    var _tgCode = _tgRes.getResponseCode();
    if (_tgCode === 200) return true;
    // 429(과다발송)·400(HTML 파싱 실패)·403(봇 차단)이 여기로 온다. 본문 앞부분까지 남겨야 원인을 안다.
    Logger.log('텔레그램 거절(HTTP ' + _tgCode + '): ' + String(_tgRes.getContentText() || '').slice(0, 200));
    return false;
  } catch (e) { Logger.log('텔레그램 실패: ' + e.message); return false; }
}

// ─── 실데이터 마지막 행번호 탐색 헬퍼 (2026-06-25 버그수정) ───
// sh.getLastRow()는 빈 행(포맷만 있고 데이터 없는)을 포함해 반환하므로,
// INQ_LASTROW 마커를 그 값으로 세팅하면 실데이터 이후 빈행 영역이 마커보다 앞에 있어
// 새 제출이 영구 스킵되는 버그 발생.
// 이 함수는 역순으로 최대 500행을 탐색해 '전화번호 칼럼이 채워진' 마지막 행번호를 반환.
// 전화번호 없는 시트(멤버십 스태프 로그 등)는 타임스탬프로 폴백.
// 실데이터가 없으면 1(헤더행=기준선 최솟값) 반환.
function _realLastDataRow_(sh, idxPhone, idxDate, idxMemo) {
  var lastRow = sh.getLastRow();
  if (lastRow < 2) return 1;
  var lastCol = sh.getLastColumn();
  if (lastCol < 1) return 1;
  var readStart = Math.max(2, lastRow - 499);
  var rows = sh.getRange(readStart, 1, lastRow - readStart + 1, lastCol).getValues();
  for (var ri = rows.length - 1; ri >= 0; ri--) {
    var r = rows[ri];
    // [웹접수] 미러 행 제외
    if (idxMemo >= 0 && String(r[idxMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) continue;
    var hasPhone = idxPhone >= 0 && !!r[idxPhone];
    var hasTs    = idxDate  >= 0 && !!r[idxDate];
    if (hasPhone || hasTs) return readStart + ri;
  }
  return 1;
}

// ─── 자체폼(웹) 접수분인가 — 폴러 제외 판정 (2026-07-27 시토 · GM 지적으로 발각) ───
// 왜 태그만으로 부족한가: 자체폼 접수는 비고칸에 [웹접수] 표식을 남겨 폴러가 걸러낸다.
//   그런데 **강습 2탭(성인·유소년)에는 비고 칸 자체가 없다** — 2026-07-18 GM 결정으로 강습
//   자체폼 접수가 기존 구글폼 응답탭에 저장되도록 바뀌었는데, 그 탭에는 표식을 쓸 자리가 없다.
//   결과: 자체폼 접수 알림(intake_submit)이 이미 나갔는데 폴러가 같은 행을 또 잡아 두 번 나갔고,
//   형식도 달라 GM 이 "왜 이 건만 양식이 다르냐"고 지적하게 됐다(2026-07-27 4:49 유소년 건).
// 대신 무엇을 보나: 강습 자체폼은 '접수 담당자' 칸에 '웹 자동접수'를 반드시 남긴다(_lsSet).
//   실측 확인 — 유소년 4615행·성인 3550행 모두 '웹 자동접수'. 이 값은 사람이 쓰지 않는다.
//   ★2026-08-08: 멤버십 경로(_imSet·CTA 미러)는 담당자 기본값이 '임정은'으로 바뀌어 이 검사에 안 걸린다.
//   멤버십 시트('26년 신규문의')는 비고 칸이 있어 위 WEB_INTAKE_TAG 검사가 그대로 걸러 준다 —
//   담당자 칸에 의존하던 건 비고 칸이 없는 강습 2탭뿐이었다.
function _isWebIntakeRow_(r, headers) {
  try {
    var iMemoW = _findCol_(headers, ['비고', '메모']);
    if (iMemoW >= 0 && String(r[iMemoW] || '').indexOf(WEB_INTAKE_TAG) >= 0) return true;
    var iOwnerW = _findCol_(headers, ['접수 담당자', '담당']);
    if (iOwnerW >= 0 && String(r[iOwnerW] || '').trim() === '웹 자동접수') return true;
  } catch (e) { /* 판정 실패 = 제외 안 함(알림을 잃지 않는 쪽) */ }
  return false;
}
// ─── 신규 문의 감지 → 텔레그램 '문의 알림' 방 발송 (시모, 2026-06-24) ───
// FORM_SHEETS 각 시트의 신규 행을 5분마다 감지해 TELEGRAM_INQUIRY_CHAT_ID 방으로 알림.
// ScriptProperties INQ_LASTROW_<ssId>_<gid> 에 마지막 처리한 실데이터 행번호 저장 → 중복 방지.
// 최초 실행: 기준선만 저장, 과거 문의 일괄발송 없음.
// ★ 마커 = 실데이터 마지막 행번호(전화번호/타임스탬프 기준). getLastRow()(빈행포함) 사용 금지.
var _INQUIRY_CHAT_ID_FALLBACK = '-5516675010';  // '문의 알림' 방 — 프로퍼티 없을 때 폴백(그룹 ID, 민감정보 아님)

function _notifyNewInquiries_() {
  var props = PropertiesService.getScriptProperties();
  var inquiryChatId = props.getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;

  FORM_SHEETS.forEach(function(cfg) {
    var propKey = 'INQ_LASTROW_' + cfg.ssId + '_' + cfg.gid;
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) return;

      // 헤더를 먼저 읽어 실데이터 탐색에 필요한 칼럼 인덱스 확보
      var lastCol = sh.getLastColumn();
      if (lastCol < 1) return;
      var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
      var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
      var idxName  = _findCol_(headers, ['성함', '이름', 'Full Name', 'Name', "Child's Full Name"]);
      var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화', 'Mobile Phone', 'Phone', "Guardian's Mobile Phone"]);
      var idxChan  = _findCol_(headers, cfg.channelKeys || ['채널', '경로', '알게', 'How Did You Hear']);
      var idxMemo  = _findCol_(headers, ['비고', '메모']);
      var idxProg  = _findCol_(headers, cfg.programKeys || ['종목', '프로그램', '과목', 'Program']);
      var idxContent = _findCol_(headers, INQUIRY_CONTENT_KEYS);  // 문의 내용(자유서술) 칸 — GM 2026-06-29 시토

      // ★ 실데이터 마지막 행번호 (전화번호/타임스탬프 기준, 빈행 제외)
      var realLastRow = _realLastDataRow_(sh, idxPhone, idxDate, idxMemo);
      var storedStr   = props.getProperty(propKey);

      // 최초 실행: 실데이터 기준선 저장 후 종료 (과거분 폭주 방지)
      if (!storedStr) {
        props.setProperty(propKey, String(realLastRow));
        Logger.log('[문의알림] 기준선 저장 — ' + cfg.type + ' realLastRow=' + realLastRow);
        return;
      }

      var storedRow = parseInt(storedStr, 10) || 1;
      if (realLastRow <= storedRow) return; // 신규 실데이터 없음

      // 신규 행 처리 (storedRow+1 ~ realLastRow)
      // ★커서는 '실제로 알림이 나간 데까지만' 올린다 — 2026-08-05 시토.
      //   종전엔 forEach 로 전부 돌린 뒤 무조건 realLastRow 를 저장했다. 그래서 텔레그램이 한 건이라도
      //   거절하면(429 과다발송·400 파싱실패·순간 네트워크 오류) 그 문의는 다시 시도되지 않고 영구히
      //   사라졌다 — 실무진 입장에선 "문의가 들어왔는데 알림이 안 왔다"가 되고, 원인은 로그에도 안 남았다.
      //   ▸이제 첫 실패 지점에서 멈추고 커서를 그 직전 행까지만 올린다. 5분 뒤 다음 주기가 그 행부터 재시도한다.
      //   ▸대가: 텔레그램이 200을 안 줬는데 실제로는 배달된 드문 경우 같은 알림이 한 번 더 갈 수 있다.
      //     중복 한 통이 문의 유실보다 낫다는 판단(놓친 문의는 매출로 직결).
      var newRows = sh.getRange(storedRow + 1, 1, realLastRow - storedRow, lastCol).getValues();
      var _advanceTo = realLastRow;
      for (var _ni = 0; _ni < newRows.length; _ni++) {
        var r = newRows[_ni];
        // [웹접수] 미러 행 제외 (이미 submit_inquiry에서 발송)
        if (_isWebIntakeRow_(r, headers)) continue;   // 자체폼 접수분 — 접수 알림은 intake_submit 이 이미 보냈다
        // 완전 빈 행 스킵
        if (!r[idxDate >= 0 ? idxDate : 0] && (idxPhone < 0 || !r[idxPhone])) continue;

        var ts = idxDate >= 0 ? r[idxDate] : '';
        var tsStr = '';
        try {
          var d = _normTs_(ts);
          tsStr = isNaN(d.getTime()) ? String(ts).substring(0, 16) : Utilities.formatDate(d, 'Asia/Seoul', 'MM/dd HH:mm');
        } catch (e) { tsStr = String(ts).substring(0, 16); }

        var name  = idxName  >= 0 ? String(r[idxName]  || '').trim() : '-';
        var phone = idxPhone >= 0 ? String(r[idxPhone] || '').trim() : '-';
        var chan  = idxChan  >= 0 ? String(r[idxChan]  || '').trim() : '-';
        var prog  = idxProg  >= 0 ? String(r[idxProg]  || '').trim() : '';
        if (!name)  name  = '-';
        if (!phone) phone = '-';
        if (!chan)  chan  = '-';

        var content = idxContent >= 0 ? String(r[idxContent] || '').trim() : '';
        if (content.length > 300) content = content.substring(0, 300) + '…';
        // ★2026-07-23 GM 규칙 이식(2026-07-27 시토 · GM 지적 '양식 달리 들어오는 건 불편하다').
//   실무진 '문의 알림' 방에는 자체폼(홈페이지 접수) 건만 넣는다. 이 폴러가 잡는 행은 구조상 전부
//   '자체폼 외'다 — 자체폼 유입분은 비고의 WEB_INTAKE_TAG 로 이미 제외된다. 따라서 여기 남는 건
//   = 구글폼 응답탭 직접 유입 → 접두사를 붙이고 GM 개인 업무보고방으로 보낸다.
//   ※이 규칙이 구 퍼널(.deploy-funnel)에만 있고 v2 로 안 옮겨져, 구글폼 건이 접두사 없이
//     실무진 방으로 들어가고 있었다(2026-07-27 04:49 유소년강습 WSC체조&트램폴린 건으로 발각).
        var msg = '📥 [자체폼 외 유입] 🔔 [신규 문의]\n'
          + '유형: ' + cfg.type + '\n'
          + (prog ? '종목: ' + _teamChip(prog) + prog + '\n' : '')
          + '이름: ' + name + '\n'
          + '연락처: ' + phone + '\n'
          + '유입채널: ' + chan
          + (content ? '\n내용: ' + content : '');
        var _sent = _notifyTelegram(msg)   /* 자체폼 외 = GM 개인 업무보고방(2026-07-23 GM 규칙) */;
        if (!_sent) {
          // 이 행(물리 storedRow+_ni+1)은 아직 아무도 못 봤다 → 커서를 바로 앞 행까지만 올리고 멈춘다.
          _advanceTo = storedRow + _ni;
          Logger.log('[문의알림] 전송 실패로 중단 — ' + cfg.type + ' 커서=' + _advanceTo + '(다음 주기 재시도)');
          break;
        }
      }

      // 기준선 갱신 — 실데이터 마지막 행번호로 저장 (빈행 포함 getLastRow 사용 금지)
      props.setProperty(propKey, String(_advanceTo));
    } catch (e) {
      Logger.log('[문의알림] ' + cfg.type + ' 오류: ' + e.message);
    }
  });

  // 강습 팀시트 상태변경(컨택/등록) 알림도 같은 5분 주기로 — 멤버십과 달리 강습은 팀시트 직접 처리라 별도 폴러 필요(2026-07-14 GM go)
  try { _notifyLessonStatusChanges_(); } catch (e) { Logger.log('[강습상태알림] ' + e.message); }
}

// ─── 강습 팀시트 상태변경 알림 폴러 (2026-07-14 시토·GM go) ───
// 각 강습 팀시트(LESSON_TEAM_SHEETS)에서 상태가 '컨택'·'등록(SUC)'으로 바뀌면 문의알림방에 알림.
// 멤버십(문의회원 페이지→GAS)은 상태변경이 GAS를 거쳐 알림이 발화하나, 강습은 팀장이 팀시트에서 직접
// 처리해 감지 경로가 없었음 → 이 폴러가 팀시트를 읽어 컨택/등록 전환만 골라 알림.
// 중복방지: ScriptProperties LESSON_NOTIFIED_<ssId>_<gid> 에 이미 알린 'rowKey|bucket' 집합 저장.
// 최초 실행(마커 없음): 현 컨택/등록 상태를 baseline으로만 저장하고 알림 없음(기존분 폭주 방지).
function _notifyLessonStatusChanges_() {
  var props = PropertiesService.getScriptProperties();
  var chatId = props.getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
  LESSON_TEAM_SHEETS.forEach(function(cfg) {
    var propKey = 'LESSON_NOTIFIED_' + cfg.ssId + '_' + cfg.gid;
    try {
      var sh = _sheetByGid_(cfg.ssId, cfg.gid);
      if (!sh) return;
      var last = sh.getLastRow(), lastCol = sh.getLastColumn();
      if (last < 2 || lastCol < 1) return;
      var data = sh.getRange(1, 1, last, lastCol).getValues();
      var headers = data[0];
      // 상태열 탐지 — _collectLessonRegistrations_와 동일 휴리스틱(고유값 2~30 + 코드형 상태값 최다 열)
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
      if (best < 0) return;  // 상태열 미발견 — 알림 없음(날조 금지)
      var idxName  = _findCol_(headers, ['성함', '이름', '성명', '수강생', '회원명']);
      var idxOwner = _findCol_(headers, ['담당', '담당자', '팀장', '강사']);

      var curKeys = [];
      var events = [];
      for (var r2 = 1; r2 < data.length; r2++) {
        var sv = String(data[r2][best] || '').trim();
        if (!sv) continue;
        var bucket = null;
        if (_isLessonReg_(sv)) bucket = 'SUC';
        else if (/컨택|응대|연락|통화|문자|회신/.test(sv)) bucket = 'CONTACT';
        if (!bucket) continue;
        var nm = idxName >= 0 ? String(data[r2][idxName] || '').trim() : '';
        var rowKey = nm || ('행' + (r2 + 1));
        var mark = rowKey + '|' + bucket;
        curKeys.push(mark);
        events.push({ mark: mark, bucket: bucket, name: nm, owner: idxOwner >= 0 ? String(data[r2][idxOwner] || '').trim() : '' });
      }

      var storedStr = props.getProperty(propKey);
      if (!storedStr) {
        try { props.setProperty(propKey, JSON.stringify(curKeys)); } catch (e) {}
        return;  // baseline만 저장, 알림 없음
      }
      var stored = {};
      try { (JSON.parse(storedStr) || []).forEach(function(k) { stored[k] = 1; }); } catch (e) {}

      // ★보내지 못한 전환은 '알린 것'으로 기록하지 않는다 — 2026-08-05 시토(_notifyNewInquiries_ 커서와 같은 수리).
      //   종전엔 전송 결과와 무관하게 curKeys 전체를 마커로 저장해, 텔레그램이 거절한 등록·컨택 전환은
      //   두 번 다시 알림이 가지 않았다(마커에 이미 있으니 다음 주기가 건너뛴다).
      var _failedMarks = {};
      events.forEach(function(ev) {
        if (stored[ev.mark]) return;  // 이미 알린 전환
        var chip = _teamChip(cfg.명);
        var who = ev.name || '(이름미상)';
        var owner = ev.owner ? (' · 담당 ' + ev.owner) : '';
        var _lsSent;
        if (ev.bucket === 'SUC') {
          _lsSent = _notifyTelegram('✅ <b>[강습 등록]</b> ' + chip + cfg.명 + '\n· 수강생: ' + who + owner, chatId);
        } else {
          _lsSent = _notifyTelegram('📞 <b>[강습 컨택]</b> ' + chip + cfg.명 + '\n· 수강생: ' + who + owner, chatId);
        }
        if (!_lsSent) _failedMarks[ev.mark] = 1;   // 다음 주기가 다시 시도하도록 마커에서 뺀다
      });
      var _saveKeys = curKeys.filter(function(k) { return !_failedMarks[k]; });
      if (_saveKeys.length !== curKeys.length) {
        Logger.log('[강습상태알림] 전송 실패 ' + (curKeys.length - _saveKeys.length) + '건 — 마커 보류(다음 주기 재시도): ' + cfg.명);
      }

      try { props.setProperty(propKey, JSON.stringify(_saveKeys)); }
      catch (e) { Logger.log('[강습상태알림] 마커 저장 실패(' + cfg.명 + '): ' + e.message); }
    } catch (e) { Logger.log('[강습상태알림] ' + cfg.명 + ' 오류: ' + e.message); }
  });
}

// 강습 상태변경 폴러 수동 실행·검증용(밑줄 없는 공개 함수 — 에디터 Run 드롭다운에 표시된다).
// 첫 실행은 baseline만 저장(알림 없음)이 정상. 실제 알림은 5분 트리거(_notifyNewInquiries_)가 자동 처리.
function testLessonStatusCheck() {
  _notifyLessonStatusChanges_();
  Logger.log('강습 상태변경 폴러 1회 실행 완료 — 첫 실행이면 baseline 저장(알림 없음). 이후 실제 컨택/등록 전환 시 알림.');
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

// ─── onFormSubmit 즉시 알림 핸들러 (2026-06-25 시모) ───
// 구글폼 응답 시트에 새 행이 추가될 때 즉시 발화 → 5분 대기 없이 즉시 발송.
// 공유 INQ_LASTROW 마커를 갱신해, 폴링 백스톱(_notifyNewInquiries_)이 같은 행을 재발송하지 않음.
// ★ 어느 폼 시트에서 발화했는지 이벤트 range로 자동 식별 — 별도 분기 불필요.
function onInquiryFormSubmit(e) {
  try {
    var props = PropertiesService.getScriptProperties();
    var inquiryChatId = props.getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;

    // 이벤트 range에서 시트 식별
    var sheet = e && e.range ? e.range.getSheet() : null;
    if (!sheet) return;
    var ssId = sheet.getParent().getId();
    var gid  = sheet.getSheetId();

    // FORM_SHEETS에서 일치하는 cfg 탐색
    var cfg = null;
    for (var i = 0; i < FORM_SHEETS.length; i++) {
      if (FORM_SHEETS[i].ssId === ssId && FORM_SHEETS[i].gid === gid) { cfg = FORM_SHEETS[i]; break; }
    }
    if (!cfg) return; // 관리 대상 아닌 시트 — 무시

    var propKey  = 'INQ_LASTROW_' + cfg.ssId + '_' + cfg.gid;
    var lastCol  = sheet.getLastColumn();
    if (lastCol < 1) return;
    var headers  = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
    var idxName  = _findCol_(headers, ['성함', '이름', 'Full Name', 'Name', "Child's Full Name"]);
    var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화', 'Mobile Phone', 'Phone', "Guardian's Mobile Phone"]);
    var idxChan  = _findCol_(headers, cfg.channelKeys || ['채널', '경로', '알게', 'How Did You Hear']);
    var idxMemo  = _findCol_(headers, ['비고', '메모']);
    var idxProg  = _findCol_(headers, cfg.programKeys || ['종목', '프로그램', '과목', 'Program']);
    var idxContent = _findCol_(headers, INQUIRY_CONTENT_KEYS);  // 문의 내용(자유서술) 칸 — GM 2026-06-29 시토

    // ★ 실데이터 마지막 행번호 (빈행 포함 getLastRow 사용 금지)
    var realLastRow = _realLastDataRow_(sheet, idxPhone, idxDate, idxMemo);
    var storedStr   = props.getProperty(propKey);
    var storedRow   = storedStr ? (parseInt(storedStr, 10) || 1) : 1;

    // 새 실데이터 행이 기준선 이하면 이미 처리된 것 — 중복 방지
    if (realLastRow <= storedRow) return;

    // 기준선 초과 신규 행 모두 처리 (동시 다중 제출 방어)
    var newRows = sheet.getRange(storedRow + 1, 1, realLastRow - storedRow, lastCol).getValues();
    newRows.forEach(function(r) {
      if (_isWebIntakeRow_(r, headers)) return; // 자체폼 접수분 제외(비고 태그 없는 강습 탭 포함)
      if (!r[idxDate >= 0 ? idxDate : 0] && (idxPhone < 0 || !r[idxPhone])) return;      // 빈 행 스킵

      var ts = idxDate >= 0 ? r[idxDate] : '';
      var tsStr = '';
      try {
        var d = _normTs_(ts);
        tsStr = isNaN(d.getTime()) ? String(ts).substring(0, 16) : Utilities.formatDate(d, 'Asia/Seoul', 'MM/dd HH:mm');
      } catch (ex) { tsStr = String(ts).substring(0, 16); }

      var name  = (idxName  >= 0 ? String(r[idxName]  || '').trim() : '') || '-';
      var phone = (idxPhone >= 0 ? String(r[idxPhone] || '').trim() : '') || '-';
      var chan  = (idxChan  >= 0 ? String(r[idxChan]  || '').trim() : '') || '-';
      var prog  = (idxProg  >= 0 ? String(r[idxProg]  || '').trim() : '');

      var content = idxContent >= 0 ? String(r[idxContent] || '').trim() : '';
      if (content.length > 300) content = content.substring(0, 300) + '…';
      var msg = '📥 [자체폼 외 유입] 🔔 [신규 문의 — 즉시]\n'
        + '유형: ' + cfg.type + '\n'
        + (prog ? '종목: ' + _teamChip(prog) + prog + '\n' : '')
        + '이름: ' + name + '\n'
        + '연락처: ' + phone + '\n'
        + '유입채널: ' + chan
        + (content ? '\n내용: ' + content : '');
      _notifyTelegram(msg)   /* 자체폼 외 = GM 개인 업무보고방(2026-07-23 GM 규칙) */;
    });

    // 기준선 갱신 — 실데이터 마지막 행번호로 저장 (폴링 백스톱 중복 발송 방지)
    props.setProperty(propKey, String(realLastRow));
  } catch (ex) {
    Logger.log('[즉시알림] onInquiryFormSubmit 오류: ' + ex.message);
  }
}

// onFormSubmit 트리거 + 폴링 백스톱 통합 설치.
// 편집권한이 있는 응답 시트(cao 소유: 멤버십 계열)에만 onFormSubmit 트리거를 건다.
// 편집 불가 시트(강습 계열 타계정)는 폴링 백스톱(_notifyNewInquiries_)이 커버.
// 웹앱 action=install_inquiry_triggers 호출 시에도 실행 가능(cao 실행 계정으로 트리거 생성됨).
function installInquiryFormSubmitTriggers() {
  var props    = PropertiesService.getScriptProperties();
  var existing = ScriptApp.getProjectTriggers();
  var results  = [];

  // ① onFormSubmit 트리거 — 편집 가능 ssId 별로 1개씩 (시트 단위 아님: 스프레드시트 단위로 발화)
  // 같은 스프레드시트에 gid가 여러 개여도 트리거는 ssId 1개당 1개.
  var seenSsIds = {};
  FORM_SHEETS.forEach(function(cfg) {
    if (seenSsIds[cfg.ssId]) return; // 이미 처리한 ssId 스킵
    seenSsIds[cfg.ssId] = true;

    // 편집 권한 확인 — openById 시도 후 getEditors() 에 cao 포함 여부
    var canEdit = false;
    try {
      var ss = SpreadsheetApp.openById(cfg.ssId);
      ss.getName(); // 접근 가능성 확인
      canEdit = true;
    } catch (e) {
      results.push({ ssId: cfg.ssId, status: 'SKIP_NO_ACCESS', reason: e.message });
      return;
    }

    // 중복 체크 — 동일 ssId + onInquiryFormSubmit 핸들러 조합
    var alreadyExists = existing.some(function(t) {
      return t.getHandlerFunction() === 'onInquiryFormSubmit' &&
             t.getTriggerSourceId && t.getTriggerSourceId() === cfg.ssId;
    });
    if (alreadyExists) {
      results.push({ ssId: cfg.ssId, status: 'ALREADY_EXISTS' });
      return;
    }

    try {
      ScriptApp.newTrigger('onInquiryFormSubmit')
        .forSpreadsheet(cfg.ssId)
        .onFormSubmit()
        .create();
      // INQ_LASTROW 기준선 미설정 시 실데이터 마지막 행번호로 초기화 (과거분 폭주 방지)
      // ★ getLastRow()(빈행포함) 금지 — 실데이터 기준 _realLastDataRow_ 사용
      FORM_SHEETS.filter(function(f) { return f.ssId === cfg.ssId; }).forEach(function(f) {
        var pk = 'INQ_LASTROW_' + f.ssId + '_' + f.gid;
        if (!props.getProperty(pk)) {
          try {
            var sh = _sheetByGid_(f.ssId, f.gid);
            if (sh) {
              var lastCol2 = sh.getLastColumn();
              var hdrs2 = lastCol2 > 0 ? sh.getRange(1, 1, 1, lastCol2).getValues()[0] : [];
              var iP2 = _findCol_(hdrs2, ['연락처','휴대폰','핸드폰','전화','Mobile Phone','Phone',"Guardian's Mobile Phone"]);
              var iD2 = _findCol_(hdrs2, ['타임스탬프','timestamp','시각','일시','접수일','접수','날짜']);
              var iM2 = _findCol_(hdrs2, ['비고','메모']);
              props.setProperty(pk, String(_realLastDataRow_(sh, iP2, iD2, iM2)));
            }
          } catch (e2) {}
        }
      });
      results.push({ ssId: cfg.ssId, status: 'INSTALLED' });
    } catch (e) {
      results.push({ ssId: cfg.ssId, status: 'FAILED', reason: e.message });
    }
  });

  // ② 폴링 백스톱(_notifyNewInquiries_ 5분) — 없으면 설치
  var hasPolling = existing.some(function(t) { return t.getHandlerFunction() === '_notifyNewInquiries_'; });
  if (!hasPolling) {
    try {
      ScriptApp.newTrigger('_notifyNewInquiries_').timeBased().everyMinutes(5).create();
      results.push({ handler: '_notifyNewInquiries_', status: 'POLLING_INSTALLED' });
    } catch (e) {
      results.push({ handler: '_notifyNewInquiries_', status: 'POLLING_FAILED', reason: e.message });
    }
  } else {
    results.push({ handler: '_notifyNewInquiries_', status: 'POLLING_ALREADY_EXISTS' });
  }

  return results;
}

// ════════════════════════════════════════════════════════════════════════
// [2026-07-19 시토] v2(prod) 문의알림 트리거 설치 — GM 1회 실행용(이사 완결).
// v1→v2 이사(2026-07-18) 때 미이전된 문의 트리거를 v2에 설치한다. 현행 dedup 코드라
// onInquiryFormSubmit(즉시)이 마커 INQ_LASTROW 갱신 → 5분 poller가 같은 행 재발송 안 함
// → 문의당 알림 1회만(단일 보장). installInquiryFormSubmitTriggers는 멱등(중복설치 방지).
// ★반드시 v1의 cleanupInquiryTriggersV1 실행 '후'에 실행(순서 어기면 순간 3중).
// 최종 상태: v2 = onFormSubmit(멤버십) + 폴링 백스톱, v1 = 문의 트리거 0.
// ════════════════════════════════════════════════════════════════════════
function setupInquiryTriggersV2() {
  var results = installInquiryFormSubmitTriggers();
  Logger.log('[v2 문의트리거 설치] ' + JSON.stringify(results));
  return results;
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
  intake_submit:  true,  // 유입 자체 Survey 폼 제출(배1037 갈래B) — 토큰(INTAKE_SUBMIT_TOKEN)·허니팟·타이밍·레이트리밋으로 별도 방어. 2026-07-15 시포
  ping_inquiry_notify: true,  // [진단용] BOT_TOKEN 확인 + 문의 알림 방 테스트 발송 (시모 2026-06-24)
  staff_feedback_submit: true,  // 실무진 피드백 제출 — intake_submit 과 동일하게 토큰(INTAKE_SUBMIT_TOKEN)·허니팟·멱등·레이트리밋으로 별도 방어. 고객 PII 미취급(별도 탭). 2026-07-24 시포·GM
  // 마케팅 집계(PII 미노출) 면제 — 2026-06-17 CMO, 시토 게이트 공유
  // 아래 액션들은 집계 숫자만 반환 · 이름·전화 등 원시 개인정보 미노출 → 면제 안전.
  // inquiry_list 등 원시 행/PII 반환 액션은 절대 면제 금지(게이트 유지).
  period_breakdown:       true,
  funnel_conversion:      true,
  type_channel_breakdown: true,
  lead_time_stats:        true,  // 문의→등록 평균 전환 소요일(집계 숫자만·PII 미노출) — 면제 안전 (2026-06-23 CMO)
  today_live:             true,
  lesson_breakdown:       true,  // 종목별 등록수만 반환(PII 미노출) — 면제 안전
  // 문의회원 페이지(CPO) 익명 읽기 — 이름·전화·메모 0 노출 → 공개 안전(2026-06-22 A안)
  member_inquiry_list:    true,
  member_inquiry_summary: true,  // 담당자별 건수만(이름·전화·메모 0) — 업무 SSOT 상단 판이 숫자 4개만 쓰는데
                                 //   member_inquiry_list 를 부르면 694행 PII 를 통째로 내려받게 된다. 그래서 집계 전용.
  member_calendar:        true,
  member_inquiry_update:  true,  // 2026-06-22 GM '전체 공개' — 실명·전화 포함 수정
  member_inquiry_add:     true,  // 2026-06-23 전화·직접 문의 수기 추가
  member_inquiry_delete:  true,  // 행 삭제
  client_write_fail:      true,  // 저장 실패 보고(밀린 건수만·회원 데이터 미저장) — 게이트가 켜져도 실무진 PC 에서
                                 //   실패 신호는 올라와야 한다. 2026-08-25 시포·GM
  member_registered_list:     true,  // 2026-06-23 등록현황(SUC/단기SUC) 조회
  // member_registered_setmonth 제거(2026-08-06 시토, 배295 점검) — 호출부 0건(membership.html 어디서도
  //   부르지 않고, member_registered_list 응답에 월 필드 자체가 없어 체크해도 화면에 뜰 수가 없었다).
  //   member_registered_delete 와 같은 사유(약속 L21, 죽은 쓰기 통로는 남기지 않는다) — 삭제.
  // member_registered_delete 제거(2026-08-05 시토, INC-042 재발방지 ②) — 호출부 0건(membership.html 등록
  //   해제는 member_inquiry_update→_regRemove_ 경유, 2026-06-29 시포). 이 액션은 비밀번호·중복전화 가드
  //   없이 전화 1건 매칭 즉시 deleteRow 하는 물리 삭제 통로였다 — 죽은 코드로 남기면 다시 켜질 위험
  //   (약속 L21), 삭제.
  member_registered_add:      true,  // 2026-06-29 등록현황 직접 추가(페이지 수기 등록)
  member_registered_remove:   true,  // 2026-08-06 시토(배295) — "+직접등록" 되돌리기. 비밀번호 게이트 +
                                      //   중복전화 가드(_regRemove_) + 유효회원 동반 정리(_regActiveRemoveIfSole_)
  member_active_list:         true,  // 멤버십 회원 명단(유효회원·전화 마스킹)
  member_active_update:       true,  // 2026-06-24 멤버십 셀 인라인 수정(유효회원 시트·전화 제외)
  member_archive_restore:     true,  // 2026-08-25 시토 — LOSS보관 회원 재등록 복귀(보관 행 삭제+유효회원 신규행, 2026-08-26 개정)
  member_registry_build:      true,  // 2026-08-26 시포(GM 승인·배801) — 회원등기부 구축·회원번호 부여(멱등·dryRun 지원)
  member_active_sort_now:     true,  // 2026-08-12 잔여일순 정렬 온디맨드(행 순서만 바꿈·값 무변경·PII 미반환)
  member_hold_preview:        true,  // 2026-07-22 휴회 경량안 — 미리보기/검증(read-only, 시트 무변경). 시포·GM
  member_hold_apply:          true,  // 2026-07-22 휴회 공개접수(쓰기전용 → '휴회접수' 탭·회원 판정 미반환). ★HOLD_LIVE 게이트(OFF). 시포·GM
  member_hold_intake_list:    true,  // 2026-07-22 휴회 접수관리 리스트(ERP read+서버 자동판정). 게이트 뒤. 시포·GM
  member_hold_approve:        true,  // 2026-07-22 휴회 승인/반려(직원 → 회원DB '이용일수' 앞 새칸 기록+증분). ★HOLD_LIVE_T 게이트(OFF). 시포·GM
  member_hold_transition:     true,  // 2026-07-22 휴회 회원 라이프사이클 전이(진행중↔완료). ★HOLD_LIVE_T 게이트(OFF). 시포·GM
  member_owner_save:          true,  // 2026-07-18 시포 — 종목별 담당자 5칸(화이트리스트) 단일셀 저장(전화 매칭)
  member_owner_bulk_set:      true,  // 2026-07-20 GM 지시 — 멤버십 담당자('담당자'만) 열 일괄 배치 쓰기(setValues 1회)
  member_active_summary:      true,  // 2026-07-20 시포 — 회원관리 카드 요약 집계(§2-A 로딩속도, PII 미노출·숫자만)
  cpo_today_stats:            true,  // 2026-06-24 CPO 오늘/이번달 문의·등록 건수(PII 미노출)
  cpo_churn_stats:            true,  // 2026-07-02 이탈 현황 실측(유효·이탈·이탈율·갱신임박 리스트) — 페이지 게이트 뒤(전체공개 정책과 동일)
  // 강습문의 페이지(CPO) — 멤버십 member_* 와 동일 정책(2026-06-26)
  lesson_inquiry_list:        true,  // 성인 강습 문의 목록(관리 필드 포함)
  lesson_stats:               true,  // 강습 통계(총·이번달·종목·경로 분포)
  lesson_calendar:            true,  // 상담예약 달력
  lesson_inquiry_update:      true,  // 진행상태·담당·상담메모·상담예약·방문상태 수정
  lesson_inquiry_add:         true,  // 2026-08-25 전화·직접 강습문의 수기 추가(member_inquiry_add 동일 취급)
  lesson_registered_roster:   true,  // 강습 등록현황·회원 명단(팀시트 상태열 _isLessonReg_) — PII 노출(전체공개 2026-06-22) 2026-06-27 시포
  lesson_registry_list:       true,  // 강습 금일 등록현황(원장 sync-on-load) — PII 노출(전체공개) 2026-06-27 시포
  lesson_team_sheet_diag:     true,  // [진단] 강습 팀시트 구조(헤더·상태열·빈칸 수) — 셀 값 미반환·토큰 필요. 2026-07-23 시포·GM
  member_hold_intake_migrate: true,  // 휴회 접수 탭 이관(회원DB→종합접수처) — 대조키 복사·원본 보존·기본 예행·토큰 필요. 배9948
  warm_cache_trigger:         true,  // 명단 캐시 워머 트리거 설치/해제/상태 — 읽기 전용 워밍·토큰 필요. 2026-07-23 시포·GM
  // 공간렌트·비즈니스 문의 패널(CPO) — lesson_inquiry_list/lesson_stats 와 동일 취급(PII 노출·전체공개). 2026-07-04 시포.
  rentbiz_inquiry_list:       true,  // 공간렌트·비즈니스 문의 목록(성함/단체명·연락처 등 원시 필드 포함)
  rentbiz_stats:              true,  // 공간렌트·비즈니스 통계(총·이번달·경로 분포·상태별 — 상태컬럼 없으면 상태 집계 생략)
  pii_status:                 true,  // [진단] PII_MASK/토큰 설정 상태(비밀값 미노출) 2026-06-25 시토
  // 트리거 관리 — 설치/조회/테스트 (2026-06-25 시모, 즉시알림 전환)
  install_inquiry_triggers:   true,  // onFormSubmit 트리거 + 폴링 백스톱 설치 (웹앱 호출 시 cao 계정으로 실행)
  list_inquiry_triggers:      true,  // 현재 트리거 목록 조회 (핸들러·타입·소스ID)
  test_form_submit_notify:    true,  // onFormSubmit 경로 mock 테스트 — 문의알림방에 TEST 메시지 1건
  resend_recent_inquiry:      true,  // 누락분 수동 발송 — FORM_SHEETS 최근 문의 1건 재발송 (마커 불변)
  diag_inquiry_ts:            true,  // 진단: 시트별 마지막 3행 타임스탬프 파싱 결과 (2026-06-25)
  diag_inquiry_state:         true,  // 진단(읽기전용): 마커값·실데이터행·트리거목록 (2026-06-25 시모)
  reset_inquiry_markers:      true,  // 마커 교정(발송0): 각 시트 실데이터 마지막 행으로 덮어씀 (2026-06-25)
  count_missed_inquiries:     true,  // 읽기전용: 특정 시각 이후 신규 실데이터 행 건수 집계 (2026-06-25)
  read_rows_by_rownum:        true,  // 읽기전용: 지정 시트·행번호의 알림 필드 원문 반환 (2026-06-25)
  preview_notify_msg:         true,  // 읽기전용: 지정 행의 알림 메시지 텍스트 미리보기(발송 0) (2026-06-25)
  lesson_rewire_audit:        true,  // [진단·읽기전용] 6팀시트 은퇴 안전게이트 — OLD(6팀시트) vs NEW(메인4시트 flat O) IDENTICAL 대조(카운트만·PII 미노출). 배973 시포. 2026-07-15 실측: 불일치(성인 812→794·유소년 926→908 등, 상세=재배선핸드오프). 은퇴 전 이 액션이 OLD≡NEW 반환할 때까지 반복 검증.
  funnel_conversion_detail:   true,  // 2026-07-20 GM 지시(배834) — M1 마케팅 대시보드 채널별 가입전환 상세 명단. PII 노출(이름·연락처뒷4자리) — member_inquiry_list 등과 동일 정책(전체공개, 읽기전용·원본시트 미변경). 연락처는 서버에서 뒷4자리로 절단 후 반환(전체번호 미노출).
  // 오넛티 선물세트(2026-08-07 GM 지시) — remaining은 숫자만(PII 0) 면제 안전. team_list는 이름/전화 원시행이 있지만
  //   서버가 이름을 첫글자만 내보내고 연락처는 아예 안 담아 보낸다(클라이언트 마스킹 아님) + 자체 접속코드(_ohnuttiTeamAuthed_)로
  //   막아 member_registered_remove(STAFF_GATE_PW)와 동일하게 "마스터 토큰 게이트는 면제 + 자체 코드 게이트는 별도 유지" 패턴.
  ohnutti_remaining:   true,
  ohnutti_team_list:   true
};
// add_utm_field 비밀 가드값 — 폼 변형 액션 무단호출 차단. _SURVEY_PUBLIC_ACTIONS에 넣지 말 것.
var _ADD_UTM_GUARD = 'wp-utm-field-2026-i-am-sure';
// naver_split_midcat 비밀 가드값 — 시트 데이터 검증 규칙 변형 액션 무단호출 차단. _SURVEY_PUBLIC_ACTIONS에 넣지 말 것.
var _NAVER_SPLIT_GUARD = 'wp-naver-midcat-split-2026-gm-ok';
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

// PII 마스킹 게이트 — 원시 실명·전화는 토큰 있을 때만 풀(full)로. 2026-06-25 시토(GM go: '닫기').
// ★ 불변식: PII_MASK 가 'on' 이 아니면(기본) 항상 풀 반환 → 코드 배포만으로는 라이브 영향 0.
//   GM 활성화: ① ScriptProperties ACCESS_TOKEN=<강한 무작위 문자열> ② PII_MASK='on' ③ 웹앱 새 버전 재배포.
//   직원 화면 '전체보기'에 토큰 1회 입력(localStorage wp_access_token → ?key=). 미입력/불일치=마스킹.
//   즉시 역롤백: PII_MASK 속성 삭제 → 다음 호출부터 전체 풀 복귀(재배포 불필요).
function _piiFull_(key) {
  if (String(_accessProp_('PII_MASK') || '').trim().toLowerCase() !== 'on') return true;  // OFF(기본)=현행 풀(무중단)
  var tok = String(_accessProp_('ACCESS_TOKEN') || '').trim();
  if (!tok) return false;                               // PII_MASK on·토큰 미설정 = 전부 마스킹(누수 차단). 토큰 설정 후 직원 전체보기.
  return String(key || '') === tok;                     // 토큰 일치 시에만 풀
}
function _svMaskName_(n) {
  n = String(n == null ? '' : n).trim(); if (!n) return '';
  return n.length <= 1 ? n : n.charAt(0) + Array(n.length).join('*');
}
function _svMaskPhone_(p) {
  var d = String(p == null ? '' : p).replace(/[^0-9]/g, '');
  return d.length >= 10 ? d.slice(0,3) + '-****-' + d.slice(-4) : (d ? '***' : '');
}

// ═══════════════════════════════════════════
//  문의회원 페이지 전용 — '26년 신규문의' 익명 읽기 (CPO cpo/member/membership.html)
//  ★ A안(2026-06-22 GM go): 이름·전화·메모 완전 제거(빈값) → 공개 페이지 안전, PII_GATE 불필요.
//     실명 표시·편집(CRUD)은 별도 접근통제(B안) 후속. 기존 inquiry_list(대시보드 집계)와 무관.
// ═══════════════════════════════════════════
var _MI_SS_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
var _MI_SHEET = '26년 신규문의';
var _MI_GID_EN = 1887747109;   // 멤버십(영문) 응답탭 — 영어 문의가 별도 탭에 쌓여 CRM에서 누락되던 누수 수리(2026-07-09 시포·GM)
// ★소프트 삭제 마커(2026-08-05 시토, GM 지시 — 새 문의 중복 삭제) — INC-020(행번호 밀림으로 실고객 오삭제) 재발방지로
//   물리적 deleteRow 를 구조적으로 막는다. 대신 진행현황(상태) 칸에 이 값만 쓰고 행은 그대로 남긴다.
//   기존 STATUS_OPTIONS(미정/컨택중/가망/SUC/단기SUC/LOSS) 6종과 겹치지 않는 새 값 1개만 추가(약속 L21 — 새 칸·새 시트는 안 만든다).
//   이 값을 읽는 모든 소비처(member_inquiry_list·inquiry_stats·member_calendar·cpo_today_stats·stage_funnel·
//   period_breakdown regByType 멤버십)가 목록·집계에서 제외해야 '삭제'가 실제로 안 보인다 — 4개 지점에서 검사(아래 grep 참조).
var MI_DUP_DELETED_STATUS = '중복(삭제)';
function _miSheet_() { return SpreadsheetApp.openById(_MI_SS_ID).getSheetByName(_MI_SHEET); }
// 영문 응답탭 은퇴(GM 2026-07-23) — 탭이 삭제돼도 null 을 돌려 조용히 건너뛴다(호출부는 전부 try/catch·null 가드).
//   영어 문의는 한글 탭에 '유입언어'·[영어] 표식으로 함께 쌓이므로 읽을 곳이 사라지는 게 아니다.
//   재개 시 = _MI_GID_EN 을 새 응답탭 gid 로 바꾸면 그대로 되살아난다.
function _miSheetEn_() { try { return _MI_GID_EN ? _sheetByGid_(_MI_SS_ID, _MI_GID_EN) : null; } catch (e) { return null; } }
// gid 명시(영문 탭 gid) 시 그 물리 시트로 라우팅. 없으면 rowIndex의 오프셋 여부(_ROW_OFFSET_EN_)로 자동 판별 —
//   목록에서 병합된 영문 행을 다시 저장할 때 정확한 탭에 기록. 둘 다 없으면 하위호환(기존 한글 '26년 신규문의' 탭). 2026-07-09 시포·GM.
function _miResolveSheet_(gid, rowIndex) {
  var g = parseInt(gid || '', 10);
  var isEn = (g === _MI_GID_EN) || (!g && parseInt(rowIndex || 0, 10) >= _ROW_OFFSET_EN_);
  if (isEn) { var s = _miSheetEn_(); if (s) return s; }
  return _miSheet_();
}
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
function _todayKR_() { return Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd'); }
// 웹 자동접수(intake_submit) 날짜·시각 → 기존 수기 444건과 동일한 표기로 통일(2026-07-20 시포).
//   '26년 신규문의' 탭은 A열(날짜)='yy. M. d' / B열(타임스탬프)='yyyy. M. d 오전/오후 h:mm:ss' 두 칸이 별도로 존재.
//   기존엔 한 번의 _imSet(['타임스탬프','접수일','날짜'], ISO문자열)만 호출해 _miColIdx_ 우선탐색으로 B(타임스탬프)만
//   채워지고 A(날짜)는 미기재 → 스프레드시트 자동서식/수식이 그 자리를 엉뚱한 포맷(예 '26-07-18')으로 채우던 문제.
//   Utilities.formatDate의 'a' 토큰은 로케일 무관 항상 영문 AM/PM만 반환(GAS 제약)이라 오전/오후는 직접 조립한다.
function _korDateOnly_(d) {
  var tz = 'Asia/Seoul';
  return Utilities.formatDate(d, tz, 'yy') + '. ' + parseInt(Utilities.formatDate(d, tz, 'M'), 10) + '. ' + parseInt(Utilities.formatDate(d, tz, 'd'), 10);
}
function _korDateTime_(d) {
  var tz = 'Asia/Seoul';
  var h24 = parseInt(Utilities.formatDate(d, tz, 'H'), 10);
  var ap = h24 < 12 ? '오전' : '오후';
  var h12 = h24 % 12; if (h12 === 0) h12 = 12;
  return Utilities.formatDate(d, tz, 'yyyy') + '. ' + parseInt(Utilities.formatDate(d, tz, 'M'), 10) + '. ' + parseInt(Utilities.formatDate(d, tz, 'd'), 10)
    + ' ' + ap + ' ' + h12 + ':' + Utilities.formatDate(d, tz, 'mm') + ':' + Utilities.formatDate(d, tz, 'ss');
}
// 날짜 전용 칸(시설투어희망일 등)에 시각이 섞여 들어오는 걸 방어 — 'YYYY-MM-DD' 접두만 남기고 절단.
//   intake_submit 클라이언트 필드(exp1Date 등)는 <input type=date>라 원래 시각이 없어야 하나,
//   실측(2026-07-20 라이브 447행 점검)에 시각 혼입 사례가 있어 서버측에서도 한 번 더 자른다.
function _dateOnlyStrip_(v) {
  var s = String(v == null ? '' : v).trim();
  var m = s.match(/^\d{4}-\d{2}-\d{2}/);
  return m ? m[0] : s;
}
// 헤더에 name 칸이 없으면 맨 끝에 새 칸으로 생성(비파괴·멱등) 후 0-based 인덱스 반환. 2026-06-29 시포(방문완료일).
function _miEnsureCol_(sh, hdr, name) {
  var ci = _miColIdx_(hdr, [name]);
  if (ci >= 0) return ci;
  var newCol = hdr.length + 1;
  sh.getRange(1, newCol).setValue(name);
  hdr.push(name);
  return newCol - 1;
}
// ★휴회 판별 함수 철회(2026-07-20 GM) — 휴회는 별도 전용 시트에서 관리 중.
//   유효회원 시트의 '휴회 종료일'을 읽던 이 함수는 잘못된 출처를 가리켜 항상 '휴회 아님'을 반환했다.
//   남겨두면 다음 사람이 "휴회는 유효회원 시트에 있다"고 오인한다 → 삭제.
//   연동은 휴회 시트 직독 방식으로 별도 설계(업무규칙: 3회 / 최소 7일 ~ 최대 60일).
// 전화번호 표시 정규화 — 시트가 '01034761531'을 숫자로 저장해 앞 0이 떨어진 '1034761531'로 보이는 문제 교정.
//   무조건 '010-3476-1531' 형식. 판단 불가(자릿수 안 맞음)면 원문 보존(손실 금지). 2026-06-26 시포·GM.
function _fmtPhone_(v) {
  var src = String(v == null ? '' : v);
  var digits = src.replace(/\D/g, '');
  if (!digits) return '';
  if (digits.length === 10 && digits.slice(0, 2) === '10') digits = '0' + digits;   // 앞 0 떨어진 휴대폰 복원
  if (digits.length === 11) return digits.slice(0, 3) + '-' + digits.slice(3, 7) + '-' + digits.slice(7);
  if (digits.length === 10) {
    if (digits.slice(0, 2) === '02') return '02-' + digits.slice(2, 6) + '-' + digits.slice(6);  // 02 지역
    return digits.slice(0, 3) + '-' + digits.slice(3, 6) + '-' + digits.slice(6);                 // 그 외 3-3-4
  }
  if (digits.length === 9 && digits.slice(0, 2) === '02') return '02-' + digits.slice(2, 5) + '-' + digits.slice(5);
  return src;  // 판단 불가 → 원문 그대로
}
// 연락기록(Contact)은 자유 텍스트 — '전화처럼 보일 때만'(숫자·하이픈·괄호·공백뿐) 정규화, 아니면 원문 보존.
function _fmtContact_(v) {
  var s = String(v == null ? '' : v);
  if (s.trim() && /^[\d\s\-+().]+$/.test(s.trim())) return _fmtPhone_(s);
  return s;
}
function _fmtPhoneOrUndef_(v)   { return (v === undefined || v === null) ? v : _fmtPhone_(v); }
function _fmtContactOrUndef_(v) { return (v === undefined || v === null) ? v : _fmtContact_(v); }
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
// 접수 타임스탬프 전용 직렬화 — 시각을 살려서 내보낸다. 2026-07-20 시포(GM 지적).
//   _miToISO_는 날짜만 반환한다(YYYY-MM-DD). 그건 예약일·방문일·상담일처럼 '날짜만' 의미 있는 칸엔 맞지만,
//   접수 타임스탬프에 쓰면 시트엔 07:03:25가 멀쩡히 있는데 화면엔 날짜만 뜬다 — 실제로 627건 전부 그랬다.
//   화면 _fmtInqDateTime(membership.html)은 'YYYY-MM-DD HH:MM' 형태를 받으면 시:분을 표시하도록 이미 돼 있다.
//   ★_miToISO_ 자체는 건드리지 않는다 — 호출부 11곳 중 대부분이 날짜 전용 칸이라 바꾸면 그쪽이 깨진다.
//   자정(00:00:00)은 '시각 미상'이라 날짜만 반환(원유선 건처럼 근거 없이 00:00이 찍힌 행을 시각처럼 보이지 않게).
function _miToISOTime_(val) {
  if (!val) return '';
  if (val instanceof Date && !isNaN(val.getTime())) {
    var p = function (n) { return ('0' + n).slice(-2); };
    var base = val.getFullYear() + '-' + p(val.getMonth() + 1) + '-' + p(val.getDate());
    var h = val.getHours(), mi = val.getMinutes(), s = val.getSeconds();
    return (h || mi || s) ? (base + ' ' + p(h) + ':' + p(mi) + ':' + p(s)) : base;
  }
  var t = String(val).trim();
  var mt = t.match(/(\d{4})[.\-\/]\s*(\d{1,2})[.\-\/]\s*(\d{1,2})[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (mt) {
    var pp = function (n) { return ('0' + n).slice(-2); };
    return mt[1] + '-' + pp(mt[2]) + '-' + pp(mt[3]) + ' ' + pp(mt[4]) + ':' + mt[5] + ':' + (mt[6] || '00');
  }
  return _miToISO_(val);   // 시각 없는 값은 기존 동작 그대로
}
// ★예약 4슬롯 헬퍼 — 신·구 형식 동시 지원 (2026-07-20 GM 지시)
//   구 형식: G=날짜 / H=시간 / I=날짜 / J=시간  → 두 칸이 예약 1건, 최대 2건
//   신 형식: G·H·I·J 각각 '2026-07-08 12:00'  → 한 칸이 예약 1건, 최대 4건
//   판별은 '값'이 아니라 'H칸 제목'으로 한다 — 값으로 판별하면 시간이 아직 안 잡힌 행에서 오판한다.
//   (G는 구글폼 문항이라 제목을 못 바꾸지만 H·I·J는 우리 칸이라 이관 때 '예약2/3/4'로 바꾼다)
function _miIsSlotFormat_(hdr, iExp1) {
  if (iExp1 < 0) return false;
  var h = String(hdr[iExp1] || '').replace(/\s+/g, '');
  return h === '예약2';
}
function _miSlotPair_(hdr, row, iTour, iExp1, iV2Dt, iExp2, n) {
  var cells = [iTour >= 0 ? row[iTour] : '', iExp1 >= 0 ? row[iExp1] : '',
               iV2Dt >= 0 ? row[iV2Dt] : '', iExp2 >= 0 ? row[iExp2] : ''];
  if (_miIsSlotFormat_(hdr, iExp1)) {
    var v = cells[n];
    return { date: _miToISO_(v), time: _miTime_(v) };
  }
  if (n === 0) return { date: _miToISO_(cells[0]) || _miToISO_(cells[1]), time: _miTime_(cells[1]) };
  if (n === 1) return { date: _miToISO_(cells[2]) || _miToISO_(cells[3]), time: _miTime_(cells[3]) };
  return { date: '', time: '' };
}
function _miSlotDate_(hdr, row, a, b, c, d, n) { return _miSlotPair_(hdr, row, a, b, c, d, n).date; }
function _miSlotTime_(hdr, row, a, b, c, d, n) { return _miSlotPair_(hdr, row, a, b, c, d, n).time; }
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
// 자유 텍스트(확정시간 칸)에서 한글 시각 추출 — 달력 표시 전용. '11시 등록상담'·'3시30분'·'오후4시'·'2시반'·'14시'·'오후 2:30' 인식.
//   추측 금지: 오전/오후 표기는 쓴 그대로 보존, 맨시각(N시)도 24h 변환 없이 그대로 노출. '미정'·시각 없는 메모는 '' 반환.
function _miTimeKR_(val) {
  if (!val) return '';
  var s = String(val);
  // 1) 한글 시각: (오전|오후)? N시 (M분|반)?
  var km = s.match(/(오전|오후)?\s*(\d{1,2})\s*시\s*(반|\d{1,2}\s*분)?/);
  if (km) {
    var ap = km[1] ? km[1] + ' ' : '';
    var mn = '';
    if (km[3]) mn = (km[3].indexOf('반') >= 0) ? '30분' : km[3].replace(/\s/g, '');
    return ap + km[2] + '시' + mn;
  }
  // 2) HH:MM (오전/오후 접두 포함)
  var hm = s.match(/(오전|오후)?\s*(\d{1,2}):(\d{2})/);
  if (hm) {
    var ap2 = hm[1] ? hm[1] + ' ' : '';
    return ap2 + ('0'+hm[2]).slice(-2) + ':' + hm[3];
  }
  return '';
}
// 시간 표시 텍스트 → 정렬용 분(0~1439 정수). 시간 없음/미정 → null. (달력 시간순 정렬 전용 · 2026-06-26)
//   '오전 N시'→N*60(오전 12시=0) · '오후 N시'→(12시=그대로/그외 +12)*60 · 'N시M분'·'N시반' 분 반영 ·
//   'HH:MM'(오전/오후 접두 포함) · 접두 없는 맨 'N시'·'HH:MM'→있는 그대로 환산. 추측 없이 표기 그대로.
function _miTminKR_(val) {
  if (!val) return null;
  var s = String(val).trim();
  if (!s) return null;
  // 1) 한글 시각: (오전|오후)? N시 (반|M분)?
  var km = s.match(/(오전|오후)?\s*(\d{1,2})\s*시\s*(반|\d{1,2}\s*분)?/);
  if (km) {
    var h = parseInt(km[2], 10);
    var ap = km[1] || '';
    var mn = 0;
    if (km[3]) mn = (km[3].indexOf('반') >= 0) ? 30 : (parseInt(km[3].replace(/[^0-9]/g, ''), 10) || 0);
    if (ap === '오전') { if (h === 12) h = 0; }
    else if (ap === '오후') { if (h !== 12) h += 12; }
    var t = h * 60 + mn;
    return (t >= 0 && t <= 1439) ? t : null;
  }
  // 2) HH:MM (오전/오후 접두 포함)
  var hm = s.match(/(오전|오후)?\s*(\d{1,2}):(\d{2})/);
  if (hm) {
    var h2 = parseInt(hm[2], 10), m2 = parseInt(hm[3], 10);
    var ap2 = hm[1] || '';
    if (ap2 === '오전') { if (h2 === 12) h2 = 0; }
    else if (ap2 === '오후') { if (h2 !== 12) h2 += 12; }
    var t2 = h2 * 60 + m2;
    return (t2 >= 0 && t2 <= 1439) ? t2 : null;
  }
  return null;
}
// ═══ 예약 리스트(가변 · 날짜+시간+내용 한 셀) — 문의현황/유효회원 공용. 2026-07-03 시포·GM ═══
//  저장 모델: JSON 배열 [{date:'YYYY-MM-DD', time:'HH:MM', note:'...'}]. 컬럼=문의 '예약목록' / 유효회원 '재등록예약목록'.
//  하위호환(비파괴): JSON 없으면 기존 체험1·2(J/K/L/M) / 재등록 단일 3칸을 예약1·2로 흡수해 읽는다. 저장 시 JSON + 기존칸 미러 동기화.
var INQ_RES_COL = '예약목록';
var ACT_RES_COL = '재등록예약목록';
// ═══ 연락 이력(가변 · 날짜+시간+상담내용 리스트) — 멤버십 문의회원 CONTACT. 2026-07-08 시포·GM(축2) ═══
//  저장 모델: 예약목록과 동일 스키마([{date,time,note}]) → _resParse_/_resStringify_ 재사용. 컬럼='연락이력'(멱등 생성).
//  하위호환(비파괴): '연락이력'이 비어 있고 옛 Contact1/2/3에 값이 있으면 각각 {date:'',time:'',note:Cn}으로 합성해 표시.
//  Contact1/2/3 컬럼은 절대 삭제·덮어쓰지 않음(원복 안전) — '연락이력'이 있으면 그것을 우선 사용.
var CONTACT_HIST_COL = '연락이력';
// ═══ 1차 컨택 알림 — 발신 기록(멱등 가드) — 2026-07-29 시토 · GM 재지적(배10379) ═══
//  세는 값(_muHistPrevCount===0)만으로는 동시 저장 두 요청이 같은 순간에 나란히 0을 읽어 둘 다 보내는
//  레이스를 못 막는다(실측: 같은 분에 2회 재발). '보낸 기록' 자체를 이 칸에 남기고, 다음 요청은 그 표시를
//  보고 건너뛴다 — 세는 로직이 다시 틀려도 이 표시가 최후 방어선(약속 L21: 관문 하나에만 박는다).
var FIRST_CONTACT_SENT_COL = '1차컨택알림발송';
// ═══ 컨택자(컨택한 사람) 구조화 — 배101(2026-07-25 시포·GM) ═══
//  '누가 컨택했는지'를 메모 끝 수기 서명(-이름) 대신 구조화 필드(by)로 기록한다.
//  시트 저장 = 사람이 읽는 평문 유지(GM: 시트 JSON 금지) — 노트 끝 '(컨택:이름)' 마커 한 가지.
//  읽기 = 마커를 by 로 분리(note 에서는 마커 제거). 과거분 소급 복원 불가 — 컨택자 집계 기준선 = 2026-07-25.
var CONTACT_BY_RE = /\s*\(컨택:([^()]*)\)\s*$/;
function _ctBySplit_(note) {
  var s = String(note == null ? '' : note);
  var m = s.match(CONTACT_BY_RE);
  if (!m) return { note: s, by: '' };
  return { note: s.replace(CONTACT_BY_RE, '').trim(), by: m[1].trim() };
}
function _ctByJoin_(note, by) {
  var n = String(note == null ? '' : note).trim();
  var b = String(by == null ? '' : by).trim();
  return b ? (n ? n + ' (컨택:' + b + ')' : '(컨택:' + b + ')') : n;
}
// 셀/배열/JSON 문자열 → 정규 예약 배열([{date,time,note}]). 완전 빈 항목 제거.
function _resParse_(raw) {
  if (!raw) return [];
  var arr;
  if (Array.isArray(raw)) { arr = raw; }
  else {
    var s = String(raw).trim();
    if (!s || s.charAt(0) !== '[') return [];
    try { arr = JSON.parse(s); } catch (e) { return []; }
  }
  if (!Array.isArray(arr)) return [];
  var out = [];
  for (var i = 0; i < arr.length; i++) {
    var it = arr[i] || {};
    var d = _miToISO_(it.date || '');
    var t = _miTime_(it.time || '') || (it.time ? String(it.time).trim() : '');
    var n = (it.note == null) ? '' : String(it.note);
    // 컨택자(by, 배101): 필드 우선, 없으면 노트 끝 '(컨택:이름)' 마커 흡수(레거시 JSON·수기 호환).
    var _bs = _ctBySplit_(n);
    var b = String(it.by == null ? '' : it.by).trim() || _bs.by;
    n = _bs.note;
    if (!d && !t && !n && !b) continue;
    out.push({ date: d, time: t, note: n, by: b });
  }
  return out;
}
// 예약 배열 → JSON 문자열(빈 배열이면 '' → 셀 클리어).
function _resStringify_(arr) {
  var clean = [];
  (arr || []).forEach(function(it){
    if (!it) return;
    var d = _miToISO_(it.date || '');
    var t = it.time ? String(it.time).trim() : '';
    var n = (it.note == null) ? '' : String(it.note);
    var b = String(it.by == null ? '' : it.by).trim();   // 컨택자(배101) — 있을 때만 키 포함(예약 등 무관 소비자 무영향)
    if (!d && !t && !n && !b) return;
    var o = { date: d, time: t, note: n };
    if (b) o.by = b;
    clean.push(o);
  });
  return clean.length ? JSON.stringify(clean) : '';
}
// ═══ 예약목록 평문 저장(JSON→평문) — 2026-07-22 GM(시트 가독성). 강습 Contact 평문(_lessonContactPlain*)과 동일 규칙·로직 재사용(별도 정의 대신 위임 — net-zero). ═══
//  저장 포맷: 줄바꿈 구분 평문, 한 줄="YYYY-MM-DD HH:MM 노트"(빈 날짜/시간 생략). 읽기(_resCellParse_)는 양포맷 — 레거시 JSON'['·신규 평문·손상 JSON(원문 note 보존).
//  프론트↔백엔드 계약(reservations 배열/JSON 문자열 송수신)은 불변 — 시트 저장 포맷만 전환. rowKey/keyPhone 행지목 로직과 무관.
function _resPlainStringify_(arr) { return _lessonContactPlainStringify_(arr); }
function _resPlainParse_(raw)     { return _lessonContactPlainParse_(raw); }
function _resCellParse_(raw)      { return _lessonContactCellParse_(raw); }

// 익명 행 배열 반환(이름·전화·메모 비움). 빈 행 스킵.
// sh 생략 시 하위호환(기존 한글 '26년 신규문의' 탭). 명시 시 그 시트를 그대로 읽는다(영문 탭 병합용). 2026-07-09 시포·GM.
function _miReadRows_(sh) {
  if (sh === undefined) sh = _miSheet_();  // 인자 미전달(레거시 호출)만 기본 한글 탭 폴백 — 명시적 null(영문 탭 미발견)은 그대로 빈 배열 반환(중복 병합 방지)
  if (!sh) return [];
  var gid = sh.getSheetId();
  var hdr = _miHeaders_(sh);
  var last = sh.getLastRow();
  var out = [];
  if (last < 2) return out;
  var data = sh.getRange(2, 1, last - 1, hdr.length).getValues();
  // ★영문 멤버십탭 헤더 별칭(2026-07-09 시포·GM, 영어 문의 누수 수리) — 실측(멤버십 영문 응답탭 gviz) 기준.
  var iName  = _miColIdx_(hdr, ['성함','이름','Full Name']);  // '성함' 우선 — '이름'이 '접수 담당자 혹은 본인 이름' 칸을 먼저 잡던 버그 차단(2026-06-24)
  var iPhone = _miColIdx_(hdr, ['연락처','전화','휴대폰','Mobile Phone Number']);
  var iProg  = _miColIdx_(hdr, ['관심 있는 프로그램 종류','관심프로그램','프로그램','Programs of Interest']);
  var iStat  = _miColIdx_(hdr, ['진행현황','진행상황','진행상태','상태']);
  var iTs    = _miColIdx_(hdr, ['타임스탬프','접수일','날짜']);
  var iTour  = _miColIdx_(hdr, ['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담']);
  // ★4슬롯 이관(2026-07-20 GM) — 신 제목 '예약2/3/4'를 앞에 둬 정확일치로 먼저 잡는다. 옛 이름은 하위호환으로 유지.
  var iExp1  = _miColIdx_(hdr, ['예약2','체험1 확정시간','체험1']);
  var iExp2  = _miColIdx_(hdr, ['예약4','체험2 확정시간','체험2']);
  var iExp3  = _miColIdx_(hdr, ['체험3 확정시간','체험3']);
  var iV2Dt  = _miColIdx_(hdr, ['예약3','시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2']);  // 2차 방문 날짜(달력 보강용·확정시간 칸과 별개)
  var iVisited = _miColIdx_(hdr, ['방문완료일','방문완료','방문일자']);  // 방문 완료(진행상황과 독립 — 등록돼도 방문 기록 유지). 2026-06-29 시포
  var iRegProgram = _miColIdx_(hdr, ['등록종목']);      // 등록(SUC) 시 실제 등록한 종목 — 문의 시 관심프로그램(iProg)과 별개, 수정 가능. 2026-07-18 시토(GM요청) 대행.
  // ★'미등록 사유'(기존 칸)를 폴백으로 추가(2026-07-20 GM 지적) — LOSS사유 칸을 새로 만든 것이 착오였고,
  //   같은 뜻의 '미등록 사유'가 원래 있었다. LOSS사유 칸이 남아 있으면 그것을 먼저(하위호환), 없으면 미등록 사유를 읽는다.
  var iLossReason = _miColIdx_(hdr, ['LOSS사유', '미등록 사유', '미등록사유']);
  var iLossReasonNote = _miColIdx_(hdr, ['LOSS사유메모']);
  var iOwner = _miColIdx_(hdr, ['담당','담당자']);
  var iMemo  = _miColIdx_(hdr, ['메모','비고','담당자메모']);
  var _CHAN_KEYS = ['문의채널','유입채널','채널','경로','알게','How Did You Hear About Us?'];  // 대분류 — 3단 우선순위(중분류→자동UTM override)는 _resolveInquiryChannelRaw_ 공용 SSOT 사용(2026-07-20, M1과 동일 규칙)
  var iContent = _miColIdx_(hdr, ['기타 웰페리온에 대한 문의 사항','기타 웰페리온','자유롭게 적어','문의 사항','문의사항','Health & Wellness Goals']);  // N열 자유서술 문의내용(#1). 2026-07-02 시포·GM
  var iRes  = _miColIdx_(hdr, [INQ_RES_COL]);  // 예약목록(JSON) — 가변 예약. 없으면 체험1·2 흡수. 2026-07-03 시포·GM
  // 연락기록 3칸 — Contact1·Contact2·Contact3 헤더 이름 탐색만 사용(위치 폴백 17/18/19 제거, 2026-07-20 시포).
  //   실측: 정답 위치는 16/17/18(Contact1=Q·Contact2=R·Contact3=S)인데 폴백이 한 칸씩 밀려 있어 Contact3→진행현황(T) 오염 잠복 지뢰였음.
  //   현재 헤더는 이름 탐색이 항상 성공(gviz 실측 검증) — 못 찾을 때만 로그 남기고 -1 유지(아래 소비처가 빈 값으로 안전 처리, 엉뚱한 칸 오염 없음).
  var iC1 = _miColIdx_(hdr, ['Contact1']); if (iC1 < 0) Logger.log('_miReadRows_: Contact1 칸 못찾음(헤더 확인 필요)');
  var iC2 = _miColIdx_(hdr, ['Contact2']); if (iC2 < 0) Logger.log('_miReadRows_: Contact2 칸 못찾음(헤더 확인 필요)');
  var iC3 = _miColIdx_(hdr, ['Contact3']); if (iC3 < 0) Logger.log('_miReadRows_: Contact3 칸 못찾음(헤더 확인 필요)');
  var iHist = _miColIdx_(hdr, [CONTACT_HIST_COL]);  // 연락이력(JSON) — 가변 컨택 이력. 2026-07-08 시포·GM(축2)
  var iLang = _miColIdx_(hdr, ['Preferred Language','Language']);  // 응답자 기재 언어(영문 탭 실측 헤더) — 영어 문의 뱃지 표시용. 2026-07-09 시포·GM
  // 영문 탭 행키 오프셋(_ROW_OFFSET_EN_) — 한글+영문 병합 시 rowIndex 충돌 방지(정의부 주석 참고). 2026-07-09 시포·GM.
  var rowOffset = (gid === _MI_GID_EN) ? _ROW_OFFSET_EN_ : 0;
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var hasName  = iName  >= 0 && row[iName];
    var hasPhone = iPhone >= 0 && row[iPhone];
    if (!hasName && !hasPhone) continue; // 완전 빈 행 스킵
    // ★소프트 삭제(중복) 제외 — 단일 공유 리더라 member_inquiry_list·inquiry_stats·member_calendar 3곳이 여기서 한 번에 걸린다.
    if (iStat >= 0 && String(row[iStat] || '').trim() === MI_DUP_DELETED_STATUS) continue;
    var _mo = {
      rowIndex: r + 2 + rowOffset,
      name:     iName  >= 0 ? String(row[iName]  || '') : '',  // 2026-06-22 GM '전체 공개' — 실명 노출
      phone:    iPhone >= 0 ? _fmtPhone_(row[iPhone]) : '',    // 연락처 노출 + 표시 정규화(앞 0 복원·하이픈)
      program:  iProg  >= 0 ? _normMembershipProgram_(String(row[iProg]  || '')) : '',
      status:   iStat  >= 0 ? String(row[iStat]  || '') : '',
      channel:  (function(){ var _cr = _resolveInquiryChannelRaw_(hdr, row, _CHAN_KEYS); return _cr ? _canonicalChannel_(_cr) : ''; })(),  // 유입채널 표준 10버킷(대분류→중분류→자동UTM 3단, M1과 동일 SSOT. 빈값은 빈값 유지)
      // ── 체험 일정 분리 저장(#4, 2026-07-02 시포·GM): 체험1 날짜=J(시설투어·상담 예약)/시간=K(체험1 확정시간), 체험2 날짜=L(시설 체험 예약2)/시간=M(체험2 확정시간).
      //    상담=체험1(동일 1차 방문). 하위호환: 분리 날짜칸(J/L)이 비면 옛 결합칸(K/M)의 날짜부로 폴백 → 무손실.
      // ★신·구 형식 동시 지원(2026-07-20 GM) — 예약을 '날짜 시간' 한 칸씩 4슬롯(G·H·I·J)으로 바꾸는 중이다.
      //   구 형식: G=날짜 / H=시간 / I=날짜 / J=시간  (두 칸이 예약 1건)
      //   신 형식: G·H·I·J 각각 '2026-07-08 12:00'   (한 칸이 예약 1건 → 최대 4건)
      //   판별: 첫 칸(G)에 시각 성분이 있으면 신 형식으로 본다. 데이터 이관 전후 어느 상태에서도 화면이 안 깨진다.
      //   ※ exp1/exp1Time/exp2/exp2Time 필드명은 그대로 유지 — 화면이 이 이름으로 읽고 있어 계약을 안 깬다.
      exp1:     _miSlotDate_(hdr, row, iTour, iExp1, iV2Dt, iExp2, 0),
      exp1Time: _miSlotTime_(hdr, row, iTour, iExp1, iV2Dt, iExp2, 0),
      exp2:     _miSlotDate_(hdr, row, iTour, iExp1, iV2Dt, iExp2, 1),
      exp2Time: _miSlotTime_(hdr, row, iTour, iExp1, iV2Dt, iExp2, 1),
      inquiryContent: iContent >= 0 ? String(row[iContent] || '') : '',   // 문의 내용(N열 자유서술) — #1
      // 하위호환 유지(옛 필드 — 미사용, 잔존 참조 안전용): 상담·체험3·2차방문은 체험1/2로 흡수
      tourDate: '', tourTime: '', exp3: '', exp3Time: '', visit2Date: '', visit2Time: '',
      visited:    (iVisited >= 0 && String(row[iVisited] == null ? '' : row[iVisited]).trim() !== '') ? true : false,  // 방문 완료 여부(독립·공백/0 오인 방지)
      visitDate:  (iVisited >= 0) ? _miToISO_(row[iVisited]) : '',  // 방문 완료일
      regProgram: iRegProgram >= 0 ? String(row[iRegProgram] || '') : '',      // 등록 종목(SUC 시 실제 등록한 종목). 2026-07-18 시토(GM요청) 대행.
      lossReason: iLossReason >= 0 ? String(row[iLossReason] || '') : '',      // LOSS 사유(문의 퍼널 전용).
      lossReasonNote: iLossReasonNote >= 0 ? String(row[iLossReasonNote] || '') : '',
      timestamp:_miToISOTime_(iTs >= 0 ? row[iTs] : ''),   // ★시각 보존(2026-07-20 GM) — _miToISO_는 날짜만 남겨 627건 전부 시분초가 잘렸었다
      memo:     iMemo  >= 0 ? String(row[iMemo]  || '') : '',
      owner:    iOwner >= 0 ? String(row[iOwner] || '') : '',
      contact1: (iC1 >= 0 && iC1 < row.length) ? _fmtContact_(row[iC1]) : '',
      contact2: (iC2 >= 0 && iC2 < row.length) ? _fmtContact_(row[iC2]) : '',
      contact3: (iC3 >= 0 && iC3 < row.length) ? _fmtContact_(row[iC3]) : '',
      // 출처 물리 시트 gid + 기재 언어 — 영문 탭 병합 표시·저장 라우팅용(row.gid 그대로 되돌려 보내면 정확한 탭에 기록). 2026-07-09 시포·GM.
      gid: gid,
      lang: iLang >= 0 ? String(row[iLang] || '').trim() : '',
      // 지문키(rowKey, §4 R1) — 정규화 타임스탬프+정규화 전화. raw 셀 값(_normTsKey_ 입력)을 그대로 써야 함
      //   (위 timestamp 필드는 _miToISO_로 시각이 잘려있어 지문 재료로 쓰면 안 됨). 둘 중 하나라도 없으면 ''(지문키 미사용 → 프론트가 keyPhone 폴백). 2026-07-22 시포.
      rowKey: (function(){ var _t = _normTsKey_(iTs >= 0 ? row[iTs] : ''), _p = _normPhone_(iPhone >= 0 ? row[iPhone] : ''), _n = _normNameKey_(iName >= 0 ? row[iName] : ''); /* 이름은 세 번째 파트로 붙인다(배491) — 없으면 두 파트 그대로라 옛 화면과 호환된다. */ return (_t && _p) ? (_t + '|' + _p + (_n ? '|' + _n : '')) : ''; })()
    };
    // 예약목록(가변): 양포맷(레거시 JSON·신규 평문) → 없으면 체험1·2 흡수(하위호환·무손실). 2026-07-03 시포·GM / 2026-07-22 GM(평문 전환)
    var _resArr = _resCellParse_(iRes >= 0 ? row[iRes] : '');
    if (!_resArr.length) {
      if (_mo.exp1) _resArr.push({ date: _mo.exp1, time: _mo.exp1Time || '', note: '' });
      if (_mo.exp2) _resArr.push({ date: _mo.exp2, time: _mo.exp2Time || '', note: '' });
    }
    _mo.reservations = _resArr;
    // ★읽는 순서 정정(2026-07-20 GM 지적) — Contact1/2/3(O·P·Q)가 정본, 연락이력은 4건째부터의 넘침분.
    //   기존엔 연락이력을 우선 읽고 없을 때만 Contact를 흡수했다. 그래서 새 칸이 정본처럼 굳어졌다.
    //   이제 Contact1/2/3을 먼저 싣고, 연락이력에 남은 것(넘침분)을 뒤에 붙인다.
    //   과거 데이터 호환: 연락이력에만 있고 Contact가 빈 옛 행(실측 17건)도 그대로 다 보인다.
    var _histArr = [];
    [_mo.contact1, _mo.contact2, _mo.contact3].forEach(function(cv){
      if (!cv) return;
      var _cbs = _ctBySplit_(cv);   // 컨택자(배101): 셀 끝 '(컨택:이름)' → by 분리
      _histArr.push({ date: '', time: '', note: _cbs.note, by: _cbs.by });
    });
    var _histOverflow = _resParse_(iHist >= 0 ? row[iHist] : '');
    if (_histOverflow.length) {
      // 중복 방지: 넘침분에 Contact와 같은 내용이 들어있는 옛 행(합성 저장분)은 한 번만 싣는다.
      var _seenNotes = {};
      _histArr.forEach(function(e){ _seenNotes[String(e.note || '').trim()] = 1; });
      _histOverflow.forEach(function(e){
        var k = String(e.note || '').trim();
        if (k && _seenNotes[k]) return;
        _histArr.push(e);
      });
    }
    _mo.contacts = _histArr;
    out.push(_mo);
  }
  return out;
}

// ═══════════════════════════════════════════
//  재등록 상담 이벤트(유효회원 시트) — 예약 달력 병합용. 2026-07-03 시포·GM.
//  유효회원 시트 '재등록상담 날짜/시간/내용' 칸이 채워진 회원을 달력 이벤트로 반환.
//  칸 미신설(헤더 없음)이면 [] 반환 → 기존 신규 이벤트 무손상. rowIndex=member_active_update 저장 대상.
// ═══════════════════════════════════════════
function _memberReconEvents_(month) {
  var sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  if (!sh) return [];
  var last = sh.getLastRow(), cols = sh.getLastColumn();
  if (last < 2 || cols < 1) return [];
  var hdr = sh.getRange(1, 1, 1, cols).getValues()[0].map(function(v){ return String(v).trim(); });
  function idx(want){ var w = String(want).replace(/\s/g, ''); for (var i = 0; i < hdr.length; i++){ if (hdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; } return -1; }
  var iRes  = idx('재등록예약목록');
  var iDate = idx('재등록상담날짜');
  if (iRes < 0 && iDate < 0) return [];   // 재등록 예약 칸 전무(JSON·단일 모두 없음) → 이벤트 없음(무손상)
  var iTime = idx('재등록상담시간');
  var iNote = idx('재등록상담내용');
  var iName = idx('회원명');
  var iProg = idx('회원구분');
  var iPhone = -1;
  for (var p = 0; p < hdr.length; p++){ var ph = hdr[p].replace(/\s/g, ''); if (ph.indexOf('휴대폰') >= 0 || ph.indexOf('전화') >= 0 || ph.indexOf('연락처') >= 0){ iPhone = p; break; } }
  // 지문키(rowKey) 재료 — member_active_update 가드와 동일 재료(등록일자+전화)로 정합. 2026-07-22 시포.
  var iTsRk = idx('등록일자'); if (iTsRk < 0) iTsRk = idx('타임스탬프');
  var data = sh.getRange(2, 1, last - 1, cols).getValues();
  var out = [];
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    // 예약목록(JSON) 우선 → 없으면 단일 재등록상담 3칸 흡수(하위호환·무손실). 2026-07-03 시포·GM
    var resArr = _resParse_(iRes >= 0 ? row[iRes] : '');
    if (!resArr.length && iDate >= 0) {
      var dISO0 = _miToISO_(row[iDate]);
      if (dISO0) {
        var tRaw0 = iTime >= 0 ? row[iTime] : '';
        var tStr0 = _miTime_(tRaw0) || _miTimeKR_(tRaw0) || (tRaw0 ? String(tRaw0).trim() : '');
        resArr = [{ date: dISO0, time: tStr0, note: iNote >= 0 ? String(row[iNote] == null ? '' : row[iNote]) : '' }];
      }
    }
    if (!resArr.length) continue;
    var _nm = iName >= 0 ? String(row[iName] == null ? '' : row[iName]).trim() : '';
    var _ph = iPhone >= 0 ? _fmtPhone_(row[iPhone]) : '';
    var _pg = iProg >= 0 ? String(row[iProg] == null ? '' : row[iProg]).trim() : '';
    var _rkTsN = _normTsKey_(iTsRk >= 0 ? row[iTsRk] : ''), _rkPhN = _normPhone_(iPhone >= 0 ? row[iPhone] : '');
    var _rkNmN = _normNameKey_(iName >= 0 ? row[iName] : '');   // 이름 세 번째 파트(배491)
    var _rk = (_rkTsN && _rkPhN) ? (_rkTsN + '|' + _rkPhN + (_rkNmN ? '|' + _rkNmN : '')) : '';
    for (var ri = 0; ri < resArr.length; ri++) {
      var res = resArr[ri];
      if (!res.date) continue;                               // 날짜 없는 항목 스킵
      if (month && res.date.slice(0, 7) !== month) continue; // 표시 월 필터
      out.push({
        date: res.date, kind: '재등록상담', source: 'active', time: res.time || '', tmin: _miTminKR_(res.time), slot: (ri === 0 ? 'recon' : 'r' + ri), resIdx: ri,
        name: _nm, phone: _ph, program: _pg,
        status: '', rowIndex: r + 2, memo: res.note, note: res.note,
        owner: '', contact1: '', contact2: '', contact3: '', visited: false, visitDate: '',
        rowKey: _rk   // 2026-07-22 시포(오지목 근본수리 R1)
      });
    }
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
function _regUpsert_(name, phone, program, regDate) {
  var key = _regNormPhone_(phone);
  if (!key) return;
  var sh = _regSheet_();
  var last = sh.getLastRow();
  if (last >= 2) {
    var data = sh.getRange(2, 1, last - 1, 4).getValues();  // 이름·전화·프로그램·등록일
    for (var i = 0; i < data.length; i++) {
      if (_regNormPhone_(data[i][1]) === key) {
        if (name)    sh.getRange(i + 2, 1).setValue(name);
        if (program) sh.getRange(i + 2, 3).setValue(program);
        if (regDate) sh.getRange(i + 2, 4).setValue(regDate);  // 등록일자 명시 시 갱신(GM 보정 가능)
        return;
      }
    }
  }
  var row = new Array(_REG_HEADER.length).fill('');
  row[0] = name || ''; row[1] = phone || ''; row[2] = program || ''; row[3] = regDate || _todayKR_();  // 등록일=지정값 우선, 없으면 오늘
  sh.appendRow(row);
}
// 등록 해제(잘못 등록 되돌리기) — 등록현황에서 전화키 매칭 행 제거. 2026-06-29 시포.
//   ★2026-08-05 시토(GM 지시) — "중복 있으면 전부" 지우던 것을 거부로 바꿨다. 전화 공유(가족·유소년)면
//   무관한 등록건까지 같이 지워질 위험이 있다 — 인라인 편집 가드와 동일한 _countRowsByPhone_(148) 재사용.
//   반환값 추가: {ok:true} 삭제됨 / {ok:true,removed:0} 대상 없음(무손상) / {ok:false,...} 거부(호출부가 알려야 함).
//   ★2026-08-06 시토(배295) — 등록현황만 지우고 유효회원(화면이 실제로 읽는 시트)은 그대로 남아 "해제해도
//   화면에서 안 사라진다"는 짝 어긋남이 있었다. 지운 뒤 유효회원도 같은 전화키로 정리 시도(아래 함수, 그
//   행의 등록회차가 1일 때만 — 2회차 이상이면 이전 정상 등록 이력이 섞여 있어 지우지 않는다, INC-020 재발방지).
function _regRemove_(phone) {
  var key = _regNormPhone_(phone);
  if (!key) return { ok: true, removed: 0 };
  var sh = _regSheet_();
  var _rrDupN = _countRowsByPhone_(sh, 1, key);   // 등록현황 B열=전화(row[1]) → 0-based phCol=1
  if (_rrDupN >= 2) return { ok: false, error: 'phone-ambiguous', count: _rrDupN };
  var last = sh.getLastRow();
  var removed = 0;
  for (var i = last; i >= 2; i--) {
    if (_regNormPhone_(sh.getRange(i, 2).getValue()) === key) { sh.deleteRow(i); removed++; }
  }
  if (removed > 0) { try { _regActiveRemoveIfSole_(key); } catch (e) { Logger.log('_regActiveRemoveIfSole_ 예외: ' + e); } }
  return { ok: true, removed: removed };
}
// 유효회원(회원 DB)에서 같은 전화키 행을 지운다 — **그 행의 등록회차가 1(유일 등록)일 때만**. 2026-08-06 시토(배295).
//   0건=대상 없음(무손상) / 2건+=번호 공유 추정이라 손대지 않고 수동 확인 요청(_countRowsByPhone_·_findRowByPhone_
//   재사용, 인라인 편집 가드와 같은 판정) / 등록회차 칸을 못 찾거나 2 이상이면 이전 등록 이력 보존을 위해 지우지
//   않고 알림만 보낸다 — 실제 회원 데이터는 확신 없이는 절대 지우지 않는다(INC-020 교훈).
function _regActiveRemoveIfSole_(normKey) {
  var sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  if (!sh) return;
  var cols = sh.getLastColumn();
  var hdr = sh.getRange(1, 1, 1, cols).getValues()[0].map(function (v) { return String(v).trim(); });
  function _idx(want) {
    var w = String(want).replace(/\s/g, '');
    for (var i = 0; i < hdr.length; i++) { if (hdr[i] && hdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; }
    return -1;
  }
  var phI = _idx('휴대폰'); if (phI < 0) phI = _idx('연락처'); if (phI < 0) phI = _idx('전화');
  var seqI = _idx('등록회차');
  if (phI < 0) return;
  var dupN = _countRowsByPhone_(sh, phI, normKey);
  if (dupN !== 1) return;   // 0건=없음(무손상) / 2건+=번호공유 추정, 손대지 않음(수동 확인)
  var row = _findRowByPhone_(sh, phI, normKey);
  if (row < 2) return;
  var seq = (seqI >= 0) ? parseInt(sh.getRange(row, seqI + 1).getValue(), 10) : NaN;
  if (seqI < 0 || !(seq === 1)) {
    try { _notifyTelegram('⚠️ 등록 해제 — 유효회원 시트는 그대로 두었습니다(등록회차 ' + (seqI < 0 ? '확인불가' : seq) + ', 이전 등록 이력 있음/불명). 필요하면 "유효회원" 시트에서 직접 확인해주세요.'); } catch (e) {}
    return;
  }
  sh.deleteRow(row);
  _memberCacheBump_();
}
// ★2026-08-01 시토(배276) — "+직접등록"(member_registered_add)이 실제 회원 DB(유효회원)에도 반영되게.
//   근본원인: 회원관리·신규등록현황 화면은 유효회원 탭만 읽는데(member_registered_list, 2026-06-25 GM),
//   등록 3경로가 전부 _regUpsert_로 '26년 등록현황' 탭에만 썼다 — 그중 SUC 자동이관 2경로는 A안(GM 결재)대로
//   유효회원 미반영이 의도된 동작이지만, "+직접등록"(사람이 계약 확정 후 넣는 경로)까지 같은 함수를 써서
//   실제 회원 DB에 안 들어가는 게 진짜 버그(임정은M 신고 3건 원인). 유효회원은 수기 관리 명단이라 헤더에
//   줄바꿈이 섞여있어(예 '등록\n일자') member_registered_list와 동일하게 공백 제거 후 부분일치로 찾는다.
//   전화 키로 멱등(기존행=갱신, 신규=추가) — 중복 행 안 생김. 필수 칸(회원명·휴대폰) 없으면 조용히 skip(무중단).
// months(개월수, 선택) — 2026-08-01 시토(배286) — 있으면 시작일자·종료일자·잔여일을 계산해 채운다.
//   "+직접등록" 폼이 원래 이름·전화·프로그램·등록일 4칸뿐이라 기간을 몰라 이 칸들이 항상 비어 있었다
//   (오분류의 근본원인). 폼에 개월수 칸이 붙기 전까지는 안 와도 무중단(비어도 안전망은 member_active_list 쪽에 있음).
// opts(선택) — 2026-08-03 시토(GM 지시 "SUC하면 채워야하는 항목값들도 다 들어가게").
//   { owner(담당자) · kind(회원구분) · age(나이) · regClass(등록분류) · locker(락커) } 를 받아 유효회원 칸에 함께 쓴다.
//   등록회차는 여기서 자동 — 신규=1 / 재등록=기존행 값+1(기존행 없으면 1). 사람이 세던 칸이라 자동이 아니면 늘 빈다.
//   ★안 온 칸은 건드리지 않는다(undefined=무변경). 사람이 손으로 채운 값을 빈 값으로 덮지 않기 위함.
// ★담당자는 항상 임정은 (GM 지시 2026-08-03). 실측 1,001명 중 996명이 이미 임정은이고, 나머지도
//   회원 담당은 임정은M 1인이다 — 문의 접수자를 회원 담당자로 흘려 넣던 것이 빈칸·오기의 원인이었다.
//   여기 한 곳에 두면 SUC·직접등록 등 모든 쓰기 경로가 같은 값을 쓴다(담당이 바뀌면 이 줄만 고친다).
var MEMBER_DEFAULT_OWNER = '임정은';
/** 회원 시트 캐시 세대번호 — 시트에 쓰기가 일어나면 올린다(2026-08-04 시토).
 *  캐시 키에 이 값을 섞어 두면, 한 번 올리는 것만으로 기간·옵션별로 갈린 옛 키가 전부 무효가 된다.
 *  (키를 하나씩 지우는 방식은 조합 수만큼 키가 있어 열거가 불가능하다.)
 */
function _memberCacheGen_() {
  try { return PropertiesService.getScriptProperties().getProperty('MEMBER_CACHE_GEN') || '0'; }
  catch (e) { return '0'; }
}
function _memberCacheBump_() {
  try {
    var p = PropertiesService.getScriptProperties();
    p.setProperty('MEMBER_CACHE_GEN', String((parseInt(p.getProperty('MEMBER_CACHE_GEN'), 10) || 0) + 1));
    // ★잔여일 정렬 표시(2026-08-12 GM "액션이 일어날 때만 움직여도 될 것 같은데") — 회원 시트에 쓰기가
    //   있었다는 사실만 여기 한 곳에 남긴다. 워머는 이 표시가 켜져 있을 때만 정렬하고 끄므로,
    //   아무도 안 고친 시간에는 시트를 열지도 않는다(전에는 하루 1회 무조건, 그 전 안은 5분마다 훑기).
    //   이 함수가 회원 시트 쓰기의 단일 관문이라 여기 한 줄이면 모든 쓰기 경로가 덮인다(약속 L21).
    p.setProperty('MEMBER_SORT_DIRTY', '1');
  } catch (e) { /* 캐시 무효화 실패가 저장 자체를 막지 않게 한다 */ }
}

/** 종목명을 **회원 시트가 이미 쓰고 있는 표준 이름**으로 맞춘다 (2026-08-04 시토).
 *
 * ★왜(GM 지적 '종목명이 기록된 종목명이 아니라서 충돌난 것 같은데'):
 *   화면 선택지는 4종 축약('플래티넘'·'노블레스'±골프)인데(2026-07-08 GM 확정 · 문의 화면용),
 *   회원 시트가 실제로 담는 값은 '★(정)플래티넘 ▶ GYM+사우나 ▶ 12개월' 같은 긴 정식명이다.
 *   그 축약값이 그대로 회원 시트에 들어가면 같은 상품이 두 이름으로 갈려 집계·조인이 깨진다
 *   (기억: 종목명 두 벌 — 강습에서 이미 같은 사고가 있었다).
 * ★방식: 상품명 목록을 새로 하드코딩하지 않는다(약속 L01). **시트에 이미 있는 값**에서
 *   같은 등급(노블레스/플래티넘)·같은 골프 유무·같은 기간종류(정/단)를 찾아 가장 많이 쓰이는 것을 쓴다.
 *   못 찾으면 받은 값을 그대로 둔다(지어내지 않는다).
 */
function _memberProgramCanon_(sh, pgI, program, moN) {
  var raw = String(program || '').trim();
  if (!raw || pgI < 0) return raw;
  function _sig(s, m) {
    var t = String(s || '');
    var grade = t.indexOf('노블레스') >= 0 ? 'N' : (t.indexOf('플래티넘') >= 0 ? 'P' : '');
    if (!grade) return '';
    var golf = (t.indexOf('골프') >= 0) ? 'G' : '-';
    // 기간종류: 문자열의 (단)/(정) 표기가 있으면 그것, 없으면 개월수로 판단(1개월 이하=단기).
    var term = t.indexOf('(단)') >= 0 ? 'S' : (t.indexOf('(정)') >= 0 ? 'R' : ((m > 0 && m <= 1) ? 'S' : 'R'));
    return grade + golf + term;
  }
  var want = _sig(raw, moN);
  if (!want) return raw;
  var last = sh.getLastRow();
  if (last < 2) return raw;
  var vals = sh.getRange(2, pgI + 1, last - 1, 1).getValues();
  var tally = {};
  for (var i = 0; i < vals.length; i++) {
    var v = String(vals[i][0] == null ? '' : vals[i][0]).trim();
    if (!v || _sig(v, 0) !== want) continue;
    tally[v] = (tally[v] || 0) + 1;
  }
  var best = '', bestN = 0;
  for (var k in tally) { if (tally[k] > bestN) { best = k; bestN = tally[k]; } }
  return best || raw;
}

function _memberActiveUpsert_(name, phone, program, regDate, months, opts) {
  var key = _regNormPhone_(phone);
  if (!key) return;
  opts = opts || {};
  opts.owner = MEMBER_DEFAULT_OWNER;
  var sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  if (!sh) return;
  var cols = sh.getLastColumn();
  var hdr = sh.getRange(1, 1, 1, cols).getValues()[0].map(function (v) { return String(v).trim(); });
  function _idx(want) {
    var w = String(want).replace(/\s/g, '');
    for (var i = 0; i < hdr.length; i++) { if (hdr[i] && hdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; }
    return -1;
  }
  var nmI = _idx('회원명');
  var phI = _idx('휴대폰'); if (phI < 0) phI = _idx('연락처'); if (phI < 0) phI = _idx('전화');
  var regI = _idx('등록일자');
  var stI = _idx('시작일자');
  var endI = _idx('종료일자'); if (endI < 0) endI = _idx('종료일');
  var remI = _idx('잔여일');
  var pgI = _idx('수강반종목'); if (pgI < 0) pgI = _idx('종목명'); if (pgI < 0) pgI = _idx('회원권'); if (pgI < 0) pgI = _idx('상품'); if (pgI < 0) pgI = _idx('프로그램');
  // 추가 칸(2026-08-03) — 없으면 -1로 조용히 건너뛴다(칸 자동생성 금지 정책 유지).
  //   '등록분류'는 '재등록분류'와도 부분일치하지만 헤더 순서상 '등록 분류'(앞칸)가 먼저 잡힌다.
  var ownI  = _idx('담당자');     // ★'PT 담당자'보다 앞칸이라 먼저 잡힌다
  var kndI  = _idx('회원구분');
  var ageI  = _idx('나이');
  var clsI  = _idx('등록분류');
  var seqI  = _idx('등록회차');
  var lckI  = _idx('락커');
  if (nmI < 0 || phI < 0) return;  // 필수 칸 없음 — 시트 구조사고 방지(칸 자동생성 안 함)
  function _put(row, ci, v) { if (ci >= 0 && v !== undefined && v !== null && String(v) !== '') sh.getRange(row, ci + 1).setValue(v); }
  // 시작일자는 등록일자와 다를 수 있다(계약일 ≠ 이용 시작일 — 실측 다수). opts.startDate 우선.
  var startDate = opts.startDate || regDate || _todayKR_();
  var moN = parseInt(months, 10);
  var endDateStr = '', remN = null;
  if (moN > 0) {
    var sd = new Date(startDate + 'T00:00:00+09:00');
    if (!isNaN(sd.getTime())) {
      var ed = new Date(sd.getTime()); ed.setMonth(ed.getMonth() + moN);
      ed.setDate(ed.getDate() - 1);  // 종료일=마지막 유효일(포함) — 시작+N개월을 그대로 쓰면 하루 더 붙는다(배582, 2026-08-18 시포)
      endDateStr = Utilities.formatDate(ed, 'Asia/Seoul', 'yyyy-MM-dd');
      remN = Math.round((ed.getTime() - Date.now()) / 86400000);
    }
  }
  // 화면이 보낸 축약 종목명('플래티넘' 등)을 회원 시트가 쓰는 정식명으로 맞춘다(위 함수 주석 참조).
  program = _memberProgramCanon_(sh, pgI, program, moN);
  var last = sh.getLastRow();
  if (last >= 2) {
    // ★2026-08-05 시토(GM 지시, "저장이 엉뚱한 회원에게 들어간다" 5건·12일·4회 반복의 뿌리) — 전화 첫매칭만으로
    //   행을 잡으면 가족·유소년처럼 번호를 공유하는 회원이 있을 때 다른 실회원 행을 조용히 덮어쓴다.
    //   인라인 편집(member_active_update, 8393 부근)엔 이미 있는 중복 거부 가드를 이 upsert 경로만 안 거쳤다 —
    //   같은 가드(_countRowsByPhone_, 148)를 그대로 재사용해 배선만 한다(새 함수 없음).
    var _mauDupN = _countRowsByPhone_(sh, phI, key);
    if (_mauDupN >= 2) {
      try {
        _notifyTelegram('⚠️ 회원 자동저장 거부 — 전화 ' + _logMaskPhone_(phone) + ' 매칭 ' + _mauDupN + '건(2건 이상, 가족·유소년 등 번호 공유 추정). "' +
          (name || '') + '" 저장이 유효회원 시트에 자동 반영되지 않았습니다. 시트에서 수동으로 확인·처리해 주세요.');
      } catch (e) {}
      return { ok: false, error: 'phone-ambiguous', count: _mauDupN };
    }
    var phVals = sh.getRange(2, phI + 1, last - 1, 1).getValues();
    for (var i = 0; i < phVals.length; i++) {
      if (_regNormPhone_(phVals[i][0]) === key) {
        var row = i + 2;
        // 등록일자를 덮기 전에 예전 값을 먼저 읽어 둔다 — 회차 판정에 쓴다(아래).
        var _prevRegIso = (regI >= 0) ? (function(){
          var _pv = sh.getRange(row, regI + 1).getValue();
          return (_pv instanceof Date && !isNaN(_pv.getTime()))
            ? Utilities.formatDate(_pv, 'Asia/Seoul', 'yyyy-MM-dd') : (_miToISO_(_pv) || '');
        })() : '';
        if (name) sh.getRange(row, nmI + 1).setValue(name);
        if (program && pgI >= 0) sh.getRange(row, pgI + 1).setValue(program);
        if (regDate && regI >= 0) { var _rc = sh.getRange(row, regI + 1); _rc.setNumberFormat('@'); _rc.setValue(regDate); }
        if (moN > 0 && stI >= 0) sh.getRange(row, stI + 1).setValue(startDate);
        if (moN > 0 && endI >= 0) sh.getRange(row, endI + 1).setValue(endDateStr);
        if (moN > 0 && remI >= 0) sh.getRange(row, remI + 1).setValue(remN);
        _put(row, ownI, opts.owner);
        _put(row, kndI, opts.kind);
        _put(row, ageI, opts.age);
        _put(row, clsI, opts.regClass);
        _put(row, lckI, opts.locker);
        // 등록회차 — 기존 행이 잡혔는데 **등록일자가 실제로 바뀌면** +1 한다.
        //   ★2026-08-04 시토(GM 지적 '박기순님 이번까지 9회차인데'). 종전 조건은 등록 분류 글자에
        //     '재등록'이 들어 있을 때만이었다. 그래서 분류가 '대기'·'단기재등록' 처럼 다른 말로 적힌
        //     재등록은 회차가 안 올랐다 — 박기순님이 그 경우로, 9회차인데 시트엔 8로 굳어 있었다.
        //   ▸판정을 글자가 아니라 사실로 바꾼다: **전화가 같은 기존 행이 잡혔다 = 이미 회원이다.**
        //     거기에 새 등록일자가 들어오면 그건 재등록이다(분류를 뭐라 적었든).
        //   ▸같은 날짜로 다시 저장하면 안 오른다(멱등) — 종전 조건은 재저장할 때마다 계속 올랐다.
        //   ▸예전 등록일자가 비어 있으면 올리지 않는다(비교할 근거가 없으면 손대지 않는다).
        if (seqI >= 0 && regDate && _prevRegIso && _prevRegIso !== String(regDate)) {
          var _prevSeq = parseInt(sh.getRange(row, seqI + 1).getValue(), 10);
          sh.getRange(row, seqI + 1).setValue((_prevSeq > 0 ? _prevSeq : 1) + 1);
        }
        _memberCacheBump_(); _aaCacheClear_(['valid']);   // 유효회원 시트만 바뀌었다 — 그 명단 캐시만 지운다(FB260806-150441 근본수리)
        return;
      }
    }
  }
  // ★2026-08-06 시토(배306) — 전화로 못 찾아 새 행을 만들기 직전, **같은 이름이 이미 다른 전화로 있는지**
  //   확인해 경고한다. 근본원인(정지원 실사고): 전화가 오타·다르게 적히면 같은 사람인데 새 행이 생긴다 —
  //   이 upsert의 대조키가 전화 하나뿐이라서다. 자동 병합은 하지 않는다(어느 전화가 맞는지는 사람만 안다,
  //   note 지시 "자동 병합 금지") — 새 행은 그대로 만들되 텔레그램으로 알려 사람이 판단하게 한다.
  if (name && nmI >= 0 && last >= 2) {
    var _mauNmVals = sh.getRange(2, nmI + 1, last - 1, 1).getValues();
    var _mauNmTrim = String(name).trim();
    if (_mauNmTrim) {
      for (var _mauNi = 0; _mauNi < _mauNmVals.length; _mauNi++) {
        if (String(_mauNmVals[_mauNi][0] || '').trim() === _mauNmTrim) {
          try {
            _notifyTelegram('⚠️ 회원 이름 중복 의심 — "' + _mauNmTrim + '"님이 다른 전화번호로 이미 있는데(유효회원 행 ' + (_mauNi + 2) +
              '), 전화 ' + _logMaskPhone_(phone) + '(으)로 새 행이 추가됩니다. 같은 사람이면(오타 등) 수동으로 확인·병합해주세요.');
          } catch (e) {}
          break;
        }
      }
    }
  }
  var newRow = new Array(cols).fill('');
  newRow[nmI] = name || '';
  if (regI >= 0) newRow[regI] = regDate || _todayKR_();
  if (pgI >= 0 && program) newRow[pgI] = program;
  if (moN > 0 && stI >= 0) newRow[stI] = startDate;
  if (moN > 0 && endI >= 0) newRow[endI] = endDateStr;
  if (moN > 0 && remI >= 0) newRow[remI] = remN;
  if (ownI >= 0 && opts.owner)    newRow[ownI] = opts.owner;
  if (kndI >= 0 && opts.kind)     newRow[kndI] = opts.kind;
  if (ageI >= 0 && opts.age)      newRow[ageI] = opts.age;
  if (clsI >= 0 && opts.regClass) newRow[clsI] = opts.regClass;
  if (lckI >= 0 && opts.locker)   newRow[lckI] = opts.locker;
  if (seqI >= 0) newRow[seqI] = 1;   // 새 행 = 첫 등록
  sh.appendRow(newRow);
  // 전화·등록일자는 appendRow 직후 텍스트서식(@)을 강제해 다시 쓴다 — 숫자로만 보이는 문자열을 Sheets가
  // 자동으로 숫자로 바꾸며 010 앞자리 0이 사라지는 사고 실측(2026-08-01, 정지원 등 3건 · 복구는 member_active_phone_fix).
  var _newRow = sh.getLastRow();
  var _pc = sh.getRange(_newRow, phI + 1); _pc.setNumberFormat('@'); _pc.setValue(phone || '');
  if (regI >= 0) { var _rc2 = sh.getRange(_newRow, regI + 1); _rc2.setNumberFormat('@'); _rc2.setValue(regDate || _todayKR_()); }
  _memberCacheBump_(); _aaCacheClear_(['valid']);   // 유효회원 시트만 바뀌었다 — 그 명단 캐시만 지운다(FB260806-150441 근본수리)
}

// ═══════════════════════════════════════════
//  강습문의 페이지 전용 — 성인 강습 문의 시트 CRM (CPO cpo/member/강습문의.html)
//  ★ 멤버십 문의회원(26년 신규문의) CRM 패턴을 그대로 복제 — 강습 문의 시트(성인 강습 응답탭)로 적용.
//     시트 헤더: 1타임스탬프 2성함 3연락처 4나이 5성인강습종목 6문의경로 7문의사항 8접수담당자 9희망레슨시간 10개인정보동의.
//     관리용 칸(진행상태·담당·상담메모·상담예약·방문상태)은 시트에 없음 → _lessonEnsureCols_ 가 우측에 멱등 생성.
// ═══════════════════════════════════════════
var LESSON_SS_ID = '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw';
var LESSON_GID = 111889422;            // 성인 강습 응답탭
var LESSON_GID_YOUTH = 268994754;      // 유소년 강습 응답탭(WSC) — 성인/유소년 별도 탭 분리(2026-06-27 시포)
// 영문 강습 응답탭 — 영어 문의가 한글 탭과 별도로 쌓여 CRM(문의 현황)에서 누락되던 누수 수리. 2026-07-09 시포·GM.
var LESSON_GID_ADULT_EN = 311319200;   // 성인 강습(영문) 응답탭
var LESSON_GID_YOUTH_EN = 931249179;   // 유소년 강습(영문) 응답탭(WSC)
var _LESSON_KNOWN_GIDS_ = [LESSON_GID, LESSON_GID_YOUTH, LESSON_GID_ADULT_EN, LESSON_GID_YOUTH_EN];
// ★행키 네임스페이스 오프셋(2026-07-09 시포·GM) — 한글+영문 탭을 한 목록에 병합하면 두 시트의 rowIndex(둘 다 2부터 시작)가
//   그대로 충돌해 클라이언트 조회(dbRows.find 등)가 엉뚱한 행을 집어 잘못된 시트에 덮어쓸 위험(무결성 사고) → 영문 탭 행에만
//   거대 오프셋을 더해 값 공간을 완전히 분리한다. 시트당 실사용 행이 100만에 도달할 일이 없어 충돌 불가.
//   읽기(_lessonReadRows_/_miReadRows_)에서 부여 → 쓰기(update/delete)에서 body.rowIndex로 원복 후 실제 행 사용.
var _ROW_OFFSET_EN_ = 1000000;
// 대상(type) → gid 해석. body.type 미전송=성인(하위호환·강습문의.html).
// body.gid 명시(알려진 4개 gid 중 하나) 시 최우선 사용. 없으면 body.rowIndex의 오프셋 여부로 한글/영문 자동 판별(2026-07-09).
function _lessonGidOf_(body) {
  var g = parseInt((body && body.gid) || '', 10);
  var ig = _lessonIntakeGid_();                                   // 강습 신규문의 스태프탭(자체폼 유입, 배1037 갈래B) — 동적 gid
  if (g && ig && g === ig) return ig;                             // body.gid 로 명시된 강습 신규문의 탭
  if (g && _LESSON_KNOWN_GIDS_.indexOf(g) >= 0) return g;
  var ri = parseInt((body && body.rowIndex) || 0, 10);
  if (ig && ri >= _ROW_OFFSET_INTAKE_) return ig;                 // 강습 신규문의 오프셋(EN보다 큼 → 먼저 판정)
  var t = String((body && body.type) || '');
  var youth = (t === '유소년강습' || t === '유소년' || t === 'youth');
  var isEn = ri >= _ROW_OFFSET_EN_;
  if (isEn) return youth ? LESSON_GID_YOUTH_EN : LESSON_GID_ADULT_EN;
  return youth ? LESSON_GID_YOUTH : LESSON_GID;
}
// type(성인/유소년) → 대응하는 영문 gid. 매칭 없으면 null(무중단).
function _lessonEnGidOf_(body) {
  var t = String((body && body.type) || '');
  if (t === '유소년강습' || t === '유소년' || t === 'youth') return LESSON_GID_YOUTH_EN;
  if (!t || t === '성인강습' || t === '성인') return LESSON_GID_ADULT_EN;
  return null;
}
// 관리 담당 컬럼명='관리담당'(★'담당'은 폼 원본 '접수담당자'와 부분일치 충돌 → 컬럼 미생성·원본 덮어쓰기 버그. 2026-06-26 시우).
// '연락이력' — 강습 CONTACT(연락 이력, 축2/축4) 멤버십 미러. 상담메모 컬럼은 보존(비파괴)·연락이력이 신규 정본. 2026-07-08 시포·GM.
// '종목별관리'(JSON 객체맵) — 강습 종목별 독립 관리(축7, GM 2026-07-08 확정). 문의 1건에 종목 여러 개면 종목마다
//  진행상태·담당·연락이력을 독립 저장: { "<sportKey>": { status, owner, contacts:[{date,time,note}] }, ... }.
//  기존 단일 진행상태/관리담당/연락이력 컬럼은 절대 삭제·덮어쓰지 않음(비파괴 폴백 — 특정 sportKey에 값 없으면 프론트가 단일 컬럼 값을 표시).
var LESSON_SPORT_MGMT_COL = '종목별관리';
// 셀 → 종목별관리 객체맵. 파싱 실패·비객체·빈값=안전 {}.
function _lessonSportMgmtParse_(raw) {
  if (!raw) return {};
  var s = String(raw).trim();
  if (!s || s.charAt(0) !== '{') return {};
  try {
    var obj = JSON.parse(s);
    return (obj && typeof obj === 'object' && !Array.isArray(obj)) ? obj : {};
  } catch (e) { return {}; }
}
// 종목별관리 객체맵 → JSON 문자열(빈 객체=''→셀 클리어).
function _lessonSportMgmtStringify_(obj) {
  if (!obj || typeof obj !== 'object') return '';
  return Object.keys(obj).length ? JSON.stringify(obj) : '';
}
// GM이 4 메인시트(성인/유소년 × KR/EN)에 세팅한 flat 관리 컬럼(L~P). 유연매칭으로 이미 있으면 append 안 함(팬텀 컬럼 재생성 차단).
// L=지정 강사(owner)·M=Contact(연락이력)·N=비고(memo)·O=진행 상황(status). 종목별관리(bySport) 모델은 flat 전환으로 폐기. 2026-07-14 시포·GM(배973).
var _LESSON_MGMT_FIELDS = [
  { keys: ['진행상태', '진행현황', '진행상황', '진행 상황', '상태'], canon: '진행 상황' },
  { keys: ['관리담당', '지정 강사'],                                 canon: '지정 강사' },
  { keys: ['상담메모', '메모', '비고'],                             canon: '비고' },
  { keys: [CONTACT_HIST_COL, 'Contact'],                            canon: 'Contact' },
  // ★LOSS사유·LOSS사유메모·등록종목 3항목 재생성 중단(cpo_lesson_col_cleanup_0721로 컬럼 자체 폐기·삭제 — 2026-07-21 시포·GM 3단계).
  //   등록종목은 강습종목 칸 덮어쓰기(retarget)로 대체. LOSS사유(+메모)는 '미등록 사유' 칸으로 이관.
  { keys: ['등록회수'],                                             canon: '등록회수' },       // 강습 등록 회수. _luSet이 자동생성하려면 이 목록 등재가 필요(등록종목과 동일 체계). 2026-07-21 시포·GM.
  { keys: ['유효기간'],                                             canon: '유효기간' },       // 강습 유효기간(만료일). 위와 동일 사유로 등재. 2026-07-21 시포·GM.
  { keys: ['유입경로(자동)', '유입경로자동', '유입경로'],           canon: '유입경로(자동)' }, // 멤버십식 2경로(문의경로+유입경로자동). 성인엔 없어 생성·유소년은 기존칸 매치. 빈칸 구조만(UTM 채움은 시모). 2026-07-21 GM.
  { keys: ['Contact2'],                                             canon: 'Contact2' },       // Contact1~3 멤버십식(현 Contact=1). 2026-07-21 GM.
  { keys: ['Contact3'],                                             canon: 'Contact3' }        // 상동. 사람언어 표시는 3단계(#8). 2026-07-21 GM.
];

// gid 매칭 시트 핸들(탭명 변경에 강함).
function _lessonSheet_(gid) {
  var want = gid || LESSON_GID;
  var sheets = SpreadsheetApp.openById(LESSON_SS_ID).getSheets();
  for (var i = 0; i < sheets.length; i++) { if (sheets[i].getSheetId() === want) return sheets[i]; }
  return null;
}
// 관리 헤더가 헤더행에 없으면 우측에 append(멱등). 각 액션 진입 시 1회 보장.
function _lessonEnsureCols_(sh) {
  if (!sh) return [];
  var lastCol = sh.getLastColumn();
  var hdr = lastCol > 0 ? sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); }) : [];
  // 유연매칭(부분일치)으로 이미 존재하는 필드는 재생성 안 함 — GM의 L~P(지정 강사/Contact/비고/진행 상황)는 이름이 달라도 매칭됨.
  var missing = _LESSON_MGMT_FIELDS.filter(function(f){ return _findCol_(hdr, f.keys) < 0; }).map(function(f){ return f.canon; });
  if (missing.length > 0) {
    sh.getRange(1, lastCol + 1, 1, missing.length).setValues([missing]);
    lastCol += missing.length;
    hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  }
  return hdr;
}
// ═══ 강습 Contact(연락이력) 평문 저장 — 2026-07-22 GM(시트 가독성, 멤버십 Contact1/2/3=평문과 정합) ═══
//  저장 포맷: 줄바꿈 구분 평문, 한 줄 = "YYYY-MM-DD HH:MM 노트"(빈 날짜/시간 생략, 노트만 있으면 노트만).
//  레거시 JSON 배열('[' 시작) 셀은 읽기에서 계속 파싱(하위호환, 무중단) — 신규 쓰기는 항상 평문.
//  프론트 계약(contacts 배열 JSON 문자열 송수신)은 불변 — 백엔드 저장 포맷만 전환.
// 평문 한 줄 → {date,time,note}. 날짜/시간 접두 없으면 전체를 note로.
function _lessonContactPlainParseLine_(line) {
  var s = String(line || '').trim();
  if (!s) return null;
  var _bys = _ctBySplit_(s);   // 컨택자(배101): 줄 끝 '(컨택:이름)' → by 분리 후 나머지 파싱
  s = _bys.note;
  var it = null;
  var m = s.match(/^(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}:\d{2}))?\s*(.*)$/);
  if (m) it = { date: m[1], time: m[2] || '', note: (m[3] || '').trim() };
  else {
    var m2 = s.match(/^(\d{1,2}:\d{2})\s+(.*)$/);
    if (m2) it = { date: '', time: m2[1], note: (m2[2] || '').trim() };
    else it = { date: '', time: '', note: s };
  }
  it.by = _bys.by;
  return it;
}
// 평문 셀(줄바꿈 구분) → 정규 배열([{date,time,note}]). 빈 줄·완전빈 항목 제거. 빈 셀=[].
function _lessonContactPlainParse_(raw) {
  var s = String(raw || '');
  if (!s.trim()) return [];
  var lines = s.split('\n');
  var out = [];
  for (var i = 0; i < lines.length; i++) {
    var it = _lessonContactPlainParseLine_(lines[i]);
    if (it && (it.date || it.time || it.note || it.by)) out.push(it);
  }
  return out;
}
// 정규 배열 → 평문 셀(줄바꿈 구분, 한 줄="YYYY-MM-DD HH:MM 노트 (컨택:이름)" 빈 값 생략). 빈 배열=''(셀 클리어).
function _lessonContactPlainStringify_(arr) {
  var lines = [];
  (arr || []).forEach(function(it){
    if (!it) return;
    var d = _miToISO_(it.date || '');
    var t = it.time ? String(it.time).trim() : '';
    var n = _ctByJoin_((it.note == null) ? '' : String(it.note).trim(), it.by);   // 컨택자(배101) 마커 포함
    if (!d && !t && !n) return;
    var parts = [];
    if (d) parts.push(d);
    if (t) parts.push(t);
    if (n) parts.push(n);
    lines.push(parts.join(' '));
  });
  return lines.join('\n');
}
// 셀(레거시 JSON'['·신규 평문·손상 JSON) → 정규 배열. 양쪽 포맷 지원(마이그레이션 중 무중단) + 손상 JSON은
// 원문을 note로 보존(무손실) — JSON.parse 성공(빈 배열 포함)만 정상 JSON으로 취급, 실패 시에만 폴백.
function _lessonContactCellParse_(raw) {
  var s = String(raw || '').trim();
  if (!s) return [];
  if (s.charAt(0) === '[') {
    try {
      var arr = JSON.parse(s);
      if (Array.isArray(arr)) return _resParse_(arr);
    } catch (e) { /* 손상 JSON → 아래 폴백 */ }
    return [{ date: '', time: '', note: s }];
  }
  return _lessonContactPlainParse_(s);
}
// 강습 행 배열 — 문의 + 관리 필드 통합. 빈 행(성함·연락처 둘 다 없음) 스킵.
// 종목별 컨택 분리(GM 2026-07-22 · 평문 태그) — 연락이력 각 줄 노트가 '[종목] …'로 시작하면 그 종목 버킷으로 분류.
//   태그 없는 줄=공통(레거시). 반환 {sportKey:{contacts:[{date,time,note(태그제거)}]}} — 프론트 bySport 계약과 정합.
//   ★JSON 종목별관리 칸을 안 쓴다(GM: 시트에 JSON 금지). 저장 정본=연락이력 평문 칸 한 곳.
function _lessonContactsBySport_(arr, sportStr) {
  var out = {};
  var _norm = function (s) { return String(s || '').replace(/\s+/g, ''); };
  // 이 회원의 실제 종목 토큰(콤마·슬래시 분리, 정규화) — 태그는 이 집합과 '정확일치'할 때만 종목별로 분리(프론트 _lessonSportSplit 정합).
  var _tokens = String(sportStr || '').split(/[,/]/).map(function (s) { return _norm(s); }).filter(Boolean);
  (arr || []).forEach(function (c) {
    var m = String(c && c.note != null ? c.note : '').match(/^\s*\[([^\]]+)\]\s*([\s\S]*)$/);
    if (!m) return;
    var sk = m[1].trim();
    // 실제 종목 토큰과 정확일치하는 태그만 분리 — 부분일치('[수영]' vs '모자수영') 오귀속·대괄호 메모('[식]') 오분류 방지.
    //   미일치 태그 줄은 flat(공통)로 남아 화면에 계속 노출(숨김 없음). 2026-07-22 시포(디버그).
    if (!sk || _tokens.indexOf(_norm(sk)) < 0) return;
    if (!out[sk]) out[sk] = { contacts: [] };
    out[sk].contacts.push({ date: c.date || '', time: c.time || '', note: (m[2] || '').trim(), by: c.by || '' });   // 컨택자 보존(배101)
  });
  return out;
}
// ★접수 시각 보존(2026-07-24 시포·GM) — 2026-07-20 에 멤버십(_miReadRows_)만 _miToISOTime_ 로 고치고
//   강습·렌트비즈는 _miToISO_(날짜만) 그대로 둬서 같은 개념이 화면마다 다르게 보였다(멤버십은 시각까지,
//   강습은 날짜만). 시트엔 시각이 멀쩡히 살아 있다(실측: 성인 'Fri Jul 24 2026 00:22:25', 유소년 13:26:32).
//   _miToISOTime_ 는 시각이 없거나 자정이면 날짜만 돌려주므로 과거 행도 안전하다.
function _lessonReadRows_(gid) {
  var sh = _lessonSheet_(gid);
  if (!sh) return [];
  var hdr = _lessonEnsureCols_(sh);
  var last = sh.getLastRow();
  if (last < 2) return [];
  var data = sh.getRange(2, 1, last - 1, hdr.length).getValues();
  // ★영문 강습탭 헤더 별칭(2026-07-09 시포·GM, 영어 문의 누수 수리) — 실측(성인/유소년 영문 응답탭 gviz) 기준.
  //   'Full Name'은 "Child's Full Name"(유소년)에도 부분일치로 걸림 · 'Mobile Phone Number'는 "Guardian's Mobile Phone Number"에도 걸림.
  var iTs    = _findCol_(hdr, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '날짜']);
  var iName  = _findCol_(hdr, ['성함', '이름', 'Full Name']);   // '성함' 우선 — '접수 담당자 혹은 본인 이름' 오매칭 차단
  var iPhone = _findCol_(hdr, ['연락처', '전화', '휴대폰', 'Mobile Phone Number']);
  var iAge   = _findCol_(hdr, ['나이', '연령', '자녀 나이', '자녀나이', '학년', 'Age']);
  var iSport = _findCol_(hdr, ['성인 강습 종목', 'WSC 강습 종목', 'WSC 강습 종류', '강습 종목', '종목', '과목', 'Program of Interest']);
  var iChan  = _findCol_(hdr, ['문의 경로', '경로', '채널', '알게', 'How Did You Hear About Us?']);
  var iNote  = _findCol_(hdr, ['문의 사항', '문의사항', '문의 내용', '내용', 'Additional Requests or Comments']);
  var iWish  = _findCol_(hdr, ['희망하시는 레슨 시간', '희망 레슨', '희망시간', '레슨 시간', 'Preferred Lesson Time']);
  var iStat  = _findCol_(hdr, ['진행상태', '진행현황', '진행상황', '진행 상황', '상태']);  // '진행 상황'(공백) = GM flat O컬럼
  var iOwner = _findColExact_(hdr, ['지정 강사', '관리담당']);  // ★정확일치 — '지정 강사'(GM flat L) 우선. 옛 팬텀 '관리담당' 잔존 시에도 L이 이기게 순서 고정. 폼 원본 '접수담당자' 안 건드림
  var iMemo  = _findCol_(hdr, ['상담메모', '메모', '비고']);
  var iCons  = _findCol_(hdr, ['상담예약', '상담 예약', '상담일정']);
  var iVisit = _findCol_(hdr, ['방문상태', '방문']);
  var iHist  = _findCol_(hdr, [CONTACT_HIST_COL, 'Contact']);  // 연락이력(JSON) 우선 → GM flat M컬럼 'Contact'(줄바꿈 포함이라 부분일치). 2026-07-14 시포·GM(배973)
  var iSportMgmt = _findColExact_(hdr, [LESSON_SPORT_MGMT_COL]);  // 종목별관리(JSON) — 축7. 2026-07-08 시포·GM
  var iLossR  = _findCol_(hdr, ['LOSS사유', '미등록 사유', '미등록사유']);   // LOSS 사유(강습) — 실제 시트 칸='미등록 사유'(멤버십과 동일). 'LOSS사유' 칸은 미존재라 별칭 추가(불일치 수리). 2026-07-22 시포·GM.
  var iLossRN = _findCol_(hdr, ['LOSS사유메모']);
  var iRegProgram = _findCol_(hdr, ['확정종목', '등록종목']);  // 등록(SUC) 시 실제 등록한 종목(강습) — '확정종목' 신설(2026-08-25), 구 '등록종목'은 폐기칸(하위호환 폴백).
  var iRegDate = _findCol_(hdr, ['등록일']);  // 강습 등록정보 5칸 신설(2026-08-25 GM 지시) — 등록일. 대시보드 집계 기준일로도 사용.
  var iLang  = _findCol_(hdr, ['Language']);  // 응답자 기재 언어(영문 탭 실측 헤더) — 영어 문의 뱃지 표시용. 2026-07-09 시포·GM
  // 영문 탭 행키 오프셋(_ROW_OFFSET_EN_) — 한글+영문 병합 시 rowIndex 충돌 방지(위 상수 주석 참고). 2026-07-09 시포·GM.
  var rowOffset = (gid === LESSON_GID_ADULT_EN || gid === LESSON_GID_YOUTH_EN) ? _ROW_OFFSET_EN_ : 0;
  var out = [];
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var hasName  = iName  >= 0 && row[iName];
    var hasPhone = iPhone >= 0 && row[iPhone];
    if (!hasName && !hasPhone) continue;  // 완전 빈 행 스킵
    var consVal = iCons >= 0 ? row[iCons] : '';
    var consTime = _miTime_(consVal) || _miTimeKR_(consVal);
    var _lMemo = iMemo >= 0 ? String(row[iMemo] || '') : '';
    // 연락이력(가변): JSON 우선 → 없고 기존 상담메모에 값 있으면 {date:'',time:'',note:상담메모}로 합성(비파괴·하위호환).
    //   상담메모 컬럼 자체는 절대 덮어쓰지 않음(읽기 시 합성만) — 연락이력이 있으면 그것을 우선 사용. 2026-07-08 시포·GM.
    var _lHistRaw = iHist >= 0 ? row[iHist] : '';
    var _lHistArr = _lessonContactCellParse_(_lHistRaw);  // 평문(줄바꿈, 신정본) · 레거시 JSON('[') 둘 다 지원. 2026-07-22 GM
    if (!_lHistArr.length && _lMemo) _lHistArr.push({ date: '', time: '', note: _lMemo });  // 레거시 상담메모 폴백
    out.push({
      rowIndex: r + 2 + rowOffset,
      timestamp: _miToISOTime_(iTs >= 0 ? row[iTs] : ''),   // 시각 보존(2026-07-24 시포·GM · 멤버십과 동일 규칙)
      name:    iName  >= 0 ? String(row[iName]  || '') : '',
      phone:   iPhone >= 0 ? _fmtPhone_(row[iPhone]) : '',   // 표시 정규화(앞 0 복원·하이픈)
      age:     iAge   >= 0 ? String(row[iAge]   || '') : '',
      sport:   iSport >= 0 ? String(row[iSport] || '') : '',
      channel: iChan  >= 0 ? String(row[iChan]  || '') : '',
      note:    iNote  >= 0 ? String(row[iNote]  || '') : '',
      wishTime:iWish  >= 0 ? String(row[iWish]  || '') : '',  // 키=wishTime(프론트 row.wishTime와 통일·소문자 wishtime 버그 수정)
      status:  iStat  >= 0 ? String(row[iStat]  || '') : '',
      owner:   iOwner >= 0 ? String(row[iOwner] || '') : '',
      memo:    _lMemo,
      consult: _miToISO_(consVal),
      consultTime: consTime,
      consultTmin: _miTminKR_(consTime),
      visited: iVisit >= 0 ? String(row[iVisit] || '') : '',
      contacts: _lHistArr,
      // 종목별 컨택 분리(GM 2026-07-22) — 연락이력 평문의 '[종목]' 태그 줄을 이 회원 실제 종목 기준으로 그룹핑(JSON 칸 미사용).
      bySport: _lessonContactsBySport_(_lHistArr, iSport >= 0 ? String(row[iSport] || '') : ''),
      lossReason:     iLossR  >= 0 ? String(row[iLossR]  || '') : '',   // LOSS 사유(강습 문의 퍼널). 2026-07-18 시토(GM요청) 대행.
      lossReasonNote: iLossRN >= 0 ? String(row[iLossRN] || '') : '',
      regProgram: iRegProgram >= 0 ? String(row[iRegProgram] || '') : '',   // 등록 종목(SUC 시 실제 등록한 종목, 강습). 2026-07-20 시포(GM요청).
      regDate: iRegDate >= 0 ? _miToISO_(row[iRegDate]) : '',   // 등록일(신설 2026-08-25) — 대시보드 등록 집계 기준일(없으면 접수일 폴백).
      // 출처 물리 시트 gid + 기재 언어 — 영문 탭 병합 표시·저장 라우팅용(row.gid 그대로 되돌려 보내면 정확한 탭에 기록). 2026-07-09 시포·GM.
      gid: gid,
      lang: iLang >= 0 ? String(row[iLang] || '').trim() : '',
      // 지문키(rowKey, §4 R1) — 정규화 타임스탬프+정규화 전화(raw 셀 값). 2026-07-22 시포(오지목 근본수리).
      rowKey: (function(){ var _t = _normTsKey_(iTs >= 0 ? row[iTs] : ''), _p = _normPhone_(iPhone >= 0 ? row[iPhone] : ''), _n = _normNameKey_(iName >= 0 ? row[iName] : ''); /* 이름은 세 번째 파트로 붙인다(배491) — 없으면 두 파트 그대로라 옛 화면과 호환된다. */ return (_t && _p) ? (_t + '|' + _p + (_n ? '|' + _n : '')) : ''; })()
    });
  }
  return out;
}

// 강습 문의 목록(한글+영문 탭 병합) — CRM 읽기경로 전용. 마케팅 집계(FORM_SHEETS·funnel_conversion)는 별도 무손상.
//   type(성인/유소년)에 해당하는 한글 탭 + 영문 탭을 함께 읽어 이어붙인다. 영문 탭 미존재/에러는 조용히 스킵(무중단).
//   2026-07-09 시포·GM — 영어 문의 누수 수리.
function _lessonReadRowsMerged_(body) {
  var krGid = _lessonGidOf_(body);
  var enGid = _lessonEnGidOf_(body);
  var rows = _lessonReadRows_(krGid);
  if (enGid && enGid !== krGid) {
    try { rows = rows.concat(_lessonReadRows_(enGid)); } catch (e) {}
  }
  // 강습 신규문의 스태프탭(자체폼 유입, 배1037 갈래B) 병합 — 관리페이지가 자동으로 표시(읽기 자동정합). 미존재/에러는 조용히 스킵.
  try { rows = rows.concat(_lessonIntakeReadRows_(body)); } catch (e) {}
  return rows;
}

// ═══════════════════════════════════════════
//  갈래 B — 유입 자체 Survey 폼 백엔드 (배1037 · 시포 2026-07-15)
//  공개 액션 intake_submit 1개. 멤버십→'26년 신규문의' 탭(_miSheet_·member_inquiry_list 자동정합),
//  강습→신규 '강습 신규문의' 스태프탭(구글폼 응답탭 직접쓰기 회피·구조리셋 방지).
//  수집 유실 0: (프론트) redirect follow+r.json → res.ok만 성공 · 멱등 submissionId · localStorage 대기큐 · 지수백오프.
//              (백엔드) submissionId Cache dedup · 저장 실패는 재시도가능 응답(noRetry 미설정)으로 대기큐 재전송 유도.
//  스팸방어(구글폼 캡차 상실 보상): 토큰 · 허니팟 · 타이밍 게이트 · 레이트리밋 · 서버측 재검증.
// ═══════════════════════════════════════════
var INTAKE_SUBMIT_TOKEN = 'wlp_intake_9f4c1b7e2a63';   // ScriptProperties INTAKE_SUBMIT_TOKEN 있으면 우선(없으면 이 기본값). 프론트 숨김토큰과 일치해야 함.
var LESSON_INTAKE_SHEET_NAME = '강습 신규문의';
var _ROW_OFFSET_INTAKE_ = 2000000;   // 강습 신규문의 탭 행키 네임스페이스(KR=0·EN=1000000과 분리 → 병합 rowIndex 충돌·오수정 방지)
var LESSON_INTAKE_HEADERS = ['타임스탬프','성함','연락처','자녀 나이','유형','강습 종목','희망 레슨 시간','문의 경로','문의 사항','개인정보 수집·이용 동의','접수ID','진행 상황','지정 강사','Contact','비고'];

function _intakeToken_() { return _accessProp_('INTAKE_SUBMIT_TOKEN') || INTAKE_SUBMIT_TOKEN; }

// ─── 실무진 피드백 쓰기 게이트 (2026-08-04 시토 재개 · 배299) ──────────────────────
//   staff_feedback_list·staff_feedback_update 판정을 이 함수 한 곳에서만 한다.
//   ①마스터 토큰(_intakeToken_) — 기존 경로 그대로 보존, list·resort·update 전부 통과(회귀 없음).
//   ②커튼 열쇠(_assets/gate.js 의 사내 게이트 비밀번호) — staff_feedback_update 한정,
//     그것도 resort(시트 전체 재정렬)는 제외. 새 토큰·새 인증 체계는 만들지 않는다(약속 L21).
//   둘 다 아니면 거부(fail-closed) — 비로그인(커튼 미통과) 상태의 쓰기는 통과할 수 없다.
function _staffFeedbackWriteAuthed_(action, body) {
  if (String(body.t || '') === _intakeToken_()) return true;
  if (action !== 'staff_feedback_update' || body.resort === true) return false;
  var gatePw = _accessProp_('STAFF_GATE_PW') || 'wellperion!@345';   // gate.js GATE_PW와 동일 값(정본=ScriptProperties)
  return String(body.password || '') === gatePw;
}

// ─── QA 격리 판정(2026-07-30 시토, 배195) ───────────────────────────────────
//   submit_inquiry 는 방문자 공개 액션이라(_SURVEY_PUBLIC_ACTIONS 토큰 면제) 진짜 손님이 실수로
//   qa=1 을 붙여도 격리로 새지 않아야 하고, 반대로 qa=1 만으로 아무나 격리 경로를 추측해 쓰면
//   안 된다 — 그래서 새 비밀값을 코드에 평문으로 넣는 대신 이미 있는 토큰(_intakeToken_, 다른
//   비공개 액션 전부가 재사용 중)과 qa=1 을 **둘 다** 요구한다. 판정 로직은 여기 한 곳뿐 —
//   submit_inquiry·inquiry_list 양쪽이 이 함수 하나를 재사용한다(약속 L01·L21).
function _isQaInquiryCall_(body) {
  return String(body.qa || '') === '1' && String(body.t || '') === _intakeToken_();
}

// (폐기 2026-07-24 GM) _quarantineIntake_ / 접수 보류함 = 사후 안전망이라 삭제. 근본 셋팅으로 전환:
//   허니팟 걸림도 버리지 않고 정상 저장 + 비고 '⚠️스팸의심' 표시(intake_submit 참조). 별도 탭 안 생김.

// 강습 신규문의 스태프탭 핸들(옵션 생성). LESSON_SS_ID(1b0XU1o) 하위 신규 탭 — 기존 응답탭·팀시트 IMPORTRANGE 정렬 불변(새 탭 추가는 무영향).
function _lessonIntakeSheet_(createIfMissing) {
  var ss = SpreadsheetApp.openById(LESSON_SS_ID);
  var sh = ss.getSheetByName(LESSON_INTAKE_SHEET_NAME);
  if (!sh && createIfMissing) {
    sh = ss.insertSheet(LESSON_INTAKE_SHEET_NAME);
    sh.getRange(1, 1, 1, LESSON_INTAKE_HEADERS.length).setValues([LESSON_INTAKE_HEADERS]);
    sh.setFrozenRows(1);
    try { sh.getRange(1, 1, 1, LESSON_INTAKE_HEADERS.length).setFontWeight('bold'); } catch (e) {}
  }
  return sh || null;
}
var _lessonIntakeGidCache_ = null;
function _lessonIntakeGid_() {
  if (_lessonIntakeGidCache_ !== null) return _lessonIntakeGidCache_;
  var sh = _lessonIntakeSheet_(false);
  _lessonIntakeGidCache_ = sh ? sh.getSheetId() : null;
  return _lessonIntakeGidCache_;
}

// ─── 신규 3종(여름특강·공간렌트·비즈니스) 저장처 — 6종 문의폼 확장(2026-07-16 시토) ───
//   summer → '강습 신규문의' 탭 재사용(집중강습 계열, 유형칼럼에 '여름특강(성인/유소년)'으로 구분 — 기존 성인/유소년 로직 무변경).
//   rental·business → _MI_SS_ID(멤버십 스프레드시트, '26년 신규문의'와 동일 SS — 구글폼 시절부터 이 SS로 통합 관례) 하위 신규 탭.
//   패턴은 _lessonIntakeSheet_ 그대로 복제(없으면 생성 + 헤더행 + 굵게 + 고정행1).
var RENTAL_INTAKE_SHEET_NAME = '공간렌트 문의';
var RENTAL_INTAKE_HEADERS = ['타임스탬프','성함','연락처','대관 공간','용도','희망일','예상 인원','문의 사항','개인정보 수집·이용 동의','접수ID','진행 상황','비고'];
function _rentalIntakeSheet_(createIfMissing) {
  var ss = SpreadsheetApp.openById(_MI_SS_ID);
  var sh = ss.getSheetByName(RENTAL_INTAKE_SHEET_NAME);
  if (!sh && createIfMissing) {
    sh = ss.insertSheet(RENTAL_INTAKE_SHEET_NAME);
    sh.getRange(1, 1, 1, RENTAL_INTAKE_HEADERS.length).setValues([RENTAL_INTAKE_HEADERS]);
    sh.setFrozenRows(1);
    try { sh.getRange(1, 1, 1, RENTAL_INTAKE_HEADERS.length).setFontWeight('bold'); } catch (e) {}
  }
  return sh || null;
}

var BUSINESS_INTAKE_SHEET_NAME = '비즈니스 문의';
// ⚠️ business는 프론트에 name 키가 없음(company·contactName만) → '성함' 칼럼 = company + ' / ' + contactName 로 합성 저장(다른 문의 탭과 스키마 정합 유지).
var BUSINESS_INTAKE_HEADERS = ['타임스탬프','성함','회사명','담당자','연락처','제휴 유형','소개자료 링크','제안 내용','개인정보 수집·이용 동의','접수ID','진행 상황','비고'];
function _businessIntakeSheet_(createIfMissing) {
  var ss = SpreadsheetApp.openById(_MI_SS_ID);
  var sh = ss.getSheetByName(BUSINESS_INTAKE_SHEET_NAME);
  if (!sh && createIfMissing) {
    sh = ss.insertSheet(BUSINESS_INTAKE_SHEET_NAME);
    sh.getRange(1, 1, 1, BUSINESS_INTAKE_HEADERS.length).setValues([BUSINESS_INTAKE_HEADERS]);
    sh.setFrozenRows(1);
    try { sh.getRange(1, 1, 1, BUSINESS_INTAKE_HEADERS.length).setFontWeight('bold'); } catch (e) {}
  }
  return sh || null;
}

// ─── 오넛티 추석 선물세트 접수(2026-08-07 GM 지시) — RENTAL/BUSINESS와 동일 패턴 복제 ───
//   저장은 이 탭 하나로 통일 — 웹접수·현장판매분 모두 여기 append(별도 시트 금지, GM: 통합 접수 시트 일원 관리).
//   현장 판매분은 수령방법='현장 수령'·비고에 표시해 구분(이 함수는 웹접수 경로만 담당 — 현장분은 담당자가 같은 탭에 직접 기입).
//   선착순 500세트는 행 삭제로 관리하지 않는다(INC-020 재발방지) — 상태값(접수/확정/대기/취소)만 바꾼다.
var OHNUTTI_INTAKE_SHEET_NAME = '오넛티 선물세트 접수';
var OHNUTTI_INTAKE_HEADERS = ['접수시각','접수번호','성함','연락처','수량','세트종류','수령방법','희망수령일','배송지','결제방법','요청사항','상태','순번','결제기한','비고'];
var OHNUTTI_CAP = 500;   // 선착순 500세트(신청 건수가 아니라 세트 수량 합) — GM 확정
function _ohnuttiIntakeSheet_(createIfMissing) {
  var ss = SpreadsheetApp.openById(_MI_SS_ID);
  var sh = ss.getSheetByName(OHNUTTI_INTAKE_SHEET_NAME);
  if (!sh && createIfMissing) {
    sh = ss.insertSheet(OHNUTTI_INTAKE_SHEET_NAME);
    sh.getRange(1, 1, 1, OHNUTTI_INTAKE_HEADERS.length).setValues([OHNUTTI_INTAKE_HEADERS]);
    sh.setFrozenRows(1);
    try { sh.getRange(1, 1, 1, OHNUTTI_INTAKE_HEADERS.length).setFontWeight('bold'); } catch (e) {}
  }
  return sh || null;
}

// 재고 집계 — 헤더 라벨 기준으로만 읽는다(_findCol_, 인덱스 금지 · 2026-08-05 사고 재발방지).
//   '결제기한'이 지난 '접수'(결제대기) 행은 슬롯을 계속 잡아먹지 않도록 확정+접수 합계에서 자동 제외한다
//   (행을 지우거나 상태를 고쳐쓰지 않고, 집계 시점 판정만으로 반영 — 물리적 상태 변경 없음).
function _ohnuttiCapacityStats_() {
  var stats = { cap: OHNUTTI_CAP, total: 0, confirmed: 0, pending: 0, waiting: 0, remaining: OHNUTTI_CAP };
  var sh = _ohnuttiIntakeSheet_(false);
  if (!sh) return stats;
  var lastCol = sh.getLastColumn(), lastRow = sh.getLastRow();
  if (lastRow < 2 || lastCol < 1) return stats;
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  var iQty = _findCol_(hdr, ['수량']);
  var iStat = _findCol_(hdr, ['상태']);
  var iDeadline = _findCol_(hdr, ['결제기한']);
  if (iQty < 0 || iStat < 0) return stats;   // 칼럼 자체가 없으면 0 날조 금지(rentbiz 패턴과 동일 원칙) — cap만 반환
  var data = sh.getRange(2, 1, lastRow - 1, lastCol).getValues();
  var now = new Date();
  for (var r = 0; r < data.length; r++) {
    var q = parseInt(data[r][iQty], 10) || 0;
    if (!q) continue;
    var st = String(data[r][iStat] || '').trim();
    stats.total += q;
    if (st === '확정') {
      stats.confirmed += q;
    } else if (st === '접수') {
      var dlRaw = iDeadline >= 0 ? data[r][iDeadline] : '';
      var dl = (dlRaw instanceof Date) ? dlRaw : (dlRaw ? new Date(dlRaw) : null);
      var expired = dl && !isNaN(dl) && dl < now;
      if (!expired) stats.pending += q;   // 기한 만료분은 슬롯 반환(집계 제외) — 상태값은 그대로(팀이 취소로 정리)
    } else if (st === '대기') {
      stats.waiting += q;
    }
  }
  stats.remaining = Math.max(0, OHNUTTI_CAP - stats.confirmed - stats.pending);
  return stats;
}

// 오넛티 팀 조회 접속코드 — ScriptProperties 키가 설정되면 그 값이 우선, 미설정이면 기본값 '1200'으로 동작(GM 즉시 사용, 2026-08-07).
var OHNUTTI_ACCESS_CODE_PROP = 'OHNUTTI_ACCESS_CODE';
var OHNUTTI_ACCESS_CODE_DEFAULT = '1200';
function _ohnuttiTeamAuthed_(body) {
  var code = String(_accessProp_(OHNUTTI_ACCESS_CODE_PROP) || '').trim() || OHNUTTI_ACCESS_CODE_DEFAULT;
  return String((body && body.code) || '').trim() === code;
}

// 상태값 4종 — '접수'(=화면 라벨 "결제대기", 결제기한 있음)와 '대기'(=화면 라벨 "대기순번", 정원초과 대기)는
// 서로 뜻이 다른 별개 상태라 둘 다 유지한다(GM이 말한 "결제대기"는 기존 '접수'의 화면 라벨 — 새 값 아님).
var OHNUTTI_STATUSES = ['접수', '확정', '대기', '취소'];
// id(접수번호) 정확일치로 물리행을 찾는다 — 행번호 기준 삭제/수정 금지(INC-020류 오삭제 재발방지, 웹접수/화면표시 열 불일치 전례).
function _ohnuttiFindRowById_(sh, id) {
  var lastCol = sh.getLastColumn(), lastRow = sh.getLastRow();
  if (lastRow < 2 || lastCol < 1) return { row: -1, count: 0 };
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  var iNum = _findCol_(hdr, ['접수번호']);
  if (iNum < 0) return { row: -1, count: 0 };
  var col = sh.getRange(2, iNum + 1, lastRow - 1, 1).getValues();
  var hits = [];
  for (var r = 0; r < col.length; r++) {
    if (String(col[r][0] || '').trim() === id) hits.push(r + 2);
  }
  return { row: hits.length === 1 ? hits[0] : -1, count: hits.length };
}

// 강습 신규문의 탭 → 문의행 배열(강습 목록 병합용). body.type(성인강습/유소년강습)로 '유형' 필터. _ROW_OFFSET_INTAKE_ 부여.
// _lessonReadRows_ 와 동일한 행 스키마를 반환(프론트·lesson_inquiry_update 라운드트립 정합).
function _lessonIntakeReadRows_(body) {
  var sh = _lessonIntakeSheet_(false);
  if (!sh) return [];
  var gid = sh.getSheetId();
  var last = sh.getLastRow();
  var lastCol = sh.getLastColumn();
  if (last < 2 || lastCol < 1) return [];
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  var data = sh.getRange(2, 1, last - 1, lastCol).getValues();
  var iTs = _findCol_(hdr, ['타임스탬프']), iType = _findCol_(hdr, ['유형']),
      iName = _findCol_(hdr, ['성함', '이름']), iPhone = _findCol_(hdr, ['연락처', '전화', '휴대폰']),
      iAge = _findCol_(hdr, ['자녀 나이', '나이', '연령']), iSport = _findCol_(hdr, ['강습 종목', '종목']),
      iWish = _findCol_(hdr, ['희망 레슨 시간', '희망시간']), iChan = _findCol_(hdr, ['문의 경로', '경로', '채널']),
      iNote = _findCol_(hdr, ['문의 사항', '문의내용', '내용']),
      iStat = _findCol_(hdr, ['진행 상황', '진행상태', '상태']), iOwner = _findColExact_(hdr, ['지정 강사', '관리담당']),
      iHist = _findCol_(hdr, [CONTACT_HIST_COL, 'Contact']), iMemo = _findCol_(hdr, ['비고', '메모', '상담메모']);
  var want = String((body && body.type) || '');
  var out = [];
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var hasName = iName >= 0 && row[iName], hasPhone = iPhone >= 0 && row[iPhone];
    if (!hasName && !hasPhone) continue;
    var rowType = iType >= 0 ? String(row[iType] || '').trim() : '';
    // 여름특강(성인)/(유소년)을 성인강습/유소년강습 뷰에 합류 표시(2026-07-18 시포 — 저장O·현황 미표시 갭 수리). 원본 유형값 보존, 매칭용으로만 정규화.
    var matchType = rowType;
    if (/^여름특강\s*\(\s*성인/.test(rowType)) matchType = '성인강습';
    else if (/^여름특강\s*\(\s*유소년/.test(rowType)) matchType = '유소년강습';
    if (want && matchType && matchType !== want) continue;   // 유형 불일치 제외(값 없으면 포함 — 누락 방지)
    var histRaw = iHist >= 0 ? row[iHist] : '';
    var histArr = _resParse_(histRaw);
    if (!histArr.length) { var p = String(histRaw || '').trim(); if (p) histArr.push({ date: '', time: '', note: p }); }
    out.push({
      rowIndex: r + 2 + _ROW_OFFSET_INTAKE_,
      timestamp: _miToISOTime_(iTs >= 0 ? row[iTs] : ''),   // 시각 보존(2026-07-24 시포·GM · 멤버십과 동일 규칙)
      name:    iName  >= 0 ? String(row[iName]  || '') : '',
      phone:   iPhone >= 0 ? _fmtPhone_(row[iPhone]) : '',
      age:     iAge   >= 0 ? String(row[iAge]   || '') : '',
      sport:   iSport >= 0 ? String(row[iSport] || '') : '',
      channel: iChan  >= 0 ? String(row[iChan]  || '') : '',
      note:    iNote  >= 0 ? String(row[iNote]  || '') : '',
      wishTime:iWish  >= 0 ? String(row[iWish]  || '') : '',
      status:  iStat  >= 0 ? String(row[iStat]  || '') : '',
      owner:   iOwner >= 0 ? String(row[iOwner] || '') : '',
      memo:    iMemo  >= 0 ? String(row[iMemo]  || '') : '',
      consult: '', consultTime: '', consultTmin: null, visited: '',
      contacts: histArr, bySport: {},
      gid: gid, lang: '', intake: true,
      // 지문키(rowKey, §4 R1) — 정규화 타임스탬프+정규화 전화(raw 셀 값). 2026-07-22 시포(오지목 근본수리).
      rowKey: (function(){ var _t = _normTsKey_(iTs >= 0 ? row[iTs] : ''), _p = _normPhone_(iPhone >= 0 ? row[iPhone] : ''), _n = _normNameKey_(iName >= 0 ? row[iName] : ''); /* 이름은 세 번째 파트로 붙인다(배491) — 없으면 두 파트 그대로라 옛 화면과 호환된다. */ return (_t && _p) ? (_t + '|' + _p + (_n ? '|' + _n : '')) : ''; })()
    });
  }
  return out;
}

// 강습 데이터 범위 필터 — 기본=올해(현재연도)만, scope=all이면 전체(시포·GM 2026-06-26).
// 타임스탬프는 _miToISO_로 'YYYY-MM-DD' 정규화됨 → 앞 4자리=연도(Asia/Seoul 기준 현재연도와 비교).
// ★ 필드 무관 범용 로직(row.timestamp만 사용) — 아래 공간렌트·비즈니스 문의(rentbiz_*)도 그대로 재사용.
function _lessonScopeFilter_(rows, body) {
  if (String((body && body.scope) || '') === 'all') return rows;
  var yr = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy');
  return rows.filter(function(row) {
    var y = String(row.timestamp || '').slice(0, 4);
    if (!/^\d{4}$/.test(y)) return true;  // ★타임스탬프 파싱 실패(빈/비표준)는 버리지 않고 포함 — 조용한 누락 방지
    return y === yr;   // 연도필터 엄격 — 선택 연도만(2026 체크=2026만 표시). 2026-07-18 GM(#3 완화 롤백: '2026 체크해도 전체 뜸' 수리). 미해결 과거건은 '전체보기(scope=all)'로.
  });
}

// ═══════════════════════════════════════════
//  문의회원 페이지(CPO) — 공간 렌트·비즈니스 파트너 문의 관리 패널
//  ★ 강습문의(lesson_inquiry_list/lesson_stats) 패턴을 그대로 미러링 — 컬럼탐지·마스킹 정책 동일(마스킹 없음·전체공개).
//     두 문의는 이미 FORM_SHEETS(멤버십과 동일 스프레드시트 12AWcAlg…)의 응답탭에 귀속되어 있다(2026-06-15).
//     달력·등록전환 없는 린(lean) 버전 — 문의 목록·통계만. 쓰기 액션 없음(읽기 전용). 2026-07-04 시포.
// ═══════════════════════════════════════════
var RENTBIZ_GID = { rent: 2014877540, biz: 1356708303 };  // FORM_SHEETS 공간렌트·비즈니스파트너 gid와 동일(단일 출처)

// 대상(type) → gid 해석. 'biz'/'business'/'비즈니스'/'비즈니스파트너'만 비즈니스, 그 외(미지정 포함)=공간렌트.
function _rentbizGidOf_(body) {
  var t = String((body && body.type) || '').trim().toLowerCase();
  if (t === 'biz' || t === 'business' || t === '비즈니스' || t === '비즈니스파트너') return RENTBIZ_GID.biz;
  return RENTBIZ_GID.rent;
}

// 구글폼 원본 응답탭 + 자체폼 신규 intake 탭('공간렌트 문의'/'비즈니스 문의') 병합 읽기.
//   2026-07-18 시포 — 자체폼 rental/business 저장분이 신규 탭에 쌓이나 rentbiz_inquiry_list가 옛 gid만 읽어 현황 미표시되던 갭 수리.
//   두 소스 동일 SS(_MI_SS_ID===MEMBER_SPREADSHEET_ID). intake 탭은 gid로 재읽어(_rentbizReadRows_ 유연 컬럼) 동일 스키마 반환. 소스가 달라 중복 없음(구글폼 vs 자체폼).
function _rentbizReadRowsMerged_(body) {
  var rows = _rentbizReadRows_(_rentbizGidOf_(body));
  try {
    var t = String((body && body.type) || '').trim().toLowerCase();
    var isBiz = (t === 'biz' || t === 'business' || t === '비즈니스' || t === '비즈니스파트너');
    var iSh = isBiz ? _businessIntakeSheet_(false) : _rentalIntakeSheet_(false);
    if (iSh) rows = rows.concat(_rentbizReadRows_(iSh.getSheetId()));
  } catch (e) {}
  return rows;
}

// 응답탭 시트 핸들 — 멤버십과 동일 스프레드시트(MEMBER_SPREADSHEET_ID)의 gid 매칭(탭명 변경에 강함).
function _rentbizSheet_(gid) {
  return _sheetByGid_(MEMBER_SPREADSHEET_ID, gid);
}

// 문의 행 배열 — 유연 컬럼탐지(_findCol_ 재사용). 구글폼 원본 그대로 읽음(관리 컬럼 추가·쓰기 없음 — 읽기 전용 패널).
//   시트 헤더가 폼마다 다를 수 있어 성함/단체명·연락처·문의내용·상태·타임스탬프 모두 유연 매칭. 빈 행(이름·연락처 둘 다 없음) 스킵.
function _rentbizReadRows_(gid) {
  var sh = _rentbizSheet_(gid);
  if (!sh) return [];
  var lastCol = sh.getLastColumn();
  if (lastCol < 1) return [];
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  var last = sh.getLastRow();
  if (last < 2) return [];
  var data = sh.getRange(2, 1, last - 1, lastCol).getValues();
  var iTs    = _findCol_(hdr, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '날짜']);
  var iName  = _findCol_(hdr, ['성함', '이름', '성명', '단체명', '업체명', '상호', '회사명', '담당자']);
  var iPhone = _findCol_(hdr, ['연락처', '전화', '휴대폰']);
  var iChan  = _findCol_(hdr, ['경로', '채널', '알게']);
  var iNote  = _findCol_(hdr, INQUIRY_CONTENT_KEYS);
  var iStat  = _findCol_(hdr, ['진행상태', '진행현황', '진행상황', '진행 상황', '상태']);
  var iOwner = _findCol_(hdr, ['접수 담당자', '관리담당', '담당자', '담당']);
  var out = [];
  for (var r = 0; r < data.length; r++) {
    var row = data[r];
    var hasName  = iName  >= 0 && row[iName];
    var hasPhone = iPhone >= 0 && row[iPhone];
    if (!hasName && !hasPhone) continue;  // 완전 빈 행 스킵
    out.push({
      rowIndex: r + 2,
      timestamp: _miToISOTime_(iTs >= 0 ? row[iTs] : ''),   // 시각 보존(2026-07-24 시포·GM · 멤버십과 동일 규칙)
      name:    iName  >= 0 ? String(row[iName]  || '') : '',
      phone:   iPhone >= 0 ? _fmtPhone_(row[iPhone]) : '',
      channel: iChan  >= 0 ? String(row[iChan]  || '') : '',
      note:    iNote  >= 0 ? String(row[iNote]  || '') : '',
      status:  iStat  >= 0 ? String(row[iStat]  || '') : '',
      owner:   iOwner >= 0 ? String(row[iOwner] || '') : ''
    });
  }
  return out;
}

// 진행상태 칼럼 존재 여부만 별도 확인(집계 정직성용) — 컬럼 자체가 없으면 상태별 집계를 아예 반환하지 않는다(0 날조 금지).
function _rentbizHasStatusCol_(gid) {
  var sh = _rentbizSheet_(gid);
  if (!sh) return false;
  var lastCol = sh.getLastColumn();
  if (lastCol < 1) return false;
  var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0];
  return _findCol_(hdr, ['진행상태', '진행현황', '진행상황', '진행 상황', '상태']) >= 0;
}

// ★2026-08-03 시토 — 끝난 일회성 정리·이관 액션 은퇴 목록.
//   왜: 이 액션들은 `_intakeToken_` 하나로 열리는데, **그 토큰이 공개 페이지 3곳에 평문으로 박혀 있다**
//   (cmo/survey/wp_inquiry_form.html · wp_inquiry_form_en.html · cpo/member/실무진피드백.html —
//   앞의 둘은 wellperion.com 문의 폼이라 누구나 소스에서 읽을 수 있다).
//   실측(2026-08-03): 그 토큰으로 열리는 액션 38개 중 **22개가 파괴적**이다 — 행 삭제·열 삭제·
//   행 재배열·전화번호 일괄수정·시트 이관. 즉 공개 폼을 연 사람 누구나 회원·강습 시트를 지우거나
//   뒤섞을 수 있는 상태였다.
//   조사 결과 그중 **21개는 2026-07 에 끝난 일회성 작업**이라 살아 있는 호출부가 없다
//   (남은 1개 loss_reason_setup 은 scripts/collectors/cpo_sheet_contract.py 가 쓰므로 제외).
//   → 새 비밀값을 하나 더 만드는 대신 **없앤다**(삭제가 최선의 차단). 되돌리려면 이 목록에서 빼면 된다.
// 2026-08-03 본문 삭제 완료 — 21개 핸들러 블록(+안내주석) 실제 제거. 이 맵·가드는 이름 재사용 차단용으로 유지.
// 2026-08-03 2차 — 저장소 호출부 0인 일회성·진단 액션 41개. 본문은 남겨 뒀다(외부 호출 가능성 소거용 관찰 기간). 살아 있는 호출이 나오면 이 목록에서 빼면 즉시 복구.
var _RETIRED_ACTIONS_ = {
  'clear_lesson_sport_mgmt_residue': 1, 'cpo_clear_wsc_auto_json': 1,
  'cpo_delete_blank_membership_cols': 1, 'cpo_delete_old_lesson_reg': 1,
  'cpo_delete_test_rows_0000': 1, 'cpo_fix_hold_sheet': 1,
  'cpo_lesson_adult_sport_normalize_0721': 1, 'cpo_lesson_clear_filter_0721': 1,
  'cpo_lesson_col_cleanup_0721': 1, 'cpo_lesson_delete_testrow_0721': 1,
  'cpo_lesson_row_reorder_0720': 1, 'cpo_lesson_row_restore_0720': 1,
  'cpo_lesson_test_delete': 1, 'cpo_migrate_intake_to_formtabs': 1,
  'cpo_migrate_lesson_reg': 1, 'cpo_restore_lost_timestamps_0718': 1,
  'cpo_wsc_contact_migrate13': 1, 'member_active_phone_fix': 1,
  'member_hold_intake_migrate': 1, 'migrate_lesson_contact_json_to_plain': 1,
  'migrate_member_reservations_plain_gj': 1,
  'lesson_multisport_split_0825': 1,   // 2026-08-25 강습 다종목 문의 줄 나누기(200건/315줄) — 실행 완료·본문 제거.
  // ↓ 2차 배치(41개) — 호출부 0·자체주석 "일회성/진단/읽기전용"+완료날짜(2026-07-20~22) 프로필. 본문 유지.
  'add_utm_field': 1, 'clear_loss_validation_20260722': 1,
  'clear_orphan_row_20260722': 1, 'consolidate_cols_20260720': 1,
  'cpo_diag_gid_formula': 1,
  'cpo_diag_wsc_legacy_inversions': 1, 'cpo_lesson_sheet_diag_0721': 1,
  'cpo_lesson_sort_verify_0721': 1, 'cpo_lesson_teamsheet_dump': 1,
  'cpo_lesson_teamsheet_formulas': 1, 'cpo_lesson_ts_display_sort_0721': 1,
  'cpo_lesson_ts_fill_0720': 1, 'cpo_lesson_ts_format_0721': 1,
  'cpo_lesson_ts_scan': 1, 'cpo_lesson_ts_scan_boundary': 1,
  'cpo_lesson_unhide_0721': 1, 'cpo_probe_adult_lesson_col0': 1,
  'dedup_autoroute_20260720': 1, 'del_col_by_name_20260720': 1,
  'del_lesson_datecol_20260720': 1, 'del_loss_cols_20260720': 1,
  'del_residence_20260720': 1, 'delete_date_col_20260720': 1,
  'delete_lesson_sheet_20260722': 1, 'diag_exec_identity_20260720': 1,
  'diag_form_link_20260720': 1, 'finalize_cols_20260720': 1,
  'finish_slot4_20260720': 1, 'fix_inquiry_channel_20260720': 1,
  'fix_ts_display_move_20260720': 1, 'member_col_cleanup_20260722': 1,
  'migrate_en_youth_to_main_20260722': 1, 'migrate_slot4_20260720': 1,
  'move_freetext_g_20260720': 1, 'naver_split_midcat': 1,
  'normalize_slot_time_20260720': 1, 'read_col_validation': 1,
  'read_rows_by_rownum': 1, 'list_lesson_sheets': 1,
  'set_col_hidden_20260722': 1, 'sort_tail_by_ts_20260720': 1
};

function _processAction(body) {
  const action = body.action || '';
  // 은퇴 액션은 토큰이 맞아도 실행하지 않는다(위 주석 참조 — 공개 토큰으로 열리던 파괴 경로 차단).
  if (_RETIRED_ACTIONS_[action]) {
    return _json({ ok: false, error: 'retired',
                   detail: '끝난 일회성 정리 작업이라 은퇴했습니다(2026-08-03). 필요하면 시토에게 요청하세요.' });
  }
  // nocache=1 → 캐시 읽기 우회(강제 재계산·재캐싱). 워머 트리거가 캐시를 미리 데우는 용도(2026-06-19 시토).
  var _nc = (body.nocache === '1');
  // ─── 접근 게이트 확인 ───
  if (!_checkSurveyAccess_(action, body.key)) {
    return _json({ ok: false, error: 'unauthorized' });
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

  // ─── [일회용] 문의 시트 공개 전환(gviz 직접읽기 성능개선 전제 — GM go 2026-07-08, 시토). ───
  //   멤버십('26년 신규문의' 소속 SS)·강습(성인·유소년 소속 SS) 스프레드시트를 "링크 있는 누구나 보기(읽기전용)"로 전환.
  //   멱등(이미 공개면 재적용해도 무해) — 배포 후 1회 호출로 실행. 다시 부를 필요 없음.
  //   ⚠️ 역롤백(공유 해제): 구글 드라이브에서 해당 파일 → 공유 → '일반 액세스'를 '제한됨'으로 변경(1초, 재배포 불필요).
  if (action === 'share_inquiry_sheets') {
    var _shareTargets = [_MI_SS_ID, LESSON_SS_ID];  // 멤버십 SS + 강습 SS(성인·유소년 탭 공용 SS)
    var _shareResults = [];
    _shareTargets.forEach(function(ssId) {
      try {
        var f = DriveApp.getFileById(ssId);
        f.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
        _shareResults.push({ ssId: ssId, name: f.getName(), ok: true, access: String(f.getSharingAccess()), permission: String(f.getSharingPermission()) });
      } catch (e) {
        _shareResults.push({ ssId: ssId, ok: false, error: e.message });
      }
    });
    return _json({ ok: _shareResults.every(function(r){ return r.ok; }), results: _shareResults });
  }

  // ─── onFormSubmit 트리거 + 폴링 백스톱 설치 (2026-06-25 시모) ───
  if (action === 'install_inquiry_triggers') {
    try {
      var installResults = installInquiryFormSubmitTriggers();
      return _json({ ok: true, results: installResults });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // [2026-07-27 시모] 봇 토큰 주입 경로는 사용 즉시 제거됨(@158에서 1회 사용·hasToken=true 확인).
  //   공개 엔드포인트에 쓰기 경로를 남기지 않는다. 재발급 등으로 다시 필요하면 그때 1회용으로
  //   다시 만들고 쓰자마자 지운다 — 상시 노출 금지.

  // ─── 알림 설정 보유 확인 (값은 절대 반환하지 않음 — 존재 여부 불리언만) ───
  // [2026-07-27 시모] scripts/telegram_health_check.py 의 _check_gas_diag 는 VOC·점검 GAS 에서
  //   hasToken/hasChatId 를 받아 '설정 누락'을 잡는데, Survey(퍼널) GAS 만 이 진단이 없어
  //   bool_fields 가 비어 있었다 — 즉 문의 알림 백엔드의 토큰·방 설정이 빠져도 아무도 몰랐다.
  //   같은 계약(hasToken/hasChatId)을 여기에도 채워 기존 헬스체크가 그대로 판정하게 한다.
  //   ※ 토큰·chat_id 실값은 반환하지 않는다(공개 엔드포인트 — 존재 여부만).
  if (action === 'diag_notify_config') {
    try {
      var _dTok = _prop('BOT_TOKEN') || _prop('TELEGRAM_BOT_TOKEN') || '';
      var _dChat = _prop('TELEGRAM_INQUIRY_CHAT_ID') || '';
      return _json({
        ok: true,
        hasToken: !!_dTok,
        hasChatId: !!(_dChat || _INQUIRY_CHAT_ID_FALLBACK),
        chatIdFromProperty: !!_dChat        // false = 코드 폴백값 사용 중
      });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 팀시트 칸 진단 (배155) — 이름·전화·상태 칸을 실제로 찾는지 확인 ───
  //  왜: 팀시트 등록행 2,318 중 735(32%)가 이름·전화 둘 다 빈 채 '등록'으로 잡히고, 원장은
  //      전화가 키라 그 행들이 못 들어간다 → 2026-07-20 이후 신규 강습 등록 0건.
  //      원인 후보 (가)칸 탐색 실패 (나)상태열 오탐지 를 가르려면 실제 헤더를 봐야 한다.
  //  ※ PII 미반환 — 헤더 문자열과 칸 인덱스·행수만.
  if (action === 'diag_team_sheet_headers') {
    try {
      var _dOut = [];
      LESSON_TEAM_SHEETS.forEach(function(cfg){
        var rec = { 명: cfg.명, 유형: cfg.유형, gid: cfg.gid };
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = '시트 없음'; _dOut.push(rec); return; }
          var last = sh.getLastRow(), lastCol = sh.getLastColumn();
          rec.lastRow = last; rec.lastCol = lastCol;
          if (last < 2 || lastCol < 1) { rec.error = '데이터 없음'; _dOut.push(rec); return; }
          var data = sh.getRange(1, 1, last, lastCol).getValues();
          var headers = data[0];
          rec.headers = headers.map(function(h){ return String(h || ''); });
          rec.iName  = _findCol_(headers, ['성함', '이름', '성명']);
          rec.iPhone = _findCol_(headers, ['연락처', '전화', '휴대폰']);
          // 상태열 자동탐지 재현 (_collectLessonRoster_ 와 동일 규칙)
          var best = -1, bestCnt = 0, cand = [];
          for (var c = 0; c < lastCol; c++) {
            var cnt = 0, distinct = {}, dn = 0;
            for (var r = 1; r < data.length; r++) {
              var cv = String(data[r][c] || '').trim();
              if (!cv) continue;
              if (!distinct[cv]) { distinct[cv] = 1; dn++; }
              if (_isLessonStatusVal_(cv)) cnt++;
            }
            if (dn >= 2 && dn <= 30 && cnt > 0) cand.push({ col: c, header: String(headers[c] || ''), sucLike: cnt, distinct: dn });
            if (dn >= 2 && dn <= 30 && cnt > bestCnt) { bestCnt = cnt; best = c; }
          }
          rec.statusCol = best;
          rec.statusHeader = best >= 0 ? String(headers[best] || '') : null;
          rec.statusCandidates = cand;
          // 등록으로 잡히는 행 중 이름·전화가 비는 비율
          var regN = 0, blank = 0;
          if (best >= 0) {
            for (var r2 = 1; r2 < data.length; r2++) {
              if (!_isLessonReg_(data[r2][best])) continue;
              regN++;
              var nm = rec.iName  >= 0 ? String(data[r2][rec.iName]  || '').trim() : '';
              var ph = rec.iPhone >= 0 ? String(data[r2][rec.iPhone] || '').trim() : '';
              if (!nm && !ph) blank++;
            }
          }
          rec.regRows = regN; rec.blankNamePhone = blank;
          // 이름·전화가 빈 '등록' 행에서 칸별로 값이 있는 개수 — 유령행인지(전부 빔),
          // 특정 칸만 비는지(가져오기 실패 등) 가른다. 값 자체는 반환하지 않는다.
          if (best >= 0 && blank > 0) {
            var fill = [];
            for (var c2 = 0; c2 < lastCol; c2++) fill.push(0);
            var samples = [];
            for (var r3 = 1; r3 < data.length; r3++) {
              if (!_isLessonReg_(data[r3][best])) continue;
              var nm2 = rec.iName  >= 0 ? String(data[r3][rec.iName]  || '').trim() : '';
              var ph2 = rec.iPhone >= 0 ? String(data[r3][rec.iPhone] || '').trim() : '';
              if (nm2 || ph2) continue;
              for (var c3 = 0; c3 < lastCol; c3++) {
                if (String(data[r3][c3] || '').trim()) fill[c3]++;
              }
              if (samples.length < 3) samples.push(r3 + 1);   // 시트 행번호(1-base)
            }
            rec.blankRowColFill = fill;      // 칸별로 값이 있던 행 수
            rec.blankRowNumbers = samples;   // 사람이 눈으로 확인할 행번호 3개
          }
        } catch (e3) { rec.error = e3.message; }
        _dOut.push(rec);
      });
      return _json({ ok: true, sheets: _dOut });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 현재 트리거 목록 조회 (핸들러명·타입·소스ID) ───
  if (action === 'list_inquiry_triggers') {
    try {
      var tList = ScriptApp.getProjectTriggers().map(function(t) {
        return {
          handler:  t.getHandlerFunction(),
          type:     t.getEventType().toString(),
          sourceId: (t.getTriggerSourceId ? t.getTriggerSourceId() : null)
        };
      });
      return _json({ ok: true, count: tList.length, triggers: tList });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // diag_warm_stamp_props_0805 — 2026-08-05 시토, 확인 완료(WAIT_RELEASE_LAST/LOSS_DATE_STAMP_LAST 둘 다
  // 2026-08-05로 찍힘 = warmLessonRosterCache 이관 후 정상 발화 확인) 후 회수함. 재추가 금지.

  // ─── onFormSubmit 핸들러 mock 테스트 (실 데이터 행 생성 없음) ───
  // FORM_SHEETS[0](멤버십 시트)을 기준으로 가짜 이벤트 객체를 구성해 onInquiryFormSubmit 경로를 통해
  // 문의알림방에 '[TEST]' 메시지 1건 발송. 실 행수·마커는 변경하지 않음.
  if (action === 'test_form_submit_notify') {
    try {
      var testChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
      var testMsg = '🧪 [TEST] onFormSubmit 즉시알림 경로 작동 확인 — 실제 문의 아님 (2026-06-25 시모)';
      _notifyTelegram(testMsg, testChatId);
      return _json({ ok: true, chat_id: testChatId, message: 'TEST 메시지 발송 완료 — 문의알림방 확인' });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 누락분 수동 발송 — FORM_SHEETS 전체에서 가장 최근 문의 1건 재발송 (2026-06-25 시모) ───
  // INQ_LASTROW 마커 불변. 딱 1건만 발송. 머리에 '[누락분 수동 발송]' 표식.
  // v2: 시트별 break 폐기 → 각 시트 최근 30행 전부 파싱해 전역 타임스탬프 max 1건 선택.
  //     날짜형식 혼재(구글폼 Date, 'YYYY. M. D', 'YYYY-MM-DD HH:mm:ss') 모두 _normTs_ 정규화.
  if (action === 'resend_recent_inquiry') {
    try {
      var rriChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
      var rriCandidates = []; // 전 시트 후보 행 목록 — 타임스탬프 기준 정렬용

      FORM_SHEETS.forEach(function(cfg) {
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) return;
          var lastRow = sh.getLastRow();
          if (lastRow < 2) return;
          var lastCol = sh.getLastColumn();
          if (lastCol < 1) return;
          var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
          var idxDate  = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
          var idxName  = _findCol_(headers, ['성함', '이름', 'Full Name', 'Name', "Child's Full Name"]);
          var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화', 'Mobile Phone', 'Phone', "Guardian's Mobile Phone"]);
          var idxChan  = _findCol_(headers, cfg.channelKeys || ['채널', '경로', '알게', 'How Did You Hear']);
          var idxMemo  = _findCol_(headers, ['비고', '메모']);

          // 최근 200행 일괄 읽기 — 시트 끝에 빈 행이 대량 존재할 수 있어 30행으론 부족
          var readStart = Math.max(2, lastRow - 199);
          var readCount = lastRow - readStart + 1;
          var allRows = sh.getRange(readStart, 1, readCount, lastCol).getValues();

          for (var ri = 0; ri < allRows.length; ri++) {
            var r = allRows[ri];
            var rowNum = readStart + ri;
            // [웹접수] 미러 행 제외
            if (idxMemo >= 0 && String(r[idxMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) continue;
            // 실데이터 판별: 전화번호 OR 타임스탬프 중 하나라도 있으면 실 행
            var hasTs    = idxDate >= 0 ? !!r[idxDate] : false;
            var hasPhone = idxPhone >= 0 && !!r[idxPhone];
            if (!hasTs && !hasPhone) continue;

            var ts = idxDate >= 0 ? r[idxDate] : '';
            var tsDate = null;
            var tsStr = '';
            try {
              var d = _normTs_(ts);
              if (!isNaN(d.getTime())) {
                tsDate = d;
                tsStr = Utilities.formatDate(d, 'Asia/Seoul', 'MM/dd HH:mm');
              } else {
                tsStr = String(ts).substring(0, 16);
              }
            } catch (ex) { tsStr = String(ts).substring(0, 16); }

            var name  = (idxName  >= 0 ? String(r[idxName]  || '').trim() : '') || '-';
            var phone = (idxPhone >= 0 ? String(r[idxPhone] || '').trim() : '') || '-';
            var chan  = (idxChan  >= 0 ? String(r[idxChan]  || '').trim() : '') || '-';

            rriCandidates.push({
              ts:        tsDate,          // Date or null
              tsMs:      tsDate ? tsDate.getTime() : 0,
              tsStr:     tsStr,
              type:      cfg.type,
              sheetName: sh.getName(),
              row:       rowNum,
              name:      name,
              phone:     phone,
              chan:       chan
            });
          }
        } catch (e2) { /* 시트 접근 실패 무시 */ }
      });

      if (rriCandidates.length === 0) return _json({ ok: false, error: '발송 가능한 문의 행 없음' });

      // 타임스탬프 내림차순 정렬 — null(파싱실패)은 맨 뒤로
      rriCandidates.sort(function(a, b) {
        if (!a.ts && !b.ts) return 0;
        if (!a.ts) return 1;
        if (!b.ts) return -1;
        return b.tsMs - a.tsMs;
      });

      var best = rriCandidates[0];
      var msg = '🗂 [누락분 수동 발송]\n'
        + '유형: ' + best.type + '\n'
        + '이름: ' + best.name + '\n'
        + '연락처: ' + best.phone + '\n'
        + '유입채널: ' + best.chan + '\n'
        + '시각: ' + best.tsStr;

      _notifyTelegram(msg, rriChatId);

      // 진단용 top3 (시트·시각만)
      var top3 = rriCandidates.slice(0, 3).map(function(c) {
        return { type: c.type, sheet: c.sheetName, row: c.row, ts: c.tsStr };
      });

      return _json({
        ok:        true,
        chat_id:   rriChatId,
        sent_type: best.type,
        sent_sheet:best.sheetName,
        sent_row:  best.row,
        sent_ts:   best.tsStr,
        sent_msg:  msg,
        top3:      top3
      });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 누락분 진단 — FORM_SHEETS 시트별 마지막 실데이터 행(역순 최대 200행 탐색) 반환 (2026-06-25) ───
  if (action === 'diag_inquiry_ts') {
    try {
      var diagOut = [];
      FORM_SHEETS.forEach(function(cfg) {
        var rec = { ssId: cfg.ssId, gid: cfg.gid, type: cfg.type, sheet: null, lastRow: 0, latestDataRow: null, error: null };
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = 'sheet_not_found'; diagOut.push(rec); return; }
          rec.sheet = sh.getName();
          var lastRow = sh.getLastRow();
          rec.lastRow = lastRow;
          if (lastRow < 2) { diagOut.push(rec); return; }
          var lastCol = sh.getLastColumn();
          var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
          rec.headers = headers.slice(0, 10).map(function(h){ return String(h||'').trim(); });
          var idxDate = _findCol_(headers, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
          var idxName = _findCol_(headers, ['성함', '이름', 'Full Name', 'Name', "Child's Full Name"]);
          var idxPhone = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화', 'Mobile Phone', 'Phone', "Guardian's Mobile Phone"]);
          var idxMemo = _findCol_(headers, ['비고', '메모']);
          rec.idxDate = idxDate; rec.idxPhone = idxPhone;
          // 역순으로 최대 200행 탐색해 실데이터 행 찾기 (빈행 스킵 조건: date AND phone 모두 없는 경우만)
          var readStart = Math.max(2, lastRow - 199);
          var rows = sh.getRange(readStart, 1, lastRow - readStart + 1, lastCol).getValues();
          for (var ri = rows.length - 1; ri >= 0; ri--) {
            var r = rows[ri];
            var rowNum = readStart + ri;
            if (idxMemo >= 0 && String(r[idxMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) continue;
            var raw = idxDate >= 0 ? r[idxDate] : r[0];  // idxDate 못 찾으면 1열로 폴백
            var hasPhone = idxPhone >= 0 && r[idxPhone];
            if (!raw && !hasPhone) continue;  // 타임스탬프·전화번호 둘 다 없을 때만 빈 행 처리
            var tsStr = '';
            try {
              var d = _normTs_(raw);
              tsStr = !isNaN(d.getTime()) ? Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : ('파싱실패:' + String(raw).substring(0, 30));
            } catch(ex) { tsStr = 'error'; }
            rec.latestDataRow = { row: rowNum, rawTs: String(raw).substring(0, 40), isDate: raw instanceof Date, parsed: tsStr, name: idxName >= 0 ? String(r[idxName]||'').substring(0,15) : '', col0: String(r[0]||'').substring(0,20) };
            break;
          }
        } catch(e2) { rec.error = e2.message; }
        diagOut.push(rec);
      });
      return _json({ ok: true, sheets: diagOut });
    } catch(e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 진단(읽기전용): 마커값·실데이터행·트리거목록 (2026-06-25 시모) ───
  // sendMessage 절대 미포함. 쓰기 없음. INQ_LASTROW 변경 없음.
  if (action === 'diag_inquiry_state') {
    try {
      var props = PropertiesService.getScriptProperties();
      var dsOut = [];
      FORM_SHEETS.forEach(function(cfg) {
        var propKey = 'INQ_LASTROW_' + cfg.ssId + '_' + cfg.gid;
        var markerVal = props.getProperty(propKey);
        var rec = {
          type: cfg.type, ssId: cfg.ssId, gid: cfg.gid,
          marker_key: propKey,
          marker_value: markerVal,          // INQ_LASTROW 현재 저장값 (null=미설정)
          sheet_lastRow: null,              // sh.getLastRow() — 빈행 포함
          real_lastDataRow: null,           // 전화번호 기준 실데이터 마지막 행번호
          real_lastDataTs: null,            // 그 행의 타임스탬프 문자열
          gap: null,                        // sheet_lastRow - real_lastDataRow (빈행 수)
          marker_vs_real: null,             // marker - real_lastDataRow (양수=마커가 앞섬→신규행 스킵)
          sheet: null, error: null
        };
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = 'sheet_not_found'; dsOut.push(rec); return; }
          rec.sheet = sh.getName();
          var lastRow = sh.getLastRow();
          rec.sheet_lastRow = lastRow;
          if (lastRow < 2) { dsOut.push(rec); return; }
          var lastCol = sh.getLastColumn();
          var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
          var idxDate  = _findCol_(headers, ['타임스탬프','timestamp','시각','일시','접수일','접수','날짜']);
          var idxPhone = _findCol_(headers, ['연락처','휴대폰','핸드폰','전화','Mobile Phone','Phone',"Guardian's Mobile Phone"]);
          var idxMemo  = _findCol_(headers, ['비고','메모']);
          // 역순 최대 500행 탐색 — 빈행이 수백 개여도 실데이터 찾음
          var readStart = Math.max(2, lastRow - 499);
          var rows = sh.getRange(readStart, 1, lastRow - readStart + 1, lastCol).getValues();
          for (var ri = rows.length - 1; ri >= 0; ri--) {
            var r = rows[ri];
            var rowNum = readStart + ri;
            if (idxMemo >= 0 && String(r[idxMemo]||'').indexOf(WEB_INTAKE_TAG) >= 0) continue;
            var hasTs    = idxDate  >= 0 && !!r[idxDate];
            var hasPhone = idxPhone >= 0 && !!r[idxPhone];
            if (!hasTs && !hasPhone) continue;
            var raw = idxDate >= 0 ? r[idxDate] : r[0];
            var tsStr = '';
            try {
              var d = _normTs_(raw);
              tsStr = !isNaN(d.getTime())
                ? Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
                : ('파싱실패:' + String(raw).substring(0, 30));
            } catch(ex) { tsStr = String(raw).substring(0, 30); }
            rec.real_lastDataRow = rowNum;
            rec.real_lastDataTs  = tsStr;
            break;
          }
          rec.gap = rec.real_lastDataRow !== null ? (lastRow - rec.real_lastDataRow) : null;
          rec.marker_vs_real = (rec.real_lastDataRow !== null && markerVal !== null)
            ? (parseInt(markerVal, 10) - rec.real_lastDataRow) : null;
        } catch(e2) { rec.error = e2.message; }
        dsOut.push(rec);
      });
      // 트리거 목록
      var triggers = ScriptApp.getProjectTriggers().map(function(t) {
        return {
          handler:  t.getHandlerFunction(),
          type:     t.getEventType().toString(),
          sourceId: (t.getTriggerSourceId ? t.getTriggerSourceId() : null)
        };
      });
      return _json({ ok: true, sheets: dsOut, triggers: triggers });
    } catch(e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 읽기전용: 지정 시트 gid + 행번호 목록의 알림 필드 원문 반환 (2026-06-25) ───
  // 파라미터: gid(숫자), rows(쉼표구분 행번호, 예 "3491,4522"), ssId(선택)
  // sendMessage 절대 없음. 마커 변경 없음.
  if (action === 'read_rows_by_rownum') {
    try {
      var rrbGid    = parseInt(body.gid, 10);
      var rrbRows   = String(body.rows || '').split(',').map(function(s){ return parseInt(s.trim(), 10); }).filter(function(n){ return !isNaN(n); });
      var rrbSsId   = body.ssId || null;
      if (!rrbGid || rrbRows.length === 0) return _json({ ok: false, error: 'gid·rows 필수' });

      // FORM_SHEETS에서 gid 일치 cfg 탐색
      var rrbCfg = null;
      for (var i = 0; i < FORM_SHEETS.length; i++) {
        if (FORM_SHEETS[i].gid === rrbGid && (!rrbSsId || FORM_SHEETS[i].ssId === rrbSsId)) {
          rrbCfg = FORM_SHEETS[i]; break;
        }
      }
      if (!rrbCfg) return _json({ ok: false, error: 'gid 매칭 없음: ' + rrbGid });

      var sh = _sheetByGid_(rrbCfg.ssId, rrbCfg.gid);
      if (!sh) return _json({ ok: false, error: 'sheet_not_found' });

      var lastCol = sh.getLastColumn();
      var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0];
      var idxDate  = _findCol_(headers, ['타임스탬프','timestamp','시각','일시','접수일','접수','날짜']);
      var idxName  = _findCol_(headers, ['성함','이름','Full Name','Name',"Child's Full Name"]);
      var idxPhone = _findCol_(headers, ['연락처','휴대폰','핸드폰','전화','Mobile Phone','Phone',"Guardian's Mobile Phone"]);
      var idxChan  = _findCol_(headers, rrbCfg.channelKeys || ['채널','경로','알게','How Did You Hear']);

      var rrbOut = rrbRows.map(function(rowNum) {
        try {
          var r = sh.getRange(rowNum, 1, 1, lastCol).getValues()[0];
          var raw = idxDate >= 0 ? r[idxDate] : r[0];
          var tsStr = '';
          try {
            var d = _normTs_(raw);
            tsStr = !isNaN(d.getTime()) ? Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(raw).substring(0, 30);
          } catch(ex) { tsStr = String(raw || '').substring(0, 30); }
          var rrbRet = {
            row:      rowNum,
            type:     rrbCfg.type,
            name:     idxName  >= 0 ? String(r[idxName]  || '').trim() : '',
            phone:    idxPhone >= 0 ? String(r[idxPhone] || '').trim() : '',
            channel:  idxChan  >= 0 ? String(r[idxChan]  || '').trim() : '',
            ts:       tsStr
          };
          // full=1 이면 모든 칸을 헤더명과 함께 돌려준다(읽기 전용·발송 0).
          //   왜: 4칸만으로는 이 문의가 어느 경로로 들어왔는지 못 가린다. 자체폼 유입은
          //   '접수 담당자=웹 자동접수' / '유입경로(자동)=utm' / '비고=[웹접수]' 흔적을 남기는데
          //   그 칸이 응답에 없어 매번 사람이 시트를 열어야 했다(GM 2026-07-27 질문에 근거로 답 못 한 이유).
          if (String(body.full || '') === '1') {
            var rrbAll = {};
            for (var hc = 0; hc < lastCol; hc++) {
              var hk = String(headers[hc] || ('col' + hc)).substring(0, 40);
              rrbAll[hk] = String(r[hc] === null || r[hc] === undefined ? '' : r[hc]).substring(0, 120);
            }
            rrbRet.all = rrbAll;
          }
          return rrbRet;
        } catch(e2) { return { row: rowNum, error: e2.message }; }
      });
      return _json({ ok: true, type: rrbCfg.type, rows: rrbOut });
    } catch(e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 읽기전용: 지정 행의 알림 메시지 텍스트 미리보기(발송 0) (2026-06-25) ───
  // 파라미터: gid(숫자), rows(쉼표구분 행번호). UrlFetchApp 미호출, sendMessage 없음.
  if (action === 'preview_notify_msg') {
    try {
      var pvGid  = parseInt(body.gid, 10);
      var pvRows = String(body.rows || '').split(',').map(function(s){ return parseInt(s.trim(),10); }).filter(function(n){ return !isNaN(n); });
      if (!pvGid || pvRows.length === 0) return _json({ ok: false, error: 'gid·rows 필수' });

      var pvCfg = null;
      for (var i = 0; i < FORM_SHEETS.length; i++) {
        if (FORM_SHEETS[i].gid === pvGid) { pvCfg = FORM_SHEETS[i]; break; }
      }
      if (!pvCfg) return _json({ ok: false, error: 'gid 매칭 없음: ' + pvGid });

      var pvSh = _sheetByGid_(pvCfg.ssId, pvCfg.gid);
      if (!pvSh) return _json({ ok: false, error: 'sheet_not_found' });

      var pvLastCol = pvSh.getLastColumn();
      var pvHdrs   = pvSh.getRange(1, 1, 1, pvLastCol).getValues()[0];
      var pvIdxDate  = _findCol_(pvHdrs, ['타임스탬프','timestamp','시각','일시','접수일','접수','날짜']);
      var pvIdxName  = _findCol_(pvHdrs, ['성함','이름','Full Name','Name',"Child's Full Name"]);
      var pvIdxPhone = _findCol_(pvHdrs, ['연락처','휴대폰','핸드폰','전화','Mobile Phone','Phone',"Guardian's Mobile Phone"]);
      var pvIdxChan  = _findCol_(pvHdrs, pvCfg.channelKeys || ['채널','경로','알게','How Did You Hear']);
      var pvIdxProg  = _findCol_(pvHdrs, pvCfg.programKeys || ['종목','프로그램','과목','Program']);
      var pvIdxContent = _findCol_(pvHdrs, INQUIRY_CONTENT_KEYS);  // 문의 내용 칸 — GM 2026-06-29 시토

      var pvOut = pvRows.map(function(rowNum) {
        try {
          var r = pvSh.getRange(rowNum, 1, 1, pvLastCol).getValues()[0];
          var raw = pvIdxDate >= 0 ? r[pvIdxDate] : r[0];
          var tsStr = '';
          try {
            var d = _normTs_(raw);
            tsStr = !isNaN(d.getTime()) ? Utilities.formatDate(d, 'Asia/Seoul', 'MM/dd HH:mm') : String(raw||'').substring(0,16);
          } catch(ex) { tsStr = String(raw||'').substring(0,16); }

          var name  = (pvIdxName  >= 0 ? String(r[pvIdxName]  ||'').trim() : '') || '-';
          var phone = (pvIdxPhone >= 0 ? String(r[pvIdxPhone] ||'').trim() : '') || '-';
          var chan  = (pvIdxChan  >= 0 ? String(r[pvIdxChan]  ||'').trim() : '') || '-';
          var prog  = (pvIdxProg  >= 0 ? String(r[pvIdxProg]  ||'').trim() : '');

          var content = pvIdxContent >= 0 ? String(r[pvIdxContent] || '').trim() : '';
          if (content.length > 300) content = content.substring(0, 300) + '…';
          var msg = '📥 [자체폼 외 유입] 🔔 [신규 문의 — 즉시]\n'
            + '유형: ' + pvCfg.type + '\n'
            + (prog ? '종목: ' + _teamChip(prog) + prog + '\n' : '')
            + '이름: ' + name + '\n'
            + '연락처: ' + phone + '\n'
            + '유입채널: ' + chan
            + (content ? '\n내용: ' + content : '');

          // 미리보기는 실제 발송 경로와 같은 제외 판정을 거쳐야 한다 — 안 거치면 '보내지 않을 것'을
          // 보여줘 검증이 거짓이 된다(2026-07-27 실측으로 드러남).
          return { row: rowNum, msg: msg, prog_col_found: pvIdxProg >= 0,
                   excluded: _isWebIntakeRow_(r, pvHdrs),
                   excluded_reason: _isWebIntakeRow_(r, pvHdrs) ? '자체폼 접수분(접수 알림은 intake_submit 담당)' : '' };
        } catch(e2) { return { row: rowNum, error: e2.message }; }
      });
      return _json({ ok: true, previews: pvOut });
    } catch(e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 마커 교정(발송 0): 각 시트 실데이터 마지막 행으로 INQ_LASTROW 덮어씀 (2026-06-25) ───
  // sendMessage 절대 미포함. 읽기+ScriptProperties 쓰기만.
  if (action === 'reset_inquiry_markers') {
    try {
      var props = PropertiesService.getScriptProperties();
      var rmOut = [];
      FORM_SHEETS.forEach(function(cfg) {
        var propKey = 'INQ_LASTROW_' + cfg.ssId + '_' + cfg.gid;
        var rec = { type: cfg.type, ssId: cfg.ssId, gid: cfg.gid, before: null, after: null, error: null };
        try {
          rec.before = props.getProperty(propKey);
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = 'sheet_not_found'; rmOut.push(rec); return; }
          var lastCol = sh.getLastColumn();
          var hdrs = lastCol > 0 ? sh.getRange(1, 1, 1, lastCol).getValues()[0] : [];
          var iP = _findCol_(hdrs, ['연락처','휴대폰','핸드폰','전화','Mobile Phone','Phone',"Guardian's Mobile Phone"]);
          var iD = _findCol_(hdrs, ['타임스탬프','timestamp','시각','일시','접수일','접수','날짜']);
          var iM = _findCol_(hdrs, ['비고','메모']);
          var realRow = _realLastDataRow_(sh, iP, iD, iM);
          props.setProperty(propKey, String(realRow));
          rec.after = realRow;
        } catch(e2) { rec.error = e2.message; }
        rmOut.push(rec);
      });
      return _json({ ok: true, results: rmOut });
    } catch(e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 읽기전용: 특정 시각 이후 신규 실데이터 행 건수 집계 (2026-06-25) ───
  // 발송 0. 파라미터: since=YYYY-MM-DDTHH:MM (KST, 예 2026-06-25T16:23)
  if (action === 'count_missed_inquiries') {
    try {
      var sinceStr = body.since || '';
      var sinceDate = sinceStr ? new Date(sinceStr.replace('T', ' ').replace(' ', 'T').indexOf('+') >= 0 ? sinceStr : sinceStr + '+09:00') : null;
      var cmOut = [];
      FORM_SHEETS.forEach(function(cfg) {
        var rec = { type: cfg.type, gid: cfg.gid, count: 0, rows: [], error: null };
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = 'sheet_not_found'; cmOut.push(rec); return; }
          var lastRow = sh.getLastRow();
          if (lastRow < 2) { cmOut.push(rec); return; }
          var lastCol = sh.getLastColumn();
          var hdrs = sh.getRange(1, 1, 1, lastCol).getValues()[0];
          var iD = _findCol_(hdrs, ['타임스탬프','timestamp','시각','일시','접수일','접수','날짜']);
          var iP = _findCol_(hdrs, ['연락처','휴대폰','핸드폰','전화','Mobile Phone','Phone',"Guardian's Mobile Phone"]);
          var iM = _findCol_(hdrs, ['비고','메모']);
          var iN = _findCol_(hdrs, ['성함','이름','Full Name','Name',"Child's Full Name"]);
          // 역순 최대 300행 탐색
          var readStart = Math.max(2, lastRow - 299);
          var rows = sh.getRange(readStart, 1, lastRow - readStart + 1, lastCol).getValues();
          for (var ri = rows.length - 1; ri >= 0; ri--) {
            var r = rows[ri];
            if (iM >= 0 && String(r[iM]||'').indexOf(WEB_INTAKE_TAG) >= 0) continue;
            var hasPhone = iP >= 0 && !!r[iP];
            var hasTs    = iD >= 0 && !!r[iD];
            if (!hasPhone && !hasTs) continue;
            var raw = iD >= 0 ? r[iD] : null;
            var d = raw ? _normTs_(raw) : null;
            if (sinceDate && (!d || isNaN(d.getTime()) || d < sinceDate)) continue;
            var tsStr = (d && !isNaN(d.getTime())) ? Utilities.formatDate(d, 'Asia/Seoul', 'MM/dd HH:mm') : String(raw||'').substring(0,16);
            rec.count++;
            if (rec.rows.length < 10) rec.rows.push({ row: readStart + ri, ts: tsStr, name: iN >= 0 ? String(r[iN]||'').substring(0,10) : '' });
          }
        } catch(e2) { rec.error = e2.message; }
        cmOut.push(rec);
      });
      var total = cmOut.reduce(function(s, r){ return s + r.count; }, 0);
      return _json({ ok: true, since: sinceStr, total: total, sheets: cmOut });
    } catch(e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── 문의 접수 ───
  if (action === 'submit_inquiry') {
    // QA 격리(배195) — qa=1+토큰 일치 시 전용 탭(QA_INQUIRY_SHEET)에만 쓰고, 실무진 미러·
    // 텔레그램 발송은 아예 안 탄다(그게 새 실서비스 코드경로가 아니라 '안 부르기'라 회귀위험 0).
    // 일반 방문자는 qa 파라미터 자체를 안 보내므로 이 분기에 절대 안 걸린다.
    const _isQa = _isQaInquiryCall_(body);
    const sh = _getSheet(_isQa ? QA_INQUIRY_SHEET : INQUIRY_SHEET, INQUIRY_HEADERS);
    const id = _genId(_isQa ? 'QA-' : 'INQ-');
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

    if (!_isQa) {
      // GM A안(2026-06-20): 실무진 처리 화면(문의DB=26년 신규문의)에도 미러 기록 → 즉시 처리 가능. fail-soft.
      _mirrorInquiryToStaffLog_(body, id);

      _notifyTelegram(
        (_isTestInquiryName_(body.name) ? '🧪 <b>[테스트 문의 — 업무보고방으로 자동전환]</b>\n' : '🔔 <b>[신규 문의]</b>\n')
        + '이름: ' + (body.name || '-') + '\n'
        + '연락처: ' + (body.phone || '-') + '\n'
        + '유형: ' + (body.type || '-') + '\n'
        + '유입채널: ' + (body.inflow || '-') + '\n'
        + '내용: ' + (body.message || '-').substring(0, 100),
        _inquiryNotifyChatId_(body.name, _prop('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK)
      );
    }

    return _json({ ok: true, id: id, message: '문의가 접수되었습니다.', qa: _isQa });
  }

  // ─── 유입 자체 Survey 폼 제출 (배1037 갈래B · 시포 2026-07-15) ───
  //   멤버십→'26년 신규문의'(_miSheet_·member_inquiry_list 자동정합) / 강습→신규 '강습 신규문의' 스태프탭(lesson_inquiry_list 병합 자동정합).
  //   수집 유실 0: 멱등 submissionId(Cache dedup) + 서버 재검증. 저장 실패는 재시도가능(noRetry 미설정) 응답 → 프론트 대기큐 재전송.
  //   스팸방어(구글폼 캡차 상실 보상): 토큰 · 허니팟 · 타이밍 게이트 · 레이트리밋. WEB_INTAKE_TAG로 마케팅 집계 이중계상 방지.
  if (action === 'intake_submit') {
    // 1) 토큰(위조방지)
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    // 2) 스팸 방어(허니팟)는 버리지 않는다 — ★근본 원칙(2026-07-24 GM 지시).
    //    이전엔 허니팟(hp)에 값이 있으면 봇으로 보고 접수를 버린 뒤 '접수 보류함' 탭에 담았다. 그건
    //    일이 잘못된 뒤 주워담는 사후 안전망일 뿐, 애초에 사람을 잃지 않게 하는 근본 셋팅이 아니다.
    //    hp 는 화면 밖 숨김칸이지만 브라우저 자동완성·비밀번호 관리자가 사람 폼에서 잘못 채울 수 있다 →
    //    버리는 순간 그 고객이 사라진다. 그래서 '버림+보류함'을 폐기하고, 아래 타이밍 게이트와 똑같이
    //    '정상 저장 + 비고 ⚠️스팸의심 표시'로 통일한다. 실무진이 목록에서 표시를 보고 봇이면 지운다 —
    //    사람 유실 0, 관리할 별도 탭 0. (봇 소량 유입 < 실고객 1명 유실, 이미 검증된 정책)
    var _iHpFlag = (String(body.hp || '').trim() !== '');
    if (_iHpFlag) { try { Logger.log('[intake honeypot flagged] phone=' + String(body.phone || '')); } catch (e) {} }
    // 3) 타이밍 게이트 — 너무 빠른 제출은 봇 의심이나 자동완성 등 정상 사용자 오탐 가능 → #2(2026-07-18 시포): 조용히 버리지 않고 저장하되 '검토' 플래그(비고)로 표면화(실사용자 유실 0).
    var _fillMs = parseInt(body.fillMs || '0', 10);
    var _iFastFlag = (_fillMs > 0 && _fillMs < 1500);
    // 스팸 의심(허니팟·빠른제출) 통합 표시 문자열 — 있으면 각 카테고리 비고에 붙인다(카테고리 무관 동일 표기).
    var _iReviewFlag = ((_iFastFlag ? '⚠️빠른제출 ' : '') + (_iHpFlag ? '⚠️스팸의심 ' : '')).trim();
    // 4) 멱등 — submissionId 최근 처리 마커 있으면 기존 결과 반환(재시도로 인한 중복행 방지)
    var _iCache = CacheService.getScriptCache();
    var _sid = String(body.submissionId || '').slice(0, 64);
    if (_sid) {
      var _prev = _iCache.get('intake_sid_' + _sid);
      if (_prev) return _json({ ok: true, id: _prev, submissionId: _sid, dedup: true });
    }
    // 5) 서버측 재검증(프론트 우회 방어)
    var _iName = String(body.name || '').trim();
    var _iPhone = String(body.phone || '').trim();
    var _iPhoneDigits = _iPhone.replace(/[^0-9]/g, '');
    var _iConsent = (body.consent === true || body.consent === '예' || String(body.consent) === 'true' || String(body.consent) === '1' || String(body.consent) === '동의');
    var _iCat = String(body.category || '').trim();   // 'membership' | 'adult' | 'youth' | 'summer' | 'rental' | 'business' | 'ohnutti'(추석 선물세트, 2026-08-07 GM)
    var _iCompany = String(body.company || '').trim();        // business 전용(name 키 없음)
    var _iContactName = String(body.contactName || '').trim(); // business 전용(name 키 없음)
    if (_iCat !== 'membership' && _iCat !== 'adult' && _iCat !== 'youth' && _iCat !== 'summer' && _iCat !== 'rental' && _iCat !== 'business' && _iCat !== 'ohnutti') return _json({ ok: false, error: '문의 유형이 올바르지 않습니다.', noRetry: true });
    if (_iCat === 'business') {
      if (!_iCompany || !_iContactName) return _json({ ok: false, error: '회사명과 담당자를 입력해 주세요.', noRetry: true });
    } else if (!_iName) {
      return _json({ ok: false, error: '이름을 입력해 주세요.', noRetry: true });
    }
    if (_iPhoneDigits.length < 9 || _iPhoneDigits.length > 11) return _json({ ok: false, error: '연락처를 정확히 입력해 주세요.', noRetry: true });
    if (!_iConsent) return _json({ ok: false, error: '개인정보 수집·이용 동의가 필요합니다.', noRetry: true });
    // 6) 레이트리밋 — 동일 전화 단시간 과다 제출 차단(정상 사용자 무영향: 60초 내 6회 초과 시만)
    if (_iPhoneDigits) {
      var _rlKey = 'intake_rl_' + _iPhoneDigits;
      var _rlN = parseInt(_iCache.get(_rlKey) || '0', 10) + 1;
      _iCache.put(_rlKey, String(_rlN), 60);
      if (_rlN > 6) return _json({ ok: false, error: '잠시 후 다시 시도해 주세요.', noRetry: true });
    }
    var _iId = 'L' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyMMdd-HHmmss');   // 접수ID 축소(2026-07-18 GM): 21자→14자. 중복은 submissionId 멱등+레이트리밋 방지.
    var _iChannel = String(body.channel || '').trim();
    var _iProgram = String(body.program || '').trim();
    var _iMessage = String(body.message || '').trim();
    var _iWish = String(body.wishTime || '').trim();
    var _iAge = String(body.age || '').trim();
    var _iUtmSource = String(body.utmSource || '').trim();
    var _iUtmMedium = String(body.utmMedium || '').trim();
    // utm_content = 같은 채널 내 세부 출처. IG는 계정 구분(official=@wellperion / namuk=@namuk.wellperion).
    //   V열 3번째 세그먼트로 기록 → 'instagram|bio|official'. 채널 판정은 split('|')[0]만 보므로 영향 없음.
    //   2026-07-20 시모: 이 값을 안 받아 적으면 '인스타 1건'이 어느 계정 기여인지 영영 알 수 없다.
    var _iUtmContent = String(body.utmContent || '').trim();
    // utm_campaign = 콘텐츠(게시물) 단위 식별자(scripts/cta_utm.py slugify_campaign). 클라이언트(wp_inquiry_form(.html/_en.html))가
    //   2026-07-31까지 이 값을 안 읽어 URL까지는 왔는데 여기서 버려지고 있었다 — '어느 콘텐츠가 문의를 만들었나'가
    //   채널 단위까지만 측정되던 근본 원인(배252 시모 실측). V열(유입경로자동) 4번째 세그먼트로만 추가 —
    //   채널 판정(_resolveInquiryChannelRaw_)은 split('|')[0]만 읽으므로 기존 로직 영향 0.
    var _iUtmCampaign = String(body.utmCampaign || '').trim();
    // 유입언어(KO/EN) — 영문 자체폼(wp_inquiry_form_en.html)이 payload.lang:'en' 을 보낸다. 없으면 KO(한글폼·기존).
    //   영문 문의도 같은 category(membership/adult/youth)·같은 시트에 append 되므로, 이 값으로 KO/EN 을 구분한다(배9674 시모).
    //   아래 _imSet/_lsSet 은 '유입언어' 칸이 있을 때만 기록 → 칸 없으면 무기록(현행 KO 트래픽 무영향, 컷오버 시 칸 추가로 활성).
    var _iLang = (String(body.lang || '').trim().toLowerCase() === 'en') ? 'EN' : 'KO';
    // 신규 3종 전용 필드(2026-07-16 시토) — wp_inquiry_form.html payload 계약과 1:1
    var _iTarget = String(body.target || '').trim();           // summer: 성인/유소년
    var _iWishMonth = String(body.wishMonth || '').trim();     // summer: 희망 월
    var _iSpace = String(body.space || '').trim();              // rental: 대관 공간(多)
    var _iPurpose = String(body.purpose || '').trim();          // rental: 용도
    var _iWishDate = String(body.wishDate || '').trim();        // rental: 희망일
    var _iHeadcount = String(body.headcount || '').trim();      // rental: 예상 인원
    var _iPartnerType = String(body.partnerType || '').trim();  // business: 제휴 유형
    var _iDocLink = String(body.docLink || '').trim();          // business: 소개자료 링크
    var _iProposal = String(body.proposal || '').trim();        // business: 제안 내용
    var _iOhQty = String(body.qty || '').trim();                 // ohnutti: 수량(세트) — wp_inquiry_form.html FORMS.ohnutti 필드키(qty)와 1:1
    var _iOhSetType = String(body.setType || '').trim();         // ohnutti: 세트 종류(230g 2구/80g 3구, 2026-08-07 GM 파트너 조건 확정)
    var _iOhMethod = String(body.method || '').trim();           // ohnutti: 수령 방법
    var _iOhWantDate = String(body.wantDate || '').trim();       // ohnutti: 희망 수령일
    var _iOhAddress = String(body.address || '').trim();         // ohnutti: 배송지(택배 선택 시)
    var _iOhPay = String(body.pay || '').trim();                 // ohnutti: 결제 방법
    var _iOhNote = String(body.note || '').trim();                // ohnutti: 요청 사항

    try {
      if (_iCat === 'membership') {
        // 멤버십 → '26년 신규문의'(_miSheet_) append. member_inquiry_list가 이미 이 탭 read → 관리페이지 자동정합(읽기 무변경).
        var _imSh = _miSheet_();
        if (!_imSh) return _json({ ok: false, error: '멤버십 시트 없음' });   // 재시도 가능(noRetry 미설정)
        var _imHdr = _miHeaders_(_imSh);
        var _imRow = new Array(_imHdr.length).fill('');
        function _imSet(names, val) { if (val === undefined || val === null || val === '') return; var ci = _miColIdx_(_imHdr, names); if (ci >= 0) _imRow[ci] = val; }
        var _imNowDt = new Date();
        // A열 '날짜' 쓰기 제거(2026-07-20 시포 · 확정스펙 §1-B). 칸 삭제에 앞서 쓰기 경로부터 끊는다.
        //   ★ 그냥 두고 칸만 지우면 이 줄이 고객 데이터를 오염시킨다 —
        //     _miColIdx_(:1344)는 정확일치 실패 시 부분일치로 폴백하는데(:1347), 후보가 ['날짜','접수일']뿐이라
        //     '날짜'를 품은 다른 헤더가 걸린다. 실헤더 시뮬레이션 결과 '5. 시설투어 및 상담을 희망하는 날짜는
        //     언제인가요?' 칸이 반환됐다 → 신규 웹접수마다 접수일자가 고객의 투어 희망일을 덮어쓴다.
        //     에러가 안 나서 발견도 늦는다. 이름참조라도 부분일치 폴백이 있으면 안전하지 않다는 사례.
        //   타임스탬프(B열)는 아래에서 계속 기록하므로 접수 시각 정보는 유실되지 않는다.
        // B열 — ★실제 Date로 기록(2026-07-20 GM). 문자열로 쓰면 시트가 텍스트로 저장해 진짜 날짜값과
        //   따로 정렬돼 맨 위/맨 아래로 튄다(GM 지적: Nicole·한혜수·원유선 건). Date면 시트 자체 서식이
        //   적용돼 시분초 보존 + 정렬·비교 정상.
        _imSet(['타임스탬프', 'timestamp'], _imNowDt);
        _imSet(['성함', '이름'], _iName);
        _imSet(['연락처', '전화', '휴대폰'], _fmtPhone_(_iPhone));
        _imSet(['관심 있는 프로그램 종류', '관심 있는 프로그램 종목', '관심프로그램', '프로그램', '종목'], _iProgram);
        _imSet(['진행현황', '진행상황', '진행상태', '상태'], '신규');
        _imSet(['문의채널', '유입채널', '채널', '경로'], _iChannel || _canonicalChannel_(_iUtmSource));
        _imSet(['접수 담당자', '담당'], MEMBER_DEFAULT_OWNER);   // 임정은 고정(2026-08-08 GM) — 아래 강습 분기(_lsSet)는 종목 팀장 배정이라 '웹 자동접수' 유지
        _imSet(['시설투어 및 상담 예약', '시설견학 및 상담 일정', '상담 예약', '상담'], _dateOnlyStrip_(body.exp1Date));  // 날짜 전용 칸 — 시각 혼입 방어(2026-07-20)
        _imSet(['기타 웰페리온에 대한 문의 사항', '기타 웰페리온', '자유롭게 적어', '문의 사항', '내용'], _iMessage);
        _imSet(['유입경로(자동)', '유입경로자동', '유입경로_자동'], _iUtmSource ? (_iUtmSource + (_iUtmMedium ? '|' + _iUtmMedium : '') + (_iUtmContent ? '|' + _iUtmContent : '') + (_iUtmCampaign ? '|' + _iUtmCampaign : '')) : (_iChannel || ''));  // V열 — utm 원본 제자리 기록(2026-07-20 content 세그먼트, 2026-07-31 campaign 4번째 세그먼트 추가). H/I(중분류·소분류)는 자기신고 분류라 건드리지 않음
        _imSet(['비고', '메모', '담당자메모'], WEB_INTAKE_TAG + (_iReviewFlag ? ' ' + _iReviewFlag : ''));   // [웹접수] 유지(집계 중복방지) + 스팸의심 표시. utm 원문은 위 유입경로(자동)로 이관 — 비고엔 더 이상 처박지 않음(2026-07-20)
        _imSet(['개인정보 수집·이용 동의'], '동의');   // U열 — 검증만 하고 미기록이던 버그 수리(2026-07-20 시포). 강습·공간렌트·비즈니스 분기와 동일 표기 '동의' 통일. 헤더가 매우 긴 문장이라 짧은 키(동의·개인정보)는 다른 칸과 충돌 위험 있어 실헤더 대조로 확인한 고유 서두 구절만 사용. 과거 행은 무변경(신규 append만).
        _imSet(['유입언어'], _iLang);   // KO/EN — 영문 자체폼 통합(배9674 시모). 정확일치 우선(_miColIdx_) + '유입언어'는 부분일치 충돌 없음. 칸 없으면 무기록(컷오버 전엔 no-op).
        _imSh.appendRow(_imRow);
        _miCacheClear_();   // 문의 캐시 일괄 무효화(달력 포함)
      } else if (_iCat === 'adult' || _iCat === 'youth' || _iCat === 'summer') {
        // 강습(성인/유소년/여름특강) → 기존 구글폼 응답탭 저장으로 전환(자체폼·구글폼 통일 1단계, 2026-07-18 GM).
        //   성인=1.성인강습(gid111889422) / 유소년·여름특강(성인분기 없음·무조건 유소년탭)=2.WSC강습(gid268994754).
        //   두 탭 헤더 이름이 달라 유연매칭(_findCol_ 부분일치)으로 흡수. 읽기 병합 로직(_lessonIntakeReadRows_ 등)은 이번 증분 범위 밖 — 그대로 유지.
        var _isSummer = (_iCat === 'summer');
        var _isYouth = (_iCat === 'youth') || _isSummer;   // 여름특강=성인 분기 제거·유소년탭 고정(GM 정정 2026-07-18)
        var _iType = _isYouth ? '유소년강습' : '성인강습';
        var _lsGid = _isYouth ? 268994754 : 111889422;
        var _lsSh = _lessonSheet_(_lsGid);
        if (!_lsSh) return _json({ ok: false, error: '강습 응답 시트 없음' });   // 재시도 가능
        var _lsHdr = _lsSh.getRange(1, 1, 1, _lsSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
        var _lsRow = new Array(_lsHdr.length).fill('');
        // 배(희망 레슨시간 유실, 2026-07-20): 칸을 못 찾거나 이미 값이 있어 조용히 스킵될 때 로그만 남김(동작 무변경 — 쓰기 조건은 기존과 100% 동일).
        function _lsSet(keys, val) {
          if (!val && val !== '') return;
          var ci = _findCol_(_lsHdr, keys);
          if (ci < 0) { Logger.log('_lsSet 스킵(칸 없음): keys=' + JSON.stringify(keys) + ' val=' + val); return; }
          if (_lsRow[ci]) { Logger.log('_lsSet 스킵(이미 값 있음 — 다른 필드와 칸 충돌 의심): keys=' + JSON.stringify(keys) + ' col="' + _lsHdr[ci] + '"(idx' + ci + ') newVal=' + val + ' existingVal=' + _lsRow[ci]); return; }
          _lsRow[ci] = val;
        }
        var _lsNowDt = new Date();
        var _lsToday = Utilities.formatDate(_lsNowDt, 'Asia/Seoul', 'yyyy-MM-dd');            // 날짜 전용(문의일 등)
        var _lsNowFull = Utilities.formatDate(_lsNowDt, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');  // 타임스탬프 전용(시:분:초 보존, 2026-07-18)
        _lsSet(['타임스탬프'], _lsNowDt);   // ★실제 Date(2026-07-20 GM) — 문자열이면 정렬이 깨진다
        // ★'문의일'(A열) 쓰기 제거 — 2026-07-20 GM 지시(칸 삭제 선행 작업).
        //   ①타임스탬프가 같은 정보를 더 정확히(시:분:초까지) 담고 있어 중복이다.
        //   ②칸을 지운 뒤에도 이 쓰기가 남아 있으면 _findCol_의 부분일치 폴백이 엉뚱한 칸을 잡아 덮어쓴다 —
        //     멤버십 시트에서 같은 패턴이 고객의 '투어 희망일' 칸을 덮어쓸 뻔했다(실측 시뮬레이션으로 확인).
        //   그래서 칸 삭제보다 이 쓰기 제거가 먼저다. 순서를 바꾸면 그 사이 들어온 문의가 오염된다.
        _lsSet(['성함', '이름'], _iName);
        _lsSet(['연락처', '핸드폰', '전화', '휴대폰'], _fmtPhone_(_iPhone));
        _lsSet(['나이', '연령', '자녀'], _iAge);
        _lsSet(['강습 종목', '종목', '과목'], _isSummer ? ('여름방학특강 - ' + _iProgram) : _iProgram);
        _lsSet(['문의 경로', '경로', '채널'], _iChannel || _canonicalChannel_(_iUtmSource));
        _lsSet(['유입경로(자동)', '유입경로자동', '유입경로_자동'], _iUtmSource ? (_iUtmSource + (_iUtmMedium ? '|' + _iUtmMedium : '') + (_iUtmContent ? '|' + _iUtmContent : '') + (_iUtmCampaign ? '|' + _iUtmCampaign : '')) : (_iChannel || ''));  // UTM 4세그먼트 기록(2026-07-31 campaign 추가) — 멤버십과 동일 패턴. _LESSON_MGMT_FIELDS 등재(2026-07-21 GM) 후 배선 누락 수리. 2026-07-26 시모.
        _lsSet(['문의 사항', '문의사항', '내용'], _iMessage);
        // 배(희망 레슨시간 유실, 2026-07-20 실측규명): 구키 ['희망','레슨 시간','시간']는 '희망' 부분일치가
        //   idx5 종목칸("...강습 종목 (희망종목 모두 체크)")에 먼저 걸려 정답칸(idx9)에 도달 못하고 조용히 스킵됨
        //   (idx5가 이미 채워져 있어 _lsSet 가드가 막음). 정답 헤더 전문을 정확일치 1순위로, 폴백은 다른 헤더와
        //   충돌 없는 '레슨 시간'만 남김(성인·WSC 양쪽 실제 헤더 대조 검증 완료 — 둘 다 idx9 정확 반환).
        _lsSet(['희망하시는 레슨 시간을 체크해주세요', '레슨 시간'], _isSummer ? (_iWish || _iWishMonth) : _iWish);   // 여름방학특강(유소년) 폼이 wishMonth→wishTime(요일/시간)으로 교체됨(2026-07-22 시모). 구 wishMonth는 폴백 유지(하위호환).
        _lsSet(['접수 담당자', '담당자 혹은', '담당'], '웹 자동접수');
        _lsSet(['개인정보', '동의', '수집·이용'], '동의');
        _lsSet(['유입언어'], _iLang);   // KO/EN — 영문 자체폼 통합(배9674 시모). '유입언어' 칸 있을 때만 기록(컷오버 전엔 no-op·현행 무영향).
        _lsSet(['진행 상황', '진행상황', '상태'], '신규');
        if (_iReviewFlag) _lsSet(['비고', '메모'], _iReviewFlag);   // 스팸의심 표시(칸 없으면 스킵·무해) — 강습도 멤버십과 동일 정책
        // 비고에 접수ID를 쓰지 않는다(2026-07-20 시포·GM 판정): 접수ID는 타임스탬프 재표현(L+yyMMdd-HHmmss)일 뿐이고
        //   강습 도메인에서 키로 쓰이는 곳이 0곳(중복방지는 위 submissionId 멱등 캐시가 전담). 비고는 CONTACT(연락이력)
        //   읽기 폴백 소스라서(_lessonReadRows_ 의 _lMemo 폴백) 접수ID가 마치 "연락 이력"인 것처럼 화면에 떠
        //   미컨택 집계를 왜곡시켰다 — 그 기록 자체를 중단한다. (렌트·비즈니스 탭의 진짜 '접수ID' 칸은 유지.)
        // 2026-07-21 GM: 상단삽입 폐지 → appendRow(맨 아래 시간순 누적). 구글폼 응답도 append라 순서 꼬임 해소. 관리화면은 타임스탬프 desc 정렬.
        _lsSh.appendRow(_lsRow);
        try {
          var _lsLast = _lsSh.getLastRow();
          if (_lsLast > 1) _lsSh.getRange(2, 1, _lsLast - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');   // 타임스탬프 열 시:분:초 표시 통일(기존행 포함)
        } catch (_e) {}
        try {
          _cacheInvalidateJson_(_iCache, 'licache|' + _iType + '|year');
          _cacheInvalidateJson_(_iCache, 'licache|' + _iType + '|all');
          _cacheInvalidateJson_(_iCache, 'lscache|' + _iType + '|year');
          _cacheInvalidateJson_(_iCache, 'lscache|' + _iType + '|all');
        } catch (e) {}
      } else if (_iCat === 'rental') {
        // 공간렌트 → '공간렌트 문의' 신규 탭(_MI_SS_ID 하위, 2026-07-16 시토)
        var _rtSh = _rentalIntakeSheet_(true);
        if (!_rtSh) return _json({ ok: false, error: '공간렌트 문의 시트 생성 실패' });
        var _rtHdr = _rtSh.getRange(1, 1, 1, _rtSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
        var _rtRow = new Array(_rtHdr.length).fill('');
        function _rtSet(name, val) { if (val === undefined || val === null || val === '') return; var ci = _findCol_(_rtHdr, [name]); if (ci >= 0) _rtRow[ci] = val; }
        _rtSet('타임스탬프', new Date());  // ★실제 Date(2026-07-20 GM) — 문자열이면 정렬이 깨진다
        _rtSet('성함', _iName);
        _rtSet('연락처', _fmtPhone_(_iPhone));
        _rtSet('대관 공간', _iSpace);
        _rtSet('용도', _iPurpose);
        _rtSet('희망일', _iWishDate);
        _rtSet('예상 인원', _iHeadcount);
        _rtSet('문의 사항', _iMessage);
        _rtSet('개인정보 수집·이용 동의', '동의');
        _rtSet('접수ID', _iId);
        _rtSet('진행 상황', '신규');
        _rtSet('유입언어', _iLang);   // KO/EN — 영문 자체폼 6종 통합(배9674 시모). 칸 있을 때만 기록(no-op safe).
        if (_iReviewFlag) _rtSet('비고', _iReviewFlag + ' 자동검토');
        _rtSh.appendRow(_rtRow);
      } else if (_iCat === 'business') {
        // 비즈니스(_iCat === 'business') → '비즈니스 문의' 신규 탭(_MI_SS_ID 하위, 2026-07-16 시토)
        var _bzSh = _businessIntakeSheet_(true);
        if (!_bzSh) return _json({ ok: false, error: '비즈니스 문의 시트 생성 실패' });
        var _bzHdr = _bzSh.getRange(1, 1, 1, _bzSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
        var _bzRow = new Array(_bzHdr.length).fill('');
        function _bzSet(name, val) { if (val === undefined || val === null || val === '') return; var ci = _findCol_(_bzHdr, [name]); if (ci >= 0) _bzRow[ci] = val; }
        _bzSet('타임스탬프', new Date());  // ★실제 Date(2026-07-20 GM) — 문자열이면 정렬이 깨진다
        _bzSet('성함', _iCompany + ' / ' + _iContactName);
        _bzSet('회사명', _iCompany);
        _bzSet('담당자', _iContactName);
        _bzSet('연락처', _fmtPhone_(_iPhone));
        _bzSet('제휴 유형', _iPartnerType);
        _bzSet('소개자료 링크', _iDocLink);
        _bzSet('제안 내용', _iProposal);
        _bzSet('개인정보 수집·이용 동의', '동의');
        _bzSet('접수ID', _iId);
        _bzSet('진행 상황', '신규');
        _bzSet('유입언어', _iLang);   // KO/EN — 영문 자체폼 6종 통합(배9674 시모). 칸 있을 때만 기록(no-op safe).
        if (_iReviewFlag) _bzSet('비고', _iReviewFlag + ' 자동검토');
        _bzSh.appendRow(_bzRow);
      } else {
        // 오넛티(_iCat === 'ohnutti') → '오넛티 선물세트 접수' 신규 탭(_MI_SS_ID 하위, 2026-08-07 GM 지시)
        //   선착순 500세트 — 수량 부족해도 접수는 막지 않고 '대기' 상태로 받는다(GM 확정). 순번·재고 계산은
        //   서버 판정(LockService 잠금 안)이 정본 — 동시접수 경합으로 순번·재고가 어긋나지 않게 한다.
        var _ohQty = parseInt(_iOhQty.replace(/[^0-9]/g, ''), 10) || 0;
        if (_ohQty < 1) return _json({ ok: false, error: '수량을 정확히 입력해 주세요.', noRetry: true });
        var _ohSh = _ohnuttiIntakeSheet_(true);
        if (!_ohSh) return _json({ ok: false, error: '오넛티 접수 시트 생성 실패' });
        var _ohLock = LockService.getScriptLock();
        if (!_ohLock.tryLock(5000)) return _json({ ok: false, error: '접수가 몰려 있습니다. 잠시 후 다시 시도해 주세요.' });   // 재시도 가능
        try {
          var _ohCap = _ohnuttiCapacityStats_();
          var _ohStatus = (_ohCap.remaining >= _ohQty) ? '접수' : '대기';
          var _ohSeq = _ohCap.total + 1;   // 순번 = 누적 신청 세트수 뒤 순서(접수+대기 모두 포함 — 대기도 순번은 받는다)
          var _ohNowDt = new Date();
          // 결제기한 = 접수 후 3일(GM 확정). '대기'는 아직 슬롯이 확정 안 돼 결제 자체가 의미 없어 기한 미기록.
          var _ohDeadline = (_ohStatus === '접수') ? new Date(_ohNowDt.getTime() + 3 * 24 * 60 * 60 * 1000) : '';
          var _ohHdr = _ohSh.getRange(1, 1, 1, _ohSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
          var _ohRow = new Array(_ohHdr.length).fill('');
          function _ohSet(name, val) { if (val === undefined || val === null || val === '') return; var ci = _findCol_(_ohHdr, [name]); if (ci >= 0) _ohRow[ci] = val; }
          _ohSet('접수시각', _ohNowDt);   // ★실제 Date — 문자열이면 정렬이 깨진다(다른 문의 탭과 동일 규칙)
          _ohSet('접수번호', _iId);
          _ohSet('성함', _iName);
          _ohSet('연락처', _fmtPhone_(_iPhone));
          _ohSet('수량', _ohQty);
          _ohSet('세트종류', _iOhSetType);
          _ohSet('수령방법', _iOhMethod);
          _ohSet('희망수령일', _iOhWantDate);
          _ohSet('배송지', _iOhAddress);
          _ohSet('결제방법', _iOhPay);
          _ohSet('요청사항', _iOhNote);
          _ohSet('상태', _ohStatus);
          _ohSet('순번', _ohSeq);
          if (_ohDeadline) _ohSet('결제기한', _ohDeadline);
          if (_iReviewFlag) _ohSet('비고', _iReviewFlag + ' 자동검토');
          _ohSh.appendRow(_ohRow);
        } finally {
          _ohLock.releaseLock();
        }
      }
    } catch (eIntake) {
      // 저장 실패 = 재시도 가능(noRetry 미설정) → 프론트 대기큐가 재전송. 조용한 유실 0.
      return _json({ ok: false, error: '서버 저장 오류: ' + eIntake.message });
    }

    // 멱등 마커(성공) — 6시간 보관. 같은 submissionId 재전송 시 중복행 방지.
    if (_sid) { try { _iCache.put('intake_sid_' + _sid, _iId, 21600); } catch (e) {} }
    // 알림 — '문의 알림' 방(멤버십 add·구글폼과 동일 톤). 실패해도 접수 자체는 성공 유지(fail-soft).
    // 신규 3종(여름특강·공간렌트·비즈니스)도 category 라벨·표시명·부가정보만 분기해 동일 _notifyTelegram 재사용(2026-07-16 시토).
    try {
      var _iCatLabelMap = { membership: '멤버십', adult: '성인 강습', youth: '유소년 강습', summer: '여름 특강', rental: '공간 렌트', business: '비즈니스 제휴', ohnutti: '오넛티 선물세트' };
      var _iCatLabel = _iCatLabelMap[_iCat] || _iCat;
      var _iDisplayName = (_iCat === 'business') ? (_iCompany + ' / ' + _iContactName) : _iName;
      var _iChat = _inquiryNotifyChatId_(_iDisplayName, _prop('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK); // 배209 재발방지 — 테스트 태그는 업무보고방으로
      var _iExtra = '';
      if (_iCat === 'summer') _iExtra = (_iWish ? ('\n희망시간: ' + _iWish) : '') + (_iWishMonth ? ('\n희망월: ' + _iWishMonth) : '') + (_iTarget ? ('\n대상: ' + _iTarget) : '');
      if (_iCat === 'rental') _iExtra = (_iSpace ? ('\n공간: ' + _iSpace) : '') + (_iPurpose ? ('\n용도: ' + _iPurpose) : '');
      if (_iCat === 'business') _iExtra = (_iPartnerType ? ('\n제휴유형: ' + _iPartnerType) : '');
      if (_iCat === 'ohnutti') _iExtra = (_iOhSetType ? ('\n세트: ' + _iOhSetType) : '') + (_iOhQty ? ('\n수량: ' + _iOhQty + '세트') : '') + (_iOhMethod ? ('\n수령방법: ' + _iOhMethod) : '');
      _notifyTelegram((_isTestInquiryName_(_iDisplayName) ? '🧪 <b>[테스트 문의 — 업무보고방으로 자동전환]</b>\n' : '🔔 <b>[웹 문의 접수]</b> (자체폼)\n') + '유형: ' + _iCatLabel + '\n이름: ' + _iDisplayName + '\n연락처: ' + _fmtPhone_(_iPhone)
        + (_iProgram ? ('\n관심: ' + _iProgram) : '') + _iExtra + (_iMessage ? ('\n내용: ' + _iMessage.substring(0, 100)) : ''), _iChat);
    } catch (e) {}
    return _json({ ok: true, id: _iId, submissionId: _sid, message: '문의가 접수되었습니다.' });
  }

  // ─── 실무진 피드백 접수 — 회원관리 화면 상단 '💬 실무진 피드백' 버튼 → 실무진피드백.html (GM 2026-07-24 시포) ───
  //   실무진이 화면·업무를 쓰다 느낀 불편·개선요청을 그 자리에서 남긴다. 저장 = 멤버십 스프레드시트
  //   '실무진 피드백' 탭(없으면 헤더와 함께 생성) · 알림 = 업무보고방 1줄.
  //   ★방어는 intake_submit 과 같은 계열을 그대로 쓴다(토큰·허니팟·멱등·레이트리밋) — 새 방식 발명 없음.
  //   ★고객 데이터 무관(회원 시트에 쓰지 않는다) — 별도 탭이라 기존 문의 파이프라인에 영향 0.
  if (action === 'staff_feedback_submit') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    if (String(body.hp || '').trim() !== '') return _json({ ok: true, id: 'HP', dedup: true });  // 허니팟(봇) — 조용히 성공가장
    var _sfCache = CacheService.getScriptCache();
    var _sfSid = String(body.submissionId || '').slice(0, 64);
    if (_sfSid) {   // 멱등 — 재시도로 같은 피드백이 두 줄 쌓이지 않게
      var _sfPrev = _sfCache.get('sf_sid_' + _sfSid);
      if (_sfPrev) return _json({ ok: true, id: _sfPrev, dedup: true });
    }
    var _sfBody = String(body.content || '').trim();
    if (!_sfBody) return _json({ ok: false, error: '내용을 입력해 주세요.', noRetry: true });
    if (_sfBody.length > 2000) _sfBody = _sfBody.slice(0, 2000);
    var _sfScreen = String(body.screen  || '').trim().slice(0, 40);
    var _sfKind   = String(body.kind    || '').trim().slice(0, 40);
    var _sfUrgent = String(body.urgency || '').trim().slice(0, 20);
    var _sfWho    = String(body.writer  || '').trim().slice(0, 40);
    var _sfRlKey = 'sf_rl_' + (_sfWho || 'anon');   // 레이트리밋 — 60초 내 5회 초과만 차단(정상 사용 무영향)
    var _sfN = parseInt(_sfCache.get(_sfRlKey) || '0', 10) + 1;
    _sfCache.put(_sfRlKey, String(_sfN), 60);
    if (_sfN > 5) return _json({ ok: false, error: '잠시 후 다시 보내주세요.', noRetry: true });

    var _sfId = 'FB' + Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyMMdd-HHmmss');
    try {
      var _sfSs = SpreadsheetApp.openById(_MI_SS_ID);          // 멤버십 문의 관리 스프레드시트(정본 상수 재사용)
      var _sfSh = _sfSs.getSheetByName('실무진 피드백');
      if (!_sfSh) {
        _sfSh = _sfSs.insertSheet('실무진 피드백');
        _sfSh.appendRow(['접수시각', '접수ID', '업무 구분', '종류', '급한정도', '작성자', '내용', '처리상태', '처리메모']);
        _sfSh.setFrozenRows(1);
      }
      // C칸 제목 정정(2026-07-25 GM) — '화면'은 무엇을 적는 칸인지 모호했다. 값이 '멤버십 회원관리'·
      // '강습 회원관리'·'종합접수처' 처럼 업무 단위라 '업무 구분'이 맞다. 이미 그렇게 돼 있으면 건드리지 않는다.
      if (String(_sfSh.getRange(1, 3).getValue() || '').trim() === '화면') {
        _sfSh.getRange(1, 3).setValue('업무 구분');
      }
      // ★새 접수는 맨 위(2행)에 넣는다(2026-07-25 GM "접수시각 기준 최근 것을 최상단으로").
      //   맨 아래로 쌓이면 실무진·시포 모두 매번 시트 끝까지 내려가야 최신 건을 본다.
      //   기존 행은 그대로 한 칸씩 내려갈 뿐이라 값·수식이 어긋나지 않는다(행 삭제 아님).
      _sfSh.insertRowBefore(2);
      _sfSh.getRange(2, 1, 1, 9).setValues([[new Date(), _sfId, _sfScreen, _sfKind, _sfUrgent, _sfWho, _sfBody, '접수', '']]);
    } catch (e) {
      // ★저장 실패를 성공으로 위장하지 않는다(INC-014 재발방지) — 화면이 실패를 그대로 보여줘야 한다.
      return _json({ ok: false, error: '저장에 실패했습니다. 잠시 후 다시 시도해 주세요.' });
    }
    if (_sfSid) _sfCache.put('sf_sid_' + _sfSid, _sfId, 600);
    try {   // 알림 실패는 접수를 되돌리지 않는다(이미 저장됨) — best-effort
      var _sfEsc = function (s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
      // ★발신처 = 문의알림방(2026-08-06 GM 지시 "종합접수처처럼 문의알림방에 접수되었고").
      //   전에는 GM 업무보고방으로만 갔다 — 신고한 실무진 본인은 접수된 줄도 몰랐다.
      //   방을 옮기는 것이지 늘리는 것이 아니다(중복 발신 금지).
      _notifyTelegram('💬 <b>실무진 피드백 접수</b>'
        + '\n접수번호: ' + _sfEsc(_sfId)
        + (_sfScreen ? '\n화면: ' + _sfEsc(_sfScreen) : '')
        + (_sfKind   ? '\n종류: ' + _sfEsc(_sfKind)   : '')
        + (_sfUrgent ? '\n급한정도: ' + _sfEsc(_sfUrgent) : '')
        + (_sfWho    ? '\n작성: ' + _sfEsc(_sfWho)    : '')
        + '\n\n' + _sfEsc(_sfBody.slice(0, 300)),
        _staffFeedbackRoom_());
    } catch (e) { /* 알림 실패 무시 */ }
    return _json({ ok: true, id: _sfId });
  }

  // ─── 실무진 피드백 알림 판정 3종 (2026-08-06 GM 지시 · 시포) ─────────────────
//   접수·처리 알림이 어디로 갈지, 그리고 '처리완료'라고 부를 자격이 있는지를 여기 한 곳에서만 정한다.
//   판정을 호출부마다 복제하면 우회로가 생긴다(약속 L21).
function _staffFeedbackRoom_() {
  // 문의알림방 — 신규 문의 알림이 이미 쓰는 그 방·그 프로퍼티를 그대로 재사용(새 방·새 키 없음).
  return PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID')
      || _INQUIRY_CHAT_ID_FALLBACK;
}
// ─── '신규 등록인가' 판정 — 단 하나의 자리 (2026-08-06 시포 · 배361 연장) ───────
//   ★왜 뽑았나: 목록(member_registered_list&newOnly=1)은 5명인데 카드(cpo_today_stats.monthReg)는
//   10명이었다(2026-08-06 GM 지적 "신규멤버십 등록현황이 5명인데 위에 카드는 10명?"). 같은 제목의
//   같은 숫자를 두 조회가 각자 세고 있었고, 한쪽만 신규 판정을 알고 있었다. 판정을 한 곳으로 모은다(약속 L01).
function _isNewRegistration_(regClass, regClass2, regSeq) {
  // 재등록분류에 '재등록'(또는 'L재등록')이 있으면 신규가 아니다. 대기·LOSS·환불·양도LOSS 등
  // 다른 값은 신규 여부와 무관하므로 그대로 둔다(보수적 — 2026-08-05 시토).
  if (String(regClass2 || '').indexOf('재등록') >= 0) return false;
  // 등록회차 2 이상이면 등록분류가 '신규'라 적혀 있어도 신규가 아니다(부부 재등록 등 · 2026-08-05 시토).
  // 회차가 비었거나 숫자가 아니면 기존 동작 유지 — 값이 없다고 빼면 진짜 신규가 사라진다.
  var m = String(regSeq || '').match(/\d+/);
  if (m && parseInt(m[0], 10) >= 2) return false;
  var c = String(regClass || '').trim();
  if (c) return c === '신규';
  var n = parseInt(regSeq, 10);
  return !(n > 1);
}
function _isDoneStatus_(st) {
  // '처리완료' · '처리완료(원인 수리)' 처럼 꼬리표가 붙은 것까지 완료로 본다.
  return String(st || '').indexOf('처리완료') >= 0;
}
function _hasRealReply_(memo) {
  var m = String(memo || '');
  // 대괄호 날짜·서명 태그는 회신 내용이 아니다 — 빼고 센다.
  var core = m.replace(/\[[^\]]*\]/g, '').trim();
  if (!core) return false;
  // 내용 없이 완료로 닫던 상투 문구 — 이게 들어 있으면 회신이 아니다.
  if (m.indexOf('아직 남기지 않아') >= 0 || m.indexOf('메모가 남는 대로') >= 0) return false;
  return core.length >= 40;
}

  // ─── 브로제이로 넘길 실무진 피드백을 브로제이 시트로 옮겨 적기 (GM 지시 2026-08-07 · 시토) ───
  //   GM: "실무진 피드백에서 브로제이로 남는건은 브로제이 시트에다가 '실무진 피드백' 시트칸
  //   만들어두었으니, 기록 연결해주고, 마무리해줘."
  //   ▸브로제이(외부 업체 · 시트 소유 jbro.matthew)가 직접 봐야 처리되는 건들이라, 우리 탭에만
  //     있으면 영영 안 넘어간다. 브로제이 시트의 '실무진 피드백' 탭으로 옮겨 적는다.
  //   ▸대조키 = 접수ID(FB…). 이미 적힌 건은 건드리지 않는다(같은 줄이 두 번 생기지 않게).
  //     행번호로 찾지 않는다 — 중간 행이 지워지면 엉뚱한 줄을 고친다(위 update 와 같은 규율).
  //   ▸브로제이가 채우는 두 칸(확인·답변 / 처리상태)은 우리가 절대 덮어쓰지 않는다.
  if (action === 'brojay_feedback_sync') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _bjSrc = SpreadsheetApp.openById(_MI_SS_ID).getSheetByName('실무진 피드백');
    if (!_bjSrc) return _json({ ok: false, error: '우리 실무진 피드백 탭 없음' });
    var _bjSrcLast = _bjSrc.getLastRow();
    if (_bjSrcLast < 2) return _json({ ok: true, added: 0, skipped: 0, note: '접수 없음' });
    var _bjSrcRows = _bjSrc.getRange(1, 1, _bjSrcLast, _bjSrc.getLastColumn()).getDisplayValues();
    var _bjH = _bjSrcRows[0].map(function (v) { return String(v).trim(); });
    var _bjI = function (n) { return _bjH.indexOf(n); };
    var cTime = _bjI('접수시각'), cId = _bjI('접수ID'), cCat = _bjI('업무 구분'),
        cKind = _bjI('종류'), cUrg = _bjI('급한정도'), cBy = _bjI('작성자'),
        cBody = _bjI('내용'), cSt = _bjI('처리상태');
    if (cId < 0 || cCat < 0) return _json({ ok: false, error: '접수ID·업무 구분 칸 미발견' });

    var _bjDstSs = SpreadsheetApp.openById('16RL4xhCK0-JOHy9rLPPte0xXdC1cSlPQnmdU13Ri6sQ');
    var _bjDst = _bjDstSs.getSheetByName('실무진 피드백');
    if (!_bjDst) return _json({ ok: false, error: '브로제이 시트에 실무진 피드백 탭 없음' });

    // 헤더 — 비어 있으면 처음 한 번만 만든다(브로제이가 이미 만들어 뒀으면 그대로 쓴다).
    var _bjDstLast = _bjDst.getLastRow();
    var _bjHeader = ['접수일', '접수ID', '작성자', '종류', '급한정도', '요청 내용',
                     '웰페리온 처리상태', '브로제이 확인·답변', '브로제이 처리상태'];
    if (_bjDstLast < 1 || String(_bjDst.getRange(1, 2).getDisplayValue() || '').trim() !== '접수ID') {
      _bjDst.getRange(1, 1, 1, _bjHeader.length).setValues([_bjHeader]).setFontWeight('bold');
      _bjDstLast = 1;
    }
    // 이미 적힌 접수ID 모으기(중복 방지)
    var _bjSeen = {};
    if (_bjDstLast >= 2) {
      var _bjIds = _bjDst.getRange(2, 2, _bjDstLast - 1, 1).getDisplayValues();
      for (var _bi = 0; _bi < _bjIds.length; _bi++) {
        var _v = String(_bjIds[_bi][0] || '').trim();
        if (_v) _bjSeen[_v] = true;
      }
    }
    var _bjNew = [], _bjSkip = 0;
    for (var _r = 1; _r < _bjSrcRows.length; _r++) {
      var row = _bjSrcRows[_r];
      if (String(row[cCat] || '').indexOf('브로제이') < 0) continue;
      var id = String(row[cId] || '').trim();
      if (!id) continue;
      if (_bjSeen[id]) { _bjSkip++; continue; }
      _bjSeen[id] = true;
      _bjNew.push([
        cTime >= 0 ? String(row[cTime] || '') : '', id,
        cBy >= 0 ? String(row[cBy] || '') : '', cKind >= 0 ? String(row[cKind] || '') : '',
        cUrg >= 0 ? String(row[cUrg] || '') : '', cBody >= 0 ? String(row[cBody] || '') : '',
        cSt >= 0 ? String(row[cSt] || '') : '', '', ''
      ]);
    }
    if (_bjNew.length) {
      _bjDst.getRange(_bjDst.getLastRow() + 1, 1, _bjNew.length, _bjHeader.length).setValues(_bjNew);
    }
    return _json({ ok: true, added: _bjNew.length, skipped: _bjSkip,
                   ids: _bjNew.map(function (x) { return x[1]; }) });
  }

// ─── 실무진 피드백 조회·처리 (토큰 게이트 · 시포 2026-07-24) ───────────────────
  //   list   : 접수된 피드백 전체를 최신순으로 반환(처리상태·처리메모 포함).
  //   update : 처리상태·처리메모를 적는다. ★대조키 = 접수ID(FB…) — 행번호로 찾지 않는다.
  //            행번호 기준은 중간에 행이 지워지면 엉뚱한 줄을 고친다(실고객 오삭제 사고와 동종).
  if (action === 'staff_feedback_list' || action === 'staff_feedback_update') {
    // ★2026-08-04 시토 재개(배299 · GM 2026-08-03 확정 "gate.js 커튼 재사용은 자율") —
    //   08-03 낮에 커튼 열쇠로 열었다가(11:27) GM이 "시트에서 보는 게 편하다"며 12분 만에 되돌린(11:39) 적이
    //   있지만, 08-04 GM이 "접수하면 바로 처리가 되어야 하는데 안 되네"로 다시 지시해 재개한다.
    //   ★판정은 이 함수 하나에서만 한다(다른 곳에 조건 복제 금지 — 약속 L21).
    if (!_staffFeedbackWriteAuthed_(action, body)) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _fbSh = SpreadsheetApp.openById(_MI_SS_ID).getSheetByName('실무진 피드백');
    if (!_fbSh) return _json({ ok: true, rows: [], note: '아직 접수 없음(탭 미생성)' });
    var _fbLast = _fbSh.getLastRow();
    if (_fbLast < 2) return _json({ ok: true, rows: [] });
    var _fbHdr = _fbSh.getRange(1, 1, 1, _fbSh.getLastColumn()).getDisplayValues()[0];
    var _fbIx = function (name) { for (var i = 0; i < _fbHdr.length; i++) if (String(_fbHdr[i]).trim() === name) return i; return -1; };
    var _cId = _fbIx('접수ID'), _cSt = _fbIx('처리상태'), _cMemo = _fbIx('처리메모');
    var _cWho = _fbIx('작성자'), _cBody = _fbIx('내용');   // 처리완료 알림 본문용(없으면 -1 — 그 줄만 생략)
    if (_cId < 0) return _json({ ok: false, error: '접수ID 칸을 찾을 수 없습니다.' });
    var _fbVals = _fbSh.getRange(2, 1, _fbLast - 1, _fbHdr.length).getDisplayValues();

    if (action === 'staff_feedback_list') {
      var _rows = [];
      for (var i = 0; i < _fbVals.length; i++) {
        var o = {};
        for (var c = 0; c < _fbHdr.length; c++) o[String(_fbHdr[c]).trim()] = _fbVals[i][c];
        _rows.push(o);
      }
      // 최신 먼저 — 물리적 행 순서에 기대지 않고 접수ID(FByyMMdd-HHmmss)로 정렬한다.
      // 2026-07-25부터 새 접수는 2행에 꽂히므로 예전처럼 reverse() 하면 오히려 과거가 위로 온다.
      // 접수ID는 시각을 그대로 담은 문자열이라 사전순 내림차순 = 시간 내림차순이다.
      _rows.sort(function (a, b) {
        var x = String(a['접수ID'] || ''), y = String(b['접수ID'] || '');
        return x < y ? 1 : (x > y ? -1 : 0);
      });
      return _json({ ok: true, count: _rows.length, rows: _rows });
    }

    // 한 번만 필요한 정렬(2026-07-25 GM) — 이미 쌓여 있던 옛 행들을 접수시각 내림차순으로 재배치한다.
    //   새 접수는 이제 2행에 꽂히므로 앞으로는 저절로 최신이 위다. 새 액션을 만들지 않고 같은 토큰
    //   게이트 안에서 처리한다. 정렬은 값만 재배치(행 삭제 없음)이고, 이미 정렬돼 있으면 결과가 같다(멱등).
    if (body.resort === true) {
      if (_fbLast >= 3) _fbSh.getRange(2, 1, _fbLast - 1, _fbHdr.length).sort({ column: 1, ascending: false });
      // C칸 제목도 여기서 함께 바로잡는다 — 접수가 들어와야만 고쳐지면 며칠 동안 옛 제목이 남는다.
      var _renamed = false;
      if (String(_fbSh.getRange(1, 3).getValue() || '').trim() === '화면') {
        _fbSh.getRange(1, 3).setValue('업무 구분');
        _renamed = true;
      }
      return _json({ ok: true, sorted: Math.max(0, _fbLast - 1), renamed: _renamed });
    }

    // update — [{id, status, memo}] 배열을 받아 접수ID 로 찾아 적는다(못 찾으면 건너뛰고 보고).
    var _ups = body.updates;
    if (!_ups || !_ups.length) return _json({ ok: false, error: 'updates 가 비어 있습니다.', noRetry: true });
    if (_cSt < 0 || _cMemo < 0) return _json({ ok: false, error: '처리상태·처리메모 칸을 찾을 수 없습니다.' });
    var _done = [], _miss = [];
    for (var u = 0; u < _ups.length; u++) {
      var wantId = String(_ups[u].id || '').trim();
      var hit = -1;
      for (var r = 0; r < _fbVals.length; r++) if (String(_fbVals[r][_cId]).trim() === wantId) { hit = r; break; }
      if (hit < 0) { _miss.push(wantId); continue; }
      var rowNo = hit + 2;   // 헤더 1줄 + 0-based → 실제 행. 대조로 찾은 행이라 어긋나지 않는다.
      var _wantSt = _ups[u].status === undefined ? '' : String(_ups[u].status);
      var _wantMemo = _ups[u].memo === undefined
        ? String(_fbVals[hit][_cMemo] || '')      // 이번에 안 보냈으면 시트에 이미 적힌 값으로 판정
        : String(_ups[u].memo);
      // ★가짜 완료 차단(2026-08-06 GM 지시 · 시포) — 회신 내용이 없는데 '처리완료'로 적히던 것을 막는다.
      //   실측 2026-08-06: 시트 58건이 전부 '처리완료'였고, 그중 오늘 접수건의 회신은
      //   "처리 메모를 아직 남기지 않아 나중에 안내드리겠습니다" 였다. 감시 장치는 매일 '미처리 0건'을
      //   보고했다 — 상태값만 보고 회신을 안 봤기 때문이다. 판정은 이 한 곳에서만 한다(약속 L21).
      if (_isDoneStatus_(_wantSt) && !_hasRealReply_(_wantMemo)) _wantSt = '확인중';
      if (_wantSt) _fbSh.getRange(rowNo, _cSt + 1).setValue(_wantSt);
      if (_ups[u].memo !== undefined) _fbSh.getRange(rowNo, _cMemo + 1).setValue(String(_ups[u].memo));
      // ★처리 결과를 문의알림방에 정리해 알린다(2026-08-06 GM 지시) — 실질 회신이 담겼을 때 1회만.
      //   접수ID당 캐시로 중복을 막는다(감시기가 3분마다 같은 값을 밀어도 두 번 나가지 않는다).
      if (_isDoneStatus_(_wantSt) && _hasRealReply_(_wantMemo)) {
        try {
          var _dnKey = 'sf_done_' + wantId;
          if (!CacheService.getScriptCache().get(_dnKey)) {
            CacheService.getScriptCache().put(_dnKey, '1', 21600);
            var _dnEsc = function (s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
            _notifyTelegram('✅ <b>실무진 피드백 처리완료</b>'
              + '\n접수번호: ' + _dnEsc(wantId)
              + (_cWho >= 0 && _fbVals[hit][_cWho] ? '\n신고: ' + _dnEsc(_fbVals[hit][_cWho]) : '')
              + (_cBody >= 0 && _fbVals[hit][_cBody] ? '\n내용: ' + _dnEsc(String(_fbVals[hit][_cBody]).slice(0, 120)) : '')
              + '\n\n처리 결과\n' + _dnEsc(String(_wantMemo).slice(0, 500)),
              _staffFeedbackRoom_());
          }
        } catch (e) { /* 알림 실패가 시트 반영을 되돌리지 않는다 */ }
      }
      _done.push(wantId);
    }
    return _json({ ok: true, updated: _done, notFound: _miss });
  }

  // ─── (관리) 유입언어(KO/EN) 칸 생성 + 검증 프로브 — 영문 자체폼 컷오버(배9674 시모, 2026-07-22). 토큰 게이트. ───
  //   op='addcol': 멤버십 '26년 신규문의' + 강습 응답탭(성인 111889422 · WSC 268994754)에 '유입언어' 헤더가 없으면
  //     맨 끝칸에 additive 추가(이름기반·행/기존칸 무변경). 이 칸이 생기면 intake_submit 의 _imSet/_lsSet(['유입언어'])가 기록 시작.
  //   op='probe': body.phone 매칭 행의 성함·유입언어 값을 시트별 반환(라이브 e2e 검증용, 읽기전용).
  if (action === 'cmo_lang_admin') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _claOp = String(body.op || 'addcol');
    var _claTargets = [
      { n: '멤버십 26년 신규문의', sh: _miSheet_() },
      { n: '성인강습 111889422', sh: _lessonSheet_(111889422) },
      { n: 'WSC강습 268994754', sh: _lessonSheet_(268994754) },
      { n: '공간렌트 문의', sh: _rentalIntakeSheet_(true) },
      { n: '비즈니스 문의', sh: _businessIntakeSheet_(true) }
    ];
    var _claRep = {};
    if (_claOp === 'addcol') {
      _claTargets.forEach(function(t){
        if (!t.sh) { _claRep[t.n] = { error: '시트 없음' }; return; }
        var lc = t.sh.getLastColumn();
        var hdr = t.sh.getRange(1, 1, 1, lc).getValues()[0].map(function(v){ return String(v).trim(); });
        var idx = _findColExact_(hdr, ['유입언어']);
        if (idx >= 0) { _claRep[t.n] = { had: true, added: false, col: idx + 1 }; return; }
        t.sh.getRange(1, lc + 1).setValue('유입언어');   // 맨 끝 새칸 헤더만 추가(additive·행 무변경)
        SpreadsheetApp.flush();
        _claRep[t.n] = { had: false, added: true, col: lc + 1 };
      });
    } else if (_claOp === 'probe') {
      var _claPhone = String(body.phone || '').replace(/[^0-9]/g, '');
      _claTargets.forEach(function(t){
        if (!t.sh) { _claRep[t.n] = { error: '시트 없음' }; return; }
        var lr = t.sh.getLastRow(), lc = t.sh.getLastColumn();
        if (lr < 2) { _claRep[t.n] = { rows: 0 }; return; }
        var hdr = t.sh.getRange(1, 1, 1, lc).getValues()[0].map(function(v){ return String(v).trim(); });
        var phI = _findCol_(hdr, ['연락처', '핸드폰', '전화', '휴대폰']);
        var nmI = _findCol_(hdr, ['성함', '이름']);
        var lgI = _findColExact_(hdr, ['유입언어']);
        var data = t.sh.getRange(2, 1, lr - 1, lc).getValues();
        var hits = [];
        for (var r = 0; r < data.length; r++) {
          var ph = phI >= 0 ? String(data[r][phI] || '').replace(/[^0-9]/g, '') : '';
          if (_claPhone && ph === _claPhone) hits.push({ row: r + 2, name: nmI >= 0 ? String(data[r][nmI] || '') : '', lang: lgI >= 0 ? String(data[r][lgI] || '') : '(칸없음)' });
        }
        _claRep[t.n] = { langCol: lgI >= 0 ? lgI + 1 : -1, matches: hits };
      });
    } else {
      return _json({ ok: false, error: 'unknown op: ' + _claOp });
    }
    return _json({ ok: true, op: _claOp, report: _claRep });
  }


  // ─── (일회성 진단) 강습 두 탭(성인·WSC) 타임스탬프 원본 실측 — 시:분:초 결손 행수 확정 ───
  //   배경: 2026-07-18 자체폼 직접쓰기 전환 과도기 코드가 타임스탬프에 날짜만 기록한 버그(09452c5b·a8830062로
  //   현재는 수리됨 — 과거 데이터만 결손). lesson_inquiry_list(_miToISO_ 경유)는 날짜로 잘라내 결손 판별 불가 →
  //   원본 셀 타입·값을 그대로 덤프하는 읽기전용 전용 진단. 쓰기 없음. 2026-07-20 시토(GM 지시).
  if (action === 'cpo_lesson_ts_scan') {
    try {
      var ltsTargets = [
        { gid: LESSON_GID,       type: '성인강습' },
        { gid: LESSON_GID_YOUTH, type: '유소년강습(WSC)' }
      ];
      var ltsOut = [];
      ltsTargets.forEach(function (t) {
        var sh = _lessonSheet_(t.gid);
        var rec = { gid: t.gid, type: t.type, sheetName: null, lastRow: 0, totalRows: 0, missingCount: 0, rows: [] };
        if (!sh) { rec.error = 'sheet_not_found'; ltsOut.push(rec); return; }
        rec.sheetName = sh.getName();
        var lastRow = sh.getLastRow();
        rec.lastRow = lastRow;
        if (lastRow < 2) { ltsOut.push(rec); return; }
        var lastCol = sh.getLastColumn();
        var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
        var ciTs    = _findCol_(hdr, ['타임스탬프']);
        var ciName  = _findCol_(hdr, ['성함', '이름']);
        var ciPhone = _findCol_(hdr, ['연락처', '핸드폰', '전화', '휴대폰']);
        if (ciTs < 0) { rec.error = 'ts_col_not_found'; ltsOut.push(rec); return; }
        var dataN = lastRow - 1;
        var rows = sh.getRange(2, 1, dataN, lastCol).getValues();
        for (var i = 0; i < rows.length; i++) {
          var rowNum = i + 2;
          var r = rows[i];
          var raw = r[ciTs];
          var name  = ciName  >= 0 ? String(r[ciName]  || '') : '';
          var phone = ciPhone >= 0 ? String(r[ciPhone] || '') : '';
          if (!raw && !name && !phone) continue;  // 완전 빈 행 스킵
          rec.totalRows++;
          var valType = (raw instanceof Date) ? 'Date' : ((raw === '' || raw == null) ? 'empty' : 'string');
          var hasTime = false;
          if (raw instanceof Date && !isNaN(raw.getTime())) {
            hasTime = !(raw.getHours() === 0 && raw.getMinutes() === 0 && raw.getSeconds() === 0);
          } else if (valType === 'string') {
            hasTime = /\d{1,2}:\d{2}(:\d{2})?/.test(String(raw));
          }
          if (!hasTime) {
            rec.missingCount++;
            rec.rows.push({
              row: rowNum, valType: valType,
              raw: (raw instanceof Date) ? Utilities.formatDate(raw, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(raw == null ? '' : raw),
              name: name.substring(0, 20), phone: phone
            });
          }
        }
        ltsOut.push(rec);
      });
      return _json({ ok: true, sheets: ltsOut });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── (일회성) 강습 두 탭 타임스탬프 결손 행 복구 — 접수ID(L+yyMMdd-HHmmss)로 역산 ───
  //   위 cpo_restore_lost_timestamps_0718과 동일 패턴(연락처+접수ID 이중확인, 정확히 1건일 때만, 실제 Date
  //   객체 기록, 이미 시:분:초 있으면 스킵). 다만 대상 목록은 python(git 이력 회수)에서 동적으로 넘겨받는다
  //   (조아람 3건·이수진 성인/유소년 2건처럼 매칭 경우의수가 커 하드코딩 불가). 서버는 반드시 ①대상 행의
  //   현재 전화번호가 target.phone과 일치 ②현재 타임스탬프가 아직 시:분:초 없음(경합 재확인) 을 재검증한 뒤에만
  //   쓴다 — 둘 중 하나라도 어긋나면 그 target만 skip(다른 target엔 영향 없음). mode=dryrun(기본)/execute.
  //   2026-07-20 시토(GM 지시).
  if (action === 'cpo_lesson_ts_fill_0720') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var ltfMode = String(body.mode || 'dryrun');
    var ltfTargets;
    try { ltfTargets = JSON.parse(body.targets || '[]'); } catch (e) { return _json({ ok: false, error: 'bad_targets_json' }); }
    if (!Array.isArray(ltfTargets) || !ltfTargets.length) return _json({ ok: false, error: 'no_targets' });

    var ltfNorm = function (p) { return String(p == null ? '' : p).replace(/\D/g, ''); };
    var ltfFmt = function (v) { return (v instanceof Date) ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(v == null ? '' : v); };

    var ltfShCache = {};
    var ltfGetSheetInfo = function (gid) {
      if (ltfShCache[gid]) return ltfShCache[gid];
      var sh = _lessonSheet_(gid);
      if (!sh) return null;
      var lastCol = sh.getLastColumn();
      var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
      var ciTs = _findCol_(hdr, ['타임스탬프']);
      var ciPhone = _findCol_(hdr, ['연락처', '핸드폰', '전화', '휴대폰']);
      var info = { sh: sh, ciTs: ciTs, ciPhone: ciPhone, lastRowBefore: sh.getLastRow() };
      ltfShCache[gid] = info;
      return info;
    };

    var ltfResults = [], ltfSkip = [];
    ltfTargets.forEach(function (t) {
      var info = ltfGetSheetInfo(t.gid);
      if (!info || info.ciTs < 0 || info.ciPhone < 0) { ltfSkip.push({ target: t, reason: 'sheet_or_column_not_found' }); return; }
      var curPhone = info.sh.getRange(t.row, info.ciPhone + 1).getValue();
      if (ltfNorm(curPhone) !== ltfNorm(t.phone)) {
        ltfSkip.push({ target: t, reason: 'phone_mismatch', rowPhoneNow: String(curPhone) }); return;
      }
      var curTs = info.sh.getRange(t.row, info.ciTs + 1).getValue();
      var hasTimeNow = (curTs instanceof Date) && !isNaN(curTs.getTime()) && !(curTs.getHours() === 0 && curTs.getMinutes() === 0 && curTs.getSeconds() === 0);
      if (hasTimeNow) { ltfSkip.push({ target: t, reason: 'already_has_time', currentValue: ltfFmt(curTs) }); return; }
      var m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(String(t.iso || ''));
      if (!m) { ltfSkip.push({ target: t, reason: 'bad_iso' }); return; }
      var newDate = new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10), parseInt(m[4], 10), parseInt(m[5], 10), parseInt(m[6], 10));
      ltfResults.push({ gid: t.gid, row: t.row, name: t.name || '', phone: t.phone, before: ltfFmt(curTs), after: ltfFmt(newDate), afterDate: newDate, ciTs: info.ciTs });
    });

    if (ltfMode === 'dryrun') {
      return _json({
        ok: true, mode: 'dryrun',
        willWrite: ltfResults.map(function (r) { return { gid: r.gid, row: r.row, name: r.name, phone: r.phone, before: r.before, after: r.after }; }),
        skip: ltfSkip
      });
    }
    if (ltfMode === 'execute') {
      var ltfWritten = [], ltfRaceSkip = [];
      ltfResults.forEach(function (r) {
        var info = ltfShCache[r.gid];
        // 쓰기 직전 재확인(경합 방지) — 그 사이 이미 시각이 채워졌으면 절대 덮어쓰지 않음
        var curNow = info.sh.getRange(r.row, r.ciTs + 1).getValue();
        var hasTimeNowB = (curNow instanceof Date) && !isNaN(curNow.getTime()) && !(curNow.getHours() === 0 && curNow.getMinutes() === 0 && curNow.getSeconds() === 0);
        if (hasTimeNowB) { ltfRaceSkip.push({ gid: r.gid, row: r.row, name: r.name, reason: 'race_already_has_time', currentValue: ltfFmt(curNow) }); return; }
        info.sh.getRange(r.row, r.ciTs + 1).setValue(r.afterDate);
        ltfWritten.push({ gid: r.gid, row: r.row, name: r.name, phone: r.phone, before: r.before, after: r.after });
      });
      var ltfRowCounts = {};
      Object.keys(ltfShCache).forEach(function (gid) {
        var info = ltfShCache[gid];
        ltfRowCounts[gid] = { before: info.lastRowBefore, after: info.sh.getLastRow() };
      });
      return _json({
        ok: true, mode: 'execute', writtenCount: ltfWritten.length, written: ltfWritten,
        skip: ltfSkip, raceSkip: ltfRaceSkip, rowCounts: ltfRowCounts
      });
    }
    return _json({ ok: false, error: 'unknown_mode' });
  }

  // ─── (일회성 백업) 강습 팀시트 13개 탭 전량 값 스냅샷 — 행 재정렬 전 필수 선행 ───
  //   배경: LESSON_TEAM_SHEETS 13탭은 왼쪽=IMPORTRANGE(원본 따라 이동)·오른쪽=팀장 직접입력(진행상황·담당,
  //   위치 고정) 구조라, 원본(1.성인강습/2.WSC강습) 행 순서를 바꾸면 왼쪽만 따라 움직여 이름↔진행상황이
  //   어긋날 위험이 있다(CPO-배973 핸드오프 근거). 이동 전 13탭 전체를 읽기전용으로 스냅샷해 사후 대조 근거를
  //   남긴다 — 쓰기 없음. 2026-07-20 시토(GM 지시).
  if (action === 'cpo_lesson_teamsheet_dump') {
    try {
      var tdOut = [];
      LESSON_TEAM_SHEETS.forEach(function (cfg) {
        var rec = { ssId: cfg.ssId, gid: cfg.gid, 유형: cfg.유형, 명: cfg.명, sheetName: null, lastRow: 0, lastCol: 0, headers: [], rows: [], error: null };
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = 'sheet_not_found'; tdOut.push(rec); return; }
          rec.sheetName = sh.getName();
          var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
          rec.lastRow = lastRow; rec.lastCol = lastCol;
          if (lastRow < 1 || lastCol < 1) { tdOut.push(rec); return; }
          var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
          rec.headers = hdr;
          if (lastRow >= 2) {
            var vals = sh.getRange(2, 1, lastRow - 1, lastCol).getDisplayValues();  // 표시값(날짜·서식 포함, 사람이 읽는 그대로) 스냅샷
            rec.rows = vals;
          }
        } catch (e2) { rec.error = e2.message; }
        tdOut.push(rec);
      });
      return _json({ ok: true, sheets: tdOut });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── (일회성 진단) 강습 팀시트 13개 — 각 탭 A~C열 수식 원인분석(왜 P.T 성인만 깨졌는지) ───
  //   읽기전용. getFormulas()로 IMPORTRANGE/QUERY/FILTER 등 실제 수식 문자열을 그대로 반환.
  //   2026-07-20 시토(GM 지시, 실행 없음·분석 전용).
  if (action === 'cpo_lesson_teamsheet_formulas') {
    try {
      var tfOut = [];
      LESSON_TEAM_SHEETS.forEach(function (cfg) {
        var rec = { ssId: cfg.ssId, gid: cfg.gid, 유형: cfg.유형, 명: cfg.명, row1: [], row2: [], error: null };
        try {
          var sh = _sheetByGid_(cfg.ssId, cfg.gid);
          if (!sh) { rec.error = 'sheet_not_found'; tfOut.push(rec); return; }
          var lastCol = Math.min(sh.getLastColumn(), 6);  // A~F열만(왼쪽 IMPORTRANGE 구간 확인용)
          rec.row1 = sh.getRange(1, 1, 1, lastCol).getFormulas()[0];
          rec.row2 = sh.getRange(2, 1, 1, lastCol).getFormulas()[0];
          rec.row1Values = sh.getRange(1, 1, 1, lastCol).getDisplayValues()[0];
        } catch (e2) { rec.error = e2.message; }
        tfOut.push(rec);
      });
      return _json({ ok: true, sheets: tfOut });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── (일회성 진단·읽기전용) 임의 gid 탭의 A1 수식 원문 조회 — P.T성인 어긋남 원인의 중간 탭(예: 1b0XU1o
  //   스프레드시트 안의 'P.T' gid=483045756 등, 팀시트가 직접 참조하는 소스가 아니라 그 사이 중간 종목별
  //   분류탭) 자체가 어떤 수식(QUERY/FILTER 등)으로 gid111889422를 참조하는지 확인용. 2026-07-20 시토.
  if (action === 'cpo_diag_gid_formula') {
    try {
      var dgSsId = String(body.ssId || '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw');
      var dgGid = parseInt(body.gid, 10);
      var dgSh = _sheetByGid_(dgSsId, dgGid);
      if (!dgSh) return _json({ ok: false, error: 'sheet_not_found' });
      var dgLastCol = Math.min(dgSh.getLastColumn(), 4);
      return _json({
        ok: true, sheetName: dgSh.getName(), lastRow: dgSh.getLastRow(), lastCol: dgSh.getLastColumn(),
        row1Formulas: dgSh.getRange(1, 1, 1, dgLastCol).getFormulas()[0],
        row1Values: dgSh.getRange(1, 1, 1, dgLastCol).getDisplayValues()[0],
        row2Formulas: dgSh.getRange(2, 1, 1, dgLastCol).getFormulas()[0],
        row2Values: dgSh.getRange(2, 1, 1, dgLastCol).getDisplayValues()[0]
      });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── (일회성 진단·읽기전용) WSC강습 레거시 구간 — 날짜 문자열 사전식 정렬 결함 범위 실측 ───
  //   'yyyy. M. d ...' 문자열이 zero-pad 없이 저장돼 있어(예 'M. 19' vs 'M. 2') 문자열 비교 시
  //   실제 날짜순과 어긋난다("10.19"가 "10.2"보다 앞에 옴). 전체 결함 범위를 숫자로 확정하기 위해
  //   지정 구간(from~to)을 실제 Date로 파싱해 인접행 역전(뒤 행이 앞 행보다 과거) 건수·위치를 센다.
  //   쓰기 없음. 2026-07-20 시토(GM 지시).
  if (action === 'cpo_diag_wsc_legacy_inversions') {
    try {
      var wiGid = LESSON_GID_YOUTH;
      var wiSh = _lessonSheet_(wiGid);
      if (!wiSh) return _json({ ok: false, error: 'sheet_not_found' });
      var wiFrom = parseInt(body.from || '16', 10);
      var wiTo = parseInt(body.to || String(wiSh.getLastRow()), 10);
      var wiLastCol = wiSh.getLastColumn();
      var wiHdr = wiSh.getRange(1, 1, 1, wiLastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
      var wiCiTs = _findCol_(wiHdr, ['타임스탬프']);
      if (wiCiTs < 0) return _json({ ok: false, error: 'ts_col_not_found' });
      var n = wiTo - wiFrom + 1;
      if (n <= 0 || n > 5000) return _json({ ok: false, error: 'range_too_large_or_invalid', n: n });
      var vals = wiSh.getRange(wiFrom, wiCiTs + 1, n, 1).getValues();
      var prevDate = null, prevRow = null;
      var inversions = [], scanned = 0, blanks = 0;
      for (var i = 0; i < vals.length; i++) {
        var rowNum = wiFrom + i;
        var raw = vals[i][0];
        var d = _parseAnyDate_(raw);
        if (!(d instanceof Date) || isNaN(d.getTime())) { blanks++; continue; }
        scanned++;
        if (prevDate && d.getTime() < prevDate.getTime()) {
          inversions.push({ row: rowNum, thisDate: Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'), prevRow: prevRow, prevDate: Utilities.formatDate(prevDate, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') });
        }
        prevDate = d; prevRow = rowNum;
      }
      return _json({
        ok: true, gid: wiGid, from: wiFrom, to: wiTo, scannedRows: scanned, blankOrUnparsed: blanks,
        inversionCount: inversions.length,
        firstInversions: inversions.slice(0, 10), lastInversions: inversions.slice(-10)
      });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── (일회성 진단) 강습 두 탭(성인·WSC) 자체폼 유입 블록 위치 실측 — 행 재정렬 사전분석 ───
  //   read_rows_by_rownum(FORM_SHEETS 전용)로는 임의 행 범위 원문을 볼 수 있으나 '경계'(자체폼 블록이
  //   어디서 끝나고 레거시 오름차순 블록이 시작되는지)를 자동 판별하진 않는다 — 이 액션은 상단부(자체폼
  //   insertRowAfter(1) 유입 후보)와 하단부(레거시)를 함께 스캔해 실측 경계 후보를 반환한다. 쓰기 없음.
  if (action === 'cpo_lesson_ts_scan_boundary') {
    try {
      var tbTargets = [
        { gid: LESSON_GID, type: '성인강습' },
        { gid: LESSON_GID_YOUTH, type: '유소년강습(WSC)' }
      ];
      var tbOut = [];
      tbTargets.forEach(function (t) {
        var sh = _lessonSheet_(t.gid);
        var rec = { gid: t.gid, type: t.type, lastRow: 0, topBlock: [], tailScan: [] };
        if (!sh) { rec.error = 'sheet_not_found'; tbOut.push(rec); return; }
        var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
        rec.lastRow = lastRow;
        var hdr = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
        var ciTs = _findCol_(hdr, ['타임스탬프']);
        var ciName = _findCol_(hdr, ['성함', '이름']);
        var ciPhone = _findCol_(hdr, ['연락처', '핸드폰', '전화', '휴대폰']);
        var fmtCell = function (raw) {
          if (raw instanceof Date && !isNaN(raw.getTime())) {
            var hasT = !(raw.getHours() === 0 && raw.getMinutes() === 0 && raw.getSeconds() === 0);
            return Utilities.formatDate(raw, 'Asia/Seoul', hasT ? 'yyyy-MM-dd HH:mm:ss' : 'yyyy-MM-dd') + (hasT ? '' : '(시각없음)');
          }
          return String(raw == null ? '' : raw);
        };
        // 상단부(2~60) 전량
        var topN = Math.min(60, Math.max(0, lastRow - 1));
        if (topN > 0) {
          var topRows = sh.getRange(2, 1, topN, lastCol).getValues();
          for (var i = 0; i < topRows.length; i++) {
            var r = topRows[i];
            var nm = ciName >= 0 ? String(r[ciName] || '') : '';
            var ph = ciPhone >= 0 ? String(r[ciPhone] || '') : '';
            if (!nm && !ph) continue;
            rec.topBlock.push({ row: i + 2, ts: fmtCell(ciTs >= 0 ? r[ciTs] : ''), name: nm.substring(0, 15), phone: ph });
          }
        }
        // 하단부(뒤에서부터 역방향 스캔, 최대 400행) — 마지막 non-blank 행부터 위로
        var scanFrom = lastRow;
        var found = 0, probeRows = [];
        var chunk = 100;
        while (scanFrom >= 2 && found < 60) {
          var start = Math.max(2, scanFrom - chunk + 1);
          var n = scanFrom - start + 1;
          var block = sh.getRange(start, 1, n, lastCol).getValues();
          for (var j = block.length - 1; j >= 0; j--) {
            var rr = block[j];
            var rowNum = start + j;
            var nm2 = ciName >= 0 ? String(rr[ciName] || '') : '';
            var ph2 = ciPhone >= 0 ? String(rr[ciPhone] || '') : '';
            if (!nm2 && !ph2) continue;
            probeRows.push({ row: rowNum, ts: fmtCell(ciTs >= 0 ? rr[ciTs] : ''), name: nm2.substring(0, 15), phone: ph2 });
            found++;
            if (found >= 60) break;
          }
          scanFrom = start - 1;
        }
        rec.tailScan = probeRows;  // 최신행(마지막 non-blank)부터 역순
        tbOut.push(rec);
      });
      return _json({ ok: true, sheets: tbOut });
    } catch (e) {
      return _json({ ok: false, error: e.message });
    }
  }

  // ─── (일회성) 타임스탬프 열 시:분:초 표시형식 즉시 적용 — 값엔 시분초 있으나 셀 표시가 날짜전용이라. 2026-07-21 시포·GM ───
  if (action === 'cpo_lesson_ts_format_0721') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var tsfOut = [];
    var tsfGids = [LESSON_GID, LESSON_GID_YOUTH];
    for (var tsfG = 0; tsfG < tsfGids.length; tsfG++) {
      var tsfSh = _lessonSheet_(tsfGids[tsfG]);
      if (!tsfSh) { tsfOut.push({ gid: tsfGids[tsfG], error: 'sheet_not_found' }); continue; }
      var tsfLastRow = tsfSh.getLastRow(), tsfLastCol = tsfSh.getLastColumn();
      var tsfHdr = tsfSh.getRange(1, 1, 1, tsfLastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
      var tsfCi = _findColExact_(tsfHdr, ['타임스탬프']);
      if (tsfCi < 0) tsfCi = 0;   // 폴백=A열
      if (tsfLastRow >= 2) tsfSh.getRange(2, tsfCi + 1, tsfLastRow - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
      tsfOut.push({ gid: tsfGids[tsfG], col: tsfCi + 1, rows: Math.max(tsfLastRow - 1, 0) });
    }
    return _json({ ok: true, sheets: tsfOut });
  }

  // ─── (일회성) 타임스탬프 표시형식+열너비+타임스탬프순 정렬 — 셀 클릭없이 시분초 보이게 + 제자리 정렬(오름차순). 2026-07-21 시포·GM ───
  if (action === 'cpo_lesson_ts_display_sort_0721') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var tdsDoSort = (String(body.sort || 'yes') !== 'no');   // 기본 정렬 수행. body.sort='no'면 형식·너비만.
    var tdsOut = [];
    var tdsGids = [LESSON_GID, LESSON_GID_YOUTH];
    for (var tdsG = 0; tdsG < tdsGids.length; tdsG++) {
      var tdsSh = _lessonSheet_(tdsGids[tdsG]);
      if (!tdsSh) { tdsOut.push({ gid: tdsGids[tdsG], error: 'sheet_not_found' }); continue; }
      var tdsLastRow = tdsSh.getLastRow(), tdsLastCol = tdsSh.getLastColumn();
      var tdsHdr = tdsSh.getRange(1, 1, 1, tdsLastCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
      var tdsCi = _findColExact_(tdsHdr, ['타임스탬프']); if (tdsCi < 0) tdsCi = 0;
      var tdsSorted = false;
      if (tdsLastRow >= 2) {
        // ① 표시형식(시:분:초)
        tdsSh.getRange(2, tdsCi + 1, tdsLastRow - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
        // ② 열 너비 넓히기 — 잘림 없이 시분초 표시
        try { tdsSh.setColumnWidth(tdsCi + 1, 160); } catch (_w) {}
        // ③ 데이터행만 타임스탬프 오름차순 정렬(행 단위·셀 동반 이동). getLastRow(잔여행 포함) 아니라 실제 타임스탬프 있는 마지막 행까지만 — 500행 이후 잔여행 미접촉. keyPhone 저장이라 rowIndex 이동 무해.
        if (tdsDoSort) {
          var tdsTsCol = tdsSh.getRange(2, tdsCi + 1, tdsLastRow - 1, 1).getValues();
          var tdsLastData = -1;
          for (var tdsI = 0; tdsI < tdsTsCol.length; tdsI++) {
            var tdsV = tdsTsCol[tdsI][0];
            if (tdsV instanceof Date || String(tdsV || '').trim() !== '') tdsLastData = tdsI;   // 0-based offset(행2 기준)
          }
          if (tdsLastData >= 1) {   // 데이터 2행 이상
            tdsSh.getRange(2, 1, tdsLastData + 1, tdsLastCol).sort({ column: tdsCi + 1, ascending: true });
            tdsSorted = tdsLastData + 1;
          }
        }
      }
      tdsOut.push({ gid: tdsGids[tdsG], rows: Math.max(tdsLastRow - 1, 0), sorted: tdsSorted });
    }
    return _json({ ok: true, sheets: tdsOut });
  }

  // ─── (일회성·읽기) 강습 시트 구조 진단 — 행 접힘/공백/숨김 원인 파악. 2026-07-21 시포·GM ───
  if (action === 'cpo_lesson_sheet_diag_0721') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var sdOut = [];
    var sdGids = [LESSON_GID, LESSON_GID_YOUTH];
    for (var sdG = 0; sdG < sdGids.length; sdG++) {
      var sdSh = _lessonSheet_(sdGids[sdG]);
      if (!sdSh) { sdOut.push({ gid: sdGids[sdG], error: 'sheet_not_found' }); continue; }
      var sdMax = sdSh.getMaxRows(), sdLast = sdSh.getLastRow(), sdCol = sdSh.getLastColumn();
      var sdTsCi = _findColExact_(sdSh.getRange(1, 1, 1, sdCol).getValues()[0].map(function (v) { return String(v || '').trim(); }), ['타임스탬프']); if (sdTsCi < 0) sdTsCi = 0;
      var sdFirst = -1, sdLastData = -1, sdCount = 0;
      if (sdLast >= 2) {
        var sdVals = sdSh.getRange(2, sdTsCi + 1, sdLast - 1, 1).getValues();
        for (var sdI = 0; sdI < sdVals.length; sdI++) { if (sdVals[sdI][0] instanceof Date) { sdCount++; if (sdFirst < 0) sdFirst = sdI + 2; sdLastData = sdI + 2; } }
      }
      var sdHidden = {};
      [2, 16, 17, 20, 21, 100, 500, 3000, 3062, 3927, sdLast].forEach(function (rn) {
        if (rn >= 1 && rn <= sdMax) { try { sdHidden[rn] = sdSh.isRowHiddenByUser(rn); } catch (_h) { sdHidden[rn] = 'err'; } }
      });
      sdOut.push({ gid: sdGids[sdG], maxRows: sdMax, lastRow: sdLast, dataRows: sdCount, firstDataRow: sdFirst, lastDataRow: sdLastData, hidden: sdHidden });
    }
    return _json({ ok: true, sheets: sdOut });
  }

  // ─── (일회성) 강습 시트 숨김 행 전체 해제(접힘 펴기). dry-run=샘플만·execute=showRows. 2026-07-21 시포·GM ───
  if (action === 'cpo_lesson_unhide_0721') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var uhExec = (String(body.mode || 'dryrun') === 'execute');
    var uhOut = [];
    var uhGids = [LESSON_GID, LESSON_GID_YOUTH];
    for (var uhG = 0; uhG < uhGids.length; uhG++) {
      var uhSh = _lessonSheet_(uhGids[uhG]);
      if (!uhSh) { uhOut.push({ gid: uhGids[uhG], error: 'sheet_not_found' }); continue; }
      var uhMax = uhSh.getMaxRows(), uhCol = uhSh.getLastColumn();
      var uhHdr = uhSh.getRange(1, 1, 1, uhCol).getValues()[0].map(function (v) { return String(v || '').trim(); });
      var uhNi = _findColExact_(uhHdr, ['성함(Name)', '유소년 이름', '성함', '이름']);
      var uhSample = [];
      [100, 1000, 2000, 3000].forEach(function (rn) {
        if (rn <= uhSh.getLastRow()) {
          var ts = uhSh.getRange(rn, 1).getValue();
          var nm = uhNi >= 0 ? uhSh.getRange(rn, uhNi + 1).getValue() : '';
          uhSample.push({ row: rn, ts: (ts instanceof Date) ? Utilities.formatDate(ts, 'Asia/Seoul', 'yyyy-MM-dd HH:mm') : String(ts || ''), name: String(nm || '') });
        }
      });
      if (uhExec) uhSh.showRows(1, uhMax);
      uhOut.push({ gid: uhGids[uhG], maxRows: uhMax, unhidden: uhExec, sample: uhSample });
    }
    return _json({ ok: true, mode: (uhExec ? 'execute' : 'dryrun'), sheets: uhOut });
  }

  // ─── (읽기) 전 행 타임스탬프 오름차순 검증 — gviz가 아닌 GAS로 실제 전 행 순서 확인. 2026-07-21 시포·GM ───
  if (action === 'cpo_lesson_sort_verify_0721') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var svOut = [];
    var svGids = [LESSON_GID, LESSON_GID_YOUTH];
    for (var svG = 0; svG < svGids.length; svG++) {
      var svSh = _lessonSheet_(svGids[svG]);
      if (!svSh) { svOut.push({ gid: svGids[svG], error: 'sheet_not_found' }); continue; }
      var svLast = svSh.getLastRow(); var svCol = svSh.getLastColumn();
      var svTsCi = _findColExact_(svSh.getRange(1, 1, 1, svCol).getValues()[0].map(function (v) { return String(v || '').trim(); }), ['타임스탬프']); if (svTsCi < 0) svTsCi = 0;
      var svViol = 0; var svFirst = null; var svPrev = null; var svData = 0;
      if (svLast >= 2) {
        var svVals = svSh.getRange(2, svTsCi + 1, svLast - 1, 1).getValues();
        for (var svI = 0; svI < svVals.length; svI++) {
          var svV = svVals[svI][0];
          if (!(svV instanceof Date)) continue;
          svData++;
          if (svPrev && svV.getTime() < svPrev.getTime()) {
            svViol++;
            if (!svFirst) svFirst = { row: svI + 2, prev: Utilities.formatDate(svPrev, 'Asia/Seoul', 'yyyy-MM-dd'), cur: Utilities.formatDate(svV, 'Asia/Seoul', 'yyyy-MM-dd') };
          }
          svPrev = svV;
        }
      }
      svOut.push({ gid: svGids[svG], dataRows: svData, violations: svViol, firstViolation: svFirst });
    }
    return _json({ ok: true, sheets: svOut });
  }

  // ─── (일회성) 성인강습 A열 빈 제목 확인·채우기 — 2026-07-20 시포(GM 승인 정리 5건 中 2) ───
  //   mode=probe(기본, 쓰기없음): A열(idx0) 현재값 분포 확인. mode=fill: 로직검증 완료 후에만 '문의일'로 채움
  //   (유소년 WSC탭과 동일 헤더로 통일). 쓰기 직전 헤더가 여전히 빈칸인지 재확인.
  if (action === 'cpo_probe_adult_lesson_col0') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var paMode = String(body.mode || 'probe');
    var paSh = _sheetByGid_('1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', 111889422);
    if (!paSh) return _json({ ok: false, error: 'sheet_not_found' });
    var paLastRow = paSh.getLastRow(), paLastCol = paSh.getLastColumn();
    var paHdr = paSh.getRange(1, 1, 1, paLastCol).getDisplayValues()[0];
    if (paMode === 'fill') {
      var paCurA1 = String(paSh.getRange(1, 1).getValue() || '').trim();
      if (paCurA1 !== '') return _json({ ok: false, error: 'title_already_set_before_write', current: paCurA1 });
      paSh.getRange(1, 1).setValue('문의일');
      return _json({ ok: true, mode: 'fill', titleSet: '문의일' });
    }
    var paDataN = Math.max(0, paLastRow - 1);
    var paCol0 = paDataN > 0 ? paSh.getRange(2, 1, paDataN, 1).getDisplayValues() : [];
    var paBlank = 0, paSample = [];
    for (var pai = 0; pai < paCol0.length; pai++) {
      var v = String(paCol0[pai][0] || '').trim();
      if (v === '') paBlank++; else if (paSample.length < 10) paSample.push(v);
    }
    return _json({ ok: true, lastRow: paLastRow, header0: paHdr[0], header1: paHdr[1], dataCount: paCol0.length, blankCount: paBlank, nonBlankSample: paSample });
  }

  // ─── 문의 목록 ───
  //   ★시각 직렬화 = KST 문자열 고정(배10357 시토 2026-07-27). Date 객체를 obj에 그대로 담아 _json()
  //   (JSON.stringify)에 넘기면 Date.toJSON()이 UTC ISO('...Z')로 바꿔 화면이 9시간 어긋난다
  //   (원본 시트 16:45:21 KST ↔ 과거 응답 07:45:21). lesson_inquiry_list가 이미 쓰는 _miToISOTime_
  //   재사용(새 함수 금지·약속 L01) — Date getter가 스크립트 타임존(Asia/Seoul)을 그대로 읽어 KST 문자열로 낸다.
  if (action === 'inquiry_list') {
    // QA 격리(배195) — qa=1+토큰 일치 시 QA_INQUIRY_SHEET만 읽는다(구글폼 합류·라이브 문의접수
    // 미조회 — QA 저장 왕복 검증 전용 경로. 조건 불일치(=일반 조회)면 기존 동작 그대로).
    const _isQa = _isQaInquiryCall_(body);
    const data = _isQa ? _readQaInquirySheetRows_() : _readInquirySheetRows_();   // 테스트행 제외 단일헬퍼(배209 GM승인 2026-07-30)
    const items = [];
    data.forEach(row => {
      const obj = {};
      INQUIRY_HEADERS.forEach((h, i) => { obj[h] = row[i]; });
      obj['시각'] = _miToISOTime_(obj['시각']);
      items.push(obj);
    });
    if (!_isQa) {
      // 구글폼 문의 합류 (개인정보 제외 — 시각·유형·채널만 노출)
      _collectFormInquiries_().forEach(function(f) {
        items.push({ id: '', 시각: _miToISOTime_(f.시각), 이름: '', 연락처: '', 문의유형: f.문의유형, 내용: '', 유입채널: f.유입채널, 상태: '신규', 메모: '구글폼' });
      });
    }
    return _json({ ok: true, count: items.length, data: items });
  }

  // ─── [진단] PII 마스킹 상태 (비밀값 노출 없음) 2026-06-25 시토 ───
  if (action === 'pii_status') {
    var _pt = String(_accessProp_('ACCESS_TOKEN') || '').trim();
    return _json({ ok: true,
      pii_mask: String(_accessProp_('PII_MASK') || ''),
      token_set: !!_pt,
      masking_active: !_piiFull_('__diag_nokey__'),
      key_valid: !!_pt && String(body.key || '') === _pt   // 입장 게이트 비번 검증용(비밀값 미노출)
    });
  }

  // ─── 문의회원 페이지(CPO): 익명 문의 목록 (A안 공개·이름/전화/메모 0) ───
  //   from/to(YYYY-MM-DD, 옵션) — 2026-07-20 시포. 타임스탬프(B열) 기준 필터(row.timestamp=_miToISO_ 결과,
  //   '타임스탬프' 칼럼을 '날짜'보다 우선탐색하는 _miColIdx_ 순서 그대로 재사용 — A열 '날짜' 문자열 불신 이슈 무관).
  //   미전달 시 기존과 100% 동일(전체 반환) — 하위호환. 부분 지정(from만/to만)도 허용.
  /* 담당자별 문의 집계 — 숫자만 반환(이름·전화·메모·내용 일절 없음). 2026-08-10 GM 지시.
     쓰임: 업무 현황 SSOT 상단 판. 그 화면은 담당자별 건수 4개만 필요한데
     member_inquiry_list 를 부르면 694행 PII 를 통째로 내려보내게 된다 — 그래서 집계 전용 경로를 둔다.
     기간 파라미터(from/to)는 member_inquiry_list 와 같은 규칙(YYYY-MM-DD 문자열 비교). */
  if (action === 'member_inquiry_summary') {
    var msFrom = String(body.from || '').trim();
    var msTo   = String(body.to   || '').trim();
    var msCache = CacheService.getScriptCache();
    var msKey = 'misummary_' + msFrom + '_' + msTo;
    if (!_nc) { var msHit = _cacheGetJson_(msCache, msKey); if (msHit) return _json(msHit); }

    var msRows = _miReadRows_(_miSheet_());
    try { msRows = msRows.concat(_miReadRows_(_miSheetEn_())); } catch (eMsEn) {}

    var msAll = {}, msPeriod = {};
    var msBump = function (bag, owner, status) {
      if (!bag[owner]) bag[owner] = { owner: owner, total: 0, reg: 0, contacting: 0, lost: 0, etc: 0 };
      var b = bag[owner];
      b.total++;
      if (status === 'SUC' || status === '단기SUC') b.reg++;
      else if (status === '컨택중' || status === '신규' || status === '가망') b.contacting++;
      else if (status === 'LOSS') b.lost++;
      else b.etc++;
    };
    msRows.forEach(function (row) {
      var msOwner = String(row.owner || '').trim() || '(미지정)';
      var msStatus = String(row.status || '').trim();
      msBump(msAll, msOwner, msStatus);                 // 누적(전환율 산출용)
      var msTs = String(row.timestamp || '');
      if (!msTs) return;
      if (msFrom && msTs < msFrom) return;
      if (msTo && msTs > msTo) return;
      msBump(msPeriod, msOwner, msStatus);              // 지정 기간
    });
    var msArr = function (bag) {
      return Object.keys(bag).map(function (k) {
        var b = bag[k];
        b.rate = b.total ? Math.round(b.reg / b.total * 1000) / 10 : 0;
        return b;
      }).sort(function (a, b) { return b.total - a.total; });
    };
    var msRes = { ok: true, from: msFrom, to: msTo, count: msRows.length,
                  all: msArr(msAll), period: msArr(msPeriod),
                  at: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm') };
    try { _cachePutJson_(msCache, msKey, msRes, 60); } catch (eMsC) {}
    return _json(msRes);
  }

  if (action === 'member_inquiry_list') {
    var miFrom = String(body.from || '').trim();
    var miTo   = String(body.to   || '').trim();
    var miPeriod = !!(miFrom || miTo);
    // 조회 캐시(축1, TTL 60초) — nocache=1 우회. 미스·실패 시 그대로 시트 재조회 폴백. 2026-07-08 시토.
    //   기간 지정 시 캐시키 분리(micache_from_to) — 무지정 호출의 기존 캐시키('micache')는 그대로 보존(하위호환).
    var miCache = CacheService.getScriptCache();
    var miCacheKey = miPeriod ? ('micache_' + miFrom + '_' + miTo) : 'micache';
    if (!_nc) {
      var miHit = _cacheGetJson_(miCache, miCacheKey);
      if (miHit) return _json(miHit);
    }
    // 한글 '26년 신규문의' + 영문 멤버십 탭 병합 — 영어 문의 누수 수리(2026-07-09 시포·GM). 영문 탭 미존재/에러는 조용히 스킵(무중단).
    var miRows = _miReadRows_(_miSheet_());
    try { miRows = miRows.concat(_miReadRows_(_miSheetEn_())); } catch (eMiEn) {}
    if (miPeriod) {
      // 문자열(YYYY-MM-DD) 범위 비교 — timestamp가 이미 _miToISO_로 정규화돼 사전식=시간순 일치. 빈 타임스탬프는
      // 귀속 불가로 스킵(조용한 오포함 방지) — _lessonScopeFilter_ 의 "파싱 실패는 포함" 정책과 반대 성격
      // (여기는 스캔 누락 방지가 아니라 특정 구간 조회이므로 귀속 불가 행을 넣으면 구간 밖 값이 섞임).
      miRows = miRows.filter(function(row) {
        var ts = row.timestamp;
        if (!ts) return false;
        if (miFrom && ts < miFrom) return false;
        if (miTo   && ts > miTo)   return false;
        return true;
      });
    }
    var _miFull = true;  // 2026-06-25 GM '성함·연락처 다 공개' — 마스킹 해제(무인증 공개 주의·시토 인증게이트 전제)
    var miResult = { ok: true, count: miRows.length, data: miRows, anon: !_miFull, period: miPeriod ? { from: miFrom, to: miTo } : null };
    _cachePutJson_(miCache, miCacheKey, miResult, 60);
    return _json(miResult);
  }

  // ─── 신규 문의 & 등록 현황(CPO): 집계 전용 액션 — 원본 행 미반환, 집계값만 ───
  //   시우 인계(status/briefs/시포_인계_문의등록현황_개편_20260720.md) 1단계 — 근본원인(집계 엔드포인트 부재)
  //   해소용 신설. member_inquiry_list(632건/584KB 전량) 대신 이 액션으로 화면 KPI·분포 렌더 가능.
  //   from/to(YYYY-MM-DD, 옵션) — 둘 다 없으면 전체 누적. 유형 3종(멤버십·성인강습·유소년강습) 개별 집계 + overall 합산.
  //   2026-07-20 시포.
  if (action === 'inquiry_stats') {
    var isFrom = String(body.from || '').trim();
    var isTo   = String(body.to   || '').trim();
    var isPeriod = !!(isFrom && isTo);

    var isCache = CacheService.getScriptCache();
    var isCacheKey = 'is_v1_' + isFrom + '_' + isTo;
    if (!_nc) {
      var isHit = _cacheGetJson_(isCache, isCacheKey);
      if (isHit) return _json(isHit);
    }

    // 직전 동일 길이 구간(전기 대비) — from/to 둘 다 있을 때만 산출. 하나만 지정된 개방구간은 비교 대상 불명확 → 스킵(null).
    var isPrevFrom = '', isPrevTo = '';
    if (isPeriod) {
      var _isFromDt = new Date(isFrom + 'T00:00:00+09:00');
      var _isToDt   = new Date(isTo   + 'T00:00:00+09:00');
      var _isSpanMs = _isToDt.getTime() - _isFromDt.getTime();  // 포함 일수 - 1일치 ms
      var _isPrevToDt   = new Date(_isFromDt.getTime() - 86400000);
      var _isPrevFromDt = new Date(_isPrevToDt.getTime() - _isSpanMs);
      isPrevFrom = Utilities.formatDate(_isPrevFromDt, 'Asia/Seoul', 'yyyy-MM-dd');
      isPrevTo   = Utilities.formatDate(_isPrevToDt,   'Asia/Seoul', 'yyyy-MM-dd');
    }
    // 문자열(YYYY-MM-DD) 범위 판정 — member_inquiry_list from/to 필터와 동일 SSOT 로직(사전식=시간순).
    function _isInRange(ts, from, to) {
      if (!ts) return false;
      if (from && ts < from) return false;
      if (to   && ts > to)   return false;
      return true;
    }
    var _isSucSet = { 'SUC': 1, '단기SUC': 1 };  // 등록 전환 판정 — 두 시트(멤버십·강습) 진행상태 공통 allowed값(ssot/sheet_columns.json)
    function _isSortDist(obj) {
      return Object.keys(obj).map(function(k){ return { label: k, count: obj[k] }; })
        .sort(function(a, b){ return b.count - a.count; });
    }
    // rows[].timestamp(_miToISO_ 결과)·status·channel 셋을 공유하는 멤버십/강습 두 소스에 공통 적용.
    function _isAggregate(rows) {
      var curCount = 0, curConv = 0, prevCount = 0;
      var byStatus = {}, byChannel = {};
      rows.forEach(function(row) {
        var inCur = isPeriod ? _isInRange(row.timestamp, isFrom, isTo) : !!row.timestamp;
        if (inCur) {
          curCount++;
          var st = String(row.status || '').trim() || '(미기재)';
          byStatus[st] = (byStatus[st] || 0) + 1;
          var ch = _canonicalChannel_(row.channel || '');
          byChannel[ch] = (byChannel[ch] || 0) + 1;
          if (_isSucSet[st]) curConv++;
        }
        if (isPeriod && _isInRange(row.timestamp, isPrevFrom, isPrevTo)) prevCount++;
      });
      var deltaPct = (isPeriod && prevCount > 0) ? Math.round((curCount - prevCount) / prevCount * 1000) / 10 : null;
      return {
        count: curCount,
        prevCount: isPeriod ? prevCount : null,
        deltaPct: deltaPct,
        converted: curConv,
        conversionRate: curCount > 0 ? Math.round(curConv / curCount * 1000) / 10 : 0,
        byStatus: _isSortDist(byStatus),
        byChannel: _isSortDist(byChannel)
      };
    }

    // 멤버십 — member_inquiry_list와 동일 소스(한글+영문 탭 병합).
    var isMemberRows = _miReadRows_(_miSheet_());
    try { isMemberRows = isMemberRows.concat(_miReadRows_(_miSheetEn_())); } catch (eIsEn) {}
    // 강습(성인/유소년) — lesson_stats와 동일 소스(한글+영문+자체폼 신규문의 병합). scope=all 상당(연도 제한 없음) —
    //   from/to가 직접 구간을 지정하므로 _lessonScopeFilter_(연도 제한)는 적용하지 않음(과거 연도 조회 시 누락 방지).
    var isAdultRows = _lessonReadRowsMerged_({ type: '성인강습' });
    var isYouthRows = _lessonReadRowsMerged_({ type: '유소년강습' });

    var isTypes = {
      멤버십:   _isAggregate(isMemberRows),
      성인강습: _isAggregate(isAdultRows),
      유소년강습: _isAggregate(isYouthRows)
    };
    var ovCount = 0, ovConv = 0, ovPrev = 0;
    Object.keys(isTypes).forEach(function(k) {
      ovCount += isTypes[k].count;
      ovConv  += isTypes[k].converted;
      if (isTypes[k].prevCount != null) ovPrev += isTypes[k].prevCount;
    });
    var isResult = {
      ok: true,
      generatedAt: _now(),
      periodMode: isPeriod,
      period: { from: isFrom, to: isTo },
      prevPeriod: isPeriod ? { from: isPrevFrom, to: isPrevTo } : null,
      types: isTypes,
      overall: {
        count: ovCount,
        converted: ovConv,
        conversionRate: ovCount > 0 ? Math.round(ovConv / ovCount * 1000) / 10 : 0,
        prevCount: isPeriod ? ovPrev : null,
        deltaPct: (isPeriod && ovPrev > 0) ? Math.round((ovCount - ovPrev) / ovPrev * 1000) / 10 : null
      }
    };
    try { isCache.put(isCacheKey, JSON.stringify(isResult), isPeriod ? 300 : 60); } catch (eIsCache) { /* 캐시 실패 무시 */ }
    return _json(isResult);
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
    // 연락기록 — 헤더 이름 탐색만 사용(위치 폴백 제거, 2026-07-20 시포 — member_inquiry_update와 동일 지뢰라 함께 수리). 행 배열이 짧으면 확장.
    //   못 찾으면 조용히 엉뚱한 칸에 쓰지 않고 로그만 남기고 스킵.
    function _maSetCol(colNames, val) {
      if (val === undefined || val === null || val === '') return;
      var ci = _miColIdx_(maHdr, colNames);
      if (ci < 0) { Logger.log('_maSetCol 스킵(칸 없음): ' + JSON.stringify(colNames) + ' val=' + val); return; }
      while (maRow.length <= ci) maRow.push('');
      maRow[ci] = val;
    }
    var maNow = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');  // 2026-07-18 시간 보존(수기 입력 타임스탬프 폴백)
    if (!body.name && !body.phone) return _json({ ok: false, error: '이름 또는 전화번호 필수' });
    _maSet(['성함','이름'], body.name);
    _maSet(['연락처','전화','휴대폰'], _fmtPhone_(body.phone));  // 하이픈 텍스트로 저장 → 시트가 앞 0 보존
    _maSet(['관심 있는 프로그램 종류','관심프로그램','프로그램'], body.program);
    _maSet(['진행현황','진행상황','진행상태','상태'], body.status || '신규');
    _maSet(['문의채널','유입채널','채널','경로'], body.channel || '유선전화');
    _maSet(['담당','담당자'], body.owner);
    _maSet(['메모','비고','담당자메모'], body.memo);
    // 체험 일정 분리 저장(#4): 체험1 날짜→J, 시간→K / 체험2 날짜→L, 시간→M. 상담=체험1. 2026-07-02 시포·GM.
    _maSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], body.exp1Date);  // J = 체험1 날짜
    _maSet(['체험1 확정시간','체험1'], body.exp1Time);                                          // K = 체험1 시간
    _maSet(['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2'], body.exp2Date);        // L = 체험2 날짜
    _maSet(['체험2 확정시간','체험2'], body.exp2Time);                                          // M = 체험2 시간
    _maSet(['기타 웰페리온에 대한 문의 사항','기타 웰페리온','자유롭게 적어','문의 사항'], body.inquiryContent);  // N = 문의내용(#1)
    _maSetCol(['Contact1'], _fmtContact_(body.contact1));
    _maSetCol(['Contact2'], _fmtContact_(body.contact2));
    _maSetCol(['Contact3'], _fmtContact_(body.contact3));
    _maSet(['타임스탬프','접수일','날짜'], body.timestamp || maNow);
    maSh.appendRow(maRow);
    if (body.status === 'SUC' || body.status === '단기SUC') {
      try { _regUpsert_(body.name, body.phone, body.program); } catch (e) {}
      // 등록 전환 전용 알림 → '문의 알림' 방(수정 경로와 동일 포맷). add는 새 행이라 old/new 비교 불필요. 이름·프로그램·담당만(전화=PII 제외). 2026-06-26 시포.
      try {
        var _maRegChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
        _notifyTelegram('✅ <b>등록 전환</b> — 문의회원이 등록(' + body.status + ')으로 전환\n· 이름: ' + (body.name || '-') + '\n· 프로그램: ' + _teamChip(body.program) + (body.program || '-') + '\n· 담당: ' + (body.owner || '-'), _maRegChatId);
      } catch (e) {}
    }
    try { _notifyTelegram('➕ 전화·직접 문의 추가 — ' + (body.name || '(이름없음)') + ' · ' + (body.phone || '-') + ' · 채널:' + (body.channel || '유선전화')); } catch (e) {}
    // 조회 캐시 무효화(축1) — add 직후 최대 60초 stale 반환 방지(rowIndex 오삭제 위험 차단). 2026-07-08 시토 안전수리.
    //   2026-08-05 시토 — 목록(micache)만 지우던 것을 달력(mccache)까지 한 헬퍼로 통일.
    _miCacheClear_();
    return _json({ ok: true, message: '추가되었습니다.', rowIndex: maSh.getLastRow() });
  }

  // ─── 문의회원 페이지(CPO): 예약 달력 (익명·상담/체험 일정) ───
  if (action === 'member_calendar') {
    var mcMonth = String(body.month || '');  // 'YYYY-MM'
    // 조회 캐시(축1, TTL 60초) — member_inquiry_list(micache)와 동일 TTL. nocache=1 우회.
    //   실측 6.9초(매 호출 재병합 + _memberReconEvents_ 재계산) → 캐시 추가. 월 단위 키(다른 달 조회 오염 방지).
    //   ★쓰기 경로 invalidate 미배선(스코프 밖) — micache처럼 즉시무효화 아님, TTL 60초로만 신선도 보장.
    //   2026-08-05 시토.
    var mcCache = CacheService.getScriptCache();
    var mcCacheKey = 'mccache|' + mcMonth;
    if (!_nc) {
      var mcHit = _cacheGetJson_(mcCache, mcCacheKey);
      if (mcHit) return _json(mcHit);
    }
    // 한글+영문 탭 병합 — 영어 문의 누수 수리(2026-07-09 시포·GM). 영문 탭 미존재/에러는 조용히 스킵(무중단).
    var mcRows = _miReadRows_(_miSheet_());
    try { mcRows = mcRows.concat(_miReadRows_(_miSheetEn_())); } catch (eMcEn) {}
    var mcEvents = [];
    mcRows.forEach(function(row){
      function add(dateStr, kind, timeStr, slot, resIdx, noteStr) {
        if (!dateStr) return;
        if (mcMonth && dateStr.slice(0,7) !== mcMonth) return;
        // rowIndex·memo·owner 동봉 — 달력 일정 클릭 → 상담 모달에서 방문완료·메모 수정용(2026-06-26 CRM)
        // tmin = 시간대별 정렬키(분 단위 정수·미정=null). time 표시 텍스트는 그대로 유지(2026-06-26).
        // slot = 예약1→exp1(J/K)·예약2→exp2(L/M) 미러 슬롯, 3번째+는 r{i}. resIdx=예약 배열 인덱스(리스트 모달 편집 대상). 2026-07-03 시포·GM.
        // source='inquiry' — 문의(신규 예약) 이벤트. 유효회원 재등록상담(source='active')과 구분.
        // note=예약별 내용(칩/패널 표시), memo=행 누적 상담메모(폴백).
        mcEvents.push({ date: dateStr, kind: kind, source: 'inquiry', time: timeStr || '', tmin: _miTminKR_(timeStr), slot: slot || '', resIdx: (resIdx == null ? '' : resIdx), name: row.name || '', phone: row.phone || '', program: row.program, status: row.status, rowIndex: row.rowIndex, memo: row.memo || '', note: noteStr || '', owner: row.owner || '', contact1: row.contact1 || '', contact2: row.contact2 || '', contact3: row.contact3 || '', visited: row.visited, visitDate: row.visitDate || '', gid: row.gid, rowKey: row.rowKey || '' });
      }
      // 예약 리스트(가변) — 각 예약이 독립 이벤트. 예약1·2는 exp1/exp2 미러 슬롯(하위 소비자 안전망). 라벨=예약. 2026-07-03 시포·GM.
      (row.reservations || []).forEach(function(res, ri){
        add(res.date, '예약', res.time, (ri === 0 ? 'exp1' : (ri === 1 ? 'exp2' : 'r' + ri)), ri, res.note);
      });
    });
    // ── 재등록 상담 병합(유효회원 시트) — 재등록상담 날짜/시간 있는 회원을 달력 이벤트로. 기존 신규 이벤트 무손상. 2026-07-03 시포·GM.
    try { _memberReconEvents_(mcMonth).forEach(function(e){ mcEvents.push(e); }); } catch (eRe) {}
    var mcResult = { ok: true, month: mcMonth, count: mcEvents.length, events: mcEvents };
    _cachePutJson_(mcCache, mcCacheKey, mcResult, 60);
    return _json(mcResult);
  }

  // ─── 문의회원 페이지(CPO): 행 수정 (이름·전화·진행상태·관심프로그램·메모·담당·일정) ───
  //   2026-06-22 GM '전체 공개' — 실명·전화도 수정 대상. 빈문자는 의도적 클리어로 간주(undefined만 스킵).
  if (action === 'member_inquiry_update') {
    var muRow = parseInt(body.rowIndex, 10);
    if (!muRow || muRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var muSh = _miResolveSheet_(body.gid, body.rowIndex);  // gid 또는 rowIndex 오프셋으로 물리 시트 라우팅(2026-07-09 시포·GM, 영어 문의 누수 수리)
    if (!muSh) return _json({ ok: false, error: '시트 없음' });
    var muRowRaw = muRow;  // 응답용 원본(오프셋 유지) — 프론트 로컬 매칭 정합. 2026-07-09 시포·GM.
    if (muRow >= _ROW_OFFSET_EN_) muRow -= _ROW_OFFSET_EN_;  // 실제 물리 행으로 디코드(시트 쓰기는 여기부터 물리 행 사용).
    var muHdr = _miHeaders_(muSh);
    var _muPhCi = _miColIdx_(muHdr, ['연락처','전화','휴대폰']);
    // ★★ 지문키(rowKey) 우선 경로(§4 R2) — 타임스탬프+연락처 조합, rowIndex/keyPhone보다 상위 진실.
    //   매칭 1건=그 행으로 확정(아래 keyPhone 검증 스킵) / 0건·2건+=거부(fail-closed). rowKey 미동봉(구클라)이거나
    //   타임스탬프 칸 미탐지 시 아래 기존 keyPhone 경로(봉합 B1/B2 포함)로 그대로 폴백. 2026-07-22 시포(오지목 근본수리).
    var _muRk = _rowKeyParts_(body);
    var _muTsCi = _muRk ? _miColIdx_(muHdr, ['타임스탬프','접수일','날짜']) : -1;
    if (_muRk && _muTsCi >= 0 && _muPhCi >= 0) {
      var _muFpRows = _findRowsByKey_(muSh, _muTsCi, _muPhCi, _muRk.ts, _muRk.phone,
                                      _nameColIdx_(muHdr), _muRk.name);
      if (_muFpRows.length === 1) {
        muRow = _muFpRows[0];
      } else if (_muFpRows.length === 0) {
        return _json({ ok: false, error: 'rowkey-not-found', detail: '행 확인 불가(지문 불일치) — 목록 새로고침 후 다시 시도하세요' });
      } else {
        return _json({ ok: false, error: 'rowkey-ambiguous', detail: '지문키 중복 매칭 — 목록 새로고침 후 다시 시도하세요' });
      }
    } else {
    // ★행키 검증(비파괴·하위호환, 지문키 미동봉/칸 미탐지 시 폴백): keyPhone 동봉 시 대상 행의 현재 전화와 대조 — 삭제/시트편집 후 rowIndex 밀림으로 엉뚱한 회원 덮어쓰기 방지.
    //   keyPhone=편집 전(로드된) 전화. body.phone(새 값)과 별개. keyPhone 미전송이면 기존 동작 폴백(정상 편집 무중단) — 단, 예약 쓰기는 예외(B1 아래).
    //   예약 쓰기 여부(B1 fail-closed 대상 판정) — 예약목록 JSON 또는 체험1·2 날짜/시간 중 하나라도 동봉되면 예약 저장으로 간주. 2026-07-22 시포(오지목 봉합).
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      if (_muPhCi >= 0) {
        var _muRowPh = _normPhone_(muSh.getRange(muRow, _muPhCi + 1).getValue());
        var _muKeyPh = _normPhone_(body.keyPhone);
        if (_muKeyPh && _muRowPh !== _muKeyPh) {
          // rowIndex가 대상과 어긋남(gviz 압축 인덱스·시트 편집 밀림·빈행) → keyPhone으로 올바른 물리 행 복구.
          // 매칭 1건=재지정(저장 성공) / 0건=거부(오수정 방지) / 2건+=모호·첫매칭 강제진행 금지·거부(오지목 봉합 B2). 2026-07-13·2026-07-22 시포(INC-013).
          var _muCount = _countRowsByPhone_(muSh, _muPhCi, _muKeyPh);
          if (_muCount === 1) {
            muRow = _findRowByPhone_(muSh, _muPhCi, _muKeyPh);
          } else if (_muCount >= 2) {
            return _json({ ok: false, error: 'duplicate-phone-ambiguous', detail: '동일 연락처 여러 건 — 새로고침 후 대상 확인 필요' });
          } else {
            return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패(대상 전화 없음) — 목록을 새로고침 후 다시 시도하세요' });
          }
        }
      } else {
        // ★2026-08-03 시토(배294) — '예약 쓰기일 때만' 조건을 뺐다. 대조할 수 없으면 쓰기 종류를
        //   가리지 않고 거부한다. 2026-07-31 배239 가 member_active_update 에 적용한 것과 같은 조치
        //   (형제 2곳이 안 고쳐진 채 남아 있었다). 전화 칸을 못 찾으면 어느 행이 맞는지 알 수 없고,
        //   시트는 동시 편집되므로 client 가 보낸 rowIndex 는 이미 밀려 있을 수 있다.
        return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
      }
    } else {
      // ★2026-08-03 시토(배294) — 위와 같은 조치(바깥 가지). keyPhone 자체가 없으면 대조 불가 →
      //   무조건 거부. 종전엔 '예약 쓰기'만 막고 순수 필드 편집(성함·연락처·진행현황·연락이력·담당자)은
      //   검증 없는 rowIndex 로 그냥 썼다 — 행이 밀려 있으면 **다른 문의고객의 그 칸들이 덮인다**
      //   (2026-07-20 실고객 오삭제 사고와 같은 뿌리).
      //   ▸전화가 비어 있는 행(실측 문의 8건·강습 1건)은 이 거부에 걸리는 게 정상이다 —
      //     대조키가 없으면 쓰지 않고 건너뛴다. 근본 해소는 실무진이 전화번호를 채우는 것.
      //
      // ★2026-08-04 시토 — 딱 하나 예외를 연다: **전화가 비어 있는 행에 그 전화를 채우는 저장.**
      //   위 문장('근본 해소는 실무진이 전화번호를 채우는 것')이 실은 불가능했다 — 채우려면 저장해야
      //   하는데 그 저장이 바로 이 줄에서 막힌다. 막다른 구조였고, 그걸 만든 게 나다.
      //   실사고(2026-08-04): 이경연 실장 이 유상두님의 전화 빈 행(문의 233)에 기본정보를 넣고 저장했는데
      //   여기서 거부돼 어디에도 안 남았다 — GM 이 '사라졌다'로 먼저 발견했다(FB260804-090407).
      //   안전 근거(셋 다 만족해야만 연다):
      //     ①이 요청이 실제로 전화번호를 채우는 요청이고
      //     ②대상 행의 전화 칸이 **지금 비어 있고**(누구의 번호도 덮지 않는다)
      //     ③보내온 이름이 그 행의 이름과 **정확히 같다**(행이 밀렸으면 이름이 안 맞아 막힌다).
      //   → 이 셋이 맞으면 그 행은 '전화로는 못 찾지만 이름으로 확인된 행'이다. 그 외는 전부 종전대로 거부.
      var _muFillPh = _normPhone_(body.phone);
      var _muNmCi2  = _miColIdx_(muHdr, ['성함', '이름']);
      if (_muFillPh && _muPhCi >= 0 && _muNmCi2 >= 0) {
        var _muRowPhNow = _normPhone_(muSh.getRange(muRow, _muPhCi + 1).getValue());
        var _muRowNm    = String(muSh.getRange(muRow, _muNmCi2 + 1).getValue() || '').trim();
        var _muBodyNm   = String(body.name || '').trim();
        if (!_muRowPhNow && _muRowNm && _muBodyNm && _muRowNm === _muBodyNm) {
          Logger.log('row-key 예외 통과(전화 채움): row=' + muRow + ' name=' + _muRowNm);
        } else {
          return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
        }
      } else {
        return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
      }
    }
    }
    function _muSet(colNames, val) {
      if (val === undefined || val === null) return;
      var ci = _miColIdx_(muHdr, colNames);
      if (ci >= 0) muSh.getRange(muRow, ci + 1).setValue(val);
    }
    // 연락기록 — 헤더 이름 탐색만 사용(위치 폴백 제거, 2026-07-20 시포 — 폴백이 한 칸씩 밀려 Contact3 저장 시 '진행현황'(T열)을 덮어쓰던 지뢰). undefined/null 스킵('' 은 클리어).
    //   못 찾으면 조용히 엉뚱한 칸에 쓰지 않고 로그만 남기고 스킵(쓰기 경로라 가장 보수적으로 — 못 찾으면 아무 것도 안 쓴다).
    function _muSetCol(colNames, val) {
      if (val === undefined || val === null) return;
      var ci = _miColIdx_(muHdr, colNames);
      if (ci < 0) { Logger.log('_muSetCol 스킵(칸 없음): ' + JSON.stringify(colNames) + ' val=' + val); return; }
      muSh.getRange(muRow, ci + 1).setValue(val);
    }
    // 등록 전환 감지: 상태 변경 '전' 값 캡처(신규→SUC 실제 전환 시점만 이관·알림 — 중복발화 차단). 2026-06-26 시토·GM.
    var _muStatusCi  = _miColIdx_(muHdr, ['진행현황','진행상황','진행상태','상태']);
    var _muOldStatus = (_muStatusCi >= 0) ? String(muSh.getRange(muRow, _muStatusCi + 1).getValue() || '').trim() : '';
    // ★LOSS 사유 서버 가드 (2026-08-10 시토 · 배491 · GM 지시 2026-08-08 "공백 없이 LOSS 처리 되는지 확인해줘")
    //   화면은 2026-08-05 부터 사유 없이 LOSS 저장을 막는다. 그런데 서버는 상태와 사유를 따로 받아,
    //   화면을 안 거치는 경로(구버전 캐시·스크립트)로 들어오면 사유 공란 LOSS 가 그대로 저장된다.
    //   최종 사유 = 이번에 보낸 값(보냈으면) 또는 시트에 이미 있는 값. 둘 다 비면 아무것도 쓰지 않고 거부한다.
    //   ※쓰기 전에 검사한다 — 뒤에서 막으면 상태만 먼저 바뀌고 사유는 빈 채로 남는다.
    if (String(body.status == null ? '' : body.status).trim() === 'LOSS') {
      var _lgCi  = _miColIdx_(muHdr, ['미등록 사유', '미등록사유']);
      var _lgCur = (_lgCi >= 0) ? String(muSh.getRange(muRow, _lgCi + 1).getValue() || '').trim() : '';
      var _lgNew = (body.lossReason !== undefined) ? String(body.lossReason || '').trim() : _lgCur;
      if (!_lgNew) {
        return _json({ ok: false, error: 'loss-reason-required',
          detail: 'LOSS 로 바꾸려면 사유가 필요합니다 — 목록에서 LOSS 사유를 고른 뒤 다시 저장하세요' });
      }
    }
    _muSet(['성함','이름'], body.name);
    _muSet(['연락처','전화','휴대폰'], _fmtPhoneOrUndef_(body.phone));  // 하이픈 텍스트 저장 → 앞 0 보존(undefined는 스킵)
    _muSet(['관심 있는 프로그램 종류','관심프로그램','프로그램'], body.program);
    _muSet(['진행현황','진행상황','진행상태','상태'], body.status);
    // ★유입경로 쓰기는 폼 소유 칸을 깨지 않는다 — 2026-07-28 시포(GM '계속 동기화 실패 뜨는데' 근본수리).
    //   '4. 웰페리온을 어떤 경로로 알게 되셨나요?'(E열)는 **구글폼이 만든 칸이라 드롭다운 데이터 확인 규칙**이 걸려 있다.
    //   그런데 화면은 이 값을 표준 10버킷으로 줄여 보여준다('네이버 검색·플레이스' → '네이버').
    //   그 줄인 값을 그대로 되쓰면 규칙 위반으로 시트가 거부하고, GAS 는 그 예외를 다음 flush 시점에 던져
    //   **뒤따르던 연락 이력 저장까지 통째로 무너뜨렸다**(실측: 'E642에 입력한 데이터가 데이터 확인 규칙을 위반').
    //   화면엔 '동기화 실패 · 재시도'로만 떠서 원인을 알 수 없었고, 실패한 요청이 큐에 남아 무한 재시도됐다.
    //   ▸처리: 폼 칸에 먼저 쓰되 flush 로 즉시 판정하고, 거부되면 '유입경로(자동)' 칸에 남긴다.
    //     그 칸은 화면 읽기의 3순위 override 라 값이 정상 반영된다(_resolveInquiryChannelRaw_).
    //     어느 쪽도 안 되면 조용히 넘어간다 — 유입경로 하나 때문에 컨택 기록을 잃지 않는다(우선순위 명시).
    if (body.channel !== undefined && body.channel !== null) {
      var _muChanOk = true;
      try {
        _muSet(['문의채널','유입채널','채널','경로'], body.channel);
        SpreadsheetApp.flush();   // 지연 반영이라 여기서 강제해야 이 자리에서 예외를 잡는다
      } catch (eChan) {
        _muChanOk = false;
        Logger.log('유입경로 폼칸 쓰기 거부(데이터 확인 규칙) → 자동칸으로 우회: ' + eChan.message);
      }
      if (!_muChanOk) {
        try { _muSet(['유입경로(자동)','유입경로자동','유입경로_자동'], body.channel); SpreadsheetApp.flush(); }
        catch (eChan2) { Logger.log('유입경로 자동칸 쓰기도 실패 — 건너뜀: ' + eChan2.message); }
      }
    }
    _muSet(['메모','비고','담당자메모'], body.memo);
    _muSet(['담당','담당자'], body.owner);
    // 체험 일정 분리 저장(#4): 체험1 날짜→J, 시간→K / 체험2 날짜→L, 시간→M. 상담=체험1. 2026-07-02 시포·GM.
    _muSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], body.exp1Date);  // J = 체험1 날짜
    _muSet(['체험1 확정시간','체험1'], body.exp1Time);                                          // K = 체험1 시간
    _muSet(['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2'], body.exp2Date);        // L = 체험2 날짜
    _muSet(['체험2 확정시간','체험2'], body.exp2Time);                                          // M = 체험2 시간
    _muSet(['기타 웰페리온에 대한 문의 사항','기타 웰페리온','자유롭게 적어','문의 사항'], body.inquiryContent);  // N = 문의내용(#1)
    // ── 예약 리스트(가변) — 예약목록 셀에 평문 저장 + 날짜를 G·H·I·J 4칸 미러. 하위호환 편집(exp*)만 오면 동기화. 2026-07-03 시포·GM / 2026-07-22 GM(JSON→평문·G~J 미러)
    if (body.reservations !== undefined) {
      var _muRes = _resParse_(body.reservations);
      var _muResCi = _miEnsureCol_(muSh, muHdr, INQ_RES_COL);
      var _muResCell = muSh.getRange(muRow, _muResCi + 1);
      _muResCell.setNumberFormat('@');
      _muResCell.setValue(_resPlainStringify_(_muRes));   // JSON→평문(사람이 읽는 시트)
      // 미러: 예약 날짜를 G(1)·H(2)·I(3)·J(4) 순서대로(최대 4). 시간·메모는 예약목록 평문에만 보존. 빈 슬롯 클리어.
      //   칸 키는 _miReadRows_ 읽기 슬롯(iTour/iExp1/iV2Dt/iExp2)과 동일 배열 재사용 → 쓰기·읽기 라운드트립 정합.
      _muSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], _muRes[0] ? _muRes[0].date : '');               // G
      _muSet(['예약2','체험1 확정시간','체험1'], _muRes[1] ? _muRes[1].date : '');                                              // H
      _muSet(['예약3','시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2'], _muRes[2] ? _muRes[2].date : '');            // I
      _muSet(['예약4','체험2 확정시간','체험2'], _muRes[3] ? _muRes[3].date : '');                                              // J
    } else if (body.exp1Date !== undefined || body.exp1Time !== undefined || body.exp2Date !== undefined || body.exp2Time !== undefined) {
      // 하위호환 경로(상담 모달·구 인라인)가 체험1·2만 편집 → 예약목록 JSON이 이미 있으면 동기화(스테일 방지). 예약3+ 보존.
      var _rcCi = _miColIdx_(muHdr, [INQ_RES_COL]);
      if (_rcCi >= 0) {
        var _prev = _resCellParse_(muSh.getRange(muRow, _rcCi + 1).getValue());   // 양포맷(레거시 JSON·신규 평문)
        var _cellISO = function(names){ var c = _miColIdx_(muHdr, names); return c >= 0 ? _miToISO_(muSh.getRange(muRow, c + 1).getValue()) : ''; };
        var _cellTime = function(names){ var c = _miColIdx_(muHdr, names); return c >= 0 ? _miTime_(muSh.getRange(muRow, c + 1).getValue()) : ''; };
        var _rebuilt = [
          { date: _cellISO(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담']), time: _cellTime(['체험1 확정시간','체험1']), note: (_prev[0] && _prev[0].note) || '' },
          { date: _cellISO(['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2']), time: _cellTime(['체험2 확정시간','체험2']), note: (_prev[1] && _prev[1].note) || '' }
        ];
        for (var _pi = 2; _pi < _prev.length; _pi++) _rebuilt.push(_prev[_pi]);
        var _rcCell = muSh.getRange(muRow, _rcCi + 1);
        _rcCell.setNumberFormat('@');
        _rcCell.setValue(_resPlainStringify_(_rebuilt));
      }
    }
    _muSetCol(['Contact1'], _fmtContactOrUndef_(body.contact1));
    _muSetCol(['Contact2'], _fmtContactOrUndef_(body.contact2));
    _muSetCol(['Contact3'], _fmtContactOrUndef_(body.contact3));
    // ── 연락이력(가변) — 축2: body.contacts(JSON 문자열/배열) 수신 시 저장. 미전송이면 무영향(기존 필드만 갱신).
    //    Contact1/2/3은 위에서 그대로 유지(비파괴·원복 안전) — 신·구 컬럼 병존. 2026-07-08 시포·GM.
    var _muHistPrevCount = 0;
    var _muHistNewArr = null;
    // 연락 이력 저장이 실패했는지 붙들어 둔다(2026-07-25 시포·GM · 실무진 피드백 FB260725-122608 외).
    //   그동안은 아래 catch 가 Logger.log 만 하고 끝나 응답은 ok:true 로 나갔다 — 화면은 '저장'
    //   토스트를 띄우고, 실무진은 저장된 줄 알고 창을 닫았다. 조용한 유실의 마지막 통로다.
    var _muHistErr = '';
    // ★저장 위치 정정(2026-07-20 GM 지적) — 기존 Contact1/2/3(O·P·Q)가 정본이다.
    //   그동안 '연락이력'이라는 칸을 새로 만들어 JSON으로 쌓았는데, 멀쩡한 칸을 두고 새 칸을 만든 것이 잘못이었다.
    //   (실측: 연락이력이 있어 보이는 468행 중 454행은 실제로 Contact1/2/3에서 합성된 값이었고, 진짜 JSON은 17행뿐)
    //   → 앞 3건은 Contact1/2/3에 사람이 읽는 글로 쓴다. 4건째부터만 '연락이력'에 넘긴다(3칸으로는 부족한 경우만).
    //   3건 이하면 연락이력 칸은 비운다 — 같은 내용이 두 곳에 남지 않게(진실은 한 곳).
    if (body.contacts !== undefined) {
      try {
        var _muHistCi = _miColIdx_(muHdr, [CONTACT_HIST_COL]);
        var _muPrevHistArr = (_muHistCi >= 0) ? _resParse_(muSh.getRange(muRow, _muHistCi + 1).getValue()) : [];
        // ★이전 연락 건수는 Contact1/2/3 + 넘침칸을 '합쳐' 센다 (2026-07-28 시토 · GM 지적 '문의알림 또 막 날리네').
        //   2026-07-20 정정으로 앞 3건은 Contact1/2/3 에 쓰고 넘침칸은 3건 이하면 비워 둔다. 그런데 이전 건수를
        //   넘침칸 하나만 보고 세고 있어서, 연락이 1~3건인 회원은 이미 컨택했는데도 이전 건수가 늘 0으로 잡혔다.
        //   → 아래 '1차 컨택 진행' 알림의 0→1 전이 조건이 매 저장마다 참이 되어 같은 사람이 반복 발송됐다
        //   (2026-07-28 실측: 도자연·홍재영 두 건이 분 단위로 재발송). 데이터가 실제로 사는 곳을 세도록 고친다.
        var _muPrevC123 = 0;
        for (var _pci = 0; _pci < 3; _pci++) {
          var _pcCol = _miColIdx_(muHdr, ['Contact' + (_pci + 1)]);
          if (_pcCol < 0) continue;
          if (String(muSh.getRange(muRow, _pcCol + 1).getValue() || '').trim()) _muPrevC123++;
        }
        _muHistPrevCount = _muPrevC123 + _muPrevHistArr.length;
        _muHistNewArr = _resParse_(body.contacts);

        // ★★연락 기록이 줄어드는 쓰기는 거부한다 — 2026-07-28 시포(GM '새로고침하면 CONTACT 날아간다' 마지막 못).
        //   이 블록은 받은 배열로 Contact1/2/3·연락이력을 통째로 다시 쓴다. 그래서 화면이 옛 상태(대개 빈 값)를
        //   실어 보내면 멀쩡한 기록이 지워졌다. 실측 피해: 유경민·김정화·도자연님(세 분 다 '컨택중'인데 기록 0),
        //   그리고 3칸이 찬 회원 65명은 4건째부터 매번 소실. 화면은 같은 날 고쳤지만, 실무진 브라우저에 옛 화면이
        //   떠 있으면 그대로 재발한다 — 그래서 서버에서 막는다(문서가 아니라 코드로 · 약속 L02).
        //   판정: 보낸 건수가 시트 현재 건수보다 적으면 '덜 알고 보낸 것'으로 보고 fail-closed.
        //   ▸일부러 지우는 경우(오타 정리 등)는 화면이 contactsPrev(현재 건수)를 같이 보내 의도를 밝힌다.
        //     그 값이 시트 실제와 맞으면 줄이는 것도 허용한다 — 지금 화면을 보고 지운 게 확실하기 때문이다.
        //   ▸rowKey fail-closed(§4 R2)와 같은 방식 — 확신이 없으면 쓰지 않고 새로고침을 요구한다.
        var _muCPrev = (body.contactsPrev === undefined || body.contactsPrev === null || body.contactsPrev === '')
          ? null : parseInt(body.contactsPrev, 10);
        var _muDeclared = (_muCPrev !== null && !isNaN(_muCPrev) && _muCPrev === _muHistPrevCount);
        if (!_muDeclared && _muHistNewArr.length < _muHistPrevCount) {
          return _json({
            ok: false, error: 'contacts-would-shrink',
            detail: '연락 기록이 지워질 뻔해 저장을 멈췄습니다 — 목록을 새로고침한 뒤 다시 저장해 주세요',
            prev: _muHistPrevCount, incoming: _muHistNewArr.length
          });
        }

        // {date,time,note} → 사람이 읽는 한 줄. 날짜·시각이 없으면 내용만(기존 수기 표기와 같은 모양).
        var _muCFmt = function (e) {
          if (!e) return '';
          var pre = String((e.date || '') + ' ' + (e.time || '')).trim();
          var body_ = _ctByJoin_(String(e.note || '').trim(), e.by);   // 컨택자(배101): '(컨택:이름)' 마커로 평문 보존
          return pre ? (pre + ' ' + body_).trim() : body_;
        };
        // 앞 3건 → Contact1/2/3. 해당 칸이 없으면 만들지 않고 건너뛴다(칸 자동생성 금지 — 이번 사고의 원인).
        for (var _ci = 0; _ci < 3; _ci++) {
          var _cCol = _miColIdx_(muHdr, ['Contact' + (_ci + 1)]);
          if (_cCol < 0) continue;
          muSh.getRange(muRow, _cCol + 1).setValue(_muCFmt(_muHistNewArr[_ci]));
        }
        // 4건째부터만 연락이력에 보관. 3건 이하면 비운다. 칸이 없으면 만들지 않는다.
        var _muOverflow = _muHistNewArr.length > 3 ? _muHistNewArr.slice(3) : [];
        var _muHistCi2 = _miColIdx_(muHdr, [CONTACT_HIST_COL]);
        if (_muHistCi2 >= 0) {
          var _muHistCell = muSh.getRange(muRow, _muHistCi2 + 1);
          _muHistCell.setNumberFormat('@');
          _muHistCell.setValue(_muOverflow.length ? _resStringify_(_muOverflow) : '');
        } else if (_muOverflow.length) {
          // 넘치는데 보관할 칸이 없을 때만 생성(4건 이상인 실사용이 생긴 경우) — 그 외엔 절대 만들지 않는다.
          var _muHistCi3 = _miEnsureCol_(muSh, muHdr, CONTACT_HIST_COL);
          muSh.getRange(muRow, _muHistCi3 + 1).setNumberFormat('@');
          muSh.getRange(muRow, _muHistCi3 + 1).setValue(_resStringify_(_muOverflow));
        }
        // 회원 변경 이력(배327) 배선 — 2026-08-04 시토(배359, 임정은M 컨택내용 8일 5회 소실 조사).
        //   이 블록은 그동안 _memberLog_를 한 번도 부르지 않았다 — member_active_update 등 다른 칸은
        //   다 남는데 CONTACT만 이력이 없어서, 다음에 또 사라지면 이번처럼 '언제 몇 건이 몇 건 됐는지'조차
        //   못 짚는다. 내용은 Contact1/2/3·연락이력 칸 자체가 원본이라 건수만 남긴다(중복 저장 안 함).
        if (_muHistNewArr.length !== _muHistPrevCount) {
          var _muLogNmCi = _miColIdx_(muHdr, ['성함', '이름']);
          _memberLog_([[new Date(), _logWho_(body),
            _muLogNmCi >= 0 ? String(muSh.getRange(muRow, _muLogNmCi + 1).getValue() || '') : '',
            _muPhCi >= 0 ? _logMaskPhone_(muSh.getRange(muRow, _muPhCi + 1).getValue()) : '',
            '연락 이력', _muHistPrevCount + '건', _muHistNewArr.length + '건', '멤버십']]);
        }
      } catch (eHist) {
        // ★삼키지 않는다(2026-07-25) — 실패는 응답에 실어 화면이 빨갛게 알리고 창을 열어두게 한다.
        Logger.log('연락이력 저장 실패: ' + eHist.message);
        _muHistErr = String(eHist && eHist.message ? eHist.message : eHist);
      }
    }
    // 방문 완료 — 진행상황과 독립 칸(방문완료일). 등록(SUC)돼도 방문 기록 유지. body.visited 미전송이면 무변경.
    //   true=방문일자(없으면 오늘) 기록 / false=클리어. 칸 없으면 _miEnsureCol_이 생성. 2026-06-29 시포.
    if (body.visited !== undefined) {
      var _vci = _miColIdx_(muHdr, ['방문완료일']);   // ★칸 자동생성 금지(2026-07-20 GM) — 없으면 건너뛴다
      if (_vci >= 0) muSh.getRange(muRow, _vci + 1).setValue(body.visited ? (body.visitDate || _todayKR_()) : '');
    }
    // 등록 종목 — 등록(SUC) 시 실제 등록한 종목(문의 시 관심프로그램과 별개, 수정 가능). 칸 없으면 자동 생성(GM 수작업 0).
    //   GM 요청(2026-07-18, 시토 대행): "등록 시 어떤 종목을 등록했는지" 기록. 2026-07-18 시토·GM.
    if (body.regProgram !== undefined) {
      // 2026-07-21 시포·GM: 멤버십 시트엔 '등록종목' 칸이 없어(자동생성 금지 정책) 조용히 유실되던 문제 수정.
      //   새 칸을 만들지 않고 기존 '관심 있는 프로그램 종목' 칸을 등록등급으로 갱신(관심프로그램 우선, '등록종목'은 폴백으로 유지).
      var _rpci = _miColIdx_(muHdr, ['3. 관심 있는 프로그램 종목', '관심 있는 프로그램 종목', '관심프로그램', '관심 프로그램', '등록종목']);   // ★칸 자동생성 금지(2026-07-20 GM) — 없으면 조용히 건너뛴다
      if (_rpci >= 0) muSh.getRange(muRow, _rpci + 1).setValue(body.regProgram);
    }
    // ★LOSS 사유 저장 위치 정정(2026-07-20 GM 지적) — 기존 '미등록 사유' 칸이 정본이다.
    //   07-18에 LOSS사유·LOSS사유메모 칸을 새로 만들었는데, 같은 뜻의 '미등록 사유'가 이미 있었다.
    //   기능은 GM이 요청한 게 맞지만 칸을 새로 만든 것은 내 설계 판단 착오였다(실측: 두 칸 모두 데이터 0건).
    //   → 사유와 메모를 '미등록 사유' 한 칸에 합쳐 쓴다. 메모가 있으면 '사유 (메모)' 형태.
    //   칸이 없으면 만들지 않고 건너뛴다 — 칸 자동생성이 이번 사고의 뿌리다.
    //   ★메모 폐기(2026-07-20 GM 확정) — "LOSS사유메모도 필요없어". 사유 하나만 '미등록 사유'에 쓴다.
    //   body.lossReasonNote는 옛 화면이 보내와도 무시한다(칸도 만들지 않는다).
    if (body.lossReason !== undefined) {
      var _lrci = _miColIdx_(muHdr, ['미등록 사유', '미등록사유']);
      if (_lrci >= 0) muSh.getRange(muRow, _lrci + 1).setValue(String(body.lossReason || '').trim());
    }
    // carry-over: 신규→SUC/단기SUC '실제 전환' 시에만 등록현황 탭 이관 + 등록 전환 전용 알림. 2026-06-26 시토·GM.
    //   A안(GM 결재): 유효회원(실계약 정본)에는 자동생성 안 함 — 계약 확정 시 사람 입력. 여기선 깔때기 이관+알림까지만.
    //   _regUpsert_는 멱등(전화키 매칭 갱신·없으면 today 도장) → SUC 저장 시 항상 실행해 등록현황 보장(중복 행 안 생김). 알림만 실제 전환(이전≠SUC) 1회. 프런트는 신규 등록 시에만 status=SUC 전송(불필요 재전송 방지).
    var _muNewStatus = String(body.status == null ? '' : body.status).trim();
    var _isSucNew = (_muNewStatus === 'SUC' || _muNewStatus === '단기SUC');
    var _wasSuc   = (_muOldStatus === 'SUC' || _muOldStatus === '단기SUC');
    // ★carry-over·알림은 시트 행의 실제 값 사용(body 우선, 없으면 행 직독). 달력 모달은 status만 보내므로 body.phone 부재 시
    //   _regUpsert_가 전화키 없이 호출돼 등록현황 미반영 + 알림 빈칸('-') 버그 → 행 직독으로 근본 해결. 2026-06-29 시포.
    //   ★컨택 시작 알림(아래)도 동일 이름/프로그램/담당 재사용 → _isSucNew 여부와 무관하게 항상 계산. 2026-07-07 시토.
    var _coNameCi = _miColIdx_(muHdr, ['성함','이름']);
    var _coPhCi   = _miColIdx_(muHdr, ['연락처','전화','휴대폰']);
    var _coProgCi = _miColIdx_(muHdr, ['관심 있는 프로그램 종류','관심프로그램','프로그램']);
    var _coOwnCi  = _miColIdx_(muHdr, ['담당','담당자']);
    var _coName  = body.name    || (_coNameCi >= 0 ? String(muSh.getRange(muRow, _coNameCi + 1).getValue() || '') : '');
    var _coPhone = body.phone   || (_coPhCi   >= 0 ? String(muSh.getRange(muRow, _coPhCi   + 1).getValue() || '') : '');
    var _coProg  = body.program || (_coProgCi >= 0 ? String(muSh.getRange(muRow, _coProgCi + 1).getValue() || '') : '');
    var _coOwner = body.owner   || (_coOwnCi  >= 0 ? String(muSh.getRange(muRow, _coOwnCi  + 1).getValue() || '') : '');
    if (_isSucNew) {
      // 등록종목(body.regProgram) 우선 — 실제 등록한 종목이 문의 시 관심프로그램(_coProg)과 다를 수 있음. 미전송 시 _coProg 폴백(기존 동작 보존).
      var _coRegProg = (body.regProgram !== undefined && String(body.regProgram).trim()) ? String(body.regProgram).trim() : _coProg;
      // _regUpsert_는 멱등(전화키 존재 시 갱신·없으면 today 도장 추가) → SUC 저장 시 항상 등록현황 보장(과거 누락 건도 재저장으로 복구).
      try { _regUpsert_(_coName, _coPhone, _coRegProg, body.regDate); } catch (e) {}
      // ★A안 해제(2026-08-03 GM 지시) — "새 문의에서 SUC하면 채워야하는 항목값들도 다 들어갈 수 있게".
      //   그동안 SUC는 '26년 등록현황' 탭에만 썼고 유효회원(회원 DB)에는 사람이 나중에 손으로 넣었다.
      //   화면(신규 등록현황·회원관리)은 유효회원만 읽으므로, SUC 처리한 회원이 화면에 안 뜨는 게 그 구조의 결과였다.
      //   ★조건: 화면이 회원 DB 칸(activeProgram)을 실어 보낸 경우에만 쓴다 — 옛 화면·달력 모달처럼 status만
      //   보내는 경로가 빈 껍데기 행을 만들지 않게 한다. 전화키 멱등이라 재저장해도 행이 늘지 않는다.
      //   ▸★2026-08-04 시토 — 실제 쓰기는 아래 블록으로 옮겼다(이 if 밖). 이유는 그 주석 참조.
      // 등록 전환 전용 알림은 '실제 전환(이전≠SUC)' 1회만 — 매 저장 중복 알림 방지. '문의 알림' 방.
      if (!_wasSuc) {
        try {
          var _regChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
          _notifyTelegram('✅ <b>등록 전환</b> — 문의회원이 등록(' + _muNewStatus + ')으로 전환\n· 이름: ' + (_coName || '-') + '\n· 등록종목: ' + _teamChip(_coRegProg) + (_coRegProg || '-') + '\n· 담당: ' + (_coOwner || '-'), _regChatId);
        } catch (e) {}
      }
    }
    // ★유효회원(회원 DB) 반영 — if(_isSucNew) 밖으로 꺼냈다 (2026-08-04 시토 · 배345).
    //   ▸왜: 등록은 **저장이 두 번**으로 갈린다. ①진행상태를 SUC 로 → status 는 오지만 등록종목(activeProgram)은
    //     아직 모른다 ②그 직후 뜨는 '등록 종목' 모달 저장 → activeProgram 은 오는데 **status 는 안 보낸다.**
    //     회원 DB 쓰기가 status 기준(_isSucNew) 안에 있었으므로 ①은 종목이 없어 건너뛰고 ②는 '새 SUC 아님'으로
    //     블록째 건너뛰었다 — **어느 쪽으로도 회원 명단에 안 써졌고, 로그도 알림도 없었다.**
    //     실측(2026-08-04): SUC 186건 중 12건이 회원 명단에 없다(2026-01 ~ 08-03, 유상두님 포함).
    //   ▸고친 방식: '이 저장으로 SUC 가 됐거나(_isSucNew) 이미 SUC 인 행(_wasSuc)' 이면서 등록종목이 실려 오면 쓴다.
    //     activeProgram 조건은 그대로 둔다 — 없애면 회원구분·시작일자가 빈 껍데기 행이 생기고, 그게 2026-07-28
    //     정지원님 중복행 사고(배306)와 같은 자리다. 전화키 멱등이라 재저장해도 행이 늘지 않는다.
    if ((_isSucNew || _wasSuc) && String(body.activeProgram || '').trim()) {
      try {
        // ★2026-08-05 시토(GM 지시) — 여기서만 || _todayKR_() 폴백을 뺐다(직접등록 7945는 그대로 둔다 —
        //   그쪽은 사람이 누른 명시적 등록 행위라 오늘 날짜가 맞다). 이 경로는 이미 SUC인 행의 재저장(예:
        //   등록종목 오타 수정)마다 반복 호출되는데, body.regDate가 안 오면 매번 "오늘"을 억지로 채워
        //   _memberActiveUpsert_가 기존 등록일자를 오늘로 덮어썼다(지문 재료 오염 → 다른 화면 동기화 실패로
        //   보이는 원인). regDate가 비면 _memberActiveUpsert_의 if(regDate && regI>=0) 가드가 그냥 안 쓴다 —
        //   신규 행은 그 함수의 appendRow 경로 자체 기본값(_todayKR_())이 여전히 채운다(무손상).
        _memberActiveUpsert_(_coName, _coPhone, String(body.activeProgram).trim(),
                             body.regDate, body.months, {
          kind:      body.memKind,
          age:       body.memAge,
          regClass:  body.memRegClass,
          locker:    body.memLocker,
          startDate: body.memStartDate
        });
      } catch (eMa) { Logger.log('SUC 유효회원 반영 실패: ' + eMa.message); }
    } else if (_isSucNew && !_wasSuc) {
      // ★건너뛴 사실을 보이게 한다(2026-08-04 시토 · 배345 후속 — GM 지적 12건은 이 조건이 계속 참이라
      //   아무 기록 없이 떨어진 결과였다). activeProgram 조건 자체는 그대로 둔다(위 주석 — 빈 껍데기 행 방지).
      //   전환 순간(!_wasSuc)에만 1회 알린다 — 매번 울리면 실무진이 같은 행을 편집할 때마다 반복 발송된다.
      //   실무진이 '등록 종목' 모달을 마저 저장하면 다음 저장은 _wasSuc=true 로 조건을 통과해 조용히 정상 반영된다.
      //   새 발신기·새 방을 만들지 않는다 — 이 파일이 이미 같은 종류(등록 전환)에 쓰는 채널(TELEGRAM_INQUIRY_CHAT_ID)
      //   그대로 재사용한다. ★운영부(카톡)는 GM PC 로컬 UI 자동화(kakao_report_sender.py)로만 닿아 GAS 서버에서
      //   직접 못 부른다 — 필요하면 그 쪽 다이제스트가 이 방을 읽어 전달하는 별도 배선이 있어야 한다(현재 없음).
      // ★2026-08-10 시포(GM 지적) — 즉시 텔레그램 알림을 뺐다.
      //   ▸왜: 위 주석대로 등록은 저장이 두 번이다(①상태를 SUC 로 ②직후 '등록 종목' 모달 저장).
      //     알림은 ①에서 나가고 ②가 몇 초 뒤 정상 반영하므로, **정상 등록마다 경보가 울렸다.**
      //     GM 지적 원문: "종목이 등록되어서 회원 명단에 되어있는데?"(유선영님 · 010-9595-6325 —
      //     확인 결과 유효회원 명단에 정상 존재). 맞는 경보가 아니라 중간 상태를 쏜 것이다.
      //   ▸대신 어떻게 잡나: 하루가 지나도 여전히 명단에 없는 건만 매일 도는 문의 일일 액션이
      //     한 줄로 모아 보고한다(cpo_report.suc_missing_from_member_list · 실측 19명).
      //     감시를 없앤 게 아니라 **울리는 시점을 옮긴 것**이다. 새 장치는 만들지 않았다(약속 L21).
      Logger.log('SUC 유효회원 반영 보류(등록종목 미수신): ' + (_coName || '-') + ' ' + (_coPhone || '-'));
    }
    // 1차 컨택 알림(축6, 이력-기준으로 일원화): 연락이력 0건 → ≥1건 전이 시 1회만. 2026-07-08 시포·GM.
    //   구 '컨택 시작'(상태=상담중 등 진입 기준) 알림은 중복 방지를 위해 이 이력-기준 알림으로 대체(제거).
    // ★발신 1회 보장(멱등 가드, 2026-07-29 시토·GM 재지적·배10379): 세는 값(_muHistPrevCount===0)이 다시
    //   틀리거나, 동시 저장 두 요청이 같은 순간 나란히 0을 읽어도 두 번 나가지 않도록 '보낸 기록'을
    //   시트에 남기고 잠금 안에서 확인→표시(check-and-set)한다. 표시가 이미 있으면 무조건 건너뛴다.
    if (_muHistNewArr && _muHistPrevCount === 0 && _muHistNewArr.length >= 1) {
      var _fcLock = LockService.getScriptLock();
      if (_fcLock.tryLock(5000)) {
        try {
          var _fcCi = _miEnsureCol_(muSh, muHdr, FIRST_CONTACT_SENT_COL);
          var _fcCell = muSh.getRange(muRow, _fcCi + 1);
          var _fcAlready = String(_fcCell.getValue() || '').trim();
          if (!_fcAlready) {
            // 먼저 표시한 뒤 보낸다 — 발송 자체가 실패해도(네트워크 등) 중복 발신보다 표시 우선(1회 보장이 목적).
            _fcCell.setValue(_korDateTime_(new Date()));
            SpreadsheetApp.flush();
            try {
              var _histFirst = _muHistNewArr[0];
              var _histWhen = ((_histFirst.date || '') + ' ' + (_histFirst.time || '')).trim();
              var _histChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
              _notifyTelegram('📞 <b>1차 컨택 진행</b> — ' + (_coName || '-') + ' (' + _teamChip(_coProg) + (_progNameOnly_(_coProg) || '-') + ')\n일시: ' + (_histWhen || '-') + '\n내용: ' + (_histFirst.note || '-') + (_histFirst.by ? '\n컨택: ' + _histFirst.by : '') + (_coOwner ? '\n배정 담당: ' + _coOwner : ''), _histChatId);
            } catch (eNotify) {
              Logger.log('1차 컨택 알림 발송 실패: ' + eNotify.message);
            }
          }
        } finally {
          _fcLock.releaseLock();
        }
      } else {
        Logger.log('1차 컨택 알림 락 획득 실패(5s) — 이번 저장은 건너뜀(표시 없이 종료, 다음 저장에서 재평가)');
      }
    }
    // 등록 해제(이전 SUC → 신규 비SUC, status 명시 전송 시) — 잘못 등록 되돌리기: 등록현황에서 제거. 2026-06-29 시포.
    if (_wasSuc && !_isSucNew && body.status !== undefined) {
      var _urPhCi = _miColIdx_(muHdr, ['연락처','전화','휴대폰']);
      var _urPhone = (body.keyPhone && String(body.keyPhone)) || (_urPhCi >= 0 ? String(muSh.getRange(muRow, _urPhCi + 1).getValue() || '') : '');
      // ★2026-08-05 시토(GM 지시) — 완전 무음 catch였다(등록 해제 실패가 아무 데도 안 남음). 기록+경보 추가.
      //   새 로그·새 발신기 없음 — Logger.log + 기존 _notifyTelegram 재사용.
      try {
        var _rrResult = _regRemove_(_urPhone);
        if (_rrResult && _rrResult.ok === false) {
          Logger.log('_regRemove_ 거부 — phone=' + _logMaskPhone_(_urPhone) + ' count=' + _rrResult.count);
          try { _notifyTelegram('⚠️ 등록 해제 거부 — 전화 ' + _logMaskPhone_(_urPhone) + ' 매칭 ' + _rrResult.count + '건(2건 이상, 번호 공유 추정). "26년 등록현황"에서 수동 확인 필요. 대상: ' + (_coName || '-')); } catch (eN1) {}
        }
      } catch (e) {
        Logger.log('_regRemove_ 예외 — phone=' + _logMaskPhone_(_urPhone) + ' err=' + e);
        try { _notifyTelegram('⚠️ 등록 해제 처리 중 오류 — 전화 ' + _logMaskPhone_(_urPhone) + '. "26년 등록현황"에서 수동 확인 필요: ' + e); } catch (eN2) {}
      }
    }
    // 조회 캐시 무효화(축1) — 다음 목록 조회부터 최신 반영. 2026-07-08 시토.
    //   2026-08-05 시토 — 달력(mccache)까지 함께 지운다. 상담·체험 일정 저장이 여기를 지나므로
    //   달력을 안 지우면 방금 바꾼 일정이 최대 60초 옛 값으로 보였다.
    _miCacheClear_();
    // 연락 이력 저장이 실패했으면 성공으로 답하지 않는다(2026-07-25 시포·GM). 다른 칸은 이미 저장됐지만
    // 실무진이 알아야 할 것은 '적은 글이 안 들어갔다'는 사실이다 — 화면이 창을 닫지 않고 다시 시도할 수 있다.
    if (_muHistErr) {
      return _json({ ok: false, error: '연락 이력 저장 실패 — 적으신 내용이 저장되지 않았습니다. 창을 닫지 마시고 다시 시도해 주세요.',
                     detail: _muHistErr, rowIndex: muRowRaw, partial: true });
    }
    return _json({ ok: true, rowIndex: muRowRaw, message: '수정되었습니다.' });
  }

  // ─── 유효회원 시트 '미등록사유' 열 드롭다운 목록 동기화 ───
  //   ★2026-08-20 시포 근본수리(GM 지시 · 임정은M 이 여러 날 반복 신고한 "LOSS 사유 적었는데 사라짐").
  //   실측: 화면 드롭다운은 17종인데 시트 그 열의 데이터확인 목록은 11종뿐이었다. 목록 밖 값
  //   (연락처상이함·재등록혜택·시설불만·주차불만·휴회불만·바쁜일정)을 고르면 setValue 가 **조용히
  //   무시**되고 서버는 ok:true 를 돌려준다 — 실무진 화면엔 저장된 듯 보이고 새로고침하면 사라진다.
  //   어떤 감시기도 못 잡던 이유가 이것이다(응답이 성공이라).
  //   ▸목록은 여기 하드코딩하지 않는다 — 정본은 화면 쪽 `_assets/loss_reasons.js` 하나이고, 호출자가
  //     그 파일에서 읽어 options 로 넘긴다(같은 값을 두 곳에 두지 않는다 · 약속 L01).
  //   ▸setAllowInvalid(true) — 목록 밖 값도 **저장은 되게** 한다. 조용한 거부가 이번 사고의 본질이라,
  //     드롭다운은 안내로만 두고 막지는 않는다. 오타는 화면이 드롭다운으로만 입력받아 막는다.
  //   ▸mode=diag 면 현재 목록만 돌려주고 아무것도 쓰지 않는다.
  if (action === 'member_unreg_reason_dv_sync') {
    var dvSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!dvSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var dvHdr = dvSh.getRange(1, 1, 1, dvSh.getLastColumn()).getValues()[0]
      .map(function(v){ return String(v).replace(/\s/g, ''); });
    var dvIx = dvHdr.indexOf('미등록사유');
    if (dvIx < 0) return _json({ ok: false, error: '미등록사유 열 없음', headers: dvHdr });
    var dvCell = dvSh.getRange(2, dvIx + 1);
    var dvCur = dvCell.getDataValidation();
    // getCriteriaValues()[0] 은 목록형이면 배열, 범위 참조형이면 Range 가 온다 — 배열일 때만 목록으로 쓴다.
    var dvCurRaw = dvCur ? dvCur.getCriteriaValues()[0] : null;
    var dvCurList = (dvCurRaw && typeof dvCurRaw.indexOf === 'function') ? dvCurRaw : [];
    if (String(body.mode || '') === 'diag') {
      return _json({ ok: true, mode: 'diag', col: dvIx + 1, current: dvCurList,
                     allowInvalid: dvCur ? dvCur.getAllowInvalid() : null });
    }
    var dvOpts = body.options;
    if (!dvOpts || !dvOpts.length) return _json({ ok: false, error: 'options 필수(정본=_assets/loss_reasons.js)' });
    var dvRule = SpreadsheetApp.newDataValidation()
      .requireValueInList(dvOpts, true).setAllowInvalid(true).build();
    var dvRows = Math.max(1, dvSh.getMaxRows() - 1);
    dvSh.getRange(2, dvIx + 1, dvRows, 1).setDataValidation(dvRule);
    return _json({ ok: true, col: dvIx + 1, rows: dvRows,
                   before: dvCurList, after: dvOpts,
                   added: dvOpts.filter(function(o){ return dvCurList.indexOf(o) < 0; }) });
  }

  // ─── 저장 실패 보고(CPO 0단계 · GM 승인 2026-08-25) ───
  //   왜: 화면에서 시트로 못 보낸 저장 요청은 그 PC 브라우저 안(localStorage)에만 남고 서버엔
  //   흔적이 한 줄도 없었다. 그래서 실무진이 실패 표시를 못 보고 지나가면 그 수정은 영영
  //   시트에 안 들어가고, 우리는 몇 건이 밀려 있는지조차 알 수 없었다(유상두 건·2026-08-22).
  //   여기서는 '무엇이 몇 건 밀렸나'만 받는다 — 회원 데이터를 새로 저장하는 통로가 아니다.
  //   새 시트·새 로그·새 알림을 만들지 않고 이미 있는 회원변경이력에 한 줄로 남긴다(약속 L21).
  //   토큰 없이 받는 대신 append 전용 + 길이 제한 + 브라우저별 시간당 상한으로 막는다.
  if (action === 'client_write_fail') {
    var _cwId = String(body.browserId || '').replace(/[^A-Za-z0-9\-]/g, '').slice(0, 24) || '미상';
    var _cwCache = CacheService.getScriptCache();
    var _cwKey = 'cwf_' + _cwId;
    var _cwN = parseInt(_cwCache.get(_cwKey) || '0', 10);
    if (_cwN >= 20) return _json({ ok: true, skipped: 'rate-limited' });   // 시간당 20줄까지
    _cwCache.put(_cwKey, String(_cwN + 1), 3600);
    // 텔레그램 알림은 그 PC 하루 한 번만 (2026-08-25 GM — "계속 이렇게 오는데?").
    //   시트 기록은 건마다 남긴다(그게 원장이다). 알림은 '이 PC 에 밀린 게 있다'는 신호라 하루 한 번이면 족하다.
    var _cwDayKey = 'cwf_day_' + _cwId;
    var _cwFirstToday = !_cwCache.get(_cwDayKey);
    if (_cwFirstToday) _cwCache.put(_cwDayKey, '1', 21600);   // CacheService 상한 6시간
    var _cwCut = function (v, n) { return String(v == null ? '' : v).slice(0, n); };
    _memberLog_([[new Date(), 'PC ' + _cwId, _cwCut(body.who, 40),
                  _logMaskPhone_(_cwCut(body.phone, 20)),
                  '저장 실패(미전송)', _cwCut(body.reason, 120),
                  '밀린 건수 ' + Math.max(0, Math.min(999, parseInt(body.count, 10) || 0)),
                  '멤버십 회원관리']]);
    // 시트에만 적으면 아무도 안 본다 — 그 PC 에서 이번 시간 첫 실패일 때만 한 줄 알린다
    // (같은 PC 연속 실패는 위 상한 카운터가 이미 막는다 · 새 알림 장치 0).
    // ★반드시 업무보고방으로 (배209 와 같은 사고 재발방지 · 2026-08-25 GM 지적).
    //   이건 우리가 고치라고 보는 내부 신호지 실무진이 읽을 글이 아니다. 기본 방으로 보내면
    //   실무진 알림방에 영문 오류코드가 그대로 떠서 놀라게 만든다 — 실제로 그렇게 샜다.
    if (_cwFirstToday) {
      try {
        _notifyTelegram('⚠️ 저장 못 간 건이 있습니다 — PC ' + _cwId
          + ' · ' + _cwCut(body.who, 20) + ' · ' + _cwCut(body.reason, 60)
          + '\n(이 PC 는 오늘 한 번만 알립니다 · 건별 기록은 회원변경이력 참조)',
          TELEGRAM_REPORT_CHAT_ID);
      } catch (e) {}
    }
    return _json({ ok: true });
  }

  // ─── 문의회원 페이지(CPO): 새 문의 중복 삭제(소프트) ───
  //   ★2026-08-05 GM 지시 — "새 문의에 중복된 건들이 있으면 임정은M 가 삭제 가능하게(비밀번호+이력)".
  //   ★물리 삭제 금지(INC-020 재발방지) — 예전엔 mdSh.deleteRow(mdRow)로 실제 행을 지웠으나, 행번호 밀림으로
  //   실고객 행이 대신 삭제된 사고가 있었다. 이제는 절대 deleteRow를 하지 않는다 — 진행현황 칸에
  //   MI_DUP_DELETED_STATUS 마커만 쓰고, 목록·집계 소비처(_miReadRows_ 등 4곳, 위 grep 참조)가 그 값을 제외한다.
  //   되돌리기 = 회원변경이력(MEMBER_LOG_SHEET)에서 이전값 확인 후 member_inquiry_update로 그 값 재기재.
  if (action === 'member_inquiry_delete') {
    var mdRow = parseInt(body.rowIndex, 10);
    if (!mdRow || mdRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var mdSh = _miResolveSheet_(body.gid, body.rowIndex);  // gid 또는 rowIndex 오프셋으로 물리 시트 라우팅(2026-07-09 시포·GM, 영어 문의 누수 수리)
    if (!mdSh) return _json({ ok: false, error: '시트 없음' });
    if (mdRow >= _ROW_OFFSET_EN_) mdRow -= _ROW_OFFSET_EN_;  // 실제 물리 행으로 디코드. 2026-07-09 시포·GM.
    // ★행키 검증(필수·예외 없음, INC-020 재발방지 2026-07-20): keyPhone 미전송/빈값이면 대조 없이 무조건 거부.
    //   구버전은 keyPhone 미전송 시 하위호환으로 검증을 생략해 통과시켰고, 동시접근으로 행이 밀린 상태에서
    //   그 폴백이 실사용돼 실고객 문의 2건이 삭제되는 사고(INC-020)로 이어짐 — 폴백 완전 제거.
    if (body.keyPhone === undefined || String(body.keyPhone) === '') {
      return _json({ ok: false, error: 'keyPhone 필수 — 대조 없이 삭제 불가' });
    }
    // ★비밀번호 게이트(매회 서버검증, 세션 통과 아님) — 새 인증체계를 만들지 않는다(약속 L21).
    //   _staffFeedbackWriteAuthed_(2026-08-04 시토)와 동일 패턴 재사용: 사내 게이트 비밀번호
    //   (_assets/gate.js GATE_PW ↔ ScriptProperties STAFF_GATE_PW, 정본=ScriptProperties)를 그대로 쓴다.
    //   새 비밀값을 코드에 평문 추가하지 않음 — 이 폴백 리터럴은 gate.js에 이미 커밋돼 있던 것과 동일.
    // ★삭제 전용 번호(GM 지시 2026-08-25) — 이경연 실장·임정은M 두 분이 중복 문의를 직접 지우실 수 있게 연다.
    //   공용 게이트 번호를 그대로 드리지 않는 이유: 그 번호는 다른 쓰기 관문과 함께 쓰여, 새면 삭제 말고도
    //   열린다. 이 번호는 이 액션 하나에만 통한다. 삭제 자체는 되돌릴 수 있고(행은 남는다) 실행자 이름이
    //   회원변경이력에 남으므로, 두 분께 열어도 되돌릴 수 없는 위험은 없다.
    var _mdGatePw = _accessProp_('STAFF_GATE_PW') || 'wellperion!@345';
    var _mdStaffPw = _accessProp_('MEMBER_DELETE_PW') || '0914';
    if (String(body.password || '') !== _mdGatePw && String(body.password || '') !== _mdStaffPw) {
      return _json({ ok: false, error: '비밀번호가 올바르지 않습니다.' });
    }
    // ★쓰기 직렬화(INC-020 재발방지 ③, 2026-07-20): 범위확인→전화대조→쓰기 사이에 동시 호출이 같은 시트에
    //   행을 밀어넣으면(삽입·삭제) 검증 통과 후 엉뚱한 행이 바뀔 수 있다 — 락을 잡고 검증부터 쓰기까지
    //   한 번의 원자 구간으로 묶는다. 락 획득 실패 시 쓰지 않고 재시도 요청(무음 스킵 금지).
    var _mdLock = LockService.getScriptLock();
    if (!_mdLock.tryLock(8000)) return _json({ ok: false, error: 'locked', detail: '다른 쓰기 작업 진행 중 — 잠시 후 다시 시도' });
    var _mdName = '', _mdPhoneMasked = '', _mdBeforeStatus = '';
    try {
      if (mdRow > mdSh.getLastRow()) return _json({ ok: false, error: '행 범위 초과' });
      var _mdHdr = _miHeaders_(mdSh);
      // ★지문키(rowKey) 대조 — 중복전화(동일 번호 다수행)면 전화만으론 행을 구분 못해 인접 실고객 오삭제
      //   위험이 남는다(INC-020 재발경로). rowKey 있으면 시각+전화 동시일치 물리행을 확정해 mdRow를 덮어쓴다
      //   (rowIndex 불신). 없으면(rowKey 미동봉 구클라) 아래 기존 전화-only 폴백 대조로 그대로 진행(비파괴·하위호환).
      //   2026-07-22 시포(오지목 근본수리 R2).
      var _mdParts = _rowKeyParts_(body);   // {ts, phone} 또는 null
      if (_mdParts) {
        var _mdTsCi = _miColIdx_(_mdHdr, ['타임스탬프','timestamp','Timestamp']);
        var _mdPhCi2 = _miColIdx_(_mdHdr, ['연락처','전화','휴대폰','Mobile Phone Number','Mobile Phone','Phone']);
        if (_mdTsCi < 0 || _mdPhCi2 < 0) return _json({ ok:false, error:'열 없음(지문키 대조 불가)' });
        var _mdHits = _findRowsByKey_(mdSh, _mdTsCi, _mdPhCi2, _mdParts.ts, _mdParts.phone,
                                      _nameColIdx_(_mdHdr), _mdParts.name);
        if (_mdHits.length === 0) return _json({ ok:false, error:'rowkey-not-found', detail:'대상 없음 — 새로고침 후 재시도' });
        if (_mdHits.length > 1) return _json({ ok:false, error:'rowkey-ambiguous', detail:'동일 시각+전화 다수 — 확인 필요' });
        mdRow = _mdHits[0];   // 지문키로 물리행 확정(rowIndex 불신)
      }
      // (else: 기존 전화-only 대조 폴백 그대로 유지 — rowKey 미동봉 구클라)
      var _mdPhCi = _miColIdx_(_mdHdr, ['연락처','전화','휴대폰','Mobile Phone Number','Mobile Phone','Phone']);
      var _mdRowPh = (_mdPhCi >= 0) ? _normPhone_(mdSh.getRange(mdRow, _mdPhCi + 1).getValue()) : '';
      var _mdKeyPh = _normPhone_(body.keyPhone);
      if (!_mdRowPh || _mdRowPh !== _mdKeyPh) {
        return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패(대상 전화 불일치/불명) — 목록 새로고침 후 다시 시도' });
      }
      var _mdStCi = _miColIdx_(_mdHdr, ['진행현황','진행상황','진행상태','상태']);
      if (_mdStCi < 0) return _json({ ok: false, error: '진행현황 칸 없음(소프트 삭제 불가)' });
      var _mdNmCi = _miColIdx_(_mdHdr, ['성함','이름']);
      _mdName = _mdNmCi >= 0 ? String(mdSh.getRange(mdRow, _mdNmCi + 1).getValue() || '') : '';
      _mdPhoneMasked = _logMaskPhone_(mdSh.getRange(mdRow, _mdPhCi + 1).getValue());
      _mdBeforeStatus = String(mdSh.getRange(mdRow, _mdStCi + 1).getValue() || '').trim() || '(미기재)';
      // ★물리 삭제 금지(INC-020) — deleteRow 대신 상태 마커만 쓴다. 행은 그대로 남아 언제든 되돌릴 수 있다.
      mdSh.getRange(mdRow, _mdStCi + 1).setValue(MI_DUP_DELETED_STATUS);
    } finally {
      _mdLock.releaseLock();
    }
    // 조회 캐시 무효화(축1) — 쓰기 직후 최대 60초 stale 반환 방지. 2026-07-08 시토 안전수리.
    //   2026-08-05 시토 — 달력(mccache)까지 함께 지운다(삭제된 문의의 예약이 달력에 남지 않게).
    _miCacheClear_();
    // ★회원 변경 이력(기존 _memberLog_ 재사용, 새 로그·새 시트 없음) — 언제·누가(_logWho_, staff 미동봉이면 '자동'이 아니라
    //   프론트가 항상 staff를 실어보내므로 실행자명)·무엇을(이름·전화 뒷4자리 마스킹)·왜(중복 삭제)·전후 상태.
    _memberLog_([[new Date(), _logWho_(body), _mdName, _mdPhoneMasked,
                  '중복 삭제(소프트)', _mdBeforeStatus, MI_DUP_DELETED_STATUS, '멤버십 새 문의']]);
    try { _notifyTelegram('🗑 새 문의 중복 삭제(소프트, 목록 제외·되돌리기 가능) — ' + (_mdName || '(이름없음)') + ' · 처리: ' + _logWho_(body)); } catch (e) {}
    return _json({ ok: true, rowIndex: mdRow, message: '삭제되었습니다(목록에서 제외 · 되돌리기 가능).' });
  }

  // ─── 강습문의 페이지(CPO): 전체 목록 (성인 강습 문의 + 관리 필드) ───
  if (action === 'lesson_inquiry_list') {
    // 조회 캐시(축1, TTL 60초) — type+scope별 키(청크 분할, 응답이 100KB 넘음). nocache=1 우회.
    //   미스·실패 시 그대로 시트 재조회 폴백. 2026-07-08 시토.
    var liType = String(body.type || '');
    var liScope = (String(body.scope || '') === 'all') ? 'all' : 'year';
    var liCache = CacheService.getScriptCache();
    var liCacheKey = 'licache|' + liType + '|' + liScope;
    if (!_nc) {
      var liHit = _cacheGetJson_(liCache, liCacheKey);
      if (liHit) return _json(liHit);
    }
    var liRows = _lessonScopeFilter_(_lessonReadRowsMerged_(body), body);
    // 종목 표준 버킷 — 프론트 칩 그룹/필터용(원문 sport 필드는 표 표시용으로 유지). 2026-06-27 시포.
    liRows.forEach(function(r){ var b = _sportBuckets_(r.sport); r.bucket = (b && b.length) ? b[0] : '기타'; });
    var liResult = { ok: true, count: liRows.length, data: liRows };
    _cachePutJson_(liCache, liCacheKey, liResult, 60);
    return _json(liResult);
  }

  // ─── 강습 등록현황·회원 명단(CPO): 팀시트 상태열 '등록'/'SUC' 행 → 종목별 집계 + 회원 명단 ───
  //   _collectLessonRegByName_ 의 상태열 탐지(고유값 2~30 + _isLessonStatusVal_ 최다 열) 동일 재사용.
  //   시트 미연결/상태열 미발견 종목은 registered=null(0 날조 금지). PII 노출 OK(전체공개 2026-06-22). 2026-06-27 시포.
  if (action === 'lesson_registered_roster') {
    var lrrType = String(body.type || '성인강습');
    // ★서버 캐시(2026-07-23 GM '속도만 좀 빨랐으면') — 이 액션은 팀시트 13개를 전부 열고 문의 시트를
    //   병합·조인하느라 실측 17~24초가 걸린다. 명단은 초 단위로 바뀌는 값이 아니라 캐시가 맞다.
    //   ⚠️ CacheService 는 한 칸 100KB 한계라 명단(1,100건 ≈ 170KB)이 안 들어간다 → 나눠 담는다.
    //   fresh=1(화면 '새로고침' 버튼)이면 캐시를 건너뛰고 새로 만든다 — 방금 SUC 한 회원이 안 보이는 일 없게.
    var LRR_CACHE_TTL = 600;   // 10분
    var lrrCacheKey = 'lesson_roster_v3_' + lrrType;
    var lrrFresh = (String(body.fresh || '') === '1' || String(body.fresh || '') === 'true');
    if (!lrrFresh) {
      try {
        var cch = CacheService.getScriptCache();
        var meta = cch.get(lrrCacheKey + '_n');
        if (meta) {
          var parts = [], nP = parseInt(meta, 10), okAll = true;
          for (var cp = 0; cp < nP; cp++) {
            var seg = cch.get(lrrCacheKey + '_' + cp);
            if (seg === null) { okAll = false; break; }
            parts.push(seg);
          }
          if (okAll && parts.length) {
            var hit = JSON.parse(parts.join(''));
            hit.cached = true;
            return _json(hit);
          }
        }
      } catch (eC) { /* 캐시 사고는 무시하고 정상 계산으로 */ }
    }
    var lrrDisplay = LESSON_DISPLAY[lrrType] || [];
    var lrrCfgByName = {};
    LESSON_TEAM_SHEETS.forEach(function(c){ lrrCfgByName[c.명] = c; });
    var lrrBySport = [];
    var lrrRoster = [];
    var lrrLedger = null;  // 발레·바레 등 팀시트 없는 종목: 등록원장 기반. 지연 로드.
    lrrDisplay.forEach(function(item){
      var rec = { 명: item.명, registered: null, sheetFound: false, external: !!item.external, note: item.note || '' };
      var cfg = item.sheet ? lrrCfgByName[item.sheet] : null;
      if (!cfg) {
        // 발레·바레(ledger:true, external 해제): 등록원장(강습 등록현황) SUC 명단으로 집계·표시.
        if (item.ledger) {
          if (lrrLedger === null) lrrLedger = _ledgerRosterByType_(lrrType);
          var lgList = lrrLedger[item.명] || [];
          rec.registered = lgList.length;  // 원장 기반(0도 실측·roster 없으면 0에서 누적)
          lgList.forEach(function(m){ lrrRoster.push({ sport: item.명, name: m.name, phone: m.phone, status: m.status }); });
        }
        lrrBySport.push(rec); return;  // 그 외 sheet:null(미연결) → registered=null 유지
      }
      try {
        var sh = _sheetByGid_(cfg.ssId, cfg.gid);
        if (!sh) { lrrBySport.push(rec); return; }
        rec.sheetFound = true;
        var last = sh.getLastRow(), lastCol = sh.getLastColumn();
        if (last < 2 || lastCol < 1) { rec.registered = 0; lrrBySport.push(rec); return; }
        var data = sh.getRange(1, 1, last, lastCol).getValues();
        var headers = data[0];
        // 상태열 탐지 — _collectLessonRegByName_ 동일(고유값 2~30 + 코드형 상태값 최다 열)
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
        if (best < 0) { lrrBySport.push(rec); return; }  // 상태열 못 찾음 → null 유지(0 날조 금지)
        var iName  = _findCol_(headers, ['성함', '이름', '성명']);
        var iPhone = _findCol_(headers, ['연락처', '전화', '휴대폰']);
        // ★헤더 이름으로 못 찾으면 값 모양으로 찾는다(2026-07-23 시포 · GM 지적으로 발견).
        //   실측: 수영 팀시트만 헤더가 맞아 이름·연락처가 나오고, 골프·P.T·필라테스·스쿼시·
        //   아쿠아로빅·체조 등 나머지 팀시트는 전부 미매칭 → 등록 명단 735건이 '누구인지 모름'
        //   상태로 떠 있었다(성인 372 · 유소년 363). 팀시트는 강사팀이 각자 만들어 헤더가 제각각이라
        //   이름 목록을 늘리는 방식으론 또 새는다 → 상태열을 이미 값으로 자동 탐지하는 것과 같은 방식.
        //   전화=010 형태 비율, 이름=2~4자 한글 비율로 판정하고, 둘 다 상태열은 제외한다.
        var _lrrColVals = function(ci) {
          var out = [];
          for (var rv = 1; rv < data.length; rv++) {
            var s = String(data[rv][ci] == null ? '' : data[rv][ci]).trim();
            if (s) out.push(s);
          }
          return out;
        };
        var _lrrPickCol = function(test) {
          var pick = -1, pickRate = 0;
          for (var cc = 0; cc < lastCol; cc++) {
            if (cc === best) continue;                 // 상태열 제외
            var vals = _lrrColVals(cc);
            if (vals.length < 3) continue;             // 표본 부족 → 판정 안 함
            var hit = 0;
            for (var vi = 0; vi < vals.length; vi++) { if (test(vals[vi])) hit++; }
            var rate = hit / vals.length;
            if (rate >= 0.6 && rate > pickRate) { pickRate = rate; pick = cc; }
          }
          return pick;
        };
        if (iPhone < 0) iPhone = _lrrPickCol(function(v){ return /01[016-9][-.\s]?\d{3,4}[-.\s]?\d{4}/.test(v.replace(/\s/g, '')); });
        if (iName < 0)  iName  = _lrrPickCol(function(v){ return /^[가-힣]{2,4}$/.test(v); });
        if (iName >= 0 && iName === iPhone) iName = -1;   // 같은 칸이면 이름 판정 포기(오표시 금지)
        rec.nameCol = iName >= 0 ? String(headers[iName] || ('열' + _colLetter_(iName))) : null;   // 진단용
        rec.phoneCol = iPhone >= 0 ? String(headers[iPhone] || ('열' + _colLetter_(iPhone))) : null;
        var reg = 0;
        for (var r2 = 1; r2 < data.length; r2++) {
          var sv = data[r2][best];
          if (!_isLessonReg_(sv)) continue;
          reg++;
          lrrRoster.push({
            sport:  item.명,
            name:   iName  >= 0 ? String(data[r2][iName] || '') : '',
            phone:  iPhone >= 0 ? _fmtPhone_(data[r2][iPhone]) : '',
            status: String(sv == null ? '' : sv).trim()
          });
        }
        rec.registered = reg;  // 시트·상태열 존재 → 0도 실측치(정직)
      } catch (e) { rec.error = String(e); }  // 접근 실패 → registered=null 유지
      lrrBySport.push(rec);
    });
    // 횟수·유효기간 조인(GM 2026-07-22): 로스터(팀시트)는 종목·이름·전화·상태만 담는다. SUC 시 문의행에 기록된
    //   등록회수/유효기간을 전화 매칭으로 붙여 '강습 회원 관리'에 표시(GM이 SUC 모달에 입력한 추가내용 반영).
    try {
      var lrrMainGid = (lrrType === '유소년강습' || lrrType === '유소년' || lrrType === 'youth') ? 268994754 : 111889422;
      var lrrMainSh = _lessonSheet_(lrrMainGid);
      if (lrrMainSh) {
        var lrrMh = lrrMainSh.getRange(1, 1, 1, lrrMainSh.getLastColumn()).getValues()[0];
        var lrrPi = _findCol_(lrrMh, ['연락처', '전화', '휴대폰']);
        var lrrCi = _findCol_(lrrMh, ['횟수', '등록회수']);  // 신칸 '횟수' 우선(2026-08-25), 구칸 '등록회수'는 과거행 폴백.
        var lrrEi = _findCol_(lrrMh, ['종료일', '유효기간']);  // 신칸 '종료일' 우선, 구칸 '유효기간'은 과거행 폴백.
        // ★조인 확장(2026-07-23 GM: '정보가 너무 단출하다') — 팀시트는 종목·이름·전화·상태 4칸뿐이라
        //   문의 시트에 이미 있는 내용을 전화 매칭으로 더 붙인다. 새 시트·새 칸 0(읽기만).
        var lrrTi = _findCol_(lrrMh, ['타임스탬프', '문의일']);        // 문의일(등록 전 최초 접점)
        var lrrAi = _findCol_(lrrMh, ['나이', '연령']);                 // 나이(연령대)
        var lrrOi = _findCol_(lrrMh, ['지정 강사', '지정강사', '관리담당']);  // 담당 강사
        var lrrWi = _findCol_(lrrMh, ['희망하시는 레슨 시간', '희망 시간', '레슨 시간']);
        var lrrLast2 = lrrMainSh.getLastRow();
        if (lrrPi >= 0 && lrrLast2 >= 2) {
          var lrrMd = lrrMainSh.getRange(2, 1, lrrLast2 - 1, lrrMainSh.getLastColumn()).getValues();
          var _lrrCell = function(row, ci) {
            if (ci < 0) return '';
            var v = row[ci];
            if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
            return String(v == null ? '' : v).trim();
          };
          var lrrRegMap = {};
          for (var lm = 0; lm < lrrMd.length; lm++) {
            var lp = _normPhone_(lrrMd[lm][lrrPi]); if (!lp) continue;
            var ent = {
              regCount:  _lrrCell(lrrMd[lm], lrrCi),
              regExpire: _lrrCell(lrrMd[lm], lrrEi),
              inqDate:   _lrrCell(lrrMd[lm], lrrTi),
              age:       _lrrCell(lrrMd[lm], lrrAi),
              owner:     _lrrCell(lrrMd[lm], lrrOi),
              wishTime:  _lrrCell(lrrMd[lm], lrrWi)
            };
            var any = false;
            for (var ek in ent) { if (ent[ek]) { any = true; break; } }
            if (any) lrrRegMap[lp] = ent;   // 최근 행(뒤) 우선
          }
          lrrRoster.forEach(function (m) {
            var mp = _normPhone_(m.phone);
            var e = mp && lrrRegMap[mp];
            if (!e) return;
            m.regCount = e.regCount; m.regExpire = e.regExpire;
            m.inqDate = e.inqDate; m.age = e.age; m.owner = e.owner; m.wishTime = e.wishTime;
          });
        }
      }
    } catch (eJoin) { /* 조인 실패 → 횟수/유효기간 미표기(무중단) */ }

    // ═══ 수강 기록을 '문의 SUC'로 축적 (2026-07-23 GM 확정) ═══
    //   배경: 옛 팀시트는 수영만 살아 있고 나머지는 '진행 상황' 열만 남은 채 이름·연락처·종목·
    //   타임스탬프가 통째로 비어 있다(실측 735명). 그 735명은 누구인지 확인할 방법이 없다.
    //   GM 지시: "지금부터라도 따로 모아도 된다 — 새 문의에서 SUC 처리할 때 종목·횟수·유효기간을
    //   기록해서 관리해도 된다." → 오늘부터 쌓이는 진실 = 문의 시트의 SUC 행(그 자리에 등록종목·
    //   등록회수·유효기간을 이미 기록하고 있다).
    //   ★옛 팀시트 기록은 지우지 않는다(과거 흔적 보존) — 대신 출처(src)를 붙여 화면이 구분하게 한다.
    //   ★중복 방지 = 전화 정규화 키. 같은 사람이면 새로 추가하지 않고 빈 칸만 채워 넣는다.
    // ★종목명 표준화(2026-07-23 GM: '종목명 통일 좀') — 문의 시트의 종목은 폼 원문이라 길고 제각각이다
    //   ('골프 레슨 (투어프로와 …)', 'WSC 체조 & 트램폴린', '스쿼시 (개인레슨 / 단체레슨)' …).
    //   그대로 명단에 섞으면 같은 종목이 여러 이름으로 갈라져 성인 20종·유소년 22종이 된다(실측).
    //   팀시트 표준명(LESSON_DISPLAY 명)으로 접어 넣는다 — 괄호·'WSC'·'레슨' 같은 수식어를 떼고
    //   표준명이 포함되면 그 종목으로 본다. 못 알아보면 원문을 그대로 둔다(임의로 '기타'에 버리지 않는다).
    function _lrrNormSport_(raw) {
      var s = String(raw == null ? '' : raw).replace(/\(.*$/, '').replace(/\s+/g, ' ').trim();
      if (!s) return '';
      var bare = s.replace(/^WSC\s*/i, '').replace(/^(성인|유소년)\s*/, '').replace(/\s*(레슨|클래스|단체|개인)\s*$/, '').trim();
      var keyed = bare.replace(/\s|&|＆/g, '');
      var names = (LESSON_DISPLAY[lrrType] || []).map(function (it) { return it.명; });
      for (var ni = 0; ni < names.length; ni++) {
        if (names[ni].replace(/\s|&|＆/g, '') === keyed) return names[ni];
      }
      // 부분일치 — 긴 표준명부터 본다('수영'이 '모자수영'을 가로채지 않게)
      var sorted = names.slice().sort(function (a, b) { return b.length - a.length; });
      for (var nj = 0; nj < sorted.length; nj++) {
        if (keyed.indexOf(sorted[nj].replace(/\s|&|＆/g, '')) >= 0) return sorted[nj];
      }
      return bare || s;
    }
    // ★전화번호 1개 ≠ 회원 1명이다. 한 사람이 종목 2개 이상 등록하면 팀시트에 형제 행이 생기는데,
    //   전화번호당 마지막 1행만 남기면 나머지 형제 행은 영구히 rowIndex 없음이 되어 화면에서
    //   연락기록 칸이 아예 비활성이 된다 — 실무진이 남기고 싶어도 못 남기는 원천 차단이었다.
    //   실측(2026-08-08 시포): '연락기록 없음' 292건 중 83건이 이 형제행 충돌이었다(최혜은·최세은
    //   그룹, 김규섭 그룹 등 — 같은 번호의 다른 행에 기록이 실재함을 확인).
    //   → 전화번호당 형제 행 전부를 배열로 들고 있는다. 배열의 마지막 원소 = 옛 단일 맵과 같은 행이라
    //     아래 등록회수·유효기간 블록은 동작이 그대로다(회귀 0).
    var lrrByPhone = {};
    lrrRoster.forEach(function (m) {
      m.src = 'team';
      var p = _normPhone_(m.phone);
      if (p) (lrrByPhone[p] = lrrByPhone[p] || []).push(m);
    });
    try {
      _lessonReadRowsMerged_({ type: lrrType }).forEach(function (r) {
        var rStatus = String(r.status == null ? '' : r.status).trim();
        var rp = _normPhone_(r.phone);
        var sibs = rp ? (lrrByPhone[rp] || []) : [];
        // ★상태 필터를 '조인'에서 뺀다(2026-08-08 시포 실측 89건). 재문의·상태변경 이력이 있어 지금
        //   상태가 LOSS·컨택중·빈값인 문의행에도 연락기록이 실재하는데, SUC 만 매칭하던 탓에 그 기록이
        //   화면에 영영 안 붙었다. 실무진이 안 남긴 게 아니라 화면이 못 찾은 것이었다.
        //   ★단 '명단에 없는 사람을 새로 추가'하는 아래 push 는 여전히 SUC 일 때만 한다 —
        //     안 그러면 아직 등록하지 않은 컨택중·LOSS 문의자가 등록회원 명단에 섞인다.
        if (!sibs.length && rStatus !== 'SUC') return;
        var rSport = _lrrNormSport_(r.regProgram || r.sport) || '기타';
        // ★편집에 필요한 원본 행 좌표를 같이 싣는다(2026-07-23 GM: 회원 관리에서도 연락 이력 수정).
        //   rowIndex·gid·rowKey 가 없으면 어느 행을 고칠지 특정할 수 없어 화면에서 편집을 열 수 없다.
        //   contacts 도 함께 보내 모달이 옛 기록까지 그대로 펼치게 한다(문의 목록과 같은 모달·같은 동작).
        var _srcMeta = {
          rowIndex: r.rowIndex, gid: r.gid, rowKey: r.rowKey || '',
          contacts: r.contacts || [], memo: String(r.memo || ''), inqType: lrrType
        };
        if (sibs.length) {   // 이미 명단에 있는 사람 → 형제 행 전부에 보강(중복 행 만들지 않는다)
          var _hasNew = (_srcMeta.contacts && _srcMeta.contacts.length) || !!String(_srcMeta.memo || '').trim();
          sibs.forEach(function (hit) {
            // 빈 칸 보강은 등록 확정행(SUC)에서만 — 컨택중·LOSS 행의 값으로 등록회원 정보를 채우지 않는다(옛 동작 유지)
            if (rStatus === 'SUC') {
              if (!String(hit.name || '').trim())  hit.name = String(r.name || '');
              if (!String(hit.phone || '').trim()) hit.phone = String(r.phone || '');
              if (!String(hit.age || '').trim())      hit.age = String(r.age || '');
              if (!String(hit.owner || '').trim())    hit.owner = String(r.owner || '');
              if (!String(hit.inqDate || '').trim())  hit.inqDate = String(r.timestamp || '').slice(0, 10);
              if (!String(hit.wishTime || '').trim()) hit.wishTime = String(r.wishTime || '');
            }
            // 편집 좌표·연락기록은 상태와 무관하게 붙인다(팀시트 유래 행은 좌표가 없어 편집 자체가 막혀 있었다).
            //   이미 좌표가 붙어 있어도 그쪽 기록이 비어 있고 이번 행에 실제 기록이 있으면 갈아끼운다
            //   — 같은 번호에 문의행이 여럿일 때 '연락기록이 있는 행'이 이긴다.
            var _hasOld = (hit.contacts && hit.contacts.length) || !!String(hit.memo || '').trim();
            if (hit.rowIndex === undefined || (_hasNew && !_hasOld)) {
              hit.rowIndex = _srcMeta.rowIndex; hit.gid = _srcMeta.gid; hit.rowKey = _srcMeta.rowKey;
              hit.contacts = _srcMeta.contacts; hit.memo = _srcMeta.memo; hit.inqType = _srcMeta.inqType;
            }
          });
          return;
        }
        lrrRoster.push({
          sport: rSport, name: String(r.name || ''), phone: String(r.phone || ''), status: 'SUC',
          age: String(r.age || ''), owner: String(r.owner || ''),
          inqDate: String(r.timestamp || '').slice(0, 10), wishTime: String(r.wishTime || ''),
          src: 'inquiry',
          rowIndex: _srcMeta.rowIndex, gid: _srcMeta.gid, rowKey: _srcMeta.rowKey,
          contacts: _srcMeta.contacts, memo: _srcMeta.memo, inqType: _srcMeta.inqType
        });
        if (rp) (lrrByPhone[rp] = lrrByPhone[rp] || []).push(lrrRoster[lrrRoster.length - 1]);
      });
    } catch (eInq) { /* 문의 소스 실패 → 팀시트분만(무중단) */ }

    // 등록회수·유효기간을 문의 소스분에도 붙인다(위 조인은 팀시트분 기준이라 새로 들어온 행은 비어 있다).
    try {
      var lrrMainGid2 = (lrrType === '유소년강습' || lrrType === '유소년' || lrrType === 'youth') ? 268994754 : 111889422;
      var lrrSh2 = _lessonSheet_(lrrMainGid2);
      if (lrrSh2 && lrrSh2.getLastRow() >= 2) {
        var lrrH2 = lrrSh2.getRange(1, 1, 1, lrrSh2.getLastColumn()).getValues()[0];
        var p2 = _findCol_(lrrH2, ['연락처', '전화', '휴대폰']);
        var c2 = _findCol_(lrrH2, ['등록회수']);
        var e2 = _findCol_(lrrH2, ['유효기간']);
        if (p2 >= 0 && (c2 >= 0 || e2 >= 0)) {
          var md2 = lrrSh2.getRange(2, 1, lrrSh2.getLastRow() - 1, lrrSh2.getLastColumn()).getValues();
          for (var q2 = 0; q2 < md2.length; q2++) {
            var pk2 = _normPhone_(md2[q2][p2]);
            var sib2 = pk2 ? lrrByPhone[pk2] : null; if (!sib2 || !sib2.length) continue;
            // 등록회수·유효기간은 종목별로 다를 수 있어 형제 행 전부에 뿌리지 않는다 —
            //   배열 마지막 행에만 붙여 단일맵이던 시절과 같은 대상을 유지한다(회귀 0).
            //   ponytail: 종목별 정확 매칭은 문의행↔팀시트 종목 대조가 필요, 실수요 생기면 그때.
            var tgt = sib2[sib2.length - 1];
            var cv2 = c2 >= 0 ? String(md2[q2][c2] == null ? '' : md2[q2][c2]).trim() : '';
            var ev2 = e2 >= 0 ? (md2[q2][e2] instanceof Date ? Utilities.formatDate(md2[q2][e2], 'Asia/Seoul', 'yyyy-MM-dd') : String(md2[q2][e2] == null ? '' : md2[q2][e2]).trim()) : '';
            if (cv2) tgt.regCount = cv2;
            if (ev2) tgt.regExpire = ev2;
          }
        }
      }
    } catch (eRc) {}

    // 정직 집계 — 이름이 있는 '확인된 회원'과 상태값만 남은 '정보 없음'을 나눠서 함께 내보낸다.
    //   합계만 보내면 735명이 정상 회원인 것처럼 읽힌다(GM 2026-07-23 A안: 숨기지도 부풀리지도 않는다).
    var lrrIdent = 0, lrrUnknown = 0;
    lrrRoster.forEach(function (m) { if (String(m.name || '').trim()) lrrIdent++; else lrrUnknown++; });
    var lrrPayload = {
      ok: true, type: lrrType, total: lrrRoster.length, bySport: lrrBySport, roster: lrrRoster,
      identified: lrrIdent, unknown: lrrUnknown,
      unknownNote: lrrUnknown ? '옛 팀시트에 진행 상황 값만 남고 이름·연락처가 비어 있는 기록입니다(실체 확인 불가).' : ''
    };
    // 캐시에 나눠 담기 — 조각 하나라도 사라지면 읽는 쪽이 통째로 무시하므로(위 okAll) 반쪽 데이터가 나올 일은 없다.
    try {
      var putStr = JSON.stringify(lrrPayload);
      var CH = 90000, segs = [];
      for (var sp = 0; sp < putStr.length; sp += CH) segs.push(putStr.substring(sp, sp + CH));
      if (segs.length <= 12) {   // 너무 크면 캐시 포기(정상 계산 경로는 그대로 동작)
        var cch2 = CacheService.getScriptCache(), bag = {};
        for (var sq = 0; sq < segs.length; sq++) bag[lrrCacheKey + '_' + sq] = segs[sq];
        bag[lrrCacheKey + '_n'] = String(segs.length);
        cch2.putAll(bag, LRR_CACHE_TTL);
      }
    } catch (ePut) { /* 캐시 실패는 무시 — 응답은 정상 반환 */ }
    return _json(lrrPayload);
  }

  // ─── 강습 등록 원장 명단 (금일 등록현황) — sync는 read 경로 밖(warmDashboardCache 5분 워머)으로 이관. 2026-06-27 시포·2026-08-05 시토 ───
  //   ★기존: 호출마다 _syncLessonRegistry_() 선실행(팀시트 13개 재수집 + 2,500+행 재스캔) → 실측 23초.
  //   read는 시트를 그대로 읽기만 한다 — 동기화는 warmDashboardCache(라이브 확인된 5분 CLOCK 트리거)로 이관.
  //   _syncLessonRegistry_ 자체 5분 캐시가드(lesson_reg_synced)가 워머 주기와 일치해 실질 5분 내 반영.
  //   type 일치 + 등록일 ∈ [from,to] 명단. from/to 미지정 = 오늘(KST). 카드=오늘 명단.
  //   시드 직후 금일=0이 정상(과거분은 기준선 2000-01-01).
  if (action === 'lesson_registry_list') {
    var lglType = String(body.type || '');
    var lglToday = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
    var lglFrom = String(body.from || lglToday);
    var lglTo   = String(body.to   || lglToday);
    // 문의내용 조인(2a, 2026-07-18 시포): 강습 문의(성인+유소년, 한글+영문+자체폼 신규문의 모두 병합)의 note 필드
    //   (_lessonReadRows_/_lessonIntakeReadRows_가 INQUIRY_CONTENT_KEYS로 탐지한 문의사항/문의내용/내용 칼럼)를
    //   정규화 전화 키로 1회 맵 구성 후 등록현황 각 행에 O(1) 조회 조인. 동일 전화 여러 건이면 뒤(최근) 건이 이김.
    //   ★캐시(축1, TTL 60초, 2026-08-05 시토 — 15.8초 수리): 이 맵은 항상 두 고정 type(성인+유소년) 전체를
    //   재구성하는 것이라 lglType/from/to 어떤 필터에도 좌우되지 않는다 — 필터 무관 고정 키라 요청별로 값이
    //   달라질 위험 없음(lesson_stats·lesson_inquiry_list와 같은 재사용 패턴, 새 유틸 없음). 시트 접근이
    //   6~8회(성인 KR/EN·유소년 KR/EN·신규문의탭 헤더+본문×2)라 여기가 15.8초의 대부분이었다. nocache=1 우회 유지.
    var lglNoteMap = {};
    var lnmCache = CacheService.getScriptCache();
    var lnmCacheKey = 'lglnotemap';
    var lnmHit = _nc ? null : _cacheGetJson_(lnmCache, lnmCacheKey);
    if (lnmHit) {
      lglNoteMap = lnmHit;
    } else {
      try {
        ['성인강습', '유소년강습'].forEach(function(t) {
          _lessonReadRowsMerged_({ type: t }).forEach(function(r) {
            var p = _normPhone_(r.phone);
            if (p && r.note) lglNoteMap[p] = r.note;
          });
        });
        _cachePutJson_(lnmCache, lnmCacheKey, lglNoteMap, 60);
      } catch (eNoteMap) {}
    }
    var lglData = [];
    try {
      var lglSh = _lessonRegSheet_();
      var lglLast = lglSh.getLastRow();
      if (lglLast >= 2) {
        var lglRows = lglSh.getRange(2, 1, lglLast - 1, _LESSON_REG_HEADER.length).getValues();
        for (var lgi = 0; lgi < lglRows.length; lgi++) {
          var lgRow = lglRows[lgi];
          if (lglType && String(lgRow[0] || '').trim() !== lglType) continue;
          var lgD = lgRow[5];
          lgD = (lgD instanceof Date && !isNaN(lgD.getTime()))
            ? Utilities.formatDate(lgD, 'Asia/Seoul', 'yyyy-MM-dd')
            : String(lgD == null ? '' : lgD).trim();
          if (lglFrom && lgD < lglFrom) continue;
          if (lglTo   && lgD > lglTo)   continue;
          lglData.push({
            종목:   String(lgRow[1] || ''),
            이름:   String(lgRow[2] || ''),
            전화:   _fmtPhone_(lgRow[3]),
            상태:   String(lgRow[4] || ''),
            등록일: lgD,
            문의내용: lglNoteMap[_normPhone_(lgRow[3])] || ''
          });
        }
      }
    } catch (eLg) {}
    return _json({ ok: true, type: lglType, from: lglFrom, to: lglTo, count: lglData.length, data: lglData });
  }

  // ─── 강습문의 페이지(CPO): 통계 (총·이번달·종목 분포·유입경로 분포) ───
  if (action === 'lesson_stats') {
    // 조회 캐시(축1, TTL 60초) — lesson_inquiry_list(licache)와 동일 키 축(type+scope). nocache=1 우회.
    //   실측 7.8초(매 호출 시트 재병합·재집계) → 캐시 추가. 2026-08-05 시토.
    var lsType = String(body.type || '');
    var lsScope = (String(body.scope || '') === 'all') ? 'all' : 'year';
    var lsCache = CacheService.getScriptCache();
    var lsCacheKey = 'lscache|' + lsType + '|' + lsScope;
    if (!_nc) {
      var lsHit = _cacheGetJson_(lsCache, lsCacheKey);
      if (lsHit) return _json(lsHit);
    }
    var lsRows = _lessonScopeFilter_(_lessonReadRowsMerged_(body), body);
    var lsTotal = lsRows.length;
    var lsMonth = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM');
    var lsThisMonth = 0;
    var lsSport = {}, lsChan = {};
    lsRows.forEach(function(row) {
      if (row.timestamp && row.timestamp.slice(0, 7) === lsMonth) lsThisMonth++;
      // 종목: 표준 버킷 집계(라벨 통째 쪼개기 금지·다중체크는 각 버킷 +1). 2026-06-26 시포.
      _sportBuckets_(row.sport).forEach(function(k){ lsSport[k] = (lsSport[k] || 0) + 1; });
      // 유입경로: 표준 10버킷 정규화(빈값=기타·미상)
      var ch = _canonicalChannel_(row.channel || '');
      lsChan[ch] = (lsChan[ch] || 0) + 1;
    });
    function _lsSort(obj) {
      return Object.keys(obj).map(function(k){ return { k: k, v: obj[k] }; })
        .sort(function(a, b){ return b.v - a.v; });
    }
    var lsResult = { ok: true, total: lsTotal, thisMonth: lsThisMonth, bySport: _lsSort(lsSport), byChannel: _lsSort(lsChan) };
    _cachePutJson_(lsCache, lsCacheKey, lsResult, 60);
    return _json(lsResult);
  }

  // ─── 강습문의 페이지(CPO): 예약 달력 (상담예약 일정) ───
  if (action === 'lesson_calendar') {
    var lcMonth = String(body.month || '');  // 'YYYY-MM'
    var lcRows = _lessonScopeFilter_(_lessonReadRowsMerged_(body), body);
    var lcEvents = [];
    lcRows.forEach(function(row) {
      var d = row.consult;
      if (!d) return;
      if (lcMonth && d.slice(0, 7) !== lcMonth) return;
      lcEvents.push({ date: d, time: row.consultTime || '', tmin: row.consultTmin, kind: '상담', name: row.name || '', phone: row.phone || '', sport: row.sport || '', status: row.status || '', memo: row.memo || '', rowIndex: row.rowIndex });
    });
    return _json({ ok: true, month: lcMonth, count: lcEvents.length, events: lcEvents });
  }

  // ─── 강습문의 페이지(CPO): 행 추가 (전화·직접 문의 수기 입력, member_inquiry_add 동일 구조) ───
  //   2026-08-25 GM 지시 — 강습 문의는 화면에서 새 줄을 만들 경로가 아예 없어 전화·방문으로 받은 접수를
  //   실무진이 못 넣고, 한 사람이 종목 두 개를 등록해도 줄을 나눌 수 없었다(딜런 승헌 델가도 실사례).
  //   대상 시트 라우팅 = 기존 강습 액션과 동일(_lessonGidOf_ — type/gid). 행은 append만
  //   (이 시트는 IMPORTRANGE 소스 — 기존 행 이동·삭제 절대 금지).
  if (action === 'lesson_inquiry_add') {
    if (!body.name || !body.phone) return _json({ ok: false, error: 'lesson-add-required', detail: '이름과 전화번호는 필수입니다 — 두 칸을 채운 뒤 다시 추가해 주세요' });
    var laSh = _lessonSheet_(_lessonGidOf_(body));
    if (!laSh) return _json({ ok: false, error: '시트 없음' });
    var laHdr = _lessonEnsureCols_(laSh);
    // 강습 등록정보 5칸(확정종목·등록일·횟수·시작일·종료일) — lesson_inquiry_update와 동일하게 보장 생성(SUC 가드 대상).
    var _laCiProgram = _miEnsureCol_(laSh, laHdr, '확정종목');
    var _laCiRegDate = _miEnsureCol_(laSh, laHdr, '등록일');
    var _laCiCount   = _miEnsureCol_(laSh, laHdr, '횟수');
    var _laCiStart   = _miEnsureCol_(laSh, laHdr, '시작일');
    var _laCiEnd     = _miEnsureCol_(laSh, laHdr, '종료일');
    // ★중복 방어(2026-08-25 GM 지시) — 같은 사람이 종목을 나눠 여러 줄 갖는 게 정상 사용례라 영구 차단하지 않는다.
    //   같은 전화+같은 이름 행이 이미 있으면 한 번 알리고, force:true 로 다시 오면 그대로 추가한다.
    var _laForce = (body.force === true || String(body.force || '').toLowerCase() === 'true' || String(body.force || '') === '1');
    var _laPhoneNorm = _normPhone_(body.phone);
    var _laNameNorm  = String(body.name || '').trim();
    if (!_laForce) {
      var _laDup = _lessonReadRowsMerged_(body).filter(function (r) {
        return _normPhone_(r.phone) === _laPhoneNorm && String(r.name || '').trim() === _laNameNorm;
      });
      if (_laDup.length) {
        return _json({
          ok: false, error: 'lesson-add-duplicate',
          detail: '같은 분의 문의가 이미 ' + _laDup.length + '건 있습니다 — 그래도 새로 추가하려면 다시 눌러 주세요',
          existing: _laDup.map(function (r) { return { rowIndex: r.rowIndex, sport: r.sport, status: r.status, timestamp: r.timestamp }; })
        });
      }
    }
    // ★강습 등록정보 서버 가드 — SUC/단기SUC로 바로 들어오면 lesson_inquiry_update와 동일 규칙으로 막는다(우회로 차단).
    var _laStatus = String(body.status || '신규').trim();
    if (_laStatus === 'SUC' || _laStatus === '단기SUC') {
      var _laFields = [
        ['regProgram', '종목'], ['regDate', '등록일'], ['regCount', '횟수'],
        ['startDate', '시작일'], ['regExpire', '종료일']
      ];
      var _laMissing = [];
      _laFields.forEach(function (f) { if (!String(body[f[0]] || '').trim()) _laMissing.push(f[1]); });
      if (_laMissing.length) {
        return _json({ ok: false, error: 'lesson-reg-fields-required',
          detail: '등록으로 바꾸려면 종목·등록일·횟수·시작일·종료일이 필요합니다 — 화면에서 채운 뒤 다시 저장해 주세요',
          missing: _laMissing });
      }
    }
    var laRow = new Array(laHdr.length).fill('');
    function _laSet(colNames, val) {
      if (val === undefined || val === null || val === '') return;
      var ci = _findCol_(laHdr, colNames);
      if (ci < 0) return;
      while (laRow.length <= ci) laRow.push('');
      laRow[ci] = val;
    }
    _laSet(['성함', '이름', 'Full Name'], body.name);
    _laSet(['연락처', '전화', '휴대폰', 'Mobile Phone Number'], _fmtPhone_(body.phone));
    _laSet(['성인 강습 종목', 'WSC 강습 종목', 'WSC 강습 종류', '강습 종목', '종목', '과목', 'Program of Interest'], body.sport);
    _laSet(['나이', '연령', '자녀 나이', '자녀나이', '학년', 'Age'], body.age);
    _laSet(['문의 경로', '경로', '채널', '알게', 'How Did You Hear About Us?'], body.channel);
    _laSet(['진행상태', '진행현황', '진행상황', '진행 상황', '상태'], _laStatus);
    _laSet(['지정 강사', '관리담당'], body.owner);
    _laSet(['상담메모', '메모', '비고'], body.memo);
    _laSet(['타임스탬프', 'timestamp', '시각', '일시', '접수일', '날짜'], body.timestamp || Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'));
    if (body.regProgram !== undefined) laRow[_laCiProgram] = body.regProgram;
    if (body.regDate    !== undefined) laRow[_laCiRegDate] = body.regDate;
    if (body.regCount   !== undefined) laRow[_laCiCount]   = body.regCount;
    if (body.startDate  !== undefined) laRow[_laCiStart]   = body.startDate;
    if (body.regExpire  !== undefined) laRow[_laCiEnd]     = body.regExpire;
    laSh.appendRow(laRow);
    // 회원 변경 이력(배327과 동일 방식, 기존 삭제·수정 경로 재사용) — 누가 추가했는지 한 줄.
    _memberLog_([[new Date(), _logWho_(body), body.name || '', _logMaskPhone_(_fmtPhone_(body.phone)),
                  '문의 추가', '', (body.sport || '(종목 미기재)') + ' / ' + _laStatus, '강습']]);
    try {
      var _laChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
      _notifyTelegram('➕ 강습 전화·직접 문의 추가 — ' + (body.name || '(이름없음)') + ' · ' + (body.phone || '-') + ' · ' + _teamChip(body.sport || '') + (body.sport || '-'), _laChatId);
    } catch (e) {}
    // 조회 캐시 무효화 — lesson_inquiry_update와 동일 4키(type별 licache/lscache year·all).
    try {
      var _laCache = CacheService.getScriptCache();
      var _laType = String(body.type || '');
      _cacheInvalidateJson_(_laCache, 'licache|' + _laType + '|year');
      _cacheInvalidateJson_(_laCache, 'licache|' + _laType + '|all');
      _cacheInvalidateJson_(_laCache, 'lscache|' + _laType + '|year');
      _cacheInvalidateJson_(_laCache, 'lscache|' + _laType + '|all');
    } catch (e) {}
    return _json({ ok: true, message: '추가되었습니다.', rowIndex: laSh.getLastRow() });
  }

  // ─── 강습문의 페이지(CPO): 행 수정 (진행상태·담당·상담메모·상담예약·방문상태) ───
  //   멤버십 member_inquiry_update 구조 그대로. undefined 필드는 스킵.
  if (action === 'lesson_inquiry_update') {
    var luRow = parseInt(body.rowIndex, 10);
    if (!luRow || luRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var luSh = _lessonSheet_(_lessonGidOf_(body));  // body.rowIndex(원본·오프셋 유지) 기준 한글/영문 자동판별
    if (!luSh) return _json({ ok: false, error: '시트 없음' });
    var luRowRaw = luRow;  // 응답용 원본(오프셋 유지) — 프론트 로컬 매칭 정합. 2026-07-09 시포·GM.
    if (luRow >= _ROW_OFFSET_INTAKE_) luRow -= _ROW_OFFSET_INTAKE_;   // 강습 신규문의(자체폼 유입, 배1037) 오프셋 우선 디코드(EN보다 큼)
    else if (luRow >= _ROW_OFFSET_EN_) luRow -= _ROW_OFFSET_EN_;      // 영문 탭 오프셋 디코드. 실제 물리 행으로 환원(시트 쓰기는 여기부터 물리 행 사용).
    var luHdr = _lessonEnsureCols_(luSh);
    // ★강습 등록정보 5칸(확정종목·등록일·횟수·시작일·종료일) 신설(2026-08-25 GM 지시) — SUC 필수가드 대상.
    //   기존 강습종목/등록회수/유효기간 칸은 그대로 둔다(삭제·이동 금지, 이 시트는 IMPORTRANGE 소스) — 새 칸에만 쓴다.
    var _lrCiProgram = _miEnsureCol_(luSh, luHdr, '확정종목');
    var _lrCiRegDate = _miEnsureCol_(luSh, luHdr, '등록일');
    var _lrCiCount   = _miEnsureCol_(luSh, luHdr, '횟수');
    var _lrCiStart   = _miEnsureCol_(luSh, luHdr, '시작일');
    var _lrCiEnd     = _miEnsureCol_(luSh, luHdr, '종료일');
    var _luPhCi = _findCol_(luHdr, ['연락처', '전화', '휴대폰']);
    // ★★ 지문키(rowKey) 우선 경로(§4 R2) — 타임스탬프+연락처 조합. 매칭 1건=확정(아래 keyPhone 검증 스킵) /
    //   0건·2건+=거부(fail-closed). rowKey 미동봉(구클라)이거나 타임스탬프 칸 미탐지 시 기존 keyPhone 경로로 폴백. 2026-07-22 시포(오지목 근본수리).
    var _luRk = _rowKeyParts_(body);
    var _luTsCi = _luRk ? _findCol_(luHdr, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '날짜']) : -1;
    if (_luRk && _luTsCi >= 0 && _luPhCi >= 0) {
      var _luFpRows = _findRowsByKey_(luSh, _luTsCi, _luPhCi, _luRk.ts, _luRk.phone,
                                      _nameColIdx_(luHdr), _luRk.name);
      if (_luFpRows.length === 1) {
        luRow = _luFpRows[0];
      } else if (_luFpRows.length === 0) {
        return _json({ ok: false, error: 'rowkey-not-found', detail: '행 확인 불가(지문 불일치) — 목록 새로고침 후 다시 시도하세요' });
      } else {
        return _json({ ok: false, error: 'rowkey-ambiguous', detail: '지문키 중복 매칭 — 목록 새로고침 후 다시 시도하세요' });
      }
    } else {
    // ★행키 검증(비파괴·하위호환, 지문키 미동봉/칸 미탐지 시 폴백): keyPhone 동봉 시 대상 행 전화 대조 — rowIndex 밀림 오수정 방지. 미전송이면 폴백 — 단, 예약(상담예약) 쓰기는 예외(B1).
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      if (_luPhCi >= 0) {
        var _luRowPh = _normPhone_(luSh.getRange(luRow, _luPhCi + 1).getValue());
        var _luKeyPh = _normPhone_(body.keyPhone);
        if (_luKeyPh && _luRowPh !== _luKeyPh) {
          // rowIndex 어긋남(gviz 압축 인덱스·시트 편집 밀림·빈행) → keyPhone으로 올바른 물리 행 복구. 2026-07-13 시포(INC-013).
          // 매칭 1건=재지정 / 0건=거부 / 2건+=모호·첫매칭 강제진행 금지·거부(오지목 봉합 B2). 2026-07-22 시포.
          var _luCount = _countRowsByPhone_(luSh, _luPhCi, _luKeyPh);
          if (_luCount === 1) {
            luRow = _findRowByPhone_(luSh, _luPhCi, _luKeyPh);
          } else if (_luCount >= 2) {
            return _json({ ok: false, error: 'duplicate-phone-ambiguous', detail: '동일 연락처 여러 건 — 새로고침 후 대상 확인 필요' });
          } else {
            return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패(대상 전화 없음) — 목록을 새로고침 후 다시 시도하세요' });
          }
        }
      } else {
        // ★2026-08-03 시토(배294) — 문의 쪽과 같은 조치. 대조 불가능하면 쓰기 종류를 안 가리고 거부.
        return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
      }
    } else {
      // ★2026-08-03 시토(배294) — keyPhone 없으면 무조건 거부. 종전엔 상담예약 쓰기만 막아,
      //   진행상태·담당·상담메모·방문상태·연락처가 **다른 강습문의고객 행에 덮일** 수 있었다.
      return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
    }
    }
    // 강습 변경 이력(배327) — 멤버십과 같은 파일·같은 패턴이라 같이 넣는다. 쓰기는 이 함수 하나를 지난다.
    var _luStaff = _logWho_(body);
    var _luNameCi = _findCol_(luHdr, ['성명', '이름', '회원명', '신청자']);
    var _luLog = [];
    function _luSet(colNames, val) {
      if (val === undefined || val === null) return;
      var ci = _findCol_(luHdr, colNames);
      if (ci < 0) return;
      var cell = luSh.getRange(luRow, ci + 1);
      var _old = String(cell.getValue() == null ? '' : cell.getValue());
      var _new = String(val);
      cell.setValue(val);
      if (_old !== _new) {
        _luLog.push([new Date(), _luStaff,
          _luNameCi >= 0 ? String(luSh.getRange(luRow, _luNameCi + 1).getValue() || '') : '',
          _luPhCi >= 0 ? _logMaskPhone_(luSh.getRange(luRow, _luPhCi + 1).getValue()) : '',
          String(luHdr[ci] || colNames[0]), _old, _new, '강습']);
      }
    }
    // ★종목(강습종목) 칸 직접 수정(2026-08-25 GM 지시 — 다종목 문의 줄 나누기) — 지금까지 이 액션은
    //   종목 칸(강습종목)을 쓰는 경로가 없었다(body.sport 는 종목별 관리 라우팅 키일 뿐 칸에 안 쓴다).
    //   body.sport 의미는 그대로 두고 별도 파라미터로 연다 — 다른 호출부가 안 깨진다.
    if (body.sportText !== undefined && body.sportText !== null) {
      _luSet(['성인 강습 종목', 'WSC 강습 종목', 'WSC 강습 종류', '강습 종목', '종목', '과목', 'Program of Interest'], body.sportText);
    }
    // ★LOSS 사유 서버 가드 (2026-08-10 시토 · 배491 · 멤버십 member_inquiry_update 와 같은 규칙)
    //   두 경로(종목별·row-level)가 갈리기 전에 한 번만 검사한다 — 분기 뒤에 각각 넣으면 한쪽만 고쳐진다.
    //   최근 30일 실측(시포 2026-08-08): 강습에 사유 공란 LOSS 2건(임하윤·이봄)이 실제로 들어와 있었다.
    if (String(body.status == null ? '' : body.status).trim() === 'LOSS') {
      var _lgLuCi  = _findCol_(luHdr, ['LOSS사유', '미등록 사유', '미등록사유']);
      var _lgLuCur = (_lgLuCi >= 0) ? String(luSh.getRange(luRow, _lgLuCi + 1).getValue() || '').trim() : '';
      var _lgLuNew = (body.lossReason !== undefined) ? String(body.lossReason || '').trim() : _lgLuCur;
      if (!_lgLuNew) {
        return _json({ ok: false, error: 'loss-reason-required',
          detail: 'LOSS 로 바꾸려면 사유가 필요합니다 — 목록에서 LOSS 사유를 고른 뒤 다시 저장하세요' });
      }
    }
    // ★강습 등록정보 서버 가드(2026-08-25 GM 지시) — SUC/단기SUC로 확정될 때 등록정보 5칸이 하나라도 비면
    //   쓰기 전에 거부한다. LOSS 가드와 동일 원칙(주석 위 참고): 뒤에서 막으면 상태만 먼저 바뀌고
    //   나머지가 빈 채 남는다. 최종값 = 이번에 보낸 값(body) 우선, 없으면 시트에 이미 있는 값.
    if (String(body.status == null ? '' : body.status).trim() === 'SUC' || String(body.status == null ? '' : body.status).trim() === '단기SUC') {
      var _lrFields = [
        ['regProgram', _lrCiProgram, '종목'],
        ['regDate',    _lrCiRegDate, '등록일'],
        ['regCount',   _lrCiCount,   '횟수'],
        ['startDate',  _lrCiStart,   '시작일'],
        ['regExpire',  _lrCiEnd,     '종료일']
      ];
      var _lrMissing = [];
      _lrFields.forEach(function(f) {
        var _cur = String(luSh.getRange(luRow, f[1] + 1).getValue() || '').trim();
        var _new = (body[f[0]] !== undefined) ? String(body[f[0]] || '').trim() : _cur;
        if (!_new) _lrMissing.push(f[2]);
      });
      if (_lrMissing.length) {
        return _json({ ok: false, error: 'lesson-reg-fields-required',
          detail: '등록으로 바꾸려면 종목·등록일·횟수·시작일·종료일이 필요합니다 — 화면에서 채운 뒤 다시 저장해 주세요',
          missing: _lrMissing });
      }
    }
    // ★종목별 독립 관리(축7, GM 2026-07-08 확정) 라우팅: body.sport(sportKey) 동봉 시 종목별 경로,
    //  없으면 기존 row-level 경로(하위호환) — 두 경로는 완전히 분기(서로 컬럼 침범 없음).
    var luSportKey = String(body.sport || '').trim();
    // ★연락이력 저장이 실패했는지 붙들어 둔다 — 2026-08-05 시토.
    //   멤버십(member_inquiry_update)은 2026-07-25 에 이 처리를 넣었는데(실무진 피드백 FB260725-122608),
    //   같은 모양의 강습 경로 두 곳은 안 고쳐진 채 남아 있었다. 아래 catch 가 Logger.log 만 하고 끝나서
    //   응답은 ok:true 로 나갔고, 화면은 '저장' 토스트를 띄웠다 — 팀장은 저장된 줄 알고 창을 닫는다.
    //   컨택 내용은 다시 쓸 수 없는 글이라(통화하며 적은 것) 조용한 유실의 대가가 특히 크다.
    var _luHistErr = '';

    if (luSportKey) {
      // ── 종목별 경로(GM 2026-07-22 · 평문 태그): 연락이력 칸에 '[종목] …' 태그 줄로 저장.
      //    이 종목 태그 줄만 교체하고 다른 종목·공통(무태그) 줄은 보존. JSON 종목별관리 칸 미사용(GM: 시트 JSON 금지).
      //    진행상태/관리담당은 종목 무관 공용(멤버십 정합, 담당은 종목탭으로 렌더 해석) — contacts만 종목별 분리.
      var _spCi = _findCol_(luHdr, [CONTACT_HIST_COL, 'Contact']);
      var _spIsThisSport = function (c) {
        var mm = String(c && c.note != null ? c.note : '').match(/^\s*\[([^\]]+)\]/);
        return !!(mm && mm[1].trim() === luSportKey);
      };
      var _spExisting = (_spCi >= 0) ? _lessonContactCellParse_(luSh.getRange(luRow, _spCi + 1).getValue()) : [];
      var _spPrevCount = _spExisting.filter(_spIsThisSport).length;
      if (body.status !== undefined && body.status !== null) _luSet(['진행상태', '진행현황', '진행상황', '진행 상황', '상태'], body.status);
      // 연락처·비고 교정 경로(2026-07-27 시포). 지금까지 이 액션은 진행상태·담당·연락이력만 썼고, 번호와 메모가
      //   한 칸에 섞인 행(예: '01052388823( 현재는 미국거주중6/16…)')을 고칠 방법이 아예 없어 수동으로 넘기고 있었다.
      //   ★안전: 위 keyPhone 대조를 이미 통과한 행에만 쓴다(행번호만 믿지 않음 · INC-020 교훈).
      //   setPhone 은 '번호를 바꾼다'는 뜻이 분명하도록 별도 키로 둔다(조회키 keyPhone 과 혼동 방지).
      if (body.setPhone !== undefined && body.setPhone !== null) _luSet(['연락처', '전화', '휴대폰'], body.setPhone);
      if (body.memo !== undefined && body.memo !== null) _luSet(['비고'], body.memo);
      if (body.owner  !== undefined && body.owner  !== null) _luSet(['지정 강사', '관리담당'], body.owner);
      var _spNewHistArr = null;
      if (body.contacts !== undefined) {
        _spNewHistArr = _resParse_(body.contacts);
        var _spKept = _spExisting.filter(function (c) { return !_spIsThisSport(c); });   // 다른 종목·공통(무태그) 보존
        var _spTagged = _spNewHistArr.map(function (c) {
          return { date: c.date || '', time: c.time || '', note: '[' + luSportKey + '] ' + String(c.note || '').trim(), by: c.by || '' };   // 컨택자 보존(배101)
        });
        // ★연락 기록이 줄어드는 쓰기 거부 — 2026-07-28 시포(멤버십 member_inquiry_update 와 동일 규칙).
        //   이 블록은 이 종목 태그 줄을 받은 배열로 통째 교체한다. 화면이 옛 상태를 실어 보내면 그만큼 지워진다.
        //   멤버십에서 실제로 그렇게 세 분 기록이 사라졌다(유경민·김정화·도자연). 강습도 같은 구조라 같이 막는다.
        //   ▸일부러 지우는 경우는 화면이 contactsPrev(이 종목 현재 건수)로 의도를 밝힌다.
        var _spCPrev = (body.contactsPrev === undefined || body.contactsPrev === null || body.contactsPrev === '')
          ? null : parseInt(body.contactsPrev, 10);
        var _spDeclared = (_spCPrev !== null && !isNaN(_spCPrev) && _spCPrev === _spPrevCount);
        if (!_spDeclared && _spTagged.length < _spPrevCount) {
          return _json({
            ok: false, error: 'contacts-would-shrink',
            detail: '연락 기록이 지워질 뻔해 저장을 멈췄습니다 — 목록을 새로고침한 뒤 다시 저장해 주세요',
            prev: _spPrevCount, incoming: _spTagged.length, sport: luSportKey
          });
        }
        var _spMerged = _spKept.concat(_spTagged);
        try {
          if (_spCi >= 0) {
            var _spCell = luSh.getRange(luRow, _spCi + 1);
            _spCell.setNumberFormat('@');
            _spCell.setValue(_lessonContactPlainStringify_(_spMerged));
          }
          // 회원 변경 이력(배327) 배선 — 2026-08-04 시토(배359). row-level 경로(아래 _luSet)만 이력에 남고
          //   종목별 경로는 안 남아 있었다 — 형제 호출부 누락(약속 L01). 건수만 남긴다.
          if (_spTagged.length !== _spPrevCount) {
            _luLog.push([new Date(), _luStaff,
              _luNameCi >= 0 ? String(luSh.getRange(luRow, _luNameCi + 1).getValue() || '') : '',
              _luPhCi >= 0 ? _logMaskPhone_(luSh.getRange(luRow, _luPhCi + 1).getValue()) : '',
              '연락 이력(' + luSportKey + ')', _spPrevCount + '건', _spTagged.length + '건', '강습']);
          }
        } catch (eSp) {
          Logger.log('강습 종목별 컨택 저장 실패: ' + eSp.message);
          _luHistErr = String(eSp && eSp.message ? eSp.message : eSp);   // 삼키지 않는다 — 아래에서 실패로 응답
        }
      }
      // 1차 컨택 알림(종목별): 이 종목 태그 줄 0건 → ≥1건 전이 시 1회만. body.silent==='1' 억제(대량 이관 오알림 방지).
      if (_spNewHistArr && _spPrevCount === 0 && _spNewHistArr.length >= 1 && String(body.silent || '') !== '1') {
        try {
          var _lsmTypeLabel = (function(t){ t = String(t || ''); return (t === '유소년강습' || t === '유소년' || t === 'youth') ? '유소년 강습' : '성인 강습'; })(body.type);
          var _lsmNameCi = _findCol_(luHdr, ['이름', '성함']);
          var _lsmName = (String(body.name || (_lsmNameCi >= 0 ? luSh.getRange(luRow, _lsmNameCi + 1).getValue() : '')).trim()) || '-';
          var _lsmHistFirst = _spNewHistArr[0];
          var _lsmHistWhen = ((_lsmHistFirst.date || '') + ' ' + (_lsmHistFirst.time || '')).trim();
          var _lsmOwnerVal = String(body.owner || '').trim();
          var _lsmContactChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
          _notifyTelegram('📞 <b>1차 컨택 진행</b> — ' + _lsmName + ' (' + _lsmTypeLabel + ' · ' + _teamChip(luSportKey) + luSportKey + ')\n일시: ' + (_lsmHistWhen || '-') + '\n내용: ' + (_lsmHistFirst.note || '-') + (_lsmHistFirst.by ? '\n컨택: ' + _lsmHistFirst.by : '') + (_lsmOwnerVal ? '\n배정 담당: ' + _lsmOwnerVal : ''), _lsmContactChatId);
        } catch (e) {}
      }
    } else {
      // ── 기존 row-level 경로(하위호환) — body.sport 미전송 시 그대로 유지. 2026-06-26~2026-07-08 시포·GM.
      // 등록 전환 감지: 상태 변경 '전' 값 캡처(신규→SUC 실제 전환 1회만 알림 — 멤버십 member_inquiry_update와 동일 패턴·중복발화 차단). 시토 2026-06-29 GM.
      var _luStatusCi  = _findCol_(luHdr, ['진행상태', '진행현황', '진행상황', '진행 상황', '상태']);
      var _luOldStatus = (_luStatusCi >= 0) ? String(luSh.getRange(luRow, _luStatusCi + 1).getValue() || '').trim() : '';
      _luSet(['진행상태', '진행현황', '진행상황', '진행 상황', '상태'], body.status);  // '진행 상황'=GM flat O컬럼
      _luSet(['지정 강사', '관리담당'], body.owner);  // ★관리 담당 컬럼만. '지정 강사'=GM flat L컬럼(폼 원본 '접수담당자' 안 건드림)
      _luSet(['상담메모', '메모', '비고'], body.memo);
      // 연락처 교정(2026-07-27 시포) — 번호와 메모가 한 칸에 섞인 행을 고칠 경로가 없어 수동으로 넘기고 있었다.
      //   ★위 keyPhone/rowKey 대조를 통과한 행에만 쓴다(행번호만 믿지 않음 · INC-020). 조회키 keyPhone 과
      //   구분되도록 setPhone 이라는 별도 키를 쓴다 — 값이 없으면 아무 일도 안 한다(_luSet 이 undefined 무시).
      _luSet(['연락처', '전화', '휴대폰'], body.setPhone);
      _luSet(['상담예약', '상담 예약', '상담일정'], body.consult);
      _luSet(['방문상태', '방문'], body.visited);
      _luSet(['LOSS사유', '미등록 사유', '미등록사유'], body.lossReason);   // LOSS 사유 → 실제 칸 '미등록 사유'(LOSS사유 칸 미존재 불일치 수리). 2026-07-22 시포·GM.
      // ★LOSS사유메모 폐기(2026-07-20 GM 확정) — "LOSS사유메모도 필요없어". 화면에서도 메모칸을 없앴다.
      // ★강습 등록정보 5칸 신설(2026-08-25 GM 지시, 배경: 등록해도 화면엔 'SUC' 글자만 남는다는 팀장 신고).
      //   종전엔 등록값을 실제 강습종목(관심종목) 칸에 덮어써 원래 문의 시 관심종목이 사라졌다 — 이제 별도
      //   '확정종목' 칸에 쓴다(관심종목 칸은 더 이상 건드리지 않음). 등록회수·유효기간(구 칸)도 손대지 않는다
      //   (삭제·이동 금지) — 새 칸(횟수·종료일)에만 쓴다.
      if (body.regProgram !== undefined) _luSet(['확정종목'], body.regProgram);
      if (body.regDate    !== undefined) _luSet(['등록일'],   body.regDate);
      if (body.regCount   !== undefined) _luSet(['횟수'],     body.regCount);
      if (body.startDate  !== undefined) _luSet(['시작일'],   body.startDate);
      if (body.regExpire  !== undefined) _luSet(['종료일'],   body.regExpire);
      // ── 연락이력(가변) — 축2/축4: body.contacts(JSON 문자열/배열) 수신 시 저장. 미전송이면 무영향(기존 필드만 갱신).
      //    상담메모는 위 _luSet으로 그대로 유지(비파괴·원복 안전) — 신·구 컬럼 병존. 2026-07-08 시포·GM.
      var _luHistPrevCount = 0;
      var _luHistNewArr = null;
      if (body.contacts !== undefined) {
        try {
          var _luHistCi = _findCol_(luHdr, [CONTACT_HIST_COL, 'Contact']);  // 연락이력 우선 → GM flat M컬럼 'Contact'(부분일치). 평문(줄바꿈)으로 라운드트립 기록. 2026-07-22 GM
          var _luPrevHistArr = (_luHistCi >= 0) ? _lessonContactCellParse_(luSh.getRange(luRow, _luHistCi + 1).getValue()) : [];  // 평문·레거시JSON 둘 다 인식(마이그레이션 중 카운트 정합)
          _luHistPrevCount = _luPrevHistArr.length;
          _luHistNewArr = _resParse_(body.contacts);  // 프론트 계약(배열/JSON 문자열) 그대로 수신·정규화 — 불변
          // ★연락 기록이 줄어드는 쓰기 거부 — 2026-07-28 시포(멤버십·강습 종목별 경로와 동일 규칙).
          //   이 경로는 연락이력 칸을 받은 배열로 통째 교체한다(태그줄 포함 전체 왕복 계약).
          //   화면이 옛 상태를 실어 보내면 그만큼 지워진다 — 멤버십에서 실제로 세 분 기록이 그렇게 사라졌다.
          var _luCPrev = (body.contactsPrev === undefined || body.contactsPrev === null || body.contactsPrev === '')
            ? null : parseInt(body.contactsPrev, 10);
          var _luDeclared = (_luCPrev !== null && !isNaN(_luCPrev) && _luCPrev === _luHistPrevCount);
          if (!_luDeclared && _luHistNewArr.length < _luHistPrevCount) {
            return _json({
              ok: false, error: 'contacts-would-shrink',
              detail: '연락 기록이 지워질 뻔해 저장을 멈췄습니다 — 목록을 새로고침한 뒤 다시 저장해 주세요',
              prev: _luHistPrevCount, incoming: _luHistNewArr.length
            });
          }
          if (_luHistCi >= 0) {
            var _luHistCell = luSh.getRange(luRow, _luHistCi + 1);
            _luHistCell.setNumberFormat('@');
            // flat 경로(sport:'')=단일종목/미기재 회원. 프론트가 모달에 전체 컨택(태그줄 포함)을 담아 왕복하므로
            //   body.contacts 그대로 기록하면 태그줄도 보존된다 — 별도 keptTags concat은 중복 유발이라 제거. 2026-07-22 디버그.
            _luHistCell.setValue(_lessonContactPlainStringify_(_luHistNewArr));
          }
          // 회원 변경 이력(배327) 배선 — 2026-08-04 시토(배359). 건수만 남긴다(내용은 칸 자체가 원본).
          if (_luHistNewArr.length !== _luHistPrevCount) {
            _luLog.push([new Date(), _luStaff,
              _luNameCi >= 0 ? String(luSh.getRange(luRow, _luNameCi + 1).getValue() || '') : '',
              _luPhCi >= 0 ? _logMaskPhone_(luSh.getRange(luRow, _luPhCi + 1).getValue()) : '',
              '연락 이력', _luHistPrevCount + '건', _luHistNewArr.length + '건', '강습']);
          }
        } catch (eHist) {
          Logger.log('강습 연락이력 저장 실패: ' + eHist.message);
          _luHistErr = String(eHist && eHist.message ? eHist.message : eHist);   // 삼키지 않는다 — 아래에서 실패로 응답
        }
      }
      // 강습 등록 전환(신규→SUC/단기SUC 1회) → '문의 알림' 방 통보(멤버십과 정합). 시토 2026-06-29 GM.
      //   이름/종목 값은 컨택 시작 알림(아래)도 재사용 → _luIsSucNew 여부와 무관하게 항상 계산. 2026-07-07 시토.
      var _luNewStatus = String(body.status == null ? '' : body.status).trim();
      var _luIsSucNew  = (_luNewStatus === 'SUC' || _luNewStatus === '단기SUC');
      var _luWasSuc    = (_luOldStatus === 'SUC' || _luOldStatus === '단기SUC');
      var _luNameCi  = _findCol_(luHdr, ['이름', '성함']);
      var _luSportCi = _findCol_(luHdr, ['종목', '과목', '관심종목', '강습종목']);
      var _luName  = (String(body.name  || (_luNameCi  >= 0 ? luSh.getRange(luRow, _luNameCi  + 1).getValue() : '')).trim()) || '-';
      var _luSport = (String(body.sport || body.program || (_luSportCi >= 0 ? luSh.getRange(luRow, _luSportCi + 1).getValue() : '')).trim()) || '-';
      try {
        if (_luIsSucNew && !_luWasSuc) {
          var _luRegChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
          _notifyTelegram('✅ <b>등록 전환(강습)</b> — 강습문의가 등록(' + _luNewStatus + ')으로 전환\n· 이름: ' + _luName + '\n· 종목: ' + _teamChip(_luSport) + _luSport + '\n· 담당: ' + (body.owner || '-'), _luRegChatId);
        }
      } catch (e) {}
      // 1차 컨택 알림(축6, 이력-기준으로 일원화): 연락이력 0건 → ≥1건 전이 시 1회만. 2026-07-08 시포·GM.
      //   구 '컨택 시작'(상태=상담중 등 진입 기준) 알림은 중복 방지를 위해 이 이력-기준 알림으로 대체(제거) — 멤버십 member_inquiry_update와 정합.
      if (_luHistNewArr && _luHistPrevCount === 0 && _luHistNewArr.length >= 1) {
        try {
          var _luTypeLabel = (function(t){ t = String(t || ''); return (t === '유소년강습' || t === '유소년' || t === 'youth') ? '유소년 강습' : '성인 강습'; })(body.type);
          var _luOwnerCi  = _findColExact_(luHdr, ['지정 강사', '관리담당']);  // 알림 담당 폴백 — '지정 강사'(GM flat L) 우선(옛 팬텀 '관리담당' 잔존 대비 순서 고정)
          var _luOwnerVal = String(body.owner || (_luOwnerCi >= 0 ? luSh.getRange(luRow, _luOwnerCi + 1).getValue() : '') || '').trim();
          var _luHistFirst = _luHistNewArr[0];
          var _luHistWhen = ((_luHistFirst.date || '') + ' ' + (_luHistFirst.time || '')).trim();
          var _luContactChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
          _notifyTelegram('📞 <b>1차 컨택 진행</b> — ' + _luName + ' (' + _luTypeLabel + ' · ' + _teamChip(_luSport) + _luSport + ')\n일시: ' + (_luHistWhen || '-') + '\n내용: ' + (_luHistFirst.note || '-') + (_luHistFirst.by ? '\n컨택: ' + _luHistFirst.by : '') + (_luOwnerVal ? '\n배정 담당: ' + _luOwnerVal : ''), _luContactChatId);
        } catch (e) {}
      }
    }
    // 조회 캐시 무효화(축1) — type(성인강습/유소년강습) 두 scope(year/all) 모두 제거해 다음 조회 최신 반영(종목별·row-level 두 경로 공통). 2026-07-08 시토.
    try {
      var _luCache = CacheService.getScriptCache();
      var _luType = String(body.type || '');
      _cacheInvalidateJson_(_luCache, 'licache|' + _luType + '|year');
      _cacheInvalidateJson_(_luCache, 'licache|' + _luType + '|all');
      _cacheInvalidateJson_(_luCache, 'lscache|' + _luType + '|year');
      _cacheInvalidateJson_(_luCache, 'lscache|' + _luType + '|all');
    } catch (e) {}
    _memberLog_(_luLog);
    // 연락 이력 저장이 실패했으면 성공으로 답하지 않는다 — 멤버십 경로(5572줄)와 같은 문구·같은 계약.
    // 다른 칸은 이미 저장됐지만, 팀장이 알아야 할 것은 '적은 글이 안 들어갔다'는 사실이다.
    if (_luHistErr) {
      return _json({ ok: false, error: '연락 이력 저장 실패 — 적으신 내용이 저장되지 않았습니다. 창을 닫지 마시고 다시 시도해 주세요.',
                     detail: _luHistErr, rowIndex: luRowRaw, partial: true });
    }
    return _json({ ok: true, rowIndex: luRowRaw, message: '수정되었습니다.' });
  }

  // (2026-08-25 GM 승인 · 시포 실행 완료 — 강습 다종목 문의 줄 나누기 200건/315줄. 일회성 액션 lesson_multisport_split_0825 는 사용 후 이 자리에서 제거, _RETIRED_ACTIONS_ 등재. 백업=status/backups/lesson_multisport_before_20260825.json.

  // ─── 공간렌트·비즈니스 문의 페이지(CPO): 전체 목록 ───
  //   강습문의(lesson_inquiry_list)와 동일 구조 — type=rent|biz, scope=all(미지정=올해만).
  if (action === 'rentbiz_inquiry_list') {
    var rbRows = _lessonScopeFilter_(_rentbizReadRowsMerged_(body), body);
    return _json({ ok: true, count: rbRows.length, data: rbRows });
  }

  // ─── 공간렌트·비즈니스 문의 페이지(CPO): 통계 (총·이번달·유입경로 분포·상태별) ───
  //   상태 컬럼이 시트에 없으면 hasStatus:false만 반환(신규/처리중/완료 지어내지 않음).
  if (action === 'rentbiz_stats') {
    var rsGid  = _rentbizGidOf_(body);
    var rsRows = _lessonScopeFilter_(_rentbizReadRowsMerged_(body), body);
    var rsTotal = rsRows.length;
    var rsMonth = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM');
    var rsThisMonth = 0;
    var rsChan = {};
    rsRows.forEach(function(row) {
      if (row.timestamp && row.timestamp.slice(0, 7) === rsMonth) rsThisMonth++;
      var ch = _canonicalChannel_(row.channel || '');
      rsChan[ch] = (rsChan[ch] || 0) + 1;
    });
    function _rsSort(obj) {
      return Object.keys(obj).map(function(k){ return { k: k, v: obj[k] }; })
        .sort(function(a, b){ return b.v - a.v; });
    }
    var rsResult = { ok: true, total: rsTotal, thisMonth: rsThisMonth, byChannel: _rsSort(rsChan) };
    var _rsIntakeSh = null;
    try {
      var _rsT2 = String((body && body.type) || '').trim().toLowerCase();
      var _rsIsBiz2 = (_rsT2 === 'biz' || _rsT2 === 'business' || _rsT2 === '비즈니스' || _rsT2 === '비즈니스파트너');
      _rsIntakeSh = _rsIsBiz2 ? _businessIntakeSheet_(false) : _rentalIntakeSheet_(false);
    } catch (e) {}
    // #5 수리(2026-07-18 시포): 병합 intake 탭('진행 상황' 칼럼)도 상태 게이트에 포함 — 구 폼 gid만 보던 갭.
    rsResult.hasStatus = _rentbizHasStatusCol_(rsGid) || (_rsIntakeSh ? _rentbizHasStatusCol_(_rsIntakeSh.getSheetId()) : false);
    if (rsResult.hasStatus) {
      var rsNew = 0, rsInProgress = 0, rsDone = 0;
      rsRows.forEach(function(row) {
        var st = String(row.status || '').trim();
        if (/완료|처리완료|해결|종료/.test(st)) rsDone++;
        else if (/처리중|진행중|응대|컨택|연락중|검토중/.test(st)) rsInProgress++;
        else rsNew++;  // 빈값·미인식 상태 = 미처리(신규)로 정직 분류
      });
      rsResult.new = rsNew; rsResult.inProgress = rsInProgress; rsResult.done = rsDone;
    }
    return _json(rsResult);
  }

  // ─── 오넛티 추석 선물세트 — 남은 수량 공개 조회(2026-08-07 GM 지시) ───
  //   접수 폼이 남은 수량을 보여주는 용도. 숫자만 반환 — 개인정보 일절 미포함(_SURVEY_PUBLIC_ACTIONS 면제 안전).
  if (action === 'ohnutti_remaining') {
    var _orStats = _ohnuttiCapacityStats_();
    return _json({ ok: true, cap: _orStats.cap, remaining: _orStats.remaining, soldOut: _orStats.remaining <= 0 });
  }

  // ─── 오넛티 팀 조회(2026-08-07 GM 지시) — 접속코드 1개로 게이트(기존 STAFF_GATE_PW 방식 재사용, 새 인증체계 없음) ───
  //   포함: 접수번호·수량·수령방법·희망수령일·배송지·상태 + 재고/판매 집계. 제외: 연락처(아예 안 담음).
  //   성함은 첫 글자만 — 클라이언트 마스킹이 아니라 서버가 애초에 원본을 내보내지 않는다(_regMask와 동일 원칙).
  if (action === 'ohnutti_team_list') {
    if (!_ohnuttiTeamAuthed_(body)) return _json({ ok: false, error: '접속코드가 올바르지 않습니다.', noRetry: true });
    var _otRows = [];
    var _otSh = _ohnuttiIntakeSheet_(false);
    if (_otSh) {
      var _otLastCol = _otSh.getLastColumn(), _otLastRow = _otSh.getLastRow();
      if (_otLastRow >= 2 && _otLastCol >= 1) {
        var _otHdr = _otSh.getRange(1, 1, 1, _otLastCol).getValues()[0].map(function(v){ return String(v).trim(); });
        var _otIName = _findCol_(_otHdr, ['성함']), _otINum = _findCol_(_otHdr, ['접수번호']), _otIQty = _findCol_(_otHdr, ['수량']),
            _otISet = _findCol_(_otHdr, ['세트종류']),
            _otIMethod = _findCol_(_otHdr, ['수령방법']), _otIWant = _findCol_(_otHdr, ['희망수령일']), _otIAddr = _findCol_(_otHdr, ['배송지']),
            _otIStat = _findCol_(_otHdr, ['상태']);
        var _otData = _otSh.getRange(2, 1, _otLastRow - 1, _otLastCol).getValues();
        for (var _otR = 0; _otR < _otData.length; _otR++) {
          var _otRow = _otData[_otR];
          var _otNum = _otINum >= 0 ? String(_otRow[_otINum] || '') : '';
          var _otNm = _otIName >= 0 ? String(_otRow[_otIName] || '') : '';
          if (!_otNum && !_otNm) continue;   // 완전 빈 행 스킵
          var _otWantRaw = _otIWant >= 0 ? _otRow[_otIWant] : '';
          var _otWantStr = (_otWantRaw instanceof Date && !isNaN(_otWantRaw.getTime()))
            ? Utilities.formatDate(_otWantRaw, 'Asia/Seoul', 'yyyy-MM-dd') : String(_otWantRaw || '');
          _otRows.push({
            id: _otNum,
            name: _otNm ? (_otNm.charAt(0) + '○○') : '',   // 첫 글자만(예: 김○○) — 서버가 원본을 안 보냄
            qty: _otIQty >= 0 ? (parseInt(_otRow[_otIQty], 10) || 0) : 0,
            setType: _otISet >= 0 ? String(_otRow[_otISet] || '') : '',
            method: _otIMethod >= 0 ? String(_otRow[_otIMethod] || '') : '',
            wantDate: _otWantStr,   // Date 셀이면 YYYY-MM-DD로(문자열화 원본 방지 · 2026-08-07 GM 라이브 발견)
            address: _otIAddr >= 0 ? String(_otRow[_otIAddr] || '') : '',
            status: _otIStat >= 0 ? String(_otRow[_otIStat] || '') : ''
          });
        }
      }
    }
    var _otStats = _ohnuttiCapacityStats_();
    return _json({
      ok: true,
      rows: _otRows,
      stats: {
        cap: _otStats.cap,
        confirmed: _otStats.confirmed,
        pending: _otStats.pending,
        waiting: _otStats.waiting,
        remaining: _otStats.remaining,
        rate: _otStats.cap ? Math.round((_otStats.confirmed + _otStats.pending) / _otStats.cap * 100) : 0
      }
    });
  }

  // ─── 오넛티 팀: 상태 변경(드롭다운 선택 → 즉시저장, 2026-08-07 GM 지시) ───
  //   오넛티팀·웰페리온팀이 이 화면 하나로 소통하는 게 목적 — 접속코드(ohnutti_team_list와 동일 게이트,
  //   새 인증체계 없음)로 쓰기를 막는다. 대상 행은 id(접수번호) 정확일치로만 찾는다(행번호 금지).
  //   동시 수정 대비 LockService로 감싼다. 저장 실패는 실패로 반환(조용한 성공가장 금지).
  if (action === 'ohnutti_status_update') {
    if (!_ohnuttiTeamAuthed_(body)) return _json({ ok: false, error: '접속코드가 올바르지 않습니다.', noRetry: true });
    var _osId = String(body.id || '').trim();
    var _osStatus = String(body.status || '').trim();
    if (!_osId) return _json({ ok: false, error: 'id 필수', noRetry: true });
    if (OHNUTTI_STATUSES.indexOf(_osStatus) < 0) return _json({ ok: false, error: '올바르지 않은 상태값', noRetry: true });
    var _osSh = _ohnuttiIntakeSheet_(false);
    if (!_osSh) return _json({ ok: false, error: '시트 없음' });
    var _osLock = LockService.getScriptLock();
    if (!_osLock.tryLock(8000)) return _json({ ok: false, error: '다른 작업 진행 중 — 잠시 후 다시 시도해 주세요.' });
    try {
      var _osHdr = _osSh.getRange(1, 1, 1, _osSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
      var _osStCi = _findCol_(_osHdr, ['상태']);
      if (_osStCi < 0) return _json({ ok: false, error: '상태 칸 없음' });
      var _osFound = _ohnuttiFindRowById_(_osSh, _osId);
      if (_osFound.count === 0) return _json({ ok: false, error: '해당 접수를 찾을 수 없습니다.' });
      if (_osFound.count > 1) return _json({ ok: false, error: '접수번호 중복 — 확인이 필요합니다.' });
      _osSh.getRange(_osFound.row, _osStCi + 1).setValue(_osStatus);
    } catch (eOs) {
      return _json({ ok: false, error: '저장 실패: ' + eOs.message });
    } finally {
      _osLock.releaseLock();
    }
    return _json({ ok: true, id: _osId, status: _osStatus });
  }

  // ─── (일회성) 오넛티 테스트 접수건 물리 삭제 — 2026-08-07 GM 라이브 발견 ───
  //   ★행번호 금지(INC-020 재발방지) — id(접수번호) 정확일치로만 행을 잡는다.
  //   ★삭제 전 성함 정확일치 필수('오넛티검증테스트-지워주세요'가 아니면 name-mismatch로 거부, 삭제 안 함).
  //   ★GM 정정(2026-08-07): 최초 지시값('[테스트] 확인용')이 오기 — 실제값으로 교체.
  //   guard key로 오호출 차단. dryRun 기본(값 전량 반환) — key + dryRun:0 명시해야 실제 삭제.
  //   사용 완료 후 이 액션 블록은 제거한다(a28b683f3 선례와 동일 운용).
  if (action === 'ohnutti_test_row_delete_20260807') {
    if (String(body.key || '') !== 'wlp_ohnuttitestdel_20260807') return _json({ ok: false, error: 'guard-mismatch' });
    var _tdId = String(body.id || '').trim();
    if (!_tdId) return _json({ ok: false, error: 'id 필수' });
    var _tdDry = (String(body.dryRun || '') !== '0');
    var _tdSh = _ohnuttiIntakeSheet_(false);
    if (!_tdSh) return _json({ ok: false, error: '시트 없음' });
    var _tdFound = _ohnuttiFindRowById_(_tdSh, _tdId);
    if (_tdFound.count === 0) return _json({ ok: false, error: '해당 접수를 찾을 수 없습니다.' });
    if (_tdFound.count > 1) return _json({ ok: false, error: '접수번호 중복 — 확인이 필요합니다.' });
    var _tdHdr = _tdSh.getRange(1, 1, 1, _tdSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    var _tdINm = _findCol_(_tdHdr, ['성함']);
    var _tdRowVals = _tdSh.getRange(_tdFound.row, 1, 1, _tdSh.getLastColumn()).getValues()[0];
    var _tdName = _tdINm >= 0 ? String(_tdRowVals[_tdINm] || '').trim() : '';
    if (_tdName !== '오넛티검증테스트-지워주세요') return _json({ ok: false, error: 'name-mismatch', name: _tdName });
    if (_tdDry) return _json({ ok: true, dryRun: true, row: _tdFound.row, name: _tdName, values: _tdRowVals });
    _tdSh.deleteRow(_tdFound.row);
    SpreadsheetApp.flush();
    return _json({ ok: true, deleted: true, row: _tdFound.row, id: _tdId });
  }

  // ─── (일회성) A열 '날짜' 칸 삭제 — 2026-07-20 시포 · 확정스펙 §1-B(GM 확정 옵션2) ───
  //   선행조건(이미 완료): ① guide(main).html KPI 위치참조 → 이름참조 전환(19a622aa)
  //     ② intake_submit의 A열 쓰기 제거(부분일치 폴백이 투어희망일을 덮어쓰는 경로 차단)
  //   ★ 이름 정확일치로만 잡는다. 부분일치 금지 — '5. 시설투어…날짜는…' 같은 칸을 지울 수 있다.
  //   ★ A열(index 0)이 아니면 거부. 타임스탬프 칸이 없어도 거부(유일한 날짜 칸을 지우는 사고 차단).
  //   dryRun=1이면 아무것도 지우지 않고 삭제 대상·표본만 반환.
  // ─── (일회성) 강습 두 탭 '문의일'(A열) 삭제 — 2026-07-20 GM 지시 ───
  //   타임스탬프가 같은 정보를 시:분:초까지 담고 있어 중복. 쓰기 경로는 이 액션 배포 전에 먼저 제거했다.
  //   안전장치 4중: ①A열 정확일치 '문의일'만(또는 빈 헤더) ②타임스탬프 칸 존재 필수(날짜 정보 전멸 방지)
  //   ③삭제 전 A열 값 전량 백업 반환 ④dryRun 기본.
  // ─── (범용) 멤버십 문의 시트 칸 1개 삭제 — 이름 정확일치 + 값 전량 백업 + dryRun ───
  //   정확일치만(부분일치로 엉뚱한 칸 지우는 사고 방지). 같은 이름이 둘이면 거부.
  //   반환에 값 전량을 담으므로 호출부가 파일로 저장하면 그것이 유일한 복구 근거다.
  // ─── (일회성) 예약을 4슬롯으로 이관 — 2026-07-20 GM 확정 ───
  //   구: G=날짜/H=시간(예약1), I=날짜/J=시간(예약2)  → 신: G·H·I·J 각각 '날짜 시간'(예약1~4)
  //   값 이관 + H/I/J 제목 변경('예약2/3/4')을 한 번에 한다. 제목이 바뀌는 순간 읽기가 신 형식으로 전환되므로
  //   둘이 갈라지면 안 된다. G는 구글폼 문항이라 제목을 못 바꾼다(값만 바꾼다).
  //   멱등: 이미 H 제목이 '예약2'면 no-op.
  // ─── (일회성) 4슬롯 마무리 — 예약3 검증 + 메모 비고 이관 + 예약목록 칸 삭제 (2026-07-20 GM) ───
  // ─── (일회성) 예약1(G) 자유서술 값 → 비고 이관 + 시간 중복 정리 (2026-07-20 GM) ───
  //   G는 구글폼 문항이라 고객이 날짜 대신 문장을 적은 값이 섞여 있다("일정에 맞춰 예약 도와드리겠습니다" 등).
  //   예약 칸에 문장이 있으면 예약으로 못 쓴다 → 비고로 옮기고 G는 비운다(정보 보존, 칸 용도 정리).
  //   덤: 4슬롯 이관 때 내가 시간을 중복시킨 값('체험1 21:00 21:00')은 뒤 중복분을 떼고 옮긴다.
  // ─── (일회성) 예약 시각 30분 단위 정규화 — 2026-07-20 GM 지시 ───
  //   최근 데이터에 12:05 / 10:35 처럼 5분씩 밀린 값이 섞여 있다(예약이 5분 단위로 잡힐 리 없다 = 오염).
  //   GM 지시: 되돌리지 말고 30분 단위로 정리한다. 가장 가까운 00분/30분으로 반올림.
  //   대상: 예약1(G)·예약2(H)·예약3(I)·예약4(J) 네 칸의 '날짜 시간' 값. 날짜만 있는 값은 건드리지 않는다.
  // ─── (일회성) 타임스탬프 서식 표시 + 시각유실 3건 제자리 이동 — 2026-07-20 GM 지시 ───
  //   ①타임스탬프 칸 서식을 'yyyy-mm-dd hh:mm:ss'로 → 값엔 시각이 있는데 시트에 날짜만 보이던 문제 해소.
  //   ②Nicole·한혜수·원유선은 타임스탬프 기준 자리가 아니라 시트 끝에 붙어 있다 → 날짜순 제자리로 옮긴다.
  //   ★행 삭제 없음. moveRows(이동)만 사용 — INC-020(행 삭제 사고) 재발 방지.
  //   ★대상은 행번호가 아니라 성함+연락처로 특정한다.
  // ─── (일회성) 시트 꼬리 구간을 타임스탬프 오름차순 정렬 — 2026-07-20 ───
  //   앞서 moveRows로 3건을 옮기다 서로를 밀어내 순서가 어긋났다(같은 목적지로 순차 이동한 내 로직 오류).
  //   행 삭제·삽입 없이 지정 구간의 '값'만 정렬한다(Range.sort) — 안전.
  //   from/to를 명시적으로 받아 전체 시트를 건드리지 않는다.
  if (action === 'sort_tail_by_ts_20260720') {
    if (String(body.key || '') !== 'wlp_sorttail_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var stFrom = parseInt(body.from || '0', 10), stTo = parseInt(body.to || '0', 10);
    if (!(stFrom > 1) || !(stTo > stFrom)) return _json({ ok: false, error: 'range-required', from: stFrom, to: stTo });
    var stDry = (String(body.dryRun || '') === '1');
    var stSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!stSh) return _json({ ok: false, error: '시트 없음' });
    var stHdr = stSh.getRange(1, 1, 1, stSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var iTs = stHdr.indexOf('타임스탬프'), iNm = stHdr.indexOf('1. 성함');
    if (iTs < 0) return _json({ ok: false, error: 'ts-col-not-found' });
    if (stTo > stSh.getLastRow()) stTo = stSh.getLastRow();
    var rng = stSh.getRange(stFrom, 1, stTo - stFrom + 1, stHdr.length);
    var before = rng.getValues().map(function (r, i) {
      var v = r[iTs];
      return { row: stFrom + i, name: iNm >= 0 ? String(r[iNm] || '') : '',
               ts: (v instanceof Date) ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(v || '') };
    });
    if (stDry) return _json({ ok: true, dryRun: true, from: stFrom, to: stTo, before: before });
    rng.sort({ column: iTs + 1, ascending: true });
    SpreadsheetApp.flush();
    var after = stSh.getRange(stFrom, 1, stTo - stFrom + 1, stHdr.length).getValues().map(function (r, i) {
      var v = r[iTs];
      return { row: stFrom + i, name: iNm >= 0 ? String(r[iNm] || '') : '',
               ts: (v instanceof Date) ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(v || '') };
    });
    return _json({ ok: true, sorted: true, from: stFrom, to: stTo, after: after });
  }

  if (action === 'fix_ts_display_move_20260720') {
    if (String(body.key || '') !== 'wlp_tsfix_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var tfDry = (String(body.dryRun || '') === '1');
    var tfSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!tfSh) return _json({ ok: false, error: '시트 없음' });
    var tfHdr = tfSh.getRange(1, 1, 1, tfSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var iTs = tfHdr.indexOf('타임스탬프'), iNm = tfHdr.indexOf('1. 성함'), iPh = tfHdr.indexOf('2. 연락처');
    if (iTs < 0 || iNm < 0 || iPh < 0) return _json({ ok: false, error: 'col-not-found' });
    var tfLast = tfSh.getLastRow();
    // ① 서식
    if (!tfDry && tfLast >= 2) { tfSh.getRange(2, iTs + 1, tfLast - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm:ss'); SpreadsheetApp.flush(); }
    // ② 이동 대상 특정 (성함+연락처)
    var targets = [
      // ★날짜까지 대조키에 넣는다 — 한혜수님은 같은 번호로 6/18·7/18 두 건이 있어(재문의) 이름+연락처만으론 특정 불가.
      //   안전장치가 'not-unique'로 거부한 것이 맞았다. 키를 빼는 게 아니라 더하는 방향으로 해결한다(INC-020 교훈).
      { name: 'Nicole choi', phone: '010-9119-2494', date: '2026-07-18' },
      { name: '한혜수',      phone: '010-4108-7735', date: '2026-07-18' },
      { name: '원유선',      phone: '010-2217-1558', date: '2026-07-18' }
    ];
    var norm = function (x) { return String(x || '').replace(/\D/g, ''); };
    var all = tfLast >= 2 ? tfSh.getRange(2, 1, tfLast - 1, tfHdr.length).getValues() : [];
    var found = [], notUnique = [];
    targets.forEach(function (t) {
      var hits = [];
      for (var i = 0; i < all.length; i++) {
        if (String(all[i][iNm] || '').trim() !== t.name) continue;
        if (norm(all[i][iPh]) !== norm(t.phone)) continue;
        var tv = all[i][iTs];
        var tvs = (tv instanceof Date) ? Utilities.formatDate(tv, 'Asia/Seoul', 'yyyy-MM-dd') : String(tv || '').substring(0, 10);
        if (t.date && tvs !== t.date) continue;
        hits.push(i + 2);
      }
      if (hits.length !== 1) { notUnique.push({ name: t.name, hits: hits.length }); return; }
      var ts = all[hits[0] - 2][iTs];
      found.push({ name: t.name, row: hits[0], ts: (ts instanceof Date) ? Utilities.formatDate(ts, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(ts || '') });
    });
    if (notUnique.length) return _json({ ok: false, error: 'not-unique', detail: notUnique });
    // 각 대상이 가야 할 위치 = 자기보다 늦은 타임스탬프가 처음 나오는 행
    var dests = found.map(function (f) {
      var myTs = f.ts.substring(0, 10);
      var dest = -1;
      for (var i = 0; i < all.length; i++) {
        var r = i + 2;
        if (r === f.row) continue;
        var v = all[i][iTs];
        var vs = (v instanceof Date) ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd') : String(v || '').substring(0, 10);
        if (!vs) continue;
        if (vs > myTs) { dest = r; break; }
      }
      return { name: f.name, from: f.row, ts: f.ts, moveBefore: dest };
    });
    if (tfDry) return _json({ ok: true, dryRun: true, formatWillSet: 'yyyy-mm-dd hh:mm:ss', targets: dests, lastRow: tfLast });
    // 이동 — 아래 행부터 처리해야 위 행 이동이 인덱스를 흔들지 않는다
    var moved = [];
    dests.sort(function (a, b) { return b.from - a.from; }).forEach(function (m) {
      if (m.moveBefore < 0 || m.moveBefore === m.from) { moved.push({ name: m.name, skipped: '이미 제자리' }); return; }
      tfSh.moveRows(tfSh.getRange(m.from + ':' + m.from), m.moveBefore);
      SpreadsheetApp.flush();
      moved.push({ name: m.name, from: m.from, to: m.moveBefore, ts: m.ts });
    });
    return _json({ ok: true, formatSet: true, moved: moved });
  }

  if (action === 'normalize_slot_time_20260720') {
    if (String(body.key || '') !== 'wlp_normtime_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var ntDry = (String(body.dryRun || '') === '1');
    var ntSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!ntSh) return _json({ ok: false, error: '시트 없음' });
    var ntHdr = ntSh.getRange(1, 1, 1, ntSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var ntN = function (x) { return String(x || '').replace(/\s+/g, ''); };
    var slots = [];
    for (var ni = 0; ni < ntHdr.length; ni++) {
      var hn = ntN(ntHdr[ni]);
      if (hn.indexOf('5.시설투어') === 0) slots[0] = ni;
      if (hn === '예약2') slots[1] = ni;
      if (hn === '예약3') slots[2] = ni;
      if (hn === '예약4') slots[3] = ni;
    }
    var iNm = ntHdr.indexOf('1. 성함');
    if (slots[0] === undefined || slots[1] === undefined) return _json({ ok: false, error: 'col-not-found', slots: slots });
    var ntLast = ntSh.getLastRow();
    var ntAll = ntLast >= 2 ? ntSh.getRange(2, 1, ntLast - 1, ntHdr.length).getValues() : [];
    var pad = function (n) { return ('0' + n).slice(-2); };
    var plan = [];
    for (var nr = 0; nr < ntAll.length; nr++) {
      var R = ntAll[nr];
      for (var sl = 0; sl < 4; sl++) {
        var ci = slots[sl];
        if (ci === undefined) continue;
        var raw = R[ci];
        var d = _miToISO_(raw), t = _miTime_(raw);
        if (!d || !t) continue;                       // 날짜만이면 대상 아님
        var mm = t.split(':'); if (mm.length < 2) continue;
        var H = parseInt(mm[0], 10), M = parseInt(mm[1], 10);
        if (isNaN(H) || isNaN(M)) continue;
        var total = H * 60 + M;
        var rounded = Math.round(total / 30) * 30;    // 가장 가까운 30분
        if (rounded >= 1440) rounded = 1410;          // 24:00 방지 → 23:30
        if (rounded === total) continue;              // 이미 정각/30분이면 통과
        var nh = Math.floor(rounded / 60), nmn = rounded % 60;
        plan.push({ row: nr + 2, slot: sl + 1, col: ci, name: iNm >= 0 ? String(R[iNm] || '') : '',
                    from: d + ' ' + t, to: d + ' ' + pad(nh) + ':' + pad(nmn) });
      }
    }
    if (ntDry) return _json({ ok: true, dryRun: true, count: plan.length, plan: plan });
    plan.forEach(function (p) { ntSh.getRange(p.row, p.col + 1).setValue(p.to); });
    SpreadsheetApp.flush();
    return _json({ ok: true, fixed: plan.length, plan: plan });
  }

  if (action === 'move_freetext_g_20260720') {
    if (String(body.key || '') !== 'wlp_freetext_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var mgDry = (String(body.dryRun || '') === '1');
    var mgSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!mgSh) return _json({ ok: false, error: '시트 없음' });
    var mgHdr = mgSh.getRange(1, 1, 1, mgSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var mgN = function (x) { return String(x || '').replace(/\s+/g, ''); };
    var iG = -1, iBigo = -1, iName = -1;
    for (var gi = 0; gi < mgHdr.length; gi++) {
      var hn = mgN(mgHdr[gi]);
      if (iG < 0 && hn.indexOf('5.시설투어') === 0) iG = gi;
      if (hn === '비고') iBigo = gi;
      if (hn === '1.성함') iName = gi;
    }
    if (iG < 0 || iBigo < 0) return _json({ ok: false, error: 'col-not-found', iG: iG, iBigo: iBigo });
    var mgLast = mgSh.getLastRow();
    var mgAll = mgLast >= 2 ? mgSh.getRange(2, 1, mgLast - 1, mgHdr.length).getValues() : [];
    var mgPlan = [];
    for (var mr = 0; mr < mgAll.length; mr++) {
      var R = mgAll[mr], v = R[iG];
      if (v instanceof Date) continue;                       // 진짜 날짜값은 대상 아님
      var vs = String(v == null ? '' : v).trim();
      if (!vs) continue;
      if (/^\d{4}-\d{2}-\d{2}( \d{1,2}:\d{2})?$/.test(vs)) continue;   // 정상 형식 통과
      // 시간 중복 정리: 끝에 붙은 ' HH:MM' 이 앞에도 있으면 뒤엣것 제거
      var cleaned = vs.replace(/\s+(\d{1,2}:\d{2})$/, function (m, t) { return vs.indexOf(t) < vs.length - m.length ? '' : m; });
      var cur = String(R[iBigo] == null ? '' : R[iBigo]).trim();
      if (cur.indexOf(cleaned) >= 0) { mgPlan.push({ row: mr + 2, name: iName >= 0 ? String(R[iName] || '') : '', from: vs, to: cleaned, bigo: '(이미 있음)', skipBigo: true }); continue; }
      mgPlan.push({ row: mr + 2, name: iName >= 0 ? String(R[iName] || '') : '', from: vs, to: cleaned,
                    bigo: (cur ? cur + ' / ' : '') + '희망일 메모: ' + cleaned });
    }
    if (mgDry) return _json({ ok: true, dryRun: true, count: mgPlan.length, plan: mgPlan });
    mgPlan.forEach(function (p) {
      if (!p.skipBigo) mgSh.getRange(p.row, iBigo + 1).setValue(p.bigo);
      mgSh.getRange(p.row, iG + 1).setValue('');
    });
    SpreadsheetApp.flush();
    return _json({ ok: true, moved: mgPlan.length, plan: mgPlan });
  }

  if (action === 'finish_slot4_20260720') {
    if (String(body.key || '') !== 'wlp_finish_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var fsDry = (String(body.dryRun || '') === '1');
    var fsSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!fsSh) return _json({ ok: false, error: '시트 없음' });
    var fsHdr = fsSh.getRange(1, 1, 1, fsSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var fsN = function (x) { return String(x || '').replace(/\s+/g, ''); };
    var iR3 = -1, iRs = -1, iBigo = -1, iName = -1;
    for (var fi = 0; fi < fsHdr.length; fi++) {
      var hn = fsN(fsHdr[fi]);
      if (hn === '예약3') iR3 = fi;
      if (hn === '예약목록') iRs = fi;
      if (hn === '비고') iBigo = fi;
      if (hn === '1.성함') iName = fi;
    }
    if (iRs < 0) return _json({ ok: true, note: '예약목록 칸 이미 없음', headers: fsHdr });
    if (iR3 < 0 || iBigo < 0) return _json({ ok: false, error: 'col-not-found', iR3: iR3, iBigo: iBigo });
    var fsLast = fsSh.getLastRow();
    var fsAll = fsLast >= 2 ? fsSh.getRange(2, 1, fsLast - 1, fsHdr.length).getValues() : [];
    var chk3 = [], notes = [];
    for (var fr = 0; fr < fsAll.length; fr++) {
      var R = fsAll[fr], raw = String(R[iRs] == null ? '' : R[iRs]).trim();
      if (!raw) continue;
      var arr = _resParse_(raw);
      var nm = iName >= 0 ? String(R[iName] || '') : '';
      if (arr.length > 2) chk3.push({ row: fr + 2, name: nm, expect: arr[2].date || '', actual: String(R[iR3] == null ? '' : R[iR3]).trim() ? _miToISO_(R[iR3]) : '' });
      for (var ai = 0; ai < arr.length; ai++) {
        var nt = String((arr[ai] || {}).note || '').trim();
        if (!nt) continue;
        var cur = String(R[iBigo] == null ? '' : R[iBigo]).trim();
        if (cur.indexOf(nt) >= 0) continue;
        notes.push({ row: fr + 2, name: nm, note: nt, curBigo: cur.substring(0, 40), newBigo: (cur ? cur + ' / ' : '') + '예약메모: ' + nt });
      }
    }
    if (fsDry) return _json({ ok: true, dryRun: true, 예약3검증: chk3, 메모이관: notes, colsBefore: fsHdr.length });
    notes.forEach(function (n) { fsSh.getRange(n.row, iBigo + 1).setValue(n.newBigo); });
    SpreadsheetApp.flush();
    fsSh.deleteColumn(iRs + 1);
    SpreadsheetApp.flush();
    var fsAfter = fsSh.getRange(1, 1, 1, fsSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, 메모이관: notes.length, 예약3검증: chk3, colsBefore: fsHdr.length, colsAfter: fsAfter.length, headersAfter: fsAfter });
  }

  if (action === 'migrate_slot4_20260720') {
    if (String(body.key || '') !== 'wlp_slot4_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var msDry = (String(body.dryRun || '') === '1');
    var msSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!msSh) return _json({ ok: false, error: '시트 없음' });
    var msHdr = msSh.getRange(1, 1, 1, msSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var msN = function (x) { return String(x || '').replace(/\s+/g, ''); };
    var iT = -1, iE1 = -1, iV2 = -1, iE2 = -1, iRs = -1;
    for (var mi = 0; mi < msHdr.length; mi++) {
      var hn = msN(msHdr[mi]);
      if (iT < 0 && hn.indexOf('5.시설투어') === 0) iT = mi;
      if (iE1 < 0 && (hn === '체험1확정시간' || hn === '예약2')) iE1 = mi;
      if (iV2 < 0 && hn.indexOf('시설체험예약2') === 0) iV2 = mi;
      if (iE2 < 0 && (hn === '체험2확정시간' || hn === '예약4')) iE2 = mi;
      if (iRs < 0 && hn === '예약목록') iRs = mi;
    }
    if (iT < 0 || iE1 < 0 || iV2 < 0 || iE2 < 0) return _json({ ok: false, error: 'col-not-found', iT: iT, iE1: iE1, iV2: iV2, iE2: iE2, headers: msHdr });
    if (msN(msHdr[iE1]) === '예약2') return _json({ ok: true, note: '이미 이관됨(멱등)', headers: msHdr });
    var msLast = msSh.getLastRow();
    var msAll = msLast >= 2 ? msSh.getRange(2, 1, msLast - 1, msHdr.length).getValues() : [];
    var comb = function (d, t) { d = String(d || '').trim(); t = String(t || '').trim(); return d ? (t ? (d + ' ' + t) : d) : ''; };
    var msRows = [], msChanged = 0, msSample = [];
    for (var mr = 0; mr < msAll.length; mr++) {
      var R = msAll[mr];
      var d1 = _miToISO_(R[iT]) || _miToISO_(R[iE1]), t1 = _miTime_(R[iE1]);
      var d2 = _miToISO_(R[iV2]) || _miToISO_(R[iE2]), t2 = _miTime_(R[iE2]);
      var s1 = comb(d1, t1), s2 = comb(d2, t2), s3 = '', s4 = '';
      if (iRs >= 0) {
        var arr = _resParse_(R[iRs]);
        if (arr.length > 2) s3 = comb(arr[2].date, arr[2].time);
        if (arr.length > 3) s4 = comb(arr[3].date, arr[3].time);
      }
      msRows.push([s1, s2, s3, s4]);
      if (s1 || s2 || s3 || s4) { msChanged++; if (msSample.length < 5) msSample.push({ row: mr + 2, slot1: s1, slot2: s2, slot3: s3, slot4: s4 }); }
    }
    if (msDry) return _json({ ok: true, dryRun: true, cols: { G: msHdr[iT], H: msHdr[iE1], I: msHdr[iV2], J: msHdr[iE2], 예약목록: iRs }, rowsWithData: msChanged, totalRows: msAll.length, sample: msSample });
    for (var mw = 0; mw < msRows.length; mw++) {
      var rw = mw + 2, v = msRows[mw];
      msSh.getRange(rw, iT + 1).setValue(v[0]);
      msSh.getRange(rw, iE1 + 1).setValue(v[1]);
      msSh.getRange(rw, iV2 + 1).setValue(v[2]);
      msSh.getRange(rw, iE2 + 1).setValue(v[3]);
    }
    SpreadsheetApp.flush();
    msSh.getRange(1, iE1 + 1).setValue('예약2');
    msSh.getRange(1, iV2 + 1).setValue('예약3');
    msSh.getRange(1, iE2 + 1).setValue('예약4');
    SpreadsheetApp.flush();
    var msAfter = msSh.getRange(1, 1, 1, msSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, migratedRows: msChanged, totalRows: msAll.length, headersAfter: msAfter });
  }

  if (action === 'del_col_by_name_20260720') {
    if (String(body.key || '') !== 'wlp_delcol_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var dnName = String(body.name || '').trim();
    if (!dnName) return _json({ ok: false, error: 'name-required' });
    var dnDry = (String(body.dryRun || '') === '1');
    var dnSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!dnSh) return _json({ ok: false, error: '시트 없음' });
    var dnHdr = dnSh.getRange(1, 1, 1, dnSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var dnNorm = function (x) { return String(x || '').replace(/\s+/g, ''); };
    var dnIdx = -1, dnHits = 0;
    for (var dni = 0; dni < dnHdr.length; dni++) { if (dnNorm(dnHdr[dni]) === dnNorm(dnName)) { dnHits++; if (dnIdx < 0) dnIdx = dni; } }
    if (dnIdx < 0) return _json({ ok: false, error: 'no-target', name: dnName, headers: dnHdr });
    if (dnHits > 1) return _json({ ok: false, error: 'ambiguous', hits: dnHits });
    var dnLast = dnSh.getLastRow(), dnBackup = [], dnFilled = 0;
    if (dnLast >= 2) {
      var dnNameI = dnHdr.indexOf('1. 성함'), dnPhoneI = dnHdr.indexOf('2. 연락처');
      var dnAll = dnSh.getRange(2, 1, dnLast - 1, dnHdr.length).getValues();
      for (var dnr = 0; dnr < dnAll.length; dnr++) {
        var dv = dnAll[dnr][dnIdx];
        var dvs = (dv instanceof Date) ? Utilities.formatDate(dv, 'Asia/Seoul', 'yyyy-MM-dd') : String(dv == null ? '' : dv).trim();
        if (!dvs) continue;
        dnFilled++;
        dnBackup.push({ row: dnr + 2, name: dnNameI >= 0 ? String(dnAll[dnr][dnNameI] || '') : '', phone: dnPhoneI >= 0 ? String(dnAll[dnr][dnPhoneI] || '') : '', value: dvs });
      }
    }
    if (dnDry) return _json({ ok: true, dryRun: true, name: dnHdr[dnIdx], idx: dnIdx, colsBefore: dnHdr.length, filled: dnFilled, totalRows: Math.max(0, dnLast - 1), sample: dnBackup.slice(0, 5) });
    dnSh.deleteColumn(dnIdx + 1);
    SpreadsheetApp.flush();
    var dnAfter = dnSh.getRange(1, 1, 1, dnSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, deleted: dnHdr[dnIdx], colsBefore: dnHdr.length, colsAfter: dnAfter.length, backedUp: dnBackup.length, backup: dnBackup, headersAfter: dnAfter });
  }

  if (action === 'del_lesson_datecol_20260720') {
    if (String(body.key || '') !== 'wlp_dellesson_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var dlDry2 = (String(body.dryRun || '') === '1');
    var dlGids = [LESSON_GID, LESSON_GID_YOUTH];
    var dlOut = [];
    for (var dg = 0; dg < dlGids.length; dg++) {
      var g = dlGids[dg];
      var sh = _sheetByGid_(LESSON_SS_ID, g);
      if (!sh) { dlOut.push({ gid: g, error: 'sheet_not_found' }); continue; }
      var hdr = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
      var h0 = hdr[0] || '';
      if (h0 && h0.replace(/\s+/g, '') !== '문의일') { dlOut.push({ gid: g, skipped: true, reason: 'A열이 문의일이 아님', a0: h0 }); continue; }
      var tsIx = -1;
      for (var ti = 0; ti < hdr.length; ti++) { if (hdr[ti].replace(/\s+/g, '') === '타임스탬프') { tsIx = ti; break; } }
      if (tsIx < 0) { dlOut.push({ gid: g, skipped: true, reason: '타임스탬프 칸 없음 — 삭제 거부' }); continue; }
      var last = sh.getLastRow(), filled = 0, backup = [], sample = [];
      if (last >= 2) {
        var col = sh.getRange(2, 1, last - 1, 1).getValues();
        var tsCol = sh.getRange(2, tsIx + 1, last - 1, 1).getValues();
        for (var ri = 0; ri < col.length; ri++) {
          var v = col[ri][0];
          var vs = (v instanceof Date) ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd') : String(v == null ? '' : v).trim();
          if (!vs) continue;
          filled++;
          backup.push({ row: ri + 2, value: vs });
          if (sample.length < 3) {
            var tv = tsCol[ri][0];
            sample.push({ row: ri + 2, 문의일: vs, 타임스탬프: (tv instanceof Date) ? Utilities.formatDate(tv, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : String(tv || '') });
          }
        }
      }
      if (dlDry2) { dlOut.push({ gid: g, a0: h0, tsIdx: tsIx, colsBefore: hdr.length, filled: filled, totalRows: Math.max(0, last - 1), sample: sample }); continue; }
      sh.deleteColumn(1);
      SpreadsheetApp.flush();
      var hdr2 = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
      dlOut.push({ gid: g, deleted: true, colsBefore: hdr.length, colsAfter: hdr2.length, backedUp: backup.length, backup: backup, newFirstHeader: hdr2[0] });
    }
    return _json({ ok: true, dryRun: dlDry2, results: dlOut });
  }

  // ─── 공용 가드(2026-07-20 GM 부재 중 보호조치) ───
  //   §1-A 병합 과정에서 '유입경로(자동)' 이름이 개칭·재사용되며 이름을 더 이상 신뢰할 수 없게 됐다
  //   (구F열='문의 경로(중분류)'가 개칭되며 616건 채널 정본을 담은 채 이 이름을 쓰게 됨).
  //   그래서 이름이 아니라 '삭제 직전 실측 값 건수'로 막는다. dedup_autoroute·finalize_cols·consolidate_cols
  //   세 액션의 칸 삭제 호출부는 이 함수를 통과해야 한다. 10건 이상이면 거부 + GM 업무보고봇방(TELEGRAM_CHAT_ID) 경고.
  //   ★삭제만 막는다 — 값 이관 등 다른 동작·기존 안전장치(값 0건 조건 등)는 그대로 둔다.
  function _guardColDeleteByContent20260720_(sh, colIdx1, colName) {
    var last = sh.getLastRow();
    var filled = 0;
    if (last >= 2) {
      var vals = sh.getRange(2, colIdx1, last - 1, 1).getValues();
      for (var gi = 0; gi < vals.length; gi++) {
        if (String(vals[gi][0] == null ? '' : vals[gi][0]).trim()) filled++;
        if (filled >= 10) break;
      }
    }
    if (filled >= 10) {
      try { _notifyTelegram('🛑 [가드] 칸 삭제 거부 — "' + colName + '" 칸 값 ' + filled + '건+(임계10) — §1-A 채널칸 오삭제 방지 가드 작동. GM 확인 필요.'); } catch (e) {}
      return false;
    }
    return true;
  }

  // ─── (일회성) 중복된 '유입경로(자동)' 칸 해소 — 2026-07-20 ───
  //   중분류를 '유입경로(자동)'으로 개칭한 결과 같은 이름 칸이 둘이 됐다(F=616건 정본 / S=폼 소유 3건).
  //   S는 우리 코드가 구글폼에 만든 기술용 문항('자동 입력 항목 — 비워두셔도 됩니다')이라 칸만 지우면 되살아난다.
  //   → ①S의 값을 앞 칸(정본)의 빈 행에 합치고 ②폼 문항 삭제 ③S 칸 삭제. 순서 고정.
  //   안전장치: S에 값이 6건 이상이면 중단(예상과 다르면 사람이 본다). + 삭제 직전 재확인(공용 가드, 임계10).
  if (action === 'dedup_autoroute_20260720') {
    if (String(body.key || '') !== 'wlp_dedup_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var daDry = (String(body.dryRun || '') === '1');
    var daSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!daSh) return _json({ ok: false, error: '시트 없음' });
    var daHdr = daSh.getRange(1, 1, 1, daSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var daIdx = [];
    for (var dai = 0; dai < daHdr.length; dai++) { if (daHdr[dai].replace(/\s+/g, '') === '유입경로(자동)') daIdx.push(dai); }
    if (daIdx.length < 2) return _json({ ok: true, note: '중복 아님', found: daIdx.length, headers: daHdr });
    var daKeep = daIdx[0], daDrop = daIdx[daIdx.length - 1];
    var daLast = daSh.getLastRow();
    var daAll = daLast >= 2 ? daSh.getRange(2, 1, daLast - 1, daHdr.length).getValues() : [];
    var daMoves = [], daDropFilled = 0;
    for (var dar = 0; dar < daAll.length; dar++) {
      var dv = String(daAll[dar][daDrop] == null ? '' : daAll[dar][daDrop]).trim();
      if (!dv) continue;
      daDropFilled++;
      if (!String(daAll[dar][daKeep] == null ? '' : daAll[dar][daKeep]).trim()) daMoves.push({ row: dar + 2, value: dv });
    }
    if (daDropFilled > 5) return _json({ ok: false, error: 'unexpected-volume', detail: '삭제 대상 칸에 값이 ' + daDropFilled + '건 — 6건 이상이면 중단', dropIdx: daDrop });
    var daFormUrl = '', daItemTitle = '', daHasItem = false;
    try {
      daFormUrl = daSh.getFormUrl() || '';
      if (daFormUrl) {
        FormApp.openByUrl(daFormUrl).getItems().forEach(function (it) {
          if (String(it.getTitle() || '').replace(/\s+/g, '') === '유입경로(자동)') { daHasItem = true; daItemTitle = it.getTitle(); }
        });
      }
    } catch (eA) { return _json({ ok: false, error: 'form_open_fail', detail: String(eA.message || eA) }); }
    if (daDry) return _json({ ok: true, dryRun: true, keepIdx: daKeep, dropIdx: daDrop,
                              dropFilled: daDropFilled, movesToKeep: daMoves.length, moveSample: daMoves.slice(0, 5),
                              formItemFound: daHasItem, formItemTitle: daItemTitle, colsBefore: daHdr.length });
    // ① 값 합치기
    daMoves.forEach(function (m) { daSh.getRange(m.row, daKeep + 1).setValue(m.value); });
    SpreadsheetApp.flush();
    // ② 폼 문항 삭제(되살아남 방지)
    var daFormDeleted = false;
    if (daHasItem) {
      try {
        var daForm = FormApp.openByUrl(daFormUrl);
        daForm.getItems().forEach(function (it) { if (String(it.getTitle() || '').replace(/\s+/g, '') === '유입경로(자동)') { daForm.deleteItem(it); daFormDeleted = true; } });
      } catch (eB) { return _json({ ok: false, error: 'form_item_delete_fail', detail: String(eB.message || eB), movedAlready: daMoves.length }); }
    }
    // ③ 칸 삭제(위치 재조회)
    var daHdr2 = daSh.getRange(1, 1, 1, daSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var daIdx2 = [];
    for (var db = 0; db < daHdr2.length; db++) { if (daHdr2[db].replace(/\s+/g, '') === '유입경로(자동)') daIdx2.push(db); }
    var daDeleted = false;
    if (daIdx2.length >= 2) {
      var daDelIdx1 = daIdx2[daIdx2.length - 1] + 1;
      if (!_guardColDeleteByContent20260720_(daSh, daDelIdx1, daHdr2[daDelIdx1 - 1])) {
        return _json({ ok: false, error: 'guard-blocked', detail: '삭제 대상 칸에 값 10건 이상 — 중단(채널칸 오삭제 방지)', colName: daHdr2[daDelIdx1 - 1], movedAlready: daMoves.length, formDeleted: daFormDeleted });
      }
      daSh.deleteColumn(daDelIdx1); daDeleted = true; SpreadsheetApp.flush();
    }
    var daAfter = daSh.getRange(1, 1, 1, daSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, moved: daMoves.length, formDeleted: daFormDeleted, colDeleted: daDeleted,
                   colsBefore: daHdr.length, colsAfter: daAfter.length, headersAfter: daAfter });
  }

  // ─── (일회성) 잉여 칸 최종 정리 2차 — 2026-07-20 GM 확정 지시 ───
  //   GM: "등록일은 그냥 삭제해도 되고 / 등록매칭은 진행상태에 SUC 변경되면 '등록' / 연락이력은 Contact1~3
  //        / 방문완료일은 체험일·체험시간 / 등록종목은 유효회원시트 / (유입경로는) 소분류가 아니라 중분류야"
  //   ① 연락이력 → Contact1/2/3 (비어있는 칸에만. 3건 초과분은 남긴다 — 넣을 칸이 없다)
  //   ② 방문완료일 → 체험1 날짜/확정시간 (비어있을 때만)
  //   ③ 등록일(자동)·등록매칭(자동) → 삭제(등록매칭은 진행현황 SUC에서 파생 가능하므로 보관 불필요)
  //   ④ '문의 경로 (중분류)' → '유입경로(자동)'으로 개칭. 기존 유입경로(자동) 칸의 값은 중분류가 빈 행에만 옮긴다.
  //   ※ 등록종목(유효회원 이관)은 이름+연락처 대조가 필요해 이 액션에 넣지 않는다(별건).
  if (action === 'finalize_cols_20260720') {
    if (String(body.key || '') !== 'wlp_final_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var fcDry = (String(body.dryRun || '') === '1');
    var fcSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!fcSh) return _json({ ok: false, error: '시트 없음' });
    var fcHdr = fcSh.getRange(1, 1, 1, fcSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var fcNorm = function (s) { return String(s || '').replace(/\s+/g, ''); };
    var fcFind = function (want) { for (var i = 0; i < fcHdr.length; i++) { if (fcNorm(fcHdr[i]) === fcNorm(want)) return i; } return -1; };
    var fcStarts = function (want) { for (var i = 0; i < fcHdr.length; i++) { if (fcNorm(fcHdr[i]).indexOf(fcNorm(want)) === 0) return i; } return -1; };

    var iHist2 = fcFind('연락이력'), iC1 = fcFind('Contact1'), iC2 = fcFind('Contact2'), iC3 = fcFind('Contact3');
    var iVis2  = fcFind('방문완료일'), iExpD = fcStarts('체험1'), iExpT = -1;
    // 체험1 계열: '체험1 확정시간'이 시간칸. 날짜칸은 '5. 시설투어~'(투어희망일)가 아니라 별도가 없으면 시간칸만 사용.
    for (var fe = 0; fe < fcHdr.length; fe++) { if (fcNorm(fcHdr[fe]).indexOf('체험1') === 0 && fcNorm(fcHdr[fe]).indexOf('확정시간') >= 0) { iExpT = fe; break; } }
    var iMid   = fcStarts('문의 경로 (중분류)'), iAuto = fcFind('유입경로(자동)');
    var fcLast = fcSh.getLastRow();
    var fcAll  = fcLast >= 2 ? fcSh.getRange(2, 1, fcLast - 1, fcHdr.length).getValues() : [];

    var fcPlan = { histToContact: [], visitToExp: [], autoToMid: [] };
    for (var fr = 0; fr < fcAll.length; fr++) {
      var rowN = fr + 2, R = fcAll[fr];
      // ① 연락이력 → Contact1/2/3
      if (iHist2 >= 0) {
        var hv = String(R[iHist2] == null ? '' : R[iHist2]).trim();
        if (hv) {
          var arr = _resParse_(hv), slots = [iC1, iC2, iC3], put = [];
          for (var hi = 0; hi < arr.length && hi < 3; hi++) {
            var sc = slots[hi];
            if (sc < 0) continue;
            if (String(R[sc] == null ? '' : R[sc]).trim()) continue;   // 이미 값 있으면 덮지 않는다
            var e = arr[hi] || {};
            var pre = String((e.date || '') + ' ' + (e.time || '')).trim();
            var txt = pre ? (pre + ' ' + String(e.note || '').trim()).trim() : String(e.note || '').trim();
            if (txt) put.push({ col: sc, text: txt });
          }
          if (put.length) fcPlan.histToContact.push({ row: rowN, put: put, overflow: Math.max(0, arr.length - 3) });
        }
      }
      // ② 방문완료일 → 체험1 확정시간(값이 비어있을 때만)
      if (iVis2 >= 0 && iExpT >= 0) {
        var vv = R[iVis2];
        var vs = (vv instanceof Date) ? Utilities.formatDate(vv, 'Asia/Seoul', 'yyyy-MM-dd') : String(vv == null ? '' : vv).trim();
        if (vs && !String(R[iExpT] == null ? '' : R[iExpT]).trim()) fcPlan.visitToExp.push({ row: rowN, value: vs });
      }
      // ④ 유입경로(자동) → 중분류(빈 행만)
      if (iAuto >= 0 && iMid >= 0) {
        var av2 = String(R[iAuto] == null ? '' : R[iAuto]).trim();
        if (av2 && !String(R[iMid] == null ? '' : R[iMid]).trim()) fcPlan.autoToMid.push({ row: rowN, value: av2 });
      }
    }

    if (fcDry) {
      return _json({ ok: true, dryRun: true, colsBefore: fcHdr.length,
                     cols: { 연락이력: iHist2, Contact1: iC1, 방문완료일: iVis2, 체험1시간: iExpT, 중분류: iMid, 유입경로자동: iAuto },
                     plan: { 'histToContact': fcPlan.histToContact.length, 'visitToExp': fcPlan.visitToExp.length, 'autoToMid': fcPlan.autoToMid.length },
                     samples: { hist: fcPlan.histToContact.slice(0, 2), visit: fcPlan.visitToExp.slice(0, 3), auto: fcPlan.autoToMid.slice(0, 3) },
                     willDelete: ['등록일(자동)', '등록매칭(자동)', '방문완료일', '연락이력'],
                     willRename: iMid >= 0 ? (fcHdr[iMid] + ' → 유입경로(자동)') : '중분류 없음',
                     headers: fcHdr });
    }

    // 실행 ①②④ 값 이관
    fcPlan.histToContact.forEach(function (p) { p.put.forEach(function (x) { fcSh.getRange(p.row, x.col + 1).setValue(x.text); }); });
    fcPlan.visitToExp.forEach(function (p) { fcSh.getRange(p.row, iExpT + 1).setValue(p.value); });
    fcPlan.autoToMid.forEach(function (p) { fcSh.getRange(p.row, iMid + 1).setValue(p.value); });
    SpreadsheetApp.flush();
    // ③ 삭제 — 뒤 인덱스부터
    var fcDelNames = ['등록일(자동)', '등록매칭(자동)', '방문완료일', '연락이력'];
    var fcDelIdx = fcDelNames.map(function (n) { return { name: n, idx: fcFind(n) }; }).filter(function (x) { return x.idx >= 0; })
                     .sort(function (a, b) { return b.idx - a.idx; });
    var fcBlocked = [];
    fcDelIdx.forEach(function (t) {
      if (_guardColDeleteByContent20260720_(fcSh, t.idx + 1, t.name)) { fcSh.deleteColumn(t.idx + 1); }
      else { fcBlocked.push(t.name); }
    });
    SpreadsheetApp.flush();
    // ④ 개칭 — 삭제 후 위치 재조회
    var fcHdr2 = fcSh.getRange(1, 1, 1, fcSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var iMid2 = -1;
    for (var fm = 0; fm < fcHdr2.length; fm++) { if (fcNorm(fcHdr2[fm]).indexOf(fcNorm('문의 경로 (중분류)')) === 0) { iMid2 = fm; break; } }
    var renamed = false;
    if (iMid2 >= 0) { fcSh.getRange(1, iMid2 + 1).setValue('유입경로(자동)'); renamed = true; SpreadsheetApp.flush(); }
    var fcAfter = fcSh.getRange(1, 1, 1, fcSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, moved: { 연락이력: fcPlan.histToContact.length, 방문완료일: fcPlan.visitToExp.length, 자동: fcPlan.autoToMid.length },
                   deleted: fcDelIdx.map(function(t){ return t.name; }).filter(function(n){ return fcBlocked.indexOf(n) < 0; }),
                   blocked: fcBlocked, renamed: renamed,
                   colsBefore: fcHdr.length, colsAfter: fcAfter.length, headersAfter: fcAfter });
  }

  // ─── (일회성) 뒤에 붙은 잉여 칸 통합 정리 — 2026-07-20 GM 확정 ───
  //   GM: "등록매칭도 R 진행현황에 매핑하면 되는데 이것도 새로 만들고, 등록일은 유효회원 시트에 기록하면 되는데
  //        신규문의시트에 추가해놨네, 다른 항목값들도 다 지맘대로 추가해버렸네"
  //   ①유입경로(자동) 값 → '문의 경로(중분류)'로 이관(중분류가 빈 행에만 — 사람 입력 우선).
  //     ★칸 자체는 안 지운다: 구글폼 문항에 '유입경로(자동)'이 있어 지워도 다음 제출 때 되살아난다(문의 91%가 구글폼).
  //   ②잉여 칸 삭제 — 값이 있는 칸은 거부하고 보고만 한다(사람이 판단할 것).
  if (action === 'consolidate_cols_20260720') {
    if (String(body.key || '') !== 'wlp_consol_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var ccDry = (String(body.dryRun || '') === '1');
    var ccSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!ccSh) return _json({ ok: false, error: '시트 없음' });
    var ccHdr = ccSh.getRange(1, 1, 1, ccSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var ccLast = ccSh.getLastRow();
    var ccFind = function (want) { for (var i = 0; i < ccHdr.length; i++) { if (ccHdr[i].replace(/\s+/g, '') === want.replace(/\s+/g, '')) return i; } return -1; };
    var ccAuto = ccFind('유입경로(자동)');
    var ccMid  = -1;
    for (var cm = 0; cm < ccHdr.length; cm++) { if (ccHdr[cm].replace(/\s+/g, '').indexOf('문의경로(중분류)') === 0) { ccMid = cm; break; } }
    if (ccAuto < 0 || ccMid < 0) return _json({ ok: false, error: 'col-not-found', auto: ccAuto, mid: ccMid, headers: ccHdr });

    var ccAll = ccLast >= 2 ? ccSh.getRange(2, 1, ccLast - 1, ccHdr.length).getValues() : [];
    // ① 이관 대상 산출
    var ccMoves = [];
    for (var cr = 0; cr < ccAll.length; cr++) {
      var av = String(ccAll[cr][ccAuto] == null ? '' : ccAll[cr][ccAuto]).trim();
      var mv = String(ccAll[cr][ccMid]  == null ? '' : ccAll[cr][ccMid]).trim();
      if (av && !mv) ccMoves.push({ row: cr + 2, from: av });
    }
    // ② 삭제 후보 — 값 있으면 거부
    var ccCandidates = ['당일컨택', '등록매칭(자동)', '등록일(자동)', '방문완료일', '예약목록', '연락이력', '등록종목',
                        '문의 경로 (중분류)', '문의 경로 (소분류)', '유입경로(자동)'];   // 뒤 3개는 점검용(삭제 후보 아님 — 값 있으면 자동으로 유지된다)
    var ccReport = [];
    ccCandidates.forEach(function (nm) {
      var ix = ccFind(nm);
      if (ix < 0) { ccReport.push({ col: nm, status: 'absent' }); return; }
      var filled = 0, samples = [];
      for (var q = 0; q < ccAll.length; q++) {
        var v = String(ccAll[q][ix] == null ? '' : ccAll[q][ix]).trim();
        if (v) { filled++; if (samples.length < 3) samples.push({ row: q + 2, value: v.substring(0, 60) }); }
      }
      ccReport.push({ col: nm, idx: ix, filled: filled, samples: samples, deletable: filled === 0 });
    });

    if (ccDry) return _json({ ok: true, dryRun: true, colsBefore: ccHdr.length,
                              autoToMidMoves: ccMoves.length, moveSample: ccMoves.slice(0, 5),
                              report: ccReport, headers: ccHdr });

    // 실행 ① 값 이관
    ccMoves.forEach(function (m) { ccSh.getRange(m.row, ccMid + 1).setValue(m.from); });
    SpreadsheetApp.flush();
    // 실행 ② 값 0건인 칸만 삭제(뒤에서부터)
    var ccDel = ccReport.filter(function (r) { return r.deletable && r.idx !== undefined; }).sort(function (a, b) { return b.idx - a.idx; });
    var ccBlocked = [];
    ccDel.forEach(function (t) {
      if (_guardColDeleteByContent20260720_(ccSh, t.idx + 1, t.col)) { ccSh.deleteColumn(t.idx + 1); }
      else { ccBlocked.push(t.col); }
    });
    SpreadsheetApp.flush();
    var ccAfter = ccSh.getRange(1, 1, 1, ccSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, moved: ccMoves.length,
                   deleted: ccDel.map(function(t){ return t.col; }).filter(function(n){ return ccBlocked.indexOf(n) < 0; }),
                   blocked: ccBlocked,
                   kept: ccReport.filter(function(r){ return r.filled > 0; }).map(function(r){ return { col: r.col, filled: r.filled }; }),
                   colsBefore: ccHdr.length, colsAfter: ccAfter.length, headersAfter: ccAfter });
  }

  // ─── (일회성) 멤버십 시트 잉여 자동칸 정리 — 2026-07-22 GM 확정 ───
  //   GM: "등록매칭(자동)이랑 등록일(자동) 없애도 되지 않아? 차라리 등록일은 비고란에 '등록일: #날짜'로 기록"
  //   T 등록매칭(자동) → 삭제(리더 0 · 진행현황 P의 SUC/등록에서 파생) / U 등록일(자동) → 비고 S에 이관 후 삭제
  //   ★autostamp 트리거(memberMatchAutostamp)도 제거 — 안 지우면 다음 02:00에 두 칸 재생성(9234·9246).
  //   순서: ①U→비고 이관(멱등: 이미 '등록일:' 있으면 스킵) ②T·U 값 클리어 ③가드 통과 후 칸 삭제 ④트리거 제거.
  if (action === 'member_col_cleanup_20260722') {
    if (String(body.key || '') !== 'wlp_mcln_20260722') return _json({ ok: false, error: 'guard-mismatch' });
    var mcDry = (String(body.dryRun || '') === '1');
    var mcSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!mcSh) return _json({ ok: false, error: '시트 없음' });
    var mcHdr = mcSh.getRange(1, 1, 1, mcSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var mcNorm = function (s) { return String(s || '').replace(/\s+/g, ''); };
    var mcFind = function (want) { for (var i = 0; i < mcHdr.length; i++) { if (mcNorm(mcHdr[i]) === mcNorm(want)) return i; } return -1; };
    var iReg  = mcFind('등록매칭(자동)');
    var iDate = mcFind('등록일(자동)');
    var iMemo = mcFind('비고'); if (iMemo < 0) iMemo = mcFind('메모');
    if (iMemo < 0) return _json({ ok: false, error: 'no-memo-col', headers: mcHdr });
    var mcLast = mcSh.getLastRow();
    var mcAll = mcLast >= 2 ? mcSh.getRange(2, 1, mcLast - 1, mcHdr.length).getValues() : [];
    // 현재 autostamp 트리거 존재 여부
    var mcTrigCount = 0;
    try { ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'memberMatchAutostamp') mcTrigCount++; }); } catch (eT) {}

    // ① U 등록일 → 비고 이관 계획(멱등)
    var mcMoves = [];
    if (iDate >= 0) {
      for (var mr = 0; mr < mcAll.length; mr++) {
        var dv = mcAll[mr][iDate];
        var ds = (dv instanceof Date) ? Utilities.formatDate(dv, 'Asia/Seoul', 'yyyy-MM-dd')
               : String(dv == null ? '' : dv).trim();
        if (!ds) continue;
        var memo = String(mcAll[mr][iMemo] == null ? '' : mcAll[mr][iMemo]);
        if (memo.indexOf('등록일:') >= 0) continue;
        var tag = '등록일: ' + ds;
        mcMoves.push({ row: mr + 2, memo: (memo.trim() ? (memo.trim() + '\n' + tag) : tag), date: ds });
      }
    }

    if (mcDry) {
      return _json({ ok: true, dryRun: true,
                     cols: { 등록매칭: iReg, 등록일: iDate, 비고: iMemo },
                     dateToMemo: mcMoves.length, sample: mcMoves.slice(0, 3),
                     autostampTriggers: mcTrigCount,
                     willClearThenDelete: [iReg >= 0 ? '등록매칭(자동)' : null, iDate >= 0 ? '등록일(자동)' : null].filter(Boolean),
                     colsBefore: mcHdr.length, headers: mcHdr });
    }

    // 실행 ① 비고 이관
    mcMoves.forEach(function (m) { mcSh.getRange(m.row, iMemo + 1).setValue(m.memo); });
    SpreadsheetApp.flush();
    // 실행 ② 값 클리어(삭제 가드 통과 목적)
    if (iReg >= 0 && mcLast >= 2)  mcSh.getRange(2, iReg + 1,  mcLast - 1, 1).clearContent();
    if (iDate >= 0 && mcLast >= 2) mcSh.getRange(2, iDate + 1, mcLast - 1, 1).clearContent();
    SpreadsheetApp.flush();
    // 실행 ③ 칸 삭제(뒤 인덱스부터) — 위치 재조회
    var mcHdr2 = mcSh.getRange(1, 1, 1, mcSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var mcTargets = ['등록매칭(자동)', '등록일(자동)'].map(function (n) {
      for (var i = 0; i < mcHdr2.length; i++) { if (mcNorm(mcHdr2[i]) === mcNorm(n)) return { name: n, idx: i }; }
      return { name: n, idx: -1 };
    }).filter(function (t) { return t.idx >= 0; }).sort(function (a, b) { return b.idx - a.idx; });
    var mcDeleted = [], mcBlocked = [];
    mcTargets.forEach(function (t) {
      if (_guardColDeleteByContent20260720_(mcSh, t.idx + 1, t.name)) { mcSh.deleteColumn(t.idx + 1); mcDeleted.push(t.name); }
      else { mcBlocked.push(t.name); }
    });
    SpreadsheetApp.flush();
    // 실행 ④ autostamp 트리거 제거(칸 재생성 방지)
    var mcTrigRemoved = 0;
    try {
      ScriptApp.getProjectTriggers().forEach(function (t) {
        if (t.getHandlerFunction() === 'memberMatchAutostamp') { ScriptApp.deleteTrigger(t); mcTrigRemoved++; }
      });
    } catch (eTr) {}
    var mcAfter = mcSh.getRange(1, 1, 1, mcSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, dateMovedToMemo: mcMoves.length, deleted: mcDeleted, blocked: mcBlocked,
                   triggersRemoved: mcTrigRemoved,
                   colsBefore: mcHdr.length, colsAfter: mcAfter.length, headersAfter: mcAfter });
  }

  // ─── (일회성) 강습 '미등록 사유' 칸 옛 드롭다운 검증 제거 — 2026-07-22 GM(LOSS 사유 저장 불가 수리) ───
  //   원인: 이 칸에 옛 택소노미(스케줄X·거주지변경 등) VALUE_IN_RANGE 검증이 걸려, ERP 모달의 funnel 표준
  //   사유(가격·거리·시간대 등, 멤버십과 공유)를 넣으면 검증 위반으로 저장 거부. 검증만 제거(값·헤더 불변) →
  //   모달 표준 사유가 그대로 저장·표시된다. 멤버십 미등록사유엔 이 제약 없음(정합).
  if (action === 'clear_loss_validation_20260722') {
    if (String(body.key || '') !== 'wlp_lossval_20260722') return _json({ ok: false, error: 'guard-mismatch' });
    var clvOut = [];
    [111889422, 268994754].forEach(function (g) {
      try {
        var sh = _sheetByGid_(LESSON_SS_ID, g);
        if (!sh) { clvOut.push({ gid: g, error: 'no-sheet' }); return; }
        var hdr = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (h) { return String(h == null ? '' : h).trim(); });
        var clvNorm = function (s) { return String(s || '').replace(/\s+/g, ''); };
        var ci = -1;
        for (var i = 0; i < hdr.length; i++) { if (clvNorm(hdr[i]) === clvNorm('미등록 사유')) { ci = i; break; } }
        if (ci < 0) { clvOut.push({ gid: g, error: 'no-col' }); return; }
        var lr = sh.getLastRow();
        var before = sh.getRange(2, ci + 1).getDataValidation() ? true : false;
        if (lr >= 2) sh.getRange(2, ci + 1, lr - 1, 1).clearDataValidations();
        clvOut.push({ gid: g, colName: hdr[ci], colIdx: ci, hadRule: before, cleared: true, rows: Math.max(0, lr - 1) });
      } catch (e) { clvOut.push({ gid: g, error: String(e.message || e) }); }
    });
    return _json({ ok: true, sheets: clvOut });
  }

  // ─── (진단·읽기전용) 강습 시트 특정 칸의 데이터검증(드롭다운) 목록 조회 — LOSS사유 모달 정합용(2026-07-22) ───
  if (action === 'read_col_validation') {
    try {
      var rvColName = String(body.col || '미등록 사유');
      var rvGids = [111889422, 268994754];
      var rvOut = [];
      rvGids.forEach(function (g) {
        var sh = _sheetByGid_(LESSON_SS_ID, g);
        if (!sh) { rvOut.push({ gid: g, error: 'no-sheet' }); return; }
        var hdr = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (h) { return String(h == null ? '' : h).trim(); });
        var ci = -1, rvNorm = function (s) { return String(s || '').replace(/\s+/g, ''); };
        for (var i = 0; i < hdr.length; i++) { if (rvNorm(hdr[i]) === rvNorm(rvColName)) { ci = i; break; } }
        if (ci < 0) { rvOut.push({ gid: g, error: 'no-col', headers: hdr }); return; }
        var rule = sh.getRange(2, ci + 1).getDataValidation();
        var vals = null, vType = null, rngA1 = null;
        if (rule) {
          vType = String(rule.getCriteriaType());
          try {
            var args = rule.getCriteriaValues();
            var a0 = args && args[0];
            if (a0 && typeof a0.getValues === 'function') {        // VALUE_IN_RANGE → Range
              rngA1 = a0.getA1Notation();
              vals = a0.getValues().map(function (r) { return String(r[0] == null ? '' : r[0]).trim(); }).filter(function (x) { return x; });
            } else if (a0 && a0.length !== undefined) {            // VALUE_IN_LIST → array
              vals = a0;
            } else { vals = a0 != null ? String(a0) : null; }
          } catch (e) { vals = 'unreadable:' + e.message; }
        }
        rvOut.push({ gid: g, colName: hdr[ci], colIdx: ci, hasRule: !!rule, criteriaType: vType, rangeA1: rngA1, values: vals });
      });
      return _json({ ok: true, col: rvColName, sheets: rvOut });
    } catch (eRV) { return _json({ ok: false, error: String(eRV.message || eRV) }); }
  }

  // ─── (진단·읽기전용) 강습 스프레드시트 탭 목록 + 행수 — 시트 삭제 안전성 판단용(2026-07-22 GM) ───
  if (action === 'list_lesson_sheets') {
    try {
      var llSs = SpreadsheetApp.openById(LESSON_SS_ID);
      var llOut = llSs.getSheets().map(function (s) {
        var lr = s.getLastRow(), lc = s.getLastColumn(), filled = 0;
        if (lr >= 2 && lc >= 1) {
          var scanCols = Math.min(lc, 3);
          var vals = s.getRange(2, 1, lr - 1, scanCols).getValues();
          for (var i = 0; i < vals.length; i++) {
            var any = false;
            for (var j = 0; j < scanCols; j++) { if (String(vals[i][j] == null ? '' : vals[i][j]).trim()) { any = true; break; } }
            if (any) filled++;
          }
        }
        return { name: s.getName(), gid: s.getSheetId(), lastRow: lr, lastCol: lc, filledRows: filled, hidden: s.isSheetHidden() };
      });
      return _json({ ok: true, ssId: LESSON_SS_ID, sheetCount: llOut.length, sheets: llOut });
    } catch (eLL) { return _json({ ok: false, error: String(eLL.message || eLL) }); }
  }

  // ─── (일회성) 영문 유소년(2-1 WSC강습 영) 4건 → 메인 WSC강습 탭 이관 — 2026-07-22 GM("이관 후 시트 삭제") ───
  //   append만(행삭제·삽입 0, IMPORTRANGE 원본 무손상). 종목값=영문 원본 유지(화면 표시맵이 한글화). 유입언어=English(EN 배지 유지).
  //   보호자 정보는 비고에 합침. 이관 후 delete_lesson_sheet_20260722로 원탭 삭제(그때 EN 병합이 null→중복표시 해소).
  if (action === 'migrate_en_youth_to_main_20260722') {
    if (String(body.key || '') !== 'wlp_enmig_20260722') return _json({ ok: false, error: 'guard-mismatch' });
    var emDry = (String(body.dryRun || '') === '1');
    var emSrc = _sheetByGid_(LESSON_SS_ID, 931249179), emDst = _sheetByGid_(LESSON_SS_ID, 268994754);
    if (!emSrc || !emDst) return _json({ ok: false, error: '시트 없음', src: !!emSrc, dst: !!emDst });
    var emSh = emSrc.getRange(1, 1, 1, emSrc.getLastColumn()).getValues()[0];
    var emS = function (names) { return _findCol_(emSh, names); };
    var eiTs = emS(['타임스탬프']), eiName = emS(["Child's Full Name", '성함', '이름']), eiPhone = emS(["Guardian's Mobile Phone Number", 'Mobile Phone Number', '연락처']),
        eiAge = emS(["Child's Age", '나이', 'Age']), eiSport = emS(['WSC Program of Interest', 'WSC 강습 종목', '종목']), eiChan = emS(['How Did You Hear About Us?', '문의 경로', '경로']),
        eiGuard = emS(["Guardian's Full Name"]), eiRel = emS(["Guardian's Relationship to Child"]), eiReq = emS(['Additional Requests or Comments', '문의 사항']),
        eiOwner = emS(['지정 강사']), eiContact = emS(['Contact', '연락이력']), eiStat = emS(['진행 상황', '진행상황']), eiLoss = emS(['미등록 사유', 'LOSS사유']), eiMemo = emS(['비고']);
    var emSl = emSrc.getLastRow();
    var emData = emSl >= 2 ? emSrc.getRange(2, 1, emSl - 1, emSrc.getLastColumn()).getValues() : [];
    var emDh = emDst.getRange(1, 1, 1, emDst.getLastColumn()).getValues()[0];
    var emD = function (names) { return _findCol_(emDh, names); };
    var edTs = emD(['타임스탬프']), edName = emD(['유소년 이름', '성함', '이름']), edPhone = emD(['핸드폰 연락처', '연락처', '전화']), edAge = emD(['나이']),
        edSport = emD(['WSC 강습 종목', '종목']), edChan = emD(['문의 경로', '경로']), edNote = emD(['문의 사항', '기타']), edOwner = emD(['지정 강사']),
        edContact = emD(['Contact', '연락이력']), edStat = emD(['진행 상황', '진행상황', '상태']), edLoss = emD(['미등록 사유']), edMemo = emD(['비고']), edLang = emD(['유입언어', 'Language']);
    var emApp = [], emMig = [];
    for (var ei = 0; ei < emData.length; ei++) {
      var er = emData[ei];
      var enm = eiName >= 0 ? String(er[eiName] || '').trim() : '', eph = eiPhone >= 0 ? String(er[eiPhone] || '').trim() : '';
      if (!enm && !eph) continue;
      var nr = new Array(emDh.length).fill('');
      var eput = function (ci, v) { if (ci >= 0 && v !== undefined && v !== null && String(v) !== '') nr[ci] = v; };
      eput(edTs, eiTs >= 0 ? er[eiTs] : ''); eput(edName, enm); eput(edPhone, eph);
      eput(edAge, eiAge >= 0 ? er[eiAge] : ''); eput(edSport, eiSport >= 0 ? er[eiSport] : '');
      eput(edChan, eiChan >= 0 ? er[eiChan] : ''); eput(edNote, eiReq >= 0 ? er[eiReq] : '');
      eput(edOwner, eiOwner >= 0 ? er[eiOwner] : ''); eput(edContact, eiContact >= 0 ? er[eiContact] : '');
      eput(edStat, eiStat >= 0 ? er[eiStat] : ''); eput(edLoss, eiLoss >= 0 ? er[eiLoss] : '');
      eput(edLang, 'English');
      var eg = eiGuard >= 0 ? String(er[eiGuard] || '').trim() : '', erl = eiRel >= 0 ? String(er[eiRel] || '').trim() : '';
      var egt = eg ? ('보호자: ' + eg + (erl ? '(' + erl + ')' : '')) : '';
      var eom = eiMemo >= 0 ? String(er[eiMemo] || '').trim() : '';
      eput(edMemo, [egt, eom, '[영문폼 이관 2026-07-22]'].filter(Boolean).join(' / '));
      emApp.push(nr); emMig.push({ name: enm, phone: eph, sport: eiSport >= 0 ? String(er[eiSport] || '') : '' });
    }
    if (emDry) return _json({ ok: true, dryRun: true, count: emApp.length, migrated: emMig, dstCols: emDh.length, dstHeaders: emDh });
    if (emApp.length) {
      // 신규 append 행에만 데이터검증 제거 후 기록 — 영문 경로/종목값이 한글 드롭다운을 위반해 setValues가 거부되는 문제 회피.
      //   기존 행 검증은 불변(신규 행만 자유입력). 2026-07-22 시포.
      var emRange = emDst.getRange(emDst.getLastRow() + 1, 1, emApp.length, emDh.length);
      emRange.clearDataValidations();
      emRange.setValues(emApp);
      SpreadsheetApp.flush();
    }
    return _json({ ok: true, migrated: emMig.length, rows: emMig });
  }

  // ─── (진단/일회성) 칸 숨김·표시 토글 — 2026-07-22 GM(유입경로자동 칸 정리 검토) ───
  //   숨김=hideColumns / 표시=showColumns. gviz 숨김칸 제외 여부 실측 후 적용 판단용(되돌림 안전).
  if (action === 'set_col_hidden_20260722') {
    if (String(body.key || '') !== 'wlp_colhide_20260722') return _json({ ok: false, error: 'guard-mismatch' });
    var chSh = _sheetByGid_(String(body.ssId || LESSON_SS_ID), parseInt(body.gid, 10));
    if (!chSh) return _json({ ok: false, error: 'no-sheet' });
    var chHdr = chSh.getRange(1, 1, 1, chSh.getLastColumn()).getValues()[0];
    var chNorm = function (s) { return String(s || '').replace(/\s+/g, ''); };
    var chCi = -1;
    for (var chi = 0; chi < chHdr.length; chi++) { if (chNorm(chHdr[chi]) === chNorm(body.col)) { chCi = chi; break; } }
    if (chCi < 0) return _json({ ok: false, error: 'no-col', headers: chHdr });
    var chHidden = String(body.hidden || '') === '1';
    if (chHidden) chSh.hideColumns(chCi + 1); else chSh.showColumns(chCi + 1);
    SpreadsheetApp.flush();
    return _json({ ok: true, col: String(chHdr[chCi]), colIdx: chCi, hidden: chHidden });
  }

  // ─── (일회성) 강습 메인탭 고아 행 내용 클리어 — 2026-07-22 시포(이관 부분기록 정리) ───
  //   행 삭제 아님(IMPORTRANGE 원본 보존) · 내용만 비움 · 전화 대조키 필수(오삭제 방지, INC-020 교훈).
  if (action === 'clear_orphan_row_20260722') {
    if (String(body.key || '') !== 'wlp_clrrow_20260722') return _json({ ok: false, error: 'guard-mismatch' });
    var crGid = parseInt(body.gid, 10), crRow = parseInt(body.rowIndex, 10), crPhone = _normPhone_(body.expectPhone || '');
    if (!crRow || crRow < 2) return _json({ ok: false, error: 'bad-row' });
    var crSh = _sheetByGid_(LESSON_SS_ID, crGid);
    if (!crSh) return _json({ ok: false, error: 'no-sheet' });
    var crHdr = crSh.getRange(1, 1, 1, crSh.getLastColumn()).getValues()[0];
    var crPi = _findCol_(crHdr, ['연락처', '전화', '휴대폰', '핸드폰']);
    var crRowPhone = crPi >= 0 ? _normPhone_(crSh.getRange(crRow, crPi + 1).getValue()) : '';
    if (!crPhone) return _json({ ok: false, error: 'expectPhone-required', detail: '대조키(expectPhone) 필수 — 행번호만으로 클리어 금지(INC-020 방지)' });
    if (crRowPhone !== crPhone) return _json({ ok: false, error: 'phone-mismatch', rowPhone: crRowPhone, expect: crPhone });
    var crBackup = crSh.getRange(crRow, 1, 1, crSh.getLastColumn()).getValues()[0];
    if (String(body.dryRun || '') === '1') return _json({ ok: true, dryRun: true, rowPhone: crRowPhone, backup: crBackup });
    crSh.getRange(crRow, 1, 1, crSh.getLastColumn()).clearContent();
    return _json({ ok: true, cleared: crRow, rowPhone: crRowPhone, backup: crBackup });
  }

  // ─── (일회성) 강습 스프레드시트 잉여 탭 삭제 — 2026-07-22 GM("필요없는 시트는 삭제 검토, 문제없으면 삭제") ───
  //   안전장치 3중: ①보호목록(활성 소비 탭) 삭제 거부 ②구글폼 연결 탭은 force=1 없으면 거부(폼 파손 방지)
  //   ③삭제 전 전 행을 백업으로 반환(호출부가 파일 저장). dryRun 기본 미삭제.
  if (action === 'delete_lesson_sheet_20260722') {
    if (String(body.key || '') !== 'wlp_delsheet_20260722') return _json({ ok: false, error: 'guard-mismatch' });
    var dsGid = parseInt(body.gid, 10);
    var DS_PROTECTED = [111889422, 268994754, 1270425989, 537942806, 534686684, 1694057341, 1768753460];   // 311319200(1-1 성인영·0건)·931249179(2-1 WSC영·이관후)=GM 폐기 승인으로 보호 해제. 2026-07-22.
    // 2012342185('강습 신규문의')=보호 해제. 2026-07-27 GM 승인.
    //   이 탭은 자체폼 강습 접수를 받던 곳이었으나, 2026-07-18 GM 결정으로 자체폼 강습도 구글폼 응답탭에
    //   직접 쓰도록 통일됐다(위 intake_submit '강습 → 기존 구글폼 응답탭 저장으로 전환'). 그 뒤로 이 탭은
    //   아무것도 받지 않는다 — 실측 2026-07-27: 데이터 0행이고, 같은 날 자체폼 강습 접수(임규현 09:18)는
    //   '2. WSC 강습'(268994754)에서 발견됐다. 읽기 병합(_lessonReadRowsMerged_)은 탭이 없으면 조용히 건너뛴다.
    if (DS_PROTECTED.indexOf(dsGid) >= 0) return _json({ ok: false, error: 'protected-sheet', gid: dsGid, detail: '활성 소비 탭 — 삭제 금지' });
    var dsSs = SpreadsheetApp.openById(LESSON_SS_ID);
    var dsSh = null;
    dsSs.getSheets().forEach(function (s) { if (s.getSheetId() === dsGid) dsSh = s; });
    if (!dsSh) return _json({ ok: false, error: 'sheet-not-found', gid: dsGid });
    var dsName = dsSh.getName(), dsLr = dsSh.getLastRow(), dsLc = dsSh.getLastColumn();
    var dsBackup = (dsLr >= 1 && dsLc >= 1) ? dsSh.getRange(1, 1, dsLr, dsLc).getValues() : [];
    var dsFormUrl = '';
    try { dsFormUrl = dsSh.getFormUrl() || ''; } catch (e) {}
    if (dsFormUrl && String(body.force || '') !== '1') return _json({ ok: false, error: 'form-attached', detail: '구글폼 연결됨 — 삭제하려면 force=1 (폼 파손 주의)', formUrl: dsFormUrl, name: dsName, rows: dsLr });
    if (String(body.dryRun || '') === '1') return _json({ ok: true, dryRun: true, name: dsName, gid: dsGid, rows: dsLr, cols: dsLc, formUrl: dsFormUrl, backup: dsBackup });
    // force로 폼 연결 탭을 지울 땐: ①응답접수 중단(고아 제출 방지) ②폼-시트 연결 해제(removeDestination) —
    //   구글은 폼 연결된 응답탭 삭제를 막으므로 연결 해제가 선행 필수. GM '폐기' 지시. 2026-07-22.
    var dsFormClosed = false, dsFormUnlinked = false;
    if (dsFormUrl && String(body.force || '') === '1') {
      try {
        var dsForm = FormApp.openByUrl(dsFormUrl);
        try { dsForm.setAcceptingResponses(false); dsFormClosed = true; } catch (eC) {}
        dsForm.removeDestination(); dsFormUnlinked = true;
        SpreadsheetApp.flush();
      } catch (eF) { return _json({ ok: false, error: 'form-unlink-fail', detail: String(eF.message || eF), formUrl: dsFormUrl, formClosed: dsFormClosed }); }
    }
    dsSs.deleteSheet(dsSh);
    return _json({ ok: true, deleted: dsName, gid: dsGid, rows: dsLr, formUrl: dsFormUrl, formClosed: dsFormClosed, formUnlinked: dsFormUnlinked, backup: dsBackup });
  }

  // ─── (일회성) 거주지 항목 전면 폐기 — 2026-07-20 GM 확정 ("자체폼이랑 구글폼 구글시트 다 삭제하자") ───
  //   근거: 구글폼이 4,759건 받는 동안 계속 수집했으나 ERP 어디에서도 읽지 않는다(Survey.js 0곳·회원관리 화면 0곳).
  //   즉 고객은 채우는데 아무도 안 보는 칸이었다.
  //   ★순서 고정: 폼 문항 삭제 → 그 다음 시트 칸 삭제. 반대로 하면 다음 제출 때 폼이 칸을 되살린다.
  //   삭제 전 값 전량을 응답에 담아 반환한다(되돌릴 유일한 근거 — 호출부가 파일로 저장한다).
  if (action === 'del_residence_20260720') {
    if (String(body.key || '') !== 'wlp_delres_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var drDry = (String(body.dryRun || '') === '1');
    var drSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!drSh) return _json({ ok: false, error: '시트 없음' });
    var drHdr = drSh.getRange(1, 1, 1, drSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var drIdx = -1;
    for (var dri = 0; dri < drHdr.length; dri++) { if (drHdr[dri].indexOf('거주지') === 0) { drIdx = dri; break; } }
    if (drIdx < 0) return _json({ ok: false, error: 'no-target', detail: '거주지로 시작하는 칸 없음(이미 삭제됐을 수 있음)', headers: drHdr });

    // 값 전량 백업 — 성함·연락처와 함께 담아야 나중에 어느 고객 것인지 알 수 있다
    var drNameI = drHdr.indexOf('1. 성함'), drPhoneI = drHdr.indexOf('2. 연락처');
    var drLast = drSh.getLastRow(), drBackup = [], drFilled = 0;
    if (drLast >= 2) {
      var drAll = drSh.getRange(2, 1, drLast - 1, drHdr.length).getValues();
      for (var drr = 0; drr < drAll.length; drr++) {
        var drV = String(drAll[drr][drIdx] == null ? '' : drAll[drr][drIdx]).trim();
        if (!drV) continue;
        drFilled++;
        drBackup.push({ row: drr + 2,
                        name: drNameI >= 0 ? String(drAll[drr][drNameI] || '') : '',
                        phone: drPhoneI >= 0 ? String(drAll[drr][drPhoneI] || '') : '',
                        residence: drV });
      }
    }

    // 폼 문항 확인
    var drFormUrl = '', drFormItem = null, drFormTitle = '';
    try {
      drFormUrl = drSh.getFormUrl() || '';
      if (drFormUrl) {
        var drForm = FormApp.openByUrl(drFormUrl);
        var drItems = drForm.getItems();
        for (var dfi = 0; dfi < drItems.length; dfi++) {
          if (String(drItems[dfi].getTitle() || '').indexOf('거주지') >= 0) { drFormItem = drItems[dfi]; drFormTitle = drItems[dfi].getTitle(); break; }
        }
      }
    } catch (eF) { return _json({ ok: false, error: 'form_open_fail', detail: String(eF.message || eF) }); }

    if (drDry) {
      // 값 분포 — 지울 가치가 있는 데이터인지 사람이 판단할 근거
      var drDist = {};
      drBackup.forEach(function (b) { drDist[b.residence] = (drDist[b.residence] || 0) + 1; });
      var drDistArr = Object.keys(drDist).map(function (k) { return { value: k, count: drDist[k] }; })
                        .sort(function (a, b) { return b.count - a.count; });
      // 폼 문항 목록도 같이 — '거주지'가 없다면 어떤 문항들이 있는지 확인용
      var drFormTitles = [];
      try { if (drFormUrl) FormApp.openByUrl(drFormUrl).getItems().forEach(function (it) { drFormTitles.push(String(it.getTitle() || '').substring(0, 40)); }); } catch (e2) {}
      return _json({ ok: true, dryRun: true, colIdx: drIdx, colHeader: drHdr[drIdx],
                     colsBefore: drHdr.length, rowsWithValue: drFilled, totalRows: drLast - 1,
                     formUrl: drFormUrl ? '있음' : '없음', formItemFound: !!drFormItem, formItemTitle: drFormTitle,
                     formTitles: drFormTitles, distribution: drDistArr,
                     sample: drBackup.slice(0, 5) });
    }

    // ① 폼 문항 삭제 먼저
    var drFormDeleted = false;
    if (drFormItem) { try { FormApp.openByUrl(drFormUrl).deleteItem(drFormItem); drFormDeleted = true; } catch (eD) { return _json({ ok: false, error: 'form_item_delete_fail', detail: String(eD.message || eD) }); } }
    // ② 그 다음 시트 칸 삭제 (헤더 재확인 — 폼 편집 사이 위치가 바뀌었을 수 있다)
    var drHdr2 = drSh.getRange(1, 1, 1, drSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    var drIdx2 = -1;
    for (var dj = 0; dj < drHdr2.length; dj++) { if (drHdr2[dj].indexOf('거주지') === 0) { drIdx2 = dj; break; } }
    if (drIdx2 < 0) return _json({ ok: true, formDeleted: drFormDeleted, colDeleted: false, note: '폼 삭제 후 칸이 이미 없음', backup: drBackup });
    drSh.deleteColumn(drIdx2 + 1);
    SpreadsheetApp.flush();
    var drAfter = drSh.getRange(1, 1, 1, drSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, formDeleted: drFormDeleted, formItemTitle: drFormTitle, colDeleted: true,
                   colsBefore: drHdr.length, colsAfter: drAfter.length,
                   backedUpRows: drBackup.length, backup: drBackup, headersAfter: drAfter });
  }

  // ─── (일회성) 07-18에 잘못 신설한 LOSS사유·LOSS사유메모 칸 제거 — 2026-07-20 GM 확정 ───
  //   같은 뜻의 '미등록 사유' 칸이 원래 있었는데 새 칸을 만든 것이 착오였다. 메모는 아예 불필요(GM).
  //   실측 두 칸 모두 데이터 0건 — 옮길 값이 없다. 값이 하나라도 있으면 삭제를 거부한다(안전장치).
  //   '미등록 사유' 칸 존재도 확인한 뒤에만 지운다(사유 기록처가 전멸하는 것 방지).
  if (action === 'del_loss_cols_20260720') {
    if (String(body.key || '') !== 'wlp_delloss_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var dlDry = (String(body.dryRun || '') === '1');
    var dlSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!dlSh) return _json({ ok: false, error: '시트 없음' });
    var dlHdr = dlSh.getRange(1, 1, 1, dlSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    if (dlHdr.indexOf('미등록 사유') < 0 && dlHdr.indexOf('미등록사유') < 0) {
      return _json({ ok: false, error: 'no-fallback-col', detail: "'미등록 사유' 칸이 없어 삭제 거부 — 사유 기록처가 없어진다", headers: dlHdr });
    }
    var dlLast = dlSh.getLastRow();
    var dlReport = [];
    ['LOSS사유', 'LOSS사유메모'].forEach(function (nm) {
      var ix = dlHdr.indexOf(nm);   // 정확일치만
      if (ix < 0) { dlReport.push({ col: nm, status: 'absent' }); return; }
      var filled = 0, samples = [];
      if (dlLast >= 2) {
        var vals = dlSh.getRange(2, ix + 1, dlLast - 1, 1).getValues();
        for (var vi = 0; vi < vals.length; vi++) {
          var v = String(vals[vi][0] == null ? '' : vals[vi][0]).trim();
          if (v) { filled++; if (samples.length < 5) samples.push({ row: vi + 2, value: v }); }
        }
      }
      dlReport.push({ col: nm, idx: ix, filled: filled, samples: samples });
    });
    var dlBlocked = dlReport.filter(function (r) { return r.filled > 0; });
    if (dlBlocked.length) return _json({ ok: false, error: 'has-data', detail: '값이 있는 칸은 지우지 않는다', blocked: dlBlocked });
    if (dlDry) return _json({ ok: true, dryRun: true, colsBefore: dlHdr.length, report: dlReport, headers: dlHdr });
    // 실행 — 인덱스가 큰 칸부터 지워야 앞 칸 삭제로 위치가 밀리지 않는다
    var dlTargets = dlReport.filter(function (r) { return r.idx !== undefined; }).sort(function (a, b) { return b.idx - a.idx; });
    dlTargets.forEach(function (t) { dlSh.deleteColumn(t.idx + 1); });
    SpreadsheetApp.flush();
    var dlAfter = dlSh.getRange(1, 1, 1, dlSh.getLastColumn()).getValues()[0].map(function(h){ return String(h == null ? '' : h).trim(); });
    return _json({ ok: true, deleted: dlTargets.map(function(t){ return t.col; }),
                   colsBefore: dlHdr.length, colsAfter: dlAfter.length, headersAfter: dlAfter });
  }

  if (action === 'delete_date_col_20260720') {
    if (String(body.key || '') !== 'wlp_delcol_date_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var dcDry = (String(body.dryRun || '') === '1');
    var dcSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!dcSh) return _json({ ok: false, error: '시트 없음' });
    var dcHdr = dcSh.getRange(1, 1, 1, dcSh.getLastColumn()).getValues()[0];
    var dcIdx = -1;
    for (var dci = 0; dci < dcHdr.length; dci++) {
      if (String(dcHdr[dci] == null ? '' : dcHdr[dci]).trim() === '날짜') { dcIdx = dci; break; }  // 정확일치만
    }
    if (dcIdx < 0) return _json({ ok: false, error: 'no-target', detail: "'날짜' 정확일치 칸 없음(이미 삭제됐을 수 있음)", headers: dcHdr });
    if (dcIdx !== 0) return _json({ ok: false, error: 'unexpected-position', detail: 'A열이 아님 idx=' + dcIdx, headers: dcHdr });
    var dcTsIdx = -1;
    for (var dct = 0; dct < dcHdr.length; dct++) {
      if (String(dcHdr[dct] == null ? '' : dcHdr[dct]).trim() === '타임스탬프') { dcTsIdx = dct; break; }
    }
    if (dcTsIdx < 0) return _json({ ok: false, error: 'no-timestamp-col', detail: '타임스탬프 칸이 없어 삭제 거부(날짜 정보 전멸 방지)' });
    var dcLast = dcSh.getLastRow();
    var dcSample = [];
    if (dcLast >= 2) {
      var dcN = Math.min(5, dcLast - 1);
      var dcVals = dcSh.getRange(2, 1, dcN, Math.max(2, dcTsIdx + 1)).getValues();
      for (var dcs = 0; dcs < dcVals.length; dcs++) {
        dcSample.push({ '날짜': String(dcVals[dcs][dcIdx] || ''), '타임스탬프': String(dcVals[dcs][dcTsIdx] || '') });
      }
    }
    var dcBefore = dcHdr.map(function(h){ return String(h == null ? '' : h).substring(0, 24); });
    if (dcDry) {
      return _json({ ok: true, dryRun: true, targetIdx: dcIdx, targetHeader: '날짜', tsIdx: dcTsIdx,
                     colsBefore: dcHdr.length, colsAfterExpected: dcHdr.length - 1,
                     rows: dcLast - 1, sample: dcSample, headersBefore: dcBefore });
    }
    dcSh.deleteColumn(dcIdx + 1);
    SpreadsheetApp.flush();
    var dcHdr2 = dcSh.getRange(1, 1, 1, dcSh.getLastColumn()).getValues()[0];
    return _json({ ok: true, dryRun: false, deleted: '날짜',
                   colsBefore: dcHdr.length, colsAfter: dcHdr2.length,
                   newFirstHeader: String(dcHdr2[0] || ''),
                   headersAfter: dcHdr2.map(function(h){ return String(h == null ? '' : h).substring(0, 24); }) });
  }

  // ─── (진단·읽기전용) 레거시 구글폼 실태 확인 — 2026-07-20 시포 ───
  //   목적: '옛 구글폼이 아직 살아서 응답을 받고 있나'를 추측이 아니라 실측으로 판정.
  //   지금 문의 유입 정본은 자체폼(intake_submit → SpreadsheetApp 직접 write)이라는 GM 확인이 있고,
  //   구글폼은 레거시 껍데기로 추정된다. 그 추정을 숫자로 검증한다.
  //   ★ 아무것도 쓰지 않는다 — getFormUrl/getResponses/getItems 전부 읽기. 폼 변형·연결해제 없음.
  if (action === 'diag_form_link_20260720') {
    if (String(body.key || '') !== 'wlp_diag_form_20260720') return _json({ ok: false, error: 'guard-mismatch' });
    var dfOut = { sheets: [], triggers: [], form: null };
    try {
      var dfSs = SpreadsheetApp.openById(FORM_SHEETS[0].ssId);
      // ① 스프레드시트 내 전 탭의 폼 연결 여부 — 어느 탭이 진짜 폼 응답탭인지 확정
      dfSs.getSheets().forEach(function(s) {
        var fu = null, err = null;
        try { fu = s.getFormUrl(); } catch (e) { err = String(e); }
        dfOut.sheets.push({ name: s.getName(), gid: s.getSheetId(), rows: s.getLastRow(),
                            cols: s.getLastColumn(), formUrl: fu || null, error: err });
      });
    } catch (e) { return _json({ ok: false, error: 'openById 실패', detail: String(e) }); }
    // ② 설치된 onFormSubmit 트리거 실태
    try {
      ScriptApp.getProjectTriggers().forEach(function(t) {
        var h = t.getHandlerFunction();
        if (h === 'onInquiryFormSubmit' || String(t.getEventType()) === 'ON_FORM_SUBMIT') {
          dfOut.triggers.push({ handler: h, eventType: String(t.getEventType()),
                                sourceId: (t.getTriggerSourceId ? t.getTriggerSourceId() : null) });
        }
      });
    } catch (e) { dfOut.triggers.push({ error: String(e) }); }
    // ③ 대상 탭에 붙은 폼의 생사 판정 — 응답 수 · 마지막 응답 시각 · 수신 여부 · 문항 목록
    var dfTarget = null;
    dfOut.sheets.forEach(function(s) { if (s.gid === FORM_SHEETS[0].gid) dfTarget = s; });
    if (dfTarget && dfTarget.formUrl) {
      try {
        var dfForm = FormApp.openByUrl(dfTarget.formUrl);
        var dfResp = dfForm.getResponses();
        var dfLast = dfResp.length ? dfResp[dfResp.length - 1].getTimestamp() : null;
        var dfItems = dfForm.getItems().map(function(it) {
          return { title: it.getTitle(), type: String(it.getType()) };
        });
        dfOut.form = {
          id: dfForm.getId(), title: dfForm.getTitle(),
          acceptingResponses: dfForm.isAcceptingResponses(),
          publishedUrl: (function(){ try { return dfForm.getPublishedUrl(); } catch (e) { return null; } })(),
          responseCount: dfResp.length,
          lastResponseAt: dfLast ? Utilities.formatDate(dfLast, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : null,
          firstResponseAt: dfResp.length ? Utilities.formatDate(dfResp[0].getTimestamp(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : null,
          itemCount: dfItems.length, items: dfItems
        };
        // ④ 폼 문항 ↔ 시트 헤더 대응 — 어떤 칸이 '폼 소유'인지 확정(삭제 안전성 판정의 핵심)
        var dfSh = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
        var dfHdr = dfSh.getRange(1, 1, 1, dfSh.getLastColumn()).getValues()[0];
        dfOut.form.headerMap = dfHdr.map(function(h, i) {
          var hn = String(h || '').replace(/\s/g, '');
          var owned = dfItems.some(function(it) {
            var tn = String(it.title || '').replace(/\s/g, '');
            return tn && (hn === tn || hn.indexOf(tn) >= 0 || tn.indexOf(hn) >= 0);
          });
          return { idx: i, header: String(h || '').substring(0, 40), formOwned: owned };
        });
      } catch (e) { dfOut.form = { error: 'FormApp 접근 실패', detail: String(e), formUrl: dfTarget.formUrl }; }
    }
    return _json({ ok: true, readOnly: true, result: dfOut });
  }

  // ─── (일회성) 문의 채널값 정리 3건 — 2026-07-20 시포(리드 승인 범위) ───
  //   승인 범위: ① 중분류 빈칸 반영 2건 ② '유입경로(자동)'에 직원명이 들어간 오염 1건을 비고로 이관.
  //   ★ 칸 구조는 절대 건드리지 않는다 — §1-A(유입경로 병합·삭제)·§1-B(날짜 삭제)는 GM 결정 대기 중.
  //   ★ 대조키 = 성함 + 연락처(숫자정규화) 둘 다 일치. rowIndex 미사용 —
  //     INC-020(행번호로 지웠다가 실고객 2명 오삭제) 재발방지. 매칭이 정확히 1건이 아니면 그 건은 건너뛴다(추측 금지).
  //   멱등: 목표값이 이미 들어있으면 skip. dryRun=1이면 한 글자도 쓰지 않고 매칭·예정변경만 반환.
  if (action === 'fix_inquiry_channel_20260720') {
    var _FIC_GUARD = 'wlp_fix_ch_20260720';
    if (String(body.key || '') !== _FIC_GUARD) return _json({ ok: false, error: 'guard-mismatch' });
    var ficDry = (String(body.dryRun || '') === '1');
    var ficSh  = _sheetByGid_(FORM_SHEETS[0].ssId, FORM_SHEETS[0].gid);
    if (!ficSh) return _json({ ok: false, error: '시트 없음' });
    var ficHdr  = ficSh.getRange(1, 1, 1, ficSh.getLastColumn()).getValues()[0];
    var ciName  = _findCol_(ficHdr, ['성함', '이름']);
    var ciPhone = _findCol_(ficHdr, ['연락처', '전화', '휴대폰']);
    var ciMid   = _findCol_(ficHdr, ['중분류']);
    var ciAuto  = _findCol_(ficHdr, ['유입경로(자동)', '유입경로자동', '유입경로_자동']);
    var ciMemo  = _findCol_(ficHdr, ['비고', '메모']);
    if (ciName < 0 || ciPhone < 0) return _json({ ok: false, error: '성함/연락처 칸 탐색 실패' });
    // 칸 위치를 응답에 실어 호출부가 눈으로 검증할 수 있게 한다(엉뚱한 칸에 쓰는 사고 조기 발견).
    var ficCols = { 성함: ciName, 연락처: ciPhone, 중분류: ciMid, '유입경로(자동)': ciAuto, 비고: ciMemo,
                    헤더확인: { 중분류: ciMid >= 0 ? ficHdr[ciMid] : null, 비고: ciMemo >= 0 ? ficHdr[ciMemo] : null } };
    var ficTargets = [
      { 용도: '중분류반영',   성함: '조아람', 연락처: '010-8923-0810', 중분류: '네이버 블로그' },
      { 용도: '중분류반영',   성함: '익명여', 연락처: '010-9265-5742', 중분류: '네이버 검색·플레이스' },
      { 용도: '오염_비고이관', 성함: '여',   연락처: '010-3929-5258', 자동값비우기: true }
    ];
    var ficLast = ficSh.getLastRow();
    var ficAll  = ficSh.getRange(2, 1, ficLast - 1, ficHdr.length).getValues();
    var ficOut = [], ficApplied = 0, ficSkipped = 0, ficErr = 0;
    ficTargets.forEach(function(t) {
      var keyPh = _normPhone_(t.연락처), keyNm = String(t.성함).trim();
      var hits = [];
      for (var i = 0; i < ficAll.length; i++) {
        if (_normPhone_(ficAll[i][ciPhone]) === keyPh && String(ficAll[i][ciName] || '').trim() === keyNm) {
          hits.push(i + 2); // 물리 행(참고용) — 매칭 결과일 뿐 입력키가 아니다
        }
      }
      if (hits.length !== 1) {
        ficErr++;
        ficOut.push({ 용도: t.용도, 대조키: t.성함 + '/' + t.연락처, 결과: '건너뜀', 사유: '매칭 ' + hits.length + '건(1건이어야 함)' });
        return;
      }
      var row = hits[0], r = ficAll[row - 2];
      var before = { 중분류: ciMid >= 0 ? String(r[ciMid] || '') : null,
                     '유입경로(자동)': ciAuto >= 0 ? String(r[ciAuto] || '') : null,
                     비고: ciMemo >= 0 ? String(r[ciMemo] || '') : null };
      var plan = [];
      if (t.중분류) {
        if (ciMid < 0) { ficErr++; ficOut.push({ 용도: t.용도, 대조키: t.성함, 결과: '건너뜀', 사유: '중분류 칸 없음' }); return; }
        if (String(before.중분류).trim()) plan.push({ 칸: '중분류', 결과: 'skip(이미 값 있음)' });
        else plan.push({ 칸: '중분류', 전: before.중분류, 후: t.중분류, 열: ciMid + 1 });
      }
      if (t.자동값비우기) {
        if (ciAuto < 0 || ciMemo < 0) { ficErr++; ficOut.push({ 용도: t.용도, 대조키: t.성함, 결과: '건너뜀', 사유: '유입경로(자동)/비고 칸 없음' }); return; }
        var moved = String(before['유입경로(자동)'] || '').trim();
        if (!moved) plan.push({ 칸: '유입경로(자동)', 결과: 'skip(이미 비어있음)' });
        else if (String(before.비고).trim()) plan.push({ 칸: '비고', 결과: 'skip(비고에 기존값 있어 덮지 않음)', 기존: before.비고 });
        else {
          plan.push({ 칸: '비고', 전: before.비고, 후: moved + ' (유입경로(자동)에서 이관 2026-07-20)', 열: ciMemo + 1 });
          plan.push({ 칸: '유입경로(자동)', 전: moved, 후: '', 열: ciAuto + 1 });
        }
      }
      if (!ficDry) {
        plan.forEach(function(p) { if (p.열) ficSh.getRange(row, p.열).setValue(p.후); });
      }
      var did = plan.filter(function(p) { return !!p.열; }).length;
      if (did) ficApplied++; else ficSkipped++;
      ficOut.push({ 용도: t.용도, 대조키: t.성함 + '/' + t.연락처, 매칭행_참고: row, 결과: did ? (ficDry ? '적용예정' : '적용') : 'skip', 변경: plan });
    });
    return _json({ ok: true, dryRun: ficDry, 칸위치: ficCols, 총행수: ficAll.length,
                   요약: { 적용: ficApplied, skip: ficSkipped, 오류: ficErr }, 상세: ficOut });
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

  // ─── (일회성 진단·읽기전용) DATA 탭 canEditByMe:false 원인 규명 — 실행계정 vs 파일소유자 vs 보호편집자 ───
  //   naver_split_midcat 진단은 '중분류' 헤더 탐색에 의존해 무관한 동시작업(컬럼 개칭)에 깨지기 쉬움 →
  //   DATA 시트를 이름으로 직접 열어 독립적으로 확인. 2026-07-20 GM 지시(원인 규명).
  if (action === 'diag_exec_identity_20260720') {
    try {
      var deiOut = { effectiveUser: '', activeUser: '', fileOwner: '', dataSheetProtections: [] };
      try { deiOut.effectiveUser = Session.getEffectiveUser().getEmail(); } catch (e1) { deiOut.effectiveUser = 'ERR:' + String(e1); }
      try { deiOut.activeUser = Session.getActiveUser().getEmail(); } catch (e2) { deiOut.activeUser = 'ERR:' + String(e2); }
      try { deiOut.fileOwner = DriveApp.getFileById(MEMBER_SPREADSHEET_ID).getOwner().getEmail(); } catch (e3) { deiOut.fileOwner = 'ERR:' + String(e3); }
      var deiSs = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
      var deiDataSheet = deiSs.getSheetByName('DATA');
      if (deiDataSheet) {
        var deiSheetProts = deiDataSheet.getProtections(SpreadsheetApp.ProtectionType.SHEET);
        for (var dsp = 0; dsp < deiSheetProts.length; dsp++) {
          var sp2 = deiSheetProts[dsp];
          var ed2 = [];
          try { ed2 = sp2.getEditors().map(function (u) { return u.getEmail(); }); } catch (ee1) {}
          deiOut.dataSheetProtections.push({ type: 'SHEET', desc: sp2.getDescription(), editors: ed2, canEditByMe: sp2.canEdit() });
        }
        var deiRangeProts = deiDataSheet.getProtections(SpreadsheetApp.ProtectionType.RANGE);
        for (var drp = 0; drp < deiRangeProts.length; drp++) {
          var rp2 = deiRangeProts[drp];
          var ed3 = [];
          try { ed3 = rp2.getEditors().map(function (u) { return u.getEmail(); }); } catch (ee2) {}
          deiOut.dataSheetProtections.push({ type: 'RANGE', a1: rp2.getRange().getA1Notation(), desc: rp2.getDescription(), editors: ed3, canEditByMe: rp2.canEdit() });
        }
      } else {
        deiOut.dataSheetError = 'DATA 시트 없음';
      }
      return _json({ ok: true, result: deiOut });
    } catch (e) {
      return _json({ ok: false, error: String(e) });
    }
  }

  // ─── 네이버 중분류 'N-플레이스(검색)' 분리 (2026-07-20 GM 승인·배9351) ───
  //   문의 경로(중분류) 드롭다운의 'N-플레이스(검색)' 단일값을 'N-플레이스'·'N-검색' 두 값으로 분리.
  //   기존 셀 데이터는 절대 미변경(과거 197건은 그대로 'N-플레이스(검색)'로 남음) — 드롭다운 "목록"만 갱신.
  //   mode=diag(기본, 읽기전용): Data Validation 목록·바인딩폼 여부 진단만. mode=apply(가드 필수): 실제 목록 교체.
  //   ★ 가드 필수 — 시트 데이터 검증 규칙을 실제 변형하므로 _SURVEY_PUBLIC_ACTIONS 화이트리스트에 절대 넣지 않는다.
  if (action === 'naver_split_midcat') {
    var nsmMode = String(body.mode || 'diag');
    var nsmGid = 1902010032; // '26년 신규문의' 스태프 로그(멤버십)
    var nsmOld = 'N-플레이스(검색)';
    var nsmNewA = 'N-플레이스';
    var nsmNewB = 'N-검색';
    try {
      var nsmSs = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
      var nsmSheet = _sheetByGid_(MEMBER_SPREADSHEET_ID, nsmGid);
      if (!nsmSheet) return _json({ ok: false, error: 'sheet-not-found', gid: nsmGid });
      var nsmLastCol = nsmSheet.getLastColumn();
      var nsmHeaders = nsmSheet.getRange(1, 1, 1, nsmLastCol).getValues()[0];
      var nsmColIdx = -1;
      for (var nhi = 0; nhi < nsmHeaders.length; nhi++) {
        if (String(nsmHeaders[nhi] || '').indexOf('중분류') >= 0) { nsmColIdx = nhi; break; }
      }
      if (nsmColIdx < 0) return _json({ ok: false, error: 'column-not-found', headers: nsmHeaders });
      var nsmBoundForm = '';
      try { nsmBoundForm = nsmSs.getFormUrl() || ''; } catch (efu) {}
      // 검증규칙은 보통 열 전체에 동일 적용되지만 혹시 몰라 샘플 행 여러 개를 훑어 첫 규칙을 채택(전체 getDataValidations는 대형시트에서 느림).
      var nsmLastRow = nsmSheet.getLastRow();
      var nsmDv = null;
      if (nsmLastRow >= 2) {
        var nsmMidRow = Math.floor((2 + nsmLastRow) / 2);
        var nsmSampleRows = [2, 3, nsmMidRow, nsmLastRow].filter(function (rr, idx, arr) { return rr >= 2 && rr <= nsmLastRow && arr.indexOf(rr) === idx; });
        for (var nsr = 0; nsr < nsmSampleRows.length; nsr++) {
          var rule = nsmSheet.getRange(nsmSampleRows[nsr], nsmColIdx + 1).getDataValidation();
          if (rule) { nsmDv = rule; break; }
        }
      }
      var nsmOldValueCellCount = 0;
      if (nsmLastRow >= 2) {
        var nsmVals = nsmSheet.getRange(2, nsmColIdx + 1, nsmLastRow - 1, 1).getValues();
        for (var nvr = 0; nvr < nsmVals.length; nvr++) {
          if (String(nsmVals[nvr][0] || '').trim() === nsmOld) nsmOldValueCellCount++;
        }
      }
      var nsmCritType = nsmDv ? String(nsmDv.getCriteriaType()) : null;
      var nsmRangeInfo = null;
      var nsmSrcRange = null;
      if (nsmDv && nsmCritType === 'VALUE_IN_RANGE') {
        try {
          nsmSrcRange = nsmDv.getCriteriaValues()[0]; // Range 객체(옵션 목록이 실제 저장된 참조 범위)
          var nsmRangeVals = nsmSrcRange.getValues();
          var nsmFlatVals = [];
          for (var rvi = 0; rvi < nsmRangeVals.length; rvi++) {
            nsmFlatVals.push(String(nsmRangeVals[rvi][0] || ''));
          }
          nsmRangeInfo = {
            sheetName: nsmSrcRange.getSheet().getName(),
            a1: nsmSrcRange.getA1Notation(),
            row: nsmSrcRange.getRow(),
            col: nsmSrcRange.getColumn(),
            numRows: nsmSrcRange.getNumRows(),
            values: nsmFlatVals
          };
          // 보호된 범위/시트 진단 — 'apply' 시도가 "보호된 셀" 예외로 막혔을 때 원인 파악용.
          try {
            var nsmProtInfo = [];
            var nsmSheetProts = nsmSrcRange.getSheet().getProtections(SpreadsheetApp.ProtectionType.SHEET);
            for (var pspi = 0; pspi < nsmSheetProts.length; pspi++) {
              var spp = nsmSheetProts[pspi];
              var sppEditors = [];
              try { sppEditors = spp.getEditors().map(function(u){return u.getEmail();}); } catch (ee1) {}
              nsmProtInfo.push({ type: 'SHEET', desc: spp.getDescription(), editors: sppEditors, canEditByMe: spp.canEdit() });
            }
            var nsmRangeProts = nsmSrcRange.getSheet().getProtections(SpreadsheetApp.ProtectionType.RANGE);
            for (var prpi = 0; prpi < nsmRangeProts.length; prpi++) {
              var rpp = nsmRangeProts[prpi];
              var rppEditors = [];
              try { rppEditors = rpp.getEditors().map(function(u){return u.getEmail();}); } catch (ee2) {}
              nsmProtInfo.push({ type: 'RANGE', a1: rpp.getRange().getA1Notation(), desc: rpp.getDescription(), editors: rppEditors, canEditByMe: rpp.canEdit() });
            }
            nsmRangeInfo.protections = nsmProtInfo;
          } catch (eprot) { nsmRangeInfo.protectionCheckError = String(eprot); }
        } catch (erx) { nsmRangeInfo = { error: String(erx) }; }
      }
      // 실행 계정 진단 — GAS 웹앱이 실제로 어느 계정으로 도는지(canEditByMe:false 원인 규명, 2026-07-20 GM 지시)
      var nsmEffectiveUser = '', nsmActiveUser = '', nsmFileOwner = '';
      try { nsmEffectiveUser = Session.getEffectiveUser().getEmail(); } catch (eeu) { nsmEffectiveUser = 'ERR:' + String(eeu); }
      try { nsmActiveUser = Session.getActiveUser().getEmail(); } catch (eau) { nsmActiveUser = 'ERR:' + String(eau); }
      try { nsmFileOwner = DriveApp.getFileById(MEMBER_SPREADSHEET_ID).getOwner().getEmail(); } catch (efo) { nsmFileOwner = 'ERR:' + String(efo); }
      var nsmDiag = {
        ok: true,
        mode: nsmMode,
        effectiveUser: nsmEffectiveUser,
        activeUser: nsmActiveUser,
        fileOwner: nsmFileOwner,
        headerFound: String(nsmHeaders[nsmColIdx]),
        colIndex: nsmColIdx + 1,
        boundFormUrl: nsmBoundForm,
        hasDataValidation: !!nsmDv,
        dvType: nsmCritType,
        dvValues: (nsmDv && nsmCritType === 'VALUE_IN_LIST') ? nsmDv.getCriteriaValues() : null,
        rangeInfo: nsmRangeInfo,
        oldValueCellCount: nsmOldValueCellCount
      };
      if (nsmMode === 'apply') {
        if (String(body.key || '') !== _NAVER_SPLIT_GUARD) {
          return _json({ ok: false, error: 'guard-mismatch' });
        }
        if (!nsmDv) return _json({ ok: false, error: 'no-validation-rule', diag: nsmDiag });

        if (nsmCritType === 'VALUE_IN_LIST') {
          var nsmCrit = nsmDv.getCriteriaValues();
          var nsmOldList = nsmCrit[0];
          var nsmShowDropdown = nsmCrit[1];
          var nsmNewList = [];
          var nsmReplaced = false;
          for (var nli = 0; nli < nsmOldList.length; nli++) {
            if (String(nsmOldList[nli]).trim() === nsmOld) {
              nsmNewList.push(nsmNewA);
              nsmNewList.push(nsmNewB);
              nsmReplaced = true;
            } else {
              nsmNewList.push(nsmOldList[nli]);
            }
          }
          if (!nsmReplaced) return _json({ ok: false, error: 'old-value-not-in-list', list: nsmOldList });
          var nsmNewRule = SpreadsheetApp.newDataValidation()
            .requireValueInList(nsmNewList, nsmShowDropdown)
            .setAllowInvalid(true)
            .build();
          var nsmMaxRows = nsmSheet.getMaxRows();
          var nsmFullRange = nsmSheet.getRange(2, nsmColIdx + 1, Math.max(nsmMaxRows - 1, 1), 1);
          nsmFullRange.setDataValidation(nsmNewRule);
        } else if (nsmCritType === 'VALUE_IN_RANGE') {
          if (!nsmSrcRange) return _json({ ok: false, error: 'range-unresolved', diag: nsmDiag });
          var nsmRangeVals2 = nsmSrcRange.getValues();
          var nsmTargetRow = -1;
          for (var rv2 = 0; rv2 < nsmRangeVals2.length; rv2++) {
            if (String(nsmRangeVals2[rv2][0] || '').trim() === nsmOld) { nsmTargetRow = rv2; break; }
          }
          if (nsmTargetRow < 0) return _json({ ok: false, error: 'old-value-not-in-range', rangeInfo: nsmRangeInfo });
          // 옵션 목록 범위 안의 빈 칸(패딩)을 찾아 두 번째 값을 넣는다. 없으면 범위 바로 아래 빈 행을 사용(옵션 시트 전용 — 문의 데이터 시트 아님).
          var nsmEmptyRow = -1;
          for (var rv3 = 0; rv3 < nsmRangeVals2.length; rv3++) {
            if (rv3 !== nsmTargetRow && !String(nsmRangeVals2[rv3][0] || '').trim()) { nsmEmptyRow = rv3; break; }
          }
          var nsmOptSheet = nsmSrcRange.getSheet();
          var nsmOptCol = nsmSrcRange.getColumn();
          var nsmOptStartRow = nsmSrcRange.getRow();
          // 1) 기존 값 칸 → 'N-플레이스'로 교체(선택항목 목록 수정 — 문의 데이터 시트 아님, 허용 범위)
          nsmOptSheet.getRange(nsmOptStartRow + nsmTargetRow, nsmOptCol).setValue(nsmNewA);
          var nsmUsedEmptyPad = false, nsmExpandedRange = false;
          if (nsmEmptyRow >= 0) {
            nsmOptSheet.getRange(nsmOptStartRow + nsmEmptyRow, nsmOptCol).setValue(nsmNewB);
            nsmUsedEmptyPad = true;
          } else {
            // 패딩 없음 → 범위 바로 다음 행에 추가하고, 검증 규칙의 참조범위를 1행 확장.
            // 안전장치: 그 다음 행이 이미 다른 용도로 쓰이고 있으면(빈칸 아니면) 절대 덮어쓰지 않고 중단.
            var nsmNextRow = nsmOptStartRow + nsmRangeVals2.length;
            var nsmNextCellVal = String(nsmOptSheet.getRange(nsmNextRow, nsmOptCol).getValue() || '').trim();
            if (nsmNextCellVal) {
              return _json({ ok: false, error: 'next-row-occupied-abort', row: nsmNextRow, col: nsmOptCol, existingValue: nsmNextCellVal });
            }
            nsmOptSheet.getRange(nsmNextRow, nsmOptCol).setValue(nsmNewB);
            var nsmExpandedSrc = nsmOptSheet.getRange(nsmOptStartRow, nsmOptCol, nsmRangeVals2.length + 1, 1);
            var nsmExpandedRule = SpreadsheetApp.newDataValidation()
              .requireValueInRange(nsmExpandedSrc, true)
              .setAllowInvalid(true)
              .build();
            var nsmMaxRows2 = nsmSheet.getMaxRows();
            nsmSheet.getRange(2, nsmColIdx + 1, Math.max(nsmMaxRows2 - 1, 1), 1).setDataValidation(nsmExpandedRule);
            nsmExpandedRange = true;
          }
          var nsmOldValueCellCountAfterR = 0;
          var nsmRecheckR = nsmLastRow >= 2 ? nsmSheet.getRange(2, nsmColIdx + 1, nsmLastRow - 1, 1).getValues() : [];
          for (var rvr = 0; rvr < nsmRecheckR.length; rvr++) {
            if (String(nsmRecheckR[rvr][0] || '').trim() === nsmOld) nsmOldValueCellCountAfterR++;
          }
          return _json({
            ok: true,
            applied: true,
            mode: 'range',
            optionSheet: nsmOptSheet.getName(),
            usedEmptyPad: nsmUsedEmptyPad,
            expandedRange: nsmExpandedRange,
            oldValueCellCountBefore: nsmOldValueCellCount,
            oldValueCellCountAfter: nsmOldValueCellCountAfterR
          });
        } else {
          return _json({ ok: false, error: 'unsupported-criteria-type', dvType: nsmCritType, diag: nsmDiag });
        }
        var nsmRecheckVals = nsmLastRow >= 2 ? nsmSheet.getRange(2, nsmColIdx + 1, nsmLastRow - 1, 1).getValues() : [];
        var nsmOldValueCellCountAfter = 0;
        for (var nvr2 = 0; nvr2 < nsmRecheckVals.length; nvr2++) {
          if (String(nsmRecheckVals[nvr2][0] || '').trim() === nsmOld) nsmOldValueCellCountAfter++;
        }
        return _json({
          ok: true,
          applied: true,
          mode: 'list',
          oldValueCellCountBefore: nsmOldValueCellCount,
          oldValueCellCountAfter: nsmOldValueCellCountAfter
        });
      }
      return _json(nsmDiag);
    } catch (e) {
      return _json({ ok: false, error: String(e) });
    }
  }

  // ─── 회원관리 페이지(CPO): 등록회원 명단 조회 (등록기간 from~to 필터, 1~12월 체크 포함) ───
  if (action === 'member_registered_list') {
    // 2026-06-25 GM: 실제 회원 DB(유효회원 시트) 등록일자 기준 — 대시보드 '멤버십 등록건' 카드와 동일 소스.
    var rlFrom = String(body.from || '');  // YYYY-MM-DD
    var rlTo   = String(body.to   || '');
    // ★newOnly=1 → 신규 등록만 (2026-08-04 GM 지시).
    //   GM: "멤버십 회원관리에 있는 회원님이 재등록 시에는 신규가 아니라서 여기 등록현황에 반영이 되면 안 될 것 같고".
    //   기본값은 끔 — 같은 액션을 월별 등록현황·전환율도 쓰므로 기본을 바꾸면 그쪽 숫자가 말없이 달라진다.
    //   판정: 등록 분류가 '신규' 이거나, 분류가 비었는데 등록회차가 1 이하인 행(첫 등록). 그 외(재등록·양수·
    //   양도·환불·대기 등)는 신규가 아니다 — 실측 2026년 196건 중 17건이 그 부류였다.
    var rlNewOnly = (String(body.newOnly || '') === '1' || body.newOnly === true);
    var rlRows = [];
    // ★캐시(2026-08-04 시토 · GM '불러오는데 너무 오래걸리는 것 같은데 왜그럴까?').
    //   실측: 이 액션만 캐시가 없어 매번 유효회원 시트 전체를 다시 읽었다 — 캐시 있을 때 7.5초 /
    //   무시했을 때 7.3초로 사실상 같았다(=캐시가 없다는 뜻). 다른 무거운 액션은 이미 같은 헬퍼로
    //   캐시를 쓰고 있어 새 장치를 만들지 않고 그 관례를 그대로 따른다(약속 L21).
    //   TTL 360초 = member_active_list 와 동일(5분 예열기 주기에 맞춘 값).
    //   ▸★캐시가 만든 새 위험 하나를 같이 막는다: 방금 등록한 회원이 몇 분간 안 보이면
    //     '안 넘어갔다'로 보인다 — 오늘(2026-08-04) GM 이 정확히 그 혼란을 겪었다. 그래서 회원 시트에
    //     쓰기가 일어날 때마다 세대번호(_memberCacheGen_)를 올려 옛 키를 통째로 못 쓰게 한다.
    //     키를 하나하나 지우지 않는 이유 = 기간·옵션 조합만큼 키가 갈려 열거가 불가능하다.
    var rlCache = CacheService.getScriptCache();
    var rlCacheKey = 'rl_v3_' + _memberCacheGen_() + '_' + rlFrom + '_' + rlTo + '_' + (rlNewOnly ? 'N' : 'A');
    if (!_nc) {
      var rlHit = _cacheGetJson_(rlCache, rlCacheKey);
      if (rlHit) return _json(rlHit);
    }
    try {
      var rlSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
      if (rlSh && rlSh.getLastRow() >= 2) {
        var rlCols = rlSh.getLastColumn();
        var rlHdr = rlSh.getRange(1, 1, 1, rlCols).getValues()[0].map(function(v){ return String(v).trim(); });
        function _rlIdx(want){ var w = String(want).replace(/\s/g, ''); for (var i = 0; i < rlHdr.length; i++){ if (rlHdr[i] && rlHdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; } return -1; }
        var rlNmI  = _rlIdx('회원명');
        var rlRegI = _rlIdx('등록일자');
        var rlPhI  = _rlIdx('휴대폰'); if (rlPhI < 0) rlPhI = _rlIdx('연락처'); if (rlPhI < 0) rlPhI = _rlIdx('전화');
        var rlPgI  = _rlIdx('수강반종목'); if (rlPgI < 0) rlPgI = _rlIdx('종목명'); if (rlPgI < 0) rlPgI = _rlIdx('회원권'); if (rlPgI < 0) rlPgI = _rlIdx('상품'); if (rlPgI < 0) rlPgI = _rlIdx('프로그램');
        // 등록 분류 3칸(2026-08-04 시토) — '등록분류'는 '재등록분류'와도 부분일치하지만 헤더 순서상
        //   앞칸('등록 분류')이 먼저 잡힌다(_memberActiveUpsert_ 와 같은 관례).
        var rlClsI  = _rlIdx('등록분류');
        var rlCls2I = _rlIdx('재등록분류');
        var rlSeqI  = _rlIdx('등록회차');
        var rlData = rlSh.getRange(2, 1, rlSh.getLastRow() - 1, rlCols).getValues();
        for (var ri = 0; ri < rlData.length; ri++) {
          var rr = rlData[ri];
          var rlNm = rlNmI >= 0 ? String(rr[rlNmI] == null ? '' : rr[rlNmI]).trim() : '';
          if (!rlNm) continue;
          var rv = rlRegI >= 0 ? rr[rlRegI] : '';
          var regDate = (rv instanceof Date && !isNaN(rv.getTime())) ? Utilities.formatDate(rv, 'Asia/Seoul', 'yyyy-MM-dd') : _miToISO_(rv);
          if (!regDate) continue;                       // 등록일 없는 행 제외
          if (rlFrom && regDate < rlFrom) continue;
          if (rlTo   && regDate > rlTo)   continue;
          var rlPh = rlPhI >= 0 ? String(rr[rlPhI] == null ? '' : rr[rlPhI]) : '';
          var rlPp = rlPh.replace(/[^0-9]/g, '');
          if (rlPp.length === 11) rlPh = rlPp.slice(0,3) + '-' + rlPp.slice(3,7) + '-' + rlPp.slice(7);
          else if (rlPp.length === 10) rlPh = rlPp.slice(0,3) + '-' + rlPp.slice(3,6) + '-' + rlPp.slice(6);
          rlRows.push({
            rowIndex: ri + 2,
            name:     rlNm,
            phone:    rlPh,
            program:  rlPgI >= 0 ? String(rr[rlPgI] == null ? '' : rr[rlPgI]).trim() : '',
            regDate:  regDate,
            // ★2026-08-04 시토(GM 지적 '황경태·박기순은 재등록이신데?') — 이 액션은 등록일자 기간만 보고
            //   등록 분류를 아예 안 봤다. 그래서 화면 「멤버십 신규 등록현황」에 재등록·양수·환불이 함께 섞이고,
            //   같은 소스를 쓰는 문의→가입 전환율의 분자도 같이 부풀었다.
            //   실측(2026-08-04): 2026년 등록 196건 중 실제 신규는 179건 — 17건이 신규가 아니었다
            //   (재등록 6·양수 5·환불 4·양도 1·대기 1). 2026-08 은 5건 중 3건이 재등록이었다.
            //   ▸여기서 걸러내지 않고 **값을 같이 내려준다** — 걸러 버리면 화면에서 재등록이 통째로 사라져
            //     '정직 표기가 빈 화면이 되는' 부류가 된다. 가르는 것은 화면 몫.
            //   ▸regClass = 「등록 분류」 · regClass2 = 「재등록 분류」(둘 다 내려준다 — 배303 통합 전까지
            //     한쪽만 값이 있는 행이 있다. 박기순님은 등록 분류만, 황경태님은 둘 다 있다).
            regClass:  rlClsI  >= 0 ? String(rr[rlClsI]  == null ? '' : rr[rlClsI]).trim()  : '',
            regClass2: rlCls2I >= 0 ? String(rr[rlCls2I] == null ? '' : rr[rlCls2I]).trim() : '',
            regSeq:    rlSeqI  >= 0 ? String(rr[rlSeqI]  == null ? '' : rr[rlSeqI]).trim()  : ''
          });
        }
        if (rlNewOnly) {
          // 판정 정본 = _isNewRegistration_(2026-08-06 시포) — 카드(cpo_today_stats)와 같은 함수를 쓴다.
          rlRows = rlRows.filter(function(r){
            return _isNewRegistration_(r.regClass, r.regClass2, r.regSeq);
          });
        }
        rlRows.sort(function(a, b){ return a.regDate < b.regDate ? 1 : (a.regDate > b.regDate ? -1 : 0); }); // 최신 등록 먼저
      }
    } catch (eRl) {}
    var rlResult = { ok: true, count: rlRows.length, data: rlRows, newOnly: rlNewOnly };
    _cachePutJson_(rlCache, rlCacheKey, rlResult, 360);
    return _json(rlResult);
  }

  // member_registered_setmonth 제거(2026-08-06 시토, 배295 점검) — 위 dispatch 테이블 주석 참조(호출부 0건).

  // member_registered_delete 제거(2026-08-05 시토, INC-042 재발방지 ②) — 위 dispatch 테이블 주석 참조.
  //   ★2026-08-06 시토(배295) 정정 — 위 주석은 "등록 해제가 이미 처리된다"고 했지만, 그 경로(문의 목록
  //   체크박스 해제 → member_inquiry_update → _regRemove_)는 **문의에서 SUC 전환된 건**에만 걸린다.
  //   "+직접등록"(문의를 거치지 않는 계약)은 되돌릴 통로가 그때도 없었다 — 아래 member_registered_remove
  //   가 그 통로다(비밀번호 게이트 + 중복전화 가드 + 유효회원 동반 정리).

  // ─── 등록현황(CPO): 페이지에서 직접 등록 추가(문의 퍼널 안 거친 직접·법인 계약 등) — _regUpsert_ 멱등(전화키). 2026-06-29 시포 ───
  if (action === 'member_registered_add') {
    var raName  = String(body.name    || '').trim();
    var raPhone = String(body.phone   || '').trim();
    var raProg  = String(body.program || '').trim();
    var raDate  = String(body.regDate || '').trim() || _todayKR_();
    var raMonths = parseInt(body.months, 10) || 0;  // 개월수(선택) — 2026-08-01 시토(배286), 있으면 종료일자·잔여일 계산
    if (!raPhone) return _json({ ok: false, error: '전화번호 필수(중복 방지 키)' });
    _regUpsert_(raName, raPhone, raProg, raDate);  // 월별체크용 '26년 등록현황' 갱신(기존 유지, 기존 전화면 갱신·없으면 등록일 도장 추가)
    // ★배276 근본수리(2026-08-01 시토) — 화면(회원관리·신규등록현황)은 유효회원 탭을 읽는다. 위 한 줄만으로는
    //   '26년 등록현황'에만 쌓여 화면에 안 보인다(임정은M 신고 FB260801-152607/141856). 유효회원에도 같은 전화키로 upsert.
    // ★FB260806-150441 근본수리 — 종전 catch(e){} 가 예외를 삼켜 유효회원 미반영 시에도 UI에 "성공"이 떴다.
    //   phone-ambiguous(중복전화 2건+) 반환 객체도 버려지던 구조. 이제 예외·에러 반환 모두 잡아 ok:false로 표면화.
    //   _regUpsert_는 이미 성공했고 멱등이므로 재시도가 안전하다.
    var _mauErr = null;
    try {
      // 나이도 함께 넣는다(GM 지시 2026-08-25 "나이 누락건이 꽤 많네").
      //   화면에서 직접 등록한 회원은 나이 칸이 늘 비어 있었다 — 이 경로가 나이를 안 받아서다.
      //   유효회원 upsert 는 이미 opts.age 를 쓸 줄 안다(칸 배선 있음). 값을 안 보내면 종전 그대로.
      var _mauR = _memberActiveUpsert_(raName, raPhone, raProg, raDate, raMonths,
                                       { age: String(body.age || '').trim() });
      if (_mauR && _mauR.ok === false) _mauErr = _mauR.error || 'activeUpsert 거부';
    } catch (e) { _mauErr = String(e); }
    // 등록 추가 알림 → '문의 알림' 방(전환 3경로와 정합). override 누락 시 개인 OWNER방으로 새던 버그 수정 — 직접·법인 등록건도 문의알림방에 통보. 2026-07-06 시토·GM.
    try {
      var _raRegChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
      _notifyTelegram('➕ <b>등록 추가</b> — 직접/법인 등록\n· 이름: ' + (raName || '-') + '\n· 프로그램: ' + _teamChip(raProg) + (raProg || '-') + '\n· 등록일: ' + raDate, _raRegChatId);
    } catch (e) {}
    if (_mauErr) return _json({ ok: false, error: '유효회원 반영 실패 (' + _mauErr + ') — 등록 버튼을 다시 눌러 재시도하세요.' });
    return _json({ ok: true, message: '등록 추가되었습니다.' });
  }

  // ─── 등록현황(CPO): "+직접등록" 되돌리기 — _regRemove_(2478행) 재사용, 유효회원까지 정리. 2026-08-06 시토(배295) ───
  //   member_registered_delete(2026-08-05 INC-042로 제거)와 달리 비밀번호 게이트 + 중복전화 가드 +
  //   유효회원 동반 정리를 거친다. 새 인증체계 없음 — member_inquiry_delete(5601행)와 같은 STAFF_GATE_PW 재사용(약속 L21).
  if (action === 'member_registered_remove') {
    var rmPhone = String(body.phone || '').trim();
    if (!rmPhone) return _json({ ok: false, error: 'phone 필수' });
    var _rmGatePw = _accessProp_('STAFF_GATE_PW') || 'wellperion!@345';
    if (String(body.password || '') !== _rmGatePw) return _json({ ok: false, error: '비밀번호가 올바르지 않습니다.' });
    var rmResult = _regRemove_(rmPhone);
    if (rmResult && rmResult.ok === false) return _json(rmResult);
    if (!rmResult || rmResult.removed === 0) return _json({ ok: false, error: '해당 등록회원 없음' });
    try { _notifyTelegram('➖ 등록 해제(되돌리기) — ' + (body.name || rmPhone)); } catch (e) {}
    return _json({ ok: true, message: '등록이 해제되었습니다.' });
  }

  // ─── 휴회 시트 구조 조사 (읽기 전용·일회성·내부토큰) ───
  //   휴회는 별도 전용 시트에서 관리됨(2026-07-20 GM). 연동 설계를 위한 구조 파악용.
  //   gviz로는 401(비공개)이라 GAS 계정 권한으로만 읽힌다. 쓰기 코드 없음. 조사 완료 후 제거 예정.
  // ─── 강습 팀시트 구조 진단(읽기 전용 · 개인정보 0) — 2026-07-23 시포·GM ───
  //   왜: 강습 회원 명단 1,742명 중 수영(1,007명)만 이름이 나오고 나머지 735명은 이름·연락처가 빈칸이다.
  //   헤더('성함'·'휴대폰 번호')는 정상 탐지되므로 "칸을 못 찾는" 문제가 아니라 "등록으로 세는 행에
  //   애초에 이름이 없다"는 뜻 — 등록 판정(상태열 자동탐지)이 회원 행이 아닌 행을 세고 있을 가능성.
  //   회원 수 KPI 직결이라 확정이 필요하고, 팀시트는 비공개라 서버에서만 볼 수 있다.
  //   ★반환하는 것: 헤더 이름·열 위치·상태값 종류와 건수·빈칸 수·행번호. 셀 값(이름·전화)은 반환하지 않는다.
  if (action === 'lesson_team_sheet_diag') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var dgType = String(body.type || '');
    var dgOut = [];
    LESSON_TEAM_SHEETS.forEach(function (cfg) {
      if (dgType && cfg.유형 !== dgType) return;
      var rec = { 명: cfg.명, 유형: cfg.유형, gid: cfg.gid };
      try {
        var dsh = _sheetByGid_(cfg.ssId, cfg.gid);
        if (!dsh) { rec.error = '시트 없음'; dgOut.push(rec); return; }
        var dLast = dsh.getLastRow(), dCol = dsh.getLastColumn();
        rec.rows = dLast; rec.cols = dCol;
        if (dLast < 2 || dCol < 1) { dgOut.push(rec); return; }
        var dData = dsh.getRange(1, 1, dLast, dCol).getValues();
        var dHdr = dData[0];
        rec.headers = dHdr.map(function (h) { return String(h == null ? '' : h).replace(/\s+/g, ' ').trim().slice(0, 18); });
        // 상태열 자동탐지 재현(roster와 동일 로직) + 후보들도 같이 보여 준다(왜 그 열이 뽑혔는지 보이게)
        var dBest = -1, dBestCnt = 0, dCand = [];
        for (var dc = 0; dc < dCol; dc++) {
          var dcnt = 0, ddist = {}, ddn = 0;
          for (var dr = 1; dr < dData.length; dr++) {
            var dv = String(dData[dr][dc] == null ? '' : dData[dr][dc]).trim();
            if (!dv) continue;
            if (!ddist[dv]) { ddist[dv] = 1; ddn++; }
            if (_isLessonStatusVal_(dv)) dcnt++;
          }
          if (ddn >= 2 && ddn <= 30 && dcnt > dBestCnt) { dBestCnt = dcnt; dBest = dc; }
          if (dcnt > 0) dCand.push({ 열: _colLetter_(dc), 헤더: String(dHdr[dc] == null ? '' : dHdr[dc]).trim().slice(0, 16), 상태형값: dcnt, 고유값수: ddn });
        }
        rec.상태열후보 = dCand.slice(0, 8);
        rec.선택된상태열 = dBest >= 0 ? { 열: _colLetter_(dBest), 헤더: String(dHdr[dBest] == null ? '' : dHdr[dBest]).trim().slice(0, 18) } : null;
        var dName = _findCol_(dHdr, ['성함', '이름', '성명']);
        var dPhone = _findCol_(dHdr, ['연락처', '전화', '휴대폰']);
        rec.이름열 = dName >= 0 ? { 열: _colLetter_(dName), 헤더: String(dHdr[dName] == null ? '' : dHdr[dName]).trim().slice(0, 18) } : null;
        rec.연락처열 = dPhone >= 0 ? { 열: _colLetter_(dPhone), 헤더: String(dHdr[dPhone] == null ? '' : dHdr[dPhone]).trim().slice(0, 18) } : null;
        // 이름 칸이 전체 몇 행에 차 있는지(등록 여부와 무관) — 시트 자체가 비어 있는 건지 판별용
        var dNameFilled = 0;
        if (dName >= 0) { for (var d5 = 1; d5 < dData.length; d5++) { if (String(dData[d5][dName] == null ? '' : dData[d5][dName]).trim()) dNameFilled++; } }
        rec.이름칸_채워진행 = dNameFilled;
        // ★비어 있는 이유를 가른다 — '사람이 안 적었다'와 '수식이 깨졌다'는 조치가 완전히 다르다.
        //   수식이면 종류(IMPORTRANGE 등)만 보고, 오류값(#REF!·#N/A)이면 그 개수를 센다. 셀 값은 반환하지 않는다.
        //   주변 칸(거주지·강습 종목) 채움률도 같이 봐서 '그 블록 전체가 빈 것'인지 '이름만 빈 것'인지 구분한다.
        if (dName >= 0) {
          var dFx = 0, dErr = 0, dKind = '';
          var dProbeN = Math.min(dLast, 60);
          for (var d6 = 2; d6 <= dProbeN; d6++) {
            var fx = String(dsh.getRange(d6, dName + 1).getFormula() || '');
            if (fx) { dFx++; if (!dKind) dKind = fx.replace(/\s+/g, ' ').slice(0, 40); }
            var vv = String(dData[d6 - 1][dName] == null ? '' : dData[d6 - 1][dName]);
            if (vv.indexOf('#REF') >= 0 || vv.indexOf('#N/A') >= 0 || vv.indexOf('#ERROR') >= 0) dErr++;
          }
          rec.이름칸_진단 = { 표본행: dProbeN - 1, 수식셀: dFx, 수식예: dKind, 오류값셀: dErr };
        }
        var dNeighbor = {};
        [['거주지', 4], ['강습 종목', 5], ['문의경로', 6], ['타임스탬프', 1]].forEach(function (pair) {
          var ci = pair[1];
          if (ci >= dCol) return;
          var f = 0;
          for (var d7 = 1; d7 < dData.length; d7++) { if (String(dData[d7][ci] == null ? '' : dData[d7][ci]).trim()) f++; }
          dNeighbor[pair[0]] = f;
        });
        rec.주변칸_채워진행 = dNeighbor;
        if (dBest < 0) { dgOut.push(rec); return; }
        var dvc = {};
        for (var d3 = 1; d3 < dData.length; d3++) {
          var dv3 = String(dData[d3][dBest] == null ? '' : dData[d3][dBest]).trim();
          if (dv3) dvc[dv3.slice(0, 14)] = (dvc[dv3.slice(0, 14)] || 0) + 1;
        }
        rec.상태값분포 = dvc;
        var dReg = 0, dNameless = 0, dSample = [];
        for (var d4 = 1; d4 < dData.length; d4++) {
          if (!_isLessonReg_(dData[d4][dBest])) continue;
          dReg++;
          var dnm = dName >= 0 ? String(dData[d4][dName] == null ? '' : dData[d4][dName]).trim() : '';
          if (!dnm) { dNameless++; if (dSample.length < 5) dSample.push(d4 + 1); }
        }
        rec.등록으로센행 = dReg;
        rec.그중_이름없음 = dNameless;
        rec.이름없는행_행번호샘플 = dSample;
      } catch (eDg) { rec.error = String(eDg).slice(0, 120); }
      dgOut.push(rec);
    });
    return _json({ ok: true, count: dgOut.length, data: dgOut });
  }

  if (action === 'hold_sheet_probe') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var hpSs = SpreadsheetApp.openById('1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ');
    var hpTabs = hpSs.getSheets().map(function (s) {
      return { name: s.getName(), gid: s.getSheetId(), rows: s.getLastRow(), cols: s.getLastColumn() };
    });
    var hpTarget = null, hpAll = hpSs.getSheets();
    for (var hi = 0; hi < hpAll.length; hi++) { if (hpAll[hi].getSheetId() === 514238773) { hpTarget = hpAll[hi]; break; } }
    if (!hpTarget) return _json({ ok: true, tabs: hpTabs, target: null, note: 'gid 514238773 탭 없음' });
    var hpLastR = hpTarget.getLastRow(), hpLastC = hpTarget.getLastColumn();
    var hpHdr = hpLastR > 0 ? hpTarget.getRange(1, 1, 1, hpLastC).getDisplayValues()[0] : [];
    // full=1 — 실측 분석(재등록 대상 교차·규칙 위반·연결키 신뢰도)에 전체 567행 필요. 기본은 기존 head/tail 샘플만(가벼움 유지). 2026-07-20 시포.
    if (String(body.full || '') === '1') {
      var hpAllN = Math.max(0, hpLastR - 1);
      var hpAllRows = hpAllN > 0 ? hpTarget.getRange(2, 1, hpAllN, hpLastC).getDisplayValues() : [];
      return _json({ ok: true, target: { name: hpTarget.getName(), gid: 514238773, rows: hpLastR, cols: hpLastC },
                     headers: hpHdr, rows: hpAllRows });
    }
    var hpN = Math.min(hpLastR - 1, 12);
    var hpSample = hpN > 0 ? hpTarget.getRange(2, 1, hpN, hpLastC).getDisplayValues() : [];
    var hpTailN = Math.min(hpLastR - 1, 8);
    var hpTail = hpTailN > 0 ? hpTarget.getRange(Math.max(2, hpLastR - hpTailN + 1), 1, hpTailN, hpLastC).getDisplayValues() : [];
    return _json({ ok: true, tabs: hpTabs, target: { name: hpTarget.getName(), gid: 514238773, rows: hpLastR, cols: hpLastC },
                   headers: hpHdr, head: hpSample, tail: hpTail });
  }

  // ─── 강습 LOSS사유 데이터 확인 규칙 진단·셋업 (일회성·내부토큰) ───
  //   사고: 07-18 신설 이후 LOSS사유 저장 0건 — 시트에 걸린 데이터 확인 규칙이 화면 선택지(INQ_LOSS_REASON_OPTIONS)와
  //   불일치해 저장이 통째로 거부됨(예: 셀 Q3433 데이터 확인 규칙 위반). gviz로는 규칙 자체를 읽을 수 없어 밖에서 확인 불가였음.
  //   mode=diag(기본,읽기전용) / apply(규칙 설정·값은 안 건드림) / verify(되읽기) / test(테스트행 1건 저장→즉시원복).
  //   헤더는 정확일치로만 찾는다(열 번호 하드코딩 금지 — 성인/유소년 두 시트가 위치 다름). 2026-07-20 시포(GM 승인).
  if (action === 'loss_reason_setup') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var lrMode = String(body.mode || 'diag');
    var LR_OPTIONS = ['가격', '거리/위치', '시간대 안 맞음', '타업체 선택', '단순 문의(등록의사 없음)', '연락 두절', '기타'];  // membership.html INQ_LOSS_REASON_OPTIONS와 문자 단위 일치 확인됨(2026-07-20)
    var lrTargets = [
      { gid: 111889422, type: '성인강습' },
      { gid: 268994754, type: '유소년강습(WSC)' }
    ];
    var _lrColLetter_ = function (n) {
      var s = '';
      while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); }
      return s;
    };
    var _lrRuleInfo_ = function (rule) {
      if (!rule) return null;
      var info = { criteriaType: String(rule.getCriteriaType()), allowInvalid: rule.getAllowInvalid(), helpText: rule.getHelpText() || '' };
      try { info.criteriaValues = rule.getCriteriaValues(); } catch (e) { info.criteriaValues = null; }
      return info;
    };

    var lrReport = [];
    for (var lti = 0; lti < lrTargets.length; lti++) {
      var lrCfg = lrTargets[lti];
      var lrSh = _sheetByGid_(LESSON_SS_ID, lrCfg.gid);
      var lrItem = { type: lrCfg.type, gid: lrCfg.gid };
      if (!lrSh) { lrItem.error = '시트 없음'; lrReport.push(lrItem); continue; }
      lrItem.sheetName = lrSh.getName();
      var lrLastCol = lrSh.getLastColumn();
      var lrLastRow = lrSh.getLastRow();
      lrItem.lastRow = lrLastRow; lrItem.lastCol = lrLastCol;
      var lrHdr = lrLastCol > 0 ? lrSh.getRange(1, 1, 1, lrLastCol).getValues()[0].map(function (v) { return String(v).trim(); }) : [];
      var lrColIdx = -1, lrNoteColIdx = -1;
      for (var hci = 0; hci < lrHdr.length; hci++) {
        if (lrHdr[hci] === 'LOSS사유') lrColIdx = hci;
        if (lrHdr[hci] === 'LOSS사유메모') lrNoteColIdx = hci;
      }
      lrItem.lossReasonCol = lrColIdx >= 0 ? { colNum: lrColIdx + 1, colLetter: _lrColLetter_(lrColIdx + 1) } : null;
      lrItem.lossReasonNoteCol = lrNoteColIdx >= 0 ? { colNum: lrNoteColIdx + 1, colLetter: _lrColLetter_(lrNoteColIdx + 1) } : null;
      if (lrColIdx < 0) { lrItem.error = 'LOSS사유 헤더 없음'; lrReport.push(lrItem); continue; }

      if (lrMode === 'diag' || lrMode === 'verify') {
        // 전체 열 getDataValidations()는 행이 수백~수천이면 GAS에서 극단적으로 느림(실측 180초+ 타임아웃).
        // 데이터 확인 규칙은 보통 연속 범위 단위로 한 번에 걸리므로 소수 샘플 행(앞/중간/뒤)만 단일 셀로 훑어도
        // 서로 다른 규칙 구간이 있으면 대부분 걸러진다. 2026-07-20 시포(타임아웃 수리).
        var lrRuleSamples = [], lrSeen = {}, lrSampleRows = [];
        if (lrLastRow >= 2) {
          var lrMidRow = Math.floor((2 + lrLastRow) / 2);
          [2, 3, lrMidRow, lrLastRow - 1, lrLastRow].forEach(function (rr) {
            if (rr >= 2 && rr <= lrLastRow && lrSampleRows.indexOf(rr) < 0) lrSampleRows.push(rr);
          });
          lrSampleRows.forEach(function (rr) {
            var rule = lrSh.getRange(rr, lrColIdx + 1).getDataValidation();
            var info = _lrRuleInfo_(rule);
            var key = info ? JSON.stringify(info) : 'NONE';
            if (!lrSeen[key]) { lrSeen[key] = true; lrRuleSamples.push({ row: rr, rule: info }); }
          });
        }
        lrItem.sampledRows = lrSampleRows;
        lrItem.existingRules = lrRuleSamples;  // 샘플 행마다 규칙이 다르면 여러 개로 나타남(원인 규명 자료) — 표본이라 전 구간 보장은 아님
        if (lrNoteColIdx >= 0 && lrLastRow >= 2) {
          lrItem.noteColRule = _lrRuleInfo_(lrSh.getRange(2, lrNoteColIdx + 1).getDataValidation());
        }
        var lrValCount = 0;
        if (lrLastRow >= 2) {
          var lrVals = lrSh.getRange(2, lrColIdx + 1, lrLastRow - 1, 1).getValues();
          for (var vi = 0; vi < lrVals.length; vi++) if (String(lrVals[vi][0] || '').trim()) lrValCount++;
        }
        lrItem.valueCount = lrValCount;
      }

      if (lrMode === 'apply') {
        var lrMaxRows = lrSh.getMaxRows();
        var lrBufferEnd = Math.min(lrLastRow + 300, lrMaxRows);
        var lrNumRows = lrBufferEnd - 1;  // 2행부터
        if (lrNumRows < 1) { lrItem.error = '적용 행 없음'; lrReport.push(lrItem); continue; }
        var lrRule = SpreadsheetApp.newDataValidation()
          .requireValueInList(LR_OPTIONS, true)
          .setAllowInvalid(true)  // ★경고 방식 — 엄격 규칙이 저장을 통째로 막던 원인 재발 방지
          .setHelpText('화면 선택지와 동일. 목록 밖 값은 점검기가 확인합니다.')
          .build();
        lrSh.getRange(2, lrColIdx + 1, lrNumRows, 1).setDataValidation(lrRule);
        lrItem.applied = { fromRow: 2, toRow: 2 + lrNumRows - 1, options: LR_OPTIONS };
      }

      if (lrMode === 'test') {
        var lrNameColIdx = -1, lrPhoneColIdx = -1;
        for (var hci2 = 0; hci2 < lrHdr.length; hci2++) {
          if (lrHdr[hci2] === '성함' || lrHdr[hci2] === '이름') lrNameColIdx = hci2;
          if (lrHdr[hci2] === '연락처' || lrHdr[hci2] === '전화') lrPhoneColIdx = hci2;
        }
        var lrTestRow = -1;
        if (lrLastRow >= 2 && (lrNameColIdx >= 0 || lrPhoneColIdx >= 0)) {
          var lrNCols = Math.max(lrNameColIdx, lrPhoneColIdx) + 1;
          var lrAllVals = lrSh.getRange(2, 1, lrLastRow - 1, lrNCols).getValues();
          for (var tri = 0; tri < lrAllVals.length; tri++) {
            var tName = lrNameColIdx >= 0 ? String(lrAllVals[tri][lrNameColIdx] || '') : '';
            var tPhone = lrPhoneColIdx >= 0 ? String(lrAllVals[tri][lrPhoneColIdx] || '') : '';
            if (tName.indexOf('테스트') >= 0 || tPhone.replace(/[^0-9]/g, '') === '01000000000') { lrTestRow = tri + 2; break; }
          }
        }
        if (lrTestRow < 0) { lrItem.testResult = '미검증(테스트 행 없음)'; lrReport.push(lrItem); continue; }
        var lrCell = lrSh.getRange(lrTestRow, lrColIdx + 1);
        lrCell.setValue('가격');
        SpreadsheetApp.flush();
        var lrReadBack = String(lrCell.getValue() || '');
        lrCell.setValue('');  // 즉시 원복
        SpreadsheetApp.flush();
        lrItem.testResult = { row: lrTestRow, wrote: '가격', readBack: lrReadBack, success: lrReadBack === '가격', reverted: String(lrCell.getValue() || '') === '' };
      }

      lrReport.push(lrItem);
    }

    return _json({ ok: true, mode: lrMode, sheets: lrReport });
  }

  // ★배209 근본수리 완료 기록(2026-08-04, 코드 변경 없음 — 이 주석만 남김. 1회성 진단·수리 액션
  //   inquiry_type_validation_209 는 실행·검증 뒤 여기서 제거됨, DEPLOY_PLAYBOOK.md 이력에도 남김):
  //   근본원인 = 문의접수(LANDING)가 아니라 _mirrorInquiryToStaffLog_(:414)가 '26년 신규문의'
  //   (MEMBER, gid1902010032) 컬럼E("...어떤 경로로 알게 되셨나요?")에 쓸 때 그 칸의
  //   VALUE_IN_RANGE·allowInvalid:false 드롭다운(원천 DATA!C2:C14)이 _canonicalChannel_(:265)의
  //   일부 출력('기타·미상'·'법인·단체'·'오프라인'·'유선전화')을 못 담아 스크립트 실행 자체를
  //   끊었다(문의접수 1차 쓰기는 항상 성공 — 행은 남고 응답만 깨진 것처럼 보인 이유).
  //   수리 = DATA!C12:C15에 그 4값 추가 + '26년 신규문의' 컬럼E 신규행 버퍼(그 시점 lastRow+1~+500)만
  //   검증범위를 DATA!C2:C15로 넓히고 allowInvalid:true 로 재발방지. 기존 행·기존 10개 값은 안 건드림.
  //   재현 6종(기본값·빈inflow·완전빈값·법인·오프라인·유선전화) 전부 JSON 정상 응답 확인.

  // ─── 회원관리 페이지(CPO): 멤버십 회원 명단 ('유효회원' 시트, 읽기전용·전화 마스킹) ───
  //   scope=valid(기본): 잔여일>=0 유효회원(2026-06-24 GM 최초 기준=잔여일>0 → 2026-07-31 실무진 신고로 경계 정정:
  //   잔여일 0=만료 당일까지 유효, LOSS 전환은 잔여일 -1일부터) / scope=ended: 종료·이탈(잔여일<0 또는 LOSS·환불·양도LOSS)
  //   ★빈 헤더·쓰레기 날짜헤더(GMT/표준시) 컬럼 제외 + 회원명 없는 빈/이상 행 제외(전체 컬럼은 그대로 노출).
  // 회원 변경 이력 읽기(배327) — 화면이 이 한 곳만 읽는다. 읽기 전용(삭제·수정 없음).
  //   scope=멤버십|강습 · limit 기본 200(최근순). 탭이 아직 없으면 빈 배열 + started 로 정직 응답.
  if (action === 'member_log_list') {
    var mlScope = String(body.scope || '').trim();
    var mlLimit = Math.min(parseInt(body.limit, 10) || 200, 500);
    var mlSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_LOG_SHEET);
    // '탭이 없다'와 '기록이 0건이다'를 응답에서 가른다(배342·웰리 2026-08-04). 그동안 둘이
    // 똑같이 {ok:true,data:[]} 로 나가서, 화면만 보면 수집이 끊긴 것과 진짜 0건이 구분되지
    // 않았다 — 자가점검이 말하는 '0 위장'이다. 기존 필드는 그대로 두고 한 칸만 더한다(비파괴).
    if (!mlSh) return _json({ ok: true, data: [], started: MEMBER_LOG_STARTED, tab: false, reason: 'no_tab' });
    if (mlSh.getLastRow() < 2) return _json({ ok: true, data: [], started: MEMBER_LOG_STARTED, tab: true, reason: 'empty' });
    var mlAll = mlSh.getRange(2, 1, mlSh.getLastRow() - 1, 8).getValues();
    var mlOut = [];
    for (var mi = mlAll.length - 1; mi >= 0 && mlOut.length < mlLimit; mi--) {
      var rw = mlAll[mi];
      if (mlScope && String(rw[7] || '') !== mlScope) continue;
      mlOut.push({ at: rw[0], staff: rw[1], member: rw[2], phone: rw[3],
                   field: rw[4], before: rw[5], after: rw[6], screen: rw[7] });
    }
    return _json({ ok: true, data: mlOut, started: MEMBER_LOG_STARTED });
  }

  // ─── 배350(GM 2026-08-04) 1회성 관리 액션 — 유효회원 시트에 '대기' 전용 칸 신설 ───
  //   '대기'를 등록분류/재등록분류 칸에 적으면 원래 신규/재등록 값이 지워지던 문제(박기순 케이스)를
  //   전용 칸으로 분리한다(웰리 2026-08-10, membership.html _isFutureStart 짝). 새 장치 아님 —
  //   이미 있는 _miEnsureCol_(휴회기간 칸 신설에 쓰던 것과 동일) 재사용. 멱등 — 이미 있으면 그대로 둔다.
  //   맨 끝에 헤더 1개만 추가(행 삭제·이동 0, 다른 칸 무손상).
  if (action === 'member_ensure_wait_col') {
    var ewSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!ewSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var ewHdr = ewSh.getRange(1, 1, 1, ewSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    var ewBefore = ewHdr.length;
    var ewIdx = _miEnsureCol_(ewSh, ewHdr, '대기');
    return _json({ ok: true, added: ewHdr.length > ewBefore, colIndex: ewIdx + 1, headerCount: ewHdr.length });
  }

  // ─── 잔여일순 정렬 온디맨드(2026-08-12 GM 지시 "시트에 잔여일 기준으로 정렬해줘") ───
  //   판정·정렬 본체는 member_active_sort_by_remaining_ 하나뿐이다(약속 L01·L21) — 여기서 다시 짜지 않고
  //   그 함수를 부르기만 한다. 그 함수가 이미 집계블록 경계 확인·행수 대조·실패 시 텔레그램 경보까지 한다.
  //   왜 필요한가: 정렬은 매일 자정 직후 워머에서 1회만 돌고 날짜 도장(MEMBER_SORT_LAST)으로 막혀 있어,
  //   낮에 종료일자·잔여일이 바뀌어도 다음 날까지 시트 순서가 옛 상태로 남았다. dry=1 이면 쓰기 없이 대상만.
  if (action === 'member_active_sort_now') {
    var snRes = member_active_sort_by_remaining_({ dry: String(body.dry || '') === '1' });
    return _json({ ok: !snRes.error, result: snRes, error: snRes.error || undefined });
  }

  if (action === 'member_active_list') {
    /* ★단일 행 조회(2026-08-20 시포 — GM "동기화 진행·완료가 정말 늦게 뜬다").
       저장 확인(read-back)은 방금 쓴 그 행 하나만 다시 읽으면 되는데, 지금까지 유효회원 전체(약 994명)를
       받고 못 찾으면 종료(201명)까지 또 받았다 — 실측 6.3초 + 13.2초 = 저장 1건에 최대 19.5초.
       화면이 rowIndexes=201,194 처럼 넘기면 그 행들만 읽어 같은 모양(data 배열)으로 돌려준다.
       읽는 범위만 좁힐 뿐 판정·형식·마스킹 규칙은 아래 본문과 같은 것을 쓴다(새 액션 0 · 약속 L21). */
    var aaOnly = String(body.rowIndexes || body.rowIndex || '').trim();
    if (aaOnly) {
      var aoWant = aaOnly.split(',').map(function(s){ return parseInt(String(s).trim(), 10); })
                          .filter(function(n){ return n >= 2; });
      if (!aoWant.length) return _json({ ok: false, error: 'rowIndexes 형식 오류(2 이상 정수)' });
      var aoSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
      if (!aoSh) return _json({ ok: false, error: '유효회원 시트 없음' });
      var aoLastCol = aoSh.getLastColumn(), aoLastRow = aoSh.getLastRow();
      var aoHdr = aoSh.getRange(1, 1, 1, aoLastCol).getValues()[0].map(function(v){ return String(v).trim(); });
      var aoKeep = aoHdr.map(function(h){ return h && !/GMT|표준시/.test(h); });
      // 지문키 재료 — 아래 본문(aaRows 생성부)과 같은 칸·같은 정규화를 쓴다.
      var aoNameI = -1;
      for (var aon = 0; aon < aoHdr.length; aon++) {
        var aonh = aoHdr[aon].replace(/\s/g, '');
        if (aonh === '성명' || aonh === '이름' || aonh.indexOf('회원명') >= 0) { aoNameI = aon; break; }
      }
      var aoTsI = -1;
      for (var aot = 0; aot < aoHdr.length; aot++) {
        var aoth = aoHdr[aot].replace(/\s/g, '');
        if (aoth.indexOf('등록일자') >= 0 || aoth.indexOf('타임스탬프') >= 0) { aoTsI = aot; break; }
      }
      var aoPhI = aoHdr.indexOf(MEMBER_PHONE_COL);
      var aoOut = [];
      for (var aoi = 0; aoi < aoWant.length; aoi++) {
        var aoR = aoWant[aoi];
        if (aoR > aoLastRow) continue;
        var aoRow = aoSh.getRange(aoR, 1, 1, aoLastCol).getValues()[0];
        var aoObj = { rowIndex: aoR };
        for (var aoc = 0; aoc < aoHdr.length; aoc++) {
          if (!aoKeep[aoc]) continue;
          var aoV = aoRow[aoc];
          if (aoV instanceof Date && !isNaN(aoV.getTime())) aoV = Utilities.formatDate(aoV, 'Asia/Seoul', 'yyyy-MM-dd');
          aoV = (aoV === null || aoV === undefined) ? '' : String(aoV);
          if (aoHdr[aoc] === MEMBER_PHONE_COL) {
            var aoP = aoV.replace(/[^0-9]/g, '');
            if (aoP.length === 11) aoV = aoP.slice(0,3) + '-' + aoP.slice(3,7) + '-' + aoP.slice(7);
            else if (aoP.length === 10) aoV = aoP.slice(0,3) + '-' + aoP.slice(3,6) + '-' + aoP.slice(6);
          }
          aoObj[aoHdr[aoc]] = aoV;
        }
        var _aoTsN = _normTsKey_(aoTsI >= 0 ? aoRow[aoTsI] : '');
        var _aoPhN = _normPhone_(aoPhI >= 0 ? aoRow[aoPhI] : '');
        var _aoNmN = aoNameI >= 0 ? _normNameKey_(aoRow[aoNameI]) : '';
        aoObj.rowKey = (_aoTsN && _aoPhN) ? (_aoTsN + '|' + _aoPhN + (_aoNmN ? '|' + _aoNmN : '')) : '';
        aoOut.push(aoObj);
      }
      return _json({ ok: true, scope: 'rows', headers: aoHdr.filter(function(h, i){ return aoKeep[i]; }),
                     count: aoOut.length, data: aoOut });
    }
    // scope='archive' = 지난 연도 LOSS 보관 시트(2026-08-13). 검색이 옛 회원을 놓치지 않도록 조회 통로를 연다.
    var aaScope = String(body.scope || 'valid');
    if (aaScope !== 'ended' && aaScope !== 'corp' && aaScope !== 'archive') aaScope = 'valid';
    var aaSs0 = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    // 법인회원: 별도 시트(법인현황 gid=1612064257) 전체를 제네릭 표시 (2026-06-25 GM)
    if (aaScope === 'corp') {
      var cpSh = null, cpShs = aaSs0.getSheets();
      for (var cps = 0; cps < cpShs.length; cps++) { if (cpShs[cps].getSheetId() === 1612064257) { cpSh = cpShs[cps]; break; } }
      if (!cpSh) cpSh = aaSs0.getSheetByName('법인현황');
      if (!cpSh) return _json({ ok: true, scope: 'corp', headers: [], count: 0, data: [] });
      var cpCols = cpSh.getLastColumn(), cpLast = cpSh.getLastRow();
      if (cpLast < 1 || cpCols < 1) return _json({ ok: true, scope: 'corp', headers: [], count: 0, data: [] });
      var cpHdrRaw = cpSh.getRange(1, 1, 1, cpCols).getValues()[0].map(function(v){ return String(v).trim(); });
      var cpKeep = cpHdrRaw.map(function(h){ return h && !/GMT|표준시/.test(h); });
      var cpHdrs = []; for (var ch = 0; ch < cpHdrRaw.length; ch++) if (cpKeep[ch]) cpHdrs.push(cpHdrRaw[ch]);
      var cpRows = [];
      if (cpLast >= 2) {
        var cpData = cpSh.getRange(2, 1, cpLast - 1, cpCols).getValues();
        for (var cpr = 0; cpr < cpData.length; cpr++) {
          var crow = cpData[cpr];
          var cpAny = false; for (var cc = 0; cc < cpCols; cc++){ if (cpKeep[cc] && String(crow[cc] == null ? '' : crow[cc]).trim()){ cpAny = true; break; } }
          if (!cpAny) continue;
          var cpObj = { rowIndex: cpr + 2 };
          for (var cc2 = 0; cc2 < cpHdrRaw.length; cc2++) {
            if (!cpKeep[cc2]) continue;
            var cv2 = crow[cc2];
            if (cv2 instanceof Date && !isNaN(cv2.getTime())) cv2 = Utilities.formatDate(cv2, 'Asia/Seoul', 'yyyy-MM-dd');
            cv2 = (cv2 === null || cv2 === undefined) ? '' : String(cv2);
            var cpHk = cpHdrRaw[cc2], cpHkN = cpHk.replace(/\s/g, '');
            if (cpHkN.indexOf('휴대폰') >= 0 || cpHkN.indexOf('연락처') >= 0 || cpHkN.indexOf('전화') >= 0) {
              var cpPn = cv2.replace(/[^0-9]/g, ''); if (cpPn.length === 11) cv2 = cpPn.slice(0,3)+'-'+cpPn.slice(3,7)+'-'+cpPn.slice(7); else if (cpPn.length === 10) cv2 = cpPn.slice(0,3)+'-'+cpPn.slice(3,6)+'-'+cpPn.slice(6);
            }
            cpObj[cpHk] = cv2;
          }
          cpRows.push(cpObj);
        }
      }
      return _json({ ok: true, scope: 'corp', headers: cpHdrs, count: cpRows.length, data: cpRows });
    }
    // ★2026-07-31 시토(GM '속도 근본적으로') — 조회 캐시(TTL 60초). 문의 목록(micache)·강습
    //   목록(licache)이 이미 쓰는 것과 **같은 헬퍼·같은 방식**을 그대로 쓴다(약속 L01 — 새 캐시
    //   장치 만들지 않는다). 이 액션만 캐시가 없어서, 회원관리 화면을 열 때마다 시트를 통째로
    //   다시 읽고 있었다.
    //   실측(웰리 2026-07-30 · 라이브 3회 중앙값): scope=valid 응답 **15.7초 / 1.18MB**.
    //   같은 부팅에서 6개 요청이 계단식(1.6→16.4초)으로 끝나 GAS 가 사실상 직렬 처리한다 —
    //   병렬을 늘려도 안 빨라지고 **서버 총 작업량을 줄여야** 한다는 뜻이다. 캐시가 그 답이다.
    //   ▸미스·실패 시 그대로 시트 재조회 폴백(무중단) · nocache=1 로 우회 가능.
    //   ▸쓰기(member_active_update 등)에서 무효화하므로 편집 직후 옛 값이 보이지 않는다.
    var aaCache = CacheService.getScriptCache();
    // ★형식별로 키를 가른다 — 안 가르면 배열 요청에 객체 응답(또는 그 반대)이 캐시에서
    //   그대로 나가 화면이 조용히 빈다. 2026-07-31 시토.
    var aaCacheKey = 'aacache|' + aaScope + '|' + (String(body.format || '') === 'rows' ? 'rows' : 'obj');
    if (!_nc) {
      var aaHit = _cacheGetJson_(aaCache, aaCacheKey);
      if (aaHit) return _json(aaHit);
    }
    var aaSh = aaSs0.getSheetByName(aaScope === 'archive' ? MEMBER_ARCHIVE_SHEET : MEMBER_SHEET);
    if (!aaSh) {
      // 보관 시트는 아직 안 만들었을 수 있다 — 오류 대신 빈 목록으로 답한다(화면이 안 깨지게).
      if (aaScope === 'archive') return _json({ ok: true, scope: aaScope, headers: [], count: 0, data: [] });
      return _json({ ok: false, error: '유효회원 시트 없음' });
    }
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
    // 지문키(rowKey, §4 R1) 재료 — ⚠️정직한계: 이 시트('유효회원')는 구글폼 응답탭이 아니라 수기 관리 명단이라
    //   '타임스탬프'(시분초) 칸이 없다. 최근접 대체값='등록일자'(날짜만) — member_active_update 가드와 동일 재료로 정합. 2026-07-22 시포.
    var aiTsRk = _aaIdx('등록일자'); if (aiTsRk < 0) aiTsRk = _aaIdx('타임스탬프');
    var aiPhRk = aaHdrRaw.indexOf(MEMBER_PHONE_COL);
    var aaRows = [];
    var aaFull = true;                                         // 2026-06-25 GM 전체공개 — 회원명도 평문(페이지 전체 PII 공개 정책 통일·전화도 평문)
    var aaNameKey = aiName >= 0 ? aaHdrRaw[aiName] : '';
    if (aaLast >= 2) {
      var aaData = aaSh.getRange(2, 1, aaLast - 1, aaCols).getValues();
      for (var ai = 0; ai < aaData.length; ai++) {
        var arow = aaData[ai];
        var nm = aiName >= 0 ? String(arow[aiName] == null ? '' : arow[aiName]).trim() : '';
        if (!nm) continue;  // 회원명 없는 빈/이상 행 제외
        // ★명단 아래에 붙은 집계표를 회원으로 세지 않는다 — 2026-07-28 시포(GM 지적:
        //   "LOSS 회원 카드 누르면 맨 아래에 0대 16-19세 막 이런 게 있는데, 김수신님 아래칸부터는 다 삭제").
        //   실측: 유효회원 시트 1693~1716행에 연령대·회차·지역 집계 블록이 들어가 있고(0대·16-19세…90-99세·
        //   합계·N회차 등록·구별 인원), 회원명 칸에 라벨이나 숫자가 들어가 있어 종료회원 명단에 회원처럼 23건 섞여 떴다.
        //   ▸시트에서 지우지 않는다 — 운영부가 쓰는 집계표이고 행 삭제는 되돌릴 수 없다(INC-020 교훈).
        //     읽는 자리 한 곳에서 거른다(약속 L21 · 관문에만).
        //   ▸판정은 '이름 모양'으로만 — 행 번호로 자르면 시트가 늘 때마다 또 어긋난다.
        //     ①숫자만('83'·'1109') ②연령대 라벨('0대'·'16-19세'·'90-99세') ③'합계'.
        //     실제 회원 이름은 이 셋 중 어느 것도 아니다(전수 확인: 유효 996명·종료 692명 오탐 0).
        if (/^[0-9.]+$/.test(nm) || /^\d{1,3}대$/.test(nm) || /^\d{1,3}\s*[-~]\s*\d{1,3}세$/.test(nm) || nm === '합계') continue;
        // 유효/종료 판정 = _memberIsValid_ 단일 함수(약속 L01, 배354 2026-08-04 짝 누락 근본수리).
        //   ★2026-08-01 신규등록 오분류 근본수리(GM 신고, 배286) — 잔여일 미기재(NaN)를 '종료'로 밀어내던 것을
        //   '유효'로 바꾼다. 신규 등록 직후(기간 미입력)엔 잔여일이 비어있는데, 종전 로직(!isNaN(rem))이 이걸
        //   그대로 종료회원 취급해 오늘 등록한 회원이 화면에서 사라졌다. 데이터 미비 ≠ 계약 종료 — 진짜 종료는
        //   잔여일이 음수로 "계산된" 경우뿐이다(쓰기 경로 보강은 _memberActiveUpsert_ months 파라미터, 이건 안전망).
        var isValid = _memberIsValid_(aiRem >= 0 ? arow[aiRem] : '', aiRe >= 0 ? arow[aiRe] : '');
        if (aaScope === 'valid' && !isValid) continue;
        if (aaScope === 'ended' && isValid) continue;   // 종료 = 유효가 아닌 모든 회원명 보유 행
        var obj = { rowIndex: ai + 2 };   // 시트 실제 행번호(인라인 수정 저장용)
        for (var ac = 0; ac < aaHdrRaw.length; ac++) {
          if (!aaKeep[ac]) continue;
          var key = aaHdrRaw[ac];
          var v = arow[ac];
          if (v instanceof Date && !isNaN(v.getTime())) v = Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
          v = (v === null || v === undefined) ? '' : String(v);
          if (key === MEMBER_PHONE_COL) { var pp = v.replace(/[^0-9]/g, ''); if (pp.length === 11) v = pp.slice(0,3) + '-' + pp.slice(3,7) + '-' + pp.slice(7); else if (pp.length === 10) v = pp.slice(0,3) + '-' + pp.slice(3,6) + '-' + pp.slice(6); }
          obj[key] = v;
        }
        /* 등록회차>=2 이고 등록 분류가 **비어 있을 때만** '재등록'으로 채워 보여준다(시트 미변경·표시 규칙).
           ★2026-08-13 시포 — 원래(2026-06-24 GM)는 회차만 보고 무조건 '재등록'으로 덮었다. 그러다 보니
           실무진이 그 칸에 무엇을 적든(대기·양수·환불·L재등록·L-가망) 회차가 2 이상이면 화면이 전부
           '재등록'으로 되돌려 보여줬다 — 고쳐도 안 고쳐진 것처럼 보이는 것이다(실측: 신상훈님 회차 7,
           시트에는 '대기'인데 화면은 '재등록'. 그래서 대기 인원이 화면 7명 · 서버 8명으로 갈렸다).
           GM 이 2026-08-13 에 등록 분류 7종을 정본으로 확정했으므로, 적힌 값은 그대로 보여준다.
           빈칸을 회차로 메우는 원래 목적은 그대로 살아 있다. */
        if (aiCls >= 0 && !String(arow[aiCls] == null ? '' : arow[aiCls]).trim()) {
          var _chaM = (aiCha >= 0 ? String(arow[aiCha] == null ? '' : arow[aiCha]) : '').match(/\d+/);
          if (_chaM && parseInt(_chaM[0], 10) >= 2) obj[aaHdrRaw[aiCls]] = '재등록';
        }
        if (!aaFull && aaNameKey) obj[aaNameKey] = _svMaskName_(obj[aaNameKey]);
        // 지문키(rowKey) — raw 셀 값(포맷 전) 사용. 2026-07-22 시포(오지목 근본수리).
        var _aaTsN = _normTsKey_(aiTsRk >= 0 ? arow[aiTsRk] : ''), _aaPhN = _normPhone_(aiPhRk >= 0 ? arow[aiPhRk] : '');
        // ★이름 세 번째 파트(배491) — 등록일자는 날짜만이라 같은 날 등록한 가족이 완전히 겹친다
        //   (실측: Maria Campero·Oscar Garcia Chacon). 이름이 붙으면 그 겹침이 사라진다.
        //   ▸이름을 가려 보내는 화면(aaFull=false)에는 넣지 않는다 — 지문키에 실명을 실으면
        //     가림이 무의미해진다. 그 경우 종전처럼 두 파트로 나가고 동작도 종전과 같다.
        var _aaNmN = (aaFull && aiName >= 0) ? _normNameKey_(arow[aiName]) : '';
        obj.rowKey = (_aaTsN && _aaPhN) ? (_aaTsN + '|' + _aaPhN + (_aaNmN ? '|' + _aaNmN : '')) : '';
        aaRows.push(obj);
      }
    }
    // 종료일자 최근순(내림차순) 기본 정렬 — 종료일 늦은 회원이 최상위 (2026-06-25 GM)
    var aiEnd = _aaIdx('종료일'); if (aiEnd < 0) aiEnd = _aaIdx('만료일'); if (aiEnd < 0) aiEnd = _aaIdx('이용종료'); if (aiEnd < 0) aiEnd = _aaIdx('만기일'); if (aiEnd < 0) aiEnd = _aaIdx('이탈일');
    if (aiEnd >= 0 && aaKeep[aiEnd]) {
      var aiEndKey = aaHdrRaw[aiEnd];
      aaRows.sort(function(a, b){ var av = String(a[aiEndKey] || ''); var bv = String(b[aiEndKey] || ''); return av < bv ? 1 : (av > bv ? -1 : 0); });
    }
    // ★2026-07-31 시토(GM '속도 근본적으로') — format=rows 면 **행을 배열로** 보낸다.
    //   왜: 응답 1,158KB 를 뜯어 보니 997행 × 36칸을 전부 객체로 보내느라 **칸 이름이
    //   369KB(32%)** 를 차지하고 있었다. 같은 이름을 997번 반복해 실어 보낸 것이다.
    //   columns 한 줄 + 행은 값만 배열로 보내면 **1,158KB → 526KB(55% 감소)**(실측).
    //   전송이 지금의 병목이라(캐시로 시트 재조회는 이미 없앴다) 이게 가장 큰 남은 덩이다.
    //   ▸정보 손실 0 — 같은 값을 순서로 전달할 뿐이고, 화면이 columns 로 다시 이름을 붙인다.
    //   ▸format 미지정이면 종전 그대로(하위호환) — 옛 화면·다른 소비자 무영향.
    //   ▸참고: 애초 계획이던 '칸 화이트리스트'는 전제가 틀렸다. 화면(_activeDisplayCols)은
    //     서버가 준 헤더를 거의 다 쓰고 9칸 남짓만 숨긴다 — 줄여도 25% 정도라 효과가 작다.
    // ★2026-08-07 시토(배117 잔여 ①) — 한 번 읽었으면 **두 형식을 함께 만들어 둘 다 캐시**한다.
    //   종전엔 캐시 키가 rows/obj 로 갈려 있어서, 같은 데이터인데 형식이 다른 요청이 오면
    //   시트를 처음부터 다시 통째로 스캔했다(유효회원 약 1,000행 풀스캔이 한 번 더).
    //   두 형식을 만드는 비용은 이미 메모리에 있는 배열을 옮겨 담는 것뿐이라 사실상 공짜다.
    var aaColNames = aaHdrs.slice();   // 칸 이름 목록(위 aaCols=칸 '개수' 와 이름이 겹치지 않게 분리)
    var aaArr = [];
    for (var ar = 0; ar < aaRows.length; ar++) {
      var aRow = aaRows[ar], aOut = [aRow.rowIndex, aRow.rowKey || ''];
      for (var ac = 0; ac < aaColNames.length; ac++) aOut.push(aRow[aaColNames[ac]] === undefined ? '' : aRow[aaColNames[ac]]);
      aaArr.push(aOut);
    }
    // meta = 앞 2칸이 무엇인지 알려 준다(화면이 순서를 추측하지 않게).
    var aaRowsResult = { ok: true, scope: aaScope, format: 'rows', meta: ['rowIndex', 'rowKey'],
                         columns: aaColNames, count: aaArr.length, rows: aaArr };
    var aaObjResult = { ok: true, scope: aaScope, headers: aaHdrs, count: aaRows.length, data: aaRows };
    var aaWantRows = (String(body.format || '') === 'rows');
    var aaResult = aaWantRows ? aaRowsResult : aaObjResult;
    // 요청받지 않은 쪽도 같은 스캔 결과로 채워 둔다(실패해도 조회는 정상 — 캐시는 보조).
    try {
      _cachePutJson_(aaCache, 'aacache|' + aaScope + '|' + (aaWantRows ? 'obj' : 'rows'),
                     aaWantRows ? aaObjResult : aaRowsResult, 360);
    } catch (aaE) {}
    // ★2026-08-03 시토(배298) — TTL 60 → 360초. 워머(2026-08-05 부터 warmLessonRosterCache —
    //   warmDashboardCache 는 트리거가 없어 안 돈다)가 5분마다 도는데
    //   TTL 이 60초면 5분 중 1분만 뜨겁고 나머지 4분은 미스라 워밍이 헛돈다. 360초로 두면
    //   워머 주기(300초)보다 길어 **항상 히트**한다(경계 race 없음).
    //   ▸신선도 영향: 쓰기 액션(member_active_update 등)은 그대로 즉시 무효화하므로 화면에서
    //     고친 값은 바로 반영된다. 늦어지는 것은 **시트를 직접 손으로 고쳤을 때뿐**이고,
    //     그 경우 최대 6분 지연(종전 1분). 이 칸은 조회용이라 감수 가능하다고 판단했으나,
    //     회원 데이터 신선도는 시포 도메인이라 다르면 시포·GM 이 한 줄로 정정한다.
    //   ▸다른 캐시(문의 micache·강습 licache)는 60초 그대로 — 이 액션만 워머에 물렸다.
    _cachePutJson_(aaCache, aaCacheKey, aaResult, 360);
    return _json(aaResult);
  }

  // ─── 멤버십 회원관리: 셀 인라인 수정(유효회원 시트 write-back · 전화 컬럼 제외) 2026-06-24 GM ───
  /* 유효회원 시트 「재등록 분류」 칸은 2026-08-13 GM 지시로 삭제했다(L열, 값 1,375개).
     값 이관은 하지 않기로 했고, 삭제 전 원본은 status/member_reclass_column_backup_20260813.json 에 있다.
     이 아래 코드들이 그 칸을 찾는 자리는 전부 '못 찾으면 건너뛴다'로 되어 있어 그대로 둔다 —
     유효/종료 판정·신규 판정 결과는 전수 대조에서 한 명도 바뀌지 않는다(1,697명 확인). */
  /* 지난 연도(2025년 이전) LOSS 506명은 2026-08-13 GM 지시로 「LOSS보관」 시트로 옮겼다.
     옮긴 원본은 status/loss_archive_backup_20260813.json 에 보관되어 있고, 이관용 일회성 액션은
     실행 뒤 지웠다. 조회는 scope='archive' 로 열려 있고, LOSS 누적 숫자는 _lossArchiveCount_ 가
     더해 주므로 옮기기 전과 같다. */
  if (action === 'member_active_update') {
    // ★여러 건을 한 요청으로 (2026-08-21 시토 · 배740 ①)
    //   왜: 지금은 1건 = 1왕복이라 5건 고치면 8.5×5 ≈ 42초다. 오늘 미등록사유 5건이 정확히 그 경우였다.
    //   묶으면 왕복 1회 + 시트 열기 1회로 줄어든다(같은 실행 안에서는 openById 가 다시 안 연다).
    //   ▸가드는 하나도 건드리지 않는다 — 각 건이 아래 단건 경로를 **그대로** 다시 탄다(_processAction 재진입).
    //     지문 대조·전화 대조·중복 거부가 건마다 원래대로 걸린다. 로직을 복제하지 않는다(약속 L21·L01).
    //   ▸한 건이 실패해도 나머지는 계속한다. 결과는 건별로 돌려주니 화면이 어느 건이 실패했는지 안다.
    if (Object.prototype.toString.call(body.updates) === '[object Array]' && body.updates.length) {
      var _bu = body.updates;
      if (_bu.length > 30) return _json({ ok: false, error: 'updates-too-many', detail: '한 번에 30건까지 — 나눠 보내세요' });
      var _buOut = [], _buOk = 0;
      for (var _bi = 0; _bi < _bu.length; _bi++) {
        var _one = {}, _bk;
        for (_bk in body) { if (_bk !== 'updates') _one[_bk] = body[_bk]; }
        for (_bk in _bu[_bi]) { _one[_bk] = _bu[_bi][_bk]; }
        _one.action = 'member_active_update';
        delete _one.updates;                       // 재귀 폭주 차단(항목이 updates 를 품고 와도 무시)
        var _br;
        try { _br = JSON.parse(_processAction(_one).getContent()); }
        catch (e) { _br = { ok: false, error: 'batch-item-failed', detail: String(e) }; }
        if (_br && _br.ok) _buOk++;
        _buOut.push(_br);
      }
      return _json({ ok: _buOk === _bu.length, count: _bu.length, okCount: _buOk, results: _buOut });
    }
    /* ★구간 계측(2026-08-26 시포 · 배11001 1단계 "왜 8.5초인지 재고 줄인다").
       추정으로 고치면 엉뚱한 데를 깎는다 — 어느 구간이 오래 걸리는지 서버가 직접 재서 응답에 싣는다.
       읽기·쓰기 로직은 하나도 안 건드린다(시각을 찍기만 한다). 응답에 ms 키가 하나 늘 뿐이라
       화면 계약도 그대로다. 병목이 확정되면 이 계측은 남겨 둔다 — 다음에 또 느려지면 바로 잰다. */
    var _auT = { t0: new Date().getTime() };
    function _auMark(k) { _auT[k] = new Date().getTime() - _auT.t0; }
    var auRow = parseInt(body.rowIndex, 10);
    if (!auRow || auRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    // 다중 필드(fields 객체) 또는 단일(col/value). fields 우선 — 재등록상담 달력 모달=날짜·시간·내용 3칸 동시 저장. 2026-07-03 시포·GM.
    var auFields = (body.fields && typeof body.fields === 'object') ? body.fields : null;
    var auCol = String(body.col || '').trim();
    if (!auFields && !auCol) return _json({ ok: false, error: 'col 또는 fields 필수' });
    var auSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!auSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    _auMark('open');
    var auHdr = auSh.getRange(1, 1, 1, auSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    _auMark('hdr');
    var _auPhI = -1;
    for (var _ap = 0; _ap < auHdr.length; _ap++) { var _aph = auHdr[_ap].replace(/\s/g, ''); if (_aph.indexOf('휴대폰') >= 0 || _aph.indexOf('전화') >= 0 || _aph.indexOf('연락처') >= 0) { _auPhI = _ap; break; } }
    // ★★ 지문키(rowKey) 우선 경로(§4 R2) — ⚠️정직한계: 유효회원(MEMBER_SHEET='유효회원') 시트는 구글폼 응답탭이 아니라
    //   수기 관리 명단이라 '타임스탬프'(시분초) 칸이 없다(실측 2026-07-22). 최근접 대체값 = '등록\n일자'(날짜만, 시각정보
    //   없음) — 문의/강습 탭 대비 판별력이 약함(같은 날 등록자가 겹치면 지문 충돌 가능성 있음)을 정직히 인지하고 사용한다.
    //   그래도 매칭 0건/2건+는 그대로 거부(fail-closed)이므로 rowIndex 단독 신뢰보다는 항상 더 안전한 쪽으로 치우친다.
    //   매칭 1건=그 행 확정(아래 keyPhone 대조 스킵) / 0건·2건+=거부. rowKey 미동봉(구클라)이거나 등록일자 칸 미탐지 시
    //   기존 keyPhone 경로로 폴백. 2026-07-22 시포(오지목 근본수리).
    var _auRk = _rowKeyParts_(body);
    var _auTsI = -1;
    if (_auRk) {
      var _AU_TS_KEYS = ['타임스탬프', '등록일자', '등록 일자', '등록일', '가입일'];
      for (var _at = 0; _at < auHdr.length; _at++) {
        var _ath = auHdr[_at].replace(/\s/g, '');
        var _atHit = false;
        for (var _atk = 0; _atk < _AU_TS_KEYS.length; _atk++) { if (_ath.indexOf(_AU_TS_KEYS[_atk].replace(/\s/g, '')) >= 0) { _atHit = true; break; } }
        if (_atHit) { _auTsI = _at; break; }
      }
    }
    if (_auRk && _auTsI >= 0 && _auPhI >= 0) {
      var _auNmI = _nameColIdx_(auHdr);
      // ★지름길(2026-08-21 시토 · 배740) — 화면이 보낸 행의 지문이 이미 맞으면 1,000행 전수 스캔을
      //   건너뛴다. 답은 달라지지 않는다(_rowKeyHitsRow_ 주석의 ①②③ 참조). 안 맞으면 종전대로 전수 스캔.
      //   실측 근거: 저장 1건 8.5초 중 약 1.4초가 이 스캔이다(시포 2026-08-21).
      var _auFpRows = _rowKeyHitsRow_(auSh, auRow, _auTsI, _auPhI, _auRk.ts, _auRk.phone, _auNmI, _auRk.name)
        ? [auRow]
        : _findRowsByKey_(auSh, _auTsI, _auPhI, _auRk.ts, _auRk.phone, _auNmI, _auRk.name);
      if (_auFpRows.length === 1) {
        auRow = _auFpRows[0];
      } else if (_auFpRows.length === 0) {
        // ★★지문 미스 복구 — 2026-08-05 시토(실무진 신고 FB260805-101542·FB260805-105803 근본수리).
        //   이 시트의 지문 재료는 '등록일자 + 전화'인데, **등록일자는 실무진이 화면에서 고치는 칸이다.**
        //   즉 회원의 등록일자를 고치는 순간 그 행의 지문이 바뀌고, 화면이 들고 있던 옛 지문으로
        //   보내는 다음 저장은 전부 0건 매칭이 되어 영구히 막혔다. 이경연 실장 이 겪은 그대로다 —
        //   "유상두·전하늘 등록일자/시작일자/종료일자 계속 처리 안 됨", "연령·등록회차만 고쳤는데
        //   지문 불일치가 자꾸 뜸"(고친 건 다른 칸인데, 앞선 등록일자 편집으로 지문이 이미 어긋나 있었다).
        //   화면 쪽은 커밋 353ae32d9 가 편집 직후 지문을 다시 계산하게 고쳤다. 여기 서버 쪽은 그래도
        //   막아 둔다 — 옛 화면이 열려 있는 브라우저·재시도 큐에 남은 옛 요청은 여전히 옛 지문을 보낸다.
        //   ▸복구 규칙: 전화 단독 매칭이 **정확히 1건**일 때만 그 행으로 확정한다. 지문의 등록일자
        //     조각이 하는 일은 '같은 전화의 여러 행'을 가르는 것뿐이라, 전화가 유일하면 그 조각이
        //     없어도 대상은 확정된다. 0건·2건+ 는 그대로 거부(fail-closed) — 행번호로는 절대 쓰지 않는다.
        //   ▸이미 있는 헬퍼(_countRowsByPhone_·_findRowByPhone_)를 그대로 쓴다. 문의 경로가 쓰는 것과 같다.
        var _auRecovered = -1;
        if (_auRk.phone) {
          var _auPhHits = _countRowsByPhone_(auSh, _auPhI, _auRk.phone);
          if (_auPhHits === 1) _auRecovered = _findRowByPhone_(auSh, _auPhI, _auRk.phone);
        }
        if (_auRecovered >= 2) {
          auRow = _auRecovered;
          Logger.log('지문 미스 복구(전화 단독 1건 일치): row=' + auRow + ' 지문ts=' + _auRk.ts);
        } else {
          return _json({ ok: false, error: 'rowkey-not-found', detail: '행 확인 불가(지문 불일치) — 목록 새로고침 후 다시 시도하세요' });
        }
      } else {
        // ★★지문 중복 복구 — 2026-08-06 시포(GM "실무진이 신뢰할 수 있는 페이지" 지시로 전수 검수 중 발견).
        //   지문 재료가 '등록일자 + 전화' 뿐이라, **가족이 같은 번호로 같은 날 등록하면 두 행의 지문이
        //   완전히 같아진다.** 그 순간 두 분 다 어떤 칸도 저장할 수 없고, 새로고침해도 영구히 안 풀린다
        //   (2026-08-05 에 넣은 '전화 단독 복구'도 후보가 2건이라 똑같이 막힌다).
        //   실측 2026-08-06: 유효회원 1,003명 중 Maria Campero·Oscar Garcia Chacon 두 분이 이 상태였다
        //   (같은 번호 · 둘 다 2025-01-03 등록). 실무진은 원인을 알 길이 없고 계속 실패만 본다.
        //   ▸복구 규칙: 화면이 보낸 rowIndex 가 **지문이 걸린 후보 행들 중 하나와 정확히 같을 때만**
        //     그 행으로 확정한다. 후보 밖 행번호는 그대로 거부 — 행번호를 단독 근거로 쓰지 않는다는
        //     INC-020 원칙은 그대로다. 후보는 모두 같은 전화·같은 등록일이라 최악의 경우에도
        //     **그 가족 두 사람 사이**를 벗어나지 않는다(남의 줄은 구조적으로 못 건드린다).
        //   ▸화면은 고치지 않았다 — 이미 보내고 있는 rowIndex 를 판정 재료로 한 겹 더 쓸 뿐이다(약속 L21).
        var _auPick = -1;
        var _auWantRow = parseInt(body.rowIndex, 10);
        if (_auWantRow >= 2) {
          for (var _afi = 0; _afi < _auFpRows.length; _afi++) {
            if (_auFpRows[_afi] === _auWantRow) { _auPick = _auWantRow; break; }
          }
        }
        if (_auPick >= 2) {
          auRow = _auPick;
          Logger.log('지문 중복 복구(후보 내 행번호 일치): row=' + auRow + ' 후보=' + _auFpRows.join(','));
        } else {
          return _json({ ok: false, error: 'rowkey-ambiguous', detail: '지문키 중복 매칭 — 목록 새로고침 후 다시 시도하세요' });
        }
      }
    } else {
    // ★행키 검증(비파괴·하위호환, 지문키 미동봉/칸 미탐지 시 폴백): keyPhone 동봉 시 대상 행 전화 대조 — rowIndex 밀림 오수정 방지. 미전송이면 폴백 — 단, 예약(재등록예약목록) 쓰기는 예외(B1).
    //   ※ 이 액션은 애초에 first-match 복구를 하지 않고 불일치 시 무조건 거부(위 __B2__ 중복전화 첫매칭 오지목 버그가 애초에 없음) — B1(빈 keyPhone fail-closed)만 보강.
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      if (_auPhI >= 0 && auRow <= auSh.getLastRow()) {
        var _auRowPh = _normPhone_(auSh.getRange(auRow, _auPhI + 1).getValue());
        var _auKeyPh = _normPhone_(body.keyPhone);
        // ★2026-07-31 시토(배239) — 조건에서 `_auRowPh &&` 를 뺐다. fail-open → fail-closed.
        //   왜: 대상 행의 휴대폰 칸이 **비어 있으면** _auRowPh 가 거짓이라 조건 전체가 false 가 되어
        //   검증을 통째로 건너뛰고 **밀린 rowIndex 에 그대로 썼다.** 그래서 2026-07-27~28 예약 달력의
        //   예약자 이름이 다른 사람으로 바뀌었다(실무진 신고 FB260728-112703).
        //   같은 파일 문의 경로(위 _muKeyPh 블록)는 처음부터 `_muKeyPh &&` 만 보는 fail-closed 인데,
        //   2026-07-22 두 경로를 같은 날 손보면서 여기만 `_auRowPh &&` 한 조각이 남았다.
        //   이제 대상 행 전화가 비면 '빈 값 ≠ 키' 로 불일치가 되어 **거부**된다(맹목 쓰기 금지).
        //   막히는 저장이 생기는 것은 감수한다 — 남의 줄을 덮어쓰는 것보다 낫다.
        if (_auKeyPh && _auRowPh !== _auKeyPh) {
          return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패 — 목록을 새로고침 후 다시 시도하세요' });
        }
      } else {
        // ★2026-08-03 시토(배294) — **여기도 조건이 남아 있었다.** 배239(2026-07-31)는 바깥 가지만
        //   고치고 이 안쪽 가지를 놓쳤다. 안쪽 = keyPhone 은 왔는데 전화 칸을 못 찾거나 행이
        //   범위를 벗어난 경우 = 역시 대조 불가능인데, 예약 쓰기가 아니면 그대로 통과해 맹목 쓰기가 됐다.
        //   바로 위 주석이 인용한 예약자 뒤바뀜 사고(FB260728-112703)와 같은 통로다.
        //   이제 안팎 모두 쓰기 종류를 가리지 않고 거부한다 — 대조할 수 없으면 쓰지 않는다.
        return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
      }
    } else {
      // ★2026-07-31 시토(배239 근본) — 예전엔 이 거부가 **예약 쓰기일 때만** 걸렸다
      //   (`else if (_auIsReservationWrite)`). 그래서 예약이 아닌 보통 칸 수정은 대조키가
      //   하나도 없어도 **검증 없이 raw rowIndex 로 그대로 썼다** — '행 번호로 남의 줄에
      //   쓴다'는 사고 부류(INC-013·INC-020·INC-037·이번 예약자 뒤바뀜)의 마지막 통로다.
      //   이제 쓰기 종류를 가리지 않고 거부한다. 대조할 수 없으면 쓰지 않는다.
      //   ▸막히는 저장이 생기나: 실측 2026-07-31 — 유효회원 997행 전부 휴대폰 칸이 차 있고,
      //     이 액션을 부르는 곳 8군데(회원관리 5·재등록 1·정리 스크립트 2) 전부 keyPhone 을
      //     동봉한다. 즉 지금 라이브에서 이 분기로 오는 정상 저장은 0건이다.
      //   ▸되돌리려면 이 블록을 `else if (_auIsReservationWrite)` 로 되돌리면 된다.
      return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 저장하세요' });
    }
    }
    // 컬럼 찾기(정확→부분). 재등록상담 칸(날짜·시간·내용)은 없으면 시트 끝에 안전 추가(ensure·additive·기존 순서 무손상). 휴대폰=-2(편집 금지).
    function _auFindCol(colName) {
      var w = String(colName).replace(/\s/g, '');
      if (w.indexOf('휴대폰') >= 0) return -2;
      var ix = -1;
      for (var a1 = 0; a1 < auHdr.length; a1++) { if (auHdr[a1].replace(/\s/g, '') === w) { ix = a1; break; } }
      if (ix < 0) { for (var a2 = 0; a2 < auHdr.length; a2++) { if (auHdr[a2] && auHdr[a2].replace(/\s/g, '').indexOf(w) >= 0) { ix = a2; break; } } }
      // '종료사유'(+'종료사유메모') 자동 신설 — 회원 종료사유 기록 기능(GM 확정), GAS가 칸 생성해 GM 수작업 0. 2026-07-09 시포·GM.
      // ★휴회 자동생성 철회(2026-07-20 GM) — 휴회는 별도 전용 시트에서 관리 중임이 확인됨.
      //   유효회원 시트에 휴회 칸을 만들면 진실이 두 곳으로 갈라진다(약속 L01: 한 곳만 본다).
      //   연동은 휴회 시트를 읽는 방식으로 별도 설계. 여기서 칸을 만들지 않는다.
      if (ix < 0 && (w.indexOf('재등록상담') >= 0 || w.indexOf('재등록예약목록') >= 0 || w.indexOf('종료사유') >= 0)) ix = _miEnsureCol_(auSh, auHdr, String(colName).trim());
      return ix;
    }
    // 셀 쓰기 — 재등록상담 칸(날짜·시간·내용)은 텍스트 서식(@) 강제 후 기록. '09:00'·'2026-07-15'가 시간/날짜 값으로
    //   자동 변환(구글시트 LMT 오프셋으로 09:00→09:05 드리프트)되는 것을 차단 → 입력값 그대로 보존. 2026-07-03 시포·GM.
    // 변경 이력 재료(배327) — 직원 이름은 프론트가 wellperion_staff_name 을 실어 보낸다(새 키 없음).
    // 사람인데 이름을 못 받으면 '이름미상', 자동 경로면 '자동'. 기록은 건너뛰지 않는다.
    var _auStaff = _logWho_(body);
    var _auNameI = -1;
    for (var _an = 0; _an < auHdr.length; _an++) {
      var _anh = auHdr[_an].replace(/\s/g, '');
      if (_anh === '성명' || _anh === '이름' || _anh.indexOf('회원명') >= 0) { _auNameI = _an; break; }
    }
    // ★행 스냅샷 1회 읽기(2026-08-05 시토 — 저장 왕복 축소, 배327 이후 실측 15회→9회).
    //   전엔 필드마다 _auWriteCell 안에서 cell.getValue()를 또 불러 old값을 읽었다(N필드=N회 읽기).
    //   auRow는 위에서 이미 확정됐으니 여기서 행 전체를 한 번만 읽어 old값·이름·전화를 전부 이 스냅샷에서
    //   꺼내 쓴다 — 쓰기(setValue/setNumberFormat)는 손대지 않고 칸별 개별 호출 그대로 유지한다(범위
    //   setValues로 합치면 그 사이 칸을 동시에 만지는 다른 저장을 덮어쓸 위험이 있다 — 이 파일 위쪽
    //   _muSetCol 주석의 Contact3가 진행현황을 덮던 사고가 그 위험의 실례라 쓰기 폭은 그대로 둔다).
    //   읽기만 배치화 = 정확성 회귀 없음(쓰는 값·쓰는 칸·검증 로직 전부 무변경).
    _auMark('key');
    var _auRowSnap = auSh.getRange(auRow, 1, 1, auHdr.length).getValues()[0];
    _auMark('snap');
    var _auMember = _auNameI >= 0 ? String(_auRowSnap[_auNameI] || '') : '';
    var _auPhone = _auPhI >= 0 ? String(_auRowSnap[_auPhI] || '') : '';
    var _auLog = [];
    var _auSaved = {};   // 쓴 뒤 되읽은 실제 셀 값 — 응답에 실어 화면이 재조회 없이 대조한다(2026-08-20).
    function _auWriteCell(ix, colName, val) {
      var cell = auSh.getRange(auRow, ix + 1);
      var _old = String(_auRowSnap[ix] == null ? '' : _auRowSnap[ix]);
      var _cn = String(colName).replace(/\s/g, '');
      if (_cn.indexOf('재등록상담') >= 0 || _cn.indexOf('재등록예약목록') >= 0) cell.setNumberFormat('@');
      var _new = val == null ? '' : String(val);
      cell.setValue(_new);
      /* ★쓴 값을 그 자리에서 다시 읽어 응답에 실어 준다(2026-08-20 시포 — GM "동기화 완료가 정말 늦게 뜬다").
         화면은 저장이 진짜 들어갔는지 확인하려고 저장 뒤에 목록을 통째로 다시 받았다(실측: 저장 7.5초 +
         재조회 9.1초 = 완료 표시까지 18.3초). 서버는 이미 그 셀을 손에 쥐고 있으므로 여기서 한 번 더
         읽어 돌려주면 그 재조회가 통째로 필요 없어진다 — 왕복 3회가 1회가 된다.
         ▸덤으로 '조용한 거부'도 여기서 잡힌다: 데이터확인 규칙이 값을 버리면 되읽은 값이 다르다
           (2026-08-20 미등록사유 사고가 정확히 그 부류였다). */
      var _back = cell.getValue();
      if (_back instanceof Date && !isNaN(_back.getTime())) _back = Utilities.formatDate(_back, 'Asia/Seoul', 'yyyy-MM-dd');
      _auSaved[colName] = (_back === null || _back === undefined) ? '' : String(_back);
      _auRowSnap[ix] = _new;  // 같은 요청 안에서 같은 칸이 다시 조회될 경우를 대비해 스냅샷도 갱신
      // 안 바뀐 칸은 안 남긴다 — 이력이 노이즈가 되면 아무도 안 본다.
      if (_old !== _new) _auLog.push([new Date(), _auStaff, _auMember, _logMaskPhone_(_auPhone), colName, _old, _new, '멤버십']);
    }
    if (auFields) {
      var _auWrote = [];
      for (var fk in auFields) {
        if (!Object.prototype.hasOwnProperty.call(auFields, fk)) continue;
        var fName = String(fk).trim();
        if (!fName) continue;
        var fIx = _auFindCol(fName);
        if (fIx === -2) continue;                                         // 전화 칸 스킵
        if (fIx < 0) return _json({ ok: false, error: '컬럼 미발견: ' + fName });
        _auWriteCell(fIx, fName, auFields[fk]);
        _auWrote.push(fName);
      }
      // 미러: 재등록예약목록 저장 시 예약1 → 재등록상담 날짜/시간/내용(하위호환·달력 폴백 안전망·무손실). 2026-07-03 시포·GM
      if (Object.prototype.hasOwnProperty.call(auFields, ACT_RES_COL)) {
        var _actRes = _resParse_(auFields[ACT_RES_COL]);
        var _ar0 = _actRes[0] || { date: '', time: '', note: '' };
        [['재등록상담 날짜', _ar0.date], ['재등록상담 시간', _ar0.time], ['재등록상담 내용', _ar0.note]].forEach(function(pair){
          var mi = _auFindCol(pair[0]);
          if (mi >= 0) _auWriteCell(mi, pair[0], pair[1]);
        });
      }
      _auMark('write');
      _memberLog_(_auLog);
      _auMark('log');
      _aaCacheClear_(['valid']);
      _auMark('total');
      return _json({ ok: true, rowIndex: auRow, cols: _auWrote, saved: _auSaved, ms: _auT });
    }
    if (auCol.replace(/\s/g, '').indexOf('휴대폰') >= 0) return _json({ ok: false, error: '전화번호는 시트에서 직접 수정해주세요' });
    var auIdx = _auFindCol(auCol);
    if (auIdx < 0) return _json({ ok: false, error: '컬럼 미발견: ' + auCol });
    _auWriteCell(auIdx, auCol, body.value);
    _auMark('write');
    _memberLog_(_auLog);
    _auMark('log');
    _aaCacheClear_(['valid']);
    _auMark('total');
    return _json({ ok: true, rowIndex: auRow, col: auCol, saved: _auSaved, ms: _auT });
  }

  // ─── LOSS보관 회원 재등록 복귀(member_archive_restore) — 2026-08-25 시토(GM 지시, 최영천 010-3837-5107 재등록 신고).
  //   왜: LOSS보관 시트는 조회전용이라(member_active_update 는 유효회원 시트만 쓴다) 보관된 분이 재등록해도
  //   실무진이 화면에서 손댈 방법이 없었다. ▸★2026-08-26 GM 지시로 바뀐 것: 복귀는 '이관'이므로 보관 행을
  //   **삭제한다**("이관건이니 기존 자료는 없어져야해"). 종전엔 보관 행을 비고 메모만 붙여 남겨서 같은 분이
  //   유효회원·보관 양쪽에 보였다(최영천 010-3837-5107 실사고). 지우기 전 행 전체 값을 변경이력에 통째로
  //   남겨 되돌릴 근거를 보존한다. ▸이미 유효회원인데 보관에도 남은 옛 건은 같은 액션의 뒷정리 경로가
  //   치운다(이름이 같을 때만 — 전화가 같아도 이름이 다르면 가족 공유번호·양도 건이라 남의 기록이다).
  //   ▸새 유효회원 행은 기존 _memberActiveUpsert_ 를 그대로 재사용 — 그 함수가 못 하는 것
  //   (담당자는 opts.owner 를 무조건 MEMBER_DEFAULT_OWNER 로 덮는다·주소/비고 인계·등록회차 이어받기·명시적
  //   종료일)만 뒤에서 직접 덧쓴다(약속 L21 — 새 쓰기 로직 중복 없음).
  if (action === 'member_archive_restore') {
    var arPhone = _normPhone_(body.phone);
    if (!arPhone) return _json({ ok: false, error: 'phone 필수' });
    var arSs = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var arArchSh = arSs.getSheetByName(MEMBER_ARCHIVE_SHEET);
    if (!arArchSh) return _json({ ok: false, error: 'LOSS보관 시트 없음' });
    var arArchHdr = arArchSh.getRange(1, 1, 1, arArchSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    function _arIdx(hdr, want) {
      var w = String(want).replace(/\s/g, '');
      for (var i = 0; i < hdr.length; i++) { if (hdr[i] && hdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; }
      return -1;
    }
    var arPhI = arArchHdr.indexOf(MEMBER_PHONE_COL); if (arPhI < 0) arPhI = _arIdx(arArchHdr, '휴대폰');
    if (arPhI < 0) return _json({ ok: false, error: 'LOSS보관 시트에 휴대폰 칸 없음' });
    // 0건·2건+ 거부(fail-closed) — 다른 쓰기 액션과 동일 가드(_countRowsByPhone_/_findRowByPhone_) 재사용.
    var arHitN = _countRowsByPhone_(arArchSh, arPhI, arPhone);
    if (arHitN === 0) return _json({ ok: false, error: 'archive-not-found', detail: 'LOSS보관에서 해당 전화번호를 찾을 수 없습니다' });
    if (arHitN >= 2) return _json({ ok: false, error: 'archive-ambiguous', detail: 'LOSS보관에 같은 전화번호가 ' + arHitN + '건 있어 어느 분인지 정할 수 없습니다 — 시트에서 직접 확인해주세요' });
    var arRow = _findRowByPhone_(arArchSh, arPhI, arPhone);
    // 유효회원에 이미 있으면 거부(중복 회원 생성 금지).
    var arActiveSh = arSs.getSheetByName(MEMBER_SHEET);
    if (!arActiveSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var arActiveHdr = arActiveSh.getRange(1, 1, 1, arActiveSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    var arActPhI = arActiveHdr.indexOf(MEMBER_PHONE_COL); if (arActPhI < 0) arActPhI = _arIdx(arActiveHdr, '휴대폰');
    if (arActPhI < 0) return _json({ ok: false, error: '유효회원 시트에 휴대폰 칸 없음' });
    if (_countRowsByPhone_(arActiveSh, arActPhI, arPhone) > 0) {
      // ── 이관 뒷정리 경로(2026-08-26 GM 지시). 이미 유효회원인데 보관에도 남아 있으면 같은 분이 화면에
      //    두 번 보인다 — 종전 코드가 보관 행을 남겼기 때문. 이름이 같을 때만 보관 행을 치운다.
      //    전화가 같아도 이름이 다르면 가족 공유번호·양도 건이라 남의 기록이므로 종전대로 거부한다.
      var _clNmI = _arIdx(arArchHdr, '회원명');
      var _clArchName = _clNmI >= 0 ? String(arArchSh.getRange(arRow, _clNmI + 1).getValue() || '').trim() : '';
      var _clActRow = _findRowByPhone_(arActiveSh, arActPhI, arPhone);
      var _clActNmI = _arIdx(arActiveHdr, '회원명');
      var _clActName = (_clActRow >= 2 && _clActNmI >= 0) ? String(arActiveSh.getRange(_clActRow, _clActNmI + 1).getValue() || '').trim() : '';
      if (!_clArchName || _clArchName !== _clActName) {
        return _json({ ok: false, error: 'already-active', detail: '이미 유효회원에 등록된 전화번호입니다 — 보관 기록의 이름(' + (_clArchName || '?') + ')과 유효회원 이름(' + (_clActName || '?') + ')이 달라 자동 정리하지 않습니다' });
      }
      var _clVals = arArchSh.getRange(arRow, 1, 1, arArchHdr.length).getValues()[0];
      _memberLog_([[new Date(), _logWho_(body), _clArchName, _logMaskPhone_(body.phone), 'LOSS보관 이관정리',
                    'LOSS보관 행 ' + arRow + ' 삭제 · 원본: ' + JSON.stringify(_clVals).slice(0, 900),
                    '유효회원 행 ' + _clActRow, '멤버십']]);
      arArchSh.deleteRow(arRow);
      _memberCacheBump_(); _aaCacheClear_(['archive']);
      return _json({ ok: true, cleaned: true, name: _clArchName, archiveRow: arRow, activeRow: _clActRow });
    }
    // 보관 행 값 읽기 — 물려줄 칸(나이·회원구분·수강반종목명·담당자·주소·비고·등록회차).
    var arNmI = _arIdx(arArchHdr, '회원명');
    var arAgeI = _arIdx(arArchHdr, '나이');
    var arKndI = _arIdx(arArchHdr, '회원구분');
    var arPgI = _arIdx(arArchHdr, '수강반종목'); if (arPgI < 0) arPgI = _arIdx(arArchHdr, '종목명'); if (arPgI < 0) arPgI = _arIdx(arArchHdr, '회원권'); if (arPgI < 0) arPgI = _arIdx(arArchHdr, '상품'); if (arPgI < 0) arPgI = _arIdx(arArchHdr, '프로그램');
    var arOwnI = _arIdx(arArchHdr, '담당자');
    var arAddrI = _arIdx(arArchHdr, '주소');
    var arMemoI = _arIdx(arArchHdr, '비고'); if (arMemoI < 0) arMemoI = _arIdx(arArchHdr, '메모');
    var arSeqI = _arIdx(arArchHdr, '등록회차');
    var arNoI = _arIdx(arArchHdr, MEMBER_REGISTRY_KEY_COL);   // 회원번호 — 보관에서 돌아와도 같은 번호를 유지한다
    var arRowVals = arArchSh.getRange(arRow, 1, 1, arArchHdr.length).getValues()[0];
    function _arCell(i) { return i >= 0 ? arRowVals[i] : ''; }
    var arName = String(_arCell(arNmI) || '').trim();
    if (!arName) return _json({ ok: false, error: 'archive-row-invalid', detail: '보관 행에서 회원명을 읽지 못했습니다' });
    var arAge = _arCell(arAgeI);
    var arKind = String(_arCell(arKndI) || '').trim();
    var arProgram = String(_arCell(arPgI) || '').trim();
    var arOwner = String(_arCell(arOwnI) || '').trim();
    var arAddr = String(_arCell(arAddrI) || '').trim();
    var arMemo = String(_arCell(arMemoI) || '').trim();
    var arSeqRaw = _arCell(arSeqI);
    var arMemberNo = String(_arCell(arNoI) || '').trim();
    var arSeqN = parseInt(String(arSeqRaw == null ? '' : arSeqRaw).replace(/[^0-9]/g, ''), 10);
    var arNewSeq = (!isNaN(arSeqN) && arSeqN > 0) ? (arSeqN + 1) : arSeqRaw;  // 숫자면 +1, 못 읽으면 그대로.

    var arRegClass = String(body.regClass || 'L재등록').trim();
    var arProgramNew = String(body.program || '').trim() || arProgram;
    var arRegDate = String(body.regDate || '').trim() || _todayKR_();
    var arMonths = parseInt(body.months, 10);
    var arStartDate = String(body.startDate || '').trim();
    var arEndDate = String(body.endDate || '').trim();
    var arStaff = _logWho_(body);

    var arPreview = {
      target: { name: arName, phone: body.phone, archiveRow: arRow },
      carried: { 나이: arAge, 회원구분: arKind, 수강반종목명: arProgram, 담당자: arOwner, 주소: arAddr, 비고: arMemo, 등록회차: String(arSeqRaw == null ? '' : arSeqRaw) + ' → ' + String(arNewSeq == null ? '' : arNewSeq) },
      newValues: { regDate: arRegDate, startDate: arStartDate || null, endDate: arEndDate || null, months: (arMonths > 0 ? arMonths : null), regClass: arRegClass, program: arProgramNew }
    };
    if (body.dryRun === true || String(body.dryRun) === 'true') {
      return _json({ ok: true, dryRun: true, preview: arPreview });
    }

    // ─── 실제 쓰기 ───
    var arOpts = { age: arAge, kind: arKind, regClass: arRegClass };
    if (arStartDate) arOpts.startDate = arStartDate;
    _memberActiveUpsert_(arName, body.phone, arProgramNew, arRegDate, (arMonths > 0 ? arMonths : 0), arOpts);
    // 방금 만든 새 행 확정 — 위에서 중복 0건을 이미 확인했으니 전화 단일매칭.
    var arNewRow = _findRowByPhone_(arActiveSh, arActPhI, arPhone);
    if (arNewRow < 2) return _json({ ok: false, error: 'restore-write-failed', detail: '유효회원 행 생성 후 확인 실패 — 시트를 확인해주세요' });
    // upsert가 못 하는 칸(주소·비고 인계·담당자 강제고정 우회·등록회차 이어받기·명시적 시작/종료일) 직접 기록.
    var arActAddrI = _arIdx(arActiveHdr, '주소');
    var arActMemoI = _arIdx(arActiveHdr, '비고'); if (arActMemoI < 0) arActMemoI = _arIdx(arActiveHdr, '메모');
    var arActOwnI = _arIdx(arActiveHdr, '담당자');
    var arActSeqI = _arIdx(arActiveHdr, '등록회차');
    var arActStI = _arIdx(arActiveHdr, '시작일자');
    var arActEndI = _arIdx(arActiveHdr, '종료일자'); if (arActEndI < 0) arActEndI = _arIdx(arActiveHdr, '종료일');
    var arActRemI = _arIdx(arActiveHdr, '잔여일');
    if (arActAddrI >= 0 && arAddr) arActiveSh.getRange(arNewRow, arActAddrI + 1).setValue(arAddr);
    if (arActMemoI >= 0 && arMemo) arActiveSh.getRange(arNewRow, arActMemoI + 1).setValue(arMemo);
    if (arActOwnI >= 0 && arOwner) arActiveSh.getRange(arNewRow, arActOwnI + 1).setValue(arOwner);
    if (arActSeqI >= 0) arActiveSh.getRange(arNewRow, arActSeqI + 1).setValue(arNewSeq);
    // 회원번호 인계(2026-08-27 GM 지시) — 보관에서 돌아온 사람은 예전에 받은 번호를 그대로 쓴다.
    //   이 한 줄이 없으면 새 행의 회원번호가 빈칸이 되고, 같은 사람이 번호를 두 개 갖게 된다.
    //   값은 위에서 이미 읽어 둔 보관 행(arRowVals)에서 꺼내므로 시트를 다시 찾아보지 않는다.
    var arActNoI = _arIdx(arActiveHdr, MEMBER_REGISTRY_KEY_COL);
    if (arActNoI >= 0 && arMemberNo) arActiveSh.getRange(arNewRow, arActNoI + 1).setValue(arMemberNo);
    // 명시적 시작/종료일은 개월수 계산보다 항상 우선(요청값 승리).
    if (arStartDate && arActStI >= 0) { var _sC = arActiveSh.getRange(arNewRow, arActStI + 1); _sC.setNumberFormat('@'); _sC.setValue(arStartDate); }
    if (arEndDate && arActEndI >= 0) {
      var _eC = arActiveSh.getRange(arNewRow, arActEndI + 1); _eC.setNumberFormat('@'); _eC.setValue(arEndDate);
      if (arActRemI >= 0) {
        var _ed = new Date(arEndDate + 'T00:00:00+09:00');
        if (!isNaN(_ed.getTime())) arActiveSh.getRange(arNewRow, arActRemI + 1).setValue(Math.round((_ed.getTime() - Date.now()) / 86400000));
      }
    }
    // 보관 행은 지운다 — 이관이라 원본을 남기지 않는다(2026-08-26 GM: "이관건이니 기존 자료는 없어져야해").
    //   지우기 전 행 전체 값을 변경이력에 통째로 남겨 되돌릴 근거를 보존한다. 전화 단일매칭을 위에서
    //   확인했고 그 뒤로 이 시트를 건드리지 않았으므로 arRow 는 여전히 그 사람 행이다.
    var arArchVals = arArchSh.getRange(arRow, 1, 1, arArchHdr.length).getValues()[0];
    _memberLog_([[new Date(), arStaff, arName, _logMaskPhone_(body.phone), 'LOSS보관 원본삭제',
                  'LOSS보관 행 ' + arRow + ' 원본: ' + JSON.stringify(arArchVals).slice(0, 900),
                  '유효회원 행 ' + arNewRow, '멤버십']]);
    arArchSh.deleteRow(arRow);
    _memberLog_([[new Date(), arStaff, arName, _logMaskPhone_(body.phone), 'LOSS보관 재등록복귀',
                  'LOSS보관 행 ' + arRow, '유효회원 행 ' + arNewRow + '(등록분류:' + arRegClass + ')', '멤버십']]);
    _memberCacheBump_(); _aaCacheClear_(['valid', 'archive']);
    return _json({ ok: true, restored: true, name: arName, phone: body.phone, archiveRow: arRow, newRow: arNewRow, regClass: arRegClass, seq: arNewSeq });
  }

  /* ─── 회원등기부 구축(member_registry_build) — 2026-08-26 시포 · GM 승인 ────────────────────
     설계 정본 = status/briefs/CPO-2026-08-26-회원도메인-이행설계.md

     왜: 지금 사람을 찾는 열쇠가 전화번호와 '등록일자+전화+이름' 지문인데, 둘 다 바뀌는 값이다.
     같은 전화에 이름이 둘 이상인 것이 1,124건이라 가족은 저장이 아예 거부되고, 등록일자를
     고치면 그 뒤 저장이 전부 막힌다(유상두·전하늘 실사고). 그래서 사람마다 **한 번 주면 절대
     안 바뀌는 번호**(M00001…)를 부여하고 모든 원장 줄을 그 번호로 꿴다.

     안전:
     · 기존 칸을 옮기거나 지우지 않는다. 각 탭 맨 뒤에 '회원번호' 칸 하나만 붙인다.
     · 사람 묶는 키 = (전화, 이름) 둘 다 같을 때만. 전화만 같고 이름이 다르면 각자 번호를 받는다
       — 잘못 합치는 것이 안 합치는 것보다 위험하다(INC-020). 같은 사람 후보는 표시만 하고
       병합은 사람이 확인한 뒤에 한다.
     · 멱등이다. 두 번 돌려도 이미 부여된 번호는 그대로다(등기부에서 찾아 재사용).
     · dryRun:true 면 아무것도 쓰지 않고 무엇을 할지만 돌려준다.
     · 행을 지우거나 옮기지 않는다. append 와 열 단위 쓰기뿐이다.                            */
  if (action === 'member_registry_build') {
    var rgDry = (body.dryRun === true || String(body.dryRun) === 'true');
    var rgSs = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);

    // 대상 = 회원 원장이 실제로 들어 있는 물리 탭 3개. '종료회원'은 별도 탭이 아니라
    // 유효회원 탭 안에서 잔여일·LOSS 태그로 갈리는 값이라 여기 없다(member_active_list 와 같은 사실).
    // 법인 탭은 이름이 아니라 gid 로 찾는다 — member_active_list scope='corp' 이 쓰는 방식 그대로다
    // (이름으로 찾으면 '시트 없음' 이 난다. 2026-08-26 실측으로 확인).
    var rgCorpSh = null, rgAllSh = rgSs.getSheets();
    for (var rcs = 0; rcs < rgAllSh.length; rcs++) {
      if (rgAllSh[rcs].getSheetId() === MEMBER_CORP_SHEET_GID) { rgCorpSh = rgAllSh[rcs]; break; }
    }
    var rgTabs = [MEMBER_SHEET, (rgCorpSh ? rgCorpSh.getName() : MEMBER_CORP_SHEET_NAME), MEMBER_ARCHIVE_SHEET];

    function _rgIdx(hdr, want) {
      var w = String(want).replace(/\s/g, '');
      for (var i = 0; i < hdr.length; i++) { if (hdr[i] && hdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; }
      return -1;
    }
    function _rgKey(phone, name) { return _normPhone_(phone) + '|' + String(name || '').trim(); }

    /* ① 이미 나간 번호 모으기 — 원장 탭의 '회원번호' 칸이 곧 대장이다.
       ★2026-08-27 GM 지시로 별도 '회원등기부' 탭 의존을 끊었다. GM: "코드랑 유효회원시트에 같이
       넣어주면 안되나? 지금있는 등기부시트 삭제하고". 등기부 탭에 실제로 들어 있던 것은 번호·이름·
       전화·생성일뿐이고(관계 칸 3개는 처음부터 빈칸으로 넣고 있었다), 그 번호는 세 탭의 회원번호
       칸에 이미 그대로 박혀 있다 — 같은 진실을 두 곳에 두던 것을 한 곳으로 줄인다(약속 L01).
       사람 묶는 키·멱등·다음 번호 규칙은 종전 그대로다. */
    var rgKnown = {}, rgMaxNo = 0, rgBodies = {};
    for (var rk = 0; rk < rgTabs.length; rk++) {
      var kSh = rgSs.getSheetByName(rgTabs[rk]);
      if (!kSh) continue;
      var kLast = kSh.getLastRow(), kCols = kSh.getLastColumn();
      if (kLast < 2) continue;
      var kHdr = kSh.getRange(1, 1, 1, kCols).getValues()[0].map(function(v){ return String(v).trim(); });
      var kBody = kSh.getRange(2, 1, kLast - 1, kCols).getValues();
      rgBodies[rgTabs[rk]] = { hdr: kHdr, body: kBody, cols: kCols };   // 아래 ②가 다시 안 읽게 넘긴다
      var kNoI = kHdr.indexOf(MEMBER_REGISTRY_KEY_COL);
      if (kNoI < 0) continue;
      var kNmI = _rgIdx(kHdr, '회원명'), kPhI = _rgIdx(kHdr, '휴대폰');
      for (var kb = 0; kb < kBody.length; kb++) {
        var _no = String(kBody[kb][kNoI] || '').trim();
        if (!_no) continue;
        if (kNmI >= 0 && kPhI >= 0) rgKnown[_rgKey(kBody[kb][kPhI], kBody[kb][kNmI])] = _no;
        var _n = parseInt(_no.replace(/[^0-9]/g, ''), 10);
        if (_n > rgMaxNo) rgMaxNo = _n;
      }
    }

    // ② 탭별로 읽어 사람 묶기
    var rgPlan = [], rgNewPeople = [], rgSeen = {}, rgReport = [];
    for (var rt = 0; rt < rgTabs.length; rt++) {
      var sh = rgSs.getSheetByName(rgTabs[rt]);
      if (!sh) { rgReport.push({ tab: rgTabs[rt], error: '시트 없음' }); continue; }
      var last = sh.getLastRow(), cols = sh.getLastColumn();
      if (last < 2) { rgReport.push({ tab: rgTabs[rt], rows: 0 }); continue; }
      var hdr = sh.getRange(1, 1, 1, cols).getValues()[0].map(function(v){ return String(v).trim(); });
      var nmI = _rgIdx(hdr, '회원명'), phI = _rgIdx(hdr, '휴대폰');
      if (nmI < 0 || phI < 0) { rgReport.push({ tab: rgTabs[rt], error: '이름/전화 칸 없음' }); continue; }
      var noI = hdr.indexOf(MEMBER_REGISTRY_KEY_COL);
      var addCol = (noI < 0);
      if (addCol && !rgDry) {
        noI = cols;                                   // 맨 뒤에 붙인다(기존 칸 위치 불변)
        sh.getRange(1, noI + 1).setValue(MEMBER_REGISTRY_KEY_COL);
        cols = cols + 1;
      }
      // ①에서 이미 읽어 둔 값을 다시 쓴다(같은 탭을 두 번 읽지 않는다). 칸을 새로 붙인 탭만 다시 읽는다.
      var _rgCached = rgBodies[rgTabs[rt]];
      var body2 = (_rgCached && !addCol) ? _rgCached.body
                : sh.getRange(2, 1, last - 1, Math.max(cols, hdr.length)).getValues();
      var colOut = [], filled = 0, kept = 0;
      for (var br = 0; br < body2.length; br++) {
        var nm = String(body2[br][nmI] || '').trim();
        var ph = body2[br][phI];
        var cur = (noI >= 0 && noI < body2[br].length) ? String(body2[br][noI] || '').trim() : '';
        if (!nm) { colOut.push([cur]); continue; }     // 이름 없는 줄은 사람이 아니다 — 건드리지 않는다
        if (cur) { colOut.push([cur]); kept++; continue; }   // 이미 있으면 그대로(멱등)
        var key = _rgKey(ph, nm);
        var no = rgKnown[key] || rgSeen[key];
        if (!no) {
          rgMaxNo++;
          no = 'M' + ('00000' + rgMaxNo).slice(-5);
          rgSeen[key] = no;
          rgNewPeople.push([no, nm, String(ph || ''), (rgTabs[rt] === MEMBER_CORP_SHEET_NAME ? '법인' : '개인'),
                            '', '', '', _todayKR_(), '']);
        }
        colOut.push([no]);
        filled++;
      }
      rgPlan.push({ tab: rgTabs[rt], sheet: sh, colIndex: noI, values: colOut, addCol: addCol });
      rgReport.push({ tab: rgTabs[rt], rows: body2.length, 칸신설: addCol, 번호부여: filled, 기존유지: kept });
    }

    if (rgDry) {
      return _json({ ok: true, dryRun: true, 새사람: rgNewPeople.length,
                     마지막번호: 'M' + ('00000' + rgMaxNo).slice(-5), 탭별: rgReport });
    }

    // ③ 실제 쓰기 — 각 탭의 회원번호 열에 쓴다(별도 등기부 탭 없음, 2026-08-27 GM 지시)
    for (var rp = 0; rp < rgPlan.length; rp++) {
      var pl = rgPlan[rp];
      if (!pl.values.length || pl.colIndex < 0) continue;
      pl.sheet.getRange(2, pl.colIndex + 1, pl.values.length, 1).setValues(pl.values);
    }
    _memberLog_([[new Date(), _logWho_(body), '(회원번호)', '', '회원번호 부여',
                  '원장 탭 회원번호 칸', '새 번호 ' + rgNewPeople.length + '명', '멤버십']]);
    // ④ 낡은 '회원등기부' 탭은 2026-08-27 에 백업(변경이력 '등기부탭 삭제 전 백업' 1,737행) 후 삭제 완료.
    //    일회성 정리 코드는 같은 날 걷어냈다 — 다시 필요하면 git 이력에서 꺼낸다(약속 L21).
    _memberCacheBump_(); _aaCacheClear_(['valid', 'corp', 'archive']);
    return _json({ ok: true, 새사람: rgNewPeople.length,
                   마지막번호: 'M' + ('00000' + rgMaxNo).slice(-5), 탭별: rgReport });
  }

  // ─── 종목별 담당자 저장(유효회원 5칸: PT/골프/P.L/스쿼시/수영 담당자) — 전화 매칭 단일셀 쓰기.
  //   화이트리스트 외 field는 무조건 거부(임의 컬럼 쓰기 차단 — 안전 경계). 2026-07-18 시포.
  if (action === 'member_owner_save') {
    var mosAllowed = ['PT 담당자', '골프 담당자', 'P.L 담당자', '스쿼시 담당자', '수영 담당자'];
    var mosField = String(body.field || '').trim();
    if (mosAllowed.indexOf(mosField) < 0) return _json({ ok: false, error: 'bad field' });
    var mosPhone = _normPhone_(body.phone);
    if (!mosPhone) return _json({ ok: false, error: 'no member' });
    var mosValue = String(body.value == null ? '' : body.value).trim();
    var mosSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!mosSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var mosLast = mosSh.getLastRow();
    if (mosLast < 2) return _json({ ok: false, error: 'no member' });
    var mosHdr = mosSh.getRange(1, 1, 1, mosSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    var mosPhoneIdx = mosHdr.indexOf(MEMBER_PHONE_COL);
    var mosFieldIdx = mosHdr.indexOf(mosField);
    if (mosPhoneIdx < 0 || mosFieldIdx < 0) return _json({ ok: false, error: '컬럼 미발견' });
    var mosPhones = mosSh.getRange(2, mosPhoneIdx + 1, mosLast - 1, 1).getValues();
    var mosRow = -1;
    for (var mosI = 0; mosI < mosPhones.length; mosI++) {
      if (_normPhone_(mosPhones[mosI][0]) === mosPhone) { mosRow = mosI + 2; break; }
    }
    if (mosRow < 0) return _json({ ok: false, error: 'no member' });
    // 배327 — 두 번째 쓰기 관문. 매칭 가드가 서로 달라 액션은 합치지 않고 기록 함수만 공유한다.
    var _mosCell = mosSh.getRange(mosRow, mosFieldIdx + 1);
    var _mosOld = String(_mosCell.getValue() == null ? '' : _mosCell.getValue());
    _mosCell.setValue(mosValue);
    if (_mosOld !== mosValue) {
      var _mosNameI = -1;
      for (var _mn = 0; _mn < mosHdr.length; _mn++) {
        var _mnh = mosHdr[_mn].replace(/\s/g, '');
        if (_mnh === '성명' || _mnh === '이름' || _mnh.indexOf('회원명') >= 0) { _mosNameI = _mn; break; }
      }
      _memberLog_([[new Date(), _logWho_(body),
                    _mosNameI >= 0 ? String(mosSh.getRange(mosRow, _mosNameI + 1).getValue() || '') : '',
                    _logMaskPhone_(mosSh.getRange(mosRow, mosPhoneIdx + 1).getValue()),
                    mosField, _mosOld, mosValue, '멤버십']]);
    }
    _aaCacheClear_(['valid']);
    return _json({ ok: true, phone: mosPhone, field: mosField, value: mosValue, rowIndex: mosRow });
  }

  // ─── 멤버십 담당자 열 일괄 배치 쓰기(단일 setValues 1회) — 행단위 POST 1,006회(약 50분) → 1회(수 초) 전환.
  //   ⚠️ field 화이트리스트: '담당자'(A열, 멤버십 담당)만 허용 — 강습 담당 5칸(PT/골프/P.L/스쿼시/수영)은 절대 불허.
  //   ⚠️ 헤더 정확일치만 매칭(INC-020 재발방지 — 부분일치 indexOf 오매칭 금지, 쓸 필드 한정).
  //   scope=valid: member_active_list 와 동일 판정기준(잔여일>=0 & 재등록분류 이탈표시 없음, 2026-07-31 경계 정정)으로 대상 행만
  //   값 교체, 범위밖(유효 아님) 행은 원값 그대로 같이 써 무변경. 단일 열 range 로만 setValues
  //   (행 추가·삭제 0, 다른 열 무손상). 2026-07-20 GM 지시(대량 변경 배치화 — 6.1초/건→일괄).
  if (action === 'member_owner_bulk_set') {
    var mbAllowed = ['담당자'];
    var mbField = String(body.field || '').trim();
    if (mbAllowed.indexOf(mbField) < 0) return _json({ ok: false, error: 'bad field' });
    var mbValue = String(body.value == null ? '' : body.value).trim();
    if (!mbValue) return _json({ ok: false, error: 'value 필수' });
    var mbScope = String(body.scope || 'valid');
    if (mbScope !== 'valid') return _json({ ok: false, error: 'scope=valid 만 지원' });
    var mbSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!mbSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var mbLast = mbSh.getLastRow();
    var mbCols = mbSh.getLastColumn();
    if (mbLast < 2 || mbCols < 1) return _json({ ok: true, scope: mbScope, total: 0, changed: 0, skipped: 0, before: {}, after: {} });
    var mbHdr = mbSh.getRange(1, 1, 1, mbCols).getValues()[0].map(function(v){ return String(v).trim(); });
    // 쓸 필드 — 정확일치만(INC-020 재발방지)
    var mbFieldIdx = -1;
    for (var mfi = 0; mfi < mbHdr.length; mfi++) { if (mbHdr[mfi] === mbField) { mbFieldIdx = mfi; break; } }
    if (mbFieldIdx < 0) return _json({ ok: false, error: '컬럼 미발견: ' + mbField });
    // scope=valid 판정 칸(잔여일·재등록분류) — member_active_list 와 동일 퍼지매칭(기존 판정 로직 재사용, 쓸 필드와는 무관)
    function _mbIdx(want){ var w = String(want).replace(/\s/g,''); for (var i=0;i<mbHdr.length;i++){ if (mbHdr[i].replace(/\s/g,'').indexOf(w) >= 0) return i; } return -1; }
    var mbRemIdx = _mbIdx('잔여일'), mbReIdx = _mbIdx('재등록분류');
    var mbRows = mbLast - 1;
    var mbAllVals = mbSh.getRange(2, 1, mbRows, mbCols).getValues();  // 판정용 전체 열 읽기(쓰기는 대상 열 1개만)
    var mbBefore = {}, mbAfter = {};
    var mbChanged = 0, mbSkipped = 0, mbTotal = 0;
    var mbOut = [];
    for (var mbI = 0; mbI < mbAllVals.length; mbI++) {
      var mbRowArr = mbAllVals[mbI];
      var mbCur = String(mbRowArr[mbFieldIdx] == null ? '' : mbRowArr[mbFieldIdx]).trim();
      // 유효/종료 판정 = _memberIsValid_ 단일 함수(약속 L01, 배354 2026-08-04 짝 누락 근본수리).
      var mbIsValid = _memberIsValid_(mbRemIdx >= 0 ? mbRowArr[mbRemIdx] : '', mbReIdx >= 0 ? mbRowArr[mbReIdx] : '');
      if (!mbIsValid) { mbOut.push([mbCur]); continue; }  // 범위밖(유효회원 아님) — 원값 그대로, 집계 제외
      mbTotal++;
      var mbKey = mbCur || '(빈값)';
      mbBefore[mbKey] = (mbBefore[mbKey] || 0) + 1;
      if (mbCur === mbValue) { mbOut.push([mbCur]); mbSkipped++; }
      else { mbOut.push([mbValue]); mbChanged++; }
      var mbAK = (mbCur === mbValue ? mbCur : mbValue) || '(빈값)';
      mbAfter[mbAK] = (mbAfter[mbAK] || 0) + 1;
    }
    if (mbChanged > 0) mbSh.getRange(2, mbFieldIdx + 1, mbRows, 1).setValues(mbOut);  // 단일 열 range 1회 — 다른 열 무손상
    // 배327 — 일괄 배치는 요약 1줄만 남긴다. 개별 1,000줄은 개별 수정 추적을 노이즈로 덮는다.
    // 건수(mbChanged)는 위에서 이미 세어 둔 값 — 열을 다시 읽지 않는다(느려지면 안 된다).
    // 이전값은 행마다 달라 '각각 다름'으로 둔다(없는 값을 지어내지 않는다).
    if (mbChanged > 0) {
      _memberLog_([[new Date(), _logWho_(body),
                    '— 전체 ' + mbChanged + '건', '', '일괄 배치 · ' + mbField,
                    '각각 다름(' + mbChanged + '건)', mbValue, '멤버십']]);
    }
    return _json({ ok: true, scope: mbScope, field: mbField, value: mbValue, total: mbTotal, changed: mbChanged, skipped: mbSkipped, before: mbBefore, after: mbAfter });
  }

  // ─── 멤버십 회원관리 요약 집계(§2-A 로딩속도) — 2026-07-20 시포 ───
  //   목적: 화면이 카드 숫자를 세려고 member_active_list(1,006행×37열, 콜드 ~11초)를 통째로 기다리던 것을
  //   서버 집계 작은 응답으로 대체. 계약 = docs/superpowers/specs/2026-07-20-member-active-summary-contract.md
  //   ★ 유효성 판정은 cpo_today_stats와 100% 동일 공식 재사용(재정의 금지) — 회원명 있는 행만, 잔여일>=0(2026-07-31 경계 정정), 이탈표시 없음.
  //   ★ member_active_list는 그대로 둔다(표·검색·인라인편집·담당자배정이 실레코드를 쓰므로). 이 액션은 부가 최적화.
  if (action === 'member_active_summary') {
    var maCache = CacheService.getScriptCache();
    var maCached = maCache.get('member_active_summary_v1');
    if (maCached) return _json(JSON.parse(maCached));
    var maTz = 'Asia/Seoul';
    var maToday = Utilities.formatDate(new Date(), maTz, 'yyyy-MM-dd');
    var maMonthStart = maToday.slice(0, 8) + '01';
    var maYearStart  = maToday.slice(0, 4) + '-01-01';
    var maRes = { ok: true, action: 'member_active_summary', date: maToday,
                  validTotal: 0, endedTotal: 0, waitingCount: 0,
                  typeCounts: { '멤버십': 0, '입주민': 0, '중단기': 0, '보증금': 0, 'FAN VIP': 0, '법인': 0, '기타': 0 },
                  lossPeriods: { day: 0, month: 0, year: 0, total: 0 },
                  waitPeriods: { day: 0, month: 0, year: 0, total: 0 } };
    try {
      var maSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
      if (!maSh || maSh.getLastRow() < 2) return _json(maRes);
      var maCols = maSh.getLastColumn();
      var maHdr = maSh.getRange(1, 1, 1, maCols).getValues()[0].map(function(v){ return String(v).trim(); });
      // 헤더 퍼지매칭 — cpo_today_stats._crIdx와 동일 관례(공백·개행 제거 후 부분일치)
      function _maIdx(want){ var w = String(want).replace(/\s/g, ''); for (var i = 0; i < maHdr.length; i++){ if (maHdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; } return -1; }
      var maNmI  = _maIdx('회원명');
      var maRemI = _maIdx('잔여일');
      var maReI  = _maIdx('재등록분류');
      var maTypI = _maIdx('회원구분');
      var maStI  = _maIdx('시작일자');
      var maClsI = _maIdx('등록분류');
      // '대기' 전용 칸 — 부분일치로 찾으면 다른 헤더에 걸릴 수 있어 이 칸만 완전일치로 찾는다.
      var maWaitI = -1;
      for (var _mw = 0; _mw < maHdr.length; _mw++) { if (maHdr[_mw].replace(/\s/g, '') === '대기') { maWaitI = _mw; break; } }
      // LOSS 날짜 칸: LOSS일자→이탈일→해지일→종료일.
      //   ★ GM 교정 2026-08-08: '이탈' 용어 전면 → LOSS. 시트 헤더도 'LOSS일자'로 변경 예정이므로 우선 순위 1위.
      //     '이탈일'은 헤더 변경 전 하위호환 폴백으로 유지 — 헤더 변경 완료 후 정리 가능.
      //     '종료일'은 이 시트의 '종료\n일자'(종료일자)와 구분이 안 돼 19건으로 틀리므로 맨 마지막 폴백.
      var maLossI = _maIdx('LOSS일자');
      if (maLossI < 0) maLossI = _maIdx('이탈일');
      if (maLossI < 0) maLossI = _maIdx('해지일');
      if (maLossI < 0) maLossI = _maIdx('종료일');
      // 회원 구분 정본 6종(GM 확정 2026-08-13) — 멤버십·입주민·보증금·FAN VIP·중단기·법인.
      //   법인은 별도 시트라 이 집계에선 0이지만, 목록에서 빼 두면 나중에 이 시트로 들어왔을 때 '기타'로 샌다.
      var MA_TYPO  = { '맴버십': '멤버십', '멥버십': '멤버십' };
      var MA_KNOWN = { '멤버십': 1, '입주민': 1, '중단기': 1, '보증금': 1, 'FAN VIP': 1, '법인': 1 };
      function _maISO(v) {
        if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, maTz, 'yyyy-MM-dd');
        return _miToISO_(v) || '';
      }
      // 대기자 판정 전용 — member_active_list의 셀 직렬화(Date→ISO, 그 외 String)를 그대로 재현한다.
      //   화면 _isFutureStart(membership.html:5506)가 그 문자열에 엄격정규식 /^\d{4}-\d{2}-\d{2}/를 걸고,
      //   형식이 아니면 '이미 시작된 것'으로 본다. _maISO(느슨 파싱)를 쓰면 '25. 10 .15' 같은 오형식 값까지
      //   날짜로 살려내 화면보다 1건 많게 샌다(2026-07-20 실측: 27 vs 화면 26). 화면 숫자가 정답이므로 동일 규칙 사용.
      function _maCell(v) {
        if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, maTz, 'yyyy-MM-dd');
        return (v === null || v === undefined) ? '' : String(v);
      }
      function _maBump(bucket, iso) {
        bucket.total++;
        if (!iso) return;                                   // 날짜 못 읽으면 total에만 포함(계약 §2)
        if (iso === maToday) bucket.day++;
        if (iso >= maMonthStart && iso <= maToday) bucket.month++;
        if (iso >= maYearStart  && iso <= maToday) bucket.year++;
      }
      var maAll = maSh.getRange(2, 1, maSh.getLastRow() - 1, maCols).getValues();
      for (var mi = 0; mi < maAll.length; mi++) {
        var mrow = maAll[mi];
        // 회원명 없는 행은 통째로 제외 — cpo_today_stats와 동일(유효·종료 어느 쪽에도 안 넣는다)
        if (maNmI >= 0 && !String(mrow[maNmI] == null ? '' : mrow[maNmI]).trim()) continue;
        // 유효/종료 판정 = _memberIsValid_ 단일 함수(약속 L01, 배354 2026-08-04 짝 누락 근본수리).
        var maValid = _memberIsValid_(maRemI >= 0 ? mrow[maRemI] : '', maReI >= 0 ? mrow[maReI] : '');
        if (maValid) {
          maRes.validTotal++;
          var mv = maTypI >= 0 ? String(mrow[maTypI] == null ? '' : mrow[maTypI]).trim() : '';
          mv = MA_TYPO[mv] || mv;
          if (!mv || !MA_KNOWN[mv]) mv = '기타';
          maRes.typeCounts[mv]++;
          /* ★2026-08-13 GM 확정 — 대기 = 8명(999명 중). 그전엔 '시작일자가 아직 안 온 회원'으로 세어 28명이
             나왔는데, 그건 대기가 아니라 '시작 예정'이다. 대기는 실무진이 분류 칸에 '대기'라고 적어 둔 회원이다.
             화면(_isFutureStart)이 이미 그 규칙으로 세어 8명을 보여주고 있었는데 이 서버 집계만 달랐다 —
             같은 이름의 숫자가 화면과 보고서에서 서로 달랐던 원인이다.
             ▸전용 '대기' 칸이 그 행에 켜져 있으면 시작일 기준으로 본다(화면과 같은 규칙, 현재 켜진 행 0건). */
          var maStS = maStI >= 0 ? _maCell(mrow[maStI]).trim() : '';
          var maIsWait = false;
          if (maWaitI >= 0 && String(mrow[maWaitI] == null ? '' : mrow[maWaitI]).trim()) {
            maIsWait = !/^\d{4}-\d{2}-\d{2}/.test(maStS) || maStS.slice(0, 10) > maToday;
          } else {
            var maClsChk = [maClsI, maReI];
            for (var mc = 0; mc < maClsChk.length; mc++) {
              if (maClsChk[mc] < 0) continue;
              var maCv = String(mrow[maClsChk[mc]] == null ? '' : mrow[maClsChk[mc]]).trim();
              if (maCv === '대기' || maCv === '재등록대기') { maIsWait = true; break; }
            }
          }
          if (maIsWait) { maRes.waitingCount++; _maBump(maRes.waitPeriods, /^\d{4}-\d{2}-\d{2}/.test(maStS) ? maStS.slice(0, 10) : ''); }
        } else {
          maRes.endedTotal++;
          _maBump(maRes.lossPeriods, maLossI >= 0 ? _maISO(mrow[maLossI]) : '');
        }
      }
      maRes.endedTotal += _lossArchiveCount_();   // 보관 시트분 합산 — 숫자 유지(2026-08-13)
    } catch (eMa) { return _json({ ok: false, action: 'member_active_summary', error: String(eMa) }); }
    try { maCache.put('member_active_summary_v1', JSON.stringify(maRes), 60); } catch (eMc) {}
    return _json(maRes);
  }

  // ═══ 휴회(재설계 2026-07-22 GM 확정) — 공개 접수=쓰기전용(회원 조회·판정결과 노출 0·PII 창구 안 열림) ═══
  //   흐름: member_hold_apply(공개 write-only → '휴회접수' 탭 접수대기) → member_hold_intake_list(ERP read+서버 자동판정)
  //         → member_hold_approve(직원 승인/반려 · 승인=회원DB '이용일수' 앞 새칸 기록+증분+상태 진행중). 검증 3회/총60일/1회 7~60 재사용.
  //   게이트: 공개 접수 write=HOLD_LIVE, 승인 write=HOLD_LIVE_T (둘 다 GM go). 리스트/자동판정=read(라이브 가능·ERP 게이트 뒤).
  //   ⚠️ 구 self-service 미리보기(member_hold_preview 이름+전화 본인조회)=GM 지시로 폐기(온라인 조회 금지) → 비활성 스텁.
  // ★저장 위치 이전(배9948 · GM A안 2026-07-23) — '접수는 종합접수처 시트로 통합, 관리는 멤버십 회원관리에서'.
  //   전: 회원 DB(MEMBER_SPREADSHEET_ID)의 '휴회접수' 탭 → 다른 접수(VOC·분실물 등)와 따로 놀았다.
  //   후: 종합접수처 데이터 시트로 통합. 이관 당시엔 회원 DB 쪽 옛 탭을 보존(원본 보존 · 이관은 대조키로만)했으나,
  //      2026-07-24 실측(탭 42개 전수 확인 0건 + Sheets API 재확인) 결과 그 옛 탭은 이미 없다 — 갈 곳이 없는
  //      죽은 폴백이라 배10041로 제거(2026-07-27). 종합접수처를 열 수 없으면 이제 그대로 null(명시적 실패).
  var HOLD_INTAKE_SS_ID = '17ly-_udUYgOoPZnv6FFV9vq_R2D41q4ZYrGaGYt9rto';   // 종합접수처 데이터 시트
  var HOLD_INTAKE_TAB = '휴회접수';
  // '휴회종료일' 신설(배9948 ②) — 회원 화면이 holdEnd 를 보내는데 받을 칸이 없어 유실되고 있었다.
  //   기간이 안 남으면 직원이 시작일+일수로 매번 역산해야 한다.
  var HOLD_INTAKE_HDR = ['접수일시', '성함', '연락처', '구분', '휴회시작일', '휴회종료일', '희망일수', '사유', '상태', '처리일시', '처리메모'];
  // 접수 탭 열기 — 종합접수처(17ly…) 단일 위치. create=true 면 없을 때 만든다.
  //   ※ 회원 DB(옛 위치) 폴백 분기 삭제(배10041·2026-07-27) — 회원 DB에 '휴회접수' 탭이 이미 없음을
  //     실측 확인(탭 42개 전수 확인 0건 + Sheets API 메타데이터 조회로 재확인, 2026-07-24 시우 1차·시포 2차).
  //     폴백은 항상 실패하는 죽은 분기였다 — 제거해도 동작 동일(주 경로 실패 시 그대로 null 반환).
  function _holdIntakeSheet_(create) {
    try {
      var ss = SpreadsheetApp.openById(HOLD_INTAKE_SS_ID);
      var sh = ss.getSheetByName(HOLD_INTAKE_TAB);
      if (!sh && create) {
        sh = ss.insertSheet(HOLD_INTAKE_TAB);
        sh.getRange(1, 1, 1, HOLD_INTAKE_HDR.length).setValues([HOLD_INTAKE_HDR]);
      }
      return sh || null;
    } catch (e) { return null; /* 권한 없음·시트 없음 */ }
  }
  var HLD_MAX_COUNT = 3, HLD_MAX_TOTAL = 60, HLD_MIN_ONCE = 7, HLD_MAX_ONCE = 60;
  // ★신규/연장 구분(2026-07-23 GM 확정) — 실측 근거: 휴회신청 응답 시트에 '1회차 연장' 5일 건(김호선) 존재.
  //   최소 7일 규칙을 연장에도 적용하면 실제 운영되던 짧은 연장이 전부 거부된다 → 연장은 하한 면제(1일~).
  //   ※ 상한(1회 60일)·횟수(3회)·누적(60일) 한도는 신규/연장 동일하게 유지 — 하한만 예외.
  var HLD_KIND_EXTEND = '연장', HLD_KIND_NEW = '신규';
  function _holdKindNorm_(v) { return String(v || '').indexOf(HLD_KIND_EXTEND) >= 0 ? HLD_KIND_EXTEND : HLD_KIND_NEW; }
  function _holdMinOnce_(kind) { return _holdKindNorm_(kind) === HLD_KIND_EXTEND ? 1 : HLD_MIN_ONCE; }
  function _holdEndCalc_(start, days) { var d = new Date(start + 'T00:00:00+09:00'); d.setDate(d.getDate() + (days - 1)); return Utilities.formatDate(d, 'Asia/Seoul', 'yyyy-MM-dd'); }
  // 시트가 'yyyy-MM-dd' 문자열을 Date 객체로 자동 변환해 저장한다 → 그대로 읽으면
  // 'Thu Jul 24 2026 00:00:00 GMT+0900' 같은 값이 직원 화면에 뜨고, 날짜 정규식도 어긋나 종료일이 안 잡힌다.
  // 읽는 쪽에서 항상 정규화한다(기존 행·신규 행 모두 안전). 2026-07-23 시포 — 라이브 실측으로 발견.
  function _holdDateStr_(v, withTime) {
    if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, 'Asia/Seoul', withTime ? 'yyyy-MM-dd HH:mm' : 'yyyy-MM-dd');
    return String(v === null || v === undefined ? '' : v).trim();
  }
  // 접수 탭 헤더 보장(추가칸 비파괴 append) — 이미 있는 탭에 '구분'이 없으면 끝에 만든다. 행 삭제·이동 0.
  function _holdIntakeHdr_(sh) {
    var h = sh.getLastRow() >= 1 ? sh.getRange(1, 1, 1, Math.max(1, sh.getLastColumn())).getValues()[0].map(function(v){ return String(v).trim(); }) : [];
    for (var k = 0; k < HOLD_INTAKE_HDR.length; k++) {
      var want = HOLD_INTAKE_HDR[k].replace(/\s/g, ''), hit = false;
      for (var j = 0; j < h.length; j++) { if (h[j].replace(/\s/g, '') === want) { hit = true; break; } }
      if (!hit) { sh.getRange(1, h.length + 1).setValue(HOLD_INTAKE_HDR[k]); h.push(HOLD_INTAKE_HDR[k]); }
    }
    return h;
  }

  // 구 온라인 본인조회 폐기(GM: 회원 데이터 온라인 조회·비교 금지) — 어떤 파라미터로도 회원 이력 미반환.
  if (action === 'member_hold_preview') return _json({ ok: false, error: 'not-supported', detail: '온라인 조회는 지원하지 않습니다' });

  // 공개 휴회접수(쓰기전용) — 회원 조회·판정 0. '휴회접수' 탭에 접수대기 1행 append만(회원 판정/잔여 미반환). 게이트 HOLD_LIVE.
  if (action === 'member_hold_apply') {
    var HOLD_LIVE = true;    // ★공개 접수 실기록 게이트 — GM go(2026-07-23) 개통. 역롤백=이 한 줄 false.
    var inName = String(body.name || body.selfName || '').trim();
    var inPhone = String(body.phone || body.selfPhone || '').trim();
    var inStart = String(body.holdStart || '').trim();
    var inDays = parseInt(body.holdDays, 10);
    var inReason = String(body.reason || body.message || '').trim();
    var inKind = _holdKindNorm_(body.holdKind || body.kind);   // 신규|연장 — 연장은 최소일수 면제(2026-07-23 GM)
    if (!inName || !inPhone) return _json({ ok: false, error: 'need-name-phone', detail: '성함과 연락처를 입력해 주세요' });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(inStart)) return _json({ ok: false, error: 'need-start', detail: '희망 시작일을 입력해 주세요' });
    if (isNaN(inDays) || inDays < 1) return _json({ ok: false, error: 'need-days', detail: '희망 일수를 입력해 주세요' });
    // ★일수 적정성 판정을 공개 접수에서 제거(배9948 ③ · GM A안) — 회원 화면에서 '구분(신규·연장)'이
    //   빠지면서 모든 접수가 '신규'로 오고, 서버 하한(7일)이 회원에게 거부 메시지로 그대로 노출됐다.
    //   GM 방침 = "일수 적정성은 접수 시트에서 직원이 확인". 접수는 일단 받고, 판정은 승인 단계에서 한다.
    //   (member_hold_intake_list 의 자동판정과 member_hold_approve 의 재검증은 그대로 남아 있다.)
    if (!HOLD_LIVE) return _json({ ok: false, error: 'hold-gated', detail: '휴회 접수는 GM 검증 후 개통됩니다(현재 미개통)' });
    var iSh = _holdIntakeSheet_(true);
    if (!iSh) return _json({ ok: false, error: 'intake-sheet-unavailable', detail: '접수 시트를 열 수 없습니다 — 데스크로 문의해 주세요' });
    var iHdr = _holdIntakeHdr_(iSh);   // 기존 탭에 '구분'·'휴회종료일'이 없어도 비파괴 보강
    var iNow = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
    // 종료일 = 회원 화면이 보낸 holdEnd 우선(직접 고른 값), 없으면 시작일+일수로 계산.
    var inEnd = String(body.holdEnd || '').trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(inEnd)) inEnd = _holdEndCalc_(inStart, inDays);
    var iVal = { '접수일시': iNow, '성함': inName, '연락처': inPhone, '구분': inKind, '휴회시작일': inStart,
                 '휴회종료일': inEnd, '희망일수': inDays, '사유': inReason, '상태': '접수대기', '처리일시': '', '처리메모': '' };
    var iRow = [];   // 헤더 순서에 맞춰 조립(고정 위치 append 금지 — 칸 순서가 바뀌어도 안전)
    for (var ic = 0; ic < iHdr.length; ic++) { var kk = iHdr[ic].replace(/\s/g, ''); var hit = '';
      for (var kn in iVal) { if (kn.replace(/\s/g, '') === kk) { hit = iVal[kn]; break; } } iRow.push(hit); }
    iSh.appendRow(iRow);
    return _json({ ok: true, received: true });   // ★회원 판정/잔여 미반환(공개 노출 금지)
  }

  // ─── 명단 캐시 워머 트리거 설치/해제/상태 — 2026-07-23 시포·GM ───
  //   ★멱등: 설치 전에 같은 핸들러 트리거를 전부 지운다(여러 번 눌러도 워머가 겹쳐 돌지 않게).
  //   ★주기는 5분 — GAS everyMinutes 는 1·5·10·15·30 만 받는다(8 을 넣으면 생성 시점에 예외).
  //     캐시 TTL 10분보다 짧게 잡아 만료와 갱신 사이에 빈 구간이 생기지 않게 겹쳐 둔다.
  if (action === 'warm_cache_trigger') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var wcMode = String(body.mode || 'status');   // status | install | remove
    var wcFn = 'warmLessonRosterCache';
    function _wcList() {
      var out = [];
      try {
        ScriptApp.getProjectTriggers().forEach(function (t) {
          if (t.getHandlerFunction() === wcFn) out.push({ id: t.getUniqueId(), type: String(t.getEventType()) });
        });
      } catch (e) {}
      return out;
    }
    if (wcMode === 'status') return _json({ ok: true, mode: 'status', installed: _wcList().length, triggers: _wcList() });
    var wcRemoved = 0;
    try {
      ScriptApp.getProjectTriggers().forEach(function (t) {
        if (t.getHandlerFunction() === wcFn) { ScriptApp.deleteTrigger(t); wcRemoved++; }
      });
    } catch (eDel) { return _json({ ok: false, error: 'trigger-delete-failed', detail: String(eDel).slice(0, 100) }); }
    if (wcMode === 'remove') return _json({ ok: true, mode: 'remove', removed: wcRemoved, installed: _wcList().length });
    try {
      ScriptApp.newTrigger(wcFn).timeBased().everyMinutes(_WARM_EVERY_MIN).create();
    } catch (eNew) { return _json({ ok: false, error: 'trigger-create-failed', detail: String(eNew).slice(0, 120) }); }
    return _json({ ok: true, mode: 'install', removedBefore: wcRemoved, everyMinutes: _WARM_EVERY_MIN, installed: _wcList().length });
  }

  // ERP 휴회 접수 관리 — '휴회접수' 탭 리스트 + 서버 자동판정(회원DB 전화 매칭·3회/총60일/1회 7~60). ERP 게이트 뒤 read 전용.
  if (action === 'member_hold_intake_list') {
    // 접수 탭은 종합접수처(17ly…) 단일 위치에서 연다(배9948 이전 · 배10041 옛 위치 폴백 제거).
    //   회원 매칭용 유효회원 시트는 계속 회원 DB에서 읽는다 — 두 시트를 섞지 않는다.
    var lss = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var lSh = _holdIntakeSheet_(false);
    if (!lSh || lSh.getLastRow() < 2) return _json({ ok: true, count: 0, data: [] });
    var lHdr = lSh.getRange(1, 1, 1, lSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    function _lIdx(n){ var w = String(n).replace(/\s/g, ''); for (var i = 0; i < lHdr.length; i++){ if (lHdr[i].replace(/\s/g,'') === w) return i; } return -1; }
    var lTs = _lIdx('접수일시'), lNm = _lIdx('성함'), lPh = _lIdx('연락처'), lSt = _lIdx('휴회시작일'), lDy = _lIdx('희망일수'), lRe = _lIdx('사유'), lStat = _lIdx('상태'), lKd = _lIdx('구분');
    // 회원DB 전화→{count,cumDays,found} 매핑(자동판정용)
    var mSh = lss.getSheetByName(MEMBER_SHEET), mMap = {};
    if (mSh && mSh.getLastRow() >= 2) {
      var mHdr = mSh.getRange(1, 1, 1, mSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
      function _mIdx(n){ var w = String(n).replace(/\s/g, ''); for (var i = 0; i < mHdr.length; i++){ if (mHdr[i].replace(/\s/g,'').indexOf(w) >= 0) return i; } return -1; }
      var mPh = _mIdx('휴대폰'), mC = _mIdx('휴회횟수'), mD = _mIdx('휴회누적일수');
      if (mPh >= 0) { var mAll = mSh.getRange(2, 1, mSh.getLastRow() - 1, mSh.getLastColumn()).getValues();
        for (var mi = 0; mi < mAll.length; mi++){ var pk = _normPhone_(mAll[mi][mPh]); if (!pk) continue;
          var cc = mC >= 0 ? parseInt(String(mAll[mi][mC] || '').replace(/[^0-9\-]/g, ''), 10) : 0; if (isNaN(cc)) cc = 0;
          var dd = mD >= 0 ? parseInt(String(mAll[mi][mD] || '').replace(/[^0-9\-]/g, ''), 10) : 0; if (isNaN(dd)) dd = 0;
          mMap[pk] = { count: cc, cumDays: dd, found: true }; } } }
    var lData = lSh.getRange(2, 1, lSh.getLastRow() - 1, lSh.getLastColumn()).getValues();
    var out = [];
    for (var li = 0; li < lData.length; li++){
      var r = lData[li];
      // 완전 공백행 건너뛰기(시트 하단 빈 줄이 빈 카드로 뜨는 것 차단 — 2026-07-23 시포). 삭제 아님, 표시만 제외.
      var _blank = true;
      for (var bz = 0; bz < r.length; bz++) { if (String(r[bz] === null || r[bz] === undefined ? '' : r[bz]).trim() !== '') { _blank = false; break; } }
      if (_blank) continue;
      var days = lDy >= 0 ? parseInt(String(r[lDy] || '').replace(/[^0-9]/g, ''), 10) : NaN;
      var kind = _holdKindNorm_(lKd >= 0 ? r[lKd] : '');
      var minOnce = _holdMinOnce_(kind);
      var m = mMap[_normPhone_(lPh >= 0 ? r[lPh] : '')] || { count: 0, cumDays: 0, found: false };
      var verdict = '가능', vreason = '';
      if (isNaN(days) || days < minOnce) { verdict = '불가'; vreason = (kind === HLD_KIND_EXTEND ? '연장 ' : '') + '1회 최소 ' + minOnce + '일'; }
      else if (days > HLD_MAX_ONCE) { verdict = '불가'; vreason = '1회 최대 ' + HLD_MAX_ONCE + '일'; }
      else if (m.count + 1 > HLD_MAX_COUNT) { verdict = '불가'; vreason = '횟수 한도(현재 ' + m.count + '/' + HLD_MAX_COUNT + '회)'; }
      else if (m.cumDays + days > HLD_MAX_TOTAL) { verdict = '불가'; vreason = '누적일 한도(현재 ' + m.cumDays + '+' + days + '>' + HLD_MAX_TOTAL + '일)'; }
      if (!m.found) vreason = (vreason ? vreason + ' · ' : '') + '회원 매칭 확인 필요';
      var startStr = lSt >= 0 ? _holdDateStr_(r[lSt]) : '';
      out.push({ intakeRow: li + 2, status: lStat >= 0 ? String(r[lStat] || '').trim() : '', kind: kind,
        appliedAt: lTs >= 0 ? _holdDateStr_(r[lTs], true) : '', name: lNm >= 0 ? String(r[lNm] || '') : '', phone: lPh >= 0 ? String(r[lPh] || '') : '',
        start: startStr, wishDays: isNaN(days) ? null : days, end: (!isNaN(days) && /^\d{4}-\d{2}-\d{2}$/.test(startStr)) ? _holdEndCalc_(startStr, days) : '',
        reason: lRe >= 0 ? String(r[lRe] || '') : '', member: { found: m.found, count: m.count, cumDays: m.cumDays }, verdict: verdict, verdictReason: vreason });
    }
    return _json({ ok: true, count: out.length, data: out });
  }

  // ─── 휴회 승인/반려(직원 클릭) — 승인=회원DB 기록(이용일수 앞 새칸 '휴회기간')+증분(휴회횟수·누적일)+상태 진행중, intake 상태 갱신 ───
  //   반려=intake 상태만 반려(회원DB 무변경·잔여 미소비). 검증 3회/총60일/1회 7~60 재검증. 게이트 HOLD_LIVE_T(GM go).
  //   회원 매칭=접수 연락처↔회원DB 전화 1행(fail-closed). 대조키(keyPhone)로 접수행 검증. 행삭제 0(셀 write·칸 insert만). 2026-07-22 시포·GM.
  if (action === 'member_hold_approve') {
    var HOLD_LIVE_T = true;          // ★승인/반영 실기록 게이트 — GM go(2026-07-23) 개통. 역롤백=이 한 줄 false.
    var HOLD_EXTEND_GO_T = false;    // 승인 시 종료일자 가산(잔여일 반영) — 시트 잔여일 수식 실측 후 true.
    var apDecision = String(body.decision || '').trim();
    if (apDecision !== 'approve' && apDecision !== 'reject') return _json({ ok: false, error: 'decision=approve|reject' });
    var apIntakeRow = parseInt(body.intakeRow, 10);
    if (!apIntakeRow || apIntakeRow < 2) return _json({ ok: false, error: 'intakeRow 필수(2 이상)' });
    var ass = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);   // 유효회원 시트(승인 시 기록 대상)
    var aiSh = _holdIntakeSheet_(false);                        // 접수 탭(이전 후 종합접수처 · 배9948)
    if (!aiSh || apIntakeRow > aiSh.getLastRow()) return _json({ ok: false, error: '접수 행 없음' });
    var aiHdr = aiSh.getRange(1, 1, 1, aiSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    function _aiIdx(n){ var w = String(n).replace(/\s/g, ''); for (var i = 0; i < aiHdr.length; i++){ if (aiHdr[i].replace(/\s/g,'') === w) return i; } return -1; }
    var aiPh = _aiIdx('연락처'), aiSt = _aiIdx('휴회시작일'), aiDy = _aiIdx('희망일수'), aiStat = _aiIdx('상태'), aiProc = _aiIdx('처리일시'), aiMemo = _aiIdx('처리메모'), aiKd = _aiIdx('구분');
    var apRowV = aiSh.getRange(apIntakeRow, 1, 1, aiSh.getLastColumn()).getValues()[0];
    var apPhone = aiPh >= 0 ? String(apRowV[aiPh] || '').trim() : '';
    // 대조키(오지목 방지): 클라 keyPhone ↔ 접수행 연락처
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '' && _normPhone_(body.keyPhone) !== _normPhone_(apPhone)) return _json({ ok: false, error: 'row-key-mismatch', detail: '접수 행 검증 실패 — 새로고침 후 다시 시도하세요' });
    if (!HOLD_LIVE_T) return _json({ ok: false, error: 'hold-gated', detail: '휴회 승인/반영은 GM 검증 후 개통됩니다(현재 미개통)' });
    var apNow = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
    if (apDecision === 'reject') {
      if (aiStat >= 0) aiSh.getRange(apIntakeRow, aiStat + 1).setValue('반려');
      if (aiProc >= 0) aiSh.getRange(apIntakeRow, aiProc + 1).setValue(apNow);
      if (aiMemo >= 0 && body.memo) aiSh.getRange(apIntakeRow, aiMemo + 1).setValue(String(body.memo));
      return _json({ ok: true, decision: 'reject', intakeRow: apIntakeRow });
    }
    // approve: 회원DB 전화 매칭(1행 fail-closed)
    var amSh = ass.getSheetByName(MEMBER_SHEET);
    if (!amSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var amHdr = amSh.getRange(1, 1, 1, amSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    function _amIdx(n){ var w = String(n).replace(/\s/g, ''); for (var i = 0; i < amHdr.length; i++){ if (amHdr[i].replace(/\s/g,'').indexOf(w) >= 0) return i; } return -1; }
    var amPh = _amIdx('휴대폰'); if (amPh < 0) return _json({ ok: false, error: '회원 전화 칸 없음' });
    var apPhN = _normPhone_(apPhone), amHits = [];
    var amAll = amSh.getLastRow() >= 2 ? amSh.getRange(2, 1, amSh.getLastRow() - 1, amSh.getLastColumn()).getValues() : [];
    for (var ami = 0; ami < amAll.length; ami++){ if (_normPhone_(amAll[ami][amPh]) === apPhN) amHits.push(ami + 2); }
    if (amHits.length === 0) return _json({ ok: false, error: 'member-not-found', detail: '회원DB에서 일치 회원을 찾을 수 없습니다(전화 확인)' });
    if (amHits.length > 1) return _json({ ok: false, error: 'member-ambiguous', detail: '동일 전화 회원 다수 — 데스크 확인' });
    var amRow = amHits[0];
    var reqStart = aiSt >= 0 ? _holdDateStr_(apRowV[aiSt]) : '';   // 시트 Date 자동변환 정규화(2026-07-23)
    var reqDays = aiDy >= 0 ? parseInt(String(apRowV[aiDy] || '').replace(/[^0-9]/g, ''), 10) : NaN;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(reqStart) || isNaN(reqDays)) return _json({ ok: false, error: 'bad-request', detail: '접수 기간/일수 불량' });
    var reqEnd = _holdEndCalc_(reqStart, reqDays);
    function _amNum(ix){ if (ix < 0) return 0; var raw = String(amSh.getRange(amRow, ix + 1).getValue() || '').replace(/[^0-9\-]/g, ''); var n = parseInt(raw, 10); return isNaN(n) ? 0 : n; }
    var amC = _amNum(_amIdx('휴회횟수')), amD = _amNum(_amIdx('휴회누적일수'));
    var apKind = _holdKindNorm_(aiKd >= 0 ? apRowV[aiKd] : '');   // 연장=하한 면제(2026-07-23 GM)
    var apMin = _holdMinOnce_(apKind);
    if (reqDays < apMin || reqDays > HLD_MAX_ONCE) return _json({ ok: false, error: '휴회 일수 범위(' + apKind + ' ' + apMin + '~' + HLD_MAX_ONCE + '일) 위반: ' + reqDays + '일' });
    if (amC + 1 > HLD_MAX_COUNT) return _json({ ok: false, error: '휴회 횟수 한도 초과(최대 ' + HLD_MAX_COUNT + '회, 현재 ' + amC + '회)' });
    if (amD + reqDays > HLD_MAX_TOTAL) return _json({ ok: false, error: '누적 휴회일수 한도 초과(최대 ' + HLD_MAX_TOTAL + '일, 현재 ' + amD + '+' + reqDays + '일)' });
    // ★GM 지정: '이용일수' 바로 앞에 새 칸 '휴회기간(휴회일수)' 신설(없으면 insertColumnBefore). 값=기간+일수 병기(예 '2026-08-01 ~ 2026-08-30 (30일)'). 시트에도 실제 칸 추가.
    var HOLD_PERIOD_COL = '휴회기간(휴회일수)';
    var _bw = '이용일수'.replace(/\s/g, ''), _bi = -1;
    for (var _bj = 0; _bj < amHdr.length; _bj++){ if (amHdr[_bj].replace(/\s/g,'').indexOf(_bw) >= 0) { _bi = _bj; break; } }
    var _pwN = HOLD_PERIOD_COL.replace(/\s/g, ''), _hasPeriod = false;
    for (var _pj = 0; _pj < amHdr.length; _pj++){ if (amHdr[_pj].replace(/\s/g,'') === _pwN) { _hasPeriod = true; break; } }
    if (!_hasPeriod) {
      if (_bi >= 0) { amSh.insertColumnBefore(_bi + 1); amSh.getRange(1, _bi + 1).setValue(HOLD_PERIOD_COL); }
      else { amSh.getRange(1, amHdr.length + 1).setValue(HOLD_PERIOD_COL); }   // 이용일수 없으면 끝에(정합 유지)
      amHdr = amSh.getRange(1, 1, 1, amSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });   // insert로 인덱스 이동 → 재조회
    }
    function _amIdx2(n){ var w = String(n).replace(/\s/g, ''); for (var i = 0; i < amHdr.length; i++){ if (amHdr[i].replace(/\s/g,'') === w) return i; } return -1; }
    var ciPeriod = _amIdx2(HOLD_PERIOD_COL);
    amSh.getRange(amRow, ciPeriod + 1).setNumberFormat('@'); amSh.getRange(amRow, ciPeriod + 1).setValue(reqStart + ' ~ ' + reqEnd + ' (' + reqDays + '일)');
    // 기존 4칸 정합 기록 + 증분 + 상태(진행중)
    var ciC2 = _miEnsureCol_(amSh, amHdr, '휴회횟수'), ciD2 = _miEnsureCol_(amSh, amHdr, '휴회누적일수'), ciS2 = _miEnsureCol_(amSh, amHdr, '휴회시작일'), ciE2 = _miEnsureCol_(amSh, amHdr, '휴회종료일'), ciStat2 = _miEnsureCol_(amSh, amHdr, '휴회접수상태');
    amSh.getRange(amRow, ciS2 + 1).setNumberFormat('@'); amSh.getRange(amRow, ciS2 + 1).setValue(reqStart);
    amSh.getRange(amRow, ciE2 + 1).setNumberFormat('@'); amSh.getRange(amRow, ciE2 + 1).setValue(reqEnd);
    amSh.getRange(amRow, ciC2 + 1).setValue(amC + 1);
    amSh.getRange(amRow, ciD2 + 1).setValue(amD + reqDays);
    amSh.getRange(amRow, ciStat2 + 1).setValue('진행중');
    var extendedA = false;
    if (HOLD_EXTEND_GO_T) { var ciME2 = _amIdx2('종료일자'); if (ciME2 >= 0) { var _eca = amSh.getRange(amRow, ciME2 + 1); if (!_eca.getFormula()) { var _eva = _eca.getValue(); if (_eva instanceof Date && !isNaN(_eva.getTime())) { _eva.setDate(_eva.getDate() + reqDays); _eca.setValue(_eva); extendedA = true; } } } }
    // intake 상태 갱신(승인)
    if (aiStat >= 0) aiSh.getRange(apIntakeRow, aiStat + 1).setValue('승인');
    if (aiProc >= 0) aiSh.getRange(apIntakeRow, aiProc + 1).setValue(apNow);
    return _json({ ok: true, decision: 'approve', intakeRow: apIntakeRow, memberRow: amRow, count: amC + 1, cumDays: amD + reqDays, period: reqStart + ' ~ ' + reqEnd, extended: extendedA });
  }

  // ─── 휴회 회원 상태전이(직원) — 승인 후 회원 라이프사이클: 진행중(휴회중)→완료(휴회 종료). 회원DB '휴회접수상태'만 갱신(잔여 재소비 없음).
  //   접수대기→진행중 확정·증분은 member_hold_approve가 담당. 이 액션은 그 이후 진행중↔완료 라벨 전이 전용. 게이트 HOLD_LIVE_T. 2026-07-22 시포·GM.
  if (action === 'member_hold_transition') {
    var HOLD_LIVE_T2 = true;    // ★상태전이 실기록 게이트 — GM go(2026-07-23) 개통. 역롤백=이 한 줄 false.
    var htN = String(body.status || '').trim();
    if (htN !== '완료' && htN !== '진행중') return _json({ ok: false, error: 'status=완료|진행중 중 하나' });
    var tSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!tSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var tHdr = tSh.getRange(1, 1, 1, tSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    var tPhI = -1;
    for (var _up = 0; _up < tHdr.length; _up++) { var _uph = tHdr[_up].replace(/\s/g, ''); if (_uph.indexOf('휴대폰') >= 0 || _uph.indexOf('전화') >= 0 || _uph.indexOf('연락처') >= 0) { tPhI = _up; break; } }
    var tRow = parseInt(body.rowIndex, 10);
    var _tRk = _rowKeyParts_(body), tTsI = -1;
    if (_tRk) { var _UK = ['등록일자', '등록 일자', '타임스탬프', '등록일', '가입일']; for (var _ut = 0; _ut < tHdr.length; _ut++) { var _uth = tHdr[_ut].replace(/\s/g, ''); for (var _utk = 0; _utk < _UK.length; _utk++) { if (_uth.indexOf(_UK[_utk].replace(/\s/g, '')) >= 0) { tTsI = _ut; break; } } if (tTsI >= 0) break; } }
    if (_tRk && tTsI >= 0 && tPhI >= 0) {
      var _tFp = _findRowsByKey_(tSh, tTsI, tPhI, _tRk.ts, _tRk.phone,
                                 _nameColIdx_(tHdr), _tRk.name);
      if (_tFp.length === 1) tRow = _tFp[0];
      else if (_tFp.length === 0) return _json({ ok: false, error: 'rowkey-not-found', detail: '회원 행 확인 불가 — 목록 새로고침 후 다시 시도하세요' });
      else return _json({ ok: false, error: 'rowkey-ambiguous', detail: '지문키 중복 매칭 — 목록 새로고침 후 다시 시도하세요' });
    } else if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      if (tPhI >= 0 && tRow >= 2 && tRow <= tSh.getLastRow()) {
        var _tRowPh = _normPhone_(tSh.getRange(tRow, tPhI + 1).getValue()), _tKeyPh = _normPhone_(body.keyPhone);
        if (_tRowPh && _tKeyPh && _tRowPh !== _tKeyPh) return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패 — 목록 새로고침 후 다시 시도하세요' });
      } else return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처 확인 후 목록 새로고침하여 다시 시도하세요' });
    } else {
      return _json({ ok: false, error: 'row-key-unverified', detail: '행 확인 불가 — 연락처/목록 새로고침 후 다시 시도하세요' });
    }
    if (!tRow || tRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var ciStatU = _miEnsureCol_(tSh, tHdr, '휴회접수상태');
    if (!HOLD_LIVE_T2) return _json({ ok: false, error: 'hold-gated', detail: '휴회 상태 반영은 GM 검증 후 개통됩니다(현재 미개통)' });
    tSh.getRange(tRow, ciStatU + 1).setValue(htN);
    return _json({ ok: true, rowIndex: tRow, status: htN });
  }

  // ─── CPO 오늘 현황(PII 미노출 집계): 오늘/이번달 문의·등록 건수 2026-06-24 GM ───
  if (action === 'cpo_today_stats') {
    var ctCache = CacheService.getScriptCache();
    var ctCached = ctCache.get('cpo_today_stats_v5');
    if (ctCached) return _json(JSON.parse(ctCached));
    var ctTz = 'Asia/Seoul';
    var ctToday = Utilities.formatDate(new Date(), ctTz, 'yyyy-MM-dd');
    var ctMonth = ctToday.slice(0, 7);
    var ctTI = 0, ctMI = 0, ctTR = 0, ctMR = 0;
    var ctActive = 0, ctEnded = 0, ctLoss = 0, ctMonthLoss = 0, ctLossDated = false;
    // 문의: 26년 신규문의 타임스탬프
    try {
      var ciSh = _miSheet_();
      if (ciSh && ciSh.getLastRow() >= 2) {
        var ciH = _miHeaders_(ciSh);
        var ciTs = _miColIdx_(ciH, ['타임스탬프','접수일','날짜']);
        var ciNm = _miColIdx_(ciH, ['성함','이름']);
        var ciPg = _miColIdx_(ciH, ['관심 있는 프로그램 종류','관심 있는 프로그램 종목','관심프로그램','프로그램']);
        var ciSt = _miColIdx_(ciH, ['진행현황','진행상황','진행상태','상태']);   // 소프트 삭제(중복) 제외용. 2026-08-05 시토.
        if (ciTs >= 0) {
          var ciData = ciSh.getRange(2, 1, ciSh.getLastRow() - 1, ciH.length).getValues();
          for (var ci = 0; ci < ciData.length; ci++) {
            if (ciNm >= 0 && !String(ciData[ci][ciNm] || '').trim() && !ciData[ci][ciTs]) continue;
            if (ciSt >= 0 && String(ciData[ci][ciSt] || '').trim() === MI_DUP_DELETED_STATUS) continue;   // ★소프트 삭제 제외(2026-08-05)
            // 멤버십 문의 집계: 프로그램 미기재(빈칸)는 포함(목록과 분모 일치), 명시적 비멤버십(강습 등)만 제외.
            if (ciPg >= 0) { var ciPv = String(ciData[ci][ciPg] || '').trim(); if (ciPv && ciPv.indexOf('플래티넘') < 0 && ciPv.indexOf('노블레스') < 0) continue; }
            var ciD = _miToISO_(ciData[ci][ciTs]);
            if (ciD === ctToday) ctTI++;
            if (ciD && ciD.slice(0, 7) === ctMonth) ctMI++;
          }
        }
      }
    } catch (eCi) {}
    // 등록 + 회원 현황(유효/종료/금일 LOSS): 유효회원 시트
    var ctMemberSs = null;   // 아래 두 블록이 함께 쓰는 스프레드시트 핸들(2026-08-07 시토)
    try {
      // ★2026-08-07 시토(배117 잔여 ②) — 같은 스프레드시트를 한 요청에서 두 번 열던 것을
      //   한 번만 열고 아래 법인 카운트와 함께 쓴다(openById 는 매번 원격 왕복이다).
      ctMemberSs = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
      var crSh = ctMemberSs.getSheetByName(MEMBER_SHEET);
      if (crSh && crSh.getLastRow() >= 2) {
        var crCols = crSh.getLastColumn();
        var crHdr = crSh.getRange(1, 1, 1, crCols).getValues()[0].map(function(v){ return String(v).trim(); });
        function _crIdx(want){ var w = String(want).replace(/\s/g, ''); for (var i = 0; i < crHdr.length; i++){ if (crHdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; } return -1; }
        var crRegI  = _crIdx('등록일자');
        var crNmI   = _crIdx('회원명');
        var crRemI  = _crIdx('잔여일');
        var crReI   = _crIdx('재등록분류');
        // 신규 판정용 두 칸(2026-08-06 시포) — 카드가 재등록까지 세던 것을 목록과 같은 기준으로 맞춘다.
        var crClsI  = _crIdx('등록분류'); if (crClsI < 0) crClsI = _crIdx('등록 분류');
        var crSeqI  = _crIdx('등록회차'); if (crSeqI < 0) crSeqI = _crIdx('등록 회차');
        // LOSS 날짜 칸: LOSS일자→이탈일→해지일→종료일(member_active_summary._maIdx 체인과 동일). 2026-08-10 시토(배483).
        //   '종료일'을 맨 마지막에 두는 이유 = 이 시트의 '종료\n일자'(다른 칸)와 구분 안 돼 오답나므로.
        var crLossI = _crIdx('LOSS일자'); if (crLossI < 0) crLossI = _crIdx('이탈일'); if (crLossI < 0) crLossI = _crIdx('해지일'); if (crLossI < 0) crLossI = _crIdx('종료일');
        ctLossDated = (crLossI >= 0);
        var crAll = crSh.getRange(2, 1, crSh.getLastRow() - 1, crCols).getValues();
        for (var cr = 0; cr < crAll.length; cr++) {
          var crow = crAll[cr];
          // 등록 집계(등록일자 — 금일/금월 신규)
          if (crRegI >= 0) {
            var cv = crow[crRegI];
            var crD = (cv instanceof Date && !isNaN(cv.getTime())) ? Utilities.formatDate(cv, ctTz, 'yyyy-MM-dd') : _miToISO_(cv);
            // ★2026-08-06 시포 — 카드 제목이 「신규 멤버십 등록현황」인데 재등록·대기까지 세고 있었다.
            //   목록과 같은 판정(_isNewRegistration_)을 태워 두 숫자를 한 기준으로 맞춘다.
            var crIsNew = _isNewRegistration_(
              crClsI >= 0 ? crow[crClsI] : '',
              crReI  >= 0 ? crow[crReI]  : '',
              crSeqI >= 0 ? crow[crSeqI] : ''
            );
            if (crIsNew && crD === ctToday) ctTR++;
            if (crIsNew && crD && crD.slice(0, 7) === ctMonth) ctMR++;
          }
          // 회원 현황(회원명 있는 행만): 유효 = 잔여일>=0(만료 당일까지 유효) & 이탈표시 없음. 2026-07-31 경계 정정.
          var crNm = crNmI >= 0 ? String(crow[crNmI] == null ? '' : crow[crNmI]).trim() : '';
          if (!crNm) continue;
          // 유효/종료 판정 = _memberIsValid_ 단일 함수(약속 L01, 배354 2026-08-04) — 종전엔 잔여일
          //   미기재(NaN)를 여기만 '종료'로 세어 member_active_list(배286)와 짝이 안 맞았다.
          var crValid = _memberIsValid_(crRemI >= 0 ? crow[crRemI] : '', crReI >= 0 ? crow[crReI] : '');
          if (crValid) ctActive++; else ctEnded++;
          // 금일 LOSS: 이탈일(또는 해지/종료일)이 오늘 + 유효 아님 — 날짜 칸 없으면 0 유지
          if (crLossI >= 0 && !crValid) {
            var lv = crow[crLossI];
            var lD = (lv instanceof Date && !isNaN(lv.getTime())) ? Utilities.formatDate(lv, ctTz, 'yyyy-MM-dd') : _miToISO_(lv);
            if (lD === ctToday) ctLoss++;
            if (lD && lD.slice(0, 7) === ctMonth) ctMonthLoss++;
          }
        }
      }
    } catch (eCr) {}
    // 법인회원 수(별도 시트 gid 1612064257 '법인현황'). 2026-06-29 시포.
    // 2026-08-13 시포·GM — 회원명만 있으면 세던 것을 '지금 유효한 법인'만 세도록 고쳤다.
    //   그 전엔 이미 끝난 회원(LOSS일자가 적혔거나 종료일자가 지난 행)도 함께 세어 실제보다 많았다
    //   (실측: 32명으로 나왔으나 그중 1명은 2026-07-21 종료 — 진짜는 31명. GM 지적).
    //   유효회원 시트(memberActive)는 이미 잔여일 기준으로 끝난 사람을 빼고 세는데 법인 시트만 안 그랬다 —
    //   같은 카드 안에서 두 숫자의 기준이 달랐던 것이 원인이다.
    var ctCorp = 0;
    try {
      var ctCorpSs = ctMemberSs || SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID), ctCorpSh = null, ctCorpShs = ctCorpSs.getSheets();
      for (var cci = 0; cci < ctCorpShs.length; cci++) { if (ctCorpShs[cci].getSheetId() === 1612064257) { ctCorpSh = ctCorpShs[cci]; break; } }
      if (!ctCorpSh) ctCorpSh = ctCorpSs.getSheetByName('법인현황');
      if (ctCorpSh && ctCorpSh.getLastRow() >= 2) {
        var ctCorpHdr = ctCorpSh.getRange(1, 1, 1, ctCorpSh.getLastColumn()).getValues()[0];
        function _ctCorpIdx(want) {
          var w = String(want).replace(/\s/g, '');
          for (var i = 0; i < ctCorpHdr.length; i++) { if (String(ctCorpHdr[i]).replace(/\s/g, '').indexOf(w) >= 0) return i; }
          return -1;
        }
        var ctCorpNmI = _ctCorpIdx('회원명'); if (ctCorpNmI < 0) ctCorpNmI = 0;
        var ctCorpEndI = _ctCorpIdx('종료일자'), ctCorpLossI = _ctCorpIdx('LOSS일자');
        var ctCorpRows = ctCorpSh.getRange(2, 1, ctCorpSh.getLastRow() - 1, ctCorpSh.getLastColumn()).getValues();
        function _ctCorpDate(v) {
          if (v instanceof Date) return Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
          return String(v == null ? '' : v).trim().slice(0, 10);
        }
        for (var ccd = 0; ccd < ctCorpRows.length; ccd++) {
          var ctCorpRow = ctCorpRows[ccd];
          if (!String(ctCorpRow[ctCorpNmI] == null ? '' : ctCorpRow[ctCorpNmI]).trim()) continue;
          if (ctCorpLossI >= 0 && _ctCorpDate(ctCorpRow[ctCorpLossI])) continue;          // LOSS 기록됨 = 끝난 회원
          if (ctCorpEndI >= 0) {
            var ctCorpEnd = _ctCorpDate(ctCorpRow[ctCorpEndI]);
            if (ctCorpEnd && ctCorpEnd < ctToday) continue;                                // 종료일자가 이미 지남
          }
          ctCorp++;
        }
      }
    } catch (eCorp) {}
    // LOSS 보관 시트로 옮긴 지난 연도분을 더한다 — 옮기기 전과 같은 누적 숫자를 유지한다(2026-08-13).
    ctEnded += _lossArchiveCount_(ctMemberSs);
    var ctResult = { ok: true, date: ctToday, todayInquiry: ctTI, monthInquiry: ctMI, todayReg: ctTR, monthReg: ctMR, memberActive: ctActive, memberCorp: ctCorp, memberEnded: ctEnded, todayLoss: ctLoss, monthLoss: ctMonthLoss, lossDated: ctLossDated };
    try { ctCache.put('cpo_today_stats_v5', JSON.stringify(ctResult), 60); } catch (eCc) {}
    return _json(ctResult);
  }

  // ─── 이탈 현황 실측(1단계) — 유효회원 시트 잔여일·재등록분류로 유효/이탈/이탈율 + 갱신 임박 리스트. 2026-07-02 시포·GM ───
  if (action === 'cpo_churn_stats') {
    var czActive = 0, czLoss = 0, czMonthLoss = 0, czRenew = [];
    // 당월 LOSS 판정용 현재 연-월(KST) — cpo_today_stats 와 동일한 LOSS일자 파싱 방식 재사용. 2026-07-03 시포·GM
    var czTz = 'Asia/Seoul';
    var czMonth = Utilities.formatDate(new Date(), czTz, 'yyyy-MM');
    try {
      var czSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
      if (czSh && czSh.getLastRow() >= 2) {
        var czCols = czSh.getLastColumn();
        var czHdr = czSh.getRange(1, 1, 1, czCols).getValues()[0].map(function(v){ return String(v).trim(); });
        function _czIdx(want){ var w = String(want).replace(/\s/g, ''); for (var i = 0; i < czHdr.length; i++){ if (czHdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; } return -1; }
        var czNm = _czIdx('회원명'); var czRem = _czIdx('잔여일'); var czRe = _czIdx('재등록분류');
        var czPg = _czIdx('등급'); if (czPg < 0) czPg = _czIdx('상품'); if (czPg < 0) czPg = _czIdx('프로그램');
        // LOSS일자 컬럼(cpo_today_stats 와 동일 우선순위: LOSS일자→이탈일→해지일→종료일) 2026-08-10 시토(배483).
        var czLossI = _czIdx('LOSS일자'); if (czLossI < 0) czLossI = _czIdx('이탈일'); if (czLossI < 0) czLossI = _czIdx('해지일'); if (czLossI < 0) czLossI = _czIdx('종료일');
        var _CZ_LOSS = { 'LOSS':1, '환불':1, '양도LOSS':1 };
        var czAll = czSh.getRange(2, 1, czSh.getLastRow() - 1, czCols).getValues();
        for (var czr = 0; czr < czAll.length; czr++) {
          var czrow = czAll[czr];
          var czName = czNm >= 0 ? String(czrow[czNm] == null ? '' : czrow[czNm]).trim() : '';
          if (!czName) continue;
          var czRemRaw = czRem >= 0 ? String(czrow[czRem] == null ? '' : czrow[czRem]).replace(/[^0-9\-]/g, '') : '';
          var czRemN = (czRemRaw === '' || czRemRaw === '-') ? NaN : parseInt(czRemRaw, 10);
          var czReV = czRe >= 0 ? String(czrow[czRe] == null ? '' : czrow[czRe]).trim() : '';
          var czIsLoss = !!_CZ_LOSS[czReV] || (!isNaN(czRemN) && czRemN < 0);  // 2026-07-31 경계 정정 — LOSS 전환은 잔여일 -1일부터(구: czRemN<=0). 실무진 신고 FB260731-090542.
          if (czIsLoss) {
            czLoss++;
            // 당월 LOSS: LOSS일자(이탈일/해지일/종료일)가 현재 연-월인 건만
            if (czLossI >= 0) {
              var czlv = czrow[czLossI];
              var czlD = (czlv instanceof Date && !isNaN(czlv.getTime())) ? Utilities.formatDate(czlv, czTz, 'yyyy-MM-dd') : _miToISO_(czlv);
              if (czlD && czlD.slice(0, 7) === czMonth) czMonthLoss++;
            }
            continue;
          }
          czActive++;
          if (!isNaN(czRemN) && czRemN >= 0 && czRemN <= 30) {  // 갱신임박 목록도 새 유효경계(잔여일>=0)와 일치시킴 — 만료 당일(0)도 목록에 포함
            czRenew.push({ name: czName, rem: czRemN, program: czPg >= 0 ? String(czrow[czPg] || '').trim() : '' });
          }
        }
      }
    } catch (eCz) {}
    czRenew.sort(function(a, b){ return a.rem - b.rem; });
    czLoss += _lossArchiveCount_();   // 보관 시트분 합산 — 누적 이탈율 분모·분자 유지(2026-08-13)
    var czTotal = czActive + czLoss;
    var czRate = czTotal > 0 ? Math.round(czLoss / czTotal * 1000) / 10 : 0;
    // 당월 LOSS율 — 분모=현재 유효+당월LOSS 근사(월초 스냅샷 없음, 라벨에 명시). 2026-07-03 시포·GM
    var czMonthTotal = czActive + czMonthLoss;
    var czMonthRate = czMonthTotal > 0 ? Math.round(czMonthLoss / czMonthTotal * 1000) / 10 : 0;
    return _json({ ok: true, activeCount: czActive, lossCount: czLoss, lossRate: czRate, monthLossCount: czMonthLoss, monthLossRate: czMonthRate, renewCount: czRenew.length, renewSoon: czRenew.slice(0, 200) });
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
      var t = ts ? _normTs_(ts).getTime() : NaN;   // 단일 정규화 SSOT
      return !isNaN(t) && t >= fcF && t <= fcT;
    }
    // ─── 정밀 분자 opt-in(2026-07-04 시포) — numerator==='registered'(또는 precise==='1')일 때만 등록일 기간필터를 분자에 적용.
    //     파라미터 없으면 이 블록 전부 미실행 — 기존 누적 로직 100% 그대로(회귀 0, 시모 마케팅 대시보드 등 기존 소비처 무영향).
    var fcPrecise = (String(body.numerator || '') === 'registered' || String(body.precise || '') === '1');
    function _fcDateISO_(v) {
      if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd');
      return _miToISO_(v);
    }
    function _fcDateInRange_(iso) {
      if (!iso) return false;
      if (fcFrom && iso < fcFrom) return false;
      if (fcTo   && iso > fcTo)   return false;
      return true;
    }
    // 캐시 조회 (범위별 키 — 기간 필터 + 분자모드 버전)
    var fcCache = CacheService.getScriptCache();
    var fcCacheKey = 'fc_v4_' + (fcPrecise ? 'reg_' : 'acc_') + fcFrom + '_' + fcTo;  // v4: byType(유형별) 추가 2026-07-27 배179 — 구조 변경이라 캐시키 올림(옛 캐시가 byType 없는 응답 반환 방지) / v3: 전환에 강습 등록 합산 반영(2026-07-03 시모) · 분자모드 분리(2026-07-04 시포) — 구캐시 무효화
    var fcHit = fcCache.get(fcCacheKey);
    if (fcHit && !_nc) return _json(JSON.parse(fcHit));

    // ① 회원부 전화번호 Set 생성
    var memberSs  = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var memberSh  = memberSs.getSheetByName(MEMBER_SHEET);
    var memberLast = memberSh.getLastRow();
    var memberSet = {};
    var memberRegMap = {};  // 정밀모드 전용: phone → 등록일(원본 Date/문자열). member_match_autostamp_(:4136-4164) 로직 이식.
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
      // 정밀모드에서만 등록일 맵 구성(비정밀 경로는 미실행 — 성능·동작 무영향)
      if (fcPrecise && phoneColIdx >= 0) {
        function _fcHdrIdx_(name) {
          var want = String(name).replace(/\s+/g, '');
          for (var hi = 0; hi < memberHeaders.length; hi++) {
            if (String(memberHeaders[hi]).replace(/\s+/g, '') === want) return hi;   // 공백·줄바꿈 무시 매칭(등록\n일자 대응)
          }
          return -1;
        }
        var dateColIdx = _fcHdrIdx_(MEMBER_DATE_COL);
        if (dateColIdx >= 0) {
          var memberFullRows = memberSh.getRange(2, 1, memberLast - 1, memberSh.getLastColumn()).getValues();
          memberFullRows.forEach(function(r) {
            var n = normalizePhone_(r[phoneColIdx]);
            if (n) memberRegMap[n] = r[dateColIdx];
          });
        }
      }
    }

    // ①-b 강습 등록자 전화 Set (팀시트 SUC 로스터 실시간 수집 — 2026-07-03 시모, GM 지시)
    // 전환 판정을 멤버십 전화매칭 단독에서 '멤버십 ∪ 강습등록' 전화 union으로 확대(아래 ②/②-b 매칭부).
    // 동일인이 멤버십+강습 모두 있어도 union이라 1회만 카운트(중복 방지).
    // 정직성 한계: 팀시트에 연락처 열이 없거나 탐지 실패한 종목은 그 등록자가 조용히 빠짐(날조 대신 누락 인정).
    var lessonSet = {};
    ['성인강습', '유소년강습'].forEach(function(fcType) {
      _collectLessonRoster_(fcType).forEach(function(m) {
        var n = _normPhone_(m.phone);
        if (n) lessonSet[n] = true;
      });
    });

    // ①-c 강습 등록원장 전화→등록일 맵 (정밀모드 전용 — lesson_registry_list :2503-2521 패턴 재사용)
    //     강습원장 시드(2026-06-27) 이전 등록자는 기준선 '2000-01-01'이라 기간필터서 제외됨 = 정직한 과소집계(convBasis에 명시).
    var lessonRegMap = {};  // phone → 등록일 ISO(가장 이른 날짜 채택 — 동일인 다종목 등록 시 최초 전환 시점)
    if (fcPrecise) {
      try {
        _syncLessonRegistry_();
        var fcLrSh   = _lessonRegSheet_();
        var fcLrLast = fcLrSh.getLastRow();
        if (fcLrLast >= 2) {
          var fcLrRows = fcLrSh.getRange(2, 1, fcLrLast - 1, _LESSON_REG_HEADER.length).getValues();
          fcLrRows.forEach(function(row) {
            var n = _normPhone_(row[3]);   // 전화
            if (!n) return;
            var iso = _fcDateISO_(row[5]); // 등록일
            if (iso && (!lessonRegMap.hasOwnProperty(n) || iso < lessonRegMap[n])) lessonRegMap[n] = iso;
          });
        }
      } catch (eFcLr) {}
    }

    // 전환 판정 — 비정밀(기존): 전화매칭만. 정밀(opt-in): 전화매칭 + 등록일 ∈ [from,to].
    function _fcConverted_(phone) {
      if (!phone) return { memberOnly: false, any: false };
      if (!fcPrecise) {
        var mo0 = !!memberSet[phone];
        return { memberOnly: mo0, any: (mo0 || !!lessonSet[phone]) };
      }
      var mIso = memberRegMap.hasOwnProperty(phone) ? _fcDateISO_(memberRegMap[phone]) : '';
      var mOk  = _fcDateInRange_(mIso);
      var lIso = lessonRegMap.hasOwnProperty(phone) ? lessonRegMap[phone] : '';
      var lOk  = _fcDateInRange_(lIso);
      return { memberOnly: mOk, any: (mOk || lOk) };
    }

    // ②+②-b 문의접수 시트 ∪ 구글폼 — 공용 SSOT(_collectAllInquiryRows_)로 단일 순회.
    //   funnel_conversion_detail과 동일 함수·동일 로우 집합·동일 채널판정을 써야 "채널 건수 클릭→명단"이
    //   항상 정합한다(2026-07-20 GM 실사용 제보로 통합 — 과거엔 이 블록이 아래 명단 액션과 각자 따로 순회).
    var totalInq = 0, totalConv = 0, totalConvMemberOnly = 0;  // memberOnly=구버전(멤버십만) 비교용 — 투명성 유지
    var byChannel = {};  // { 채널명: {inquiries, converted} }
    // [배179 · 2026-07-27 GM 지시 '멤버십/성인강습/유소년강습 구분해서 확실하게']
    //   같은 순회에서 유형별로도 담는다 — 새 순회·새 액션 없음(비용 0). row.type 은
    //   _collectAllInquiryRows_ 가 이미 싣고 있던 값(문의유형/폼 유형)이라 새 원천도 아니다.
    //   빈 값은 '(미분류)'로 모아 화면에서 보이게 한다 — 숨기면 합계가 안 맞아 더 헷갈린다.
    var byType = {};
    _collectAllInquiryRows_(_fcInPeriod).forEach(function(row) {
      var channel = row.channel;
      var ftype = String(row.type || '').trim() || '(미분류)';
      totalInq++;
      if (!byChannel[channel]) byChannel[channel] = { inquiries: 0, converted: 0 };
      byChannel[channel].inquiries++;
      if (!byType[ftype]) byType[ftype] = { inquiries: 0, converted: 0, convertedMemberOnly: 0 };
      byType[ftype].inquiries++;

      var fcConv = _fcConverted_(row.phone);
      if (fcConv.memberOnly) { totalConvMemberOnly++; byType[ftype].convertedMemberOnly++; }
      if (fcConv.any) {
        totalConv++;
        byChannel[channel].converted++;
        byType[ftype].converted++;
      }
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
      total: {
        inquiries: totalInq, converted: totalConv, rate: rate,
        convertedMemberOnly: totalConvMemberOnly,  // 구버전(멤버십 전화매칭만) — 강습 합산 전 값, 투명성 위해 상시 병기
        lessonAdded: totalConv - totalConvMemberOnly  // 강습 등록 union으로 추가된 순증분
      },
      byChannel: channelArr,
      byType: Object.keys(byType).map(function(t) {
        var d = byType[t];
        return {
          type: t,
          inquiries: d.inquiries,
          converted: d.converted,
          convertedMemberOnly: d.convertedMemberOnly,
          rate: d.inquiries > 0 ? Math.round((d.converted / d.inquiries) * 1000) / 10 : 0
        };
      }).sort(function(a, b) { return b.inquiries - a.inquiries; }),
      periodMode: fcPeriod,
      period: { from: fcFrom, to: fcTo },
      convBasis: fcPrecise
        ? '등록일 기준 기간정합 · 단 강습원장 시드(2026-06-27) 이전 등록자는 기준선(2000-01-01)이라 기간필터서 제외=과소집계'
        : (fcPeriod
            ? '문의=선택기간(시각 기준) / 전환=선택기간 문의 중 유효회원∪강습등록 전화매칭(등록일 미사용 → 기간 내 문의가 전환된 누적값)'
            : '전체 누적 — 유효회원∪강습등록 전화매칭'),
      generatedAt: _now()
    };
    // 정밀모드 표시 — 비정밀(기존) 경로는 필드 자체를 추가하지 않아 응답 스키마 100% 동일 유지(회귀 0).
    if (fcPrecise) fcResult.numeratorMode = 'registered';
    // 캐시 저장 (범위별 키 — 100KB 초과 시 생략)
    try { fcCache.put(fcCacheKey, JSON.stringify(fcResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(fcResult);
  }

  // ─── 채널별 가입전환 상세 명단 (GM 지시 2026-07-20 · 배834 묶음C) ───
  // funnel_conversion(byChannel, 비정밀·전체누적 경로)과 완전히 동일한 매칭 규칙(전화매칭:
  // 유효회원∪강습등록)을 재사용 — "전환 N건 = 이 사람들"의 채널별 건수가 그 액션의 byChannel[ch].converted
  // 와 항상 일치하도록 로직을 복제(회귀 없음, 읽기 전용 — 원본 시트 미변경).
  // 개인정보 최소화: 연락처는 서버에서 뒷 4자리만 자름(전체 번호 응답 없음).
  if (action === 'funnel_conversion_detail') {
    // from/to(YYYY-MM-DD KST) 있으면 문의 시각 기준 기간필터(funnel_conversion 비정밀 경로와 동일 규칙) —
    // 없으면 전체 누적. 이래야 기간뷰에서 '가입 N건' 클릭 시 명단 건수가 그 기간의 byChannel.converted와 정합.
    var fdFrom = body.from || '';
    var fdTo   = body.to   || '';
    var fdPeriod = !!(fdFrom && fdTo);
    var fdF = fdPeriod ? new Date(fdFrom + 'T00:00:00+09:00').getTime() : 0;
    var fdT = fdPeriod ? new Date(fdTo   + 'T23:59:59+09:00').getTime() : 0;
    function _fdInPeriod_(ts) {
      if (!fdPeriod) return true;
      var t = ts ? _normTs_(ts).getTime() : NaN;
      return !isNaN(t) && t >= fdF && t <= fdT;
    }
    var fdCache = CacheService.getScriptCache();
    var fdCacheKey = 'fcd_v2_' + fdFrom + '_' + fdTo;  // v2: 강습원장 시드(2000-01-01) placeholder 확인불가 처리 반영 — 구캐시 무효화
    var fdHit = fdCache.get(fdCacheKey);
    if (fdHit && !_nc) return _json(JSON.parse(fdHit));

    // ① 회원부 전화 Set + 등록일 맵(상세 명단은 등록일 표시가 목적이라 항상 구성 — 정밀모드 게이트 없음)
    var fdMemberSs   = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID);
    var fdMemberSh   = fdMemberSs.getSheetByName(MEMBER_SHEET);
    var fdMemberLast = fdMemberSh.getLastRow();
    var fdMemberSet    = {};
    var fdMemberRegMap = {};
    if (fdMemberLast >= 2) {
      var fdMemberHeaders = fdMemberSh.getRange(1, 1, 1, fdMemberSh.getLastColumn()).getValues()[0];
      var fdPhoneColIdx = fdMemberHeaders.indexOf(MEMBER_PHONE_COL);
      var fdDateColIdx = -1;
      (function() {
        var want = String(MEMBER_DATE_COL).replace(/\s+/g, '');
        for (var hi = 0; hi < fdMemberHeaders.length; hi++) {
          if (String(fdMemberHeaders[hi]).replace(/\s+/g, '') === want) { fdDateColIdx = hi; return; }
        }
      })();
      if (fdPhoneColIdx >= 0) {
        var fdMemberRows = fdMemberSh.getRange(2, 1, fdMemberLast - 1, fdMemberSh.getLastColumn()).getValues();
        fdMemberRows.forEach(function(r) {
          var n = normalizePhone_(r[fdPhoneColIdx]);
          if (!n) return;
          fdMemberSet[n] = true;
          if (fdDateColIdx >= 0) fdMemberRegMap[n] = r[fdDateColIdx];
        });
      }
    }

    // ①-b 강습 등록자 전화 Set + 종목(phone → sport, funnel_conversion과 동일 로스터 소스)
    var fdLessonSet = {};
    var fdLessonSportMap = {};
    ['성인강습', '유소년강습'].forEach(function(fdType) {
      _collectLessonRoster_(fdType).forEach(function(m) {
        var n = _normPhone_(m.phone);
        if (!n) return;
        fdLessonSet[n] = true;
        if (!fdLessonSportMap.hasOwnProperty(n)) fdLessonSportMap[n] = m.sport;
      });
    });

    // ①-c 강습 등록원장 전화→등록일 맵(정밀모드와 동일 소스·로직 재사용, 게이트 없이 항상 실행)
    var fdLessonRegMap = {};
    try {
      _syncLessonRegistry_();
      var fdLrSh   = _lessonRegSheet_();
      var fdLrLast = fdLrSh.getLastRow();
      if (fdLrLast >= 2) {
        var fdLrRows = fdLrSh.getRange(2, 1, fdLrLast - 1, _LESSON_REG_HEADER.length).getValues();
        fdLrRows.forEach(function(row) {
          var n = _normPhone_(row[3]);   // 전화
          if (!n) return;
          var iso = _miToISO_(row[5]);   // 등록일
          if (iso === '2000-01-01') return;  // 원장 시드 기준선 placeholder(_syncLessonRegistry_ 시드모드) — 실제 등록일 아님, 확인불가로 취급(날조 금지)
          if (iso && (!fdLessonRegMap.hasOwnProperty(n) || iso < fdLessonRegMap[n])) fdLessonRegMap[n] = iso;
        });
      }
    } catch (eFdLr) {}

    function _fdRegDate_(phone) {
      if (fdMemberRegMap.hasOwnProperty(phone)) {
        var v = fdMemberRegMap[phone];
        var iso = (v instanceof Date && !isNaN(v.getTime())) ? Utilities.formatDate(v, 'Asia/Seoul', 'yyyy-MM-dd') : _miToISO_(v);
        if (iso) return iso;
      }
      if (fdLessonRegMap.hasOwnProperty(phone)) return fdLessonRegMap[phone];
      return null;  // 원장에서 등록일 미확인 — 프론트 '확인불가' 표기(날조 금지)
    }
    // funnel_conversion 비정밀 경로와 동일 판정(전화매칭만, 등록일 미사용) — byChannel.converted 건수와 항상 정합.
    function _fdConverted_(phone) {
      if (!phone) return { memberOnly: false, lessonOnly: false, any: false };
      var mo = !!fdMemberSet[phone];
      var lo = !!fdLessonSet[phone];
      return { memberOnly: mo && !lo, lessonOnly: lo && !mo, any: (mo || lo) };
    }
    function _fdPhone4_(phone) { return (phone && phone.length >= 4) ? phone.slice(-4) : '확인불가'; }
    function _fdBasisLabel_(conv) { return conv.memberOnly ? '멤버십 전화매칭' : (conv.lessonOnly ? '강습등록 전화매칭' : '멤버십+강습등록 전화매칭'); }
    function _fdTypeLabel_(phone, fallback) {
      return fdLessonSportMap.hasOwnProperty(phone) ? fdLessonSportMap[phone] : (fallback || '확인불가');
    }

    var fdByChannel = {};  // { 채널명: [ {name, phone4, type, inquiryDate, regDate, regDateConfirmed, matchBasis} ... ] }
    function _fdPush_(channel, rec) {
      if (!fdByChannel[channel]) fdByChannel[channel] = [];
      fdByChannel[channel].push(rec);
    }

    // ②+②-b 문의접수 시트 ∪ 구글폼 — 공용 SSOT(_collectAllInquiryRows_)로 단일 순회, funnel_conversion과
    //   동일 로우 집합·동일 채널판정(2026-07-20 GM 실사용 제보로 통합 — 채널 건수 클릭→명단 정합 보장).
    _collectAllInquiryRows_(_fdInPeriod_).forEach(function(row) {
      var conv = _fdConverted_(row.phone);
      if (!conv.any) return;
      var regDate = _fdRegDate_(row.phone);
      _fdPush_(row.channel, {
        name:             row.source === 'form' ? '확인불가(이름 미수집 폼)' : (row.name || '확인불가'),
        phone4:           _fdPhone4_(row.phone),
        type:             _fdTypeLabel_(row.phone, row.type),
        inquiryDate:      _miToISO_(row.ts) || '확인불가',
        regDate:          regDate || '확인불가',
        regDateConfirmed: !!regDate,
        matchBasis:       _fdBasisLabel_(conv)
      });
    });

    var fdResult = {
      ok: true,
      byChannel: fdByChannel,
      periodMode: fdPeriod,
      period: { from: fdFrom, to: fdTo },
      note: (fdPeriod ? '문의=선택기간(시각 기준)' : '문의·전환 전체 누적(기간무필터)') +
        ' · 전환판정=전화매칭(유효회원∪강습등록, 등록일 미사용) — funnel_conversion(비정밀) byChannel.converted와 동일기준·건수 정합 · ' +
        '연락처는 서버에서 뒷4자리만 반환 · regDate=확인불가는 원장에서 등록일 미확인(날조 아님) · 폼 경로 문의는 이름 미수집(원본 한계)',
      generatedAt: _now()
    };
    try { fdCache.put(fdCacheKey, JSON.stringify(fdResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(fdResult);
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
    var tcID = _readInquirySheetRows_();   // 테스트행 제외 단일헬퍼(배209 GM승인 2026-07-30)
    var tcChI = INQUIRY_HEADERS.indexOf('유입채널');
    var tcTpI = INQUIRY_HEADERS.indexOf('문의유형');
    var tcPhI = INQUIRY_HEADERS.indexOf('연락처');
    var tcDtI = INQUIRY_HEADERS.indexOf('시각');
    tcID.forEach(function(r) {
      _tcPush_(r[tcTpI], r[tcChI], r[tcPhI], _parseAnyDate_(r[tcDtI]));
    });
    _collectFormInquiries_().forEach(function(f) {
      _tcPush_(f.문의유형, f.유입채널, f.연락처, f.시각);
    });

    // periodMode: from/to 둘 다 있으면 '문의'는 기간뷰, '등록(전환)'은 누적(등록일 데이터 없음 → 기간 산출 불가).
    var tcPeriod = !!(tcFrom && tcTo);
    var tcF = tcPeriod ? new Date(tcFrom + 'T00:00:00+09:00').getTime() : 0;
    var tcT = tcPeriod ? new Date(tcTo + 'T23:59:59+09:00').getTime() : 0;
    function _tcInPeriod(row) {
      if (!tcPeriod) return true;
      var t = row.시각 ? _normTs_(row.시각).getTime() : NaN;  // 단일 정규화 SSOT(공백→T·KST)
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
        var d = _normTs_(ts);  // 단일 정규화 SSOT
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

    // ── inquiries 집계 — _collectFormInquiries_ 한 번만 호출 ──
    var formInquiries = _collectFormInquiries_(); // 【중복 제거】 단일 호출 후 재사용

    var inqTs    = [];
    var inqMonthRows = []; // {유입채널, 문의유형} — 이번달만 보관
    var inqSheetRows = []; // {시각(Date), 연락처, 유입채널, 문의유형} — conversion·custom용
    {
      var inqData2 = _readInquirySheetRows_();   // 테스트행 제외 단일헬퍼(배209 GM승인 2026-07-30)
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
          if (String(r[idxStatus] || '').trim() === MI_DUP_DELETED_STATUS) return;   // ★소프트 삭제(중복) 제외(2026-08-05 시토)
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
    // ★ 2026-07-06 시포 정직 재배선: 멤버십·강습을 별도 2퍼널로 분리(원본은 두 제품을 한 퍼널에 섞어 문의 8,677=멤버십749+강습8,448 착시).
    //   소스: 멤버십=문의접수(현재 0)+26년신규문의(gid1902010032) / 강습=성인(111889422)+유소년WSC(268994754).
    //   단계=칸 신호 파생(각 시트 헤더 키워드로 탐지, 실재 신호만 승격·비강등). 검증=임시배포 getLastRow/실집계(gviz는 강습 undercount·신뢰불가).
    var sfCache = CacheService.getScriptCache();
    var sfHit   = sfCache.get('sf_v3');
    if (sfHit && !_nc) return _json(JSON.parse(sfHit));

    // ① 회원부 전화번호 Set (funnel_conversion 방식 그대로)
    var sfMemberSet = {};
    var sfMemberSh  = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    var sfMemberLast = sfMemberSh.getLastRow();
    if (sfMemberLast >= 2) {
      var sfMH = sfMemberSh.getRange(1, 1, 1, sfMemberSh.getLastColumn()).getValues()[0];
      var sfPCol = sfMH.indexOf(MEMBER_PHONE_COL);
      if (sfPCol >= 0) {
        sfMemberSh.getRange(2, sfPCol + 1, sfMemberLast - 1, 1).getValues().forEach(function(r) {
          var n = normalizePhone_(r[0]); if (n) sfMemberSet[n] = true;
        });
      }
    }

    var sfMonthStart = new Date(Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM') + '-01T00:00:00+09:00');
    function _sfToDate_(ts) { if (ts instanceof Date) return ts; var s = String(ts || '').trim(); return s ? new Date(s.replace(' ', 'T') + '+09:00') : new Date(NaN); }
    function _mkB_() { return { 문의: 0, 응대: 0, 예약: 0, 방문: 0, 가입: 0, 이탈: 0 }; }
    function _sfAddB_(buckets, rank) {
      buckets.forEach(function(b) {
        if (rank === 0) { b.이탈++; b.문의++; }
        else { if (rank >= 1) b.문의++; if (rank >= 2) b.응대++; if (rank >= 3) b.예약++; if (rank >= 4) b.방문++; if (rank >= 5) b.가입++; }
      });
    }
    // 멤버십/강습 버킷(전체·이번달)
    var memT = _mkB_(), memM = _mkB_(), lesT = _mkB_(), lesM = _mkB_();

    // ★ 2026-07-28 시모(GM 지시) — [웹접수] 미러 제외를 '조건부'로 바꾼다.
    //   무엇이 잘못됐나: 아래 _sfProc_ 는 비고에 '[웹접수]' 가 있는 행을 무조건 건너뛰었다.
    //   그 제외의 전제는 "웹문의는 ①-a 문의접수 시트로 이미 1회 집계된다" 였는데,
    //   그 시트는 실제로 0행이다(바로 아래 ①-a 주석도 '현재 0행'이라고 적고 있다).
    //   결과: 홈페이지 자체 폼(2026-07-15 라이브)으로 들어온 문의가 ①-a 에서도 0,
    //   ①-b 에서도 제외 → 어디에서도 안 세어졌다. 2026-07 실측 멤버십 문의 52건 중
    //   이 화면엔 34건만 떴다(35% 누락). 자체 폼 비중이 커질수록 갭도 계속 벌어진다.
    //   고친 방식: '무조건 제외' 를 '진짜 중복일 때만 제외' 로 바꾼다.
    //   ①-a 에서 문의접수 시트의 연락처를 모아 두고, ①-b 의 [웹접수] 미러 행은
    //   그 연락처가 실제로 ①-a 에 있을 때만 건너뛴다.
    //   → 문의접수가 웹문의를 다시 받기 시작하면 그때부터 자동으로 중복이 막히고(회귀 0),
    //     지금처럼 안 받고 있으면 미러가 유일한 기록이므로 그대로 센다.
    //   ※ 2026-07-28 실측: 문의접수 시트는 전체 2행뿐이고 둘 다 유입경로 '전화' 다.
    //     즉 자체 폼(intake_submit)은 이 시트에 쓰지 않는다 — '이미 1회 집계된다' 는 전제가 사실이 아니었다.
    var _sfInqPhones = {};           // ①-a 문의접수 시트에 실재하는 연락처 집합
    function _sfIsDupWebMirror_(phone) { return !!(phone && _sfInqPhones[phone]); }

    // 시트 1개 처리 — headers·rows·칸키맵(keys)·대상버킷. 단계=상태칸+담당자/예약/방문 신호+회원매칭.
    function _sfProc_(headers, rows, keys, totB, monB) {
      var iStatus = _findCol_(headers, ['진행상태', '상태', '단계']);
      var iPhone  = _findCol_(headers, ['연락처', '휴대폰', '핸드폰', '전화']);
      var iDate   = _findCol_(headers, ['타임스탬프', '문의일', '시각', '일시', '접수일', '접수', '날짜']); if (iDate < 0) iDate = 0;
      var iMemo   = _findCol_(headers, ['비고', '메모']);
      var iOwner  = _findCol_(headers, keys.owner);
      var iBook   = _findCol_(headers, keys.book);
      var iVisit  = _findCol_(headers, keys.visit);
      rows.forEach(function(r) {
        if (!r[iDate] && (iPhone < 0 || !r[iPhone])) return;                                   // 빈 행 스킵
        var _ph0 = iPhone >= 0 ? normalizePhone_(r[iPhone]) : '';
        if (iMemo >= 0 && String(r[iMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0
            && _sfIsDupWebMirror_(_ph0)) return;                                               // [웹접수] 미러 — ①-a에 같은 연락처가 실재할 때만 제외(위 주석)
        var rank = _stageOf_(iStatus >= 0 ? r[iStatus] : '');
        if (iOwner >= 0 && String(r[iOwner] || '').trim()) rank = Math.max(rank, 2);           // 담당배정 → 응대
        if (iBook  >= 0 && String(r[iBook]  || '').trim()) rank = Math.max(rank, 3);           // 예약/투어 → 예약
        if (iVisit >= 0 && String(r[iVisit] || '').trim()) rank = Math.max(rank, 4);           // 방문/체험확정 → 방문
        var phone = iPhone >= 0 ? normalizePhone_(r[iPhone]) : '';
        if (phone && sfMemberSet[phone]) rank = Math.max(rank, 5);                             // 회원매칭 → 가입
        var d = _sfToDate_(_parseAnyDate_(r[iDate]));
        _sfAddB_((!isNaN(d.getTime()) && d >= sfMonthStart) ? [totB, monB] : [totB], rank);
      });
    }

    var MEM_KEYS = { owner: ['접수 담당자', '담당'], book: ['희망하는 날짜', '시설투어', '투어'], visit: ['확정시간', '체험1', '체험2'] };
    var LES_KEYS = { owner: ['관리담당', '접수 담당자', '진행 상황'], book: ['상담예약'], visit: ['방문상태'] };
    var LES_GIDS = { 111889422: 1, 268994754: 1 };

    // 멤버십 ①-a: INQUIRY_SHEET(문의접수) — 테스트행 제외 단일헬퍼(배209 GM승인 2026-07-30)
    try {
      var sfInqRows = _readInquirySheetRows_();
      if (sfInqRows.length >= 1) {
        var sfInqPhoneCol = INQUIRY_HEADERS.indexOf('연락처');
        if (sfInqPhoneCol >= 0) {
          sfInqRows.forEach(function(r) {                       // ★ ①-b의 [웹접수] 미러 중복 판정용 연락처 집합
            var n = normalizePhone_(r[sfInqPhoneCol]); if (n) _sfInqPhones[n] = true;
          });
        }
        _sfProc_(INQUIRY_HEADERS, sfInqRows, MEM_KEYS, memT, memM);
      }
    } catch (e) { /* 무중단 */ }

    // ①-b: FORM_SHEETS → gid로 멤버십/강습 분기
    FORM_SHEETS.forEach(function(cfg) {
      try {
        var sh = _sheetByGid_(cfg.ssId, cfg.gid); if (!sh) return;
        var last = sh.getLastRow(), lc = sh.getLastColumn(); if (last < 2 || lc < 1) return;
        var hd = sh.getRange(1, 1, 1, lc).getValues()[0];
        var rows = sh.getRange(2, 1, last - 1, lc).getValues();
        // ★소프트 삭제(중복) 제외 — 26년 신규문의(FORM_SHEETS[0])만 해당. _sfProc_ 내부 iStatus(진행상태/상태/단계)는
        //   이 시트 실헤더 '진행현황'을 못 찾아 여기서 따로 걸러야 한다(2026-08-05 시토, GM 지시).
        if (cfg === FORM_SHEETS[0]) {
          var _sfMiStI = _miColIdx_(hd, ['진행현황','진행상황','진행상태','상태']);
          if (_sfMiStI >= 0) rows = rows.filter(function(r){ return String(r[_sfMiStI] || '').trim() !== MI_DUP_DELETED_STATUS; });
        }
        if (LES_GIDS[cfg.gid]) _sfProc_(hd, rows, LES_KEYS, lesT, lesM);   // 강습 퍼널
        else                   _sfProc_(hd, rows, MEM_KEYS, memT, memM);   // 멤버십 퍼널(그 외 폼=소량·멤버십 편입)
      } catch (e) { /* 무중단 */ }
    });

    function _retain_(b) { function p(n, dd) { return dd ? Math.round(n / dd * 1000) / 10 : 0; } return { 응대: p(b.응대, b.문의), 예약: p(b.예약, b.응대), 방문: p(b.방문, b.예약), 가입: p(b.가입, b.방문) }; }
    var sfResult = {
      ok: true, generatedAt: _now(),
      membership: { total: memT, month: memM, retain: _retain_(memT) }, // ★ 멤버십 문의 퍼널
      lesson:     { total: lesT, month: lesM, retain: _retain_(lesT) }, // ★ 강습 문의 퍼널
      total: memT, month: memM, retain: _retain_(memT)                  // 하위호환(기본=멤버십)
    };
    try { sfCache.put('sf_v3', JSON.stringify(sfResult), 1800); } catch (e) { /* 무시 */ }
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
    var wtBuckets = [];  // [{start: Date, end: Date, weekStart: 'YYYY-MM-DD', inquiries: 0}]
    for (var wi = 7; wi >= 0; wi--) {
      var bucketStart = new Date(wtThisWeekStart.getTime() - wi * 7 * 86400000);
      var bucketEnd   = new Date(bucketStart.getTime()     + 7 * 86400000);
      var bucketStr   = Utilities.formatDate(bucketStart, 'Asia/Seoul', 'yyyy-MM-dd');
      wtBuckets.push({ start: bucketStart, end: bucketEnd, weekStart: bucketStr, inquiries: 0 });
    }

    // 타임스탬프(Date|string) → Date 변환 (period_breakdown 의 _toDate_ 와 동일 로직)
    function _wtToDate_(ts) {
      if (ts instanceof Date) return ts;
      var s = String(ts || '').trim();
      if (!s) return new Date(NaN);
      return new Date(s.replace(' ', 'T') + '+09:00');
    }

    // ── 문의 타임스탬프 집계 — 문의접수 시트 + 구글폼 합산 ──
    var wtInqData = _readInquirySheetRows_();   // 테스트행 제외 단일헬퍼(배209 GM승인 2026-07-30)
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
      return { weekStart: b.weekStart, inquiries: b.inquiries };
    });

    var wtResult = { ok: true, weeks: wtWeeks, generatedAt: _now() };
    try { wtCache.put('wt_v1', JSON.stringify(wtResult), 1800); } catch (e) { /* 캐시 저장 실패 무시 */ }
    return _json(wtResult);
  }

  // ─── 종목별 등록 집계 (대시보드 강습 펼침 — GM 2026-06-18) ───
  // 성인/유소년강습을 GM 지정 종목 단위로 펼쳐 '등록' 수만 반환. 문의는 종목 데이터 없음 → 프론트가 대분류로 표기.
  // 등록 = LESSON_TEAM_SHEETS 팀시트 상태열 SUC/등록 등(_isLessonReg_). 정본 = _collectLessonRegByName_.
  // 정직성: 외부 프로그램(루프메소드)=registered:null('외부관리·명단 미표시'), 0으로 채우지 않음. 시트 있고 등록 0=실측 0.
  if (action === 'lesson_breakdown') {
    var lbFrom = body.from || '';   // YYYY-MM-DD (기간별 문의 집계용)
    var lbTo   = body.to   || '';
    var lbCache = CacheService.getScriptCache();
    var lbKey = 'lb_v2_' + lbFrom + '_' + lbTo;   // 기간별 캐시키
    var lbHit = lbCache.get(lbKey);
    if (lbHit && !_nc) return _json(JSON.parse(lbHit));

    var byName    = _collectLessonRegByName_();              // 등록(누적): { 'P.T 성인': {registered|null,...}, ... }
    var byNameInq = _collectLessonInqByName_(lbFrom, lbTo);  // (others 표기용 · 팀시트 기준 — 신뢰 낮음)
    var inqBySport = _lessonInqBySportFromForms_(lbFrom, lbTo);  // [배179] 문의 정본 = 강습 응답 탭
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
      var ledgerRoster = null;  // 팀시트 없는 종목(발레·바레): 등록원장 기반. 지연 로드(있을 때만 1회).
      data[grp] = LESSON_DISPLAY[grp].map(function(item) {
        var reg = null, inq = null, src = null, sheetUrl = null;
        if (item.sheet) {
          usedSheets[item.sheet] = true;
          var rec  = byName[item.sheet];
          var recI = byNameInq[item.sheet];
          if (rec)  { reg = rec.registered; src = rec.statusHeader; }  // null이면 그대로(데이터 미연결)
          inq = _lessonInqLookup_(inqBySport[grp], item.명);   // [배179] 문의 = 응답 탭 기준
          sheetUrl = _lessonSheetUrl(item.sheet);
        } else if (item.ledger) {
          // 발레·바레(external 해제): 등록원장(강습 등록현황) SUC 카운트로 집계. roster 없으면 0(정직·날조 아님).
          if (ledgerRoster === null) ledgerRoster = _ledgerRosterByType_(grp);
          reg = (ledgerRoster[item.명] || []).length;
          inq = _lessonInqLookup_(inqBySport[grp], item.명);   // [배179] 문의 = 응답 탭 기준
          src = '등록원장(강습 등록현황)';
        }
        return { 명: item.명, registered: reg, inquiries: inq, sheet: item.sheet || null, sheetUrl: sheetUrl, statusSource: src, external: !!item.external, note: item.note || '' };
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
        if (!item.sheet && !item.ledger) unmatched.push({ 유형: grp, 명: item.명, external: !!item.external, reason: item.note || '등록·문의 데이터 출처 없음' });
      });
    });

    var lbResult = {
      ok: true,
      generatedAt: _now(),
      range: { from: lbFrom, to: lbTo },
      basis: '종목별 문의 = 강습 응답 탭(성인·유소년)을 종목 표준분류(_sportBuckets_)로 기간 집계 [2026-07-27 변경 — 종전 팀시트 타임스탬프 기준은 팀시트 응답칸 공백으로 수영 외 전 종목이 0 이었다] · 모자수영은 표준분류가 수영에 합쳐 분리 불가라 미측정 · 등록 = 팀시트 상태열 수강등록(SUC/등록) 누적 [주의: 팀시트 11곳은 등록 행에 성함·휴대폰이 비어 있어 실인원 확인 불가 — 배155/배173] · 팀시트 없는 종목(발레·바레·뮤지컬)=등록원장 SUC 카운트',
      data: data,
      others: others,
      unmatched: unmatched
    };
    try { lbCache.put(lbKey, JSON.stringify(lbResult), 1800); } catch (e) { /* 캐시 실패 무시 */ }
    return _json(lbResult);
  }

  // ─── [진단·읽기전용] 6팀시트 은퇴 안전게이트 — 재배선 전/후 IDENTICAL 대조 (배973 시포) ───
  //   OLD(6팀시트 기반) vs NEW(메인4시트 flat O컬럼 기반)를 동일 로직으로 산출해 나란히 반환.
  //   카운트만 반환(이름·전화 미노출). 시트 무변경(_lessonEnsureCols_ 미호출·순수 read).
  //   ★2026-07-15 실측 결론: OLD≠NEW(대량·양방향 불일치). 원인=팀시트 '진행 상황'(팀장 로컬 입력)과
  //     메인 O(페이지 입력)가 독립 유지되어 발산 — 메인 O는 등록상태 SSOT가 아직 아님.
  //     ∴ 6팀시트 은퇴/소비자 재배선은 이 액션이 OLD≡NEW 반환할 때까지 보류(억지 통과 금지).
  //     재검증: clasp push → clasp create-deployment → 새 /exec?action=lesson_rewire_audit 호출.
  if (action === 'lesson_rewire_audit') {
    var AUD_MAIN = [
      { gid: 111889422, type: '성인강습',   lang: 'KR' },
      { gid: 268994754, type: '유소년강습', lang: 'KR' },
      { gid: 311319200, type: '성인강습',   lang: 'EN' },
      { gid: 931249179, type: '유소년강습', lang: 'EN' }
    ];
    // 메인 flat 행 순수 리더(무변경) — 진행상황(O)·종목·경로·타임스탬프·성함/연락처 존재여부만.
    function _audReadMain_(gid) {
      var sh = _sheetByGid_(LESSON_SS_ID, gid);
      if (!sh) return null;
      var last = sh.getLastRow(), lastCol = sh.getLastColumn();
      if (last < 2 || lastCol < 1) return { sh: sh, hdr: [], rows: [], idx: {} };
      var data = sh.getRange(1, 1, last, lastCol).getValues();
      var hdr = data[0];
      var idx = {
        status: _findCol_(hdr, ['진행상태', '진행현황', '진행상황', '진행 상황', '상태']),
        sport:  _findCol_(hdr, ['성인 강습 종목', 'WSC 강습 종목', 'WSC 강습 종류', '강습 종목', '종목', '과목', 'Program of Interest']),
        chan:   _findCol_(hdr, ['문의 경로', '경로', '채널', '알게', 'How Did You Hear About Us?']),
        name:   _findCol_(hdr, ['성함', '이름', 'Full Name']),
        phone:  _findCol_(hdr, ['연락처', '전화', '휴대폰', 'Mobile Phone Number']),
        ts:     _findCol_(hdr, ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '날짜'])
      };
      var rows = [];
      for (var r = 1; r < data.length; r++) {
        var row = data[r];
        var hasName  = idx.name  >= 0 && row[idx.name];
        var hasPhone = idx.phone >= 0 && row[idx.phone];
        if (!hasName && !hasPhone) continue;  // 완전 빈 행 스킵(=_lessonReadRows_ 동일)
        rows.push({
          status: idx.status >= 0 ? String(row[idx.status] || '') : '',
          sport:  idx.sport  >= 0 ? String(row[idx.sport]  || '') : '',
          chan:   idx.chan   >= 0 ? String(row[idx.chan]   || '') : '',
          ts:     idx.ts     >= 0 ? row[idx.ts] : ''
        });
      }
      return { sh: sh, hdr: hdr.map(function(h){ return String(h||''); }), rows: rows, idx: idx };
    }
    // 메인 종목라벨 → 팀시트 '명' 버킷(유형별). 우선순위: 아쿠아·모자수영·체조 먼저(수영 오귀속 차단).
    function _audNameBucket_(type, sportRaw) {
      var s = String(sportRaw || '');
      if (/아쿠아/.test(s)) return type === '성인강습' ? '아쿠아로빅' : null;
      if (/모자|엄마|보호자\s*동반|자녀\s*동반/.test(s)) return type === '유소년강습' ? '모자수영' : null;
      if (/체조|트램폴린/.test(s)) return type === '유소년강습' ? '유소년체조' : null;
      var suffix = type === '성인강습' ? ' 성인' : ' 유소년';
      if (/수영/.test(s))            return '수영' + suffix;
      if (/필라테스|필라/.test(s))    return '필라테스' + suffix;
      if (/P\.?T|피티|퍼스널/i.test(s)) return 'P.T' + suffix;
      if (/스쿼시/.test(s))          return '스쿼시' + suffix;
      if (/골프/.test(s))            return '골프' + suffix;
      // 발레·바레 분리(시토·GM 2026-07-15): 과거 합쳐진 옵션은 legacy 합산, 신규 단독은 각각. 표준=순수 '발레'/'바레'.
      if (/웰니스\s*프로그램|바레\s*[,·]\s*발레|발레\s*[,·]\s*바레/.test(s)) return '루프메소드(발레·바레)';  // legacy(팀시트 없음)
      if (/발레/.test(s))            return '발레';
      if (/바레/.test(s))            return '바레';
      return null;  // 미매칭(뮤지컬·기타 등) → OLD 팀시트에 대응 명 없음
    }
    var KST = 'Asia/Seoul';
    var nowD = new Date();
    var todayStr = Utilities.formatDate(nowD, KST, 'yyyy-MM-dd');
    var dayStart   = new Date(todayStr + 'T00:00:00+09:00');
    var weekStart  = new Date(new Date(nowD.getTime() - 6 * 86400000).toISOString().slice(0,10) + 'T00:00:00+09:00');
    var monthStart = new Date(Utilities.formatDate(nowD, KST, 'yyyy-MM') + '-01T00:00:00+09:00');
    var yearStart  = new Date(Utilities.formatDate(nowD, KST, 'yyyy') + '-01-01T00:00:00+09:00');
    function _audDate_(v) { var d = _parseAnyDate_(v); if (d instanceof Date) return d; var s = String(d||'').trim(); return s ? new Date(s.replace(' ','T') + '+09:00') : new Date(NaN); }

    // ── NEW: 메인4시트 flat 집계 ──
    var NEW_regByType = {}, NEW_regByName = {}, NEW_inqByName = {}, NEW_kpi = {}, NEW_alertCand = {};
    var mainDump = [];
    AUD_MAIN.forEach(function(cfg) {
      var m = _audReadMain_(cfg.gid);
      var tp = cfg.type;
      if (!NEW_regByType[tp]) NEW_regByType[tp] = { registered: 0, channels: {} };
      if (!NEW_kpi[tp]) NEW_kpi[tp] = { day:0, week:0, month:0, year:0 };
      if (!NEW_alertCand[tp]) NEW_alertCand[tp] = { SUC: 0, CONTACT: 0 };
      var dumpRec = { gid: cfg.gid, type: tp, lang: cfg.lang, sheetFound: !!(m && m.sh), rows: m ? m.rows.length : 0,
                      statusCol: m ? (m.idx.status >= 0 ? m.hdr[m.idx.status] : '(미발견)') : '(시트없음)',
                      sportCol:  m ? (m.idx.sport  >= 0 ? m.hdr[m.idx.sport]  : '(미발견)') : '(시트없음)',
                      sports: {}, regTotal: 0 };
      if (!m) { mainDump.push(dumpRec); return; }
      m.rows.forEach(function(row) {
        var isReg = _isLessonReg_(row.status);
        var lab = row.sport || '(빈종목)';
        if (!dumpRec.sports[lab]) dumpRec.sports[lab] = { total: 0, reg: 0 };
        dumpRec.sports[lab].total++; if (isReg) dumpRec.sports[lab].reg++;
        // regByType(type-level) + channels
        if (isReg) {
          NEW_regByType[tp].registered++; dumpRec.regTotal++;
          var ch = _canonicalChannel_(row.chan);
          if (!NEW_regByType[tp].channels[ch]) NEW_regByType[tp].channels[ch] = { registered: 0 };
          NEW_regByType[tp].channels[ch].registered++;
        }
        // per-명 등록/문의
        var nm = _audNameBucket_(tp, row.sport);
        if (nm) {
          if (!NEW_regByName[nm]) NEW_regByName[nm] = { registered: 0 };
          if (!NEW_inqByName[nm]) NEW_inqByName[nm] = { inquiries: 0 };
          NEW_inqByName[nm].inquiries++;              // OLD _collectLessonInqByName_ = 전체 행(상태무관)
          if (isReg) NEW_regByName[nm].registered++;
        }
        // KPI 기간별(SUC by timestamp)
        if (isReg) {
          var d = _audDate_(row.ts);
          if (!isNaN(d.getTime())) {
            if (d >= dayStart)   NEW_kpi[tp].day++;
            if (d >= weekStart)  NEW_kpi[tp].week++;
            if (d >= monthStart) NEW_kpi[tp].month++;
            if (d >= yearStart)  NEW_kpi[tp].year++;
          }
        }
        // 상태알림 후보(SUC/CONTACT)
        if (isReg) NEW_alertCand[tp].SUC++;
        else if (/컨택|응대|연락|통화|문자|회신/.test(row.status)) NEW_alertCand[tp].CONTACT++;
      });
      mainDump.push(dumpRec);
    });

    // ── OLD: 6팀시트 집계(기존 정본 함수 재사용) ──
    var OLD_regByType = _collectLessonRegistrations_();   // {type:{registered, channels}}
    var OLD_debug = _LESSON_DEBUG.slice();                 // 팀시트별 statusHeader·registered·rows·표본
    var OLD_regByName = _collectLessonRegByName_();        // {명:{registered, statusHeader, rows, sheetFound}}
    var OLD_inqByName = _collectLessonInqByName_('', '');  // {명:{inquiries, sheetFound}}
    // OLD KPI 기간별 + 상태알림 후보(팀시트 상태열 재탐지)
    var OLD_kpi = { '성인강습': { day:0,week:0,month:0,year:0 }, '유소년강습': { day:0,week:0,month:0,year:0 } };
    var OLD_alertCand = { '성인강습': { SUC:0, CONTACT:0 }, '유소년강습': { SUC:0, CONTACT:0 } };
    LESSON_TEAM_SHEETS.forEach(function(tcfg) {
      try {
        var sh = _sheetByGid_(tcfg.ssId, tcfg.gid); if (!sh) return;
        var last = sh.getLastRow(), lastCol = sh.getLastColumn(); if (last < 2 || lastCol < 1) return;
        var data = sh.getRange(1, 1, last, lastCol).getValues();
        var best = -1, bestCnt = 0;
        for (var c = 0; c < lastCol; c++) {
          var cnt = 0, dn = 0, distinct = {};
          for (var r = 1; r < data.length; r++) {
            var cv = String(data[r][c] || '').trim(); if (!cv) continue;
            if (!distinct[cv]) { distinct[cv] = 1; dn++; }
            if (_isLessonStatusVal_(cv)) cnt++;
          }
          if (dn >= 2 && dn <= 30 && cnt > bestCnt) { bestCnt = cnt; best = c; }
        }
        if (best < 0) return;
        var idxDate = _findCol_(data[0], ['타임스탬프', 'timestamp', '시각', '일시', '접수일', '접수', '날짜']);
        if (idxDate < 0) idxDate = 0;
        for (var r2 = 1; r2 < data.length; r2++) {
          var sv = data[r2][best];
          if (_isLessonReg_(sv)) {
            OLD_alertCand[tcfg.유형].SUC++;
            var d = _audDate_(data[r2][idxDate]);
            if (!isNaN(d.getTime())) {
              if (d >= dayStart)   OLD_kpi[tcfg.유형].day++;
              if (d >= weekStart)  OLD_kpi[tcfg.유형].week++;
              if (d >= monthStart) OLD_kpi[tcfg.유형].month++;
              if (d >= yearStart)  OLD_kpi[tcfg.유형].year++;
            }
          } else if (/컨택|응대|연락|통화|문자|회신/.test(String(sv || ''))) {
            OLD_alertCand[tcfg.유형].CONTACT++;
          }
        }
      } catch (e) {}
    });

    return _json({
      ok: true, generatedAt: _now(), note: '카운트만·PII 미노출. OLD=6팀시트 / NEW=메인4시트 flat.',
      OLD: { regByType: OLD_regByType, regByName: OLD_regByName, inqByName: OLD_inqByName, kpiPeriod: OLD_kpi, alertCand: OLD_alertCand, teamDebug: OLD_debug },
      NEW: { regByType: NEW_regByType, regByName: NEW_regByName, inqByName: NEW_inqByName, kpiPeriod: NEW_kpi, alertCand: NEW_alertCand, mainDump: mainDump }
    });
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

// ═══ 대기→멤버십 자동전환 (2026-08-04 GM 지시) ═══
//   회원구분('멤버십'등)을 '대기'·'LOSS'로 바꾸는 건 사람 전담(자동화 금지) — 반대로
//   '분류'가 든 칸(등록분류/재등록분류)에 실무진이 적어둔 '대기'는, 시작일자가 도래하면
//   더는 대기가 아니므로 그 칸만 비운다. 회원구분 칸·LOSS 값은 절대 건드리지 않는다.
//   화면 판정 = _isFutureStart(membership.html:6802) — '분류' 든 칸 중 하나라도 정확히 '대기'면 대기자.
//   이 함수가 그 칸을 지우면 화면에서도 자동으로 대기자 명단을 빠진다(별도 화면 수정 불필요).

// 순수판정(시트 I/O 없음) — 본체·자체점검이 공유. headers=트림된 헤더 배열, rowValues=해당 행 값 배열,
// todayIso='YYYY-MM-DD'. 반환: null=대상 아님(시작일자 칸 없음/빈값/파싱불가/미도래 — 절대 건드리지 않음),
// 배열(빈 배열 포함)=시작일자 도래 — 배열 원소는 지워야 할 '분류' 칸의 0-based 인덱스.
function _memberWaitReleaseCols_(headers, rowValues, todayIso) {
  var startIdx = -1;
  for (var si = 0; si < headers.length; si++) {
    if (String(headers[si]).replace(/\s/g, '').indexOf('시작일자') >= 0) { startIdx = si; break; }
  }
  if (startIdx < 0) return null;
  var startIso = _miToISO_(rowValues[startIdx]);           // 기존 관례 재사용(느슨 파싱, 실패 시 '')
  if (!startIso || startIso > todayIso) return null;       // 미도래·미기재·파싱불가 — 건드리지 않음(<=today만 대상)
  var cols = [];
  for (var hi = 0; hi < headers.length; hi++) {
    if (String(headers[hi]).replace(/\s/g, '').indexOf('분류') >= 0     // _memClassKeys(membership.html:6776)와 동일 판정
        && String(rowValues[hi] || '').trim() === '대기') cols.push(hi);
  }
  return cols;
}

/**
 * member_wait_auto_release_(opts)
 * 유효회원 시트를 순회해 시작일자가 도래(<=오늘)했는데 '분류' 칸에 아직 '대기'가 남은 행의
 * 그 칸(들)만 비운다. dry:true면 쓰기 없이 대상만 반환(검증용). 멱등 — 지울 게 없으면 쓰기 0회.
 * 회원구분 칸은 절대 읽고 쓰지 않는다(GM 지시: 회원구분↔대기/LOSS 전환은 사람 전담).
 */
function member_wait_auto_release_(opts) {
  var dry = !!(opts && opts.dry);
  var tz = 'Asia/Seoul';
  var today = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  var out = { checked: 0, released: 0, targets: [], dry: dry };
  var sh;
  try {
    sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  } catch (e) {
    out.error = e.message;
    return out;
  }
  if (!sh || sh.getLastRow() < 2) return out;

  var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  var data = sh.getRange(2, 1, lastRow - 1, lastCol).getValues();

  var writes = [];  // { row(1-based), col(1-based), before }
  for (var r = 0; r < data.length; r++) {
    var cols = _memberWaitReleaseCols_(headers, data[r], today);
    if (cols === null) continue;
    out.checked++;   // 시작일자 도래한 행(대기 유무 무관 — 실측 정답=0)
    cols.forEach(function(ci) {
      writes.push({ row: r + 2, col: ci + 1, before: String(data[r][ci] || '').trim() });
    });
  }
  out.released = writes.length;
  out.targets = writes.map(function(w) { return { row: w.row, col: w.col, before: w.before }; });
  if (!dry) writes.forEach(function(w) { sh.getRange(w.row, w.col).setValue(''); });
  return out;
}

/** 자체점검(프레임워크 없음) — _memberWaitReleaseCols_ 판정 6분기 단독 확인(시트 I/O 없음).
 *  Apps Script 편집기에서 수동 실행. 실패 시 throw, 통과 시 Logger.log('[OK] ...'). */
function member_wait_auto_release_selfcheck_() {
  var H = ['회원명', '등록분류', '재등록분류', '회원구분', '시작\n일자'];
  var TODAY = '2026-08-04';
  function eq(label, actual, expected) {
    var a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) throw new Error('[FAIL] ' + label + ' — got ' + a + ' want ' + e);
  }
  eq('미도래-건드리지않음',
     _memberWaitReleaseCols_(H, ['홍길동', '신규', '대기', '멤버십', '2026-08-10'], TODAY), null);
  eq('도래+재등록분류대기-해당칸만',
     _memberWaitReleaseCols_(H, ['김철수', '신규', '대기', '멤버십', '2026-08-01'], TODAY), [2]);
  eq('오늘정확히도래(<=포함)',
     _memberWaitReleaseCols_(H, ['이영희', '신규', '대기', '멤버십', TODAY], TODAY), [2]);
  eq('도래+정상값-빈배열(건드릴칸없음)',
     _memberWaitReleaseCols_(H, ['박민수', '신규', '재등록', '멤버십', '2026-08-01'], TODAY), []);
  eq('시작일자빈칸-건드리지않음',
     _memberWaitReleaseCols_(H, ['최영', '신규', '대기', '멤버십', ''], TODAY), null);
  eq('등록재등록둘다대기-두칸모두',
     _memberWaitReleaseCols_(H, ['정하나', '대기', '대기', '멤버십', '2026-08-01'], TODAY), [1, 2]);
  Logger.log('[OK] member_wait_auto_release_selfcheck_ 6건 통과');
  return true;
}

// ═══ LOSS일자 자동 기록 (2026-08-05 시토 · 배302, GM 지시 2026-08-03) ═══
//   GM 원문: '잔여일이 -1이 되면 자동으로 LOSS일자가 찍히게'.
//   실측(2026-08-04 웰리): LOSS 회원(scope=ended) 689명은 LOSS일자가 이미 100% 채워져 있다(공백 0) —
//   지금까지는 사람이 채워왔다는 뜻. 소급 대상 자체가 없으므로 과거분 백필은 하지 않는다(GM 확인 불요).
//   판정은 _memberIsValid_(약속 L01 SSOT, member_active_summary 등 4곳과 동일 함수) 를 재사용하되
//   재등록분류 자리에 빈 문자열을 고정으로 넘겨 '잔여일<0' 단독 조건으로 좁힌다 — 재등록분류 기반
//   LOSS/환불/양도LOSS 전환은 스코프 밖(실무진이 이미 그 경로는 수동으로 100% 채우는 중).
//   멱등: LOSS일자 칸이 이미 채워진 행은 절대 덮어쓰지 않는다.

/** 순수판정(시트 I/O 없음) — 본체·자체점검이 공유. remCell=잔여일 원본 셀 값, lossCell=LOSS일자 원본 셀 값.
 *  true=오늘 날짜로 찍어야 함(잔여일이 진짜 음수 & LOSS일자 아직 빈칸). */
function _memberLossDateShouldStamp_(remCell, lossCell) {
  return !_memberIsValid_(remCell, '') && !String(lossCell == null ? '' : lossCell).trim();
}

/**
 * member_loss_date_auto_stamp_(opts)
 * 유효회원 시트를 순회해 잔여일이 음수인데 LOSS일자가 빈칸인 행에 오늘 날짜(KST)를 1회 찍는다.
 * dry:true면 쓰기 없이 대상만 반환(검증용). 멱등 — 찍을 게 없으면 쓰기 0회.
 * 회원명 없는 행(시트 하단 집계 블록 등, 배964 교훈)은 건드리지 않는다.
 */
function member_loss_date_auto_stamp_(opts) {
  var dry = !!(opts && opts.dry);
  var tz = 'Asia/Seoul';
  var today = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  var out = { checked: 0, stamped: 0, targets: [], dry: dry };
  var sh;
  try {
    sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  } catch (e) {
    out.error = e.message;
    return out;
  }
  if (!sh || sh.getLastRow() < 2) return out;

  var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  function _idx(want) {
    var w = String(want).replace(/\s/g, '');
    for (var i = 0; i < headers.length; i++) { if (headers[i].replace(/\s/g, '').indexOf(w) >= 0) return i; }
    return -1;
  }
  var nmI   = _idx('회원명');
  var remI  = _idx('잔여일');
  var lossI = _idx('LOSS일자');   // ssot/sheet_columns.json member_active 계약에 실헤더 'LOSS\n일자'로 확인됨(2026-08-05)
  if (remI < 0 || lossI < 0) { out.error = '칸 없음(잔여일=' + remI + ' LOSS일자=' + lossI + ')'; return out; }

  var data = sh.getRange(2, 1, lastRow - 1, lastCol).getValues();
  var writes = [];
  for (var r = 0; r < data.length; r++) {
    if (nmI >= 0 && !String(data[r][nmI] || '').trim()) continue;   // 회원명 없는 행(집계 블록 등) 제외
    if (!_memberLossDateShouldStamp_(data[r][remI], data[r][lossI])) continue;
    out.checked++;
    writes.push({ row: r + 2, col: lossI + 1, name: String(data[r][nmI] || ''), rem: String(data[r][remI] || ''), lossBefore: String(data[r][lossI] || '') });
  }
  out.stamped = writes.length;
  out.targets = writes.map(function(w) { return { row: w.row, col: w.col, name: w.name, rem: w.rem, lossBefore: w.lossBefore }; });
  if (!dry) {
    writes.forEach(function(w) { sh.getRange(w.row, w.col).setValue(today); });
    // 이 자동 도장은 시트에 직접 써 왔는데 쓰기 관문을 안 거쳐, 찍은 뒤에도 회원 목록 캐시가 옛 값을
    // 그대로 내주고 잔여일 정렬 표시도 안 켜졌다(2026-08-12 시포). 쓴 게 있을 때만 관문을 부른다.
    if (writes.length) _memberCacheBump_();
  }
  return out;
}

/** 자체점검(프레임워크 없음) — _memberLossDateShouldStamp_ 판정 6분기 단독 확인(시트 I/O 없음).
 *  Apps Script 편집기에서 수동 실행. 실패 시 throw, 통과 시 Logger.log('[OK] ...'). */
function member_loss_date_auto_stamp_selfcheck_() {
  function eq(label, actual, expected) {
    if (actual !== expected) throw new Error('[FAIL] ' + label + ' — got ' + actual + ' want ' + expected);
  }
  eq('잔여일 -1, LOSS일자 빈칸 — 대상',              _memberLossDateShouldStamp_('-1', ''), true);
  eq('잔여일 -5, LOSS일자 빈칸 — 대상',              _memberLossDateShouldStamp_('-5', ''), true);
  eq('잔여일 -1, LOSS일자 이미 있음 — 제외(멱등)',    _memberLossDateShouldStamp_('-1', '2026-08-01'), false);
  eq('잔여일 0(만료 당일까지 유효) — 제외',           _memberLossDateShouldStamp_('0', ''), false);
  eq('잔여일 5(유효) — 제외',                        _memberLossDateShouldStamp_('5', ''), false);
  eq('잔여일 미기재(빈칸, 유효 취급) — 제외',          _memberLossDateShouldStamp_('', ''), false);
  Logger.log('[OK] member_loss_date_auto_stamp_selfcheck_ 6건 통과');
  return true;
}

// ═══ 유효회원 시트 잔여일순 정렬 (2026-08-08 시포, GM 지시 "잔여일 기준 정렬 하루 한 번") ═══
//   매일 자정 직후(실무진 근무 전) 1회, 이미 실측 확인된 유일한 CLOCK 트리거(warmLessonRosterCache,
//   5분 주기)의 날짜 도장 가드에 얹는다 — 새 트리거·새 액션 신설 없음(약속 L21).
//   ★쓰기 안전: member_active_update 는 행번호가 아니라 (등록일자+전화) 지문으로 행을 다시 찾으므로
//   정렬로 행 순서가 바뀌어도 다른 회원 줄을 덮어쓰지 않는다. 유일한 예외는 같은 전화+같은 등록일 쌍
//   1건(2025-01-03, 지문 동일) — 지문 재료 보강(시토 배491)으로 근본수리 예정, 그 전까지는 그 두 행
//   사이에서만 이론상 혼동 가능.
//   ★집계 블록 보호 — 유효회원 시트 맨 아래에는 연령대·회차·지역 집계 블록이 붙어 있다(member_active_list
//   8910행과 동일 이름패턴 판정: 숫자만/연령대 라벨/'합계'). 정렬 범위에 포함되면 회원 행 사이로 흩어질
//   위험이 있어(2026-07-28 GM 지적 사고와 동일 유형) 정렬 범위에서 완전히 제외한다. 경계는 매번 이름
//   패턴으로 재탐색 — 경계 아래 나머지가 전부 패턴에 안 맞으면(가정 붕괴) 정렬하지 않고 abort+경보.
function _memberSortFooterName_(nm) {
  return /^[0-9.]+$/.test(nm) || /^\d{1,3}대$/.test(nm) || /^\d{1,3}\s*[-~]\s*\d{1,3}세$/.test(nm) || nm === '합계';
}

/**
 * member_active_sort_by_remaining_(opts)
 * 유효회원 시트를 잔여일 오름차순(임박순 — czRenew 갱신임박 목록과 동일 방향)으로 정렬한다.
 * - 대상: 머리글 아래 '진짜 회원 행'만(맨 위부터 첫 집계블록 이름 패턴 행 전까지).
 * - 정렬 전 그 경계 아래 나머지 행이 전부 집계블록 패턴인지 재확인 — 아니면 정렬하지 않고 abort.
 * - 정렬 전/후 총 행수(getLastRow())가 같은지 확인 — 다르면 abort+텔레그램 경보(데이터 유실 방어).
 * dry:true면 쓰기 없이 대상 범위·행수만 반환(검증용).
 */
function member_active_sort_by_remaining_(opts) {
  var dry = !!(opts && opts.dry);
  var out = { dry: dry, sorted: false };
  var sh;
  try {
    sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  } catch (e) {
    out.error = e.message;
    return out;
  }
  if (!sh || sh.getLastRow() < 3) return out;  // 데이터 2행 미만이면 정렬 무의미

  var lastRowBefore = sh.getLastRow(), lastCol = sh.getLastColumn();
  var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function(v){ return String(v).trim(); });
  function _idx(want) {
    var w = String(want).replace(/\s/g, '');
    for (var i = 0; i < headers.length; i++) { if (headers[i].replace(/\s/g, '').indexOf(w) >= 0) return i; }
    return -1;
  }
  var nmI = _idx('회원명'), remI = _idx('잔여일');
  if (nmI < 0 || remI < 0) { out.error = '칸 없음(회원명=' + nmI + ' 잔여일=' + remI + ')'; return out; }

  var names = sh.getRange(2, nmI + 1, lastRowBefore - 1, 1).getValues().map(function(r){ return String(r[0] || '').trim(); });

  // 경계 찾기 — 맨 위부터 첫 집계블록 패턴 이름이 나오는 행(names 배열 0-based 인덱스)
  var footerStart = -1;
  for (var i = 0; i < names.length; i++) {
    if (names[i] && _memberSortFooterName_(names[i])) { footerStart = i; break; }
  }
  var memberRowCount = footerStart < 0 ? names.length : footerStart;

  // 안전확인 — 경계 아래 나머지가 전부 집계블록 패턴(또는 빈칸)인지. 하나라도 정상 이름이면 가정 붕괴 → abort.
  for (var j = memberRowCount; j < names.length; j++) {
    if (names[j] && !_memberSortFooterName_(names[j])) {
      out.error = '집계블록 경계 판정 실패(행 ' + (j + 2) + ' "' + names[j] + '") — 정렬 중단';
      try { _notifyTelegram('⚠️ 유효회원 잔여일 정렬 중단 — ' + out.error); } catch (eN) {}
      return out;
    }
  }

  out.memberRowCount = memberRowCount;
  out.footerRowCount = names.length - memberRowCount;
  if (memberRowCount < 2) return out;  // 정렬할 회원 행이 1행 이하면 무의미

  if (!dry) {
    sh.getRange(2, 1, memberRowCount, lastCol).sort({ column: remI + 1, ascending: true });
    var lastRowAfter = sh.getLastRow();
    if (lastRowAfter !== lastRowBefore) {
      out.error = '정렬 후 행수 불일치(전 ' + lastRowBefore + ' → 후 ' + lastRowAfter + ')';
      try { _notifyTelegram('⚠️ 유효회원 잔여일 정렬 — ' + out.error + ' (데이터 확인 요망)'); } catch (eN2) {}
      return out;
    }
    out.sorted = true;
  }
  return out;
}

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
  // ★ 은퇴(2026-07-22 GM 확정): '등록매칭(자동)'·'등록일(자동)' 칸 폐지. 이 함수가 그 두 칸의 유일한
  //   라이터였고, 칸을 삭제해도 다음 02:00에 재생성하던 물리 원인(9234·9246 자동생성)이다. no-op로 중립화 —
  //   실제 트리거 제거는 member_col_cleanup_20260722 액션이 수행. 등록일 정본=유효회원 시트 등록일자,
  //   등록매칭=진행현황 SUC에서 파생. 되살리려면 이 return 한 줄만 제거하면 원복된다.
  return { matched: 0, total: 0, retired: true };
  // ── 이하 원복용 보존(도달하지 않음) ──
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

/** 공개 트리거용 래퍼 (Apps Script 트리거는 인자 없는 최상위 함수여야 함)
 *  ★정정(2026-08-05 시토) — 이전 주석의 "이미 설치된 매일 02:00(KST) 트리거"는 실측 없이 적힌 문장이었다.
 *  action=list_inquiry_triggers(읽기전용 진단)로 라이브 트리거를 직접 조회하니 memberMatchAutostamp 에는
 *  CLOCK 트리거가 걸려 있지 않다(설치하려면 아래 installMemberMatchTrigger()를 GAS 에디터에서 1회 수동 실행
 *  해야 하는데, 그 실행이 실제로 있었던 적이 없다). 즉 이 함수는 지금 자동으로 돌지 않는다.
 *  member_wait_auto_release_·member_loss_date_auto_stamp_ 는 실측 확인된 5분 CLOCK 트리거
 *  (warmLessonRosterCache)로 이관해 그쪽에서 하루 1회 돈다 — 이 02:00 경로는 지금 불필요(중복 대비만).
 *  member_match_autostamp_ 자체는 2026-07-22 은퇴(no-op). */
function memberMatchAutostamp() {
  try {
    var wr = member_wait_auto_release_();
    Logger.log('member_wait_auto_release_: checked=' + wr.checked + ' released=' + wr.released + (wr.error ? ' error=' + wr.error : ''));
  } catch (e) {
    Logger.log('member_wait_auto_release_ 실패: ' + e.message);
  }
  // ★LOSS일자 자동기록(2026-08-05 시토·배302) — 대기→멤버십 자동전환과 같은 자리에 얹는다(약속 L21, 새 트리거 금지).
  try {
    var ld = member_loss_date_auto_stamp_();
    Logger.log('member_loss_date_auto_stamp_: checked=' + ld.checked + ' stamped=' + ld.stamped + (ld.error ? ' error=' + ld.error : ''));
  } catch (e) {
    Logger.log('member_loss_date_auto_stamp_ 실패: ' + e.message);
  }
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
/* ═══ 강습 회원 명단 캐시 워머 (2026-07-23 시포·GM) ═══════════════════════════
 *  왜: lesson_registered_roster 는 팀시트 13개 + 문의 시트 병합·조인이라 20초쯤 걸린다.
 *      10분 캐시를 걸어 두 번째부터는 2~3초로 줄었지만, 캐시가 비는 순간 처음 여는 사람이
 *      그 20초를 그대로 뒤집어쓴다. 미리 데워 두면 그 사람도 안 겪는다.
 *  방법: 자기 자신에게 HTTP 를 쏘지 않는다(인증·URL 의존·중복 과금 없음).
 *      _processAction 을 그대로 호출해 fresh=1 로 다시 만들면 캐시가 갱신된다.
 *  안전: 읽기 전용 액션만 부른다(시트 쓰기 0). 실패해도 조용히 넘어간다 — 워머가 죽어도
 *      화면은 느려질 뿐 고장 나지 않는다.
 */
var _WARM_EVERY_MIN = 5;   // GAS everyMinutes 허용값 = 1·5·10·15·30. 캐시 TTL(600초)보다 짧게.
function warmLessonRosterCache() {
  // ★강습 등록원장 동기화(2026-08-05 시토 · lesson_registry_list 23초 수리) — 원래 read 경로(호출마다)에서
  //   실행되던 _syncLessonRegistry_()를 여기로 이관. ★대상 재선정: 처음엔 warmDashboardCache(다른 함수)에
  //   얹었으나, action=list_inquiry_triggers(읽기전용 진단)로 라이브 트리거 목록을 직접 조회해 보니
  //   warmDashboardCache는 CLOCK 트리거가 설치돼 있지 않았다(코드 주석의 "실측 확인" 주장은 실제로 틀렸다 —
  //   확인 없이 만든 문장을 그대로 믿을 뻔했다). 이 warmLessonRosterCache 만이 list_inquiry_triggers로
  //   실측 확인된 진짜 CLOCK 트리거(5분 주기)이고, 도메인도 강습 원장이라 자연스러운 자리다. 새 트리거는
  //   만들지 않는다(약속 L21). _syncLessonRegistry_ 자체에 5분(300초) 캐시가드가 있어 이 5분 워머와 주기가
  //   맞물린다 — 중복 호출은 가드가 즉시 반환해 무해. 실패해도 다음 워머 주기(5분 뒤)에 재시도되므로 삼킨다.
  try { _syncLessonRegistry_(); } catch (eSyncReg) {}
  var types = ['성인강습', '유소년강습'], done = [];
  for (var i = 0; i < types.length; i++) {
    try {
      _processAction({ action: 'lesson_registered_roster', type: types[i], fresh: '1' });
      done.push(types[i]);
    } catch (e) { /* 한쪽 실패가 다른 쪽을 막지 않게 */ }
  }

  // ★대기→멤버십 자동해제 + LOSS일자 자동기록(2026-08-05 시토·배302) — warmDashboardCache에서 이관.
  //   두 기능 모두 원래 memberMatchAutostamp(02:00 일일) 또는 warmDashboardCache(5분) 에 얹혀 있었는데,
  //   action=list_inquiry_triggers(읽기전용 진단)로 라이브 트리거를 직접 조회하니 **둘 다 CLOCK 트리거가
  //   설치돼 있지 않았다**(라이브 확인 4건: _notifyNewInquiries_·warmLessonRosterCache·onInquiryFormSubmit×2뿐).
  //   즉 배포 이후(오늘) 자동으로 한 번도 실행된 적이 없다. 이 함수(warmLessonRosterCache)만이 실측 확인된
  //   CLOCK 트리거라 여기로 옮긴다. 새 트리거는 만들지 않는다(약속 L21). 하루 1회만 돌게 날짜 도장으로 막는다
  //   — 5분마다 회원 시트를 통째로 훑으면 낭비.
  try {
    var _wrTz = 'Asia/Seoul';
    var _wrToday = Utilities.formatDate(new Date(), _wrTz, 'yyyy-MM-dd');
    var _wrProps = PropertiesService.getScriptProperties();
    if (_wrProps.getProperty('WAIT_RELEASE_LAST') !== _wrToday) {
      var _wr = member_wait_auto_release_();
      _wrProps.setProperty('WAIT_RELEASE_LAST', _wrToday);
      Logger.log('member_wait_auto_release_(warm): checked=' + _wr.checked + ' released=' + _wr.released);
    }
    if (_wrProps.getProperty('LOSS_DATE_STAMP_LAST') !== _wrToday) {
      var _ld = member_loss_date_auto_stamp_();
      _wrProps.setProperty('LOSS_DATE_STAMP_LAST', _wrToday);
      Logger.log('member_loss_date_auto_stamp_(warm): checked=' + _ld.checked + ' stamped=' + _ld.stamped + (_ld.error ? ' error=' + _ld.error : ''));
    }
    // ★유효회원 잔여일순 정렬(2026-08-08 시포, GM 지시) — 같은 날짜 도장 가드로 하루 1회, 자정 직후
    //   (실무진 근무 전) 첫 5분 틱에서만 실행. 위 두 함수와 같은 자리(약속 L21, 새 트리거 없음).
    // ★쓰기가 있었을 때만 정렬(2026-08-12 GM "액션이 일어날 때만 움직여도 될 것 같은데").
    //   구: 날짜 도장으로 하루 1회 — 낮에 값이 바뀐 날은 다음 날까지 옛 순서로 남았다(오늘 종료일자
    //   521건 정정이 그 경우). 신: 회원 시트 쓰기 관문(_memberCacheBump_)이 표시를 켜고, 여기서 그
    //   표시가 켜져 있을 때만 정렬한 뒤 끈다. 아무도 안 고친 틱은 속성 하나 읽고 끝난다(시트 접근 0).
    //   ▸표시를 먼저 끄지 않고 정렬 성공 뒤에 끈다 — 정렬이 실패하면 다음 틱이 다시 시도한다.
    if (_wrProps.getProperty('MEMBER_SORT_DIRTY') === '1') {
      var _ms = member_active_sort_by_remaining_();
      if (_ms.sorted) _wrProps.deleteProperty('MEMBER_SORT_DIRTY');
      Logger.log('member_active_sort_by_remaining_(warm): sorted=' + _ms.sorted + ' memberRowCount=' + _ms.memberRowCount + (_ms.error ? ' error=' + _ms.error : ''));
    }
  } catch (e) { /* 워머가 죽어도 강습 캐시 워밍은 이미 끝났다 — 다음 주기 재시도 */ }

  // ★회원 목록(유효·종료) 캐시 워밍 — 2026-08-05 시토(배298 미완 마감).
  //   왜 여기냐: 이 두 스코프를 데우는 코드는 warmDashboardCache 에 08-03에 들어갔는데, 그 함수에는
  //   CLOCK 트리거가 없어 **한 번도 자동으로 돈 적이 없다**(라이브 확인 4건에 없음). 파이썬 쪽
  //   daily_scheduler._warm_dashboard_cache 는 마케팅 4종만 데우고 회원 목록은 목록에 없다.
  //   즉 GM 이 "느려서 CRM 관리가 안 된다"고 한 바로 그 화면만 워밍에서 빠져 있었다.
  //   실측(라이브 curl, 2026-08-05): scope=valid 캐시미스 12.1초 / 히트 3.3초 · ended 8.9초 / 6.9초.
  //   주기 5분 < 캐시 TTL 6분(8464줄) 이라 만료 구간 없이 항상 뜨겁게 유지된다.
  //   자기 URL 로 HTTP 를 쏘지 않고 _processAction 을 직접 부른다(위 강습 워밍과 같은 방식 — 인증·과금 무관).
  //   ★자리는 이 함수의 맨 끝이다 — 대기해제·LOSS 스탬프(위)는 시트에 쓰는 일이라 캐시 데우기보다
  //     먼저 끝나야 한다. 워밍을 앞에 두면 20초쯤을 그 앞에 얹어 트리거 실행시간 한계에 그만큼 가까워진다.
  //   ▸알아 둘 것: 워머가 시트를 읽는 12초 사이에 실무진이 저장하면, 워머가 저장 직전 값을 캐시에 넣어
  //     최대 6분간 옛 값이 보일 수 있다. 다만 이 경합은 원래 있던 것이다 — 캐시가 빈 상태에서 사람이
  //     목록을 열어도 똑같이 12초를 읽는다. 워머는 그 '찬 상태 읽기'를 사람 대신 떠안는 쪽이라
  //     전체 노출은 늘지 않는다. 없애려면 쓰기 시각을 보고 put 을 건너뛰는 장치가 필요한데,
  //     그건 실제 피해가 관측되면 그때 만든다(지금은 장치를 늘리지 않는다).
  ['valid', 'ended'].forEach(function (sc) {
    try { _processAction({ action: 'member_active_list', scope: sc, format: 'rows', nocache: '1' }); }
    catch (eWarmAa) { /* 한쪽 실패가 다른 쪽·아래 자동처리를 막지 않게 */ }
  });

  return done;
}

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
// 무거운 집계(type_channel·funnel_conversion 등)를 nocache=1로 강제 재계산해
// 캐시를 미리 데움 → 사용자는 항상 캐시 히트(~1.5초).
// Claude/LLM 토큰 무관(구글 서버 실행). 자기 /exec 호출이라 새 OAuth 스코프 없음.
// ★정정(2026-08-05 시토) — 이전 주석의 "시간 트리거가 5분마다 호출"은 실측 없이 적힌 문장이었다.
//   action=list_inquiry_triggers(읽기전용 진단)로 라이브 트리거를 직접 조회하니 이 함수(warmDashboardCache)에는
//   CLOCK 트리거가 설치돼 있지 않다 — installWarmTrigger()가 GM/시토 손으로 1회 실행된 적이 없다는 뜻.
//   즉 이 함수는 GAS 자체 트리거로는 자동 실행되지 않는다. 대신 telegram_bot/daily_scheduler.py 의
//   _warm_dashboard_cache(15분 간격, 봇 프로세스 가동 중일 때만)가 funnel_conversion·type_channel_breakdown·
//   click_stats·period_breakdown 4종은 대신 데운다 — member_active_list(valid/ended) 2스코프는 파이썬 목록에
//   없어 이 경로로는 안 식는다(둘 다 커버 X). 대기→멤버십 자동해제·LOSS일자 자동기록은 여기 얹지 않는다
//   (아래 참고) — 라이브로 확인된 CLOCK 트리거(warmLessonRosterCache)로 옮겼다.
var _WARM_EXEC_URL = 'https://script.google.com/macros/s/AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec';

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
    'action=period_breakdown' + range,
    // ★2026-08-03 시토(배298 · GM '너무 느려 CRM 관리가 안 된다')로 여기 넣었던 회원 목록 2스코프는
    //   2026-08-05 warmLessonRosterCache 로 옮겼다 — 이 함수엔 CLOCK 트리거가 없어 실제로는 한 번도
    //   돈 적이 없었기 때문이다. 같은 것을 두 곳에서 데우면 헛돈이 되므로 여기서는 뺀다.
    //   (배경 실측: 화면이 valid·ended 를 근접 프리페치하는데 GAS 가 동시실행을 큐잉해 한 건이 65.5초까지
    //    밀렸다 — 캐시를 상시 뜨겁게 두면 미스가 없어 경합도 사라진다. format=rows 만 데우는 이유는
    //    화면이 그 형식만 부르고 형식별로 캐시 키가 갈리기 때문.)
  ];
  qs.forEach(function(q) {
    try {
      UrlFetchApp.fetch(_WARM_EXEC_URL + '?' + q + '&nocache=1', { muteHttpExceptions: true, followRedirects: true });
    } catch (e) { /* 개별 실패 무시 — 다음 주기 재시도 */ }
  });
  // 대기→멤버십 자동해제·LOSS일자 자동기록은 여기 없다 — warmLessonRosterCache로 이관(2026-08-05 시토, 아래 참고).
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

