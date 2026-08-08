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
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JPATH = ROOT / 'status' / 'gm_personal_routine.json'

# 생활 토막 → 트래커 축(axes). 정본 = gm_personal_routine.json 의 toroks[].axes 와 같은 매핑.
# 여기서 다시 적는 이유는 버튼 4개로 줄이기 위해서다 — 축 9개를 다 물으면 원래 문제로 돌아간다.
TOROKS = [
    ('self',     '🌱', '나',   ['morning_ex', 'self_dev']),
    ('dad',      '👨‍👧', '아빠', ['evening_run']),
    ('husband',  '💑', '남편', ['family_time']),
    ('work',     '💼', '일',   ['work_focus']),
]
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


def state(day: str | None = None) -> dict:
    """지금 눌려 있는 토막·기분. 버튼 표시에 쓴다."""
    day = day or today()
    d = _day(load(), day)
    axes = d.get('axes') or {}
    on = {tid for tid, _i, _l, keys in TOROKS if all(axes.get(k) == 'O' for k in keys)}
    return {'on': on, 'mood': d.get('mood') or '', 'weight': d.get('weight') or '',
            'sleep': d.get('sleep') or ''}


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


def _write(data: dict) -> None:
    data['updated_at'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    JPATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


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
    line = f"{marks}   담긴 토막 {n}/4"
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


def build_morning(day: str | None = None) -> str:
    """아침 카드 — 오늘 할 네 가지. 버튼 없음, 읽고 지나가면 된다."""
    day = day or today()
    p = plan(day)
    d = datetime.date.fromisoformat(day)
    wd = '월화수목금토일'[d.weekday()]
    lines = [f"🌅 오늘 하나씩 — {d.month}/{d.day}({wd})",
             "네 가지만. 큰 거 아닙니다.", ""]
    for tid, icon, label, _k in TOROKS:
        if p.get(tid):
            lines.append(f"{icon} {label}   {p[tid]}")
    lines += ["", "저녁에 이 네 가지를 그대로 다시 여쭙겠습니다."]
    return '\n'.join(lines)


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
             "아침에 정한 네 가지입니다. 하신 것만 눌러 주세요.", ""]
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
    row1 = [{'text': ('✅' if tid in st['on'] else '') + f'{icon} {label}',
             'callback_data': f'ck:t:{tid}'} for tid, icon, label, _k in TOROKS]
    row2 = [{'text': ('✅' if st['mood'] == m else '') + m,
             'callback_data': f'ck:m:{m}'} for m in MOODS]
    row3 = [{'text': '💾 저장', 'callback_data': 'ck:save'},
            {'text': '오늘은 건너뜀', 'callback_data': 'ck:skip'}]
    return {'inline_keyboard': [row1, row2, row3]}


def week_card(day: str | None = None) -> str:
    """일요일 저녁 한 주 카드 — 지난 7일 도달율. 없는 날은 없다고만 적는다."""
    day = day or today()
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
        head = f"{dt.month}/{dt.day}({wd})  {' '.join(i for _t, i in done) if done else '·'}   {len(done)}/4"
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
              "점수가 아니라 거울입니다 — 비어 있어도 괜찮습니다.")


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print(build_prompt())
    print(json.dumps(build_markup(), ensure_ascii=False))
    print('---')
    print(week_card())
