# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

DEST = r'C:\Users\jjky0\welperion-automation\3. 웰페리온 가이드\coo\check\운영부 체계.html'
with open(DEST, encoding='utf-8') as f:
    src = f.read()

# 잔재 확인
for m in re.finditer('주차관리부', src):
    ctx = src[max(0, m.start()-40):m.start()+60]
    print('POS', m.start(), repr(ctx))

# 핵심 항목 확인
checks = [
    ("document.getElementById('tab-voc')", 'switchTab voc'),
    ('이경연 실장', 'staff'),
    ('OPS_POLICY_BOARD', 'policy key'),
    ('opscheck3_', 'lk key'),
    ('O-A1', 'O-A1 item'),
    ('1FAIpQLSd7mDzTyZT5FSXVcxmpMCaqv7M', 'form url'),
    ('1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ', 'sheet url'),
    ('본에스티스', 'location chip'),
    ('NIGHT_WEEKDAY=[];', 'night cleared'),
]
for needle, label in checks:
    print('OK' if needle in src else 'FAIL', label)

print('total len=', len(src))
