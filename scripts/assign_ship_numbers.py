"""
assign_ship_numbers.py
담당(clevel)별 고정 식별번호(ship_no)를 _queue.json에 1회 부여.
멱등·append-only — 기존 번호 절대 변경 금지.

--pre-commit 게이트(2026-07-20 시토·동시커밋 사고대응):
  pre-commit 훅은 매 커밋마다 무조건 이 스크립트를 부르고 결과를
  `git add -- status/_queue.json` 해왔다 — 이 커밋이 _queue.json 을 전혀 건드릴
  의도가 없어도, 훅이 "지금 디스크에 있는" 내용을 통째로 스테이징해버린다. 공유
  워크트리에서 다른 세션이 _queue.json 을 편집 중(아직 add 안 함)이면 그 스테일/
  미완성 내용이 무관한 커밋에 섞여 들어간다(sync_queue_mirror.py 가 이미 겪은
  것과 같은 사고 패턴). --pre-commit 플래그가 주어지면, status/_queue.json 이
  "이번 커밋에 실제로 staged" 된 경우(`git diff --cached --name-only`)에만
  동작하고, 아니면 조용히 아무 것도 안 하고 종료한다(fail-open).
"""
import subprocess
import sys, json, os
from collections import defaultdict
from contextlib import nullcontext

sys.stdout.reconfigure(encoding='utf-8')

try:  # 크로스프로세스 _queue.json 락 (P2, 2026-07-10) — 같은 scripts/ 디렉토리
    import queue_lock
except Exception:
    queue_lock = None

QUEUE_PATH = os.path.join(os.path.dirname(__file__), '..', 'status', '_queue.json')
QUEUE_PATH = os.path.normpath(QUEUE_PATH)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_REL = 'status/_queue.json'


def _is_staged_for_commit(root):
    """status/_queue.json 이 이번 커밋(인덱스, HEAD 대비)에 실제로 staged 됐는지."""
    try:
        out = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--', QUEUE_REL],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return bool(out.stdout.decode('utf-8', 'replace').strip())
    except Exception:
        return False

def load():
    with open(QUEUE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save(data):
    with open(QUEUE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    summary = {}
    max_no = defaultdict(int)
    with (queue_lock.queue_lock("assign-ships", repo_root=REPO_ROOT) if queue_lock else nullcontext()):
        tasks = load()

        # 담당별 현재 max ship_no 계산
        for t in tasks:
            if 'ship_no' in t and t['ship_no'] is not None:
                cl = str(t.get('clevel', '')).lower()
                try:
                    max_no[cl] = max(max_no[cl], int(t['ship_no']))
                except (ValueError, TypeError):
                    pass

        # 담당별 ship_no 없는 작업 수집 → enqueued_at(없으면 task_id) 오름차순 정렬 후 부여
        pending = defaultdict(list)
        for i, t in enumerate(tasks):
            if 'ship_no' not in t or t['ship_no'] is None:
                cl = str(t.get('clevel', '')).lower()
                sort_key = str(t.get('enqueued_at') or t.get('task_id') or '')
                pending[cl].append((sort_key, i))

        for cl, entries in pending.items():
            entries.sort(key=lambda x: x[0])
            next_no = max_no[cl] + 1
            for _, idx in entries:
                tasks[idx]['ship_no'] = next_no
                next_no += 1
            summary[cl] = len(entries)

        save(tasks)

    if summary:
        print('[assign_ship_numbers] 새로 부여:')
        for cl, cnt in sorted(summary.items()):
            print(f'  {cl}: {cnt}건 (→ {max_no[cl]+cnt}번까지)')
    else:
        print('[assign_ship_numbers] 새로 부여할 항목 없음 (멱등 확인)')

if __name__ == '__main__':
    if '--pre-commit' in sys.argv:
        if not _is_staged_for_commit(REPO_ROOT):
            print('[assign_ship_numbers] status/_queue.json 이 이번 커밋에 staged 안 됨 — skip(무관 상태 혼입 방지)')
            sys.exit(0)
    main()
