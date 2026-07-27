#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""weekly_marketing_feedback.py — 시모 마케팅 폐루프 ⑤ '평가 환류' v1: 주간 마케팅 피드백 브리프 생성기.

담당: AI CMO 시모 | 버전: v1 (프레임, 2026-07-03)
스펙: .omc/specs/deep-interview-cmo-eval-feedback-loop.md (deep-interview 확정 · 모호도 14%)
정직 원칙(약속 L05): 측정 못하는 걸 측정한 척 안 함. 가짜 자동 점수판 없음.
v1 = **정성 우선 + 측정 보조**. 자동 가중 점수는 UTM 데이터가 충분히 쌓인 뒤(v2).

범위: **공식 @wellperion 계정 전용.** 개인 시리즈(namuk)는 제외 — ship31이 별도 정성 소유
(review_queue.json account=="wellperion" 아닌 항목은 전부 배제해 중복 방지).

데이터 소스 (기존 파이프 재사용 — 신규 배관 없음):
  - 공식 발행 콘텐츠: 3. 웰페리온 가이드/cmo/review/review_queue.json
      (account=="wellperion" AND status=="발행완료" AND published_at 최근 7일)
  - 측정 보조 신호: 문의Survey GAS(funnel) — funnel_conversion(byChannel)
  - 신규 등록 상세(2026-07-06 가산): 동일 GAS — member_registered_list(멤버십, 등록일 기간필터)
      · lesson_registry_list(강습 종목별, 등록일 기간필터). [배140 2026-07-27 정정] 발레·바레는
      2026-07-15 부로 외부관리 아님(원장 직접 집계, 현재 실측 0=진짜 0). 뮤지컬은 2026-07-27 배선했으나
      배포 사고로 라이브 원장 오염(중복·오늘자 오기재) — GM 승인 후 수리 전까지 뮤지컬·체조 수치는
      신뢰 불가로 표기. 강습 원장 2026-06-27 시드 시점 인원(96%)은 총계는 정상, 등록일만 기준선 미상.

산출물: status/briefs/CMO-weekly-feedback-<YYYYMMDD>.md (--mode weekly, 기본)
  1) 이번 주 공식 발행 콘텐츠 표
  2) 측정 보조 참고표 (신호별 정직 꼬리표: 측정/부분/미측정/연동 미비) + 신규 등록 상세(멤버십/강습종목)
  3) Top/Bottom 정성 판정 — 시모가 채우는 빈 슬롯(자동 채움 금지)
  4) 다음 편 제안 — 시모가 채우는 빈 슬롯(자동 G1 등록 금지, 제안 shape 힌트만 출력)

일일 모드(2026-07-06 가산, --mode daily): status/briefs/CMO-daily-feedback-<YYYYMMDD>.md —
  오늘(KST) 하루로 좁힌 가벼운 카드: ①오늘 발행 ②오늘 문의→전환 ③오늘 신규 등록 상세.
  Top/Bottom·다음 편 제안 섹션은 daily 에선 제외(그건 weekly 정성 판정 전용으로 유지).
  --dry-run: 브리프는 그대로 생성·저장하되 텔레그램 실제 발송만 생략(카드 텍스트는 stdout 출력).

──────────────────────────────────────────────────────────
Task Scheduler 주간 cron 등록 명령 (FOLLOW-UP — 아직 미등록. GM 승인 후 관리자 권한으로 1회 실행)
──────────────────────────────────────────────────────────
schtasks /create ^
  /tn "Wellperion-CMO-Weekly-Marketing-Feedback" ^
  /tr "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NonInteractive -WindowStyle Hidden -Command \"python 'C:\\Users\\jjky0\\welperion-automation\\scripts\\weekly_marketing_feedback.py'\"" ^
  /sc WEEKLY /d MON /st 09:00 ^
  /ru SYSTEM /f

* /ru SYSTEM 대신 관리자 계정명을 지정해도 됩니다.
* v1은 수동 실행(run-on-demand)이 기본 — 예약작업 등록은 후속 작업이며 본 스크립트는
  등록을 수행하지 않는다(GM 승인 후 위 명령을 관리자 권한 콘솔에서 1회 실행).
──────────────────────────────────────────────────────────

──────────────────────────────────────────────────────────
텔레그램 주간 요약 발송 (2026-07-03 GM 승인 — 라이브)
──────────────────────────────────────────────────────────
브리프 생성 끝에 5~8줄 요약을 문의알림방(chat_id=WEEKLY_SUMMARY_CHAT_ID, 시모 담당방 —
메모리 project_telegram_3room_split)으로 sendMessage 한다. 발송 로직은 ig_series_producer.py
telegram()·monthly_marketing_report.py send_message() 와 동일 패턴(urllib POST + tg_outbound_log
best-effort 로깅) — 신규 배관 없이 기존 발송 방식 재사용.
정직 원칙: Top/Bottom·다음 편 제안은 이 스크립트가 생성 시점엔 항상 빈 슬롯이므로
"시모 정리 대기"로만 표기(지어내지 않음). 측정 실패 신호는 "미측정"으로 표기.
발송 실패는 브리프 생성을 절대 막지 않는다(try/except best-effort, 리포트는 항상 저장됨).
역롤백: WEEKLY_SUMMARY_CHAT_ID = "" 로 바꾸면 즉시 미발송(브리프 생성·저장은 그대로 계속됨).
──────────────────────────────────────────────────────────
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

# Windows 콘솔(cp949)·예약작업 환경에서도 한글 print 안 깨지도록.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# requests 없으면 urllib 폴백 (monthly_marketing_report.py 와 동일 패턴).
try:
    import requests as _requests

    def _http_get(url, timeout=20):
        resp = _requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

except ImportError:
    import urllib.request

    def _http_get(url, timeout=20):
        req = urllib.request.Request(url, headers={"User-Agent": "WellperionCMO/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


# ── 경로 설정 ────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
REVIEW_QUEUE_PATH = _REPO_ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
BRIEFS_DIR = _REPO_ROOT / "status" / "briefs"

GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbykgMyFc-g_KG7x3HoKStKBwerKhYYfmbqNeFqCL5O1b_4-1nng4wEiKhkNJtfB4BWo/exec"
)

OFFICIAL_ACCOUNT = "wellperion"  # 공식 계정 리터럴 — 정확 일치만 포함(namuk.wellperion 등 개인 계정 자동 배제).
PUBLISHED_STATUS = "발행완료"

# 강습 종목 중 팀시트가 없어 lesson_registry_list 원장에 등록이 들어올 경로가 없는 종목.
#
# [배140 · 2026-07-27 시모 실측 정정] 옛 주석은 '루프메소드(발레·바레)=external·미집계'라고
# 적어뒀는데 실태와 달랐다. 2026-07-15(시토·GM)에 발레·바레는 external 을 풀고 성인강습
# 소속으로 배선됐다(sheet:null + ledger:true → 원장 SUC 직접 카운트). 그래서 '외부관리라
# 집계 안 됨'은 이미 틀린 말이었고, 12일간 잘못된 꼬리표가 매 보고서에 붙었다.
#
# 라이브 실측(2026-07-27, funnel GAS lesson_registry_list + 강습문의 스냅샷):
#   · 발레·바레 : 성인 문의 9건 · 그중 등록(SUC) 0건 → 원장 0행. 즉 지금 0 은 실제 0이다.
#   · 뮤지컬     : 유소년 문의 146건 · 그중 등록 11명(전화 중복 제거) → 집계 밖이던 진짜 구멍.
#
# ★2026-07-27 해소 완료(배140). 팀시트 없는 종목(ledger:true)은 원장을 읽기만 하고 쓰는 쪽
#   (_syncLessonRegistry_)이 팀시트 roster 만 봐서 행이 생길 경로가 없었다 — GM 이 정본으로
#   지정한 강습 '응답' 탭(성인 gid 111889422 / 유소년 268994754)에서 등록 상태 행을 수집하도록
#   배선했다. 라이브 검증(원장 2,515행): 수영1502·체조&트램폴린371·골프168 전부 사고 전 값 복귀,
#   뮤지컬 11명 편입·등록일 전부 기준선. → 목록을 비운다. 새 종목이 같은 상태가 되면 여기 다시 적는다.
#   ※ 종목명 두 체계 트랩(_sportBuckets_ '체조' vs LESSON_DISPLAY '체조&트램폴린') 주의 —
#     Survey.js _sportBuckets_ 주석 참조. 정확일치 조인 금지·매칭 실패 시 폴백 금지.
LESSON_EXTERNAL_UNTRACKED = []

# ── 재생성 시 시모 정성 판정 보존(덮어쓰기 방지) ────────────────────
# 2026-07-03 사고: 동시 재실행이 시모가 채운 §3/§4 를 빈 placeholder 로 덮어씀(수동 복구됨).
# 섹션1-2(자동 데이터)는 매번 갱신하되, §3/§4 는 시모가 이미 채웠으면 절대 재생성하지 않는다.
SECTION_3_HEADING = "## 3. Top / Bottom 정성 판정"
SECTION_4_HEADING = "## 4. 다음 편 제안"
# 각 섹션의 "아직 시모가 안 채운" placeholder 를 판별하는 마커.
# 주의: "_자동 채움 없음 — ..." 안내 문장은 시모가 Top/Bottom 을 채운 뒤에도 안내용으로
# 그대로 남겨두는 경우가 실제로 있다(2026-07-03 실사례) — 이걸 마커에 넣으면 채운 섹션도
# "미채움"으로 오판해 재생성해버린다. 그래서 실제 placeholder 문구(▸ (...))만 마커로 쓴다.
SECTION_3_PLACEHOLDER_MARKERS = ["▸ (시모 정성 판정"]
SECTION_4_PLACEHOLDER_MARKERS = ["▸ (시모: 통한 패턴"]
# 2026-07-15 §5 각 스코어카드(클릭 기반)=GM 결정으로 삭제됐으나, §4 tail 추출용 stop-heading
# 상수 SECTION_5_HEADING 정의 자체가 함께 유실되어(재사용처 3곳 NameError 잠복) 있었다.
# 2026-07-20 배834 반응 성적표 §5(IG 도달·당근 조회/찜·카페 조회 실측 — 클릭 아님)를 새로
# 신설하며 아래에서 다시 정의(버그 수리 겸용). §5는 시스템 자동 계산 전용 — 시모 정성 채움 대상
# 아니므로 §3/§4 처럼 보존 로직 불필요(매번 최신 스캔 결과로 재생성).
SECTION_5_HEADING = "## 5. 콘텐츠 반응 성적표"

# ── 텔레그램 주간 요약 발송 (문의알림방 · 2026-07-03 GM go 라이브) ─────
ENV_PATH = _REPO_ROOT / "telegram_bot" / ".env"
TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"

# 역롤백: 이 값을 "" 로 바꾸면 즉시 미발송(브리프 생성·저장은 그대로 계속됨).
WEEKLY_SUMMARY_CHAT_ID = "-5516675010"  # 문의알림방(시모 담당) — 메모리 project_telegram_3room_split

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass
    def pace(*a, **k):
        return None


def _load_env_value(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드 (ig_series_producer.py 와 동일 패턴)."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        if ENV_PATH.exists():
            for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def build_telegram_summary(items: list[dict], fc: dict | None,
                            mr: dict | None, lr: dict | None,
                            date_from: str, date_to: str, out_path: Path) -> str:
    """5~8줄 요약. 측정 실패는 '미측정', 정성 슬롯은 '시모 정리 대기'로 정직 표기(지어내지 않음)."""
    lines = [f"주간 마케팅 정리 — {date_from} ~ {date_to}", ""]
    lines.append(f"· 이번 주 공식(@wellperion) 발행: {len(items)}건")

    if fc is None:
        lines.append("· 문의 전환: 미측정(수집 실패)")
    else:
        by_ch = fc.get("byChannel") or []
        if not by_ch:
            lines.append("· 문의 전환: 0건(표본 없음)")
        else:
            total_inq = sum(d.get("inquiries", 0) for d in by_ch)
            total_conv = sum(d.get("converted", 0) for d in by_ch)
            lines.append(f"· 문의 전환: {total_inq}건 문의 → {total_conv}명 전환(채널 {len(by_ch)}개, 부분측정)")

    lines.append(_registration_oneliner(mr, lr))
    lines.append("· Top/Bottom·다음 편 제안: 시모 정리 대기")
    lines.append("")
    lines.append(f"상세=주간 마케팅 정리 보고 ({out_path.name})")
    return "\n".join(lines)


def send_telegram_summary(text: str) -> bool:
    """문의알림방에 주간 요약 1건 발송. best-effort — 실패해도 브리프 생성 자체는 막지 않는다.
    역롤백: WEEKLY_SUMMARY_CHAT_ID = "" 로 바꾸면 즉시 미발송."""
    if not WEEKLY_SUMMARY_CHAT_ID:
        print("[INFO] WEEKLY_SUMMARY_CHAT_ID 미설정 — 텔레그램 요약 발송 생략(역롤백 상태)")
        return False
    token = _load_env_value(TELEGRAM_TOKEN_ENV_KEY)
    if not token:
        print("[WARN] TELEGRAM_BOT_TOKEN 미설정 — 텔레그램 요약 발송 생략")
        return False
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": WEEKLY_SUMMARY_CHAT_ID, "text": text, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST"
        )
        pace()
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            print(f"[INFO] 텔레그램 주간 요약 {'발송 성공' if ok else '발송 실패'} (문의알림방)")
            log_outbound(text, chat_id=WEEKLY_SUMMARY_CHAT_ID,
                         source="weekly_marketing_feedback.send_telegram_summary", ok=ok, kind="sendMessage")
            return ok
    except Exception as e:
        print(f"[WARN] 텔레그램 주간 요약 발송 실패: {e} (브리프 생성은 계속됨)")
        log_outbound(text, chat_id=WEEKLY_SUMMARY_CHAT_ID,
                     source="weekly_marketing_feedback.send_telegram_summary", ok=False, kind="sendMessage")
        return False


_TZOFF_RE = re.compile(r"[+-]\d{2}:\d{2}$")


# ── 발행 시각 파싱 (review_queue.json 은 'YYYY-MM-DD' 또는 ISO 혼재) ──
def _parse_dt(raw) -> datetime.datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        if len(s) == 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.datetime.strptime(s, "%Y-%m-%d")
        s2 = s.replace("Z", "")
        s2 = _TZOFF_RE.sub("", s2)  # +09:00 등 오프셋 제거(naive 비교)
        return datetime.datetime.fromisoformat(s2)
    except Exception:
        return None


# ── ① 공식 발행 콘텐츠 (review_queue.json 재사용) ─────────────────
def load_official_recent(days: int = 7, now: datetime.datetime | None = None) -> list[dict]:
    """review_queue.json 에서 공식(@wellperion) · 발행완료 · 최근 N일 항목만 뽑는다.
    개인 시리즈(namuk)는 account 값이 다르므로(namuk.wellperion 등) 자동 배제된다."""
    now = now or datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=days)

    try:
        raw = REVIEW_QUEUE_PATH.read_text(encoding="utf-8")
        entries = json.loads(raw)
    except Exception as e:
        print(f"[WARN] review_queue.json 로드 실패: {e}")
        return []

    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("account") != OFFICIAL_ACCOUNT:
            continue
        if e.get("status") != PUBLISHED_STATUS:
            continue
        dt = _parse_dt(e.get("published_at"))
        if dt is None or dt < cutoff or dt > now:
            continue
        out.append({
            "title": e.get("title") or "(제목 없음)",
            "channel": e.get("channel") or "-",
            "published_at": e.get("published_at"),
            "published_dt": dt,
            "post_url": e.get("post_url"),
            "id": e.get("id"),
        })

    out.sort(key=lambda x: x["published_dt"], reverse=True)
    return out


# ── ② 측정 보조 신호 (funnel GAS 재사용, 신규 배관 없음) ───────────
def fetch_funnel_conversion(date_from: str, date_to: str) -> dict | None:
    """funnel_conversion — 채널별 문의·전환(자기신고 유입경로 ↔ 회원부 전화 매칭).
    2026-07-03 UTM→문의 하드 귀속 배선 라이브 — 그 이전 문의는 과거 소급 없이 자기신고 채널로만 집계됨.
    실패 시 None(→ 미측정 표기)."""
    try:
        data = _http_get(f"{GAS_URL}?action=funnel_conversion&from={date_from}&to={date_to}", timeout=40)
        if not data.get("ok"):
            print(f"[WARN] funnel_conversion ok=false: {data}")
            return None
        return data
    except Exception as e:
        print(f"[WARN] funnel_conversion 수집 실패: {e}")
        return None


# ── ②-보강 신규 등록 상세 (동일 GAS 재사용, 신규 배관 없음, 2026-07-06) ─────
def fetch_member_registered(date_from: str, date_to: str) -> dict | None:
    """member_registered_list — 등록일 기준 기간 내 멤버십 신규 등록 명단.
    실패 시 None(→ 미집계 표기, 0 위장 금지). 회원관리 페이지와 동일 소스(유효회원 시트 등록일자)."""
    try:
        data = _http_get(
            f"{GAS_URL}?action=member_registered_list&from={date_from}&to={date_to}", timeout=40
        )
        if not data.get("ok"):
            print(f"[WARN] member_registered_list ok=false: {data}")
            return None
        return data
    except Exception as e:
        print(f"[WARN] member_registered_list 수집 실패: {e}")
        return None


def fetch_lesson_registry(date_from: str, date_to: str) -> dict | None:
    """lesson_registry_list — 등록일 기준 기간 내 강습 신규 등록 명단(종목별, type 미지정=성인+유소년 전체).
    실패 시 None(→ 미집계 표기). 2026-06-27 원장 시드 이전 등록자는 원장 자체에 없어 과소집계될 수 있음."""
    try:
        data = _http_get(
            f"{GAS_URL}?action=lesson_registry_list&from={date_from}&to={date_to}", timeout=40
        )
        if not data.get("ok"):
            print(f"[WARN] lesson_registry_list ok=false: {data}")
            return None
        return data
    except Exception as e:
        print(f"[WARN] lesson_registry_list 수집 실패: {e}")
        return None


def _member_registered_summary(mr: dict | None) -> dict | None:
    """member_registered_list 원응답 → {total, by_program}. program 칼럼이 실제로 채워진 경우만 세부 분해,
    아니면 by_program={} (단일 버킷 "멤버십"으로 표기하도록 상위에서 처리)."""
    if mr is None:
        return None
    data = mr.get("data") or []
    by_program: dict[str, int] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        p = str(row.get("program") or "").strip()
        if p:
            by_program[p] = by_program.get(p, 0) + 1
    total = mr.get("count")
    if not isinstance(total, int):
        total = len(data)
    return {"total": total, "by_program": by_program}


def _lesson_registered_summary(lr: dict | None) -> dict | None:
    """lesson_registry_list 원응답 → {total, by_sport}. 종목 필드 그대로 집계(라벨 재해석 없음)."""
    if lr is None:
        return None
    data = lr.get("data") or []
    by_sport: dict[str, int] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        s = str(row.get("종목") or "").strip() or "기타"
        by_sport[s] = by_sport.get(s, 0) + 1
    total = lr.get("count")
    if not isinstance(total, int):
        total = len(data)
    return {"total": total, "by_sport": by_sport}


def _fmt_registration_detail_md(mr: dict | None, lr: dict | None, date_from: str, date_to: str) -> str:
    """§2 가산 섹션 — 신규 등록 상세(멤버십/강습종목) 마크다운 블록. 정직 꼬리표 필수 동봉."""
    mrs = _member_registered_summary(mr)
    lrs = _lesson_registered_summary(lr)
    lines = [f"**신규 등록 상세(멤버십/강습종목 · 등록일 기준 {date_from} ~ {date_to})**", ""]

    if mrs is None:
        lines.append("- 멤버십 신규: 미집계(수집 실패)")
    elif mrs["by_program"]:
        detail = " · ".join(f"{k} {v}건" for k, v in sorted(mrs["by_program"].items(), key=lambda kv: kv[1], reverse=True))
        lines.append(f"- 멤버십 신규: {mrs['total']}건 ({detail})")
    else:
        lines.append(f"- 멤버십 신규: {mrs['total']}건 (세부상품 칼럼 미기재 — 단일 버킷 집계)")

    if lrs is None:
        lines.append("- 강습 신규 등록(종목별): 미집계(수집 실패)")
    elif lrs["by_sport"]:
        detail = " · ".join(f"{k} {v}건" for k, v in sorted(lrs["by_sport"].items(), key=lambda kv: kv[1], reverse=True))
        lines.append(f"- 강습 신규 등록(종목별): {lrs['total']}건 — {detail}")
    else:
        lines.append("- 강습 신규 등록(종목별): 0건(표본 없음)")

    # [배140 · 2026-07-27 종료] 뮤지컬 배선 완료·교정 검증 통과(원장 2,515행 — 수영 1502·
    # 체조&트램폴린 371·골프 168 사고 전 값 복귀, 뮤지컬 11명 편입·등록일 전부 기준선).
    # 옛 '집계 밖'·'오염 신뢰불가' 꼬리표는 사실이 아니게 됐으므로 제거한다. 목록이 비면 줄도 없다.
    if LESSON_EXTERNAL_UNTRACKED:
        lines.append(
            f"- ⚠️ {' · '.join(LESSON_EXTERNAL_UNTRACKED)}: 팀시트가 없어 등록이 원장에 들어올 "
            "경로가 없음 — 문의는 들어오나 등록 수가 0으로 보임(집계 밖)"
        )
    # [배140 · 2026-07-27 실측] '누락'이라는 말이 오해를 낳았다. 실제로는 빠진 게 아니라
    # 날짜만 기준선(2000-01-01)으로 적재돼 있다 — 원장 2,504행 중 2,408행(96%)이 그 상태다.
    # 사람도 건수도 다 있고, '언제 등록했는지'만 모른다. 그래서 기간별 비교만 불가하고
    # 총계는 정상이다. 진짜 등록일은 팀시트에도 문의시트에도 없어(문의일≠등록일) 복원 불가.
    lines.append(
        "- ⚠️ 강습 등록 원장: 2026-06-27 시드 시점에 있던 2,408명(전체의 96%)은 등록일이 "
        "기준선(2000-01-01)으로 적재됨 — **인원·총계는 정상, '언제 등록했는지'만 미상**. "
        "따라서 기간별 증감 비교는 06-27 이후분에만 유효(총계 비교는 무방)"
    )
    lines.append("- ⚠️ 멤버십 세부상품 분해는 회원 DB 시트 칼럼(수강반종목/종목명/회원권/상품) 존재 여부에 종속")
    return "\n".join(lines)


def _registration_oneliner(mr: dict | None, lr: dict | None) -> str:
    """텔레그램 카드용 1줄(+미집계 각주) 요약 — 종목 브레이크다운 축약, 정직 꼬리표는 짧게 동봉."""
    mrs = _member_registered_summary(mr)
    lrs = _lesson_registered_summary(lr)
    parts = []
    parts.append("멤버십 미측정" if mrs is None else f"멤버십 {mrs['total']}건")
    if lrs is None:
        parts.append("강습 미측정")
    elif lrs["by_sport"]:
        rows = sorted(lrs["by_sport"].items(), key=lambda kv: kv[1], reverse=True)
        parts.append(f"강습 {lrs['total']}건(" + "·".join(f"{k} {v}" for k, v in rows) + ")")
    else:
        parts.append(f"강습 {lrs['total']}건")
    line1 = "· 신규 등록: " + " / ".join(parts)
    # [배140 · 2026-07-27 종료] 카드 꼬리표도 실측에 맞게. 남은 한계는 하나뿐 — 등록일 미상.
    # (뮤지컬 배선·교정 검증 통과. '외부관리·집계 밖'·'배포사고 오염' 표기는 사실이 아니게 됐다.)
    tail = []
    if LESSON_EXTERNAL_UNTRACKED:
        tail.append(f"{' · '.join(LESSON_EXTERNAL_UNTRACKED)}=팀시트 없어 집계 밖")
    tail.append("강습원장 96%는 등록일만 미상·인원은 정상")
    line2 = "· (" + " / ".join(tail) + ")"
    return line1 + "\n" + line2


# ── §5 콘텐츠 반응 성적표 (2026-07-20 배834 — reaction_scorecard.py 재사용, 신규 배관 없음) ──
# 발행 루프를 감싸는 상위 루프: 반응 파악(IG 도달·당근 조회/찜·카페 조회 실측) → 반응 없으면
# (저조) 개선안 자동 제안(반무인 — 실제 재발행·수정은 GM 승인 후). 2026-07-15 삭제된 클릭 집계를
# 되살리지 않고 이 실측 신호들로 대체(GM 지시). status/cmo_reaction_scorecard.json 재사용(신규 파일
# 아님, reaction_scorecard.scan()이 관리) — 이 브리프는 그 결과를 읽기만 한다.
def _fmt_reaction_scorecard_section() -> str:
    try:
        import reaction_scorecard as _rs
    except Exception as e:
        return f"_반응 성적표 모듈 로드 실패 — 미측정({e})_"
    try:
        cards = _rs._load_json(_rs.SCORECARD_PATH, {})
    except Exception as e:
        return f"_반응 성적표 로드 실패 — 미측정({e})_"
    if not cards:
        return "_반응 성적표 없음(reaction_scorecard.py --scan 미실행 또는 발행 콘텐츠 없음)._"
    items = sorted(cards.values(), key=lambda c: c.get("published_at") or "", reverse=True)[:10]
    lines = [
        "| 편 | IG 도달 | 판정 | 근거 |",
        "|---|---|---|---|",
    ]
    for c in items:
        ig = (c.get("channels") or {}).get("instagram", {})
        reach = ig.get("latest_reach") if ig.get("status") == "measured" else None
        reach_s = str(reach) if reach is not None else "미측정"
        title = str(c.get("title", "")).replace("|", "\\|")
        verdict = c.get("verdict", "판정보류")
        reason = str(c.get("verdict_reason", "")).replace("|", "\\|")
        lines.append(f"| {title} | {reach_s} | {verdict} | {reason} |")
    proposals = [c for c in items if c.get("verdict") == "저조" and c.get("improvement_proposal")]
    if proposals:
        lines.append("")
        lines.append("**저조 편 개선 제안(반무인 — GM 승인 후 실행, 자동 재발행 없음)**")
        for c in proposals:
            lines.append(f"- {c['title']}: {c['improvement_proposal']}")
    lines.append("")
    lines.append(
        "_참고: 채널별 문의→가입 전환(§2)은 누적 집계라 편별 귀속 불가 — 본 성적표에는 반영하지 "
        "않음. IG 좋아요·저장은 비공개 지표라 수집 불가(쓰지 않음). "
        "측정 대상: `scripts/reaction_scorecard.py`(status/cmo_reaction_scorecard.json)._"
    )
    return "\n".join(lines)


# ── 마크다운 조립 ──────────────────────────────────────────────────
def _fmt_content_table(items: list[dict]) -> str:
    if not items:
        return "_이번 주 공식(@wellperion) 발행 콘텐츠 없음._"
    lines = ["| 제목 | 채널 | 발행일 | 링크 |", "|---|---|---|---|"]
    for it in items:
        pub = (it.get("published_at") or "")[:10]
        url = it.get("post_url")
        link = f"[열기]({url})" if url else "— (URL 미회수)"
        title = str(it["title"]).replace("|", "\\|")
        lines.append(f"| {title} | {it['channel']} | {pub} | {link} |")
    return "\n".join(lines)


def _fmt_conversion_breakdown(fc: dict | None) -> str:
    if fc is None:
        return "_수집 실패 — 미측정(GAS 응답 없음)_"
    by_ch = fc.get("byChannel") or []
    if not by_ch:
        return "_해당 기간 문의 0건 — 미측정(표본 없음)_"
    rows = sorted(by_ch, key=lambda d: d.get("inquiries", 0), reverse=True)
    lines = ["| 채널(자기신고 유입경로) | 문의 | 전환 | 전환율 |", "|---|---|---|---|"]
    for d in rows:
        ch = d.get("channel", "기타")
        inq = d.get("inquiries", 0)
        conv = d.get("converted", 0)
        rate = d.get("rate")
        rate_s = f"{rate}%" if rate is not None else "—"
        lines.append(f"| {ch} | {inq}건 | {conv}명 | {rate_s} |")
    return "\n".join(lines)


# ── §4 자동 제안 초안 규칙 (2026-07-14 가산 — 배743 폐루프⑤ '평가 환류' 마지막 고리) ──────
# 정성 우선 + 측정 보조(스펙 Constraints). 표본 임계 미달(문의<5건)이면 자동 제안 불가로 정직 표기
# (클릭 기반 조기신호 폴백은 2026-07-15 클릭 지수 제거·GM 결정으로 삭제 — 억지 대체 금지).
# 성과 신호원 = funnel_conversion.byChannel(문의→전환, 배744 라이브 배선).
# ig_engagement_ledger(배31 반응원장)는 개인 계정(namuk) 전용 — 스펙 Constraints("공식 계정 전용·
# 개인 시리즈는 ship31 정성 소유·중복 금지")에 따라 본 공식 루프에는 의도적으로 섞지 않는다.
_MIN_INQUIRY_SAMPLE = 5  # 채널 랭킹(전환 기준) 발동 표본 임계 — 스펙 정직 가드 "편당 문의<5→미측정"과 정합

# funnel_conversion.byChannel 은 자기신고 유입경로 CANONICAL_CHANNELS 10버킷을 그대로 반환하는데
# (.deploy-funnel/Survey.js:111-112), 그중 '소개·지인'·'기존·과거 회원'·'오프라인'·'기타·미상' 은
# 콘텐츠를 발행할 채널이 아니다(다음 편을 "기존·과거 회원 채널"에 낼 수 없음) — 다음 편 채널 제안
# 랭킹에서 제외한다(실제 콘텐츠 발행 채널만 후보로 남김).
_NON_CONTENT_CHANNELS = {"소개·지인", "기존·과거 회원", "오프라인", "기타·미상"}


def _rank_channels_by_conversion(fc: dict | None) -> list[dict]:
    """funnel_conversion.byChannel 을 전환수 우선(전환 동률 시 문의수 보조) 내림차순 정렬.
    실제 콘텐츠 발행 채널이 아닌 자기신고 버킷(_NON_CONTENT_CHANNELS)은 제외. 실패/빈값이면 []."""
    if fc is None:
        return []
    by_ch = fc.get("byChannel") or []
    rows = [
        d for d in by_ch
        if isinstance(d, dict) and d.get("channel") not in _NON_CONTENT_CHANNELS
    ]
    return sorted(rows, key=lambda d: (d.get("converted", 0), d.get("inquiries", 0)), reverse=True)


def _fmt_next_episode_suggestion(fc: dict | None) -> str:
    """규칙(정성 우선 + 측정 보조, v1): 이번 주 총 문의가 _MIN_INQUIRY_SAMPLE 이상이면 전환 상위
    채널을 1순위로 제안(측정 꼬리표). 표본 부족/미측정이면 '자동 제안 불가'로 정직 표기(지어내지
    않음 — 2026-07-15 클릭 기반 조기신호 폴백 삭제·GM 결정, 억지 대체 금지).
    항상 참고용 초안 — 최종 판정·G1 등록은 아래 시모 슬롯(§4 placeholder)의 몫(GM 게이트 유지).
    v2(가중 점수 자동화) 발동 전 v1 정성 규칙 — .omc/specs/deep-interview-cmo-eval-feedback-loop.md
    'v1→v2 발동 트리거' 참조."""
    lines = ["**자동 제안 초안(규칙 기반 · 참고용 — 시모 최종 확정 필요)**", ""]

    ranked_conv = _rank_channels_by_conversion(fc)
    total_inq = sum(d.get("inquiries", 0) for d in ranked_conv)

    if ranked_conv and total_inq >= _MIN_INQUIRY_SAMPLE:
        top = ranked_conv[0]
        ch = top.get("channel", "기타")
        inq = top.get("inquiries", 0)
        conv = top.get("converted", 0)
        rate = top.get("rate")
        rate_s = f"{rate}%" if rate is not None else "—"
        lines.append(
            f"- 성과 상위 채널(전환 기준 · **측정**): {ch} — 문의 {inq}건 → 전환 {conv}명(전환율 {rate_s})"
        )
        lines.append(f"- 다음 편 제안 방향: {ch} 채널 우선 노출·유사 소재/후킹 반복 검토")
    else:
        lines.append(f"- 성과 상위 채널: **미측정** — 문의전환 표본 부족(<{_MIN_INQUIRY_SAMPLE}건) 또는 신호 없음")
        lines.append("- 다음 편 제안 방향: 자동 제안 불가 — 시모 정성 판정(§3)만으로 결정")

    lines.append("")
    lines.append(
        "_v1 정성 규칙(가중 점수화 아님) — 채널 랭킹만 자동, 소재·후킹 판단은 시모 몫. 개인 계정(namuk) "
        "반응원장(ship31)은 목적·계정이 달라 본 공식 루프에 섞지 않음(스펙 Constraints)._"
    )
    return "\n".join(lines)


def build_brief(items: list[dict], fc: dict | None,
                 mr: dict | None, lr: dict | None,
                 date_from: str, date_to: str, generated_at: datetime.datetime) -> str:
    week_label = f"{date_from} ~ {date_to}"

    parts = []
    parts.append(f"# 주간 마케팅 정리 보고 — {generated_at.strftime('%Y-%m-%d')}")
    parts.append("")
    parts.append(
        "> **v1 = 정성 우선 + 측정 보조.** 측정 안 되는 값은 `미측정`으로 정직 표기(가짜 수치 0)."
    )
    parts.append("")
    parts.append(f"집계 대상 주간: {week_label} · 범위: 공식 @wellperion 전용(개인 시리즈 namuk 제외 — ship31 별도 소유)")
    parts.append("")

    parts.append("## 1. 이번 주 공식 발행 콘텐츠")
    parts.append("")
    parts.append(_fmt_content_table(items))
    parts.append("")

    parts.append("## 2. 측정 보조 참고표")
    parts.append("")
    parts.append("| 신호 | 꼬리표 | 설명 |")
    parts.append("|---|---|---|")
    parts.append(
        "| 문의 전환(자기신고 유입경로) | **부분** | 2026-07-03 UTM→문의 하드 귀속 개통분부터 정확 — "
        "과거 문의는 소급 없이 자기신고 채널로만 집계(조인 아님) |"
    )
    parts.append("| 저장·좋아요 | **미측정** | 플랫폼 비공개(IG/네이버 API 미제공) — 수집 경로 없음 |")
    parts.append("| 카카오 | **연동 미비** | 발행 URL 추적 없음(카카오 채널 관리자 공개 id 미노출) |")
    parts.append("")
    parts.append("**문의 전환 상세(부분 — 위 설명 참조)**")
    parts.append("")
    parts.append(_fmt_conversion_breakdown(fc))
    parts.append("")

    parts.append(_fmt_registration_detail_md(mr, lr, date_from, date_to))
    parts.append("")

    parts.append(SECTION_3_HEADING)
    parts.append("")
    parts.append("_자동 채움 없음 — 시모가 위 표·콘텐츠를 보고 직접 판정해 채운다._")
    parts.append("")
    parts.append("- **Top(통한 콘텐츠):** ▸ (시모 정성 판정 — 통한 콘텐츠·이유)")
    parts.append("- **Bottom(안 통한 콘텐츠):** ▸ (시모 정성 판정 — 안 통한 콘텐츠·이유)")
    parts.append("")

    parts.append(SECTION_4_HEADING)
    parts.append("")
    parts.append(_fmt_next_episode_suggestion(fc))
    parts.append("")
    parts.append("▸ (시모: 통한 패턴 → 다음 편 후킹·소재·채널 제안 → G1 배 등록)")
    parts.append("")
    parts.append(
        "<!-- 참고용 힌트(자동 등록 아님) — 시모가 반영 확정 시 status/_queue.json 에 아래 shape 로 "
        "직접 append 하고 상태를 PENDING 으로 등록:\n"
        "{\n"
        '  "task_id": "CMO-<YYYY-MM-DD>-NEXT-EPISODE-PROPOSAL",\n'
        '  "clevel": "cmo",\n'
        '  "title": "[시모] <다음 편 제안 한 줄>",\n'
        '  "status": "PENDING",\n'
        '  "priority": "⛵돛단배",\n'
        f'  "enqueued_at": "{generated_at.strftime("%Y-%m-%d")}",\n'
        '  "note": "주간 마케팅 정리 보고(status/briefs/CMO-weekly-feedback-'
        f'{generated_at.strftime("%Y%m%d")}.md) Top 판정 근거로 제안"\n'
        "}\n"
        "-->"
    )
    parts.append("")

    parts.append(SECTION_5_HEADING)
    parts.append("")
    parts.append(_fmt_reaction_scorecard_section())
    parts.append("")

    return "\n".join(parts)


# ── daily 모드 (2026-07-06 가산) — 오늘(KST) 하루 스냅샷, Top/Bottom·다음편 제외 ──
def build_daily_brief(items: list[dict], fc: dict | None,
                       mr: dict | None, lr: dict | None,
                       date_str: str, generated_at: datetime.datetime) -> str:
    """daily 브리프 — weekly 의 §1/§2 형태를 그대로 재사용하되 기간을 오늘 하루로 좁히고,
    시모 정성 판정(§3/§4)은 daily 산출물에서 제외(그건 weekly 전용으로 유지 — 매일 채울 슬롯 아님)."""
    parts = []
    parts.append(f"# 일일 마케팅 정리 보고 — {generated_at.strftime('%Y-%m-%d')}")
    parts.append("")
    parts.append(
        "> **daily = 오늘(KST) 스냅샷.** 정성 Top/Bottom·다음 편 제안은 daily 에 없음(주간 보고 전용 유지). "
        "측정 안 되는 값은 `미측정`/`미집계`로 정직 표기."
    )
    parts.append("")
    parts.append(f"집계 대상: {date_str} (오늘) · 범위: 공식 @wellperion 전용(개인 시리즈 namuk 제외)")
    parts.append("")

    parts.append("## 1. 오늘 발행 콘텐츠")
    parts.append("")
    parts.append(_fmt_content_table(items))
    parts.append("")

    parts.append("## 2. 오늘 문의 → 전환(채널별)")
    parts.append("")
    parts.append(_fmt_conversion_breakdown(fc))
    parts.append("")

    parts.append("## 3. 오늘 신규 등록 상세(멤버십/강습종목)")
    parts.append("")
    parts.append(_fmt_registration_detail_md(mr, lr, date_str, date_str))
    parts.append("")

    return "\n".join(parts)


def build_daily_telegram_summary(items: list[dict], fc: dict | None,
                                  mr: dict | None, lr: dict | None,
                                  date_str: str, out_path: Path) -> str:
    """daily 텔레그램 카드 — ①발행 ②전환 ③등록상세 3줄+각주. send_telegram_summary() 재사용(발송 로직 신규 없음)."""
    lines = [f"오늘 마케팅 정리 — {date_str}", ""]
    lines.append(f"· ① 오늘 공식(@wellperion) 발행: {len(items)}건")

    if fc is None:
        lines.append("· ② 문의 전환: 미측정(수집 실패)")
    else:
        by_ch = fc.get("byChannel") or []
        if not by_ch:
            lines.append("· ② 문의 전환: 0건(표본 없음)")
        else:
            total_inq = sum(d.get("inquiries", 0) for d in by_ch)
            total_conv = sum(d.get("converted", 0) for d in by_ch)
            lines.append(f"· ② 문의 전환: {total_inq}건 문의 → {total_conv}명 전환(채널 {len(by_ch)}개, 부분측정)")

    reg_lines = _registration_oneliner(mr, lr).split("\n")
    lines.append("· ③ " + reg_lines[0].lstrip("· "))
    lines.append(reg_lines[1])
    return "\n".join(lines)


# ── 재생성 시 §3/§4 시모 정성 판정 보존 ─────────────────────────────
def _is_filled(section_text: str | None, placeholder_markers: list[str]) -> bool:
    """섹션 원문에 해당 섹션의 placeholder 마커가 하나도 없으면 시모가 채운 FILLED 로 판단.
    비어있음/None = 미채움(placeholder)."""
    if not section_text or not section_text.strip():
        return False
    return not any(marker in section_text for marker in placeholder_markers)


def _extract_section(md_text: str, heading: str, stop_headings: list[str]) -> str | None:
    """heading 줄부터 — stop_headings 중 가장 먼저 나오는 지점 직전(없으면 EOF)까지 — 원문 그대로 추출.
    heading 을 못 찾으면 None."""
    start = md_text.find(heading)
    if start == -1:
        return None
    end = len(md_text)
    for stop in stop_headings:
        idx = md_text.find(stop, start + len(heading))
        if idx != -1 and idx < end:
            end = idx
    return md_text[start:end].rstrip("\n")


def apply_preserved_judgment(fresh_md: str, out_path: Path) -> str:
    """오늘자 브리프 파일이 이미 있고 §3/§4 에 시모가 실제로 채운 내용이 있으면,
    새로 생성한 §3/§4 placeholder 를 그 기존 내용으로 되돌려(보존)한다.
    §1-2(자동 데이터)는 항상 fresh_md 값을 그대로 쓴다.
    - 기존 파일 없음 → fresh_md 그대로(정상 첫 실행/새 날짜).
    - 기존 §3/§4 가 아직 placeholder → fresh_md 그대로(정상 재생성).
    - 기존 §3/§4 가 FILLED → fresh_md 의 해당 구간을 기존 원문으로 치환(보존).
    - 파싱이 애매/실패 → 유실 방지 우선: 기존 파일의 §3~EOF 원문을 통째로 보존.
    """
    if not out_path.exists():
        return fresh_md
    try:
        existing_md = out_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 기존 브리프 읽기 실패({out_path.name}): {e} — 새 placeholder 로 진행")
        return fresh_md

    try:
        # §4 tail 은 §5(각 스코어카드, 2026-07-09 가산·항상 자동 재생성) 헤딩 직전에서 끊는다 —
        # 그래야 §4 보존/치환이 매번 새로 계산되는 §5 스코어카드를 잘못 집어삼키지 않는다.
        fresh_s3 = _extract_section(fresh_md, SECTION_3_HEADING, [SECTION_4_HEADING])
        fresh_s4_tail = _extract_section(fresh_md, SECTION_4_HEADING, [SECTION_5_HEADING])
        if fresh_s3 is None or fresh_s4_tail is None:
            print("[WARN] 신규 브리프에서 §3/§4 헤딩을 못 찾음(포맷 변경 의심) — 보존 병합 생략")
            return fresh_md

        exist_s3 = _extract_section(existing_md, SECTION_3_HEADING, [SECTION_4_HEADING])
        exist_s4_tail = _extract_section(existing_md, SECTION_4_HEADING, [SECTION_5_HEADING])

        merged = fresh_md

        if _is_filled(exist_s3, SECTION_3_PLACEHOLDER_MARKERS):
            merged = merged.replace(fresh_s3, exist_s3, 1)
            print("[INFO] §3(Top/Bottom 정성 판정) 기존 시모 판정 보존 — 재생성 스킵")
        else:
            print("[INFO] §3 기존 콘텐츠 없음/미채움 — placeholder 새로 생성")

        # §4 는 위 §3 치환으로 fresh_md 내용이 바뀌었을 수 있으니 merged 기준으로 재추출.
        # (§5 직전에서 끊어야 §5 스코어카드가 §4 보존 치환에 함께 삭제되지 않는다.)
        fresh_s4_tail_current = _extract_section(merged, SECTION_4_HEADING, [SECTION_5_HEADING])
        if _is_filled(exist_s4_tail, SECTION_4_PLACEHOLDER_MARKERS) and fresh_s4_tail_current is not None:
            merged = merged.replace(fresh_s4_tail_current, exist_s4_tail, 1)
            print("[INFO] §4(다음 편 제안) 기존 시모 제안 보존 — 재생성 스킵")
        else:
            print("[INFO] §4 기존 콘텐츠 없음/미채움 — placeholder 새로 생성")

        return merged
    except Exception as e:
        print(f"[WARN] §3/§4 보존 병합 중 예외: {e} — 유실 방지 위해 기존 §3~EOF 원문 통째 보존")
        try:
            idx_exist = existing_md.find(SECTION_3_HEADING)
            idx_fresh = fresh_md.find(SECTION_3_HEADING)
            if idx_exist != -1 and idx_fresh != -1:
                return fresh_md[:idx_fresh] + existing_md[idx_exist:]
        except Exception:
            pass
        return fresh_md


# ── 메인 ────────────────────────────────────────────────────────
def run_weekly(dry_run: bool = False):
    now = datetime.datetime.now()
    date_from = (now - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")

    print("[INFO] 시모 주간 마케팅 피드백 브리프 생성 시작")
    print(f"[INFO] 집계 대상 주간: {date_from} ~ {date_to}")

    items = load_official_recent(days=7, now=now)
    print(f"[INFO] 공식(@wellperion) 발행완료 콘텐츠 {len(items)}건 (최근 7일)")

    fc = fetch_funnel_conversion(date_from, date_to)
    mr = fetch_member_registered(date_from, date_to)
    lr = fetch_lesson_registry(date_from, date_to)

    brief_md = build_brief(items, fc, mr, lr, date_from, date_to, now)

    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEFS_DIR / f"CMO-weekly-feedback-{now.strftime('%Y%m%d')}.md"

    # §3/§4 는 시모가 이미 채웠으면 재생성으로 절대 덮어쓰지 않는다(2026-07-03 사고 재발방지).
    brief_md = apply_preserved_judgment(brief_md, out_path)

    out_path.write_text(brief_md, encoding="utf-8")

    print(f"[INFO] 브리프 생성 완료: {out_path}")
    print("─" * 60)
    print(brief_md)
    print("─" * 60)

    # 텔레그램 주간 요약 발송(문의알림방, best-effort) — 실패해도 위 브리프 저장은 이미 끝난 상태.
    summary_text = build_telegram_summary(items, fc, mr, lr, date_from, date_to, out_path)
    if dry_run:
        print("[INFO] --dry-run: 텔레그램 실제 발송 생략 — 카드 텍스트만 stdout 출력")
        print("─" * 60)
        print(summary_text)
        print("─" * 60)
    else:
        send_telegram_summary(summary_text)


def build_daily_card_text(now: datetime.datetime | None = None) -> str:
    """일일 마케팅 카드 본문만 생성(브리프 md 저장 포함, 텔레그램 발송 없음).
    daily_scheduler 병합 다이제스트가 호출한다. 실패해도 예외를 밖으로 던지지 않고
    1줄 폴백 문자열을 반환한다(문의 정리 다이제스트 전체가 죽지 않도록)."""
    if now is None:
        now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    try:
        print("[INFO] 시모 일일 마케팅 정리 카드 생성 시작")
        print(f"[INFO] 집계 대상: {date_str} (오늘)")

        # load_official_recent 는 7일 윈도우 기준 재사용 함수 — days=2 로 넉넉히 받아 오늘자만 필터링(신규 배관 없음).
        recent = load_official_recent(days=2, now=now)
        items = [it for it in recent if (it.get("published_at") or "")[:10] == date_str]
        print(f"[INFO] 공식(@wellperion) 발행완료 콘텐츠 {len(items)}건 (오늘)")

        fc = fetch_funnel_conversion(date_str, date_str)
        mr = fetch_member_registered(date_str, date_str)
        lr = fetch_lesson_registry(date_str, date_str)

        brief_md = build_daily_brief(items, fc, mr, lr, date_str, now)

        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = BRIEFS_DIR / f"CMO-daily-feedback-{now.strftime('%Y%m%d')}.md"
        out_path.write_text(brief_md, encoding="utf-8")

        print(f"[INFO] 일일 브리프 생성 완료: {out_path}")

        return build_daily_telegram_summary(items, fc, mr, lr, date_str, out_path)
    except Exception as e:
        print(f"[WARN] 일일 마케팅 카드 생성 실패: {e}")
        return f"오늘 마케팅 정리 — {date_str} (수집 실패)"


def run_daily(dry_run: bool = False):
    now = datetime.datetime.now()
    summary_text = build_daily_card_text(now)

    print("─" * 60)
    print(summary_text)
    print("─" * 60)

    if dry_run:
        print("[INFO] --dry-run: 텔레그램 실제 발송 생략 — 카드 텍스트만 stdout 출력")
    else:
        send_telegram_summary(summary_text)


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description="시모 마케팅 정리 브리프 생성기(weekly 기본 · daily 옵션)")
    p.add_argument("--mode", choices=["weekly", "daily"], default="weekly",
                    help="weekly(기본, 최근 7일) 또는 daily(오늘 하루)")
    p.add_argument("--dry-run", action="store_true",
                    help="브리프 생성·저장은 그대로 하되 텔레그램 실제 발송만 생략(카드 텍스트 stdout 출력)")
    return p.parse_args()


def main():
    args = _parse_args()
    if args.mode == "daily":
        run_daily(dry_run=args.dry_run)
    else:
        run_weekly(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
