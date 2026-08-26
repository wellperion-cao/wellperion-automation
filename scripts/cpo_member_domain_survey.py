# -*- coding: utf-8 -*-
"""회원 도메인 6벌 원장 현행 실측 — 이행 설계 재료(2026-08-26 시포)."""
import json, collections, os, sys, time
import requests

sys.stdout.reconfigure(encoding='utf-8')

U = ('https://script.google.com/macros/s/'
     'AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec')
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'status', 'member_domain_survey.json')


def get(params, timeout=200):
    t = time.time()
    r = requests.get(U, params=params, timeout=timeout)
    try:
        d = r.json()
    except Exception:
        return None, time.time() - t, 'HTTP %s / 비JSON' % r.status_code
    return d, time.time() - t, None


def norm(p):
    return str(p or '').replace('-', '').replace(' ', '').strip()


report = {}

MEMBER_SCOPES = [('valid', '유효회원'), ('ended', '종료회원'), ('corp', '법인회원'), ('archive', 'LOSS보관')]
ledgers = {}
for scope, label in MEMBER_SCOPES:
    d, el, err = get({'action': 'member_active_list', 'scope': scope, 'nc': '1'})
    rows = (d or {}).get('data') or []
    ledgers[scope] = rows
    cols = list(rows[0].keys()) if rows else []
    report[label] = {
        'scope': scope, '행수': len(rows), '조회초': round(el, 1), '오류': err,
        '칸': [c.replace('\n', '\\n') for c in cols],
    }

d, el, err = get({'action': 'member_inquiry_list', 'scope': 'all', 'nc': '1'})
inq = (d or {}).get('data') or []
report['멤버십문의'] = {'행수': len(inq), '조회초': round(el, 1), '오류': err,
                    '칸': list(inq[0].keys()) if inq else [],
                    '상태값': dict(collections.Counter(str(r.get('status') or '(빈칸)') for r in inq))}

lessons = {}
for t_ in ('성인강습', '유소년강습'):
    d, el, err = get({'action': 'lesson_inquiry_list', 'type': t_, 'scope': 'all', 'nc': '1'})
    rows = (d or {}).get('data') or []
    lessons[t_] = rows
    report['강습문의_' + t_] = {'행수': len(rows), '조회초': round(el, 1), '오류': err,
                             '칸': list(rows[0].keys()) if rows else [],
                             '상태값': dict(collections.Counter(str(r.get('status') or '(빈칸)') for r in rows))}

# ── 같은 사람이 몇 벌에 걸쳐 있나 (전화 기준) ──
phone_map = collections.defaultdict(set)
name_by_phone = collections.defaultdict(set)
for scope, label in MEMBER_SCOPES:
    for r in ledgers[scope]:
        p = norm(r.get('휴대폰 번호') or r.get('휴대폰'))
        if p and p != '0':
            phone_map[p].add(label)
            name_by_phone[p].add(str(r.get('회원명') or '').strip())
for r in inq:
    p = norm(r.get('phone'))
    if p and p != '0':
        phone_map[p].add('멤버십문의')
        name_by_phone[p].add(str(r.get('name') or '').strip())
for t_, rows in lessons.items():
    for r in rows:
        p = norm(r.get('phone'))
        if p and p != '0':
            phone_map[p].add('강습문의')
            name_by_phone[p].add(str(r.get('name') or '').strip())

spread = collections.Counter(len(v) for v in phone_map.values())
report['_사람하나가_걸친_원장수'] = {str(k): v for k, v in sorted(spread.items())}
report['_전화_고유수'] = len(phone_map)

# 같은 전화에 이름이 여러 개(가족 공유번호·양도) — 사람 식별이 전화로 안 되는 실측
multi_name = {p: sorted(n for n in ns if n) for p, ns in name_by_phone.items() if len({n for n in ns if n}) > 1}
report['_같은전화_다른이름_건수'] = len(multi_name)
report['_같은전화_다른이름_예시'] = dict(list(multi_name.items())[:12])

# 원장 간 중복(같은 사람이 두 회원 원장에 동시에)
dup = []
for p, labels in phone_map.items():
    mem = labels & {'유효회원', '종료회원', '법인회원', 'LOSS보관'}
    if len(mem) > 1:
        dup.append({'전화뒤4': p[-4:], '이름': sorted(n for n in name_by_phone[p] if n), '원장': sorted(mem)})
report['_회원원장_중복_건수'] = len(dup)
report['_회원원장_중복'] = dup

# 등록완료(SUC)인데 회원 원장에 없는 사람
member_phones = set()
for scope in ('valid', 'ended', 'corp'):
    for r in ledgers[scope]:
        p = norm(r.get('휴대폰 번호'))
        if p:
            member_phones.add(p)
suc_missing = [r for r in inq if str(r.get('status')) in ('SUC', '단기SUC') and norm(r.get('phone')) and norm(r.get('phone')) not in member_phones]
report['_멤버십_등록완료인데_원장에없음'] = len(suc_missing)
report['_멤버십_등록완료_총'] = len([r for r in inq if str(r.get('status')) in ('SUC', '단기SUC')])

# 강습 등록완료인데 등록일 빈칸
for t_, rows in lessons.items():
    suc = [r for r in rows if str(r.get('status')) in ('SUC', '단기SUC')]
    filled = [r for r in suc if str(r.get('regDate') or '').strip()]
    report['강습문의_' + t_]['등록완료'] = len(suc)
    report['강습문의_' + t_]['등록완료_등록일있음'] = len(filled)

# 같은 사람 문의가 몇 줄로 갈라지나(강습 종목별 분할 실측)
lesson_rows_per_phone = collections.Counter()
for t_, rows in lessons.items():
    for r in rows:
        p = norm(r.get('phone'))
        if p:
            lesson_rows_per_phone[p] += 1
buckets = collections.Counter()
for p, n in lesson_rows_per_phone.items():
    buckets['1줄' if n == 1 else ('2~4줄' if n <= 4 else ('5~9줄' if n <= 9 else '10줄+'))] += 1
report['_강습_한사람당_줄수'] = dict(buckets)
report['_강습_최다줄'] = max(lesson_rows_per_phone.values()) if lesson_rows_per_phone else 0

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in report.items() if not k.startswith('_회원원장_중복')}, ensure_ascii=False, indent=1)[:6000])
print('\n저장:', OUT)
