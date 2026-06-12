# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

DEST = r'C:\Users\jjky0\welperion-automation\3. 웰페리온 가이드\coo\check\운영부 체계.html'
with open(DEST, encoding='utf-8') as f:
    src = f.read()

fixes = [
    # 헤더 시트 링크 title
    ('title="주차관리부 전용 시트 연동 예정"',
     'title="운영부 전용 시트 연동 예정"'),
    # submitShift toast msg
    ('[주차관리부 체계 점검 ', '[운영부 체계 점검 '),
    # copyReport 함수 (2곳: 휴관일 + 보고 시작)
    ('주차관리부 체계 일일 점검 보고', '운영부 체계 일일 점검 보고'),
    # JS 주석 (규정 트렐로 보드)
    ('주차관리부 규정 트렐로 보드 (규정 탭)', '운영부 규정 트렐로 보드 (규정 탭)'),
    # 혹시 남은 것
    ('주차관리부', '운영부'),
]
for old, new in fixes:
    cnt = src.count(old)
    if cnt:
        src = src.replace(old, new)
        print(f'replaced {cnt}x: {old[:50]}')

# switchTab voc
voc_line  = "document.getElementById('tab-voc').classList.toggle('hidden',tab!=='voc');"
guide_line = "document.getElementById('tab-guide').classList.toggle('hidden',tab!=='guide');"
if voc_line not in src:
    assert guide_line in src, 'guide toggle line not found'
    src = src.replace(guide_line, voc_line + '\n  ' + guide_line, 1)
    print('switchTab voc injected')
else:
    print('switchTab voc already present')

with open(DEST, 'w', encoding='utf-8') as f:
    f.write(src)
print('written, len=', len(src))

# 최종 잔재 확인
import re
remaining = list(re.finditer('주차관리부', src))
print('remaining 주차관리부:', len(remaining))
for m in remaining:
    print('  POS', m.start(), repr(src[max(0,m.start()-20):m.start()+40]))
