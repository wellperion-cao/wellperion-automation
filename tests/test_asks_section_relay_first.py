# -*- coding: utf-8 -*-
"""배2578 — 「확인 부탁드릴 것」 절이 접힐 때 배 전달문이 접히면 안 된다.

접힘 안내가 가리키는 링크는 결재 현황 SSOT 화면이라 배 전달문은 거기에 없다.
원장 #번호 건은 그 화면에서 볼 수 있으므로 그쪽부터 접는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import send_ops_digest as d  # noqa: E402


def _mk(who, ask, date):
    return {"who": who, "ask": ask, "date": date}


def test_relay_stays_inline_when_section_folds():
    # 원장 #번호 건이 접수일로 앞서도(01-01) 배 전달문이 인라인에 남아야 한다.
    nudge = [_mk("이경연 실장", f"#10{i} 원장건 {i}", "2026-01-01") for i in range(8)]
    nudge += [_mk("이정헌 소장", f"#20{i} 원장건 {i}", "2026-01-02") for i in range(8)]
    relay = [_mk("이경연 실장", "회원 문자 자동 안내 문구 확인", "2026-09-05"),
             _mk("이정헌 소장", "동반 게스트 1일권 확인", "2026-09-08")]

    out = d.build_asks_section(relay, nudge)
    assert "외" in out and "건 —" in out, "이 표본은 접혀야 시험이 성립한다"
    for it in relay:
        assert it["ask"] in out, f"배 전달문이 접혔다: {it['ask']}"


def test_relay_never_truncated_by_per_person_budget():
    # 사람당 몫(per)보다 배 전달문이 많아도 전달문은 전부 실린다(접힘 링크 화면에 없으므로).
    nudge = [_mk("이경연 실장", f"#10{i} 원장건 {i}", "2026-01-01") for i in range(6)]
    nudge += [_mk("이정헌 소장", f"#20{i} 원장건 {i}", "2026-01-02") for i in range(6)]
    relay = [_mk("이경연 실장", f"전달문 {i}", "2026-09-05") for i in range(4)]
    out = d.build_asks_section(relay, nudge)
    for it in relay:
        assert it["ask"] in out, f"배 전달문이 잘렸다: {it['ask']}"


def test_header_counts_real_open_items():
    relay = [_mk("이경연 실장", "전달문 A", "2026-09-05")]
    nudge = [_mk("이경연 실장", f"#10{i} 원장건 {i}", "2026-01-01") for i in range(10)]
    out = d.build_asks_section(relay, nudge)
    assert out.splitlines()[0] == "🧾 확인 부탁드릴 것 11건", out.splitlines()[0]


def test_send_skip_mark_only_matches_the_empty_case():
    # 「보낼 것 없음」만 정상 종료(rc=0). 진짜 실패 BLOCKED 는 그대로 실패로 남아야 한다.
    assert d.SEND_SKIP_MARK in "BLOCKED: 전량 중복/보류 스킵(실발신 0건) — {'★운영부': 'via_manager'}"
    for real_fail in ("BLOCKED: 2개 방 실패",
                      "BLOCKED: 다른 카톡 발신이 화면을 잡고 있어 보내지 못했다",
                      "BLOCKED: 전송 대상 방이 없음(kakao_rooms.json)"):
        assert d.SEND_SKIP_MARK not in real_fail, real_fail


def test_no_fold_keeps_everything():
    relay = [_mk("이경연 실장", "전달문 A", "2026-09-05")]
    nudge = [_mk("이경연 실장", "#101 원장건", "2026-01-01")]
    out = d.build_asks_section(relay, nudge)
    assert "전달문 A" in out and "#101 원장건" in out


if __name__ == "__main__":
    test_relay_stays_inline_when_section_folds()
    test_relay_never_truncated_by_per_person_budget()
    test_header_counts_real_open_items()
    test_send_skip_mark_only_matches_the_empty_case()
    test_no_fold_keeps_everything()
    print("ok")
