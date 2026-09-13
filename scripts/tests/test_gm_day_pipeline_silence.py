"""저녁 정리 통이 조용히 죽던 두 원인에 대한 최소 회귀 검사 (2026-09-14 시토).

① 월간운영계획 progress 가 문자열('0')이면 정렬 key 가 터져 20:00 통이 안 나갔다(22회).
② 토요일을 '휴무'로 묶어 08:00·20:00 업무 통이 통째로 빠졌다(cron 은 mon-sat).
③ 침묵 감지가 남의 데이터 파일을 신호로 봐 한 달간 ok 로 보였다 — 발신 로그를 본다.
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "telegram_bot")]

import gm_checkin  # noqa: E402
import module_silence_detector as msd  # noqa: E402


def test_progress_string_does_not_break_sort(tmp_path=None):
    objs = [{"title": "A (GM 직접)", "progress": "0"}, {"title": "B (GM 직접)", "progress": 40}]
    plan = {"months": {"2026-09": {"objectives": objs}}}
    p = ROOT / "status" / "monthly_ops_plan.json"
    orig = gm_checkin.MONTHLY_PLAN
    tmp = Path(str(p) + ".test.json")
    tmp.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    try:
        gm_checkin.MONTHLY_PLAN = tmp
        got = gm_checkin._fetch_gm_direct_objectives("2026-09-14")
        assert [o["progress"] for o in got] == [0, 40]
        assert sorted(got, key=lambda o: -(o.get("progress") or 0))[0]["title"].startswith("B")
    finally:
        gm_checkin.MONTHLY_PLAN = orig
        tmp.unlink(missing_ok=True)


def test_saturday_is_a_work_day():
    import daily_scheduler as ds
    sat = datetime.datetime(2026, 9, 12, 8, 0)
    sun = datetime.datetime(2026, 9, 13, 8, 0)
    assert ds._haru_work_off(sat) is False
    assert ds._haru_work_off(sun) is True


def test_tgsend_signal_takes_the_oldest(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    rows = [{"ts": "2026-09-14T08:00:00", "source": "gm_morning_brief", "ok": True},
            {"ts": "2026-09-01T20:00:00", "source": "gm_evening_recap", "ok": True}]
    (logs / "telegram_sent-2026-09-14.log").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    dt, method = msd._tgsend_signal("gm_morning_brief,gm_evening_recap", tmp_path)
    assert dt.strftime("%Y-%m-%d") == "2026-09-01", "한쪽이 죽으면 죽은 쪽 시각이 신호다"
    assert msd._tgsend_signal("gm_morning_brief,never_sent", tmp_path) is None


if __name__ == "__main__":
    import tempfile
    test_progress_string_does_not_break_sort()
    test_saturday_is_a_work_day()
    with tempfile.TemporaryDirectory() as d:
        test_tgsend_signal_takes_the_oldest(Path(d))
    print("ok — 3 검사 통과")
