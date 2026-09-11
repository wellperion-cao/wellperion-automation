# -*- coding: utf-8 -*-
"""색 정본을 물린 화면이 다시 제 색을 적는 것을 막는다 (GM 지시 2026-09-11).

GM: "디자인 관련해서 통일되게 할순없나? 이 부분에 대해서 디테일이 너무약하네"

화면이 erp/brand/*.css 를 <link> 해 놓고 자기 <style> 안에서 --bg·--text·--accent 를
또 적으면, 정본을 고쳐도 그 화면만 안 따라온다. 2026-09-09 에 업무 현황 SSOT 가
그렇게 혼자 베이지로 떠 있었고 GM 이 이틀 뒤 발견하셨다.

인쇄(@media print) 안의 재정의는 뜻이 다르다 — 흰 종이에 맞추는 것이라 검사에서 뺀다.
그래서 bash grep 이 아니라 여기서 중괄호를 세어 print 블록을 통째로 지우고 본다.

exit 1 = 커밋 중단 / exit 0 = 통과. 우회 = env SKIP_BRAND_TOKEN_GUARD=1 또는 --no-verify.
"""
import io, re, subprocess, sys

TOKENS = re.compile(r"--(?:bg|paper|text|dim|accent|border)\s*:")
PRINT_AT = re.compile(r"@media[^{]*\bprint\b[^{]*\{")


def strip_print_blocks(css: str) -> str:
    """@media print { ... } 를 중괄호 짝을 세어 통째로 지운다."""
    out, i = [], 0
    while True:
        m = PRINT_AT.search(css, i)
        if not m:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:m.start()])
        depth, j = 1, m.end()
        while j < len(css) and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j


def staged_html():
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    for line in r.stdout.splitlines():
        if line.endswith(".html") and line.startswith("3. "):
            yield line


def main() -> int:
    bad = []
    for path in staged_html():
        try:
            s = io.open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "erp/brand/" not in s:
            continue                      # 정본을 안 물린 화면은 이 가드 대상이 아니다
        body = strip_print_blocks(s)
        # 주석 안의 토큰 이름은 설명이라 세지 않는다
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        n = len(TOKENS.findall(body))
        if n:
            bad.append((path, n))
    if not bad:
        return 0
    print("[brand-token-guard][BLOCK] 색 정본을 물려 놓고 색을 또 적은 화면이 있다.")
    for path, n in bad:
        print("  %s — %d곳" % (path, n))
    print("  고치는 곳은 정본 한 파일이다:")
    print("    업무·결재 현황판 = 3. 웰페리온 가이드/erp/brand/ssot-board.css")
    print("    그 밖 파트너사 화면 = 3. 웰페리온 가이드/erp/brand/tenant-wellperion.css")
    return 1


if __name__ == "__main__":
    sys.exit(main())
