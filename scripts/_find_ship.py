import json
q = json.load(open('status/_queue.json', encoding='utf-8'))
hits = [s for s in q if isinstance(s, dict) and any(
    k in str(s) for k in ['임정은', '연락이력', 'CEO-2026-08-15']
)]
print(json.dumps(hits, ensure_ascii=False, indent=2))
