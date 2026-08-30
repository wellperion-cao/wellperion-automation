# -*- coding: utf-8 -*-
"""GM 개인 하루 체크인 — 텔레그램 버튼 한 번으로 적는다 (GM 승인 2026-08-08 · A안).

왜 있나
  G1 개인 영역의 「오늘 체크인」은 칸이 11개라 매일 페이지를 열어야 했고, 이틀 만에 끊겼다
  (기록 2026-05-26·05-27 두 날 뒤 73일 공백). 「GM의 일요일」이 계속 도는 이유는
  사람이 하는 게 사진 한 장뿐이기 때문이다. 같은 구조를 여기 옮긴다 —
  저녁에 봇이 묻고, GM 은 버튼만 누른다. 글자 입력 0.

무엇을 쓰나
  status/gm_personal_routine.json 하나뿐이다(새 저장소 신설 없음 · 약속 L21).
  G1 페이지가 이미 읽고 쓰는 그 파일에 같은 모양으로 하루 한 칸을 채운다.

누가 부르나
  · 발신 = telegram_bot/daily_scheduler.py 21:30 잡 (build_prompt / build_markup)
  · 수신 = telegram_bot/bot.py 의 ck: 콜백 (toggle / set_mood / save)
  둘 다 여기 함수를 부른다 — 판정·저장 로직을 두 벌로 만들지 않는다.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
JPATH = ROOT / 'status' / 'gm_personal_routine.json'

# ── 하루방 새 체계 v2 (GM 지시 2026-08-29 · 세부 5건 웰리 결정) — 2026-09-01(월)부터 ──
# 하루 9건 고정 + 미팅 + 일요일 주간 1건. 이날 전까지는 기존 체계 그대로(오늘·내일 무변).
HARU_V2_START = datetime.date(2026, 9, 1)


def haru_v2(day: str | None = None) -> bool:
    d = datetime.date.fromisoformat(day) if day else datetime.date.today()
    return d >= HARU_V2_START

# ── 오늘 일정 (배514, GM 지시 2026-08-10 "나의하루에 오늘 일정이 있으면 항상 정리해서 보고") ──
#   출처 후보 2곳 실측: G1 개인 캘린더(wellperion_guide(main).html #gm1-cal-wrap)는
#   localStorage 전용 — 브라우저 밖(이 서버 스크립트)에서 못 읽는다. 전사일정(schedule_ssot)은
#   GAS 가 정본·저장소 JSON은 seed 폴백(전사_일정.html 과 동일 이중화) — 이것만 쓴다. 새 저장소
#   신설 없음(약속 L21). GM 개인 일정은 그 안에서 담당자(assignee)에 "GM"·"김남욱"이 걸린 오늘자
#   항목만 골라낸다.
from collectors.ops_shared import SCHEDULE_GAS_URL  # 전사일정 GAS 단일 출처(약속 L01)
SCHEDULE_LOCAL = ROOT / 'status' / 'schedule_ssot.json'


# 마지막으로 일정을 어디서 읽었는지 — 'gas'(정본) / 'local'(옛 사본) / ''(못 읽음).
# 왜 남기나: 정본이 안 열려 옛 사본으로 내려앉아도 성공처럼 보이는 자리였다. 2026-08-12
# 실측 — 06:05 엔 정본 51건(오늘 2건)이었는데 07:5x 엔 정본이 JSON 을 안 줘 옛 사본 37건으로
# 떨어졌고, 브리핑이 "오늘 잡힌 일정은 없습니다"를 냈다. 0 건과 못 읽음은 구분했지만
# '옛 값으로 읽음'은 구분이 없어 조용히 통과했다(자가점검 7번 「0 위장」의 사촌).
_SCHEDULE_SOURCE = ''


def _load_schedule_items_ex() -> tuple[list, bool]:
    """일정 항목 + 성공여부. 실패(양쪽 다 못 읽음)와 0건을 구분한다(자가점검 7번 「0 위장」 금지).
    어느 쪽에서 읽었는지는 모듈 변수 _SCHEDULE_SOURCE 로 남긴다 — 호출부 수정 없이
    화면에 '옛 사본'임을 표기하기 위해서다."""
    global _SCHEDULE_SOURCE
    try:
        r = requests.get(SCHEDULE_GAS_URL, params={'action': 'load_schedule'}, timeout=8)
        j = r.json()
        if j.get('ok'):
            _SCHEDULE_SOURCE = 'gas'
            return (j.get('data') or {}).get('items') or [], True
    except Exception:
        pass
    try:
        items = json.loads(SCHEDULE_LOCAL.read_text(encoding='utf-8')).get('items') or []
        _SCHEDULE_SOURCE = 'local'
        return items, True
    except Exception:
        _SCHEDULE_SOURCE = ''
        return [], False


def _schedule_stale_note() -> str:
    """정본 대신 옛 사본을 읽었을 때만 붙는 한 줄. 정상이면 빈 문자열."""
    return '— 전사일정 정본이 안 열려 옛 사본을 봤습니다(오늘 것이 빠져 있을 수 있습니다)' \
        if _SCHEDULE_SOURCE == 'local' else ''


def _load_schedule_items() -> list:
    return _load_schedule_items_ex()[0]


_NOTE_TIME_RE = re.compile(r'^\s*(\d{1,2}:\d{2})\s*·')


def _extract_time(name: str, note: str, time_cell: str = '') -> str:
    """일정 시각 — 제목 속 (HH:MM) 우선, 없으면 note 앞머리 'HH:MM · ...'(전사일정은 날짜 단위라
    시각을 note 에 적는 관례, 2026-08-11 팀장 지적), 그래도 없으면 전사일정의 시각 칸.
    셋 다 없으면 빈 문자열(지어내지 않음).

    ★시각 칸을 읽게 된 경위(2026-08-25 · GM 지시 "다음부터 놓치지 않게 챙겨줘"):
      전사일정 화면에는 시각 칸이 따로 있고 GM 도 거기에 시각을 적어 오셨는데, 이 함수가
      제목과 note 만 봐서 그 값을 통째로 못 읽었다. 그래서 시각이 분명히 적힌 일정도
      '시각 없음'으로 분류돼 30분 전 알림 대상에서 조용히 빠졌다.
      실측(2026-08-25): 8/27 GM 일정 2건이 시각 칸에 10:30·14:00 을 갖고 있는데
      이 함수는 둘 다 빈 문자열을 돌려주고 있었다 — 둘 다 알림이 안 울렸을 것이다.
      ▸우선순위를 제목·note 뒤에 둔 이유 = 기존에 그 두 곳으로 잡히던 일정의 동작을
        한 건도 바꾸지 않기 위해서다(회귀 0). 시각 칸은 '아무 데서도 못 찾았을 때'만 쓴다.
    """
    m = re.search(r'\((\d{1,2}:\d{2})\)', name)
    if m:
        return m.group(1)
    m = _NOTE_TIME_RE.match(note or '')
    if m:
        return m.group(1)
    m = re.match(r'^(\d{1,2}:\d{2})$', str(time_cell or '').strip())
    return m.group(1) if m else ''


def _filter_today_items(items: list, day: str) -> list:
    """그날 GM 담당 항목만 (시각, 제목) 쌍으로 시각순 정렬해 돌려준다. 시각 없는 항목은 뒤로."""
    out = []
    for it in items or []:
        if (it or {}).get('next_due') != day:
            continue
        assignee = it.get('assignee') or ''
        if 'GM' not in assignee and '김남욱' not in assignee:
            continue
        name = it.get('name') or ''
        time_s = _extract_time(name, it.get('note') or '', it.get('time') or '')
        title = re.sub(r'\s*\(\d{1,2}:\d{2}\)\s*', '', name).strip()
        out.append((time_s, title))
    out.sort(key=lambda p: p[0] or '99:99')
    return out


def _format_schedule(pairs: list) -> str:
    return '\n'.join(f"{t} {title}" if t else title for t, title in pairs)


def schedule_lines(day: str | None = None) -> str:
    """오늘 일정 본문(줄바꿈 join). 0건이면 빈 문자열 — 호출부가 그 자리를 통째로 뺀다."""
    day = day or today()
    return _format_schedule(_filter_today_items(_load_schedule_items(), day))

# 생활 토막 → 트래커 축(axes). 정본 = gm_personal_routine.json 의 toroks[].axes 와 같은 매핑.
# 여기서 다시 적는 이유는 버튼 4개로 줄이기 위해서다 — 축 9개를 다 물으면 원래 문제로 돌아간다.
# ★토막은 5개다 — 4개로 만들었다가 「⚖️ 단순함」이 영원히 빠지는 걸 놓쳤다(2026-08-08 수리).
#   G1 화면은 /5 로 세므로, 4개만 물으면 하루를 다 채워도 화면엔 4/5 로 뜬다.
TOROKS = [
    ('self',     '🌱', '나',   ['morning_ex', 'self_dev']),
    ('dad',      '👨‍👧', '아빠', ['evening_run']),
    ('husband',  '💑', '남편', ['family_time']),
    ('work',     '💼', '일',   ['work_focus']),
    ('simple',   '⚖️', '단순함', ['principle']),
]
# G1 트래커(MOOD_LABEL)와 같은 벌을 쓴다 — 두 벌이면 한쪽에서 누른 기분이 다른 쪽에서 '안 적음'이 된다.
MOODS = ['😀', '🙂', '😐', '😔']


def today() -> str:
    return datetime.date.today().isoformat()


def load() -> dict:
    return json.loads(JPATH.read_text(encoding='utf-8'))


def _day(data: dict, day: str) -> dict:
    """그날 칸을 꺼낸다. 없으면 만들되 **어제 값을 체중·수면에 이어 붙인다** —
    안 바뀌는 값을 매일 다시 적게 하지 않는다(A안의 '안 바뀌면 그냥 넘김')."""
    days = data.setdefault('days', {})
    if day in days:
        return days[day]
    prev = [days[k] for k in sorted(days) if k < day]
    last = prev[-1] if prev else {}
    days[day] = {
        'weight': last.get('weight', ''),
        'sleep': last.get('sleep', ''),
        'axes': {},
        'note': '',
        'mood': '',
        'source': 'telegram',
    }
    return days[day]


DONE_MARKS = ('O', '△')   # G1 트래커(litToroks)와 같은 판정 — O 만 세면 '조금'이 화면에서 사라진다


def state(day: str | None = None) -> dict:
    """지금 눌려 있는 토막·기분. 버튼 표시에 쓴다."""
    day = day or today()
    d = _day(load(), day)
    axes = d.get('axes') or {}
    on = {tid for tid, _i, _l, keys in TOROKS
          if any(axes.get(k) in DONE_MARKS for k in keys)}
    return {'on': on, 'mood': d.get('mood') or '', 'weight': d.get('weight') or '',
            'sleep': d.get('sleep') or '', 'axes': axes}


def toggle(torok_id: str, day: str | None = None) -> dict:
    """토막 하나를 켜고 끈다. 켜면 그 토막이 물고 있는 축을 전부 'O', 끄면 전부 빈칸."""
    day = day or today()
    data = load()
    d = _day(data, day)
    axes = d.setdefault('axes', {})
    keys = next((k for tid, _i, _l, k in TOROKS if tid == torok_id), None)
    if not keys:
        return state(day)
    turning_on = not all(axes.get(k) == 'O' for k in keys)
    for k in keys:
        axes[k] = 'O' if turning_on else ''
    _write(data)
    return state(day)


def set_mood(mood: str, day: str | None = None) -> dict:
    day = day or today()
    data = load()
    d = _day(data, day)
    d['mood'] = '' if d.get('mood') == mood else mood
    _write(data)
    return state(day)


# ── 시점별 체크(끼니·운동) 4슬롯 — GM 요청 2026-08-09 "아침에 먹는것도 운동하는것도 다
#   체크하고, 점심 먹는거 간식 먹는거 저녁 먹고 운동도". 저녁 설문(TOROKS)이 하루가
#   끝난 뒤 5토막·기분을 묻는 것과 달리, 이건 그때그때(아침/점심/간식/저녁) 끼니·운동만
#   묻는다 — 겹치지 않는다. 운동 축은 TOROKS 가 이미 쓰는 morning_ex·evening_run 재사용.
#   (슬롯id, 시, 분, 카드제목, [(축id, 문항라벨), ...])
SLOTS = [
    ('morning', 9, 0, '🌅 아침', [('meal_breakfast', '🍚 아침 먹었다'), ('morning_ex', '🏃 아침 운동')]),
    ('lunch', 13, 30, '🍚 점심', [('meal_lunch', '점심 먹었다')]),
    ('snack', 16, 30, '🍪 간식', [('snack', '간식 먹었다')]),
    ('dinner', 21, 0, '🌆 저녁', [('meal_dinner', '🍚 저녁 먹었다'), ('evening_run', '🏃 저녁 운동')]),
]
_MEAL_AXES = ('meal_breakfast', 'meal_lunch', 'snack', 'meal_dinner')
_EX_AXES = ('morning_ex', 'evening_run')


def _selfcheck_slots() -> None:
    """버튼 6종(아침식사·아침운동·점심식사·간식·저녁식사·저녁운동) ↔ 저장 축이 1:1인지 확인.
    SLOTS 를 손대다 축 하나를 빼먹거나 중복 매핑하면 여기서 바로 터진다."""
    slot_axes = [axis for _sid, _h, _m, _title, items in SLOTS for axis, _label in items]
    assert len(slot_axes) == 6, f"버튼 6종이어야 하는데 {len(slot_axes)}개: {slot_axes}"
    assert len(set(slot_axes)) == 6, f"축 중복: {slot_axes}"
    assert set(slot_axes) == set(_MEAL_AXES) | set(_EX_AXES), \
        f"SLOTS 축과 _MEAL_AXES/_EX_AXES 불일치: {set(slot_axes)} vs {set(_MEAL_AXES) | set(_EX_AXES)}"
    for sid, _h, _m, _title, items in SLOTS:
        for axis, _label in items:
            for code in ('O', 'X'):
                cb = f'ck:s:{sid}:{axis}:{code}'
                _, _, back_sid, back_axis, back_code = cb.split(':', 4)
                assert (back_sid, back_axis, back_code) == (sid, axis, code), cb


def _derive_meals3(axes: dict) -> None:
    """세 끼(아침·점심·저녁)가 다 O 면 meals3 도 따라 O — 사람이 따로 안 누르게(파생값).
    meals3 는 G1 화면이 읽으므로 지우지 않는다."""
    if all(axes.get(k) == 'O' for k in ('meal_breakfast', 'meal_lunch', 'meal_dinner')):
        axes['meals3'] = 'O'


def _meal_ex_line(day: str | None = None) -> str:
    """그날 체크된 끼니·운동 개수 한 줄 — 🍚2 🏃1. 저녁 마무리·주간 카드가 공유해서 쓴다."""
    day = day or today()
    axes = _day(load(), day).get('axes') or {}
    meals = sum(1 for k in _MEAL_AXES if axes.get(k) == 'O')
    ex = sum(1 for k in _EX_AXES if axes.get(k) == 'O')
    return f"🍚{meals} 🏃{ex}"


def _axis_plan(axis: str, day: str) -> str:
    """그 축의 '오늘 실제로 뭘 하기로 했나' 한 줄. 정본 = gm_personal_routine.json 의 axes[].plan
    (G1 「내 리듬」 표에서 옮겨 온 값). 일요일은 plan_sun 이 있으면 그쪽을 쓴다. 없으면 빈 문자열."""
    try:
        rows = json.loads(JPATH.read_text(encoding='utf-8')).get('axes') or []
    except Exception:
        return ''
    row = next((r for r in rows if r.get('id') == axis), None)
    if not row:
        return ''
    if datetime.date.fromisoformat(day).weekday() == 6 and row.get('plan_sun'):
        return str(row['plan_sun'])
    return str(row.get('plan') or '')


def _routine_field(key: str) -> str:
    """개인 루틴 파일의 한 줄짜리 값(기상 보충제·업무 시작 등). 없으면 빈 문자열."""
    try:
        return str(json.loads(JPATH.read_text(encoding='utf-8')).get(key) or '')
    except Exception:
        return ''


def morning_plan_lines(day: str | None = None) -> list:
    """06시 하루 시작 카드에 붙일 '오늘 아침 이렇게' — 기상 보충제 · 아침 운동 · 아침 식사 ·
    업무 시작. G1 표와 GM 정정을 그대로 읊는다(2026-08-12). 값이 없는 줄은 빼고 낸다."""
    day = day or today()
    out = []
    w = _routine_field('기상_공복보충제')
    if w:
        out.append(f"  • 기상 직후   {w}")
    for axis, label in (('morning_ex', '아침 운동'), ('meal_breakfast', '아침 식사')):
        plan = _axis_plan(axis, day)
        if plan:
            out.append(f"  • {label}   {plan}")
    work = _routine_field('업무시작')
    if work:
        out.append(f"  • 업무 시작   {work}")
    return (["🌅 오늘 아침 이렇게"] + out) if out else []


def build_slot(slot_id: str, day: str | None = None) -> dict:
    """시점 카드 하나. 항목마다 ○했다/－안했다 두 버튼, 답한 항목은 버튼이 사라진다.
    전부 답하면 본문을 「오늘 여기까지」 요약으로 바꾼다."""
    day = day or today()
    slot = next((s for s in SLOTS if s[0] == slot_id), None)
    if not slot:
        return {'text': '', 'markup': None}
    _sid, _h, _m, title, items = slot
    if haru_v2(day):
        # [웰리 결정 2 · 2026-08-29] 간식 = 13:30 병합 — GM 지시문 6번이 「점심·간식 체크인」으로
        # 못박았다. 16:30 통은 폐지(발신은 run_gm_checkin_slot 이 스킵), 축·기록 키는 그대로다.
        if slot_id == 'lunch':
            title = '🍪 점심·간식'
            items = list(items) + list(next(s for s in SLOTS if s[0] == 'snack')[4])
    axes = _day(load(), day).get('axes') or {}
    # 'M'(미응답 · v2 30분 재알림 뒤 확정)도 끝난 것으로 본다 — 더 묻지 않는다(GM 규약).
    if all(axes.get(axis) in ('O', 'X', 'M') for axis, _label in items):
        return {'text': f"오늘 여기까지 — {_meal_ex_line(day)}", 'markup': None}
    lines = [title, '']
    rows = []
    for axis, label in items:
        v = axes.get(axis)
        mark = {'O': '✅', 'X': '－', 'M': '–'}.get(v, '·')
        lines.append(f"{mark} {label}")
        # GM 이 G1 에 적어 둔 그날의 실제 구성을 그대로 읊는다 (GM 지시 2026-08-12 —
        # "아침을 먹었다"만으로는 부족하고 무엇을 먹는지가 중요하다). 값이 없으면 아무 것도 안 붙인다.
        plan = _axis_plan(axis, day)
        if plan:
            lines.append(f"   {plan}")
        if v not in ('O', 'X', 'M'):
            # ★버튼에 무엇에 대한 답인지 적는다 (GM 지시 2026-08-13 "아침 식사 / 아침 운동
            #   이렇게 별도로 했다 안했다로 해줘"). 전에는 두 축 다 안 눌린 아침 카드에
            #   '○ 했다 / － 안 했다' 줄이 **똑같이 두 줄** 떠서 어느 줄이 식사고 어느 줄이
            #   운동인지 눌러 보기 전엔 알 수 없었다. 이름은 기존 축 분류에서 뽑는다
            #   (_MEAL_AXES/_EX_AXES — 새 표 만들지 않는다 · 약속 L01).
            kind = '간식' if axis == 'snack' else ('식사' if axis in _MEAL_AXES else '운동')
            icon = label[0] if label and not label[0].isalnum() and label[0] not in ' ' else ''
            tag = f"{icon} {kind}".strip()
            if haru_v2(day):
                # v2 체크인 규약(GM 확정) — 버튼은 ✅했음/❌못함 둘뿐, 자유 입력 요구 없음.
                rows.append([{'text': f'✅ {tag} 했음', 'callback_data': f'ck:s:{slot_id}:{axis}:O'},
                             {'text': f'❌ {tag} 못함', 'callback_data': f'ck:s:{slot_id}:{axis}:X'}])
            else:
                rows.append([{'text': f'○ {tag} 했다', 'callback_data': f'ck:s:{slot_id}:{axis}:O'},
                             {'text': f'－ {tag} 안 했다', 'callback_data': f'ck:s:{slot_id}:{axis}:X'}])
    # 구성이 적혀 있는 카드에만 고치는 길을 한 줄로 알린다(GM 지시 2026-08-12 "아닌건 수정하는 방향으로").
    if any(_axis_plan(axis, day) for axis, _label in items):
        lines += ['', '바뀐 게 있으면 답장으로 알려 주세요 — 그대로 고칩니다.']
    return {'text': '\n'.join(lines), 'markup': {'inline_keyboard': rows}}


def set_slot_answer(slot_id: str, axis: str, code: str, day: str | None = None) -> None:
    """시점 카드 버튼 하나의 답을 그 자리에서 저장한다."""
    if code not in ('O', 'X'):
        return
    day = day or today()
    data = load()
    d = _day(data, day)
    axes = d.setdefault('axes', {})
    axes[axis] = code
    _derive_meals3(axes)
    _write(data)


# ── 저녁 설문 — 한 번에 하나씩 (GM 2026-08-08 "Survey 처럼 기록해도 좋을 것 같긴한데") ──
#   왜 바꿨나: 버튼 10개가 한 화면에 깔리니 무엇부터 눌러야 할지 알 수 없었다(GM: "난해하다").
#   같은 메시지를 문항마다 갈아 끼운다(editMessageText) — 방이 카드로 더러워지지 않는다.
#   문항 = 토막 5개(아침에 정한 그 문장을 그대로 물어본다) + 기분 1개 = 6문. 탭 6번이면 끝.
#   답은 기존 데이터 모델 그대로 O(했다)·△(조금)·X(못 했다) — 5점 척도는 안 쓴다(점수 냄새).
#   문항마다 바로 저장한다 — 중간에 그만두셔도 답한 데까지가 그날 기록이다.
ANSWERS = [('O', '○ 했다'), ('T', '△ 조금'), ('X', '－ 못 했다')]
_ANS_VALUE = {'O': 'O', 'T': '△', 'X': 'X'}


def set_answer(idx: int, code: str, day: str | None = None) -> None:
    """문항 하나의 답을 그 자리에서 저장한다. idx = 토막 순번, 마지막 +1 = 기분."""
    day = day or today()
    data = load()
    d = _day(data, day)
    if idx < len(TOROKS):
        _tid, _i, _l, keys = TOROKS[idx]
        axes = d.setdefault('axes', {})
        for k in keys:
            axes[k] = _ANS_VALUE.get(code, '')
    elif idx == len(TOROKS):
        d['mood'] = code if code in MOODS else ''
    _write(data)


def build_step(idx: int, day: str | None = None) -> dict:
    """문항 하나의 화면. idx 가 문항 수를 넘으면 마무리 화면을 낸다.

    반환 {'text': 본문, 'markup': inline_keyboard 또는 None}
    """
    day = day or today()
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]
    total = len(TOROKS) + 1
    head = f"🌙 오늘 어떠셨어요 — {d.month}/{d.day}({wd})"

    if idx < len(TOROKS):
        tid, icon, label, _k = TOROKS[idx]
        sentence = (plan(day) or {}).get(tid, '')
        text = (f"{head}\n{idx + 1}/{total}\n\n"
                f"{icon} {label}\n{sentence}\n\n하셨어요?")
        rows = [[{'text': lab, 'callback_data': f'ck:q:{idx}:{code}'} for code, lab in ANSWERS]]
        return {'text': text, 'markup': {'inline_keyboard': rows}}

    if idx == len(TOROKS):
        text = f"{head}\n{total}/{total}\n\n오늘 기분은 어떠셨어요?"
        rows = [[{'text': m, 'callback_data': f'ck:q:{idx}:{m}'} for m in MOODS]]
        return {'text': text, 'markup': {'inline_keyboard': rows}}

    return {'text': _finish_text(day),
            'markup': {'inline_keyboard': [[{'text': '🔧 다시 답하기',
                                             'callback_data': 'ck:q:0:'}]]}}


def _finish_text(day: str) -> str:
    """마무리 화면 — 오늘 무엇이 담겼는지 한 장. 여기에만 취침 안내가 붙는다."""
    st = state(day)
    lines = ["✅ 오늘 기록했습니다", ""]
    p = plan(day) or {}
    for tid, icon, label, keys in TOROKS:
        v = next((st['axes'].get(k) for k in keys if st['axes'].get(k)), '')
        mark = {'O': '○', '△': '△', 'X': '－'}.get(v, '·')
        lines.append(f"{mark} {icon} {label}   {p.get(tid, '')}")
    lines.append("")
    lines.append(f"담긴 토막 {len(st['on'])}/{len(TOROKS)}   {_meal_ex_line(day)}"
                 + (f"   기분 {st['mood']}" if st['mood'] else ""))
    lines += ["", "한 줄 남기시려면 이 메시지에 답장해 주세요.",
              "", "📵 전자기기 off — 수면 루틴 시작",
              "오늘 하루도 고생 많으셨습니다."]
    return '\n'.join(lines)


def _write(data: dict) -> None:
    data['updated_at'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    JPATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ── 💡 아이디어 쌓아두기 (GM 지시 2026-08-30) ────────────────────────────────
#   GM: "아이디어 생각날 때마다 말해줄 테니까 하루 공지에다가 조금씩 추가해주라."
#   새 원장을 만들지 않는다(약속 L21) — 이미 GM 개인 것을 담는 이 파일에 ideas 한 칸을 얹는다.
#   지우지 않고 쌓기만 한다. 만든 뒤에는 GM 이 done 처리한다(mark_idea_done).
def add_idea(text: str, day: str | None = None) -> int:
    """아이디어 한 줄을 쌓는다. 같은 글이 이미 열려 있으면 다시 넣지 않는다(중복 금지)."""
    text = ' '.join(str(text or '').split())
    if not text:
        return 0
    data = load()
    ideas = data.setdefault('ideas', [])
    if any(not i.get('done') and i.get('text') == text for i in ideas):
        return 0
    ideas.append({'t': day or today(), 'text': text, 'done': False})
    _write(data)
    return len(ideas)


def open_ideas() -> list:
    """아직 안 만든 아이디어 — 적은 순서 그대로. 잘라내지 않는다(GM 지시 2026-08-30 · 전부 보여준다)."""
    try:
        return [i for i in (load().get('ideas') or []) if not i.get('done')]
    except Exception:
        return []


def mark_idea_done(text_or_index) -> bool:
    """만들었으면 닫는다. 번호(1부터) 또는 글 일부로 찾는다."""
    data = load()
    ideas = data.get('ideas') or []
    opened = [i for i in ideas if not i.get('done')]
    target = None
    if isinstance(text_or_index, int) or str(text_or_index).isdigit():
        n = int(text_or_index)
        if 1 <= n <= len(opened):
            target = opened[n - 1]
    else:
        key = str(text_or_index).strip()
        target = next((i for i in opened if key in i.get('text', '')), None)
    if not target:
        return False
    target['done'] = True
    target['done_at'] = today()
    _write(data)
    return True


def _idea_section() -> str:
    """하루 공지에 붙는 아이디어 절. 없으면 빈 문자열(빈 절을 만들지 않는다)."""
    items = open_ideas()
    if not items:
        return ''
    lines = [f"💡 쌓아둔 아이디어 {len(items)}건"]
    lines += [f"· {i['text']} ({i['t'][5:].replace('-', '/')})" for i in items]
    return '\n'.join(lines)


# ── 📖 오늘의 문장 — 체화할 때까지 반복 (GM 지시 2026-08-30) ──────────────────
#   GM: "매일 아침에 명언 및 진리로 문장을 반복되게(내가 체화할 때까지) 보고 싶어."
#   그래서 날마다 바꾸지 않는다. 한 문장을 GM 이 「다음」 이라고 할 때까지 계속 같은 자리에 둔다.
#   며칠째인지만 옆에 적는다 — 재촉이 아니라 얼마나 데리고 있었는지 보이라고.
#   새 원장 0 — 아이디어와 같은 파일(gm_personal_routine.json) 의 creed 칸.
def _creed(data: dict) -> dict:
    return data.setdefault('creed', {'items': [], 'index': 0, 'since': today()})


def creed_add(text: str, source: str = '') -> int:
    """문장을 목록 끝에 더한다. 같은 글이 이미 있으면 넣지 않는다."""
    text = ' '.join(str(text or '').split())
    if not text:
        return 0
    data = load()
    c = _creed(data)
    if any(i.get('text') == text for i in c['items']):
        return 0
    c['items'].append({'text': text, 'source': source})
    _write(data)
    return len(c['items'])


def creed_next() -> str:
    """이 문장은 체화됐다 — 다음 문장으로 넘긴다. 끝에 닿으면 처음으로 돌아간다."""
    data = load()
    c = _creed(data)
    if not c['items']:
        return ''
    c['index'] = (int(c.get('index') or 0) + 1) % len(c['items'])
    c['since'] = today()
    _write(data)
    return c['items'][c['index']]['text']


def creed_today() -> tuple:
    """(문장, 출처, 며칠째). 목록이 비면 ('', '', 0)."""
    try:
        c = (load().get('creed') or {})
        items = c.get('items') or []
        if not items:
            return ('', '', 0)
        it = items[int(c.get('index') or 0) % len(items)]
        try:
            days = (datetime.date.fromisoformat(today())
                    - datetime.date.fromisoformat(c.get('since') or today())).days + 1
        except Exception:
            days = 1
        return (it.get('text', ''), it.get('source', ''), max(1, days))
    except Exception:
        return ('', '', 0)


def _creed_section() -> str:
    """아침 공지 맨 위에 붙는 오늘의 문장. 없으면 빈 문자열."""
    text, source, days = creed_today()
    if not text:
        return ''
    tail = f" — {source}" if source else ''
    return f"📖 오늘의 문장 ({days}일째)\n「{text}」{tail}"


def commit(day: str | None = None) -> bool:
    """저장을 눌렀을 때만 커밋한다 — 버튼 누를 때마다 커밋하면 하루에 열 번 쌓인다.
    실패해도 파일은 이미 로컬에 남아 있으므로 다음 커밋에 자연히 딸려 간다."""
    day = day or today()
    try:
        r = subprocess.run(
            ['C:/Python314/python.exe', str(ROOT / 'scripts' / 'safe_commit.py'),
             '-m', f'chore(gm): 개인 체크인 {day} (텔레그램)', '--',
             'status/gm_personal_routine.json'],
            cwd=str(ROOT), capture_output=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False


def summary(day: str | None = None) -> str:
    """저장 후 GM 께 보여 줄 한 줄. 점수·심판이 아니라 거울이다(파일 _doc 원칙)."""
    day = day or today()
    st = state(day)
    marks = ' '.join(i if tid in st['on'] else '·' for tid, i, _l, _k in TOROKS)
    n = len(st['on'])
    line = f"{marks}   담긴 토막 {n}/{len(TOROKS)}   {_meal_ex_line(day)}"
    if st['mood']:
        line += f"   기분 {st['mood']}"
    return line


def plan(day: str | None = None) -> dict:
    """그날의 '오늘 하나만' — 토막별 제안 1개. 한 번 정해지면 그날은 안 바뀐다.

    체크만 하는 카드는 '했나/안 했나'로 끝난다. GM 지적(2026-08-08): "1가지씩 뭘 하게끔
    만들고 느끼게끔 하는 게 중요하다." 그래서 아침에 네 가지를 정해 두고, 저녁 카드가
    같은 문장을 그대로 다시 보여 준다 — 아침에 정한 걸 저녁에 마주하면 하루가 남는다.

    뽑는 규칙: 최근 7일에 나온 제안은 뺀다(같은 말이 반복되면 벽지가 된다).
    남는 게 없으면 풀 전체에서 날짜 기준으로 순환한다 — 무작위를 안 쓴다(같은 날 다시
    불러도 같은 값이 나와야 아침 카드와 저녁 카드가 어긋나지 않는다).
    """
    day = day or today()
    data = load()
    d = _day(data, day)
    if d.get('plan'):
        return d['plan']

    pools = data.get('suggestions') or {}
    days = data.get('days') or {}
    recent = set()
    base = datetime.date.fromisoformat(day)
    for i in range(1, 8):
        prev = days.get((base - datetime.timedelta(days=i)).isoformat()) or {}
        recent.update((prev.get('plan') or {}).values())

    picked = {}
    for tid, _icon, _label, _keys in TOROKS:
        pool = pools.get(tid) or []
        if not pool:
            continue
        fresh = [s for s in pool if s not in recent] or pool
        picked[tid] = fresh[base.toordinal() % len(fresh)]
    d['plan'] = picked
    _write(data)
    return picked


def build_prompt(day: str | None = None) -> str:
    """카드 자체가 설명서다.

    GM 이 첫 카드를 받고 "뭔지 잘 모르겠는데"라고 했다(2026-08-08). 별도 가이드 문서를
    만들면 그 문서를 또 찾아야 한다 — 매일 오는 카드 안에 뜻을 적어 두는 쪽이 맞다.
    네 줄은 GM 개인 북극성("나·아빠·남편·일이 다 담겨 돌아가는 하루")의 네 토막 그대로다.
    """
    day = day or today()
    st = state(day)
    p = plan(day)
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]
    lines = [f"🌙 오늘 어떠셨어요 — {d.month}/{d.day}({wd})",
             "아침에 정한 다섯 가지입니다. 하신 것만 눌러 주세요.", ""]
    for tid, icon, label, _k in TOROKS:
        mark = '✅' if tid in st['on'] else '　'
        lines.append(f"{mark}{icon} {label}   {p.get(tid, '')}")
    lines += ["",
              "못 하신 건 그냥 두세요 — 그것도 오늘입니다.",
              "아래 줄은 오늘 기분. 다 누르셨으면 💾 저장."]
    carry = []
    if st['weight']:
        carry.append(f"체중 {st['weight']}")
    if st['sleep']:
        carry.append(f"수면 {st['sleep']}")
    if carry:
        lines += ["", ' · '.join(carry) + " ← 어제 값 그대로 (바뀌었으면 답장으로 적어 주세요)"]
    return '\n'.join(lines)


def build_markup(day: str | None = None) -> dict:
    """텔레그램 inline_keyboard. 켜진 토막은 앞에 ✅ 를 붙여 지금 상태가 그대로 보이게 한다."""
    day = day or today()
    st = state(day)
    btn = [{'text': ('✅' if tid in st['on'] else '') + f'{icon} {label}',
            'callback_data': f'ck:t:{tid}'} for tid, icon, label, _k in TOROKS]
    # 토막 5개를 한 줄에 넣으면 글자가 잘린다 — 3+2 로 나눈다.
    rows = [btn[:3], btn[3:]]
    rows.append([{'text': ('✅' if st['mood'] == m else '') + m,
                  'callback_data': f'ck:m:{m}'} for m in MOODS])
    rows.append([{'text': '💾 저장', 'callback_data': 'ck:save'},
                 {'text': '오늘은 건너뜀', 'callback_data': 'ck:skip'}])
    return {'inline_keyboard': rows}


def week_card(day: str | None = None) -> str:
    """일요일 저녁 한 주 카드 — 지난 7일 도달율. 없는 날은 없다고만 적는다.
    v2(2026-09-01~)는 체크인 집계만 담는 주간 루틴 리포트(_week_card_v2)로 간다."""
    day = day or today()
    if haru_v2(day):
        return _week_card_v2(day)
    end = datetime.date.fromisoformat(day)
    data = load()
    days = data.get('days') or {}
    # 기록이 없는 날도 분모에 넣는다(7일 × 4토막 = 28). 기록된 날만 세면 하루 적고
    # 나머지를 비운 주가 100% 로 나온다 — 거울이 아니라 거짓말이 된다.
    lines, filled, total = [], 0, 28
    for i in range(6, -1, -1):
        dt = end - datetime.timedelta(days=i)
        rec = days.get(dt.isoformat())
        wd = '월화수목금토일'[dt.weekday()]
        if not rec:
            lines.append(f"{dt.month}/{dt.day}({wd})  — 기록 없음")
            continue
        axes = rec.get('axes') or {}
        pl = rec.get('plan') or {}
        done = [(tid, icon) for tid, icon, _l, keys in TOROKS
                if all(axes.get(x) == 'O' for x in keys)]
        filled += len(done)
        head = (f"{dt.month}/{dt.day}({wd})  {' '.join(i for _t, i in done) if done else '·'}   {len(done)}/4"
                f"   {_meal_ex_line(dt.isoformat())}")
        if rec.get('mood'):
            head += f"  {rec['mood']}"
        lines.append(head)
        # 실제로 한 것 한 줄만 덧붙인다 — 한 주를 훑을 때 '무엇을' 했는지가 남게(GM 2026-08-08).
        for tid, _icon in done[:2]:
            if pl.get(tid):
                lines.append(f"      └ {pl[tid]}")
    pct = round(filled / total * 100)
    return ("🗓️ 한 주 — 무엇이 담겼나\n" + '\n'.join(lines)
            + f"\n\n담긴 토막 {filled}/{total} · {pct}%\n"
              "점수가 아니라 거울입니다 — 비어 있어도 괜찮습니다."
            + routine_review(day))


# ── 지킨 만큼만 세고, 세어 본 것에서만 제안한다 (GM 지시 2026-08-12) ────────────────
#   GM: "위에것을 했는지 체크를 해주고, 기록해주고, 더 개선할게 있으면 제안해주고,
#   아닌건 수정하는 방향으로." 제안은 계산된 사실에서만 나온다 — 감상·일반론 금지.
_REVIEW_AXES = (('meal_breakfast', '아침 식사'), ('morning_ex', '아침 운동'),
                ('meal_lunch', '점심 식사'), ('evening_run', '저녁 운동'))


def _kept_counts(day: str, span: int = 7) -> dict:
    """최근 span 일 동안 축별로 O 를 센다. 기록 없는 날도 분모에 넣는다(안 센 날을 빼면 거짓이 된다)."""
    end = datetime.date.fromisoformat(day)
    days = (load().get('days') or {})
    out = {}
    for axis, _label in _REVIEW_AXES:
        n = 0
        for i in range(span):
            rec = days.get((end - datetime.timedelta(days=i)).isoformat()) or {}
            if (rec.get('axes') or {}).get(axis) == 'O':
                n += 1
        out[axis] = n
    return out


def routine_review(day: str | None = None, span: int = 7) -> str:
    """지킨 횟수 한 줄 + 그 숫자에서 나오는 제안 1개. 제안거리가 없으면 제안 줄을 안 붙인다."""
    day = day or today()
    kept = _kept_counts(day, span)
    counts = ' · '.join(f"{label} {kept[axis]}/{span}" for axis, label in _REVIEW_AXES)
    out = ["", "", f"📌 지난 {span}일 — {counts}"]

    # 제안 — 조건에 맞는 첫 한 개만. 여러 개를 한꺼번에 내면 아무것도 안 남는다.
    b, ex = kept['meal_breakfast'], kept['morning_ex']
    if b <= span // 2:
        out.append(f"제안 — 아침이 {b}/{span}입니다. 구성이 길어 부담이면 "
                   "'미온수 + 달걀 + 주스'까지만 고정으로 줄여 보시죠.")
    elif ex <= span // 2 < b:
        out.append(f"제안 — 아침은 {b}/{span}인데 아침 운동은 {ex}/{span}입니다. "
                   "운동을 식사 앞에 붙이면 하나로 굴러갑니다.")
    else:
        # 잘 지켜지는 주에는 내용 쪽 제안 — G1 「영양 관리」가 이미 적어 둔 단백질 부족(약 65g/권장 120g).
        out.append("제안 — 아침 달걀 1개는 단백질 약 6g입니다. "
                   "G1 영양 관리에 적힌 하루 부족분(약 65g/권장 120g)을 메우려면 달걀 2개가 가장 쉽습니다.")
    out.append("맞지 않으면 이 방에 답장으로 적어 주세요 — 계획을 그대로 고치겠습니다.")
    return '\n'.join(out)


# ── 08:00 GM 업무 브리핑 (배514 미배선 해소, GM 지시 2026-08-10) ──────────────────
#   왜: schedule_lines() 는 있었는데 그걸 부르는 08:00 잡이 저장소에 0건이었다 — 실제 06:00은
#   daily_scheduler._checkin_morning_block() 이 나가는데 그건 schedule_lines() 를 안 부른다.
#   여기서 실제로 쓰이게 배선한다(더 이상 죽은 코드 아님). 소스 4종(전사일정·GM업무 월간
#   objectives 「(GM 직접)」·업무SSOT 김남욱 담당·회장님 보고건)을 모으되, 기한 필드가 없는
#   GM업무·회장님 보고건을 "오늘 할 일"로 몰지 않는다(지어내기 금지) — 4묶음으로 정직히 나눈다.
from queue_dispatch import ROLES as _CLEVEL_NICKS, EXCLUDED_ROLES as _QUEUE_EXCLUDED_ROLES  # noqa: E402
from worklog import GM_AREAS  # noqa: E402  — 정본=worklog.py(값 복사 금지·약속 L01)

MONTHLY_PLAN = ROOT / 'status' / 'monthly_ops_plan.json'
WORKLOG_PATH = ROOT / 'status' / 'worklog.jsonl'  # 저녁 정리 카드(build_evening_recap) 소스
CHAIRMAN_ITEMS_JS = ROOT / '3. 웰페리온 가이드' / 'coo' / 'chairman' / '_chairman_items.js'
CHAIRMAN_REPORTED = ROOT / '3. 웰페리온 가이드' / 'coo' / 'chairman' / 'chairman_reported.json'
GM_WORK_URL = 'https://wellperion-cao.github.io/wellperion-automation/coo/chairman/GM%EC%97%85%EB%AC%B4.html'
G1_URL = 'https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#G1'
_CHAIRMAN_ITEM_RE = re.compile(r"\{\s*id:\s*'([^']+)',\s*title:\s*'([^']+)'")


def _fetch_gm_direct_objectives(day: str) -> list | None:
    """이번 달 objectives 중 제목에 「(GM 직접)」 이 든 것. 실패 시 None."""
    try:
        data = json.loads(MONTHLY_PLAN.read_text(encoding='utf-8'))
        objs = ((data.get('months') or {}).get(day[:7]) or {}).get('objectives') or []
        return [o for o in objs if '(GM 직접)' in str(o.get('title', ''))]
    except Exception:
        return None


def _fetch_gm_ssot_open() -> list | None:
    """업무 SSOT(GAS todo_list) 담당자=김남욱·상태 열려있는 항목. 실패 시 None."""
    try:
        from collectors.ops_shared import SSOT_API_URL, TODO_DONE_STATUSES, gas_get
    except Exception:
        return None
    resp = gas_get(SSOT_API_URL, params={'action': 'todo_list'}, label='gm_morning_brief')
    if resp is None:
        return None
    try:
        data = resp.json()
        if not data.get('ok'):
            return None
        items = data.get('data') or []
        return [x for x in items
                if '김남욱' in str(x.get('담당자', ''))
                and str(x.get('상태', '')) not in TODO_DONE_STATUSES]
    except Exception:
        return None


def _parse_due(s: str):
    try:
        return datetime.datetime.fromisoformat(str(s or '').rstrip('Z').replace('T', ' ')).date()
    except Exception:
        return None


def _split_by_due(items: list, day: str) -> tuple[list, list]:
    """(종료일 오늘+3일 이내·이미 지남, 나머지) — (항목, due) 쌍 리스트로."""
    base = datetime.date.fromisoformat(day)
    near, rest = [], []
    for x in items:
        due = _parse_due(x.get('종료일'))
        (near.append((x, due)) if due is not None and due <= base + datetime.timedelta(days=3)
         else rest.append(x))
    return near, rest


def _due_label(due, day: str) -> str:
    delta = (datetime.date.fromisoformat(day) - due).days
    if delta > 0:
        return f"D+{delta} 지남"
    if delta == 0:
        return "오늘 마감"
    return f"D{delta} 마감"


def _fetch_chairman_open() -> list | None:
    """회장님 보고건 중 chairman_reported.json 에 완료일이 없는 것만. 실패 시 None."""
    try:
        js = CHAIRMAN_ITEMS_JS.read_text(encoding='utf-8')
    except Exception:
        return None
    items = [{'id': m.group(1), 'title': m.group(2)} for m in _CHAIRMAN_ITEM_RE.finditer(js)]
    try:
        reported = json.loads(CHAIRMAN_REPORTED.read_text(encoding='utf-8'))
    except Exception:
        reported = {}
    return [it for it in items if not reported.get(it['id'])]


def _bucket(title: str, lines: list, fail_note: str = '') -> str:
    """묶음 한 칸. 0건·실패없음이면 빈 문자열(호출부가 그 자리를 통째로 뺀다). 5줄 초과는 접는다."""
    if not lines and not fail_note:
        return ''
    head = f"■ {title}" + (f" ({len(lines)})" if lines else '')
    if fail_note:
        head += f" {fail_note}"
    if not lines:
        return head
    body = '\n'.join(lines[:5])
    tail = f"\n외 {len(lines) - 5}건" if len(lines) > 5 else ''
    return f"{head}\n{body}{tail}"


def _josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """앞말 받침 유무로 조사 선택. 한글이 아니면(숫자·영문·기호) 받침 있는 쪽으로 둔다."""
    ch = (word or '').rstrip()[-1:]
    if not ch or not ('가' <= ch <= '힣'):
        return with_batchim
    return with_batchim if (ord(ch) - 0xAC00) % 28 else without_batchim


def _pick_secretary_line(sched_pairs: list, due_pairs: list, waiting_lines: list, day: str) -> str:
    """맨 위 비서 한 줄 — 오늘 가장 먼저 볼 것 1개. 지목할 게 없으면 빈 문자열(억지로 안 씀)."""
    if due_pairs:
        x, due = due_pairs[0]
        return f"오늘은 {x.get('업무명', '')} 마감({_due_label(due, day)})이 가장 급합니다."
    if sched_pairs:
        t, title = sched_pairs[0]
        head = f"{title}{f'({t})' if t else ''}"
        return f"오늘은 {head}{_josa(head, '이', '가')} 가장 큽니다."
    if waiting_lines:
        head = waiting_lines[0][2:]
        return f"오늘은 {head}{_josa(head, '이', '가')} 먼저 기다리고 있습니다."
    return ''


# ── ■ 부문별 오늘 핵심 (배538, GM 지시 2026-08-10) ──────────────────────────────
#   왜: C-Level 마다 큐(status/_queue.json)에 쌓인 현실업무(office)가 브리핑에 안 보여
#   GM 이 작업 중 놓쳤다. 새 저장소·새 발송 신설 없이(약속 L21) 기존 큐에서 계산만 해
#   08:00 브리핑에 얹는다. 대상 5역할·순서 = 시포·시우·시모·시토·웰리(GM 지정, 실무비중순).
#   시로·시뽀 제외 — queue_dispatch.EXCLUDED_ROLES 를 import 해 거른다(정본 재사용).
#   ※2026-08-05부로 EXCLUDED_ROLES 자체는 비어 있다(재확정 경위=queue_dispatch.py 주석) —
#   그래도 상수를 import 해 두면 그 결정이 바뀔 때 여기도 자동 반영된다(하드코딩 방지).
#   시로·시뽀 배제 자체는 아래 목록에 그 둘을 안 넣는 것으로 확정한다.
QUEUE_PATH = ROOT / 'status' / '_queue.json'
_DEPT_ROLES = tuple(r for r in ('cpo', 'coo', 'cmo', 'cto', 'ceo') if r not in _QUEUE_EXCLUDED_ROLES)
_DEPT_OPEN_EXCLUDE = ('DONE', 'EXCLUDED', 'CANCELLED')
_DEPT_PRIORITY_WEIGHT = {'🛳️크루즈': 3, '⛴️여객선': 2, '⛵돛단배': 1}
_DEPT_TITLE_MAX = 30
_DEPT_TITLE_PREFIX_RE = re.compile(r'^\[[^\]]+\]\s*')
# ·는 뺐다 — 실측(2026-08-10)해보니 "회원관리·강습"·"블로그·카페"처럼 붙여쓴
# 병렬명사 접속으로도 흔히 쓰여, 여기서 자르면 "회원관리"·"다음 블로그"처럼
# 핵심어만 남고 뜻이 날아간다(뜻 유지가 글자수보다 우선 — 지시문 본문 기준).
_DEPT_TITLE_CUT_RE = re.compile(r'[—(]')


def _filter_office_ships(data: list) -> list:
    """열린 배 & audience=office & 대상 5역할만. (기한이 지났거나 임박한 배가 있으면 최우선
    이어야 하지만 _queue.json 스키마 조사 결과(2026-08-10, 151건 전수) due/deadline 계열
    필드가 아예 없다 — 그 규칙은 항상 건너뛴다. 필드가 생기면 여기부터 손댄다.)"""
    return [x for x in data
            if x.get('status') not in _DEPT_OPEN_EXCLUDE
            and x.get('audience') == 'office'
            and x.get('clevel') in _DEPT_ROLES]


def _dept_ship_sort_key(x: dict, day: str) -> tuple:
    """②정체일수 내림차순 → ③무게(priority) 내림차순."""
    d = _parse_due(x.get('updated_at') or x.get('enqueued_at'))
    idle = (datetime.date.fromisoformat(day) - d).days if d else -1
    return (-idle, -_DEPT_PRIORITY_WEIGHT.get(x.get('priority'), 0))


def _rank_office_ships_by_role(ships: list, day: str) -> dict:
    """role → 정렬된 상위 최대 3배."""
    out = {}
    for role in _DEPT_ROLES:
        rows = sorted((x for x in ships if x.get('clevel') == role),
                      key=lambda x: _dept_ship_sort_key(x, day))
        out[role] = rows[:3]
    return out


def _clean_ship_title(title) -> str:
    """어색한 중간 잘림 방지 — 역할표식 제거 후, 부연(—,(,·) 앞까지만 쓰고
    그래도 길면 단어(공백) 경계에서 자른다(약속 자연줄바꿈 원칙). 말줄임은 맨 뒤 … 하나뿐."""
    t = _DEPT_TITLE_PREFIX_RE.sub('', str(title or '')).strip()
    m = _DEPT_TITLE_CUT_RE.search(t)
    if m and m.start() > 0:
        t = t[:m.start()].rstrip()
    if len(t) <= _DEPT_TITLE_MAX:
        return t
    cut = t[:_DEPT_TITLE_MAX]
    sp = cut.rfind(' ')
    if sp >= _DEPT_TITLE_MAX // 2:
        cut = cut[:sp]
    return cut.rstrip(' ·—-') + '…'


def _dept_ship_reason(x: dict, day: str) -> str:
    """왜 지금인지 — 계산된 사실만(N일째 멈춤). 못 구하면 빈 문자열(감상·추측 금지)."""
    d = _parse_due(x.get('updated_at') or x.get('enqueued_at'))
    if d is None:
        return ''
    idle = (datetime.date.fromisoformat(day) - d).days
    return f"{idle}일째 멈춤" if idle >= 0 else ''


def _format_department_highlights(by_role: dict, day: str) -> str:
    """역할별 최대 3줄. office 배가 0건인 역할은 줄 자체를 뺀다(★없는 것을 만들지 마라)."""
    lines = []
    for role in _DEPT_ROLES:
        rows = by_role.get(role) or []
        for i, x in enumerate(rows):
            reason = _dept_ship_reason(x, day)
            sn = str(x.get('short_no') or x.get('ship_no') or '').strip()
            body = f"배{sn} {_clean_ship_title(x.get('title'))}" + (f" — {reason}" if reason else '')
            lines.append((f" [{_CLEVEL_NICKS.get(role, role)}] · " if i == 0 else '        · ') + body)
    if not lines:
        return ''
    return "■ 부문별 오늘 핵심\n" + '\n'.join(lines)


def _load_office_ships() -> list | None:
    """실패 시 None(자가점검 7번 「0 위장」 금지 — 0건과 못 읽음을 구분)."""
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return None
    return _filter_office_ships(data)


# ── 🎯 오늘 이것부터 (GM 지시 2026-08-11 "중요한 건을 기준으로 · 놓치는 게 없도록") ──
#   비서 한 줄 바로 아래, 브리핑 맨 위. 기존 「부문별 오늘 핵심」이 정체일수만 보다 보니
#   15줄이 전부 "N일째 멈춤"이 돼 GM 이 오늘 뭘 봐야 할지 못 골랐다 — 이건 반대로
#   "오늘 움직여야 할 것"만 우선순위 순으로 최대 5건 뽑는다. 새 원천 신설 없음(약속 L21) —
#   build_morning_brief 가 이미 계산해 둔 sched_pairs·chairman·due_pairs 만 재사용한다.
#   순위 ①오늘 일정 ②회장님 보고 대기 ③기한 지난 것. "사람이 GM 회신 기다리는 것"·
#   "매출·안전·법"은 팀장 지시 원안엔 있었으나 지어내지 않고는 뽑을 근거(신뢰 가능한 날짜·
#   플래그)가 저장소에 없어 뺐다 — 근거 생기면 여기 추가한다.
#   ★묵은순위 보정(GM 2026-08-13 지적 · 배558 후속) — 카테고리 ①이 5칸을 다 채우면 19일
#   묵은 ③건이 영영 안 보였다. 경과일수를 "있는 데이터"에만 매긴다 — ③(업무SSOT 종료일)만
#   신뢰 가능한 날짜가 있어 계산하고, ①②는 지어내지 않고 None(기존 순서 그대로 둔다).
#   ③ 안에서는 오래 묵은 순으로 정렬 + 5칸 중 최소 1칸은 전체 후보 중 가장 오래 묵은 것에
#   무조건 배정한다(이미 뽑혀 있으면 그대로).
FIRST_THINGS_MAX = 5


def _first_thing_candidates(sched_pairs: list, chairman_open: list | None,
                             due_pairs: list, day: str) -> list[tuple[str, tuple, int | None]]:
    """(표시줄, 식별키, 경과일수) 우선순위 순 후보. 식별키로 「놓친 것 없나」와 겹치지 않게 뺀다.
    경과일수는 신뢰 가능한 날짜가 있는 ③만 채운다(①②는 None — 지어내지 않는다)."""
    cands = []
    for t, title in sched_pairs:
        cands.append((f"· {(t + ' ') if t else ''}{title}", ('sched', title), None))
    for it in (chairman_open or []):
        cands.append((f"· {it['title']} — 회장님 보고 대기", ('chairman', it['id']), None))
    base = datetime.date.fromisoformat(day)
    overdue = []
    for x, due in due_pairs:
        label = _due_label(due, day)
        if label.startswith('D+'):  # 지난 것만 — 임박은 기존 「기한이 임박했습니다」가 이미 다룬다
            overdue.append((f"· {x.get('업무명', '(제목없음)')} — {label}",
                             ('ssot', x.get('업무명', '')), (base - due).days))
    overdue.sort(key=lambda c: -c[2])  # ③ 안에서는 오래 묵은 순
    cands += overdue
    return cands


def _first_thing_lines(cands: list) -> tuple[list, set]:
    """최대 5건으로 자르고, 실제로 쓰인 항목의 식별키 집합을 함께 돌려준다.
    묵은순위 보정 — 경과일수를 아는 후보 중 가장 오래 묵은 것이 5칸 밖으로 밀렸으면
    마지막 칸을 내주고 대신 들어간다(이미 5칸 안이면 그대로)."""
    picked = cands[:FIRST_THINGS_MAX]
    aged = [c for c in cands if c[2] is not None]
    if aged:
        oldest = max(aged, key=lambda c: c[2])
        if oldest not in picked:
            picked = picked[:-1] + [oldest]
    return [line for line, _k, _a in picked], {k for _l, k, _a in picked}


def _missed_lines(chairman_open: list | None, ssot_rest: list | None, used: set, max_n: int = 3) -> list:
    """「놓친 것 없나」— 오늘 이것부터에 못 들어간 답 대기 항목 중 최대 3개."""
    out = []
    for it in (chairman_open or []):
        if ('chairman', it['id']) in used:
            continue
        out.append(f"· {it['title']} — 회장님 보고 대기")
    for x in (ssot_rest or []):
        title = x.get('업무명', '(제목없음)')
        if ('ssot', title) in used:
            continue
        out.append(f"· {title} — {x.get('상태', '')} · 답 대기")
    return out[:max_n]


def build_dept_block(day: str | None = None) -> str:
    """부문별 오늘 핵심(배편) — 2026-08-12 GM 지시로 「나의하루」에서 빠져 AI 진행현황방으로 간다.
    계산은 그대로 두고 받는 방만 옮긴 것이다(값·판정 무변경)."""
    day = day or today()
    ships = _load_office_ships()
    if ships is None:
        return '■ 부문별 오늘 핵심 (불러오지 못함)'
    return _format_department_highlights(_rank_office_ships_by_role(ships, day), day)


def _tomorrow_missing_time_lines(items: list, day: str) -> list:
    """내일 GM 일정 중 시각이 비어 있는 것 — 오늘 채워 두면 내일 30분 전 알림이 울린다.

    GM 지시 2026-08-25 "다음부터 놓치지 않게 챙겨줘".
    ▸당일 아침에 알리면 늦다(그날 30분 전 알림은 이미 계산이 끝난 뒤다). 그래서 하루 전에 짚는다.
    ▸시각이 필요 없는 일정(계약 만료·양생 같은 날짜형)도 함께 걸리지만, 내일치로 좁혀 두면
      드물게 뜬다 — 매일 우는 목록을 만들지 않는다.
    ▸시각을 대신 채우지 않는다. 몇 시인지는 GM 만 아는 값이다(약속 L23·L25).
    """
    from datetime import date as _date, timedelta as _td
    try:
        tomorrow = (_date.fromisoformat(day) + _td(days=1)).isoformat()
    except Exception:
        return []
    return [f"· {title}" for t, title in _filter_today_items(items, tomorrow) if not t]


def _relayed_waiting_section(day: str) -> str:
    """「전달했는데 답이 없는 것」 절 한 칸. 0건이면 빈 문자열(그 자리가 통째로 빠진다).

    제목에 총 건수와 사람 수를 함께 적는다 — 줄 수(=사람 수)만 세는 _bucket 을 쓰면
    9건이 '(3)' 으로 보여 GM 이 건수를 오해한다.
    """
    lines, total = _relayed_waiting_lines(day)
    if not lines:
        return ''
    head = f"■ 전달했는데 답이 없는 것 {total}건 · {len(lines)}명"
    return head + '\n' + '\n'.join(lines[:5]) + (f"\n외 {len(lines) - 5}명" if len(lines) > 5 else '')


def _relayed_waiting_lines(day: str):
    """「전달했는데 답이 없는 것」 — 카톡 방으로 나간 요청 중 아직 회신이 없는 건을 사람별로 묶는다.

    GM 지시 2026-08-25: "GM업무도 그렇지만, 전달했던 내용도 놓치지 않게 해줄 수 있어?"
    ▸판정·수집은 새로 만들지 않는다 — ★중간관리자 아침 정리가 이미 쓰는
      send_ops_digest.build_reply_nudge_items() 를 그대로 부른다(약속 L21·L01).
      그 함수가 7일 창·중복 제거·담당 빈칸 제외·닫힌 건 제외까지 이미 해 준다.
    ▸사람별로 묶는 이유 = GM 이 보는 것은 "누구에게 다시 말해야 하나"이지 항목 나열이 아니다.
      항목을 다 펼치면 아침 브리핑이 그 절 하나로 길어진다.
    ▸실패는 조용히 넘긴다(fail-soft) — 이 절 때문에 브리핑 전체가 안 나가면 안 된다.
    """
    try:
        import send_ops_digest as _od
        items = _od.build_reply_nudge_items(day) or []
    except Exception:
        return [], 0
    if not items:
        return [], 0
    by_who: dict = {}
    for it in items:
        who = str(it.get('who') or '').strip() or '담당 미정'
        by_who.setdefault(who, []).append(str(it.get('ask') or '').strip())
    lines = []
    for who, asks in sorted(by_who.items(), key=lambda kv: -len(kv[1])):
        head = asks[0][:26] if asks else ''
        more = f" 외 {len(asks) - 1}건" if len(asks) > 1 else ''
        lines.append(f"· {who} {len(asks)}건 — {head}{more}")
    return lines, len(items)


def build_morning_brief(day: str | None = None) -> str:
    """08:00 「나의하루」 GM 업무 브리핑 — 월~토 발송. 전사일정·GM업무·업무SSOT·회장님 보고건 4묶음.
    v2(2026-09-01~)는 「하루의 시작」 3절(_morning_brief_v2)로 간다."""
    day = day or today()
    if haru_v2(day):
        return _morning_brief_v2(day)
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]

    sched_items, sched_ok = _load_schedule_items_ex()
    sched_pairs = _filter_today_items(sched_items, day) if sched_ok else []
    sched_lines = [f"· {(t + ' ') if t else ''}{title}" for t, title in sched_pairs]

    ssot = _fetch_gm_ssot_open()
    due_pairs, ssot_rest = _split_by_due(ssot, day) if ssot is not None else ([], [])
    due_lines = [f"· {x.get('업무명', '(제목없음)')} — {_due_label(due, day)}" for x, due in due_pairs]

    chairman = _fetch_chairman_open()
    # (표시줄, 식별키) — 「오늘 이것부터」에 이미 실린 항목은 아래에서 걸러 낸다.
    # 안 거르면 같은 회장님 보고건이 한 메시지에 두 번(맨 위 + 답 대기) 나와 GM 이 두 번 읽는다.
    waiting_pairs = []
    if ssot is not None:
        waiting_pairs += [(f"· {x.get('업무명', '(제목없음)')} — {x.get('상태', '')}",
                           ('ssot', x.get('업무명', ''))) for x in ssot_rest]
    if chairman is not None:
        waiting_pairs += [(f"· {it['title']} — 회장님 보고 대기",
                           ('chairman', it['id'])) for it in chairman]
    if ssot is None and chairman is None:
        waiting_note = '(불러오지 못함)'
    elif ssot is None or chairman is None:
        waiting_note = '— 일부 소스 불러오지 못함'
    else:
        waiting_note = ''

    objs = _fetch_gm_direct_objectives(day)
    # ★2026-08-13 GM 지시 — 「나의하루」는 "오늘 어떻게 살까"만 본다. 진행 중 배 목록(회사가
    # 어떻게 도는가)은 업무보고방 몫이라 여기선 건수 한 줄만 남기고 항목 나열은 뺀다.
    prog_count = len(objs or [])
    prog_section = (f"■ 진행 중 {prog_count}건 — 상세는 GM업무 화면" if prog_count
                     else '' if objs is not None else '■ 진행 중 (불러오지 못함)')

    first_lines, first_used = _first_thing_lines(
        _first_thing_candidates(sched_pairs, chairman, due_pairs, day))
    waiting_lines = [line for line, key in waiting_pairs if key not in first_used]
    if first_lines:
        first_section = f"🎯 오늘 이것부터 ({len(first_lines)})\n" + '\n'.join(first_lines)
    elif not sched_ok or chairman is None or ssot is None:
        first_section = "🎯 오늘 이것부터 (일부 소스 조회 실패 — 재확인 필요)"
    else:
        first_section = ''
    missed_section = _bucket('놓친 것 없나', _missed_lines(chairman, ssot_rest, first_used))

    # ★2026-08-12 GM 지시 — 「나의하루」 방은 개인 것만 온다. 부문별 배 목록(배편)은 여기서 빼고
    # AI 진행현황방으로 보낸다(build_dept_block 이 그 몫). 이 방엔 일정·체크할 것·놓치면 안 되는 것만.
    sections = [
        first_section,
        missed_section,
        _bucket('오늘 잡힌 일정', sched_lines,
                _schedule_stale_note() if sched_ok else '(불러오지 못함)'),
        _bucket('기한이 임박했습니다', due_lines, '' if ssot is not None else '(불러오지 못함)'),
        _bucket('답을 기다리는 것', waiting_lines, waiting_note),
        # 위 「답을 기다리는 것」은 업무 시트·회장님 보고건이 원천이다. 아래는 카톡 방으로
        # 나간 요청 — 원천이 달라 한 절에 섞지 않는다(섞으면 GM 이 어디를 봐야 할지 모른다).
        _relayed_waiting_section(day),
        _bucket('내일 일정 — 시각이 비어 있습니다 (넣으시면 30분 전에 알려드립니다)',
                _tomorrow_missing_time_lines(sched_items, day) if sched_ok else []),
        prog_section,
        _idea_section(),   # 💡 쌓아둔 아이디어 (GM 지시 2026-08-30)
    ]
    sections = [s for s in sections if s]

    secretary = _pick_secretary_line(sched_pairs, due_pairs, waiting_lines, day)
    if not secretary and first_lines:
        # 답 대기 항목이 「오늘 이것부터」로 전부 올라간 날 — 비서 줄만 사라지지 않게 건수로 잇는다.
        secretary = f"오늘은 답을 기다리는 {len(first_lines)}건이 먼저입니다."

    lines = [f"🌅 오늘의 업무  ·  {d.month}월 {d.day}일({wd})"]
    creed = _creed_section()   # 📖 오늘의 문장 — 맨 위 (GM 지시 2026-08-30)
    if creed:
        lines += ['', creed]
    if secretary:
        lines += ['', secretary]
    for s in sections:
        lines += ['', s]
    lines += ['', f"GM업무 화면: {GM_WORK_URL}", f"G1 항로: {G1_URL}"]
    return '\n'.join(lines)


# ── 08:00 카톡 「김남욱」 방 짧은 일정판 = 삭제 (GM 지시 2026-08-18 · 배691) ──────
#   GM: "오늘의 업무 아침 브리핑과 카카오톡 오늘 일정 브리핑 — 일정없어도 매일 발신이랑
#   중복이니까 병합하면 될듯." 위 build_morning_brief 의 「오늘 잡힌 일정」 절이 같은 원천을
#   이미 낸다. 호출부(daily_scheduler._run_gm_morning_kakao)와 함께 지웠다 — 꺼두지 않고
#   지우는 이유 = 꺼둔 코드는 죽은 코드가 되고 나중에 누가 다시 켠다(약속 L21).
def _selfcheck_morning_brief() -> None:
    """배514 — GM 직접 필터·기한임박 분리·회장님 파싱·버킷 폴딩 self-check(네트워크 없이)."""
    sample_plan_objs = [
        {'title': 'A (GM 직접)', 'status': '진행', 'progress': 40},
        {'title': 'B', 'status': '진행', 'progress': 10},
    ]
    assert [o for o in sample_plan_objs if '(GM 직접)' in o['title']] == [sample_plan_objs[0]]

    day = '2026-08-10'
    items = [
        {'업무명': '지남', '종료일': '2026-08-08T00:00:00.000Z', '상태': '대기'},
        {'업무명': '임박', '종료일': '2026-08-12T00:00:00.000Z', '상태': '대기'},
        {'업무명': '멀음', '종료일': '2026-09-29T00:00:00.000Z', '상태': '대기'},
    ]
    near, rest = _split_by_due(items, day)
    assert [x['업무명'] for x, _d in near] == ['지남', '임박'], near
    assert [x['업무명'] for x in rest] == ['멀음'], rest
    assert _due_label(near[0][1], day) == 'D+2 지남', _due_label(near[0][1], day)
    assert _due_label(near[1][1], day) == 'D-2 마감', _due_label(near[1][1], day)

    sample_js = "window.X = [\n{ id: 'd1', title: '테스트 항목', when: '오늘', cat: '기타' },\n];"
    ids = [(m.group(1), m.group(2)) for m in _CHAIRMAN_ITEM_RE.finditer(sample_js)]
    assert ids == [('d1', '테스트 항목')], ids

    assert '외 2건' in _bucket('테스트', [f'· 항목{i}' for i in range(7)])
    assert _bucket('빈', []) == ''
    assert _bucket('실패', [], '(불러오지 못함)') == '■ 실패 (불러오지 못함)'

    # ── 배538 부문별 오늘 핵심: audience=office만·시로시뽀 제외·역할당 최대 3건 ──
    dept_sample = [
        {'clevel': 'cpo', 'status': 'PENDING', 'audience': 'office', 'ship_no': 1, 'title': '[시포] A',
         'priority': '🛳️크루즈', 'updated_at': '2026-08-01', 'enqueued_at': '2026-07-01'},
        {'clevel': 'cpo', 'status': 'PENDING', 'audience': 'office', 'ship_no': 2, 'title': '[시포] B',
         'priority': '⛵돛단배', 'updated_at': '2026-08-05', 'enqueued_at': '2026-07-01'},
        {'clevel': 'cpo', 'status': 'PENDING', 'audience': 'office', 'ship_no': 3, 'title': '[시포] C',
         'priority': '⛴️여객선', 'updated_at': '2026-08-06', 'enqueued_at': '2026-07-01'},
        {'clevel': 'cpo', 'status': 'PENDING', 'audience': 'office', 'ship_no': 4, 'title': '[시포] D',
         'priority': '⛴️여객선', 'updated_at': '2026-08-07', 'enqueued_at': '2026-07-01'},  # 4번째 → 잘려야
        {'clevel': 'cpo', 'status': 'PENDING', 'audience': 'ai', 'ship_no': 5, 'title': '[시포] AI배',
         'priority': '🛳️크루즈', 'updated_at': '2026-08-01', 'enqueued_at': '2026-07-01'},  # audience=ai → 제외
        {'clevel': 'chro', 'status': 'PENDING', 'audience': 'office', 'ship_no': 6, 'title': '[시로] E',
         'priority': '🛳️크루즈', 'updated_at': '2026-08-01', 'enqueued_at': '2026-07-01'},  # chro → 제외
        {'clevel': 'cfo', 'status': 'PENDING', 'audience': 'office', 'ship_no': 7, 'title': '[시뽀] F',
         'priority': '🛳️크루즈', 'updated_at': '2026-08-01', 'enqueued_at': '2026-07-01'},  # cfo → 제외
        {'clevel': 'cpo', 'status': 'DONE', 'audience': 'office', 'ship_no': 8, 'title': '[시포] G',
         'priority': '🛳️크루즈', 'updated_at': '2026-08-01', 'enqueued_at': '2026-07-01'},  # DONE → 제외
    ]
    filtered = _filter_office_ships(dept_sample)
    assert all(x.get('audience') != 'ai' for x in filtered), filtered  # ①
    assert all(x.get('clevel') not in ('chro', 'cfo') for x in filtered), filtered  # ②
    assert {x['ship_no'] for x in filtered} == {1, 2, 3, 4}, filtered

    by_role = _rank_office_ships_by_role(filtered, day)
    assert all(len(v) <= 3 for v in by_role.values()), by_role  # ③
    assert len(by_role['cpo']) == 3, by_role['cpo']
    assert [x['ship_no'] for x in by_role['cpo']] == [1, 2, 3], by_role['cpo']  # 정체일수 내림차순

    text = _format_department_highlights(by_role, day)
    assert text.startswith('■ 부문별 오늘 핵심'), text
    assert '[시포]' in text and '배1 A — 9일째 멈춤' in text, text
    assert '[시로]' not in text and '[시뽀]' not in text, text
    assert _format_department_highlights({}, day) == ''

    # ── 「오늘 이것부터」 우선순위·5건 절단·「놓친 것 없나」 중복제외 self-check ──
    sched_pairs = [('14:00', '브로제이 방문'), ('', '주차관리인 면접'), ('09:00', 'A'), ('10:00', 'B')]
    chairman_open = [{'id': 'd9', 'title': 'X'}, {'id': 'd10', 'title': 'Y'}, {'id': 'd11', 'title': 'Z'}]
    due_pairs = [({'업무명': '지남건', '종료일': '2026-08-08'}, datetime.date(2026, 8, 8))]
    cands = _first_thing_candidates(sched_pairs, chairman_open, due_pairs, day)
    assert [k for _l, k, _a in cands[:4]] == [('sched', t) for _t, t in sched_pairs], cands  # 일정이 최우선
    first_lines, used = _first_thing_lines(cands)
    assert len(first_lines) == 5, first_lines  # 4(일정)+1 로 5 절단인데, 묵은순위 보정이 마지막 칸을
    # 가장 오래 묵은 '지남건'(D+ 최대)에 내준다 — 회장님 d9 가 밀리고 d9·d10·d11 전부 놓친 것으로 간다.
    assert ('ssot', '지남건') in used and ('chairman', 'd9') not in used, used
    missed = _missed_lines(chairman_open, [], used)
    assert missed == ['· X — 회장님 보고 대기', '· Y — 회장님 보고 대기', '· Z — 회장님 보고 대기'], missed
    # 묵은 후보가 없으면(빈 due_pairs) 기존 순서 그대로 — 지어낸 보정 없음.
    cands2 = _first_thing_candidates(sched_pairs, chairman_open, [], day)
    lines2, used2 = _first_thing_lines(cands2)
    assert ('chairman', 'd9') in used2, used2


def _selfcheck_schedule() -> None:
    """배514 — 일정 필터·정렬 self-check(네트워크 없이, 고정 표본으로). 0건→빈 자리, 다건→시각순."""
    sample = [
        {'next_due': '2026-08-10', 'assignee': 'GM', 'name': '오후 미팅 (15:00)'},
        {'next_due': '2026-08-10', 'assignee': '김남욱GM', 'name': '오전 미팅 (09:30)'},
        {'next_due': '2026-08-10', 'assignee': '수영팀', 'name': '수영장 청소'},  # GM 아님 → 제외
        {'next_due': '2026-08-11', 'assignee': 'GM', 'name': '내일 건 (10:00)'},  # 다른 날 → 제외
        # ↓ 팀장 지적(2026-08-11) — 전사일정은 날짜 단위라 시각을 note 에 적는다("HH:MM · ...").
        {'next_due': '2026-08-10', 'assignee': 'GM', 'name': '면접', 'note': '11:00 · 면접 진행'},
        {'next_due': '2026-08-10', 'assignee': 'GM', 'name': '시각 없는 건', 'note': '메모만 있음'},
    ]
    got = _filter_today_items(sample, '2026-08-10')
    assert [t for t, _ in got] == ['09:30', '11:00', '15:00', ''], got  # note 시각도 순서에 섞이고, 없는 건 맨 뒤
    assert ('11:00', '면접') in got, got
    assert _extract_time('제목 (15:00)', '11:00 · 다른시각') == '15:00'  # 제목 시각이 note 보다 우선(중복 방지)
    assert _extract_time('제목', '') == ''  # 셋 다 없으면 지어내지 않는다
    # 시각 칸(2026-08-25) — 제목·note 에 없을 때만 쓰고, 있을 때는 기존 우선순위를 지킨다.
    assert _extract_time('제목', '', '10:30') == '10:30'
    assert _extract_time('제목 (15:00)', '', '10:30') == '15:00'
    assert _extract_time('제목', '11:00 · 메모', '10:30') == '11:00'
    assert _extract_time('제목', '', '종일') == ''      # 시각이 아닌 값은 안 읽는다
    assert _extract_time('제목', '', None) == ''        # 빈 칸도 안전
    assert _format_schedule(got) == '09:30 오전 미팅\n11:00 면접\n15:00 오후 미팅\n시각 없는 건', _format_schedule(got)
    assert _filter_today_items(sample, '2099-01-01') == []
    assert _format_schedule([]) == ''


# ── 20:30 「오늘 하신 일」 저녁 정리 카드 (나의하루 방) — GM 지시 2026-08-10 ─────────
#   08:00 업무 브리핑(할 일)의 짝 — 저녁엔 오늘 GM요청 worklog 를 ok/warn ref 로 짝지어
#   끝낸 것·아직 남은 것으로 가른다. 자동 접수(UserPromptSubmit)엔 "오 된 것 같다" 같은
#   대화 부스러기가 섞이므로 노이즈 필터로 거른다(GM 지시 원문 규칙 4종).
def _recap_noise_legacy(event: str) -> bool:
    """레거시 겉모양 규칙 4종 — ref 기준 필터가 전부 걸러버릴 때만 쓰는 안전장치 폴백."""
    e = (event or '').strip()
    if e.startswith('C-Level 부팅'):
        return True
    if len(e) < 15:
        return True
    if e.endswith('?') and len(e) < 30:
        return True
    return False


_GM_REF_RE = re.compile(r'^GM-\d{8}-(\d+)$')


def _recap_noise(rec: dict) -> bool:
    """자동 접수(UserPromptSubmit) 원문 판정 — True 면 항목 후보에서 뺀다.
    ref 끝자리가 GM-YYYYMMDD-NN 형식에서 세 자리 이상 숫자면 자동 접수(잡담·부팅문 다 섞임),
    두 자리면 웰리가 실제 업무 지시로 판단해 직접 남긴 것. 그 외 형식(예: CEO-… task_id)은 그대로 둔다."""
    m = _GM_REF_RE.match(str(rec.get('ref', '')))
    if m and len(m.group(1)) >= 3:
        return True
    if '자동 접수' in str(rec.get('detail', '')):
        return True
    return False


def _load_today_gm_worklog(day: str) -> list[dict]:
    try:
        lines = WORKLOG_PATH.read_text(encoding='utf-8').splitlines()
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get('area') in GM_AREAS and str(rec.get('ts', ''))[:10] == day:
            out.append(rec)
    out.sort(key=lambda r: r.get('ts', ''))
    return out


def _dedup_consecutive(items: list[dict]) -> tuple[list[dict], int]:
    """연속 동일 항목 텍스트는 하나만 남긴다. (남은 목록, 걸러진 건수)."""
    out, dropped, last = [], 0, None
    for it in items:
        if last is not None and it['item'] == last:
            dropped += 1
            continue
        out.append(it)
        last = it['item']
    return out, dropped


def _build_done_pending_pass(day: str, noise_fn) -> tuple[list[dict], list[dict], int]:
    by_ref: dict[str, list[dict]] = {}
    for rec in _load_today_gm_worklog(day):
        by_ref.setdefault(rec.get('ref', ''), []).append(rec)

    done, pending, filtered = [], [], 0
    for group in by_ref.values():
        oks = [r for r in group if r.get('result') == 'ok']
        warns = [r for r in group if r.get('result') != 'ok']
        if oks:
            item = next((r['event'] for r in warns if not noise_fn(r)), None) \
                or next((r['event'] for r in oks if not noise_fn(r)), None)
            if item is None:
                filtered += 1
                continue
            ok = oks[-1]
            result = (ok.get('detail') or ok.get('event') or '').strip()
            done.append({'ts': max(r.get('ts', '') for r in group),
                         'item': item.strip()[:70], 'result': result[:60]})
        else:
            item = next((r['event'] for r in warns if not noise_fn(r)), None)
            if item is None:
                filtered += 1
                continue
            pending.append({'ts': max(r.get('ts', '') for r in warns), 'item': item.strip()[:70]})

    done.sort(key=lambda x: x['ts'])
    pending.sort(key=lambda x: x['ts'])
    done, d1 = _dedup_consecutive(done)
    pending, d2 = _dedup_consecutive(pending)
    return done, pending, filtered + d1 + d2


def _build_done_pending(day: str) -> tuple[list[dict], list[dict], int, bool]:
    """오늘 GM요청 worklog(ref 로 warn=접수/ok=완료 짝짓기) → (끝낸 것, 아직 남은 것, 걸러진 건수, 폴백여부).
    ref/detail 기준 새 필터가 둘 다 0건으로 만들면 과필터 신호 — 레거시 겉모양 필터로 되돌린다(빈 카드 금지)."""
    done, pending, filtered = _build_done_pending_pass(day, _recap_noise)
    if not done and not pending:
        legacy_fn = lambda rec: _recap_noise_legacy(rec.get('event', ''))
        done, pending, filtered = _build_done_pending_pass(day, legacy_fn)
        return done, pending, filtered, True
    return done, pending, filtered, False


RECAP_MAX_BUTTONS = 8  # 버튼 20개 넘으면 지저분해진다(GM 지시) — 「아직 남은 것」 상위 8개만 버튼


def _recap_snapshot(day: str) -> dict:
    """그날의 저녁 정리 재료를 얼린다(plan() 과 같은 관례) — 버튼 인덱스가 그날 안 바뀌게."""
    data = load()
    d = _day(data, day)
    if d.get('recap'):
        return d['recap']

    done, pending, filtered, fallback = _build_done_pending(day)

    sched_items, sched_ok = _load_schedule_items_ex()
    sched_pairs = _filter_today_items(sched_items, day) if sched_ok else []
    sched_lines = [f"· {(t + ' ') if t else ''}{title}" for t, title in sched_pairs]

    objs = _fetch_gm_direct_objectives(day) or []
    top_objs = sorted(objs, key=lambda o: -(o.get('progress') or 0))[:3]
    plan_lines = [f"· {str(o.get('title', '')).replace(' (GM 직접)', '')} — {o.get('progress', 0)}%"
                  for o in top_objs]

    snap = {
        'done': [{'item': x['item'], 'result': x['result']} for x in done],
        'pending': [{'item': x['item']} for x in pending],
        'sched_lines': sched_lines,
        'plan_lines': plan_lines,
        'filtered': filtered,
        'fallback': fallback,
        'ack': {},
    }
    d['recap'] = snap
    _write(data)
    return snap


def _tomorrow_section(day: str) -> str:
    """🔜 내일 — 저녁 카드 끝에 붙는 내일 일정 리마인드(GM 지시 2026-08-13).
    새 수집 로직 없음(약속 L21) — 아침 브리핑이 쓰는 _load_schedule_items_ex·_filter_today_items를
    날짜만 내일로 바꿔 재사용한다. 최대 3줄 + 외 N건. 0건이면 통째로 뺀다(빈 제목 금지)."""
    tomorrow = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    items, ok = _load_schedule_items_ex()
    if not ok:
        return '🔜 내일 — 내일 일정을 못 읽었습니다'
    pairs = _filter_today_items(items, tomorrow)
    if not pairs:
        return ''
    lines = [f"· {(t + ' ') if t else ''}{title}" for t, title in pairs[:3]]
    if len(pairs) > 3:
        lines.append(f"외 {len(pairs) - 3}건")
    return '🔜 내일\n' + '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════
# 하루방 v2 (2026-09-01~ · GM 지시 2026-08-29) — 체크인 재알림·아침/마무리/주간 새 틀
# 전부 기존 재료 재사용: 상태는 gm_personal_routine.json 한 곳(새 원장 0), 일정·SSOT·회장님
# 소스는 build_morning_brief 가 쓰던 그 함수들. 발신 규칙 = 12줄 이내·이모지 머리 1개·
# 빈 블록은 「없음」 한 줄·못함/미응답에 잔소리 0.
# ══════════════════════════════════════════════════════════════════════════
V2_CHECKIN_SLOTS = ('morning', 'lunch', 'dinner')   # v2 체크인 3건(간식은 lunch 에 병합)


def _v2_slot_items(slot_id: str) -> list:
    items = list(next(s for s in SLOTS if s[0] == slot_id)[4])
    if slot_id == 'lunch':
        items += list(next(s for s in SLOTS if s[0] == 'snack')[4])
    return items


def note_slot_sent(slot_id: str, day: str | None = None) -> None:
    """v2 재알림 판정용 — 슬롯 카드가 나간 시각을 그 날짜 기록에 남긴다."""
    day = day or today()
    data = load()
    _day(data, day).setdefault('slot_sent', {})[slot_id] = datetime.datetime.now().isoformat(timespec='seconds')
    _write(data)


def slot_followups(now: "datetime.datetime | None" = None) -> list:
    """v2 체크인 후속 판정 — 5분 주기 폴러가 부른다. 반환 [(slot_id, 'remind'|'miss'), …].
    규약(GM 확정): 30분 무응답 → 딱 한 번 재알림 · 그 뒤에도 무응답이면 미응답('M') 기록 후 종료.
    사유를 캐묻지 않는다 — 상태 전이와 기록뿐."""
    now = now or datetime.datetime.now()
    day = now.strftime('%Y-%m-%d')
    data = load()
    d = _day(data, day)
    sent = d.get('slot_sent') or {}
    axes = d.setdefault('axes', {})
    reminded = d.setdefault('slot_reminded', {})
    actions, dirty = [], False
    for sid in V2_CHECKIN_SLOTS:
        ts = sent.get(sid)
        if not ts:
            continue
        try:
            elapsed = (now - datetime.datetime.fromisoformat(ts)).total_seconds() / 60.0
        except Exception:
            continue
        pending = [a for a, _l in _v2_slot_items(sid) if axes.get(a) not in ('O', 'X', 'M')]
        if not pending:
            continue
        if elapsed >= 60 and reminded.get(sid):
            for a in pending:
                axes[a] = 'M'
            dirty = True
            actions.append((sid, 'miss'))
        elif elapsed >= 30 and not reminded.get(sid):
            reminded[sid] = True
            dirty = True
            actions.append((sid, 'remind'))
    if dirty:
        _write(data)
    return actions


def _v2_first_pick(day: str) -> str:
    """08:00 ③ 오늘의 한 건 — 항상 1건. 1순위 = 전날 20:00 이 넘긴 「내일 첫 건」.
    없으면 기한 임박(가까운 순), 같으면 회장님·대표님 보고 건 우선(GM 확정)."""
    tf = (load().get('tomorrow_first') or {})
    if tf.get('date') == day and str(tf.get('text') or '').strip():
        return str(tf['text']).strip()
    ssot = _fetch_gm_ssot_open()
    due_pairs, _rest = _split_by_due(ssot, day) if ssot is not None else ([], [])
    chairman = _fetch_chairman_open() or []
    chair_titles = {it['title'] for it in chairman}
    cands = sorted(((due, str(x.get('업무명', '')).strip()) for x, due in due_pairs if x.get('업무명')),
                   key=lambda p: (p[0], p[1] not in chair_titles))
    if cands:
        due, title = cands[0]
        return f"{title} ({_due_label(due, day)})"
    if chairman:
        return f"{chairman[0]['title']} — 회장님 보고 대기"
    return '없음'


def _morning_brief_v2(day: str) -> str:
    """v2 08:00 「하루의 시작」 — ①오늘 일정 ②보고할 것/받을 것 ③오늘의 한 건. 12줄 이내."""
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]
    items, ok = _load_schedule_items_ex()
    pairs = _filter_today_items(items, day) if ok else []
    lines = [f"🧭 하루의 시작 — {d.month}/{d.day}({wd})"]
    if pairs:
        lines.append("① 오늘 일정")
        lines += [f"· {(t + ' ') if t else ''}{title}" for t, title in pairs[:3]]
        if len(pairs) > 3:
            lines.append(f"· 외 {len(pairs) - 3}건")
    else:
        lines.append("① 오늘 일정 없음" if ok else "① 오늘 일정 (못 읽음 — 재확인)")
    ssot = _fetch_gm_ssot_open()
    due_pairs, ssot_rest = _split_by_due(ssot, day) if ssot is not None else ([], [])
    chairman = _fetch_chairman_open()
    report = [f"{x.get('업무명', '')} ({_due_label(due, day)})" for x, due in due_pairs[:2]]
    receive = [f"{it['title']} — 회장님 보고 대기" for it in (chairman or [])[:1]]
    receive += [f"{x.get('업무명', '')} — {x.get('상태', '')}" for x in ssot_rest[:1]]
    lines.append("② 보고할 것 / 받을 것")
    lines.append("· 보고: " + (" · ".join(report) if report else "없음"))
    lines.append("· 받을 것: " + (" · ".join(v for v in receive if v.strip(' —')) or "없음"))
    lines.append("③ 오늘의 한 건")
    lines.append(f"· {_v2_first_pick(day)}")
    out = lines[:12]
    # 오늘의 문장·아이디어는 12줄 상한 밖에 붙인다 — GM 지시 2026-08-30
    # ("쌓아둔 건 다 보고 싶다" · 문장은 체화할 때까지 매일 같은 자리).
    creed = _creed_section()
    if creed:
        out.insert(1, creed)
    idea = _idea_section()
    if idea:
        out.append(idea)
    return '\n'.join(out)


def _evening_recap_v2(day: str) -> dict:
    """v2 20:00 「하루의 마무리」 — 끝낸 것·남은 것·내일 첫 건. 버튼 없음(체크인은 3건뿐).
    「내일 첫 건」은 다음 날 08:00 ③의 1순위 후보로 저장한다(같은 파일 · 새 원장 0)."""
    snap = _recap_snapshot(day)
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]
    done = snap.get('done') or []
    pending = snap.get('pending') or []
    lines = [f"🌙 하루의 마무리 — {d.month}/{d.day}({wd})"]
    lines.append(f"끝낸 것 {len(done)}건" if done else "끝낸 것 없음")
    if done:
        lines.append("· " + " · ".join(x['item'][:24] for x in done[:3]))
    lines.append(f"남은 것 {len(pending)}건" if pending else "남은 것 없음")
    if pending:
        lines.append("· " + " · ".join(x['item'][:24] for x in pending[:2]))
    tomorrow = (d + datetime.timedelta(days=1)).isoformat()
    first = pending[0]['item'] if pending else ''
    if not first:
        tpairs = _filter_today_items(_load_schedule_items_ex()[0], tomorrow)
        first = (f"{tpairs[0][0]} {tpairs[0][1]}".strip() if tpairs else '')
    lines.append("내일 첫 건")
    lines.append(f"· {first}" if first else "· 없음")
    data = load()
    data['tomorrow_first'] = {'date': tomorrow, 'text': first}
    _write(data)
    return {'text': '\n'.join(lines[:12]), 'markup': None}


def _week_card_v2(day: str) -> str:
    """v2 일요일 21:10 주간 루틴 리포트 — 체크인 기록 집계만. 재질문 0 · 잔소리 0."""
    end = datetime.date.fromisoformat(day)
    days = (load().get('days') or {})
    labels = {a: l.lstrip('🍚🏃 ').strip() for s in SLOTS for a, l in s[4]}
    cnt = {a: 0 for a in labels}
    missed = 0
    for i in range(6, -1, -1):
        rec = days.get((end - datetime.timedelta(days=i)).isoformat()) or {}
        ax = rec.get('axes') or {}
        for a in cnt:
            if ax.get(a) == 'O':
                cnt[a] += 1
            elif ax.get(a) == 'M':
                missed += 1
    start = end - datetime.timedelta(days=6)
    meals = " · ".join(f"{labels[a]} {cnt[a]}/7" for a in _MEAL_AXES if a in cnt)
    exs = " · ".join(f"{labels[a]} {cnt[a]}/7" for a in _EX_AXES if a in cnt)
    return (f"📋 한 주 루틴 — {start.month}/{start.day}(월)~{end.month}/{end.day}(일)\n"
            f"{meals}\n{exs}\n미응답 {missed}회\n"
            f"기록은 자율현황 루틴 탭에 있습니다.")


def _selfcheck_haru_v2() -> None:
    """v2 규약 자체 점검 — 병합·버튼·후속 상태 전이·12줄 상한."""
    items = _v2_slot_items('lunch')
    assert any(a == 'snack' for a, _l in items), '간식 축이 13:30에 병합돼야 한다'
    assert [s for s in V2_CHECKIN_SLOTS] == ['morning', 'lunch', 'dinner'], '체크인은 3건'
    now = datetime.datetime.now()
    day = now.strftime('%Y-%m-%d')
    data = load()
    d = _day(data, day)
    bak = {k: d.get(k) for k in ('slot_sent', 'slot_reminded', 'axes')}
    try:
        d['slot_sent'] = {'morning': (now - datetime.timedelta(minutes=31)).isoformat(timespec='seconds')}
        d['slot_reminded'] = {}
        d['axes'] = {}
        _write(data)
        acts = slot_followups(now)
        assert ('morning', 'remind') in acts, f'30분 무응답 → 재알림 1회: {acts}'
        acts2 = slot_followups(now)
        assert not acts2, f'재알림은 딱 한 번: {acts2}'
        acts3 = slot_followups(now + datetime.timedelta(minutes=31))
        assert ('morning', 'miss') in acts3, f'재알림 뒤 무응답 → 미응답 확정: {acts3}'
        ax = _day(load(), day).get('axes') or {}
        assert ax.get('meal_breakfast') == 'M' and ax.get('morning_ex') == 'M', '미응답 M 기록'
    finally:
        data = load()
        d = _day(data, day)
        for k, v in bak.items():
            if v is None:
                d.pop(k, None)
            else:
                d[k] = v
        _write(data)
    print('[selfcheck] haru_v2 OK — 병합·재알림 1회·M 기록')


def build_evening_recap(day: str | None = None) -> dict:
    """20:30 저녁 정리 카드 — {'text', 'markup'}. 08:00 업무 브리핑의 짝(할 일 ↔ 한 일)."""
    day = day or today()
    if haru_v2(day):
        return _evening_recap_v2(day)
    snap = _recap_snapshot(day)
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]
    ack = snap.get('ack') or {}

    lines = [f"🌙 오늘 하신 일  ·  {d.month}월 {d.day}일({wd})"]

    done_lines = [f"✅ {x['item']} — {x['result']}" if x['result'] else f"✅ {x['item']}"
                  for x in snap['done']]
    b = _bucket('끝낸 것', done_lines)
    if b:
        lines += ['', b]

    pending = snap['pending']
    if pending:
        p_lines = [f"{'✅' if ack.get(str(i)) else '⬜'} {x['item']} — 아직 진행 중"
                   for i, x in enumerate(pending)]
        shown = p_lines[:RECAP_MAX_BUTTONS]
        tail = f"\n외 {len(p_lines) - RECAP_MAX_BUTTONS}건" if len(p_lines) > RECAP_MAX_BUTTONS else ''
        lines += ['', f"■ 아직 남은 것 ({len(p_lines)})\n" + '\n'.join(shown) + tail]

    # [2026-08-29 GM 지시 · 텔레그램 중복 정리] 「오늘 일정」 절 삭제 — 같은 일정이 하루
    # 다섯 번 나열됐다. 일정 나열은 08시 아침 브리핑 한 곳. 내일 일정(_tomorrow_section)은
    # 성격이 달라(하루 마무리에서 내일 준비) 그대로 둔다. snap['sched_lines'] 는 다른
    # 소비자(스냅샷 파일)가 있어 데이터는 그대로 만든다 — 여기 표시만 뺀다.

    b = _bucket('진행 중 과제', snap['plan_lines'])
    if b:
        lines += ['', b]

    lines += ['', '오늘 하루도 고생 많으셨습니다 — 남은 건 편하실 때 확인 버튼으로 지워 주세요.']
    if snap.get('fallback'):
        lines += ['', '(정리 기준 확인 필요)']

    tomorrow_section = _tomorrow_section(day)
    if tomorrow_section:
        lines += ['', tomorrow_section]

    rows = [[{'text': f'☑ {i + 1}번 확인', 'callback_data': f'ck:r:{i}'}]
            for i, x in enumerate(pending[:RECAP_MAX_BUTTONS]) if not ack.get(str(i))]
    return {'text': '\n'.join(lines), 'markup': {'inline_keyboard': rows} if rows else None}


def ack_recap_item(idx: int, day: str | None = None) -> dict:
    """저녁 정리 카드의 「☑ N번 확인」 버튼 — 기존 상태 파일(gm_personal_routine.json)에 키만 얹는다."""
    day = day or today()
    data = load()
    d = _day(data, day)
    recap = d.get('recap')
    if not recap:
        return {'text': '', 'markup': None}
    recap.setdefault('ack', {})[str(idx)] = True
    _write(data)
    return build_evening_recap(day)


def _selfcheck_recap() -> None:
    """배 — 노이즈 필터(ref 기준)·ref 짝짓기·연속중복·폴백안전장치·버튼 인덱스 self-check(고정 표본)."""
    assert _recap_noise({'ref': 'GM-20260810-1001', 'detail': '받음 · 자동 접수(UserPromptSubmit)'}) is True
    assert _recap_noise({'ref': 'GM-20260810-03', 'detail': '받음'}) is False  # 두 자리 = 웰리 직접 기록
    assert _recap_noise({'ref': 'GM-20260810-01', 'detail': '받음 · 자동 접수(어떤 이유로든)'}) is True  # detail 규칙
    assert _recap_noise({'ref': 'CEO-morning-01', 'detail': ''}) is False  # GM-YYYYMMDD-NN 형식 아니면 그대로

    sample = [
        {'ts': '2026-08-10T09:00:00+09:00', 'result': 'warn', 'ref': 'GM-20260810-03', 'event': '테스트 지시사항 접수 항목 A'},
        {'ts': '2026-08-10T09:05:00+09:00', 'result': 'ok', 'ref': 'GM-20260810-03', 'event': '완료', 'detail': 'A 처리 결과 요약'},
        {'ts': '2026-08-10T09:10:00+09:00', 'result': 'warn', 'ref': 'GM-20260810-04', 'event': '테스트 지시사항 접수 항목 B'},
        {'ts': '2026-08-10T09:11:00+09:00', 'result': 'warn', 'ref': 'GM-20260810-05', 'event': '테스트 지시사항 접수 항목 B'},  # 연속중복
        {'ts': '2026-08-10T09:12:00+09:00', 'result': 'warn', 'ref': 'GM-20260810-1006', 'event': '실제로는 긴 자동접수 원문이 여기 들어온다',
         'detail': '받음 · 자동 접수(UserPromptSubmit)'},  # 네 자리 ref → 제외 대상
    ]
    global _load_today_gm_worklog
    _orig = _load_today_gm_worklog
    _load_today_gm_worklog = lambda day: sample
    try:
        done, pending, filtered, fallback = _build_done_pending('2026-08-10')
    finally:
        _load_today_gm_worklog = _orig
    assert [x['item'] for x in done] == ['테스트 지시사항 접수 항목 A'], done
    assert done[0]['result'] == 'A 처리 결과 요약', done
    assert [x['item'] for x in pending] == ['테스트 지시사항 접수 항목 B'], pending
    assert filtered == 2, filtered  # 연속중복 1 + 네 자리 ref 노이즈 1
    assert fallback is False, fallback
    # 세 자리 이상 ref(자동 접수 원문)를 가진 항목이 결과 목록에 하나도 없을 것
    assert not any('긴 자동접수 원문' in x['item'] for x in done + pending), (done, pending)

    # ★안전장치 — 전부 자동 접수뿐이면(끝낸 것·남은 것 둘 다 0건) 레거시 필터로 폴백해야 한다
    all_noise = [
        {'ts': '2026-08-10T09:00:00+09:00', 'result': 'warn', 'ref': 'GM-20260810-2001',
         'event': '오넛티 추석 단체 할인 기준 명확화 — 소비자가 기준 30% 확정', 'detail': '받음 · 자동 접수(UserPromptSubmit)'},
    ]
    _load_today_gm_worklog = lambda day: all_noise
    try:
        done2, pending2, _, fallback2 = _build_done_pending('2026-08-10')
    finally:
        _load_today_gm_worklog = _orig
    assert fallback2 is True, (done2, pending2, fallback2)
    assert [x['item'] for x in pending2] == ['오넛티 추석 단체 할인 기준 명확화 — 소비자가 기준 30% 확정'], pending2


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # 💡 아이디어 쌓기 (GM 지시 2026-08-30) — 하루 공지에 그날부터 함께 나간다.
    #   담기 : python scripts/gm_checkin.py --idea "회의 때 쓸 음성 웰리"
    #   보기 : python scripts/gm_checkin.py --ideas
    #   닫기 : python scripts/gm_checkin.py --idea-done 1
    # 📖 오늘의 문장 (GM 지시 2026-08-30) — 체화할 때까지 같은 문장이 매일 아침 뜬다.
    #   담기 : python scripts/gm_checkin.py --creed-add "문장" [출처]
    #   보기 : python scripts/gm_checkin.py --creed
    #   넘기기: python scripts/gm_checkin.py --creed-next     (체화됐을 때만)
    if len(sys.argv) > 1 and sys.argv[1] in ('--creed', '--creed-add', '--creed-next'):
        cmd = sys.argv[1]
        if cmd == '--creed':
            t, src, days = creed_today()
            print(f"📖 오늘의 문장 ({days}일째)\n「{t}」" + (f" — {src}" if src else '') if t
                  else '아직 담긴 문장이 없습니다.')
        elif cmd == '--creed-add':
            print('담았습니다.' if creed_add(sys.argv[2] if len(sys.argv) > 2 else '',
                                          sys.argv[3] if len(sys.argv) > 3 else '')
                  else '이미 있거나 내용이 비었습니다.')
        else:
            nxt = creed_next()
            print(f"다음 문장으로 넘겼습니다.\n「{nxt}」" if nxt else '담긴 문장이 없습니다.')
        raise SystemExit(0)

    if len(sys.argv) > 1 and sys.argv[1] in ('--idea', '--ideas', '--idea-done'):
        cmd = sys.argv[1]
        if cmd == '--ideas':
            items = open_ideas()
            print(f"💡 쌓아둔 아이디어 {len(items)}건")
            for n, i in enumerate(items, 1):
                print(f"{n}. {i['text']} ({i['t']})")
        elif cmd == '--idea':
            print('담았습니다.' if add_idea(' '.join(sys.argv[2:])) else '이미 있거나 내용이 비었습니다.')
        else:
            print('닫았습니다.' if mark_idea_done(' '.join(sys.argv[2:])) else '못 찾았습니다.')
        raise SystemExit(0)

    _selfcheck_slots()
    _selfcheck_schedule()
    _selfcheck_morning_brief()
    _selfcheck_recap()
    print(build_prompt())
    print(json.dumps(build_markup(), ensure_ascii=False))
    print('---')
    print(week_card())
    print('---')
    print(build_morning_brief())
    print('---')
    print(build_evening_recap())
