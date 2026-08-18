// LOSS/미등록 사유 표준 목록(17종) — 단일 정본(배653 근본수리, 2026-08-18).
//   membership.html·renewal.html 이 각자 목록을 따로 갖고 있어 실제로 어긋났다(임정은M 재요청, renewal.html
//   구주석 "v4 동기화"가 그 흔적). 이제 두 화면이 이 파일 하나를 <script src>로 읽는다.
//   문구는 시트에 그대로 쌓인 과거 데이터와 맞물려 있다 — 한 글자도 고치지 말 것(추가는 GM 결정 사항).
var LOSS_REASON_OPTIONS = ['금액·프로모션', '양도/강습전환', '건강문제', '단기', '낮은이용횟수', '타센터등록', '거주지변경', '무응답(기타)', '가망', '블랙', '수신거절', '연락처상이함', '재등록혜택', '시설불만', '주차불만', '휴회불만', '바쁜일정'];
var INQ_LOSS_REASON_OPTIONS = LOSS_REASON_OPTIONS;   // membership.html 기존 변수명(하위호환)
var NOREG_REASONS = LOSS_REASON_OPTIONS;             // renewal.html 기존 변수명(하위호환)
