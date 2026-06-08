#!/usr/bin/env python3
"""
update_guide_hub_changelog.py
------------------------------
status/_queue.json 의 DONE 항목을 기반으로 웰페리온 ERP home 페이지의
  1) 최신 카드 (<!-- AUTO:LATEST-START --> ~ <!-- AUTO:LATEST-END -->)
  2) 업데이트 기록 표 (<!-- AUTO:TABLE-START --> ~ <!-- AUTO:TABLE-END -->)
두 영역을 자동 갱신합니다.

소스: status/_queue.json  status=DONE 항목 (processed_at 내림차순)
표시 형식: ✅ [시모] AI #9 북극성 항해 설계 발행 완료 — 2026-06-08
커밋 해시·기술 prefix(fix/feat 등) 노출 없음.

사용법:
    python scripts/update_guide_hub_changelog.py           # 실제 반영
    python scripts/update_guide_hub_changelog.py --dry-run # 변경 미리보기
"""

import argparse
import json
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
REPO_ROOT  = Path(__file__).resolve().parent.parent
GUIDE_HTML = REPO_ROOT / "3. 웰페리온 가이드" / "wellperion_guide(main).html"
QUEUE_JSON = REPO_ROOT / "status" / "_queue.json"

# ── 마커 ───────────────────────────────────────────────────────────────────
LATEST_START = "<!-- AUTO:LATEST-START -->"
LATEST_END   = "<!-- AUTO:LATEST-END -->"
TABLE_START  = "<!-- AUTO:TABLE-START -->"
TABLE_END    = "<!-- AUTO:TABLE-END -->"

# ── C-Level 표시명 매핑 ────────────────────────────────────────────────────
CLEVEL_LABEL = {
    "ceo": "웰리",
    "cfo": "시뽀",
    "chro": "시로",
    "cmo": "시모",
    "coo": "시우",
    "cpo": "시포",
    "cto": "시토",
}


def get_done_items(max_count: int = 10) -> list[dict]:
    """
    _queue.json 에서 status=DONE 항목을 processed_at 내림차순으로 최대 max_count건 반환.
    폐기(ABANDONED) · 진행중(IN_PROGRESS) · 대기(PENDING) 제외.
    """
    if not QUEUE_JSON.exists():
        print(f"[WARN] _queue.json 없음: {QUEUE_JSON}", file=sys.stderr)
        return []

    with open(QUEUE_JSON, encoding="utf-8") as f:
        data = json.load(f)

    done = [item for item in data if item.get("status") == "DONE"]
    # processed_at 기준 내림차순 (없으면 enqueued_at fallback)
    done.sort(
        key=lambda x: x.get("processed_at") or x.get("enqueued_at") or "",
        reverse=True,
    )
    return done[:max_count]


def format_item(item: dict) -> dict:
    """
    항목 하나를 표시용 dict로 변환.
    반환 키: date, label, title_clean
    """
    clevel_raw = (item.get("clevel") or "").lower()
    label = CLEVEL_LABEL.get(clevel_raw, clevel_raw.upper())
    date  = item.get("processed_at") or item.get("enqueued_at") or ""

    # title 에서 이미 [XXX] 형태 prefix 가 들어있는 경우 그대로 사용,
    # 없으면 앞에 붙임 (부분 매칭: [시모], [시모-08] 등 모두 포함)
    title = (item.get("title") or "").strip()
    # title이 [ 로 시작하면 이미 bracket prefix 있음
    if title.startswith("["):
        title_clean = title
    else:
        title_clean = f"[{label}] {title}"

    # 80자 초과 시 말줄임
    if len(title_clean) > 80:
        title_clean = title_clean[:77] + "…"

    return {"date": date, "label": label, "title_clean": title_clean}


def build_latest_card(items: list[dict]) -> str:
    """최근 5건 완료 배(항로)로 최신 카드 HTML 생성."""
    recent = items[:5]
    if not recent:
        return ""

    today = datetime.now(tz=timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    lines = [LATEST_START]
    lines.append('    <div class="card grow">')
    lines.append(f'      <h4>✅ 오늘의 항로 — 완료된 배 ({today} 기준)</h4>')
    for it in recent:
        fmt = format_item(it)
        lines.append(
            f'      <p><strong>{fmt["date"]}</strong>'
            f' ✅ {fmt["title_clean"]}</p>'
        )
    lines.append('    </div>')
    lines.append(LATEST_END)
    return "\n".join(lines)


def build_table_rows(items: list[dict]) -> str:
    """완료 배 목록을 업데이트 기록 표 행(tr)으로 변환 — 날짜별 그룹화."""
    if not items:
        return ""

    grouped: dict[str, list[str]] = {}
    for item in items:
        fmt = format_item(item)
        grouped.setdefault(fmt["date"], []).append(f'✅ {fmt["title_clean"]}')

    rows = []
    for date in sorted(grouped.keys(), reverse=True):
        entries = " · ".join(grouped[date])
        if len(entries) > 200:
            entries = entries[:197] + "…"
        rows.append(
            f'      <tr><td><strong>{date} (항로완료)</strong></td>'
            f'<td>{entries}</td></tr>'
        )
    return "\n".join(rows)


def ensure_markers(html: str) -> tuple[str, bool]:
    """마커가 없으면 HTML에 자동으로 삽입."""
    inserted = False

    if LATEST_START not in html:
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

    if TABLE_START not in html:
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
    pattern = re.compile(
        re.escape(LATEST_START) + r".*?" + re.escape(LATEST_END),
        re.DOTALL,
    )
    if not pattern.search(html):
        print("[WARN] 최신 카드 마커를 찾을 수 없습니다.")
        return html
    return pattern.sub(card_html, html)


def apply_table_rows(html: str, new_rows: str) -> str:
    pattern = re.compile(
        re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END),
        re.DOTALL,
    )
    replacement = f"{TABLE_START}\n{new_rows}\n      {TABLE_END}"
    if not pattern.search(html):
        print("[WARN] 업데이트 기록 표 마커를 찾을 수 없습니다.")
        return html
    return pattern.sub(replacement, html)


def main():
    parser = argparse.ArgumentParser(
        description="웰페리온 ERP home — G1 항로 완료 배 narrative 갱신"
    )
    parser.add_argument("--dry-run", action="store_true", help="실제 파일 수정 없이 변경 미리보기")
    args = parser.parse_args()

    # 1. HTML 읽기
    if not GUIDE_HTML.exists():
        print(f"[ERROR] 파일 없음: {GUIDE_HTML}", file=sys.stderr)
        sys.exit(1)
    original_html = GUIDE_HTML.read_text(encoding="utf-8")

    # 2. 마커 확인 및 자동 삽입
    html, markers_inserted = ensure_markers(original_html)

    # 3. _queue.json DONE 항목 추출
    items = get_done_items(max_count=10)
    if not items:
        print("[INFO] DONE 항목 없음. 종료.")
        sys.exit(0)

    print(f"[INFO] 항로 완료 배 {len(items)}건 추출:")
    for it in items:
        fmt = format_item(it)
        print(f"       {fmt['date']} {fmt['title_clean'][:60]}")

    # 4. 새 HTML 조각 생성
    card_html  = build_latest_card(items)
    table_rows = build_table_rows(items)

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
        print("■ 최신 카드 영역:")
        print(card_html)
        print()
        print("■ 업데이트 기록 표 자동 행:")
        print(table_rows)
        print("-" * 60)
        print("[DRY-RUN] 완료. 파일은 수정되지 않았습니다.")
    else:
        GUIDE_HTML.write_text(new_html, encoding="utf-8")
        print(f"[INFO] 파일 갱신 완료: {GUIDE_HTML}")


if __name__ == "__main__":
    main()
