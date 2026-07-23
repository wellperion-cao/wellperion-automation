# -*- coding: utf-8 -*-
"""schedule_inventory.py 계약 테스트 — PowerShell·파일시스템 전부 격리(라이브 무변경).
검증 대상: scripts/schedule_inventory.py (배9640 phase1 — 스케줄 인벤토리 저장소 박제)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import schedule_inventory as si  # noqa: E402


# ── ① Windows 작업 JSON 파싱 ────────────────────────────────────────────────
_SAMPLE_TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <TimeTrigger>
      <StartBoundary>2026-07-24T09:30:00</StartBoundary>
      <Repetition>
        <Interval>PT3M</Interval>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>C:\\Windows\\System32\\wscript.exe</Command>
      <Arguments>"C:\\Users\\jjky0\\welperion-automation\\launchers\\cpo_inquiry_snapshot_hidden.vbs"</Arguments>
    </Exec>
  </Actions>
  <Settings>
    <Enabled>true</Enabled>
  </Settings>
</Task>
"""


def test_parse_windows_tasks_json_single_task():
    raw = json.dumps({
        "name": "Wellperion-CPO-Inquiry-Snapshot-3min",
        "state": "Ready",
        "last_run": "2026-07-23T10:00:00+09:00",
        "last_result": 0,
        "next_run": "2026-07-23T10:03:00+09:00",
        "xml": _SAMPLE_TASK_XML,
    })
    tasks = si.parse_windows_tasks_json(raw)
    assert len(tasks) == 1
    t = tasks[0]
    assert t["name"] == "Wellperion-CPO-Inquiry-Snapshot-3min"
    assert t["state"] == "Ready"
    assert t["enabled"] is True
    # last_run·last_result·next_run 은 매 실행마다 바뀌어 파일을 계속 흔들므로
    # 일부러 저장하지 않는다(멱등 보장). 정의 필드만 남는다.
    assert "last_result" not in t
    assert "last_run" not in t
    assert "next_run" not in t
    assert t["triggers"] == [{
        "type": "TimeTrigger",
        "start_boundary": "2026-07-24T09:30:00",
        "repetition_interval": "PT3M",
    }]
    assert t["actions"] == [{
        "execute": "C:\\Windows\\System32\\wscript.exe",
        "arguments": '"C:\\Users\\jjky0\\welperion-automation\\launchers\\cpo_inquiry_snapshot_hidden.vbs"',
    }]


def test_parse_windows_tasks_json_single_object_wrapped_as_list():
    # PowerShell ConvertTo-Json 은 항목이 1개면 배열이 아니라 단일 객체를 낼 수 있음 — 방어 확인.
    raw = json.dumps({"name": "OnlyOne", "state": "Ready", "xml": ""})
    tasks = si.parse_windows_tasks_json(raw)
    assert isinstance(tasks, list)
    assert len(tasks) == 1
    assert tasks[0]["name"] == "OnlyOne"
    assert tasks[0]["triggers"] == []
    assert tasks[0]["actions"] == []


def test_parse_windows_tasks_json_enabled_falls_back_to_state_when_xml_omits_it():
    # Windows 는 Enabled=true(기본값)일 때 <Enabled> 자체를 XML 에서 생략한다 — 실측 확인됨.
    xml_no_enabled_elem = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        '<Settings><DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries></Settings>'
        '</Task>'
    )
    raw_ready = json.dumps({"name": "T1", "state": "Ready", "xml": xml_no_enabled_elem})
    assert si.parse_windows_tasks_json(raw_ready)[0]["enabled"] is True

    raw_disabled = json.dumps({"name": "T2", "state": "Disabled", "xml": xml_no_enabled_elem})
    assert si.parse_windows_tasks_json(raw_disabled)[0]["enabled"] is False


def test_parse_windows_tasks_json_sorted_by_name():
    raw = json.dumps([
        {"name": "Wellperion-Zeta", "state": "Ready", "xml": ""},
        {"name": "Wellperion-Alpha", "state": "Ready", "xml": ""},
    ])
    tasks = si.parse_windows_tasks_json(raw)
    assert [t["name"] for t in tasks] == ["Wellperion-Alpha", "Wellperion-Zeta"]


# ── ② daily_scheduler 정적 파싱으로 add_job 잡 추출 ─────────────────────────
_SAMPLE_SCHEDULER_SRC = '''
def main():
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        health_check_bot,
        trigger=IntervalTrigger(minutes=15),
        id="bot_health_check",
        misfire_grace_time=120,
        coalesce=True,
        next_run_time=datetime.now(),
    )

    if args.test:
        scheduler.add_job(
            lambda: run_report(get_test_slot(), test_mode=True),
            trigger="interval",
            hours=1,
            id="test_hourly",
            misfire_grace_time=600,
            next_run_time=datetime.now(),
        )
    else:
        schedule_map = {
            "06": (6, 0),
            "12": (12, 0),
        }
        for slot, (hour, minute) in schedule_map.items():
            scheduler.add_job(
                run_report,
                trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
                args=[slot, False],
                id=f"report_{slot}",
                misfire_grace_time=600,
                coalesce=True,
            )

        nudge_map = {
            "nudge_pm": (17, 0, "pm"),
            "nudge_close": (22, 0, "close"),
        }
        for slot, (hour, minute, shift) in nudge_map.items():
            scheduler.add_job(
                run_nudge,
                trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
                args=[shift],
                id=f"report_{slot}",
                misfire_grace_time=600,
                coalesce=True,
            )
'''


def test_parse_apscheduler_jobs_simple_call():
    jobs = si.parse_apscheduler_jobs(_SAMPLE_SCHEDULER_SRC)
    by_id = {j["id"]: j for j in jobs}
    assert "bot_health_check" in by_id
    j = by_id["bot_health_check"]
    assert j["func"] == "health_check_bot"
    assert j["trigger"] == {"type": "IntervalTrigger", "params": {"minutes": 15}}
    assert j["misfire_grace_time"] == 120
    assert j["coalesce"] is True
    assert j["run_on_start"] is True


def test_parse_apscheduler_jobs_excludes_test_hourly():
    jobs = si.parse_apscheduler_jobs(_SAMPLE_SCHEDULER_SRC)
    assert "test_hourly" not in {j["id"] for j in jobs}


def test_parse_apscheduler_jobs_expands_schedule_map_loop():
    jobs = si.parse_apscheduler_jobs(_SAMPLE_SCHEDULER_SRC)
    by_id = {j["id"]: j for j in jobs}
    assert "report_06" in by_id and "report_12" in by_id
    j06 = by_id["report_06"]
    assert j06["func"] == "run_report"
    assert j06["trigger"] == {"type": "CronTrigger", "params": {"hour": 6, "minute": 0, "timezone": "Asia/Seoul"}}
    assert j06["call_args"] == ["06", False]
    assert not j06.get("parse_failed")

    j12 = by_id["report_12"]
    assert j12["trigger"]["params"]["hour"] == 12


def test_parse_apscheduler_jobs_expands_nudge_map_loop_with_3tuple():
    jobs = si.parse_apscheduler_jobs(_SAMPLE_SCHEDULER_SRC)
    by_id = {j["id"]: j for j in jobs}
    assert "report_nudge_pm" in by_id and "report_nudge_close" in by_id
    jp = by_id["report_nudge_pm"]
    assert jp["func"] == "run_nudge"
    assert jp["trigger"]["params"] == {"hour": 17, "minute": 0, "timezone": "Asia/Seoul"}
    assert jp["call_args"] == ["pm"]

    jc = by_id["report_nudge_close"]
    assert jc["call_args"] == ["close"]
    assert jc["trigger"]["params"]["hour"] == 22


def test_parse_apscheduler_jobs_total_count_excludes_test_only():
    jobs = si.parse_apscheduler_jobs(_SAMPLE_SCHEDULER_SRC)
    # bot_health_check(1) + report_06/12(2) + report_nudge_pm/close(2) = 5, test_hourly 제외
    assert len(jobs) == 5


# ── ③ 멱등: 같은 입력 두 번 → 파일 내용 동일 ─────────────────────────────────
def test_write_inventory_idempotent(tmp_path, monkeypatch):
    fixed_windows = [{"name": "Wellperion-A", "state": "Ready", "enabled": True,
                       "triggers": [], "actions": [], "last_run": None,
                       "last_result": 0, "next_run": None}]
    fixed_jobs = [{"func": "f", "id": "job_a", "trigger": {"type": "IntervalTrigger", "params": {"minutes": 5}},
                   "run_on_start": False}]

    monkeypatch.setattr(si, "collect_windows_tasks", lambda: fixed_windows)
    monkeypatch.setattr(si, "collect_apscheduler_jobs", lambda: fixed_jobs)

    out_path = tmp_path / "schedule_inventory.json"

    data1 = si.build_inventory()
    si.write_inventory(out_path, data1)
    content1 = out_path.read_bytes()

    data2 = si.build_inventory()
    si.write_inventory(out_path, data2)
    content2 = out_path.read_bytes()

    assert content1 == content2
    assert data1 == data2


# ── ④ --check 가 차이 있을 때 exit 1 ─────────────────────────────────────────
def test_main_check_exits_1_on_difference(tmp_path, monkeypatch, capsys):
    out_path = tmp_path / "schedule_inventory.json"
    old_data = {
        "generated_at_note": "x",
        "windows_tasks": [{"name": "Wellperion-Old", "state": "Ready"}],
        "apscheduler_jobs": [],
        "counts": {"windows": 1, "apscheduler": 0},
    }
    out_path.write_text(json.dumps(old_data, ensure_ascii=False, indent=2), encoding="utf-8")

    new_windows = [{"name": "Wellperion-New", "state": "Ready", "enabled": True,
                     "triggers": [], "actions": [], "last_run": None,
                     "last_result": 0, "next_run": None}]

    monkeypatch.setattr(si, "OUT_PATH", out_path)
    monkeypatch.setattr(si, "collect_windows_tasks", lambda: new_windows)
    monkeypatch.setattr(si, "collect_apscheduler_jobs", lambda: [])
    monkeypatch.setattr(sys, "argv", ["schedule_inventory.py", "--check"])

    try:
        si.main()
        assert False, "SystemExit 가 발생해야 한다"
    except SystemExit as e:
        assert e.code == 1

    out = capsys.readouterr().out
    assert "불일치" in out
    # 파일이 갱신되지 않아야 한다(--check 는 쓰지 않음)
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk == old_data


def test_main_check_exits_0_when_identical(tmp_path, monkeypatch, capsys):
    out_path = tmp_path / "schedule_inventory.json"
    fixed_windows = [{"name": "Wellperion-A", "state": "Ready", "enabled": True,
                       "triggers": [], "actions": [], "last_run": None,
                       "last_result": 0, "next_run": None}]

    monkeypatch.setattr(si, "OUT_PATH", out_path)
    monkeypatch.setattr(si, "collect_windows_tasks", lambda: fixed_windows)
    monkeypatch.setattr(si, "collect_apscheduler_jobs", lambda: [])

    data = si.build_inventory()
    si.write_inventory(out_path, data)

    monkeypatch.setattr(sys, "argv", ["schedule_inventory.py", "--check"])
    try:
        si.main()
        assert False, "SystemExit 가 발생해야 한다"
    except SystemExit as e:
        assert e.code == 0
