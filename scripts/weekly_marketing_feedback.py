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
  - 측정 보조 신호: 문의Survey GAS(funnel) — click_stats(byUtmSource) · funnel_conversion(byChannel)

산출물: status/briefs/CMO-weekly-feedback-<YYYYMMDD>.md
  1) 이번 주 공식 발행 콘텐츠 표
  2) 측정 보조 참고표 (신호별 정직 꼬리표: 측정/부분/미측정/연동 미비)
  3) Top/Bottom 정성 판정 — 시모가 채우는 빈 슬롯(자동 채움 금지)
  4) 다음 편 제안 — 시모가 채우는 빈 슬롯(자동 G1 등록 금지, 제안 shape 힌트만 출력)

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
    "AKfycbzdwSCCSSJ6JXLDoWuo7HG0JmBM2iy10TujFQ_O5JbTjnWaN7gOk-ddA4IAvsNfelg0xA/exec"
)

OFFICIAL_ACCOUNT = "wellperion"  # 공식 계정 리터럴 — 정확 일치만 포함(namuk.wellperion 등 개인 계정 자동 배제).
PUBLISHED_STATUS = "발행완료"

# click_stats byUtmSource 코드 → 표기 라벨 (scripts/cta_utm.py CHANNEL_UTM 과 정합).
UTM_LABELS = {
    "직접/홈": "직접/홈 유입",
    "naver_blog": "네이버 블로그",
    "naver_cafe": "네이버 카페",
    "danggn": "당근마켓",
    "kakao": "카카오",
    "instagram": "인스타그램",
}

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

# ── 텔레그램 주간 요약 발송 (문의알림방 · 2026-07-03 GM go 라이브) ─────
ENV_PATH = _REPO_ROOT / "telegram_bot" / ".env"
TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"

# 역롤백: 이 값을 "" 로 바꾸면 즉시 미발송(브리프 생성·저장은 그대로 계속됨).
WEEKLY_SUMMARY_CHAT_ID = "-5516675010"  # 문의알림방(시모 담당) — 메모리 project_telegram_3room_split

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass


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


def build_telegram_summary(items: list[dict], cs: dict | None, fc: dict | None,
                            date_from: str, date_to: str, out_path: Path) -> str:
    """5~8줄 요약. 측정 실패는 '미측정', 정성 슬롯은 '시모 정리 대기'로 정직 표기(지어내지 않음)."""
    lines = [f"주간 마케팅 정리 — {date_from} ~ {date_to}", ""]
    lines.append(f"· 이번 주 공식(@wellperion) 발행: {len(items)}건")

    if cs is None:
        lines.append("· UTM 클릭(채널별): 미측정(수집 실패)")
    else:
        by_src = cs.get("byUtmSource") or {}
        if not by_src:
            lines.append("· UTM 클릭(채널별): 0건(표본 없음)")
        else:
            rows = sorted(by_src.items(), key=lambda kv: kv[1], reverse=True)
            lines.append(
                "· UTM 클릭(채널별): "
                + " · ".join(f"{UTM_LABELS.get(k, k)} {v}회" for k, v in rows)
            )

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
def fetch_click_stats(date_from: str, date_to: str) -> dict | None:
    """click_stats — 채널별 UTM 클릭. 실패 시 None(→ 미측정 표기, 0 위장 금지)."""
    try:
        data = _http_get(f"{GAS_URL}?action=click_stats&from={date_from}&to={date_to}", timeout=40)
        if not data.get("ok"):
            print(f"[WARN] click_stats ok=false: {data}")
            return None
        return data
    except Exception as e:
        print(f"[WARN] click_stats 수집 실패: {e}")
        return None


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


def _fmt_click_breakdown(cs: dict | None) -> str:
    if cs is None:
        return "_수집 실패 — 미측정(GAS 응답 없음)_"
    by_src = cs.get("byUtmSource") or {}
    if not by_src:
        return "_이번 주 클릭 로그 0건 — 미측정(표본 없음)_"
    rows = sorted(by_src.items(), key=lambda kv: kv[1], reverse=True)
    lines = ["| 채널(UTM) | 클릭 |", "|---|---|"]
    for k, v in rows:
        label = UTM_LABELS.get(k, k)
        lines.append(f"| {label} | {v}회 |")
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


def build_brief(items: list[dict], cs: dict | None, fc: dict | None,
                 date_from: str, date_to: str, generated_at: datetime.datetime) -> str:
    week_label = f"{date_from} ~ {date_to}"

    parts = []
    parts.append(f"# 주간 마케팅 정리 보고 — {generated_at.strftime('%Y-%m-%d')}")
    parts.append("")
    parts.append(
        "> **v1 = 정성 우선 + 측정 보조.** 측정 안 되는 값은 `미측정`으로 정직 표기(가짜 수치 0). "
        "자동 가중 점수는 UTM 데이터 축적 후(v2) 도입."
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
    parts.append("| UTM 클릭(채널별) | **측정** | 문의 CTA 클릭 로그 실집계(최근 7일) |")
    parts.append(
        "| 문의 전환(클릭↔문의 조인) | **부분** | 2026-07-03 UTM→문의 하드 귀속 개통분부터 정확 — "
        "과거 문의는 소급 없이 자기신고 채널로만 집계(조인 아님) |"
    )
    parts.append("| 저장·좋아요 | **미측정** | 플랫폼 비공개(IG/네이버 API 미제공) — 수집 경로 없음 |")
    parts.append("| 카카오 | **연동 미비** | 발행 URL·클릭 추적 없음(카카오 채널 관리자 공개 id 미노출) |")
    parts.append("")
    parts.append("**UTM 클릭 상세(최근 7일, 측정)**")
    parts.append("")
    parts.append(_fmt_click_breakdown(cs))
    parts.append("")
    parts.append("**문의 전환 상세(부분 — 위 설명 참조)**")
    parts.append("")
    parts.append(_fmt_conversion_breakdown(fc))
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

    # ── v2 훅 ────────────────────────────────────────────────────
    # UTM 데이터가 충분히 쌓이면(표본 확보 후) 아래 지점에 자동 가중 점수를 도입한다.
    #   가중 점수 = 전환×w1 + 클릭×w2 + (...)   ← 가중치는 데이터 축적 후 별도 설계(지금 미정)
    #   Top/Bottom 컷오프 = 가중 점수 상하위 N개 자동 산출(현재는 섹션3 시모 정성 판정으로 대체)
    # v1은 표본이 얇아(sparse) 자동 점수를 내면 과적합·오판 위험(스펙 Assumptions 참조) → 의도적 스텁.
    parts.append(
        "<!-- v2 훅: UTM 표본 축적 후 자동 가중 점수(전환×w1 + 클릭×w2 …) + Top/Bottom 자동 컷오프 도입. "
        "가중치·컷오프 로직은 지금(v1) 미구현 — 섹션3 은 시모 정성 판정으로 유지. -->"
    )
    parts.append("")

    return "\n".join(parts)


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
        fresh_s3 = _extract_section(fresh_md, SECTION_3_HEADING, [SECTION_4_HEADING])
        fresh_s4_tail = _extract_section(fresh_md, SECTION_4_HEADING, [])  # §4부터 EOF(참고 힌트·v2훅 포함)
        if fresh_s3 is None or fresh_s4_tail is None:
            print("[WARN] 신규 브리프에서 §3/§4 헤딩을 못 찾음(포맷 변경 의심) — 보존 병합 생략")
            return fresh_md

        exist_s3 = _extract_section(existing_md, SECTION_3_HEADING, [SECTION_4_HEADING])
        exist_s4_tail = _extract_section(existing_md, SECTION_4_HEADING, [])

        merged = fresh_md

        if _is_filled(exist_s3, SECTION_3_PLACEHOLDER_MARKERS):
            merged = merged.replace(fresh_s3, exist_s3, 1)
            print("[INFO] §3(Top/Bottom 정성 판정) 기존 시모 판정 보존 — 재생성 스킵")
        else:
            print("[INFO] §3 기존 콘텐츠 없음/미채움 — placeholder 새로 생성")

        # §4 는 위 §3 치환으로 fresh_md 내용이 바뀌었을 수 있으니 merged 기준으로 재추출.
        fresh_s4_tail_current = _extract_section(merged, SECTION_4_HEADING, [])
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
def main():
    now = datetime.datetime.now()
    date_from = (now - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    date_to = now.strftime("%Y-%m-%d")

    print("[INFO] 시모 주간 마케팅 피드백 브리프 생성 시작")
    print(f"[INFO] 집계 대상 주간: {date_from} ~ {date_to}")

    items = load_official_recent(days=7, now=now)
    print(f"[INFO] 공식(@wellperion) 발행완료 콘텐츠 {len(items)}건 (최근 7일)")

    cs = fetch_click_stats(date_from, date_to)
    fc = fetch_funnel_conversion(date_from, date_to)

    brief_md = build_brief(items, cs, fc, date_from, date_to, now)

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
    summary_text = build_telegram_summary(items, cs, fc, date_from, date_to, out_path)
    send_telegram_summary(summary_text)


if __name__ == "__main__":
    main()
