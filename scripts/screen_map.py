#!/usr/bin/env python3
# 화면 지도 생성기 (GM 지시 2026-09-17 「전체 화면 페이지를 링크화 시켜서 정리해줘」)
# "3. 웰페리온 가이드" 아래 *.html 전부를 훑어 status/screen_map.json 을 만든다.
# 실행: C:/Python314/python.exe scripts/screen_map.py
#       C:/Python314/python.exe scripts/screen_map.py --apply   ← AI삭제 판정 실제로 지우고 재생성(GM 승인 건만)
#       C:/Python314/python.exe scripts/screen_map.py --prune [--apply]  ← 이동스텁·30일·접속0 대상만 따로(주 1회용 · 오늘은 안 돌림)
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "3. 웰페리온 가이드"
OUT = ROOT / "status" / "screen_map.json"
TODAY = date(2026, 9, 17)
DELETED_KEY = "deleted_2026_09_17"

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

# 옛 판 탐지 — 같은 폴더·같은 줄기 이름에서 이 토큰만 다르면 "판이 여럿" (GM 지시 2026-09-17 13:1x)
STALE_VER_RE = re.compile(r"(_v\d+(?:\.\d+)?|v\d+(?:\.\d+)?|\(A\)|\(B\)|_old|_backup|_copy|_초안|초안|_최종|최종)", re.I)

# 종류 판정(GM 확정 2026-09-17 13:1x 「업무와 문서의 차이」) — 낱말 먼저, 폴더는 그 다음 보조.
KIND_WORK_WORD_RE = re.compile(r"선물세트|안내판|운영지침|채용공고|기획|의견제출서|현수막|A3|A4|검토|비교|견적|보고")
KIND_DOC_WORD_RE = re.compile(r"소개서|로드맵|브랜드가이드|가이드|매뉴얼|규정|헌법|약속")
KIND_DOC_PREFIXES = ("회사문서/", "cmo/brand/")
KIND_WORK_PREFIXES = ("reports/",)
KIND_WORK_A3_RE = re.compile(r"^\d{6}_.*_A[34]\b")

# 외부 삽입 — 워드프레스·공개 사이트에 끼워 쓰는 블록/위젯. erp 접속 0 이 정상이라
# 고립·접속0 판정(GM후보·AI삭제)에서 뺀다(GM 지시 2026-09-17 13:1x·보정).
# 규칙 = 파일명이 wp_ 로 시작 / _block(.html·_en.html) 로 끝남 / chat_widget.html / public/** (아래 is_external_embed 에서 처리).
EXTERNAL_EMBED_RE = re.compile(r"^wp_|_block(_en)?\.html$|^chat_widget\.html$", re.I)

# 웰리 판단 (GM후보에만 표시) — 문서·업무 kind 별 권고 한 낱말.
WELLY_DOC_KEEP_RE = re.compile(r"매뉴얼|가이드")
WELLY_DOC_DELETE_RE = re.compile(r"초안|샘플|draft|요약", re.I)
WELLY_WORK_FRESH_DAYS = 60

# 백업류 파일명 — 판번호와 무관하게 항상 자동삭제 대상(GM 지시).
BACKUP_NAME_RE = re.compile(r"\.bak_|backup|_copy", re.I)

# weekly_page_hygiene.py 의 PAGE_TARGETS 가 open() 으로 실제로 여는 "리다이렉트 스텁" 들 —
# 위생 자동화가 매주 감사·수정하는 대상이라 hits==0 이어도 지우면 안 된다(2026-09-17 실측 확인).
# index.html 은 별도로 항상 보호(is_protected)돼 있어 여기 안 넣는다.
KNOWN_ACTIVE_STUB_RELS = frozenset({"northstar_today.html", "wellperion_dashboard_web.html", "항해지도.html"})

# GM후보 A(삭제는 GM 판단) — 파일명·제목에 이 낱말이 있으면 "만들다 만 것" 신호.
GM_A_NAME_RE = re.compile(r"초안|샘플|draft", re.I)
GM_A_MIN_AGE_DAYS = 7          # 만든 지 이만큼 안 됐으면 아직 작업 중일 수 있어 후보에서 뺀다.
GM_B_MIN_AGE_DAYS = 14         # 업무 산출물이 이만큼 안 건드려졌으면 "끝난 일" 로 본다.
PRUNE_MIN_AGE_DAYS = 30        # --prune 전용(주 1회) — 이동스텁이 이만큼 오래+접속0.


def excluded(path: Path) -> bool:
    for part in path.relative_to(GUIDE).parts[:-1]:
        if part in EXCLUDE_DIR_NAMES or part.startswith("_archive"):
            return True
    return False


def clean_text(raw: str) -> str:
    return TAG_RE.sub("", raw).strip()


def md(iso_date):
    """'2026-09-07' -> '9/7'. 없으면 그대로 돌려준다."""
    if not iso_date:
        return iso_date
    y, mo, d = iso_date.split("-")
    return f"{int(mo)}/{int(d)}"


def days_since(iso_date) -> int:
    """iso_date 로부터 오늘까지 며칠. 날짜가 없으면 아주 큰 수(=오래된 것으로 안 본다는 뜻이 아니라
    "모른다"를 나타내되, 나이 조건은 통과시키지 않도록 호출부에서 None 을 따로 챙긴다)."""
    if not iso_date:
        return -1
    y, mo, d = (int(x) for x in iso_date.split("-"))
    return (TODAY - date(y, mo, d)).days


def _parse_git_log(args) -> dict:
    """git log --name-only 한 번을 파일별 커밋일 딕셔너리로 접는다. setdefault 라 먼저 만난 날짜가 남는다."""
    proc = subprocess.run(
        ["git", "log", "--format=C\x1f%cs", "--name-only"] + args,
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = {}
    cur_date = None
    for line in proc.stdout.splitlines():
        if line.startswith("C\x1f"):
            cur_date = line.split("\x1f", 1)[1]
        elif line.strip():
            out.setdefault(line, cur_date)
    return out


def load_last_commits() -> dict:
    """최신→과거 순으로 훑어 먼저 만난 날짜 = 가장 최근 커밋일."""
    return _parse_git_log([])


def load_first_commits() -> dict:
    """--reverse(과거→최신) 로 훑어 먼저 만난 날짜 = 처음 생긴 날(= "만든 지 며칠" 계산용)."""
    return _parse_git_log(["--reverse"])


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


def load_hits() -> tuple:
    """(hits_dict, since, until). 로그 보존 11일 실측(시토 2026-09-17) — 파일에 없는 경로는 0 접속으로 본다."""
    if not HITS_FILE.exists():
        return {}, None, None
    try:
        data = json.loads(HITS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, None, None
    return data.get("hits", {}), data.get("since"), data.get("until")


def norm_title(title: str) -> str:
    t = re.sub(r"\s+", "", title)
    t = VERSION_RE.sub("", t)
    return t


def stem_key(rel: str) -> tuple:
    """폴더 + 판번호 뗀 줄기 이름. 같은 폴더 안에서만 "같은 화면의 다른 판"으로 본다."""
    dirpart, _, base = rel.rpartition("/")
    name = base[:-5] if base.lower().endswith(".html") else base
    s = STALE_VER_RE.sub("", name)
    s = s.strip("_-")
    return dirpart, s


def is_external_embed(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return bool(EXTERNAL_EMBED_RE.search(name)) or rel.startswith("public/") or "/public/" in rel


def classify_kind(rel: str, title: str) -> str:
    """문서(회사가 계속 갖는 정본) / 업무(끝이 있는 산출물) / 화면(그 외 앱 화면).
    GM 확정 2026-09-17 13:1x — 파일명·제목 낱말이 먼저, 폴더는 낱말로 못 가를 때만 보조로 쓴다."""
    name = rel.rsplit("/", 1)[-1]
    hay = name + " " + title
    if KIND_DOC_WORD_RE.search(hay):
        return "문서"
    if KIND_WORK_WORD_RE.search(hay):
        return "업무"
    if rel.startswith(KIND_DOC_PREFIXES) or rel.startswith("erp/admin/company"):
        return "문서"
    if rel.startswith(KIND_WORK_PREFIXES) or (rel.startswith("coo/chairman/") and KIND_WORK_A3_RE.search(name)):
        return "업무"
    return "화면"


def welly_judge(e: dict) -> str:
    """GM후보 표의 「웰리 판단」 열 — reason 옆에 붙는 권고 한 낱말(GM 지시 2026-09-17 13:5x)."""
    name = e["rel"].rsplit("/", 1)[-1]
    hay = name + " " + e["title"]
    if e["kind"] == "문서":
        if WELLY_DOC_KEEP_RE.search(hay):
            return "유지·링크 걸기"
        if WELLY_DOC_DELETE_RE.search(hay):
            return "삭제 권고"
    elif e["kind"] == "업무" and e["last_commit"] and days_since(e["last_commit"]) <= WELLY_WORK_FRESH_DAYS:
        return "유지·업무 첨부"
    return "GM 판단"


META_DESC_RE = re.compile(r'<meta\b[^>]*\bname=["\']description["\'][^>]*\bcontent=["\']([^"\']*)["\']', re.I)
META_DESC_RE2 = re.compile(r'<meta\b[^>]*\bcontent=["\']([^"\']*)["\'][^>]*\bname=["\']description["\']', re.I)
LEAD_CLASS_RE = re.compile(r'<(?:div|p)[^>]*class=["\'][^"\']*\b(?:sub|lead)\b[^"\']*["\'][^>]*>(.*?)</(?:div|p)>', re.I | re.S)
FIRST_P_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.I | re.S)


SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)


def extract_essence(text: str, title: str) -> str:
    """본질·핵심 한 줄 — <meta description> -> h1 다음 첫 문단(.sub/.lead/p) -> title 순. 60자 자름.
    <script> 안 문자열이 '<p>' 처럼 보여 오검출되는 것을 막으려 스크립트 블록은 먼저 걷어낸다."""
    text = SCRIPT_RE.sub("", text)
    m = META_DESC_RE.search(text) or META_DESC_RE2.search(text)
    raw = clean_text(m.group(1)) if m else ""
    if not raw:
        hm = H1_RE.search(text)
        if hm:
            rest = text[hm.end():]
            pm = LEAD_CLASS_RE.search(rest) or FIRST_P_RE.search(rest)
            if pm:
                raw = clean_text(pm.group(1))
    if not raw:
        raw = title
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:60]


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


def mark_stale_versions(entries: list, referrers: dict) -> dict:
    """같은 폴더·같은 줄기 이름(판번호만 다름) 이 둘 이상 — 오래된 쪽이 접속0·참조0·inbound0 이고
    새 판이 그 옛 판을 href 로 안 가리킬 때만 자동삭제 후보(GM 승인 2026-09-17 13:1x)."""
    groups = defaultdict(list)
    for e in entries:
        if is_protected(e):
            continue
        key = stem_key(e["rel"])
        if key[1]:
            groups[key].append(e)

    reason = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        comparable = [e for e in members if e["last_commit"]]
        if len(comparable) < 2:
            continue
        newest = max(comparable, key=lambda e: e["last_commit"])
        for e in comparable:
            if e is newest or e["last_commit"] >= newest["last_commit"]:
                continue
            old_basename = e["rel"].split("/")[-1]
            if newest["rel"] in referrers.get(old_basename, set()):
                continue  # 새 판이 옛 판을 가리킴 — 보존
            if e["refs"] == 0 and e["inbound"] == 0 and e["hits"] == 0:
                reason[e["no"]] = "옛 판(새 판 있음)"
    return reason


def judge_verdict(e: dict, hits_since, hits_until, dup_reason: str, stale_reason: str) -> tuple:
    """1차 정리 판정 — (verdict, reason, gm_tier). verdict ∈ {AI삭제,GM후보,유지}. gm_tier ∈ {A,B,None}."""
    if e["folder"] == "(루트)" and e["rel"] == "index.html":
        return "유지", "루트 진입", None
    # reports/ 는 원래 A3 보관함이지만, 그 안에도 "옛 주소 → coo/chairman 실물" 리다이렉트 스텁이
    # 섞여 있다(실측 12건, 599바이트 meta-refresh 뿐 · 2026-09-17 재확인) — 스텁이 아닌 진짜
    # 보관 문서만 보호하고, 스텁은 이동스텁 규칙(아래)을 그대로 탄다.
    if e["folder"] == "reports" and not e.get("redirect_to"):
        return "유지", "A3 보관", None

    name = e["rel"].rsplit("/", 1)[-1]
    if BACKUP_NAME_RE.search(name):
        return "AI삭제", "백업 파일명(.bak_/backup/_copy)", None
    if stale_reason:
        return "AI삭제", stale_reason, None

    hits = e["hits"]
    window = f"{md(hits_since)}~{md(hits_until)}" if hits_since else "접속기록"

    if e["external"]:
        return "유지", "외부 삽입(erp 접속 0 정상)", None

    is_stub = bool(e.get("redirect_to")) or bool(STUB_TITLE_RE.search(e["title"]))
    if is_stub:
        if e["rel"] in KNOWN_ACTIVE_STUB_RELS:
            return "유지", "위생자동화가 여는 파일(weekly_page_hygiene.py) — 보존", None
        if hits == 0:
            return "AI삭제", f"이동스텁·{window} 접속0회", None
        return "유지", f"이동스텁이지만 {window} 접속{hits}회", None

    flags = e["flags"]
    if dup_reason:
        return ("유지", "", None) if hits > 0 else ("GM후보", dup_reason, "A")

    if e["kind"] in ("문서", "화면") and hits == 0 and e["created_days"] > GM_A_MIN_AGE_DAYS:
        if GM_A_NAME_RE.search(name) or GM_A_NAME_RE.search(e["title"]) or "오래됨" in flags or "고립" in flags:
            reasons = [r for r in ("오래됨", "고립") if r in flags]
            if GM_A_NAME_RE.search(name) or GM_A_NAME_RE.search(e["title"]):
                reasons.append("초안류 이름")
            return "GM후보", "·".join(reasons) if reasons else "정리 후보", "A"

    if e["kind"] == "업무" and hits == 0 and e["last_commit"] and days_since(e["last_commit"]) >= GM_B_MIN_AGE_DAYS:
        return "GM후보", "끝난 업무 산출물 — 보관 후보", "B"

    return "유지", "", None


def prune_candidates(entries: list) -> list:
    """--prune 전용 — 이동스텁 & 30일 이상 방치 & 접속0. 주 1회 별도 실행용(오늘은 안 돌린다)."""
    out = []
    for e in entries:
        if not e.get("redirect_to") or is_protected(e) or e["external"]:
            continue
        if e["rel"] in KNOWN_ACTIVE_STUB_RELS:
            continue
        if e["hits"] == 0 and e["last_commit"] and days_since(e["last_commit"]) >= PRUNE_MIN_AGE_DAYS:
            out.append(e)
    return out


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


def load_previous_deleted() -> list:
    if not OUT.exists():
        return []
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get(DELETED_KEY, [])
    except (OSError, json.JSONDecodeError):
        return []


def build(carried_deleted: list) -> dict:
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
    first_commits = load_first_commits()
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
        first_commit = first_commits.get(git_key)
        rm = REFRESH_RE.search(text)
        redirect_to = rm.group(1).strip() if rm else None

        basename = parts[-1]
        inbound_files = referrers.get(basename, set()) - {rel}
        inbound = len(inbound_files)
        in_card = modules.get(rel)
        size_kb = round(p.stat().st_size / 1024, 1)

        flags = []
        if last_commit and days_since(last_commit) > 30:
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
        if is_external_embed(rel):
            flags = [f for f in flags if f != "고립"]  # 밖에서 끼워 쓰는 것 — erp 접속 0 이 정상
            flags.append("외부삽입")

        entry = {
            "no": i,
            "rel": rel,
            "url": url,
            "title": title,
            "folder": folder,
            "last_commit": last_commit,
            "created_days": days_since(first_commit) if first_commit else 0,
            "in_card": in_card,
            "inbound": inbound,
            "size_kb": size_kb,
            "flags": flags,
            "kind": classify_kind(rel, title),
            "external": is_external_embed(rel),
            "essence": extract_essence(text, title),
        }
        if redirect_to:
            entry["redirect_to"] = redirect_to
        entries.append(entry)

    # ── 1차 정리 판정 ──
    refs_by_basename = count_refs({e["rel"].split("/")[-1] for e in entries})
    hits, hits_since, hits_until = load_hits()
    for e in entries:
        e["refs"] = refs_by_basename.get(e["rel"].split("/")[-1], 0)
        hit = hits.get("/" + e["rel"])
        e["hits"] = hit["n"] if hit else 0

    dup_reason_by_no = mark_dup_titles(entries)
    stale_reason_by_no = mark_stale_versions(entries, referrers)
    for e in entries:
        verdict, reason, gm_tier = judge_verdict(
            e, hits_since, hits_until,
            dup_reason_by_no.get(e["no"], ""), stale_reason_by_no.get(e["no"], ""),
        )
        e["verdict"] = verdict
        e["reason"] = reason
        if gm_tier:
            e["gm_tier"] = gm_tier
            e["welly"] = welly_judge(e)

    verdict_counts = defaultdict(int)
    kind_counts = defaultdict(int)
    for e in entries:
        verdict_counts[e["verdict"]] += 1
        kind_counts[e["kind"]] += 1
    ai_delete = [e["no"] for e in entries if e["verdict"] == "AI삭제"]

    return {
        "_doc": "전체 화면(*.html) 링크 목록. scripts/screen_map.py 가 만든다 — 손으로 고치지 마라.",
        "generated": TODAY.isoformat(),
        "total": len(entries),
        "in_card": sum(1 for e in entries if e["in_card"]),
        "orphan": sum(1 for e in entries if "고립" in e["flags"]),
        "stale": sum(1 for e in entries if "오래됨" in e["flags"]),
        "stub": sum(1 for e in entries if "이동스텁" in e["flags"]),
        "hits_since": hits_since,
        "hits_until": hits_until,
        "verdict_counts": {
            "유지": verdict_counts.get("유지", 0),
            "GM후보": verdict_counts.get("GM후보", 0),
            "AI삭제": verdict_counts.get("AI삭제", 0),
        },
        "kind_counts": {
            "문서": kind_counts.get("문서", 0),
            "업무": kind_counts.get("업무", 0),
            "화면": kind_counts.get("화면", 0),
        },
        "ai_delete": ai_delete,
        DELETED_KEY: carried_deleted,
        "screens": entries,
    }


def write_out(out: dict):
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    vc, kc = out["verdict_counts"], out["kind_counts"]
    print(f"screen_map: {out['total']}장 · 카드 {out['in_card']} · 고립 {out['orphan']} · 오래됨 {out['stale']} · 이동스텁 {out['stub']} -> {OUT}")
    print(f"1차 정리 판정: 유지 {vc['유지']} · GM후보 {vc['GM후보']} · AI삭제 {vc['AI삭제']}")
    print(f"종류: 문서 {kc['문서']} · 업무 {kc['업무']} · 화면 {kc['화면']}")
    print(f"지운 누적: {len(out[DELETED_KEY])}장")


def main():
    argv = sys.argv[1:]
    apply_delete = "--apply" in argv
    prune_mode = "--prune" in argv
    carried = load_previous_deleted()
    out = build(carried)

    if prune_mode:
        targets = prune_candidates(out["screens"])
        print(f"--prune 대상 {len(targets)}장(이동스텁·{PRUNE_MIN_AGE_DAYS}일 이상·접속0):")
        for e in targets:
            print(f"  {e['no']} {e['rel']}")
        if apply_delete:
            deleted_now = []
            for e in targets:
                fp = GUIDE / e["rel"]
                try:
                    fp.unlink()
                    print(f"삭제: {e['rel']}")
                    deleted_now.append({"rel": e["rel"], "reason": f"--prune({PRUNE_MIN_AGE_DAYS}일·접속0)"})
                except OSError as ex:
                    print(f"삭제 실패: {e['rel']} — {ex}")
            carried = carried + deleted_now
            out = build(carried)
        write_out(out)
        return

    if apply_delete:
        targets = [e for e in out["screens"] if e["verdict"] == "AI삭제"]
        if not targets:
            print("AI삭제 대상 없음 — 지울 것 없다.")
        else:
            deleted_now = []
            for e in targets:
                fp = GUIDE / e["rel"]
                try:
                    fp.unlink()
                    print(f"삭제: {e['rel']} ({e['reason']})")
                    deleted_now.append({"no": e["no"], "rel": e["rel"], "reason": e["reason"]})
                except OSError as ex:
                    print(f"삭제 실패: {e['rel']} — {ex}")
            carried = carried + deleted_now
            out = build(carried)  # 지운 뒤 재생성 — 숫자 갱신

    write_out(out)


if __name__ == "__main__":
    main()
