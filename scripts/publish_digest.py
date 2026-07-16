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

멱등: scripts/.publish_digest_sent.json 에 그룹키 → 해시(항목id·url·published_at 조합)
      저장. 같은 콘텐츠를 재실행해도 해시가 같으면 재발신하지 않는다(재스팸 방지).

★ 조용한 실패 금지: 토큰·챗ID 미설정이면 stderr에 [ERROR] 로그를 남기고 전송을
  시도하지 않는다 — 성공한 척 조용히 넘어가지 않는다.
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
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
ENV_FILE = ROOT / "telegram_bot" / ".env"
SENT_LEDGER = ROOT / "scripts" / ".publish_digest_sent.json"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY = "TELEGRAM_INQUIRY_CHAT_ID"  # 문의·컨택·등록 알림방

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
        entries.append((order, label, url))
    entries.sort(key=lambda e: e[0])
    for _, label, url in entries:
        lines.append(label)
        lines.append(url if url else "게시됨 · 채널에서 확인")
    lines.append("")
    lines.append("좋아요·댓글로 응원 부탁드립니다 🙏")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 멱등 — 그룹키 + 내용 해시로 1콘텐츠 1회 보장
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
    """발행완료 항목들을 콘텐츠 단위로 묶어 문의·컨택·등록 알림방에 통합요약 1건씩 발신.

    멱등: 이미 보낸 콘텐츠(그룹키+해시 동일)는 재발신하지 않는다.
    조용한 실패 금지: 토큰/챗ID 미설정이면 [ERROR] 로그 남기고 전송 시도 없이 반환.
    반환: 실제 발신(또는 dry-run 출력)한 건수.
    """
    if not items:
        return 0

    token = _load_env_val(TELEGRAM_TOKEN_ENV_KEY)
    chat_id = _load_env_val(TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY)
    if not dry_run and (not token or not chat_id):
        print(
            "[ERROR] 발행완료 통합요약 발신 불가 — "
            f"{TELEGRAM_TOKEN_ENV_KEY} 또는 {TELEGRAM_INQUIRY_CHAT_ID_ENV_KEY} 미설정 "
            "(telegram_bot/.env 확인 필요) — 조용히 넘어가지 않음",
            file=sys.stderr,
        )
        return 0

    lp = ledger_path or SENT_LEDGER
    groups = group_published(items)
    ledger = _load_ledger(lp)
    sent = 0
    dirty = False
    for key, group in groups.items():
        h = _group_hash(group)
        if ledger.get(key) == h:
            continue  # 이미 같은 내용으로 발신됨 — 재스팸 방지
        msg = build_digest(group)
        preview_url = _instagram_preview_url(group)
        if dry_run:
            print("[DRY-RUN] → 문의·컨택·등록 알림방 대상 (실전송 없음)")
            print(msg)
            if preview_url:
                print(f"[DRY-RUN] link_preview_options.url = {preview_url}")
            print("-" * 40)
            sent += 1
            continue  # dry-run 은 멱등 이력을 남기지 않는다(실제 발신 아님)
        # GM 원안 '인스타 메인 1장 뷰' — 첫 슬라이드 이미지가 있으면 sendPhoto(캡션=디제스트),
        # 없거나 캡션이 sendPhoto 한도(1024자) 초과면 텍스트 발송으로 폴백.
        img = _first_slide_image(group)
        if img and len(msg) <= 1024:
            ok = _send_photo(token, chat_id, img, msg)
        else:
            ok = _send(token, chat_id, msg)
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
