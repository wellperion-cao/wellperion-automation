# -*- coding: utf-8 -*-
"""배421 되돌림 차단 가드 자체검사 — 커밋을 만들지 않는다(임시 인덱스 트리만 만든다)."""
import os, sys, subprocess, tempfile
sys.path.insert(0, 'scripts'); sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import safe_commit as sc

ROOT = Path('.').resolve()

def tree_from_worktree(paths):
    """지정 경로의 '지금 디스크 내용'만 담은 트리 SHA — HEAD 를 바탕으로 얹는다."""
    fd, idx = tempfile.mkstemp(suffix='.idx'); os.close(fd); os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    subprocess.run(['git','read-tree','HEAD'], cwd=ROOT, env=env, check=True)
    subprocess.run(['git','add','--'] + paths, cwd=ROOT, env=env, check=True)
    t = subprocess.run(['git','write-tree'], cwd=ROOT, env=env,
                       capture_output=True, text=True, check=True).stdout.strip()
    os.unlink(idx)
    return t

head = sc._git_out(['rev-parse','HEAD'], ROOT)

# ① 낡은 사본(워크트리가 HEAD 보다 옛것) → 되돌림으로 차단돼야 한다
stale = ['3. 웰페리온 가이드/coo/reception/종합접수처_현황.html']
w, r = sc._detect_concurrent_edit_warnings(stale, ROOT, tree_from_worktree(stale), head)
assert r, "낡은 사본을 되돌림으로 못 잡았다"
print("① 낡은 사본 차단 OK:", r[0][:110])

# ② 내가 방금 고친 파일(HEAD 이후 새 내용) → 차단되면 안 된다
fresh = ['scripts/safe_commit.py']
w2, r2 = sc._detect_concurrent_edit_warnings(fresh, ROOT, tree_from_worktree(fresh), head)
assert not r2, f"정상 편집을 오탐으로 막았다: {r2}"
print("② 정상 편집 통과 OK (경고", len(w2), "건)")

# ③ 변경 없는 파일 → 조용해야 한다
same = ['CLAUDE.md']
w3, r3 = sc._detect_concurrent_edit_warnings(same, ROOT, tree_from_worktree(same), head)
assert not r3 and not w3, f"무변경 파일에서 소리가 났다: {r3} {w3}"
print("③ 무변경 파일 무소음 OK")
print("PASS")
