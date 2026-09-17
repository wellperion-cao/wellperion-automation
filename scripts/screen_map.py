#!/usr/bin/env python3
# 화면 지도 생성기 (GM 지시 2026-09-17 「전체 화면 페이지를 링크화 시켜서 정리해줘」)
# "3. 웰페리온 가이드" 아래 *.html 전부를 훑어 status/screen_map.json 을 만든다.
# 실행: C:/Python314/python.exe scripts/screen_map.py
import json
import re
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "3. 웰페리온 가이드"
OUT = ROOT / "status" / "screen_map.json"
TODAY = date(2026, 9, 17)

EXCLUDE_DIR_NAMES = {"tmp", "node_modules"}
TEMP_PAT = re.compile(r"초안|draft|backup|copy|v0\b|\bA-B\b", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r'href=["\']([^"\'#?]+)', re.I)
# 이동 스텁 = meta refresh 로 다른 화면으로 넘기기만 하는 파일(옛 주소 보존용)
REFRESH_RE = re.compile(r'http-equiv=["\']refresh["\'][^>]*url=([^"\'>\s]+)', re.I)
# 정본 주소 — 서버(nginx guide-alias)가 파일명 대신 쓰는 짧은 주소. 화면엔 이것만 보인다.
CANON_URL = {"wellperion_guide(main).html": "https://erp.wellperion.com/home"}


def excluded(path: Path) -> bool:
    for part in path.relative_to(GUIDE).parts[:-1]:
        if part in EXCLUDE_DIR_NAMES or part.startswith("_archive"):
            return True
    return False


def clean_text(raw: str) -> str:
    return TAG_RE.sub("", raw).strip()


def load_last_commits() -> dict:
    """git log 한 번으로 파일별 최근 커밋 날짜를 모은다."""
    proc = subprocess.run(
        ["git", "log", "--format=C\x1f%cs", "--name-only"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    last = {}
    cur_date = None
    for line in proc.stdout.splitlines():
        if line.startswith("C\x1f"):
            cur_date = line.split("\x1f", 1)[1]
        elif line.strip():
            last.setdefault(line, cur_date)
    return last


def load_modules() -> dict:
    """path(erp/ 기준 상대) -> 카드 name. 37장."""
    mpath = GUIDE / "erp" / "modules.json"
    data = json.loads(mpath.read_text(encoding="utf-8"))
    out = {}
    for m in data.get("modules", []):
        p = m.get("path")
        if not p:
            continue
        resolved = (GUIDE / "erp" / p).resolve()
        try:
            rel = resolved.relative_to(GUIDE).as_posix()
        except ValueError:
            continue
        out[rel] = m.get("name", "")
    return out


def main():
    files = sorted(
        p for p in GUIDE.rglob("*.html") if not excluded(p)
    )
    contents = {}
    for p in files:
        rel = p.relative_to(GUIDE).as_posix()
        try:
            contents[rel] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            contents[rel] = ""

    # 들어오는 링크 — href 값의 마지막 조각(파일명) 기준으로 센다.
    referrers = defaultdict(set)
    for rel, text in contents.items():
        for m in HREF_RE.finditer(text):
            href = m.group(1)
            if href.startswith(("http://", "https://", "mailto:", "javascript:", "tel:")):
                continue
            base = href.rstrip("/").split("/")[-1]
            if base.lower().endswith(".html"):
                referrers[base].add(rel)

    last_commits = load_last_commits()
    modules = load_modules()

    entries = []
    for i, p in enumerate(files, 1):
        rel = p.relative_to(GUIDE).as_posix()
        text = contents[rel]
        parts = rel.split("/")
        folder = parts[0] if len(parts) > 1 else "(루트)"

        m = TITLE_RE.search(text)
        title_src = "title"
        title = clean_text(m.group(1)) if m and clean_text(m.group(1)) else ""
        if not title:
            m = H1_RE.search(text)
            title = clean_text(m.group(1)) if m and clean_text(m.group(1)) else ""
            title_src = "h1" if title else "filename"
        if not title:
            title = p.stem
            title_src = "filename"

        url = CANON_URL.get(rel) or "https://erp.wellperion.com/" + "/".join(quote(seg) for seg in parts)
        git_key = "3. 웰페리온 가이드/" + rel
        last_commit = last_commits.get(git_key)
        rm = REFRESH_RE.search(text)
        redirect_to = rm.group(1).strip() if rm else None

        basename = parts[-1]
        inbound_files = referrers.get(basename, set()) - {rel}
        inbound = len(inbound_files)
        in_card = modules.get(rel)
        size_kb = round(p.stat().st_size / 1024, 1)

        flags = []
        if last_commit:
            y, mo, d = (int(x) for x in last_commit.split("-"))
            if (TODAY - date(y, mo, d)).days > 30:
                flags.append("오래됨")
        if inbound == 0 and not in_card:
            flags.append("고립")
        if title_src == "filename":
            flags.append("제목없음")
        if TEMP_PAT.search(p.stem):
            flags.append("임시")
        if redirect_to:
            flags = [f for f in flags if f != "고립"]  # 스텁은 들어오는 링크가 없는 게 정상
            flags.append("이동스텁")

        entry = {
            "no": i,
            "rel": rel,
            "url": url,
            "title": title,
            "folder": folder,
            "last_commit": last_commit,
            "in_card": in_card,
            "inbound": inbound,
            "size_kb": size_kb,
            "flags": flags,
        }
        if redirect_to:
            entry["redirect_to"] = redirect_to
        entries.append(entry)

    out = {
        "_doc": "전체 화면(*.html) 링크 목록. scripts/screen_map.py 가 만든다 — 손으로 고치지 마라.",
        "generated": TODAY.isoformat(),
        "total": len(entries),
        "in_card": sum(1 for e in entries if e["in_card"]),
        "orphan": sum(1 for e in entries if "고립" in e["flags"]),
        "stale": sum(1 for e in entries if "오래됨" in e["flags"]),
        "stub": sum(1 for e in entries if "이동스텁" in e["flags"]),
        "screens": entries,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"screen_map: {out['total']}장 · 카드 {out['in_card']} · 고립 {out['orphan']} · 오래됨 {out['stale']} · 이동스텁 {out['stub']} -> {OUT}")


if __name__ == "__main__":
    main()
