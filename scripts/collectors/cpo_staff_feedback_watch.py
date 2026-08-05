# -*- coding: utf-8 -*-
"""
cpo_staff_feedback_watch.py — 실무진 피드백이 들어오면 그 자리에서 담당 C-Level '배'로 띄운다.

왜 있나 (2026-07-25 GM 지시)
  "이건은 발생할때마다 체크해서 해줄순없나?"
  실무진 피드백(회원관리 화면 상단 💬 버튼 → 실무진피드백.html → GAS staff_feedback_submit)은
  접수 즉시 업무보고방에 1줄 알림이 간다. 그런데 알림은 흘러가고, 아무도 배로 옮기지 않으면
  '접수' 상태 그대로 시트에 남는다 — 실제로 7/24~25 접수 8건 중 6건이 아무 배도 없이 방치돼
  있었고, 그중 3건은 같은 증상(CONTACT 유실)의 반복 신고였다. 큐에 없으면 항로에도 없다(약속 L15).

무엇을 하나
  1. staff_feedback_list 로 전체 피드백을 읽는다(읽기 전용).
  2. 처리상태가 아직 '접수'인 건 중 배가 없는 것만 status/_queue.json 에 배로 올린다.
     - 대조키 = 접수ID(FB…). 행번호로 찾지 않는다(실고객 오삭제 사고와 동종 위험 회피).
     - 활성 큐 + 아카이브 양쪽을 보고 중복을 막는다(한 피드백 = 한 배).
     - 담당은 화면(업무 구분)·종류 키워드로 가른다(route_clevel, 2026-07-27 배10309) —
       애매하면 시포(cpo)로 보낸다(안전 폴백). 화면이 어디든 무조건 시포로 서던 문제 수정.
  3. 하트비트를 남긴다(가동 신호는 배가 아니라 하트비트로 — 배9995 도배 사고 교훈).
  4. 나가는 쪽(2026-07-27 웰리 지시 — "반쪽만 자동인 루프는 자동이 아니다") — 접수ID로 만들어진
     배의 status 변화를 그대로 시트 처리상태 칸에 반영한다(sync_feedback_status). 처음엔 DONE
     한 단계만 반영해 배가 IN_PROGRESS 인 동안은 실무진 화면에 접수 여부조차 안 보였다 — 유경민님
     피드백 2건(배10205·10207)이 4일째 무응답으로 남은 원인(웰리 실측 2026-07-28). 지금은 3단계
     모두 반영한다: 배 생성 시 '접수됨' → status IN_PROGRESS 면 '확인중' → status DONE 이면
     '처리완료'(문구 조립은 기존 build_staff_reply 그대로 — 회귀 0).
     멱등 판단은 그때그때 fetch 한 라이브 시트의 현재 처리상태 '단계 순위'로 한다(이미 같은
     단계거나 더 앞선 단계면 건너뜀 — 반복 덮어쓰기 금지) — 로컬 마커에 기대지 않는다.

무엇을 안 하나
  - 알림을 새로 보내지 않는다. 접수 알림은 GAS 가 이미 보낸다(중복 발신 금지).
  - status/_queue.json 을 회신 때문에 고치지 않는다(대표님 지시 — 큐는 웰리 중앙 갱신 전용).
    회신은 시트에만 쓴다. 배 상태(DONE)는 이미 다른 경로로 정해진 값을 읽기만 한다.
  - 새 예약작업을 만들지 않는다. 3분 주기 cpo_inquiry_snapshot.bat 에 얹어 같이 돈다.

실행: python scripts/collectors/cpo_staff_feedback_watch.py [--dry-run] [--no-push]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from queue_lock import mutate_queue, load_queue  # noqa: E402
from module_heartbeat import record_heartbeat, last_heartbeat  # noqa: E402
from assign_short_no import next_short_no  # noqa: E402
from clevel_colors import nickname as clevel_nickname  # noqa: E402

KST = timezone(timedelta(hours=9))

MODULE_ID = "cpo-staff-feedback-watch"
ARCHIVE_PATH = ROOT / "status" / "_queue_archive.json"

# 주소·토큰 정본 = .deploy-funnel-v2/Survey.js(FUNNEL_EXEC_URL · INTAKE_SUBMIT_TOKEN).
# 실무진피드백.html 이 쓰는 것과 같은 값 — 자체 발명 아님.
FB_GAS_URL = ("https://script.google.com/macros/s/"
              "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec")
FB_TOKEN = "wlp_intake_9f4c1b7e2a63"

OPEN_STATUS = ("PENDING", "IN_PROGRESS")
# 급한정도 → 배 무게. 값이 없거나 모르는 값이면 보통으로 본다.
# ★2026-07-27 GM 결정(①안 "급함이면 다른 배보다 먼저 집는다") — 급한정도를 무게 칸에 넣지 않는다.
#   전에는 급함→🛳️크루즈로 무게 칸에 밀어넣었다. 그런데 자율 착수 규칙은 "🛳️크루즈는 무거우니
#   안전하게 멈춤(park)"이라 ★급하다고 표시할수록 자율 착수에서 빠지는★ 정반대 동작이 됐다(배10320 실측).
#   본질 = 무게(얼마나 큰 일인가)와 급한정도(얼마나 급한가)는 다른 축인데 한 칸에 섞은 범주 오류.
#   게다가 접수 시점에는 작업 무게를 알 수 없다 — 실무진이 고른 건 무게가 아니라 급한 정도다.
#   그래서 무게는 접수 기본값(⛴️여객선)으로 두고, 급한정도는 ship['urgency'] 별도 칸에 그대로 남긴다.
#   순서 반영은 선별 게이트(welly_auto_runner._sort_key)가 이 칸을 읽어서 한다.
DEFAULT_PRIORITY = "⛴️여객선"   # 접수 시점엔 실제 무게를 알 수 없음 — 중간값
URGENCY_ALLOWED = ("급함", "보통", "천천히")

# ★2026-07-27 배10309(시우→시포) — 화면이 무엇이든 전부 시포 배로 서던 문제를 고친다.
#   '업무 구분'(screen) 선택값이 폼(실무진피드백.html)의 '어떤 업무인가요?'에서 담당을 가리려고
#   있는 칸인데, build_ship() 이 clevel 을 'cpo' 로 하드코딩해 그 값을 제목에만 쓰고 버리고 있었다.
#   이 폼은 여러 화면이 공유하는 단일 창구(멤버십·강습·종합접수처 + 앞으로 더 붙을 화면들)라
#   화면값 문자열을 하나씩 나열하지 않고 키워드로 판정한다 — 새 화면이 붙어도 코드 재수정 없이 맞는다.
#   매핑 근거는 지어내지 않고 이미 쓰는 도메인 정의 그대로 옮긴다:
#     회원·문의·강습 = 시포(cpo) / 점검·공지·접수·VOC = 시우(coo) /
#     시설 배선·자동화·화면 장애 = 시토(cto) / 마케팅·콘텐츠 = 시모(cmo).
#   인사·재무(시로·시뽀)는 나우열M 관할이라 자동 배정 대상이 아니다 — 해당하면 시우로 보내 사람이 본다.
#   순서가 먼저인 항목이 우선 매치된다. 어느 것도 안 맞으면 시포로 보낸다(지금 동작 유지 = 안전 폴백,
#   잘못 보내 사라지는 것보다 낫다).
# ★2026-07-30(시토) — 배231·232(FB260730-083916/084209) "골프장 빔프로젝트 + PC 전원 제어
#   시간 설정"이 시포로 갔다. 원인 실측: screen="브로제이"(화면 이름) · kind="그 외" — 둘 다
#   업무 도메인을 담지 않는 값이라 어떤 키워드도 못 맞고 기본값(cpo)으로 떨어졌다. 실제 신호는
#   자유서술 content("전원"·"PC")에만 있었는데 route_clevel 이 content 를 아예 보지 않고 있었다
#   — 이 자리가 그 판정 지점(약속 L21, 새 매핑 파일 만들지 않음). content 를 판정 대상에
#   더하고, 시설계 키워드(설비·전원·PC·프로젝터·조명·공조·누수·고장)를 cto 버킷에 보강한다.
#   나머지 버킷도 같은 자리에서 함께 보강(회원=상담·등록·CS / 점검=근무·부서 운영 / 마케팅=발행).
_CLEVEL_KEYWORDS = (
    ("cto", ("시설", "배선", "자동화", "장애", "설비", "전원", "PC", "프로젝터", "조명", "공조", "누수", "고장")),
    ("cmo", ("마케팅", "콘텐츠", "홍보", "발행")),
    ("coo", ("인사", "재무", "급여", "채용", "회계")),  # 나우열M 관할 — 자동배정 아님, 시우가 사람에게 넘김
    ("coo", ("점검", "공지", "접수", "VOC", "voc", "근무", "부서 운영")),
    ("cpo", ("회원", "강습", "문의", "멤버십", "상담", "등록", "CS")),
)


def route_clevel(screen: str, kind: str, content: str = "") -> str:
    """화면(업무 구분)·종류·내용(content) 텍스트로 담당 C-Level 을 고른다.
    content 를 보는 이유(2026-07-30) — screen/kind 가 화면 이름·'그 외' 처럼 도메인을
    담지 않는 값일 때도, 실무진이 실제로 적은 자유서술에는 신호가 있다(예: "PC 전원 제어").
    애매하면 cpo(안전 폴백)."""
    text = f"{screen} {kind} {content}"
    for clevel, keywords in _CLEVEL_KEYWORDS:
        if any(k in text for k in keywords):
            return clevel
    return "cpo"


# ─── 나가는 쪽: 배가 DONE 되면 실무진 화면에 회신한다 (2026-07-27 웰리 지시) ──────────────────
#   들어오는 쪽(위)은 이미 자동인데 나가는 쪽(고침 → 실무진 회신)은 사람이 매번 손으로
#   staff_feedback_update 를 불러야 했다 — 반쪽만 자동인 루프. 여기서 마저 잇는다.
#   ship['note'] 는 GM·다른 C-Level이 읽는 내부 감사 기록(커밋 해시·파일명·함수명 섞임)이라
#   그대로 실무진에게 보낼 수 없다 — 아래는 그 note 에서 마지막 '완료' 계열 항목을 찾아
#   기술 잡음만 걷어내고 한 줄로 다듬는다. 완벽한 존댓말 재작성은 아니지만(그건 이 배치
#   스크립트 안에 AI 문장생성이 없어 불가능), 실무진이 읽고 이해할 수 있는 사실 그대로다.
_FBID_RE = re.compile(r"FB\d{6}-\d{6}")
_COMMIT_HASH_RE = re.compile(r"커밋\s*[0-9a-f]{6,12}(?:\s*[→\-]{1,2}>?\s*[0-9a-f]{6,12})*")
_FILENAME_RE = re.compile(r"\b[\w\-]+\.(?:py|js|html|json|md)\b")
_PATHLIKE_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_./]*)+\b")  # cmo/survey 같은 저장소 경로
_IDENTIFIER_RE = re.compile(r"_[A-Za-z][A-Za-z0-9_]*")
_ALLCAPS_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_PAREN_SPAN_RE = re.compile(r"\([^()]*\)")
_GM_QUOTE_START_RE = re.compile(r'GM\s*(지시|판단|결정)\s*[:"“]')
_CLOSING_TAG_RE = re.compile(r"\[[^\]\n]*(?:완료|확정|결정|검수 통과|종결)[^\]\n]*\]")
# ★2026-08-04 웰리 — 부정문을 종결로 읽어 실무진 화면에 내부 진단문이 그대로 나갔다.
#   실사고: 배10496 note 의 「[왜 저장이 안 됐나 — 확정 못 함]」이 '확정' 때문에 종결 태그로
#   잡혔고, 그 아래 rowKey·WriteBuffer 설명이 임정은M 회신으로 시트에 적혔다.
#   태그 안에 부정어가 있으면 종결이 아니다. ('결정'은 GM 결정 기록이 종결이라 새로 넣었다.)
_CLOSING_NEGATION_RE = re.compile(r"못\s|못함|못 함|불가|실패|안 됨|안됨|미완|보류")

# ─── 약속-표현 게이트 (2026-07-29 GM·웰리 지적 — FB260729-132718 실사고) ───────────────────
#   사고: 배 10399 회신에 "검토해서 반영하겠습니다"(미래형 약속)라고 적어 놓고 그 순간 배를
#   DONE 으로 닫아버렸다 — 실제 반영은 없었는데 시트 처리상태만 '처리완료'로 바뀌어 완료로
#   보고됐다(GM: "거짓말로 일하지마"). 회신문에 약속 표현이 있으면 그 약속을 추적할 '다른'
#   배(후속)가 있어야 한다 — 없으면 이 회신은 내보내지 않는다(관문 한 곳, 새 감시기 신설 없음).
#   "-겠습니다"는 한국어에서 미래·의지형 어미다("반영했습니다"류 완료형과 뚜렷이 구분되는
#   문법 표지라 오탐이 적다) — 이미 끝난 일을 적을 때는 쓰이지 않는다.
_PROMISE_RE = re.compile(r"겠습니다")

STAFF_REPLY_ALREADY_DONE = "처리완료"

# ── 3단계 상태 노출(2026-07-28 웰리 위임) ───────────────────────────────────
#   배 status(PENDING/IN_PROGRESS/DONE)를 시트 처리상태 칸의 3단계 문구로 매핑한다.
#   순위표는 멱등 판정용 — 시트 현재 값이 목표 단계보다 같거나 앞서 있으면 쓰지 않는다.
#   사람이 직접 적은 임의 문구(이 표에 없는 값)는 안 건드리는 게 안전해 최고 순위로 본다.
STAFF_STATUS_RECEIVED = "접수됨"
STAFF_STATUS_IN_PROGRESS = "확인중"
STAFF_STATUS_DONE = STAFF_REPLY_ALREADY_DONE  # "처리완료" — 기존 값과 동일 상수 재사용(중복 정의 금지)
# ★2026-07-28 GM 지시 — "'접수했습니다' 이거 하지 말고, 바로 작업 진행해서 처리된 내용을 메모해줘."
#   그동안 배가 생기는 순간 '접수됨 — 접수했습니다. 순서대로 확인해 처리하겠습니다'를 시트에 썼다.
#   실무진 화면엔 그 문구만 며칠씩 떠 있고, 정작 데이터는 계속 문제였다(연락 기록 유실 3건이 그 상태로
#   방치됐다 — GM 지적 "접수했습니다 순서대로 처리하겠다고만 적혀있고, 계속 CONTACT 내용 날아가는데").
#   빈 약속은 신뢰만 깎는다 → 진행 단계 문구는 쓰지 않고, **실제로 처리된 내용만** 쓴다.
#   PENDING/IN_PROGRESS 를 None 으로 두면 sync_feedback_status 가 그 배를 회신 대상에서 제외한다.
#   ▸배 생성(들어오는 쪽)은 그대로다 — 접수 자체는 계속 자동으로 큐에 올라간다.
_SHIP_STATUS_TO_STAGE = {
    "PENDING": None,
    "IN_PROGRESS": None,
    "DONE": STAFF_STATUS_DONE,
}
_STAGE_ORDER = (STAFF_STATUS_RECEIVED, STAFF_STATUS_IN_PROGRESS, STAFF_STATUS_DONE)
_UNKNOWN_STAGE_RANK = 99


def _stage_rank(current_status: str) -> int:
    """시트 현재 처리상태 문구 → 단계 순위. 빈칸·'접수'=0(아직 아무 단계도 안 씀).
    startswith 로 판정(기존 DONE 판정이 그랬듯 접두 문구 뒤 추가 텍스트가 붙어도 인식)."""
    s = current_status.strip()
    if not s or s == "접수":
        return 0
    for rank, stage in enumerate(_STAGE_ORDER, start=1):
        if s.startswith(stage):
            return rank
    return _UNKNOWN_STAGE_RANK  # 사람이 직접 적은 문구 — 자동화가 덮어쓰지 않는다


def _stage_memo(stage: str, ship: dict, today: str) -> str:
    """단계별 실무진 화면 문구. DONE 은 기존 build_staff_reply 그대로(회귀 0)."""
    if stage == STAFF_STATUS_DONE:
        return build_staff_reply(ship, today)
    if stage == STAFF_STATUS_IN_PROGRESS:
        return f"[{today} 확인중] 접수한 내용을 확인하고 있습니다. 처리되면 다시 안내드리겠습니다."
    return f"[{today} 접수됨] 접수했습니다. 순서대로 확인해 처리하겠습니다."


def _is_technical_snippet(s: str) -> bool:
    return bool(
        _COMMIT_HASH_RE.search(s) or _FILENAME_RE.search(s) or _PATHLIKE_RE.search(s)
        or _IDENTIFIER_RE.search(s) or _ALLCAPS_TOKEN_RE.search(s)
    )


def _clean_staff_text(text: str) -> str:
    """커밋 해시·파일명·함수명(류)을 걷어낸다. 그런 토큰만 든 괄호절은 통째로 지운다
    (식별자만 지우면 '(_holdOnlyView 조건)' → '(조건)' 처럼 문장이 깨지기 때문)."""
    protected = {}

    def _protect(m):
        key = f"\x00{len(protected)}\x00"
        protected[key] = m.group(0)
        return key

    text = _FBID_RE.sub(_protect, text)  # 접수ID는 보존(오탐 방지 — FB260724 같은 토큰이 ALLCAPS로 오인되던 문제)
    text = _PAREN_SPAN_RE.sub(lambda m: "" if _is_technical_snippet(m.group(0)) else m.group(0), text)
    text = _COMMIT_HASH_RE.sub("", text)
    text = _FILENAME_RE.sub("", text)
    text = _PATHLIKE_RE.sub("", text)
    text = _IDENTIFIER_RE.sub("", text)
    text = _ALLCAPS_TOKEN_RE.sub("", text)
    for key, val in protected.items():
        text = text.replace(key, val)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip(" ·-→")


# 접수 시 note 끝에 붙는 정형 안내문 — build_ship 이 새 배를 만들 때 쓰는 문구와 동일 상수.
# 완료 기록을 안 남기고 배를 닫으면 _last_closing_entry 가 이 문단을 "마지막 문단"으로 폴백해
# 뽑아오는데, 이건 우리 내부 지시문이라 실무진에게 그대로 보내면 안 된다(웰리 반려 2026-08-01,
# FB260731-115427 — "▸ 처리 후 staff_feedback_update 로..." 문구가 그대로 GM 화면에 나감).
_INTAKE_INSTRUCTION_LINE = (
    "▸ 처리 후 staff_feedback_update 로 시트의 처리상태·처리메모를 채운다"
    "(대조키=접수ID). 실무진이 본인 화면에서 처리 결과를 확인할 수 있어야 완료다."
)
# 실제 완료 내용에서는 절대 안 나올 만큼 특이한 문장이라 이 부분 문자열 하나로 정형 문구를 판별한다.
_INTAKE_INSTRUCTION_MARK = "실무진이 본인 화면에서 처리 결과를 확인할 수 있어야 완료다"


def _last_closing_entry(note: str) -> str:
    """note 안에서 가장 마지막 '완료/확정/검수 통과/종결' 계열 항목의 본문을 뽑는다.
    그런 항목이 하나도 없으면(옛 형식 등) 마지막 문단으로 폴백."""
    matches = [m for m in _CLOSING_TAG_RE.finditer(note)
               if not _CLOSING_NEGATION_RE.search(m.group(0))]
    if not matches:
        return note.split("\n\n")[-1]
    m = matches[-1]
    tail = note[m.end():]
    nxt = tail.find("\n\n")
    return (tail[:nxt] if nxt >= 0 else tail).strip()


def build_staff_reply(ship: dict, today: str) -> str:
    """DONE 배 하나 → 실무진이 읽을 한 줄 회신. 원 신고 문구(GM 지시 "…")는 재인용하지
    않고, 실제로 뭘 어떻게 고쳤는지(▸ 항목 최대 2개)만 담는다."""
    note = str(ship.get("note") or "")
    block = _last_closing_entry(note)
    if _INTAKE_INSTRUCTION_MARK in block:
        # 완료 기록이 없어 접수 안내문(정형 문구)만 뽑힌 경우 — 뜻 모를 내부 지시문을 실무진에게
        # 보내느니 "메모를 안 남겼다"를 드러내는 게 낫다(웰리 반려 2026-08-01).
        title = str(ship.get("title") or "").split("—", 1)[-1].strip()
        base = f"확인해 처리했습니다{('(' + title + ')') if title else ''}."
        return f"[{today} 처리완료] {base} (담당자가 상세 처리 메모를 남기지 않았습니다.)"
    lines = [ln.strip() for ln in block.split("\n")]

    picked = []
    bullets = 0
    in_quote_skip = False
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("[") or ln.startswith("★"):
            break
        if in_quote_skip:
            if ln.count('"') % 2 == 1:
                in_quote_skip = False
            continue
        if _GM_QUOTE_START_RE.search(ln):
            if ln.count('"') % 2 == 1:
                in_quote_skip = True
            continue
        if ln.startswith("▸"):
            if bullets >= 2:
                continue
            bullets += 1
        picked.append(ln)
        if bullets >= 2:
            break
        if len(picked) >= 3:
            break

    # 도입부만 짧게 걸리는 경우(예: "원인을 찾았다." 한 줄) — 결론/조치 소단락이 있으면 덧붙인다.
    # 실무진 입장에선 "찾았다"보다 "그래서 어떻게 했다"가 중요하다.
    if len(picked) < 2:
        for ln in lines:
            ln = ln.strip()
            m = re.match(r"^\[(처리|결론|조치|답변)[^\]]*\]\s*(.+)$", ln)
            if m and m.group(2):
                picked.append(m.group(2))
                break

    summary = _clean_staff_text(" ".join(picked))
    if not summary:
        title = str(ship.get("title") or "").split("—", 1)[-1].strip()
        summary = f"확인해 처리했습니다{('(' + title + ')') if title else ''}."
    if len(summary) > 150:
        summary = summary[:150].rstrip() + "…"
    return f"[{today} 처리완료] {summary}"


def _has_tracked_followup(feedback_id: str, queue: list, archive: list, exclude_task_id) -> bool:
    """이 접수ID의 약속을 추적하는 '다른' 배가 있는지 본다(닫히는 배 자기 자신은 제외).
    feedback_id 필드로 연결되거나, note·title 안에 그 접수ID 문자열이 있으면 인정한다
    (_existing_ids 와 같은 관용 — 옛 배는 feedback_id 필드가 없을 수 있다)."""
    if not feedback_id:
        return False
    for it in list(queue) + list(archive):
        if not isinstance(it, dict) or it.get("task_id") == exclude_task_id:
            continue
        if str(it.get("feedback_id") or "").strip() == feedback_id:
            return True
        if feedback_id in (str(it.get("note") or "") + " " + str(it.get("title") or "")):
            return True
    return False


# 시트가 이미 '처리완료' 단계인데도 어긋남으로 안 보는 배 상태. DONE 은 당연하고, MERGED 는
# 이 배 자신이 다른 배로 흡수돼(대조키=접수ID 그대로 유지, 처리·회신은 병합 대상 배가 수행)
# 자기 상태가 영구히 DONE 이 될 일이 없는 정상 종결 형태라 함께 면제한다.
_DRIFT_EXEMPT_STATUSES = ("DONE", "MERGED")


def detect_done_reopen_drift(rows: list, queue: list, archive: list) -> list:
    """배가 DONE(또는 MERGED) 이 아닌데(재오픈 등) 실무진 시트는 이미 '처리완료' 단계인
    어긋남을 찾는다. (2026-07-28 웰리 지시 ③ 구조 차단 — 배10205·10207 실사고: 배는
    IN_PROGRESS 인데 시트엔 '처리완료'가 찍혀 있었다. sync_feedback_status 는
    target_stage=None(PENDING/IN_PROGRESS) 이면 그 배를 곧장 건너뛰어 이 어긋남을 원래 보지
    못했다 — 그 사각을 여기서 메운다. 자동으로 시트를 되돌리지 않는다: 되돌림은 실제로 안
    고쳐졌을 때만 맞는데 그 판단은 매번 라이브 재확인이 필요하다(약속 L03) — 잘못 자동
    되돌리면 이미 고쳐진 건까지 실무진에게 '확인중'으로 되비쳐 오히려 신뢰를 깎는다. 여기서는
    어긋남을 놓치지 않고 표면화만 한다.

    ★2026-08-01 시포 — 접수ID당 배 하나(feedback_id 필드로 연결된 배)만 본다. 한 번은 "다른
    배가 이 접수ID를 언급하면 해결로 친다"는 식으로 넓혀 봤는데(병합·인계 오탐 2건을 잡으려고),
    FB260801-152607 실사고로 반려됐다 — 다른 증상을 고친 무관한 DONE 배가 note 에 이 접수ID를
    한 번 언급했다는 이유만으로 진짜 미해결(회원 2명이 여전히 화면에 안 뜸, 근본수리 배는 아직
    PENDING)을 가렸다. 배 노트 텍스트 매칭은 무관한 배(전수점검·감사 목록 등)까지 끌어들여
    오탐을 만든다 — 신뢰할 신호가 아니다. 그래서 판정은 **이 접수ID의 배 자신의 상태**로만
    한다. DONE 은 물론이고 MERGED 도 정상 종결(위 _DRIFT_EXEMPT_STATUSES 참고, 처리·회신은
    병합 대상 배가 대신 수행하는 정상 형태 — 배10371③ 최초 실사고 사례)이라 같이 면제한다."""
    by_fid = {}
    for r in rows:
        fid = str(r.get("접수ID") or "").strip()
        if fid:
            by_fid[fid] = r

    # 같은 접수ID로 배가 여러 번(재오픈 등) 있을 수 있다 — 활성 큐를 아카이브보다 우선한다.
    latest_by_fid = {}
    for ship in list(archive) + list(queue):  # queue를 나중에 덮어써 활성 큐 우선
        if not isinstance(ship, dict):
            continue
        fid = str(ship.get("feedback_id") or "").strip()
        if fid:
            latest_by_fid[fid] = ship

    drift = []
    for fid, ship in latest_by_fid.items():
        row = by_fid.get(fid)
        if row is None:
            continue
        current_status = str(row.get("처리상태") or "").strip()
        if _stage_rank(current_status) < _stage_rank(STAFF_STATUS_DONE):
            continue  # 시트가 아직 처리완료 단계가 아니면 이 감시 대상 아님
        if str(ship.get("status") or "") in _DRIFT_EXEMPT_STATUSES:
            continue  # 정상 — 배 자신이 DONE 이거나 병합으로 정상 종결
        drift.append({
            "id": fid, "task_id": ship.get("task_id"),
            "ship_status": ship.get("status"), "sheet_status": current_status,
        })
    return drift


# ─── 정체(aging) 리마인드 (2026-08-05 GM 지시) ────────────────────────────────
#   8단계 중 7단계는 이미 자동인데 딱 하나(에스컬레이션)가 없었다 — 접수→배 생성까지는
#   자동이지만, 배가 며칠째 안 닫혀도 아무도 안 본다. 실사고: FB260728-112703(예약자
#   이름 뒤바뀜 신고)이 2일을 묵었고 GM이 물어서야 추적이 시작됐다.
#   ★새 감시기·새 예약작업·새 상태파일 금지(약속 L21) — 이미 매일 도는 이 감시기 안에,
#   이미 읽고 있는 rows/queue/archive 로만 판정한다. 문턱은 아침 자가점검과 동일(1일 이상).
#   표면화 경로도 새로 만들지 않는다 — 이 파일이 이미 쓰는 두 경로(print→로그 / 하트비트
#   detail·extra→자율현황 보드)를 그대로 재사용한다(detect_done_reopen_drift와 동일 패턴).
_STALE_MIN_DAYS = 1
_KOR_DT_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*(오전|오후)\s*(\d{1,2}):(\d{2}):(\d{2})")


def _parse_kor_dt(s: str) -> "datetime | None":
    """GAS가 주는 '2026. 8. 4 오전 10:12:28' 형식(한국어 로캘) 파서. 못 읽으면 None."""
    m = _KOR_DT_RE.search(s or "")
    if not m:
        return None
    y, mo, d, ampm, h, mi, se = m.groups()
    h = int(h) % 12
    if ampm == "오후":
        h += 12
    try:
        return datetime(int(y), int(mo), int(d), h, int(mi), int(se))
    except ValueError:
        return None


def detect_stale_feedback(rows: list, queue: list, archive: list, now: "datetime") -> list:
    """처리완료에 아직 안 닿은(rank<3) 건 중 접수 후 1일(_STALE_MIN_DAYS) 이상 지난 것을
    오래된 순으로 뽑는다. now 는 tz 없는 KST 벽시계 시각(접수시각도 tz 없이 온다).
    담당 배정(feedback_id로 연결된 배 존재) 여부와 회신 여부(시트 단계 '확인중' 이상)를
    갈라 표시한다(GM 지시 ⑤ — 배정만 되고 회신 없는 채 묵는 것도 여전히 미해결)."""
    latest_by_fid = {}
    for ship in list(archive) + list(queue):  # queue 를 나중에 덮어써 활성 큐 우선(detect_done_reopen_drift와 동일)
        if not isinstance(ship, dict):
            continue
        fid = str(ship.get("feedback_id") or "").strip()
        if fid:
            latest_by_fid[fid] = ship

    out = []
    for r in rows:
        fid = str(r.get("접수ID") or "").strip()
        if not fid:
            continue
        status = str(r.get("처리상태") or "").strip()
        if _stage_rank(status) >= len(_STAGE_ORDER):  # 처리완료 — 대상 아님
            continue
        created = _parse_kor_dt(str(r.get("접수시각") or ""))
        if created is None:
            continue
        days = (now - created).total_seconds() / 86400.0
        if days < _STALE_MIN_DAYS:
            continue

        ship = latest_by_fid.get(fid)
        screen = str(r.get("업무 구분") or r.get("화면") or "").strip()
        content = str(r.get("내용") or "").strip()
        clevel = str(ship.get("clevel") or "").strip() if ship else route_clevel(screen, str(r.get("종류") or ""), content)
        replied = _stage_rank(status) >= 2  # '확인중' 이상 — 실무진 화면에 뭔가 회신이 나간 적 있음
        if ship is None:
            label = f"담당 미배정 {int(days)}일째"
        elif not replied:
            label = f"담당 배정됨·회신 없음 {int(days)}일째"
        else:
            label = f"확인중(회신됨) {int(days)}일째"
        out.append({
            "id": fid, "days": days, "clevel": clevel_nickname(clevel) if clevel else "미정",
            "title": screen or content[:30], "label": label,
        })
    out.sort(key=lambda x: -x["days"])
    return out


def _stale_fingerprint(stale: list) -> str:
    """같은 내용(같은 접수ID·같은 경과일) 이면 지문이 같다 — 도배 방지용.
    경과일이 바뀌면(1일째→2일째) 지문도 바뀌어 다시 알린다(GM 요구 그대로)."""
    return "|".join(f"{s['id']}:{int(s['days'])}" for s in stale)


def sync_feedback_status(rows: list, queue: list, archive: list, today: str):
    """접수ID로 배와 시트를 대조 — 배 status(PENDING→접수됨/IN_PROGRESS→확인중/DONE→처리완료)에
    맞는 단계가 시트에 아직 안 쓰여 있으면 그 단계 하나만 조립한다(단계를 건너뛰지 않음 —
    같은 회차에 배가 PENDING→DONE 으로 바로 잡혀 있어도 반환값은 목표 단계 하나뿐이라,
    다음 회차가 실행되면서 자연히 다음 단계로 올라간다. 3분 주기 잡이라 문제 없음).
    반환: [{id, status, memo, ship_title}] — 실제 GAS 호출은 호출부에서(멱등 판단은
    라이브 시트의 현재 처리상태 '단계 순위'로 한다 — 로컬 마커에 기대지 않는다: 3분마다 도는
    잡이라 로컬 상태와 시트가 어긋나도 다음 회차에 시트 기준으로 다시 판단하면 스스로 맞다).
    DONE 단계의 회신 문구·경로는 build_staff_reply 그대로 유지(회귀 0)."""
    by_fid = {}
    for r in rows:
        fid = str(r.get("접수ID") or "").strip()
        if fid:
            by_fid[fid] = r

    seen_task_ids = set()
    updates = []
    for ship in list(queue) + list(archive):
        if not isinstance(ship, dict):
            continue
        fid = str(ship.get("feedback_id") or "").strip()
        ship_status = str(ship.get("status") or "")
        target_stage = _SHIP_STATUS_TO_STAGE.get(ship_status)
        if not fid or target_stage is None:
            continue
        task_id = ship.get("task_id")
        if task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)

        row = by_fid.get(fid)
        if row is None:
            continue  # 시트에서 못 찾음(삭제 등) — 안전하게 건너뜀, 다음 회차 재시도
        current_status = str(row.get("처리상태") or "").strip()
        if _stage_rank(current_status) >= _stage_rank(target_stage):
            continue  # 멱등 — 이미 같은 단계거나 더 앞선 단계(사람이 직접 적은 값 포함)

        memo = _stage_memo(target_stage, ship, today)
        # 약속-표현 게이트 — DONE 회신에 미래형 약속("...겠습니다")이 있는데 그 약속을
        # 추적하는 다른 배가 없으면 내보내지 않는다(배10399 재발방지 · GM 2026-07-29).
        if target_stage == STAFF_STATUS_DONE and _PROMISE_RE.search(memo) \
                and not _has_tracked_followup(fid, queue, archive, task_id):
            print(f"[blocked] {fid} ({task_id}) — 회신에 약속 표현이 있는데 후속 배가 없습니다. "
                  f"회신을 보내지 않습니다: {memo[:100]}")
            continue
        updates.append({
            "id": fid, "status": target_stage, "memo": memo,
            "ship_title": ship.get("title"), "task_id": task_id,
        })
    return updates


def push_feedback_updates(updates: list, timeout=60):
    """staff_feedback_update 호출 — 대조키=접수ID(행번호 아님). 실패 시 (None, 사유)."""
    payload = [{"id": u["id"], "status": u["status"], "memo": u["memo"]} for u in updates]
    body = json.dumps({"action": "staff_feedback_update", "t": FB_TOKEN, "updates": payload}).encode("utf-8")
    req = urllib.request.Request(
        FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"
    if not data.get("ok"):
        return None, str(data.get("error") or "ok=false")
    return data, None


def fetch_feedback(timeout=60):
    """접수된 피드백 전체(최신순). 실패 시 (None, 사유) — 조용히 성공으로 위장하지 않는다."""
    body = json.dumps({"action": "staff_feedback_list", "t": FB_TOKEN}).encode("utf-8")
    req = urllib.request.Request(
        FB_GAS_URL, data=body, headers={"Content-Type": "text/plain;charset=utf-8"}
    )
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"
    if not data.get("ok"):
        return None, str(data.get("error") or "ok=false")
    return data.get("rows") or [], None


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title).strip("-")
    return (s[:28] or "TASK").upper()


def _existing_ids(queue, archive) -> set:
    """이미 배가 있는 접수ID 집합. feedback_id 필드가 정본, 옛 배는 note 안 FB… 문자열로도 인정."""
    ids = set()
    for it in list(queue) + list(archive):
        if not isinstance(it, dict):
            continue
        fid = it.get("feedback_id")
        if fid:
            ids.add(str(fid).strip())
            continue
        note = str(it.get("note") or "")
        for m in re.finditer(r"FB\d{6}-\d{6}", note):
            ids.add(m.group(0))
    return ids


def build_ship(row: dict, queue, today: str) -> dict:
    fid = str(row.get("접수ID") or "").strip()
    # 화면 이름 칸은 2026-07-25 에 '화면' → '업무 구분' 으로 이름이 바뀌었는데 여기가 옛 이름만 읽고 있었다.
    # 그래서 그 뒤 올라온 배는 제목에서 화면 이름이 통째로 빠졌다(예: 배10302 "실무진 피드백 — 불편해요: 행간격이…"
    # — 멤버십인지 강습인지 제목만 보고 알 수 없었다). 두 이름 다 받아 옛 행도 그대로 읽는다. 2026-07-27 시포.
    screen = str(row.get("업무 구분") or row.get("화면") or "").strip()
    kind = str(row.get("종류") or "").strip()
    urgency = str(row.get("급한정도") or "").strip()
    writer = str(row.get("작성자") or "").strip()
    content = str(row.get("내용") or "").strip()
    at = str(row.get("접수시각") or "").strip()

    head = " ".join(x for x in (screen, kind) if x)
    first = re.sub(r"\s+", " ", content)[:44]
    title = f"실무진 피드백 — {head}: {first}" if head else f"실무진 피드백 — {first}"

    clevel = route_clevel(screen, kind, content)
    nick = clevel_nickname(clevel)

    nos = [x.get("ship_no") or 0 for x in queue if isinstance(x, dict)]
    ship_no = (max(nos) + 1) if nos else 1

    note = (
        f"[실무진 피드백 자동 접수 {today}] 접수ID {fid} · 접수 {at}"
        f" · 작성자 {writer or '(미기재 — 되묻기 불가)'}"
        f"{' · 급한정도 ' + urgency if urgency else ''}\n\n"
        f"{content}\n\n"
        f"{_INTAKE_INSTRUCTION_LINE}"
    )
    return {
        "task_id": f"{clevel.upper()}-{today}-FB-{_slug(fid or first)}",
        "clevel": clevel,
        "title": f"[{nick}] {title}",
        "status": "PENDING",
        "priority": DEFAULT_PRIORITY,
        # 급한정도는 무게와 별개 칸으로 — 선별 게이트가 이 값을 먼저 보고 순서를 정한다(GM ①안 2026-07-27).
        "urgency": urgency if urgency in URGENCY_ALLOWED else "보통",
        "enqueued_at": today,
        "from": "실무진",
        "note": note,
        "next": "내용 확인 → 원인·조치 → 시트 처리상태 갱신 → 작성자에게 결과 회신",
        "ship_no": ship_no,
        "short_no": next_short_no(queue),
        "module": "home",
        "surface": "autonomy",
        # ★2026-07-31 웰리 — 실무진이 손들어 올린 신고는 언제나 사람 일(office)이다.
        #   그동안 이 칸이 비어 나가서 08:00 보고가 "audience 미표기"로 흘렸고, 실무진 신고가
        #   AI 살림 쪽 화면에 섞여 뜰 수 있었다(오늘 실측 2척). 두 건만 고치지 않고 만드는 자리에
        #   박는다 — 앞으로 들어오는 신고는 전부 붙어서 온다(약속 L21 관문).
        "audience": "office",
        "feedback_id": fid,
    }


def _selftest() -> int:
    """자기검사(웰리 반려 2026-08-01 후속) — 안내문구만 있는 note 는 회신으로 안 나가고,
    정상 완료 기록이 있으면 그대로 나가는지. 프레임워크 없이 assert 두 개."""
    boiler_note = (
        "[실무진 피드백 자동 접수 2026-08-01] 접수ID FB000000-000000 · 접수 x · 작성자 테스트\n\n"
        "테스트 내용\n\n" + _INTAKE_INSTRUCTION_LINE
    )
    out1 = build_staff_reply({"note": boiler_note, "title": "[시포] 테스트"}, "2026-08-01")
    assert "staff_feedback_update" not in out1, out1
    assert "메모를 남기지 않았습니다" in out1, out1

    good_note = boiler_note + "\n\n[처리완료 2026-08-01] 버튼 색을 파란색으로 바꿨습니다."
    out2 = build_staff_reply({"note": good_note, "title": "[시포] 테스트"}, "2026-08-01")
    assert "버튼 색을 파란색으로 바꿨습니다" in out2, out2

    print("selftest OK")
    print("  안내문구만 있을 때:", out1)
    print("  완료 기록 있을 때 :", out2)

    # ── 정체 리마인드 자체검사(2026-08-05) ── 1일 미만 안 걸림 / 처리완료 안 걸림 /
    #    담당 있고 회신 없는 건이 구분됨. 3개 assert 로 충분(ponytail — 프레임워크 없음).
    now = datetime(2026, 8, 5, 12, 0, 0)
    rows_stale = [
        {"접수ID": "FB260804-100000", "처리상태": "접수", "접수시각": "2026. 8. 4 오전 10:00:00",
         "업무 구분": "멤버십", "종류": "버그", "내용": "예약자 이름이 바뀝니다"},
        {"접수ID": "FB260805-100000", "처리상태": "접수", "접수시각": "2026. 8. 5 오전 10:00:00",
         "업무 구분": "멤버십", "종류": "버그", "내용": "당일 접수"},
        {"접수ID": "FB260801-090000", "처리상태": "처리완료", "접수시각": "2026. 8. 1 오전 9:00:00",
         "업무 구분": "멤버십", "종류": "버그", "내용": "이미 처리됨"},
    ]
    queue_stale = [{"feedback_id": "FB260804-100000", "clevel": "cpo", "status": "PENDING", "task_id": "T1"}]
    stale = detect_stale_feedback(rows_stale, queue_stale, [], now)
    ids = {s["id"] for s in stale}
    assert "FB260804-100000" in ids, stale        # 1일 이상 + 담당 있음 → 걸림
    assert "FB260805-100000" not in ids, stale     # 접수 2시간(1일 미만) → 안 걸림
    assert "FB260801-090000" not in ids, stale     # 처리완료 → 안 걸림
    lbl = next(s["label"] for s in stale if s["id"] == "FB260804-100000")
    assert "담당 배정됨" in lbl and "회신 없음" in lbl, lbl  # 배정됨·회신없음 구분 표시
    print("정체 리마인드 자체검사 OK:", lbl)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="큐에 쓰지 않고 무엇이 올라갈지만 출력")
    ap.add_argument("--no-push", action="store_true", help="큐만 갱신하고 커밋·푸시 생략")
    ap.add_argument("--selftest", action="store_true", help="build_staff_reply 안내문구 가드 자기검사만 실행")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    rows, err = fetch_feedback()
    if rows is None:
        print(f"[error] 피드백 조회 실패 — {err}")
        return 0  # fail-soft: 3분마다 도는 잡이라 다음 회차에 재시도한다.

    # ★2026-08-03 시토(배299 · 0 위장 수리) — '미처리 집계'와 '배 생성 대상'을 갈랐다.
    #   종전엔 하나였고 판정이 빈칸·'접수' 두 값뿐이라, 실무진이 손든 건이 **집계에서 사라졌다**:
    #   라이브 40건 중 '확인중' 1·'진행중' 1 이 미처리인데 하트비트는 **미처리 0·회신_대상 0**.
    #   0 위장이라 어떤 감시기도 안 잡는다(아침 자가점검 #7 그 부류).
    #   ▸미처리 = **'처리완료'에 도달하지 않은 전부.** 사람이 직접 적은 임의 문구('진행중' 등)도
    #     미처리로 센다 — 사람이 손든 신호는 숨기는 쪽보다 한 번 더 보이는 쪽이 낫다.
    #   ▸배 생성 대상은 **넓히지 않는다**(rank<=1 = 빈칸·접수·접수됨). '확인중'은 이미 배가 붙어
    #     진행 중이라는 뜻이라 여기서 또 배를 만들면 중복이 된다. 대신 '접수됨'을 새로 포함했다 —
    #     종전 판정이 상수(STAFF_STATUS_RECEIVED="접수됨")와 안 맞아 신규 접수건이 배 없이
    #     샐 수 있었다(현재 시트엔 해당 행 0건이라 즉시 영향은 없고 구멍만 막는다).
    _DONE_RANK = len(_STAGE_ORDER)  # '처리완료' 순위
    pending = [r for r in rows
               if _stage_rank(str(r.get("처리상태") or "")) != _DONE_RANK]
    ship_targets = [r for r in rows
                    if _stage_rank(str(r.get("처리상태") or "")) <= 1]

    now_dt = datetime.now(KST).replace(tzinfo=None)
    today = now_dt.date().isoformat()

    try:
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        archive = []

    if args.dry_run:
        q = load_queue()
        have = _existing_ids(q, archive)
        new = [r for r in ship_targets if str(r.get("접수ID") or "").strip() not in have]
        print(f"전체 {len(rows)}건 · 미처리 {len(pending)}건 · 배 없는 신규 {len(new)}건")
        for r in new:
            print("  +", r.get("접수ID"), "|", str(r.get("내용") or "")[:60].replace("\n", " "))

        sync_updates = sync_feedback_status(rows, q, archive, today)
        print(f"\n[나가는 쪽] 배 status 대비 시트 처리상태가 아직 안 따라간 것 {len(sync_updates)}건")
        for u in sync_updates:
            print(f"  ~ {u['id']} ({u['task_id']}) → 처리상태='{u['status']}'")
            print(f"    처리메모: {u['memo']}")

        drift = detect_done_reopen_drift(rows, q, archive)
        print(f"\n[재발방지 어긋남] 배 DONE 아닌데 시트는 이미 처리완료 {len(drift)}건")
        for d in drift:
            print(f"  ! {d['id']} ({d['task_id']}) — 배 status={d['ship_status']} / 시트='{d['sheet_status']}'")

        stale = detect_stale_feedback(rows, q, archive, now_dt)
        print(f"\n[정체 리마인드] 1일 이상 묵은 실무진 신고 {len(stale)}건 (오래된 순)")
        for s in stale:
            print(f"  ⏳ {s['id']} · {int(s['days'])}일째 · 담당 {s['clevel']} · {s['label']} — {s['title']}")
        return 0

    made = []

    def mutator(queue):
        have = _existing_ids(queue, archive)
        for r in ship_targets:
            fid = str(r.get("접수ID") or "").strip()
            if not fid or fid in have:
                continue
            ship = build_ship(r, queue, today)
            queue.append(ship)
            have.add(fid)
            made.append(ship)
        return queue

    mutate_queue(mutator, holder=MODULE_ID)

    # 나가는 쪽 — 큐 파일은 안 건드린다(대표님 지시: _queue.json 은 웰리 중앙 갱신 전용).
    # 배 status(접수됨/확인중/처리완료)에 맞는 단계가 시트에 아직 안 쓰였으면 골라
    # staff_feedback_update 로 반영한다. 멱등 판단은 로컬 상태가 아니라 방금 fetch 한
    # 라이브 시트 값 기준(sync_feedback_status 내부).
    queue_now = load_queue()
    replied = []
    reply_err = None
    sync_updates = sync_feedback_status(rows, queue_now, archive, today)
    if sync_updates:
        result, reply_err = push_feedback_updates(sync_updates)
        if result is not None:
            replied = result.get("updated") or []
            missed = result.get("notFound") or []
            for u in sync_updates:
                tag = "OK" if u["id"] in replied else ("NOT_FOUND" if u["id"] in missed else "?")
                print(f"[reply:{tag}] {u['id']} ({u['task_id']}) — {u['memo']}")
        else:
            print(f"[warn] staff_feedback_update 실패 — {reply_err} (다음 회차 재시도)")

    drift = detect_done_reopen_drift(rows, queue_now, archive)
    for d in drift:
        print(f"[drift] {d['id']} ({d['task_id']}) — 배 status={d['ship_status']} 인데 시트는 "
              f"이미 '{d['sheet_status']}' 입니다. 실제로 다시 문제가 있는지 재확인하세요.")

    # 정체 리마인드 — 지문 억제(같은 접수ID·같은 경과일이면 매 3분 재통보하지 않는다).
    # 새 상태파일을 안 만든다: 이 모듈 자신의 하트비트(status/heartbeats/{MODULE_ID}.json,
    # 이미 매 회차 덮어써 존재)에 지난 지문을 실어 두고 이번 회차와 비교한다.
    stale = detect_stale_feedback(rows, queue_now, archive, now_dt)
    stale_fp = _stale_fingerprint(stale)
    prev_fp = str((last_heartbeat(MODULE_ID) or {}).get("정체_지문") or "")
    if stale and stale_fp != prev_fp:
        print(f"[정체 리마인드] 1일 이상 묵은 실무진 신고 {len(stale)}건 (오래된 순)")
        for s in stale:
            print(f"  ⏳ {s['id']} · {int(s['days'])}일째 · 담당 {s['clevel']} · {s['label']} — {s['title']}")
    elif stale:
        print(f"[정체 리마인드] 변화 없음(이미 통보) — {len(stale)}건 유지")

    record_heartbeat(
        MODULE_ID,
        detail=(
            f"피드백 {len(rows)}건 · 미처리 {len(pending)}건 · 이번에 배로 올린 것 {len(made)}건"
            f" · 회신 대상 {len(sync_updates)}건 · 회신 완료 {len(replied)}건"
            f" · 재발방지 어긋남 {len(drift)}건 · 정체(1일+) {len(stale)}건"
        ),
        extra={
            "전체": len(rows), "미처리": len(pending), "신규_배": len(made),
            "회신_대상": len(sync_updates), "회신_완료": len(replied),
            "재발방지_어긋남": len(drift),
            "정체_1일이상": len(stale), "정체_지문": stale_fp,
        },
    )

    if not made:
        print(f"[done] 새로 올릴 피드백 없음 (전체 {len(rows)} · 미처리 {len(pending)})")
        return 0

    for s in made:
        print(f"[ship] 배 {s['short_no']} · {s['title']}")

    if args.no_push:
        print("[done] --no-push — 커밋 생략")
        return 0

    # 커밋은 safe_commit 을 통한다(부팅 스킬 §5-2 — 세션 커밋 관문 단일화).
    # git_commit_push 를 직접 부르면 이 저장소가 detached HEAD 로 돌 때 push 가
    # "You are not currently on a branch" 로 죽는다(2026-07-25 실측). safe_commit 은
    # 지정 경로만 담고 HEAD 재검증·원자 갱신까지 하며 그 상황을 함께 처리한다.
    # 제목을 chore(queue) 로 시작한다 — auto_log_adhoc_to_queue 의 SKIP 규칙에 걸려
    # 이 커밋이 또 하나의 완료-배를 낳지 않는다(배 도배 재발 방지).
    import subprocess  # noqa: PLC0415
    msg = f"chore(queue): 실무진 피드백 {len(made)}건 배로 접수 (cpo-staff-feedback-watch)"
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "safe_commit.py"), "-m", msg, "--",
             "status/_queue.json", f"status/heartbeats/{MODULE_ID}.json"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=180,
        )
        print((r.stdout or "").strip()[-400:] or "[warn] safe_commit 출력 없음")
        if r.returncode != 0:
            print(f"[warn] safe_commit rc={r.returncode} — 큐 파일은 로컬에 남음, 다음 회차 재시도")
    except Exception as e:
        print(f"[warn] 커밋 실패(무해 — 큐 파일은 로컬에 남음): {type(e).__name__}: {str(e)[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
