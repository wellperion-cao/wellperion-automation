#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Patch hangro_board.py: replace render section with 3-sector markdown table (약속 L16)."""
import sys
from pathlib import Path

path = Path(__file__).parent / "hangro_board.py"
content = path.read_text(encoding="utf-8")

start_marker = "# ── 렌더 한 줄 "
end_marker = '    return "\\n".join(lines), secs\n'

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker, start_idx)

if start_idx == -1:
    # Try without trailing spaces
    start_marker2 = "# ── 렌더 한 줄"
    start_idx = content.find(start_marker2)

if start_idx == -1:
    sys.exit("NOTFOUND: start_marker")
if end_idx == -1:
    sys.exit("NOTFOUND: end_marker")

end_idx_final = end_idx + len(end_marker)
print(f"Block [{start_idx}:{end_idx_final}]")

NEW_BLOCK = (
    "# ── 닉코네임 매핑 (clevel 필드 → 닉코네임, 약속 L16) ──────────────────\n"
    "CLEVEL_NICK: dict[str, str] = {\n"
    '    "CEO": "웰리",   "AI CEO": "웰리",\n'
    '    "CMO": "시모",   "AI CMO": "시모",\n'
    '    "COO": "시우",   "AI COO": "시우",\n'
    '    "CTO": "시토",   "AI CTO": "시토",\n'
    '    "CPO": "시포",   "AI CPO": "시포",\n'
    '    "CFO": "시븴",   "AI CFO": "시븴",\n'
    '    "CHRO": "시로",  "AI CHRO": "시로",\n'
    "}\n"
    "\n"
    "\n"
    "def _nick(owner: str) -> str:\n"
    '    """clevel 필드 → 닉코네임. 이미 닉코네임이거나 GM이면 그대로."""\n'
    "    u = owner.strip().upper()\n"
    "    for k, v in CLEVEL_NICK.items():\n"
    "        if k in u:\n"
    "            return v\n"
    '    if "김남욱" in owner or "GM" in owner.upper():\n'
    '        return "GM"\n'
    "    return owner[:4] if owner else \"?\"\n"
    "\n"
    "\n"
    "def _md_table(rows: list[tuple[str, str, str, str, str]]) -> str:\n"
    '    """마크다운 5칸 표: 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언"""\n'
    "    if not rows:\n"
    '        return "| — | — | (없음) | | |\\n"\n'
    '    header = "| 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언 |"\n'
    '    sep    = "|---|---|---|---|---|"\n'
    '    body   = "\\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows)\n'
    '    return f"{header}\\n{sep}\\n{body}\\n"\n'
    "\n"
    "\n"
    "def _item_to_row(it: dict, ship_col_extra: str = \"\") -> tuple[str, str, str, str, str]:\n"
    '    """아이템 dict → 5-tuple for _md_table.\n'
    "    ship_col_extra: 꿈리표 (예: '보류', '🔗', '🌀') — 배 칸 아이콘 뒤에 붙음.\"\"\"\n"
    '    ship  = it["_ship"]\n'
    '    icon  = ship["icon"]\n'
    '    nick  = _nick(str(it.get("owner", "")))\n'
    '    title = str(it.get("title", ""))\n'
    '    badges = ("🔴" if ship.get("urgent") else "") + ("🌟" if ship.get("northstar") else "")\n'
    '    due   = it.get("end_date", "")\n'
    '    due_s = f" ~{due[5:10]}" if due and len(due) >= 10 else ""\n'
    '    title_col  = f"{title}{badges}{due_s}".strip()\n'
    '    desc       = str(it.get("간단설명") or "").strip()\n'
    '    advice     = str(it.get("핵심조언") or "").strip()\n'
    '    ship_col   = f"{icon} {ship_col_extra}".strip() if ship_col_extra else icon\n'
    "    return (ship_col, nick, title_col, desc, advice)\n"
    "\n"
    "\n"
    "# ── 박스표 (요약 카운터용) ────────────────────────────────────────────────\n"
    "def _box_table(rows: list[tuple[str, str]]) -> str:\n"
    "    if not rows:\n"
    '        return ""\n'
    "    lw = max(len(r[0]) for r in rows)\n"
    "    rw = max(len(r[1]) for r in rows)\n"
    '    top    = "┌" + "─" * (lw + 2) + "┬" + "─" * (rw + 2) + "┐"\n'
    '    sep    = "├" + "─" * (lw + 2) + "┼" + "─" * (rw + 2) + "┤"\n'
    '    bot    = "└" + "─" * (lw + 2) + "┴" + "─" * (rw + 2) + "┘"\n'
    "    lines  = [top]\n"
    "    for i, (l, r) in enumerate(rows):\n"
    '        lines.append(f"│ {l:<{lw}} │ {r:>{rw}} │")\n'
    "        if i < len(rows) - 1:\n"
    "            lines.append(sep)\n"
    "    lines.append(bot)\n"
    '    return "\\n".join(lines)\n'
    "\n"
    "\n"
    "# ── 메인 렌더 (3섹터 마크다운 표, 약속 L16) ─────────────────────\n"
    "def build_board(gas_items: list[dict], queue_items: list[dict]) -> tuple[str, dict]:\n"
    '    """도드 텍스트 + 섹션 dict 반환.\n'
    "    3섹터: 🚢 진행중 / ⚓ 대기중 / 🏁 입항 완료 (오늘)\n"
    "    표 칼럼(5개): 배 | 담당 | 진행명 | 간단설명 | 본질에 대한 핵심조언\n"
    "    배 칸=난이도 배 아이콘만 · 상태는 섹터 제목에만 · 담당=닉코네임.\"\"\"\n"
    "    all_items = gas_items + queue_items\n"
    "    secs = _classify(all_items)\n"
    "\n"
    "    today  = dt.date.today().strftime(\"%Y-%m-%d\")\n"
    "    wd_kor = [\"월\", \"화\", \"수\", \"목\", \"금\", \"토\", \"일\"][dt.date.today().weekday()]\n"
    "\n"
    "    n_urgent   = len(secs[\"urgent\"])\n"
    "    n_appr     = len(secs[\"appr\"])\n"
    "    n_inflight = len(secs[\"appr_inflight\"])\n"
    "    n_done     = len(secs[\"done\"])\n"
    "    n_drift    = len(secs[\"drift\"])\n"
    "\n"
    "    inprog  = [it for it in secs[\"today\"] if it[\"status\"] in STATUS_INPROGRESS or it[\"status\"].upper() in STATUS_INPROGRESS]\n"
    "    waiting = [it for it in secs[\"today\"] if it not in inprog]\n"
    "    n_total = n_urgent + len(inprog) + len(waiting) + n_appr\n"
    "\n"
    "    _cnt_rows = [\n"
    "        (\"🚢 진행중\",              str(len(inprog))),\n"
    "        (\"⚓ 대기중\",               str(len(waiting))),\n"
    "        (\"🏁 입항 완료 (오늘)\", str(n_done + n_drift)),\n"
    "        (\"🔴 급한 입항 (마감임박)\", str(n_urgent)),\n"
    "        (\"🔴 GM 결재 대기\",        str(n_appr)),\n"
    "    ]\n"
    "    if n_inflight:\n"
    "        _cnt_rows.append((\"⏳ 결재 진행 중 (타 결재자)\", str(n_inflight)))\n"
    "    if n_drift:\n"
    "        _cnt_rows.append((\"🌀 표류 (다음 미정)\",          str(n_drift)))\n"
    "    _cnt_rows.append((\"진행 합계\",                    str(n_total)))\n"
    "    summary_table = _box_table(_cnt_rows)\n"
    "\n"
    "    lines: list[str] = []\n"
    "    lines.append(f\"🧭 오늘의 항로  {today} ({wd_kor})\")\n"
    "    lines.append(\"━\" * 36)\n"
    "    lines.append(summary_table)\n"
    "\n"
    "    # 항로 정합경고\n"
    "    try:\n"
    "        from queue_integrity_check import board_banner\n"
    "        _bn = board_banner(gas_items=gas_items)\n"
    "        if _bn:\n"
    "            lines.append(_bn)\n"
    "    except Exception:\n"
    "        pass\n"
    "\n"
    "    # ── 🔴 급한 입항 (별도 알림) ──\n"
    "    if secs[\"urgent\"]:\n"
    "        lines.append(\"\")\n"
    "        lines.append(\"🔴 급한 입항 (마감임박 ≤3일)\")\n"
    "        lines.append(_md_table([_item_to_row(it) for it in secs[\"urgent\"]]))\n"
    "\n"
    "    # ── 🚢 진행중 섹터 ──\n"
    "    lines.append(\"\")\n"
    "    lines.append(\"### 🚢 진행중\")\n"
    "    if inprog:\n"
    "        lines.append(_md_table([_item_to_row(it) for it in inprog]))\n"
    "    else:\n"
    "        lines.append(\"_(없음)_\\n\")\n"
    "\n"
    "    # ── ⚓ 대기중 섹터 ──\n"
    "    lines.append(\"### ⚓ 대기중\")\n"
    "    if waiting:\n"
    "        wait_rows = []\n"
    "        for it in waiting:\n"
    "            st  = str(it.get(\"status\", \"\"))\n"
    "            tag = \"보류\" if st in {\"보류\", \"ON_HOLD\"} else \"\"\n"
    "            wait_rows.append(_item_to_row(it, ship_col_extra=tag))\n"
    "        lines.append(_md_table(wait_rows))\n"
    "    else:\n"
    "        lines.append(\"_(없음)_\\n\")\n"
    "\n"
    "    # ── 🏁 입항 완료 (오늘) 섹터 ──\n"
    "    lines.append(\"### 🏁 입항 완료 (오늘)\")\n"
    "    done_all = secs[\"done\"] + secs[\"drift\"]\n"
    "    if done_all:\n"
    "        done_rows = []\n"
    "        for it in secs[\"done\"]:\n"
    "            has_next = bool(str(it.get(\"next\") or \"\").strip())\n"
    "            tag = \"🔗\" if has_next else \"\"\n"
    "            done_rows.append(_item_to_row(it, ship_col_extra=tag))\n"
    "        for it in secs[\"drift\"]:\n"
    "            # 표류: 🌀 기표, 핵심조언에 👉 촉구 반드시 포함 (약속 L16)\n"
    "            advice = str(it.get(\"핵심조언\") or \"\").strip()\n"
    "            advice_col = f\"{advice} — 👉 다음 뽐 할지 정하세요\" if advice else \"👉 다음 뽐 할지 정하세요\"\n"
    "            ship  = it[\"_ship\"]\n"
    "            icon  = ship[\"icon\"]\n"
    "            nick  = _nick(str(it.get(\"owner\", \"\")))\n"
    "            title = str(it.get(\"title\", \"\"))\n"
    "            badges = (\"🔴\" if ship.get(\"urgent\") else \"\") + (\"🌟\" if ship.get(\"northstar\") else \"\")\n"
    "            title_col = f\"{title}{badges}\".strip()\n"
    "            desc  = str(it.get(\"간단설명\") or \"\").strip()\n"
    "            done_rows.append((f\"{icon} 🌀\", nick, title_col, desc, advice_col))\n"
    "        lines.append(_md_table(done_rows))\n"
    "    else:\n"
    "        lines.append(\"_(없음)_\\n\")\n"
    "\n"
    "    # ── 결재 포인터 ──\n"
    "    if secs[\"appr\"]:\n"
    "        lines.append(\"\")\n"
    "        lines.append(f\"🔴 GM 결재 {n_appr}건 — 결재 현황 SSOT에서 확인·결재\")\n"
    "        lines.append(\"    https://wellperion-cao.github.io/wellperion-automation/coo/todo/%EA%B2%B0%EC%9E%AC%20%ED%98%84%ED%99%A9%20SSOT.html\")\n"
    "\n"
    "    if secs[\"appr_inflight\"]:\n"
    "        lines.append(\"\")\n"
    "        lines.append(f\"⏳ 결재 진행 중 {n_inflight}건 (타 결재자 대기) — 결재 현황 SSOT\")\n"
    "\n"
    "    lines.append(\"\")\n"
    "    lines.append(\"━\" * 36)\n"
    "    lines.append(\"_본 보드는 자동 생성입니다._\")\n"
    "\n"
    "    return \"\\n\".join(lines), secs\n"
)

new_content = content[:start_idx] + NEW_BLOCK + "\n" + content[end_idx_final:]
path.write_text(new_content, encoding="utf-8")
print("OK - written")

# Quick verify
check = path.read_text(encoding="utf-8")
ok = all([
    "def _nick" in check,
    "def _md_table" in check,
    "CLEVEL_NICK" in check,
    "입항 완료 (오늘)" in check,
    "### 🚢 진행중" in check,
    "### ⚓ 대기중" in check,
])
print(f"Verify: {'ALL OK' if ok else 'MISSING SOMETHING'}")
for s in ["def _nick", "def _md_table", "CLEVEL_NICK", "입항 완료 (오늘)", "### 🚢 진행중", "### ⚓ 대기중"]:
    print(f"  {s}: {s in check}")
