# 🛡️ 재발방지 회귀감시
_갱신: 2026-07-20 · 자동 산출(ssot/incident_regression_monitor.py)_

## 판정: ⚠️ 회귀 감지

| 검사 | 결과 |
|---|---|
| 신규 캐논 발산(baseline 초과) | 0건 |
| 가드 자산 무결 | OK |
| 박제 무결(GUARDED) | 깨짐: INC-010(FIXED(근본원인 정규화·복원 완료 · 견고화는 후속)), INC-011(OPEN(코드 검증 완료 · 라이브 발효=봇 재기동(퇴근 재부팅) 대기)), INC-020(OPEN(미조치·차단조치 설계만 확정, 구현 대기)) |

### 🛠 기존 코드 캐논 드리프트 (수정 후보 · INC-005류, baseline 수용분)
- official_phone ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260707_192343.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_raw_content_20260707_192131.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_golf.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_welly_auto_runner.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/cafe_upload_playwright.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scratchpad/L_series_paper/register_queue.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_publish_preflight.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/fix_reception_design.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260707_192343.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_raw_content_20260707_192131.txt` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-todo/업무&결재 현황.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/notify_gm_progress.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/publish_digest.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- bot_token_key ← `status/backups/daily_scheduler_pre_gmdm_slim_20260718.py` (canon 직독으로 전환 권장)
- bot_token_key ← `status/backups/northstar_recommender_pre_gmdm_slim_20260718.py` (canon 직독으로 전환 권장)
- bot_token_key ← `status/backups/지원팀_일일점검_pre_INC0716_migration_20260718_110003.js` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- company_address ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/notify_gm_progress.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- naver_cafe_club_id ← `scripts/retrieve_post_url.py` (canon 직독으로 전환 권장)
- rule:cta_channel_rules ← `scripts/compose_golf.py` (canon 직독으로 전환 권장)
