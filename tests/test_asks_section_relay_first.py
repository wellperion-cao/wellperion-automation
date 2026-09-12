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


def test_no_fold_keeps_everything():
    relay = [_mk("이경연 실장", "전달문 A", "2026-09-05")]
    nudge = [_mk("이경연 실장", "#101 원장건", "2026-01-01")]
    out = d.build_asks_section(relay, nudge)
    assert "전달문 A" in out and "#101 원장건" in out


if __name__ == "__main__":
    test_relay_stays_inline_when_section_folds()
    test_no_fold_keeps_everything()
    print("ok")
