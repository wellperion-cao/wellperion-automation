#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GM 화면에 내부 낱말이 나가는지 턴 끝에 잡는다 (GM 지시 2026-09-09 · Stop 훅).

GM 원문: "또 기록 커밋 이야기하네, 저장 배포로 통일 시켜달라고 계속 이야기하는데? 박제하지않았어?"

왜 필요한가
  같은 날 17:46 에 시우가 **도구가 찍는 문구**를 저장·배포로 바꿨다(커밋 327adba89). 그런데 그 뒤로도
  보고 표 끝줄이 계속 「기록 = 커밋 961b5a7f9」로 나갔다 — 도구는 고쳤는데 **사람(AI)이 쓰는 문장**은
  안 고쳐졌기 때문이다. 문서에 한 줄 더 적는 것으로는 안 잡힌다(오늘 하루에만 세 번 더 나갔다).
  그래서 턴이 끝날 때 실제로 나간 글을 읽어 세는 자리를 둔다.

무엇을 잡나
  GM 화면에 그대로 찍히면 안 되는 내부 낱말 — 커밋 · 푸시 · master · 브랜치 · 스위퍼 · cherry-pick ·
  origin. 대신 쓸 말 = 저장 / 배포 / 저장·배포 완료.

무엇은 안 잡나
  · GM 이 그 낱말을 먼저 쓴 턴(예: 지금 이 지시처럼 "커밋 이야기하네") — 되받아 답해야 한다.
  · 낱말·줄글 검사는 막지 않는다. 경고만 낸다(stderr).
  · 8요소 표 검사(검사 A·B)만 막는다 — stderr + exit 2. GM 지시 2026-09-10 이 다섯 번 반복돼서다.

자체점검: python scripts/gm_wording_guard.py --selftest
"""
import json
import os
import sys

# 내부 낱말 → GM 화면에서 쓸 말. 여기 없는 말은 잡지 않는다(과잉 경고 금지).
BANNED = {
    "커밋": "저장",
    "푸시": "배포",
    "브랜치": "(빼거나 '저장 줄기')",
    "스위퍼": "(빼기 — 배포가 알아서 된다)",
    "cherry-pick": "(빼기)",
    "master": "(빼기)",
    "origin": "(빼기)",
}


def last_messages(transcript_path):
    """(이번 턴 assistant 글, 이번 턴 user 글). 못 읽으면 ('', '').

    Stop 훅 타이밍 버그 방어: 역순으로 읽어 user 가 assistant 보다 먼저
    나오면 현재 응답이 아직 transcript 에 기록되지 않은 것 → ('', '') 반환.
    직전 턴 assistant 를 잘못 읽어 오탐(false positive)이 나는 것을 막는다.
    """
    assistant, user = "", ""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return "", ""
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        msg = row.get("message") or {}
        role = msg.get("role") or row.get("type")
        content = msg.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
        if not text.strip():
            continue
        # user 가 assistant 보다 먼저 나오면 현재 응답이 아직 미기록 상태
        if role == "user" and not assistant:
            return "", ""
        if role == "assistant" and not assistant:
            assistant = text
        elif role == "user" and not user:
            user = text
        if assistant and user:
            break
    return assistant, user


def offenders(assistant_text, user_text):
    """GM 화면에 나간 내부 낱말. GM 이 먼저 쓴 낱말은 뺀다."""
    return [w for w in BANNED if w in assistant_text and w not in user_text]


# ── 표 밖 줄글 (GM 지시 2026-09-10) ───────────────────────────────────────────────
#   GM 원문: "표로 안보여주고 또 이상하게 정리해주네, 이상하게 정리해주는 구조를 삭제할 순 없나?"
#   약속 L18 은 이미 「표가 본문 · 표 밖 줄글은 표로 못 담는 것만」인데, 문서로만 있어서
#   계속 새어 나갔다(같은 지적 반복). 그래서 낱말 검사와 같은 자리에서 줄 수를 센다.
#   허용 = 표 위 상태 결론 1줄 + 맨 끝 기록위치 1줄 + 판단 이유 2줄 = 4줄.
#   막지 않는다. 경고만 낸다(이 파일의 다른 검사와 같은 규칙).
PROSE_LIMIT = 4


def prose_lines(assistant_text):
    """표·목록·제목·코드를 뺀 '줄글' 줄만 센다. 표가 없는 답(코드 설명 등)은 대상 밖 — 빈 목록."""
    lines, in_code, out, has_table = assistant_text.splitlines(), False, [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        if s.startswith("|"):
            has_table = True
            continue
        if s.startswith(("#", ">", "-", "*", "·", "▪")) or s[:2].rstrip(".").isdigit():
            continue      # 제목·인용·목록은 줄글이 아니다(한눈에 읽힌다)
        out.append(s)
    return out if has_table else []


def prose_offense(assistant_text):
    """줄글이 허용치를 넘었으면 (넘은 줄 수, 예시 한 줄). 아니면 None."""
    ps = prose_lines(assistant_text)
    if len(ps) <= PROSE_LIMIT:
        return None
    longest = max(ps, key=len)
    return len(ps), (longest[:60] + "…" if len(longest) > 60 else longest)


# ── 8요소 표 (GM 지시 2026-09-10 · 하루 네 번 + 09-11 한 번 = 다섯 번 같은 지적) ─────────
#   경고만 내던 자리라 지켜지지 않았다. 검사 A(8요소 표 아님)·B(표 두 장)는 **막는다**(exit 2).
#   낱말·줄글 검사는 지금처럼 경고만 — 한꺼번에 막으면 되묻기 고리가 생긴다.
EIGHT = [("📌", "GM 요청"), ("🔍", "실측"), ("✅", "반영"),
         ("🔎", "검수"), ("📤", "배포"), ("⏱", "소요"), ("💡", "더 나았을 방법")]
TOOL_TABLES = ("🧭 오늘의 항로", "🥁 쿵짝표")   # 도구가 내는 정해진 표 = 대상 밖
FORMAT_HINT = (
    "  GM 지시 2026-09-10(4회 반복) = GM 화면에 내는 표는 8요소 표 하나뿐이다.\n"
    "  순서 고정: 📌 GM 요청 | 🔍 실측 | ✅ 반영 | 🔎 검수 | 📤 배포 | ⏱ 소요 | 💡 더 나았을 방법 | 👉 GM 액션(필요할 때만)\n"
    "  물음이 없는 턴도 같은 표를 쓴다 — 📌 칸에 '무엇 때문에 내는 보고인지'를 적으면 성립한다.\n"
    "  이 표로 다시 써라.\n")


def _body(assistant_text):
    """코드블록·빈 줄을 뺀 줄들."""
    out, in_code = [], False
    for ln in assistant_text.splitlines():
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        out.append(s)
    return out


def format_offense(assistant_text):
    """검사 A·B. 위반이면 되돌릴 글, 아니면 None."""
    if any(t in assistant_text for t in TOOL_TABLES):
        return None                                      # 도구가 낸 정해진 표
    body = _body(assistant_text)
    if not body:
        return None                                      # 코드 블록만 있는 답
    if not any(s.startswith("|") for s in body) and len(body) <= 2:
        return None                                      # 표 없는 짧은 답(한 줄 확인·되묻기)
    missing = ["%s %s" % (m, n) for m, n in EIGHT if m not in assistant_text]
    if missing:
        return ("[GM 답변 형식] 8요소 표가 아니다 — 빠진 칸: %s\n" % ", ".join(missing)) + FORMAT_HINT
    if assistant_text.count("📌") > 1:
        return ("[GM 답변 형식] 8요소 표가 두 장이다(📌 %d개) — 한 턴에 한 장이다.\n"
                "  보조 표는 8요소 표 아래 최대 1장(목록·비교처럼 표로만 담기는 것)이고, 📌 는 붙이지 않는다.\n"
                % assistant_text.count("📌")) + FORMAT_HINT
    # 검사 C — 한 요소를 여러 줄로 늘리지 않는다(GM 지적 2026-09-11 「표 완전 최악이네」).
    #   8요소 표는 8행이다. 실측을 네 줄, 반영을 세 줄로 쪼개면 표가 11행이 되고 구조가 무너져
    #   어느 것이 결론인지 안 보인다. 할 말이 많으면 칸 안에서 줄이고 나머지는 보조 표로 내린다.
    #   표 안 줄(| 로 시작)만 센다 — 맨 위 상태 결론 줄의 ✅·⏳ 는 규칙이 허용하는 자리다.
    rows = [s for s in body if s.startswith("|")]
    dup = [("%s %s" % (m, n), sum(s.count(m) for s in rows)) for m, n in EIGHT
           if sum(s.count(m) for s in rows) > 1]
    if dup:
        return ("[GM 답변 형식] 같은 요소가 여러 줄이다 — %s\n"
                "  8요소 표는 8행 고정이다. 한 요소 = 한 줄. 내용이 많으면 그 칸 안에서 줄여 쓰고,\n"
                "  목록이 필요하면 표 아래 보조 표 한 장으로 내린다.\n"
                % ", ".join("%s %d줄" % (k, v) for k, v in dup)) + FORMAT_HINT
    # 검사 D — 칸 하나에 문단을 넣지 않는다(GM 재지적 4회 · 2026-09-05·07·11·15 「표가 이상하게 나온다」).
    #   원격 화면은 칸이 길면 표가 통째로 무너진다. 규칙(한 줄 60자 안쪽)은 lessons.md 에 세 번 적혔는데
    #   지켜지지 않았다 — 문서가 아니라 여기서 잡는다. 8요소 표의 내용 칸만 잰다(보조 표는 안 잰다).
    long_cells = _long_cells(rows)
    if long_cells:
        return ("[GM 답변 형식] 칸이 너무 길다(%d자 초과) — %s\n"
                "  한 칸 = 한 줄 %d자 안쪽·한 가지. 긴 설명은 보조 표 한 장으로 내리거나 표 밖 두 줄로.\n"
                % (CELL_MAX, ", ".join("%s %d자" % (k, v) for k, v in long_cells), CELL_MAX)) + FORMAT_HINT
    return None


CELL_MAX = 60

# ── 검사 E — 👉 GM 액션 행에 GM 몫이 아닌 것을 올리지 않는다 (GM 2026-09-16 「일을 줄여야 하는데 왜 거꾸로 · 너무 힘들다」).
#   그날 한 세션이 4턴에 GM 액션 7건을 냈는데 GM 만 할 수 있는 것은 2건(💰 결제 · 공식값)이었다.
#   GM 몫 = 금지 5종(💰🔒🚫📐🏷️) + GM 손·GM 계정(결제·로그인·사람 사실 확인). 그 밖은 AI 가 기본값으로
#   진행하고 사후 한 줄이다(wellperion-boot §2-1 2026-08-03 GM 재확정). 경고만 — 형식 검사와 달리 내용 판정이라 막지 않는다.
GM_ONLY = ("💰", "🔒", "🚫", "📐", "🏷️", "결제", "결재", "계정", "로그인", "비밀번호", "공식값", "전략",
           "회장님", "대표님", "손", "직접", "가/부", "승인")


def gm_action_offense(assistant_text):
    """👉 GM 액션 행이 있는데 GM 몫 신호가 하나도 없으면 그 칸 내용을 돌려준다. 아니면 None."""
    for s in _body(assistant_text):
        if s.startswith("|") and "👉" in s:
            cells = [c.strip() for c in s.strip("|").split("|")]
            body = max(cells[1:], key=len) if len(cells) > 1 else ""
            if body and not any(k in body for k in GM_ONLY):
                return body
    return None


# ── 검사 F — 👉 GM 액션은 아침 한 줄로 모은다 (GM 2026-09-16 「일을 늘리지 말고 줄여라 · 내가 다 체크한다」).
#   검사 E 는 "이게 GM 몫이 맞나"를 가른다. 이 검사는 그 다음 층 — GM 몫이 맞아도 턴마다
#   물으면 GM 이 그때그때 결정을 떠안는다(같은 날 실측 하루 10회+). 급한 5종(💰🔒🚫📐🏷️)이
#   아니면 지금 묻지 않고 status/gm_asks.json 에 적어 아침 07:30~08:30 수집 창에서 한 번에
#   모은다. 경고만 — 표는 다음 턴이 지운다.
DEFER_WINDOW = (7 * 60 + 30, 8 * 60 + 30)  # 07:30~08:30(분)
URGENT_MARKS = ("💰", "🔒", "🚫", "📐", "🏷️")


def _in_defer_window(now=None) -> bool:
    import datetime as _dt
    now = now or _dt.datetime.now()
    minutes = now.hour * 60 + now.minute
    return DEFER_WINDOW[0] <= minutes <= DEFER_WINDOW[1]


def gm_action_defer(assistant_text, in_window=None):
    """👉 GM 액션 행 중 급한 5종이 없고 지금이 수집 시간도 아니면 그 칸 내용을 돌려준다. 아니면 None."""
    if in_window is None:
        in_window = _in_defer_window()
    if in_window:
        return None
    for s in _body(assistant_text):
        if s.startswith("|") and "👉" in s:
            cells = [c.strip() for c in s.strip("|").split("|")]
            # 2026-09-17 시토: 첫 칸이 👉 요소일 때만 — 가로 머리행(| 📌 … | 👉 GM 액션 |)이나
            #   👉 를 언급한 규칙 줄까지 여쭐 것으로 적혔다(gm_asks #3·#4 잡음).
            if not cells or not cells[0].startswith("👉") or len(cells) < 2:
                continue
            body = cells[1]
            if body and body not in ("없음", "행 없음", "해당 없음", "—", "-")                     and "📌" not in body and not any(k in body for k in URGENT_MARKS):
                return body
    return None


def _long_cells(rows):
    """8요소 표 행(| 📌 … | 내용 |)에서 내용 칸이 CELL_MAX 를 넘는 것 [(요소, 글자수)]."""
    out = []
    for m, n in EIGHT:
        for s in rows:
            if m not in s:
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2:
                continue
            body = max(cells[1:], key=len)
            if len(body) > CELL_MAX:
                out.append(("%s %s" % (m, n), len(body)))
            break
    return out


def main():
    if "--selftest" in sys.argv:
        assert offenders("기록 = 커밋 961b5a7f9", "") == ["커밋"]
        assert offenders("기록 = 커밋 961b5a7f9", "커밋 이야기하네") == []      # GM 이 먼저 쓴 낱말
        assert offenders("저장·배포 완료", "") == []
        assert offenders("master 로 올렸다", "") == ["master"]
        table = "| 📌 GM 요청 | 무엇 |\n|---|---|\n| ✅ 반영 | 했다 |"
        assert prose_offense("결론 한 줄\n" + table + "\n기록 = 저장·배포 완료") is None
        assert prose_offense(table + "\n" + "\n".join("줄글%d 입니다." % i for i in range(6)))[0] == 6
        assert prose_offense("표 없는 답인데 줄글이 다섯 줄이다.\n" * 6) is None   # 표 없는 답은 대상 밖
        assert prose_offense(table + "\n- 목록은 줄글이 아니다\n" * 9) is None
        # 검사 D — 칸 60자 초과(GM 재지적 4회 · 2026-09-15). 8요소 표 내용 칸만 잰다.
        full8 = ("| 📌 GM 요청 | 무엇 |\n|---|---|\n| 🔍 실측 | %s |\n| ✅ 반영 | 했다 |\n| 🔎 검수 | 봤다 |\n"
                 "| 📤 배포 | 완료 |\n| ⏱ 소요 | 1분 |\n| 💡 더 나았을 방법 | 없음 |")
        assert format_offense(full8 % ("짧다" * 5)) is None
        _long = format_offense(full8 % ("가" * 61))
        assert _long and "너무 길다" in _long and "🔍 실측 61자" in _long
        assert _long_cells(["| 🔍 실측 | " + "가" * 60 + " |"]) == []                  # 60자는 통과
        a, u = last_messages(os.devnull)
        assert (a, u) == ("", "")                                            # 못 읽어도 안 죽는다
        # Stop 훅 타이밍 버그: user 가 먼저 있고 assistant 가 없으면 미기록 상태 → ('', '')
        import tempfile
        def _make_transcript(*roles_texts):
            lines = []
            for role, text in roles_texts:
                lines.append(json.dumps({"message": {"role": role, "content": text}}))
            tf = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
            tf.write("\n".join(lines))
            tf.close()
            return tf.name
        # 정상: user → assistant 순(역순 스캔 시 assistant 먼저 발견)
        normal = _make_transcript(("user", "지시"), ("assistant", "8요소표"))
        a, u = last_messages(normal)
        assert a == "8요소표" and u == "지시", "정상 케이스 실패"
        os.unlink(normal)
        # 버그 케이스: assistant 가 아직 없고 user 만 있음(현재 응답 미기록)
        late = _make_transcript(("user", "이번턴지시"))
        a, u = last_messages(late)
        assert (a, u) == ("", ""), "타이밍 버그 케이스 실패 — user 먼저면 빈 값이어야 한다"
        os.unlink(late)
        full = ("| 📌 GM 요청 | 무엇 |\n|---|---|\n| 🔍 실측 | 쟀다 |\n| ✅ 반영 | 했다 |\n"
                "| 🔎 검수 | 봤다 |\n| 📤 배포 | 올렸다 |\n| ⏱ 소요 | 3분 |\n| 💡 더 나았을 방법 | 없다 |")
        assert format_offense(full) is None                                  # 8요소 다 있으면 통과
        half = format_offense("| 📌 GM 요청 | 무엇 |\n|---|---|\n| 🔍 실측 | 쟀다 |\n| ✅ 반영 | 했다 |\n| 💡 더 나았을 방법 | 없다 |")
        assert half and "🔎 검수" in half and "📤 배포" in half and "⏱ 소요" in half
        two = format_offense(full + "\n\n" + full)
        assert two and "두 장" in two                                        # 📌 두 번 = 위반
        assert format_offense("🧭 오늘의 항로\n| 배 | 상태 |\n|---|---|\n| 1101 | 진행 |") is None
        assert format_offense("🥁 쿵짝표\n| 지시 | 한 것 |\n|---|---|\n| a | b |") is None
        assert format_offense("네, 맞다.\n어느 쪽을 말하는 건가?") is None    # 표 없는 짧은 답
        assert format_offense("```\ncode only\n```") is None
        # 검사 E — 👉 행 내용 판정(GM 2026-09-16)
        assert gm_action_offense("| 👉 GM 액션 | 매터포트 결제(💰) |") is None
        assert gm_action_offense("| 👉 GM 액션 | 로고 v1 가/부 |") is None
        assert gm_action_offense("| 👉 GM 액션 | v3 이름표 바꿀 곳 지목 |") == "v3 이름표 바꿀 곳 지목"
        assert gm_action_offense(full) is None                                 # 👉 행 없음
        # 검사 F — 👉 아침 수집(GM 2026-09-16). in_window 를 직접 넘겨 벽시계에 의존하지 않는다.
        assert gm_action_defer("| 👉 GM 액션 | 급하지 않은 것 |", in_window=True) is None
        assert gm_action_defer("| 👉 GM 액션 | 급하지 않은 것 |", in_window=False) == "급하지 않은 것"
        assert gm_action_defer("| 👉 GM 액션 | 매터포트 결제(💰) |", in_window=False) is None   # 급한 5종은 통과
        assert gm_action_defer(full, in_window=False) is None                  # 👉 행 없음
        assert _in_defer_window(__import__("datetime").datetime(2026, 9, 16, 8, 0)) is True
        assert _in_defer_window(__import__("datetime").datetime(2026, 9, 16, 9, 0)) is False
        print("selftest ok")
        return 0
    if os.environ.get("WELLPERION_HEADLESS"):
        # INC-063 재발(2026-09-17): 무인 claude -p(아침 요약 두뇌)에도 이 Stop 훅이 붙어
        # 「8요소 표로 다시 써라」(return 2)로 되돌리자 두뇌가 JSON 대신 표를 냈다.
        # 사람 세션 규칙은 사람 세션에만 — worklog.py 와 같은 표식으로 통째 건너뛴다.
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    path = payload.get("transcript_path") or ""
    if not path:
        return 0
    assistant, user = last_messages(path)
    if not assistant:
        return 0
    bad = offenders(assistant, user)
    if bad:
        fix = " · ".join("%s→%s" % (w, BANNED[w]) for w in bad)
        sys.stderr.write(
            "[GM 화면 낱말] 방금 답에 내부 낱말이 나갔다: %s\n"
            "  GM 지시(2026-09-09) = 저장·배포로 통일. 도구 문구는 이미 그렇게 찍는다(시우 327adba89).\n"
            "  고칠 것: %s\n" % (", ".join(bad), fix))
    long_prose = prose_offense(assistant)
    if long_prose:
        n, sample = long_prose
        sys.stderr.write(
            "[GM 화면 줄글] 방금 답에 표 밖 줄글이 %d줄 나갔다(허용 %d줄).\n"
            "  GM 지시(2026-09-10) = 표가 본문. 표로 담을 수 있는 말은 표 안으로 옮긴다.\n"
            "  본보기: %s\n" % (n, PROSE_LIMIT, sample))
    bad_format = format_offense(assistant)
    if bad_format:
        sys.stderr.write(bad_format)
        return 2                       # 막는다 — 경고만으로는 같은 지적이 다섯 번 났다
    homework = gm_action_offense(assistant)
    if homework:
        sys.stderr.write(
            "[GM 숙제] 👉 GM 액션 행에 GM 몫이 아닌 것이 올라갔다: %s\n"
            "  GM 몫 = 💰🔒🚫📐🏷️ 5종 + GM 손·GM 계정뿐(2026-08-03 GM 재확정). 나머지는 기본값으로\n"
            "  내가 진행하고 사후 한 줄로 알린다 — 행을 지우거나 GM 몫만 남겨라(GM 2026-09-16 「일이 거꾸로 는다」).\n"
            % (homework[:60] + "…" if len(homework) > 60 else homework))
    defer = gm_action_defer(assistant)
    if defer:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import gm_asks
            new_id = gm_asks.add(role=os.environ.get("WELLPERION_ROLE") or "unknown",
                                  title=defer, why_gm="👉 GM 액션(수집 시간 07:30~08:30 밖)")
        except Exception:
            new_id = 0
        sys.stderr.write(
            "[GM 액션 보류] 👉 는 아침 한 줄로 모은다 — status/gm_asks.json #%d 에 적고 표에서 뺀다.\n"
            "  수집 시간(07:30~08:30) 밖이다. 급한 5종(💰🔒🚫📐🏷️)이면 그대로 두어도 된다.\n" % new_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
