#!/usr/bin/env python3
"""
extract_glossary_quiz.py
------------------------
온보딩 게임 퀴즈의 원천을 용어사전(가이드허브 g6)으로 단일화하는 추출기.

입력:
    3. 웰페리온 가이드/wellperion_guide(main).html  의  id="g6"  (S3 용어 사전) article
    - g6 안의 탭 패널 중 "용어→정의" 2열(또는 확장자 3열) 표만 robust 파싱.
    - 복잡한 다열 표(문서 계층/8단계 프레임워크 등)는 용어/정의 쌍이 아니므로 자동 제외.

출력 1:
    3. 웰페리온 가이드/onboarding/quiz_bank.json
    -> [{ "term": ..., "def": ..., "category": ... }, ...]  (HTML 태그 제거·트림)

출력 2:
    3. 웰페리온 가이드/onboarding/game.html  의
        <!-- AUTO:QUIZBANK-START -->var GLOSSARY_BANK=[...];<!-- AUTO:QUIZBANK-END -->
    블록을 동일 데이터로 치환(인라인 주입 -> fetch 없이 file://·Pages 양쪽 작동).
    마커가 없으면 </script> 직전 적절한 위치에 1회 생성.

특징:
    - 멱등(여러 번 실행해도 동일 결과)·재실행 안전.
    - cp949 콘솔 안전(utf-8 reconfigure).

사용법:
    python scripts/extract_glossary_quiz.py
        -> quiz_bank.json + game.html AUTO:QUIZBANK 갱신 + 추출 개수 출력
    python scripts/extract_glossary_quiz.py --dry-run
        -> 변경 미리보기(파일 미수정)
"""

import argparse
import io
import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

# ── Windows CP949 환경에서 한글 출력 보장 ──────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 경로 ───────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE_DIR = REPO_ROOT / "3. 웰페리온 가이드"
GUIDE_HTML = GUIDE_DIR / "wellperion_guide(main).html"
ONBOARD_DIR = GUIDE_DIR / "onboarding"
QUIZ_BANK_JSON = ONBOARD_DIR / "quiz_bank.json"
GAME_HTML = ONBOARD_DIR / "game.html"

# ── game.html 인라인 주입 마커 ─────────────────────────────────────────────
# <script> 내부에 주입되므로 JS 주석 구문(/* */)을 사용한다.
# (HTML 주석 <!-- -->는 JS strict 모드에서 코드를 가려 깨짐 — 의도적 JS 호환 마커)
QB_START = "/* AUTO:QUIZBANK-START */"
QB_END = "/* AUTO:QUIZBANK-END */"

# 헤더 셀에 이 단어가 들어간 열을 "용어 / 정의(설명)" 열로 인식
TERM_HEADERS = ("용어", "확장자")
DEF_HEADERS = ("정의", "설명")


# ── g6 article 추출 ────────────────────────────────────────────────────────
def extract_g6_html(full_html: str) -> str:
    """id="g6" article 내부 HTML만 잘라낸다."""
    m = re.search(r'<article\b[^>]*\bid="g6"[^>]*>', full_html)
    if not m:
        raise SystemExit('[오류] id="g6" article을 찾지 못했습니다.')
    start = m.end()
    # 중첩 <article>는 g6 내부에 없음 -> 다음 </article>까지가 g6 본문.
    end = full_html.find("</article>", start)
    if end == -1:
        raise SystemExit('[오류] g6 article의 종료 태그를 찾지 못했습니다.')
    return full_html[start:end]


# ── 탭 패널 분해 (data-panel="..." 단위) ───────────────────────────────────
def split_panels(g6_html: str):
    """
    g6 내부를 data-panel 블록 단위로 (panel_name, panel_html) 리스트로 분해.
    표가 어느 패널(카테고리)에 속하는지 알기 위해 사용.
    """
    panels = []
    for m in re.finditer(r'data-panel="([^"]+)"\s*>', g6_html):
        name = m.group(1)
        panels.append((name, m.start(), m.end()))
    result = []
    for i, (name, _s, body_start) in enumerate(panels):
        body_end = panels[i + 1][1] if i + 1 < len(panels) else len(g6_html)
        result.append((name, g6_html[body_start:body_end]))
    return result


# 패널명 -> 사람이 읽는 카테고리 라벨
PANEL_LABEL = {
    "org": "조직·직급",
    "sys": "시스템·프로세스",
    "op": "운영 용어",
    "ext": "파일 확장자",
    "doc": "문서 유형",
}


# ── <table> 파서 (HTMLParser 기반, robust) ─────────────────────────────────
class TableParser(HTMLParser):
    """HTML 조각에서 <table>들을 행/셀(텍스트, th여부) 구조로 추출."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []  # [ [ [ (is_th, text), ... ], ... ], ... ]
        self._cur_table = None
        self._cur_row = None
        self._cur_cell = None  # buffer of text fragments
        self._cur_is_th = False
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._cur_table = []
        elif tag == "tr" and self._cur_table is not None:
            self._cur_row = []
        elif tag in ("td", "th") and self._cur_row is not None:
            self._in_cell = True
            self._cur_is_th = (tag == "th")
            self._cur_cell = []

    def handle_endtag(self, tag):
        if tag == "table" and self._cur_table is not None:
            self.tables.append(self._cur_table)
            self._cur_table = None
        elif tag == "tr" and self._cur_row is not None:
            self._cur_table.append(self._cur_row)
            self._cur_row = None
        elif tag in ("td", "th") and self._in_cell:
            text = " ".join("".join(self._cur_cell).split()).strip()
            self._cur_row.append((self._cur_is_th, text))
            self._in_cell = False
            self._cur_cell = None

    def handle_data(self, data):
        if self._in_cell:
            self._cur_cell.append(data)


def clean(text: str) -> str:
    """남은 엔티티 unescape + 공백 정규화."""
    return " ".join(unescape(text).split()).strip()


# ── 표 -> 용어/정의 쌍 추출 ────────────────────────────────────────────────
def rows_to_terms(table, category: str):
    """
    하나의 표(행 리스트)에서 용어/정의 쌍 추출.
    - 헤더 행(th)에서 '용어/확장자' 열과 '정의/설명' 열 인덱스를 찾는다.
    - 헤더가 그 패턴이 아니면(복잡한 다열 표) 빈 리스트 반환 -> 자동 제외.
    """
    if not table:
        return []

    # 헤더 행 탐색: th가 하나라도 있는 첫 행
    header = None
    for row in table:
        if any(is_th for is_th, _ in row):
            header = row
            break
    if header is None:
        return []

    headers = [clean(txt) for _is, txt in header]
    term_idx = def_idx = None
    for idx, h in enumerate(headers):
        if term_idx is None and any(k in h for k in TERM_HEADERS):
            term_idx = idx
        if def_idx is None and any(k in h for k in DEF_HEADERS):
            def_idx = idx
    # 용어/정의 2열 패턴이 아니면 이 표는 용어사전이 아님 -> 제외
    if term_idx is None or def_idx is None or term_idx == def_idx:
        return []

    out = []
    for row in table:
        # 헤더 행은 건너뜀
        if any(is_th for is_th, _ in row):
            continue
        cells = [clean(txt) for _is, txt in row]
        if term_idx >= len(cells) or def_idx >= len(cells):
            continue
        term = cells[term_idx]
        definition = cells[def_idx]
        if not term or not definition:
            continue
        out.append({"term": term, "def": definition, "category": category})
    return out


def extract_terms(full_html: str):
    g6 = extract_g6_html(full_html)
    terms = []
    seen = set()
    for panel_name, panel_html in split_panels(g6):
        category = PANEL_LABEL.get(panel_name, panel_name)
        p = TableParser()
        p.feed(panel_html)
        for table in p.tables:
            for entry in rows_to_terms(table, category):
                key = entry["term"]
                if key in seen:
                    continue
                seen.add(key)
                terms.append(entry)
    return terms


# ── game.html 인라인 주입 ──────────────────────────────────────────────────
def build_injection(terms) -> str:
    """AUTO:QUIZBANK 블록 전체 문자열(마커 포함)을 생성."""
    payload = json.dumps(terms, ensure_ascii=False, separators=(",", ":"))
    return QB_START + "var GLOSSARY_BANK=" + payload + ";" + QB_END


def inject_into_game(game_html: str, terms) -> str:
    block = build_injection(terms)
    start = game_html.find(QB_START)
    end = game_html.find(QB_END)
    if start != -1 and end != -1 and end > start:
        end += len(QB_END)
        return game_html[:start] + block + game_html[end:]
    # 마커 없음 -> <script> "use strict"; 직후에 1회 생성
    anchor = '"use strict";'
    pos = game_html.find(anchor)
    if pos == -1:
        # 최후수단: 첫 <script> 직후
        m = re.search(r"<script\b[^>]*>", game_html)
        if not m:
            raise SystemExit("[오류] game.html에 <script> 블록이 없어 주입 위치를 찾지 못했습니다.")
        pos = m.end()
        return game_html[:pos] + "\n" + block + "\n" + game_html[pos:]
    pos += len(anchor)
    return game_html[:pos] + "\n" + block + "\n" + game_html[pos:]


def main():
    ap = argparse.ArgumentParser(description="용어사전(g6) -> 온보딩 게임 퀴즈 은행 추출")
    ap.add_argument("--dry-run", action="store_true", help="파일 미수정, 변경 미리보기만")
    args = ap.parse_args()

    if not GUIDE_HTML.exists():
        raise SystemExit(f"[오류] 가이드 HTML 없음: {GUIDE_HTML}")
    if not GAME_HTML.exists():
        raise SystemExit(f"[오류] game.html 없음: {GAME_HTML}")

    full_html = GUIDE_HTML.read_text(encoding="utf-8")
    terms = extract_terms(full_html)

    if not terms:
        raise SystemExit("[오류] g6에서 용어를 1개도 추출하지 못했습니다. 표 구조를 확인하세요.")

    # 카테고리별 개수 집계
    by_cat = {}
    for t in terms:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1

    json_text = json.dumps(terms, ensure_ascii=False, indent=2) + "\n"
    game_html = GAME_HTML.read_text(encoding="utf-8")
    new_game_html = inject_into_game(game_html, terms)

    if args.dry_run:
        print("[dry-run] 변경 미리보기 (파일 미수정)")
    else:
        ONBOARD_DIR.mkdir(parents=True, exist_ok=True)
        QUIZ_BANK_JSON.write_text(json_text, encoding="utf-8")
        if new_game_html != game_html:
            GAME_HTML.write_text(new_game_html, encoding="utf-8")

    print(f"[완료] 용어 추출: {len(terms)}개")
    for cat, n in by_cat.items():
        print(f"   - {cat}: {n}개")
    print(f"   -> {QUIZ_BANK_JSON.relative_to(REPO_ROOT)}")
    print(f"   -> {GAME_HTML.relative_to(REPO_ROOT)} (AUTO:QUIZBANK 주입)")


if __name__ == "__main__":
    main()
