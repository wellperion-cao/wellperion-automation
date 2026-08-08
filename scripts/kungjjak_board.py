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


def _read(day: str, role: str | None):
    for line in LOG.open(encoding='utf-8'):
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
        yield d


def load(day: str, role: str | None):
    """GM 지시 짝(ref=GM-*)만 — 접수↔완료 대응이 있는 것."""
    by: dict[str, list] = {}
    for d in _read(day, role):
        if str(d.get('ref') or '').startswith('GM-'):
            by.setdefault(d['ref'], []).append(d)
    return by


def load_work(day: str, role: str | None, limit: int = 12):
    """오늘 한 일 — GM 지시가 아닌 자체 작업. 웰리·시토 말고는 GM 지시를 직접 안 받으므로
    이 목록이 그 역할의 하루가 된다(빈 표를 내지 않기 위함)."""
    out = []
    for d in _read(day, role):
        if str(d.get('ref') or '').startswith('GM-'):
            continue
        if d.get('result') != 'ok':
            continue
        ev = str(d.get('event') or '').strip()
        if not ev:
            continue
        out.append({
            'time': str(d.get('ts'))[11:16],
            'area': str(d.get('area') or '').strip(),
            'event': ev,
            'detail': str(d.get('detail') or '').strip(),
        })
    # 같은 제목이 반복되면 마지막 것만(자동 갱신 로그가 여러 번 쌓인다)
    seen, dedup = set(), []
    for w in reversed(out):
        if w['event'] in seen:
            continue
        seen.add(w['event'])
        dedup.append(w)
    dedup.reverse()
    return dedup[-limit:]


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


def emit(day: str) -> int:
    """전 역할 오늘치를 status/kungjjak_today.json 으로 발행 — 자율현황 화면이 이걸 읽는다.

    worklog.jsonl 전체는 1.6MB·5,600줄이라 브라우저가 통째로 읽으면 무겁다.
    오늘치만 잘라 작은 파일로 낸다(오늘 실측 574줄 → 훨씬 작다).
    """
    out = {'_doc': '쿵짝표 — 역할별 오늘 GM 지시 접수↔완료. 원천 = status/worklog.jsonl (여기는 잘라낸 화면용)',
           'date': day, 'roles': {}}
    for role in NICK:
        by = load(day, role)
        items = []
        done = total = 0
        for ref in sorted(by):
            ev = by[ref]
            warns = [e for e in ev if e.get('result') == 'warn']
            oks = [e for e in ev if e.get('result') == 'ok']
            start = warns[0] if warns else (oks[0] if oks else None)
            st = datetime.datetime.fromisoformat(start['ts']) if start else None
            en = datetime.datetime.fromisoformat(oks[-1]['ts']) if oks else None
            mins = None
            if st and en:
                mins = int((en - st).total_seconds() // 60)
                total += mins
                done += 1
            did = str(oks[-1].get('detail') or '').strip() if oks else ''
            items.append({
                'ref': ref,
                'no': ref[-2:],
                'got': str(ev[0].get('event') or '').strip(),
                'did': did,
                'start': st.strftime('%H:%M') if st else None,
                'end': en.strftime('%H:%M') if en else None,
                'minutes': mins,
                'upload': upload_state(did, bool(oks)),
                'open': not oks,
            })
        work = load_work(day, role)
        if items or work:
            out['roles'][role] = {
                'nick': NICK[role], 'items': items, 'work': work,
                'count': len(items), 'done': done,
                'open': len(items) - done,
                'avg_minutes': (total // done) if done else None,
                'work_count': len(work),
            }
    p = ROOT / 'status' / 'kungjjak_today.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    roles = ', '.join(f'{v["nick"]} {v["done"]}/{v["count"]}' for v in out['roles'].values())
    print(f'발행 {p.name} — {day} · {roles or "기록 없음"}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--role', default=None, help='ceo·cto·cmo·cpo·coo·chro·cfo')
    ap.add_argument('--date', default=None, help='YYYY-MM-DD (기본 오늘)')
    ap.add_argument('--all-roles', action='store_true')
    ap.add_argument('--emit', action='store_true',
                    help='status/kungjjak_today.json 으로 발행 (자율현황 화면용)')
    a = ap.parse_args()

    if a.emit:
        return emit(a.date or datetime.date.today().isoformat())

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
