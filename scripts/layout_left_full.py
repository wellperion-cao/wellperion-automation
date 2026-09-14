# -*- coding: utf-8 -*-
"""ERP 화면 레이아웃 검사·수리 — 좌측 정렬 · 폭 최대 · 모바일 반응형.

왜 있나
-------
GM 지시(2026-07-02, 2026-09-14 재지시): "좌측 정렬로 폭을 최대로 해줘, 다른 것들도 항상
이렇게 해줘, 당연히 모바일은 또 맞춰줘."

규칙을 문서에만 적어 두니 새 화면이 계속 `max-width:1180px; margin:0 auto` 로 태어났다
(2026-09-14 실측 60개). 그래서 검사기로 박는다 — 문서가 아니라 이 파일이 판정한다.

무엇을 보나
-----------
화면마다 세 가지를 본다.
  1) 컨테이너(.wrap·.container·.page·body·main 등)에 폭 캡(max-width:NNNpx)이 걸렸나
  2) 그 컨테이너가 가운데로 몰렸나(margin:0 auto)
  3) 모바일에서 맞나 — viewport meta 가 있나

인쇄물은 건드리지 않는다
------------------------
A3·A4 보고서와 지면(@page)을 쓰는 문서는 폭 캡이 의도다 — 종이 크기가 정해져 있다.
대외 홈·회사소개서도 브랜드 지면이라 이 검사 범위 밖이다(제외 목록 참조).

쓰는 법
-------
    python scripts/layout_left_full.py              # 어긋난 화면을 센다(고치지 않음)
    python scripts/layout_left_full.py --고침        # 실제로 고친다
    python scripts/layout_left_full.py --자가점검    # 이 검사기가 제대로 잡는지
"""
from __future__ import annotations

import argparse
import glob
import io
import re
import sys

# 이 검사 범위 밖 — 인쇄 지면·대외 브랜드 지면·남의 소관.
제외조각 = (
    "회사문서",       # 회사소개서·제안서 = 인쇄 지면
    "public/", "public\\",     # 대외 홈(워드프레스 주입 블록)
    "reports/", "reports\\",   # A3·A4 보고서
    "cmo/home", "cmo\\home",   # 새 홈페이지 초안 = 브랜드 지면
    "/dietcamp/", "\\dietcamp\\",  # 업체 대외 홈 = 그 업체 브랜드 지면(시보 소관)
    "cfo/", "cfo\\",           # CFO 화면은 나우열M 소관 — AI 가 고치지 않는다
    "/tmp/", "\\tmp\\",
    "_archive", "node_modules",
)

# 소유자가 따로 있어 AI 가 직접 못 고치는 화면(GM 확정 2026-08-05). 담당 = 나우열M.
# 목록 정본은 safe_commit.py 의 도메인 가드다 — 여기 베껴 적지 않고 그걸 읽는다.
# 이 화면이 필요하면 텔레그램 업무관리 방으로 담당자에게 넘긴다.
def 남의도메인() -> tuple[str, ...]:
    try:
        import importlib.util
        스펙 = importlib.util.spec_from_file_location("_sc", "scripts/safe_commit.py")
        모듈 = importlib.util.module_from_spec(스펙)
        스펙.loader.exec_module(모듈)
        경로 = set()
        for _역할, _담당, 집합, _방, _메모 in 모듈.DOMAIN_MODIFY_RULES:
            경로 |= {str(x).replace("\\", "/") for x in 집합}
        return tuple(경로)
    except Exception:
        return ()

# 폭을 최대로 펴야 하는 자리. 카드·이미지·모달에 걸린 폭 캡은 건드리지 않는다.
컨테이너 = re.compile(
    r"(^|[\s,>])(body|main|\.wrap\b|\.wrapper\b|\.container\b|\.page\b|\.content\b"
    r"|#app\b|#root\b|\.layout\b|\.shell\b)",
    re.I,
)
규칙 = re.compile(r"([^{}]+)\{([^{}]*)\}")
폭캡 = re.compile(r"max-width\s*:\s*(\d{3,4})px")
가운데 = re.compile(r"margin\s*:\s*([^;]*\bauto\b[^;]*)|margin-inline\s*:\s*auto")
지면 = re.compile(r"@page\b|\bsize\s*:\s*A[34]\b", re.I)

최소캡 = 600  # 이보다 좁은 캡은 본문 읽기 폭(칼럼)이라 그대로 둔다

# 워드프레스에 주입되는 조각(wp_*·*_block)은 남의 지면 안에 들어간다 — 폭은 그 홈이 정한다.
주입블록 = ("wp_", "_block.html", "_block_en.html")


def 스타일들(s: str) -> list[str]:
    """주석은 먼저 걷어 낸다 — 안 걷으면 주석 뒤 선언이 셀렉터로 잡힌다."""
    return [re.sub(r"/\*.*?\*/", "", x, flags=re.S)
            for x in re.findall(r"<style[^>]*>(.*?)</style>", s, re.S)]


def 인쇄물인가(경로: str, s: str) -> bool:
    """인쇄 전용 문서인가.

    @page 나 @media print 는 '인쇄도 된다'는 뜻이지 인쇄 전용이라는 뜻이 아니다 —
    업무 화면 상당수가 인쇄 스타일을 함께 가진다. 파일 이름이 지면을 못 박은 것만 인쇄물로 본다.
    """
    return bool(re.search(r"_A[34]\b|_A[34]\.", 경로))


def 골격(스타일: str) -> str:
    """@media·@page·@supports 같은 덩어리를 통째로 들어낸다.

    미디어쿼리 안은 좁은 화면·인쇄 지면용이라 폭 캡이 의도다. 들어내지 않으면
    평탄한 정규식이 그 안쪽 규칙까지 바깥 규칙으로 잘못 읽는다.
    """
    남은, i = [], 0
    while i < len(스타일):
        m = re.compile(r"@[\w-]+[^{;]*\{").search(스타일, i)
        if not m:
            남은.append(스타일[i:])
            break
        남은.append(스타일[i:m.start()])
        깊이, j = 1, m.end()
        while j < len(스타일) and 깊이:
            깊이 += (스타일[j] == "{") - (스타일[j] == "}")
            j += 1
        i = j
    return "".join(남은)


def 진단(경로: str, s: str) -> dict:
    """이 화면이 규칙에서 어긋난 자리를 센다."""
    어긋남 = []
    for 스타일 in 스타일들(s):
        for sel, 본문 in 규칙.findall(골격(스타일)):
            sel = sel.strip()
            if sel.startswith("@") or not 컨테이너.search(sel):
                continue
            m = 폭캡.search(본문)
            if m and int(m.group(1)) >= 최소캡:
                어긋남.append((sel[:70], m.group(0), bool(가운데.search(본문))))
    return {
        "폭캡": 어긋남,
        "뷰포트없음": "viewport" not in s[:4000],
    }


def 짝폭값(s: str) -> set[str]:
    """컨테이너가 쓰는 폭 값을 모은다.

    헤더 바 안쪽(.hd-inner)·푸터 안쪽은 본문(.wrap)과 **같은 폭 값**으로 줄을 맞춘다.
    본문만 풀면 헤더는 가운데 남아 오히려 더 어긋나 보인다 — 같은 값은 같이 푼다.
    """
    값들 = set()
    for 스타일 in 스타일들(s):
        for sel, 본문 in 규칙.findall(골격(스타일)):
            sel = sel.strip()
            if sel.startswith("@") or not 컨테이너.search(sel):
                continue
            m = 폭캡.search(본문)
            if m and int(m.group(1)) >= 최소캡:
                값들.add(m.group(1))
    return 값들


def 고치기(s: str) -> tuple[str, int]:
    """컨테이너의 폭 캡을 풀고 좌측으로 붙인다. 좌우 padding 은 그대로 둔다."""
    고친수 = 0
    짝값 = 짝폭값(s)

    def 한블록(m):
        nonlocal 고친수
        sel, 본문 = m.group(1), m.group(2)
        if sel.strip().startswith("@"):
            return m.group(0)
        캡 = 폭캡.search(본문)
        if not 컨테이너.search(sel):
            # 컨테이너는 아니지만 같은 폭으로 줄 맞춘 짝(헤더·푸터 안쪽)이면 함께 푼다
            if not (캡 and 캡.group(1) in 짝값):
                return m.group(0)
        if not 캡 or int(캡.group(1)) < 최소캡:
            return m.group(0)
        새본문 = 폭캡.sub("max-width:100%", 본문, count=1)
        새본문 = re.sub(r"margin\s*:\s*0\s+auto\b", "margin:0", 새본문)
        새본문 = re.sub(r"margin\s*:\s*([\d.]+\w*)\s+auto\b", r"margin:\1 0", 새본문)
        새본문 = re.sub(r"margin-inline\s*:\s*auto", "margin-inline:0", 새본문)
        고친수 += 1
        return f"{sel}{{{새본문}}}"

    보관 = []

    def 접기(m):
        보관.append(m.group(0))
        return f"/*__주석{len(보관) - 1}__*/"

    임시 = re.sub(r"/\*.*?\*/", 접기, s, flags=re.S)

    def 덩어리접기(스타일본문: str) -> str:
        결과, i = [], 0
        while i < len(스타일본문):
            m = re.compile(r"@[\w-]+[^{;]*\{").search(스타일본문, i)
            if not m:
                결과.append(규칙.sub(한블록, 스타일본문[i:]))
                break
            결과.append(규칙.sub(한블록, 스타일본문[i:m.start()]))
            깊이, j = 1, m.end()
            while j < len(스타일본문) and 깊이:
                깊이 += (스타일본문[j] == "{") - (스타일본문[j] == "}")
                j += 1
            결과.append(스타일본문[m.start():j])
            i = j
        return "".join(결과)

    임시 = re.sub(r"(<style[^>]*>)(.*?)(</style>)",
                  lambda m: m.group(1) + 덩어리접기(m.group(2)) + m.group(3),
                  임시, flags=re.S)
    새 = re.sub(r"/\*__주석(\d+)__\*/", lambda m: 보관[int(m.group(1))], 임시)
    return 새, 고친수


def 뷰포트넣기(s: str) -> tuple[str, bool]:
    """모바일에서 화면 폭에 맞게 — 이 한 줄이 없으면 폰이 데스크톱 폭으로 그린다."""
    if "viewport" in s[:4000]:
        return s, False
    태그 = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    m = re.search(r"<meta\s+charset[^>]*>", s, re.I)
    if m:
        return s[: m.end()] + "\n" + 태그 + s[m.end():], True
    m = re.search(r"<head[^>]*>", s, re.I)
    if m:
        return s[: m.end()] + "\n" + 태그 + s[m.end():], True
    return s, False


def 잠긴경로() -> tuple[str, ...]:
    """GM 이 잠근 화면은 아무도 못 건드린다(status/reception_freeze.json).

    잠금 목록을 여기 베껴 적지 않고 그 파일을 읽는다 — 목록이 늘면 저절로 따라온다.
    """
    try:
        import json
        잠금 = json.load(io.open("status/reception_freeze.json", encoding="utf-8"))
    except Exception:
        return ()
    if not 잠금.get("locked"):
        return ()
    return tuple(str(x).replace("\\", "/") for x in 잠금.get("paths", []))


def 화면들() -> list[str]:
    나온것 = []
    잠김 = 잠긴경로() + 남의도메인()
    for p in glob.glob("3. 웰페리온 가이드/**/*.html", recursive=True):
        정규 = p.replace("\\", "/")
        if any(정규.startswith(x) or 정규 == x for x in 잠김):
            continue
        if any(x in 정규 for x in (c.replace("\\", "/") for c in 제외조각)):
            continue
        이름 = 정규.rsplit("/", 1)[-1]
        if 이름.startswith(주입블록[0]) or 이름.endswith(주입블록[1:]):
            continue
        나온것.append(p)
    return sorted(나온것)


def 돌기(고침: bool) -> int:
    어긋난화면 = 0
    고친블록 = 0
    뷰포트추가 = 0
    for p in 화면들():
        s = io.open(p, encoding="utf-8", errors="ignore").read()
        if not 스타일들(s) or 인쇄물인가(p, s):
            continue
        d = 진단(p, s)
        if not d["폭캡"] and not d["뷰포트없음"]:
            continue
        어긋난화면 += 1
        if 고침:
            새, n = 고치기(s)
            새, v = 뷰포트넣기(새)
            if n or v:
                io.open(p, "w", encoding="utf-8").write(새)
                고친블록 += n
                뷰포트추가 += int(v)
                print(f"  고침 {p}  (폭 {n}곳{' · 모바일 폭 1줄' if v else ''})")
        else:
            자리 = "; ".join(f"{a} {b}{' +중앙' if c else ''}" for a, b, c in d["폭캡"][:2])
            print(f"  {p}  {자리}{'  [모바일 폭 줄 없음]' if d['뷰포트없음'] else ''}")

    if 고침:
        print(f"\n화면 {어긋난화면}개 — 폭 {고친블록}곳, 모바일 폭 줄 {뷰포트추가}개 추가")
    else:
        print(f"\n어긋난 화면 {어긋난화면}개 (고치려면 --고침)")
    return 어긋난화면


def 자가점검() -> None:
    나쁜화면 = """<html><head><meta charset="utf-8"><style>
      .wrap{max-width:1180px; margin:0 auto; padding:24px 20px;}
      .card{max-width:720px;}
      .col{max-width:480px; margin:0 auto;}
    </style></head><body><div class="wrap"></div></body></html>"""

    d = 진단("시험.html", 나쁜화면)
    assert len(d["폭캡"]) == 1, f"컨테이너 하나만 잡아야 한다: {d['폭캡']}"
    assert d["폭캡"][0][2] is True, "가운데 몰린 것을 못 잡는다"
    assert d["뷰포트없음"] is True, "모바일 폭 줄 없는 것을 못 잡는다"

    고쳐진, n = 고치기(나쁜화면)
    assert n == 1, f"고친 자리 수가 다르다: {n}"
    assert "max-width:100%" in 고쳐진, "폭을 안 풀었다"
    assert "margin:0;" in 고쳐진 or "margin:0 " in 고쳐진, "좌측으로 안 붙였다"
    assert "padding:24px 20px" in 고쳐진, "좌우 여백을 지웠다 — 글이 화면 끝에 붙는다"
    assert ".card{max-width:720px;}" in 고쳐진, "카드 폭까지 풀었다"
    assert "max-width:480px" in 고쳐진, "읽기 폭(600px 미만)까지 건드렸다"

    고쳐진, v = 뷰포트넣기(고쳐진)
    assert v and "width=device-width" in 고쳐진, "모바일 폭 줄을 안 넣었다"
    assert not 진단("시험.html", 고쳐진)["폭캡"], "고친 뒤에도 걸린다"

    좋은화면 = '<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>.wrap{max-width:100%; margin:0; padding:24px 20px;}</style></head><body></body></html>'
    d2 = 진단("좋은.html", 좋은화면)
    assert not d2["폭캡"] and not d2["뷰포트없음"], f"멀쩡한 화면을 잡는다: {d2}"

    주석낀화면 = """<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>
      /* 2026-07-15 여백 축소: 상 34 → 20 */
      .wrap{max-width:1080px; margin:0 auto;}
    </style></head><body></body></html>"""
    d3 = 진단("주석.html", 주석낀화면)
    assert len(d3["폭캡"]) == 1 and d3["폭캡"][0][0].strip() == ".wrap", f"주석을 셀렉터로 읽는다: {d3['폭캡']}"
    고쳐진3, n3 = 고치기(주석낀화면)
    assert n3 == 1 and "2026-07-15 여백 축소" in 고쳐진3, "고치면서 주석을 잃었다"

    미디어낀화면 = """<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>
      .wrap{max-width:1180px; margin:0 auto;}
      @media print{ @page{size:A4} .wrap{max-width:190mm; margin:0 auto;} .tbl{max-width:900px} }
      @media(max-width:900px){ .wrap{padding:0 12px} .side{max-width:700px; margin:0 auto} }
    </style></head><body></body></html>"""
    d4 = 진단("미디어.html", 미디어낀화면)
    assert len(d4["폭캡"]) == 1, f"미디어쿼리 안쪽까지 잡는다: {d4['폭캡']}"
    고쳐진4, n4 = 고치기(미디어낀화면)
    assert n4 == 1, f"미디어쿼리 안쪽까지 고친다: {n4}"
    assert "max-width:190mm" in 고쳐진4, "인쇄 지면 폭을 건드렸다"
    assert "max-width:700px" in 고쳐진4, "좁은 화면 규칙을 건드렸다"
    assert ".tbl{max-width:900px}" in 고쳐진4, "인쇄 표 폭을 건드렸다"

    assert 인쇄물인가("reports/260901_A3.html", "<html>"), "A3 보고서를 인쇄물로 안 본다"
    assert not 인쇄물인가("erp/x.html", "<style>@media print{@page{size:A4}}</style>"),         "인쇄 스타일을 가진 업무 화면까지 인쇄물로 본다"

    print("자가점검 OK — 컨테이너만 고르고, 카드·읽기폭·여백·인쇄물은 건드리지 않는다")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--고침", action="store_true", help="실제로 고친다")
    ap.add_argument("--자가점검", action="store_true")
    a = ap.parse_args()
    if a.자가점검:
        자가점검()
        return
    sys.exit(1 if 돌기(a.고침) and not a.고침 else 0)


if __name__ == "__main__":
    main()
