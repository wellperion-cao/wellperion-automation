# -*- coding: utf-8 -*-
"""쿵짝표 — 하루치 GM 지시 접수↔완료 짝을 표 하나로 (7역할 공통 · GM 지시 2026-08-08).

왜 있나
  8요소 표(wellperion-gm-report 스킬 §4-1)는 **건별** 보고다. 그것만으로는
  "오늘 받은 것 중 무엇이 아직 안 끝났나"가 안 보인다. 이 표는 **하루 전체**를
  한 장으로 보여 준다 — 접수한 것 / 한 것 / 걸린 시간 / 저장·업로드 여부.

무엇을 읽나
  status/worklog.jsonl 하나뿐이다(새 원장을 만들지 않는다 · 약속 L21).
  같은 ref 에 result=warn(접수)과 result=ok(완료)가 짝으로 쌓이는 구조를 그대로 쓴다.
  ok 가 없으면 진행중으로 나온다 — 그것이 곧 놓친 것 목록이다.

쓰는 법
  C:/Python314/python.exe scripts/kungjjak_board.py                 # 오늘·내 역할
  C:/Python314/python.exe scripts/kungjjak_board.py --role cto
  C:/Python314/python.exe scripts/kungjjak_board.py --date 2026-08-07
  C:/Python314/python.exe scripts/kungjjak_board.py --all-roles
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / 'status' / 'worklog.jsonl'
SHA_RE = re.compile(r'\b([0-9a-f]{7,40})\b')

NICK = {'ceo': '웰리', 'cto': '시토', 'cmo': '시모', 'cpo': '시포',
        'coo': '시우', 'chro': '시로', 'cfo': '시뽀'}


def _pushed(sha: str) -> bool:
    """그 커밋이 원격(origin/master)까지 올라갔는지 — 저장만 하고 안 올리면 GM 화면은 옛것이다."""
    try:
        r = subprocess.run(['git', 'merge-base', '--is-ancestor', sha, 'origin/master'],
                           cwd=str(ROOT), capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _dur(start: datetime.datetime, end: datetime.datetime) -> str:
    m = int((end - start).total_seconds() // 60)
    return f'{m}분' if m < 60 else f'{m // 60}시간{m % 60}분'


def load(day: str, role: str | None):
    rows = []
    with LOG.open(encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not str(d.get('ts') or '').startswith(day):
                continue
            if role and d.get('role') != role:
                continue
            if not str(d.get('ref') or '').startswith('GM-'):
                continue
            rows.append(d)
    by: dict[str, list] = {}
    for d in rows:
        by.setdefault(d['ref'], []).append(d)
    return by


def upload_state(detail: str, has_done: bool) -> str:
    """저장·업로드 칸. 커밋 해시가 있으면 원격 도달까지 확인한다."""
    shas = [m.group(1) for m in SHA_RE.finditer(detail)
            if len(m.group(1)) >= 7 and not m.group(1).isdigit()]
    for s in shas:
        if _pushed(s):
            return f'✅ 올림 ({s[:9]})'
    if shas:
        return f'⚠️ 저장만 ({shas[0][:9]})'
    if not has_done:
        return '—'
    if any(k in detail for k in ('발송', '게시', '전달', '공유')):
        return '발송 (저장 대상 아님)'
    return '기록만'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--role', default=None, help='ceo·cto·cmo·cpo·coo·chro·cfo')
    ap.add_argument('--date', default=None, help='YYYY-MM-DD (기본 오늘)')
    ap.add_argument('--all-roles', action='store_true')
    a = ap.parse_args()

    day = a.date or datetime.date.today().isoformat()
    role = None if a.all_roles else (a.role or 'ceo')
    by = load(day, role)

    who = '전 역할' if a.all_roles else NICK.get(role, role)
    print(f'## 🥁 쿵짝표 — {who} · {day}')
    print()
    if not by:
        print('오늘 받은 GM 지시가 없습니다.')
        return 0

    print('| # | 접수한 것 | 한 것 | 소요 | 저장·업로드 |')
    print('|---|---|---|---|---|')
    total = done = 0
    for ref in sorted(by):
        ev = by[ref]
        warns = [e for e in ev if e.get('result') == 'warn']
        oks = [e for e in ev if e.get('result') == 'ok']
        start = warns[0] if warns else (oks[0] if oks else None)
        st = datetime.datetime.fromisoformat(start['ts']) if start else None
        en = datetime.datetime.fromisoformat(oks[-1]['ts']) if oks else None

        dur = '**진행중**'
        if st and en:
            dur = _dur(st, en)
            total += int((en - st).total_seconds() // 60)
            done += 1

        got = str(ev[0].get('event') or '').strip()
        did = str(oks[-1].get('detail') or '').strip() if oks else '아직'
        up = upload_state(did, bool(oks))
        print(f'| {ref[-2:]} | {got[:52]} | {did[:74]} | {dur} | {up} |')

    print()
    avg = (total // done) if done else 0
    miss = len(by) - done
    line = f'**{len(by)}건 접수 · {done}건 완료 · 평균 {avg}분**'
    if miss:
        line += f' · **진행중 {miss}건**'
    print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
