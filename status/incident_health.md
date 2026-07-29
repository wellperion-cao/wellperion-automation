# 🛡️ 재발방지 회귀감시
_갱신: 2026-07-29 · 자동 산출(ssot/incident_regression_monitor.py)_

## 판정: ⚠️ 회귀 감지

| 검사 | 결과 |
|---|---|
| 신규 캐논 발산(baseline 초과) | 120건 · official_phone, inquiry_path, telegram_chat_id, bot_token_key, company_scale, company_address, report_bot_handle, slogan_en, slogan_kr, naver_cafe_club_id, rule:cta_channel_rules, rule:gm_approval_gate_5 |
| 가드 자산 무결 | OK |
| 박제 무결(GUARDED) | 깨짐: INC-010(FIXED(근본원인 정규화·복원 완료 · 견고화는 후속)), INC-011(OPEN(코드 검증 완료 · 라이브 발효=봇 재기동(퇴근 재부팅) 대기)), INC-023(OPEN), INC-024(OPEN), INC-025(OPEN), INC-027(OPEN), INC-029(OPEN), INC-031(OPEN), INC-033(OPEN), INC-034(OPEN), INC-035(OPEN(의식적 예외 — GM 수용)), INC-037(OPEN) |
| 결정정합 누출(leaked · §6.3) | OK(0건) |

### ⚠️ 신규 드리프트(회귀)
- **official_phone**: 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt, scripts/poc-evidence/footer_diag.json
- **inquiry_path**: .deploy-forms/폼안내.js, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt, scripts/poc-evidence/footer_diag.json, scripts/review_queue_util.py, status/learning_proposals.json
- **telegram_chat_id**: ops/register_cpo_member_expiry_alert.bat, scripts/alert_router.py, scripts/collectors/cpo_sheet_contract.py, scripts/member_expiry_alert.bat, scripts/reaction_scorecard.py, scripts/report_stream_1_impl.py, scripts/report_stream_3_impl.py, scripts/report_stream_3_mgmt.py, scripts/unassigned_nudge.py, status/backups/_queue_before_shipno_dedup_20260722.json, status/briefs/시토_알림묶기_설계안_20260724.md, status/briefs/웰리_텔레그램_발신전수_20260724.md, status/module_registry.json, status/notify_registry.json, wellperion-agents/scripts/ceo_morning_pipeline.py
- **bot_token_key**: .deploy-reception/RECEPTION_배포.js, docs/superpowers/plans/2026-07-21-웰리-항로-검수-종착지-두뇌.md, status/_queue.json, status/briefs/시토_봇토큰_재발급_런북_20260723.md, tests/test_self_health_watchdog.py
- **company_scale**: 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt, status/page_hygiene_proposal_20260726.md
- **company_address**: 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt, scripts/poc-evidence/footer_diag.json, status/_queue_archive.json, status/backups/before_bulk_snapshot_20260720.json, status/backups/todo_ssot_before_delete_20260725.json
- **report_bot_handle**: scripts/precommit_secret_guard.py, scripts/report_stream_1_impl.py, scripts/report_stream_3_impl.py, tests/test_precommit_secret_guard.py
- **slogan_en**: 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt
- **slogan_kr**: 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt
- **naver_cafe_club_id**: 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260722.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260723.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260724.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260725.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260726.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260727.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260728.txt, 1. AI자료_아카이브/11_카카오톡/★운영부/2026-07/운영부_auto_20260729.txt, status/briefs/CMO-daily-feedback-20260722.md, status/briefs/CMO-weekly-feedback-20260723.md, status/briefs/CMO-weekly-feedback-20260727.md
- **rule:cta_channel_rules**: scripts/review_queue_util.py, status/backups/_queue_before_shipno_dedup_20260722.json
- **rule:gm_approval_gate_5**: .claude/skills/wellperion-brand/SKILL.md, .omc/specs/2026-07-09-cmo-northstar-production-loop-design.md, .omc/specs/deep-interview-experiment2-blog-cta.md, .omc/specs/deep-interview-monthly-report-funnel-redesign.md, .omc/state/sessions/b3359991-443e-4181-85a5-99e1e854838f/pre-tool-advisory-throttle.json, 3. 웰페리온 가이드/cmo/expansion_plan.md, 3. 웰페리온 가이드/status/_queue.json, 3. 웰페리온 가이드/status/_queue_archive.json, docs/superpowers/specs/2026-07-09-cmo-northstar-production-loop-design.md, instagram/namuk.wellperion/260616_AI16_휴관이벤트공지문AI로채널별/build_slides.py, instagram/namuk.wellperion/260617_AI17_사진몇장올리면AI가블로그인/build_slides.py, scripts/cta_utm.py, scripts/generate_channel_copy.py, scripts/review_queue_util.py, ssot/canon_values.json, ssot/divergence_scan.py, status/_queue.json, status/_queue_archive.json, status/backups/_queue_before_shipno_dedup_20260722.json, status/briefs/CMO-2026-06-26-M1-M5-AUDIT.md, status/briefs/CMO-weekly-feedback-20260703.md, status/briefs/CMO-weekly-feedback-20260706.md, status/briefs/CMO-weekly-feedback-20260713.md, status/briefs/CMO-weekly-feedback-20260714.md, tmp/gh_main.html

### 🛠 기존 코드 캐논 드리프트 (수정 후보 · INC-005류, baseline 수용분)
- official_phone ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/footer_diag.json` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_page6_content_backup_20260707_192343.txt` (canon 직독으로 전환 권장)
- official_phone ← `scripts/poc-evidence/home_raw_content_20260707_192131.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/footer_diag.json` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_page6_content_backup_20260707_192343.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_golf.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scratchpad/L_series_paper/register_queue.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/fix_reception_design.py` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_publish_preflight.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/cafe_upload_playwright.py` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/poc-evidence/home_raw_content_20260707_192131.txt` (canon 직독으로 전환 권장)
- inquiry_path ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- inquiry_path ← `tests/test_welly_auto_runner.py` (canon 직독으로 전환 권장)
- inquiry_path ← `.deploy-forms/폼안내.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/reaction_scorecard.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_3_mgmt.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/notify_gm_progress.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/unassigned_nudge.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/collectors/cpo_sheet_contract.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/publish_digest.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_1_impl.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `.deploy-todo/업무&결재 현황.js` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.bat` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/member_expiry_alert.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/alert_router.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `scripts/report_stream_3_impl.py` (canon 직독으로 전환 권장)
- telegram_chat_id ← `wellperion-agents/scripts/ceo_morning_pipeline.py` (canon 직독으로 전환 권장)
- bot_token_key ← `tests/test_self_health_watchdog.py` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-funnel-v2/Survey.js` (canon 직독으로 전환 권장)
- bot_token_key ← `.deploy-reception/RECEPTION_배포.js` (canon 직독으로 전환 권장)
- bot_token_key ← `status/backups/northstar_recommender_pre_gmdm_slim_20260718.py` (canon 직독으로 전환 권장)
- bot_token_key ← `status/backups/daily_scheduler_pre_gmdm_slim_20260718.py` (canon 직독으로 전환 권장)
- bot_token_key ← `status/backups/지원팀_일일점검_pre_INC0716_migration_20260718_110003.js` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_series.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_official_facility_f1.py` (canon 직독으로 전환 권장)
- company_scale ← `scripts/compose_html.py` (canon 직독으로 전환 권장)
- company_address ← `scripts/compose_cta_card.py` (canon 직독으로 전환 권장)
- company_address ← `scripts/poc-evidence/footer_diag.json` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/cpo_report.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/precommit_secret_guard.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/report_stream_3_impl.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `scripts/report_stream_1_impl.py` (canon 직독으로 전환 권장)
- report_bot_handle ← `tests/test_precommit_secret_guard.py` (canon 직독으로 전환 권장)
- naver_cafe_club_id ← `scripts/retrieve_post_url.py` (canon 직독으로 전환 권장)
- rule:cta_channel_rules ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/generate_channel_copy.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/review_queue_util.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `instagram/namuk.wellperion/260616_AI16_휴관이벤트공지문AI로채널별/build_slides.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `ssot/canon_values.json` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `instagram/namuk.wellperion/260617_AI17_사진몇장올리면AI가블로그인/build_slides.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `scripts/cta_utm.py` (canon 직독으로 전환 권장)
- rule:gm_approval_gate_5 ← `ssot/divergence_scan.py` (canon 직독으로 전환 권장)
