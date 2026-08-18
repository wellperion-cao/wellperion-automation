"""자율현황 라이브 섹션 — 도구(tool_use) 이벤트가 items 에 안 나가는지 자기검사
(GM 지적 2026-08-18 "Bash·grep·python 스니펫이 그대로 보인다" → 서버 쪽에서 걸러냄).

python scripts/live_cli_status_server.py 옆에서 실행:
  C:/Python314/python.exe scripts/test_live_cli_status_tool_filter.py
"""
import json
import live_cli_status_server as m

_USER = json.dumps({
    'type': 'user', 'timestamp': '2026-08-18T03:00:00Z',
    'message': {'content': '이거 확인해줘'},
})
_ASSISTANT = json.dumps({
    'type': 'assistant', 'timestamp': '2026-08-18T03:00:01Z',
    'message': {'content': [{'type': 'text', 'text': '확인했다'}]},
})
# 도구 이벤트를 가장 최근으로 둔다 — status(last_ts/busy)가 여전히 이걸 근거로 쓰는지 확인용
_TOOL = json.dumps({
    'type': 'assistant', 'timestamp': '2026-08-18T03:00:02Z',
    'message': {'content': [{'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'grep -r foo'}}]},
})

lines = [_USER, _ASSISTANT, _TOOL]

# ── _events_from_lines 자체는 도구 이벤트를 여전히 만든다(상태 판정용 근거로 계속 필요)
events = m._events_from_lines(lines)
assert sum(1 for e in events if e[1] == '도구') == 1, events

# ── 화면에 나가는 payload 는 도구를 뺀다 — _latest_session 을 이 3줄짜리 가짜 세션으로 바꿔치기
_orig_latest = m._latest_session
_orig_read_tail = m._read_tail_lines
_orig_read_head = m._read_head_timestamp
m._latest_session = lambda: 'fake.jsonl'
m._read_tail_lines = lambda path: lines
m._read_head_timestamp = lambda path: '2026-08-18T02:59:00Z'
try:
    payload = m._build_payload()
finally:
    m._latest_session = _orig_latest
    m._read_tail_lines = _orig_read_tail
    m._read_head_timestamp = _orig_read_head

kinds = [it['kind'] for it in payload['items']]
assert '도구' not in kinds, kinds
assert '지시' in kinds and '응답' in kinds, kinds

# ── 도구 이벤트가 가장 최근이어도 last_activity_at/busy 판정은 그걸 반영한다
assert payload['last_activity_at'] == '2026-08-18T03:00:02Z', payload

print('OK — 도구 이벤트 items 제외 + 상태판정 유지 확인')
