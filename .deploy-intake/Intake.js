/** 웰페리온 고객 접수 배관 (intake-api) — 2026-08-06 시토 분리 신설
 *
 *  왜 떼어냈나:
 *    문의 접수(intake_submit)가 매출·강습·회원관리·마케팅 집계까지 다 얹힌
 *    한 덩어리 GAS(.deploy-funnel-v2/Survey.js, 770,127바이트·11,236줄)를
 *    거쳤다. 실측(2026-08-06, 존재하지 않는 action 대조): 왕복 중앙값의 88%가
 *    액션과 무관한 고정비용(컨테이너가 매번 그 덩치를 통째로 로드) — 배240.
 *    전례: 2026-08-04 매출 배관을 sales-api 로 분리(커밋 c5ac263b2). 같은 수법.
 *
 *  담당 액션: intake_submit 딱 1개(+ping 진단) — 고객 문의 접수 저장(멤버십·
 *    성인/유소년/여름특강 강습·공간렌트·비즈니스 제휴 6종 category 분기).
 *    함수 본문은 Survey.js 원문 그대로 이관(동작 동일성 보장) — scripts/
 *    _extract_intake_closure.py 로 실제 참조 식별자만 자동 폐포 추출.
 *
 *  ⚠ 회원 저장(member_owner_save 등)·조회·집계 액션은 여기 없다 — GM 결재
 *    범위가 "접수만"이라 그쪽은 계속 Survey.js(funnel-v2)가 담당한다.
 *  ⚠ 원본(Survey.js)에서 코드를 지우지 않았다 — 두 경로가 당분간 함께 산다.
 *    화면 전환은 별도 결재 후(이번 배포는 신설·실측까지만).
 *  ⚠ BOT_TOKEN 캐치업 필요: 이 프로젝트 ScriptProperties 에 BOT_TOKEN 이
 *    없으면 텔레그램 문의알림만 무음 실패한다(접수 자체는 fail-soft 로 정상
 *    저장됨 — _notifyTelegram 참조). 화면 전환 전 GM/시토가 Survey.js 와
 *    같은 BOT_TOKEN 값을 이 프로젝트 속성에도 설정해야 한다.
 */

function _sheetByGid_(ssId, gid) {
  var sheets = SpreadsheetApp.openById(ssId).getSheets();
  for (var i = 0; i < sheets.length; i++) { if (sheets[i].getSheetId() === gid) return sheets[i]; }
  return null;
}

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

function _findColExact_(headers, keys) {
  for (var k = 0; k < keys.length; k++) {
    for (var i = 0; i < headers.length; i++) {
      if (String(headers[i] || '').trim() === keys[k]) return i;
    }
  }
  return -1;
}

function _normPhone_(v) { return String(v == null ? '' : v).replace(/[^0-9]/g, ''); }

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

function _isLessonReg_(v) {
  var s = String(v == null ? '' : v).trim();
  if (s.length > 15) return false;  // 자유메모 배제(노이즈)
  if (/미등록|등록취소|취소|환불|대기|보류|불가|loss|가망|컨택/i.test(s)) return false;
  return /^(등록|등록완료|suc|단기\s*suc|성공)$/i.test(s);  // 구조화 성공값만 (단기SUC 포함)
}

function _isTestInquiryName_(name) {
  var s = String(name || '');
  for (var i = 0; i < _INQ_TEST_NAME_MARKERS_.length; i++) {
    if (s.indexOf(_INQ_TEST_NAME_MARKERS_[i]) >= 0) return true;
  }
  return false;
}

function _inquiryNotifyChatId_(name, normalChatId) {
  return _isTestInquiryName_(name) ? TELEGRAM_REPORT_CHAT_ID : normalChatId;
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function _prop(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '';
}

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

function _dateOnlyStrip_(v) {
  var s = String(v == null ? '' : v).trim();
  var m = s.match(/^\d{4}-\d{2}-\d{2}/);
  return m ? m[0] : s;
}

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

function _ctBySplit_(note) {
  var s = String(note == null ? '' : note);
  var m = s.match(CONTACT_BY_RE);
  if (!m) return { note: s, by: '' };
  return { note: s.replace(CONTACT_BY_RE, '').trim(), by: m[1].trim() };
}

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

function _memberCacheBump_() {
  try {
    var p = PropertiesService.getScriptProperties();
    p.setProperty('MEMBER_CACHE_GEN', String((parseInt(p.getProperty('MEMBER_CACHE_GEN'), 10) || 0) + 1));
  } catch (e) { /* 캐시 무효화 실패가 저장 자체를 막지 않게 한다 */ }
}

function _lessonSheet_(gid) {
  var want = gid || LESSON_GID;
  var sheets = SpreadsheetApp.openById(LESSON_SS_ID).getSheets();
  for (var i = 0; i < sheets.length; i++) { if (sheets[i].getSheetId() === want) return sheets[i]; }
  return null;
}

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
      // 출처 물리 시트 gid + 기재 언어 — 영문 탭 병합 표시·저장 라우팅용(row.gid 그대로 되돌려 보내면 정확한 탭에 기록). 2026-07-09 시포·GM.
      gid: gid,
      lang: iLang >= 0 ? String(row[iLang] || '').trim() : '',
      // 지문키(rowKey, §4 R1) — 정규화 타임스탬프+정규화 전화(raw 셀 값). 2026-07-22 시포(오지목 근본수리).
      rowKey: (function(){ var _t = _normTsKey_(iTs >= 0 ? row[iTs] : ''), _p = _normPhone_(iPhone >= 0 ? row[iPhone] : ''); return (_t && _p) ? (_t + '|' + _p) : ''; })()
    });
  }
  return out;
}

function _intakeToken_() { return _accessProp_('INTAKE_SUBMIT_TOKEN') || INTAKE_SUBMIT_TOKEN; }

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
      rowKey: (function(){ var _t = _normTsKey_(iTs >= 0 ? row[iTs] : ''), _p = _normPhone_(iPhone >= 0 ? row[iPhone] : ''); return (_t && _p) ? (_t + '|' + _p) : ''; })()
    });
  }
  return out;
}

const MEMBER_SPREADSHEET_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';

const MEMBER_SHEET = '유효회원';

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

var CANONICAL_CHANNELS = ['네이버 검색·플레이스', '네이버 블로그', '동부이촌동 커뮤니티', '인스타그램',
                          '카카오톡', '당근마켓', '소개·지인', '기존·과거 회원', '법인·단체',
                          '오프라인', '유선전화', '기타·미상'];

var WEB_INTAKE_TAG = '[웹접수]';

var _INQ_TEST_NAME_MARKERS_ = ['[UTF8검증]', '[진단209검증', '자동QA', '[자동QA]'];

var TELEGRAM_REPORT_CHAT_ID = '8254867551';

var _INQUIRY_CHAT_ID_FALLBACK = '-5516675010';

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
  member_calendar:        true,
  member_inquiry_update:  true,  // 2026-06-22 GM '전체 공개' — 실명·전화 포함 수정
  member_inquiry_add:     true,  // 2026-06-23 전화·직접 문의 수기 추가
  member_inquiry_delete:  true,  // 행 삭제
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
  funnel_conversion_detail:   true   // 2026-07-20 GM 지시(배834) — M1 마케팅 대시보드 채널별 가입전환 상세 명단. PII 노출(이름·연락처뒷4자리) — member_inquiry_list 등과 동일 정책(전체공개, 읽기전용·원본시트 미변경). 연락처는 서버에서 뒷4자리로 절단 후 반환(전체번호 미노출).
};

var _MI_SS_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';

var _MI_SHEET = '26년 신규문의';

var CONTACT_HIST_COL = '연락이력';

var CONTACT_BY_RE = /\s*\(컨택:([^()]*)\)\s*$/;

var _REG_SHEET = '26년 등록현황';

var _REG_HEADER = ['이름','전화','프로그램','등록일','1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];

var LESSON_SS_ID = '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw';

var LESSON_GID = 111889422;

var LESSON_GID_ADULT_EN = 311319200;

var LESSON_GID_YOUTH_EN = 931249179;

var _ROW_OFFSET_EN_ = 1000000;

var LESSON_SPORT_MGMT_COL = '종목별관리';

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

var INTAKE_SUBMIT_TOKEN = 'wlp_intake_9f4c1b7e2a63';

var LESSON_INTAKE_SHEET_NAME = '강습 신규문의';

var _ROW_OFFSET_INTAKE_ = 2000000;

var LESSON_INTAKE_HEADERS = ['타임스탬프','성함','연락처','자녀 나이','유형','강습 종목','희망 레슨 시간','문의 경로','문의 사항','개인정보 수집·이용 동의','접수ID','진행 상황','지정 강사','Contact','비고'];

var RENTAL_INTAKE_SHEET_NAME = '공간렌트 문의';

var RENTAL_INTAKE_HEADERS = ['타임스탬프','성함','연락처','대관 공간','용도','희망일','예상 인원','문의 사항','개인정보 수집·이용 동의','접수ID','진행 상황','비고'];

var BUSINESS_INTAKE_SHEET_NAME = '비즈니스 문의';

var BUSINESS_INTAKE_HEADERS = ['타임스탬프','성함','회사명','담당자','연락처','제휴 유형','소개자료 링크','제안 내용','개인정보 수집·이용 동의','접수ID','진행 상황','비고'];


function _processAction(body) {
  const action = body.action || '';
  if (action === 'ping') {
    return _json({
      ok: true, service: 'intake-api',
      at: Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss'),
      // 알림 토큰이 들어 있는지만 길이로 알린다(값은 절대 안 내보낸다). 0 이면 접수는 되는데
      // 텔레그램 알림만 조용히 안 가는 상태다 — 그 침묵을 밖에서 볼 수 있게 하는 창 하나.
      botTokenLen: _prop('BOT_TOKEN').length
    });
  }
  /* set_bot_token_once (1회용 쓰기 문) 는 값을 넣은 뒤 지웠다 — 2026-08-06 배240.
     남겨 두면 쓰이지 않는 쓰기 통로가 그대로 열려 있게 된다(약속 L21 "꺼둔 것은 남기지 않는다").
     대신 ping 이 토큰 설정 여부를 길이로만 알려 준다(값은 안 내보낸다) — 토큰이 빠지면
     접수는 되는데 알림만 조용히 안 가는 부류라, 사람이 눈치채려면 볼 자리가 있어야 한다. */

  // nocache 플래그는 원본 계약 유지(미사용이라도 body 그대로 통과) — intake_submit 은 캐시 우회 분기 없음.
  if (!_checkSurveyAccess_(action, body.key)) {
    return _json({ ok: false, error: 'unauthorized' });
  }

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
        _imSet(['접수 담당자', '담당'], '웹 자동접수');
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
      } else {
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
      var _iCatLabelMap = { membership: '멤버십', adult: '성인 강습', youth: '유소년 강습', summer: '여름 특강', rental: '공간 렌트', business: '비즈니스 제휴' };
      var _iCatLabel = _iCatLabelMap[_iCat] || _iCat;
      var _iDisplayName = (_iCat === 'business') ? (_iCompany + ' / ' + _iContactName) : _iName;
      var _iChat = _inquiryNotifyChatId_(_iDisplayName, _prop('TELEGRAM_INQUIRY_CHAT_ID') || _INQUIRY_CHAT_ID_FALLBACK); // 배209 재발방지 — 테스트 태그는 업무보고방으로
      var _iExtra = '';
      if (_iCat === 'summer') _iExtra = (_iWish ? ('\n희망시간: ' + _iWish) : '') + (_iWishMonth ? ('\n희망월: ' + _iWishMonth) : '') + (_iTarget ? ('\n대상: ' + _iTarget) : '');
      if (_iCat === 'rental') _iExtra = (_iSpace ? ('\n공간: ' + _iSpace) : '') + (_iPurpose ? ('\n용도: ' + _iPurpose) : '');
      if (_iCat === 'business') _iExtra = (_iPartnerType ? ('\n제휴유형: ' + _iPartnerType) : '');
      _notifyTelegram((_isTestInquiryName_(_iDisplayName) ? '🧪 <b>[테스트 문의 — 업무보고방으로 자동전환]</b>\n' : '🔔 <b>[웹 문의 접수]</b> (자체폼)\n') + '유형: ' + _iCatLabel + '\n이름: ' + _iDisplayName + '\n연락처: ' + _fmtPhone_(_iPhone)
        + (_iProgram ? ('\n관심: ' + _iProgram) : '') + _iExtra + (_iMessage ? ('\n내용: ' + _iMessage.substring(0, 100)) : ''), _iChat);
    } catch (e) {}
    return _json({ ok: true, id: _iId, submissionId: _sid, message: '문의가 접수되었습니다.' });
  }

  return _json({ ok: false, error: '알 수 없는 action: ' + action });
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

/** 최초 1회 권한 승인용 — Apps Script 편집기에서 이 함수를 실행하면
 *  이 프로젝트가 쓰는 권한(스프레드시트·PropertiesService·외부 URL 호출)을
 *  구글이 한 번 물어본다. 승인해야 웹앱(/exec)이 외부에 응답한다(전례: sales-api
 *  authorize(), 커밋 c5ac263b2). 이후로는 다시 실행할 필요 없다. */
function authorize() {
  var n = 0;
  try { n = SpreadsheetApp.openById(_MI_SS_ID).getName().length; } catch (e) {}
  Logger.log('권한 승인 완료 (확인값 ' + n + ') — 이제 웹앱이 응답합니다.');
  return 'OK';
}
