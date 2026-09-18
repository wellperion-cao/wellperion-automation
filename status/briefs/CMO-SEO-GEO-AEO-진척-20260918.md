# SEO·GEO·AEO 진척 표 (배 2740 · 라이브 실측 16:45)

대상: http://wellperion.com/ (워드프레스 라이브) · 실측 = curl·urllib GET만(POST 없음).

## SEO — 됨 6 / 부분 2 / 안됨 3 (전체 11)

| 항목 | 상태 | 근거(라이브 값) |
|---|---|---|
| sitemap_index.xml | 됨 | GET 200, robots.txt Sitemap 줄이 정확히 가리킴 |
| robots.txt AI 크롤러 허용 | 됨 | GPTBot·ClaudeBot·PerplexityBot·Google-Extended 등 Allow: / |
| ko 홈 title/meta/og/canonical | 됨 | title="웰페리온(Wellperion)", meta description=공식 한 줄, og:title/description 존재, canonical=http://wellperion.com/ko/ |
| en 홈 title/meta/og/canonical | 됨 | meta description 영문 정원제 문장, og 존재, canonical=http://wellperion.com/en/ |
| ko 홈 h1 | 됨 | h1×2, 첫 h1="Limited-Enrollment Sports Club Wellperion" |
| en 홈 h1 | 됨 | h1×2, 동일 |
| ko/inquiry title/meta/og | 부분→됨(이번 반영) | 이전 meta description·og·twitter description 없음(null) 확인 → wp_geo_apply.py로 라이브 반영, curl 재확인 완료(아래 §반영) |
| ko/facilities title/meta/og | 안됨 | meta description 없음(null), og:description 없음. title="Facilities - 웰페리온(Wellperion)"만 있음 |
| ko/inquiry, ko/facilities h1 | 안됨 | 둘 다 `<h1>` 0개(페이지 안에 제목 텍스트는 있으나 h1 태그 미사용) |
| 이미지 alt 비율 | 부분 | ko홈 60%(3/5) · ko/inquiry 60%(3/5) · en홈 60%(3/5) · ko/facilities 15%(3/20 — 17장 alt 없음, 가장 심각) |
| 구조화 데이터(JSON-LD) | 됨 | 전 페이지 IHAF 공통 삽입 확인: Organization·SportsActivityLocation·FAQPage(@graph) 4곳(ko홈·en홈·inquiry·facilities) 동일 존재 |
| 페이지속도 | 안됨 | 이전 라운드 실측(09-18 11:31 Lighthouse) 값 유지 — WP 라이브 홈 35점·LCP 32.5초·전송 5.2MB. 이번 라운드 재측정 안 함(근본해법=도메인 전환, GM 결정 대기·배923) |
| 구글 소유 인증 태그 | 됨(등록은 별개) | `<meta name="google-site-verification" content="SMzsb...">` 라이브 존재. 실제 서치콘솔 제출·소유 계정 확인은 GM 손(gm_asks #64) |
| 네이버 서치어드바이저 등록 | 못잼(GM 손) | 배 2741 별건 · GM 로그인 필요 |

## GEO — 됨 3 / 부분 1 (전체 4)

| 항목 | 상태 | 근거 |
|---|---|---|
| llms.txt | 됨 | GET 200 |
| 회사 정보 일치(canon 대조) | 됨 | llms.txt 전화 02-6261-1200·주소 "서빙고로 413" = canon_values 일치. ko홈·en홈·inquiry·facilities 4페이지 전부 본문에 공식 전화·주소 텍스트 존재(has_official_phone/address = true 4/4) |
| 4엔진 인용 | 부분(1/4) | claude 2/16(09-14 기준, 이번 라운드 재측정 안 함) · chatgpt·perplexity·google_ai = 09-18 12:15 재실측에서 전부 봇차단 벽(스크린샷 증거 있음) — 정공법(유료 API 연동)은 💰 GM 결재 필요 |
| 외부 채널 소개문·이름 일치 | 부분 | 소개문 6/6 done, 채널 이름·업종 5곳 값 확인 = GM 손(gm_asks #55) |

## AEO — 됨 3 (전체 3, 상담봇 자력답변률은 참고 지표)

| 항목 | 상태 | 근거 |
|---|---|---|
| FAQPage JSON-LD | 됨 | @graph 안 FAQPage 노드, mainEntity 14개 확인 (4페이지 공통 IHAF 삽입) |
| 질문형 소제목(요약 텍스트) | 됨 | ko/faq/ 페이지 `<summary>` 14개 전부 "…나요?" 질문형(details/summary 네이티브 아코디언) |
| FAQ 페이지 존재·라이브 | 됨 | http://wellperion.com/ko/faq/ GET 200 |
| (참고) 상담봇 3업체 자력답변률 | 참고 | 최근 7일 98/100/85% — 배 2742 별건, 이 진척 표 카운트에 안 넣음 |

## 이번 라운드 라이브 반영 (1건)

- **무엇**: ko/inquiry/ (post_id=8394) Yoast 메타설명·og:description·twitter:description 이 비어 있던 것(null 확인)을 공식 문구로 채움.
- **문구**: "웰페리온 문의 페이지 — 서울 한남동 정원제 스포츠클럽. 수영·P.T·필라테스·골프·스쿼시·발레·바레 강습, 사우나·스파 상담과 투어 예약은 이 페이지에서 신청하세요." (금지어 없음 · positioning_kr "정원제 스포츠클럽" 사용)
- **도구**: `scripts/wp_geo_apply.py --meta-desc --post-id 8394 --lang ko --from-file <scratch>/inquiry_meta_desc.html`
- **라이브 확인**: curl로 meta description·og:description·twitter:description 3태그 모두 반영 확인(위 §SEO 표 "ko/inquiry" 행).
- **되돌림 백업**: 반영 전 값이 원래 비어 있었으므로(신규 삽입, 덮어쓴 기존 문구 없음) 되돌릴 땐 `<scratch>/inquiry_meta_desc_revert_empty.html`(content="")로 같은 명령 재실행 — 스크래치 경로: `C:/Users/jjky0/AppData/Local/Temp/claude/C--Users-jjky0-welperion-automation/9cf184de-2a41-458b-afae-47199ec91c75/scratchpad/inquiry_meta_desc_revert_empty.html`

## 남은 것(다음 바퀴)

1. ko/facilities/ (post_id=6274) meta description·og·h1 — 같은 방식으로 다음 바퀴 반영
2. ko/inquiry·ko/facilities h1 태그 부재(사람 눈엔 제목 보이나 `<h1>` 미사용) — 화면 코드(디자인) 수정 필요, CMO 단독 처리 어려움
3. ko/facilities 이미지 alt 17장 누락 — 이미지별 alt 문구 작성 필요(다음 바퀴)
4. 페이지속도·GEO 엔진 3개·검색엔진 등록·외부 채널 이름 5곳 = 이전 라운드와 동일하게 GM 손 또는 💰 결재 대기(변화 없음)
