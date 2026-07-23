# 스케줄링 이중체계 전수 실태 조사 (배9640 ③)

조사일: 2026-07-23 · 조사자: 시토(AI CTO) 서브에이전트 · **조사·문서화만, 라이브 무변경**

## 한 줄 결론

Windows 작업 스케줄러(33개)와 파이썬 apscheduler(daily_scheduler.py 내 22개 잡)는 **문자 그대로 겹치는 중복 잡은 없다**(33개 전 대상 스크립트 실재 확인·죽은 잡 0건) — 진짜 문제는 "이중 등록"이 아니라 **2계층 중첩 구조를 사람이 주석으로만 조정**하고 있는 것(예: 08시 통합브리프 흡수로 07/09/15/22시 슬롯을 daily_scheduler.py 안에서 "폐지"했다는 사실이 코드 주석에만 존재), 그리고 **잡 1개 추가 시 Windows 경로는 최소 2~3개 파일 + 비-git 등록 액션**이 필요한 반면 **apscheduler 경로는 기존 파일 1곳 편집**으로 끝난다는 비대칭이다.

---

## 표1: Windows 예약작업 전수 (Wellperion* 33개)

| 이름 | 다음실행 | 대상(Execute+Arguments) | 상태 | 마지막결과 |
|---|---|---|---|---|
| Wellperion-AI-Education-Weekly | 07-26 09:30 | python ai_education_auto_learner.py --no-send | Ready | 0 |
| Wellperion-AI-Learning-Proposer-Weekly | 07-27 09:45 | vbs → ai_learning_proposer_hidden.vbs | Ready | 0 |
| Wellperion-CEO-Morning-Brief-0800-Live | 07-24 08:00 | python wellperion-agents/scripts/ceo_morning_pipeline.py | Ready | 0 |
| Wellperion-CMO-Daily-Marketing-2100 | 07-23 21:00 | vbs → weekly_marketing_feedback_daily_hidden.vbs | Ready | 0 |
| Wellperion-CMO-Monthly-Report | 08-01 09:00 | python monthly_marketing_report.py | Ready | 0 |
| Wellperion-CMO-Weekly-Marketing-Feedback | 07-27 09:00 | vbs → weekly_marketing_feedback_hidden.vbs | Ready | 0 |
| Wellperion-CPO-Inquiry-Snapshot-3min | 3분주기 | vbs → cpo_inquiry_snapshot_hidden.vbs | Ready | 0 |
| Wellperion-CPO-MemberExpiry-Monthly-4thMon-1000 | 07-27 10:00 | vbs → member_expiry_alert_hidden.vbs | Ready | 267011(미도래) |
| Wellperion-Education-Archive-Weekly | 07-26 09:00 | python education_archive_weekly.py | Ready | 0 |
| Wellperion-Engagement-Collect-0930 | 07-24 09:30 | vbs → engagement_collect_hidden.vbs | Ready | 0 |
| Wellperion-GM-Aide-Scan-0630 | 07-24 06:30 | vbs → gm_aide_scan_hidden.vbs | Ready | 0 |
| Wellperion-IG-Reach-Collect-0945 | 07-24 09:45 | vbs → ig_reach_collect_hidden.vbs | Ready | 0 |
| Wellperion-IG-Series-Produce-0730 | 07-24 07:30 | bat → start_ig_series_producer.bat | Ready | 0 |
| Wellperion-IG-Token-Refresh-Weekly | 07-27 06:10 | vbs → ig_token_refresh_hidden.vbs | Ready | 0 |
| Wellperion-Kakao-CheckStatus-Share-2300 | 07-23 23:00 | vbs → kakao_check_share_hidden.vbs | Ready | 0 |
| Wellperion-Kakao-Sales-Report-0930 | 07-24 09:30 | vbs → kakao_auto_daily_report_hidden.vbs | Ready | 0 |
| Wellperion-LSeries-Daily-Card-0845 | 07-24 08:45 | vbs → lesson_series_daily_card_hidden.vbs | Ready | 0 |
| Wellperion-Module-Report-Daily | 07-24 09:10 | vbs → ops/module_report_daily_hidden.vbs | Ready | 0 |
| Wellperion-Module-Report-Monthly | 08-01 09:10 | vbs → ops/module_report_monthly_hidden.vbs | Ready | 267011(미도래) |
| Wellperion-Module-Report-Weekly | 07-27 09:00 | vbs → ops/module_report_weekly_hidden.vbs | Ready | 0 |
| Wellperion-MonthlyCheckReport-0900-D1 | 08-01 09:00 | vbs → monthly_check_report_hidden.vbs | Ready | 267011(미도래) |
| Wellperion-MonthlyOps-End-2100 | 07-31 21:00 | vbs → monthly_ops_report_hidden.vbs end | Ready | 267011(미도래) |
| Wellperion-MonthlyOps-Start-0900 | 08-01 09:00 | vbs → monthly_ops_report_hidden.vbs start | Ready | 267011(미도래) |
| Wellperion-MonthlyOps-Sync-Daily | 07-24 07:00 | vbs → monthly_ops_sync_hidden.vbs | Ready | 0 |
| Wellperion-Morning-Update | 07-24 05:40 | vbs → morning_update_hidden.vbs (→ ops/morning_update.bat) | Ready | 2147946720(코드주석 상 기지 양성·부팅타이밍) |
| Wellperion-NorthStar-0630 | 07-24 06:30 | vbs → northstar_recommender_hidden.vbs | Ready | 0 |
| Wellperion-Ops-Morning-Digest-0730 | 07-24 07:30 | vbs → ops_morning_digest_hidden.vbs | Ready | 0 |
| Wellperion-Telegram-HealthCheck-1300 | 07-23 13:00 | vbs → telegram_health_check_hidden.vbs | Ready | 0 |
| Wellperion-Weekly-Page-Hygiene-Sun-0900 | 07-26 09:00 | vbs → weekly_page_hygiene_hidden.vbs | Ready | 0 |
| Wellperion-Weekly-Self-Review-Sunday | 07-26 10:30 | vbs → weekly_self_review_hidden.vbs | Ready | 0 |
| Wellperion-Welly-Auto-Runner-0730 | 07-24 07:30 | vbs → welly_auto_runner_hidden.vbs | Ready | 0 |
| **WellperionDailyScheduler** | (상주) | vbs → `python -u telegram_bot\daily_scheduler.py` | Ready | 0 |
| **WellperionTelegramBot** | (상주) | vbs → `python -u telegram_bot\bot.py` | Ready | 0 |

- 대상 스크립트/런처 31종 전수 **파일 실재 확인 완료(전부 존재, MISS 0건)**.
- `267011`(6건) = "아직 트리거 도래 안 함"(LastRunTime 1999-11-30 플레이스홀더) — 월간 잡이 이번 달 트리거 전이라 정상. **죽은 잡 아님.**
- `2147946720` (Wellperion-Morning-Update) = launcher vbs 자체 주석(07-15 시토)에 "부팅 직후 대화형 로그온 미완료 시 스케줄러가 실행을 거절하는 0x800710E0류 오표기, erp_status_publisher가 정상(건너뜀)으로 정직 처리"라고 기지(既知) 명시 — 신규 발견 아님.
- 마지막 두 항목(`WellperionDailyScheduler`/`WellperionTelegramBot`)은 "특정 시각에 1회 실행"이 아니라 **상주 프로세스 부팅 담당** — 이 둘이 곧 apscheduler 22잡 체계의 물리적 진입점이다.

## 표2: apscheduler 잡 전수 (telegram_bot/daily_scheduler.py, 22개 · production)

| 잡ID | 시각/주기 | 대상 함수 |
|---|---|---|
| pre_task_notifier | 5분 간격 | `_pre_task_notify` |
| bot_health_check | 15분 간격 | `health_check_bot` |
| env_reload_watcher | 5분 간격 | `check_env_reload` |
| ig_publish_verify_sweep | 30분 간격 | `verify_publish_sweep` |
| erp_status_publisher | 30분 간격 | `_publish_erp_status` |
| kpi_collector_morning | 매일 07:50 | `_collect_kpi` |
| kpi_collector_evening | 매일 21:00 | `_collect_kpi` |
| cpo_sheet_contract_check | 매일 07:50 | `_check_sheet_contract` |
| parking_revenue_crawler | 매일 07:00(KST) | `_crawl_parking_revenue` |
| dashboard_cache_warm | 15분 간격 | `_warm_dashboard_cache` |
| push_sweeper | 5분 간격 | `_push_sweeper` |
| queue_archive_sweep | 6시간 간격(+부팅즉시1회) | `_queue_archive_sweep` |
| report_06/12/18/21/23 (5개) | 매일 06·12·18·21·23시(KST) | `run_report(slot)` |
| report_nudge_pm | 매일 17:00(KST) | `run_nudge("pm")` |
| report_nudge_close | 매일 22:00(KST) | `run_nudge("close")` |
| daily_digest_early | 매일 20:00(KST) | `run_daily_digest(True)` |
| daily_digest_late | 매일 22:30(KST) | `run_daily_digest(False)` |
| stream_3_mgmt_0930 | 매일 09:30(KST) | `run_stream_3_mgmt` |

- `test_hourly` 잡은 `--test` 플래그 전용(scheduler_hidden.vbs는 무인자 실행이라 **비활성** — 표에서 제외).
- 등록부는 `telegram_bot/daily_scheduler.py` 한 파일에 물리적으로 전부 존재(`grep add_job` 17개 호출 블록, 그 중 반복문 2곳이 5+2개를 펼침).

## 표3: 중복 / 한쪽만 / 죽은 것 판정

| 분류 | 항목 | 판정 근거 |
|---|---|---|
| **문자 그대로 중복(동일 액션 이중등록)** | 없음(0건) | 33개 Windows 잡 vs 22개 apscheduler 잡 교차 대조 — 완전 동일 액션 쌍 없음 |
| **동일 시각·다른 내용(혼동 위험)** | 09:30 — Windows `Kakao-Sales-Report`(카톡 매출보고) vs apscheduler `stream_3_mgmt_0930`(텔레그램 업무보고방) | 시각만 같고 채널·내용 다름. 장애 시 "그 09:30 건"이 어느 쪽인지 사람이 헷갈릴 소지 |
| | 23:00 — Windows `Kakao-CheckStatus-Share`(카톡 점검공유) vs apscheduler `report_23`(텔레그램 GM 마감점검 DM) | 상동 |
| **조정이 코드/문서 아닌 주석에만 존재** | daily_scheduler.py 내 07/09/15/22시 슬롯 — "08시 ceo_morning_pipeline(Windows Task)이 흡수했으니 여기선 폐지"라는 사실이 **daily_scheduler.py 파일 상단 주석 3곳**에만 적혀 있고, Windows 쪽 Wellperion-CEO-Morning-Brief-0800-Live 작업 자체에는 이 의존관계가 전혀 기록돼 있지 않음 | 한쪽을 고치는 사람이 반대쪽 존재를 몰라도 아무 경고 없이 진행 가능 — 이중체계의 실제 리스크는 여기 |
| **한쪽에만 있음(정상 — 성격상 당연)** | Windows 전용: 월 1회/주 1회 배치(모니터링 리포트류), 상시 대기 프로세스 부팅 2건(`WellperionDailyScheduler`/`WellperionTelegramBot`) | Windows가 "OS 부팅·장기주기" 담당 역할 |
| | apscheduler 전용: 5~30분 간격 상시 폴링(헬스체크·캐시워밍·발행검증 등) 12건 | 파이썬 상주 프로세스라 초 단위 간격 가능 — Windows Task Scheduler로 흉내내려면 잡을 33→45+ 로 늘려야 함(비현실적) |
| **죽은 것(대상 부재·실패 누적)** | **0건** | 33개 전 대상 스크립트 실재 확인. LastResult 비정상 값 6건은 전부 "월간 미도래"(정상) 또는 "기지 양성"(문서화된 벤치마크) — 진짜 고장 없음 |

## "잡 1개 추가 의식" 실측 (실제 커밋 근거)

**Windows 경로** — 커밋 `82ffe63d4`(hangro_review 크론 런처 신설) 실측:
- 신규 파일 2개: `launchers/hangro_review_hidden.vbs`(숨김창 wscript 래퍼, 6줄) + `scripts/hangro_review.bat`(cron 실행용 ASCII bat, 14줄)
- **git diff에 안 잡히는 비-파일 액션 1개 필수**: `Register-ScheduledTask` (또는 GUI) 실행 — 이건 Windows 레지스트리 상태라 커밋 이력에 없음, 조사자가 매번 직접 실행해야 함
- 참고 사례(`a82964e48` 북극성 추천기 06:30 신설)는 여기에 더해 `.gitignore` 로그 경로 추가, `schedule.json` 미러 갱신, 웹 페이지(`northstar_today.html`) 신설까지 얹힘 — 실제로는 **파일 2~5개 + 등록 액션 1개**가 흔한 범위
- 대상 파이썬 스크립트가 신규면 그 파일까지 +1

**apscheduler 경로** — `stream_3_mgmt_0930`(`daily_scheduler.py:3157-3166`, CTO 2026-07-22) 실측:
- **기존 파일 1곳**(`telegram_bot/daily_scheduler.py`)에 `scheduler.add_job(...)` 블록 삽입 — 신규 파일 0개, 별도 등록 액션 0개(파일 저장 후 프로세스 재기동만 하면 발효)

→ **비대칭 = Windows 3~5배 더 무겁다.** 이게 "잡 하나 추가하는 데 여러 파일을 손대는 의식"의 실체.

## 통합 후보 3안 (권고만, 실행 안 함)

1. **apscheduler 단일화**: 모든 잡을 daily_scheduler.py(or 잡 전용 신규 파일)로 흡수, Windows Task는 "상주 프로세스 부팅" 2개만 남김.
   - 장점: 잡 추가가 파일 1곳 편집으로 통일 / 간격(분 단위) 잡 자연 지원 / 코드로 크론표 diff 가능.
   - 단점: 프로세스 다운 시 전체 잡 동반 정지(단일장애점) / 월간·연간 초장기주기는 상주 프로세스 메모리 신뢰성 부담.
   - 리스크: 현재 5~30분 폴링 12건이 이미 한 프로세스에 몰려 있어 부하집중 심화.

2. **Windows Task 단일화**: apscheduler 22잡을 각각 독립 Windows Task(+launcher)로 환원.
   - 장점: 잡 단위 장애 격리 / OS 레벨 재시도·로그 표준화.
   - 단점: 5분 간격 잡까지 vbs+bat+Register 세트로 만들면 **잡 1개 의식이 지금보다 더 무거워짐**(정반대 방향) / 33→45+ 작업으로 관리면 폭증.
   - 사실상 요구사항(잡 등록 단순화)과 역행 — 비권장.

3. **레지스트리 + 씬 레이어(권장 방향성만)**: 단일 선언 파일(YAML/JSON)에 "시각·주기·대상·실행계층(Windows/apscheduler)"을 기록하고, 두 실행계층은 그 선언을 읽어 동기화하는 얇은 브릿지만 둠.
   - 장점: 08시 vs 07/09/15/22시 같은 "이쪽이 저쪽을 흡수했다"는 관계가 **코드 주석이 아니라 선언 파일에 명시적 필드**로 남음 — 이번 조사에서 드러난 핵심 리스크(표3) 직접 해소.
   - 단점: 브릿지 구현·검증 비용 발생(신규 인프라) / 기존 33+22개 전량 마이그레이션 필요.
   - `status/module_registry.json`(CLAUDE.md §3-2 기존 SSOT) 확장으로 시작하면 신규 파일 생성 없이 착수 가능 — 다음 단계 설계 시 우선 검토 대상.

## 제약 준수

- 예약작업·apscheduler 등록/수정/삭제 없음(전 과정 `Get-*`만 사용).
- 파이썬 스케줄러/봇 프로세스 무변경.
- 본 md 1개 파일만 신규 생성.
