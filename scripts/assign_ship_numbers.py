"""
assign_ship_numbers.py
담당(clevel)별 고정 식별번호(ship_no)를 _queue.json에 1회 부여.
멱등·append-only — 기존 번호 절대 변경 금지.
"""
import sys, json, os
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

QUEUE_PATH = os.path.join(os.path.dirname(__file__), '..', 'status', '_queue.json')
QUEUE_PATH = os.path.normpath(QUEUE_PATH)

def load():
    with open(QUEUE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save(data):
    with open(QUEUE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    tasks = load()

    # 담당별 현재 max ship_no 계산
    max_no = defaultdict(int)
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

    summary = {}
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
    main()
