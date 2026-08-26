# 🛡️ 재발방지 회귀감시
_갱신: 2026-08-26 · 자동 산출(ssot/incident_regression_monitor.py)_

## 판정: ⚠️ 회귀 감지 · 경보 억제(직전과 동일 내용 · 지문 ba3fbdf682079222)

| 검사 | 결과 |
|---|---|
| 신규 캐논 발산(baseline 초과) | 50건 · official_phone, inquiry_path, telegram_chat_id, bot_token_key, company_scale, company_address, report_bot_handle, sales_year_target, golf_bay_systems, rule:cta_channel_rules, rule:gm_approval_gate_5 |
| 가드 자산 무결 | OK |
| 박제 무결(GUARDED) | OK |
| 결정정합 누출(leaked · §6.3) | OK(0건) |

### ⚠️ 신규 드리프트(회귀)
- **official_phone**: scripts/poc-evidence/home_page6_content_backup_20260818_180054.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181607.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181629.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181654.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181720.txt, scripts/poc-evidence/home_page6_content_backup_20260818_184302.txt, scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt, status/monthly_ops_plan.json
- **inquiry_path**: scripts/graphify-out/cache/ast/v0.9.31/5c03e52a8ad498d816c2c320d33cba9f68866bd24448b8a01ded45950db29c26.json, scripts/graphify-out/graph.json, scripts/poc-evidence/home_page6_content_backup_20260818_180054.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181607.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181629.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181654.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181720.txt, scripts/poc-evidence/home_page6_content_backup_20260818_184302.txt, scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt, status/gas_push_baseline.json, status/monthly_ops_plan.json, status/schedule_ssot.json
- **telegram_chat_id**: .deploy-funnel-v2/Survey.js, .deploy-intake/Intake.js, scripts/kakao_auto_daily_report.py, scripts/kakao_report_sender.py, scripts/module_reporter.py, scripts/naver_talktalk_custommenu.py, scripts/report_stream_2b_reception.py, scripts/weekly_marketing_feedback.py, status/gas_push_baseline.json, tests/test_room_routing.py
- **bot_token_key**: .deploy-intake/Intake.js, status/gas_push_baseline.json
- **company_scale**: scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt, status/page_hygiene_proposal_20260802.md, status/page_hygiene_proposal_20260823.md
- **company_address**: status/loss_archive_backup_20260813.json, status/member_active_snapshot.json, status/member_ended_snapshot.json
- **report_bot_handle**: scripts/kakao_auto_daily_report.py
- **sales_year_target**: status/gas_push_baseline.json
- **golf_bay_systems**: scripts/poc-evidence/home_page6_content_backup_20260818_181607.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181629.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181654.txt, scripts/poc-evidence/home_page6_content_backup_20260818_181720.txt, scripts/poc-evidence/home_page6_content_backup_20260818_184302.txt, scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt
- **rule:cta_channel_rules**: scripts/graphify-out/graph.json, status/gas_push_baseline.json
- **rule:gm_approval_gate_5**: scripts/graphify-out/graph.json, status/gas_push_baseline.json

### 🛠 기존 코드 캐논 드리프트 (수정 후보 · INC-005류, baseline 수용분)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_181654.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_184302.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_181629.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_raw_content_20260707_192131.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/footer_diag.json` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_180054.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_181607.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260818_181720.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260707_192343.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_raw_content_20260707_192131.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/graphify-out/graph.json` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_publish_preflight.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_golf.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/cafe_upload_playwright.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/graphify-out/cache/ast/v0.9.31/5c03e52a8ad498d816c2c320d33cba9f68866bd24448b8a01ded45950db29c26.json` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/footer_diag.json` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_180054.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-forms/폼안내.js` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260707_192343.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_181629.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scratchpad/L_series_paper/register_queue.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_181607.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/fix_reception_design.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_181720.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_181654.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260818_184302.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_welly_auto_runner.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-intake/Intake.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/kakao_report_sender.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_3_mgmt.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-todo/업무&결재 현황.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/naver_talktalk_custommenu.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/kakao_auto_daily_report.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_3_impl.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/notify_gm_progress.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/weekly_marketing_feedback.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/unassigned_nudge.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/collectors/cpo_sheet_contract.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/reaction_scorecard.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_2b_reception.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/alert_router.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.bat` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/publish_digest.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `tests/test_room_routing.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `wellperion-agents/scripts/ceo_morning_pipeline.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/module_reporter.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_1_impl.py` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-intake/Intake.js` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-reception/RECEPTION_배포.js` (canon 직독으로 전환 권장)
- bot_token_key ← `tests/test_self_health_watchdog.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- company_address ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- company_address ← `scripts/poc-evidence/footer_diag.json` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/precommit_secret_guard.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/kakao_auto_daily_report.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/report_stream_3_impl.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `tests/test_precommit_secret_guard.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/report_stream_1_impl.py` (canon 직독으로 전환 권장)
- naver_cafe_club_id ← `scripts/retrieve_post_url.py` (canon 직독으로 전환 권장)
- golf_bay_systems ← `scripts/poc-evidence/home_page6_content_backup_20260818_181654.txt` (canon 직독으로 전환 권장)
- golf_bay_systems ← `scripts/poc-evidence/home_page6_content_backup_20260818_184302.txt` (canon 직독으로 전환 권장)
- golf_bay_systems ← `scripts/poc-evidence/home_page6_content_backup_20260818_181629.txt` (canon 직독으로 전환 권장)
- golf_bay_systems ← `scripts/poc-evidence/home_page6_content_backup_20260818_184330.txt` (canon 직독으로 전환 권장)
- golf_bay_systems ← `scripts/poc-evidence/home_page6_content_backup_20260818_181607.txt` (canon 직독으로 전환 권장)
- golf_bay_systems ← `scripts/poc-evidence/home_page6_content_backup_20260818_181720.txt` (canon 직독으로 전환 권장)
- rule:cta_channel_rules ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- rule:cta_channel_rules ← `scripts/graphify-out/graph.json` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/cta_utm.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `instagram/namuk.wellperion/260617_AI17_사진몇장올리면AI가블로그인/build_slides.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/graphify-out/graph.json` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `ssot/canon_values.json` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `instagram/namuk.wellperion/260616_AI16_휴관이벤트공지문AI로채널별/build_slides.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `ssot/divergence_scan.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
