# -*- coding: utf-8 -*-
"""
schedule_inventory.py — 예약 스케줄 인벤토리 저장소 박제 (배9640 phase1)
-------------------------------------------------------------------
조사 근거: docs/superpowers/specs/2026-07-23-scheduling-unification-audit.md
  Windows 작업 스케줄러(33개)와 apscheduler(telegram_bot/daily_scheduler.py, 22개)가
  2계층으로 갈라져 있고, Windows 등록은 Register-ScheduledTask 1회 실행이라 git에 흔적이
  안 남는다 — PC가 초기화되면 복원 불가. 통합의 첫 걸음 = 스케줄 현황을 저장소 파일로
  박아 눈에 보이게 하는 것(이 스크립트).

읽기 전용. 라이브 예약작업·apscheduler 잡을 생성·수정·삭제하지 않는다
(PowerShell 은 Get-ScheduledTask/Get-ScheduledTaskInfo/Export-ScheduledTask 만 사용).

출력: status/schedule_inventory.json
  - 매 실행마다 바뀌는 타임스탬프를 넣지 않는다(멱등 — 내용 불변이면 파일도 불변).
  - 정렬 고정: windows_tasks=이름 오름차순, apscheduler_jobs=id 오름차순.

CLI:
  python scripts/schedule_inventory.py            파일 갱신
  python scripts/schedule_inventory.py --check    파일을 쓰지 않고 현재 실태와 저장 파일이
                                                    다른지만 비교(다르면 차이 출력 + exit 1)

★2026-08-05(시토, 흩어진 파이프라인 통합 조사) — status/schedule.json 을 이 파일의
  windows_tasks 인벤토리로부터 자동 생성하는 export 모드는 **만들지 않기로 결론**냈다
  (배39 잔여분 조사). 이유: schedule.json 소비자 telegram_bot/pre_task_notifier.py 가
  필요로 하는 clevel 필드를 Windows 작업 이름만으로 신뢰성 있게 못 뽑는다 — 실측
  32건 중 이름에 역할 토큰(CEO/CMO/COO/CPO)이 든 건 7건뿐이고, 나머지는 토큰이
  없거나(AI-Education-Weekly 등) 이름이 오히려 오도한다("Ops-Morning-Digest"는
  이름만 보면 COO 같지만 실제 소유는 CTO — module_registry.json cto-ops-morning-digest
  로 확인). 잘못된 clevel 로 자동 생성하면 담당자 오표기 알림이 나가는데, 이는
  2026-07-30 배39 가 막았던 "유령 알림"보다 나은 실패가 아니다. 그래서 원래 계획한
  "Windows=원천, schedule.json=생성물" 전환은 보류하고, 더 작은 개입만 유지한다:
  check_declared_vs_actual() 의 curated mapping(요일·시각만 대조, clevel 은 안 봄)을
  그대로 둔다. schedule.json 자체는 여전히 사람이 큐레이션하는 파일이다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEDULER_SRC = ROOT / "telegram_bot" / "daily_scheduler.py"
OUT_PATH = ROOT / "status" / "schedule_inventory.json"
SCHEDULE_JSON_PATH = ROOT / "status" / "schedule.json"
NOTIFY_REGISTRY_PATH = ROOT / "status" / "notify_registry.json"

# apscheduler 로 넘어가는 즉시(--test 전용) 잡 — 무인자 vbs 실행에서는 비활성.
# 조사 문서(표2 각주)와 동일 기준으로 인벤토리에서도 제외.
_EXCLUDED_JOB_IDS = {"test_hourly"}


# ── PowerShell: Windows 예약작업 수집(읽기 전용) ────────────────────────────
_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
# 2026-07-30 배39: 'Welperion'(L 한 개 오타)로 등록된 작업 2개(Auto-Shutdown-2330·
# Ep3-Review-Reminder-0701-1000)가 'Wellperion*' 단일 패턴에서 빠져 집계가 33→실제
# 35건과 어긋났었다(실측 확인). 이름 자체는 안 고친다(재등록은 별건) — 집계만 양쪽 다.
# ★-TaskName 파라미터는 리프 이름만 보고 폴더(TaskPath)는 안 본다 — Auto-Shutdown-2330
# 은 TaskName 자체엔 'Welperion'이 없고 TaskPath('\Welperion\')에만 있어 -TaskName
# 필터로는 두 스펠링을 다 줘도 여전히 빠진다. 그래서 전체 조회 후 이름+경로 양쪽을
# 정규식으로 본다(대소문자 무관·L 한 개도 매칭).
$tasks = @(Get-ScheduledTask | Where-Object { $_.TaskName -match '(?i)wel.?perion' -or $_.TaskPath -match '(?i)wel.?perion' })
$out = foreach ($t in $tasks) {
    try { $info = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath } catch { $info = $null }
    try { $xml = Export-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath } catch { $xml = '' }
    [PSCustomObject]@{
        name = $t.TaskName
        state = $t.State.ToString()
        last_run = if ($info -and $info.LastRunTime) { $info.LastRunTime.ToString('o') } else { $null }
        last_result = if ($info) { $info.LastTaskResult } else { $null }
        next_run = if ($info -and $info.NextRunTime) { $info.NextRunTime.ToString('o') } else { $null }
        xml = $xml
    }
}
ConvertTo-Json -InputObject $out -Depth 6
"""


def _run_powershell(script: str, timeout: int = 90) -> str:
    """PowerShell -Command 실행 → 표준출력 텍스트. UTF-8 우선, 실패 시 cp949 폴백."""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, timeout=timeout,
    )
    raw = r.stdout or b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    return text.strip()


def collect_windows_tasks(timeout: int = 90) -> list[dict]:
    """Get-ScheduledTask 로 Wellperion* 작업 전수 조회 → 정규화 리스트. 읽기 전용."""
    text = _run_powershell(_PS_SCRIPT, timeout=timeout)
    if not text:
        raise RuntimeError("Get-ScheduledTask PowerShell 조회 실패(빈 출력)")
    return parse_windows_tasks_json(text)


# ── Windows 작업 XML(Export-ScheduledTask) → triggers/actions/enabled 파싱 ──
def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _xml_find_text(elem, path_tags):
    cur = elem
    for tag in path_tags:
        nxt = None
        for child in cur:
            if _local(child.tag) == tag:
                nxt = child
                break
        if nxt is None:
            return None
        cur = nxt
    return cur.text


def _parse_task_xml(xml_text: str) -> dict:
    if not xml_text or not xml_text.strip():
        return {"triggers": [], "actions": [], "enabled": None}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"triggers": [], "actions": [], "enabled": None, "xml_parse_failed": True}

    triggers = []
    for container in root:
        if _local(container.tag) != "Triggers":
            continue
        for trig in container:
            t = {"type": _local(trig.tag)}
            start = _xml_find_text(trig, ["StartBoundary"])
            if start:
                t["start_boundary"] = start
            interval = _xml_find_text(trig, ["Repetition", "Interval"])
            if interval:
                t["repetition_interval"] = interval
            days_interval = _xml_find_text(trig, ["ScheduleByDay", "DaysInterval"])
            if days_interval:
                t["days_interval"] = days_interval
            for child in trig:
                if _local(child.tag) == "ScheduleByWeek":
                    for wchild in child:
                        if _local(wchild.tag) == "DaysOfWeek":
                            t["days_of_week"] = [_local(d.tag) for d in wchild]
                        elif _local(wchild.tag) == "WeeksInterval":
                            t["weeks_interval"] = wchild.text
                elif _local(child.tag) == "ScheduleByMonth":
                    days = [d.text for d in child if _local(d.tag) == "DaysOfMonth" for d in d]
                    if days:
                        t["days_of_month"] = days
            triggers.append(t)

    actions = []
    for container in root:
        if _local(container.tag) != "Actions":
            continue
        for act in container:
            if _local(act.tag) != "Exec":
                continue
            actions.append({
                "execute": _xml_find_text(act, ["Command"]),
                "arguments": _xml_find_text(act, ["Arguments"]),
            })

    enabled = None
    for container in root:
        if _local(container.tag) != "Settings":
            continue
        enabled_text = _xml_find_text(container, ["Enabled"])
        if enabled_text is not None:
            enabled = enabled_text.strip().lower() == "true"

    return {"triggers": triggers, "actions": actions, "enabled": enabled}


def parse_windows_tasks_json(raw_json: str) -> list[dict]:
    """PS ConvertTo-Json 결과(문자열) → 정규화된 작업 리스트(이름 오름차순 고정)."""
    data = json.loads(raw_json)
    if isinstance(data, dict):
        data = [data]
    tasks = []
    for item in data:
        parsed = _parse_task_xml(item.get("xml") or "")
        xml_enabled = parsed.get("enabled")
        if xml_enabled is None:
            # Windows 는 Enabled=true(기본값)일 때 <Enabled> 자체를 XML 에서 생략한다 —
            # 그럴 땐 실시간 State(작업 스케줄러가 실제로 판정한 값)로 유추.
            state = str(item.get("state") or "").strip().lower()
            xml_enabled = state != "disabled" if state else None
        entry = {
            "name": item.get("name"),
            "state": item.get("state"),
            "enabled": xml_enabled,
            "triggers": parsed.get("triggers", []),
            "actions": parsed.get("actions", []),
        }
        # ★ last_run·last_result·next_run 은 **일부러 저장하지 않는다.**
        # 이 파일의 목적은 "무엇이 몇 시에 도는가"(정의)를 저장소에 박아 PC 사고 시
        # 복원 가능하게 하는 것이다. 실행 시각은 매 순간 바뀌므로 넣으면 파일이 계속
        # 달라져 자동 커밋 소음이 된다(3분 주기 작업 하나만 있어도 즉시 깨짐 — 실측).
        # 실행 상태는 예약작업 화면·러너 로그에서 보면 되고, 여기선 정의만 다룬다.
        if parsed.get("xml_parse_failed"):
            entry["parse_failed"] = True
        tasks.append(entry)
    tasks.sort(key=lambda t: (t.get("name") or ""))
    return tasks


# ── daily_scheduler.py 정적 파싱(임포트/기동 없음) — scheduler.add_job(...) 추출 ──
def _find_matching_paren(text: str, open_idx: int) -> int:
    """text[open_idx] == '('. 짝이 맞는 ')' 인덱스를 문자열 리터럴 인식하며 찾는다."""
    depth = 0
    in_str = None
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in ("\"", "'"):
                in_str = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError("unmatched paren")


def _split_top_level(s: str, sep: str = ",") -> list[str]:
    """괄호/대괄호/중괄호 깊이 0·문자열 밖에서만 sep 로 분리."""
    parts = []
    depth = 0
    in_str = None
    start = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in ("\"", "'"):
                in_str = c
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == sep and depth == 0:
                parts.append(s[start:i])
                start = i + 1
        i += 1
    tail = s[start:].strip()
    if tail:
        parts.append(tail)
    return [p.strip() for p in parts]


def _split_kv(part: str):
    """최상위(깊이0) '=' 로 key/value 분리. 없으면 (None, part) — 위치 인자."""
    depth = 0
    in_str = None
    i = 0
    n = len(part)
    while i < n:
        c = part[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in ("\"", "'"):
                in_str = c
            elif c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == "=" and depth == 0:
                if i + 1 < n and part[i + 1] == "=":
                    i += 2
                    continue
                return part[:i].strip(), part[i + 1:].strip()
        i += 1
    return None, part.strip()


def _parse_literal(text: str):
    t = text.strip()
    if len(t) >= 2 and ((t[0] == '"' and t[-1] == '"') or (t[0] == "'" and t[-1] == "'")):
        return t[1:-1]
    if t == "True":
        return True
    if t == "False":
        return False
    if t == "None":
        return None
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t  # 원문 그대로(식별자·표현식 등 미해석)


def _substitute(text: str, subs: dict) -> str:
    """텍스트가 정확히 루프 변수 하나면 값으로 치환한 원문(재-parse_literal 대상)을 만든다."""
    t = text.strip()
    if t in subs:
        val = subs[t]
        return f'"{val}"' if isinstance(val, str) else str(val)
    return text


def _substitute_fstring(text: str, subs: dict):
    """f"...{var}..." 형태 id 를 subs 로 치환. 반환: (결과문자열, parse_failed)"""
    t = text.strip()
    m = re.match(r'^f(["\'])(.*)\1$', t, re.DOTALL)
    if not m:
        return _parse_literal(t), False
    _, body = m.groups()
    failed = {"v": False}

    def repl(mo):
        var = mo.group(1)
        if var in subs:
            return str(subs[var])
        failed["v"] = True
        return mo.group(0)

    result = re.sub(r"\{(\w+)\}", repl, body)
    return result, failed["v"]


def _substitute_args_list(text: str, subs: dict):
    t = text.strip()
    if not (t.startswith("[") and t.endswith("]")):
        return _parse_literal(t)
    inner = t[1:-1]
    items = []
    for p in _split_top_level(inner):
        if not p:
            continue
        items.append(_parse_literal(_substitute(p, subs)))
    return items


def _parse_trigger(value_text: str, subs: dict) -> dict:
    v = value_text.strip()
    m = re.match(r"^(\w+)\((.*)\)$", v, re.DOTALL)
    if not m:
        return {"type": _parse_literal(v), "params": {}}
    ttype, inner = m.group(1), m.group(2)
    params = {}
    for p in _split_top_level(inner):
        if not p:
            continue
        k, val = _split_kv(p)
        if k is None:
            continue
        params[k] = _parse_literal(_substitute(val, subs))
    return {"type": ttype, "params": params}


def _detect_loop_context(source: str, call_start: int):
    """add_job(...) 호출을 감싸는 'for x, (a, b) in D.items():' 를 찾는다. 없으면 None."""
    line_start = source.rfind("\n", 0, call_start) + 1
    prefix = source[line_start:call_start]
    call_indent = len(prefix) - len(prefix.lstrip())
    for line in reversed(source[:line_start].splitlines()):
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        if indent < call_indent:
            m = re.match(r"for\s+(\w+)\s*,\s*\(([^)]+)\)\s+in\s+(\w+)\.items\(\)\s*:", stripped)
            if m:
                loop_var = m.group(1)
                tuple_vars = [v.strip() for v in m.group(2).split(",")]
                dict_name = m.group(3)
                return loop_var, tuple_vars, dict_name
            return None
    return None


def _extract_dict_literal(source: str, dict_name: str):
    """`{dict_name} = { "key": (a, b, ...), ... }` 형태 딕셔너리를 [(key, [vals...]), ...] 로."""
    m = re.search(rf"{re.escape(dict_name)}\s*=\s*\{{(.*?)\n\s*\}}", source, re.DOTALL)
    if not m:
        return None
    body = m.group(1)
    entries = []
    for em in re.finditer(r'"([^"]+)"\s*:\s*\(([^)]*)\)', body):
        key = em.group(1)
        vals = [_parse_literal(v) for v in _split_top_level(em.group(2))]
        entries.append((key, vals))
    return entries or None


def parse_apscheduler_jobs(source: str) -> list[dict]:
    """telegram_bot/daily_scheduler.py 소스 텍스트(정적) → 잡 리스트(id 오름차순).
    임포트·기동 없음 — 순수 텍스트 파싱. 못 뽑은 항목은 parse_failed=True 로 남긴다."""
    jobs = []
    for idx, m in enumerate(re.finditer(r"scheduler\.add_job\(", source)):
        open_idx = m.end() - 1
        try:
            close_idx = _find_matching_paren(source, open_idx)
        except ValueError:
            continue
        block = source[open_idx + 1:close_idx]
        parts = _split_top_level(block)
        if not parts:
            continue
        func_part = parts[0].strip()
        kv = {}
        for p in parts[1:]:
            k, v = _split_kv(p)
            if k:
                kv[k] = v

        loop_ctx = _detect_loop_context(source, m.start())
        is_loop = loop_ctx is not None
        if is_loop:
            loop_var, tuple_vars, dict_name = loop_ctx
            dict_entries = _extract_dict_literal(source, dict_name)
            if dict_entries:
                entries_subs = []
                for key, vals in dict_entries:
                    subs = {loop_var: key}
                    for var_name, val in zip(tuple_vars, vals):
                        subs[var_name] = val
                    entries_subs.append(subs)
            else:
                entries_subs = [{}]  # 딕셔널 리터럴 추출 실패 — subs 비움(parse_failed 유도)
        else:
            entries_subs = [{}]

        for subs in entries_subs:
            job: dict = {"func": func_part}
            parse_failed = is_loop and not subs

            if "id" in kv:
                if is_loop:
                    id_val, failed = _substitute_fstring(kv["id"], subs)
                    parse_failed = parse_failed or failed
                else:
                    id_val = _parse_literal(kv["id"])
                job["id"] = id_val
            else:
                job["id"] = f"__unknown_{idx}__"
                parse_failed = True

            if "trigger" in kv:
                job["trigger"] = _parse_trigger(kv["trigger"], subs)
                # trigger 밖에 놓인 예비 kwarg(예: 문자열 trigger="interval" + hours=1) 흡수
                for extra_key in ("hours", "minutes", "days", "weeks", "seconds"):
                    if extra_key in kv and extra_key not in job["trigger"]["params"]:
                        job["trigger"]["params"][extra_key] = _parse_literal(kv[extra_key])
            else:
                job["trigger"] = None

            if "args" in kv:
                job["call_args"] = _substitute_args_list(kv["args"], subs)

            for meta_key in ("misfire_grace_time", "coalesce"):
                if meta_key in kv:
                    job[meta_key] = _parse_literal(kv[meta_key])

            job["run_on_start"] = "next_run_time" in kv and "datetime.now()" in kv["next_run_time"]

            if job.get("id") in _EXCLUDED_JOB_IDS:
                continue
            if parse_failed:
                job["parse_failed"] = True
            jobs.append(job)

    jobs.sort(key=lambda j: (j.get("id") or ""))
    return jobs


def collect_apscheduler_jobs() -> list[dict]:
    text = SCHEDULER_SRC.read_text(encoding="utf-8")
    return parse_apscheduler_jobs(text)


# ── 인벤토리 조립 / 저장 / --check ──────────────────────────────────────────
def build_inventory() -> dict:
    windows_tasks = collect_windows_tasks()
    apscheduler_jobs = collect_apscheduler_jobs()
    return {
        "generated_at_note": (
            "실행마다 바뀌는 타임스탬프를 의도적으로 넣지 않음(멱등) — "
            "내용이 안 바뀌면 파일도 안 바뀐다. 최신 실행 시각이 필요하면 "
            "status/heartbeats 등 별도 SSOT 참고."
        ),
        "windows_tasks": windows_tasks,
        "apscheduler_jobs": apscheduler_jobs,
        "counts": {"windows": len(windows_tasks), "apscheduler": len(apscheduler_jobs)},
    }


def write_inventory(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_diff(old: dict, new: dict) -> None:
    old_c, new_c = old.get("counts", {}), new.get("counts", {})
    if old_c != new_c:
        print(f"  counts: {old_c} -> {new_c}")

    old_names = {t.get("name") for t in old.get("windows_tasks", [])}
    new_names = {t.get("name") for t in new.get("windows_tasks", [])}
    if new_names - old_names:
        print(f"  windows_tasks 추가: {sorted(new_names - old_names)}")
    if old_names - new_names:
        print(f"  windows_tasks 제거: {sorted(old_names - new_names)}")

    old_by_name = {t.get("name"): t for t in old.get("windows_tasks", [])}
    new_by_name = {t.get("name"): t for t in new.get("windows_tasks", [])}
    for nm in sorted(old_names & new_names):
        if old_by_name[nm] != new_by_name[nm]:
            print(f"  windows_tasks[{nm}] 내용 변경")

    old_ids = {j.get("id") for j in old.get("apscheduler_jobs", [])}
    new_ids = {j.get("id") for j in new.get("apscheduler_jobs", [])}
    if new_ids - old_ids:
        print(f"  apscheduler_jobs 추가: {sorted(new_ids - old_ids)}")
    if old_ids - new_ids:
        print(f"  apscheduler_jobs 제거: {sorted(old_ids - new_ids)}")

    old_by_id = {j.get("id"): j for j in old.get("apscheduler_jobs", [])}
    new_by_id = {j.get("id"): j for j in new.get("apscheduler_jobs", [])}
    for jid in sorted(old_ids & new_ids):
        if old_by_id[jid] != new_by_id[jid]:
            print(f"  apscheduler_jobs[{jid}] 내용 변경")


# ── 선언(status/schedule.json·notify_registry.json) ↔ 실제(Windows 예약작업) 대조 ──
# 2026-07-30 배202 ⓿ 팀리드 지시 — 같은 부류(문서=일요일, 실제=월요일 등 요일 드리프트)가
# 사람 눈으로 세 번 잡혔다(모듈 주간·AI 자기학습·재발방지 회귀감시). 매번 사람이 찾는 구조라
# 계속 새므로 기존 --check 관문에 흡수한다(새 파일·새 예약작업 0 · 약속 L21).
# 설계: 매칭은 명시적 표(curated mapping)로만 한다 — 이름 유사도로 자동매칭하면 헛경보가
# 나서(팀리드 지시: 헛경보 확인 필수) 오히려 신뢰를 깎는다. 새 정기 발신이 생기면 이 표에
# 한 줄 추가하는 게 유지보수 방식이다.
_KOREAN_WEEKDAY = {
    "일": "Sunday", "월": "Monday", "화": "Tuesday", "수": "Wednesday",
    "목": "Thursday", "금": "Friday", "토": "Saturday",
}

# (표시 라벨, 대조 대상 windows 작업명) — schedule.json 은 sid, notify_registry.json 은 id 로 조회.
_SCHEDULE_JSON_MAP = {
    "cto-2026-06-23-ai-education-auto-learner": "Wellperion-AI-Education-Weekly",
    "cto-2026-06-23-ai-learning-proposer": "Wellperion-AI-Learning-Proposer-Weekly",
    "cto-regression-monitor-0915": None,  # 독립 예약작업 없음(알려진 편승 사례) — 대조불가로 남김
}
_NOTIFY_REGISTRY_MAP = {
    "win-0730-ig-review": "Wellperion-IG-Series-Produce-0730",
    "win-0730-ops-digest": "Wellperion-Ops-Morning-Digest-0730",
    "win-0800-ceo": "Wellperion-CEO-Morning-Brief-0800-Live",
    "win-0845-lseries": "Wellperion-LSeries-Daily-Card-0845",
    "win-0910-module-daily": "Wellperion-Module-Report-Daily",
    "win-0930-kakao-sales": "Wellperion-Kakao-Sales-Report-0930",
    "win-1300-healthcheck": "Wellperion-Telegram-HealthCheck-1300",
    "win-2100-cmo-daily": "Wellperion-CMO-Daily-Marketing-2100",
    "win-weekly-mon0900-marketing": "Wellperion-CMO-Weekly-Marketing-Feedback",
    "win-weekly-sun0900-education": "Wellperion-AI-Education-Weekly",
    "win-weekly-sun1030-selfreview": "Wellperion-Weekly-Self-Review-Sunday",
    "win-monthly-1st0900-marketing": "Wellperion-CMO-Monthly-Report",
    "win-monthly-1st0900-checksummary": "Wellperion-MonthlyCheckReport-0900-D1",
    "win-monthly-1st0900-opsplan": "Wellperion-MonthlyOps-Start-0900",
    "win-monthly-lastday2100-opsclose": "Wellperion-MonthlyOps-End-2100",
    "win-monthly-4thmon1000-memberexpiry": "Wellperion-CPO-MemberExpiry-Monthly-4thMon-1000",
}


def _parse_declared_text(text: str):
    """자유서술 한글 일정 텍스트 → (요일영문_또는_None, 'HH:MM'_또는_None). 모르면 (None, None)."""
    if not text:
        return (None, None)
    weekday = None
    m = re.search(r"(매주\s*)?([일월화수목금토])요일", text)
    if not m:
        m = re.search(r"(?:^|[\s/·])([일월화수목금토])(?:\s|$)", text)
    if m:
        weekday = _KOREAN_WEEKDAY.get(m.group(m.lastindex))
    tm = re.search(r"(\d{1,2}):(\d{2})", text)
    hhmm = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None
    return (weekday, hhmm)


def _actual_from_task(task: dict):
    """windows_tasks 항목(triggers 포함) → (요일영문_또는_None, 'HH:MM'_또는_None). CalendarTrigger 1개 기준."""
    for t in task.get("triggers", []):
        if t.get("type") != "CalendarTrigger":
            continue
        days = t.get("days_of_week") or []
        weekday = days[0] if len(days) == 1 else None  # 복수요일·월간패턴은 요일단정 안 함(대조불가로 자연 처리)
        start = t.get("start_boundary") or ""
        m = re.search(r"T(\d{2}):(\d{2})", start)
        hhmm = f"{m.group(1)}:{m.group(2)}" if m else None
        return (weekday, hhmm)
    return (None, None)


def check_declared_vs_actual(windows_tasks: list[dict]) -> dict:
    """선언(schedule.json·notify_registry.json) ↔ 실제(windows_tasks) 요일·시각 대조.
    반환: {'rows': [...], 'ok': N, 'drift': M, 'unmatched': K}. 매칭 실패는 어긋남과 절대 안 섞는다."""
    by_name = {t.get("name"): t for t in windows_tasks}
    rows = []

    def _eval(label, declared_text, task_name):
        if not task_name or task_name not in by_name:
            rows.append((label, declared_text or "(선언값 없음)", "—", "대조불가"))
            return
        dweek, dtime = _parse_declared_text(declared_text or "")
        aweek, atime = _actual_from_task(by_name[task_name])
        if aweek is None and atime is None:
            rows.append((label, f"{dweek or '?'} {dtime or '?'}", "(요일·시각 추출 불가)", "대조불가"))
            return
        declared_s = f"{dweek or '?'} {dtime or '?'}"
        actual_s = f"{aweek or '?'} {atime or '?'}"
        mismatch = (dweek and aweek and dweek != aweek) or (dtime and atime and dtime != atime)
        rows.append((label, declared_s, actual_s, "어긋남" if mismatch else "정상"))

    if SCHEDULE_JSON_PATH.exists():
        for item in json.loads(SCHEDULE_JSON_PATH.read_text(encoding="utf-8")):
            sid = item.get("sid")
            if sid in _SCHEDULE_JSON_MAP:
                _eval(item.get("name") or sid, item.get("exec_time"), _SCHEDULE_JSON_MAP[sid])

    if NOTIFY_REGISTRY_PATH.exists():
        reg = json.loads(NOTIFY_REGISTRY_PATH.read_text(encoding="utf-8"))
        for item in reg.get("items", []):
            iid = item.get("id")
            if iid in _NOTIFY_REGISTRY_MAP:
                _eval(iid, item.get("when"), _NOTIFY_REGISTRY_MAP[iid])

    ok = sum(1 for r in rows if r[3] == "정상")
    drift = sum(1 for r in rows if r[3] == "어긋남")
    unmatched = sum(1 for r in rows if r[3] == "대조불가")
    return {"rows": rows, "ok": ok, "drift": drift, "unmatched": unmatched}


def _print_declared_vs_actual(result: dict) -> None:
    print(f"[선언↔실제 대조] 정상 {result['ok']} · 어긋남 {result['drift']} · 대조불가 {result['unmatched']}")
    for label, declared, actual, verdict in result["rows"]:
        mark = {"정상": "✅", "어긋남": "⚠️", "대조불가": "❔"}.get(verdict, "?")
        print(f"  {mark} {label} | 선언={declared} | 실제={actual} | {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Windows 예약작업 + apscheduler 잡 인벤토리를 status/schedule_inventory.json 으로 "
                     "박제(읽기 전용, 라이브 무변경)."
    )
    ap.add_argument("--check", action="store_true",
                     help="파일을 쓰지 않고 현재 실태와 저장된 파일이 다른지만 비교(다르면 exit 1)")
    args = ap.parse_args()

    data = build_inventory()

    if args.check:
        drift_result = check_declared_vs_actual(data["windows_tasks"])
        _print_declared_vs_actual(drift_result)

        if not OUT_PATH.exists():
            print(f"[check] 기존 인벤토리 없음: {OUT_PATH}")
            sys.exit(1)
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if existing == data:
            print(f"[check] 일치 — windows={data['counts']['windows']} apscheduler={data['counts']['apscheduler']}")
            sys.exit(0)
        print("[check] 불일치 발견:")
        _print_diff(existing, data)
        sys.exit(1)

    write_inventory(OUT_PATH, data)
    print(f"[schedule_inventory] windows={data['counts']['windows']} "
          f"apscheduler={data['counts']['apscheduler']} -> {OUT_PATH}")


if __name__ == "__main__":
    main()
