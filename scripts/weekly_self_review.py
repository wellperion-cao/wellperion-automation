#!/usr/bin/env python3
"""주간 AI 자기정리·학습 — Before/After 체감 카드 (weekly_self_review.py) — v2

설계: docs/superpowers/specs/2026-07-10-weekly-ai-self-review-before-after-design.md (v2 재설계)
v1 GM 판정: "아직 안 느껴진다" — 탐지 3종이 이 메모리 코퍼스에서 수학적으로 0만 나오는
구조적 버그였음(90일+ AND 고아=영구0, 유사도≥0.55=영구0, 긴 정확문자열 모순=변형언급 놓침).
v2 = 탐지 역산(3단 깔때기+4신호) + 카드 위계 역전("고친 것" 최상단, 무변화는 ✅ 1줄).

3파트: ① 메모리 정리(병합·갱신 자율/삭제만 게이트) ② AI 트렌드→적용 ③ C-Level 컨텍스트(_queue).

원칙(탐지): 규칙=후보 발굴(재현율), 두뇌(claude CLI via model_router)=최종 판정(정밀도·MERGE/UPDATE/HOLD).
원칙(카드): 변화가 주인공 — 고친 것(실명)→배운 것(제안)→행동 필요(정체 배 실명)→무변화는 ✅ 1줄.

일요일 릴레이(10:30 본 스크립트):
  일 09:00  Education-Archive           (기존 유지)
  일 09:30  ai_education_auto_learner --no-send (기존, 발송만 OFF — 수집·요약은 카드 원료)
  일 10:00  ai_learning_proposer --no-send        (기존, 트리거 월→일 이동 + 발송만 OFF)
  일 10:30  weekly_self_review.py (본 스크립트) — 메모리+큐 정리 + 카드 조립·발송

안전(배237 가역=자율 원칙):
  - 메모리 스냅샷(zip, 4주 보관) 없이는 병합·갱신 실행 안 함.
  - 메모리 완전 삭제는 절대 자율 금지 — 두뇌가 DELETE_CANDIDATE 판정한 것만
    status/self_review_delete_queue.json 적재, --approve-delete <file> 로만 실제 삭제(직전 재스냅샷).
  - 병합·갱신도 두뇌가 확신 없으면(HOLD) 아무것도 쓰지 않는다 — 정보손실 0 최우선.
  - 병합 시 MEMORY.md 인덱스 링크 재배선 + 중복라벨 병합 + 본문 [[위키링크]] 도 대상 재지정.
  - 큐 정리(완료 아카이브)는 기존 queue_archive_sweep.py 재사용(신규 아카이브 로직 없음·net-zero).
  - 실제 텔레그램 발송은 게이트 WEEKLY_REVIEW_LIVE_SEND=1 일 때만(기본 OFF·GM go 시 ON).
    OFF여도 스캔·정리·카드조립·로그기록은 전부 정상 실행(콘솔로 매주 검증 가능).

사용법:
  python scripts/weekly_self_review.py                   # 실행(게이트 OFF면 발송만 생략)
  python scripts/weekly_self_review.py --dry-run          # 전부 읽기전용 — 스냅샷·변경·발송 0
  python scripts/weekly_self_review.py --list-delete-queue
  python scripts/weekly_self_review.py --approve-delete <file.md>
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
ENV_FILE = BASE_DIR / "telegram_bot" / ".env"
STATUS_DIR = BASE_DIR / "status"
SCRIPTS_DIR = BASE_DIR / "scripts"

MEMORY_DIR = Path(r"C:\Users\jjky0\.claude\projects\C--Users-jjky0-welperion-automation\memory")
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"

SNAPSHOT_DIR = STATUS_DIR / "_memory_snapshots"
SNAPSHOT_RETAIN_WEEKS = 4

LOG_FILE = STATUS_DIR / "self_review_log.jsonl"
DELETE_QUEUE_FILE = STATUS_DIR / "self_review_delete_queue.json"

PROPOSALS_FILE = STATUS_DIR / "learning_proposals.json"
QUEUE_FILE = STATUS_DIR / "_queue.json"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "aide_detectors") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "aide_detectors"))

# ── 라이브 발송 게이트 (기본 OFF · GM go 시에만 ON — 다른 게이트와 절대 공유 금지) ──
LIVE_SEND_ENV = "WEEKLY_REVIEW_LIVE_SEND"
_ON_VALUES = {"1", "true", "yes", "on"}


def live_send_enabled() -> bool:
    return os.environ.get(LIVE_SEND_ENV, "").strip().lower() in _ON_VALUES


# ── 자율 실행 한도 (한 회차 비용·리스크 상한 — §5 기본값 3/3, 병합만 GM 승인 첫 라이브런 한정 4) ──
MAX_MERGE_CLUSTERS_PER_RUN = 4
MAX_UPDATE_FILES_PER_RUN = 3
BODY_SIM_THRESHOLD = 0.35     # v1: 0.55(카테고리내) → v2: 0.35(frontmatter 제거 전문, 실측 역산)
TOKEN_JACCARD_THRESHOLD = 0.4

# ── 확장 삭제후보 스캔 (GM 지시 2026-07-10 "더 딥하게·낡은건 삭제") — 후보만 발굴, 실삭제는
#    항상 --approve-delete 게이트 뒤(배237). 재현율 우선 규칙 프리필터 → 두뇌가 보수적 최종판정
#    (애매하면 후보 제외 — 과삭제 금지를 프롬프트에 명시). 매주 카드 "🗑 삭제 후보" 섹션 원료.
DELETE_SCAN_STALE_DAYS = 60
S3_STALE_DAYS = 45

CLEVEL_ROLES = ["ceo", "cfo", "chro", "cmo", "coo", "cpo", "cto"]
ROLE_NICK = {"ceo": "웰리", "cfo": "시뽀", "chro": "시로", "cmo": "시모",
             "coo": "시우", "cpo": "시포", "cto": "시토"}

# S1 폐기어휘 — 짧은 토큰+변형 사전(v1의 긴 정확문자열 매칭 폐지, §2-2). 새 폐기건=여기 1줄 추가.
RETIRED_TOKENS = [
    ("Notion", "웰페리온 ERP·G1 단일화(Notion AI조직DB·CEO인박스·GM TODO 폐기, CLAUDE.md §2/§3)"),
    ("인박스", "CEO 인박스 DB(INB) 폐기 — 호출 금지(CLAUDE.md §3)"),
    ("캔바", "슬라이드 엔진 = compose_barre 로 캔바 독립(project_slide_engine_canva_independence)"),
    ("Canva", "슬라이드 엔진 = compose_barre 로 캔바 독립"),
    ("Netlify", "가이드허브 배포 = GitHub Pages(https://wellperion-cao.github.io/wellperion-automation/)"),
    ("김남욱 페이지", "GM 할일 SSOT = G1 '오늘의 항로'(CLAUDE.md §3-1) — 가이드허브 개인페이지 아님"),
    ("ceo_morning_brief_08", "구버전 폐기·미존재 — 정본 wellperion-agents/scripts/ceo_morning_pipeline.py"),
    ("카카오 오픈채팅봇", "R&D 종결(비즈채널은 정상 — project_kakao_bot_rd_closed)"),
]
_AWARE_MARKERS = ["폐기", "종결", "OFF", "폐지", "중단", "대체"]

# S3 완료된 일회성 TODO 신호 — 미래형 문구
_FUTURE_PHRASES = ["수동 배포 필요", "배포 후 입력", "할 예정", "예정이다", "추후 반영",
                    "나중에 처리", "GM님 수동 배포"]

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_CIRCLED = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤", 6: "⑥"}


def _circled(i: int) -> str:
    return _CIRCLED.get(i, f"({i})")


# ═══════════════════════════════════════════
#  유틸
# ═══════════════════════════════════════════
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_env() -> dict:
    out = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _safe_read(f: Path) -> str:
    try:
        return f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _strip_frontmatter(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def _frontmatter_name_slug(text: str) -> str | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    nm = re.search(r"^name:\s*(.+)$", text[:m.end()], re.MULTILINE)
    if not nm:
        return None
    val = nm.group(1).strip().strip('"').strip("'")
    if not val or " " in val or not re.match(r"^[a-z0-9-]+$", val):
        return None
    return val


def _link_forms(f: Path, contents: dict) -> set[str]:
    """이 파일을 가리킬 수 있는 위키링크 표기 전부 — 실측(2026-07-10 라이브런): 코퍼스는
    2관례 혼재 ① 파일명 스템 언더스코어(`[[project_guidehub_ssot]]`, 압도 다수)
    ② frontmatter name 슬러그 하이픈(`[[project-guidehub-ssot]]`, 소수). 병합 후 재지정은
    양쪽 다 잡아야 한다(하이픈만 잡던 v2.0 버그로 실측 5건 dead-link 발생 → 수정)."""
    forms = {f.stem}
    fm = _frontmatter_name_slug(contents.get(f, ""))
    if fm:
        forms.add(fm)
    return forms


# ═══════════════════════════════════════════
#  파트 A-1 — 메모리 스냅샷(가역화)
# ═══════════════════════════════════════════
def _prune_snapshots():
    cutoff = datetime.now() - timedelta(weeks=SNAPSHOT_RETAIN_WEEKS)
    for f in SNAPSHOT_DIR.glob("*.zip"):
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if d < cutoff:
            try:
                f.unlink()
            except Exception:
                pass


def snapshot_memory(dry_run: bool) -> Path | None:
    """정리 전 메모리 폴더 전체를 zip 백업(가역화 장치). dry-run 은 완전 무행동."""
    if dry_run:
        return None
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _prune_snapshots()
    if not MEMORY_DIR.exists():
        return None
    dest = SNAPSHOT_DIR / f"{today_str()}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in MEMORY_DIR.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(MEMORY_DIR))
    return dest


def list_memory_files() -> list[Path]:
    if not MEMORY_DIR.exists():
        return []
    return sorted(p for p in MEMORY_DIR.glob("*.md") if p.name != "MEMORY.md")


# ═══════════════════════════════════════════
#  파트 A-2 — 탐지 v2: 병합 3단 깔때기 + 낡음 4신호(§2)
# ═══════════════════════════════════════════
def _index_line_clusters(index_text: str) -> list[list[str]]:
    """같은 불릿 줄에 링크된 파일들 = 사람이 이미 만든 주제 클러스터(§2-1 ①)."""
    clusters = []
    for line in index_text.splitlines():
        names = re.findall(r"\]\(([\w\-]+\.md)\)", line)
        if len(names) >= 2:
            clusters.append(names)
    return clusters


def _filename_tokens(name: str) -> set:
    stem = name[:-3] if name.endswith(".md") else name
    parts = stem.split("_")
    if parts and parts[0] in ("feedback", "project", "reference"):
        parts = parts[1:]
    return {p for p in parts if p}


def _funnel_duplicate_pairs(files: list[Path], contents: dict, index_text: str) -> dict[tuple, list[str]]:
    """3단 깔때기(§2-1) 후보쌍 → {(a,b) 정렬쌍: [증거태그,...]}."""
    by_name = {f.name: f for f in files}
    pairs: dict[tuple, list[str]] = defaultdict(list)

    # ① 인덱스 줄 클러스터
    for names in _index_line_clusters(index_text):
        present = [by_name[n] for n in names if n in by_name]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                key = tuple(sorted((present[i], present[j]), key=lambda p: p.name))
                pairs[key].append("인덱스줄")

    n = len(files)
    # ② 파일명 토큰 겹침 (Jaccard 0.4+, 2토큰+ 공유)
    tokens = {f: _filename_tokens(f.name) for f in files}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = files[i], files[j]
            ta, tb = tokens[a], tokens[b]
            if not ta or not tb:
                continue
            inter = ta & tb
            if len(inter) < 2:
                continue
            union = ta | tb
            if union and (len(inter) / len(union)) >= TOKEN_JACCARD_THRESHOLD:
                key = tuple(sorted((a, b), key=lambda p: p.name))
                pairs[key].append("파일명토큰")

    # ③ 본문(frontmatter 제거) 유사도 0.35+ — quick_ratio 로 선컷(성능)
    bodies = {f: _strip_frontmatter(contents.get(f, "")) for f in files}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = files[i], files[j]
            ba, bb = bodies[a], bodies[b]
            if not ba or not bb:
                continue
            shorter, longer = sorted((len(ba), len(bb)))
            if longer > 3 * max(shorter, 1):
                continue
            sm = difflib.SequenceMatcher(None, ba, bb)
            if sm.quick_ratio() < BODY_SIM_THRESHOLD:
                continue
            ratio = sm.ratio()
            if ratio >= BODY_SIM_THRESHOLD:
                key = tuple(sorted((a, b), key=lambda p: p.name))
                pairs[key].append(f"본문유사{ratio:.2f}")

    return pairs


def _cluster_pairs(pairs: dict[tuple, list[str]], contents: dict) -> list[tuple[list[Path], str]]:
    """연결성분(union-find)마다 근거가 가장 강한 '쌍'만 병합후보로 채택.

    ★안전(정보손실 0 최우선): 같은 인덱스줄에 3+ 파일이 있어도 전부 같은 주제라는
    보장이 없다(실측: 세션명+RemoteControl+예약제 3파일이 한 줄에 있지만 예약제는
    다른 주제). 3+ 파일을 통째로 두뇌에 병합 판정시키면 손실 위험이 커지므로,
    연결성분 안에서도 항상 '가장 확신 높은 쌍(2파일)'만 후보로 낸다.
    동점(태그 수 동일)이면 frontmatter 제거 본문 실측 유사도로 타이브레이크."""
    parent: dict[Path, Path] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    by_component: dict[Path, list[tuple[tuple[Path, Path], list[str]]]] = defaultdict(list)
    for (a, b), tags in pairs.items():
        by_component[find(a)].append(((a, b), tags))

    def _tiebreak_ratio(a: Path, b: Path) -> float:
        ba, bb = _strip_frontmatter(contents.get(a, "")), _strip_frontmatter(contents.get(b, ""))
        if not ba or not bb:
            return 0.0
        return difflib.SequenceMatcher(None, ba, bb).ratio()

    out = []
    for root, edges in by_component.items():
        edges.sort(key=lambda e: (-len(set(e[1])), -_tiebreak_ratio(*e[0])))
        best_pair, best_tags = edges[0]
        out.append((list(best_pair), "+".join(sorted(set(best_tags)))))
    # 근거 신호 수 많은(=확신 높은) 쌍 우선
    out.sort(key=lambda t: -len(t[1].split("+")))
    return out


def _s1s2_candidates(files: list[Path], contents: dict) -> list[tuple[Path, str, str, str]]:
    """S1 폐기어휘 + S2 국소 자각판정(±100자 내 폐기/종결 없을 때만 후보) — (file, term, note, snippet)."""
    out = []
    for f in files:
        body = _strip_frontmatter(contents.get(f, ""))
        for term, note in RETIRED_TOKENS:
            m = None
            for cand in re.finditer(re.escape(term), body):
                start, end = cand.start(), cand.end()
                window = body[max(0, start - 100):end + 100]
                if any(mk in window for mk in _AWARE_MARKERS):
                    continue  # 이미 자각 — 진짜 모순 아님(v1 버그 수정)
                m = cand
                break
            if m is None:
                continue
            snippet = body[max(0, m.start() - 30):m.end() + 30].replace("\n", " ").strip()
            out.append((f, term, note, snippet))
    return out


def _s3_candidates(files: list[Path], contents: dict) -> list[Path]:
    """S3 완료된 일회성 TODO 후보 — 미래형 문구 + 45일+ 미수정."""
    now = datetime.now()
    out = []
    for f in files:
        try:
            age = (now - datetime.fromtimestamp(f.stat().st_mtime)).days
        except Exception:
            continue
        if age < S3_STALE_DAYS:
            continue
        body = _strip_frontmatter(contents.get(f, ""))
        if any(p in body for p in _FUTURE_PHRASES):
            out.append(f)
    return out


def _extract_index_labels(index_text: str) -> dict[str, str]:
    """MEMORY.md 인덱스에서 파일명→사람이 붙인 라벨(대괄호 텍스트) 추출 — 카드 서술용."""
    out = {}
    for m in re.finditer(r"\[([^\]]+)\]\(([\w\-]+\.md)\)", index_text):
        out.setdefault(m.group(2), m.group(1))
    return out


def scan_memory() -> dict:
    files = list_memory_files()
    contents = {f: _safe_read(f) for f in files}
    index_text = MEMORY_INDEX.read_text(encoding="utf-8") if MEMORY_INDEX.exists() else ""
    total_kb = round(sum(len(contents[f].encode("utf-8")) for f in files) / 1024, 1)

    linked_names = set(re.findall(r"\]\(([\w\-]+\.md)\)", index_text))
    orphans = [f for f in files if f.name not in linked_names]
    dead_links = sorted(n for n in linked_names if not (MEMORY_DIR / n).exists())

    dup_pairs = _funnel_duplicate_pairs(files, contents, index_text)
    dup_clusters = _cluster_pairs(dup_pairs, contents)
    update_hits = _s1s2_candidates(files, contents)
    s3_files = _s3_candidates(files, contents)
    labels = _extract_index_labels(index_text)

    return {
        "files": files, "file_count": len(files), "total_kb": total_kb,
        "orphans": orphans, "dead_links": dead_links,
        "dup_pairs": dup_pairs, "dup_clusters": dup_clusters,
        "update_hits": update_hits, "s3_files": s3_files,
        "index_text": index_text, "contents": contents, "labels": labels,
    }


# ═══════════════════════════════════════════
#  파트 A-3 — 두뇌(LLM) 최종 판정 — 구조화 프로토콜(MERGE/UPDATE/DELETE_CANDIDATE/HOLD)
# ═══════════════════════════════════════════
def _run_claude(prompt: str, label: str) -> str | None:
    try:
        from model_router import run_claude
    except ImportError:
        return None
    text, _model = run_claude(prompt, label=label)
    return text


def _extract_json_array(text: str) -> str | None:
    """텍스트 안 어디든 있는 첫 균형잡힌 [...] 배열을 추출한다(실측: LLM이 순수 JSON만
    달라는 지시를 무시하고 앞뒤에 설명·근거 산문을 붙이는 경우가 흔함 — 배열 시작 [ 을
    찾아 괄호 깊이 카운팅으로 대응하는 ] 까지 잘라낸다). 못 찾으면 None."""
    start = text.find("[")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _parse_verdict(raw: str | None, ok_head: str) -> tuple[str, str]:
    """첫 줄=판정 헤더, 나머지=본문/사유. 형식 이탈·빈응답은 전부 HOLD(안전 보류)."""
    if not raw or not raw.strip():
        return "HOLD", "LLM 응답 없음"
    lines = raw.strip().splitlines()
    head = lines[0].strip().upper()
    rest = "\n".join(lines[1:]).strip()
    if head.startswith(ok_head) and rest:
        return ok_head, rest
    if head.startswith("DELETE_CANDIDATE"):
        return "DELETE_CANDIDATE", rest or "사유 미기재"
    if head.startswith("HOLD"):
        return "HOLD", rest or "사유 미기재"
    return "HOLD", "LLM 응답 형식 이탈 — 안전 보류"


def _llm_merge_judge(cluster: list[Path], contents: dict, evidence: str) -> tuple[str, str]:
    bodies = [f"### {f.name}\n{contents.get(f, '')}" for f in cluster]
    prompt = (
        f"아래는 웰페리온 AI 메모리 파일 {len(cluster)}개다(병합 후보, 탐지근거: {evidence}). "
        "정말 같은 결정·규칙을 서술하는지 신중히 판단하라.\n"
        "병합 가치가 있으면 첫 줄에 정확히 'MERGE'만 쓰고, 다음 줄부터 병합된 파일 전체"
        "(YAML frontmatter 포함, 기존 압축 불릿 스타일 유지, 모든 사실·수치·날짜 보존 — 정보 손실 금지)를 출력.\n"
        "병합하면 안 되면(다른 주제·정보손실 위험·확신 없음) 첫 줄에 정확히 'HOLD'만 쓰고 다음 줄에 사유 1문장.\n"
        "다른 텍스트·설명·코드블록 없이 이 형식만.\n\n" + "\n\n".join(bodies)
    )
    raw = _run_claude(prompt, label="weekly-self-review-merge")
    return _parse_verdict(raw, "MERGE")


def _llm_update_judge(f: Path, text: str, hits: list[tuple[str, str, str]]) -> tuple[str, str]:
    hit_lines = "\n".join(f"- '{t}' 현재사실: {n} (본문 발췌: ...{s}...)" for t, n, s in hits)
    prompt = (
        "아래 웰페리온 AI 메모리 파일이 폐기·변경된 항목을 현행처럼 언급하는 것으로 의심된다:\n"
        f"{hit_lines}\n\n파일 전체를 읽고 정확히 3개 중 하나로만 응답하라:\n"
        "1) 정말 낡았고 확실히 고칠 수 있으면 첫 줄에 'UPDATE', 다음 줄부터 현행화된 파일 전체"
        "(frontmatter 포함, 다른 내용은 그대로 보존)\n"
        "2) 이미 끝난 일회성 내용이고 역사적 기록 가치도 없으면 첫 줄에 'DELETE_CANDIDATE', 다음 줄에 사유\n"
        "3) 확신이 없거나 절반만 낡았으면 첫 줄에 'HOLD', 다음 줄에 사유\n"
        "다른 텍스트·설명·코드블록 없이 이 형식만.\n\n### " + f.name + "\n" + text
    )
    raw = _run_claude(prompt, label="weekly-self-review-update")
    return _parse_verdict(raw, "UPDATE")


def _llm_s3_judge(f: Path, text: str) -> tuple[str, str]:
    prompt = (
        "아래 웰페리온 AI 메모리 파일은 '~할 예정'/'배포 후 입력' 등 미래형 문구를 포함하고 "
        f"{S3_STALE_DAYS}일+ 갱신이 없다. 실제로 이미 끝난 일회성 TODO인지 판단하라 — 정확히 3개 중 하나:\n"
        "1) 이미 끝났고 지금도 유효한 지식이 남아 있으면 첫 줄에 'UPDATE', 다음 줄부터 완료 반영한 파일 전체\n"
        "2) 이미 끝났고 역사적 기록 가치도 없으면 첫 줄에 'DELETE_CANDIDATE', 다음 줄에 사유\n"
        "3) 아직 안 끝났거나 확신 없으면 첫 줄에 'HOLD', 다음 줄에 사유\n"
        "다른 텍스트·설명·코드블록 없이 이 형식만.\n\n### " + f.name + "\n" + text
    )
    raw = _run_claude(prompt, label="weekly-self-review-s3")
    return _parse_verdict(raw, "UPDATE")


def _redirect_wikilinks(all_files: list[Path], keep: Path, dropped: list[Path], contents: dict) -> int:
    """병합 후 본문 [[위키링크]] 참조 재지정(언더스코어·하이픈 두 관례 모두 커버, §4 주의사항).
    새 참조는 코퍼스 다수관례(파일명 스템 언더스코어)로 통일. keep 파일 안에 남은 자기참조
    (합쳐진 파트너를 가리키던 링크)는 순환이 되므로 재지정이 아니라 제거. 재지정+제거 파일 수 반환."""
    old_forms: set[str] = set()
    for d in dropped:
        old_forms |= _link_forms(d, contents)
    new_form = keep.stem
    old_forms.discard(new_form)
    if not old_forms:
        return 0
    alt = "|".join(re.escape(s) for s in old_forms)
    pattern = re.compile(r"\[\[(?:" + alt + r")\]\]")
    self_ref_pattern = re.compile(r"\s*[·,]?\s*\[\[(?:" + alt + r")\]\]")
    n = 0
    for f in all_files:
        if f in dropped or not f.exists():
            continue
        text = _safe_read(f)
        if not pattern.search(text):
            continue
        if f == keep:
            new_text = self_ref_pattern.sub("", text)  # 자기참조 제거(구분자 포함)
        else:
            new_text = pattern.sub(f"[[{new_form}]]", text)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            n += 1
    return n


def _collapse_duplicate_index_links(index_text: str) -> str:
    """병합으로 한 줄에 같은 target 을 가리키는 링크가 2개+ 생기면 라벨을 '+'로 합쳐 1개로 압축."""
    out_lines = []
    for line in index_text.splitlines():
        matches = list(re.finditer(r"\[([^\]]+)\]\(([\w\-]+\.md)\)", line))
        if len(matches) < 2:
            out_lines.append(line)
            continue
        by_target: dict[str, list] = defaultdict(list)
        for m in matches:
            by_target[m.group(2)].append(m)
        if not any(len(v) > 1 for v in by_target.values()):
            out_lines.append(line)
            continue
        result = line
        # 뒤에서부터 중복분 제거(첫 등장만 남김) + 라벨 합치기
        for target, ms in by_target.items():
            if len(ms) < 2:
                continue
            joined = "+".join(m.group(1) for m in ms)
            for m in reversed(ms[1:]):
                s = m.start()
                if s > 0 and result[s - 1] == "·":
                    s -= 1
                result = result[:s] + result[m.end():]
            old_bracket = f"[{ms[0].group(1)}]({target})"
            new_bracket = f"[{joined}]({target})"
            result = result.replace(old_bracket, new_bracket, 1)
        out_lines.append(result)
    return "\n".join(out_lines)


def _frontmatter_description(text: str) -> str | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    dm = re.search(r"^description:\s*(.+)$", text[:m.end()], re.MULTILINE)
    if not dm:
        return None
    return dm.group(1).strip().strip('"').strip("'")


def _delete_scan_prefilter(files: list[Path], contents: dict, exclude: set[Path]) -> list[Path]:
    """확장 삭제후보 재현율 프리필터 — 폐기어휘 언급 또는 60일+ 미수정. 이번 회차에 이미
    병합·갱신·기존판정된 파일은 제외(중복 판정 방지)."""
    now = datetime.now()
    out = []
    for f in files:
        if f in exclude or not f.exists():
            continue
        body = _strip_frontmatter(contents.get(f, ""))
        has_retired = any(term in body for term, _ in RETIRED_TOKENS)
        try:
            age = (now - datetime.fromtimestamp(f.stat().st_mtime)).days
        except Exception:
            age = 0
        if has_retired or age >= DELETE_SCAN_STALE_DAYS:
            out.append(f)
    return out


def _llm_delete_scan_judge(candidates: list[Path], contents: dict, orphan_names: set[str]) -> list[dict]:
    """배치 1콜 — 후보들을 요약해 두뇌에 '진짜 지금 안 쓰는 낡음/폐기'만 보수적으로 골라달라
    요청(GM 지시 2026-07-10). 애매·부분적·"언젠가 쓸 지식"은 프롬프트로 명시 배제.
    반환: [{file, topic, reason, last_relevance}] — 실삭제 아님, 후보 제안만."""
    if not candidates:
        return []
    digests = []
    for f in candidates:
        body = _strip_frontmatter(contents.get(f, ""))
        desc = _frontmatter_description(contents.get(f, "")) or ""
        orphan_tag = " [인덱스 미참조]" if f.name in orphan_names else ""
        try:
            age = (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).days
        except Exception:
            age = 0
        digests.append(
            f"### {f.name} (마지막수정 {age}일 전){orphan_tag}\n설명: {desc}\n본문 발췌: {body[:400]}"
        )
    prompt = (
        "아래는 웰페리온 AI 세션 학습 메모리 파일 후보 목록이다(운영 시스템 문서 아님 — Claude Code 가 "
        "매 세션 참고하는 결정·피드백 카드). 각 파일이 '지금은 이용 안 하는 낡거나 폐기된 것'인지 매우 "
        "보수적으로 판단하라. 후보로 골라도 되는 경우만:\n"
        "- 파일 전체 주제가 이미 죽은 시스템·도구·프로세스(예: 폐기된 채널, 중단된 기능)만 다룸\n"
        "- 현행과 완전 무관하게 새 규칙으로 전부 대체된 구버전 지식\n"
        "- 다른 파일과 사실상 완전 중복(내용이 실질적으로 같음)\n"
        "절대 후보로 고르면 안 되는 경우(과삭제 금지):\n"
        "- 일부 문장만 낡았고 나머지는 아직 유효 (그건 갱신 대상이지 삭제 대상 아님)\n"
        "- '언젠가 다시 필요할 수도 있는' 배경지식·교훈·인시던트 기록\n"
        "- 판단이 조금이라도 애매한 것 — 애매하면 반드시 제외\n\n"
        "정확히 JSON 배열만 응답(설명·코드블록 없이). 후보가 없으면 빈 배열 []:\n"
        '[{"file":"파일명.md","topic":"한줄 주제","reason":"삭제 후보 사유(폐기근거) 한줄",'
        '"last_relevance":"마지막으로 유효했던 시점·맥락 한줄"}]\n\n' + "\n\n".join(digests)
    )
    raw = _run_claude(prompt, label="weekly-self-review-delete-scan")
    if not raw or not raw.strip():
        return []
    try:
        arr = _extract_json_array(raw.strip())
        if arr is None:
            return []
        data = json.loads(arr)
        if not isinstance(data, list):
            return []
    except Exception:
        return []
    valid_names = {f.name for f in candidates}
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("file", "")).strip()
        if name not in valid_names:
            continue
        out.append({
            "file": name,
            "topic": str(item.get("topic", ""))[:60],
            "reason": str(item.get("reason", ""))[:120],
            "last_relevance": str(item.get("last_relevance", ""))[:80],
        })
    return out


def apply_memory_maintenance(scan: dict, dry_run: bool) -> dict:
    """병합·갱신·인덱스 정리(가역=자율, 두뇌 최종판정). 완전 삭제는 이 함수에서 절대 하지 않음."""
    result = {"merged": [], "updated": [], "delete_candidates": [], "held": [], "index_fixed": 0,
              "wikilinks_redirected": 0}
    if dry_run:
        return result

    contents = dict(scan["contents"])
    index_text = scan["index_text"]
    all_files = list(scan["files"])
    touched_paths: set[Path] = set()  # 이번 회차에 이미 판정된 파일 — ④ 확장삭제스캔 중복판정 방지

    # ① 갱신/삭제제안 먼저 — S1/S2 파일단위 그룹핑, 상한 MAX_UPDATE_FILES_PER_RUN(오래된 파일 우선).
    #    ★순서 중요: 병합보다 먼저 실행해 낡은 값을 in-place 로 현행화한 뒤, 병합 단계가
    #    "이미 현행화된 내용"을 합치게 한다(역순이면 병합살아남은 파일에 낡은 값이 그대로
    #    새어들어갈 위험 — 정보손실 0 요구 위반). contents[f] 를 즉시 갱신해 병합 단계가 읽는다.
    grouped: dict[Path, list] = defaultdict(list)
    for f, term, note, snippet in scan["update_hits"]:
        if f in grouped or f.exists():
            grouped[f].append((term, note, snippet))
    ordered = sorted(grouped.keys(), key=lambda f: f.stat().st_mtime if f.exists() else 0)
    count = 0
    handled: set[Path] = set()
    for f in ordered:
        if count >= MAX_UPDATE_FILES_PER_RUN or not f.exists():
            continue
        hits = grouped[f]
        text = contents.get(f) or _safe_read(f)
        action, payload = _llm_update_judge(f, text, hits)
        count += 1
        handled.add(f)
        touched_paths.add(f)
        if action == "UPDATE":
            f.write_text(payload.strip() + "\n", encoding="utf-8")
            contents[f] = payload.strip() + "\n"
            result["updated"].append({"file": f.name, "terms": [h[0] for h in hits]})
        elif action == "DELETE_CANDIDATE":
            result["delete_candidates"].append({
                "file": f.name, "topic": hits[0][0] if hits else "", "reason": payload, "last_relevance": ""
            })
        else:
            result["held"].append({"file": f.name, "reason": f"갱신보류: {payload}"})

    # S3 완료된 일회성 TODO — 남은 예산만큼, S1/S2 로 이미 처리된 파일은 중복 판정 안 함
    remaining = max(0, MAX_UPDATE_FILES_PER_RUN - count)
    for f in scan["s3_files"][:remaining]:
        if f in handled or not f.exists():
            continue
        text = contents.get(f) or _safe_read(f)
        action, payload = _llm_s3_judge(f, text)
        touched_paths.add(f)
        if action == "UPDATE":
            f.write_text(payload.strip() + "\n", encoding="utf-8")
            contents[f] = payload.strip() + "\n"
            result["updated"].append({"file": f.name, "terms": ["완료TODO"]})
        elif action == "DELETE_CANDIDATE":
            result["delete_candidates"].append({
                "file": f.name, "topic": "완료TODO", "reason": payload, "last_relevance": ""
            })
        else:
            result["held"].append({"file": f.name, "reason": f"S3보류: {payload}"})

    # ② 병합 — 클러스터당 LLM 1회, 상한 MAX_MERGE_CLUSTERS_PER_RUN(근거 신호 많은 순).
    #    contents 는 위 갱신단계에서 이미 최신화된 본문을 담고 있으므로, 병합 대상에
    #    방금 현행화한 파일이 섞여 있어도 낡은 값이 아니라 고쳐진 값이 병합된다.
    for cluster, evidence in scan["dup_clusters"][:MAX_MERGE_CLUSTERS_PER_RUN]:
        cluster = [f for f in cluster if f.exists()]
        if len(cluster) < 2:
            continue  # 갱신 단계에서 DELETE_CANDIDATE 로 처리됐거나 이미 사라진 경우
        action, payload = _llm_merge_judge(cluster, contents, evidence)
        if action != "MERGE":
            result["held"].append({"file": cluster[0].name, "reason": f"병합보류: {payload}"})
            touched_paths.update(cluster)
            continue
        keep, drop = cluster[0], cluster[1:]
        keep.write_text(payload.strip() + "\n", encoding="utf-8")
        contents[keep] = payload.strip() + "\n"
        touched_paths.add(keep)
        touched_paths.update(drop)
        for d in drop:
            try:
                d.unlink()
            except Exception:
                continue
            index_text = index_text.replace(f"]({d.name})", f"]({keep.name})")
            all_files = [x for x in all_files if x != d]
        result["wikilinks_redirected"] += _redirect_wikilinks(all_files, keep, drop, contents)
        result["merged"].append({
            "kept": keep.name, "dropped": [d.name for d in drop],
            "labels": [p.name for p in cluster], "evidence": evidence,
        })

    index_text = _collapse_duplicate_index_links(index_text)

    # ④ 확장 삭제후보 스캔(GM 지시 2026-07-10) — 병합·현행화 넘어 전체 낡음/폐기주제/고아 스윕.
    #    이번 회차에 이미 판정된 파일은 제외(touched_paths). 실삭제 없음 — 후보만 delete_candidates 에 적재.
    del_scan_pool = [f for f in all_files if f.exists()]
    del_candidates_files = _delete_scan_prefilter(del_scan_pool, contents, touched_paths)
    orphan_names = {f.name for f in scan["orphans"]}
    for item in _llm_delete_scan_judge(del_candidates_files, contents, orphan_names):
        result["delete_candidates"].append(item)

    # ③ 인덱스 정리 — 죽은 링크(참조는 있으나 파일 없음) 라인 제거
    fixed = 0
    if scan["dead_links"]:
        new_lines = []
        for line in index_text.splitlines():
            refs = re.findall(r"\]\(([\w\-]+\.md)\)", line)
            if refs and any(n in scan["dead_links"] and not (MEMORY_DIR / n).exists() for n in refs):
                fixed += 1
                continue
            new_lines.append(line)
        index_text = "\n".join(new_lines)
    result["index_fixed"] = fixed

    if index_text and not index_text.endswith("\n"):
        index_text += "\n"
    if result["merged"] or fixed or index_text != scan["index_text"]:
        MEMORY_INDEX.write_text(index_text, encoding="utf-8")

    return result


# ── 삭제 큐(비가역 — 두뇌가 판정한 것만, GM 승인 후 실제 삭제) ──
def load_delete_queue() -> list:
    if not DELETE_QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(DELETE_QUEUE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_delete_queue(items: list):
    DELETE_QUEUE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def append_delete_candidates(candidates: list[dict], dry_run: bool) -> tuple[int, list[dict]]:
    """반환: (누적 총건수, 이번 회차 신규분)."""
    existing = load_delete_queue()
    names = {c["file"] for c in existing}
    fresh = [c for c in candidates if c["file"] not in names]
    if dry_run:
        return len(names) + len(fresh), fresh
    for c in fresh:
        existing.append({
            "file": c["file"], "topic": c.get("topic", ""), "reason": c["reason"],
            "last_relevance": c.get("last_relevance", ""), "flagged_at": today_str(),
        })
        names.add(c["file"])
    if fresh:
        save_delete_queue(existing)
    return len(existing), fresh


def cmd_approve_delete(filename: str):
    q = load_delete_queue()
    target = next((c for c in q if c["file"] == filename), None)
    if not target:
        print(f"[ERROR] 삭제 대기 목록에 없음: {filename}")
        sys.exit(1)
    snap = snapshot_memory(dry_run=False)  # 삭제 직전 재스냅샷(가역 보장)
    print(f"[스냅샷] {snap}")
    path = MEMORY_DIR / filename
    if path.exists():
        path.unlink()
        print(f"[삭제 완료] {filename} — 되돌리려면 위 스냅샷 zip 에서 복원")
    else:
        print(f"[정보] 파일이 이미 없음: {filename}")
    q = [c for c in q if c["file"] != filename]
    save_delete_queue(q)


def cmd_list_delete_queue():
    q = load_delete_queue()
    if not q:
        print("[정보] 삭제 대기 없음")
        return
    print(f"삭제 후보 {len(q)}건:")
    for c in q:
        topic = c.get("topic", "")
        rel = c.get("last_relevance", "")
        print(f"  - {c['file']}  [{topic}] {c['reason']}"
              + (f" (마지막 관련성: {rel})" if rel else "")
              + f"  (지정: {c['flagged_at']})")
    print("승인: python scripts/weekly_self_review.py --approve-delete <file>")


# ═══════════════════════════════════════════
#  파트 B — AI 트렌드 학습 → 우리 적용 (기존 proposer/learner 결과 재사용)
# ═══════════════════════════════════════════
def load_proposals() -> list:
    if not PROPOSALS_FILE.exists():
        return []
    try:
        data = json.loads(PROPOSALS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def learning_loop_snapshot() -> dict:
    cards = load_proposals()
    applied = sum(1 for c in cards if c.get("status") == "반영")
    pending = sum(1 for c in cards if c.get("status") == "제안")
    eff_ok = sum(1 for c in cards if c.get("status") == "반영" and c.get("효과") == "효과있음")
    return {"applied": applied, "pending": pending, "eff_ok": eff_ok}


def this_week_trend_proposals() -> list:
    """오늘 생성된 신규 제안(status=제안) — 카드 'AI 트렌드 적용' 원료."""
    today = today_str()
    return [c for c in load_proposals() if c.get("생성일") == today and c.get("status") == "제안"]


# ═══════════════════════════════════════════
#  파트 C — C-Level 컨텍스트(_queue.json) 정리
# ═══════════════════════════════════════════
def load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _is_drift(item: dict, pending_clevels: set) -> bool:
    """🌀표류 판정(보수적, hangro_board.py 와 동일 기준): 완료(DONE)인데
    terminal=false·next 비었고·같은 clevel 의 후속 PENDING 도 없음."""
    if item.get("status") != "DONE":
        return False
    if item.get("terminal", False):
        return False
    if str(item.get("next") or "").strip():
        return False
    return (item.get("clevel") or "").lower() not in pending_clevels


def _archive_candidates(ships: list) -> list:
    today = today_str()
    out = []
    for it in ships:
        if str(it.get("status") or "") not in ("DONE", "완료", "폐기"):
            continue
        if str(it.get("processed_at") or "")[:10] == today:
            continue
        out.append(it)
    return out


def clevel_snapshot(queue: list) -> dict:
    try:
        import stall_watch  # aide_detectors — 정체 판정 정본 재사용(net-zero)
    except Exception:
        stall_watch = None

    pending_clevels = {(it.get("clevel") or "").lower() for it in queue if it.get("status") == "PENDING"}
    out = {}
    for role in CLEVEL_ROLES:
        ships = [it for it in queue if (it.get("clevel") or "").lower() == role]
        out[role] = {
            "active": sum(1 for it in ships if it.get("status") in ("PENDING", "IN_PROGRESS")),
            "stalled": len(stall_watch.detect_stalled(ships)) if stall_watch else 0,
            "drift": sum(1 for it in ships if _is_drift(it, pending_clevels)),
            "archive_candidates": len(_archive_candidates(ships)),
        }
    return out


def _stalled_ship_details(queue: list) -> list[dict]:
    """정체 배 실명(§3 렌더규칙4) — 가장 정체 많은 clevel 하나만 골라 상세 반환."""
    try:
        import stall_watch
    except Exception:
        return []
    by_task_id = {it.get("task_id"): it for it in queue if it.get("task_id")}
    per_role: dict[str, list] = defaultdict(list)
    for gap in stall_watch.detect_stalled(queue):
        role = gap.get("clevel", "")
        ship = by_task_id.get(gap.get("task_id"))
        if not ship:
            continue
        pr = str(ship.get("priority") or "")
        icon = "🛳️" if "🛳️" in pr else ("⛴️" if "⛴️" in pr else "⛵")
        per_role[role].append({
            "ship_no": ship.get("ship_no"), "title": str(ship.get("title", ""))[:26],
            "icon": icon, "nick": ROLE_NICK.get(role, role), "role": role,
        })
    if not per_role:
        return []
    top_role = max(per_role, key=lambda r: len(per_role[r]))
    return per_role[top_role]


def run_queue_archive_sweep(dry_run: bool) -> None:
    """완료 아카이브 정리 — 기존 queue_archive_sweep.py 재사용(신규 로직 없음)."""
    if dry_run:
        return
    try:
        py = sys.executable or "python"
        subprocess.run([py, str(SCRIPTS_DIR / "queue_archive_sweep.py")],
                        cwd=str(BASE_DIR), timeout=60)
    except Exception as e:
        print(f"[WARN] queue_archive_sweep 실행 실패: {type(e).__name__}: {e}")


# ═══════════════════════════════════════════
#  로그
# ═══════════════════════════════════════════
def append_log(record: dict):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_last_log() -> dict | None:
    if not LOG_FILE.exists():
        return None
    lines = [l for l in LOG_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return None


# ═══════════════════════════════════════════
#  카드 조립 v2 — "변화가 주인공, 무변화는 각주"(§3). 실명 서술 우선, N→N 나열 폐지.
# ═══════════════════════════════════════════
def _pretty_label(name: str, labels: dict[str, str]) -> str:
    lab = labels.get(name)
    if lab:
        return lab.split("·")[0].strip("[] ") if "·" in lab else lab
    return name[:-3].replace("_", " ") if name.endswith(".md") else name


def build_card(mem_before: dict, mem_after: dict, maint: dict,
                delete_total: int, new_delete_candidates: list,
                loop_before: dict, loop_after: dict, trend_proposals: list,
                clevel_before: dict, clevel_after: dict, archived_this_run: int,
                stalled_detail: list, snapshot_path) -> str:
    now = datetime.now()
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    date_label = f"{now.month}/{now.day} {weekday_kr}"
    labels = mem_before.get("labels", {})

    mem_file_delta = mem_after["file_count"] - mem_before["file_count"]
    n_merged = len(maint["merged"])
    n_updated = len(maint["updated"])
    stalled_total = sum(v["stalled"] for v in clevel_after.values())

    no_change = (
        mem_file_delta == 0 and n_merged == 0 and n_updated == 0 and maint["index_fixed"] == 0
        and not new_delete_candidates and not trend_proposals
        and archived_this_run == 0 and not stalled_detail
    )
    if no_change:
        return (
            f"🧠 주간 AI 자기정리 — 이번 주 변화 없음 ({date_label})\n"
            f"메모리 {mem_after['file_count']}개 건강 · 큐 정체 0건 · 대기 {delete_total}건\n"
            f"기록: status/self_review_log.jsonl"
        )

    # ⏱ 30초 요약 — 결과 중심
    bits = []
    if mem_file_delta != 0 or n_merged or n_updated:
        bits.append(f"메모리 {mem_before['file_count']}→{mem_after['file_count']} "
                     f"(병합 {n_merged}·현행화 {n_updated})")
    if n_updated:
        bits.append(f"오래된 SSOT 오류 {n_updated}건 발견·수리")
    if trend_proposals:
        bits.append(f"적용 제안 {len(trend_proposals)}건 대기")
    if stalled_detail:
        bits.append(f"{stalled_detail[0]['nick']} 정체 {len(stalled_detail)}척 처분 제안")
    if archived_this_run:
        bits.append(f"완료 {archived_this_run}건 아카이브")
    summary_line = (" · ".join(bits) + ".") if bits else "메모리·큐 소폭 정합만 진행."

    lines = [
        f"🧠 주간 AI 자기정리 — 이번 주 이렇게 똑똑해졌습니다 ({date_label})",
        "",
        f"⏱ 30초 요약: {summary_line}",
        "",
    ]

    # 🔧 이번 주 고친 것 — 실명 서술. 병합·갱신 각 카테고리가 서로를 밀어내지 않도록
    # (실측: 병합3+갱신1묶음이 같이 나온 주에 cap 하나만 두면 갱신이 통째로 잘림) 카테고리별
    # 표시 여유를 두고, 전체는 30초 스캔이 깨지지 않는 선(최대 5줄)에서만 자른다.
    merge_bullets = []
    for m in maint["merged"]:
        labs = "+".join(_pretty_label(n, labels) for n in m["labels"])
        merge_bullets.append(f'"{labs}" {len(m["labels"])}개 → 1개 병합 ({m["kept"]})')
    update_bullets = []
    if maint["updated"]:
        by_term: dict[str, list[str]] = defaultdict(list)
        for u in maint["updated"]:
            key = u["terms"][0] if u["terms"] else "현행화"
            by_term[key].append(u["file"])
        for term, flist in by_term.items():
            names = ", ".join(_pretty_label(n, labels) for n in flist)
            update_bullets.append(f"'{term}' 낡은 언급 {len(flist)}파일 현행화 → {names}")
    fix_bullets = (merge_bullets[:3] + update_bullets[:3])[:5]
    if fix_bullets:
        lines.append("🔧 이번 주 고친 것")
        for i, b in enumerate(fix_bullets, 1):
            lines.append(f"{_circled(i)} {b}")
        lines.append("")

    # 📡 이번 주 배운 것 → 적용 제안
    if trend_proposals:
        lines.append(f"📡 이번 주 배운 것 → 적용 제안 (승인 대기 {loop_after.get('pending', 0)})")
        for i, p in enumerate(trend_proposals[:2], 1):
            what = str(p.get("무엇을", ""))[:56]
            now_txt = str(p.get("현재는", "") or "(미기재)")[:70]
            after_txt = str(p.get("바뀌면", "") or "(미기재)")[:70]
            lines.append(f"{_circled(i)} [{p.get('대상_clevel', '?')}] {what}")
            lines.append(f"   현재는: {now_txt}")
            lines.append(f"   바뀌면: {after_txt}")
            lines.append(f"   → 승인: \"python scripts/ai_learning_proposer.py --approve {p.get('id', '')}\"")
        lines.append("")

    # 🧭 행동 필요 — 정체 배 실명 + 처분 제안
    if stalled_detail:
        nick = stalled_detail[0]["nick"]
        lines.append(f"🧭 행동 필요 — {nick} 정체 {len(stalled_detail)}척 (임계 초과 무업데이트)")
        ship_line = " · ".join(f"배{s['ship_no']} {s['title']}{s['icon']}" for s in stalled_detail)
        lines.append(f"· {ship_line}")
        routine = [s for s in stalled_detail if s["icon"] != "🛳️"]
        project = [s for s in stalled_detail if s["icon"] == "🛳️"]
        sugg = []
        if routine:
            sugg.append(f"{'·'.join(str(s['ship_no']) for s in routine)}은 상시업무 → module_registry 전환")
        if project:
            sugg.append(f"{'·'.join(str(s['ship_no']) for s in project)}은 이번 주 항로 재점화")
        if sugg:
            lines.append(f"→ 제안: {', '.join(sugg)}")
        lines.append("")

    # 🗑 삭제 후보(비가역 — 게이트, GM 지시 2026-07-10) — 신규분만 강조 노출, 실삭제 없음(제안뿐)
    if new_delete_candidates:
        lines.append(f"🗑 삭제 후보 {len(new_delete_candidates)}건 (비가역 → 승인 필요, 실삭제 없음)")
        for c in new_delete_candidates[:5]:
            topic = c.get("topic", "")
            rel = c.get("last_relevance", "")
            tail = f" (마지막 관련성: {rel})" if rel else ""
            lines.append(f"· {_pretty_label(c['file'], labels)} [{topic}] — {c['reason'][:70]}{tail}")
        lines.append('→ 승인: "python scripts/weekly_self_review.py --approve-delete <file>"')
        lines.append("")

    # ✅ 이상 없음 — 무변화 지표 전부 묶음(§3 렌더규칙5)
    ok_bits = [f"인덱스 정합(고아{len(mem_after['orphans'])}·죽은링크{len(mem_after['dead_links'])})",
               f"삭제 대기 {delete_total}건"]
    if not stalled_detail:
        ok_bits.append(f"큐 정체 {stalled_total}건")
    lines.append(f"✅ 이상 없음: {' · '.join(ok_bits)}")
    lines.append(f"기록: status/self_review_log.jsonl · 스냅샷: {snapshot_path or '(dry-run, 없음)'} (되돌리기 가능)")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  텔레그램 발송 (게이트 뒤)
# ═══════════════════════════════════════════
def send_telegram(message: str) -> bool:
    if not live_send_enabled():
        print(f"\n[게이트 OFF] 실제 텔레그램 발송 생략 — {LIVE_SEND_ENV}=1 로 GM 승인 후 활성화")
        return False
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[WARN] 텔레그램 설정 없음 — 발송 생략")
        return False
    if len(message) > 4000:
        message = message[:3990] + "\n...(잘림)"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = json.loads(resp.read().decode()).get("ok", False)
            try:
                from tg_outbound_log import log_outbound
                log_outbound(message, chat_id=chat_id, source="weekly_self_review.send_telegram",
                              ok=ok, kind="sendMessage")
            except Exception:
                pass
            print(f"[텔레그램 {'발송 성공' if ok else '발송 실패'}]")
            return ok
    except Exception as e:
        print(f"[ERROR] 텔레그램 발송 실패: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════
#  메인 파이프라인
# ═══════════════════════════════════════════
def run(dry_run: bool):
    print(f"[시작] 주간 AI 자기정리 v2 ({now_str()})  dry-run={dry_run}\n")

    # ── 파트 A: 메모리 ──
    print("[1/4] 메모리 스캔(정리 전, 탐지 v2)...")
    mem_before = scan_memory()
    print(f"  파일 {mem_before['file_count']}개 · {mem_before['total_kb']}KB · "
          f"병합후보 {len(mem_before['dup_clusters'])}클러스터 · "
          f"낡음후보(S1/S2) {len(mem_before['update_hits'])}건 · S3(완료TODO) {len(mem_before['s3_files'])}건 · "
          f"인덱스불일치(고아 {len(mem_before['orphans'])}/죽은링크 {len(mem_before['dead_links'])})")

    print("[2/4] 스냅샷(가역화) + 자율 정리(두뇌 판정: 병합·갱신·인덱스)...")
    snap_path = snapshot_memory(dry_run)
    print(f"  스냅샷: {snap_path or '(dry-run, 생략)'}")
    maint = apply_memory_maintenance(mem_before, dry_run)
    delete_total, new_delete = append_delete_candidates(maint["delete_candidates"], dry_run)
    print(f"  병합 {len(maint['merged'])}건 · 갱신 {len(maint['updated'])}건 · "
          f"인덱스정리 {maint['index_fixed']}건 · 보류 {len(maint['held'])}건 · "
          f"삭제제안(신규) {len(new_delete)}건 · 삭제대기 누적 {delete_total}건")
    for h in maint["held"]:
        print(f"    [보류] {h['file']}: {h['reason']}")

    changed = maint["merged"] or maint["updated"] or maint["index_fixed"]
    mem_after = scan_memory() if (changed and not dry_run) else mem_before

    # ── 파트 B: AI 트렌드 ──
    print("[3/4] 자기학습 루프 스냅샷...")
    loop_after = learning_loop_snapshot()
    last_log = load_last_log()
    loop_before = last_log.get("loop_after", loop_after) if last_log else loop_after
    trend_proposals = this_week_trend_proposals()
    print(f"  반영 {loop_before.get('applied',0)}→{loop_after.get('applied',0)} · "
          f"이번주 신규제안 {len(trend_proposals)}건")

    # ── 파트 C: C레벨 컨텍스트 ──
    print("[4/4] C레벨 큐 정리(정체 실명/완료아카이브)...")
    queue_before = load_queue()
    clevel_before = clevel_snapshot(queue_before)
    stalled_detail = _stalled_ship_details(queue_before)
    run_queue_archive_sweep(dry_run)
    queue_after = load_queue() if not dry_run else queue_before
    clevel_after = clevel_snapshot(queue_after)
    archived_this_run = max(0, len(queue_before) - len(queue_after)) if not dry_run else 0
    print(f"  활성 {sum(v['active'] for v in clevel_before.values())}척 · "
          f"정체 {sum(v['stalled'] for v in clevel_before.values())}건 · "
          f"완료아카이브 {archived_this_run}건 이동")

    card = build_card(mem_before, mem_after, maint, delete_total, new_delete,
                       loop_before, loop_after, trend_proposals,
                       clevel_before, clevel_after, archived_this_run,
                       stalled_detail, snap_path)

    # ★배10011(2026-07-24, GM 승인) — 일요일 아침 자동화현황방/GM_DM 산발 발신 4건을
    # 이 카드(가장 늦게 도는 10:30 슬롯) 뒤에 이어붙여 1통으로 합친다. 흡수 대상:
    # weekly_page_hygiene·education_archive_weekly·ai_education_auto_learner(--no-send).
    # 소스 없으면(적재 0건) 기존과 완전히 동일한 카드만 나간다(무변화).
    absorbed_blocks: list[str] = []
    if not dry_run:
        try:
            import weekly_bundle_pending as _bundle
            absorbed = _bundle.consume("sunday_weekly_bundle")
            absorbed_blocks = [it["text"] for it in absorbed if it.get("text")]
        except Exception as e:
            print(f"[WARN] sunday_weekly_bundle 소비 실패(무시 — 이 카드는 정상 발송): {e}")

    full_card = card
    if absorbed_blocks:
        full_card = card + "\n\n" + "\n\n".join(absorbed_blocks)

    print("\n" + "=" * 60)
    print(full_card)
    print("=" * 60)

    if dry_run:
        print("\n[dry-run] 로그 기록·텔레그램 발송 생략")
        return

    append_log({
        "date": today_str(), "ts": now_str(),
        "mem_before_count": mem_before["file_count"], "mem_after_count": mem_after["file_count"],
        "merged": maint["merged"], "updated": maint["updated"], "held": maint["held"],
        "index_fixed": maint["index_fixed"], "wikilinks_redirected": maint["wikilinks_redirected"],
        "delete_pending": delete_total, "new_delete_candidates": new_delete,
        "loop_after": loop_after,
        "archived_this_run": archived_this_run,
        "clevel_after": clevel_after,
        "snapshot": str(snap_path) if snap_path else None,
    })

    send_telegram(full_card)
    print(f"\n[완료] ({now_str()})")


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="주간 AI 자기정리 v2 — 메모리+AI트렌드+C레벨컨텍스트 Before/After 카드 (일 10:30)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="전부 읽기전용 — 스냅샷·변경·발송 0")
    parser.add_argument("--approve-delete", type=str, metavar="FILE", dest="approve_delete",
                         help="삭제 대기 메모리 파일 실제 삭제(직전 재스냅샷)")
    parser.add_argument("--list-delete-queue", action="store_true", dest="list_delete_queue",
                         help="삭제 대기 목록 조회")
    args = parser.parse_args()

    if args.list_delete_queue:
        cmd_list_delete_queue()
        return
    if args.approve_delete:
        cmd_approve_delete(args.approve_delete)
        return

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
