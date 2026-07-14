# 모듈 등록부 단일 계약 v1 (웰리 확정 · 전 C레벨 공유 SSOT)

> **웰리(AI CEO) 확정 · 2026-07-09.** 지금 CEO·CMO·COO 세션이 각자 등록부를 만들어 발산 중(원리1 위반). 본 문서 = **단일 계약**. 모든 세션은 별도 등록부를 만들지 말고 이 계약에 **자기 도메인 모듈만** 등록한다. 스키마 변경은 웰리 승인.

## 1. 단일 등록부 (하나뿐)
- **정본 파일 = `status/module_registry.json`** 하나. 형태: `{"_doc": ..., "_schema": ..., "modules": [ ... ]}`.
- **별도 레지스트리 파일 금지.** `coo_registry.py`·`module_reporter.py` 등은 **로더·소비자**로만 존재하고, 자기만의 등록부 파일/스키마를 SSOT로 두지 않는다.
- 각 도메인은 자기 모듈만 등록. `id` 접두사가 소유 역할과 일치(`cto-*`·`cmo-*`·`coo-*`…).

## 2. 정본 모듈 스키마 (13 필드 · 상위집합)
| 필드 | 타입 | 뜻 | 레거시(module_reporter.py) 대응 |
|---|---|---|---|
| `id` | str | kebab-case, 도메인 접두사 | (name에서 분리) |
| `owner_role` | str | cto·cmo·coo·cpo·cfo·chro·ceo | owner |
| `owner_nick` | str | 시토·시모·시우… | owner |
| `feature` | str | 특징 기능 한 줄 | name |
| `data_source` | obj | `{kind: gas\|json\|sheet, ref}` | collector |
| `notify_spec` | obj | `{daily, weekly, monthly, channel, bot_id}` | cadence + bot_room |
| `front_card` | obj | `{window, anchor}` | (신규) |
| `autonomy` | str | auto·semi·mech·propose·manual | (신규) |
| `ai_free_fallback` | str | AI 없이도 작동하는 근거 | (신규) |
| `feedback` | obj | `{enabled, audience, entries[]}` | (신규·환류) |
| `reversible` | bool | 가역=자율 완료 가능 | (신규) |
| `enabled` | bool | 모듈 활성 여부 | enabled |
| `honesty_default` | str | measured·estimated·unmeasured (정직 배지 기본) | honesty_default |

- **소비자는 자기 필드만 읽는다(관대).** `module_reporter.py`는 `notify_spec`·`data_source`·`honesty_default`·`enabled`를, 화면은 `front_card`·`autonomy`·`ai_free_fallback`를, 자율 루프는 `reversible`·`owner_role`를 읽는다. 서로의 필드를 파괴하지 않는다.

## 3. 레거시 → 정본 수렴 지침 (각 세션 실행)
- **CMO 세션:** `module_reporter.py`가 읽던 `name/owner/bot_room/cadence/collector`를 정본 필드(`feature/owner_role/notify_spec/data_source`)에서 읽도록 조정. `enabled`·`honesty_default`는 그대로 유지(정본에 편입됨). CMO 마케팅 모듈은 `cmo-*` id로 이 등록부에 등록.
- **COO 세션:** `coo_registry.py`가 자기 등록부를 두지 말고 `status/module_registry.json`을 로드. COO 점검 모듈은 `coo-*` id로 등록.
- **CEO(웰리):** 스키마 계약 소유·조정. 시토 모듈 `cto-*` 등록 완료(3개).

## 4. 즉시 정합할 중복 1건
- `automation_health`(레거시 스키마) + `cto-automation-health`(신규) = **같은 자동화 건강 모듈이 두 번 등록됨.** → `cto-automation-health` 하나로 병합(`honesty_default`·`enabled` 필드 흡수, 레거시 엔트리 제거). **병합 실행은 CMO 세션과 충돌 없는 시점에 웰리가 단독 수행.**

## 5. 5기둥 정합 (제품화 레퍼런스)
| 기둥 | 정본 필드 |
|---|---|
| ① 백엔드 AI 없이 | `ai_free_fallback` |
| ② UX 단축 | `front_card` |
| ③ 모듈화 | 등록부 자체 |
| ④ 모듈별 알림 자동보고 | `notify_spec` |
| ⑤ 채널 자격증명 웹등록·자동로그인 | `credentials_ref`(후속 필드·defer·🔒보안) |

- 제품화: 단일 테넌트(웰페리온) now. 모듈 단위 구조라 후속에 `tenant` 축 확장 여지(지금 구현 안 함·YAGNI).

## 6. 커밋 규율 (동시 세션)
- 같은 워크트리 다중 세션 동시 커밋 중 → 커밋 전 `git status` 확인, 자기 파일만 스테이징, 원샷 커밋. 파괴적 git(reset --hard·amend·rebase) 금지. ref-lock 충돌 시 비파괴 재시도.
- ⚠️ 관찰: `post-commit` 훅(`auto_log_adhoc_to_queue.py`)이 동시 세션 스테이징 파일을 auto-log 커밋에 섞음 → 시토 후속 수리 대상(훅에 세션 격리 필요).
