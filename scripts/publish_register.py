# scripts/publish_register.py
# 제작완료 → 자동 등록·알림 범용 헬퍼 (FIX3, 2026-06-03 AI CTO)
#
# 빌드(build_slides.py 등)가 슬라이드/몽타주 제작을 끝낸 직후 1회 호출하면:
#   (a) montage(검수 미리보기)를 웰페리온 ERP M5 review 폴더로 캐시우회 파일명으로 복사
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
    from tg_outbound_log import log_outbound, pace
except Exception:
    def log_outbound(*a, **k):
        pass
    def pace(*a, **k):
        return None

try:  # 저신호 무음 플래그(best-effort) — 임포트 실패해도 발신 무영향(False 폴백)
    _tgb = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'telegram_bot'))
    if _tgb not in sys.path:
        sys.path.insert(0, _tgb)
    from notify_prefs import muted
except Exception:
    def muted(kind: str) -> bool:
        return False

# scripts/ 자기 자신을 sys.path 에 보장(호출부가 이미 넣어둔 경우가 대부분이지만,
# register_channel_review 재사용 import 가 항상 되게 하는 안전망). (배834-A, 2026-07-20)
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

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
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"

# status='발행완료' 인 엔트리는 검수대기로 강등 금지 (회귀 가드)
_TERMINAL_PUBLISHED = "발행완료"


def _load_env_value(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드. 값은 절대 stdout 미출력."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    # .env 직접 파싱 (python-dotenv 미설치 환경 대비 — 의존성 없이 동작)
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
    """telegram_bot/.env 또는 환경변수에서 봇 토큰 로드. 토큰 값은 절대 출력 안 함."""
    return _load_env_value(TELEGRAM_TOKEN_ENV_KEY)


TELEGRAM_CHAT_ID: str = _load_env_value(TELEGRAM_CHAT_ID_ENV_KEY)  # telegram_bot/.env SSOT


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
        pace()
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
        pace()
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


# ─────────────────────────────────────────────────────────────────────────────
# 채널 형제 자동등록 (배834-A, 2026-07-20 필라테스 L4 사고 재발방지)
#   IG 엔트리 등록 시, 콘텐츠 폴더에 이미 채널별 본문(블로그·카페·카카오·당근)이 준비돼
#   있으면 register_channel_review.register_channels() 를 그대로 재사용해 형제 검수
#   엔트리를 자동 upsert 한다. 본문 파일이 실제로 존재하는 채널만 대상 — 없는 채널은
#   지어내지 않는다(파일 존재가 유일 트리거). 공식계정(wellperion)만 대상 — 개인계정
#   (namuk.wellperion 등)은 멀티채널 발행 대상이 아니므로 조용히 건너뜀.
# ─────────────────────────────────────────────────────────────────────────────
_SIBLING_CHANNEL_SPECS: list[tuple[str, str, str, str, dict]] = [
    # (id 접미사, 채널명, 서브폴더, 본문 파일명, 추가 필드)
    ("BLOG",   "네이버 블로그",           "output(블로그)",       "_blog_body.txt", {}),
    ("CAFE",   "네이버 카페 (동부이촌동)", "output(카페)",         "_cafe_body.txt", {"menuid": 659}),
    ("KAKAO",  "카카오 채널",             "output(카카오 채널)",  "kakao_copy.md",  {}),
    ("DANGGN", "당근채널",                "output(당근)",         "danggn_copy.md", {}),
]


def _sibling_base_id(queue_id: str) -> str:
    """형제 id 접두사 계산 — 대표 id 끝의 '-OFFICIAL-IG'/'-IG' 접미사를 제거한 베이스."""
    for suffix in ("-OFFICIAL-IG", "-IG"):
        if queue_id.endswith(suffix):
            return queue_id[: -len(suffix)]
    return queue_id


def _auto_register_channel_siblings(
    content_folder: Path, queue_id: str, title: str, account: str,
) -> list[str]:
    """콘텐츠 폴더에 이미 만들어진 채널별 본문이 있으면 형제 검수 엔트리 자동 upsert.

    ★ register_channel_review.register_channels() 를 그대로 재사용 — 등록 로직 중복 작성 금지.
    실패해도 IG 등록은 이미 끝났으므로 죽지 않는다(호출부에서 예외 격리 — best-effort).
    반환: 실제 upsert 된 형제 id 리스트(승인 카드 그룹핑용, 비어있으면 형제 없음/해당無).
    """
    if account != "wellperion":
        return []  # 개인계정 — 멀티채널 대상 아님(조용히 건너뜀)

    try:
        from register_channel_review import register_channels
    except Exception as exc:
        print(f"[WARN] register_channel_review import 실패 — 형제 채널 자동등록 생략: {exc}")
        return []

    try:
        folder_rel = content_folder.relative_to(ROOT).as_posix()
    except Exception:
        folder_rel = content_folder.as_posix()

    base_id = _sibling_base_id(queue_id)
    channels: list[dict] = []
    for suffix, ch_label, subdir, body_name, extra in _SIBLING_CHANNEL_SPECS:
        body_path = content_folder / subdir / body_name
        if not body_path.exists():
            continue  # 이 채널 본문 없음 — 생성 안 함(존재하는 채널만 자동 등록)
        entry = {
            "id": f"{base_id}-{suffix}",
            "title": f"{title} — {ch_label}",
            "channel": ch_label,
            "account": account,
            "body_file": f"{folder_rel}/{subdir}/{body_name}",
            "image_dir": f"{folder_rel}/{subdir}",
            "image_glob": "*.jpg",
        }
        entry.update(extra)
        channels.append(entry)

    if not channels:
        return []

    try:
        register_channels(
            folder_rel=folder_rel,
            # folder/output/ 마스터 슬라이드 재복사 없음(채널별 이미지 이미 각 서브폴더에 존재) —
            # 존재하지 않는 글롭을 줘서 register_channels 의 슬라이드 복사 단계를 안전하게 no-op화.
            slide_glob="__NO_MASTER_SLIDES_TO_COPY__.jpg",
            channels=channels,
            preview_slug=base_id,
        )
    except Exception as exc:
        print(f"[WARN] 형제 채널 register_channels 예외(IG 등록은 유효): {exc}")
        return []

    ids = [c["id"] for c in channels]
    print(f"[INFO] 형제 채널 자동등록 — {len(ids)}건: {ids}")
    return ids


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
    send_card: bool = False,
) -> None:
    """제작완료 → 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송 범용 헬퍼.

    어떤 단계가 실패해도 빌드 자체는 깨지 않음(광범위 try/except 격리).
    review_queue 다른 엔트리·파일은 절대 삭제하지 않음 (id 매칭 1건만 손댐).

    send_card — True 면 montage 발송 뒤 scripts/send_review_card.py --id <queue_id> 를
        subprocess 로 1회 호출해 [✅승인]/[❌반려] 버튼 카드까지 발송한다(실패해도 경고만).
        ⚠️ 기본 False — 자동생성기(ig_series_producer.py)는 send_review_card 를 별도 호출하므로
        절대 send_card=True 로 부르면 안 됨(카드 중복 방지). 수동 build_slides 경로만 True.
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

        # (b2) 채널 형제 자동등록 — 콘텐츠 폴더에 블로그·카페·카카오·당근 본문이 이미
        # 준비돼 있으면 형제 검수 엔트리를 함께 upsert (배834-A, 필라테스 L4 사고 재발방지).
        # 실패해도 IG 등록은 이미 끝났으므로 죽지 않음(best-effort).
        try:
            sibling_ids = _auto_register_channel_siblings(content_folder, queue_id, title, account)
        except Exception as exc:
            print(f"[WARN] 형제 채널 자동등록 예외(IG 등록은 유효): {exc}")
            sibling_ids = []

        # (c) 텔레그램 1줄 + montage 발송
        action = "갱신" if matched else "신규 등록"
        msg = (
            f"🎨 제작완료 — {title}\n"
            f"M5 {action}(status={final_status}) · 채널 {channel}\n"
            f"웰페리온 ERP M5에서 미리보기·검수\n"
            f"https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M5"
        )
        try:
            skip_produce_done = muted("produce_done")
        except Exception:
            skip_produce_done = False
        if skip_produce_done:
            print("[무음] produce_done 저신호 설정 — 제작완료 사진카드 발송 스킵 (notify_prefs.py)")
        else:
            _telegram_send_photo(montage_path, msg)

        # (d) 수동 경로 승인버튼 카드 — send_card=True 일 때만 (자동생성기는 별도 호출이라 무영향).
        #     montage(버튼 없음) 뒤 [✅승인]/[❌반려] 버튼 카드 1회. 실패해도 등록은 유효(경고만).
        #     형제 채널이 자동등록됐으면(sibling_ids) --group-ids 로 묶어 GM이 카드 1장을
        #     [승인]하면 IG+형제 채널이 함께 승인·발행되게 한다(GM 지시 — 발행 로직은 불변,
        #     기존 워처의 채널별 dispatch_publish 경로를 그대로 탄다).
        if send_card:
            try:
                import subprocess

                card_script = ROOT / "scripts" / "send_review_card.py"
                cmd = [sys.executable, str(card_script), "--id", str(queue_id)]
                if sibling_ids:
                    cmd += ["--group-ids", ",".join([str(queue_id), *sibling_ids])]
                proc = subprocess.run(
                    cmd,
                    cwd=str(ROOT), timeout=60,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                if proc.returncode == 0:
                    print(f"[INFO] 승인버튼 카드 발송 호출 성공 — id={queue_id}")
                else:
                    print(f"[WARN] 승인버튼 카드 발송 실패(rc={proc.returncode}) — 등록은 유효. "
                          f"수동: send_review_card.py --id {queue_id}")
                if proc.stdout:
                    print(proc.stdout.strip())
            except Exception as exc:
                print(f"[WARN] 승인버튼 카드 발송 예외(등록은 유효): {exc}")

        print(f"[OK] register_publish 완료 — id={queue_id} / status={final_status} / preview={preview_rel}")
    except Exception as exc:
        # 절대 빌드를 깨지 않음
        print(f"[WARN] register_publish 전체 예외 (제작 결과는 유효): {exc}")
