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
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime
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
AI_SIGNOFF = "웰페리온 회원 시포 드림"

# 하루에 부탁드리는 건수 상한 — 소음은 상한(30일)이 아니라 건수로 잡는다(웰리 07-25).
DAILY_TOP_N = 10              # 회전 선발 상한(가드 대상) — 기존 값 유지(웰리 07-25)
MSG_DISPLAY_N = 5             # 메시지 본문에 실제로 줄로 싣는 건수(GM 08-05 "10줄 안쪽")
STALE_MIN_DAYS = 3           # 갓 들어온 문의는 정상 응대 흐름에 맡긴다
DORMANT_OVER_DAYS = 100      # 이 일수 "초과" + 연락이력 0건 = 휴면
RENOTIFY_GAP_DAYS = 1        # 같은 건 재알림 최소 간격 — 배정될 때까지 매일(GM 08-05). 같은 날 중복실행만 막는다.
NOTIFIED_KEEP_DAYS = 30      # 가드 맵에서 이보다 오래된 기록은 청소(무한 비대 방지)
HEARTBEAT_ID = "cpo-unassigned-nudge"  # 배10014 방식 — 상설 파일 1개 갱신

# ── 24시간 SLA 위반 → 카카오 ★부서장 방 (GM 2026-08-05 지시) ────────────────────
SLA_SINCE_DATE = "2026-08-01"  # 대상 = 이 날짜(포함) 이후 접수분만
SLA_HOURS = 24                 # 문턱 — 배정·컨택 둘 중 하나라도 없으면 위반
SLA_MSG_DISPLAY_N = 5          # 본문에 줄로 싣는 건수(GM "10줄 안쪽")
KAKAO_DEPTHEAD_ROOM = "★부서장"  # scripts/kakao_rooms.json 정본과 동일 값(창-제목 대조용)


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


def collect_unassigned(today: str) -> list[dict]:
    """담당자 미배정 + 활성 강습 문의 전건(3일 이상 경과 · 상한 없음)."""
    sources = {
        "성인강습": R._fetch_list("lesson_inquiry_list", type="성인강습"),
        "유소년강습": R._fetch_list("lesson_inquiry_list", type="유소년강습"),
    }
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
                "key": _lead_key(r),
            })
    out.sort(key=lambda x: -x["days"])
    return out


def split_dormant(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(배정 푸시 대상, 휴면) 분리.

    휴면 = 연락이력 0건 AND 경과 100일 초과 → 푸시에서 제외만 한다(삭제·폐기 금지,
    월 1회 --list-dormant 로 검토). 연락이력 있는 100일+ 건은 정상 대상 유지.
    """
    eligible, dormant = [], []
    for it in items:
        if (not it["contacted"]) and it["days"] > DORMANT_OVER_DAYS:
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

def _load_notified(root: Path | None = None) -> dict[str, str]:
    from module_heartbeat import PROJECT_ROOT, last_heartbeat
    rec = last_heartbeat(HEARTBEAT_ID, root=root or PROJECT_ROOT)
    m = (rec or {}).get("notified")
    return dict(m) if isinstance(m, dict) else {}


def _record_sent(selected: list[dict], notified: dict[str, str], today: str,
                 eligible_n: int, dormant_n: int, root: Path | None = None) -> dict:
    """발송 '성공' 직후에만 호출 — dry-run 은 가드 상태를 소모하지 않는다."""
    from module_heartbeat import PROJECT_ROOT, record_heartbeat
    merged = dict(notified)
    for it in selected:
        merged[it["key"]] = today
    merged = {k: v for k, v in merged.items()
              if 0 <= R._days_since(v, today) <= NOTIFIED_KEEP_DAYS}
    return record_heartbeat(
        HEARTBEAT_ID,
        detail=f"배정 안내 {len(selected)}건 발송(대상 {eligible_n}건 · 휴면 제외 {dormant_n}건)",
        extra={"notified": merged},
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


def collect_sla_violations(now: datetime | None = None) -> list[dict]:
    """8/1(SLA_SINCE_DATE) 이후 접수 강습 문의 중 24시간(SLA_HOURS) 경과 +
    (담당자 없음 또는 컨택기록 0건) 위반건. 이미 등록완료·이탈종결(LOSS)로 끝난
    건은 빼고(R._is_registered/_is_loss 재사용 — 판정 기준 두 벌 금지), 경과시간
    내림차순(오래된 위반 먼저)으로 반환한다."""
    now = now or datetime.now()
    sources = {
        "성인강습": R._fetch_list("lesson_inquiry_list", type="성인강습"),
        "유소년강습": R._fetch_list("lesson_inquiry_list", type="유소년강습"),
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
                "sport": str(r.get("sport", "") or "-").strip() or "-",
                "name": str(r.get("name", "") or "-").strip() or "-",
                "date": ts[:16] or "-",
                "hours": hours,
                "assigned": assigned,
                "contacted": contacted,
                "reason": "담당없음" if not assigned else "담당있음·컨택없음",
            })
    out.sort(key=lambda x: -x["hours"])
    return out


def build_sla_alert_text(violations: list[dict]) -> str:
    """카카오 ★부서장 방용 평문(GM 2026-08-05) — 위반 0건이면 빈 문자열(발송 안 함).
    10줄 안쪽·한 줄에 한 건(접수일시·이름·종목·경과시간·상태)·부탁 조·AI 주체 명시."""
    if not violations:
        return ""
    shown = violations[:SLA_MSG_DISPLAY_N]  # 이미 경과시간 내림차순(오래된 순)
    rest_n = len(violations) - len(shown)
    lines = [f"⏰ 24시간 미배정·미컨택 · {len(violations)}건 (8/1 이후 접수분)"]
    lines.append("부서장님, 아래 문의 확인 부탁드립니다 🙏")
    for it in shown:
        lines.append(f"· {it['date']} · {it['name']} · {_sport_short(it['sport'])} · "
                     f"{_fmt_elapsed(it['hours'])}째 · {it['reason']}")
    if rest_n > 0:
        lines.append(f"… 외 {rest_n}건 (총 {len(violations)}건)")
    lines.append(f"👉 처리하기: {ASSIGN_URL_LESSON} (입장코드 {ENTRY_CODE})")
    lines.append(AI_SIGNOFF)
    return "\n".join(lines)


def build_payload(today: str | None = None, notified: dict[str, str] | None = None) -> dict:
    """오늘 회차 산출물 한 벌: 본문 + 선발 10건 + 휴면 목록 + 집계."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    notified = _load_notified() if notified is None else notified
    items = collect_unassigned(today)
    eligible, dormant = split_dormant(items)
    selected = select_daily(eligible, notified, today)
    return {
        "today": today,
        "text": _render_message(selected, eligible, dormant),
        "selected": selected,
        "eligible": eligible,
        "dormant": dormant,
        "notified": notified,
    }


def _render_message(selected: list[dict], eligible: list[dict], dormant: list[dict]) -> str:
    """그것만 담은 독립 메시지(GM 2026-08-05) — 10줄 안쪽·한 줄에 한 건·부탁 조.

    텔레그램 굵게가 잘 안 먹어 줄바꿈·기호로 읽히게 한다. 표시는 선발 top MSG_DISPLAY_N
    건을 "오래된 순"으로 다시 정렬해서 싣는다(select_daily 의 회전 선발 순서는 종목별
    공정 배분용이라 화면 순서와 다르다). 나머지는 "외 N건"+총계로 접는다(도배 방지).
    """
    if not eligible:
        return "✅ 담당자 미배정 문의 0건 — 모두 배정 완료되었습니다. 감사합니다 🙏"
    if not selected:
        # 대상은 있으나 전건이 오늘 이미 안내됨(같은 날 중복 실행 방지) — 다시 보내지 않는다.
        return ""

    oldest = eligible[0]["days"]  # collect_unassigned() 에서 이미 -days 정렬됨
    shown = sorted(selected, key=lambda x: -x["days"])[:MSG_DISPLAY_N]
    rest_n = len(eligible) - len(shown)

    lines = [f"🙋 담당 배정 필요 · {len(eligible)}건 (가장 오래된 건 {oldest}일째)"]
    lines.append("팀장님들, 아래 문의부터 담당 배정 부탁드립니다 🙏")
    for it in shown:
        sport = _sport_short(it["sport"])
        lines.append(f"· {it['date']} · {it['name']} · {sport} · {it['days']}일째")
    if rest_n > 0:
        lines.append(f"… 외 {rest_n}건 (총 {len(eligible)}건)")
    lines.append(f"👉 배정하기: {ASSIGN_URL_LESSON} (입장코드 {ENTRY_CODE})")
    lines.append(AI_SIGNOFF)
    return "\n".join(lines)


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
        assert by_name["담당없음A"]["reason"] == "담당없음"
        assert by_name["자동접수값"]["reason"] == "담당없음"
        assert by_name["담당있음미컨택"]["reason"] == "담당있음·컨택없음", \
            "담당있음·컨택없음이 담당없음과 구분 안 됨"
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
    p.add_argument("--selftest", action="store_true",
                   help="SLA 판정 자가검사만 실행(가짜 데이터·실제 발신 0건).")
    args = p.parse_args()

    if args.selftest:
        _selftest_sla()
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
