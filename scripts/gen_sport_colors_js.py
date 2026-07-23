# -*- coding: utf-8 -*-
"""
scripts/sport_colors.py (SPORT_DOT 단일 출처) → 3. 웰페리온 가이드/_assets/sport_colors.js 생성기.

브라우저 JS는 .py를 import 할 수 없으므로, 색표를 페이지에 손으로 다시 베끼는 대신 이 스크립트로
'파생'시킨다 — 정본은 여전히 scripts/sport_colors.py 하나(약속 L01 '한 곳만 본다'). 값을 바꿀 땐
sport_colors.py 만 고치고 이 스크립트를 다시 실행해 .js 를 재생성한다(손 편집 금지 — 아래 생성 파일
상단에 경고 주석 포함).

사용: C:\\Python314\\python.exe scripts\\gen_sport_colors_js.py
"""
from __future__ import annotations

import json
from pathlib import Path

from sport_colors import SPORT_DOT

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "3. 웰페리온 가이드" / "_assets" / "sport_colors.js"


def render_js() -> str:
    table_json = json.dumps(SPORT_DOT, ensure_ascii=False)
    return (
        "// AUTO-GENERATED — 손 편집 금지.\n"
        "// 정본 = scripts/sport_colors.py (SPORT_DOT). 값이 바뀌면 그 파일을 고치고\n"
        "// `C:\\Python314\\python.exe scripts\\gen_sport_colors_js.py` 로 이 파일을 다시 생성하세요.\n"
        "// 매칭 알고리즘(키워드 부분포함·대소문자 무시·표 순서상 첫 매치)도 Python 쪽과 동일해야 합니다.\n"
        f"var SPORT_DOT_TABLE = {table_json};\n"
        "function sportDot(name) {\n"
        "  var k = String(name || '').trim().toLowerCase();\n"
        "  if (!k) return '';\n"
        "  for (var i = 0; i < SPORT_DOT_TABLE.length; i++) {\n"
        "    var kw = SPORT_DOT_TABLE[i][0], dot = SPORT_DOT_TABLE[i][1];\n"
        "    if (k.indexOf(kw.toLowerCase()) >= 0) return dot;\n"
        "  }\n"
        "  return '';\n"
        "}\n"
    )


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render_js(), encoding="utf-8")
    print(f"[생성 완료] {OUT_PATH} ({len(SPORT_DOT)}개 항목)")


if __name__ == "__main__":
    main()
