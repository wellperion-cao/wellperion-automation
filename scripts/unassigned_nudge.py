# -*- coding: utf-8 -*-
"""문의 담당자 미배정 배정 독려 안내 (배9206 · GM 지시 2026-07-23)

GM 지시: "미배정건 각 팀장분들한테 좋게 푸시해서 배정 다 채울 수 있도록."

무엇을 하나
  - 담당자가 아직 정해지지 않은 강습 문의를 종목별로 묶고, 오래 기다린 순으로
    상위 몇 건을 이름과 함께 보여준 뒤, 배정 화면 링크로 바로 갈 수 있게 안내한다.
  - 어조는 독촉이 아니라 부탁·감사 (GM "좋게 푸시").

왜 별도 모듈인가
  - 22:30 일일보고(report_stream_1_impl)의 '📌 누적 미배정' 한 줄은 참고 표기라
    행동을 끌어내지 못한다. 이 모듈은 '무엇을·어디서·어떻게' 까지 준다.
  - 판정 기준은 새로 만들지 않고 report_stream_1_impl 의 것을 그대로 쓴다
    (약속 L01 한 곳만 본다 — 미배정 정의가 두 벌이 되면 숫자가 갈린다).

게이트
  - 기본 = dry-run(출력만). 실제 발송은 --send 를 명시해야 한다.
  - --to gm(기본, GM 개인 봇방) / --to staff(문의알림방 실무진).
    실무진 발송은 되돌릴 수 없으므로 GM 확인 후 전환한다(배9253 과 동일 절차).

★배100 개편 (웰리 결정 2026-07-25 반영)
  - 30일 상한(STALE_MAX_DAYS) 제거 — 상한 때문에 최우선 건(80~204일)이 통째로
    빠져 알림이 있으나 마나였다. 소음은 상한이 아니라 **하루 상위 10건**으로 잡는다.
  - 정렬 = 종목 점수(브리프 status/briefs/시포_미배정_우선순위_20260725.md §0 공식
    그대로): 미배정건수 × 경과일중앙값 × (0.5 + 미컨택비율). 선발은 종목 점수 순
    라운드로빈(1위 종목 최악건 → 2위 → … → 다시 1위 2번째), 종목 안에서는
    "연락이력 없음 우선 → 오래된 순".
  - 같은 건 재알림 7일 간격 — 상태는 배10014 방식(상설 파일 1개 갱신) 재사용:
    module_heartbeat 공통 유틸의 status/heartbeats/cpo-unassigned-nudge.json 에
    {키: 마지막 안내일} 을 덮어쓰기 갱신. 새 원장 파일 없음. **발송 성공 시에만**
    갱신되므로 dry-run 은 가드 상태를 소모하지 않는다.
    키는 rowKey(타임스탬프|전화번호 — PII)를 그대로 두지 않고 sha1 해시 12자리.
  - 휴면 = 연락이력 0건 AND 경과 100일 초과 → 푸시 대상에서 제외(실무진 시간을
    죽은 리드에 쓰지 않게). ★삭제·폐기 아님 — 매 실행 시 데이터에서 다시 도출되며
    --list-dormant 로 전체 목록 열람(월 1회 검토용). 연락이력이 있는 100일+ 건은
    이미 관계가 있으므로 정상 배정 대상이다.

★2026-08-05 시토 추가 — 24시간 SLA 위반 → 카카오 ★부서장 방 (GM 지시)
  GM: "8월부터는 무조건 철저하게 관리해줘야해 담당자 24시간 내 미배정 및 컨택
  안되었을 시에는 카카오톡 부서장방에 전달." 위 배정 독려(텔레그램·문의알림방·
  상한없음)와는 다른 층 — 대상은 8/1 이후 신규 접수만, 문턱은 정확히 24시간,
  목적지는 카카오 ★부서장 방(scripts/kakao_rooms.json 정본). 새 스크립트·새 예약
  작업·새 방 없음 — 이 모듈이 이미 읽는 데이터에 collect_sla_violations()/
  build_sla_alert_text()만 얹고, 발신은 daily_scheduler.run_daily_digest()가 기존
  카카오 관문(kakao_report_sender.py --message --only-room)으로 보낸다.
  판정 = 접수 후 24시간 경과 && (담당자 없음 || 컨택기록 0건). 단, 이미 등록완료·
  이탈종결(LOSS)로 끝난 건은 대상에서 뺀다(R._is_registered/_is_loss 재사용 —
  이미 해결된 리드를 "위반"으로 알리면 부서장이 헛다리를 짚는다). 도배 방지 =
  하루 1회(run_daily_digest 자체가 하루 1회만 실행되는 게이트라 별도 가드 파일을
  두지 않는다 — 약속 L21, 새 원장 금지). 위반이 계속되면 경과시간이 매일 바뀌므로
  매일 다시 알리는 게 맞다(GM "철저하게") — 재알림 억제 없음. 위반 0건이면 조용히
  아무것도 보내지 않는다.

★2026-08-05 시토 2차 추가 — 컨택 후 60일(2개월) 무응답 → 같은 카카오 ★부서장 경보에 얹음
  GM: "기한을 2개월로 해줘 / 짚어주면서 하나씩 고쳐나가게 서포트해 // 근본적인
  해결방안을 마련해." 실측(2026-08-05): 마지막 활동(접수일·연락일 중 최근) 60일+
  경과·컨택 이력 1건 이상('컨택 후')·활성(등록·LOSS 아님) 리드 다수. 지금까지는
  화면 '오래 멈춘 리드' 섹션을 직접 열어야만 보였고 하루 5건 캡이라 뒤에 숨은
  건수가 매일 노출되지 않았다 — 이 알림이 그 간극을 메운다.
  판정 = collect_sla_violations()와 동일 판정틀(R._is_registered/_is_loss 재사용) +
  '컨택 후'(contacts[]≥1, _has_contact 재사용) + 최근활동(접수일·연락일[].date 중
  최신) 경과 60일 이상. 대상 = 강습(성인/유소년) + 회원(member_inquiry_list) 통합
  — GM 지시가 도메인을 가르지 않았다(716건 = 강습585+회원131 실측 당시 기준).
  회전(도배 방지) = 기존 하트비트 파일(cpo-unassigned-nudge.json)에 새 키
  "notified60"만 얹는다(새 원장 금지) — 마지막으로 보여준 날짜 오름차순(못 보여준
  건 우선) → 경과일 내림차순으로 정렬해 매일 상위 5건만 뽑는다. 오늘 보여준 건은
  다음 정렬에서 뒤로 밀리고(회전), 상태가 바뀌어 후보에서 빠진 건(등록/LOSS 처리
  또는 재컨택으로 60일 밑으로 내려간 건)은 다음 회차에 notified60에서 자동 청소된다
  (현재 후보 키 집합 밖은 버림) — "처리되면 목록에서 사라진다"(GM).
  근본 처방 2종(GM "다시 쌓이지 않게"):
   ① 45일 예고 — 60일 도달 전에 미리 알리면 늦지 않게 손댈 수 있다(문턱을 넘은 뒤
      알리면 이미 늦다). 별도 목록·별도 발송을 만들지 않고 같은 경보 헤더 한 줄에
      "2개월 임박 N건"으로 병기한다(45~59일 구간, 60일 이상 본선 목록과 절대 겹치지
      않음 — 판정 임계값이 서로 배타적이라 자연히 분리, selftest로 재확인).
   ② 상태로 닫을 길 — 알림만으로는 다시 쌓인다. AI 는 상태를 바꾸지 않는다(사람이
      정한다) — 본문에 "계속 진행/이탈(LOSS)/보류 중 하나로 정리해 주세요" 유도
      문구만 넣어 사람이 화면에서 직접 고르게 한다.
  화면(membership.html/lesson 배정화면) 쪽 수정은 이번에 하지 않는다 — 다른 레인이
  같은 파일을 고치는 중이라 제안만 남긴다(카카오 알림 발신 코드로 충분히 처리 가능
  — 새 화면 없이 문구만으로 회전·예고·상태선택 유도 3가지를 전부 담았다).
  발송 = 기존 카카오 관문(kakao_report_sender.py --only-room ★부서장) 재사용, 24시간
  SLA 블록 발송 직후 독립 두 번째 메시지로 "얹는다"(같은 방·같은 회차·새 방/새
  예약작업 없음). 본문 자체도 10줄 이내(GM "짧고 핵심만").

★2026-08-05 시토 개편 (GM 지시 — "다른 내용까지 다 같이 들어가니까 진행이 안된다")
  - 진단: 이 모듈 자체는 배9206 이후 한 번도 실제 발신 배선에 물린 적이 없었다.
    실제로 팀장님들이 받던 배정 독려는 report_stream_1_impl.build_digest() 안
    "📌 3일 넘게 담당이 안 정해진 문의" 한 블록뿐이었고, 그 블록이 신규문의·컨택&등록
    현황 등 다른 섹션과 한 메시지(22:30 문의알림방)에 뒤섞여 나가 묻혔다.
  - 흡수 해제: report_stream_1_impl 의 그 블록에서 강습(성인/유소년) 항목을 뺐다
    (멤버십은 이 모듈이 다루지 않는 별도 도메인이라 그대로 둠 — module_reporter.py
    ABSORB_BUNDLES 흡수 해제와 같은 방식: 배선만 끊고 새 경로는 안 만든다).
  - 배선: telegram_bot/daily_scheduler.py run_daily_digest() 가 stream1 발송 직후
    이 모듈의 build_payload()를 그대로 호출해 문의알림방(기존 목적지 그대로)에
    독립 메시지로 보낸다. 새 스크립트·새 예약작업·새 방 없음 — 기존 발신 관문
    (send_telegram)과 기존 스케줄(매일 20:00 또는 22:30)만 재사용.
  - 지속: RENOTIFY_GAP_DAYS 7일 → 1일. 배정될 때까지 매일 다시 뜬다(단, 같은 날
    중복 실행 시 재전송은 막는다). 도배 방지는 여전히 상위 DAILY_TOP_N 건 회전
    선발로 잡되, 메시지 본문에는 오래된 순 MSG_DISPLAY_N 건만 줄로 싣고 나머지는
    "외 N건" + 총계로 접는다(GM "10줄 안쪽").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import report_stream_1_impl as R  # noqa: E402  (미배정 판정 단일 출처)

# 방 — daily_scheduler 와 같은 값(.env 우선, 폴백 동일). 여기서 새 값을 만들지 않는다.
GM_CHAT_ID = 8254867551
STAFF_CHAT_ID = int(os.environ.get("TELEGRAM_INQUIRY_CHAT_ID") or -5516675010)

# 배정 화면 — 이 모듈은 강습(성인/유소년)만 다룬다(멤버십은 별도 도메인 · 운영부 08:00 보고에서 이미 다룸).
_BASE = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/"
ASSIGN_URL_LESSON = _BASE + "lesson.html"

# 화면 입장 코드 — GM 2026-07-23 제공. 실무진이 코드를 몰라 못 들어가는 일이 없게 안내에 포함.
ENTRY_CODE = "1200"

# 실무진 방에 나가는 안내는 **항상 어느 AI가 보내는지 밝힌다** (GM 2026-07-23 지시).
# 받는 분이 누구에게 되물어야 할지 알 수 있어야 하고, 정체불명 자동 메시지로 읽히면 안 된다.
# 2026-07-24 시토 정정: 문의 담당자 배정은 '문의 이후' = 시포(회원) 도메인이다. 시모(마케팅)는 유입까지.
# 잘못 적으면 실무진이 되물을 상대를 틀리게 찾아간다. 문안 소유는 시포 — 바꾸려면 시포 배로.
# 2026-08-05: 맨 위 인사 대신 맨 끝 서명으로(GM "10줄 안쪽" — 인사말 한 줄도 아깝다).
# GM 확정 2026-08-05 — "웰페리온 회원 시포 드림"은 사람 이름처럼 읽힌다. 실무진이 받는 글에는
# **AI 이고 무엇을 담당하는지**가 드러나야 한다. 형식 = 웰페리온 AI {담당 영역} 담당 {닉네임} 드림.
# 2026-08-21 GM 확정 — 직함을 길게 붙이지 않는다. 웰리를 "AI 웰리"로 줄이면서 같이 맞췄다
# (실무진이 두 가지 표기를 보면 같은 조직이 아닌 것처럼 읽힌다). 짝 = send_ops_digest.RELAY_SIGNOFF.
AI_SIGNOFF = "AI 시포 드림"

# 하루에 부탁드리는 건수 상한 — 소음은 상한(30일)이 아니라 건수로 잡는다(웰리 07-25).
DAILY_TOP_N = 10              # 회전 선발 상한(가드 대상) — 기존 값 유지(웰리 07-25)
MSG_DISPLAY_N = 0             # 0 = 선발된 것 전부 싣는다(GM 지시 2026-08-30 "다 보고 싶다"). 종전 5건
STALE_MIN_DAYS = 3           # 갓 들어온 문의는 정상 응대 흐름에 맡긴다
DORMANT_OVER_DAYS = 100      # 이 일수 "초과" + 연락이력 0건 = 휴면
# ★2026-08-20 시포 — 화면 아카이브 기준과 맞춘다(GM 신고: 알림에 뜬 이효주 님을 화면에서 못 찾음).
#   membership.html 의 _isOldUncontacted/STALE_ARCHIVE_DAYS(=60, GM 확정 2026-08-14)가 마지막 움직임
#   60일 초과 건을 목록에서 숨긴다. 그런데 이 알림은 "연락한 적 있나"를 contacts[].note 로 보고(_has_contact),
#   화면은 contacts[].date 로 본다 — 날짜 없이 메모만 있는 행에서 두 판정이 갈려, 화면에 없는 건을
#   알림이 배정하라고 보냈다(이효주 님 4/1 접수·140일째, 메모 "카카오톡 hyojoohk", 날짜 공란).
#   같은 값을 두 벌로 판정하지 않는다(약속 L01) — 화면과 같은 '마지막 움직임' 기준을 여기서도 쓴다.
STALE_ARCHIVE_DAYS = 60      # 마지막 움직임 후 이 일수 "이상" = 화면에서 숨겨진 건 → 알림도 보내지 않는다
# 마지막 움직임으로 치는 날짜 칸 — membership.html _lastActivityDays 와 같은 목록(한 곳만 고치면 갈린다).
_ACTIVITY_DATE_KEYS = ("exp1Time", "exp2Time", "exp3Time", "tourDate", "visitDate",
                       "visit2Date", "contact1", "contact2", "contact3")
RENOTIFY_GAP_DAYS = 1        # 같은 건 재알림 최소 간격 — 배정될 때까지 매일(GM 08-05). 같은 날 중복실행만 막는다.
NOTIFIED_KEEP_DAYS = 30      # 가드 맵에서 이보다 오래된 기록은 청소(무한 비대 방지)
HEARTBEAT_ID = "cpo-unassigned-nudge"  # 배10014 방식 — 상설 파일 1개 갱신

# ── 24시간 SLA 위반 → 카카오 ★부서장 방 (GM 2026-08-05 지시) ────────────────────
SLA_SINCE_DATE = "2026-08-01"  # 대상 = 이 날짜(포함) 이후 접수분만
SLA_HOURS = 24                 # 문턱 — 배정·컨택 둘 중 하나라도 없으면 위반
SLA_MSG_DISPLAY_N = 0          # 0 = 전부 싣는다(GM 지시 2026-08-30). 종전 3건
KAKAO_DEPTHEAD_ROOM = "★부서장"  # scripts/kakao_rooms.json 정본과 동일 값(창-제목 대조용)
ASSIGN_URL_MEMBER = _BASE + "membership.html"  # 회원 문의 처리 화면(60일 무응답 알림 링크용)

# ── 컨택 후 60일(2개월) 무응답 → 카카오 ★부서장 방 (GM 2026-08-05 지시) ──────────
NORESP_MIN_DAYS = 60    # 본선 문턱 — GM "기한을 2개월로"
NORESP_WARN_DAYS = 45   # 예고 문턱 — 60일 도달 전에 미리 뜨게(문턱 넘고 알리면 늦다)
NORESP_MSG_DISPLAY_N = 0  # 0 = 전부 싣는다(GM 지시 2026-08-30). 종전 5건


def _has_contact(row: dict) -> bool:
    """연락이력 유무 — contacts[] 에 내용 있는 메모가 1건이라도 있는지(브리프 §0)."""
    for c in row.get("contacts") or []:
        if isinstance(c, dict) and str(c.get("note", "") or "").strip():
            return True
    return False


def _lead_key(row: dict) -> str:
    """7일 가드용 안정 키. rowKey 원문(타임스탬프|전화번호)은 PII 라 해시로만 저장."""
    raw = str(row.get("rowKey", "") or "") or (
        str(row.get("timestamp", "") or "") + "|" + str(row.get("name", "") or "")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


_ROWS_CACHE: dict[str, list[dict]] = {}


def _lesson_rows(today: str) -> list[dict]:
    """강습 문의 전건(성인+유소년) — 한 회차 안에서 여러 번 쓰이므로 날짜별 1회만 조회.
    daily_scheduler 처럼 오래 사는 프로세스에서도 날짜가 바뀌면 자동으로 다시 읽는다."""
    if _ROWS_CACHE.get("date") != today:
        rows: list[dict] = []
        for label in ("성인강습", "유소년강습"):
            for r in R._fetch_list("lesson_inquiry_list", type=label):
                r["_label"] = label
                rows.append(r)
        _ROWS_CACHE.clear()
        _ROWS_CACHE.update({"date": today, "rows": rows})
    return _ROWS_CACHE.get("rows") or []


def collect_unassigned(today: str) -> list[dict]:
    """담당자 미배정 + 활성 강습 문의 전건(3일 이상 경과 · 상한 없음)."""
    sources: dict[str, list[dict]] = {"성인강습": [], "유소년강습": []}
    for r in _lesson_rows(today):
        sources[r.get("_label", "성인강습")].append(r)
    out: list[dict] = []
    for label, rows in sources.items():
        for r in rows:
            if R._is_test_row(r):
                continue
            days = R._days_since(str(r.get("timestamp", "") or ""), today)
            if days < STALE_MIN_DAYS:
                continue
            if not R._is_unassigned_active(r, True):
                continue
            sport = str(r.get("sport", "") or "-").strip() or "-"
            out.append({
                "type": label,
                "sport": sport,
                "group": f"{label} {_sport_short(sport)}",
                "name": str(r.get("name", "") or "-").strip() or "-",
                "date": str(r.get("timestamp", "") or "")[:10] or "-",
                "days": days,
                "contacted": _has_contact(r),
                "last_days": _last_activity_days(r, today),
                "key": _lead_key(r),
            })
    out.sort(key=lambda x: -x["days"])
    return out


def _last_activity_days(row: dict, today: str) -> int | None:
    """마지막 움직임(접수·연락·투어·체험) 이후 며칠 — membership.html _lastActivityDays 와 같은 계산.

    날짜가 하나도 없으면 None(판정 보류 = 숨기지 않는다). 화면은 contacts[].date 만 보고
    note 는 안 본다 — 여기서도 그대로 맞춘다(기준이 갈리면 화면과 알림이 또 어긋난다).
    """
    dates = []
    ts = str(row.get("timestamp", "") or "")[:10]
    if ts:
        dates.append(ts)
    for c in row.get("contacts") or []:
        if isinstance(c, dict):
            d = str(c.get("date", "") or "")[:10]
            if d:
                dates.append(d)
    for k in _ACTIVITY_DATE_KEYS:
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(row.get(k, "") or ""))
        if m:
            dates.append(m.group(0))
    if not dates:
        return None
    return R._days_since(max(dates), today)


def split_dormant(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(배정 푸시 대상, 휴면) 분리.

    휴면 두 갈래(둘 다 '숨기기'일 뿐 삭제·폐기 아님 — 월 1회 --list-dormant 로 검토):
      ① 연락이력 0건 AND 경과 100일 초과 (종전)
      ② 마지막 움직임 후 STALE_ARCHIVE_DAYS(60일) 이상 — 화면이 목록에서 숨긴 건과 같은 기준.
         화면에 없는 건을 배정하라고 보내면 받는 사람이 찾지 못한다(2026-08-20 GM 신고, 이효주 님).
    """
    eligible, dormant = [], []
    for it in items:
        last = it.get("last_days")
        if last is not None and last >= STALE_ARCHIVE_DAYS:
            dormant.append(it)
        elif (not it["contacted"]) and it["days"] > DORMANT_OVER_DAYS:
            dormant.append(it)
        else:
            eligible.append(it)
    return eligible, dormant


def sport_scores(items: list[dict]) -> dict[str, float]:
    """종목 점수 = 미배정건수 × 경과일 중앙값 × (0.5 + 미컨택비율) — 브리프 §0 공식 그대로."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        groups[it["group"]].append(it)
    scores: dict[str, float] = {}
    for g, its in groups.items():
        med = statistics.median(i["days"] for i in its)
        uncontacted = sum(1 for i in its if not i["contacted"]) / len(its)
        scores[g] = len(its) * med * (0.5 + uncontacted)
    return scores


def select_daily(items: list[dict], notified: dict[str, str], today: str,
                 top_n: int = DAILY_TOP_N) -> list[dict]:
    """오늘 안내할 상위 top_n 건.

    ① 재알림 가드: 마지막 안내로부터 RENOTIFY_GAP_DAYS 미만이면 이번 회차 제외
       (현재 1일 — 같은 날 중복 실행만 막고, 배정될 때까지 매일 다시 뜬다).
    ② 종목 점수 내림차순으로 종목을 세우고, 종목 안은 "연락이력 없음 우선 →
       경과일 오래된 순"으로 세운 뒤 라운드로빈으로 뽑는다(한 종목 독식 방지 —
       브리프 §0 방법 그대로).
    """
    fresh = []
    for it in items:
        last = notified.get(it["key"], "")
        if last and 0 <= R._days_since(last, today) < RENOTIFY_GAP_DAYS:
            continue
        fresh.append(it)
    if not fresh:
        return []
    scores = sport_scores(fresh)
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in fresh:
        groups[it["group"]].append(it)
    ordered = sorted(groups, key=lambda g: -scores[g])
    for g in ordered:
        groups[g].sort(key=lambda i: (i["contacted"], -i["days"]))
    picked: list[dict] = []
    rank = 0
    while len(picked) < top_n:
        took = False
        for g in ordered:
            if rank < len(groups[g]):
                picked.append(groups[g][rank])
                took = True
                if len(picked) >= top_n:
                    break
        if not took:
            break
        rank += 1
    return picked


# ── 7일 가드 상태 — 배10014 방식: 상설 하트비트 1파일 덮어쓰기 갱신(새 원장 금지) ──

def _load_heartbeat_extra(root: Path | None = None) -> dict:
    """상설 하트비트 1파일의 두 회전 상태(notified/notified60)를 함께 읽는다 — record_heartbeat()
    는 extra 를 통째로 덮어쓰므로, 한쪽만 갱신할 때 다른 쪽 상태가 지워지지 않게 항상 같이 들고 다닌다."""
    from module_heartbeat import PROJECT_ROOT, last_heartbeat
    rec = last_heartbeat(HEARTBEAT_ID, root=root or PROJECT_ROOT) or {}
    return {
        "notified": dict(rec.get("notified") or {}) if isinstance(rec.get("notified"), dict) else {},
        "notified60": dict(rec.get("notified60") or {}) if isinstance(rec.get("notified60"), dict) else {},
        # open = 지난 회차에 '아직 미배정'이던 건들 {키: 이름} — 다음 회차에 그중 몇이
        # 실제로 배정됐는지 세어 팡파레를 울리는 데만 쓴다(GM 2026-08-07). 새 파일 없음.
        "open": dict(rec.get("open") or {}) if isinstance(rec.get("open"), dict) else {},
    }


def _load_notified(root: Path | None = None) -> dict[str, str]:
    return _load_heartbeat_extra(root)["notified"]


def _load_notified60(root: Path | None = None) -> dict[str, str]:
    return _load_heartbeat_extra(root)["notified60"]


def _record_sent(selected: list[dict], notified: dict[str, str], today: str,
                 eligible_n: int, dormant_n: int, root: Path | None = None) -> dict:
    """발송 '성공' 직후에만 호출 — dry-run 은 가드 상태를 소모하지 않는다."""
    from module_heartbeat import PROJECT_ROOT, record_heartbeat
    merged = dict(notified)
    for it in selected:
        merged[it["key"]] = today
    merged = {k: v for k, v in merged.items()
              if 0 <= R._days_since(v, today) <= NOTIFIED_KEEP_DAYS}
    extra = _load_heartbeat_extra(root)
    extra["notified"] = merged
    # 이번 회차에 아직 미배정인 건들을 찍어 둔다 — 다음 회차가 이 명단과 대조해
    # 실제로 담당이 붙은 건만 팡파레로 축하한다(GM 2026-08-07). 행 조회는 캐시 재사용.
    extra["open"] = {i["key"]: i["name"] for i in split_dormant(collect_unassigned(today))[0]}
    return record_heartbeat(
        HEARTBEAT_ID,
        detail=f"배정 안내 {len(selected)}건 발송(대상 {eligible_n}건 · 휴면 제외 {dormant_n}건)",
        extra=extra,
        root=root or PROJECT_ROOT,
    )


def _record_sent60(selected: list[dict], notified60: dict[str, str], today: str,
                    current_keys: set[str], due_n: int, root: Path | None = None) -> dict:
    """60일 무응답 경보 발송 '성공' 직후에만 호출. current_keys=이번 회차 due 후보 키 집합 —
    여기 없는 옛 키(등록/LOSS 처리 또는 재컨택으로 후보에서 빠진 건)는 자동 청소된다
    (GM "처리되면 목록에서 사라진다")."""
    from module_heartbeat import PROJECT_ROOT, record_heartbeat
    merged = dict(notified60)
    for it in selected:
        merged[it["key"]] = today
    merged = {k: v for k, v in merged.items()
              if k in current_keys and 0 <= R._days_since(v, today) <= NOTIFIED_KEEP_DAYS}
    extra = _load_heartbeat_extra(root)
    extra["notified60"] = merged
    return record_heartbeat(
        HEARTBEAT_ID,
        detail=f"60일 무응답 안내 {len(selected)}건 발송(대상 {due_n}건)",
        extra=extra,
        root=root or PROJECT_ROOT,
    )


def _sport_short(sport: str) -> str:
    """종목명을 세부 옵션 앞부분으로 정규화.

    원본이 '성인 수영 (개인레슨 / 단체레슨)'·'뮤지컬 (Brad Little Star Academy)' 처럼
    괄호 안 세부가 붙어 오는데, 그대로 세면 같은 종목이 여러 줄로 쪼개진다(실제 발생).
    """
    return sport.split("(")[0].strip() or "-"


def _hours_since_ts(ts: str, now_dt: datetime) -> float:
    """접수 타임스탬프(실측 형식 "YYYY-MM-DD HH:MM:SS")부터 now_dt 까지 경과시간(시간
    단위, 소수). R._days_since() 는 날짜만 잘라 비교해 자정 근처 오차가 최대 하루라
    24시간 문턱 판정엔 못 쓴다 — 이 함수는 시각까지 그대로 써서 실제 경과시간을 잰다."""
    raw = str(ts or "").strip()
    d0 = None
    try:
        d0 = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            d0 = datetime.strptime(raw[:10], "%Y-%m-%d")  # 시각 없는 값 폴백(자정 취급)
        except Exception:
            return 0.0
    return (now_dt - d0).total_seconds() / 3600.0


def _is_assigned_owner(row: dict) -> bool:
    """담당자 배정 여부(연락 유무와 무관) — R._is_unassigned_active 와 같은 오너 판정
    (owner 비었거나 자동접수값이면 미배정)이지만 등록/이탈 여부는 섞지 않는다."""
    owner = str(row.get("owner", "") or "").strip()
    return bool(owner) and owner not in R._AUTO_OWNER_VALUES


def _fmt_elapsed(hours: float) -> str:
    if hours < 48:
        return f"{int(hours)}시간"
    return f"{int(hours // 24)}일"


MEMBER_DEFAULT_OWNER = "임정은"   # 멤버십 문의 담당은 이 한 사람뿐이다(GM 확정 2026-08-14)


def assign_member_owners(apply: bool = False) -> list[dict]:
    """담당이 비었거나 '웹 자동접수' 인 진행중 멤버십 문의를 임정은M 앞으로 채운다.

    GM 지시 2026-08-14: "멤버십은 담당자가 임정은M 밖에 없을텐데? 자동으로 배정해줘."
    ▸강습은 종목별 팀이 갈려 collect_auto_assign 이 따로 판단하지만, 멤버십은 후보가 한 명이라
      판단할 것이 없다 — 비어 있으면 채운다.
    ▸쓰기는 화면과 같은 관문(member_inquiry_update)만 쓴다. 새 액션 없음(약속 L21).
    ▸대조키(rowKey·keyPhone) 동봉 — 행번호만 믿고 쓰면 남의 행을 고친다(INC-013·INC-020).
    """
    import json as _json
    import requests
    rows = R._fetch_list("member_inquiry_list")
    out = []
    for r in rows:
        if R._is_test_row(r):
            continue
        if R._is_registered(r, False) or R._is_loss(r):
            continue
        owner = str(r.get("owner", "") or "").strip()
        if owner and owner not in R._AUTO_OWNER_VALUES:
            continue
        item = {"name": str(r.get("name", "") or "-"), "rowIndex": r.get("rowIndex"), "ok": None}
        if apply:
            body = {"action": "member_inquiry_update", "rowIndex": r.get("rowIndex"),
                    "gid": r.get("gid"), "rowKey": r.get("rowKey"), "keyPhone": r.get("phone"),
                    "owner": MEMBER_DEFAULT_OWNER}
            try:
                res = requests.post(R.FUNNEL_EXEC_URL, data=_json.dumps(body).encode("utf-8"),
                                    headers={"Content-Type": "text/plain;charset=utf-8"},
                                    timeout=60, allow_redirects=True)
                j = res.json()
                item["ok"] = bool(j.get("ok"))
                if not item["ok"]:
                    item["error"] = str(j.get("error") or "")
            except Exception as e:  # noqa: BLE001
                item["ok"] = False
                item["error"] = str(e)[:120]
        out.append(item)
    return out


def collect_sla_violations(now: datetime | None = None) -> list[dict]:
    """8/1(SLA_SINCE_DATE) 이후 접수 강습 문의 중 24시간(SLA_HOURS) 경과 +
    (담당자 없음 또는 컨택기록 0건) 위반건. 이미 등록완료·이탈종결(LOSS)로 끝난
    건은 빼고(R._is_registered/_is_loss 재사용 — 판정 기준 두 벌 금지), 경과시간
    내림차순(오래된 위반 먼저)으로 반환한다."""
    now = now or datetime.now()
    # 2026-08-14 GM 물음('이제 신경쓸 것 없나') 답하다 발견 — 멤버십이 이 경보에서 통째로 빠져 있었다.
    #   실측: 8/1 이후 미컨택 멤버십 5건(맹기훈·익명여/신동아·이도경·정새벽·육세라)이 24시간을 한참
    #   넘겼는데 한 번도 이 경보에 안 실렸다. 강습만 보던 것을 회원까지 넓힌다(판정·문턱은 그대로).
    sources = {
        "성인강습": R._fetch_list("lesson_inquiry_list", type="성인강습"),
        "유소년강습": R._fetch_list("lesson_inquiry_list", type="유소년강습"),
        "멤버십": R._fetch_list("member_inquiry_list"),
    }
    out: list[dict] = []
    for label, rows in sources.items():
        for r in rows:
            if R._is_test_row(r):
                continue
            ts = str(r.get("timestamp", "") or "")
            if ts[:10] < SLA_SINCE_DATE:
                continue
            if R._is_registered(r, True) or R._is_loss(r):
                continue  # 이미 해결된 리드 — 위반 알림 대상 아님
            hours = _hours_since_ts(ts, now)
            if hours < SLA_HOURS:
                continue
            assigned = _is_assigned_owner(r)
            contacted = _has_contact(r)
            if assigned and contacted:
                continue  # 배정도 컨택도 됐으면 정상
            out.append({
                "type": label,
                "sport": str(r.get("sport", "") or r.get("program", "") or "-").strip() or "-",  # 멤버십은 종목 대신 상품명
                "name": str(r.get("name", "") or "-").strip() or "-",
                "date": ts[:16] or "-",
                "hours": hours,
                "assigned": assigned,
                "contacted": contacted,
                # GM 지적 2026-08-31 — "배정완료건도 보는데 미배정·미컨택 내용이 정확하지 않다."
                # 담당이 이미 정해진 건을 '담당있음·컨택없음' 이라 적어도, 표제가 「미배정·미컨택」
                # 이라 받는 사람은 전부 미배정으로 읽었다. 실측 당시 36건 중 30건이 배정완료였다.
                # 두 상태를 사람 말로 갈라 적는다 — 해야 할 일이 서로 다르다(배정 vs 연락).
                "reason": "담당 미정" if not assigned else "배정완료·기록없음",
            })
    out.sort(key=lambda x: -x["hours"])
    return out


def build_sla_alert_text(violations: list[dict]) -> str:
    """카카오 ★부서장 방용 평문(GM 2026-08-05) — 위반 0건이면 빈 문자열(발송 안 함).
    10줄 안쪽·한 줄에 한 건(접수일시·이름·종목·경과시간·상태)·부탁 조·AI 주체 명시."""
    if not violations:
        return ""
    # 이미 경과시간 내림차순(오래된 순). 0 = 전부(GM 지시 2026-08-30)
    shown = violations if SLA_MSG_DISPLAY_N <= 0 else violations[:SLA_MSG_DISPLAY_N]
    rest_n = len(violations) - len(shown)
    # 표제는 두 숫자를 갈라 적는다(GM 지적 2026-08-31). 「미배정·미컨택 N건」 한 덩어리로 적으면
    # 이미 담당이 정해진 건까지 미배정으로 읽힌다 — 실측 당시 36건 중 30건이 배정완료였고,
    # 그 건들에 필요한 것은 배정이 아니라 연락(또는 연락 기록)이다.
    _no_owner = sum(1 for v in violations if not v.get("assigned"))
    _no_contact = len(violations) - _no_owner
    _head = f"⏰ 24시간 넘긴 문의 {len(violations)}건 (8/1 이후 접수분)"
    _parts = []
    if _no_owner:
        _parts.append(f"담당 미정 {_no_owner}건")
    if _no_contact:
        _parts.append(f"배정완료·연락기록 없음 {_no_contact}건")
    if _parts:
        _head += " — " + " · ".join(_parts)
    lines = [_head]
    # GM 지시 2026-08-14: 확인만 부탁하니 답이 없어 같은 건이 13일째 남았다.
    #   ①기준(24시간)을 매번 알리고 ②회신을 명시적으로 요청한다. 줄 수는 표시 건수로 상쇄.
    # GM 지시 2026-08-31: "담당자 배정보단 컨택 내용 기록이 더 중요하니까 그 부분을 다시 한번
    #   어필해줘." 그래서 첫 줄이 기준 설명이 아니라 **기록 요청**이다 — 앞줄일수록 읽힌다.
    #   종전 첫 줄(24시간 기준 설명)은 셋째 줄로 내렸다. 줄 수는 그대로 3줄(10줄 상한 유지).
    # GM 지시 2026-08-14 도 그대로 산다: 연락을 안 한 건과 연락은 했는데 기록만 빠진 건을 가른다.
    lines.append("❗가장 중요한 건 연락 기록입니다 — 담당이 정해져 있어도 기록이 없으면 저희 화면엔 연락 안 한 건으로 남습니다.")
    lines.append("이미 통화·문자 하셨으면 화면에 한 줄만 남겨 주시고, 아직이면 연락 먼저 부탁드립니다.")
    lines.append("기준은 접수 후 24시간 안 첫 연락입니다. 처리하신 건은 한 줄 회신 부탁드립니다 🙏")
    for it in shown:
        # 유형(멤버십/강습)을 앞에 적는다 — 2026-08-14 회원 문의까지 넓히면서 어느 화면에서
        #   처리해야 하는지가 줄만 봐서는 안 보이게 됐다.
        lines.append(f"· [{it['type']}] {it['date']} · {it['name']} · {_sport_short(it['sport'])} · "
                     f"{_fmt_elapsed(it['hours'])}째 · {it['reason']}")
    if rest_n > 0:
        lines.append(f"… 외 {rest_n}건 (총 {len(violations)}건)")
    # 링크는 한 줄에 하나 — 704행과 같은 이유다. ' · ' 로 이어 붙이면 카톡이 첫 주소 뒤
    # 구분자·다음 주소까지 하나의 링크로 먹어 404 가 난다(2026-08-08 실측, 2026-08-27 재발).
    # 그리고 이 목록에 실제로 들어 있는 종류의 링크만 건다 — 2026-08-27 GM 지시로 강습은
    # ★부서장, 멤버십은 ★운영부로 갈라 보내므로 남의 화면 링크를 같이 주면 헷갈린다.
    _types = {v.get("type", "") for v in violations}
    if any("강습" in t for t in _types):
        lines.append(f"👉 강습: {ASSIGN_URL_LESSON}")
    if "멤버십" in _types:
        lines.append(f"👉 멤버십: {ASSIGN_URL_MEMBER} (입장코드 {ENTRY_CODE})")
    lines.append(AI_SIGNOFF)
    return "\n".join(lines)


# ── 24시간 SLA 위반 발신 게이트(2026-08-15 GM 지시 · 중복 알림 정리) ────────────────
# 실측: 8/10~14 매일 같은 명단이 "9일째"→"13일째"로 숫자만 오르며 5번 독촉, 움직임 0건.
#   변화 없는 재독촉은 소음이라 "직전 발신 대비 새로 생긴 건·해소된 건이 있을 때만" 보낸다.
#   전체 명단(움직임 없는 오래된 건 포함)은 주 1회(월요일)만 재노출 — 잊혀지지 않게 하되
#   매일 안 울린다. 새 예약작업 없음(약속 L21) — 기존 daily_scheduler SLA 발송 앞에 게이트만 얹는다.
SLA_ALERT_STATE_PATH = Path(_HERE).parent / "status" / "sla_alert_state.json"


def _sla_violation_key(it: dict) -> str:
    return f"{it['type']}::{it['name']}::{it['date']}"


def sla_alert_gate(violations: list[dict], now: datetime | None = None) -> bool:
    """True = 오늘 보낸다. 월요일은 전체 재노출로 항상 True. 그 외 요일은 직전 발신 키셋과
    비교해 달라졌을 때만 True(신규 발생 또는 해소 둘 다 '변화'). 상태 파일이 없거나 깨졌으면
    비교 기준이 없으므로 보수적으로 True(놓치는 것보다 한 번 더 보내는 게 낫다)."""
    now = now or datetime.now()
    if now.weekday() == 0:  # 월요일 — 전체 재노출
        return True
    try:
        prev = set(json.loads(SLA_ALERT_STATE_PATH.read_text(encoding="utf-8")).get("keys") or [])
    except Exception:
        return True
    curr = {_sla_violation_key(it) for it in violations}
    return curr != prev


def record_sla_alert_sent(violations: list[dict], now: datetime | None = None) -> None:
    """SLA 위반 알림이 실제로 나간 뒤 호출 — 다음 비교의 기준(직전 발신 키셋)을 남긴다."""
    now = now or datetime.now()
    try:
        SLA_ALERT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SLA_ALERT_STATE_PATH.write_text(json.dumps({
            "keys": sorted({_sla_violation_key(it) for it in violations}),
            "sent_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _last_activity_days(row: dict, today: str) -> int | None:
    """최근 활동(접수일 또는 연락이력[].date 중 가장 최근) 경과일. 날짜 전무=None(판정불가)."""
    dates = []
    ts = str(row.get("timestamp", "") or "")[:10]
    if ts:
        dates.append(ts)
    for c in row.get("contacts") or []:
        if isinstance(c, dict):
            d = str(c.get("date", "") or "")[:10]
            if d:
                dates.append(d)
    if not dates:
        return None
    return R._days_since(max(dates), today)  # YYYY-MM-DD 문자열 비교=날짜비교 안전, max=가장 최근


def collect_noresponse(today: str) -> list[dict]:
    """컨택 후(contacts[]≥1) 무응답 — 최근활동 경과 NORESP_WARN_DAYS(45)일 이상, 강습+회원 통합.
    등록완료·이탈종결(LOSS)은 제외(R._is_registered/_is_loss — collect_sla_violations와 동일 판정틀).
    미컨택(contacts 0건)은 대상 아님 — 그건 배정독려(collect_unassigned)가 이미 다룬다.
    경과일 내림차순(오래된 순) 반환 — 45~59일(예고)과 60일+(본선)은 호출부에서 split."""
    sources = {
        "성인강습": (R._fetch_list("lesson_inquiry_list", type="성인강습"), True),
        "유소년강습": (R._fetch_list("lesson_inquiry_list", type="유소년강습"), True),
        "회원": (R._fetch_list("member_inquiry_list"), False),
    }
    out: list[dict] = []
    for label, (rows, is_lesson) in sources.items():
        for r in rows:
            if R._is_test_row(r):
                continue
            if R._is_registered(r, is_lesson) or R._is_loss(r):
                continue
            if not _has_contact(r):
                continue
            days = _last_activity_days(r, today)
            if days is None or days < NORESP_WARN_DAYS:
                continue
            sport = str(r.get("sport") or r.get("program") or "-").strip() or "-"
            out.append({
                "kind": label,
                "sport": sport,
                "name": str(r.get("name", "") or "-").strip() or "-",
                "date": str(r.get("timestamp", "") or "")[:10] or "-",
                "owner": str(r.get("owner", "") or "-").strip() or "-",
                "days": days,
                "key": _lead_key(r),
            })
    out.sort(key=lambda x: -x["days"])
    return out


def split_noresponse(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(60일+ 본선, 45~59일 예고) 분리 — 임계값이 서로 배타적이라 겹치지 않는다."""
    due = [it for it in items if it["days"] >= NORESP_MIN_DAYS]
    warn = [it for it in items if it["days"] < NORESP_MIN_DAYS]
    return due, warn


def select_noresponse_rotation(due: list[dict], notified60: dict[str, str],
                                top_n: int = NORESP_MSG_DISPLAY_N) -> list[dict]:
    """회전 선발 — 마지막으로 보여준 날짜 오름차순(못 보여준 건 "" 이 가장 앞) → 경과일
    내림차순. 오늘 보여준 건은 notified60 기록 후 다음 선발에서 뒤로 밀린다(라운드로빈).
    처리(등록/LOSS/재컨택)된 건은 due 자체에서 빠지므로 자동으로 회전에서 사라진다."""
    ordered = sorted(due, key=lambda it: (notified60.get(it["key"], ""), -it["days"]))
    return ordered if top_n <= 0 else ordered[:top_n]


def build_noresponse_alert_text(due: list[dict], warn_n: int, selected: list[dict]) -> str:
    """카카오 ★부서장 방용 평문(GM 2026-08-05) — 60일+ 0건이면 빈 문자열(발송 안 함).
    10줄 이내·한 줄에 한 건(접수일·이름·종목·경과일·담당자)·상태선택 유도·AI 서명."""
    if not due:
        return ""
    shown = selected if NORESP_MSG_DISPLAY_N <= 0 else selected[:NORESP_MSG_DISPLAY_N]
    rest_n = len(due) - len(shown)
    oldest = due[0]["days"]  # collect_noresponse()에서 이미 -days 정렬됨
    warn_part = f" · 2개월 임박(45~59일) {warn_n}건 곧 도달" if warn_n else ""
    # 총 건수를 맨 앞에 크게 내면 받는 사람이 "501건을 하라는 건가" 로 읽고 손을 놓는다
    # (2026-08-08 GM 지적 — 카톡에 501건이 그대로 떴다). 오늘 부탁하는 건 shown 뿐이라는 걸
    # 첫 줄에서 못 박고, 전체 규모는 맨 아래 참고 한 줄로 내린다.
    lines = [f"🗓️ 컨택 후 2개월(60일+) 무응답 — 오늘 {len(shown)}건만 봐 주세요"]
    lines.append("계속 진행 / LOSS / 보류 중 하나로만 알려주시면 됩니다 🙏")
    # 같은 사람이 같은 날 같은 종목으로 두 번 접수된 행이 있다 — 그대로 뿌리면 똑같은 줄이
    # 두 번 떠서 받는 사람은 오류로 읽는다(2026-08-08 GM 실측: 김은희 2줄). 데이터는 그대로
    # 두고 화면에서만 합쳐 건수를 붙인다.
    _seen: dict[tuple, int] = {}
    _order: list[tuple] = []
    for it in shown:
        k = (it["date"], it["name"], it["sport"], it["owner"])
        if k not in _seen:
            _seen[k] = 0
            _order.append(k)
        _seen[k] += 1
    for it in shown:
        k = (it["date"], it["name"], it["sport"], it["owner"])
        if k not in _order:
            continue
        _order.remove(k)
        dup = f" ({_seen[k]}건)" if _seen[k] > 1 else ""
        lines.append(f"· {it['date']} · {it['name']} · {_sport_short(it['sport'])} · "
                     f"{it['days']}일째 · 담당:{it['owner']}{dup}")
    if rest_n > 0:
        lines.append(f"(전체 {len(due)}건 · 가장 오래된 건 {oldest}일째{warn_part} — 매일 몇 건씩 나눠 보내드립니다)")
    # 링크는 한 줄에 하나. ' · ' 로 이어 붙이면 카톡이 첫 주소 뒤 구분자까지 링크로 먹어 깨진다
    # (2026-08-08 GM 실측 — lesson.html%20·%20https://… 로 잘려 나갔다).
    lines.append(f"🔗 강습: {ASSIGN_URL_LESSON}")
    lines.append(f"🔗 회원: {ASSIGN_URL_MEMBER} (입장코드 {ENTRY_CODE})")
    lines.append(AI_SIGNOFF)
    return "\n".join(lines)


# ── 2주 경과 미배정 → 종목 팀장 이름으로 일괄 배정 (GM 지시 2026-08-07) ──────────
# GM: "담당자 배정 2주 정도 지나면 각 팀장이름으로 일단 배정해서 마무리해줘" · "이번 한 번만"
# 이름은 지어내지 않는다 — 이미 배정된 1,285건에서 종목별 최다 담당자를 실측해 뽑은 표다
# (2026-08-07 실측). 위에서부터 첫 일치(모자수영이 수영보다 먼저 와야 한다).
# 판단이 갈리는 종목(키성장 P.T·웰니스)은 넣지 않는다 — 최다값이 3표 차 안이라 찍는 것과 같다.
AUTO_ASSIGN_MIN_DAYS = 2   # 48시간(GM 확정 2026-08-29 · 종전 14일) — 「담당 없음」 유형을 구조로 0으로
TEAM_LEAD_BY_SPORT = [
    # 발레·바레 = 외부 파트너 루프메소드 담당(GM 지정 2026-08-07). 실측 표가 아니라 GM 지정값이다.
    ("발레", "루프메소드"), ("바레", "루프메소드"),
    ("모자수영", "김성은"), ("체조", "이형주"), ("뮤지컬", "편한별"),
    ("스쿼시", "이상훈"), ("골프", "최현준"), ("필라테스", "최은지"),
    ("수영", "박민서"), ("P.T", "김상식"),
]
AMBIGUOUS_SPORT_KEYS = ("키성장", "웰니스")   # GM 확인 전까지 자동 배정 제외


# ── 종목별 강사 명단·팀장 = 화면(membership.html)이 정본 ──────────────────────
# 같은 명단을 파이썬에 베껴 두면 GM 이 화면에서 팀장을 바꿔도 이쪽은 옛 사람을 계속 쓴다
# (실제로 그랬다 — 골프 팀장이 2026-08-05 에 최현준→김태엽으로 바뀌었는데 이 파일 표는
#  최현준 그대로였다). 그래서 화면 파일에서 읽어 쓴다(약속 L01 한 곳만 본다).
_PAGE = Path(_HERE).parent / "3. 웰페리온 가이드" / "cpo" / "member" / "membership.html"
_ROSTER_CACHE: dict = {}

# _lessonRosterKeyOf / _lessonTeamLeadOf 의 판정 순서를 그대로 옮긴 것(위에서부터 첫 일치).
# 순서가 뜻을 가진다 — 'WSC 키성장 P.T' 는 WSC(체조)보다 P.T 가 먼저 잡혀야 한다.
_SPORT_KEY_RULES = [
    (re.compile(r"아쿠아"), "수영"), (re.compile(r"수영"), "수영"),
    (re.compile(r"Parent.?Child|swim", re.I), "수영"),
    (re.compile(r"P\.?T", re.I), "P.T"), (re.compile(r"필라"), "필라테스"),
    (re.compile(r"발레|바레"), "웰니스"),
    (re.compile(r"골프"), "골프"), (re.compile(r"스쿼시"), "스쿼시"),
    (re.compile(r"체조|트램폴린|WSC", re.I), "체조&트램폴린"),
    (re.compile(r"뮤지컬"), "뮤지컬팀"),
    (re.compile(r"웰니스|wellness|루프", re.I), "웰니스"),
]


def _load_roster() -> tuple[dict, dict]:
    """(종목키→강사 명단, 종목키→팀장) — 화면 파일에서 직접 읽는다."""
    if _ROSTER_CACHE:
        return _ROSTER_CACHE["roster"], _ROSTER_CACHE["leads"]
    html = _PAGE.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"var LESSON_INSTRUCTOR_ROSTER\s*=\s*(\{.*?\n\});", html, re.S)
    if not m:
        raise RuntimeError("membership.html 에서 강사 명단을 찾지 못함")
    body = re.sub(r"//[^\n]*", "", m.group(1))          # 주석 제거 후 JSON 으로 읽는다
    roster = json.loads(re.sub(r",(\s*[}\]])", r"\1", body))
    leads = {}
    for line in re.findall(r"if \(/([^/]+)/[a-z]*\.test\(s\)\) return '([^']+)';",
                           html[html.find("function _lessonTeamLeadOf"):][:1200]):
        leads[line[0]] = line[1]
    _ROSTER_CACHE.update({"roster": roster, "leads": leads})
    return roster, leads


def sport_key_of(sport: str) -> str | None:
    """종목 표기 → 명단 키(화면 _lessonRosterKeyOf 와 같은 순서·같은 결과)."""
    s = str(sport or "")
    for rx, key in _SPORT_KEY_RULES:
        if rx.search(s):
            return key
    return None


def team_of(sport: str) -> tuple[str, list[str]] | tuple[None, list]:
    """종목 표기 → (팀장, 그 팀 강사 명단). 판정 못 하면 (None, [])."""
    key = sport_key_of(sport)
    if not key:
        return None, []
    roster, leads = _load_roster()
    names = list(roster.get(key) or [])
    lead = ""
    for pat, who in leads.items():
        if re.search(pat, str(sport or ""), re.I):
            lead = who
            break
    if not lead and names:
        lead = names[0]
    if lead and lead not in names:
        names = [lead] + names
    return (lead or None), names


def lead_for_sport(sport: str) -> str | None:
    """첫 종목 기준 팀장 이름. 모호 종목·미등록 종목은 None(사람이 처리)."""
    first = _sport_short(str(sport or "").split(",")[0])
    if any(k in first for k in AMBIGUOUS_SPORT_KEYS):
        return None
    for key, lead in TEAM_LEAD_BY_SPORT:
        if key in first:
            return lead
    return None


def collect_auto_assign(today: str, min_days: int = AUTO_ASSIGN_MIN_DAYS) -> tuple[list[dict], list[dict]]:
    """(배정 대상, 보류) — 보류 사유는 'reason' 에 적는다.

    보류가 되는 두 경우: ①대조키(전화·지문키)가 없어 안전하게 못 쓰는 행 — 행번호만 믿고
    쓰면 남의 행을 고친다(INC-013·INC-020) ②종목이 모호하거나 표에 없어 이름을 못 정하는 행.
    """
    ready, held = [], []
    for label in ("성인강습", "유소년강습"):
        for r in R._fetch_list("lesson_inquiry_list", type=label):
            if R._is_test_row(r):
                continue
            days = R._days_since(str(r.get("timestamp", "") or ""), today)
            if days < min_days or not R._is_unassigned_active(r, True):
                continue
            item = {"type": label, "name": str(r.get("name", "") or "-").strip() or "-",
                    "sport": str(r.get("sport", "") or "-").strip() or "-", "days": days,
                    "rowIndex": r.get("rowIndex"), "rowKey": str(r.get("rowKey", "") or ""),
                    "phone": str(r.get("phone", "") or "").strip(), "gid": r.get("gid"),
                    "date": str(r.get("timestamp", "") or "")[:10]}
            lead = lead_for_sport(item["sport"])
            if not item["phone"] and not item["rowKey"]:
                item["reason"] = "대조키 없음(전화·지문키 빈칸)"
                held.append(item)
            elif not lead:
                item["reason"] = "종목 팀장 미정"
                held.append(item)
            else:
                item["owner"] = lead
                ready.append(item)
    ready.sort(key=lambda x: -x["days"])
    held.sort(key=lambda x: -x["days"])
    return ready, held


def collect_owner_fixes(today: str) -> tuple[list[dict], list[dict]]:
    """담당이 그 종목 팀 사람이 아닌 문의를 골라 (고칠 것, 보류)로 나눈다 (GM 지시 2026-08-07).

    GM: "뮤지컬은 담당자가 편한별밖에 없어서 통일" · "키성장 P.T 도 PT팀이면 그대로, 다른 팀이면
    김상식으로" · "스쿼시 필라테스 다 비슷하네 · 유소년 목록은 내가 못 찾는 것까지 다 보완".
    ▸판정은 화면과 같은 명단(membership.html 정본)으로 한다 — 기준이 두 벌이 되면 화면과 값이 갈린다.
    ▸그 팀 사람이면 팀장이 아니어도 그대로 둔다(팀 안에서 누가 맡든 우리가 정할 일이 아니다).
    ▸여러 종목을 신청한 행은 담당 칸이 종목별로 나뉘지 않는다(한 칸을 공유) —
      **어느 신청 종목 팀에도 속하지 않을 때만** 첫 종목 팀장으로 맞춘다.
    ▸등록완료·이탈(LOSS)로 끝난 건은 건드리지 않는다 — 담당자별 등록율이 바뀌어 실적이 흔들린다.
    """
    fix, held = [], []
    for label in ("성인강습", "유소년강습"):
        for r in R._fetch_list("lesson_inquiry_list", type=label):
            if R._is_test_row(r):
                continue
            if R._is_registered(r, True) or R._is_loss(r):
                continue
            sport = str(r.get("sport", "") or "").strip()
            segs = [s.strip() for s in sport.split(",") if s.strip()] or [sport]
            teams = [team_of(s) for s in segs]
            known = [(lead, names) for lead, names in teams if lead]
            if not known:
                continue                      # 종목을 못 알아보는 행은 사람 몫(지어내지 않는다)
            owner = str(r.get("owner", "") or "").strip()
            if owner and owner not in R._AUTO_OWNER_VALUES:
                if any(owner in names for _, names in known):
                    continue                  # 그 종목 팀 사람 — 그대로 둔다
            lead = known[0][0]
            if owner == lead:
                continue
            item = {"name": str(r.get("name", "") or "-").strip() or "-", "sport": sport,
                    "owner": lead, "before": owner or "(빈칸)", "type": label,
                    "rowIndex": r.get("rowIndex"), "rowKey": str(r.get("rowKey", "") or ""),
                    "phone": str(r.get("phone", "") or "").strip(), "gid": r.get("gid"),
                    "date": str(r.get("timestamp", "") or "")[:10]}
            if not item["phone"] and not item["rowKey"]:
                item["reason"] = "대조키 없음(전화·지문키 빈칸)"
                held.append(item)
            else:
                fix.append(item)
    return fix, held


def apply_auto_assign(ready: list[dict], timeout: float = 60.0) -> list[dict]:
    """실제 쓰기 — 기존 화면과 같은 관문(lesson_inquiry_update)만 쓴다. 새 액션 없음.
    대조키(rowKey·keyPhone) 동봉 필수 — GAS 가 fail-closed 로 검증한다(배294)."""
    import requests
    out = []
    for it in ready:
        body = {"action": "lesson_inquiry_update", "rowIndex": it["rowIndex"],
                "owner": it["owner"], "keyPhone": it["phone"], "gid": it["gid"]}
        if it["rowKey"]:
            body["rowKey"] = it["rowKey"]
        try:
            resp = requests.post(R.FUNNEL_EXEC_URL, json=body, timeout=timeout,
                                 allow_redirects=True)
            d = resp.json()
            out.append({**it, "ok": bool(d.get("ok")), "error": d.get("error", "")})
        except Exception as e:
            out.append({**it, "ok": False, "error": str(e)[:80]})
    return out


def newly_assigned(prev_open: dict, today: str) -> list[dict]:
    """지난 회차에 미배정이던 건 중 **이번에 담당자가 붙은 건**만 골라낸다(GM 2026-08-07 '팡파레').

    사라진 키를 세지 않고 행을 다시 열어 owner 를 확인한다 — 등록완료·이탈(LOSS)로 목록에서
    빠진 건까지 '배정했다'고 축하하면 팀장님들이 받는 숫자가 사실이 아니게 된다.
    """
    if not prev_open:
        return []
    rows = {_lead_key(r): r for r in _lesson_rows(today)}
    out = []
    for key, name in prev_open.items():
        r = rows.get(key)
        if r is not None and _is_assigned_owner(r):
            out.append({"name": str(name or r.get("name") or "-"),
                        "owner": str(r.get("owner", "") or "-").strip(),
                        "sport": _sport_short(str(r.get("sport", "") or "-"))})
    return out


def _render_cheer(done: list[dict], eligible_n: int) -> str:
    """팡파레 한 줄(+담당별 건수). 배정된 게 없고 미배정도 남아 있으면 빈 문자열."""
    if not done and eligible_n:
        return ""
    if done:
        by = defaultdict(int)
        for d in done:
            by[d["owner"] or "-"] += 1
        who = " · ".join(f"{o} {n}건" for o, n in sorted(by.items(), key=lambda x: -x[1])[:4])
        head = f"🎉 배정 완료 {len(done)}건 — {who}. 감사합니다 🙏"
    else:
        head = "🎉 감사합니다 🙏"
    if not eligible_n:
        return head + "\n🏁 미배정 0건 — 전부 배정 끝났습니다!"
    return head


def build_payload(today: str | None = None, notified: dict[str, str] | None = None) -> dict:
    """오늘 회차 산출물 한 벌: 본문 + 선발 10건 + 휴면 목록 + 집계 + 팡파레."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    extra = _load_heartbeat_extra()
    notified = extra["notified"] if notified is None else notified
    items = collect_unassigned(today)
    eligible, dormant = split_dormant(items)
    selected = select_daily(eligible, notified, today)
    done = newly_assigned(extra["open"], today)
    cheer = _render_cheer(done, len(eligible))
    # 하루 일과 정리에서 옮겨 온 두 줄(2026-08-20 GM 신고 — 중복). 조회 실패해도 본 메시지는
    # 나가야 한다(촉구 한 통이 통째로 멈추는 것이 더 나쁘다).
    try:
        _mem = R._fetch_list("member_inquiry_list")
        _ad = R._fetch_list("lesson_inquiry_list", type="성인강습")
        _yo = R._fetch_list("lesson_inquiry_list", type="유소년강습")
        today_new = collect_today_unassigned(today, _mem, _ad, _yo)
        uncontacted = R._uncontacted_membership(
            {"membership": _mem, "adult": _ad, "youth": _yo}, today)
    except Exception:
        today_new, uncontacted = [], []
    try:
        loss_gaps = collect_loss_reason_gaps()
    except Exception:
        loss_gaps = []
    return {
        "today": today,
        "text": _render_message(selected, eligible, dormant, cheer, today_new, uncontacted, loss_gaps),
        "selected": selected,
        "eligible": eligible,
        "dormant": dormant,
        "notified": notified,
        "cheered": done,
    }


def _render_message(selected: list[dict], eligible: list[dict], dormant: list[dict],
                    cheer: str = "", today_new: list | None = None,
                    uncontacted: list | None = None, loss_gaps: list | None = None) -> str:
    """그것만 담은 독립 메시지(GM 2026-08-05) — 10줄 안쪽·한 줄에 한 건·부탁 조.

    텔레그램 굵게가 잘 안 먹어 줄바꿈·기호로 읽히게 한다. 표시는 선발 top MSG_DISPLAY_N
    건을 "오래된 순"으로 다시 정렬해서 싣는다(select_daily 의 회전 선발 순서는 종목별
    공정 배분용이라 화면 순서와 다르다). 나머지는 "외 N건"+총계로 접는다(도배 방지).
    """
    today_new = today_new or []
    uncontacted = uncontacted or []
    loss_gaps = loss_gaps or []
    _extra = _extra_sections(today_new, uncontacted, loss_gaps)
    if not eligible:
        # 팡파레가 있으면 그것만으로 충분(같은 뜻을 두 줄로 적지 않는다).
        _head = cheer or "✅ 담당자 미배정 문의 0건 — 모두 배정 완료되었습니다. 감사합니다 🙏"
        # 배정은 다 됐어도 '오늘 신규 미담당'·'멤버십 미컨택'은 남아 있을 수 있다 — 그 두 줄은
        # 이제 이 통이 전담하므로 여기서 끊기면 아무 데도 안 나간다(2026-08-20).
        return "\n".join([_head] + _extra + ([AI_SIGNOFF] if _extra else []))
    if not selected:
        # 대상은 있으나 전건이 오늘 이미 안내됨(같은 날 중복 실행 방지) — 다시 보내지 않는다.
        # 단, 그 사이 배정된 건이 있으면 팡파레만 보낸다(축하를 하루 미루지 않는다).
        if _extra:
            return "\n".join(([cheer] if cheer else []) + _extra + [AI_SIGNOFF])
        return cheer

    oldest = eligible[0]["days"]  # collect_unassigned() 에서 이미 -days 정렬됨
    # 팡파레가 붙는 날은 줄 수 상한(GM "10줄 안쪽")을 지키려고 목록을 그만큼 줄인다.
    show_n = 0 if MSG_DISPLAY_N <= 0 else max(1, MSG_DISPLAY_N - (2 if cheer else 0))
    _ordered = sorted(selected, key=lambda x: -x["days"])
    shown = _ordered if show_n <= 0 else _ordered[:show_n]
    rest_n = len(eligible) - len(shown)

    lines = []
    if cheer:
        lines += [cheer, ""]      # 축하가 먼저, 부탁이 그 다음
    lines.append(f"🙋 담당 배정 필요 · {len(eligible)}건 (가장 오래된 건 {oldest}일째)")
    lines.append("팀장님들, 아래 문의부터 담당 배정 부탁드립니다 🙏")
    for it in shown:
        sport = _sport_short(it["sport"])
        lines.append(f"· {it['date']} · {it['name']} · {sport} · {it['days']}일째")
    if rest_n > 0:
        lines.append(f"… 외 {rest_n}건 (총 {len(eligible)}건)")
    lines.append(f"👉 배정하기: {ASSIGN_URL_LESSON} (입장코드 {ENTRY_CODE})")
    lines += _extra_sections(today_new, uncontacted, loss_gaps)
    lines.append(AI_SIGNOFF)
    return "\n".join(lines)


def collect_loss_reason_gaps(limit_days: int = 45) -> list[tuple[str, str]]:
    """LOSS 처리는 됐는데 '미등록사유' 칸이 빈 회원 — 최근 limit_days 이내 LOSS 건만.

    ★2026-08-20 시포(GM 지시 "실무진 말을 믿고 작업해줘"). 임정은M 이 사유를 적었는데
    사라진다고 세 번 신고했고(FB260820-101541·101712·110540), 실측하니 회원변경이력에
    저장 시도 자체가 안 남아 있었다 — 화면에서 서버로 요청이 나가지 못한 것이다.
    화면 '오늘 할 일'에도 같은 목록이 있지만 그건 화면을 열어야 보인다. 저장이 조용히
    유실돼도 다음 날 사람 눈에 닿게, **이미 매일 나가는 이 통에 한 줄로만** 얹는다
    (새 알림·새 예약작업을 만들지 않는다 — 약속 L21).
    """
    from datetime import date as _date
    rows = R._fetch_list("member_active_list", scope="ended", nocache="1")
    cut = (datetime.now() - timedelta(days=limit_days)).strftime("%Y-%m-%d")
    out = []
    for r in rows:
        if str(r.get("미등록사유", "") or "").strip():
            continue
        loss_at = str(r.get("LOSS\n일자", "") or r.get("종료\n일자", "") or "")[:10]
        if not loss_at or loss_at < cut:
            continue
        nm = str(r.get("회원명", "") or "-").strip() or "-"
        out.append((nm, loss_at))
    out.sort(key=lambda x: x[1])
    return out


def _extra_sections(today_new: list, uncontacted: list, loss_gaps: list | None = None) -> list[str]:
    """하루 일과 정리에 있던 촉구 두 줄을 이 통으로 옮겨 담는다(2026-08-20 GM 신고 — 중복).

    옛 자리 = report_stream_1_impl.build_digest 의 「🆕 담당배정 필요」·「📌 연락 아직 안 된
    문의(멤버십)」. 같은 방에 두 통이 연달아 나가면서 같은 제목의 촉구가 두 번 읽혔다.
    데이터·판정은 그대로 stream1 함수를 재사용한다(새 판정 만들지 않는다 — 약속 L01·L21).
    """
    out: list[str] = []
    if today_new:
        names = " · ".join(f"{nm}({tp})" for nm, tp in today_new)
        out.append(f"🆕 오늘 들어온 문의 중 담당 미정 {len(today_new)}건 — {names}")
    if uncontacted:
        head = ", ".join(f"{nm}({d}일째)" for nm, d in uncontacted[:5])
        tail = f" 외 {len(uncontacted) - 5}건" if len(uncontacted) > 5 else ""
        out.append(f"📌 아직 연락 못 드린 멤버십 문의 {len(uncontacted)}건 — {head}{tail}")
    if loss_gaps:
        # 최근 LOSS 부터 — 방금 처리하신 건이 맨 앞에 보여야 "내가 적은 게 안 들어갔구나"가 바로 읽힌다.
        recent = sorted(loss_gaps, key=lambda x: x[1], reverse=True)
        names = ", ".join(f"{nm}({d[5:]})" for nm, d in recent[:5])
        tail2 = f" 외 {len(recent) - 5}명" if len(recent) > 5 else ""
        out.append(f"🚪 LOSS 미등록사유 빈칸 {len(loss_gaps)}명 — {names}{tail2}")
        out.append("   👉 적으셨는데 비어 있으면 저장이 안 된 것입니다. 사유 한 낱말만 주시면 저희가 넣겠습니다")
    return out


def collect_today_unassigned(today: str, mem_raw: list, adult_raw: list, youth_raw: list) -> list:
    """당일 접수분 중 담당이 아직 안 정해진 건 — stream1 이 쓰던 판정 그대로."""
    groups = {"membership": R._today_rows(mem_raw, today),
              "adult": R._today_rows(adult_raw, today),
              "youth": R._today_rows(youth_raw, today)}
    out = []
    for kind, rows in groups.items():
        is_lesson = kind != "membership"
        for r in rows:
            if R._has_progress(r):
                continue
            if R._is_unassigned_active(r, is_lesson):
                nm = str(r.get("name", "") or "-").strip() or "-"
                out.append((nm, R._type_label(kind)))
    return out


def send(text: str, chat_id: int) -> dict:
    """실제 발송. 토큰 SSOT = telegram_bot/.env (CLAUDE.md §3).

    ★2026-07-24 시토 수리: 여기는 그동안 한 번도 성공한 적이 없었다(항상 ok=False).
      telegram_notifier 는 **import 시점에** load_dotenv() 를 인자 없이 부른다 → 현재
      작업폴더에 .env 가 있어야만 토큰이 잡힌다. 이 스크립트는 저장소 루트에서 도는데
      루트엔 .env 가 없어서 토큰이 빈 문자열이었고, send() 가 조용히 {} 를 반환했다.
      dry-run 만 돌려봤기 때문에 '보낼 준비 됐다'로 오인돼 있었다.
      고침 = ①정본 .env 를 경로로 명시해 먼저 읽고 ②모듈이 이미 빈 값을 잡았을 수도 있으니
      토큰·주소를 인스턴스에 직접 박는다(import 순서에 좌우되지 않게).
    """
    repo = os.path.dirname(_HERE)
    from dotenv import load_dotenv  # noqa: E402

    load_dotenv(os.path.join(repo, "telegram_bot", ".env"))
    sys.path.insert(0, os.path.join(repo, "wellperion-agents"))
    from telegram_notifier import TelegramNotifier  # noqa: E402

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "chat_id": chat_id, "resp": {},
                "error": "TELEGRAM_BOT_TOKEN 없음 — telegram_bot/.env 확인"}

    notifier = TelegramNotifier()
    notifier.token = token
    notifier.base_url = f"https://api.telegram.org/bot{token}"
    # TelegramNotifier.send() 는 생성 시 잡힌 self.chat_id 로만 보낸다(방 인자 없음).
    # 방을 바꿔 보내려면 이 속성을 갈아끼우는 게 유일한 경로다.
    notifier.chat_id = str(chat_id)
    resp = notifier.send(text)
    return {"ok": bool(resp.get("ok")), "chat_id": chat_id, "resp": resp}


def _selftest_sla() -> None:
    """24시간 SLA 위반 판정 자가검사(assert 기반, 실제 GAS 호출·발송 0건 — R._fetch_list
    를 가짜 행으로 바꿔치기). 확인: ①24시간 미만은 안 걸림 ②7월 접수분은 대상 아님
    ③담당있음·컨택없음이 담당없음과 구분됨 ④등록완료/LOSS 는 대상에서 빠짐
    ⑤위반 0건이면 빈 문자열(발송 안 함) ⑥본문 10줄 이내."""
    now = datetime(2026, 8, 5, 12, 0, 0)  # 기준 "지금"

    def _row(name, ts, owner="", contacts=None, status=""):
        return {"name": name, "timestamp": ts, "owner": owner,
                "contacts": contacts or [], "status": status, "sport": "성인 수영"}

    rows = [
        _row("갓접수", "2026-08-05 01:00:00"),                       # 11h — 24h 미만, 대상 아님
        _row("칠월접수", "2026-07-30 08:00:00"),                     # 7월 — 대상 아님(날짜 컷)
        _row("담당없음A", "2026-08-01 08:00:00"),                    # 오너 없음 — 위반(담당없음)
        _row("담당있음미컨택", "2026-08-02 08:00:00", owner="김상식"),  # 컨택 0 — 위반(담당있음·컨택없음)
        _row("정상처리", "2026-08-02 08:00:00", owner="김상식",
             contacts=[{"note": "1차 상담 완료"}]),                  # 배정+컨택 — 정상
        _row("등록완료건", "2026-08-01 08:00:00", status="등록완료"),  # 이미 해결 — 대상 아님
        _row("이탈건", "2026-08-01 08:00:00", status="LOSS"),         # 이미 해결 — 대상 아님
        _row("자동접수값", "2026-08-01 08:00:00", owner="웹 자동접수"),  # 자동값=미배정 취급 — 위반
    ]

    orig_fetch = R._fetch_list
    R._fetch_list = lambda action, **params: (rows if params.get("type") == "성인강습" else [])
    try:
        v = collect_sla_violations(now=now)
        names = {it["name"] for it in v}
        assert "갓접수" not in names, "24시간 미만인데 위반으로 잡힘"
        assert "칠월접수" not in names, "7월 접수분인데 위반으로 잡힘(날짜 컷 실패)"
        assert "정상처리" not in names, "배정+컨택 다 됐는데 위반으로 잡힘"
        assert "등록완료건" not in names, "이미 등록완료인데 위반으로 잡힘"
        assert "이탈건" not in names, "이미 LOSS 종결인데 위반으로 잡힘"
        assert "담당없음A" in names and "자동접수값" in names, "담당 없는 건이 안 잡힘"
        assert "담당있음미컨택" in names, "담당 있고 컨택만 없는 건이 안 잡힘"

        by_name = {it["name"]: it for it in v}
        assert by_name["담당없음A"]["reason"] == "담당 미정"
        assert by_name["자동접수값"]["reason"] == "담당 미정"
        assert by_name["담당있음미컨택"]["reason"] == "배정완료·기록없음", \
            "배정완료·연락기록없음이 담당 미정과 구분 안 됨"
        print(f"  [판정] 위반 {len(v)}건 — 24h미만 제외/7월 제외/정상 제외/등록·LOSS 제외/"
              "담당없음↔담당있음·컨택없음 구분 — 전부 통과")

        empty_text = build_sla_alert_text([])
        assert empty_text == "", "위반 0건인데 본문이 생성됨(발송하면 안 됨)"
        print("  [빈 목록] 본문 \"\" — 발송 안 함 — 통과")

        text = build_sla_alert_text(v)
        assert "★부서장" not in text  # 방 이름은 본문이 아니라 --only-room 인자로 감(중복 노출 방지)
        assert AI_SIGNOFF in text, "AI 주체 서명 누락(기존 배정 독려와 동일 서명 AI_SIGNOFF 재사용)"
        line_n = len(text.splitlines())
        assert line_n <= 10, f"본문이 10줄을 넘음({line_n}줄)"
        print(f"  [본문] {line_n}줄(10줄 이내) · 서명 포함 — 통과")
        print("SELFTEST OK: 24시간 SLA 위반 판정 정상(실발송 0건)")
    finally:
        R._fetch_list = orig_fetch


def _selftest_noresponse() -> None:
    """컨택 후 60일 무응답 판정·회전 자가검사(assert 기반, 실제 GAS 호출·발송 0건).
    확인: ①60일 미만(45~59 예고구간)은 본선 제외 ②등록완료/LOSS 제외 ③미컨택 제외
    (배정독려 몫) ④최근 재컨택은 무응답 아님 ⑤강습+회원 통합 집계 ⑥45일 예고와 60일
    본선이 겹치지 않음 ⑦0건이면 빈 문자열 ⑧본문 10줄 이내 ⑨회전이 다음 회차에 다른
    건을 낸다(2회 연속 비교)."""
    today_dt = datetime(2026, 8, 5)
    today = today_dt.strftime("%Y-%m-%d")

    def _d(n: int) -> str:
        return (today_dt - timedelta(days=n)).strftime("%Y-%m-%d")

    def _row(name, contact_days_ago, ts_days_ago=None, owner="", status=""):
        ts = _d(ts_days_ago if ts_days_ago is not None else contact_days_ago)
        contacts = [{"date": _d(contact_days_ago), "note": "1차 상담"}] if contact_days_ago is not None else []
        return {"name": name, "timestamp": ts, "owner": owner, "contacts": contacts,
                "status": status, "sport": "성인 수영"}

    lesson_rows = [
        _row("59일차", 59),                            # 예고 구간(45~59) — 본선 아님
        _row("60일차", 60),                             # 본선(60+)
        _row("미컨택오래됨", None, ts_days_ago=100),      # 컨택 0 — 대상 아님(배정독려 몫)
        _row("등록완료오래됨", 90, status="등록완료"),     # 등록완료 — 대상 아님
        _row("이탈오래됨", 90, status="LOSS"),            # LOSS — 대상 아님
        _row("최근재컨택", 5, ts_days_ago=200),           # 최근활동=5일 전 — 대상 아님(살아있음)
    ]
    member_rows = [_row("회원65일차", 65)]

    orig_fetch = R._fetch_list

    def _fake(action, **params):
        if action == "lesson_inquiry_list" and params.get("type") == "성인강습":
            return lesson_rows
        if action == "member_inquiry_list":
            return member_rows
        return []
    R._fetch_list = _fake
    try:
        items = collect_noresponse(today)
        due, warn = split_noresponse(items)
        due_names = {it["name"] for it in due}
        warn_names = {it["name"] for it in warn}

        assert "60일차" in due_names, "60일 경과건이 본선에 안 잡힘"
        assert "회원65일차" in due_names, "회원(멤버십) 도메인이 통합 집계에서 빠짐"
        assert "59일차" not in due_names and "59일차" in warn_names, "60일 미만이 본선에 잘못 잡힘"
        assert not (due_names & warn_names), "45일 예고가 60일 본선과 겹침"
        assert not ({"미컨택오래됨"} & (due_names | warn_names)), "미컨택 건이 무응답 경보에 섞임(배정독려 몫)"
        assert "등록완료오래됨" not in due_names, "등록완료건이 무응답 경보에 섞임"
        assert "이탈오래됨" not in due_names, "LOSS건이 무응답 경보에 섞임"
        assert not ({"최근재컨택"} & (due_names | warn_names)), "최근 재컨택건이 무응답으로 오판정됨"
        print(f"  [판정] 본선 {len(due)}건 · 예고 {len(warn)}건 — 60일 미만 제외/등록·LOSS 제외/"
              "미컨택 제외/45일 예고-60일 본선 비중복/회원+강습 통합 — 전부 통과")

        empty_text = build_noresponse_alert_text([], 0, [])
        assert empty_text == "", "본선 0건인데 본문이 생성됨(발송하면 안 됨)"
        print("  [빈 목록] 본문 \"\" — 발송 안 함 — 통과")

        sel1 = select_noresponse_rotation(due, {})
        text = build_noresponse_alert_text(due, len(warn), sel1)
        assert AI_SIGNOFF in text, "AI 주체 서명 누락"
        line_n = len(text.splitlines())
        assert line_n <= 10, f"본문이 10줄을 넘음({line_n}줄)"
        print(f"  [본문] {line_n}줄(10줄 이내) · 서명 포함 — 통과")

        # 회전: 실데이터 2건뿐이라 회전 확인용으로 가짜 후보를 늘려 5건 초과 상태를 만든다.
        many_due = due + [dict(due[0], name=f"가짜{i}", key=f"fakekey{i}", days=90 - i) for i in range(8)]
        sel_day1 = select_noresponse_rotation(many_due, {})
        notified60 = {it["key"]: today for it in sel_day1}
        sel_day2 = select_noresponse_rotation(many_due, notified60)
        keys1 = {it["key"] for it in sel_day1}
        keys2 = {it["key"] for it in sel_day2}
        assert keys1 != keys2, "회전이 다음 회차에 다른 건을 내지 못함(같은 5건 반복)"
        print(f"  [회전] 1일차 {sorted(keys1)} → 2일차 {sorted(keys2)} — 다른 건 선발 확인 통과")
        print("SELFTEST OK: 60일 무응답 판정·회전 정상(실발송 0건)")
    finally:
        R._fetch_list = orig_fetch


def _selftest_cheer() -> None:
    """팡파레 판정 자가검사(가짜 데이터·발신 0건). 확인: ①배정된 건만 축하 ②목록에서
    빠졌어도 담당 없으면(LOSS·등록 등) 축하 안 함 ③미배정 0건이면 마무리 줄 추가
    ④배정 0건이고 미배정 남았으면 침묵 ⑤팡파레 붙은 본문도 10줄 이내."""
    today = "2026-08-07"
    rows = [
        {"name": "배정된사람", "owner": "박민서", "sport": "성인 수영", "timestamp": "2026-07-01 10:00:00"},
        {"name": "이탈된사람", "owner": "", "sport": "뮤지컬", "timestamp": "2026-07-01 10:00:00"},
    ]
    keys = {r["name"]: _lead_key(r) for r in rows}
    _ROWS_CACHE.clear()
    _ROWS_CACHE.update({"date": today, "rows": rows})
    try:
        prev = {keys["배정된사람"]: "배정된사람", keys["이탈된사람"]: "이탈된사람"}
        done = newly_assigned(prev, today)
        names = {d["name"] for d in done}
        assert names == {"배정된사람"}, f"배정된 건만 축하해야 하는데 {names}"
        assert done[0]["owner"] == "박민서"
        print(f"  [판정] 축하 대상 {len(done)}건 — 담당 붙은 건만, 담당 없는 건 제외 — 통과")

        assert _render_cheer([], 5) == "", "배정 0건인데 팡파레가 울림"
        assert "🏁" in _render_cheer(done, 0), "미배정 0건인데 마무리 줄이 없음"
        assert "🏁" not in _render_cheer(done, 3), "미배정이 남았는데 마무리 줄이 붙음"
        print("  [문구] 배정0=침묵 · 미배정0=마무리줄 · 남음=축하만 — 통과")

        eligible = [{"sport": "성인 수영", "name": f"대기{i}", "date": "2026-07-20",
                     "days": 18 - i, "contacted": False, "key": f"k{i}", "type": "성인강습"}
                    for i in range(9)]
        text = _render_message(eligible[:5], eligible, [], _render_cheer(done, len(eligible)))
        line_n = len(text.splitlines())
        assert line_n <= 10, f"팡파레 포함 본문이 10줄을 넘음({line_n}줄)"
        assert "🎉" in text and "🙋" in text, "축하와 부탁이 같은 메시지에 함께 있어야 한다"
        print(f"  [본문] {line_n}줄(10줄 이내) · 축하+부탁 동시 — 통과")
        print("SELFTEST OK: 팡파레 판정 정상(실발송 0건)")
    finally:
        _ROWS_CACHE.clear()


def main() -> int:
    p = argparse.ArgumentParser(description="문의 담당자 미배정 배정 독려 안내")
    p.add_argument("--send", action="store_true",
                   help="실제 발송(기본은 출력만 — 실무진 발송은 되돌릴 수 없다)")
    p.add_argument("--to", choices=("gm", "staff"), default="gm",
                   help="gm=GM 개인 봇방(기본) / staff=문의알림방 실무진")
    p.add_argument("--today", default=None, help="기준일(YYYY-MM-DD, 기본 오늘)")
    p.add_argument("--list-dormant", action="store_true",
                   help="휴면(연락이력 0건·100일 초과) 전체 목록 출력 — 월 1회 검토용. 발송 없음.")
    p.add_argument("--sla-check", action="store_true",
                   help="24시간 SLA 위반(카카오 ★부서장 방 대상) 본문만 출력 — 발송 없음(검증용).")
    p.add_argument("--noresp-check", action="store_true",
                   help="컨택 후 60일 무응답(카카오 ★부서장 방 대상) 본문만 출력 — 발송 없음(검증용).")
    p.add_argument("--selftest", action="store_true",
                   help="SLA·60일 무응답 판정 자가검사만 실행(가짜 데이터·실제 발신 0건).")
    p.add_argument("--auto-assign", action="store_true",
                   help=f"{AUTO_ASSIGN_MIN_DAYS}일 넘게 미배정인 강습 문의를 종목 팀장 이름으로 배정(기본 미리보기).")
    p.add_argument("--apply", action="store_true", help="--auto-assign/--fix-owners 를 실제로 시트에 쓴다.")
    p.add_argument("--assign-member", action="store_true",
                   help="담당 빈 멤버십 문의를 임정은M 앞으로 채운다(기본 미리보기 · --apply 로 실제 쓰기).")
    p.add_argument("--fix-owners", action="store_true",
                   help="담당이 그 종목 팀 사람이 아닌 문의를 팀장으로 통일(기본 미리보기).")
    args = p.parse_args()

    if args.assign_member:
        res = assign_member_owners(apply=args.apply)
        if not args.apply:
            print(f"[멤버십 배정] 대상 {len(res)}건 (미리보기 · --apply 로 실제 쓰기)")
            for it in res[:20]:
                print(f"  · {it['name']} (행 {it['rowIndex']})")
            return 0
        bad = [x for x in res if not x.get("ok")]
        print(f"[멤버십 배정] 성공 {len(res) - len(bad)}건 · 실패 {len(bad)}건")
        for x in bad:
            print(f"  [실패] {x['name']} — {x.get('error', '')}")
        return 0 if not bad else 1

    if args.fix_owners:
        today = args.today or datetime.now().strftime("%Y-%m-%d")
        fix, held = collect_owner_fixes(today)
        by = defaultdict(list)
        for it in fix:
            by[it["owner"]].append(it)
        print(f"[담당 통일] 고칠 것 {len(fix)}건 · 보류 {len(held)}건 (등록완료·LOSS 건은 제외)")
        for lead in sorted(by, key=lambda k: -len(by[k])):
            froms = defaultdict(int)
            for it in by[lead]:
                froms[it["before"]] += 1
            detail = " · ".join(f"{k} {v}" for k, v in sorted(froms.items(), key=lambda x: -x[1]))
            print(f"  · {lead} ← {len(by[lead])}건 ({detail})")
        for it in held:
            print(f"  [보류] {it['date']} · {it['name']} · {it['sport'][:24]} — {it['reason']}")
        if not args.apply:
            print("(미리보기 — 실제로 쓰려면 --apply)")
            return 0
        res = apply_auto_assign(fix)
        bad = [r for r in res if not r["ok"]]
        print(f"[쓰기 완료] 성공 {len(res) - len(bad)}건 · 실패 {len(bad)}건")
        for r in bad:
            print(f"  [실패] {r['name']} · {r['sport'][:24]} — {r['error']}")
        return 0 if not bad else 1

    if args.auto_assign:
        today = args.today or datetime.now().strftime("%Y-%m-%d")
        ready, held = collect_auto_assign(today)
        print(f"[자동 배정] 대상 {len(ready)}건 · 보류 {len(held)}건 "
              f"({AUTO_ASSIGN_MIN_DAYS}일 이상 미배정)")
        by_lead = defaultdict(int)
        for it in ready:
            by_lead[it["owner"]] += 1
        for lead, n in sorted(by_lead.items(), key=lambda x: -x[1]):
            print(f"  · {lead} ← {n}건")
        for it in held:
            print(f"  [보류] {it['date']} · {it['name']} · {_sport_short(it['sport'])} "
                  f"· {it['days']}일째 — {it['reason']}")
        if not args.apply:
            print("(미리보기 — 실제로 쓰려면 --apply)")
            return 0
        res = apply_auto_assign(ready)
        ok = [r for r in res if r["ok"]]
        bad = [r for r in res if not r["ok"]]
        print(f"[쓰기 완료] 성공 {len(ok)}건 · 실패 {len(bad)}건")
        for r in bad:
            print(f"  [실패] {r['name']} · {r['sport']} — {r['error']}")
        return 0 if not bad else 1

    if args.selftest:
        _selftest_sla()
        _selftest_noresponse()
        _selftest_cheer()
        return 0

    if args.sla_check:
        violations = collect_sla_violations()
        text = build_sla_alert_text(violations)
        print(f"[SLA 위반] {len(violations)}건 (8/1 이후 접수 · 24시간 경과 · 담당없음/컨택없음) "
              f"— 목적지=카카오 {KAKAO_DEPTHEAD_ROOM} 방")
        print("-" * 56)
        print(text or "(위반 0건 — 발송 안 함)")
        print("-" * 56)
        return 0

    if args.noresp_check:
        today = args.today or datetime.now().strftime("%Y-%m-%d")
        items = collect_noresponse(today)
        due, warn = split_noresponse(items)
        notified60 = _load_notified60()
        selected = select_noresponse_rotation(due, notified60)
        text = build_noresponse_alert_text(due, len(warn), selected)
        print(f"[60일 무응답] 본선 {len(due)}건 · 예고(45~59일) {len(warn)}건 "
              f"— 목적지=카카오 {KAKAO_DEPTHEAD_ROOM} 방")
        print("-" * 56)
        print(text or "(본선 0건 — 발송 안 함)")
        print("-" * 56)
        return 0

    payload = build_payload(args.today)
    chat_id = GM_CHAT_ID if args.to == "gm" else STAFF_CHAT_ID

    if args.list_dormant:
        dormant = payload["dormant"]
        print(f"[휴면 목록] {len(dormant)}건 — 연락이력 0건 · {DORMANT_OVER_DAYS}일 초과. "
              "삭제·폐기 아님(월 1회 검토용).")
        for it in sorted(dormant, key=lambda x: -x["days"]):
            print(f"  · {it['name']} · {_sport_short(it['sport'])} · {it['days']}일째 · {it['type']}")
        return 0

    text = payload["text"]
    if not text:
        print(f"[휴식] 미배정 {len(payload['eligible'])}건 전부 {RENOTIFY_GAP_DAYS}일 가드 안 "
              "— 오늘은 보낼 것이 없습니다(도배 방지).")
        return 0

    if not args.send:
        print(f"[dry-run] 발송 안 함 · 대상={args.to}({chat_id}) · "
              f"오늘 {len(payload['selected'])}건 / 미배정 {len(payload['eligible'])}건 / "
              f"휴면 제외 {len(payload['dormant'])}건")
        print("-" * 56)
        print(text)
        print("-" * 56)
        return 0

    result = send(text, chat_id)
    print(f"[발송] 대상={args.to}({chat_id}) ok={result['ok']}")
    if result["ok"]:
        # 발송이 실제로 나간 뒤에만 재알림 가드 시계를 돌린다(배10014 상설 갱신 방식).
        rec = _record_sent(payload["selected"], payload["notified"], payload["today"],
                           len(payload["eligible"]), len(payload["dormant"]))
        print(f"[가드 기록] heartbeats/{HEARTBEAT_ID}.json ok={rec.get('ok')}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
