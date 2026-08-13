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


def ref_no(ref: str, day: str) -> str:
    """표의 # 칸. 오늘 지시는 번호만, 지난 날 지시는 날짜를 앞에 붙인다.

    ref 는 `GM-YYYYMMDD-NN` 꼴이다. 전엔 `ref[-2:]` 로 잘라 썼는데, 어제·그제 받은
    지시를 오늘 끝내면 오늘 것과 같은 번호가 두 번 나와 어느 쪽인지 알 수 없었다
    (2026-08-08 실측: 04·06·13·25 가 각각 두 줄). 세 자리 이상 번호도 잘려 나갔다.
    """
    m = re.match(r'GM-(\d{4})(\d{2})(\d{2})-(\d+)$', ref)
    if not m:
        return ref[-2:]
    ymd, no = f'{m.group(1)}-{m.group(2)}-{m.group(3)}', m.group(4)
    return no if ymd == day else f'{m.group(2)}/{m.group(3)} {no}'


def _dur(start: datetime.datetime, end: datetime.datetime) -> str:
    m = int((end - start).total_seconds() // 60)
    return f'{m}분' if m < 60 else f'{m // 60}시간{m % 60}분'


_REF_DAY_RE = re.compile(r'^GM-(\d{4})(\d{2})(\d{2})-')


def _ref_day(ref: str) -> str:
    """ref(GM-YYYYMMDD-NN)에 박힌 접수일. 없으면 빈 문자열."""
    m = _REF_DAY_RE.match(str(ref or ''))
    return f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else ''


def _read(day: str, role: str | None):
    """GM- ref 가 있는 줄은 **ref 에 박힌 날짜**로 그날에 속하는지 가른다(이벤트 자체의
    ts 가 아니다) — 접수는 어제, 완료는 오늘 넘겨서 찍히면(자정 넘긴 마무리) 예전엔 완료
    줄이 오늘 날짜로 필터링돼 어제 그룹에 안 들어갔다. 그러면 --carry 가 이미 오늘 아침
    닫힌 지시를 '아직'으로 오판했다(2026-08-13 실측 — GM-20260812-2024, 08:31 종결인데
    --carry 가 미완으로 냈다). ref 없는 일반 작업 기록(load_work)은 그대로 ts 로 가른다."""
    for line in LOG.open(encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        ref = str(d.get('ref') or '')
        if ref.startswith('GM-'):
            if _ref_day(ref) != day:
                continue
        elif not str(d.get('ts') or '').startswith(day):
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


def _role_commits(role: str, start: datetime.datetime, end: datetime.datetime) -> list[str]:
    """그 역할이 그 시간대(±10분)에 남긴 커밋 해시 — 커밋 메시지 관례 스코프 `(role)`로 판별
    (예: chore(cpo): ... / ...auto-log 입항완료 배 — <sha> (ceo)). 완료 기록의 detail 에
    해시를 안 적었어도(예: 큐를 mutate_queue 로 직접 닫아 완료 훅을 안 거친 경우) 실제
    커밋을 잡기 위한 보강 — GM 2026-08-10 "시포 쿵짝표에는 커밋푸시 이건 안해줬네".
    ponytail: 시간창 휴리스틱(±10분) — 같은 역할이 같은 창 안에서 다른 지시로도 커밋하면
    섞일 수 있다. 오탐이 늘면 커밋 메시지에 ref 를 박아 정확 매칭으로 승격."""
    try:
        since = (start - datetime.timedelta(minutes=10)).isoformat()
        until = (end + datetime.timedelta(minutes=10)).isoformat()
        r = subprocess.run(
            ['git', 'log', f'--since={since}', f'--until={until}',
             f'--grep=({role})', '--format=%H'],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10)
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def upload_state(detail: str, has_done: bool, role: str | None = None,
                  start: datetime.datetime | None = None,
                  end: datetime.datetime | None = None) -> str:
    """저장·업로드 칸. 커밋 해시가 있으면 원격 도달까지 확인한다.
    detail 에 해시가 없으면(완료 메모에 안 적었거나 완료 훅을 안 거친 경우) 같은
    시간대의 역할 스코프 커밋을 대신 찾는다(_role_commits)."""
    shas = [m.group(1) for m in SHA_RE.finditer(detail)
            if len(m.group(1)) >= 7 and not m.group(1).isdigit()]
    if not shas and has_done and role and start:
        shas = _role_commits(role, start, end or start)
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



# ══════════════════════════════════════════════════════════════════════════
# 놓친 지시 · 반복 지시 자동 적발 (GM 지시 2026-08-08 "절대 놓치지마")
#   왜: 접수는 훅이 자동으로 넣는데 완료 짝은 사람이 남긴다. 그래서 끝난 일도 계속
#   '진행중'으로 쌓이고, 그 더미 안에서 **진짜 안 한 것**이 안 보인다(실측 2026-08-08:
#   열린 41건 중 대부분이 이미 끝난 것이었다).
#   ★자동으로 '완료' 도장을 찍지는 않는다 — 안 한 일을 했다고 적는 것이 지금보다 나쁘다.
#   대신 셋으로 **가른다**: 방금 받음 / 했는데 안 닫음 / 진짜 놓침.
# ══════════════════════════════════════════════════════════════════════════
GRACE_MIN = 90          # 이 시간 안이면 아직 '방금 받음' — 재촉하지 않는다
_STOP = re.compile(r'[^0-9A-Za-z가-힣]+')


def _norm(t: str) -> set:
    """제목 비교용 낱말 집합 — 조사·기호 차이로 다른 지시처럼 보이는 것을 막는다."""
    return {w for w in _STOP.split(str(t or '')) if len(w) >= 2}


def classify_open(items: list, work: list, now: datetime.datetime) -> list:
    """열린(완료 짝 없는) 지시를 셋으로 가른다.

    - just    : 받은 지 GRACE_MIN 분 안 — 아직 재촉할 때가 아니다
    - unclosed: 접수 뒤 그 역할이 남긴 작업 기록이 있다 — 했는데 짝만 안 지은 것
    - missed  : 접수 뒤 아무 작업 기록도 없다 — **진짜 놓친 것**
    자기검사 = scripts/test_kungjjak_missed.py
    """
    out = []
    for it in items:
        if not it.get('open'):
            continue
        st = it.get('start')
        mins = None
        if st:
            try:
                h, m = st.split(':')
                started = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                mins = int((now - started).total_seconds() // 60)
            except Exception:
                mins = None
        if mins is not None and mins < GRACE_MIN:
            kind = 'just'
        elif any((w.get('time') or '') > (st or '') for w in work):
            kind = 'unclosed'      # 접수 뒤에 뭔가 한 흔적이 있다
        else:
            kind = 'missed'
        out.append(dict(it, kind=kind, waited=mins))
    return out


def find_repeats(items: list) -> list:
    """같은 말을 두 번 이상 하신 것 — GM 이 반복하셨다면 그건 내가 안 한 것이다.

    낱말이 절반 이상 겹치면 같은 지시로 본다(조사·표현 차이 흡수).
    """
    groups = []
    for it in items:
        w = _norm(it.get('got'))
        if len(w) < 2:
            continue
        for g in groups:
            # 겹친 낱말이 짧은 쪽의 절반 이상이면 같은 지시로 본다.
            # 고정값 2 를 쓰면 '쿵짝표 보여줘' 처럼 두 낱말짜리 지시가 영영 안 묶인다
            # (실측 2026-08-08: GM 이 세 번 물으셨는데 하나도 안 잡혔다).
            need = max(1, (min(len(w), len(g['words'])) + 1) // 2)
            if len(w & g['words']) >= need:
                g['items'].append(it)
                g['words'] |= w
                break
        else:
            groups.append({'words': w, 'items': [it]})
    return [{'count': len(g['items']),
             'got': g['items'][0].get('got'),
             'nos': [x.get('no') for x in g['items']]}
            for g in groups if len(g['items']) >= 2]


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
                'no': ref_no(ref, day),
                'got': str(ev[0].get('event') or '').strip(),
                'did': did,
                'start': st.strftime('%H:%M') if st else None,
                'end': en.strftime('%H:%M') if en else None,
                'minutes': mins,
                'upload': upload_state(did, bool(oks), role=role, start=st, end=en),
                'open': not oks,
            })
        work = load_work(day, role)
        _now = datetime.datetime.now()
        opened = classify_open(items, work, _now)
        repeats = find_repeats(items)
        if items or work:
            out['roles'][role] = {
                'nick': NICK[role], 'items': items, 'work': work,
                'count': len(items), 'done': done,
                'open': len(items) - done,
                'avg_minutes': (total // done) if done else None,
                'work_count': len(work),
                'missed': [x for x in opened if x['kind'] == 'missed'],
                'unclosed': [x for x in opened if x['kind'] == 'unclosed'],
                'just': [x for x in opened if x['kind'] == 'just'],
                'repeats': repeats,
            }
    p = ROOT / 'status' / 'kungjjak_today.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    roles = ', '.join(f'{v["nick"]} {v["done"]}/{v["count"]}' for v in out['roles'].values())
    print(f'발행 {p.name} — {day} · {roles or "기록 없음"}')
    return 0


def _render_table(by: dict, day: str) -> None:
    """표 한 장 + 요약 줄. `day` 는 # 칸 서식(ref_no)에만 쓴다 — 오늘 날짜를 넘기면
    지난 날짜 ref 는 자동으로 'MM/DD NN' 로 찍혀 오늘 것과 섞이지 않는다(--carry 가 그걸 쓴다)."""
    print('| # | 접수한 것 | 한 것 | 소요 | 저장·업로드 |')
    print('|---|---|---|---|---|')
    total = done = measured = 0
    for ref in sorted(by):
        ev = by[ref]
        warns = [e for e in ev if e.get('result') == 'warn']
        oks = [e for e in ev if e.get('result') == 'ok']
        start = warns[0] if warns else (oks[0] if oks else None)
        st = datetime.datetime.fromisoformat(start['ts']) if start else None
        en = datetime.datetime.fromisoformat(oks[-1]['ts']) if oks else None

        # 소급 기록은 소요를 계산하지 않는다 — 접수 ts 가 실제로 지시받은 시각이 아니라
        # 나중에 몰아 적은 시각이라 0분으로 찍히고, 그 0분이 '즉시 처리'로 읽힌다.
        # 판정은 **표식 '시각 추정' 하나만** 본다(2026-08-08 GM 확정).
        #   ▸처음엔 '소급'이라는 낱말도 같이 봤는데, 소급 기능 자체를 설명한 완료 기록
        #     ("…소급분 소요를 고쳤다")이 그 낱말 때문에 소급으로 오판됐다. 실시간 처리
        #     2건이 '소급'으로 찍혔다 — 자유 낱말 스캔은 본문을 자세히 쓸수록 오탐한다.
        #   ▸그래서 소급으로 남길 때는 detail 끝에 '· 시각 추정'을 붙이는 것을 표식으로 삼는다.
        backfilled = any('시각 추정' in str(e.get('detail') or '') for e in ev)

        dur = '**진행중**'
        if st and en:
            done += 1
            if backfilled:
                dur = '소급'
            else:
                dur = _dur(st, en)
                total += int((en - st).total_seconds() // 60)
                measured += 1

        got = str(ev[0].get('event') or '').strip()
        did = str(oks[-1].get('detail') or '').strip() if oks else '아직'
        item_role = str(ev[0].get('role') or '').strip().lower()
        up = upload_state(did, bool(oks), role=item_role, start=st, end=en)
        print(f'| {ref_no(ref, day)} | {got[:52]} | {did[:74]} | {dur} | {up} |')

    print()
    # 평균은 실제로 잰 건만으로 낸다 — 소급분을 섞으면 평균이 0분 쪽으로 끌려간다.
    miss = len(by) - done
    line = f'**{len(by)}건 접수 · {done}건 완료'
    if measured:
        line += f' · 평균 {total // measured}분(잰 것 {measured}건)'
    else:
        line += ' · 잰 것 없음(전부 소급)'
    line += '**'
    if miss:
        line += f' · **진행중 {miss}건**'
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--role', default=None, help='ceo·cto·cmo·cpo·coo·chro·cfo')
    ap.add_argument('--date', default=None, help='YYYY-MM-DD (기본 오늘)')
    ap.add_argument('--all-roles', action='store_true')
    ap.add_argument('--emit', action='store_true',
                    help='status/kungjjak_today.json 으로 발행 (자율현황 화면용)')
    ap.add_argument('--carry', action='store_true',
                    help='어제 못 끝낸 것(완료 짝 없는 지시)도 함께 낸다 — 부팅용. '
                         '기본 동작(옵션 없음)은 바꾸지 않는다.')
    a = ap.parse_args()

    if a.emit:
        return emit(a.date or datetime.date.today().isoformat())

    day = a.date or datetime.date.today().isoformat()
    role = None if a.all_roles else (a.role or 'ceo')
    who = '전 역할' if a.all_roles else NICK.get(role, role)

    if a.carry:
        yday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
        yby = load(yday, role)
        carried = {ref: ev for ref, ev in yby.items()
                   if not any(e.get('result') == 'ok' for e in ev)}
        if carried:
            print(f'## 🥁 쿵짝표 — {who} · 어제 못 끝낸 것 ({len(carried)}건)')
            print()
            # day(오늘)를 넘겨 ref_no 가 'MM/DD NN' 로 찍히게 한다 — 오늘 표와 섞이지 않게.
            _render_table(carried, day)
            print()

    by = load(day, role)
    print(f'## 🥁 쿵짝표 — {who} · {day}')
    print()
    if not by:
        print('오늘 받은 GM 지시가 없습니다.')
        return 0

    _render_table(by, day)
    return 0


if __name__ == '__main__':
    sys.exit(main())
