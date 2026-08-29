# -*- coding: utf-8 -*-
"""GM 직접 업무 체크리스트 자동 점검 — gm_task_autocheck.py (GM 요청 2026-08-15 · 웰리 설계 승인)

무엇을 하나
  ① 자동 체크 — status/monthly_ops_plan.json 의 GM 직접 목표 progress_note □ 줄 중
     **배 번호(배NNN)가 적힌 줄만** status/_queue.json(+아카이브)의 그 배 status 로 판정,
     DONE 이면 □→☑ + progress·honesty(basis) 갱신(화면 「변경 저장」과 같은 계산식).
     배 번호 없는 줄은 절대 건드리지 않는다 — 근거 없는 자동 체크가 최악이다(설계 ①).
     배 번호 오참조 방어: 줄 낱말과 배 제목 낱말이 절반 이상 겹칠 때만 인정
     (kungjjak_board._norm 재사용 — 실측: 옛 배469 참조가 다른 제목의 배를 가리키고 있었다).
  ② 미완 일정화 — 미완(□) 줄 중 마감 표식 `(~M/D)` 가 있는 줄만 전사일정 등재 후보.
     등록은 ops_daily_digest.bridge_to_schedule 재사용(지난날짜·중복·상한 거르기 포함).
     담당(dept)은 비운다 — GM 직접 건이라 지어낼 값이 없다(약속 L23). 날짜 없는 미완은
     일정을 만들지 않고 푸시 문안에 개수만 나열한다.
  ③ GM 푸시 — telegram_notifier(텔레그램 업무보고방) 1일 1회. 발송락
     status/.gm_autocheck_sent(날짜)로 같은 날 재실행 시 중복 발송 방지.

킬스위치: status/gm_autocheck.json {"enabled": false} — false 면 실행 전체 스킵(--dry-run 은 예외).
되돌리기: ceo_morning_pipeline.py 의 호출 1줄 제거(또는 킬스위치 false) + 커밋 revert.

쓰는 법
  C:/Python314/python.exe wellperion-agents/scripts/gm_task_autocheck.py --dry-run   # 판정만 출력
  C:/Python314/python.exe wellperion-agents/scripts/gm_task_autocheck.py             # 실가동(킬스위치 ON 필요)
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'status' / 'monthly_ops_plan.json'
QUEUE = ROOT / 'status' / '_queue.json'
QUEUE_ARCHIVE = ROOT / 'status' / '_queue_archive.json'
SWITCH = ROOT / 'status' / 'gm_autocheck.json'
SENT_LOCK = ROOT / 'status' / '.gm_autocheck_sent'

sys.path.insert(0, str(ROOT / 'scripts'))
from kungjjak_board import _norm, _SHIP_IN_TEXT_RE  # 판정 보조 재사용(약속 L01)

DUE_RE = re.compile(r'\(~(\d{1,2})/(\d{1,2})\)')
CHECK_RE = re.compile(r'^(\s*)([\u25A1\u2611])(.*)$')


def _gm_direct(obj: dict) -> bool:
    """GM 직접 판정 — _gm_direct_tasks.js isGmDirect 와 같은 기준(제목 태그 또는 ERP 건 id 지정)."""
    return '(GM 직접)' in str(obj.get('title') or '') or obj.get('id') == '2026-08-08'


def _load_ships() -> dict:
    """short_no → (status, title). 라이브 큐가 우선, 아카이브는 보조(번호 재사용 시 라이브가 이긴다)."""
    ships = {}
    for path in (QUEUE_ARCHIVE, QUEUE):
        try:
            for s in json.loads(path.read_text(encoding='utf-8')):
                no = str(s.get('short_no') or '').strip()
                if no:
                    ships[no] = (str(s.get('status') or ''), str(s.get('title') or ''))
        except Exception:
            continue
    return ships


def _ship_done_for_line(line: str, ships: dict) -> str | None:
    """줄이 가리키는 배가 DONE 이고 제목 낱말이 절반 이상 겹치면 그 배 번호, 아니면 None."""
    m = _SHIP_IN_TEXT_RE.search(line)
    if not m:
        return None
    no = m.group(1)
    status, title = ships.get(no, ('', ''))
    if status != 'DONE':
        return None
    lw, tw = _norm(line), _norm(title)
    need = max(1, (min(len(lw), len(tw)) + 1) // 2)
    if len(lw & tw) < need:
        print(f'  [방어] 배{no} DONE 이지만 제목 불일치 — 체크 안 함: {line.strip()[:50]}')
        return None
    return no


def run(dry_run: bool, body_out: str | None = None) -> int:
    if not dry_run:
        try:
            if not json.loads(SWITCH.read_text(encoding='utf-8')).get('enabled'):
                print('[SKIP] 킬스위치 OFF (status/gm_autocheck.json enabled=false)')
                return 0
        except Exception:
            print('[SKIP] 킬스위치 파일 없음/불량 — 실가동 안 함')
            return 0

    today = datetime.date.today()
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    month = plan.get('months', {}).get(f'{today:%Y-%m}')
    if not month:
        print('[SKIP] 이번 달 계획 없음')
        return 0
    ships = _load_ships()

    checked, sched_cands, undone_total, undone_dated = [], [], 0, 0
    for obj in month.get('objectives', []):
        if not _gm_direct(obj):
            continue
        lines = str(obj.get('progress_note') or '').split('\n')
        flips = 0
        for i, ln in enumerate(lines):
            m = CHECK_RE.match(ln)
            if not m:
                continue
            if m.group(2) == '\u2611':
                continue
            no = _ship_done_for_line(ln, ships)
            if no:
                lines[i] = m.group(1) + '\u2611' + m.group(3)
                flips += 1
                checked.append((obj['id'], no, m.group(3).strip()[:50]))
                continue
            undone_total += 1
            dm = DUE_RE.search(ln)
            if dm:
                undone_dated += 1
                due = f'{today.year}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}'
                sched_cands.append({'date': due, 'title': m.group(3).strip()[:80],
                                    'dept': '', 'note': f'GM 직접 · {obj.get("title", "")[:30]}',
                                    'time': ''})
        if flips:
            obj['progress_note'] = '\n'.join(lines)
            todos = [CHECK_RE.match(l) for l in lines]
            todos = [t for t in todos if t]
            done = sum(1 for t in todos if t.group(2) == '\u2611')
            obj['progress'] = round(done / len(todos) * 100)
            obj['honesty'] = {'level': 'basis', 'label': '🧮 근거계산',
                              'basis': f'자동 체크(배 입항 대조) {done}/{len(todos)}',
                              'at': today.isoformat()}

    if checked and not dry_run:
        plan['updated_at'] = today.isoformat()
        PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f'[체크] 자동 체크 {len(checked)}건' + (' (dry-run — 저장 안 함)' if dry_run and checked else ''))
    for oid, no, txt in checked:
        print(f'  ☑ {oid} · 배{no} 입항 → {txt}')
    print(f'[미완] 미완 {undone_total}건 · 마감 표식(~M/D) {undone_dated}건')

    # 전사일정 등재 — ops_daily_digest.bridge_to_schedule 그대로(중복·지난날짜·상한 거르기 포함).
    registered = []
    if sched_cands:
        try:
            from ops_daily_digest import bridge_to_schedule
            registered = bridge_to_schedule(sched_cands, today.isoformat(), 'gm_autocheck', dry_run=dry_run)
        except Exception as exc:
            print(f'[WARN] 전사일정 등재 실패({exc}) — 푸시 문안에만 나열')

    # 푸시 문안 — 1일 1회(발송락). dry-run 은 문안만 찍는다.
    msg = (f'🧭 GM 직접 업무 자동 점검 ({today.isoformat()})\n'
           f'· 자동 체크 {len(checked)}건' +
           ''.join(f'\n  ☑ 배{no} 입항 — {txt}' for _, no, txt in checked[:5]) +
           f'\n· 미완 {undone_total}건 (마감 표식 {undone_dated}건 · 전사일정 등재 {len(registered)}건)\n'
           f'· 상세 = GM업무 화면 「김남욱 GM 업무 진행건」')
    print('----- 푸시 문안 -----')
    print(msg)
    print('---------------------')
    if body_out:
        # [2026-08-29 GM 승인] 같은 방(업무보고방) 08시 두 통 → 한 통. 문안을 파일로 넘겨
        # ceo_morning_pipeline 이 「오늘의 항로」 본문 꼬리에 싣는다 — 단독 발송 안 함.
        Path(body_out).write_text(msg, encoding='utf-8')
        print(f'[발송] --body-out — 아침 통에 실어 보냄 · 단독 발송 안 함')
        return 0
    if dry_run:
        print('[발송] dry-run — 발송 안 함')
        return 0
    if SENT_LOCK.exists() and SENT_LOCK.read_text(encoding='utf-8').strip() == today.isoformat():
        print('[발송] 오늘 이미 발송 — 중복 방지 스킵')
        return 0
    try:
        sys.path.insert(0, str(ROOT / 'wellperion-agents'))
        from telegram_notifier import TelegramNotifier
        TelegramNotifier().send(msg)
        SENT_LOCK.write_text(today.isoformat(), encoding='utf-8')
        print('[발송] 업무보고방 발송 완료')
    except Exception as exc:
        print(f'[WARN] 발송 실패({exc})')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='판정·문안만 출력, 저장·발송 없음')
    ap.add_argument('--body-out', default=None,
                    help='푸시 문안을 이 파일에 쓰고 단독 발송은 생략(아침 통 합침용)')
    args = ap.parse_args()
    return run(args.dry_run, body_out=args.body_out)


if __name__ == '__main__':
    sys.exit(main())
