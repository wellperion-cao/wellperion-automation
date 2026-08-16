/**
 * ⚠️ 폐기됨 (2026-06-23, 2026-08-17 정본 재확인) — 이 파일은 더 이상 사용/배포되지 않습니다.
 *
 * 퍼널/문의 Survey GAS의 라이브 정본 = .deploy-funnel-v2/Survey.js
 *   (clasp scriptId 1BezMSW… · 배포: cd .deploy-funnel-v2 && clasp push -f && clasp deploy -i <deploymentId>)
 * .deploy-funnel(scriptId 1A77oDR…, 이 주석이 예전에 정본이라 적었던 곳)은 INC-040(2026-07-31)에서
 *   "은퇴한 백업"으로 확인됨 — 라이브 아님.
 *
 * 고객이 보는 접수 폼(wp_inquiry_form.html)의 intake_submit 은 위 원본이 아니라
 *   .deploy-intake/Intake.js (scriptId 1zmXkpox…, intake-api 로 분리된 경량 배포)가 실제로 실행한다
 *   (2026-08-10 시토 전환 · wp_inquiry_form.html GAS_PROD). 두 파일의 intake_submit 블록은
 *   scripts/tests/test_intake_parity.py 가 자동 대조 — 접수 유형을 고치면 원본(.deploy-funnel-v2)과
 *   분리본(.deploy-intake) 둘 다 고쳐야 이 검사가 통과한다.
 *
 * 함수 수정·추가는 반드시 .deploy-funnel-v2/Survey.js 에서 한다(접수 로직은 .deploy-intake/Intake.js 동반 수정).
 * 과거 구버전 코드는 git 이력에 보존됨(이 파일 직전 커밋).
 * (이중 소스 드리프트로 #3가 죽은 사본에 잘못 들어간 사고 → 단일화)
 */
