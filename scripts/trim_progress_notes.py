"""status/monthly_ops_plan.json 의 progress_note 를 최신 3블록만 남기고 나머지를
status/monthly_ops_plan_이력.md 로 옮긴다 (CLAUDE.md SSOT .md 규칙 — 누적기록 금지).

블록 = '▶[' (▶[) 로 시작하는 경위 로그 한 덩이. 그 앞의 체크리스트 본문은 손대지 않는다.
기본은 --dry-run(집계만 출력) · 실제로 쓰려면 --apply.
"""
import argparse
import json
import re
import sys

PLAN_PATH = "status/monthly_ops_plan.json"
HISTORY_PATH = "status/monthly_ops_plan_이력.md"
MARK = "▶["  # ▶[
KEEP = 3
MIN_BLOCKS_TO_TRIM = 4

BLOCK_SPLIT = re.compile(r"(?=" + re.escape(MARK) + r")")
CHECKLIST_LINE = re.compile(r"^\s*[□☑]")  # □ or ☑


def find_objectives(data):
    """[(month_label, path, objective_dict), ...] for the three known locations."""
    out = []
    months = data.get("months", {})
    for mkey, m in months.items():
        for i, o in enumerate(m.get("objectives", [])):
            out.append((mkey, f"months.{mkey}.objectives[{i}]", o))
        arch = m.get("archived_objectives")
        if arch:
            items = arch.get("items", []) if isinstance(arch, dict) else arch
            for i, o in enumerate(items):
                out.append((mkey, f"months.{mkey}.archived_objectives.items[{i}]", o))
    arch_top = data.get("archived_objectives")
    if arch_top:
        items = arch_top.get("items", []) if isinstance(arch_top, dict) else arch_top
        for i, o in enumerate(items):
            month = (o.get("id") or "")[:7] or "archived"
            out.append((month, f"archived_objectives[{i}]", o))
    return out


def split_blocks(note):
    """(prefix, blocks) — prefix = everything before the first ▶[ (untouched)."""
    idx = note.find(MARK)
    if idx == -1:
        return note, []
    prefix = note[:idx]
    blocks = [b for b in BLOCK_SPLIT.split(note[idx:]) if b]
    return prefix, blocks


def count_checklist_lines(note):
    return sum(1 for line in note.split("\n") if CHECKLIST_LINE.match(line))


def load_history_sections(text):
    """{heading: body_text} keyed by exact '## ...' line, preserving order via dict."""
    sections = {}
    order = []
    heading = None
    buf = []
    for line in text.split("\n"):
        if line.startswith("## "):
            if heading is not None:
                sections[heading] = "\n".join(buf)
            heading = line
            buf = []
            order.append(heading)
        else:
            buf.append(line)
    if heading is not None:
        sections[heading] = "\n".join(buf)
    return sections, order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다 (기본은 dry-run)")
    args = ap.parse_args()

    with open(PLAN_PATH, encoding="utf-8") as f:
        data = json.load(f)

    before_checklist_total = 0
    plan = []  # (path, prefix, keep_note, archive_text, heading)
    for month, path, o in find_objectives(data):
        note = o.get("progress_note", "")
        if not note:
            continue
        before_checklist_total += count_checklist_lines(note)
        prefix, blocks = split_blocks(note)
        if len(blocks) < MIN_BLOCKS_TO_TRIM:
            continue
        archive_blocks, keep_blocks = blocks[:-KEEP], blocks[-KEEP:]
        new_note = prefix + "".join(keep_blocks)
        heading = f"## {month} · {o.get('title', '')}"
        plan.append((path, o, len(note), len(new_note), "".join(archive_blocks), heading))

    if not plan:
        print("손댈 칸 없음 (4블록 이상인 progress_note 없음)")
        return

    total_before = sum(p[2] for p in plan)
    total_after = sum(p[3] for p in plan)
    print(f"대상 칸: {len(plan)}개")
    for path, _, before, after, archived, heading in plan:
        print(f"  {path}: {before}자 -> {after}자 (이력으로 {len(archived)}자)")
    print(f"합계: {total_before}자 -> {total_after}자")

    if not args.apply:
        print("(dry-run — 적용하려면 --apply)")
        return

    # 이력 파일에 append (중복 방지: 섹션 본문에 이미 있는 블록은 다시 안 넣는다)
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            history_text = f.read()
    except FileNotFoundError:
        history_text = "# 월간운영계획 progress_note 이력\n\n"

    sections, order = load_history_sections(history_text)
    for path, o, before, after, archived, heading in plan:
        existing = sections.get(heading, "")
        if archived and archived not in existing:
            sections[heading] = existing + "\n" + archived
            if heading not in order:
                order.append(heading)
        o["progress_note"] = o["progress_note"]  # placeholder; set below

    # rebuild new_note into the objective dicts now that history is staged
    for path, o, before, after, archived, heading in plan:
        prefix, blocks = split_blocks(o["progress_note"])
        keep_blocks = blocks[-KEEP:]
        o["progress_note"] = prefix + "".join(keep_blocks)

    header = history_text.split("## ", 1)[0] if "## " in history_text else history_text
    if not header.strip():
        header = "# 월간운영계획 progress_note 이력\n\n"
    new_history = header
    for heading in order:
        new_history += heading + "\n" + sections[heading].rstrip("\n") + "\n\n"

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write(new_history)

    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    after_checklist_total = 0
    for _month, _path, o in find_objectives(data):
        after_checklist_total += count_checklist_lines(o.get("progress_note", ""))

    print(f"체크리스트 줄(전체 파일): 적용전 {before_checklist_total} -> 적용후 {after_checklist_total}")
    print("적용 완료.")


if __name__ == "__main__":
    main()
