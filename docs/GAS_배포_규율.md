# GAS 배포 규율 — 버전 200 하드리밋 재발방지

## 사고 배경 (2026-07)
funnel GAS(`.deploy-funnel`)가 배포 버전 200개 하드리밋에 걸려 신규 배포가 막혔다.
구글 Apps Script는 버전 삭제 API를 제공하지 않아(콘솔 수동 삭제만 가능·대량 회수
불가) 이사(`.deploy-funnel-v2` 신규 프로젝트)로 대응 중(#9001 시포). check(165)가
다음으로 임박한 프로젝트 — 아래 3줄 규율 + 상시 모니터로 재발을 막는다.

## 핵심 3줄
1. **개발·테스트는 dev에서.** `clasp push` 후 `@HEAD`(`/dev` URL)로 검증 — 버전을
   소비하지 않는다. `clasp deploy`(프로덕션 배포)는 버전을 1개씩 생성한다.
2. **프로덕션 배포는 완성된 기능 단위로 1회만.** 디버깅 중 반복 재배포 금지 —
   dev URL에서 충분히 검증한 뒤 1회 배포. (`-i <deploymentId>` 재사용은 `/exec`
   URL만 보존할 뿐 버전 소비 자체는 막지 못한다 — `.deploy-reception/README.md` 참고.)
3. **200 근접(버전수 ≥180) 시 이사.** 새 GAS 프로젝트를 만들어 소스 이관 후
   `/exec` URL을 전환한다. 절차는 `#9001 funnel 이사` 완료 후
   `scripts/gas_migrate_project.py`로 일반화 예정(§이사 플레이북).

## 배포 관문 — raw `clasp deploy` 금지 (2026-07-18 CTO 신설)
**프로덕션 배포(`clasp deploy`)는 절대 raw로 직접 실행하지 않는다.** 반드시
`scripts/gas_deploy_guard.py`(배포 직전 버전 가드)를 경유한다. 배포 하나가 조용히
버전을 소비하는 것 자체를 막을 수는 없지만, 임계 임박을 배포 직전에 눈에 띄게
경고해 "몰래 쌓이는" 사고(funnel #9001)를 재발방지한다.

```bash
# 개발/테스트는 여전히 clasp push + /dev URL — 버전 미소비, 가드 불필요
python scripts/gas_deploy_guard.py <project> -- -i <deploymentId> -d "설명"
# <project> = check | funnel | funnel-v2 | todo | voc (또는 .deploy-* 폴더명)
```

동작(배포 직전 버전수 조회 후 임계 판정):
- **<180** : 🟢 조용히 통과 후 배포 진행.
- **180~194** : ⚠️ 눈에 띄는 경고 출력 후 배포 진행(차단 안 함) — 이사 계획을 슬슬 준비.
- **≥195** : 🔴 강경 경고 + **배포 기본 중단**. 강행하려면 `--force` 명시(200 직전
  마지막 슬롯을 실수로 태우는 것 방지).
- 버전 조회 자체가 실패하면 WARN만 출력하고 통과(오탐으로 배포를 막지 않는다).

검증(실제 배포 없이 판정만): `--check-only` 플래그.

## 배포 전 확인 (5개 프로젝트 일괄 표)
```bash
python scripts/gas_version_monitor.py
```
현재 5개 프로젝트 버전수를 표로 확인한다. 🔴(≥190)·🟠(≥150) 상태의 프로젝트는
배포 전 반드시 확인 — 임박 시 신규 배포 대신 이사를 먼저 검토한다. 개별 배포는
위 `gas_deploy_guard.py`가 배포 직전 자동으로 이 조회를 수행하므로 수동 확인은
보조 수단이다.

## 상시 모니터 (2026-07-18 CTO 신설)
- `scripts/gas_version_monitor.py` — Apps Script API로 5개 프로젝트 버전수 조회.
  - `--json` : `status/gas_version_status.json` 발행
  - `--warn` : 임계(≥180) 프로젝트만 1줄 요약 출력, 없으면 무출력(조용)
- **새 정기 알림 채널을 만들지 않는다.** 기존 13시 텔레그램 헬스체크
  (`scripts/telegram_health_check.py`)가 `--warn` 로직을 그대로 흡수해
  임계 초과 시에만 GM 채널에 경보를 얹는다. 평소(전부 <180)엔 무발신.

## 이사 플레이북 (설계만·구현 보류)
funnel 실제 이사(#9001)가 검증된 뒤 `scripts/gas_migrate_project.py`로
절차(신규 프로젝트 생성→소스 push→`/exec` 배포→URL 전환→구 프로젝트 동결)를
재사용 스크립트로 일반화한다. 지금은 funnel 사례 하나로 검증 중이라 구현하지
않는다.

## 5개 GAS 프로젝트 (clasp 로컬)
| 로컬 폴더 | scriptId | 용도 |
|---|---|---|
| `.deploy-check` | `1FLQAzjq6IME2A41QZlfZZSzzAeaFFDAr58M6T-JzDtzzbC4gEKuQFNp6` | 지원팀 일일점검 |
| `.deploy-funnel` | `1A77oDRaa21K25c3-M1AgewNfUzfW-zamfRhYWjlYUrvIdPCYazs8KQru` | 회원문의(이사 중 — 버전 200 도달) |
| `.deploy-funnel-v2` | `1BezMSW_rGi57IrC9IoxoQzczsATVzqwFa039cigvhad0wpCBdOmhHTjQ` | funnel 이사 신규 프로젝트 |
| `.deploy-todo` | `1VUMgK-vJvxCUO_mjQPpTFLjtv3NWWt8ESkCHH-l3QyCYrpBw2RXsYFFg` | 업무&결재 현황 |
| `.deploy-reception` | `1_jF5yhXZfBgw7KX9adW17ER0t_lQ8xrVaGsZBraUJ5AZZPzfIGuFKw9Y` | 종합접수처 |
