# -*- coding: utf-8 -*-
"""인사(CHRO) 도메인 API — 읽기 라우트 (인사 데이터 AWS 이관 1단계 · 2026-09-05 CHRO/A-5).

근거 = CTO 회신 status/briefs/CTO-2026-09-05-인사데이터-AWS이관-서버준비-회신.md
       (§1 표 3·4 경로·인증·스택 · §2 6단계 중 ①읽기 미러 · §3 테스트 데이터 격리).
표 정의 = common/schema.sql 의 hr 스키마 22개 표. 적재 = migrate_hr.py.
app.py 가 같은 폴더의 api_*.py 를 자동 등록한다 — app.py 본문은 건드리지 않는다.

  GET  /api/hr/health                 표별 행수 · 마지막 적재 상태 · 권한·마스킹·기록 켜짐 여부
  GET  /api/hr/{db}                   db = emp·exitroster·exit·appl·hire·eval·onbo·blacklist·leave·autolog
  POST /api/hr/read                   본문 {"db":"appl"} — 현행 화면이 GAS 를 부르던 모양 그대로

★ 화면 수정을 최소화하는 형태를 택한 근거(지시서 요구 · 판단 3가지)
  1) 봉투에 results 와 data 를 같이 싣는다.
     현행 허브(3. 웰페리온 가이드/chro/hub/index.html)의 유일한 정규화 함수가
     `extractResults(raw){ if(raw&&Array.isArray(raw.results)) return raw.results; ... }` 하나다(실측 1곳).
     그래서 results 를 그대로 실으면 화면 데이터 계층은 한 줄도 안 고쳐도 된다.
     동시에 ERP 표준 봉투는 {ok, data} 라(회신 §1-4 · 배990 선례) data 에도 같은 배열을 싣는다.
     한 배열을 두 이름으로 가리키는 것뿐이라 비용이 없고, ③단계(화면 전환)에서 results 를 떼면 된다.
     ★마스킹도 이 한 배열을 제자리에서 고친다 — 복사본을 만들면 메모리가 두 배가 되고
       한쪽만 마스킹되는 사고가 구조적으로 가능해진다.
  2) 본문 POST 호환 라우트를 둔다.
     허브는 `fetch(NOTION_FN,{method:"POST", headers:{"Content-Type":"text/plain;charset=utf-8"},
     body:JSON.stringify({db:key,...})})` 로 읽는다. GET 만 만들면 fetch 호출부 전체를
     고쳐야 하지만, 같은 모양의 POST 를 두면 화면은 주소 상수(NOTION_FN) 한 줄만 바꾸면 된다.
     ★Content-Type 이 text/plain 이라 FastAPI 자동 본문 파싱(Pydantic)이 못 받는다 —
       api_reception.py 와 같이 Request 로 원문을 받아 직접 json.loads 한다.
     ★본문에 실려 오는 비밀 문자열은 읽지도, 기록하지도 않는다(아래 인증·권한 절).
  3) 각 행에 _sheet_row 를 그대로 실어 준다.
     화면·러너가 행번호를 58개소/7파일에서 쓴다(사진 파일명 r<row>.jpg 포함). 새 기본키(_id)를 같이 주되
     _sheet_row 를 끊지 않아야 ①단계에서 화면이 산다. ⚠️ 새 쓰기 경로는 _sheet_row 를 열쇠로 받지 않는다 —
     받으면 행번호 의존이 그대로 이사한다(schema.sql hr 머리말 ①).

인증·권한: nginx auth_request 가 /api/ 전체를 이미 막는다(erp_api/api.nginx.conf) — 로그인 쿠키가 없으면 401.
  ⛔ 라우터 안에서 비밀 문자열을 검사하지 않는다(원 설계 유지) — 현행 GAS 의 공유 평문 방식을 서버로 옮기지 않는다.
  ★신원 = 관문이 넘긴 로그인 이메일(X-Erp-User). 관문 설정이 이 헤더를 항상 덮어쓰므로 위조가 불가능하다
    (api.nginx.conf 5·10행 실측). 판별식 = (역할 헤더가 admin 이고 신뢰 플래그가 켜짐)
    OR (로그인 이메일이 관리자 이메일 목록에 있음). 둘 다 아니면 뷰어.
  ⚠️ 역할 헤더(X-Erp-Role)는 기본적으로 믿지 않는다 — 관문 API 설정이 이메일 헤더만 덮어쓰고 역할 헤더는
    손대지 않아, 로그인한 사람이 그 헤더를 직접 실어 보내면 그대로 상류에 도달한다. 마스킹 분기를 그 헤더에
    거는 순간 누구나 관리자 원문을 받는 권한 상승 통로가 되므로, 관문 두 줄(api.nginx.conf 준비분)이 실제
    배포되고 클라이언트가 직접 실어 보낸 역할 헤더가 상류에 도달하지 않음을 1회 확인한 뒤에만
    HR_TRUST_ROLE_HEADER 를 켠다(헬스 응답의 identity.trust_role_header 로 현재 상태가 보인다).
  ★관리자 이메일 목록은 환경변수 HR_ADMIN_EMAILS(쉼표 구분) — 기본값은 빈 목록이다. 관리자 계정이
    경영지원부 공용 계정이라 이메일을 코드에 박지 않는다(CTO 설계 의도 보존). 목록이 비어 있고 신뢰
    플래그도 꺼져 있으면 전원이 뷰어 = 전원이 마스킹본을 받는다(실패 방향이 안전한 쪽으로 기운다).
마스킹: 현행 GAS 백엔드와 등가가 되게 3층으로 나눈다. ★현행도 실질 3층이다 — .deploy-hr/Code.js 의
  maskEmpRrnUnconditional_ 이 역할과 무관하게 도는 층이고, 2026-07-14 실노출 사고 뒤에 추가됐다.
  그 추가 사유가 주석에 '운영허브가 정상 읽기도 관리자 자격으로 호출해 뷰어 마스킹이 전혀 안 걸렸다'라고
  적혀 있는데, 이 API 의 관리자 경로가 정확히 그 조건이다. 그래서 뷰어 분기 안에만 두지 않는다.
  0층 상시 층(역할 무관 — 관리자 응답에도 걸린다) — 주민번호 13자리·축약형(셀 전체 일치)을 고정 토큰으로
    치환하고, 칸 이름에 '주민'이 든 칸과 값이 그대로 칸 이름이 된 오염 헤더를 통째로 제거한다.
    응답 행 전체를 재귀 순회하므로(정규화 칸 · 원본 레코드 data JSONB 통째 · 중첩 값) 메모·비고·면담 내용·
    평가 피드백 같은 자유 텍스트 안의 주민번호도 같이 걸린다.
    ★적재가 떨어뜨리는 것은 칸 이름 3종뿐이라(migrate_hr.py DROP_FIELDS) 자유 텍스트는 이 층이 유일한 방어다.
    ★'지금은 적재 원천이 GAS 라 이미 가려져 들어온다'는 상류의 우연이고 ⑤단계에서 GAS 를 끄면 사라진다 —
      그래서 이 API 자신의 불변식으로 못을 박는다.
    ⛔ 연락처는 이 층에 넣지 않는다 — 현행 백엔드가 관리자에게 연락처 원문을 주고 허브 임직원·지원자 화면이
      그 값을 쓴다. 여기서 가리면 '현행과 등가'가 아니라 기능 축소다(연락처는 1층 = 뷰어 정책 소관).
  1층 뷰어 정책(뷰어 응답에만) — 0층에 더해 연락처(휴대폰·국가번호형)와 MASK_EMAIL 정책을 태운다.
    ★치환은 고정 토큰이다 — GAS 는 주민번호 앞 6자리를 남겼으나 그게 곧 생년월일이라 여기서는 남기지 않는다.
    ⛔ 이메일은 현행과 같이 마스킹하지 않는다 — 가릴지 여부가 매니저 확인 항목이라 MASK_EMAIL 상수 한 곳만
      두고 기본은 현행 유지다.
  2층 생년 파생(관리자 응답에만) — 직원 표(emp·exitroster)의 생년 칸에서 표준 날짜 표기(YYYY-MM-DD)와
    만나이를 파생해 싣는다. 뷰어 응답에서는 생년월일·나이 두 키를 제거한다. 허브 임직원 표가 이 두 필드를
    그대로 읽고(index.html 899~901행), 원본 주민번호는 응답 어디에도 안 내려가는 것이 현행 정책이므로
    파생은 반드시 서버가 한다. 만나이 기준일은 한국 시간 기준 오늘(KST 고정 오프셋 명시).
    ★순서는 2층 → 0층 → 1층이다. 0층을 먼저 태우면 파생 입력이 지워진다.
  ★응답 봉투의 masked 칸은 '1층(뷰어 정책)이 걸렸는가'를 뜻한다 — 0층은 역할과 무관하게 늘 걸리므로
    masked=false 가 '아무것도 안 가렸다'는 뜻이 아니다. 조회 기록에 남기는 값과 같은 값이다.
  ★프론트의 임직원 표 2셀 가림은 그대로 둔다 — 서버 마스킹과 이중으로 겹치게 하는 것이 의도다.
  ★공개 자동화로그의 이니셜 마스킹(명부 50명 미만이면 응답 거부하는 페일세이프)은 공개 라우트 규칙이라
    이 API 범위 밖이다.

열쇠 단위 차단: 관문은 화면만 잠그고 API 경로는 로그인 여부만 본다 — 주소만 알면 인사 화면 권한이 없는
  계정도 원문을 받는다. 그래서 뷰어가 못 여는 열쇠를 VIEWER_DENY_DBS 한 곳에 모은다(최종 목록은 매니저 확인 대상).
  ★판정은 역할(role == ROLE_VIEWER)로 한다 — '마스킹이 걸렸는가'로 판정하면 0층 상시화 같은 마스킹 정책
    변경이 곧바로 열람 범위 변경으로 새어 나간다(두 값은 뜻이 다르므로 분리해 둔다).
  ⚠️ 거부 문구에 '권한'·'비밀번호'·unauthorized 낱말을 쓰지 않는다 — 허브 로그인 게이트가 응답 오류를
    정규식으로 훑어(index.html 5578행) 그 낱말이 섞이면 세션을 지우고 재로그인 화면으로 튄다.
    ★게이트가 훑는 칸은 message 가 아니라 error 코드 칸이다(실측) — 그래서 금지어 검사를 error·message
      두 칸에 다 걸고, 정적 표본이 아니라 ERROR_CODES 전체를 돌려 검사한다(자체점검).
    ★동적 문구도 같은 위험이다 — DB 예외 원문에 서버 lc_messages 가 한국어면 '권한'이 섞인다.
      그래서 바깥으로 나가는 문구는 전부 고정 문장이고, 예외는 종류 이름만 서버 로그에 남긴다.
  ★인사 화면 모듈 열람권 게이트(2026-09-11 · 결함 6 전반) — 열쇠 단위 차단만으로는 '인사 화면이 잠긴 계정이
    주소만 알고 API 를 직접 부른다'가 그대로 남는다(뷰어 허용 열쇠인 현재근무자·휴무의 74명 명부가 이메일·비고까지
    나간다 = P-03 '매니저 전용' 과 충돌). VIEWER_DENY_DBS 에 emp·leave 를 넣지 않는 이유 = 넣으면 허브 열람권이
    있는 정상 뷰어의 근무표·명부까지 죽고 문제의 본질은 그대로다. 대신 이 라우터가 관문의 기존 /auth/check 를
    화면 경로(HR_GATE_URI · 기본 /chro/hub/index.html = modules.json chro-hub-index)를 X-Original-URI 에 붙여
    대신 불러 '그 화면을 열 수 있는 계정인가'로 판정한다(_gate). 관문(erp_auth)·nginx 의 permission 코드는
    손대지 않는다. 판정 = 200 통과 · 401/403 거부(scope-blocked · gate-deny) · 그 외·예외 = 닫힘(gate-unavailable
    503 · 캐시하지 않음). 관리자(HR_ADMIN_EMAILS)도 게이트를 지난다 — 목록에 있어도 화면 열람권이 없으면
    API 도 없다(실패 방향 안전). 사무실 자동 로그인 세션은 관문이 chro-* 모듈을 막으므로 자동으로 걸린다.
    /health 는 게이트를 타지 않는다(개인정보 없음). 되돌리기 = HR_GATE_MODE=off 한 줄(재배포 불요).

살아 있는 행·신선도(2026-09-11 · 결함 2·5): 적재기가 원천에서 사라진 행을 지우지 않고 vanished_at 으로 닫으므로
  읽기는 살아 있는 행(vanished_at IS NULL)만 기본 반환한다. include_vanished=1 은 관리자 응답에서만 받고
  그때만 각 행에 _vanished_at·_vanish_reason 이 덧붙는다. 봉투에는 as_of(마지막 성공 apply run 의 finished_at)·
  as_of_run_id 가 항상 실려 소비자가 이 미러의 신선도를 안다(없으면 null · 오류 봉투에는 싣지 않는다).

조회 기록: hr.access_log 에 '누가·언제·어느 열쇠를·마스킹 여부'만 남긴다(행 내용·개인정보 값은 담지 않는다).
  읽기 라우트는 읽기 전용 세션으로 DB 를 열기 때문에 같은 연결로는 기록을 쓸 수 없다 — 쓰기 연결을 짧게 열고 닫는다.
  ★기록에 담는 값은 '검증을 통과한 것'으로만 좁힌다 — db_key 는 DBS 에 있는 열쇠일 때만 그 값을 싣고
    아니면 고정 문자열('unknown'), 기간 파라미터는 형식 검사를 통과했을 때만 값을 싣고 아니면 사유만,
    마지막 안전망으로 문자열 값 전체에 길이 상한(_AUDIT_STR_MAX)을 일괄로 건다.
    ⛔ 이 좁히기가 없으면 로그인한 아무나 본문 db 칸에 임의 텍스트(개인정보 포함)를 실어 보내는 것만으로
      감사 원장에 그 문자열을 영구히 남길 수 있다(본문 상한이 10MB · api.nginx.conf). 이 표에는 보존기간·
      삭제 배치가 없으므로 '들어오면 영구'다.
  실패 정책(비대칭 — 원문이 나가는 경로만 닫는다 · 이 비대칭 자체는 매니저 확인 항목):
    · 관리자 원문 응답인데 기록에 실패하면 응답을 주지 않고 오류 봉투로 거절한다(닫히는 방향).
    · 뷰어 마스킹 응답은 기록에 실패해도 통과시키되 헬스의 기록 실패 누계를 올린다.
  보존기간은 미정이다 — 파기·보유기간 정책이 법적 검토 지점이라 표만 만들고 삭제 배치는 넣지 않는다.

오류 봉투: 이 API 의 모든 응답이 ok(성공 여부)·error(코드)·message(사람이 읽는 문구)·_source(출처)를 갖는다.
  코드 목록 = ERROR_CODES(고정 목록 — 러너·화면이 열쇠로 삼을 수 있게 한 곳에 박아 둔다).
  ⛔ message 에는 예외 원문을 절대 잇지 않는다 — psycopg2 오류 문자열에는 표·칸 이름, 실패한 값 조각,
    접속 대상 호스트가 섞이고 접속 문자열이 잘못된 형태면 DSN 조각까지 실린다. 관문은 로그인 여부만 보므로
    인사 자료 열람 권한이 없는 계정도 이 라우트에 닿는다. 예외는 종류 이름만 서버 로그로 보낸다(_log_exc).
  ⚠️ 상태코드 모드 — 기본값은 http 다(2026-09-06 감사 지적 8 반영으로 compat 에서 바꿈).
    종전 기본값 compat(항상 200 + 본문 ok)에서는 이 오류 봉투가 허브에 보이지 않았다: 허브 조회 함수는
    200 이면 본문 ok 를 안 읽고 결과 배열만 꺼내며 없으면 빈 배열로 본다(실측) — 범위 차단·미지 열쇠·
    기간 형식 오류·저장소 열기 실패·기록 실패 거절 다섯 경우가 전부 '0건'으로 조용히 그려지고 재시도도
    오류 표시도 일어나지 않았다. '자료가 없다'와 '못 읽었다'가 화면에서 구분되지 않는 것이라
    '호환이 곧 안전'이 아니다(조용한 통과 금지 원칙 위배).
    기본을 http 로 두면 같은 조회 함수가 비200 을 오류로 잡아 화면에 오류 상태를 세운다 —
    허브를 고치지 않아도(=다른 레인을 기다리지 않아도) 조용한 0건이 사라진다.
    · 되돌리기 = HR_HTTP_STATUS_MODE=compat 한 줄(재배포 불요). 알 수 없는 값이면 http 쪽으로 붙는다.
    · 비용 = 영구 오류에도 허브가 3회 재시도한다(열쇠당 약 1.4초). 거부는 DB 에 닿기 전에 되돌아가므로
      저장소 부하는 아니고, 뷰어가 못 여는 탭은 허브가 애초에 감춰 화면에도 안 보인다.
    · 성공 응답은 어느 모드든 200 이다 — 이 스위치는 오류 경로에서만 불린다(_status).

⚠️ 배포 준비물(컷오버 전에 사람이 확정·조치해야 하는 것)
  1) HR_ADMIN_EMAILS 등록 — 매니저 실사용 계정이 확정되기 전까지는 전원이 뷰어라 관리자 화면이 열리지 않는다.
  2) 서버 DB 계정에 hr.access_log INSERT 권한.
  3) [해결 2026-09-06] 상태코드 모드 — 기본값을 http 로 바꿔 서버 쪽에서 닫았다(허브 수정 불요).
     허브 조회 함수에 본문 ok 검사를 한 줄 넣는 개선은 여전히 바람직하지만, 없어도 조용한 0건은 안 생긴다.
  4) [해결 2026-09-06] 러너 판정 확장 — 러너는 오류 코드가 정확히 unauthorized 이거나 문구에 그 한글
     낱말이 있을 때만 인증형으로 분류했는데, 이 봉투는 허브 게이트 때문에 그 둘을 다 피하도록 설계돼
     있다(두 요구가 서로 배타적이라 한 문자열로는 둘 다 만족시킬 수 없다 = 서버만으로는 못 닫는 항목).
     ⚠️ 3번(상태코드 http)으로도 안 닫힌다 — 러너는 curl 을 쓰고 curl 은 4xx·5xx 에도 종료코드가 0 이라
        상태코드가 판정에 안 들어온다. 그래서 러너(.claude/tools/hr-backend2.ps1)에 봉투 검사를 한 줄
        더했다: _source 가 이 API 의 것인 응답에서 ok 가 참이 아니면 이상(exit 6, 재전송 없음).
        판정 범위를 _source 로 좁혔으므로 현행 GAS 응답(이 칸이 없다)에는 동작 변화가 없다.
        서버가 주는 안정된 열쇠 = ERROR_CODES. 자체점검이 두 소비자의 판정식을 옮겨 와 전 코드를 검사한다.
  5) autolog 열쇠 처리 확정 — 이 열쇠를 연 목적(러너 되판정)과 VIEWER_DENY_DBS 가 서로를 상쇄한다.
     컷오버 시점에는 전원이 뷰어(1번 미조치)인데 autolog 가 뷰어 거부 목록에 있어 아무도 못 연다.
     ★2026-09-06 판단 — 목록은 지금 그대로 둔다(막힌 채). 근거: 러너 되판정(log-add.ps1
       Confirm-RowLanded)은 작업 칸을 '완전일치'로 대조하므로, 열되 실명을 가리는 절충안은 대조를
       구조적으로 깨뜨려(항상 불일치 → 거짓 '미기록') 되레 해롭다. 1단계는 읽기 미러라 쓰기·되판정은
       여전히 현행 GAS 로 가므로 지금 막혀 있어도 깨지는 것이 없다.
     ⚠️ 컷오버 전 매니저 확정 필요 — 남은 길은 러너 계정을 HR_ADMIN_EMAILS 에 넣는 것뿐인데,
       그건 그 계정에 인사 PII 전 열쇠의 관리자 읽기를 주는 것이라 사람이 받아들일 사항이다.
  6) 관리자 화면 생년월일·나이 칸 — 파생 입력(hr.employee.birth_date)이 실제로 채워지는지 먼저 센다.
     /health 의 birth_source.employee_birth_date_rows 가 그 건수다. 임직원 원천의 '생일'이 월-일 두
     조각이면 날짜 변환기를 통과하지 못해 0 에 가깝게 나오고, 그러면 컷오버 후 그 두 칸이 빈다
     (허브의 화면단 대체 경로도 주민번호 칸이 사라져 같이 막힌다). 0 이면 어느 칸에서 가져올지 확정해야 한다.
  7) HR_GATE_* 기본값 확인 — 관문 내부 주소(HR_AUTH_CHECK_URL · 기본 127.0.0.1:8000 /auth/check)와 게이트 화면
     경로(HR_GATE_URI)가 서버 실물(erp-auth.service 포트 · modules.json)과 같은지 1회. 5)의 러너 계정을 관리자
     목록에 넣는 안이 채택되면 그 계정에 허브 모듈 허용도 같이 줘야 게이트를 지난다.

테스트/더미 행: 쓰기 관문과 같은 판정(common/db.py is_test_payload) 결과가 is_test 칸에 들어 있다 —
  읽기는 기본으로 뺀다(?include_test=1 이면 포함). 새 판정 함수를 만들지 않는다(회신 §3).

자체점검: python3 api_hr.py --selftest   (DB·네트워크 없음 — 봉투 모양·행 변환·열쇠표·마스킹·통로 단일화만)
"""
import datetime
import decimal
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # 저장소 server/ = 서버 /srv/erp/
from common import db  # noqa: E402  — DB 를 여는 유일한 자리 · 모든 조회는 tenant_id 로 거른다

SOURCE = "hr-db"          # 다른 미러는 'sheet-mirror'(정본=시트). hr 은 ⑤단계 뒤 서버가 정본이 되므로 이름을 나눈다.
MAX_ROWS = 20000          # 안전 상한 — 휴무 5,603행이 최대라 평상시엔 안 닿는다. 닿으면 truncated=true 로 알린다.
router = APIRouter(prefix="/api/hr")

# 현행 GAS 읽기 열쇠(db:...) → hr 표. label 은 사람이 읽는 이름(오류 문구·health 용).
#   emp/exitroster 는 같은 표(hr.employee)를 status 로 가른다 — '현재근무자'와 '퇴사자 명부'는 같은 사람의 상태 차이다.
#   ⚠️ exitroster 는 정본 문서 db 목록에 빠져 있으나 실제로 살아 있는 읽기 열쇠다. 빼면 퇴사자 명부가 통째로 사라진다.
#   limit = 열쇠별 기본 반환 상한(0 = MAX_ROWS = 사실상 전량. 화면이 전량을 받아 집계하므로 전량이 기본이다).
#   ★autolog 만 최신 120행 — 러너가 전송 타임아웃 때 '최신 120행·6분 창에 그 기록이 있는가'로 성패를
#     되판정하는데 서버에 이 읽기 열쇠가 없어 검증 요청이 갈 곳이 없었다. 라우트를 먼저 열어 두면
#     적재가 붙는 즉시 동작한다(적재 전에는 0행이 정상 — 헬스가 '고장'과 구분해 보여 준다).
#   vanish = 그 표에 vanished_at 칸이 있어 '살아 있는 행'(vanished_at IS NULL)만 기본 반환하는가(aws2 §0.1).
#     ★autolog 만 False — 자동화로그는 적재 범위 밖이라 스키마가 그 칸을 만들지 않는다.
DBS = {
    "emp":        {"table": "hr.employee",    "pk": "employee_id",   "where": "status <> '퇴사'",
                   "order": "dept_name_raw NULLS LAST, legacy_row",  "label": "현재근무자", "limit": 0, "vanish": True},
    "exitroster": {"table": "hr.employee",    "pk": "employee_id",   "where": "status = '퇴사'",
                   "order": "resign_date DESC NULLS LAST, legacy_row", "label": "퇴사자 명부", "limit": 0, "vanish": True},
    "exit":       {"table": "hr.resignation", "pk": "resignation_id", "where": "",
                   "order": "last_work_date DESC NULLS LAST, legacy_row", "label": "퇴사처리", "limit": 0, "vanish": True},
    "appl":       {"table": "hr.applicant",   "pk": "applicant_id",  "where": "",
                   "order": "applied_at DESC NULLS LAST, legacy_row", "label": "지원자", "limit": 0, "vanish": True},
    "hire":       {"table": "hr.job_posting", "pk": "posting_id",    "where": "",
                   "order": "start_date DESC NULLS LAST, legacy_row", "label": "채용공고", "limit": 0, "vanish": True},
    "eval":       {"table": "hr.evaluation",  "pk": "eval_id",       "where": "",
                   "order": "period_start DESC NULLS LAST, legacy_row", "label": "인사평가", "limit": 0, "vanish": True},
    "onbo":       {"table": "hr.onboarding_item", "pk": "item_id",   "where": "",
                   "order": "employee_name_raw, week_no NULLS LAST, legacy_row", "label": "입사·온보딩", "limit": 0,
                   "vanish": True},
    "blacklist":  {"table": "hr.hire_blacklist",  "pk": "blacklist_id", "where": "",
                   "order": "registered_at DESC NULLS LAST, legacy_row", "label": "채용블랙리스트", "limit": 0,
                   "vanish": True},
    "leave":      {"table": "hr.leave_entry", "pk": "leave_id",      "where": "",
                   "order": "work_date, person_name_raw", "label": "휴무", "limit": 0, "vanish": True},
    "autolog":    {"table": "hr.automation_log", "pk": "log_id",     "where": "",
                   "order": "occurred_at DESC, log_id DESC", "label": "자동화로그", "limit": 120, "vanish": False},
}
# 행 봉투에서 감추는 내부 칸 — data 원본이 없을 때 정규화 칸으로 행을 만들 때만 쓴다.
#   ★birth_date 는 여기서 감추고 _birth_date 로 옮겨 둔다 — 2층(_apply_birth)이 역할에 따라 파생·삭제한다.
#   ★vanished 3칸은 감춘다 — include_vanished 응답에서만 row_out 이 _vanished_at·_vanish_reason 으로 덧붙인다.
_HIDDEN = ("tenant_id", "data", "is_test", "created_at", "updated_at", "synced_at", "legacy_tab", "birth_date",
           "vanished_at", "vanish_reason", "vanished_run_id")
_LIVE_PRED = "vanished_at IS NULL"          # '살아 있는 행' 술어 — 조회·행수 집계가 같은 문자열을 쓴다(aws2 §0.1)

# ── 신원·권한 ──────────────────────────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
ENV_ADMIN_EMAILS = "HR_ADMIN_EMAILS"            # 쉼표 구분 · 기본 빈 목록 ⛔ 실값을 코드·주석·보고서에 두지 않는다
ENV_TRUST_ROLE_HEADER = "HR_TRUST_ROLE_HEADER"  # 기본 꺼짐 — 관문 두 줄이 실제 배포되고 1회 확인한 뒤에만 켠다
ENV_STATUS_MODE = "HR_HTTP_STATUS_MODE"         # 'http'(기본 · 오류에 실제 상태코드) · 'compat'(되돌리기 · 항상 200)
# 인사 화면 모듈 열람권 게이트(aws2 §0.4 · §B-5) — 값은 서버 api.env 에만 둔다.
ENV_GATE_MODE = "HR_GATE_MODE"                  # 'module'(기본 · 게이트 켬) · 'off'(되돌리기 · 재배포 불요)
ENV_AUTH_CHECK_URL = "HR_AUTH_CHECK_URL"        # 관문 내부 주소(erp_auth /auth/check · erp-auth.service 포트 8000 실측)
ENV_GATE_URI = "HR_GATE_URI"                    # 게이트가 대신 물어볼 화면 경로(modules.json chro-hub-index)
ENV_GATE_CACHE_SEC = "HR_GATE_CACHE_SEC"        # 게이트 판정 캐시 초
GATE_MODE_DEFAULT = "module"
AUTH_CHECK_URL_DEFAULT = "http://127.0.0.1:8000/auth/check"
GATE_URI_DEFAULT = "/chro/hub/index.html"
GATE_CACHE_SEC_DEFAULT = 60
GATE_TIMEOUT_SEC = 2                            # 관문 호출 시간 상한 — 넘으면 닫힘(gate-unavailable)
_GATE_CACHE_MAX = 1024                          # 캐시 항목 상한 — 넘치면 가장 오래된 것부터 버린다
_GATE_COOKIE = "erp_session"                    # 관문 세션 쿠키 이름(erp_auth COOKIE 와 같은 값 · 값은 읽되 기록하지 않는다)
_GATE_COOKIE_RE = re.compile(r"(?:^|;\s*)" + _GATE_COOKIE + r"=([^;]*)")
_GATE_CACHE = {}                                # {sha256(세션값): (만료 시각, 판정)} — 프로세스 안에서만
_GATE_DENY_STATUSES = (401, 403)                # 관문 /auth/check 의 거부 두 값(로그인 필요 · 모듈 불허) → deny
#   ⚠️ 이 숫자는 관문 응답을 '읽는' 자리다 — 이 API 가 바깥으로 '내보내는' 상태코드에는 여전히 401 을 쓰지 않는다.

# 오류 코드 고정 목록 — 러너·화면이 열쇠로 삼는 자리다(배포 준비물 4). 새 코드를 늘리면 여기에도 넣는다.
#   ⚠️ 자체점검이 이 목록 전체를 돌며 코드·문구에 허브 게이트 금지어가 없는지 본다 —
#      게이트는 message 가 아니라 error 코드 칸을 정규식으로 훑으므로(실측) 코드 이름 자체가 검사 대상이다.
#   ★gate-unavailable(503) = 열람 판정 장치(관문)가 응답하지 않아 닫힌 경우. 게이트 '거부'는 새 코드가 아니라
#     기존 scope-blocked(403 · deny_reason=gate-deny)를 재사용한다.
ERROR_CODES = ("bad-payload", "bad-param", "unknown-db", "scope-blocked", "bad-date",
               "db-unavailable", "db-error", "audit-unavailable", "gate-unavailable")
# 바깥으로 나가는 고정 문구 — 예외 원문을 잇지 않는다(표·칸 이름·값 조각·접속 대상·DSN 조각 노출 방지).
MSG_DB_UNAVAILABLE = "자료 저장소에 연결하지 못했습니다."
MSG_DB_ERROR = "자료를 읽는 중 오류가 발생했습니다."
MSG_GATE_UNAVAILABLE = "열람 판정 장치가 응답하지 않아 이 요청은 처리하지 않았습니다."
MSG_SCOPE_BLOCKED = "이 계정으로 열람할 수 있는 범위가 아닌 자료입니다."
MSG_VANISHED_ADMIN_ONLY = "요청 값 include_vanished 은(는) 관리자 열람에서만 쓸 수 있습니다."
_AUDIT_STR_MAX = 64                             # 조회 기록에 남기는 문자열 값의 일괄 상한(안전망)

# 뷰어가 못 여는 열쇠 — 한 곳에 모은다(최종 목록은 매니저 확인 대상).
#   근거 = 허브가 뷰어에게 숨기는 탭(채용·채널·온보딩·평가) + 관리자 전용 화면(퇴사자 명부·블랙리스트).
#   뷰어 허용 = 현재근무자·휴무.
#   ⚠️ autolog 는 지시서 제안 목록에 없던 신설 열쇠다. work 칸이 '지원자 실명 병기 의무'라 지원자(appl)를
#      막으면서 이 열쇠를 열어 두면 같은 실명이 뒷문으로 나간다 — 그래서 일단 막았다(실패 방향 안전).
#      ★러너가 뷰어 신원으로 되판정을 부르면 이 항목에 막힌다 → 남은 길은 러너 계정을 관리자 목록에
#        넣는 것뿐이다(열되 실명만 가리는 절충은 러너의 완전일치 대조를 깨서 못 쓴다 — 배포 준비물 5).
#        1단계에서는 되판정이 여전히 현행 GAS 로 가므로 막힌 채로 깨지는 것이 없다.
#   ★emp·leave 는 이 목록에 넣지 않는다(2026-09-11 aws2 §B-5 결정) — 넣으면 허브 열람권이 있는 정상 뷰어의
#      근무표·명부까지 죽는다. '인사 화면이 잠긴 계정의 직접 호출'은 모듈 열람권 게이트(_gate)가 막는다.
VIEWER_DENY_DBS = ("appl", "hire", "blacklist", "onbo", "eval", "exitroster", "exit", "autolog")
# 뷰어 응답에서 통째로 빼는 칸(1층 · aws2 §B-3) — 2층이 빼는 생년월일·나이 두 키에 더해 bday·생일·재직기간과
#   '생년'·'생일'·'재직' 낱말이 든 칸 전부. 관리자 응답은 그대로(재직기간 등은 관리자 화면이 쓴다).
#   ★'재직'은 정확 일치가 아니라 낱말 포함으로 잡는다 — 실데이터 헤더가 '재직기간' 그대로가 아니라
#     오염된 변형(예: 값이 섞여 든 헤더)으로 들어와도 걸러지도록(R3, 뷰어 응답 기준·관리자 무영향).
VIEWER_DROP_KEYS = ("생년월일", "나이", "bday", "생일", "재직기간")
_VIEWER_DROP_WORDS = ("생년", "생일", "재직")

# ── 마스킹 패턴 ────────────────────────────────────────────────────────────────────────────────
#   현행 GAS maskPiiForViewer_ 와 같은 판별 — 값의 '형식'만 본다(칸 이름이 뭐라 적혀 있든 걸린다).
#   주민번호 13자리(구분자 유무 · 성별코드 1~8) · 축약형 7자리(셀 전체 일치일 때만 — 자유텍스트 과탐 방지)
#   휴대폰 01[016789] 앵커 · 국가번호(+82) 붙은 형태
PII_RRN_RE = re.compile(r"(?<!\d)\d{6}[-.\s]?[1-8]\d{6}(?!\d)")
PII_RRN_PARTIAL_WHOLE_RE = re.compile(r"^\d{6}[-.\s]?[1-8]$")
PII_RRN_KEY_RE = re.compile(r"^\d{6}[-.\s]?[1-8]\d{6}$")
PII_PHONE_RE = re.compile(r"(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
PII_PHONE_INTL_RE = re.compile(r"(?<![\d+])\+?82[-.\s]?1[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
PII_PHONE_KEY_RE = re.compile(r"^01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}$")
PII_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+\.[\w.-]+")
MASK_RRN_TOKEN = "******-*******"     # 고정 토큰 — 앞 6자리(생년월일)도 남기지 않는다
MASK_PHONE_TOKEN = "***-****-****"
MASK_EMAIL_TOKEN = "***@***"
MASK_EMAIL = False                    # ⚠️ 이메일도 가릴지는 매니저 확인 항목 — 켜고 끄는 자리는 이 한 줄뿐(기본 = 현행 유지)
_PII_KEY_WORD = "주민"                # 칸 이름에 이 낱말이 들어가면 값과 무관하게 통째 제거(오염 헤더 방어)

# 생년 파생 — 주민번호 앞자리(YYMMDD-성별)에서 생년월일·만나이만. 성별코드 1~4 만 인정한다
#   (외국인등록 5~8 · 1800년대 9/0 은 판별 근거가 부족해 미지원 — 현행 GAS deriveAdminDob_ 와 같은 범위).
BIRTH_RRN_FULL_RE = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})[-.\s]?([1-4])\d{6}(?!\d)")
BIRTH_RRN_PARTIAL_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})[-.\s]?([1-4])$")
BIRTH_ISO_RE = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$")
KST = datetime.timezone(datetime.timedelta(hours=9))   # 서버 시간대가 UTC 여도 만나이가 어긋나지 않게 오프셋을 박는다

# 조회 기록 실패 누계 — 프로세스 안에서만 센다(값이 아니라 상태만 헬스에 노출한다).
_AUDIT = {"fail": 0, "last_error": ""}


class DbUnavailable(Exception):
    """DB 를 열지 못했다. 라우트가 오류 봉투로 바꿔 돌려준다 — 프레임워크 기본 오류 모양(ok 칸 없음)을 내보내지 않는다."""


def _log_exc(where, e):
    """예외 흔적은 서버 로그에만. ⛔ 종류(클래스 이름)만 남긴다 — 예외 본문에는 표·칸 이름, 값 조각,
    접속 대상, 잘못된 접속 문자열 조각이 섞인다(_audit_write 가 쓰는 방식과 같게 통일)."""
    try:
        print("[api_hr] %s: %s" % (where, type(e).__name__), file=sys.stderr)
    except Exception:
        pass


def _open():
    try:
        return db.connect(readonly=True)          # 읽기 전용으로 연다 — 이 프로세스가 hr 표를 못 건드리게 못을 박는다
    except db.Error as e:
        _log_exc("db.connect", e)
        raise DbUnavailable(type(e).__name__)     # ⛔ 예외 원문을 들고 다니지 않는다(응답 문구로 새는 통로가 된다)


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _admin_emails():
    """관리자 이메일 목록(환경변수 · 쉼표 구분 · 기본 빈 목록). 비어 있으면 아무도 이메일로는 관리자가 되지 않는다."""
    raw = os.environ.get(ENV_ADMIN_EMAILS) or ""
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def _trust_role_header():
    """역할 헤더를 믿을지. 기본 꺼짐 — 관문이 역할 헤더를 덮어쓰도록 설정이 실제 배포됐고, 클라이언트가 직접
    실어 보낸 역할 헤더가 상류에 도달하지 않음을 1회 확인한 뒤에만 켠다(그 전엔 위조 통로가 열려 있다)."""
    return _truthy(os.environ.get(ENV_TRUST_ROLE_HEADER))


def _user(request):
    """관문이 넘긴 로그인 이메일(X-Erp-User). 관문 설정이 항상 덮어쓰므로 클라이언트가 위조할 수 없다."""
    return (request.headers.get("x-erp-user") or "").strip().lower()


def _role(request):
    """관문이 넘겨 준 역할 헤더 원문(소문자·공백 정규화).
    ⚠️ 이것만으로 관리자를 판정하지 않는다 — 신뢰 플래그가 꺼져 있으면 통째로 무시한다(_identify 참고)."""
    return (request.headers.get("x-erp-role") or "").strip().lower()


def _identify(request):
    """신원 판별 — 관리자 = (역할 헤더가 admin 이고 신뢰 플래그 켜짐) OR (로그인 이메일이 관리자 목록에 있음).
    둘 다 아니면 뷰어. 목록이 비어 있고 플래그도 꺼져 있으면 전원이 뷰어 = 전원이 마스킹본을 받는다."""
    email = _user(request)
    trust = _trust_role_header()
    by_header = bool(trust and _role(request) == ROLE_ADMIN)
    by_email = bool(email and email in _admin_emails())
    return {"email": email, "role": ROLE_ADMIN if (by_header or by_email) else ROLE_VIEWER,
            "by_header": by_header, "by_email": by_email, "trust_header": trust}


def _client_ip(request):
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if fwd:
        return fwd[:_AUDIT_STR_MAX]
    host = getattr(getattr(request, "client", None), "host", None)
    return host[:_AUDIT_STR_MAX] if isinstance(host, str) else host


# ── 인사 화면 모듈 열람권 게이트 (aws2 §B-5 · erp_auth 무수정) ──────────────────────────────────
#   관문의 기존 /auth/check 를 화면 경로를 붙여 대신 부른다 — 관문 코드가 이미 갖고 있는 모듈 판정
#   (module_at → allowed · 자동 로그인 세션의 chro-* 차단)을 그대로 빌린다. nginx 가 proxy_pass 로 Cookie 헤더를
#   상류(8001)에 그대로 넘기므로 이 라우터가 읽을 수 있다(관문 location 이 같은 값을 쓴다).
def _gate_mode():
    return (os.environ.get(ENV_GATE_MODE) or GATE_MODE_DEFAULT).strip().lower()


def _gate_uri():
    return (os.environ.get(ENV_GATE_URI) or GATE_URI_DEFAULT).strip() or GATE_URI_DEFAULT


def _gate_cache_sec():
    n, bad = _parse_int(os.environ.get(ENV_GATE_CACHE_SEC), 0, 86400, GATE_CACHE_SEC_DEFAULT)
    return GATE_CACHE_SEC_DEFAULT if bad else n


def _gate_fetch(url, headers):
    """관문 호출 1회 → HTTP 상태코드(정수). 4xx·5xx 도 상태코드로 돌려주고, 연결·시간 초과 등은 예외로 올린다.
    ★자체점검이 이 함수만 바꿔 끼워 200/거부/예외 세 경우를 검사한다 — 호출부(_gate)에 urllib 을 직접 두지 않는다."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=GATE_TIMEOUT_SEC) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def _gate_cache_get(k, now):
    hit = _GATE_CACHE.get(k)
    if hit is None:
        return None
    if hit[0] <= now:
        _GATE_CACHE.pop(k, None)
        return None
    return hit[1]


def _gate_cache_put(k, verdict, now):
    ttl = _gate_cache_sec()
    if ttl <= 0:
        return
    while len(_GATE_CACHE) >= _GATE_CACHE_MAX:          # 가장 오래된 항목부터(삽입 순서 보존) 버린다
        try:
            _GATE_CACHE.pop(next(iter(_GATE_CACHE)))
        except StopIteration:
            break
    _GATE_CACHE[k] = (now + ttl, verdict)


def _gate(request):
    """→ 'ok' | 'deny' | 'unavailable'.
    1) HR_GATE_MODE=off 면 통과(되돌리기 손잡이).  2) 세션 쿠키 조각이 없으면 거부.
    3) 캐시(열쇠 = 세션값의 sha256 · TTL HR_GATE_CACHE_SEC) 적중이면 그 판정.
    4) 관문 GET — Cookie 원문 · X-Original-URI=<HR_GATE_URI> · X-Original-Method=GET · 2초.
       200 → ok / 거부 상태(4xx 중 관문이 쓰는 두 값) → deny / 그 외 상태·예외 → unavailable(캐시하지 않음).
    ⛔ 세션값은 해시로만 다루고 어디에도 남기지 않는다. 예외는 종류 이름만 서버 로그에."""
    if _gate_mode() == "off":
        return "ok"
    cookie = request.headers.get("cookie") or ""
    m = _GATE_COOKIE_RE.search(cookie)
    if not m or not m.group(1).strip():
        return "deny"
    k = hashlib.sha256(m.group(1).strip().encode("utf-8")).hexdigest()
    now = time.time()
    cached = _gate_cache_get(k, now)
    if cached is not None:
        return cached
    url = (os.environ.get(ENV_AUTH_CHECK_URL) or AUTH_CHECK_URL_DEFAULT).strip() or AUTH_CHECK_URL_DEFAULT
    headers = {"Cookie": cookie, "X-Original-URI": _gate_uri(), "X-Original-Method": "GET"}
    try:
        status = _gate_fetch(url, headers)
    except Exception as e:                        # 연결 거부·시간 초과·URL 오류 등 — 닫힘(실패 방향 안전)
        _log_exc("gate/fetch", e)
        return "unavailable"
    if status == 200:
        verdict = "ok"
    elif status in _GATE_DENY_STATUSES:           # 관문이 쓰는 두 거부값(로그인 필요 · 모듈 불허)
        verdict = "deny"
    else:
        return "unavailable"
    _gate_cache_put(k, verdict, now)
    return verdict


def jsonable(v):
    """DATE·TIME·TIMESTAMPTZ·NUMERIC 을 화면이 받던 문자열·숫자 모양으로. 지어내지 않고 표준 표기만 쓴다."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, datetime.datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    return v


# ── 0층 · 상시 층 (역할 무관 — 관리자 응답에도 걸린다) ──────────────────────────────────────────
#   현행 GAS 의 maskEmpRrnUnconditional_ 과 같은 자리다(2026-07-14 실노출 사고 뒤 추가된 층).
#   하는 일 = 주민번호 치환 + '주민' 계열·오염 헤더 칸 제거. ⛔ 연락처는 여기 없다(1층 = 뷰어 정책 소관).
def _baseline_text(s):
    """문자열 1개 — 주민번호만. 13자리(구분자 유무)는 자유 텍스트 안이라도, 축약형은 셀 전체 일치일 때만."""
    if not isinstance(s, str) or not s:
        return s
    if PII_RRN_PARTIAL_WHOLE_RE.match(s.strip()):
        return MASK_RRN_TOKEN
    return PII_RRN_RE.sub(MASK_RRN_TOKEN, s)


def _baseline_value(v):
    """행 전체 재귀 순회 — 정규화 칸 · 원본 레코드(data JSONB 통째) · 중첩 값이 전부 순회 대상이다."""
    if isinstance(v, str):
        return _baseline_text(v)
    if isinstance(v, list):
        return [_baseline_value(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k in v:
            if _is_pii_key(k):
                continue                       # '주민' 낱말 칸 · 값이 그대로 칸 이름이 된 오염 헤더 = 통째 제거
            out[k] = _baseline_value(v[k])
        return out
    return v


def _apply_baseline(rows):
    """역할과 무관하게 늘 도는 층. 제자리 치환 — 봉투의 results·data 가 같은 배열이라 한 번이면 된다.
    ★1층(뷰어 정책)이 그 위에 그대로 얹힌다. 두 층은 같은 값에 두 번 걸려도 결과가 같다(멱등).
    ★오염 헤더 칸을 버리기 전에 그 칸이 담고 있던 연락처만 정상 칸으로 옮긴다(현행 GAS 와 같은 구제 분기).
      역할과 무관하게 옮기고, 뷰어 응답이면 바로 위에 얹히는 1층이 그 값을 다시 가린다 — 즉 구제가
      뷰어 마스킹을 뚫지 않는다. 이미 값이 있는 연락처 칸은 덮지 않는다.
    ★구제한 값도 이 층을 그대로 통과시킨다 — 구제는 '버려질 칸에서 값만 꺼내는' 일이라, 꺼낸 값에
      주민번호가 섞여 있으면 구제가 0층을 우회하는 통로가 된다(전화번호 값이면 결과가 같아 회귀 0)."""
    for i in range(len(rows)):
        phone, _ = _contaminated_rescue(rows[i])
        out = _baseline_value(rows[i])
        if phone and isinstance(out, dict) and not out.get("연락처"):
            out["연락처"] = _baseline_text(phone)
        rows[i] = out
    return rows


# ── 1층 · 뷰어 정책 (뷰어 응답에만 — 0층에 더해 연락처·이메일) ──────────────────────────────────
def _mask_text(s):
    """문자열 1개. 축약형 주민번호는 셀 전체 일치일 때만 통째로 — 자유텍스트에서의 과탐을 막는 안전판이다."""
    if not isinstance(s, str) or not s:
        return s
    if PII_RRN_PARTIAL_WHOLE_RE.match(s.strip()):
        return MASK_RRN_TOKEN
    out = PII_RRN_RE.sub(MASK_RRN_TOKEN, s)
    out = PII_PHONE_INTL_RE.sub(MASK_PHONE_TOKEN, out)      # 국가번호형을 먼저 — 뒷자리만 남고 잘리는 일이 없게
    out = PII_PHONE_RE.sub(MASK_PHONE_TOKEN, out)
    if MASK_EMAIL:
        out = PII_EMAIL_RE.sub(MASK_EMAIL_TOKEN, out)
    return out


def _is_pii_key(k):
    """칸 이름 자체가 개인정보인 경우. '주민'이 들어가면 값과 무관하게 제거하고, 헤더 오염으로 값이 그대로
    칸 이름이 된 경우(주민번호·전화번호 셀 전체 일치)도 제거한다. 정상 칸 이름은 이 형식과 일치할 수 없다."""
    s = str(k if k is not None else "").strip()
    if not s:
        return False
    if _PII_KEY_WORD in s:
        return True
    return bool(PII_RRN_PARTIAL_WHOLE_RE.match(s) or PII_RRN_KEY_RE.match(s) or PII_PHONE_KEY_RE.match(s))


def _contaminated_rescue(row):
    """오염된 헤더 칸에서 그 행의 실제 값만 건져 낸다 → (연락처, 생년 원본).
    배경 = 시트 헤더행의 한 칸이 라벨 대신 실제 값(전화번호·주민번호)으로 덮이면 그 칸의 '이름'과 '값'이
      둘 다 개인정보가 되어 세 층이 칸을 이름째 버린다. 버리기만 하면 그 칸이 실제로 담고 있던 연락처·
      생년월일까지 관리자 응답에서 함께 사라진다 — 현행 GAS 가 2026-07-15 에 같은 회귀를 고친 자리이고,
      0층에 그 구제 분기가 없다는 것이 2026-09-06 감사 지적 3 이다.
    ⛔ 주민번호 원본은 이 함수를 통해서도 응답에 실리지 않는다 — 2층 생년 파생의 입력으로만 쓰이고,
      응답에 남는 것은 파생된 생년월일·나이뿐이다(원본 칸은 0층이 그대로 버린다).
    ★맨 위 칸만 본다 — 오염은 헤더행 승격에서만 생기므로 중첩 값에는 이 모양이 나타나지 않는다."""
    if not isinstance(row, dict):
        return None, None
    phone = birth = None
    for k in row:
        v = row[k]
        if not isinstance(v, str) or not v.strip():
            continue
        s = str(k if k is not None else "").strip()
        if phone is None and PII_PHONE_KEY_RE.match(s):
            phone = v.strip()
        elif birth is None and (PII_RRN_KEY_RE.match(s) or PII_RRN_PARTIAL_WHOLE_RE.match(s)):
            birth = v.strip()
    return phone, birth


def _is_viewer_drop_key(k):
    """뷰어 응답에서 통째로 빼는 칸인가 — VIEWER_DROP_KEYS 에 있거나 이름에 '생년'·'생일'·'재직' 낱말이 든 칸(aws2 §B-3).
    ★1층(뷰어 전용) 소관이다 — 관리자 응답은 그대로 두고, 2층(_apply_birth)의 두 pop 은 순서 계약대로 유지한다."""
    s = str(k if k is not None else "").strip()
    if not s:
        return False
    if s in VIEWER_DROP_KEYS:
        return True
    return any(w in s for w in _VIEWER_DROP_WORDS)


def _mask_value(v):
    """행 전체를 재귀 순회 — 정규화 칸 · 원본 레코드(data JSONB 통째) · 중첩 값이 전부 같은 순회 대상이다.
    적재가 떨어뜨리는 것은 칸 이름 3종뿐이라 메모·비고·면담 내용·평가 피드백 본문까지 훑어야 한다.
    ★생년·생일·재직기간 계열 칸은 이 층(뷰어 전용)에서 통째로 뺀다 — 중첩(data 원본)까지 같은 규칙."""
    if isinstance(v, str):
        return _mask_text(v)
    if isinstance(v, list):
        return [_mask_value(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k in v:
            if _is_pii_key(k) or _is_viewer_drop_key(k):
                continue                       # 통째 제거 — 마스킹한 이름으로 되살리지 않는다
            out[k] = _mask_value(v[k])
        return out
    return v


def _apply_mask(rows):
    """뷰어 응답의 제자리 마스킹. rows 는 봉투의 results·data 가 같이 가리키는 그 배열이다 —
    새 배열을 만들지 않고 원소만 바꿔 끼워 두 이름 모두에 한 번에 반영되게 한다."""
    for i in range(len(rows)):
        rows[i] = _mask_value(rows[i])
    return rows


# ── 2층 · 생년 파생 (관리자 응답에만) ───────────────────────────────────────────────────────────
def _today_kst():
    return datetime.datetime.now(datetime.timezone.utc).astimezone(KST).date()


def _derive_birth(v, today=None):
    """생년 원본 → (YYYY-MM-DD, 만나이) 또는 None. DATE·ISO 문자열·주민번호 앞자리(YYMMDD-성별) 셋 다 받는다.
    ⛔ 뒷자리(일련번호)는 애초에 적재하지 않으므로 이 함수를 지나 응답에 섞일 수 없다."""
    today = today or _today_kst()
    y = m = d = None
    if isinstance(v, datetime.date) and not isinstance(v, datetime.datetime):
        y, m, d = v.year, v.month, v.day
    elif isinstance(v, str) and v.strip():
        s = v.strip()
        mm = BIRTH_ISO_RE.match(s)
        if mm:
            y, m, d = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
        else:
            mm = BIRTH_RRN_PARTIAL_RE.match(s) or BIRTH_RRN_FULL_RE.search(s)
            if mm:
                century = 1900 if mm.group(4) in ("1", "2") else 2000
                y, m, d = century + int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
    if not y or not (1 <= m <= 12) or not (1 <= d <= 31):
        return None
    try:
        born = datetime.date(y, m, d)
    except ValueError:
        return None
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 0 or age > 120:
        return None
    return ("%04d-%02d-%02d" % (y, m, d), age)


def _apply_birth(rows, role):
    """관리자에게만 생년월일·나이를 파생해 싣고, 뷰어에게서는 두 키를 제거한다.
    _birth_date(정규화 칸에서 옮겨 둔 원본)는 역할과 무관하게 항상 응답에서 뺀다."""
    today = _today_kst()
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw = r.pop("_birth_date", None)
        if role == ROLE_ADMIN:
            # 맨 마지막이 오염 헤더 구제 — 정규화 칸도 '생년월일'·'생일' 칸도 없고 그 행의 생년이
            #   오염된 칸에만 남아 있는 경우다(0층이 그 칸을 버리기 전인 지금이 유일한 기회다).
            got = (_derive_birth(raw, today) or _derive_birth(r.get("생년월일"), today)
                   or _derive_birth(r.get("생일"), today)
                   or _derive_birth(_contaminated_rescue(r)[1], today))
            if got:
                r["생년월일"], r["나이"] = got[0], got[1]
        else:
            r.pop("생년월일", None)
            r.pop("나이", None)
    return rows


def row_out(r, key, pk, include_vanished=False):
    """행 1개 → 화면이 받던 모양.
    data(시트 원본 레코드)가 있으면 그것을 그대로 준다 — 한글 칸 이름을 여기서 지어내지 않기 위한 선택이다.
    ⑤단계(GAS 끄기) 뒤 data 를 지우면 정규화 칸으로 자동 전환된다(그때 화면 어댑터를 ③단계에서 이미 바꿔 둔다).
    ★include_vanished 응답(관리자 전용)에서만 _vanished_at(ISO)·_vanish_reason 을 덧붙인다 — 그 외엔 싣지 않는다."""
    keys = list(r.keys())
    src = r["data"] if "data" in keys else None
    if isinstance(src, str):                      # 드라이버 설정에 따라 문자열로 올 수 있다
        try:
            src = json.loads(src)
        except (TypeError, ValueError):
            src = None
    d = dict(src) if isinstance(src, dict) else {k: jsonable(r[k]) for k in keys if k not in _HIDDEN}
    d["_id"] = r[pk] if pk in keys else None
    d["_sheet_row"] = r["legacy_row"] if "legacy_row" in keys else None   # 화면·사진 파일명·과거 로그가 쓰는 rNN
    d["_db"] = key
    d["_source"] = SOURCE
    if "birth_date" in keys:                      # 2층이 소비하고 지운다 — 어느 역할의 응답에도 이 키는 남지 않는다
        d["_birth_date"] = jsonable(r["birth_date"])
    if include_vanished and "vanished_at" in keys:
        d["_vanished_at"] = jsonable(r["vanished_at"])
        d["_vanish_reason"] = r["vanish_reason"] if "vanish_reason" in keys else None
    return d


def envelope(key, rows, total, truncated=False, role=ROLE_VIEWER, masked=True, as_of=None, as_of_run_id=None):
    """{ok, data} = ERP 표준 봉투(회신 §1-4) + results = 현행 화면 extractResults 호환. 같은 배열 하나를 두 이름으로.
    ★role 은 항상 싣는다 — 허브 로그인 게이트가 역할 칸이 없으면 그 자체를 인증 실패로 처리하고(index.html 5580행),
      블랙리스트 적재·생년월일 표시가 역할 값 admin 에 걸려 있다.
    ★masked 는 '1층(뷰어 정책)이 걸렸는가'를 뜻한다 — 0층은 역할과 무관하게 늘 걸리므로 masked=false 가
      '아무것도 안 가렸다'는 뜻이 아니다. 조회 기록에 남기는 값과 같은 값이다(사후 대조용).
    ★as_of·as_of_run_id 는 항상 싣는다(없으면 null) — 마지막 성공 apply run 의 finished_at·run_id(aws2 §0.3 · 결함 5)."""
    return {"ok": True, "db": key, "count": len(rows), "total": total,
            "results": rows, "data": rows, "truncated": truncated,
            "role": role, "masked": masked, "as_of": as_of, "as_of_run_id": as_of_run_id, "_source": SOURCE}


def error_envelope(code, message, key=None, role=ROLE_VIEWER, masked=True):
    """오류도 같은 모양으로 — 성공 여부·오류 코드·사람이 읽는 문구·출처를 항상 갖는다.
    ⚠️ error 코드와 message 둘 다 '권한'·'비밀번호'·unauthorized 낱말을 쓰지 않는다 — 허브 게이트가
      정규식으로 훑는 칸은 message 가 아니라 error 코드 칸이다(실측). 자체점검이 ERROR_CODES 전체를 검사한다.
    ⛔ message 에 예외 원문을 잇지 않는다 — 고정 문장만 쓴다(MSG_DB_UNAVAILABLE·MSG_DB_ERROR)."""
    out = {"ok": False, "error": code, "message": message,
           "role": role, "masked": masked, "_source": SOURCE}
    if key:
        out["db"] = key
    return out


def _status(code):
    """오류 응답의 상태코드 정책. 이 함수는 오류 경로에서만 불린다 — 성공 응답은 어느 모드든 200 이다.
    ★기본 'http'(2026-09-06 감사 지적 8 반영) — 허브 조회 함수가 상태 200 이면 본문의 성공 여부를 안 읽고
      결과 배열만 꺼내므로(실측), 오류까지 200 으로 돌려주면 범위 차단·미지 열쇠·형식 오류·저장소 실패·
      기록 실패가 화면에 '0건'으로 조용히 그려진다. 비200 이면 같은 함수가 오류로 잡아 화면에 오류 상태를
      세운다 — 허브를 고치지 않고 서버 쪽에서만 조용한 통과를 닫는 길이다.
    ★'compat' = 되돌리기 손잡이(환경변수 한 줄 · 재배포 불요). 알 수 없는 값은 안전한 쪽(오류를 드러내는
      쪽)으로 붙인다 — 오타 하나가 조용한 0건으로 되돌아가지 않게."""
    mode = (os.environ.get(ENV_STATUS_MODE) or "http").strip().lower()
    return 200 if mode == "compat" else code


def _valid_date(s):
    """기간 파라미터 형식 검사 — DB 에 닿기 전에 되돌리기 위한 것이다(영구 오류에 재시도가 붙지 않게)."""
    if s is None or s == "":
        return True
    try:
        datetime.datetime.strptime(str(s).strip(), "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


# ── 요청 파라미터 검사 — 라우트 서명이 아니라 여기서 한다 ────────────────────────────────────────
#   ⛔ 라우트 서명에 Query(ge=/le=) 제약을 걸지 않는다. 걸면 FastAPI 의 요청 검증이 라우트 본문보다 먼저 돌아
#      {"detail":[...]} 422 가 그대로 나간다 — ok 칸도 role 칸도 없는 프레임워크 기본 오류 모양이고,
#      봉투를 통째로 건너뛰므로 오류 코드도 역할 칸도 없어 허브도 러너도 이 응답을 못 읽는다.
#      전역 예외 핸들러는 진입 파일(app.py)을 고쳐야 해서 못 쓰므로 서명에서 닫는다(_valid_date 와 같은 자리).
_BOOL_TRUE = ("1", "true", "yes", "on", "y", "t")
_BOOL_FALSE = ("", "0", "false", "no", "off", "n", "f")


def _parse_int(v, lo, hi, default=0):
    """정수 파라미터 → (값, 오류사유 또는 None). 빈 값이면 기본값. 범위를 넘으면 조용히 자르지 않고 되돌린다."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return default, None
    if isinstance(v, bool):
        return default, "정수만 받습니다"
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return default, "정수만 받습니다"
    if n < lo or (hi is not None and n > hi):
        return default, "허용 범위는 %d~%s 입니다" % (lo, "제한없음" if hi is None else str(hi))
    return n, None


def _parse_bool(v, default=False):
    """참·거짓 파라미터 → (값, 오류사유 또는 None). 0/1 뿐 아니라 true/false 표기도 받는다
    (화면·러너가 흔히 보내는 표기다 — 여기서 막으면 정상 호출이 프레임워크 422 로 떨어진다)."""
    if v is None:
        return default, None
    if isinstance(v, bool):
        return v, None
    t = str(v).strip().lower()
    if t in _BOOL_TRUE:
        return True, None
    if t in _BOOL_FALSE:
        return default if t == "" else False, None
    return default, "0·1 또는 true·false 로 보내 주세요"


def _audit_clip(v):
    """조회 기록에 담기 직전 안전망 — 문자열 값 전체에 길이 상한을 일괄로 건다(중첩 포함).
    ⛔ 호출자가 보낸 문자열이 검사 전에 기록으로 새는 통로를 여기서 한 번 더 막는다."""
    if isinstance(v, str):
        return v[:_AUDIT_STR_MAX]
    if isinstance(v, dict):
        return {k: _audit_clip(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_audit_clip(x) for x in v]
    return v


_AS_OF_SQL = ("SELECT run_id, finished_at, batch_at FROM hr.migration_run"
              " WHERE tenant_id=%s AND mode='apply' AND status='ok' ORDER BY run_id DESC LIMIT 1")


def _as_of(conn):
    """마지막 성공 apply run → (as_of ISO 문자열 또는 None, run_id 또는 None, batch_at 또는 None). 봉투·health 가 같이 쓴다."""
    r = conn.execute(_AS_OF_SQL, (db.TENANT,)).fetchone()
    if r is None:
        return None, None, None
    return jsonable(r["finished_at"]), r["run_id"], jsonable(r["batch_at"])


def _fetch(key, limit, offset, include_test, date_from, date_to, include_vanished=False):
    spec = DBS[key]
    where, args = ["tenant_id = %s"], [db.TENANT]
    if spec["where"]:
        where.append(spec["where"])
    if not include_test:
        where.append("is_test = FALSE")
    if spec["vanish"] and not include_vanished:   # 살아 있는 행만 — 원천에서 사라진 행은 닫혀 있을 뿐 지워지지 않는다
        where.append(_LIVE_PRED)
    if key == "leave":                            # 휴무만 기간 좁히기 — 5,603행을 매번 다 보낼 이유가 없다
        if date_from:
            where.append("work_date >= %s")
            args.append(date_from)
        if date_to:
            where.append("work_date <= %s")
            args.append(date_to)
    w = " AND ".join(where)
    default_cap = spec.get("limit") or MAX_ROWS   # autolog 만 최신 120행 — 나머지는 전량(화면이 전량을 받아 집계)
    cap = min(limit, MAX_ROWS) if limit else default_cap
    conn = _open()
    try:                                          # 실패해도 연결을 버리지 않는다 — 예외는 위에서 봉투로 바뀐다
        with conn:
            total = conn.execute("SELECT COUNT(*) FROM %s WHERE %s" % (spec["table"], w), args).fetchone()[0]
            rs = conn.execute("SELECT * FROM %s WHERE %s ORDER BY %s LIMIT %%s OFFSET %%s"
                              % (spec["table"], w, spec["order"]), args + [cap, offset]).fetchall()
            as_of, as_of_run_id, _ = _as_of(conn)  # 같은 연결에서 — 행과 신선도 표시가 한 스냅샷이다
    finally:
        try:
            conn.close()
        except Exception:
            pass
    rows = [row_out(r, key, spec["pk"], include_vanished) for r in rs]
    # cap = '실제로 적용된 상한'. 요청값이 아니라 이 값을 봉투에 싣는다 — 요청값을 믿고 페이지를 넘기는
    #   호출자가 어긋난다(예: autolog 는 요청 0 이어도 실제로는 120행만 나간다).
    return rows, total, (total > offset + len(rows)), cap, as_of, as_of_run_id


def _audit_write(entry):
    """조회 기록 1건. 읽기 라우트는 읽기 전용 세션이라 같은 연결로는 못 쓴다 — 쓰기 연결을 짧게 열고 닫는다.
    ⛔ 행 내용·개인정보 값은 담지 않는다. 남기는 것은 '누가·언제·어느 열쇠를·마스킹 여부'까지다.
    ★안전망 — 담기 직전에 문자열 값 전체를 _AUDIT_STR_MAX 로 자른다(호출자가 보낸 원문이 새는 통로 차단)."""
    entry = _audit_clip(dict(entry or {}))
    conn = None
    try:
        conn = db.connect()
        with conn:
            conn.execute(
                "INSERT INTO hr.access_log (tenant_id, occurred_at, user_email, role, db_key, route,"
                " response_status, row_count, masked, params, deny_reason, client_ip)"
                " VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s, CAST(%s AS jsonb), %s, %s)",
                (db.TENANT, entry.get("email") or None, entry.get("role"), entry.get("db_key") or None,
                 entry.get("route"), entry.get("response_status"), entry.get("row_count"),
                 entry.get("masked"), json.dumps(entry.get("params") or {}, ensure_ascii=False),
                 entry.get("deny_reason") or None, entry.get("client_ip")))
        return True
    except Exception as e:                        # ⛔ 예외 본문에 값이 섞일 수 있어 종류(클래스 이름)만 남긴다
        _AUDIT["fail"] += 1
        _AUDIT["last_error"] = type(e).__name__
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _serve(request, key, route, limit=0, offset=0, include_test=False,
           date_from=None, date_to=None, reject=None, include_vanished=False):
    """두 읽기 라우트가 지나는 단 하나의 통로.
    신원 판별 → 본문 거절 → 모듈 열람권 게이트 → 열쇠 검사 → 파라미터 검사 → 조회 → 마스킹(2층→0층→1층) → 조회 기록 → 봉투 조립.
    ★게이트(_gate)는 열쇠 검사보다 앞이다 — 인사 화면이 잠긴 계정에는 어느 열쇠가 있는지조차 알려 주지 않는다.
      관리자(by_email)도 지난다(목록에 있어도 화면 열람권이 없으면 API 도 없다 — 실패 방향 안전).
    ★limit·offset·include_test 는 문자열로 받아 여기서 정수·참거짓으로 바꾼다 — 라우트 서명에 제약을 걸면
      FastAPI 요청 검증이 먼저 돌아 ok·role 칸 없는 422 가 봉투를 건너뛰고 그대로 나간다.
    ★앱 전역 미들웨어를 쓰지 않는 이유: 그건 공용 진입 파일(app.py)을 고쳐야 하는데 그 파일은
      '도메인별 파일만 손대고 진입 파일은 건드리지 않는다'는 규약이 있어 레인 충돌이 난다.
      통로를 하나로 좁히면 규약을 지키면서도 라우트가 늘 때 기록이 빠지기 어렵다(자체점검이 그걸 검사한다)."""
    ident = _identify(request)
    role = ident["role"]
    masked = (role != ROLE_ADMIN)                 # = '1층(뷰어 정책)을 태우는가'. 0층은 역할과 무관하게 늘 돈다.
    # 파라미터 검사 — 라우트 서명이 아니라 여기서 한다(프레임워크 422 를 내보내지 않기 위해서다).
    lim, bad_lim = _parse_int(limit, 0, MAX_ROWS)
    off, bad_off = _parse_int(offset, 0, None)
    inc, bad_inc = _parse_bool(include_test)
    inc_van, bad_van = _parse_bool(include_vanished)
    bad_param = (("limit", bad_lim) if bad_lim else
                 ("offset", bad_off) if bad_off else
                 ("include_test", bad_inc) if bad_inc else
                 ("include_vanished", bad_van) if bad_van else None)
    date_ok = _valid_date(date_from) and _valid_date(date_to)
    # ⛔ 조회 기록에는 '검증을 통과한 값'만 담는다 — 미지 열쇠·형식 오류 값이 검사 전에 원장으로 새지 않게.
    params = {"limit": lim if not bad_lim else "invalid", "offset": off if not bad_off else "invalid",
              "include_test": inc if not bad_inc else "invalid",
              "include_vanished": inc_van if not bad_van else "invalid",
              "from": (date_from if date_ok else "invalid"), "to": (date_to if date_ok else "invalid")}
    rec = {"email": ident["email"], "role": role,
           "db_key": (key if key in DBS else "unknown"),   # DBS 에 있는 열쇠일 때만 그 값을 싣는다
           "route": route, "masked": masked, "params": params, "client_ip": _client_ip(request)}

    def deny(code, message, http_code, reason):
        rec.update({"response_status": code, "row_count": 0, "deny_reason": reason})
        _audit_write(rec)                         # 거부는 원문이 안 나가므로 기록 실패로 막지 않는다
        return JSONResponse(error_envelope(code, message, key if key in DBS else None, role, masked),
                            status_code=_status(http_code))

    if reject:                                    # 라우트가 본문조차 못 읽은 경우 — DB 에 닿기 전에 되돌린다
        return deny(reject[0], reject[1], 400, reject[0])
    gate = _gate(request)                         # 인사 화면 모듈 열람권 — 관문 /auth/check 를 화면 경로로 대신 묻는다
    if gate == "deny":
        # ⚠️ 문구에 '권한'·'비밀번호'·unauthorized 를 쓰지 않는다 — 허브 게이트가 그 낱말을 훑어 세션을 지운다.
        return deny("scope-blocked", MSG_SCOPE_BLOCKED, 403, "gate-deny")
    if gate != "ok":                              # 판정 장치가 응답하지 않음 — 닫힘(원문이 나가는 쪽으로 열지 않는다)
        return deny("gate-unavailable", MSG_GATE_UNAVAILABLE, 503, "gate-unavailable")
    if key not in DBS:
        return deny("unknown-db",
                    "알 수 없는 db 열쇠입니다: %s (가능: %s)" % (str(key)[:40], ", ".join(sorted(DBS))),
                    404, "unknown-db")
    if role == ROLE_VIEWER and key in VIEWER_DENY_DBS:
        # ★판정은 역할로 한다 — masked 로 판정하면 마스킹 정책 변경이 열람 범위 변경으로 새어 나간다.
        # ⚠️ 문구에 '권한'·'비밀번호'·unauthorized 를 쓰지 않는다 — 허브 게이트가 그 낱말을 훑어 세션을 지운다.
        return deny("scope-blocked", "이 계정으로 열람할 수 있는 범위가 아닌 자료입니다: %s" % DBS[key]["label"],
                    403, "viewer-deny")
    if bad_param:
        return deny("bad-param", "요청 값 %s 이(가) 올바르지 않습니다 — %s." % bad_param, 400, "bad-param")
    if inc_van and role == ROLE_VIEWER:           # 닫힌 행(퇴사자 등 역사)은 관리자 열람에서만
        return deny("bad-param", MSG_VANISHED_ADMIN_ONLY, 400, "bad-param")
    if not date_ok:
        return deny("bad-date", "기간은 YYYY-MM-DD 형식으로 보내 주세요.", 400, "bad-date")

    try:
        rows, total, truncated, cap, as_of, as_of_run_id = _fetch(key, lim, off, inc, date_from, date_to, inc_van)
    except DbUnavailable as e:
        _log_exc("fetch/open %s" % key, e)
        rec.update({"response_status": "db-unavailable", "row_count": 0, "deny_reason": "db-unavailable"})
        _audit_write(rec)
        return JSONResponse(error_envelope("db-unavailable", MSG_DB_UNAVAILABLE, key, role, masked),
                            status_code=_status(503))
    except db.Error as e:                         # ⛔ 예외 원문을 본문에 싣지 않는다 — 서버 로그에만
        _log_exc("fetch %s" % key, e)
        rec.update({"response_status": "db-error", "row_count": 0, "deny_reason": "db-error"})
        _audit_write(rec)
        return JSONResponse(error_envelope("db-error", MSG_DB_ERROR, key, role, masked),
                            status_code=_status(503))

    _apply_birth(rows, role)                      # 2층 — 관리자에게만 파생, 뷰어에게선 두 키 제거(0층보다 먼저)
    _apply_baseline(rows)                         # 0층 — 역할 무관 상시(주민번호·'주민' 계열 칸·오염 헤더)
    if masked:
        _apply_mask(rows)                         # 1층 — 뷰어 정책(연락처·이메일). 0층 위에 그대로 얹힌다.

    rec.update({"response_status": "ok", "row_count": len(rows), "deny_reason": None})
    logged = _audit_write(rec)
    if not logged and not masked:
        # 실패 정책(비대칭) — 원문이 나가는 경로만 닫는다. 뷰어 마스킹본은 기록에 실패해도 통과시킨다.
        return JSONResponse(error_envelope("audit-unavailable",
                                           "조회 기록 장치가 응답하지 않아 이 요청은 처리하지 않았습니다.",
                                           key, role, masked), status_code=_status(503))
    out = envelope(key, rows, total, truncated, role, masked, as_of, as_of_run_id)
    out["limit"] = cap                            # 요청값이 아니라 '실제로 적용된 상한'
    out["offset"] = off
    return out


@router.get("/health")
def health():
    """표별 행수 + 테스트 표시 행수 + 마지막 적재 실행 + 권한·마스킹·기록이 실제로 켜져 있는지.
    ★값이 아니라 상태만 노출한다(참·거짓·건수) — 개인정보가 새지 않으면서 컷오버 전 1회 확인이 된다."""
    ident = {"admin_emails_configured": bool(_admin_emails()),   # ⛔ 이메일 실값은 싣지 않는다 — 등록 여부만
             "trust_role_header": _trust_role_header(),
             "status_mode": (os.environ.get(ENV_STATUS_MODE) or "http").strip().lower(),
             "viewer_denied_dbs": list(VIEWER_DENY_DBS),
             "mask_email": MASK_EMAIL,
             "gate_mode": _gate_mode(),            # 모듈 열람권 게이트 상태 — 관문 주소·쿠키 값은 싣지 않는다
             "gate_uri": _gate_uri()}
    try:
        conn = db.connect(readonly=True)
    except db.Error as e:                          # ⛔ 예외 원문을 본문에 싣지 않는다 — 서버 로그에만
        _log_exc("health/connect", e)
        return {"ok": False, "error": "db-unavailable", "message": MSG_DB_UNAVAILABLE,
                "identity": ident, "_source": SOURCE}
    try:
        with conn:
            rows, rows_test, rows_vanished = {}, {}, {}
            for key, spec in DBS.items():
                w = "tenant_id=%s" + ((" AND " + spec["where"]) if spec["where"] else "")
                if spec["vanish"]:                 # rows = 살아 있는 행수 · rows_vanished = 닫힌 행수(따로)
                    r = conn.execute("SELECT COUNT(*) FILTER (WHERE %s) AS n,"
                                     " COUNT(*) FILTER (WHERE is_test AND %s) AS t,"
                                     " COUNT(*) FILTER (WHERE vanished_at IS NOT NULL) AS v"
                                     " FROM %s WHERE %s" % (_LIVE_PRED, _LIVE_PRED, spec["table"], w),
                                     (db.TENANT,)).fetchone()
                    rows[key], rows_test[key], rows_vanished[key] = r["n"], r["t"], r["v"]
                else:                              # autolog — vanished 칸이 없다(적재 범위 밖) → 0 고정
                    r = conn.execute("SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE is_test) AS t"
                                     " FROM %s WHERE %s" % (spec["table"], w), (db.TENANT,)).fetchone()
                    rows[key], rows_test[key], rows_vanished[key] = r["n"], r["t"], 0
            run = conn.execute("SELECT run_id, mode, status, started_at, finished_at, note FROM hr.migration_run"
                               " WHERE tenant_id=%s ORDER BY run_id DESC LIMIT 1", (db.TENANT,)).fetchone()
            # 미완 run 은 '최신 1건'이 아니라 running 인 것 전부를 본다(결함 4) — 강제 종료로 남은 run 이
            #   그 뒤의 정상 run 에 가려지지 않게. 적재기의 다음 apply 가 aborted 로 닫을 때까지 여기 보인다.
            running_runs = [x["run_id"] for x in conn.execute(
                "SELECT run_id FROM hr.migration_run WHERE tenant_id=%s AND status='running' ORDER BY run_id",
                (db.TENANT,)).fetchall()]
            ok_at, ok_run_id, ok_batch_at = _as_of(conn)   # 봉투 as_of 와 같은 질의
            # 2층 파생 입력이 실제로 채워져 있는지(배포 준비물 6) — 0 에 가까우면 관리자 화면의
            # 생년월일·나이 칸이 컷오버 후 빈다. 값이 아니라 건수만 센다.
            bd = conn.execute("SELECT COUNT(*) AS n FROM hr.employee"
                              " WHERE tenant_id=%s AND birth_date IS NOT NULL", (db.TENANT,)).fetchone()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    last = None
    if run is not None:
        last = {"run_id": run["run_id"], "mode": run["mode"], "status": run["status"],
                "started_at": jsonable(run["started_at"]), "finished_at": jsonable(run["finished_at"]),
                "note": run["note"]}
    # 조회 기록은 표가 아직 없을 수 있어(스키마 미적용) 별도 연결로 짧게 본다 — 실패해도 헬스 전체를 죽이지 않는다.
    access = {"last_at": None, "write_failures": _AUDIT["fail"], "last_error": _AUDIT["last_error"],
              "table_ready": False}
    c2 = None
    try:
        c2 = db.connect(readonly=True)
        with c2:
            a = c2.execute("SELECT MAX(occurred_at) AS m FROM hr.access_log WHERE tenant_id=%s",
                           (db.TENANT,)).fetchone()
        access["last_at"] = jsonable(a["m"]) if a else None
        access["table_ready"] = True
    except Exception as e:
        access["last_error"] = access["last_error"] or type(e).__name__
    finally:
        # ⛔ 닫기는 반드시 finally 로 — 조회 기록 표가 아직 없는 상태(=컷오버 직전의 정상 상태)가
        #    바로 예외 경로라, 문맥 블록 뒤에서 닫으면 헬스를 부를 때마다 연결이 하나씩 버려진다.
        if c2 is not None:
            try:
                c2.close()
            except Exception:
                pass
    last_ok = None
    if ok_run_id is not None:
        last_ok = {"run_id": ok_run_id, "finished_at": ok_at, "batch_at": ok_batch_at}
    return {"ok": sum(rows.values()) > 0, "rows": rows, "rows_test": rows_test, "rows_vanished": rows_vanished,
            "last_migration": last, "last_ok_run": last_ok,
            "running_runs": running_runs, "stale_run": len(running_runs) > 0,
            "identity": ident, "access_log": access,
            # 2층 생년 파생의 입력이 실제로 있는가(배포 준비물 6) — 0 이면 관리자 화면 두 칸이 빈다.
            "birth_source": {"employee_birth_date_rows": bd["n"], "derivable": bd["n"] > 0},
            # 자동화로그는 적재가 아직 없어 0행이 정상이다 — '열쇠는 살아 있는데 적재가 아직'과 '고장'을 구분해 보인다.
            "autolog": {"rows": rows.get("autolog", 0), "loaded": rows.get("autolog", 0) > 0,
                        "default_limit": DBS["autolog"]["limit"]},
            "_source": SOURCE}


@router.post("/read")
async def read(request: Request):
    """현행 화면이 GAS 를 부르던 모양 그대로 — 본문 {"db":"appl"}. 주소 상수 한 줄만 바꾸면 화면이 그대로 산다.
    ⛔ 본문에 비밀 문자열이 실려 와도 읽지 않고 기록하지 않는다. 인증은 앞단 nginx auth_request 가 이미 했다.
    ★본문 정리 말고는 아무 일도 하지 않는다 — 판별·조회·마스킹·기록·봉투는 전부 공통 통로 안에서 한 순서로 일어난다."""
    bad = None
    key = ""
    inc_van = None
    try:
        payload = json.loads((await request.body()).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        key = str(payload.get("db") or "").strip()
        inc_van = payload.get("include_vanished")    # 관리자 전용 — 검사·거절은 공통 통로 안에서
    except Exception:
        bad = ("bad-payload", "요청 본문을 읽지 못했습니다. {\"db\":\"appl\"} 모양으로 보내 주세요.")
    return _serve(request, key, "POST /api/hr/read", reject=bad, include_vanished=inc_van)


@router.get("/{db_key}")
def read_get(
    request: Request,
    db_key: str,
    # ⛔ 여기에 int 형·하한상한 제약을 걸지 않는다 — 걸면 FastAPI 요청 검증이 라우트 본문보다 먼저 돌아
    #    ok 칸도 role 칸도 없는 {"detail":[...]} 422 가 그대로 나간다(?limit=abc · ?limit=99999 · ?offset=-1 ·
    #    ?include_test=true 넷 다 재현됨). 봉투를 건너뛰어 오류 코드도 역할 칸도 없으니 허브도 러너도
    #    그 응답을 못 읽는다. 전역 예외 핸들러는 진입 파일(app.py)을 고쳐야
    #    해서 못 쓴다 → 문자열로 받아 _serve 안에서 검사하고 어긋나면 bad-param 오류 봉투로 돌려준다.
    limit: Optional[str] = Query(None),           # 0·빈값 = 열쇠별 기본 상한(대개 전량 · autolog 만 최신 120행)
    offset: Optional[str] = Query(None),
    include_test: Optional[str] = Query(None),    # 테스트/더미 행 포함 여부(기본 제외 · 1/true 둘 다 받는다)
    date_from: Optional[str] = Query(None, alias="from"),   # 휴무 전용 — work_date 하한(YYYY-MM-DD)
    date_to: Optional[str] = Query(None, alias="to"),       # 휴무 전용 — work_date 상한
    include_vanished: Optional[str] = Query(None),  # 닫힌 행(원천에서 사라진 행) 포함 — 관리자 응답에서만
):
    return _serve(request, db_key, "GET /api/hr/{db}", limit=limit, offset=offset,
                  include_test=include_test, date_from=date_from, date_to=date_to,
                  include_vanished=include_vanished)


# ═══════════════════════════════════════════════════════════════════════════════════════════
#  쓰기 — 2단계(회신 §2 ②쓰기 서버화). 이번 커밋 범위 밖이라 뼈대만 적어 둔다.
#  TODO(2단계) 라우트 목록 — 현행 GAS 액션과 1:1 로 맞춘다
#    POST /api/hr/applicant            register-applicant / update-applicant   (등록 3게이트 유지)
#    POST /api/hr/applicant/stage      set-stage      ★stage 를 덮지 말고 hr.application_stage_history 에 쌓는다
#    POST /api/hr/applicant/photo      set-photo      ★파일명 r<row>.jpg 는 당분간 유지(러너 3종이 묶여 있다)
#    POST /api/hr/employee             hire-complete / fix-emp-field / resign
#    POST /api/hr/onboarding           add-onboarding / update-onboarding / onbo-checkin-save
#    POST /api/hr/evaluation           save-eval
#    POST /api/hr/leave                set-leave / set-leave-bulk  ★단건 UPSERT — full-sync 월 병합 규칙이 필요 없어진다
#    POST /api/hr/log                  log-add        ★actor_code 없는 쓰기는 거절(공통 셀프체크 6 을 서버가 강제)
#  2단계에서 반드시 지킬 것
#    · db.is_test_payload(payload) 를 그대로 재사용해 is_test 를 찍는다 — 새 판정 함수를 만들지 않는다(회신 §3).
#    · 쓴 사람 = request.headers["x-erp-user"](관문이 넘긴 로그인 이메일). 화면이 보낸 이름을 믿지 않는다.
#    · 쓰기 응답에 '갱신된 그 행'을 그대로 실어 준다 — 화면이 전체를 다시 읽지 않게(휴무 1칸 저장 후 5,603행 재조회 소멸).
#    · 트랜잭션 + UNIQUE 제약이 있으므로 재전송이 안전해진다 → 현행 '쓰기 재전송 절대 금지' 규칙의 폐기 근거.
#      ⚠️ 단 폐기는 이관 검증 통과 후. 병행 기간에는 종전 규칙을 그대로 지킨다.
#    · 쓰기 라우트도 읽기와 같이 통로를 하나로 좁히고 hr.access_log 와 같은 자리에 기록을 남긴다.
# ═══════════════════════════════════════════════════════════════════════════════════════════


def selftest():
    """DB·네트워크 없이 — 열쇠표 정합 · 봉투 모양 · 행 변환 · 마스킹 2층 · 권한 판별 · 통로 단일화만."""
    assert set(DBS) == {"emp", "exitroster", "exit", "appl", "hire", "eval", "onbo",
                        "blacklist", "leave", "autolog"}
    for k, s in DBS.items():
        assert s["table"].startswith("hr."), k
        assert s["pk"] and s["order"] and s["label"], k
        assert isinstance(s["limit"], int) and s["limit"] >= 0, k
    assert DBS["autolog"]["limit"] == 120, "러너 되판정 창(최신 120행)과 같아야 한다"
    # 봉투 — results 와 data 가 같은 배열을 가리켜야 화면 정규화 함수가 그대로 산다
    e = envelope("appl", [{"a": 1}], 1)
    assert e["ok"] is True and e["results"] == e["data"] and e["count"] == 1 and e["_source"] == SOURCE
    assert e["results"] is e["data"], "같은 배열 하나여야 한다(복사본이면 메모리만 두 배)"
    assert e["role"] and "masked" in e, "역할 칸은 항상 실려야 한다(허브 게이트가 없으면 인증 실패로 본다)"
    # 오류 봉투 — 성공 여부·코드·문구·출처를 항상 갖고, 게이트 금지어가 error·message 두 칸에 다 없어야 한다.
    #   ★허브 게이트가 실제로 훑는 칸은 message 가 아니라 error 코드 칸이다(index.html 5578행 실측) —
    #     그래서 정적 표본 몇 개가 아니라 ERROR_CODES 전체를 돌린다. 새 코드를 늘리면 여기서 먼저 걸린다.
    _sample_msgs = {
        "bad-payload": "요청 본문을 읽지 못했습니다.",
        "bad-param": "요청 값 limit 이(가) 올바르지 않습니다 — 정수만 받습니다.",
        "unknown-db": "알 수 없는 db 열쇠입니다: zz (가능: %s)" % ", ".join(sorted(DBS)),
        "scope-blocked": "이 계정으로 열람할 수 있는 범위가 아닌 자료입니다: 지원자",
        "bad-date": "기간은 YYYY-MM-DD 형식으로 보내 주세요.",
        "db-unavailable": MSG_DB_UNAVAILABLE,
        "db-error": MSG_DB_ERROR,
        "audit-unavailable": "조회 기록 장치가 응답하지 않아 이 요청은 처리하지 않았습니다.",
        "gate-unavailable": MSG_GATE_UNAVAILABLE,
    }
    assert set(_sample_msgs) == set(ERROR_CODES), "새 오류 코드는 ERROR_CODES 와 이 표에 같이 올린다"
    # 살아 있는 행 플래그 — autolog 만 예외(적재 범위 밖 · vanished 칸 없음)
    assert all("vanish" in s for s in DBS.values())
    assert set(k for k, s in DBS.items() if s["vanish"]) == set(DBS) - {"autolog"}
    assert all(c in _HIDDEN for c in ("vanished_at", "vanish_reason", "vanished_run_id"))
    # 봉투 — as_of·as_of_run_id 는 항상 실리고 기본은 null
    assert "as_of" in e and e["as_of"] is None and "as_of_run_id" in e and e["as_of_run_id"] is None
    assert envelope("emp", [], 0, as_of="2026-09-11 03:00:00", as_of_run_id=7)["as_of_run_id"] == 7
    assert "as_of" not in error_envelope("db-error", MSG_DB_ERROR, "emp"), "오류 봉투에는 싣지 않는다"
    _banned = re.compile(r"unauthorized|권한|비밀번호", re.I)
    for _code in ERROR_CODES:
        env = error_envelope(_code, _sample_msgs[_code], "appl")
        assert env["ok"] is False and env["error"] == _code and env["message"] and env["_source"] == SOURCE
        assert env["role"], "오류 봉투에도 역할 칸이 있어야 한다"
        assert not _banned.search(env["error"]), _code       # ★게이트가 훑는 칸은 여기다
        assert not _banned.search(env["message"]), _code
    # DB 계열 문구는 고정 문장 — 예외 원문(표·칸 이름·값 조각·접속 대상·DSN 조각)을 잇는 자리가 없어야 한다
    assert "%" not in MSG_DB_UNAVAILABLE and "%" not in MSG_DB_ERROR
    # 행 변환 — data 원본이 있으면 그대로, _sheet_row·_id 는 항상 덧붙는다
    r = {"applicant_id": 7, "legacy_row": 112, "tenant_id": "wellperion",
         "data": {"지원자명": "홍길동", "전형 단계": "서류"}, "applicant_name": "홍길동"}
    o = row_out(r, "appl", "applicant_id")
    assert o["지원자명"] == "홍길동" and o["_sheet_row"] == 112 and o["_id"] == 7 and o["_db"] == "appl"
    # data 가 문자열로 와도 같은 결과
    r2 = dict(r, data=json.dumps({"지원자명": "홍길동"}, ensure_ascii=False))
    assert row_out(r2, "appl", "applicant_id")["지원자명"] == "홍길동"
    # data 가 없으면 정규화 칸으로 — 내부 칸은 감춘다
    r3 = {"leave_id": 3, "legacy_row": 20, "tenant_id": "wellperion", "person_name_raw": "홍길동",
          "work_date": datetime.date(2026, 9, 5), "shift_start": datetime.time(9, 0),
          "is_test": False, "synced_at": datetime.datetime(2026, 9, 5, 12, 0)}
    o3 = row_out(r3, "leave", "leave_id")
    assert o3["work_date"] == "2026-09-05" and o3["shift_start"] == "09:00:00" and o3["_sheet_row"] == 20
    assert "tenant_id" not in o3 and "is_test" not in o3 and "synced_at" not in o3
    assert jsonable(decimal.Decimal("4.50")) == 4.5
    # 생년 칸은 정규화 출력에 그대로 안 나가고 _birth_date 로 옮겨진다(2층이 소비한다)
    r4 = {"employee_id": 1, "legacy_row": 5, "person_name_raw": "홍길동",
          "birth_date": datetime.date(1990, 1, 1)}
    o4 = row_out(r4, "emp", "employee_id")
    assert "birth_date" not in o4 and o4["_birth_date"] == "1990-01-01"
    # 닫힌 행 표시 — include_vanished 응답에서만 _vanished_at·_vanish_reason 이 덧붙고 원래 칸은 감춘다
    r5 = {"employee_id": 2, "legacy_row": 9, "person_name_raw": "홍길동",
          "vanished_at": datetime.datetime(2026, 9, 11, 3, 0), "vanish_reason": "absent-from-source",
          "vanished_run_id": 12}
    o5 = row_out(r5, "emp", "employee_id")
    assert "_vanished_at" not in o5 and "vanished_at" not in o5 and "vanished_run_id" not in o5
    o5v = row_out(r5, "emp", "employee_id", include_vanished=True)
    assert o5v["_vanished_at"] == "2026-09-11 03:00:00" and o5v["_vanish_reason"] == "absent-from-source"
    assert "vanished_at" not in o5v and "vanished_run_id" not in o5v

    # ── 0층 상시 층 — 역할과 무관하게 걸린다(관리자 응답에도). 연락처는 여기 소관이 아니다 ──────
    assert _baseline_text("900101-1234567") == MASK_RRN_TOKEN
    assert _baseline_text("9001011234567") == MASK_RRN_TOKEN
    assert _baseline_text("900101-1") == MASK_RRN_TOKEN                  # 축약형(셀 전체 일치)
    assert _baseline_text("메모: 본인확인 900101-1234567 완료").count(MASK_RRN_TOKEN) == 1
    assert _baseline_text("010-1234-5678") == "010-1234-5678", "연락처는 1층(뷰어 정책) 소관이다"
    assert _baseline_text("2026-09-05 근무") == "2026-09-05 근무", "날짜는 건드리지 않는다"
    _adm = [{"주민번호": "900101-1234567", "성명": "홍길동", "900101-1234567": "오염 헤더",
             "메모": "본인확인 900101-1234567 · 010-1234-5678", "data": {"주민 번호": "900101-1"}}]
    _apply_baseline(_adm)                                    # 관리자 응답에도 도는 층이다
    assert "주민번호" not in _adm[0], "'주민' 낱말 칸은 값과 무관하게 통째 제거(상시)"
    assert "900101-1234567" not in _adm[0], "값이 그대로 칸 이름이 된 오염 헤더도 제거(상시)"
    assert "주민 번호" not in _adm[0]["data"], "원본 레코드(data JSONB) 통째와 중첩까지 같은 순회 대상"
    assert _adm[0]["메모"].count(MASK_RRN_TOKEN) == 1 and "010-1234-5678" in _adm[0]["메모"]
    assert _adm[0]["성명"] == "홍길동"
    _apply_mask(_adm)                                        # 1층은 0층 위에 그대로 얹힌다(두 번 걸려도 같다)
    assert _adm[0]["메모"].count(MASK_RRN_TOKEN) == 1 and MASK_PHONE_TOKEN in _adm[0]["메모"]

    # ── 오염 헤더 구제 — 칸은 이름째 버리되 그 칸이 담고 있던 연락처·생년만 정상 칸으로 되돌린다.
    #    (현행 GAS maskEmpRrnUnconditional_ 의 구제 분기와 같은 동작 — 없으면 관리자 화면의 두 칸이 빈다)
    assert _contaminated_rescue({"010-1234-5678": "010-9876-5432"})[0] == "010-9876-5432"
    assert _contaminated_rescue({"900101-1234567": "900101-1234567"})[1] == "900101-1234567"
    assert _contaminated_rescue({"성명": "홍길동"}) == (None, None)
    assert _contaminated_rescue({"010-1234-5678": ""})[0] is None, "빈 칸은 구제 대상이 아니다"
    _con = [{"성명": "홍길동", "010-1234-5678": "010-9876-5432", "900101-1234567": "900101-1234567"}]
    _apply_birth(_con, ROLE_ADMIN)                           # 2층이 먼저 — 0층이 그 칸을 버리기 전이다
    _apply_baseline(_con)
    assert "010-1234-5678" not in _con[0] and "900101-1234567" not in _con[0], "오염 칸은 이름째 버린다"
    assert "900101-1234567" not in json.dumps(_con[0], ensure_ascii=False), "주민번호 원문은 남지 않는다"
    assert _con[0]["연락처"] == "010-9876-5432", "버리기 전에 연락처만 정상 칸으로 구제한다"
    assert _con[0]["생년월일"] == "1990-01-01" and isinstance(_con[0]["나이"], int)
    _con2 = [{"연락처": "010-1111-2222", "010-1234-5678": "010-9876-5432"}]
    _apply_baseline(_con2)
    assert _con2[0]["연락처"] == "010-1111-2222", "이미 값이 있는 연락처 칸은 덮지 않는다"
    _con3 = [{"010-1234-5678": "900101-1234567"}]                # 오염 칸에 전화가 아닌 값이 들어 있는 경우
    _apply_baseline(_con3)
    assert _con3[0]["연락처"] == MASK_RRN_TOKEN, "구제한 값도 0층을 통과한다(구제가 0층을 우회하지 않는다)"
    _conv = [{"성명": "홍길동", "010-1234-5678": "010-9876-5432", "900101-1234567": "900101-1234567"}]
    _apply_birth(_conv, ROLE_VIEWER)
    _apply_baseline(_conv)
    _apply_mask(_conv)
    assert _conv[0]["연락처"] == MASK_PHONE_TOKEN, "구제한 연락처도 뷰어에게는 1층이 가린다"
    assert "생년월일" not in _conv[0] and "나이" not in _conv[0], "뷰어에게는 생년 파생 자체가 없다"

    # ── 1층 뷰어 정책 — 값의 형식만 보고 자유 텍스트까지 훑는다 ──────────────────────────────
    assert _mask_text("900101-1234567") == MASK_RRN_TOKEN
    assert _mask_text("9001011234567") == MASK_RRN_TOKEN
    assert _mask_text("900101-1") == MASK_RRN_TOKEN                  # 축약형(셀 전체 일치)
    assert _mask_text("면담 메모: 본인확인 900101-1234567 완료").count(MASK_RRN_TOKEN) == 1
    assert _mask_text("010-1234-5678") == MASK_PHONE_TOKEN
    assert _mask_text("01012345678") == MASK_PHONE_TOKEN
    assert _mask_text("+82-10-1234-5678") == MASK_PHONE_TOKEN
    assert _mask_text("비고 연락처 010.1234.5678 로 연락").count(MASK_PHONE_TOKEN) == 1
    assert _mask_text("2026-09-05 근무") == "2026-09-05 근무", "날짜는 건드리지 않는다"
    assert _mask_text("a@b.com") == "a@b.com", "이메일은 현행과 같이 마스킹하지 않는다(기본값)"
    # 칸 이름 방어 — '주민'이 들어간 칸과, 값이 그대로 칸 이름이 된 오염 헤더를 통째로 뺀다
    assert _is_pii_key("주민번호") and _is_pii_key("주민등록번호") and _is_pii_key("900101-1234567")
    assert _is_pii_key("010-1234-5678") and not _is_pii_key("성명") and not _is_pii_key("연락처")
    nested = {"주민번호": "900101-1234567", "메모": {"본문": "연락 010-1234-5678", "목록": ["900101-1"]},
              "성명": "홍길동"}
    m = _mask_value(nested)
    assert "주민번호" not in m and m["성명"] == "홍길동"
    assert m["메모"]["본문"].endswith(MASK_PHONE_TOKEN) and m["메모"]["목록"][0] == MASK_RRN_TOKEN
    # 뷰어 응답 키 제거(aws2 §B-3) — bday·생일·재직기간과 '생년'·'생일' 낱말 칸은 1층이 통째로 뺀다(중첩 포함)
    assert _is_viewer_drop_key("bday") and _is_viewer_drop_key("생일") and _is_viewer_drop_key("재직기간")
    assert _is_viewer_drop_key("생년월일") and _is_viewer_drop_key("나이") and _is_viewer_drop_key("생년(주민)")
    assert not _is_viewer_drop_key("성명") and not _is_viewer_drop_key("연락처") and not _is_viewer_drop_key("")
    _vd = [{"bday": "01-01", "생일": "1월 1일", "재직기간": "3년", "성명": "홍길동",
            "data": {"생일": "1월 1일", "비고": "x"}}]
    _apply_birth(_vd, ROLE_VIEWER)
    _apply_baseline(_vd)
    _apply_mask(_vd)
    assert "bday" not in _vd[0] and "생일" not in _vd[0] and "재직기간" not in _vd[0], "뷰어 행에서 세 키 제거"
    assert _vd[0]["성명"] == "홍길동" and "생일" not in _vd[0]["data"] and _vd[0]["data"]["비고"] == "x"
    _ad = [{"bday": "01-01", "재직기간": "3년", "성명": "홍길동"}]
    _apply_birth(_ad, ROLE_ADMIN)
    _apply_baseline(_ad)                                     # 관리자 응답은 1층을 안 타므로 그대로
    assert _ad[0]["재직기간"] == "3년" and _ad[0]["bday"] == "01-01", "관리자 행은 재직기간 유지"
    # 제자리 치환 — 봉투의 results·data 가 같은 배열이므로 한 번으로 두 이름 모두에 반영돼야 한다
    rows = [{"메모": "010-1234-5678"}]
    env2 = envelope("emp", rows, 1)
    _apply_mask(rows)
    assert env2["results"][0]["메모"] == MASK_PHONE_TOKEN and env2["data"] is env2["results"]

    # ── 2층 생년 파생 — 관리자만, 기준일은 KST ──────────────────────────────────────────────
    t = datetime.date(2026, 9, 6)
    assert _derive_birth(datetime.date(1990, 1, 1), t) == ("1990-01-01", 36)
    assert _derive_birth("900101-1", t) == ("1990-01-01", 36)
    assert _derive_birth("900101-1234567", t) == ("1990-01-01", 36)
    assert _derive_birth("051231-3", t) == ("2005-12-31", 20)
    assert _derive_birth("2026-09-07", t) is None, "미래 생년은 만나이가 음수라 버린다"
    assert _derive_birth("6월 21일", t) is None and _derive_birth(None, t) is None
    adm = [{"_birth_date": "1990-01-01", "성명": "홍길동"}]
    _apply_birth(adm, ROLE_ADMIN)
    assert adm[0]["생년월일"] == "1990-01-01" and isinstance(adm[0]["나이"], int)
    assert "_birth_date" not in adm[0], "원본 생년 칸은 어느 역할의 응답에도 남지 않는다"
    vw = [{"_birth_date": "1990-01-01", "생년월일": "1990-01-01", "나이": 36, "성명": "홍길동"}]
    _apply_birth(vw, ROLE_VIEWER)
    assert "_birth_date" not in vw[0] and "생년월일" not in vw[0] and "나이" not in vw[0]

    # ── 권한 판별 — 목록이 비고 플래그가 꺼져 있으면 전원이 뷰어(실패 방향이 안전한 쪽) ──────
    class _Req(object):
        def __init__(self, h):
            self.headers = h
            self.client = None
    saved = (os.environ.get(ENV_ADMIN_EMAILS), os.environ.get(ENV_TRUST_ROLE_HEADER))
    try:
        os.environ.pop(ENV_ADMIN_EMAILS, None)
        os.environ.pop(ENV_TRUST_ROLE_HEADER, None)
        assert _identify(_Req({"x-erp-role": "admin",
                               "x-erp-user": "someone@example.invalid"}))["role"] == ROLE_VIEWER
        os.environ[ENV_TRUST_ROLE_HEADER] = "1"
        assert _identify(_Req({"x-erp-role": "admin"}))["role"] == ROLE_ADMIN
        assert _identify(_Req({"x-erp-role": "staff"}))["role"] == ROLE_VIEWER
        os.environ.pop(ENV_TRUST_ROLE_HEADER, None)
        os.environ[ENV_ADMIN_EMAILS] = " A@example.invalid , b@example.invalid "
        assert _identify(_Req({"x-erp-user": "a@EXAMPLE.invalid"}))["role"] == ROLE_ADMIN
        assert _identify(_Req({"x-erp-user": "c@example.invalid"}))["role"] == ROLE_VIEWER
        assert _identify(_Req({}))["role"] == ROLE_VIEWER
    finally:
        for name, val in zip((ENV_ADMIN_EMAILS, ENV_TRUST_ROLE_HEADER), saved):
            if val is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = val
    # 뷰어 거부 목록 — 허용은 현재근무자·휴무 둘뿐이다(emp·leave 는 게이트가 지킨다 · aws2 §B-5)
    assert set(VIEWER_DENY_DBS) <= set(DBS)
    assert set(DBS) - set(VIEWER_DENY_DBS) == {"emp", "leave"}
    assert _valid_date("2026-09-05") and _valid_date(None) and not _valid_date("2026/09/05x")

    # ── 모듈 열람권 게이트 — 관문 호출부(_gate_fetch)만 바꿔 끼워 200/거부/예외·캐시·off 를 본다 ──────
    _calls = []

    def _fake_fetch(status_or_exc):
        def f(url, headers):
            _calls.append((url, dict(headers)))
            if isinstance(status_or_exc, Exception):
                raise status_or_exc
            return status_or_exc
        return f
    _saved_gate = (os.environ.get(ENV_GATE_MODE), os.environ.get(ENV_GATE_URI),
                   os.environ.get(ENV_GATE_CACHE_SEC), os.environ.get(ENV_AUTH_CHECK_URL))
    _real_fetch = globals()["_gate_fetch"]
    _GATE_CACHE.clear()
    try:
        for _n in (ENV_GATE_MODE, ENV_GATE_URI, ENV_GATE_CACHE_SEC, ENV_AUTH_CHECK_URL):
            os.environ.pop(_n, None)
        _ck = {"cookie": "a=1; erp_session=tok-abc; b=2"}
        assert _gate(_Req({})) == "deny", "세션 쿠키 조각이 없으면 관문을 부르지 않고 거부"
        assert _gate(_Req({"cookie": "a=1; erp_session=; b=2"})) == "deny"
        assert not _calls
        globals()["_gate_fetch"] = _fake_fetch(200)
        assert _gate(_Req(_ck)) == "ok"
        assert _calls[-1][0] == AUTH_CHECK_URL_DEFAULT
        assert _calls[-1][1]["X-Original-URI"] == GATE_URI_DEFAULT and _calls[-1][1]["X-Original-Method"] == "GET"
        assert _calls[-1][1]["Cookie"] == _ck["cookie"], "Cookie 헤더는 원문 그대로 관문에 넘긴다"
        globals()["_gate_fetch"] = _fake_fetch(403)
        assert _gate(_Req(_ck)) == "ok" and len(_calls) == 1, "캐시 적중 — 관문을 다시 부르지 않는다"
        _GATE_CACHE.clear()
        assert _gate(_Req(_ck)) == "deny" and len(_calls) == 2
        assert _gate(_Req(_ck)) == "deny" and len(_calls) == 2, "거부도 캐시된다"
        _GATE_CACHE.clear()
        globals()["_gate_fetch"] = _fake_fetch(_GATE_DENY_STATUSES[0])
        assert _gate(_Req(_ck)) == "deny", "로그인 필요 응답도 거부"
        _GATE_CACHE.clear()
        globals()["_gate_fetch"] = _fake_fetch(500)
        assert _gate(_Req(_ck)) == "unavailable" and not _GATE_CACHE, "그 외 상태는 닫힘 · 캐시하지 않는다"
        globals()["_gate_fetch"] = _fake_fetch(OSError("connection refused"))
        assert _gate(_Req(_ck)) == "unavailable" and not _GATE_CACHE, "예외도 닫힘 · 캐시하지 않는다"
        # 캐시 열쇠는 세션값의 해시 — 원문이 캐시에 남지 않는다
        globals()["_gate_fetch"] = _fake_fetch(200)
        assert _gate(_Req(_ck)) == "ok"
        assert "tok-abc" not in json.dumps(list(_GATE_CACHE.keys()))
        # 캐시 상한 — 넘치면 가장 오래된 것부터 버린다
        for _i in range(_GATE_CACHE_MAX + 5):
            _gate(_Req({"cookie": "erp_session=t%d" % _i}))
        assert len(_GATE_CACHE) == _GATE_CACHE_MAX
        # TTL 0 이면 캐시하지 않는다
        _GATE_CACHE.clear()
        os.environ[ENV_GATE_CACHE_SEC] = "0"
        assert _gate(_Req(_ck)) == "ok" and not _GATE_CACHE
        os.environ[ENV_GATE_CACHE_SEC] = "abc"
        assert _gate_cache_sec() == GATE_CACHE_SEC_DEFAULT, "잘못된 값이면 기본값"
        os.environ.pop(ENV_GATE_CACHE_SEC, None)
        # 환경변수로 화면 경로·관문 주소를 바꾸면 그대로 실린다
        _GATE_CACHE.clear()
        os.environ[ENV_GATE_URI] = "/chro/hub/schedule.html"
        os.environ[ENV_AUTH_CHECK_URL] = "http://127.0.0.1:8000/auth/check?x=1"
        assert _gate(_Req(_ck)) == "ok" and _calls[-1][1]["X-Original-URI"] == "/chro/hub/schedule.html"
        assert _calls[-1][0].endswith("?x=1")
        # 되돌리기 손잡이 — off 면 쿠키가 없어도 관문을 부르지 않고 통과
        _ncalls = len(_calls)
        os.environ[ENV_GATE_MODE] = " OFF "
        assert _gate(_Req({})) == "ok" and len(_calls) == _ncalls
        os.environ[ENV_GATE_MODE] = "module"
        assert _gate(_Req({})) == "deny"
        os.environ[ENV_GATE_MODE] = "zzz"
        assert _gate(_Req({})) == "deny", "알 수 없는 값은 게이트를 켠 쪽(닫힘)으로 붙는다"
    finally:
        globals()["_gate_fetch"] = _real_fetch
        _GATE_CACHE.clear()
        for name, val in zip((ENV_GATE_MODE, ENV_GATE_URI, ENV_GATE_CACHE_SEC, ENV_AUTH_CHECK_URL), _saved_gate):
            if val is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = val
    # ── 오류가 프론트·러너의 '실제' 판정 기준에 걸리는가(2026-09-06 감사 지적 8) ────────────────
    #   두 소비자의 판정식을 그대로 옮겨 와, 표본 몇 개가 아니라 ERROR_CODES 전체를 돌린다.
    #   허브 = 조회 함수가 `if(!r.ok) throw` 다(index.html queryDB 실측) → 오류는 비200 이어야 잡힌다.
    #     ⚠️ 그중 401 만은 쓰면 안 된다 — 허브가 401 을 '비밀번호 오류'로 보고 세션을 지우고 로그인 화면으로
    #        튄다(같은 파일 게이트 실측). 즉 '잡히기만 하면 된다'가 아니라 401 을 피한 비200 이어야 한다.
    #   러너 = 종전 판정이 인증형 하나뿐이라(error 가 정확히 unauthorized 이거나 문구에 그 한글 낱말)
    #     이 봉투를 못 잡았다 — 그 두 낱말은 허브 게이트가 훑는 낱말과 같아 서버가 쓸 수 없다(요구가 배타적).
    #     그래서 러너에 _source 로 좁힌 봉투 검사를 한 줄 넣었고(hr-backend2.ps1 Test-HrApiError),
    #     그 판정식을 여기 옮겨 서버 응답이 실제로 걸리는지 본다. ★이 판정은 상태코드를 안 보므로
    #     curl 이 4xx·5xx 에도 종료코드 0 을 내는 사각과 무관하게 산다.
    _HTTP_BY_CODE = {"bad-payload": 400, "bad-param": 400, "bad-date": 400,
                     "unknown-db": 404, "scope-blocked": 403,
                     "db-unavailable": 503, "db-error": 503, "audit-unavailable": 503,
                     "gate-unavailable": 503}
    assert set(_HTTP_BY_CODE) == set(ERROR_CODES), "새 오류 코드는 이 상태코드 표에도 같이 올린다"

    def _hub_catches(status):
        return not (200 <= status < 300)          # 허브 queryDB: 200 대가 아니면 오류로 잡는다

    def _runner_catches(env):
        # 러너 Test-HrApiError: _source 가 이 API 의 것인 봉투에서 ok 가 참이 아니면 이상으로 본다
        return env.get("_source") == SOURCE and "ok" in env and env.get("ok") is not True

    # ── 상태코드 정책 — 기본은 오류를 드러내는 쪽. 이 기본값이 '조용한 0건'을 막는 장치다 ──────
    _saved_mode = os.environ.get(ENV_STATUS_MODE)
    try:
        os.environ.pop(ENV_STATUS_MODE, None)
        assert _status(404) == 404 and _status(403) == 403 and _status(503) == 503, \
            "기본값은 오류를 200 으로 덮지 않는다(덮으면 허브가 '0건'으로 조용히 그린다)"
        for _code, _http in sorted(_HTTP_BY_CODE.items()):
            _st = _status(_http)
            _env = error_envelope(_code, _sample_msgs[_code], "appl")
            assert _hub_catches(_st), "%s 가 허브 판정에 안 걸린다('0건'으로 조용히 그려진다)" % _code
            assert _st != 401, "%s: 401 은 쓰지 않는다 — 허브가 세션을 지우고 로그인 화면으로 튄다" % _code
            assert _runner_catches(_env), "%s 가 러너 판정에 안 걸린다(exit 0 = 정상으로 통과한다)" % _code
        # 기존 성공 응답의 모양은 그대로 — 어느 판정에도 걸리지 않아야 한다(회귀 0 의 뒷받침)
        assert not _hub_catches(200)
        assert not _runner_catches(envelope("emp", [], 0, role=ROLE_ADMIN, masked=False))
        os.environ[ENV_STATUS_MODE] = "compat"
        assert _status(404) == 200, "되돌리기 손잡이(compat)는 종전대로 항상 200"
        assert not _hub_catches(_status(404)), \
            "compat 은 되돌리기 손잡이 — 허브 판정이 다시 못 잡는다(그래서 기본값이 아니다)"
        assert _runner_catches(error_envelope("unknown-db", _sample_msgs["unknown-db"], "appl")), \
            "러너 판정은 상태코드를 안 보므로 compat 에서도 산다"
        os.environ[ENV_STATUS_MODE] = " HTTP "
        assert _status(404) == 404, "앞뒤 공백·대문자도 같은 값으로 읽는다"
        os.environ[ENV_STATUS_MODE] = "zzz"
        assert _status(404) == 404, "알 수 없는 값이면 안전한 쪽(오류를 드러내는 쪽)으로 붙는다"
    finally:
        if _saved_mode is None:
            os.environ.pop(ENV_STATUS_MODE, None)
        else:
            os.environ[ENV_STATUS_MODE] = _saved_mode

    # ── 요청 파라미터 — 통로 안에서 검사한다(프레임워크 422 를 내보내지 않기 위해서다) ──────────
    assert _parse_int(None, 0, MAX_ROWS) == (0, None) and _parse_int("", 0, MAX_ROWS) == (0, None)
    assert _parse_int("120", 0, MAX_ROWS) == (120, None)
    assert _parse_int("abc", 0, MAX_ROWS)[1], "정수가 아니면 오류 봉투로 되돌린다"
    assert _parse_int(str(MAX_ROWS + 1), 0, MAX_ROWS)[1], "상한 초과는 조용히 자르지 않는다"
    assert _parse_int("-1", 0, None)[1], "음수 offset 도 되돌린다"
    assert _parse_bool("true") == (True, None) and _parse_bool("1") == (True, None)
    assert _parse_bool("false") == (False, None) and _parse_bool(None) == (False, None)
    assert _parse_bool("abc")[1], "알 수 없는 표기를 조용히 거짓으로 두지 않는다"
    # 조회 기록 안전망 — 담기 직전에 문자열 값이 길이 상한으로 잘린다(중첩 포함)
    _clip = _audit_clip({"db_key": "x" * 500, "params": {"from": "y" * 500, "limit": 10}})
    assert len(_clip["db_key"]) == _AUDIT_STR_MAX and len(_clip["params"]["from"]) == _AUDIT_STR_MAX
    assert _clip["params"]["limit"] == 10, "숫자는 그대로 둔다"

    # ── 통로 단일화 — 라우트 본문은 공통 통로만 부른다(우회 라우트가 생기면 여기서 먼저 막힌다) ──
    code = open(os.path.abspath(__file__), encoding="utf-8").read().split('"""', 2)[2].split("def selftest(", 1)[0]
    for marker in ('@router.post("/read")', '@router.get("/{db_key}")'):
        body = code.split(marker, 1)[1].split("\n@router.", 1)[0].split("\n# ═", 1)[0]
        assert "_serve(" in body, marker + " 는 공통 통로를 지나야 한다"
        for bypass in ("_fetch(", "envelope(", "_apply_mask(", "_apply_baseline(", "_apply_birth(",
                       "_audit_write(", "_identify(", "_gate("):
            assert bypass not in body, marker + " 가 공통 통로를 우회한다: " + bypass
    # 라우트 서명에 프레임워크 요청 검증 제약이 없어야 한다 — 있으면 그 검증이 본문보다 먼저 돌아
    #   ok 칸도 role 칸도 없는 422 가 봉투를 건너뛰고 나간다.
    _getbody = code.split('@router.get("/{db_key}")', 1)[1].split("\n@router.", 1)[0].split("\n# ═", 1)[0]
    for _sig in ("ge=", "le=", "gt=", "lt=", "min_length=", "max_length=", "regex=", "pattern="):
        assert _sig not in _getbody, "라우트 서명에 요청 검증 제약을 걸지 않는다: " + _sig
    # 뷰어 거부 판정은 역할로 한다 — 마스킹 여부로 판정하면 마스킹 정책 변경이 열람 범위 변경으로 새어 나간다
    assert "role == ROLE_VIEWER and key in VIEWER_DENY_DBS" in code
    assert "masked and key in VIEWER_DENY_DBS" not in code
    # 마스킹 순서 = 2층 → 0층 → 1층. 0층은 역할 분기 밖(상시)이고 1층만 뷰어 분기 안이다.
    _sv = code.split("def _serve(", 1)[1]
    for _layer in ("_apply_birth(rows, role)", "_apply_baseline(rows)", "_apply_mask(rows)"):
        assert _layer in _sv, "공통 통로에서 마스킹 층이 빠졌다: " + _layer
    assert _sv.index("_apply_birth(rows, role)") < _sv.index("_apply_baseline(rows)") \
        < _sv.index("_apply_mask(rows)"), "0층을 먼저 태우면 2층 파생 입력이 지워진다"
    assert "if masked:\n        _apply_mask(rows)" in _sv, "1층만 뷰어 분기 안에 있다(0층은 상시)"
    # 모듈 열람권 게이트는 조회보다 앞이고 열쇠 검사보다도 앞이다(잠긴 계정에는 열쇠 목록조차 안 준다)
    assert "_gate(" in _sv and _sv.index("_gate(") < _sv.index("_fetch("), "게이트가 조회보다 앞이어야 한다"
    assert _sv.index("_gate(") < _sv.index("key not in DBS"), "게이트가 열쇠 검사보다 앞이어야 한다"
    assert '"gate-deny"' in _sv and '"gate-unavailable"' in _sv
    # 닫힌 행 포함은 관리자 열람에서만 — 뷰어 요청은 조회 전에 되돌린다
    assert "inc_van and role == ROLE_VIEWER" in _sv and _sv.index("inc_van and role == ROLE_VIEWER") < _sv.index("_fetch(")
    # 오염 헤더 구제는 두 층 안에만 있어야 한다 — 공통 통로가 따로 부르면 순서 계약이 두 곳으로 갈라진다
    assert "_contaminated_rescue(" not in _sv, "구제는 층 안에서만 한다(공통 통로에서 따로 부르지 않는다)"
    # 오류 상태코드로 401 을 쓰지 않는다 — 허브가 401 을 '비밀번호 오류'로 읽고 세션을 지운 뒤
    #   로그인 화면으로 튄다(index.html queryDB·게이트 실측). 오류는 드러내되 이 코드만은 피한다.
    assert "401" not in _sv, "이 통로에서 401 을 쓰면 허브가 세션을 지우고 로그인 화면으로 튄다"
    assert 'out["limit"] = cap' in _sv, "상한 칸에는 요청값이 아니라 실제 적용된 상한을 싣는다"
    # 라우터 안에 자체 비밀 문자열 검사가 없어야 한다(관문 위임 · 지시서 요구).
    # 머리말 docstring 은 현행 화면 호출 모양을 인용하느라 그 낱말을 쓰므로 그 뒤부터,
    # 그리고 이 점검 함수 자신(금지어 목록이 여기 있다)은 빼고 = 라우트 본문만 본다.
    # ⛔ 금지어 목록에 실제 비밀 조각을 적지 않는다 — 공개 저장소다. '비번을 다루는 모양'만 잡는다.
    for banned in ("adminPassword", "SESSION_PW", "password ==", 'payload.get("password")', "payload.get('password')"):
        assert banned not in code, "라우터가 비밀 문자열을 다루면 안 된다: " + banned
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
