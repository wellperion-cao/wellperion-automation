# scripts/publish_register.py
# 제작완료 → 자동 등록·알림 범용 헬퍼 (FIX3, 2026-06-03 AI CTO)
#
# 빌드(build_slides.py 등)가 슬라이드/몽타주 제작을 끝낸 직후 1회 호출하면:
#   (a) montage(검수 미리보기)를 가이드허브 M5 review 폴더로 캐시우회 파일명으로 복사
#   (b) review_queue.json 을 id 기준 upsert (있으면 update·없으면 append)
#       - status='검수대기' (단, 이미 '발행완료' 인 엔트리는 status 강등 금지)
#       - preview/slides/caption/location/mentions/collaborators/account/folder/channel/title 세팅
#       - 다른 엔트리·파일 절대 삭제 안 함 (id 매칭 1건만 손댐)
#   (c) 텔레그램 1줄 보고 + montage 사진 발송 (토큰 stdout 노출 금지)
#
# 향후 다른 콘텐츠 폴더에서도 import 해서 register_publish(...) 호출만 하면 됨.
#
# 사용 예 (build_slides.py main 끝):
#   from publish_register import register_publish
#   register_publish(
#       content_folder=FOLDER, slug="260603_AI4_역할분담",
#       montage_path=montage, caption=CAPTION, location="웰페리온 스포츠클럽",
#       mentions=[],  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정
#       account="namuk.wellperion",
#       slides=[p.relative_to(ROOT).as_posix() for p in paths],
#       queue_id="CMO-2026-06-03-AI4-역할분담", title="AI #4편 — 역할 분담(개인계정)",
#       channel="인스타그램 (namuk.wellperion)",
#   )
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

# -----------------------------------------------------------------
# 콘솔 인코딩 하드닝 — Windows cp949 콘솔에서 대시(—)·이모지 print 시
# UnicodeEncodeError 로 죽지 않게 stdout/stderr 를 UTF-8(replace)로 강제.
# -----------------------------------------------------------------
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconf = getattr(_stream, "reconfigure", None) if _stream is not None else None
    if _reconf is not None:
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
REVIEW_DIR = ROOT / "3. 웰페리온 가이드" / "cmo" / "review"
REVIEW_QUEUE_PATH = REVIEW_DIR / "review_queue.json"
ENV_PATH = ROOT / "telegram_bot" / ".env"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot (CLAUDE.md §3)

# status='발행완료' 인 엔트리는 검수대기로 강등 금지 (회귀 가드)
_TERMINAL_PUBLISHED = "발행완료"


def _load_telegram_token() -> str:
    """telegram_bot/.env 또는 환경변수에서 봇 토큰 로드. 토큰 값은 절대 출력 안 함."""
    token = os.environ.get(TELEGRAM_TOKEN_ENV_KEY, "").strip()
    if token:
        return token
    # .env 직접 파싱 (python-dotenv 미설치 환경 대비 — 의존성 없이 동작)
    try:
        if ENV_PATH.exists():
            for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == TELEGRAM_TOKEN_ENV_KEY:
                    return val.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _telegram_send_photo(photo_path: Path, caption: str) -> None:
    """montage 사진 + 1줄 캡션 발송. 실패해도 절대 예외로 죽지 않음(토큰 trace 미출력)."""
    token = _load_telegram_token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — montage 발송 생략 (env: TELEGRAM_BOT_TOKEN)")
        return
    if not photo_path.exists():
        print(f"[WARN] montage 파일 미존재 — 텍스트만 발송 시도: {photo_path}")
        _telegram_send_message(caption)
        return
    try:
        import urllib.request
        import uuid

        boundary = f"----wp{uuid.uuid4().hex}"
        url = f"https://api.telegram.org/bot{token}/sendPhoto"

        def _field(name: str, value: str) -> bytes:
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")

        photo_bytes = photo_path.read_bytes()
        body = bytearray()
        body += _field("chat_id", TELEGRAM_CHAT_ID)
        body += _field("caption", caption)
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="{photo_path.name}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode("utf-8")
        body += photo_bytes
        body += f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            url,
            data=bytes(body),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = resp.status == 200
        log_outbound(caption, chat_id=TELEGRAM_CHAT_ID, source="publish_register._telegram_send_photo", ok=ok, kind="sendPhoto")
        print(f"[INFO] 텔레그램 montage 발송 {'성공' if ok else '실패'} (chat={TELEGRAM_CHAT_ID})")
    except Exception:
        # 토큰 trace 노출 방지 — 예외 상세 미출력
        log_outbound(caption, chat_id=TELEGRAM_CHAT_ID, source="publish_register._telegram_send_photo", ok=False, kind="sendPhoto")
        print("[WARN] 텔레그램 montage 발송 실패 (상세 미출력 — 토큰 trace 노출 방지)")


def _telegram_send_message(text: str) -> None:
    """1줄 텍스트 보고 (montage 없거나 사진 발송 실패 시 폴백). 토큰 trace 미출력."""
    token = _load_telegram_token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 보고 생략")
        return
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
        log_outbound(text, chat_id=TELEGRAM_CHAT_ID, source="publish_register._telegram_send_message", ok=ok, kind="sendMessage")
        print(f"[INFO] 텔레그램 보고 {'성공' if ok else '실패'}")
    except Exception:
        log_outbound(text, chat_id=TELEGRAM_CHAT_ID, source="publish_register._telegram_send_message", ok=False, kind="sendMessage")
        print("[WARN] 텔레그램 보고 실패 (토큰 trace 노출 방지)")


def _copy_preview(montage_path: Path, slug: str) -> str | None:
    """montage 를 review 폴더로 캐시우회 파일명(타임스탬프)으로 복사.

    반환: 배포루트(`3. 웰페리온 가이드`) 기준 정방향 슬래시 상대경로 (review_queue.preview = M5 img src 호환).
    ※ ROOT 기준이면 '3. 웰페리온 가이드/' 접두사가 붙어 M5에서 404(미리보기 깨짐) — 배포루트 기준 필수.
    실패 시 None (등록은 계속 진행).
    """
    try:
        if not montage_path.exists():
            print(f"[WARN] montage 미존재 — preview 복사 건너뜀: {montage_path}")
            return None
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        ext = montage_path.suffix or ".png"
        dest = REVIEW_DIR / f"{slug}_preview_{ts}{ext}"
        shutil.copyfile(montage_path, dest)
        rel = dest.relative_to(REVIEW_DIR.parent.parent).as_posix()  # 배포루트(가이드 폴더) 기준 → cmo/review/...
        print(f"[INFO] preview 복사 완료(캐시우회) → {rel}")
        return rel
    except Exception as exc:
        print(f"[WARN] preview 복사 예외 (등록 계속): {exc}")
        return None


def _upsert_queue(
    queue_id: str,
    fields: dict,
) -> tuple[bool, str]:
    """review_queue.json 을 id 기준 upsert.

    - id 매칭 엔트리 있으면 update, 없으면 append.
    - 이미 status='발행완료' 인 엔트리는 status 를 '검수대기'로 강등하지 않음(회귀 가드).
      단 preview/slides/caption 등 본문 필드는 갱신(최신 미리보기 반영).
    - 다른 엔트리·파일 절대 삭제 안 함.
    반환: (matched(=update 여부), 최종 status).
    """
    if not REVIEW_QUEUE_PATH.exists():
        print(f"[WARN] review_queue.json 미존재 — 신규 생성: {REVIEW_QUEUE_PATH}")
        queue: list[dict] = []
    else:
        try:
            loaded = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
            queue = loaded if isinstance(loaded, list) else []
        except Exception as exc:
            print(f"[ERROR] review_queue 파싱 실패 — 등록 중단(파일 보존): {exc}")
            raise

    matched_item: dict | None = None
    for item in queue:
        if item.get("id") == queue_id:
            matched_item = item
            break

    if matched_item is not None:
        prev_status = matched_item.get("status", "")
        # 본문 필드 갱신 (status 제외)
        for k, v in fields.items():
            if k == "status":
                continue
            matched_item[k] = v
        # status 강등 가드 — 발행완료는 검수대기로 내리지 않음
        if prev_status == _TERMINAL_PUBLISHED:
            print(
                f"[INFO] id={queue_id} 는 이미 '발행완료' — status 강등 금지(유지). "
                f"본문 필드만 갱신."
            )
            final_status = _TERMINAL_PUBLISHED
        else:
            final_status = fields.get("status", prev_status or "검수대기")
            matched_item["status"] = final_status
        print(f"[INFO] review_queue update — id={queue_id} / status={final_status}")
        result = (True, final_status)
    else:
        new_item = dict(fields)
        new_item["id"] = queue_id
        new_item.setdefault("status", "검수대기")
        queue.append(new_item)
        print(f"[INFO] review_queue append(신규) — id={queue_id} / status={new_item['status']}")
        result = (False, new_item["status"])

    REVIEW_QUEUE_PATH.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _write_curation_md(
    content_folder: Path,
    caption: str,
    location: str,
    mentions: list[str],
    collaborators: list[str],
) -> None:
    """발행기 필수 입력 큐레이션_추천.md 자동 생성 (2026-06-04 누락 재발방지 A-i).

    제작완료 시점에 항상 생성 → 사람이 '잊을 수 없게' 한다(오늘 3회 실패 원인 #1 차단).
    review_queue 의 caption 단일 출처를 그대로 ## post A 단일 슬롯으로 직렬화.
    이미 존재하면 덮어써 최신 caption 과 동기화한다(desync 방지).
    실패해도 빌드/등록은 깨지 않음(상위 try/except 격리).
    """
    md_path = Path(content_folder) / "큐레이션_추천.md"
    lines: list[str] = [
        "# 큐레이션_추천 (자동 생성 — register_publish · 발행기 필수 입력)",
        "",
        "> 이 파일은 제작완료 시 자동 생성됩니다. review_queue.json 의 caption 단일 출처를 직렬화한 것.",
        "> 수동 발행기(--mode publish)가 큐레이션 누락으로 즉사하지 않게 하는 안전판입니다.",
        "",
        "## post A",
        "",
        "### 캡션",
        caption.strip(),
        "",
        "### 위치",
        (location or "").strip(),
        "",
        "### 멘션",
        " ".join(("@" + m.lstrip("@")) for m in mentions) if mentions else "",
        "",
        "### Collaborator",
        "\n".join(("@" + c.lstrip("@")) for c in collaborators) if collaborators else "",
        "",
        "### 종목",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[INFO] 큐레이션_추천.md 자동 생성/갱신 → {md_path}")


def register_publish(
    content_folder: Path,
    slug: str,
    montage_path: Path,
    caption: str,
    location: str = "",
    mentions: list[str] | None = None,
    account: str = "namuk.wellperion",
    slides: list[str] | None = None,
    queue_id: str | None = None,
    title: str | None = None,
    channel: str | None = None,
    collaborators: list[str] | None = None,
) -> None:
    """제작완료 → 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송 범용 헬퍼.

    어떤 단계가 실패해도 빌드 자체는 깨지 않음(광범위 try/except 격리).
    review_queue 다른 엔트리·파일은 절대 삭제하지 않음 (id 매칭 1건만 손댐).
    """
    try:
        content_folder = Path(content_folder)
        montage_path = Path(montage_path)
        mentions = mentions or []
        slides = slides or []
        collaborators = collaborators or []
        queue_id = queue_id or slug
        title = title or slug
        channel = channel or f"인스타그램 ({account})"
        # folder = ROOT 기준 상대경로 (review_queue 표준 — 정방향 슬래시)
        try:
            folder_rel = content_folder.relative_to(ROOT).as_posix()
        except Exception:
            folder_rel = content_folder.as_posix()

        # (a0) 발행기 필수 입력 큐레이션_추천.md 자동 생성 (누락 재발방지 A-i)
        try:
            _write_curation_md(content_folder, caption, location, mentions, collaborators)
        except Exception as exc:
            print(f"[WARN] 큐레이션_추천.md 자동 생성 예외 (등록 계속 — 큐 caption 폴백 가능): {exc}")

        # (a) preview 복사 (캐시우회 파일명)
        preview_rel = _copy_preview(montage_path, slug)

        # (b) review_queue upsert (id 기준)
        fields: dict = {
            "title": title,
            "channel": channel,
            "account": account,
            "folder": folder_rel,
            "slides": slides,
            "caption": caption,
            "location": location,
            "collaborators": collaborators,
            "mentions": mentions,
            "status": "검수대기",
        }
        if preview_rel:
            fields["preview"] = preview_rel
        try:
            matched, final_status = _upsert_queue(queue_id, fields)
        except Exception as exc:
            print(f"[WARN] review_queue upsert 예외 (제작은 완료): {exc}")
            matched, final_status = (False, "검수대기")

        # (c) 텔레그램 1줄 + montage 발송
        action = "갱신" if matched else "신규 등록"
        msg = (
            f"🎨 제작완료 — {title}\n"
            f"M5 {action}(status={final_status}) · 채널 {channel}\n"
            f"가이드허브 M5에서 미리보기·검수\n"
            f"https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M5"
        )
        _telegram_send_photo(montage_path, msg)

        print(f"[OK] register_publish 완료 — id={queue_id} / status={final_status} / preview={preview_rel}")
    except Exception as exc:
        # 절대 빌드를 깨지 않음
        print(f"[WARN] register_publish 전체 예외 (제작 결과는 유효): {exc}")
