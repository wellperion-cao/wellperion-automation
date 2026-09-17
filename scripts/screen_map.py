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

# ── 1차 정리 판정 (GM 지시 2026-09-17 「웰리랑 시토 판단으로 1차 정리」) ──
HITS_FILE = ROOT / "status" / "screen_hits.json"
# refs 대상 = HTML 아닌 저장소 추적 파일만. git ls-files 로 잡아 gitignore(.venv·profiles·graphify-out 등) 밖으로 빼고
# 1GB 훑기 시간을 줄인다(전체 rglob 이면 39,000여 파일 · 1GB — git 추적분만 쓰면 2,000여 파일 · 90MB).
REFS_PATHSPECS = [
    "scripts/**", "server/**", "status/**", "ssot/**",
    "*.json", "*.md", "*.py", "*.js", "*.gs", "*.ps1", "*.bat",
    "3. 웰페리온 가이드/**/*.js",
]
REFS_EXCLUDE_PARTS = {"qa_screenshots", "logs", "tmp", "node_modules", ".omc", "briefs", "kakao_agent"}
REFS_SELF_EXCLUDE = {"status/screen_map.json"}
# 로그·아카이브류는 "한때 언급됐다"는 것만 말해줄 뿐 지금 배선돼 쓰인다는 신호가 아니다 — refs 에서 뺀다.
REFS_LOG_NAME_RE = re.compile(r"\.jsonl$|_log(\.|_)|_archive|worklog|_ledger|^screen_hits\.json$", re.I)
# 이동 스텁이 아니어도 제목이 이럴 땐 같은 규칙(이동/폐기 안내문) 적용
STUB_TITLE_RE = re.compile(r"이동됨|이름이\s*바뀌었습니다|폐기")
# *.json·*.md 한 파일이 화면 이름을 이 개수 넘게 물면 "실제 배선"이 아니라 전체 화면을 훑어 만든
# 인벤토리·제안서다(ui_standard.json·page_hygiene_proposal_*.md 실측) — refs 집계에서 그 파일만 뺀다.
# *.py/*.js 는 threshold 를 넘게 걸어도(wordpress_admin_playwright.py 등) 진짜 배선이라 그대로 둔다.
REFS_INVENTORY_THRESHOLD = 15
REFS_INVENTORY_EXTS = (".json", ".md")
VERSION_RE = re.compile(r"[_\-(]?[vV]\d+(?:\.\d+)?[_\-)]?")


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


def refs_excluded(rel: str) -> bool:
    parts = rel.split("/")
    for part in parts[:-1]:
        if part in REFS_EXCLUDE_PARTS or part.startswith("_archive"):
            return True
    if rel in REFS_SELF_EXCLUDE or rel.lower().endswith(".html"):
        return True
    return bool(REFS_LOG_NAME_RE.search(parts[-1]))


def count_refs(basenames: set) -> dict:
    """basename(원문+퍼센트인코딩) 이 저장소 추적 텍스트 파일에 나오는 총 횟수. 파일당 한 번 읽어 정규식 한 번(join alternation)으로 훑는다."""
    variants = set()
    for bn in basenames:
        variants.add(bn)
        variants.add(quote(bn))
    pattern = re.compile("|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)))

    proc = subprocess.run(
        ["git", "ls-files", "--"] + REFS_PATHSPECS,
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    file_matches = {}
    for rel in proc.stdout.splitlines():
        rel = rel.strip()
        if not rel or refs_excluded(rel):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = list(pattern.finditer(text))
        if matches:
            file_matches[rel] = matches

    counts = defaultdict(int)
    for rel, matches in file_matches.items():
        if rel.lower().endswith(REFS_INVENTORY_EXTS):
            distinct = {m.group(0) for m in matches}
            if len(distinct) > REFS_INVENTORY_THRESHOLD:
                continue  # 전체 훑기 인벤토리 파일 — 실제 배선 신호 아님
        for m in matches:
            counts[m.group(0)] += 1

    # basename 단위로 합산(원문+인코딩 중복 카운트 방지)
    refs_by_basename = {}
    for bn in basenames:
        enc = quote(bn)
        n = counts.get(bn, 0)
        if enc != bn:
            n += counts.get(enc, 0)
        refs_by_basename[bn] = n
    return refs_by_basename


def load_hits() -> dict:
    if not HITS_FILE.exists():
        return {}
    try:
        return json.loads(HITS_FILE.read_text(encoding="utf-8")).get("hits", {})
    except (OSError, json.JSONDecodeError):
        return {}


def norm_title(title: str) -> str:
    t = re.sub(r"\s+", "", title)
    t = VERSION_RE.sub("", t)
    return t


def is_protected(e: dict) -> bool:
    """루트 진입점·모듈 카드에 실린 것·reports A3 보관 — 절대 정리 후보로 안 잡는다."""
    if e["folder"] == "(루트)" and e["rel"] == "index.html":
        return True
    if e.get("in_card"):
        return True
    if e["folder"] == "reports":
        return True
    return False


def mark_dup_titles(entries: list) -> dict:
    """제목(공백·판번호 제거) 이 같은 파일이 둘 이상이면 — 보호 대상 뺀 나머지 중 last_commit 이 확실히 더 오래된 쪽만 후보."""
    groups = defaultdict(list)
    for e in entries:
        key = norm_title(e["title"])
        if key:
            groups[key].append(e)
    dup_reason = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        candidates = [e for e in members if not is_protected(e)]
        comparable = [e for e in candidates if e["last_commit"]]
        if len(comparable) < 2:
            continue
        newest = max(comparable, key=lambda e: e["last_commit"])
        for e in comparable:
            if e is not newest and e["last_commit"] < newest["last_commit"]:
                dup_reason[e["no"]] = "제목 중복(오래된 쪽)"
    return dup_reason


def judge_verdict(e: dict, refs: int, hits30, dup_reason: str) -> tuple:
    """1차 정리 판정 — (verdict, reason). verdict ∈ {AI삭제,GM후보,유지,보류}."""
    if e["folder"] == "(루트)" and e["rel"] == "index.html":
        return "유지", "루트 진입"
    if e["folder"] == "reports":
        return "유지", "A3 보관"

    is_stub = bool(e.get("redirect_to")) or bool(STUB_TITLE_RE.search(e["title"]))
    if is_stub and refs == 0:
        if hits30 == 0:
            return "AI삭제", "이동스텁·참조0·접속0"
        if hits30 is None:
            return "보류", "이동스텁·참조0·접속기록 없음"
        return "유지", "이동스텁이지만 접속 있음"

    flags = e["flags"]
    cond_a = ("고립" in flags and refs == 0 and
              any(f in flags for f in ("임시", "오래됨", "제목없음")))
    if cond_a or dup_reason:
        if hits30 is not None and hits30 > 0:
            return "유지", ""
        if cond_a:
            hit_flags = [f for f in ("오래됨", "임시", "제목없음") if f in flags]
            return "GM후보", "고립·" + "·".join(hit_flags)
        return "GM후보", dup_reason

    return "유지", ""


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

    # ── 1차 정리 판정 ──
    refs_by_basename = count_refs({e["rel"].split("/")[-1] for e in entries})
    hits = load_hits()
    dup_reason_by_no = mark_dup_titles(entries)
    for e in entries:
        refs = refs_by_basename.get(e["rel"].split("/")[-1], 0)
        hit = hits.get("/" + e["rel"])
        hits30 = hit["n"] if hit else None
        verdict, reason = judge_verdict(e, refs, hits30, dup_reason_by_no.get(e["no"], ""))
        e["refs"] = refs
        e["hits30"] = hits30
        e["verdict"] = verdict
        e["reason"] = reason

    verdict_counts = defaultdict(int)
    for e in entries:
        verdict_counts[e["verdict"]] += 1
    ai_delete = [e["no"] for e in entries if e["verdict"] == "AI삭제"]

    out = {
        "_doc": "전체 화면(*.html) 링크 목록. scripts/screen_map.py 가 만든다 — 손으로 고치지 마라.",
        "generated": TODAY.isoformat(),
        "total": len(entries),
        "in_card": sum(1 for e in entries if e["in_card"]),
        "orphan": sum(1 for e in entries if "고립" in e["flags"]),
        "stale": sum(1 for e in entries if "오래됨" in e["flags"]),
        "stub": sum(1 for e in entries if "이동스텁" in e["flags"]),
        "verdict_counts": {
            "유지": verdict_counts.get("유지", 0),
            "GM후보": verdict_counts.get("GM후보", 0),
            "AI삭제": verdict_counts.get("AI삭제", 0),
            "보류": verdict_counts.get("보류", 0),
        },
        "ai_delete": ai_delete,
        "screens": entries,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    vc = out["verdict_counts"]
    print(f"screen_map: {out['total']}장 · 카드 {out['in_card']} · 고립 {out['orphan']} · 오래됨 {out['stale']} · 이동스텁 {out['stub']} -> {OUT}")
    print(f"1차 정리 판정: 유지 {vc['유지']} · GM후보 {vc['GM후보']} · AI삭제 {vc['AI삭제']} · 보류 {vc['보류']}")


if __name__ == "__main__":
    main()
