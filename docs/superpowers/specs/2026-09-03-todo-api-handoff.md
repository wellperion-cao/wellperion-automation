# 업무·결재 SSOT 읽기 API 인계 (2026-09-03 · 시토 레인 T · 배 922)

받는 분: 나우열M (업무 현황 SSOT · 결재 현황 SSOT 화면·GAS 소유). 전달: 웰리(카톡).
서버 쪽은 **읽기 거울**만 만들었습니다. 시트·GAS·두 화면은 손대지 않았습니다 — 붙일지 말지, 언제 붙일지는 나우열M 결정입니다.

## 설명 10줄
1. 서버(15.164.151.105)가 5분마다 GAS `todo_list`(GM 행 포함)를 읽어 PostgreSQL 표 2개(`todo_items` 전 항목 · `approvals` 결재요청 있는 항목)에 통째로 옮겨 둡니다. 열쇠 = 항목 `id`(TODO-…), 행번호가 아닙니다.
2. 정본은 그대로 시트입니다. API 는 읽기 전용이고 응답마다 `_source: "sheet-mirror"` 가 붙습니다. 쓰기(todo_add·todo_update)는 지금처럼 GAS 로 갑니다.
3. 주소: `GET /api/todo?status=&dept=&owner=&limit=&offset=` 목록 · `GET /api/todo/{id}` 한 건(결재 정보 `_approval` 포함) · `GET /api/todo/summary` 집계 · `GET /api/todo/health` 동기화 상태.
4. 행 모양은 GAS 응답의 한 행과 **똑같습니다**(업무명·담당자·상태·결재요청… 한글 키 그대로). 덧붙는 키만 `_id · _dept · _status · _synced_at · _source`.
5. `summary` 는 home 업무 카드와 같은 정의입니다 — 실무진 담당 행만, 전체/이번달/오늘 × 진행/완료/보류. 오늘(22:03) 실측 = 전체 164 · 이번달 14 · home_kpi_crosscheck.json(21:57) 과 일치.
6. `dept` 는 카테고리 번호로 붙입니다: [1][4]→운영부 · [5]→시설부 · [2][3]→파트너팀 · 그 외 빈값.
7. 로그인 쿠키가 없으면 nginx 가 401 을 줍니다(외부 실측 401). 화면이 서버 안(erp 로그인 뒤)에서 열릴 때만 됩니다 — GitHub Pages 에서 열면 지금처럼 GAS 를 부르는 게 맞습니다.
8. 빠르기: GAS todo_list 는 3초 안팎, 미러는 수십 ms. 대신 최대 5분 늦을 수 있습니다(`_synced_at` 으로 확인).
9. 동기화가 실패하면 미러를 빈 값으로 덮지 않고 직전 것을 유지합니다. `health.last_failed_kst` 에 실패 시각이 남습니다.
10. 문제·요청은 시토에게. 코드 = `server/erp_api/sync_todo.py` · `api_todo.py` · cron `/etc/cron.d/erp-todo-sync`.

## 붙여넣기용 코드 조각 (화면 loadTasks 안 · 선택)
서버 안에서 열렸을 때만 미러를 쓰고, 아니면(또는 401·오류면) 지금 GAS 호출로 그대로 넘어갑니다. 기존 `normalizeTask`·`render` 는 그대로 씁니다.

```js
// 업무·결재 SSOT — 서버 미러 먼저, 안 되면 GAS(정본) 그대로 (시토 2026-09-03 · 배 922)
async function fetchTodoRows() {
  if (location.hostname === '15.164.151.105' || location.hostname === 'erp.wellperion.com') {
    try {
      const r = await fetch('/api/todo?limit=1000', { credentials: 'same-origin' });
      if (r.ok) { const d = await r.json(); if (Array.isArray(d.rows)) return d.rows; }
    } catch (e) { /* 미러 실패 → 아래 GAS 로 */ }
  }
  const r = await fetch(TODO_API_URL + '?action=todo_list&include_gm=1&gmkey=1531', { redirect: 'follow' });
  const res = await r.json();
  if (!res.ok) throw new Error(res.error || 'todo_list 실패');
  return res.data || [];
}
// loadTasks 안에서:  ALL_TASKS = (await fetchTodoRows()).map(normalizeTask);
```
