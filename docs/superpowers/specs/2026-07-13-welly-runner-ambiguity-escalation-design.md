# 예약 러너 모호성 에스컬레이션 + 무인 발효 — 확정 설계

- 확정: 2026-07-13 (deep-interview 조기종료·GM 위임·GM go "이대로 구현+발효")
- 임계값: deep-interview 5% (project .claude/settings.json) · 조기종료(GM "웰리 편한대로 결정해줘 따라갈게")
- 전제: 예약 러너(`scripts/welly_auto_runner.py`) 이미 구축·검증 — 가역·저위험만·빈포인터 제외·클린트리 가드·재귀방지·역롤백·RUNNER_LIVE 게이트.

## 목표
러너가 무인으로 돌되, **모호한 배는 억지 실행·조용한 skip 대신 GM에게 물어** 답을 받아 진행한다. 신뢰가 쌓이면 자율 폭을 넓힌다.

## 채널 = 하이브리드 (GM 결정 반영: "알림 뜨면 체크" + "CLI가 편함")
- **텔레그램 = 알림(핑)만.** 모호 배 발생 시 GM 채널로 "모호한 배 N건 — 세션 열어 인터뷰 필요" 저빈도 핑(dedup·하루 과다발송 금지).
- **인터뷰 = CLI 세션의 deep-interview.** GM이 세션 열면(핸드폰 원격) 웰리가 parked 배를 deep-interview(AskUserQuestion)로 물음. 텔레그램 왕복 인터뷰는 만들지 않음(단순).

## 흐름
```
러너(예약) 배 선택 → [모호 판정] → 모호하면 park(플래그, 실행 안 함) + 텔레그램 핑
                                  → 안 모호하면 기존대로 자율 실행(가역·클린트리)
GM 세션 열기 → 웰리 부팅이 parked-interview 배 서피스 → deep-interview(AskUserQuestion·폰)
→ GM 답변을 배 note에 기록 + 플래그 해제 → 다음 러너 사이클에서 실행
```

## ① 모호 판정 (보수적 기본값 — 의심되면 물음)
배를 실행하려 할 때 아래 중 하나면 '모호'로 park:
- 산출물·절차가 note에 구체적으로 안 나옴(무엇을 만들지 불명확).
- 접근법이 여러 개(어느 방향인지 결정 필요).
- 스코프 결정·판단이 필요(러너가 대신 정하면 안 되는 것).
- (안전 기본) 난이도 🛳️크루즈(무거움)는 기본 park+물음.
- v1은 보수적 — 애매하면 park. 오탐(과도한 물음)은 신뢰 축적 후 완화.

## ② park 처리 + 텔레그램 핑
- 배에 `aide_interview_needed: true` + `aide_interview_reason` 플래그(가역·note 무손상). 실행·상태변경 없음.
- 텔레그램 핑: GM 채널, "🧭 러너 모호 배 N건 — 세션 열어 인터뷰" 1줄. dedup(같은 배 반복 핑 금지)·하루 cap.

## ③ 세션 서피스 + 인터뷰 + 재개
- 웰리 부팅(ai-ceo.md)에 parked-interview 배 서피스 포인터(북극성 세션픽업 패턴 재사용).
- 웰리가 deep-interview(AskUserQuestion)로 물음 → GM 답변 → 배 note에 `[GM 인터뷰 답변]` 기록 + `aide_interview_needed` 해제.
- 다음 러너 사이클: 플래그 없으면 모호 재판정에서 통과 → 실행.

## ④ 무인 발효 범위·주기·안전
- 발효 = `scripts/welly_auto_runner.bat` RUNNER_LIVE=1 + Task Scheduler 등록(ops/register_welly_auto_runner.bat).
- 범위: 가역·저위험·클린트리·비모호만 자율. 비가역·판단·모호는 물음/세션.
- 주기: 하루 1~2회(보수적). 조정 가능.
- 신뢰-테이퍼: 무결 자율 완료 N회(기본 보수적, 예: 5) 누적 시 자율 폭 확대 검토(모호 기준 완화·주기 상향) — GM 확인 게이트 유지.
- 안전: 기존 가드 전부 유지. 즉시 역롤백(RUNNER_LIVE=0 한 줄·git revert).

## 비목표
- 텔레그램 안에서 전체 인터뷰 왕복(복잡·미도입).
- 비가역·판단 배 자율 실행(영원히 세션·GM 결재).
