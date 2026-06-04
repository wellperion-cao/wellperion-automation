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
    'For immediate assistance: http://wellperion.com/ko/inquiry/'
  );
  form.setCollectEmail(false);
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
    'For immediate assistance: http://wellperion.com/ko/inquiry/'
  );
  form.setCollectEmail(false);
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
    'For immediate assistance: http://wellperion.com/ko/inquiry/'
  );
  form.setCollectEmail(false);
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
    'For immediate assistance: http://wellperion.com/ko/inquiry/'
  );
  form.setCollectEmail(false);
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
