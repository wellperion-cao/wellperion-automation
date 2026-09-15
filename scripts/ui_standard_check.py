# -*- coding: utf-8 -*-
"""화면 UI 표준 — 규격을 읽고, 화면마다 얼마나 지키는지 센다.

왜 있나
-------
GM 지시 2026-09-14: "전체 페이지 디자인 UI/UX 표준화를 만들어서 ERP플랫폼 관리에 표로
잘 정리해주고, 그 표가 승인나면 전체적인 페이지에 반영이 되는걸 희망해"

규격 자체는 이미 있다 — `3. 웰페리온 가이드/assets/wp-ui.css`(간격·글자 단계)와
`erp/brand/tenant-wellperion.css`(색). 없던 것은 **지금 몇 장이 그걸 따르는지**다.
2026-09-14 첫 실측: 화면 184장 중 공통 규격을 링크한 것이 6장. 나머지는 각자 px 를 박아
쓴다(한 화면에 글자 크기 41종까지). GM 이 "뭔가 불편한데 왜 그런지 모르겠다"고 한 것의 숫자다.

무엇을 재나 — 다섯 가지. 전부 기계가 셀 수 있는 것만 둔다.
  1) 공통 규격 링크    assets/wp-ui.css 를 <link> 하는가
  2) 글자 단계        직접 박은 font-size 가짓수 (기준 6 이하 = 본문 5 + 표제 1)
  3) 색 단계          직접 박은 색(hex) 가짓수 (기준 12 이하)
  4) 모바일 폭        viewport meta 가 있는가
  5) 좌측 정렬·폭 최대  컨테이너에 폭 캡이 없는가 (scripts/layout_left_full.py 와 같은 판정)
  6) UX 19항목          헤드리스로 실제 렌더해 잰다(scripts/design_audit.py · 디자인 규칙집 UI/UX Pro Max
                        의 순수 HTML 항목: 터치 44px·키보드 초점·명암비 4.5·이모지 아이콘 0·반응형 사진·
                        폰 글자 16px·움직임 줄이기·오류 0 …). 걸린 항목 0 이 기준.
                        GM 2026-09-15 「시모가 성장한 것을 화면 UI/UX 까지 표준화」 — 규격(①~⑤)은 파일을 읽어
                        세고, UX(⑥)는 브라우저로 렌더해 센다. ⑥은 느리다(한 장 3~4초) — `--ux` 를 붙일 때만 잰다.

★"지킨다"의 뜻을 여기서 정한다. 화면이 규격을 링크하면 1번은 통과지만, 그 위에 px 를
  또 박으면 링크가 무의미하다 — 그래서 링크와 가짓수를 따로 센다.

인쇄 문서(A3·A4)와 대외 지면은 범위 밖이다 — 지면은 화면 규격을 따르지 않는다.

쓰는 법
-------
    python scripts/ui_standard_check.py           # 현황을 세어 화면에 찍는다
    python scripts/ui_standard_check.py --저장    # status/ui_standard.json 에 쓴다(화면이 읽는다)
    python scripts/ui_standard_check.py --저장 --ux   # ⑥ UX 까지(139장 ≈ 8분 · .venv 의 playwright 로 돈다)
    python scripts/ui_standard_check.py --자가점검
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = "3. 웰페리온 가이드"
OUT = os.path.join(ROOT, "status", "ui_standard.json")

공통규격 = "assets/wp-ui.css"

# 범위 밖 — 지면(인쇄)·대외 브랜드 화면·부품 조각. 화면 규격의 대상이 아니다.
제외조각 = ("_archive", "node_modules", "/tmp/", "\\tmp\\",
            "reports/", "reports\\", "회사문서", "/backups/", "\\backups\\")
제외이름 = ("_block.html", "_block_en.html", "_template.html")

기준 = {"글자단계": 6, "색단계": 12}

_폰트 = re.compile(r"font-size\s*:\s*([\d.]+)px")
_색 = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
_규칙 = re.compile(r"([^{}]+)\{([^{}]*)\}")
_폭캡 = re.compile(r"max-width\s*:\s*(\d{3,4})px")
_컨테이너 = re.compile(r"(^|[\s,>])(body|main|\.wrap\b|\.wrapper\b|\.container\b|\.page\b|\.content\b)", re.I)


def 화면들() -> list[str]:
    나온것 = []
    for p in glob.glob(os.path.join(ROOT, GUIDE, "**", "*.html"), recursive=True):
        p = os.path.relpath(p, ROOT)          # 어느 폴더에서 불러도 저장소 기준으로 센다
        정규 = p.replace("\\", "/")
        if any(x.replace("\\", "/") in 정규 for x in 제외조각):
            continue
        if re.search(r"_A[34]\b|_A[34]\.", 정규):      # 인쇄 지면
            continue
        이름 = 정규.rsplit("/", 1)[-1]
        if 이름.endswith(제외이름):
            continue
        나온것.append(p)
    return sorted(나온것)


def 스타일(s: str) -> str:
    """<style> 안쪽만. 주석은 걷어 낸다(주석 속 예시 색을 세면 숫자가 부풀어 오른다)."""
    덩어리 = re.findall(r"<style[^>]*>(.*?)</style>", s, re.S)
    return re.sub(r"/\*.*?\*/", "", "\n".join(덩어리), flags=re.S)


def 재기(경로: str, s: str) -> dict:
    st = 스타일(s)
    폭캡 = False
    for sel, 본문 in _규칙.findall(st):
        sel = sel.strip()
        if sel.startswith("@") or "@" in sel or not _컨테이너.search(sel):
            continue
        m = _폭캡.search(본문)
        if m and int(m.group(1)) >= 600:
            폭캡 = True
            break
    return {
        "화면": 경로.replace("\\", "/").replace(GUIDE + "/", ""),
        "공통규격": 공통규격 in s,
        "글자단계": len(set(_폰트.findall(st))),
        "색단계": len({c.lower() for c in _색.findall(st)}),
        "모바일폭": "viewport" in s[:4000],
        "폭최대": not 폭캡,
    }


def 통과(r: dict) -> bool:
    """여섯 가지를 다 채워야 「지킨다」다. 하나라도 빠지면 안 지키는 것이다.
    ⑥ UX 는 아직 안 잰 화면(ux걸림 None)이면 판정에서 뺀다 — 모르는 것을 통과로도 탈락으로도 세지 않는다."""
    ux = r.get("ux걸림")
    return (r["공통규격"] and r["글자단계"] <= 기준["글자단계"]
            and r["색단계"] <= 기준["색단계"] and r["모바일폭"] and r["폭최대"]
            and (ux is None or ux == 0))


def ux재기(경로들: list[str]) -> dict:
    """design_audit.py --json 을 한 프로세스로 돌려 화면별 걸린 항목 이름을 받는다.
    playwright 는 .venv 에만 있다 — 그 파이썬으로 부른다."""
    import subprocess
    venv = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    py = venv if os.path.isfile(venv) else sys.executable
    out = subprocess.run([py, os.path.join(ROOT, "scripts", "design_audit.py"), "--json", *경로들],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    결과 = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue
        결과[j["path"].replace("\\", "/")] = j.get("warn") if "warn" in j else None
    return 결과


def 세기(ux: bool = False, 이전: dict | None = None) -> dict:
    행 = []
    경로표 = {}
    for p in 화면들():
        s = io.open(os.path.join(ROOT, p), encoding="utf-8", errors="ignore").read()
        if "<style" not in s and 공통규격 not in s:
            continue                      # 자기 모양이 없는 조각 — 잴 것이 없다
        r = 재기(p, s)
        경로표[r["화면"]] = os.path.join(ROOT, p).replace("\\", "/")
        행.append(r)
    # ⑥ UX — --ux 면 지금 재고, 아니면 지난 실측값을 그대로 물려받는다(모르면 None)
    지난 = {x["화면"]: x for x in (이전 or {}).get("화면", [])}
    측정 = ux재기([경로표[r["화면"]] for r in 행]) if ux else {}
    for r in 행:
        k = 경로표[r["화면"]]
        if ux and 측정.get(k) is not None:
            r["ux걸림"] = len(측정[k]); r["ux항목"] = 측정[k]
        else:
            지 = 지난.get(r["화면"], {})
            r["ux걸림"] = 지.get("ux걸림"); r["ux항목"] = 지.get("ux항목")
        r["지킴"] = 통과(r)
    지킴 = sum(1 for r in 행 if r["지킴"])
    항목 = {k: sum(1 for r in 행 if (r[k] if isinstance(r[k], bool) else r[k] <= 기준[k]))
            for k in ("공통규격", "글자단계", "색단계", "모바일폭", "폭최대")}
    항목["UX"] = sum(1 for r in 행 if r.get("ux걸림") == 0)
    항목["UX잼"] = sum(1 for r in 행 if r.get("ux걸림") is not None)
    return {
        "_이 파일은": "화면 UI/UX 표준의 규격과 지금 지킴 현황. scripts/ui_standard_check.py 가 만든다 — 손으로 고치지 마라. 규격 정본은 assets/wp-ui.css(간격·글자)·erp/brand/tenant-wellperion.css(웰페리온 색)·erp/admin/platform_brand.css(웰페리온 랩스 색)이고, UX 항목은 scripts/design_audit.py(디자인 규칙집)가 렌더해 센다. 이 파일은 그것을 얼마나 지키는지 센 결과다.",
        "잰 때": datetime.now(KST).isoformat(timespec="seconds"),
        "기준": 기준,
        "화면수": len(행),
        "지킴수": 지킴,
        "항목별": 항목,
        "화면": sorted(행, key=lambda r: (r["지킴"], -r["글자단계"])),
    }


def 보고(d: dict) -> None:
    n, k = d["화면수"], d["지킴수"]
    print(f"\n■ 화면 UI/UX 표준 — 화면 {n}장 중 여섯 가지를 다 지키는 것 {k}장 ({k*100//max(n,1)}%)\n")
    이름 = {"공통규격": "공통 규격을 링크한다", "글자단계": f"글자 크기 {기준['글자단계']}종 이하",
            "색단계": f"직접 박은 색 {기준['색단계']}종 이하", "모바일폭": "모바일 폭 줄이 있다",
            "폭최대": "좌측 정렬·폭 최대", "UX": "UX 19항목 걸림 0"}
    for k2, v in d["항목별"].items():
        if k2 == "UX잼":
            continue
        분모 = d["항목별"].get("UX잼", 0) if k2 == "UX" else n
        print(f"  {이름[k2]:<22} {v:>4} / {분모}" + ("  (잰 화면 기준)" if k2 == "UX" else ""))
    안지킴 = [r for r in d["화면"] if not r["지킴"]]
    print(f"\n  안 지키는 화면 {len(안지킴)}장 — 글자 종류가 많은 순 10장")
    for r in sorted(안지킴, key=lambda x: -x["글자단계"])[:10]:
        print(f"    글자 {r['글자단계']:>3}종 · 색 {r['색단계']:>3}종  {r['화면'][-52:]}")
    print()


def 자가점검() -> None:
    좋은화면 = ('<html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width">'
                '<link rel="stylesheet" href="../assets/wp-ui.css">'
                '<style>.wrap{max-width:100%;margin:0}</style></head><body></body></html>')
    r = 재기("좋은.html", 좋은화면)
    assert r["공통규격"] and r["모바일폭"] and r["폭최대"], r
    assert r["글자단계"] == 0 and r["색단계"] == 0, r
    assert 통과(r), "멀쩡한 화면을 안 지킨다고 센다"

    나쁜화면 = ('<html><head><meta charset="utf-8"><style>'
                + "".join(f".a{i}{{font-size:{10+i}px;color:#0000{i:02d}}}" for i in range(9))
                + '.wrap{max-width:1180px;margin:0 auto}</style></head><body></body></html>')
    r2 = 재기("나쁜.html", 나쁜화면)
    assert not r2["공통규격"], "링크가 없는데 있다고 센다"
    assert r2["글자단계"] == 9, r2
    assert not r2["모바일폭"], "모바일 폭 줄이 없는데 있다고 센다"
    assert not r2["폭최대"], "폭 캡이 있는데 없다고 센다"
    assert not 통과(r2), "안 지키는 화면을 지킨다고 센다"

    주석화면 = ('<html><head><meta charset="utf-8"><style>'
                '/* 예: font-size:99px; color:#ABCDEF 는 세지 않는다 */'
                '.a{font-size:14px}</style></head><body></body></html>')
    r3 = 재기("주석.html", 주석화면)
    assert r3["글자단계"] == 1 and r3["색단계"] == 0, f"주석 속 예시를 센다: {r3}"

    r4 = dict(r); r4["ux걸림"] = 1
    assert not 통과(r4), "UX 걸림이 있는데 지킨다고 센다"
    r4["ux걸림"] = 0
    assert 통과(r4), "UX 걸림 0 인데 안 지킨다고 센다"
    print("자가점검 OK — 링크·글자·색·모바일 폭·좌측정렬 다섯 + UX 걸림을 각각 세고, 주석은 안 센다")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--저장", action="store_true", help=f"{OUT} 에 쓴다")
    ap.add_argument("--자가점검", action="store_true")
    ap.add_argument("--ux", action="store_true", help="⑥ UX 19항목을 헤드리스로 잰다(느림)")
    a = ap.parse_args()
    if a.자가점검:
        자가점검()
        return
    기존 = {}
    if os.path.isfile(OUT):
        try:
            기존 = json.load(io.open(OUT, encoding="utf-8"))
        except Exception:
            기존 = {}
    d = 세기(ux=a.ux, 이전=기존)
    보고(d)
    if a.저장:
        # 승인 상태는 사람이 정하는 값이라 재는 쪽이 덮지 않는다
        for k in ("승인", "승인일", "승인자", "반영"):
            if k in 기존:
                d[k] = 기존[k]
        io.open(OUT, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
        print(f"  → {OUT}")


if __name__ == "__main__":
    main()
