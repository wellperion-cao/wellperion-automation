// =====================================================================
// 웰페리온 인사 운영 허브 — 시트 기반 백엔드 v2.0 (Notion 완전 제거)
// Last updated: 2026-06-03
//
// 데이터 SSOT: 인사현황 시트 (1iOxky9aPwzMN2XZXBMNBRcXuo8np7qbseTDpKIIZrl4)
// 워크시트 7개: 현재근무자, 퇴사자, 채용공고, 지원자, 인사평가, 입사·온보딩, 퇴사처리
//
// 배포 후 1회 실행: migrateNotionToSheets() — Notion 데이터를 시트로 옮김
// =====================================================================

// ====== 상수 ======
var ACCESS_PASSWORD  = "wellperion!@345";
var ADMIN_PASSWORD   = "wellperion!@1202";
var CMD_PASSWORD     = "fk1200132!";  // HR office CMD 전용 저권한(조회+명령큐만, 파괴적 쓰기 불가)
// [추가 2026-07-10 2차] office-cmd-push(무비번 공개 접수) 스팸 가드 — 회수(cmd-pull)·결과기록(cmd-result)·
// 실행은 여전히 admin 비밀번호 + "오피스큐" 세션 승인 뒤에 있으므로, 여기 가드는 큐 적재 남용만 억제한다.
var OFFICE_CMD_MAX_PENDING   = 5;     // 대기(pending) 상태 명령이 이미 이만큼이면 신규 접수 거부
var OFFICE_CMD_MAX_PER_HOUR  = 20;    // 상태 무관, 최근 1시간 내 접수 건수 상한
var OFFICE_CMD_MAX_LEN       = 500;   // 명령 텍스트 최대 길이(자)
// [추가 2026-07-18 A-5] submit-application(자체 지원 접수 폼) 스팸 가드 — 무비번 공개 액션.
//   office-cmd-push의 "길이·건수·시간당 상한" 3종 가드 개념을 차용하되, 이 액션은 접수 즉시
//   파일을 Drive에 쓰고 큐 대기 개념이 없어(폴더가 계속 커지므로 폴더 스캔 방식 대신)
//   CacheService 기반 시간대 버킷 카운터로 구현(폴더 크기 무관 O(1) 판정). 파일 검증(형식·크기)·
//   허니팟은 office-cmd-push에 없던 이 액션 고유의 추가 가드(공개 웹폼이라 봇 유입 표면이 다름).
var SUBMIT_APP_MAX_PER_HOUR  = 10;    // 시간당 접수 상한(시간대 버킷 키, 슬라이딩 윈도우 아님)
var SUBMIT_APP_MAX_FIELD_LEN = { name: 50, phone: 20, email: 100, position: 100 };
var SUBMIT_APP_MAX_FILE_BYTES = 10 * 1024 * 1024; // 10MB
var SUBMIT_APP_ALLOWED_MIME_ = { "application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png" };
var HR_SHEET_ID      = "1iOxky9aPwzMN2XZXBMNBRcXuo8np7qbseTDpKIIZrl4";

// 온보딩 체크인 위임 기입 전용 PIN(저권한) — 관리자 비번과 무관, 온보딩 체크인 필드 쓰기만 허용
var ONBO_PIN = "1202";
var ONBO_CHECKIN_CATS_ = ["주간 체크인", "격주 체크리스트", "월간 체크인"];

// 워크시트 이름
var SHEET_CURRENT = "현재근무자";
var SHEET_EXIT    = "퇴사자";
var SHEET_HIRE    = "채용공고";
var SHEET_APPL    = "지원자";
var SHEET_EVAL    = "인사평가";
var SHEET_ONBO    = "입사·온보딩";
var SHEET_RESIGN  = "퇴사처리";
var SHEET_LEAVE   = "휴무";
var SHEET_AUTOLOG = "자동화로그"; // [추가 2026-07-04] CHRO 자동화 로그(append 전용, 없으면 자동 생성)
var SHEET_BLACKLIST = "채용블랙리스트"; // [추가 2026-07-07] 채용 블랙리스트(append 전용, 없으면 자동 생성). PII 최소화: 연락처 뒤4자리만.
var SHEET_CMDQUEUE = "명령큐"; // [추가 2026-07-08] 오피스 터미널 ↔ CHRO 세션 명령 큐(append-only, 없으면 자동 생성)
// [추가 2026-07-20 A-5, 매니저 승인 개선④] 결정대기 — 매니저 판단 대기 건 큐(append-only, 없으면 자동 생성).
//   STATE.md 적체 완화용: 아침 브리핑에 미결 1건씩 로테이션 노출(표시만, 자동 결정·자동 실행 없음).
//   PII 금지 — 요지/옵션/추천 텍스트만 적재(적재자 책임, 생년·연락처 등 상세 금지).
var SHEET_DECISION = "결정대기";
// [추가 2026-07-24] 근무변경신청 — 근무 스케줄 보드(schedule.html) 신청·결재 공유 저장(없으면 자동 생성).
//   보드가 localStorage(기기별) 한계로 기기 간 데이터가 안 보이던 문제의 서버 정본. id 단위 upsert.
//   공개 액션(schedreq-*)이지만 쓰기는 필드 화이트리스트·길이 상한·상태 enum·행수 상한·Lock으로 가드.
var SHEET_SCHEDREQ = "근무변경신청";
var SCHEDREQ_MAX_ROWS = 2000;
// [추가 2026-07-14 A-4] 직무성과(50%) 업무평가 — 관리자가 COO 업무보드(읽기전용 소스)에서 로드한 업무별
//   완성도(0~100%)·성과점수(1~5)를 입력·저장하는 HR 관리자 영역(admin 비번 보호). COO 보드는 무변경(읽기전용).
//   대상자+평가기간 단위로 in-place upsert(행 삽입/삭제 없음), 업무 목록은 JSON으로 한 셀에 보관.
var SHEET_WORKEVAL = "업무평가";
// 업무 중요도(난이도) 가중치 — SSOT 대시보드(DIFF_WEIGHT)와 동일: 하1·중5·상10. 미책정=0(계산 제외·경고).
var WORKEVAL_DIFF_WEIGHT = { "하": 1, "중": 5, "상": 10 };

// [추가 2026-07-14 A-4 웨이브2] 자기평가·리더십평가(상향) 트랙 — 등급 미반영(1년차 개발/진단용).
//   두 탭 모두 HR 관리자 잠금영역: handleReadOne_(db:) switch·public-stats·autolog 어디에도 없어 공개 읽기(viewer)로 노출 0.
//   자기평가: 본인이 팀장평가와 동일 항목(5축+태도)을 5점 척도로 선제출 → 팀장 평가지에 자기점수 병렬표시(갭). 등급·총점 미산출.
//   리더십평가: 부서원→팀장 상향, 6항목 5점 + 개선서술. 평가자 실명 미저장(비식별). 응답 3명 미만이면 그 팀장 결과 전면 비공개(k-익명).
var SHEET_SELFEVAL   = "자기평가";
var SHEET_LEADEREVAL = "리더십평가";
// k-익명 최소 응답수 — 리더십평가 집계·요약(리더 공유용) 열람 게이트. 이 값 미만이면 전면 비공개.
var LEADERSHIP_MIN_K = 3;
// 리더십평가 문항(6) — 정본 확정스펙(방향제시·공정성·코칭·소통·의사결정·구성원 존중). 등급 종합 없음.
var LEADERSHIP_ITEMS = ["방향 제시","공정성","코칭·성장지원","소통","의사결정","구성원 존중"];

// 마이그레이션용 (1회 실행 후 NOTION_TOKEN은 삭제해도 됨)
var NOTION_TOKEN = "ntn_y108197716025oIXQyE5DcmIWQJ6YSw2qXCkKg4KHLF7OF";
var NOTION_DATABASES = {
  emp:  "d9838f3ef40340a8ab5b67724bccdb4e",
  hire: "3430407da94881689b5ffdef39c9ea00",
  appl: "769a164c1eda432da225d5d805a4b8ff",
  onbo: "20e93fccb4e24c0c8a5423a1fa7dde89",
  eval: "5455ef5eb90a4fc09ff987c51b7ecb5c",
  exit: "08df810076c84969941a8e2e662c50d6"
};

// 기존 인사현황 시트 헤더 (5행/6행)
var HEADER_ROW     = 5;
var DATA_START_ROW = 6;

// 신규 워크시트의 헤더는 1행, 데이터는 2행부터
var NEW_HEADER_ROW     = 1;
var NEW_DATA_START_ROW = 2;

// 신규 워크시트 헤더 정의
var SCHEMAS = {
  hire: [
    "포지션명","부서","채용 유형","채용 상태","채용 채널","우선순위","담당 C-Level",
    "공고 시작일","공고 마감일","채용 완료일","모집 인원","지원자 수","면접자 수",
    "급여 범위","주요 업무","자격 요건","비고","원본 Notion URL"
  ],
  appl: [
    "지원자명","연결 공고","지원 포지션","지원 경로","전형 단계","면접 평점",
    "지원일","면접 일정","합류 가능일","담당 면접관","연락처","이메일","메모","원본 Notion URL"
  ],
  eval: [
    "평가명","대상자","평가 종류","평가 주기","평가 기간 시작","평가 기간 종료",
    "평가자","총점","가산점","평가 등급","평가지 링크","포상 여부","포상 내역","피드백","원본 Notion URL"
  ],
  onbo: [
    "체크 항목","카테고리","대상 신입 직원","담당자","완료 기한","완료 여부","완료일","비고","원본 Notion URL"
  ],
  resign: [
    "처리 건명","연결 임직원","퇴사 유형","퇴사 신청일","최종 근무일","퇴사 사유","면담 내용",
    "퇴사 면담 여부","장비 반납 여부","시스템 계정 회수","퇴직금 지급 여부","퇴직금 지급일","처리 완료 여부","원본 Notion URL"
  ],
  leave: [
    "성명","부서","날짜","값","등록일시"
  ],
  autolog: [
    "일시","주체","작업","상세","결과"
  ],
  blacklist: [
    "No","성명","생년","연락처(뒤4자리)","지원경로","사유","등록일","비고"
  ],
  cmdqueue: [
    "id","시각","명령","상태","결과","응답시각"
  ],
  // [추가 2026-07-20 A-5] 결정대기 — 매니저 판단 대기 큐. 상태: pending/done(행 삭제 금지, 상태 칸만 갱신).
  //   옵션JSON = 문자열 배열을 JSON.stringify한 것. 마지막노출일 = 브리핑 로테이션 마킹(yyyy-MM-dd).
  decision: [
    "id","등록일시","요지","옵션JSON","추천안","상태","마지막노출일","완료일시"
  ],
  // [추가 2026-07-24] 근무변경신청 — 스케줄 보드 신청·결재 공유 저장. id 단위 upsert(행 이동 없음).
  schedreq: [
    "id","신청자","종류","대상일","출근","퇴근","사유","결재자","상태","결재일","등록일시","수정일시"
  ],
  // [추가 2026-07-14 A-4] 업무평가(직무성과 산출) — 대상자+평가기간 단위 1행. 업무목록JSON에 카드별
  //   완성도·성과점수·성취도·중요도가중치를 보관. 직무성과=Σ(중요도가중치×성취도)/Σ(중요도가중치)(0~100).
  workeval: [
    "대상자","평가기간","직무성과","중요도합","커버리지","미책정건수","겸직플래그",
    "산출식버전","평가자","업무목록JSON","저장일시"
  ],
  // [추가 2026-07-14 A-4 웨이브2] 자기평가 — 대상자(본인)+평가기간 단위 1행(upsert). 등급·총점 열 없음(미산출).
  //   공통역량5축·태도5항목 점수는 JSON으로 보관(팀장 평가지 병렬 갭 표시용). 자유서술은 이 잠금탭에만(db:eval 공개읽기 미노출).
  selfeval: [
    "대상자","평가기간","평가주기","공통역량5축JSON","태도5항목JSON",
    "직무성과 자기서술","성장영역","필요지원","강점","개발영역","저장일시"
  ],
  // [추가 2026-07-14 A-4 웨이브2] 리더십평가(부서원→팀장, 상향) — 제출 1건=1행(append-only).
  //   ⚠평가자 실명/식별정보 열 없음(비식별·역추적 차단). '제출경로'는 통로 감사용(self/admin)일 뿐 신원 아님.
  leadereval: [
    "대상팀장","평가기간","항목점수JSON","개선서술","제출경로","저장일시"
  ]
};

// ====== Web App 진입점 ======
function doGet_impl_(e) {
  return withCORS_(handleRequest_(e, "GET"));
}

function doPost_impl_(e) {
  return withCORS_(handleRequest_(e, "POST"));
}

function handleRequest_(e, method) {
  try {
    var body = {};
    if (method === "POST" && e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }
    var params = (e && e.parameter) || {};

    // [추가] 공개 집계 — 비밀번호 불필요, 개인정보 미포함 (인증 게이트보다 먼저 처리)
    var __pubAction = body.action || params.action || "";
    if (__pubAction === "public-stats") {
      return jsonResponse_(handlePublicStats_());
    }

    // [추가 2026-07-16 A-5 P2·G5] 리크루팅 정적 페이지 마감 동기 — 비밀번호 불필요.
    //   화이트리스트 4필드만 반환(포지션명/bucket/상태/closed) — 급여·담당자·URL 등 PII·민감정보 0.
    if (__pubAction === "public-job-status") {
      return jsonResponse_(handlePublicJobStatus_());
    }

    // [추가] 온보딩 위임 기입 — 관리자 비번 불필요. 이름 목록은 공개(PII 無), 조회·저장은 PIN(1202) 필요.
    // 스코프 최소권한: 온보딩(입사·온보딩) 시트의 체크인 카테고리 행만, 그마저도 완료여부/완료일/비고/담당자 필드만 쓸 수 있음.
    if (__pubAction === "onbo-active-names") {
      return jsonResponse_(handleOnboActiveNames_());
    }

    // [추가 2026-07-05] 자동화 로그 공개 열람 — 비밀번호 불필요.
    //   자동화로그 탭(작업 이력)만 접근, 다른 탭(인사·지원자 등)은 절대 건드리지 않음.
    //   반환 필드는 일시·주체·작업·상세·결과 5개로 고정(화이트리스트) — 그 외 필드 노출 금지.
    //   limit 기본 300, 최대 600. offset으로 이어받기 지원(최신순 정렬 후 페이지네이션).
    if (__pubAction === "autolog-list") {
      var __alPubLimit = parseInt(body.limit || params.limit, 10);
      if (!__alPubLimit || __alPubLimit <= 0 || isNaN(__alPubLimit)) __alPubLimit = 300;
      if (__alPubLimit > 600) __alPubLimit = 600;
      var __alPubOffset = parseInt(body.offset || params.offset, 10);
      if (!__alPubOffset || __alPubOffset < 0 || isNaN(__alPubOffset)) __alPubOffset = 0;
      return jsonResponse_(handleAutologListPublic_(__alPubLimit, __alPubOffset));
    }

    // [추가 2026-07-10] HR office 개방 개편 — 오피스 화면 전용 "공개" 열람(비밀번호 불필요).
    //   autolog-list처럼 자동화로그 탭만 읽지만, 오피스 화면은 실명 그대로 표시하기로 매니저 확정
    //   (실행 안전장치는 "오피스큐" 인간 승인 절차이지 이 화면의 열람 여부가 아니므로 이름 마스킹 미적용).
    //   PII 노출면을 autolog-list보다 한 단계 더 좁힘 — 상세(자유텍스트, PII 위험도 최고) 필드는
    //   애초에 반환하지 않고 일시·주체·작업·결과 4개만(office.html이 실제로 쓰는 필드와 정확히 일치).
    if (__pubAction === "office-autolog") {
      var __oaLimit = parseInt(body.limit || params.limit, 10);
      if (!__oaLimit || __oaLimit <= 0 || isNaN(__oaLimit)) __oaLimit = 300;
      if (__oaLimit > 600) __oaLimit = 600;
      var __oaOffset = parseInt(body.offset || params.offset, 10);
      if (!__oaOffset || __oaOffset < 0 || isNaN(__oaOffset)) __oaOffset = 0;
      return jsonResponse_(handleOfficeAutologPublic_(__oaLimit, __oaOffset));
    }

    // [2026-07-10 2차 개편] office-cmd-push(무비번 공개 접수) — 7/10 1차 시도는 A-6 병렬 감사에서
    //   "무권한자가 CHRO 실행큐에 명령 주입 가능"으로 NO-GO 판정되어 철회했었다(drafts\tmp_B안감사_result.md).
    //   매니저 재결정(2026-07-10 2차)으로 서버측 스팸 가드(대기건수 상한·시간당 상한·길이 상한)를 전제로
    //   재도입한다. 안전판은 그대로 유지: 이 통로는 "접수(append, 상태=pending)"만 가능하고, 회수(cmd-pull)·
    //   결과기록(cmd-result)·실제 실행은 여전히 admin 비밀번호 + "오피스큐" 세션 승인 뒤에 있다(무손상).
    //   기존 비번 경로(cmd-push+adminPassword, role:"cmd"/"admin")는 완전히 무변경 유지.
    if (__pubAction === "office-cmd-push") {
      var __ocLock = LockService.getScriptLock();
      try { __ocLock.waitLock(15000); } catch (_ocLockErr) {
        return jsonResponse_({ ok: false, error: "busy", message: "다른 요청을 처리 중입니다. 잠시 후 다시 시도해 주세요." }, 503);
      }
      var __ocRes;
      try { __ocRes = handleOfficeCmdPush_(body); }
      finally { try { __ocLock.releaseLock(); } catch (_ocRelErr) {} }
      return jsonResponse_(__ocRes, __ocRes && __ocRes.ok ? 200 : 400);
    }

    // [추가 2026-07-18 A-5] submit-application(무비번 공개) — 리크루팅 페이지 자체 지원 접수.
    //   이 액션은 시트(지원자 탭)에 절대 직접 쓰지 않는다 — 파일을 자동수신 Drive 폴더에 저장만
    //   하고, 기존 이력서 자동 파이프라인(일일 스윕⑨ → intake-list 발견 → A-1 판독·평가 →
    //   register-applicant 등록)이 그대로 이어받는다(신규 등록 로직 중복 금지, 게이트①~④ 무손상).
    if (__pubAction === "submit-application") {
      var __saLock = LockService.getScriptLock();
      try { __saLock.waitLock(15000); } catch (_saLockErr) {
        return jsonResponse_({ ok: false, error: "busy", message: "다른 요청을 처리 중입니다. 잠시 후 다시 시도해 주세요." }, 503);
      }
      var __saRes;
      try { __saRes = handleSubmitApplication_(body); }
      finally { try { __saLock.releaseLock(); } catch (_saRelErr) {} }
      return jsonResponse_(__saRes, __saRes && __saRes.ok ? 200 : 400);
    }

    // [추가 2026-07-24] schedreq-* — 근무 스케줄 보드 신청·결재 공유 저장(무비번 공개).
    //   보드 자체가 공개 페이지 + 결재는 클라이언트 결재라인 확인 구조라 서버 비번 게이트 없음.
    //   대신 쓰기 가드: 필드 화이트리스트·길이 상한·상태 enum·행수 상한(SCHEDREQ_MAX_ROWS)·ScriptLock.
    //   근무변경신청 탭만 접근 — 다른 탭(인사·지원자 등)은 절대 건드리지 않음.
    if (__pubAction === "schedreq-list") {
      return jsonResponse_(handleSchedReqList_());
    }
    if (__pubAction === "schedreq-save" || __pubAction === "schedreq-delete") {
      var __srLock = LockService.getScriptLock();
      try { __srLock.waitLock(15000); } catch (_srLockErr) {
        return jsonResponse_({ ok: false, error: "busy", message: "다른 요청을 처리 중입니다. 잠시 후 다시 시도해 주세요." }, 503);
      }
      var __srRes;
      try { __srRes = (__pubAction === "schedreq-save") ? handleSchedReqSave_(body) : handleSchedReqDelete_(body); }
      finally { try { __srLock.releaseLock(); } catch (_srRelErr) {} }
      return jsonResponse_(__srRes, __srRes && __srRes.ok ? 200 : 400);
    }

    if (__pubAction === "onbo-checkin-read" || __pubAction === "onbo-checkin-save") {
      var __pin = String(body.pin || params.pin || "");
      if (__pin !== ONBO_PIN) {
        return jsonResponse_({ ok: false, error: "pin_invalid", message: "PIN 번호가 올바르지 않습니다." }, 401);
      }
      if (__pubAction === "onbo-checkin-read") {
        return jsonResponse_(handleOnboCheckinRead_(body));
      }
      var __lk3 = LockService.getScriptLock();
      try { __lk3.waitLock(20000); } catch (_le3) {
        return jsonResponse_({ ok: false, error: "다른 작업이 처리 중입니다. 잠시 후 다시 시도해 주세요." }, 503);
      }
      var __res3 = handleOnboCheckinSave_(body);
      bustDbrCache_(["onbo"]);
      return jsonResponse_(__res3);
    }

    // [추가 2026-07-04] 신입직원 본인 자가성찰 기입 — 관리자 비번 불필요.
    // [변경 2026-07-04 r2] 인증 방식: 멘토 PIN(1202) 공용 → 본인 연락처(현재근무자 시트) 뒤 4자리로 교체.
    //   멘토는 체크인만(onbo-checkin-*, PIN 1202 그대로), 신입 본인은 본인 성찰만(onbo-self-*, 연락처 뒤4자리) — 상호 교차 접근 차단.
    // 스코프 최소권한: 온보딩 시트의 '주간 성찰' 카테고리 행만, 완료여부/완료일/비고 필드만 쓸 수 있음(담당자 변경 불가).
    if (__pubAction === "onbo-self-read" || __pubAction === "onbo-self-save") {
      var __selfName = String(body.name || params.name || "").trim();
      var __pin2 = String(body.pin || params.pin || "");
      if (!__selfName) {
        return jsonResponse_({ ok: false, error: "name_required", message: "이름을 선택해 주세요." }, 400);
      }
      var __selfAuth = verifySelfPin_(__selfName, __pin2);
      if (!__selfAuth.ok) {
        return jsonResponse_({ ok: false, error: __selfAuth.error, message: __selfAuth.message }, 401);
      }
      if (__pubAction === "onbo-self-read") {
        return jsonResponse_(handleOnboSelfRead_(body));
      }
      var __lk4 = LockService.getScriptLock();
      try { __lk4.waitLock(20000); } catch (_le4) {
        return jsonResponse_({ ok: false, error: "다른 작업이 처리 중입니다. 잠시 후 다시 시도해 주세요." }, 503);
      }
      var __res4 = handleOnboSelfSave_(body);
      bustDbrCache_(["onbo"]);
      return jsonResponse_(__res4);
    }

    // [추가 2026-07-14 A-4 웨이브2] 리더십평가 익명 제출 — 부서원이 팀장을 평가·제출.
    //   자격 게이트: 제출자가 현직원 본인임을 verifySelfPin_(성명+연락처 뒤4자리)로 확인(외부 스팸 차단)하되
    //   ⚠제출자 신원은 시트에 저장하지 않는다(비식별). admin 비번으로도 대행 제출 가능(HR 스테이션).
    //   저장은 append-only(제출 1건=1행), db:eval 공개읽기 미노출 잠금탭. 집계·열람은 별도 admin 액션(k-익명 게이트).
    if (__pubAction === "leadership-submit") {
      var __lpPw    = body.password || body.adminPassword || params.password || "";
      var __lpAdmin = (checkPassword_(__lpPw) === "admin");
      var __lpChannel = "self";
      if (!__lpAdmin) {
        var __lpName = String(body.submitterName || params.submitterName || "").trim();
        if (!__lpName) {
          return jsonResponse_({ ok: false, error: "auth_required", message: "제출자 본인 성명과 연락처 뒤 4자리로 인증해 주세요(신원은 저장되지 않습니다)." }, 401);
        }
        var __lpv = verifySelfPin_(__lpName, String(body.pin || params.pin || ""));
        if (!__lpv.ok) {
          return jsonResponse_({ ok: false, error: __lpv.error, message: __lpv.message }, 401);
        }
      } else {
        __lpChannel = "admin";
      }
      var __lpLock = LockService.getScriptLock();
      try { __lpLock.waitLock(20000); } catch (_lpe) {
        return jsonResponse_({ ok: false, error: "busy", message: "다른 작업이 처리 중입니다. 잠시 후 다시 시도해 주세요." }, 503);
      }
      var __lpRes;
      try { __lpRes = handleSaveLeadershipEval_(body, __lpChannel); }
      finally { try { __lpLock.releaseLock(); } catch (_lpr) {} }
      return jsonResponse_(__lpRes, (__lpRes && __lpRes.ok) ? 200 : 400);
    }

    // 운영허브 호환: password / adminPassword 둘 다 인식
    var password = body.password || body.adminPassword || params.password || "";
    var role = checkPassword_(password);
    if (!role) return jsonResponse_({ ok: false, error: "unauthorized", message: "비밀번호가 올바르지 않습니다." }, 401);

    // [추가 2026-07-14 A-4] 업무평가(직무성과) 조회 — 읽기 전용이지만 성과점수를 담은 관리자 영역이라 admin 전용.
    //   읽기이므로 아래 쓰기용 락/캐시무효화 블록을 타지 않도록 여기서 먼저 처리(불필요한 직렬화·캐시버스트 회피).
    var __weReadAction = body.action || params.action || "";
    if (__weReadAction === "get-work-eval") {
      if (role !== "admin") {
        return jsonResponse_({ ok: false, error: "admin_required", message: "업무평가 조회는 관리자 비밀번호가 필요합니다." }, 403);
      }
      return jsonResponse_(handleGetWorkEval_(body));
    }

    // [추가 2026-07-14 A-4 웨이브2] 자기평가·리더십평가 조회 — 읽기 전용, 관리자 잠금영역(admin 전용).
    //   get-work-eval과 동일하게 쓰기용 락/캐시무효화 블록 앞에서 처리(불필요한 직렬화·캐시버스트 회피).
    //   ⚠리더십 조회는 k-익명 게이트(handleGetLeadershipEval_ 내부)로 응답 3명 미만이면 요약 전면 비공개.
    if (__weReadAction === "get-self-eval" || __weReadAction === "get-leadership-eval") {
      if (role !== "admin") {
        return jsonResponse_({ ok: false, error: "admin_required", message: "평가 조회는 관리자 비밀번호가 필요합니다." }, 403);
      }
      if (__weReadAction === "get-self-eval")       return jsonResponse_(handleGetSelfEval_(body));
      if (__weReadAction === "get-leadership-eval") return jsonResponse_(handleGetLeadershipEval_(body));
    }

    // [추가 2026-07-14 A-5] 이력서 자동수신 Drive 우회 — 클라우드 루틴이 Drive를 MCP 커넥터가 아니라
    //   이 백엔드(DriveApp)로 대행시켜 curl(/exec)만으로 동작하게 함(A-7 설계, drafts\A7_드라이브우회_요약.md).
    //   intake-list·intake-file은 읽기 전용(Drive만 조회, HR 시트 무관)이라 아래 쓰기용 락/캐시무효화
    //   블록을 타지 않도록 get-work-eval과 동일하게 여기서 먼저 처리. intake-report·intake-done도
    //   HR_SHEET_ID를 건드리지 않으므로(순수 Drive 쓰기) 같은 자리에서 처리해 불필요한 시트 락을 피한다.
    //   기존 doPost 라우팅·액션·행고정 계약(#13)은 무변경.
    var __intakeAction = body.action || params.action || "";
    if (__intakeAction === "intake-list" || __intakeAction === "intake-file" ||
        __intakeAction === "intake-report" || __intakeAction === "intake-done") {
      if (role !== "admin") {
        return jsonResponse_({ ok: false, error: "admin_required", message: "이력서 자동수신 액션은 관리자 비밀번호가 필요합니다." }, 403);
      }
      switch (__intakeAction) {
        case "intake-list":   return jsonResponse_(handleIntakeList_(body));
        case "intake-file":   return jsonResponse_(handleIntakeFile_(body));
        case "intake-report": return jsonResponse_(handleIntakeReport_(body));
        case "intake-done":   return jsonResponse_(handleIntakeDone_(body));
      }
    }

    // [추가 2026-07-15 A-5] 지원자 주소 ↔ 웰페리온 직선거리(km) — 순수 읽기(지오코딩+계산, 시트 쓰기 없음)이므로
    //   get-work-eval/intake-* 와 동일하게 쓰기용 락/캐시무효화 블록 앞에서 처리. role은 이미 위에서 검증됨(277행)
    //   — admin/viewer/cmd 모두 허용(민감정보 미포함, km만 반환).
    var __geoAction = body.action || params.action || "";
    if (__geoAction === "geo-distance") {
      return jsonResponse_(handleGeoDistance_(body));
    }

    // 운영허브 호환: db:"emp" 형태의 개별 DB 조회
    var dbKey = body.db || params.db;
    if (dbKey) {
      // 역대 퇴사자 명부 — 주민번호·생일 등 민감정보 포함이라 관리자 비밀번호 필수(다른 db 계열은 viewer도 허용).
      if (dbKey === "exitroster" && role !== "admin") {
        return jsonResponse_({ ok: false, error: "admin_required", message: "역대 퇴사자 명부는 관리자 비밀번호가 필요합니다." }, 403);
      }
      // [추가 2026-07-04] 자동화 로그 — 인사 내역 포함이라 관리자 비밀번호 필수.
      // limit 지원(기본 100), 최신순 정렬. 요청마다 값이 달라질 수 있어 공용 캐시(dbr_*)는 타지 않는다.
      if (dbKey === "autolog") {
        if (role !== "admin" && role !== "cmd") {
          return jsonResponse_({ ok: false, error: "admin_required", message: "자동화 로그는 관리자 비밀번호가 필요합니다." }, 403);
        }
        var __alLimit = parseInt(body.limit || params.limit, 10);
        if (!__alLimit || __alLimit <= 0 || isNaN(__alLimit)) __alLimit = 200;
        var __alOffset = parseInt(body.offset || params.offset, 10);
        if (!__alOffset || __alOffset < 0 || isNaN(__alOffset)) __alOffset = 0;
        var __alRows = handleReadAutolog_(__alLimit, __alOffset);
        return jsonResponse_({ ok: true, role: role, results: __alRows, count: __alRows.length, limit: __alLimit, offset: __alOffset });
      }
      // [2026-07-13 A-5] 캐시키에 등급(role) 포함 — 이전엔 등급무관 공용키(dbr_<db>)라 admin이 채운 캐시를
      // viewer가 그대로 받거나(원문 유출) 그 반대(교차오염) 위험이 있었음(A-6 감사 지적). 등급별 별도 캐시.
      var __ck="dbr_"+dbKey+"_"+role;var __cache=CacheService.getScriptCache();var __hit=null;try{__hit=__cache.get(__ck);}catch(_e){}if(__hit!==null){return jsonResponse_({ok:true,role:role,cached:true,results:JSON.parse(__hit)});}var __res=handleReadOne_(dbKey, role);if(role!=="admin"){__res=maskPiiForViewer_(__res);}try{var __s=JSON.stringify(__res);if(__s.length<95000)__cache.put(__ck,__s,DBR_CACHE_TTL_SEC_);}catch(_e){}return jsonResponse_({ok:true,role:role,results:__res});
    }

    var action = body.action || params.action || (method === "GET" ? "read" : "");

    var _lk=null;
    if(action && action!=="read"){
      if(role!=="admin" && !(role==="cmd" && (action==="cmd-push"||action==="cmd-status"))){ return jsonResponse_({ok:false,error:"관리자 권한이 필요합니다. 관리자(쓰기) 비밀번호로 다시 로그인하세요."},403); }
      _lk=LockService.getScriptLock(); try{ _lk.waitLock(20000); }catch(_le){ return jsonResponse_({ok:false,error:"다른 작업이 처리 중입니다. 잠시 후 다시 시도해 주세요."},503); }
      // [수정 2026-07-16 A-5 병목패치①②] 무효화를 락 획득 "성공" 후로 이동(503 실패 경로에서 무의미한 소거 방지) +
      // 액션→탭 매핑으로 소거 범위 축소(미등재 액션은 기존과 동일하게 8db 전량 폴백 — 과소무효화 회귀 0 지향).
      // 캐시키는 기존과 동일하게 등급 3종(admin/viewer/cmd) 모두 무효화.
      bustDbrCache_(ACTION_DB_MAP_.hasOwnProperty(action) ? ACTION_DB_MAP_[action] : ACTION_DB_FULL_FALLBACK_);
    }

    switch (action) {
      case "read":               return jsonResponse_(handleRead_(role));
      case "register":           requireAdmin_(role); return jsonResponse_(handleRegister_(body));
      case "resign":             requireAdmin_(role); return jsonResponse_(handleResign_(body));
      case "vacate-current":     requireAdmin_(role); return jsonResponse_(handleVacateCurrent_(body));
      case "add-exit-record":    requireAdmin_(role); return jsonResponse_(handleAddExitRecord_(body));
      case "fix-exit-row":       requireAdmin_(role); return jsonResponse_(handleFixExitRow_(body));
      case "schedule-interview": requireAdmin_(role); return jsonResponse_(handleScheduleInterview_(body));
      case "update-interview":   requireAdmin_(role); return jsonResponse_(handleUpdateInterview_(body));
      case "hire-complete":      requireAdmin_(role); return jsonResponse_(handleHireComplete_(body));
      case "save-eval":          requireAdmin_(role); return jsonResponse_(handleSaveEval_(body));
      case "save-work-eval":     requireAdmin_(role); return jsonResponse_(handleSaveWorkEval_(body));
      case "save-self-eval":     requireAdmin_(role); return jsonResponse_(handleSaveSelfEval_(body));
      case "add-job":            requireAdmin_(role); return jsonResponse_(handleAddJob_(body));
      case "register-applicant": requireAdmin_(role); return jsonResponse_(handleRegisterApplicant_(body));
      case "update-job": requireAdmin_(role); return jsonResponse_(handleUpdateJob_(body));
      case "set-stage": requireAdmin_(role); return jsonResponse_(handleSetStage_(body));
      case "set-channels": requireAdmin_(role); return jsonResponse_(handleSetChannels_(body));
      case "update-applicant": requireAdmin_(role); return jsonResponse_(handleUpdateApplicant_(body));
      case "set-photo": requireAdmin_(role); return jsonResponse_(handleSetPhoto_(body));
      case "add-onboarding": requireAdmin_(role); return jsonResponse_(handleAddOnboarding_(body));
      case "add-selfreflect": requireAdmin_(role); return jsonResponse_(handleAddSelfReflect_(body));
      case "update-onboarding": requireAdmin_(role); return jsonResponse_(handleUpdateOnboarding_(body));
      case "delete-onboarding": requireAdmin_(role); return jsonResponse_(handleDeleteOnboarding_(body));
      case "update-hire": requireAdmin_(role); return jsonResponse_(handleUpdateHire_(body));
      case "update-headcount": requireAdmin_(role); return jsonResponse_(handleUpdateHeadcount_(body));
      case "set-leave":          requireAdmin_(role); return jsonResponse_(handleSetLeave_(body));
      case "set-leave-bulk":     requireAdmin_(role); return jsonResponse_(handleSetLeaveBulk_(body));
      case "delete-leave":       requireAdmin_(role); return jsonResponse_(handleSetLeave_({emp:(body.emp||body.name), date:body.date, value:""}));
      case "delete-applicant":   requireAdmin_(role); return jsonResponse_(handleDeleteApplicant_(body));
      case "delete-eval":        requireAdmin_(role); return jsonResponse_(handleDeleteEval_(body));
      case "set-eval-target":    requireAdmin_(role); return jsonResponse_(handleSetEvalTarget_(body));
      case "migrate":            requireAdmin_(role); return jsonResponse_(migrateNotionToSheets());
      case "add-blacklist":      requireAdmin_(role); return jsonResponse_(handleAddBlacklist_(body));
      case "remove-blacklist":   requireAdmin_(role); return jsonResponse_(handleRemoveBlacklist_(body));
      case "decision-add":       requireAdmin_(role); return jsonResponse_(handleDecisionAdd_(body));  // [추가 2026-07-20 A-5]
      case "decision-list":      requireAdmin_(role); return jsonResponse_(handleDecisionList_(body)); // [추가 2026-07-20 A-5]
      case "decision-done":      requireAdmin_(role); return jsonResponse_(handleDecisionDone_(body)); // [추가 2026-07-20 A-5]
      case "log-add":            requireAdmin_(role); return jsonResponse_(handleLogAdd_(body));
      case "log-add-bulk":       requireAdmin_(role); return jsonResponse_(handleLogAddBulk_(body));
      case "log-fix":            requireAdmin_(role); return jsonResponse_(handleLogFix_(body));
      case "autolog-reset":      requireAdmin_(role); return jsonResponse_(handleAutologReset_(body));
      case "run-reminder":       requireAdmin_(role); return jsonResponse_(handleRunReminder_(body));
      case "install-reminder-trigger": requireAdmin_(role); return jsonResponse_(handleInstallReminderTrigger_(body));
      case "tg-relay":           requireAdmin_(role); return jsonResponse_(handleTgRelay_(body)); // [2026-07-14 CFO 협업] 텔레그램 발송 위탁(기존 TG 속성 재사용·토큰 이동 없음)
      case "cmd-push":           requireCmdOrAdmin_(role); return jsonResponse_(handleCmdPush_(body));
      case "cmd-pull":           requireAdmin_(role); return jsonResponse_(handleCmdPull_(body));
      case "cmd-result":         requireAdmin_(role); return jsonResponse_(handleCmdResult_(body));
      case "cmd-status":         requireCmdOrAdmin_(role); return jsonResponse_(handleCmdStatus_(body));
      default:                   return jsonResponse_({ ok: false, error: "unknown_action", action: action }, 400);
    }
  } catch (err) {
    return jsonResponse_({ ok: false, error: "exception", message: String(err && err.message || err), stack: String(err && err.stack || "") }, 500);
  }
}

// =====================================================================
// [추가 2026-07-14 A-5] 이력서 자동수신 Drive 우회 4종 — DriveApp 표준 API로
//   자동수신 폴더 접근을 백엔드가 대행(A-7 설계, drafts\A7_드라이브우회_요약.md).
//   대상 폴더: 자동수신(jobkoinfo 메일 첨부 저장소) + 업로드(매니저 수동 업로드).
//   시스템 산출물(_처리대장.json·처리리포트_*·_알림_*)과 처리완료_* 하위폴더는 목록에서 제외.
// =====================================================================
var INTAKE_FOLDER_AUTO_   = "1zGBB4RERG7qmvR1azY6p0HIsZlqys6vY"; // 자동수신
var INTAKE_FOLDER_UPLOAD_ = "1dWAwOpRh6tWibiP-ixHeqK3F2joLsEun"; // 업로드
var INTAKE_FOLDERS_ = {
  "자동수신": INTAKE_FOLDER_AUTO_, "intake": INTAKE_FOLDER_AUTO_, "auto": INTAKE_FOLDER_AUTO_,
  "업로드":   INTAKE_FOLDER_UPLOAD_, "upload": INTAKE_FOLDER_UPLOAD_
};
// 처리완료_* 하위폴더는 getFiles()가 애초에 하위폴더를 반환하지 않아 자동 제외됨(폴더≠파일).
// 이 접두사들은 같은 폴더 "최상위"에 남는 시스템 산출 파일만 걸러낸다.
var INTAKE_SYSTEM_PREFIXES_ = ["_처리대장", "처리리포트_", "_알림_"];

function isIntakeSystemFile_(name) {
  for (var i = 0; i < INTAKE_SYSTEM_PREFIXES_.length; i++) {
    if (String(name || "").indexOf(INTAKE_SYSTEM_PREFIXES_[i]) === 0) return true;
  }
  return false;
}

function resolveIntakeFolderId_(folderParam) {
  var f = String(folderParam || "").trim();
  if (!f) return "";
  if (INTAKE_FOLDERS_[f]) return INTAKE_FOLDERS_[f];
  return f; // 라벨이 아니면 폴더ID로 간주(그대로 사용)
}

// ①intake-list: 두 폴더 최상위 신규 PDF 목록(id·이름·크기·폴더구분). 하위 처리완료_*·시스템산출물 제외.
//   [수정 2026-07-14 A-6 조건부GO 반영] 폴더 접근 실패를 continue로 조용히 삼키면 "빈 폴더"와
//   "접근권 없음"이 응답상 구분 안 돼(둘 다 ok:true,count:0) 배포후 스모크(폴더_not_found로 접근권
//   판별)가 무력화된다 → 폴더별 실패를 errors[]로 명시 노출하고, 두 폴더 모두 실패면 non-ok로 반환.
//   한 폴더만 실패해도(부분 실패) 나머지 폴더 목록은 정상 반환하되 errors에 함께 기록.
function handleIntakeList_(body) {
  var folders = [
    { id: INTAKE_FOLDER_AUTO_,   label: "자동수신" },
    { id: INTAKE_FOLDER_UPLOAD_, label: "업로드" }
  ];
  var out = [];
  var errors = [];
  for (var i = 0; i < folders.length; i++) {
    var folder;
    try { folder = DriveApp.getFolderById(folders[i].id); } catch (e) {
      errors.push({ folderId: folders[i].id, folder: folders[i].label, reason: String(e && e.message || e) });
      continue;
    }
    var it = folder.getFiles();
    while (it.hasNext()) {
      var f = it.next();
      var name = f.getName();
      if (isIntakeSystemFile_(name)) continue;
      // [수정 2026-07-18 A-5] PDF 단독 화이트리스트 → PDF/JPEG/PNG 화이트리스트로 확장.
      //   기존 PDF 계약(잡코리아 첨부)은 100% 그대로 통과, submit-application(자체 지원 폼)이
      //   저장하는 JPG/PNG 이력서도 스윕이 발견하도록 타입만 추가(하위호환 — 이 패치의 유일한
      //   기존함수 수정 지점, A-6 감사 시 별도 확인).
      var __mt = f.getMimeType();
      if (__mt !== MimeType.PDF && __mt !== MimeType.JPEG && __mt !== MimeType.PNG) continue;
      out.push({ fileId: f.getId(), name: name, size: f.getSize(), folder: folders[i].label });
    }
  }
  // 두 폴더 모두 접근 실패 = "빈 폴더"가 아니라 접근권 문제 확정 신호 → non-ok로 명확히 구분.
  if (errors.length > 0 && errors.length === folders.length) {
    return {
      ok: false, action: "intake-list", error: "folder_access_failed",
      message: "두 폴더 모두 접근에 실패했습니다 — 백엔드 실행계정의 폴더 접근권을 확인하세요.",
      count: 0, results: [], errors: errors
    };
  }
  return { ok: true, action: "intake-list", count: out.length, results: out, errors: errors };
}

// ②intake-file: 지정 PDF를 base64로 1건 반환(비전판독·복호화는 세션에서 계속 수행).
function handleIntakeFile_(body) {
  var fileId = String((body && body.fileId) || "").trim();
  if (!fileId) return { ok: false, error: "fileId_required", message: "fileId는 필수입니다." };
  var file;
  try { file = DriveApp.getFileById(fileId); } catch (e) {
    return { ok: false, error: "file_not_found", message: "파일을 찾을 수 없습니다: " + fileId };
  }
  var blob = file.getBlob();
  var base64;
  try { base64 = Utilities.base64Encode(blob.getBytes()); } catch (e2) {
    return { ok: false, error: "encode_failed", message: String(e2 && e2.message || e2) };
  }
  return {
    ok: true, action: "intake-file", fileId: fileId, name: file.getName(),
    mimeType: blob.getContentType(), size: file.getSize(), base64: base64
  };
}

// ③intake-report: 처리리포트·알림플래그를 지정 폴더(라벨 또는 폴더ID)에 텍스트 파일로 기록(있으면 덮어쓰기).
function handleIntakeReport_(body) {
  var filename = String((body && body.filename) || "").trim();
  var content = (body && body.content != null) ? String(body.content) : "";
  if (!filename) return { ok: false, error: "filename_required", message: "filename은 필수입니다." };
  var folderId = resolveIntakeFolderId_((body && body.folder) || "");
  if (!folderId) return { ok: false, error: "folder_required", message: "folder는 필수입니다(자동수신/업로드 라벨 또는 폴더ID)." };
  var folder;
  try { folder = DriveApp.getFolderById(folderId); } catch (e) {
    return { ok: false, error: "folder_not_found", message: "폴더를 찾을 수 없습니다: " + folderId };
  }
  // 동일 파일명 존재 시 덮어쓰기 = 기존분 휴지통 이동 후 새로 생성(버전 난립 방지)
  var existing = folder.getFilesByName(filename);
  while (existing.hasNext()) { existing.next().setTrashed(true); }
  var newFile = folder.createFile(filename, content, MimeType.PLAIN_TEXT);
  return { ok: true, action: "intake-report", fileId: newFile.getId(), name: filename, folderId: folderId };
}

// ④intake-done: 처리분을 「처리완료_YYYY-MM-DD」 하위폴더(원본 상위폴더 기준, 없으면 생성)로 이동.
function handleIntakeDone_(body) {
  var fileId = String((body && body.fileId) || "").trim();
  if (!fileId) return { ok: false, error: "fileId_required", message: "fileId는 필수입니다." };
  var dateStr = String((body && body.dateStr) || "").trim();
  if (!dateStr) dateStr = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd");
  var file;
  try { file = DriveApp.getFileById(fileId); } catch (e) {
    return { ok: false, error: "file_not_found", message: "파일을 찾을 수 없습니다: " + fileId };
  }
  var parents = file.getParents();
  if (!parents.hasNext()) {
    return { ok: false, error: "no_parent", message: "원본 상위 폴더를 찾을 수 없습니다." };
  }
  var origin = parents.next();
  var destName = "처리완료_" + dateStr;
  var destFolder;
  var subIter = origin.getFoldersByName(destName);
  if (subIter.hasNext()) { destFolder = subIter.next(); }
  else { destFolder = origin.createFolder(destName); }
  destFolder.addFile(file);
  origin.removeFile(file);
  return { ok: true, action: "intake-done", fileId: fileId, movedTo: destName };
}

// =====================================================================
// [추가 2026-07-18 A-5] SUBMIT-APPLICATION — 자체 지원 접수 폼(무비번 공개).
//   지원자가 이름·연락처(+이메일 선택)·포지션·이력서 파일(PDF/JPG/PNG, ≤10MB)을 제출하면
//   자동수신 Drive 폴더(INTAKE_FOLDER_AUTO_)에 파일로 저장 — 기존 이력서 자동 파이프라인
//   (일일 스윕⑨ → intake-list 발견 → A-1 PDF판독/AI평가 → register-applicant 등록)이
//   그대로 이어받는다. 이 함수는 지원자 시트에 절대 직접 쓰지 않음(신규 등록 로직은
//   전부 기존 파이프라인 전담 — 중복 금지). 스팸 가드 4종: 필드 길이 상한 · 시간당 접수
//   상한(CacheService 시간대 버킷, 폴더 크기 무관 O(1)) · 파일 형식+크기 화이트리스트 ·
//   허니팟(가짜 성공 응답으로 봇 교란, 실제 저장·로그는 안 함).
//   ⚠️ handleIntakeList_()는 기존에 PDF만 필터링했다(원래 주석 "PDF만(잡코리아 첨부 계약)").
//   JPG/PNG 웹폼 이력서도 스윕이 발견하게 하려면 그 필터를 PDF/JPEG/PNG 화이트리스트로
//   넓혀야 한다(아래 handleIntakeList_ 수정 참조) — 기존 PDF 동작은 100% 그대로 유지되고
//   타입만 추가되는 하위호환 변경이지만, 이번 패치에서 "새로 추가"가 아니라 "기존 함수를
//   수정"하는 유일한 지점이므로 A-6 감사 시 반드시 별도 확인할 것.
// =====================================================================
function handleSubmitApplication_(body) {
  body = body || {};

  // 허니팟 — 봉인 필드(website)가 채워져 있으면 봇으로 간주. 가짜 성공 응답(교란)만 반환하고
  // 실제 파일 저장·자동화로그는 하지 않는다(PII 없는 최소 카운트성 로그만 남김).
  if (String(body.website || "").trim()) {
    try {
      handleLogAdd_({
        actor: "자체 지원 폼", work: "지원접수 스팸의심 차단",
        detail: "허니팟 필드 채움(요청 무시)", result: "저장 안 함 — 가짜 성공 응답 반환"
      });
    } catch (eHp) {}
    return { ok: true, message: "지원이 접수되었습니다. 감사합니다." };
  }

  var name = String(body.name || "").trim();
  var phone = String(body.phone || "").trim();
  var email = String(body.email || "").trim();
  var position = String(body.position || "").trim();
  var fileName = String(body.fileName || "").trim();
  var fileMimeType = String(body.fileMimeType || "").trim();
  var fileBase64 = String(body.fileBase64 || "");

  if (!name || !phone || !position) {
    return { ok: false, error: "fields_required", message: "이름·연락처·지원 포지션은 필수입니다." };
  }
  if (!fileBase64 || !fileMimeType) {
    return { ok: false, error: "file_required", message: "이력서 파일을 첨부해 주세요." };
  }
  var __fieldVals = { name: name, phone: phone, email: email, position: position };
  for (var __fk in SUBMIT_APP_MAX_FIELD_LEN) {
    var __fv = __fieldVals[__fk] || "";
    if (__fv.length > SUBMIT_APP_MAX_FIELD_LEN[__fk]) {
      return { ok: false, error: "field_too_long", message: __fk + " 항목이 너무 깁니다." };
    }
  }
  var ext = SUBMIT_APP_ALLOWED_MIME_[fileMimeType];
  if (!ext) {
    return { ok: false, error: "file_type_invalid", message: "이력서는 PDF, JPG, PNG 파일만 가능합니다." };
  }

  // 시간당 접수 상한 — CacheService 시간대 버킷 키(폴더 스캔 없이 O(1) 판정, 폴더가 커져도 성능 무관).
  var cache = CacheService.getScriptCache();
  var hourKey = "submitapp_hr_" + Utilities.formatDate(new Date(), "Asia/Seoul", "yyyyMMddHH");
  var hourCount = parseInt(cache.get(hourKey), 10) || 0;
  if (hourCount >= SUBMIT_APP_MAX_PER_HOUR) {
    return { ok: false, error: "rate_limited", message: "지금 접수가 몰려 있습니다. 잠시 후 다시 시도하시거나 이메일(cao@wellperion.com)로 직접 보내주세요." };
  }

  // 파일 디코드 + 실바이트 기준 용량 검사(base64 문자열 길이가 아니라 디코드 후 bytes.length로 판정)
  var bytes;
  try { bytes = Utilities.base64Decode(fileBase64); } catch (eDec) {
    return { ok: false, error: "file_decode_failed", message: "파일을 읽을 수 없습니다. 다시 첨부해 주세요." };
  }
  if (bytes.length === 0) {
    return { ok: false, error: "file_empty", message: "파일이 비어 있습니다." };
  }
  if (bytes.length > SUBMIT_APP_MAX_FILE_BYTES) {
    return { ok: false, error: "file_too_large", message: "파일 용량은 10MB 이하만 가능합니다." };
  }

  // 저장 파일명: 웹지원_<포지션>_<이름>_<타임스탬프>.<ext> — 경로/특수문자 제거로 파일시스템 안전화.
  function __safeSeg(s) { return String(s).replace(/[\\\/:*?"<>|]/g, "").replace(/\s+/g, "").slice(0, 30); }
  var ts = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyyMMdd_HHmmss");
  var savedName = "웹지원_" + __safeSeg(position) + "_" + __safeSeg(name) + "_" + ts + "." + ext;

  var folder;
  try { folder = DriveApp.getFolderById(INTAKE_FOLDER_AUTO_); } catch (eFolder) {
    return { ok: false, error: "folder_unavailable", message: "일시적인 오류입니다. 잠시 후 다시 시도해 주세요." };
  }
  try {
    var blob = Utilities.newBlob(bytes, fileMimeType, savedName);
    folder.createFile(blob);
  } catch (eSave) {
    return { ok: false, error: "save_failed", message: "파일 저장에 실패했습니다. 잠시 후 다시 시도해 주세요." };
  }

  // 시간당 카운터 갱신은 성공 저장 후에만(검증 실패로 반려된 요청은 상한을 소모하지 않음).
  try { cache.put(hourKey, String(hourCount + 1), 3600); } catch (eCache) {}

  // 자동화로그 — PII 최소화: 이름·포지션만 남김(연락처·이메일·원본 파일명은 로그에 남기지 않음).
  try {
    handleLogAdd_({
      actor: "자체 지원 폼",
      work: "지원접수(웹폼)",
      detail: "포지션: " + position + " · 지원자: " + name,
      result: "자동수신 폴더 저장 완료 — 파이프라인 대기(" + savedName + ")"
    });
  } catch (eLog) {}

  return { ok: true, message: "지원이 접수되었습니다. 확인 후 연락드리겠습니다. 감사합니다." };
}

// 개별 DB 조회 — 운영허브의 db:"emp" 호출 호환
// [수정 2026-07-15 A-5] role 파라미터 추가(선택) — emp(현재근무자) 응답에서 admin 전용
// 생년월일·나이 파생을 결정하는 데만 쓰인다(readCurrentSheet_ 참조). 다른 case는 무관·미사용.
function handleReadOne_(dbKey, role) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  switch (dbKey) {
    case "emp":  return readCurrentSheet_(ss, role);
    case "hire": return readSchemaSheet_(ss, SHEET_HIRE, SCHEMAS.hire);
    case "appl": return readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl);
    case "eval": return readSchemaSheet_(ss, SHEET_EVAL, SCHEMAS.eval);
    case "onbo": return readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
    case "exit": return readSchemaSheet_(ss, SHEET_RESIGN, SCHEMAS.resign);
    case "leave": return readSchemaSheet_(ss, SHEET_LEAVE, SCHEMAS.leave);
    case "exitroster": return readExitSheet_(ss);
    case "blacklist": return readSchemaSheet_(ss, SHEET_BLACKLIST, SCHEMAS.blacklist);
    default:     return [];
  }
}

// =====================================================================
// [추가 2026-07-04] 자동화 로그 — CHRO가 스스로 처리한 작업 내역 기록
//   시트: 자동화로그 (없으면 자동 생성, 헤더 1행: 일시·주체·작업·상세·결과)
//   append 전용(맨 아래 추가만) — 행 고정 원칙(인사현황 시트)과는 무관한 신설 탭.
// =====================================================================
// [추가 2026-07-04 r6] at 검증 정규식 — "YYYY-MM-DD HH:MM"(초 생략 가능) 형식만 허용.
var AUTOLOG_AT_RE_ = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$/;

// =====================================================================
// [추가 2026-07-07] 채용 블랙리스트 — 재지원 차단 대상 관리(append 전용, 없으면 자동 생성)
//   탭: 채용블랙리스트 (헤더 1행: No·성명·생년·연락처(뒤4자리)·지원경로·사유·등록일·비고)
//   PII 최소화: 연락처는 뒤 4자리만 저장. 신설 탭이므로 맨아래 append 자유(행 고정 계약 무관).
// =====================================================================
function handleAddBlacklist_(body) {
  var name = String((body && body.name) || "").trim();
  if (!name) return { ok: false, error: "name_required", message: "name(성명)은 필수입니다." };
  var birth  = String((body && body.birth)  || "").trim();
  var phone4 = String((body && body.phone4) || "").trim();
  var source = String((body && body.source) || "").trim();
  var reason = String((body && body.reason) || "").trim();
  var memo   = String((body && body.memo)   || "").trim();

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_BLACKLIST, SCHEMAS.blacklist);

  // No 자동 증가 = 기존 A열 최대 숫자 + 1 (삭제로 인한 공백행에도 안전)
  var lastRow = sh.getLastRow();
  var no = 1;
  if (lastRow >= NEW_DATA_START_ROW) {
    var nums = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, 1).getValues();
    var maxNo = 0;
    for (var i = 0; i < nums.length; i++) {
      var n = parseInt(nums[i][0], 10);
      if (!isNaN(n) && n > maxNo) maxNo = n;
    }
    no = maxNo + 1;
  }

  var today = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd");
  var nr = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nr, 1, 1, SCHEMAS.blacklist.length)
    .setValues([[no, name, birth, phone4, source, reason, today, memo]]);
  return { ok: true, action: "add-blacklist", row: nr, no: no, name: name, 등록일: today };
}

// [추가 2026-07-07] 블랙리스트 제거 — name(첫 일치) 또는 sheetRow 지정. 행 삭제 대신 값만 비움(No 밀림 방지).
function handleRemoveBlacklist_(body) {
  var name = String((body && body.name) || "").trim();
  var sheetRow = parseInt((body && (body.sheetRow || body.row)) || 0, 10);
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_BLACKLIST);
  if (!sh) return { ok: false, error: "sheet_not_found", message: "채용블랙리스트 탭이 없습니다." };
  var last = sh.getLastRow();
  var target = 0;
  if (sheetRow && sheetRow >= NEW_DATA_START_ROW && sheetRow <= last) {
    target = sheetRow;
  } else if (name) {
    var names = sh.getRange(NEW_DATA_START_ROW, 2, Math.max(last - NEW_DATA_START_ROW + 1, 0), 1).getValues();
    for (var i = 0; i < names.length; i++) {
      if (String(names[i][0] || "").trim() === name) { target = NEW_DATA_START_ROW + i; break; }
    }
  }
  if (!target) return { ok: false, error: "not_found", message: "대상을 찾지 못했습니다(name 또는 sheetRow 확인)." };
  sh.getRange(target, 1, 1, SCHEMAS.blacklist.length).clearContent();
  return { ok: true, action: "remove-blacklist", row: target, name: name };
}

// =====================================================================
// [추가 2026-07-20 A-5, 매니저 승인 개선④] 결정대기 큐 — STATE.md 매니저 판단 대기 적체 완화.
//   탭: 결정대기 (없으면 자동 생성, 블랙리스트/명령큐와 동일 append-only 패턴).
//   흐름: decision-add(적재, 상태=pending) → 아침 브리핑이 pending 중 가장 오래 노출 안 된 1건을
//        로테이션 표시(마지막노출일 갱신) → 매니저가 결정하면 decision-done(상태=done, 행 유지).
//   PII 금지 — 요지/옵션JSON/추천안은 텍스트 요약만(생년·연락처 등 상세는 적재자가 넣지 않을 것).
// =====================================================================
function handleDecisionAdd_(body) {
  var summary = String((body && (body.summary || body["요지"])) || "").trim();
  if (!summary) return { ok: false, error: "summary_required", message: "summary(요지)는 필수입니다." };
  var optionsRaw = (body && (body.options || body["옵션"])) || [];
  var options = [];
  if (Array.isArray(optionsRaw)) {
    options = optionsRaw.map(function (o) { return String(o || "").trim(); }).filter(function (o) { return o; });
  } else if (typeof optionsRaw === "string" && optionsRaw.trim()) {
    options = [optionsRaw.trim()];
  }
  var recommendation = String((body && (body.recommendation || body["추천안"])) || "").trim();

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_DECISION, SCHEMAS.decision);

  // id 자동 증가 = 기존 A열 최대값 + 1 (블랙리스트/명령큐와 동일 패턴 — 공백행에도 안전)
  var lastRow = sh.getLastRow();
  var id = 1;
  if (lastRow >= NEW_DATA_START_ROW) {
    var idCol = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, 1).getValues();
    var maxId = 0;
    for (var i = 0; i < idCol.length; i++) {
      var n = parseInt(idCol[i][0], 10);
      if (!isNaN(n) && n > maxId) maxId = n;
    }
    id = maxId + 1;
  }

  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  var nr = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nr, 1, 1, SCHEMAS.decision.length)
    .setValues([[id, now, summary, JSON.stringify(options), recommendation, "pending", "", ""]]);
  return { ok: true, action: "decision-add", row: nr, id: id, 등록일시: now };
}

// status(body.status) 미지정 시 전체 반환(pending/done 혼합) — 목록 화면·매니저 조회용.
function handleDecisionList_(body) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var rows = readSchemaSheet_(ss, SHEET_DECISION, SCHEMAS.decision);
  var status = String((body && body.status) || "").trim();
  if (status) rows = rows.filter(function (r) { return String(r["상태"] || "").trim() === status; });
  return { ok: true, results: rows };
}

// id(우선) 또는 sheetRow로 대상 지정. 행 삭제 없이 상태 칸만 done으로 갱신(결정대기 큐 계약).
function handleDecisionDone_(body) {
  var id = parseInt((body && body.id) || 0, 10);
  var sheetRow = parseInt((body && (body.sheetRow || body.row)) || 0, 10);
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_DECISION);
  if (!sh) return { ok: false, error: "sheet_not_found", message: "결정대기 탭이 없습니다." };
  var last = sh.getLastRow();
  var target = 0;
  if (sheetRow && sheetRow >= NEW_DATA_START_ROW && sheetRow <= last) {
    target = sheetRow;
  } else if (id) {
    var ids = sh.getRange(NEW_DATA_START_ROW, 1, Math.max(last - NEW_DATA_START_ROW + 1, 0), 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (parseInt(ids[i][0], 10) === id) { target = NEW_DATA_START_ROW + i; break; }
    }
  }
  if (!target) return { ok: false, error: "not_found", message: "대상을 찾지 못했습니다(id 또는 sheetRow 확인)." };
  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  sh.getRange(target, 6).setValue("done");   // 상태
  sh.getRange(target, 8).setValue(now);      // 완료일시
  return { ok: true, action: "decision-done", row: target, id: id, 완료일시: now };
}

// =====================================================================
// [추가 2026-07-08] 명령 큐 — 오피스 터미널 ↔ CHRO 세션 간 비동기 명령 전달
//   탭: 명령큐 (헤더 1행: id·시각·명령·상태·결과·응답시각, 없으면 자동 생성)
//   append-only 신설 탭 — 행 고정 계약(인사현황 시트) 무관.
//   흐름: cmd-push(등록, 상태=pending) → cmd-pull(pending 전부 회수 + delivered 전환)
//        → cmd-result(결과·응답시각 기록, 상태=done) → cmd-status(단건 상태/결과 조회)
//   adminPassword 검증은 handleRequest_ 상단 공통 게이트(role!=="admin" → 403)에서 이미 처리됨.
// =====================================================================
function handleCmdPush_(body) {
  var text = String((body && body.text) || "").trim();
  if (!text) return { ok: false, error: "text_required", message: "text는 필수입니다." };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_CMDQUEUE, SCHEMAS.cmdqueue);

  // id 자동 증가 = 기존 A열(id) 최대값 + 1 (블랙리스트 No 패턴과 동일 — 공백행에도 안전)
  var lastRow = sh.getLastRow();
  var id = 1;
  if (lastRow >= NEW_DATA_START_ROW) {
    var idCol = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, 1).getValues();
    var maxId = 0;
    for (var i = 0; i < idCol.length; i++) {
      var n = parseInt(idCol[i][0], 10);
      if (!isNaN(n) && n > maxId) maxId = n;
    }
    id = maxId + 1;
  }

  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  var nr = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nr, 1, 1, SCHEMAS.cmdqueue.length).setValues([[id, now, text, "pending", "", ""]]);
  return { ok: true, id: id };
}

// [추가 2026-07-10 2차] office-cmd-push — 비밀번호 없는 공개 접수(HR office CMD 입력창 전용).
//   handleCmdPush_와 동일하게 "명령큐" 탭에 append(pending)만 하되, 서버측 스팸 가드 3종을 追加:
//   ①대기(pending) 건수 상한 ②시간당 접수 건수 상한(상태 무관) ③텍스트 길이 상한.
//   회수(cmd-pull)·결과기록(cmd-result)·실제 실행은 이 함수가 건드리지 않음(admin 전용 그대로).
function handleOfficeCmdPush_(body) {
  var text = String((body && body.text) || "").trim();
  if (!text) return { ok: false, error: "text_required", message: "text는 필수입니다." };
  if (text.length > OFFICE_CMD_MAX_LEN) {
    return { ok: false, error: "text_too_long", message: "명령은 " + OFFICE_CMD_MAX_LEN + "자 이내로 입력해 주세요." };
  }

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_CMDQUEUE, SCHEMAS.cmdqueue);

  var lastRow = sh.getLastRow();
  var maxId = 0, pendingCount = 0, hourCount = 0;
  var nowMs = Date.now();
  if (lastRow >= NEW_DATA_START_ROW) {
    // id·시각·상태 4열만(id=1,시각=2,상태=4) — 대량이라도 가벼운 범위 읽기
    var rows = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, 4).getValues();
    for (var i = 0; i < rows.length; i++) {
      var rid = parseInt(rows[i][0], 10);
      if (!isNaN(rid) && rid > maxId) maxId = rid;
      var status = String(rows[i][3] || "");
      if (status === "pending") pendingCount++;
      var tsRaw = rows[i][1], tsMs = NaN;
      if (tsRaw instanceof Date) {
        tsMs = tsRaw.getTime();
      } else {
        var tm = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(tsRaw || ""));
        if (tm) tsMs = new Date(tm[1] + "-" + tm[2] + "-" + tm[3] + "T" + tm[4] + ":" + tm[5] + ":00+09:00").getTime();
      }
      if (!isNaN(tsMs) && (nowMs - tsMs) <= 3600000) hourCount++;
    }
  }

  if (pendingCount >= OFFICE_CMD_MAX_PENDING) {
    return { ok: false, error: "queue_full", message: "대기 중인 명령이 이미 " + OFFICE_CMD_MAX_PENDING + "건입니다. 처리 후 다시 시도해 주세요." };
  }
  if (hourCount >= OFFICE_CMD_MAX_PER_HOUR) {
    return { ok: false, error: "rate_limited", message: "시간당 접수 한도(" + OFFICE_CMD_MAX_PER_HOUR + "건)를 초과했습니다. 잠시 후 다시 시도해 주세요." };
  }

  var id = maxId + 1;
  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  var nr = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nr, 1, 1, SCHEMAS.cmdqueue.length).setValues([[id, now, text, "pending", "", ""]]);
  return { ok: true, id: id, position: pendingCount + 1 };
}

function handleCmdPull_(body) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_CMDQUEUE, SCHEMAS.cmdqueue);
  var last = sh.getLastRow();
  if (last < NEW_DATA_START_ROW) return { ok: true, commands: [] };

  var rng = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, SCHEMAS.cmdqueue.length);
  var values = rng.getValues();
  var commands = [];
  for (var i = 0; i < values.length; i++) {
    var status = String(values[i][3] || "").trim();
    if (status === "pending") {
      commands.push({ id: values[i][0], text: values[i][2], ts: values[i][1] });
      values[i][3] = "delivered";
    }
  }
  if (commands.length > 0) rng.setValues(values); // pending → delivered 일괄 반영
  return { ok: true, commands: commands };
}

function handleCmdResult_(body) {
  var id = parseInt((body && body.id), 10);
  if (!id) return { ok: false, error: "id_required", message: "id는 필수입니다." };
  var result = String((body && body.result) || "").slice(0, 1000); // ≤1000자

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_CMDQUEUE);
  if (!sh) return { ok: false, error: "not_found", message: "id를 찾지 못했습니다(명령큐 탭 없음)." };
  var last = sh.getLastRow();
  if (last < NEW_DATA_START_ROW) return { ok: false, error: "not_found", message: "id를 찾지 못했습니다." };

  var ids = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, 1).getValues();
  var target = 0;
  for (var i = 0; i < ids.length; i++) {
    if (parseInt(ids[i][0], 10) === id) { target = NEW_DATA_START_ROW + i; break; }
  }
  if (!target) return { ok: false, error: "not_found", message: "id를 찾지 못했습니다." };

  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  sh.getRange(target, 4, 1, 3).setValues([["done", result, now]]); // 상태·결과·응답시각(4~6열)
  return { ok: true };
}

function handleCmdStatus_(body) {
  var id = parseInt((body && body.id), 10);
  if (!id) return { ok: false, error: "id_required", message: "id는 필수입니다." };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_CMDQUEUE);
  if (!sh) return { ok: false, error: "not_found", message: "id를 찾지 못했습니다(명령큐 탭 없음)." };
  var last = sh.getLastRow();
  if (last < NEW_DATA_START_ROW) return { ok: false, error: "not_found", message: "id를 찾지 못했습니다." };

  var values = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, SCHEMAS.cmdqueue.length).getValues();
  for (var i = 0; i < values.length; i++) {
    if (parseInt(values[i][0], 10) === id) {
      var out = { ok: true, status: String(values[i][3] || "") };
      if (values[i][4]) out.result = values[i][4];
      return out;
    }
  }
  return { ok: false, error: "not_found", message: "id를 찾지 못했습니다." };
}

function handleLogAdd_(body) {
  var actor  = String((body && body.actor)  || "").trim();
  var work   = String((body && body.work)   || "").trim();
  var detail = String((body && body.detail) || "").trim();
  var result = String((body && body.result) || "").trim();
  var atRaw  = String((body && body.at) || "").trim();
  if (!actor || !work) return { ok: false, error: "actor_work_required", message: "actor·work은 필수입니다." };

  var now;
  if (atRaw) {
    if (!AUTOLOG_AT_RE_.test(atRaw)) {
      return { ok: false, error: "at_invalid", message: "at은 'YYYY-MM-DD HH:MM' 형식이어야 합니다." };
    }
    now = atRaw;
  } else {
    now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  }

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_AUTOLOG, SCHEMAS.autolog);
  var nr = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nr, 1, 1, SCHEMAS.autolog.length).setValues([[now, actor, work, detail, result]]);
  return { ok: true, action: "log-add", row: nr, timestamp: now };
}

// =====================================================================
// [추가 2026-07-04 r6] LOG-ADD-BULK — 여러 행을 한 번에 자동화로그 맨아래 append (관리자 전용)
//   최대 300행/호출. 각 행은 log-add와 동일한 필드(at·actor·work·detail·result), at 없으면
//   호출 시각(모든 행 공통) 사용. 행 하나라도 actor·work 누락/at 형식 오류면 전체 거부(부분 반영 없음).
// =====================================================================
function handleLogAddBulk_(body) {
  var rows = (body && body.rows) || [];
  if (!Array.isArray(rows) || rows.length === 0) {
    return { ok: false, error: "rows_required", message: "rows 배열이 필요합니다." };
  }
  if (rows.length > 300) {
    return { ok: false, error: "rows_too_many", message: "한 번에 최대 300행까지 가능합니다. (요청: " + rows.length + "행)" };
  }

  var nowDefault = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i] || {};
    var actor  = String(r.actor  || "").trim();
    var work   = String(r.work   || "").trim();
    var detail = String(r.detail || "").trim();
    var result = String(r.result || "").trim();
    var atRaw  = String(r.at || "").trim();
    if (!actor || !work) {
      return { ok: false, error: "actor_work_required", message: (i + 1) + "번째 행: actor·work은 필수입니다." };
    }
    var at;
    if (atRaw) {
      if (!AUTOLOG_AT_RE_.test(atRaw)) {
        return { ok: false, error: "at_invalid", message: (i + 1) + "번째 행: at은 'YYYY-MM-DD HH:MM' 형식이어야 합니다." };
      }
      at = atRaw;
    } else {
      at = nowDefault;
    }
    out.push([at, actor, work, detail, result]);
  }

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_AUTOLOG, SCHEMAS.autolog);
  var startRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(startRow, 1, out.length, SCHEMAS.autolog.length).setValues(out);
  return { ok: true, action: "log-add-bulk", added: out.length, startRow: startRow };
}

// =====================================================================
// [추가 2026-07-04 r6] AUTOLOG-RESET — 자동화로그 "탭만" 내용 삭제 후 헤더 재생성 (관리자 전용)
//   confirm 문구가 정확히 "자동화로그"와 일치할 때만 수행 — 오발동 방지. 다른 시트는 절대 건드리지 않음.
// =====================================================================
function handleAutologReset_(body) {
  var confirm = String((body && body.confirm) || "").trim();
  if (confirm !== "자동화로그") {
    return { ok: false, error: "confirm_mismatch", message: "확인 문구('자동화로그')가 일치하지 않아 초기화를 거부합니다." };
  }

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_AUTOLOG);
  if (sh) {
    sh.clearContents();
  } else {
    sh = ss.insertSheet(SHEET_AUTOLOG);
  }
  sh.getRange(NEW_HEADER_ROW, 1, 1, SCHEMAS.autolog.length).setValues([SCHEMAS.autolog]);
  sh.getRange(NEW_HEADER_ROW, 1, 1, SCHEMAS.autolog.length).setFontWeight("bold").setBackground("#f0f0f0");
  sh.setFrozenRows(NEW_HEADER_ROW);
  return { ok: true, action: "autolog-reset", msg: "자동화로그 탭 초기화 완료(헤더 재생성)" };
}

// =====================================================================
// [추가 2026-07-10] LOG-FIX — 자동화로그 기존 행의 주체/작업/상세/결과 선택 정정 (관리자 전용)
//   용도 = 인코딩 유실(U+FFFD) 복구 등 사후 로그 정정 한정. 자동화로그 탭 외 어떤 시트도 건드리지 않음.
//   append 계약(다른 autolog 함수)과 별개 — 이 액션만 기존 행을 setValues로 덮어씀.
//   sheetRow 필수, actor/work/detail/result는 제공(공백 아님)된 필드만 갱신 — 미전달 필드는 원본 보존.
// =====================================================================
function handleLogFix_(body) {
  var sheetRow = parseInt((body && (body.sheetRow || body.row)) || 0, 10);
  if (!sheetRow || sheetRow < NEW_DATA_START_ROW) {
    return { ok: false, error: "sheetRow_required", message: "sheetRow(2 이상)가 필요합니다." };
  }

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_AUTOLOG);
  if (!sh) return { ok: false, error: "sheet_not_found", message: "자동화로그 탭이 없습니다." };
  var last = sh.getLastRow();
  if (sheetRow > last) {
    return { ok: false, error: "row_out_of_range", message: "sheetRow(" + sheetRow + ")가 시트 범위(최대 " + last + ")를 벗어났습니다." };
  }

  var hasActor  = body && body.actor  !== undefined && body.actor  !== null && String(body.actor).trim()  !== "";
  var hasWork   = body && body.work   !== undefined && body.work   !== null && String(body.work).trim()   !== "";
  var hasDetail = body && body.detail !== undefined && body.detail !== null && String(body.detail).trim() !== "";
  var hasResult = body && body.result !== undefined && body.result !== null && String(body.result).trim() !== "";
  if (!hasActor && !hasWork && !hasDetail && !hasResult) {
    return { ok: false, error: "no_fields", message: "actor/work/detail/result 중 최소 1개는 필요합니다." };
  }

  var rowRange = sh.getRange(sheetRow, 1, 1, SCHEMAS.autolog.length); // 일시·주체·작업·상세·결과
  var vals = rowRange.getValues()[0];
  var before = { 일시: vals[0], 주체: vals[1], 작업: vals[2], 상세: vals[3], 결과: vals[4] };

  if (hasActor)  vals[1] = String(body.actor).trim();
  if (hasWork)   vals[2] = String(body.work).trim();
  if (hasDetail) vals[3] = String(body.detail).trim();
  if (hasResult) vals[4] = String(body.result).trim();

  rowRange.setValues([vals]);
  return {
    ok: true, action: "log-fix", row: sheetRow,
    before: before,
    after: { 일시: vals[0], 주체: vals[1], 작업: vals[2], 상세: vals[3], 결과: vals[4] }
  };
}

// db:"autolog" 조회 전용 — 최신순 정렬 후 offset·limit 적용 (기본 limit 200, offset 0)
function handleReadAutolog_(limit, offset) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var rows = readSchemaSheet_(ss, SHEET_AUTOLOG, SCHEMAS.autolog);
  rows.reverse(); // append 전용 → 시트상 마지막 행이 최신 → 뒤집으면 최신순
  if (offset && offset > 0) rows = rows.slice(offset);
  if (limit && rows.length > limit) rows = rows.slice(0, limit);
  return rows;
}

// =====================================================================
// [추가 2026-07-05] 이니셜 마스킹 — autolog-list(공개) 응답의 "작업"·"상세" 텍스트에서
//   임직원(현재근무자)·지원자·퇴사자 명부의 실명을 성+○○(2자 성명은 성+○)로 치환한다.
//   관리자용 db:"autolog"(handleReadAutolog_)는 이 마스킹을 타지 않는다(무마스킹 유지).
//   기존 읽기 유틸(readCurrentSheet_/readSchemaSheet_/readExitSheet_)만 재사용 — 신규 시트 접근 없음.
// =====================================================================
// 알려진 예외 — 로그 원문에 성 없이(또는 명부 표기와 다르게) 등장해 표준 길이규칙으로는
// 안 맞는 특수 토큰. 항상 "앞 1자+○○"로 강제 치환한다(명부 존재 여부와 무관).
var MASK_NAME_EXCEPTIONS_ = { "치원": "치○○" };

// [2026-07-05 감사 NO-GO L1/L2 대응] 수동 추가 마스킹 목록 — 라이브 명부(emp/appl/exitroster)에
// 표준 표기로 없거나(라이브 미재직 실측 등) 확인이 어려운 인물을 이중 안전 차원에서 강제 포함한다.
// 표준 성+○○/성+○ 규칙을 그대로 적용(exceptions와 달리 강제 축약 아님).
//   - "한두희": 라이브 emp 부재 실측 확인 — 휴무표에만 등장하는 인물.
//   - "양상규": 감사 L1 — emp 로스터엔 "양상규-딸"로만 존재, 로그엔 맨이름으로 등장(아래 표기변형
//     보정으로도 커버되나 이중 안전 차원에서 명시 추가).
var MASK_MANUAL_NAMES_ = ["한두희", "양상규"];

// [2026-07-05 페일세이프] 마스킹 명부(emp+appl+exitroster+예외+수동목록) 총원이 이 값 미만이면
// 시트 소실·읽기 실패로 명부가 비정상 축소된 것으로 간주 — 부분 마스킹으로 새지 않도록 공개
// 응답 자체를 거부한다(collectMaskNameList_에서 throw → handleRequest_ 최상위 catch → ok:false).
var MASK_ROSTER_MIN_ = 50;

// 이름 1개 → 마스킹된 표기 (2자=성+○, 3자 이상=성+○○ 고정). 예외 토큰은 항상 1자+○○.
function maskNameOf_(name) {
  if (MASK_NAME_EXCEPTIONS_.hasOwnProperty(name)) return MASK_NAME_EXCEPTIONS_[name];
  var first = name.charAt(0);
  return name.length <= 2 ? (first + "○") : (first + "○○");
}

// 임직원·지원자·퇴사자 명부 전수 + 알려진 예외 토큰 + 수동 추가 목록을 모아, 긴 이름부터
// 치환되도록 길이 내림차순 정렬한 목록을 반환한다(짧은 이름이 긴 이름의 부분문자열을 먼저
// 깨는 것 방지). 명부 표기에 하이픈·공백이 섞인 변형(예: "양상규-딸")은 전체 토큰뿐 아니라
// 하이픈/공백 앞의 기본 토큰("양상규")도 함께 등록한다 — 로그 원문엔 접미사 없이 맨이름만
// 등장하는 경우([2026-07-05 감사 NO-GO L1])가 있기 때문.
function collectMaskNameList_(ss) {
  var seen = {};
  function add(n) {
    n = String(n || "").trim();
    if (n.length >= 2) seen[n] = true;
    var base = n.match(/^([^\s-]+)[\s-]/); // "이름-관계"/"이름 관계" 표기의 기본 토큰
    if (base && base[1] && base[1].length >= 2) seen[base[1]] = true;
  }
  var emp = readCurrentSheet_(ss);
  for (var i = 0; i < emp.length; i++) add(emp[i]["성명"]);
  var appl = readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl);
  for (var j = 0; j < appl.length; j++) add(appl[j]["지원자명"]);
  var exitroster = readExitSheet_(ss);
  for (var k = 0; k < exitroster.length; k++) add(exitroster[k]["성명"] || exitroster[k]["이름"]);
  for (var ex in MASK_NAME_EXCEPTIONS_) { if (MASK_NAME_EXCEPTIONS_.hasOwnProperty(ex)) seen[ex] = true; }
  for (var mi = 0; mi < MASK_MANUAL_NAMES_.length; mi++) add(MASK_MANUAL_NAMES_[mi]);

  var list = [];
  for (var nm in seen) { if (seen.hasOwnProperty(nm)) list.push(nm); }
  list.sort(function (a, b) { return b.length - a.length; }); // 긴 이름부터

  if (list.length < MASK_ROSTER_MIN_) {
    throw new Error("마스킹 명부 부족(" + list.length + "명 < " + MASK_ROSTER_MIN_ + "명) — 명부 소실 위험으로 공개 응답을 거부합니다.");
  }
  return list;
}

// 텍스트 1개에서 nameList 각 이름을 치환(부분일치·전역). 명부 밖 텍스트는 그대로 반환.
function maskText_(text, nameList) {
  if (!text) return text;
  var s = String(text);
  for (var i = 0; i < nameList.length; i++) {
    var nm = nameList[i];
    if (s.indexOf(nm) === -1) continue;
    s = s.split(nm).join(maskNameOf_(nm));
  }
  return s;
}

// autolog 행 배열(공개용)에 마스킹 적용 — "작업"·"상세"만 치환, "일시"·"주체"·"결과"는 그대로.
function maskAutologRowsPublic_(rows, ss) {
  var nameList = collectMaskNameList_(ss);
  return rows.map(function (r) {
    return {
      "일시": r["일시"] || "",
      "주체": r["주체"] || "",
      "작업": maskText_(r["작업"] || "", nameList),
      "상세": maskText_(r["상세"] || "", nameList),
      "결과": r["결과"] || ""
    };
  });
}

// =====================================================================
// [추가 2026-07-05] autolog-list — 자동화 로그 "공개" 열람 전용(비밀번호 불필요)
//   자동화로그 탭만 읽는다(다른 시트 접근 없음). 반환 필드는 아래 5개로 명시적 화이트리스트
//   처리 — 시트에 컬럼이 추가되더라도 여기서 걸러지므로 의도치 않은 필드 노출이 없다.
//   total(전체 건수)을 함께 내려줘 프런트가 "총 N건" 표시·이어받기(offset) 종료 시점을 판단할 수 있게 한다.
//   [변경 2026-07-05] work·detail은 이니셜 마스킹(maskAutologRowsPublic_) 적용 후 반환.
// =====================================================================
function handleAutologListPublic_(limit, offset) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var rows = readSchemaSheet_(ss, SHEET_AUTOLOG, SCHEMAS.autolog);
  rows.reverse(); // 최신순
  var total = rows.length;
  var sliced = (offset || offset === 0) ? rows.slice(offset, offset + limit) : rows.slice(0, limit);
  var out = maskAutologRowsPublic_(sliced, ss);
  return { ok: true, results: out, count: out.length, total: total, limit: limit, offset: offset };
}

// =====================================================================
// [추가 2026-07-10] office-autolog — HR office 개방 개편 전용 "공개" 열람(비밀번호 불필요, 실명 무마스킹).
//   자동화로그 탭만 읽는다(다른 시트 접근 없음). 반환 필드는 일시·주체·작업·결과 4개로 명시적 화이트리스트
//   처리 — "상세"는 애초에 내려주지 않는다(office.html은 이 필드를 쓰지 않고, PII 위험도가 가장 높은
//   자유텍스트라 화이트리스트에서 제외하는 편이 안전).
// =====================================================================
function handleOfficeAutologPublic_(limit, offset) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var rows = readSchemaSheet_(ss, SHEET_AUTOLOG, SCHEMAS.autolog);
  rows.reverse(); // 최신순
  var total = rows.length;
  var sliced = (offset || offset === 0) ? rows.slice(offset, offset + limit) : rows.slice(0, limit);
  var out = sliced.map(function (r) {
    return { "일시": r["일시"] || "", "주체": r["주체"] || "", "작업": r["작업"] || "", "결과": r["결과"] || "", "_sheet_row": r["_sheet_row"] || 0 };
  });
  return { ok: true, results: out, count: out.length, total: total, limit: limit, offset: offset };
}

function checkPassword_(pwd) {
  if (pwd === ADMIN_PASSWORD) return "admin";
  if (pwd === ACCESS_PASSWORD) return "viewer";
  if (pwd === CMD_PASSWORD) return "cmd";
  return null;
}

function requireAdmin_(role) {
  if (role !== "admin") {
    throw new Error("관리자 권한 필요");
  }
}
function requireCmdOrAdmin_(role) {
  if (role !== "admin" && role !== "cmd") {
    throw new Error("권한 필요");
  }
}

// =====================================================================
// [추가 2026-07-13 A-5] 비관리자(viewer/cmd) 응답 PII 마스킹 — 서버측 최종 방어선.
//   배경: 시트 헤더행 오염(6/24 지적)으로 컬럼명 기반 필드 탐지가 불안정 → 값의 "형식"만으로
//   주민등록번호·연락처를 판별해 마스킹한다(컬럼명·필드키 의존 없음 → 헤더가 뭐라 적혀 있든 안전).
//   admin 응답에는 절대 적용하지 않는다(인사카드·평가지·생년/나이 표시 등 관리자 화면 회귀 방지).
//   RRN: "YYMMDD-1234567" 형식(총 13자리, 구분자 앞뒤 숫자와 안 붙어야 함, 성별코드 자리 1~8).
//   전화: "01X-XXXX-XXXX" 형식(이동통신 접두 01[016789] 앵커 — 기존 verifySelfPin_과 동일 앵커 재사용).
//   [2026-07-13 라운드트립 실측 추가] 현재근무자 시트의 실제 "주민번호" 열은 헤더 오염과 별개로
//   축약형(생년월일+성별코드 7자리, 뒤 6자리 일련번호 없이 "YYMMDD-N"만 저장)인 셀이 다수 확인됨.
//   13자리 전체 패턴만으론 이 축약형을 놓치므로, 셀 값 전체가 이 축약형과 정확히 일치할 때만
//   추가로 마스킹한다(부분일치 아닌 전체일치 — 자유텍스트 메모 등에서의 과탐 방지 안전판).
var PII_RRN_RE_   = /(?<!\d)\d{6}[-.\s]?[1-8]\d{6}(?!\d)/g;
var PII_RRN_PARTIAL_WHOLE_RE_ = /^\d{6}[-.\s]?[1-8]$/;
var PII_PHONE_RE_ = /(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)/g;
// [추가 2026-07-13 A-5 r2] 객체 "키" 오염 방어용 — 값 스캔용 정규식(위 3종)은 문자열 중간에서
// 패턴을 찾도록 lookbehind/lookahead를 쓰지만, 키는 헤더행 오염으로 "그 값 자체가 키가 된" 경우라
// 셀 전체일치(whole-match, ^...$)로만 판정한다. 정상 컬럼명(이름/부서 등)은 이 형식과 절대 일치하지
// 않으므로 과탐 없음 — 축약형 RRN은 기존 PII_RRN_PARTIAL_WHOLE_RE_ 재사용.
var PII_RRN_FULL_KEY_RE_   = /^\d{6}[-.\s]?[1-8]\d{6}$/;
var PII_PHONE_KEY_RE_ = /^01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}$/;

// [추가 2026-07-14 A-5] emp 응답용 "생일 월일 안전 파생" — 주민번호 앞자리(YYMMDD-성별)에서
// 월(MM)·일(DD)만 뽑아 새 필드 bday="MM-DD"로 붙인다. 연도(YY)·성별코드(1~4)는 응답에
// 절대 포함하지 않는다(나이 역산 불가가 계약). 매니저 지시로 성별코드는 1~4만 인정
// (기존 마스킹 정규식은 외국인등록 5~8도 포함하지만, 생일 파생은 1~4로 범위를 좁힘).
// 전체형(13자리: YYMMDD-[1-4]XXXXXX)과 축약형(7자리: YYMMDD-[1-4] 단독) 둘 다 지원.
// 월 01~12·일 01~31 범위 밖이거나 매치 실패면 null 반환(bday 필드 자체를 안 붙임).
var BDAY_FULL_RE_    = /(?<!\d)(\d{2})(\d{2})(\d{2})[-.\s]?[1-4]\d{6}(?!\d)/;
var BDAY_PARTIAL_RE_ = /^(\d{2})(\d{2})(\d{2})[-.\s]?[1-4]$/;
// [폐기 2026-07-14 A-7] ⚠ 더 이상 호출되지 않음 — emp bday 소스를 '주민번호 앞자리' →
//   '생일' 열(readCurrentSheet_ row[8])로 교체함. 참고용으로만 남겨둠(완전 제거는 배포 감사 시 결정).
function deriveBdayFromValue_(v) {
  if (typeof v !== "string" || !v) return null;
  var s = v.trim();
  var m = BDAY_PARTIAL_RE_.exec(s);
  if (!m) m = BDAY_FULL_RE_.exec(s);
  if (!m) return null;
  var mm = parseInt(m[2], 10);
  var dd = parseInt(m[3], 10);
  if (mm < 1 || mm > 12) return null;
  if (dd < 1 || dd > 31) return null;
  var mm2 = (mm < 10 ? "0" : "") + mm;
  var dd2 = (dd < 10 ? "0" : "") + dd;
  return mm2 + "-" + dd2;
}

function maskRrnMatch_(m) {
  var d = String(m).replace(/[^0-9]/g, "");
  if (d.length !== 13) return m; // 형식 불일치 시 원문 보존(과탐 방지 안전판)
  return d.substring(0, 6) + "-*******";
}
function maskPhoneMatch_(m) {
  var d = String(m).replace(/[^0-9]/g, "");
  if (d.length < 10) return m;
  return d.substring(0, 3) + "-****-" + d.substring(d.length - 4);
}
function maskPiiString_(s) {
  if (typeof s !== "string" || !s) return s;
  if (PII_RRN_PARTIAL_WHOLE_RE_.test(s.trim())) return "*******"; // 축약형 주민번호(셀 전체 일치) 완전마스킹
  return s.replace(PII_RRN_RE_, maskRrnMatch_).replace(PII_PHONE_RE_, maskPhoneMatch_);
}
// [추가 2026-07-13 A-5 r2 — A-6 @52 감사 발견 보강] 오염 헤더가 파싱된 행 객체의 "키" 이름으로
// 승격된 경우(예: emp 시트 헤더행 오염)를 잡는다. 값(value) 마스킹과 달리 키는 셀 전체일치일 때만
// 오염으로 간주 — 정상 컬럼명(이름/부서/연락처 라벨 등)은 이 3형식과 정확히 일치할 수 없어 과탐 없음.
function isPiiContaminatedKey_(k) {
  var s = String(k === null || k === undefined ? "" : k).trim();
  if (!s) return false;
  return PII_RRN_PARTIAL_WHOLE_RE_.test(s) || PII_RRN_FULL_KEY_RE_.test(s) || PII_PHONE_KEY_RE_.test(s);
}
function maskPiiKey_(k) {
  var s = String(k === null || k === undefined ? "" : k).trim();
  if (PII_RRN_PARTIAL_WHOLE_RE_.test(s)) return "*******";
  if (PII_RRN_FULL_KEY_RE_.test(s)) return maskRrnMatch_(s);
  if (PII_PHONE_KEY_RE_.test(s)) return maskPhoneMatch_(s);
  return k; // 오염 아님 — 원문 키 그대로(정상 컬럼명 보존)
}
// 응답 객체(배열/중첩 객체 포함)를 재귀 스캔해 문자열 값만 마스킹. 숫자·불리언·null 등은 그대로 통과.
// 키(key)도 오염 형식(주민번호/연락처 셀 전체일치)과 일치하면 동일 규칙으로 마스킹한다(값과 별개 사각 보강).
function maskPiiForViewer_(data) {
  if (data === null || data === undefined) return data;
  if (typeof data === "string") return maskPiiString_(data);
  if (data instanceof Date) return data;
  if (Array.isArray(data)) {
    var arr = new Array(data.length);
    for (var i = 0; i < data.length; i++) arr[i] = maskPiiForViewer_(data[i]);
    return arr;
  }
  if (typeof data === "object") {
    var out = {};
    for (var k in data) {
      if (!Object.prototype.hasOwnProperty.call(data, k)) continue;
      var safeKey = isPiiContaminatedKey_(k) ? maskPiiKey_(k) : k;
      // 마스킹된 키가 기존 키와 충돌하면(극히 드묾) 값 유실 방지용 접미사로 구분
      if (safeKey !== k && Object.prototype.hasOwnProperty.call(out, safeKey)) {
        var n = 2;
        while (Object.prototype.hasOwnProperty.call(out, safeKey + "_" + n)) n++;
        safeKey = safeKey + "_" + n;
      }
      out[safeKey] = maskPiiForViewer_(data[k]);
    }
    return out;
  }
  return data;
}

// =====================================================================
// [긴급 추가 2026-07-14 A-5] emp(현재근무자) 응답 — role 무관 무조건 주민번호 마스킹.
//   배경(A-6 감사 drafts\A6_주민번호노출_긴급.md 확정): 현재근무자 시트 헤더행(5/6행)의
//   한 열이 라벨 대신 실제 주민번호 문자열로 덮여 있어, readCurrentSheet_가 헤더를 키로
//   승격하는 구조상 그 열의 "키"와 "값"이 모두 재직자 63명 실제 주민번호가 되어 응답에 실림.
//   위의 maskPiiForViewer_는 role !== "admin"일 때만 적용되는데, 운영허브는 정상 읽기도
//   관리자 비밀번호(wellperion!@1202)로 호출해 role === "admin"이 되므로 기존 마스킹이
//   전혀 걸리지 않았던 것이 실노출 원인. emp 데이터는 인사카드 표시에 주민번호 원문이
//   필요 없으므로 role 무관(admin 포함) 무조건 마스킹한다. ⚠️ 시트 자체는 절대 미변경 —
//   readCurrentSheet_가 만든 응답 배열만 반환 직전에 스캔·치환(비파괴, 행고정 #13 무관).
// [수정 2026-07-15 A-5 — 임직원탭 admin PII 표시 회귀 수정] 위 긴급 지혈(2026-07-14)이 오염된
//   헤더 키(주민번호/전화번호 형태로 승격된 컬럼)를 통째로 드롭하면서, 그 컬럼이 실제로 담고 있던
//   "연락처"·"생년월일" 데이터까지 admin 응답에서 함께 사라졌다(7/13 "admin엔 마스킹 미적용" 계약을
//   7/14 지혈이 의도치 않게 깨뜨린 회귀 — A-6 지적 없이 A-5 자체 재점검으로 발견, 2026-07-15).
//   ⚠️ 주민번호 원문(13자리 전체·7자리 축약형 모두)은 이 함수를 나가는 어떤 role의 응답에도 여전히
//   절대 포함하지 않는다(무변경) — 다만 그 값에서 "생년월일"(YYYY-MM-DD)·"나이"(정수)만 role==="admin"
//   에 한해 서버측에서 파생해 별도 필드로 되돌려준다(원본 뒷자리 일련번호는 입력조차 받지 않으므로
//   응답에 섞일 수 없음). 전화번호 형태로 오염된 키는 값(이 행의 실제 연락처)을 role 무관 "연락처"
//   필드로 구제한다 — viewer 마스킹은 기존과 동일하게 이 함수 밖 maskPiiForViewer_가 계속 처리.
function maskEmpRrnUnconditional_(rows, role) {
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var safeRow = {};
    var __phoneRescue = null, __dobRescue = null;
    // [변경 2026-07-14 A-7] bday 소스 교체 — readCurrentSheet_가 '생일' 열(I열=index 8)에서
    //   이미 obj.bday("MM-DD")로 파생해 보낸다. 여기서는 주민번호 앞자리 파생(deriveBdayFromValue_)을
    //   폐기하고, 아래 키 복사 루프가 기존 obj.bday를 그대로 보존한다(연도·성별코드는 원천적으로 없음).
    for (var k in row) {
      if (!Object.prototype.hasOwnProperty.call(row, k)) continue;
      var v = row[k];
      // 키 자체가 주민번호·전화번호 문자열로 오염된 경우 — 원본 키+값은 응답에서 여전히 통째 드롭.
      // 다만 그 열의 실제 의미가 판별되면(전화번호 형태→연락처 / 주민번호 형태→admin 전용 생년월일·나이)
      // 정상 필드로 안전 파생만 시켜 아래(루프 밖)에서 복구한다.
      if (isPiiContaminatedKey_(k)) {
        if (PII_PHONE_KEY_RE_.test(k)) {
          var __pv = (typeof v === "string") ? v.trim() : "";
          if (__pv && !__phoneRescue) __phoneRescue = __pv;
        } else if (role === "admin" && !__dobRescue) {
          __dobRescue = deriveAdminDob_(v);
        }
        continue;
      }
      if (typeof v === "string" && v) {
        var trimmed = v.trim();
        if (PII_RRN_PARTIAL_WHOLE_RE_.test(trimmed)) {
          v = "*******"; // 축약형(생년월일+성별코드 7자리) 전체일치 — 완전 마스킹
        } else {
          v = v.replace(PII_RRN_RE_, maskRrnMatch_); // 13자리 전체형 — 뒷자리 마스킹
        }
      }
      safeRow[k] = v;
    }
    // 정상 키 복사가 모두 끝난 뒤 구제 — "연락처" 기본값("")이 뒤늦게 덮어쓰지 않도록 루프 밖에서 병합.
    if (__phoneRescue && !safeRow["연락처"]) safeRow["연락처"] = __phoneRescue;
    if (__dobRescue) { safeRow["생년월일"] = __dobRescue.dob; safeRow["나이"] = __dobRescue.age; }
    rows[i] = safeRow;
  }
  return rows;
}
// [추가 2026-07-15 A-5] 주민번호 앞자리(YYMMDD-성별)에서 생년월일 전체(YYYY-MM-DD)와 만 나이만
//   파생 — 호출부에서 role==="admin"일 때만 사용(admin 전용). 원본 뒷자리(일련번호)는 애초에
//   입력받지 않으므로 응답에 섞일 수 없음. 성별코드 1~4만 인정(7/14 bday 파생과 동일 범위 —
//   외국인등록 5~8·1800년대 9/0은 판별 근거 부족으로 미지원, bday 정책과 일관성 유지).
var ADMIN_DOB_FULL_RE_    = /(?<!\d)(\d{2})(\d{2})(\d{2})[-.\s]?([1-4])\d{6}(?!\d)/;
var ADMIN_DOB_PARTIAL_RE_ = /^(\d{2})(\d{2})(\d{2})[-.\s]?([1-4])$/;
function deriveAdminDob_(v) {
  if (typeof v !== "string" || !v) return null;
  var s = v.trim();
  var m = ADMIN_DOB_PARTIAL_RE_.exec(s);
  if (!m) m = ADMIN_DOB_FULL_RE_.exec(s);
  if (!m) return null;
  var yy = parseInt(m[1], 10), mm = parseInt(m[2], 10), dd = parseInt(m[3], 10), g = m[4];
  if (mm < 1 || mm > 12 || dd < 1 || dd > 31) return null;
  var century = (g === "1" || g === "2") ? 1900 : 2000;
  var year = century + yy;
  var p = function (n) { return (n < 10 ? "0" : "") + n; };
  var today = new Date();
  var age = today.getFullYear() - year;
  var mNow = today.getMonth() + 1, dNow = today.getDate();
  if (mNow < mm || (mNow === mm && dNow < dd)) age--;
  if (age < 0 || age > 120) return null;
  return { dob: year + "-" + p(mm) + "-" + p(dd), age: age };
}

// [추가 2026-07-16 A-5 병목패치①] 액션→소거 대상 db 매핑 — 액션이 실제 변경하는 탭 캐시만 무효화.
// 미등재 액션은 안전측 폴백(ACTION_DB_FULL_FALLBACK_ = 기존 8db 전량, 회귀 0)으로 처리.
// log-add류는 자동화로그 탭이 애초에 이 8db 목록에 없어 무효화 대상 자체가 없음(최빈 쓰기의 최대 낭비 제거).
var ACTION_DB_MAP_ = {
  "log-add": [], "log-add-bulk": [], "log-fix": [],
  "register-applicant": ["appl"], "update-applicant": ["appl"], "set-stage": ["appl"],
  "set-eval-target": ["appl"], "delete-applicant": ["appl"],
  "schedule-interview": ["appl"], "update-interview": ["appl"], "set-photo": ["appl"],
  "save-eval": ["eval","appl"], "save-work-eval": ["eval","appl"], "save-self-eval": ["eval","appl"], "delete-eval": ["eval","appl"],
  "hire-complete": ["onbo","emp"], "add-onboarding": ["onbo","emp"], "update-onboarding": ["onbo","emp"],
  "delete-onboarding": ["onbo","emp"], "add-selfreflect": ["onbo","emp"],
  "vacate-current": ["emp","exit","exitroster"], "resign": ["emp","exit","exitroster"],
  "add-exit-record": ["emp","exit","exitroster"], "fix-exit-row": ["emp","exit","exitroster"],
  "add-job": ["hire"], "update-job": ["hire"], "update-hire": ["hire"], "update-headcount": ["hire"], "set-channels": ["hire"],
  "set-leave": ["leave"], "set-leave-bulk": ["leave"], "delete-leave": ["leave"]
};
var ACTION_DB_FULL_FALLBACK_ = ["emp","hire","appl","eval","onbo","exit","leave","exitroster"];
// [추가 2026-07-16 A-5 병목패치③] 읽기 캐시 TTL 연장(60→300초). db:appl은 직렬화 길이가 95,000자
// 임계를 넘어(실측 118,300자) put() 진입 자체가 안 되므로 이 TTL은 무관(appl은 영구 미스, ④ 별도 과제).
var DBR_CACHE_TTL_SEC_ = 300;

// [2026-07-13 A-5] db 읽기 캐시가 등급별(role suffix) 키로 분리됐으므로, 쓰기 후 무효화 시
// 등급 3종(admin/viewer/cmd) 키를 모두 지워야 한다. 공용 헬퍼로 중복 방지.
function bustDbrCache_(dbKeys) {
  try {
    var roles = ["admin", "viewer", "cmd"];
    var keys = [];
    for (var i = 0; i < dbKeys.length; i++) {
      for (var j = 0; j < roles.length; j++) keys.push("dbr_" + dbKeys[i] + "_" + roles[j]);
    }
    CacheService.getScriptCache().removeAll(keys);
  } catch (_e) {}
}

// =====================================================================
// [추가 2026-07-24] 근무변경신청(schedreq) — 스케줄 보드 신청·결재 공유 저장
//   탭: 근무변경신청 (헤더 1행, 없으면 자동 생성). id 단위 upsert / 삭제. 다른 탭 접근 없음.
// =====================================================================
function getSchedReqSheet_() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_SCHEDREQ);
  if (!sh) {
    sh = ss.insertSheet(SHEET_SCHEDREQ);
    sh.getRange(NEW_HEADER_ROW, 1, 1, SCHEMAS.schedreq.length).setValues([SCHEMAS.schedreq]);
    sh.getRange(NEW_HEADER_ROW, 1, 1, SCHEMAS.schedreq.length).setFontWeight("bold").setBackground("#f0f0f0");
    sh.setFrozenRows(NEW_HEADER_ROW);
  }
  return sh;
}

// 시트가 날짜/시각 문자열을 Date로 자동 변환해 저장하는 경우가 있어 읽을 때 원래 문자열로 복원
function schedReqCell_(v, kind) {
  if (v === null || v === undefined) return "";
  if (Object.prototype.toString.call(v) === "[object Date]") {
    var tz = Session.getScriptTimeZone();
    if (kind === "time") return Utilities.formatDate(v, tz, "HH:mm");
    if (kind === "datetime") return Utilities.formatDate(v, tz, "yyyy-MM-dd HH:mm:ss");
    return Utilities.formatDate(v, tz, "yyyy-MM-dd");
  }
  return String(v).trim();
}

function handleSchedReqList_() {
  var sh = getSchedReqSheet_();
  var last = sh.getLastRow();
  var out = [];
  if (last >= NEW_DATA_START_ROW) {
    var vals = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, SCHEMAS.schedreq.length).getValues();
    for (var i = 0; i < vals.length; i++) {
      var v = vals[i];
      if (!String(v[0]).trim()) continue;
      out.push({
        id: String(v[0]).trim(), emp: schedReqCell_(v[1], "text"), type: schedReqCell_(v[2], "text"),
        date: schedReqCell_(v[3], "date"), s: schedReqCell_(v[4], "time"), e: schedReqCell_(v[5], "time"),
        reason: schedReqCell_(v[6], "text"), appr: schedReqCell_(v[7], "text"),
        status: schedReqCell_(v[8], "text"), decidedAt: schedReqCell_(v[9], "date")
      });
    }
  }
  return { ok: true, reqs: out };
}

function handleSchedReqSave_(body) {
  var r = body && body.req;
  if (!r || !r.id) return { ok: false, error: "req_required", message: "req(id 포함) 객체가 필요합니다." };
  var id = String(r.id).trim();
  if (!id || id.length > 40) return { ok: false, error: "bad_id" };
  var emp = String(r.emp || "").trim(), type = String(r.type || "").trim(), date = String(r.date || "").trim();
  if (!emp || !type || !date) return { ok: false, error: "missing_fields", message: "신청자·종류·대상일은 필수입니다." };
  if (emp.length > 30 || type.length > 20 || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return { ok: false, error: "bad_fields" };
  var status = String(r.status || "대기").trim();
  if (["대기", "승인", "반려"].indexOf(status) < 0) return { ok: false, error: "bad_status" };
  var decidedAt = String(r.decidedAt || "").trim();
  if (decidedAt && !/^\d{4}-\d{2}-\d{2}$/.test(decidedAt)) return { ok: false, error: "bad_decidedAt" };
  var s = String(r.s || "").trim().slice(0, 10), e = String(r.e || "").trim().slice(0, 10);
  var reason = String(r.reason || "").trim().slice(0, 200), appr = String(r.appr || "").trim().slice(0, 30);

  var sh = getSchedReqSheet_();
  var last = sh.getLastRow();
  var rowIdx = 0;
  if (last >= NEW_DATA_START_ROW) {
    var ids = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (String(ids[i][0]).trim() === id) { rowIdx = NEW_DATA_START_ROW + i; break; }
    }
  }
  if (!rowIdx && last - NEW_HEADER_ROW >= SCHEDREQ_MAX_ROWS) {
    return { ok: false, error: "row_limit", message: "저장 상한(" + SCHEDREQ_MAX_ROWS + "건)에 도달했습니다." };
  }
  var now = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
  var createdAt = now;
  if (rowIdx) createdAt = schedReqCell_(sh.getRange(rowIdx, 11).getValue(), "datetime") || now;
  var vals = [[id, emp, type, date, s, e, reason, appr, status, decidedAt, createdAt, now]];
  if (rowIdx) sh.getRange(rowIdx, 1, 1, SCHEMAS.schedreq.length).setValues(vals);
  else sh.appendRow(vals[0]);
  return { ok: true, action: "schedreq-save", id: id, updated: !!rowIdx };
}

function handleSchedReqDelete_(body) {
  var id = String((body && body.id) || "").trim();
  if (!id) return { ok: false, error: "id_required" };
  var sh = getSchedReqSheet_();
  var last = sh.getLastRow();
  if (last >= NEW_DATA_START_ROW) {
    var ids = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (String(ids[i][0]).trim() === id) {
        sh.deleteRow(NEW_DATA_START_ROW + i);
        return { ok: true, action: "schedreq-delete", deleted: id };
      }
    }
  }
  return { ok: true, action: "schedreq-delete", deleted: null, message: "해당 id 없음(이미 삭제됨)" };
}

function jsonResponse_(obj, statusOverride) {
  var out = ContentService.createTextOutput(JSON.stringify(obj));
  out.setMimeType(ContentService.MimeType.JSON);
  return out;
}

function withCORS_(output) {
  return output; // Apps Script의 ContentService는 자동 CORS 처리됨
}

// =====================================================================
// READ — 7개 시트를 운영허브용 응답 객체로 변환
// =====================================================================
function handleRead_(role) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);

  var out = {
    ok: true,
    role: role,
    emp:    readCurrentSheet_(ss),
    hire:   readSchemaSheet_(ss, SHEET_HIRE,   SCHEMAS.hire),
    appl:   readSchemaSheet_(ss, SHEET_APPL,   SCHEMAS.appl),
    eval:   readSchemaSheet_(ss, SHEET_EVAL,   SCHEMAS.eval),
    onbo:   readSchemaSheet_(ss, SHEET_ONBO,   SCHEMAS.onbo),
    exit:   readSchemaSheet_(ss, SHEET_RESIGN, SCHEMAS.resign),
    timestamp: new Date().toISOString()
  };
  // [2026-07-13 A-5] 역대 퇴사자 명부(주민번호 포함, 최고위험 PII) — 직접 경로(db:exitroster)와
  // 동일하게 관리자 전용. 이전엔 이 전체읽기 경로가 등급 구분 없이 통째로 반환해 db:exitroster의
  // 관리자 게이트를 우회하는 구멍이었음(A-6 2026-07-13 감사 지적). 비관리자에겐 필드 자체를 반환하지 않는다.
  if (role === "admin") {
    out.exit_employees = readExitSheet_(ss);
  }
  // [2026-07-13 A-5] 비관리자(viewer/cmd) 응답은 값형식 기반 PII 마스킹(주민번호·연락처) 적용.
  // admin은 절대 마스킹하지 않음(원문 유지 — 인사카드 등 관리자 화면 회귀 방지).
  if (role !== "admin") {
    out = maskPiiForViewer_(out);
  }
  return out;
}

// 현재근무자 시트 → 임직원 객체 배열 (두 줄 헤더 + 그룹 부서명)
function readCurrentSheet_(ss, role) {
  var sh = ss.getSheetByName(SHEET_CURRENT);
  if (!sh) return [];
  var last = sh.getLastRow();
  if (last < DATA_START_ROW) return [];

  // 헤더 5행/6행 통합 매핑
  var lastCol = sh.getLastColumn();
  var hdr5 = sh.getRange(5, 1, 1, lastCol).getValues()[0];
  var hdr6 = sh.getRange(6, 1, 1, lastCol).getValues()[0];
  var headerMap = {};
  for (var c = 0; c < lastCol; c++) {
    var h5 = String(hdr5[c] || "").trim();
    var h6 = String(hdr6[c] || "").trim();
    var key = h5 || h6;
    if (key) headerMap[c] = key;
  }
  // fix5: F열(0-indexed 5) = 입사일 강제 매핑 (헤더가 병합셀이라 빈값일 때)
  headerMap[5] = "입사일";
  // [추가 2026-07-14 A-7] 생일 열(I열=index 8): 헤더 라벨('생일')이 4행에 있어 5/6행 스캔 밖 →
  //   headerMap엔 첫 데이터행(6행)의 생일 값이 키로 잡혀 오염된다. 그 오염 키를 제거하고,
  //   아래 데이터 루프에서 row[8]을 고정 열로 직접 읽어 bday("MM-DD")만 파생한다
  //   (연도·성별·생일 원문 미노출 — 주민번호 파생 방식 폐기).
  delete headerMap[8];

  var values = sh.getRange(DATA_START_ROW, 1, last - DATA_START_ROW + 1, lastCol).getValues();
  var rows = [];
  var groupDept = "";

  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var obj = {};
    for (var c2 = 0; c2 < row.length; c2++) {
      var k = headerMap[c2];
      if (!k) continue;
      var v = row[c2];
      if (v instanceof Date) v = Utilities.formatDate(v, "Asia/Seoul", "yyyy-MM-dd");
      else if (v !== null && v !== "") v = String(v).trim();
      else v = "";
      obj[k] = v;
    }

    // 그룹 부서 추적
    var dept = obj["부서"] || obj["소속"] || "";
    if (dept) groupDept = dept;
    else if (groupDept) obj["부서"] = groupDept;

    if (!obj["이름"] && !obj["성명"]) continue;

    obj["url"] = makeSheetUrl_(SHEET_CURRENT, DATA_START_ROW + i);

    // 운영허브 호환 키 매핑
    obj["성명"]      = obj["성명"] || obj["이름"] || "";
    obj["부서"]      = obj["부서"] || groupDept || "";
    obj["소속"]      = mapDeptToSosok_(obj["부서"]);
    obj["직급"]      = obj["직급"] || obj["직책"] || "";
    obj["입사일"]    = obj["입사일"] || obj["입사&계약 일자"] || obj["입사"] || "";
    obj["연락처"]    = obj["연락처"] || "";
    obj["이메일"]    = obj["이메일"] || obj["G메일주소"] || obj["G 메일 주소"] || "";
    obj["고용 형태"] = obj["고용 형태"] || obj["고용형태"] || "정규직";
    obj["재직 상태"] = obj["재직 상태"] || obj["재직상태"] || "재직중";
    obj["_sheet_row"] = DATA_START_ROW + i;

    // === 매니저님 보정 매핑 ===
    // 입사일: "입사 & 계약 일자" 컬럼 매칭 (공백 포함된 헤더)
    obj["입사일"] = obj["입사일"] || obj["입사&계약 일자"] || obj["입사 & 계약 일자"] || obj["입사 & 계약일자"] || obj["입사"] || "";
    // fallback: 헤더가 비어있어 첫 데이터가 헤더로 잡혔을 때 — 키나 값 중 yyyy-MM-dd 형식 찾기
    if (!obj["입사일"]) {
      for (var __k in obj) {
        if (__k === "입사일" || __k === "_sheet_row" || __k === "url") continue;
        var __v = obj[__k];
        if (typeof __v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(__v)) {
          obj["입사일"] = __v;
          break;
        }
      }
    }
    // fix4: row[5] H열 (입사 & 계약 일자) 직접
    if (!obj["입사일"]) {
      var __raw = row[5];
      if (__raw instanceof Date) obj["입사일"] = Utilities.formatDate(__raw, "Asia/Seoul", "yyyy-MM-dd");
      else if (__raw) obj["입사일"] = String(__raw).trim();
    }
    // 강습부 직원 → 프리랜서
    var __dn = (obj["부서"] || groupDept || "").trim();
    if (/^(헬스|P\.?T|필라테스|스쿼시|골프|수영|체조|G\.?X|GXE)/i.test(__dn)) {
      obj["고용 형태"] = "프리랜서";
    }
    // 김남욱·나우열 → 경영지원부 override
    if (obj["성명"] === "김남욱" || obj["성명"] === "나우열") {
      obj["부서"] = "경영지원부";
      obj["소속"] = "경영지원부";
    }

    // [추가 2026-07-14 A-7] 생일(I열=index 8) → bday "MM-DD"(월-일만).
    //   소스 = '생일' 열(주민번호 앞자리 파생 폐기). 값 예: "6월 21일" / "음 6월 21일"(음력 접두) —
    //   연도 없음. 월-일만 파생, 파싱불가·공백·범위초과(월 1~12/일 1~31 밖)는 bday 미부여(누락).
    var __bRaw = row[8];
    if (__bRaw !== null && __bRaw !== undefined && __bRaw !== "") {
      var __bStr = (__bRaw instanceof Date)
        ? Utilities.formatDate(__bRaw, "Asia/Seoul", "MM-dd")
        : String(__bRaw).trim();
      var __bMatch = /(\d{1,2})\s*월\s*(\d{1,2})\s*일/.exec(__bStr);
      if (__bMatch) {
        var __bMo = parseInt(__bMatch[1], 10), __bDy = parseInt(__bMatch[2], 10);
        if (__bMo >= 1 && __bMo <= 12 && __bDy >= 1 && __bDy <= 31) {
          obj["bday"] = ("0" + __bMo).slice(-2) + "-" + ("0" + __bDy).slice(-2);
        }
      } else if (/^\d{2}-\d{2}$/.test(__bStr)) {
        obj["bday"] = __bStr; // 이미 MM-DD 형식으로 입력된 경우 그대로
      }
    }

    rows.push(obj);
  }
  // [긴급 2026-07-14 A-5, 2026-07-15 회귀수정] 응답 직전 무조건 주민번호 마스킹(role 무관) —
  //   단 role==="admin"이면 그 안에서 생년월일·나이만 안전 파생해 되돌려준다(위 함수 설명 참조).
  rows = maskEmpRrnUnconditional_(rows, role);
  return rows;
}

// 퇴사자 시트 → 객체 배열
// [2026-07-04 버그 수정] 기존엔 헤더를 5/6행에서 스캔 → 첫 데이터행(6행) 값이 키로 오염되고
// 퇴사일(U)·재직기간(G)·비고(S) 열이 통째로 드롭됐음. 쓰기 계약(addToExitSheet_)과 동일한
// EXIT_COLS 고정 열 매핑으로 읽어 읽기·쓰기 계약을 일치시킨다(헤더 스캔 금지).
function readExitSheet_(ss) {
  var sh = ss.getSheetByName(SHEET_EXIT);
  if (!sh) return [];
  var last = sh.getLastRow();
  if (last < DATA_START_ROW) return [];

  var lastCol = sh.getLastColumn();
  var values = sh.getRange(DATA_START_ROW, 1, last - DATA_START_ROW + 1, lastCol).getValues();
  function fmt_(v) {
    if (v instanceof Date) return Utilities.formatDate(v, "Asia/Seoul", "yyyy-MM-dd");
    if (v !== null && v !== undefined && v !== "") return String(v).trim();
    return "";
  }

  var rows = [];
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var obj = {
      "No":       fmt_(row[EXIT_COLS.no - 1]),
      "부서":     fmt_(row[EXIT_COLS.dept - 1]),
      "이름":     fmt_(row[EXIT_COLS.name - 1]),
      "근무시간": fmt_(row[EXIT_COLS.workTime - 1]),
      "입사일":   fmt_(row[EXIT_COLS.join - 1]),
      "재직기간": fmt_(row[EXIT_COLS.tenure - 1]),
      "주민번호": fmt_(row[EXIT_COLS.rrn - 1]),
      "생일":     fmt_(row[EXIT_COLS.birth - 1]),
      "연락처":   fmt_(row[EXIT_COLS.phone - 1]),
      "비고":     fmt_(row[EXIT_COLS.note - 1]),
      "퇴사일":   fmt_(row[EXIT_COLS.lastDay - 1])
    };
    if (!obj["이름"]) continue;
    obj["성명"] = obj["이름"];
    obj["재직 상태"] = "퇴사";
    obj["_sheet_row"] = DATA_START_ROW + i;
    obj["url"] = makeSheetUrl_(SHEET_EXIT, DATA_START_ROW + i);
    rows.push(obj);
  }
  return rows;
}

// 1행 헤더 시트 → 객체 배열
function readSchemaSheet_(ss, sheetName, schema) {
  var sh = ss.getSheetByName(sheetName);
  if (!sh) return [];
  var last = sh.getLastRow();
  if (last < NEW_DATA_START_ROW) return [];
  var lastCol = Math.max(sh.getLastColumn(), schema.length);

  var hdr = sh.getRange(NEW_HEADER_ROW, 1, 1, lastCol).getValues()[0];
  var values = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, lastCol).getValues();

  var rows = [];
  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var obj = {};
    var hasAny = false;
    for (var c = 0; c < lastCol; c++) {
      var k = String(hdr[c] || "").trim();
      if (!k) continue;
      var v = row[c];
      if (v instanceof Date) { var _hm = Utilities.formatDate(v, "Asia/Seoul", "HHmm"); v = (_hm === "0000") ? Utilities.formatDate(v, "Asia/Seoul", "yyyy-MM-dd") : Utilities.formatDate(v, "Asia/Seoul", "yyyy-MM-dd'T'HH:mm"); }
      else if (v === null || v === undefined) v = "";
      else v = String(v).trim();
      obj[k] = v;
      if (v !== "") hasAny = true;
    }
    if (!hasAny) continue;
    obj["_sheet_row"] = NEW_DATA_START_ROW + i;
    obj["url"] = makeSheetUrl_(sheetName, NEW_DATA_START_ROW + i);
    rows.push(obj);
  }
  return rows;
}

// 시트 행 식별자 → 32자리 hex (운영허브 normId 호환)
function makeSheetUrl_(sheetName, row) {
  var raw = sheetName + "::" + row;
  var bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, raw, Utilities.Charset.UTF_8);
  var hex = "";
  for (var i = 0; i < bytes.length; i++) {
    var v = bytes[i] & 0xff;
    hex += (v < 16 ? "0" : "") + v.toString(16);
  }
  return "sheet://row/" + hex;
}

// =====================================================================
// REGISTER — 신규 입사자 등록 (현재근무자 시트 + 입사·온보딩 체크리스트)
// =====================================================================
function handleRegister_(body) {
  var name      = (body.name      || "").trim();
  var dept      = (body.dept      || "").trim();   // 부서 (강습부/경영지원부/운영부/시설부)
  var sosok     = (body.sosok     || "").trim();   // 소속 (PT팀/필라테스팀/...)
  var rank      = (body.rank      || "").trim();   // 직급
  var joinDate  = (body.joinDate  || "").trim();
  var phone     = (body.phone     || "").trim();
  var email     = (body.email     || "").trim();
  var empType   = (body.empType   || "정규직").trim();

  if (!name)     return { ok: false, error: "name_required" };
  if (!dept)     return { ok: false, error: "dept_required" };
  if (!joinDate) return { ok: false, error: "joinDate_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);

  // 1) 현재근무자 시트에 부서 그룹 끝에 행 삽입
  var curResult = insertIntoCurrentByDept_(ss, dept, sosok, rank, name, joinDate, phone, email);
  if (!curResult.ok) return curResult;

  // 2) 입사·온보딩 체크리스트 자동 생성 (기본 5개 카테고리 × 핵심 항목)
  addDefaultOnboardingTasks_(ss, name, joinDate);

  return {
    ok: true,
    msg: "신규 입사자 '" + name + "' 등록 완료. 시트 " + curResult.row + "행 + 온보딩 체크리스트 생성.",
    sheet_row: curResult.row
  };
}

// 부서 그룹 라벨 정규화 — 공백·줄바꿈 제거 + 끝의 '부' 유무 무시.
// 예: "주차\n관리"≡"주차관리"≡"주차관리부", "시설"≡"시설부", "지원"≡"지원부".
function normDeptLabel_(s) {
  var t = String(s || "").replace(/\s+/g, "");
  if (t.length > 1 && t.charAt(t.length - 1) === "부") t = t.slice(0, -1);
  return t;
}

// [2026-07-04 매니저 확정 정책] 현재근무자 시트는 행 고정 — 외부 수식·스케줄&페이롤 링크가
// 행번호를 참조하므로 insertRow/deleteRow 절대 금지. 신규 입사는 해당 부서 구역의 "빈 슬롯 행"에
// 값만 채운다. 빈 슬롯이 없으면 에러 반환(행 확보는 매니저가 시트에서 직접 — 자동 삽입 금지).
function insertIntoCurrentByDept_(ss, dept, sosok, rank, name, joinDate, phone, email) {
  var sh = ss.getSheetByName(SHEET_CURRENT);
  if (!sh) return { ok: false, error: "sheet_not_found", sheet: SHEET_CURRENT };

  var rankCol = colByHeader_(sh, "직책") || colByHeader_(sh, "직급") || 3;
  var nameCol = colByHeader_(sh, "이름") || colByHeader_(sh, "성명") || 4;
  var joinCol = colByHeader_(sh, "입사&계약 일자") || colByHeader_(sh, "입사일") || 6;
  var phoneCol = colByHeader_(sh, "연락처") || 10;
  var mailCol  = colByHeader_(sh, "G메일주소") || colByHeader_(sh, "G 메일 주소") || colByHeader_(sh, "이메일");
  // 부서 그룹 라벨 열은 항상 B열(=2) 고정 — colByHeader_는 건드리지 않는다(병합셀 헤더라 못 찾음).
  var deptCol = colByHeader_(sh, "부서") || colByHeader_(sh, "소속") || 2;

  var last = sh.getLastRow();
  var noSlotMsg = "[" + dept + "] 구역에 빈 행이 없습니다. 시트에서 행을 확보한 뒤 다시 시도해 주세요(행 자동 삽입 금지 정책).";
  if (last < DATA_START_ROW) {
    return { ok: false, error: "no_empty_slot", message: noSlotMsg };
  }
  var values = sh.getRange(DATA_START_ROW, 1, last - DATA_START_ROW + 1, sh.getLastColumn()).getValues();

  // 부서 구역(연속 구간) 탐색 — B열 그룹 라벨을 정규화 매칭해 목표 부서 구역 안에서
  // 이름(D열)이 빈 첫 행을 슬롯으로 선정.
  var targetNorm = normDeptLabel_(dept);
  var groupDept = "";
  var slotRow = -1;
  for (var i = 0; i < values.length; i++) {
    var dpRaw = String(values[i][deptCol - 1] || "").trim();
    if (dpRaw) groupDept = dpRaw;
    if (groupDept && normDeptLabel_(groupDept) === targetNorm) {
      var nm = String(values[i][nameCol - 1] || "").trim();
      if (!nm) { slotRow = DATA_START_ROW + i; break; }
    }
  }

  if (slotRow < 0) {
    return { ok: false, error: "no_empty_slot", message: noSlotMsg };
  }

  // A열 No — 이미 값이 있으면 절대 덮지 않음(빈 경우만 이전행+1)
  var noCell = sh.getRange(slotRow, 1);
  var curNo = noCell.getValue();
  if (curNo === "" || curNo === null || curNo === undefined) {
    var prevNo = sh.getRange(slotRow - 1, 1).getValue();
    if (typeof prevNo === "number" && !isNaN(prevNo)) {
      noCell.setValue(prevNo + 1);
    }
  }

  // B열(부서, 병합)·E열(근무시간)·수식 있는 셀은 건드리지 않음 — 슬롯 행의 지정된 필드만 기입.
  if (rank)     sh.getRange(slotRow, rankCol).setValue(rank);
  if (name)     sh.getRange(slotRow, nameCol).setValue(name);
  if (joinDate) sh.getRange(slotRow, joinCol).setValue(toDate_(joinDate));
  if (phone)    sh.getRange(slotRow, phoneCol).setValue(phone);
  if (email && mailCol) sh.getRange(slotRow, mailCol).setValue(email);

  return { ok: true, row: slotRow };
}

function addDefaultOnboardingTasks_(ss, name, joinDate) {
  var sh = getOrCreateSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
  var tasks = [
    ["근로계약서 작성·서명",  "서류·계약",    name, "인사담당",          joinDate, "", "", "", ""],
    ["신분증 사본 제출",      "서류·계약",    name, "신입직원",          joinDate, "", "", "", ""],
    ["통장 사본 제출 (급여)", "서류·계약",    name, "신입직원",          joinDate, "", "", "", ""],
    ["보건증 발급",          "서류·계약",    name, "신입직원",          joinDate, "", "", "강습부 필수", ""],
    ["근태·일정 시스템 접근", "시스템 접근",  name, "운영부",            joinDate, "", "", "", ""],
    ["사원증 발급 / 락커 배정", "시설·장비",  name, "관리부",            joinDate, "", "", "", ""],
    ["오리엔테이션",         "교육·OT",      name, "CHRO",              joinDate, "", "", "", ""],
    ["부서 인사 인사·시설 투어", "조직 적응", name, "부서장",            joinDate, "", "", "", ""]
  ];
  var startRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(startRow, 1, tasks.length, tasks[0].length).setValues(tasks);
}

// =====================================================================
// P1 — 이탈 파생정리 (2026-07-16 A-7 설계 구현, drafts\P1통합_설계_result.md)
//   resign·vacate-current 공용. 이름 기준으로 파생물(온보딩·평가·휴무)을 정리하되
//   불가침 데이터(완료 기록·채점된 평가)는 절대 안 건드림. 삭제 대상은 "증명 가능한
//   빈 템플릿"만. 오폭 방지: 동명이인 재직자가 남아있으면 파생정리 전면 스킵.
// =====================================================================
function countCurrentByName_(ss, name) {
  var sh = ss.getSheetByName(SHEET_CURRENT);
  if (!sh) return 0;
  var nameCol = colByHeader_(sh, "이름") || colByHeader_(sh, "성명") || 4;
  var last = sh.getLastRow();
  if (last < DATA_START_ROW) return 0;
  var names = sh.getRange(DATA_START_ROW, nameCol, last - DATA_START_ROW + 1, 1).getValues();
  var cnt = 0;
  for (var i = 0; i < names.length; i++) {
    if (String(names[i][0] || "").trim() === name) cnt++;
  }
  return cnt;
}

function cleanupDepartureDependents_(ss, name, opts) {
  opts = opts || {};
  var result = { onboarding: { deleted: 0, preserved: 0 }, eval: { deleted: 0, skippedFilled: 0 }, leave: { cleared: 0 }, skipped: null };
  if (!name) { result.skipped = "name_empty"; return result; }

  // 0) 동명이인 게이트 — 정리 전 현재근무자에 같은 이름이 잔존하면 파생정리 전면 스킵.
  if (countCurrentByName_(ss, name) >= 1) {
    result.skipped = "동명이인 재직자 존재";
    return result;
  }

  // 1) 온보딩 — '대상 신입 직원'===name & 완료여부·완료일·비고 전부 공란인 행만 삭제(bottom-up).
  //    하나라도 기록 있으면 보존(재직이력).
  var shOnbo = ss.getSheetByName(SHEET_ONBO);
  if (shOnbo) {
    var dataOnbo = shOnbo.getDataRange().getValues();
    if (dataOnbo.length >= 1) {
      var hdrOnbo = dataOnbo[0];
      var cName = hdrOnbo.indexOf("대상 신입 직원");
      var cDone = hdrOnbo.indexOf("완료 여부");
      var cDoneDate = hdrOnbo.indexOf("완료일");
      var cNote = hdrOnbo.indexOf("비고");
      if (cName >= 0) {
        for (var i = dataOnbo.length - 1; i >= 1; i--) {
          var orow = dataOnbo[i];
          if (String(orow[cName] || "").trim() !== name) continue;
          var isEmptyTemplate =
            (cDone < 0 || String(orow[cDone] || "").trim() === "") &&
            (cDoneDate < 0 || String(orow[cDoneDate] || "").trim() === "") &&
            (cNote < 0 || String(orow[cNote] || "").trim() === "");
          if (isEmptyTemplate) {
            shOnbo.deleteRow(i + 1);
            result.onboarding.deleted++;
          } else {
            result.onboarding.preserved++;
          }
        }
      }
    }
  }

  // 2) 평가 — '대상자'===name 정확일치 & 총점·평가 등급·평가자 전부 공란인 placeholder만 삭제.
  //    ⚠️ 정확일치만(부분일치·평가명 매칭 금지 — "(연결 N건)" 붕괴행은 대상자≠name이라 미매칭 = 안전).
  //    하나라도 채워지면 절대 불가침(handleDeleteEval_ 가드와 동일 판정 재사용).
  var shEval = ss.getSheetByName(SHEET_EVAL);
  if (shEval) {
    var dataEval = shEval.getDataRange().getValues();
    if (dataEval.length >= 1) {
      var hdrEval = dataEval[0];
      var cTgt = hdrEval.indexOf("대상자");
      var cScore = hdrEval.indexOf("총점");
      var cGrade = hdrEval.indexOf("평가 등급");
      var cEvaluator = hdrEval.indexOf("평가자");
      if (cTgt >= 0) {
        for (var j = dataEval.length - 1; j >= 1; j--) {
          var erow = dataEval[j];
          if (String(erow[cTgt] || "").trim() !== name) continue;
          var filled = (cScore >= 0 && String(erow[cScore] || "").trim() !== "") ||
                       (cGrade >= 0 && String(erow[cGrade] || "").trim() !== "") ||
                       (cEvaluator >= 0 && String(erow[cEvaluator] || "").trim() !== "");
          if (filled) {
            result.eval.skippedFilled++;
          } else {
            shEval.deleteRow(j + 1);
            result.eval.deleted++;
          }
        }
      }
    }
  }

  // 3) 휴무 — 기본 보존(정리 안 함). opts.clearFutureLeave===true && opts.lastDay 있을 때만
  //    미래(날짜>최종근무일) 휴무만 비움. 근태·페이롤 이력 소스이므로 기본은 절대 건드리지 않음.
  if (opts.clearFutureLeave === true && opts.lastDay) {
    var shLeave = ss.getSheetByName(SHEET_LEAVE);
    if (shLeave) {
      var dataLeave = shLeave.getDataRange().getValues();
      if (dataLeave.length >= 1) {
        var hdrLeave = dataLeave[0];
        var cL = _leaveCols_(hdrLeave);
        var lastDayDate = toDate_(String(opts.lastDay));
        if (cL.n >= 0 && cL.d >= 0 && lastDayDate instanceof Date) {
          for (var k = dataLeave.length - 1; k >= 1; k--) {
            var lrow = dataLeave[k];
            if (String(lrow[cL.n] || "").trim() !== name) continue;
            var dRaw = lrow[cL.d];
            var d = (dRaw instanceof Date) ? dRaw : toDate_(String(dRaw || ""));
            if (d instanceof Date && d > lastDayDate) {
              shLeave.deleteRow(k + 1);
              result.leave.cleared++;
            }
          }
        }
      }
    }
  }

  return result;
}

// =====================================================================
// RESIGN — 퇴사 처리
// 1) 현재근무자 시트에서 행 제거
// 2) 퇴사자 시트에 추가
// 3) 퇴사처리 시트에 신규 레코드 생성
// =====================================================================
function handleResign_(body) {
  // 운영허브 호환 매개변수 (employeeName, exitType, lastDay)
  var name      = (body.name || body.employeeName || "").trim();
  var dept      = (body.dept || "").trim();
  var lastDay   = (body.lastDay || body.lastWorkDay || "").trim();
  var type      = (body.type || body.exitType || "자진 퇴사").trim();
  var reason    = (body.reason || "").trim();
  var memo      = (body.memo || body.note || "").trim();

  if (!name)    return { ok: false, error: "name_required" };
  if (!lastDay) return { ok: false, error: "lastDay_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var resultSheet = { attempted: true, ok: false, msg: "" };
  var resultExit  = { ok: false, msg: "" };

  // 1) 현재근무자에서 해당 이름 행 찾아서 부서 등 정보 수집 + 행 삭제
  var info = removeFromCurrentByName_(ss, name);
  if (!info.found) {
    resultSheet.ok = false;
    resultSheet.msg = "현재근무자 시트에서 '" + name + "' 못 찾음";
    return {
      ok: false,
      error: "not_found_in_current",
      employeeName: name,
      sheet: resultSheet,
      exitRecord: false,
      exitRecordMsg: "이름 매칭 실패로 처리 중단",
      exitMessage: name + " 처리 실패 — 현재근무자 시트에서 찾을 수 없습니다."
    };
  }

  // 2) 퇴사자 시트에 행 추가
  try {
    var addedExitRow = addToExitSheet_(ss, info, lastDay, type);
    resultSheet.ok = true;
    resultSheet.msg = "현재근무자 → 퇴사자 이동 완료 (" + addedExitRow + "행)";
  } catch (e) {
    resultSheet.ok = false;
    resultSheet.msg = "퇴사자 시트 쓰기 실패: " + (e.message || e);
  }

  // 3) 퇴사처리 시트에 행 추가
  try {
    var sh = getOrCreateSheet_(ss, SHEET_RESIGN, SCHEMAS.resign);
    var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
    sh.getRange(nextRow, 1, 1, SCHEMAS.resign.length).setValues([[
      name + " 퇴사 처리",
      name,
      type,
      Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd"),
      lastDay,
      reason,
      memo,
      "", "", "", "", "", "", ""
    ]]);
    resultExit.ok = true;
    resultExit.msg = "퇴사처리 레코드 " + nextRow + "행 생성";
  } catch (e) {
    resultExit.ok = false;
    resultExit.msg = "퇴사처리 시트 쓰기 실패: " + (e.message || e);
  }

  // [P1 2026-07-16] 이탈 파생정리 — 이름 기준 온보딩·평가 빈 템플릿 정리(불가침 데이터 보존).
  // cleanupDependents:false 로 명시 차단 가능(기본 ON).
  var __dep = (body.cleanupDependents === false) ? { skipped: "opt-out" } :
              cleanupDepartureDependents_(ss, name, { clearFutureLeave: body.clearFutureLeave === true, lastDay: lastDay });

  return {
    ok: true,
    employeeName: name,
    sheet: resultSheet,                   // 운영허브 호환: sheet.{attempted,ok,msg}
    exitRecord: resultExit.ok,            // 운영허브 호환: 퇴사처리 레코드 생성 여부
    exitRecordMsg: resultExit.msg,
    exitMessage: name + " 퇴사 처리 완료 (시트 이동 + 퇴사처리 레코드 생성)",
    msg: name + " 퇴사 처리 완료",
    dependents: __dep
  };
}

// =====================================================================
// VACATE-CURRENT — 채용취소 / 입사무산 정리 (2026-07-07 추가)
//   임직원(현재근무자) 시트에서 해당 행을 "값만 비움"(행 고정 정책: deleteRow 금지,
//   A열 No·B열 부서(병합)·수식 셀 보존). resign과 달리 퇴사자 로스터·퇴사처리 시트에
//   기록을 생성하지 않는다 — 실근무 이력이 없는 사전등록(hire 확정)만 취소하는 용도.
//   입력: name(또는 employeeName) 우선, 없으면 sheetRow(또는 row). adminPassword 필수.
// =====================================================================
function handleVacateCurrent_(body) {
  var name     = String((body && (body.name || body.employeeName)) || "").trim();
  var rowRaw   = (body && (body.sheetRow || body.row));
  var sheetRow = parseInt(rowRaw, 10);
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);

  var info;
  if (name) {
    // 이름 매칭 → 검증된 removeFromCurrentByName_ 재사용(값비움·수식셀/병합 보존, 행 유지).
    info = removeFromCurrentByName_(ss, name);
    if (!info.found) {
      return {
        ok: false,
        error: "not_found_in_current",
        employeeName: name,
        message: "현재근무자 시트에서 '" + name + "' 못 찾음 — 값비움 중단(퇴사기록도 미생성)"
      };
    }
  } else if (!isNaN(sheetRow) && sheetRow >= DATA_START_ROW) {
    info = vacateCurrentRow_(ss, sheetRow);
    if (!info.found) {
      return {
        ok: false,
        error: "row_empty_or_out_of_range",
        sheetRow: sheetRow,
        message: "행 " + sheetRow + "에 비울 값(이름)이 없거나 범위를 벗어남 — 중단"
      };
    }
  } else {
    return { ok: false, error: "name_or_row_required", message: "name 또는 sheetRow가 필요합니다." };
  }

  // [P1 2026-07-16] 이탈 파생정리 — 입사무산자의 register 기본 온보딩 템플릿·평가 placeholder 정리.
  // vacate 는 lastDay 없음 → clearFutureLeave 무의미. cleanupDependents:false 로 명시 차단 가능(기본 ON).
  var __depName = info.name || name || "";
  var __dep = (body.cleanupDependents === false) ? { skipped: "opt-out" } :
              cleanupDepartureDependents_(ss, __depName, {});

  return {
    ok: true,
    action: "vacate-current",
    employeeName: __depName,
    clearedRow: info.row,
    dept: info.dept || "",
    rank: info.rank || "",
    exitRecord: false,           // 퇴사처리 시트 기록 생성 안 함(채용취소는 퇴사 아님)
    exitRoster: false,           // 퇴사자 로스터 이관 안 함
    note: "채용취소/입사무산 — 현재근무자 행 값비움(행 유지·A열 No·B열 부서·수식셀 보존). 퇴사자·퇴사처리 시트 기록 미생성.",
    msg: __depName + " 현재근무자 값비움 완료 (행 " + info.row + ", 퇴사기록 미생성)",
    dependents: __dep
  };
}

// sheetRow로 직접 값비움 — removeFromCurrentByName_와 동일한 행고정 정책(C열~마지막열 중
// 수식 없는 셀만 clearContent, A열 No·B열 부서 병합·수식셀 보존). 이름 응답용으로 수집만.
function vacateCurrentRow_(ss, rowNum) {
  var sh = ss.getSheetByName(SHEET_CURRENT);
  if (!sh) return { found: false };
  var last = sh.getLastRow();
  if (rowNum < DATA_START_ROW || rowNum > last) return { found: false };

  var nameCol = colByHeader_(sh, "이름") || colByHeader_(sh, "성명") || 4;
  var deptCol = colByHeader_(sh, "부서") || colByHeader_(sh, "소속") || 2;
  var rankCol = colByHeader_(sh, "직책") || colByHeader_(sh, "직급") || 3;
  var lastCol = sh.getLastColumn();

  var rowVals = sh.getRange(rowNum, 1, 1, lastCol).getValues()[0];
  var name = String(rowVals[nameCol - 1] || "").trim();
  if (!name) return { found: false };  // 비울 값 없음
  var rank = String(rowVals[rankCol - 1] || "").trim();
  var dept = String(rowVals[deptCol - 1] || "").trim();

  var formulas = sh.getRange(rowNum, 1, 1, lastCol).getFormulas()[0];
  for (var c = 3; c <= lastCol; c++) {
    if (!formulas[c - 1]) sh.getRange(rowNum, c).clearContent();
  }
  return { found: true, name: name, dept: dept, rank: rank, row: rowNum };
}

function removeFromCurrentByName_(ss, name) {
  var sh = ss.getSheetByName(SHEET_CURRENT);
  if (!sh) return { found: false };
  var nameCol = colByHeader_(sh, "이름") || colByHeader_(sh, "성명") || 4;
  var deptCol = colByHeader_(sh, "부서") || colByHeader_(sh, "소속") || 2;
  var rankCol = colByHeader_(sh, "직책") || colByHeader_(sh, "직급") || 3;
  var joinCol = colByHeader_(sh, "입사&계약 일자") || colByHeader_(sh, "입사일") || 6;
  var phoneCol = colByHeader_(sh, "연락처") || 10;
  var timeCol  = colByHeader_(sh, "근무시간") || 5;
  var rrnCol   = colByHeader_(sh, "주민번호") || 8;
  var birthCol = colByHeader_(sh, "생일") || 9;

  var last = sh.getLastRow();
  if (last < DATA_START_ROW) return { found: false };

  var values = sh.getRange(DATA_START_ROW, 1, last - DATA_START_ROW + 1, sh.getLastColumn()).getValues();
  var groupDept = "";
  for (var i = 0; i < values.length; i++) {
    var dp = String(values[i][deptCol - 1] || "").trim();
    if (dp) groupDept = dp;
    var nm = String(values[i][nameCol - 1] || "").trim();
    if (nm === name) {
      // 표시값(주민번호·생일·근무시간)은 화면 그대로 이관하기 위해 DisplayValues로 수집
      var disp = sh.getRange(DATA_START_ROW + i, 1, 1, sh.getLastColumn()).getDisplayValues()[0];
      var info = {
        found: true,
        name: name,
        dept: dp || groupDept,
        rank: String(values[i][rankCol - 1] || "").trim(),
        joinDate: values[i][joinCol - 1],
        phone: String(disp[phoneCol - 1] || "").trim(),
        workTime: String(disp[timeCol - 1] || "").trim(),
        rrn: String(disp[rrnCol - 1] || "").trim(),
        birth: String(disp[birthCol - 1] || "").trim(),
        row: DATA_START_ROW + i
      };
      // [2026-07-04 매니저 확정 정책] 행 고정 — deleteRow 금지(외부 수식·스케줄&페이롤 링크가
      // 행번호를 참조). 행은 그대로 두고 C열~마지막열 중 "수식 없는 셀"만 값을 비워 빈 슬롯으로
      // 되돌린다. A열 No·B열(부서 병합)은 항상 보존.
      var __lastCol = sh.getLastColumn();
      var __formulas = sh.getRange(info.row, 1, 1, __lastCol).getFormulas()[0];
      for (var __c = 3; __c <= __lastCol; __c++) {
        if (!__formulas[__c - 1]) sh.getRange(info.row, __c).clearContent();
      }
      return info;
    }
  }
  return { found: false };
}

// 퇴사자 탭 열 계약 (2026-07-02 매니저 확정 — 헤더 4·5행 실측 고정):
// A=No · B=(병합·미사용) · C=부서 · D=이름 · E=근무시간 · F=입사 일자 · G=재직 기간
// H=주민번호 · I=생일 · J=연락처 · S=비고 · U=퇴사 일자
// ※ 이 탭 헤더는 4행(라벨)·5행(No~근무시간)이라 colByHeader_(5/6행 스캔)로 못 찾음 → 열 고정.
var EXIT_COLS = { no:1, dept:3, name:4, workTime:5, join:6, tenure:7, rrn:8, birth:9, phone:10, note:19, lastDay:21 };

function addToExitSheet_(ss, info, lastDay, type) {
  var sh = ss.getSheetByName(SHEET_EXIT);
  if (!sh) sh = ss.insertSheet(SHEET_EXIT);

  var last = sh.getLastRow();
  var newRow = Math.max(last + 1, DATA_START_ROW);
  if (newRow > sh.getMaxRows()) sh.insertRowAfter(sh.getMaxRows());

  // No = 기존 데이터 A열 최대 숫자 + 1
  var nextNo = 1;
  if (last >= DATA_START_ROW) {
    var nos = sh.getRange(DATA_START_ROW, EXIT_COLS.no, last - DATA_START_ROW + 1, 1).getValues();
    for (var i = 0; i < nos.length; i++) {
      var n = parseInt(nos[i][0], 10);
      if (!isNaN(n) && n >= nextNo) nextNo = n + 1;
    }
  }

  sh.getRange(newRow, EXIT_COLS.no).setValue(nextNo);
  sh.getRange(newRow, EXIT_COLS.name).setValue(info.name);
  if (info.dept)     sh.getRange(newRow, EXIT_COLS.dept).setValue(info.dept);
  if (info.workTime) sh.getRange(newRow, EXIT_COLS.workTime).setValue(info.workTime);
  if (info.joinDate) sh.getRange(newRow, EXIT_COLS.join).setValue(info.joinDate);
  if (info.rrn)      sh.getRange(newRow, EXIT_COLS.rrn).setNumberFormat("@").setValue(info.rrn);
  if (info.birth)    sh.getRange(newRow, EXIT_COLS.birth).setValue(info.birth);
  if (info.phone)    sh.getRange(newRow, EXIT_COLS.phone).setNumberFormat("@").setValue(info.phone);
  if (lastDay)       sh.getRange(newRow, EXIT_COLS.lastDay).setNumberFormat("@").setValue(String(lastDay));

  // 재직 기간 = 입사일 ~ 최종 근무일 (기존 행 "N년N개월N일" 표기와 동일)
  var tenure = tenureText_(info.joinDate, lastDay);
  if (tenure) sh.getRange(newRow, EXIT_COLS.tenure).setValue(tenure);

  // 퇴사 유형·직책은 비고(S)에 보존 (퇴사처리 탭에도 별도 기록됨)
  var note = [];
  if (info.rank) note.push(info.rank);
  if (type) note.push(type);
  if (note.length) sh.getRange(newRow, EXIT_COLS.note).setValue(note.join(" · "));

  return newRow;
}

// "N년N개월N일" 재직기간 문자열 (기존 퇴사자 행 표기와 동일 형식)
function tenureText_(join, last) {
  var j = (join instanceof Date) ? join : toDate_(String(join || ""));
  var l = (last instanceof Date) ? last : toDate_(String(last || ""));
  if (!(j instanceof Date) || isNaN(j) || !(l instanceof Date) || isNaN(l) || l < j) return "";
  var y = l.getFullYear() - j.getFullYear();
  var m = l.getMonth() - j.getMonth();
  var d = l.getDate() - j.getDate();
  if (d < 0) { m--; d += new Date(l.getFullYear(), l.getMonth(), 0).getDate(); }
  if (m < 0) { y--; m += 12; }
  if (y < 0) return "";
  return y + "년" + m + "개월" + d + "일";
}

// =====================================================================
// [추가 2026-07-04] ADD-EXIT-RECORD — 퇴사처리 레코드 소급 생성
//   현재근무자 시트에 이미 없는(과거) 퇴사자의 퇴사처리 이력을 보정할 때 사용.
//   (예: 이지영 2026-06-12 자진퇴사 — 현재근무자엔 이미 부재, 퇴사처리 이력만 누락)
//   admin 권한은 switch(action) 단계의 requireAdmin_(role)에서 이미 검증됨.
// =====================================================================
function handleAddExitRecord_(body) {
  var name    = (body.name    || "").trim();
  var lastDay = (body.lastDay || "").trim();
  var type    = (body.type    || "자진 퇴사").trim();
  var title   = (body.title   || "").trim();
  var memo    = (body.memo    || body.note || "").trim();
  var reason  = (body.reason  || "").trim();

  if (!name)    return { ok: false, error: "name_required" };
  if (!lastDay) return { ok: false, error: "lastDay_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_RESIGN, SCHEMAS.resign);
  var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nextRow, 1, 1, SCHEMAS.resign.length).setValues([[
    title || (name + " 퇴사 처리"),
    name,
    type,
    Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd"),
    lastDay,
    reason,
    memo,
    "", "", "", "", "", "", ""
  ]]);
  return { ok: true, msg: name + " 퇴사처리 레코드 소급 생성 (" + sh.getName() + " " + nextRow + "행)", sheet_row: nextRow };
}

// =====================================================================
// [추가 2026-07-04] FIX-EXIT-ROW — 퇴사자 시트 특정 행 보정
//   생일(I)·퇴사일(U)·입사일(F) 등 전달된 필드만 EXIT_COLS 위치에 텍스트 서식으로 기입.
//   expectName으로 대상 행의 현재 이름을 먼저 확인 — 불일치 시 거부(잘못된 sheetRow 오기입 방지).
//   tenureRecalc:true면 (갱신 후) 입사일·퇴사일로 재직기간(G)을 tenureText_로 재계산해 기입.
// =====================================================================
function handleFixExitRow_(body) {
  var sheetRow = parseInt(body.sheetRow, 10);
  var expectName = (body.expectName || "").trim();

  if (!sheetRow || isNaN(sheetRow) || sheetRow < DATA_START_ROW) {
    return { ok: false, error: "sheetRow_invalid" };
  }
  if (!expectName) return { ok: false, error: "expectName_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_EXIT);
  if (!sh) return { ok: false, error: "sheet_not_found", sheet: SHEET_EXIT };
  if (sheetRow > sh.getLastRow()) return { ok: false, error: "sheetRow_out_of_range" };

  var curName = String(sh.getRange(sheetRow, EXIT_COLS.name).getValue() || "").trim();
  if (curName !== expectName) {
    return {
      ok: false, error: "name_mismatch",
      message: sheetRow + "행의 이름('" + curName + "')이 확인값('" + expectName + "')과 다릅니다. 잘못된 행 지정을 방지하기 위해 거부합니다."
    };
  }

  var updated = [];
  if (body.birth !== undefined && body.birth !== null && String(body.birth).trim() !== "") {
    sh.getRange(sheetRow, EXIT_COLS.birth).setNumberFormat("@").setValue(String(body.birth).trim());
    updated.push("생일");
  }
  if (body.exitDate !== undefined && body.exitDate !== null && String(body.exitDate).trim() !== "") {
    sh.getRange(sheetRow, EXIT_COLS.lastDay).setNumberFormat("@").setValue(String(body.exitDate).trim());
    updated.push("퇴사일");
  }
  if (body.joinDate !== undefined && body.joinDate !== null && String(body.joinDate).trim() !== "") {
    sh.getRange(sheetRow, EXIT_COLS.join).setNumberFormat("@").setValue(String(body.joinDate).trim());
    updated.push("입사일");
  }

  if (body.tenureRecalc === true || body.tenureRecalc === "true") {
    var joinVal = sh.getRange(sheetRow, EXIT_COLS.join).getValue();
    var lastVal = sh.getRange(sheetRow, EXIT_COLS.lastDay).getValue();
    var tenure = tenureText_(joinVal, lastVal);
    if (tenure) {
      sh.getRange(sheetRow, EXIT_COLS.tenure).setValue(tenure);
      updated.push("재직기간");
    }
  }

  return {
    ok: true,
    msg: expectName + " (" + sheetRow + "행) " + (updated.length ? updated.join("·") + " 갱신" : "변경 사항 없음"),
    updated: updated
  };
}

// =====================================================================
// SCHEDULE INTERVIEW — 지원자 시트 면접 일정 갱신 (운영허브 호환)
// 운영허브 호출: applicantPageId, stage, interviewDate, interviewer
// =====================================================================
function handleScheduleInterview_(body) {
  var pageId      = (body.applicantPageId || "").trim();
  var applName    = (body.applicant || body.name || body.applicantName || "").trim();
  var datetime    = (body.interviewDate || body.datetime || body.interviewAt || "").trim();
  var interviewer = (body.interviewer || "").trim();
  var stage       = (body.stage || "1차 면접").trim();

  if (!pageId && !applName) return { ok: false, error: "applicant_required" };
  if (!datetime) return { ok: false, error: "datetime_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_APPL, SCHEMAS.appl);

  var rowNum = pageId ? findRowByPageId_(sh, pageId) : -1;
  if (rowNum < 0 && applName) {
    var r = findRowByCol_(sh, "지원자명", applName);
    if (r.found) rowNum = r.row;
  }
  if (rowNum < 0) return { ok: false, error: "applicant_not_found", pageId: pageId, name: applName };

  setCellByHeader_(sh, rowNum, "면접 일정", parseIvDate_(datetime));
  if (interviewer) setCellByHeader_(sh, rowNum, "담당 면접관", interviewer);
  if (stage) setCellByHeader_(sh, rowNum, "전형 단계", stage);

  var nm = applName || getCellByHeader_(sh, rowNum, "지원자명") || "지원자";
  return {
    ok: true,
    applicantName: nm,
    stage: stage,
    interviewDate: datetime,
    msg: nm + " — " + stage + " 일정 등록: " + datetime
  };
}

// =====================================================================
// UPDATE INTERVIEW — 면접 평가 결과 입력 (운영허브 호환)
// 운영허브 호출: applicantPageId, grade, nextStage, note
// =====================================================================
function handleUpdateInterview_(body) {
  var pageId    = (body.applicantPageId || "").trim();
  var applName  = (body.applicant || body.name || "").trim();
  var grade     = (body.grade || "").trim();
  var feedback  = (body.note || body.feedback || body.memo || "").trim();
  var nextStage = (body.nextStage || "").trim();

  if (!pageId && !applName) return { ok: false, error: "applicant_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_APPL, SCHEMAS.appl);

  var rowNum = pageId ? findRowByPageId_(sh, pageId) : -1;
  if (rowNum < 0 && applName) {
    var r = findRowByCol_(sh, "지원자명", applName);
    if (r.found) rowNum = r.row;
  }
  if (rowNum < 0) return { ok: false, error: "applicant_not_found", pageId: pageId, name: applName };

  if (grade) setCellByHeader_(sh, rowNum, "면접 평점", grade);
  if (feedback) {
    var current = getCellByHeader_(sh, rowNum, "메모") || "";
    var stamp = "[" + Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm") + " 면접평가] ";
    setCellByHeader_(sh, rowNum, "메모", (current ? current + "\n" : "") + stamp + feedback);
  }
  if (nextStage) setCellByHeader_(sh, rowNum, "전형 단계", nextStage);

  var nm = applName || getCellByHeader_(sh, rowNum, "지원자명") || "지원자";
  return {
    ok: true,
    applicantName: nm,
    grade: grade,
    nextStage: nextStage,
    msg: nm + " 면접 평가 갱신 (등급 " + grade + ", 다음 " + nextStage + ")"
  };
}

// =====================================================================
// HIRE COMPLETE — 입사확정 → 현재근무자 시트 신규 행 (운영허브 호환)
// 운영허브 호출: applicantPageId, name, dept, sosok, rank, empType, joinDate
// =====================================================================
// [추가 2026-07-16 A-5 P2 공통헬퍼] 공고 포지션명↔지원자 매칭 키 정규화 — 프론트 jobMatchesAppl_(index.html)과 동일 계약.
function normalizeJobKey_(s) { return String(s || "").replace(/\s|[()（）]/g, "").toLowerCase(); }

// 한 공고(포지션명)에 매칭되는 지원자 배열 반환. 프론트와 동일 규칙(양방향 부분일치 len≥4 + 지원포지션 폴백).
function matchApplicantsForJob_(applRows, jobTitle) {
  var hk = normalizeJobKey_(jobTitle); if (hk.length < 4) return [];
  return applRows.filter(function (a) {
    var cands = [];
    var lk = a["연결 공고"]; if (lk) String(lk).split(/[,/|]/).forEach(function (x) { cands.push(x); });
    if (a["지원 포지션"]) cands.push(a["지원 포지션"]);
    return cands.some(function (r) { var rn = normalizeJobKey_(r); return rn.length >= 4 && (hk.indexOf(rn) >= 0 || rn.indexOf(hk) >= 0); });
  });
}
function isFinalStage_(stg) { var s = String(stg || "").replace(/\s/g, ""); return s === "최종합격" || s === "합격"; }
function isRejectedStage_(stg) { return /불합격|탈락/.test(String(stg || "")); }
// 진행중 = 최종합격/불합격/탈락/보류가 아닌 전형 단계(=아직 처리 필요)
function isActiveStage_(stg) { return !isFinalStage_(stg) && !isRejectedStage_(stg) && !/보류/.test(String(stg || "")); }

function handleHireComplete_(body) {
  var pageId   = (body.applicantPageId || "").trim();
  var applName = (body.name || body.applicant || "").trim();
  var joinDate = (body.joinDate || "").trim();
  var dept     = (body.dept || "").trim();
  var sosok    = (body.sosok || "").trim();
  var rank     = (body.rank || "").trim();
  var empType  = (body.empType || "정규직").trim();
  var phone    = (body.phone || "").trim();
  var email    = (body.email || "").trim();

  if (!pageId && !applName) return { ok: false, error: "applicant_required" };
  if (!joinDate) return { ok: false, error: "joinDate_required" };
  if (!dept) return { ok: false, error: "dept_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var applSheet = { attempted: true, ok: false, msg: "" };
  var registerResult = null;

  // 1) 지원자 시트의 전형 단계를 "최종 합격"으로 갱신 + 누락 정보 채우기
  var applSh = getOrCreateSheet_(ss, SHEET_APPL, SCHEMAS.appl);
  var rowNum = pageId ? findRowByPageId_(applSh, pageId) : -1;
  if (rowNum < 0 && applName) {
    var r = findRowByCol_(applSh, "지원자명", applName);
    if (r.found) rowNum = r.row;
  }
  if (rowNum > 0) {
    try {
      setCellByHeader_(applSh, rowNum, "전형 단계", "최종 합격");
      setCellByHeader_(applSh, rowNum, "합류 가능일", joinDate);
      if (!applName) applName = getCellByHeader_(applSh, rowNum, "지원자명") || "";
      if (!phone)    phone    = getCellByHeader_(applSh, rowNum, "연락처") || "";
      if (!email)    email    = getCellByHeader_(applSh, rowNum, "이메일") || "";
      applSheet.ok = true;
      applSheet.msg = "지원자 시트 '최종 합격' 처리";
    } catch (e) {
      applSheet.ok = false;
      applSheet.msg = "지원자 시트 업데이트 실패: " + (e.message || e);
    }
  } else {
    applSheet.ok = false;
    applSheet.msg = "지원자 시트에서 행을 못 찾음 (이름·pageId 불일치)";
  }

  // 2) 현재근무자 시트에 등록 (handleRegister_ 재사용)
  registerResult = handleRegister_({
    name: applName, dept: dept, sosok: sosok, rank: rank,
    joinDate: joinDate, phone: phone, email: email, empType: empType
  });

  // [추가 2026-07-16 A-5 P2·G3] 공고 충원 현황 계산(읽기 전용 — hire 시트에 쓰지 않음).
  //   자동으로 마감 쓰지 않는다(정책 확정) — "제안"만 응답에 실어보내고, 마감 실행은 허브 UI 확인 → update-hire 경로.
  var __posting = { matched: false };
  try {
    var hireRows = readSchemaSheet_(ss, SHEET_HIRE, SCHEMAS.hire);
    var applRows = readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl);
    var applA = null; if (rowNum > 0) applA = applRows.filter(function (x) { return x["_sheet_row"] === rowNum; })[0];
    var jobCandTitle = (applA && (applA["지원 포지션"] || applA["연결 공고"])) || dept;
    var jobHit = hireRows.filter(function (h) {
      var hk = normalizeJobKey_(h["포지션명"]); var jc = normalizeJobKey_(jobCandTitle);
      return hk.length >= 4 && jc.length >= 4 && (hk.indexOf(jc) >= 0 || jc.indexOf(hk) >= 0);
    })[0];
    if (jobHit) {
      var openings = Number(String(jobHit["모집 인원"] || "").trim());
      var filled = matchApplicantsForJob_(applRows, jobHit["포지션명"]).filter(function (a) { return isFinalStage_(a["전형 단계"]); }).length;
      var validOpenings = isFinite(openings) && openings > 0;
      __posting = {
        matched: true, jobRow: jobHit["_sheet_row"], jobName: jobHit["포지션명"],
        openings: validOpenings ? openings : "", filled: filled,
        remaining: validOpenings ? Math.max(0, openings - filled) : "",
        suggestClose: validOpenings && (openings - filled) <= 0 && jobHit["채용 상태"] !== "마감",
        reason: validOpenings ? "" : "모집인원 미기재 — 자동 판정 불가"
      };
    }
  } catch (e) { __posting = { matched: false, error: String(e) }; }

  return {
    ok: registerResult.ok === true,
    applicantName: applName,
    applicantSheet: applSheet,
    sheet: { attempted: true, ok: registerResult.ok === true, msg: registerResult.msg || "" },
    register: registerResult,
    posting: __posting,
    hireMessage: applName + " 입사 확정 (시트 등록 + 온보딩 체크리스트 생성)",
    msg: registerResult.msg || ""
  };
}

// 지원자 시트에서 pageId로 행 번호 찾기 (운영허브 normId 매칭)
function findRowByPageId_(sh, pageId) {
  var target = String(pageId || "").toLowerCase();
  if (!target) return -1;
  var last = sh.getLastRow();
  if (last < NEW_DATA_START_ROW) return -1;
  for (var r = NEW_DATA_START_ROW; r <= last; r++) {
    var url = makeSheetUrl_(sh.getName(), r);
    var m = url.match(/[0-9a-f]{32}$/i);
    if (m && m[0].toLowerCase() === target) return r;
  }
  return -1;
}

// =====================================================================
// SAVE EVAL — 인사평가 결과 저장
// =====================================================================
// [추가 2026-07-13 A-4] 결정적 산출 헬퍼 — 시스템화 우선: A~F 환산식·숫자 파싱을 코드로 고정(AI 재량 배제).
function evalNum_(v) {
  if (v === undefined || v === null || v === "") return null;
  var x = Number(v);
  return isNaN(x) ? null : x;
}
// 종합점수(100점 만점) → A~F 6등급. 설계서 §5.4 단일 기준(90/80/70/60/50).
function computeEvalGrade_(total) {
  var t = Number(total);
  if (isNaN(t)) return "";
  if (t >= 90) return "A";
  if (t >= 80) return "B";
  if (t >= 70) return "C";
  if (t >= 60) return "D";
  if (t >= 50) return "E";
  return "F";
}

function handleSaveEval_(body) {
  var evalName  = (body.evalName  || body.title || "").trim();
  var target    = (body.target    || body.name  || "").trim();
  var family    = (body.family    || body.jobFamily || "").trim();   // 직군(정기 성과평가 5직군)
  var evalType  = (body.evalType  || (family ? "정기 성과평가" : "직원평가")).trim();
  var cycle     = (body.cycle     || "반기").trim();
  var startDate = (body.startDate || "").trim();
  var endDate   = (body.endDate   || "").trim();
  var evaluator = (body.evaluator || "").trim();
  var bonus     = body.bonus !== undefined ? body.bonus : "";
  // [웨이브1 정정 2026-07-14 A-4] 가산점(운영부 업무평가 SSOT 산출) 정규화: 숫자면 0~10 클램프(상한 방어), 비숫자/미전달은 "" 보존.
  var bonusNum  = evalNum_(bonus);
  if (bonusNum !== null) { bonusNum = Math.max(0, Math.min(10, Math.round(bonusNum * 10) / 10)); bonus = bonusNum; }
  var link      = (body.link      || "").trim();
  var reward    = body.reward === true || body.reward === "Y" || body.reward === "true";
  var rewardText= (body.rewardText|| "").trim();
  var feedback  = (body.feedback  || "").trim();

  // --- 3기둥(직무성과·공통역량·태도) 결정적 산출: 컴포넌트 100환산 점수 3개가 모두 오면 서버가 종합·등급을 재계산 ---
  //     (설계서 §5.3 종합 = KPI×wKpi + 역량×wComp + 태도×wAtt · §3.4 정직성 게이트 · §5.4 A~F). 없으면 기존 total/grade 그대로(하위호환).
  var kpiScore  = evalNum_(body.kpiScore);    // 직무성과 KPI 점수(0~100)
  var compScore = evalNum_(body.compScore);   // 공통역량 5축 점수(0~100)
  var attScore  = evalNum_(body.attScore);    // 태도·가치 점수(0~100)
  var honesty   = (body.honestyViolation === true || body.honestyViolation === "Y" || body.honestyViolation === "true");
  var wKpi  = evalNum_(body.wKpi);
  var wComp = evalNum_(body.wComp);
  var wAtt  = evalNum_(body.wAtt);
  var total, grade;
  var computed = (kpiScore !== null && compScore !== null && attScore !== null);
  if (computed) {
    if (honesty && attScore > 40) attScore = 40;                 // 정직성 게이트: 태도 블록 2점(=40/100) 상한
    if (wKpi === null || wComp === null || wAtt === null) { wKpi = 50; wComp = 35; wAtt = 15; }
    var wsum = wKpi + wComp + wAtt;
    if (wsum <= 0) { wKpi = 50; wComp = 35; wAtt = 15; wsum = 100; }
    total = Math.round((kpiScore * wKpi + compScore * wComp + attScore * wAtt) / wsum * 10) / 10;
    grade = computeEvalGrade_(total);
  } else {
    total = body.total !== undefined ? body.total : "";
    grade = (body.grade || "").trim();
    if (grade === "" && total !== "" && !isNaN(Number(total))) grade = computeEvalGrade_(total);
  }

  // [웨이브1 정정 2026-07-14 A-4] 최종점수 = 기본 3기둥 총점(≤100) + 가산점(≤10) → 등급 재산정.
  //   정기 성과평가 산출 경로(computed)에서 가산점>0일 때만 등급 상향 반영. '총점' 열은 기본(≤100) 그대로 보존,
  //   '가산점' 열은 클램프값, '평가 등급'만 최종점수 기준. 레거시 직원평가(비산출·bonus 미전달)는 등급 무변경(하위호환).
  var finalScore = (computed && !isNaN(Number(total))) ? Math.round((Number(total) + (bonusNum || 0)) * 10) / 10 : "";
  if (computed && bonusNum !== null && bonusNum > 0) grade = computeEvalGrade_(finalScore);

  if (!target) return { ok: false, error: "target_required" };
  if (!evalName) evalName = (cycle || "회차") + " " + target + " " + evalType + (family ? " (" + family + ")" : "");

  // 산출 시 표준 브레이크다운을 피드백에 병기 — 15열 스키마/행 고정 보존(별도 열 추가 없음)
  if (computed) {
    var hasBonus = (bonusNum !== null && bonusNum > 0);
    var bd = "■ 정기 성과평가 산출: 기본 " + total + "점"
      + (hasBonus ? (" + 가산점 " + bonusNum + "점 = 최종 " + finalScore + "점") : "")
      + " · 등급 " + grade
      + (honesty ? " · [정직성 게이트 적용]" : "")
      + "\n■ 직무성과 KPI: " + kpiScore + "점 (가중 " + wKpi + "%)"
      + "\n■ 공통역량 5축: " + compScore + "점 (가중 " + wComp + "%)"
      + "\n■ 태도·가치: " + attScore + "점 (가중 " + wAtt + "%)"
      + (hasBonus ? ("\n■ 가산점(운영부 업무평가 SSOT): +" + bonusNum + "점 (최대 +10)") : "")
      + (family ? "\n■ 직군: " + family : "");
    if (body.breakdown) bd += "\n" + String(body.breakdown).trim();
    feedback = feedback ? (bd + "\n\n" + feedback) : bd;
  }

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_EVAL, SCHEMAS.eval);
  var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nextRow, 1, 1, SCHEMAS.eval.length).setValues([[
    evalName, target, evalType, cycle, startDate, endDate, evaluator,
    total, bonus, grade, link, reward ? "Y" : "N", rewardText, feedback, ""
  ]]);

  // [추가 2026-07-16 A-5 P4·G9] 대상자 재직 검증 — 거부 아님(저장은 무조건 성공). 경고 필드만 부가.
  //   이름변형·계약직·직군대상 등 정당 케이스를 막지 않기 위해 표면화만, 판단은 사람 몫.
  var __empWarn = "";
  try {
    var __emp = readCurrentSheet_(ss);
    var __tk = String(target || "").replace(/\s/g, "");
    var __hit = __emp.some(function (e) { return String(e["성명"] || e["이름"] || "").replace(/\s/g, "") === __tk && e["재직 상태"] !== "퇴사"; });
    if (!__hit) __empWarn = "대상자('" + target + "')가 현재근무자(재직)에 없음 — 퇴사자/오타/미등록 여부 확인 권장";
  } catch (e) { }

  return { ok: true, msg: target + " 평가 저장 (" + sh.getName() + " " + nextRow + "행)", total: total, bonus: (bonusNum === null ? "" : bonusNum), finalScore: finalScore, grade: grade, computed: computed, warning: __empWarn };
}

// =====================================================================
// [추가 2026-07-14 A-4] 직무성과(50%) 업무평가 — 저장/조회 (admin 전용)
//   설계: 확정스펙(웨이브1 매니저 확정) — COO 업무보드는 읽기전용 소스(무변경), 완성도·성과점수는 HR 관리자
//   영역(이 탭)에 저장. 성과점수 1~5(×20 환산), 결합=곱셈(완성도%×성과환산), 직무성과=중요도가중 성취도 평균(0~100).
//   완료 판정=관리자가 채점(완성도·성과 입력)한 업무 기준(완료일 필드 부재 우회). 중요도 미책정=계산 제외+경고.
//   서버가 산출을 재계산(프론트와 이중 결정화) — 클라이언트 값 신뢰하지 않음.
// =====================================================================
function computeJobPerf_(tasks) {
  var list = (tasks && tasks.length) ? tasks : [];
  var num = 0, den = 0, scored = 0, unrated = 0, total = list.length;
  var norm = [];
  for (var i = 0; i < total; i++) {
    var t = list[i] || {};
    var comp = evalNum_(t.completeness);           // 완성도 0~100(%)
    var q    = evalNum_(t.quality);                // 성과점수 1~5
    var diff = String(t.diff || "").trim();        // 업무 중요도(난이도) 하/중/상
    var w    = WORKEVAL_DIFF_WEIGHT[diff] || 0;    // 중요도 가중치(미책정=0)
    var hasScore = (comp !== null && comp >= 0 && comp <= 100 && q !== null && q >= 1 && q <= 5);
    var ach = null;
    if (hasScore) {
      scored++;
      ach = Math.round((comp / 100) * (q * 20) * 10) / 10;   // 곱셈 결합: 완성도%×(성과×20) → 0~100
      if (w > 0) { num += w * ach; den += w; } else { unrated++; }  // 채점됐으나 난이도 미책정 → 경고 대상
    }
    norm.push({
      id: String(t.id || ""), title: String(t.title || ""), owner: String(t.owner || ""),
      category: String(t.category || ""), status: String(t.status || ""),
      diff: diff, weight: w, completeness: comp, quality: q, achievement: ach
    });
  }
  var jobPerf = den > 0 ? Math.round(num / den * 10) / 10 : null;
  // [웨이브1 정정 2026-07-14 A-4] 정규화 직무성과(0~100) → 운영부 가산점(최대 +10) 선형 환산(÷10). 상·하한 방어.
  //   설계정정: 직무성과 50% 자동대체(프리필) 폐기 → 산출값은 '가산점(≤+10)'으로만 쓰인다(save-eval 가산점 필드).
  var bonus = (jobPerf === null) ? null : Math.max(0, Math.min(10, Math.round(jobPerf / 10 * 10) / 10));
  return { jobPerf: jobPerf, bonus: bonus, weightSum: den, scored: scored, unrated: unrated, total: total, coverage: scored + "/" + total, tasks: norm };
}

function handleSaveWorkEval_(body) {
  var target    = (body.target || body.name || "").trim();
  var period    = (body.period || "").trim();
  var evaluator = (body.evaluator || "").trim();
  var dualFlag  = (body.dualFlag === true || body.dualFlag === "Y" || body.dualFlag === "true") ? "Y" : "";
  if (!target) return { ok: false, error: "target_required", message: "대상자가 필요합니다." };
  if (!period) return { ok: false, error: "period_required", message: "평가기간이 필요합니다." };
  var tasks = (body.tasks && Array.isArray(body.tasks)) ? body.tasks : [];
  var c = computeJobPerf_(tasks);   // 서버 재계산(권위값)
  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_WORKEVAL, SCHEMAS.workeval);
  // 대상자+평가기간으로 기존 행 탐색 → in-place 갱신, 없으면 맨 아래 append (행 삽입/삭제 없음)
  var lastRow = sh.getLastRow();
  var foundRow = 0;
  if (lastRow >= NEW_DATA_START_ROW) {
    var keyVals = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, 2).getValues();
    for (var i = 0; i < keyVals.length; i++) {
      if (String(keyVals[i][0]).trim() === target && String(keyVals[i][1]).trim() === period) { foundRow = NEW_DATA_START_ROW + i; break; }
    }
  }
  var writeRow = foundRow || Math.max(lastRow + 1, NEW_DATA_START_ROW);
  sh.getRange(writeRow, 1, 1, SCHEMAS.workeval.length).setValues([[
    target, period, (c.jobPerf === null ? "" : c.jobPerf), c.weightSum, c.coverage, c.unrated, dualFlag,
    "v2: 곱셈(완성도%×성과점수×20)·중요도가중 성취도 평균 → 운영부 가산점(÷10, ≤+10)", evaluator, JSON.stringify(c.tasks), now
  ]]);
  return {
    ok: true, action: "save-work-eval", target: target, period: period, jobPerf: c.jobPerf, bonus: c.bonus,
    weightSum: c.weightSum, coverage: c.coverage, unrated: c.unrated, scored: c.scored, total: c.total,
    dualFlag: dualFlag, row: writeRow, updated: !!foundRow
  };
}

function handleGetWorkEval_(body) {
  var target = (body.target || body.name || "").trim();
  var period = (body.period || "").trim();
  if (!target) return { ok: false, error: "target_required", message: "대상자가 필요합니다." };
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_WORKEVAL);
  if (!sh) return { ok: true, found: false, target: target, period: period, latest: null, results: [] };
  var lastRow = sh.getLastRow();
  if (lastRow < NEW_DATA_START_ROW) return { ok: true, found: false, target: target, period: period, latest: null, results: [] };
  var n = SCHEMAS.workeval.length;
  var data = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, n).getValues();
  var out = [];
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    if (String(r[0]).trim() !== target) continue;
    if (period && String(r[1]).trim() !== period) continue;
    var tasks = [];
    try { tasks = JSON.parse(r[9] || "[]"); } catch (e) { tasks = []; }
    var jp = (r[2] === "" ? null : Number(r[2]));
    // [웨이브1 정정 2026-07-14 A-4] 저장 직무성과(0~100)에서 가산점(≤+10) 결정적 파생 — 프리필 대상에게 참고표시.
    var bn = (jp === null || isNaN(jp)) ? null : Math.max(0, Math.min(10, Math.round(jp / 10 * 10) / 10));
    out.push({
      target: r[0], period: r[1], jobPerf: jp, bonus: bn, weightSum: r[3],
      coverage: r[4], unrated: r[5], dualFlag: r[6], formulaVer: r[7], evaluator: r[8],
      tasks: tasks, savedAt: r[10], _sheet_row: NEW_DATA_START_ROW + i
    });
  }
  out.reverse();  // 최신 저장분 우선
  return { ok: true, found: out.length > 0, target: target, period: period, latest: (out.length ? out[0] : null), results: out };
}

// =====================================================================
// [추가 2026-07-14 A-4 웨이브2] 자기평가·리더십평가(상향) — 저장/조회
//   확정스펙(매니저 확정): 자기평가=팀장평가와 동일 항목(5축+태도)·5점, 본인 선제출, 등급 미산출·미반영(1년차 참고).
//   리더십평가=부서원→팀장 6항목 5점+개선서술, 평가자 실명 미저장(비식별), 응답 3명 미만이면 요약 전면 비공개(k-익명),
//   원자료는 매니저(admin)만, 리더 공유용은 집계요약(k 통과 시)만. 두 트랙 모두 등급·처우 미반영.
//   저장 위치: 관리자 잠금탭(자기평가/리더십평가) — db:eval 공개읽기·public-stats·autolog 미노출(PII/민감 노출면 0).
// =====================================================================
function handleSaveSelfEval_(body) {
  var target = (body.target || body.name || "").trim();
  var period = (body.period || "").trim();
  var cycle  = (body.cycle  || "반기").trim();
  if (!target) return { ok: false, error: "target_required", message: "대상자(본인)가 필요합니다." };
  if (!period) return { ok: false, error: "period_required", message: "평가기간이 필요합니다." };
  function normScores(arr) {
    var list = (arr && arr.length) ? arr : [];
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var it = list[i] || {};
      var s = evalNum_(it.score);
      if (s !== null) { if (s < 1) s = 1; if (s > 5) s = 5; }
      out.push({ k: String(it.k || ""), score: (s === null ? null : s) });
    }
    return out;
  }
  var axes = normScores(body.axes);
  var atts = normScores(body.attitudes);
  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_SELFEVAL, SCHEMAS.selfeval);
  // 대상자+평가기간 upsert(행 삽입/삭제 없음) — 본인이 마감 전 수정 가능
  var lastRow = sh.getLastRow();
  var foundRow = 0;
  if (lastRow >= NEW_DATA_START_ROW) {
    var keyVals = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, 2).getValues();
    for (var i = 0; i < keyVals.length; i++) {
      if (String(keyVals[i][0]).trim() === target && String(keyVals[i][1]).trim() === period) { foundRow = NEW_DATA_START_ROW + i; break; }
    }
  }
  var writeRow = foundRow || Math.max(lastRow + 1, NEW_DATA_START_ROW);
  sh.getRange(writeRow, 1, 1, SCHEMAS.selfeval.length).setValues([[
    target, period, cycle, JSON.stringify(axes), JSON.stringify(atts),
    String(body.jobPerfSelf || "").trim(), String(body.growthArea || "").trim(),
    String(body.supportNeeded || "").trim(), String(body.strength || "").trim(),
    String(body.devArea || "").trim(), now
  ]]);
  // ⚠등급·총점 미산출·미반영 — 인사평가(SHEET_EVAL) 무기록. 팀장 평가지 병렬 갭·면담 참고 전용.
  return { ok: true, action: "save-self-eval", target: target, period: period, row: writeRow, updated: !!foundRow, graded: false, axesCount: axes.length, attCount: atts.length };
}

function handleGetSelfEval_(body) {
  var target = (body.target || body.name || "").trim();
  var period = (body.period || "").trim();
  if (!target) return { ok: false, error: "target_required", message: "대상자가 필요합니다." };
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_SELFEVAL);
  if (!sh) return { ok: true, found: false, target: target, period: period, latest: null, results: [], graded: false };
  var lastRow = sh.getLastRow();
  if (lastRow < NEW_DATA_START_ROW) return { ok: true, found: false, target: target, period: period, latest: null, results: [], graded: false };
  var n = SCHEMAS.selfeval.length;
  var data = sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, n).getValues();
  var out = [];
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    if (String(r[0]).trim() !== target) continue;
    if (period && String(r[1]).trim() !== period) continue;
    var axes = [], atts = [];
    try { axes = JSON.parse(r[3] || "[]"); } catch (e) { axes = []; }
    try { atts = JSON.parse(r[4] || "[]"); } catch (e) { atts = []; }
    out.push({
      target: r[0], period: r[1], cycle: r[2], axes: axes, attitudes: atts,
      jobPerfSelf: r[5], growthArea: r[6], supportNeeded: r[7], strength: r[8], devArea: r[9], savedAt: r[10],
      _sheet_row: NEW_DATA_START_ROW + i
    });
  }
  out.reverse();
  return { ok: true, found: out.length > 0, target: target, period: period, latest: (out.length ? out[0] : null), results: out, graded: false };
}

function handleSaveLeadershipEval_(body, channel) {
  var target = (body.target || body.leader || "").trim();
  var period = (body.period || "").trim();
  if (!target) return { ok: false, error: "target_required", message: "대상 팀장을 선택해 주세요." };
  if (!period) return { ok: false, error: "period_required", message: "평가기간이 필요합니다." };
  var raw = (body.items && body.items.length) ? body.items : [];
  var items = [], scored = 0;
  for (var i = 0; i < raw.length; i++) {
    var it = raw[i] || {};
    var s = evalNum_(it.score);
    if (s !== null) { if (s < 1) s = 1; if (s > 5) s = 5; scored++; }
    items.push({ k: String(it.k || ""), score: (s === null ? null : s) });
  }
  if (scored === 0) return { ok: false, error: "no_score", message: "최소 한 항목 이상 점수를 입력해 주세요." };
  var improve = String(body.improve || body.comment || "").trim();
  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss");
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_LEADEREVAL, SCHEMAS.leadereval);
  // append-only(제출 1건=1행, 맨 아래). ⚠평가자 신원/식별정보 미저장(비식별·역추적 차단). '제출경로'는 통로(self/admin)일 뿐.
  var writeRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(writeRow, 1, 1, SCHEMAS.leadereval.length).setValues([[
    target, period, JSON.stringify(items), improve, (channel || "self"), now
  ]]);
  // 제출자에게 진행 응답수를 알리지 않는다(몇 번째인지 역추적 힌트 차단).
  return { ok: true, action: "leadership-submit", target: target, period: period, message: "익명 제출이 접수되었습니다. 감사합니다." };
}

function handleGetLeadershipEval_(body) {
  var target = (body.target || body.leader || "").trim();
  var period = (body.period || "").trim();
  var mode   = (body.mode || (target ? "summary" : "index")).trim();
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_LEADEREVAL);
  var n = SCHEMAS.leadereval.length;
  if (!sh) {
    if (mode === "index") return { ok: true, mode: "index", period: period, minK: LEADERSHIP_MIN_K, leaders: [] };
    return { ok: true, mode: mode, target: target, period: period, found: false, n: 0, locked: (mode === "summary"), minK: LEADERSHIP_MIN_K };
  }
  var lastRow = sh.getLastRow();
  var data = (lastRow >= NEW_DATA_START_ROW) ? sh.getRange(NEW_DATA_START_ROW, 1, lastRow - NEW_DATA_START_ROW + 1, n).getValues() : [];

  // ---- index: 기간별 대상팀장 응답수 개요(점수 미노출) — 매니저가 k 충족 여부만 확인 ----
  if (mode === "index") {
    var counts = {};
    for (var i = 0; i < data.length; i++) {
      var r = data[i];
      if (period && String(r[1]).trim() !== period) continue;
      var t = String(r[0]).trim(); if (!t) continue;
      counts[t] = (counts[t] || 0) + 1;
    }
    var leaders = [];
    for (var ck in counts) { if (counts.hasOwnProperty(ck)) leaders.push({ target: ck, n: counts[ck], locked: (counts[ck] < LEADERSHIP_MIN_K) }); }
    leaders.sort(function (a, b) { return a.target < b.target ? -1 : (a.target > b.target ? 1 : 0); });
    return { ok: true, mode: "index", period: period, minK: LEADERSHIP_MIN_K, leaders: leaders };
  }

  if (!target) return { ok: false, error: "target_required", message: "대상 팀장을 선택해 주세요." };

  // ---- 대상 팀장 응답 수집 + 항목 평균 ----
  var responses = [], agg = {}, order = [];
  for (var j = 0; j < data.length; j++) {
    var row = data[j];
    if (String(row[0]).trim() !== target) continue;
    if (period && String(row[1]).trim() !== period) continue;
    var itms = [];
    try { itms = JSON.parse(row[2] || "[]"); } catch (e) { itms = []; }
    for (var m = 0; m < itms.length; m++) {
      var key = String(itms[m].k || ""), sc = evalNum_(itms[m].score);
      if (!key) continue;
      if (!agg[key]) { agg[key] = { sum: 0, cnt: 0 }; order.push(key); }
      if (sc !== null) { agg[key].sum += sc; agg[key].cnt++; }
    }
    responses.push({ items: itms, improve: String(row[3] || ""), savedAt: row[5] });
  }
  var count = responses.length;
  var averages = order.map(function (key) { var a = agg[key]; return { k: key, avg: (a.cnt > 0 ? Math.round(a.sum / a.cnt * 100) / 100 : null), n: a.cnt }; });

  // ---- summary(리더 공유용): k-익명 게이트 — 3명 미만이면 전면 비공개(정확 응답수도 미노출) ----
  if (mode === "summary") {
    if (count < LEADERSHIP_MIN_K) {
      return { ok: true, mode: "summary", target: target, period: period, locked: true, minK: LEADERSHIP_MIN_K,
        message: "응답자가 " + LEADERSHIP_MIN_K + "명 미만이어서 익명성 보호를 위해 결과를 공개하지 않습니다." };
    }
    return { ok: true, mode: "summary", target: target, period: period, locked: false, n: count, minK: LEADERSHIP_MIN_K, averages: averages };
  }

  // ---- raw(매니저 전용 원자료): k 무관 열람. 개별 응답 포함(평가자 신원은 애초에 미저장). 표본 3 미만 경고. ----
  return { ok: true, mode: "raw", target: target, period: period, n: count, minK: LEADERSHIP_MIN_K,
    lowSample: (count < LEADERSHIP_MIN_K), averages: averages, responses: responses,
    notice: (count < LEADERSHIP_MIN_K ? "표본 " + LEADERSHIP_MIN_K + " 미만 — 해석 주의·리더 개인에게 공유 금지." : "") };
}

// =====================================================================
// ADD JOB — 채용공고 추가
// =====================================================================
function handleAddJob_(body) {
  var title    = (body.title || body.position || "").trim();
  var dept     = (body.dept || "").trim();
  var jobType  = (body.jobType || body.type || "정규직").trim();
  var status   = (body.status || "공고 준비").trim();
  var channels = (body.channels || []);
  if (typeof channels === "string") channels = [channels];
  var priority = (body.priority || "보통").trim();
  var cLevel   = (body.cLevel || []);
  if (typeof cLevel === "string") cLevel = [cLevel];
  var startDate = (body.startDate || "").trim();
  var endDate   = (body.endDate || "").trim();
  var doneDate  = (body.doneDate || "").trim();
  var openings  = body.openings !== undefined ? body.openings : "";
  var salary    = (body.salary || "").trim();
  var duty      = (body.duty || "").trim();
  var qual      = (body.qual || "").trim();
  var memo      = (body.memo || "").trim();

  if (!title) return { ok: false, error: "title_required" };

  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_HIRE, SCHEMAS.hire);
  var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  sh.getRange(nextRow, 1, 1, SCHEMAS.hire.length).setValues([[
    title, dept, jobType, status, channels.join(", "), priority, cLevel.join(", "),
    startDate, endDate, doneDate, openings, 0, 0, salary, duty, qual, memo, ""
  ]]);
  return { ok: true, msg: "채용공고 '" + title + "' 추가 (" + sh.getName() + " " + nextRow + "행)" };
}

// =====================================================================
// MIGRATE NOTION → SHEETS (1회성)
//
// 실행 순서:
//   1. 워크시트 5개 신설 + 헤더 작성 (없으면 생성, 있으면 유지)
//   2. 각 Notion DB 전수 조회 → 시트에 추가
//   3. 결과 로그 반환
// =====================================================================
function migrateNotionToSheets() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var log = ["=== Notion → 시트 마이그레이션 시작 ===",
             "시작: " + Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss")];

  // 1. 5개 워크시트 생성·헤더 보장
  getOrCreateSheet_(ss, SHEET_HIRE,   SCHEMAS.hire);
  getOrCreateSheet_(ss, SHEET_APPL,   SCHEMAS.appl);
  getOrCreateSheet_(ss, SHEET_EVAL,   SCHEMAS.eval);
  getOrCreateSheet_(ss, SHEET_ONBO,   SCHEMAS.onbo);
  getOrCreateSheet_(ss, SHEET_RESIGN, SCHEMAS.resign);
  log.push("워크시트 5개 준비 완료");

  // 2. 각 DB 마이그레이션
  var counts = {};
  try { counts.hire = migrateHire_(ss);   log.push("[채용공고] " + counts.hire + "건"); }
  catch (e) { log.push("[채용공고] 오류: " + e.message); }

  try { counts.appl = migrateAppl_(ss);   log.push("[지원자] " + counts.appl + "건"); }
  catch (e) { log.push("[지원자] 오류: " + e.message); }

  try { counts.eval = migrateEval_(ss);   log.push("[인사평가] " + counts.eval + "건"); }
  catch (e) { log.push("[인사평가] 오류: " + e.message); }

  try { counts.onbo = migrateOnbo_(ss);   log.push("[입사·온보딩] " + counts.onbo + "건"); }
  catch (e) { log.push("[입사·온보딩] 오류: " + e.message); }

  try { counts.resign = migrateExit_(ss); log.push("[퇴사처리] " + counts.resign + "건"); }
  catch (e) { log.push("[퇴사처리] 오류: " + e.message); }

  log.push("=== 완료: " + Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm:ss") + " ===");
  var fullLog = log.join("\n");
  Logger.log(fullLog);

  return { ok: true, counts: counts, log: fullLog };
}

function migrateHire_(ss) {
  var pages = notionQueryAll_(NOTION_DATABASES.hire);
  var sh = ss.getSheetByName(SHEET_HIRE);
  var rows = [];
  pages.forEach(function (p) {
    var prop = p.properties || {};
    rows.push([
      titleOf_(prop["포지션명"]),
      selectOf_(prop["부서"]),
      selectOf_(prop["채용 유형"]),
      selectOf_(prop["채용 상태"]),
      multiSelectOf_(prop["채용 채널"]),
      selectOf_(prop["우선순위"]),
      multiSelectOf_(prop["담당 C-Level"]),
      dateOf_(prop["공고 시작일"]),
      dateOf_(prop["공고 마감일"]),
      dateOf_(prop["채용 완료일"]),
      numberOf_(prop["모집 인원"]),
      numberOf_(prop["지원자 수"]),
      numberOf_(prop["면접자 수"]),
      richTextOf_(prop["급여 범위"]),
      richTextOf_(prop["주요 업무"]),
      richTextOf_(prop["자격 요건"]),
      richTextOf_(prop["비고"]),
      p.url || ""
    ]);
  });
  if (rows.length) {
    var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
    sh.getRange(nextRow, 1, rows.length, SCHEMAS.hire.length).setValues(rows);
  }
  return rows.length;
}

function migrateAppl_(ss) {
  var pages = notionQueryAll_(NOTION_DATABASES.appl);
  var sh = ss.getSheetByName(SHEET_APPL);
  var rows = [];
  pages.forEach(function (p) {
    var prop = p.properties || {};
    rows.push([
      titleOf_(prop["지원자명"]),
      relationCountOf_(prop["연결 공고"]),  // 공고 페이지 ID 카운트만 표기 (이름은 후처리)
      richTextOf_(prop["지원 포지션"]),
      selectOf_(prop["지원 경로"]),
      selectOf_(prop["전형 단계"]),
      selectOf_(prop["면접 평점"]),
      dateOf_(prop["지원일"]),
      dateOf_(prop["면접 일정"]),
      dateOf_(prop["합류 가능일"]),
      richTextOf_(prop["담당 면접관"]),
      phoneOf_(prop["연락처"]),
      emailOf_(prop["이메일"]),
      richTextOf_(prop["메모"]),
      p.url || ""
    ]);
  });
  if (rows.length) {
    var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
    sh.getRange(nextRow, 1, rows.length, SCHEMAS.appl.length).setValues(rows);
  }
  return rows.length;
}

function migrateEval_(ss) {
  var pages = notionQueryAll_(NOTION_DATABASES.eval);
  var sh = ss.getSheetByName(SHEET_EVAL);
  var rows = [];
  pages.forEach(function (p) {
    var prop = p.properties || {};
    var period = prop["평가 기간"] || {};
    var ds = period.date || {};
    rows.push([
      titleOf_(prop["평가명"]),
      relationCountOf_(prop["대상자"]),
      selectOf_(prop["평가 종류"]),
      selectOf_(prop["평가 주기"]),
      ds.start || "",
      ds.end || "",
      richTextOf_(prop["평가자"]),
      numberOf_(prop["총점"]),
      numberOf_(prop["가산점"]),
      selectOf_(prop["평가 등급"]),
      (prop["평가지 링크"] && prop["평가지 링크"].url) || "",
      checkOf_(prop["포상 여부"]),
      richTextOf_(prop["포상 내역"]),
      richTextOf_(prop["피드백"]),
      p.url || ""
    ]);
  });
  if (rows.length) {
    var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
    sh.getRange(nextRow, 1, rows.length, SCHEMAS.eval.length).setValues(rows);
  }
  return rows.length;
}

function migrateOnbo_(ss) {
  var pages = notionQueryAll_(NOTION_DATABASES.onbo);
  var sh = ss.getSheetByName(SHEET_ONBO);
  var rows = [];
  pages.forEach(function (p) {
    var prop = p.properties || {};
    rows.push([
      titleOf_(prop["체크 항목"]),
      selectOf_(prop["카테고리"]),
      richTextOf_(prop["대상 신입 직원"]),
      richTextOf_(prop["담당자"]),
      dateOf_(prop["완료 기한"]),
      checkOf_(prop["완료 여부"]),
      dateOf_(prop["완료일"]),
      richTextOf_(prop["비고"]),
      p.url || ""
    ]);
  });
  if (rows.length) {
    var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
    sh.getRange(nextRow, 1, rows.length, SCHEMAS.onbo.length).setValues(rows);
  }
  return rows.length;
}

function migrateExit_(ss) {
  var pages = notionQueryAll_(NOTION_DATABASES.exit);
  var sh = ss.getSheetByName(SHEET_RESIGN);
  var rows = [];
  // 연결 임직원 ID → 이름 매핑 (한 번만 임직원 DB 조회)
  var empMap = {};
  try {
    var emps = notionQueryAll_(NOTION_DATABASES.emp);
    emps.forEach(function (e) {
      var nm = titleOf_(e.properties && e.properties["성명"]);
      if (nm) empMap[e.id.replace(/-/g, "")] = nm;
    });
  } catch (e) {}

  pages.forEach(function (p) {
    var prop = p.properties || {};
    var rel = prop["연결 임직원"] && prop["연결 임직원"].relation;
    var linkedName = "";
    if (rel && rel.length) {
      var pid = rel[0].id.replace(/-/g, "");
      linkedName = empMap[pid] || "";
    }
    rows.push([
      titleOf_(prop["처리 건명"]),
      linkedName,
      selectOf_(prop["퇴사 유형"]),
      dateOf_(prop["퇴사 신청일"]),
      dateOf_(prop["최종 근무일"]),
      richTextOf_(prop["퇴사 사유"]),
      richTextOf_(prop["면담 내용"]),
      checkOf_(prop["퇴사 면담 여부"]),
      checkOf_(prop["장비 반납 여부"]),
      checkOf_(prop["시스템 계정 회수"]),
      checkOf_(prop["퇴직금 지급 여부"]),
      dateOf_(prop["퇴직금 지급일"]),
      checkOf_(prop["처리 완료 여부"]),
      p.url || ""
    ]);
  });
  if (rows.length) {
    var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
    sh.getRange(nextRow, 1, rows.length, SCHEMAS.resign.length).setValues(rows);
  }
  return rows.length;
}

// Notion DB 전체 페이지 조회 (page_size 100, has_more 처리)
function notionQueryAll_(databaseId) {
  var pages = [];
  var cursor = null;
  for (var i = 0; i < 50; i++) {
    var payload = { page_size: 100 };
    if (cursor) payload.start_cursor = cursor;
    var resp = UrlFetchApp.fetch("https://api.notion.com/v1/databases/" + databaseId + "/query", {
      method: "post",
      headers: {
        "Authorization": "Bearer " + NOTION_TOKEN,
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error("Notion 조회 실패 " + databaseId.slice(0,8) + ": " + resp.getContentText().slice(0,200));
    }
    var data = JSON.parse(resp.getContentText());
    (data.results || []).forEach(function (p) { pages.push(p); });
    if (!data.has_more) break;
    cursor = data.next_cursor;
  }
  return pages;
}

// =====================================================================
// 헬퍼 함수들
// =====================================================================

// 워크시트 가져오기 또는 생성 (헤더 작성)
function getOrCreateSheet_(ss, name, headers) {
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(NEW_HEADER_ROW, 1, 1, headers.length).setValues([headers]);
    sh.getRange(NEW_HEADER_ROW, 1, 1, headers.length).setFontWeight("bold").setBackground("#f0f0f0");
    sh.setFrozenRows(NEW_HEADER_ROW);
  } else {
    // 헤더가 비어 있으면 작성
    var existing = sh.getRange(NEW_HEADER_ROW, 1, 1, headers.length).getValues()[0];
    var empty = true;
    for (var i = 0; i < existing.length; i++) if (existing[i]) { empty = false; break; }
    if (empty) {
      sh.getRange(NEW_HEADER_ROW, 1, 1, headers.length).setValues([headers]);
      sh.getRange(NEW_HEADER_ROW, 1, 1, headers.length).setFontWeight("bold").setBackground("#f0f0f0");
      sh.setFrozenRows(NEW_HEADER_ROW);
    }
  }
  return sh;
}

// 두 줄 헤더(5/6행) 검색
function colByHeader_(sheet, headerName) {
  var lastCol = sheet.getLastColumn();
  if (lastCol < 1) return 0;
  var maxScanRow = Math.min(sheet.getLastRow(), 6);
  // 신규 워크시트는 1행에 헤더
  if (sheet.getName() !== SHEET_CURRENT && sheet.getName() !== SHEET_EXIT) {
    var hdr1 = sheet.getRange(NEW_HEADER_ROW, 1, 1, lastCol).getValues()[0];
    var want1 = String(headerName).replace(/\s/g, "");
    for (var c = 0; c < lastCol; c++) {
      if (String(hdr1[c]).replace(/\s/g, "") === want1) return c + 1;
    }
    return 0;
  }
  // 인사현황 시트는 5/6행 헤더
  var hdr5 = sheet.getRange(5, 1, 1, lastCol).getValues()[0];
  var hdr6 = sheet.getRange(6, 1, 1, lastCol).getValues()[0];
  var want = String(headerName).replace(/\s/g, "");
  for (var i = 0; i < lastCol; i++) {
    if (String(hdr5[i]).replace(/\s/g, "") === want) return i + 1;
    if (String(hdr6[i]).replace(/\s/g, "") === want) return i + 1;
  }
  return 0;
}

// 신규 워크시트에서 특정 헤더 셀 값 조회
function getCellByHeader_(sheet, row, headerName) {
  var col = colByHeader_(sheet, headerName);
  if (!col) return "";
  return sheet.getRange(row, col).getValue();
}

function setCellByHeader_(sheet, row, headerName, value) {
  var col = colByHeader_(sheet, headerName);
  if (!col) return false;
  sheet.getRange(row, col).setValue(value);
  return true;
}

// 신규 워크시트에서 특정 헤더 컬럼의 값과 일치하는 첫 행 찾기
function findRowByCol_(sheet, headerName, value) {
  var col = colByHeader_(sheet, headerName);
  if (!col) return { found: false };
  var last = sheet.getLastRow();
  if (last < NEW_DATA_START_ROW) return { found: false };
  var rng = sheet.getRange(NEW_DATA_START_ROW, col, last - NEW_DATA_START_ROW + 1, 1).getValues();
  var target = String(value).trim();
  for (var i = 0; i < rng.length; i++) {
    if (String(rng[i][0]).trim() === target) {
      return { found: true, row: NEW_DATA_START_ROW + i };
    }
  }
  return { found: false };
}

// 날짜 변환
function toDate_(s) {
  if (!s) return "";
  if (s instanceof Date) return s;
  var d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d;
}

// Notion 속성 추출 헬퍼
function titleOf_(prop) {
  if (!prop || !prop.title) return "";
  return prop.title.map(function (t) { return t.plain_text || ""; }).join("");
}
function richTextOf_(prop) {
  if (!prop || !prop.rich_text) return "";
  return prop.rich_text.map(function (t) { return t.plain_text || ""; }).join("");
}
function selectOf_(prop) {
  if (!prop || !prop.select) return "";
  return prop.select.name || "";
}
function multiSelectOf_(prop) {
  if (!prop || !prop.multi_select) return "";
  return prop.multi_select.map(function (o) { return o.name; }).join(", ");
}
function dateOf_(prop) {
  if (!prop || !prop.date || !prop.date.start) return "";
  return prop.date.start;
}
function numberOf_(prop) {
  if (!prop || prop.number === null || prop.number === undefined) return "";
  return prop.number;
}
function checkOf_(prop) {
  if (!prop) return "";
  return prop.checkbox ? "Y" : "N";
}
function phoneOf_(prop) {
  if (!prop) return "";
  return prop.phone_number || "";
}
function emailOf_(prop) {
  if (!prop) return "";
  return prop.email || "";
}
function relationCountOf_(prop) {
  // 마이그레이션 단계에선 relation을 페이지명으로 풀지 않고 placeholder만 둠
  if (!prop || !prop.relation) return "";
  if (prop.relation.length === 0) return "";
  return "(연결 " + prop.relation.length + "건)";
}

// 한 번에 실행 가능한 디버그 함수
function debugReadAll() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var info = {
    sheets: ss.getSheets().map(function (s) { return s.getName(); }),
    current_count: readCurrentSheet_(ss).length,
    exit_count: readExitSheet_(ss).length,
    hire_count: readSchemaSheet_(ss, SHEET_HIRE, SCHEMAS.hire).length,
    appl_count: readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl).length,
    eval_count: readSchemaSheet_(ss, SHEET_EVAL, SCHEMAS.eval).length,
    onbo_count: readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo).length,
    resign_count: readSchemaSheet_(ss, SHEET_RESIGN, SCHEMAS.resign).length
  };
  Logger.log(JSON.stringify(info, null, 2));
  return info;
}

// 부서명 → 소속 매핑 (역추론)
function mapDeptToSosok_(dept) {
  var d = String(dept || "").trim();
  if (!d) return "";
  if (d === "강습부") return "강습부";
  if (d === "관리부") return "관리부";
  if (d === "경영부") return "경영부";
  if (d === "경영지원부") return "경영지원부";
  if (d === "운영부") return "운영부";
  if (d === "시설" || d === "주차" || d === "주차관리" || d === "주차관리부" || d === "지원") return "시설부";
  return d;
}


// 송후서 지원자 1회 등록 (실행 후 삭제 가능)
function addApplicantSongHooseo() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_APPL);
  if (!sh) throw new Error('지원자 시트 없음');
  var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  var memo = '[AI 사전평가: B] 운영·시설·스케줄 4년6개월 / 안내데스크·리셉셔니스트 2년4개월(프리픽스 지점장) / 단기 근무 패턴(6개월·9개월) 사유 확인 필요. 자기소개서 3문장으로 짧음. 면접 추천 질문: 1)이직 사유 2)지점장 시절 팀워크 사례 3)업무 절차 개선 사례 4)프로세스 예외 판단 5)클레임 대응 사례.';
  var row = [
    '송후서',
    '웰페리온 운영부 사원 정규직 채용',
    '운영부 사원',
    '잡코리아',
    '서류 검토',
    'B',
    '2026-06-01',
    '',
    '',
    '',
    '010-8296-1870',
    'hoos1115@naver.com',
    memo,
    'https://www.jobkorea.co.kr/corp/Applicant/ResumeDB?Co_Pass_No=434398254&Pass_R_No=312212287&GI_No=50973551'
  ];
  sh.getRange(nextRow, 1, 1, row.length).setValues([row]);
  Logger.log('송후서 지원자 추가 완료, ' + sh.getName() + ' ' + nextRow + '행');
  return { ok: true, sheet: sh.getName(), row: nextRow };
}


// 직급 일괄 수정 (1회 실행)
function fixRanksJune() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var cur = ss.getSheetByName(SHEET_CURRENT);
  var nameCol = colByHeader_(cur, "이름") || colByHeader_(cur, "성명") || 4;
  var rankCol = colByHeader_(cur, "직책") || colByHeader_(cur, "직급") || 3;
  var last = cur.getLastRow();
  var values = cur.getRange(DATA_START_ROW, 1, last - DATA_START_ROW + 1, cur.getLastColumn()).getValues();
  var updates = { "최준용": "대리", "임정은": "대리", "나우열": "과장" };
  var changed = [];
  for (var i = 0; i < values.length; i++) {
    var nm = String(values[i][nameCol-1] || "").trim();
    if (updates[nm]) {
      var row = DATA_START_ROW + i;
      var oldVal = cur.getRange(row, rankCol).getValue();
      cur.getRange(row, rankCol).setValue(updates[nm]);
      changed.push(nm + " " + oldVal + "→" + updates[nm] + " (행 " + row + ")");
    }
  }
  Logger.log("직급 수정: " + changed.join(", "));
  return { ok: true, changed: changed };
}


// 정윤주 지원자 1회 등록
function addApplicantJungYoonju() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_APPL);
  if (!sh) throw new Error('지원자 시트 없음');
  var nextRow = Math.max(sh.getLastRow() + 1, NEW_DATA_START_ROW);
  var memo = '[AI 사전평가: A] 마스터 트레이너(최고위등급) / 자격증 4개(생스포웠지도사 보디빌딧·에어로빅) / 2023 피트니스 챔피언 1위 / MBC충북 방송 있·출··SK하이닉스 임직원 전용 트레이너. 운영·시설·안전관리 경험 편에·에장 직책 2번. 운영부 사원 지원 하셨으나 실질적 PT 업무에 더 적합 → 강습부 P.T 자리 검토 권장. 연봉 6,700만원. 면접 추천 질문: 1) 직무 적합성 이유 2) 장기근속 활용 여부 3) 연봉기대 4) 운영 vs 강습부 이동 마음 있의 5) 시설·안전관리 위기 사례.';
  var row = [
    '정윤주',
    '웰페리온 운영부 사원 정규직 채용',
    '운영부 사원',
    '잡코리아',
    '서류 검토',
    'A',
    '2026-06-05',
    '',
    '',
    '',
    '010-5672-6737',
    'myyj7506@naver.com',
    memo,
    'https://www.jobkorea.co.kr/corp/Applicant/ResumeDB?Co_Pass_No=434825467&Pass_R_No=312646607&GI_No=50973551'
  ];
  sh.getRange(nextRow, 1, 1, row.length).setValues([row]);
  Logger.log('정윤주 지원자 추가 완료, ' + sh.getName() + ' ' + nextRow + '행');
  return { ok: true, sheet: sh.getName(), row: nextRow };
}


// 지원자 3명 메모 풍부화 (1회 실행)
function enrichApplicantMemos() {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_APPL);
  var nameCol = colByHeader_(sh, "지원자명");
  var memoCol = colByHeader_(sh, "메모");
  var last = sh.getLastRow();
  var vals = sh.getRange(NEW_DATA_START_ROW, 1, last - NEW_DATA_START_ROW + 1, sh.getLastColumn()).getValues();

  var memos = {
    "오상우": [
      "■ AI 평가: B",
      "",
      "■ 개인정보",
      "• 남, 만 42세 (1984년생) / 경기 고양시 덕양구 원흥동",
      "• 연락처 010-6534-7930 · onetami@naver.com",
      "• 학력: 단국대학교(천안) 독일어 4년 졸업 / 양재고등학교 문과계열",
      "• 자격증: MOS 외 2",
      "",
      "■ 경력 총 13년 2개월",
      "• 세이브존 화정점 — 시설팀 사원 (퇴사)",
      "",
      "■ 자기소개서",
      "다양한 경험을 통한 서비스 마인드를 갖춘 지원자 오상우입니다.",
      "",
      "■ 4대 인재상",
      "• 주인의식 B · 팀워크 B · 주도성 B- · 프로세스 B+ · 서비스마인드 P",
      "",
      "■ 강점",
      "• 시설관리·운영 13년 장기 경력",
      "• 서비스 마인드 보유",
      "",
      "■ 약점/우려",
      "• 자기소개서 매우 짧음 (1문장)",
      "• 구체 성과·수치 부재",
      "• 만 42세 — 운영부 사원 직급 적합도 확인 필요",
      "",
      "■ 면접 질문 추천",
      "1. 세이브존 화정점에서 퇴사하신 사유와 본인이 가장 자랑할 만한 성과는?",
      "2. 시설관리 13년 중 가장 어려웠던 위기 상황과 해결 사례?",
      "3. 회원 응대 중 클레임을 직접 처리한 경험을 말씀해 주세요.",
      "4. 동료와 의견 충돌이 있을 때 어떻게 조율하시는지?",
      "5. 본인이 생각하는 좋은 운영부 직원의 자질 세 가지?"
    ].join("\n"),

    "송후서": [
      "■ AI 평가: B",
      "",
      "■ 개인정보",
      "• 여, 만 31세 (1994년생) / 서울 서대문구 창천동",
      "• 연락처 010-8296-1870 · hoos1115@naver.com",
      "• 학력: 한림연예예술고등학교 졸업 (2013)",
      "• 자격증: 1종보통운전면허",
      "",
      "■ 경력 총 4년 6개월",
      "• 2025.12~2026.05 (6개월) 레인보우1872 골프아카데미 — 상담, FC 관리, SNS 관리",
      "• 2020.05~2021.01 (9개월) 오이엑스스튜디오 매니저 — 학생관리",
      "• 2018.02~2020.05 (2년 4개월) 프리픽스댄스학원 지점장 — 안내데스크·리셉셔니스트, 강사/수강생 관리, 시설관리, 스케줄",
      "",
      "■ 자기소개서 (책임감을 가지고 일하겠습니다)",
      "저는 맡은 역할을 성실하게 수행하며 조직에 안정적인 기여를 할 수 있는 환경에서 성장하고 싶다는 목표가 있습니다. 그 과정에서 제가 가진 \"꼼꼼함과 책임감\"은 업무 정확도가 중요한 직무에서 특히 도움이 될 것이라 생각합니다. 귀사의 업무 방식과 가치관은 제가 지향하는 성장 방향과 맞닿아 있어 지원하게 되었습니다.",
      "",
      "■ 4대 인재상",
      "• 주인의식 B · 팀워크 B- · 주도성 B · 프로세스 A- · 서비스마인드 P",
      "",
      "■ 강점",
      "• 운영·시설·스케줄 관리 4년 6개월 — 운영부 즉시 투입 가능",
      "• 안내데스크·리셉셔니스트 경력 — 회원 응대 능숙",
      "• 지점장 직책 — 매니지먼트 경험",
      "",
      "■ 약점/우려",
      "• 자기소개서 매우 짧음 (3문장)",
      "• 최근 6개월·과거 9개월 단기 근무 패턴 — 장기 근속 여부 확인 필요",
      "• 구체 성과·수치 부재",
      "",
      "■ 면접 질문 추천",
      "1. 레인보우1872를 6개월 만에 퇴사하신 이유와 웰페리온에서는 어떻게 다를 거라 보시는지?",
      "2. 프리픽스 지점장 시절 직원 간 갈등을 중재했던 구체적 사례?",
      "3. 스케줄·시설관리에서 본인이 직접 개선한 절차?",
      "4. 정해진 프로세스를 벗어나야 하는 상황에서 어떻게 판단하시는지?",
      "5. 응대 중 가장 어려웠던 클레임과 그 대응 방식, 결과는?"
    ].join("\n"),

    "정윤주": [
      "■ AI 평가: A (가장 우수)",
      "",
      "■ 개인정보",
      "• 여, 만 28세 (1997년생) / 서울 동대문구 용두동",
      "• 연락처 010-5672-6737 · myyj7506@naver.com",
      "• 학력: 서원대학교 레저스포츠과 4년 졸업 (2016~2019) / 상당고등학교",
      "• 자격증 4개: 2급 생활스포츠지도사(보디빌딩), 2급 생활스포츠지도사(에어로빅), R-KATA 선수트레이너, 2종보통운전면허",
      "• 수상: 2023 피트니스 챔피언 1위 그랑프리 (전남·충북), 제104회 전국체전 그랑프리전 3위",
      "",
      "■ 경력 총 10년 1개월",
      "• 2024.04~2026.04 (2년 1개월) 주식회사 발렉스서비스 — 마스터 트레이너(최고위), 임직원 1:1, 단체행사, 시설 안전관리 / 연봉 6,700만원",
      "• 2022.05~2024.04 (2년) 엠에프씨피트니스 — 1:1 PT, 재활·운동선수, 바디프로필·비키니",
      "• 2020.03~2022.04 (2년 2개월) 메디포스운동재활센터 실장 — 시설관리·안전관리·재활 / 연봉 5,000만원",
      "• 2019.07~2020.01 (7개월) 충청북도체육회 홍보팀 — SNS·홈피·사진·기자 응대",
      "• 2016.03~2019.06 (3년 4개월) 글로리휘트니스 실장 — 피티트레이너 (대학 알바)",
      "",
      "■ 자기소개서",
      "공중파 MBC 고정 출연 및 SK하이닉스 임원 트레이너 경험을 바탕으로 전문성을 갖춘 운동강사이며, 공감과 소통을 통해 개인별 맞춤 운동 지도와 꾸준한 동기부여를 만들어냅니다.",
      "",
      "■ 4대 인재상",
      "• 주인의식 A · 팀워크 A- · 주도성 A · 프로세스 A- · 서비스마인드 P",
      "",
      "■ 강점",
      "• 피트니스 전문가 최고 수준 (마스터 트레이너 최고위, 챔피언 우승, 방송 출연)",
      "• 운영·시설관리 경험 풍부 (실장 직책 2번)",
      "• 대인관계·고객응대 8년+",
      "",
      "■ 약점/우려 — 핵심",
      "• 직무 매칭: 운영부 사원 채용공고 vs 본인은 마스터 트레이너 / PT 전문가",
      "• 본인 적합 자리는 강습부 P.T 시니어/마스터",
      "• Over-qualified — 운영부 사원으로 장기 근속 가능성 우려",
      "• 연봉 6,700만원 vs 운영부 사원 — 격차 큼",
      "",
      "■ 면접 질문 추천",
      "1. 풍부한 트레이너 경력에도 운영부 사원에 지원하신 이유와 트레이너 경험을 어떻게 활용하실지?",
      "2. 운영부 사원이 6개월 후에도 매력적인 일자리가 될 이유?",
      "3. 현재 연봉 6,700만원 대비 운영부 사원의 합리적 연봉 수준은?",
      "4. 합격 후 강습부(P.T 시니어/마스터) 이동 제안이 있다면 결정은?",
      "5. 실장으로 시설관리·안전관리 위기 사례 구체적으로?",
      "",
      "■ 매니저 추천",
      "• 강습부 P.T 시니어/마스터 자리로 이동 검토 권장"
    ].join("\n")
  };

  var changed = [];
  for (var i = 0; i < vals.length; i++) {
    var nm = String(vals[i][nameCol-1] || "").trim();
    if (memos[nm]) {
      var row = NEW_DATA_START_ROW + i;
      sh.getRange(row, memoCol).setValue(memos[nm]);
      changed.push(nm + " 메모 갱신 (행 " + row + ")");
    }
  }
  Logger.log(changed.join("\n"));
  return { ok: true, changed: changed };
}


// [추가 2026-07-13 A-5] 무개입 자율화 3게이트 — 연령제한 포지션 집합(포지션명→상한 연령).
//   초과 시 "차단"이 아니라 stage="보류"로 안전 격리(등록은 됨·데이터 유실 없음, 추측금지 원칙).
var AGE_LIMITED_POSITIONS_ = { "수행기사": 55 };

// [추가 2026-07-14 A-7] 포지션/공고명 → canonical bucket (희망분야≠공고 불일치 게이트용).
// 발렛/주차를 수행기사보다 먼저 판정(운전 계열 붕괴매핑 방지). 기타/미상은 null(비교 제외=오탐 방지).
// ⚠️ "사내기사"(사내 운전기사) — 원 A-7 패치의 "사내이사" 오타를 A-5가 배포 전 교정(2026-07-14).
function canonicalJobBucket_(s) {
  var t = String(s || "").toLowerCase();
  if (!t.trim()) return null;
  if (/발렛|주차|파킹|parking|valet/.test(t)) return "발렛파킹";
  if (/수행기사|수행\s*기사|운전기사|사내기사/.test(t)) return "수행기사";
  if (/리셉션|프런트|프론트|컨시어지|운영부|reception|concierge/.test(t)) return "리셉션";
  return null;
}

// [추가 2026-07-16 A-5 P4·G8] 블랙리스트 대조 — 차단 아님·보류 격리만. 동명이인 오차단 방지 위해
//   식별키(성명 AND (생년 OR 연락처뒤4)) 강일치일 때만 strong. 프론트 blMatch(index.html)와 동일 계약.
function blacklistMatch_(ss, name, birthY, phone4) {
  var sh = ss.getSheetByName(SHEET_BLACKLIST); if (!sh) return null;
  var rows = readSchemaSheet_(ss, SHEET_BLACKLIST, SCHEMAS.blacklist);
  var nk = String(name || "").replace(/\s/g, "");
  var hits = rows.filter(function (b) { return String(b["성명"] || "").replace(/\s/g, "") === nk; });
  if (!hits.length) return null;
  var strong = hits.some(function (b) {
    var by = (String(b["생년"] || "").match(/(19|20)\d{2}/) || [""])[0];
    var p4 = String(b["연락처(뒤4자리)"] || "").replace(/\D/g, "").slice(-4);
    return (by && birthY && by === birthY) || (p4 && phone4 && p4 === phone4);
  });
  return { level: strong ? "strong" : "weak", reason: (hits[0]["사유"] || "") };
}

// memo 자유텍스트에서 "만NN세" 패턴으로 나이를 파싱(생년 저장 표준 형식들이 전부 이 패턴을 포함).
function parseAgeFromMemo_(memo) {
  var m = String(memo || "").match(/만\s*(\d{1,3})\s*세/);
  if (!m) return null;
  var n = parseInt(m[1], 10);
  return (n > 0 && n < 130) ? n : null;
}

function handleRegisterApplicant_(body) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_APPL);
  if (!sh) return { ok:false, error:"sheet_missing", message:"지원자 시트를 찾을 수 없습니다." };
  var now = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd");

  var name = body.name || "";
  var position = body.position;
  var stage = body.stage || "서류 검토";
  var memo = body.memo || "";
  var flags = [];
  var holdNotes = [];

  // 게이트(iii) 포지션 애매 → 보류: 미전달/공백 또는 호출자가 명시적으로 _ambiguous:true.
  //   기존엔 무조건 "운영부 리셉션"으로 추측 등록(붕괴매핑 온상) — 이제는 등록은 하되 보류로 격리.
  if (!position || !String(position).trim() || body._ambiguous === true) {
    flags.push("AMBIGUOUS_HOLD");
    holdNotes.push("지원공고 미상 — 포지션 확정 필요");
    position = position || "운영부 리셉션";
  }

  // 게이트(iv) 희망분야≠지원공고 불일치 → 보류(MISMATCH_HOLD). [2026-07-14 A-7]
  //   메일 공고명(body.jobPostingName, ① Gmail manifest)이 있고, 이력서 희망 도출 position과
  //   canonical bucket이 다르면 오배정 위험(정세성 r93형) → 공고 bucket 표준 포지션으로 교정 후 보류.
  //   jobPostingName 미전달(=① 미도입)이면 이 블록은 그대로 통과(no-op).
  var postingTitle = body.jobPostingName || "";
  if (postingTitle) {
    var bPos = canonicalJobBucket_(position);
    var bJob = canonicalJobBucket_(postingTitle);
    if (bPos && bJob && bPos !== bJob) {
      flags.push("MISMATCH_HOLD");
      holdNotes.push("희망분야≠지원공고 (희망 " + position + " / 공고 " + postingTitle + ") — 공고 우선 확인 필요");
      position = (bJob === "발렛파킹") ? "발렛파킹"
               : (bJob === "수행기사") ? "수행기사"
               : (bJob === "리셉션")  ? "운영부 리셉션"
               : position; // 메일 공고명 = 1차 근거로 포지션 교정, stage는 아래 보류 처리
    }
  }

  // 게이트(ii) 나이 하드게이트 → 보류: 연령제한 포지션에 상한 초과 지원자.
  var ageLimit = AGE_LIMITED_POSITIONS_[position];
  if (ageLimit) {
    var age = (typeof body.age === "number" && body.age > 0) ? body.age : parseAgeFromMemo_(memo);
    if (age && age > ageLimit) {
      flags.push("AGE_HOLD");
      holdNotes.push("연령요건 초과(만" + age + ">" + ageLimit + ") — 매니저/포지션 재확인");
    }
  }

  // [추가 2026-07-16 A-5 P4·G8] 블랙리스트 대조 — 등록 유입 시점. strong=보류 격리(holdNotes 합류),
  //   weak(성명만 일치)=메모 경고만·등록 진행(동명이인 오차단 방지).
  var __blBirthY = (String(memo || "").match(/(19|20)\d{2}/) || [""])[0];
  var __blP4 = String(body.phone || "").replace(/\D/g, "").slice(-4);
  var __bl = blacklistMatch_(ss, name, __blBirthY, __blP4);
  if (__bl) {
    if (__bl.level === "strong") { flags.push("BLACKLIST_HOLD"); holdNotes.push("블랙리스트 강일치(" + (__bl.reason || "사유미기재") + ") — 매니저 확인 필요"); }
    else { flags.push("BLACKLIST_WEAK"); memo = "[블랙리스트 성명일치(약) — 식별키 미확인, 확인 권장]\n" + memo; }
  }

  // 게이트 DUP_HOLD — [추가 2026-07-16 A-5 병목패치⑤/B19·B5 정합] 무인 스윕 자가치유·유인 세션의
  //   시간 창 겹침(B19)과 러너 302 재전송 중복(B5)으로 인한 이중 등록을 백엔드 계층에서 원천 차단.
  //   동일 이름 + (연락처 뒤4 또는 이메일) 기존재 시 신규 행은 그대로 생성하되(비파괴·append만) 보류로
  //   격리 — 거부 아님, 매니저가 해제 가능. 동명이인은 연락처/이메일이 다르면 오보류되지 않음.
  var __dupPhone4 = String(body.phone || "").replace(/\D/g, "").slice(-4);
  var __dupEmail = String(body.email || "").trim().toLowerCase();
  if (name && (__dupPhone4 || __dupEmail)) {
    var __existRows = sh.getDataRange().getValues();
    var __existHeader = __existRows[0] || [];
    var __cName2 = __existHeader.indexOf("지원자명"), __cPhone2 = __existHeader.indexOf("연락처"), __cEmail2 = __existHeader.indexOf("이메일");
    var __qName = String(name).replace(/\s/g, "");
    for (var __di = 1; __di < __existRows.length; __di++) {
      var __rn = String(__existRows[__di][__cName2] || "").replace(/\s/g, "");
      if (!__rn || __rn !== __qName) continue;
      var __rp4 = String(__existRows[__di][__cPhone2] || "").replace(/\D/g, "").slice(-4);
      var __re = String(__existRows[__di][__cEmail2] || "").trim().toLowerCase();
      if ((__dupPhone4 && __rp4 && __rp4 === __dupPhone4) || (__dupEmail && __re && __re === __dupEmail)) {
        flags.push("DUP_HOLD");
        holdNotes.push("동일인 기등록 의심(기존 row " + (__di + 1) + ") — 중복/재지원 확인 필요");
        break;
      }
    }
  }

  if (holdNotes.length > 0) {
    stage = "보류";
    memo = "[자동보류: " + holdNotes.join(" / ") + "]\n" + memo;
  }

  var row = [
    name, body.jobLink || "", position,
    body.source || "", stage, body.grade || "",
    body.applyDate || now, "", "", "",
    body.phone || "", body.email || "", memo, ""
  ];
  sh.appendRow(row);

  // 게이트(i) autolog 강제: 어떤 호출자(루틴·A-1·직접등록 등)든 백엔드가 스스로 1건 기록
  //   → 유주연류 "직접등록 무계측" 재발 차단. 로그 실패는 등록 자체를 막지 않음(비파괴 원칙).
  try {
    handleLogAdd_({
      actor: (body._actor || "루틴·A-1"),
      work: "지원자 등록",
      detail: name + "/" + position + "/" + stage,
      result: flags.length ? ("등록·" + flags.join(",")) : "등록"
    });
  } catch (logErr) {
    Logger.log("register-applicant autolog 실패: " + logErr);
  }

  var resp = { ok:true, action:"register-applicant", name: row[0], source: row[3] };
  if (flags.length) resp.flag = flags.join(",");
  return resp;
}


function handleUpdateJob_(body) {
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_HIRE);
  if (!sh) return { ok:false, error:"sheet_missing", message:"채용공고 시트를 찾을 수 없습니다." };
  var data = sh.getDataRange().getValues();
  if (data.length < 2) return { ok:false, error:"no_rows" };
  var header = data[0];
  var nameCol = header.indexOf("포지션명");
  var statCol = header.indexOf("채용 상태");
  if (nameCol < 0 || statCol < 0) return { ok:false, error:"col_missing" };
  var q = String(body.jobName || "").replace(/\s/g, "");
  var status = body.status || "마감";
  var updated = [];
  for (var i = 1; i < data.length; i++) {
    var nm = String(data[i][nameCol] || "").replace(/\s/g, "");
    if (nm && q && (nm.indexOf(q) >= 0 || q.indexOf(nm) >= 0)) {
      sh.getRange(i + 1, statCol + 1).setValue(status);
      updated.push(data[i][nameCol]);
    }
  }
  return { ok:true, action:"update-job", updated:updated, status:status };
}


function parseIvDate_(s){
  if(s instanceof Date) return s;
  s=String(s||"").trim();
  if(!s) return s;
  var m=s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})/);
  if(m){ var hh=("0"+m[4]).slice(-2); return Utilities.parseDate(m[1]+"-"+m[2]+"-"+m[3]+" "+hh+":"+m[5], "Asia/Seoul", "yyyy-MM-dd HH:mm"); }
  var d=s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if(d){ return Utilities.parseDate(d[1]+"-"+d[2]+"-"+d[3], "Asia/Seoul", "yyyy-MM-dd"); }
  return s;
}

function handleSetStage_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_APPL);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data=sh.getDataRange().getValues();
  if(data.length<2) return { ok:false, error:"no_rows" };
  var header=data[0];
  function col(n){ return header.indexOf(n); }
  var cName=col("\uc9c0\uc6d0\uc790\uba85"), cStage=col("\uc804\ud615 \ub2e8\uacc4"), cDate=col("\uba74\uc811 \uc77c\uc815"), cItv=col("\ub2f4\ub2f9 \uba74\uc811\uad00"), cDay=col("\uc9c0\uc6d0\uc77c"), cMemo=col("\uba54\ubaa8");
  if(cStage<0) return { ok:false, error:"col_missing" };
  var rowNum=-1;
  var sr=parseInt(body.sheetRow,10);
  if(sr && sr>=2 && sr<=data.length){ rowNum=sr; }
  else {
    var qn=String(body.name||"").replace(/\s/g,"");
    var qd=String(body.applyDate||"").slice(0,10);
    for(var i=1;i<data.length;i++){
      var nm=String(data[i][cName]||"").replace(/\s/g,"");
      var dy=String(data[i][cDay]||"").slice(0,10);
      if(nm && nm===qn && (!qd || dy===qd)){ rowNum=i+1; break; }
    }
  }
  if(rowNum<0) return { ok:false, error:"applicant_not_found" };
  if(body.stage) sh.getRange(rowNum,cStage+1).setValue(body.stage);
  if(cDate>=0 && body.interviewDate) sh.getRange(rowNum,cDate+1).setValue(parseIvDate_(body.interviewDate));
  if(cItv>=0 && body.interviewer) sh.getRange(rowNum,cItv+1).setValue(body.interviewer);
  if(cMemo>=0 && body.note){ var prev=String(sh.getRange(rowNum,cMemo+1).getValue()||""); sh.getRange(rowNum,cMemo+1).setValue((prev?prev+"\n":"")+body.note); }
  return { ok:true, action:"set-stage", row:rowNum, stage:body.stage||"" };
}

function handleAddOnboarding_(body){
  var name=String(body.name||'').trim();
  var join=String(body.joinDate||'').trim();
  if(!name) return {ok:false,error:'이름이 필요합니다.'};
  if(!join) return {ok:false,error:'입사일이 필요합니다.'};
  var dept=String(body.dept||'').trim();
  var mentor=String(body.mentor||'').trim();
  var owner=String(body.owner||'관리자+HR').trim();
  var pj=join.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if(!pj) return {ok:false,error:'입사일 형식 오류(YYYY-MM-DD).'};
  var jy=+pj[1], jm=+pj[2], jd=+pj[3];
  function aDays(n){ return new Date(jy, jm-1, jd+n); }
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_ONBO);
  if(!sh) return {ok:false,error:'sheet_missing'};
  var plan=[
    ['온보딩 정보','온보딩정보', aDays(0), '부서: '+(dept||'-')+' | 멘토: '+(mentor||'-')],
    ['1주차 체크인','주간 체크인', aDays(7), ''],
    ['2주차 체크인','주간 체크인', aDays(14), ''],
    ['3주차 체크인','주간 체크인', aDays(21), ''],
    ['4주차 체크인','주간 체크인', aDays(28), ''],
    ['5주차 체크인','주간 체크인', aDays(35), ''],
    ['6주차 체크인','주간 체크인', aDays(42), ''],
    ['7주차 체크인','주간 체크인', aDays(49), ''],
    ['8주차 체크인','주간 체크인', aDays(56), ''],
    ['9주차 체크인','주간 체크인', aDays(63), ''],
    ['10주차 체크인','주간 체크인', aDays(70), ''],
    ['11주차 체크인','주간 체크인', aDays(77), ''],
    ['12주차 수습평가','주간 체크인', aDays(84), '']
  ];
  var rows=plan.map(function(p){ return [ p[0], p[1], name, owner, p[2], '', '', p[3], '' ]; });
  // [추가 2026-07-04] '주간 성찰' 12행도 함께 자동 생성(담당자=신입직원, 기한은 체크인과 동일 주차로 미러링)
  var reflectPlan=[
    ['1주차 성찰','주간 성찰', aDays(7), ''],
    ['2주차 성찰','주간 성찰', aDays(14), ''],
    ['3주차 성찰','주간 성찰', aDays(21), ''],
    ['4주차 성찰','주간 성찰', aDays(28), ''],
    ['5주차 성찰','주간 성찰', aDays(35), ''],
    ['6주차 성찰','주간 성찰', aDays(42), ''],
    ['7주차 성찰','주간 성찰', aDays(49), ''],
    ['8주차 성찰','주간 성찰', aDays(56), ''],
    ['9주차 성찰','주간 성찰', aDays(63), ''],
    ['10주차 성찰','주간 성찰', aDays(70), ''],
    ['11주차 성찰','주간 성찰', aDays(77), ''],
    ['12주차 성찰','주간 성찰', aDays(84), '']
  ];
  var reflectRows=reflectPlan.map(function(p){ return [ p[0], p[1], name, '신입직원', p[2], '', '', p[3], '' ]; });
  rows=rows.concat(reflectRows);
  var nextRow=Math.max(sh.getLastRow()+1, NEW_DATA_START_ROW);
  sh.getRange(nextRow,1,rows.length, SCHEMAS.onbo.length).setValues(rows);
  return {ok:true, action:'add-onboarding', name:name, created:rows.length};
}

function handleDeleteOnboarding_(body){
  var name=String(body.name||'').trim();
  if(!name) return {ok:false,error:'name_required'};
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_ONBO);
  if(!sh) return {ok:false,error:'sheet_missing'};
  var data=sh.getDataRange().getValues();
  var header=data[0];
  var cName=header.indexOf('대상 신입 직원');
  if(cName<0) return {ok:false,error:'col_missing'};
  var del=0;
  for(var i=data.length-1;i>=1;i--){ if(String(data[i][cName]||'').trim()===name){ sh.deleteRow(i+1); del++; } }
  return {ok:true, action:'delete-onboarding', name:name, deleted:del};
}

function handleUpdateOnboarding_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_ONBO);
  if(!sh) return {ok:false,error:'sheet_missing'};
  var data=sh.getDataRange().getValues();
  var header=data[0];
  function col(n){return header.indexOf(n);}
  var cDone=col('완료 여부'), cComp=col('완료일'), cMemo=col('비고'), cOwner=col('담당자'), cCat=col('카테고리');
  var sr=parseInt(body.sheetRow,10);
  if(!(sr && sr>=2 && sr<=data.length)) return {ok:false,error:'row_not_found'};
  // [추가 2026-07-04] 완전 잠금 — '주간 체크인'/'주간 성찰' 행이 이미 완료(true)면 관리자 경로도 수정 불가(정정은 시트에서만)
  var __rowCat1 = cCat>=0 ? String(data[sr-1][cCat]||'').trim() : '';
  var __lockErr1 = checkOnboLock_(__rowCat1, cDone>=0 ? data[sr-1][cDone] : '');
  if (__lockErr1) return __lockErr1;
  if(typeof body.done!=='undefined' && cDone>=0) sh.getRange(sr,cDone+1).setValue(body.done?true:'');
  if(cComp>=0){ if(body.done){ var cd=body.completedDate||Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd'); sh.getRange(sr,cComp+1).setValue(cd); } else { sh.getRange(sr,cComp+1).setValue(''); } }
  if(typeof body.note!=='undefined' && cMemo>=0) sh.getRange(sr,cMemo+1).setValue(body.note);
  if(body.owner && cOwner>=0) sh.getRange(sr,cOwner+1).setValue(body.owner);
  return {ok:true, action:'update-onboarding', row:sr};
}

// =====================================================================
// 온보딩 위임 기입 (PIN 1202) — 관리자 비번 불필요, 온보딩 체크인 필드만 스코프 제한 쓰기
// =====================================================================

// 진행중(미완료 체크인 있는) 온보딩 대상자 이름만 반환. PII 없음(부서·연락처·비고 등 미포함). 비밀번호 불필요(공개).
function handleOnboActiveNames_() {
  try {
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var rows = readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
    var byName = {};
    rows.forEach(function (r) {
      var cat = String(r["카테고리"] || "");
      if (ONBO_CHECKIN_CATS_.indexOf(cat) < 0) return;
      var nm = String(r["대상 신입 직원"] || "").trim();
      if (!nm) return;
      if (!(nm in byName)) byName[nm] = { total: 0, done: 0 };
      byName[nm].total++;
      var v = r["완료 여부"];
      if (v === true || v === "Y" || v === "true" || v === "__YES__") byName[nm].done++;
    });
    var names = Object.keys(byName).filter(function (nm) { return byName[nm].done < byName[nm].total; });
    return { ok: true, names: names };
  } catch (err) {
    return { ok: false, error: "exception", message: String(err && err.message || err) };
  }
}

// 특정 대상자의 체크인 행만 반환(카테고리: 주간/격주/월간 체크인 한정). PIN 검증은 호출측(handleRequest_)에서 완료.
function handleOnboCheckinRead_(body) {
  try {
    var name = String(body.name || "").trim();
    if (!name) return { ok: false, error: "name_required" };
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var rows = readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
    var out = rows.filter(function (r) {
      if (String(r["대상 신입 직원"] || "").trim() !== name) return false;
      return ONBO_CHECKIN_CATS_.indexOf(String(r["카테고리"] || "")) >= 0;
    }).map(function (r) {
      return {
        _sheet_row: r["_sheet_row"],
        item: r["체크 항목"] || "",
        due: r["완료 기한"] || "",
        done: r["완료 여부"] || "",
        completedDate: r["완료일"] || "",
        note: r["비고"] || "",
        owner: r["담당자"] || ""
      };
    });
    out.sort(function (a, b) { return new Date(a.due) - new Date(b.due); });
    if (!out.length) return { ok: false, error: "not_found", message: "해당 이름의 체크인 대상을 찾을 수 없습니다." };
    return { ok: true, name: name, rows: out };
  } catch (err) {
    return { ok: false, error: "exception", message: String(err && err.message || err) };
  }
}

// 체크인 저장 — 지정 행이 "해당 이름 + 체크인 카테고리"일 때만, 완료여부/완료일/비고/담당자 필드만 기입. PIN 검증은 호출측에서 완료.
function handleOnboCheckinSave_(body) {
  try {
    var name = String(body.name || "").trim();
    var sr = parseInt(body.sheetRow, 10);
    if (!name) return { ok: false, error: "name_required" };
    if (!(sr >= NEW_DATA_START_ROW)) return { ok: false, error: "row_required" };
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var sh = ss.getSheetByName(SHEET_ONBO);
    if (!sh) return { ok: false, error: "sheet_missing" };
    var data = sh.getDataRange().getValues();
    if (sr < 2 || sr > data.length) return { ok: false, error: "row_not_found" };
    var header = data[0];
    function col(n) { return header.indexOf(n); }
    var cName = col("대상 신입 직원"), cCat = col("카테고리");
    var rowVals = data[sr - 1];
    var rowName = String(rowVals[cName] || "").trim();
    var rowCat = String(rowVals[cCat] || "").trim();
    if (rowName !== name) return { ok: false, error: "name_mismatch", message: "이름이 해당 행과 일치하지 않습니다." };
    if (ONBO_CHECKIN_CATS_.indexOf(rowCat) < 0) return { ok: false, error: "scope_denied", message: "체크인 항목만 기입 가능합니다." };

    // [추가 2026-07-04] 완전 잠금 — 이미 완료(true)면 PIN(멘토) 경로도 수정 불가(정정은 시트에서만)
    var __cDoneChk = col('완료 여부');
    var __lockErr2 = checkOnboLock_(rowCat, __cDoneChk >= 0 ? rowVals[__cDoneChk] : '');
    if (__lockErr2) return __lockErr2;

    var cDone = col('완료 여부'), cComp = col('완료일'), cMemo = col('비고'), cOwner = col('담당자');
    if (typeof body.done !== 'undefined' && cDone >= 0) sh.getRange(sr, cDone + 1).setValue(body.done ? true : '');
    if (cComp >= 0) {
      if (body.done) {
        var cd = body.completedDate || Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
        sh.getRange(sr, cComp + 1).setValue(cd);
      } else {
        sh.getRange(sr, cComp + 1).setValue('');
      }
    }
    if (typeof body.note !== 'undefined' && cMemo >= 0) sh.getRange(sr, cMemo + 1).setValue(body.note);
    if (body.owner && cOwner >= 0) sh.getRange(sr, cOwner + 1).setValue(body.owner);
    return { ok: true, action: 'onbo-checkin-save', row: sr, name: name };
  } catch (err) {
    return { ok: false, error: "exception", message: String(err && err.message || err) };
  }
}

// =====================================================================
// [추가 2026-07-04] 완전 잠금 공통 헬퍼 — '주간 체크인'/'주간 성찰' 행이 이미 완료(true)면
// 관리자·멘토PIN·본인PIN 3개 경로 모두 쓰기 거부. 정정은 시트에서만.
// =====================================================================
function isOnboDoneYes_(v) { return v === true || v === "Y" || v === "true" || v === "__YES__"; }
function checkOnboLock_(rowCat, doneVal) {
  if ((ONBO_CHECKIN_CATS_.indexOf(rowCat) >= 0 || rowCat === "주간 성찰") && isOnboDoneYes_(doneVal)) {
    return { ok: false, error: "locked", message: "완료된 체크인은 수정할 수 없습니다(정정은 시트에서만)." };
  }
  return null;
}

// =====================================================================
// [추가 2026-07-04 r2] 자가성찰 본인인증 — 현재근무자(emp) 시트에서 이름 일치 행들의
// 연락처를 숫자만 남겨 뒤 4자리와 대조. 동명이인(P.T/G.X 겸직 이중등록 등) 대응: 일치 행이
// 여럿이면 그 중 하나라도 일치하면 통과. 연락처 있는 행이 하나도 없으면 no_phone.
// 응답에 연락처 원문은 절대 포함하지 않는다(ok 여부만 반환).
// =====================================================================
// [추가 2026-07-04 r3] 현재근무자 시트 헤더행 PII 오염 폴백 — 연락처 열의 5/6행 헤더 셀에
// 대표번호 등 다른 값이 잘못 박혀 있으면 readCurrentSheet_ 키맵에서 '연락처' 키가 그 열에
// 안 붙어(=obj["연락처"]가 빈값) 실제 연락처 값이 오염된 헤더 텍스트를 키 이름으로 하는
// 필드 밑에 들어가 버린다. 이 경우 행의 모든 값을 스캔해 휴대폰 번호 패턴을 폴백으로 찾는다.
// 주민번호("590721-1..." 등)는 01[016789] 이동통신 접두 앵커라 오매치되지 않는다.
var SELF_PIN_PHONE_RE_ = /01[016789][\s.\-]?\d{3,4}[\s.\-]?\d{4}/;
function findRowPhoneDigits_(row) {
  var direct = String(row["연락처"] || "").replace(/\D/g, "");
  if (direct) return direct;
  for (var k in row) {
    if (k === "url" || k === "_sheet_row") continue;
    var vStr = String(row[k] == null ? "" : row[k]);
    var m = vStr.match(SELF_PIN_PHONE_RE_);
    if (m) {
      var d = m[0].replace(/\D/g, "");
      if (d.length >= 10) return d;
    }
  }
  return "";
}
function verifySelfPin_(name, pin) {
  var pinDigits = String(pin || "").replace(/\D/g, "");
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var emp = readCurrentSheet_(ss);
  var candidates = emp.filter(function (r) {
    return String(r["성명"] || "").trim() === name;
  });
  var hasPhone = false;
  for (var i = 0; i < candidates.length; i++) {
    var phoneDigits = findRowPhoneDigits_(candidates[i]);
    if (!phoneDigits) continue;
    hasPhone = true;
    var last4 = phoneDigits.slice(-4);
    if (pinDigits && last4 === pinDigits) return { ok: true };
  }
  if (!hasPhone) {
    return { ok: false, error: "no_phone", message: "연락처 정보가 없어 본인 확인이 불가합니다. 관리자에게 문의하세요." };
  }
  return { ok: false, error: "pin_invalid", message: "본인 확인에 실패했습니다. 연락처 뒤 4자리를 확인하세요." };
}

// =====================================================================
// [추가 2026-07-04] 신입직원 본인 자가성찰 — onbo-checkin-* 패턴 그대로 따름
//   · onbo-self-read: 해당 이름의 '주간 성찰' 행만 반환
//   · onbo-self-save: 대상 행이 '주간 성찰' + 이름 일치일 때만 완료여부/완료일/비고 기록(담당자 변경 불가)
// =====================================================================
function handleOnboSelfRead_(body) {
  try {
    var name = String(body.name || "").trim();
    if (!name) return { ok: false, error: "name_required" };
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var rows = readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
    var out = rows.filter(function (r) {
      if (String(r["대상 신입 직원"] || "").trim() !== name) return false;
      return String(r["카테고리"] || "").trim() === "주간 성찰";
    }).map(function (r) {
      return {
        _sheet_row: r["_sheet_row"],
        item: r["체크 항목"] || "",
        due: r["완료 기한"] || "",
        done: r["완료 여부"] || "",
        completedDate: r["완료일"] || "",
        note: r["비고"] || "",
        owner: r["담당자"] || ""
      };
    });
    out.sort(function (a, b) { return new Date(a.due) - new Date(b.due); });
    if (!out.length) return { ok: false, error: "not_found", message: "해당 이름의 성찰 대상을 찾을 수 없습니다." };
    return { ok: true, name: name, rows: out };
  } catch (err) {
    return { ok: false, error: "exception", message: String(err && err.message || err) };
  }
}

function handleOnboSelfSave_(body) {
  try {
    var name = String(body.name || "").trim();
    var sr = parseInt(body.sheetRow, 10);
    if (!name) return { ok: false, error: "name_required" };
    if (!(sr >= NEW_DATA_START_ROW)) return { ok: false, error: "row_required" };
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var sh = ss.getSheetByName(SHEET_ONBO);
    if (!sh) return { ok: false, error: "sheet_missing" };
    var data = sh.getDataRange().getValues();
    if (sr < 2 || sr > data.length) return { ok: false, error: "row_not_found" };
    var header = data[0];
    function col(n) { return header.indexOf(n); }
    var cName = col("대상 신입 직원"), cCat = col("카테고리");
    var rowVals = data[sr - 1];
    var rowName = String(rowVals[cName] || "").trim();
    var rowCat = String(rowVals[cCat] || "").trim();
    if (rowName !== name) return { ok: false, error: "name_mismatch", message: "이름이 해당 행과 일치하지 않습니다." };
    if (rowCat !== "주간 성찰") return { ok: false, error: "scope_denied", message: "성찰 항목만 기입 가능합니다." };

    var cDone = col('완료 여부');
    var __lockErr3 = checkOnboLock_(rowCat, cDone >= 0 ? rowVals[cDone] : '');
    if (__lockErr3) return __lockErr3;

    var cComp = col('완료일'), cMemo = col('비고');
    if (typeof body.done !== 'undefined' && cDone >= 0) sh.getRange(sr, cDone + 1).setValue(body.done ? true : '');
    if (cComp >= 0) {
      if (body.done) {
        var cd = body.completedDate || Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
        sh.getRange(sr, cComp + 1).setValue(cd);
      } else {
        sh.getRange(sr, cComp + 1).setValue('');
      }
    }
    if (typeof body.note !== 'undefined' && cMemo >= 0) sh.getRange(sr, cMemo + 1).setValue(body.note);
    // 담당자(owner)는 본인 경로에서 변경 불가 — body.owner 무시
    return { ok: true, action: 'onbo-self-save', row: sr, name: name };
  } catch (err) {
    return { ok: false, error: "exception", message: String(err && err.message || err) };
  }
}

// =====================================================================
// [추가 2026-07-04] ADD-SELFREFLECT — 기존 재직/온보딩 중인 직원에게 '주간 성찰' 12행 소급 생성
//   · admin 전용. {action:'add-selfreflect', adminPassword, name}
//   · 이미 '주간 성찰' 행이 있으면 중복 생성 방지({ok:false,error:'exists'})
//   · 해당 직원의 기존 'N주차 체크인'/'12주차 수습평가' 행 완료 기한을 그대로 미러링
//   · 체크인 행이 없으면 오늘 기준 aDays(7~84)로 대체
// =====================================================================
function handleAddSelfReflect_(body){
  var name=String(body.name||'').trim();
  if(!name) return {ok:false,error:'name_required'};

  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_ONBO);
  if(!sh) return {ok:false,error:'sheet_missing'};
  var data=sh.getDataRange().getValues();
  var header=data[0];
  var cItem=header.indexOf('체크 항목'), cCat=header.indexOf('카테고리'), cName=header.indexOf('대상 신입 직원'),
      cOwner=header.indexOf('담당자'), cDue=header.indexOf('완료 기한');
  if(cCat<0 || cName<0) return {ok:false,error:'col_missing'};

  // 중복 방지: 해당 직원의 '주간 성찰' 행이 이미 하나라도 있으면 거부
  for(var i=1;i<data.length;i++){
    if(String(data[i][cName]||'').trim()===name && String(data[i][cCat]||'').trim()==='주간 성찰'){
      return {ok:false, error:'exists'};
    }
  }

  // 기존 '주간 체크인' 행에서 주차별 완료 기한 추출(체크 항목 앞자리 "N주차"로 매칭)
  var dueByWeek={};
  for(var j=1;j<data.length;j++){
    if(String(data[j][cName]||'').trim()!==name) continue;
    if(String(data[j][cCat]||'').trim()!=='주간 체크인') continue;
    var label=String(data[j][cItem]||'');
    var wm=label.match(/^(\d{1,2})\s*주차/);
    if(wm){ dueByWeek[+wm[1]]=data[j][cDue]; }
  }

  var today=new Date();
  function aDays(n){ var d=new Date(today.getFullYear(), today.getMonth(), today.getDate()+n); return d; }

  var rows=[];
  for(var w=1; w<=12; w++){
    var label=(w===12) ? '12주차 성찰' : (w+'주차 성찰');
    var due=dueByWeek[w];
    if(!due){ due=aDays(w*7); }
    var row=[]; for(var k=0;k<header.length;k++) row[k]='';
    if(cItem>=0) row[cItem]=label;
    row[cCat]='주간 성찰';
    row[cName]=name;
    if(cOwner>=0) row[cOwner]='신입직원';
    if(cDue>=0) row[cDue]=due;
    rows.push(row);
  }
  var nextRow=Math.max(sh.getLastRow()+1, NEW_DATA_START_ROW);
  sh.getRange(nextRow,1,rows.length,header.length).setValues(rows);
  return {ok:true, action:'add-selfreflect', name:name, created:rows.length};
}

function handleSetChannels_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_HIRE);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data=sh.getDataRange().getValues();
  if(data.length<2) return { ok:false, error:"no_rows" };
  var header=data[0];
  var cName=header.indexOf("\ud3ec\uc9c0\uc158\uba85");
  var cCh=header.indexOf("\ucc44\uc6a9 \ucc44\ub110");
  if(cCh<0) return { ok:false, error:"col_missing" };
  var rowNum=-1;
  var sr=parseInt(body.sheetRow,10);
  if(sr && sr>=2 && sr<=data.length){ rowNum=sr; }
  else {
    var q=String(body.jobName||"").replace(/\s/g,"");
    for(var i=1;i<data.length;i++){ var nm=String(data[i][cName]||"").replace(/\s/g,""); if(nm && q && (nm.indexOf(q)>=0 || q.indexOf(nm)>=0)){ rowNum=i+1; break; } }
  }
  if(rowNum<0) return { ok:false, error:"job_not_found" };
  var chans=body.channels;
  var val=Array.isArray(chans)?chans.join(", "):String(chans||"");
  sh.getRange(rowNum,cCh+1).setValue(val);
  return { ok:true, action:"set-channels", row:rowNum, channels:val };
}

function handleUpdateApplicant_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_APPL);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data=sh.getDataRange().getValues();
  if(data.length<2) return { ok:false, error:"no_rows" };
  var header=data[0];
  var rowNum=parseInt(body.sheetRow,10);
  if(!(rowNum>=2 && rowNum<=data.length)){
    var cName=header.indexOf("\uc9c0\uc6d0\uc790\uba85"), cDay=header.indexOf("\uc9c0\uc6d0\uc77c");
    var qn=String(body.name||"").replace(/\s/g,""), qd=String(body.applyDate||"").slice(0,10); rowNum=-1;
    for(var i=1;i<data.length;i++){ var nm=String(data[i][cName]||"").replace(/\s/g,""); var dy=String(data[i][cDay]||"").slice(0,10); if(nm && nm===qn && (!qd||dy===qd)){ rowNum=i+1; break; } }
    if(rowNum<0) return { ok:false, error:"applicant_not_found" };
  }
  // [\ucd94\uac00 2026-07-16 A-5] \uc6d0\ubcf8 \ub9c1\ud06c \uc4f0\uae30 \ud655\uc7a5(sourceUrl/\ubcc4\uce6d sourceLink) \u2014 A-2 \ub9e4\uce6d\ud45c \uc77c\uad04 \ucc44\uc6c0 + A-1 \ub4f1\ub85d \ud30c\uc774\ud504 \uc6a9\ub3c4.
  //   \uae30\uc874 \ud544\ub4dc \ubcf4\uc874 \uaddc\uce59 \ub3d9\uc77c(\uc804\ub2ec\u00b7\ube44\uc5b4\uc788\uc9c0 \uc54a\uc744 \ub54c\ub9cc \ubc18\uc601) + http(s) \ud615\uc2dd\ub9cc \ud5c8\uc6a9(\ube44\uc815\uc0c1 \uac12\uc740 \uc694\uccad \uc790\uccb4 \uac70\ubd80).
  var __srcUrl = (body.sourceUrl!==undefined && body.sourceUrl!==null) ? body.sourceUrl : body.sourceLink;
  if(__srcUrl!==undefined && __srcUrl!==null && String(__srcUrl)!==""){
    if(!/^https?:\/\//i.test(String(__srcUrl))) return { ok:false, error:"invalid_source_url", message:"\uc6d0\ubcf8 \ub9c1\ud06c\ub294 http(s) \ud615\uc2dd\uc774\uc5b4\uc57c \ud569\ub2c8\ub2e4." };
  }
  var map={};
  map["\uc5f0\ub77d\ucc98"]=body.phone; map["\uc774\uba54\uc77c"]=body.email; map["\uc9c0\uc6d0 \ud3ec\uc9c0\uc158"]=body.position; map["\uc9c0\uc6d0 \uacbd\ub85c"]=body.source; map["\uba54\ubaa8"]=body.memo; map["\uc804\ud615 \ub2e8\uacc4"]=body.stage; map["\uba74\uc811 \ud3c9\uc810"]=body.grade;
  map["\uc5f0\uacb0 \uacf5\uace0"]=body.jobLink; // [\ucd94\uac00 2026-07-14 A-5] 8\ubc88\uc9f8 \uc120\ud0dd\ud30c\ub77c\ubbf8\ud130 \u2014 \ubbf8\uc804\ub2ec/\uacf5\ubc31\uc774\uba74 \uae30\uc874\uac12 \ubcf4\uc874(\uac00\uc774\ud2b8 \uacf5\ud1b5\uaddc\uce59)
  map["\uc6d0\ubcf8 Notion URL"]=__srcUrl;
  var updated=[];
  for(var k in map){ if(map[k]!==undefined && map[k]!==null && String(map[k])!==""){ var c=header.indexOf(k); if(c>=0){ sh.getRange(rowNum,c+1).setValue(map[k]); updated.push(k); } } }
  return { ok:true, action:"update-applicant", row:rowNum, updated:updated };
}

function handleUpdateHire_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_HIRE);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data=sh.getDataRange().getValues();
  if(data.length<2) return { ok:false, error:"no_rows" };
  var header=data[0];
  var cName=header.indexOf("\ud3ec\uc9c0\uc158\uba85");
  var rowNum=parseInt(body.sheetRow,10);
  if(!(rowNum>=2 && rowNum<=data.length)){
    var q=String(body.jobName||"").replace(/\s/g,""); rowNum=-1;
    for(var i=1;i<data.length;i++){ var nm=String(data[i][cName]||"").replace(/\s/g,""); if(nm && q && (nm.indexOf(q)>=0||q.indexOf(nm)>=0)){ rowNum=i+1; break; } }
    if(rowNum<0) return { ok:false, error:"job_not_found" };
  }
  var map={};
  map["\ud3ec\uc9c0\uc158\uba85"]=body.title; map["\ubd80\uc11c"]=body.dept; map["\ucc44\uc6a9 \uc720\ud615"]=body.jobType; map["\ucc44\uc6a9 \uc0c1\ud0dc"]=body.status; map["\ucc44\uc6a9 \ucc44\ub110"]=body.channels; map["\uc6b0\uc120\uc21c\uc704"]=body.priority; map["\ub2f4\ub2f9 C-Level"]=body.cLevel; map["\uacf5\uace0 \uc2dc\uc791\uc77c"]=body.startDate; map["\uacf5\uace0 \ub9c8\uac10\uc77c"]=body.endDate; map["\ubaa8\uc9d1 \uc778\uc6d0"]=body.openings; map["\uae09\uc5ec \ubc94\uc704"]=body.salary; map["\uc8fc\uc694 \uc5c5\ubb34"]=body.duty; map["\uc790\uaca9 \uc694\uac74"]=body.qual; map["\ube44\uace0"]=body.memo;
  var updated=[];
  for(var k in map){ if(map[k]!==undefined && map[k]!==null){ var c=header.indexOf(k); if(c>=0){ sh.getRange(rowNum,c+1).setValue(map[k]); updated.push(k); } } }

  // [추가 2026-07-16 A-5 P2·G4] 공고 마감 시 진행중 지원자 명단 반환(자동쓰기 0 — 지원자 당락 자동변경 배제).
  //   status=마감으로 세팅되는 경우만 계산. 마감 아니면 빈 배열.
  var __closing = (String(body.status||"").trim()==="마감");
  var __pendingApplicants = [];
  if(__closing){
    var __jobTitle = String(data[rowNum-1][cName]||"");
    var __appl = readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl);
    __pendingApplicants = matchApplicantsForJob_(__appl, __jobTitle)
      .filter(function(a){return isActiveStage_(a["전형 단계"]);})
      .map(function(a){return {row:a["_sheet_row"], name:a["지원자명"], stage:a["전형 단계"]||""};});
  }

  return { ok:true, action:"update-hire", row:rowNum, updated:updated, pendingApplicants:__pendingApplicants };
}

// UPDATE HEADCOUNT — 채용공고 '모집 인원' 셀만 수정 (전용·최소침습)
// 입력: (sheetRow 또는 jobName) + headcount(=openings 별칭). 행 삽입/삭제 없이 값만 setValue.
function handleUpdateHeadcount_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_HIRE);
  if(!sh) return { ok:false, error:"sheet_missing", message:"채용공고 시트를 찾을 수 없습니다." };
  var data=sh.getDataRange().getValues();
  if(data.length<2) return { ok:false, error:"no_rows" };
  var header=data[0];
  var cName=header.indexOf("포지션명");        // 포지션명
  var cHead=header.indexOf("모집 인원");        // 모집 인원
  if(cHead<0) return { ok:false, error:"col_missing", message:"모집 인원 열을 찾을 수 없습니다." };
  var raw=(body.headcount!==undefined && body.headcount!==null) ? body.headcount : body.openings;
  if(raw===undefined || raw===null || String(raw).trim()==="") return { ok:false, error:"headcount_missing", message:"headcount 값이 필요합니다." };
  var n=Number(String(raw).trim());
  if(!isFinite(n) || n<0 || Math.floor(n)!==n) return { ok:false, error:"headcount_invalid", message:"모집 인원은 0 이상의 정수여야 합니다." };
  var rowNum=parseInt(body.sheetRow,10);
  if(!(rowNum>=2 && rowNum<=data.length)){
    var q=String(body.jobName||"").replace(/\s/g,""); rowNum=-1;
    for(var i=1;i<data.length;i++){ var nm=String(data[i][cName]||"").replace(/\s/g,""); if(nm && q && (nm.indexOf(q)>=0||q.indexOf(nm)>=0)){ rowNum=i+1; break; } }
    if(rowNum<0) return { ok:false, error:"job_not_found" };
  }
  var prev=(cHead>=0) ? data[rowNum-1][cHead] : "";
  sh.getRange(rowNum, cHead+1).setValue(n);   // 해당 셀만 값 교체 (행 고정)
  return { ok:true, action:"update-headcount", row:rowNum, jobName:String(data[rowNum-1][cName]||""), headcount:n, prev:String(prev) };
}

function handleSetPhoto_(body){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_APPL);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data=sh.getDataRange().getValues();
  if(data.length<2) return { ok:false, error:"no_rows" };
  var header=data[0];
  var rowNum=parseInt(body.sheetRow,10);
  if(!(rowNum>=2 && rowNum<=data.length)){
    var cName=header.indexOf("\uc9c0\uc6d0\uc790\uba85"); var qn=String(body.name||"").replace(/\s/g,""); var qd=String(body.applyDate||"").slice(0,10); rowNum=-1;
    var cDay=header.indexOf("\uc9c0\uc6d0\uc77c");
    for(var i=1;i<data.length;i++){ var nm=String(data[i][cName]||"").replace(/\s/g,""); var dy=String(data[i][cDay]||"").slice(0,10); if(nm && nm===qn && (!qd||dy===qd)){ rowNum=i+1; break; } }
    if(rowNum<0) return { ok:false, error:"applicant_not_found" };
  }
  var c=header.indexOf("\uc0ac\uc9c4");
  if(c<0){ c=header.length; sh.getRange(1,c+1).setValue("\uc0ac\uc9c4"); }
  sh.getRange(rowNum,c+1).setValue(body.photo||"");
  return { ok:true, action:"set-photo", row:rowNum, len:String(body.photo||"").length };
}

function _fixKimJoblink(){
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_APPL);
  var data=sh.getDataRange().getValues();
  var header=data[0];
  var c=-1,nameCol=-1;
  for(var k=0;k<header.length;k++){ var h=String(header[k]).replace(/\s/g,""); if(h==="\uc5f0\uacb0\uacf5\uace0") c=k; if(h==="\uc9c0\uc6d0\uc790\uba85") nameCol=k; }
  var target=-1;
  for(var r=1;r<data.length;r++){ if(String(data[r][nameCol]).indexOf("\uae40\uc7ac\ud604")>=0) target=r+1; }
  var hsh=ss.getSheetByName(SHEET_HIRE);
  var hd=hsh.getDataRange().getValues();
  var hh=hd[0];
  var posCol=-1; for(var k2=0;k2<hh.length;k2++){ if(String(hh[k2]).replace(/\s/g,"").indexOf("\ud3ec\uc9c0\uc158\uba85")>=0) posCol=k2; }
  var jobName=""; for(var r2=1;r2<hd.length;r2++){ var nm=String(hd[r2][posCol]); if(nm.indexOf("\uc8fc\ucc28\uad00\ub9ac\uc790")>=0 && nm.indexOf("\uc2dc\uc124\ubd80")>=0){ jobName=nm; } }
  var res="c="+c+" target="+target+" posCol="+posCol+" jobName=["+jobName+"]";
  Logger.log(res);
  if(c>=0 && target>0 && jobName){ sh.getRange(target,c+1).setValue(jobName); res="UPDATED "+res; Logger.log(res); }
  return res;
}


/* ===== 성능: 응답 캐시 (45초, 쓰기 시 무효화) ===== */
function cacheKey_(pw){ return "hubv1_"+Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, "k:"+String(pw))); }
function bustCache_(){ try{ var c=CacheService.getScriptCache(); c.removeAll([cacheKey_(ADMIN_PASSWORD), cacheKey_(ACCESS_PASSWORD), cacheKey_("")]); }catch(e){} }
function doGet(e){
  var pw=(e&&e.parameter&&e.parameter.password)||"";
  var cache=CacheService.getScriptCache();
  var key=cacheKey_(pw);
  try{ var hit=cache.get(key); if(hit){ return ContentService.createTextOutput(hit).setMimeType(ContentService.MimeType.JSON); } }catch(e1){}
  var out=doGet_impl_(e);
  try{ var txt=out.getContent(); if(txt && txt.length<95000){ cache.put(key, txt, 45); } }catch(e2){}
  return out;
}
function doPost(e){
  var out=doPost_impl_(e);
  try{ bustCache_(); }catch(e3){}
  return out;
}

// =====================================================================
// [추가] PUBLIC-STATS — 개인정보 없는 공개 집계
//   · 비밀번호 불필요(공개). 성명·연락처·이메일 등 PII 일절 미반환.
//   · 집계 정의는 허브 index.html renderDash와 동일.
//   · 기존 읽기 헬퍼(readCurrentSheet_/readExitSheet_/readSchemaSheet_) 재사용.
// =====================================================================
// [추가 2026-07-16 A-5 P2·G5] public-job-status — 리크루팅 정적 페이지 마감 동기용 공개 읽기.
//   public-stats 선례와 동일 게이트(비번검사 전, 인증 불필요). 반환은 4필드 화이트리스트만
//   (포지션명·bucket·상태·closed) — 급여/연락처/담당자/원본URL 등 일절 미포함(PII 0).
function handlePublicJobStatus_() {
  try {
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var hire = readSchemaSheet_(ss, SHEET_HIRE, SCHEMAS.hire);
    var out = hire.map(function (h) {
      return {
        position: String(h["포지션명"] || ""),
        bucket: canonicalJobBucket_(h["포지션명"]) || "",
        status: String(h["채용 상태"] || ""),
        closed: String(h["채용 상태"] || "").trim() === "마감"
      };
    }).filter(function (x) { return x.position; });
    return { ok: true, jobs: out };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

function handlePublicStats_() {
  try {
    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var emp  = readCurrentSheet_(ss);
    var hire = readSchemaSheet_(ss, SHEET_HIRE, SCHEMAS.hire);
    var appl = readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl);
    var onbo = readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
    var exits = readExitSheet_(ss);

    var TZ = "Asia/Seoul";
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    var asOf = Utilities.formatDate(today, TZ, "yyyy-MM-dd");
    var in7 = new Date(today.getTime() + 7 * 86400000);
    var d90 = new Date(today.getTime() - 90 * 86400000);

    function nameOf(e) { return String(e["성명"] || e["이름"] || "").trim(); }
    function isYes(v) { return v === true || v === "Y" || v === "true" || v === "__YES__"; }
    function parseDate(s) { if (!s) return null; var dd = new Date(s); return isNaN(dd.getTime()) ? null : dd; }

    // 재직자 (퇴사 제외), 성명 기준 중복 1회
    var active = emp.filter(function (e) { return e["재직 상태"] !== "퇴사"; });
    var seen = {};
    var uniqueActive = [];
    active.forEach(function (e) {
      var n = nameOf(e);
      if (!n || seen[n]) return;
      seen[n] = 1;
      uniqueActive.push(e);
    });
    var headcount = uniqueActive.length;

    // 평균 근속 (허브 __tenure 동일 정의)
    var sum = 0, cnt = 0;
    uniqueActive.forEach(function (e) {
      var dd = parseDate(e["입사일"]);
      if (!dd) return;
      sum += (today - dd) / (365.25 * 86400000);
      cnt++;
    });
    var avgTenure = cnt ? (sum / cnt).toFixed(1) : null;

    // 진행 중 채용 (허브 activeHire 동일 상태군)
    var ACTIVE_STATUS = ["공고 준비", "공고중", "서류심사", "면접 진행", "처우 협의"];
    var openings = hire.filter(function (h) {
      return ACTIVE_STATUS.indexOf(String(h["채용 상태"] || "").trim()) >= 0;
    }).length;

    // 공고중인 공고 목록 (제목·부서만 — PII 아님)
    var openingsList = hire.filter(function (h) {
      return String(h["채용 상태"] || "").trim() === "공고중";
    }).map(function (h) {
      return { title: String(h["포지션명"] || "").trim(), dept: String(h["부서"] || "").trim() };
    });

    // 지원자 풀 (허브 appl.length 동일)
    var applicantPool = appl.length;

    // 온보딩 완료율 (허브 obRate 동일)
    var obDone = onbo.filter(function (o) { return isYes(o["완료 여부"]); }).length;
    var onboardingRate = onbo.length ? Math.round(obDone / onbo.length * 100) : null;

    // 최근 90일 퇴사 (허브 exit90 동일 — 최종 근무일 기준)
    var exits90 = exits.filter(function (e) {
      var d = parseDate(e["최종 근무일"] || e["퇴사일자"] || e["퇴사일"]);
      return d && d >= d90;
    }).length;

    // 향후 7일 면접 / 공고 마감 (허브 todos 동일 정의)
    var weekInterviews = 0;
    appl.forEach(function (a) {
      var d = parseDate(a["면접 일정"]);
      if (d && d >= today && d <= in7) weekInterviews++;
    });
    var weekClosings = 0;
    hire.forEach(function (h) {
      var d = parseDate(h["공고 마감일"]);
      if (d && String(h["채용 상태"] || "").trim() === "공고중" && d >= today && d <= in7) weekClosings++;
    });

    // 부서별 재직 인원 (합계 = headcount, 중복 제거된 uniqueActive 기준)
    var deptMap = {};
    var deptOrder = [];
    uniqueActive.forEach(function (e) {
      var d = String(e["부서"] || "미지정").trim() || "미지정";
      if (!(d in deptMap)) { deptMap[d] = 0; deptOrder.push(d); }
      deptMap[d]++;
    });
    var deptBreakdown = deptOrder.map(function (d) { return { name: d, count: deptMap[d] }; });

    // 고용 형태 (프리랜서 / 정규직 등)
    var freelance = 0, fulltime = 0;
    uniqueActive.forEach(function (e) {
      var t = String(e["고용 형태"] || "").trim();
      if (t.indexOf("프리") >= 0) freelance++;
      else fulltime++;
    });

    return {
      ok: true,
      asOf: asOf,
      headcount: headcount,
      avgTenure: avgTenure,
      openings: openings,
      openingsList: openingsList,
      applicantPool: applicantPool,
      onboardingRate: onboardingRate,
      exits90: exits90,
      weekInterviews: weekInterviews,
      weekClosings: weekClosings,
      deptBreakdown: deptBreakdown,
      employment: { freelance: freelance, fulltime: fulltime }
    };
  } catch (err) {
    return { ok: false, error: "public_stats_exception", message: String(err && err.message || err) };
  }
}

// =====================================================================
// 휴무·근무 스케줄 (휴무 시트) — set-leave / set-leave-bulk / delete-leave / db:leave
// 셀 1개 = 1행 (성명+날짜 키). 값 = 휴무코드(휴/연차/반차오전/반차오후/공휴/대휴/휴관) 또는 출근시간("05:40" / "13:30 18:00")
// =====================================================================
function _leaveCols_(header){
  return {
    n: header.indexOf("성명"), d: header.indexOf("날짜"),
    v: header.indexOf("값"),  p: header.indexOf("부서"), t: header.indexOf("등록일시")
  };
}
function handleSetLeave_(body){
  var emp  = String(body.emp || body.name || "").trim();
  var date = String(body.date || "").slice(0,10);
  var value= String(body.value || "").trim();
  var dept = String(body.dept || "").trim();
  if(!emp || !date) return { ok:false, error:"emp_date_required" };
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_LEAVE, SCHEMAS.leave);
  var data = sh.getDataRange().getValues();
  var header = data[0];
  var c = _leaveCols_(header);
  var found = -1;
  for(var i=1;i<data.length;i++){
    if(String(data[i][c.n]||"").trim()===emp && String(data[i][c.d]||"").slice(0,10)===date){ found=i+1; break; }
  }
  var now = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm");
  if(!value){
    if(found>0) sh.deleteRow(found);
    return { ok:true, action:"set-leave", deleted:(found>0), emp:emp, date:date };
  }
  if(found>0){
    sh.getRange(found, c.v+1).setNumberFormat("@").setValue(value);
    if(dept && c.p>=0) sh.getRange(found, c.p+1).setValue(dept);
    if(c.t>=0) sh.getRange(found, c.t+1).setValue(now);
  } else {
    var row=[]; for(var k=0;k<header.length;k++) row[k]="";
    row[c.n]=emp; row[c.d]=date; row[c.v]=value; if(c.p>=0)row[c.p]=dept; if(c.t>=0)row[c.t]=now;
    var nr=Math.max(sh.getLastRow()+1, NEW_DATA_START_ROW);
    sh.getRange(nr, c.v+1).setNumberFormat("@"); // 값=텍스트(시간 자동변환 방지)
    sh.getRange(nr,1,1,header.length).setValues([row]);
  }
  return { ok:true, action:"set-leave", emp:emp, date:date, value:value };
}
// 전체 동기화: {data:{emp:{date:value}}, deptMap:{emp:dept}} → 휴무 시트 데이터행 전체 교체
function handleSetLeaveBulk_(body){
  var map = body.data || {};
  var deptMap = body.deptMap || {};
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = getOrCreateSheet_(ss, SHEET_LEAVE, SCHEMAS.leave);
  var header = sh.getRange(1,1,1,SCHEMAS.leave.length).getValues()[0];
  var c = _leaveCols_(header);
  var last = sh.getLastRow();
  if(last >= NEW_DATA_START_ROW){
    sh.getRange(NEW_DATA_START_ROW,1,last-NEW_DATA_START_ROW+1, Math.max(sh.getLastColumn(),header.length)).clearContent();
  }
  var now = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm");
  var rows=[];
  var emps=Object.keys(map);
  for(var a=0;a<emps.length;a++){
    var emp=emps[a]; var byDate=map[emp]||{}; var dates=Object.keys(byDate);
    for(var b=0;b<dates.length;b++){
      var d=dates[b]; var v=byDate[d];
      if(v===""||v===null||typeof v==="undefined") continue;
      var r=[]; for(var k=0;k<header.length;k++) r[k]="";
      r[c.n]=emp; r[c.d]=d; r[c.v]=String(v); if(c.p>=0)r[c.p]=(deptMap[emp]||""); if(c.t>=0)r[c.t]=now;
      rows.push(r);
    }
  }
  if(rows.length){
    sh.getRange(NEW_DATA_START_ROW, c.v+1, rows.length, 1).setNumberFormat("@"); // 값=텍스트
    sh.getRange(NEW_DATA_START_ROW,1,rows.length,header.length).setValues(rows);
  }
  return { ok:true, action:"set-leave-bulk", written:rows.length };
}
// 지원자 행 삭제 (오상우 중복 등). expectName 제공 시 이름 일치 검증.
function handleDeleteApplicant_(body){
  var sr = parseInt(body.sheetRow,10);
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_APPL);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data = sh.getDataRange().getValues();
  if(!(sr>=NEW_DATA_START_ROW && sr<=data.length)) return { ok:false, error:"row_not_found" };
  var header=data[0]; var cN=header.indexOf("지원자명");
  var nameAt = (cN>=0)? String(data[sr-1][cN]||"").trim() : "";
  if(body.expectName && String(body.expectName).trim()!==nameAt) return { ok:false, error:"name_mismatch", found:nameAt };
  // [변경 2026-07-16 A-5 P3·G6] deleteRow → 행유지·값비움. 하위 전원의 _sheet_row·pageId(MD5)·r<row>.jpg
  //   매핑이 행번호 삭제로 전원 시프트되던 오프바이원 근본원인 제거. all-blank 행은 readSchemaSheet_이
  //   자동 스킵(read에 미출현) — 별도 필터 불요. 현재근무자 시트 "행고정·값만 비움" 철학과 동일 패턴.
  sh.getRange(sr, 1, 1, Math.max(header.length, SCHEMAS.appl.length)).clearContent();
  return { ok:true, action:"delete-applicant", row:sr, name:nameAt, mode:"value-cleared" };
}
// 평가 행 삭제 — 빈 평가행(총점·등급·평가자 공란)만 허용, 입력된 평가는 거부(기록유실 방지)
function handleDeleteEval_(body){
  var sr = parseInt(body.sheetRow,10);
  var ss = SpreadsheetApp.openById(HR_SHEET_ID);
  var sh = ss.getSheetByName(SHEET_EVAL);
  if(!sh) return { ok:false, error:"sheet_missing" };
  var data = sh.getDataRange().getValues();
  if(!(sr>=NEW_DATA_START_ROW && sr<=data.length)) return { ok:false, error:"row_not_found" };
  var header=data[0], row=data[sr-1];
  var cScore=header.indexOf("총점"), cGrade=header.indexOf("평가 등급"), cEval=header.indexOf("평가자");
  function filled(ci){ return ci>=0 && String(row[ci]||"").trim()!==""; }
  if(filled(cScore)||filled(cGrade)||filled(cEval)){
    return { ok:false, error:"eval_not_empty", message:"입력된 평가는 삭제할 수 없습니다(기록유실 방지)." };
  }
  sh.deleteRow(sr);
  return { ok:true, action:"delete-eval", row:sr };
}

// 안A(2026-07-16 A-7 설계, drafts\P1통합_설계_result.md) — 붕괴 대상자("(연결 N건)") 복구.
// 대상자 셀 1칸만 setValue. 행 삽입·삭제 없음(행고정). 공란/붕괴리터럴일 때만 덮어씀 — 이미
// 실명이면 force 없인 거부(오폭 방지). expectCurrent 동봉 시 정확대조(delete-applicant 패턴 재사용).
function handleSetEvalTarget_(body){
  var sr = parseInt(body.sheetRow||body.row,10);
  var name = String(body.name||body.target||"").trim();
  if(!name) return {ok:false,error:"name_required"};
  var ss=SpreadsheetApp.openById(HR_SHEET_ID);
  var sh=ss.getSheetByName(SHEET_EVAL);
  if(!sh) return {ok:false,error:"sheet_missing"};
  var data=sh.getDataRange().getValues();
  if(!(sr>=NEW_DATA_START_ROW && sr<=data.length)) return {ok:false,error:"row_not_found"};
  var header=data[0]; var cTgt=header.indexOf("대상자");
  if(cTgt<0) return {ok:false,error:"col_missing"};
  var cur=String(data[sr-1][cTgt]||"").trim();
  // 오폭 가드: expectCurrent 주면 정확대조.
  if(body.expectCurrent!==undefined && String(body.expectCurrent).trim()!==cur)
    return {ok:false,error:"current_mismatch",found:cur};
  // 안전 가드: 현재값이 공란 또는 붕괴리터럴(연결 N건)일 때만 덮어씀. 이미 실명이면 force 없인 거부.
  var isBroken = (cur==="") || /^\(연결\s*\d+건\)$/.test(cur) || /연결/.test(cur);
  if(!isBroken && body.force!==true)
    return {ok:false,error:"already_named",found:cur,message:"이미 실명 대상자 — force 필요"};
  sh.getRange(sr, cTgt+1).setValue(name);
  return {ok:true, action:"set-eval-target", row:sr, name:name, previous:cur};
}

// =====================================================================
// [추가 2026-07-04, 개편 2026-07-05] 일일 텔레그램 HR 아침 브리핑
//   · sendDailyHrReminder() — 시간 트리거 전용(doPost 흐름과 무관) + doPost run-reminder 액션에서도
//     동일 함수 재사용. 토큰/채팅ID는 스크립트 속성(TG_BOT_TOKEN, TG_CHAT_ID)에서만 읽음 —
//     코드 하드코딩 금지. 속성 미설정 시 크래시 없이 Logger만 남기고 조용히 종료.
//   · installDailyReminderTrigger(kstHour) — 기존 sendDailyHrReminder 트리거 전부 삭제 후 매일 KST
//     지정 시각(무인자 호출은 기존과 동일 8시, doPost install-reminder-trigger 액션은 기본 9시) 트리거를
//     새로 만든다. appsscript.json timeZone=Asia/Seoul 확인됨(2026-07-04).
//   · 메시지 조립은 순수 함수(buildDailyHrReminderMessage_/renderDailyHrReminderText_ 등, GAS 서비스
//     미사용)로 분리 — node 등 순수 JS 환경에서 그대로 단위 시뮬레이션 가능.
//   · 데이터 수집은 기존 읽기 유틸(readSchemaSheet_)과 기존 완료판정 유틸(isOnboDoneYes_) 재사용.
//   · [2026-07-05] 구성을 "지연 항목 나열"에서 4섹션(오늘 정리된 이력서 / 오늘 면접 / 오늘 온보딩 /
//     지연 요약 1줄) 브리핑으로 개편(매니저 확정 사양). "오늘 정리된 이력서"는 지원자 메모의
//     "[자동 수집 YYYY-MM-DD]" 마커(register-applicant memo 표준, wellperion-hr/docs/시스템-레퍼런스.md
//     "인사카드 메모 표준 양식" 참조 — resume-intake(A-1)가 남기는 표준 접두 마커)로 판정한다.
// =====================================================================

// ---- 순수 날짜 유틸 (GAS 서비스 미사용 — node 단위 시뮬 가능) ----

// 연/월/일 정수로 UTC 자정 Date 생성 — 달력일(day) 비교 전용이라 실행 환경 타임존에 영향 안 받음.
function mkUTCDate_(y, m, d) {
  if (!y || !m || !d) return null;
  var dt = new Date(Date.UTC(y, m - 1, d));
  return isNaN(dt.getTime()) ? null : dt;
}

// 시트에서 온 완료기한/면접일정 값(readSchemaSheet_ 표준 출력인 "yyyy-MM-dd"·"yyyy-MM-dd'T'HH:mm" 외에도
// 수기입력으로 인한 "yyyy.MM.dd"·"yyyy/MM/dd"·"yyyy년 M월 d일" 등 문자열이 섞일 수 있음)을
// 달력일(UTC 자정 Date)로 견고 파싱한다. 실패 시 null. (Date 인스턴스가 직접 들어와도 처리)
function parseFlexibleDate_(raw) {
  if (raw === null || raw === undefined) return null;
  if (raw instanceof Date) {
    return isNaN(raw.getTime()) ? null : mkUTCDate_(raw.getFullYear(), raw.getMonth() + 1, raw.getDate());
  }
  var s = String(raw).trim();
  if (!s) return null;

  // yyyy-MM-dd / yyyy-MM-dd'T'HH:mm(:ss)? / "yyyy-MM-dd HH:mm" — readSchemaSheet_ 표준 출력 포맷
  var m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return mkUTCDate_(+m[1], +m[2], +m[3]);

  // yyyy.MM.dd / yyyy/MM/dd (수기 입력 대응)
  m = s.match(/^(\d{4})[./](\d{1,2})[./](\d{1,2})/);
  if (m) return mkUTCDate_(+m[1], +m[2], +m[3]);

  // "yyyy년 M월 d일" (수기 입력 대응)
  m = s.match(/^(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일/);
  if (m) return mkUTCDate_(+m[1], +m[2], +m[3]);

  // 최후 수단 — 네이티브 Date 파싱(그 외 표기). 로컬 컴포넌트를 그대로 "달력일"로 재해석해
  // 실행 타임존 차이로 인한 오프바이원을 방지한다.
  var d = new Date(s);
  if (!isNaN(d.getTime())) return mkUTCDate_(d.getFullYear(), d.getMonth() + 1, d.getDate());
  return null;
}

// UTC 자정 Date → 정수 "일수"(day epoch). 두 달력일의 선후 비교·차이 계산용.
function epochDay_(d) { return Math.round(d.getTime() / 86400000); }

// 면접 일정에서 시각(HH:MM)만 추출 — "yyyy-MM-ddTHH:mm..."/"yyyy-MM-dd HH:mm" 모두 대응.
// 시각 정보가 없는 순수 날짜("yyyy-MM-dd")면 빈 문자열(표시 생략).
function fmtTimeOnly_(s) {
  var m = String(s || "").match(/^\d{4}-\d{2}-\d{2}[T ](\d{2}:\d{2})/);
  return m ? m[1] : "";
}

// 지원자 메모에서 "[자동 수집 YYYY-MM-DD]" 표준 마커(register-applicant memo 표준 —
// wellperion-hr/docs/시스템-레퍼런스.md "인사카드 메모 표준 양식" 참조)를 찾아 날짜 문자열만
// 반환한다. 마커 없으면 null. 메모는 readSchemaSheet_에서 trim된 문자열로 오므로 맨 앞 매칭.
// [2026-07-08] 아침 브리핑 섹션①의 "오늘" 판정에는 더 이상 쓰지 않음(아래 buildDailyHrReminderMessage_
// 주석 참조 — 마커=오늘 방식은 08시 발송 후 등록분이 영구 누락되는 설계결함, A-6 감사 지적으로 행번호
// 포인터 방식으로 교체). 다른 용도로 재사용될 수 있어 함수 자체는 보존.
function parseAutoCollectMarkerDate_(memo) {
  var m = String(memo || "").match(/^\[자동 수집 (\d{4}-\d{2}-\d{2})\]/);
  return m ? m[1] : null;
}

// 지원자 행 배열에서 현재 존재하는 최대 시트 행번호를 구한다(순수 함수). 빈 배열이면 0.
// readSchemaSheet_가 채운 "_sheet_row"를 그대로 사용 — register-applicant가 appendRow만
// 쓰므로(=append-only) 행번호는 곧 등록 순서. delete-applicant로 중간행이 삭제되면 시트가
// 줄어들 수 있어(행 고정 정책은 "현재근무자" 탭 한정 — 지원자 탭은 delete-applicant 시 deleteRow
// 허용됨, 함정노트 "인사현황 시트 행 고정" 절 참조) 이 값은 매 실행 시 새로 계산해야 한다(캐시 금지).
function computeApplMaxRow_(applRows) {
  var max = 0;
  (applRows || []).forEach(function (a) {
    var r = Number(a && a["_sheet_row"]) || 0;
    if (r > max) max = r;
  });
  return max;
}

// ---- 메시지 빌더 (순수 함수 — GAS 서비스 미사용) ----
// applRows/onboRows = readSchemaSheet_(ss, SHEET_APPL/SHEET_ONBO, SCHEMAS.appl/onbo) 결과 그대로 전달.
// todayStr = "yyyy-MM-dd"(KST 기준 "오늘"). 호출부(sendDailyHrReminder)에서 Asia/Seoul로 고정 계산해 넘긴다.
// effectiveApplPointer = 직전 브리핑까지 "이미 안내한" 지원자 탭의 최대 행번호(호출부에서 스크립트
// 속성 lastAnnouncedApplRow를 읽어 최초실행·시트축소(delete-applicant) 케이스까지 안전 처리한 뒤 넘김.
// 이 함수 자체는 그 값을 그대로 필터 기준으로만 쓰는 순수 함수 — PropertiesService를 직접 만지지 않음).
// [추가 2026-07-20 A-5] decision 인자 = 이번 회차에 노출할 결정대기 1건(호출부 sendDailyHrReminder가
//   pickDecisionForBriefing_로 선정 후 전달) 또는 미결 0건이면 null. 이 함수 자체는 순수 함수 유지
//   — 로테이션 마킹(마지막노출일 갱신) 등 쓰기는 호출부 책임.
function buildDailyHrReminderMessage_(applRows, onboRows, todayStr, effectiveApplPointer, empRows, decision) {
  var today = parseFlexibleDate_(todayStr);
  var todayEpoch = today ? epochDay_(today) : epochDay_(mkUTCDate_(1970, 1, 1));
  var applPointer = Number(effectiveApplPointer) || 0;

  // ① 신규 이력서 — [2026-07-08 설계 변경, A-6 감사 지적 반영] 기존엔 메모의 "[자동 수집 오늘날짜]"
  // 마커로 "오늘"만 판정했으나, 08시 발송 "이후" 등록된 지원자는 그날은 마커가 아직 안 잡히고
  // 다음날엔 마커가 "어제"가 되어 걸러져 **어떤 브리핑에도 영구 누락**되는 결함이 있었다.
  // → 지원자 탭이 register-applicant의 appendRow만 쓰는 append-only 구조(행번호=등록순)라는 점을
  //   이용해 "직전 브리핑 이후 새로 등록된 행(행번호 > applPointer)"으로 판정 교체.
  //   발송 전/후 등록 타이밍과 무관하게 다음 회차에 **정확히 1회**만 노출되고, 그 다음날은 빠진다
  //   (매니저 확정 사양 — 면접 미배정자를 매일 반복 노출하는 방식은 채택하지 않음).
  var resumes = [];
  (applRows || []).forEach(function (a) {
    var r = Number(a && a["_sheet_row"]) || 0;
    if (r <= applPointer) return;
    resumes.push({
      name: a["지원자명"] || "(이름 미상)",
      position: a["지원 포지션"] || "",
      grade: a["면접 평점"] || ""
    });
  });

  // ② 오늘 면접 — 면접 일정이 오늘 날짜인 지원자. 전형 단계 불합격·탈락은 제외(허브 index.html의
  // /불합격|탈락/ 판정 패턴과 동일 정규식 사용 — badgeStyle()·STAGE_ORDER 참고. 이미 탈락 처리된
  // 건까지 브리핑에 올리지 않기 위한 안전장치 — 스펙엔 명시 없으나 기존 리마인드 로직 유지).
  var interviews = [];
  (applRows || []).forEach(function (a) {
    var stage = String(a["전형 단계"] || "").trim();
    if (/불합격|탈락/.test(stage)) return;
    var iv = a["면접 일정"];
    if (!iv) return;
    var dt = parseFlexibleDate_(iv);
    if (!dt) return;
    if (epochDay_(dt) !== todayEpoch) return;
    interviews.push({
      name: a["지원자명"] || "(이름 미상)",
      position: a["지원 포지션"] || "",
      time: fmtTimeOnly_(iv),
      interviewer: a["담당 면접관"] || "",
      _sortKey: String(iv)
    });
  });
  interviews.sort(function (x, y) { return x._sortKey.localeCompare(y._sortKey); });

  // ③④ 온보딩 — 완료(isOnboDoneYes_)는 전부 제외. 카테고리 구분 없이 완료 기한만 기준.
  //   ③ 오늘 온보딩: 완료 기한 == 오늘.
  //   ④ 지연: 완료 기한 < 오늘 — [2026-07-23 매니저 지시] 브리핑 노출 제거. 집계는 렌더 시그니처
  //     호환용으로만 남기며 renderDailyHrReminderText_는 더 이상 출력하지 않는다(③ 판정 로직 공유 루프라 유지).
  var todayOnbo = [];
  var overdue   = [];
  (onboRows || []).forEach(function (o) {
    if (isOnboDoneYes_(o["완료 여부"])) return;
    var due = o["완료 기한"];
    if (!due) return;
    var dt = parseFlexibleDate_(due);
    if (!dt) return;
    var e = epochDay_(dt);
    var target = o["대상 신입 직원"] || "";
    if (e === todayEpoch) {
      todayOnbo.push({ target: target, task: o["체크 항목"] || "", owner: o["담당자"] || "" });
    } else if (e < todayEpoch) {
      overdue.push({ target: target });
    }
  });

  // ⑤ 생일 — [추가 2026-07-18 A-7] 운영허브 birthdayCard(D-7 위젯)와 동일 기준(bday "MM-DD" 안전
  //   파생 필드·재직자·겸직 중복 제거·D-0~D-7·연말연초 롤오버). 순수 계산은 buildBirthdayList_에 위임.
  var birthdays = buildBirthdayList_(empRows, todayStr);

  return renderDailyHrReminderText_(todayStr, resumes, interviews, todayOnbo, overdue, birthdays, decision);
}

// [추가 2026-07-18 A-7] 아침 브리핑 생일 섹션 데이터 — 운영허브 birthdayCard와 동일 기준.
//   · 데이터원 = emp의 안전 파생 필드 bday("MM-DD", 연도·성별 없음). 원본 생년·주민번호 미노출.
//   · 재직자만(재직 상태 "퇴사" 제외), 겸직 중복행은 최초 유효값만 채택(위젯과 동일).
//   · D-0(당일)~D-7(오늘 포함)만. 올해 날짜가 지났으면 내년으로 넘겨 재계산(12월→1월 롤오버).
//   · 날짜연산은 GAS 실행 타임존 오프바이원 방지를 위해 UTC 자정(mkUTCDate_/epochDay_)으로 통일
//     — 브리핑의 다른 섹션(면접·온보딩 판정)과 동일 규약. 반환 = [{name,dept,mm,dd,d}] (d 오름차순).
function buildBirthdayList_(empRows, todayStr) {
  var today = parseFlexibleDate_(todayStr);
  if (!today) return [];
  var ty = today.getUTCFullYear();
  var todayEpoch = epochDay_(today);

  var byName = {};
  (empRows || []).forEach(function (e) {
    if (String(e["재직 상태"] || "") === "퇴사") return;
    var nm = String(e["성명"] || e["이름"] || "").trim();
    if (!nm) return;
    if (byName[nm] && byName[nm].mm) return; // 겸직 중복행은 최초 유효값만
    var m = /^(\d{2})-(\d{2})$/.exec(String(e["bday"] || "").trim());
    var dept = String(e["부서"] || "").replace(/\n/g, " ").trim();
    if (!byName[nm] || m) {
      byName[nm] = { dept: dept, mm: m ? parseInt(m[1], 10) : null, dd: m ? parseInt(m[2], 10) : null };
    }
  });

  var list = [];
  Object.keys(byName).forEach(function (nm) {
    var b = byName[nm];
    if (b.mm == null || b.dd == null) return;
    var d = mkUTCDate_(ty, b.mm, b.dd);
    if (!d) return;
    var e = epochDay_(d);
    if (e < todayEpoch) { d = mkUTCDate_(ty + 1, b.mm, b.dd); if (!d) return; e = epochDay_(d); }
    var dn = e - todayEpoch;
    if (dn < 0 || dn > 7) return;
    list.push({ name: nm, dept: b.dept, mm: b.mm, dd: b.dd, d: dn });
  });
  list.sort(function (a, b) { return a.d - b.d; });
  return list;
}

// 지연 항목을 대상자별 건수로 집계 — "대상자 N건 · 대상자 N건" 한 줄 요약(개별 나열 금지, 매니저 확정 사양).
// 대상자 미기재 행은 "(대상자 미상)"으로 묶는다. 처음 등장한 순서를 유지.
function summarizeOverdueByTarget_(overdueItems) {
  var order = [];
  var counts = {};
  (overdueItems || []).forEach(function (o) {
    var key = String(o.target || "").trim() || "(대상자 미상)";
    if (!counts.hasOwnProperty(key)) { counts[key] = 0; order.push(key); }
    counts[key]++;
  });
  return order.map(function (k) { return k + " " + counts[k] + "건"; }).join(" · ");
}

// ---- 텍스트 렌더링 (순수 함수) ----
// 고정 구성(매니저 확정 사양, 2026-07-05): 이력서/면접/온보딩(·생일)은 0건이어도 "• 없음"으로 항상 표시.
// [제거 2026-07-23 매니저 지시] ⚠️ 지연 요약 줄·🎯 오늘의 결정 코너는 브리핑에서 제외(결정대기 큐·
//   decision-add 액션·pickDecisionForBriefing_ 등 함수 자체는 유지, 브리핑 노출만 중단).
//   overdue/decision 인자는 호출부 호환을 위해 시그니처만 유지하고 본문에서는 사용하지 않는다.
function renderDailyHrReminderText_(todayStr, resumes, interviews, todayOnbo, overdue, birthdays, decision) {
  var blocks = ["📋 웰페리온 HR 아침 브리핑 (" + todayStr + ")"];

  var l1 = ["📄 신규 이력서 " + resumes.length + "건"];
  if (resumes.length) {
    resumes.forEach(function (r) {
      l1.push("• " + r.name + (r.position ? " · " + r.position : "") + (r.grade ? " · " + r.grade : ""));
    });
  } else {
    l1.push("• 없음");
  }
  blocks.push(l1.join("\n"));

  var l2 = ["🗓️ 오늘 면접 " + interviews.length + "건"];
  if (interviews.length) {
    interviews.forEach(function (iv) {
      l2.push("• " + (iv.time ? iv.time + " " : "") + iv.name +
        (iv.position ? " · " + iv.position : "") +
        (iv.interviewer ? " · " + iv.interviewer : ""));
    });
  } else {
    l2.push("• 없음");
  }
  blocks.push(l2.join("\n"));

  var l3 = ["🧭 오늘 온보딩 " + todayOnbo.length + "건"];
  if (todayOnbo.length) {
    todayOnbo.forEach(function (o) {
      l3.push("• " + o.target + (o.task ? " · " + o.task : "") + (o.owner ? " · " + o.owner : ""));
    });
  } else {
    l3.push("• 없음");
  }
  blocks.push(l3.join("\n"));

  // ⑤ 생일 — [추가 2026-07-18 A-7] 다가오는 생일(D-7 이내). 당일(D-0)은 🎉 축하 문구로 강조,
  //   다가오는 건은 D-N + 월/일. 다른 고정 섹션과 동일하게 0건이어도 "• 없음"으로 항상 표시.
  //   텔레그램은 parse_mode 미지정 순수 텍스트라 강조는 이모지·문구로만(마크업 없음).
  var bdays = birthdays || [];
  var l4 = ["🎂 생일 (7일 이내) " + bdays.length + "명"];
  if (bdays.length) {
    bdays.forEach(function (b) {
      if (b.d === 0) {
        l4.push("🎉 오늘 · " + b.name + (b.dept ? " · " + b.dept : "") + " — 생일을 진심으로 축하합니다!");
      } else {
        l4.push("• D-" + b.d + " " + b.name + (b.dept ? " · " + b.dept : "") + " (" + b.mm + "월 " + b.dd + "일)");
      }
    });
  } else {
    l4.push("• 없음");
  }
  blocks.push(l4.join("\n"));

  return blocks.join("\n\n");
}

// [추가 2026-07-04, 개편 2026-07-05] 자동화 로그용 — 브리핑 텍스트에서 집계 요약만 뽑아낸다.
// 순수 함수. 섹션 헤더(이력서/면접/온보딩/생일) 각각의 건수를 파싱.
// [제거 2026-07-23 매니저 지시] 지연·결정 섹션이 브리핑에서 빠지면서 해당 파싱 줄도 함께 제거.
function summarizeReminderText_(text) {
  var s = String(text || "");
  var parts = [];
  var mr = s.match(/📄 신규 이력서 (\d+)건/);
  if (mr) parts.push("이력서 " + mr[1] + "건");
  var mi = s.match(/🗓️ 오늘 면접 (\d+)건/);
  if (mi) parts.push("면접 " + mi[1] + "건");
  var mo = s.match(/🧭 오늘 온보딩 (\d+)건/);
  if (mo) parts.push("온보딩 " + mo[1] + "건");
  var mb = s.match(/🎂 생일 \(7일 이내\) (\d+)명/); // [추가 2026-07-18 A-7]
  if (mb) parts.push("생일 " + mb[1] + "명");
  return parts.length ? parts.join(" · ") : "챙길 항목 없음";
}

// [추가 2026-07-14, CFO 협업·매니저 승인] 텔레그램 발송 릴레이 — CFO 자율 루틴(아침 브리핑·개선 제안
//   알림)의 발송 위탁용. 토큰/채팅ID는 이 스크립트의 기존 스크립트 속성(TG_BOT_TOKEN/TG_CHAT_ID)을
//   그대로 재사용(재등록·토큰 이동 없음 — "봇 토큰은 AI가 직접 다루지 않는다" 원칙 유지, STATE_이력
//   2026-07 리마인드 활성화 항목 참조). admin 게이트 필수. text만 받아 발송하고 결과 코드를 반환.
//   속성 미설정 시 리마인드와 동일하게 조용히 스킵(no_tg_key). 자동화 로그에 발송 계측 남김.
function handleTgRelay_(body) {
  var text = String((body && body.text) || "").slice(0, 4000);
  if (!text.trim()) return { ok: false, error: "no_text" };
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty("TG_BOT_TOKEN");
  var chatId = props.getProperty("TG_CHAT_ID");
  if (!token || !chatId) return { ok: false, skipped: "no_tg_key" };
  var resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/sendMessage", {
    method: "post",
    payload: { chat_id: chatId, text: text },
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  try {
    handleLogAdd_({ actor: "CFO 릴레이", work: "텔레그램 발송 위탁", detail: text.slice(0, 80), result: code === 200 ? "발송" : ("실패 " + code) });
  } catch (_logErrR) { Logger.log("handleTgRelay_: 자동화 로그 기록 실패 — " + String(_logErrR && _logErrR.message || _logErrR)); }
  return { ok: code === 200, code: code };
}

// [추가 2026-07-15 A-5] 지원자 주소 ↔ 웰페리온(서빙고로 413) 직선거리(km) — 읽기 전용, 시트 쓰기 없음.
//   기준점은 최초 1회만 지오코딩해 스크립트 속성(GEO_BASE_LAT/LNG)에 좌표 고정 후 재사용.
//   지원자 주소는 요청 시 지오코딩(Maps.newGeocoder, region=kr) → 하버사인 계산 — 좌표는 응답에 포함하지 않고
//   주소 해시별 결과 km만 스크립트 속성에 캐시(좌표 미저장 = PII 최소화). 빈 주소·지오코딩 실패는 예외 없이
//   ok:false로 반환(비파괴 — 카드 렌더링을 막지 않음). 다른 핸들러·액션·행고정 계약 무변경.
var GEO_BASE_ADDRESS = "서울특별시 용산구 서빙고로 413";
function handleGeoDistance_(body) {
  var address = String((body && body.address) || "").trim();
  if (!address) return { ok: false, error: "address_required" };
  try {
    var props = PropertiesService.getScriptProperties();
    var baseLat = parseFloat(props.getProperty("GEO_BASE_LAT"));
    var baseLng = parseFloat(props.getProperty("GEO_BASE_LNG"));
    if (!baseLat || !baseLng || isNaN(baseLat) || isNaN(baseLng)) {
      var baseGeo = Maps.newGeocoder().setRegion("kr").geocode(GEO_BASE_ADDRESS);
      if (!baseGeo || !baseGeo.results || !baseGeo.results.length) return { ok: false, error: "base_geocode_failed" };
      var baseLoc = baseGeo.results[0].geometry.location;
      baseLat = baseLoc.lat; baseLng = baseLoc.lng;
      // 좌표 타당성(서울 근방) 방어 — 비정상 지오코딩 결과는 고정하지 않는다.
      if (baseLat < 37 || baseLat > 38 || baseLng < 126 || baseLng > 128) return { ok: false, error: "base_geocode_out_of_range" };
      props.setProperty("GEO_BASE_LAT", String(baseLat));
      props.setProperty("GEO_BASE_LNG", String(baseLng));
    }
    var cacheKey = "GEO_DIST_" + Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, address, Utilities.Charset.UTF_8));
    var cachedKm = props.getProperty(cacheKey);
    if (cachedKm !== null && cachedKm !== "") {
      return { ok: true, km: Number(cachedKm), cached: true };
    }
    var geo = Maps.newGeocoder().setRegion("kr").geocode(address);
    if (!geo || !geo.results || !geo.results.length) return { ok: false, error: "geocode_failed" };
    var loc = geo.results[0].geometry.location;
    var km = Math.round(haversineKm_(baseLat, baseLng, loc.lat, loc.lng) * 10) / 10;
    try { props.setProperty(cacheKey, String(km)); } catch (_geoCapErr) { /* 속성 용량 초과 등은 캐시만 스킵(비파괴) */ }
    return { ok: true, km: km, cached: false };
  } catch (e) {
    return { ok: false, error: "geo_exception", message: String(e && e.message || e) };
  }
}
function haversineKm_(lat1, lng1, lat2, lng2) {
  var R = 6371; // 지구 반지름(km)
  var toRad = function (d) { return d * Math.PI / 180; };
  var dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// [추가 2026-07-20 A-5, 매니저 승인 개선④] 결정대기 로테이션 선정 — 순수 함수(GAS 서비스 미사용).
//   상태==="pending"인 행 중 "가장 오래 노출 안 된" 1건을 고른다(마지막노출일 오름차순, 공란=최우선
//   — 아직 한 번도 노출 안 된 건을 새로 노출된 건보다 먼저 보여줌). 동률이면 id가 작은(먼저 등록된) 건.
//   반환: { _sheet_row, id, summary, options:[...], recommendation } 또는 미결 0건이면 null.
function pickDecisionForBriefing_(decisionRows) {
  var pending = (decisionRows || []).filter(function (r) { return String(r["상태"] || "").trim() === "pending"; });
  if (!pending.length) return null;

  var best = null;
  pending.forEach(function (r) {
    var exposed = String(r["마지막노출일"] || "").trim(); // 공란 = "" → 문자열 비교상 항상 최소값
    var id = parseInt(r["id"], 10) || 0;
    if (!best ||
        exposed < String(best["마지막노출일"] || "").trim() ||
        (exposed === String(best["마지막노출일"] || "").trim() && id < (parseInt(best["id"], 10) || 0))) {
      best = r;
    }
  });
  if (!best) return null;

  var options = [];
  try { options = JSON.parse(best["옵션JSON"] || "[]"); } catch (_eOpt) { options = []; }
  if (!Array.isArray(options)) options = [];

  return {
    _sheet_row: Number(best["_sheet_row"]) || 0,
    id: parseInt(best["id"], 10) || 0,
    summary: String(best["요지"] || ""),
    options: options,
    recommendation: String(best["추천안"] || "")
  };
}

// pickDecisionForBriefing_이 고른 행의 "마지막노출일"만 오늘 날짜로 갱신(로테이션 마킹, 상태·다른
// 필드는 그대로). 시트/행이 사라졌으면 조용히 스킵(브리핑 본 기능에 영향 없도록 — 다른 쓰기 헬퍼와
// 동일한 방어적 패턴).
function markDecisionExposed_(ss, sheetRow, todayStr) {
  if (!sheetRow) return;
  try {
    var sh = ss.getSheetByName(SHEET_DECISION);
    if (!sh) return;
    sh.getRange(sheetRow, 7).setValue(todayStr); // 마지막노출일 = SCHEMAS.decision의 7번째 컬럼
  } catch (_eMark) {
    Logger.log("markDecisionExposed_: 실패 — " + String(_eMark && _eMark.message || _eMark));
  }
}

// ---- GAS 엔트리포인트 ----

// 시간 트리거 전용 — doPost 흐름과 무관(단, doPost의 run-reminder 관리자 액션에서도 즉시실행용으로
// 그대로 재사용됨 — 트리거 호출부는 반환값을 무시하므로 안전). 토큰/채팅ID는 스크립트 속성에서만
// 읽고, 미설정 시 크래시 없이 Logger만 남기고 조용히 종료한다(코드 하드코딩 절대 금지).
// [2026-07-05] run-reminder 액션이 결과를 응답으로 돌려줘야 해서 각 종료 경로에 결과 객체를
// 반환하도록 보강(기존 트리거 흐름·로직은 무변경, throw 없음도 그대로 유지).
function sendDailyHrReminder() {
  try {
    var props = PropertiesService.getScriptProperties();
    var token = props.getProperty("TG_BOT_TOKEN");
    var chatId = props.getProperty("TG_CHAT_ID");
    if (!token || !chatId) {
      Logger.log("sendDailyHrReminder: TG_BOT_TOKEN/TG_CHAT_ID 스크립트 속성 미설정 — 발송 스킵");
      // [추가 2026-07-04] 자동화 로그 계측 — 실패해도 리마인드 본 기능엔 영향 없도록 try로 감싼다.
      try {
        handleLogAdd_({ actor: "리마인드 루틴", work: "아침 브리핑 발송", detail: "TG_BOT_TOKEN/TG_CHAT_ID 미설정", result: "스킵" });
      } catch (_logErrA) { Logger.log("sendDailyHrReminder: 자동화 로그 기록 실패(스킵 케이스) — " + String(_logErrA && _logErrA.message || _logErrA)); }
      return { ok: true, sent: false, detail: "TG_BOT_TOKEN/TG_CHAT_ID 미설정 — 발송 스킵" };
    }

    var ss = SpreadsheetApp.openById(HR_SHEET_ID);
    var applRows = readSchemaSheet_(ss, SHEET_APPL, SCHEMAS.appl);
    var onboRows = readSchemaSheet_(ss, SHEET_ONBO, SCHEMAS.onbo);
    // [추가 2026-07-18 A-7] 생일 섹션용 재직자 — readCurrentSheet_가 안전 파생 bday("MM-DD")를 붙여 반환
    //   (role 미지정=주민번호 마스킹, bday는 '생일' 열 파생이라 마스킹 무관·유지). 읽기만, 쓰기 없음.
    var empRows = readCurrentSheet_(ss);
    var todayStr = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd");

    // [2026-07-08] 섹션① "신규 이력서" 판정용 행 포인터 — Script Properties 키 lastAnnouncedApplRow.
    //   · 미설정(최초 실행) = 과거 전체를 신규로 덤프하지 않도록 이번 회차는 신규 0건 처리하고
    //     포인터를 현재 최대 행으로 초기화만 한다(안전장치, 지시서 명시 요구사항).
    //   · 기설정 = delete-applicant로 지원자 탭이 줄어들어 저장된 포인터보다 현재 최대 행이
    //     작아질 수 있으므로 Math.min으로 클램프(그래야 이후 새로 append되는 행이 옛 포인터에
    //     가려 영구 누락되는 사고를 막는다 — appl 탭은 "현재근무자"와 달리 행 고정 대상이 아님).
    var __applPointerRaw = props.getProperty("lastAnnouncedApplRow");
    var __applPointerIsFirstRun = (__applPointerRaw === null || __applPointerRaw === "");
    var __applCurrentMaxRow = computeApplMaxRow_(applRows);
    var __applEffectivePointer = __applPointerIsFirstRun
      ? __applCurrentMaxRow
      : Math.min(Number(__applPointerRaw) || 0, __applCurrentMaxRow);

    // [제거 2026-07-23 매니저 지시] ⑥ 오늘의 결정 — 브리핑 노출·로테이션 선정·마지막노출일 마킹 중단.
    //   결정대기 큐(시트·decision-add 액션)와 pickDecisionForBriefing_/markDecisionExposed_ 함수는 유지.
    //   decision 자리는 null 고정으로 호출 시그니처만 유지(불필요한 시트 읽기/쓰기 방지).
    var text = buildDailyHrReminderMessage_(applRows, onboRows, todayStr, __applEffectivePointer, empRows, null);

    // 이번 회차에서 "신규"로 판정하는 데 쓴 기준선(__applEffectivePointer)까지는 이미 안내에
    // 반영됐으므로, 다음 회차 기준선을 현재 최대 행으로 전진시킨다(빌드 직후 갱신 — 매니저 지시서
    // "메시지 빌드 후" 방식 채택. 텔레그램 발송 성공 여부와 무관하게 전진해 재시도 큐 없는 기존
    // 구조와 일관되게 유지).
    props.setProperty("lastAnnouncedApplRow", String(__applCurrentMaxRow));

    var resp = UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/sendMessage", {
      method: "post",
      payload: { chat_id: chatId, text: text },
      muteHttpExceptions: true
    });
    var code = resp.getResponseCode();
    if (code !== 200) {
      Logger.log("sendDailyHrReminder: 텔레그램 발송 실패(" + code + ") " + resp.getContentText().slice(0, 300));
    } else {
      Logger.log("sendDailyHrReminder: 발송 완료 (" + todayStr + ")");
    }
    // [추가 2026-07-04] 자동화 로그 계측 — 실패해도 리마인드 본 기능엔 영향 없도록 try로 감싼다.
    var __reminderSummary = summarizeReminderText_(text);
    try {
      handleLogAdd_({
        actor: "리마인드 루틴",
        work: "아침 브리핑 발송",
        detail: __reminderSummary,
        result: (code === 200) ? "발송" : ("실패(" + code + ")")
      });
    } catch (_logErrB) {
      Logger.log("sendDailyHrReminder: 자동화 로그 기록 실패 — " + String(_logErrB && _logErrB.message || _logErrB));
    }
    return (code === 200)
      ? { ok: true, sent: true, detail: __reminderSummary }
      : { ok: true, sent: false, detail: "텔레그램 발송 실패(" + code + ")" };
  } catch (err) {
    // 토큰이 fetch URL에 포함되므로(UrlFetchApp 예외 메시지가 요청 URL을 되돌려주는 경우 대비),
    // 로그·응답 어디에도 토큰 원문이 남지 않도록 치환 후 사용(토큰 노출 절대 금지 원칙).
    var __safeMsg = String((err && err.message) || err || "");
    if (typeof token !== "undefined" && token) { __safeMsg = __safeMsg.split(token).join("***"); }
    Logger.log("sendDailyHrReminder: 예외 — " + __safeMsg);
    return { ok: false, sent: false, detail: "예외 — " + __safeMsg };
  }
}

// 기존 sendDailyHrReminder 트리거를 전부 삭제하고 매일 KST kstHour시대(기본 8) 트리거를 새로 만든다.
// appsscript.json timeZone이 Asia/Seoul이 아니게 되는 경우를 대비해, 스크립트 tz 기준으로
// "KST kstHour:00"에 해당하는 시(hour)를 역산해서 등록한다(Asia/Seoul은 서머타임 없는 고정 UTC+9).
// [2026-07-05] doPost install-reminder-trigger 관리자 액션에서 hour 파라미터로 재사용하기 위해
// kstHour 인자를 추가(무인자 호출은 기존과 동일하게 8시 유지 — 하위호환).
function installDailyReminderTrigger(kstHour) {
  var targetKstHour = (kstHour === undefined || kstHour === null || kstHour === "" || isNaN(Number(kstHour))) ? 8 : Number(kstHour);

  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  triggers.forEach(function (t) {
    if (t.getHandlerFunction() === "sendDailyHrReminder") {
      ScriptApp.deleteTrigger(t);
      removed++;
    }
  });

  var scriptTz = Session.getScriptTimeZone();
  var targetHour = targetKstHour;
  if (scriptTz !== "Asia/Seoul") {
    var now = new Date();
    var kY = Number(Utilities.formatDate(now, "Asia/Seoul", "yyyy"));
    var kM = Number(Utilities.formatDate(now, "Asia/Seoul", "MM"));
    var kD = Number(Utilities.formatDate(now, "Asia/Seoul", "dd"));
    var kstInstant = new Date(Date.UTC(kY, kM - 1, kD, targetKstHour - 9, 0, 0)); // KST targetKstHour:00 = 전날 UTC (targetKstHour-9)시
    targetHour = Number(Utilities.formatDate(kstInstant, scriptTz, "H"));
  }

  ScriptApp.newTrigger("sendDailyHrReminder")
    .timeBased()
    .everyDays(1)
    .atHour(targetHour)
    .create();

  var msg = "installDailyReminderTrigger: 기존 트리거 " + removed + "개 삭제 → 신규 트리거 생성 (scriptTz=" + scriptTz + ", kstHour=" + targetKstHour + ", atHour=" + targetHour + ")";
  Logger.log(msg);
  return { ok: true, removed: removed, scriptTz: scriptTz, kstHour: targetKstHour, atHour: targetHour };
}

// =====================================================================
// [추가 2026-07-05] doPost 관리자 액션 2종 — 아침 브리핑 원격 실행·트리거 재설치
//   지금까지 sendDailyHrReminder()를 시험하려면 스크립트 편집기에서 직접 함수를 클릭 실행해야 했던
//   불편을 없앤다. 둘 다 requireAdmin_ 게이트(다른 쓰기 액션과 동일한 adminPassword 검증 패턴).
// =====================================================================

// run-reminder — sendDailyHrReminder()를 즉시 실행하고 결과를 그대로 응답한다.
// sendDailyHrReminder()는 어떤 경로로도 throw하지 않고 항상 {ok, sent, detail} 형태를 반환하도록
// 되어 있어(위 함수 참조), 그 반환값을 그대로 내려주면 스펙의 {ok:true, sent:true/false, detail:"..."}
// 형태가 된다. detail에는 토큰 값이 절대 섞이지 않는다(sendDailyHrReminder_ 내부에서 치환 처리).
function handleRunReminder_(body) {
  var result = sendDailyHrReminder();
  return result || { ok: true, sent: false, detail: "실행됨(반환값 없음)" };
}

// install-reminder-trigger — hour 파라미터(기본 9, KST 기준)로 기존 sendDailyHrReminder 트리거를
// 전부 삭제 후 재설치한다. 실제 삭제·생성 로직은 installDailyReminderTrigger()를 그대로 재사용.
function handleInstallReminderTrigger_(body) {
  var hour = parseInt((body && body.hour), 10);
  if (isNaN(hour) || hour < 0 || hour > 23) hour = 9;
  installDailyReminderTrigger(hour);
  return { ok: true, hour: hour };
}
