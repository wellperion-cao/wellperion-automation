# COO 모듈 복제 절차 (레지스트리 1줄 → 자동 점등)

파일럿(점검현황) 검증 후, 나머지 모듈을 켜는 표준 절차. AI 없이도 따라 할 수 있게.

## 새 모듈 켜기 5단계
1. `status/coo_modules.json`에서 해당 모듈 찾기(이미 스텁 존재).
2. `data_source.endpoint`·`queries` 채우기(그 모듈 GAS 읽기 엔드포인트·action).
3. `status_metric.compute`·`display` 정의(무엇을 %/숫자로 보일지).
4. `telegram.daily_join`/`anomaly_immediate` 원하는 주기로 true.
5. `enabled: true`, `honesty_tags`를 실제 측정수준(measured/partial/unmeasured)으로.

→ 저장하면: ERP O1 허브 카드·08시 보고·이상 알림·부팅 두뇌가 **자동 반영**(별도 코드 0). 검증: pytest 전체 + O1 시크릿 크롬 실측 + dry-run 보고 라인 확인.

## 게이트
- 라이브 발효(O1 push·텔레그램 실발송)는 GM go.
- 비가역(시트/GAS 변경)은 자율 금지 — 제안만.
