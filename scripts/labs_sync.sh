#!/usr/bin/env bash
# 랩스 공개 화면 서버 매분 자동 반영 (GM 지시 2026-09-19 — 시모가 오늘 /labs 재배포를 두 번 손으로 요청 → 근본 수리)
# 서버(/srv/erp/repo)에서 매분 git pull 직후 크론이 이 파일을 돈다(크론 줄은 커밋 메시지 참고).
# 콘텐츠(html/css/svg) 6개만 갱신한다 — nginx 설정은 손대지 않는다(그건 수동 = server/deploy_labs.sh 만).
# 이 위치를 scripts/ 로 잡은 이유: server/** 는 이 서버의 git sparse-checkout 밖이라 매분 pull 로
# 안 들어온다(scp 로만 반영) — scripts/ 는 sparse-checkout 안이라 커밋 즉시 서버에도 자동으로 온다.
# 회색·href 치환 규칙은 server/deploy_labs.sh 와 같다 — 실행 위치가 달라(그건 PC 에서 git show 로
# HEAD 를 읽어 ssh 로 보냄 · 이건 서버가 로컬 워킹트리 파일을 직독) 공통 함수로 묶지 않았다.
set -euo pipefail
REPO="/srv/erp/repo/3. 웰페리온 가이드"
DEST=/srv/www/4_labs
TMP="$DEST/.sync_tmp"   # DEST 와 같은 파일시스템 — mv 가 원자적이려면 필수
mkdir -p "$TMP/assets" "$DEST/assets"
trap 'rm -rf "$TMP"' EXIT

grep -v 'page_ping.js' "$REPO/erp/admin/company_intro.html" \
  | grep -v 'href="company.html"' \
  | sed 's#href="\.\./\.\./assets/wp-ui\.css"#href="assets/wp-ui.css"#' > "$TMP/intro.html"
grep -v 'page_ping.js' "$REPO/erp/admin/labs_home.html" \
  | sed 's#href="\.\./\.\./assets/wp-ui\.css"#href="assets/wp-ui.css"#' > "$TMP/index.html"
cp "$REPO/erp/admin/labs_posts.html"    "$TMP/posts.html"
cp "$REPO/erp/admin/platform_brand.css" "$TMP/platform_brand.css"
cp "$REPO/erp/admin/axlabs_logo.svg"    "$TMP/axlabs_logo.svg"
cp "$REPO/assets/wp-ui.css"             "$TMP/assets/wp-ui.css"

sync_one() {  # 내용이 같으면 버림(mtime 유지) · 다르면 원자적 교체
  cmp -s "$1" "$2" 2>/dev/null && rm -f "$1" || mv -f "$1" "$2"
}
sync_one "$TMP/intro.html"         "$DEST/intro.html"
sync_one "$TMP/index.html"         "$DEST/index.html"
sync_one "$TMP/posts.html"         "$DEST/posts.html"
sync_one "$TMP/platform_brand.css" "$DEST/platform_brand.css"
sync_one "$TMP/axlabs_logo.svg"    "$DEST/axlabs_logo.svg"
sync_one "$TMP/assets/wp-ui.css"   "$DEST/assets/wp-ui.css"
