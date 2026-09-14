#!/bin/sh
# install_hooks.sh
# 웰페리온 git hooks 설치 스크립트
# 실행: sh scripts/install_hooks.sh  (repo root 기준)
# Windows Git Bash 또는 Git for Windows sh 환경에서 실행

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SCRIPTS_DIR="$REPO_ROOT/scripts"

echo "[install_hooks] hooks 설치 시작 → $HOOKS_DIR"

# pre-commit hook 복사 + 실행권한
cp "$SCRIPTS_DIR/pre-commit.hook" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"

echo "[install_hooks] pre-commit hook 설치 완료."
echo "[install_hooks] 확인: $HOOKS_DIR/pre-commit"

# post-commit hook 복사 + 실행권한 (커밋 직후 origin 자동 push · INC-006)
cp "$SCRIPTS_DIR/post-commit.hook" "$HOOKS_DIR/post-commit"
chmod +x "$HOOKS_DIR/post-commit"

echo "[install_hooks] post-commit hook 설치 완료."
echo "[install_hooks] 확인: $HOOKS_DIR/post-commit"

# pre-push hook 복사 + 실행권한 (🔒 자물쇠 라인 · 배1098 · 2026-09-07)
cp "$SCRIPTS_DIR/pre-push.hook" "$HOOKS_DIR/pre-push"
chmod +x "$HOOKS_DIR/pre-push"

echo "[install_hooks] pre-push hook 설치 완료."
echo "[install_hooks] 확인: $HOOKS_DIR/pre-push"

# _queue.json 전용 머지 드라이버 등록 (.gitattributes 의 merge=queuejson 와 짝)
#   여러 세션이 각자 '배'를 추가해도 task_id 합집합으로 자동 병합 → rebase 충돌·자동push 실패 근본차단(2026-06-19 시토)
git config merge.queuejson.name "_queue.json task_id union merge (CTO)"
# 파이썬 고르기 — 나우열M PC 는 `python` 이 스토어 스텁(문구만 찍고 안 돔)이라 실제로 도는 것을 시험해 고른다(2026-09-14 CFO 발견).
if python -c "import sys" >/dev/null 2>&1; then PYBIN=python
elif py -3 -c "import sys" >/dev/null 2>&1; then PYBIN="py -3"
else PYBIN=python3; fi
git config merge.queuejson.driver "$PYBIN scripts/git_merge_queue.py %O %A %B"
echo "[install_hooks] _queue.json 머지 드라이버 등록 완료 (merge.queuejson)."

# pre-commit 가 호출하는 보조 스크립트 존재 확인 (별도 설치 불필요 — 경로참조)
if [ -f "$SCRIPTS_DIR/sync_queue_mirror.py" ]; then
  echo "[install_hooks] _queue 미러 동기화 스크립트 확인: sync_queue_mirror.py (pre-commit 단계 ①-3)"
else
  echo "[install_hooks][WARN] sync_queue_mirror.py 없음 — G1 _queue 미러 동기화가 동작하지 않습니다."
fi
