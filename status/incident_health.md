# 🛡️ 재발방지 회귀감시
_갱신: 2026-09-18 · 자동 산출(ssot/incident_regression_monitor.py)_

## 판정: ⚠️ 회귀 감지

| 검사 | 결과 |
|---|---|
| 자체점검(제외 후 스캔 대상) | 4676건 |
| 신규 캐논 발산(baseline 초과) | 131건 · official_phone, inquiry_path, telegram_chat_id, bot_token_key, company_scale, company_address, report_bot_handle, slogan_en, slogan_kr, naver_cafe_club_id, sales_year_target, golf_bay_systems, aws_server_eip, positioning_kr, official_one_liner_kr, ai_sender_name, platform_company_name, platform_one_liner_kr, sales_year_target_2027, gm_principles, ops_status_report_title, rule:cta_channel_rules, rule:gm_approval_gate_5 |
| 가드 자산 무결 | OK |
| 박제 무결(GUARDED) | OK |
| 결정정합 누출(leaked · §6.3) | OK(0건) |

### ⚠️ 신규 드리프트(회귀)
- **official_phone**: scripts/diet_camp_agent.py, server/counselbot/tenants/1_wellperion.json, server/counselbot/tenants/1_wellperion_faq_draft_20260917.json, server/counselbot/tenants/1_wellperion_qa.json, server/erp_api/seed_faq/1_wellperion.json, server/erp_api/sms_templates.seed.json, status/counsel_questions_summary.json, status/drafts/dlive_ip_request_20260902.md, status/drafts/dlive_msg_templates_confirmed_20260910.md, status/drafts/dlive_test_schedule_20260917.md, status/drafts/전응준대표님_딜라이브_승인서류_20260915.md, status/monthly_ops_plan.json, status/reception_rows_cache.json
- **inquiry_path**: scripts/tenants/wellperion.json, scripts/wordpress_admin_playwright.py, server/counselbot/tenants/1_wellperion.json, server/counselbot/tenants/1_wellperion_faq_draft_20260917.json, server/counselbot/tenants/1_wellperion_qa.json, server/erp_api/api_chat.py, server/erp_api/seed_faq/1_wellperion.json, status/counsel_questions_summary.json, status/drafts/blog_survey_reply_20260902.md, status/gas_push_baseline.json, status/monthly_ops_plan.json, status/monthly_ops_plan_이력.md, status/schedule_ssot.json
- **telegram_chat_id**: .deploy-funnel-v2/Survey.js, .deploy-intake/Intake.js, docs/superpowers/specs/2026-08-31-aws-infra-kickoff-design.md, docs/superpowers/specs/2026-09-03-gas-to-server-migration-plan.md, scripts/aws_bootstrap.py, scripts/aws_budget_alert_lambda.py, scripts/kakao_auto_daily_report.py, scripts/kakao_report_sender.py, scripts/module_reporter.py, scripts/naver_talktalk_custommenu.py, scripts/notify/telegram_user_send.py, scripts/push_lock.py, scripts/report_stream_2b_reception.py, scripts/sales_report_ops_summary.py, scripts/sales_report_server_send.py, scripts/send_ops_digest.py, scripts/telegram_health_check.py, scripts/weekly_marketing_feedback.py, scripts/weekly_report_draft.py, server/deploy_auth.sh, status/cto.json, status/gas_push_baseline.json, status/notify_drift.json, status/push_approvals.json, tests/test_room_routing.py
- **bot_token_key**: .deploy-intake/Intake.js, server/deploy_auth.sh, status/gas_push_baseline.json
- **company_scale**: 2. 브랜드_자료/12_AX랩스/blog_style.json, 2. 브랜드_자료/12_AX랩스/채널/글_02_어떻게.md, PRODUCT.md, scripts/make_fb_cover.py, server/counselbot/tenants/1_wellperion_faq_draft_20260917.json, server/counselbot/tenants/1_wellperion_qa.json, server/erp_api/seed_faq/1_wellperion.json, status/drafts/blog_survey_reply_20260902.md, status/gm_personal_routine.json, status/page_hygiene_proposal_20260802.md, status/page_hygiene_proposal_20260823.md, status/page_hygiene_proposal_20260913.md, status/screen_map.json
- **company_address**: 2. 브랜드_자료/12_AX랩스/blog_style.json, server/counselbot/tenants/1_wellperion.json, server/counselbot/tenants/1_wellperion_faq_draft_20260917.json, server/counselbot/tenants/1_wellperion_qa.json, server/erp_api/seed_faq/1_wellperion.json, status/work_system.json
- **report_bot_handle**: scripts/kakao_auto_daily_report.py, scripts/sales_report_server_send.py, status/telegram_rooms.json
- **slogan_en**: scratch_check_main2.js, status/drafts/blog_survey_reply_20260902.md
- **slogan_kr**: status/drafts/blog_survey_reply_20260902.md, status/page_hygiene_proposal_20260913.md
- **naver_cafe_club_id**: scripts/tenants/wellperion.json
- **sales_year_target**: status/gas_push_baseline.json, status/monthly_report_ledger.json
- **golf_bay_systems**: status/photo_library.json
- **aws_server_eip**: 3. 웰페리온 가이드/erp/admin/AWS_ERP_운영가이드.html, 3. 웰페리온 가이드/wellperion_guide(main).html, status/monthly_ops_plan.json, status/monthly_ops_plan_이력.md, status/push_approvals.json, status/welly_auto_runner_state.json
- **positioning_kr**: 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/blog_style.json, 2. 브랜드_자료/11_고척골프_조재오부장님/blog_style.json, 2. 브랜드_자료/웰페리온_기반_FOUNDATION.md, PRODUCT.md, server/counselbot/tenants/1_wellperion.json, server/counselbot/tenants/1_wellperion_faq_draft_20260917.json, server/counselbot/tenants/1_wellperion_qa.json, server/erp_api/seed_faq/1_wellperion.json
- **official_one_liner_kr**: server/counselbot/tenants/1_wellperion_qa.json, server/erp_api/seed_faq/1_wellperion.json
- **ai_sender_name**: 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/04_소통기록/소통기록.md, 2. 브랜드_자료/10_다이어트캠프_브랜드가이드/blog_style.json, 2. 브랜드_자료/11_고척골프_조재오부장님/04_소통기록/소통기록.md, 2. 브랜드_자료/11_고척골프_조재오부장님/blog_style.json, 2. 브랜드_자료/12_AX랩스/blog_style.json, 2. 브랜드_자료/웰페리온_AI_C레벨_협업매뉴얼_2026-04-24.html, reports/260905_ERP권한_매트릭스.html, telegram_bot/bot.py, telegram_bot/daily_scheduler.py
- **platform_company_name**: 2. 브랜드_자료/12_AX랩스/채널/소개글_5채널.md
- **platform_one_liner_kr**: 2. 브랜드_자료/12_AX랩스/채널/소개글_5채널.md
- **sales_year_target_2027**: profiles/danggn/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/SavedPromptsService-D6QnqyHN.js, profiles/danggn/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/esm-D_VmRwaY.js, profiles/danggn/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/mcpPermissions-CMuwfoXg.js, profiles/jo_naver-blog_login/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/SavedPromptsService-D6QnqyHN.js, profiles/jo_naver-blog_login/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/esm-D_VmRwaY.js, profiles/jo_naver-blog_login/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/mcpPermissions-CMuwfoXg.js
- **gm_principles**: status/monthly_ops_plan.json
- **ops_status_report_title**: 3. 웰페리온 가이드/coo/report/매출회원현황보고.html, 3. 웰페리온 가이드/wellperion_guide(main).html, scripts/sales_report_server_send.py, ssot/canon_values.json, status/screen_bins.json, status/screen_map.json
- **rule:cta_channel_rules**: 2. 브랜드_자료/11_고척골프_조재오부장님/client.json, 3. 웰페리온 가이드/erp/admin/labs_home.html, status/gas_push_baseline.json, status/push_approvals.json
- **rule:gm_approval_gate_5**: 2. 브랜드_자료/11_고척골프_조재오부장님/client.json, status/gas_push_baseline.json, status/push_approvals.json

### 🛠 기존 코드 캐논 드리프트 (수정 후보 · INC-005류, baseline 수용분)
- official_phone ← `scripts/diet_camp_agent.py` (canon 직독으로 전환 권장)
- official_phone ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/wordpress_admin_playwright.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_golf.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_welly_auto_runner.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scratchpad/L_series_paper/register_queue.py` (canon 직독으로 전환 권장)
- inquiry_path ← `server/erp_api/api_chat.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/tenants/wellperion.json` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-forms/폼안내.js` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_publish_preflight.py` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/fix_reception_design.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/cafe_upload_playwright.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-todo/업무&결재 현황.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/naver_talktalk_custommenu.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/unassigned_nudge.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/alert_router.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/notify_gm_progress.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `tests/test_room_routing.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/notify/telegram_user_send.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/sales_report_ops_summary.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/kakao_auto_daily_report.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `wellperion-agents/scripts/ceo_morning_pipeline.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_2b_reception.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_1_impl.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_3_impl.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/weekly_report_draft.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/push_lock.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/telegram_health_check.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/kakao_report_sender.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_3_mgmt.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/aws_bootstrap.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-intake/Intake.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/aws_budget_alert_lambda.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/send_ops_digest.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.bat` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/reaction_scorecard.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/weekly_marketing_feedback.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/sales_report_server_send.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/module_reporter.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/collectors/cpo_sheet_contract.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/publish_digest.py` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-intake/Intake.js` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- bot_token_key ← `tests/test_self_health_watchdog.py` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-reception/RECEPTION_배포.js` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/make_fb_cover.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- company_address ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/report_stream_3_impl.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/precommit_secret_guard.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/report_stream_1_impl.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `tests/test_precommit_secret_guard.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/sales_report_server_send.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/kakao_auto_daily_report.py` (canon 직독으로 전환 권장)
- slogan_en ← `scratch_check_main2.js` (canon 직독으로 전환 권장)
- naver_cafe_club_id ← `scripts/retrieve_post_url.py` (canon 직독으로 전환 권장)
- naver_cafe_club_id ← `scripts/tenants/wellperion.json` (canon 직독으로 전환 권장)
- ai_sender_name ← `telegram_bot/daily_scheduler.py` (canon 직독으로 전환 권장)
- ai_sender_name ← `telegram_bot/bot.py` (canon 직독으로 전환 권장)
- sales_year_target_2027 ← `profiles/danggn/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/mcpPermissions-CMuwfoXg.js` (canon 직독으로 전환 권장)
- sales_year_target_2027 ← `profiles/danggn/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/SavedPromptsService-D6QnqyHN.js` (canon 직독으로 전환 권장)
- sales_year_target_2027 ← `profiles/jo_naver-blog_login/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/esm-D_VmRwaY.js` (canon 직독으로 전환 권장)
- sales_year_target_2027 ← `profiles/jo_naver-blog_login/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/SavedPromptsService-D6QnqyHN.js` (canon 직독으로 전환 권장)
- sales_year_target_2027 ← `profiles/jo_naver-blog_login/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/mcpPermissions-CMuwfoXg.js` (canon 직독으로 전환 권장)
- sales_year_target_2027 ← `profiles/danggn/Default/Extensions/fcoeoabgfenejglbffodgkkbkcdhcgfn/1.0.91_0/assets/esm-D_VmRwaY.js` (canon 직독으로 전환 권장)
- ops_status_report_title ← `scripts/sales_report_server_send.py` (canon 직독으로 전환 권장)
- ops_status_report_title ← `ssot/canon_values.json` (canon 직독으로 전환 권장)
- rule:cta_channel_rules ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `instagram/namuk.wellperion/260617_AI17_사진몇장올리면AI가블로그인/build_slides.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/cta_utm.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `instagram/namuk.wellperion/260616_AI16_휴관이벤트공지문AI로채널별/build_slides.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `ssot/divergence_scan.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `ssot/canon_values.json` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
