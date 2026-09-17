"""status/monthly_ops_plan.json 의 progress_note 를 최신 3블록만 남기고 나머지를
status/monthly_ops_plan_이력.md 로 옮긴다 (CLAUDE.md SSOT .md 규칙 — 누적기록 금지).

블록 = '▶[' (▶[) 로 시작하는 경위 로그 한 덩이. 그 앞의 체크리스트 본문은 손대지 않는다.
기본은 --dry-run(집계만 출력) · 실제로 쓰려면 --apply.
"""
import argparse
import json
import re
import sys

# ★2026-09-17 시토 — 낡은 판 되쓰기 가드는 이제 queue_lock.mutate_json 관문 안에 있다(자가치유
#   포함). 이 파일은 더 이상 refuse_if_older_than_head 를 직접 부르지 않는다 — main() 참조.

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


_BLOCK_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def select_blocks(blocks):
    """(keep_blocks, archive_blocks) — 원래 순서 유지.
    ★2026-09-17 시우 수리: 종전 blocks[-KEEP:] 는 「뒤 3개 = 최신」을 가정했는데 이 파일의 note 는
    최신 블록이 맨 앞에 붙는다(gm_handoff·GM 지시 기록). 그래서 07:00 마다 최신 GM 지시 블록이 이력으로
    밀려나고(09-16 321→300 · 09-17 352→317 체크리스트 줄 감소) 「GM 표식이 사라진다」가 재발했다.
    규칙: ①□/☑ 체크리스트가 든 블록은 절대 이력으로 보내지 않는다 ②나머지 중 날짜(YYYY-MM-DD)가 가장
    최신인 KEEP 개를 남긴다(날짜 없는 블록 = 판정 불가라 남긴다)."""
    dated = []
    keep = set()
    for i, b in enumerate(blocks):
        if count_checklist_lines(b) or not _BLOCK_DATE.search(b):
            keep.add(i)
        else:
            dated.append((max(_BLOCK_DATE.findall(b)), i))
    for _, i in sorted(dated, reverse=True)[:KEEP]:
        keep.add(i)
    keep_blocks = [b for i, b in enumerate(blocks) if i in keep]
    archive_blocks = [b for i, b in enumerate(blocks) if i not in keep]
    return keep_blocks, archive_blocks


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


def _compute_trim_plan(data):
    """(before_checklist_total, plan) — plan = [(path, o, before_len, after_len, archive_text, heading), ...].
    data 하나만의 순수함수 — dry-run 미리보기와 실제 적용(mutate_json 안 fresh 데이터) 양쪽에서 같이 쓴다."""
    before_checklist_total = 0
    plan = []
    for month, path, o in find_objectives(data):
        note = o.get("progress_note", "")
        if not note:
            continue
        before_checklist_total += count_checklist_lines(note)
        prefix, blocks = split_blocks(note)
        if len(blocks) < MIN_BLOCKS_TO_TRIM:
            continue
        keep_blocks, archive_blocks = select_blocks(blocks)
        if not archive_blocks:
            continue
        new_note = prefix + "".join(keep_blocks)
        heading = f"## {month} · {o.get('title', '')}"
        plan.append((path, o, len(note), len(new_note), "".join(archive_blocks), heading))
    return before_checklist_total, plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다 (기본은 dry-run)")
    args = ap.parse_args()

    with open(PLAN_PATH, encoding="utf-8") as f:
        data = json.loads(f.read())

    before_checklist_total, plan = _compute_trim_plan(data)

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

    # ★2026-09-17 시토 — queue_lock.mutate_json 관문으로 통일(GM 「낡은 판 되쓰기 근본 해결」).
    # 트림 판정은 fresh 데이터 하나만의 순수함수(_compute_trim_plan)라 잠금 안에서 다시 계산해도
    # 결과가 같다 — 디스크가 HEAD 보다 낡았으면 자가치유된 뒤 그 판 위에서 트림한다.
    outcome = {"applied": False}

    def _mutator(fresh_data):
        _, fresh_plan = _compute_trim_plan(fresh_data)
        if not fresh_plan:
            return fresh_data  # 이미 트림됨(다른 실행이 먼저 처리) — 손대지 않는다

        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                history_text = f.read()
        except FileNotFoundError:
            history_text = "# 월간운영계획 progress_note 이력\n\n"

        sections, order = load_history_sections(history_text)
        for path, o, before, after, archived, heading in fresh_plan:
            existing = sections.get(heading, "")
            if archived and archived not in existing:
                sections[heading] = existing + "\n" + archived
                if heading not in order:
                    order.append(heading)

        for path, o, before, after, archived, heading in fresh_plan:
            prefix, blocks = split_blocks(o["progress_note"])
            keep_blocks, _ = select_blocks(blocks)
            o["progress_note"] = prefix + "".join(keep_blocks)

        header = history_text.split("## ", 1)[0] if "## " in history_text else history_text
        if not header.strip():
            header = "# 월간운영계획 progress_note 이력\n\n"
        new_history = header
        for heading in order:
            new_history += heading + "\n" + sections[heading].rstrip("\n") + "\n\n"

        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            f.write(new_history)

        outcome["applied"] = True
        return fresh_data

    from queue_lock import mutate_json
    try:
        mutate_json(PLAN_PATH, _mutator, holder="trim_progress_notes")
    except Exception as e:
        print(f"[거부] {PLAN_PATH} 저장 실패 — {e}")
        return

    if not outcome["applied"]:
        print("적용 시점 재확인 결과 손댈 칸 없음 — 건너뜀")
        return

    with open(PLAN_PATH, encoding="utf-8") as f:
        after_data = json.loads(f.read())
    after_checklist_total = 0
    for _month, _path, o in find_objectives(after_data):
        after_checklist_total += count_checklist_lines(o.get("progress_note", ""))

    print(f"체크리스트 줄(전체 파일): 적용전 {before_checklist_total} -> 적용후 {after_checklist_total}")
    print("적용 완료.")


def _selftest():
    """최신이 맨 앞인 note 에서 최신 3개·체크리스트 블록이 남는지 — 09-17 수리 자체점검."""
    note = ("본문\n▶[GM 지시 2026-09-16] 최신\n□ 남을 체크\n▶[2026-09-10] 둘째\n▶[2026-09-05] 셋째\n"
            "▶[2026-08-20] 넷째\n▶[2026-08-01] 다섯째\n☑ 끝\n▶[2026-07-01] 여섯째\n")
    prefix, blocks = split_blocks(note)
    keep, arch = select_blocks(blocks)
    assert prefix == "본문\n" and len(blocks) == 6
    # 체크리스트 든 블록(09-16·08-01)은 무조건 남고, 나머지 중 최신 3(09-10·09-05·08-20)이 남는다
    d = lambda bs: [_BLOCK_DATE.search(b).group(1) for b in bs]
    assert d(keep) == ["2026-09-16", "2026-09-10", "2026-09-05", "2026-08-20", "2026-08-01"], d(keep)
    assert d(arch) == ["2026-07-01"], d(arch)
    print("SELFTEST OK — 체크리스트 블록 유지 + 최신 3 · 옛 블록만 이력행")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _selftest()
    else:
        main()
