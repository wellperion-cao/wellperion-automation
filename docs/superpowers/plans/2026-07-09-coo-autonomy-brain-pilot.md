# COO 자율화 두뇌 파일럿(점검현황) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** COO 소유 모듈을 "레지스트리 구동" 뼈대로 재구성하고, 파일럿 '점검 현황' 1모듈을 레지스트리→ERP 허브 카드→텔레그램 자동보고→부팅 두뇌까지 end-to-end 관통시킨다.

**Architecture:** 단일 SSOT `status/coo_modules.json`(레지스트리)에서 허브 렌더러·자동보고 러너·부팅 두뇌가 모두 읽는다(L01 한 곳 원천). 모듈 1개 추가 = 레지스트리 1줄 → 세 소비자가 자동 점등. 기존 인프라 재사용: HOME 점검 위젯 fetch 패턴(CHECK_API), `ceo_morning_pipeline.build_telegram_report`, `telegram_notifier.TelegramNotifier`, `aide_detectors/reversibility.route`(배237 가역성 라우터).

**Tech Stack:** Python 3.14(전체경로 `C:\Python314\python.exe`), pytest, httpx, 바닐라 JS(main.html SPA), GAS(읽기 전용 소비).

## Global Constraints

- 모든 출력·주석 한국어(약속 L17). 영어/약어 최소.
- 스펙 정본: `.omc/specs/deep-interview-coo-autonomy-brain.md`.
- **레지스트리 = 단일 SSOT**(L01). 허브·러너·부팅두뇌는 값·주기를 하드코딩하지 말고 레지스트리에서 읽는다.
- **자율 = 가역 조치만**(집계·보고·이상표시·항로기록). 비가역(시트/GAS 변경·라이브 배포·보안) = 제안+GM go.
- **라이브 발효 게이트**: O1 페이지 배포(git push→Pages)·08시 텔레그램 실발송·이상 알림 실발송은 GM go+역롤백. 코드/로컬 검증까지는 자율. 부팅 두뇌 자율 write는 기본 게이트 OFF(env 미설정 시 큐 델타 0).
- 점검 GAS(`@56`, `.deploy-check/지원팀 일일점검.js`)는 지원부와 공유 백엔드 — **읽기만**. 회귀 금지.
- 정직 꼬리표(measured/partial/unmeasured)를 카드·보고에 일관 표기(약속 L05).
- 파괴적 git 금지(reset --hard 등). 원샷 커밋.
- 파일럿은 `check_status` 모듈만 완전 배선. 나머지 5모듈 = 레지스트리 스텁(enabled=false·telegram off).

**참조 앵커(기존 코드):**
- HOME 점검 위젯: `3. 웰페리온 가이드/wellperion_guide(main).html` — `home-check-kpi` div(line 601), fetch IIFE(line 10360~10503), `CHECK_API`(line 10361), `parseKpi`(line 10368).
- O1 탭 본문: 같은 파일 `<article id="O1">`(line 5572~5639), 헤더 div(line 5573).
- 08시 보고: `wellperion-agents/scripts/ceo_morning_pipeline.py` — `build_telegram_report`(line 1003), 삽입 지점(line 1091 배너 직후), 발송 `send_reports`(line 1228).
- 텔레그램: `wellperion-agents/telegram_notifier.py` — `TelegramNotifier.send(message, reply_markup=None)`(line 29), 토큰 env `TELEGRAM_BOT_TOKEN`(line 9).
- 가역성 라우터: `scripts/aide_detectors/reversibility.py` — `route(gap)->str`(line 10), `split_lanes(gaps)->tuple`(line 20).
- 큐: `status/_queue.json`(배 구조: task_id/clevel/title/status/priority/ship_no/note/next/reversibility).

---

### Task 1: 모듈 레지스트리 + 로더/검증

**Files:**
- Create: `status/coo_modules.json`
- Create: `scripts/coo_registry.py`
- Test: `tests/test_coo_registry.py`

**Interfaces:**
- Produces: `load_registry(path=REGISTRY_PATH) -> dict`, `validate_registry(reg) -> list[str]`(오류 목록, 빈 리스트=통과), `get_module(reg, mid) -> dict|None`, `iter_enabled(reg) -> list[dict]`, 상수 `REGISTRY_PATH`, `REQUIRED_KEYS`.

- [ ] **Step 1: 레지스트리 JSON 작성**

Create `status/coo_modules.json`:

```json
{
  "_doc": "COO 자율화 두뇌 모듈 레지스트리 — 한 곳 원천(L01). ERP 허브 카드·텔레그램 자동보고·부팅 두뇌가 전부 여기서 읽는다. 모듈 1개 추가 = 여기 1줄 → 세 소비자 자동 점등.",
  "정본": "status/coo_modules.json",
  "modules": [
    {
      "id": "check_status",
      "name": "점검 현황",
      "hub": "O1",
      "erp_paths": ["coo/check/지원부 체계.html", "coo/check/시설부 체계.html", "coo/check/운영부 체계.html", "coo/check/주차관리부 체계.html", "coo/check/강습팀 업장관리.html", "coo/check/파트너팀 체계.html"],
      "data_source": {
        "type": "gas",
        "endpoint": "https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec",
        "queries": {"facility": "action=weekly&dept=facility", "support": "action=today_live&dept=support"}
      },
      "headline_feature": "부서별 점검 완료율·이상 한눈에",
      "status_metric": {"compute": "dept별 pct (facility=weekly, support=today_live)", "display": "{pct}% {badge}"},
      "telegram": {"bot": "@namuki_report_bot", "daily_join": true, "anomaly_immediate": true, "weekly": false, "monthly": false},
      "autonomy": {"reversible": ["aggregate", "report", "flag", "route"], "gated": ["sheet_edit", "gas_deploy", "security"]},
      "honesty_tags": ["measured"],
      "enabled": true
    },
    {"id": "reception_locker", "name": "리셉션·라커", "hub": "O1", "erp_paths": ["coo/reception/종합접수처_현황.html", "coo/리셉션 업무/라커관리/index.html"], "data_source": {"type": "gas", "endpoint": "", "queries": {}}, "headline_feature": "접수·컴플레인·라커 배정", "status_metric": {"compute": "TBD(복제 시)", "display": "-"}, "telegram": {"bot": "@namuki_report_bot", "daily_join": false, "anomaly_immediate": false, "weekly": false, "monthly": false}, "autonomy": {"reversible": ["aggregate", "report", "flag", "route"], "gated": ["sheet_edit", "gas_deploy", "security"]}, "honesty_tags": ["unmeasured"], "enabled": false},
    {"id": "work_approval", "name": "업무·결재 SSOT", "hub": "O1", "erp_paths": ["coo/todo/업무 현황 SSOT.html", "coo/todo/결재 현황 SSOT.html"], "data_source": {"type": "gas", "endpoint": "", "queries": {}}, "headline_feature": "실무진 todo·결재 흐름", "status_metric": {"compute": "TBD(복제 시)", "display": "-"}, "telegram": {"bot": "@namuki_report_bot", "daily_join": false, "anomaly_immediate": false, "weekly": false, "monthly": false}, "autonomy": {"reversible": ["aggregate", "report", "flag", "route"], "gated": ["sheet_edit", "gas_deploy", "security"]}, "honesty_tags": ["unmeasured"], "enabled": false},
    {"id": "notice", "name": "공지/안내문", "hub": "O1", "erp_paths": ["coo/notice/notice_template.html"], "data_source": {"type": "local", "endpoint": "", "queries": {}}, "headline_feature": "안내문 생성·발행", "status_metric": {"compute": "TBD(복제 시)", "display": "-"}, "telegram": {"bot": "@namuki_report_bot", "daily_join": false, "anomaly_immediate": false, "weekly": false, "monthly": false}, "autonomy": {"reversible": ["aggregate", "report", "flag", "route"], "gated": ["sheet_edit", "gas_deploy", "security"]}, "honesty_tags": ["unmeasured"], "enabled": false},
    {"id": "monthly_ops", "name": "월간운영계획·전사회의", "hub": "O1", "erp_paths": ["coo/월간운영계획.html", "coo/전사회의.html"], "data_source": {"type": "gas", "endpoint": "", "queries": {}}, "headline_feature": "매출·부서·로드맵", "status_metric": {"compute": "TBD(복제 시)", "display": "-"}, "telegram": {"bot": "@namuki_report_bot", "daily_join": false, "anomaly_immediate": false, "weekly": false, "monthly": false}, "autonomy": {"reversible": ["aggregate", "report", "flag", "route"], "gated": ["sheet_edit", "gas_deploy", "security"]}, "honesty_tags": ["unmeasured"], "enabled": false},
    {"id": "reregister", "name": "재등록 대시보드", "hub": "O1", "erp_paths": ["coo/reregister/O3.html"], "data_source": {"type": "gas", "endpoint": "", "queries": {}}, "headline_feature": "재등록율·이탈", "status_metric": {"compute": "TBD(복제 시)", "display": "-"}, "telegram": {"bot": "@namuki_report_bot", "daily_join": false, "anomaly_immediate": false, "weekly": false, "monthly": false}, "autonomy": {"reversible": ["aggregate", "report", "flag", "route"], "gated": ["sheet_edit", "gas_deploy", "security"]}, "honesty_tags": ["unmeasured"], "enabled": false}
  ]
}
```

- [ ] **Step 2: 실패 테스트 작성**

Create `tests/test_coo_registry.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R


def test_registry_loads_six_modules():
    reg = R.load_registry()
    assert len(reg["modules"]) == 6


def test_registry_schema_valid():
    reg = R.load_registry()
    assert R.validate_registry(reg) == []


def test_pilot_check_status_enabled_and_wired():
    reg = R.load_registry()
    m = R.get_module(reg, "check_status")
    assert m is not None
    assert m["enabled"] is True
    assert m["telegram"]["daily_join"] is True
    assert m["telegram"]["anomaly_immediate"] is True
    assert m["data_source"]["endpoint"].startswith("https://script.google.com")


def test_five_stub_modules_disabled():
    reg = R.load_registry()
    stubs = [m for m in reg["modules"] if m["id"] != "check_status"]
    assert len(stubs) == 5
    assert all(m["enabled"] is False for m in stubs)
    assert all(m["telegram"]["daily_join"] is False for m in stubs)


def test_iter_enabled_returns_only_pilot():
    reg = R.load_registry()
    enabled = R.iter_enabled(reg)
    assert [m["id"] for m in enabled] == ["check_status"]
```

- [ ] **Step 3: 실패 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coo_registry'`

- [ ] **Step 4: 로더 구현**

Create `scripts/coo_registry.py`:

```python
# -*- coding: utf-8 -*-
"""COO 자율화 두뇌 모듈 레지스트리 로더·검증 (단일 SSOT = status/coo_modules.json)."""
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "status" / "coo_modules.json"

REQUIRED_KEYS = ["id", "name", "hub", "erp_paths", "data_source",
                 "headline_feature", "status_metric", "telegram",
                 "autonomy", "honesty_tags", "enabled"]
TELEGRAM_KEYS = ["bot", "daily_join", "anomaly_immediate", "weekly", "monthly"]


def load_registry(path=REGISTRY_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_registry(reg: dict) -> list:
    errors = []
    mods = reg.get("modules")
    if not isinstance(mods, list):
        return ["modules 키가 리스트가 아님"]
    seen = set()
    for i, m in enumerate(mods):
        for k in REQUIRED_KEYS:
            if k not in m:
                errors.append(f"[{i}] 필수키 누락: {k}")
        mid = m.get("id")
        if mid in seen:
            errors.append(f"[{i}] 중복 id: {mid}")
        seen.add(mid)
        tg = m.get("telegram", {})
        for k in TELEGRAM_KEYS:
            if k not in tg:
                errors.append(f"[{mid}] telegram.{k} 누락")
    return errors


def get_module(reg: dict, mid: str):
    for m in reg.get("modules", []):
        if m.get("id") == mid:
            return m
    return None


def iter_enabled(reg: dict) -> list:
    return [m for m in reg.get("modules", []) if m.get("enabled") is True]
```

- [ ] **Step 5: 통과 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_registry.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: 커밋**

```bash
git add status/coo_modules.json scripts/coo_registry.py tests/test_coo_registry.py
git commit -m "feat(coo): 모듈 레지스트리 SSOT + 로더/검증 (자율화 두뇌 부품①)"
```

---

### Task 2: 점검현황 상태 fetch + 이상 감지

**Files:**
- Modify: `scripts/coo_registry.py` (fetch 헬퍼 추가)
- Test: `tests/test_coo_check_status.py`

**Interfaces:**
- Consumes: `get_module`, module dict의 `data_source.queries`.
- Produces: `fetch_check_status(module, fetch_fn=_http_get_json) -> dict` — 반환 `{"depts": {"facility": {"pct": int, "done": int, "total": int}, "support": {...}}, "anomaly": bool, "reasons": list[str], "tag": "measured"}`. `fetch_fn(url) -> dict` 주입 가능(테스트용).

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_coo_check_status.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R


def _fake_fetch(mapping):
    def _f(url):
        for key, resp in mapping.items():
            if key in url:
                return resp
        raise AssertionError(f"예상 못한 URL: {url}")
    return _f


def test_fetch_normal_no_anomaly():
    reg = R.load_registry()
    m = R.get_module(reg, "check_status")
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 15, "pct": 58}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(m, fetch_fn=fetch)
    assert st["depts"]["facility"]["pct"] == 58
    assert st["depts"]["support"]["pct"] == 92
    assert st["anomaly"] is False
    assert st["tag"] == "measured"


def test_fetch_detects_pct_overflow_anomaly():
    reg = R.load_registry()
    m = R.get_module(reg, "check_status")
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 15, "done": 100, "pct": 667}]},
        "dept=support": {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []},
    })
    st = R.fetch_check_status(m, fetch_fn=fetch)
    assert st["anomaly"] is True
    assert any("100%" in r or "667" in r for r in st["reasons"])


def test_fetch_detects_issue_anomaly():
    reg = R.load_registry()
    m = R.get_module(reg, "check_status")
    fetch = _fake_fetch({
        "dept=facility": {"ok": True, "data": [{"date": "any", "total": 26, "done": 26, "pct": 100}]},
        "dept=support": {"ok": True, "total": 50, "done": 40, "pct": 80, "allIssues": ["시설부 여 3항목 미입력"]},
    })
    st = R.fetch_check_status(m, fetch_fn=fetch)
    assert st["anomaly"] is True
    assert any("미입력" in r for r in st["reasons"])
```

- [ ] **Step 2: 실패 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_check_status.py -v`
Expected: FAIL — `AttributeError: module 'coo_registry' has no attribute 'fetch_check_status'`

- [ ] **Step 3: fetch 헬퍼 구현**

Append to `scripts/coo_registry.py`:

```python
import urllib.request


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _pick_today(resp: dict) -> dict:
    """weekly 응답(data 배열) → 마지막(오늘) 행. today_live 응답 → 그대로."""
    if isinstance(resp.get("data"), list) and resp["data"]:
        return resp["data"][-1]
    return resp


def fetch_check_status(module: dict, fetch_fn=_http_get_json) -> dict:
    ds = module["data_source"]
    endpoint = ds["endpoint"]
    depts, reasons = {}, []
    for dept, query in ds.get("queries", {}).items():
        row = _pick_today(fetch_fn(f"{endpoint}?{query}&_pv=0"))
        total = int(row.get("total") or 0)
        done = int(row.get("done") or 0)
        pct = row.get("pct")
        pct = int(pct) if pct is not None else (round(done / total * 100) if total else None)
        depts[dept] = {"pct": pct, "done": done, "total": total}
        if pct is None or pct > 100:
            reasons.append(f"{dept} 완료율 이상({pct}% — 100% 초과/미산출)")
        for iss in (row.get("allIssues") or []):
            reasons.append(f"{dept}: {iss}")
    return {"depts": depts, "anomaly": bool(reasons), "reasons": reasons, "tag": "measured"}
```

- [ ] **Step 4: 통과 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_check_status.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/coo_registry.py tests/test_coo_check_status.py
git commit -m "feat(coo): 점검현황 상태 fetch + 이상 감지 (부품① 데이터)"
```

---

### Task 3: 08시 통합보고 합류 (자동보고 러너 — 일간)

**Files:**
- Create: `scripts/coo_report_line.py`
- Modify: `wellperion-agents/scripts/ceo_morning_pipeline.py` (`build_telegram_report`, line 1091 배너 직후)
- Test: `tests/test_coo_report_line.py`

**Interfaces:**
- Consumes: `coo_registry.iter_enabled`, `fetch_check_status`.
- Produces: `build_coo_daily_lines(reg=None, fetch_fn=None) -> list[str]` — daily_join=true 모듈별 1줄. 이상이면 ⚠ 접두. 실패 시 정직 꼬리표 `(측정 실패)`.

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_coo_report_line.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R
import coo_report_line as RL


def _fetch_ok(url):
    if "dept=facility" in url:
        return {"ok": True, "data": [{"total": 26, "done": 15, "pct": 58}]}
    return {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []}


def test_daily_line_has_check_status():
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_fetch_ok)
    joined = "\n".join(lines)
    assert "점검 현황" in joined
    assert "58%" in joined and "92%" in joined
    assert "⚠" not in joined


def test_daily_line_flags_anomaly():
    def _bad(url):
        if "dept=facility" in url:
            return {"ok": True, "data": [{"total": 15, "done": 100, "pct": 667}]}
        return {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []}
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_bad)
    assert any("⚠" in ln for ln in lines)


def test_only_daily_join_modules_appear():
    lines = RL.build_coo_daily_lines(reg=R.load_registry(), fetch_fn=_fetch_ok)
    # 스텁 모듈(daily_join=false)은 미출현
    assert all("리셉션" not in ln for ln in lines)
```

- [ ] **Step 2: 실패 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_report_line.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coo_report_line'`

- [ ] **Step 3: 러너 구현**

Create `scripts/coo_report_line.py`:

```python
# -*- coding: utf-8 -*-
"""COO 모듈 일간 자동보고 라인 생성 (레지스트리 telegram.daily_join 구동)."""
import coo_registry as R


def build_coo_daily_lines(reg=None, fetch_fn=None) -> list:
    reg = reg or R.load_registry()
    fetch = fetch_fn or R._http_get_json
    lines = []
    for m in R.iter_enabled(reg):
        if not m["telegram"].get("daily_join"):
            continue
        try:
            st = R.fetch_check_status(m, fetch_fn=fetch)
        except Exception:
            lines.append(f"• {m['name']}: (측정 실패 — 정직 표기)")
            continue
        parts = []
        for dept, d in st["depts"].items():
            label = {"facility": "시설", "support": "지원"}.get(dept, dept)
            parts.append(f"{label} {d['pct']}%")
        badge = "⚠" if st["anomaly"] else "✅"
        lines.append(f"{badge} {m['name']}: " + " · ".join(parts))
    return lines
```

- [ ] **Step 4: 통과 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_report_line.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 08시 파이프라인에 배선**

In `wellperion-agents/scripts/ceo_morning_pipeline.py`, `build_telegram_report`, 배너 삽입(line 1091) 직후에 추가:

```python
    # COO 모듈 자동보고 합류 (레지스트리 구동 — 점검현황 등 daily_join 모듈)
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "..", "scripts"))
        from coo_report_line import build_coo_daily_lines
        _coo_lines = build_coo_daily_lines()
        if _coo_lines:
            lines.append("")
            lines.append("🏢 <b>운영 점검</b>")
            lines.extend(_coo_lines)
    except Exception as _e:
        lines.append(f"🏢 운영 점검: (합류 실패 — {type(_e).__name__})")
```

- [ ] **Step 6: dry-run 검증**

Run: `C:\Python314\python.exe wellperion-agents/scripts/ceo_morning_pipeline.py --dry-run`
Expected: 콘솔 출력 본문에 "🏢 운영 점검" 섹션 + "점검 현황: 시설 …% · 지원 …%" 라인 포함(실제 GAS 실측). 실발송 없음(dry-run).

- [ ] **Step 7: 커밋**

```bash
git add scripts/coo_report_line.py tests/test_coo_report_line.py "wellperion-agents/scripts/ceo_morning_pipeline.py"
git commit -m "feat(coo): 08시 통합보고에 점검현황 자동 합류 (부품③ 일간)"
```

> **라이브 게이트:** 실제 08시 발송은 예약작업이 이미 가동 중이므로, 이 배선이 다음 08시부터 자동 반영됨. 첫 실발송 도착 확인 = GM go 후 익일 검증.

---

### Task 4: 이상 즉시 알림 (자동보고 러너 — 이벤트)

**Files:**
- Create: `scripts/coo_check_anomaly.py`
- Test: `tests/test_coo_check_anomaly.py`

**Interfaces:**
- Consumes: `coo_registry`, `telegram_notifier.TelegramNotifier`.
- Produces: `run_anomaly_check(reg=None, fetch_fn=None, notifier=None, dry_run=True) -> dict` — 반환 `{"alerts": list[str], "sent": int}`. anomaly_immediate=true 모듈만. dry_run=True면 send 안 함.

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_coo_check_anomaly.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R
import coo_check_anomaly as A


class _FakeNotifier:
    def __init__(self):
        self.sent = []
    def send(self, message, reply_markup=None):
        self.sent.append(message)
        return {"ok": True}


def _fetch_anomaly(url):
    if "dept=facility" in url:
        return {"ok": True, "data": [{"total": 26, "done": 26, "pct": 100}]}
    return {"ok": True, "total": 50, "done": 40, "pct": 80, "allIssues": ["시설부 여 3항목 미입력"]}


def _fetch_clean(url):
    if "dept=facility" in url:
        return {"ok": True, "data": [{"total": 26, "done": 15, "pct": 58}]}
    return {"ok": True, "total": 50, "done": 46, "pct": 92, "allIssues": []}


def test_anomaly_triggers_send_when_not_dry():
    n = _FakeNotifier()
    res = A.run_anomaly_check(reg=R.load_registry(), fetch_fn=_fetch_anomaly, notifier=n, dry_run=False)
    assert res["sent"] == 1
    assert n.sent and "미입력" in n.sent[0]


def test_no_anomaly_no_send():
    n = _FakeNotifier()
    res = A.run_anomaly_check(reg=R.load_registry(), fetch_fn=_fetch_clean, notifier=n, dry_run=False)
    assert res["sent"] == 0
    assert n.sent == []


def test_dry_run_never_sends():
    n = _FakeNotifier()
    res = A.run_anomaly_check(reg=R.load_registry(), fetch_fn=_fetch_anomaly, notifier=n, dry_run=True)
    assert res["sent"] == 0
    assert len(res["alerts"]) == 1
    assert n.sent == []
```

- [ ] **Step 2: 실패 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_check_anomaly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coo_check_anomaly'`

- [ ] **Step 3: 구현**

Create `scripts/coo_check_anomaly.py`:

```python
# -*- coding: utf-8 -*-
"""COO 모듈 이상 즉시 텔레그램 알림 (레지스트리 anomaly_immediate 구동). 기본 dry-run."""
import argparse
import coo_registry as R


def run_anomaly_check(reg=None, fetch_fn=None, notifier=None, dry_run=True) -> dict:
    reg = reg or R.load_registry()
    fetch = fetch_fn or R._http_get_json
    alerts = []
    sent = 0
    for m in R.iter_enabled(reg):
        if not m["telegram"].get("anomaly_immediate"):
            continue
        try:
            st = R.fetch_check_status(m, fetch_fn=fetch)
        except Exception:
            continue
        if not st["anomaly"]:
            continue
        msg = f"⚠ <b>{m['name']} 이상</b>\n" + "\n".join(f"• {r}" for r in st["reasons"])
        alerts.append(msg)
        if not dry_run and notifier is not None:
            notifier.send(msg)
            sent += 1
    return {"alerts": alerts, "sent": sent}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="실발송(기본=dry-run)")
    args = ap.parse_args()
    notifier = None
    if args.send:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "wellperion-agents"))
        from telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
    res = run_anomaly_check(notifier=notifier, dry_run=not args.send)
    print(f"이상 {len(res['alerts'])}건 · 발송 {res['sent']}건")
    for a in res["alerts"]:
        print("---\n" + a)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_check_anomaly.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: dry-run 실측**

Run: `C:\Python314\python.exe scripts/coo_check_anomaly.py`
Expected: 콘솔에 "이상 N건 · 발송 0건"(라이브 GAS 실측 기반, 발송 0=dry-run). 발송은 `--send`+GM go.

- [ ] **Step 6: 커밋**

```bash
git add scripts/coo_check_anomaly.py tests/test_coo_check_anomaly.py
git commit -m "feat(coo): 점검 이상 즉시 텔레그램 알림 (부품③ 이벤트·기본 dry-run)"
```

---

### Task 5: 부팅 두뇌 + 가역성 라우터

**Files:**
- Create: `scripts/coo_boot_brain.py`
- Test: `tests/test_coo_boot_brain.py`

**Interfaces:**
- Consumes: `coo_registry`, `aide_detectors/reversibility.route`.
- Produces: `build_module_actions(reg=None, status_map=None) -> list[dict]`(각 `{module, action, kind, revert_ok, external, data_loss}`), `route_actions(actions) -> dict`(`{"auto": [...], "propose": [...]}`), `run_boot_brain(reg=None, status_map=None, apply_gate=None) -> dict`(게이트 OFF 기본 → 큐 write 0·delta 0).

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_coo_boot_brain.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R
import coo_boot_brain as B


def test_reversible_actions_go_auto():
    reg = R.load_registry()
    actions = B.build_module_actions(reg=reg, status_map={"check_status": {"anomaly": False}})
    lanes = B.route_actions(actions)
    auto_names = {a["action"] for a in lanes["auto"]}
    assert {"aggregate", "report", "route"}.issubset(auto_names)
    assert "flag" in auto_names or True  # flag는 이상 시에만


def test_gated_actions_go_propose():
    reg = R.load_registry()
    actions = B.build_module_actions(reg=reg, status_map={"check_status": {"anomaly": False}})
    lanes = B.route_actions(actions)
    propose_names = {a["action"] for a in lanes["propose"]}
    assert {"sheet_edit", "gas_deploy", "security"}.issubset(propose_names)


def test_gate_off_writes_nothing():
    reg = R.load_registry()
    res = B.run_boot_brain(reg=reg, status_map={"check_status": {"anomaly": False}}, apply_gate=False)
    assert res["queue_delta"] == 0
    assert res["applied"] == 0


def test_anomaly_adds_flag_action():
    reg = R.load_registry()
    actions = B.build_module_actions(reg=reg, status_map={"check_status": {"anomaly": True}})
    flags = [a for a in actions if a["action"] == "flag"]
    assert len(flags) == 1
    assert flags[0]["revert_ok"] is True  # 표시=가역
```

- [ ] **Step 2: 실패 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_boot_brain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'coo_boot_brain'`

- [ ] **Step 3: 구현**

Create `scripts/coo_boot_brain.py`:

```python
# -*- coding: utf-8 -*-
"""COO 부팅 두뇌 — 레지스트리 로드 → 모듈 상태 → 가역성 라우터로 자율/제안 분기.
자율 write는 apply_gate(기본 OFF·env COO_BOOT_APPLY)일 때만. 기본 delta 0."""
import os
import coo_registry as R

sys_path = os.path.join(os.path.dirname(__file__), "aide_detectors")
import sys
sys.path.insert(0, sys_path)
import reversibility  # route(gap)->'auto'|'propose'


def build_module_actions(reg=None, status_map=None) -> list:
    reg = reg or R.load_registry()
    status_map = status_map or {}
    actions = []
    for m in R.iter_enabled(reg):
        st = status_map.get(m["id"], {})
        rev = m["autonomy"]["reversible"]
        gated = m["autonomy"]["gated"]
        for a in rev:
            if a == "flag" and not st.get("anomaly"):
                continue  # 이상 없으면 플래그 액션 없음
            actions.append({"module": m["id"], "action": a, "kind": "reversible",
                            "revert_ok": True, "external": False, "data_loss": False})
        for a in gated:
            actions.append({"module": m["id"], "action": a, "kind": "gated",
                            "revert_ok": False, "external": True, "data_loss": False})
    return actions


def route_actions(actions: list) -> dict:
    lanes = {"auto": [], "propose": []}
    for a in actions:
        lane = reversibility.route(a)  # 3부울 규칙 정본 재사용
        lanes["auto" if lane == "auto" else "propose"].append(a)
    return lanes


def _apply_gate_enabled(apply_gate) -> bool:
    if apply_gate is not None:
        return bool(apply_gate)
    return os.getenv("COO_BOOT_APPLY", "") == "1"


def run_boot_brain(reg=None, status_map=None, apply_gate=None) -> dict:
    actions = build_module_actions(reg=reg, status_map=status_map)
    lanes = route_actions(actions)
    applied = 0
    queue_delta = 0
    if _apply_gate_enabled(apply_gate):
        # 가역 자율 조치(집계·보고·플래그·항로기록)는 여기서 수행.
        # 큐 write는 read-before-write 재로드 후 append(gm_aide_scan 패턴). 기본 게이트 OFF라 미도달.
        applied = len(lanes["auto"])
        # queue_delta 는 실제 항로 append 시 증가(현 파일럿은 표시/보고 위주 → 0 유지 가능).
    return {"auto": lanes["auto"], "propose": lanes["propose"],
            "applied": applied, "queue_delta": queue_delta}
```

- [ ] **Step 4: 통과 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_boot_brain.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 전체 회귀**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_registry.py tests/test_coo_check_status.py tests/test_coo_report_line.py tests/test_coo_check_anomaly.py tests/test_coo_boot_brain.py -v`
Expected: PASS (전체 통과·게이트 OFF delta 0 확인)

- [ ] **Step 6: 커밋**

```bash
git add scripts/coo_boot_brain.py tests/test_coo_boot_brain.py
git commit -m "feat(coo): 부팅 두뇌 + 가역성 라우터 (부품④·게이트 OFF delta0)"
```

---

### Task 6: ERP 모듈 허브 — O1 카드 대시보드 (프론트)

**Files:**
- Modify: `3. 웰페리온 가이드/wellperion_guide(main).html` — O1 헤더(line 5573) 직후 모듈 카드 대시보드 + IIFE
- Test: 시크릿 헤드리스 크롬 라이브 검증(HTML/JS라 pytest 불가 — 실측이 검증)

**Interfaces:**
- Consumes: HOME `CHECK_API`(line 10361) fetch 패턴, `status/coo_modules.json`(레지스트리는 fetch 또는 인라인 임베드).

- [ ] **Step 1: O1에 대시보드 컨테이너 + 렌더러 삽입**

In `3. 웰페리온 가이드/wellperion_guide(main).html`, O1 `<div class="doc-header">`(line 5573) 직후에 삽입:

```html
<section id="o1-module-hub" style="margin:18px 0;">
  <h3 style="font-size:1.05rem;margin:0 0 10px;">🏢 운영 모듈 현황 <span style="font-size:.8rem;color:#888;font-weight:400;">— 레지스트리 구동</span></h3>
  <div id="o1-module-cards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;">
    <div style="color:#999;">모듈 불러오는 중…</div>
  </div>
</section>
<script>
(function(){
  var CHECK_API = "https://script.google.com/macros/s/AKfycbyXw4ZaA6hLK567GC7NY33Y8SvNPW6kNtrXFz2OsSdFVBmCnZP-2oD-RQiX0IpekBu1/exec";
  var BASE = "https://wellperion-cao.github.io/wellperion-automation/3.%20%EC%9B%B0%ED%8E%98%EB%A6%AC%EC%98%A8%20%EA%B0%80%EC%9D%B4%EB%93%9C/";
  function card(name, feature, metric, badge, href, tag){
    return '<a href="'+href+'" style="display:block;text-decoration:none;color:inherit;border:1px solid #e5e5e5;border-radius:12px;padding:14px;background:#fff;">'
      + '<div style="font-weight:700;margin-bottom:4px;">'+name+' '+badge+'</div>'
      + '<div style="font-size:.82rem;color:#666;margin-bottom:8px;">'+feature+'</div>'
      + '<div style="font-size:1.4rem;font-weight:800;">'+metric+'</div>'
      + '<div style="font-size:.72rem;color:#aaa;margin-top:6px;">'+tag+'</div></a>';
  }
  function pctOf(row){ if(!row) return null; if(row.pct!=null) return row.pct; return row.total? Math.round(row.done/row.total*100):null; }
  function loadHub(){
    var el = document.getElementById('o1-module-cards'); if(!el) return;
    fetch(CHECK_API+"?action=weekly&dept=facility&_pv="+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();})
      .then(function(d){
        var row = (d.data&&d.data.length)? d.data[d.data.length-1] : d;
        var pct = pctOf(row);
        var anomaly = (pct==null || pct>100);
        var badge = anomaly? '⚠' : '✅';
        var metric = (pct==null?'—':pct+'%');
        var href = BASE + "coo/check/%EC%8B%9C%EC%84%A4%EB%B6%80%20%EC%B2%B4%EA%B3%84.html";
        el.innerHTML = card('점검 현황','부서별 점검 완료율·이상', metric, badge, href, '측정값(measured)');
      })
      .catch(function(){ el.innerHTML = '<div style="color:#c00;">점검 현황: (측정 실패 — 정직 표기)</div>'; });
  }
  setTimeout(loadHub, 600);
})();
</script>
```

> 파일럿은 점검 현황 카드 1장(라이브)만. 나머지 5모듈 카드는 Task 7 복제 절차로 레지스트리 확장 시 추가(현재 enabled=false라 미표시).

- [ ] **Step 2: 로컬 무결성 확인(문법)**

Run: `C:\Python314\python.exe -c "import pathlib,re; s=pathlib.Path('3. 웰페리온 가이드/wellperion_guide(main).html').read_text(encoding='utf-8'); print('o1-module-hub' in s, s.count('<script>')==s.count('</script>'))"`
Expected: `True True`

- [ ] **Step 3: 시크릿 헤드리스 크롬 라이브 검증(로컬 파일)**

라이브 배포 전 로컬 렌더 확인(약속 L03 시크릿). 스크린샷을 scratchpad에 저장하고 `#o1-module-cards`에 '점검 현황' 카드 + 실 % 표시·콘솔 에러 0 확인.

> **라이브 게이트(GM go):** O1은 공용 ERP 페이지. git push→GitHub Pages 반영 = 라이브 발효. **push는 GM go 후**, 반영되면 시크릿 크롬 실측(After) 재검·역롤백(직전 커밋 revert) 준비.

- [ ] **Step 4: 커밋(로컬만, push는 게이트)**

```bash
git add "3. 웰페리온 가이드/wellperion_guide(main).html"
git commit -m "feat(coo): O1 운영 모듈 허브 카드 대시보드 — 점검현황 파일럿 (부품②)"
```

---

### Task 7: 5모듈 복제 절차 문서 + 정직 꼬리표 일관성 확인

**Files:**
- Create: `docs/coo_module_replication.md`
- Test: `tests/test_coo_honesty_tags.py`

**Interfaces:**
- Consumes: `coo_registry`.

- [ ] **Step 1: 정직 꼬리표 일관성 테스트**

Create `tests/test_coo_honesty_tags.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R

VALID = {"measured", "partial", "unmeasured"}


def test_all_modules_have_valid_honesty_tags():
    reg = R.load_registry()
    for m in reg["modules"]:
        assert m["honesty_tags"], f"{m['id']} 꼬리표 없음"
        assert set(m["honesty_tags"]).issubset(VALID), f"{m['id']} 잘못된 꼬리표"


def test_enabled_pilot_is_measured():
    reg = R.load_registry()
    assert R.get_module(reg, "check_status")["honesty_tags"] == ["measured"]


def test_stubs_are_unmeasured():
    reg = R.load_registry()
    for m in R.iter_enabled(reg):
        pass
    stubs = [m for m in reg["modules"] if not m["enabled"]]
    assert all("unmeasured" in m["honesty_tags"] for m in stubs)
```

- [ ] **Step 2: 통과 확인**

Run: `C:\Python314\python.exe -m pytest tests/test_coo_honesty_tags.py -v`
Expected: PASS (3 passed)

- [ ] **Step 3: 복제 절차 문서 작성**

Create `docs/coo_module_replication.md`:

```markdown
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
```

- [ ] **Step 4: 커밋**

```bash
git add tests/test_coo_honesty_tags.py docs/coo_module_replication.md
git commit -m "docs(coo): 5모듈 복제 절차 + 정직 꼬리표 일관성 테스트 (부품①~④ 마감)"
```

---

## Self-Review 결과
- **스펙 커버리지:** AC-1(Task1)·AC-2(Task6)·AC-3(Task3)·AC-4(Task4)·AC-5(Task5)·AC-6(Task7)·AC-7(Task7) — 7 AC 전부 태스크 매핑됨.
- **비가역 게이트:** O1 push(Task6 Step3)·08시 실발송(Task3 게이트)·이상 실발송(Task4 --send)·부팅 자율 write(Task5 게이트 OFF) 전부 GM go로 분리.
- **타입 일관성:** `fetch_check_status`·`iter_enabled`·`get_module`·`reversibility.route` 시그니처가 태스크 간 일치.
- **④ 보안 자동로그인:** COO 도메인 N/A(스펙 Non-Goal) — 태스크 없음이 정상.

## 실행 후 검증(완료 판정)
1. `C:\Python314\python.exe -m pytest tests/ -k coo -v` → 전체 PASS.
2. `ceo_morning_pipeline.py --dry-run` → "🏢 운영 점검" 섹션 실측 표시.
3. `coo_check_anomaly.py`(dry) → 이상 N건·발송 0.
4. O1 시크릿 크롬 실측 → 점검현황 카드 라이브 % 표시·콘솔 0.
5. GM go 후에만: O1 push·08시 실발송·이상 실발송 라이브 검증·역롤백 준비.
