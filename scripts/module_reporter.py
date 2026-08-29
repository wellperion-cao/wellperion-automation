# -*- coding: utf-8 -*-
"""
module_reporter.py — 범용 모듈 자동보고 리포터 (공유 SSOT 소비).
─────────────────────────────────────────────────────────────────────────────
정본 등록부 = status/module_registry.json (시우/COO 소유 스키마). 이 리포터는
scripts/module_registry.py:load_registry() 로 등록부를 읽어, 각 모듈의
notify_spec 기준으로 주기·채널을 필터하고, id 규약으로 수집기를 해소해
표준 payload 를 만들어 텔레그램으로 발송한다 → status/module_report_log.jsonl 기록.

플래그:
  --cadence {daily|weekly|monthly}   notify_spec[cadence]==True 인 모듈만
  --dry-run                          발송 0(네트워크 미호출)·payload 프리뷰
  --module <id>                      특정 모듈만

선택 규칙: notify_spec[cadence] is True AND notify_spec.channel == "telegram".
라이브 게이트: notify_spec.bot_id — None 이면 발송 스킵(현재 전부 null=미발효).
  · bot_id int  → 그대로 chat_id
  · bot_id str  → status/telegram_rooms.json 에서 방이름→chat_id 해소
  · bot_id None → 스킵(미발효)
수집기 해소(id 규약): 모듈 id(하이픈) → collectors.<id_underscore>.
  예: cto-automation-health → collectors.cto_automation_health.
  구현 없는 모듈은 '로그+스킵'(오류 아님 · 후속 구현 대기).
멱등: dedup 키 = "{module_id}|{date}|{cadence}". notify_spec 은 슬롯시각 없이
  daily/weekly/monthly 불리언이라 cadence 버킷이 정확한 멱등 단위다.
격리: 한 수집기 예외가 다른 모듈 발송을 막지 않음(실패는 로그만 남기고 넘어감).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from datetime import datetime

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
_SSOT_DIR = os.path.join(_PROJECT_ROOT, "ssot")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from module_registry import load_registry  # noqa: E402
from clevel_colors import color_dot  # noqa: E402 — 부서 색동그라미 정본(단일 딕셔너리)
import weekly_bundle_pending as _bundle  # noqa: E402 — 배10011 알림 묶기 공용 pending

# ── 배10011(2026-07-24, GM 승인) — 자동화현황방(GM 2인 전용, 실측 확인) 직접 발신을
#   다른 메시지로 흡수한다. (cadence, bot_id) → bundle_id 매핑. 직접 sender() 호출 대신
#   weekly_bundle_pending 에 적재만 하고, 실제 발송은 흡수 대상 메시지가 소비(consume)+발송
#   후 mark_bundle_sent() 로 로그를 확정한다.
# ★2026-08-05(시토, GM 지적) — daily 흡수("자동화현황방"→"stream3_daily")를 제거했다.
#   흡수처였던 report_stream_3_mgmt(09:30 하루 일과 정리)는 업무보고방(8254867551) 발신
#   고정인데, 흡수는 자동화현황방(AI진행현황방) 몫인 cto-automation-health 09:10 데일리를
#   그 업무보고방 메시지 안으로 밀어넣고 있었다 — GM 이 실측 지적한 오배달의 원인. weekly
#   흡수(monday_weekly_bundle → ai_learning_proposer)는 AI진행현황방으로 정확히 가므로 그대로 둔다.
ABSORB_BUNDLES = {
    ("weekly", "자동화현황방"): "monday_weekly_bundle",  # 월요일 모듈위클리 → AI자기학습제안에 흡수(AI진행현황방 발신)
}

# ★2026-08-03(시토) — GM_DM 은 (cadence, bot_id) 단위로 묶을 수 없다: 이 방으로 daily 가는
#   모듈이 5개(coo-check-status·coo-work-approval·cmo-content-pipeline·cpo-inquiry-daily-actions·
#   cmo-content-intake)라 위 2튜플 방식을 그대로 쓰면 무관한 2개(멀쩡히 매일 발신 중)까지 같이
#   묶여 침묵한다. 그래서 이 케이스만 (cadence, bot_id, module_id) 3튜플로 모듈 단위 지정한다
#   (조회는 3튜플 우선 → 없으면 기존 2튜플 폴백, 아래 참고).
_COVERED_ELSEWHERE = "__covered__"  # bundle_id 자리에 이 값이면 적재(append)하지 않고 그냥 건너뛴다.
ABSORB_BUNDLES.update({
    # 08:00 아침보고 「🏢 운영 점검」이 coo_report_line.build_coo_daily_lines() 로 이 두 모듈을
    # 이미 싣는다 — 09:10 독립 발신은 GM 방 하루 2회 중복(2026-08-03 시토 실측). 소비자가 없어
    # weekly_bundle_pending 에 적재하면 영영 안 소비돼 새는 곳이 하나 더 생긴다 — 그래서 적재가
    # 아니라 건너뜀(action="covered")으로 처리한다.
    ("daily", "GM_DM", "coo-check-status"): _COVERED_ELSEWHERE,
    ("daily", "GM_DM", "coo-work-approval"): _COVERED_ELSEWHERE,
    # ★2026-08-13(GM 승인) — 같은 두 모듈이 bot_id "업무관리" 로도 매일 나가고 있었다.
    #   위 GM_DM 키만 막아 둔 탓에 09:10 업무보고방 카드 2장은 그대로 살아 있었고, GM 이
    #   "이건들도 난 의미없다고 생각하는데" 라고 짚었다. 실측 대조 —
    #     08:00 "점검 현황: 시설 48% · 지원 0%" ↔ 09:10 "시설 48%(15/31) · 지원 0%(0/108)"
    #     → 같은 숫자에 분모만 더 붙은 두 번째 발신(70분 뒤).
    #     "전사 업무·결재" 는 마감 초과 13건이 46~68일째 같은 이름 그대로라 매일 같은 목록이었다.
    #   잃는 것 0으로 옮겼다: 분모와 마감초과 건수를 08:00 한 줄에 합쳤다(coo_registry
    #   fetch_check_status·fetch_workapproval_status display). 이름 목록은 업무·결재 SSOT 화면에 있다.
    ("daily", "업무관리", "coo-check-status"): _COVERED_ELSEWHERE,
    ("daily", "업무관리", "coo-work-approval"): _COVERED_ELSEWHERE,
})


def _resolve_absorb(cadence, bot_id, mid):
    """(cadence, bot_id, module_id) 3튜플(모듈 단위) 우선 조회 → 없으면 기존 (cadence, bot_id)
    2튜플(방 단위) 폴백. 둘 다 없으면 None(흡수 대상 아님)."""
    return ABSORB_BUNDLES.get((cadence, bot_id, mid), ABSORB_BUNDLES.get((cadence, bot_id)))

_STATUS_DIR = os.path.join(_PROJECT_ROOT, "status")
ROOMS_PATH = os.path.join(_STATUS_DIR, "telegram_rooms.json")
REPORT_LOG_PATH = os.path.join(_STATUS_DIR, "module_report_log.jsonl")

VALID_CADENCES = ("daily", "weekly", "monthly")

# ── 2026-08-15(GM 지시 "5통→1통, 가독성") ────────────────────────────────────
# GM 업무관리방에 09:10 전후 여러 통이 따로 나가 못 읽겠다는 지적. 새 파일·새 예약작업
# 없이 이 스크립트 안에서 (A) 문의·콘텐츠 두 모듈을 GM 업무관리방 한 통으로 묶고
# (B) 지표 라벨을 사람말로 바꾸고 (C) cto-automation-health(AI관리 daily)는 사람말
# 3줄로 줄이고 전부 정상이면 무발신한다. 아래 세 상수·표가 그 정본.
GM_DAILY_BUNDLE_MODULES = ("cpo-inquiry-daily-actions", "cmo-content-pipeline")
GM_DAILY_BUNDLE_KEY = "gm_daily_digest"
GM_DAILY_BUNDLE_ROOM = "업무관리"

# 지표 라벨 사람말 치환표(Part B) — 원문 라벨을 못 바꾸는 이유는 로그·화면(자율현황)이
# 원문 키로 과거값과 대조하기 때문. 발신 텍스트에서만 통과시킨다.
LABEL_HUMANIZE = {
    "미컨택(연락기록 0건)": "아직 연락 못 드린 분",
    "등록됐는데 회원 명단에 없음(하루 지난 것)": "등록은 됐는데 회원 명단에 없는 분",
    "오늘 신규 문의": "새 문의",
    "발행완료": "발행",
}

_JOB_NAME_HUMANIZE = {
    "Wellperion-PC-Boot-Greeting": "PC 부팅 인사",
}


# ── 로더 ─────────────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── 수집기 해소(id 규약) ──────────────────────────────────────────────────────
def collector_module_name(module_id):
    """모듈 id(하이픈) → 수집기 모듈명(언더스코어).
    예: cto-automation-health → collectors.cto_automation_health."""
    return "collectors." + str(module_id or "").replace("-", "_")


# ── 라이브 게이트: notify_spec.bot_id → chat_id ──────────────────────────────
def resolve_chat_id(bot_id, rooms):
    """notify_spec.bot_id → chat_id(int) 또는 None(미발효/미해소).
      int  → 그대로 chat_id
      str  → rooms(방이름→chat_id) 해소(없으면 None)
      None → None(미발효)
    """
    if bot_id is None:
        return None
    if isinstance(bot_id, bool):        # bool 은 int 하위형 — 방어
        return None
    if isinstance(bot_id, int):
        return bot_id
    if isinstance(bot_id, str):
        if not isinstance(rooms, dict):
            return None
        if bot_id in rooms:
            return rooms[bot_id]
        # 옛 이름으로 부르는 곳이 아직 남아 있다(GM 지시 2026-08-12 로 키를 실제 방 이름으로
        # 바꿨다: 개인방→하루 · GM_DM→업무관리 · 자동화현황방→AI관리 …). 매핑 정본은
        # telegram_rooms.json 의 _legacy_aliases — 여기서 복제하지 않는다. 이 한 줄이 없으면
        # 옛 이름으로 부르던 발신이 방을 못 찾아 조용히 안 나간다.
        alias = (rooms.get("_legacy_aliases") or {}).get(bot_id)
        return rooms.get(alias) if alias else None
    return None


# ── 선택 규칙 ────────────────────────────────────────────────────────────────
def selected_for_cadence(mod, cadence):
    """notify_spec[cadence] is True AND channel == 'telegram' → 선택."""
    spec = mod.get("notify_spec")
    if not isinstance(spec, dict):
        return False
    return bool(spec.get(cadence)) and spec.get("channel") == "telegram"


# ── 템플릿 포맷 ──────────────────────────────────────────────────────────────
def format_report(payload, module_name, cadence, owner_role=None):
    """owner_role 있으면 부서 색동그라미(clevel_colors 정본)를 제목 앞에 붙인다."""
    dot_prefix = (color_dot(owner_role) + " ") if owner_role else ""
    lines = [f"📊 {dot_prefix}{payload.get('title', module_name)} ({cadence})"]
    summary = payload.get("summary_line", "")
    if summary:
        lines.append(summary)
    for m in payload.get("metrics", []):
        label = LABEL_HUMANIZE.get(m.get("label"), m.get("label"))
        lines.append(f"  · {label}: {m.get('value')}")
    honesty = payload.get("honesty_tag")
    if honesty:
        lines.append(f"정직: {honesty}")
    link = payload.get("link")
    if link:
        lines.append(link)
    return "\n".join(lines)


# ── 변화 판정(라이브 데이터) ──────────────────────────────────────────────────
def _metrics_of(payload):
    """payload.metrics → {라벨: 값}. 라벨이 없거나 형식이 다르면 빈 dict(판정 포기=평소대로 발송)."""
    out = {}
    for m in (payload or {}).get("metrics") or []:
        if isinstance(m, dict) and m.get("label") is not None:
            out[str(m["label"])] = m.get("value")
    return out


def _last_metrics(log_path, mid):
    """그 모듈의 **가장 최근** 기록된 지표값. 없으면 None(첫 회차 = 무조건 발송)."""
    if not os.path.exists(log_path):
        return None
    found = None
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("module") == mid and isinstance(rec.get("metrics"), dict):
                    found = rec["metrics"]
    except Exception:
        return None
    return found


def _delta_line(prev, cur, max_items=4):
    """'미컨택 46→41(-5)' 처럼 **바뀐 값만** 한 줄로. 첫 회차나 변화 없음이면 빈 문자열."""
    if not prev or not cur:
        return ""
    parts = []
    for label, now_v in cur.items():
        was = prev.get(label)
        if was is None or was == now_v:
            continue
        gap = ""
        if isinstance(was, (int, float)) and isinstance(now_v, (int, float)):
            d = now_v - was
            gap = f"({d:+g})"
        parts.append(f"{label} {was}→{now_v}{gap}")
    if not parts:
        return ""
    shown = parts[:max_items]
    tail = f" 외 {len(parts) - len(shown)}건" if len(parts) > len(shown) else ""
    return "🔄 지난 보고 대비 — " + " · ".join(shown) + tail


# ── 로그 ─────────────────────────────────────────────────────────────────────
def _already_sent(key, log_path):
    """로그에 sent=True 로 남은 동일 dedup 키가 있으면 True(멱등)."""
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("dedup_key") == key and rec.get("sent") is True:
                    return True
    except Exception:
        return False
    return False


def _append_log(log_path, record):
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── 북극성 대비 블록(GM 확정 2026-07-31) ─────────────────────────────────────
def _northstar_prefix(cadence):
    """daily·weekly 리포터 실행에서, 이번 실행 중 실제로 발송되는(=흡수 안 된) 첫
    메시지 맨 위에만 1회 붙일 블록. monthly 는 대상 아님(GM 지정 범위). 실패해도
    빈 문자열(보고를 절대 끊지 않는다). 블록 본문은 northstar_reach.build_northstar_block()
    한 곳에서만 만든다(약속 L01) — ceo_morning_pipeline.py._northstar_head() 와 동일 패턴."""
    if cadence not in ("daily", "weekly"):
        return ""
    try:
        from northstar_reach import build_northstar_block  # noqa: PLC0415
        block = build_northstar_block()
        return f"{block}\n\n" if block else ""
    except Exception:
        return ""


# ── GM 업무관리방 daily 1통 묶음(Part A, 2026-08-15) ──────────────────────────
def _metric_val(payload, label, default=None):
    for m in (payload or {}).get("metrics") or []:
        if m.get("label") == label:
            return m.get("value")
    return default


def _format_gm_daily_bundle(payloads, prev, now):
    """문의(시포)+콘텐츠(시모) → GM 업무관리방 「🧭 아침 보고」 한 통.
    변화 있는 지표만 화살표로, 오늘 뉴스 아닌 줄·섹션은 뺀다(GM 지시 2026-08-15)."""
    weekday = "월화수목금토일"[now.weekday()]
    lines = [f"🧭 아침 보고 · {now.strftime('%m-%d')} ({weekday})"]

    cpo = payloads.get("cpo-inquiry-daily-actions")
    suc_missing, link = 0, None
    if cpo:
        prev_cpo = prev.get("cpo-inquiry-daily-actions") or {}
        today_new = _metric_val(cpo, "오늘 신규 문의", 0)
        todays_res = _metric_val(cpo, "오늘 상담·체험 예약", 0)
        uncontacted = _metric_val(cpo, "미컨택(연락기록 0건)", 0)
        suc_missing = _metric_val(cpo, "등록됐는데 회원 명단에 없음(하루 지난 것)", 0) or 0
        link = cpo.get("link")
        prev_unc = prev_cpo.get("미컨택(연락기록 0건)")
        unc_txt = f"{uncontacted}명"
        if isinstance(prev_unc, (int, float)) and prev_unc != uncontacted:
            unc_txt = f"{prev_unc}명 → {uncontacted}명"
        cpo_lines = [
            f"▪ 오늘 상담·체험 예약 {todays_res}건",
            f"▪ 새 문의 {today_new}건 · 아직 연락 못 드린 분 {unc_txt}",
        ]
        if suc_missing:
            cpo_lines.append(f"▪ 등록은 됐는데 회원 명단에 없는 분 {suc_missing}명")
        lines += ["", "📮 문의 — 시포"] + cpo_lines

    cmo = payloads.get("cmo-content-pipeline")
    if cmo:
        prev_cmo = prev.get("cmo-content-pipeline") or {}
        published = _metric_val(cmo, "발행완료", 0) or 0
        prev_pub = prev_cmo.get("발행완료")
        delta = published - prev_pub if isinstance(prev_pub, (int, float)) else 0
        if delta > 0:  # 발행 소식 없으면 섹션째 뺀다
            lines += ["", "📣 콘텐츠 — 시모", f"▪ 어제 발행 {delta}건 (누적 {published}건)"]

    if suc_missing:
        gm_line = f"▪ 명단 누락 {suc_missing}명"
        if link:
            gm_line += f" → {link}"
        lines += ["", f"👉 GM 확인 1건", gm_line]

    return "\n".join(lines)


# ── AI관리방 자동화 이상 요약(Part C, 2026-08-15) ─────────────────────────────
_FAIL_COUNT_RE = re.compile(r"실패\s*(\d+)\)")
_FAIL_NAMES_RE = re.compile(r"실패:\s*(.+)$")
_SHEET_COUNT_RE = re.compile(r"위반\s*(\d+)건")


def _format_automation_health_ai_room(payload, now):
    """cto-automation-health → AI관리방 사람말 3줄. 전부 정상이면 빈 문자열(무발신).
    주간 회귀·침묵·결정정합('옛것 재생 차단' — 가드 정상작동 기록) 등은 로그에만 남고
    텔레그램에는 안 나간다(GM 지시 2026-08-15 — 이상 있을 때만, 짧게)."""
    ratio = str(_metric_val(payload, "자동화 가동", "") or "")
    ok_s, _, total_s = ratio.partition("/")
    schedule = str(_metric_val(payload, "스케줄·오늘 진행", "") or "")
    sheet = str(_metric_val(payload, "이상 신호·sheet_contract", "") or "")

    lines = []
    if ok_s.isdigit() and total_s.isdigit() and ok_s != total_s:
        lines.append(f"▪ {total_s}개 중 {ok_s}개 정상")

    m = _FAIL_COUNT_RE.search(schedule)
    if m and int(m.group(1)) > 0:
        names_m = _FAIL_NAMES_RE.search(schedule)
        names = [n.strip() for n in (names_m.group(1) if names_m else "").split(",") if n.strip()]
        humans = [_JOB_NAME_HUMANIZE.get(n, n) for n in names]
        lines.append(f"▪ 멈춘 것: {', '.join(humans) or '?'} {m.group(1)}건 → 오늘 중 복구")

    m = _SHEET_COUNT_RE.search(sheet)
    if m and int(m.group(1)) > 0:
        lines.append(f"▪ 회원 시트 규칙 위반 {m.group(1)}건 → 시포가 처리 중")

    # [2026-08-29 GM 승인] 09:12 별도 통이던 「🚨 ERP 이상 신호」 전문을 이 09:10 통
    # 꼬리에 싣는다(같은 방 두 통 → 한 통 · 내용 보존). 전문은 collector 의
    # '이상 신호·*' metric(전체 줄)에 이미 들어 있어 여기서 다시 재지 않는다.
    detail = []
    for mrow in payload.get("metrics", []):
        label = str(mrow.get("label") or "")
        if label.startswith("이상 신호·"):
            detail.append(str(mrow.get("value") or "").replace("\n    ", "\n  "))

    if not lines and not detail:
        return ""
    body = f"🔧 자동화 이상 · {now.strftime('%m-%d')} — 시토\n" + "\n".join(lines or ["▪ 가동 지표 정상"])
    if detail:
        body += "\n\n🚨 ERP 이상 신호(상세)\n" + "\n\n".join(detail)
    return body


# ── 핵심 실행 ────────────────────────────────────────────────────────────────
def run_report(cadence, *, dry_run=False, only_module=None,
               registry_path=None, rooms_path=ROOMS_PATH,
               log_path=REPORT_LOG_PATH, sender=None, now=None, heartbeat=False):
    """
    cadence 버킷에서 notify_spec 로 선택된 모듈을 순회·수집·발송(dry_run 시 발송 0).
    registry_path=None → 공유 SSOT(load_registry 기본경로).
    sender: send(chat_id, text)->bool. None이면 notify.telegram_send.send 지연 로드.
    heartbeat: True 면 collect() 성공 직후 module_heartbeat.record_heartbeat() 호출
      (배1307 5차 — "실제 결과를 낸 시점" 기록). 기본 False — pytest 가 가짜 id("good" 등)로
      실제 registry_path·collector 를 우회할 때 status/heartbeats/ 에 테스트 오염 방지.
      실제 CLI(main())는 항상 True 로 호출한다.
    반환: 실행 결과 dict(테스트·CLI 공용).
    """
    now = now or datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    registry = load_registry(registry_path)
    rooms = load_json(rooms_path, {})
    modules = registry.get("modules", []) if isinstance(registry, dict) else []

    # 발송기 지연 로드(dry-run·테스트에서 미접촉 가능)
    if sender is None and not dry_run:
        from notify.telegram_send import send as sender  # noqa: PLC0415

    results = []
    ns_block = _northstar_prefix(cadence)
    ns_applied = False
    gm_bundle_payloads: dict = {}   # Part A(2026-08-15) — GM 업무관리방 1통 묶음 버퍼
    gm_bundle_prev: dict = {}

    for mod in modules:
        mid = mod.get("id")
        if only_module and mid != only_module:
            continue
        if not selected_for_cadence(mod, cadence):
            continue

        # ── 수집기 해소(id 규약) — 미구현이면 로그+스킵(오류 아님) ──
        cname = collector_module_name(mid)
        try:
            collector_mod = importlib.import_module(cname)
        except ImportError:
            if not dry_run:
                _append_log(log_path, {
                    "ts": now.isoformat(), "module": mid, "cadence": cadence,
                    "sent": False, "reason": "collector_missing",
                    "note": "collector 미구현·후속", "collector": cname,
                })
            results.append({"module": mid, "action": "skip",
                            "reason": "collector_missing", "collector": cname})
            continue

        # ── 수집(개별 try/except 격리) — 실패는 로그만 남기고 다음 모듈로 ──
        try:
            payload = collector_mod.collect(mod)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:120]}"
            if not dry_run:
                _append_log(log_path, {
                    "ts": now.isoformat(), "module": mid, "cadence": cadence,
                    "sent": False, "error": err, "dedup_key": None,
                })
            results.append({"module": mid, "action": "error", "error": err})
            continue

        # 하트비트(배1307 5차) — collect() 성공 = "실제 결과를 낸 시점"(발송 여부와 무관).
        # dry_run 이든 live 든 수집 자체는 동일하게 실제 GAS/시트 조회이므로 여기서 기록.
        if heartbeat:
            try:
                from module_heartbeat import record_heartbeat  # noqa: PLC0415
                record_heartbeat(mid, detail=str(payload.get("summary_line", ""))[:120])
            except Exception:
                pass  # 하트비트 실패가 리포터 본 작업을 막지 않는다(fail-soft)

        key = f"{mid}|{date_str}|{cadence}"

        # Part A(2026-08-15) — GM 업무관리방 두 모듈은 개별발송 대신 버퍼링만 하고 다음
        # 모듈로 넘어간다. 실제 합본 발송은 루프가 끝난 뒤 한 번(_format_gm_daily_bundle).
        if cadence == "daily" and mid in GM_DAILY_BUNDLE_MODULES:
            gm_bundle_payloads[mid] = payload
            gm_bundle_prev[mid] = _last_metrics(log_path, mid)
            if not dry_run:
                _append_log(log_path, {
                    "ts": now.isoformat(), "module": mid, "cadence": cadence,
                    "dedup_key": key, "sent": True, "metrics": _metrics_of(payload),
                    "note": "bundled_into:" + GM_DAILY_BUNDLE_KEY,
                })
            results.append({"module": mid, "action": "bundled",
                            "bundle": GM_DAILY_BUNDLE_KEY, "dedup_key": key})
            continue

        text = format_report(payload, mod.get("feature", mid), cadence,
                              owner_role=mod.get("owner_role"))

        # Part C(2026-08-15) — AI관리방 자동화현황은 사람말 3줄로 덮어쓴다. 전부
        # 정상이면 무발신(로그만 남기고 스킵) — module_report_log.jsonl 에는 그대로
        # metrics 가 남으니 실측 이력은 유지된다.
        if cadence == "daily" and mid == "cto-automation-health":
            ai_text = _format_automation_health_ai_room(payload, now)
            if not ai_text:
                if not dry_run:
                    _append_log(log_path, {
                        "ts": now.isoformat(), "module": mid, "cadence": cadence,
                        "dedup_key": key, "sent": False, "reason": "all_normal",
                    })
                results.append({"module": mid, "action": "skip",
                                "reason": "all_normal", "dedup_key": key})
                continue
            text = ai_text

        bot_id = (mod.get("notify_spec") or {}).get("bot_id")
        chat_id = resolve_chat_id(bot_id, rooms)

        # 북극성 블록 — 흡수 대상(ABSORB_BUNDLES)은 다른 보고 쪽에 이미 블록이 있으므로
        # 여기서 붙이지 않는다(중복 방지). 흡수 안 되는(=이 실행에서 진짜로 나가는) 첫
        # 메시지에만 1회 적용.
        if ns_block and not ns_applied and _resolve_absorb(cadence, bot_id, mid) is None:
            text = f"{ns_block}{text}"
            ns_applied = True

        # dry-run: 프리뷰만(네트워크·로그 부작용 0)
        if dry_run:
            results.append({"module": mid, "action": "dry-run", "dedup_key": key,
                            "bot_id": bot_id, "chat_id": chat_id,
                            "payload": payload, "text": text})
            continue

        # 멱등: 동일 {module|date|cadence} 발송 이력 있으면 스킵
        if _already_sent(key, log_path):
            results.append({"module": mid, "action": "skip",
                            "reason": "dedup", "dedup_key": key})
            continue

        # 라이브 게이트: bot_id None(미발효) 또는 방 미해소 → 발송 스킵
        # ★배10191(2026-07-25) — 이 게이트가 아래 흡수 분기보다 **먼저** 와야 한다.
        #   전에는 흡수 분기가 앞에 있어서, 흡수 대상(자동화현황방)인 모듈은 그 방의 chat_id 가
        #   null 이어도 게이트를 지나치고 pending 번들에 쌓이기만 했다 — 로그에도 results 에도
        #   'room_unresolved' 가 안 남는 **조용한 실패**. 번들도 결국 같은 방으로 나가므로 방을
        #   못 찾으면 흡수해봤자 아무도 못 받는다. 그러니 못 찾으면 흡수 전에 정직하게 스킵한다.
        #   (이 순서를 지키던 테스트 test_bot_id_str_unresolved_room_skips 가 흡수 분기 도입 때
        #    빨간불이 됐고 그대로 방치돼 있었다 — 안전망이 꺼진 줄도 모르고 있었던 것.)
        if chat_id is None:
            reason = "bot_id_null" if bot_id is None else "room_unresolved"
            _append_log(log_path, {
                "ts": now.isoformat(), "module": mid, "cadence": cadence,
                "dedup_key": key, "sent": False, "reason": reason, "bot_id": bot_id,
            })
            results.append({"module": mid, "action": "skip",
                            "reason": reason, "dedup_key": key})
            continue

        # ★배10011 — 흡수 대상(자동화현황방 등)이면 직접 발송 대신 pending에 적재만.
        #   sent=True 기록은 흡수한 메시지가 실제 발송에 성공한 뒤 mark_bundle_sent()가 한다
        #   (여기서 먼저 sent 처리하면 흡수측이 실패해도 "보낸 걸로" 착각 — 순서 중요).
        bundle_id = _resolve_absorb(cadence, bot_id, mid)
        if bundle_id == _COVERED_ELSEWHERE:
            # 다른 보고(예: 08:00 아침보고)가 이미 실었다 — 적재할 소비자가 없으므로 pending에
            # 쌓지 않고 건너뛴다. 조용히 사라지지 않게 흔적만 남긴다.
            results.append({"module": mid, "action": "covered",
                            "by": "morning_brief_0800", "dedup_key": key})
            continue
        if bundle_id:
            _bundle.append(bundle_id, source=key, text=text, now=now)
            results.append({"module": mid, "action": "absorbed",
                            "bundle": bundle_id, "dedup_key": key})
            continue

        # ★변한 게 없으면 보내지 않는다 (GM 지적 2026-08-07 · 시토).
        #   GM: "의미도 없고, 뭔가 그냥 의무적으로 정해진 것만 보내는 느낌인데, 라이브 데이터가
        #   필요한건데." 같은 숫자를 매일 다시 던지면 읽는 사람이 방 자체를 안 보게 된다.
        #   ▸숫자가 하나라도 달라졌을 때만 보내고, 그때는 **무엇이 어떻게 변했는지**를 맨 위에 붙인다.
        #   ▸모듈이 조용해진 것(죽은 것)은 이 침묵과 구분해야 하는데, 그건 module_silence_detector
        #     가 이미 본다 — 여기서 또 감시 장치를 만들지 않는다(약속 L21).
        cur_metrics = _metrics_of(payload)
        prev_metrics = _last_metrics(log_path, mid)
        if cur_metrics and prev_metrics == cur_metrics:
            _append_log(log_path, {
                "ts": now.isoformat(), "module": mid, "cadence": cadence,
                "dedup_key": key, "sent": False, "reason": "no_change",
                "metrics": cur_metrics,
            })
            results.append({"module": mid, "action": "skip",
                            "reason": "no_change", "dedup_key": key})
            continue
        delta = _delta_line(prev_metrics, cur_metrics)
        if delta:
            text = delta + "\n" + text

        ok = bool(sender(chat_id, text))
        _append_log(log_path, {
            "ts": now.isoformat(), "module": mid, "cadence": cadence,
            "dedup_key": key, "sent": ok, "chat_id": chat_id,
            "honesty_tag": payload.get("honesty_tag"),
            "metrics": cur_metrics,
        })
        results.append({"module": mid, "action": "sent" if ok else "send_failed",
                        "dedup_key": key, "sent": ok})

    # Part A(2026-08-15) — 버퍼링해둔 GM 업무관리방 1통을 루프 끝에 한 번만 발송.
    if cadence == "daily" and gm_bundle_payloads:
        bundle_key = f"{GM_DAILY_BUNDLE_KEY}|{date_str}|daily"
        bundle_text = _format_gm_daily_bundle(gm_bundle_payloads, gm_bundle_prev, now)
        bundle_chat_id = resolve_chat_id(GM_DAILY_BUNDLE_ROOM, rooms)
        if dry_run:
            results.append({"module": GM_DAILY_BUNDLE_KEY, "action": "dry-run",
                            "dedup_key": bundle_key, "bot_id": GM_DAILY_BUNDLE_ROOM,
                            "chat_id": bundle_chat_id,
                            "payload": {"bundled_modules": list(gm_bundle_payloads)},
                            "text": bundle_text})
        elif bundle_chat_id is None:
            _append_log(log_path, {
                "ts": now.isoformat(), "module": GM_DAILY_BUNDLE_KEY, "cadence": cadence,
                "dedup_key": bundle_key, "sent": False, "reason": "room_unresolved",
            })
            results.append({"module": GM_DAILY_BUNDLE_KEY, "action": "skip",
                            "reason": "room_unresolved", "dedup_key": bundle_key})
        elif _already_sent(bundle_key, log_path):
            results.append({"module": GM_DAILY_BUNDLE_KEY, "action": "skip",
                            "reason": "dedup", "dedup_key": bundle_key})
        else:
            ok = bool(sender(bundle_chat_id, bundle_text))
            _append_log(log_path, {
                "ts": now.isoformat(), "module": GM_DAILY_BUNDLE_KEY, "cadence": cadence,
                "dedup_key": bundle_key, "sent": ok, "chat_id": bundle_chat_id,
            })
            results.append({"module": GM_DAILY_BUNDLE_KEY,
                            "action": "sent" if ok else "send_failed",
                            "dedup_key": bundle_key, "sent": ok})

    # 침묵 감지기 스냅샷 갱신(배1307 4차) — 기존 daily 예약작업에 편승, 새 스케줄러 등록 없음.
    # 로컬 파일 기록뿐(알림·네트워크 없음) → dry-run "부작용 0" 계약 보존 위해 실발행에서만 실행.
    if cadence == "daily" and not dry_run:
        try:
            from module_silence_detector import publish_snapshot  # noqa: PLC0415
            publish_snapshot()
        except Exception:
            pass  # 스냅샷 갱신 실패가 본 리포터의 발송 결과를 막지 않는다

        # 재발방지 회귀감시(캐논값·규칙 발산) 일일 실행(2026-07-20 웰리) — status/schedule.json에
        # "매일 09:15" 로 문서화만 돼 있고 실제 Task Scheduler 등록이 없던 사각지대를,
        # 새 예약작업 등록 대신 이미 라이브 등록된 Wellperion-Module-Report-Daily 에 편승해 메운다.
        # 회귀(신규 캐논복사/규칙재서술·가드유실·박제깨짐) 발견 시 내부에서 텔레그램 1줄 경보
        # (telegram_bot/.env TELEGRAM_CHAT_ID=GM 업무보고봇방)까지 자체 처리 — 정상이면 무발신.
        try:
            if _SSOT_DIR not in sys.path:
                sys.path.insert(0, _SSOT_DIR)
            from incident_regression_monitor import run as run_regression_monitor  # noqa: PLC0415
            run_regression_monitor()
        except Exception:
            pass  # 회귀감시 실패가 본 리포터의 발송 결과를 막지 않는다

        # 자가건강 감시(2026-08-08 시토) — 위 회귀감시와 같은 이유로 여기 편승한다.
        # [2026-08-29 GM 승인] 단독 발신은 껐다(notify=False) — 이상 전문은 바로 위에서
        # 나간 09:10 cto-automation-health 다이제스트(_self_health_rows 전체 줄)에 이미
        # 실려 있어, 같은 방에 2분 뒤 두 번째 통(09:12 「🚨 ERP 이상 신호」)이 중복이었다.
        # 기록·하트비트(침묵 감지용 자가증명)는 그대로 남는다.
        try:
            from self_health_watchdog import run_watchdog  # noqa: PLC0415
            run_watchdog(dry_run=False, notify=False)
        except Exception:
            pass  # 자가건강 감시 실패가 본 리포터의 발송 결과를 막지 않는다

    return {"cadence": cadence, "date": date_str, "dry_run": dry_run, "results": results}


def mark_bundle_sent(dedup_keys: list[str], *, cadence: str, log_path=REPORT_LOG_PATH, now=None) -> None:
    """배10011 — weekly_bundle_pending 으로 흡수된 모듈들을, 흡수한 메시지가 실제로
    발송 성공한 뒤 이 함수로 module_report_log.jsonl 에 sent=True 확정 기록한다.
    이래야 다음 실행에서 _already_sent() 가 True 를 내어 재적재·중복을 막는다."""
    now = now or datetime.now()
    for key in dedup_keys:
        mid = key.split("|", 1)[0]
        _append_log(log_path, {
            "ts": now.isoformat(), "module": mid, "cadence": cadence,
            "dedup_key": key, "sent": True, "note": "absorbed_bundle(배10011)",
        })


def _cadences_due_today(today=None) -> list:
    """오늘 돌려야 할 주기 목록. daily 는 매일, weekly 는 월요일, monthly 는 1일.

    ★2026-08-01(시토 · GM 승인 "예약작업 묶기") — 예전엔 같은 이 스크립트를 주기만 바꿔
      **예약작업 세 개**로 따로 등록해 뒀다(Daily 09:10 · Weekly 월 09:00 · Monthly 1일 09:10).
      하는 일이 같은데 등록만 셋이라, 하나가 죽어도 다른 게 도는 것처럼 보여 알아채기 어려웠다.
      날짜 판단을 여기 한 곳에 두고 예약작업은 하나만 남긴다(약속 L21 — 관문에만).
      요일·날짜 기준은 원래 예약작업이 잡혀 있던 값 그대로다(월요일·매월 1일).
    """
    from datetime import date as _date
    d = today or _date.today()
    due = ["daily"]
    if d.weekday() == 0:      # 월요일
        due.append("weekly")
    if d.day == 1:
        due.append("monthly")
    return due


def main(argv=None):
    ap = argparse.ArgumentParser(description="범용 모듈 자동보고 리포터(공유 SSOT 소비)")
    ap.add_argument("--cadence", required=True, choices=VALID_CADENCES + ("auto",),
                    help="auto = 오늘 해당하는 주기를 모두 실행(매일 + 월요일이면 주간 + 1일이면 월간)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--module", default=None)
    args = ap.parse_args(argv)

    if args.cadence == "auto":
        rc = 0
        for cad in _cadences_due_today():
            print(f"=== cadence={cad} ===")
            rc |= main(["--cadence", cad]
                       + (["--dry-run"] if args.dry_run else [])
                       + (["--module", args.module] if args.module else []))
        return rc

    out = run_report(args.cadence, dry_run=args.dry_run, only_module=args.module, heartbeat=True)

    for r in out["results"]:
        if r["action"] == "dry-run":
            print(f"[dry-run] {r['module']} → bot_id={r['bot_id']} "
                  f"chat_id={r['chat_id']} key={r['dedup_key']}")
            print(json.dumps(r["payload"], ensure_ascii=False, indent=2))
            print("--- 발송 텍스트 ---")
            print(r["text"])
            print()
        else:
            print(f"[{r['action']}] {r['module']} "
                  f"{r.get('reason', '') or r.get('dedup_key', '') or ''}".rstrip())

    print(f"\n요약: cadence={out['cadence']} dry_run={out['dry_run']} "
          f"결과 {len(out['results'])}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
