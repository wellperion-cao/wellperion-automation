// Wellperion English Google Forms Generator v1.0
// 실행: createEnglishForms() 함수를 GAS 에디터에서 1회 실행
// 생성되는 폼: 멤버십 / 성인강습 / 유소년강습 / 여름특강 (영문 4종)
// 응답 시트 연결:
//   멤버십       → MEMBER_SPREADSHEET_ID (12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U)
//   성인·유소년   → LESSON_SPREADSHEET_ID (1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw)
//   여름특강      → LESSON_SPREADSHEET_ID (동일)

// ─── 응답 시트 ID ───
var MEMBER_SS_ID = '12AWcAlgmmYKr2nUbWmVpa71_z3zi0BaU4ZdnOwrI_7U';
var LESSON_SS_ID = '1b0XU1oTHlXzBhEzUOar5GEm44vjopdO25qfsh-awDXw';

// PIPA 동의문 (공통 영문)
var PIPA_MEMBERSHIP =
  'In accordance with the Personal Information Protection Act (PIPA) of the Republic of Korea, ' +
  'Wellperion Co., Ltd. collects and processes your personal information as follows.\n\n' +
  'Purpose: Scheduling and conducting membership tours and consultations; responding to membership inquiries.\n' +
  'Items collected: Name, mobile phone number, areas of interest, preferred tour date, wellness goal.\n' +
  'Retention: 1 year from collection date, or until purpose is fulfilled (whichever is earlier).\n' +
  'Third-party disclosure: Not shared without separate consent, except as required by law.\n\n' +
  'You have the right to refuse consent; however, doing so may prevent us from processing your inquiry.\n\n' +
  'I have read and agree to the above terms for the collection and use of my personal information.';

var PIPA_ADULT =
  'In accordance with the Personal Information Protection Act (PIPA) of the Republic of Korea, ' +
  'Wellperion Co., Ltd. collects and processes your personal information as follows.\n\n' +
  'Purpose: Processing lesson inquiries; scheduling consultations and trial lessons; program matching.\n' +
  'Items collected: Name, mobile phone number, age group, program interest, preferred lesson time, instructor preference, additional requests.\n' +
  'Retention: 1 year from collection date, or until purpose is fulfilled (whichever is earlier).\n' +
  'Third-party disclosure: Not shared without separate consent, except as required by law.\n\n' +
  'You have the right to refuse consent; however, doing so may prevent us from processing your inquiry.\n\n' +
  'I have read and agree to the above terms for the collection and use of my personal information.';

var PIPA_YOUTH =
  'In accordance with the Personal Information Protection Act (PIPA) of the Republic of Korea, ' +
  'Wellperion Co., Ltd. collects and processes personal information as follows. ' +
  'As this form concerns a minor, the legal guardian is required to provide consent on the child\'s behalf.\n\n' +
  'Purpose: Processing youth program inquiries; scheduling consultations and trial sessions; program matching.\n' +
  'Items collected: Child\'s name, child\'s age, guardian\'s name, guardian\'s contact number, relationship to child, program interest, additional requests.\n' +
  'Retention: 1 year from collection date, or until purpose is fulfilled (whichever is earlier).\n' +
  'Third-party disclosure: Not shared without separate consent, except as required by law.\n\n' +
  'The guardian has the right to refuse consent; however, doing so may prevent processing of the inquiry.\n\n' +
  'I am the legal guardian of the child named above, and I have read and agree to the above terms for the collection and use of personal information.';

var PIPA_SUMMER =
  'In accordance with the Personal Information Protection Act (PIPA) of the Republic of Korea, ' +
  'Wellperion Co., Ltd. collects and processes your personal information as follows.\n\n' +
  'Purpose: Processing summer program inquiries; scheduling consultations and program registration; participant matching and communication.\n' +
  'Items collected: Name, mobile phone number, participant type, program interest, preferred period and session time, additional requests.\n' +
  'Retention: 1 year from collection date, or until purpose is fulfilled (whichever is earlier).\n' +
  'Third-party disclosure: Not shared without separate consent, except as required by law.\n' +
  'For inquiries submitted on behalf of a minor, the legal guardian\'s consent is required.\n\n' +
  'You have the right to refuse consent; however, doing so may prevent us from processing your inquiry.\n\n' +
  'I have read and agree to the above terms for the collection and use of my personal information.';

// ─── 유틸: Language 고정값 항목 추가 ───
function _addLanguageField_(form) {
  var item = form.addTextItem();
  item.setTitle('Language');
  item.setRequired(false);
  // 기본값은 GAS FormApp에서 직접 설정 불가 — 절차문서에서 안내
  // 응답 시트에서 EN 구분은 이 항목에 응답자가 보는 값 "EN"으로 식별
  // (실제 운영 시 prefillUrl 또는 hiddenField 대체 가능)
}

// ─── 유틸: 응답 시트 연결 ───
function _linkToSheet_(form, spreadsheetId) {
  try {
    var ss = SpreadsheetApp.openById(spreadsheetId);
    form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheetId);
    Logger.log('  시트 연결 완료: ' + spreadsheetId);
  } catch (e) {
    Logger.log('  [경고] 시트 연결 실패 — 권한 확인 필요: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════
//  1. 멤버십 문의 폼
// ═══════════════════════════════════════════════════════════
function createMembershipFormEN_() {
  var form = FormApp.create('Wellperion Private Sports Club — Membership Inquiry');
  form.setDescription(
    'Thank you for your interest in Wellperion, Seoul\'s premier private sports club. ' +
    'Please complete the following to schedule your exclusive club tour and consultation.\n\n' +
    'Tour appointments are available by prior reservation only. Walk-in visits are not accepted.\n' +
    'For immediate assistance: http://wellperion.com/en/inquiry/'
  );
  form.setCollectEmail(false);
  form.setRequireLogin(false);   // 익명 제출 허용(조직 로그인벽 제거) — 외국인 방문자 접근 가능
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage(
    'Thank you for your inquiry. Our consultant will contact you within one business day to schedule your tour.'
  );

  // Q1 Full Name
  form.addTextItem()
    .setTitle('Full Name')
    .setHelpText('e.g., Kim Namwook')
    .setRequired(true);

  // Q2 Mobile Phone Number
  form.addTextItem()
    .setTitle('Mobile Phone Number')
    .setHelpText('e.g., 010-0000-0000 — Used for consultation scheduling only.')
    .setRequired(true);

  // Q3 Areas of Interest (checkbox)
  form.addCheckboxItem()
    .setTitle('Areas of Interest')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Health & Wellness Management',
      'Swimming',
      'Golf',
      'Sauna & Recovery',
      'Private Lessons (PT / Aqua / Pilates / Squash)'
    ])
    .setRequired(true);

  // Q4 How Did You Hear About Us? (MC)
  form.addMultipleChoiceItem()
    .setTitle('How Did You Hear About Us?')
    .setChoiceValues([
      'Member referral',
      'Instagram / Social media',
      'Online search',
      'Building / Residential community notice',
      'Other'
    ])
    .setRequired(true);

  // Q5 Preferred Tour Date (text, optional)
  form.addTextItem()
    .setTitle('Preferred Tour Date (and Time, if applicable)')
    .setHelpText('e.g., 2026-06-15, afternoon preferred — Our consultants will confirm availability within one business day.')
    .setRequired(false);

  // Q6 Health & Wellness Goal (paragraph, optional)
  form.addParagraphTextItem()
    .setTitle('Your Health & Wellness Goal')
    .setHelpText('Briefly describe what you hope to achieve through membership (e.g., weight management, stress relief, sport performance).')
    .setRequired(false);

  // Q7 Language (EN 식별용)
  _addLanguageField_(form);

  // Q8 Privacy Consent (PIPA)
  form.addCheckboxItem()
    .setTitle('Consent to Collection and Use of Personal Information')
    .setHelpText(PIPA_MEMBERSHIP)
    .setChoiceValues([
      'I have read and agree to the above terms for the collection and use of my personal information.'
    ])
    .setRequired(true);

  // 응답 시트 연결
  _linkToSheet_(form, MEMBER_SS_ID);

  return form;
}

// ═══════════════════════════════════════════════════════════
//  2. 성인 강습 문의 폼
// ═══════════════════════════════════════════════════════════
function createAdultLessonFormEN_() {
  var form = FormApp.create('Wellperion Private Sports Club — Adult Lesson Inquiry');
  form.setDescription(
    'Interested in private or group lessons at Wellperion? ' +
    'Fill in the details below and our program consultants will reach out to arrange a session tailored to your schedule and goals.\n\n' +
    'All lessons are by prior reservation only. Walk-in visits are not accepted.\n' +
    'For immediate assistance: http://wellperion.com/en/inquiry/'
  );
  form.setCollectEmail(false);
  form.setRequireLogin(false);   // 익명 제출 허용(조직 로그인벽 제거) — 외국인 방문자 접근 가능
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage(
    'Thank you! Our program consultant will contact you within one business day.'
  );

  // Q1 Full Name
  form.addTextItem()
    .setTitle('Full Name')
    .setHelpText('e.g., Kim Namwook')
    .setRequired(true);

  // Q2 Mobile Phone Number
  form.addTextItem()
    .setTitle('Mobile Phone Number')
    .setHelpText('e.g., 010-0000-0000')
    .setRequired(true);

  // Q3 Age Group (MC)
  form.addMultipleChoiceItem()
    .setTitle('Age Group')
    .setChoiceValues(['20s', '30s', '40s', '50s', '60 and above'])
    .setRequired(true);

  // Q4 Program of Interest (checkbox)
  form.addCheckboxItem()
    .setTitle('Program of Interest')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Personal Training (PT)',
      'Swimming Lessons',
      'Aqua Exercise',
      'Golf Lessons',
      'Squash Lessons',
      'Pilates'
    ])
    .setRequired(true);

  // Q5 How Did You Hear About Us? (MC)
  form.addMultipleChoiceItem()
    .setTitle('How Did You Hear About Us?')
    .setChoiceValues([
      'Member referral',
      'Instagram / Social media',
      'Online search',
      'Building / Residential community notice',
      'Other'
    ])
    .setRequired(true);

  // Q6 Preferred Lesson Time (checkbox, optional)
  form.addCheckboxItem()
    .setTitle('Preferred Lesson Time')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Early morning (before 8 AM)',
      'Morning (8 AM – 12 PM)',
      'Afternoon (12 PM – 5 PM)',
      'Evening (5 PM – 9 PM)'
    ])
    .setRequired(false);

  // Q7 Instructor Preference (MC, optional)
  form.addMultipleChoiceItem()
    .setTitle('Instructor Preference')
    .setChoiceValues([
      'No preference',
      'Prefer a specific instructor (please specify in the comments below)'
    ])
    .setRequired(false);

  // Q8 Additional Requests (paragraph, optional)
  form.addParagraphTextItem()
    .setTitle('Additional Requests or Comments')
    .setHelpText('Please share any specific requirements, physical conditions, or preferences our instructors should be aware of.')
    .setRequired(false);

  // Q9 Language (EN 식별용)
  _addLanguageField_(form);

  // Q10 Privacy Consent (PIPA)
  form.addCheckboxItem()
    .setTitle('Consent to Collection and Use of Personal Information')
    .setHelpText(PIPA_ADULT)
    .setChoiceValues([
      'I have read and agree to the above terms for the collection and use of my personal information.'
    ])
    .setRequired(true);

  // 응답 시트 연결
  _linkToSheet_(form, LESSON_SS_ID);

  return form;
}

// ═══════════════════════════════════════════════════════════
//  3. 유소년 강습 문의 폼
// ═══════════════════════════════════════════════════════════
function createYouthLessonFormEN_() {
  var form = FormApp.create('Wellperion Private Sports Club — Youth (WSC) Lesson Inquiry');
  form.setDescription(
    'Enroll your child in Wellperion\'s exclusive youth sports programs. ' +
    'Please provide the details below and our WSC program team will contact you to discuss the best fit.\n\n' +
    'All youth programs are by prior reservation only. Walk-in visits are not accepted.\n' +
    'For immediate assistance: http://wellperion.com/en/inquiry/'
  );
  form.setCollectEmail(false);
  form.setRequireLogin(false);   // 익명 제출 허용(조직 로그인벽 제거) — 외국인 방문자 접근 가능
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage(
    'Thank you! Our WSC program team will contact you within one business day.'
  );

  // Q1 Child's Full Name
  form.addTextItem()
    .setTitle("Child's Full Name")
    .setHelpText('e.g., Kim Sieun')
    .setRequired(true);

  // Q2 Guardian's Mobile Phone Number
  form.addTextItem()
    .setTitle("Guardian's Mobile Phone Number")
    .setHelpText('e.g., 010-0000-0000')
    .setRequired(true);

  // Q3 Child's Age
  form.addTextItem()
    .setTitle("Child's Age (years)")
    .setHelpText('e.g., 8')
    .setRequired(true);

  // Q4 WSC Program of Interest (checkbox)
  form.addCheckboxItem()
    .setTitle('WSC Program of Interest')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Swimming',
      'Gymnastics',
      'Squash',
      'Golf',
      'Growth-Focused Personal Training (Youth PT)',
      'Parent-Child Swimming',
      'Pilates (Youth)',
      'Musical Movement'
    ])
    .setRequired(true);

  // Q5 How Did You Hear About Us? (MC)
  form.addMultipleChoiceItem()
    .setTitle('How Did You Hear About Us?')
    .setChoiceValues([
      'Member referral',
      'Instagram / Social media',
      'Online search',
      'Building / Residential community notice',
      'Other'
    ])
    .setRequired(true);

  // Q6 Guardian's Full Name
  form.addTextItem()
    .setTitle("Guardian's Full Name")
    .setHelpText('e.g., Kim Namwook')
    .setRequired(true);

  // Q7 Guardian's Relationship to Child (MC, optional)
  form.addMultipleChoiceItem()
    .setTitle("Guardian's Relationship to Child")
    .setChoiceValues(['Father', 'Mother', 'Grandparent', 'Other'])
    .setRequired(false);

  // Q8 Additional Requests (paragraph, optional)
  form.addParagraphTextItem()
    .setTitle('Additional Requests or Comments')
    .setHelpText("Please share any health considerations, scheduling constraints, or special requirements for your child.")
    .setRequired(false);

  // Q9 Language (EN 식별용)
  _addLanguageField_(form);

  // Q10 Privacy Consent — 미성년자 포함 PIPA
  form.addCheckboxItem()
    .setTitle('Consent to Collection and Use of Personal Information (including minor\'s data)')
    .setHelpText(PIPA_YOUTH)
    .setChoiceValues([
      "I am the legal guardian of the child named above, and I have read and agree to the above terms for the collection and use of personal information."
    ])
    .setRequired(true);

  // 응답 시트 연결
  _linkToSheet_(form, LESSON_SS_ID);

  return form;
}

// ═══════════════════════════════════════════════════════════
//  4. 여름 특강 문의 폼
// ═══════════════════════════════════════════════════════════
function createSummerSpecialFormEN_() {
  var form = FormApp.create('Wellperion Private Sports Club — Summer Special Programs');
  form.setDescription(
    'Make the most of your summer at Wellperion. ' +
    'Our Summer Special programs offer intensive sessions across five premium sports disciplines. ' +
    'Submit your inquiry and our team will reach out with program details and scheduling options.\n\n' +
    'All Summer Special programs are by prior reservation only. Availability is limited — early inquiry is encouraged.\n' +
    'For immediate assistance: http://wellperion.com/en/inquiry/'
  );
  form.setCollectEmail(false);
  form.setRequireLogin(false);   // 익명 제출 허용(조직 로그인벽 제거) — 외국인 방문자 접근 가능
  form.setAllowResponseEdits(false);
  form.setConfirmationMessage(
    'Thank you for your interest in our Summer Special programs! We will be in touch shortly with details and availability.'
  );

  // Q1 Full Name
  form.addTextItem()
    .setTitle('Full Name')
    .setHelpText('e.g., Kim Namwook')
    .setRequired(true);

  // Q2 Mobile Phone Number
  form.addTextItem()
    .setTitle('Mobile Phone Number')
    .setHelpText('e.g., 010-0000-0000')
    .setRequired(true);

  // Q3 Participant Type (MC)
  form.addMultipleChoiceItem()
    .setTitle('Participant Type')
    .setChoiceValues([
      'Adult (18 and above)',
      'Youth / Child (under 18) — guardian inquiry'
    ])
    .setRequired(true);

  // Q4 Summer Special Program of Interest (checkbox)
  form.addCheckboxItem()
    .setTitle('Summer Special Program of Interest')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Summer Swimming Intensive',
      'Summer Gymnastics Intensive',
      'Summer Squash Intensive',
      'Summer Golf Intensive',
      'Youth Summer Personal Training (Growth-Focused PT)'
    ])
    .setRequired(true);

  // Q5 Preferred Program Period (MC, optional)
  form.addMultipleChoiceItem()
    .setTitle('Preferred Program Period')
    .setChoiceValues([
      'July 2026',
      'August 2026',
      'Either / Flexible'
    ])
    .setRequired(false);

  // Q6 Preferred Session Time (checkbox, optional)
  form.addCheckboxItem()
    .setTitle('Preferred Session Time')
    .setHelpText('Select all that apply.')
    .setChoiceValues([
      'Early morning (before 8 AM)',
      'Morning (8 AM – 12 PM)',
      'Afternoon (12 PM – 5 PM)',
      'Evening (5 PM – 9 PM)'
    ])
    .setRequired(false);

  // Q7 How Did You Hear About Us? (MC)
  form.addMultipleChoiceItem()
    .setTitle('How Did You Hear About Us?')
    .setChoiceValues([
      'Member referral',
      'Instagram / Social media',
      'Online search',
      'Building / Residential community notice',
      'Other'
    ])
    .setRequired(true);

  // Q8 Additional Requests (paragraph, optional)
  form.addParagraphTextItem()
    .setTitle('Additional Requests or Comments')
    .setHelpText('Please share any scheduling needs, physical conditions, or special requests our program team should consider.')
    .setRequired(false);

  // Q9 Language (EN 식별용)
  _addLanguageField_(form);

  // Q10 Privacy Consent (PIPA)
  form.addCheckboxItem()
    .setTitle('Consent to Collection and Use of Personal Information')
    .setHelpText(PIPA_SUMMER)
    .setChoiceValues([
      'I have read and agree to the above terms for the collection and use of my personal information.'
    ])
    .setRequired(true);

  // 응답 시트 연결
  _linkToSheet_(form, LESSON_SS_ID);

  return form;
}

// ═══════════════════════════════════════════════════════════
//  메인 실행 함수 — GAS 에디터에서 이 함수 1회 실행
// ═══════════════════════════════════════════════════════════
function createEnglishForms() {
  Logger.log('=== Wellperion 영문 구글폼 4종 생성 시작 ===');

  var results = [];

  try {
    Logger.log('[1/4] 멤버십 문의 폼 생성 중...');
    var f1 = createMembershipFormEN_();
    var url1 = f1.getPublishedUrl();
    var edit1 = f1.getEditUrl();
    results.push({ name: '멤버십 문의 (EN)', published: url1, edit: edit1 });
    Logger.log('  완료: ' + url1);
  } catch (e) {
    Logger.log('  [오류] 멤버십 폼: ' + e.message);
    results.push({ name: '멤버십 문의 (EN)', error: e.message });
  }

  try {
    Logger.log('[2/4] 성인 강습 문의 폼 생성 중...');
    var f2 = createAdultLessonFormEN_();
    var url2 = f2.getPublishedUrl();
    var edit2 = f2.getEditUrl();
    results.push({ name: '성인 강습 문의 (EN)', published: url2, edit: edit2 });
    Logger.log('  완료: ' + url2);
  } catch (e) {
    Logger.log('  [오류] 성인 강습 폼: ' + e.message);
    results.push({ name: '성인 강습 문의 (EN)', error: e.message });
  }

  try {
    Logger.log('[3/4] 유소년 강습 문의 폼 생성 중...');
    var f3 = createYouthLessonFormEN_();
    var url3 = f3.getPublishedUrl();
    var edit3 = f3.getEditUrl();
    results.push({ name: '유소년 강습 문의 (EN)', published: url3, edit: edit3 });
    Logger.log('  완료: ' + url3);
  } catch (e) {
    Logger.log('  [오류] 유소년 강습 폼: ' + e.message);
    results.push({ name: '유소년 강습 문의 (EN)', error: e.message });
  }

  try {
    Logger.log('[4/4] 여름 특강 문의 폼 생성 중...');
    var f4 = createSummerSpecialFormEN_();
    var url4 = f4.getPublishedUrl();
    var edit4 = f4.getEditUrl();
    results.push({ name: '여름 특강 문의 (EN)', published: url4, edit: edit4 });
    Logger.log('  완료: ' + url4);
  } catch (e) {
    Logger.log('  [오류] 여름 특강 폼: ' + e.message);
    results.push({ name: '여름 특강 문의 (EN)', error: e.message });
  }

  Logger.log('');
  Logger.log('=== 생성 결과 요약 ===');
  results.forEach(function(r) {
    if (r.error) {
      Logger.log('[실패] ' + r.name + ' — ' + r.error);
    } else {
      Logger.log('[성공] ' + r.name);
      Logger.log('  공개 URL : ' + r.published);
      Logger.log('  편집 URL : ' + r.edit);
    }
  });
  Logger.log('=== 완료 ===');

  return results;
}

// ═══════════════════════════════════════════════════════════
//  [중요] 기존 라이브 폼 4종 — 설정만 수정(중복 생성 금지)
//  목적: 익명 로그인벽 제거(setRequireLogin=false) + CTA litt.ly→en/inquiry 갱신
//  방식: 소유자 Drive에서 정확한 제목으로 기존 폼을 찾아 openById → 설정 변경.
//        새 폼을 만들지 않음(FormApp.create 호출 없음).
//  실행: GM이 GAS 에디터에서 updateEnglishFormsAccess() 1회 실행(폼 소유자 계정).
// ═══════════════════════════════════════════════════════════

// 생성 시 사용한 정확한 폼 제목 → 수정 후 description(이미 litt.ly→en/inquiry 반영본)
var EN_FORM_SPECS = [
  { title: 'Wellperion Private Sports Club — Membership Inquiry',
    desc: 'Thank you for your interest in Wellperion, Seoul\'s premier private sports club. ' +
          'Please complete the following to schedule your exclusive club tour and consultation.\n\n' +
          'Tour appointments are available by prior reservation only. Walk-in visits are not accepted.\n' +
          'For immediate assistance: http://wellperion.com/en/inquiry/' },
  { title: 'Wellperion Private Sports Club — Adult Lesson Inquiry',
    desc: 'Interested in private or group lessons at Wellperion? ' +
          'Fill in the details below and our program consultants will reach out to arrange a session tailored to your schedule and goals.\n\n' +
          'All lessons are by prior reservation only. Walk-in visits are not accepted.\n' +
          'For immediate assistance: http://wellperion.com/en/inquiry/' },
  { title: 'Wellperion Private Sports Club — Youth (WSC) Lesson Inquiry',
    desc: 'Enroll your child in Wellperion\'s exclusive youth sports programs. ' +
          'Please provide the details below and our WSC program team will contact you to discuss the best fit.\n\n' +
          'All youth programs are by prior reservation only. Walk-in visits are not accepted.\n' +
          'For immediate assistance: http://wellperion.com/en/inquiry/' },
  { title: 'Wellperion Private Sports Club — Summer Special Programs',
    desc: 'Make the most of your summer at Wellperion. ' +
          'Our Summer Special programs offer intensive sessions across five premium sports disciplines. ' +
          'Submit your inquiry and our team will reach out with program details and scheduling options.\n\n' +
          'All Summer Special programs are by prior reservation only. Availability is limited — early inquiry is encouraged.\n' +
          'For immediate assistance: http://wellperion.com/en/inquiry/' }
];

// Drive에서 정확한 제목의 Google Form을 찾아 폼 객체 반환(없으면 null, 다수면 가장 최근 1개)
function _findFormByTitle_(title) {
  var it = DriveApp.getFilesByName(title);
  var newest = null, newestTime = 0;
  while (it.hasNext()) {
    var f = it.next();
    if (f.getMimeType() !== MimeType.GOOGLE_FORMS) continue;
    var t = f.getLastUpdated().getTime();
    if (t >= newestTime) { newestTime = t; newest = f; }
  }
  if (!newest) return null;
  return FormApp.openById(newest.getId());
}

// 단일 편집 작업 재시도 래퍼 — "Failed to edit the form. Please wait and try again."(일시적) 대응.
// 3회까지 3초 간격 재시도. 끝내 실패하면 'FAIL:<메시지>' 반환(→ 일시적 아님 = 정책 차단 의심).
function _tryFormOp_(fn, label) {
  for (var a = 1; a <= 3; a++) {
    try { fn(); return 'OK'; }
    catch (e) {
      if (a < 3) { Utilities.sleep(3000); continue; }
      return 'FAIL: ' + e.message;
    }
  }
}

function updateEnglishFormsAccess() {
  Logger.log('=== [수정v2·진단형] 영문 폼 4종 — 익명 허용 + CTA 갱신 (작업별 진단 + 자동 재시도) ===');
  var summary = [];
  for (var i = 0; i < EN_FORM_SPECS.length; i++) {
    var spec = EN_FORM_SPECS[i];
    var rec = { title: spec.title, status: 'PENDING' };
    try {
      var form = _findFormByTitle_(spec.title);
      if (!form) {
        Logger.log('[누락] 폼 못 찾음: ' + spec.title);
        rec.status = 'NOT_FOUND';
        summary.push(rec);
        continue;
      }
      rec.published = form.getPublishedUrl();
      rec.edit = form.getEditUrl();
      try { rec.beforeLogin = form.requiresLogin(); } catch (e) { rec.beforeLogin = 'read-fail'; }

      // ── 작업을 분리해 어느 설정이 막히는지 콕 집어 진단 ──
      rec.opRequireLogin = _tryFormOp_(function () { form.setRequireLogin(false); }, 'setRequireLogin(false)');
      rec.opCollectEmail = _tryFormOp_(function () { form.setCollectEmail(false); }, 'setCollectEmail(false)');
      rec.opDescription  = _tryFormOp_(function () { form.setDescription(spec.desc); }, 'setDescription');

      try { rec.afterLogin = form.requiresLogin(); } catch (e) { rec.afterLogin = 'read-fail'; }
      rec.status = (rec.opRequireLogin === 'OK' && rec.afterLogin === false) ? 'LOGIN_FIXED'
                 : (rec.opRequireLogin === 'OK') ? 'LOGIN_OP_OK_BUT_STILL_ON'
                 : 'LOGIN_BLOCKED';

      Logger.log('[' + rec.status + '] ' + spec.title);
      Logger.log('   requiresLogin: ' + rec.beforeLogin + ' → ' + rec.afterLogin);
      Logger.log('   setRequireLogin: ' + rec.opRequireLogin);
      Logger.log('   setCollectEmail: ' + rec.opCollectEmail);
      Logger.log('   setDescription:  ' + rec.opDescription);
      Logger.log('   공개 URL: ' + rec.published);
    } catch (e) {
      Logger.log('[오류] ' + spec.title + ' — ' + e.message);
      rec.status = 'ERROR';
      rec.error = e.message;
    }
    summary.push(rec);
    Utilities.sleep(2500); // 폼 간 간격 — 연속 편집 속도제한(rate-limit) 회피
  }

  Logger.log('');
  Logger.log('=== 수정 결과 요약 ===');
  var blocked = 0;
  summary.forEach(function (s) {
    Logger.log(s.status + ' | login(' + s.beforeLogin + '→' + s.afterLogin + ') | ' + s.title);
    if (s.status === 'LOGIN_BLOCKED' || s.status === 'ERROR') blocked++;
  });
  Logger.log('');
  if (blocked === summary.length) {
    Logger.log('!! 4종 모두 막힘 → 일시적 혼잡 아님. Google Workspace 관리정책이 폼 로그인을 강제하는 것으로 판단.');
    Logger.log('   → 스크립트로 해제 불가. 폼 UI 수동 토글(설정▸응답▸"조직 제한" 해제) 또는 관리콘솔 정책 변경 필요.');
  } else if (blocked > 0) {
    Logger.log('일부만 성공 — 실패분은 잠시 후 다시 실행하면 풀릴 수 있음(일시적 가능성).');
  } else {
    Logger.log('=== 전부 성공 — 익명 시크릿창으로 4종 폼 로그인벽 없이 열리는지 재검증 ===');
  }
  return summary;
}

// ═══════════════════════════════════════════════════════════
//  [최종·멱등] finalizeEnglishForms() — 로그인해제 + 시트연결 보장 통합
//  목적: 영문 폼 4종에 대해 (1)익명 허용 (2)이메일수집 끄기 (3)응답 시트 연결 보장
//        (4)description CTA 유지 — 를 한 번에, 여러 번 실행해도 안전(멱등)하게 처리.
//  중복 방지 핵심: setDestination 은 "현재 미연결/오연결"일 때만 호출.
//        이미 올바른 시트에 연결돼 있으면 절대 재호출 안 함(중복 응답탭 생성 위험 차단).
//        FormApp.create 호출 없음(중복 폼 0).
//  실행: GM이 GAS 에디터에서 finalizeEnglishForms() 1회 실행(폼 소유자 cao@ 계정).
// ═══════════════════════════════════════════════════════════

// 폼 제목 → 연결돼야 할 응답 시트 ID 매핑 (생성 스크립트 _linkToSheet_ 규칙과 동일)
//   멤버십 → MEMBER_SS / 성인·유소년·여름 → LESSON_SS
var EN_FORM_SHEET_MAP = [
  { title: 'Wellperion Private Sports Club — Membership Inquiry',      ss: MEMBER_SS_ID },
  { title: 'Wellperion Private Sports Club — Adult Lesson Inquiry',    ss: LESSON_SS_ID },
  { title: 'Wellperion Private Sports Club — Youth (WSC) Lesson Inquiry', ss: LESSON_SS_ID },
  { title: 'Wellperion Private Sports Club — Summer Special Programs', ss: LESSON_SS_ID }
];

// 제목으로 spec(description)을 찾아 반환 (EN_FORM_SPECS 재사용)
function _specForTitle_(title) {
  for (var i = 0; i < EN_FORM_SPECS.length; i++) {
    if (EN_FORM_SPECS[i].title === title) return EN_FORM_SPECS[i];
  }
  return null;
}

// 응답 시트 연결 보장(멱등) — 이미 올바른 시트면 손대지 않음.
// 반환: { link, before, target } / link ∈ already-linked | newly-linked | relinked | link-failed
function _ensureSheetLinked_(form, targetSsId) {
  var curType, curId = null;
  try { curType = form.getDestinationType(); } catch (e) { curType = null; }
  // getDestinationId(): 목적지 없으면 예외 발생 → try로 감싸 안전 처리
  try { curId = form.getDestinationId(); } catch (e) { curId = null; }

  var isSpreadsheet = (curType === FormApp.DestinationType.SPREADSHEET);
  var beforeStr = (isSpreadsheet && curId) ? curId : '(none)';

  // 이미 올바른 시트에 연결됨 → 절대 재호출 안 함(중복 응답탭 방지)
  if (isSpreadsheet && curId === targetSsId) {
    return { link: 'already-linked', before: beforeStr, target: targetSsId };
  }
  // 미연결 또는 오연결 → 올바른 시트로 (재)연결
  var wasLinkedElsewhere = (isSpreadsheet && curId && curId !== targetSsId);
  var op = _tryFormOp_(function () {
    form.setDestination(FormApp.DestinationType.SPREADSHEET, targetSsId);
  }, 'setDestination');
  if (op !== 'OK') {
    return { link: 'link-failed', before: beforeStr, target: targetSsId, error: op };
  }
  return { link: wasLinkedElsewhere ? 'relinked' : 'newly-linked', before: beforeStr, target: targetSsId };
}

function finalizeEnglishForms() {
  Logger.log('=== [최종·멱등] finalizeEnglishForms — 로그인해제 + 시트연결 보장 (중복 0) ===');
  var summary = [];
  for (var i = 0; i < EN_FORM_SHEET_MAP.length; i++) {
    var map = EN_FORM_SHEET_MAP[i];
    var spec = _specForTitle_(map.title);
    var rec = { title: map.title, status: 'PENDING' };
    try {
      var form = _findFormByTitle_(map.title);
      if (!form) {
        Logger.log('[누락] 폼 못 찾음: ' + map.title);
        rec.status = 'NOT_FOUND';
        summary.push(rec);
        continue;
      }
      rec.published = form.getPublishedUrl();
      rec.edit = form.getEditUrl();

      // (1) 익명 허용 + (2) 이메일수집 끄기 (멱등 — 이미 그 값이어도 무해)
      rec.opRequireLogin = _tryFormOp_(function () { form.setRequireLogin(false); }, 'setRequireLogin(false)');
      rec.opCollectEmail = _tryFormOp_(function () { form.setCollectEmail(false); }, 'setCollectEmail(false)');
      try { rec.requiresLogin = form.requiresLogin(); } catch (e) { rec.requiresLogin = 'read-fail'; }

      // (3) 응답 시트 연결 보장 — 이미 올바르면 건드리지 않음
      var dr = _ensureSheetLinked_(form, map.ss);
      rec.destination = dr.target;
      rec.destinationBefore = dr.before;
      rec.linkResult = dr.link;
      if (dr.error) rec.linkError = dr.error;

      // (4) description CTA 유지/보정 (멱등)
      if (spec) rec.opDescription = _tryFormOp_(function () { form.setDescription(spec.desc); }, 'setDescription');

      var linkOk = (dr.link === 'already-linked' || dr.link === 'newly-linked' || dr.link === 'relinked');
      rec.status = (rec.opRequireLogin === 'OK' && rec.requiresLogin === false && linkOk)
                 ? 'FINALIZED' : 'NEEDS_ATTENTION';

      Logger.log('[' + rec.status + '] ' + map.title);
      Logger.log('   requiresLogin(after): ' + rec.requiresLogin + ' | setRequireLogin: ' + rec.opRequireLogin + ' | setCollectEmail: ' + rec.opCollectEmail);
      Logger.log('   destination: ' + rec.destination + ' (' + rec.linkResult + ')  [before: ' + rec.destinationBefore + ']');
      if (rec.linkError) Logger.log('   !! 시트연결 실패: ' + rec.linkError);
      Logger.log('   공개 URL: ' + rec.published);
    } catch (e) {
      Logger.log('[오류] ' + map.title + ' — ' + e.message);
      rec.status = 'ERROR';
      rec.error = e.message;
    }
    summary.push(rec);
    Utilities.sleep(2500); // 폼 간 간격 — 연속 편집 rate-limit 회피
  }

  Logger.log('');
  Logger.log('=== finalize 결과 요약 ===');
  var notReady = 0;
  summary.forEach(function (s) {
    Logger.log(s.status + ' | login=' + s.requiresLogin + ' | destination: ' + s.destination + ' (' + s.linkResult + ') | ' + s.title);
    if (s.status !== 'FINALIZED') notReady++;
  });
  Logger.log('');
  if (notReady === 0) {
    Logger.log('=== 전부 FINALIZED — 익명 시크릿창 제출 테스트 후 해당 시트 탭 적재 확인 권장 ===');
  } else {
    Logger.log('!! ' + notReady + '건 미완 — 위 로그의 NEEDS_ATTENTION/ERROR 항목 확인. 잠시 후 재실행(멱등) 또는 폼 UI 점검.');
  }
  return summary;
}
