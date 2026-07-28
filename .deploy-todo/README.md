# .deploy-todo — 업무·결재 현황 GAS (clasp)

**편집도 배포도 여기서만 한다.** 이 폴더의 `업무&결재 현황.js` 가 라이브 소스 그 자체다
(빌드 산출물이 아니다 — reception 과 반대 구조이니 헷갈리지 말 것).

- **GAS 프로젝트:** 업무·결재 현황 (scriptId = `.clasp.json`)
- **/exec 배포ID(고정·URL 보존):** `AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7`
- **이 GAS가 받치는 화면:** 업무 현황 SSOT · 결재 현황 SSOT · G1 오늘의 항로(`gm_hangro`) ·
  home 대시보드 KPI(`home_kpi`) · CFO 매출현황 월별. **여러 담당이 함께 쓴다 — 배포 전 영향 확인.**

## 배포
```bash
python scripts/gas_deploy_guard.py todo -- -i AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7
```
배포ID를 `-i` 로 재사용해야 화면들이 쓰는 /exec 주소가 그대로 유지된다(새로 만들면 주소가 바뀐다).
**raw `clasp deploy` 직접 호출 금지** — 200 버전 하드리밋 가드(`scripts/gas_deploy_guard.py`)를 반드시 경유.

## 왜 이 문서가 생겼나 (2026-07-28 시우 · GM 지시)
`3. 웰페리온 가이드/coo/todo/apps_script_todo.js` 라는 **부분 사본**이 오래 남아 있었다(49KB,
`home_kpi`·CFO 매출 등이 빠진 옛 갈래). 이름만 보면 그쪽이 정본 같아서, 조회 속도 개선 작업 때
실제로 그 파일을 먼저 고쳤다가 라이브에 안 먹는 걸 발견하고 되돌렸다.
`ssot/enforcement.py` 도 그 파일을 '미끼'로 분류해 변경 감지만 하고 있었을 뿐, 파일 자체는 남아 있었다.
**GM 판단으로 사본을 지우고**(꺼둔 채 두지 않는다 — 약속 L21), 그 자리에 이 문서를 둔다.
