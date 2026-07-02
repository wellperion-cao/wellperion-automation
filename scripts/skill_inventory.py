#!/usr/bin/env python3
"""스킬·플러그인 인벤토리 수집기 (skill_inventory.py)

시토 자기학습 파이프라인의 신규 입력 ①.
디스크의 플러그인 캐시에서 설치된 스킬(OMC + superpowers 등)을 열거하고,
docs/skill_cheatsheet.md 와 대조해 '이미 정리됨' vs '새것/미활용' 을 표시한다.

★ 안전 원칙 (설계 불변):
  - 파일시스템 read 만. 라이브 부작용 0. ~/.claude/plugins/** 는 읽기만.
  - 메모리·프롬프트·CLAUDE.md·에이전트 정의 수정 절대 없음.
  - 행동 자동변경·훅·자동호출 0 (깊이 = 발굴 + 표시).

정본 소스:
  ~/.claude/plugins/installed_plugins.json 로 '활성 설치 버전' 경로를 얻고
  그 경로의 skills/*/SKILL.md 만 열거 (버전 중복 방지).
  installed_plugins.json 없으면 cache/**/skills/*/SKILL.md 글롭 폴백(이름 dedup).

사용법:
  python scripts/skill_inventory.py            # 콘솔 요약 (설치 스킬·미활용 표시)
  python scripts/skill_inventory.py --json     # 인벤토리 JSON 출력 (파이프용)
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path

# 단독 실행 시에만 stdout 를 UTF-8 로 래핑한다.
# (import 시 래핑하면 호출부의 stdout 버퍼를 가로채/닫아 I/O 오류를 낼 수 있음)
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 경로 상수 ──
BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
PLUGINS_DIR = Path.home() / ".claude" / "plugins"
INSTALLED_PLUGINS = PLUGINS_DIR / "installed_plugins.json"
CACHE_DIR = PLUGINS_DIR / "cache"
CHEATSHEET = BASE_DIR / "docs" / "skill_cheatsheet.md"


# ═══════════════════════════════════════════
#  SKILL.md 파싱
# ═══════════════════════════════════════════
def _parse_frontmatter(text: str) -> dict:
    """YAML frontmatter(--- ... ---)에서 name·description 등 단순 key: value 추출."""
    out = {}
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _extract_name_desc(skill_dir: Path, text: str) -> tuple[str, str]:
    """frontmatter 우선, 없으면 첫 헤더/문단으로 name·description 보완."""
    fm = _parse_frontmatter(text)
    name = fm.get("name", "").strip()
    desc = fm.get("description", "").strip()

    if not name:
        h = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        name = h.group(1).strip() if h else skill_dir.name

    if not desc:
        # frontmatter 이후 첫 비어있지 않은 산문 줄 (헤더·--- 제외)
        body = re.sub(r"^\s*---\s*\n.*?\n---\s*\n", "", text, flags=re.DOTALL)
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("---"):
                desc = s
                break

    return name, desc


# ═══════════════════════════════════════════
#  설치 경로 결정
# ═══════════════════════════════════════════
def collect_install_paths() -> list:
    """installed_plugins.json 에서 활성 설치 (plugin, version, path, marketplace) 목록.
    파일 없거나 파싱 실패 시 빈 목록 → 폴백 글롭 사용."""
    if not INSTALLED_PLUGINS.exists():
        return []
    try:
        data = json.loads(INSTALLED_PLUGINS.read_text(encoding="utf-8"))
    except Exception:
        return []
    result = []
    for key, entries in (data.get("plugins") or {}).items():
        # key 예: "oh-my-claudecode@omc"
        plugin = key.split("@", 1)[0]
        marketplace = key.split("@", 1)[1] if "@" in key else ""
        for e in entries if isinstance(entries, list) else []:
            path = e.get("installPath", "")
            if not path:
                continue
            result.append({
                "plugin": plugin,
                "marketplace": marketplace,
                "version": e.get("version", ""),
                "path": Path(path),
            })
    return result


def _glob_skill_dirs_fallback() -> list:
    """installed_plugins.json 없을 때: cache/**/skills/*/SKILL.md 글롭 후
    (source, skill_name) 기준 최신 버전 경로만 남긴다."""
    found = {}  # (source, skill_name) -> (version_str, SKILL.md path)
    if not CACHE_DIR.exists():
        return []
    for sk in CACHE_DIR.glob("**/skills/*/SKILL.md"):
        # .../<market>/<plugin>/<version>/skills/<skill>/SKILL.md
        parts = sk.parts
        try:
            skills_idx = len(parts) - 1 - list(reversed(parts)).index("skills")
        except ValueError:
            continue
        version = parts[skills_idx - 1] if skills_idx - 1 >= 0 else ""
        plugin = parts[skills_idx - 2] if skills_idx - 2 >= 0 else ""
        skill_name = sk.parent.name
        k = (plugin, skill_name)
        prev = found.get(k)
        if prev is None or version > prev[0]:
            found[k] = (version, sk, plugin)
    out = []
    for (plugin, _skill_name), (version, sk, _p) in found.items():
        out.append({"plugin": plugin, "marketplace": "", "version": version, "path_skillmd": sk})
    return out


# ═══════════════════════════════════════════
#  인벤토리 수집
# ═══════════════════════════════════════════
def collect_skills() -> list:
    """설치된 스킬 목록을 dict 리스트로 반환.
    각 항목: {name, description, plugin, source, version, path}"""
    skills = []
    seen = set()  # (plugin, name) dedup

    installs = collect_install_paths()
    skill_md_files = []
    if installs:
        for ins in installs:
            skills_root = ins["path"] / "skills"
            if not skills_root.exists():
                continue
            for sk in skills_root.glob("*/SKILL.md"):
                skill_md_files.append((sk, ins["plugin"], ins["marketplace"], ins["version"]))
    else:
        for f in _glob_skill_dirs_fallback():
            skill_md_files.append((f["path_skillmd"], f["plugin"], f.get("marketplace", ""), f["version"]))

    for sk, plugin, marketplace, version in skill_md_files:
        try:
            text = sk.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        name, desc = _extract_name_desc(sk.parent, text)
        key = (plugin, name)
        if key in seen:
            continue
        seen.add(key)
        skills.append({
            "name": name,
            "description": desc,
            "plugin": plugin,
            "source": marketplace or plugin,
            "version": version,
            "path": str(sk),
        })
    skills.sort(key=lambda s: (s["plugin"], s["name"]))
    return skills


def load_cheatsheet_text() -> str:
    """docs/skill_cheatsheet.md 본문(있으면). 대조로 '정리됨/미활용' 판정."""
    if not CHEATSHEET.exists():
        return ""
    try:
        return CHEATSHEET.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _is_documented(skill_name: str, cheatsheet_text: str) -> bool:
    """치트시트 본문에 스킬 이름이 (단어 경계로) 등장하면 '정리됨'."""
    if not cheatsheet_text or not skill_name:
        return False
    return re.search(re.escape(skill_name), cheatsheet_text, flags=re.IGNORECASE) is not None


def build_inventory() -> dict:
    """전체 인벤토리 조립. 반환 dict:
    {skills:[...], total, by_plugin:{plugin:count}, cheatsheet_exists, documented, unused, unused_count}"""
    skills = collect_skills()
    cheatsheet_text = load_cheatsheet_text()
    cheatsheet_exists = bool(cheatsheet_text)

    documented, unused = [], []
    for s in skills:
        s["documented"] = _is_documented(s["name"], cheatsheet_text)
        s["status"] = "정리됨" if s["documented"] else "새것/미활용"
        (documented if s["documented"] else unused).append(s["name"])

    by_plugin = {}
    for s in skills:
        by_plugin[s["plugin"]] = by_plugin.get(s["plugin"], 0) + 1

    return {
        "skills": skills,
        "total": len(skills),
        "by_plugin": by_plugin,
        "cheatsheet_exists": cheatsheet_exists,
        "documented": documented,
        "unused": unused,
        "unused_count": len(unused),
    }


def format_for_prompt(inv: dict, limit: int = 60) -> str:
    """LLM 프롬프트 주입용 요약 텍스트. proposer 가 사용."""
    lines = [
        f"설치 스킬 총 {inv['total']}개 "
        f"({' · '.join(f'{p} {c}' for p, c in sorted(inv['by_plugin'].items()))})",
        f"치트시트 정리됨 {len(inv['documented'])} · 미활용 {inv['unused_count']}",
        "",
    ]
    for s in inv["skills"][:limit]:
        mark = "☑" if s["documented"] else "✨"
        desc = (s["description"] or "")[:110]
        lines.append(f"  {mark} [{s['plugin']}] {s['name']} — {desc}")
    if inv["total"] > limit:
        lines.append(f"  … 외 {inv['total'] - limit}개")
    return "\n".join(lines)


# ═══════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="설치 스킬·플러그인 인벤토리 수집기 (read-only)",
    )
    parser.add_argument("--json", action="store_true", help="인벤토리 JSON 출력 (파이프용)")
    args = parser.parse_args()

    inv = build_inventory()

    if args.json:
        print(json.dumps(inv, ensure_ascii=False, indent=2))
        return

    print(f"\n{'='*64}")
    print(f"  🧩 스킬·플러그인 인벤토리  총 {inv['total']}개")
    print(f"{'='*64}")
    print(f"  플러그인별: " + " · ".join(f"{p} {c}" for p, c in sorted(inv["by_plugin"].items())))
    ct = "있음" if inv["cheatsheet_exists"] else "없음(뼈대 필요)"
    print(f"  치트시트({CHEATSHEET.name}): {ct}  |  정리됨 {len(inv['documented'])}  |  ✨미활용 {inv['unused_count']}")
    print(f"{'-'*64}")
    for s in inv["skills"]:
        mark = "☑정리됨" if s["documented"] else "✨미활용"
        desc = (s["description"] or "")[:80]
        print(f"  {mark}  [{s['plugin']}] {s['name']}")
        if desc:
            print(f"          {desc}")
    print(f"{'='*64}")
    if inv["unused_count"]:
        print(f"  ✨ 미활용 {inv['unused_count']}개: " + ", ".join(inv["unused"][:40]))
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
