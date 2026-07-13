"""
test_welly_auto_runner.py — 예약 Claude 러너 MVP pytest.
검증 대상: scripts/welly_auto_runner.py
인라인 fixture(가짜 queue·registry)만 사용 — 실제 status/_queue.json은 건드리지 않는다
(모든 run_once 호출에 tmp_path 기반 queue_path/state_path/log_path를 명시 주입).
"""

import copy
import json
import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import welly_auto_runner as war  # noqa: E402

FAKE_REGISTRY = {
    "modules": [
        {
            "id": "cto-automation-health",
            "owner_role": "cto",
            "owner_nick": "시토",
            "feature": "자동화 건강 점수판",
            "data_source": {"kind": "json", "ref": "erp_status.json"},
            "notify_spec": {"daily": False, "weekly": True, "monthly": False, "channel": "telegram", "bot_id": None},
            "front_card": {"window": "자율현황", "anchor": "layer-automation"},
            "autonomy": "auto",
            "ai_free_fallback": "예약작업이 사람 세션 없이 상시 가동",
            "feedback": {"enabled": True, "audience": "gm+clevel", "entries": []},
            "reversible": True,
        }
    ]
}

BASE_SHIP = {
    "task_id": "CTO-2026-07-13-A",
    "clevel": "cto",
    "title": "가역 배 예시",
    "status": "PENDING",
    "priority": "⛵돛단배",
    "enqueued_at": "2026-07-13",
    "note": "내부 점검 스크립트 patch",
    "next": "",
    "depends_on": "",
    "module": "T2",
    "ship_no": 900,
}


def _ship(**overrides):
    s = copy.deepcopy(BASE_SHIP)
    s.update(overrides)
    return s


# ── select_one_low_risk_ship: 저위험 추가 필터 ──
def test_select_excludes_extra_low_risk_keywords():
    for keyword in ("라이브 배포 아님 라이브 점검", "GAS 스크립트 수정", "시트쓰기 반영"):
        queue = [_ship(note=keyword)]
        result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
        assert result is None, f"저위험 추가 필터 미차단: {keyword}"


def test_select_still_uses_base_irreversible_filter():
    queue = [_ship(title="발행 파이프라인 정비")]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is None


def test_select_allows_plain_reversible_ship():
    queue = [_ship()]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is not None
    assert result["task_id"] == "CTO-2026-07-13-A"


# ── select_one_low_risk_ship: 구체 작업 배 필터(bridge 포인터 배 제외) ──
def test_select_excludes_bridge_origin_ship():
    queue = [_ship(origin="bridge")]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is None


def test_select_excludes_next_prefixed_task_id():
    queue = [_ship(task_id="NEXT-20260707-155721")]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is None


def test_select_excludes_ship_without_priority():
    queue = [_ship(priority=None)]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is None

    queue_empty = [_ship(priority="")]
    result_empty = war.select_one_low_risk_ship("cto", queue_empty, registry=FAKE_REGISTRY)
    assert result_empty is None


def test_select_bridge_ship_excluded_among_mixed_candidates():
    # 실제 관측 사례(NEXT-20260707-155721)와 동형: origin=bridge + NEXT- task_id + priority 없음.
    bridge_ship = {
        "task_id": "NEXT-20260707-155721",
        "clevel": "cto",
        "title": "재설계=배420으로 이어짐. stage4 기여추적은 420에 통합 검토",
        "status": "PENDING",
        "depends_on": "",
        "from": "cto",
        "origin": "bridge",
        "enqueued_at": "2026-07-07T06:57:21Z",
        "ship_no": 597,
    }
    queue = [bridge_ship, _ship()]  # bridge 포인터 + 정상 구체 가역 배
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is not None
    assert result["task_id"] == "CTO-2026-07-13-A"


# ── 쿨다운 배 제외 ──
def test_select_excludes_cooldown_task_ids():
    queue = [_ship()]
    result = war.select_one_low_risk_ship(
        "cto", queue, registry=FAKE_REGISTRY, cooldown_task_ids={"CTO-2026-07-13-A"}
    )
    assert result is None


# ── 1척 제한 + 난이도(priority) 오름차순 ──
def test_select_returns_exactly_one_ship_smallest_priority_first():
    queue = [
        _ship(task_id="BIG", priority="🛳️크루즈"),
        _ship(task_id="SMALL", priority="⛵돛단배"),
        _ship(task_id="MID", priority="⛴️여객선"),
    ]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert isinstance(result, dict)
    assert result["task_id"] == "SMALL"


def test_select_returns_none_when_no_candidates():
    queue = [_ship(clevel="cmo")]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is None


# ── build_orchestration_prompt: 재귀 폭주 방지 지시 포함 ──
def test_prompt_contains_ship_fields_and_recursion_guard():
    ship = _ship()
    prompt = war.build_orchestration_prompt(ship, clevel="cto", nick="시토")
    assert ship["task_id"] in prompt
    assert ship["title"] in prompt
    assert "welly_auto_runner.py" in prompt
    assert "재귀 폭주 방지" in prompt
    assert "clevel_post_action.py" in prompt


# ── run_once: 게이트 OFF(dry-run) — claude 미호출·커밋0·큐 무변경 ──
def test_run_once_dry_run_never_calls_subprocess(tmp_path, monkeypatch):
    queue = [_ship()]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    state_path = tmp_path / "state.json"
    log_path = tmp_path / "log.jsonl"

    def _boom(*a, **kw):
        raise AssertionError("dry-run인데 subprocess.run이 호출됨")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    before = queue_path.read_text(encoding="utf-8")
    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(state_path),
        log_path=str(log_path),
        live=False,
    )
    after = queue_path.read_text(encoding="utf-8")

    assert result["mode"] == "dry-run"
    assert result["executed"] is False
    assert result["commit"] is None
    assert result["ship"]["task_id"] == "CTO-2026-07-13-A"
    assert result["prompt"] is not None
    assert before == after  # 큐 무변경
    assert not state_path.exists()  # 쿨다운 상태 파일도 dry-run에선 생성 안 됨


def test_run_once_dry_run_no_ship_when_only_irreversible_present(tmp_path, monkeypatch):
    queue = [_ship(note="보안 설정 변경")]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run 호출 금지")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        live=False,
    )
    assert result["ship"] is None
    assert result["executed"] is False


# ── 재귀 폭주 방지 가드: env 활성 시 큐도 안 읽고 즉시 차단 ──
def test_run_once_guard_blocked_skips_everything(tmp_path, monkeypatch):
    monkeypatch.setenv(war.GUARD_ENV_VAR, "1")

    def _boom(*a, **kw):
        raise AssertionError("guard-blocked인데 subprocess.run이 호출됨")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    nonexistent_queue = str(tmp_path / "does_not_exist.json")
    result = war.run_once(
        clevel="cto",
        queue_path=nonexistent_queue,  # guard가 먼저 걸려 이 경로는 열리지 않아야 함
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        live=True,
    )
    assert result["mode"] == "guard-blocked"
    assert result["ship"] is None
    assert result["executed"] is False


# ── env RUNNER_LIVE 기본 OFF 확인 ──
def test_is_live_defaults_off(monkeypatch):
    monkeypatch.delenv(war.LIVE_ENV_VAR, raising=False)
    assert war._is_live() is False


def test_is_live_on_when_env_set_to_1(monkeypatch):
    monkeypatch.setenv(war.LIVE_ENV_VAR, "1")
    assert war._is_live() is True


# ── 쿨다운 헬퍼 ──
def test_mark_and_active_cooldown_roundtrip():
    from datetime import datetime, timezone

    state = {"cooldown": {}}
    now = datetime(2026, 7, 13, 0, 0, tzinfo=timezone.utc)
    war._mark_cooldown(state, "CTO-X", reason="테스트 실패", hours=24, now=now)
    active_now = war._active_cooldown_ids(state, now=now)
    assert "CTO-X" in active_now

    later = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    active_later = war._active_cooldown_ids(state, now=later)
    assert "CTO-X" not in active_later


# ── 클린트리 가드(working_tree_guard): 노이즈 vs 진짜 미커밋 작업 구분 ──
def _init_git_repo(repo_dir):
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=str(repo_dir), check=True)
    sp.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)
    sp.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), check=True)


def test_working_tree_guard_passes_when_clean(tmp_path):
    _init_git_repo(tmp_path)
    result = war.working_tree_guard(repo_root=str(tmp_path))
    assert result["blocked"] is False
    assert result["dirty_files"] == []
    assert result["real_work_files"] == []


def test_working_tree_guard_passes_when_only_noise_dirty(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "status").mkdir()
    (tmp_path / "status" / "briefs").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "status" / "kpi_values.json").write_text("{}", encoding="utf-8")
    (tmp_path / "status" / "gm_profile.md").write_text("noise", encoding="utf-8")
    (tmp_path / "status" / "briefs" / "CMO-daily-feedback-20260713.md").write_text("x", encoding="utf-8")
    (tmp_path / "logs" / "run.log").write_text("x", encoding="utf-8")
    (tmp_path / "telegram_bot_heartbeat.txt").write_text("x", encoding="utf-8")

    result = war.working_tree_guard(repo_root=str(tmp_path))
    assert result["blocked"] is False
    assert result["real_work_files"] == []
    assert len(result["dirty_files"]) == 5


def test_working_tree_guard_blocks_on_real_work_file(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "status").mkdir()
    (tmp_path / "status" / "kpi_values.json").write_text("{}", encoding="utf-8")  # 노이즈
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "some_new_feature.py").write_text("print('hi')\n", encoding="utf-8")  # 진짜 작업

    result = war.working_tree_guard(repo_root=str(tmp_path))
    assert result["blocked"] is True
    assert "scripts/some_new_feature.py" in result["real_work_files"]
    assert "status/kpi_values.json" not in result["real_work_files"]


@pytest.mark.parametrize(
    "path,expected_noise",
    [
        ("status/_archive.json", True),
        ("status/gm_aide_scan_log.jsonl", True),
        ("status/briefs/CMO-daily-feedback-20260706.md", True),
        ("status/morning_plans/2026-07-13.json", True),
        ("status/_memory_snapshots/2026-07-12.zip", True),
        ("status/northstar_card_sample.md", True),
        ("status/self_review_log.jsonl", True),
        ("status/learning_health.md", True),
        ("telegram_bot/.finance_cache.txt", True),
        ("telegram_bot/bot_heartbeat.txt", True),
        ("3. 웰페리온 가이드/cmo/review/성찰틀_preview_20260712073003.png", True),
        ("logs/foo.txt", True),
        ("scripts/welly_auto_runner.py", False),
        ("scripts/gm_aide_scan.bat", False),
        ("docs/superpowers/specs/2026-07-09-module-registry-contract.md", False),
        ("instagram/_실전사례_2주플랜.md", False),
        ("ops/restart_telegram_bot_core.ps1", False),
    ],
)
def test_is_noise_path_matches_real_observed_allowlist(path, expected_noise):
    assert war._is_noise_path(path) is expected_noise


# ── run_once: 클린트리 가드는 LIVE에서만 발동 ──
def test_run_once_dry_run_does_not_check_working_tree(tmp_path, monkeypatch):
    queue = [_ship()]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("dry-run인데 working_tree_guard가 호출됨")

    monkeypatch.setattr(war, "working_tree_guard", _boom)

    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        live=False,
    )
    assert result["mode"] == "dry-run"


def test_run_once_live_blocked_by_working_tree_guard(tmp_path, monkeypatch):
    queue = [_ship()]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("워킹트리 가드 차단인데 subprocess.run이 호출됨(claude 호출 시도)")

    monkeypatch.setattr(war.subprocess, "run", _boom)
    monkeypatch.setattr(
        war, "working_tree_guard",
        lambda *a, **kw: {
            "blocked": True, "dirty_files": ["scripts/foo.py"],
            "real_work_files": ["scripts/foo.py"], "reason": "테스트 차단",
        },
    )

    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        live=True,
    )
    assert result["mode"] == "live"
    assert result["executed"] is False
    assert result["ship"] is None
    assert result["commit"] is None
    assert "scripts/foo.py" in result["dirty_files"]


def test_run_once_live_passes_guard_then_proceeds_to_selection(tmp_path, monkeypatch):
    # 비가역 배만 있어 후보 0건 — 워킹트리 가드는 통과했지만 claude는 호출되지 않아야 함
    queue = [_ship(note="보안 설정 변경")]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        war, "working_tree_guard",
        lambda *a, **kw: {"blocked": False, "dirty_files": [], "real_work_files": [], "reason": "클린"},
    )

    def _boom(*a, **kw):
        raise AssertionError("후보 0건인데 subprocess.run이 호출됨")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        live=True,
    )
    assert result["mode"] == "live"
    assert result["ship"] is None
    assert result["reason"] != "테스트 차단"


# ── build_orchestration_prompt: git add 범위 명시 금지 문구 ──
def test_prompt_contains_explicit_add_scope_prohibition():
    ship = _ship()
    prompt = war.build_orchestration_prompt(ship, clevel="cto", nick="시토")
    assert "git add -A" in prompt
    assert "git commit -a" in prompt
