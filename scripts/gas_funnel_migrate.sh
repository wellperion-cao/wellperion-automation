#!/usr/bin/env bash
# 퍼널 GAS 200버전 상한 → 새 프로젝트 이사 플레이북 (재발방지 축2)
# 2026-07-18 시포. 두 단계: create(자동) → [cao 수동 인증 1회] → repoint(자동).
#
# 사용:
#   bash scripts/gas_funnel_migrate.sh create v3        # 새 프로젝트 생성·push·배포 (새 /exec URL 출력)
#   [편집기에서 cao가 함수 1회 실행→허용 (OAuth·수동·구글정책상 자동화 불가)]
#   bash scripts/gas_funnel_migrate.sh repoint <OLD_ID> <NEW_ID>   # 16곳 URL 치환·검증
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# 재배선 대상 16곳 (status/_queue.json·backups·워크트리 제외)
FILES=(
"3. 웰페리온 가이드/cpo/member/membership.html"
"3. 웰페리온 가이드/cmo/funnel/마케팅현황대시보드.html"
"3. 웰페리온 가이드/wellperion_guide(main).html"
"3. 웰페리온 가이드/자율현황.html"
"3. 웰페리온 가이드/cmo/survey/wp_inquiry_form.html"
"3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html"
"scripts/ops_daily_digest.py"
"telegram_bot/daily_scheduler.py"
"scripts/weekly_marketing_feedback.py"
"scripts/cpo_report.py"
"scripts/kpi_collector.py"
"scripts/qa_inject_inquiry.py"
"scripts/telegram_health_check.py"
"scripts/monthly_marketing_report.py"
)

cmd="${1:-}"; case "$cmd" in
  create)
    label="${2:-vNEXT}"; src="$REPO/.deploy-funnel-v2"; dst="$REPO/.deploy-funnel-$label"
    echo "▶ $src → $dst 복사 후 새 프로젝트 생성"
    mkdir -p "$dst"; cp "$src"/*.js "$src"/appsscript.json "$dst"/ 2>/dev/null || true
    cd "$dst"; rm -f .clasp.json
    clasp create-script --title "funnel $label (버전이사)" --rootDir "$dst"
    clasp push --force
    clasp deploy -d "funnel $label 초기배포"
    echo "── 새 배포 목록 (prod /exec = @1 줄의 ID) ──"; clasp list-deployments
    echo ""
    echo "★수동 1회: 편집기에서 cao 함수 실행→허용 후 →  bash scripts/gas_funnel_migrate.sh repoint <옛ID> <새ID>"
    ;;
  repoint)
    OLD="${2:?옛 deploymentId}"; NEW="${3:?새 deploymentId}"
    for f in "${FILES[@]}"; do
      if [ -f "$f" ]; then b=$(grep -c "$OLD" "$f" || true); sed -i "s/$OLD/$NEW/g" "$f"
        echo "  $f : $b→$(grep -c "$OLD" "$f" || true)"; fi
    done
    # v2/다음 Survey.js 자기참조(_WARM_EXEC_URL)도
    for s in "$REPO"/.deploy-funnel-*/Survey.js; do sed -i "s/$OLD/$NEW/g" "$s" 2>/dev/null || true; done
    left=$(grep -rl "$OLD" "$REPO/3. 웰페리온 가이드" "$REPO/scripts" "$REPO/telegram_bot" 2>/dev/null | grep -v backups || true)
    echo "── 잔존(라이브) 옛URL: ${left:-없음(0)}"
    echo "★검증: 새/exec 대조(등록·문의 수 동일) → 커밋·푸시 → 시크릿크롬 문의회원 로드 확인 → daily_scheduler 재기동"
    ;;
  *) echo "usage: $0 create <label> | repoint <OLD_ID> <NEW_ID>"; exit 1;;
esac
