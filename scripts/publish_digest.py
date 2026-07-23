#!/usr/bin/env python3
"""발행완료 → 콘텐츠 1건 통합요약 텔레그램 자동 발신 (2026-07-15)

흐름: ig_review_publish_watcher.py 가 이번 실행(run)에서 '발행완료'로 전환된 항목들을
      모아 send_publish_digest() 를 호출한다 → 항목을 콘텐츠(폴더) 단위로 묶어
      '문의·컨택·등록 알림' 텔레그램방(TELEGRAM_INQUIRY_CHAT_ID, telegram_bot/.env)에
      콘텐츠 1건당 통합요약 메시지 1장을 발신한다.

      기존 _notify_published()(danggn/kakao 개별 발행 직후 per-channel 알림)와는 별개 —
      이건 '콘텐츠 1건 = 통합 한 장' GM 루틴을 위한 채널 종합 요약이다.

그룹키: folder 필드에서 '/output(...)' 접미를 제거한 베이스 경로
        (예: instagram/260715_L1_수영/output(블로그) → instagram/260715_L1_수영).
        folder 없으면 id 에서 채널 접미(-BLOG 등 대문자 토큰)를 제거한 값.

멱등: scripts/.publish_digest_sent.json 에 그룹키 → 해시(항목id·url·published_at 조합,
      참조용) 저장. 판정 기준은 **그룹키 존재 여부**(1콘텐츠 1회 — 항목 부분집합이 채널별로
      나뉘어 들어와 해시가 달라져도 재발신하지 않는다). ★ 2026-07-18 시토: 같은 콘텐츠가
      채널별로 분할 유입되며 해시가 매번 달라져 재발신되던 결함을 이 기준으로 수리.

★ 조용한 실패 금지: 토큰·챗ID 미설정이면 stderr에 [ERROR] 로그를 남기고 전송을
  시도하지 않는다 — 성공한 척 조용히 넘어가지 않는다.

품질 게이트 + 라우팅 (2026-07-18 GM 지시): 콘텐츠(folder) 1건 = 1이미지 + 5채널
(인스타·블로그·카페·당근·카카오) 링크 전부가 '표준'이다. 발신 직전 review_queue.json
전체에서 해당 folder 그룹을 모아 _group_is_complete() 로 표준 충족 여부를 판정한다.
- 충족 → 실무진 문의알림방(TELEGRAM_INQUIRY_CHAT_ID)에 표준 디제스트(그룹 전체 채널
  엔트리 기준, 이번 사이클 부분집합이 아님) 발송 후 SENT_LEDGER[folder] 기록(평생 1회).
- 미충족 → 실무진 방엔 발송하지 않고 GM 개인 업무보고봇 방(TELEGRAM_CHAT_ID)에 사유와
  함께 보류 1줄만 발송(같은 folder는 SENT_LEDGER[f"{folder}:held"] 로 1회만 — 완결되면
  자동으로 표준 디제스트가 나간다).

★ 게이트 완화 (2026-07-22 시토): 완결 판정(_group_is_complete)에서 채널별 게시 URL 회수
  요건을 제거했다 — 카카오는 편별 공개 URL이 원래 없고 네이버 블로그는 URL 회수가 불안정해
  5채널 전부 실제 '발행완료'여도 다이제스트가 영구 보류되던 구조적 결함 수리. 이제 완결은
  상태(_COMPLETE_STATUSES)만으로 판정하고, URL 없는 채널은 build_digest()가 정본 채널
  홈 URL(_CHANNEL_HOME_URLS)로 폴백해 '1이미지+5링크' 표준을 유지한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:  # 전역 발송 페이싱(프로세스 간 429 방지) — best-effort
    from tg_outbound_log import pace as _tg_pace
except Exception:
    def _tg_pace(*_a, **_k):
        return None

try:  # 결정 정합 게이트 공용 신호(§4) — dedup 이 재발송을 막을 때 1줄 남긴다(best-effort)
    from decision_replay_log import append as _replay_append
except Exception:
    def _replay_append(*_a, **_k):
        return False
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
ENV_FILE = ROOT / "telegram_bot" / ".env"
SENT_LEDGER = ROOT / "scripts" / ".publish_digest_sent.json"
REVIEW_QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY = "TELEGRAM_INQUIRY_CHAT_ID"  # 문의·컨택·등록 알림방(실무진)
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"  # GM 개인 업무보고봇 방(8254867551) — 보류 알림 전용

_OUTPUT_SUFFIX_RE = re.compile(r"/output\([^)]*\)\s*$")
_BRACKET_LABEL_RE = re.compile(r"\s*\[[^\]]*\]\s*")
_ID_CHANNEL_SUFFIX_RE = re.compile(r"-[A-Z]{3,}$")

# 채널 → (표시순서, 이모지 라벨) — 부분일치. 매핑에 없으면 🔗 {원채널명} (순서는 맨 뒤).
_CHANNEL_LABEL_ORDER: list[tuple[re.Pattern, str]] = [
    (re.compile("인스타"), "📷 인스타그램"),
    (re.compile("블로그"), "📝 네이버 블로그"),
    (re.compile("카페"), "☕ 네이버 카페"),
    (re.compile("카카오"), "💬 카카오채널"),
    (re.compile("당근"), "🥕 당근"),
]
_DEFAULT_DIGEST_INTRO = "여러 채널에 새 소식을 올렸어요."

# 채널별 정본 홈 URL(게시글 URL 미회수 시 폴백) — 저장소 기존 설정에서 취득, 추정·날조 금지.
# 인스타그램: 3. 웰페리온 가이드/coo/reception/reception_block.html:399 (공식 인스타그램 링크)
# 네이버 블로그: scripts/naver_blog_upload_playwright.py DEFAULT_BLOG_ID="wellperion"
#   (blog.naver.com/{blog_id} 패턴)
# 네이버 카페: scripts/retrieve_post_url.py CAFE_NAME="ichon1dong" (동부이촌동 커뮤니티)
# 카카오채널: scripts/kakao_channel_upload_playwright.py / retrieve_post_url.py
#   KAKAO_CHANNEL_ID="_cgxiKj" (pf.kakao.com/{channel_id} 공개 홈)
# 당근: bizprofile.daangn.com/... 은 로그인 필요한 관리자 홈이라 공개 소비자 홈 URL이
#   저장소에 없음 — 하드코딩하지 않고 미발견으로 남긴다(폴백은 기존 플레이스홀더 문구).
_CHANNEL_HOME_URLS: list[tuple[re.Pattern, str]] = [
    (re.compile("인스타"), "https://www.instagram.com/wellperion/"),
    (re.compile("블로그"), "https://blog.naver.com/wellperion"),
    (re.compile("카페"), "https://cafe.naver.com/ichon1dong"),
    (re.compile("카카오"), "https://pf.kakao.com/_cgxiKj"),
]


def _channel_home_url(channel: str) -> str:
    """채널 문자열 → 정본 홈 URL. 매핑에 없으면 ''(당근 등 미발견 채널)."""
    for pattern, home_url in _CHANNEL_HOME_URLS:
        if pattern.search(channel):
            return home_url
    return ""


# ---------------------------------------------------------------------------
# .env 로더 (python-dotenv 불필요, KEY=VALUE / # 주석) — os.environ 우선.
# ---------------------------------------------------------------------------
def _load_env_val(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# 그룹핑 — 콘텐츠(폴더) 단위
# ---------------------------------------------------------------------------
def _base_key(it: dict) -> str:
    """발행 항목 → 콘텐츠 단위 그룹키."""
    folder = (it.get("folder") or "").strip()
    if folder:
        return _OUTPUT_SUFFIX_RE.sub("", folder)
    item_id = (it.get("id") or "").strip()
    return _ID_CHANNEL_SUFFIX_RE.sub("", item_id) or item_id


def group_published(items: list[dict]) -> dict[str, list[dict]]:
    """발행완료 항목들을 콘텐츠 단위(그룹키)로 묶는다. 입력 순서를 그룹 내 순서로 보존."""
    groups: dict[str, list[dict]] = {}
    for it in items:
        key = _base_key(it)
        groups.setdefault(key, []).append(it)
    return groups


# ---------------------------------------------------------------------------
# 품질 게이트 — folder(그룹키) 완결·표준 판정 (2026-07-18)
# ---------------------------------------------------------------------------
# '확인필요(발행됨·URL미회수)'(블로그·카페, 2026-07-20 배834) = 게시는 진행됐으나 URL 폴링
# 실패한 상태 — '미발행'이 아니라 published 취급하되, 아래 missing_url 검사가 URL 없으므로
# 여전히 완결 판정을 막는다(URL 보강 후 자동 통과).
_COMPLETE_STATUSES = {"발행완료", "발행검증대기", "확인필요(발행됨·URL미회수)"}
# official(웰페리온 공식) 그룹은 5채널 전부가 표준 — 채널 유형별 엔트리 자체가 있는지 강제.
# personal(namuk) 계정은 현행대로 IG 단독 허용(강제 미적용).
_REQUIRED_OFFICIAL_CHANNELS: list[tuple[str, re.Pattern]] = [
    ("인스타그램", re.compile("인스타")),
    ("네이버 블로그", re.compile("블로그")),
    ("네이버 카페", re.compile("카페")),
    ("당근", re.compile("당근")),
    ("카카오채널", re.compile("카카오")),
]


def _load_review_queue() -> list[dict]:
    """완결 판정용 review_queue.json 전체 로드(폐기·검수대기·발행완료 등 상태 무관 전부).
    로드 실패 시 빈 리스트(안전한 쪽=미완결 판정으로 귀결·오발신 방지) + [ERROR] 로그."""
    try:
        data = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[ERROR] review_queue.json 로드 실패({REVIEW_QUEUE_PATH}): {exc}", file=sys.stderr)
        return []


def _group_all_entries(folder: str, all_review_items: list[dict]) -> list[dict]:
    """folder(그룹키)에 속하는 review_queue 전체 엔트리 — 발행완료·검수대기·실패·폐기 전부."""
    return [it for it in all_review_items if _base_key(it) == folder]


def _group_is_official(entries: list[dict]) -> bool:
    """official(웰페리온 공식) 계정 그룹 판정 — 엔트리 account에 'wellperion' 포함 & 'namuk' 미포함.
    그룹 내 엔트리 하나라도 namuk 계정이면 personal로 간주(5채널 강제 미적용, 현행 IG 단독 허용)."""
    saw_wellperion = False
    for it in entries:
        account = (it.get("account") or "").lower()
        if "namuk" in account:
            return False
        if "wellperion" in account:
            saw_wellperion = True
    return saw_wellperion


def _group_is_complete(folder: str, all_review_items: list[dict]) -> tuple[bool, str]:
    """folder(그룹키) 완결·표준 판정 — review_queue.json 전체에서 해당 그룹 엔트리를 모아
    (C) official 그룹은 5채널 유형 전부 엔트리 존재 강제, (A) 전 채널 발행 상태(_COMPLETE_STATUSES)
    여부를 검사. URL 회수 여부는 더 이상 완결 판정 기준이 아니다(2026-07-22 게이트 완화 —
    URL 미회수는 build_digest()의 채널 홈 폴백으로 흡수).
    True → 실무진 문의알림방 표준 디제스트 발신 대상. False → 사유와 함께 GM 개인 방 보류 대상."""
    entries = _group_all_entries(folder, all_review_items)
    if not entries:
        return False, "리뷰 큐에서 그룹 엔트리를 찾지 못함"

    if _group_is_official(entries):
        present_channels = [it.get("channel") or "" for it in entries]
        missing_channel_types = [
            label for label, pattern in _REQUIRED_OFFICIAL_CHANNELS
            if not any(pattern.search(ch) for ch in present_channels)
        ]
        if missing_channel_types:
            return False, ", ".join(missing_channel_types) + " 엔트리 없음(미등록)"

    not_published = [
        f"{it.get('channel') or '채널 미지정'}({it.get('status') or '미상태'})"
        for it in entries
        if (it.get("status") or "미상태") not in _COMPLETE_STATUSES
    ]
    if not_published:
        return False, "미발행: " + ", ".join(not_published)

    # ★ 2026-07-22 시토: URL 회수 요건 제거(게이트 완화) — 카카오는 편별 공개 URL이
    # 원래 없고, 네이버 블로그는 URL 회수가 불안정해 5채널 전부 실제 '발행완료'여도
    # 게이트가 다이제스트를 영구 보류시키던 구조적 결함 수리. 완료 판정은 이제
    # 상태(_COMPLETE_STATUSES)만으로 하고, URL 유무는 build_digest()의 홈 URL
    # 폴백(_CHANNEL_HOME_URLS)으로 흡수한다.
    return True, ""


def _dedup_channel_entries(entries: list[dict]) -> list[dict]:
    """채널 라벨(고정 5종) 기준 1채널 1엔트리로 축약 — URL 있는 엔트리 우선, 동률이면
    published_at 최신 우선. 같은 folder에 채널 중복 엔트리가 있어도(예: 인스타 2건)
    표준 디제스트에 채널이 중복 표시되지 않도록 한다."""
    best: dict[str, dict] = {}
    for it in entries:
        _, label = _channel_label(it.get("channel") or "채널 미지정")
        cur = best.get(label)
        if cur is None:
            best[label] = it
            continue
        cur_has_url = bool((cur.get("post_url") or "").strip())
        new_has_url = bool((it.get("post_url") or "").strip())
        if new_has_url and not cur_has_url:
            best[label] = it
        elif new_has_url == cur_has_url and (it.get("published_at") or "") > (cur.get("published_at") or ""):
            best[label] = it
    return list(best.values())


def _held_notice(folder: str, reason: str, entries: list[dict]) -> str:
    """GM 개인 방 보류 알림 1줄 — 전 채널 발행완료되면 자동으로 표준 디제스트가 나간다는 안내 포함."""
    title = _digest_title(entries) if entries else folder
    return (
        f"⚠️ 발행 디제스트 기준 미달로 실무진 방 발송 보류 — {folder} / {title}: {reason}. "
        "전 채널 발행완료되면 자동 발송."
    )


# ---------------------------------------------------------------------------
# 메시지 포맷
# ---------------------------------------------------------------------------
def _representative_title(group: list[dict]) -> str:
    """그룹 대표 제목: ' — ' 앞 공통 베이스가 있으면 그것, 없으면 첫 항목 전체 제목.
    내부 라벨 '[채널]' 표기는 제거한다."""
    titles = [it.get("title", "") for it in group if it.get("title")]
    if not titles:
        return group[0].get("id", "(제목 없음)") if group else "(제목 없음)"
    bases = [t.split(" — ")[0].strip() for t in titles]
    uniq = list(dict.fromkeys(b for b in bases if b))
    chosen = uniq[0] if len(uniq) == 1 else titles[0]
    return _BRACKET_LABEL_RE.sub(" ", chosen).strip()


def _channel_label(channel: str) -> tuple[int, str]:
    """채널 문자열 → (표시순서, 이모지 라벨). 매핑에 없으면 (맨뒤순서, '🔗 {원채널명}')."""
    for order, (pattern, label) in enumerate(_CHANNEL_LABEL_ORDER):
        if pattern.search(channel):
            return order, label
    return len(_CHANNEL_LABEL_ORDER), f"🔗 {channel}"


def _digest_title(group: list[dict]) -> str:
    """리치 포맷 제목 — group 항목 중 digest_title 있으면 그것, 없으면 기존 대표 title 폴백."""
    for it in group:
        t = (it.get("digest_title") or "").strip()
        if t:
            return t
    return _representative_title(group)


def _digest_intro(group: list[dict]) -> str:
    """리치 포맷 설명 한 줄 — group 항목 중 digest_intro 있으면 그것, 없으면 일반 폴백 문구."""
    for it in group:
        intro = (it.get("digest_intro") or "").strip()
        if intro:
            return intro
    return _DEFAULT_DIGEST_INTRO


def build_digest(group: list[dict]) -> str:
    """콘텐츠 1건 통합요약 메시지 — 📢헤더 · 설명 · 채널이모지 링크(고정순서) · 응원 CTA."""
    title = _digest_title(group)
    intro = _digest_intro(group)
    lines = [
        f"📢 웰페리온 공식 · {title} 발행 완료 — 응원 부탁드려요!",
        "",
        intro,
        "아래 링크에서 ❤️ 좋아요 · 💬 댓글 남겨주시면 큰 힘이 됩니다 🙏",
        "",
    ]
    entries: list[tuple[int, str, str]] = []
    for it in group:
        # ★ URL 미회수 채널도 이름은 노출 — 채널 누락 방지(2026-07-16 카카오 누락 수정).
        #   엔진이 게시 URL을 못 잡은 채널(예: 카카오)이 디제스트에서 통째로 빠지던 버그.
        url = (it.get("post_url") or "").strip()
        ch = it.get("channel") or "채널 미지정"
        order, label = _channel_label(ch)
        entries.append((order, label, url, ch))
    entries.sort(key=lambda e: e[0])
    for _, label, url, ch in entries:
        lines.append(label)
        if url:
            lines.append(url)  # 게시글 링크(실제 URL)
        else:
            home_url = _channel_home_url(ch)
            # ★ 2026-07-22 시토: URL 미회수 채널(카카오·블로그 등)도 '1이미지+5링크' 표준
            # 유지를 위해 채널 정본 홈으로 폴백. 게시글 링크와 헷갈리지 않게 표기 구분.
            lines.append(f"{home_url} (채널 홈 · 게시글 링크 미확정)" if home_url else "게시됨 · 채널에서 확인")
    lines.append("")
    lines.append("좋아요·댓글로 응원 부탁드립니다 🙏")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 멱등 — 그룹키 존재 기준으로 1콘텐츠 1회 보장(해시는 참조용 저장만)
# ---------------------------------------------------------------------------
def _group_hash(group: list[dict]) -> str:
    payload = "||".join(sorted(
        f"{it.get('id', '')}|{it.get('post_url', '')}|{it.get('published_at', '')}"
        for it in group
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_ledger(ledger_path: Path) -> dict:
    if not ledger_path.exists():
        return {}
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_ledger(ledger_path: Path, ledger: dict) -> None:
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 텔레그램 전송
# ---------------------------------------------------------------------------
def _instagram_preview_url(group: list[dict]) -> str:
    """그룹 항목 중 channel에 '인스타' 포함 + post_url 있는 첫 항목의 post_url.
    없으면 빈 문자열(미리보기 카드 생략)."""
    for it in group:
        channel = it.get("channel") or ""
        url = (it.get("post_url") or "").strip()
        if "인스타" in channel and url:
            return url
    return ""


def _send(token: str, chat_id: str, text: str, preview_url: str = "") -> bool:
    payload: dict[str, str] = {"chat_id": chat_id, "text": text}
    # ★ 근본원인 (2026-07-16 진단): 인스타그램 게시물 URL의 link_preview는 텔레그램이 IG로부터
    #   미리보기 이미지를 못 가져와(IG가 봇 프리뷰 페처 차단) sendMessage 자체가 429로 실패한다.
    #   → 디제스트가 07-15 셋업 후 한 번도 도착 못한 진짜 원인. 미리보기를 끄면 즉시 200 성공(실측).
    #   따라서 IG URL 대용량 미리보기는 비활성으로 안정 배달을 보장한다.
    #   시각 카드가 필요하면 IG URL 프리뷰가 아니라 sendPhoto로 실제 슬라이드 이미지를 첨부(후속 옵션).
    _ = preview_url  # 시그니처 호환(미사용) — IG URL 프리뷰는 429 유발이라 사용 안 함
    payload["link_preview_options"] = json.dumps({"is_disabled": True})
    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # 429(레이트리밋) 자가재시도 — retry_after 존중 + 백오프. 텔레그램 그룹 초당/분당 한계로
    # 발행 run-end 텔레그램 버스트 직후 429가 잦아 디제스트가 조용히 유실되던 문제 근본 차단
    # (2026-07-16 진단: 이력 파일 부재=한 번도 성공 못함, 재시도 0이 원인).
    max_attempts = 6
    for attempt in range(max_attempts):
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            _tg_pace()  # 발송 직전 전역 페이싱(초당 1건 미만·프로세스 간)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and attempt < max_attempts - 1:
                retry_after = 3
                try:
                    body = json.loads(ex.read().decode())
                    retry_after = int(body.get("parameters", {}).get("retry_after", 3))
                except Exception:
                    pass
                wait = min(retry_after + 2 * (attempt + 1), 60)  # 초당 한계 흡수 버퍼
                print(f"[digest] 429 레이트리밋 — {wait}s 대기 후 재시도 "
                      f"({attempt + 1}/{max_attempts})", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"[digest] 전송 실패 HTTP {ex.code}: {ex.reason}", file=sys.stderr)
            return False
        except Exception as ex:  # 네트워크·타임아웃 등
            print(f"[digest] 전송 오류: {ex}", file=sys.stderr)
            return False
    return False


def _first_slide_image(group: list[dict]) -> str:
    """콘텐츠의 인스타그램 메인 1장(첫 슬라이드) 로컬 경로 — 없으면 ''.
    IG URL link_preview는 텔레그램이 못 가져와(IG 차단) 429 → 실제 이미지 파일로 '1장 뷰' 구현."""
    for it in group:
        folder = (it.get("folder") or "").strip()
        if not folder:
            continue
        base = re.sub(r"/output\([^)]*\)$", "", folder)
        for sub in ("output(인스타그램)", "output(instagram)"):
            d = ROOT / base / sub
            try:
                if d.is_dir():
                    imgs = sorted(d.glob("post_*.jpg")) or sorted(d.glob("*.jpg"))
                    if imgs:
                        return str(imgs[0])
            except Exception:
                continue
    return ""


def _send_photo(token: str, chat_id: str, photo_path: str, caption: str) -> bool:
    """인스타그램 메인 1장을 sendPhoto로 첨부 + 캡션(디제스트 본문). 페이싱 + 429 자가재시도.
    GM 원안='메인 1장 뷰' — IG URL 프리뷰가 아니라 실제 이미지 업로드라 IG 차단과 무관하게 항상 뜬다."""
    try:
        with open(photo_path, "rb") as f:
            photo_bytes = f.read()
    except Exception:
        return False
    boundary = "----wpdigest" + os.urandom(8).hex()
    fname = os.path.basename(photo_path) or "photo.jpg"

    def _field(name: str, value: str) -> bytes:
        return (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                f'{value}\r\n').encode("utf-8")

    body = (
        _field("chat_id", str(chat_id))
        + _field("caption", caption)
        + (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; '
           f'filename="{fname}"\r\nContent-Type: image/jpeg\r\n\r\n').encode("utf-8")
        + photo_bytes + b"\r\n"
        + f"--{boundary}--\r\n".encode("utf-8")
    )
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    for attempt in range(6):
        _tg_pace()
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and attempt < 5:
                ra = 3
                try:
                    ra = int(json.loads(ex.read().decode()).get("parameters", {}).get("retry_after", 3))
                except Exception:
                    pass
                time.sleep(min(ra + 2 * (attempt + 1), 60))
                continue
            print(f"[digest] sendPhoto 실패 HTTP {ex.code}: {ex.reason}", file=sys.stderr)
            return False
        except Exception as ex:
            print(f"[digest] sendPhoto 오류: {ex}", file=sys.stderr)
            return False
    return False


def send_publish_digest(
    items: list[dict],
    dry_run: bool = False,
    ledger_path: Path | None = None,
) -> int:
    """발행완료 항목들을 콘텐츠 단위로 묶어 품질 게이트 통과 시 문의·컨택·등록 알림방에
    통합요약 1건씩 발신. 게이트 미달이면 실무진 방엔 보내지 않고 GM 개인 방에 보류 1줄만
    보낸다(2026-07-18 GM 지시 — 품질 게이트 + 라우팅).

    품질 게이트(_group_is_complete): review_queue.json 전체에서 folder 그룹의 모든 엔트리를
    모아 (A) official 그룹 5채널 유형 전부 등록 여부 (B) 전 채널 발행 상태를 검사한다
    (2026-07-22 게이트 완화 — URL 회수 여부는 더 이상 완결 판정 기준이 아니다. URL 없는
    채널은 build_digest()가 채널 정본 홈으로 폴백).
    - 충족 → 실무진 문의알림방. 디제스트는 이번 사이클 부분집합이 아니라 review_queue.json의
      해당 folder 전체 채널 엔트리(5채널)로 구성 — 누락 0. SENT_LEDGER[folder]에 기록(평생 1회).
    - 미충족 → 실무진 방엔 미발송. GM 개인 방(TELEGRAM_CHAT_ID)에 사유 포함 보류 1줄만 —
      같은 folder는 SENT_LEDGER[f"{folder}:held"]로 1회만(재스팸 방지). 나중에 완결되면
      (해당 folder 키가 아직 SENT_LEDGER에 없으므로) 다음 사이클에 자동으로 표준 디제스트 발송.

    멱등: 이미 보낸 콘텐츠(그룹키가 원장에 존재)는 재발신하지 않는다 — 그룹 내 항목
    부분집합이 채널별로 나뉘어 들어와 해시가 달라져도 무관(1콘텐츠 = 통합요약 평생 1회).
    (2026-07-18 시토: 해시 비교 방식은 채널별 분할 유입 시 재발신 결함이 있어 그룹키
    존재 기준으로 강화.)
    조용한 실패 금지: 토큰/챗ID 미설정이면 [ERROR] 로그 남기고 전송 시도 없이 반환.
    반환: 실무진 방에 실제 발신(또는 dry-run 출력)한 건수(보류 알림은 미포함).
    """
    if not items:
        return 0

    token = _load_env_val(TELEGRAM_TOKEN_ENV_KEY)
    inquiry_chat_id = _load_env_val(TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY)
    if not dry_run and (not token or not inquiry_chat_id):
        print(
            "[ERROR] 발행완료 통합요약 발신 불가 — "
            f"{TELEGRAM_TOKEN_ENV_KEY} 또는 {TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY} 미설정 "
            "(telegram_bot/.env 확인 필요) — 조용히 넘어가지 않음",
            file=sys.stderr,
        )
        return 0
    gm_chat_id = _load_env_val(TELEGRAM_CHAT_ID_ENV_KEY)

    lp = ledger_path or SENT_LEDGER
    groups = group_published(items)
    all_review_items = _load_review_queue()
    ledger = _load_ledger(lp)
    sent = 0
    dirty = False
    for key, group in groups.items():
        if key in ledger:
            # 이미 발신된 콘텐츠(그룹키 존재) — 항목 부분집합·해시 변동 무관 재스팸 방지.
            # 결정 정합 신호(§4): 이미 요약 발신된 콘텐츠가 재유입돼 재발송을 막은 순간을
            # 공용 로그에 1줄 남긴다(옛것 재생 차단 증거). dry-run 은 로그를 더럽히지 않는다.
            if not dry_run:
                _replay_append(
                    "cmo-publish-digest",
                    subject=str(key),
                    detail="이미 요약 발신된 콘텐츠 재유입 — 통합요약 재발송 차단(멱등)",
                )
            continue

        complete, reason = _group_is_complete(key, all_review_items)

        if not complete:
            held_key = f"{key}:held"
            if held_key in ledger:
                continue  # 이미 GM 보류 알림 발신함(같은 folder 1회만) — 완결되면 위 ledger 체크에서 자동 발송
            group_entries = _group_all_entries(key, all_review_items) or group
            notice = _held_notice(key, reason, group_entries)
            if dry_run:
                print("[DRY-RUN] → GM 개인 업무보고봇 방 대상 (기준 미달·보류, 실전송 없음)")
                print(notice)
                print("-" * 40)
                continue  # dry-run 은 멱등 이력을 남기지 않는다(실제 발신 아님)
            if not gm_chat_id:
                print(
                    f"[ERROR] 보류 알림 발신 불가 — {TELEGRAM_CHAT_ID_ENV_KEY} 미설정 "
                    "(telegram_bot/.env 확인 필요) — 조용히 넘어가지 않음",
                    file=sys.stderr,
                )
                continue
            ok = _send(token, gm_chat_id, notice)
            if ok:
                ledger[held_key] = _group_hash(group_entries)
                dirty = True
                print(f"[INFO] 기준 미달 보류 알림 발신 완료: {key} — {reason}")
            else:
                print(f"[WARN] 기준 미달 보류 알림 발신 실패: {key}", file=sys.stderr)
            continue

        # 완결·표준 충족 — 이번 사이클 부분집합이 아니라 review_queue.json의 folder 전체
        # 채널 엔트리(5채널, 중복 채널은 축약)로 표준 디제스트를 구성한다.
        full_entries = _dedup_channel_entries(_group_all_entries(key, all_review_items) or group)
        h = _group_hash(full_entries)
        msg = build_digest(full_entries)
        preview_url = _instagram_preview_url(full_entries)
        if dry_run:
            print("[DRY-RUN] → 실무진 문의·컨택·등록 알림방 대상 (기준 충족, 실전송 없음)")
            print(msg)
            if preview_url:
                print(f"[DRY-RUN] link_preview_options.url = {preview_url}")
            print("-" * 40)
            sent += 1
            continue  # dry-run 은 멱등 이력을 남기지 않는다(실제 발신 아님)
        # GM 원안 '인스타 메인 1장 뷰' — 첫 슬라이드 이미지가 있으면 sendPhoto(캡션=디제스트),
        # 없거나 캡션이 sendPhoto 한도(1024자) 초과면 텍스트 발송으로 폴백.
        img = _first_slide_image(full_entries)
        if img and len(msg) <= 1024:
            ok = _send_photo(token, inquiry_chat_id, img, msg)
        else:
            ok = _send(token, inquiry_chat_id, msg)
        if ok:
            ledger[key] = h
            dirty = True
            sent += 1
            print(f"[INFO] 발행완료 통합요약 발신 완료: {key}")
        else:
            print(f"[WARN] 발행완료 통합요약 발신 실패: {key}", file=sys.stderr)
    if dirty:
        _save_ledger(lp, ledger)
    return sent
