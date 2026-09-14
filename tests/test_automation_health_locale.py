"""자동화 건강판 — schtasks 라벨이 한글이든 영문이든 같은 값을 내는지.

2026-09-14 시토(배11439). 상주 스케줄러 자식 프로세스 안에서만 schtasks 가 영문 라벨
("HostName:" / "TaskName:", 공백 없음)로 출력해 블록 분리가 통째로 실패했고, 자동화
건강판이 09-09 새벽부터 "측정 없음 (wellperion 작업 매칭 0건)" 0% 를 발행했다.
두 갈래 샘플을 같은 함수에 먹여 같은 결과가 나오는지 잰다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import erp_status_publisher as esp  # noqa: E402

KO = """
폴더: \\
호스트 이름:                       WELLPERIONGM
작업 이름:                         \\Wellperion-Alpha
다음 실행 시간:                    2026-09-15 오전 11:16:00
상태:                              준비
마지막 실행 시간:                  2026-09-14 오전 11:16:01
마지막 결과:                       0

호스트 이름:                       WELLPERIONGM
작업 이름:                         \\Wellperion-Beta
다음 실행 시간:                    2026-09-15 오전 9:00:00
마지막 실행 시간:                  2026-09-14 오전 9:00:00
마지막 결과:                       1

호스트 이름:                       WELLPERIONGM
작업 이름:                         \\AdobeGCInvoker-1.0
다음 실행 시간:                    2026-09-15 오전 11:16:00
마지막 실행 시간:                  2026-09-14 오전 11:16:01
마지막 결과:                       0
"""

EN = """
Folder: \\
HostName:                             WELLPERIONGM
TaskName:                             \\Wellperion-Alpha
Next Run Time:                        2026-09-15 오전 11:16:00
Status:                               Ready
Last Run Time:                        2026-09-14 오전 11:16:01
Last Result:                          0

HostName:                             WELLPERIONGM
TaskName:                             \\Wellperion-Beta
Next Run Time:                        2026-09-15 오전 9:00:00
Last Run Time:                        2026-09-14 오전 9:00:00
Last Result:                          1

HostName:                             WELLPERIONGM
TaskName:                             \\AdobeGCInvoker-1.0
Next Run Time:                        2026-09-15 오전 11:16:00
Last Run Time:                        2026-09-14 오전 11:16:01
Last Result:                          0
"""


def _run(dump):
    esp._schtasks_dump = lambda: dump
    esp._live_task_names = lambda: {"wellperion-alpha", "wellperion-beta"}
    return esp.collect_automation_health()


def test_both_locales_same_result():
    ko, en = _run(KO), _run(EN)
    for tag, r in (("ko", ko), ("en", en)):
        assert r["total"] == 2, f"{tag}: wellperion 작업 2건이어야 하는데 {r}"
        assert r["healthy"] == 1, f"{tag}: 정상 1건이어야 하는데 {r}"
        assert [i["name"] for i in r["items"]] == ["Wellperion-Alpha", "Wellperion-Beta"], tag
        assert r["items"][0]["last_run"].startswith("2026-09-14"), tag
        assert r["items"][1]["state"] == "실패", tag
    assert ko["summary"] == en["summary"]


if __name__ == "__main__":
    test_both_locales_same_result()
    print("OK — 한글·영문 라벨 동일 결과")
