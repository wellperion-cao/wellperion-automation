# -*- coding: utf-8 -*-
"""1회용 — Survey.js에서 intake_submit 액션이 실제로 쓰는 top-level 함수/상수만
   의존성 폐포(closure)로 뽑아 별도 파일로 만든다. ponytail: 수작업 추적 대신
   식별자 스캔 자동화 — 11,236줄에서 손으로 그레핑하면 놓치는 게 나온다.
"""
import re
import sys

SRC = ".deploy-funnel-v2/Survey.js"
with open(SRC, encoding="utf-8") as f:
    text = f.read()

# ── 1) top-level 선언 스팬을 찾는다 (function NAME(...) {...} / var|const|let NAME = ...;) ──
def find_matching_brace(s, start):
    # start = index of '{'
    depth = 0
    i = start
    in_str = None
    while i < len(s):
        c = s[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in ('"', "'", '`'):
            in_str = c
        elif c == '/' and i + 1 < len(s) and s[i+1] == '/':
            nl = s.find('\n', i)
            i = nl if nl != -1 else len(s)
            continue
        elif c == '/' and i + 1 < len(s) and s[i+1] == '*':
            end = s.find('*/', i + 2)
            i = end + 2 if end != -1 else len(s)
            continue
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1

def find_stmt_end(s, start):
    # start right after '=' ... find top-level ';' respecting braces/brackets/parens/strings
    depth = 0
    i = start
    in_str = None
    while i < len(s):
        c = s[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in ('"', "'", '`'):
            in_str = c
        elif c == '/' and i + 1 < len(s) and s[i+1] == '/':
            nl = s.find('\n', i)
            i = nl if nl != -1 else len(s)
            continue
        elif c == '/' and i + 1 < len(s) and s[i+1] == '*':
            end = s.find('*/', i + 2)
            i = end + 2 if end != -1 else len(s)
            continue
        elif c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return i
        i += 1
    return -1

decls = {}   # name -> (start, end, kind)
order = []

# function NAME(
for m in re.finditer(r'^function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(', text, re.M):
    name = m.group(1)
    brace = text.find('{', m.end())
    if brace == -1:
        continue
    end = find_matching_brace(text, brace)
    if end == -1:
        continue
    decls.setdefault(name, (m.start(), end + 1, 'function'))
    order.append(name)

# var/const/let NAME = ...;
for m in re.finditer(r'^(?:var|const|let)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=', text, re.M):
    name = m.group(1)
    end = find_stmt_end(text, m.end())
    if end == -1:
        continue
    if name not in decls:  # 함수 우선(더 흔함), 없을 때만
        decls[name] = (m.start(), end + 1, 'var')
        order.append(name)

print(f"[info] top-level 선언 {len(decls)}개 인식", file=sys.stderr)

# ── 2) seed: intake_submit 핸들러 블록 + 알려진 진입 헬퍼 ──
seed_names = [
    '_checkSurveyAccess_', '_intakeToken_', '_json', '_notifyTelegram',
]

# intake_submit 핸들러 자체는 named-decl이 아니라 if-block이라 별도로 잘라낸다.
h_start = text.index("if (action === 'intake_submit') {")
brace = text.find('{', h_start)
h_end = find_matching_brace(text, brace)
handler_src = text[h_start:h_end + 1]

def identifiers(s):
    return set(re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*', s))

included = set()
work = list(seed_names) + list(identifiers(handler_src) & set(decls.keys()))
while work:
    name = work.pop()
    if name in included or name not in decls:
        continue
    included.add(name)
    span = text[decls[name][0]:decls[name][1]]
    for ident in identifiers(span):
        if ident in decls and ident not in included:
            work.append(ident)

# 순서 보존(원본 파일 순서), 중복 제거
seen = set()
ordered_included = [n for n in order if n in included and not (n in seen or seen.add(n))]

print(f"[info] 포함 helper {len(ordered_included)}개: {ordered_included}", file=sys.stderr)

out = []
out.append("// ── 자동 추출(closure) — scripts/_extract_intake_closure.py, 2026-08-06 ──\n")
for n in ordered_included:
    s, e, kind = decls[n]
    out.append(text[s:e])
    out.append("\n\n")

out.append("// ── intake_submit 핸들러 본문 ──\n")
out.append(handler_src)
out.append("\n")

with open("scripts/_intake_closure_output.js", "w", encoding="utf-8") as f:
    f.write("".join(out))

print("[done] scripts/_intake_closure_output.js 생성", file=sys.stderr)
