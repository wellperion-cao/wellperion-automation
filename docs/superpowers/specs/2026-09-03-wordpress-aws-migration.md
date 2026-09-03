# wellperion.com 워드프레스 cafe24 → AWS 이전 절차서

작성 2026-09-03 · 대상 서버 EC2 t3.small(2GB) 15.164.151.105 · 상태 = **서버 준비 완료, 이전 미실행(GM 결재 대기)**

## 0. 현황 실측 (2026-09-03)

| 항목 | 값 |
|---|---|
| 현재 호스팅 | cafe24 (DNS ns2.cafe24.com), HTTP 전용(HTTPS 미동작) |
| 워드프레스 | 설치 경로 `/wp/`, 활성 테마 Salient, 활성 플러그인 22개(WPML 6종·Salient WPBakery·Contact Form 7·KBoard·Toolset·Yoast·WP 파일 관리자 등), 페이지 20개 |
| 저장소 안 cafe24 접속정보 | **없음** (FTP·DB·관리자 계정 어디에도 없음. 유일한 흔적 = 옛 폰트 호스트 `wellperion.cafe24.com/font`) |
| WP 관리자 자동 로그인 | 살아 있음 — `scripts/wordpress_admin_playwright.py --mode inspect` 로 위 정보 읽음(읽기 전용) |
| 준비된 AWS 환경 | nginx 1.30.4 + php-fpm 8.2.33(워커 4) + MariaDB 10.11.18(buffer pool 256M), 워드프레스 한국어판 최신본 `/srv/wp/html` 전개, `wp-config.php` 없음(설치 마법사 미실행) |
| 확인 | `nginx -t` 통과 · `Host: wellperion.com` 요청 시 워드프레스가 302 응답(= 설치 대기 정상) |

## 1. GM 이 해 줘야 하는 것 (이것 없으면 못 옮김)

| # | 받을 것 | 어디서 | 방법 |
|---|---|---|---|
| G1 | cafe24 호스팅 관리자 로그인 | cafe24.com | 계정·비번 (또는 GM이 직접 로그인해 아래를 내려받아 전달) |
| G2 | DB 덤프 `wellperion.sql` | cafe24 phpMyAdmin → 내보내기(형식 SQL, 압축 gzip) | 10~20분 |
| G3 | `wp-content` 전체 (테마·플러그인·업로드 이미지) | cafe24 FTP, 또는 이미 깔린 **WP 파일 관리자** 플러그인으로 zip 압축 후 내려받기 | 용량에 따라 20~60분 |
| G4 | `wp-config.php` 원본 | 같은 경로 | **salt 8줄·`$table_prefix`** 가 핵심 — 이게 없으면 로그인 세션·테이블 접두사가 깨진다 |
| G5 | cafe24 DNS 관리 접근 | cafe24 도메인 관리 | A 레코드 변경 권한 |

## 2. 서버에 넣는 순서 (시토 작업 · GM 손 불필요)

| 단계 | 하는 일 | 시간 | 위험 |
|---|---|---|---|
| S1 | `wp-content` 를 `/srv/wp/html/wp-content` 로 덮어쓰기, 소유자 nginx | 10분 | 낮음 (원본은 cafe24에 그대로) |
| S2 | DB 덤프를 `wp` DB 로 import | 10분 | 낮음 |
| S3 | `wp-config.php` 작성 — DB 값은 `/srv/wp/.env`(서버 전용), salt·`$table_prefix` 는 G4 원본 그대로 복사 | 5분 | prefix 틀리면 "설치 화면"이 뜬다 → 즉시 발견됨 |
| S4 | DB 안 URL 치환 여부 판단: 도메인이 그대로라 **치환 불필요**. HTTPS 전환 시에만 6번 참조 | – | – |
| S5 | 퍼머링크·업로드 경로 확인, `wp.error.log` 무오류 확인 | 10분 | 낮음 |

## 3. 임시 확인법 (DNS 안 건드리고 미리 보기)

| 단계 | 하는 일 |
|---|---|
| T1 | GM PC 관리자 권한 메모장으로 `C:\Windows\System32\drivers\etc\hosts` 열기 |
| T2 | 맨 아래 줄 추가 → `15.164.151.105 wellperion.com` |
| T3 | 크롬 시크릿창에서 `http://wellperion.com/` 열어 새 서버 화면 확인 (메뉴·문의·이미지·다국어 /ko/ /en/) |
| T4 | **확인 끝나면 그 줄을 반드시 지운다** — 안 지우면 GM PC만 계속 새 서버를 본다 |

소요 5분 · 위험 없음(GM PC 한 대에만 적용).

## 4. DNS 전환 (GM 결재 후)

| 단계 | 하는 일 | 시간 | 위험 |
|---|---|---|---|
| D1 | 전환 하루 전, cafe24 DNS 에서 A 레코드 TTL 을 3600 → 300 으로 낮춤 | 5분 + 하루 대기 | 없음 |
| D2 | A 레코드 `wellperion.com`·`www` → **15.164.151.105** 로 변경 | 5분 | 전파 5~30분, 그 사이 접속자는 옛 서버/새 서버가 섞여 보임 |
| D3 | 전파 확인 `nslookup wellperion.com` | 30분 | – |
| D4 | 안정 확인 후 cafe24 호스팅 해지 (최소 2주 유지 권장) | – | 성급히 해지하면 되돌릴 곳이 사라진다 |

전환 중 들어온 문의 글은 **옛 서버 DB 에 남는다** → D2 직후 cafe24 문의·KBoard 테이블을 한 번 더 확인해 옮긴다.

## 5. HTTPS (전환 완료 후)

| 단계 | 하는 일 | 시간 |
|---|---|---|
| H1 | `sudo dnf install certbot python3-certbot-nginx` | 5분 |
| H2 | `sudo certbot --nginx -d wellperion.com -d www.wellperion.com` (DNS 가 이미 새 서버를 가리켜야 함) | 5분 |
| H3 | 워드프레스 설정 → 주소를 `https://` 로 변경, DB 안 `http://wellperion.com` 일괄 치환 | 20분 |
| H4 | **저장소 스크립트 수정** — `http://wellperion.com` 하드코딩 = `scripts/*.py` 안에 **50곳 / 9개 파일** | 30분 |

`http://` 고정 파일(발생 수):
`wordpress_admin_playwright.py`(32) · `verify_reception_flow.py`(5) · `coo_page_guard.py`(4) · `fix_reception_design.py`(3) · `check_reception_wp_drift.py`(2) · `slide_compositor.py`(1) · `naver_blog_upload_playwright.py`(1) · `cta_utm.py`(1) · `cafe_upload_playwright.py`(1). 이 밖에 발행된 콘텐츠·HTML 안의 링크는 http→https 자동 리다이렉트로 덮인다.

## 6. 되돌리기

| 상황 | 조치 | 시간 |
|---|---|---|
| 새 서버 화면이 깨짐 | cafe24 A 레코드를 **원래 IP로 되돌린다**. cafe24 원본은 손대지 않았으므로 그대로 살아난다 | 5분 + 전파 5~30분 |
| 전제 | D4(호스팅 해지)를 하기 전까지만 유효 — 그래서 최소 2주 유지 | – |

되돌리기 대비: D2 직전에 **cafe24 의 기존 A 레코드 IP 를 적어 둔다**(이게 유일한 복구 키).

## 7. 남은 위험

| 위험 | 대응 |
|---|---|
| WPML·Toolset 등 유료 플러그인 라이선스가 서버 IP·도메인에 묶임 | 도메인이 같으므로 대체로 무사. 깨지면 각 플러그인에서 라이선스 재등록 |
| 2GB 메모리 — ERP 관문과 워드프레스 공존 | php-fpm 워커 4·buffer pool 256M 로 잡아 둠. 부하 시 t3.medium 상향 |
| 이메일 발송(Contact Form 7) | cafe24 메일 서버를 쓰고 있었다면 전환 후 미발송 가능 → SMTP 플러그인으로 별도 설정 필요 |
