"""AI 시리즈 다음 편 자동 제작 → M5 검수큐 등록 (제작만 · 발행 절대 자동 아님)

GM 정정 지시(2026-06-04, AI CTO 위임). 매일 07:30 예약작업으로 가동되어
로드맵상 '다음 예정 편'을 시모(헤드리스 claude)가 GM 1인칭 보이스로 초안 제작 → 빌드 →
register_publish 로 M5 검수큐(status='검수대기') 적재 → 로드맵 행 '제작완료(자동생성)' 자동 표시 →
send_review_card 로 GM 텔레그램에 [✅승인]/[❌반려] 버튼 카드 발송까지 자동. 그 뒤 GM 이 M5 에서
슬라이드 검토 → 텔레그램 카드 [✅승인] 탭 → 봇 pub: 콜백이 그 순간 즉시 발행(무폴링). 발행 게이트는
GM 텔레그램 탭(수동 승인) 불변 — 스케줄 발행 없음.

★ 안전 원칙 (절대 위반 금지):
  - 자동 발행 없음. 이 스크립트는 status='검수대기' 적재 + [승인] 버튼 카드 발송까지만 한다.
  - 발행 트리거는 오직 GM 텔레그램 [✅승인] 탭(봇 pub: 콜백). review_queue 폴링 감시기 부활 금지.
  - 로드맵 '기획예정' 소진 시 생성 금지 + 텔레그램 1줄 경고 후 종료(쓰레기/중복 생성 금지).
  - 생성 실패(로드맵 파싱·헤드리스 호출·빌드 등) 시 텔레그램 경고 + 중단. 불량 항목 M5 미등록.

설계: 결정적(deterministic) 작업 = 이 스크립트(로드맵 파싱·다음편 선정·폴더 스캐폴드·소진 가드·
      텔레그램). 창의적(copy) 작업 = 시모(헤드리스 claude)에게 build_slides.py 1개만 작성 위임.
      그 build_slides.py 가 기존 편 표준(6장·logo_style='symbol'·마지막 장 편별 제목(#11+)·
      저장/댓글/팔로우 CTA·litt.ly 금지)을 그대로 따르고, 끝에서 register_publish(M5 등록)를 호출한다.

실행:
  제작:                 python scripts\\ig_series_producer.py
  로직만(테스트):        python scripts\\ig_series_producer.py --dry-run   (헤드리스 호출·빌드 안 함)
  다음편 선정만 출력:     python scripts\\ig_series_producer.py --plan-only

종료코드: 0=성공(또는 소진으로 정상 종료) / 1=오류(텔레그램 경고 발송됨).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 콘솔 인코딩 하드닝 (cp949 콘솔에서 대시·이모지 print 시 죽지 않게)
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconf = getattr(_stream, "reconfigure", None) if _stream is not None else None
    if _reconf is not None:
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
ROADMAP = ROOT / "instagram" / "_AI시리즈_로드맵.md"
INSTAGRAM_DIR = ROOT / "instagram"
# AI 시리즈(개인계정 namuk) 편들은 instagram/namuk.wellperion/ 하위에 거주(회사 콘텐츠와 분리).
# 폴더 스캔(중복 가드)·신규편 생성·참고 빌더 모두 이 디렉터리를 기준으로 한다(2026-06-12 정리).
NAMUK_DIR = INSTAGRAM_DIR / "namuk.wellperion"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ENV_PATH = ROOT / "telegram_bot" / ".env"

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"

PLANNED_STATUS = "기획예정"  # 로드맵 편별 표에서 '아직 제작 안 한 다음 예정 편' 상태값

# 마지막 장 시그니처 슬로건 고정 (2026-06-04 GM 지시 — 전 편 공통 SOP, 로드맵 ★섹션)
SIGNATURE_SLOGAN = "AI를 다루는 대표가\n살아남는다"


# ─────────────────────────────────────────────────────────────────────────────
# 텔레그램 (토큰 stdout 노출 금지 — 메모리 feedback_telegram_token_env_key)
# ─────────────────────────────────────────────────────────────────────────────
def _load_env_value(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드."""
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


def _load_telegram_token() -> str:
    return _load_env_value(TELEGRAM_TOKEN_ENV_KEY)


TELEGRAM_CHAT_ID: str = _load_env_value(TELEGRAM_CHAT_ID_ENV_KEY)  # telegram_bot/.env SSOT


def telegram(message: str) -> None:
    """1줄 텔레그램 보고. 실패해도 죽지 않음(토큰 trace 미출력)."""
    token = _load_telegram_token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 보고 생략")
        return
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[INFO] 텔레그램 보고 {'성공' if resp.status == 200 else '실패'}")
            log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="ig_series_producer.telegram", ok=(resp.status == 200), kind="sendMessage")
    except Exception:
        log_outbound(message, chat_id=TELEGRAM_CHAT_ID, source="ig_series_producer.telegram", ok=False, kind="sendMessage")
        print("[WARN] 텔레그램 보고 실패 (토큰 trace 노출 방지)")


# ─────────────────────────────────────────────────────────────────────────────
# 로드맵 파싱 + 다음 편 선정
# ─────────────────────────────────────────────────────────────────────────────
class RoadmapError(Exception):
    """로드맵 파싱·구조 이상 (상위에서 텔레그램 경고 + 중단)."""


def parse_roadmap_episodes(text: str) -> list[dict]:
    """편별 로드맵 표 행을 파싱해 dict 리스트 반환.

    표 헤더: | # | 일자 | 폴더(코드명) | 제목 | 핵심메시지(1줄) | 상태 |
    구분선(|---|...) 과 헤더 행은 제외. 숫자(또는 '8(피날레)' 같은 형태)로 시작하는 행만 채택.
    반환 항목: {"num": int, "num_raw": str, "date": str, "folder": str,
               "title": str, "message": str, "status": str}
    """
    episodes: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        # 구분선 제외
        if set(line.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        num_raw = cells[0]
        # 헤더 행('#') 제외 / 첫 셀이 숫자로 시작하는 행만 채택
        m = re.match(r"^\s*(\d+)", num_raw)
        if not m:
            continue
        episodes.append(
            {
                "num": int(m.group(1)),
                "num_raw": num_raw,
                "date": cells[1],
                "folder": cells[2],
                "title": cells[3],
                "message": cells[4],
                "status": cells[5],
            }
        )
    if not episodes:
        raise RoadmapError("편별 로드맵 표에서 유효한 편 행을 1건도 못 찾음 (표 구조 변경 의심)")
    return episodes


# ─────────────────────────────────────────────────────────────────────────────
# 시즌2 규칙 단일 출처 읽기 (★ 재발방지 — 2026-06-15)
# 로드맵 §2.6 의 ```producer-season-config 펜스 블록(KEY: 값)을 읽어 dict 반환.
# 시즌 라벨·도입 캡션처럼 '변하는 규칙'을 로드맵에서만 관리 → producer 손 동시수정 폐지.
# 파싱 실패·블록 부재 시 빈 dict(시즌 규칙 생략 — 안전 폴백, 기존 §2.5 규칙은 불변).
# ※ 이 블록은 표(|...|)가 아니므로 parse_roadmap_episodes 파서에 전혀 영향 없음.
# ─────────────────────────────────────────────────────────────────────────────
def parse_season_config(text: str) -> dict[str, str]:
    """로드맵의 ```producer-season-config 펜스 블록을 KEY: 값 dict 로 파싱."""
    cfg: dict[str, str] = {}
    in_block = False
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not in_block:
            if stripped.startswith("```") and "producer-season-config" in stripped:
                in_block = True
            continue
        # 블록 안
        if stripped.startswith("```"):
            break  # 펜스 종료
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key:
            cfg[key] = val
    return cfg


def load_season_config() -> dict[str, str]:
    """로드맵 파일에서 시즌 설정 읽기(best-effort). 실패해도 빈 dict 반환(폴백)."""
    try:
        return parse_season_config(ROADMAP.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] 시즌 설정 읽기 실패 — 시즌 라벨 생략(기존 규칙 유지): {exc}")
        return {}


def season_label_block(ep: dict, cfg: dict[str, str]) -> str:
    """이 편에 적용할 시즌2 라벨·도입 캡션 지시문 생성(로드맵 단일출처에서 조립).

    cfg 가 비었거나 키가 없으면 빈 문자열 → 프롬프트에서 시즌 규칙 줄 자체가 생략(안전).
    """
    label = cfg.get("SEASON2_LABEL", "").strip()
    if not label:
        return ""  # 시즌 설정 부재 — 기존 동작 유지
    parts: list[str] = []
    # 라벨 실제 문자열을 항상 먼저 명시(시모가 어떤 텍스트인지 알도록), 이어서 로드맵 규칙 문구.
    parts.append(f"- 시즌2 라벨 텍스트 = \"{label}\" (표지 부제/eng_sub 자리에 이 문자열을 넣는다).")
    label_rule = cfg.get("SEASON2_LABEL_RULE", "").strip()
    if label_rule:
        parts.append(f"- {label_rule}")
    # 도입 캡션: 자동제작 시즌2 첫 편(SEASON2_INTRO_FIRST_NUM)에서만
    intro_caption = cfg.get("SEASON2_INTRO_CAPTION", "").strip()
    intro_first = cfg.get("SEASON2_INTRO_FIRST_NUM", "").strip()
    if intro_caption and intro_first.isdigit() and ep["num"] == int(intro_first):
        intro_rule = cfg.get("SEASON2_INTRO_RULE", "").strip()
        parts.append(
            f"- 이 편은 시즌2 도입 첫 편 — CAPTION 첫 줄에 다음 한 줄을 그대로 넣어라: \"{intro_caption}\""
            + (f" ({intro_rule})" if intro_rule else "")
        )
    elif intro_caption and intro_first.isdigit():
        parts.append("- 시즌2 도입 캡션은 첫 편 전용 — 이 편엔 라벨만 유지하고 도입 멘트는 넣지 마라(간결 원칙).")
    hashtag = cfg.get("SEASON2_HASHTAG", "").strip()
    if hashtag:
        parts.append(f"- 캡션 해시태그에 {hashtag} 1개를 권장 풀에 추가(시즌1과 검색·묶음 구분).")
    # 시즌2 실전편 표준 3비트(문제→AI해결→자동화) — 로드맵 §2.6 단일출처. 카드 없는 편의 기본 골격.
    structure_rule = cfg.get("SEASON2_STRUCTURE_RULE", "").strip()
    if structure_rule:
        parts.append(f"- {structure_rule}")
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 편별 기획 카드 단일 출처 읽기 (★ 엉성함·매일 재기획 차단 — 2026-06-16)
# 로드맵 §5.1 의 ```producer-episode-card-{num} 펜스 블록(KEY: 값)을 읽어 편별 dict 반환.
# producer 가 '제목+1줄'만 받아 6장을 매일 즉석 생성하던 문제 → 편별 6장 비트·연결·현실가드를
# 로드맵에서 확정해 읽어 '제작만' 하게 한다(INC-001 동일 철학: 로드맵 단일출처, 코드는 읽기만).
# 카드 부재 시 빈 dict → 기존 1줄 동작 폴백(안전). 표(|...|)가 아니므로 표 파서에 영향 없음.
# ─────────────────────────────────────────────────────────────────────────────
def parse_episode_cards(text: str) -> dict[int, dict[str, str]]:
    """로드맵의 ```producer-episode-card-{num} 펜스 블록들을 {num: {KEY: 값}} 으로 파싱."""
    cards: dict[int, dict[str, str]] = {}
    cur_num: int | None = None
    cur: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if cur_num is None:
            m = re.match(r"^```producer-episode-card-(\d+)\s*$", stripped)
            if m:
                cur_num = int(m.group(1))
                cur = {}
            continue
        # 블록 안
        if stripped.startswith("```"):
            cards[cur_num] = cur
            cur_num = None
            cur = {}
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key:
            cur[key] = val
    return cards


def load_episode_card(num: int) -> dict[str, str]:
    """로드맵에서 해당 편 기획 카드 읽기(best-effort). 실패·부재 시 빈 dict(1줄 폴백)."""
    try:
        return parse_episode_cards(ROADMAP.read_text(encoding="utf-8")).get(num, {})
    except Exception as exc:
        print(f"[WARN] 편별 카드 읽기 실패 — 1줄 핵심메시지로 폴백: {exc}")
        return {}


def episode_card_block(card: dict[str, str]) -> str:
    """편별 카드 dict → 제작 프롬프트 주입 지시문. 카드 비면 빈 문자열(기존 동작)."""
    if not card:
        return ""
    lines: list[str] = []
    hook = card.get("HOOK", "").strip()
    if hook:
        lines.append(f"- 후크(첫인상 한 줄): {hook}")
    cp = card.get("CONNECT_PREV", "").strip()
    if cp:
        lines.append(f"- 어제와의 연결(직전 편 잇기 — 반복 말고 전진): {cp}")
    cn = card.get("CONNECT_NEXT", "").strip()
    if cn:
        lines.append(f"- 내일로의 다리(다음 편 예고 여운): {cn}")
    slide_keys = [k for k in card if k.startswith("SLIDE_")]

    def _slide_no(k: str) -> int:
        mm = re.search(r"SLIDE_(\d+)", k)
        return int(mm.group(1)) if mm else 99

    slide_keys.sort(key=_slide_no)
    if slide_keys:
        lines.append("- 슬라이드 장별 비트(이 순서·내용대로 '제작만' — 주제·소재 임의 변경 금지):")
        for k in slide_keys:
            label = k.replace("SLIDE_", "").replace("_", " ").strip()
            lines.append(f"  · {label}장: {card[k]}")
    q = card.get("QUESTION", "").strip()
    if q:
        lines.append(f"- 편별 질문(마지막 장·캡션 저장/댓글 CTA의 (이번 편 질문) 자리에 그대로): {q}")
    rg = card.get("REALITY_GUARD", "").strip()
    if rg:
        lines.append(f"- ★현실 가드(반드시 준수): {rg}")
    return "\n".join(lines)


# 이미 제작/검수/발행/폐기된 편으로 판정할 상태 키워드(부분일치) — 재선정 차단
# (어제·오늘 #7 재탕 사고 방지: '기획예정' 완전일치 + 아래 키워드 미포함 + 폴더 미존재 3중 가드)
_DONE_STATUS_KW = ("제작완료", "검수대기", "검수 대기", "발행완료", "폐기", "보류")


def _episode_already_produced(ep: dict) -> bool:
    """이 편 번호(AI{num})로 이미 제작된 폴더가 instagram/namuk.wellperion/ 아래에 있으면 True.

    make_folder_slug 가 매 가동 '오늘 날짜'로 폴더를 새로 만들기 때문에, 같은 편을 다른
    날짜로 재제작하는 사고를 막으려면 날짜와 무관하게 'AI{num}_' 패턴 폴더 존재로 판정한다.

    ★ 판정 기준: 폴더 안에 build_slides.py 가 있어야 '제작됨'으로 간주.
    기획_초안.md 만 있는 사전 기획 폴더(GM 수동 생성)는 미제작으로 통과시켜
    producer 가 정상적으로 #10 을 선정할 수 있도록 한다(2026-06-08 버그 수정).
    폐기 폴더(_폐기_DEPRECATED.md 보유)는 build_slides.py 유무와 무관하게 제작됨으로 간주.
    """
    try:
        marker = f"_AI{ep['num']}_"
        scan_dir = NAMUK_DIR if NAMUK_DIR.is_dir() else INSTAGRAM_DIR
        for child in scan_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not (marker in name or name.endswith(f"_AI{ep['num']}")):
                continue
            # 폐기 폴더는 build_slides 유무 무관하게 '제작됨' (재선정 차단)
            if (child / "_폐기_DEPRECATED.md").exists():
                return True
            # build_slides.py 가 있어야 실제 제작된 폴더
            if (child / "build_slides.py").exists():
                return True
    except Exception:
        pass
    return False


def pick_next_episode(episodes: list[dict]) -> dict | None:
    """진짜 미제작 '기획예정' 편 중 번호가 가장 빠른 1건 반환. 없으면 None (소진).

    3중 가드(2026-06-07 시토 — #7 재탕 사고 수정):
      ① 상태 == '기획예정' (완전일치)
      ② 상태에 제작완료/검수대기/발행완료/폐기/보류 키워드 미포함(안전망)
      ③ 해당 편(AI{num}) 제작 폴더가 instagram/ 아래에 아직 없음
    """
    candidates: list[dict] = []
    for e in episodes:
        st = e["status"]
        if st != PLANNED_STATUS:
            continue
        if any(kw in st for kw in _DONE_STATUS_KW if kw != PLANNED_STATUS):
            continue
        if _episode_already_produced(e):
            print(
                f"[INFO] #{e['num']} 은 '기획예정'이나 제작 폴더가 이미 존재 — 재선정 스킵(중복 차단)."
            )
            continue
        candidates.append(e)
    if not candidates:
        return None
    candidates.sort(key=lambda e: e["num"])
    return candidates[0]


def prev_published_episode(episodes: list[dict], next_num: int) -> dict | None:
    """다음 편 직전(번호 기준 바로 앞) 편 — 중복 점검 컨텍스트용. 없으면 None."""
    befores = [e for e in episodes if e["num"] < next_num]
    if not befores:
        return None
    befores.sort(key=lambda e: e["num"])
    return befores[-1]


# ─────────────────────────────────────────────────────────────────────────────
# 폴더 코드명 / slug 생성
# ─────────────────────────────────────────────────────────────────────────────
def make_folder_slug(ep: dict) -> str:
    """제작용 폴더명(코드명) 생성. 예: 260605_AI6_작은가게AI팀

    로드맵 폴더 셀이 '(예정)' 등 placeholder 이므로, 제작일(오늘) + AI{num} + 제목 압축으로 생성.
    한글/영문/숫자만 남기고 공백 제거(파일시스템 안전).
    """
    today = datetime.now().strftime("%y%m%d")
    title = ep["title"]
    # 제목에서 콜론 앞부분(한글 헤드) 우선 사용
    head = title.split(":")[0].split("—")[0].strip()
    # 파일시스템 안전: 한글·영숫자만
    safe = re.sub(r"[^0-9A-Za-z가-힣]", "", head)[:14] or f"AI{ep['num']}편"
    return f"{today}_AI{ep['num']}_{safe}"


def make_queue_id(ep: dict) -> str:
    """이 편의 review_queue id 를 결정적으로 재구성.

    ★ build_producer_prompt 의 QUEUE_ID 공식과 반드시 동일해야 한다(시모가 쓴 build_slides.py
    의 queue_id 와 일치해야 카드를 정확히 그 엔트리로 발송·발행 가능). 공식 변경 시 양쪽 동시 수정.
    예: #6 「작은 가게도 AI 팀을 가질 수 있다」 → CMO-2026-06-04-AI6-작은가게도AI팀을가
    """
    head = re.sub(r"[^0-9A-Za-z가-힣]", "", ep["title"].split(":")[0])[:10]
    return f"CMO-{datetime.now().strftime('%Y-%m-%d')}-AI{ep['num']}-{head}"


# ─────────────────────────────────────────────────────────────────────────────
# 시모(헤드리스 claude) 호출 — build_slides.py 작성 위임
# ─────────────────────────────────────────────────────────────────────────────
def _find_claude() -> str:
    """claude CLI 경로 탐색 (telegram_bot/bot.py _find_claude 동일 전략)."""
    import shutil as _shutil

    for name in ("claude.cmd", "claude.exe", "claude"):
        p = _shutil.which(name)
        if p:
            return p
    for cand in (
        Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
        Path.home() / "AppData" / "Roaming" / "npm" / "claude",
    ):
        if cand.exists():
            return str(cand)
    return "claude"


def build_producer_prompt(ep: dict, prev: dict | None, folder_slug: str) -> str:
    """시모에게 보낼 제작 지시 프롬프트. build_slides.py 1개 파일만 작성하도록 강제.

    ★ 시즌2 라벨·도입 캡션 등 '변하는 시즌 규칙'은 로드맵 §2.6(producer-season-config)에서
    읽어 주입한다(2026-06-15 재발방지). 코드 하드코딩 중복 제거 → 로드맵 단일출처.
    """
    folder_path = NAMUK_DIR / folder_slug
    ref_build = NAMUK_DIR / "260604_AI5_깨진환상들" / "build_slides.py"
    prev_block = (
        f"- 직전 편(#{prev['num']}): 제목「{prev['title']}」 / 핵심메시지「{prev['message']}」\n"
        f"  → 이 편은 직전 편을 '이어가는' 편이다. 같은 말을 반복하지 말고 한 걸음 전진시키되,\n"
        f"    어제(#{prev['num']})→오늘(#{ep['num']})이 하나의 흐름으로 자연스럽게 연결되게 하라\n"
        f"    (아래 '확정 기획 카드'에 어제와의 연결 지시가 있으면 그걸 최우선으로 따른다)."
        if prev
        else "- 직전 편 없음(이 편이 첫 편)."
    )
    # 시즌2 규칙(로드맵 단일출처에서 읽음). 설정 부재 시 빈 문자열 → 규칙 줄 생략(안전 폴백).
    season_rules = season_label_block(ep, load_season_config())
    season_block = (
        f"\n## 시즌2 규칙 (로드맵 §2.6 단일출처 — 자동 주입)\n{season_rules}\n"
        if season_rules
        else ""
    )
    # 편별 확정 기획 카드(로드맵 §5.1 단일출처). 카드 부재 시 빈 문자열 → 기존 1줄 동작(폴백).
    card_rules = episode_card_block(load_episode_card(ep["num"]))
    card_block = (
        f"\n## 이번 편 확정 기획 카드 (로드맵 §5.1 단일출처 — 이 비트대로 '제작만' 한다)\n"
        f"아래는 이미 확정된 편별 설계다. 6장 비트·어제/내일 연결·현실 가드를 그대로 따라 제작하라.\n"
        f"(이 카드가 위 '핵심메시지 1줄'보다 구체적이다 — 카드와 1줄이 충돌하면 카드를 따른다.)\n{card_rules}\n"
        if card_rules
        else ""
    )
    return f"""너는 웰페리온 AI CMO(시모)다. GM 개인계정 namuk.wellperion 의 'AI A~Z' 연재 다음 편을 제작한다.
GM 1인칭 진솔 보이스(생각 리더십)로, 초등학생도 이해할 일상어로 쓴다. 광고·멤버십 모집 톤 금지.

## 이번 편 — 로드맵에서 확정된 주제다 (재기획·주제 변경 금지)
- 번호: #{ep['num']}
- 제목(확정): {ep['title']}
- 핵심메시지(확정·1줄): {ep['message']}
★ 너의 일 = 위 '확정 제목·핵심메시지'를 6장으로 **제작**하는 것이다. **기획이 아니다.**
  제목·주제·핵심메시지를 네 판단으로 바꾸거나 다른 소재로 갈아끼우지 마라. 위 주제 그대로 만든다.
  (초안 아님 — 로드맵 §4.1에서 확정된 편이다. 더 좋은 아이디어가 떠올라도 이 편은 위 주제로만 만든다.)
{prev_block}
{card_block}
## 산출물 (단 하나의 파일만 작성)
파일 경로: {folder_path / "build_slides.py"}
참고 표준(똑같은 구조·함수·register_publish 호출을 그대로 따른다): {ref_build}
  ※ 단, 참고 파일의 마지막장 슬로건·CTA 문구는 구버전(#1~10)이다 — 그건 따르지 말고 아래 규칙 3·4의 정본(편별 제목 + 저장·댓글·팔로우)을 적용하라.

## 절대 준수 (위반 시 불량 — M5 등록 안 됨)
1. 정확히 6장. SLIDES 리스트에 본문 5장(1장 표지 + 4장 본문) + main()에서 마지막 6장(시그니처)을 별도 생성.
2. 모든 슬라이드 logo_style="symbol" (개인계정 W 심볼만).
3. 마지막 6장 kor_title = 이번 편 마무리 제목(편별 자유 · #11+ 실전 노선). 과거 #1~#10 고정 슬로건("AI를 다루는 대표가 살아남는다")을 #11+ 에 쓰지 마라(폐지됨).
4. 마지막 장 body·캡션 마무리 CTA = 저장·댓글·팔로우 정본(2026-06-10 GM 개정). 'DM 주세요'·'함께 성장합시다'·문의 URL 절대 금지. litt.ly 금지.
   - 마지막 장 body 템플릿(3줄 고정, (이번 편 질문)만 편별로 채움):
     "나중에 따라하려면 저장\\n(이번 편 질문) 댓글로 알려주세요\\n이런 AI 활용기 계속 보고 싶으면 팔로우"
   - 캡션 마무리 템플릿(해시태그 줄 직전):
     "📌 나중에 따라하려면 저장\\n💬 (이번 편 질문)? 댓글로 알려주세요\\n👀 이런 AI 활용기 계속 보고 싶으면 팔로우"
5. CAPTION 마무리도 시그니처 슬로건과 모순 없게. 해시태그 포함.
6. compose_text_slide(main 프리셋) 외 디자인 코드 재발명 금지. build_montage 함수도 참고 파일 그대로 복사.
7. QUEUE_ID="CMO-{datetime.now().strftime('%Y-%m-%d')}-AI{ep['num']}-{re.sub(r'[^0-9A-Za-z가-힣]', '', ep['title'].split(':')[0])[:10]}",
   slug="{folder_slug}", title="AI #{ep['num']}편 — (이번 편 한글 요약)(개인계정)",
   channel="인스타그램 (namuk.wellperion)", account="namuk.wellperion".
8. FOLDER = ROOT / "instagram" / "namuk.wellperion" / "{folder_slug}" 로 설정.
9. 웰페리온은 1인·소상공인·작은가게가 아니라 조직(대표+직원+실무팀)을 갖춘 하이엔드 프라이빗 스포츠클럽이다. 화자는 '조직을 이끄는 리더' 1인칭. '혼자/작은가게도/1인기업/소상공인' 프레임 금지.
10. MENTIONS = [] (멘션 자동 삽입 금지). 실제 협업 상대가 있는 편에만 GM 지정 시 추가.
11. 해시태그 금지: #소상공인 #1인기업 #작은가게. 권장 풀: #AI #AI활용 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온 등 실체에 맞는 것만.
12. CAPTION 본문·CTA 어디에도 무관한 @계정 멘션 줄을 넣지 마라.
13. 글 간결·핵심만(2026-06-13 GM) — 군더더기·미사여구·반복·설명 늘이기 금지. 짧은 문장, 한 슬라이드 한 메시지. 캡션도 핵심만(분량 채우기 금지).
14. 현실 반영(2026-06-13 GM) — 소재는 웰리(AI CEO)·AI C-Level과 실제로 한 작업에서만 가져온다(시간대별 자동보고·문의 반응 대시보드·M5 검수 파이프라인·항로 보드 등 진짜 한 일). 추상론·가상 시나리오·과장 금지. 안 해본 기능을 지어내지 마라. — 단, 이는 위 '확정 주제'를 **현실 사례로 설명**하라는 뜻이지, 주제를 다른 작업으로 바꾸라는 뜻이 아니다(주제는 위에서 고정).
{season_block}
## 작업 방법
- Write 도구로 위 build_slides.py 파일 하나만 생성하라. 다른 파일은 만들지 마라. 발행/커밋/push 하지 마라.
- 코드만 작성한다. build_slides.py 실행은 이 호출 밖(상위 스케줄러)에서 한다.
- 완료하면 "BUILD_SLIDES_WRITTEN: {folder_path / 'build_slides.py'}" 한 줄을 마지막에 출력하라.
"""


def invoke_simo_producer(ep: dict, prev: dict | None, folder_slug: str, timeout: int = 600) -> str:
    """헤드리스 claude(시모) 호출 → build_slides.py 작성. 반환: 응답 텍스트.

    실패(비정상 종료·예외) 시 RuntimeError 로 상위에 전파 → 텔레그램 경고 + 중단.
    """
    claude_bin = _find_claude()
    prompt = build_producer_prompt(ep, prev, folder_slug)
    args = [
        claude_bin,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]
    try:
        # Windows .cmd 는 exec 불가 → shell 모드 (bot.py run_claude 와 동일 전략)
        if claude_bin.lower().endswith(".cmd") or os.name == "nt":
            shell_cmd = subprocess.list2cmdline(args)
            proc = subprocess.run(
                shell_cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                timeout=timeout,
                shell=True,
            )
        else:
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                timeout=timeout,
            )
    except FileNotFoundError:
        raise RuntimeError(f"claude CLI 를 찾을 수 없음 ({claude_bin})")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"시모 헤드리스 호출 타임아웃({timeout}s)")
    except Exception as exc:
        raise RuntimeError(f"시모 호출 subprocess 예외: {type(exc).__name__}: {exc}")

    if proc.returncode != 0:
        err = (proc.stderr or "")[:600]
        raise RuntimeError(f"시모 비정상 종료 exit={proc.returncode} stderr={err}")

    raw = proc.stdout or ""
    # output-format=json → result 추출 (실패해도 원문 반환)
    try:
        import json

        data = json.loads(raw)
        return data.get("result") or data.get("response") or raw
    except Exception:
        return raw


# ─────────────────────────────────────────────────────────────────────────────
# 로드맵 자동 갱신 (생산·등록 성공 시 해당 편 행 상태 → 제작완료, 다음날 다음 편 선정)
# ─────────────────────────────────────────────────────────────────────────────
PRODUCED_STATUS = "제작완료·GM검수대기(자동생성)"  # 생산 성공 후 로드맵 행 상태값


def mark_episode_produced(ep: dict, folder_slug: str) -> bool:
    """로드맵 편별 표에서 ep['num'] 행의 일자·폴더·상태를 '제작완료(자동생성)'로 갱신.

    현재 상태가 PLANNED_STATUS('기획예정') 인 행만 손댄다(이미 발행완료 등은 강등 금지).
    그래야 다음날 가동 시 pick_next_episode 가 그 다음 '기획예정' 편을 고른다(중복 재생성 차단).
    반환: 갱신 성공 여부. 실패해도 빌드/등록은 이미 끝났으므로 죽지 않음(상위에서 경고만).
    """
    try:
        text = ROADMAP.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] 로드맵 읽기 실패 — 자동표시 건너뜀: {exc}")
        return False

    today_iso = datetime.now().strftime("%Y-%m-%d")
    out_lines: list[str] = []
    updated = False
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        # 표 데이터 행만 검사 (| 로 시작, 구분선·헤더 제외)
        if updated or not stripped.startswith("|"):
            out_lines.append(line)
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            out_lines.append(line)
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 6:
            out_lines.append(line)
            continue
        m = re.match(r"^\s*(\d+)", cells[0])
        if not m or int(m.group(1)) != ep["num"]:
            out_lines.append(line)
            continue
        # 매칭 — 단 '기획예정' 행만 갱신(회귀 가드)
        if cells[5] != PLANNED_STATUS:
            print(f"[INFO] 로드맵 #{ep['num']} 행 상태='{cells[5]}' (기획예정 아님) — 자동표시 생략(강등 금지).")
            out_lines.append(line)
            updated = True  # 더 갱신 안 함(첫 매칭 행만)
            continue
        cells[1] = today_iso
        cells[2] = folder_slug
        cells[5] = PRODUCED_STATUS
        out_lines.append("| " + " | ".join(cells) + " |")
        updated = True
        print(f"[INFO] 로드맵 #{ep['num']} 행 자동 갱신 → 일자={today_iso} 폴더={folder_slug} 상태={PRODUCED_STATUS}")

    if not updated:
        print(f"[WARN] 로드맵에서 #{ep['num']} 행을 찾지 못함 — 자동표시 실패(다음날 중복 재생성 위험).")
        return False
    try:
        # 끝 개행 보존
        new_text = "\n".join(out_lines)
        if text.endswith("\n") and not new_text.endswith("\n"):
            new_text += "\n"
        ROADMAP.write_text(new_text, encoding="utf-8")
        return True
    except Exception as exc:
        print(f"[WARN] 로드맵 쓰기 실패 — 자동표시 미반영: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 검수 카드 발송 (제작완료 시 [✅승인]/[❌반려] 버튼 카드 → 텔레그램, 무폴링 발행 트리거)
# ─────────────────────────────────────────────────────────────────────────────
def send_review_card(queue_id: str) -> bool:
    """scripts/send_review_card.py --id <queue_id> 호출 → GM 텔레그램에 [✅승인] 버튼 카드 발송.

    register_publish 의 montage 사진(버튼 없음) 와 별개로, 이 버튼 카드 탭이 유일한 무폴링 발행
    트리거다(bot.py pub: 콜백). 실패해도 제작·등록은 이미 끝났으므로 죽지 않음(경고만).
    """
    script = ROOT / "scripts" / "send_review_card.py"
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [str(PY), str(script), "--id", queue_id],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
        print((proc.stdout or "") + (proc.stderr or ""))
        ok = proc.returncode == 0
        print(f"[{'OK' if ok else 'WARN'}] 검수 카드 발송 {'성공' if ok else '실패'} — id={queue_id}")
        return ok
    except Exception as exc:
        print(f"[WARN] 검수 카드 발송 예외 (제작·등록은 완료): {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 빌드 실행 (생성된 build_slides.py → register_publish → M5 검수대기)
# ─────────────────────────────────────────────────────────────────────────────
def run_build_slides(build_path: Path, timeout: int = 300) -> None:
    """생성된 build_slides.py 실행. register_publish 가 M5 검수대기 등록까지 수행.

    실패(exit≠0) 시 RuntimeError 전파 → 텔레그램 경고 + 중단(불량 미등록).
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [str(PY), str(build_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    if proc.returncode != 0:
        raise RuntimeError(f"build_slides.py 실행 실패 exit={proc.returncode}")


# ─────────────────────────────────────────────────────────────────────────────
# 주제 이탈 검사 (2차 게이트) — 1차 프롬프트 잠금이 뚫렸을 때 GM이 승인 전 알게.
#   휴리스틱(로드맵 핵심어가 산출물에 하나도 없으면 이탈 의심)이라 '경고만' — 하드블록 안 함.
# ─────────────────────────────────────────────────────────────────────────────
_DRIFT_STOP = {
    "그리고", "하는", "에서", "으로", "합니다", "이런", "저런", "우리", "당신", "그것",
    "에게", "까지", "부터", "대한", "위해", "통해", "바로", "정말", "매우", "오늘",
    "지금", "해서", "해도", "대표", "리더", "방법", "이렇게", "그래서",
}


def _hangul_tokens(s: str) -> list[str]:
    return re.findall(r"[가-힣]{2,}", str(s))


def check_topic_drift(build_path: Path, ep: dict) -> str | None:
    """생성된 build_slides.py 주제가 로드맵 확정편과 '완전히' 다른지 보수적 검사.
    로드맵 제목 핵심어가 산출물에 하나도 안 나오면 이탈 의심. 판단 애매하면 None(경고 안 냄·fail-open)."""
    try:
        code = build_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    parts: list[str] = []
    m = re.search(r'title\s*=\s*["\']([^"\']+)["\']', code)
    if m:
        parts.append(m.group(1))
    parts += re.findall(r'kor_title\s*=\s*["\']([^"\']+)["\']', code)
    mc = re.search(r'CAPTION\s*=\s*(?:"""|\'\'\'|["\'])(.{0,160})', code, re.S)
    if mc:
        parts.append(mc.group(1))
    blob = " ".join(parts)
    if not blob.strip():
        return None  # 주제 단서를 못 뽑음 → 판단 보류
    title_core = str(ep.get("title", "")).split(":")[0]
    key = [t for t in _hangul_tokens(title_core) if t not in _DRIFT_STOP]
    key = list(dict.fromkeys(key))
    if len(key) < 2:
        return None  # 핵심어 빈약 → 오탐 위험, 보류
    if any(t in blob for t in key):
        return None  # 핵심어 하나라도 맞으면 정상으로 본다(보수적)
    return (
        f"⚠️ AI 시리즈 #{ep.get('num')} 주제 이탈 의심 — 로드맵 확정 「{ep.get('title', '')}」 의 "
        f"핵심어({'·'.join(key[:4])})가 산출물에 하나도 없음. 검수카드 승인 전 주제 확인 요망."
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI 시리즈 보드 데이터 동기화 (로드맵 → series_data.json 파생 미러)
# ─────────────────────────────────────────────────────────────────────────────
def refresh_series_board() -> bool:
    """build_series_board_data.py 를 실행해 series_data.json 을 재생성(보드 동기화).

    best-effort: 실패해도 제작·등록에 영향 주지 않음(False 반환 + 경고만).
    """
    try:
        builder = ROOT / "scripts" / "build_series_board_data.py"
        if not builder.exists():
            print("[WARN] build_series_board_data.py 부재 — 보드 동기화 생략")
            return False
        import importlib.util

        spec = importlib.util.spec_from_file_location("_series_board", builder)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
        return True
    except Exception as exc:
        print(f"[WARN] AI 시리즈 보드 데이터 동기화 실패(제작 영향 없음): {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 승인 대기 리마인더 (07:30 제작 끝에 검수대기 항목 있으면 텔레그램 1줄 알림)
# ─────────────────────────────────────────────────────────────────────────────
REVIEW_QUEUE_PATH = (
    ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
)
PENDING_STATUS = "검수대기"
_MAX_LIST = 5  # 메시지에 나열할 최대 편 수


def _build_pending_reviews_msg(repo_root: Path) -> str | None:  # noqa: ARG001
    """검수대기 항목을 읽어 리마인더 메시지 문자열 반환. 0건이면 None(전송 안 함).

    메시지 생성과 전송을 분리해 전송 없이 빌더만 단독 테스트 가능하게 한다.
    파일 없거나 파싱 실패 → None(fail-soft, 제작 본 작업에 영향 없음).
    """
    try:
        if not REVIEW_QUEUE_PATH.exists():
            return None
        import json as _json

        raw = REVIEW_QUEUE_PATH.read_text(encoding="utf-8")
        data = _json.loads(raw)
        # 리스트 or {"items": [...]} 두 구조 모두 안전 처리
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        else:
            return None

        pending = [it for it in items if isinstance(it, dict) and it.get("status") == PENDING_STATUS]
        if not pending:
            return None

        # 편 식별: id에서 'AI{번호}' 추출 시도, 없으면 title 앞부분
        def _label(it: dict) -> str:
            m = re.search(r"AI(\d+)", str(it.get("id", "")))
            if m:
                return f"#{m.group(1)}편"
            title = str(it.get("title", "")).strip()
            return title[:18] + ("…" if len(title) > 18 else "")

        labels = [_label(it) for it in pending[:_MAX_LIST]]
        extra = len(pending) - _MAX_LIST
        summary = " · ".join(labels)
        if extra > 0:
            summary += f" 외 {extra}건"

        return (
            f"📋 AI 시리즈 승인 대기 {len(pending)}편 — {summary}\n"
            f"M5 또는 텔레그램 카드에서 [✅승인]하면 발행됩니다."
        )
    except Exception:
        return None


def report_pending_reviews(repo_root: Path) -> None:
    """검수대기 1건 이상이면 텔레그램 리마인더 전송. 0건이면 조용히 종료.

    모든 예외 fail-soft — 리마인더 실패가 제작 본 작업을 망치지 않게.
    """
    try:
        msg = _build_pending_reviews_msg(repo_root)
        if msg:
            telegram(msg)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────
def run(dry_run: bool, plan_only: bool) -> int:
    print(
        f"[INFO] === AI 시리즈 제작기 시작 === "
        f"{datetime.now().isoformat(timespec='seconds')} (dry_run={dry_run}, plan_only={plan_only})"
    )

    # 1) 로드맵 파싱 (실패 시 경고 + 중단)
    try:
        if not ROADMAP.exists():
            raise RoadmapError(f"로드맵 파일 부재: {ROADMAP}")
        episodes = parse_roadmap_episodes(ROADMAP.read_text(encoding="utf-8"))
    except RoadmapError as exc:
        msg = f"⚠️ AI 시리즈 제작 중단 — 로드맵 파싱 실패: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 2) 다음 편 선정 (소진 시 생성 금지 + 경고 후 정상 종료)
    nxt = pick_next_episode(episodes)
    if nxt is None:
        planned_nums = [e["num_raw"] for e in episodes if e["status"] == PLANNED_STATUS]
        print(f"[INFO] 기획예정 편 소진 — 생성 금지(쓰레기/중복 방지). (남은 기획예정: {planned_nums})")
        telegram("📭 AI 시리즈 기획예정 편 소진(0건) — 로드맵 §5에 '기획예정' 행 추가 필요, 다음 편 자동 제작 중단")
        return 0

    prev = prev_published_episode(episodes, nxt["num"])
    folder_slug = make_folder_slug(nxt)
    print(
        f"[INFO] 다음 편 선정 → #{nxt['num']} 「{nxt['title']}」 / 핵심메시지: {nxt['message']}\n"
        f"       제작 폴더(코드명): {folder_slug}"
        + (f" / 직전 편 #{prev['num']} 「{prev['title']}」(중복 점검 대상)" if prev else "")
    )

    if plan_only:
        print("[PLAN-ONLY] 선정만 출력하고 종료(제작 안 함).")
        return 0

    if dry_run:
        print(
            "[DRY-RUN] 헤드리스 시모 호출·빌드·M5 등록 안 함. 아래 프롬프트만 검증:\n"
            "----- 프롬프트 미리보기 (앞 800자) -----"
        )
        print(build_producer_prompt(nxt, prev, folder_slug)[:800])
        print("----- (생략) -----")
        return 0

    # 3) 폴더 스캐폴드 (namuk.wellperion/ 하위 — 회사 콘텐츠와 분리)
    folder_path = NAMUK_DIR / folder_slug
    folder_path.mkdir(parents=True, exist_ok=True)
    build_path = folder_path / "build_slides.py"

    # 4) 시모 헤드리스 호출 → build_slides.py 작성 (실패 시 경고 + 중단)
    try:
        result_text = invoke_simo_producer(nxt, prev, folder_slug)
        print(f"[INFO] 시모 응답 수신 (len={len(result_text)})")
    except RuntimeError as exc:
        msg = f"⚠️ AI 시리즈 #{nxt['num']} 제작 중단 — 시모 헤드리스 호출 실패: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 4-1) build_slides.py 실제 생성 검증 (시모가 안 썼으면 불량 — M5 미등록)
    if not build_path.exists():
        msg = (
            f"⚠️ AI 시리즈 #{nxt['num']} 제작 중단 — 시모가 build_slides.py 미생성 "
            f"({build_path}). M5 미등록."
        )
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 4-2) 주제 이탈 검사 (2차 게이트) — 1차 프롬프트 잠금이 뚫렸을 때 GM이 승인 전 알게.
    #      경고만 — M5 등록·검수카드는 그대로 진행(하드블록 안 함). GM이 카드에서 판단.
    _drift = check_topic_drift(build_path, nxt)
    if _drift:
        print(f"[WARN] {_drift}")
        telegram(_drift)

    # 5) 빌드 실행 → register_publish 가 M5 검수대기 등록까지 (실패 시 경고 + 중단)
    try:
        run_build_slides(build_path)
    except Exception as exc:
        msg = f"⚠️ AI 시리즈 #{nxt['num']} 빌드 실패 — M5 미등록: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 6) 로드맵 자동 갱신 — 이 편 행을 '제작완료(자동생성)'로 표시(다음날 다음 편 선정·중복 차단).
    #    실패해도 제작·등록은 끝났으므로 경고만.
    if not mark_episode_produced(nxt, folder_slug):
        telegram(
            f"⚠️ AI 시리즈 #{nxt['num']} 로드맵 자동표시 실패 — 다음날 같은 편 재생성 위험. "
            f"로드맵 #{nxt['num']} 행 상태 수동 확인 요망."
        )

    # 6-1) AI 시리즈 보드 데이터 동기화(로드맵 → series_data.json). best-effort — 실패해도 제작 영향 없음.
    refresh_series_board()

    # 7) 검수 카드 발송 — [✅승인]/[❌반려] 버튼 카드(무폴링 발행 트리거). register_publish montage 와 별개.
    queue_id = make_queue_id(nxt)
    if not send_review_card(queue_id):
        telegram(
            f"⚠️ AI 시리즈 #{nxt['num']} 검수 카드(버튼) 발송 실패 — id={queue_id}. "
            f"M5 등록은 됨. 수동 카드 발송: send_review_card.py --id {queue_id}"
        )

    # 8) 성공 — register_publish montage + 위 [승인] 버튼 카드까지 발송됨.
    #    발행은 GM 텔레그램 [✅승인] 탭 시 봇 pub: 콜백이 즉시 수행(무폴링). 이 스크립트는 발행 안 함.
    print(
        f"[OK] AI 시리즈 #{nxt['num']} 「{nxt['title']}」 제작 완료 → M5 검수대기 등록 + 검수 카드 발송. "
        f"발행은 GM 텔레그램 [✅승인] 탭 → 봇 pub: 즉시 발행(무폴링). (이 스크립트는 발행 안 함)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="AI 시리즈 다음 편 자동 제작 → M5 검수큐 등록 (발행 절대 자동 아님)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="헤드리스 호출·빌드·등록 없이 선정·프롬프트만 검증"
    )
    ap.add_argument(
        "--plan-only", action="store_true", help="다음 편 선정 결과만 출력하고 즉시 종료"
    )
    args = ap.parse_args()
    exit_code = run(dry_run=args.dry_run, plan_only=args.plan_only)
    # 승인 대기 리마인더 — dry_run/plan_only 모드에선 전송 안 함(테스트 무전송 원칙)
    if not args.dry_run and not args.plan_only:
        report_pending_reviews(ROOT)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
