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


# ── is_ambiguous: 모호 판정(배xxx, 2026-07-13 설계) ──
def test_is_ambiguous_false_for_concrete_reversible_ship():
    result = war.is_ambiguous(_ship())
    assert result["ambiguous"] is False
    assert result["reasons"] == []


def test_is_ambiguous_true_for_short_vague_note():
    ship = _ship(note="점검")  # _VAGUE_MIN_NOTE_LEN(8) 미만
    result = war.is_ambiguous(ship)
    assert result["ambiguous"] is True
    assert any("불명확" in r for r in result["reasons"])


def test_is_ambiguous_true_for_multi_approach_keyword():
    ship = _ship(note="A안 또는 B안 중 골라서 스크립트 patch")
    result = war.is_ambiguous(ship)
    assert result["ambiguous"] is True
    assert any("접근법" in r for r in result["reasons"])


def test_is_ambiguous_true_for_scope_decision_keyword():
    ship = _ship(note="범위 결정 필요한 리팩터링 작업 진행")
    result = war.is_ambiguous(ship)
    assert result["ambiguous"] is True
    assert any("스코프" in r for r in result["reasons"])


def test_is_ambiguous_true_for_cruise_priority():
    ship = _ship(priority="🛳️크루즈", note="충분히 구체적인 절차가 담긴 내부 점검 스크립트 patch")
    result = war.is_ambiguous(ship)
    assert result["ambiguous"] is True
    assert any("크루즈" in r for r in result["reasons"])


def test_is_ambiguous_resumes_after_gm_interview_answer_recorded():
    # 짧은 note(모호 사유)였더라도, 웰리가 GM 답변을 마커로 기록 + 플래그 해제하면 통과해야 함.
    ship = _ship(note="점검", aide_interview_needed=False)
    ship["note"] = f"점검 {war.INTERVIEW_ANSWER_MARKER} 상세 절차는 X로 확정"
    result = war.is_ambiguous(ship)
    assert result["ambiguous"] is False


def test_is_ambiguous_still_ambiguous_while_flag_still_set_despite_marker():
    # 마커가 있어도 aide_interview_needed가 아직 True면(=미해소) 원 휴리스틱을 재적용해야 함.
    ship = _ship(aide_interview_needed=True)
    ship["note"] = f"{war.INTERVIEW_ANSWER_MARKER} A안 또는 B안 중 아직 미정"
    result = war.is_ambiguous(ship)
    assert result["ambiguous"] is True
    assert any("접근법" in r for r in result["reasons"])


# ── park_ship_for_interview ──
def test_park_ship_for_interview_sets_flags_and_preserves_note(tmp_path):
    queue = [_ship()]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    ok = war.park_ship_for_interview(str(queue_path), "CTO-2026-07-13-A", ["산출물 불명확"])
    assert ok is True

    saved = json.loads(queue_path.read_text(encoding="utf-8"))
    assert saved[0]["aide_interview_needed"] is True
    assert saved[0]["aide_interview_reason"] == "산출물 불명확"
    assert saved[0]["note"] == BASE_SHIP["note"]  # note 무손상


def test_park_ship_for_interview_returns_false_when_task_id_missing(tmp_path):
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps([_ship()], ensure_ascii=False), encoding="utf-8")
    ok = war.park_ship_for_interview(str(queue_path), "NO-SUCH-ID", ["reason"])
    assert ok is False


# ── select_one_low_risk_ship: 이미 parked 중인 배는 재선택 제외 ──
def test_select_excludes_already_parked_ship():
    queue = [_ship(aide_interview_needed=True)]
    result = war.select_one_low_risk_ship("cto", queue, registry=FAKE_REGISTRY)
    assert result is None


def test_select_skips_parked_ship_and_picks_next_candidate():
    parked = _ship(task_id="CTO-PARKED", aide_interview_needed=True, priority="⛵돛단배")
    normal = _ship(task_id="CTO-NORMAL", priority="⛴️여객선")
    result = war.select_one_low_risk_ship("cto", [parked, normal], registry=FAKE_REGISTRY)
    assert result is not None
    assert result["task_id"] == "CTO-NORMAL"


# ── parked_interview_worklist / print_interview_worklist ──
def test_parked_interview_worklist_filters_flagged_only():
    queue = [_ship(task_id="A", aide_interview_needed=True), _ship(task_id="B")]
    items = war.parked_interview_worklist(queue)
    assert len(items) == 1
    assert items[0]["task_id"] == "A"


def test_print_interview_worklist_outputs_markdown_table(tmp_path, capsys):
    queue = [_ship(task_id="A", aide_interview_needed=True, aide_interview_reason="사유X")]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    war.print_interview_worklist(queue_path=str(queue_path))
    out = capsys.readouterr().out
    assert "1척" in out
    assert "CTO-2026-07-13-A" not in out  # task_id는 A로 오버라이드됨
    assert "`A`" in out
    assert "사유X" in out


def test_print_interview_worklist_empty_message(tmp_path, capsys):
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text("[]", encoding="utf-8")
    war.print_interview_worklist(queue_path=str(queue_path))
    out = capsys.readouterr().out
    assert "없음" in out


# ── 텔레그램 핑: dedup + 하루 cap (실전송 없음 — notifier=None/FakeNotifier만 사용) ──
class _FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return {"ok": True, "result": {"message_id": 1}}


def test_ping_decision_should_send_for_new_parked_ids():
    state = {"pinged_task_ids": [], "sent_dates": {}}
    decision = war._ping_decision(["CTO-A"], state)
    assert decision["should_send"] is True
    assert decision["new_task_ids"] == ["CTO-A"]


def test_ping_decision_dedup_blocks_already_pinged():
    state = {"pinged_task_ids": ["CTO-A"], "sent_dates": {}}
    decision = war._ping_decision(["CTO-A"], state)
    assert decision["should_send"] is False
    assert "dedup" in decision["reason"]


def test_ping_decision_daily_cap_blocks_after_limit():
    from datetime import datetime, timezone

    now = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
    state = {"pinged_task_ids": [], "sent_dates": {"2026-07-13": war.AMBIGUOUS_PING_DAILY_CAP}}
    decision = war._ping_decision(["CTO-A"], state, now=now)
    assert decision["should_send"] is False
    assert "cap" in decision["reason"]


def test_maybe_send_ambiguous_ping_with_none_notifier_previews_only_no_state_file(tmp_path):
    state_path = tmp_path / "ping_state.json"
    result = war.maybe_send_ambiguous_ping(["CTO-A"], state_path=str(state_path), notifier=None)
    assert result["sent"] is False
    assert "모호 배 1건" in result["text"]
    assert not state_path.exists()  # 실전송 없음 — 상태파일도 생성 안 됨


def test_maybe_send_ambiguous_ping_with_fake_notifier_sends_and_persists_state(tmp_path):
    state_path = tmp_path / "ping_state.json"
    notifier = _FakeNotifier()
    result = war.maybe_send_ambiguous_ping(["CTO-A"], state_path=str(state_path), notifier=notifier)
    assert result["sent"] is True
    assert notifier.sent == [result["text"]]
    assert state_path.exists()

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert "CTO-A" in saved["pinged_task_ids"]


def test_maybe_send_ambiguous_ping_dedups_across_calls(tmp_path):
    state_path = tmp_path / "ping_state.json"
    notifier = _FakeNotifier()
    war.maybe_send_ambiguous_ping(["CTO-A"], state_path=str(state_path), notifier=notifier)
    second = war.maybe_send_ambiguous_ping(["CTO-A"], state_path=str(state_path), notifier=notifier)
    assert second["sent"] is False
    assert len(notifier.sent) == 1  # 두 번째 호출은 dedup으로 실제 전송 안 됨


# ── run_once: 모호 배는 parked 모드 — 실행 안 함, dry-run은 큐 무변경 ──
def test_run_once_dry_run_ambiguous_ship_returns_parked_mode_without_queue_mutation(tmp_path, monkeypatch):
    queue = [_ship(note="점검")]  # 짧은 note = 모호
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("dry-run parked 시나리오인데 subprocess.run이 호출됨")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    before = queue_path.read_text(encoding="utf-8")
    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"),
        live=False,
    )
    after = queue_path.read_text(encoding="utf-8")

    assert result["mode"] == "parked"
    assert result["executed"] is False
    assert result["parked"] is False  # dry-run은 실제 park(큐 변경) 안 함
    assert before == after  # 큐 무변경 유지


# ── run_cycle: 전 C-Level 순회(배237 phase4) ──
def test_run_cycle_visits_all_default_clevels_in_order(tmp_path, monkeypatch):
    queue = [_ship()]  # cto 배 1척만 존재 — 나머지 clevel은 후보 0건이어야 함
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("dry-run 사이클인데 subprocess.run이 호출됨")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    cycle = war.run_cycle(
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"),
        live=False,
    )

    assert cycle["cycle_order"] == list(war.DEFAULT_CLEVELS)
    assert set(cycle["results"].keys()) == set(war.DEFAULT_CLEVELS)
    assert cycle["results"]["cto"]["ship"]["task_id"] == "CTO-2026-07-13-A"
    for clevel in war.DEFAULT_CLEVELS:
        if clevel != "cto":
            assert cycle["results"][clevel]["ship"] is None
    assert cycle["executed_count"] == 0  # dry-run은 executed=False뿐이므로 카운트 0


def test_run_cycle_respects_custom_clevels_subset(tmp_path):
    queue = [_ship(clevel="cmo", task_id="CMO-X")]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    cycle = war.run_cycle(
        clevels=("cmo", "cto"), queue_path=str(queue_path), registry_path=None,
        state_path=str(tmp_path / "state.json"), log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"), live=False,
    )
    assert cycle["cycle_order"] == ["cmo", "cto"]
    assert set(cycle["results"].keys()) == {"cmo", "cto"}


def test_run_cycle_stops_at_total_cap_marks_remaining_clevels_skipped(tmp_path, monkeypatch):
    queue = [_ship()]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    calls = []

    def _fake_run_once(clevel, **kwargs):
        calls.append(clevel)
        return {
            "mode": "live", "ship": {"task_id": f"{clevel.upper()}-X"}, "prompt": "p",
            "executed": True, "success": True, "commit": "deadbeef",
        }

    monkeypatch.setattr(war, "run_once", _fake_run_once)

    cycle = war.run_cycle(
        clevels=("cmo", "coo", "cto", "cpo"),
        queue_path=str(queue_path), registry_path=None,
        state_path=str(tmp_path / "state.json"), log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"),
        live=True, max_total_ships=2,
    )

    assert calls == ["cmo", "coo"]  # 상한 도달 후 run_once 호출 자체가 안 됨
    assert cycle["executed_count"] == 2
    assert cycle["results"]["cto"]["mode"] == "cycle-cap-skipped"
    assert cycle["results"]["cpo"]["mode"] == "cycle-cap-skipped"
    assert cycle["results"]["cto"]["executed"] is False


# ── run_cycle: 모호배 비협상 원칙(GM 2026-07-14 못박기) — 절대 추측 진행 금지 ──
def test_run_cycle_never_executes_ambiguous_ship_across_any_clevel(tmp_path, monkeypatch):
    # cmo·cto 둘 다 모호 배(짧은 note)만 존재 — 어느 clevel도 실행되면 안 되고 전부 park.
    queue = [
        _ship(clevel="cmo", task_id="CMO-VAGUE", note="점검"),
        _ship(clevel="cto", task_id="CTO-VAGUE", note="점검"),
    ]
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("모호 배인데 subprocess.run(claude 호출)이 실행됨 — 비협상 원칙 위반")

    monkeypatch.setattr(war.subprocess, "run", _boom)
    monkeypatch.setattr(
        war, "working_tree_guard",
        lambda *a, **kw: {"blocked": False, "dirty_files": [], "real_work_files": [], "reason": "클린"},
    )

    cycle = war.run_cycle(
        clevels=("cmo", "cto"),
        queue_path=str(queue_path), registry_path=None,
        state_path=str(tmp_path / "state.json"), log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"),
        live=True,  # 라이브여도 모호 배는 실행 대신 park만 되어야 함
    )

    assert cycle["executed_count"] == 0
    for clevel in ("cmo", "cto"):
        result = cycle["results"][clevel]
        assert result["mode"] == "parked"
        assert result["executed"] is False
        assert result["parked"] is True  # 라이브 park는 실제 큐 플래그까지 기록됨

    saved = json.loads(queue_path.read_text(encoding="utf-8"))
    for ship in saved:
        assert ship["aide_interview_needed"] is True  # 두 배 다 인터뷰 대기로 park, 실행 흔적 0


def test_run_cycle_passes_correct_nick_per_clevel(tmp_path, monkeypatch):
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text("[]", encoding="utf-8")
    seen_nicks = {}

    def _fake_run_once(clevel, nick, **kwargs):
        seen_nicks[clevel] = nick
        return {"mode": "dry-run", "ship": None, "prompt": None, "executed": False, "commit": None}

    monkeypatch.setattr(war, "run_once", _fake_run_once)

    war.run_cycle(
        queue_path=str(queue_path), registry_path=None,
        state_path=str(tmp_path / "state.json"), log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"), live=False,
    )

    assert seen_nicks == war.CLEVEL_NICKS


def test_run_once_live_ambiguous_ship_parks_flag_and_previews_ping_without_real_send(tmp_path, monkeypatch):
    queue = [_ship(note="점검")]  # 짧은 note = 모호
    queue_path = tmp_path / "_queue.json"
    queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    monkeypatch.delenv(war.PING_LIVE_ENV_VAR, raising=False)  # 기본 OFF — 실전송 게이트 잠김 확인
    monkeypatch.setattr(
        war, "working_tree_guard",
        lambda *a, **kw: {"blocked": False, "dirty_files": [], "real_work_files": [], "reason": "클린"},
    )

    def _boom(*a, **kw):
        raise AssertionError("parked 시나리오인데 subprocess.run(claude 호출)이 실행됨")

    monkeypatch.setattr(war.subprocess, "run", _boom)

    result = war.run_once(
        clevel="cto",
        queue_path=str(queue_path),
        registry_path=None,
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "log.jsonl"),
        ping_state_path=str(tmp_path / "ping_state.json"),
        live=True,
    )

    assert result["mode"] == "parked"
    assert result["executed"] is False
    assert result["commit"] is None
    assert result["parked"] is True

    saved = json.loads(queue_path.read_text(encoding="utf-8"))
    assert saved[0]["aide_interview_needed"] is True
    assert saved[0]["aide_interview_reason"]

    # RUNNER_PING_LIVE 기본 OFF이므로 notifier=None 경로 — 실전송 없음(payload만 결과에 남음)
    assert result["ping"]["sent"] is False
    assert "모호 배 1건" in result["ping"]["text"]
