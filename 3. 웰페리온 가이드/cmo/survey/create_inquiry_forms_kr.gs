// 웰페리온 신규 문의 구글폼 생성기 (한글) v1.0 — 공간 렌트 · 비즈니스 파트너
// 실행: GAS 에디터에서 createInquiryFormsKR() 함수를 1회 실행(cao@wellperion.com 계정).
// 결과: 폼 2개 + 응답 스프레드시트 1개 생성 → 실행 로그(보기 > 로그)에
//        ssId · 응답탭 gid · 폼 공개/편집 URL · FORM_SHEETS 교체값이 출력됨.
// 명세 원본: cmo/survey/문의_신규유형_폼설계_260612.md (§1·§2·§3)
// ⚠️ 생성 후 폼 UI에서 "조직으로 제한" 해제 확인 필수(비로그인 외부 제출 — §5-2, 시크릿창 테스트).

// ─── PIPA 개인정보 동의문 (목적만 치환) ───
function _pipa_(purpose) {
  return '개인정보 보호법에 따라 주식회사 웰페리온은 아래와 같이 개인정보를 수집·이용합니다.\n\n'
    + '수집 목적: ' + purpose + '\n'
    + '수집 항목: 성함(단체·회사명), 연락처, 이메일, 문의·제안 내용\n'
    + '보유 기간: 수집일로부터 1년 또는 목적 달성 시까지(둘 중 빠른 시점)\n'
    + '제3자 제공: 별도 동의 없이 제공하지 않음(법령상 요구 시 예외)\n\n'
    + '동의를 거부하실 수 있으나, 거부 시 문의 응대가 제한될 수 있습니다.';
}
var PIPA_CONSENT_CHOICE = '위 개인정보 수집·이용에 동의합니다.';

// ─── 응답 시트 새 탭 식별 헬퍼 ───
function _sheetIdSet_(ss) {
  var s = ss.getSheets(), set = {};
  for (var i = 0; i < s.length; i++) set[s[i].getSheetId()] = true;
  return set;
}
function _newSheetInfo_(ss, before) {
  SpreadsheetApp.flush();
  var s = ss.getSheets();
  for (var i = 0; i < s.length; i++) {
    var id = s[i].getSheetId();
    if (!before[id]) return { gid: id, name: s[i].getName() };
  }
  return { gid: '?', name: '(미확인)' };
}

// ═══════════════════════════════════════════════════════════
//  1. 공간 렌트 문의 폼
// ═══════════════════════════════════════════════════════════
function _buildSpaceRentalForm_() {
  var form = FormApp.create('웰페리온 스포츠클럽 — 공간 렌트 문의');
  form.setDescription(
    '웰페리온의 프리미엄 공간을 행사·촬영·모임 목적으로 대관하실 수 있습니다. '
    + '아래 정보를 남겨주시면 담당자가 가용 일정과 맞춤 견적을 안내해 드립니다. (사전 예약제 운영)\n\n'
    + '이용 요금은 공간 규모·기간·구성에 따라 맞춤 견적으로 안내드립니다. 문의 접수 후 담당자가 상세 견적을 드립니다.'
  );
  form.setCollectEmail(false);
  form.setRequireLogin(false);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage('문의가 접수되었습니다. 담당자가 영업일 기준 1일 이내 연락드리겠습니다.');

  form.addTextItem().setTitle('성함 / 단체명').setRequired(true);
  form.addTextItem().setTitle('연락처(휴대폰)').setHelpText('견적·일정 안내용').setRequired(true);
  form.addTextItem().setTitle('이메일').setHelpText('견적서 송부용(선택)').setRequired(false);
  form.addMultipleChoiceItem().setTitle('렌트 목적')
    .setChoiceValues(['행사·세미나', '촬영·미디어', '소규모 클래스·PT', '기업 워크숍', '프라이빗 모임', '기타'])
    .setRequired(true);
  form.addCheckboxItem().setTitle('희망 공간').setHelpText('복수 선택 가능')
    .setChoiceValues(['수영장', '스튜디오·GX룸', '라운지·커뮤니티', '골프존', '스쿼시 코트', '사우나·리커버리', '전체 대관', '협의 필요'])
    .setRequired(true);
  form.addTextItem().setTitle('희망 일자').setHelpText('예: 2026-07-15 오후 — 가용 일정은 담당자가 확인 후 회신').setRequired(true);
  form.addCheckboxItem().setTitle('희망 시간대').setHelpText('복수 선택 가능')
    .setChoiceValues(['오전(영업시작~12시)', '오후(12~17시)', '저녁(17~21시)', '종일', '협의'])
    .setRequired(false);
  form.addMultipleChoiceItem().setTitle('예상 인원')
    .setChoiceValues(['10명 이하', '11~30명', '31~50명', '51~100명', '100명 초과'])
    .setRequired(false);
  form.addMultipleChoiceItem().setTitle('예상 예산대(참고)').setHelpText('안내·참고용입니다. 미정이어도 괜찮습니다.')
    .setChoiceValues(['미정', '100만원 이하', '100~300만원', '300~500만원', '500만원 이상'])
    .setRequired(false);
  form.addMultipleChoiceItem().setTitle('알게 된 경로')
    .setChoiceValues(['회원 소개', '인스타그램·SNS', '온라인 검색', '입주·지역 커뮤니티', '기타'])
    .setRequired(true);
  form.addParagraphTextItem().setTitle('상세 요청사항').setHelpText('행사 성격·필요 장비·세부 일정 등 자유롭게 적어주세요').setRequired(false);
  form.addCheckboxItem().setTitle('개인정보 수집·이용 동의')
    .setHelpText(_pipa_('공간 렌트 문의 응대 및 일정·견적 안내'))
    .setChoiceValues([PIPA_CONSENT_CHOICE])
    .setRequired(true);
  return form;
}

// ═══════════════════════════════════════════════════════════
//  2. 비즈니스 파트너 문의 폼
// ═══════════════════════════════════════════════════════════
function _buildPartnerForm_() {
  var form = FormApp.create('웰페리온 스포츠클럽 — 비즈니스 파트너 문의');
  form.setDescription(
    '웰페리온과 함께 성장할 파트너를 찾습니다. 제휴·입점·콜라보·B2B 복지 제안 등 사업 협업을 제안해 주시면 '
    + '담당 부서가 검토 후 연락드립니다.'
  );
  form.setCollectEmail(false);
  form.setRequireLogin(false);
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage('문의가 접수되었습니다. 담당자가 영업일 기준 1일 이내 연락드리겠습니다.');

  form.addTextItem().setTitle('회사·브랜드명').setRequired(true);
  form.addTextItem().setTitle('담당자 성함').setRequired(true);
  form.addTextItem().setTitle('직책').setRequired(false);
  form.addTextItem().setTitle('연락처(휴대폰)').setHelpText('협의 일정 안내용').setRequired(true);
  form.addTextItem().setTitle('이메일').setHelpText('제안서·회신 송부용').setRequired(true);
  form.addMultipleChoiceItem().setTitle('제휴 유형')
    .setChoiceValues(['브랜드 콜라보·프로모션', '입점·공간 제휴', 'B2B 기업복지·단체 멤버십', '콘텐츠·미디어 협업', '상품·서비스 공급', '투자·사업제휴', '기타'])
    .setRequired(true);
  form.addMultipleChoiceItem().setTitle('회사 규모')
    .setChoiceValues(['1~10인', '11~50인', '51~200인', '200인 초과', '개인·프리랜서'])
    .setRequired(false);
  form.addTextItem().setTitle('웹사이트·SNS·소개자료 링크').setHelpText('URL').setRequired(false);
  form.addMultipleChoiceItem().setTitle('희망 진행 시점')
    .setChoiceValues(['즉시·1개월 내', '1~3개월', '3개월 이상', '미정'])
    .setRequired(false);
  form.addMultipleChoiceItem().setTitle('알게 된 경로')
    .setChoiceValues(['회원 소개', '인스타그램·SNS', '온라인 검색', '업계 네트워크', '기타'])
    .setRequired(true);
  form.addParagraphTextItem().setTitle('제안 내용').setHelpText('제휴 목적·기대 효과·협업 형태를 구체적으로 적어주세요').setRequired(true);
  form.addCheckboxItem().setTitle('개인정보 수집·이용 동의')
    .setHelpText(_pipa_('사업 제휴 검토 및 협의 진행'))
    .setChoiceValues([PIPA_CONSENT_CHOICE])
    .setRequired(true);
  return form;
}

// ═══════════════════════════════════════════════════════════
//  메인 — GM이 이 함수를 1회 실행
// ═══════════════════════════════════════════════════════════
function createInquiryFormsKR() {
  var ss = SpreadsheetApp.create('웰페리온 신규문의 응답(공간렌트·비즈니스파트너)');
  var ssId = ss.getId();
  Logger.log('════════════════════════════════════');
  Logger.log('응답 스프레드시트 ssId = ' + ssId);
  Logger.log('응답 시트 URL = ' + ss.getUrl());
  Logger.log('────────────────────────────────────');

  var before1 = _sheetIdSet_(ss);
  var f1 = _buildSpaceRentalForm_();
  f1.setDestination(FormApp.DestinationType.SPREADSHEET, ssId);
  var g1 = _newSheetInfo_(ss, before1);
  Logger.log('[공간렌트] 공개 URL  = ' + f1.getPublishedUrl());
  Logger.log('[공간렌트] 편집 URL  = ' + f1.getEditUrl());
  Logger.log('[공간렌트] 응답탭 gid = ' + g1.gid + '  (탭명: ' + g1.name + ')');
  Logger.log('────────────────────────────────────');

  var before2 = _sheetIdSet_(ss);
  var f2 = _buildPartnerForm_();
  f2.setDestination(FormApp.DestinationType.SPREADSHEET, ssId);
  var g2 = _newSheetInfo_(ss, before2);
  Logger.log('[파트너]   공개 URL  = ' + f2.getPublishedUrl());
  Logger.log('[파트너]   편집 URL  = ' + f2.getEditUrl());
  Logger.log('[파트너]   응답탭 gid = ' + g2.gid + '  (탭명: ' + g2.name + ')');
  Logger.log('════════════════════════════════════');
  Logger.log('▼ apps_script_survey.js FORM_SHEETS 교체값(주석 풀고 아래로):');
  Logger.log("  , { ssId: '" + ssId + "', gid: " + g1.gid + ", type: '공간렌트',       channelKeys: ['경로', '채널', '알게'] }");
  Logger.log("  , { ssId: '" + ssId + "', gid: " + g2.gid + ", type: '비즈니스파트너', channelKeys: ['경로', '채널', '알게'] }");
  Logger.log('════════════════════════════════════');
  Logger.log('⚠️ 다음: 각 폼 UI > 설정 > 응답 > "조직으로 제한" 해제(비로그인 외부 제출). 시크릿창 제출 테스트.');
}

// ═══════════════════════════════════════════════════════════
//  재지정 — 공간렌트·파트너 응답을 멤버십 관리 스프레드시트로 통합
//  실행: GM이 repointInquiryFormsToMembership() 1회 실행 → 새 응답탭 gid 출력
//  결과: 12AWcAlg 안에 새 응답탭 2개 생성. 기존 1zkT는 폐기 가능(테스트응답 포함).
// ═══════════════════════════════════════════════════════════
function repointInquiryFormsToMembership() {
  var TARGET = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';  // 1-1) 멤버십 문의 관리(26년도)
  var forms = [
    { name: '공간렌트',       id: '1u8MsWSZO_kRBNdJxjLLhbNnhdIZr73l-WlyPIPntcsc' },
    { name: '비즈니스파트너', id: '1A7tDDFD0LJZFwqdrlHEYWQbOfd_un6uB8NIgcZNiEUE' }
  ];
  var out = [];
  Logger.log('════════════════════════════════════');
  Logger.log('대상 통합 스프레드시트 = ' + TARGET);
  forms.forEach(function(f) {
    var before = {};
    SpreadsheetApp.openById(TARGET).getSheets().forEach(function(s) { before[s.getSheetId()] = true; });
    var form = FormApp.openById(f.id);
    form.setDestination(FormApp.DestinationType.SPREADSHEET, TARGET);
    SpreadsheetApp.flush();
    Utilities.sleep(1500);
    var gid = null, nm = null;
    SpreadsheetApp.openById(TARGET).getSheets().forEach(function(s) {
      if (!before[s.getSheetId()]) { gid = s.getSheetId(); nm = s.getName(); }
    });
    Logger.log('[' + f.name + '] 새 응답탭 gid = ' + gid + '  (탭명: ' + nm + ')');
    out.push({ type: f.name, gid: gid });
  });
  Logger.log('────────────────────────────────────');
  Logger.log('▼ apps_script_survey.js FORM_SHEETS 교체값(ssId·gid 갱신):');
  out.forEach(function(r) {
    Logger.log("  , { ssId: '" + TARGET + "', gid: " + r.gid + ", type: '" + r.type + "', channelKeys: ['경로', '채널', '알게'] }");
  });
  Logger.log('════════════════════════════════════');
  Logger.log('⚠️ 기존 1zkT 응답 스프레드시트는 이제 미사용 — 휴지통 이동 가능(테스트응답 2건 함께 폐기).');
}
