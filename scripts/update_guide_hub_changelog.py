#!/usr/bin/env python3
"""
update_guide_hub_changelog.py
------------------------------
git log 기반으로 가이드허브 home 페이지의
  1) 최신 카드 (<!-- AUTO:LATEST-START --> ~ <!-- AUTO:LATEST-END -->)
  2) 업데이트 기록 표 (<!-- AUTO:TABLE-START --> ~ <!-- AUTO:TABLE-END -->)
두 영역을 자동 갱신합니다.

사용법:
    python scripts/update_guide_hub_changelog.py           # 실제 반영
    python scripts/update_guide_hub_changelog.py --dry-run # 변경 미리보기
"""

import argparse
import subprocess
import sys
import re
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows CP949 환경에서 한글 출력 보장
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 경로 설정 ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE_HTML = REPO_ROOT / "3. 웰페리온 가이드" / "wellperion_guide(main).html"

# ── 마커 ───────────────────────────────────────────────────────────────────
LATEST_START = "<!-- AUTO:LATEST-START -->"
LATEST_END   = "<!-- AUTO:LATEST-END -->"
TABLE_START  = "<!-- AUTO:TABLE-START -->"
TABLE_END    = "<!-- AUTO:TABLE-END -->"

# ── git 커밋 제외 패턴 (가이드허브 자체 자동 커밋 제외) ──────────────────
AUTO_COMMIT_PREFIX = "auto(changelog):"


def run(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=REPO_ROOT
    )
    if result.returncode != 0:
        print(f"[ERROR] {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_commits(max_count: int = 15) -> list[dict]:
    """최근 1주일 이내 커밋을 최대 max_count건 추출 (자동 커밋 제외)."""
    raw = run([
        "git", "log",
        "--format=%H\x1f%ad\x1f%s",
        "--date=format:%Y-%m-%d",
        "--since=1 week ago",
        f"--max-count={max_count * 2}",  # 필터 여유분
    ])
    commits = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        if subject.startswith(AUTO_COMMIT_PREFIX):
            continue
        commits.append({"sha": sha[:8], "date": date, "subject": subject})
        if len(commits) >= max_count:
            break
    return commits


def build_latest_card(commits: list[dict]) -> str:
    """최근 5건 커밋으로 최신 카드 HTML 생성."""
    recent = commits[:5]
    if not recent:
        return ""

    today = datetime.now(tz=timedelta(hours=9).__class__ and
                         timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    lines = [LATEST_START]
    lines.append(f'    <div class="card grow">')
    lines.append(f'      <h4>최신 업데이트 — {today} (자동 갱신)</h4>')
    for c in recent:
        # 긴 제목은 80자 이내로 잘라 표시
        subj = c["subject"]
        if len(subj) > 80:
            subj = subj[:77] + "…"
        lines.append(f'      <p><strong>{c["date"]}</strong> {subj}</p>')
    lines.append(f'    </div>')
    lines.append(LATEST_END)
    return "\n".join(lines)


def build_table_row(commits: list[dict]) -> str:
    """커밋 목록을 업데이트 기록 표 행(tr)으로 변환 — 날짜별 그룹화."""
    if not commits:
        return ""

    # 날짜별 그룹화
    grouped: dict[str, list[str]] = {}
    for c in commits:
        grouped.setdefault(c["date"], []).append(c["subject"])

    rows = []
    for date in sorted(grouped.keys(), reverse=True):
        subjects = " · ".join(grouped[date])
        if len(subjects) > 200:
            subjects = subjects[:197] + "…"
        rows.append(
            f'      <tr><td><strong>{date} (자동)</strong></td>'
            f'<td>{subjects}</td></tr>'
        )
    return "\n".join(rows)


def ensure_markers(html: str) -> tuple[str, bool]:
    """
    마커가 없으면 HTML에 자동으로 삽입합니다.
    반환: (수정된_html, 마커가_삽입됐는지_여부)
    """
    inserted = False

    # 최신 카드 마커: 기존 <div class="card grow"> 최신 블록을 감쌈
    if LATEST_START not in html:
        # 홈 article 안의 첫 번째 card grow 블록 (최신 카드) 앞뒤에 마커 삽입
        # 패턴: <div class="card grow">\n      <h4>최신 으로 시작하는 블록
        pattern = r'(<div class="card grow">\s*<h4>최신.*?</div>)'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            old = match.group(0)
            new = f"{LATEST_START}\n    {old}\n    {LATEST_END}"
            html = html[:match.start()] + new + html[match.end():]
            inserted = True
            print("[INFO] 최신 카드 마커 자동 삽입 완료")
        else:
            print("[WARN] 최신 카드 블록을 찾지 못했습니다. 수동으로 마커를 추가하세요.")

    # 업데이트 기록 표 마커: <h3>🕐 업데이트 기록</h3> 다음 table 안에 삽입
    if TABLE_START not in html:
        # 테이블 헤더 행 다음에 마커 삽입
        pattern = r'(<h3><span class="ico">🕐</span>업데이트 기록</h3>\s*<table>.*?<tr><th[^>]*>날짜</th>.*?</tr>)'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            old = match.group(0)
            new = f"{old}\n      {TABLE_START}\n      {TABLE_END}"
            html = html[:match.start()] + new + html[match.end():]
            inserted = True
            print("[INFO] 업데이트 기록 표 마커 자동 삽입 완료")
        else:
            print("[WARN] 업데이트 기록 표를 찾지 못했습니다. 수동으로 마커를 추가하세요.")

    return html, inserted


def apply_latest_card(html: str, card_html: str) -> str:
    """최신 카드 영역을 새 내용으로 교체."""
    pattern = re.compile(
        re.escape(LATEST_START) + r".*?" + re.escape(LATEST_END),
        re.DOTALL
    )
    if not pattern.search(html):
        print("[WARN] 최신 카드 마커를 찾을 수 없습니다.")
        return html
    return pattern.sub(card_html, html)


def apply_table_rows(html: str, new_rows: str) -> str:
    """업데이트 기록 표에서 기존 자동 행을 제거하고 새 행을 맨 위에 삽입."""
    # 마커 사이의 내용을 새 행으로 교체
    pattern = re.compile(
        re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END),
        re.DOTALL
    )
    replacement = f"{TABLE_START}\n{new_rows}\n      {TABLE_END}"
    if not pattern.search(html):
        print("[WARN] 업데이트 기록 표 마커를 찾을 수 없습니다.")
        return html
    return pattern.sub(replacement, html)


def main():
    parser = argparse.ArgumentParser(description="가이드허브 home 페이지 최신 카드 자동 갱신")
    parser.add_argument("--dry-run", action="store_true", help="실제 파일 수정 없이 변경 미리보기")
    args = parser.parse_args()

    # 1. HTML 읽기
    if not GUIDE_HTML.exists():
        print(f"[ERROR] 파일 없음: {GUIDE_HTML}", file=sys.stderr)
        sys.exit(1)
    original_html = GUIDE_HTML.read_text(encoding="utf-8")

    # 2. 마커 확인 및 자동 삽입
    html, markers_inserted = ensure_markers(original_html)

    # 3. git 커밋 추출
    commits = get_commits(max_count=15)
    if not commits:
        print("[INFO] 최근 1주일 내 커밋 없음. 종료.")
        sys.exit(0)

    print(f"[INFO] 커밋 {len(commits)}건 추출:")
    for c in commits:
        print(f"       {c['date']} {c['sha']} {c['subject'][:60]}")

    # 4. 새 HTML 조각 생성
    card_html = build_latest_card(commits)
    table_rows = build_table_row(commits)

    # 5. 교체
    new_html = apply_latest_card(html, card_html)
    new_html = apply_table_rows(new_html, table_rows)

    # 6. 변경 여부 확인
    if new_html == original_html and not markers_inserted:
        print("[INFO] 변경 없음. 파일 그대로 유지.")
        sys.exit(0)

    # 7. dry-run / 실제 쓰기
    if args.dry_run:
        print("\n[DRY-RUN] 변경 미리보기 (실제 파일 수정 없음):")
        print("-" * 60)
        # 최신 카드 미리보기
        print("■ 최신 카드 영역:")
        print(card_html)
        print()
        # 테이블 행 미리보기
        print("■ 업데이트 기록 표 자동 행:")
        print(table_rows)
        print("-" * 60)
        print("[DRY-RUN] 완료. 파일은 수정되지 않았습니다.")
    else:
        GUIDE_HTML.write_text(new_html, encoding="utf-8")
        print(f"[INFO] 파일 갱신 완료: {GUIDE_HTML}")


if __name__ == "__main__":
    main()
