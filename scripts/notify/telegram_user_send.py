# -*- coding: utf-8 -*-
"""telegram_user_send.py — GM 본인 텔레그램 계정으로 직접 발송(Telethon, User API).

봇(telegram_send.py)과 다르다: 봇은 "봇이 보냄"으로 찍히고, 이건 GM 본인 이름으로 나간다.
GM 결재(2026-09-05): 업무관리 그룹(-5492623600)에 GM 계정으로 글을 남기는 용도.

설정 = telegram_bot/.env 의 TG_USER_API_ID · TG_USER_API_HASH · TG_USER_PHONE (my.telegram.org 발급).
세션 = telegram_bot/gm_user.session (.gitignore *.session 로 이미 제외).

사용:
  --setup                          최초 1회, GM 본인 터미널에서 대화형 로그인
  --whoami                         세션 확인
  --send --chat <id> --text "..."  발송(텍스트는 stdin 도 가능) · --dry-run 미리보기

파이썬에서: from scripts.notify.telegram_user_send import send_as_gm
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = ROOT / "telegram_bot" / ".env"
_SESSION_NAME = str(ROOT / "telegram_bot" / "gm_user")  # telethon 이 .session 을 붙인다
_SESSION_FILE = ROOT / "telegram_bot" / "gm_user.session"
REQUIRED = ("TG_USER_API_ID", "TG_USER_API_HASH", "TG_USER_PHONE")
SOURCE = "telegram_user_send"
# 하루 상한 — 폭주(같은 글 반복 발신)를 막는 장치이지 정상 운영을 막는 장치가 아니다.
# 2026-09-11 실측: 자동 통 + 나우열M 왕복이 겹쳐 19:1x 에 30통을 채웠고, 그 뒤 그분이 부를 때마다
# 답이 안 나가고 실패 알림만 GM 봇방으로 갔다(GM: 「나우열M 업무보고봇 호출 계속 들어오는데?」).
# 그날 30통은 정상 부하였다 — 네 배로 올린다. 폭주는 이 숫자가 아니라 같은 글 반복으로 잡는다.
_DAILY_CAP = 120
_AI_SIGNS = ("[AI 웰리]", "AI 시토", "AI 시모", "AI 시우", "AI 시포", "AI 시뽀", "AI 시로", "AI 시보", "AI CEO")

sys.path.insert(0, str(ROOT / "scripts"))
from tg_outbound_log import log_outbound  # noqa: E402 — 기존 발신 로그 관문 재사용
import worklog  # noqa: E402 — CHRO 업무지시 발신 로그(GM 원문 보관)용
# 직함 뒤 '님' 자동 보정 — 카톡 발신 관문(kakao_report_sender.build_caption)과 같은 함수를 그대로 가져다
# 쓴다(배 12677 · GM 지시 2026-09-16). 새 함수를 또 만들지 않는다 — 관문은 하나, 부르는 자리만 둘(약속 L21).
from kakao_report_sender import add_honorifics  # noqa: E402


def _parse_env_file(path: Path) -> dict:
    cfg = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


def _load_env() -> dict:
    cfg = _parse_env_file(_ENV_FILE)
    for k in REQUIRED:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def _session_exists() -> bool:
    return _SESSION_FILE.exists()


def _check_ai_signature(text: str) -> None:
    """제거하지 않는다 — GM 계정 발신문에 AI 서명이 섞였다는 사실만 알린다(호출부 책임)."""
    for s in _AI_SIGNS:
        if s in text:
            print(f"[경고] 본문에 AI 서명({s!r})이 있음 — GM 계정 발신인데 그대로 보냄", file=sys.stderr)
            return


def _today_sent_count() -> int:
    log_path = ROOT / "logs" / f"telegram_sent-{datetime.date.today():%Y-%m-%d}.log"
    if not log_path.exists():
        return 0
    n = 0
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("source") == SOURCE and rec.get("ok") is True:
            n += 1
    return n


def _prepare(text: str):
    """설정·세션 점검. 문제 있으면 (None, exit_code), 없으면 (cfg, 0)."""
    cfg = _load_env()
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        print(f"[설정 필요] telegram_bot/.env 에 {', '.join(missing)} 값을 넣어주세요.")
        print("my.telegram.org 에서 App 생성 → api_id/api_hash 발급, 전화번호는 국가코드 포함(예: +8210...)")
        return None, 2
    if not _session_exists():
        print("[미인증] 세션 없음 — 먼저 --setup 실행 "
              "(! C:/Python314/python.exe scripts/notify/telegram_user_send.py --setup)")
        return None, 3
    _check_ai_signature(text)
    return cfg, 0


async def _setup_async(api_id, api_hash, phone, code=None, password=None):
    """`!` 셸은 stdin 이 null 이라 input() 이 EOF 로 죽는다(2026-09-05 실측) —
    코드·2단계 비밀번호를 인자로 받는다. 코드 없이 부르면 텔레그램이 코드를 보내고 종료(exit 5)."""
    from telethon import TelegramClient
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    if code is None:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me(); print(f"[OK] 이미 로그인됨: {(me.first_name or '')} (id={me.id})"); await client.disconnect(); return
        await client.send_code_request(phone)
        await client.disconnect()
        print("[코드 발송] 텔레그램 앱에 온 숫자 코드를 받아 다시: --setup --code 12345  (2단계 비밀번호 있으면 --password 도)")
        sys.exit(5)
    await client.start(phone=phone, code_callback=lambda: str(code), password=password)
    me = await client.get_me()
    print(f"[OK] 로그인 완료: {(me.first_name or '')} {(me.last_name or '')} (id={me.id})".strip())
    await client.disconnect()


async def _whoami_async(api_id, api_hash):
    from telethon import TelegramClient
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("[미인증] 세션 만료 — --setup 다시 실행")
            return
        me = await client.get_me()
        print(f"[OK] {(me.first_name or '')} {(me.last_name or '')} (id={me.id})".strip())
    finally:
        await client.disconnect()


def _room_id(chat_id):
    """--chat 에 방 이름(status/telegram_rooms.json 키 · 예 '업무관리-나우열M')이 오면 숫자 id 로 푼다.
    2026-09-06 실사고: 이름을 그대로 넘겨 int() 에서 죽고 헬스체크가 '발송 실패 1건'으로 잡았다. 숫자면 그대로."""
    s = str(chat_id).strip()
    # 2026-09-15 실사고: '업무관리' 키가 telegram_rooms.json 에서는 GM 개인 봇방(=GM 본인 id)이라, GM 계정으로
    # 보내면 「저장한 메시지」(자기 자신)로 들어갔다(10:17·10:20 두 통). 이 도구의 '업무관리' 는 나우열M 그룹뿐이다.
    if s in ("업무관리", "업무관리-나우열M", "AtoA"):
        return WORK_ROOM_CHAT_ID
    if s.lstrip("-").isdigit():
        rid = int(s)
    else:
        rooms = json.loads((ROOT / "status" / "telegram_rooms.json").read_text(encoding="utf-8"))
        if not (s in rooms and rooms[s]):
            raise ValueError("알 수 없는 방 이름: %s (status/telegram_rooms.json 키 또는 숫자 chat_id)" % s)
        rid = int(rooms[s])
    if rid == GM_SELF_ID:
        raise ValueError("GM 계정이 자기 자신(id %d)에게 보내면 「저장한 메시지」로 간다 — 나우열M 방은 '업무관리' 또는 %d"
                         % (GM_SELF_ID, WORK_ROOM_CHAT_ID))
    return rid


GM_SELF_ID = 8254867551   # GM 본인 텔레그램 id(--whoami) — 봇방 chat_id 와 같은 숫자라 헷갈린다


async def _resolve_and_send(client, chat_id, text):
    chat_id = _room_id(chat_id)
    try:
        entity = await client.get_entity(int(chat_id))
    except (ValueError, TypeError):
        await client.get_dialogs()  # raw id 캐시 미스 — 대화목록 동기화 후 재시도
        entity = await client.get_entity(int(chat_id))
    await client.send_message(entity, text)


async def _rename_async(api_id, api_hash, chat_id, title):
    """그룹 방 제목 변경(GM 계정 = 방장). 작은 그룹은 messages.EditChatTitle · 슈퍼그룹은 channels.EditTitle."""
    from telethon import TelegramClient
    from telethon.tl.functions.messages import EditChatTitleRequest
    from telethon.tl.functions.channels import EditTitleRequest
    from telethon.tl.types import Channel
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("세션 만료/미인증 — --setup 다시 실행 필요")
        rid = _room_id(chat_id)
        try:
            entity = await client.get_entity(rid)
        except (ValueError, TypeError):
            await client.get_dialogs()
            entity = await client.get_entity(rid)
        if isinstance(entity, Channel):
            await client(EditTitleRequest(channel=entity, title=title))
        else:
            await client(EditChatTitleRequest(chat_id=abs(rid), title=title))
        entity = await client.get_entity(rid)
        return getattr(entity, "title", "")
    finally:
        await client.disconnect()


async def _send_async(api_id, api_hash, chat_id, text):
    from telethon import TelegramClient
    client = TelegramClient(_SESSION_NAME, api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("세션 만료/미인증 — --setup 다시 실행 필요")
        await _resolve_and_send(client, chat_id, text)
    finally:
        await client.disconnect()


def _try_send(cfg, chat_id, text) -> bool:
    try:
        asyncio.run(asyncio.wait_for(
            _send_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"], chat_id, text),
            timeout=30))
        return True
    except Exception as ex:
        print(f"[실패] {ex}")
        return False


def cap_reached() -> bool:
    """오늘 상한에 닿았나. 부르는 쪽이 「보낼 수 없는 상태」와 「보내다 실패」를 가르는 데 쓴다 —
    상한은 사유가 하나뿐이라 매번 알릴 일이 아니다(같은 실패가 열 번 오면 알림이 아니라 소음이다)."""
    return _today_sent_count() >= _DAILY_CAP


_CAP_MARK = ROOT / "logs" / ".tg_user_cap_notified"


def _notify_cap_once() -> None:
    """상한에 닿은 날 GM 봇방에 한 줄만. 같은 날 두 번째부터는 조용히 지나간다."""
    today = f"{datetime.date.today():%Y-%m-%d}"
    try:
        if _CAP_MARK.exists() and _CAP_MARK.read_text(encoding="utf-8").strip() == today:
            return
    except Exception:
        pass
    try:
        import urllib.request
        cfg = _parse_env_file(_ENV_FILE)
        token, chat = cfg.get("TELEGRAM_BOT_TOKEN"), cfg.get("TG_CHAT_ID") or "8254867551"
        if token:
            body = json.dumps({"chat_id": chat,
                               "text": f"📮 오늘 업무관리 방 발송 상한({_DAILY_CAP}통)에 닿았습니다 — "
                                       "이후 그 방으로 나가는 답이 자정까지 멈춥니다."}).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                         data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass
    try:
        _CAP_MARK.parent.mkdir(parents=True, exist_ok=True)
        _CAP_MARK.write_text(today, encoding="utf-8")
    except Exception:
        pass


def send_as_gm(chat_id, text: str) -> bool:
    """다른 파이썬 코드에서 호출. 성공 True."""
    text = add_honorifics(text)
    cfg, code = _prepare(text)
    if cfg is None:
        return False
    if cap_reached():
        print(f"[상한] 오늘 {_DAILY_CAP}통 발송 완료 — 더 못 보냄")
        _notify_cap_once()
        return False
    ok = _try_send(cfg, chat_id, text)
    log_outbound(text, chat_id=chat_id, source=SOURCE, ok=ok, kind="sendMessage")
    return ok


WORK_ROOM_CHAT_ID = -5492623600  # 텔레그램 「업무관리」 그룹(GM·나우열M·봇 · GM 확정 2026-09-05)


def render_chro_task(name: str, owner: str, start: str, end: str, content: str, no=None) -> str:
    """업무지시 규격(GM 확정 2026-09-05) — 첫 줄 「CHRO야」 고정. 나우열M 쪽 CHRO(AI)가 이 첫마디로
    업무지시를 인식해 업무 SSOT 에 바로 등록한다. 줄 순서·라벨은 바꾸지 않는다.

    업무명 앞 번호(라벨) = 나우열M 요청 2026-09-11 「업무명 앞에 번호(라벨링) 필수로 넣어」.
    번호가 있어야 업무 SSOT 행과 중간관리자 원장(#101~)이 같은 이름으로 이어진다 — 없으면
    제목 유사도로 맞춰야 해서 완료 회신이 엉뚱한 건에 붙는다. 번호 없이도 보낼 수는 있지만
    그때는 경고를 남긴다(막으면 원장에 없는 새 건을 아예 못 올린다)."""
    label = f"[#{str(no).lstrip('#').strip()}] " if str(no or "").strip() else ""
    if not label:
        print("[chro-task] ⚠ 업무명 앞 번호 없음 — 원장 번호를 넣어야 회신이 정확히 붙는다"
              "(나우열M 요청 2026-09-11)", file=sys.stderr)
    vals = {"업무명": label + str(name or "").strip(), "담당자": owner,
            "시작일": start, "종료일": end, "내용": content}
    empty = [k for k, v in vals.items() if not str(v or "").strip()]
    if empty:
        raise ValueError(f"업무지시 빈 값: {', '.join(empty)}")
    if not str(name or "").strip():
        raise ValueError("업무지시 빈 값: 업무명")
    return "CHRO야\n" + "\n".join(f"{k} : {str(v).strip()}" for k, v in vals.items())


def _normalize_task_name(name: str) -> str:
    """업무명 비교용 정규화 — 앞 「[#N]」 라벨·꼬리 괄호·공백 제거."""
    s = str(name or "").strip()
    s = re.sub(r"^\[#\d+\]\s*", "", s)
    s = re.sub(r"[\(（][^)）]*[\)）]\s*$", "", s)
    return re.sub(r"\s+", "", s)


def _lead_keyword(name: str) -> str:
    """업무명 첫 낱말들을 공백 없이 이어 6자를 채운 핵심 덩이(예 "SVIP 요가 클래스" → "SVIP요가").
    앞 라벨은 뺀다 — 낱말만 겹치고 포함 관계는 아닌 두 업무명을 잡는 두 번째 판정 축."""
    s = str(name or "").strip()
    s = re.sub(r"^\[#\d+\]\s*", "", s)
    acc = ""
    for w in s.split():
        acc += w
        if len(acc) >= 6:
            break
    return acc


def _is_dup(new_name, new_owner, ex_name, ex_owner) -> bool:
    """중복 의심 순수 판정(네트워크 없음 — selfcheck 용으로 뗐다). 둘 중 하나면 중복 의심:
      ① 정규화한 업무명이 완전히 같거나, 한쪽(20자 이상)이 다른 쪽에 포함
      ② 같은 담당자 + 핵심 낱말(첫 6자 이상) 일치 — 포함관계는 아니지만 낱말만 겹치는 경우
         (2026-09-14 사례: "SVIP 요가 클래스 — 생크몽드 공간·스파권 패키지 계약·정산" vs
          "SVIP요가 최도희선생님 마케팅 준비" — 담당자 같고 "SVIP요가" 일치)."""
    new_norm = _normalize_task_name(new_name)
    ex_norm = _normalize_task_name(ex_name)
    if not ex_norm:
        return False
    if new_norm == ex_norm:
        return True
    if len(new_norm) >= 20 and new_norm in ex_norm:
        return True
    if len(ex_norm) >= 20 and ex_norm in new_norm:
        return True
    new_kw = _lead_keyword(new_name)
    if (new_kw and len(new_kw) >= 6
            and str(ex_owner or "").strip() == str(new_owner or "").strip()
            and new_kw == _lead_keyword(ex_name)):
        return True
    return False


def _find_ssot_duplicate(name: str, owner: str) -> dict | None:
    """업무 SSOT(todo_list) 열린 행 중 중복 의심 하나를 돌려준다(없으면 None) — 발신 직전에만 부른다.
    gmkey 조회 방식 = scripts/gm_handoff.py 의 GM_KEY·todo_list 호출 그대로 재사용(값 복붙 금지)."""
    from gm_handoff import GM_KEY
    import ops_daily_digest as o
    rows = o._gas_get(o.SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                      timeout=40, label="chro-task dup").json().get("data") or []
    for r in rows:
        if str(r.get("상태") or "") in ("완료", "삭제"):
            continue
        if _is_dup(name, owner, r.get("업무명"), r.get("담당자")):
            return r
    return None


def send_chro_task(name, owner, start, end, content, chat_id=WORK_ROOM_CHAT_ID, no=None,
                    gm_quote: str = "", force_dup: str = "") -> bool:
    """gm_quote = GM 이 그 자리에서 낸 지시 원문 — 없으면 거절(나우열M 지적 2026-09-14 · GM 지시
    "너가 왜 SSOT에 업무를 올려? 전달만 하고 삭제해" · 08-18 규칙 3회째 위반 뒤 박은 가드).
    force_dup = 중복 의심을 뚫고 보낼 이유(비우면 중복 의심 시 안 뚫린다)."""
    if not str(gm_quote or "").strip():
        raise ValueError("CHRO 업무지시는 GM 이 그 자리에서 낸 지시를 옮길 때만 — gm_quote(GM 원문)를 넣어라 "
                          "· AI 가 정리한 건은 규격 없이 안내문으로 전달만")
    if not str(force_dup or "").strip():
        dup = _find_ssot_duplicate(name, owner)
        if dup:
            print(f"[중복 의심] 이미 있는 행: {dup.get('id')} {dup.get('업무명')} — "
                  "그 행에 내용을 보태거나 안내문으로 전달")
            return False
    text = render_chro_task(name, owner, start, end, content, no=no)
    ok = send_as_gm(chat_id, text)
    worklog.log(role="ceo", area="업무관리방", event=f"CHRO 업무지시 발신: {name}",
                result="ok" if ok else "fail",
                detail=f"GM 원문: {str(gm_quote).strip()[:300]}"
                       + (f" · 중복강행 사유: {str(force_dup).strip()}" if force_dup else ""))
    return ok


def _selfcheck():
    import tempfile
    t = render_chro_task("테스트", "나우열M", "2026-09-08", "2026-09-12", "내용")
    assert t.splitlines()[0] == "CHRO야" and t.splitlines()[1] == "업무명 : 테스트", t
    # 업무명 앞 번호(나우열M 2026-09-11) — 주면 붙고, # 를 겹쳐 써도 하나만 남는다.
    n1 = render_chro_task("테스트", "나우열M", "2026-09-08", "2026-09-12", "내용", no=201)
    assert n1.splitlines()[1] == "업무명 : [#201] 테스트", n1
    n2 = render_chro_task("테스트", "나우열M", "2026-09-08", "2026-09-12", "내용", no="#201")
    assert n2.splitlines()[1] == "업무명 : [#201] 테스트", n2
    # 방 이름 해소 — '업무관리' 는 나우열M 그룹이고, GM 본인 id 로는 절대 보내지 않는다(2026-09-15 「저장한 메시지」 사고).
    assert _room_id("업무관리") == WORK_ROOM_CHAT_ID and _room_id("AtoA") == WORK_ROOM_CHAT_ID
    assert _room_id(str(WORK_ROOM_CHAT_ID)) == WORK_ROOM_CHAT_ID
    try:
        _room_id(str(GM_SELF_ID)); raise AssertionError("GM 본인 id 가 통과했다")
    except ValueError as ex:
        assert "저장한 메시지" in str(ex), ex
    try:
        render_chro_task("", "x", "y", "z", "w"); raise AssertionError("빈 값 통과")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / ".env"
        tmp.write_text("TG_USER_API_ID=123\nTG_USER_API_HASH=abc\nTG_USER_PHONE=+821012345678\n", encoding="utf-8")
        cfg = _parse_env_file(tmp)
        assert cfg == {"TG_USER_API_ID": "123", "TG_USER_API_HASH": "abc", "TG_USER_PHONE": "+821012345678"}, cfg
    _check_ai_signature("[AI 웰리] 테스트")  # 예외 없이 경고만
    _check_ai_signature("평범한 GM 메시지")
    # 가드① GM 원문 없이는 거절
    try:
        send_chro_task("x", "y", "2026-01-01", "2026-01-02", "c")
        raise AssertionError("gm_quote 없이 통과됨")
    except ValueError as ex:
        assert "gm_quote" in str(ex), ex
    print("[selfcheck] 가드① OK — gm_quote 없이 부르면 거절: ValueError")
    # 가드② 중복 의심 — 완전 일치·포함(20자+)·같은 담당자+핵심낱말
    assert _is_dup("테스트 업무", "나우열M", "테스트 업무", "나우열M") is True  # 완전 일치
    assert _is_dup("테스트 업무 이십자이상제목붙이기포함검사용텍스트", "나우열M",
                    "테스트 업무 이십자이상제목붙이기포함검사용텍스트 — 추가설명", "나우열M") is True  # 포함(20자+)
    # 2026-09-14 실사례: 담당자 같고 낱말만 겹침(포함관계 아님) → 중복 의심으로 잡혀야 한다
    dup_hit = _is_dup(
        "SVIP 요가 클래스 — 생크몽드 공간·스파권 패키지 계약·정산", "나우열M",
        "SVIP요가 최도희선생님 마케팅 준비", "나우열M")
    assert dup_hit is True, "오늘 사례(SVIP요가)가 중복 의심으로 안 잡힘"
    print(f"[selfcheck] 가드② OK — 오늘 사례(SVIP요가) 중복 의심 판정: {dup_hit}")
    assert _is_dup("완전히 다른 업무", "나우열M", "SVIP요가 최도희선생님 마케팅 준비", "최준용M") is False  # 담당자 다르면 통과
    print("[selfcheck] OK")


def main():
    ap = argparse.ArgumentParser(description="GM 텔레그램 계정으로 직접 발송(Telethon)")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--code", type=str, help="--setup 2단계: 텔레그램 앱에 온 숫자 코드")
    ap.add_argument("--password", type=str, help="2단계 인증 비밀번호(있을 때만)")
    ap.add_argument("--whoami", action="store_true")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--chat", type=str)
    ap.add_argument("--text", type=str)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--rename", type=str, help="그룹 방 제목 변경(GM 계정=방장) · 기본 chat=업무관리(나우열M 그룹)")
    ap.add_argument("--chro-task", action="store_true", help="업무지시 규격(CHRO야/업무명/담당자/시작일/종료일/내용)으로 발송 · 기본 chat=업무관리")
    ap.add_argument("--no", dest="task_no", help="업무명 앞에 붙일 원장 번호(#201 등 · 나우열M 요청 2026-09-11)")
    ap.add_argument("--gm-quote", dest="gm_quote",
                     help="CHRO 업무지시 필수 — GM 이 그 자리에서 낸 지시 원문(없으면 거절 · GM 지시 2026-09-14)")
    ap.add_argument("--force-dup", dest="force_dup",
                     help="업무 SSOT 중복 의심 가드를 뚫을 이유(비우면 중복 의심 시 발송 안 함)")
    ap.add_argument("--name"); ap.add_argument("--owner"); ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--content")
    args = ap.parse_args()

    if args.chro_task:
        if not str(args.gm_quote or "").strip():
            print("[오류] CHRO 업무지시는 GM 이 그 자리에서 낸 지시를 옮길 때만 — --gm-quote(GM 원문)가 필요하다 "
                  "· AI 가 정리한 건은 규격 없이 안내문으로 전달만")
            sys.exit(2)
        try:
            text = render_chro_task(args.name, args.owner, args.start, args.end, args.content, no=args.task_no)
        except ValueError as ex:
            print(f"[오류] {ex}"); sys.exit(2)
        chat = args.chat or str(WORK_ROOM_CHAT_ID)
        if not str(args.force_dup or "").strip():
            dup = _find_ssot_duplicate(args.name, args.owner)
            if dup:
                print(f"[중복 의심] 이미 있는 행: {dup.get('id')} {dup.get('업무명')} — "
                      "그 행에 내용을 보태거나 안내문으로 전달")
                sys.exit(6)
        cfg, code = _prepare(text)
        if cfg is None:
            print(text); sys.exit(code)
        if args.dry_run:
            print(f"[dry-run] chat={chat}\n{text}"); return
        if _today_sent_count() >= _DAILY_CAP:
            print(f"[상한] 오늘 {_DAILY_CAP}통 발송 완료"); sys.exit(4)
        ok = _try_send(cfg, chat, text)
        log_outbound(text, chat_id=chat, source=SOURCE, ok=ok, kind="sendMessage")
        worklog.log(role="ceo", area="업무관리방", event=f"CHRO 업무지시 발신: {args.name}",
                    result="ok" if ok else "fail",
                    detail=f"GM 원문: {args.gm_quote.strip()[:300]}"
                           + (f" · 중복강행 사유: {args.force_dup.strip()}" if args.force_dup else ""))
        sys.exit(0 if ok else 1)

    if args.selfcheck:
        _selfcheck()
        return

    if args.setup:
        cfg = _load_env()
        missing = [k for k in REQUIRED if not cfg.get(k)]
        if missing:
            print(f"[설정 필요] telegram_bot/.env 에 {', '.join(missing)} 값을 넣어주세요.")
            print("my.telegram.org 에서 App 생성 → api_id/api_hash 발급, 전화번호는 국가코드 포함(예: +8210...)")
            sys.exit(2)
        asyncio.run(_setup_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"], cfg["TG_USER_PHONE"], code=args.code, password=args.password))
        return

    if args.whoami:
        cfg, code = _prepare("")
        if cfg is None:
            sys.exit(code)
        asyncio.run(_whoami_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"]))
        return

    if args.rename:
        cfg, code = _prepare("")
        if cfg is None:
            sys.exit(code)
        chat = args.chat or str(WORK_ROOM_CHAT_ID)
        if args.dry_run:
            print(f"[dry-run] 제목 변경 안 함 — chat={chat} title={args.rename!r}"); return
        title = asyncio.run(_rename_async(int(cfg["TG_USER_API_ID"]), cfg["TG_USER_API_HASH"], chat, args.rename))
        print(f"[OK] 방 제목 → {title!r} (chat={_room_id(chat)})")
        return

    if args.send:
        if not args.chat:
            print("[오류] --chat 필요")
            sys.exit(1)
        text = args.text if args.text is not None else sys.stdin.read()
        cfg, code = _prepare(text)
        if cfg is None:
            sys.exit(code)
        if args.dry_run:
            print(f"[dry-run] 발송 안 함 — chat={args.chat} text={text[:80]!r}")
            return
        if _today_sent_count() >= _DAILY_CAP:
            print(f"[상한] 오늘 {_DAILY_CAP}통 발송 완료 — 더 못 보냄")
            sys.exit(4)
        ok = _try_send(cfg, args.chat, text)
        log_outbound(text, chat_id=args.chat, source=SOURCE, ok=ok, kind="sendMessage")
        sys.exit(0 if ok else 1)

    ap.print_help()


if __name__ == "__main__":
    main()
