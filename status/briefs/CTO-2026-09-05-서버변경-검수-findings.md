# 2026-09-05 서버 변경 검수 — 결함 목록

검수 대상 = 오늘 AWS 서버(15.164.151.105)에 올린 변경 8개 파일. 읽기 전용 검수(수정 안 함).
결함 22건 — 치명 4 · 높음 5 · 중간 7 · 낮음 6.

검증 방법: 코드 직독 + `save_photo`·`module_at` 을 실제 함수로 떼어 내 입력을 넣어 재현했다.
서버 실물(nginx 실행 설정·PostgreSQL 시퀀스 현재값·cron)은 이 PC 에서 확인 못 했다 — 그 부분은 '추정' 으로 적었다.

---

## 치명 (지금 데이터가 사라지거나 남이 서버에 파일을 쓴다)

### C1. 접수·습득물이 5분 뒤 통째로 지워진다
- 자리: `server/erp_api/sync_reception.py:73` ↔ `server/erp_api/api_reception.py:258, 305`
- 무엇이 잘못: 오늘 `/api/reception/submit`·`/api/reception/lost` 가 서버 DB 에만 적도록 바뀌었는데(시트는 동결),
  5분 cron 인 `sync_reception._replace()` 는 여전히 `DELETE FROM reception_items WHERE tenant_id=%s` 로 표를 통째로
  비우고 GAS 시트 응답으로 다시 채운다. 서버가 적은 행은 시트에 없으므로 다음 동기화에서 사라진다.
  `lost_found` 도 같다. `_replace` 의 '0건 보호' 는 시트가 137행을 그대로 돌려주므로 발동하지 않는다.
- 터지는 상황: 회원이 종합접수처 폼을 제출한다 → 텔레그램 알림은 간다 → 최대 5분 뒤 현황판에서 그 건이 없어진다.
  접수한 사람도, 부서도 그 건을 다시 찾을 수 없다.
- 최소 수리: `replace_board`·`replace_lost` 의 삭제 범위를 시트 출처 행으로 좁힌다 — 예: 두 표에 `origin` 칸을 두고
  `DELETE ... AND origin='sheet'` (서버가 적는 행은 `origin='server'`).

### C2. 로그인 없이 서버 아무 폴더에나 파일을 쓸 수 있다
- 자리: `server/erp_api/api_reception.py:328` (`subdir` 무검증) → `api_reception.py:116` (`os.path.join(UPLOAD_DIR, subdir, month)`)
- 무엇이 잘못: `/api/reception/photo` 는 `reception-public.nginx.conf:13` 에서 `auth_request` 없이 공개다.
  본문의 `subdir` 을 그대로 경로에 이어 붙이는데 `..` 을 거르지 않는다.
- 터지는 상황(재현함): `{"subdir":"../../www/hacked","photo":"<base64>","fileName":"x.html"}` →
  저장 경로가 `/srv/erp/uploads/../../www/hacked/202609/<sha>.html` 로 풀려 업로드 폴더 밖에 파일이 생긴다.
  `/srv/erp/www` 는 깃 체크아웃 트리라 서버 깃 워처와도 충돌한다.
- 최소 수리: `subdir` 를 화이트리스트로 못 박는다 — `subdir if subdir in ("reception","lost-found") else "reception"`.

### C3. 업로드 파일 확장자를 올리는 쪽이 정한다 → ERP 오리진 저장 XSS
- 자리: `server/erp_api/api_reception.py:112-113` (mime 표에 없으면 `os.path.splitext(file_name)[1]`) ↔ `reception-public.nginx.conf:25` (`/uploads/` 무인증 정적 서빙)
- 무엇이 잘못: `mimeType` 을 표에 없는 값으로 주면 확장자가 `fileName` 에서 그대로 온다. `/uploads/` 는 ERP 와 같은
  오리진(포트 80 default_server)에서 서빙되므로 `.html`·`.svg` 는 브라우저가 실행한다.
- 터지는 상황(재현함): 무인증 `/api/reception/photo` 또는 `/api/reception/submit` 에
  `mimeType:"application/octet-stream"`, `fileName:"x.html"`, 본문 = 스크립트 →
  응답으로 `/uploads/reception/202609/<sha>.html` URL 을 돌려받는다. 그 링크를 직원이 열면 스크립트가
  ERP 오리진에서 돈다. 세션 쿠키는 HttpOnly 라 훔치진 못해도, 같은 오리진 `fetch` 로 그 직원 권한의
  ERP 조회·쓰기를 전부 대신 할 수 있다.
- 최소 수리: 확장자를 mime 표 값으로만 정한다 — 표에 없으면 저장하지 않고 빈 문자열 반환(`fileName` 폴백 삭제).

### C4. 주소 앞에 슬래시 하나 더 붙이면 모든 모듈 권한 판정이 꺼진다
- 자리: `server/erp_auth/app.py:172` (`posixpath.normpath`)
- 무엇이 잘못: POSIX 규칙상 `normpath` 는 **선행 슬래시 두 개를 보존**한다(`//cpo/x.html` → `//cpo/x.html`).
  그래서 `_MODS[2]` 조회가 빗나가 `module_at()` 이 `None` 을 돌려주고, `check()` 는 로그인 여부만 본다.
  반면 nginx 는 `merge_slashes` 기본값이 on 이라 파일은 정상으로 내준다.
- 터지는 상황(재현함): 아무 로그인 계정으로 `//cpo/member/membership.html` 요청 → 권한 없는 계정도 회원 화면을 본다.
  modules.json 103개 모듈 전부에 통한다. 슬래시 3개(`///`)는 정상 정규화되므로 정확히 2개일 때만 뚫린다.
- 최소 수리: `path = "/" + posixpath.normpath(...).lstrip("/")` 로 선행 슬래시를 1개로 강제한다.

---

## 높음

### H1. 접수번호 시퀀스를 seed 하는 코드가 저장소에 없다 (추정)
- 자리: `server/common/schema.sql:189-192` (`CREATE SEQUENCE IF NOT EXISTS reception_seq;`)
- 무엇이 잘못: 주석과 `api_reception.py:8-11` 은 "배포 시 1회 `setval` 로 GAS ScriptProperties 값을 이어받는다" 고
  적었지만, 저장소 어디에도 `setval` 호출이 없다(`deploy_db.sh`·`deploy_reception_public.sh` 모두 안 한다.
  `setval` 은 `migrate_sqlite_to_pg.py:73` 의 users.id 용 한 줄뿐).
- 터지는 상황: 시퀀스가 1부터 시작하면 첫 제출이 `RECEPTION-1` 을 발급한다. 그 값은 시트 미러에 이미 있으므로
  `reception_items` 기본키(tenant_id, reg_id) 충돌 → 500 → 폼의 재시도 큐가 5xx 로 계속 재시도한다.
  공개 접수가 통째로 막힌다. 서버에서 손으로 `setval` 을 이미 돌렸다면 해당 없음 — 서버 실물 확인 필요.
- 최소 수리: `deploy_reception_public.sh` 에
  `SELECT setval('reception_seq', (SELECT COALESCE(MAX(SUBSTRING(reg_id FROM 11)::int),0) FROM reception_items));` 한 줄을 넣는다.
- 해소(2026-09-05): 서버 실측으로 `reception_seq` last_value=160 확인 — 이미 GAS 값을 이어받은 상태. 발동 조건이 없으니 후속 조치 불요.

### H2. 폴더 index.html 모듈 6개는 권한 판정이 안 걸린다
- 자리: `server/erp_auth/app.py:172-174` (오늘 추가한 `.html` 보정에 `/index.html` 이 빠졌다)
- 무엇이 잘못: modules.json 에 `.../index.html` 로 등록된 모듈이 6개다
  (`/home/index.html`, `/home/en/index.html`, `/coo/리셉션 업무/index.html`, `/coo/리셉션 업무/라커관리/index.html`,
  `/chro/recruiting/index.html`, `/chro/hub/index.html`). `/chro/hub/` 와 `/chro/hub` 둘 다 `module_at` 이 `None` 이다
  (재현함). nginx 는 `try_files $uri/index.html`(erp.nginx.conf:40)·`${uri}index.html`(:48)로 파일을 내준다.
- 터지는 상황: 권한 없는 직원이 `/chro/hub/` 로 인사 허브를 연다.
- 최소 수리: `module_at` 의 폴백에 `_MODS[2].get(path.rstrip("/") + "/index.html")` 를 한 항 더 붙인다.

### H3. 공개 접수에 제출 토큰 게이트가 사라졌다
- 자리: `server/erp_api/api_reception.py:211-267` ↔ 구 GAS `apps_script_reception.js:2894` (`_vSubmitGateOk_`)
- 무엇이 잘못: GAS 시절 `reg_submit` 은 숨김 토큰 `t` + 지문 기반 속도제한을 통과해야 했다. 서버판은 `t` 를 읽지도 않는다.
  화면(`reception_block.html:1046`)은 아직 `t: RECEPTION_SUBMIT_TOKEN` 을 보내고 있으나 서버가 버린다.
- 터지는 상황: 주소만 알면 누구나 접수를 만들고, 그때마다 핵심멤버방에 텔레그램이 울린다.
  방어는 nginx IP 당 분당 20회뿐이라 IP 를 바꾸면 그대로 뚫린다.
- 최소 수리: `submit` 첫머리에서 `payload.get("t")` 를 서버 env 값과 대조하고 불일치면 400.
- 수리: `submit()` 첫머리에서 `payload["t"]` 를 `RECEPTION_SUBMIT_TOKEN`(env `RECEPTION_SUBMIT_TOKEN`, 기본값 = 폼 상수와 동일)과 대조 — 불일치면 400 BAD_TOKEN.
- 실측: 토큰 없이 `POST /api/reception/submit` → `400 {"code":"BAD_TOKEN"}` (2026-09-05).
- 커밋: 이 커밋(server/erp_api/api_reception.py).

### H4. 같은 접수가 두 줄로 들어가고 텔레그램도 두 번 간다
- 자리: `server/erp_api/api_reception.py:247-267` (idem 키 없음) ↔ `reception_block.html:1060` (`rcqSend` 재시도 큐)
- 무엇이 잘못: 폼은 429·5xx·네트워크 오류에 같은 본문을 자동 재전송한다. 서버는 매 요청마다 새 `RECEPTION-N` 을 발급하고
  알림을 쏜다. `api_write.py` 가 쓰던 중복 가림(idem) 이 이 통로엔 없다.
- 터지는 상황: 응답이 늦어 타임아웃 난 제출 1건이 접수 2건 + 알림 2회가 된다.
- 최소 수리: 폼이 이미 만드는 큐 id 를 본문에 실어 보내고, `reception_items` 에 그 값 유니크 인덱스를 걸어 `ON CONFLICT DO NOTHING`.
- 수리: 스키마 변경 없이 처리 — `submit()` 이 같은 카테고리 최근 20건 중 연락처+내용+장소가 같고 90초 이내인 행이
  있으면 새로 적지 않고 그 `reg_id` 를 그대로 돌려준다(알림도 다시 안 보낸다). `_dup_recent()`.
- 실측: 같은 payload 로 2회 연속 POST → 둘 다 `RECEPTION-162` 반환, 원장엔 1행만 남음(2026-09-05).
- 커밋: 이 커밋(server/erp_api/api_reception.py).

### H5. `/api/todo/{id}` 는 GM 행 게이트를 안 지난다
- 자리: `server/erp_api/api_todo.py:135-143`
- 무엇이 잘못: 목록(`todo_list`)에만 `REPLACE(owner,' ','') NOT LIKE '%김남욱%'` 게이트가 있고, 단건 조회에는 없다.
- 터지는 상황: ERP 로그인 계정이 업무 id 를 알거나 찍으면 GM 개인 업무 행을 결재 정보까지 그대로 받는다(배326 보호 우회).
- 최소 수리: `todo_item` 쿼리에 같은 `NOT LIKE` 조건을 붙이고, 목록과 같은 `include_gm`·`gmkey` 를 받게 한다.
- 수리: `todo_item`에 목록과 같은 `include_gm`·`gmkey` 파라미터 + owner·creator NOT LIKE 게이트 추가.
- 실측: 담당자=나우열M·생성자=김남욱GM 인 실제 행(`TODO-20260526173229010`) — 게이트 적용 전 단건 조회 200,
  적용 후 `404`(목록에서도 빠짐, M6 실측과 동일 케이스).
- 커밋: 이 커밋(server/erp_api/api_todo.py).

---

## 중간

### M1. 구글 로그인 state 에 브라우저 결속이 없다 (로그인 CSRF)
- 자리: `server/erp_auth/app.py:480` (state = `{"n": next, "exp"}` 뿐)
- 무엇이 잘못: state 가 요청한 브라우저를 가리키는 값(난수 쿠키 등)을 안 담는다. 서명만 확인한다.
- 터지는 상황: 공격자가 자기 계정으로 흐름을 시작해 얻은 콜백 URL 을 직원에게 열게 하면, 그 직원 브라우저가
  공격자 계정 세션을 받는다. 이후 직원이 넣는 내용이 공격자 계정에 쌓인다.
- 최소 수리: `google_start` 에서 난수를 쿠키로 심고 state 에도 넣어 콜백에서 대조한다.

### M2. 오픈 리다이렉트 — `next=//도메인`
- 자리: `server/erp_auth/app.py:344`, `app.py:480`
- 무엇이 잘못: `next.startswith("/")` 만 본다. `//evil.example` 은 이 검사를 통과하고 브라우저는 외부 사이트로 간다.
- 터지는 상황: `http://…/auth/login?next=//가짜사이트` 링크로 로그인 직후 위장 페이지에 떨군다.
- 최소 수리: `next.startswith("/") and not next.startswith("//")` 로 조건을 좁힌다.

### M3. 가입 부서 검증이 화면 선택지보다 넓다
- 자리: `server/erp_auth/app.py:562` (`if dept not in PRESETS`)
- 무엇이 잘못: 화면 선택지는 `DEPTS` 6개인데 검증은 `PRESETS` 기준이다. `PRESETS` 엔 `전체`(그룹 10개 전부)와 `마케팅` 이 더 있다.
- 터지는 상황: 폼을 손으로 고쳐 `dept=전체` 로 신청하면 perms 에 그룹 전체가 박힌 채 승인 대기로 들어간다.
  GM 이 승인 화면에서 `전체` 뱃지를 못 보고 누르면 그 계정이 모든 모듈을 본다.
- 최소 수리: `if dept not in DEPTS` 로 바꾼다.

### M4. 채팅 로그가 무한히 자란다 + 매 조회마다 전량 스캔
- 자리: `server/erp_api/api_chat.py:105-112`(append), `:145-168`(unanswered)
- 무엇이 잘못: `/srv/erp/chat_log.jsonl` 에 회전이 없다(logrotate 설정도 저장소에 없다).
  `unanswered` 는 요청마다 파일 전체를 처음부터 읽는다.
- 터지는 상황: 공개 채팅이 쓰일수록 파일이 커지고, 아침 학습 회로 조회가 점점 느려진다. 디스크가 차면 로그는
  조용히 실패하지만(예외 삼킴) 원인이 안 보인다.
- 최소 수리: `/etc/logrotate.d/erp-chat` 을 `deploy_chat.sh` 에 넣는다(daily·rotate 14·copytruncate).
- 수리: logrotate 대신 앱 코드로 처리(welly_auto_runner._append_log 와 같은 방식) — `_log()` 가 20MB 넘으면 `.1`
  로 밀고 두 세대만 남긴다. `unanswered` 는 전량 스캔 대신 로그 꼬리 300KB 만 읽는다.
- 실측: 실 서버 로그에 신규 질문 남긴 뒤 `/api/chat/1_wellperion/unanswered?days=1` 조회 → 최신 행 정상 노출.
- 커밋: 이 커밋(server/erp_api/api_chat.py).

### M5. 채팅 질문 원문에 개인정보가 들어와도 그대로 남는다
- 자리: `server/erp_api/api_chat.py:14`(문서 "이름·전화 저장 안 함"), `:105-110`(질문 원문 그대로 기록)
- 무엇이 잘못: 저장하지 않는 건 별도 입력칸일 뿐, 질문 자유텍스트는 원문 그대로 남는다. 상담 문의는 대개
  "010-… 로 연락 주세요" 형태로 들어온다.
- 터지는 상황: 공개 채팅 로그에 회원 전화번호가 평문으로 쌓이고, 문서는 안 쌓인다고 적혀 있어 아무도 안 본다.
- 최소 수리: `_log` 에서 전화번호 정규식을 마스킹하고 문서 문구를 실제 동작에 맞춘다.
- 수리: `_mask_pii()` 로 저장 전 전화번호·이메일 마스킹 + 모듈 docstring 문구 정정.
- 실측: "상담은 010-1234-5678 로 연락 주세요" 질문 → 실 로그엔 "[전화번호] 로 연락 주세요" 로 저장됨(원문 미보존).
- 커밋: 이 커밋(server/erp_api/api_chat.py).

### M6. GM 행 게이트가 담당자 빈 행까지 같이 떨군다 · 생성자 칸은 안 본다
- 자리: `server/erp_api/api_todo.py:117`
- 무엇이 잘못: SQL 에서 `NULL NOT LIKE '%…%'` 는 참이 아니라 NULL 이라 그 행이 결과에서 빠진다.
  담당자가 비어 있는 업무는 GM 것이 아닌데도 목록에서 사라진다. 또 `todo_items.creator`(생성자) 칸은 검사하지 않는다.
- 터지는 상황: 담당자 미지정 업무가 화면에서 안 보인다. 반대로 담당자는 실무진인데 생성자가 GM 인 개인 행은 그대로 노출된다.
- 최소 수리: `COALESCE(REPLACE(owner,' ',''),'') NOT LIKE %s` 로 바꾸고, 같은 조건을 `creator` 에도 AND 로 건다.
- 수리: `todo_list` where 절 정확히 그대로 적용(COALESCE + creator AND).
- 실측: 담당자=나우열M·생성자=김남욱GM 인 `TODO-20260526173229010` — 수리 전 기본 목록(비GM 열쇠)에 노출,
  수리 후 목록·단건 모두에서 빠짐(2026-09-05, H5 실측과 동일 행).
- 커밋: 이 커밋(server/erp_api/api_todo.py).

### M7. 사진 저장 실패가 접수자에게 안 보인다
- 자리: `server/erp_api/api_reception.py:121-122`(예외를 빈 문자열로 삼킴), `:267`(`"photoWarning": ""` 고정)
- 무엇이 잘못: base64 가 깨졌거나 디스크가 차면 사진 없이 접수만 들어가고 응답은 정상이라고 말한다.
  응답 칸 이름은 `photoWarning` 인데 항상 빈 값이다.
- 터지는 상황: 시설 고장·컴플레인 접수에서 증빙 사진이 조용히 없어진다. 부서는 사진이 원래 없었다고 판단한다.
- 최소 수리: `cat["photo"]` 인데 `photo_url` 이 비면 `photoWarning` 에 사유를 채워 돌려준다.
- 수리: 사진 입력은 있었는데 `save_photo` 가 빈 문자열을 돌려주면 `photoWarning` 에 사유 채움(접수 자체는 200 유지).
- 실측: 깨진 base64 로 `POST submit` → `photoWarning:"사진 저장에 실패했습니다. 접수는 정상 처리되었습니다."`, 접수는 정상 등록.
- 커밋: 이 커밋(server/erp_api/api_reception.py).

---

## 낮음

### L1. 공개 통로가 `X-Erp-User` 헤더를 안 지운다
- 자리: `reception-public.nginx.conf:5,13` · `chat.nginx.conf:11` (`api.nginx.conf:10` 만 덮어쓴다)
- 지금은 소비자가 `api_write.py:183` 하나뿐이고 그 경로는 `/api/` 규칙을 지나므로 실피해 없다. 다만 앞으로 이 공개
  location 아래에 라우트가 하나라도 생기면 클라이언트가 보낸 이메일을 그대로 믿게 된다.
- 최소 수리: 두 파일에 `proxy_set_header X-Erp-User "";` 를 넣는다.
- 수리: `reception-public.nginx.conf`(submit·photo) · `chat.nginx.conf`(public POST · unanswered) 네 위치 전부에 추가.
- 실측: `nginx -t` 통과 · `systemctl reload nginx` 성공(두 배포 스크립트 각각 재실측 curl 정상 200/400/404).
- 커밋: 이 커밋(server/erp_api/reception-public.nginx.conf, chat.nginx.conf).

### L2. 점 폴더 주소는 `deny all` 대신 404 로 빠진다
- 자리: `server/erp_auth/erp.nginx.conf:44` 가 `:54` 의 `location ~ /\.` 보다 먼저 선언됐다
- nginx 는 정규식을 선언 순서로 본다. `/.git/` 처럼 슬래시로 끝나는 점 경로는 위 정규식이 먼저 잡아 404 가 된다
  (파일은 `/.git/config` 처럼 슬래시로 안 끝나므로 여전히 deny 된다 — 실노출은 없다).
- 최소 수리: `location ~ /\.` 를 `include` 위로 올린다.

### L3. 금지어 목록이 '보내는 말' 용이라 '받는 질문' 을 못 거른다
- 자리: `server/erp_api/api_chat.py:31` ← `scripts/diet_camp_agent.py:58` (`"원 드리"·"할인해"·"세금계산서"` 등)
- 이 목록은 AI 가 카톡으로 **내보낼** 문장을 막으려고 만든 것이다. 손님이 **물어보는** 말인 "가격"·"요금"·"회비"·"월 얼마" 는 하나도 안 걸린다.
- 최소 수리: `api_chat` 에 수신용 목록을 따로 둔다 — `("가격","요금","회비","비용","얼마")` 를 MEDICAL_WORDS 옆에 추가.
- 수리: `PRICE_QUESTION_WORDS` 추가 후 `_forbidden_hit`에 OR 로 합류.
- 실측: "회비가 얼마인가요" POST → `answered:false`, 상담예약 안내로 폴백(2026-09-05).
- 커밋: 이 커밋(server/erp_api/api_chat.py).

### L4. api_chat 자체점검이 서버 밖에서 못 돈다
- 자리: `server/erp_api/api_chat.py:193-194` (`_load_faq("1_wellperion")` → `/srv/erp/faq/…`)
- 개발 PC 에서 `python api_chat.py` 를 돌리면 "FAQ 없음" 으로 실패한다(실측). 매칭 규칙을 고칠 때 로컬 확인이 막힌다.
- 최소 수리: `seed_faq/1_wellperion.json` 를 폴백으로 읽게 한 줄 바꾼다.
- 수리: `_load_faq`가 `/srv/erp/faq` 실패 시 `seed_faq/{tenant}.json` 폴백(서버는 실제 경로가 항상 먼저 있어 동작 그대로).
- 실측: 로컬 PC 에서 `python api_chat.py` 자체점검 실행 → `selftest ok`(이전엔 "FAQ 없음"으로 즉시 실패).
  다캠(2_dietcamp) seed 는 콘텐츠가 원래 빈 자리표시자라 해당 케이스만 자체점검에서 skip 처리(콘텐츠는 시보 소관).
- 커밋: 이 커밋(server/erp_api/api_chat.py).

### L5. `channel_captured_at` 에 포착 시각이 아니라 접수 시각이 들어간다
- 자리: `server/erp_api/sync_inquiries.py:111` (`ts or None`)
- 칸 이름은 '유입경로를 언제 잡았나' 인데 값은 문의 제출 시각이다. `channel_code` 가 `unknown` 인 행에도 채워져
  "포착했다" 로 읽힌다.
- 최소 수리: `channel_code != "unknown"` 일 때만 `now` 를 넣는다.
- 수리: `replace_type`에서 `code`를 한 번만 계산해 재사용 — `channel_captured_at`은 `code != "unknown"`일 때만 `now`, 아니면 `None`.
- 실측: 서버에서 `sync_inquiries.py` 수동 실행 뒤 DB 확인 — `unknown` 2549건 전부 `channel_captured_at IS NULL`,
  `referral` 4건은 실행 시각(15:20:04)으로 채워짐(2026-09-05).
- 커밋: 이 커밋(server/erp_api/sync_inquiries.py).
- 덧붙임(추정): 컷오버 비교 `timestamp < "2026-09-05"` 는 문자열 비교다. 멤버십 문의 실제 형식
  `"2026-09-05 14:30:00"` 에서는 정상 동작한다(스냅샷 실측). 강습 문의가 UTC ISO(`…T05:12:00.000Z`)로 오면
  KST 오전 문의가 전날로 읽혀 하루치가 `unknown` 이 된다 — 강습 응답 형식 확인 필요.

### L6. 접수번호 시퀀스가 tenant 를 안 나눈다
- 자리: `server/common/schema.sql:191-192`
- 표는 전부 `tenant_id` 로 나누는데 시퀀스는 전역이다. 다캠(2_dietcamp) 이 같은 DB 로 접수를 받는 순간 번호가 섞인다.
- 최소 수리: 지금은 그대로 두고, tenant 가 늘 때 `reception_seq_{tenant}` 로 나눈다.
- 후속(2026-09-05): 이번 수리 범위에서 제외 — 스키마 변경(시퀀스 분리)이 필요해 다음 tenant 온보딩 때 처리.

---

## 이상 없음으로 확인한 것

- 채팅 위젯 XSS: `chat_widget.html:64-76` `linkify()` 가 텍스트 노드로만 붙인다. `innerHTML` 은 고정 뼈대에만 쓴다.
- SQL 인젝션: 검수 8개 파일 전부 파라미터 바인딩. 문자열로 이어 붙이는 자리는 표 이름·정렬 절인데 전부 코드 안 상수다.
- `/api/chat/{tenant}/unanswered` 권한: 정규식 location 이 `/api/chat/` 접두보다 먼저 잡히고, 끝에 슬래시를 붙여도
  FastAPI 가 307 로 정본 주소로 되돌려 관문을 다시 지난다.
- `/api/reception/lost`(습득물 등록): `/api/` 규칙 아래라 로그인 뒤에서만 열린다.
- `/uploads/` 는 `^~` 접두라 폴더 정규식이 못 가로챈다.
- 폴더 location 정규식의 제외 목록: erp.conf 안의 프록시·alias 접두 location 을 전부 덮는다(빠진 것 없음).

## 검수 못 한 것

- nginx 실행 설정이 저장소 파일과 같은지(서버 `/etc/nginx/conf.d/` 실물 미확인).
- `reception_seq` 현재값 — H1 이 이미 수동 처리됐는지 여부.
- `/etc/cron.d/erp-reception-sync` 가 실제로 도는지(C1 의 발동 조건).
- 세 가지 다 서버 ssh 1회로 확인된다.
