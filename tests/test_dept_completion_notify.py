"""
test_dept_completion_notify.py — 부서 톡방 '처리 완료' 통보 검증(2026-08-01, GM 지시).

검증 대상: report_stream_2b_reception._completion_block (종합접수처) +
          report_stream_1_impl._completion_block (문의).
확인 항목: ①기본 꺼짐 ②35건 동시완료여도 메시지 1개(캡+overflow 줄) ③멱등(재실행 시 재통보 0)
  ④켜면 신규건만 통보. 실제 텔레그램/카카오 발송·GAS 호출은 하지 않는다(순수 함수 검증).

★ persist=True 테스트는 실제 status/dept_completion_notify.json(라이브 킬스위치 파일)을
  절대 건드리지 않는다 — monkeypatch로 두 모듈의 COMPLETION_STATE_PATH를 tmp_path 임시
  파일로 바꿔치기한 뒤에만 persist=True를 쓴다(안 그러면 테스트가 GM go 스위치를 덮어씀).
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import report_stream_2b_reception as RC  # noqa: E402
import report_stream_1_impl as RQ  # noqa: E402


def _isolate_state_path(monkeypatch, tmp_path):
    """두 모듈의 COMPLETION_STATE_PATH를 tmp_path 임시 파일로 바꿔 라이브 파일 보호."""
    tmp = tmp_path / "dept_completion_notify_test.json"
    monkeypatch.setattr(RC, "COMPLETION_STATE_PATH", tmp)
    monkeypatch.setattr(RQ, "COMPLETION_STATE_PATH", tmp)
    return tmp


def _reception_rows(n_done, dept="시설부", start_id=1):
    rows = []
    for i in range(n_done):
        rows.append({
            "regId": f"R{start_id + i}", "dept": dept, "category": "시설물 고장 접수",
            "content": f"고장건{i}", "status": "완료", "handler": "박호균",
        })
    return rows


# ---------------------------------------------------------------------------
# ① 기본 꺼짐 — enabled=False면 완료건이 있어도 빈 문자열
# ---------------------------------------------------------------------------
def test_reception_off_by_default_produces_nothing():
    state = {"enabled": False, "reception_seen_done_ids": []}
    rows = _reception_rows(5)
    out = RC._completion_block(rows, state=state, persist=False)
    assert out == ""


def test_inquiry_off_by_default_produces_nothing():
    state = {"enabled": False, "inquiry_seen_keys": []}
    raw_groups = {"membership": [
        {"name": "김철수", "timestamp": "2026-08-01T09:00:00", "owner": "박팀장",
         "program": "플래티넘", "status": "신규", "contacts": []},
    ]}
    out = RQ._completion_block(raw_groups, state=state, persist=False)
    assert out == ""


# ---------------------------------------------------------------------------
# ② 폭주 시뮬레이션 — 35건 한 번에 완료돼도 메시지 1개(캡 6줄+overflow 1줄)
# ---------------------------------------------------------------------------
def test_reception_35_completions_at_once_is_one_message_capped():
    state = {"enabled": True, "reception_seen_done_ids": []}
    rows = _reception_rows(35)
    out = RC._completion_block(rows, state=state, persist=False)
    assert out != ""
    assert out.count("✅ [") == RC._COMPLETION_CAP  # 캡 이상 노출 안 함
    assert "…외 29건 더" in out
    assert "처리 완료 알림 35건" in out
    # "메시지 1개" — 여러 메시지로 쪼개는 로직 자체가 없다(개행 하나짜리 문자열 1개).
    assert isinstance(out, str)


# ---------------------------------------------------------------------------
# ③ 멱등 — 같은 상태로 두 번 돌리면 두 번째는 재통보 0건
# ---------------------------------------------------------------------------
def test_reception_idempotent_across_two_runs(monkeypatch, tmp_path):
    _isolate_state_path(monkeypatch, tmp_path)
    rows = _reception_rows(5)
    state = {"enabled": True, "reception_seen_done_ids": []}
    first = RC._completion_block(rows, state=state, persist=True)
    assert "처리 완료 알림 5건" in first
    second = RC._completion_block(rows, state=state, persist=True)
    assert second == ""  # 같은 5건 재발신 없음


def test_inquiry_idempotent_across_two_runs(monkeypatch, tmp_path):
    _isolate_state_path(monkeypatch, tmp_path)
    raw_groups = {"membership": [
        {"name": "김철수", "timestamp": "2026-08-01T09:00:00", "owner": "박팀장",
         "program": "플래티넘", "status": "SUC", "contacts": [{"note": "통화"}]},
    ]}
    state = {"enabled": True, "inquiry_seen_keys": []}
    first = RQ._completion_block(raw_groups, state=state, persist=True)
    assert "처리 완료 알림" in first
    second = RQ._completion_block(raw_groups, state=state, persist=True)
    assert second == ""


# ---------------------------------------------------------------------------
# ④ 켜면 신규건만 — 기존 완료건은 재통보 안 하고 새로 완료된 것만 잡는다
# ---------------------------------------------------------------------------
def test_reception_only_new_completions_after_seen_cursor():
    state = {"enabled": True, "reception_seen_done_ids": ["R1", "R2", "R3"]}
    rows = _reception_rows(5)  # R1..R5
    out = RC._completion_block(rows, state=state, persist=False)
    assert "처리 완료 알림 2건" in out  # R4·R5만 신규


# ---------------------------------------------------------------------------
# ⑤ 커서는 '보낸 뒤에' 확정된다 (2026-08-05 시토) — 발송이 실패하면 커서가 움직이면 안 된다.
#   움직여 버리면 그 완료건들은 다음 날 '이미 통보함'으로 걸러져 영영 통보되지 않는다.
# ---------------------------------------------------------------------------
def test_reception_cursor_committed_only_after_send(monkeypatch, tmp_path):
    import json
    tmp = _isolate_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(RC, "_pending_state", None)   # 앞 테스트의 대기분 격리
    rows = _reception_rows(5)
    state = {"enabled": True, "reception_seen_done_ids": []}

    out = RC._completion_block(rows, state=state, persist=True)
    assert "처리 완료 알림 5건" in out
    assert not tmp.exists()          # 발송 전 = 파일에 아무것도 안 씀(발송 실패 시 재통보 보장)

    assert RC.commit_completion_cursor() is True     # 발송 성공 뒤에야 확정
    saved = json.loads(tmp.read_text(encoding="utf-8"))
    assert saved["reception_seen_done_ids"] == ["R1", "R2", "R3", "R4", "R5"]
    assert RC.commit_completion_cursor() is False    # 대기분 없으면 두 번 쓰지 않음


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
