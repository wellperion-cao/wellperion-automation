# AWS 인프라 착수 설계 — 웰페리온
작성: AI 웰리 | 2026-08-31 | 배 CTO-2026-08-29-시포-시토-GM업무02-ERP-잔여체크-2항목-AW

---

## 0. 이 문서의 위치

GM 승인 근거: `reports/260829_AWS_AI도구_도입검토_A3.html` (2026-08-29)

**①② (소유관리 정리·사용률 측정)**: GM 권고 `reports/260815_ERP브로제이전환_A3.html` 에 따라 9/1 브로제이 전환 완료 뒤로 순연. 이 문서는 ③ AWS만 다룬다.

---

## 1. GM 액션 (시토가 할 수 없는 것 — 계정 개설이 선행)

| 순서 | 항목 | 비고 |
|------|------|------|
| 1 | AWS 계정 개설 | GM 결제수단(카드) 필요. 어느 회사 메일로 열지도 결정 필요(cao@ / info@) |
| 2 | 결제수단(법인카드) 등록 | 💰 결제 — GM 결재 영역 |
| 3 | 결제 통화 KRW 설정 | **개설 시점에만 바꿀 수 있다.** 나중에 변경 불가 — 비용 알람을 원화로 보려면 이때 해야 한다 |
| 4 | 루트 계정 2단계 인증(휴대폰) 등록 | 루트는 잠가 두고 평소 안 쓴다. GM 휴대폰이라 GM 만 가능 |
| 5 | 계정 번호 · 루트 이메일을 시토에게 공유 | **비밀번호는 필요 없다.** 이후 IAM·예산 설정은 시토가 진행 |
| 6 | 월 예산 상한 승인 | 설계 기준 서버 월 $17~20, 알람 기준 20만 원. 이 상한이 맞는지 한 마디 |

> 2026-09-02 갱신 — 위 목록을 GM업무 9월 「AWS 계정 개설 — 시토가 GM께 요청드리는 것」(2026-09-13) 카드에도
> 같은 내용으로 올렸다. 문자 자동 연동(딜라이브)이 이 계정 하나에 걸려 있어 급해졌다 —
> 2일차 항목에 **탄력적 IP(고정 IP) 1개 발급·연결**을 넣는다(GM 확정 2026-09-02).

---

## 2. 예산 알람 → GM 텔레그램 배선

### 2-1. 아키텍처

```
AWS Budgets (20만원 초과 감지)
    └─► SNS Topic: wellperion-budget-alert
            └─► Lambda: budget_alert_to_telegram
                    └─► Telegram Bot API → GM 업무보고방 (Chat ID: 8254867551)
```

### 2-2. AWS Budgets 설정값

| 항목 | 값 |
|------|----|
| 예산 유형 | Cost budget (월간) |
| 임계값 | 200,000 KRW (≈ USD 150) — 시토가 계정 생성 후 통화 확인 후 확정 |
| 알람 조건 | 실제 지출 > 임계값 |
| 알림 대상 | SNS Topic (아래) |

### 2-3. SNS → Lambda 연결

- SNS Topic 이름: `wellperion-budget-alert`
- 리전: `ap-northeast-2` (서울)
- Lambda 함수: `budget_alert_to_telegram` (스켈레톤 → `scripts/aws_budget_alert_lambda.py`)

### 2-4. IAM 최소 권한

Lambda 실행 역할에 필요한 것만:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```
- Telegram 전송은 outbound HTTPS만 → 추가 AWS 권한 불필요

---

## 3. 서버 1대 사양안

| 항목 | 권고값 | 근거 |
|------|--------|------|
| 인스턴스 유형 | `t3.small` (2 vCPU, 2 GB RAM) | 자동화 스크립트·API 서버 용도; 월 ~$17 |
| 리전 | `ap-northeast-2` (서울) | 지연 최소화 |
| OS | Amazon Linux 2023 | AWS 지원·보안 패치 자동 |
| 스토리지 | gp3 20 GB | 로그·DB 적재 여유 |
| 보안 그룹 | SSH(22) — 사무실 IP만 / HTTPS(443) — 필요 시 추가 | 최소 노출 |
| 탄력적 IP | 1개 할당 | 재시작 후 IP 고정 |
| 예상 월 비용 | $17–20 (t3.small + EIP + 스토리지) | 예산 알람 기준 내 |

**브로제이 CRM 이관 연계**: 브로제이 DB는 이 서버 또는 별도 RDS에 수용. 이관 시 시토 배가 별도 설계.

---

## 4. 시토 착수 순서 (계정 개설 후)

```
Day 0  GM → AWS 계정 개설 + 계정 ID 공유
Day 1  시토 → IAM Admin 역할 설정 + SNS Topic 생성
Day 1  시토 → Lambda 배포 (scripts/aws_budget_alert_lambda.py)
Day 1  시토 → AWS Budgets 설정 (20만원 임계값)
Day 1  시토 → 테스트: Budgets 임계값 1원으로 내려 알람 수신 확인 후 복원
Day 2  시토 → EC2 t3.small 생성 + 탄력적 IP 할당 + SSH 접속 확인
Day 2  시토 → 보안 그룹 최소화 + 기본 모니터링 CloudWatch 활성화
```

---

## 5. ①② 순연 기록

- **소유관리 페이지 정리**: 대장 외 화면 124개 훑기 선행 필요. 9/1 이후 별도 배로 올린다.
- **사용률 측정 배선**: 화면 정리 완료 후 의미 있음. 소유관리 정리 배와 연속 착수.
