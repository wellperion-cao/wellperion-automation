// 웰페리온 랜딩 페이지 추적 Apps Script v1.0
// 리틀리(litt.ly) 대체 — 문의 추적 → 시트 누적
// 시트: 문의접수 (클릭 지수는 2026-07 GM 결정으로 전면 삭제)

// ─── 상수 ───
const LANDING_SPREADSHEET_ID = '1g9Ohmd8C_WxyvWt9EX58oEFZLiOAJ_EG7t7XteJFuGE';
const INQUIRY_SHEET = '문의접수';

// 회원부 시트 (유효회원 탭)
const MEMBER_SPREADSHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
const MEMBER_SHEET = '유효회원';
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
  // ─── 영문 문의 3종 (시모 2026-06-24) ───
  , { ssId: '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U', gid: 1887747109, type: '멤버십(영문)',    channelKeys: ['How Did You Hear About Us?', '경로', '채널'], programKeys: ['Programs of Interest', '종목', '프로그램'] }
  , { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 311319200,  type: '성인강습(영문)',  channelKeys: ['How Did You Hear About Us?', '경로', '채널'], programKeys: ['Program of Interest', '종목', '과목'] }
  , { ssId: '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw', gid: 931249179,  type: '유소년강습(영문)', channelKeys: ['How Did You Hear About Us?', '경로', '채널'], programKeys: ['WSC Program of Interest', '종목', '과목'] }
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
  if (/당근|daangn|danggn/i.test(s)) return '당근마켓';
  if (/동부이촌동|동커|동\.커|이촌동|카페/.test(s)) return '동부이촌동 커뮤니티';
  if (/네이버|naver|플레이스|블로그|블러그|검색|인터넷/i.test(s)) return '네이버';  // '지도' 단독 제외('인지도' 오탐 방지·네이버지도는 '네이버'로 포착)
  if (/소개|지인|친구|friend|추천|동기/i.test(s)) return '소개·지인';
  if (/회원|가족|자녀|아이|아들|딸|형|누나|언니|동생|둘째|첫째|보호자|학부모|부모|母|수강|강습|다녔|다니|이용|경험|기존|과거|재수강|정회원|연회원|멤버십회원|멤버쉽|wsc|준회원|수강생/i.test(s)) return '기존·과거 회원';
  if (/간판|현수막|홍보물|우편|워크인|방문|지나가|지나는|집근처|근처|동네|거주|입주|하이페리온|길에|봤|보여서|아파트|오프라인/.test(s)) return '오프라인';
  return '기타·미상';
}

// ─── 강습 종목 표준 버킷 (시포·GM 2026-06-26) ───
// 자유라벨('성인 수영 (개인레슨/단체레슨)' 등)을 표준 종목으로 집계한다.
// 라벨 통째 쪼개기 금지 — 한 응답이 여러 종목 다중체크면 각 버킷 +1(부분문자열 매칭).
// 어느 버킷에도 안 걸리고 텍스트가 있으면 '기타'로 귀속(날조 금지).
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
      var idxChan  = _findCol_(headers, cfg.channelKeys);          // 대분류(문의 채널) — 폴백 기준
      var idxChanFine = _findCol_(headers, ['중분류']);             // 문의 경로(중분류) — 정밀(있을 때만, 멤버십 탭)
      var idxAuto  = _findCol_(headers, ['유입경로(자동)', '유입경로자동', '유입경로_자동']);  // WP 문의폼 프리필 UTM(하드 신호) — 있을 때만, 최우선
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
        // WP 문의폼이 방문자의 클릭 UTM을 '유입경로(자동)'에 프리필 — 자기신고(대분류/중분류)보다 신뢰도 높은
        // 하드 신호이므로 최우선 override. 단, 매핑 불가(캠페인 슬러그 등)면 자기신고 유지(절대 후퇴 없음).
        if (idxAuto >= 0) {
          var autoRaw = String(r[idxAuto] || '').trim();
          if (autoRaw) {
            // 프리필 값은 "source" 또는 "source|campaign"(향후) 또는 캠페인 슬러그일 수 있음.
            var autoSrc = autoRaw.split('|')[0].trim();
            var autoCh = _canonicalChannel_(autoSrc);
            if (autoCh !== '기타·미상') chanRaw = autoSrc;  // 하드 UTM 신호가 자기신고를 이김 — 캠페인 슬러그는 그냥 통과(회귀 없음)
          }
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
    { 명: '모자수영',      sheet: '모자수영' }          // 누락 배선(팀시트 gid 1219410707) 2026-07-03
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
        var key = np + '|' + type;
        if (keyIdx.hasOwnProperty(key)) {
          var rr = rows[keyIdx[key]];                  // 기존 키 — 등록일 보존, 상태·이름·종목만 갱신
          if (rr[1] !== m.sport || rr[2] !== m.name || rr[4] !== m.status) {
            rr[1] = m.sport; rr[2] = m.name; rr[4] = m.status; dirty = true;
          }
        } else {
          rows.push([type, m.sport, m.name, m.phone, m.status, (seed ? '2000-01-01' : today), key]);
          newIdx.push(rows.length - 1);
          keyIdx[key] = rows.length - 1;
          dirty = true;
        }
      });
    });
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
    if (dirty && rows.length) {
      sh.getRange(2, 1, rows.length, _LESSON_REG_HEADER.length).setValues(rows);
    }
    cache.put('lesson_reg_synced', '1', 300);          // 5분 가드
  } catch (e) {
  } finally {
    lock.releaseLock();
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
      var newRows = sh.getRange(storedRow + 1, 1, realLastRow - storedRow, lastCol).getValues();
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
        var prog  = idxProg  >= 0 ? String(r[idxProg]  || '').trim() : '';
        if (!name)  name  = '-';
        if (!phone) phone = '-';
        if (!chan)  chan  = '-';

        var content = idxContent >= 0 ? String(r[idxContent] || '').trim() : '';
        if (content.length > 300) content = content.substring(0, 300) + '…';
        var msg = '🔔 [신규 문의]\n'
          + '유형: ' + cfg.type + '\n'
          + (prog ? '종목: ' + _teamChip(prog) + prog + '\n' : '')
          + '이름: ' + name + '\n'
          + '연락처: ' + phone + '\n'
          + '유입채널: ' + chan
          + (content ? '\n내용: ' + content : '');
        _notifyTelegram(msg, inquiryChatId);
      });

      // 기준선 갱신 — 실데이터 마지막 행번호로 저장 (빈행 포함 getLastRow 사용 금지)
      props.setProperty(propKey, String(realLastRow));
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

      events.forEach(function(ev) {
        if (stored[ev.mark]) return;  // 이미 알린 전환
        var chip = _teamChip(cfg.명);
        var who = ev.name || '(이름미상)';
        var owner = ev.owner ? (' · 담당 ' + ev.owner) : '';
        if (ev.bucket === 'SUC') {
          _notifyTelegram('✅ <b>[강습 등록]</b> ' + chip + cfg.명 + '\n· 수강생: ' + who + owner, chatId);
        } else {
          _notifyTelegram('📞 <b>[강습 컨택]</b> ' + chip + cfg.명 + '\n· 수강생: ' + who + owner, chatId);
        }
      });

      try { props.setProperty(propKey, JSON.stringify(curKeys)); }
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
      if (idxMemo >= 0 && String(r[idxMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) return; // 웹접수 미러 제외
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
      var msg = '🔔 [신규 문의 — 즉시]\n'
        + '유형: ' + cfg.type + '\n'
        + (prog ? '종목: ' + _teamChip(prog) + prog + '\n' : '')
        + '이름: ' + name + '\n'
        + '연락처: ' + phone + '\n'
        + '유입채널: ' + chan
        + (content ? '\n내용: ' + content : '');
      _notifyTelegram(msg, inquiryChatId);
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
  member_calendar:        true,
  member_inquiry_update:  true,  // 2026-06-22 GM '전체 공개' — 실명·전화 포함 수정
  member_inquiry_add:     true,  // 2026-06-23 전화·직접 문의 수기 추가
  member_inquiry_delete:  true,  // 행 삭제
  member_registered_list:     true,  // 2026-06-23 등록현황(SUC/단기SUC) 조회
  member_registered_setmonth: true,  // 등록회원 1~12월 체크 토글
  member_registered_delete:   true,  // 등록 해제(행 삭제)
  member_registered_add:      true,  // 2026-06-29 등록현황 직접 추가(페이지 수기 등록)
  member_active_list:         true,  // 멤버십 회원 명단(유효회원·전화 마스킹)
  member_active_update:       true,  // 2026-06-24 멤버십 셀 인라인 수정(유효회원 시트·전화 제외)
  member_owner_save:          true,  // 2026-07-18 시포 — 종목별 담당자 5칸(화이트리스트) 단일셀 저장(전화 매칭)
  cpo_today_stats:            true,  // 2026-06-24 CPO 오늘/이번달 문의·등록 건수(PII 미노출)
  cpo_churn_stats:            true,  // 2026-07-02 이탈 현황 실측(유효·이탈·이탈율·갱신임박 리스트) — 페이지 게이트 뒤(전체공개 정책과 동일)
  // 강습문의 페이지(CPO) — 멤버십 member_* 와 동일 정책(2026-06-26)
  lesson_inquiry_list:        true,  // 성인 강습 문의 목록(관리 필드 포함)
  lesson_stats:               true,  // 강습 통계(총·이번달·종목·경로 분포)
  lesson_calendar:            true,  // 상담예약 달력
  lesson_inquiry_update:      true,  // 진행상태·담당·상담메모·상담예약·방문상태 수정
  lesson_registered_roster:   true,  // 강습 등록현황·회원 명단(팀시트 상태열 _isLessonReg_) — PII 노출(전체공개 2026-06-22) 2026-06-27 시포
  lesson_registry_list:       true,  // 강습 금일 등록현황(원장 sync-on-load) — PII 노출(전체공개) 2026-06-27 시포
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
  funnel_conversion_detail:   true   // 2026-07-20 GM 지시(배834) — M1 마케팅 대시보드 채널별 가입전환 상세 명단. PII 노출(이름·연락처뒷4자리) — member_inquiry_list 등과 동일 정책(전체공개, 읽기전용·원본시트 미변경). 연락처는 서버에서 뒷4자리로 절단 후 반환(전체번호 미노출).
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
//  문의회원 페이지 전용 — '26년 신규문의' 익명 읽기 (CPO cpo/member/문의회원.html)
//  ★ A안(2026-06-22 GM go): 이름·전화·메모 완전 제거(빈값) → 공개 페이지 안전, PII_GATE 불필요.
//     실명 표시·편집(CRUD)은 별도 접근통제(B안) 후속. 기존 inquiry_list(대시보드 집계)와 무관.
// ═══════════════════════════════════════════
var _MI_SS_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
var _MI_SHEET = '26년 신규문의';
var _MI_GID_EN = 1887747109;   // 멤버십(영문) 응답탭 — 영어 문의가 별도 탭에 쌓여 CRM에서 누락되던 누수 수리(2026-07-09 시포·GM)
function _miSheet_() { return SpreadsheetApp.openById(_MI_SS_ID).getSheetByName(_MI_SHEET); }
function _miSheetEn_() { return _sheetByGid_(_MI_SS_ID, _MI_GID_EN); }
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
    if (!d && !t && !n) continue;
    out.push({ date: d, time: t, note: n });
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
    if (!d && !t && !n) return;
    clean.push({ date: d, time: t, note: n });
  });
  return clean.length ? JSON.stringify(clean) : '';
}

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
  var iExp1  = _miColIdx_(hdr, ['체험1 확정시간','체험1']);
  var iExp2  = _miColIdx_(hdr, ['체험2 확정시간','체험2']);
  var iExp3  = _miColIdx_(hdr, ['체험3 확정시간','체험3']);
  var iV2Dt  = _miColIdx_(hdr, ['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2']);  // 2차 방문 날짜(달력 보강용·확정시간 칸과 별개)
  var iVisited = _miColIdx_(hdr, ['방문완료일','방문완료','방문일자']);  // 방문 완료(진행상황과 독립 — 등록돼도 방문 기록 유지). 2026-06-29 시포
  var iRegProgram = _miColIdx_(hdr, ['등록종목']);      // 등록(SUC) 시 실제 등록한 종목 — 문의 시 관심프로그램(iProg)과 별개, 수정 가능. 2026-07-18 시토(GM요청) 대행.
  var iLossReason = _miColIdx_(hdr, ['LOSS사유']);      // 문의 퍼널 LOSS 사유 — 기존회원 종료사유(CHURN_REASON_COL)와 별개 체계. 2026-07-18 시토(GM요청) 대행.
  var iLossReasonNote = _miColIdx_(hdr, ['LOSS사유메모']);
  var iOwner = _miColIdx_(hdr, ['담당','담당자']);
  var iMemo  = _miColIdx_(hdr, ['메모','비고','담당자메모']);
  var iChan  = _miColIdx_(hdr, ['문의채널','유입채널','채널','경로','알게','How Did You Hear About Us?']);
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
    var _mo = {
      rowIndex: r + 2 + rowOffset,
      name:     iName  >= 0 ? String(row[iName]  || '') : '',  // 2026-06-22 GM '전체 공개' — 실명 노출
      phone:    iPhone >= 0 ? _fmtPhone_(row[iPhone]) : '',    // 연락처 노출 + 표시 정규화(앞 0 복원·하이픈)
      program:  iProg  >= 0 ? String(row[iProg]  || '') : '',
      status:   iStat  >= 0 ? String(row[iStat]  || '') : '',
      channel:  (iChan >= 0 && row[iChan]) ? _canonicalChannel_(String(row[iChan])) : '',  // 유입채널 표준 10버킷(빈값은 빈값 유지)
      // ── 체험 일정 분리 저장(#4, 2026-07-02 시포·GM): 체험1 날짜=J(시설투어·상담 예약)/시간=K(체험1 확정시간), 체험2 날짜=L(시설 체험 예약2)/시간=M(체험2 확정시간).
      //    상담=체험1(동일 1차 방문). 하위호환: 분리 날짜칸(J/L)이 비면 옛 결합칸(K/M)의 날짜부로 폴백 → 무손실.
      exp1:     (_miToISO_(iTour >= 0 ? row[iTour] : '') || _miToISO_(iExp1 >= 0 ? row[iExp1] : '')),
      exp1Time: _miTime_(iExp1 >= 0 ? row[iExp1] : ''),
      exp2:     (_miToISO_(iV2Dt >= 0 ? row[iV2Dt] : '') || _miToISO_(iExp2 >= 0 ? row[iExp2] : '')),
      exp2Time: _miTime_(iExp2 >= 0 ? row[iExp2] : ''),
      inquiryContent: iContent >= 0 ? String(row[iContent] || '') : '',   // 문의 내용(N열 자유서술) — #1
      // 하위호환 유지(옛 필드 — 미사용, 잔존 참조 안전용): 상담·체험3·2차방문은 체험1/2로 흡수
      tourDate: '', tourTime: '', exp3: '', exp3Time: '', visit2Date: '', visit2Time: '',
      visited:    (iVisited >= 0 && String(row[iVisited] == null ? '' : row[iVisited]).trim() !== '') ? true : false,  // 방문 완료 여부(독립·공백/0 오인 방지)
      visitDate:  (iVisited >= 0) ? _miToISO_(row[iVisited]) : '',  // 방문 완료일
      regProgram: iRegProgram >= 0 ? String(row[iRegProgram] || '') : '',      // 등록 종목(SUC 시 실제 등록한 종목). 2026-07-18 시토(GM요청) 대행.
      lossReason: iLossReason >= 0 ? String(row[iLossReason] || '') : '',      // LOSS 사유(문의 퍼널 전용).
      lossReasonNote: iLossReasonNote >= 0 ? String(row[iLossReasonNote] || '') : '',
      timestamp:_miToISO_(iTs   >= 0 ? row[iTs]   : ''),
      memo:     iMemo  >= 0 ? String(row[iMemo]  || '') : '',
      owner:    iOwner >= 0 ? String(row[iOwner] || '') : '',
      contact1: (iC1 >= 0 && iC1 < row.length) ? _fmtContact_(row[iC1]) : '',
      contact2: (iC2 >= 0 && iC2 < row.length) ? _fmtContact_(row[iC2]) : '',
      contact3: (iC3 >= 0 && iC3 < row.length) ? _fmtContact_(row[iC3]) : '',
      // 출처 물리 시트 gid + 기재 언어 — 영문 탭 병합 표시·저장 라우팅용(row.gid 그대로 되돌려 보내면 정확한 탭에 기록). 2026-07-09 시포·GM.
      gid: gid,
      lang: iLang >= 0 ? String(row[iLang] || '').trim() : ''
    };
    // 예약목록(가변): JSON 우선 → 없으면 체험1·2 흡수(하위호환·무손실). 2026-07-03 시포·GM
    var _resArr = _resParse_(iRes >= 0 ? row[iRes] : '');
    if (!_resArr.length) {
      if (_mo.exp1) _resArr.push({ date: _mo.exp1, time: _mo.exp1Time || '', note: '' });
      if (_mo.exp2) _resArr.push({ date: _mo.exp2, time: _mo.exp2Time || '', note: '' });
    }
    _mo.reservations = _resArr;
    // 연락이력(가변): JSON 우선 → 없으면 Contact1/2/3 흡수(비파괴·하위호환). 2026-07-08 시포·GM(축2)
    var _histArr = _resParse_(iHist >= 0 ? row[iHist] : '');
    if (!_histArr.length) {
      [_mo.contact1, _mo.contact2, _mo.contact3].forEach(function(cv){
        if (cv) _histArr.push({ date: '', time: '', note: cv });
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
    for (var ri = 0; ri < resArr.length; ri++) {
      var res = resArr[ri];
      if (!res.date) continue;                               // 날짜 없는 항목 스킵
      if (month && res.date.slice(0, 7) !== month) continue; // 표시 월 필터
      out.push({
        date: res.date, kind: '재등록상담', source: 'active', time: res.time || '', tmin: _miTminKR_(res.time), slot: (ri === 0 ? 'recon' : 'r' + ri), resIdx: ri,
        name: _nm, phone: _ph, program: _pg,
        status: '', rowIndex: r + 2, memo: res.note, note: res.note,
        owner: '', contact1: '', contact2: '', contact3: '', visited: false, visitDate: ''
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
// 등록 해제(잘못 등록 되돌리기) — 등록현황에서 전화키 매칭 행 제거(중복 있으면 전부). 2026-06-29 시포.
function _regRemove_(phone) {
  var key = _regNormPhone_(phone);
  if (!key) return;
  var sh = _regSheet_();
  var last = sh.getLastRow();
  for (var i = last; i >= 2; i--) {
    if (_regNormPhone_(sh.getRange(i, 2).getValue()) === key) sh.deleteRow(i);
  }
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
  { keys: ['LOSS사유'],                                             canon: 'LOSS사유' },      // 문의 퍼널 LOSS 사유(강습) — 멤버십과 동일 체계. 2026-07-18 시토(GM요청) 대행.
  { keys: ['LOSS사유메모'],                                         canon: 'LOSS사유메모' },
  { keys: ['등록종목'],                                             canon: '등록종목' }        // 등록(SUC) 시 실제 등록한 종목 — 멤버십 member_inquiry_update와 동일 체계. LOSS사유와 같은 정확일치 전용 키(부분일치 충돌 방지 — '성인 강습 종목'/'WSC 강습 종목' 등 기존 종목칸과 별개). 2026-07-20 시포(GM요청).
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
// 강습 행 배열 — 문의 + 관리 필드 통합. 빈 행(성함·연락처 둘 다 없음) 스킵.
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
  var iLossR  = _findCol_(hdr, ['LOSS사유']);      // 문의 퍼널 LOSS 사유(강습) — 멤버십과 동일 체계. 2026-07-18 시토(GM요청) 대행.
  var iLossRN = _findCol_(hdr, ['LOSS사유메모']);
  var iRegProgram = _findCol_(hdr, ['등록종목']);  // 등록(SUC) 시 실제 등록한 종목(강습) — 멤버십과 동일 체계. 2026-07-20 시포(GM요청).
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
    var _lHistArr = _resParse_(_lHistRaw);            // JSON이면 파싱(스태프가 페이지에서 편집한 이력)
    if (!_lHistArr.length) {
      var _lHistPlain = String(_lHistRaw || '').trim();
      if (_lHistPlain) _lHistArr.push({ date: '', time: '', note: _lHistPlain });  // GM Contact 컬럼 plain text 보존(읽기에서 사라지지 않게)
      else if (_lMemo) _lHistArr.push({ date: '', time: '', note: _lMemo });        // 레거시 상담메모 폴백
    }
    out.push({
      rowIndex: r + 2 + rowOffset,
      timestamp: _miToISO_(iTs >= 0 ? row[iTs] : ''),
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
      // 종목별 독립 관리(축7) — 파싱맵(없으면 {}). 분리 로직은 프론트에서만(GM 결정) — 여기선 원맵만 반환.
      bySport: _lessonSportMgmtParse_(iSportMgmt >= 0 ? row[iSportMgmt] : ''),
      lossReason:     iLossR  >= 0 ? String(row[iLossR]  || '') : '',   // LOSS 사유(강습 문의 퍼널). 2026-07-18 시토(GM요청) 대행.
      lossReasonNote: iLossRN >= 0 ? String(row[iLossRN] || '') : '',
      regProgram: iRegProgram >= 0 ? String(row[iRegProgram] || '') : '',   // 등록 종목(SUC 시 실제 등록한 종목, 강습). 2026-07-20 시포(GM요청).
      // 출처 물리 시트 gid + 기재 언어 — 영문 탭 병합 표시·저장 라우팅용(row.gid 그대로 되돌려 보내면 정확한 탭에 기록). 2026-07-09 시포·GM.
      gid: gid,
      lang: iLang >= 0 ? String(row[iLang] || '').trim() : ''
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
      timestamp: _miToISO_(iTs >= 0 ? row[iTs] : ''),
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
      gid: gid, lang: '', intake: true
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
      timestamp: _miToISO_(iTs >= 0 ? row[iTs] : ''),
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

function _processAction(body) {
  const action = body.action || '';
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
          return {
            row:      rowNum,
            type:     rrbCfg.type,
            name:     idxName  >= 0 ? String(r[idxName]  || '').trim() : '',
            phone:    idxPhone >= 0 ? String(r[idxPhone] || '').trim() : '',
            channel:  idxChan  >= 0 ? String(r[idxChan]  || '').trim() : '',
            ts:       tsStr
          };
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
          var msg = '🔔 [신규 문의 — 즉시]\n'
            + '유형: ' + pvCfg.type + '\n'
            + (prog ? '종목: ' + _teamChip(prog) + prog + '\n' : '')
            + '이름: ' + name + '\n'
            + '연락처: ' + phone + '\n'
            + '유입채널: ' + chan
            + (content ? '\n내용: ' + content : '');

          return { row: rowNum, msg: msg, prog_col_found: pvIdxProg >= 0 };
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

  // ─── 유입 자체 Survey 폼 제출 (배1037 갈래B · 시포 2026-07-15) ───
  //   멤버십→'26년 신규문의'(_miSheet_·member_inquiry_list 자동정합) / 강습→신규 '강습 신규문의' 스태프탭(lesson_inquiry_list 병합 자동정합).
  //   수집 유실 0: 멱등 submissionId(Cache dedup) + 서버 재검증. 저장 실패는 재시도가능(noRetry 미설정) 응답 → 프론트 대기큐 재전송.
  //   스팸방어(구글폼 캡차 상실 보상): 토큰 · 허니팟 · 타이밍 게이트 · 레이트리밋. WEB_INTAKE_TAG로 마케팅 집계 이중계상 방지.
  if (action === 'intake_submit') {
    // 1) 토큰(위조방지)
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    // 2) 허니팟 — 봇이 채운 hp 값 있으면 조용히 성공가장(무기록). 숨김필드라 사람 오탐 거의 없음. #2(2026-07-18): 드롭 추적 로그.
    if (String(body.hp || '').trim() !== '') { try { Logger.log('[intake drop] honeypot phone=' + String(body.phone||'')); } catch(e){} return _json({ ok: true, id: 'HP', dedup: true }); }
    // 3) 타이밍 게이트 — 너무 빠른 제출은 봇 의심이나 자동완성 등 정상 사용자 오탐 가능 → #2(2026-07-18 시포): 조용히 버리지 않고 저장하되 '검토' 플래그(비고)로 표면화(실사용자 유실 0).
    var _fillMs = parseInt(body.fillMs || '0', 10);
    var _iFastFlag = (_fillMs > 0 && _fillMs < 1500);
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
    var _iCat = String(body.category || '').trim();   // 'membership' | 'adult' | 'youth' | 'summer' | 'rental' | 'business'(신규 3종 2026-07-16 시토)
    var _iCompany = String(body.company || '').trim();        // business 전용(name 키 없음)
    var _iContactName = String(body.contactName || '').trim(); // business 전용(name 키 없음)
    if (_iCat !== 'membership' && _iCat !== 'adult' && _iCat !== 'youth' && _iCat !== 'summer' && _iCat !== 'rental' && _iCat !== 'business') return _json({ ok: false, error: '문의 유형이 올바르지 않습니다.', noRetry: true });
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

    try {
      if (_iCat === 'membership') {
        // 멤버십 → '26년 신규문의'(_miSheet_) append. member_inquiry_list가 이미 이 탭 read → 관리페이지 자동정합(읽기 무변경).
        var _imSh = _miSheet_();
        if (!_imSh) return _json({ ok: false, error: '멤버십 시트 없음' });   // 재시도 가능(noRetry 미설정)
        var _imHdr = _miHeaders_(_imSh);
        var _imRow = new Array(_imHdr.length).fill('');
        function _imSet(names, val) { if (val === undefined || val === null || val === '') return; var ci = _miColIdx_(_imHdr, names); if (ci >= 0) _imRow[ci] = val; }
        var _imNowDt = new Date();
        _imSet(['날짜', '접수일'], _korDateOnly_(_imNowDt));       // A열 — 기존 444건 다수 포맷 'yy. M. d' 통일(2026-07-20). '타임스탬프'와 한 호출로 합치면 _miColIdx_가 B만 채우므로 반드시 분리
        _imSet(['타임스탬프', 'timestamp'], _korDateTime_(_imNowDt));  // B열 — 기존 다수 포맷 'yyyy. M. d 오전/오후 h:mm:ss' 통일
        _imSet(['성함', '이름'], _iName);
        _imSet(['연락처', '전화', '휴대폰'], _fmtPhone_(_iPhone));
        _imSet(['관심 있는 프로그램 종류', '관심 있는 프로그램 종목', '관심프로그램', '프로그램', '종목'], _iProgram);
        _imSet(['진행현황', '진행상황', '진행상태', '상태'], '신규');
        _imSet(['문의채널', '유입채널', '채널', '경로'], _iChannel || _canonicalChannel_(_iUtmSource));
        _imSet(['접수 담당자', '담당'], '웹 자동접수');
        _imSet(['시설투어 및 상담 예약', '시설견학 및 상담 일정', '상담 예약', '상담'], _dateOnlyStrip_(body.exp1Date));  // 날짜 전용 칸 — 시각 혼입 방어(2026-07-20)
        _imSet(['기타 웰페리온에 대한 문의 사항', '기타 웰페리온', '자유롭게 적어', '문의 사항', '내용'], _iMessage);
        _imSet(['유입경로(자동)', '유입경로자동', '유입경로_자동'], _iUtmSource ? (_iUtmSource + (_iUtmMedium ? '|' + _iUtmMedium : '')) : (_iChannel || ''));  // V열 — utm 원본 제자리 기록(2026-07-20). H/I(중분류·소분류)는 자기신고 분류라 건드리지 않음
        _imSet(['비고', '메모', '담당자메모'], WEB_INTAKE_TAG + (_iFastFlag ? ' ⚠️빠른제출' : ''));   // [웹접수] 유지(집계 중복방지). utm 원문은 위 유입경로(자동)로 이관 — 비고엔 더 이상 처박지 않음(2026-07-20)
        _imSet(['개인정보 수집·이용 동의'], '동의');   // U열 — 검증만 하고 미기록이던 버그 수리(2026-07-20 시포). 강습·공간렌트·비즈니스 분기와 동일 표기 '동의' 통일. 헤더가 매우 긴 문장이라 짧은 키(동의·개인정보)는 다른 칸과 충돌 위험 있어 실헤더 대조로 확인한 고유 서두 구절만 사용. 과거 행은 무변경(신규 append만).
        _imSh.appendRow(_imRow);
        try { _cacheInvalidateJson_(_iCache, 'micache'); } catch (e) {}
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
        _lsSet(['타임스탬프'], _lsNowFull);
        var _lsDateCi = _findCol_(_lsHdr, ['문의일', '문의 일', '날짜']);
        if (_lsDateCi >= 0) { if (!_lsRow[_lsDateCi]) _lsRow[_lsDateCi] = _lsToday; }
        else if (!String(_lsHdr[0] || '').trim() && !_lsRow[0]) { _lsRow[0] = _lsNowFull; }   // 성인탭 A열 빈헤더=타임스탬프 대응(시간 보존)
        _lsSet(['성함', '이름'], _iName);
        _lsSet(['연락처', '핸드폰', '전화', '휴대폰'], _fmtPhone_(_iPhone));
        _lsSet(['나이', '연령', '자녀'], _iAge);
        _lsSet(['강습 종목', '종목', '과목'], _isSummer ? ('여름방학특강 - ' + _iProgram) : _iProgram);
        _lsSet(['문의 경로', '경로', '채널'], _iChannel || _canonicalChannel_(_iUtmSource));
        _lsSet(['문의 사항', '문의사항', '내용'], _iMessage);
        // 배(희망 레슨시간 유실, 2026-07-20 실측규명): 구키 ['희망','레슨 시간','시간']는 '희망' 부분일치가
        //   idx5 종목칸("...강습 종목 (희망종목 모두 체크)")에 먼저 걸려 정답칸(idx9)에 도달 못하고 조용히 스킵됨
        //   (idx5가 이미 채워져 있어 _lsSet 가드가 막음). 정답 헤더 전문을 정확일치 1순위로, 폴백은 다른 헤더와
        //   충돌 없는 '레슨 시간'만 남김(성인·WSC 양쪽 실제 헤더 대조 검증 완료 — 둘 다 idx9 정확 반환).
        _lsSet(['희망하시는 레슨 시간을 체크해주세요', '레슨 시간'], _isSummer ? _iWishMonth : _iWish);
        _lsSet(['접수 담당자', '담당자 혹은', '담당'], '웹 자동접수');
        _lsSet(['개인정보', '동의', '수집·이용'], '동의');
        _lsSet(['진행 상황', '진행상황', '상태'], '신규');
        _lsSet(['비고', '메모'], _iId);   // 접수ID를 비고에 흘림(기존 탭엔 별도 ID칸 없음)
        _lsSh.insertRowAfter(1); _lsSh.getRange(2, 1, 1, _lsRow.length).setValues([_lsRow]);   // 최근일자 상단(2026-07-18 GM 기존 지시 유지)
        try {
          _cacheInvalidateJson_(_iCache, 'licache|' + _iType + '|year');
          _cacheInvalidateJson_(_iCache, 'licache|' + _iType + '|all');
        } catch (e) {}
      } else if (_iCat === 'rental') {
        // 공간렌트 → '공간렌트 문의' 신규 탭(_MI_SS_ID 하위, 2026-07-16 시토)
        var _rtSh = _rentalIntakeSheet_(true);
        if (!_rtSh) return _json({ ok: false, error: '공간렌트 문의 시트 생성 실패' });
        var _rtHdr = _rtSh.getRange(1, 1, 1, _rtSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
        var _rtRow = new Array(_rtHdr.length).fill('');
        function _rtSet(name, val) { if (val === undefined || val === null || val === '') return; var ci = _findCol_(_rtHdr, [name]); if (ci >= 0) _rtRow[ci] = val; }
        _rtSet('타임스탬프', Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'));  // 2026-07-18 시간 보존
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
        if (_iFastFlag) _rtSet('비고', '⚠️ 빠른제출 자동검토');
        _rtSh.appendRow(_rtRow);
      } else {
        // 비즈니스(_iCat === 'business') → '비즈니스 문의' 신규 탭(_MI_SS_ID 하위, 2026-07-16 시토)
        var _bzSh = _businessIntakeSheet_(true);
        if (!_bzSh) return _json({ ok: false, error: '비즈니스 문의 시트 생성 실패' });
        var _bzHdr = _bzSh.getRange(1, 1, 1, _bzSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
        var _bzRow = new Array(_bzHdr.length).fill('');
        function _bzSet(name, val) { if (val === undefined || val === null || val === '') return; var ci = _findCol_(_bzHdr, [name]); if (ci >= 0) _bzRow[ci] = val; }
        _bzSet('타임스탬프', Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'));  // 2026-07-18 시간 보존
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
        if (_iFastFlag) _bzSet('비고', '⚠️ 빠른제출 자동검토');
        _bzSh.appendRow(_bzRow);
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
      var _iChat = _prop('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
      var _iCatLabelMap = { membership: '멤버십', adult: '성인 강습', youth: '유소년 강습', summer: '여름 특강', rental: '공간 렌트', business: '비즈니스 제휴' };
      var _iCatLabel = _iCatLabelMap[_iCat] || _iCat;
      var _iDisplayName = (_iCat === 'business') ? (_iCompany + ' / ' + _iContactName) : _iName;
      var _iExtra = '';
      if (_iCat === 'summer') _iExtra = (_iTarget ? ('\n대상: ' + _iTarget) : '') + (_iWishMonth ? ('\n희망월: ' + _iWishMonth) : '');
      if (_iCat === 'rental') _iExtra = (_iSpace ? ('\n공간: ' + _iSpace) : '') + (_iPurpose ? ('\n용도: ' + _iPurpose) : '');
      if (_iCat === 'business') _iExtra = (_iPartnerType ? ('\n제휴유형: ' + _iPartnerType) : '');
      _notifyTelegram('🔔 <b>[웹 문의 접수]</b> (자체폼)\n유형: ' + _iCatLabel + '\n이름: ' + _iDisplayName + '\n연락처: ' + _fmtPhone_(_iPhone)
        + (_iProgram ? ('\n관심: ' + _iProgram) : '') + _iExtra + (_iMessage ? ('\n내용: ' + _iMessage.substring(0, 100)) : ''), _iChat);
    } catch (e) {}
    return _json({ ok: true, id: _iId, submissionId: _sid, message: '문의가 접수되었습니다.' });
  }

  // ─── (임시) 강습 폼탭 테스트행 삭제 — 증분1 검증 정리용. 웰리 수동. 2026-07-18 ───
  if (action === 'cpo_lesson_test_delete') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _tRep = {};
    [ { n: '1. 성인강습', gid: 111889422 }, { n: '2. WSC 강습', gid: 268994754 } ].forEach(function(cfg){
      var sh = _sheetByGid_(LESSON_SS_ID, cfg.gid); if (!sh) { _tRep[cfg.n] = '없음'; return; }
      var lr = sh.getLastRow(), lc = sh.getLastColumn(); if (lr < 2) { _tRep[cfg.n] = 0; return; }
      var hdr = sh.getRange(1, 1, 1, lc).getValues()[0].map(function(v){ return String(v).trim(); });
      var phI = _findCol_(hdr, ['연락처', '핸드폰', '전화', '휴대폰']); var nmI = _findCol_(hdr, ['성함', '이름']);
      var data = sh.getRange(2, 1, lr - 1, lc).getValues(); var del = 0;
      for (var r = data.length - 1; r >= 0; r--) {
        var ph = phI >= 0 ? String(data[r][phI] || '').replace(/[^0-9]/g, '') : '';
        var nm = nmI >= 0 ? String(data[r][nmI] || '') : '';
        if (/^010000070/.test(ph) || /자동검증/.test(nm)) { sh.deleteRow(r + 2); del++; }
      }
      _tRep[cfg.n] = del;
    });
    return _json({ ok: true, deleted: _tRep });
  }

  // ─── (임시) 강습 신규문의(자체폼 유입, 배1037) 탭 → 기존 폼탭(1.성인강습/2.WSC강습) 일회성 이관 ───
  //   증분2(캐시수리·테스트삭제·17이관) 시포 2026-07-18. intake_submit 전환 때와 동일 유연키(_findCol_).
  //   유형 라우팅: 성인강습→111889422 / 유소년강습·여름특강(...)→268994754(여름특강은 종목 앞에 '여름방학특강 - ' 접두).
  //   지정 강사·Contact·진행 상황은 스태프 작업분이므로 기존값 그대로 보존 이관(신규 기본값으로 덮지 않음).
  //   이관 후 원본 탭은 헤더만 남기고 데이터행 clear(탭 삭제 금지 — 새 문의가 계속 이 탭에 쌓이는 구조 유지).
  if (action === 'cpo_migrate_intake_to_formtabs') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _miSrc = _lessonIntakeSheet_(false);
    if (!_miSrc) return _json({ ok: false, error: '강습 신규문의 탭 없음' });
    var _miLr = _miSrc.getLastRow(), _miLc = _miSrc.getLastColumn();
    if (_miLr < 2) return _json({ ok: true, migrated: 0, remaining: 0 });
    var _miHdr = _miSrc.getRange(1, 1, 1, _miLc).getValues()[0].map(function(v){ return String(v).trim(); });
    var _miRows = _miSrc.getRange(2, 1, _miLr - 1, _miLc).getValues();
    // 소스(강습 신규문의) 칼럼 인덱스 — 유연키
    var _mSDate  = _findCol_(_miHdr, ['타임스탬프', '날짜']);
    var _mSName  = _findCol_(_miHdr, ['성함', '이름']);
    var _mSPhone = _findCol_(_miHdr, ['연락처', '핸드폰', '전화']);
    var _mSAge   = _findCol_(_miHdr, ['나이', '연령', '자녀']);
    var _mSType  = _findCol_(_miHdr, ['유형']);
    var _mSSport = _findCol_(_miHdr, ['강습 종목', '종목']);
    var _mSWish  = _findCol_(_miHdr, ['희망', '레슨 시간', '시간']);
    var _mSChan  = _findCol_(_miHdr, ['문의 경로', '경로']);
    var _mSNote  = _findCol_(_miHdr, ['문의 사항', '내용']);
    var _mSAgree = _findCol_(_miHdr, ['개인정보', '동의']);
    var _mSStat  = _findCol_(_miHdr, ['진행 상황', '상태']);
    var _mSOwner = _findCol_(_miHdr, ['지정 강사']);
    var _mSHist  = _findCol_(_miHdr, ['Contact', '연락이력']);
    var _mSMemo  = _findCol_(_miHdr, ['비고']);
    var _mDstCache = {};   // gid → { sh, hdr } — 목적 탭 핸들 캐시(반복 open 방지)
    function _mDst(gid) {
      if (_mDstCache[gid]) return _mDstCache[gid];
      var sh = _lessonSheet_(gid);
      var rec = sh ? { sh: sh, hdr: _lessonEnsureCols_(sh) } : null;
      _mDstCache[gid] = rec;
      return rec;
    }
    var _mMigrated = 0, _mSkipped = [];
    for (var mi = 0; mi < _miRows.length; mi++) {
      var mRow = _miRows[mi];
      var mName = _mSName >= 0 ? String(mRow[_mSName] || '').trim() : '';
      var mPhone = _mSPhone >= 0 ? String(mRow[_mSPhone] || '').trim() : '';
      if (!mName && !mPhone) continue;   // 완전 빈 행(카운트 대상 아님) — clear로 함께 정리
      var mType = _mSType >= 0 ? String(mRow[_mSType] || '').trim() : '';
      var isYouth = (mType === '유소년강습') || /^여름특강/.test(mType);
      var isSummer = /^여름특강/.test(mType);
      var mGid = isYouth ? 268994754 : 111889422;
      var mDst = _mDst(mGid);
      if (!mDst) { _mSkipped.push({ srcRow: mi + 2, reason: 'dst-sheet-missing' }); continue; }
      var mDstRow = new Array(mDst.hdr.length).fill('');
      var _mSet = function(keys, val) { if (val === undefined || val === null || val === '') return; var ci = _findCol_(mDst.hdr, keys); if (ci >= 0 && !mDstRow[ci]) mDstRow[ci] = val; };
      var mDateRaw = _mSDate >= 0 ? mRow[_mSDate] : '';
      var mDateOnlyStr = (mDateRaw instanceof Date && !isNaN(mDateRaw.getTime()))
        ? Utilities.formatDate(mDateRaw, 'Asia/Seoul', 'yyyy-MM-dd')
        : String(mDateRaw || '');
      // 타임스탬프는 시:분:초까지 보존(2026-07-18) — 소스가 Date면 전체 포맷, 문자열이면 원형 그대로 이관(이미 시간 포함일 수 있음).
      var mDateFullStr = (mDateRaw instanceof Date && !isNaN(mDateRaw.getTime()))
        ? Utilities.formatDate(mDateRaw, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss')
        : String(mDateRaw || '');
      _mSet(['타임스탬프'], mDateFullStr);
      var _mDstDateCi = _findCol_(mDst.hdr, ['문의일', '문의 일', '날짜']);
      if (_mDstDateCi >= 0) { if (!mDstRow[_mDstDateCi]) mDstRow[_mDstDateCi] = mDateOnlyStr; }
      else if (!String(mDst.hdr[0] || '').trim() && !mDstRow[0]) { mDstRow[0] = mDateFullStr; }   // 성인탭 A열 빈헤더=타임스탬프 대응
      _mSet(['성함', '이름'], mName);
      _mSet(['연락처', '핸드폰', '전화', '휴대폰'], _fmtPhone_(mPhone));
      _mSet(['나이', '연령', '자녀'], _mSAge >= 0 ? String(mRow[_mSAge] || '') : '');
      var mSport = _mSSport >= 0 ? String(mRow[_mSSport] || '') : '';
      _mSet(['강습 종목', '종목', '과목'], isSummer ? ('여름방학특강 - ' + mSport) : mSport);
      _mSet(['문의 경로', '경로', '채널'], _mSChan >= 0 ? String(mRow[_mSChan] || '') : '');
      _mSet(['문의 사항', '문의사항', '내용'], _mSNote >= 0 ? String(mRow[_mSNote] || '') : '');
      _mSet(['희망', '레슨 시간', '시간'], _mSWish >= 0 ? String(mRow[_mSWish] || '') : '');
      _mSet(['접수 담당자', '담당자 혹은', '담당'], '웹 자동접수');
      _mSet(['개인정보', '동의', '수집·이용'], (_mSAgree >= 0 ? String(mRow[_mSAgree] || '') : '') || '동의');
      // ★진행 상황·지정 강사·Contact·비고 — 직원 작업분 그대로 보존(신규 기본값으로 덮지 않음)
      var mStat = _mSStat >= 0 ? String(mRow[_mSStat] || '') : '';
      var _mDstStCi = _findCol_(mDst.hdr, ['진행 상황', '진행상황', '상태']);
      if (_mDstStCi >= 0) mDstRow[_mDstStCi] = mStat || '신규';
      var mOwner = _mSOwner >= 0 ? String(mRow[_mSOwner] || '') : '';
      if (mOwner) { var _mDstOwCi = _findColExact_(mDst.hdr, ['지정 강사', '관리담당']); if (_mDstOwCi >= 0) mDstRow[_mDstOwCi] = mOwner; }
      var mHist = _mSHist >= 0 ? mRow[_mSHist] : '';
      if (mHist) { var _mDstHiCi = _findCol_(mDst.hdr, [CONTACT_HIST_COL, 'Contact']); if (_mDstHiCi >= 0) mDstRow[_mDstHiCi] = mHist; }
      var mMemo = _mSMemo >= 0 ? String(mRow[_mSMemo] || '') : '';
      var _mDstMeCi = _findCol_(mDst.hdr, ['비고', '메모']);
      if (_mDstMeCi >= 0 && mMemo) mDstRow[_mDstMeCi] = mDstRow[_mDstMeCi] ? (mDstRow[_mDstMeCi] + ' / ' + mMemo) : mMemo;
      mDst.sh.insertRowAfter(1);
      mDst.sh.getRange(2, 1, 1, mDstRow.length).setValues([mDstRow]);
      _mMigrated++;
    }
    _miSrc.getRange(2, 1, _miLr - 1, _miLc).clearContent();   // 헤더 유지·탭 삭제 금지 — 데이터행만 정리
    var _mRemainRows = _miSrc.getRange(2, 1, _miLr - 1, _miLc).getValues();
    var _mRemaining = _mRemainRows.filter(function(r){ return r.some(function(v){ return String(v || '').trim() !== ''; }); }).length;
    try {
      ['성인강습', '유소년강습'].forEach(function(t){
        var _mCache = CacheService.getScriptCache();
        _cacheInvalidateJson_(_mCache, 'licache|' + t + '|year');
        _cacheInvalidateJson_(_mCache, 'licache|' + t + '|all');
      });
    } catch (e) {}
    return _json({ ok: true, migrated: _mMigrated, remaining: _mRemaining, skipped: _mSkipped });
  }

  // ─── (임시) 강습 등록현황 이관: 멤버십SS→강습SS 복사(삭제 별도). 웰리 수동. 2026-07-18 ───
  if (action === 'cpo_migrate_lesson_reg') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _src = SpreadsheetApp.openById(_MI_SS_ID).getSheetByName('강습 등록현황');
    if (!_src) return _json({ ok: false, error: '원본 강습 등록현황 없음(멤버십SS)' });
    var _sLr = _src.getLastRow(), _sLc = _src.getLastColumn();
    if (_sLr < 1 || _sLc < 1) return _json({ ok: false, error: '원본 비어있음' });
    var _vals = _src.getRange(1, 1, _sLr, _sLc).getValues();
    var _dstSs = SpreadsheetApp.openById(LESSON_SS_ID);
    var _dst = _dstSs.getSheetByName('강습 등록현황');
    if (!_dst) _dst = _dstSs.insertSheet('강습 등록현황');
    _dst.clear();
    _dst.getRange(1, 1, _vals.length, _sLc).setValues(_vals);
    _dst.setFrozenRows(1);
    try { _dst.getRange(1, 1, 1, _sLc).setFontWeight('bold'); } catch (e) {}
    return _json({ ok: true, srcRows: _sLr, dstRows: _dst.getLastRow(), cols: _sLc });
  }

  // ─── (임시) 멤버십SS의 옛 강습 등록현황 탭 삭제 — 이관·검증 완료 후에만. 웰리 수동. 2026-07-18 ───
  if (action === 'cpo_delete_old_lesson_reg') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });
    var _oSs = SpreadsheetApp.openById(_MI_SS_ID);
    var _oSh = _oSs.getSheetByName('강습 등록현황');
    if (!_oSh) return _json({ ok: true, deleted: false, note: '이미 없음' });
    var _oRows = _oSh.getLastRow();
    _oSs.deleteSheet(_oSh);
    return _json({ ok: true, deleted: true, rows: _oRows });
  }

  // ═══════════════════════════════════════════════════════════════════
  // ★ INC-020 복구 전용 · 실행 후 제거할 것. 2026-07-20 시포(GM 지시, 팀리드 대행).
  // 동시접근으로 행이 밀린 상태에서 member_inquiry_delete가 잘못 호출돼 실고객 문의 2건(권소현 행 바로
  // 아래에 GM이 미리 만들어둔 빈 줄 2개)이 삭제된 사고 복구. rowIndex 하드코딩 절대 금지 — gviz는 캐시
  // 지연으로 실제 시트와 행번호가 다를 수 있어(GM 화면 실측과 불일치 확인됨) SpreadsheetApp으로 매 호출
  // 라이브 상태에서 이름·전화 앵커를 다시 찾는다. 행 삽입·삭제 금지 — 이미 있는 빈 행 2개에 값만 채움.
  // 가드 1~4 중 하나라도 실패하면 아무것도 쓰지 않고 실패만 반환(멱등·안전 우선). 배포 후 팀리드 지시로만
  // 1회 실행 — 아직 실행 안 함. 실행 완료 확인 후 다음 배포에서 이 액션 통째로 제거할 것.
  // ═══════════════════════════════════════════════════════════════════
  if (action === 'inc020_restore') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });  // cpo_lesson_test_delete·cpo_delete_old_lesson_reg와 동일 내부전용 토큰게이트
    var _irSh = _miSheet_();
    if (!_irSh) return _json({ ok: false, error: '시트 없음' });
    var _irHdr = _miHeaders_(_irSh);
    var _irPhCi = _miColIdx_(_irHdr, ['연락처', '전화', '휴대폰']);
    if (_irPhCi < 0) return _json({ ok: false, error: '연락처 칸 못 찾음' });
    var _irLastBefore = _irSh.getLastRow();
    if (_irLastBefore < 2) return _json({ ok: false, error: '데이터 없음' });
    var _irData = _irSh.getRange(2, 1, _irLastBefore - 1, _irHdr.length).getValues();  // 라이브 1회 스캔(가드1·4 공용)

    // 가드1 — 권소현(010-3794-3617) 행, 정확히 1건이어야 함.
    var _irAnchorPh = _normPhone_('010-3794-3617');
    var _irAnchorRows = [];
    for (var _i1 = 0; _i1 < _irData.length; _i1++) { if (_normPhone_(_irData[_i1][_irPhCi]) === _irAnchorPh) _irAnchorRows.push(_i1 + 2); }
    if (_irAnchorRows.length !== 1) return _json({ ok: false, error: 'anchor-not-unique', detail: '권소현(010-3794-3617) 행 ' + _irAnchorRows.length + '건 발견 — 정확히 1건이어야 함', anchorRows: _irAnchorRows });
    var _irAnchorRow = _irAnchorRows[0];

    // 가드2 — 앵커 바로 아래 2개 행이 완전히 빈 행인지(라이브 재확인 — 가드3 직전까지 최신 상태 보장).
    var _irBlank1Row = _irAnchorRow + 1, _irBlank2Row = _irAnchorRow + 2;
    if (_irBlank2Row > _irSh.getLastRow()) return _json({ ok: false, error: 'not-enough-rows', detail: '권소현 아래 2개 행이 존재하지 않음' });
    function _irIsBlankRow_(rowNum) {
      var vals = _irSh.getRange(rowNum, 1, 1, _irHdr.length).getValues()[0];
      for (var _c = 0; _c < vals.length; _c++) { if (String(vals[_c] || '').trim() !== '') return false; }
      return true;
    }
    if (!_irIsBlankRow_(_irBlank1Row) || !_irIsBlankRow_(_irBlank2Row)) return _json({ ok: false, error: 'rows-not-blank', detail: '권소현 아래 2개 행 중 하나 이상에 값이 있음 — 중단(행 삽입·삭제 없이는 복구 불가 상태)' });

    // 가드3 — 그 다음 행(앵커+3)이 이동걸(010-3777-6675)인지.
    var _irDgRow = _irAnchorRow + 3;
    if (_irDgRow > _irSh.getLastRow()) return _json({ ok: false, error: 'anchor2-missing', detail: '이동걸 위치에 행이 없음' });
    var _irDgPhVal = _irSh.getRange(_irDgRow, _irPhCi + 1).getValue();
    if (_normPhone_(_irDgPhVal) !== _normPhone_('010-3777-6675')) return _json({ ok: false, error: 'anchor2-mismatch', detail: '권소현+3행이 이동걸(010-3777-6675)이 아님 — 실제값:' + _irDgPhVal });

    // 가드4(멱등성) — 시트 전체에 복구 대상 전화(010-5215-9886/010-8816-2121)가 이미 있으면 중단(중복 입력 방지).
    var _irNew1 = _normPhone_('010-5215-9886'), _irNew2 = _normPhone_('010-8816-2121');
    for (var _i4 = 0; _i4 < _irData.length; _i4++) {
      var _p4 = _normPhone_(_irData[_i4][_irPhCi]);
      if (_p4 === _irNew1 || _p4 === _irNew2) return _json({ ok: false, error: 'already-restored', detail: '이미 복구된 것으로 보이는 연락처가 시트에 존재 — 멱등 가드로 중단' });
    }

    // ── 가드 1~4 전부 통과 — 이제부터 쓴다. 행 삽입·삭제 없음(insertRows·deleteRow 호출 자체가 없음) — 이미 있는 빈 행 2개에 setValues만. ──
    // 헤더는 전부 이름 매칭(_miColIdx_ — 정확일치 1순위·부분일치는 다른 칸과 안 겹치는 고유 단어만 폴백). 열 번호 하드코딩 없음.
    var _irNameKeys = { 날짜:['날짜'], 타임: ['타임스탬프'], 성함:['성함','이름'], 연락처:['연락처','전화','휴대폰'],
      거주지:['거주지 [거주지역]','거주지'],
      프로그램:['3. 관심 있는 프로그램 종목','관심 있는 프로그램 종류','관심프로그램','프로그램'],
      경로메인:['4. 웰페리온을 어떤 경로로 알게 되셨나요?','웰페리온을 어떤 경로로 알게'],
      경로중분류:['문의 경로\n(중분류)','중분류'], 경로소분류:['문의 경로\n(소분류)','소분류'],
      문의사항:['6. 웰페리온에 대한 문의 사항 및 운동 목적 등을 기록해주시면 참고하여 상담 진행됩니다. 감사합니다.',
                '기타 웰페리온에 대한 문의 사항','기타 웰페리온','자유롭게 적어','문의 사항','문의사항','Health & Wellness Goals'],
      접수담당자:['접수 담당자 혹은 본인 이름'], Contact1:['Contact1'], 진행현황:['진행현황'] };
    function _irBuildRow_(f) {
      var row = new Array(_irHdr.length).fill('');
      function set(k, val) { if (val === undefined || val === null || val === '') return; var ci = _miColIdx_(_irHdr, _irNameKeys[k]); if (ci >= 0) row[ci] = val; }
      set('날짜', f.dateStr); set('타임', f.ts); set('성함', f.name); set('연락처', f.phone); set('거주지', f.region);
      set('프로그램', f.program); set('경로메인', f.channelMain); set('경로중분류', f.channelMid); set('경로소분류', f.channelSub);
      set('문의사항', f.note); set('접수담당자', f.staff); set('Contact1', f.contact1); set('진행현황', f.status);
      return row;
    }
    // 입력값 — GM 지시 그대로, 한 글자도 변경 없음. 타임스탬프=실제 Date(문자열 아님), KST 16:28:40/18:32:44를 UTC 인스턴트로 고정(스크립트/시트 타임존 설정과 무관하게 항상 정확).
    var _irRow1 = _irBuildRow_({
      dateStr: '26. 5. 4 오', ts: new Date(Date.UTC(2026, 4, 4, 7, 28, 40)),
      name: '여', phone: '010-5215-9886', region: '기타',
      program: '플래티넘 (Gym + G.X + Sauna 이용)',
      channelMain: '오프라인 (옥외간판/아파트 홍보물/현수막)', channelMid: '아파트 홍보', channelSub: '남산타운',
      note: '남산타운-실장님', staff: '임정은', contact1: '26/5/4 무응답/담당자 문자 발송완-정은', status: '컨택중'
    });
    var _irRow2 = _irBuildRow_({
      dateStr: '26. 5. 4 오', ts: new Date(Date.UTC(2026, 4, 4, 9, 32, 44)),
      name: '장수진', phone: '010-8816-2121', region: '기타',
      program: '노블레스 (Gym + G.X + Swimming + Sauna 이용)',
      channelMain: '인지도 (입주민/만기회원/준회원)', channelMid: '준회원', channelSub: '',
      note: '멤버십상담/주희쌤전달', staff: '임정은', contact1: '26/5/4 무응답/담당자 문자 발송완-정은', status: '컨택중'
    });
    _irSh.getRange(_irBlank1Row, 1, 1, _irRow1.length).setValues([_irRow1]);
    _irSh.getRange(_irBlank2Row, 1, 1, _irRow2.length).setValues([_irRow2]);

    // 쓰기 후 되읽어 검증(라이브 재조회).
    var _irV1 = _irSh.getRange(_irBlank1Row, 1, 1, _irHdr.length).getValues()[0];
    var _irV2 = _irSh.getRange(_irBlank2Row, 1, 1, _irHdr.length).getValues()[0];
    try { _cacheInvalidateJson_(CacheService.getScriptCache(), 'micache'); } catch (e) {}
    try { _notifyTelegram('🛠 INC-020 복구 실행 — 행 ' + _irBlank1Row + '·' + _irBlank2Row + ' 채움(권소현 행 ' + _irAnchorRow + ' 앵커)'); } catch (e) {}
    return _json({
      ok: true, message: 'INC-020 복구 완료',
      anchorRow: _irAnchorRow, restoredRow1: _irBlank1Row, restoredRow2: _irBlank2Row,
      headerMatch: Object.keys(_irNameKeys).reduce(function(acc, k) { acc[k] = _miColIdx_(_irHdr, _irNameKeys[k]); return acc; }, { 연락처: _irPhCi }),
      verifyReadback: {
        row1PhoneMatch: _normPhone_(_irV1[_irPhCi]) === _irNew1,
        row2PhoneMatch: _normPhone_(_irV2[_irPhCi]) === _irNew2
      },
      rowsBefore: _irLastBefore, rowsAfter: _irSh.getLastRow()
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // ★ [읽기 전용 진단] INC-020 복구 전제조건 라이브 실측 — 2026-07-20 시포(팀리드 대행).
  // inc020_restore 가 'rows-not-blank'로 멈춘 원인을 확인하기 위한 진단 전용 액션.
  // gviz는 캐시 지연으로 못 믿는다 — SpreadsheetApp 직독만 사용. 쓰기 코드 없음(setValue·
  // insertRows·deleteRow 전무). 실행 후 제거 대상(inc020_restore와 함께 정리).
  // ═══════════════════════════════════════════════════════════════════
  if (action === 'inc020_diag') {
    if (String(body.t || '') !== _intakeToken_()) return _json({ ok: false, error: 'bad-token', noRetry: true });  // inc020_restore와 동일 내부전용 토큰게이트
    var _idSh = _miSheet_();
    if (!_idSh) return _json({ ok: false, error: '시트 없음' });
    var _idHdr = _miHeaders_(_idSh);
    var _idPhCi = _miColIdx_(_idHdr, ['연락처', '전화', '휴대폰']);
    var _idNmCi = _miColIdx_(_idHdr, ['성함', '이름']);
    var _idTsCi = _miColIdx_(_idHdr, ['타임스탬프']);
    if (_idPhCi < 0) return _json({ ok: false, error: '연락처 칸 못 찾음' });
    var _idLast = _idSh.getLastRow();
    if (_idLast < 2) return _json({ ok: true, totalRows: _idLast, error: '데이터 없음' });
    var _idData = _idSh.getRange(2, 1, _idLast - 1, _idHdr.length).getValues();

    function _idIsBlank_(arr) {
      for (var c = 0; c < arr.length; c++) { if (String(arr[c] || '').trim() !== '') return false; }
      return true;
    }
    // physicalRow = 실제 시트 행번호(헤더=1행 기준 1-base)
    function _idRowInfo_(physicalRow) {
      if (physicalRow < 2 || physicalRow > _idLast) return { rowNum: physicalRow, outOfRange: true };
      var arr = _idData[physicalRow - 2];
      return {
        rowNum: physicalRow,
        name: _idNmCi >= 0 ? String(arr[_idNmCi] || '') : '',
        phone: _idPhCi >= 0 ? String(arr[_idPhCi] || '') : '',
        timestamp: _idTsCi >= 0 ? String(arr[_idTsCi] || '') : '',
        isBlank: _idIsBlank_(arr)
      };
    }

    // ① 권소현(010-3794-3617) 실제 행번호·매치건수
    var _idKwonPh = _normPhone_('010-3794-3617');
    var _idKwonRows = [];
    for (var i1 = 0; i1 < _idData.length; i1++) { if (_normPhone_(_idData[i1][_idPhCi]) === _idKwonPh) _idKwonRows.push(i1 + 2); }

    // ② 권소현 기준 위 2행 · 아래 6행(첫 매치 앵커) — 본인 행 포함(참고용)
    var _idNeighbors = [];
    var _idKwonRowInfo = null;
    if (_idKwonRows.length > 0) {
      var _idAnchor = _idKwonRows[0];
      _idKwonRowInfo = _idRowInfo_(_idAnchor);
      for (var off = -2; off <= 6; off++) {
        if (off === 0) continue;   // 본인 행은 _idKwonRowInfo로 별도 표기
        _idNeighbors.push(_idRowInfo_(_idAnchor + off));
      }
    }

    // ③ 이동걸(010-3777-6675) 실제 행번호
    var _idDgPh = _normPhone_('010-3777-6675');
    var _idDgRows = [];
    for (var i3 = 0; i3 < _idData.length; i3++) { if (_normPhone_(_idData[i3][_idPhCi]) === _idDgPh) _idDgRows.push(i3 + 2); }

    // ④ 복구대상 전화(010-5215-9886/010-8816-2121) 이미 존재하는지
    var _idNew1 = _normPhone_('010-5215-9886'), _idNew2 = _normPhone_('010-8816-2121');
    var _idNew1Rows = [], _idNew2Rows = [];
    for (var i4 = 0; i4 < _idData.length; i4++) {
      var _p4 = _normPhone_(_idData[i4][_idPhCi]);
      if (_p4 === _idNew1) _idNew1Rows.push(i4 + 2);
      if (_p4 === _idNew2) _idNew2Rows.push(i4 + 2);
    }

    // ⑥ 완전히 빈 행 전수 스캔
    var _idBlankRows = [];
    for (var i6 = 0; i6 < _idData.length; i6++) { if (_idIsBlank_(_idData[i6])) _idBlankRows.push(i6 + 2); }

    // ⑦ [2026-07-20 추가·완전성 확인용] 권소현 앵커+1·+2행(복구대상 2건) 전체 칸 덤프 — 헤더-값 쌍 전부.
    //   타임스탬프가 실제 Date인지(문자열 아님) 구분 위해 typeof/instanceof도 함께 반환. 읽기만(getValues) — 쓰기 없음.
    function _idFullRow_(physicalRow) {
      if (physicalRow < 2 || physicalRow > _idLast) return { rowNum: physicalRow, outOfRange: true };
      var arr = _idData[physicalRow - 2];
      var cells = {};
      for (var c = 0; c < _idHdr.length; c++) {
        var key = _idHdr[c] || ('(빈헤더_' + c + ')');
        var raw = arr[c];
        var isDateVal = (raw instanceof Date) && !isNaN(raw.getTime());
        cells[key] = {
          value: isDateVal ? Utilities.formatDate(raw, 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss') : (raw === null || raw === undefined ? '' : String(raw)),
          type: isDateVal ? 'Date' : (typeof raw)
        };
      }
      return { rowNum: physicalRow, isBlank: _idIsBlank_(arr), cells: cells };
    }
    var _idFullRows = [];
    if (_idKwonRows.length > 0) {
      var _idAnchor2 = _idKwonRows[0];
      _idFullRows.push(_idFullRow_(_idAnchor2 + 1));
      _idFullRows.push(_idFullRow_(_idAnchor2 + 2));
    }

    return _json({
      ok: true,
      totalRows: _idLast,   // ⑤ getLastRow()
      kwon: { phone: '010-3794-3617', matchRows: _idKwonRows, matchCount: _idKwonRows.length, rowInfo: _idKwonRowInfo },
      neighbors: _idNeighbors,   // 권소현 앵커 기준 -2~-1(위 2행)·1~6(아래 6행), 본인행 제외
      dongguel: { phone: '010-3777-6675', matchRows: _idDgRows, matchCount: _idDgRows.length },
      alreadyRestored: {
        '010-5215-9886': _idNew1Rows,
        '010-8816-2121': _idNew2Rows
      },
      blankRows: _idBlankRows,
      blankRowCount: _idBlankRows.length,
      fullRows: _idFullRows   // ⑦ 앵커+1·+2행 전체 칸(헤더-값-타입) — 완전성 확인용
    });
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
  if (action === 'member_inquiry_list') {
    // 조회 캐시(축1, TTL 60초) — nocache=1 우회. 미스·실패 시 그대로 시트 재조회 폴백. 2026-07-08 시토.
    var miCache = CacheService.getScriptCache();
    var miCacheKey = 'micache';
    if (!_nc) {
      var miHit = _cacheGetJson_(miCache, miCacheKey);
      if (miHit) return _json(miHit);
    }
    // 한글 '26년 신규문의' + 영문 멤버십 탭 병합 — 영어 문의 누수 수리(2026-07-09 시포·GM). 영문 탭 미존재/에러는 조용히 스킵(무중단).
    var miRows = _miReadRows_(_miSheet_());
    try { miRows = miRows.concat(_miReadRows_(_miSheetEn_())); } catch (eMiEn) {}
    var _miFull = true;  // 2026-06-25 GM '성함·연락처 다 공개' — 마스킹 해제(무인증 공개 주의·시토 인증게이트 전제)
    var miResult = { ok: true, count: miRows.length, data: miRows, anon: !_miFull };
    _cachePutJson_(miCache, miCacheKey, miResult, 60);
    return _json(miResult);
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
    try { _cacheInvalidateJson_(CacheService.getScriptCache(), 'micache'); } catch (e) {}
    return _json({ ok: true, message: '추가되었습니다.', rowIndex: maSh.getLastRow() });
  }

  // ─── 문의회원 페이지(CPO): 예약 달력 (익명·상담/체험 일정) ───
  if (action === 'member_calendar') {
    var mcMonth = String(body.month || '');  // 'YYYY-MM'
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
        mcEvents.push({ date: dateStr, kind: kind, source: 'inquiry', time: timeStr || '', tmin: _miTminKR_(timeStr), slot: slot || '', resIdx: (resIdx == null ? '' : resIdx), name: row.name || '', phone: row.phone || '', program: row.program, status: row.status, rowIndex: row.rowIndex, memo: row.memo || '', note: noteStr || '', owner: row.owner || '', contact1: row.contact1 || '', contact2: row.contact2 || '', contact3: row.contact3 || '', visited: row.visited, visitDate: row.visitDate || '', gid: row.gid });
      }
      // 예약 리스트(가변) — 각 예약이 독립 이벤트. 예약1·2는 exp1/exp2 미러 슬롯(하위 소비자 안전망). 라벨=예약. 2026-07-03 시포·GM.
      (row.reservations || []).forEach(function(res, ri){
        add(res.date, '예약', res.time, (ri === 0 ? 'exp1' : (ri === 1 ? 'exp2' : 'r' + ri)), ri, res.note);
      });
    });
    // ── 재등록 상담 병합(유효회원 시트) — 재등록상담 날짜/시간 있는 회원을 달력 이벤트로. 기존 신규 이벤트 무손상. 2026-07-03 시포·GM.
    try { _memberReconEvents_(mcMonth).forEach(function(e){ mcEvents.push(e); }); } catch (eRe) {}
    return _json({ ok: true, month: mcMonth, count: mcEvents.length, events: mcEvents });
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
    // ★행키 검증(비파괴·하위호환): keyPhone 동봉 시 대상 행의 현재 전화와 대조 — 삭제/시트편집 후 rowIndex 밀림으로 엉뚱한 회원 덮어쓰기 방지.
    //   keyPhone=편집 전(로드된) 전화. body.phone(새 값)과 별개. keyPhone 미전송이면 기존 동작 폴백(정상 편집 무중단).
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      var _muPhCi = _miColIdx_(muHdr, ['연락처','전화','휴대폰']);
      if (_muPhCi >= 0) {
        var _muRowPh = _normPhone_(muSh.getRange(muRow, _muPhCi + 1).getValue());
        var _muKeyPh = _normPhone_(body.keyPhone);
        if (_muKeyPh && _muRowPh !== _muKeyPh) {
          // rowIndex가 대상과 어긋남(gviz 압축 인덱스·시트 편집 밀림·빈행) → keyPhone으로 올바른 물리 행 복구.
          // 찾으면 그 행으로 재지정(저장 성공), 못 찾으면 거부(오수정 방지·기존 안전동작). 2026-07-13 시포(INC-013 근본수리).
          var _muFound = _findRowByPhone_(muSh, _muPhCi, _muKeyPh);
          if (_muFound >= 2) muRow = _muFound;
          else return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패(대상 전화 없음) — 목록을 새로고침 후 다시 시도하세요' });
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
    _muSet(['성함','이름'], body.name);
    _muSet(['연락처','전화','휴대폰'], _fmtPhoneOrUndef_(body.phone));  // 하이픈 텍스트 저장 → 앞 0 보존(undefined는 스킵)
    _muSet(['관심 있는 프로그램 종류','관심프로그램','프로그램'], body.program);
    _muSet(['진행현황','진행상황','진행상태','상태'], body.status);
    _muSet(['문의채널','유입채널','채널','경로'], body.channel);
    _muSet(['메모','비고','담당자메모'], body.memo);
    _muSet(['담당','담당자'], body.owner);
    // 체험 일정 분리 저장(#4): 체험1 날짜→J, 시간→K / 체험2 날짜→L, 시간→M. 상담=체험1. 2026-07-02 시포·GM.
    _muSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], body.exp1Date);  // J = 체험1 날짜
    _muSet(['체험1 확정시간','체험1'], body.exp1Time);                                          // K = 체험1 시간
    _muSet(['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2'], body.exp2Date);        // L = 체험2 날짜
    _muSet(['체험2 확정시간','체험2'], body.exp2Time);                                          // M = 체험2 시간
    _muSet(['기타 웰페리온에 대한 문의 사항','기타 웰페리온','자유롭게 적어','문의 사항'], body.inquiryContent);  // N = 문의내용(#1)
    // ── 예약 리스트(가변) — JSON 우선 저장 + 체험1·2(J/K/L/M) 미러. 하위호환 편집(exp*)만 오면 JSON 동기화. 2026-07-03 시포·GM
    if (body.reservations !== undefined) {
      var _muRes = _resParse_(body.reservations);
      var _muResCi = _miEnsureCol_(muSh, muHdr, INQ_RES_COL);
      var _muResCell = muSh.getRange(muRow, _muResCi + 1);
      _muResCell.setNumberFormat('@');
      _muResCell.setValue(_resStringify_(_muRes));
      // 미러: 예약1→J/K, 예약2→L/M (없으면 클리어). 달력 폴백·하위 소비자 안전망(무손실).
      _muSet(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담'], _muRes[0] ? _muRes[0].date : '');
      _muSet(['체험1 확정시간','체험1'], _muRes[0] ? _muRes[0].time : '');
      _muSet(['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2'], _muRes[1] ? _muRes[1].date : '');
      _muSet(['체험2 확정시간','체험2'], _muRes[1] ? _muRes[1].time : '');
    } else if (body.exp1Date !== undefined || body.exp1Time !== undefined || body.exp2Date !== undefined || body.exp2Time !== undefined) {
      // 하위호환 경로(상담 모달·구 인라인)가 체험1·2만 편집 → 예약목록 JSON이 이미 있으면 동기화(스테일 방지). 예약3+ 보존.
      var _rcCi = _miColIdx_(muHdr, [INQ_RES_COL]);
      if (_rcCi >= 0) {
        var _prev = _resParse_(muSh.getRange(muRow, _rcCi + 1).getValue());
        var _cellISO = function(names){ var c = _miColIdx_(muHdr, names); return c >= 0 ? _miToISO_(muSh.getRange(muRow, c + 1).getValue()) : ''; };
        var _cellTime = function(names){ var c = _miColIdx_(muHdr, names); return c >= 0 ? _miTime_(muSh.getRange(muRow, c + 1).getValue()) : ''; };
        var _rebuilt = [
          { date: _cellISO(['시설투어 및 상담 예약','시설견학 및 상담 일정','상담 예약','상담']), time: _cellTime(['체험1 확정시간','체험1']), note: (_prev[0] && _prev[0].note) || '' },
          { date: _cellISO(['시설 체험 예약2(날짜 기록)','시설 체험 예약2','체험 예약2']), time: _cellTime(['체험2 확정시간','체험2']), note: (_prev[1] && _prev[1].note) || '' }
        ];
        for (var _pi = 2; _pi < _prev.length; _pi++) _rebuilt.push(_prev[_pi]);
        var _rcCell = muSh.getRange(muRow, _rcCi + 1);
        _rcCell.setNumberFormat('@');
        _rcCell.setValue(_resStringify_(_rebuilt));
      }
    }
    _muSetCol(['Contact1'], _fmtContactOrUndef_(body.contact1));
    _muSetCol(['Contact2'], _fmtContactOrUndef_(body.contact2));
    _muSetCol(['Contact3'], _fmtContactOrUndef_(body.contact3));
    // ── 연락이력(가변) — 축2: body.contacts(JSON 문자열/배열) 수신 시 저장. 미전송이면 무영향(기존 필드만 갱신).
    //    Contact1/2/3은 위에서 그대로 유지(비파괴·원복 안전) — 신·구 컬럼 병존. 2026-07-08 시포·GM.
    var _muHistPrevCount = 0;
    var _muHistNewArr = null;
    if (body.contacts !== undefined) {
      try {
        var _muHistCi = _miColIdx_(muHdr, [CONTACT_HIST_COL]);
        var _muPrevHistArr = (_muHistCi >= 0) ? _resParse_(muSh.getRange(muRow, _muHistCi + 1).getValue()) : [];
        _muHistPrevCount = _muPrevHistArr.length;
        _muHistNewArr = _resParse_(body.contacts);
        var _muHistCi2 = _miEnsureCol_(muSh, muHdr, CONTACT_HIST_COL);
        var _muHistCell = muSh.getRange(muRow, _muHistCi2 + 1);
        _muHistCell.setNumberFormat('@');
        _muHistCell.setValue(_resStringify_(_muHistNewArr));
      } catch (eHist) { Logger.log('연락이력 저장 실패: ' + eHist.message); }
    }
    // 방문 완료 — 진행상황과 독립 칸(방문완료일). 등록(SUC)돼도 방문 기록 유지. body.visited 미전송이면 무변경.
    //   true=방문일자(없으면 오늘) 기록 / false=클리어. 칸 없으면 _miEnsureCol_이 생성. 2026-06-29 시포.
    if (body.visited !== undefined) {
      var _vci = _miEnsureCol_(muSh, muHdr, '방문완료일');
      muSh.getRange(muRow, _vci + 1).setValue(body.visited ? (body.visitDate || _todayKR_()) : '');
    }
    // 등록 종목 — 등록(SUC) 시 실제 등록한 종목(문의 시 관심프로그램과 별개, 수정 가능). 칸 없으면 자동 생성(GM 수작업 0).
    //   GM 요청(2026-07-18, 시토 대행): "등록 시 어떤 종목을 등록했는지" 기록. 2026-07-18 시토·GM.
    if (body.regProgram !== undefined) {
      var _rpci = _miEnsureCol_(muSh, muHdr, '등록종목');
      muSh.getRange(muRow, _rpci + 1).setValue(body.regProgram);
    }
    // LOSS 사유 — 문의 퍼널 LOSS 전용(기존회원 종료사유 모달·CHURN_REASON_COL과 별개 체계·혼동 금지). 칸 없으면 자동 생성.
    //   GM 요청(2026-07-18, 시토 대행). 2026-07-18 시토·GM.
    if (body.lossReason !== undefined) {
      var _lrci = _miEnsureCol_(muSh, muHdr, 'LOSS사유');
      muSh.getRange(muRow, _lrci + 1).setValue(body.lossReason);
    }
    if (body.lossReasonNote !== undefined) {
      var _lrnci = _miEnsureCol_(muSh, muHdr, 'LOSS사유메모');
      muSh.getRange(muRow, _lrnci + 1).setValue(body.lossReasonNote);
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
      // 등록 전환 전용 알림은 '실제 전환(이전≠SUC)' 1회만 — 매 저장 중복 알림 방지. '문의 알림' 방.
      if (!_wasSuc) {
        try {
          var _regChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
          _notifyTelegram('✅ <b>등록 전환</b> — 문의회원이 등록(' + _muNewStatus + ')으로 전환\n· 이름: ' + (_coName || '-') + '\n· 등록종목: ' + _teamChip(_coRegProg) + (_coRegProg || '-') + '\n· 담당: ' + (_coOwner || '-'), _regChatId);
        } catch (e) {}
      }
    }
    // 1차 컨택 알림(축6, 이력-기준으로 일원화): 연락이력 0건 → ≥1건 전이 시 1회만. 2026-07-08 시포·GM.
    //   구 '컨택 시작'(상태=상담중 등 진입 기준) 알림은 중복 방지를 위해 이 이력-기준 알림으로 대체(제거).
    if (_muHistNewArr && _muHistPrevCount === 0 && _muHistNewArr.length >= 1) {
      try {
        var _histFirst = _muHistNewArr[0];
        var _histWhen = ((_histFirst.date || '') + ' ' + (_histFirst.time || '')).trim();
        var _histChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
        _notifyTelegram('📞 <b>1차 컨택 진행</b> — ' + (_coName || '-') + ' (' + _teamChip(_coProg) + (_progNameOnly_(_coProg) || '-') + ')\n일시: ' + (_histWhen || '-') + '\n내용: ' + (_histFirst.note || '-') + (_coOwner ? '\n담당: ' + _coOwner : ''), _histChatId);
      } catch (e) {}
    }
    // 등록 해제(이전 SUC → 신규 비SUC, status 명시 전송 시) — 잘못 등록 되돌리기: 등록현황에서 제거. 2026-06-29 시포.
    if (_wasSuc && !_isSucNew && body.status !== undefined) {
      var _urPhCi = _miColIdx_(muHdr, ['연락처','전화','휴대폰']);
      var _urPhone = (body.keyPhone && String(body.keyPhone)) || (_urPhCi >= 0 ? String(muSh.getRange(muRow, _urPhCi + 1).getValue() || '') : '');
      try { _regRemove_(_urPhone); } catch (e) {}
    }
    // 조회 캐시 무효화(축1) — 다음 목록 조회부터 최신 반영. 2026-07-08 시토.
    try { _cacheInvalidateJson_(CacheService.getScriptCache(), 'micache'); } catch (e) {}
    return _json({ ok: true, rowIndex: muRowRaw, message: '수정되었습니다.' });
  }

  // ─── 문의회원 페이지(CPO): 행 삭제 ───
  if (action === 'member_inquiry_delete') {
    var mdRow = parseInt(body.rowIndex, 10);
    if (!mdRow || mdRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    var mdSh = _miResolveSheet_(body.gid, body.rowIndex);  // gid 또는 rowIndex 오프셋으로 물리 시트 라우팅(2026-07-09 시포·GM, 영어 문의 누수 수리)
    if (!mdSh) return _json({ ok: false, error: '시트 없음' });
    if (mdRow >= _ROW_OFFSET_EN_) mdRow -= _ROW_OFFSET_EN_;  // 실제 물리 행으로 디코드. 2026-07-09 시포·GM.
    if (mdRow > mdSh.getLastRow()) return _json({ ok: false, error: '행 범위 초과' });
    // ★행키 검증(필수·예외 없음, INC-020 재발방지 2026-07-20): keyPhone 미전송/빈값이면 대조 없이 무조건 거부.
    //   구버전은 keyPhone 미전송 시 하위호환으로 검증을 생략해 통과시켰고, 동시접근으로 행이 밀린 상태에서
    //   그 폴백이 실사용돼 실고객 문의 2건이 삭제되는 사고(INC-020)로 이어짐 — 폴백 완전 제거.
    if (body.keyPhone === undefined || String(body.keyPhone) === '') {
      return _json({ ok: false, error: 'keyPhone 필수 — 대조 없이 삭제 불가' });
    }
    var _mdHdr = _miHeaders_(mdSh);
    var _mdPhCi = _miColIdx_(_mdHdr, ['연락처','전화','휴대폰']);
    var _mdRowPh = (_mdPhCi >= 0) ? _normPhone_(mdSh.getRange(mdRow, _mdPhCi + 1).getValue()) : '';
    var _mdKeyPh = _normPhone_(body.keyPhone);
    if (!_mdRowPh || _mdRowPh !== _mdKeyPh) {
      return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패(대상 전화 불일치/불명) — 목록 새로고침 후 다시 시도' });
    }
    mdSh.deleteRow(mdRow);
    // 조회 캐시 무효화(축1) — delete 직후 최대 60초 stale 반환 방지(연쇄 오삭제 위험 차단). 2026-07-08 시토 안전수리.
    try { _cacheInvalidateJson_(CacheService.getScriptCache(), 'micache'); } catch (e) {}
    try { _notifyTelegram('🗑 문의회원 삭제(공개페이지) — 행 ' + mdRow); } catch (e) {}
    return _json({ ok: true, rowIndex: mdRow, message: '삭제되었습니다.' });
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
    return _json({ ok: true, type: lrrType, total: lrrRoster.length, bySport: lrrBySport, roster: lrrRoster });
  }

  // ─── 강습 등록 원장 명단 (금일 등록현황) — sync-on-load. 2026-06-27 시포 ───
  //   호출 시 _syncLessonRegistry_() 선실행(팀시트 SUC→원장 upsert). type 일치 + 등록일 ∈ [from,to] 명단.
  //   from/to 미지정 = 오늘(KST). 카드=오늘 명단. 시드 직후 금일=0이 정상(과거분은 기준선 2000-01-01).
  if (action === 'lesson_registry_list') {
    _syncLessonRegistry_();
    var lglType = String(body.type || '');
    var lglToday = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd');
    var lglFrom = String(body.from || lglToday);
    var lglTo   = String(body.to   || lglToday);
    // 문의내용 조인(2a, 2026-07-18 시포): 강습 문의(성인+유소년, 한글+영문+자체폼 신규문의 모두 병합)의 note 필드
    //   (_lessonReadRows_/_lessonIntakeReadRows_가 INQUIRY_CONTENT_KEYS로 탐지한 문의사항/문의내용/내용 칼럼)를
    //   정규화 전화 키로 1회 맵 구성 후 등록현황 각 행에 O(1) 조회 조인. 동일 전화 여러 건이면 뒤(최근) 건이 이김.
    var lglNoteMap = {};
    try {
      ['성인강습', '유소년강습'].forEach(function(t) {
        _lessonReadRowsMerged_({ type: t }).forEach(function(r) {
          var p = _normPhone_(r.phone);
          if (p && r.note) lglNoteMap[p] = r.note;
        });
      });
    } catch (eNoteMap) {}
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
    return _json({ ok: true, total: lsTotal, thisMonth: lsThisMonth, bySport: _lsSort(lsSport), byChannel: _lsSort(lsChan) });
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
    // ★행키 검증(비파괴·하위호환): keyPhone 동봉 시 대상 행 전화 대조 — rowIndex 밀림 오수정 방지. 미전송이면 폴백.
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      var _luPhCi = _findCol_(luHdr, ['연락처', '전화', '휴대폰']);
      if (_luPhCi >= 0) {
        var _luRowPh = _normPhone_(luSh.getRange(luRow, _luPhCi + 1).getValue());
        var _luKeyPh = _normPhone_(body.keyPhone);
        if (_luKeyPh && _luRowPh !== _luKeyPh) {
          // rowIndex 어긋남(gviz 압축 인덱스·시트 편집 밀림·빈행) → keyPhone으로 올바른 물리 행 복구. 2026-07-13 시포(INC-013).
          var _luFound = _findRowByPhone_(luSh, _luPhCi, _luKeyPh);
          if (_luFound >= 2) luRow = _luFound;
          else return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패(대상 전화 없음) — 목록을 새로고침 후 다시 시도하세요' });
        }
      }
    }
    function _luSet(colNames, val) {
      if (val === undefined || val === null) return;
      var ci = _findCol_(luHdr, colNames);
      if (ci >= 0) luSh.getRange(luRow, ci + 1).setValue(val);
    }
    // ★종목별 독립 관리(축7, GM 2026-07-08 확정) 라우팅: body.sport(sportKey) 동봉 시 종목별 경로,
    //  없으면 기존 row-level 경로(하위호환) — 두 경로는 완전히 분기(서로 컬럼 침범 없음).
    var luSportKey = String(body.sport || '').trim();

    if (luSportKey) {
      // ── 종목별 경로: status/owner/contacts를 종목별관리[sportKey]에 병합 저장(있는 키만 갱신, 나머지 보존).
      //    기존 진행상태/관리담당/연락이력(row-level) 컬럼은 절대 건드리지 않음(비파괴 폴백 유지). 2026-07-08 시포·GM(축7).
      var _lsmCi = _findColExact_(luHdr, [LESSON_SPORT_MGMT_COL]);  // _lessonEnsureCols_가 이미 멱등 생성(위 luHdr 조회 시점)
      var _lsmMap = (_lsmCi >= 0) ? _lessonSportMgmtParse_(luSh.getRange(luRow, _lsmCi + 1).getValue()) : {};
      var _lsmEntry = _lsmMap[luSportKey] || { status: '', owner: '', contacts: [] };
      var _lsmPrevHistCount = Array.isArray(_lsmEntry.contacts) ? _lsmEntry.contacts.length : 0;
      if (body.status !== undefined && body.status !== null) _lsmEntry.status = String(body.status);
      if (body.owner  !== undefined && body.owner  !== null) _lsmEntry.owner  = String(body.owner);
      var _lsmNewHistArr = null;
      if (body.contacts !== undefined) {
        _lsmNewHistArr = _resParse_(body.contacts);
        _lsmEntry.contacts = _lsmNewHistArr;
      }
      _lsmMap[luSportKey] = _lsmEntry;
      try {
        if (_lsmCi >= 0) {
          var _lsmCell = luSh.getRange(luRow, _lsmCi + 1);
          _lsmCell.setNumberFormat('@');
          _lsmCell.setValue(_lessonSportMgmtStringify_(_lsmMap));
        }
      } catch (eLsm) { Logger.log('강습 종목별관리 저장 실패: ' + eLsm.message); }
      // 1차 컨택 알림(종목별, 축6·축7 일원화): 해당 종목 연락이력 0건 → ≥1건 전이 시 1회만.
      if (_lsmNewHistArr && _lsmPrevHistCount === 0 && _lsmNewHistArr.length >= 1) {
        try {
          var _lsmTypeLabel = (function(t){ t = String(t || ''); return (t === '유소년강습' || t === '유소년' || t === 'youth') ? '유소년 강습' : '성인 강습'; })(body.type);
          var _lsmNameCi = _findCol_(luHdr, ['이름', '성함']);
          var _lsmName = (String(body.name || (_lsmNameCi >= 0 ? luSh.getRange(luRow, _lsmNameCi + 1).getValue() : '')).trim()) || '-';
          var _lsmHistFirst = _lsmNewHistArr[0];
          var _lsmHistWhen = ((_lsmHistFirst.date || '') + ' ' + (_lsmHistFirst.time || '')).trim();
          var _lsmOwnerVal = String(_lsmEntry.owner || '').trim();
          var _lsmContactChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
          _notifyTelegram('📞 <b>1차 컨택 진행</b> — ' + _lsmName + ' (' + _lsmTypeLabel + ' · ' + _teamChip(luSportKey) + luSportKey + ')\n일시: ' + (_lsmHistWhen || '-') + '\n내용: ' + (_lsmHistFirst.note || '-') + (_lsmOwnerVal ? '\n담당: ' + _lsmOwnerVal : ''), _lsmContactChatId);
        } catch (e) {}
      }
    } else {
      // ── 기존 row-level 경로(하위호환) — body.sport 미전송 시 그대로 유지. 2026-06-26~2026-07-08 시포·GM.
      // 등록 전환 감지: 상태 변경 '전' 값 캡처(신규→SUC 실제 전환 1회만 알림 — 멤버십 member_inquiry_update와 동일 패턴·중복발화 차단). 시토 2026-06-29 GM.
      var _luStatusCi  = _findCol_(luHdr, ['진행상태', '진행현황', '진행상황', '진행 상황', '상태']);
      var _luOldStatus = (_luStatusCi >= 0) ? String(luSh.getRange(luRow, _luStatusCi + 1).getValue() || '').trim() : '';
      _luSet(['진행상태', '진행현황', '진행상황', '진행 상황', '상태'], body.status);  // '진행 상황'=GM flat O컬럼
      _luSet(['관리담당', '지정 강사'], body.owner);  // ★관리 담당 컬럼만. '지정 강사'=GM flat L컬럼(폼 원본 '접수담당자' 안 건드림)
      _luSet(['상담메모', '메모', '비고'], body.memo);
      _luSet(['상담예약', '상담 예약', '상담일정'], body.consult);
      _luSet(['방문상태', '방문'], body.visited);
      _luSet(['LOSS사유'], body.lossReason);       // 강습 LOSS 사유(문의 퍼널) — _lessonEnsureCols_가 칸 자동생성. 2026-07-18 시토(GM요청) 대행.
      _luSet(['LOSS사유메모'], body.lossReasonNote);
      _luSet(['등록종목'], body.regProgram);        // 강습 등록 종목(SUC 시 실제 등록한 종목) — 멤버십과 동일 체계, 칸 자동생성. 2026-07-20 시포(GM요청).
      // ── 연락이력(가변) — 축2/축4: body.contacts(JSON 문자열/배열) 수신 시 저장. 미전송이면 무영향(기존 필드만 갱신).
      //    상담메모는 위 _luSet으로 그대로 유지(비파괴·원복 안전) — 신·구 컬럼 병존. 2026-07-08 시포·GM.
      var _luHistPrevCount = 0;
      var _luHistNewArr = null;
      if (body.contacts !== undefined) {
        try {
          var _luHistCi = _findCol_(luHdr, [CONTACT_HIST_COL, 'Contact']);  // 연락이력 우선 → GM flat M컬럼 'Contact'(부분일치). JSON으로 라운드트립 기록
          var _luPrevHistArr = (_luHistCi >= 0) ? _resParse_(luSh.getRange(luRow, _luHistCi + 1).getValue()) : [];
          _luHistPrevCount = _luPrevHistArr.length;
          _luHistNewArr = _resParse_(body.contacts);
          if (_luHistCi >= 0) {
            var _luHistCell = luSh.getRange(luRow, _luHistCi + 1);
            _luHistCell.setNumberFormat('@');
            _luHistCell.setValue(_resStringify_(_luHistNewArr));
          }
        } catch (eHist) { Logger.log('강습 연락이력 저장 실패: ' + eHist.message); }
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
          _notifyTelegram('📞 <b>1차 컨택 진행</b> — ' + _luName + ' (' + _luTypeLabel + ' · ' + _teamChip(_luSport) + _luSport + ')\n일시: ' + (_luHistWhen || '-') + '\n내용: ' + (_luHistFirst.note || '-') + (_luOwnerVal ? '\n담당: ' + _luOwnerVal : ''), _luContactChatId);
        } catch (e) {}
      }
    }
    // 조회 캐시 무효화(축1) — type(성인강습/유소년강습) 두 scope(year/all) 모두 제거해 다음 조회 최신 반영(종목별·row-level 두 경로 공통). 2026-07-08 시토.
    try {
      var _luCache = CacheService.getScriptCache();
      var _luType = String(body.type || '');
      _cacheInvalidateJson_(_luCache, 'licache|' + _luType + '|year');
      _cacheInvalidateJson_(_luCache, 'licache|' + _luType + '|all');
    } catch (e) {}
    return _json({ ok: true, rowIndex: luRowRaw, message: '수정되었습니다.' });
  }

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
    // 2026-06-25 GM: 실제 회원 DB(유효회원 시트) 등록일자 기준 — 대시보드 '멤버십 등록건' 카드와 동일 소스.
    var rlFrom = String(body.from || '');  // YYYY-MM-DD
    var rlTo   = String(body.to   || '');
    var rlRows = [];
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
            regDate:  regDate
          });
        }
        rlRows.sort(function(a, b){ return a.regDate < b.regDate ? 1 : (a.regDate > b.regDate ? -1 : 0); }); // 최신 등록 먼저
      }
    } catch (eRl) {}
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

  // ─── 등록현황(CPO): 페이지에서 직접 등록 추가(문의 퍼널 안 거친 직접·법인 계약 등) — _regUpsert_ 멱등(전화키). 2026-06-29 시포 ───
  if (action === 'member_registered_add') {
    var raName  = String(body.name    || '').trim();
    var raPhone = String(body.phone   || '').trim();
    var raProg  = String(body.program || '').trim();
    var raDate  = String(body.regDate || '').trim() || _todayKR_();
    if (!raPhone) return _json({ ok: false, error: '전화번호 필수(중복 방지 키)' });
    _regUpsert_(raName, raPhone, raProg, raDate);  // 기존 전화면 갱신, 없으면 등록일 도장 추가
    // 등록 추가 알림 → '문의 알림' 방(전환 3경로와 정합). override 누락 시 개인 OWNER방으로 새던 버그 수정 — 직접·법인 등록건도 문의알림방에 통보. 2026-07-06 시토·GM.
    try {
      var _raRegChatId = PropertiesService.getScriptProperties().getProperty('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK;
      _notifyTelegram('➕ <b>등록 추가</b> — 직접/법인 등록\n· 이름: ' + (raName || '-') + '\n· 프로그램: ' + _teamChip(raProg) + (raProg || '-') + '\n· 등록일: ' + raDate, _raRegChatId);
    } catch (e) {}
    return _json({ ok: true, message: '등록 추가되었습니다.' });
  }

  // ─── 회원관리 페이지(CPO): 멤버십 회원 명단 ('유효회원' 시트, 읽기전용·전화 마스킹) ───
  //   scope=valid(기본): 잔여일>0 유효회원(2026-06-24 GM) / scope=ended: 종료·이탈(잔여일≤0 또는 LOSS·환불·양도LOSS)
  //   ★빈 헤더·쓰레기 날짜헤더(GMT/표준시) 컬럼 제외 + 회원명 없는 빈/이상 행 제외(전체 컬럼은 그대로 노출).
  if (action === 'member_active_list') {
    var aaScope = String(body.scope || 'valid'); if (aaScope !== 'ended' && aaScope !== 'corp') aaScope = 'valid';
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
    var aaSh = aaSs0.getSheetByName(MEMBER_SHEET);
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
    var aaFull = true;                                         // 2026-06-25 GM 전체공개 — 회원명도 평문(페이지 전체 PII 공개 정책 통일·전화도 평문)
    var aaNameKey = aiName >= 0 ? aaHdrRaw[aiName] : '';
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
          if (key === MEMBER_PHONE_COL) { var pp = v.replace(/[^0-9]/g, ''); if (pp.length === 11) v = pp.slice(0,3) + '-' + pp.slice(3,7) + '-' + pp.slice(7); else if (pp.length === 10) v = pp.slice(0,3) + '-' + pp.slice(3,6) + '-' + pp.slice(6); }
          obj[key] = v;
        }
        // 등록회차>=2 → 등록분류 '재등록' 표시(시트 미변경 · 표시 규칙) 2026-06-24 GM
        if (aiCls >= 0) {
          var _chaM = (aiCha >= 0 ? String(arow[aiCha] == null ? '' : arow[aiCha]) : '').match(/\d+/);
          if (_chaM && parseInt(_chaM[0], 10) >= 2) obj[aaHdrRaw[aiCls]] = '재등록';
        }
        if (!aaFull && aaNameKey) obj[aaNameKey] = _svMaskName_(obj[aaNameKey]);
        aaRows.push(obj);
      }
    }
    // 종료일자 최근순(내림차순) 기본 정렬 — 종료일 늦은 회원이 최상위 (2026-06-25 GM)
    var aiEnd = _aaIdx('종료일'); if (aiEnd < 0) aiEnd = _aaIdx('만료일'); if (aiEnd < 0) aiEnd = _aaIdx('이용종료'); if (aiEnd < 0) aiEnd = _aaIdx('만기일'); if (aiEnd < 0) aiEnd = _aaIdx('이탈일');
    if (aiEnd >= 0 && aaKeep[aiEnd]) {
      var aiEndKey = aaHdrRaw[aiEnd];
      aaRows.sort(function(a, b){ var av = String(a[aiEndKey] || ''); var bv = String(b[aiEndKey] || ''); return av < bv ? 1 : (av > bv ? -1 : 0); });
    }
    return _json({ ok: true, scope: aaScope, headers: aaHdrs, count: aaRows.length, data: aaRows });
  }

  // ─── 멤버십 회원관리: 셀 인라인 수정(유효회원 시트 write-back · 전화 컬럼 제외) 2026-06-24 GM ───
  if (action === 'member_active_update') {
    var auRow = parseInt(body.rowIndex, 10);
    if (!auRow || auRow < 2) return _json({ ok: false, error: 'rowIndex 필수(2 이상)' });
    // 다중 필드(fields 객체) 또는 단일(col/value). fields 우선 — 재등록상담 달력 모달=날짜·시간·내용 3칸 동시 저장. 2026-07-03 시포·GM.
    var auFields = (body.fields && typeof body.fields === 'object') ? body.fields : null;
    var auCol = String(body.col || '').trim();
    if (!auFields && !auCol) return _json({ ok: false, error: 'col 또는 fields 필수' });
    var auSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!auSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var auHdr = auSh.getRange(1, 1, 1, auSh.getLastColumn()).getValues()[0].map(function(v){ return String(v).trim(); });
    // ★행키 검증(비파괴·하위호환): keyPhone 동봉 시 대상 행 전화 대조 — rowIndex 밀림 오수정 방지. 미전송이면 폴백.
    if (body.keyPhone !== undefined && String(body.keyPhone) !== '') {
      var _auPhI = -1;
      for (var _ap = 0; _ap < auHdr.length; _ap++) { var _aph = auHdr[_ap].replace(/\s/g, ''); if (_aph.indexOf('휴대폰') >= 0 || _aph.indexOf('전화') >= 0 || _aph.indexOf('연락처') >= 0) { _auPhI = _ap; break; } }
      if (_auPhI >= 0 && auRow <= auSh.getLastRow()) {
        var _auRowPh = _normPhone_(auSh.getRange(auRow, _auPhI + 1).getValue());
        var _auKeyPh = _normPhone_(body.keyPhone);
        if (_auRowPh && _auKeyPh && _auRowPh !== _auKeyPh) {
          return _json({ ok: false, error: 'row-key-mismatch', detail: '행 검증 실패 — 목록을 새로고침 후 다시 시도하세요' });
        }
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
      if (ix < 0 && (w.indexOf('재등록상담') >= 0 || w.indexOf('재등록예약목록') >= 0 || w.indexOf('종료사유') >= 0)) ix = _miEnsureCol_(auSh, auHdr, String(colName).trim());
      return ix;
    }
    // 셀 쓰기 — 재등록상담 칸(날짜·시간·내용)은 텍스트 서식(@) 강제 후 기록. '09:00'·'2026-07-15'가 시간/날짜 값으로
    //   자동 변환(구글시트 LMT 오프셋으로 09:00→09:05 드리프트)되는 것을 차단 → 입력값 그대로 보존. 2026-07-03 시포·GM.
    function _auWriteCell(ix, colName, val) {
      var cell = auSh.getRange(auRow, ix + 1);
      var _cn = String(colName).replace(/\s/g, '');
      if (_cn.indexOf('재등록상담') >= 0 || _cn.indexOf('재등록예약목록') >= 0) cell.setNumberFormat('@');
      cell.setValue(val == null ? '' : String(val));
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
      return _json({ ok: true, rowIndex: auRow, cols: _auWrote });
    }
    if (auCol.replace(/\s/g, '').indexOf('휴대폰') >= 0) return _json({ ok: false, error: '전화번호는 시트에서 직접 수정해주세요' });
    var auIdx = _auFindCol(auCol);
    if (auIdx < 0) return _json({ ok: false, error: '컬럼 미발견: ' + auCol });
    _auWriteCell(auIdx, auCol, body.value);
    return _json({ ok: true, rowIndex: auRow, col: auCol });
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
    mosSh.getRange(mosRow, mosFieldIdx + 1).setValue(mosValue);
    return _json({ ok: true, phone: mosPhone, field: mosField, value: mosValue, rowIndex: mosRow });
  }

  // ─── [일회성 · GM 직접 지시 · 실행 후 제거] 담당자 일괄 변경(유효회원 시트) — 2026-07-20 시포 ───
  //   대상 4건 고정 하드코딩(field/oldValue/newValue를 호출부 파라미터로 받지 않음 — 임의값 주입으로
  //   다른 회원·다른 칸이 덮어써지는 경로 원천 차단. 오늘 INC-020 사고 재발방지 원칙 적용).
  //   ① 스쿼시 담당자: 최수진→이상훈(178건 실측) ② 스쿼시 담당자: 이우성→이상훈(5건 실측)
  //   ③ 골프 담당자: 김명선→최현준(2건 실측) ④ 골프 담당자: 정시우→최현준(24건 실측)
  //   ※ GM 표현은 "OO 팀장"이었으나 시트 기존 표기(이름만)를 그대로 따름 — 직함 병기 시 기존 값과
  //     표기가 갈려 집계가 깨짐(GM 확인).
  //   안전장치: 헤더 정확일치(indexOf 부분일치 금지) · 해당 칸 현재값이 정확히 구담당자인 행만 ·
  //            deleteRow/insertRows/sort 호출 전무(단일셀 setValue만) · dryRun 기본값 true(명시적
  //            dryRun:false 만 실제 실행) · 실행 직전 셀 재조회로 레이스 방지 · 쓰기 전후 총행수 비교 반환.
  //   _SURVEY_PUBLIC_ACTIONS 화이트리스트에 넣지 않음(add_utm_field와 동일 원칙 — 폼/데이터 변형 액션).
  if (action === 'bulk_owner_reassign') {
    var BOR_PAIRS = [
      { key: 'squash1', field: '스쿼시 담당자', oldValue: '최수진', newValue: '이상훈' },
      { key: 'squash2', field: '스쿼시 담당자', oldValue: '이우성', newValue: '이상훈' },
      { key: 'golf1',   field: '골프 담당자',   oldValue: '김명선', newValue: '최현준' },
      { key: 'golf2',   field: '골프 담당자',   oldValue: '정시우', newValue: '최현준' }
    ];
    var borDry = (body.dryRun !== false);          // 기본 dry-run — 명시적 false 만 실제 실행
    var borOnly = String(body.pair || '').trim();  // 'squash1'|'squash2'|'golf1'|'golf2'|'' (전부)
    var borSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
    if (!borSh) return _json({ ok: false, error: '유효회원 시트 없음' });
    var borLastBefore = borSh.getLastRow();
    var borCols = borSh.getLastColumn();
    if (borLastBefore < 2) return _json({ ok: false, error: 'no rows' });
    var borHdr = borSh.getRange(1, 1, 1, borCols).getValues()[0].map(function(v){ return String(v).trim(); });
    var borResults = [];
    for (var bp = 0; bp < BOR_PAIRS.length; bp++) {
      var borP = BOR_PAIRS[bp];
      if (borOnly && borOnly !== borP.key) continue;
      var bFieldIdx = borHdr.indexOf(borP.field);   // 정확일치만
      if (bFieldIdx < 0) { borResults.push({ pair: borP.key, error: '컬럼 미발견: ' + borP.field }); continue; }
      var bData = borSh.getRange(2, bFieldIdx + 1, borLastBefore - 1, 1).getValues();
      var bMatchRows = [];
      for (var bi = 0; bi < bData.length; bi++) {
        var bCur = String(bData[bi][0] == null ? '' : bData[bi][0]).trim();
        if (bCur === borP.oldValue) bMatchRows.push(bi + 2);
      }
      if (borDry) {
        borResults.push({ pair: borP.key, field: borP.field, oldValue: borP.oldValue, newValue: borP.newValue, dryRun: true, matchCount: bMatchRows.length });
        continue;
      }
      var bWritten = 0;
      for (var bj = 0; bj < bMatchRows.length; bj++) {
        var bRow = bMatchRows[bj];
        var bCell = borSh.getRange(bRow, bFieldIdx + 1);
        var bNow = String(bCell.getValue() == null ? '' : bCell.getValue()).trim();
        if (bNow === borP.oldValue) { bCell.setValue(borP.newValue); bWritten++; }  // 쓰기 직전 재확인(레이스 방지)
      }
      borResults.push({ pair: borP.key, field: borP.field, oldValue: borP.oldValue, newValue: borP.newValue, dryRun: false, matchCount: bMatchRows.length, written: bWritten });
    }
    var borLastAfter = borSh.getLastRow();
    return _json({ ok: true, dryRun: borDry, results: borResults, rowsBefore: borLastBefore, rowsAfter: borLastAfter, rowCountUnchanged: (borLastBefore === borLastAfter) });
  }

  // ─── CPO 오늘 현황(PII 미노출 집계): 오늘/이번달 문의·등록 건수 2026-06-24 GM ───
  if (action === 'cpo_today_stats') {
    var ctCache = CacheService.getScriptCache();
    var ctCached = ctCache.get('cpo_today_stats_v4');
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
        if (ciTs >= 0) {
          var ciData = ciSh.getRange(2, 1, ciSh.getLastRow() - 1, ciH.length).getValues();
          for (var ci = 0; ci < ciData.length; ci++) {
            if (ciNm >= 0 && !String(ciData[ci][ciNm] || '').trim() && !ciData[ci][ciTs]) continue;
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
    try {
      var crSh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
      if (crSh && crSh.getLastRow() >= 2) {
        var crCols = crSh.getLastColumn();
        var crHdr = crSh.getRange(1, 1, 1, crCols).getValues()[0].map(function(v){ return String(v).trim(); });
        function _crIdx(want){ var w = String(want).replace(/\s/g, ''); for (var i = 0; i < crHdr.length; i++){ if (crHdr[i].replace(/\s/g, '').indexOf(w) >= 0) return i; } return -1; }
        var crRegI  = _crIdx('등록일자');
        var crNmI   = _crIdx('회원명');
        var crRemI  = _crIdx('잔여일');
        var crReI   = _crIdx('재등록분류');
        var crLossI = _crIdx('이탈일'); if (crLossI < 0) crLossI = _crIdx('해지일'); if (crLossI < 0) crLossI = _crIdx('종료일');
        ctLossDated = (crLossI >= 0);
        var _CR_LOSS = { 'LOSS':1, '환불':1, '양도LOSS':1 };
        var crAll = crSh.getRange(2, 1, crSh.getLastRow() - 1, crCols).getValues();
        for (var cr = 0; cr < crAll.length; cr++) {
          var crow = crAll[cr];
          // 등록 집계(등록일자 — 금일/금월 신규)
          if (crRegI >= 0) {
            var cv = crow[crRegI];
            var crD = (cv instanceof Date && !isNaN(cv.getTime())) ? Utilities.formatDate(cv, ctTz, 'yyyy-MM-dd') : _miToISO_(cv);
            if (crD === ctToday) ctTR++;
            if (crD && crD.slice(0, 7) === ctMonth) ctMR++;
          }
          // 회원 현황(회원명 있는 행만): 유효 = 잔여일>0 & 이탈표시 없음
          var crNm = crNmI >= 0 ? String(crow[crNmI] == null ? '' : crow[crNmI]).trim() : '';
          if (!crNm) continue;
          var crRemRaw = crRemI >= 0 ? String(crow[crRemI] == null ? '' : crow[crRemI]).replace(/[^0-9\-]/g, '') : '';
          var crRem = (crRemRaw === '' || crRemRaw === '-') ? NaN : parseInt(crRemRaw, 10);
          var crReV = crReI >= 0 ? String(crow[crReI] == null ? '' : crow[crReI]).trim() : '';
          var crValid = !isNaN(crRem) && crRem > 0 && !_CR_LOSS[crReV];
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
    // 법인회원 수(별도 시트 gid 1612064257 '법인현황' — 회원명 있는 행). 2026-06-29 시포.
    var ctCorp = 0;
    try {
      var ctCorpSs = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID), ctCorpSh = null, ctCorpShs = ctCorpSs.getSheets();
      for (var cci = 0; cci < ctCorpShs.length; cci++) { if (ctCorpShs[cci].getSheetId() === 1612064257) { ctCorpSh = ctCorpShs[cci]; break; } }
      if (!ctCorpSh) ctCorpSh = ctCorpSs.getSheetByName('법인현황');
      if (ctCorpSh && ctCorpSh.getLastRow() >= 2) {
        var ctCorpHdr = ctCorpSh.getRange(1, 1, 1, ctCorpSh.getLastColumn()).getValues()[0], ctCorpNmI = 0;
        for (var cch = 0; cch < ctCorpHdr.length; cch++) { if (String(ctCorpHdr[cch]).replace(/\s/g, '').indexOf('회원명') >= 0) { ctCorpNmI = cch; break; } }
        var ctCorpData = ctCorpSh.getRange(2, ctCorpNmI + 1, ctCorpSh.getLastRow() - 1, 1).getValues();
        for (var ccd = 0; ccd < ctCorpData.length; ccd++) { if (String(ctCorpData[ccd][0] == null ? '' : ctCorpData[ccd][0]).trim()) ctCorp++; }
      }
    } catch (eCorp) {}
    var ctResult = { ok: true, date: ctToday, todayInquiry: ctTI, monthInquiry: ctMI, todayReg: ctTR, monthReg: ctMR, memberActive: ctActive, memberCorp: ctCorp, memberEnded: ctEnded, todayLoss: ctLoss, monthLoss: ctMonthLoss, lossDated: ctLossDated };
    try { ctCache.put('cpo_today_stats_v4', JSON.stringify(ctResult), 60); } catch (eCc) {}
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
        // LOSS일자 컬럼(cpo_today_stats 와 동일 우선순위: 이탈일→해지일→종료일)
        var czLossI = _czIdx('이탈일'); if (czLossI < 0) czLossI = _czIdx('해지일'); if (czLossI < 0) czLossI = _czIdx('종료일');
        var _CZ_LOSS = { 'LOSS':1, '환불':1, '양도LOSS':1 };
        var czAll = czSh.getRange(2, 1, czSh.getLastRow() - 1, czCols).getValues();
        for (var czr = 0; czr < czAll.length; czr++) {
          var czrow = czAll[czr];
          var czName = czNm >= 0 ? String(czrow[czNm] == null ? '' : czrow[czNm]).trim() : '';
          if (!czName) continue;
          var czRemRaw = czRem >= 0 ? String(czrow[czRem] == null ? '' : czrow[czRem]).replace(/[^0-9\-]/g, '') : '';
          var czRemN = (czRemRaw === '' || czRemRaw === '-') ? NaN : parseInt(czRemRaw, 10);
          var czReV = czRe >= 0 ? String(czrow[czRe] == null ? '' : czrow[czRe]).trim() : '';
          var czIsLoss = !!_CZ_LOSS[czReV] || (!isNaN(czRemN) && czRemN <= 0);
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
          if (!isNaN(czRemN) && czRemN > 0 && czRemN <= 30) {
            czRenew.push({ name: czName, rem: czRemN, program: czPg >= 0 ? String(czrow[czPg] || '').trim() : '' });
          }
        }
      }
    } catch (eCz) {}
    czRenew.sort(function(a, b){ return a.rem - b.rem; });
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
    var fcCacheKey = 'fc_v3_' + (fcPrecise ? 'reg_' : 'acc_') + fcFrom + '_' + fcTo;  // v3: 전환에 강습 등록 합산 반영(2026-07-03 시모) · 분자모드 분리(2026-07-04 시포) — 구캐시 무효화
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

    // ② 문의접수 시트 집계
    var inqSh   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var inqLast = inqSh.getLastRow();
    var totalInq = 0, totalConv = 0, totalConvMemberOnly = 0;  // memberOnly=구버전(멤버십만) 비교용 — 투명성 유지
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

        var fcConv = _fcConverted_(phone);
        if (fcConv.memberOnly) totalConvMemberOnly++;   // 구버전(멤버십만) 비교용
        if (fcConv.any) {
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
      var fcConv2 = _fcConverted_(phone);
      if (fcConv2.memberOnly) totalConvMemberOnly++;   // 구버전(멤버십만) 비교용
      if (fcConv2.any) { totalConv++; byChannel[channel].converted++; }
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

    // ② 문의접수 시트 — 전환된 행만 명단화(비전환 문의는 상세 미노출, 이미 채널 문의수 합계로 별도 표시됨)
    var fdInqSh   = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
    var fdInqLast = fdInqSh.getLastRow();
    if (fdInqLast >= 2) {
      var fdInqData    = fdInqSh.getRange(2, 1, fdInqLast - 1, INQUIRY_HEADERS.length).getValues();
      var fdIdxName    = INQUIRY_HEADERS.indexOf('이름');
      var fdIdxPhone   = INQUIRY_HEADERS.indexOf('연락처');
      var fdIdxChannel = INQUIRY_HEADERS.indexOf('유입채널');
      var fdIdxDate    = INQUIRY_HEADERS.indexOf('시각');
      var fdIdxType    = INQUIRY_HEADERS.indexOf('문의유형');
      fdInqData.forEach(function(row) {
        if (!_fdInPeriod_(row[fdIdxDate])) return;   // 기간 필터(미지정=전체 누적)
        var phone = normalizePhone_(row[fdIdxPhone]);
        var conv  = _fdConverted_(phone);
        if (!conv.any) return;
        var channel = _canonicalChannel_(row[fdIdxChannel]);
        var regDate = _fdRegDate_(phone);
        _fdPush_(channel, {
          name:             fdIdxName >= 0 ? (String(row[fdIdxName] || '').trim() || '확인불가') : '확인불가',
          phone4:           _fdPhone4_(phone),
          type:             _fdTypeLabel_(phone, fdIdxType >= 0 ? String(row[fdIdxType] || '') : ''),
          inquiryDate:      _miToISO_(row[fdIdxDate]) || '확인불가',
          regDate:          regDate || '확인불가',
          regDateConfirmed: !!regDate,
          matchBasis:       _fdBasisLabel_(conv)
        });
      });
    }
    // ②-b 구글폼 응답 문의 합류 — 이 소스는 이름 필드를 수집하지 않음(원본 폼 구조 한계) → 정직하게 '확인불가' 표기.
    _collectFormInquiries_().forEach(function(f) {
      if (!_fdInPeriod_(f.시각)) return;   // 기간 필터(미지정=전체 누적)
      var phone = normalizePhone_(f.연락처);
      var conv  = _fdConverted_(phone);
      if (!conv.any) return;
      var channel = _canonicalChannel_(f.유입채널);
      var regDate = _fdRegDate_(phone);
      _fdPush_(channel, {
        name:             '확인불가(이름 미수집 폼)',
        phone4:           _fdPhone4_(phone),
        type:             _fdTypeLabel_(phone, f.문의유형 || ''),
        inquiryDate:      _miToISO_(f.시각) || '확인불가',
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
        if (iMemo >= 0 && String(r[iMemo] || '').indexOf(WEB_INTAKE_TAG) >= 0) return;         // [웹접수] 미러 제외
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

    // 멤버십 ①-a: INQUIRY_SHEET(문의접수 — 현재 0행이나 부활 대비 유지)
    try {
      var sfInqSh = _getSheet(INQUIRY_SHEET, INQUIRY_HEADERS);
      var sfInqLast = sfInqSh.getLastRow();
      if (sfInqLast >= 2) _sfProc_(INQUIRY_HEADERS, sfInqSh.getRange(2, 1, sfInqLast - 1, INQUIRY_HEADERS.length).getValues(), MEM_KEYS, memT, memM);
    } catch (e) { /* 무중단 */ }

    // ①-b: FORM_SHEETS → gid로 멤버십/강습 분기
    FORM_SHEETS.forEach(function(cfg) {
      try {
        var sh = _sheetByGid_(cfg.ssId, cfg.gid); if (!sh) return;
        var last = sh.getLastRow(), lc = sh.getLastColumn(); if (last < 2 || lc < 1) return;
        var hd = sh.getRange(1, 1, 1, lc).getValues()[0];
        var rows = sh.getRange(2, 1, last - 1, lc).getValues();
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
      var ledgerRoster = null;  // 팀시트 없는 종목(발레·바레): 등록원장 기반. 지연 로드(있을 때만 1회).
      data[grp] = LESSON_DISPLAY[grp].map(function(item) {
        var reg = null, inq = null, src = null, sheetUrl = null;
        if (item.sheet) {
          usedSheets[item.sheet] = true;
          var rec  = byName[item.sheet];
          var recI = byNameInq[item.sheet];
          if (rec)  { reg = rec.registered; src = rec.statusHeader; }  // null이면 그대로(데이터 미연결)
          if (recI) { inq = recI.inquiries; }
          sheetUrl = _lessonSheetUrl(item.sheet);
        } else if (item.ledger) {
          // 발레·바레(external 해제): 등록원장(강습 등록현황) SUC 카운트로 집계. roster 없으면 0(정직·날조 아님).
          if (ledgerRoster === null) ledgerRoster = _ledgerRosterByType_(grp);
          reg = (ledgerRoster[item.명] || []).length;
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
      basis: '종목별 문의 = 팀시트 행을 타임스탬프 기준 기간 집계 · 등록 = 팀시트 상태열 수강등록(SUC/등록) 누적 · 팀시트 없는 종목(발레·바레)=등록원장(강습 등록현황) SUC 카운트 기반',
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

// ─── [일회성 · 편집기 실행 전용] 유효회원 시트 A1 헤더 오타 수리 'ㄹ'→'담당자' ───
// 2026-07-20 시포 — GM 결재 완료건. doGet/doPost 액션에 미배선(공개 호출 불가) — 편집기에서 1회 실행 후 삭제할 것.
// 안전장치: A1이 정확히 'ㄹ'일 때만 쓴다(이미 바뀌었거나 다른 값이면 아무것도 안 하고 로그만 남김) — 오작동으로 다른 값 덮어쓰기 방지.
function fixMemberSheetHeaderA1_() {
  var sh = SpreadsheetApp.openById(MEMBER_SPREADSHEET_ID).getSheetByName(MEMBER_SHEET);
  if (!sh) { Logger.log('유효회원 시트 없음'); return; }
  var cell = sh.getRange(1, 1);
  var cur = String(cell.getValue()).trim();
  if (cur !== 'ㄹ') { Logger.log('A1 현재값이 ㄹ 아님(값="' + cur + '") — 미변경(안전가드)'); return; }
  cell.setValue('담당자');
  Logger.log('A1: "ㄹ" → "담당자" 변경 완료');
}
