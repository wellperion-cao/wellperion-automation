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
_SHIP_IN_TEXT_RE = re.compile(r'배\s*(\d{2,6})')

NICK = {'ceo': '웰리', 'cto': '시토', 'cmo': '시모', 'cpo': '시포',
        'coo': '시우', 'chro': '시로', 'cfo': '시뽀', 'cbo': '시보'}

# 정본 5칸(wellperion-gm-report 스킬 §4-3) — 표 렌더는 _render_table 단 하나뿐이고
# 헤더는 여기서만 만든다. 칸 수·이름이 바뀌면 아래 _selfcheck()가 바로 깨진다
# (2026-08-13 build_task_rows/_render_task_table 이라는 별도 경로가 몰래 생겨 5칸이
# 6칸으로 벌어졌던 사고 재발 방지 · 배658).
TABLE_COLUMNS = ['#', '접수한 것', '한 것', '상태·소요', '저장·업로드']


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

    ref 안의 1000단위는 역할 구간(worklog._GM_REF_BLOCK — 시포=4000대)이라 all-roles 표에서
    역할끼리 번호가 겹치지 않게 하는 **내부 장치**다. 화면에까지 실어 나르면 4001·4014 처럼
    네 자리가 되어 읽는 데 방해만 된다(2026-08-15 GM 지적). 표에는 구간을 뺀 순번만 낸다.
    """
    m = re.match(r'GM-(\d{4})(\d{2})(\d{2})-(\d+)$', ref)
    if not m:
        return ref[-2:]
    ymd = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
    no = f'{int(m.group(4)) % 1000:02d}'
    return no if ymd == day else f'{m.group(2)}/{m.group(3)} {no}'


def ref_sort_key(ref: str):
    """표 정렬 키 — 번호 부분을 **숫자로** 비교한다. `sorted(by)` 가 ref 문자열을 그대로
    비교하면 "10" < "1001" < "11" 이 돼 표가 01·02…10·1001…1029·11·12 처럼 깨진다
    (2026-08-13 GM 지적). ymd 먼저, 그 다음 번호를 int 로 비교 — 접수일 순 안에서 번호순."""
    m = re.match(r'GM-(\d{4})(\d{2})(\d{2})-(\d+)$', ref)
    if not m:
        return ('9999-99-99', 0, ref)
    return (f'{m.group(1)}-{m.group(2)}-{m.group(3)}', int(m.group(4)), ref)


def _dur(start: datetime.datetime, end: datetime.datetime) -> str:
    m = int((end - start).total_seconds() // 60)
    return f'{m}분' if m < 60 else f'{m // 60}시간{m % 60}분'


_REF_DAY_RE = re.compile(r'^GM-(\d{4})(\d{2})(\d{2})-')


def _ref_day(ref: str) -> str:
    """ref(GM-YYYYMMDD-NN)에 박힌 접수일. 없으면 빈 문자열."""
    m = _REF_DAY_RE.match(str(ref or ''))
    return f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else ''


_NOT_GM_PREFIX = ('<', '[SYSTEM NOTIFICATION', '[형식 고정', 'C-Level 부팅', '너는 ', '당신은 ')


def _read(day: str, role: str | None):
    """GM- ref 가 있는 줄은 **ref 에 박힌 날짜**로 그날에 속하는지 가른다(이벤트 자체의
    ts 가 아니다) — 접수는 어제, 완료는 오늘 넘겨서 찍히면(자정 넘긴 마무리) 예전엔 완료
    줄이 오늘 날짜로 필터링돼 어제 그룹에 안 들어갔다. 그러면 --carry 가 이미 오늘 아침
    닫힌 지시를 '아직'으로 오판했다(2026-08-13 실측 — GM-20260812-2024, 08:31 종결인데
    --carry 가 미완으로 냈다). ref 없는 일반 작업 기록(load_work)은 그대로 ts 로 가른다.

    부팅 프롬프트·시스템 문구는 여기서 걸러내지 않는다 — ref(GM-*) 는 접수 줄과 완료
    줄이 따로 쌓이는데, 줄 단위로 거르면 접수 줄만 빠지고 완료 줄이 남아 그 ref 가 엉뚱한
    '한 것' 텍스트로 표에 살아남는다(2026-08-13 실측 — 부팅문 접수 줄을 걸렀더니 같은
    ref 의 완료 줄 "답변 종결…"이 '접수한 것' 자리에 뜨는 2차 오류가 났다). 그래서 거르기는
    **ref 를 통째로 묶은 뒤**(load) 판단한다 — 정본 관문은 worklog.py 의 접수 훅
    (UserPromptSubmit)이고, 여기는 그 훅 고치기 전에 이미 쌓인 과거 줄만 위한 방어선이다."""
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
        else:
            if not str(d.get('ts') or '').startswith(day):
                continue
            if str(d.get('event') or '').startswith(_NOT_GM_PREFIX):
                continue  # ref 없는 work 줄은 그 자리에서 걸러도 안전(그룹화 없음)
        if role and d.get('role') != role:
            continue
        yield d


_NOISE_TAIL_RE = re.compile(r'(줘봐|보여줘|열어줘)[?？]?$|(읽을만해|괜찮네|좋음)$')


def _is_noise_got(got: str) -> bool:
    """지시가 아닌 발화 — 승인 답변("응"·"A")·조회 요청("~줘봐")·감상("~읽을만해")·
    미완성 발화(쉼표로 끝남). GM 지적 2026-08-13 "쿵짝표가 저게 아닌데?" — 표엔
    실제 업무 지시만 남긴다(작업이 따라온 지적은 got 이 아니라 완료짝 유무로 걸러진다,
    여긴 순수 발화 형태만 본다)."""
    t = (got or '').strip()
    if not t:
        return True
    core = re.sub(r'^[\d.,\s]+(번)?', '', t).strip()
    if len(core) <= 4:
        return True
    if core.endswith(','):
        return True
    return bool(_NOISE_TAIL_RE.search(core))


def load(day: str, role: str | None, include_ai: bool = True):
    """GM 지시 짝(ref=GM-*)만 — 접수↔완료 대응이 있는 것. 부팅 프롬프트·시스템 문구·
    지시가 아닌 발화(승인 답변·조회 요청·감상)가 섞인 ref 는 통째로 뺀다
    (그룹 안 아무 줄이나 걸리면 전체 제외 — 2026-08-13 GM 지적).

    include_ai=False 면 area='AI지시'(현실 업무가 아닌 AI 내부 살림, 웰리가 판단해 붙인 값)로
    표시된 그룹도 뺀다 — GM업무 화면용(배684 · GM 지시 2026-08-18 "AI건 말고 현실업무 기준").
    자율현황(emit)은 전부를 보여주는 화면이라 기본값(True)을 그대로 쓴다."""
    by: dict[str, list] = {}
    for d in _read(day, role):
        if str(d.get('ref') or '').startswith('GM-'):
            by.setdefault(d['ref'], []).append(d)
    for ref, ev in list(by.items()):
        if any(str(e.get('event') or '').startswith(_NOT_GM_PREFIX) for e in ev):
            del by[ref]
            continue
        if _is_noise_got(ev[0].get('event')):
            del by[ref]
            continue
        if not include_ai and any(str(e.get('area') or '') == 'AI지시' for e in ev):
            del by[ref]
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


STOP_KEYWORDS = ('정지', '중단', '차단', '삭제', '끄기', '해제', '금지')
_STOCK_PHRASES = {
    '완료', '처리함', '됨', '처리 완료', '완료함', '진행함', '받음',
    '후속은 배가 추적한다', '후속 작업이 있으면 배(_queue)가 추적한다',
}
_PATH_RE = re.compile(r'[\w./ㄱ-힣-]+\.(?:py|json|jsonl|html|md|js|css|gs)\b')
_URL_RE = re.compile(r'https?://')
_NUM_UNIT_RE = re.compile(r'\d+\s*(?:건|%|분|개|명|일|원|줄|회|시간|시|명|행|가지)')


def evidence_state(got: str, did: str, up: str) -> str:
    """증거 칸 (GM 지시 2026-08-13 "쿵짝표로 다 끝난 줄 알았는데 계속 빈틈이 생기네").

    ①정지·중단·차단·삭제·끄기·해제·금지 류 지시 = "했다"가 완료 조건이 아니라
      "지금도 그런가"가 완료 조건이다. 완료 짝이 있어도 항상 재확인 필요로 찍는다
      (8/12 "업무SSOT 자동등록 정지"가 완료 짝만 찍히고 8/13 07:34 에 7건 재발한 실사고).
    ②그 외는 detail 에 실증거(커밋해시·파일경로·URL·실측숫자) 가 있는지로 가른다 —
      "완료"·"처리함" 류 상투어만 있으면 진짜 끝난 것과 구분이 안 된다."""
    if any(k in (got or '') for k in STOP_KEYWORDS):
        return '🔁재확인'
    t = (did or '').strip()
    # '⚠️' 로 시작하는 detail 은 스스로 "증거 없음"이라 밝힌 것이다(close_gm_refs 자동종결
    # 기본값, 2026-08-13). upload_state 가 근처 시간대 커밋을 주워 ✅로 보이게 하는 것보다
    # 이 자기표시가 우선이다 — 안 그러면 "증거 없음"이라 적어 놓고 증거있음으로 뜬다.
    if not t or t in _STOCK_PHRASES or t.startswith('⚠️'):
        return '⚠️없음'
    if up.startswith('✅') or up.startswith('⚠️ 저장만'):
        return '✅있음'
    if _PATH_RE.search(t) or _URL_RE.search(t) or _NUM_UNIT_RE.search(t):
        return '✅있음'
    return '⚠️없음'


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


def _tomorrow_block(day: str) -> dict:
    """🔜 내일 — 자율현황 쿵짝 블록에 붙는 내일 일정(GM 지시 2026-08-13 "자율현황 하루칸에도").
    새 수집 로직 없음(약속 L21) — gm_checkin._tomorrow_section 이 쓰는 같은 함수를 재사용.
    실패(일정을 못 읽음)와 0건을 구분한다(자가점검 「0 위장」 금지) — ok=False 면 화면은 못 읽음으로 적는다."""
    tomorrow = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    try:
        import gm_checkin
        items, ok = gm_checkin._load_schedule_items_ex()
    except Exception:
        return {'ok': False, 'items': [], 'more': 0}
    if not ok:
        return {'ok': False, 'items': [], 'more': 0}
    pairs = gm_checkin._filter_today_items(items, tomorrow)
    lines = [f"{(t + ' ') if t else ''}{title}" for t, title in pairs[:3]]
    return {'ok': True, 'items': lines, 'more': max(0, len(pairs) - 3)}


def emit(day: str) -> int:
    """전 역할 오늘치를 status/kungjjak_today.json 으로 발행 — 자율현황 화면이 이걸 읽는다.

    worklog.jsonl 전체는 1.6MB·5,600줄이라 브라우저가 통째로 읽으면 무겁다.
    오늘치만 잘라 작은 파일로 낸다(오늘 실측 574줄 → 훨씬 작다).
    """
    out = {'_doc': '쿵짝표 — 역할별 오늘 GM 지시 접수↔완료. 원천 = status/worklog.jsonl (여기는 잘라낸 화면용)',
           'date': day, 'roles': {}, 'tomorrow': _tomorrow_block(day)}
    for role in NICK:
        by = load(day, role)
        items = []
        for ref in by:
            ev = by[ref]
            warns = [e for e in ev if e.get('result') == 'warn']
            oks = [e for e in ev if e.get('result') == 'ok']
            start = warns[0] if warns else (oks[0] if oks else None)
            st = datetime.datetime.fromisoformat(start['ts']) if start else None
            en = datetime.datetime.fromisoformat(oks[-1]['ts']) if oks else None
            mins = int((en - st).total_seconds() // 60) if st and en else None
            did = str(oks[-1].get('detail') or '').strip() if oks else ''
            got = str(ev[0].get('event') or '').strip()
            up = upload_state(did, bool(oks), role=role, start=st, end=en)
            ev_state = evidence_state(got, did, up) if oks else None
            items.append({
                'ref': ref,
                'no': ref_no(ref, day),
                'got': got,
                'did': did,
                'start': st.strftime('%H:%M') if st else None,
                'end': en.strftime('%H:%M') if en else None,
                'minutes': mins,
                'upload': up,
                'open': not oks,
                'evidence': ev_state,
                'ev': ev_state or '—',       # _dedup_rows 가 보는 랭킹용 키
                'sortkey': ref_sort_key(ref),
            })
        # 접수 훅 2개가 같은 지시를 다르게 채번하는 문제(2026-08-13) — CLI 표와 같은 방식으로 합친다.
        items = _dedup_rows(items)
        items.sort(key=lambda x: x['sortkey'])
        for it in items:
            del it['ev'], it['sortkey']
        done = sum(1 for it in items if it['minutes'] is not None)
        total = sum(it['minutes'] for it in items if it['minutes'] is not None)
        # 30건 — 기본 12건이면 바쁜 날 아침 자체 작업이 창 밖으로 밀려 화면(GM업무·자율현황)에서
        # 사라진다(2026-08-15 실측 — 06:04 자율화 선언이 오후에 안 보임).
        work = load_work(day, role, limit=30)
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
                # 'stop_watch' 는 2026-08-13 제거 — 끝난 지시를 매일 다시 띄우던 목록이다
                # (사유는 아래 _render_table 호출부 주석). 화면(자율현황)은 `r.stop_watch || []`
                # 로 방어하고 있어 키가 없으면 섹션 자체를 안 그린다 — 화면 수정 불필요.
            }
    p = ROOT / 'status' / 'kungjjak_today.json'
    body = json.dumps(out, ensure_ascii=False, indent=2)
    roles = ', '.join(f'{v["nick"]} {v["done"]}/{v["count"]}' for v in out['roles'].values())

    # ★2026-08-16 시토(배652 · 웰리 실측) — 값이 그대로면 쓰지도 커밋하지도 않는다.
    #   왜 이게 필요한가: 이 발행본은 3분 슬롯에서 다시 만들어지는데, 내용이 같아도 매번
    #   덮어써서 파일 수정시각이 계속 새로 찍혔다. 그래서 저장소로 올려 주는 장치
    #   (post_commit_push._commit_stale_machine_outputs)가 "2시간 이상 묵은 산출물만
    #   올린다"는 조건에 **영원히 걸리지 않았다** — 3분마다 새 파일처럼 보이니 영영 안 묵는다.
    #   허용목록에는 진작 들어 있었는데도 한 번도 안 실린 이유가 이것이다.
    #   결과: GM업무 화면 「오늘 처리 기록」과 자율현황이 아침 값에 머물렀다.
    if p.exists() and p.read_text(encoding='utf-8') == body:
        print(f'발행 생략 {p.name} — 값 동일 · {day} · {roles or "기록 없음"}')
    else:
        p.write_text(body, encoding='utf-8')
        print(f'발행 {p.name} — {day} · {roles or "기록 없음"}')

    # 저장소에 아직 안 올라간 값이면 여기서 올린다(웰리 요청 3번 — 3분마다 커밋이 쌓이지 않게).
    # ★'쓸 게 없다'와 '올릴 게 없다'는 다르다 — 위에서 쓰기를 생략해도 그 값이 아직
    #   저장소에 없을 수 있다(앞선 실행이 쓰기만 하고 커밋을 못 한 경우). 그래서 커밋 여부는
    #   방금 썼는지가 아니라 **저장소와 다른지**로 판단한다. 이 대조는 락이 필요 없는 값싼
    #   호출이라, 값이 그대로인 대부분의 3분 주기에는 커밋 관문을 아예 부르지 않는다.
    # 새 스크립트·새 예약을 만들지 않고 이미 이 슬롯이 지나는 자리에서 기존 관문을 부른다(약속 L21).
    # 실패해도 발행은 성공으로 둔다 — 다음 주기에 다시 시도하고, 그래도 못 가면 이제는
    # 파일이 안 묵는 문제가 사라졌으므로 2시간 스위퍼가 받아 준다(이중 안전망).
    try:
        dirty = subprocess.run(
            ['git', '-C', str(ROOT), 'diff', '--name-only', 'HEAD', '--', str(p)],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        if (dirty.stdout or '').strip():
            sys.path.insert(0, str(ROOT / 'scripts'))
            from safe_commit import safe_commit
            # ★push=False 인 이유(실측 2026-08-16) — safe_commit 의 push 경로는 커밋 뒤에
            #   ad-hoc 자동기록(auto_log)을 부르고, 그게 worklog 에 한 줄을 쌓는다. 이 발행본의
            #   원천이 바로 worklog 라, 커밋할 때마다 내용이 다시 바뀌어 3분마다 영원히 커밋이
            #   찍히는 되먹임이 된다(실측: 연속 3회 모두 새 커밋). 그래서 auto_log 는 부르지 않는다.
            r = safe_commit([str(p)], f'chore(auto): 쿵짝 발행본 갱신 — {day}',
                            holder='kungjjak-emit', push=False)
            if not r.get('ok'):
                print(f'[WARN] 쿵짝 발행본 커밋 건너뜀: {r.get("reason", "")[:120]}')
            else:
                # ★2026-09-01 시토(배757) — 올리기까지 여기서 한다. 예전엔 5분 스위퍼에
                #   맡겼는데(위 되먹임 회피의 부수효과), PC 종료가 커밋과 다음 스위퍼 사이에
                #   끼면 커밋이 밤새 로컬에 갇힌다(실측: 08-31 밤 95c8d686b 00:28 커밋 →
                #   마지막 스위퍼 push 00:26 → 00:31 스위퍼 전에 PC 종료 → 아침 05:58 까지
                #   원격 미반영). post_commit_push.py 직접 호출은 auto_log 를 부르지 않으므로
                #   위 되먹임과 무관하다 — 기존 관문 재사용(약속 L21), 실패=fail-open(스위퍼가 백스톱).
                try:
                    subprocess.run(
                        [sys.executable, str(ROOT / 'scripts' / 'post_commit_push.py')],
                        cwd=str(ROOT), capture_output=True, text=True,
                        encoding='utf-8', errors='replace', timeout=120)
                except Exception as push_exc:
                    print(f'[WARN] 쿵짝 발행본 push 건너뜀(스위퍼가 올림): {type(push_exc).__name__}: {push_exc}')
    except Exception as exc:
        print(f'[WARN] 쿵짝 발행본 커밋 건너뜀: {type(exc).__name__}: {exc}')
    return 0


def _row_ship_no(r: dict) -> str | None:
    """행이 가리키는 배 번호('한 것' 칸에서 뽑는다) — 훅 접수(GM 원문 그대로)와 세션 재접수
    (요약문)는 '접수한 것' 문구가 서로 달라 낱말겹침으로 안 잡히는 경우가 많다(배684 실측 —
    47건 중 절반 가까이가 이런 미스). 그래도 '한 것'에 같은 배 번호가 적혀 있으면 같은 지시다."""
    m = _SHIP_IN_TEXT_RE.search(r.get('did') or '')
    return m.group(1) if m else None


def _dedup_rows(rows: list[dict]) -> list[dict]:
    """같은 지시가 접수 훅 2개(자동 UserPromptSubmit + 손으로 또 한 번) 때문에 ref 가
    다른 두 줄로 잡히는 것을 하나로 합친다(2026-08-13 GM 지적 — 04↔1001·05↔1002…
    47건 중 절반 가까이가 이 중복이었다). 우선 같은 배 번호(_row_ship_no)를 가리키면
    문구가 달라도 같은 지시로 묶고, 배 번호가 없으면 find_repeats() 와 같은 낱말-겹침
    판정으로 묶는다. **증거가 있는 쪽 행을 통째로 살린다**(부분 병합이 아니라 행 전체
    교체 — 필드가 서로 안 맞는 프랑켄슈타인 행을 막는다). 둘 다 증거가 같으면 번호가
    앞선(sortkey 가 작은) 쪽을 남긴다."""
    rank = {'✅있음': 0, '🔁재확인': 0, '⚠️없음': 1, '—': 2}
    groups: list[list[dict]] = []
    for r in rows:
        ship = _row_ship_no(r)
        w = _norm(r['got'])
        for g in groups:
            if ship and ship == _row_ship_no(g[0]):
                g.append(r)
                break
            gw = _norm(g[0]['got'])
            if w and gw:
                need = max(1, (min(len(w), len(gw)) + 1) // 2)
                if len(w & gw) >= need:
                    g.append(r)
                    break
        else:
            groups.append([r])
    return [min(g, key=lambda r: (rank.get(r['ev'], 1), r['sortkey'])) for g in groups]


def _render_table(by: dict, day: str) -> None:
    """표 한 장 + 요약 줄. `day` 는 # 칸 서식(ref_no)에만 쓴다 — 오늘 날짜를 넘기면
    지난 날짜 ref 는 자동으로 'MM/DD NN' 로 찍혀 오늘 것과 섞이지 않는다(--carry 가 그걸 쓴다)."""
    rows = []
    for ref in by:
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

        got = str(ev[0].get('event') or '').strip()
        did = str(oks[-1].get('detail') or '').strip() if oks else '아직'
        # 자동종결(close_gm_refs)이 근처 커밋을 못 찾으면 "⚠️ 자동종결 — …별도 완료 기록
        # 없음" 을 그대로 detail 에 남긴다 — 우리 사정을 설명하는 내부 문구지 GM 이 읽을
        # 말이 아니다(배684 · GM 지시 2026-08-18). '⚠️' 로 시작하는 detail 은 스스로 증거
        # 없다고 밝힌 것이니(evidence_state 와 같은 판정 기준) 완료로 세지 않고 진행중으로
        # 되돌린다 — GM 화면·자율현황 모두 여기 한 곳만 고치면 같이 정직해진다.
        auto_closed = did.startswith('⚠️')
        if auto_closed:
            did = '아직'

        # 상태 아이콘을 소요 앞에 붙인다(GM 지시 2026-08-13 — "진행 중인지 완료된 건지도
        # 파악하면 좋겠다"). 칸을 6개로 늘리지 않는다: 늘리면 '접수한 것'·'한 것' 칸이 좁아져
        # 본문이 더 잘리고, 오늘 되돌린 정본 5칸이 또 흔들린다. 소요 칸은 이미 상태를 겸하고
        # 있었으나(시간=완료 / 진행중=미완) 완료 쪽이 암묵이라 GM 이 규칙을 외워야 읽혔다.
        # 아이콘은 항해 표준 그대로 — 🏁 입항(완료) / 🚢 항해 중(진행).
        dur, minutes = '🚢 **진행중**', None
        has_dur = bool(st and en) and not auto_closed
        if has_dur:
            if backfilled:
                dur = '🏁 소급'
            else:
                dur = f'🏁 {_dur(st, en)}'
                minutes = int((en - st).total_seconds() // 60)

        item_role = str(ev[0].get('role') or '').strip().lower()
        up = upload_state(did, bool(oks), role=item_role, start=st, end=en)
        ev_state = evidence_state(got, did, up) if oks else '—'
        # # 칸에 배 번호를 같이 보여준다(GM 지시 2026-08-13 — "식별번호" 요구). did 에서
        # "배NNN" 을 찾아 붙인다. 못 찾으면 접수번호만(빈칸으로 안 둔다).
        # 닉네임은 뺀다(2026-08-15 GM 지적 — 칸이 길다). --role 표는 전부 같은 역할이라
        # 잉여였고, --all-roles 에서도 배 번호가 역할별로 달라 구분이 된다.
        no = ref_no(ref, day)
        m = _SHIP_IN_TEXT_RE.search(did)
        if m:
            no = f'{no}·배{m.group(1)}'
        rows.append({'ref': ref, 'no': no, 'got': got, 'did': did,
                      'dur': dur, 'up': up, 'ev': ev_state, 'sortkey': ref_sort_key(ref),
                      'has_dur': has_dur, 'minutes': minutes})

    n_before = len(rows)
    rows = _dedup_rows(rows)
    rows.sort(key=lambda r: r['sortkey'])

    # 증거 칸은 정본(wellperion-gm-report 스킬 §4-3, 5칸)에 없다 — 판정 로직(evidence_state)은
    # 살리되 별도 칸으로 안 낸다. '한 것'이 상투어면 그 문장 자체가 이미 증거 없음을 드러낸다
    # (GM 지적 2026-08-13 "형식 자체가 없어지고 다시 만드는거야?" — 6칸으로 늘렸던 걸 되돌림).
    print('| ' + ' | '.join(TABLE_COLUMNS) + ' |')
    print('|' + '---|' * len(TABLE_COLUMNS))
    for r in rows:
        print(f"| {r['no']} | {r['got'][:52]} | {r['did'][:74]} | {r['dur']} | {r['up']} |")

    print()
    done = sum(1 for r in rows if r['has_dur'])
    measured_rows = [r for r in rows if r['minutes'] is not None]
    # 평균은 실제로 잰 건만으로 낸다 — 소급분을 섞으면 평균이 0분 쪽으로 끌려간다.
    miss = len(rows) - done
    dup = n_before - len(rows)
    line = f'**{len(rows)}건 접수 · {done}건 완료'
    if measured_rows:
        line += f' · 평균 {sum(r["minutes"] for r in measured_rows) // len(measured_rows)}분(잰 것 {len(measured_rows)}건)'
    else:
        line += ' · 잰 것 없음(전부 소급)'
    line += '**'
    if miss:
        line += f' · **진행중 {miss}건**'
    if dup:
        line += f' · 중복 {dup}건 합침'
    print(line)
    _print_gm_catch_count()


def _print_gm_catch_count(role: str = 'ceo') -> None:
    """★약속 L25 계기판 — 「GM 이 먼저 잡아 준 것」이 오늘 몇 건인지 한 줄로 낸다.

    2026-08-19 GM 발효. 그날 기준선은 11건이었다(GM: "내가 다 일일이 체크해서 이야기하는 것도
    너무 반복되는 것 같네"). 숫자가 안 줄면 L25 가 안 먹은 것이다 — 그때는 규칙을 늘리지 말고
    왜 안 먹었는지를 본다.

    새 원장을 만들지 않는다(약속 L21) — 이미 전 역할이 쓰는 status/worklog.jsonl 에서
    area='GM지적' 줄만 세어 온다. 기록이 없으면 0건으로 조용히 지나간다(경고 아님).
    """
    import json as _json
    import os as _os
    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                         'status', 'worklog.jsonl')
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    n = 0
    try:
        with open(path, encoding='utf-8') as f:
            for ln in f:
                ln = ln.strip()
                if not ln or 'GM지적' not in ln:
                    continue
                try:
                    d = _json.loads(ln)
                except Exception:
                    continue
                if d.get('area') == 'GM지적' and str(d.get('ts', '')).startswith(today) \
                        and (not role or d.get('role') == role):
                    n += 1
    except FileNotFoundError:
        return
    if n == 0:
        print('🎯 GM 이 먼저 잡아 준 것 — **오늘 0건** (기준선 2026-08-19 11건 · 약속 L25)')
    else:
        print(f'🎯 GM 이 먼저 잡아 준 것 — **오늘 {n}건** (기준선 2026-08-19 11건 · 약속 L25). '
              '줄지 않으면 규칙을 늘리지 말고 왜 안 먹었는지를 본다.')


def _selfcheck() -> None:
    """최소 회귀 검사 — 정본 5칸(TABLE_COLUMNS)이 흔들리면 여기서 바로 깨진다.
    역할이 달라도(cto·cpo…) _render_table 은 role 인자를 안 받는 단일 경로라
    두 역할의 합성 데이터를 같은 함수에 넣어 헤더가 갈리지 않는지 함께 본다
    (2026-08-10 '시토·시포 표가 서로 달랐다' 재발 방지 · 배658)."""
    import contextlib
    import io

    now = datetime.datetime(2026, 8, 16, 10, 0, 0)
    for role in ('cto', 'cpo'):
        by = {
            f'GM-{role}-01': [
                {'ts': now.isoformat(), 'result': 'warn', 'event': f'{role} 접수', 'role': role},
                {'ts': (now + datetime.timedelta(minutes=5)).isoformat(), 'result': 'ok',
                 'detail': f'{role} 완료 배1', 'role': role},
            ],
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _render_table(by, '2026-08-16')
        out = buf.getvalue()
        lines = [ln for ln in out.splitlines() if ln.startswith('|')]
        assert len(lines) >= 2, f'{role}: 표 본문이 안 찍혔다'
        header_cells = [c.strip() for c in lines[0].strip('|').split('|')]
        assert header_cells == TABLE_COLUMNS, (
            f'{role}: 헤더 {header_cells} != 정본 {TABLE_COLUMNS} — 칸 수·이름 드리프트')
        row_cells = lines[2].strip('|').split('|') if len(lines) > 2 else lines[1].strip('|').split('|')
        assert len(row_cells) == len(TABLE_COLUMNS), (
            f'{role}: 데이터 행 칸수 {len(row_cells)} != {len(TABLE_COLUMNS)}')
    print(f'[OK] kungjjak_board 자가검사 통과 — {len(TABLE_COLUMNS)}칸 정본 유지, 역할 무관 동일 헤더')


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
    ap.add_argument('--selfcheck', action='store_true',
                    help='정본 5칸 회귀 검사만 돌리고 끝(배658)')
    a = ap.parse_args()

    if a.selfcheck:
        _selfcheck()
        return 0

    if a.emit:
        return emit(a.date or datetime.date.today().isoformat())

    day = a.date or datetime.date.today().isoformat()
    role = None if a.all_roles else (a.role or 'ceo')
    who = '전 역할' if a.all_roles else NICK.get(role, role)

    if a.carry:
        yday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
        yby = load(yday, role, include_ai=False)
        carried = {ref: ev for ref, ev in yby.items()
                   if not any(e.get('result') == 'ok' for e in ev)}
        if carried:
            print(f'## 🥁 쿵짝표 — {who} · 어제 못 끝낸 것 ({len(carried)}건)')
            print()
            # day(오늘)를 넘겨 ref_no 가 'MM/DD NN' 로 찍히게 한다 — 오늘 표와 섞이지 않게.
            _render_table(carried, day)
            print()

    by = load(day, role, include_ai=False)
    print(f'## 🥁 쿵짝표 — {who} · {day}')
    print()
    if not by:
        print('오늘 받은 GM 지시가 없습니다.')
        return 0

    _render_table(by, day)
    # 「🔁 재확인 필요 — 정지·차단류」 섹션은 2026-08-13 같은 날 만들고 같은 날 없앴다.
    # 의도: 정지 지시는 나중에 조용히 되살아나니 완료 짝이 있어도 매일 다시 본다
    #       (실사고 — SSOT 자동등록 정지가 21시간 방치돼 7건 재발).
    # 결과: 그 목록에 뜬 13건이 **전부 이미 끝난 것**이었고, GM 이 "지시한 것들 다
    #       마무리된 것들 아냐?"라고 물으셨다. 판단거리를 만들지 못하고 잡음만 늘렸다.
    # 원인 둘: ①끝난 것을 매일 다시 띄우는 설계 자체가 틀렸다 ②낱말 스캔이라
    #       완료 보고문에 '삭제'가 들어간 것까지 걸렸다(자가점검 표가 이미 경고한 함정).
    # 재발 방지는 목록이 아니라 **코드**로 한다 — 정지시킨 것은 킬스위치 값과 실행
    # 결과로 확인하고(오늘 SSOT 에 한 이중 잠금이 그것), 화면에 매일 띄우지 않는다.
    return 0


if __name__ == '__main__':
    sys.exit(main())
