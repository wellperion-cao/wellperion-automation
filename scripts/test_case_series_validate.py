"""case_series_dispatch 의 편 검증이 슬라이드 장수·대본 파일명에 안 물리는지 확인.

배경(2026-08-10 · 배474): 「하루의 완성」 재가동으로 슬라이드가 6장에서 7장으로 늘고
대본 파일명 번호 체계도 전역(ep18)/폴더로컬(ep01) 두 벌로 갈렸는데, 발송 스크립트만
'post_1..6.jpg + _검수_미리보기_6장.png + ep{전역번호}_diary_source.html' 을 못 박고 있었다.
완성된 6편이 전부 '대본 불량'으로 걸러져 08-09 일요일 주간배치가 0/6 편 등록으로 끝났고,
승인 카드도 발행도 나가지 않았다. 에러 로그는 정직했지만 아무도 안 봤다.

실행: C:/Python314/python.exe scripts/test_case_series_validate.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import case_series_dispatch as m  # noqa: E402


def _make_folder(root: Path, *, slides: int, montage: str | None,
                 diary_name: str | None, caption: bool, name: str = "260810_테스트편") -> Path:
    folder = root / name
    (folder / "output").mkdir(parents=True, exist_ok=True)
    for i in range(1, slides + 1):
        (folder / "output" / f"post_{i}.jpg").write_bytes(b"x")
    if montage:
        (folder / "output" / montage).write_bytes(b"x")
    if diary_name:
        pads = '<div class="pad blue">x</div>' * 6
        (folder / diary_name).write_text(pads, encoding="utf-8")
    if caption:
        (folder / "caption.md").write_text("본문", encoding="utf-8")
    return folder


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        m.ROOT = root  # 검증 함수는 ROOT 기준 상대경로를 쓴다

        # 1) 7장 + 대본 파일명이 폴더로컬(ep01) — 전역번호 18 로 조회해도 통과해야 한다
        _make_folder(root, slides=7, montage="_검수_미리보기_7장.png",
                     diary_name="ep01_diary_source.html", caption=True)
        ok, why, diary, _ = m.validate_case_folder({"folder": "260810_테스트편", "num": 18})
        assert ok, f"7장·ep01 대본이 통과해야 한다 — 실제 사유: {why}"
        assert diary is not None and diary.name == "ep01_diary_source.html"
        ok2, _, montage = m.render_reuse_or_build({"folder": "260810_테스트편", "num": 18}, diary)
        assert ok2 and montage and montage.name == "_검수_미리보기_7장.png", "7장 렌더를 재사용해야 한다"

        # 2) 대본이 아예 없어도 슬라이드가 완성돼 있으면 통과 (렌더 재사용 경로)
        for p in root.rglob("ep01_diary_source.html"):
            p.unlink()
        ok, why, diary, _ = m.validate_case_folder({"folder": "260810_테스트편", "num": 19})
        assert ok, f"렌더 완료분은 대본 없이도 통과해야 한다 — 실제 사유: {why}"
        assert diary is None

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        m.ROOT = root

        # 3) 렌더도 대본도 없으면 여전히 막아야 한다
        _make_folder(root, slides=0, montage=None, diary_name=None, caption=True, name="c3")
        ok, why, _, _ = m.validate_case_folder({"folder": "c3", "num": 20})
        assert not ok and "대본 html 미존재" in why, f"빈 폴더는 막아야 한다 — 실제: {ok} / {why}"

        # 4) 슬라이드가 최소 장수 미만이면 대본 검증으로 떨어진다
        _make_folder(root, slides=3, montage="_검수_미리보기_3장.png",
                     diary_name=None, caption=True, name="c4")
        ok, why, _, _ = m.validate_case_folder({"folder": "c4", "num": 21})
        assert not ok, f"3장짜리는 완성으로 치면 안 된다 — 실제: {why}"

        # 5) caption.md 가 없으면 렌더가 다 됐어도 막는다
        _make_folder(root, slides=7, montage="_검수_미리보기_7장.png",
                     diary_name=None, caption=False, name="c5")
        ok, why, _, _ = m.validate_case_folder({"folder": "c5", "num": 22})
        assert not ok and "caption.md" in why, f"캡션 없으면 막아야 한다 — 실제: {ok} / {why}"

    print("OK — 5개 검증 통과")


if __name__ == "__main__":
    run()
