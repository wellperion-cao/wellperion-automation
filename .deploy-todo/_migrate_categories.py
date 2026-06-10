#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""업무 카테고리 9분류 마이그레이션 (2026-06-10).
백업(_backup_todo_list_20260610.json) 기준으로 카테고리 문자열을 일괄 치환.
- 단순 +1 시프트: [3]운영정책->[4], [4]시설->[5], [5]회원CS->[6], [8]회의->[9]
- [2] 인사 & 파트너 -> 인사/[3]파트너팀 (ID별 best-effort, 아래 SPLIT)
- 비정본(업무/시스템/결재) -> [7] IT·시스템·자동화 (best-effort)
- [1] 매출, 빈칸은 불변
todo_update는 빈값 보존 규칙이라 category만 보내면 다른 필드 무손상.
"""
import json, urllib.request, sys, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API = 'https://script.google.com/macros/s/AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec'
DRY = ('--apply' not in sys.argv)

# 시프트 매핑 (현재 라벨 -> 신규 라벨)
SHIFT = {
    '[3] 운영 정책': '[4] 운영 정책',
    '[4] 시설 및 환경': '[5] 시설 및 환경',
    '[5] 회원·CS': '[6] 회원·CS',
    '[8] 회의': '[9] 회의',
}
# 비정본 카테고리 보존 매핑
LEGACY = {
    '업무': '[7] IT·시스템·자동화',
    '시스템': '[7] IT·시스템·자동화',
    '결재': '[7] IT·시스템·자동화',
}
# [2] 인사 & 파트너 ID별 split (인사=내부직원 / 파트너팀=외부파트너·강사)
SPLIT = {
    'TODO-20260610150040028': '[2] 인사',        # 시설팀 재계약(근로계약)
    'TODO-20260605172323917': '[2] 인사',        # 운영부 사원 채용
    'TODO-20260605133653237': '[2] 인사',        # 직책수당 가이드 정비
    'TODO-20260529150352212': '[2] 인사',        # 이지영사원 퇴사일정
    'TODO-20260527192601290': '[2] 인사',        # 지원부 김미영주임 채용
    'TODO-20260526191513510': '[2] 인사',        # 칭찬사원제도
    'TODO-20260526180143612': '[2] 인사',        # 운영부 급여변경 재계약
    'TODO-20260526173241993': '[2] 인사',        # 위성진 주차관리인 계약전환(채용)
    'TODO-20260609141020681': '[3] 파트너팀',     # 부서 업장관리(강습팀 지원)
    'TODO-20260605153327905': '[3] 파트너팀',     # 강습부서 월1회 콘텐츠
    'TODO-20260528172848231': '[3] 파트너팀',     # 루프팀 GXE 인수인계
    'TODO-20260526173308627': '[3] 파트너팀',     # 파트너 복장 지급
    'TODO-20260526173255598': '[3] 파트너팀',     # 파트너 복장 지급
    'TODO-20260526173237401': '[3] 파트너팀',     # 김명선 프로 계약 종료(외부 강사)
    'TODO-20260526173229010': '[3] 파트너팀',     # 파트너 레벨링 체계
    'TODO-20260526173224815': '[3] 파트너팀',     # 정착지원금 제도 개편
}

def new_cat(row):
    cat = row.get('카테고리', '')
    rid = row.get('id', '')
    if cat == '[2] 인사 & 파트너':
        return SPLIT.get(rid)  # 미정의면 None -> 보고
    if cat in SHIFT:
        return SHIFT[cat]
    if cat in LEGACY:
        return LEGACY[cat]
    return None  # [1] 매출, 빈칸 등 불변

def post(rid, cat):
    payload = json.dumps({'action':'todo_update','id':rid,'category':cat}).encode('utf-8')
    req = urllib.request.Request(API, data=payload, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))

def main():
    d = json.load(open('.deploy-todo/_backup_todo_list_20260610.json', encoding='utf-8'))
    rows = d['data']
    plan = []
    unmapped_partner = []
    for r in rows:
        nc = new_cat(r)
        if r.get('카테고리') == '[2] 인사 & 파트너' and nc is None:
            unmapped_partner.append(r.get('id'))
        if nc and nc != r.get('카테고리'):
            plan.append((r.get('id'), r.get('카테고리'), nc, r.get('업무명','')))
    print('MODE:', 'DRY-RUN' if DRY else 'APPLY')
    print('총 행:', len(rows), '| 치환 대상:', len(plan), '| 미매핑 파트너:', len(unmapped_partner))
    for rid, old, nc, title in plan:
        print(f'  {rid} | {old} -> {nc} | {title[:30]}')
    if unmapped_partner:
        print('!! 미매핑 [2]인사&파트너:', unmapped_partner)
    if DRY:
        print('\n(dry-run. --apply 로 실제 실행)')
        return
    ok = err = 0
    for rid, old, nc, title in plan:
        try:
            res = post(rid, nc)
            if res.get('ok'):
                ok += 1; print(f'OK {rid} -> {nc}')
            else:
                err += 1; print(f'ERR {rid}: {res}')
        except Exception as e:
            err += 1; print(f'EXC {rid}: {e}')
        time.sleep(0.4)
    print(f'\n완료: 성공 {ok} / 실패 {err} / 계획 {len(plan)}')

if __name__ == '__main__':
    main()
