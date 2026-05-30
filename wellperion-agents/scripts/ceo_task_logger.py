# -*- coding: utf-8 -*-
"""
ceo_task_logger.py — AI CEO(웰리) 업무현황 SSOT 자동 기록 헬퍼
=================================================================
용도
    GM 지시를 받아 웰리가 수행하는 작업을 업무현황 SSOT(가이드허브 coo/todo,
    GM이 보는 화면)에 "할일 → 진행중 → 완료" 흐름으로 자동 기록한다.
    그동안 위임·검증·텔레그램 보고만 하고 SSOT에는 안 남겨 GM이 추적 못하던
    문제를 해소 (2026-05-30 [#04] GM 지시).

데이터 경로 (SSOT)
    구글 시트 '업무&결재 현황' ← Apps Script(.deploy-todo/업무&결재 현황.js)
    exec 엔드포인트(공개 GET). 페이지(업무 현황 SSOT.html)와 동일 API 사용.
    필드(영문→한글 서버 매핑): title 업무명 / category 카테고리 / owner 담당자 /
      startDate 시작일 / endDate 종료일 / content 내용 / status 상태 /
      approval 결재요청 / link 링크 / creator 생성자
    상태 옵션: 진행중 · 완료 · 보류

보안
    todo_add/todo_done 는 페이지 자체가 비인증 GET 으로 호출하는 공개 액션이라
    별도 토큰 불필요(토큰은 서버측 ScriptProperties 보관, 본 스크립트 비노출).
    exec URL 은 환경변수 CEO_TASK_API_URL 로 override 가능(기본값=SSOT 정본).

사용법 (라이브러리)
    from ceo_task_logger import add_ceo_task, complete_ceo_task
    res = add_ceo_task("노션 폐기 1단계 정리", status="완료",
                       category="[3] 운영 정책",
                       content="archive watcher 400 폭주 차단 …")
    # → {'ok': True, 'id': 'TODO-...'}
    complete_ceo_task(res["id"])   # 진행중 → 완료 갱신

사용법 (CLI)
    python ceo_task_logger.py add  --title "..." [--status 진행중] [--category ...] [--content ...]
    python ceo_task_logger.py done --id TODO-...
    python ceo_task_logger.py list [--status 완료]
"""
import os
import sys
import json
import argparse

import requests

# ── exec URL (SSOT 정본; env override 허용) ─────────────────────────
DEFAULT_API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
API_URL = os.environ.get("CEO_TASK_API_URL", DEFAULT_API_URL)

# AI CEO 담당자 표기 (담당=AI CEO/웰리). 시트 MEMBERS 에 없는 신규 표기 —
# 담당자 필드는 자유 텍스트라 등록 가능. GM 추적용 식별 라벨.
CEO_OWNER = "AI CEO(웰리)"
DEFAULT_CATEGORY = "[3] 운영 정책"

_TIMEOUT = 60


def _call(params):
    """업무현황 SSOT API 호출(GET 쿼리스트링; 페이지와 동일 방식)."""
    r = requests.get(API_URL, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def add_ceo_task(title, status="진행중", category=None, content="",
                 owner=None, link="", start_date=None, end_date=""):
    """업무현황 SSOT 에 AI CEO 작업 1건 등록.

    Args:
        title:     업무명 (필수)
        status:    진행중 | 완료 | 보류 (기본 진행중)
        category:  카테고리 (기본 [3] 운영 정책)
        content:   내용 본문
        owner:     담당자 (기본 AI CEO(웰리))
        link:      관련 링크(커밋·페이지 등)
        start_date:시작일 (기본 시트측 오늘)
        end_date:  종료일

    Returns:
        dict {'ok': bool, 'id': 'TODO-...', ...}
    """
    if not title:
        raise ValueError("title 필수")
    params = {
        "action": "todo_add",
        "title": title,
        "category": category or DEFAULT_CATEGORY,
        "owner": owner or CEO_OWNER,
        "content": content,
        "status": status,
        "link": link,
        "creator": CEO_OWNER,
    }
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    return _call(params)


def complete_ceo_task(task_id):
    """등록된 업무를 완료(진행중 → 완료) 처리."""
    if not task_id:
        raise ValueError("task_id 필수")
    return _call({"action": "todo_done", "id": task_id})


def list_ceo_tasks(status=None, owner=None):
    """업무현황 SSOT 조회(검증용). status/owner 필터 선택."""
    params = {"action": "todo_list"}
    if status:
        params["status"] = status
    if owner:
        params["owner"] = owner
    return _call(params)


# ─── CLI ─────────────────────────────────────────────────────────────
def _main(argv=None):
    ap = argparse.ArgumentParser(description="AI CEO 업무현황 SSOT 기록 헬퍼")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="업무 등록")
    a.add_argument("--title", required=True)
    a.add_argument("--status", default="진행중")
    a.add_argument("--category", default=None)
    a.add_argument("--content", default="")
    a.add_argument("--owner", default=None)
    a.add_argument("--link", default="")

    d = sub.add_parser("done", help="업무 완료 처리")
    d.add_argument("--id", required=True)

    ls = sub.add_parser("list", help="업무 조회(검증)")
    ls.add_argument("--status", default=None)
    ls.add_argument("--owner", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "add":
        res = add_ceo_task(args.title, status=args.status, category=args.category,
                           content=args.content, owner=args.owner, link=args.link)
    elif args.cmd == "done":
        res = complete_ceo_task(args.id)
    elif args.cmd == "list":
        res = list_ceo_tasks(status=args.status, owner=args.owner)
    else:
        ap.error("알 수 없는 명령")
        return 2

    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())
