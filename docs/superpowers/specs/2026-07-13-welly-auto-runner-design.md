# 예약 Claude 러너 MVP 설계 — welly_auto_runner (배237 phase3)

> GM 승인(2026-07-13). 담당: AI CTO(시토). 정본 코드: `scripts/welly_auto_runner.py`.
> 이번 구축은 **기본 OFF(dry-run)**. 만들되 실제 무인 실행 0. 라이브 발효는 dry-run 증명 후 GM go.

## 0. 배경·목표

phase1(가이드허브 자율 표면)·phase2(GM 보좌 자율 캡처)에 이어, "웰리가 시켜서 완료까지"를
**headless claude 세션이 스케줄로 자동으로 띄워** 실제로 관통시키는 것이 phase3다. 지금까지는
웰리 오케스트레이션이 사람 세션(GM·CLI) 안에서만 굴렀다 — 이 러너는 그 부트스트랩을 예약작업으로
이관하는 첫 조각이다.

## 1. 안전모델 요약

| 축 | 내용 |
|---|---|
| 선별 | `welly_orchestrate.select_autonomous_ships`(가역·담당clevel·PENDING/IN_PROGRESS·등록부 모듈 존재) + 러너 전용 저위험 추가 필터 + 쿨다운 배 제외 + 난이도(priority) 오름차순 정렬 → **1척만** |
| 게이트 | env `RUNNER_LIVE`(기본 미설정=OFF). OFF=dry-run(배 선택+프롬프트 생성+로그만, claude 미호출·커밋0·`_queue.json` 무변경). `1`=ON일 때만 실제 claude 호출 |
| 재귀 가드 | env `WELLY_AUTO_RUNNER_ACTIVE`. LIVE 실행 시 자식 프로세스에 `=1`로 심음. 이 값이 이미 켜져 있으면(=러너가 띄운 세션이 러너를 다시 부르려 함) 큐 로드조차 없이 즉시 `guard-blocked` |
| 폭주·비용 가드 | 선별기 구조상 1회 1척 보장. 실패 배는 `COOLDOWN_HOURS`(24h) 재선택 금지(`status/welly_auto_runner_state.json`). claude 호출에 타임아웃(`claude_timeout`, 기본 1200s) |
| 역롤백 | LIVE 실행 전후 git HEAD를 `status/welly_auto_runner_log.jsonl`에 기록 — 문제 시 `git revert <commit>` 한 줄 |
| 트리거 | 전용 런처(vbs 숨김→bat→python), Task Scheduler 신규 1개. `daily_scheduler.py`는 건드리지 않음(충돌 회피) |

## 2. 선별 — 저위험 추가 필터

기존 `scripts/welly_orchestrate.py`의 `IRREVERSIBLE_KEYWORDS`(발행·배포·삭제·외부전송·결제·보안·전략·공식값)에
러너 전용으로 아래를 보강한다(`EXTRA_LOW_RISK_EXCLUDE_KEYWORDS`):

```
라이브, GAS, 시트쓰기, 시트 쓰기
```

두 필터를 모두 통과한 배 중, 쿨다운(`status/welly_auto_runner_state.json`의 `cooldown` 맵, 만료 전 task_id)에
있는 배를 제외하고, `priority`(⛵돛단배=0 < ⛴️여객선=1(미표기 기본값) < 🛳️크루즈=2) 오름차순으로 정렬해
**첫 1척**만 반환한다(`select_one_low_risk_ship`). 후보 0건이면 `None`.

## 3. 호출 — headless claude 실행 방식(실측 확정)

이 환경(Windows, claude CLI 설치됨)에서 `claude --help`로 실측 확인한 flag:

- `-p, --print` — 비대화 출력(파이프 가능), 워크스페이스 신뢰 다이얼로그 스킵
- `--model <model>` — 모델 지정
- `--permission-mode <mode>` — `acceptEdits|auto|bypassPermissions|manual|dontAsk|plan`
- `--allowedTools <tools...>` — 허용 도구 화이트리스트(예: `"Bash(git *) Edit"`)
- `--output-format <text|json|stream-json>`
- `--dangerously-skip-permissions` / `--allow-dangerously-skip-permissions` — 전 권한 우회(이 러너는 **사용하지 않음**, 대신 `--allowedTools`로 화이트리스트 최소화)

기존 `scripts/model_router.py`의 `run_claude()`가 이미 `claude -p --model X`(stdin 프롬프트,
subprocess, 재시도·강등 정책)를 프로덕션에서 쓰고 있음을 확인(예: `cto-*` ad-hoc 배 913 —
운영부 카톡 AI 요약이 `model_router.run_claude` 재사용). 단, `model_router`는 **텍스트 생성 전용**
(프롬프트→텍스트, 도구 미사용)이라 배 실행(파일 편집·커밋)에는 부족 — 이 러너는 별도로
`--permission-mode acceptEdits` + `--allowedTools "Read Write Edit Bash(git *) Bash(python*)"`를
추가해 **파일 편집·git 커밋까지 가능한 범위**로 명시 확장하되, 임의 명령 전체 허용
(`--dangerously-skip-permissions`)은 배제해 화이트리스트 밖 행동을 원천 차단한다.

확정 커맨드(LIVE 경로, `scripts/welly_auto_runner.py::run_once` 실측 코드 그대로):

```
claude -p --model claude-sonnet-4-6 \
  --permission-mode acceptEdits \
  --allowedTools "Read Write Edit Bash(git *) Bash(python*)" \
  --output-format text
```

프롬프트는 stdin으로 전달(`subprocess.run(cmd, input=prompt, ...)`), `cwd`=레포 루트,
자식 env에 `WELLY_AUTO_RUNNER_ACTIVE=1` 주입.

## 4. 프롬프트 조립

`build_orchestration_prompt(ship, clevel, nick)` — 선택된 배 1척의 `task_id`·`priority`·`title`·`note`를
채워, "웰리로서 도메인 방식 실행→검증(프론트면 시크릿 크롬)→명시경로 커밋(Co-Authored-By 2줄 포함)→
`clevel_post_action.py`로 G1 기록" 절차를 지시한다. 재귀 폭주 방지 지시("이 세션에서
welly_auto_runner.py를 재호출하지 마라")를 프롬프트 레벨에도 명시해 env 가드와 이중 방어.
비가역·판단 필요 시 즉시 중단·GM 결재로 넘기라는 절대 규칙 포함.

## 5. 게이트 상세

- `RUNNER_LIVE` 미설정 또는 `"0"` → dry-run(기본, 이번 구축 상태)
- `RUNNER_LIVE=1` → LIVE(GM go 후에만 스케줄 launcher .bat에 이 줄 추가)
- dry-run 경로는 `subprocess.run` 자체를 호출하지 않음(테스트로 강제 검증 — `test_run_once_dry_run_never_calls_subprocess`)
- guard-blocked 경로는 큐 파일조차 열지 않음(존재하지 않는 경로를 줘도 에러 없이 즉시 반환 — `test_run_once_guard_blocked_skips_everything`)

## 6. 폭주·비용 가드

- 1회 1척: `select_one_low_risk_ship`이 구조적으로 리스트가 아닌 단일 dict|None만 반환
- 실패 배 쿨다운: LIVE 실행이 실패(exit≠0/타임아웃/새 커밋 없음)하면 `status/welly_auto_runner_state.json`의
  `cooldown[task_id] = {"until": <ISO, now+24h>, "reason": <stderr 요약>}`로 마킹 — 다음 실행에서 자동 제외
- 타임아웃: `claude_timeout`(기본 1200s = 20분) — 예약작업 10분 하드컷을 쓰는 다른 배치(gm_aide_scan 등)와
  달리 이 러너는 별도 스케줄 슬롯(§7)에서 독립 실행되므로 더 긴 상한 허용

## 7. 트리거(제안 — 실제 등록은 GM go 시)

산출물(문서만, 미실행):
- `scripts/welly_auto_runner.bat` — `gm_aide_scan.bat` 패턴(cd /d 레포루트, `PYTHONIOENCODING=utf-8`,
  `python -u scripts\welly_auto_runner.py >> logs\welly_auto_runner.log 2>&1`). `RUNNER_LIVE`는
  **주석 처리된 채로** 포함 — 주석 해제가 곧 1단계 라이브 발효(gm_aide_scan.bat의 `GM_AIDE_AUTO_EXEC` 패턴과 동일한 1-stage 롤백 관례)
- `launchers/welly_auto_runner_hidden.vbs` — `gm_aide_scan_hidden.vbs`와 동일하게 `wscript`로 숨김 실행
- `ops/register_welly_auto_runner.bat` — `schtasks /Create`(제안 주기: 매일 1회, 예: 07:30 — gm_aide_scan(06:30)과
  겹치지 않게) 명령을 담되, **이 세션에서 실행하지 않음**. GM이 관리자 권한으로 직접 실행해야 등록됨

스케줄이 등록돼 있어도 `RUNNER_LIVE`가 주석 처리(OFF)인 한 매일 dry-run만 돌아 무해하다.

## 8. 역롤백

- 1단계(가장 흔함): `welly_auto_runner.bat`에서 `set RUNNER_LIVE=1` 줄을 주석 처리 → 즉시 dry-run 복귀
- 2단계: 러너가 만든 커밋이 문제면 로그(`status/welly_auto_runner_log.jsonl`)의 `commit` 필드로
  `git revert <commit>` 1줄
- 3단계(완전 폐기): `ops/register_welly_auto_runner.bat`와 동일 이름으로 `schtasks /Delete` 실행(등록 스크립트에
  포함된 "old task 제거" 패턴 재사용)

## 9. 발효 절차(GM go 시)

1. dry-run 로그(`status/welly_auto_runner_log.jsonl`) 여러 회차 확인 — 선택되는 배가 매번 합리적인지 육안 검수
2. `ops/register_welly_auto_runner.bat`를 관리자 권한으로 1회 실행(Task Scheduler 등록, 이 시점도 아직 dry-run)
3. `welly_auto_runner.bat`의 `REM set RUNNER_LIVE=1` 주석을 해제 → 다음 스케줄 실행부터 LIVE
4. 며칠 관찰 후 문제 없으면 유지, 문제 시 §8 1단계로 즉시 롤백

## 10. 안 되는 지점(정직 보고)

- `--allowedTools`로 도구를 화이트리스트해도, LIVE 세션이 화이트리스트 내에서 **의도와 다른 파일**을
  건드릴 가능성은 코드 게이트만으로 100% 차단되지 않는다 — 프롬프트 지시(§4)와 커밋 단위 역롤백(§8)이
  최종 방어선이다.
- `verify_reversible_meta`(기존 `welly_orchestrate.py`)는 "아티팩트 필드 비어있지 않음"만 확인하는
  최소 규칙이라, LIVE 세션이 아티팩트 URL을 형식적으로만 채우고 실제 검증을 부실하게 했을 가능성까지는
  코드가 잡지 못한다 — 발효 후 초기 몇 회는 GM/웰리의 육안 검수 병행을 권장(§9 Step 1, 4).
