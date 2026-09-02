#!/usr/bin/env python3
"""다이어트캠프 이승기 대표님 대화 에이전트 (GM 지시 2026-09-02).

무엇을 하나
    대표님이 카톡으로 무언가 말씀하시면, 그 말을 읽고 답장 한 통을 써서 보낸다.
    먼저 말을 걸지는 않는다 — 대표님이 말씀하셨을 때만 답한다.

왜 만들었나
    종전에는 매일 07시에 미리 써 둔 원고를 순서대로 보내기만 했다(daily_scheduler
    run_diet_camp_morning). 대표님이 답을 주셔도 그 답에 맞춰 다음 말을 바꾸지 못해,
    답이 없으면 같은 재문의만 반복됐다. 실제로 3일 연속 같은 통이 나갔다.
    GM: "이승기대표님이랑 소통할 수 있는 AI 에이전트를 만들어야할 것 같은데?"

새 관문을 만들지 않는다 (약속 L21)
    수신 = scripts/kakao_export_chat.py      (이미 있는 대화 내보내기)
    작성 = scripts/model_router.run_claude   (이미 있는 모델 호출·폴백)
    발신 = scripts/kakao_report_sender.py    (카톡 발신 관문 하나뿐)
    통보 = scripts/telegram_notifier.py      (GM 업무보고방)
    이 파일은 넷을 잇는 얇은 층이고, 자기 상태 파일 하나만 새로 갖는다.

안전장치
    · 대표님 새 발화가 없으면 아무것도 안 한다(먼저 말 걸지 않음).
    · 하루 발신 상한 6통. 넘으면 GM 께만 알리고 멈춘다.
    · 돈·계약·가격을 약속하는 말이 초안에 들어가면 보내지 않고 GM 께 넘긴다.
    · 10줄을 넘는 초안은 보내지 않는다(카톡에서 안 읽힌다).
    · enabled=false 면 한 줄도 안 나간다.
    · --dry-run 은 초안만 찍고 발신하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

ROOM = "다이어트캠프 이승기 대표님"
GM_NAME = "김남욱"                      # 이 방 구성원은 대표님과 GM 둘뿐이다
STATE_PATH = REPO_ROOT / "status" / "diet_camp_agent.json"
SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"
EXPORTER = REPO_ROOT / "scripts" / "kakao_export_chat.py"

DAILY_SEND_CAP = 6
MAX_LINES = 10
CONTEXT_LINES = 60                      # 프롬프트에 넣을 최근 대화 줄 수

# 초안에 이 말이 들어가면 보내지 않는다 — 돈·계약은 사람이 정한다(3-트리거 💰).
FORBIDDEN = ("원 드리", "원에 드리", "계약", "견적서", "입금", "송금", "할인해", "무료로 드리",
             "결제", "청구", "세금계산서")

LINE_RE = re.compile(r"^\[(?P<who>[^\]]+)\]\s*\[(?P<when>[^\]]+)\]\s*(?P<text>.*)$")
DAY_RE = re.compile(r"^-{3,}\s*(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일.*-{3,}$")

SYSTEM_BRIEF = """너는 웰페리온의 AI 비서다. 지금 카카오톡에서 '다이어트캠프 이승기 대표님'과 1:1로 대화하고 있다.

대표님에 대해 알아 둘 것
- 대표님은 AI 를 처음 써 보신다. 어려운 말·영어·전문용어를 쓰면 안 된다.
- 답장이 아주 짧다("응", "3번", "오키"). 그래서 질문은 번호나 한 단어로 답할 수 있게 낸다.
- 웰페리온 GM(김남욱)과 가까운 사이다. 딱딱한 공문 말투가 아니라 정중하고 편한 존댓말을 쓴다.

지금 하는 일
- 블로그 만드는 업체가 다이어트캠프에 대해 여덟 가지를 물어 왔고, 그 답을 대표님께 받아 정리해 넘기는 중이다.
  ①오시는 분들(나이대·이유) ②다이어트캠프만의 장점 ③운영하며 지키는 것 ④블로그에 꼭 넣을 것
  ⑤한 줄 소개 ⑥블로그 말투 ⑦참고 블로그·주제 ⑧운영 중인 상품 전부
- 대표님이 답해 주신 항목은 다시 묻지 않는다. 남은 항목만 이어서 여쭙는다.

답장 쓰는 법
- 카카오톡 한 통. 10줄 안쪽. 빈 줄은 쓰지 않는다(카톡에서 화면이 세 배로 늘어난다).
- 항목은 1️⃣ 2️⃣ 같은 번호로 세우고, 설명은 그 다음 줄에 세 칸 들여쓴다.
- 먼저 대표님이 방금 하신 말에 반응한다. 받은 내용을 한 줄로 되짚어 확인하고 고맙다고 한다.
- 그 다음 남은 질문을 한 번에 하나나 둘만 여쭙는다. 몰아서 묻지 않는다.
- 마지막 줄은 👉 로 시작해, 대표님이 무엇을 주시면 되는지 한 줄로 적는다.
- 재촉하지 않는다. "며칠째"·"아직"·"빨리" 같은 말을 쓰지 않는다.
- 돈·가격·계약·결제에 대해서는 어떤 약속도 하지 않는다. 그 이야기가 나오면 "GM님께 여쭤보고 말씀드리겠습니다"라고만 한다.
- 모르는 것은 지어내지 않는다. 모르면 모른다고 하고 확인해서 알려드린다고 쓴다.

출력 형식
- 보낼 카카오톡 본문만 출력한다. 설명·따옴표·머리말·코드블록을 붙이지 않는다.
- 대표님이 방금 하신 말이 답장이 필요 없는 잡담이거나(예: "응", "오키") 이미 대화가 끝난
  흐름이면, 본문 대신 정확히 SKIP 한 단어만 출력한다."""


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        # 처음 도는 날 — 켜져 있고, 아직 아무것도 처리 안 한 상태
        return {"enabled": True, "last_handled": "", "sent_today": 0, "sent_date": "",
                "history": []}


def _save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _export_chat() -> str | None:
    """방 대화를 내보내 텍스트로 돌려준다. 실패하면 None(그날은 조용히 넘어간다)."""
    try:
        r = subprocess.run(
            [sys.executable, str(EXPORTER), "--room", ROOM],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
        )
        tail = (r.stdout or "").strip().splitlines()
        if r.returncode != 0 or not tail or not tail[-1].startswith("DONE:"):
            print(f"[agent] 대화 내보내기 실패 — {tail[-1] if tail else '(출력없음)'}", file=sys.stderr)
            return None
        return Path(tail[-1].partition("—")[-1].strip()).read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"[agent] 내보내기 예외: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def parse_lines(text: str) -> list[dict]:
    """대화 텍스트를 {day, who, when, text} 목록으로. 날짜 구분선을 만나면 그 날짜를 물린다."""
    day, out = "", []
    for raw in text.splitlines():
        s = raw.strip()
        d = DAY_RE.match(s)
        if d:
            day = f"{d.group('y')}-{int(d.group('m')):02d}-{int(d.group('d')):02d}"
            continue
        m = LINE_RE.match(s)
        if m:
            out.append({"day": day, "who": m.group("who").strip(),
                        "when": m.group("when").strip(), "text": m.group("text").strip()})
    return out


def new_from_partner(lines: list[dict], last_handled: str) -> list[dict]:
    """마지막으로 처리한 대표님 발화 이후에 새로 온 대표님 발화만.

    last_handled 는 '<day> <when> <text>' 를 합친 표식이다. 같은 표식을 만난 뒤부터
    담는다 — 표식이 대화에 없으면(내보내기 범위 밖) 마지막 한 줄만 새 것으로 본다."""
    mine = [ln for ln in lines if ln["who"] != GM_NAME]
    if not mine:
        return []
    if not last_handled:
        return mine[-1:]
    keys = [f"{ln['day']} {ln['when']} {ln['text']}" for ln in mine]
    if last_handled in keys:
        return mine[keys.index(last_handled) + 1:]
    return mine[-1:]


def build_prompt(lines: list[dict], fresh: list[dict]) -> str:
    recent = lines[-CONTEXT_LINES:]
    convo = "\n".join(f"[{ln['who']}] {ln['text']}" for ln in recent if ln["text"])
    newest = "\n".join(ln["text"] for ln in fresh if ln["text"])
    return (f"{SYSTEM_BRIEF}\n\n"
            f"── 최근 대화 (오래된 것 위) ──\n{convo}\n\n"
            f"── 대표님이 방금 하신 말 ──\n{newest}\n\n"
            f"위 말에 대한 답장 한 통을 써라. 본문만 출력한다.")


def guard(draft: str) -> str | None:
    """보내면 안 되는 초안이면 그 이유를, 보내도 되면 None 을 돌려준다."""
    body = draft.strip()
    if not body:
        return "초안이 비었다"
    if body == "SKIP":
        return "SKIP"
    if len(body.splitlines()) > MAX_LINES:
        return f"{len(body.splitlines())}줄 — 카톡 한 통 상한 {MAX_LINES}줄을 넘었다"
    hit = [w for w in FORBIDDEN if w in body]
    if hit:
        return f"돈·계약 관련 표현이 들어갔다({', '.join(hit)}) — 사람이 정할 몫이다"
    return None


def _send(body: str) -> bool:
    p = subprocess.run(
        [sys.executable, str(SENDER), "--message", body, "--only-room", ROOM, "--sender", "웰리"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip()
    print(f"[agent] 발신 rc={p.returncode} · {out.splitlines()[-1] if out else '(출력없음)'}")
    return p.returncode == 0 and "DONE" in out


def _tell_gm(msg: str) -> None:
    try:
        sys.path.insert(0, str(REPO_ROOT / "wellperion-agents"))
        from telegram_notifier import TelegramNotifier  # noqa: PLC0415
        TelegramNotifier().send(msg)
    except Exception as exc:
        print(f"[agent] GM 통보 건너뜀: {type(exc).__name__}: {exc}", file=sys.stderr)


def init_marker() -> int:
    """켜는 시점의 마지막 대표님 발화를 '이미 처리함'으로 찍는다.

    이걸 안 하면 첫 실행이 며칠 전 말씀에 뒤늦게 답장한다 — 대표님 입장에서는
    갑자기 지난 대화에 답이 오는 셈이라 이상하다. 켤 때 한 번만 돈다."""
    text = _export_chat()
    if text is None:
        print("[agent] 대화를 못 읽어 초기화하지 못했다 — 카톡 창을 확인하고 다시 실행")
        return 1
    lines = parse_lines(text)
    mine = [ln for ln in lines if ln["who"] != GM_NAME]
    st = _load_state()
    st["enabled"] = True
    st["last_handled"] = (f"{mine[-1]['day']} {mine[-1]['when']} {mine[-1]['text']}"
                          if mine else "")
    _save_state(st)
    print(f"[agent] 초기화 완료 — 이 시점 이후 대표님 말씀부터 답한다\n  기준: {st['last_handled'][:80]}")
    return 0


def run(dry_run: bool = False) -> int:
    st = _load_state()
    if not st.get("enabled", False):
        print("[agent] enabled=false — 아무것도 하지 않는다")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    if st.get("sent_date") != today:
        st["sent_date"], st["sent_today"] = today, 0

    text = _export_chat()
    if text is None:
        return 0                                   # 못 읽은 날은 조용히 — 지어내지 않는다
    lines = parse_lines(text)
    fresh = new_from_partner(lines, st.get("last_handled", ""))
    if not fresh:
        print("[agent] 대표님 새 말씀 없음 — 먼저 말 걸지 않는다")
        return 0

    marker = f"{fresh[-1]['day']} {fresh[-1]['when']} {fresh[-1]['text']}"

    if st["sent_today"] >= DAILY_SEND_CAP:
        _tell_gm(f"🤖 다이어트캠프 에이전트 — 오늘 상한 {DAILY_SEND_CAP}통을 채워 답장을 멈췄습니다. "
                 f"대표님 새 말씀: {fresh[-1]['text'][:60]}")
        st["last_handled"] = marker
        _save_state(st)
        return 0

    from model_router import run_claude  # noqa: PLC0415
    draft, used = run_claude(build_prompt(lines, fresh), label="diet-camp-agent")
    if draft is None:
        print("[agent] 초안 생성 실패 — 이번 회차 건너뜀(다음 주기에 다시 시도)", file=sys.stderr)
        return 0
    draft = draft.strip()

    why = guard(draft)
    if why == "SKIP":
        print("[agent] 답장이 필요 없는 말씀 — 넘어간다")
        st["last_handled"] = marker
        _save_state(st)
        return 0
    if why:
        _tell_gm(f"🤖 다이어트캠프 에이전트 — 초안을 보내지 않고 올립니다({why}).\n"
                 f"대표님: {fresh[-1]['text'][:80]}\n초안: {draft[:400]}")
        st["last_handled"] = marker
        _save_state(st)
        return 0

    if dry_run:
        print("── 보낼 초안 (dry-run · 발신 안 함) ──")
        print(draft)
        return 0

    if _send(draft):
        st["sent_today"] += 1
        st["last_handled"] = marker
        st.setdefault("history", []).append(
            {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "model": used,
             "partner": fresh[-1]["text"][:120], "reply": draft})
        st["history"] = st["history"][-30:]
        _save_state(st)
        _tell_gm(f"🤖 다이어트캠프 에이전트 답장 1통\n대표님: {fresh[-1]['text'][:60]}\n"
                 f"보낸 말: {draft.splitlines()[0][:60]}")
        return 0
    _tell_gm("🤖 다이어트캠프 에이전트 — 답장 발신에 실패했습니다. 카톡 창을 확인해 주세요.")
    return 1


def _selfcheck() -> None:
    """네트워크·카톡 없이 도는 검사. 파싱·새 발화 판정·차단 규칙 셋만 본다."""
    sample = ("--------------- 2026년 9월 1일 화요일 ---------------\n"
              "[김남욱] [오전 7:00] 안녕하세요\n"
              "[다이어트캠프 이승기 대표님] [오후 5:11] 3번\n"
              "--------------- 2026년 9월 2일 수요일 ---------------\n"
              "[다이어트캠프 이승기 대표님] [오전 9:10] 40대 여자들 많아\n")
    lines = parse_lines(sample)
    assert len(lines) == 3, lines
    assert lines[-1]["day"] == "2026-09-02", lines[-1]

    # 처음 도는 경우 = 마지막 한 줄만 새 것
    assert [x["text"] for x in new_from_partner(lines, "")] == ["40대 여자들 많아"]
    # 표식 이후만 새 것
    assert [x["text"] for x in new_from_partner(lines, "2026-09-01 오후 5:11 3번")] == ["40대 여자들 많아"]
    # 최신까지 처리했으면 새 것 없음
    assert new_from_partner(lines, "2026-09-02 오전 9:10 40대 여자들 많아") == []
    # GM 발화는 답장 대상이 아니다
    assert all(x["who"] != GM_NAME for x in new_from_partner(lines, ""))

    assert guard("SKIP") == "SKIP"
    assert guard("") is not None
    assert guard("\n".join(f"{i}줄" for i in range(MAX_LINES + 1))) is not None
    assert guard("1️⃣ 감사합니다\n👉 한 줄만 주세요") is None
    assert guard("계약서 보내드리겠습니다") is not None, "돈·계약 표현은 막아야 한다"
    print("[selfcheck] diet_camp_agent OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="다이어트캠프 이승기 대표님 대화 에이전트")
    ap.add_argument("--dry-run", action="store_true", help="초안만 찍고 발신하지 않는다")
    ap.add_argument("--selftest", action="store_true", help="네트워크 없이 규칙만 검사")
    ap.add_argument("--init", action="store_true",
                    help="켜는 시점 기준선 잡기 — 지난 대화에 뒤늦게 답하지 않게 한다")
    args = ap.parse_args()
    if args.selftest:
        _selfcheck()
        return 0
    if args.init:
        return init_marker()
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
