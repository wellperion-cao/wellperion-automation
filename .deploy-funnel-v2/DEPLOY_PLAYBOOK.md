# 퍼널 GAS 배포 플레이북 (v2 — 200버전 재발방지)

**배경:** 구 프로젝트(1A77oDR…)가 200버전 하드리밋 도달 → 배포 전면 차단(버전 삭제 불가). 2026-07-18 v2(`1BezMSW…`)로 이사. 아래 규율로 v2는 몇 달→몇 년 단위로 버틴다.

## 현재 라이브
- **prod /exec:** `AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo`
- scriptId: `1BezMSW_rGi57IrC9IoxoQzczsATVzqwFa039cigvhad0wpCBdOmhHTjQ` · 로컬 `.deploy-funnel-v2`
- 구 프로젝트(`1A77oDR…`·`.deploy-funnel`)=**백업 보존·삭제금지**.

## 축1 — 버전 절약 규율 (제일 중요)
`clasp deploy`(=`create-version`)는 **버전을 1개 영구 소비**한다. 버전은 못 지운다. 그러니:

1. **개발·테스트 중엔 배포하지 말 것.** `clasp push`만 하면 코드가 올라가고 **버전은 0 소비**된다.
   - 테스트는 편집기에서 함수 실행, 또는 인증된 `/dev` URL(소유자만)로.
   - ❌ 오늘의 실수: @188→@200까지 증분 테스트마다 배포 = 12버전 낭비.
2. **`clasp deploy`(재배포)는 "완성된 기능당 1회"만.** 여러 수정을 모아 마지막에 한 번.
3. 프로덕션 배포 명령(기존 배포 갱신, 새 배포 생성 금지):
   ```
   cd .deploy-funnel-v2 && clasp push --force && \
   clasp deploy -i AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo -d "설명"
   ```
4. 배포 전 `clasp list-versions | tail -1`로 잔여 확인. 180 넘으면 축2로 이사 준비.

## 축2 — 이사 플레이북 (또 차면 1회 실행)
자동화 가능한 부분 = `scripts/gas_funnel_migrate.sh` (아래). **딱 한 단계만 수동**: 새 스크립트 편집기에서 cao가 함수 1회 실행→'허용'(OAuth 인증). 그 외(생성·push·배포·16곳 재배선·검증)는 스크립트가.

수동 인증이 필요한 이유: 웹앱 executeAs=USER_DEPLOYING → 배포자(cao) 최초 1회 스코프 승인 필수. 이건 구글 정책상 자동화 불가.

## 재배선 대상 (URL 바꿀 때 참조 — 16곳)
페이지 6(문의회원·마케팅현황대시보드·wellperion_guide(main)·자율현황·wp_inquiry_form·월간마케팅보고서) + 파이썬 8(ops_daily_digest·daily_scheduler·weekly_marketing_feedback·cpo_report·kpi_collector·qa_inject_inquiry·telegram_health_check·monthly_marketing_report) + Survey.js 자기참조(_WARM_EXEC_URL). **제외:** status/_queue.json(문서)·status/backups·죽은 워크트리.
⚠️ daily_scheduler.py는 상시 데몬 → URL 교체 후 **재기동해야** 새 백엔드 사용(구 백엔드 살아있어 그 전까진 정상).
