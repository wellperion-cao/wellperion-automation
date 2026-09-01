#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/kakao_auto_daily_report.py — 카톡 매출보고 9시 무인 발송 오케스트레이터

배경(2026-07-07 CTO): 두 코어 스크립트를 하나의 무인 흐름으로 묶는다.
    1) scripts/generate_sales_report_image.py — 텔레그램 사진 없이 이미지 자체 생성
    2) scripts/kakao_report_sender.py         — 카톡 방(들)에 전송
    이 오케스트레이터가 09:00 예약작업(Task Scheduler)에 등록되면 텔레그램 버튼 탭 없이도
    완전자동 3방 발송이 가능해진다.

킬스위치(역롤백, 절대 원칙): status/kakao_auto_send.json 의 {"enabled": true/false}.
    파일이 없거나 enabled != true 면 **무인 스케줄 실행(=--rooms 미지정 실행)** 은 아무
    것도 하지 않고 로그만 남기고 exit 0 한다 — GM go 승인 전 무인 실발송 금지.
    단 --rooms 로 방을 직접 지정한 실행(검증·부분전송용)은 킬스위치와 무관하게 즉시
    실행한다(수동 검증까지 막으면 안전검증 자체가 불가능해지므로).

흐름:
    1) generate_sales_report_image.py 실행 → stdout `IMAGE: <경로>` 파싱.
       실패(FAILED: 또는 파싱 실패)면 OWNER 텔레그램 경보 + exit 1.
    2) 성공 시 caption 자동 생성(보고 대상일=오늘-1일, "M.D(요일) 매출 및 운영사항
       보고드립니다.") 후 kakao_report_sender.py 실행.
       --rooms 지정 시 방마다 --only-room 반복 호출(콤마구분), 미지정 시 옵션 없이
       3방 일괄 1회 호출. --dry-run 은 그대로 sender에 전달.
    3) sender가 DONE이면 status/kakao_last_send.json 갱신(있으면 재사용) + 정상 로그.
       실패(BLOCKED/일부 방 실패)면 OWNER 텔레그램에 실패 방·사유 1줄 경보.

휴관일 인지(2026-07-07 CTO, GM 확정 규칙 · 배488): 보고 대상일(=기준일-1일)이
    휴관일(신정·설날·추석·매월 2·4째 일요일 — scripts/close_days.py 판정)이면 이미지
    생성·전송을 건너뛰고, 대신 "M.D(요일)은(는) 휴관일이었습니다. …" 안내문 텍스트만
    3방에 전송한다(kakao_report_sender.py --message 경로). 정상 영업일이면 기존 이미지
    경로 그대로.

사용:
    python scripts/kakao_auto_daily_report.py                          # 무인 실행(킬스위치 게이트, 3방 실발송)
    python scripts/kakao_auto_daily_report.py --dry-run --rooms "김남욱" # 수동 검증(게이트 무시, 미전송)
    python scripts/kakao_auto_daily_report.py --as-of 20260112 --dry-run --rooms "김남욱"  # 특정 기준일 시뮬레이션
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from close_days import is_closed, next_business_day  # noqa: E402
from generate_sales_report_image import profile_chrome_pids, GAS_URL  # noqa: E402
try:  # 발신 관문(best-effort) — 임포트 실패해도 경보 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = Path(__file__).resolve().parent / "generate_sales_report_image.py"
SENDER_SCRIPT = Path(__file__).resolve().parent / "kakao_report_sender.py"
ENV_PATH = ROOT / "telegram_bot" / ".env"
KILL_SWITCH_FILE = ROOT / "status" / "kakao_auto_send.json"
STATUS_FILE = ROOT / "status" / "kakao_last_send.json"

_WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── .env 직독(하드코딩 금지) — scripts/telegram_health_check.py와 동일 방식 ──────────
def _load_env(path: Path) -> dict:
    env: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception as exc:
        log(f"[경고] .env 읽기 실패: {exc}")
    return env


def send_owner_alert(message: str) -> None:
    """실패 경보(best-effort) — AI 진행현황방으로 (2026-08-04 GM "시토 진행건은 AI방").
    카톡 '내용'(매출 보고)은 업무보고방 소관이 맞지만, 그 내용이 **안 나갔다는 배선
    경보**는 tech_check 다 — 내용과 배선 경보를 가른다. 종전엔 .env OWNER_ID(업무
    보고방)로 갔다(08-04 09:31 실측). 분류는 alert_router 한 곳만(약속 L01)."""
    try:
        env = _load_env(ENV_PATH)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            log("[경고] TELEGRAM_BOT_TOKEN(.env) 없음 — 경보 발송 생략")
            return
        from alert_router import TECH_CHECK, route  # noqa: PLC0415
        ok = _tg_send(token, route(TECH_CHECK), message, source="kakao_auto_daily_report.send_owner_alert", timeout=15)
        log("OWNER 텔레그램 경보 발송 완료" if ok else "[경고] 경보 발송 실패")
    except Exception as exc:
        log(f"[경고] 경보 발송 예외(무시): {exc}")


def kill_switch_enabled() -> bool:
    """status/kakao_auto_send.json 의 enabled 필드. 파일 없음/파싱 실패=False(안전측 기본값)."""
    try:
        cfg = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("enabled", False))
    except Exception:
        return False


# ── 매출보고 정본 렌더 단일화(배99, 2026-07-25 시토) ─────────────────────────────
# 같은 매출시트를 GAS(매출보고_자동발송.js, ~09:00 텔레그램 사진)와 이 파이프라인
# (generate_sales_report_image.py, 09:30 카톡)이 **각각 따로** 렌더해 왔다(약속 L01 위반형).
# 정본 렌더 = generate_sales_report_image.py 산출물(아카이브 PNG) 하나로 확정 —
# 카톡 방향 재사용(봇이 자기 메시지를 getUpdates로 못 받아 텔레그램 사진의 무인 수신이
# 불가)은 기술적으로 막혀 있어, 가능한 유일한 단일화 방향이 이쪽이다.
# 텔레그램도 같은 PNG를 쓰도록 아래 게이트를 배선한다. 기본 OFF —
# **GAS 09:00 사진 푸시 트리거를 끈 뒤에만** status/kakao_auto_send.json 에
# "telegram_photo": true 로 켠다(이중 발송 방지 · 채널 변경이라 GM go 후 전환).
def telegram_photo_enabled() -> bool:
    """킬스위치 파일의 telegram_photo 필드(기본 false=GAS가 계속 담당)."""
    try:
        cfg = json.loads(KILL_SWITCH_FILE.read_text(encoding="utf-8"))
        return bool(cfg.get("telegram_photo", False))
    except Exception:
        return False


def send_telegram_photo(image_path: str, caption: str) -> bool:
    """정본 PNG를 텔레그램(GM 보고방)에도 발송 — 기존 사진 관문
    telegram_notifier.TelegramNotifier.send_photo 경유(전역 페이싱+발신 계측 자동 편입, L21)."""
    try:
        agents_dir = str(ROOT / "wellperion-agents")
        if agents_dir not in sys.path:
            sys.path.insert(0, agents_dir)
        from telegram_notifier import TelegramNotifier
        r = TelegramNotifier().send_photo(image_path, caption)
        return bool(isinstance(r, dict) and r.get("ok"))
    except Exception as exc:
        log(f"[경고] 텔레그램 사진 발송 실패(카톡 전송은 계속 진행): {exc}")
        return False


# ── 회장님 매출보고 핵심숫자 텍스트화(GM 지시 2026-08-08) ─────────────────────────
# 배경: 회장님 방 09:30 보고는 사진이라 로그로 숫자 대조가 안 된다(2026-08-01 옛값
# 오발송을 사람이 다음날에야 발견). GM 결정 = 회장님 방은 사진 그대로 유지, 같은
# 숫자를 텍스트로 업무보고방(8254867551)에도 남겨 로그 대조가 가능하게 한다.
# ★숫자 출처는 이미지와 반드시 같아야 한다(별도 재계산 금지) — GAS
# action=daily_report_rate_debug 가 이미지가 export하는 그 파일·그 '보고' 탭의
# "✅ 총 매출 합계" 행(금일|월누적|월목표|월달성률)을 직독한다(_kpiDailyReportRateDebug,
# .deploy-todo/업무&결재 현황.js) — resolve_sheet()/export_url_for()와 동일 파일 해석
# 규칙(_kpiSalesReportTab)을 GAS 쪽에서 공유하므로 이미지와 같은 셀 값이 나온다.
SALES_REPORT_WORK_ROOM_ID = 8254867551  # 업무보고방(@namuki_report_bot) — 회장님 방 아님


def fetch_daily_report_numbers(target_date: datetime) -> "dict | None":
    """이미지가 그린 '✅ 총 매출 합계' 행을 GAS 직독. 실패/못 찾음 → None(호출부가 '미수집' 표기)."""
    import requests
    try:
        resp = requests.get(GAS_URL, params={"action": "daily_report_rate_debug", "month": target_date.month},
                             timeout=30)
        data = resp.json()
    except Exception as exc:
        log(f"[경고] 매출 핵심숫자 조회 실패: {exc}")
        return None
    if not data.get("ok"):
        log(f"[경고] 매출 핵심숫자 조회 실패(ok=false): {data.get('error')}")
        return None
    for row in data.get("rows", []):
        if "총 매출 합계" in str(row.get("label", "")):
            n = {k: (row.get(k) or {}).get("value") for k in ("today", "month", "target", "rate")}
            n["rate_formula"] = (row.get("rate") or {}).get("formula", "")
            return n
    log("[경고] '총 매출 합계' 행을 GAS 응답에서 못 찾음")
    return None


def _fmt_won(v) -> str:
    return f"{round(v):,}원" if isinstance(v, (int, float)) else "미수집"


def _fmt_rate(v) -> str:
    """시트 퍼센트 서식 셀은 raw value가 분수(0.2634)로 온다 — 정수 퍼센트(예 71%)로 이미
    저장된 값과 헷갈리지 않게 절대값 1 이하만 100배(분수 판정)."""
    if not isinstance(v, (int, float)):
        return "미수집"
    return f"{v * 100:.2f}%" if -1 <= v <= 1 else f"{v:.2f}%"


SALES_TARGETS_FILE = ROOT / "status" / "sales_targets.json"


def _canon_monthly_target() -> "int | None":
    """월 목표 정본(status/sales_targets.json). 없거나 깨졌으면 None(대조 생략)."""
    try:
        return int(json.loads(SALES_TARGETS_FILE.read_text(encoding="utf-8"))["monthly_target_total"])
    except Exception:
        return None


def check_sales_numbers(nums: "dict | None", canon_target: "int | None") -> list[str]:
    """매일 발송 직전 숫자 자체를 검사한다. 이상 없으면 빈 목록.

    배351(2026-08-04): 달성률 셀이 다른 시트 부분합을 분모로 물어 같은 행 목표와
    어긋난 채 회장님 방으로 나갔다. 그때 만든 회귀 감시(구 scripts/
    _check_sales_report_rate_formula.py)는 아무 곳에서도 호출되지 않아 한 번도 돈 적이
    없었다 — 그래서 검사를 별도 스크립트로 두지 않고 발송 관문 안으로 옮긴다(약속 L21).

    배464(2026-08-08 GM 정정): 시트 월목표(현실 목표 6.105억)와 정본(이상 목표 6.6억)은
    어긋난 게 아니라 성격이 다른 두 값이다 — 같아야 한다는 경고는 없앤다. 대신 두 값이
    각자 살아 있는지만 본다(정본 파일을 못 읽거나 시트 목표가 비면 그건 진짜 이상이다).
    """
    n = nums or {}
    warns: list[str] = []

    target, month, rate = n.get("target"), n.get("month"), n.get("rate")
    if nums is not None and not isinstance(target, (int, float)):
        warns.append("⚠️ 현실 목표(시트 월목표) 값을 못 읽었습니다")
    if nums is not None and canon_target is None:
        warns.append("⚠️ 이상 목표(정본, status/sales_targets.json) 값을 못 읽었습니다")

    if "INDIRECT" in str(n.get("rate_formula", "")):
        warns.append("⚠️ 달성률 수식이 다른 시트 부분합을 분모로 씁니다(배351 재발)")

    if all(isinstance(v, (int, float)) for v in (month, rate, target)) and target:
        if abs(rate - month / target) > 1e-6:
            warns.append(f"⚠️ 달성률({rate * 100:.2f}%)이 월누적÷목표({month / target * 100:.2f}%)와 다릅니다")

    return warns


def build_sales_numbers_text(target_date: datetime, nums: "dict | None") -> str:
    """배464(2026-08-08 GM 정정): 목표는 현실(시트)·이상(정본) 두 줄로 나란히 보이고,
    그 격차가 곧 남은 과제의 크기다 — 어긋남 경고로 다루지 않는다."""
    weekday_kr = _WEEKDAY_KR[target_date.weekday()]
    n = nums or {}
    canon_target = _canon_monthly_target()
    warns = check_sales_numbers(nums, canon_target)
    for w in warns:
        log(f"[경고] 매출 핵심숫자 대조: {w}")

    month, target, rate = n.get("month"), n.get("target"), n.get("rate")
    lines = [
        f"📊 회장님 매출보고 핵심숫자 ({target_date.month}.{target_date.day}({weekday_kr})분, "
        f"사진 대조용)",
        f"금일 매출: {_fmt_won(n.get('today'))}",
        f"당월 누적: {_fmt_won(month)}",
        f"당월 목표(현실): {_fmt_won(target)} · 달성률 {_fmt_rate(rate)}",
    ]
    if isinstance(canon_target, (int, float)) and canon_target and isinstance(month, (int, float)):
        ideal_rate = month / canon_target
        lines.append(f"당월 목표(이상): {_fmt_won(canon_target)} · 달성률 {_fmt_rate(ideal_rate)}")
        if isinstance(target, (int, float)):
            gap_pt = (rate - ideal_rate) * 100 if isinstance(rate, (int, float)) else None
            gap_pt_txt = f"{gap_pt:.2f}%p" if gap_pt is not None else "미수집"
            lines.append(f"격차(이상-현실): {round(canon_target - target):,}원 · {gap_pt_txt}")

    text = "\n".join(lines)
    return text + ("\n\n" + "\n".join(warns) if warns else "")


def send_sales_numbers_text(target_date: datetime) -> bool:
    """업무보고방(8254867551)에 텍스트 1건 발송 — tg_outbound_log 관문 경유(로그 남음)."""
    env = _load_env(ENV_PATH)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        log("[경고] TELEGRAM_BOT_TOKEN(.env) 없음 — 핵심숫자 텍스트 발송 생략")
        return False
    nums = fetch_daily_report_numbers(target_date)
    text = build_sales_numbers_text(target_date, nums)
    ok = _tg_send(token, SALES_REPORT_WORK_ROOM_ID, text,
                   source="kakao_auto_daily_report.send_sales_numbers_text", timeout=15)
    log(f"업무보고방 매출 핵심숫자 텍스트 {'발송 완료' if ok else '발송 실패'}")
    return ok


# status/kakao_last_send.json 기록은 더 이상 여기서 하지 않는다(2026-08-04 CTO) — 관문
# kakao_report_sender.py의 write_status()가 단일 기록 지점이다(run_sender/run_sender_message
# 가 --status-file 로 STATUS_FILE 경로를 넘긴다). 이유: 이 래퍼만 상태를 적고 사람이
# kakao_report_sender.py를 직접 불러 재발송하면(09:34 3방 재발송 사고, 2026-08-04) 그
# 결과가 어디에도 안 남아 화면이 옛 실패에 굳어 있었다 — 관문 한 곳으로 옮기면 어느
# 경로로 불러도 같은 파일에 정직하게 반영된다.


# 북극성 대비 블록 헬퍼(_northstar_prefix)는 지웠다 — GM 지시 2026-08-02 로 회장님
# 매출보고에서 이 블록을 빼면서 호출부가 사라졌다. 꺼둔 채 남기면 죽은 코드가 되고
# 나중에 누가 다시 켠다(약속 L21). 블록 자체는 northstar_reach.build_northstar_block()
# 에 그대로 살아 있고, 거기서 매월 1일에만 나가도록 막혀 있다.


def build_caption(target_date: datetime) -> str:
    """보고 대상일(통상 오늘-1일) 기준 "M.D(요일) 매출 및 운영사항 보고드립니다." 한 줄.

    ★북극성 대비 블록을 여기에 넣지 않는다 (GM 지시 2026-08-02).
    기준 = 2026-07-30 자 보고 형식(= 2026-07-31 09:30 발신) — 인사말 한 줄뿐이었다.
    2026-07-31 커밋 05a6d5fd5 가 백그라운드 보고 5종에 북극성 블록을 얹으면서
    이 캡션도 "회장님, 🌟 북극성 대비 — …" 로 시작하고 인사말이 맨 아래로 밀렸다
    (08-01 09:30 발신 1회가 그렇게 나갔다). GM 이 그 형식을 되돌리도록 지시했고,
    북극성 대비는 정비 후 매월 1일에만 별도로 보낸다 — 일일 매출보고에는 안 붙는다."""
    return f"{_md(target_date)} 매출 및 운영사항 보고드립니다."


def _md(d: datetime) -> str:
    return f"{d.month}.{d.day}({_WEEKDAY_KR[d.weekday()]})"


def last_reported_target() -> "datetime | None":
    """마지막으로 실제 발송에 성공한 '보고 대상일'. 모르면 None.

    STATUS_FILE 에 last_ok_target 이 있으면 그것이 정본이다(성공할 때마다 갱신).
    옛 기록엔 그 칸이 없으므로, ok=true 인 IMAGE_REPORT 기록의 발송 시각에서
    하루를 빼 대신 쓴다(발송일-1 = 그날의 보고 대상일)."""
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    raw = data.get("last_ok_target")
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            pass
    if data.get("ok") and data.get("kind") == "IMAGE_REPORT":
        try:
            return datetime.strptime(data["at"][:10], "%Y-%m-%d") - timedelta(days=1)
        except Exception:
            return None
    return None


def record_ok_target(target_date: datetime) -> None:
    """발송 성공 시 STATUS_FILE 에 보고 대상일을 남긴다(다음 회차의 밀린 날 판정 근거).
    새 파일을 만들지 않는다(약속 L21) — 이미 발신 관문이 쓰는 파일에 칸 하나만 더한다."""
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else {}
        data["last_ok_target"] = target_date.strftime("%Y-%m-%d")
        STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"[경고] 보고 대상일 기록 실패(무시): {exc}")


def missed_targets(target_date: datetime, limit: int = 10) -> "list[datetime]":
    """이번 대상일 이전에 보고가 안 나간 영업일 목록(오래된 순).

    윈도우 업데이트·PC 꺼짐 등으로 회차를 통째로 놓치면 그날 인사말이 영영 안 나간다.
    보고 이미지는 그 달 시트를 통째로 찍은 것이라 숫자는 저절로 따라잡히지만, 어느 날짜
    분인지는 인사말에만 있다 — 그래서 밀린 날짜를 다음 회차 인사말에 함께 적는다
    (GM 지시 2026-08-19: '못 나가면 오늘 것까지 내일 정리해서 같이 보내줘').
    휴관일은 애초에 보고 대상이 아니라 뺀다. 마지막 성공을 모르면 빈 목록(=평소대로)."""
    last_ok = last_reported_target()
    if last_ok is None:
        return []
    # 기준일에서 시각을 떨군 뒤 비교한다. 호출부가 넘기는 target 은 datetime.now()-1일이라
    # 시각이 붙어 있고, last_ok 는 문자열에서 읽어 자정이다. 그대로 비교하면 대상일 당일이
    # 자기 자신보다 앞선 것으로 잡혀 '밀린 날' 목록에 들어간다.
    # 2026-08-20 09:30 실사고 — 인사말이 "8.19(수)·8.19(수) 매출 및 운영사항 보고드립니다."
    # 로 4개 방(회장님 포함)에 나갔다.
    target_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    day = last_ok + timedelta(days=1)
    while day < target_day and len(out) < limit:
        if not is_closed(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def build_caption_with_missed(target_date: datetime, missed: "list[datetime]") -> str:
    """밀린 날이 있으면 인사말 한 줄에 날짜를 함께 적는다.

    ★반드시 '한 줄'을 유지한다. 회장님 방에는 새 종류의 줄이 생기면 그 회차를 보류하는
    게이트가 있어(kakao_report_sender.chairman_content_allows), 설명을 별도 줄로 붙이면
    정작 밀린 날 발송이 또 막힌다. 그래서 줄 수를 늘리지 않고 날짜만 잇는다.
    2일치 = 가운뎃점 연결 / 3일치 이상 = 처음~마지막 범위. 이 두 모양만 쓴다 —
    모양이 늘 때마다 회장님 게이트 기준선에 미리 넣어 둬야 하기 때문이다."""
    if not missed:
        return build_caption(target_date)
    days = missed + [target_date]
    label = "·".join(_md(d) for d in days) if len(days) == 2 else f"{_md(days[0])}~{_md(days[-1])}"
    return f"{label} 매출 및 운영사항 보고드립니다."


def build_holiday_notice(target: datetime, as_of: datetime) -> str:
    """보고 대상일(target=기준일-1일)이 휴관일일 때의 안내문 생성.

    biz = 기준일(as_of)부터 첫 영업일(=휴관 지나 다음 보고 대상이 될 날).
    resume = biz+1일부터 첫 영업일(=biz분 매출을 실제로 보고하게 될 날).
    예) target=6/28(일, 휴관) → biz=6/29(월) → resume=6/30(화)
        "6/28(일)은 휴관일이었습니다. 화요일에 월요일분부터 이어서 매출·운영사항
        보고드리겠습니다."
    """
    target_md = f"{target.month}/{target.day}"
    target_dow = _WEEKDAY_KR[target.weekday()]
    biz = next_business_day(as_of)
    resume = next_business_day(biz + timedelta(days=1))
    biz_dow = _WEEKDAY_KR[biz.weekday()]
    resume_dow = _WEEKDAY_KR[resume.weekday()]
    # 조사(은/는)는 요일 글자의 받침 유무로 결정 — 월·목·금·일=은 / 화·수·토=는
    josa = "은" if (ord(target_dow) - 0xAC00) % 28 != 0 else "는"
    return (
        f"{target_md}({target_dow}){josa} 휴관일이었습니다. {resume_dow}요일에 "
        f"{biz_dow}요일분부터 이어서 매출·운영사항 보고드리겠습니다."
    )


def _run(cmd: list[str]) -> "tuple[int, str]":
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _parse_tag(output: str, tag: str) -> "str | None":
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith(tag):
            return line[len(tag):].strip()
    return None


def generate_image(target_date: datetime) -> "tuple[bool, str]":
    """generate_sales_report_image.py 실행. 반환: (성공여부, IMAGE경로 또는 실패사유).

    ★보고 대상일을 넘긴다(2026-09-01 시토 · GM 지적). 안 넘기면 생성기가 제 나름대로
    '오늘'을 기준일로 잡아 그 달 시트를 찾는다 — 같은 달 안에서는 어제·오늘이 같은 달이라
    티가 안 나지만 **매월 1일에는 아직 없는 그 달 시트를 찾다 실패**한다(2026-09-01 09:30
    실측: monthly_sales_file_not_found: 2026-9 로 매출보고가 안 나갔다). 대상일은 오케스트
    레이터가 이미 알고 있으므로 그대로 넘겨 기준을 한 곳으로 모은다.
    """
    cmd = [sys.executable, str(GEN_SCRIPT), "--date", target_date.strftime("%Y%m%d")]
    log(f"이미지 생성 실행: {' '.join(cmd)}")
    rc, output = _run(cmd)
    print(output, end="" if output.endswith("\n") else "\n")
    image_path = _parse_tag(output, "IMAGE:")
    if rc == 0 and image_path:
        return True, image_path
    reason = _parse_tag(output, "FAILED:") or "알 수 없는 오류(이미지 생성 단계)"
    return False, reason


def wait_for_profile_chrome_clear(timeout_sec: int = 60) -> None:
    """이미지 생성이 쓰던 profiles/danggn 크롬이 남아 있으면 발신기가 카톡 창을 포그라운드로
    못 끌어온다(Windows 포그라운드 잠금 — 배348). 고정 sleep 대신 조건 폴링: 정확한 소요시간은
    확정 못 했으므로(추정) 사라지는 즉시 진행, 상한을 넘기면 로그만 남기고 계속한다(안 멈춤)."""
    start = time.time()
    while time.time() - start < timeout_sec:
        if not profile_chrome_pids():
            return
        time.sleep(1.0)
    remaining = profile_chrome_pids()
    if remaining:
        log(f"이미지 생성 크롬 잔존({remaining}) — {timeout_sec}초 대기 후에도 안 사라짐, 그대로 진행")


def run_sender(rooms: "list[str] | None", image_path: str, caption: str, dry_run: bool) -> "tuple[bool, list[str]]":
    """rooms=None → 옵션 없이 3방 일괄 1회 호출. rooms=[...] → 방마다 --only-room 반복 호출."""
    failures: list[str] = []
    targets = rooms if rooms else [None]
    for room in targets:
        # --sender 매출보고 — kakao_report_sender 사람 방 발신 가드(배 11070 ⑤) 통과용
        # (rooms[] 기본 4방에 사람 방 ★운영부가 섞여 있다).
        cmd = [sys.executable, str(SENDER_SCRIPT), "--image", image_path, "--caption", caption,
               "--status-file", str(STATUS_FILE), "--status-kind", "IMAGE_REPORT",
               "--sender", "매출보고"]
        if dry_run:
            cmd.append("--dry-run")
        if room:
            cmd.extend(["--only-room", room])
        label = room or "전체(3방 일괄)"
        log(f"카톡 전송 실행[{label}]: {' '.join(cmd)}")
        rc, output = _run(cmd)
        print(output, end="" if output.endswith("\n") else "\n")
        tail = output.strip().splitlines()[-1] if output.strip() else "출력 없음"
        log(f"카톡 전송 결과[{label}]: rc={rc} tail={tail}")
        if rc != 0 or "DONE:" not in output:
            failures.append(f"{label}: {tail}")
    return (len(failures) == 0), failures


def run_sender_message(rooms: "list[str] | None", message: str, dry_run: bool) -> "tuple[bool, list[str]]":
    """휴관일 안내문 전용 — kakao_report_sender.py를 --message로 호출(이미지 경로 없음).
    rooms=None → 옵션 없이 3방 일괄 1회 호출. rooms=[...] → 방마다 --only-room 반복 호출."""
    failures: list[str] = []
    targets = rooms if rooms else [None]
    for room in targets:
        # --sender 매출보고 — 위와 동일 가드 통과용(휴관일 안내문도 같은 3~4방 계열).
        cmd = [sys.executable, str(SENDER_SCRIPT), "--message", message,
               "--status-file", str(STATUS_FILE), "--status-kind", "HOLIDAY_NOTICE",
               "--sender", "매출보고"]
        if dry_run:
            cmd.append("--dry-run")
        if room:
            cmd.extend(["--only-room", room])
        label = room or "전체(3방 일괄)"
        log(f"카톡 안내문 전송 실행[{label}]: {' '.join(cmd)}")
        rc, output = _run(cmd)
        print(output, end="" if output.endswith("\n") else "\n")
        tail = output.strip().splitlines()[-1] if output.strip() else "출력 없음"
        log(f"카톡 안내문 전송 결과[{label}]: rc={rc} tail={tail}")
        if rc != 0 or "DONE:" not in output:
            failures.append(f"{label}: {tail}")
    return (len(failures) == 0), failures


def main() -> int:
    ap = argparse.ArgumentParser(description="카톡 매출보고 9시 무인 발송 오케스트레이터")
    ap.add_argument("--rooms", default=None,
                     help="콤마구분 방 이름(검증·부분전송용). 지정 시 킬스위치와 무관하게 즉시 실행")
    ap.add_argument("--dry-run", action="store_true", help="sender에 --dry-run 전달(실전송 안 함)")
    ap.add_argument("--as-of", default=None, metavar="YYYYMMDD",
                     help="실행 기준일(기본=오늘). 시뮬레이션·테스트용 — 보고 대상일=기준일-1일")
    ap.add_argument("--selftest-numbers", action="store_true",
                     help="check_sales_numbers() 자체 검사(발송·네트워크 없음)")
    args = ap.parse_args()

    if args.selftest_numbers:
        ok = {"today": 1, "month": 160817436, "target": 610500000,
              "rate": 160817436 / 610500000, "rate_formula": "=J4/K4"}
        assert check_sales_numbers(ok, 610500000) == []
        assert check_sales_numbers(ok, 660000000) == []  # 현실≠이상 정상(배464 GM 정정) — 경고 없음
        assert any("정본" in w for w in check_sales_numbers(ok, None))  # 정본 값 못 읽으면 경고
        assert any("배351" in w for w in check_sales_numbers(
            {**ok, "rate_formula": '=SUM(INDIRECT("x"))'}, 610500000))
        assert any("월누적÷목표" in w for w in check_sales_numbers({**ok, "rate": 0.9}, 610500000))
        assert check_sales_numbers(None, 610500000) == []
        text = build_sales_numbers_text(datetime(2026, 8, 8), ok)
        assert "당월 목표(현실): 610,500,000원" in text
        assert "당월 목표(이상): 660,000,000원" in text
        assert "격차(이상-현실): 49,500,000원" in text
        assert "정본" not in text and "다릅니다" not in text
        print("PASS — check_sales_numbers/build_sales_numbers_text 6종")

        # 밀린 회차 인사말(2026-08-19 GM 지시) — 줄 수가 늘지 않는지까지 함께 본다.
        d = lambda s: datetime.strptime(s, "%Y-%m-%d")  # noqa: E731
        assert build_caption_with_missed(d("2026-08-19"), []) == "8.19(수) 매출 및 운영사항 보고드립니다."
        assert build_caption_with_missed(d("2026-08-19"), [d("2026-08-18")]) == \
            "8.18(화)·8.19(수) 매출 및 운영사항 보고드립니다."
        assert build_caption_with_missed(d("2026-08-19"), [d("2026-08-17"), d("2026-08-18")]) == \
            "8.17(월)~8.19(수) 매출 및 운영사항 보고드립니다."
        for cap in ("8.19(수) 매출 및 운영사항 보고드립니다.",
                    "8.18(화)·8.19(수) 매출 및 운영사항 보고드립니다.",
                    "8.17(월)~8.19(수) 매출 및 운영사항 보고드립니다."):
            assert len(cap.splitlines()) == 1, f"인사말이 여러 줄이 되면 회장님 게이트가 막는다: {cap!r}"
        print("PASS — 밀린 회차 인사말 3종(한 줄 유지)")

        # 밀린 날 판정에 시각이 섞이면 대상일이 자기 자신을 밀린 날로 잡는다(2026-08-20 실사고).
        # 위 3종은 전부 자정 datetime 이라 이 결함을 통과시켰다 — 호출부가 실제로 넘기는
        # 모양(시각 있음)으로 한 번 더 본다.
        _orig = globals()["last_reported_target"]
        globals()["last_reported_target"] = lambda: d("2026-08-18")
        try:
            timed = datetime(2026, 8, 19, 9, 30)
            assert missed_targets(timed) == [], "대상일 당일이 밀린 날로 잡히면 날짜가 두 번 찍힌다"
            assert build_caption_with_missed(timed, missed_targets(timed)) == \
                "8.19(수) 매출 및 운영사항 보고드립니다."
            globals()["last_reported_target"] = lambda: d("2026-08-17")
            assert missed_targets(timed) == [d("2026-08-18")]
        finally:
            globals()["last_reported_target"] = _orig
        print("PASS — 밀린 날 판정(시각 섞인 기준일)")
        return 0

    if sys.platform != "win32":
        print("FAILED: 이 스크립트는 Windows 전용입니다.")
        return 1

    rooms = [r.strip() for r in args.rooms.split(",") if r.strip()] if args.rooms else None

    try:
        as_of = datetime.strptime(args.as_of, "%Y%m%d") if args.as_of else datetime.now()
    except ValueError:
        print(f"FAILED: --as-of 형식 오류(YYYYMMDD 필요): {args.as_of!r}")
        return 1

    if rooms is None:
        if not kill_switch_enabled():
            log(f"킬스위치 OFF({KILL_SWITCH_FILE} 없음 또는 enabled=false) — 무인 실행 생략(아무 작업 안 함)")
            print("SKIPPED: 킬스위치 비활성 — 아무 작업도 하지 않음")
            return 0
        log("킬스위치 ON — 무인 3방 발송 진행")
    else:
        log(f"--rooms 지정({rooms}) — 킬스위치와 무관하게 즉시 실행(수동 검증 모드)")

    target = as_of - timedelta(days=1)
    log(f"기준일(as_of)={as_of.strftime('%Y-%m-%d')} / 보고 대상일(target)={target.strftime('%Y-%m-%d')}")

    if is_closed(target):
        notice = build_holiday_notice(target, as_of)
        log(f"휴관일 분기 — 안내문: {notice!r}")

        ok, failures = run_sender_message(rooms, notice, args.dry_run)
        if ok:
            msg = f"DONE: 카톡 {'검증(dry-run)' if args.dry_run else '전송'} 완료(휴관 안내문) — {notice}"
            log(msg)
            print(msg)
            return 0
        else:
            detail = "; ".join(failures)
            send_owner_alert(f"⚠️ 카톡 휴관 안내문 자동 발송 실패 — {detail}")
            print(f"FAILED: 카톡 휴관 안내문 전송 실패 — {detail}")
            return 1

    ok, image_or_reason = generate_image(target)
    if not ok:
        msg = f"⚠️ 카톡 매출보고 자동 파이프라인 실패 — 이미지 생성 단계: {image_or_reason}"
        log(msg)
        send_owner_alert(msg)
        print(f"FAILED: 이미지 생성 실패 — {image_or_reason}")
        return 1
    image_path = image_or_reason
    log(f"이미지 생성 성공: {image_path}")

    missed = missed_targets(target)
    if missed:
        log(f"밀린 보고 대상일 {len(missed)}건 — 이번 회차에 함께 적는다: "
            f"{[d.strftime('%Y-%m-%d') for d in missed]}")
    caption = build_caption_with_missed(target, missed)
    log(f"caption: {caption!r}")

    # 정본 렌더 단일화(배99): 게이트 ON이면 같은 PNG를 텔레그램에도 발송(GAS 대체).
    if telegram_photo_enabled():
        if args.dry_run:
            log("텔레그램 사진 게이트 ON — dry-run이라 발송 생략")
        else:
            tg_ok = send_telegram_photo(image_path, caption)
            log(f"텔레그램 사진 발송 {'완료' if tg_ok else '실패'} — 정본 PNG 재사용({image_path})")

    wait_for_profile_chrome_clear()
    ok, failures = run_sender(rooms, image_path, caption, args.dry_run)
    if ok:
        # 핵심숫자 텍스트 = 폐지 (GM 지시 2026-08-13 "회장님 매출보고 핵심숫자도 보내지말아줘").
        #   2026-08-08 에 '회장님 사진 발송 직후 같은 숫자를 업무보고방에도 텍스트로' 붙였던 한 줄이다.
        #   같은 값이 사진에 이미 있고, 08:00 항로 부록에도 이달 매출·지출이 나간다 — 세 번째였다.
        #   게이트로 끄지 않고 호출을 지운다(약속 L21). 되살릴 일이 생기면 이 커밋을 되돌린다.
        #   build_sales_numbers_text 는 --selftest-numbers 와 되돌림용으로 남겨 둔다(호출부 0).
        # 밀린 날 판정 근거는 **무인 3방 발송이 성공했을 때만** 남긴다.
        #   --rooms 로 방 하나만 지정한 검증 실행까지 '그날 보고 끝남'으로 적으면,
        #   진짜 못 나간 날이 다음 회차 인사말에서 빠진다(검증이 사실을 덮는다).
        if not args.dry_run and rooms is None:
            record_ok_target(target)
        detail = "DRY-RUN 검증 완료" if args.dry_run else "3방 전송 완료" if rooms is None else f"{rooms} 전송 완료"
        msg = f"DONE: 카톡 {'검증(dry-run)' if args.dry_run else '전송'} 완료 — {detail}"
        log(msg)
        print(msg)
        return 0
    else:
        detail = "; ".join(failures)
        send_owner_alert(f"⚠️ 카톡 매출보고 자동 발송 실패 — {detail}")
        print(f"FAILED: 카톡 전송 실패 — {detail}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
