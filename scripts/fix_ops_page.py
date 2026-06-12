# -*- coding: utf-8 -*-
"""운영부 체계.html — switchTab voc 추가 + 주차관리부 잔재 교체"""
import re, sys

DEST = r'C:\Users\jjky0\welperion-automation\3. 웰페리온 가이드\coo\check\운영부 체계.html'

with open(DEST, encoding='utf-8') as f:
    src = f.read()

# 1. switchTab에 tab-voc 추가 (아직 없으면)
voc_line = "document.getElementById('tab-voc').classList.toggle('hidden',tab!=='voc');"
guide_line = "document.getElementById('tab-guide').classList.toggle('hidden',tab!=='guide');"
if voc_line not in src:
    assert guide_line in src, 'guide toggle not found'
    src = src.replace(guide_line,
                      voc_line + '\n  ' + guide_line, 1)
    print('switchTab voc added')
else:
    print('switchTab voc already present')

# 2. 주차관리부 잔재 교체
replacements = [
    # 헤더 시트 링크 title 속성
    ('title="주차관리부 전용 시트 연동 예정"', 'title="운영부 전용 시트 연동 예정"'),
    # copyReport/copyShare 함수 내 문자열
    ('[주차관리부 체계 점검', '[운영부 체계 점검'),
    ('주차관리부 체계 점검', '운영부 체계 점검'),
    # 남은 일반 텍스트
    ('주차관리부 체계', '운영부 체계'),
]
for old, new in replacements:
    count = src.count(old)
    if count:
        src = src.replace(old, new)
        print(f'replaced {count}x: {repr(old[:40])}')

# 잔재 확인
remaining = len(re.findall('주차관리부', src))
print('remaining 주차관리부:', remaining)
if remaining:
    for m in re.finditer('주차관리부', src):
        ctx = src[max(0, m.start()-20):m.start()+30]
        print('  ', repr(ctx))

with open(DEST, 'w', encoding='utf-8') as f:
    f.write(src)
print('written, len=', len(src))
