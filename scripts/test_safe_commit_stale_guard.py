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

def tree_with_blob(path, content_bytes):
    """path 하나만 주어진 바이트로 바꾼 트리 SHA(나머지는 HEAD 그대로) — 디스크 안 건드림."""
    fd, idx = tempfile.mkstemp(suffix='.idx'); os.close(fd); os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    subprocess.run(['git','read-tree','HEAD'], cwd=ROOT, env=env, check=True)
    blob = subprocess.run(['git','hash-object','-w','--stdin'], cwd=ROOT, input=content_bytes,
                          capture_output=True, check=True).stdout.strip().decode()
    subprocess.run(['git','update-index','--add','--cacheinfo','100644', blob, path],
                   cwd=ROOT, env=env, check=True)
    t = subprocess.run(['git','write-tree'], cwd=ROOT, env=env,
                       capture_output=True, text=True, check=True).stdout.strip()
    os.unlink(idx)
    return t

head = sc._git_out(['rev-parse','HEAD'], ROOT)

# ① 낡은 사본(과거 커밋 버전과 바이트가 똑같은 내용을 다시 올림) → 되돌림으로 차단돼야 한다
# ★2026-08-10 시토 — 예전엔 이 파일의 '지금 워크트리' 내용이 실제로 옛 사본이라
#   tree_from_worktree 로도 통과했다(작성 당시 실측 전제). 그런데 그 전제는
#   디스크 상태에 얹혀 있어 나중에 그 파일이 정상 커밋되면(=워크트리가 HEAD와
#   같아지면) 조용히 깨진다 — 실제로 2026-08-10 재실행에서 그렇게 깨진 것을
#   조사로 확인했다(가드 본체 결함이 아니라 이 전제 자체가 낡은 것). 디스크
#   상태에 기대지 않도록 과거 커밋의 blob 을 tree_with_blob 으로 직접 얹어
#   결정론적으로 만든다 — 검사 강도는 그대로(여전히 byte-exact 과거 버전 매칭을
#   요구한다), 전제만 고정한다.
stale = '3. 웰페리온 가이드/coo/reception/종합접수처_현황.html'
_stale_hist = subprocess.run(['git', 'log', '--format=%H', '-5', 'HEAD', '--', stale],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
assert len(_stale_hist) >= 2, f"{stale} 이력이 테스트에 부족합니다(2개 이상 필요)"
_old_content = subprocess.run(['git', 'show', f'{_stale_hist[1]}:{stale}'],
                              cwd=ROOT, capture_output=True, check=True).stdout
w, r = sc._detect_concurrent_edit_warnings([stale], ROOT, tree_with_blob(stale, _old_content), head)
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

# ④ 작은 상태 JSON(status/ 바로 아래·4KB 이하)의 낡은 사본 → 차단이 아니라 경고여야 한다
small_json = 'status/_bridge_last.json'
hist = subprocess.run(['git','log','--format=%H','-5','HEAD','--',small_json],
                      cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
assert len(hist) >= 2, f"{small_json} 이력이 테스트에 부족합니다(2개 이상 필요)"
old_content = subprocess.run(['git','show', f'{hist[1]}:{small_json}'],
                             cwd=ROOT, capture_output=True, check=True).stdout
assert sc._is_small_state_json(small_json, ROOT), f"{small_json} 이 작은 상태 JSON 판정에서 빠졌다"
w4, r4 = sc._detect_concurrent_edit_warnings([small_json], ROOT,
                                             tree_with_blob(small_json, old_content), head)
assert not r4, f"작은 상태 JSON을 차단으로 잡았다(경고여야 함): {r4}"
assert any('[낡은 사본 경고]' in x for x in w4), f"작은 상태 JSON 경고가 안 떴다: {w4}"
print("④ 작은 상태 JSON 경고(차단 아님) OK:", w4[0][:110])
print("PASS")

# ⑤ 도메인 가드 강행 스위치 — 넘을 도메인 이름을 정확히 대야만 열린다(2026-08-06).
#    배경: 그 전엔 SKIP_PHANTOM_DELETE_GUARD 하나가 '지워진 파일 감지'와 '남의 도메인 수정
#    차단'을 같이 열었다. 끄려던 것과 열리는 것이 다르면 그건 우회로다 — 실제로 실행 레인이
#    인쇄 CSS 를 고치다 막히자 그 값을 켜서 시로(나우열M 라인) 가드를 그 자리에서 통과했다.
_chro = sorted(sc.CHRO_DOMAIN_PATHS)[0]
_pairs = [('M', _chro)]

def _blocked(env):
    for k in ('WP_DOMAIN_FORCE', 'SKIP_PHANTOM_DELETE_GUARD'):
        os.environ.pop(k, None)
    os.environ.update(env or {})
    try:
        return sc._domain_modify_violation(
            _pairs, "CHRO(시로)", "나우열M", sc.CHRO_DOMAIN_PATHS, "★중간관리자", None, ROOT) is not None
    finally:
        for k in ('WP_DOMAIN_FORCE', 'SKIP_PHANTOM_DELETE_GUARD'):
            os.environ.pop(k, None)

assert _blocked(None), "스위치 없이 남의 도메인이 통과했다"
assert _blocked({'SKIP_PHANTOM_DELETE_GUARD': '1'}), "옛 스위치가 아직 도메인 가드를 연다"
assert _blocked({'WP_DOMAIN_FORCE': 'COO'}), "다른 도메인 이름으로 열렸다"
assert not _blocked({'WP_DOMAIN_FORCE': 'CHRO'}), "이름을 정확히 댔는데 안 열렸다"
print("⑤ 도메인 강행은 이름을 대야만 열림 OK")
