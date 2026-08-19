# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

filtered = [{'rowIndex': 730, 'name': '이상준'}]
extra_from_valid = [{'rowIndex': 730, 'name': '이상준'}, {'rowIndex': 200, 'name': '홍길동'}]

before = filtered + extra_from_valid
print('수정 전:', [r['name'] for r in before], '→ 이상준', sum(1 for r in before if r['name'] == '이상준'), '건')

seen = set(r['rowIndex'] for r in filtered)
extra_deduped = [r for r in extra_from_valid if r['rowIndex'] not in seen]
after = filtered + extra_deduped
print('수정 후:', [r['name'] for r in after], '→ 이상준', sum(1 for r in after if r['name'] == '이상준'), '건')

assert sum(1 for r in after if r['name'] == '이상준') == 1, '중복 제거 실패'
assert any(r['name'] == '홍길동' for r in after), '다른 회원 누락'
print('PASS — 이상준 중복 제거 OK, 홍길동 정상 포함 OK')
