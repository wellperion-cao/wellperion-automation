#!/usr/bin/env bash
# run_cycle.sh — 1 사이클 실행 스캐폴드 (Linux/Mac)
# 용도: 큐에서 PENDING 태스크 읽기 → 실행 envelope → 검증 체크리스트 출력
# 주의: LLM 직접 호출 없음 — 구조와 체크리스트만 제공
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
QUEUE_FILE="$ROOT_DIR/state/_queue.json"

echo "=== 스웜 사이클 실행 스캐폴드 ==="
echo "사이클 시작: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. ssot 부팅 확인
echo "[BOOT] ssot 3종 확인..."
for f in "ssot/약속.json" "ssot/incidents.json" "ssot/canon.json"; do
  if [ -f "$ROOT_DIR/$f" ]; then
    echo "  OK  $f"
  else
    echo "  ERROR: $f 없음 — 부팅 중단"
    exit 1
  fi
done

# 2. 큐에서 PENDING 태스크 확인
echo ""
echo "[QUEUE] PENDING 태스크 확인..."
if command -v python3 &>/dev/null; then
  PENDING=$(python3 -c "
import json, sys
with open('$QUEUE_FILE', encoding='utf-8') as f:
    q = json.load(f)
tasks = [t for t in q.get('tasks', []) if t.get('status') == 'PENDING']
print(f'PENDING: {len(tasks)}개')
for t in tasks:
    print(f'  - [{t[\"id\"]}] {t[\"title\"]}')
" 2>/dev/null || echo "  (python3로 파싱 실패 — 수동 확인)")
  echo "$PENDING"
else
  echo "  (python3 없음 — state/_queue.json 수동 확인)"
fi

# 3. 실행 체크리스트
echo ""
echo "[CYCLE] 실행 전 체크리스트:"
echo "  [ ] 1. intake 스킬 실행 (목표·범위·성공조건 명확화)"
echo "  [ ] 2. decompose 스킬 실행 (태스크 분해·병렬 식별)"
echo "  [ ] 3. 라우팅 결정 (토큰 라우팅 원칙 준수)"
echo "  [ ] 4. executor → implement 스킬 (병렬 가능 항목 병렬 실행)"
echo "  [ ] 5. reviewer → verify 스킬 (완료 4요건 확인)"
echo "  [ ] 6. 큐 상태 업데이트"
echo "  [ ] 7. retrospective 스킬 실행"
echo "  [ ] 8. memory-update 스킬 실행"

# 4. 경계 확인
echo ""
echo "[LIMITS] 루프 경계 (canon.json 기준):"
if command -v python3 &>/dev/null; then
  python3 -c "
import json
with open('$ROOT_DIR/ssot/canon.json', encoding='utf-8') as f:
    c = json.load(f)
lim = c.get('loop_limits', {})
print(f'  태스크당 최대 재시도: {lim.get(\"max_retries_per_task\", 3)}회')
print(f'  최대 사이클: {lim.get(\"max_cycles\", 10)}')
print(f'  수렴 판단 기준: {lim.get(\"stall_threshold_cycles\", 3)}사이클 연속 진전 없음')
" 2>/dev/null || echo "  (python3로 파싱 실패 — canon.json 수동 확인)"
fi

echo ""
echo "=== 사이클 스캐폴드 출력 완료 ==="
echo "이제 Claude Code에서 AGENTS.md를 시작점으로 오케스트레이터를 호출하세요."
