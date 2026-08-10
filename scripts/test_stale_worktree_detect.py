# -*- coding: utf-8 -*-
"""뒤진 작업본 감지 자체검사 — 실제 커밋을 만들지 않는다(임시 인덱스 트리만 만든다).
_reconcile() 이 HEAD 를 전진시킨 직후 붙인 _detect_stale_worktree_copies() 검사.
"""
import os, sys, subprocess, tempfile
sys.path.insert(0, 'scripts'); sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import post_commit_push as pcp

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


path = 'CLAUDE.md'
# ★디스크 실제 파일은 core.autocrlf=true 때문에 CRLF 로 체크아웃돼 있다(실측).
#   git 저장소 정본(HEAD 블롭)은 LF — 그걸 기준선으로 삼아야 "디스크 vs 새 HEAD"
#   비교가 실제 운영 상황(디스크 CRLF · 블롭 LF)과 같아진다.
baseline = subprocess.run(['git', 'show', f'HEAD:{path}'], cwd=ROOT,
                           capture_output=True, check=True).stdout
old_tree = tree_with_blob(path, baseline)  # 디스크와 (정규화 후) 같은 내용 = "옛 HEAD" 흉내

# ① 진짜 내용이 다른 새 HEAD → 디스크(옛 내용)가 뒤진 작업본으로 잡혀야 한다
new_tree_real = tree_with_blob(path, baseline + b"\n<!-- remote change -->\n")
stale1 = pcp._detect_stale_worktree_copies(str(ROOT), old_tree, new_tree_real)
assert path in stale1, f"뒤진 작업본을 못 잡았다: {stale1}"
print("① 뒤진 작업본 감지 OK:", stale1)

# ② 줄바꿈만 다른 새 HEAD(내용은 같음) → 오탐이면 안 된다
crlf_bytes = baseline.replace(b"\n", b"\r\n")
new_tree_crlf = tree_with_blob(path, crlf_bytes)
stale2 = pcp._detect_stale_worktree_copies(str(ROOT), old_tree, new_tree_crlf)
assert path not in stale2, f"줄바꿈 차이만인데 뒤진 작업본으로 오탐했다: {stale2}"
print("② 줄바꿈 차이 오탐 없음 OK:", stale2)

# ③ 통합 전후로 아무 것도 안 바뀜 → 조용해야 한다
stale3 = pcp._detect_stale_worktree_copies(str(ROOT), old_tree, old_tree)
assert stale3 == [], f"무변경인데 소리가 났다: {stale3}"
print("③ 무변경 무소음 OK")

print("PASS")
