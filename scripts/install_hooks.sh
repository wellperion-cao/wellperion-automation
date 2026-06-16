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
