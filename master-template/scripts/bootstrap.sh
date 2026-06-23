#!/usr/bin/env bash
# bootstrap.sh — 마스터 템플릿 초기화 스크립트 (Linux/Mac)
# 용도: 새 프로젝트에 복붙 후 state 폴더 초기화, 필수 파일 존재 확인, 체크리스트 출력
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 마스터 템플릿 부트스트랩 ==="
echo "루트: $ROOT_DIR"
echo ""

# 1. 필수 파일 존재 확인
REQUIRED_FILES=(
  "README.md"
  "AGENTS.md"
  "CLAUDE.md"
  "ssot/약속.json"
  "ssot/incidents.json"
  "ssot/canon.json"
  "state/_queue.json"
  "loop/swarm-loop.md"
  "loop/quality-gates.md"
)

MISSING=0
echo "[1/4] 필수 파일 확인..."
for f in "${REQUIRED_FILES[@]}"; do
  if [ -f "$ROOT_DIR/$f" ]; then
    echo "  OK  $f"
  else
    echo "  MISSING  $f"
    MISSING=$((MISSING + 1))
  fi
done

if [ "$MISSING" -gt 0 ]; then
  echo ""
  echo "ERROR: 필수 파일 ${MISSING}개 누락. 템플릿이 완전히 복사되었는지 확인하세요."
  exit 1
fi

# 2. [[REPLACE_ME]] 플레이스홀더 확인
echo ""
echo "[2/4] 플레이스홀더 확인 (canon.json)..."
PLACEHOLDER_COUNT=$(grep -c "\[\[REPLACE_ME\]\]" "$ROOT_DIR/ssot/canon.json" 2>/dev/null || echo "0")
if [ "$PLACEHOLDER_COUNT" -gt 0 ]; then
  echo "  WARNING: canon.json에 [[REPLACE_ME]] 플레이스홀더 ${PLACEHOLDER_COUNT}개 남음"
  echo "  → ssot/canon.json을 열어 실제 프로젝트 값으로 교체하세요"
else
  echo "  OK  플레이스홀더 없음"
fi

# 3. state/memory 폴더 초기화
echo ""
echo "[3/4] state/memory 폴더 초기화..."
mkdir -p "$ROOT_DIR/state/memory"
if [ ! -f "$ROOT_DIR/state/memory/MEMORY.md" ]; then
  echo "# 영구 메모리 인덱스" > "$ROOT_DIR/state/memory/MEMORY.md"
  echo "" >> "$ROOT_DIR/state/memory/MEMORY.md"
  echo "형식: - [제목](파일명.md) — 한 줄 요약" >> "$ROOT_DIR/state/memory/MEMORY.md"
  echo "  생성됨: state/memory/MEMORY.md"
else
  echo "  OK  MEMORY.md 이미 존재"
fi

# 4. 다음 체크리스트 출력
echo ""
echo "[4/4] 시작 체크리스트"
echo "  [ ] ssot/canon.json — [[REPLACE_ME]] 플레이스홀더를 실제 값으로 교체"
echo "  [ ] AGENTS.md — 미션 한 문장 교체"
echo "  [ ] README.md — 프로젝트 목적·컨텍스트 수정"
echo "  [ ] state/_queue.json — 첫 번째 태스크 추가"
echo "  [ ] Claude Code에서 AGENTS.md를 시작점으로 오케스트레이터 호출"
echo ""
echo "=== 부트스트랩 완료 ==="
