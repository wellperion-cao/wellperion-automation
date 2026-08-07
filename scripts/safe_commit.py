# scripts/safe_commit.py
# 전 C-Level 공용 "스테일 트리 차단" 안전 커밋터 (2026-07-23, CMO 신설 · 배9820).
#
# 계기: 공용 작업트리 레이스 — 커밋 준비 시점에 읽은 트리를 나중 parent 위에 커밋해
#   ①남의 미커밋 변경분을 내 커밋이 쓸어담거나(이력 귀속 어긋남, 2026-07-23 하루 4회 관측)
#   ②그 사이 들어온 파일이 '삭제'로 기록되는(2026-07-21 AI하루 10편 190파일 삭제) 사고.
#   상세 실측 = status/briefs/시모_커밋스테일트리_제기_20260723.md.
#
# 차단 원리(2026-07-23 커밋 8244b4acb 에서 혼입 0건 실증된 절차를 그대로 함수화):
#   1) 라이브 인덱스에 손대지 않는다 — GIT_INDEX_FILE 로 임시 인덱스를 쓰고,
#      그 임시 인덱스는 라이브 index 복사가 아니라 `read-tree HEAD` 로 시작한다
#      (라이브 index 를 cp 하면 남의 staged 파일이 전부 딸려온다 — 기억 박제 2건).
#   2) 지정 경로만 stage → write-tree.
#   2-b) ★선검증(2026-07-24, 배10009) — commit-tree/update-ref *이전*, 트리 대 트리
#      비교로 무관 경로 혼입·유령 삭제(디스크엔 있는데 삭제로 staged)를 판정한다.
#      걸리면 커밋 자체를 만들지 않고 그 자리에서 중단한다. (구 결함: 이 판정이
#      update-ref *이후*에 돌아 탐지는 해도 이미 만들어진 나쁜 커밋이 그대로 origin
#      까지 push 됐다 — scripts/precommit_phantom_delete_guard.py 의 디스크 존재
#      판정 방식을 재사용해 앞당김. safe_commit 은 commit-tree/update-ref 라 git
#      훅이 안 걸려 그 가드가 원래 이 경로에선 발화하지 않는다.)
#   3) commit-tree 직전 HEAD 재검증 — 트리 읽은 뒤 HEAD 가 움직였으면 폐기하고 재시도.
#   4) `git update-ref HEAD <new> <old>` CAS 로 원자 갱신 — 경쟁 커밋이 끼어들면
#      update-ref 자체가 실패하고 재시도(락만으로는 못 막는 틈을 git 이 막아준다).
#   5) 커밋 후 사후 재확인(방어적) — 선검증과 같은 트리라 정상 상황엔 항상 통과.
#      push 게이트는 committed 가 아니라 ok 를 본다(혼입 감지 시 push 도 막힘).
#
# 직렬화 락은 기존 scripts/git_lock.py 의 GitLock 을 그대로 재사용한다(중복 구현 금지).
# push 도 기존 scripts/post_commit_push.py 를 그대로 호출한다 — update-ref 는 post-commit
#   훅을 발화시키지 않으므로(훅은 `git commit` 경로 전용) 명시 호출이 필요하다.
#
# ★작업트리를 바꾸는 git 명령(reset·checkout --·rebase)은 이 모듈에서 절대 쓰지 않는다.
#
# API:
#   from safe_commit import safe_commit
#   res = safe_commit(paths, message, holder="ig_publish_verify")
#   res = {"ok":bool, "committed":bool, "sha":str, "attempts":int,
#          "changed":[경로...], "foreign":[혼입경로...],
#          "auto_included":[자동포함 append로그...],
#          "concurrent_edit_warnings":[동시편집 경고...], "reason":str}
#
# CLI(자체 검증·수동 커밋용):
#   python scripts/safe_commit.py -m "메시지" --no-push -- <경로1> <경로2>
#
# ── 배10291·배10314 흡수(2026-07-27 · 시토) ──────────────────────────────────
# 두 배 모두 이 관문 한 곳에 흡수한다(약속 L21 — 새 가드 파일·새 모듈 금지).
#
# [배10291] 동시 편집 경고 — 공유 작업트리 사고(하루 4건, 배9226·10059·상태줄·10291)는
#   전부 "문서로 금지"가 기계를 못 막아서 났다(약속 L02). 이 관문에서 잡되, 판단은
#   보수적으로 정했다: **차단이 아니라 경고**로만 시작한다 — 오탐으로 정상 커밋을
#   막으면 그게 더 큰 사고이기 때문이다(GM 지시 원문). 최근 N분 내 다른 커밋이 같은
#   경로를 바꿨으면 경고하고, 그중에서도 내가 스테이징한 내용이 그 변경 '이전' 버전과
#   완전히 같으면(=남의 최근 변경을 통째로 지움) 더 강한 경고를 남긴다. 오탐이 실측되면
#   차단으로 강화할지 재판단한다(§_detect_concurrent_edit_warnings 참조).
#   ▶2026-08-06 — 위 "최근 N분 내 경고" 는 삭제했다. 아무도 안 읽는 채널(stdout 뿐)이었고,
#   실사고 부류(옛 사본이 최신을 덮음)는 배421 낡은 사본 차단(같은 함수, 이력 N개 blob
#   비교)이 대신 잡는다(Fable 설계검토 지적④, 약속 L21 net-zero). 지금 §_detect_
#   concurrent_edit_warnings 는 낡은 사본 판정만 한다 — 상세는 그 함수 docstring 참조.
#
# [배10314] append 로그 자동 포함 — status/worklog.jsonl 등 공용 작업 현황 로그는
#   호출자가 경로에 안 넣으면 로컬에만 쌓여 GM 화면이 멈춘다(시포 실측 2026-07-27,
#   커밋 283dd4669 로 1회 복구했지만 구조 문제는 그대로였음). status/*.jsonl(비재귀,
#   backups/ 등 하위 폴더 제외)은 이미 .gitattributes 에 merge=union(2026-06-19)이 걸려
#   있어 여러 세션이 동시에 이어써도 무손실 병합된다 — 그래서 "지정 경로만 담는다"
#   계약을 이 카테고리 하나에 한해 완화해도 안전하다고 판단했다(§_auto_include_modified_logs
#   참조). 작업트리에서 실제로 바뀐 로그만, 커밋 전에 rel_paths 에 편입시켜 이후 모든
#   검증(선검증·훅가드·사후재확인)이 "지정 경로"로 그대로 인식하게 한다 — 별도 예외
#   분기를 새로 안 만들고 기존 계약 흐름에 자연히 올라타는 방식.
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 저장소 루트 = 이 스크립트(scripts/)의 부모 — 작업트리를 어느 PC·경로에 클론했든 동일하게 동작
# (구: 특정 PC 사용자 경로 하드코딩 → 다른 PC에서 PermissionError, 2026-07-25 CFO 실측 보정)
ROOT = Path(__file__).resolve().parents[1]

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from git_lock import GitLock  # noqa: E402  (같은 scripts/ 폴더 — 락 로직 재사용)
# chro/cfo 보호 삭제 판정용 경로 목록 재사용(2026-08-04 — 새 상수 중복 정의 금지,
# .git/hooks/pre-commit 이 부르는 precommit_phantom_delete_guard.py 와 단일 출처).
# SKIP_ENV·_log_block 도 같은 이유로 재사용(2026-08-05 — 아래 COO 도메인 차단의
# 우회 스위치·로그 싱크로 그대로 쓴다. 새 env·새 로그 파일 안 만듦).
from precommit_phantom_delete_guard import (  # noqa: E402
    PROTECTED_DELETE_PREFIXES,
    foreign_delete_violations,
    _log_block as _domain_guard_log,
)

# ── COO(시우) 도메인 파일 차단(2026-08-05 GM 편제 확정) ─────────────────────────
# GM 원문: "실무진들과 작업 충돌되는 부분... 시우건도 준용M 라인으로해서 건드리지말고,
#   내용 전달만 할 수 있게 해줄래? 운영부 방에... 각기 담당자 이름 적어서 웰리가 전달"
# GM 선택 ① — 시우 배(큐 항목)는 그대로 산다. 다만 **운영 도메인의 파일을 AI가
#   직접 고치지 않는다** — 발견하면 ★운영부 카톡방에 담당자를 붙여 "전달"만 한다.
#
# ★층 구분(섞으면 안 됨) — queue_dispatch.py 의 EXCLUDED_ROLES(chro·cfo)는
#   "배 생성 자체"를 큐 관문에서 차단한다(그 두 역할 앞으로는 배조차 안 만든다).
#   이건 그와 다른 층이다: 시우는 배가 그대로 살아 있고, 이 관문(파일 커밋)에서
#   "그 도메인 파일을 AI가 직접 쓰는 것"만 막는다 — 큐·항로에서 시우 배가
#   사라지면 안 된다(EXCLUDED_ROLES 에 coo 를 넣는 것과는 다른 조치).
#
# 경로 출처(실측 · 임의 확장·축소 금지) — ssot/ownership_map.json roles[nick=시우]:
#   primary_surface="월간운영계획·전사회의", domain="종합접수처·각 체계 페이지".
#   + ssot/kpi.json _점검소유_2026_07_27: "점검 화면(coo/check/ 시설부 체계·
#   운영부 체계·전사 일정)... 전부 시우 소유"(GAS 배선 파일은 시토 소유라 제외 —
#   같은 문장 "점검의 배선(GAS·자동발송)은 시토"). coo/ 폴더 안이라도 소유가 다른
#   것(예 coo/todo/업무 현황 SSOT.html·결재 현황 SSOT.html = 시로 domain 문구와
#   일치)은 이 목록에 넣지 않았다 — GM 지시 원문의 그 반례와 정확히 일치.
# ▶2026-08-05 GM 확정 — 월간운영계획·전사_일정 두 화면은 GM 소관으로 옮긴다(GM 이
#   직접 지시해 수정하는 화면이라 이 가드에 걸리면 GM 지시가 막힌다). 나머지 7개는
#   준용M 라인 그대로.
COO_DOMAIN_PATHS = frozenset({
    "3. 웰페리온 가이드/전사회의.html",
    "3. 웰페리온 가이드/coo/reception/종합접수처_현황.html",
    "3. 웰페리온 가이드/coo/check/시설부 체계.html",
    "3. 웰페리온 가이드/coo/check/운영부 체계.html",
    "3. 웰페리온 가이드/coo/check/주차관리부 체계.html",
    "3. 웰페리온 가이드/coo/check/지원부 체계.html",
    "3. 웰페리온 가이드/coo/check/파트너팀 체계.html",
})

# ── CHRO(시로)·CFO(시뽀) 도메인 파일 "수정" 차단(2026-08-05 GM 확정) ────────────
# GM 원문(같은 날): "시우 및 시로, 시뽀 관련해서는 운영부 카카오톡 방에 전달해서
#   작업 시키면 되겠네... 시토는 자율화라고 하지만 막 건드려서 충돌이 나지 않게
#   도와줘야해." → 시로·시뽀는 큐 관문(queue_dispatch.EXCLUDED_ROLES)에서 **배
#   생성 자체**가 이미 막혀 있다(더 강한 층). 여기서는 그 위에 남아 있던 구멍 —
#   "AI가 그 도메인 파일을 직접 '수정'하는 경로"(safe_commit)만 COO와 같은 방식
#   으로 마저 막는다. 위 chro/cfo 보호 삭제 판정(§ PROTECTED_DELETE_PREFIXES)은
#   "삭제"만 막고 "수정"은 안 막았다 — 그 구멍.
# ★재확정(같은 날, GM): "실무 처리 시로 시뽀도 배(업무) 유지하고, 실무 처리를
#   ★중간관리자 방 전달 → 사람이 처리하게 해줘." → 배(큐 항목)를 되살린 것은
#   추적용이지 AI가 파일을 고쳐도 된다는 뜻이 아니다 — 이 차단은 그대로 유지.
#   대신 전달처를 나눈다: 시우(운영) 도메인 차단은 ★운영부 방(담당 최준용M),
#   시로·시뽀(인사·재무) 도메인 차단은 ★중간관리자 방(담당 나우열M) — 두 방
#   모두 scripts/kakao_rooms.json all_rooms 에 실재(새 방 안 만듦). 아래
#   DOMAIN_MODIFY_RULES 의 room 필드가 이 구분을 담는다.
#
# 경로 출처(임의 확장 금지) — ssot/ownership_map.json roles[]:
#   시로 domain="업무현황 SSOT·결재현황 SSOT" → 실제 파일 2개(폴더는 coo 지만
#   소유는 시로 — coo/check/* 처럼 folder=owner 가 아니다):
# 도메인 가드 강행 스위치 — 넘을 도메인 이름을 값으로 넣는다(쉼표로 여러 개).
# 예: WP_DOMAIN_FORCE=CHRO · WP_DOMAIN_FORCE=CHRO,COO
_DOMAIN_FORCE_ENV = "WP_DOMAIN_FORCE"

CHRO_DOMAIN_PATHS = frozenset({
    "3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html",
    "3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html",
})
#   시뽀 domain="운영 매출·지출" → cfo/finance/ 안의 매출·지출 대시보드 3종
#   (apps_script_expense.js 등 배선 파일은 제외 — COO 와 동일 원칙: 내용 화면은
#   도메인 소유, GAS 배선은 시토 소유). 매출지출현황.html 은 GM 이 직접 보는
#   공개 페이지(기억 project_public_pages_gas_password_exposure_accepted)라
#   차단은 하되 강행 경로(SKIP env)를 안내문에 명시해 GM 요청 수정을 막지 않는다.
CFO_DOMAIN_PATHS = frozenset({
    "3. 웰페리온 가이드/cfo/finance/매출지출현황.html",
    "3. 웰페리온 가이드/cfo/finance/매출현황.html",
    "3. 웰페리온 가이드/cfo/finance/지출현황.html",
})
_CFO_GM_JUDGMENT_NOTE = (
    "GM 이 직접 보는 공개 화면입니다 — GM 지시로 고치는 경우 강행 스위치로 "
    "진행하세요(막되 우회로는 열어 둠)."
)

# 세 도메인을 한 판정 함수(_domain_modify_violation)로 처리한다(약속 L01 —
# 같은 관문 안에서 로직도 하나로 합친다. 새 가드 파일·새 함수 난립 금지).
# 튜플: (역할표기, 담당자 표기, 경로집합, 전달방(카톡 room name), GM판단 메모 or None)
# ★2026-08-05 GM 재확정 — 전달처를 도메인별로 가른다: 시우(운영)=★운영부,
#   시로·시뽀(인사·재무)=★중간관리자. 두 방 모두 scripts/kakao_rooms.json
#   all_rooms 에 실재(새 방 생성 금지).
# ★2026-08-07 시토(배429 · 약속 L24 발효) — 운영부 수신 대상을 **이경연 실장**으로 모은다.
#   GM 확정 2026-08-06: "운영부의 지시·보고는 이경연 실장 한 곳을 거친다. 최준용M·임정은M·
#   윤병현AM·백승화 사원 개인에게 직접 지시하지 않는다." 여기가 방·담당자 정본이라
#   이 한 줄만 바꾸면 이걸 읽는 발신부(아침 운영부 전달 등)가 함께 따라온다(약속 L01).
#   ▸개인 이름을 지우는 게 아니라 **받는 사람**을 실장으로 바꾸는 것이다 — 누가 실제로 할지는
#     실장이 나눈다(본문 안에 개인 이름이 남는 것은 참고 정보라 그대로 둔다).
DOMAIN_MODIFY_RULES = (
    ("COO(시우)", "이경연 실장", COO_DOMAIN_PATHS, "★운영부", None),
    ("CHRO(시로)", "나우열M", CHRO_DOMAIN_PATHS, "★중간관리자", None),
    ("CFO(시뽀)", "나우열M", CFO_DOMAIN_PATHS, "★중간관리자", _CFO_GM_JUDGMENT_NOTE),
)


def _domain_modify_violation(diff_pairs, role_label: str, contact: str,
                              domain_paths: frozenset, room: str,
                              judgment_note: str | None, root: Path) -> str | None:
    """도메인 경로가 이번 커밋에 하나라도 걸리면 차단 문구를 만든다(없으면 None).

    강행: env WP_DOMAIN_FORCE 에 **그 역할 이름**을 넣어야 한다(예: WP_DOMAIN_FORCE=CHRO).
    로그는 precommit_phantom_delete_guard 의 _log_block 재사용(새 로그 파일 안 만듦).

    ★2026-08-06 시토 — 강행 스위치를 SKIP_PHANTOM_DELETE_GUARD 와 갈랐다.
      왜: 그 전엔 두 가드가 스위치 하나를 같이 썼다. '지워진 파일 감지'를 끄려고 켠 값이
      전혀 다른 '남의 도메인 수정 차단'까지 같이 열어 버린다 — 끄려던 것과 열리는 것이
      다르면 그건 우회로다. 실제로 이날 실행 레인이 인쇄 CSS 를 고치다 막히자 그 값을
      켜서 시로(나우열M 라인) 도메인 가드를 그 자리에서 통과했다(logs/phantom_delete_guard.jsonl
      CHRO(시로)_domain_force 2건). 사람·리드가 판단하라고 둔 문을 기계가 눌렀다.
      이제는 **어느 도메인을 넘는지 이름으로 말해야** 열린다 — 모르고 열리는 일이 없다.
      스위치 개수는 그대로다(도메인용이 phantom 것을 빌려 쓰던 것을 자기 것으로 옮겼을 뿐).
    """
    hits = sorted({path for _, path in diff_pairs if path in domain_paths})
    if not hits:
        return None
    # role_label 은 "CHRO(시로)" 꼴 — 괄호 앞 영문 토큰만 비교한다(한글 입력 부담 제거).
    role_token = role_label.split("(")[0].strip().upper()
    forced = {t.strip().upper() for t in os.environ.get(_DOMAIN_FORCE_ENV, "").split(",") if t.strip()}
    if role_token in forced:
        _domain_guard_log(f"{role_label}_domain_force", hits, str(root))
        print(f"[WARN] {_DOMAIN_FORCE_ENV}={role_token} — {role_label} 도메인 가드 강행 통과: "
              f"{', '.join(hits)}")
        return None
    extra = f" 외 {len(hits) - 1}건" if len(hits) > 1 else ""
    note = f" [GM 판단 대상] {judgment_note}" if judgment_note else ""
    room_tag = room.lstrip("★")
    return (
        f"{role_label} 도메인 차단: {hits[0]}{extra} — AI가 직접 수정하지 않습니다"
        f"(GM 확정 2026-08-05). 담당: {contact}. {room} 카톡방에 담당자 붙여 전달하세요: "
        f"python scripts/queue_dispatch.py --to ceo --title \"[{room_tag} 전달] "
        f"{hits[0]} 수정 필요\" --note \"담당자: {contact} (scripts/kakao_rooms.json "
        f"{room} members 참조)\" (웰리가 {room} 방으로 전달)."
        f" 강행하려면 env {_DOMAIN_FORCE_ENV}={role_token}(그 도메인만 열림·로그 남음)."
        f" ★강행은 사람·리드가 판단한다 — 막혔다고 자동으로 누르지 마라.{note}"
    )

_MAX_RETRIES = 5          # HEAD 경합 재시도 상한(경쟁 커밋이 계속 끼어들면 실패 보고)
_RETRY_WAIT_SEC = 0.4
_INDEX_LOCK_WAIT_SEC = 0.5
# ★2026-08-03 시토(GM "커밋 안 되는 건들이 많은 것 같은데") — 6회(=3초)는 너무 짧았다.
#   이 저장소는 예약작업·세션이 동시에 커밋해 index.lock 이 수 초씩 잡혀 있는 게 정상이다.
#   실측: 로그 전체에 커밋 실패·잠금 충돌 **266건** · 하루 넘게 고립된 산출물 5건.
#   기다리는 비용은 초 단위인데 포기하는 비용은 '며칠 동안 GM 화면이 옛것'이다 — 40회(=20초)로
#   늘린다. **락은 여전히 지우지 않는다**(다른 세션이 실제로 커밋 중일 수 있다).
_INDEX_LOCK_RETRIES = 40  # index.lock 은 지우지 않는다 — 대기 후 재시도만 한다(0.5s × 40 = 20초)

# ★2026-08-03 시토 — 실패한 커밋을 '다음 커밋'이 대신 밀어 올리는 자가치유 원장.
#   문제: safe_commit 이 ok=False 를 돌려줘도 호출자 대부분은 로그만 찍고 끝낸다. 그러면
#   그 산출물은 아무도 다시 시도하지 않아 며칠씩 작업트리에 고립된다(오늘 실사고 2건 —
#   월간운영계획 이틀·GAS 버전상태 사흘). 호출자를 하나씩 고치는 건 우회로만 늘린다(약속 L21).
#   해법: **모든 커밋이 지나가는 이 관문**에 실패 경로를 적어 두고, 다음번 아무 커밋이나
#   들어올 때 그것부터 따로 밀어 올린다. 저장소엔 하루에도 수십 번 커밋이 나므로 사실상
#   즉시 치유된다. 새 예약작업·새 감시기 0.
#   ★섞지 않는다: 잔여분은 **별도 커밋**으로 올린다. 지금 호출자의 커밋에 합치면 그게 바로
#   '남의 파일 쓸어담기'(2026-08-03 07:47 실사고)와 같은 짓이 된다.
_PENDING_LEDGER = "status/_safe_commit_pending.json"
_FLUSHING = False  # 재귀 가드 — 잔여분 커밋이 다시 잔여분 플러시를 부르지 않게

# ★2026-08-06 시토(Fable 설계검토 지적①) — 원장은 **일시 실패만** 기억한다.
#   선검증·훅가드·되돌림(낡은 사본)·도메인 차단은 스테이징 내용 자체의 문제라
#   재시도해도 100% 같은 이유로 다시 실패한다. 그런데도 원장이 이걸 기억하면
#   ⓐ절대 못 고칠 항목이 머리를 차지해 뒤 항목이 굶고 ⓑ이후 모든 커밋이 이
#   항목 재시도 비용(락+이력스캔)을 매번 문다. 아래 세 reason 접두사
#   ("선검증 실패(커밋 생성 안 함)"·"훅가드 위반(커밋 생성 안 함)"·
#   "되돌림 차단(커밋 생성 안 함)")는 모두 "(커밋 생성 안 함)" 공통 마커로
#   끝나므로 그 문자열 하나로 판별한다(각 reason 조립부 3곳 그대로 재사용 —
#   새 enum·새 분류 테이블 안 만듦). HEAD 경합·잠금 예외 등 "다시 하면 될 수
#   있는" 실패만 원장에 남는다.
_PERMANENT_FAILURE_MARK = "(커밋 생성 안 함)"
_LEDGER_MAX_ATTEMPTS = 5  # 일시 실패도 이 횟수 넘게 계속 실패하면 원장에서 뺀다(무한 재시도 금지)


def _is_permanent_failure(reason: str) -> bool:
    return _PERMANENT_FAILURE_MARK in (reason or "")

# 배10314 — append 로그 자동 포함 대상(비재귀 · status/ 바로 아래만).
_AUTO_INCLUDE_LOG_DIR = "status"
_AUTO_INCLUDE_LOG_SUFFIX = ".jsonl"

# ★2026-08-06 시토(Fable 설계검토 지적④) — 배10291 의 "최근 N분 내 동시편집" 경고는
#   경고만 하고 아무도 안 읽는 채널(stdout 뿐)이었고, 실사고 부류(옛 사본이 최신을
#   덮음)는 같은 날 넣은 낡은 사본 차단이 대신 잡는다(자기 자신이 방금 고친 파일에도
#   뜨는 오탐이 실측됨). 삭제한다 — 새 장치(낡은 사본 차단)를 넣었으니 낡은 걸
#   하나 없앤다(약속 L21 net-zero). _CONCURRENT_EDIT_WINDOW_MIN 상수도 함께 제거.
#
# 낡은 사본 판정에서 훑을 이력 깊이. 며칠 묵은 사본까지 잡되 경로당 git 호출이
# 선형으로 늘어나므로 얕게 둔다. ponytail: 30 이 모자라면 그때 올린다.
_STALE_COPY_SCAN_DEPTH = 30

# ★2026-08-06 시토(Fable 설계검토 지적②) — {"enabled": false} 같은 토글, 발송여부
#   플래그 등 status/ 바로 아래 작은 JSON 은 **정당하게** 과거 커밋 버전과 바이트가
#   똑같아진다(값의 가짓수가 적어 재사용됨). 낡은 사본 차단을 그대로 걸면 예약
#   파이프라인의 정상 커밋이 조용히 막힌다 — .bat 예약작업 호출자는 stdout 을 안
#   읽어 WP_ALLOW_REVERT 안내조차 못 보고, 그 실패가 원장에 쌓여 영구 재시도
#   루프가 된다. 기준(무엇을 "작다"로 볼지): status/ 바로 아래(비재귀 — worklog
#   등은 이미 §_auto_include_modified_logs 로 별도 처리), 확장자 .json, 4KB 이하
#   (토글·플래그류 상태 파일은 이 크기를 넘지 않는다 — 넘으면 콘텐츠성 데이터로
#   보고 차단 유지). 페이지(.html)·코드(.py 등)·문서는 이 예외 대상이 아니다.
_SMALL_STATE_JSON_DIR = "status/"
_SMALL_STATE_JSON_SUFFIX = ".json"
_SMALL_STATE_JSON_MAX_BYTES = 4096


def _is_small_state_json(path: str, root: Path) -> bool:
    if not (path.startswith(_SMALL_STATE_JSON_DIR)
            and path.count("/") == 1 and path.endswith(_SMALL_STATE_JSON_SUFFIX)):
        return False
    try:
        return (root / path).stat().st_size <= _SMALL_STATE_JSON_MAX_BYTES
    except OSError:
        return False


def _batch_blobs(root: Path, rev_path_pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """`<rev>:<path>` 여러 건을 `git cat-file --batch-check` 한 번으로 조회한다.

    ★2026-08-06 시토(Fable 설계검토 지적③) — 낡은 사본 판정이 이력 SHA 최대 30개를
    git ls-tree 로 하나씩 조회해(경로당 최대 31 서브프로세스, 전부 GitLock 안에서
    돎) 커밋 관문 체류시간을 늘렸다(이 저장소는 이미 index.lock 경합으로 실패한
    전례가 있다). batch-check 는 stdin 에 여러 줄을 한 번에 넣고 그대로 답 받으므로
    같은 조회를 서브프로세스 1회로 줄인다(31→2: git log 1회 + 이 함수 1회).
    출력은 입력과 1:1 순서로 대응한다(git 계약) — blob 이 아니거나 없으면 그 항목은
    결과 dict 에서 빠진다.
    """
    if not rev_path_pairs:
        return {}
    stdin = "\n".join(f"{rev}:{path}" for rev, path in rev_path_pairs) + "\n"
    r = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false", "cat-file", "--batch-check"],
        input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out: dict[tuple[str, str], str] = {}
    for pair, line in zip(rev_path_pairs, r.stdout.splitlines()):
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "blob":
            out[pair] = parts[0]
    return out


def _git(args: list[str], root: Path, env: dict | None = None,
         check: bool = False) -> subprocess.CompletedProcess:
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    return subprocess.run(
        # core.quotepath=false — git 기본값은 한글 등 비ASCII 경로를 "\355\201..." 로 인용해
        # 출력한다. 그러면 ⑤ 사후검증의 경로 비교가 전부 어긋나 정상 커밋도 '혼입'으로 오판하고,
        # _sync_live_index 의 ls-tree/ls-files 대조도 깨진다(=임시 인덱스 후처리 무력화 →
        # 2026-07-21 삭제 사고 경로 재개통). 한글 폴더가 표준인 저장소라 전 호출에 고정한다.
        # (2026-07-23 격리 재현으로 실측 — instagram/.../큐레이션_추천.md 가 혼입으로 오판됨)
        ["git", "-C", str(root), "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=run_env, check=check,
    )


def _git_out(args: list[str], root: Path, env: dict | None = None) -> str:
    r = _git(args, root, env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패(rc={r.returncode}): {r.stderr.strip()}")
    return r.stdout.strip()


def _rel(path, root: Path) -> str:
    """저장소 상대 posix 경로로 정규화(절대·상대 입력 모두 허용)."""
    p = Path(str(path))
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return Path(str(path)).as_posix()


def _tree_entries(rev: str, rel_paths: list[str], root: Path) -> dict[str, tuple[str, str]]:
    """ls-tree 로 지정 경로의 (mode, blob) 맵. rev 가 없으면 빈 맵."""
    out = _git(["ls-tree", "-r", rev, "--", *rel_paths], root)
    entries: dict[str, tuple[str, str]] = {}
    if out.returncode != 0:
        return entries
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3:
            entries[path.strip()] = (parts[0], parts[2])
    return entries


def _index_entries(rel_paths: list[str], root: Path) -> dict[str, tuple[str, str]]:
    """라이브 인덱스의 (mode, blob) 맵(stage 0 만)."""
    out = _git(["ls-files", "-s", "--", *rel_paths], root)
    entries: dict[str, tuple[str, str]] = {}
    if out.returncode != 0:
        return entries
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3 and parts[2] == "0":
            entries[path.strip()] = (parts[0], parts[1])
    return entries


def _tree_diff_status(tree_a: str, tree_b: str, root: Path) -> list[tuple[str, str]]:
    """두 트리 객체를 직접 비교(커밋 없이도 가능) — [(status, path), ...].

    diff-tree 는 커밋 없이 트리-트리 비교를 지원하므로 commit-tree/update-ref
    *이전*에도 검증할 수 있다(배10009 선검증의 핵심 — rename/copy 감지(-M/-C)는
    안 켜므로 status 는 항상 단일 문자 + 경로 1개 쌍으로만 나온다).
    """
    out = _git(["diff-tree", "--no-commit-id", "--name-status", "-r", "-z",
                tree_a, tree_b], root)
    if out.returncode != 0:
        raise RuntimeError(f"git diff-tree 실패(rc={out.returncode}): {out.stderr.strip()}")
    tokens = [t for t in out.stdout.split("\x00") if t]
    pairs: list[tuple[str, str]] = []
    for i in range(0, len(tokens) - 1, 2):
        pairs.append((tokens[i][:1], tokens[i + 1]))
    return pairs


# ── 훅가드 이식(2026-07-24 · 웰리 가드모듈 병합지도 §2 사각지대 봉합) ──────────
# safe_commit 은 commit-tree/update-ref 라 git 훅(.git/hooks/pre-commit)이
# 전혀 안 걸린다(위 _precheck_violations 주석 참조) — 그 훅 안 가드 10개가
# 전부 이 경로에서 미발화한다는 게 조사로 확인됐다(status/briefs/
# 웰리_가드모듈_병합지도_20260724.md §2). 1단계(비밀값·대량유실·공식값)에
# 이어 2단계로 계약이 같은 3개(활성 큐 항목 소멸·죽은 ERP 문서 앵커·알림 문구
# 내 시트 원본 링크)를 추가 이식한다 — 로직은 복제하지 않고 기존 가드
# 스크립트를 그대로 서브프로세스로 호출한다(L01, 단일 지점 재사용).
# 나머지 4개(incident·chatid_drift·reception_drift — phantom_delete는 이미
# 위 _precheck_violations 가 대체 판정 중)는 이번에도 이식하지 않는다 —
# incident 는 미확인(안 읽고 이식 금지), chatid_drift·reception_drift 는
# warn-only 라 지금 넣어도 득이 적고 잡음만 는다.
_HOOK_GUARDS = (
    ("secret", "precommit_secret_guard.py"),
    ("truncation", "precommit_truncation_guard.py"),
    ("enforcement", "precommit_enforcement_guard.py"),
    ("queue", "precommit_queue_guard.py"),
    ("erp_anchor", "precommit_erp_anchor_guard.py"),
    ("sheet_link", "precommit_sheet_link_guard.py"),
)


def _run_hook_guards(root: Path, index_path: Path) -> list[str]:
    """이식된 훅가드 3종을 임시 인덱스 기준으로 실행 — 위반 메시지 목록(비면 통과).

    각 가드는 내부적으로 `git diff --cached`/`git cat-file -p :path` 로 스테이징
    상태를 읽는다 — 둘 다 GIT_INDEX_FILE 환경변수를 그대로 존중하므로, 이 임시
    인덱스를 가리키게 하면 safe_commit 이 stage 한 내용만 정확히 본다(라이브
    인덱스는 안 건드림). cwd=root 로 실행해 각 가드의 내부 git 호출이 이 저장소를
    보게 한다.

    ★enforcement 가드의 GM 승인 우회([GM-approved])는 `.git/COMMIT_EDITMSG` 를
      읽는데(ssot/enforcement.py:_commit_message) safe_commit 경로엔 그 파일이
      "이번" 커밋 메시지를 담고 있지 않다(옛 커밋의 메시지이거나 비어있음) —
      알려진 한계. 단 enforcement_mode.json 기본값이 warn/off(둘 다 절대
      비차단)라 지금은 실질 위험 없음. mode=block 전환 시엔 이 한계부터 반드시
      보완할 것(§2 참고, 이 함수를 다시 고치지 말고 ssot/enforcement.py 쪽에
      commit_message 인자를 받는 진입점을 추가하는 방향).
    """
    run_env = dict(os.environ)
    run_env["GIT_INDEX_FILE"] = str(index_path)
    run_env["PYTHONUTF8"] = "1"
    violations: list[str] = []
    for label, fname in _HOOK_GUARDS:
        script = _SCRIPTS_DIR / fname
        if not script.exists():
            continue  # 가드 파일 없음 = fail-open(기존 훅 규약과 동일)
        try:
            r = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(root), env=run_env,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
        except Exception as exc:
            # 가드 실행 자체 실패 = fail-open(기존 훅 규약과 동일 — 가드 버그로
            # 전 커밋이 막히면 안 됨).
            print(f"[WARN] {label} 가드 실행 실패(fail-open): {type(exc).__name__}: {exc}")
            continue
        if r.returncode == 1:
            msg = (r.stderr or r.stdout or "").strip()
            violations.append(f"[{label}] {msg[:500]}")
    return violations


def _precheck_violations(head_tree: str, tree: str, rel_paths: list[str], root: Path) -> list[str]:
    """commit-tree/update-ref *이전* 선검증(배10009) — 무관 경로 혼입 + 유령 삭제 판정.

    ★기존 결함: 이 판정이 update-ref 이후에 돌아 탐지는 해도 이미 만들어진
      나쁜 커밋을 origin 까지 그대로 push 해버렸다(감지는 정확, 차단 실패).
      이 함수를 write-tree 직후·commit-tree 이전에 호출해 문제가 있으면
      커밋 자체를 만들지 않고 중단하도록 바로잡는다.
    ★판정 로직은 새로 짜지 않고 scripts/precommit_phantom_delete_guard.py 의
      "삭제로 표시됐는데 디스크엔 실존" 판정 방식을 그대로 재사용한다 — 그
      가드는 git 훅(pre-commit)에서만 발화하는데 safe_commit 은 commit-tree
      /update-ref 라 훅이 아예 안 걸린다(가드 사각지대).
    - 무관 경로 혼입: rel_paths 밖의 경로가 조금이라도 바뀌면 위반(추가·수정·
      삭제 무관 — safe_commit 계약상 지정 경로 밖은 절대 손대면 안 됨).
    - 유령 삭제: rel_paths 안이라도 삭제(D)로 표시됐는데 작업트리(디스크)에
      파일이 실존하면 위반. 디스크에도 없으면 의도된 정당한 삭제 — 통과.
    """
    violations: list[str] = []
    diff_pairs = _tree_diff_status(head_tree, tree, root)
    for status, path in diff_pairs:
        in_scope = any(path == rp or path.startswith(rp + "/") for rp in rel_paths)
        if not in_scope:
            violations.append(f"무관 경로 혼입: {status} {path}")
            continue
        if status == "D" and (root / path).exists():
            violations.append(f"유령 삭제(디스크엔 실존): {path}")

    # chro/cfo 보호 삭제(2026-08-04 — 인사 지원자 사진 반복삭제 사고 재발방지):
    # 삭제가 하나라도 chro/cfo 안이면서 이 커밋에 chro/cfo 밖 경로가 섞여 있으면
    # 차단한다. 커밋 전체가 chro/cfo 안에서만 이뤄지면(도메인 전용 호출) 통과.
    # ★2026-08-05 — CFO_DOMAIN_PATHS(아래) 3개는 아래 도메인 수정 차단이 삭제를
    #   포함해 항상 걸러내므로 여기서 제외한다(안 그러면 같은 파일에 메시지가
    #   두 번 뜬다 — GM 지시 "이중 발동 안 하는지 확인").
    protected_deletes = [p for s, p in diff_pairs
                          if s == "D" and any(p.startswith(pre) for pre in PROTECTED_DELETE_PREFIXES)
                          and p not in CFO_DOMAIN_PATHS and p not in CHRO_DOMAIN_PATHS]
    if protected_deletes:
        mixed_domain = any(not any(p.startswith(pre) for pre in PROTECTED_DELETE_PREFIXES)
                            for _, p in diff_pairs)
        if mixed_domain:
            extra = f" 외 {len(protected_deletes) - 1}건" if len(protected_deletes) > 1 else ""
            violations.append(f"보호된 삭제 차단(chro/cfo 도메인 혼입): {protected_deletes[0]}{extra}")

    # COO(시우)·CHRO(시로)·CFO(시뽀) 도메인 파일 "수정" 차단(2026-08-05 GM 편제 확정
    # — 위 COO_DOMAIN_PATHS/CHRO_DOMAIN_PATHS/CFO_DOMAIN_PATHS·DOMAIN_MODIFY_RULES
    # 주석 참조). 삭제뿐 아니라 추가·수정도 막는다 — 기본은 항상 차단이고, 사람이
    # 강행할 때만 통과(우회 로그는 _domain_modify_violation 안에서 남긴다).
    for role_label, contact, domain_paths, room, judgment_note in DOMAIN_MODIFY_RULES:
        v = _domain_modify_violation(diff_pairs, role_label, contact, domain_paths, room, judgment_note, root)
        if v:
            violations.append(v)

    # 일반 혼입 삭제 판정(2026-08-04 GM 근본분석 — 로직은 가드 모듈 단일 출처):
    # 비삭제 변경과 섞인 커밋의 삭제는 caller 가 rel_paths 에 **파일 단위로 정확히**
    # 나열한 것만 허용. 디렉터리 지정에 쓸려 들어온 삭제(원격 추가분이 이 PC 디스크에
    # 없어 D 로 보이는 부류)는 차단. 통과 방법: 삭제할 파일 경로를 직접 나열하거나
    # 삭제 전용 커밋으로 분리(전부 D 면 통과).
    del_paths = [p for s, p in diff_pairs if s == "D"]
    all_paths = [p for _, p in diff_pairs]
    for p in foreign_delete_violations(del_paths, all_paths, explicit_paths=rel_paths):
        violations.append(
            f"혼입 삭제 차단(명시 지정 없음): {p} — 삭제하려면 이 파일 경로를 직접 나열하거나 "
            f"삭제 전용 커밋으로 분리하세요"
        )
    return violations


def _sync_live_index(rel_paths: list[str], root: Path, old_head: str, new_sha: str) -> list[str]:
    """커밋 후 라이브 인덱스의 '옛 HEAD 기준' 항목만 새 커밋 기준으로 동기화한다.

    ★왜 필요한가(격리 테스트로 실측, 2026-07-23): 임시 인덱스로 커밋하면 라이브 인덱스는
      옛 HEAD 스냅샷 그대로 남는다 → 내가 새로 추가한 파일이 라이브 인덱스에선 '삭제(D)'로
      보이고, 그 상태에서 다른 세션이 커밋하면 내 파일이 '삭제'로 기록된다(2026-07-21
      AI하루 190파일 삭제 사고의 물리 경로). 기억 박제 2건("임시인덱스 뒤 인덱스 정리 필수")의
      코드 이행.

    ★안전장치: 라이브 인덱스 항목이 옛 HEAD 와 같은 경우(=다른 세션이 자기 것을 stage 해두지
      않은 경우)에만 동기화한다. 다르면 남의 staged 내용이므로 손대지 않는다.
      작업트리는 건드리지 않는다(update-index = 인덱스 전용 · reset/checkout 미사용).
    """
    old_map = _tree_entries(old_head, rel_paths, root)
    new_map = _tree_entries(new_sha, rel_paths, root)
    live_map = _index_entries(rel_paths, root)
    add_lines: list[str] = []
    remove_paths: list[str] = []
    for path in set(old_map) | set(new_map) | set(live_map):
        live = live_map.get(path)
        old = old_map.get(path)
        new = new_map.get(path)
        if live == new:
            continue
        if live != old:
            continue  # 다른 세션이 stage 해둔 자기 내용 — 절대 덮지 않는다
        if new:
            add_lines.append(f"{new[0]} {new[1]}\t{path}")
        else:
            remove_paths.append(path)
    synced = [ln.split("\t", 1)[1] for ln in add_lines] + remove_paths
    try:
        if add_lines:
            # stdin 은 반드시 bytes — text=True 로 주면 Windows 에서 "\n"→"\r\n" 로 번역돼
            # 경로 끝에 CR 이 붙고 update-index 가 조용히 실패한다(2026-07-23 격리 테스트로 실측).
            payload = ("\n".join(add_lines) + "\n").encode("utf-8")
            # ★2026-08-01(시토 · 배265) — index.lock 경합이면 기다렸다 재시도한다.
            #   왜: 한 방에 실패하면 라이브 인덱스에 **커밋 전 옛 사본이 남는다.**
            #   그 상태로 다른 세션이 커밋하면 방금 고친 코드가 되돌아가고, 자동
            #   reconcile 은 그 파일에서 매번 충돌해 push 가 막힌다(2026-08-01 실사고:
            #   옛 사본 37건 누적 → 자동 push 20회 연속 차단). 임시 인덱스 stage 가
            #   이미 쓰는 것과 같은 대기·재시도를 여기에도 준다(_stage_with_retry 동일 상수).
            for attempt in range(_INDEX_LOCK_RETRIES):
                r = subprocess.run(
                    ["git", "-C", str(root), "update-index", "--add", "--index-info"],
                    input=payload, capture_output=True, timeout=60,
                )
                if r.returncode == 0:
                    break
                err = r.stderr.decode("utf-8", "replace").strip()
                if "index.lock" not in err.lower() or attempt == _INDEX_LOCK_RETRIES - 1:
                    print(f"[WARN] 라이브 인덱스 동기화 실패(best-effort): {err}\n"
                          f"       ↳ 옛 사본이 인덱스에 남았을 수 있습니다. "
                          f"확인: git diff --cached --name-only")
                    break
                time.sleep(_INDEX_LOCK_WAIT_SEC)
        if remove_paths:
            _git(["update-index", "--force-remove", "--", *remove_paths], root)
    except Exception as exc:  # best-effort — 커밋은 이미 성공했다
        print(f"[WARN] 라이브 인덱스 동기화 실패(best-effort): {type(exc).__name__}: {exc}")
    return synced


def _stage_with_retry(rel_paths: list[str], root: Path, env: dict) -> None:
    """지정 경로만 임시 인덱스에 stage. index.lock 경합은 지우지 말고 대기 후 재시도."""
    last_err = ""
    for attempt in range(_INDEX_LOCK_RETRIES):
        r = _git(["add", "--", *rel_paths], root, env)
        if r.returncode == 0:
            return
        last_err = (r.stderr or r.stdout).strip()
        if "index.lock" not in last_err.lower():
            raise RuntimeError(f"git add 실패: {last_err}")
        time.sleep(_INDEX_LOCK_WAIT_SEC)
    raise RuntimeError(f"git add 실패(index.lock 대기 초과): {last_err}")


def _auto_include_modified_logs(root: Path, existing_rel_paths: list[str]) -> list[str]:
    """append 전용 로그(status/*.jsonl, 비재귀) 중 작업트리에서 바뀐 것만 자동 포함 후보로 반환.

    배10314(2026-07-27 · 시포 실측): worklog.jsonl 등은 호출자가 경로에 명시적으로
    안 넣으면 로컬에만 쌓여 GM 화면(작업 현황 로그 패널)이 멈춘다. *.jsonl 은 이미
    .gitattributes 에 merge=union(2026-06-19)이 걸려 있어 여러 세션이 동시에 이어써도
    무손실 병합되므로 자동 포함해도 안전하다. status/ 바로 아래(비재귀)만 대상으로
    좁혀 status/backups/ 스냅샷처럼 '로그가 아닌' *.jsonl 이 잘못 딸려오는 걸 막는다.
    """
    out = _git(["ls-tree", "--name-only", "HEAD", "--", f"{_AUTO_INCLUDE_LOG_DIR}/"], root)
    if out.returncode != 0:
        return []
    found: list[str] = []
    for name in out.stdout.splitlines():
        path = name.strip()
        if not path or not path.endswith(_AUTO_INCLUDE_LOG_SUFFIX):
            continue
        if path in existing_rel_paths:
            continue  # 호출자가 이미 지정 — 중복 처리 불필요
        diff = _git(["diff", "--name-only", "HEAD", "--", path], root)
        if diff.returncode == 0 and diff.stdout.strip():
            found.append(path)
    return found


def _detect_concurrent_edit_warnings(
    rel_paths: list[str], root: Path, tree: str, head: str,
) -> list[str]:
    """지정 경로가 '과거 커밋 버전과 바이트까지 똑같은 옛 사본'인지 판정한다.

    배10291(2026-07-26) 신설 → 2026-08-06 시토(배421) "낡은 사본 차단" 으로 대체.
    구 배10291 은 최근 N분 내 동시편집을 경고만 했는데 아무도 안 읽는 채널이었고
    (stdout 뿐), 실사고 부류(옛 사본이 최신 코드를 덮음)는 이 함수의 낡은 사본
    판정이 대신 잡는다 — 그래서 그 15분 창 경고 블록은 삭제했다(Fable 설계검토
    지적④, 약속 L21 net-zero: 새 장치를 넣었으니 낡은 것 하나를 없앤다).

    ★자동 포함되는 append 로그(_auto_include_modified_logs)는 이 판정 대상에서 뺀다 —
      그 카테고리는 설계상 여러 세션이 상시 동시 append 하는 게 정상이고 merge=union
      으로 이미 무손실 병합되므로 여기서 또 경고하면 잡음만 늘어난다. 그래서 호출자는
      auto-include 이전의 caller_rel_paths 만 넘긴다.
    ★차단이 기본이지만 예외 하나 — status/ 아래 작은 상태 JSON(§_is_small_state_json)
      은 정당하게 과거 버전과 같아질 수 있어 경고로만 낮춘다(Fable 설계검토 지적②).
    ★판정: 올리려는 내용이 '이 경로의 과거 커밋 버전과 바이트까지 똑같은지' 본다.
      같으면 나는 새로 고친 게 아니라 옛 사본을 그대로 다시 올리는 중이고, 그 사이
      커밋된 변경이 통째로 사라진다. blob 완전일치라 오탐이 사실상 없다.
      (2026-08-06 배421 실측: 워크트리에 08-04 19:21 옛 사본 9건이 남아 있었다.
       15분 창짜리 경고로는 이틀 지난 이 부류를 영원히 못 잡고, 직전 커밋 하나만
       비교해도 그 뒤로 커밋이 더 쌓이면 놓친다 — 그래서 이력 N개를 훑는다.)
    """
    def _blob_at(rev: str, path: str) -> str:
        r = _git(["ls-tree", rev, "--", path], root)
        if r.returncode != 0 or not r.stdout.strip():
            return ""
        parts = r.stdout.strip().split()
        return parts[2] if len(parts) >= 3 else ""

    warnings: list[str] = []
    reverts: list[str] = []
    for path in rel_paths:
        mine_blob = _blob_at(tree, path)
        if not mine_blob:
            continue

        history = _git(["log", "--format=%H", f"-{_STALE_COPY_SCAN_DEPTH}", head, "--", path], root)
        if history.returncode != 0 or not history.stdout.strip():
            continue
        shas = history.stdout.strip().splitlines()
        # Fable 지적③ — 이력 SHA 최대 30개를 git ls-tree 로 하나씩 조회하던 걸(경로당
        # 최대 31 서브프로세스) batch-check 한 번으로 합친다(31→2: 위 git log + 아래 1회).
        blob_map = _batch_blobs(root, [(head, path)] + [(sha, path) for sha in shas[1:]])
        head_blob = blob_map.get((head, path), "")
        if mine_blob == head_blob:
            continue  # 최신 내용과 같음 — 낡은 사본 아님
        for sha in shas[1:]:          # shas[0] = 현재 내용을 만든 커밋
            if blob_map.get((sha, path)) != mine_blob:
                continue
            subject = _git_out(["log", "-1", "--format=%s", shas[0]], root)[:70]
            when = _git_out(["log", "-1", "--format=%ad", "--date=format:%m-%d %H:%M",
                             shas[0]], root)
            body = (
                f"{path} — 올리려는 내용이 옛 커밋 {sha[:9]} 버전과 똑같습니다. 그 뒤 "
                f"{when} 커밋 {shas[0][:9]}({subject}) 이 이 파일을 바꿨는데, 이대로 "
                f"올리면 그 변경이 통째로 사라집니다."
            )
            if _is_small_state_json(path, root):
                warnings.append(
                    f"[낡은 사본 경고] {body} (작은 상태 JSON — 정상적으로 과거 값과 "
                    f"같아질 수 있어 경고만 하고 커밋은 진행합니다.)"
                )
            else:
                reverts.append(
                    f"[낡은 사본 차단] {body} 작업트리 사본이 낡았습니다 — 최신 내용을 "
                    f"받아 다시 고쳐 올리세요. 되돌리기가 의도라면 WP_ALLOW_REVERT=1 로 다시 실행."
                )
            break
    return warnings, reverts


_RECENT_TOUCH_SEC = 900   # 15분 — 이 안에 건드린 파일이 HEAD와 같으면 '편집 유실' 의심

def _recently_touched(rel_paths: list, root: Path) -> list:
    """지정 경로 중 최근 _RECENT_TOUCH_SEC 안에 수정된 것들(디렉터리는 그 안 파일까지).

    '변경 없음'과 짝으로만 쓴다 — 방금 건드렸는데 내용이 HEAD와 같다면
    내 편집이 사라졌을 가능성이 있다는 신호다(위 호출부 주석 참조).
    판단 재료일 뿐 차단하지 않는다. 파일이 없거나 stat 실패는 조용히 건너뛴다.
    """
    import time as _time
    now = _time.time()
    out = []
    for rel in rel_paths:
        p = root / rel
        try:
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file() and now - f.stat().st_mtime <= _RECENT_TOUCH_SEC:
                        out.append(_rel(f, root))
                        break        # 폴더당 한 번만 알리면 충분
            elif p.is_file() and now - p.stat().st_mtime <= _RECENT_TOUCH_SEC:
                out.append(rel)
        except OSError:
            continue
    return out


def _ledger_path(root: Path) -> Path:
    return root / _PENDING_LEDGER


def _ledger_read(root: Path) -> list:
    try:
        return json.loads(_ledger_path(root).read_text(encoding="utf-8"))
    except Exception:
        return []


def _ledger_write(root: Path, entries: list) -> None:
    try:
        p = _ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")
    except Exception:
        pass  # 원장 기록 실패가 본 커밋을 막지 않는다(fail-soft)


def _ledger_remember(root: Path, rel_paths: list, message: str, reason: str) -> None:
    """커밋 실패분을 원장에 적는다. 같은 경로는 갱신만(무한 증식 방지)."""
    entries = [e for e in _ledger_read(root)
               if sorted(e.get("paths") or []) != sorted(rel_paths)]
    entries.append({"paths": rel_paths, "message": message, "reason": reason[:200], "attempts": 0})
    _ledger_write(root, entries[-50:])  # 상한 — 원장 자체가 새는 곳이 되지 않게


def _flush_pending(root: Path, push: bool) -> list:
    """원장에 쌓인 지난 실패분을 **각각 별도 커밋으로** 밀어 올린다.

    지금 호출자의 커밋에 절대 합치지 않는다 — 합치면 '남의 파일 쓸어담기'가 된다.
    이미 커밋됐거나 사라진 경로는 '변경 없음'으로 통과하므로 원장에서 조용히 빠진다.
    """
    global _FLUSHING
    entries = _ledger_read(root)
    if not entries or _FLUSHING:
        return []
    # ★2026-08-03 시토 — **급한 자리에서는 치유하지 않는다.** post_commit_push 의 기계산출물
    #   선커밋처럼 '락이 잡혀 있으면 바로 포기'하도록 일부러 짧은 타임아웃(GIT_LOCK_ACQUIRE_TIMEOUT)을
    #   물려 부르는 경로가 있다. 그 자리에서 치유를 시도하면 2초 만에 실패하고 원장에 실패 사유만
    #   덧칠돼 영영 안 빠진다(발효 직후 실측 — 3건이 그 상태로 남았다).
    #   치유는 **여유 있는 일반 커밋**에서만 한다. 저장소엔 하루 수십 번 그런 커밋이 나므로
    #   기회는 충분하다 — 급할 때 억지로 하지 않는 게 오히려 빨리 낫는다.
    try:
        if int(os.environ.get("GIT_LOCK_ACQUIRE_TIMEOUT", "90")) < 30:
            return []
    except Exception:  # noqa: BLE001
        pass
    # ★2026-08-03 시토 — **한 번에 1건만.** 발효 직후 실측에서 3건을 연달아 치유하느라
    #   평범한 커밋 하나가 2분 넘게 붙잡혔다(각 건이 락을 최대 90초 기다린다). 치유가 본 작업을
    #   느리게 만들면 그 자체가 새 문제다. 저장소엔 하루 수십 번 커밋이 나므로 1건씩만 밀어도
    #   금세 빠진다 — 급하지 않은 일을 급하게 하지 않는다.
    entries, deferred = entries[:1], entries[1:]

    _FLUSHING = True
    healed, left = [], []
    try:
        for e in entries:
            paths, msg = e.get("paths") or [], e.get("message") or "(지난 실패분 재시도)"
            if not paths:
                continue
            try:
                r = safe_commit(paths, f"{msg} [지연 재시도]", holder="safe_commit_flush",
                                repo_root=str(root), push=push)
            except Exception as ex:  # noqa: BLE001
                e["reason"] = f"재시도 예외: {type(ex).__name__}"
                r = None
            if r and r.get("ok"):
                healed.append({"paths": paths, "sha": r.get("sha", "")})
                continue
            if r is not None:
                e["reason"] = str(r.get("reason", ""))[:200]
            # ★지적① — 선검증·훅가드·되돌림·도메인 차단은 다시 해도 100% 같은 이유로
            #   또 실패한다(스테이징 내용 자체의 문제). 원장에 다시 넣지 않고 버린다.
            if _is_permanent_failure(e["reason"]):
                print(f"[자가치유] 정책 차단 — 재시도 불가라 원장에서 제거: "
                      f"{paths} — {e['reason'][:80]}")
                continue
            # 일시 실패는 재시도 상한까지만 보존. 넘으면 버린다(무한 재시도 금지).
            e["attempts"] = e.get("attempts", 0) + 1
            if e["attempts"] >= _LEDGER_MAX_ATTEMPTS:
                print(f"[자가치유] 재시도 {_LEDGER_MAX_ATTEMPTS}회 초과 — 원장에서 제거: "
                      f"{paths} — {e['reason'][:80]}")
                continue
            left.append(e)
    finally:
        _FLUSHING = False
        # ★지적① — 이번에 실패한 항목은 맨 앞이 아니라 **뒤**로 보낸다(deferred 먼저
        #   쓴다). 맨 앞에 두면(구: left + deferred) 못 고치는 항목이 계속 머리를
        #   차지해 뒤 항목들이 굶는다.
        _ledger_write(root, deferred + left)
    return healed


def safe_commit(
    paths,
    message: str,
    holder: str = "safe_commit",
    repo_root=None,
    push: bool = True,
    max_retries: int = _MAX_RETRIES,
) -> dict:
    """지정 경로만 담아 HEAD 재검증 + update-ref CAS 로 원자 커밋한다.

    paths: 커밋할 경로 목록(절대·상대 모두 허용). 이 목록 밖 파일은 절대 커밋되지 않는다.
    push:  True 면 커밋 성공 후 기존 post_commit_push.py 호출(update-ref 는 post-commit
           훅을 발화시키지 않으므로 명시 호출). 실패해도 커밋은 유지(fail-open).
    반환:  {"ok","committed","sha","attempts","changed","foreign","reason"}
           - committed=False, ok=True → 변경 없음(무해 통과)
           - foreign 이 비어있지 않으면 혼입 발생 → ok=False (보고용)
    """
    root = Path(repo_root) if repo_root else ROOT
    rel_paths = [_rel(p, root) for p in paths if str(p).strip()]
    result = {"ok": False, "committed": False, "sha": "", "attempts": 0,
              "changed": [], "foreign": [], "hook_violations": [], "index_synced": [],
              "auto_included": [], "concurrent_edit_warnings": [], "reverts": [],
              "reason": ""}
    if not rel_paths:
        result["ok"] = True
        result["reason"] = "대상 경로 없음"
        return result

    index_path = root / ".git" / f"safe_commit_index_{os.getpid()}"
    env = {"GIT_INDEX_FILE": str(index_path)}

    # ★자가치유 — 지난 실패분을 **먼저 별도 커밋으로** 밀어 올린다(락 잡기 전에 호출해야
    #   재귀 진입 시 같은 락을 두 번 잡지 않는다). 이 커밋에 섞지 않는다.
    healed = _flush_pending(root, push)
    if healed:
        print(f"[자가치유] 지난 커밋 실패분 {len(healed)}건 밀어 올림 — "
              + ", ".join(h["sha"][:9] for h in healed if h.get("sha")))

    try:
        with GitLock(holder=holder, repo_root=str(root)):
            # 배10314 — 호출자가 지정한 경로는 동시편집 경고(배10291) 판정 대상으로 그대로
            # 남기고, append 로그는 여기서 rel_paths 에 편입시켜 이후 모든 검증(선검증·
            # 훅가드·사후재확인)이 "지정 경로"로 자연히 인식하게 한다(별도 예외 분기 없음).
            caller_rel_paths = list(rel_paths)
            auto_paths = _auto_include_modified_logs(root, rel_paths)
            if auto_paths:
                rel_paths = list(dict.fromkeys(rel_paths + auto_paths))
                result["auto_included"] = auto_paths

            for attempt in range(1, max_retries + 1):
                result["attempts"] = attempt
                # ① 임시 인덱스를 HEAD 트리로 시작(라이브 index 복사 금지)
                index_path.unlink(missing_ok=True)
                head = _git_out(["rev-parse", "HEAD"], root)
                _git_out(["read-tree", "HEAD"], root, env)

                # ② 지정 경로만 stage
                _stage_with_retry(rel_paths, root, env)
                tree = _git_out(["write-tree"], root, env)

                head_tree = _git_out(["rev-parse", f"{head}^{{tree}}"], root)
                if tree == head_tree:
                    result["ok"] = True
                    result["reason"] = "변경 없음(nothing to commit)"
                    # ★ 2026-07-28 시모 — '변경 없음'은 두 가지가 겹쳐 있다.
                    #   (가) 이미 반영돼 있어 커밋할 게 없다 = 정상(멱등 재실행)
                    #   (나) **내가 방금 고쳤는데 그 편집이 남의 커밋에 덮여 사라졌다** = 사고
                    #   지금까지 둘 다 똑같이 [OK] 로 찍혀서 (나)를 조용히 통과시켰다.
                    #   2026-07-28 하루에 두 번 발생했고(M1 화면·퍼널 GAS), 한 번은 놓쳐서
                    #   라이브에는 있고 저장소엔 없는 상태로 몇 시간 갔다.
                    #   가르는 신호 = **최근에 파일을 건드렸는데 내용이 HEAD와 똑같다.**
                    #   방금 편집한 파일이 HEAD와 같다는 건 편집이 사라졌다는 뜻이다.
                    #   차단하지 않는다(정상 케이스가 훨씬 많다) — 대신 출력에서 갈라 보여준다.
                    result["suspect_lost_edit"] = _recently_touched(rel_paths, root)
                    return result

                # ②-b 선검증(배10009) — commit-tree/update-ref *이전* 트리-트리 비교로
                # 무관 경로 혼입·유령 삭제를 판정한다. 걸리면 커밋 자체를 만들지 않고
                # 즉시 중단(재시도 안 함 — HEAD 레이스가 아니라 스테이징 내용 자체의
                # 문제라 재시도해도 그대로 재현된다).
                violations = _precheck_violations(head_tree, tree, rel_paths, root)
                if violations:
                    result["foreign"] = violations
                    result["reason"] = (
                        f"선검증 실패(커밋 생성 안 함) — {violations[0]}"
                        + (f" 외 {len(violations) - 1}건" if len(violations) > 1 else "")
                    )
                    return result

                # ②-c 훅가드 이식(2026-07-24) — secret·truncation·enforcement.
                # 같은 임시 인덱스를 GIT_INDEX_FILE 로 넘겨 스테이징 내용만 정확히
                # 검사한다. 걸리면 ②-b 와 동일하게 커밋 자체를 만들지 않고 중단.
                hook_violations = _run_hook_guards(root, index_path)
                if hook_violations:
                    result["hook_violations"] = hook_violations
                    result["reason"] = (
                        f"훅가드 위반(커밋 생성 안 함) — {hook_violations[0]}"
                        + (f" 외 {len(hook_violations) - 1}건" if len(hook_violations) > 1 else "")
                    )
                    return result

                # ②-d 동시편집 경고(배10291) — 차단하지 않는다. 호출자가 지정한 경로만
                # 대상(caller_rel_paths — auto-include 된 append 로그는 상시 동시편집이
                # 정상이라 대상에서 뺀다). 발견돼도 result 와 stdout 에만 남기고 계속 진행.
                # ★되돌림(reverts)만은 차단한다 — blob 완전일치라 오탐이 없고, 이 부류가
                #   실제로 최신 코드를 지운 사고를 냈다(§_detect_concurrent_edit_warnings).
                edit_warnings, reverts = _detect_concurrent_edit_warnings(
                    caller_rel_paths, root, tree, head)
                if reverts and os.environ.get("WP_ALLOW_REVERT") != "1":
                    result["reverts"] = reverts
                    result["reason"] = (
                        f"되돌림 차단(커밋 생성 안 함) — {reverts[0]}"
                        + (f" 외 {len(reverts) - 1}건" if len(reverts) > 1 else "")
                    )
                    return result
                if edit_warnings:
                    result["concurrent_edit_warnings"] = edit_warnings
                    for w in edit_warnings:
                        print(f"[WARN] {w}")

                # ③ commit-tree 직전 HEAD 재검증 — 움직였으면 통째로 재시도(스테일 트리 차단)
                head_now = _git_out(["rev-parse", "HEAD"], root)
                if head_now != head:
                    time.sleep(_RETRY_WAIT_SEC)
                    continue

                new_sha = _git_out(["commit-tree", tree, "-p", head, "-m", message], root)

                # ④ CAS — 경쟁 커밋이 끼어들었으면 update-ref 가 실패한다(원자 갱신)
                upd = _git(["update-ref", "HEAD", new_sha, head], root)
                if upd.returncode != 0:
                    time.sleep(_RETRY_WAIT_SEC)
                    continue

                result["sha"] = new_sha
                result["committed"] = True

                # ④-b 라이브 인덱스 동기화(임시 인덱스 커밋의 필수 후처리 — 위 주석 참조)
                result["index_synced"] = _sync_live_index(rel_paths, root, head, new_sha)

                # ⑤ 사후 재확인(방어적 — 선검증②-b 와 같은 트리라 정상 상황에선 항상 통과.
                # commit-tree/update-ref 가 그 사이 트리를 바꿀 수는 없으니 여기서 다시
                # 걸리는 건 이례적이지만, 걸리면 여전히 ok=False 로 push 를 막는다)
                changed = [ln for ln in _git_out(
                    ["diff-tree", "--no-commit-id", "--name-only", "-r", new_sha], root
                ).splitlines() if ln.strip()]
                result["changed"] = changed
                foreign = [c for c in changed
                           if not any(c == rp or c.startswith(rp + "/") for rp in rel_paths)]
                if not changed:
                    result["foreign"] = foreign
                    result["reason"] = "커밋에 변경 파일 0건(검증 실패)"
                elif foreign:
                    result["foreign"] = foreign
                    result["reason"] = f"무관 경로 혼입 {len(foreign)}건(사후 재확인 — 이례적)"
                else:
                    result["ok"] = True
                    result["reason"] = f"커밋 완료 {len(changed)}건"
                break
            else:
                result["reason"] = f"HEAD 경합 {max_retries}회 재시도 초과(커밋 안 함)"
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            index_path.unlink(missing_ok=True)
        except Exception:
            pass

    # ★자가치유 — 실패했으면 원장에 적어 둔다. 다음 커밋이 대신 밀어 올린다.
    #   '변경 없음'(committed=False·ok=True)은 실패가 아니므로 적지 않는다.
    #   플러시 중 실패는 _flush_pending 이 이미 원장에 남기므로 여기서 또 적지 않는다(중복 방지).
    if not result["ok"] and not _FLUSHING and not _is_permanent_failure(result.get("reason", "")):
        _ledger_remember(root, rel_paths, message, result.get("reason", ""))
        print(f"[자가치유] 커밋 실패 — 원장에 적어 뒀습니다. 다음 커밋이 재시도합니다: "
              f"{result.get('reason','')[:80]}")

    # ★배10009: committed 만 보면 혼입이 감지돼(ok=False) 이미 만들어진 나쁜 커밋이
    # 그대로 push 될 수 있었다 — 검증 통과 여부(ok)를 게이트로 쓴다.
    if result["ok"] and push:
        # ── ① ad-hoc 자동기록(2026-07-25 시우 · GM 지적 "상태줄에 안 나온다") ──
        # safe_commit 은 commit-tree/update-ref 라 .git/hooks/post-commit 이 발화하지 않는다.
        # 그 훅의 ①단계(auto_log_adhoc_to_queue.py)만 이식에서 빠져 있었다 — pre-commit 가드는
        # 함수로 이식했고 push 는 아래에서 명시 호출하는데 이것만 누락됐다.
        # 결과(역설): 맨손 commit 금지 규칙을 지킨 세션일수록 한 일이 G1·상태줄에서 사라지고,
        # 규칙을 어긴 쪽만 자동기록됐다. 실측 2026-07-25 — 그날 자동기록 37척 중 33척이 예약
        # 스크립트(맨손 commit)였고 safe_commit 으로 올린 C-Level 커밋은 0척이었다.
        # ★교착 없음: 이 자리는 위 `with GitLock(...)` 을 이미 빠져나온 뒤다. auto_log 는 자기
        #   GitLock 을 따로 잡고, 못 잡으면 within-parent-lock 으로 보류한다(fail-open).
        # ★순서: 훅과 동일하게 자동기록 → push. 그래야 자동기록이 만든 커밋까지 같이 올라간다.
        # ★배106(2026-07-25 시토 · 웰리 결정): 방금 만든 커밋 sha 를 명시 인자로 넘긴다 —
        #   인자 없이 HEAD 를 읽으면 이 호출 전에 다른 세션 커밋이 끼어들 때 남의 커밋을
        #   기록한다(레이스). 기록 계층은 auto_log 쪽에 있다: ①[umbrella:ID] 명시 흡수
        #   → ②그 역할 IN_PROGRESS 배 note 흡수 → ③상설 일일 ad-hoc 배 1척 갱신
        #   (도배 방지 · 시포 배10014 방식 재사용). 여기(관문)는 호출만 한다(L21).
        try:
            subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "auto_log_adhoc_to_queue.py"),
                 result["sha"]],
                cwd=str(root), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except Exception as exc:  # 기록 실패가 커밋·push 를 막지 않는다(fail-open, 훅 규약 동일)
            print(f"[WARN] ad-hoc 자동기록 건너뜀: {type(exc).__name__}: {exc}")
        try:
            subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "post_commit_push.py")],
                cwd=str(root), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except Exception as exc:  # push 실패는 커밋을 되돌리지 않는다(fail-open)
            print(f"[WARN] push 실패(커밋은 유지 — 다음 워처가 올림): {type(exc).__name__}: {exc}")
        _reply_to_feedback_in_message(message)
    return result


# ── 고치면 신고한 사람에게 회신이 따라간다 (GM 지적 2026-08-07 · 시토) ─────────────
# GM: "FB260806-192852 이건은 바로 처리 가능했을 것 같은데?" — 실제로 접수 15분 만에 고쳐
# 라이브까지 나갔는데, 신고자 화면엔 하루가 지나도 '확인중'이었고 회신도 "메모를 아직 남기지
# 않았다"는 빈 문구였다. **고친 사람이 회신을 안 채운 것**이 진짜 결함이다(받음→끝냄 짝).
# 사람 기억에 맡기면 또 빠진다(약속 L02) → 모든 커밋이 지나는 이 관문에 얹는다(L21).
#   커밋 메시지에 접수ID(FB260806-192852 꼴)가 있으면 그 메시지를 그대로 회신으로 적고
#   처리완료로 닫는다. 문구를 새로 지어내지 않는다 — 고친 사람이 쓴 커밋 제목이 곧 회신이다.
_FEEDBACK_ID_RE = re.compile(r"\bFB\d{6}-\d{6}\b")


def feedback_ids_in(message: str) -> list[str]:
    """커밋 메시지에서 실무진 피드백 접수ID를 뽑는다(중복 제거·등장순)."""
    seen, out = set(), []
    for m in _FEEDBACK_ID_RE.findall(message or ""):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def feedback_reply_from(message: str, today: str) -> str:
    """커밋 메시지 → 신고자에게 보낼 회신 한 줄. 첫 줄(제목)만 쓰고 접수ID·타입 접두는 지운다."""
    head = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    head = _FEEDBACK_ID_RE.sub("", head)
    head = re.sub(r"^\s*\w+(\([^)]*\))?\s*:\s*", "", head)      # 'fix(cpo): ' 같은 접두 제거
    head = head.strip(" -—·:")
    return (f"[{today} 처리완료] {head}. 확인해 보시고 아직 그대로면 다시 남겨주세요."
            if head else f"[{today} 처리완료] 요청하신 내용을 반영했습니다.")


def _reply_to_feedback_in_message(message: str) -> None:
    """커밋 메시지에 접수ID가 있으면 그 피드백을 처리완료로 닫고 회신을 채운다.
    실패해도 커밋·push 를 되돌리지 않는다(fail-open — 회신 실패가 배포를 막으면 안 된다)."""
    ids = feedback_ids_in(message)
    if not ids:
        return
    try:
        sys.path.insert(0, str(_SCRIPTS_DIR / "collectors"))
        from cpo_staff_feedback_watch import push_feedback_updates  # type: ignore
        today = datetime.now().strftime("%Y-%m-%d")
        memo = feedback_reply_from(message, today)
        _, err = push_feedback_updates(
            [{"id": i, "status": "처리완료", "memo": memo} for i in ids])
        print(f"[피드백 회신] {', '.join(ids)} — " + ("실패: " + err if err else "처리완료로 닫음"))
    except Exception as exc:
        print(f"[WARN] 피드백 회신 건너뜀: {type(exc).__name__}: {exc}")


def _repair_batch_line_endings(paths: list[str]) -> list[str]:
    """커밋에 담기는 .bat/.cmd 가 LF 로 저장돼 있으면 CRLF 로 되돌린다(고친 경로 목록 반환).

    왜 여기 있나 — cmd.exe 는 배치 파일을 CRLF 로 읽는다. LF 로 저장되면 예약작업이
    '성공(반환값 0)'으로 보고되면서 실제로는 아무 일도 안 하는 상태가 된다. 조용한
    실패라 어떤 감시기도 잡지 못한다:
      · 2026-07-30 — Start-AI 계열 7종 + wellperion.bat 이 LF 로 저장돼 C-Level 부팅 전멸.
      · 2026-08-05 — cpo_inquiry_snapshot.bat 이 LF 로 저장돼 3분 주기 잡이 13:06 부터
        5시간 멈췄다. 그 잡에 실무진 피드백 감시기가 얹혀 있어 오전 10시 신고 3건이
        접수 상태 그대로 방치됐고, GM 이 먼저 발견하셨다.
    .gitattributes 의 `*.bat text eol=crlf` 는 git 체크아웃만 보호한다 — 편집 도구가
    파일을 직접 쓰면 작업트리는 LF 로 남고, git 은 정규화 때문에 차이를 보여주지도
    않는다(그래서 눈으로도 안 보인다). 커밋은 모든 세션이 지나가는 관문이라 여기서
    되돌린다(새 검사기·새 훅 신설 없음).
    """
    fixed: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.suffix.lower() not in (".bat", ".cmd") or not p.is_file():
            continue
        try:
            data = p.read_bytes()
            if data.count(b"\r\n") == 0 and data.count(b"\n") > 0:
                p.write_bytes(data.replace(b"\n", b"\r\n"))
                fixed.append(raw)
        except OSError:
            continue  # 잠겼거나 읽을 수 없으면 커밋을 막지 않는다(경보만 없는 셈)
    return fixed


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="스테일 트리 차단 안전 커밋(HEAD 재검증 + update-ref CAS)")
    p.add_argument("-m", "--message", required=True, help="커밋 메시지")
    p.add_argument("--holder", default="safe_commit_cli", help="락 holder 이름")
    p.add_argument("--no-push", action="store_true", help="커밋만 하고 push 하지 않음")
    p.add_argument("paths", nargs="+", help="커밋할 경로(이 목록 밖은 절대 안 담김)")
    args = p.parse_args()

    for _p in _repair_batch_line_endings(args.paths):
        print(f"  ~ 줄끝 복구(.bat 은 CRLF 여야 cmd 가 읽는다): {_p}")

    res = safe_commit(args.paths, args.message, holder=args.holder, push=not args.no_push)
    # ★ '변경 없음'인데 방금 건드린 파일이 있으면 [OK] 로 찍지 않는다(2026-07-28 시모).
    #   그 조합은 '내 편집이 남의 커밋에 덮여 사라졌다'는 뜻일 수 있고, 실제로 그날 두 번 났다.
    _suspect = res.get("suspect_lost_edit") or []
    _tag = "OK" if res["ok"] else "FAIL"
    if res["ok"] and _suspect:
        _tag = "확인필요"
    print(f"[{_tag}] {res['reason']} "
          f"(시도 {res['attempts']}회 · sha={res['sha'][:9] or '-'})")
    if _suspect:
        print("  ! 방금 고친 파일인데 저장소 내용과 똑같습니다 — 편집이 덮여 사라졌을 수 있습니다:")
        for s in _suspect:
            print(f"      {s}")
        print("  → 파일을 열어 내 수정이 남아 있는지 눈으로 확인하세요. "
              "없으면 다시 넣고 커밋해야 합니다(문자열 검색 말고 실제 코드 줄로 확인).")
    for c in res["changed"]:
        print(f"  + {c}")
    for f in res["foreign"]:
        print(f"  ! 혼입 {f}")
    for h in res["hook_violations"]:
        print(f"  ! 훅가드 {h}")
    for a in res["auto_included"]:
        print(f"  ~ 자동포함(append 로그) {a}")
    for w in res["concurrent_edit_warnings"]:
        print(f"  ? {w}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
