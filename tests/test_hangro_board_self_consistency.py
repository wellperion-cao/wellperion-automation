# -*- coding: utf-8 -*-
"""큐 자기정합 3종(2026-08-04 GM 지시 "줄기 3 큐 자기정합") — hangro_board 판정 자체 점검.
"이미 끝난 일을 안 끝난 줄 알고 다시 판다"를 부팅 항로(🔔 멈춰 있는 배)에서 표면화하는 장치.
①커밋 근거 있는 열린 배는 뜬다 ②닫힌 배는 안 뜬다 ③오늘 뜬 배는 안 뜬다
④외부(GM·실무진) 회신 대기 배는 의심 목록에 안 뜬다."""
import datetime as dt
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import hangro_board as HB  # noqa: E402

_REPO = os.path.join(os.path.dirname(__file__), "..")
_TODAY = dt.date.today().isoformat()
_OLD = (dt.date.today() - dt.timedelta(days=5)).isoformat()


def _item(status, note, owner="cto", enqueued_at=_OLD, title="t"):
    return {
        "owner": owner, "status": status, "note": note, "_raw_summary": "",
        "enqueued_at": enqueued_at, "updated_at": "", "title": title,
        "priority": "NORMAL", "end_date": "",
    }


def _real_commit_hash() -> str:
    r = subprocess.run(["git", "log", "-1", "--format=%h"], cwd=_REPO,
                        capture_output=True, text=True)
    return r.stdout.strip()


# ── ①「끝난 듯」— note 자기증언 ───────────────────────────────────────────
def test_self_testimony_open_ship_shows():
    items = [_item("PENDING", f"[{_OLD}] 이미 처리 완료했다")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert len(looks_done) == 1


# ── ①「끝난 듯」— note가 인용한 커밋해시가 실재하는지(존재 안 하면 근거로 안 씀) ──
def test_cited_commit_must_exist_in_git():
    h = _real_commit_hash()
    ev_fake = HB._cited_commit_evidence(_item("PENDING", f"[{_OLD}] 반영 확인(커밋 0000000)"))
    ev_real = HB._cited_commit_evidence(_item("PENDING", f"[{_OLD}] 반영 확인(커밋 {h})"))
    assert ev_fake == ""  # 존재하지 않는 해시는 근거로 안 씀
    assert ev_real == "" or "실재 확인" in ev_real  # 실재하면(등록전용 아닌 한) 근거로 잡힘


# ── ② 닫힌 배는 안 뜬다 ─────────────────────────────────────────────────
def test_done_ship_does_not_show():
    items = [_item("DONE", f"[{_OLD}] 이미 처리 완료했다")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert looks_done == []


# ── ③ 오늘 뜬 배는 안 뜬다 ───────────────────────────────────────────────
def test_new_today_ship_does_not_show():
    items = [_item("PENDING", f"[{_TODAY}] 이미 처리 완료했다", enqueued_at=_TODAY)]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert looks_done == []


# ── ④ 외부(GM) 회신 대기 배는 의심 목록에 안 뜬다 ────────────────────────────
def test_external_wait_ship_does_not_show():
    items = [_item("PENDING", f"[{_OLD}] 이미 처리 완료했다 — GM 승인 대기")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert looks_done == []


# ── ★시로(CHRO)·시뽀(CFO)는 목록에도 안 올린다 ────────────────────────────
def test_excluded_roles_never_shown():
    items = [_item("PENDING", f"[{_OLD}] 이미 처리 완료했다", owner="chro")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert looks_done == []


# ── 중복 배 — 같은 담당의 DONE·열린 배가 제목 겹침 ───────────────────────────
def test_duplicate_title_flagged():
    items = [
        _item("PENDING", "", owner="cto", title="[시토] 회원 변경 이력 자동 경로 이름미상"),
        _item("DONE", "", owner="cto", title="[시토] 회원 변경 이력 자동 경로 이름미상 수정"),
    ]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert len(dupes) == 1


def test_different_topic_not_flagged_as_duplicate():
    items = [
        _item("PENDING", "", owner="cto", title="[시토] 회원 변경 이력이 기록 0건"),
        _item("DONE", "", owner="cto", title="[시토] 회원 변경 이력 자동 경로 이름미상 수정"),
    ]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert dupes == []


# ── note↔status 불일치(실측 배206 재현: note "정박 전환"인데 status IN_PROGRESS) ──
def test_parked_note_but_in_progress_status_flagged():
    items = [_item("IN_PROGRESS", f"[{_OLD}] ⚓ 정박 전환: 회신 대기")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert len(mismatch) == 1


def test_parked_note_with_matching_status_not_flagged():
    items = [_item("PENDING", f"[{_OLD}] ⚓ 정박 전환: 회신 대기")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert mismatch == []


def test_parked_then_unparked_not_flagged():
    items = [_item("IN_PROGRESS",
                    f"[{_OLD}] ⚓ 정박 전환: 회신 대기\n[{_TODAY}] 정박 해제 — 재개")]
    looks_done, dupes, mismatch = HB._self_consistency_findings(items)
    assert mismatch == []


if __name__ == "__main__":
    test_self_testimony_open_ship_shows()
    test_cited_commit_must_exist_in_git()
    test_done_ship_does_not_show()
    test_new_today_ship_does_not_show()
    test_external_wait_ship_does_not_show()
    test_excluded_roles_never_shown()
    test_duplicate_title_flagged()
    test_different_topic_not_flagged_as_duplicate()
    test_parked_note_but_in_progress_status_flagged()
    test_parked_note_with_matching_status_not_flagged()
    test_parked_then_unparked_not_flagged()
    print("OK — all self-consistency self-checks passed")
