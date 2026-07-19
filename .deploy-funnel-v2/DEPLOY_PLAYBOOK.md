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
3. 프로덕션 배포 명령(기존 배포 갱신, 새 배포 생성 금지) — **raw `clasp deploy` 직접
   호출 금지, 반드시 배포 직전 버전 가드 경유**(`scripts/gas_deploy_guard.py`,
   `docs/GAS_배포_규율.md`):
   ```
   python scripts/gas_deploy_guard.py funnel-v2 -- -i AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo -d "설명"
   ```
4. 가드가 배포 직전 버전수를 자동 조회해 180/195 임계를 판정한다(180~194=경고 후
   진행, ≥195=기본 중단·`--force`로만 강행) — 수동 `clasp list-versions` 확인은
   보조 수단.

## 축2 — 이사 플레이북 (또 차면 1회 실행)
자동화 가능한 부분 = `scripts/gas_funnel_migrate.sh` (아래). **딱 한 단계만 수동**: 새 스크립트 편집기에서 cao가 함수 1회 실행→'허용'(OAuth 인증). 그 외(생성·push·배포·16곳 재배선·검증)는 스크립트가.

수동 인증이 필요한 이유: 웹앱 executeAs=USER_DEPLOYING → 배포자(cao) 최초 1회 스코프 승인 필수. 이건 구글 정책상 자동화 불가.

## 축3 — 트리거 이전 (이사 시 필수 · 2026-07-19 시토 · 이중발신 사고 재발방지)
**사고:** 2026-07-18 이사 때 웹앱 URL 16곳만 재배선하고 **GAS 설치형 트리거를 이전하지 않아**,
구 v1(`1A77oDR`)의 onFormSubmit·5분 poller가 계속 발화 → 문의알림방 이중발신(구 v1 stale + 신 v2). v2는 트리거 0이었음.
**이사 체크리스트에 반드시 포함:**
1. **구 스크립트(v1) 문의 트리거 전삭제** — `cleanupInquiryTriggersV1()` 실행, 또는 편집기 트리거 UI에서
   `onInquiryFormSubmit`(폼별)·`_notifyNewInquiries_`(5분 poller) 삭제. `memberMatchAutostamp` 등 무관 트리거는 보존.
2. **신 스크립트(v2) 문의 트리거 설치** — `installInquiryFormSubmitTriggers()`(또는 `setupInquiryTriggersV2()`) 1회 실행(cao OAuth).
   현행 dedup 코드(onFormSubmit이 `INQ_LASTROW` 마커 갱신 → poller 재발송 안 함)로 문의당 1회만 발화.
3. **안전 순서 = 구 삭제 → 신 설치** (역순은 순간 3중발신). 짧은 순간 무알림이 순간 3중보다 안전.
4. **검증:** 새 문의 1건 → 문의알림방 알림 **정확히 1건**.
5. **원칙:** 백업 스크립트는 **코드만 보존, 트리거는 0**. 트리거는 항상 현행 prod 1곳에만.

## 재배선 대상 (URL 바꿀 때 참조 — 16곳)
페이지 6(문의회원·마케팅현황대시보드·wellperion_guide(main)·자율현황·wp_inquiry_form·월간마케팅보고서) + 파이썬 8(ops_daily_digest·daily_scheduler·weekly_marketing_feedback·cpo_report·kpi_collector·qa_inject_inquiry·telegram_health_check·monthly_marketing_report) + Survey.js 자기참조(_WARM_EXEC_URL). **제외:** status/_queue.json(문서)·status/backups·죽은 워크트리.
⚠️ daily_scheduler.py는 상시 데몬 → URL 교체 후 **재기동해야** 새 백엔드 사용(구 백엔드 살아있어 그 전까진 정상).
