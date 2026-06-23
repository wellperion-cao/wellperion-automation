#!/usr/bin/env bash
# verify.sh — 품질 게이트 체크 (Linux/Mac)
# 용도: 필수 파일 존재·JSON 유효성·플레이스홀더·증거 기록 확인
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

PASS=0
FAIL=0

check() {
  local label="$1"
  local result="$2"
  if [ "$result" = "PASS" ]; then
    echo "  PASS  $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $label — $result"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== 품질 게이트 검증 ==="
echo ""

# 게이트 1: 필수 파일 존재
echo "[게이트 1] 필수 파일 완전성"
REQUIRED=(
  "README.md" "AGENTS.md" "CLAUDE.md"
  "ssot/약속.json" "ssot/incidents.json" "ssot/canon.json"
  "state/_queue.json" "state/README.md"
  "loop/swarm-loop.md" "loop/quality-gates.md"
  "agents/orchestrator.md" "agents/planner.md"
  "agents/executor.md" "agents/reviewer.md" "agents/researcher.md"
  "skills/index.md"
  "skills/intake/SKILL.md" "skills/decompose/SKILL.md"
  "skills/implement/SKILL.md" "skills/verify/SKILL.md"
  "skills/memory-update/SKILL.md" "skills/retrospective/SKILL.md"
  "docs/upstreams.md"
)
for f in "${REQUIRED[@]}"; do
  if [ -f "$ROOT_DIR/$f" ]; then
    check "$f" "PASS"
  else
    check "$f" "파일 없음"
  fi
done

# 게이트 2: JSON 유효성
echo ""
echo "[게이트 2] JSON 유효성"
JSON_FILES=("ssot/약속.json" "ssot/incidents.json" "ssot/canon.json" "state/_queue.json")
for f in "${JSON_FILES[@]}"; do
  if [ -f "$ROOT_DIR/$f" ]; then
    if python3 -c "import json; json.load(open('$ROOT_DIR/$f', encoding='utf-8'))" 2>/dev/null; then
      check "$f" "PASS"
    else
      check "$f" "JSON 파싱 오류"
    fi
  fi
done

# 게이트 3: 플레이스홀더 확인
echo ""
echo "[게이트 3] 플레이스홀더 (canon.json)"
COUNT=$(grep -c "\[\[REPLACE_ME\]\]" "$ROOT_DIR/ssot/canon.json" 2>/dev/null || echo "0")
if [ "$COUNT" -eq 0 ]; then
  check "canon.json 플레이스홀더" "PASS"
else
  check "canon.json 플레이스홀더" "${COUNT}개 남음 (교체 필요)"
fi

# 결과 요약
echo ""
echo "=== 결과 ==="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "  판정: 모든 게이트 통과"
  exit 0
else
  echo "  판정: ${FAIL}개 게이트 실패 — 재작업 필요"
  exit 1
fi
