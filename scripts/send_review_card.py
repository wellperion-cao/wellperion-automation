"""콘텐츠 검수 카드 발송기 (2026-06-03, IG 폴링 감시기 폐기 대체).

검수대기 콘텐츠를 GM 텔레그램으로 [✅승인][❌반려] 인라인 버튼 카드로 발송한다.
GM이 [✅승인] 탭 → bot.py 의 cmd_publish_callback(pub:<id>:approve) 가 받아
그 순간 발행 엔진(ig_review_publish_watcher.py --once)을 1회 호출한다(폴링 없음).

CMO 가 콘텐츠를 review_queue.json 에 status='검수대기' 로 적재한 직후 이 스크립트를
호출하면 된다.

실행:
  특정 id 카드:        python scripts\\send_review_card.py --id CMO-2026-06-03-XXX
  검수대기 전체 카드:   python scripts\\send_review_card.py --all-pending
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import urllib.parse
import urllib.request

try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound, pace, send as _tg_gateway_send
except Exception:
    def log_outbound(*a, **k):
        pass
    def pace(*a, **k):
        return None
    def _tg_gateway_send(*a, **k):
        return None

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
QUEUE = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
M1_URL = "https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M1"

# 형제 채널 id 접미사 — publish_register.py _SIBLING_CHANNEL_SPECS 와 동일 규칙(배834 계열).
# 여기서 재정의(직접 import 안 함)하는 이유: 이 스크립트는 카드 발송 단독 진입점(빈번한
# subprocess 호출)이라 publish_register 임포트 부담·부작용을 지지 않는다(자기완결 유지).
_SIBLING_ID_SUFFIXES = ("BLOG", "CAFE", "KAKAO", "DANGGN")
_SIBLING_MERGEABLE_STATUSES = ("검수대기", "승인")

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"
# 건별 마지막 카드 상태 저장 — 같은 건 재발송 시 이전 카드 자동 삭제(카드 1개만 유지)
# 값 스키마: {item_id: {"msg_id": int, "sig": str(caption해시), "ts": float}}
#   (구버전 평면 int 도 _load_msgids 에서 신스키마로 흡수 — 하위호환)
CARD_MSGID_STORE = ROOT / "scripts" / ".review_card_msgids.json"
# 동시 호출(11초 내 2회 발송 같은 사고) 직렬화용 파일 락 + 콘텐츠당 1회 재발송 차단 창(초)
CARD_LOCK = ROOT / "scripts" / ".review_card.lock"
DEDUP_WINDOW_SEC = 90  # 같은 콘텐츠·동일 내용 카드의 재발송을 막는 시간 창
# 그룹 id 매핑 저장소 — callback_data 64바이트 한계 우회용 (hash→[id,...])
CARD_GROUPS_STORE = ROOT / "scripts" / ".review_card_groups.json"


def _env_val(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    env = ROOT / "telegram_bot" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def _token() -> str:
    return _env_val(TELEGRAM_TOKEN_ENV_KEY)


TELEGRAM_CHAT_ID: str = _env_val(TELEGRAM_CHAT_ID_ENV_KEY)  # telegram_bot/.env SSOT


def _preview_photo(item: dict) -> Path | None:
    """검수카드에 첨부할 montage 미리보기 로컬 경로.
    preview(배포루트 상대 cmo/review/...) 우선, 없으면 폴더 output/_검수_미리보기_*.png."""
    guide_root = ROOT / "3. 웰페리온 가이드"
    prev = item.get("preview") or ""
    if prev:
        p = guide_root / prev
        if p.exists():
            return p
    folder = item.get("folder") or ""
    if folder:
        out = ROOT / folder / "output"
        if out.exists():
            cands = sorted(out.glob("_검수_미리보기_*.png"))
            if cands:
                return cands[0]
    return None


def _caption_sig(item: dict) -> str:
    """콘텐츠 동일성 판정용 서명. id + title + folder 로 안정 해시(내용 바뀌면 갱신).
    교체·폐기 후 새 내용으로 다시 올리면 sig 가 달라져 새 카드 1장이 정상 발송된다."""
    base = "|".join([
        str(item.get("id", "")),
        str(item.get("title", "")),
        str(item.get("folder", "")),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _load_msgids() -> dict:
    """저장소 로드 + 신스키마({msg_id,sig,ts}) 정규화(구버전 평면 int 흡수)."""
    raw = {}
    try:
        if CARD_MSGID_STORE.exists():
            raw = json.loads(CARD_MSGID_STORE.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    out: dict = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict):
                out[k] = v
            else:  # 구버전: 값이 message_id(int) 단일
                out[k] = {"msg_id": v, "sig": "", "ts": 0}
    return out


def _acquire_lock(timeout: float = 25.0) -> bool:
    """카드 발송 직렬화 락 획득(동시 2회 발송 사고 방지). 획득 실패해도 발송은 진행(best-effort)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fd = os.open(str(CARD_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return True
        except FileExistsError:
            # 스테일 락(60초 초과) 회수
            try:
                if time.time() - CARD_LOCK.stat().st_mtime > 60:
                    CARD_LOCK.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            time.sleep(0.3)
        except Exception:
            return False
    return False


def _release_lock() -> None:
    try:
        CARD_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


def _save_msgids(d: dict) -> None:
    try:
        CARD_MSGID_STORE.write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _delete_message(token: str, msg_id: int) -> bool:
    """봇이 보낸 이전 카드 삭제(48시간 내 가능). 실패는 무시(이미 지웠거나 만료)."""
    data = urllib.parse.urlencode(
        {"chat_id": TELEGRAM_CHAT_ID, "message_id": msg_id}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/deleteMessage", data=data, method="POST")
    try:
        pace()
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def _send_text_card(token: str, caption: str, keyboard: dict, item_id: str) -> int | None:
    """이미지 없을 때 텍스트 카드 폴백. message_id 반환(실패 None).
    발신 관문(tg_outbound_log.send) 경유 — 페이싱·429재시도·로깅 자동 편입(배255 3차,
    2026-08-17). full_response=True 로 응답 dict 를 받아 message_id 를 뽑는다."""
    resp = _tg_gateway_send(
        token, TELEGRAM_CHAT_ID, caption,
        source="send_review_card._send_text_card", kind="sendMessage",
        extra={"parse_mode": "HTML", "disable_web_page_preview": "true",
               "reply_markup": json.dumps(keyboard, ensure_ascii=False)},
        timeout=10, full_response=True,
    )
    mid = (resp or {}).get("result", {}).get("message_id")
    print(f"[INFO] 카드(텍스트 폴백) 발송 {'성공' if mid else '실패'}: {item_id}")
    return mid


def _send_photo_card(token: str, caption: str, keyboard: dict,
                     photo: Path, item_id: str) -> int | None:
    """sendPhoto (montage 이미지 + caption + 인라인 버튼). message_id 반환(실패 None).
    발신 관문(tg_outbound_log.send) 경유 — 페이싱·429재시도·로깅 자동 편입(배255 3차,
    2026-08-17). 업로드 시간은 관문이 파일 크기를 보고 잡는다(tg_outbound_log.send)."""
    resp = _tg_gateway_send(
        token, TELEGRAM_CHAT_ID, caption,
        source="send_review_card._send_photo_card", kind="sendPhoto", photo=str(photo),
        extra={"parse_mode": "HTML", "reply_markup": json.dumps(keyboard, ensure_ascii=False)},
        timeout=20, full_response=True,
    )
    mid = (resp or {}).get("result", {}).get("message_id")
    print(f"[INFO] 검수카드(이미지) 발송 {'성공' if mid else '실패'}: {item_id}")
    if mid is None:
        print("[WARN] 검수카드(이미지) 발송 실패 — 텍스트 폴백 시도")
    return mid


def send_card(item: dict, force: bool = False,
              group_ids: list | None = None) -> bool:
    """검수 카드 1건 발송 — montage 미리보기 이미지 + [승인]/[반려] 버튼.

    group_ids: 복수 id 일괄 승인용. 지정 시 버튼 callback_data가
               pub:<id1,id2,...>:approve 형태로 생성된다. 카드 대표 item(미리보기·제목)은
               item 인자를 사용. 중복 가드 키는 item.id 기준.

    콘텐츠당 1회 보장: 동시 호출은 파일 락으로 직렬화하고, 같은 콘텐츠(동일 내용 sig)의
    카드가 DEDUP_WINDOW_SEC 내 이미 나가 있으면 재발송을 스킵한다(11초 내 2회 발송 사고 차단).
    내용이 바뀐 교체본은 sig 가 달라져 새 카드 1장만 발송(이전 카드는 삭제). force=True 면 가드 무시.
    이미지 없으면 텍스트 폴백. (토큰 stdout 노출 금지)"""
    token = _token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 발송 생략")
        return False
    item_id = item.get("id", "")
    title = item.get("title", item_id)
    channel = item.get("channel", "")
    folder = item.get("folder", "")
    sig = _caption_sig(item)

    locked = _acquire_lock()
    try:
        # 콘텐츠당 1회 가드: 동일 sig 카드가 최근(창 이내) 이미 발송됐으면 재발송 스킵
        if not force:
            store0 = _load_msgids()
            prev = store0.get(item_id) or {}
            if (
                prev.get("msg_id")
                and prev.get("sig") == sig
                and (time.time() - float(prev.get("ts") or 0)) < DEDUP_WINDOW_SEC
            ):
                print(
                    f"[INFO] 콘텐츠당 1회 가드 - 동일 카드 최근 발송됨(스킵): {item_id} "
                    f"msg_id={prev.get('msg_id')}"
                )
                return True
        return _do_send_card(token, item, item_id, title, channel, folder, sig,
                             group_ids=group_ids)
    finally:
        if locked:
            _release_lock()


def _write_group(group_ids: list) -> str:
    """group_ids 를 .review_card_groups.json 에 저장하고 10자 sha1 해시키를 반환.
    callback_data 64바이트 한계 우회용 — bot.py 가 이 파일로 해시→id목록 역조회."""
    key = hashlib.sha1(",".join(group_ids).encode("utf-8")).hexdigest()[:10]
    try:
        store: dict = {}
        if CARD_GROUPS_STORE.exists():
            try:
                store = json.loads(CARD_GROUPS_STORE.read_text(encoding="utf-8"))
            except Exception:
                store = {}
        store[key] = group_ids
        CARD_GROUPS_STORE.write_text(
            json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return key


def _do_send_card(token, item, item_id, title, channel, folder, sig,
                  group_ids: list | None = None) -> bool:
    """group_ids 가 있으면 카드 1장으로 복수 id 일괄 승인 버튼을 생성한다.
    callback_data 64바이트 한계 → 해시키 방식: pub:grp:<hash>:approve"""

    if group_ids:
        grp_hash = _write_group(group_ids)
        cb_approve = f"pub:grp:{grp_hash}:approve"
        cb_reject  = f"pub:grp:{grp_hash}:reject"
        ch_label = f"{len(group_ids)}개 채널 일괄"
    elif len(f"pub:{item_id}:approve".encode("utf-8")) > 60:
        # ★id 가 길면 callback_data 가 텔레그램 64바이트 한계를 넘어 버튼이 통째로 안 붙는다
        #   (카드는 그대로 나가고 승인만 못 하게 되므로 실패로 보이지 않는다 — 가장 나쁜 종류).
        #   접수 id 에 시각을 넣으면서 실측 63바이트까지 찼다(2026-08-05). 한 글자만 더 길어지면
        #   끊긴다 → 그룹용 해시 우회를 단일 건에도 그대로 쓴다(새 장치 만들지 않는다).
        grp_hash = _write_group([item_id])
        cb_approve = f"pub:grp:{grp_hash}:approve"
        cb_reject  = f"pub:grp:{grp_hash}:reject"
        ch_label = channel
    else:
        cb_approve = f"pub:{item_id}:approve"
        cb_reject  = f"pub:{item_id}:reject"
        ch_label = channel

    # 발행 품질 게이트 경고(배10038) — review_queue_util._apply_quality_gate 가 등록 시점에
    # item['qc_flags'] 로 남긴 것을 그대로 노출. 차단은 안 하되 GM이 승인 전에 보게 한다.
    #
    # 일괄 승인 카드(group_ids)는 버튼 한 번에 형제 채널이 전부 발행된다 → 대표 item 의
    # 경고만 보이면 나머지 채널의 위반을 GM이 못 보고 승인하게 된다. 그래서 그룹이면
    # 형제 전원의 qc_flags 를 모아 노출한다(2026-07-25).
    qc_flags = list(item.get("qc_flags") or [])
    if group_ids:
        try:
            _all = json.loads(QUEUE.read_text(encoding="utf-8"))
            _by_id = {x.get("id"): x for x in (_all if isinstance(_all, list) else [])}
            for _gid in group_ids:
                if _gid == item_id:
                    continue
                for _f in (_by_id.get(_gid, {}).get("qc_flags") or []):
                    _labeled = f"[{_by_id[_gid].get('channel') or _gid}] {_f}"
                    if _labeled not in qc_flags:
                        qc_flags.append(_labeled)
        except Exception as exc:  # 경고 수집 실패가 카드 발송을 막지 않는다
            print(f"[WARN] 그룹 qc_flags 수집 실패(무시): {exc}")
    qc_line = ("\n⚠️ <b>품질 경고</b> — " + " / ".join(qc_flags) + "\n") if qc_flags else ""

    # 발행 시점 — publish_at 없으면(기존 항목 전부 포함) 지금까지 그래왔듯 승인 즉시.
    publish_at = item.get("publish_at") or ""
    if publish_at:
        try:
            _d = datetime.fromisoformat(publish_at)
            # 오전/오후를 값에서 뽑는다 — 종전엔 '오전'이 박혀 있어 저녁 예약이
            # '오전 18:00' 으로 나갔다(2026-08-25 발견).
            _ampm, _h12 = ("오전", _d.hour) if _d.hour < 12 else ("오후", _d.hour - 12 or 12)
            if _h12 == 0:
                _h12 = 12
            pub_label = (f"승인하시면 {_d.year}년 {_d.month}월 {_d.day}일 "
                         f"{_ampm} {_h12}:{_d.minute:02d} 에 올라갑니다")
        except ValueError:
            pub_label = f"승인하시면 {publish_at} 에 올라갑니다"
    else:
        # 발행 감시기가 15분마다 도는 배치에 얹혀 있다(2026-08-25) — 승인과 실제 게시
        # 사이가 최대 15분이다. '즉시'라고만 적으면 GM 이 안 올라간 줄 알고 다시 보신다.
        pub_label = "승인하시면 15분 안에 올라갑니다"

    # 슬라이드 안 잔글씨는 몽타주에서 안 읽힌다(8컷을 한 장에 줄여 붙이기 때문).
    # 그래서 카드에 인쇄될 값을 글자로도 적는다 — 승인 전에 읽고 판단하시라고.
    # (2026-08-16 실사고: 정보 슬라이드에 접수 메모 '테스트도 성공'이 그대로 실려 나갔는데
    #  승인 화면에서는 보이지 않아 그대로 승인됐다.) 값이 없으면 이 줄은 아예 안 붙는다.
    info_lines = [str(x).strip() for x in (item.get("info_lines") or []) if str(x).strip()]
    info_block = ("\n<b>슬라이드에 인쇄될 값</b>\n" + "\n".join(f"· {x}" for x in info_lines) + "\n"
                  if info_lines else "")

    # 올린 사람 — 2026-08-23 부터 GM 말고 다른 사람도 올린다. 누가 올린 건지 안 보이면
    # 승인하는 쪽이 되물어야 한다. 없는 건(옛 항목)은 줄 자체를 만들지 않는다.
    writer_line = f"올린이: {item['writer']}\n" if (item.get("writer") or "").strip() else ""
    caption = (
        f"🔎 <b>콘텐츠 검수 요청</b>\n"
        f"<b>{title}</b>\n"
        f"{writer_line}"
        f"채널: {ch_label}\n"
        f"폴더: {folder}\n"
        f"발행 — {pub_label}\n"
        f"{qc_line}\n"
        f"{info_block}"
        f"슬라이드 미리보기 ↑ · <a href=\"{M1_URL}\">M1에서 전체 보기</a>\n"
        f"확인 후 아래에서 바로 발행 승인하세요."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": ("✅ 승인 (예약 발행)" if publish_at else "✅ 승인 (즉시 발행)"), "callback_data": cb_approve},
            {"text": "❌ 반려", "callback_data": cb_reject},
        ]]
    }

    photo = _preview_photo(item)
    if photo is None:
        print(f"[INFO] 미리보기 이미지 없음 — 텍스트 카드 폴백: {item_id}")
        new_id = _send_text_card(token, caption, keyboard, item_id)
    else:
        new_id = _send_photo_card(token, caption, keyboard, photo, item_id)
        if new_id is None:  # 이미지 발송 실패 → 텍스트 폴백
            new_id = _send_text_card(token, caption, keyboard, item_id)

    if new_id is None:
        return False

    # 같은 건의 이전 카드 자동 삭제 후 새 상태 저장 (카드 1개만 유지)
    store = _load_msgids()
    prev_id = (store.get(item_id) or {}).get("msg_id")
    if prev_id and prev_id != new_id:
        if _delete_message(token, prev_id):
            print(f"[INFO] 이전 카드 자동 삭제: {item_id} msg_id={prev_id}")
    store[item_id] = {"msg_id": new_id, "sig": sig, "ts": time.time()}
    _save_msgids(store)
    _mark_card_sent([item_id, *(group_ids or [])])
    return True


def _mark_card_sent(item_ids: list) -> None:
    """review_queue.json 에 card_sent_at 기록 — G1 알림(gm1RenderAlertSignal)이
    '카드 발송·GM 응답대기'와 '차례 대기(카드 미발송 재고)'를 구분하게 한다.

    배경(배292, 2026-08-02): AI하루 시리즈는 하루 1장만 발송하는 설계라 status='검수대기'
    항목 중 다수가 아직 카드조차 안 나간 재고인데, G1 화면은 이를 전부 'GM 승인 대기'로
    세어 GM이 방치한 것처럼 보이는 착시를 만들었다. 새 감시기 신설 없이 기존 단일 쓰기
    관문(review_queue_util.mutate_review_queue)에 필드 하나만 얹는다(약속 L21).
    best-effort — 실패해도 카드 발송 결과(반환값)에는 영향 없음."""
    try:
        from review_queue_util import mutate_review_queue, SkipSave
    except Exception as exc:
        print(f"[WARN] card_sent_at 기록 스킵(review_queue_util 임포트 실패, 무시): {exc}")
        return
    ids = set(item_ids)
    now_iso = datetime.now().isoformat(timespec="seconds")

    def _apply(items):
        changed = False
        for it in items:
            if it.get("id") in ids and not it.get("card_sent_at"):
                it["card_sent_at"] = now_iso
                changed = True
        if not changed:
            raise SkipSave

    try:
        mutate_review_queue(_apply, holder="send_review_card")
    except Exception as exc:
        print(f"[WARN] card_sent_at 기록 실패(무시, 카드 발송 자체는 완료됨): {exc}")


def load_queue() -> list:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[ERROR] 큐 파싱 실패: {e}")
        return []


def _sibling_base_id(queue_id: str) -> str:
    """대표 id 끝의 '-OFFICIAL-IG'/'-IG' 접미사를 제거한 베이스.
    publish_register._sibling_base_id 와 동일 규칙(형제 id 접두사 계산)."""
    for suffix in ("-OFFICIAL-IG", "-IG"):
        if queue_id.endswith(suffix):
            return queue_id[: -len(suffix)]
    return queue_id


def _find_sibling_group_ids(item: dict, items: list) -> list:
    """공식(account=='wellperion') IG 카드에 대해 같은 folder 계열 형제 채널
    (블로그·카페·카카오·당근) 중 검수대기/승인 상태인 id 를 자동 수집.

    수리 A(2026-07-22, 배9573 계열): 자동생산기(ig_series_producer.py)는
    `send_review_card.py --id <id>` 단독 호출만 하므로, register_publish 가 자동등록해둔
    형제(블로그·카페·카카오·당근)가 검수대기로 남아 있어도 그룹카드가 안 나가 GM [승인]이
    IG 하나만 승인하고 나머지는 검수대기에 방치되던 문제 — 여기서 형제를 스스로 찾아
    group_ids 를 구성해 자동으로 pub:grp 그룹카드가 나가게 한다.

    가드: account가 'wellperion'이고 channel에 '인스타그램'이 포함된 카드에만 적용.
    개인계정(namuk.wellperion 등)은 IG 단독이 표준이므로 그룹핑 대상에서 제외
    (조용히 빈 리스트 반환 — 기존 단일카드 동작 무회귀).
    형제가 하나도 없으면 빈 리스트 반환 → 호출부가 기존처럼 단일카드로 폴백.
    """
    if item.get("account") != "wellperion":
        return []
    channel = str(item.get("channel", ""))
    if "인스타그램" not in channel:
        return []

    item_id = str(item.get("id", ""))
    base_id = _sibling_base_id(item_id)
    sibling_ids: list = []
    for suffix in _SIBLING_ID_SUFFIXES:
        sib_id = f"{base_id}-{suffix}"
        if sib_id == item_id:
            continue
        sib = next((it for it in items if it.get("id") == sib_id), None)
        if sib is not None and sib.get("status") in _SIBLING_MERGEABLE_STATUSES:
            sibling_ids.append(sib_id)
    return sibling_ids


def main() -> None:
    p = argparse.ArgumentParser(description="콘텐츠 검수 카드 발송기")
    p.add_argument("--id", help="발송할 큐 항목 id (카드 대표 항목 — 미리보기·제목 기준)")
    p.add_argument("--group-ids", help=(
        "콤마 구분 복수 id: 카드 1장으로 일괄 승인 버튼 생성. "
        "--id 는 대표 항목(미리보기·제목)으로만 사용. "
        "예: --id A --group-ids A,B,C,D"))
    p.add_argument("--all-pending", action="store_true",
                   help="status='검수대기' 전체 카드 발송")
    p.add_argument("--force", action="store_true",
                   help="콘텐츠당 1회 가드 무시하고 강제 재발송(이전 카드는 교체)")
    args = p.parse_args()

    items = load_queue()
    if args.id:
        target = next((it for it in items if it.get("id") == args.id), None)
        if not target:
            print(f"[ERROR] id 미발견: {args.id}")
            sys.exit(1)
        group_ids = [x.strip() for x in args.group_ids.split(",") if x.strip()] \
            if args.group_ids else None
        if group_ids is None:
            # --group-ids 미지정 시에만 자동 형제그룹핑 시도(명시 지정은 그대로 존중).
            sibling_ids = _find_sibling_group_ids(target, items)
            if sibling_ids:
                group_ids = [args.id, *sibling_ids]
                print(f"[INFO] 형제 채널 자동그룹핑 — {len(sibling_ids)}건: {sibling_ids}")
        sys.exit(0 if send_card(target, force=args.force, group_ids=group_ids) else 1)
    elif args.all_pending:
        pending = [it for it in items if it.get("status") == "검수대기"]
        if not pending:
            print("[INFO] 검수대기 항목 없음.")
            return
        sent = sum(1 for it in pending if send_card(it, force=args.force))
        print(f"[INFO] 검수대기 {len(pending)}건 중 {sent}건 발송.")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
