"""놓친 지시·반복 지시 적발 자기검사 (2026-08-08 · GM "절대 놓치지마").

위험한 지점 둘:
  ① 안 한 일을 '했다'로 자동 처리하는 것 — 지금 상태보다 나쁘다. 그래서 자동 완료는 없다.
  ② 방금 받은 것을 '놓쳤다'로 몰아 재촉하는 것 — 그러면 경보가 곧 무시된다.

python scripts/kungjjak_board.py 옆에서 실행:
  C:/Python314/python.exe scripts/test_kungjjak_missed.py
"""
import datetime
from kungjjak_board import classify_open, find_repeats, GRACE_MIN

NOW = datetime.datetime(2026, 8, 8, 15, 0)


def item(no, got, start, open_=True):
    return {'no': no, 'got': got, 'start': start, 'open': open_}


# ── 방금 받은 것은 재촉하지 않는다
r = classify_open([item('1', '가나다 라마바', '14:30')], [], NOW)
assert r[0]['kind'] == 'just', r
assert r[0]['waited'] == 30

# ── 오래됐고 그 뒤 아무 흔적도 없으면 진짜 놓친 것
r = classify_open([item('2', '가나다 라마바', '09:00')], [], NOW)
assert r[0]['kind'] == 'missed', r

# ── 오래됐지만 접수 뒤 작업 기록이 있으면 '했는데 안 닫은 것'
r = classify_open([item('3', '가나다 라마바', '09:00')], [{'time': '10:20'}], NOW)
assert r[0]['kind'] == 'unclosed', r

# ── 접수보다 앞선 작업 기록은 근거가 안 된다(그건 다른 일이다)
r = classify_open([item('4', '가나다 라마바', '09:00')], [{'time': '08:10'}], NOW)
assert r[0]['kind'] == 'missed', r

# ── 이미 닫힌 것은 아예 안 센다
assert classify_open([item('5', '끝난 일', '09:00', open_=False)], [], NOW) == []

# ── 경계: 딱 GRACE_MIN 분이면 더는 '방금'이 아니다
start = (NOW - datetime.timedelta(minutes=GRACE_MIN)).strftime('%H:%M')
assert classify_open([item('6', '가나다 라마바', start)], [], NOW)[0]['kind'] == 'missed'

# ── 반복 지시: 같은 말을 두 번 하시면 묶인다
rep = find_repeats([item('7', '쿵짝표 보여줘', '09:00'), item('8', '쿵짝표 보여줘봐', '10:00')])
assert len(rep) == 1 and rep[0]['count'] == 2, rep

# ── 다른 지시는 안 묶인다
rep = find_repeats([item('9', '매출 보고 고쳐줘', '09:00'), item('10', '링크가 잘려서 나간다', '10:00')])
assert rep == [], rep

# ── 한 번뿐인 것은 반복이 아니다
assert find_repeats([item('11', '쿵짝표 보여줘', '09:00')]) == []

print('OK — 놓친·반복 지시 적발 판정 9건 통과')
