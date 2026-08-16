"""★중간관리자 카톡 회신칸이 낡은 수집본을 '회신 없음'과 같은 모양으로 보여주는지 검사한다.

배경(웰리 실측 2026-08-17): 아침 07:30에 방을 한 번 수집한 뒤 같은 날 저녁까지 재수집이
없으면, 날짜는 안 바뀌어(같은 날) 옛 코드의 stale 판정(날짜만 비교)을 피해 갔다. 그 사이
실제로 온 회신(나우열M 8/16 09:40 · 이정헌 소장 8/16 14:31)이 화면에는 그냥 "회신 없음"으로
찍혔다 — 못 읽은 것과 진짜 없는 것이 같은 모양이었다. 고침: 날짜가 아니라 경과 "시간"으로
판정(12시간 이상 낡으면 stale)한다.

실행: C:/Python314/python.exe scripts/test_midmgr_stale_reply.py
"""
import datetime as dt
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hangro_board as hb  # noqa: E402


def _write_archive(base: Path, saved_at: dt.datetime, msg_day: str, lines: list[str]) -> None:
    month_dir = base / saved_at.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    f = month_dir / f"★중간관리자_auto_{saved_at.strftime('%Y%m%d')}.txt"
    body = (
        "★중간관리자 님과 카카오톡 대화\n"
        f"저장한 날짜 : {saved_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"--------------- {msg_day} ---------------\n"
        + "\n".join(lines) + "\n"
    )
    f.write_text(body, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        hb.MIDMGR_ARCHIVE_DIR = base
        now = dt.datetime.now()

        # 1) 같은 날, 07:30 수집 후 저녁까지 재수집 없음(13시간 전) — 두 사람은 회신을 안 남긴 파일
        old = now - dt.timedelta(hours=13)
        _write_archive(base, old, f"{old.year}년 {old.month}월 {old.day}일",
                        [f"[라우열] [오전 09:00] 다른 얘기"])
        out = hb._midmgr_reply_slice("ceo")
        assert "13시간 전" in out, f"경과 시간이 안 찍혔다:\n{out}"
        assert "확인 못 함" in out, f"낡은 수집본인데 '확인 못 함'이 안 떴다:\n{out}"
        assert "이경연 실장 — 회신 없음" not in out, "낡은데 '회신 없음'으로 찍혔다(구분 실패)"

        # 2) 방금 수집(30분 전) — 경고 없이 정상 '회신 없음'
        base2 = Path(tmp) / "fresh"
        hb.MIDMGR_ARCHIVE_DIR = base2
        fresh = now - dt.timedelta(minutes=30)
        _write_archive(base2, fresh, f"{fresh.year}년 {fresh.month}월 {fresh.day}일",
                        [f"[라우열] [오전 09:00] 다른 얘기"])
        out2 = hb._midmgr_reply_slice("ceo")
        assert "확인 못 함" not in out2, f"방금 수집인데 '확인 못 함'이 떴다:\n{out2}"
        assert "이경연 실장 — 회신 없음" in out2, f"방금 수집인데 정상 '회신 없음'이 안 보인다:\n{out2}"

    print("OK — 12시간 넘게 낡은 수집본은 '확인 못 함'으로, 방금 수집본은 정상 '회신 없음'으로 갈린다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
