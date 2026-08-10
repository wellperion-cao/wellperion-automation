# -*- coding: utf-8 -*-
"""GAS 사본 축소 차단 가드(배cd2e79cae 재발방지) 자체검사 — 커밋을 만들지 않는다(트리만 만든다)."""
import os, sys, subprocess, tempfile
sys.path.insert(0, 'scripts'); sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import safe_commit as sc

ROOT = Path('.').resolve()

def tree_with_blob(path, content_bytes):
    """path 하나만 주어진 바이트로 바꾼 트리 SHA(나머지는 HEAD 그대로) — 디스크 안 건드림."""
    fd, idx = tempfile.mkstemp(suffix='.idx'); os.close(fd); os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    subprocess.run(['git', 'read-tree', 'HEAD'], cwd=ROOT, env=env, check=True)
    blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=ROOT, input=content_bytes,
                          capture_output=True, check=True).stdout.strip().decode()
    subprocess.run(['git', 'update-index', '--add', '--cacheinfo', '100644', blob, path],
                   cwd=ROOT, env=env, check=True)
    t = subprocess.run(['git', 'write-tree'], cwd=ROOT, env=env,
                       capture_output=True, text=True, check=True).stdout.strip()
    os.unlink(idx)
    return t

head = sc._git_out(['rev-parse', 'HEAD'], ROOT)
head_tree = sc._git_out(['rev-parse', 'HEAD^{tree}'], ROOT)

# 테스트 대상 = .deploy-procurement/procurement.js (CHRO 소유 .deploy-todo 는 절대 안 건드림).
target = '.deploy-procurement/procurement.js'
original = subprocess.run(['git', 'show', f'HEAD:{target}'], cwd=ROOT,
                          capture_output=True, check=True).stdout
assert original.count(b'\n') >= sc.GAS_SHRINK_BLOCK_LINES + 10, f"{target} 이 테스트에 너무 짧습니다"

for k in ('WP_ALLOW_GAS_SHRINK',):
    os.environ.pop(k, None)

# ① 큰 폭 축소(옛 사본으로 덮은 흉내) → 차단돼야 한다
shrunk = b'\n'.join(original.split(b'\n')[:5])
t1 = tree_with_blob(target, shrunk)
pairs1 = sc._tree_diff_status(head_tree, t1, ROOT)
v1 = sc._gas_shrink_violations(head_tree, t1, pairs1, ROOT)
assert v1, "큰 폭 GAS 사본 축소를 못 잡았다"
assert 'GAS 사본 축소 차단' in v1[0]
print("① 큰 폭 축소 차단 OK:", v1[0][:100])

# ② 정상 편집(줄 추가만, 삭제 0) → 통과해야 한다(회귀 확인 — 평범한 수정을 막지 않는다)
appended = original + b'// test comment\n'
t2 = tree_with_blob(target, appended)
pairs2 = sc._tree_diff_status(head_tree, t2, ROOT)
v2 = sc._gas_shrink_violations(head_tree, t2, pairs2, ROOT)
assert not v2, f"줄만 추가한 정상 편집을 막았다: {v2}"
print("② 정상 편집(추가만) 통과 OK")

# ③ 강행 스위치 WP_ALLOW_GAS_SHRINK=1 → 큰 폭 축소도 통과해야 한다(우회 로그는 fail-open)
os.environ['WP_ALLOW_GAS_SHRINK'] = '1'
try:
    v3 = sc._gas_shrink_violations(head_tree, t1, pairs1, ROOT)
finally:
    os.environ.pop('WP_ALLOW_GAS_SHRINK', None)
assert not v3, f"강행 스위치를 켰는데도 막혔다: {v3}"
print("③ 강행 스위치(WP_ALLOW_GAS_SHRINK=1) 통과 OK")

# ④ .deploy- 밖 경로는 대상이 아니다(회귀 — 다른 도메인 파일 정상 수정에 안 끼어든다)
other = 'CLAUDE.md'
other_orig = subprocess.run(['git', 'show', f'HEAD:{other}'], cwd=ROOT,
                            capture_output=True, check=True).stdout
t4 = tree_with_blob(other, other_orig.split(b'\n', 1)[-1])  # 첫 줄만 삭제(작은 수정 1건 흉내)
pairs4 = sc._tree_diff_status(head_tree, t4, ROOT)
v4 = sc._gas_shrink_violations(head_tree, t4, pairs4, ROOT)
assert not v4, f".deploy- 밖 파일까지 잘못 잡았다: {v4}"
print("④ .deploy- 밖 경로 무관 OK")

print("PASS")
