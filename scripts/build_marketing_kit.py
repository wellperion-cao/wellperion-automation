# -*- coding: utf-8 -*-
"""마케팅 자동화 셋업 킷을 한 파일로 묶어 ERP 다운로드 자리에 놓는다 (배1152).

GM 2026-09-09: "모듈을 다운로드 받아서 바로 셋팅할 수 있도록" · "ERP 관리자 페이지 다운로드 페이지에".

원본 = `3. 웰페리온 가이드/cmo/kit/` · 묶음 = `3. 웰페리온 가이드/erp/launchers/마케팅자동화_셋업킷.zip`
목록 한 줄은 `3. 웰페리온 가이드/erp/downloads.json` 에 넣는다(화면은 안 고친다 — 그 파일 규칙 그대로).

★비밀값 금지: 이 자리는 여러 사람이 받아 가는 곳이다. 토큰·비밀번호·열쇠가 든 파일은
넣지 않는다. 넣으려 하면 아래 검사가 막는다.

    C:/Python314/python.exe scripts/build_marketing_kit.py
    C:/Python314/python.exe scripts/build_marketing_kit.py --self-check
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "3. 웰페리온 가이드" / "cmo" / "kit"
OUT = ROOT / "3. 웰페리온 가이드" / "erp" / "launchers" / "마케팅자동화_셋업킷.zip"
DOWNLOADS = ROOT / "3. 웰페리온 가이드" / "erp" / "downloads.json"

담을것 = ["셋업안내.md", "새업체_마케팅설정.json", "셋업.py"]

# 비밀값처럼 보이는 것. 하나라도 걸리면 묶지 않는다.
비밀냄새 = [
    re.compile(r"(?i)(password|passwd|secret|private[_-]?key)\s*[:=]\s*\S"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(sk|ghp|xox[baprs])-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
]


def 비밀검사(text: str) -> list[str]:
    return [p.pattern for p in 비밀냄새 if p.search(text)]


def build() -> Path:
    없는것 = [f for f in 담을것 if not (KIT / f).exists()]
    if 없는것:
        raise SystemExit(f"원본이 없다: {없는것}")

    for f in 담을것:
        걸린것 = 비밀검사((KIT / f).read_text(encoding="utf-8"))
        if 걸린것:
            raise SystemExit(f"비밀값처럼 보이는 것이 {f} 에 있다 — 묶지 않는다: {걸린것}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in 담을것:
            z.write(KIT / f, arcname=f"마케팅자동화_셋업킷/{f}")
    return OUT


def register() -> bool:
    """다운로드 목록에 한 줄. 이미 있으면 설명만 갱신한다(줄이 두 개가 되지 않게)."""
    d = json.loads(DOWNLOADS.read_text(encoding="utf-8"))
    항목 = {
        "id": "marketing-automation-kit",
        "name": "마케팅 자동화 셋업 킷",
        "desc": "새로 맡는 업체 하나를 세우는 꾸러미. 압축을 풀고 셋업안내.md 부터 읽으면 된다. 비밀값은 들어 있지 않다.",
        "file": f"launchers/{OUT.name}",
        "for": "C-Level · 영업",
    }
    목록 = d["downloads"]
    for i, x in enumerate(목록):
        if x.get("id") == 항목["id"]:
            if x == 항목:
                return False
            목록[i] = 항목
            break
    else:
        목록.append(항목)
    DOWNLOADS.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def self_check() -> None:
    assert 비밀검사("password: hunter2"), "비밀번호 줄을 못 잡는다"
    assert 비밀검사("AKIA" + "IOSFODNN7EXAMPLE"), "AWS 열쇠를 못 잡는다"  # secret-ok: AWS 공식 문서의 예시 키 · 검사기가 실제로 잡는지 보는 자가점검용
    assert not 비밀검사("문의 주소는 https://example.com/inquiry 입니다"), "멀쩡한 줄을 잘못 잡는다"
    z = build()
    with zipfile.ZipFile(z) as f:
        이름들 = f.namelist()
    assert len(이름들) == len(담을것), 이름들
    print("self-check OK ·", z.name, f"{z.stat().st_size:,}바이트 ·", len(이름들), "개")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        self_check()
    else:
        z = build()
        바뀜 = register()
        print(f"묶었다 → {z}  ({z.stat().st_size:,}바이트)")
        print("다운로드 목록", "갱신함" if 바뀜 else "이미 같음")
