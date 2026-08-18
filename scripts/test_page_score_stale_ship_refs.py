# -*- coding: utf-8 -*-
"""check_page_score_stale_ship_refs() 회귀검사 (배 4331 후속).

page_score.json 의 note 가 이미 끝난 배를 정정 신호 없이 인용하면 걸려야 하고,
정정 신호(종결/해소/사실 아님/정상 가동/확인 완료)가 있으면 통과해야 한다.

실행: C:/Python314/python.exe scripts/test_page_score_stale_ship_refs.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integration_health as ih


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        page_score = tmp / "page_score.json"
        queue = tmp / "_queue.json"
        archive = tmp / "_queue_archive.json"

        _write(queue, [{"short_no": 999, "status": "DONE"}])
        _write(archive, [{"short_no": 617}])

        orig = (ih.PAGE_SCORE, ih.LOCAL_QUEUE, ih.QUEUE_ARCHIVE)
        ih.PAGE_SCORE, ih.LOCAL_QUEUE, ih.QUEUE_ARCHIVE = page_score, queue, archive
        try:
            # 1) 끝난 배를 정정 신호 없이 인용 → ok=False
            _write(page_score, {"pages": [
                {"name": "가짜화면", "note": "배617 CTO 미해결·수동 갱신 의존"},
            ]})
            name, ok, detail = ih.check_page_score_stale_ship_refs()
            assert ok is False, f"정정 신호 없는 끝난 배 인용인데 통과함: {detail}"
            assert "617" in detail, f"detail 에 배 번호 없음: {detail}"

            # 2) 정정 신호가 있으면 같은 문장이어도 통과
            _write(page_score, {"pages": [
                {"name": "가짜화면", "note": "배617 CTO 미해결 아님 — 08-14 종결 확인"},
            ]})
            name, ok, detail = ih.check_page_score_stale_ship_refs()
            assert ok is True, f"정정 신호 있는데도 걸림: {detail}"

            # 3) 큐에서 status=DONE 인 배 인용도 걸린다(아카이브 미등재라도)
            _write(page_score, {"pages": [
                {"name": "가짜화면2", "note": "배999 여전히 미해결"},
            ]})
            name, ok, detail = ih.check_page_score_stale_ship_refs()
            assert ok is False, f"큐 status=DONE 인 배 인용인데 통과함: {detail}"
        finally:
            ih.PAGE_SCORE, ih.LOCAL_QUEUE, ih.QUEUE_ARCHIVE = orig

    print("OK — 정정 신호 없는 끝난 배 인용=걸림, 정정 신호 있으면=통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
